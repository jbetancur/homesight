"""
HSIL River ML Engine

Production-grade online learning using River (https://riverml.xyz/).
No LLMs or neural nets. Fully local, incremental models.

Models:
- ComfortModel: Predict preferred indoor conditions based on time, weather, and patterns
- AnomalyModel: Detect outliers per-device using HalfSpaceTrees
- RoutineModel: Cluster events by time-of-day, location, weather conditions
- OccupancyModel: Predict if area is occupied from sensor mix + weather
- BaselineModel: Running mean/variance baselines per sensor metric
"""

import logging
import sqlite3
import json
import pickle
import math
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict

from river import linear_model, anomaly, cluster, stats, optim, metrics

from .types import EventContext, BehaviorPrediction, BehaviorPredictionType
from .weather_client import EnvironmentalContext

logger = logging.getLogger(__name__)


class HSILRiverLearningEngine:
    """
    River-based online learning engine for HSIL.
    All models update incrementally on each event.
    """

    def __init__(
        self,
        db_path: str = "/var/lib/homesight/hsil_memory.db",
        weather_service=None,
        erratic_decay_half_life: float = 300.0,
        erratic_threshold: float = 0.5,
        erratic_list_threshold: float = 0.3
    ):
        self.db_path = db_path
        self.weather_service = weather_service

        # Erratic behavior configuration
        self.erratic_decay_half_life = erratic_decay_half_life
        self.erratic_threshold = erratic_threshold
        self.erratic_list_threshold = erratic_list_threshold

        # Weather context cache
        self._env_context: Optional[EnvironmentalContext] = None

        # Initialize models
        self._init_models()

        # Initialize database
        self._init_db()

        # Load persisted models
        self._load_models()

        logger.info(
            f"HSILRiverLearningEngine initialized with River models "
            f"(erratic_decay_half_life={erratic_decay_half_life}s, "
            f"threshold={erratic_threshold}, list_threshold={erratic_list_threshold})"
        )

    def _init_models(self):
        """Initialize all River models"""

        # Comfort model: Linear regression for preferred conditions
        # Features: temp, humidity, hour_sin, hour_cos, dow_sin, dow_cos,
        #           external_temp, feels_like, wind_speed, aqi, sun_elevation
        self.comfort_model = linear_model.LinearRegression(
            optimizer=optim.SGD(lr=0.01)
        )

        # Anomaly models: One HalfSpaceTrees per device
        # Per-device anomaly detection
        self.anomaly_models: Dict[str, anomaly.HalfSpaceTrees] = defaultdict(
            lambda: anomaly.HalfSpaceTrees(n_trees=10, height=8, window_size=250)
        )

        # Routine model: KMeans clustering for activity patterns
        # Features: hour_sin, hour_cos, dow_sin, dow_cos, sensor_type_encoded,
        #           location_encoded, sunrise_offset, sunset_offset, weather_category
        self.routine_model = cluster.KMeans(
            n_clusters=6,
            halflife=0.5,
            sigma=3,
            seed=42
        )

        # Occupancy model: Logistic regression
        # Features: motion_count, door_events, temp_variance, humidity_variance,
        #           time_features, weather_features
        self.occupancy_model = linear_model.LogisticRegression(
            optimizer=optim.SGD(lr=0.05)
        )

        # Baseline models: Running mean/variance per device+metric
        self.baseline_models: Dict[str, Dict[str, Tuple[stats.Mean, stats.Var]]] = defaultdict(dict)

        # Event frequency models: Track event rate per device for erratic detection
        # Stores (event_count_model, inter_event_time_model) per device
        self.frequency_models: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "event_count": stats.Mean(),  # Mean events per hour
                "inter_event_time": stats.Mean(),  # Mean seconds between events
                "inter_event_var": stats.Var(),  # Variance in inter-event time
                "last_event_time": None,
                "recent_events": [],  # Rolling window of recent timestamps
                "erratic_score": stats.EWMean(fading_factor=0.3),  # Exponential weighted erratic score
            }
        )

        # Model metadata
        self.model_update_counts = defaultdict(int)

        # Performance tracking
        self.comfort_mae = metrics.MAE()
        self.comfort_rmse = metrics.RMSE()
        self.occupancy_accuracy = metrics.Accuracy()
        self.occupancy_precision = metrics.Precision()
        self.occupancy_recall = metrics.Recall()

        # Drift detection - track rolling window of errors
        self.comfort_error_window = []  # Last 100 errors
        self.occupancy_error_window = []  # Last 100 errors
        self.max_error_window = 100

        # Runtime tracking
        self.first_event_time: Optional[datetime] = None
        self.last_event_time: Optional[datetime] = None

        # Validation split (80/20)
        self.validation_counter = 0
        self.validation_frequency = 5  # Every 5th event goes to validation

    def _init_db(self):
        """Initialize database for model persistence"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Model persistence table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS river_models (
                model_name TEXT PRIMARY KEY,
                model_data BLOB NOT NULL,
                last_updated TIMESTAMP NOT NULL,
                update_count INTEGER DEFAULT 0
            )
        """)

        # Prediction history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS river_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_type TEXT NOT NULL,
                device_id TEXT,
                location TEXT,
                prediction_value REAL,
                confidence REAL,
                features TEXT,
                timestamp TIMESTAMP NOT NULL
            )
        """)

        # Model stats
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS river_stats (
                stat_key TEXT PRIMARY KEY,
                stat_value REAL,
                last_updated TIMESTAMP NOT NULL
            )
        """)

        # Model performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                window_size INTEGER,
                timestamp TIMESTAMP NOT NULL
            )
        """)

        # Runtime metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runtime_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def _load_models(self):
        """Load persisted models from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT model_name, model_data, update_count FROM river_models")

        for row in cursor.fetchall():
            model_name, model_data, update_count = row
            try:
                model_obj = pickle.loads(model_data)

                if model_name == "comfort_model":
                    self.comfort_model = model_obj
                elif model_name == "routine_model":
                    self.routine_model = model_obj
                elif model_name == "occupancy_model":
                    self.occupancy_model = model_obj
                elif model_name.startswith("anomaly_"):
                    device_id = model_name.replace("anomaly_", "")
                    self.anomaly_models[device_id] = model_obj
                elif model_name.startswith("baseline_"):
                    # Parse baseline_{device_id}_{metric}
                    parts = model_name.replace("baseline_", "").rsplit("_", 1)
                    if len(parts) == 2:
                        device_id, metric = parts
                        self.baseline_models[device_id][metric] = model_obj

                self.model_update_counts[model_name] = update_count
                logger.debug(f"Loaded model: {model_name} (updates: {update_count})")

            except Exception as e:
                logger.error(f"Error loading model {model_name}: {e}")

        conn.close()
        logger.info(f"Loaded {len(self.model_update_counts)} persisted models")

        # Load runtime metadata
        self._load_runtime_metadata()

    def _save_model(self, model_name: str, model_obj: Any):
        """Persist a model to database"""
        try:
            model_data = pickle.dumps(model_obj)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            update_count = self.model_update_counts[model_name] + 1

            cursor.execute("""
                INSERT OR REPLACE INTO river_models
                (model_name, model_data, last_updated, update_count)
                VALUES (?, ?, ?, ?)
            """, (model_name, model_data, datetime.now().isoformat(), update_count))

            conn.commit()
            conn.close()

            self.model_update_counts[model_name] = update_count

        except Exception as e:
            logger.error(f"Error saving model {model_name}: {e}")

    def _load_runtime_metadata(self):
        """Load runtime metadata from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT key, value FROM runtime_metadata WHERE key IN ('first_event_time', 'last_event_time')")
            for key, value in cursor.fetchall():
                if key == "first_event_time" and value:
                    self.first_event_time = datetime.fromisoformat(value)
                elif key == "last_event_time" and value:
                    self.last_event_time = datetime.fromisoformat(value)

            conn.close()
            logger.debug(f"Loaded runtime metadata: first={self.first_event_time}, last={self.last_event_time}")
        except Exception as e:
            logger.error(f"Error loading runtime metadata: {e}")

    def _save_runtime_metadata(self):
        """Persist runtime metadata to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if self.first_event_time:
                cursor.execute("""
                    INSERT OR REPLACE INTO runtime_metadata (key, value, updated_at)
                    VALUES (?, ?, ?)
                """, ("first_event_time", self.first_event_time.isoformat(), datetime.now().isoformat()))

            if self.last_event_time:
                cursor.execute("""
                    INSERT OR REPLACE INTO runtime_metadata (key, value, updated_at)
                    VALUES (?, ?, ?)
                """, ("last_event_time", self.last_event_time.isoformat(), datetime.now().isoformat()))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving runtime metadata: {e}")

    def _record_performance_metric(self, model_name: str, metric_name: str, metric_value: float, window_size: Optional[int] = None):
        """Record a performance metric to the database for historical tracking"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO model_performance (model_name, metric_name, metric_value, window_size, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (model_name, metric_name, metric_value, window_size, datetime.now().isoformat()))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error recording performance metric: {e}")

    def set_weather_context(self, env: EnvironmentalContext):
        """Cache environmental context for predictions"""
        self._env_context = env

    # ==================== FEATURE ENGINEERING ====================

    def _encode_time_cyclic(self, timestamp: datetime) -> Dict[str, float]:
        """Encode time as sin/cos for cyclical patterns"""
        hour = timestamp.hour
        dow = timestamp.weekday()

        hour_radians = 2 * math.pi * hour / 24
        dow_radians = 2 * math.pi * dow / 7

        return {
            "hour_sin": math.sin(hour_radians),
            "hour_cos": math.cos(hour_radians),
            "dow_sin": math.sin(dow_radians),
            "dow_cos": math.cos(dow_radians),
        }

    def _compute_sun_elevation(self, timestamp: datetime, env: Optional[EnvironmentalContext]) -> float:
        """
        Compute approximate sun elevation (0-1 normalized).
        0 = below horizon, 1 = solar noon peak
        """
        if not env:
            return 0.5

        sunrise = env.sun.sunrise
        sunset = env.sun.sunset

        if timestamp < sunrise or timestamp > sunset:
            return 0.0

        # Normalize position in day
        day_progress = (timestamp - sunrise).total_seconds() / (sunset - sunrise).total_seconds()

        # Simple parabolic elevation (peaks at noon)
        elevation = 4 * day_progress * (1 - day_progress)

        return elevation

    def _compute_sun_offsets(self, timestamp: datetime, env: Optional[EnvironmentalContext]) -> Tuple[float, float]:
        """
        Compute minutes since sunrise and until sunset.
        Normalized to [-1, 1] range.
        """
        if not env:
            return 0.0, 0.0

        sunrise_offset = (timestamp - env.sun.sunrise).total_seconds() / 3600  # hours
        sunset_offset = (env.sun.sunset - timestamp).total_seconds() / 3600

        # Normalize to [-1, 1]
        sunrise_offset_norm = max(-1.0, min(1.0, sunrise_offset / 12))
        sunset_offset_norm = max(-1.0, min(1.0, sunset_offset / 12))

        return sunrise_offset_norm, sunset_offset_norm

    def _categorize_weather(self, env: Optional[EnvironmentalContext]) -> Dict[str, float]:
        """
        Categorize weather into binary features.
        Returns one-hot-like encoding.
        """
        if not env:
            return {
                "weather_hot": 0.0,
                "weather_cold": 0.0,
                "weather_humid": 0.0,
                "weather_stormy": 0.0
            }

        temp = env.weather.temperature
        humidity = env.weather.humidity
        description = env.weather.description.lower()

        return {
            "weather_hot": 1.0 if temp > 80 else 0.0,
            "weather_cold": 1.0 if temp < 50 else 0.0,
            "weather_humid": 1.0 if humidity > 70 else 0.0,
            "weather_stormy": 1.0 if any(word in description for word in ["rain", "storm", "thunder"]) else 0.0
        }

    def _extract_comfort_features(
        self,
        context: EventContext,
        env: Optional[EnvironmentalContext]
    ) -> Dict[str, float]:
        """Extract features for comfort model"""
        features = {}

        # Indoor conditions
        features["indoor_temp"] = float(context.event_value) if context.event_type in ["temperature", "temp"] else 70.0
        features["indoor_humidity"] = 50.0  # Default, can be enriched from context

        # Time features
        time_features = self._encode_time_cyclic(context.timestamp)
        features.update(time_features)

        # Weather features
        if env:
            features["external_temp"] = env.weather.temperature
            features["feels_like"] = env.weather.feels_like
            features["external_humidity"] = env.weather.humidity
            features["wind_speed"] = env.weather.wind_speed
            features["aqi"] = env.air_quality.aqi if env.air_quality else 1.0
            features["sun_elevation"] = self._compute_sun_elevation(context.timestamp, env)
        else:
            features["external_temp"] = 70.0
            features["feels_like"] = 70.0
            features["external_humidity"] = 50.0
            features["wind_speed"] = 0.0
            features["aqi"] = 1.0
            features["sun_elevation"] = 0.5

        return features

    def _extract_routine_features(
        self,
        context: EventContext,
        env: Optional[EnvironmentalContext]
    ) -> Dict[str, float]:
        """Extract features for routine clustering"""
        features = {}

        # Time features
        time_features = self._encode_time_cyclic(context.timestamp)
        features.update(time_features)

        # Sun features
        sunrise_offset, sunset_offset = self._compute_sun_offsets(context.timestamp, env)
        features["sunrise_offset"] = sunrise_offset
        features["sunset_offset"] = sunset_offset

        # Sensor type encoding (simple hash)
        features["sensor_type"] = hash(context.event_type) % 100 / 100.0

        # Location encoding
        features["location"] = hash(context.location) % 100 / 100.0

        # Weather category
        weather_cat = self._categorize_weather(env)
        features.update(weather_cat)

        # Activity indicators
        features["is_motion"] = 1.0 if "motion" in context.event_type.lower() else 0.0
        features["is_door"] = 1.0 if "door" in context.event_type.lower() else 0.0

        return features

    def _extract_anomaly_features(
        self,
        context: EventContext,
        env: Optional[EnvironmentalContext]
    ) -> Dict[str, float]:
        """Extract features for anomaly detection"""
        features = {}

        # Primary value
        if isinstance(context.event_value, (int, float)):
            features["value"] = float(context.event_value)
        else:
            features["value"] = 0.0

        # Trends
        features["trend_1h"] = context.trend_1h or 0.0
        features["trend_24h"] = context.trend_24h or 0.0

        # Weather context (to reduce false positives during weather events)
        if env:
            features["external_temp"] = env.weather.temperature
            features["external_humidity"] = env.weather.humidity
            weather_cat = self._categorize_weather(env)
            features.update(weather_cat)
        else:
            features["external_temp"] = 70.0
            features["external_humidity"] = 50.0

        return features

    # ==================== LEARNING ====================

    async def learn_from_sensor_data(
        self,
        context: EventContext,
        env: Optional[EnvironmentalContext] = None
    ):
        """
        Update all models incrementally from sensor data.

        Args:
            context: EventContext from sensor event
            env: Optional environmental context from weather service
        """
        # Track runtime
        if self.first_event_time is None:
            self.first_event_time = context.timestamp
            logger.info(f"First event received at {self.first_event_time}")
        self.last_event_time = context.timestamp

        # Cache weather context for this learning cycle
        if env:
            self._env_context = env
            logger.debug(f"Updated weather context: {env.weather.temperature:.1f}°F, {env.weather.description}")
        else:
            env = self._env_context
            if not env:
                logger.debug("No weather context available - using defaults")

        # Determine if this event is for validation (every 5th event)
        self.validation_counter += 1
        is_validation = (self.validation_counter % self.validation_frequency) == 0

        # Update baseline model
        if isinstance(context.event_value, (int, float)):
            await self._update_baseline(context.device_id, context.event_type, float(context.event_value))

        # Update event frequency model (for erratic detection)
        erratic_info = await self._update_frequency_model(context)
        if erratic_info and erratic_info.get("is_erratic"):
            logger.warning(
                f"ML detected erratic behavior: {context.device_id} - "
                f"score={erratic_info['erratic_score']:.2f}, "
                f"rate={erratic_info['events_per_minute']:.1f}/min"
            )

        # Update anomaly model
        await self._update_anomaly_model(context, env)

        # Update routine model
        await self._update_routine_model(context, env)

        # Update comfort model (for temp/humidity events)
        if context.event_type in ["temperature", "temp", "humidity"]:
            await self._update_comfort_model(context, env, is_validation)

        # Persist models and metadata periodically (every 50 updates)
        if sum(self.model_update_counts.values()) % 50 == 0:
            await self._persist_all_models()
            self._save_runtime_metadata()

    async def _update_baseline(self, device_id: str, metric: str, value: float):
        """Update running baseline statistics"""
        if device_id not in self.baseline_models:
            self.baseline_models[device_id] = {}

        if metric not in self.baseline_models[device_id]:
            self.baseline_models[device_id][metric] = (stats.Mean(), stats.Var())

        mean_model, var_model = self.baseline_models[device_id][metric]
        mean_model.update(value)
        var_model.update(value)

        # Persist every 100 updates
        model_name = f"baseline_{device_id}_{metric}"
        self.model_update_counts[model_name] += 1

        if self.model_update_counts[model_name] % 100 == 0:
            self._save_model(model_name, (mean_model, var_model))

    async def _update_frequency_model(self, context: EventContext) -> Optional[Dict[str, Any]]:
        """
        Update event frequency model for erratic behavior detection.
        
        Tracks:
        - Inter-event time (seconds between events)
        - Event rate (events per minute/hour)
        - Erratic score (high score = erratic behavior)
        
        Returns erratic info if behavior is detected.
        """
        device_id = context.device_id
        current_time = context.timestamp
        
        freq_model = self.frequency_models[device_id]
        last_time = freq_model["last_event_time"]
        
        # Update recent events window (keep last 60 seconds)
        recent = freq_model["recent_events"]
        cutoff = current_time.timestamp() - 60  # Last 60 seconds
        freq_model["recent_events"] = [t for t in recent if t > cutoff]
        freq_model["recent_events"].append(current_time.timestamp())
        
        # Calculate inter-event time
        if last_time:
            inter_event_seconds = (current_time - last_time).total_seconds()
            
            # Update statistics
            freq_model["inter_event_time"].update(inter_event_seconds)
            freq_model["inter_event_var"].update(inter_event_seconds)
            
            # Calculate erratic score
            # Erratic = many events in short time + low inter-event variance (consistent rapid fire)
            events_in_window = len(freq_model["recent_events"])
            events_per_minute = events_in_window  # Window is 60 seconds
            
            # Score based on:
            # - High event rate (>3/min is suspicious, >10/min is very erratic)
            # - Very short inter-event time (<10 seconds)
            rate_score = min(1.0, events_per_minute / 10.0)  # Normalize to 0-1
            time_score = max(0, 1.0 - (inter_event_seconds / 30.0))  # <30s = higher score
            
            erratic_score = (rate_score * 0.6 + time_score * 0.4)
            freq_model["erratic_score"].update(erratic_score)
            
            # Get smoothed erratic score
            smoothed_score = freq_model["erratic_score"].get()
            
            # Persist periodically
            model_name = f"frequency_{device_id}"
            self.model_update_counts[model_name] += 1
            
            if self.model_update_counts[model_name] % 50 == 0:
                self._save_model(model_name, {
                    "inter_event_time": freq_model["inter_event_time"],
                    "inter_event_var": freq_model["inter_event_var"],
                    "erratic_score": freq_model["erratic_score"],
                })
            
            # Return erratic info if score is high
            is_erratic = smoothed_score > 0.5 and events_per_minute >= 3
            
            result = {
                "device_id": device_id,
                "is_erratic": is_erratic,
                "erratic_score": smoothed_score,
                "events_per_minute": events_per_minute,
                "inter_event_seconds": inter_event_seconds,
                "mean_inter_event": freq_model["inter_event_time"].get(),
            }
            
            # Update last event time
            freq_model["last_event_time"] = current_time
            
            return result
        
        # First event for this device
        freq_model["last_event_time"] = current_time
        return None

    async def get_device_erratic_stats(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get erratic behavior statistics for a device.

        Returns ML-learned stats about event frequency patterns.
        Applies time-based decay to erratic score if device has been quiet.
        """
        if device_id not in self.frequency_models:
            return None

        freq_model = self.frequency_models[device_id]

        mean_inter_event = freq_model["inter_event_time"].get()
        var_inter_event = freq_model["inter_event_var"].get()
        erratic_score = freq_model["erratic_score"].get()
        recent_count = len(freq_model["recent_events"])

        # Apply time-based decay to erratic score
        # If device has been quiet for a while, reduce the erratic score
        last_event_time = freq_model.get("last_event_time")
        if last_event_time:
            time_since_last_event = (datetime.now() - last_event_time).total_seconds()

            # Decay erratic score exponentially over time
            # Uses configurable half-life from config
            decay_factor = 2 ** (-time_since_last_event / self.erratic_decay_half_life)

            # Apply decay
            decayed_score = erratic_score * decay_factor
        else:
            decayed_score = erratic_score

        # Calculate if currently erratic (using configurable threshold)
        is_currently_erratic = decayed_score > self.erratic_threshold and recent_count >= 3

        return {
            "device_id": device_id,
            "mean_inter_event_seconds": mean_inter_event,
            "variance_inter_event": var_inter_event,
            "erratic_score": decayed_score,
            "is_erratic": is_currently_erratic,
            "recent_events_per_minute": recent_count,
            "trend": "erratic" if is_currently_erratic else "normal",
        }

    async def get_all_erratic_devices(self) -> list:
        """
        Get all devices exhibiting erratic behavior.

        Returns list of devices with scores above list_threshold.
        Uses configurable threshold from config.
        """
        erratic_devices = []

        for device_id in self.frequency_models:
            stats = await self.get_device_erratic_stats(device_id)
            if stats and stats.get("erratic_score", 0) > self.erratic_list_threshold:
                erratic_devices.append(stats)

        # Sort by erratic score descending
        erratic_devices.sort(key=lambda x: x.get("erratic_score", 0), reverse=True)

        return erratic_devices

    async def _update_anomaly_model(self, context: EventContext, env: Optional[EnvironmentalContext]):
        """Update per-device anomaly detection model"""
        features = self._extract_anomaly_features(context, env)

        # Update model
        model = self.anomaly_models[context.device_id]
        model.learn_one(features)

        # Persist periodically
        model_name = f"anomaly_{context.device_id}"
        self.model_update_counts[model_name] += 1

        if self.model_update_counts[model_name] % 100 == 0:
            self._save_model(model_name, model)

    async def _update_routine_model(self, context: EventContext, env: Optional[EnvironmentalContext]):
        """Update routine clustering model"""
        features = self._extract_routine_features(context, env)

        # Learn from this routine event
        self.routine_model.learn_one(features)

        # Persist periodically
        model_name = "routine_model"
        self.model_update_counts[model_name] += 1

        if self.model_update_counts[model_name] % 100 == 0:
            self._save_model(model_name, self.routine_model)

    async def _update_comfort_model(self, context: EventContext, env: Optional[EnvironmentalContext], is_validation: bool = False):
        """
        Update comfort model with validation split.

        For now, we use a simple target: assume current conditions are acceptable.
        In production, this would be refined with user feedback.
        """
        features = self._extract_comfort_features(context, env)

        # Target: current value (assumes it's acceptable)
        # This gets refined by user feedback via separate update path
        if context.event_type in ["temperature", "temp"]:
            target = float(context.event_value)
        else:
            target = 50.0  # humidity default

        if is_validation:
            # Validation: predict first, then measure error (don't train)
            try:
                prediction = self.comfort_model.predict_one(features)
                error = abs(prediction - target)

                # Update performance metrics
                self.comfort_mae.update(target, prediction)
                self.comfort_rmse.update(target, prediction)

                # Track rolling window for drift detection
                self.comfort_error_window.append(error)
                if len(self.comfort_error_window) > self.max_error_window:
                    self.comfort_error_window.pop(0)

                logger.debug(f"Validation: predicted={prediction:.1f}, actual={target:.1f}, error={error:.1f}")
            except Exception as e:
                logger.debug(f"Comfort model not ready for prediction: {e}")
        else:
            # Training: learn from this example
            self.comfort_model.learn_one(features, target)

            # Persist periodically
            model_name = "comfort_model"
            self.model_update_counts[model_name] += 1

            if self.model_update_counts[model_name] % 100 == 0:
                self._save_model(model_name, self.comfort_model)

                # Record performance metrics to DB
                if self.comfort_mae.get() is not None:
                    self._record_performance_metric("comfort_model", "mae", self.comfort_mae.get())
                if self.comfort_rmse.get() is not None:
                    self._record_performance_metric("comfort_model", "rmse", self.comfort_rmse.get())

    async def _persist_all_models(self):
        """Persist all models to database"""
        self._save_model("comfort_model", self.comfort_model)
        self._save_model("routine_model", self.routine_model)
        self._save_model("occupancy_model", self.occupancy_model)

        for device_id, model in self.anomaly_models.items():
            self._save_model(f"anomaly_{device_id}", model)

        for device_id, metrics in self.baseline_models.items():
            for metric, model_tuple in metrics.items():
                self._save_model(f"baseline_{device_id}_{metric}", model_tuple)

        logger.debug("Persisted all River models")

    # ==================== ANOMALY DETECTION ====================

    async def is_anomalous(
        self,
        device_id: str,
        metric: str,
        value: float
    ) -> Tuple[bool, float]:
        """
        Check if value is anomalous.

        Returns:
            (is_anomalous, score)
            score: 0-1, higher = more anomalous
        """
        # Check baseline model first
        baseline_result = await self._is_baseline_anomalous(device_id, metric, value)

        # Check HalfSpaceTrees anomaly model
        if device_id in self.anomaly_models:
            model = self.anomaly_models[device_id]

            # Create minimal feature dict
            features = {
                "value": value,
                "trend_1h": 0.0,
                "trend_24h": 0.0,
                "external_temp": 70.0,
                "external_humidity": 50.0
            }

            # Get anomaly score
            anomaly_score = model.score_one(features)

            # Normalize score (HalfSpaceTrees returns 0-1, higher = more anomalous)
            is_anomalous = anomaly_score > 0.7

            # Combine with baseline check
            if baseline_result[0] and is_anomalous:
                return True, max(baseline_result[1], anomaly_score)
            elif baseline_result[0] or is_anomalous:
                return True, (baseline_result[1] + anomaly_score) / 2
            else:
                return False, anomaly_score

        return baseline_result

    async def _is_baseline_anomalous(
        self,
        device_id: str,
        metric: str,
        value: float,
        stddev_threshold: float = 3.0
    ) -> Tuple[bool, float]:
        """Check if value exceeds baseline by stddev_threshold"""
        if device_id not in self.baseline_models:
            return False, 0.0

        if metric not in self.baseline_models[device_id]:
            return False, 0.0

        mean_model, var_model = self.baseline_models[device_id][metric]

        mean_val = mean_model.get()
        var_val = var_model.get()

        if mean_val is None or var_val is None or var_val <= 0:
            return False, 0.0

        stddev = math.sqrt(var_val)

        if stddev == 0:
            return False, 0.0

        z_score = abs(value - mean_val) / stddev

        # Normalize to 0-1 score
        score = min(1.0, z_score / (stddev_threshold * 2))

        return z_score > stddev_threshold, score

    # ==================== PREDICTIONS ====================

    async def predict_preferred_value(
        self,
        location: str,
        metric: str,
        current_value: float,
        env: Optional[EnvironmentalContext] = None
    ) -> Tuple[Optional[float], float]:
        """
        Predict preferred value for a metric.

        Returns:
            (predicted_value, confidence)
        """
        if env:
            self._env_context = env
        else:
            env = self._env_context

        # Build feature vector
        # Create a pseudo-context
        from .types import EventContext

        pseudo_context = EventContext(
            device_id="virtual",
            sensor_id="virtual",
            event_type=metric,
            event_value=current_value,
            location=location,
            device_type="virtual",
            timestamp=datetime.now()
        )

        features = self._extract_comfort_features(pseudo_context, env)

        # Predict using comfort model
        try:
            predicted = self.comfort_model.predict_one(features)

            # Confidence based on model update count
            model_name = "comfort_model"
            update_count = self.model_update_counts.get(model_name, 0)

            # Confidence scales with training samples (capped at 0.9)
            confidence = min(0.9, update_count / 1000.0)

            return predicted, confidence

        except Exception as e:
            logger.error(f"Error predicting preferred value: {e}")
            return None, 0.0

    async def get_comfort_preference(self, location: str) -> Optional[Dict[str, Any]]:
        """
        Get learned comfort preferences for a location.

        Returns dict with predicted ranges.
        """
        env = self._env_context

        # Predict for multiple conditions
        temp_pred, temp_conf = await self.predict_preferred_value(location, "temperature", 70.0, env)
        humid_pred, humid_conf = await self.predict_preferred_value(location, "humidity", 50.0, env)

        if temp_pred is None:
            return None

        return {
            "preferred_temp": temp_pred,
            "preferred_temp_confidence": temp_conf,
            "preferred_humidity": humid_pred or 50.0,
            "preferred_humidity_confidence": humid_conf,
            "location": location
        }

    async def get_routine_features(self, location: str) -> Dict[str, Any]:
        """
        Get routine clustering features for a location.

        Returns cluster assignments and patterns.
        """
        # This is a simplified implementation
        # In production, would analyze cluster centroids and patterns

        return {
            "location": location,
            "routine_clusters_active": len(self.routine_model.centers) if hasattr(self.routine_model, "centers") else 0,
            "model_updates": self.model_update_counts.get("routine_model", 0)
        }

    # ==================== STATISTICS ====================

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive ML engine statistics with REAL model performance metrics"""
        # Get erratic devices
        erratic_devices = await self.get_all_erratic_devices()

        # Calculate model maturity indicators
        comfort_updates = self.model_update_counts.get("comfort_model", 0)
        routine_updates = self.model_update_counts.get("routine_model", 0)
        occupancy_updates = self.model_update_counts.get("occupancy_model", 0)

        # Model maturity based on update counts
        comfort_maturity = "mature" if comfort_updates > 500 else "developing" if comfort_updates > 100 else "immature"
        routine_maturity = "mature" if routine_updates > 500 else "developing" if routine_updates > 100 else "immature"
        occupancy_maturity = "mature" if occupancy_updates > 500 else "developing" if occupancy_updates > 100 else "immature"

        # REAL performance metrics (not fake confidence)
        comfort_mae_value = self.comfort_mae.get() if self.comfort_mae.get() is not None else None
        comfort_rmse_value = self.comfort_rmse.get() if self.comfort_rmse.get() is not None else None

        # Calculate actual accuracy from MAE (lower error = higher accuracy)
        # Accuracy as percentage: 100% - (MAE / reasonable_range * 100)
        # For temperature, reasonable range ~30°F
        if comfort_mae_value is not None and comfort_mae_value > 0:
            comfort_accuracy = max(0, min(100, 100 - (comfort_mae_value / 30.0 * 100)))
        else:
            comfort_accuracy = None

        # Routine clustering stats (if KMeans model has centers)
        try:
            routine_clusters = len(self.routine_model.centers) if hasattr(self.routine_model, 'centers') else 0
        except Exception:
            routine_clusters = 0

        # Calculate per-device health metrics
        device_health = []
        for device_id in self.baseline_models.keys():
            device_stats = await self.get_device_erratic_stats(device_id)

            # Handle case where device_stats might be None (device has no erratic data yet)
            if device_stats is None:
                device_stats = {}

            # Get baseline stats for this device
            baseline_metrics = {}
            if device_id in self.baseline_models:
                for metric, (mean_model, var_model) in self.baseline_models[device_id].items():
                    mean_val = mean_model.get()
                    var_val = var_model.get()
                    baseline_metrics[metric] = {
                        "mean": mean_val,
                        "variance": var_val,
                        "std_dev": math.sqrt(var_val) if var_val and var_val > 0 else 0.0
                    }

            # Get anomaly model update count for this device
            anomaly_model_name = f"anomaly_{device_id}"
            anomaly_updates = self.model_update_counts.get(anomaly_model_name, 0)

            device_health.append({
                "device_id": device_id,
                "erratic_score": device_stats.get("erratic_score", 0.0),
                "decayed_erratic_score": device_stats.get("decayed_erratic_score", 0.0),
                "is_erratic": device_stats.get("is_erratic", False),
                "recent_event_count": device_stats.get("recent_event_count", 0),
                "anomaly_model_updates": anomaly_updates,
                "baseline_metrics": baseline_metrics,
                "last_event_time": device_stats.get("last_event_time"),
            })

        # Calculate REAL runtime (not fake!)
        total_updates = sum(self.model_update_counts.values())

        if self.first_event_time and self.last_event_time:
            runtime_seconds = (self.last_event_time - self.first_event_time).total_seconds()
            actual_hours_active = runtime_seconds / 3600.0
            updates_per_hour = total_updates / max(1, actual_hours_active)
        else:
            # Fallback if no events yet
            actual_hours_active = 0.0
            updates_per_hour = 0.0

        # Data quality score: based on variety of devices and update distribution
        # Count all devices being tracked across all model types (baseline, anomaly, frequency)
        all_tracked_devices = set()
        all_tracked_devices.update(self.baseline_models.keys())
        all_tracked_devices.update(self.anomaly_models.keys())
        all_tracked_devices.update(self.frequency_models.keys())
        num_devices = len(all_tracked_devices)

        data_quality = min(1.0, num_devices / 10.0) * 0.5 + min(1.0, total_updates / 1000.0) * 0.5

        # Drift detection - calculate recent error vs baseline
        comfort_drift_detected = False
        comfort_drift_severity = 0.0
        if len(self.comfort_error_window) >= 20:
            # Compare recent errors (last 20) vs baseline (first 50% of window)
            window_size = len(self.comfort_error_window)
            baseline_errors = self.comfort_error_window[:window_size // 2]
            recent_errors = self.comfort_error_window[-20:]

            baseline_mean = sum(baseline_errors) / len(baseline_errors)
            recent_mean = sum(recent_errors) / len(recent_errors)

            # Drift if recent errors are >50% higher than baseline
            if baseline_mean > 0:
                drift_ratio = recent_mean / baseline_mean
                if drift_ratio > 1.5:
                    comfort_drift_detected = True
                    comfort_drift_severity = min(1.0, (drift_ratio - 1.0) / 2.0)  # Normalize to 0-1

        return {
            # Basic stats (backward compatible)
            "comfort_model_updates": comfort_updates,
            "routine_model_updates": routine_updates,
            "occupancy_model_updates": occupancy_updates,
            "anomaly_models_active": len(self.anomaly_models),
            "baseline_models_active": sum(len(metrics) for metrics in self.baseline_models.values()),
            "frequency_models_active": len(self.frequency_models),
            "total_model_updates": total_updates,
            "devices_tracked": num_devices,
            "erratic_devices": erratic_devices,
            "erratic_device_count": len(erratic_devices),

            # Model maturity indicators
            "model_maturity": {
                "comfort": {
                    "status": comfort_maturity,
                    "update_count": comfort_updates,
                    # REAL performance metrics
                    "mae": round(comfort_mae_value, 2) if comfort_mae_value is not None else None,
                    "rmse": round(comfort_rmse_value, 2) if comfort_rmse_value is not None else None,
                    "accuracy_pct": round(comfort_accuracy, 1) if comfort_accuracy is not None else None,
                },
                "routine": {
                    "status": routine_maturity,
                    "update_count": routine_updates,
                    "clusters_detected": routine_clusters,
                },
                "occupancy": {
                    "status": occupancy_maturity,
                    "update_count": occupancy_updates,
                }
            },

            # Learning velocity metrics (REAL runtime)
            "learning_velocity": {
                "total_updates": total_updates,
                "actual_hours_active": round(actual_hours_active, 2),
                "updates_per_hour": round(updates_per_hour, 1),
                "data_quality_score": round(data_quality, 3),
                "first_event_time": self.first_event_time.isoformat() if self.first_event_time else None,
                "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            },

            # Model drift detection
            "drift_detection": {
                "comfort_model": {
                    "drift_detected": comfort_drift_detected,
                    "severity": round(comfort_drift_severity, 3) if comfort_drift_detected else 0.0,
                    "error_window_size": len(self.comfort_error_window),
                }
            },

            # Per-device health metrics
            "device_health": device_health
        }
