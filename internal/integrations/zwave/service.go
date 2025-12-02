package zwave

import (
	"context"
	"fmt"
	"log"
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
			device.Alias = existingDevice.Alias
			device.CreatedAt = existingDevice.CreatedAt
			device.DocsIngested = existingDevice.DocsIngested
			device.DocsIngestedAt = existingDevice.DocsIngestedAt
			device.DocsStatus = existingDevice.DocsStatus
			// Preserve existing metadata entries
			if existingDevice.Metadata != nil {
				for k, v := range existingDevice.Metadata {
					if _, exists := device.Metadata[k]; !exists {
						device.Metadata[k] = v
					}
				}
			}
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
			"manufacturer": device.Metadata["manufacturer"],
			"model":        device.Metadata["model"],
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

	// Update metadata with property value
	if device.Metadata == nil {
		device.Metadata = make(map[string]string)
	}

	// Store as string in metadata
	device.Metadata[fmt.Sprintf("value_%s", property)] = fmt.Sprintf("%v", value)
	if propertyName != "" {
		device.Metadata[fmt.Sprintf("name_%s", property)] = propertyName
	}

	// Special handling for battery level (CC_BATTERY = 0x80 = 128)
	if commandClass == CC_BATTERY && property == "level" {
		if floatVal, ok := value.(float64); ok {
			device.Metadata["battery_level"] = fmt.Sprintf("%d", int(floatVal))
			if floatVal < 20 {
				device.Metadata["battery_low"] = "true"
			} else {
				delete(device.Metadata, "battery_low")
			}
			log.Printf("[ZWAVE] Updated battery level for device %s: %d%%", deviceID, int(floatVal))
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
	// Low battery detection
	if commandClass == CC_BATTERY && property == "level" {
		if level, ok := value.(float64); ok && level < 20 {
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
		title = fmt.Sprintf("Power Event: %s", eventLabel)
		severity = model.SeverityMedium

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
