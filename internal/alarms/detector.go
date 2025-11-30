package alarms

import (
	"fmt"

	"github.com/homesight/homesight/internal/model"
)

// AlarmCondition represents a detected alarm state
type AlarmCondition struct {
	DeviceID    string
	Key         string // The state key that triggered the alarm
	Value       interface{}
	IsActive    bool // true = alarm ON, false = alarm cleared
	IncidentType model.IncidentType
	Title       string
	Description string
	Severity    model.IncidentSeverity
}

// Detector detects alarm conditions from device state updates
type Detector struct{}

// NewDetector creates a new alarm detector
func NewDetector() *Detector {
	return &Detector{}
}

// DetectAlarm analyzes a device state update and returns an alarm condition if detected
func (d *Detector) DetectAlarm(deviceID string, key string, value interface{}) *AlarmCondition {
	// Z-Wave Notification Command Class (113-0-*)
	if alarm := d.detectZWaveAlarm(deviceID, key, value); alarm != nil {
		return alarm
	}

	// Zigbee IAS Zone alarms
	if alarm := d.detectZigbeeAlarm(deviceID, key, value); alarm != nil {
		return alarm
	}

	// Generic boolean alarms
	if alarm := d.detectGenericAlarm(deviceID, key, value); alarm != nil {
		return alarm
	}

	return nil
}

// detectZWaveAlarm detects Z-Wave Notification Command Class alarms
func (d *Detector) detectZWaveAlarm(deviceID string, key string, value interface{}) *AlarmCondition {
	// Z-Wave alarm format: "113-0-<AlarmType>-Sensor status"
	// Examples:
	// - "113-0-Water Alarm-Sensor status"
	// - "113-0-Home Security-Motion"
	// - "113-0-Home Security-Tamper"
	// - "113-0-Smoke-Alarm status"
	// - "113-0-CO-Alarm status"
	// - "113-0-Heat-Alarm status"

	numValue, ok := value.(float64)
	if !ok {
		// Try int
		if intVal, ok := value.(int); ok {
			numValue = float64(intVal)
		} else {
			return nil
		}
	}

	isActive := numValue != 0

	// Water Leak
	if containsAny(key, []string{"Water Alarm", "water_leak", "leak"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeWaterLeak,
			Title:        "Water Leak Detected",
			Description:  fmt.Sprintf("Water leak sensor triggered (value: %v)", value),
			Severity:     model.SeverityCritical,
		}
	}

	// Smoke Alarm
	if containsAny(key, []string{"Smoke", "smoke_alarm"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeSmoke,
			Title:        "Smoke Detected",
			Description:  fmt.Sprintf("Smoke alarm triggered (value: %v)", value),
			Severity:     model.SeverityCritical,
		}
	}

	// CO Alarm
	if containsAny(key, []string{"CO-", "co_alarm", "carbon_monoxide"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeCO,
			Title:        "Carbon Monoxide Detected",
			Description:  fmt.Sprintf("CO alarm triggered (value: %v)", value),
			Severity:     model.SeverityCritical,
		}
	}

	// Heat Alarm
	if containsAny(key, []string{"Heat-", "heat_alarm", "overheat"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeHeat,
			Title:        "Heat Alarm",
			Description:  fmt.Sprintf("Heat alarm triggered (value: %v)", value),
			Severity:     model.SeverityHigh,
		}
	}

	// Motion Alarm (Home Security - Motion)
	if containsAny(key, []string{"Motion", "motion_alarm"}) && containsAny(key, []string{"Security", "Alarm"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeMotion,
			Title:        "Motion Detected",
			Description:  fmt.Sprintf("Security motion sensor triggered (value: %v)", value),
			Severity:     model.SeverityMedium,
		}
	}

	// Tamper Alarm
	if containsAny(key, []string{"Tamper", "tamper_alarm"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeTamper,
			Title:        "Tamper Alert",
			Description:  fmt.Sprintf("Device tamper detected (value: %v)", value),
			Severity:     model.SeverityHigh,
		}
	}

	// Contact/Door Alarm
	if containsAny(key, []string{"Contact", "contact_alarm", "Door", "Window"}) && containsAny(key, []string{"Security", "Alarm", "forced"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeContact,
			Title:        "Contact Alarm",
			Description:  fmt.Sprintf("Door/window forced open (value: %v)", value),
			Severity:     model.SeverityHigh,
		}
	}

	// Burglar Alarm
	if containsAny(key, []string{"Burglar", "burglar_alarm", "intrusion"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeBurglar,
			Title:        "Burglar Alarm",
			Description:  fmt.Sprintf("Intrusion detected (value: %v)", value),
			Severity:     model.SeverityCritical,
		}
	}

	// Glass Break
	if containsAny(key, []string{"Glass", "glass_break"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeGlassBreak,
			Title:        "Glass Break Detected",
			Description:  fmt.Sprintf("Glass break sensor triggered (value: %v)", value),
			Severity:     model.SeverityCritical,
		}
	}

	// Freeze Alarm
	if containsAny(key, []string{"Freeze", "freeze_alarm"}) {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeFreeze,
			Title:        "Freeze Alert",
			Description:  fmt.Sprintf("Freeze alarm triggered (value: %v)", value),
			Severity:     model.SeverityHigh,
		}
	}

	return nil
}

