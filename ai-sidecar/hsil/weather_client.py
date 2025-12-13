"""
Weather client - fetches weather from Go API
"""
import logging
import os
from typing import Optional
from datetime import datetime
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WeatherData(BaseModel):
    """Current weather conditions"""
    temperature: float
    feels_like: float
    humidity: int
    pressure: int
    description: str
    icon: str
    wind_speed: float
    wind_direction: Optional[float] = None
    clouds: int
    visibility: int
    uv_index: Optional[float] = None
    precipitation: Optional[float] = None
    timestamp: datetime


class SunTimes(BaseModel):
    """Sunrise and sunset times"""
    sunrise: datetime
    sunset: datetime
    day_length_hours: float


class EnvironmentalContext(BaseModel):
    """Complete environmental context from Go API"""
    weather: WeatherData
    sun: SunTimes
    location: str
    cached_at: datetime


class WeatherClient:
    """Client for fetching weather from Go API"""

    def __init__(self, api_url: str = None):
        if api_url is None:
            api_url = os.getenv("HOMESIGHT_API_URL", "http://localhost:8080")
        self.api_url = api_url.rstrip("/")
        self._cached_context: Optional[EnvironmentalContext] = None

    async def get_environmental_context(self, force_refresh: bool = False) -> Optional[EnvironmentalContext]:
        """Fetch weather from Go API"""
        if not force_refresh and self._cached_context:
            # Use cached if less than 5 minutes old
            age = datetime.now() - self._cached_context.cached_at
            if age.total_seconds() < 300:
                return self._cached_context

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}/api/weather")
                response.raise_for_status()
                data = response.json()

                context = EnvironmentalContext(**data)
                self._cached_context = context
                logger.debug(f"Fetched weather from Go API: {context.location}, {context.weather.temperature}°F")
                return context
        except Exception as e:
            logger.warning(f"Failed to fetch weather from Go API: {e}")
            return self._cached_context

    @property
    def cached_context(self) -> Optional[EnvironmentalContext]:
        """Get cached weather without fetching"""
        return self._cached_context

    async def refresh(self, force_refresh: bool = True):
        """Refresh weather cache"""
        await self.get_environmental_context(force_refresh=force_refresh)
