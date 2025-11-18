package discovery

type NonJSONParser struct{}

func (p *NonJSONParser) Parse(topic string, payload []byte) *MQTTDiscoveredDevice {
	// Could be a simple state message, skip for now
	return nil
}
