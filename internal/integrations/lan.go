package integrations

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// LANIntegration integrates LAN-based devices (Shelly, Tapo, Govee)
type LANIntegration struct {
	client  *http.Client
	devices map[string]string // device_id -> base_url
}

// NewLANIntegration creates a new LAN integration
func NewLANIntegration() *LANIntegration {
	return &LANIntegration{
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
		devices: make(map[string]string),
	}
}

// RegisterDevice adds a device to the LAN integration
func (i *LANIntegration) RegisterDevice(deviceID, baseURL string) {
	i.devices[deviceID] = baseURL
}

// Discover finds LAN devices (typically configured, not auto-discovered)
func (i *LANIntegration) Discover(ctx context.Context) ([]model.DeviceDescriptor, error) {
	devices := make([]model.DeviceDescriptor, 0)
	for id := range i.devices {
		devices = append(devices, model.DeviceDescriptor{
			ID:          id,
			Name:        id,
			Type:        "lan_device",
			Integration: "lan",
		})
	}
	return devices, nil
}

// Subscribe polls LAN devices for state changes
func (i *LANIntegration) Subscribe(ctx context.Context, events chan<- model.DeviceEvent) error {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			for deviceID, baseURL := range i.devices {
				event, err := i.pollDevice(deviceID, baseURL)
				if err != nil {
					continue
				}
				events <- event
			}
		}
	}
}

// pollDevice retrieves current state from a device
func (i *LANIntegration) pollDevice(deviceID, baseURL string) (model.DeviceEvent, error) {
	url := fmt.Sprintf("%s/status", baseURL)
	resp, err := i.client.Get(url)
	if err != nil {
		return model.DeviceEvent{}, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.DeviceEvent{}, err
	}

	var state map[string]any
	if err := json.Unmarshal(body, &state); err != nil {
		return model.DeviceEvent{}, err
	}

	return model.DeviceEvent{
		DeviceID:  deviceID,
		SensorID:  deviceID,
		Timestamp: time.Now(),
		ValueType: "json",
		Value:     state,
		Metadata:  map[string]string{"integration": "lan"},
	}, nil
}

// Control sends a command to a LAN device
func (i *LANIntegration) Control(ctx context.Context, cmd model.DeviceCommand) error {
	baseURL, ok := i.devices[cmd.DeviceID]
	if !ok {
		return fmt.Errorf("device not found: %s", cmd.DeviceID)
	}

	url := fmt.Sprintf("%s/%s", baseURL, cmd.Command)
	payload, _ := json.Marshal(cmd.Arguments)

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(payload))
	if err != nil {
		return err
	}

	resp, err := i.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("device returned status %d", resp.StatusCode)
	}

	return nil
}

// Close shuts down the LAN integration
func (i *LANIntegration) Close() error {
	return nil
}
