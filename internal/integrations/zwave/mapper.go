package zwave

import (
	"fmt"
	"strings"

	"github.com/homesight/homesight/internal/model"
)

// MapNodeToDevice converts a Z-Wave node to a HomeSight device
func MapNodeToDevice(node *ZWaveNode, homeID int) *model.Device {
	// Generate stable device ID: zwave-{homeId}-{nodeId}
	deviceID := fmt.Sprintf("zwave-%d-%d", homeID, node.NodeID)

	// Extract manufacturer/model from device database
	manufacturer := node.DeviceConfig.Manufacturer
	modelName := node.DeviceConfig.Label
	if modelName == "" {
		modelName = fmt.Sprintf("Z-Wave Device (Node %d)", node.NodeID)
	}

	// Determine device type from command classes
	deviceType := inferDeviceType(node)

	// Build metadata
	metadata := map[string]string{
		"manufacturer":     manufacturer,
		"model":           modelName,
		"manufacturer_id": fmt.Sprintf("0x%04x", node.ManufacturerID),
		"product_type":    fmt.Sprintf("0x%04x", node.ProductType),
		"product_id":      fmt.Sprintf("0x%04x", node.ProductID),
		"firmware":        node.FirmwareVersion,
		"security":        node.Security,
		"node_id":         fmt.Sprintf("%d", node.NodeID),
		"interview_stage": fmt.Sprintf("%d", node.InterviewStage),
		"is_listening":    fmt.Sprintf("%t", node.IsListening),
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

	return &model.Device{
		ID:          deviceID,
		Name:        modelName,
		Type:        deviceType,
		Integration: "zwave",
		Enabled:     node.Ready,
		Metadata:    metadata,
	}
}

// inferDeviceType determines HomeSight device type from Z-Wave command classes
func inferDeviceType(node *ZWaveNode) string {
	// Check for specific device types based on command classes
	// Priority: Most specific first

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
		CC_BASIC:                "Basic",
		CC_SWITCH_BINARY:        "Switch Binary",
		CC_SWITCH_MULTILEVEL:    "Switch Multilevel",
		CC_SENSOR_BINARY:        "Sensor Binary",
		CC_SENSOR_MULTILEVEL:    "Sensor Multilevel",
		CC_METER:                "Meter",
		CC_COLOR_SWITCH:         "Color Switch",
		CC_CONFIGURATION:        "Configuration",
		CC_NOTIFICATION:         "Notification",
		CC_MANUFACTURER_SPECIFIC: "Manufacturer Specific",
		CC_BATTERY:              "Battery",
		CC_WAKE_UP:              "Wake Up",
		CC_ASSOCIATION:          "Association",
		CC_VERSION:              "Version",
		CC_INDICATOR:            "Indicator",
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
