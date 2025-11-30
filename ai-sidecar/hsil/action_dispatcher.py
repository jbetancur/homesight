"""
Action Dispatcher

Publishes actions back to MQTT topics to control devices.

Topics:
- homesight/hvac/set_temp
- homesight/water/close_main
- homesight/device/<id>/command
"""

import logging
from typing import Optional
import json

from .types import ActionCommand

logger = logging.getLogger(__name__)


class ActionDispatcherService:
    """
    Dispatches action commands to devices via MQTT.
    """

    def __init__(self, mqtt_client=None, topic_prefix: str = "homesight"):
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        logger.info(f"ActionDispatcherService initialized with prefix={topic_prefix}")

    def set_mqtt_client(self, mqtt_client):
        """Set MQTT client (after initialization)"""
        self.mqtt_client = mqtt_client
        logger.info("MQTT client configured for ActionDispatcher")

    async def dispatch(self, action: ActionCommand) -> bool:
        """
        Dispatch an action command.

        Args:
            action: ActionCommand to execute

        Returns:
            True if dispatched successfully
        """
        if not self.mqtt_client:
            logger.warning("Cannot dispatch action - no MQTT client configured")
            return False

        try:
            # Build full topic (action may have partial or full topic)
            topic = action.topic
            if not topic.startswith(self.topic_prefix):
                topic = f"{self.topic_prefix}/{topic}"

            # Build payload
            payload = {
                "command": action.command,
                "value": action.value,
                "timestamp": __import__("datetime").datetime.now().isoformat()
            }

            # Publish to MQTT
            logger.info(f"Dispatching action: {topic} -> {payload}")

            await self.mqtt_client.publish(
                topic,
                json.dumps(payload),
                qos=1  # At least once delivery
            )

            return True

        except Exception as e:
            logger.error(f"Failed to dispatch action: {e}")
            return False

    async def dispatch_hvac_temp(self, temperature: float) -> bool:
        """Convenience method: Set HVAC temperature"""
        action = ActionCommand(
            topic=f"{self.topic_prefix}/hvac/set_temp",
            command="set_temperature",
            value=temperature
        )
        return await self.dispatch(action)

    async def dispatch_water_valve(self, close: bool = True) -> bool:
        """Convenience method: Control main water valve"""
        action = ActionCommand(
            topic=f"{self.topic_prefix}/water/close_main",
            command="close_valve" if close else "open_valve",
            value=close
        )
        return await self.dispatch(action)

    async def dispatch_device_command(
        self,
        device_id: str,
        command: str,
        value: any
    ) -> bool:
        """Convenience method: Send command to specific device"""
        action = ActionCommand(
            topic=f"{self.topic_prefix}/device/{device_id}/command",
            command=command,
            value=value
        )
        return await self.dispatch(action)
