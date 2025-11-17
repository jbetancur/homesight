package integrations

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/homesight/homesight/internal/model"
)

// MQTTIntegration integrates MQTT-based devices
type MQTTIntegration struct {
	client    mqtt.Client
	baseTopic string
	mu        sync.RWMutex
	devices   map[string]model.DeviceDescriptor
}

// NewMQTTIntegration creates a new MQTT integration
func NewMQTTIntegration(brokerURL, baseTopic string) (*MQTTIntegration, error) {
	return NewMQTTIntegrationWithAuth(brokerURL, baseTopic, "", "")
}

// NewMQTTIntegrationWithAuth creates a new MQTT integration with authentication
func NewMQTTIntegrationWithAuth(brokerURL, baseTopic, username, password string) (*MQTTIntegration, error) {
	opts := mqtt.NewClientOptions()
	opts.AddBroker(brokerURL)
	opts.SetClientID("homesight")
	opts.SetAutoReconnect(true)
	opts.SetResumeSubs(true)    // Auto-resume subscriptions after reconnect
	opts.SetCleanSession(false) // Persist subscriptions across reconnects

	if username != "" {
		opts.SetUsername(username)
	}
	if password != "" {
		opts.SetPassword(password)
	}

	client := mqtt.NewClient(opts)
	if token := client.Connect(); token.Wait() && token.Error() != nil {
		return nil, fmt.Errorf("failed to connect to MQTT broker: %w", token.Error())
	}

	return &MQTTIntegration{
		client:    client,
		baseTopic: baseTopic,
		devices:   make(map[string]model.DeviceDescriptor),
	}, nil
}

// Discover finds MQTT devices
func (i *MQTTIntegration) Discover(ctx context.Context) ([]model.DeviceDescriptor, error) {
	i.mu.RLock()
	defer i.mu.RUnlock()

	devices := make([]model.DeviceDescriptor, 0, len(i.devices))
	for _, d := range i.devices {
		devices = append(devices, d)
	}
	return devices, nil
}

// GetClient returns the MQTT client for advanced usage (like discovery listeners)
func (i *MQTTIntegration) GetClient() mqtt.Client {
	return i.client
}

// Subscribe listens for MQTT device events
func (i *MQTTIntegration) Subscribe(ctx context.Context, events chan<- model.DeviceEvent) error {
	// Subscribe to general device topics
	topic := fmt.Sprintf("%s/+/+", i.baseTopic)

	handler := func(client mqtt.Client, msg mqtt.Message) {
		event, err := i.parseMessage(msg)
		if err != nil {
			return
		}

		select {
		case events <- event:
		case <-ctx.Done():
		}
	}

	if token := i.client.Subscribe(topic, 0, handler); token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to subscribe: %w", token.Error())
	}

	return nil
}

// parseMessage converts MQTT message to DeviceEvent
func (i *MQTTIntegration) parseMessage(msg mqtt.Message) (model.DeviceEvent, error) {
	var payload map[string]any
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		return model.DeviceEvent{}, err
	}

	deviceID, _ := payload["device_id"].(string)
	sensorID, _ := payload["sensor_id"].(string)
	value := payload["value"]

	return model.DeviceEvent{
		DeviceID:  deviceID,
		SensorID:  sensorID,
		Timestamp: time.Now(),
		ValueType: fmt.Sprintf("%T", value),
		Value:     value,
		Metadata:  make(map[string]string),
	}, nil
}

// Control sends a command to an MQTT device
func (i *MQTTIntegration) Control(ctx context.Context, cmd model.DeviceCommand) error {
	topic := fmt.Sprintf("%s/%s/set", i.baseTopic, cmd.DeviceID)
	payload, err := json.Marshal(cmd.Arguments)
	if err != nil {
		return err
	}

	token := i.client.Publish(topic, 0, false, payload)
	token.Wait()
	return token.Error()
}

// Close shuts down the MQTT integration
func (i *MQTTIntegration) Close() error {
	i.client.Disconnect(250)
	return nil
}
