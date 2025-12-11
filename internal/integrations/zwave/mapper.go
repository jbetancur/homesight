package zwave

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/homesight/homesight/internal/model"
	"github.com/homesight/homesight/internal/util"
)

// MapNodeToDevice converts a Z-Wave node to a HomeSight device
func MapNodeToDevice(node *ZWaveNode, homeID uint32) *model.Device {
	// Generate stable device ID: zwave-{nodeId}
	deviceID := fmt.Sprintf("zwave-%d", node.NodeID)

	// Extract manufacturer/model - try multiple sources
	// Priority: DeviceConfig > direct fields > fallback to "Unknown"
	manufacturer := node.DeviceConfig.Manufacturer
	if strings.TrimSpace(manufacturer) == "" {
		manufacturer = node.Manufacturer // Try direct field
	}
	if strings.TrimSpace(manufacturer) == "" {
		manufacturer = "Unknown Manufacturer"
	}

	// Try multiple sources for model name
	modelName := node.DeviceConfig.Label
	if strings.TrimSpace(modelName) == "" {
		modelName = node.Label // Try direct label field
	}
	if strings.TrimSpace(modelName) == "" {
		modelName = node.Name // Try direct name field
	}
	if strings.TrimSpace(modelName) == "" {
		modelName = fmt.Sprintf("Node %d", node.NodeID)
	}

	// Determine device type from command classes
	deviceType := inferDeviceType(node)

	// Determine if device should be enabled
	// Interview stage 7 = Complete, or node.Ready = true, or status >= 3 (Ready/Alive)
	isEnabled := node.Ready || node.InterviewStage >= 7 || node.Status >= 3

	device := &model.Device{
		ID:           deviceID,
		Name:         modelName,
		Type:         deviceType,
		Integration:  "zwave",
		Manufacturer: manufacturer,
		Model:        modelName,
		Enabled:      isEnabled,
	}

	// Extract unified readings
	device.Readings = extractReadings(node)

	// Extract unified controls
	device.Controls = extractControls(node)

	// Extract battery info (only for battery-powered devices)
	if !node.IsListening {
		device.Battery = extractBatteryInfo(node)
	}

	// Extract connectivity info
	device.Connectivity = &model.DeviceConnectivity{
		Online:      isEnabled,
		FirmwareVer: node.FirmwareVersion,
	}

	// Extract entities (entity-based model)
	device.Entities = extractEntities(node, deviceID)

	// Populate unified contract from entities (readings, battery, controls)
	PopulateUnifiedContractFromEntities(device)

	// Store complete raw Z-Wave data
	device.RawData = buildRawData(node, homeID)

	// Log device mapping for debugging
	log.Printf("[ZWAVE-MAPPER] Mapped node %d to device: name=%s, type=%s, enabled=%v, ready=%v, status=%d, interviewStage=%d",
		node.NodeID, modelName, deviceType, device.Enabled, node.Ready, node.Status, node.InterviewStage)

	return device
}

