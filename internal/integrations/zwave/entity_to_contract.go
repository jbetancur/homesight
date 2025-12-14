package zwave

import (
	"log"
	"strings"

	"github.com/homesight/homesight/internal/model"
)

// PopulateUnifiedContractFromEntities populates the unified contract fields
// (readings, battery, controls) from the device entities
func PopulateUnifiedContractFromEntities(device *model.Device) {
	if len(device.Entities) == 0 {
		return
	}

	log.Printf("[ENTITY-MAPPER] PopulateUnifiedContractFromEntities called for device %s with %d entities", device.ID, len(device.Entities))

	// Initialize contract fields if nil
	if device.Readings == nil {
		device.Readings = &model.DeviceReadings{}
	}
	if device.Battery == nil && hasBatteryEntity(device.Entities) {
		device.Battery = &model.DeviceBattery{}
		log.Printf("[ENTITY-MAPPER] Initialized battery object for device %s", device.ID)
	}
	if device.Controls == nil && hasControlEntity(device.Entities) {
		device.Controls = &model.DeviceControls{}
	}

	// Map entities to contract fields
	for _, entity := range device.Entities {
		mapEntityToContract(device, &entity)
	}

	// Post-processing: Detect AC-powered devices and clear battery warnings
	if device.Battery != nil {
		log.Printf("[ENTITY-MAPPER] Post-processing check for %s: battery level=%d, is_low=%v", device.ID, device.Battery.Level, device.Battery.IsLow)

		// Check if device is AC-powered (has backup battery, not primary battery)
		isACPowered := isACPoweredDevice(device.Entities)

		if isACPowered {
			// Device has AC power with backup battery - don't flag as low battery
			device.Battery.IsLow = false
			log.Printf("[ENTITY-MAPPER] ✓ Post-processing: Device %s is AC-powered with backup battery, clearing low battery flag", device.ID)
		} else if device.Battery.Level == 0 && device.Battery.IsLow {
			// For battery-only devices, check if battery is disconnected
			for _, entity := range device.Entities {
				if cc, ok := entity.Metadata["command_class"].(float64); ok && int(cc) == CC_BATTERY {
					propName := strings.ToLower(entity.Name)
					if propName == "disconnected" {
						if disconnected, ok := entity.Value.(bool); ok && disconnected {
							device.Battery.IsLow = false
							log.Printf("[ENTITY-MAPPER] ✓ Post-processing: Battery disconnected, clearing low battery flag for device %s", device.ID)
							break
						}
					}
				}
			}
		}
	}
}

// isACPoweredDevice detects if a Z-Wave device is AC-powered with backup battery
// Returns true if device is AC-powered (battery is backup only, not primary power source)
// Uses multiple heuristics:
// 1. Wake Up interval >= 1 hour (3600s) indicates AC power
//    - Battery-only devices typically wake every 1-15 minutes to save power
//    - AC devices can wake less frequently (12-24 hours) since power isn't constrained
// 2. Presence of "backup" entity indicating optional backup battery
// 3. Battery "disconnected" flag indicating optional/removable backup battery
// 4. No Wake Up entity at all (always-listening AC devices don't need wake-up)
func isACPoweredDevice(entities []model.DeviceEntity) bool {
	const wakeUpIntervalThreshold = 3600 // 1 hour in seconds
	hasWakeUpEntity := false

	for _, entity := range entities {
		cc, ok := entity.Metadata["command_class"].(float64)
		if !ok {
			continue
		}

		propName := strings.ToLower(entity.Name)

		// Check for Wake Up command class (132)
		if int(cc) == 132 {
			hasWakeUpEntity = true

			// Check if wake up interval is high (AC-powered)
			if propName == "wakeupinterval" {
				if interval, ok := entity.Value.(float64); ok {
					if interval >= wakeUpIntervalThreshold {
						log.Printf("[ENTITY-MAPPER] Detected AC power via Wake Up interval: %.0fs (>= %ds threshold)", interval, wakeUpIntervalThreshold)
						return true
					}
				}
			}
		}

		// Check for explicit backup battery indicator
		if propName == "backup" {
			if backup, ok := entity.Value.(bool); ok && backup {
				log.Printf("[ENTITY-MAPPER] Detected AC power via backup battery flag")
				return true
			}
		}

		// Check for battery disconnected (indicating optional backup)
		if (propName == "disconnected" || propName == "battery disconnected") && int(cc) == CC_BATTERY {
			if disconnected, ok := entity.Value.(bool); ok && disconnected {
				log.Printf("[ENTITY-MAPPER] Detected AC power via battery disconnected flag")
				return true
			}
		}
	}

	// If device has battery but NO Wake Up entity, it's always-listening (AC-powered)
	// Battery-powered devices ALWAYS have Wake Up to conserve power
	if !hasWakeUpEntity {
		log.Printf("[ENTITY-MAPPER] Detected AC power: No Wake Up entity (always-listening device)")
		return true
	}

	return false
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
		// Handle battery disconnected sensor from binary sensor CC too
		if propName == "disconnected" && device.Battery != nil {
			if disconnected, ok := entity.Value.(bool); ok && disconnected {
				device.Battery.IsLow = false
				log.Printf("[ENTITY-MAPPER] Battery disconnected (from binary sensor), clearing low battery flag")
			}
		}
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
	case "disconnected":
		// If battery is disconnected (backup battery not installed), don't flag as low
		if disconnected, ok := entity.Value.(bool); ok && disconnected {
			device.Battery.IsLow = false
			log.Printf("[ENTITY-MAPPER] Battery disconnected, clearing low battery flag")
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
	var numValue float64
	switch v := entity.Value.(type) {
	case bool:
		isActive = v
	case float64:
		isActive = v != 0
		numValue = v
	case int:
		isActive = v != 0
		numValue = float64(v)
	default:
		return
	}

	// Check for Power Management notification - backup battery status
	// Value 18 = "Back-up battery disconnected"
	if strings.Contains(propName, "power management") ||
		strings.Contains(propName, "backup battery") {
		log.Printf("[ENTITY-MAPPER] Power Management entity detected: value=%.0f, battery_exists=%v", numValue, device.Battery != nil)
		if device.Battery != nil && numValue == 18 {
			device.Battery.IsLow = false
			log.Printf("[ENTITY-MAPPER] ✓ Power Management: Backup battery disconnected (value=18), cleared low battery flag for device %s", device.ID)
		}
		// Don't map power management notifications to readings
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
