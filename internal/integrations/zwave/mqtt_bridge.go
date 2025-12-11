package zwave

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

// MQTTBridge bridges between Z-Wave JS WebSocket and MQTT
// It translates Z-Wave events to HomeSight MQTT topics and vice versa
type MQTTBridge struct {
	ctx        context.Context
	cancel     context.CancelFunc
	client     *Client
	mqttClient mqtt.Client
}

// NewMQTTBridge creates a new Z-Wave MQTT bridge
func NewMQTTBridge(wsURL string, mqttBrokerURL string) *MQTTBridge {
	ctx, cancel := context.WithCancel(context.Background())

	// Create Z-Wave client
	zwaveClient := NewClient(wsURL)

	// Create MQTT client
	opts := mqtt.NewClientOptions().
		AddBroker(mqttBrokerURL).
		SetClientID("homesight-zwave-bridge").
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(2 * time.Second).
		SetCleanSession(true).
		SetKeepAlive(10 * time.Second).
		SetPingTimeout(5 * time.Second)

	mqttClient := mqtt.NewClient(opts)

	return &MQTTBridge{
		ctx:        ctx,
		cancel:     cancel,
		client:     zwaveClient,
		mqttClient: mqttClient,
	}
}

// Start initializes the Z-Wave MQTT bridge
func (b *MQTTBridge) Start() error {
	log.Println("[ZWAVE-BRIDGE] Starting Z-Wave MQTT bridge...")

	// Connect to MQTT broker
	log.Println("[ZWAVE-BRIDGE] Connecting to MQTT broker...")
	token := b.mqttClient.Connect()

	// Wait for connection with timeout
	if !token.WaitTimeout(5 * time.Second) {
		log.Println("[ZWAVE-BRIDGE] Warning: MQTT broker connection timeout - will retry in background")
	} else if token.Error() != nil {
		log.Printf("[ZWAVE-BRIDGE] Warning: Failed to connect to MQTT broker: %v - will retry in background", token.Error())
	} else {
		log.Println("[ZWAVE-BRIDGE] Connected to MQTT broker")
	}

	// Subscribe to command topics asynchronously with retries
	go b.subscribeToCommands()

	// Set up Z-Wave event handlers
	b.setupEventHandlers()

	// Set connection callbacks
	b.client.SetOnConnect(func() {
		log.Println("[ZWAVE-BRIDGE] Connected to Z-Wave JS Server")
		go b.publishInitialDiscovery()
	})

	b.client.SetOnDisconnect(func() {
		log.Println("[ZWAVE-BRIDGE] Disconnected from Z-Wave JS Server")
	})

	// Connect to Z-Wave JS
	if err := b.client.Connect(); err != nil {
		return fmt.Errorf("failed to connect to Z-Wave JS: %w", err)
	}

	log.Println("[ZWAVE-BRIDGE] Z-Wave MQTT bridge started")
	return nil
}

// subscribeToCommands subscribes to command topics with retries
func (b *MQTTBridge) subscribeToCommands() {
	// Wait longer initially to give MQTT time to stabilize
	time.Sleep(2 * time.Second)

	maxRetries := 20
	retryDelay := 1 * time.Second

	for attempt := 0; attempt < maxRetries; attempt++ {
		// Check if client is connected before attempting subscribe
		if !b.mqttClient.IsConnected() {
			log.Printf("[ZWAVE-BRIDGE] MQTT not connected (attempt %d/%d), waiting...", attempt+1, maxRetries)
			time.Sleep(retryDelay)
			continue
		}

		log.Printf("[ZWAVE-BRIDGE] Attempting to subscribe to command topics (attempt %d/%d)...", attempt+1, maxRetries)

		// Subscribe to legacy command topic
		token := b.mqttClient.Subscribe("homesight/cmd/+", 1, b.handleCommand)
		if !token.Wait() || token.Error() != nil {
			log.Printf("[ZWAVE-BRIDGE] Subscribe attempt %d failed for homesight/cmd/+: %v", attempt+1, token.Error())
			time.Sleep(retryDelay)
			continue
		}

		// Subscribe to entity set topic
		token = b.mqttClient.Subscribe("homesight/entity/set/+", 1, b.handleEntitySet)
		if !token.Wait() || token.Error() != nil {
			log.Printf("[ZWAVE-BRIDGE] Subscribe attempt %d failed for homesight/entity/set/+: %v", attempt+1, token.Error())
			time.Sleep(retryDelay)
			continue
		}

		log.Println("[ZWAVE-BRIDGE] ✓ Successfully subscribed to command topics!")
		return
	}

	log.Println("[ZWAVE-BRIDGE] ⚠️ Failed to subscribe to command topics after all retries - commands will not work!")
}

