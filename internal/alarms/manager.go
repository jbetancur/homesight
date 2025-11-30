package alarms

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/google/uuid"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/model"
)

// Manager manages the lifecycle of alarm-based incidents
type Manager struct {
	detector        *Detector
	incidentService incidents.IncidentService
}

// NewManager creates a new alarm manager
func NewManager(incidentService incidents.IncidentService) *Manager {
	return &Manager{
		detector:        NewDetector(),
		incidentService: incidentService,
	}
}

// ProcessStateUpdate processes a device state update and manages incidents
func (m *Manager) ProcessStateUpdate(ctx context.Context, deviceID string, key string, value interface{}, device *model.Device) error {
	// Detect if this is an alarm condition
	alarm := m.detector.DetectAlarm(deviceID, key, value)
	if alarm == nil {
		// Not an alarm condition, nothing to do
		return nil
	}

	log.Printf("[ALARM-MANAGER] Detected alarm: device=%s, key=%s, active=%v, type=%s", deviceID, key, alarm.IsActive, alarm.IncidentType)

	if alarm.IsActive {
		// Alarm is ON - create or update active incident
		return m.createOrUpdateIncident(ctx, alarm, device)
	} else {
		// Alarm is OFF - resolve any active incident
		return m.resolveIncident(ctx, deviceID, alarm.IncidentType)
	}
}

// createOrUpdateIncident creates a new incident or updates an existing active one
func (m *Manager) createOrUpdateIncident(ctx context.Context, alarm *AlarmCondition, device *model.Device) error {
	// Check if there's already an active incident for this device + alarm type
	existing, err := m.findActiveIncident(ctx, alarm.DeviceID, alarm.IncidentType)
	if err != nil {
		log.Printf("[ALARM-MANAGER] Error finding existing incident: %v", err)
		// Continue anyway - we'll create a new one
	}

	if existing != nil {
		// Incident already exists and is active
		log.Printf("[ALARM-MANAGER] Active incident already exists: %s", existing.ID)

		// Update the incident with latest data
		existing.UpdatedAt = time.Now()
		if existing.Data == nil {
			existing.Data = make(map[string]any)
		}
		existing.Data["latest_value"] = alarm.Value
		existing.Data["latest_key"] = alarm.Key
		existing.Data["updated_count"] = getIntOrZero(existing.Data["updated_count"]) + 1

		return m.incidentService.CreateOrUpdate(ctx, existing)
	}

	// Create new incident
	incident := &model.Incident{
		ID:          uuid.New().String(),
		Type:        alarm.IncidentType,
		Title:       alarm.Title,
		Description: alarm.Description,
		Severity:    alarm.Severity,
		Status:      model.StatusOpen,
		DeviceID:    alarm.DeviceID,
		SensorID:    alarm.DeviceID, // Use device ID as sensor ID for now
		RuleName:    "alarm_detector",
		Data: map[string]any{
			"alarm_key":   alarm.Key,
			"alarm_value": alarm.Value,
			"trigger_time": time.Now().Format(time.RFC3339),
		},
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
		AnalysisStatus: "pending",
	}

	// Populate zone and asset from device if available
	if device != nil {
		incident.ZoneID = device.ZoneID
		incident.AssetID = device.AssetID
	}

	log.Printf("[ALARM-MANAGER] Creating new incident: %s (type=%s, device=%s)", incident.ID, incident.Type, incident.DeviceID)

	return m.incidentService.CreateOrUpdate(ctx, incident)
}

// resolveIncident resolves any active incident for the given device and alarm type
func (m *Manager) resolveIncident(ctx context.Context, deviceID string, incidentType model.IncidentType) error {
	// Find active incident
	incident, err := m.findActiveIncident(ctx, deviceID, incidentType)
	if err != nil {
		return fmt.Errorf("error finding active incident: %w", err)
	}

	if incident == nil {
		// No active incident to resolve
		log.Printf("[ALARM-MANAGER] No active incident to resolve for device=%s, type=%s", deviceID, incidentType)
		return nil
	}

	// Resolve the incident
	log.Printf("[ALARM-MANAGER] Resolving incident: %s (device=%s, type=%s)", incident.ID, deviceID, incidentType)
	return m.incidentService.Resolve(ctx, incident.ID)
}

// findActiveIncident finds an active incident for a device and incident type
func (m *Manager) findActiveIncident(ctx context.Context, deviceID string, incidentType model.IncidentType) (*model.Incident, error) {
	// List all open incidents for this device
	filters := map[string]any{
		"status":    model.StatusOpen,
		"device_id": deviceID,
	}

	incidents, err := m.incidentService.List(ctx, filters)
	if err != nil {
		return nil, err
	}

	// Find the one matching this incident type
	for _, inc := range incidents {
		if inc.Type == incidentType {
			return &inc, nil
		}
	}

	return nil, nil
}

// getIntOrZero safely extracts an int from interface{} or returns 0
func getIntOrZero(v any) int {
	switch val := v.(type) {
	case int:
		return val
	case float64:
		return int(val)
	case int64:
		return int(val)
	default:
		return 0
	}
}