// detectZigbeeAlarm detects Zigbee IAS Zone alarms
func (d *Detector) detectZigbeeAlarm(deviceID string, key string, value interface{}) *AlarmCondition {
	// Zigbee IAS Zone uses zoneStatus or alarm boolean flags
	if key == "zone_status" || key == "zoneStatus" {
		numValue, ok := value.(float64)
		if !ok {
			if intVal, ok := value.(int); ok {
				numValue = float64(intVal)
			} else {
				return nil
			}
		}

		isActive := numValue != 0

		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     isActive,
			IncidentType: model.IncidentTypeGeneric,
			Title:        "Alarm Triggered",
			Description:  fmt.Sprintf("IAS Zone alarm (zone_status: %v)", value),
			Severity:     model.SeverityHigh,
		}
	}

	return nil
}

// detectGenericAlarm detects generic boolean alarm conditions
func (d *Detector) detectGenericAlarm(deviceID string, key string, value interface{}) *AlarmCondition {
	// Check for boolean alarm flags
	boolValue, isBool := value.(bool)
	if !isBool {
		return nil
	}

	// Motion (non-security, just presence)
	if key == "motion" || key == "occupancy" {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     boolValue,
			IncidentType: model.IncidentTypeMotion,
			Title:        "Motion Detected",
			Description:  "Motion sensor activated",
			Severity:     model.SeverityInfo,
		}
	}

	// Contact sensor (open/closed)
	if key == "contact" || key == "open" {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     boolValue,
			IncidentType: model.IncidentTypeContact,
			Title:        "Contact Opened",
			Description:  "Door/window contact opened",
			Severity:     model.SeverityInfo,
		}
	}

	// Tamper
	if key == "tamper" {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     boolValue,
			IncidentType: model.IncidentTypeTamper,
			Title:        "Tamper Alert",
			Description:  "Device tamper detected",
			Severity:     model.SeverityHigh,
		}
	}

	// Water leak
	if key == "water_leak" || key == "leak" {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     boolValue,
			IncidentType: model.IncidentTypeWaterLeak,
			Title:        "Water Leak Detected",
			Description:  "Water leak sensor triggered",
			Severity:     model.SeverityCritical,
		}
	}

	// Power overload
	if key == "overload" || key == "power_overload" {
		return &AlarmCondition{
			DeviceID:     deviceID,
			Key:          key,
			Value:        value,
			IsActive:     boolValue,
			IncidentType: model.IncidentTypePower,
			Title:        "Power Overload",
			Description:  "Power overload detected",
			Severity:     model.SeverityHigh,
		}
	}

	return nil
}

// containsAny checks if a string contains any of the substrings
func containsAny(s string, substrings []string) bool {
	for _, substr := range substrings {
		if contains(s, substr) {
			return true
		}
	}
	return false
}

// contains is a simple case-insensitive substring check
func contains(s, substr string) bool {
	// Simple implementation - could use strings.Contains with ToLower for case-insensitive
	sLower := toLower(s)
	substrLower := toLower(substr)
	return indexOfSubstring(sLower, substrLower) >= 0
}

func toLower(s string) string {
	result := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'A' && c <= 'Z' {
			result[i] = c + ('a' - 'A')
		} else {
			result[i] = c
		}
	}
	return string(result)
}

func indexOfSubstring(s, substr string) int {
	if len(substr) == 0 {
		return 0
	}
	if len(substr) > len(s) {
		return -1
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		match := true
		for j := 0; j < len(substr); j++ {
			if s[i+j] != substr[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}
