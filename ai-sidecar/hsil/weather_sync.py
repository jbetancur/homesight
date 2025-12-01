"""
Weather Sync Service

Background service that periodically refreshes weather data.
Prevents per-chat weather fetches and ensures cached weather context.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WeatherSyncService:
    """
    Background service for periodic weather updates.

    Runs every 5-10 minutes to refresh weather cache.
    Ensures conversational agent never blocks on weather API calls.
    """

    def __init__(self, weather_service, refresh_interval_minutes: int = 10):
        """
        Initialize weather sync service.

        Args:
            weather_service: WeatherService instance
            refresh_interval_minutes: Minutes between refreshes (default: 10)
        """
        self.weather_service = weather_service
        self.refresh_interval = timedelta(minutes=refresh_interval_minutes)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_refresh: Optional[datetime] = None

    async def start(self):
        """Start background weather sync"""
        if self._running:
            logger.warning("WeatherSyncService already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info(f"WeatherSyncService started (refresh every {self.refresh_interval.total_seconds()/60:.1f} minutes)")

    async def stop(self):
        """Stop background weather sync"""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("WeatherSyncService stopped")

    async def _sync_loop(self):
        """Background sync loop"""
        try:
            # Immediate first refresh
            await self._refresh_weather()

            while self._running:
                await asyncio.sleep(self.refresh_interval.total_seconds())

                if self._running:
                    await self._refresh_weather()

        except asyncio.CancelledError:
            logger.info("Weather sync loop cancelled")
        except Exception as e:
            logger.error(f"Weather sync loop error: {e}")

    async def _refresh_weather(self):
        """Refresh weather data"""
        try:
            logger.debug("Refreshing weather data...")
            await self.weather_service.refresh(force_refresh=True)
            self._last_refresh = datetime.now()
            logger.info(f"Weather data refreshed successfully at {self._last_refresh.isoformat()}")

        except Exception as e:
            logger.error(f"Failed to refresh weather: {e}")

    def get_status(self) -> dict:
        """
        Get sync service status.

        Returns:
            Dictionary with status information
        """
        return {
            "running": self._running,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "refresh_interval_minutes": self.refresh_interval.total_seconds() / 60,
            "next_refresh_in_seconds": (
                (self._last_refresh + self.refresh_interval - datetime.now()).total_seconds()
                if self._last_refresh
                else 0
            ),
        }
