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
	payload := string(msg.Payload())

	// Empty payload means device was removed
	if len(payload) == 0 {
		return nil
	}

	var data map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &data); err != nil {
		// Not JSON, might be a simple value message
		return l.parseNonJSONMessage(topic, payload)
	}

	device := &MQTTDiscoveredDevice{
		Topics:       []string{topic},
		RawPayload:   payload,
		Metadata:     make(map[string]string),
		DiscoveredAt: time.Now(),
	}

	// Detect discovery format based on topic structure
	if strings.Contains(topic, "homeassistant/") {
		l.parseHomeAssistantFormat(topic, data, device)
	} else if strings.Contains(topic, "/homie/") || strings.HasPrefix(topic, "homie/") {
		l.parseHomieFormat(topic, data, device)
	} else if strings.Contains(topic, "tasmota/discovery/") {
		l.parseTasmotaFormat(topic, data, device)
	} else {
		l.parseGenericFormat(topic, data, device)
	}

	// Ensure we have at least an ID and name
	if device.ID == "" {
		device.ID = generateIDFromTopic(topic)
	}
	if device.Name == "" {
		device.Name = device.ID
	}

	return device
}

// parseHomeAssistantFormat parses Home Assistant MQTT discovery format
// Topic: homeassistant/<component>/<node_id>/<object_id>/config
func (l *MQTTDiscoveryListener) parseHomeAssistantFormat(topic string, data map[string]interface{}, device *MQTTDiscoveredDevice) {
	parts := strings.Split(topic, "/")
	if len(parts) >= 4 {
		device.Type = parts[1] // component (light, switch, sensor, etc.)
		device.Integration = "homeassistant"

		// Extract device info
		if deviceInfo, ok := data["device"].(map[string]interface{}); ok {
			if name, ok := deviceInfo["name"].(string); ok {
				device.Name = name
			}
			if mfr, ok := deviceInfo["manufacturer"].(string); ok {
				device.Manufacturer = mfr
			}
			if model, ok := deviceInfo["model"].(string); ok {
				device.Model = model
			}
			if ids, ok := deviceInfo["identifiers"].([]interface{}); ok && len(ids) > 0 {
				device.ID = fmt.Sprintf("%v", ids[0])
			}
		}

		// Extract entity name if no device name
		if device.Name == "" {
			if name, ok := data["name"].(string); ok {
				device.Name = name
			}
		}

		// Store useful metadata
		if stateTopic, ok := data["state_topic"].(string); ok {
			device.Metadata["state_topic"] = stateTopic
		}
		if cmdTopic, ok := data["command_topic"].(string); ok {
			device.Metadata["command_topic"] = cmdTopic
		}
	}
}

// parseHomieFormat parses Homie convention format
// Topic: homie/<device_id>/$homie or homie/<device_id>/$name
func (l *MQTTDiscoveryListener) parseHomieFormat(topic string, data map[string]interface{}, device *MQTTDiscoveredDevice) {
	parts := strings.Split(topic, "/")
	if len(parts) >= 2 {
		device.Integration = "homie"
		device.ID = parts[1]

		// Homie uses property-based discovery
		if strings.HasSuffix(topic, "/$name") {
			if name, ok := data["name"].(string); ok {
				device.Name = name
			}
		}
	}
}

// parseTasmotaFormat parses Tasmota discovery format
func (l *MQTTDiscoveryListener) parseTasmotaFormat(topic string, data map[string]interface{}, device *MQTTDiscoveredDevice) {
	device.Integration = "tasmota"
	device.Type = "switch"

	if hn, ok := data["hn"].(string); ok {
		device.Name = hn
		device.ID = hn
	}
	if mac, ok := data["mac"].(string); ok {
		device.Metadata["mac"] = mac
	}
	if model, ok := data["md"].(string); ok {
		device.Model = model
	}
}

// parseGenericFormat attempts to extract device info from unknown format
func (l *MQTTDiscoveryListener) parseGenericFormat(topic string, data map[string]interface{}, device *MQTTDiscoveredDevice) {
	device.Integration = "generic"

	// Try common field names
	for _, key := range []string{"name", "device_name", "friendly_name"} {
		if name, ok := data[key].(string); ok {
			device.Name = name
			break
		}
	}

	for _, key := range []string{"id", "device_id", "unique_id"} {
		if id, ok := data[key].(string); ok {
			device.ID = id
			break
		}
	}

	for _, key := range []string{"type", "device_type", "kind"} {
		if dtype, ok := data[key].(string); ok {
			device.Type = dtype
			break
		}
	}
}

// parseNonJSONMessage handles non-JSON messages (simple values)
func (l *MQTTDiscoveryListener) parseNonJSONMessage(topic, payload string) *MQTTDiscoveredDevice {
	// Could be a simple state message, skip for now
	return nil
}

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
