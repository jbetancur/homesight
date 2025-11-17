package rules

import (
	"context"

	"github.com/homesight/homesight/internal/model"
)

// RuleEngine evaluates events against configured rules
type RuleEngine interface {
	// Process evaluates an event and returns any triggered incidents
	Process(ctx context.Context, event model.DeviceEvent) ([]model.Incident, error)

	// Close shuts down the rule engine
	Close() error
}
