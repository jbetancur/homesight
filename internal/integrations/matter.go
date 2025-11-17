package integrations

import (
	"context"
	"fmt"
	"time"

	"github.com/homesight/homesight/internal/discovery"
	"github.com/homesight/homesight/internal/model"
)

// MatterIntegration integrates Matter-compatible devices
type MatterIntegration struct {
	discoveredDevices map[string]discovery.LANDevice
}

// NewMatterIntegration creates a new Matter integration
func NewMatterIntegration() *MatterIntegration {
	return &MatterIntegration{
		discoveredDevices: make(map[string]discovery.LANDevice),
	}
}

// Discover finds Matter devices
func (i *MatterIntegration) Discover(ctx context.Context) ([]model.DeviceDescriptor, error) {
	// Auto-discover Matter devices via mDNS
	devices, err := discovery.DiscoverMatterDevices(5 * time.Second)
	if err != nil {
		return nil, fmt.Errorf("failed to discover Matter devices: %w", err)
	}

	descriptors := make([]model.DeviceDescriptor, 0, len(devices))
	for _, dev := range devices {
		deviceID := fmt.Sprintf("matter-%s", dev.Name)
		i.discoveredDevices[deviceID] = dev

		descriptors = append(descriptors, model.DeviceDescriptor{
			ID:          deviceID,
			Name:        dev.Name,
			Type:        "matter_device",
			Integration: "matter",
			Metadata: map[string]string{
				"host":  dev.Host,
				"port":  fmt.Sprintf("%d", dev.Port),
				"model": dev.Model,
			},
		})
	}

	return descriptors, nil
}

// Subscribe listens for Matter device events
func (i *MatterIntegration) Subscribe(ctx context.Context, events chan<- model.DeviceEvent) error {
	// Matter integration not yet implemented
	// Waiting for stable Matter SDK for Go or will use matter-js bridge
	return fmt.Errorf("matter integration not yet implemented")
}

// Control sends a command to a Matter device
func (i *MatterIntegration) Control(ctx context.Context, cmd model.DeviceCommand) error {
	// Matter integration not yet implemented
	// Will use Matter SDK's device control API when implemented
	return fmt.Errorf("matter integration not yet implemented")
}

// Close shuts down the Matter integration
func (i *MatterIntegration) Close() error {
	return nil
}