// Stop shuts down the bridge
func (b *MQTTBridge) Stop() error {
	log.Println("[ZWAVE-BRIDGE] Stopping Z-Wave MQTT bridge...")
	b.cancel()
	b.mqttClient.Disconnect(250)
	return b.client.Close()
}

// setupEventHandlers configures Z-Wave event handlers
func (b *MQTTBridge) setupEventHandlers() {
	// Node added - publish discovery
	b.client.On("node added", func(event Event) {
		b.handleNodeAdded(event)
	})

	// Node ready - publish metadata
	b.client.On("node ready", func(event Event) {
		b.handleNodeReady(event)
	})

	// Node removed - publish removal
	b.client.On("node removed", func(event Event) {
		b.handleNodeRemoved(event)
	})

	// Value updated - publish state
	b.client.On("value updated", func(event Event) {
		b.handleValueUpdated(event)
	})

	// Notification - publish incident
	b.client.On("notification", func(event Event) {
		b.handleNotification(event)
	})
}

// publishInitialDiscovery publishes discovery messages for all existing nodes
func (b *MQTTBridge) publishInitialDiscovery() {
	time.Sleep(2 * time.Second) // Wait for connection to stabilize

	log.Println("[ZWAVE-BRIDGE] Publishing initial discovery...")

	b.client.stateMu.RLock()
	nodes := make(map[int]*ZWaveNode)
	for k, v := range b.client.nodes {
		nodes[k] = v
	}
	homeID := b.client.homeID
	b.client.stateMu.RUnlock()

	for _, node := range nodes {
		if !node.Ready {
			continue
		}
		b.publishDiscovery(node, homeID)
	}

	log.Printf("[ZWAVE-BRIDGE] Initial discovery complete: %d nodes", len(nodes))
}

// handleNodeAdded processes node added events
func (b *MQTTBridge) handleNodeAdded(event Event) {
	nodeData, ok := event.Data["node"]
	if !ok {
		return
	}

	data, _ := json.Marshal(nodeData)
	var node ZWaveNode
	if err := json.Unmarshal(data, &node); err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to parse node: %v", err)
		return
	}

	log.Printf("[ZWAVE-BRIDGE] Node added: %d", node.NodeID)

	// Don't publish discovery yet - wait for node ready
}

// handleNodeReady processes node ready events
func (b *MQTTBridge) handleNodeReady(event Event) {
	nodeData, ok := event.Data["node"]
	if !ok {
		return
	}

	data, _ := json.Marshal(nodeData)
	var node ZWaveNode
	if err := json.Unmarshal(data, &node); err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to parse node: %v", err)
		return
	}

	log.Printf("[ZWAVE-BRIDGE] Node ready: %d - %s", node.NodeID, node.DeviceConfig.Label)

	b.client.stateMu.RLock()
	homeID := b.client.homeID
	b.client.stateMu.RUnlock()

	b.publishDiscovery(&node, homeID)
}

// handleNodeRemoved processes node removed events
func (b *MQTTBridge) handleNodeRemoved(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	nodeID := int(nodeIDFloat)

	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	log.Printf("[ZWAVE-BRIDGE] Node removed: %d", nodeID)

	// Publish removal message
	topic := fmt.Sprintf("homesight/zwave/%d/removed", nodeID)
	payload := map[string]interface{}{
		"device_id":   deviceID,
		"integration": "zwave",
		"reason":      "node_removed",
	}

	b.publishJSON(topic, payload, false)
}

