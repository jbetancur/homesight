"""
Policy Engine

Converts high-level intents into concrete home actions.

Examples:
- "I'm cold" → determine ideal HVAC action
- Leak anomalies → close water valve
- Low humidity + low temperature → pre-heat
- Unusual water usage → alert
"""

import logging
from typing import Optional, Dict, Any

from .types import PolicyDecision, ActionCommand, BehaviorPrediction, EventContext

logger = logging.getLogger(__name__)


class PolicyEngineService:
    """
    Policy engine that converts intents and predictions into actionable commands.
    """

    def __init__(self, mqtt_topic_prefix: str = "homesight"):
        self.mqtt_topic_prefix = mqtt_topic_prefix
        logger.info("PolicyEngineService initialized")

    async def evaluate_user_intent(
        self,
        intent: str,
        context: Dict[str, Any]
    ) -> PolicyDecision:
        """
        Evaluate a user intent and determine the appropriate action.

        Args:
            intent: User's expressed intent (e.g., "I'm cold", "too hot")
            context: Current home state context

        Returns:
            PolicyDecision with recommended action
        """
        intent_lower = intent.lower()

        # Temperature comfort intents
        if "cold" in intent_lower or "chilly" in intent_lower:
            return await self._handle_too_cold(context)

        elif "hot" in intent_lower or "warm" in intent_lower:
            return await self._handle_too_hot(context)

        # Water/leak intents
        elif "leak" in intent_lower or "water" in intent_lower:
            return await self._handle_water_concern(context)

        # Humidity intents
        elif "dry" in intent_lower or "humid" in intent_lower:
            return await self._handle_humidity(context, intent_lower)

        # Default: no specific action
        return PolicyDecision(
            intent=intent,
            action=None,
            reasoning="No specific policy matched this intent",
            confidence=0.5,
            metadata={"context": context}
        )

    async def evaluate_prediction(
        self,
        prediction: BehaviorPrediction,
        context: Dict[str, Any]
    ) -> PolicyDecision:
        """
        Evaluate a behavior prediction and determine if action is needed.

        Args:
            prediction: Behavior prediction from model
            context: Current home state

        Returns:
            PolicyDecision with action if needed
        """
        if prediction.type.value == "water_safety":
            return await self._handle_water_safety_prediction(prediction, context)

        elif prediction.type.value == "comfort":
            return await self._handle_comfort_prediction(prediction, context)

        elif prediction.type.value == "maintenance":
            return await self._handle_maintenance_prediction(prediction, context)

        # Default: no action
        return PolicyDecision(
            intent=f"prediction:{prediction.type.value}",
            action=None,
            reasoning="Prediction does not require immediate action",
            confidence=prediction.confidence,
            metadata={"prediction": prediction.model_dump(mode='json')}
        )

    # ==================== Intent Handlers ====================

    async def _handle_too_cold(self, context: Dict[str, Any]) -> PolicyDecision:
        """Handle 'I'm cold' intent"""
        current_temp = context.get("temperature", 70)
        target_temp = current_temp + 2  # Increase by 2°F

        action = ActionCommand(
            topic=f"{self.mqtt_topic_prefix}/hvac/set_temp",
            command="set_temperature",
            value=target_temp
        )

        return PolicyDecision(
            intent="too_cold",
            action=action,
            reasoning=f"User reported being cold. Increasing temperature from {current_temp}°F to {target_temp}°F",
            confidence=0.9,
            metadata={"current_temp": current_temp, "target_temp": target_temp}
        )

    async def _handle_too_hot(self, context: Dict[str, Any]) -> PolicyDecision:
        """Handle 'I'm hot' intent"""
        current_temp = context.get("temperature", 70)
        target_temp = current_temp - 2  # Decrease by 2°F

        action = ActionCommand(
            topic=f"{self.mqtt_topic_prefix}/hvac/set_temp",
            command="set_temperature",
            value=target_temp
        )

        return PolicyDecision(
            intent="too_hot",
            action=action,
            reasoning=f"User reported being hot. Decreasing temperature from {current_temp}°F to {target_temp}°F",
            confidence=0.9,
            metadata={"current_temp": current_temp, "target_temp": target_temp}
        )

    async def _handle_water_concern(self, context: Dict[str, Any]) -> PolicyDecision:
        """Handle water/leak concerns"""
        leak_detected = context.get("leak_detected", False)

        if leak_detected:
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/water/close_main",
                command="close_valve",
                value=True
            )

            return PolicyDecision(
                intent="water_leak",
                action=action,
                reasoning="Leak detected. Closing main water valve as precaution",
                confidence=0.95,
                metadata=context
            )

        # No immediate action if no leak detected
        return PolicyDecision(
            intent="water_concern",
            action=None,
            reasoning="No active leak detected. Monitoring water systems",
            confidence=0.7,
            metadata=context
        )

    async def _handle_humidity(self, context: Dict[str, Any], intent: str) -> PolicyDecision:
        """Handle humidity concerns"""
        current_humidity = context.get("humidity", 50)

        if "dry" in intent:
            # Increase humidity (run humidifier or adjust HVAC)
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/hvac/humidifier",
                command="set_humidity_target",
                value=45  # Target 45% RH
            )

            return PolicyDecision(
                intent="too_dry",
                action=action,
                reasoning=f"User reported dry air. Current humidity {current_humidity}%, targeting 45%",
                confidence=0.85,
                metadata={"current_humidity": current_humidity}
            )

        elif "humid" in intent:
            # Decrease humidity (run dehumidifier or adjust HVAC)
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/hvac/dehumidifier",
                command="set_humidity_target",
                value=50  # Target 50% RH
            )

            return PolicyDecision(
                intent="too_humid",
                action=action,
                reasoning=f"User reported humid air. Current humidity {current_humidity}%, targeting 50%",
                confidence=0.85,
                metadata={"current_humidity": current_humidity}
            )

        return PolicyDecision(
            intent="humidity_concern",
            action=None,
            reasoning="Humidity concern noted but no specific action determined",
            confidence=0.6,
            metadata=context
        )

    # ==================== Prediction Handlers ====================

    async def _handle_water_safety_prediction(
        self,
        prediction: BehaviorPrediction,
        context: Dict[str, Any]
    ) -> PolicyDecision:
        """Handle water safety predictions"""
        pred_data = prediction.prediction
        risk_score = pred_data.get("risk_score", 0.0)
        recommended_action = pred_data.get("recommended_action", "none")

        if recommended_action == "close_main_valve":
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/water/close_main",
                command="close_valve",
                value=True
            )

            return PolicyDecision(
                intent="water_safety_risk",
                action=action,
                reasoning=f"High water safety risk detected (score: {risk_score:.2f}). Closing main valve",
                confidence=prediction.confidence,
                metadata={"prediction": pred_data}
            )

        elif recommended_action == "alert_homeowner":
            # For alerts, we don't send device commands, but log for notification system
            return PolicyDecision(
                intent="water_safety_alert",
                action=None,
                reasoning=f"Moderate water safety risk (score: {risk_score:.2f}). Alerting homeowner",
                confidence=prediction.confidence,
                metadata={"alert": True, "prediction": pred_data}
            )

        return PolicyDecision(
            intent="water_safety_normal",
            action=None,
            reasoning="Water safety within normal parameters",
            confidence=prediction.confidence,
            metadata={"prediction": pred_data}
        )

    async def _handle_comfort_prediction(
        self,
        prediction: BehaviorPrediction,
        context: Dict[str, Any]
    ) -> PolicyDecision:
        """Handle comfort predictions"""
        pred_data = prediction.prediction
        comfort_score = pred_data.get("comfort_score", 1.0)
        recommended_action = pred_data.get("recommended_action", "none")

        if recommended_action == "increase_heat":
            temp = pred_data.get("temperature", 70)
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/hvac/set_temp",
                command="set_temperature",
                value=temp + 2
            )

            return PolicyDecision(
                intent="comfort_optimization_heat",
                action=action,
                reasoning=f"Low comfort score ({comfort_score:.2f}). Increasing heat",
                confidence=prediction.confidence,
                metadata={"prediction": pred_data}
            )

        elif recommended_action == "increase_cooling":
            temp = pred_data.get("temperature", 70)
            action = ActionCommand(
                topic=f"{self.mqtt_topic_prefix}/hvac/set_temp",
                command="set_temperature",
                value=temp - 2
            )

            return PolicyDecision(
                intent="comfort_optimization_cooling",
                action=action,
                reasoning=f"Low comfort score ({comfort_score:.2f}). Increasing cooling",
                confidence=prediction.confidence,
                metadata={"prediction": pred_data}
            )

        return PolicyDecision(
            intent="comfort_normal",
            action=None,
            reasoning="Comfort within acceptable range",
            confidence=prediction.confidence,
            metadata={"prediction": pred_data}
        )

    async def _handle_maintenance_prediction(
        self,
        prediction: BehaviorPrediction,
        context: Dict[str, Any]
    ) -> PolicyDecision:
        """Handle maintenance predictions"""
        pred_data = prediction.prediction
        maintenance_score = pred_data.get("maintenance_score", 0.0)
        recommended_action = pred_data.get("recommended_action", "none")

        # Maintenance typically doesn't trigger automated device actions,
        # but creates tasks/notifications

        return PolicyDecision(
            intent=f"maintenance_{recommended_action}",
            action=None,
            reasoning=f"Maintenance score: {maintenance_score:.2f}. Recommendation: {recommended_action}",
            confidence=prediction.confidence,
            metadata={"create_task": True, "prediction": pred_data}
        )
