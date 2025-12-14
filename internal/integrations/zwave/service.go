package zwave

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/events"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/model"
)

// Service manages Z-Wave integration lifecycle
type Service struct {
	ctx         context.Context
	cancel      context.CancelFunc
	client      *Client
	deviceRepo  db.DeviceRepository
	eventBus    events.EventBus
	incidentSvc incidents.IncidentService
}

// NewService creates a new Z-Wave integration service
func NewService(
	wsURL string,
	deviceRepo db.DeviceRepository,
	eventBus events.EventBus,
	incidentSvc incidents.IncidentService,
) *Service {
	ctx, cancel := context.WithCancel(context.Background())

	return &Service{
		ctx:         ctx,
		cancel:      cancel,
		client:      NewClient(wsURL),
		deviceRepo:  deviceRepo,
		eventBus:    eventBus,
		incidentSvc: incidentSvc,
	}
}

// Start initializes the Z-Wave service
func (s *Service) Start() error {
	log.Println("[ZWAVE] Starting Z-Wave integration service...")

	// Setup event listeners before connecting
	s.SetupEventListeners()

	// Set connection callbacks
	s.client.SetOnConnect(func() {
		log.Println("[ZWAVE] Connected to Z-Wave JS Server")
		// Perform initial sync
		go s.initialSync()
	})

	s.client.SetOnDisconnect(func() {
		log.Println("[ZWAVE] Disconnected from Z-Wave JS Server")
	})

	// Connect to Z-Wave JS WebSocket server
	if err := s.client.Connect(); err != nil {
		return fmt.Errorf("failed to connect to Z-Wave JS: %w", err)
	}

	// Start periodic health check for battery devices
	go s.periodicHealthCheck()

	log.Println("[ZWAVE] Z-Wave integration service started")
	return nil
}

// Stop shuts down the Z-Wave service
func (s *Service) Stop() error {
	log.Println("[ZWAVE] Stopping Z-Wave integration service...")
	s.cancel()
	return s.client.Close()
}

// initialSync loads all existing Z-Wave nodes from the controller
func (s *Service) initialSync() {
	// Wait a bit for the WebSocket to stabilize
	time.Sleep(2 * time.Second)

	log.Println("[ZWAVE] Starting initial sync of Z-Wave nodes...")

	s.client.stateMu.RLock()
	nodes := make(map[int]*ZWaveNode)
	for k, v := range s.client.nodes {
		nodes[k] = v
	}
	homeID := s.client.homeID
	s.client.stateMu.RUnlock()

	if len(nodes) == 0 {
		log.Println("[ZWAVE] No nodes found during initial sync")
		return
	}

	log.Printf("[ZWAVE] Found %d existing nodes, syncing to database...", len(nodes))

	synced := 0
	for _, node := range nodes {
		if !node.Ready {
			log.Printf("[ZWAVE] Skipping node %d (not ready, interview stage %d)", node.NodeID, node.InterviewStage)
			continue
		}

		// Map node to device
		device := MapNodeToDevice(node, homeID)

		// Check if device already exists to preserve user settings
		deviceID := fmt.Sprintf("zwave-%d", node.NodeID)
		existingDevice, _ := s.deviceRepo.Get(s.ctx, deviceID)
		if existingDevice != nil {
			// Preserve user-defined settings
			device.ZoneID = existingDevice.ZoneID
			device.AssetID = existingDevice.AssetID
			device.DisplayName = existingDevice.DisplayName
			device.CreatedAt = existingDevice.CreatedAt
			device.DocsIngested = existingDevice.DocsIngested
			device.DocsIngestedAt = existingDevice.DocsIngestedAt
			device.DocsStatus = existingDevice.DocsStatus
		}

		// Set timestamps for initial discovery
		now := time.Now()
		device.LastSeen = now
		device.UpdatedAt = now
		if device.CreatedAt.IsZero() {
			device.CreatedAt = now
		}

		// Upsert to database
		if err := s.deviceRepo.Upsert(s.ctx, device); err != nil {
			log.Printf("[ZWAVE] Failed to sync node %d: %v", node.NodeID, err)
			continue
		}

		// Emit discovery event
		s.emitDiscovery(device, "initial_sync")

		synced++
		log.Printf("[ZWAVE] Synced node %d: %s (%s)", node.NodeID, device.Name, device.Type)
	}

	log.Printf("[ZWAVE] Initial sync complete: %d/%d nodes synced", synced, len(nodes))
}

