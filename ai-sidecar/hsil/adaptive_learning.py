"""
Adaptive Learning System

Learns from ALL system data:
1. Sensor patterns (temperature cycles, water usage, motion patterns)
2. User preferences (user says "cold" at 68°F → learns they prefer 70°F)
3. Action outcomes (did closing valve stop the leak? did temp change help?)

This creates a continuously improving system that adapts to:
- User comfort preferences
- Home-specific patterns (your HVAC cycles, your water usage baseline)
- Seasonal adjustments
- Occupancy patterns
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
import statistics

from .types import EventContext, Feature, ActionCommand

logger = logging.getLogger(__name__)


class AdaptiveLearningService:
    """
    Continuously learns from all system data to improve predictions
    and recommendations.
    """

    def __init__(self, db_path: str = "/var/lib/homesight/hsil_memory.db"):
        self.db_path = db_path
        self._init_db()
        self._init_policy_table()

        # In-memory caches for fast lookup
        self.comfort_preferences = {}  # location -> preferred temp range
        self.device_baselines = {}  # device_id -> baseline values
        self.pattern_cache = {}  # Pattern storage

        # Load existing learned data
        self._load_learned_data()

        logger.info("AdaptiveLearningService initialized")

    def _init_policy_table(self):
        """Initialize policy table for adaptive automation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS automation_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                device_id TEXT,
                policy_key TEXT NOT NULL,
                policy_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                feedback_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def update_policy_from_feedback(self, user_id: str, device_id: str, policy_key: str, preferred_value: str):
        """
        Update automation policy based on user feedback. Increments feedback count and confidence.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT confidence, feedback_count FROM automation_policies
            WHERE user_id = ? AND device_id = ? AND policy_key = ?
        """, (user_id, device_id, policy_key))
        row = cursor.fetchone()
        if row:
            confidence, feedback_count = row
            new_confidence = min(1.0, confidence + 0.1)
            new_count = feedback_count + 1
            cursor.execute("""
                UPDATE automation_policies SET policy_value = ?, confidence = ?, feedback_count = ?, last_updated = ?
                WHERE user_id = ? AND device_id = ? AND policy_key = ?
            """, (preferred_value, new_confidence, new_count, datetime.now().isoformat(), user_id, device_id, policy_key))
        else:
            cursor.execute("""
                INSERT INTO automation_policies (user_id, device_id, policy_key, policy_value, confidence, feedback_count, last_updated)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (user_id, device_id, policy_key, preferred_value, 0.6, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info(f"Policy updated: {policy_key}={preferred_value} for user={user_id}, device={device_id}")

    def get_policy(self, user_id: str, device_id: str, policy_key: str) -> Optional[str]:
        """
        Retrieve current automation policy for a user/device/key.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT policy_value, confidence FROM automation_policies
            WHERE user_id = ? AND device_id = ? AND policy_key = ?
        """, (user_id, device_id, policy_key))
        row = cursor.fetchone()
        conn.close()
        if row and row[1] >= 0.7:
            return row[0]
        return None

    def _init_db(self):
        """Initialize learning database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Comfort preferences learned from user feedback
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comfort_preferences (
                location TEXT PRIMARY KEY,
                preferred_temp_min REAL,
                preferred_temp_max REAL,
                preferred_humidity_min REAL,
                preferred_humidity_max REAL,
                sample_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP NOT NULL
            )
        """)

        # Device baselines (what's "normal" for each device)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_baselines (
                device_id TEXT,
                metric_name TEXT,
                baseline_value REAL,
                baseline_stddev REAL,
                sample_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP NOT NULL,
                PRIMARY KEY (device_id, metric_name)
            )
        """)

        # Action outcomes (did the action help?)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                action_value TEXT,
                context TEXT,  -- JSON of context when action taken
                outcome TEXT,  -- "success", "failure", "partial"
                outcome_score REAL,  -- 0-1 score
                timestamp TIMESTAMP NOT NULL
            )
        """)

        # User preference events (user says "cold", "hot", etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preference_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_intent TEXT NOT NULL,
                location TEXT,
                temperature REAL,
                humidity REAL,
                time_of_day INTEGER,  -- Hour 0-23
                day_of_week INTEGER,  -- 0-6
                timestamp TIMESTAMP NOT NULL
            )
        """)

        # Learned patterns (recurring behaviors)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                pattern_data TEXT,  -- JSON
                confidence REAL DEFAULT 0.5,
                occurrence_count INTEGER DEFAULT 1,
                last_seen TIMESTAMP NOT NULL,
                UNIQUE(pattern_type, pattern_key)
            )
        """)

        conn.commit()
        conn.close()

        logger.info("Adaptive learning database initialized")

    def _load_learned_data(self):
        """Load learned data into memory caches"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Load comfort preferences
        cursor.execute("SELECT * FROM comfort_preferences")
        for row in cursor.fetchall():
            self.comfort_preferences[row[0]] = {
                "temp_min": row[1],
                "temp_max": row[2],
                "humidity_min": row[3],
                "humidity_max": row[4],
                "sample_count": row[5]
            }

        # Load device baselines
        cursor.execute("SELECT * FROM device_baselines")
        for row in cursor.fetchall():
            if row[0] not in self.device_baselines:
                self.device_baselines[row[0]] = {}
            self.device_baselines[row[0]][row[1]] = {
                "baseline": row[2],
                "stddev": row[3],
                "sample_count": row[4]
            }

        conn.close()

        logger.info(
            f"Loaded learned data: {len(self.comfort_preferences)} comfort prefs, "
            f"{len(self.device_baselines)} device baselines"
        )

    # ==================== SENSOR DATA LEARNING ====================

    async def learn_from_sensor_data(self, context: EventContext):
        """
        Learn patterns from sensor data.

        Updates:
        - Device baselines (what's normal for this sensor)
        - Temporal patterns (time-of-day, day-of-week patterns)
        - Anomaly detection baselines
        """
        # Update device baseline
        if isinstance(context.event_value, (int, float)):
            await self._update_device_baseline(
                context.device_id,
                context.event_type,
                float(context.event_value)
            )

        # Learn temporal patterns
        await self._learn_temporal_pattern(context)

    async def _update_device_baseline(
        self,
        device_id: str,
        metric_name: str,
        value: float
    ):
        """
        Update baseline statistics for a device metric using
        incremental mean/variance calculation.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT baseline_value, baseline_stddev, sample_count
            FROM device_baselines
            WHERE device_id = ? AND metric_name = ?
        """, (device_id, metric_name))

        row = cursor.fetchone()

        if row:
            old_mean = row[0]
            old_stddev = row[1]
            old_count = row[2]

            # Incremental update (Welford's algorithm)
            new_count = old_count + 1
            delta = value - old_mean
            new_mean = old_mean + delta / new_count

            # Simple running stddev update
            new_variance = ((old_stddev ** 2) * old_count + delta * (value - new_mean)) / new_count
            new_stddev = new_variance ** 0.5

            cursor.execute("""
                UPDATE device_baselines
                SET baseline_value = ?,
                    baseline_stddev = ?,
                    sample_count = ?,
                    last_updated = ?
                WHERE device_id = ? AND metric_name = ?
            """, (
                new_mean,
                new_stddev,
                new_count,
                datetime.now().isoformat(),
                device_id,
                metric_name
            ))

            # Update cache
            if device_id not in self.device_baselines:
                self.device_baselines[device_id] = {}
            self.device_baselines[device_id][metric_name] = {
                "baseline": new_mean,
                "stddev": new_stddev,
                "sample_count": new_count
            }

        else:
            # First sample
            cursor.execute("""
                INSERT INTO device_baselines
                (device_id, metric_name, baseline_value, baseline_stddev, sample_count, last_updated)
                VALUES (?, ?, ?, 0.0, 1, ?)
            """, (device_id, metric_name, value, datetime.now().isoformat()))

            if device_id not in self.device_baselines:
                self.device_baselines[device_id] = {}
            self.device_baselines[device_id][metric_name] = {
                "baseline": value,
                "stddev": 0.0,
                "sample_count": 1
            }

        conn.commit()
        conn.close()

    async def _learn_temporal_pattern(self, context: EventContext):
        """Learn time-of-day and day-of-week patterns"""
        import json

        if not isinstance(context.event_value, (int, float)):
            return

        hour = context.timestamp.hour
        dow = context.timestamp.weekday()

        pattern_key = f"{context.device_id}:{context.event_type}:h{hour}"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Store pattern
        cursor.execute("""
            INSERT INTO learned_patterns
            (pattern_type, pattern_key, pattern_data, confidence, occurrence_count, last_seen)
            VALUES ('temporal', ?, ?, 0.5, 1, ?)
            ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                pattern_data = ?,
                occurrence_count = occurrence_count + 1,
                confidence = MIN(1.0, confidence + 0.01),
                last_seen = ?
        """, (
            pattern_key,
            json.dumps({"value": context.event_value, "hour": hour, "dow": dow}),
            datetime.now().isoformat(),
            json.dumps({"value": context.event_value, "hour": hour, "dow": dow}),
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

    # ==================== USER PREFERENCE LEARNING ====================

    async def learn_from_user_action(
        self,
        user_intent: str,
        location: str,
        current_temp: Optional[float] = None,
        current_humidity: Optional[float] = None,
        action_taken: Optional[ActionCommand] = None
    ):
        """
        Learn from user actions and requests.

        Examples:
        - User says "I'm cold" at 68°F → learn they prefer > 68°F
        - User increases temp to 72°F → learn preferred temp
        - User says "too hot" at 75°F → learn they prefer < 75°F
        """
        now = datetime.now()

        # Record user preference event
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO user_preference_events
            (user_intent, location, temperature, humidity, time_of_day, day_of_week, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_intent,
            location,
            current_temp,
            current_humidity,
            now.hour,
            now.weekday(),
            now.isoformat()
        ))

        conn.commit()
        conn.close()

        # Update comfort preferences
        await self._update_comfort_preferences(
            user_intent,
            location,
            current_temp,
            current_humidity,
            action_taken
        )

        logger.info(f"Learned from user action: intent={user_intent}, location={location}, temp={current_temp}")

    async def _update_comfort_preferences(
        self,
        user_intent: str,
        location: str,
        current_temp: Optional[float],
        current_humidity: Optional[float],
        action_taken: Optional[ActionCommand]
    ):
        """Update learned comfort preferences"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current preferences
        cursor.execute("""
            SELECT preferred_temp_min, preferred_temp_max,
                   preferred_humidity_min, preferred_humidity_max,
                   sample_count
            FROM comfort_preferences
            WHERE location = ?
        """, (location,))

        row = cursor.fetchone()

        if row:
            temp_min, temp_max, hum_min, hum_max, sample_count = row
        else:
            # Initialize with reasonable defaults
            temp_min, temp_max = 68.0, 75.0
            hum_min, hum_max = 35.0, 55.0
            sample_count = 0

        # Adjust based on user intent
        intent_lower = user_intent.lower()

        if "cold" in intent_lower or "chilly" in intent_lower:
            if current_temp is not None:
                # User is cold at this temp, they prefer warmer
                temp_min = max(temp_min, current_temp + 1.0)
                if action_taken and action_taken.value:
                    # Learn their target temp
                    temp_max = min(temp_max + 0.5, float(action_taken.value))

        elif "hot" in intent_lower or "warm" in intent_lower:
            if current_temp is not None:
                # User is hot at this temp, they prefer cooler
                temp_max = min(temp_max, current_temp - 1.0)
                if action_taken and action_taken.value:
                    temp_min = max(temp_min - 0.5, float(action_taken.value))

        elif "dry" in intent_lower:
            if current_humidity is not None:
                hum_min = max(hum_min, current_humidity + 5.0)

        elif "humid" in intent_lower:
            if current_humidity is not None:
                hum_max = min(hum_max, current_humidity - 5.0)

        # Store updated preferences
        cursor.execute("""
            INSERT INTO comfort_preferences
            (location, preferred_temp_min, preferred_temp_max,
             preferred_humidity_min, preferred_humidity_max,
             sample_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(location) DO UPDATE SET
                preferred_temp_min = ?,
                preferred_temp_max = ?,
                preferred_humidity_min = ?,
                preferred_humidity_max = ?,
                sample_count = sample_count + 1,
                last_updated = ?
        """, (
            location, temp_min, temp_max, hum_min, hum_max,
            sample_count + 1, datetime.now().isoformat(),
            temp_min, temp_max, hum_min, hum_max,
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        # Update cache
        self.comfort_preferences[location] = {
            "temp_min": temp_min,
            "temp_max": temp_max,
            "humidity_min": hum_min,
            "humidity_max": hum_max,
            "sample_count": sample_count + 1
        }

        logger.debug(
            f"Updated comfort preferences for {location}: "
            f"temp={temp_min:.1f}-{temp_max:.1f}°F, humidity={hum_min:.0f}-{hum_max:.0f}%"
        )

    # ==================== ACTION OUTCOME LEARNING ====================

    async def learn_from_action_outcome(
        self,
        action: ActionCommand,
        context: Dict[str, Any],
        outcome: str,  # "success", "failure", "partial"
        outcome_score: float  # 0-1
    ):
        """
        Learn whether an action was successful.

        Example:
        - Action: Close water valve
        - Context: Leak detected in basement
        - Outcome: Success (leak stopped)
        - Score: 1.0
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO action_outcomes
            (action_type, action_value, context, outcome, outcome_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            action.command,
            str(action.value),
            json.dumps(context),
            outcome,
            outcome_score,
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        logger.info(
            f"Learned action outcome: {action.command} = {outcome} "
            f"(score: {outcome_score:.2f})"
        )

    # ==================== QUERY LEARNED DATA ====================

    async def get_comfort_preference(self, location: str) -> Optional[Dict[str, float]]:
        """Get learned comfort preferences for a location"""
        return self.comfort_preferences.get(location)

    async def get_device_baseline(self, device_id: str, metric_name: str) -> Optional[Dict[str, float]]:
        """Get learned baseline for a device metric"""
        if device_id in self.device_baselines:
            return self.device_baselines[device_id].get(metric_name)
        return None

    async def is_anomalous(
        self,
        device_id: str,
        metric_name: str,
        value: float,
        stddev_threshold: float = 3.0
    ) -> Tuple[bool, float]:
        """
        Check if a value is anomalous based on learned baseline.

        Returns:
            (is_anomalous, z_score)
        """
        baseline_data = await self.get_device_baseline(device_id, metric_name)

        if not baseline_data or baseline_data["sample_count"] < 10:
            # Not enough data to determine anomaly
            return False, 0.0

        baseline = baseline_data["baseline"]
        stddev = baseline_data["stddev"]

        if stddev == 0:
            return False, 0.0

        z_score = abs(value - baseline) / stddev

        return z_score > stddev_threshold, z_score

    async def predict_preferred_value(
        self,
        location: str,
        metric: str,  # "temperature" or "humidity"
        current_value: float
    ) -> Optional[float]:
        """
        Predict the user's preferred value based on learned preferences.

        Returns target value, or None if not enough data.
        """
        prefs = await self.get_comfort_preference(location)

        if not prefs or prefs["sample_count"] < 3:
            return None

        if metric == "temperature":
            # Return midpoint of preferred range
            return (prefs["temp_min"] + prefs["temp_max"]) / 2.0

        elif metric == "humidity":
            return (prefs["humidity_min"] + prefs["humidity_max"]) / 2.0

        return None

    async def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM user_preference_events")
        user_events = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM device_baselines")
        device_baselines = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM comfort_preferences")
        comfort_prefs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM action_outcomes")
        action_outcomes = cursor.fetchone()[0]

        cursor.execute("""
            SELECT AVG(outcome_score)
            FROM action_outcomes
            WHERE timestamp > datetime('now', '-7 days')
        """)
        recent_success_rate = cursor.fetchone()[0] or 0.0

        conn.close()

        return {
            "user_preference_events": user_events,
            "device_baselines_learned": device_baselines,
            "comfort_preferences_learned": comfort_prefs,
            "action_outcomes_recorded": action_outcomes,
            "recent_success_rate": recent_success_rate,
            "locations_with_preferences": len(self.comfort_preferences)
        }

    async def record_interaction(
        self,
        interaction_id: str,
        user_query: str,
        system_response: str,
        action_taken: Any = None,
        context: Any = None
    ):
        """
        Record a conversational interaction for learning purposes.
        Persists to the conversational_interactions table.
        """
        import json
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversational_interactions (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                user_query TEXT,
                system_response TEXT,
                action_taken TEXT,
                context TEXT
            )
        """)

        cursor.execute("""
            INSERT OR REPLACE INTO conversational_interactions
            (id, timestamp, user_query, system_response, action_taken, context)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            interaction_id,
            datetime.now().isoformat(),
            user_query,
            system_response,
            json.dumps(action_taken) if action_taken is not None else None,
            json.dumps(context) if context is not None else None
        ))

        conn.commit()
        conn.close()

        logger.info(f"Recorded interaction: {interaction_id}, query='{user_query}', response='{system_response}', action={action_taken}")