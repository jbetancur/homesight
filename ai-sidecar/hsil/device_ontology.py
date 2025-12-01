"""
Device Ontology

Provides structured device knowledge to prevent hallucinations.
Loads device list from backend and provides query methods.
Includes zone attributes for HIL reasoning.
"""

import logging
import httpx
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
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


@dataclass
class ZoneAttributes:
    """Zone attributes for HIL reasoning"""
    # Physical characteristics
    floor_type: Optional[str] = None  # hardwood, tile, carpet, concrete, laminate
    square_feet: int = 0
    has_windows: bool = False
    has_fireplace: bool = False
    
    # HVAC/Climate
    has_hvac_return: bool = False
    has_hvac_vent: bool = False
    has_radiant_heat: bool = False
    has_ceiling_fan: bool = False
    
    # Water/Plumbing
    has_plumbing: bool = False
    has_water_heater: bool = False
    has_washer: bool = False
    has_sump_pump: bool = False
    
    # Risk factors & Occupancy
    has_valuables: bool = False
    has_pets: bool = False
    has_infant: bool = False
    has_elderly: bool = False
    is_occupied_daily: bool = False
    
    # Custom tags
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ZoneAttributes":
        """Create from API response dict"""
        if not data:
            return cls()
        return cls(
            floor_type=data.get("floor_type"),
            square_feet=data.get("square_feet", 0),
            has_windows=data.get("has_windows", False),
            has_fireplace=data.get("has_fireplace", False),
            has_hvac_return=data.get("has_hvac_return", False),
            has_hvac_vent=data.get("has_hvac_vent", False),
            has_radiant_heat=data.get("has_radiant_heat", False),
            has_ceiling_fan=data.get("has_ceiling_fan", False),
            has_plumbing=data.get("has_plumbing", False),
            has_water_heater=data.get("has_water_heater", False),
            has_washer=data.get("has_washer", False),
            has_sump_pump=data.get("has_sump_pump", False),
            has_valuables=data.get("has_valuables", False),
            has_pets=data.get("has_pets", False),
            has_infant=data.get("has_infant", False),
            has_elderly=data.get("has_elderly", False),
            is_occupied_daily=data.get("is_occupied_daily", False),
            tags=data.get("tags", []),
        )


@dataclass
class Zone:
    """Zone/Room representation with attributes"""
    zone_id: str
    name: str
    type: str
    home_id: str = "default"
    attributes: ZoneAttributes = field(default_factory=ZoneAttributes)


