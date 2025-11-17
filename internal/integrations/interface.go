package integrations

import (
	"context"

	"github.com/homesight/homesight/internal/model"
)

// Integration defines the contract for all device integrations
type Integration interface {
	// Discover finds devices supported by this integration
	Discover(ctx context.Context) ([]model.DeviceDescriptor, error)

	// Subscribe starts listening for device events
	Subscribe(ctx context.Context, events chan<- model.DeviceEvent) error

	// Control sends a command to a device
	Control(ctx context.Context, cmd model.DeviceCommand) error

	// Close shuts down the integration
	Close() error
}
