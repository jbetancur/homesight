"""
Device Ontology

Provides structured device knowledge to prevent hallucinations.
Loads device list from backend and provides query methods.
"""

import logging
import httpx
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class Device:
    """Device representation"""
    device_id: str
    name: str
    type: str
    location: Optional[str] = None
    zone_id: Optional[str] = None
    capabilities: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class DeviceOntology:
    """
    Device knowledge graph to prevent hallucinations.

    Provides:
    - Device existence checks
    - Room/zone validation
    - Sensor type queries
    - Device capability checks
    """

    def __init__(self, backend_url: str = "http://localhost:8080"):
        self.backend_url = backend_url
        self.devices: Dict[str, Device] = {}
        self.devices_by_zone: Dict[str, List[Device]] = defaultdict(list)
        self.devices_by_type: Dict[str, List[Device]] = defaultdict(list)
        self.zones: Set[str] = set()
        self.device_types: Set[str] = set()
        self._loaded = False

    async def load(self) -> bool:
        """
        Load device list from backend.

        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Fetch devices
                devices_resp = await client.get(f"{self.backend_url}/api/devices")
                if devices_resp.status_code == 200:
                    devices_data = devices_resp.json()
                    await self._process_devices(devices_data)

                # Fetch zones
                zones_resp = await client.get(f"{self.backend_url}/api/zones")
                if zones_resp.status_code == 200:
                    zones_data = zones_resp.json()
                    await self._process_zones(zones_data)

                self._loaded = True
                logger.info(f"Loaded {len(self.devices)} devices across {len(self.zones)} zones")
                return True

        except Exception as e:
            logger.error(f"Failed to load device ontology: {e}")
            return False

    async def _process_devices(self, devices_data: List[Dict[str, Any]]):
        """Process device data from backend"""
        for dev_data in devices_data:
            device = Device(
                device_id=dev_data.get("id", ""),
                name=dev_data.get("name", ""),
                type=dev_data.get("type", "unknown"),
                location=dev_data.get("location"),
                zone_id=dev_data.get("zone_id"),
                capabilities=dev_data.get("capabilities", []),
                metadata=dev_data.get("metadata", {})
            )

            self.devices[device.device_id] = device
            self.device_types.add(device.type)

            # Index by zone
            if device.zone_id:
                self.devices_by_zone[device.zone_id].append(device)
                self.zones.add(device.zone_id)

            # Index by type
            self.devices_by_type[device.type].append(device)

    async def _process_zones(self, zones_data: List[Dict[str, Any]]):
        """Process zone data from backend"""
        for zone_data in zones_data:
            zone_id = zone_data.get("id")
            if zone_id:
                self.zones.add(zone_id)

    def has_temperature_sensor(self, room: Optional[str] = None) -> bool:
        """
        Check if temperature sensor exists in room.

        Args:
            room: Room/zone name (None = any room)

        Returns:
            True if sensor exists
        """
        if not self._loaded:
            logger.warning("Device ontology not loaded")
            return False

        temp_devices = self.devices_by_type.get("temp_sensor", []) + \
                       self.devices_by_type.get("temperature", []) + \
                       self.devices_by_type.get("multisensor", [])

        if room is None:
            return len(temp_devices) > 0

        # Normalize room name
        room_normalized = self.normalize_room_name(room)

        # Check if any device in that room
        for device in temp_devices:
            if device.zone_id and self.normalize_room_name(device.zone_id) == room_normalized:
                return True
            if device.location and self.normalize_room_name(device.location) == room_normalized:
                return True

        return False

    def has_sensor_type(self, sensor_type: str, room: Optional[str] = None) -> bool:
        """
        Check if sensor type exists in room.

        Args:
            sensor_type: Sensor type (leak, motion, contact, etc.)
            room: Room/zone name (None = any room)

        Returns:
            True if sensor exists
        """
        if not self._loaded:
            logger.warning("Device ontology not loaded")
            return False

        devices = self.devices_by_type.get(sensor_type, [])

        if room is None:
            return len(devices) > 0

        # Normalize room name
        room_normalized = self.normalize_room_name(room)

        for device in devices:
            if device.zone_id and self.normalize_room_name(device.zone_id) == room_normalized:
                return True
            if device.location and self.normalize_room_name(device.location) == room_normalized:
                return True

        return False

    def get_valves(self) -> List[Device]:
        """Get all valve devices"""
        if not self._loaded:
            return []

        return self.devices_by_type.get("valve", []) + \
               self.devices_by_type.get("water_valve", [])

    def get_sensors_by_type(self, sensor_type: str) -> List[Device]:
        """Get all sensors of given type"""
        if not self._loaded:
            return []

        return self.devices_by_type.get(sensor_type, [])

    def get_devices_in_room(self, room: str) -> List[Device]:
        """Get all devices in room/zone"""
        if not self._loaded:
            return []

        room_normalized = self.normalize_room_name(room)

        # Check zone_id index
        for zone_id, devices in self.devices_by_zone.items():
            if self.normalize_room_name(zone_id) == room_normalized:
                return devices

        # Fallback: search by location
        matching = []
        for device in self.devices.values():
            if device.location and self.normalize_room_name(device.location) == room_normalized:
                matching.append(device)

        return matching

    def list_rooms(self) -> List[str]:
        """List all known rooms/zones"""
        if not self._loaded:
            return []

        return list(self.zones)

    def normalize_room_name(self, room: str) -> str:
        """
        Normalize room name for comparison.

        Examples:
        - "Bedroom" -> "bedroom"
        - "living room" -> "living_room"
        - "Master Bedroom" -> "master_bedroom"
        """
        if not room:
            return ""

        normalized = room.lower().strip()
        normalized = normalized.replace(' ', '_')
        normalized = normalized.replace('-', '_')

        return normalized

    def has_device(self, device_id: str) -> bool:
        """Check if device exists"""
        return device_id in self.devices

    def get_device(self, device_id: str) -> Optional[Device]:
        """Get device by ID"""
        return self.devices.get(device_id)

    def validate_room(self, room: str) -> bool:
        """
        Validate that room exists.

        Args:
            room: Room name

        Returns:
            True if room exists
        """
        if not self._loaded:
            return False

        room_normalized = self.normalize_room_name(room)

        for zone in self.zones:
            if self.normalize_room_name(zone) == room_normalized:
                return True

        return False

    def get_device_summary(self) -> Dict[str, Any]:
        """
        Get summary of device ontology for LLM context.

        Returns:
            Dictionary with device counts and capabilities
        """
        if not self._loaded:
            return {"status": "not_loaded"}

        summary = {
            "total_devices": len(self.devices),
            "rooms": list(self.zones),
            "device_types": {},
        }

        # Count by type
        for device_type, devices in self.devices_by_type.items():
            summary["device_types"][device_type] = len(devices)

        # Rooms with sensors
        rooms_with_temp = []
        rooms_with_leak = []
        for zone in self.zones:
            if self.has_temperature_sensor(zone):
                rooms_with_temp.append(zone)
            if self.has_sensor_type("leak", zone):
                rooms_with_leak.append(zone)

        summary["rooms_with_temperature"] = rooms_with_temp
        summary["rooms_with_leak_detection"] = rooms_with_leak

        return summary
