"""
MQTT service for real-time device state and incident monitoring.

This service subscribes to HomeSight MQTT topics and maintains an
in-memory cache of device state, providing real-time updates to
other services.
"""

import logging
from typing import Dict, Optional, Callable
from datetime import datetime
import threading

from mqtt_client import HomeSightMQTTClient

logger = logging.getLogger(__name__)


class MQTTService:
    """
    Manages MQTT subscriptions and maintains device/incident cache.

    Provides callbacks for other services to respond to real-time events.
    """

    def __init__(
        self,
        broker_url: str = "localhost",
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Initialize MQTT service."""
        self.client = HomeSightMQTTClient(
            broker_url=broker_url,
            broker_port=broker_port,
            client_id="homesight-ai-sidecar",
            username=username,
            password=password,
        )

        # In-memory caches
        self.devices: Dict[str, dict] = {}
        self.device_states: Dict[str, dict] = {}
        self.lock = threading.RLock()

        # Callbacks for external services
        self._discovery_callbacks: list[Callable] = []
        self._state_callbacks: list[Callable] = []
        self._incident_callbacks: list[Callable] = []

        # Register MQTT handlers
        self.client.on_discovery(self._handle_discovery)
        self.client.on_state(self._handle_state)
        self.client.on_incident(self._handle_incident)
        self.client.on_metadata(self._handle_metadata)

        self._connected = False

    def start(self):
        """Connect to MQTT broker and start listening."""
        try:
            self.client.connect()
            self._connected = True
            logger.info("MQTT service started and connected")
        except Exception as e:
            logger.error(f"Failed to start MQTT service: {e}")
            self._connected = False

    def stop(self):
        """Disconnect from MQTT broker."""
        self.client.disconnect()
        self._connected = False
        logger.info("MQTT service stopped")

    @property
    def is_connected(self) -> bool:
        """Check if connected to MQTT broker."""
        return self._connected and self.client.is_connected

    # ========== Event Handlers ==========

    def _handle_discovery(self, integration: str, device_id: str, payload: dict):
        """Handle device discovery messages."""
        with self.lock:
            full_device_id = payload.get("device_id", f"{integration}-{device_id}")

            # Update device cache
            self.devices[full_device_id] = {
                "device_id": full_device_id,
                "integration": integration,
                "name": payload.get("name", full_device_id),
                "manufacturer": payload.get("manufacturer"),
                "model": payload.get("model"),
                "capabilities": payload.get("capabilities", []),
                "discovered_at": datetime.utcnow().isoformat(),
            }

            logger.info(f"Device discovered: {full_device_id} ({integration})")

        # Notify callbacks
        for callback in self._discovery_callbacks:
            try:
                callback(full_device_id, self.devices[full_device_id])
            except Exception as e:
                logger.error(f"Error in discovery callback: {e}")

    def _handle_state(self, device_id: str, payload: dict):
        """Handle device state update messages."""
        with self.lock:
            # Update state cache
            if device_id not in self.device_states:
                self.device_states[device_id] = {}

            timestamp = payload.get("ts")
            values = payload.get("values", {})

            self.device_states[device_id] = {
                "timestamp": timestamp,
                "values": values,
                "updated_at": datetime.utcnow().isoformat(),
            }

            logger.debug(f"State update: {device_id} - {len(values)} values")

        # Notify callbacks
        for callback in self._state_callbacks:
            try:
                callback(device_id, values, timestamp)
            except Exception as e:
                logger.error(f"Error in state callback: {e}")

    def _handle_incident(self, payload: dict):
        """Handle incident messages."""
        incident_id = payload.get("incident_id")
        device_id = payload.get("device_id")
        severity = payload.get("severity")
        title = payload.get("title")

        logger.info(f"Incident received: {title} ({severity}) - {device_id}")

        # Notify callbacks
        for callback in self._incident_callbacks:
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Error in incident callback: {e}")

    def _handle_metadata(self, device_id: str, payload: dict):
        """Handle device metadata updates."""
        with self.lock:
            if device_id in self.devices:
                # Update metadata
                if "metadata" not in self.devices[device_id]:
                    self.devices[device_id]["metadata"] = {}

                self.devices[device_id]["metadata"].update(
                    payload.get("metadata", {})
                )

                if "zone_id" in payload:
                    self.devices[device_id]["zone_id"] = payload["zone_id"]
                if "asset_id" in payload:
                    self.devices[device_id]["asset_id"] = payload["asset_id"]

                logger.debug(f"Metadata updated: {device_id}")

    # ========== Public API ==========

    def get_device(self, device_id: str) -> Optional[dict]:
        """Get device info from cache."""
        with self.lock:
            return self.devices.get(device_id)

    def get_all_devices(self) -> list[dict]:
        """Get all devices from cache."""
        with self.lock:
            return list(self.devices.values())

    def get_device_state(self, device_id: str) -> Optional[dict]:
        """Get current device state from cache."""
        with self.lock:
            return self.device_states.get(device_id)

    def send_command(self, device_id: str, command: str, args: Optional[dict] = None):
        """
        Send command to device via MQTT.

        Args:
            device_id: Target device ID
            command: Command name (e.g., "set_switch", "refresh")
            args: Optional command arguments
        """
        self.client.publish_command(device_id, command, args or {})
        logger.info(f"Command sent: {device_id} -> {command}")

    # ========== Callbacks ==========

    def on_discovery(self, callback: Callable[[str, dict], None]):
        """
        Register callback for device discovery.

        Callback signature: (device_id: str, device_info: dict) -> None
        """
        self._discovery_callbacks.append(callback)

    def on_state(self, callback: Callable[[str, dict, str], None]):
        """
        Register callback for device state updates.

        Callback signature: (device_id: str, values: dict, timestamp: str) -> None
        """
        self._state_callbacks.append(callback)

    def on_incident(self, callback: Callable[[dict], None]):
        """
        Register callback for incidents.

        Callback signature: (incident: dict) -> None
        """
        self._incident_callbacks.append(callback)


# Singleton instance
_mqtt_service: Optional[MQTTService] = None


def get_mqtt_service() -> Optional[MQTTService]:
    """Get singleton MQTT service instance."""
    return _mqtt_service


def initialize_mqtt_service(
    broker_url: str = "localhost",
    broker_port: int = 1883,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MQTTService:
    """
    Initialize and start MQTT service.

    Should be called once at application startup.
    """
    global _mqtt_service

    if _mqtt_service is not None:
        logger.warning("MQTT service already initialized")
        return _mqtt_service

    logger.info("Initializing MQTT service...")
    _mqtt_service = MQTTService(
        broker_url=broker_url,
        broker_port=broker_port,
        username=username,
        password=password,
    )
    _mqtt_service.start()

    return _mqtt_service


def shutdown_mqtt_service():
    """Shutdown MQTT service."""
    global _mqtt_service

    if _mqtt_service is not None:
        _mqtt_service.stop()
        _mqtt_service = None
        logger.info("MQTT service shut down")
