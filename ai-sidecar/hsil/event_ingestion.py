"""
Event Ingestion Layer

Subscribes to HomeSight MQTT events and normalizes them into EventContext objects.
Enriches events with trends, anomalies, and context.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import asyncio
from collections import deque
import statistics

from .types import EventContext

logger = logging.getLogger(__name__)


class EventIngestionService:
    """
    Ingests raw MQTT events and transforms them into enriched EventContext objects.
    
    Includes erratic sensor detection to identify potential sensor malfunctions
    (e.g., rapid-fire triggers that indicate noise/malfunction vs. real events).
    """

    # Erratic detection thresholds
    ERRATIC_WINDOW_SECONDS = 60  # Time window to count rapid events
    ERRATIC_THRESHOLD_COUNT = 3  # Number of events in window to flag as erratic
    ERRATIC_COOLDOWN_SECONDS = 300  # Don't flag same sensor as erratic within this period

    def __init__(self, db_path: str = "/var/lib/homesight/homesight.db"):
        self.db_path = db_path
        # In-memory circular buffer for quick trend calculation
        # device_id -> sensor_id -> deque of (timestamp, value)
        self.event_buffer: Dict[str, Dict[str, deque]] = {}
        self.max_buffer_size = 1000  # Keep last 1000 events per sensor
        
        # Track erratic sensor detections to prevent spam
        # device_id:sensor_id -> last erratic detection timestamp
        self._erratic_cooldowns: Dict[str, datetime] = {}

        logger.info(f"EventIngestionService initialized with db_path={db_path}")

    async def ingest_mqtt_event(
        self,
        device_id: str,
        sensor_id: str,
        event_type: str,
        value: Any,
        location: str = "Unknown",
        device_type: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ) -> EventContext:
        """
        Ingest a raw MQTT event and transform it into an enriched EventContext.

        Args:
            device_id: Device identifier
            sensor_id: Sensor identifier
            event_type: Type of event (temperature, humidity, leak, etc.)
            value: Event value
            location: Zone/location name
            device_type: Type of device
            metadata: Additional metadata

        Returns:
            EventContext with enriched data
        """
        timestamp = datetime.now()

        # Store in buffer for trend calculation
        await self._add_to_buffer(device_id, sensor_id, timestamp, value)

        # Calculate trends
        trend_1h = await self._calculate_trend(device_id, sensor_id, hours=1)
        trend_24h = await self._calculate_trend(device_id, sensor_id, hours=24)

        # Calculate anomaly score (simple z-score based detection for now)
        anomaly_score = await self._calculate_anomaly(device_id, sensor_id, value)

        context = EventContext(
            device_id=device_id,
            sensor_id=sensor_id,
            event_type=event_type,
            event_value=value,
            location=location,
            device_type=device_type,
            timestamp=timestamp,
            trend_1h=trend_1h,
            trend_24h=trend_24h,
            anomaly_score=anomaly_score,
            metadata=metadata or {}
        )

        # Check for erratic sensor behavior (rapid-fire triggers)
        is_erratic, event_frequency = await self._check_erratic_behavior(
            device_id, sensor_id, timestamp, event_type
        )
        if is_erratic:
            context.metadata["is_erratic"] = True
            context.metadata["event_frequency_per_minute"] = event_frequency
            context.metadata["erratic_reason"] = (
                f"Sensor triggered {event_frequency:.1f} times/min "
                f"(threshold: {self.ERRATIC_THRESHOLD_COUNT}/min). "
                "This may indicate sensor malfunction or environmental interference."
            )
            logger.warning(
                f"ERRATIC SENSOR DETECTED: {device_id}/{sensor_id} - "
                f"{event_frequency:.1f} events/min in {event_type}"
            )

        logger.debug(
            f"Ingested event: device={device_id}, sensor={sensor_id}, "
            f"type={event_type}, value={value}, anomaly={(f'{anomaly_score:.2f}' if anomaly_score is not None else 'N/A')}"
            f"{', ERRATIC' if is_erratic else ''}"
        )

        return context

    async def _add_to_buffer(self, device_id: str, sensor_id: str, timestamp: datetime, value: Any):
        """Add event to in-memory buffer for trend calculation"""
        if device_id not in self.event_buffer:
            self.event_buffer[device_id] = {}

        if sensor_id not in self.event_buffer[device_id]:
            self.event_buffer[device_id][sensor_id] = deque(maxlen=self.max_buffer_size)

        # Only store numeric values for trend calculation
        if isinstance(value, (int, float)):
            self.event_buffer[device_id][sensor_id].append((timestamp, float(value)))

    async def _calculate_trend(
        self,
        device_id: str,
        sensor_id: str,
        hours: int
    ) -> Optional[float]:
        """
        Calculate trend (rate of change) over the specified time period.
        Returns change per hour.
        """
        if device_id not in self.event_buffer:
            return None
        if sensor_id not in self.event_buffer[device_id]:
            return None

        buffer = self.event_buffer[device_id][sensor_id]
        if len(buffer) < 2:
            return None

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_events = [(t, v) for t, v in buffer if t >= cutoff_time]

        if len(recent_events) < 2:
            return None

        # Simple linear regression to get trend
        # Calculate change per hour
        first_time, first_value = recent_events[0]
        last_time, last_value = recent_events[-1]

        time_diff = (last_time - first_time).total_seconds() / 3600  # hours
        if time_diff == 0:
            return None

        value_diff = last_value - first_value
        trend = value_diff / time_diff

        return trend

    async def _calculate_anomaly(
        self,
        device_id: str,
        sensor_id: str,
        value: Any
    ) -> Optional[float]:
        """
        Calculate anomaly score (0-1) based on statistical deviation.
        Uses simple z-score method for now.
        """
        if not isinstance(value, (int, float)):
            return None

        if device_id not in self.event_buffer:
            return None
        if sensor_id not in self.event_buffer[device_id]:
            return None

        buffer = self.event_buffer[device_id][sensor_id]
        if len(buffer) < 10:  # Need enough data for statistics
            return 0.0

        values = [v for _, v in buffer]

        try:
            mean = statistics.mean(values)
            stdev = statistics.stdev(values)

            if stdev == 0:
                return 0.0

            z_score = abs((value - mean) / stdev)

            # Convert z-score to 0-1 probability
            # z=0 -> 0, z=3 -> 0.997, z=4 -> 0.9999
            anomaly_score = min(1.0, z_score / 4.0)

            return anomaly_score
        except Exception as e:
            logger.warning(f"Error calculating anomaly score: {e}")
            return None

    async def _check_erratic_behavior(
        self,
        device_id: str,
        sensor_id: str,
        timestamp: datetime,
        event_type: str
    ) -> tuple[bool, float]:
        """
        Check if sensor is exhibiting erratic behavior (rapid-fire triggers).
        
        This detects sensor malfunctions like:
        - Water leak sensors triggering multiple times per second
        - Motion sensors with constant false positives
        - Contact sensors chattering
        
        Returns:
            (is_erratic, event_frequency_per_minute)
        """
        # Only check for binary/event sensors (leak, motion, contact, smoke, etc.)
        erratic_sensor_types = {"leak", "motion", "contact", "smoke", "co", "door", "window", "tamper"}
        if event_type.lower() not in erratic_sensor_types:
            return False, 0.0
        
        # Get event buffer for this sensor
        if device_id not in self.event_buffer or sensor_id not in self.event_buffer[device_id]:
            return False, 0.0
        
        buffer = self.event_buffer[device_id][sensor_id]
        if len(buffer) < self.ERRATIC_THRESHOLD_COUNT:
            return False, 0.0
        
        # Count events within the erratic window
        cutoff = timestamp - timedelta(seconds=self.ERRATIC_WINDOW_SECONDS)
        recent_events = [t for t, _ in buffer if t >= cutoff]
        event_count = len(recent_events)
        
        # Calculate frequency per minute
        event_frequency = event_count * (60.0 / self.ERRATIC_WINDOW_SECONDS)
        
        # Check if exceeds threshold
        if event_count >= self.ERRATIC_THRESHOLD_COUNT:
            # Check cooldown to prevent spamming erratic detection
            cooldown_key = f"{device_id}:{sensor_id}"
            last_erratic = self._erratic_cooldowns.get(cooldown_key)
            
            if last_erratic and (timestamp - last_erratic).total_seconds() < self.ERRATIC_COOLDOWN_SECONDS:
                # Already flagged recently, don't flag again but return the frequency
                return False, event_frequency
            
            # Mark as erratic
            self._erratic_cooldowns[cooldown_key] = timestamp
            return True, event_frequency
        
        return False, event_frequency

    def get_erratic_sensors(self) -> List[Dict[str, Any]]:
        """
        Get list of sensors that have been flagged as erratic recently.
        
        Useful for diagnostics and UI display.
        """
        now = datetime.now()
        active_erratic = []
        
        for key, timestamp in self._erratic_cooldowns.items():
            if (now - timestamp).total_seconds() < self.ERRATIC_COOLDOWN_SECONDS:
                device_id, sensor_id = key.split(":", 1)
                active_erratic.append({
                    "device_id": device_id,
                    "sensor_id": sensor_id,
                    "flagged_at": timestamp.isoformat(),
                    "age_seconds": (now - timestamp).total_seconds()
                })
        
        return active_erratic

    async def get_device_context(self, device_id: str) -> Dict[str, Any]:
        """
        Get current context for a device (all sensors).
        """
        if device_id not in self.event_buffer:
            return {}

        context = {}
        for sensor_id, buffer in self.event_buffer[device_id].items():
            if buffer:
                latest_time, latest_value = buffer[-1]
                context[sensor_id] = {
                    "value": latest_value,
                    "timestamp": latest_time.isoformat(),
                    "trend_1h": await self._calculate_trend(device_id, sensor_id, 1),
                    "trend_24h": await self._calculate_trend(device_id, sensor_id, 24),
                }

        return context
