package mqtt

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/homesight/homesight/internal/alarms"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/events"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/model"
)

// Consumer processes MQTT messages from integrations and updates the device registry
type Consumer struct {
	ctx          context.Context
	cancel       context.CancelFunc
	client       mqtt.Client
	deviceRepo   db.DeviceRepository
	eventBus     events.EventBus
	incidentSvc  incidents.IncidentService
	alarmManager *alarms.Manager
}

// NewConsumer creates a new MQTT consumer
func NewConsumer(
	brokerURL string,
	clientID string,
	deviceRepo db.DeviceRepository,
	eventBus events.EventBus,
	incidentSvc incidents.IncidentService,
) (*Consumer, error) {
	ctx, cancel := context.WithCancel(context.Background())

	opts := mqtt.NewClientOptions().
		AddBroker(brokerURL).
		SetClientID(clientID).
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second)

	client := mqtt.NewClient(opts)

	c := &Consumer{
		ctx:          ctx,
		cancel:       cancel,
		client:       client,
		deviceRepo:   deviceRepo,
		eventBus:     eventBus,
		incidentSvc:  incidentSvc,
		alarmManager: alarms.NewManager(incidentSvc),
	}

	return c, nil
}

// Start begins consuming MQTT messages
func (c *Consumer) Start() error {
	log.Println("[MQTT-CONSUMER] Connecting to MQTT broker...")

	token := c.client.Connect()

	// Wait with timeout to avoid blocking indefinitely
	if !token.WaitTimeout(5 * time.Second) {
		log.Println("[MQTT-CONSUMER] Warning: MQTT broker connection timeout - will retry in background")
		// Don't return error - let auto-reconnect handle it
		return nil
	}

	if token.Error() != nil {
		log.Printf("[MQTT-CONSUMER] Warning: Failed to connect to MQTT broker: %v - will retry in background", token.Error())
		// Don't return error - let auto-reconnect handle it
		return nil
	}

	log.Println("[MQTT-CONSUMER] Connected to MQTT broker")

	// Subscribe to integration topics
	subscriptions := map[string]byte{
		"homesight/+/+/discovery": 0,
		"homesight/+/+/metadata":  0,
		"homesight/+/+/state":     0,
		"homesight/+/+/removed":   0,
		"homesight/incidents/#":   0,
	}

	for topic, qos := range subscriptions {
		log.Printf("[MQTT-CONSUMER] Subscribing to: %s", topic)
		token := c.client.Subscribe(topic, qos, c.handleMessage)
		if token.Wait() && token.Error() != nil {
			return fmt.Errorf("failed to subscribe to %s: %w", topic, token.Error())
		}
	}

	log.Println("[MQTT-CONSUMER] Subscribed to all integration topics")
	return nil
}

// Stop shuts down the consumer
func (c *Consumer) Stop() error {
	log.Println("[MQTT-CONSUMER] Stopping MQTT consumer...")
	c.cancel()
	c.client.Disconnect(250)
	return nil
}

// forwardToHSIL sends sensor events to HSIL for continuous learning
func (c *Consumer) forwardToHSIL(deviceID, sensorID, eventType string, value interface{}, location, deviceType string) {
	payload := map[string]interface{}{
		"device_id":   deviceID,
		"sensor_id":   sensorID,
		"event_type":  eventType,
		"value":       value,
		"location":    location,
		"device_type": deviceType,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to marshal HSIL event: %v", err)
		return
	}

	// Fire and forget - don't block MQTT processing
	go func() {
		client := &http.Client{Timeout: 2 * time.Second}
		// Use AI sidecar URL from environment (set by Docker compose)
		aiURL := os.Getenv("AI_SERVICE_URL")
		if aiURL == "" {
			aiURL = "http://ai-sidecar:8001" // Docker network default
		}
		resp, err := client.Post(aiURL+"/hsil/events", "application/json", bytes.NewBuffer(jsonData))
		if err != nil {
			// Only log first few failures to avoid spam
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			log.Printf("[MQTT-CONSUMER] HSIL returned status %d for %s/%s", resp.StatusCode, deviceID, eventType)
		}
	}()
}

