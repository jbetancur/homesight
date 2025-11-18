package discovery

// DeviceMessageParser defines the interface for device message parsers
// Each parser should implement Parse and return a normalized device struct
// The input is the MQTT topic and payload

type DeviceMessageParser interface {
	Parse(topic string, payload []byte) *MQTTDiscoveredDevice
}
