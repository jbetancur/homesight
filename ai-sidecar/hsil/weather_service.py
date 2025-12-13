"""
HSIL Weather Service - Met.no Edition

Fetches real-time weather data from the Norwegian Meteorological Institute (Met.no),
the same source used by Home Assistant's default weather integration.

Features:
- Current weather conditions (temperature, humidity, wind, etc.)
- Hourly and daily forecasts
- Sunrise/sunset times (calculated)
- Air quality (from AirNow API, optional)

API Docs: https://api.met.no/weatherapi/locationforecast/2.0/documentation
No API key required! Just needs a User-Agent header.
"""

import logging
import os
import json
import math
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Shared cache for multi-worker coordination
WEATHER_CACHE_FILE = Path("/tmp/homesight_cache/weather.json")


class WeatherData(BaseModel):
    """Current weather conditions"""
    temperature: float = Field(description="Temperature in Fahrenheit")
    feels_like: float = Field(description="Feels like temperature in Fahrenheit")
    humidity: int = Field(description="Humidity percentage")
    pressure: int = Field(description="Atmospheric pressure in hPa")
    description: str = Field(description="Weather description")
    icon: str = Field(description="Weather icon code")
    wind_speed: float = Field(description="Wind speed in mph")
    wind_direction: Optional[float] = Field(None, description="Wind direction in degrees")
    clouds: int = Field(description="Cloudiness percentage")
    visibility: int = Field(description="Visibility in meters")
    uv_index: Optional[float] = Field(None, description="UV index")
    precipitation: Optional[float] = Field(None, description="Precipitation in last hour (inches)")
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


class HourlyForecast(BaseModel):
    """Hourly forecast data"""
    time: datetime
    temperature: float
    condition: str
    precipitation_probability: Optional[int] = None
    precipitation: Optional[float] = None
    wind_speed: float
    humidity: int


class EnvironmentalContext(BaseModel):
    """Complete environmental context"""
    weather: WeatherData
    sun: SunTimes
    air_quality: Optional[AirQuality] = None
    hourly_forecast: Optional[List[HourlyForecast]] = None
    location: str = Field(description="Location name")
    cached_at: datetime = Field(default_factory=datetime.now)


# Met.no weather symbol to description mapping
WEATHER_SYMBOLS = {
    "clearsky": ("Clear sky", "01d"),
    "fair": ("Fair", "02d"),
    "partlycloudy": ("Partly cloudy", "03d"),
    "cloudy": ("Cloudy", "04d"),
    "rainshowers": ("Rain showers", "09d"),
    "rainshowersandthunder": ("Thunderstorms", "11d"),
    "sleetshowers": ("Sleet showers", "13d"),
    "snowshowers": ("Snow showers", "13d"),
    "rain": ("Rain", "10d"),
    "heavyrain": ("Heavy rain", "10d"),
    "heavyrainandthunder": ("Heavy thunderstorms", "11d"),
    "sleet": ("Sleet", "13d"),
    "snow": ("Snow", "13d"),
    "snowandthunder": ("Snow and thunder", "13d"),
    "fog": ("Fog", "50d"),
    "sleetshowersandthunder": ("Sleet and thunder", "11d"),
    "snowshowersandthunder": ("Snow and thunder", "11d"),
    "rainandthunder": ("Rain and thunder", "11d"),
    "sleetandthunder": ("Sleet and thunder", "11d"),
    "lightrainshowers": ("Light rain showers", "09d"),
    "heavyrainshowers": ("Heavy rain showers", "09d"),
    "lightsleetshowers": ("Light sleet showers", "13d"),
    "heavysleetshowers": ("Heavy sleet showers", "13d"),
    "lightsnowshowers": ("Light snow showers", "13d"),
    "heavysnowshowers": ("Heavy snow showers", "13d"),
    "lightrain": ("Light rain", "10d"),
    "lightsleet": ("Light sleet", "13d"),
    "heavysleet": ("Heavy sleet", "13d"),
    "lightsnow": ("Light snow", "13d"),
    "heavysnow": ("Heavy snow", "13d"),
}


