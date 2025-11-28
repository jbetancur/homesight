package api

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/homesight/homesight/internal/integrations/zwave"
	"github.com/homesight/homesight/internal/model"
)

// initZWave initializes the Z-Wave integration
func (s *Server) initZWave() {
	log.Printf("[ZWAVE] Initializing Z-Wave integration...")

	wsURL := s.cfg.ZWave.WebSocketURL
	if wsURL == "" {
		wsURL = "ws://localhost:3000"
	}

	s.zwaveClient = zwave.NewClient(wsURL)

	// Register event handlers
	s.zwaveClient.On(zwave.EventDriverReady, s.handleZWaveDriverReady)
	s.zwaveClient.On(zwave.EventNodeAdded, s.handleZWaveNodeAdded)
	s.zwaveClient.On(zwave.EventNodeReady, s.handleZWaveNodeReady)
	s.zwaveClient.On(zwave.EventValueUpdated, s.handleZWaveValueUpdated)
	s.zwaveClient.On(zwave.EventNotification, s.handleZWaveNotification)
	s.zwaveClient.On(zwave.EventNodeDead, s.handleZWaveNodeDead)
	s.zwaveClient.On(zwave.EventNodeAlive, s.handleZWaveNodeAlive)
	s.zwaveClient.On(zwave.EventInclusionStarted, s.handleZWaveInclusionStarted)
	s.zwaveClient.On(zwave.EventInclusionFailed, s.handleZWaveInclusionFailed)
	s.zwaveClient.On(zwave.EventInclusionStopped, s.handleZWaveInclusionStopped)

	// Set connection callbacks
	s.zwaveClient.SetOnConnect(func() {
		log.Printf("[ZWAVE] Connected to Z-Wave JS")
		// Sync existing nodes on connect
		s.syncZWaveNodes()
	})

	s.zwaveClient.SetOnDisconnect(func() {
		log.Printf("[ZWAVE] Disconnected from Z-Wave JS")
	})

	// Connect asynchronously
	go func() {
		if err := s.zwaveClient.Connect(); err != nil {
			log.Printf("[ZWAVE] Failed to connect: %v", err)
		}
	}()
}

// handleZWaveDriverReady handles Z-Wave driver ready event
func (s *Server) handleZWaveDriverReady(event zwave.Event) {
	log.Printf("[ZWAVE] Driver ready: %+v", event.Data)

	// Extract home ID
	if homeID, ok := event.Data["homeId"].(float64); ok {
		s.zwaveMutex.Lock()
		s.zwaveHomeID = int(homeID)
		s.zwaveMutex.Unlock()
		log.Printf("[ZWAVE] Home ID: 0x%08x", s.zwaveHomeID)
	}

	// Sync existing nodes
	s.syncZWaveNodes()
}

// syncZWaveNodes synchronizes all Z-Wave nodes into device registry
func (s *Server) syncZWaveNodes() {
	nodes, err := s.zwaveClient.GetNodes()
	if err != nil {
		log.Printf("[ZWAVE] Failed to get nodes: %v", err)
		return
	}

	log.Printf("[ZWAVE] Syncing %d nodes...", len(nodes))

	for _, node := range nodes {
		if node.NodeID == 1 {
			// Skip controller node
			continue
		}

		if !node.Ready {
			// Skip nodes that aren't ready yet
			continue
		}

		s.syncZWaveNode(&node)
	}
}

// syncZWaveNode synchronizes a single Z-Wave node
func (s *Server) syncZWaveNode(node *zwave.ZWaveNode) {
	s.zwaveMutex.RLock()
	homeID := s.zwaveHomeID
	s.zwaveMutex.RUnlock()

	device := zwave.MapNodeToDevice(node, uint32(homeID))

	// Check if device already exists
	existing, err := s.deviceRepo.Get(context.Background(), device.ID)
	if err == nil && existing != nil {
		// Update existing device metadata
		device.Name = existing.Name // Preserve user's custom name
		device.ZoneID = existing.ZoneID
		device.AssetID = existing.AssetID
		device.CreatedAt = existing.CreatedAt
	}

	device.LastSeen = time.Now()
	device.UpdatedAt = time.Now()

	// Upsert device
	if err := s.deviceRepo.Upsert(context.Background(), device); err != nil {
		log.Printf("[ZWAVE] Failed to sync node %d: %v", node.NodeID, err)
		return
	}

	log.Printf("[ZWAVE] Synced device: %s (node %d)", device.Name, node.NodeID)
}

// handleZWaveNodeAdded handles new node being added
func (s *Server) handleZWaveNodeAdded(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	log.Printf("[ZWAVE] Node %d added, waiting for interview...", int(nodeID))

	// Publish event for UI
	s.eventBus.Publish(Event{
		Type: "zwave.node_added",
		Data: map[string]interface{}{
			"node_id": int(nodeID),
			"status":  "interviewing",
		},
	})
}

