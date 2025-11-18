package discovery

import (
	"strings"
)

type HomieParser struct{}

func (p *HomieParser) Parse(topic string, payload []byte) *MQTTDiscoveredDevice {
	data := parseJSON(payload)
	device := &MQTTDiscoveredDevice{
		Topics:       []string{topic},
		RawPayload:   string(payload),
		Metadata:     make(map[string]string),
		DiscoveredAt: now(),
	}
	parts := strings.Split(topic, "/")
	if len(parts) >= 2 {
		device.Integration = "homie"
		device.ID = parts[1]
		if strings.HasSuffix(topic, "/$name") {
			if name, ok := data["name"].(string); ok {
				device.Name = name
			}
		}
	}
	return device
}