// inferDeviceType determines HomeSight device type from Z-Wave command classes
func inferDeviceType(node *ZWaveNode) string {
	// Check for specific device types based on command classes and device config
	// Priority: Most specific first

	// Check deviceConfig description/label for hints
	desc := strings.ToLower(node.DeviceConfig.Description + " " + node.DeviceConfig.Label)
	if strings.Contains(desc, "water leak") || strings.Contains(desc, "leak sensor") {
		return "water_leak"
	}
	if strings.Contains(desc, "motion") {
		return "motion_sensor"
	}
	if strings.Contains(desc, "door") || strings.Contains(desc, "window") {
		return "door_sensor"
	}
	if strings.Contains(desc, "smoke") {
		return "smoke_detector"
	}
	if strings.Contains(desc, "co2") || strings.Contains(desc, "carbon monoxide") {
		return "co_detector"
	}

	// Water leak sensor (Notification CC with water alarm)
	if hasCommandClass(node, CC_NOTIFICATION) {
		// Check if notification type is water
		notifType := getNotificationType(node)
		if notifType == NOTIFICATION_WATER {
			return "water_leak"
		}
		// Check for other notification types
		switch notifType {
		case NOTIFICATION_SMOKE:
			return "smoke_detector"
		case NOTIFICATION_CO:
			return "co_detector"
		case NOTIFICATION_BURGLAR:
			return "motion_sensor"
		case NOTIFICATION_HEAT:
			return "temperature_sensor"
		}
	}

	// Binary sensor (door/window, motion, etc.)
	if hasCommandClass(node, CC_SENSOR_BINARY) {
		return "binary_sensor"
	}

	// Multilevel sensor (temperature, humidity, light, etc.)
	if hasCommandClass(node, CC_SENSOR_MULTILEVEL) {
		return "sensor"
	}

	// Binary switch (on/off plug, relay)
	if hasCommandClass(node, CC_SWITCH_BINARY) {
		return "switch"
	}

	// Multilevel switch (dimmer, motor control)
	if hasCommandClass(node, CC_SWITCH_MULTILEVEL) {
		return "dimmer"
	}

	// Color control (RGB lights)
	if hasCommandClass(node, CC_COLOR_SWITCH) {
		return "light"
	}

	// Meter (power, energy, water, gas)
	if hasCommandClass(node, CC_METER) {
		return "meter"
	}

	// Battery-powered device
	if hasCommandClass(node, CC_BATTERY) {
		return "battery_device"
	}

	return "unknown"
}

// hasCommandClass checks if node supports a command class
func hasCommandClass(node *ZWaveNode, ccID int) bool {
	// First check CommandClasses map
	if node.CommandClasses != nil {
		_, exists := node.CommandClasses[ccID]
		if exists {
			return true
		}
	}

	// Fallback: check Values array for this command class
	if valuesArray, ok := node.Values.([]interface{}); ok {
		for _, v := range valuesArray {
			valueObj, ok := v.(map[string]interface{})
			if !ok {
				continue
			}
			commandClass, _ := valueObj["commandClass"].(float64)
			if int(commandClass) == ccID {
				return true
			}
		}
	}

	return false
}

// getNotificationType extracts notification type from node values
func getNotificationType(node *ZWaveNode) int {
	// Values can be map or array, try to handle as map
	if valuesMap, ok := node.Values.(map[string]interface{}); ok {
		for key, value := range valuesMap {
			if strings.Contains(key, "Notification") && strings.Contains(key, "type") {
				if notifType, ok := value.(float64); ok {
					return int(notifType)
				}
			}
		}
	}
	return -1
}

// findBatteryLevel extracts battery level percentage from node values
func findBatteryLevel(node *ZWaveNode) (int, bool) {
	if !hasCommandClass(node, CC_BATTERY) {
		return 0, false
	}

	// Values can be map or array, try to handle as map
	if valuesMap, ok := node.Values.(map[string]interface{}); ok {
		for key, value := range valuesMap {
			if strings.Contains(strings.ToLower(key), "battery") &&
				strings.Contains(strings.ToLower(key), "level") {
				switch v := value.(type) {
				case float64:
					return int(v), true
				case int:
					return v, true
				}
			}
		}
	}

	return 0, false
}

// GetCommandClassName returns human-readable name for command class ID
func GetCommandClassName(ccID int) string {
	names := map[int]string{
		CC_BASIC:                 "Basic",
		CC_SWITCH_BINARY:         "Switch Binary",
		CC_SWITCH_MULTILEVEL:     "Switch Multilevel",
		CC_SENSOR_BINARY:         "Sensor Binary",
		CC_SENSOR_MULTILEVEL:     "Sensor Multilevel",
		CC_METER:                 "Meter",
		CC_COLOR_SWITCH:          "Color Switch",
		CC_CONFIGURATION:         "Configuration",
		CC_NOTIFICATION:          "Notification",
		CC_MANUFACTURER_SPECIFIC: "Manufacturer Specific",
		CC_BATTERY:               "Battery",
		CC_WAKE_UP:               "Wake Up",
		CC_ASSOCIATION:           "Association",
		CC_VERSION:               "Version",
		CC_INDICATOR:             "Indicator",
	}

	if name, ok := names[ccID]; ok {
		return name
	}

	return fmt.Sprintf("Unknown (0x%02x)", ccID)
}

