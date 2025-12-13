"""
Sensor Fusion Engine

Combines multiple signal sources into unified context for reasoning:
- Z-Wave sensors (temp, humidity, leak, motion)
- Weather data (Met.no)
- Time/temporal context
- Behavioral patterns
- Historical baselines
- Week-over-week deltas
- Seasonal trends

No duplicate logic - integrates with existing EventIngestionService and River ML.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from .hil_types import (
    FusedContext, SensorSignal, TemporalContext, WeatherContext,
    BehavioralContext, SignalType
)
from .weather_client import WeatherClient, EnvironmentalContext

logger = logging.getLogger(__name__)


class SensorFusionEngine:
    """
    Fuses multiple sensor streams into unified context for reasoning.

    Architecture:
    1. Collects signals from all sources
    2. Normalizes and validates
    3. Computes temporal context
    4. Enriches with weather
    5. Calculates behavioral patterns
    6. Detects anomalies
    7. Produces FusedContext for downstream reasoning
    """

    def __init__(
        self,
        weather_service: Optional[WeatherClient] = None,
        event_buffer: Optional[Dict] = None,
        learning_engine=None,
        backend_url: str = "http://localhost:8080"
    ):
        self.weather_service = weather_service
        self.event_buffer = event_buffer or {}  # From EventIngestionService
        self.learning_engine = learning_engine  # River ML engine
        self.backend_url = backend_url

        # Room/zone mapping cache
        self.room_sensors: Dict[str, List[str]] = defaultdict(list)

        # Behavioral pattern cache
        self.behavioral_cache: Dict[str, Any] = {}

        # Signal buffer for fusion (last 100 signals)
        self.signal_buffer: List[SensorSignal] = []
        self.max_signal_buffer = 100

        # Location coordinates (for sun calculations)
        self.lat = 37.7749  # Default: San Francisco
        self.lon = -122.4194

        logger.info("SensorFusionEngine initialized")

    def set_location(self, lat: float, lon: float):
        """Set location for temporal calculations"""
        self.lat = lat
        self.lon = lon

    async def fuse(
        self,
        trigger_signal: Optional[SensorSignal] = None,
        include_weather: bool = True,
        include_behavioral: bool = True
    ) -> FusedContext:
        """
        Produce fused context from all available signals.

        Args:
            trigger_signal: The signal that triggered fusion (optional)
            include_weather: Include weather context
            include_behavioral: Include behavioral patterns

        Returns:
            FusedContext with all fused data
        """
        now = datetime.now()

        # 1. Temporal context
        temporal = self._compute_temporal_context(now)

        # 2. Weather context
        weather = None
        if include_weather and self.weather_service:
            weather = await self._get_weather_context()

        # 3. Indoor conditions from recent sensors
        indoor_temp, indoor_humidity = self._compute_indoor_conditions()

        # 4. Room-specific conditions
        room_conditions = self._compute_room_conditions()

        # 5. Behavioral context
        behavioral = None
        if include_behavioral:
            behavioral = self._compute_behavioral_context(now)

        # 6. Active alarms from backend
        active_leaks, active_smoke, active_co = await self._get_active_alarms()

        # 7. Anomaly signals
        anomalies = self._detect_anomalies()

        # 8. Baseline deviations and trends
        baseline_deviations = self._compute_baseline_deviations()
        trend_1h = self._compute_trends(hours=1)
        trend_24h = self._compute_trends(hours=24)
        week_delta = self._compute_week_over_week_delta()

        # 9. Build fused context
        fused = FusedContext(
            trigger_signal=trigger_signal,
            temporal=temporal,
            weather=weather,
            indoor_temp=indoor_temp,
            indoor_humidity=indoor_humidity,
            room_conditions=room_conditions,
            behavioral=behavioral,
            active_leaks=active_leaks,
            active_smoke=active_smoke,
            active_co=active_co,
            anomalies=anomalies,
            baseline_deviations=baseline_deviations,
            trend_1h=trend_1h,
            trend_24h=trend_24h,
            week_over_week_delta=week_delta,
            signal_count=len(self.signal_buffer),
            fusion_confidence=self._compute_fusion_confidence(),
            fusion_timestamp=now
        )

        return fused

    def add_signal(self, signal: SensorSignal):
        """Add a signal to the fusion buffer"""
        self.signal_buffer.append(signal)

        # Trim buffer if too large
        if len(self.signal_buffer) > self.max_signal_buffer:
            self.signal_buffer = self.signal_buffer[-self.max_signal_buffer:]

        # Update room mapping
        room = signal.metadata.get("location", "unknown")
        if signal.device_id not in self.room_sensors[room]:
            self.room_sensors[room].append(signal.device_id)

    def _compute_temporal_context(self, now: datetime) -> TemporalContext:
        """Compute time-based context"""
        hour = now.hour
        dow = now.weekday()
        is_weekend = dow >= 5

        # Compute sun elevation
        sun_elevation, sunrise_offset, sunset_offset = self._compute_sun_position(now)

        # Determine if daytime
        is_daytime = sun_elevation > 0.1

        # Determine season (Northern hemisphere)
        month = now.month
        if month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        elif month in [9, 10, 11]:
            season = "fall"
        else:
            season = "winter"

        return TemporalContext(
            timestamp=now,
            hour_of_day=hour,
            day_of_week=dow,
            is_weekend=is_weekend,
            is_daytime=is_daytime,
            sun_elevation=sun_elevation,
            sunrise_offset_hours=sunrise_offset,
            sunset_offset_hours=sunset_offset,
            season=season
        )

    def _compute_sun_position(self, now: datetime) -> Tuple[float, float, float]:
        """
        Compute sun elevation and offsets from sunrise/sunset.

        Returns: (elevation 0-1, hours since sunrise, hours until sunset)
        """
        day_of_year = now.timetuple().tm_yday

        # Solar declination
        declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))

        lat_rad = math.radians(self.lat)
        dec_rad = math.radians(declination)

        cos_hour_angle = -math.tan(lat_rad) * math.tan(dec_rad)

        # Handle polar day/night
        if cos_hour_angle > 1:
            return 0.0, 0.0, 0.0  # Polar night
        elif cos_hour_angle < -1:
            return 1.0, 12.0, 12.0  # Polar day

        hour_angle = math.degrees(math.acos(cos_hour_angle))

        # Solar noon offset
        solar_noon_offset = -self.lon / 15.0

        sunrise_hour = 12 - (hour_angle / 15.0) + solar_noon_offset
        sunset_hour = 12 + (hour_angle / 15.0) + solar_noon_offset

        # Clamp
        sunrise_hour = max(0, min(23.99, sunrise_hour))
        sunset_hour = max(0, min(23.99, sunset_hour))

        current_hour = now.hour + now.minute / 60.0

        # Elevation (0 at horizon, 1 at noon)
        if current_hour < sunrise_hour or current_hour > sunset_hour:
            elevation = 0.0
        else:
            day_progress = (current_hour - sunrise_hour) / (sunset_hour - sunrise_hour)
            elevation = 4 * day_progress * (1 - day_progress)

        sunrise_offset = current_hour - sunrise_hour
        sunset_offset = sunset_hour - current_hour

        return elevation, sunrise_offset, sunset_offset

    async def _get_weather_context(self) -> Optional[WeatherContext]:
        """Get weather context from weather service"""
        if not self.weather_service:
            return None

        try:
            # Use cached context (never block on API)
            env = self.weather_service.cached_context
            if not env:
                return None

            return WeatherContext(
                temperature=env.weather.temperature,
                feels_like=env.weather.feels_like,
                humidity=env.weather.humidity,
                pressure=env.weather.pressure,
                wind_speed=env.weather.wind_speed,
                description=env.weather.description,
                is_stormy="storm" in env.weather.description.lower() or "rain" in env.weather.description.lower(),
                is_hot=env.weather.temperature > 80,
                is_cold=env.weather.temperature < 50,
                is_humid=env.weather.humidity > 70,
                aqi=env.air_quality.aqi if env.air_quality else None
            )
        except Exception as e:
            logger.warning(f"Failed to get weather context: {e}")
            return None

    def _compute_indoor_conditions(self) -> Tuple[Optional[float], Optional[float]]:
        """Compute aggregate indoor temperature and humidity"""
        temps = []
        humidities = []

        # Get recent signals
        cutoff = datetime.now() - timedelta(minutes=30)

        for signal in self.signal_buffer:
            if signal.timestamp < cutoff:
                continue

            if signal.signal_type == SignalType.SENSOR_READING:
                event_type = signal.metadata.get("event_type", "")

                if event_type in ["temperature", "temp"]:
                    if isinstance(signal.value, (int, float)):
                        temps.append(float(signal.value))
                elif event_type == "humidity":
                    if isinstance(signal.value, (int, float)):
                        humidities.append(float(signal.value))

        # Average
        avg_temp = sum(temps) / len(temps) if temps else None
        avg_humidity = sum(humidities) / len(humidities) if humidities else None

        return avg_temp, avg_humidity

    def _compute_room_conditions(self) -> Dict[str, Dict[str, Any]]:
        """Compute per-room conditions"""
        room_data: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        cutoff = datetime.now() - timedelta(minutes=30)

        for signal in self.signal_buffer:
            if signal.timestamp < cutoff:
                continue

            room = signal.metadata.get("location", "unknown")
            event_type = signal.metadata.get("event_type", "")

            if isinstance(signal.value, (int, float)):
                room_data[room][event_type].append(float(signal.value))

        # Average per room
        result = {}
        for room, metrics in room_data.items():
            result[room] = {}
            for metric, values in metrics.items():
                if values:
                    result[room][metric] = sum(values) / len(values)
                    result[room][f"{metric}_count"] = len(values)

        return result

    def _compute_behavioral_context(self, now: datetime) -> BehavioralContext:
        """Compute behavioral context from patterns"""
        # Find last motion event
        last_motion = None
        for signal in reversed(self.signal_buffer):
            if signal.metadata.get("event_type") == "motion":
                last_motion = signal.timestamp
                break

        last_motion_minutes = None
        if last_motion:
            last_motion_minutes = int((now - last_motion).total_seconds() / 60)

        # Determine activity level based on motion
        if last_motion_minutes is None:
            activity_level = "away"
            occupancy_prob = 0.3
        elif last_motion_minutes < 5:
            activity_level = "active"
            occupancy_prob = 0.95
        elif last_motion_minutes < 30:
            activity_level = "resting"
            occupancy_prob = 0.8
        elif last_motion_minutes < 120:
            activity_level = "resting"
            occupancy_prob = 0.6
        else:
            activity_level = "away"
            occupancy_prob = 0.2

        # Time-based adjustments
        hour = now.hour
        if 0 <= hour < 6:
            if activity_level == "resting":
                activity_level = "asleep"
            occupancy_prob = min(occupancy_prob + 0.2, 1.0) if occupancy_prob > 0.3 else occupancy_prob

        return BehavioralContext(
            typical_wake_time="07:00",  # Would learn from patterns
            typical_sleep_time="23:00",
            occupancy_probability=occupancy_prob,
            activity_level=activity_level,
            last_motion_minutes_ago=last_motion_minutes,
            routine_deviation_score=0.0  # Would compute from learned patterns
        )

    async def _get_active_alarms(self) -> Tuple[List[str], List[str], List[str]]:
        """Get active alarms from backend"""
        import httpx

        active_leaks = []
        active_smoke = []
        active_co = []

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.backend_url}/api/incidents?status=active")
                if resp.status_code == 200:
                    incidents = resp.json()
                    for inc in incidents:
                        inc_type = inc.get("type", "").lower()
                        device_id = inc.get("device_id", "unknown")

                        if "leak" in inc_type or "water" in inc_type:
                            active_leaks.append(device_id)
                        elif "smoke" in inc_type:
                            active_smoke.append(device_id)
                        elif "co" in inc_type or "carbon" in inc_type:
                            active_co.append(device_id)
        except Exception as e:
            logger.warning(f"Failed to fetch active alarms: {e}")

        return active_leaks, active_smoke, active_co

    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in recent signals"""
        anomalies = []

        # Check recent signals for high anomaly scores
        cutoff = datetime.now() - timedelta(minutes=15)

        for signal in self.signal_buffer:
            if signal.timestamp < cutoff:
                continue

            anomaly_score = signal.metadata.get("anomaly_score", 0.0)
            if anomaly_score > 0.7:
                anomalies.append({
                    "device_id": signal.device_id,
                    "sensor_id": signal.sensor_id,
                    "type": signal.metadata.get("event_type", "unknown"),
                    "value": signal.value,
                    "score": anomaly_score,
                    "timestamp": signal.timestamp.isoformat()
                })

        return anomalies

    def _compute_baseline_deviations(self) -> Dict[str, float]:
        """Compute how much current values deviate from baselines"""
        deviations = {}

        if not self.learning_engine:
            return deviations

        # Get latest value per device/metric
        latest: Dict[str, Dict[str, float]] = {}
        for signal in reversed(self.signal_buffer):
            device_id = signal.device_id
            metric = signal.metadata.get("event_type", "unknown")

            if isinstance(signal.value, (int, float)):
                key = f"{device_id}_{metric}"
                if key not in latest:
                    latest[key] = float(signal.value)

        # Compare to baselines
        for key, value in latest.items():
            parts = key.rsplit("_", 1)
            if len(parts) == 2:
                device_id, metric = parts
                if device_id in self.learning_engine.baseline_models:
                    if metric in self.learning_engine.baseline_models[device_id]:
                        mean_model, var_model = self.learning_engine.baseline_models[device_id][metric]
                        mean_val = mean_model.get()
                        var_val = var_model.get()

                        if mean_val is not None and var_val is not None and var_val > 0:
                            stddev = math.sqrt(var_val)
                            z_score = (value - mean_val) / stddev if stddev > 0 else 0
                            deviations[key] = z_score

        return deviations

    def _compute_trends(self, hours: int) -> Dict[str, float]:
        """Compute trends (change rate) over given time period"""
        trends = {}
        cutoff = datetime.now() - timedelta(hours=hours)

        # Group signals by device/metric
        grouped: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)

        for signal in self.signal_buffer:
            if signal.timestamp < cutoff:
                continue

            if isinstance(signal.value, (int, float)):
                key = f"{signal.device_id}_{signal.metadata.get('event_type', 'unknown')}"
                grouped[key].append((signal.timestamp, float(signal.value)))

        # Compute trend for each
        for key, readings in grouped.items():
            if len(readings) < 2:
                continue

            readings.sort(key=lambda x: x[0])
            first_time, first_val = readings[0]
            last_time, last_val = readings[-1]

            time_diff_hours = (last_time - first_time).total_seconds() / 3600
            if time_diff_hours > 0:
                trend = (last_val - first_val) / time_diff_hours
                trends[key] = trend

        return trends

    def _compute_week_over_week_delta(self) -> Dict[str, float]:
        """
        Compute week-over-week delta for key metrics.

        This would require historical data storage - placeholder for now.
        """
        # TODO: Integrate with historical storage
        return {}

    def _compute_fusion_confidence(self) -> float:
        """Compute overall confidence in fused data"""
        if not self.signal_buffer:
            return 0.0

        # Factors affecting confidence:
        # 1. Number of recent signals
        # 2. Signal freshness
        # 3. Signal diversity (multiple device types)

        now = datetime.now()
        recent_cutoff = now - timedelta(minutes=5)

        recent_count = sum(1 for s in self.signal_buffer if s.timestamp > recent_cutoff)
        freshness_score = min(1.0, recent_count / 10)

        # Device diversity
        devices = set(s.device_id for s in self.signal_buffer if s.timestamp > recent_cutoff)
        diversity_score = min(1.0, len(devices) / 5)

        # Signal confidence average
        confidences = [s.confidence for s in self.signal_buffer if s.timestamp > recent_cutoff]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Combined score
        confidence = (freshness_score * 0.3 + diversity_score * 0.3 + avg_confidence * 0.4)

        return min(1.0, max(0.0, confidence))

    def format_for_llm(self, context: FusedContext) -> str:
        """Format fused context as concise text for LLM"""
        lines = []

        lines.append(f"Time: {context.temporal.timestamp.strftime('%I:%M %p %A')}")
        lines.append(f"Sun: {'Daytime' if context.temporal.is_daytime else 'Night'} (elevation: {context.temporal.sun_elevation:.1%})")

        if context.weather:
            lines.append(f"Outside: {context.weather.temperature:.0f}°F, {context.weather.description}")
            if context.weather.is_stormy:
                lines.append("⚠️ Stormy conditions")

        if context.indoor_temp:
            lines.append(f"Indoor temp: {context.indoor_temp:.1f}°F")
        if context.indoor_humidity:
            lines.append(f"Indoor humidity: {context.indoor_humidity:.0f}%")

        if context.room_conditions:
            lines.append("Room conditions:")
            for room, conditions in context.room_conditions.items():
                cond_str = ", ".join(f"{k}: {v:.1f}" for k, v in conditions.items() if not k.endswith("_count"))
                lines.append(f"  {room}: {cond_str}")

        if context.behavioral:
            lines.append(f"Occupancy: {context.behavioral.activity_level} ({context.behavioral.occupancy_probability:.0%} probability)")

        if context.active_leaks:
            lines.append(f"⚠️ ACTIVE LEAKS: {', '.join(context.active_leaks)}")
        if context.active_smoke:
            lines.append(f"🔥 SMOKE DETECTED: {', '.join(context.active_smoke)}")
        if context.active_co:
            lines.append(f"⚠️ CO DETECTED: {', '.join(context.active_co)}")

        if context.anomalies:
            lines.append(f"Anomalies detected: {len(context.anomalies)}")
            for a in context.anomalies[:3]:
                lines.append(f"  - {a['device_id']}: {a['type']}={a['value']} (score: {a['score']:.2f})")

        return "\n".join(lines)
