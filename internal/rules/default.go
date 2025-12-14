package rules

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/model"
)

// DefaultRuleEngine implements common home monitoring rules
type DefaultRuleEngine struct {
	mu               sync.RWMutex
	deviceStates     map[string]deviceState
	sumpPumpCycles   map[string][]time.Time
	freezeThresholds map[string]float64
	activeIncidents  map[string]*model.Incident // Track active incidents by rule+device key
	deviceRepo       db.DeviceRepository        // For looking up device details
}

type deviceState struct {
	lastSeen  time.Time
	lastValue any
	battery   float64
}

// NewDefaultRuleEngine creates a new rule engine with standard rules
func NewDefaultRuleEngine(deviceRepo db.DeviceRepository) *DefaultRuleEngine {
	return &DefaultRuleEngine{
		deviceStates:     make(map[string]deviceState),
		sumpPumpCycles:   make(map[string][]time.Time),
		freezeThresholds: make(map[string]float64),
		activeIncidents:  make(map[string]*model.Incident),
		deviceRepo:       deviceRepo,
	}
}

// enrichIncident adds zone_id and asset_id from device lookup
func (e *DefaultRuleEngine) enrichIncident(ctx context.Context, incident *model.Incident) {
	if e.deviceRepo == nil || incident.DeviceID == "" {
		return
	}

	device, err := e.deviceRepo.Get(ctx, incident.DeviceID)
	if err != nil {
		// Device not found or error - continue without enrichment
		log.Printf("Failed to enrich incident %s with device details: %v", incident.ID, err)
		return
	}

	// Populate zone and asset IDs from device
	incident.ZoneID = device.ZoneID
	incident.AssetID = device.AssetID
}

// Process evaluates an event and returns any triggered incidents
func (e *DefaultRuleEngine) Process(ctx context.Context, event model.DeviceEvent) ([]model.Incident, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	incidents := make([]model.Incident, 0)

	// Update device state
	e.deviceStates[event.DeviceID] = deviceState{
		lastSeen:  event.Timestamp,
		lastValue: event.Value,
	}

	// Apply rules based on sensor type
	metadata := event.Metadata
	if metadata == nil {
		metadata = make(map[string]string)
	}

	sensorType := metadata["type"]
	switch sensorType {
	case "leak_sensor", "water_sensor":
		if inc := e.checkLeakDetection(event); inc != nil {
			e.enrichIncident(ctx, inc)
			incidents = append(incidents, *inc)
		}
	case "temperature":
		if inc := e.checkFreezeRisk(event); inc != nil {
			e.enrichIncident(ctx, inc)
			incidents = append(incidents, *inc)
		}
	case "sump_pump":
		if inc := e.checkSumpPumpCycles(event); inc != nil {
			e.enrichIncident(ctx, inc)
			incidents = append(incidents, *inc)
		}
	case "battery":
		if inc := e.checkBatteryLow(event); inc != nil {
			e.enrichIncident(ctx, inc)
			incidents = append(incidents, *inc)
		}
	}

	// Check device offline
	if inc := e.checkDeviceOffline(event); inc != nil {
		e.enrichIncident(ctx, inc)
		incidents = append(incidents, *inc)
	}

	return incidents, nil
}