// handleValueUpdated processes value update events
func (b *MQTTBridge) handleValueUpdated(event Event) {
	// Extract nodeId from event.Data (top level)
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	// Extract args from event.Data
	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	commandClass, _ := args["commandClass"].(float64)
	property, _ := args["property"].(string)
	newValue := args["newValue"]

	// Extract unit metadata if available from Z-Wave JS
	// The metadata contains the unit string (e.g., "°F", "°C", "%")
	var unit string
	if metadata, ok := args["metadata"].(map[string]interface{}); ok {
		if unitStr, ok := metadata["unit"].(string); ok {
			unit = unitStr
		}
	}

	log.Printf("[ZWAVE-BRIDGE] Value updated: node=%d cc=%d property=%s value=%v unit=%s", nodeID, int(commandClass), property, newValue, unit)

	// Standardize temperature values to Fahrenheit
	if property == "Air temperature" {
		if numVal, ok := newValue.(float64); ok {
			// If no unit provided, assume Celsius if value is in typical room temp range (10-40)
			// Otherwise assume Fahrenheit
			shouldConvert := false
			if unit == "°C" || unit == "C" {
				shouldConvert = true
			} else if unit == "" && numVal >= 10 && numVal <= 40 {
				// No unit metadata - assume Celsius for typical indoor temps (50-104°F = 10-40°C)
				shouldConvert = true
				log.Printf("[ZWAVE-BRIDGE] No unit metadata for temperature %.1f, assuming Celsius", numVal)
			}

			if shouldConvert {
				// Convert Celsius to Fahrenheit: F = C * 9/5 + 32
				newValue = numVal*9.0/5.0 + 32.0
				unit = "°F"
				log.Printf("[ZWAVE-BRIDGE] Converted temperature: %.1f°C -> %.1f°F", numVal, newValue.(float64))
			}
		}
	}

	// Publish state update
	topic := fmt.Sprintf("homesight/zwave/%d/state", nodeID)

	// Get normalized property name
	propertyNormalized := normalizePropertyName(property, int(commandClass))

	// For temperature readings that we converted, ONLY store the normalized version
	// This avoids duplicate "Air temperature" + "temperature_f" fields
	values := map[string]interface{}{}
	if property == "Air temperature" {
		// Only store normalized version (temperature_f) - skip original
		values[propertyNormalized] = newValue
	} else {
		// For other properties, store both original and normalized (if different)
		values[property] = newValue
		if propertyNormalized != property && propertyNormalized != strings.ToLower(strings.ReplaceAll(property, " ", "_")) {
			values[propertyNormalized] = newValue
		}
	}

	// Store unit metadata if available from Z-Wave JS
	// For temperature, only store with normalized property name
	if unit != "" {
		if property == "Air temperature" {
			// Only store unit for normalized property (temperature_f_unit)
			values[propertyNormalized+"_unit"] = unit
		} else {
			// For other properties, store with both original and normalized names
			values[property+"_unit"] = unit
			if propertyNormalized != property {
				values[propertyNormalized+"_unit"] = unit
			}
		}
	}

	state := map[string]interface{}{
		"ts":     time.Now().Format(time.RFC3339),
		"values": values,
	}

	b.publishJSON(topic, state, false)

	// Publish entity update event
	b.publishEntityUpdate(nodeID, int(commandClass), property, newValue, unit)

	// Check if this should trigger an incident
	b.checkIncidentConditions(nodeID, int(commandClass), property, newValue, args)
}