class WeatherService:
    """
    Service for fetching real-time weather data from Met.no.

    Uses the same API as Home Assistant's default weather integration.
    No API key required - just needs proper User-Agent header.

    API: https://api.met.no/weatherapi/locationforecast/2.0/
    """

    def __init__(
        self,
        zip_code: str = "94102",
        location_name: Optional[str] = None,
    ):
        """
        Initialize weather service.

        Args:
            zip_code: US ZIP code for weather location
            location_name: Human-readable location name (auto-detected if None)
        """
        self.zip_code = zip_code
        self.location_name = location_name or f"ZIP {zip_code}"
        
        # Coordinates - will be populated from ZIP geocoding
        self.lat: Optional[float] = None
        self.lon: Optional[float] = None

        # AirNow API for air quality (optional)
        self.airnow_api_key = os.getenv("AIRNOW_API_KEY")

        # Cache
        self._cache: Optional[EnvironmentalContext] = None
        self._cache_duration = timedelta(minutes=15)

        # Met.no requires a User-Agent identifying the application
        self.user_agent = "HomeSight/1.0 (https://github.com/jbetancur/homesight)"

    async def get_environmental_context(self, force_refresh: bool = False) -> Optional[EnvironmentalContext]:
        """
        Get current environmental context (weather, sun times, air quality).

        Args:
            force_refresh: Force fetch from API instead of using cache

        Returns:
            EnvironmentalContext or None if fetch fails
        """
        # Check shared file cache first (works across all workers)
        if not force_refresh:
            cached_context = self._read_weather_cache()
            if cached_context:
                logger.debug("Using cached weather from shared file")
                self._cache = cached_context  # Update in-memory cache too
                return cached_context

        # Check in-memory cache as fallback
        if not force_refresh and self._cache:
            age = datetime.now() - self._cache.cached_at
            if age < self._cache_duration:
                logger.debug(f"Using in-memory cached environmental data (age: {age.seconds}s)")
                return self._cache

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Geocode ZIP if we don't have coordinates
                if self.lat is None or self.lon is None:
                    if not await self._geocode_zip(client):
                        logger.error(f"Could not geocode ZIP {self.zip_code}")
                        return self._cache

                # Fetch weather from Met.no
                weather_data, hourly_forecast = await self._fetch_weather(client)

                if not weather_data:
                    logger.error("Could not fetch weather data from Met.no")
                    return self._cache

                # Calculate sun times
                sun_times = self._calculate_sun_times()

                # Fetch air quality from AirNow (optional)
                air_quality = await self._fetch_air_quality(client)

                # Build context
                context = EnvironmentalContext(
                    weather=weather_data,
                    sun=sun_times,
                    air_quality=air_quality,
                    hourly_forecast=hourly_forecast,
                    location=self.location_name,
                    cached_at=datetime.now()
                )

                # Cache it (both in-memory and shared file)
                self._cache = context
                self._write_weather_cache(context)
                logger.info(f"Refreshed weather data for {self.location_name}: {weather_data.temperature:.1f}°F, {weather_data.description}")

                return context

        except Exception as e:
            logger.error(f"Error fetching environmental data: {e}", exc_info=True)
            return self._cache  # Return stale cache on error

    async def _geocode_zip(self, client: httpx.AsyncClient) -> bool:
        """
        Geocode ZIP code to lat/lon using free Zippopotam.us API.
        
        Returns True if successful, False otherwise.
        """
        try:
            url = f"https://api.zippopotam.us/us/{self.zip_code}"
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.warning(f"Could not geocode ZIP {self.zip_code}")
                return False
            
            data = response.json()
            if "places" in data and len(data["places"]) > 0:
                place = data["places"][0]
                self.lat = float(place["latitude"])
                self.lon = float(place["longitude"])
                self.location_name = f"{place['place name']}, {place['state abbreviation']}"
                logger.info(f"Geocoded ZIP {self.zip_code} to {self.location_name} ({self.lat}, {self.lon})")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error geocoding ZIP {self.zip_code}: {e}")
            return False

    async def _fetch_weather(self, client: httpx.AsyncClient) -> tuple[Optional[WeatherData], Optional[List[HourlyForecast]]]:
        """
        Fetch current weather and forecast from Met.no.

        Returns:
            Tuple of (current weather, hourly forecast list)
        """
        try:
            url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
            
            params = {
                "lat": round(self.lat, 4),  # Met.no wants max 4 decimal places
                "lon": round(self.lon, 4),
            }
            
            headers = {
                "User-Agent": self.user_agent,
            }

            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Parse the response
            properties = data.get("properties", {})
            timeseries = properties.get("timeseries", [])

            if not timeseries:
                logger.warning("No timeseries data in Met.no response")
                return None, None

            # Current conditions from first timeseries entry
            current = timeseries[0]
            current_data = current.get("data", {})
            instant = current_data.get("instant", {}).get("details", {})
            next_1h = current_data.get("next_1_hours", {})
            next_6h = current_data.get("next_6_hours", {})

            # Get weather symbol (condition)
            symbol_code = ""
            if next_1h:
                symbol_code = next_1h.get("summary", {}).get("symbol_code", "")
            elif next_6h:
                symbol_code = next_6h.get("summary", {}).get("symbol_code", "")

            # Strip day/night suffix from symbol code
            base_symbol = symbol_code.replace("_day", "").replace("_night", "").replace("_polartwilight", "")
            description, icon = WEATHER_SYMBOLS.get(base_symbol, ("Unknown", "01d"))

            # Temperature (Met.no gives Celsius, convert to Fahrenheit)
            temp_c = instant.get("air_temperature", 20)
            temp_f = temp_c * 9 / 5 + 32

            # Wind speed (Met.no gives m/s, convert to mph)
            wind_ms = instant.get("wind_speed", 0)
            wind_mph = wind_ms * 2.237

            # Calculate feels-like temperature
            humidity = int(instant.get("relative_humidity", 50))
            feels_like = self._calculate_feels_like(temp_f, wind_mph, humidity)

            # Precipitation from next_1h if available
            precipitation = None
            if next_1h:
                precip_mm = next_1h.get("details", {}).get("precipitation_amount", 0)
                precipitation = precip_mm / 25.4  # mm to inches

            weather = WeatherData(
                temperature=temp_f,
                feels_like=feels_like,
                humidity=humidity,
                pressure=int(instant.get("air_pressure_at_sea_level", 1013)),
                description=description,
                icon=icon,
                wind_speed=wind_mph,
                wind_direction=instant.get("wind_from_direction"),
                clouds=int(instant.get("cloud_area_fraction", 0)),
                visibility=10000,  # Met.no doesn't provide visibility
                uv_index=instant.get("ultraviolet_index_clear_sky"),
                precipitation=precipitation,
                timestamp=datetime.now()
            )

            # Parse hourly forecast (next 12 hours)
            hourly_forecast = []
            for entry in timeseries[1:13]:  # Skip current, get next 12
                try:
                    time_str = entry.get("time", "")
                    entry_data = entry.get("data", {})
                    entry_instant = entry_data.get("instant", {}).get("details", {})
                    entry_next_1h = entry_data.get("next_1_hours", {})

                    # Parse time
                    forecast_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

                    # Temperature
                    fc_temp_c = entry_instant.get("air_temperature", 20)
                    fc_temp_f = fc_temp_c * 9 / 5 + 32

                    # Condition
                    fc_symbol = ""
                    if entry_next_1h:
                        fc_symbol = entry_next_1h.get("summary", {}).get("symbol_code", "")
                    fc_base = fc_symbol.replace("_day", "").replace("_night", "").replace("_polartwilight", "")
                    fc_desc, _ = WEATHER_SYMBOLS.get(fc_base, ("Unknown", "01d"))

                    # Precipitation
                    fc_precip = None
                    fc_precip_prob = None
                    if entry_next_1h:
                        details = entry_next_1h.get("details", {})
                        fc_precip_mm = details.get("precipitation_amount", 0)
                        fc_precip = fc_precip_mm / 25.4 if fc_precip_mm else None
                        fc_precip_prob = int(details.get("probability_of_precipitation", 0)) if "probability_of_precipitation" in details else None

                    # Wind
                    fc_wind_ms = entry_instant.get("wind_speed", 0)
                    fc_wind_mph = fc_wind_ms * 2.237

                    hourly_forecast.append(HourlyForecast(
                        time=forecast_time,
                        temperature=fc_temp_f,
                        condition=fc_desc,
                        precipitation_probability=fc_precip_prob,
                        precipitation=fc_precip,
                        wind_speed=fc_wind_mph,
                        humidity=int(entry_instant.get("relative_humidity", 50))
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing forecast entry: {e}")
                    continue

            return weather, hourly_forecast if hourly_forecast else None

        except Exception as e:
            logger.error(f"Error fetching weather from Met.no: {e}")
            return None, None

    def _calculate_feels_like(self, temp_f: float, wind_mph: float, humidity: int) -> float:
        """
        Calculate feels-like temperature using wind chill or heat index.
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

        return temp_f

    def _calculate_sun_times(self) -> SunTimes:
        """
        Calculate sunrise/sunset times using solar position algorithm.
        """
        now = datetime.now()
        
        lat = self.lat if self.lat is not None else 40.7128
        lon = self.lon if self.lon is not None else -74.0060
        
        day_of_year = now.timetuple().tm_yday

        # Solar declination
        declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))

        # Hour angle at sunrise/sunset
        lat_rad = math.radians(lat)
        dec_rad = math.radians(declination)

        cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

        # Check for polar day/night
        if cos_hour_angle > 1:
            sunrise = now.replace(hour=12, minute=0, second=0, microsecond=0)
            sunset = now.replace(hour=12, minute=0, second=0, microsecond=0)
        elif cos_hour_angle < -1:
            sunrise = now.replace(hour=0, minute=0, second=0, microsecond=0)
            sunset = now.replace(hour=23, minute=59, second=0, microsecond=0)
        else:
            hour_angle = math.degrees(math.acos(cos_hour_angle))

            # Solar noon offset from Greenwich
            solar_noon_offset = -lon / 15.0

            sunrise_hour = 12 - (hour_angle / 15.0) + solar_noon_offset
            sunset_hour = 12 + (hour_angle / 15.0) + solar_noon_offset

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
        """
        if not self.airnow_api_key:
            return None

        try:
            url = "https://www.airnowapi.org/aq/observation/latLong/current/"

            params = {
                "format": "application/json",
                "latitude": self.lat,
                "longitude": self.lon,
                "distance": 25,
                "API_KEY": self.airnow_api_key
            }

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data:
                return None

            pm25_aqi = None
            o3_aqi = None

            for obs in data:
                param = obs.get("ParameterName", "")
                aqi = obs.get("AQI")

                if param == "PM2.5" and aqi:
                    pm25_aqi = aqi
                elif param == "O3" and aqi:
                    o3_aqi = aqi

            aqi_value = max(pm25_aqi or 0, o3_aqi or 0)

            if aqi_value <= 50:
                aqi_cat = 1
            elif aqi_value <= 100:
                aqi_cat = 2
            elif aqi_value <= 150:
                aqi_cat = 3
            elif aqi_value <= 200:
                aqi_cat = 4
            else:
                aqi_cat = 5

            return AirQuality(
                aqi=aqi_cat,
                pm2_5=pm25_aqi,
                o3=o3_aqi,
                timestamp=datetime.now()
            )

        except Exception as e:
            logger.debug(f"Could not fetch air quality: {e}")
            return None

    async def refresh(self, force_refresh: bool = True):
        """Refresh weather cache."""
        await self.get_environmental_context(force_refresh=force_refresh)

    @property
    def cached_context(self) -> Optional[EnvironmentalContext]:
        """Get cached environmental context without fetching."""
        return self._cache

    def format_for_llm(self, context: Optional[EnvironmentalContext] = None) -> Dict[str, Any]:
        """
        Format environmental context for LLM consumption.

        Returns minimal, structured weather data suitable for LLM prompts.
        """
        if context is None:
            context = self._cache

        if not context:
            return {"status": "unavailable"}

        result = {
            "location": context.location,
            "temperature": round(context.weather.temperature, 1),
            "feels_like": round(context.weather.feels_like, 1),
            "humidity": context.weather.humidity,
            "condition": context.weather.description,
            "wind_speed": round(context.weather.wind_speed, 1),
            "clouds": context.weather.clouds,
        }

        if context.weather.uv_index is not None:
            result["uv_index"] = round(context.weather.uv_index, 1)

        if context.weather.precipitation is not None and context.weather.precipitation > 0:
            result["precipitation_inches"] = round(context.weather.precipitation, 2)

        # Sun context
        now = datetime.now()
        if now < context.sun.sunrise:
            result["sun_status"] = "before_sunrise"
        elif now > context.sun.sunset:
            result["sun_status"] = "after_sunset"
        else:
            result["sun_status"] = "daytime"

        # Air quality if available
        if context.air_quality:
            result["air_quality"] = context.air_quality.quality_text()

        return result

    def format_for_display(self, context: Optional[EnvironmentalContext] = None) -> str:
        """
        Format environmental context as text for display.
        """
        if context is None:
            context = self._cache

        if not context:
            return "Weather data not available."

        lines = [
            f"📍 {context.location}",
            f"",
            f"🌤️  Current Weather:",
            f"  • {context.weather.description}",
            f"  • Temperature: {context.weather.temperature:.1f}°F (feels like {context.weather.feels_like:.1f}°F)",
            f"  • Humidity: {context.weather.humidity}%",
            f"  • Wind: {context.weather.wind_speed:.1f} mph",
            f"  • Cloud cover: {context.weather.clouds}%",
        ]

        if context.weather.uv_index is not None:
            lines.append(f"  • UV Index: {context.weather.uv_index:.1f}")

        lines.extend([
            f"",
            f"🌅 Sun:",
            f"  • Sunrise: {context.sun.sunrise.strftime('%I:%M %p')}",
            f"  • Sunset: {context.sun.sunset.strftime('%I:%M %p')}",
        ])

        if context.air_quality:
            lines.extend([
                f"",
                f"💨 Air Quality: {context.air_quality.quality_text()}",
            ])

        if context.hourly_forecast:
            lines.extend([
                f"",
                f"📅 Next few hours:",
            ])
            for fc in context.hourly_forecast[:4]:
                time_str = fc.time.strftime("%I %p")
                lines.append(f"  • {time_str}: {fc.temperature:.0f}°F, {fc.condition}")

        return "\n".join(lines)

    def _read_weather_cache(self) -> Optional[EnvironmentalContext]:
        """Read weather from shared cache file"""
        try:
            if not WEATHER_CACHE_FILE.exists():
                return None

            with open(WEATHER_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                cached_at = datetime.fromisoformat(cache_data.get('cached_at'))
                age = datetime.now() - cached_at

                # Cache valid for 15 minutes
                if age < self._cache_duration:
                    # Reconstruct EnvironmentalContext from JSON
                    return EnvironmentalContext(**cache_data['data'])
                return None
        except Exception as e:
            logger.warning(f"Failed to read weather cache: {e}")
            return None

    def _write_weather_cache(self, context: EnvironmentalContext):
        """Write weather to shared cache file"""
        try:
            WEATHER_CACHE_FILE.parent.mkdir(exist_ok=True)
            cache_data = {
                'data': context.model_dump(mode='json'),
                'cached_at': context.cached_at.isoformat()
            }
            with open(WEATHER_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Failed to write weather cache: {e}")
