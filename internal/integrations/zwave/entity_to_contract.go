package zwave

import (
	"log"
	"strings"

	"github.com/homesight/homesight/internal/model"
)

// PopulateUnifiedContractFromEntities populates the unified contract fields
// (readings, battery, controls) from the device entities
func PopulateUnifiedContractFromEntities(device *model.Device) {
	if device.Entities == nil || len(device.Entities) == 0 {
		return
	}

	// Initialize contract fields if nil
	if device.Readings == nil {
		device.Readings = &model.DeviceReadings{}
	}
	if device.Battery == nil && hasBatteryEntity(device.Entities) {
		device.Battery = &model.DeviceBattery{}
	}
	if device.Controls == nil && hasControlEntity(device.Entities) {
		device.Controls = &model.DeviceControls{}
	}

	// Map entities to contract fields
	for _, entity := range device.Entities {
		mapEntityToContract(device, &entity)
	}
}

// hasBatteryEntity checks if there's a battery entity
func hasBatteryEntity(entities []model.DeviceEntity) bool {
	for _, e := range entities {
		if cc, ok := e.Metadata["command_class"].(float64); ok && int(cc) == CC_BATTERY {
			return true
		}
	}
	return false
}

// hasControlEntity checks if there's a control entity
func hasControlEntity(entities []model.DeviceEntity) bool {
	for _, e := range entities {
		if e.EntityType == model.EntityTypeSwitch && e.Settable {
			return true
		}
	}
	return false
}

// mapEntityToContract maps a single entity to the appropriate contract field
func mapEntityToContract(device *model.Device, entity *model.DeviceEntity) {
	// Get command class from metadata (can be int or float64 depending on JSON unmarshaling)
	ccInt := 0
	if cc, ok := entity.Metadata["command_class"].(float64); ok {
		ccInt = int(cc)
	} else if cc, ok := entity.Metadata["command_class"].(int); ok {
		ccInt = cc
	}

	// Get command class name
	ccName := ""
	if name, ok := entity.Metadata["command_class_name"].(string); ok {
		ccName = strings.ToLower(name)
	}

	propName := strings.ToLower(entity.Name)

	log.Printf("[ENTITY-MAPPER] Mapping entity: %s (CC %d/%s, type %s)", entity.Name, ccInt, ccName, entity.EntityType)

	// Map based on command class
	switch ccInt {
	case CC_BATTERY:
		mapBatteryEntity(device, entity, propName)

	case CC_SENSOR_MULTILEVEL:
		mapMultilevelSensorEntity(device, entity, propName)

	case CC_NOTIFICATION:
		mapNotificationEntity(device, entity, propName)

	case CC_SWITCH_BINARY:
		mapBinarySwitchEntity(device, entity, propName)

	case CC_SENSOR_BINARY:
		mapBinarySensorEntity(device, entity, propName)

	default:
		// Try to infer from entity type and name
		inferMappingFromName(device, entity, propName, ccName)
	}
}

// mapBatteryEntity maps battery-related entities
func mapBatteryEntity(device *model.Device, entity *model.DeviceEntity, propName string) {
	if device.Battery == nil {
		device.Battery = &model.DeviceBattery{}
	}

	switch propName {
	case "level":
		if level, ok := entity.Value.(float64); ok {
			device.Battery.Level = int(level)
			device.Battery.IsLow = level < 20
			log.Printf("[ENTITY-MAPPER] Mapped battery level: %d%%", int(level))
		}
	case "islow":
		if isLow, ok := entity.Value.(bool); ok {
			device.Battery.IsLow = isLow
		}
	case "charging", "ischarging":
		if charging, ok := entity.Value.(bool); ok {
			device.Battery.IsCharging = charging
		}
	}
}

// mapMultilevelSensorEntity maps multilevel sensor values
func mapMultilevelSensorEntity(device *model.Device, entity *model.DeviceEntity, propName string) {
	// Check sensor type from metadata
	sensorType := ""
	if st, ok := entity.Metadata["type"].(string); ok {
		sensorType = strings.ToLower(st)
	}

	// Get numeric value
	var value float64
	switch v := entity.Value.(type) {
	case float64:
		value = v
	case int:
		value = float64(v)
	default:
		return
	}

	// Map based on sensor type or property name
	if strings.Contains(sensorType, "temperature") || strings.Contains(propName, "temperature") ||
		strings.Contains(propName, "air temperature") {
		// Check unit to determine if conversion is needed
		unit := strings.ToLower(entity.Unit)
		tempF := value
		if unit == "°c" || unit == "celsius" {
			tempF = celsiusToFahrenheit(value)
		}
		device.Readings.TemperatureF = &tempF
		log.Printf("[ENTITY-MAPPER] Mapped temperature: %.1f°F", tempF)
	} else if strings.Contains(sensorType, "humidity") || strings.Contains(propName, "humidity") {
		device.Readings.Humidity = &value
		log.Printf("[ENTITY-MAPPER] Mapped humidity: %.1f%%", value)
	} else if strings.Contains(propName, "illuminance") || strings.Contains(propName, "light") {
		device.Readings.Illuminance = &value
	} else if strings.Contains(propName, "power") {
		device.Readings.PowerW = &value
	} else if strings.Contains(propName, "energy") {
		device.Readings.EnergyKWh = &value
	} else if strings.Contains(propName, "voltage") {
		device.Readings.VoltageV = &value
	} else if strings.Contains(propName, "current") {
		device.Readings.CurrentA = &value
	}
}

