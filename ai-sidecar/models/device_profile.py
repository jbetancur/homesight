"""
Device Profile - Structured device ontology for HomeSight

This module provides a type-safe, validated device representation that replaces
the Dict[str, Any] pattern used throughout the codebase.

Key benefits:
- Type safety: Catch errors at edit-time, not runtime
- Validation: Pydantic ensures data quality
- Extensibility: Easy to add new device types
- Documentation: Self-documenting device capabilities
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DeviceType(str, Enum):
    """
    Device type taxonomy for home automation devices.

    Categories:
    - SENSOR_*: Read-only sensing devices
    - ACTUATOR_*: Control/output devices
    - HUB: Coordination/gateway devices
    - CAMERA: Video/image capture
    - SECURITY: Security-specific devices
    - ENERGY: Power monitoring/control
    """
    # Sensors
    SENSOR_MOTION = "motion_sensor"
    SENSOR_DOOR = "door_sensor"
    SENSOR_WINDOW = "window_sensor"
    SENSOR_TEMPERATURE = "temperature_sensor"
    SENSOR_HUMIDITY = "humidity_sensor"
    SENSOR_LEAK = "leak_sensor"
    SENSOR_SMOKE = "smoke_detector"
    SENSOR_CO = "carbon_monoxide_detector"
    SENSOR_LIGHT = "light_sensor"
    SENSOR_VIBRATION = "vibration_sensor"
    SENSOR_CONTACT = "contact_sensor"
    SENSOR_MULTI = "multi_sensor"  # Combined temp/humidity/motion

    # Actuators
    ACTUATOR_SWITCH = "switch"
    ACTUATOR_DIMMER = "dimmer"
    ACTUATOR_OUTLET = "smart_outlet"
    ACTUATOR_LOCK = "smart_lock"
    ACTUATOR_THERMOSTAT = "thermostat"
    ACTUATOR_VALVE = "valve"
    ACTUATOR_GARAGE = "garage_door_opener"
    ACTUATOR_BLIND = "smart_blind"
    ACTUATOR_FAN = "smart_fan"

    # Infrastructure
    HUB = "hub"
    REPEATER = "repeater"
    BRIDGE = "bridge"

    # Video
    CAMERA_INDOOR = "indoor_camera"
    CAMERA_OUTDOOR = "outdoor_camera"
    CAMERA_DOORBELL = "video_doorbell"

    # Security
    SECURITY_KEYPAD = "security_keypad"
    SECURITY_SIREN = "siren"

    # Energy
    ENERGY_MONITOR = "energy_monitor"
    ENERGY_METER = "smart_meter"

    # Other
    BUTTON = "button"
    REMOTE = "remote_control"
    UNKNOWN = "unknown"


class PowerSource(str, Enum):
    """Device power source type"""
    BATTERY = "battery"
    AC_POWERED = "ac_powered"
    USB = "usb"
    POE = "poe"  # Power over Ethernet
    HARDWIRED = "hardwired"
    SOLAR = "solar"
    HYBRID = "hybrid"  # Multiple sources (e.g., AC + battery backup)
    UNKNOWN = "unknown"


class Protocol(str, Enum):
    """Communication protocol"""
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    BLUETOOTH_LE = "ble"
    THREAD = "thread"
    MATTER = "matter"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class BatteryType(str, Enum):
    """Common battery types in home automation"""
    CR2032 = "CR2032"  # Coin cell (most sensors)
    CR2450 = "CR2450"
    CR123A = "CR123A"
    AA = "AA"
    AAA = "AAA"
    NINE_VOLT = "9V"
    RECHARGEABLE = "rechargeable"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class DeviceCapability(str, Enum):
    """Device capabilities/features for filtering and tool selection"""
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    MOTION = "motion"
    CONTACT = "contact"
    BATTERY_LEVEL = "battery_level"
    TAMPER_DETECTION = "tamper"
    ON_OFF = "on_off"
    DIMMING = "dimming"
    COLOR_CONTROL = "color"
    LOCKING = "lock"
    VIDEO_STREAM = "video"
    AUDIO = "audio"
    TWO_WAY_AUDIO = "two_way_audio"
    NIGHT_VISION = "night_vision"
    POWER_METERING = "power_metering"
    OCCUPANCY = "occupancy"
    VIBRATION = "vibration"
    LEAK_DETECTION = "leak"
    SMOKE_DETECTION = "smoke"
    CO_DETECTION = "co"


class DocumentStatus(str, Enum):
    """Documentation ingestion status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL = "partial"  # Some docs found, not all
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"


