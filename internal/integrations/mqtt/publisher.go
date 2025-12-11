package mqtt

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/homesight/homesight/internal/model"
)

// Publisher publishes commands to MQTT for integrations to consume
type Publisher struct {
	client mqtt.Client
}

// NewPublisher creates a new MQTT command publisher
func NewPublisher(brokerURL string, clientID string) (*Publisher, error) {
	opts := mqtt.NewClientOptions().
		AddBroker(brokerURL).
		SetClientID(clientID).
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second)

	client := mqtt.NewClient(opts)

	log.Println("[MQTT-PUBLISHER] Connecting to MQTT broker...")
	token := client.Connect()

	// Wait with timeout to avoid blocking indefinitely
	if !token.WaitTimeout(5 * time.Second) {
		log.Println("[MQTT-PUBLISHER] Warning: MQTT broker connection timeout - will retry in background")
		// Don't return error - let auto-reconnect handle it
		return &Publisher{client: client}, nil
	}

	if token.Error() != nil {
		log.Printf("[MQTT-PUBLISHER] Warning: Failed to connect to MQTT broker: %v - will retry in background", token.Error())
		// Don't return error - let auto-reconnect handle it
		return &Publisher{client: client}, nil
	}

	log.Println("[MQTT-PUBLISHER] Connected to MQTT broker")

	return &Publisher{
		client: client,
	}, nil
}

// PublishCommand publishes a device command to MQTT
func (p *Publisher) PublishCommand(cmd model.DeviceCommand) error {
	topic := fmt.Sprintf("homesight/cmd/%s", cmd.DeviceID)

	msg := CommandMessage{
		Command:   cmd.Command,
		Arguments: cmd.Arguments,
	}

	payload, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal command: %w", err)
	}

	log.Printf("[MQTT-PUBLISHER] Publishing command to %s: %s", topic, cmd.Command)

	token := p.client.Publish(topic, 0, false, payload)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish command: %w", token.Error())
	}

	return nil
}

// PublishDiscovery publishes a device discovery message (for testing)
func (p *Publisher) PublishDiscovery(integration, deviceID string, msg DiscoveryMessage) error {
	topic := fmt.Sprintf("homesight/%s/%s/discovery", integration, deviceID)

	payload, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal discovery: %w", err)
	}

	log.Printf("[MQTT-PUBLISHER] Publishing discovery to %s", topic)

	token := p.client.Publish(topic, 0, true, payload) // retained
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish discovery: %w", token.Error())
	}

	return nil
}

// PublishState publishes a device state update (for testing)
func (p *Publisher) PublishState(integration, deviceID string, values map[string]interface{}) error {
	topic := fmt.Sprintf("homesight/%s/%s/state", integration, deviceID)

	msg := StateMessage{
		Timestamp: time.Now(),
		Values:    values,
	}

	payload, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal state: %w", err)
	}

	log.Printf("[MQTT-PUBLISHER] Publishing state to %s", topic)

	token := p.client.Publish(topic, 0, false, payload)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish state: %w", token.Error())
	}

	return nil
}

// Publish publishes raw bytes to a topic
func (p *Publisher) Publish(topic string, payload []byte) error {
	log.Printf("[MQTT-PUBLISHER] Publishing to %s", topic)

	token := p.client.Publish(topic, 0, false, payload)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish: %w", token.Error())
	}

	return nil
}

// Close shuts down the publisher
func (p *Publisher) Close() error {
	p.client.Disconnect(250)
	return nil
}
