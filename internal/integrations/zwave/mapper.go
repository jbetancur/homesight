package zwave

import (
	"fmt"
	"log"
	"strings"

	"github.com/homesight/homesight/internal/model"
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

	// Build metadata
	metadata := map[string]string{
		"manufacturer":     manufacturer,
		"model":            modelName,
		"manufacturer_id":  fmt.Sprintf("0x%04x", node.ManufacturerID),
		"product_type":     fmt.Sprintf("0x%04x", node.ProductType),
		"product_id":       fmt.Sprintf("0x%04x", node.ProductID),
		"firmware":         node.FirmwareVersion,
		"security":         node.Security,
		"node_id":          fmt.Sprintf("%d", node.NodeID),
		"home_id":          fmt.Sprintf("0x%08x", homeID),
		"interview_stage":  fmt.Sprintf("%d", node.InterviewStage),
		"is_listening":     fmt.Sprintf("%t", node.IsListening),
		"supports_beaming": fmt.Sprintf("%t", node.SupportsBeaming),
	}

	// Add command classes
	ccNames := make([]string, 0, len(node.CommandClasses))
	for ccID, cc := range node.CommandClasses {
		ccNames = append(ccNames, cc.Name)
		metadata[fmt.Sprintf("cc_%d", ccID)] = cc.Name
	}
	metadata["command_classes"] = strings.Join(ccNames, ",")

	// Extract battery level if available
	if batteryLevel, ok := findBatteryLevel(node); ok {
		metadata["battery_level"] = fmt.Sprintf("%d", batteryLevel)
	}

	// Check for low battery
	if isLowBattery(node) {
		metadata["battery_low"] = "true"
	}

	// Extract all sensor values from node.Values during initial sync
	extractNodeValues(node, metadata)

	// Determine if device should be enabled
	// Interview stage 7 = Complete, or node.Ready = true, or status >= 3 (Ready/Alive)
	isEnabled := node.Ready || node.InterviewStage >= 7 || node.Status >= 3

	device := &model.Device{
		ID:          deviceID,
		Name:        modelName,
		Type:        deviceType,
		Integration: "zwave",
		Enabled:     isEnabled,
		Metadata:    metadata,
	}

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
	_, exists := node.CommandClasses[ccID]
	return exists
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

// extractNodeValues extracts all sensor values from node.Values into metadata
func extractNodeValues(node *ZWaveNode, metadata map[string]string) {
	if node.Values == nil {
		return
	}

	// Z-Wave JS sends values as an array of value objects
	valuesArray, ok := node.Values.([]interface{})
	if ok {
		for _, v := range valuesArray {
			valueObj, ok := v.(map[string]interface{})
			if !ok {
				continue
			}

			// Get property name and value
			propertyName, _ := valueObj["propertyName"].(string)
			value := valueObj["value"]
			commandClass, _ := valueObj["commandClass"].(float64)

			if propertyName == "" || value == nil {
				continue
			}

			// Map known properties to standard metadata keys
			propLower := strings.ToLower(propertyName)
			ccID := int(commandClass)

			// Battery level (CC 128)
			if ccID == CC_BATTERY && propLower == "level" {
				if floatVal, ok := value.(float64); ok {
					metadata["battery_level"] = fmt.Sprintf("%d", int(floatVal))
					if floatVal < 20 {
						metadata["battery_low"] = "true"
					}
					log.Printf("[ZWAVE-MAPPER] Extracted battery level: %d%%", int(floatVal))
				}
			}

			// Water Alarm (CC 113 - Notification)
			if ccID == CC_NOTIFICATION && (propLower == "water alarm" || strings.Contains(propLower, "water")) {
				metadata["value_water"] = fmt.Sprintf("%v", value)
				log.Printf("[ZWAVE-MAPPER] Extracted water alarm: %v", value)
			}

			// Temperature (CC 49 - Multilevel Sensor)
			if ccID == CC_SENSOR_MULTILEVEL && strings.Contains(propLower, "temperature") {
				metadata["value_temperature"] = fmt.Sprintf("%v", value)
				log.Printf("[ZWAVE-MAPPER] Extracted temperature: %v", value)
			}

			// Humidity (CC 49 - Multilevel Sensor)
			if ccID == CC_SENSOR_MULTILEVEL && strings.Contains(propLower, "humidity") {
				metadata["value_humidity"] = fmt.Sprintf("%v", value)
				log.Printf("[ZWAVE-MAPPER] Extracted humidity: %v", value)
			}

			// Motion/Binary sensor (CC 48)
			if ccID == CC_SENSOR_BINARY {
				if strings.Contains(propLower, "motion") {
					metadata["value_motion"] = fmt.Sprintf("%v", value)
				} else if strings.Contains(propLower, "contact") {
					metadata["value_contact"] = fmt.Sprintf("%v", value)
				} else {
					// Generic binary sensor
					metadata[fmt.Sprintf("value_%s", strings.ReplaceAll(propLower, " ", "_"))] = fmt.Sprintf("%v", value)
				}
				log.Printf("[ZWAVE-MAPPER] Extracted binary sensor %s: %v", propertyName, value)
			}
		}
		return
	}

	// Fallback: try as map (legacy format)
	valuesMap, ok := node.Values.(map[string]interface{})
	if !ok {
		return
	}

	// Look for common sensor value patterns
	sensorKeywords := map[string]string{
		"temperature":  "temperature",
		"humidity":     "humidity",
		"leak":         "leak",
		"water":        "water",
		"motion":       "motion",
		"contact":      "contact",
		"tamper":       "tamper",
		"power":        "power",
		"energy":       "energy",
		"brightness":   "brightness",
		"level":        "level",
		"notification": "notification",
	}

	for key, value := range valuesMap {
		keyLower := strings.ToLower(key)

		// Check if this key matches any sensor keywords
		for keyword, metaKey := range sensorKeywords {
			if strings.Contains(keyLower, keyword) {
				// Don't overwrite battery_level which is handled separately
				if metaKey == "level" && strings.Contains(keyLower, "battery") {
					continue
				}
				// Store with value_ prefix
				metadata[fmt.Sprintf("value_%s", metaKey)] = fmt.Sprintf("%v", value)
				log.Printf("[ZWAVE-MAPPER] Extracted value from node: %s = %v", key, value)
				break
			}
		}
	}
}

// isLowBattery checks if battery is low
func isLowBattery(node *ZWaveNode) bool {
	level, ok := findBatteryLevel(node)
	if !ok {
		return false
	}

	// Consider low if below 20%
	return level < 20
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