// handleZWaveNodeReady handles node interview complete
func (s *Server) handleZWaveNodeReady(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	log.Printf("[ZWAVE] Node %d ready", int(nodeID))

	// Get full node info
	node, err := s.zwaveClient.GetNode(int(nodeID))
	if err != nil {
		log.Printf("[ZWAVE] Failed to get node %d: %v", int(nodeID), err)
		return
	}

	// Create HomeSight device
	s.zwaveMutex.RLock()
	homeID := s.zwaveHomeID
	s.zwaveMutex.RUnlock()

	device := zwave.MapNodeToDevice(node, uint32(homeID))
	device.LastSeen = time.Now()
	device.CreatedAt = time.Now()
	device.UpdatedAt = time.Now()

	// Save to database
	if err := s.deviceRepo.Upsert(context.Background(), device); err != nil {
		log.Printf("[ZWAVE] Failed to create device: %v", err)
		return
	}

	// Emit device added event
	s.eventBus.Publish(Event{
		Type: DeviceAdded,
		Data: device,
	})

	// Notify AI sidecar about new device
	go s.notifyAIDeviceCreated(*device)

	log.Printf("[ZWAVE] Device onboarded: %s (ID: %s)", device.Name, device.ID)
}

// handleZWaveValueUpdated handles value change events
func (s *Server) handleZWaveValueUpdated(event zwave.Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	commandClass := int(args["commandClass"].(float64))
	property, _ := args["property"].(string)
	newValue := args["newValue"]

	// Use new device ID format (matches service.go)
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	// Get device
	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		// Device not found, skip update
		return
	}

	// Update device metadata based on value change
	updated := false

	switch commandClass {
	case zwave.CC_BATTERY:
		if property == "level" {
			if level, ok := newValue.(float64); ok {
				device.Metadata["battery_level"] = fmt.Sprintf("%d", int(level))
				device.Metadata["battery_low"] = fmt.Sprintf("%t", level < 20)
				updated = true

				// Create low battery incident if needed
				if level < 20 {
					s.createZWaveIncident(device, "low_battery", "warning",
						fmt.Sprintf("Battery low: %d%%", int(level)))
				}
			}
		}

	case zwave.CC_SENSOR_BINARY:
		// Binary sensor state change
		if state, ok := newValue.(bool); ok {
			log.Printf("[ZWAVE] Binary sensor %s: %v", device.Name, state)
		}

	case zwave.CC_SENSOR_MULTILEVEL:
		// Multilevel sensor (temperature, humidity, etc.)
		log.Printf("[ZWAVE] Sensor %s value: %v", device.Name, newValue)
	}

	if updated {
		device.LastSeen = time.Now()
		device.UpdatedAt = time.Now()
		s.deviceRepo.Upsert(context.Background(), device)

		// Publish device updated event
		s.eventBus.Publish(Event{
			Type: DeviceUpdated,
			Data: device,
		})
	}
}

// handleZWaveNotification handles Z-Wave notification events (alarms)
func (s *Server) handleZWaveNotification(event zwave.Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	notificationType := int(args["type"].(float64))
	notificationEvent := int(args["event"].(float64))
	label, _ := args["label"].(string)
	eventLabel, _ := args["eventLabel"].(string)

	// Use new device ID format
	deviceID := fmt.Sprintf("zwave-%d", nodeID)

	// Get device
	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		log.Printf("[ZWAVE] Device not found for node %d", nodeID)
		return
	}

	log.Printf("[ZWAVE] Notification from %s: %s - %s", device.Name, label, eventLabel)

	// Handle specific notification types
	switch notificationType {
	case zwave.NOTIFICATION_WATER:
		s.handleWaterNotification(device, notificationEvent, eventLabel)

	case zwave.NOTIFICATION_SMOKE:
		if notificationEvent != 0 {
			s.createZWaveIncident(device, "smoke_detected", "critical", "Smoke detected!")
		} else {
			s.clearZWaveIncidents(deviceID, "smoke_detected")
		}

	case zwave.NOTIFICATION_CO:
		if notificationEvent != 0 {
			s.createZWaveIncident(device, "co_detected", "critical", "Carbon monoxide detected!")
		} else {
			s.clearZWaveIncidents(deviceID, "co_detected")
		}

	case zwave.NOTIFICATION_BURGLAR:
		if notificationEvent != 0 {
			s.createZWaveIncident(device, "motion_detected", "info",
				fmt.Sprintf("Motion detected: %s", eventLabel))
		}
	}
}

// handleWaterNotification handles water leak notifications
func (s *Server) handleWaterNotification(device *model.Device, eventCode int, eventLabel string) {
	switch eventCode {
	case zwave.WATER_LEAK_DETECTED, zwave.WATER_LEAK_DETECTED_UNKNOWN:
		// Leak detected - create critical incident
		s.createZWaveIncident(device, "water_leak", "critical",
			fmt.Sprintf("Water leak detected: %s", device.Name))

	case zwave.WATER_EVENT_CLEARED:
		// Leak cleared - close incident
		s.clearZWaveIncidents(device.ID, "water_leak")
	}
}