// ExtractCapabilities extracts device capabilities from command classes
func ExtractCapabilities(node *ZWaveNode) []string {
	capabilities := []string{}

	if hasCommandClass(node, CC_SWITCH_BINARY) {
		capabilities = append(capabilities, "switch")
	}

	if hasCommandClass(node, CC_SWITCH_MULTILEVEL) {
		capabilities = append(capabilities, "dimmer")
	}

	if hasCommandClass(node, CC_SENSOR_BINARY) {
		capabilities = append(capabilities, "binary_sensor")
	}

	if hasCommandClass(node, CC_SENSOR_MULTILEVEL) {
		capabilities = append(capabilities, "sensor")
	}

	if hasCommandClass(node, CC_NOTIFICATION) {
		capabilities = append(capabilities, "notification")
	}

	if hasCommandClass(node, CC_BATTERY) {
		capabilities = append(capabilities, "battery")
	}

	if hasCommandClass(node, CC_METER) {
		capabilities = append(capabilities, "meter")
	}

	if hasCommandClass(node, CC_COLOR_SWITCH) {
		capabilities = append(capabilities, "color")
	}

	return capabilities
}

// ExtractDeviceState extracts current state from a Z-Wave node
// Returns a map suitable for device.State field
func ExtractDeviceState(node *ZWaveNode) map[string]interface{} {
	state := make(map[string]interface{})

	// Extract battery percentage
	if level, ok := findBatteryLevel(node); ok {
		state["battery"] = level
	}

	// Extract state from values (stored during events)
	// Note: Values are updated dynamically via value_updated events
	if valuesMap, ok := node.Values.(map[string]interface{}); ok {
		// Look for common state values
		for key, value := range valuesMap {
			keyLower := strings.ToLower(key)

			// Binary states (leak, motion, contact, tamper)
			if strings.Contains(keyLower, "leak") || strings.Contains(keyLower, "water") {
				if boolVal, ok := value.(bool); ok {
					state["leak"] = boolVal
				}
			}

			if strings.Contains(keyLower, "motion") {
				if boolVal, ok := value.(bool); ok {
					state["motion"] = boolVal
				}
			}

			if strings.Contains(keyLower, "contact") || strings.Contains(keyLower, "door") || strings.Contains(keyLower, "window") {
				if boolVal, ok := value.(bool); ok {
					state["contact"] = boolVal
				}
			}

			if strings.Contains(keyLower, "tamper") {
				if boolVal, ok := value.(bool); ok {
					state["tamper"] = boolVal
				}
			}

			// Numeric sensors
			if strings.Contains(keyLower, "temperature") {
				if floatVal, ok := value.(float64); ok {
					state["temperature"] = floatVal
				}
			}

			if strings.Contains(keyLower, "humidity") {
				if floatVal, ok := value.(float64); ok {
					state["humidity"] = floatVal
				}
			}

			if strings.Contains(keyLower, "power") {
				if floatVal, ok := value.(float64); ok {
					state["power"] = floatVal
				}
			}

			if strings.Contains(keyLower, "energy") {
				if floatVal, ok := value.(float64); ok {
					state["energy"] = floatVal
				}
			}

			// On/off state
			if strings.Contains(keyLower, "currentvalue") || strings.Contains(keyLower, "state") {
				if boolVal, ok := value.(bool); ok {
					state["on"] = boolVal
				} else if intVal, ok := value.(int); ok {
					state["on"] = intVal > 0
				} else if floatVal, ok := value.(float64); ok {
					state["on"] = floatVal > 0
				}
			}

			// Brightness level
			if strings.Contains(keyLower, "level") || strings.Contains(keyLower, "brightness") {
				if intVal, ok := value.(int); ok {
					state["brightness"] = intVal
				} else if floatVal, ok := value.(float64); ok {
					state["brightness"] = int(floatVal)
				}
			}
		}
	}

	return state
}