// mapNotificationEntity maps notification/alarm entities
func mapNotificationEntity(device *model.Device, entity *model.DeviceEntity, propName string) {
	// Notification entities typically report alarm states
	var isActive bool
	switch v := entity.Value.(type) {
	case bool:
		isActive = v
	case float64:
		isActive = v != 0
	case int:
		isActive = v != 0
	default:
		return
	}

	// Map based on notification type
	// Only map water/leak alarm sensors, NOT valve status
	if (strings.Contains(propName, "water") || strings.Contains(propName, "leak")) &&
		!strings.Contains(propName, "valve") &&
		!strings.Contains(propName, "jammed") {
		device.Readings.Water = &isActive
		log.Printf("[ENTITY-MAPPER] Mapped water alarm: %v (entity: %s)", isActive, propName)
	} else if strings.Contains(propName, "smoke") {
		device.Readings.Smoke = &isActive
	} else if strings.Contains(propName, "co") || strings.Contains(propName, "carbon") {
		device.Readings.CO = &isActive
	} else if strings.Contains(propName, "tamper") {
		device.Readings.Tamper = &isActive
	} else if strings.Contains(propName, "motion") {
		device.Readings.Motion = &isActive
	}
}

// mapBinarySwitchEntity maps binary switch controls
func mapBinarySwitchEntity(device *model.Device, entity *model.DeviceEntity, propName string) {
	if device.Controls == nil {
		device.Controls = &model.DeviceControls{}
	}

	// Only map if it's settable (actual control, not just status)
	if entity.Settable && (propName == "targetvalue" || propName == "currentvalue") {
		var value bool
		switch v := entity.Value.(type) {
		case bool:
			value = v
		case float64:
			value = v != 0
		case int:
			value = v != 0
		default:
			return
		}

		if device.Controls.Switch == nil {
			device.Controls.Switch = &model.SwitchControl{}
		}
		device.Controls.Switch.Value = value
		device.Controls.Switch.Settable = entity.Settable
		log.Printf("[ENTITY-MAPPER] Mapped switch control: %v (settable: %v)", value, entity.Settable)
	}
}

// mapBinarySensorEntity maps binary sensor readings
func mapBinarySensorEntity(device *model.Device, entity *model.DeviceEntity, propName string) {
	var isActive bool
	switch v := entity.Value.(type) {
	case bool:
		isActive = v
	case float64:
		isActive = v != 0
	case int:
		isActive = v != 0
	default:
		return
	}

	// Try to infer what kind of binary sensor this is
	if strings.Contains(propName, "motion") {
		device.Readings.Motion = &isActive
	} else if strings.Contains(propName, "contact") || strings.Contains(propName, "door") {
		device.Readings.Contact = &isActive
	} else if strings.Contains(propName, "tamper") {
		device.Readings.Tamper = &isActive
	}
}

// inferMappingFromName tries to infer mapping from entity name/category
func inferMappingFromName(device *model.Device, entity *model.DeviceEntity, propName, ccName string) {
	// Skip if already mapped by command class
	// This is a fallback for entities without standard command classes

	// For diagnostic/config entities, don't map to readings
	if entity.EntityType == model.EntityTypeDiagnostic || entity.EntityType == model.EntityTypeConfig {
		return
	}

	// Try name-based inference for sensors
	if entity.EntityType == model.EntityTypeSensor {
		if numValue, ok := entity.Value.(float64); ok {
			if strings.Contains(propName, "temperature") {
				tempF := numValue
				if strings.Contains(entity.Unit, "C") {
					tempF = celsiusToFahrenheit(numValue)
				}
				device.Readings.TemperatureF = &tempF
			} else if strings.Contains(propName, "humidity") {
				device.Readings.Humidity = &numValue
			}
		}
	}
}

// celsiusToFahrenheit converts Celsius to Fahrenheit
func celsiusToFahrenheit(celsius float64) float64 {
	return celsius*1.8 + 32
}
