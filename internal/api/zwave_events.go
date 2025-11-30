package api

import (
	"context"
	"fmt"
	"log"
	"strings"
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
	s.zwaveClient.On(zwave.EventNodeInterview, s.handleZWaveNodeInterview)
	s.zwaveClient.On(zwave.EventNodeRemoved, s.handleZWaveNodeRemoved)
	s.zwaveClient.On(zwave.EventValueUpdated, s.handleZWaveValueUpdated)
	s.zwaveClient.On(zwave.EventNotification, s.handleZWaveNotification)
	s.zwaveClient.On(zwave.EventNodeDead, s.handleZWaveNodeDead)
	s.zwaveClient.On(zwave.EventNodeAlive, s.handleZWaveNodeAlive)
	s.zwaveClient.On(zwave.EventInclusionStarted, s.handleZWaveInclusionStarted)
	s.zwaveClient.On(zwave.EventInclusionFailed, s.handleZWaveInclusionFailed)
	s.zwaveClient.On(zwave.EventInclusionStopped, s.handleZWaveInclusionStopped)
	s.zwaveClient.On(zwave.EventExclusionStarted, s.handleZWaveExclusionStarted)
	s.zwaveClient.On(zwave.EventExclusionStopped, s.handleZWaveExclusionStopped)

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

	// Build map of current Z-Wave node IDs
	currentNodeIDs := make(map[string]bool)
	for _, node := range nodes {
		if node.NodeID == 1 {
			// Skip controller node
			continue
		}

		deviceID := fmt.Sprintf("zwave-%d", node.NodeID)
		currentNodeIDs[deviceID] = true

		// Sync all nodes, even if not ready yet (interviewing nodes)
		// This ensures devices appear in the UI immediately
		s.syncZWaveNode(&node)
	}

	// Remove devices that are no longer in Z-Wave JS (cleanup orphaned devices)
	s.cleanupOrphanedZWaveDevices(currentNodeIDs)
}