class DeviceProfile(BaseModel):
    """
    Comprehensive device profile with full metadata and documentation status.

    This replaces the Dict[str, Any] pattern and provides type safety,
    validation, and clear schema for device information.

    Example:
        device = DeviceProfile(
            id="dev_abc123",
            manufacturer="Aqara",
            model="SNZB-02",
            device_type=DeviceType.SENSOR_TEMPERATURE,
            protocol=Protocol.ZIGBEE,
            power_source=PowerSource.BATTERY,
            battery_type=BatteryType.CR2032,
            capabilities=[
                DeviceCapability.TEMPERATURE,
                DeviceCapability.HUMIDITY,
                DeviceCapability.BATTERY_LEVEL
            ]
        )
    """

    # Core identification
    id: str = Field(..., description="Unique device ID")
    manufacturer: str = Field(..., description="Manufacturer name (e.g., 'Aqara', 'Philips')")
    model: str = Field(..., description="Model number/identifier")
    device_type: DeviceType = Field(default=DeviceType.UNKNOWN, description="Device type category")

    # Technical specifications
    protocol: Protocol = Field(default=Protocol.UNKNOWN, description="Communication protocol")
    power_source: PowerSource = Field(default=PowerSource.UNKNOWN, description="Power source type")
    battery_type: Optional[BatteryType] = Field(default=None, description="Battery type if battery-powered")

    # Optional metadata
    firmware_version: Optional[str] = Field(default=None, description="Current firmware version")
    hardware_version: Optional[str] = Field(default=None, description="Hardware revision")
    serial_number: Optional[str] = Field(default=None, description="Device serial number")

    # Capabilities
    capabilities: List[DeviceCapability] = Field(
        default_factory=list,
        description="List of device capabilities/features"
    )

    # User-facing info
    name: Optional[str] = Field(default=None, description="User-assigned friendly name")
    location: Optional[str] = Field(default=None, description="Physical location (e.g., 'Living Room', 'Front Door')")

    # Documentation tracking
    has_official_docs: bool = Field(default=False, description="Whether official manufacturer docs were found")
    docs_status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="Documentation ingestion status")
    docs_ingested_at: Optional[datetime] = Field(default=None, description="When documentation was last ingested")
    docs_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Documentation confidence score (0-1)")
    docs_sources: List[str] = Field(
        default_factory=list,
        description="Sources of documentation (e.g., ['official_pdf', 'ai_generated'])"
    )

    # Extensibility
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for future extensibility"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(default=None, description="When device was added to system")
    updated_at: Optional[datetime] = Field(default=None, description="Last metadata update")

    @field_validator('manufacturer', 'model')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace from manufacturer and model"""
        if v:
            return v.strip()
        return v

    @field_validator('manufacturer', 'model')
    @classmethod
    def not_empty(cls, v: str) -> str:
        """Ensure manufacturer and model are not empty"""
        if not v or not v.strip():
            raise ValueError("Manufacturer and model cannot be empty")
        return v

    def is_battery_powered(self) -> bool:
        """Check if device is battery-powered"""
        return self.power_source in [PowerSource.BATTERY, PowerSource.HYBRID]

    def is_sensor(self) -> bool:
        """Check if device is a sensor (read-only)"""
        # Handle both enum and string (due to use_enum_values)
        dtype = self.device_type if isinstance(self.device_type, str) else self.device_type.value
        # Sensors have either "*_sensor" suffix or "*_detector" suffix
        return dtype.endswith("_sensor") or dtype.endswith("_detector") or dtype == "multi_sensor"

    def is_actuator(self) -> bool:
        """Check if device is an actuator (controllable)"""
        # Handle both enum and string (due to use_enum_values)
        dtype = self.device_type if isinstance(self.device_type, str) else self.device_type.value
        # Actuators include switches, outlets, locks, etc.
        actuator_types = {
            "switch", "dimmer", "smart_outlet", "smart_lock", "thermostat",
            "valve", "garage_door_opener", "smart_blind", "smart_fan"
        }
        return dtype in actuator_types

    def has_capability(self, capability: DeviceCapability) -> bool:
        """Check if device has a specific capability"""
        return capability in self.capabilities

    def can_reset(self) -> bool:
        """Check if device supports reset operations"""
        # Most devices can be reset, but some infrastructure cannot
        return self.device_type not in [DeviceType.HUB, DeviceType.BRIDGE]

    def supports_settings_update(self) -> bool:
        """Check if device supports settings configuration"""
        # Actuators and some sensors support settings
        return self.is_actuator() or self.device_type in [
            DeviceType.SENSOR_MULTI,
            DeviceType.CAMERA_INDOOR,
            DeviceType.CAMERA_OUTDOOR,
            DeviceType.CAMERA_DOORBELL
        ]

    def needs_docs_refresh(self, max_age_days: int = 90) -> bool:
        """Check if documentation should be refreshed"""
        if self.docs_status in [DocumentStatus.FAILED, DocumentStatus.NOT_AVAILABLE]:
            return True

        if not self.docs_ingested_at:
            return True

        age_days = (datetime.utcnow() - self.docs_ingested_at).days
        return age_days > max_age_days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceProfile":
        """
        Create DeviceProfile from dictionary (for backward compatibility).

        Handles legacy Dict[str, Any] format used throughout codebase.
        Attempts to map fields intelligently with fallbacks.
        """
        # Extract core fields with fallbacks
        device_id = data.get("id") or data.get("device_id") or ""
        manufacturer = data.get("manufacturer", "Unknown")
        model = data.get("model", "Unknown")

        # Map device type
        type_str = data.get("type") or data.get("device_type") or "unknown"
        try:
            device_type = DeviceType(type_str)
        except ValueError:
            device_type = DeviceType.UNKNOWN

        # Create profile with available data
        return cls(
            id=device_id,
            manufacturer=manufacturer,
            model=model,
            device_type=device_type,
            name=data.get("name"),
            location=data.get("location"),
            firmware_version=data.get("firmware_version"),
            extra_metadata=data.get("metadata", {})
        )

    class Config:
        use_enum_values = True  # Serialize enums as their values
        json_schema_extra = {
            "example": {
                "id": "dev_abc123",
                "manufacturer": "Aqara",
                "model": "SNZB-02",
                "device_type": "temperature_sensor",
                "protocol": "zigbee",
                "power_source": "battery",
                "battery_type": "CR2032",
                "capabilities": ["temperature", "humidity", "battery_level"],
                "name": "Living Room Temp Sensor",
                "location": "Living Room",
                "has_official_docs": True,
                "docs_status": "success",
                "docs_confidence": 0.90,
                "docs_sources": ["official_pdf"]
            }
        }


class DeviceEvent(BaseModel):
    """
    Device lifecycle event.

    Used for event-driven document ingestion and processing.
    """
    type: str = Field(..., description="Event type (e.g., 'device.created', 'device.updated')")
    data: Dict[str, Any] = Field(..., description="Event payload (will be converted to DeviceProfile)")
    force: bool = Field(default=False, description="Force refresh/re-ingest flag")

    def to_device_profile(self) -> DeviceProfile:
        """Convert event data to DeviceProfile"""
        return DeviceProfile.from_dict(self.data)


# Legacy compatibility - keep old DeviceInfo for gradual migration
class DeviceInfo(BaseModel):
    """
    DEPRECATED: Use DeviceProfile instead.

    Kept for backward compatibility during migration.
    Will be removed in future version.
    """
    device_id: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_profile(self) -> DeviceProfile:
        """Convert legacy DeviceInfo to DeviceProfile"""
        return DeviceProfile.from_dict({
            "id": self.device_id,
            "manufacturer": self.manufacturer or "Unknown",
            "model": self.model or "Unknown",
            "type": self.type or "unknown",
            "metadata": self.metadata or {}
        })