// handleNotification processes notification events
func (b *MQTTBridge) handleNotification(event Event) {
	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	nodeIDFloat, _ := args["nodeId"].(float64)
	nodeID := int(nodeIDFloat)

	notifTypeFloat, _ := args["type"].(float64)
	notifType := int(notifTypeFloat)

	notifEventFloat, _ := args["event"].(float64)
	notifEvent := int(notifEventFloat)

	label, _ := args["label"].(string)
	eventLabel, _ := args["eventLabel"].(string)

	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	log.Printf("[ZWAVE-BRIDGE] Notification: node=%d type=%d event=%d label=%s", nodeID, notifType, notifEvent, label)

	// Publish incident
	severity := "info"
	title := fmt.Sprintf("%s: %s", label, eventLabel)
	incidentType := "notification"

	// Map to specific incident types and severities
	switch notifType {
	case NOTIFICATION_WATER:
		switch notifEvent {
		case WATER_LEAK_DETECTED, WATER_LEAK_DETECTED_UNKNOWN:
			severity = "critical"
			title = "Water Leak Detected"
			incidentType = "leak"
		case WATER_EVENT_CLEARED:
			// Don't publish - this should resolve existing incidents
			return
		default:
			severity = "high"
		}
	case NOTIFICATION_SMOKE:
		severity = "critical"
		title = "Smoke Detected"
		incidentType = "smoke"
	case NOTIFICATION_CO:
		severity = "critical"
		title = "Carbon Monoxide Detected"
		incidentType = "co"
	case NOTIFICATION_BURGLAR:
		severity = "high"
		incidentType = "intrusion"
	case NOTIFICATION_POWER:
		severity = "medium"
	}

	incidentID := fmt.Sprintf("%s-%d", deviceID, time.Now().Unix())
	topic := fmt.Sprintf("homesight/incidents/%s/%s", deviceID, incidentID)

	incident := map[string]interface{}{
		"incident_id":   incidentID,
		"device_id":     deviceID,
		"title":         title,
		"description":   eventLabel,
		"severity":      severity,
		"incident_type": incidentType,
		"ts":            time.Now().Format(time.RFC3339),
		"data": map[string]interface{}{
			"notification_type":  notifType,
			"notification_event": notifEvent,
			"label":              label,
		},
	}

	b.publishJSON(topic, incident, false)
}

// publishDiscovery publishes a device discovery message with full mapped device data
func (b *MQTTBridge) publishDiscovery(node *ZWaveNode, homeID uint32) {
	topic := fmt.Sprintf("homesight/zwave/%d/discovery", node.NodeID)

	// Use mapper to get full device with controls, readings, etc.
	device := MapNodeToDevice(node, homeID)

	// Convert to discovery format (maintain compatibility with MQTT consumer)
	discovery := map[string]interface{}{
		"device_id":    device.ID,
		"integration":  device.Integration,
		"name":         device.Name,
		"manufacturer": device.Manufacturer,
		"model":        device.Model,
		"hw_id":        fmt.Sprintf("%d", node.NodeID),
		"capabilities": inferCapabilities(node),
		// Include unified contract fields
		"readings":     device.Readings,
		"controls":     device.Controls,
		"battery":      device.Battery,
		"connectivity": device.Connectivity,
		// Include entity-based model
		"entities": device.Entities,
	}

	b.publishJSON(topic, discovery, true) // retained
}

// handleCommand processes MQTT command messages (legacy)
func (b *MQTTBridge) handleCommand(client mqtt.Client, msg mqtt.Message) {
	topic := msg.Topic()
	payload := msg.Payload()

	// Extract device ID from topic: homesight/cmd/zwave-<nodeId>
	parts := strings.Split(topic, "/")
	if len(parts) != 3 {
		return
	}

	deviceID := parts[2]
	if !strings.HasPrefix(deviceID, "zwave-") {
		return
	}

	nodeIDStr := strings.TrimPrefix(deviceID, "zwave-")
	var nodeID int
	fmt.Sscanf(nodeIDStr, "%d", &nodeID)

	// Parse command
	var cmd map[string]interface{}
	if err := json.Unmarshal(payload, &cmd); err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to parse command: %v", err)
		return
	}

	command, _ := cmd["command"].(string)
	args, _ := cmd["args"].(map[string]interface{})

	log.Printf("[ZWAVE-BRIDGE] Command received: node=%d command=%s", nodeID, command)

	// Translate to Z-Wave JS command
	b.executeCommand(nodeID, command, args)
}