// cleanupOrphanedZWaveDevices removes devices from DB that are no longer in Z-Wave JS
func (s *Server) cleanupOrphanedZWaveDevices(currentNodeIDs map[string]bool) {
	// Get all devices from database
	allDevices, err := s.deviceRepo.List(context.Background())
	if err != nil {
		log.Printf("[ZWAVE] Failed to list devices for cleanup: %v", err)
		return
	}

	// Remove Z-Wave devices that aren't in Z-Wave JS anymore
	for _, device := range allDevices {
		// Only process Z-Wave devices
		if device.Integration != "zwave" {
			continue
		}

		if !currentNodeIDs[device.ID] {
			log.Printf("[ZWAVE] Cleaning up orphaned device: %s (ID: %s)", device.Name, device.ID)

			// Delete from database
			if err := s.deviceRepo.Delete(context.Background(), device.ID); err != nil {
				log.Printf("[ZWAVE] Failed to delete orphaned device: %v", err)
				continue
			}

			// Emit device removed event
			s.eventBus.Publish(Event{
				Type: DeviceRemoved,
				Data: device,
			})

			log.Printf("[ZWAVE] Orphaned device removed: %s (ID: %s)", device.Name, device.ID)
		}
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
		// Preserve user settings, but allow name updates if it was auto-generated
		// Only preserve custom names (not "Node X" format)
		if existing.Name != "" && !strings.HasPrefix(existing.Name, "Node ") {
			device.Name = existing.Name
		}
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

// handleZWaveNodeInterview handles node interview progress
func (s *Server) handleZWaveNodeInterview(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}

	// Get interview stage if available
	interviewStage := -1
	if stage, ok := event.Data["interviewStage"].(float64); ok {
		interviewStage = int(stage)
	}

	// Simply log interview progress - don't create/update devices until ready event
	// This prevents "Node X" / "Unknown Manufacturer" devices from appearing during interview
	log.Printf("[ZWAVE] Node %d interview stage: %d (waiting for ready event to create device)", int(nodeID), interviewStage)
}

// handleZWaveNodeReady handles node interview complete
func (s *Server) handleZWaveNodeReady(event zwave.Event) {
	nodeID, ok := event.Data["nodeId"].(float64)
	if !ok {
		log.Printf("[ZWAVE] ❌ Ready event missing nodeId")
		return
	}

	log.Printf("[ZWAVE] ✅ Node %d READY event received - creating device", int(nodeID))

	// Get full node info from cache
	node, err := s.zwaveClient.GetNode(int(nodeID))
	if err != nil {
		log.Printf("[ZWAVE] ❌ Failed to get node %d from cache: %v", int(nodeID), err)
		return
	}

	log.Printf("[ZWAVE] 📋 Node %d data: name=%s, manufacturer=%s, ready=%v, status=%d",
		int(nodeID), node.DeviceConfig.Label, node.DeviceConfig.Manufacturer, node.Ready, node.Status)

	// Create or update HomeSight device
	s.zwaveMutex.RLock()
	homeID := s.zwaveHomeID
	s.zwaveMutex.RUnlock()

	deviceID := fmt.Sprintf("zwave-%d", int(nodeID))

	// Check if device exists
	existingDevice, _ := s.deviceRepo.Get(context.Background(), deviceID)

	device := zwave.MapNodeToDevice(node, uint32(homeID))
	device.LastSeen = time.Now()
	device.UpdatedAt = time.Now()

	if existingDevice != nil {
		// Device already exists - preserve user settings, but allow name updates if it was auto-generated
		// Only preserve custom names (not "Node X" format)
		if existingDevice.Name != "" && !strings.HasPrefix(existingDevice.Name, "Node ") {
			device.Name = existingDevice.Name
		}
		device.ZoneID = existingDevice.ZoneID
		device.AssetID = existingDevice.AssetID
		device.CreatedAt = existingDevice.CreatedAt

		// Update in database
		if err := s.deviceRepo.Upsert(context.Background(), device); err != nil {
			log.Printf("[ZWAVE] Failed to update device: %v", err)
			return
		}

		// Emit device updated event
		s.eventBus.Publish(Event{
			Type: DeviceUpdated,
			Data: device,
		})

		log.Printf("[ZWAVE] Device ready (updated): %s (ID: %s)", device.Name, device.ID)
	} else {
		// New device - create it
		device.CreatedAt = time.Now()

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
}

// handleZWaveNodeRemoved handles node removal (exclusion/offboarding)
func (s *Server) handleZWaveNodeRemoved(event zwave.Event) {
	log.Printf("[ZWAVE] handleZWaveNodeRemoved called with event data: %+v", event.Data)

	var nodeID float64
	var ok bool

	// Try direct nodeId field first
	if nodeID, ok = event.Data["nodeId"].(float64); !ok {
		// Try nested node.nodeId
		if nodeObj, ok := event.Data["node"].(map[string]interface{}); ok {
			if nodeID, ok = nodeObj["nodeId"].(float64); !ok {
				log.Printf("[ZWAVE] Failed to extract nodeId from nested node object, keys: %v", getKeys(nodeObj))
				return
			}
		} else {
			log.Printf("[ZWAVE] Failed to extract nodeId from event data, keys available: %v", getKeys(event.Data))
			return
		}
	}

	deviceID := fmt.Sprintf("zwave-%d", int(nodeID))
	log.Printf("[ZWAVE] Node %d removed (device: %s)", int(nodeID), deviceID)

	// Get device before deleting to emit proper event
	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		log.Printf("[ZWAVE] Device %s not found for removal", deviceID)
		return
	}

	// Delete from database
	if err := s.deviceRepo.Delete(context.Background(), deviceID); err != nil {
		log.Printf("[ZWAVE] Failed to delete device: %v", err)
		return
	}

	// Emit device removed event with full device data for real-time UI update
	s.eventBus.Publish(Event{
		Type: DeviceRemoved,
		Data: device,
	})

	log.Printf("[ZWAVE] Device offboarded: %s (ID: %s)", device.Name, deviceID)
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

	case zwave.CC_NOTIFICATION:
		// Notification/Alarm events (water leak, smoke, motion, etc.)
		log.Printf("[ZWAVE] Notification %s property=%s value=%v", device.Name, property, newValue)

		// Handle Water Alarm notifications
		if property == "Water Alarm" {
			if valueFloat, ok := newValue.(float64); ok {
				valueInt := int(valueFloat)
				if valueInt == 2 { // Water leak detected
					s.createZWaveIncident(device, "water_leak", "critical",
						fmt.Sprintf("Water leak detected: %s", device.Name))
					log.Printf("[ZWAVE] 🚨 Water leak incident created for %s", device.Name)
				} else if valueInt == 0 { // Leak cleared
					s.clearZWaveIncidents(device.ID, "water_leak")
					log.Printf("[ZWAVE] ✅ Water leak incident cleared for %s", device.Name)
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

// handleZWaveExclusionStarted handles exclusion started event
func (s *Server) handleZWaveExclusionStarted(event zwave.Event) {
	log.Printf("[ZWAVE] Exclusion started")

	s.eventBus.Publish(Event{
		Type: "zwave.exclusion_started",
		Data: map[string]interface{}{
			"status": "ready",
		},
	})
}

// handleZWaveExclusionStopped handles exclusion stopped event
func (s *Server) handleZWaveExclusionStopped(event zwave.Event) {
	log.Printf("[ZWAVE] Exclusion stopped")

	s.eventBus.Publish(Event{
		Type: "zwave.exclusion_stopped",
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

	// Create new incident with generated ID
	incidentID := fmt.Sprintf("%s-%s-%d", device.ID, incidentType, time.Now().Unix())
	incident := &model.Incident{
		ID:          incidentID,
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

	// Notify AI sidecar for analysis
	s.notifyAIIncidentCreated(*incident)

	log.Printf("[ZWAVE] Incident raised: %s for %s", incidentType, device.Name)
}

// clearZWaveIncidents clears all open incidents of a specific type for a device
func (s *Server) clearZWaveIncidents(deviceID, incidentType string) {
	ctx := context.Background()

	log.Printf("[ZWAVE] Attempting to clear incidents for device %s, type %s", deviceID, incidentType)

	filters := map[string]any{
		"device_id": deviceID,
		"status":    "open",
	}
	incidents, err := s.incidentService.List(ctx, filters)
	if err != nil {
		log.Printf("[ZWAVE] Failed to list incidents: %v", err)
		return
	}

	log.Printf("[ZWAVE] Found %d open incidents for device %s", len(incidents), deviceID)

	for _, incident := range incidents {
		log.Printf("[ZWAVE] Checking incident: ID=%s, Title=%s, Status=%s", incident.ID, incident.Title, incident.Status)
		if incident.Title == incidentType && incident.Status == model.StatusOpen {
			log.Printf("[ZWAVE] Resolving incident %s (type=%s)", incident.ID, incidentType)
			if err := s.incidentService.Resolve(ctx, incident.ID); err != nil {
				log.Printf("[ZWAVE] Failed to resolve incident: %v", err)
				continue
			}

			// Fetch updated incident to get the resolved status and timestamp
			updatedIncident, err := s.incidentService.Get(ctx, incident.ID)
			if err != nil {
				log.Printf("[ZWAVE] Failed to fetch updated incident: %v", err)
				continue
			}

			log.Printf("[ZWAVE] Publishing incident_updated event for %s (status=%s)", updatedIncident.ID, updatedIncident.Status)

			// Publish incident updated event with fresh data
			s.eventBus.Publish(Event{
				Type: IncidentUpdated,
				Data: updatedIncident,
			})

			log.Printf("[ZWAVE] ✅ Incident resolved and event published: %s for device %s", incidentType, deviceID)
		}
	}
}

// getKeys returns the keys from a map for debugging
func getKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
