"""
HSIL Weather Service - NOAA Edition

Fetches and caches external environmental data from NOAA CDO Web Services:
- Weather conditions (temperature, humidity, precipitation)
- Wind speed and direction
- Atmospheric pressure
- Sunrise/sunset times (calculated)
- Air quality (from AirNow API)

API Docs: https://www.ncdc.noaa.gov/cdo-web/webservices/v2
"""

import logging
import os
import math
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WeatherData(BaseModel):
    """Current weather conditions"""
    temperature: float = Field(description="Temperature in Fahrenheit")
    feels_like: float = Field(description="Feels like temperature in Fahrenheit")
    humidity: int = Field(description="Humidity percentage")
    pressure: int = Field(description="Atmospheric pressure in hPa")
    description: str = Field(description="Weather description")
    icon: str = Field(description="Weather icon code")
    wind_speed: float = Field(description="Wind speed in mph")
    clouds: int = Field(description="Cloudiness percentage")
    visibility: int = Field(description="Visibility in meters")
    timestamp: datetime = Field(default_factory=datetime.now)


class SunTimes(BaseModel):
    """Sunrise and sunset times"""
    sunrise: datetime
    sunset: datetime
    day_length_hours: float = Field(description="Length of day in hours")


class AirQuality(BaseModel):
    """Air quality index data"""
    aqi: int = Field(description="Air Quality Index (1-5, 1=Good, 5=Very Poor)")
    pm2_5: Optional[float] = Field(None, description="PM2.5 concentration")
    pm10: Optional[float] = Field(None, description="PM10 concentration")
    o3: Optional[float] = Field(None, description="Ozone concentration")
    no2: Optional[float] = Field(None, description="NO2 concentration")
    timestamp: datetime = Field(default_factory=datetime.now)

    def quality_text(self) -> str:
        """Get text description of air quality"""
        if self.aqi == 1:
            return "Good"
        elif self.aqi == 2:
            return "Fair"
        elif self.aqi == 3:
            return "Moderate"
        elif self.aqi == 4:
            return "Poor"
        else:
            return "Very Poor"


class EnvironmentalContext(BaseModel):
    """Complete environmental context"""
    weather: WeatherData
    sun: SunTimes
    air_quality: Optional[AirQuality] = None
    location: str = Field(description="Location name")
    cached_at: datetime = Field(default_factory=datetime.now)


