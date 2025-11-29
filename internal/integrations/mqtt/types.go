package mqtt

import "time"

// DiscoveryMessage represents a device discovery message
type DiscoveryMessage struct {
	DeviceID     string   `json:"device_id"`
	Integration  string   `json:"integration"`
	Name         string   `json:"name,omitempty"`
	Manufacturer string   `json:"manufacturer,omitempty"`
	Model        string   `json:"model,omitempty"`
	HwID         string   `json:"hw_id,omitempty"`
	Capabilities []string `json:"capabilities"`
}

// RemovedMessage represents a device removal message
type RemovedMessage struct {
	DeviceID    string `json:"device_id"`
	Integration string `json:"integration"`
	Reason      string `json:"reason,omitempty"`
}

// MetadataMessage represents device metadata updates
type MetadataMessage struct {
	DeviceID string            `json:"device_id"`
	ZoneID   string            `json:"zone_id,omitempty"`
	AssetID  string            `json:"asset_id,omitempty"`
	Enabled  *bool             `json:"enabled,omitempty"`
	Metadata map[string]string `json:"metadata,omitempty"`
}

// StateMessage represents device state updates
type StateMessage struct {
	Timestamp time.Time              `json:"ts"`
	Values    map[string]interface{} `json:"values"`
}

// AttributeMessage represents a single attribute update
type AttributeMessage struct {
	Timestamp time.Time   `json:"ts"`
	Value     interface{} `json:"value"`
	Unit      string      `json:"unit,omitempty"`
}

// CommandMessage represents a device command
type CommandMessage struct {
	Command   string                 `json:"command"`
	Arguments map[string]interface{} `json:"args,omitempty"`
}

// IncidentMessage represents an incident
type IncidentMessage struct {
	IncidentID   string                 `json:"incident_id"`
	DeviceID     string                 `json:"device_id"`
	Title        string                 `json:"title"`
	Description  string                 `json:"description"`
	Severity     string                 `json:"severity"`
	IncidentType string                 `json:"incident_type,omitempty"`
	Timestamp    time.Time              `json:"ts"`
	Data         map[string]interface{} `json:"data,omitempty"`
}