// handleEntitySet processes entity set commands via MQTT
func (b *MQTTBridge) handleEntitySet(client mqtt.Client, msg mqtt.Message) {
	topic := msg.Topic()
	payload := msg.Payload()

	// Extract device ID from topic: homesight/entity/set/zwave-<nodeId>
	parts := strings.Split(topic, "/")
	if len(parts) != 4 {
		log.Printf("[ZWAVE-BRIDGE] Invalid entity set topic: %s", topic)
		return
	}

	deviceID := parts[3]
	if !strings.HasPrefix(deviceID, "zwave-") {
		return
	}

	nodeIDStr := strings.TrimPrefix(deviceID, "zwave-")
	var nodeID int
	fmt.Sscanf(nodeIDStr, "%d", &nodeID)

	// Parse entity set message
	var req struct {
		EntityID string      `json:"entity_id"`
		Value    interface{} `json:"value"`
	}
	if err := json.Unmarshal(payload, &req); err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to parse entity set message: %v", err)
		return
	}

	log.Printf("[ZWAVE-BRIDGE] Entity set received: node=%d entity=%s value=%v", nodeID, req.EntityID, req.Value)

	// Extract metadata from entity ID
	// Formats:
	//   - zwave-42-cc37-targetValue (no propertyKey)
	//   - zwave-43-cc112-40-255 (with propertyKey)
	entityParts := strings.Split(req.EntityID, "-")
	if len(entityParts) < 3 {
		log.Printf("[ZWAVE-BRIDGE] Invalid entity ID format: %s", req.EntityID)
		return
	}

	// Extract command class from ccXX part
	ccPart := entityParts[2]
	if !strings.HasPrefix(ccPart, "cc") {
		log.Printf("[ZWAVE-BRIDGE] Invalid entity ID (missing cc prefix): %s", req.EntityID)
		return
	}

	var commandClass int
	fmt.Sscanf(ccPart, "cc%d", &commandClass)

	// Extract property and propertyKey
	// For numeric properties with propertyKey: entityParts[3]=property, entityParts[4]=propertyKey
	// For string properties: entityParts[3:] = property parts
	var property string
	var propertyKey interface{} = nil

	if len(entityParts) >= 5 {
		// Check if last part is a numeric propertyKey
		lastPart := entityParts[len(entityParts)-1]
		var pkNum int
		if n, err := fmt.Sscanf(lastPart, "%d", &pkNum); err == nil && n == 1 {
			// Last part is numeric - treat as propertyKey
			propertyKey = pkNum
			property = strings.Join(entityParts[3:len(entityParts)-1], "-")
		} else {
			// Last part is not numeric - include in property
			property = strings.Join(entityParts[3:], "-")
		}
	} else {
		property = strings.Join(entityParts[3:], "-")
	}

	log.Printf("[ZWAVE-BRIDGE] Setting Z-Wave value: node=%d cc=%d property=%s propertyKey=%v value=%v",
		nodeID, commandClass, property, propertyKey, req.Value)

	// Call Z-Wave JS to set the value
	b.setValueByEntity(nodeID, commandClass, property, propertyKey, req.Value)
}

// executeCommand executes a Z-Wave command
func (b *MQTTBridge) executeCommand(nodeID int, command string, args map[string]interface{}) {
	switch command {
	case "set_switch":
		on, _ := args["on"].(bool)
		value := false
		if on {
			value = true
		}
		b.setValue(nodeID, CC_SWITCH_BINARY, "targetValue", value)

	case "set_level":
		level, _ := args["level"].(float64)
		b.setValue(nodeID, CC_SWITCH_MULTILEVEL, "targetValue", int(level))

	case "refresh":
		// Refresh all values for the node
		b.client.Call("node.refresh_values", map[string]interface{}{
			"nodeId": nodeID,
		})

	default:
		log.Printf("[ZWAVE-BRIDGE] Unknown command: %s", command)
	}
}