// extractReadings extracts unified sensor readings from Z-Wave node
func extractReadings(node *ZWaveNode) *model.DeviceReadings {
	readings := &model.DeviceReadings{}
	hasData := false

	// Try to extract from values array (Z-Wave JS format)
	if valuesArray, ok := node.Values.([]interface{}); ok {
		for _, v := range valuesArray {
			valueObj, ok := v.(map[string]interface{})
			if !ok {
				continue
			}

			propertyName, _ := valueObj["propertyName"].(string)
			value := valueObj["value"]
			commandClass, _ := valueObj["commandClass"].(float64)
			ccID := int(commandClass)

			if propertyName == "" || value == nil {
				continue
			}

			propLower := strings.ToLower(propertyName)

			// Temperature (CC 49 - Multilevel Sensor)
			// Z-Wave typically reports in Celsius, convert to Fahrenheit
			if ccID == CC_SENSOR_MULTILEVEL && strings.Contains(propLower, "temperature") {
				if floatVal, ok := value.(float64); ok {
					// Check metadata for unit, default to Celsius for Z-Wave
					metadata, _ := valueObj["metadata"].(map[string]interface{})
					unit := "°C"
					if metadata != nil {
						if metaUnit, ok := metadata["unit"].(string); ok {
							unit = metaUnit
						}
					}

					// Convert to Fahrenheit if needed
					tempF := floatVal
					if strings.Contains(unit, "C") {
						tempF = util.CelsiusToFahrenheit(floatVal)
					}
					readings.TemperatureF = &tempF
					hasData = true
				}
			}

			// Humidity (CC 49 - Multilevel Sensor)
			if ccID == CC_SENSOR_MULTILEVEL && strings.Contains(propLower, "humidity") {
				if floatVal, ok := value.(float64); ok {
					readings.Humidity = &floatVal
					hasData = true
				}
			}

			// Water Alarm (CC 113 - Notification)
			if ccID == CC_NOTIFICATION && (propLower == "water alarm" || strings.Contains(propLower, "water")) {
				boolVal := false
				switch v := value.(type) {
				case float64:
					boolVal = v > 0
				case int:
					boolVal = v > 0
				case bool:
					boolVal = v
				}
				readings.Water = &boolVal
				hasData = true
			}

			// Motion (CC 48 - Binary Sensor or CC 113 - Notification)
			if (ccID == CC_SENSOR_BINARY || ccID == CC_NOTIFICATION) && strings.Contains(propLower, "motion") {
				if boolVal, ok := value.(bool); ok {
					readings.Motion = &boolVal
					hasData = true
				}
			}

			// Contact (CC 48 - Binary Sensor)
			if ccID == CC_SENSOR_BINARY && (strings.Contains(propLower, "contact") || strings.Contains(propLower, "door")) {
				if boolVal, ok := value.(bool); ok {
					readings.Contact = &boolVal
					hasData = true
				}
			}

			// Tamper (CC 113 - Notification)
			if ccID == CC_NOTIFICATION && strings.Contains(propLower, "tamper") {
				if boolVal, ok := value.(bool); ok {
					readings.Tamper = &boolVal
					hasData = true
				}
			}

			// Power/Energy (CC 50 - Meter)
			if ccID == CC_METER {
				if strings.Contains(propLower, "power") {
					if floatVal, ok := value.(float64); ok {
						readings.PowerW = &floatVal
						hasData = true
					}
				}
				if strings.Contains(propLower, "energy") {
					if floatVal, ok := value.(float64); ok {
						readings.EnergyKWh = &floatVal
						hasData = true
					}
				}
			}
		}
	}

	if !hasData {
		return nil
	}
	return readings
}