// handleMessage routes incoming MQTT messages to appropriate handlers
func (c *Consumer) handleMessage(client mqtt.Client, msg mqtt.Message) {
	topic := msg.Topic()
	payload := msg.Payload()

	// Parse topic structure: homesight/<integration>/<deviceId>/<messageType>
	parts := strings.Split(topic, "/")

	if len(parts) < 4 {
		log.Printf("[MQTT-CONSUMER] Invalid topic format: %s", topic)
		return
	}

	if parts[0] != "homesight" {
		return
	}

	// Handle incident messages separately
	if parts[1] == "incidents" {
		c.handleIncidentMessage(parts, payload)
		return
	}

	integration := parts[1]
	deviceID := parts[2]
	messageType := parts[3]

	switch messageType {
	case "discovery":
		c.handleDiscovery(integration, deviceID, payload)
	case "metadata":
		c.handleMetadata(deviceID, payload)
	case "state":
		c.handleState(deviceID, payload)
	case "removed":
		c.handleRemoved(deviceID, payload)
	case "attr":
		// homesight/<integration>/<deviceId>/attr/<name>
		if len(parts) >= 5 {
			attrName := parts[4]
			c.handleAttribute(deviceID, attrName, payload)
		}
	default:
		log.Printf("[MQTT-CONSUMER] Unknown message type: %s", messageType)
	}
}

// handleDiscovery processes device discovery messages
func (c *Consumer) handleDiscovery(integration, deviceID string, payload []byte) {
	var msg DiscoveryMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse discovery message: %v", err)
		return
	}

	// Validate required fields
	if msg.DeviceID == "" {
		msg.DeviceID = fmt.Sprintf("%s-%s", integration, deviceID)
	}
	if msg.Integration == "" {
		msg.Integration = integration
	}

	log.Printf("[MQTT-CONSUMER] Discovery: %s (%s) - %s %s", msg.DeviceID, msg.Integration, msg.Manufacturer, msg.Model)

	// Try to fetch existing device to preserve metadata (e.g., battery_level from Z-Wave)
	existingDevice, _ := c.deviceRepo.Get(c.ctx, msg.DeviceID)

	// Convert to model.Device
	device := &model.Device{
		ID:          msg.DeviceID,
		Name:        msg.Name,
		Type:        inferDeviceType(msg.Capabilities),
		Integration: msg.Integration,
		Enabled:     true,
		LastSeen:    time.Now(),
		Metadata:    make(map[string]string),
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}

	// Preserve existing device state (zone_id, asset_id, metadata, docs status, etc.)
	if existingDevice != nil {
		// Preserve zone and asset assignments (user-defined)
		device.ZoneID = existingDevice.ZoneID
		device.AssetID = existingDevice.AssetID
		// Preserve alias (user-defined name)
		device.Alias = existingDevice.Alias
		// Preserve existing created_at
		device.CreatedAt = existingDevice.CreatedAt
		// Preserve docs ingestion status
		device.DocsIngested = existingDevice.DocsIngested
		device.DocsIngestedAt = existingDevice.DocsIngestedAt
		device.DocsStatus = existingDevice.DocsStatus
		// Preserve existing metadata (e.g., battery_level, firmware_version from Z-Wave integration)
		if existingDevice.Metadata != nil {
			for k, v := range existingDevice.Metadata {
				device.Metadata[k] = v
			}
		}
	}

	if device.Name == "" {
		device.Name = msg.DeviceID
	}

	// Update metadata from discovery message (overwrite with new values if present)
	if msg.Manufacturer != "" {
		device.Metadata["manufacturer"] = msg.Manufacturer
	}
	if msg.Model != "" {
		device.Metadata["model"] = msg.Model
	}
	if msg.HwID != "" {
		device.Metadata["hw_id"] = msg.HwID
	}
	if len(msg.Capabilities) > 0 {
		capsJSON, _ := json.Marshal(msg.Capabilities)
		device.Metadata["capabilities"] = string(capsJSON)
	}

	// Upsert to database
	if err := c.deviceRepo.Upsert(c.ctx, device); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to upsert device: %v", err)
		return
	}

	// Emit discovery event
	event := model.DeviceEvent{
		DeviceID:  device.ID,
		SensorID:  device.ID,
		Timestamp: time.Now(),
		ValueType: "discovery",
		Value:     "mqtt",
		Metadata: map[string]string{
			"integration":  device.Integration,
			"manufacturer": msg.Manufacturer,
			"model":        msg.Model,
		},
	}
	c.eventBus.Publish(event)

	log.Printf("[MQTT-CONSUMER] Device registered: %s", device.ID)
}

