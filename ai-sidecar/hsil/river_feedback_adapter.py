"""
River Feedback Adapter

Adapts user feedback into training signals for River models.
Translates user intents ("I'm cold") into model updates.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .types import EventContext, ActionCommand
from .weather_service import EnvironmentalContext

logger = logging.getLogger(__name__)


class RiverFeedbackAdapter:
    """
    Translates user feedback into River model training signals.
    """

    def __init__(self, learning_engine):
        """
        Args:
            learning_engine: HSILRiverLearningEngine instance
        """
        self.learning_engine = learning_engine

    async def learn_from_user_feedback(
        self,
        user_intent: str,
        location: str,
        current_temp: Optional[float] = None,
        current_humidity: Optional[float] = None,
        action_taken: Optional[ActionCommand] = None,
        env: Optional[EnvironmentalContext] = None
    ):
        """
        Process user feedback and update River models.

        Examples:
        - User says "I'm cold" at 68°F → train comfort model that preferred temp > 68
        - User sets temp to 72°F → train comfort model with target=72
        - User says "too hot" at 75°F → train comfort model that preferred temp < 75

        Args:
            user_intent: User's stated intent or action
            location: Location where feedback occurred
            current_temp: Current temperature
            current_humidity: Current humidity
            action_taken: Optional action user took
            env: Environmental context
        """
        intent_lower = user_intent.lower()

        # Determine target value from intent
        target_temp = None
        target_confidence = 0.5

        # Parse intent
        if "cold" in intent_lower or "chilly" in intent_lower:
            # User wants it warmer
            if current_temp is not None:
                target_temp = current_temp + 3.0  # Want 3°F warmer
                target_confidence = 0.7
            if action_taken and action_taken.value:
                target_temp = float(action_taken.value)
                target_confidence = 0.9

        elif "hot" in intent_lower or "warm" in intent_lower:
            # User wants it cooler
            if current_temp is not None:
                target_temp = current_temp - 3.0  # Want 3°F cooler
                target_confidence = 0.7
            if action_taken and action_taken.value:
                target_temp = float(action_taken.value)
                target_confidence = 0.9

        elif "perfect" in intent_lower or "comfortable" in intent_lower or "good" in intent_lower:
            # Current conditions are good
            if current_temp is not None:
                target_temp = current_temp
                target_confidence = 0.85

        elif action_taken and "set" in intent_lower and action_taken.value:
            # User explicitly set a value
            target_temp = float(action_taken.value)
            target_confidence = 0.95

        # If we have a target, update comfort model
        if target_temp is not None:
            await self._update_comfort_model_from_feedback(
                location=location,
                target_temp=target_temp,
                current_temp=current_temp or target_temp,
                current_humidity=current_humidity or 50.0,
                env=env,
                confidence=target_confidence
            )

            logger.info(
                f"Learned from feedback: '{user_intent}' at {location} "
                f"(target={target_temp:.1f}°F, confidence={target_confidence:.2f})"
            )

    async def _update_comfort_model_from_feedback(
        self,
        location: str,
        target_temp: float,
        current_temp: float,
        current_humidity: float,
        env: Optional[EnvironmentalContext],
        confidence: float
    ):
        """
        Update comfort model with user feedback.

        Uses weighted learning: higher confidence feedback updates model more strongly.
        """
        # Build feature vector
        from .types import EventContext

        pseudo_context = EventContext(
            device_id="user_feedback",
            sensor_id="user_feedback",
            event_type="temperature",
            event_value=current_temp,
            location=location,
            device_type="feedback",
            timestamp=datetime.now()
        )

        features = self.learning_engine._extract_comfort_features(pseudo_context, env)

        # Train comfort model multiple times based on confidence
        # High confidence feedback gets multiple training iterations
        iterations = int(confidence * 10)

        for _ in range(max(1, iterations)):
            self.learning_engine.comfort_model.learn_one(features, target_temp)

        # Increment update count
        model_name = "comfort_model"
        self.learning_engine.model_update_counts[model_name] += iterations

        # Save if threshold reached
        if self.learning_engine.model_update_counts[model_name] % 50 == 0:
            self.learning_engine._save_model(model_name, self.learning_engine.comfort_model)

    async def learn_from_action_outcome(
        self,
        action: ActionCommand,
        outcome: str,
        outcome_score: float,
        context: Dict[str, Any]
    ):
        """
        Learn from action outcomes.

        For now, this is primarily used for logging and future model refinement.
        In production, could be used to train a reinforcement learning policy.

        Args:
            action: Action that was taken
            outcome: "success", "failure", "partial"
            outcome_score: 0-1 score
            context: Context when action was taken
        """
        logger.info(
            f"Action outcome: {action.command}={action.value} "
            f"→ {outcome} (score: {outcome_score:.2f})"
        )

        # Future: Use this to train a policy model
        # For now, just log for observability