// handleZWaveNodeDead handles node offline events
func (s *Server) handleZWaveNodeDead(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	deviceID := fmt.Sprintf("zwave-%d", int(nodeID))

	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		return
	}

	log.Printf("[ZWAVE] Node %d dead: %s", int(nodeID), device.Name)

	// Create device offline incident
	s.createZWaveIncident(device, "device_offline", "warning",
		fmt.Sprintf("Device offline: %s", device.Name))
}

// handleZWaveNodeAlive handles node back online events
func (s *Server) handleZWaveNodeAlive(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	deviceID := fmt.Sprintf("zwave-%d", int(nodeID))

	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		return
	}

	log.Printf("[ZWAVE] Node %d alive: %s", int(nodeID), device.Name)

	// Clear offline incident
	s.clearZWaveIncidents(deviceID, "device_offline")

	// Update last seen
	device.LastSeen = time.Now()
	device.UpdatedAt = time.Now()
	s.deviceRepo.Upsert(context.Background(), device)
}

// handleZWaveInclusionStarted handles inclusion started event
func (s *Server) handleZWaveInclusionStarted(event zwave.Event) {
	log.Printf("[ZWAVE] Inclusion started")

	s.eventBus.Publish(Event{
		Type: "zwave.inclusion_started",
		Data: map[string]interface{}{
			"status": "ready",
		},
	})
}

// handleZWaveInclusionFailed handles inclusion failed event
func (s *Server) handleZWaveInclusionFailed(event zwave.Event) {
	log.Printf("[ZWAVE] Inclusion failed")

	s.eventBus.Publish(Event{
		Type: "zwave.inclusion_failed",
		Data: map[string]interface{}{
			"status": "failed",
		},
	})
}

// handleZWaveInclusionStopped handles inclusion stopped event
func (s *Server) handleZWaveInclusionStopped(event zwave.Event) {
	log.Printf("[ZWAVE] Inclusion stopped")

	s.eventBus.Publish(Event{
		Type: "zwave.inclusion_stopped",
		Data: map[string]interface{}{
			"status": "stopped",
		},
	})
}

// createZWaveIncident creates a new incident for a Z-Wave device
func (s *Server) createZWaveIncident(device *model.Device, incidentType, severity, message string) {
	ctx := context.Background()

	// Check if incident already exists and is open
	filters := map[string]any{
		"device_id": device.ID,
		"status":    "open",
	}
	existingIncidents, _ := s.incidentService.List(ctx, filters)
	for _, inc := range existingIncidents {
		if inc.Title == incidentType && inc.Status == model.StatusOpen {
			// Incident already exists
			return
		}
	}

	// Map string severity to model.IncidentSeverity
	var sev model.IncidentSeverity
	switch severity {
	case "critical":
		sev = model.SeverityCritical
	case "high":
		sev = model.SeverityHigh
	case "medium":
		sev = model.SeverityMedium
	case "low":
		sev = model.SeverityLow
	default:
		sev = model.SeverityInfo
	}

	// Create new incident
	incident := &model.Incident{
		Title:       incidentType,
		Description: message,
		Severity:    sev,
		Status:      model.StatusOpen,
		DeviceID:    device.ID,
		ZoneID:      device.ZoneID,
		AssetID:     device.AssetID,
		Data:        map[string]any{},
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}

	if err := s.incidentService.CreateOrUpdate(ctx, incident); err != nil {
		log.Printf("[ZWAVE] Failed to create incident: %v", err)
		return
	}

	// Publish incident added event
	s.eventBus.Publish(Event{
		Type: IncidentAdded,
		Data: incident,
	})

	log.Printf("[ZWAVE] Incident raised: %s for %s", incidentType, device.Name)
}

// clearZWaveIncidents clears all open incidents of a specific type for a device
func (s *Server) clearZWaveIncidents(deviceID, incidentType string) {
	ctx := context.Background()

	filters := map[string]any{
		"device_id": deviceID,
		"status":    "open",
	}
	incidents, err := s.incidentService.List(ctx, filters)
	if err != nil {
		return
	}

	for _, incident := range incidents {
		if incident.Title == incidentType && incident.Status == model.StatusOpen {
			if err := s.incidentService.Resolve(ctx, incident.ID); err != nil {
				log.Printf("[ZWAVE] Failed to resolve incident: %v", err)
				continue
			}

			// Publish incident updated event
			s.eventBus.Publish(Event{
				Type: IncidentUpdated,
				Data: incident,
			})

			log.Printf("[ZWAVE] Incident resolved: %s for device %s", incidentType, deviceID)
		}
	}
}

func timePtr(t time.Time) *time.Time {
	return &t
}
