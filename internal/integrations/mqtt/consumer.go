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
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/homesight/homesight/internal/alarms"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/events"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/model"
)

// WeatherCache holds cached outdoor temperature data
type WeatherCache struct {
	Temperature float64
	UpdatedAt   time.Time
}

// Consumer processes MQTT messages from integrations and updates the device registry
type Consumer struct {
	ctx            context.Context
	cancel         context.CancelFunc
	client         mqtt.Client
	deviceRepo     db.DeviceRepository
	readingRepo    db.SensorReadingRepository
	eventBus       events.EventBus
	incidentSvc    incidents.IncidentService
	alarmManager   *alarms.Manager
	weatherCache   *WeatherCache
	weatherCacheMu sync.RWMutex
}

// NewConsumer creates a new MQTT consumer
func NewConsumer(
	brokerURL string,
	clientID string,
	deviceRepo db.DeviceRepository,
	readingRepo db.SensorReadingRepository,
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
		readingRepo:  readingRepo,
		eventBus:     eventBus,
		incidentSvc:  incidentSvc,
		alarmManager: alarms.NewManager(incidentSvc),
		weatherCache: &WeatherCache{},
	}

	// Start background weather fetcher
	go c.fetchWeatherPeriodically()

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
		"homesight/+/+/discovery":    0,
		"homesight/+/+/metadata":     0,
		"homesight/+/+/state":        0,
		"homesight/+/+/removed":      0,
		"homesight/incidents/#":      0,
		"homesight/entity/updated/#": 0, // Entity value updates
		"homesight/entity/result/#":  0, // Entity set command results
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

	// Handle entity messages (homesight/entity/<type>/<deviceId>)
	if parts[1] == "entity" {
		if len(parts) < 4 {
			log.Printf("[MQTT-CONSUMER] Invalid entity topic format: %s", topic)
			return
		}
		entityMsgType := parts[2] // "updated" or "result"
		deviceID := parts[3]
		c.handleEntityMessage(entityMsgType, deviceID, payload)
		return
	}

	integration := parts[1]
	nodeOrDeviceID := parts[2] // Could be just nodeID (e.g., "42") or full deviceID (e.g., "zwave-42")
	messageType := parts[3]

	// Construct full device ID if needed (some integrations use just nodeID in topics)
	deviceID := nodeOrDeviceID
	if integration == "zwave" {
		// Z-Wave topics use node ID, so construct full device ID
		deviceID = fmt.Sprintf("zwave-%s", nodeOrDeviceID)
	}

	// Debug logging for state messages
	if messageType == "state" {
		log.Printf("[MQTT-CONSUMER] State message received: topic=%s, deviceID=%s, integration=%s", topic, deviceID, integration)
	}

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
	existingDevice, err := c.deviceRepo.Get(c.ctx, msg.DeviceID)
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Error fetching existing device %s: %v", msg.DeviceID, err)
	}

	if existingDevice != nil {
		log.Printf("[MQTT-CONSUMER] Found existing device %s: alias=%q, zone=%s", msg.DeviceID, existingDevice.Alias, existingDevice.ZoneID)
	} else {
		log.Printf("[MQTT-CONSUMER] No existing device found for %s (creating new)", msg.DeviceID)
	}

	// Convert to model.Device
	device := &model.Device{
		ID:           msg.DeviceID,
		Name:         msg.Name,
		Type:         inferDeviceType(msg.Capabilities),
		Integration:  msg.Integration,
		Manufacturer: msg.Manufacturer,
		Model:        msg.Model,
		Enabled:      true,
		LastSeen:     time.Now(),
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
		// Unified contract fields from discovery (e.g., Z-Wave mapper)
		Readings:     msg.Readings,
		Controls:     msg.Controls,
		Battery:      msg.Battery,
		Connectivity: msg.Connectivity,
		Entities:     msg.Entities, // Entity-based model
	}

	// Store raw MQTT discovery data
	if device.RawData == nil {
		device.RawData = make(map[string]interface{})
	}
	if msg.HwID != "" {
		device.RawData["hw_id"] = msg.HwID
	}
	if len(msg.Capabilities) > 0 {
		device.RawData["capabilities"] = msg.Capabilities
	}

	// Preserve existing device state (zone_id, asset_id, unified contract fields, docs status, etc.)
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
		// Preserve unified contract fields ONLY if they have data
		// Don't preserve null values - let integrations provide fresh data
		if existingDevice.Readings != nil {
			device.Readings = existingDevice.Readings
		}
		if existingDevice.Controls != nil {
			device.Controls = existingDevice.Controls
		}
		if existingDevice.Battery != nil {
			device.Battery = existingDevice.Battery
		}
		if existingDevice.Connectivity != nil {
			device.Connectivity = existingDevice.Connectivity
		}
		// Preserve raw data from other integrations
		if existingDevice.RawData != nil {
			for k, v := range existingDevice.RawData {
				// Don't overwrite new values
				if _, exists := device.RawData[k]; !exists {
					device.RawData[k] = v
				}
			}
		}
		log.Printf("[MQTT-CONSUMER] After preservation: alias=%q, zone=%s", device.Alias, device.ZoneID)
	}

	if device.Name == "" {
		device.Name = msg.DeviceID
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

	// Store any metadata in RawData for backward compatibility with MQTT messages
	if msg.Metadata != nil {
		if device.RawData == nil {
			device.RawData = make(map[string]interface{})
		}
		for k, v := range msg.Metadata {
			device.RawData[k] = v
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
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to get device %s for state update: %v", deviceID, err)
		return
	}
	if device == nil {
		log.Printf("[MQTT-CONSUMER] Device %s not found for state update", deviceID)
		return
	}
	if err == nil && device != nil {
		device.LastSeen = time.Now()
		device.UpdatedAt = time.Now()

		// Store state values in RawData
		if device.RawData == nil {
			device.RawData = make(map[string]interface{})
		}
		for k, v := range msg.Values {
			device.RawData[fmt.Sprintf("state_%s", k)] = v
		}

		// Update unified Controls based on state changes
		for k, v := range msg.Values {
			normalizedKey := strings.ToLower(k)
			log.Printf("[MQTT-CONSUMER] Processing state key for %s: %s (normalized: %s) = %v (type: %T)", deviceID, k, normalizedKey, v, v)

			// Switch control updates (binary switch)
			if normalizedKey == "switch_state" || normalizedKey == "currentvalue" || normalizedKey == "targetvalue" {
				if boolVal, ok := v.(bool); ok {
					if device.Controls == nil {
						device.Controls = &model.DeviceControls{}
					}
					if device.Controls.Switch == nil {
						device.Controls.Switch = &model.SwitchControl{Settable: true}
					}
					device.Controls.Switch.Value = boolVal
					log.Printf("[MQTT-CONSUMER] ✓ Updated switch control for %s: %v", deviceID, boolVal)
				} else {
					log.Printf("[MQTT-CONSUMER] ✗ Could not convert %s value %v to bool (type: %T)", k, v, v)
				}
			}

			// Level control updates (dimmer/multilevel switch)
			if normalizedKey == "level" {
				if floatVal, ok := v.(float64); ok {
					if device.Controls == nil {
						device.Controls = &model.DeviceControls{}
					}
					if device.Controls.Level == nil {
						device.Controls.Level = &model.LevelControl{Settable: true, Min: 0, Max: 100}
					}
					device.Controls.Level.Value = int(floatVal)
					log.Printf("[MQTT-CONSUMER] Updated level control for %s: %d", deviceID, int(floatVal))
				}
			}
		}

		c.deviceRepo.Upsert(c.ctx, device)
	}

	// Publish device events for each value
	for key, value := range msg.Values {
		valueType := "string"
		var floatValue float64
		switch v := value.(type) {
		case float64:
			valueType = "float"
			floatValue = v
		case float32:
			valueType = "float"
			floatValue = float64(v)
		case int:
			valueType = "float"
			floatValue = float64(v)
			value = floatValue
		case int32:
			valueType = "float"
			floatValue = float64(v)
			value = floatValue
		case int64:
			valueType = "float"
			floatValue = float64(v)
			value = floatValue
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

		// Persist temperature and humidity readings to database for thermal analysis
		if valueType == "float" {
			normalizedKey := strings.ToLower(key)
			// Store temperature_f directly (integrations should send standardized Fahrenheit)
			if strings.Contains(normalizedKey, "temperature") {
				c.persistSensorReading(deviceID, "temperature", floatValue)
			} else if strings.Contains(normalizedKey, "humidity") {
				c.persistSensorReading(deviceID, "humidity", floatValue)
			}
		}

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

	// Update device raw data
	device, err := c.deviceRepo.Get(c.ctx, deviceID)
	if err == nil && device != nil {
		if device.RawData == nil {
			device.RawData = make(map[string]interface{})
		}
		device.RawData[fmt.Sprintf("attr_%s", attrName)] = msg.Value
		device.LastSeen = time.Now()
		device.UpdatedAt = time.Now()
		c.deviceRepo.Upsert(c.ctx, device)
	}

	// Publish event
	valueType := "string"
	var floatValue float64
	switch v := msg.Value.(type) {
	case float64:
		valueType = "float"
		floatValue = v
	case float32:
		valueType = "float"
		floatValue = float64(v)
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

	// Persist temperature and humidity readings to database for thermal analysis
	if valueType == "float" {
		normalizedAttr := strings.ToLower(attrName)
		if strings.Contains(normalizedAttr, "temperature") || normalizedAttr == "air temperature" {
			// Store raw sensor value - conversion to user preference happens at query time
			c.persistSensorReading(deviceID, "temperature", floatValue)
		} else if strings.Contains(normalizedAttr, "humidity") {
			c.persistSensorReading(deviceID, "humidity", floatValue)
		}
	}

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
// handleEntityMessage processes entity update and result messages
func (c *Consumer) handleEntityMessage(msgType string, deviceID string, payload []byte) {
	var msg map[string]interface{}
	if err := json.Unmarshal(payload, &msg); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to parse entity message: %v", err)
		return
	}

	entityID, _ := msg["entity_id"].(string)
	value := msg["value"]
	timestamp, _ := msg["ts"].(string)

	log.Printf("[MQTT-CONSUMER] Entity %s: deviceID=%s entityID=%s value=%v", msgType, deviceID, entityID, value)

	// Create event for SSE
	event := model.DeviceEvent{
		DeviceID:  deviceID,
		SensorID:  entityID,
		Timestamp: time.Now(),
		ValueType: msgType, // "updated" or "result"
		Value:     value,
		Metadata: map[string]string{
			"entity_id": entityID,
			"timestamp": timestamp,
		},
	}

	// Add success/error info for result messages
	if msgType == "result" {
		if success, ok := msg["success"].(bool); ok {
			if success {
				event.Metadata["status"] = "success"
			} else {
				event.Metadata["status"] = "failed"
			}
		}
		if errorMsg, ok := msg["error"].(string); ok {
			event.Metadata["error"] = errorMsg
		}
	}

	// Publish to SSE event bus
	c.eventBus.Publish(event)
}

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
	if device.RawData == nil {
		device.RawData = make(map[string]interface{})
	}
	device.RawData["removal_reason"] = msg.Reason

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

	// Skip battery incidents for AC-powered devices with backup batteries
	if msg.IncidentType == "battery" && device != nil && device.Entities != nil {
		for _, entity := range device.Entities {
			if entity.Name == "backup" {
				if backup, ok := entity.Value.(bool); ok && backup {
					log.Printf("[MQTT-CONSUMER] Skipping battery incident for %s - device uses backup battery (AC-powered)", msg.DeviceID)
					return
				}
			}
		}
	}

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

// fetchWeatherPeriodically fetches outdoor temperature every 5 minutes
func (c *Consumer) fetchWeatherPeriodically() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	// Fetch immediately on startup
	c.updateWeatherCache()

	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			c.updateWeatherCache()
		}
	}
}

// updateWeatherCache fetches current weather from AI sidecar
func (c *Consumer) updateWeatherCache() {
	aiURL := os.Getenv("AI_SERVICE_URL")
	if aiURL == "" {
		aiURL = "http://ai-sidecar:8001"
	}

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(aiURL + "/weather")
	if err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to fetch weather: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return
	}

	var weather struct {
		Temperature float64 `json:"temperature"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&weather); err != nil {
		return
	}

	c.weatherCacheMu.Lock()
	c.weatherCache.Temperature = weather.Temperature
	c.weatherCache.UpdatedAt = time.Now()
	c.weatherCacheMu.Unlock()
}

// getOutdoorTemp returns the cached outdoor temperature
func (c *Consumer) getOutdoorTemp() *float64 {
	c.weatherCacheMu.RLock()
	defer c.weatherCacheMu.RUnlock()

	// Return nil if cache is stale (> 15 minutes old)
	if time.Since(c.weatherCache.UpdatedAt) > 15*time.Minute {
		return nil
	}

	temp := c.weatherCache.Temperature
	return &temp
}

// persistSensorReading stores temperature/humidity readings in the database
func (c *Consumer) persistSensorReading(deviceID, readingType string, value float64) {
	if c.readingRepo == nil {
		return
	}

	outdoorTemp := c.getOutdoorTemp()

	if err := c.readingRepo.Insert(c.ctx, deviceID, readingType, value, outdoorTemp); err != nil {
		log.Printf("[MQTT-CONSUMER] Failed to persist sensor reading for %s/%s: %v", deviceID, readingType, err)
	}
}