// handleMetadata processes metadata update messages
func (c *Consumer) handleMetadata(deviceID string, payload []byte) {
	var msg MetadataMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse metadata message: %v", err)
		return
	}

	log.Printf("[MQTT-CONSUMER] Metadata update: %s", deviceID)

	// Get existing device
	device, err := c.deviceRepo.Get(c.ctx, deviceID)
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to get device for metadata update: %v", err)
		return
	}
	if device == nil {
		log.Printf("[MQTT-CONSUMER] Device not found for metadata update: %s", deviceID)
		return
	}

	// Update fields
	if msg.ZoneID != "" {
		device.ZoneID = msg.ZoneID
	}
	if msg.AssetID != "" {
		device.AssetID = msg.AssetID
	}
	if msg.Enabled != nil {
		device.Enabled = *msg.Enabled
	}
	if msg.Metadata != nil {
		if device.Metadata == nil {
			device.Metadata = make(map[string]string)
		}
		for k, v := range msg.Metadata {
			device.Metadata[k] = v
		}
	}

	device.UpdatedAt = time.Now()

	// Save to database
	if err := c.deviceRepo.Upsert(c.ctx, device); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to update device metadata: %v", err)
	}
}

// handleState processes state update messages
func (c *Consumer) handleState(deviceID string, payload []byte) {
	var msg StateMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse state message: %v", err)
		return
	}

	log.Printf("[MQTT-CONSUMER] State update: %s (%d values)", deviceID, len(msg.Values))

	// Update device last seen
	device, err := c.deviceRepo.Get(c.ctx, deviceID)
	if err == nil && device != nil {
		device.LastSeen = time.Now()
		device.UpdatedAt = time.Now()

		// Store state values in metadata
		if device.Metadata == nil {
			device.Metadata = make(map[string]string)
		}
		for k, v := range msg.Values {
			device.Metadata[fmt.Sprintf("state_%s", k)] = fmt.Sprintf("%v", v)
		}

		c.deviceRepo.Upsert(c.ctx, device)
	}

	// Publish device events for each value
	for key, value := range msg.Values {
		valueType := "string"
		switch value.(type) {
		case float64, float32:
			valueType = "float"
		case int, int32, int64:
			valueType = "float"
			value = float64(value.(int))
		case bool:
			valueType = "bool"
		}

		event := model.DeviceEvent{
			DeviceID:  deviceID,
			SensorID:  fmt.Sprintf("%s_%s", deviceID, key),
			Timestamp: msg.Timestamp,
			ValueType: valueType,
			Value:     value,
			Metadata: map[string]string{
				"source": "mqtt",
				"key":    key,
			},
		}
		c.eventBus.Publish(event)

		// Forward to HSIL for continuous ML learning
		location := "unknown"
		deviceType := "sensor"
		if device != nil {
			if device.ZoneID != "" {
				location = device.ZoneID
			}
			if device.Type != "" {
				deviceType = device.Type
			}
		}
		c.forwardToHSIL(deviceID, event.SensorID, key, value, location, deviceType)

		// Check for alarm conditions and manage incidents
		if err := c.alarmManager.ProcessStateUpdate(c.ctx, deviceID, key, value, device); err != nil {
			log.Printf("[MQTT-CONSUMER] Failed to process alarm for %s/%s: %v", deviceID, key, err)
		}
	}
}

