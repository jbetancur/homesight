"""
MQTT client for HomeSight AI sidecar.

Subscribes to device state and incident messages from the HomeSight MQTT bus.
Publishes device commands to control devices.
"""

import json
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


def parse_mqtt_url(url: str, default_port: int = 1883) -> tuple[str, int]:
    """
    Parse MQTT broker URL to extract hostname and port.
    
    Handles formats:
    - tcp://hostname:port
    - mqtt://hostname:port
    - hostname:port
    - hostname
    
    Args:
        url: MQTT broker URL
        default_port: Default port if not specified
    
    Returns:
        Tuple of (hostname, port)
    """
    # Add scheme if missing for urlparse to work
    if "://" not in url:
        url = f"tcp://{url}"
    
    parsed = urlparse(url)
    hostname = parsed.hostname or "localhost"
    port = parsed.port or default_port
    
    return hostname, port


class HomeSightMQTTClient:
    """MQTT client for HomeSight integration messages."""

    def __init__(
        self,
        broker_url: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "homesight-ai-sidecar",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize MQTT client.

        Args:
            broker_url: MQTT broker URL (supports tcp://host:port, mqtt://host:port, host:port, host)
            broker_port: MQTT broker port (default: 1883, overridden if URL contains port)
            client_id: MQTT client ID
            username: Optional MQTT username
            password: Optional MQTT password
        """
        # Parse URL to extract hostname and port
        self.broker_url, url_port = parse_mqtt_url(broker_url, broker_port)
        # Use port from URL if present, otherwise use provided port
        self.broker_port = url_port

        self.client = mqtt.Client(client_id=client_id)

        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Callbacks
        self._discovery_callback: Optional[Callable] = None
        self._state_callback: Optional[Callable] = None
        self._incident_callback: Optional[Callable] = None
        self._metadata_callback: Optional[Callable] = None

        self._connected = False

    def connect(self) -> None:
        """Connect to MQTT broker."""
        logger.info(f"Connecting to MQTT broker at {self.broker_url}:{self.broker_port}")
        self.client.connect(self.broker_url, self.broker_port, 60)
        self.client.loop_start()

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        logger.info("Disconnecting from MQTT broker")
        self.client.loop_stop()
        self.client.disconnect()
        self._connected = False

    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection to MQTT broker."""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            self._connected = True

            # Subscribe to all HomeSight topics
            topics = [
                ("homesight/+/+/discovery", 0),
                ("homesight/+/+/metadata", 0),
                ("homesight/+/+/state", 0),
                ("homesight/+/+/removed", 0),
                ("homesight/incidents/#", 0),
            ]

            for topic, qos in topics:
                self.client.subscribe(topic, qos)
                logger.info(f"Subscribed to {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection from MQTT broker."""
        self._connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        topic = msg.topic

        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse message from {topic}: {msg.payload}")
            return

        # Parse topic: homesight/<integration>/<deviceId>/<messageType>
        parts = topic.split("/")

        if len(parts) < 2 or parts[0] != "homesight":
            return

        # Handle incident messages (homesight/incidents/# - can be 3+ parts)
        if parts[1] == "incidents":
            logger.debug(f"Received incident message on {topic}")
            if self._incident_callback:
                self._incident_callback(payload)
            return

        # For device messages, need at least 4 parts
        if len(parts) < 4:
            logger.debug(f"Ignoring message with unexpected topic format: {topic}")
            return

        integration = parts[1]
        node_id = parts[2]
        message_type = parts[3]

        # Construct full device ID: {integration}-{nodeId}
        # This matches the format used by the Go API database
        device_id = f"{integration}-{node_id}"

        # Route to appropriate callback
        if message_type == "discovery" and self._discovery_callback:
            self._discovery_callback(integration, device_id, payload)
        elif message_type == "metadata" and self._metadata_callback:
            self._metadata_callback(device_id, payload)
        elif message_type == "state" and self._state_callback:
            self._state_callback(device_id, payload)
        elif message_type == "removed":
            logger.info(f"Device removed: {device_id}")

    def on_discovery(self, callback: Callable[[str, str, Dict], None]) -> None:
        """
        Register callback for device discovery messages.

        Args:
            callback: Function(integration, device_id, payload)
        """
        self._discovery_callback = callback

    def on_state(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Register callback for device state messages.

        Args:
            callback: Function(device_id, payload)
        """
        self._state_callback = callback

    def on_incident(self, callback: Callable[[Dict], None]) -> None:
        """
        Register callback for incident messages.

        Args:
            callback: Function(payload)
        """
        self._incident_callback = callback

    def on_metadata(self, callback: Callable[[str, Dict], None]) -> None:
        """
        Register callback for metadata update messages.

        Args:
            callback: Function(device_id, payload)
        """
        self._metadata_callback = callback

    def publish_command(self, device_id: str, command: str, args: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish a device command.

        Args:
            device_id: Target device ID
            command: Command name (e.g., "set_switch", "set_level")
            args: Optional command arguments
        """
        topic = f"homesight/cmd/{device_id}"

        payload = {
            "command": command,
            "args": args or {}
        }

        self.client.publish(topic, json.dumps(payload), qos=0)
        logger.info(f"Published command to {device_id}: {command}")

    def publish_discovery(
        self,
        integration: str,
        device_id: str,
        name: str,
        capabilities: list,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Publish a device discovery message (for testing or custom integrations).

        Args:
            integration: Integration name (e.g., "ai", "custom")
            device_id: Unique device ID
            name: Human-readable device name
            capabilities: List of capabilities
            manufacturer: Optional manufacturer name
            model: Optional model name
        """
        # Extract short device ID from full ID
        short_id = device_id.replace(f"{integration}-", "")
        topic = f"homesight/{integration}/{short_id}/discovery"

        payload = {
            "device_id": device_id,
            "integration": integration,
            "name": name,
            "capabilities": capabilities,
        }

        if manufacturer:
            payload["manufacturer"] = manufacturer
        if model:
            payload["model"] = model

        self.client.publish(topic, json.dumps(payload), qos=0, retain=True)
        logger.info(f"Published discovery for {device_id}")

    def publish_state(
        self,
        integration: str,
        device_id: str,
        values: Dict[str, Any],
    ) -> None:
        """
        Publish device state update (for testing or custom integrations).

        Args:
            integration: Integration name
            device_id: Device ID
            values: State values dictionary
        """
        short_id = device_id.replace(f"{integration}-", "")
        topic = f"homesight/{integration}/{short_id}/state"

        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "values": values,
        }

        self.client.publish(topic, json.dumps(payload), qos=0)
        logger.debug(f"Published state for {device_id}")

    @property
    def is_connected(self) -> bool:
        """Check if connected to MQTT broker."""
        return self._connected


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create client
    client = HomeSightMQTTClient()

    # Register callbacks
    def on_discovery(integration, device_id, payload):
        print(f"Discovery: {device_id} ({integration})")
        print(f"  Capabilities: {payload.get('capabilities')}")

    def on_state(device_id, payload):
        print(f"State update: {device_id}")
        print(f"  Values: {payload.get('values')}")

    def on_incident(payload):
        print(f"Incident: {payload.get('title')} ({payload.get('severity')})")
        print(f"  Device: {payload.get('device_id')}")

    client.on_discovery(on_discovery)
    client.on_state(on_state)
    client.on_incident(on_incident)

    # Connect
    client.connect()

    # Keep running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.disconnect()