// setValue sets a Z-Wave value
func (b *MQTTBridge) setValue(nodeID int, commandClass int, property string, value interface{}) {
	// Z-Wave JS Server expects valueId as a nested object
	_, err := b.client.Call("node.set_value", map[string]interface{}{
		"nodeId": nodeID,
		"valueId": map[string]interface{}{
			"commandClass": commandClass,
			"property":     property,
		},
		"value": value,
	})

	if err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to set value: %v", err)
	} else {
		log.Printf("[ZWAVE-BRIDGE] Successfully set value: node=%d cc=%d property=%s value=%v", nodeID, commandClass, property, value)
	}
}

// setValueByEntity sets a Z-Wave value from entity metadata
func (b *MQTTBridge) setValueByEntity(nodeID int, commandClass int, property string, propertyKey interface{}, value interface{}) {
	// For Configuration command class (112), property must be a number
	var propertyValue interface{} = property
	if commandClass == CC_CONFIGURATION {
		var propNum int
		fmt.Sscanf(property, "%d", &propNum)
		propertyValue = propNum
	}

	// Build valueId object
	valueId := map[string]interface{}{
		"commandClass": commandClass,
		"property":     propertyValue,
	}

	// Add propertyKey if provided
	if propertyKey != nil {
		valueId["propertyKey"] = propertyKey
	}

	// Z-Wave JS Server expects valueId as a nested object
	result, err := b.client.Call("node.set_value", map[string]interface{}{
		"nodeId":  nodeID,
		"valueId": valueId,
		"value":   value,
	})

	// Check if command succeeded
	if err != nil {
		log.Printf("[ZWAVE-BRIDGE] ❌ Failed to set entity value: %v", err)
		b.publishEntityUpdateResult(nodeID, commandClass, property, propertyKey, value, false, err.Error())
	} else if resultMap, ok := result.(map[string]interface{}); ok {
		if successVal, ok := resultMap["success"].(bool); ok && successVal {
			log.Printf("[ZWAVE-BRIDGE] ✓ Successfully set entity: node=%d cc=%d property=%s propertyKey=%v value=%v", nodeID, commandClass, property, propertyKey, value)
			b.publishEntityUpdateResult(nodeID, commandClass, property, propertyKey, value, true, "")
		} else {
			log.Printf("[ZWAVE-BRIDGE] ❌ Z-Wave rejected entity set: node=%d cc=%d property=%s propertyKey=%v value=%v", nodeID, commandClass, property, propertyKey, value)
			b.publishEntityUpdateResult(nodeID, commandClass, property, propertyKey, value, false, "Z-Wave JS rejected command")
		}
	} else {
		log.Printf("[ZWAVE-BRIDGE] ✓ Successfully queued entity set: node=%d cc=%d property=%s propertyKey=%v value=%v", nodeID, commandClass, property, propertyKey, value)
		b.publishEntityUpdateResult(nodeID, commandClass, property, propertyKey, value, true, "")
	}
}

// publishEntityUpdateResult publishes the result of an entity set operation
func (b *MQTTBridge) publishEntityUpdateResult(nodeID int, commandClass int, property string, propertyKey interface{}, value interface{}, success bool, errorMsg string) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	entityID := fmt.Sprintf("%s-cc%d-%s", deviceID, commandClass, property)
	if propertyKey != nil {
		entityID = fmt.Sprintf("%s-%v", entityID, propertyKey)
	}

	topic := fmt.Sprintf("homesight/entity/result/%s", deviceID)
	payload := map[string]interface{}{
		"entity_id": entityID,
		"value":     value,
		"success":   success,
		"ts":        time.Now().Format(time.RFC3339),
	}

	if !success {
		payload["error"] = errorMsg
	}

	b.publishJSON(topic, payload, false)
}