// checkLeakDetection detects water leaks
func (e *DefaultRuleEngine) checkLeakDetection(event model.DeviceEvent) *model.Incident {
	leak, ok := event.Value.(bool)
	if !ok {
		return nil
	}

	incidentKey := fmt.Sprintf("leak_%s", event.DeviceID)

	if leak {
		// Leak detected - create or update incident
		incident := &model.Incident{
			ID:          fmt.Sprintf("leak_%s_%d", event.DeviceID, event.Timestamp.Unix()),
			Title:       "Water Leak Detected",
			Description: fmt.Sprintf("Leak sensor %s detected water", event.SensorID),
			Severity:    model.SeverityCritical,
			Status:      model.StatusOpen,
			DeviceID:    event.DeviceID,
			SensorID:    event.SensorID,
			RuleName:    "leak_detection",
			Data: map[string]any{
				"detected_at": event.Timestamp,
			},
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
		e.activeIncidents[incidentKey] = incident
		return incident
	}

	// No leak - auto-resolve if incident exists
	if activeIncident, exists := e.activeIncidents[incidentKey]; exists {
		now := time.Now()
		activeIncident.Status = model.StatusResolved
		activeIncident.ResolvedAt = &now
		activeIncident.UpdatedAt = now
		delete(e.activeIncidents, incidentKey)
		return activeIncident
	}

	return nil
}

// checkFreezeRisk detects freeze risk from temperature sensors
func (e *DefaultRuleEngine) checkFreezeRisk(event model.DeviceEvent) *model.Incident {
	temp, ok := event.Value.(float64)
	if !ok {
		return nil
	}

	threshold := 35.0 // °F
	if t, exists := e.freezeThresholds[event.SensorID]; exists {
		threshold = t
	}

	incidentKey := fmt.Sprintf("freeze_%s", event.DeviceID)

	if temp < threshold {
		// Temperature below threshold - create or update incident
		incident := &model.Incident{
			ID:          fmt.Sprintf("freeze_%s_%d", event.DeviceID, event.Timestamp.Unix()),
			Title:       "Freeze Risk Detected",
			Description: fmt.Sprintf("Temperature %.1f°F is below freeze threshold of %.1f°F", temp, threshold),
			Severity:    model.SeverityHigh,
			Status:      model.StatusOpen,
			DeviceID:    event.DeviceID,
			SensorID:    event.SensorID,
			RuleName:    "freeze_risk",
			Data: map[string]any{
				"temperature": temp,
				"threshold":   threshold,
			},
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
		e.activeIncidents[incidentKey] = incident
		return incident
	}

	// Temperature safe - auto-resolve if incident exists
	if activeIncident, exists := e.activeIncidents[incidentKey]; exists {
		now := time.Now()
		activeIncident.Status = model.StatusResolved
		activeIncident.ResolvedAt = &now
		activeIncident.UpdatedAt = now
		delete(e.activeIncidents, incidentKey)
		return activeIncident
	}

	return nil
}

// checkSumpPumpCycles detects excessive sump pump activity
func (e *DefaultRuleEngine) checkSumpPumpCycles(event model.DeviceEvent) *model.Incident {
	active, ok := event.Value.(bool)
	if !ok || !active {
		return nil
	}

	// Record cycle
	cycles := e.sumpPumpCycles[event.DeviceID]
	cycles = append(cycles, event.Timestamp)

	// Keep only last hour
	cutoff := event.Timestamp.Add(-1 * time.Hour)
	filtered := make([]time.Time, 0)
	for _, t := range cycles {
		if t.After(cutoff) {
			filtered = append(filtered, t)
		}
	}
	e.sumpPumpCycles[event.DeviceID] = filtered

	// Check if too many cycles
	if len(filtered) > 20 {
		return &model.Incident{
			ID:          fmt.Sprintf("sump_%s_%d", event.DeviceID, event.Timestamp.Unix()),
			Title:       "Excessive Sump Pump Activity",
			Description: fmt.Sprintf("Sump pump has cycled %d times in the last hour", len(filtered)),
			Severity:    model.SeverityHigh,
			Status:      model.StatusOpen,
			DeviceID:    event.DeviceID,
			SensorID:    event.SensorID,
			RuleName:    "sump_pump_excessive",
			Data: map[string]any{
				"cycle_count": len(filtered),
				"period":      "1h",
			},
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
	}

	return nil
}

// checkBatteryLow detects low battery levels
func (e *DefaultRuleEngine) checkBatteryLow(event model.DeviceEvent) *model.Incident {
	battery, ok := event.Value.(float64)
	if !ok {
		return nil
	}

	// Check if device is AC-powered (battery is backup only)
	// Skip battery incidents for AC-powered devices with backup batteries
	if e.deviceRepo != nil {
		device, err := e.deviceRepo.Get(context.Background(), event.DeviceID)
		if err == nil && device != nil && device.Entities != nil {
			if e.isACPoweredDevice(device.Entities) {
				log.Printf("[RULES] Skipping battery incident for %s - device is AC-powered with backup battery", event.DeviceID)
				return nil
			}
		}
	}

	incidentKey := fmt.Sprintf("battery_%s", event.DeviceID)
	threshold := 20.0

	if battery < threshold {
		// Low battery - create or update incident
		incident := &model.Incident{
			ID:          fmt.Sprintf("battery_%s_%d", event.DeviceID, event.Timestamp.Unix()),
			Title:       "Low Battery",
			Description: fmt.Sprintf("Device battery at %.0f%%", battery),
			Severity:    model.SeverityMedium,
			Status:      model.StatusOpen,
			DeviceID:    event.DeviceID,
			SensorID:    event.SensorID,
			RuleName:    "battery_low",
			Data: map[string]any{
				"battery_percent": battery,
			},
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
		e.activeIncidents[incidentKey] = incident
		return incident
	}

	// Battery OK - auto-resolve if incident exists
	if activeIncident, exists := e.activeIncidents[incidentKey]; exists {
		now := time.Now()
		activeIncident.Status = model.StatusResolved
		activeIncident.ResolvedAt = &now
		activeIncident.UpdatedAt = now
		delete(e.activeIncidents, incidentKey)
		return activeIncident
	}

	return nil
}

// checkDeviceOffline detects devices that haven't reported recently
func (e *DefaultRuleEngine) checkDeviceOffline(event model.DeviceEvent) *model.Incident {
	// This would typically be run periodically, not per-event
	// Placeholder for now
	return nil
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
func (e *DefaultRuleEngine) isACPoweredDevice(entities []model.DeviceEntity) bool {
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
						log.Printf("[RULES] Detected AC power via Wake Up interval: %.0fs (>= %ds threshold)", interval, wakeUpIntervalThreshold)
						return true
					}
				}
			}
		}

		// Check for explicit backup battery indicator
		if propNameLower == "backup" {
			if backup, ok := entity.Value.(bool); ok && backup {
				log.Printf("[RULES] Detected AC power via backup battery flag")
				return true
			}
		}

		// Check for battery disconnected (indicating optional backup)
		if (propNameLower == "disconnected" || propNameLower == "battery disconnected") && int(cc) == CC_BATTERY {
			if disconnected, ok := entity.Value.(bool); ok && disconnected {
				log.Printf("[RULES] Detected AC power via battery disconnected flag")
				return true
			}
		}
	}

	// If device has battery but NO Wake Up entity, it's always-listening (AC-powered)
	// Battery-powered devices ALWAYS have Wake Up to conserve power
	if !hasWakeUpEntity {
		log.Printf("[RULES] Detected AC power: No Wake Up entity (always-listening device)")
		return true
	}

	return false
}

// Close shuts down the rule engine
func (e *DefaultRuleEngine) Close() error {
	return nil
}
