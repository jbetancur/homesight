package discovery

type TasmotaParser struct{}

func (p *TasmotaParser) Parse(topic string, payload []byte) *MQTTDiscoveredDevice {
	data := parseJSON(payload)
	device := &MQTTDiscoveredDevice{
		Topics:       []string{topic},
		RawPayload:   string(payload),
		Metadata:     make(map[string]string),
		DiscoveredAt: now(),
		Integration:  "tasmota",
		Type:         "switch",
	}
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
	return device
}