// emitDiscovery broadcasts a device discovery event
func (s *Service) emitDiscovery(device *model.Device, source string) {
	// Publish device event for discovery
	event := model.DeviceEvent{
		DeviceID:  device.ID,
		SensorID:  device.ID,
		Timestamp: time.Now(),
		ValueType: "discovery",
		Value:     source,
		Metadata: map[string]string{
			"integration":  "zwave",
			"manufacturer": device.Manufacturer,
			"model":        device.Model,
			"type":         device.Type,
		},
	}

	s.eventBus.Publish(event)
	log.Printf("[ZWAVE] Discovery event emitted for device %s", device.ID)
}

// publishDeviceEvent publishes a device state change event
func (s *Service) publishDeviceEvent(deviceID string, property string, value interface{}) {
	valueType := "string"
	if _, ok := value.(float64); ok {
		valueType = "float"
	} else if _, ok := value.(bool); ok {
		valueType = "bool"
	} else if _, ok := value.(int); ok {
		valueType = "int"
	}

	event := model.DeviceEvent{
		DeviceID:  deviceID,
		SensorID:  fmt.Sprintf("%s_%s", deviceID, property),
		Timestamp: time.Now(),
		ValueType: valueType,
		Value:     value,
		Metadata: map[string]string{
			"integration": "zwave",
			"property":    property,
		},
	}

	s.eventBus.Publish(event)
}

// updateDeviceState updates device state in the database
func (s *Service) updateDeviceState(nodeID int, commandClass int, property string, value interface{}, propertyName string) {
	s.updateDeviceStateWithUnit(nodeID, commandClass, property, value, propertyName, "")
}

// updateDeviceStateWithUnit updates device state in the database including unit metadata
func (s *Service) updateDeviceStateWithUnit(nodeID int, commandClass int, property string, value interface{}, propertyName string, unit string) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	// Get device from database
	device, err := s.deviceRepo.Get(s.ctx, deviceID)
	if err != nil {
		log.Printf("[ZWAVE] Failed to get device %s for state update: %v", deviceID, err)
		return
	}

	if device == nil {
		return
	}

	// Update unified contract fields based on command class and property
	switch commandClass {
	case CC_BATTERY:
		if property == "level" {
			if floatVal, ok := value.(float64); ok {
				// Only update battery for battery-powered devices
				if device.RawData != nil {
					if isListening, ok := device.RawData["is_listening"].(bool); !ok || !isListening {
						// Only store non-zero battery levels (0% often means bad/missing data)
						if floatVal > 0 {
							if device.Battery == nil {
								device.Battery = &model.DeviceBattery{}
							}
							device.Battery.Level = int(floatVal)
							device.Battery.IsLow = floatVal <= 20
							log.Printf("[ZWAVE] Updated battery level for device %s: %d%%", deviceID, int(floatVal))
						}
					}
				}
			}
		}

	case CC_SENSOR_MULTILEVEL:
		// Initialize readings if needed
		if device.Readings == nil {
			device.Readings = &model.DeviceReadings{}
		}

		// Temperature sensor
		if strings.Contains(strings.ToLower(property), "temperature") {
			if floatVal, ok := value.(float64); ok {
				// Convert to Fahrenheit if needed based on unit
				tempF := floatVal
				if unit == "°C" || unit == "C" {
					tempF = (floatVal * 9 / 5) + 32
				}
				device.Readings.TemperatureF = &tempF
				log.Printf("[ZWAVE] Updated temperature for device %s: %.1f°F", deviceID, tempF)
			}
		}

		// Humidity sensor
		if strings.Contains(strings.ToLower(property), "humidity") {
			if floatVal, ok := value.(float64); ok {
				device.Readings.Humidity = &floatVal
				log.Printf("[ZWAVE] Updated humidity for device %s: %.1f%%", deviceID, floatVal)
			}
		}

		// Illuminance
		if strings.Contains(strings.ToLower(property), "illuminance") {
			if floatVal, ok := value.(float64); ok {
				device.Readings.Illuminance = &floatVal
			}
		}

		// Power
		if strings.Contains(strings.ToLower(property), "power") {
			if floatVal, ok := value.(float64); ok {
				device.Readings.PowerW = &floatVal
			}
		}

	case CC_NOTIFICATION:
		// Initialize readings if needed
		if device.Readings == nil {
			device.Readings = &model.DeviceReadings{}
		}

		// Water leak sensor
		if strings.Contains(strings.ToLower(property), "water") {
			boolVal := false
			switch v := value.(type) {
			case float64:
				boolVal = v > 0
			case bool:
				boolVal = v
			}
			device.Readings.Water = &boolVal
			log.Printf("[ZWAVE] Updated water sensor for device %s: %v", deviceID, boolVal)
		}

		// Motion sensor
		if strings.Contains(strings.ToLower(property), "motion") {
			boolVal := false
			switch v := value.(type) {
			case float64:
				boolVal = v > 0
			case bool:
				boolVal = v
			}
			device.Readings.Motion = &boolVal
		}

		// Tamper
		if strings.Contains(strings.ToLower(property), "tamper") {
			boolVal := false
			switch v := value.(type) {
			case float64:
				boolVal = v > 0
			case bool:
				boolVal = v
			}
			device.Readings.Tamper = &boolVal
		}

	case CC_SENSOR_BINARY:
		// Initialize readings if needed
		if device.Readings == nil {
			device.Readings = &model.DeviceReadings{}
		}

		if boolVal, ok := value.(bool); ok {
			// Contact sensor
			if strings.Contains(strings.ToLower(property), "contact") || strings.Contains(strings.ToLower(property), "door") {
				device.Readings.Contact = &boolVal
			}
			// Motion sensor
			if strings.Contains(strings.ToLower(property), "motion") {
				device.Readings.Motion = &boolVal
			}
		}

	case CC_SWITCH_BINARY:
		// Initialize controls if needed
		if device.Controls == nil {
			device.Controls = &model.DeviceControls{}
		}
		if device.Controls.Switch == nil {
			device.Controls.Switch = &model.SwitchControl{Settable: true}
		}

		if boolVal, ok := value.(bool); ok {
			device.Controls.Switch.Value = boolVal
			log.Printf("[ZWAVE] Updated switch state for device %s: %v", deviceID, boolVal)
		}

	case CC_SWITCH_MULTILEVEL:
		// Initialize controls if needed
		if device.Controls == nil {
			device.Controls = &model.DeviceControls{}
		}
		if device.Controls.Level == nil {
			device.Controls.Level = &model.LevelControl{Settable: true, Min: 0, Max: 100}
		}

		if floatVal, ok := value.(float64); ok {
			device.Controls.Level.Value = int(floatVal)
			log.Printf("[ZWAVE] Updated level for device %s: %d", deviceID, int(floatVal))
		}
	}

	// Update timestamps - this marks the device as "online" in the UI
	now := time.Now()
	device.UpdatedAt = now
	device.LastSeen = now

	// Save to database
	if err := s.deviceRepo.Upsert(s.ctx, device); err != nil {
		log.Printf("[ZWAVE] Failed to update device state: %v", err)
	}
}

