"""
Feature Extraction Service

Transforms raw events into higher-level features:
- Temperature/humidity trends
- Water usage deltas
- HVAC cycle duration
- Leak probability score
- Motion patterns
- Occupancy heuristics
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from .types import EventContext, Feature

logger = logging.getLogger(__name__)


class FeatureExtractionService:
    """
    Extracts high-level features from raw events.
    """

    def __init__(self):
        # Track HVAC state changes for cycle detection
        self.hvac_state_changes: Dict[str, List[tuple]] = defaultdict(list)

        # Track water flow events for usage calculation
        self.water_events: Dict[str, List[tuple]] = defaultdict(list)

        # Track motion events for occupancy
        self.motion_events: Dict[str, List[tuple]] = defaultdict(list)

        logger.info("FeatureExtractionService initialized")

    async def extract_features(self, context: EventContext) -> List[Feature]:
        """
        Extract high-level features from an event context.

        Returns:
            List of extracted features
        """
        features = []

        # Extract features based on event type
        if context.event_type in ["temperature", "temp"]:
            features.extend(await self._extract_temperature_features(context))

        elif context.event_type in ["humidity"]:
            features.extend(await self._extract_humidity_features(context))

        elif context.event_type in ["water_flow", "flow"]:
            features.extend(await self._extract_water_features(context))

        elif context.event_type in ["leak", "water_leak"]:
            features.extend(await self._extract_leak_features(context))

        elif context.event_type in ["hvac_state", "thermostat"]:
            features.extend(await self._extract_hvac_features(context))

        elif context.event_type in ["motion"]:
            features.extend(await self._extract_motion_features(context))

        return features

    async def _extract_temperature_features(self, context: EventContext) -> List[Feature]:
        """Extract temperature-related features"""
        features = []

        # Temperature trend feature
        if context.trend_1h is not None:
            trend_category = "stable"
            if context.trend_1h > 1.0:
                trend_category = "rising_fast"
            elif context.trend_1h > 0.3:
                trend_category = "rising"
            elif context.trend_1h < -1.0:
                trend_category = "falling_fast"
            elif context.trend_1h < -0.3:
                trend_category = "falling"

            features.append(Feature(
                name="temperature_trend",
                value=trend_category,
                timestamp=context.timestamp,
                device_id=context.device_id,
                zone_id=context.location
            ))

        # Comfort zone feature (assuming F)
        if isinstance(context.event_value, (int, float)):
            temp = context.event_value
            comfort_level = "comfortable"
            if temp < 65:
                comfort_level = "too_cold"
            elif temp > 78:
                comfort_level = "too_hot"

            features.append(Feature(
                name="comfort_level",
                value=comfort_level,
                timestamp=context.timestamp,
                device_id=context.device_id,
                zone_id=context.location
            ))

        return features

    async def _extract_humidity_features(self, context: EventContext) -> List[Feature]:
        """Extract humidity-related features"""
        features = []

        if isinstance(context.event_value, (int, float)):
            humidity = context.event_value

            humidity_level = "normal"
            if humidity < 30:
                humidity_level = "too_dry"
            elif humidity > 60:
                humidity_level = "too_humid"

            features.append(Feature(
                name="humidity_level",
                value=humidity_level,
                timestamp=context.timestamp,
                device_id=context.device_id,
                zone_id=context.location
            ))

        return features

    async def _extract_water_features(self, context: EventContext) -> List[Feature]:
        """Extract water usage features"""
        features = []

        # Track water flow events
        self.water_events[context.device_id].append((context.timestamp, context.event_value))

        # Keep only last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        self.water_events[context.device_id] = [
            (t, v) for t, v in self.water_events[context.device_id] if t >= cutoff
        ]

        # Calculate total usage in last hour
        hour_cutoff = datetime.now() - timedelta(hours=1)
        hour_events = [v for t, v in self.water_events[context.device_id] if t >= hour_cutoff]

        if hour_events and isinstance(hour_events[0], (int, float)):
            total_usage = sum(hour_events)

            usage_level = "normal"
            if total_usage > 100:  # gallons
                usage_level = "high"
            elif total_usage > 200:
                usage_level = "very_high"

            features.append(Feature(
                name="water_usage_1h",
                value=usage_level,
                timestamp=context.timestamp,
                device_id=context.device_id,
                zone_id=context.location
            ))

        return features

    async def _extract_leak_features(self, context: EventContext) -> List[Feature]:
        """Extract leak-related features"""
        features = []

        # Calculate leak probability based on anomaly score and value
        leak_detected = bool(context.event_value)

        leak_probability = 0.0
        if leak_detected:
            leak_probability = 1.0 if context.anomaly_score is None else max(0.8, context.anomaly_score)
        elif context.anomaly_score and context.anomaly_score > 0.7:
            leak_probability = context.anomaly_score

        features.append(Feature(
            name="leak_probability",
            value=leak_probability,
            timestamp=context.timestamp,
            device_id=context.device_id,
            zone_id=context.location
        ))

        return features

    async def _extract_hvac_features(self, context: EventContext) -> List[Feature]:
        """Extract HVAC cycle features"""
        features = []

        # Track state changes
        self.hvac_state_changes[context.device_id].append((context.timestamp, context.event_value))

        # Keep only last 48 hours
        cutoff = datetime.now() - timedelta(hours=48)
        self.hvac_state_changes[context.device_id] = [
            (t, v) for t, v in self.hvac_state_changes[context.device_id] if t >= cutoff
        ]

        # Calculate cycle duration if we have enough data
        if len(self.hvac_state_changes[context.device_id]) >= 4:
            # Find last on->off cycle
            states = self.hvac_state_changes[context.device_id]

            # Simple cycle detection
            cycles = []
            on_time = None
            for t, state in reversed(states):
                if state == "on" or state is True:
                    on_time = t
                elif (state == "off" or state is False) and on_time:
                    cycle_duration = (on_time - t).total_seconds() / 60  # minutes
                    cycles.append(cycle_duration)
                    on_time = None
                    if len(cycles) >= 3:
                        break

            if cycles:
                avg_cycle = sum(cycles) / len(cycles)

                cycle_category = "normal"
                if avg_cycle < 10:
                    cycle_category = "short"
                elif avg_cycle > 30:
                    cycle_category = "long"

                features.append(Feature(
                    name="hvac_cycle_duration",
                    value=cycle_category,
                    timestamp=context.timestamp,
                    device_id=context.device_id,
                    zone_id=context.location
                ))

        return features

    async def _extract_motion_features(self, context: EventContext) -> List[Feature]:
        """Extract motion/occupancy features"""
        features = []

        # Track motion events
        motion_detected = bool(context.event_value)
        self.motion_events[context.device_id].append((context.timestamp, motion_detected))

        # Keep only last 4 hours
        cutoff = datetime.now() - timedelta(hours=4)
        self.motion_events[context.device_id] = [
            (t, v) for t, v in self.motion_events[context.device_id] if t >= cutoff
        ]

        # Calculate occupancy heuristic
        hour_cutoff = datetime.now() - timedelta(hours=1)
        recent_motion = [v for t, v in self.motion_events[context.device_id] if t >= hour_cutoff]

        occupancy = "unknown"
        if len(recent_motion) > 5:
            occupancy = "occupied"
        elif len(recent_motion) == 0:
            occupancy = "vacant"
        else:
            occupancy = "possibly_occupied"

        features.append(Feature(
            name="occupancy",
            value=occupancy,
            timestamp=context.timestamp,
            device_id=context.device_id,
            zone_id=context.location
        ))

        return features
