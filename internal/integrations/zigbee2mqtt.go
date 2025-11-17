package integrations

import (
	"context"
	"fmt"

	"github.com/homesight/homesight/internal/model"
)

// Zigbee2MQTTIntegration integrates Zigbee devices via Zigbee2MQTT
type Zigbee2MQTTIntegration struct {
	*MQTTIntegration
}

// NewZigbee2MQTTIntegration creates a new Zigbee2MQTT integration
func NewZigbee2MQTTIntegration(brokerURL string) (*Zigbee2MQTTIntegration, error) {
	return NewZigbee2MQTTIntegrationWithAuth(brokerURL, "", "")
}

// NewZigbee2MQTTIntegrationWithAuth creates a new Zigbee2MQTT integration with authentication
func NewZigbee2MQTTIntegrationWithAuth(brokerURL, username, password string) (*Zigbee2MQTTIntegration, error) {
	mqtt, err := NewMQTTIntegrationWithAuth(brokerURL, "zigbee2mqtt", username, password)
	if err != nil {
		return nil, fmt.Errorf("failed to create Zigbee2MQTT integration: %w", err)
	}

	return &Zigbee2MQTTIntegration{
		MQTTIntegration: mqtt,
	}, nil
}

// Discover finds Zigbee devices
func (i *Zigbee2MQTTIntegration) Discover(ctx context.Context) ([]model.DeviceDescriptor, error) {
	// Zigbee2MQTT provides device discovery via MQTT bridge topic
	return i.MQTTIntegration.Discover(ctx)
}