// checkIncident evaluates if a value update should trigger an incident
func (s *Service) checkIncident(nodeID int, commandClass int, property string, value interface{}, args map[string]interface{}) {
	// Low battery detection - only for battery-powered devices
	if commandClass == CC_BATTERY && property == "level" {
		deviceID := fmt.Sprintf("zwave-%d", nodeID)
		device, _ := s.deviceRepo.Get(s.ctx, deviceID)

		// Skip battery incidents for AC-powered devices with backup batteries
		if device != nil && device.Entities != nil {
			if s.isACPoweredDevice(device.Entities) {
				log.Printf("[ZWAVE-SERVICE] Skipping battery incident for %s - device is AC-powered with backup battery", deviceID)
				return
			}
		}

		if level, ok := value.(float64); ok && level <= 20 && level > 0 {
			s.createIncident(nodeID, "Low Battery", fmt.Sprintf("Battery level is %d%%", int(level)), model.SeverityLow, map[string]any{
				"battery_level": level,
			})
		}
	}

	// Binary sensor changes (contact, motion, etc.)
	if commandClass == CC_SENSOR_BINARY {
		if boolVal, ok := value.(bool); ok && boolVal {
			s.createIncident(nodeID, "Sensor Triggered", fmt.Sprintf("Binary sensor %s activated", property), model.SeverityInfo, map[string]any{
				"sensor": property,
			})
		}
	}
}

