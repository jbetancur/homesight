package discovery

import (
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

// MQTTDiscoveredDevice represents a device discovered via MQTT
type MQTTDiscoveredDevice struct {
	ID           string            `json:"id"`
	Name         string            `json:"name"`
	Type         string            `json:"type"`
	Integration  string            `json:"integration"`
	Manufacturer string            `json:"manufacturer,omitempty"`
	Model        string            `json:"model,omitempty"`
	Topics       []string          `json:"topics"`
	Metadata     map[string]string `json:"metadata,omitempty"`
	RawPayload   string            `json:"raw_payload,omitempty"`
	DiscoveredAt time.Time         `json:"discovered_at"`
}

// MQTTDiscoveryListener listens to MQTT topics and discovers devices
type MQTTDiscoveryListener struct {
	client        mqtt.Client
	devices       map[string]*MQTTDiscoveredDevice
	mutex         sync.RWMutex
	topicPatterns []string
}

// NewMQTTDiscoveryListener creates a new MQTT discovery listener
func NewMQTTDiscoveryListener(client mqtt.Client, topicPatterns []string) *MQTTDiscoveryListener {
	return &MQTTDiscoveryListener{
		client:        client,
		devices:       make(map[string]*MQTTDiscoveredDevice),
		topicPatterns: topicPatterns,
	}
}

// Start begins listening for discovery messages
func (l *MQTTDiscoveryListener) Start() error {
	for _, pattern := range l.topicPatterns {
		token := l.client.Subscribe(pattern, 0, l.handleMessage)
		if token.Wait() && token.Error() != nil {
			return fmt.Errorf("failed to subscribe to %s: %w", pattern, token.Error())
		}
	}
	return nil
}

// handleMessage processes incoming MQTT messages
func (l *MQTTDiscoveryListener) handleMessage(client mqtt.Client, msg mqtt.Message) {
	device := l.parseMessage(msg)
	if device != nil {
		l.mutex.Lock()
		l.devices[device.ID] = device
		l.mutex.Unlock()
	}
}

// parseMessage extracts device info from an MQTT message
// Supports multiple discovery formats (Home Assistant, Homie, Tasmota, etc.)
func (l *MQTTDiscoveryListener) parseMessage(msg mqtt.Message) *MQTTDiscoveredDevice {
	topic := msg.Topic()
	payload := msg.Payload()

	if len(payload) == 0 {
		return nil
	}

	var parser DeviceMessageParser
	if strings.Contains(topic, "homeassistant/") {
		parser = &HomeAssistantParser{}
	} else if strings.Contains(topic, "/homie/") || strings.HasPrefix(topic, "homie/") {
		parser = &HomieParser{}
	} else if strings.Contains(topic, "tasmota/discovery/") {
		parser = &TasmotaParser{}
	} else {
		var js map[string]interface{}
		if err := json.Unmarshal(payload, &js); err != nil {
			parser = &NonJSONParser{}
		} else {
			parser = &GenericParser{}
		}
	}

	device := parser.Parse(topic, payload)
	if device == nil {
		return nil
	}
	if device.ID == "" {
		device.ID = generateIDFromTopic(topic)
	}
	if device.Name == "" {
		device.Name = device.ID
	}
	return device
}

// parseHomieFormat parses Homie convention format

// GetDevices returns all discovered devices
func (l *MQTTDiscoveryListener) GetDevices() []*MQTTDiscoveredDevice {
	l.mutex.RLock()
	defer l.mutex.RUnlock()

	devices := make([]*MQTTDiscoveredDevice, 0, len(l.devices))
	for _, device := range l.devices {
		devices = append(devices, device)
	}
	return devices
}

// Clear removes all discovered devices
func (l *MQTTDiscoveryListener) Clear() {
	l.mutex.Lock()
	defer l.mutex.Unlock()
	l.devices = make(map[string]*MQTTDiscoveredDevice)
}

// generateIDFromTopic creates a unique ID from topic structure
func generateIDFromTopic(topic string) string {
	// Remove common prefixes and generate simple ID
	topic = strings.TrimPrefix(topic, "homeassistant/")
	topic = strings.TrimPrefix(topic, "homie/")
	topic = strings.TrimSuffix(topic, "/config")
	return strings.ReplaceAll(topic, "/", "_")
}
