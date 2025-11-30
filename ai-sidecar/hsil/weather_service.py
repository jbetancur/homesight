"""
HSIL Weather Service

Fetches and caches external environmental data:
- Weather conditions
- Temperature, humidity, pressure
- Sunrise/sunset times
- Air quality index
"""

import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
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
    Service for fetching external environmental data.

    Uses OpenWeatherMap API (free tier):
    - Current weather
    - Air pollution
    - Geocoding for location

    Caches data for 15 minutes to reduce API calls.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        lat: float = 37.7749,  # Default: San Francisco
        lon: float = -122.4194,
        location_name: str = "San Francisco, CA"
    ):
        """
        Initialize weather service.

        Args:
            api_key: OpenWeatherMap API key (or use OPENWEATHER_API_KEY env var)
            lat: Latitude
            lon: Longitude
            location_name: Human-readable location name
        """
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.lat = lat
        self.lon = lon
        self.location_name = location_name

        # Cache
        self._cache: Optional[EnvironmentalContext] = None
        self._cache_duration = timedelta(minutes=15)

        if not self.api_key:
            logger.warning(
                "No OpenWeatherMap API key configured. "
                "Set OPENWEATHER_API_KEY environment variable. "
                "Get a free key at https://openweathermap.org/api"
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch weather data
                weather_data = await self._fetch_weather(client)

                # Fetch air quality
                air_quality = await self._fetch_air_quality(client)

                # Build context
                context = EnvironmentalContext(
                    weather=weather_data,
                    sun=self._calculate_sun_times(weather_data),
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

    async def _fetch_weather(self, client: httpx.AsyncClient) -> WeatherData:
        """Fetch current weather from OpenWeatherMap"""
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "imperial"  # Fahrenheit
        }

        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        return WeatherData(
            temperature=data["main"]["temp"],
            feels_like=data["main"]["feels_like"],
            humidity=data["main"]["humidity"],
            pressure=data["main"]["pressure"],
            description=data["weather"][0]["description"],
            icon=data["weather"][0]["icon"],
            wind_speed=data["wind"]["speed"],
            clouds=data["clouds"]["all"],
            visibility=data.get("visibility", 10000),
            timestamp=datetime.fromtimestamp(data["dt"])
        )

    def _calculate_sun_times(self, weather: WeatherData) -> SunTimes:
        """Calculate sunrise/sunset times (simplified - would use API in production)"""
        # In a real implementation, this would come from the weather API
        # For now, use rough estimates
        now = datetime.now()
        sunrise = now.replace(hour=6, minute=30, second=0, microsecond=0)
        sunset = now.replace(hour=18, minute=30, second=0, microsecond=0)

        day_length = (sunset - sunrise).total_seconds() / 3600

        return SunTimes(
            sunrise=sunrise,
            sunset=sunset,
            day_length_hours=day_length
        )

    async def _fetch_air_quality(self, client: httpx.AsyncClient) -> Optional[AirQuality]:
        """Fetch air quality from OpenWeatherMap"""
        try:
            url = "https://api.openweathermap.org/data/2.5/air_pollution"
            params = {
                "lat": self.lat,
                "lon": self.lon,
                "appid": self.api_key
            }

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if "list" not in data or len(data["list"]) == 0:
                return None

            pollution = data["list"][0]
            components = pollution.get("components", {})

            return AirQuality(
                aqi=pollution["main"]["aqi"],
                pm2_5=components.get("pm2_5"),
                pm10=components.get("pm10"),
                o3=components.get("o3"),
                no2=components.get("no2"),
                timestamp=datetime.fromtimestamp(pollution["dt"])
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
            f"🌤️  Weather:",
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
                f"💨 Air Quality: {context.air_quality.quality_text()} (AQI {context.air_quality.aqi})",
            ])
            if context.air_quality.pm2_5:
                lines.append(f"  • PM2.5: {context.air_quality.pm2_5:.1f} μg/m³")

        return "\n".join(lines)
