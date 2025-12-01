"""
Temperature Preference Model

Uses River ML to learn user temperature preferences and predict adjustments.
Learns from user commands and feedback in real-time.
"""

import logging
import pickle
from typing import Optional, Dict, Any
from datetime import datetime
import math

from river import linear_model, optim, stats

logger = logging.getLogger(__name__)


class TemperaturePreferenceModel:
    """
    Online learning model for user temperature preferences.

    Features:
    - Outdoor temperature
    - Current indoor temperature
    - Time of day (cyclic encoding)
    - Day of week (cyclic encoding)
    - User feedback signals

    Predicts: Optimal temperature adjustment
    """

    def __init__(self, db_path: str = "/var/lib/homesight/hsil_memory.db"):
        self.db_path = db_path

        # Linear regression for temperature prediction
        self.model = linear_model.LinearRegression(
            optimizer=optim.SGD(lr=0.01)
        )

        # Running statistics for baseline
        self.baseline_temp = stats.Mean()
        self.temp_variance = stats.Var()

        # Preference bounds (learned)
        self.learned_min = 68.0
        self.learned_max = 75.0

        # Load persisted model if available
        self._load_model()

        logger.info("TemperaturePreferenceModel initialized")

    def _load_model(self):
        """Load persisted model from database"""
        # TODO: Load from SQLite blob storage
        pass

    def _save_model(self):
        """Save model to database"""
        # TODO: Persist to SQLite blob storage
        pass

    def learn_from_command(
        self,
        user_message: str,
        current_indoor_temp: float,
        current_outdoor_temp: Optional[float] = None,
        target_temp: Optional[float] = None,
        delta: Optional[int] = None
    ):
        """
        Learn from user temperature command.

        Args:
            user_message: User's message (for sentiment)
            current_indoor_temp: Current temperature
            current_outdoor_temp: Outdoor temperature
            target_temp: Target temperature (if explicit)
            delta: Temperature delta (if incremental)
        """
        # Extract features
        features = self._extract_features(current_indoor_temp, current_outdoor_temp)

        # Determine target
        if target_temp is not None:
            y = target_temp
        elif delta is not None:
            y = current_indoor_temp + delta
        else:
            # Infer from message sentiment
            if any(word in user_message.lower() for word in ["cold", "freezing", "chilly"]):
                y = current_indoor_temp + 2
            elif any(word in user_message.lower() for word in ["hot", "warm", "stuffy"]):
                y = current_indoor_temp - 2
            else:
                # No clear signal
                return

        # Update model
        self.model.learn_one(features, y)

        # Update baseline stats
        self.baseline_temp.update(y)
        self.temp_variance.update(y)

        # Update learned bounds
        mean = self.baseline_temp.get()
        if mean:
            std = math.sqrt(self.temp_variance.get()) if self.temp_variance.get() else 2.0
            self.learned_min = max(65, mean - std)
            self.learned_max = min(80, mean + std)

        logger.info(f"Learned temp preference: target={y:.1f}°F (bounds: {self.learned_min:.1f}-{self.learned_max:.1f}°F)")

        # Persist model periodically
        self._save_model()

    def predict_adjustment(
        self,
        user_message: str,
        current_indoor_temp: float,
        current_outdoor_temp: Optional[float] = None
    ) -> Optional[int]:
        """
        Predict temperature adjustment based on user message.

        Args:
            user_message: User's message
            current_indoor_temp: Current temperature
            current_outdoor_temp: Outdoor temperature

        Returns:
            Temperature delta (-5 to +5) or None if no adjustment needed
        """
        # Extract features
        features = self._extract_features(current_indoor_temp, current_outdoor_temp)

        # Predict optimal temperature
        try:
            predicted_temp = self.model.predict_one(features)

            # Calculate delta
            delta = round(predicted_temp - current_indoor_temp)

            # Clamp delta
            delta = max(-5, min(5, delta))

            # Only suggest adjustment if significant
            if abs(delta) < 1:
                return None

            logger.info(f"Predicted adjustment: {delta:+d}°F (current={current_indoor_temp:.1f}°F, predicted={predicted_temp:.1f}°F)")
            return int(delta)

        except Exception as e:
            logger.warning(f"Temperature prediction failed: {e}")
            return None

    def get_preferred_range(self) -> tuple:
        """Get learned temperature preference range"""
        return (self.learned_min, self.learned_max)

    def _extract_features(
        self,
        indoor_temp: float,
        outdoor_temp: Optional[float] = None
    ) -> Dict[str, float]:
        """Extract features for model"""
        now = datetime.now()

        # Cyclic time encoding (hour of day)
        hour = now.hour
        hour_sin = math.sin(2 * math.pi * hour / 24)
        hour_cos = math.cos(2 * math.pi * hour / 24)

        # Cyclic day of week encoding
        day_of_week = now.weekday()
        day_sin = math.sin(2 * math.pi * day_of_week / 7)
        day_cos = math.cos(2 * math.pi * day_of_week / 7)

        features = {
            "indoor_temp": indoor_temp,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "day_sin": day_sin,
            "day_cos": day_cos,
        }

        if outdoor_temp is not None:
            features["outdoor_temp"] = outdoor_temp
            features["temp_diff"] = indoor_temp - outdoor_temp

        return features

    def get_stats(self) -> Dict[str, Any]:
        """Get model statistics"""
        return {
            "learned_min": self.learned_min,
            "learned_max": self.learned_max,
            "baseline_mean": self.baseline_temp.get() if self.baseline_temp.get() else None,
            "baseline_variance": self.temp_variance.get() if self.temp_variance.get() else None,
            "model_params": len(self.model.weights) if hasattr(self.model, 'weights') else 0
        }