// publishEntityUpdate publishes an entity value update event
func (b *MQTTBridge) publishEntityUpdate(nodeID int, commandClass int, property string, value interface{}, unit string) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	entityID := fmt.Sprintf("%s-cc%d-%s", deviceID, commandClass, property)

	topic := fmt.Sprintf("homesight/entity/updated/%s", deviceID)
	payload := map[string]interface{}{
		"entity_id": entityID,
		"value":     value,
		"ts":        time.Now().Format(time.RFC3339),
	}

	if unit != "" {
		payload["unit"] = unit
	}

	b.publishJSON(topic, payload, false)
}

// checkIncidentConditions checks if a value update should trigger an incident
func (b *MQTTBridge) checkIncidentConditions(nodeID, commandClass int, property string, value interface{}, args map[string]interface{}) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	// Low battery detection
	if commandClass == CC_BATTERY && property == "level" {
		if level, ok := value.(float64); ok && level < 20 {
			incidentID := fmt.Sprintf("%s-battery-%d", deviceID, time.Now().Unix())
			topic := fmt.Sprintf("homesight/incidents/%s/%s", deviceID, incidentID)

			incident := map[string]interface{}{
				"incident_id":   incidentID,
				"device_id":     deviceID,
				"title":         "Low Battery",
				"description":   fmt.Sprintf("Battery level is %d%%", int(level)),
				"severity":      "low",
				"incident_type": "battery",
				"ts":            time.Now().Format(time.RFC3339),
				"data": map[string]interface{}{
					"battery_level": level,
				},
			}

			b.publishJSON(topic, incident, false)
		}
	}
}

// publishJSON publishes a JSON payload to MQTT
func (b *MQTTBridge) publishJSON(topic string, payload interface{}, retained bool) {
	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to marshal payload: %v", err)
		return
	}

	token := b.mqttClient.Publish(topic, 0, retained, data)
	if token.Wait() && token.Error() != nil {
		log.Printf("[ZWAVE-BRIDGE] Failed to publish to %s: %v", topic, token.Error())
	}
}

// normalizePropertyName converts Z-Wave property names to friendly names
func normalizePropertyName(property string, commandClass int) string {
	switch property {
	case "currentValue":
		switch commandClass {
		case CC_SENSOR_BINARY:
			return "motion"
		case CC_SWITCH_BINARY:
			return "switch_state"
		case CC_SWITCH_MULTILEVEL:
			return "level"
		default:
			return "value"
		}
	case "level":
		return "battery_pct"
	case "Air temperature":
		return "temperature_f"
	case "Humidity":
		return "humidity_pct"
	default:
		// Convert to snake_case
		normalized := strings.ToLower(property)
		normalized = strings.ReplaceAll(normalized, " ", "_")
		return normalized
	}
}

// inferCapabilities infers device capabilities from Z-Wave node data
func inferCapabilities(node *ZWaveNode) []string {
	capabilities := []string{}

	// Check command classes (CommandClasses is a map[int]CommandClass)
	for ccID := range node.CommandClasses {
		switch ccID {
		case CC_SENSOR_BINARY:
			capabilities = append(capabilities, "motion")
		case CC_SWITCH_BINARY:
			capabilities = append(capabilities, "switch")
		case CC_SWITCH_MULTILEVEL:
			capabilities = append(capabilities, "dimmer")
		case CC_BATTERY:
			capabilities = append(capabilities, "battery")
		case CC_NOTIFICATION:
			// Could be leak, smoke, CO, etc. - need more context
			capabilities = append(capabilities, "notification")
		case CC_SENSOR_MULTILEVEL:
			capabilities = append(capabilities, "temperature", "humidity")
		}
	}

	// Deduplicate
	seen := make(map[string]bool)
	result := []string{}
	for _, cap := range capabilities {
		if !seen[cap] {
			seen[cap] = true
			result = append(result, cap)
		}
	}

	return result
}
