package zwave

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// SetupEventListeners configures all Z-Wave event subscriptions
func (s *Service) SetupEventListeners() {
	// Driver ready - controller initialized
	s.client.On(EventDriverReady, s.handleDriverReady)

	// Node lifecycle events
	s.client.On(EventNodeAdded, s.handleNodeAdded)
	s.client.On(EventNodeReady, s.handleNodeReady)
	s.client.On(EventNodeRemoved, s.handleNodeRemoved)
	s.client.On(EventNodeInterview, s.handleNodeInterview)

	// Value changes
	s.client.On(EventValueUpdated, s.handleValueUpdated)
	s.client.On(EventValueAdded, s.handleValueAdded)

	// Notifications (alarms, sensors)
	s.client.On(EventNotification, s.handleNotification)

	// Node status
	s.client.On(EventNodeDead, s.handleNodeDead)
	s.client.On(EventNodeAlive, s.handleNodeAlive)
	s.client.On(EventNodeWakeUp, s.handleNodeWakeUp)
	s.client.On(EventNodeSleep, s.handleNodeSleep)

	log.Println("[ZWAVE] Event listeners configured")
}

// handleDriverReady processes driver ready event
func (s *Service) handleDriverReady(event Event) {
	log.Printf("[ZWAVE] Driver ready, controller initialized")
	// Initial sync happens in service Start() after this event
}

// handleNodeAdded processes new node addition
func (s *Service) handleNodeAdded(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		log.Printf("[ZWAVE] Invalid nodeId in node added event")
		return
	}
	nodeID := int(nodeIDFloat)

	log.Printf("[ZWAVE] Node added: %d (interview starting)", nodeID)
}

// handleNodeReady processes node ready event (interview complete)
func (s *Service) handleNodeReady(event Event) {
	nodeData, ok := event.Data["node"]
	if !ok {
		log.Printf("[ZWAVE] No node data in node ready event")
		return
	}

	// Parse the node
	data, err := json.Marshal(nodeData)
	if err != nil {
		log.Printf("[ZWAVE] Failed to marshal node data: %v", err)
		return
	}

	var node ZWaveNode
	if err := json.Unmarshal(data, &node); err != nil {
		log.Printf("[ZWAVE] Failed to unmarshal node: %v", err)
		return
	}

	log.Printf("[ZWAVE] Node ready: %d - %s (manufacturer: %s)",
		node.NodeID, node.DeviceConfig.Label, node.DeviceConfig.Manufacturer)

	// Convert to device model
	s.client.stateMu.RLock()
	homeID := s.client.homeID
	s.client.stateMu.RUnlock()

	device := MapNodeToDevice(&node, homeID)

	// Set timestamps - mark as online
	now := time.Now()
	device.LastSeen = now
	device.UpdatedAt = now
	if device.CreatedAt.IsZero() {
		device.CreatedAt = now
	}

	// Upsert to database
	if err := s.deviceRepo.Upsert(s.ctx, device); err != nil {
		log.Printf("[ZWAVE] Failed to upsert device: %v", err)
		return
	}

	// Emit discovery event
	s.emitDiscovery(device, "node_ready")

	log.Printf("[ZWAVE] Device registered: %s (%s)", device.ID, device.Name)
}

// handleNodeRemoved processes node removal
func (s *Service) handleNodeRemoved(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	log.Printf("[ZWAVE] Node removed: %d (device: %s)", nodeID, deviceID)

	// Delete from database
	if err := s.deviceRepo.Delete(s.ctx, deviceID); err != nil {
		log.Printf("[ZWAVE] Failed to delete device: %v", err)
	}
}

// handleNodeInterview processes interview progress
func (s *Service) handleNodeInterview(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	stageFloat, ok := event.Data["stageName"].(float64)
	stageName := "unknown"
	if ok {
		stageName = getInterviewStageName(int(stageFloat))
	}

	log.Printf("[ZWAVE] Node %d interview: %s", nodeID, stageName)
}