// extractControls extracts unified control capabilities from Z-Wave node
func extractControls(node *ZWaveNode) *model.DeviceControls {
	controls := &model.DeviceControls{}
	hasControls := false

	// Check for binary switch (CC 37)
	hasBinarySwitch := hasCommandClass(node, CC_SWITCH_BINARY)
	log.Printf("[ZWAVE-MAPPER] Node %d: Checking CC_SWITCH_BINARY (37), result=%v", node.NodeID, hasBinarySwitch)
	if hasBinarySwitch {
		controls.Switch = &model.SwitchControl{
			Value:    false, // Will be updated via value events
			Settable: true,
		}
		hasControls = true
		log.Printf("[ZWAVE-MAPPER] Node %d: Added switch control", node.NodeID)
	}

	// Check for multilevel switch/dimmer (CC 38)
	if hasCommandClass(node, CC_SWITCH_MULTILEVEL) {
		controls.Level = &model.LevelControl{
			Value:    0,
			Settable: true,
			Min:      0,
			Max:      100,
		}
		hasControls = true
	}

	// Check for color control (CC 51)
	if hasCommandClass(node, CC_COLOR_SWITCH) {
		controls.Color = &model.ColorControl{
			R:        0,
			G:        0,
			B:        0,
			Settable: true,
		}
		hasControls = true
	}

	if !hasControls {
		return nil
	}
	return controls
}

// extractBatteryInfo extracts unified battery information from Z-Wave node
func extractBatteryInfo(node *ZWaveNode) *model.DeviceBattery {
	level, ok := findBatteryLevel(node)
	if !ok || level == 0 {
		return nil
	}

	return &model.DeviceBattery{
		Level:      level,
		IsLow:      level < 20,
		IsCharging: false, // Z-Wave doesn't typically report charging status
	}
}

// extractEntities converts all Z-Wave values into entities
func extractEntities(node *ZWaveNode, deviceID string) []model.DeviceEntity {
	entities := []model.DeviceEntity{}
	now := time.Now()

	// Try to extract from values array (Z-Wave JS format)
	valuesArray, ok := node.Values.([]interface{})
	if !ok {
		log.Printf("[ZWAVE-MAPPER] Node %d: Values is not an array, skipping entity extraction", node.NodeID)
		return entities
	}

	for _, v := range valuesArray {
		valueObj, ok := v.(map[string]interface{})
		if !ok {
			continue
		}

		// Extract basic value info
		propertyName, _ := valueObj["propertyName"].(string)
		property := valueObj["property"]
		propertyKey := valueObj["propertyKey"] // Can be nil
		value := valueObj["value"]
		commandClass, _ := valueObj["commandClass"].(float64)
		ccID := int(commandClass)
		commandClassName, _ := valueObj["commandClassName"].(string)

		if propertyName == "" || value == nil {
			continue
		}

		// Handle nested value objects (e.g., duration with unit)
		if valueMap, ok := value.(map[string]interface{}); ok {
			if actualValue, exists := valueMap["value"]; exists {
				value = actualValue
			}
		}

		// Extract metadata
		metadata := map[string]interface{}{
			"command_class":      ccID,
			"command_class_name": commandClassName,
			"property":           property,
		}

		// Add propertyKey to metadata if it exists
		if propertyKey != nil {
			metadata["property_key"] = propertyKey
		}

		if meta, ok := valueObj["metadata"].(map[string]interface{}); ok {
			for k, v := range meta {
				metadata[k] = v
			}
		}

		// Build entity ID: deviceID-commandClass-property[-propertyKey]
		entityID := fmt.Sprintf("%s-cc%d-%v", deviceID, ccID, property)
		if propertyKey != nil {
			entityID = fmt.Sprintf("%s-%v", entityID, propertyKey)
		}

		// Determine entity type and category
		entityType, category := inferEntityType(ccID, propertyName, metadata)

		// Get unit from metadata
		unit := ""
		if meta, ok := valueObj["metadata"].(map[string]interface{}); ok {
			if u, ok := meta["unit"].(string); ok {
				unit = u
			}
		}

		// Temperature conversion for sensors
		if category == "temperature" && unit == "°C" {
			if floatVal, ok := value.(float64); ok {
				value = util.CelsiusToFahrenheit(floatVal)
				unit = "°F"
			}
		}

		// Determine if settable
		settable := false
		if meta, ok := valueObj["metadata"].(map[string]interface{}); ok {
			if w, ok := meta["writeable"].(bool); ok {
				settable = w
			}
		}

		entity := model.DeviceEntity{
			ID:         entityID,
			DeviceID:   deviceID,
			EntityType: entityType,
			Name:       propertyName,
			Category:   category,
			Value:      value,
			Unit:       unit,
			Settable:   settable,
			Metadata:   metadata,
			UpdatedAt:  now,
		}

		entities = append(entities, entity)
	}

	log.Printf("[ZWAVE-MAPPER] Node %d: Extracted %d entities", node.NodeID, len(entities))
	return entities
}

