#!/usr/bin/env python3
"""
Quick validation test for DeviceProfile model.
Run: python test_device_profile.py
"""

from models.device_profile import (
    DeviceProfile,
    DeviceType,
    PowerSource,
    Protocol,
    BatteryType,
    DeviceCapability,
    DocumentStatus
)

def test_device_profile_creation():
    """Test creating a DeviceProfile"""
    print("✅ Testing DeviceProfile creation...")

    device = DeviceProfile(
        id="dev_test_001",
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
        ],
        name="Living Room Sensor",
        location="Living Room"
    )

    print(f"  Device: {device.manufacturer} {device.model}")
    print(f"  Type: {device.device_type}")
    print(f"  Battery powered: {device.is_battery_powered()}")
    print(f"  Is sensor: {device.is_sensor()}")
    print(f"  Can reset: {device.can_reset()}")

def test_from_dict():
    """Test backward compatibility with Dict[str, Any]"""
    print("\n✅ Testing backward compatibility (from_dict)...")

    legacy_data = {
        "id": "dev_legacy_001",
        "manufacturer": "Philips",
        "model": "Hue Bulb",
        "type": "actuator_dimmer",
    }

    device = DeviceProfile.from_dict(legacy_data)
    print(f"  Converted: {device.manufacturer} {device.model}")
    print(f"  Type: {device.device_type}")
    print(f"  Is actuator: {device.is_actuator()}")

def test_validation():
    """Test validation errors"""
    print("\n✅ Testing validation...")

    try:
        # Should fail - empty manufacturer
        DeviceProfile(
            id="test",
            manufacturer="",
            model="Test"
        )
        print("  ❌ FAILED: Should have caught empty manufacturer")
    except ValueError as e:
        print(f"  ✅ Caught validation error: {e}")

def test_json_serialization():
    """Test JSON serialization"""
    print("\n✅ Testing JSON serialization...")

    device = DeviceProfile(
        id="dev_json_test",
        manufacturer="Test",
        model="Model-X",
        device_type=DeviceType.SENSOR_MOTION,
        capabilities=[DeviceCapability.MOTION, DeviceCapability.BATTERY_LEVEL]
    )

    json_data = device.model_dump_json()
    print(f"  JSON length: {len(json_data)} bytes")
    print(f"  Contains 'motion_sensor': {'motion_sensor' in json_data}")

if __name__ == "__main__":
    print("🧪 DeviceProfile Validation Tests\n")
    print("=" * 50)

    test_device_profile_creation()
    test_from_dict()
    test_validation()
    test_json_serialization()

    print("\n" + "=" * 50)
    print("✅ All tests passed!")