// handleAttribute processes individual attribute update messages
func (c *Consumer) handleAttribute(deviceID, attrName string, payload []byte) {
	var msg AttributeMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse attribute message: %v", err)
		return
	}

	log.Printf("[MQTT-CONSUMER] Attribute update: %s/%s = %v", deviceID, attrName, msg.Value)

	// Update device metadata
	device, err := c.deviceRepo.Get(c.ctx, deviceID)
	if err == nil && device != nil {
		if device.Metadata == nil {
			device.Metadata = make(map[string]string)
		}
		device.Metadata[fmt.Sprintf("attr_%s", attrName)] = fmt.Sprintf("%v", msg.Value)
		device.LastSeen = time.Now()
		device.UpdatedAt = time.Now()
		c.deviceRepo.Upsert(c.ctx, device)
	}

	// Publish event
	valueType := "string"
	switch msg.Value.(type) {
	case float64, float32:
		valueType = "float"
	case bool:
		valueType = "bool"
	}

	event := model.DeviceEvent{
		DeviceID:  deviceID,
		SensorID:  fmt.Sprintf("%s_%s", deviceID, attrName),
		Timestamp: msg.Timestamp,
		ValueType: valueType,
		Value:     msg.Value,
		Metadata: map[string]string{
			"source": "mqtt",
			"attr":   attrName,
			"unit":   msg.Unit,
		},
	}
	c.eventBus.Publish(event)

	// Forward to HSIL for continuous ML learning
	location := "unknown"
	deviceType := "sensor"
	if device != nil {
		if device.ZoneID != "" {
			location = device.ZoneID
		}
		if device.Type != "" {
			deviceType = device.Type
		}
	}
	c.forwardToHSIL(deviceID, event.SensorID, attrName, msg.Value, location, deviceType)
}

// handleRemoved processes device removal messages
func (c *Consumer) handleRemoved(deviceID string, payload []byte) {
	var msg RemovedMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse removed message: %v", err)
		return
	}

	log.Printf("[MQTT-CONSUMER] Device removed: %s (reason: %s)", deviceID, msg.Reason)

	// Mark device as disabled
	device, err := c.deviceRepo.Get(c.ctx, deviceID)
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to get device for removal: %v", err)
		return
	}
	if device == nil {
		return
	}

	device.Enabled = false
	device.UpdatedAt = time.Now()
	if device.Metadata == nil {
		device.Metadata = make(map[string]string)
	}
	device.Metadata["removal_reason"] = msg.Reason

	if err := c.deviceRepo.Upsert(c.ctx, device); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to mark device as removed: %v", err)
	}
}

// handleIncidentMessage processes incident messages
func (c *Consumer) handleIncidentMessage(parts []string, payload []byte) {
	var msg IncidentMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse incident message: %v", err)
		return
	}

	log.Printf("[MQTT-CONSUMER] Incident: %s - %s (%s)", msg.DeviceID, msg.Title, msg.Severity)

	// Convert severity string to model.IncidentSeverity
	severity := model.SeverityInfo
	switch msg.Severity {
	case "critical":
		severity = model.SeverityCritical
	case "high":
		severity = model.SeverityHigh
	case "medium":
		severity = model.SeverityMedium
	case "low":
		severity = model.SeverityLow
	}

	// Get device info for zone/asset context
	device, _ := c.deviceRepo.Get(c.ctx, msg.DeviceID)

	incident := &model.Incident{
		ID:          msg.IncidentID,
		Title:       msg.Title,
		Description: msg.Description,
		Severity:    severity,
		Status:      model.StatusOpen,
		DeviceID:    msg.DeviceID,
		SensorID:    msg.DeviceID,
		RuleName:    "mqtt_incident",
		Data:        msg.Data,
		CreatedAt:   msg.Timestamp,
		UpdatedAt:   msg.Timestamp,
	}

	if device != nil {
		incident.ZoneID = device.ZoneID
		incident.AssetID = device.AssetID
	}

	if msg.IncidentType != "" {
		if incident.Data == nil {
			incident.Data = make(map[string]any)
		}
		incident.Data["incident_type"] = msg.IncidentType
	}

	if err := c.incidentSvc.CreateOrUpdate(c.ctx, incident); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to create incident: %v", err)
	}
}

// inferDeviceType infers device type from capabilities
func inferDeviceType(capabilities []string) string {
	for _, cap := range capabilities {
		switch cap {
		case "leak":
			return "leak_sensor"
		case "smoke":
			return "smoke_detector"
		case "co":
			return "co_detector"
		case "motion":
			return "motion_sensor"
		case "contact":
			return "contact_sensor"
		case "thermostat":
			return "thermostat"
		case "lock":
			return "lock"
		case "switch":
			return "switch"
		case "dimmer":
			return "dimmer"
		case "temperature":
			return "temp_sensor"
		}
	}
	return "sensor"
}