class DeviceOntology:
    """
    Device knowledge graph to prevent hallucinations.

    Provides:
    - Device existence checks
    - Room/zone validation
    - Sensor type queries
    - Device capability checks
    - Zone attributes for HIL reasoning
    """

    def __init__(self, backend_url: str = "http://localhost:8080"):
        self.backend_url = backend_url
        self.devices: Dict[str, Device] = {}
        self.devices_by_zone: Dict[str, List[Device]] = defaultdict(list)
        self.devices_by_type: Dict[str, List[Device]] = defaultdict(list)
        self.zones: Dict[str, Zone] = {}  # zone_id -> Zone with attributes
        self.zone_ids: Set[str] = set()
        self.device_types: Set[str] = set()
        self._loaded = False
        logger.info(f"DeviceOntology initialized with backend_url={backend_url}")

    async def load(self) -> bool:
        """
        Load device list from backend.
        
        Retries up to 3 times with backoff for transient failures.

        Returns:
            True if successful, False otherwise
        """
        max_retries = 3
        retry_delay = 3.0  # seconds
        
        logger.info(f"Attempting to load device ontology from {self.backend_url}...")
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    logger.debug(f"Attempt {attempt + 1}/{max_retries}: Fetching devices...")
                    
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
                    logger.info(f"✅ Loaded {len(self.devices)} devices across {len(self.zone_ids)} zones")
                    return True

            except httpx.ConnectError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Connection failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay * (attempt + 1)}s...")
                    import asyncio
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"❌ Failed to connect to backend after {max_retries} attempts. Is the backend running at {self.backend_url}?")
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to load device ontology (attempt {attempt + 1}/{max_retries}): {e}")
                    import asyncio
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to load device ontology after {max_retries} attempts: {e}")
                    return False
        
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
                self.zone_ids.add(device.zone_id)

            # Index by type
            self.devices_by_type[device.type].append(device)

    async def _process_zones(self, zones_data: List[Dict[str, Any]]):
        """Process zone data from backend with attributes"""
        for zone_data in zones_data:
            zone_id = zone_data.get("id")
            if zone_id:
                self.zone_ids.add(zone_id)
                
                # Parse zone attributes
                attributes = ZoneAttributes.from_dict(zone_data.get("attributes"))
                
                zone = Zone(
                    zone_id=zone_id,
                    name=zone_data.get("name", zone_id),
                    type=zone_data.get("type", "unknown"),
                    home_id=zone_data.get("home_id", "default"),
                    attributes=attributes
                )
                self.zones[zone_id] = zone

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

        return list(self.zone_ids)

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

        for zone_id in self.zone_ids:
            if self.normalize_room_name(zone_id) == room_normalized:
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
            "rooms": list(self.zone_ids),
            "device_types": {},
        }

        # Count by type
        for device_type, devices in self.devices_by_type.items():
            summary["device_types"][device_type] = len(devices)

        # Rooms with sensors
        rooms_with_temp = []
        rooms_with_leak = []
        for zone_id in self.zone_ids:
            if self.has_temperature_sensor(zone_id):
                rooms_with_temp.append(zone_id)
            if self.has_sensor_type("leak", zone_id):
                rooms_with_leak.append(zone_id)

        summary["rooms_with_temperature"] = rooms_with_temp
        summary["rooms_with_leak_detection"] = rooms_with_leak
        
        # Low battery device alerts
        low_battery_devices = []
        for device in self.devices.values():
            if device.metadata and device.metadata.get("battery_level"):
                try:
                    battery = int(device.metadata.get("battery_level"))
                    if battery < 20:
                        low_battery_devices.append(f"{device.name} ({battery}%)")
                except (ValueError, TypeError):
                    pass
        if low_battery_devices:
            summary["low_battery_alerts"] = low_battery_devices
        
        # Zone details with attributes
        summary["zone_details"] = {}
        for zone_id, zone in self.zones.items():
            # Get devices with more detail (name, type, battery, readings)
            zone_devices = self.devices_by_zone.get(zone_id, [])
            device_list = []
            for d in zone_devices:
                device_info = f"{d.name} ({d.type})"
                # Include sensor readings if available
                readings = self._extract_sensor_readings(d.metadata)
                if readings:
                    device_info += f" [{readings}]"
                # Include battery level if available
                elif d.metadata and d.metadata.get("battery_level"):
                    battery = d.metadata.get("battery_level")
                    device_info += f" [Battery: {battery}%]"
                device_list.append(device_info)
            
            zone_info = {
                "name": zone.name,
                "type": zone.type,
                "devices": device_list,
                "device_count": len(zone_devices),
            }
            # Include relevant attributes
            attrs = zone.attributes
            attr_list = []
            if attrs.floor_type:
                attr_list.append(f"floor: {attrs.floor_type}")
            if attrs.has_plumbing:
                attr_list.append("plumbing")
            if attrs.has_hvac_return:
                attr_list.append("HVAC return")
            if attrs.has_hvac_vent:
                attr_list.append("HVAC vent")
            if attrs.has_water_heater:
                attr_list.append("water heater")
            if attrs.has_washer:
                attr_list.append("washer/dryer")
            if attrs.has_sump_pump:
                attr_list.append("sump pump")
            if attrs.has_valuables:
                attr_list.append("valuables")
            if attrs.has_pets:
                attr_list.append("pets")
            if attrs.has_infant:
                attr_list.append("infant")
            if attrs.has_elderly:
                attr_list.append("elderly")
            if attr_list:
                zone_info["attributes"] = attr_list
            summary["zone_details"][zone_id] = zone_info

        return summary
    
    # ==================== Zone Attributes Methods ====================
    
    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Get zone by ID with attributes"""
        return self.zones.get(zone_id)
    
    def get_zone_attributes(self, zone_id: str) -> Optional[ZoneAttributes]:
        """Get attributes for a zone"""
        zone = self.zones.get(zone_id)
        return zone.attributes if zone else None
    
    def has_hardwood_floors(self, zone_id: str) -> bool:
        """Check if zone has hardwood floors (important for water damage)"""
        attrs = self.get_zone_attributes(zone_id)
        return attrs and attrs.floor_type == "hardwood"
    
    def has_plumbing(self, zone_id: str) -> bool:
        """Check if zone has plumbing (expected water sources)"""
        attrs = self.get_zone_attributes(zone_id)
        return attrs and attrs.has_plumbing
    
    def has_hvac_return(self, zone_id: str) -> bool:
        """Check if zone has HVAC return (important for smoke spread)"""
        attrs = self.get_zone_attributes(zone_id)
        return attrs and attrs.has_hvac_return
    
    def has_vulnerable_occupants(self, zone_id: str) -> bool:
        """Check if zone has infants or elderly (higher priority)"""
        attrs = self.get_zone_attributes(zone_id)
        return attrs and (attrs.has_infant or attrs.has_elderly)
    
    def get_risk_factors(self, zone_id: str) -> List[str]:
        """Get list of risk factors for a zone"""
        attrs = self.get_zone_attributes(zone_id)
        if not attrs:
            return []
        
        factors = []
        if attrs.floor_type == "hardwood":
            factors.append("hardwood_floors")
        if attrs.has_valuables:
            factors.append("valuables")
        if attrs.has_infant:
            factors.append("infant")
        if attrs.has_elderly:
            factors.append("elderly")
        if attrs.has_water_heater:
            factors.append("water_heater")
        if attrs.has_sump_pump:
            factors.append("sump_pump")
        if attrs.has_hvac_return:
            factors.append("hvac_return")
        
        return factors
    
    def get_zone_context_for_llm(self, zone_id: str) -> str:
        """Get zone context string for LLM prompts"""
        zone = self.zones.get(zone_id)
        if not zone:
            return f"Zone: {zone_id} (no details available)"
        
        attrs = zone.attributes
        details = [f"Zone: {zone.name} ({zone.type})"]
        
        if attrs.floor_type:
            details.append(f"Floor: {attrs.floor_type}")
        if attrs.has_plumbing:
            details.append("Has plumbing")
        if attrs.has_hvac_return:
            details.append("Has HVAC return")
        if attrs.has_sump_pump:
            details.append("Has sump pump")
        if attrs.has_infant:
            details.append("⚠️ Infant present")
        if attrs.has_elderly:
            details.append("⚠️ Elderly occupant")
        if attrs.has_valuables:
            details.append("Contains valuables")
        if attrs.tags:
            details.append(f"Tags: {', '.join(attrs.tags)}")
        
        return " | ".join(details)

    # ==================== Battery Methods ====================
    
    def get_low_battery_devices(self, threshold: int = 20) -> List[Device]:
        """Get devices with low battery (below threshold percentage)"""
        low_battery = []
        for device in self.devices.values():
            if device.metadata and device.metadata.get("battery_level"):
                try:
                    battery = int(device.metadata.get("battery_level"))
                    if battery < threshold:
                        low_battery.append(device)
                except (ValueError, TypeError):
                    pass
        return low_battery
    
    def get_device_battery_summary(self) -> Dict[str, Any]:
        """Get summary of battery-powered devices"""
        battery_devices = []
        for device in self.devices.values():
            if device.metadata and device.metadata.get("battery_level"):
                try:
                    battery = int(device.metadata.get("battery_level"))
                    battery_devices.append({
                        "device_id": device.device_id,
                        "name": device.name,
                        "type": device.type,
                        "location": device.location,
                        "battery_level": battery
                    })
                except (ValueError, TypeError):
                    pass
        
        # Sort by battery level (lowest first)
        battery_devices.sort(key=lambda d: d["battery_level"])
        
        low_count = sum(1 for d in battery_devices if d["battery_level"] < 20)
        
        return {
            "total_battery_devices": len(battery_devices),
            "low_battery_count": low_count,
            "devices": battery_devices
        }

    # ==================== Sensor Reading Methods ====================
    
    def _extract_sensor_readings(self, metadata: Optional[Dict[str, Any]]) -> str:
        """Extract sensor readings from device metadata and format as string"""
        if not metadata:
            return ""
        
        readings = []
        
        # Check for Z-Wave style values (value_<property>)
        # Check for MQTT style values (state_<property>)
        # Check for direct properties
        reading_keys = {
            'temperature': ['value_temperature', 'state_temperature', 'temperature'],
            'humidity': ['value_humidity', 'state_humidity', 'humidity'],
            'leak': ['value_leak', 'state_leak', 'leak', 'value_water', 'state_water'],
            'motion': ['value_motion', 'state_motion', 'motion'],
            'contact': ['value_contact', 'state_contact', 'contact'],
            'power': ['value_power', 'state_power', 'power'],
            'energy': ['value_energy', 'state_energy', 'energy'],
            'brightness': ['value_brightness', 'state_brightness', 'brightness', 'value_level'],
        }
        
        for reading_type, keys in reading_keys.items():
            for key in keys:
                if key in metadata:
                    value = metadata[key]
                    formatted = self._format_reading(reading_type, value)
                    if formatted:
                        readings.append(formatted)
                    break  # Only use first match for each type
        
        # Always include battery if available
        if metadata.get('battery_level'):
            readings.append(f"Battery: {metadata['battery_level']}%")
        
        return ", ".join(readings) if readings else ""
    
    def _format_reading(self, reading_type: str, value: Any) -> Optional[str]:
        """Format a single sensor reading for display"""
        try:
            if reading_type == 'temperature':
                return f"Temp: {float(value):.1f}°"
            elif reading_type == 'humidity':
                return f"Humidity: {float(value):.0f}%"
            elif reading_type == 'leak':
                is_leak = str(value).lower() in ('true', '1', 'yes', 'wet')
                return "⚠️ LEAK DETECTED" if is_leak else "Dry"
            elif reading_type == 'motion':
                has_motion = str(value).lower() in ('true', '1', 'yes')
                return "Motion detected" if has_motion else None  # Only show if motion
            elif reading_type == 'contact':
                is_open = str(value).lower() in ('false', '0', 'open')
                return "Open" if is_open else "Closed"
            elif reading_type == 'power':
                return f"Power: {float(value):.1f}W"
            elif reading_type == 'energy':
                return f"Energy: {float(value):.2f}kWh"
            elif reading_type == 'brightness':
                return f"Brightness: {int(float(value))}%"
            else:
                return f"{reading_type}: {value}"
        except (ValueError, TypeError):
            return None
    
    def get_device_readings(self, device_id: str) -> Dict[str, Any]:
        """Get current sensor readings for a specific device"""
        device = self.devices.get(device_id)
        if not device or not device.metadata:
            return {}
        
        readings = {}
        reading_keys = ['temperature', 'humidity', 'leak', 'motion', 'contact', 
                       'power', 'energy', 'brightness', 'battery_level']
        
        for key in reading_keys:
            # Check direct key
            if key in device.metadata:
                readings[key] = device.metadata[key]
            # Check value_ prefix (Z-Wave)
            elif f"value_{key}" in device.metadata:
                readings[key] = device.metadata[f"value_{key}"]
            # Check state_ prefix (MQTT)
            elif f"state_{key}" in device.metadata:
                readings[key] = device.metadata[f"state_{key}"]
        
        return readings
