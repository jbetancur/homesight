package discovery

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// HomeAssistantParser implements DeviceMessageParser for Home Assistant MQTT discovery

type HomeAssistantParser struct{}

func (p *HomeAssistantParser) Parse(topic string, payload []byte) *MQTTDiscoveredDevice {
	data := parseJSON(payload)
	device := &MQTTDiscoveredDevice{
		Topics:       []string{topic},
		RawPayload:   string(payload),
		Metadata:     make(map[string]string),
		DiscoveredAt: now(),
	}

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
	return device
}

// Helper to parse JSON payload
func parseJSON(payload []byte) map[string]interface{} {
	var data map[string]interface{}
	_ = json.Unmarshal(payload, &data)
	return data
}

// Helper to get current time
func now() time.Time {
	return time.Now()
}
