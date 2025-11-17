package rules

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// DefaultRuleEngine implements common home monitoring rules
type DefaultRuleEngine struct {
	mu               sync.RWMutex
	deviceStates     map[string]deviceState
	sumpPumpCycles   map[string][]time.Time
	freezeThresholds map[string]float64
}

type deviceState struct {
	lastSeen  time.Time
	lastValue any
	battery   float64
}

// NewDefaultRuleEngine creates a new rule engine with standard rules
func NewDefaultRuleEngine() *DefaultRuleEngine {
	return &DefaultRuleEngine{
		deviceStates:     make(map[string]deviceState),
		sumpPumpCycles:   make(map[string][]time.Time),
		freezeThresholds: make(map[string]float64),
	}
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
			incidents = append(incidents, *inc)
		}
	case "temperature":
		if inc := e.checkFreezeRisk(event); inc != nil {
			incidents = append(incidents, *inc)
		}
	case "sump_pump":
		if inc := e.checkSumpPumpCycles(event); inc != nil {
			incidents = append(incidents, *inc)
		}
	case "battery":
		if inc := e.checkBatteryLow(event); inc != nil {
			incidents = append(incidents, *inc)
		}
	}

	// Check device offline
	if inc := e.checkDeviceOffline(event); inc != nil {
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

	if leak {
		return &model.Incident{
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

	if temp < threshold {
		return &model.Incident{
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

	if battery < 20.0 {
		return &model.Incident{
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
	}

	return nil
}

// checkDeviceOffline detects devices that haven't reported recently
func (e *DefaultRuleEngine) checkDeviceOffline(event model.DeviceEvent) *model.Incident {
	// This would typically be run periodically, not per-event
	// Placeholder for now
	return nil
}

// Close shuts down the rule engine
func (e *DefaultRuleEngine) Close() error {
	return nil
}