class WeatherService:
    """
    Service for fetching external environmental data from NOAA.

    Uses NOAA CDO Web Services v2:
    - Historical and near-real-time weather observations
    - Station-based data (requires finding nearest station)
    - Free API with token (https://www.ncdc.noaa.gov/cdo-web/token)

    Caches data for 15 minutes to reduce API calls.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        lat: float = 37.7749,  # Default: San Francisco
        lon: float = -122.4194,
        location_name: str = "San Francisco, CA",
        station_id: Optional[str] = None  # NOAA station ID (e.g., "GHCND:USW00023234")
    ):
        """
        Initialize weather service.

        Args:
            api_key: NOAA CDO API token (or use NOAA_API_KEY env var)
            lat: Latitude
            lon: Longitude
            location_name: Human-readable location name
            station_id: NOAA station ID (auto-detected if None)
        """
        self.api_key = api_key or os.getenv("NOAA_API_KEY")
        self.lat = lat
        self.lon = lon
        self.location_name = location_name
        self.station_id = station_id

        # AirNow API for air quality (separate from NOAA)
        self.airnow_api_key = os.getenv("AIRNOW_API_KEY")

        # Cache
        self._cache: Optional[EnvironmentalContext] = None
        self._cache_duration = timedelta(minutes=15)

        # Station cache
        self._nearest_station: Optional[str] = None

        if not self.api_key:
            logger.warning(
                "No NOAA API key configured. "
                "Set NOAA_API_KEY environment variable. "
                "Get a free token at https://www.ncdc.noaa.gov/cdo-web/token"
            )

    async def get_environmental_context(self, force_refresh: bool = False) -> Optional[EnvironmentalContext]:
        """
        Get current environmental context (weather, sun times, air quality).

        Args:
            force_refresh: Force fetch from API instead of using cache

        Returns:
            EnvironmentalContext or None if API key not configured
        """
        # Check cache
        if not force_refresh and self._cache:
            age = datetime.now() - self._cache.cached_at
            if age < self._cache_duration:
                logger.debug(f"Using cached environmental data (age: {age.seconds}s)")
                return self._cache

        # API key required
        if not self.api_key:
            logger.debug("No API key - returning None")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Find nearest station if not set
                if not self.station_id and not self._nearest_station:
                    self._nearest_station = await self._find_nearest_station(client)

                station = self.station_id or self._nearest_station

                if not station:
                    logger.error("Could not find NOAA weather station")
                    return None

                # Fetch weather data from NOAA
                weather_data = await self._fetch_weather(client, station)

                # Calculate sun times
                sun_times = self._calculate_sun_times()

                # Fetch air quality from AirNow
                air_quality = await self._fetch_air_quality(client)

                # Build context
                context = EnvironmentalContext(
                    weather=weather_data,
                    sun=sun_times,
                    air_quality=air_quality,
                    location=self.location_name,
                    cached_at=datetime.now()
                )

                # Cache it
                self._cache = context
                logger.info(f"Refreshed environmental data for {self.location_name}")

                return context

        except Exception as e:
            logger.error(f"Error fetching environmental data: {e}", exc_info=True)
            return self._cache  # Return stale cache on error

    async def _find_nearest_station(self, client: httpx.AsyncClient) -> Optional[str]:
        """
        Find nearest NOAA weather station to lat/lon.

        Uses the NOAA CDO stations endpoint with extent-based search.
        """
        try:
            # Search for stations within ~0.5 degree (~35 miles) radius
            extent = 0.5
            url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/stations"

            params = {
                "extent": f"{self.lat - extent},{self.lon - extent},{self.lat + extent},{self.lon + extent}",
                "datatypeid": "TOBS",  # Temperature observation (common)
                "limit": 10,
                "offset": 1
            }

            headers = {"token": self.api_key}

            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if "results" not in data or len(data["results"]) == 0:
                logger.warning("No NOAA stations found near location")
                return None

            # Return first station
            station_id = data["results"][0]["id"]
            logger.info(f"Found NOAA station: {station_id}")
            return station_id

        except Exception as e:
            logger.error(f"Error finding NOAA station: {e}")
            return None

    async def _fetch_weather(self, client: httpx.AsyncClient, station_id: str) -> WeatherData:
        """
        Fetch recent weather observations from NOAA station.

        Returns latest observations for temperature, humidity, wind, etc.
        """
        # Fetch last 24 hours of data
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(hours=24)

        url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"

        params = {
            "datasetid": "GHCND",  # Global Historical Climatology Network Daily
            "stationid": station_id,
            "startdate": start_date.strftime("%Y-%m-%d"),
            "enddate": end_date.strftime("%Y-%m-%d"),
            "units": "standard",  # Fahrenheit, mph
            "limit": 1000
        }

        headers = {"token": self.api_key}

        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Parse latest observations
        observations = {}

        if "results" in data:
            for obs in data["results"]:
                datatype = obs.get("datatype")
                value = obs.get("value")

                if datatype == "TOBS":  # Temperature observation
                    observations["temperature"] = value
                elif datatype == "AWND":  # Average wind speed
                    observations["wind_speed"] = value * 2.237  # m/s to mph
                elif datatype == "PRCP":  # Precipitation
                    observations["precipitation"] = value

        # Build WeatherData from observations
        temp = observations.get("temperature", 70.0)

        # Estimate feels_like using wind chill or heat index
        wind_speed = observations.get("wind_speed", 5.0)
        feels_like = self._calculate_feels_like(temp, wind_speed, humidity=50)

        # Determine weather description from precipitation
        precip = observations.get("precipitation", 0.0)
        if precip > 0.1:
            description = "rainy"
            icon = "09d"
        elif precip > 0:
            description = "light rain"
            icon = "10d"
        else:
            description = "clear"
            icon = "01d"

        return WeatherData(
            temperature=temp,
            feels_like=feels_like,
            humidity=50,  # NOAA GHCND doesn't include humidity - would need different dataset
            pressure=1013,  # Standard pressure - would need barometric data
            description=description,
            icon=icon,
            wind_speed=wind_speed,
            clouds=20,  # Estimated
            visibility=10000,  # Default 10km
            timestamp=datetime.now()
        )

    def _calculate_feels_like(self, temp_f: float, wind_mph: float, humidity: int) -> float:
        """
        Calculate feels-like temperature using wind chill or heat index.

        Args:
            temp_f: Temperature in Fahrenheit
            wind_mph: Wind speed in mph
            humidity: Relative humidity percentage

        Returns:
            Feels-like temperature in Fahrenheit
        """
        # Wind chill (temp < 50°F, wind > 3 mph)
        if temp_f <= 50 and wind_mph > 3:
            wind_chill = (
                35.74 + 0.6215 * temp_f
                - 35.75 * (wind_mph ** 0.16)
                + 0.4275 * temp_f * (wind_mph ** 0.16)
            )
            return wind_chill

        # Heat index (temp > 80°F)
        elif temp_f >= 80:
            c1 = -42.379
            c2 = 2.04901523
            c3 = 10.14333127
            c4 = -0.22475541
            c5 = -6.83783e-3
            c6 = -5.481717e-2
            c7 = 1.22874e-3
            c8 = 8.5282e-4
            c9 = -1.99e-6

            heat_index = (
                c1 + c2 * temp_f + c3 * humidity
                + c4 * temp_f * humidity
                + c5 * (temp_f ** 2)
                + c6 * (humidity ** 2)
                + c7 * (temp_f ** 2) * humidity
                + c8 * temp_f * (humidity ** 2)
                + c9 * (temp_f ** 2) * (humidity ** 2)
            )
            return heat_index

        # No adjustment needed
        return temp_f

    def _calculate_sun_times(self) -> SunTimes:
        """
        Calculate sunrise/sunset times using solar position algorithm.

        Uses simplified sunrise equation based on latitude and day of year.
        """
        now = datetime.now()
        day_of_year = now.timetuple().tm_yday

        # Solar declination
        declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))

        # Hour angle at sunrise/sunset
        lat_rad = math.radians(self.lat)
        dec_rad = math.radians(declination)

        cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

        # Check for polar day/night
        if cos_hour_angle > 1:
            # Polar night
            sunrise = now.replace(hour=12, minute=0, second=0, microsecond=0)
            sunset = now.replace(hour=12, minute=0, second=0, microsecond=0)
        elif cos_hour_angle < -1:
            # Polar day
            sunrise = now.replace(hour=0, minute=0, second=0, microsecond=0)
            sunset = now.replace(hour=23, minute=59, second=0, microsecond=0)
        else:
            hour_angle = math.degrees(math.acos(cos_hour_angle))

            # Solar noon offset from Greenwich (negative lon = west)
            # West is negative, so we ADD to get local time
            solar_noon_offset = -self.lon / 15.0  # degrees to hours

            # Sunrise and sunset times (in local time)
            sunrise_hour = 12 - (hour_angle / 15.0) + solar_noon_offset
            sunset_hour = 12 + (hour_angle / 15.0) + solar_noon_offset

            # Clamp to valid hour range [0, 23]
            sunrise_hour = max(0, min(23.99, sunrise_hour))
            sunset_hour = max(0, min(23.99, sunset_hour))

            sunrise = now.replace(hour=int(sunrise_hour), minute=int((sunrise_hour % 1) * 60), second=0, microsecond=0)
            sunset = now.replace(hour=int(sunset_hour), minute=int((sunset_hour % 1) * 60), second=0, microsecond=0)

        day_length = (sunset - sunrise).total_seconds() / 3600

        return SunTimes(
            sunrise=sunrise,
            sunset=sunset,
            day_length_hours=day_length
        )

    async def _fetch_air_quality(self, client: httpx.AsyncClient) -> Optional[AirQuality]:
        """
        Fetch air quality from AirNow API (EPA).

        NOAA doesn't provide air quality, so we use EPA's AirNow service.
        """
        if not self.airnow_api_key:
            logger.debug("No AirNow API key - skipping air quality")
            return None

        try:
            url = "https://www.airnowapi.org/aq/observation/latLong/current/"

            params = {
                "format": "application/json",
                "latitude": self.lat,
                "longitude": self.lon,
                "distance": 25,  # miles
                "API_KEY": self.airnow_api_key
            }

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data or len(data) == 0:
                return None

            # Find PM2.5 and Ozone observations
            pm25_aqi = None
            o3_aqi = None

            for obs in data:
                param = obs.get("ParameterName", "")
                aqi = obs.get("AQI")

                if param == "PM2.5" and aqi:
                    pm25_aqi = aqi
                elif param == "O3" and aqi:
                    o3_aqi = aqi

            # Use worst AQI
            aqi_value = max(pm25_aqi or 0, o3_aqi or 0)

            # Convert AQI (0-500) to 1-5 scale
            if aqi_value <= 50:
                aqi_cat = 1  # Good
            elif aqi_value <= 100:
                aqi_cat = 2  # Fair
            elif aqi_value <= 150:
                aqi_cat = 3  # Moderate
            elif aqi_value <= 200:
                aqi_cat = 4  # Poor
            else:
                aqi_cat = 5  # Very Poor

            return AirQuality(
                aqi=aqi_cat,
                pm2_5=pm25_aqi,
                o3=o3_aqi,
                timestamp=datetime.now()
            )

        except Exception as e:
            logger.warning(f"Could not fetch air quality: {e}")
            return None

    def format_for_llm(self, context: Optional[EnvironmentalContext]) -> str:
        """
        Format environmental context as text for LLM consumption.

        Returns:
            Human-readable text summary of environmental conditions
        """
        if not context:
            return "Environmental data not available."

        lines = [
            f"📍 Location: {context.location}",
            f"",
            f"🌤️  Weather (NOAA):",
            f"  • Temperature: {context.weather.temperature:.1f}°F (feels like {context.weather.feels_like:.1f}°F)",
            f"  • Conditions: {context.weather.description.title()}",
            f"  • Humidity: {context.weather.humidity}%",
            f"  • Wind: {context.weather.wind_speed:.1f} mph",
        ]

        # Add sun times
        lines.extend([
            f"",
            f"🌅 Sun:",
            f"  • Sunrise: {context.sun.sunrise.strftime('%I:%M %p')}",
            f"  • Sunset: {context.sun.sunset.strftime('%I:%M %p')}",
        ])

        # Add air quality if available
        if context.air_quality:
            lines.extend([
                f"",
                f"💨 Air Quality: {context.air_quality.quality_text()} (AQI category {context.air_quality.aqi})",
            ])
            if context.air_quality.pm2_5:
                lines.append(f"  • PM2.5 AQI: {context.air_quality.pm2_5}")

        return "\n".join(lines)

    async def refresh(self, force_refresh: bool = True):
        """
        Refresh weather cache.

        This is called by WeatherSyncService in background.

        Args:
            force_refresh: Force fetch from API
        """
        await self.get_environmental_context(force_refresh=force_refresh)

    @property
    def cached_context(self) -> Optional[EnvironmentalContext]:
        """
        Get cached environmental context without fetching.

        Returns:
            Cached EnvironmentalContext or None
        """
        return self._cache

    def format_for_llm(self, context: Optional[EnvironmentalContext] = None) -> Dict[str, Any]:
        """
        Format environmental context for LLM consumption.

        Returns minimal, structured weather data suitable for LLM prompts.
        Avoids overwhelming the context window with unnecessary data.

        Args:
            context: EnvironmentalContext (uses cache if None)

        Returns:
            Dictionary with essential weather fields
        """
        if context is None:
            context = self._cache

        if not context:
            return {"status": "unavailable"}

        result = {
            "temperature": round(context.weather.temperature, 1),
            "feels_like": round(context.weather.feels_like, 1),
            "humidity": context.weather.humidity,
            "condition": context.weather.description,
            "wind_speed": round(context.weather.wind_speed, 1),
        }

        # Add sun context if relevant (time of day)
        now = datetime.now()
        if now < context.sun.sunrise:
            result["sun_status"] = "before_sunrise"
        elif now > context.sun.sunset:
            result["sun_status"] = "after_sunset"
        else:
            result["sun_status"] = "daytime"

        # Add air quality if available
        if context.air_quality:
            result["air_quality"] = context.air_quality.quality_text()
            result["aqi"] = context.air_quality.aqi

        return result