// inferEntityType determines entity type and category from Z-Wave command class and property
func inferEntityType(ccID int, propertyName string, metadata map[string]interface{}) (model.EntityType, string) {
	propLower := strings.ToLower(propertyName)

	// Check metadata type first
	if meta, ok := metadata["type"].(string); ok {
		switch meta {
		case "boolean":
			// Binary sensor or switch (depending on writeable)
			if w, ok := metadata["writeable"].(bool); ok && w {
				return model.EntityTypeSwitch, "control"
			}
			return model.EntityTypeBinarySensor, "binary_sensor"
		case "number", "duration":
			// Numeric sensor or control
			if w, ok := metadata["writeable"].(bool); ok && w {
				return model.EntityTypeNumber, "control"
			}
			return model.EntityTypeSensor, "sensor"
		}
	}

	// Infer from command class
	switch ccID {
	case CC_SENSOR_MULTILEVEL: // 49
		// Determine category from property name
		if strings.Contains(propLower, "temperature") {
			return model.EntityTypeSensor, "temperature"
		}
		if strings.Contains(propLower, "humidity") {
			return model.EntityTypeSensor, "humidity"
		}
		return model.EntityTypeSensor, "sensor"

	case CC_SENSOR_BINARY: // 48
		return model.EntityTypeBinarySensor, "binary_sensor"

	case CC_SWITCH_BINARY: // 37
		if strings.Contains(propLower, "currentvalue") || strings.Contains(propLower, "targetvalue") {
			return model.EntityTypeSwitch, "control"
		}
		if strings.Contains(propLower, "duration") {
			return model.EntityTypeSensor, "diagnostic"
		}
		return model.EntityTypeDiagnostic, "diagnostic"

	case CC_SWITCH_MULTILEVEL: // 38
		return model.EntityTypeNumber, "control"

	case CC_NOTIFICATION: // 113
		// Alarms and notifications
		if strings.Contains(propLower, "alarm") || strings.Contains(propLower, "leak") ||
			strings.Contains(propLower, "overheat") || strings.Contains(propLower, "freeze") {
			return model.EntityTypeAlarm, "alarm"
		}
		return model.EntityTypeBinarySensor, "notification"

	case CC_BATTERY: // 128
		return model.EntityTypeSensor, "battery"

	case CC_METER: // 50
		if strings.Contains(propLower, "power") {
			return model.EntityTypeSensor, "power"
		}
		if strings.Contains(propLower, "energy") {
			return model.EntityTypeSensor, "energy"
		}
		return model.EntityTypeSensor, "meter"

	case CC_CONFIGURATION: // 112
		return model.EntityTypeConfig, "config"

	default:
		return model.EntityTypeDiagnostic, "diagnostic"
	}
}

// buildRawData stores complete raw Z-Wave node data
func buildRawData(node *ZWaveNode, homeID uint32) map[string]interface{} {
	return map[string]interface{}{
		"node_id":               node.NodeID,
		"home_id":               fmt.Sprintf("0x%08x", homeID),
		"status":                node.Status,
		"ready":                 node.Ready,
		"manufacturer_id":       fmt.Sprintf("0x%04x", node.ManufacturerID),
		"product_type":          fmt.Sprintf("0x%04x", node.ProductType),
		"product_id":            fmt.Sprintf("0x%04x", node.ProductID),
		"firmware_version":      node.FirmwareVersion,
		"security":              node.Security,
		"interview_stage":       node.InterviewStage,
		"is_listening":          node.IsListening,
		"is_frequent_listening": node.IsFrequentListening,
		"supports_beaming":      node.SupportsBeaming,
		"command_classes":       node.CommandClasses,
		"values":                node.Values,
		"device_config":         node.DeviceConfig,
	}
}