// createIncidentFromNotification maps Z-Wave notifications to incidents
func (s *Service) createIncidentFromNotification(nodeID int, notifType int, notifEvent int, label string, eventLabel string) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	var title string
	var severity model.IncidentSeverity
	incidentType := "notification"

	// Map notification types to incidents
	switch notifType {
	case NOTIFICATION_WATER:
		switch notifEvent {
		case WATER_LEAK_DETECTED, WATER_LEAK_DETECTED_UNKNOWN:
			title = "Water Leak Detected"
			severity = model.SeverityCritical
			incidentType = "leak"
		case WATER_EVENT_CLEARED:
			// Resolve existing leak incidents
			s.resolveIncidentsOfType(deviceID, "leak")
			return
		default:
			title = fmt.Sprintf("Water Alarm: %s", eventLabel)
			severity = model.SeverityHigh
		}

	case NOTIFICATION_SMOKE:
		title = "Smoke Detected"
		severity = model.SeverityCritical
		incidentType = "smoke"

	case NOTIFICATION_CO:
		title = "Carbon Monoxide Detected"
		severity = model.SeverityCritical
		incidentType = "co"

	case NOTIFICATION_BURGLAR:
		switch notifEvent {
		case 3: // Tamper
			title = "Tamper Detected"
			severity = model.SeverityHigh
			incidentType = "tamper"
		case 8: // Motion
			title = "Motion Detected"
			severity = model.SeverityInfo
			incidentType = "motion"
		default:
			title = fmt.Sprintf("Intrusion: %s", eventLabel)
			severity = model.SeverityHigh
			incidentType = "intrusion"
		}

	case NOTIFICATION_POWER:
		switch notifEvent {
		case 10, 11: // Replace battery soon (10), Replace battery now (11)
			title = "Low Battery Warning"
			severity = model.SeverityMedium
			incidentType = "low_battery"
		case 14: // Charge battery soon
			title = "Low Battery Warning"
			severity = model.SeverityLow
			incidentType = "low_battery"
		default:
			title = fmt.Sprintf("Power Event: %s", eventLabel)
			severity = model.SeverityMedium
			incidentType = "power"
		}

	default:
		title = fmt.Sprintf("%s: %s", label, eventLabel)
		severity = model.SeverityInfo
	}

	s.createIncident(nodeID, title, eventLabel, severity, map[string]any{
		"notification_type":  notifType,
		"notification_event": notifEvent,
		"incident_type":      incidentType,
	})
}

// createIncident creates a new incident
func (s *Service) createIncident(nodeID int, title string, description string, severity model.IncidentSeverity, data map[string]any) {
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	// Get device info for context
	device, err := s.deviceRepo.Get(s.ctx, deviceID)
	if err != nil {
		log.Printf("[ZWAVE] Failed to get device for incident: %v", err)
		return
	}

	if device == nil {
		return
	}

	incident := &model.Incident{
		ID:          fmt.Sprintf("zwave-%d-%d", nodeID, time.Now().Unix()),
		Title:       title,
		Description: description,
		Severity:    severity,
		Status:      model.StatusOpen,
		DeviceID:    deviceID,
		SensorID:    deviceID,
		ZoneID:      device.ZoneID,
		AssetID:     device.AssetID,
		RuleName:    "zwave_notification",
		Data:        data,
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}

	if err := s.incidentSvc.CreateOrUpdate(s.ctx, incident); err != nil {
		log.Printf("[ZWAVE] Failed to create incident: %v", err)
		return
	}

	log.Printf("[ZWAVE] Incident created: %s - %s (severity: %s)", deviceID, title, severity)
}

// resolveIncidentsOfType resolves all open incidents of a specific type for a device
func (s *Service) resolveIncidentsOfType(deviceID string, incidentType string) {
	// List open incidents for this device
	incidents, err := s.incidentSvc.List(s.ctx, map[string]any{
		"device_id": deviceID,
		"status":    model.StatusOpen,
	})
	if err != nil {
		log.Printf("[ZWAVE] Failed to list incidents: %v", err)
		return
	}

	for _, incident := range incidents {
		// Check if incident matches the type
		if incidentData, ok := incident.Data["incident_type"].(string); ok && incidentData == incidentType {
			if err := s.incidentSvc.Resolve(s.ctx, incident.ID); err != nil {
				log.Printf("[ZWAVE] Failed to resolve incident %s: %v", incident.ID, err)
			} else {
				log.Printf("[ZWAVE] Resolved incident: %s", incident.ID)
			}
		}
	}
}

// periodicHealthCheck runs a periodic check for stale battery devices
func (s *Service) periodicHealthCheck() {
	ticker := time.NewTicker(30 * time.Minute)
	defer ticker.Stop()

	// Run initial check after 5 minutes
	time.Sleep(5 * time.Minute)
	s.checkStaleDevices()

	for {
		select {
		case <-s.ctx.Done():
			return
		case <-ticker.C:
			s.checkStaleDevices()
		}
	}
}