// handleValueUpdated processes value change events
func (s *Service) handleValueUpdated(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	// Extract value change details
	commandClass, _ := args["commandClass"].(float64)
	property, _ := args["property"].(string)
	newValue := args["newValue"]
	propertyName, _ := args["propertyName"].(string)

	// Extract unit metadata if available from Z-Wave JS
	// The metadata contains the unit string (e.g., "°F", "°C", "%")
	var unit string
	if metadata, ok := args["metadata"].(map[string]interface{}); ok {
		if unitStr, ok := metadata["unit"].(string); ok {
			unit = unitStr
		}
	}

	log.Printf("[ZWAVE] Node %d value updated: %s (CC %d) = %v unit=%s",
		nodeID, property, int(commandClass), newValue, unit)

	// Update device state in database (pass command class and unit for context)
	s.updateDeviceStateWithUnit(nodeID, int(commandClass), property, newValue, propertyName, unit)

	// Emit device event
	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	s.publishDeviceEvent(deviceID, property, newValue)

	// Check for incidents
	s.checkIncident(nodeID, int(commandClass), property, newValue, args)
}

// handleValueAdded processes new value discovery
func (s *Service) handleValueAdded(event Event) {
	// Similar to value updated, but for newly discovered values
	s.handleValueUpdated(event)
}

// handleNotification processes Z-Wave notifications (alarms)
func (s *Service) handleNotification(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	args, ok := event.Data["args"].(map[string]interface{})
	if !ok {
		return
	}

	// Extract notification details
	notifType, _ := args["type"].(float64)
	notifEvent, _ := args["event"].(float64)
	label, _ := args["label"].(string)
	eventLabel, _ := args["eventLabel"].(string)

	log.Printf("[ZWAVE] Notification from node %d: %s - %s (type=%d, event=%d)",
		nodeID, label, eventLabel, int(notifType), int(notifEvent))

	// Map notification to incident
	s.createIncidentFromNotification(nodeID, int(notifType), int(notifEvent), label, eventLabel)
}

// handleNodeDead processes node dead event
func (s *Service) handleNodeDead(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	log.Printf("[ZWAVE] Node %d is dead (not responding)", nodeID)

	// Mark device as disabled
	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	device, err := s.deviceRepo.Get(s.ctx, deviceID)
	if err == nil && device != nil {
		device.Enabled = false
		s.deviceRepo.Upsert(s.ctx, device)
	}

	// Create incident for offline device
	s.createIncident(nodeID, "Node Offline", "Z-Wave node is not responding", model.SeverityMedium, map[string]any{
		"reason": "dead",
	})
}

// handleNodeAlive processes node alive event
func (s *Service) handleNodeAlive(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	log.Printf("[ZWAVE] Node %d is alive (responding)", nodeID)

	// Mark device as enabled
	deviceID := fmt.Sprintf("zwave-%d", nodeID)
	device, err := s.deviceRepo.Get(s.ctx, deviceID)
	if err == nil && device != nil {
		device.Enabled = true
		s.deviceRepo.Upsert(s.ctx, device)
	}
}

// handleNodeWakeUp processes node wake up event
func (s *Service) handleNodeWakeUp(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	log.Printf("[ZWAVE] Node %d woke up", nodeID)
}

// handleNodeSleep processes node sleep event
func (s *Service) handleNodeSleep(event Event) {
	nodeIDFloat, ok := event.Data["nodeId"].(float64)
	if !ok {
		return
	}
	nodeID := int(nodeIDFloat)

	log.Printf("[ZWAVE] Node %d went to sleep", nodeID)
}

// Helper functions

func getInterviewStageName(stage int) string {
	stages := map[int]string{
		0: "None",
		1: "ProtocolInfo",
		2: "NodeInfo",
		3: "CommandClasses",
		4: "OverwriteConfig",
		5: "Neighbors",
		6: "Complete",
	}
	if name, ok := stages[stage]; ok {
		return name
	}
	return fmt.Sprintf("Stage%d", stage)
}
