package discovery

type GenericParser struct{}

func (p *GenericParser) Parse(topic string, payload []byte) *MQTTDiscoveredDevice {
	data := parseJSON(payload)
	device := &MQTTDiscoveredDevice{
		Topics:       []string{topic},
		RawPayload:   string(payload),
		Metadata:     make(map[string]string),
		DiscoveredAt: now(),
		Integration:  "generic",
	}
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
	return device
}