// checkStaleDevices identifies battery-powered devices that haven't reported recently
func (s *Service) checkStaleDevices() {
	// Get all devices
	devices, err := s.deviceRepo.List(s.ctx)
	if err != nil {
		log.Printf("[ZWAVE-HEALTH] Failed to list devices: %v", err)
		return
	}

	staleCutoff := time.Now().Add(-48 * time.Hour)
	staleCount := 0

	for _, device := range devices {
		// Only check Z-Wave devices
		if device.Integration != "zwave" {
			continue
		}

		// Only check battery-powered devices (skip AC-powered devices with backup batteries)
		if device.Entities != nil && s.isACPoweredDevice(device.Entities) {
			continue
		}

		// Also skip if no battery entity present
		if device.Battery == nil {
			continue
		}

		// Check if device is stale (no updates in 48 hours)
		if device.LastSeen.Before(staleCutoff) && device.Enabled {
			staleHours := int(time.Since(device.LastSeen).Hours())
			log.Printf("[ZWAVE-HEALTH] Stale device detected: %s (last seen %d hours ago)", device.ID, staleHours)

			// Create incident for stale device
			s.createIncident(
				extractNodeID(device.ID),
				"Device Not Reporting",
				fmt.Sprintf("Battery device has not reported in %d hours (possible dead battery)", staleHours),
				model.SeverityMedium,
				map[string]any{
					"hours_since_last_seen": staleHours,
					"incident_type":         "stale_device",
				},
			)

			// Mark device as disabled to prevent repeated incidents
			deviceCopy := device
			deviceCopy.Enabled = false
			if err := s.deviceRepo.Upsert(s.ctx, &deviceCopy); err != nil {
				log.Printf("[ZWAVE-HEALTH] Failed to disable stale device %s: %v", device.ID, err)
			}

			staleCount++
		}
	}

	if staleCount > 0 {
		log.Printf("[ZWAVE-HEALTH] Health check complete: %d stale devices found", staleCount)
	}
}

// extractNodeID extracts the numeric node ID from a device ID like "zwave-47"
func extractNodeID(deviceID string) int {
	var nodeID int
	fmt.Sscanf(deviceID, "zwave-%d", &nodeID)
	return nodeID
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
func (s *Service) isACPoweredDevice(entities []model.DeviceEntity) bool {
	const wakeUpIntervalThreshold = 3600 // 1 hour in seconds
	const CC_WAKE_UP = 132
	const CC_BATTERY = 128
	hasWakeUpEntity := false

	for _, entity := range entities {
		cc, ok := entity.Metadata["command_class"].(float64)
		if !ok {
			continue
		}

		propName := ""
		if name, ok := entity.Metadata["property"].(string); ok {
			propName = name
		} else {
			propName = entity.Name
		}

		// Normalize to lowercase for comparison
		propNameLower := ""
		for _, r := range propName {
			if r >= 'A' && r <= 'Z' {
				propNameLower += string(r + 32)
			} else {
				propNameLower += string(r)
			}
		}

		// Check for Wake Up command class (132)
		if int(cc) == CC_WAKE_UP {
			hasWakeUpEntity = true

			// Check if wake up interval is high (AC-powered)
			if propNameLower == "wakeupinterval" {
				if interval, ok := entity.Value.(float64); ok {
					if interval >= wakeUpIntervalThreshold {
						log.Printf("[ZWAVE-SERVICE] Detected AC power via Wake Up interval: %.0fs (>= %ds threshold)", interval, wakeUpIntervalThreshold)
						return true
					}
				}
			}
		}

		// Check for explicit backup battery indicator
		if propNameLower == "backup" {
			if backup, ok := entity.Value.(bool); ok && backup {
				log.Printf("[ZWAVE-SERVICE] Detected AC power via backup battery flag")
				return true
			}
		}

		// Check for battery disconnected (indicating optional backup)
		if (propNameLower == "disconnected" || propNameLower == "battery disconnected") && int(cc) == CC_BATTERY {
			if disconnected, ok := entity.Value.(bool); ok && disconnected {
				log.Printf("[ZWAVE-SERVICE] Detected AC power via battery disconnected flag")
				return true
			}
		}
	}

	// If device has battery but NO Wake Up entity, it's always-listening (AC-powered)
	// Battery-powered devices ALWAYS have Wake Up to conserve power
	if !hasWakeUpEntity {
		log.Printf("[ZWAVE-SERVICE] Detected AC power: No Wake Up entity (always-listening device)")
		return true
	}

	return false
}
