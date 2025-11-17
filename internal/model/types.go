package model

import "time"

// DeviceDescriptor describes a discovered device
type DeviceDescriptor struct {
	ID           string
	Name         string
	Type         string // "leak_sensor", "temp_sensor", "sump_pump", etc.
	Integration  string // "matter", "zigbee", "mqtt", "lan"
	Capabilities []string
	Metadata     map[string]string
}

// DeviceEvent represents a normalized sensor event
type DeviceEvent struct {
	DeviceID  string
	SensorID  string
	Timestamp time.Time
	ValueType string // "bool", "float", "string"
	Value     any
	Metadata  map[string]string
}

// DeviceCommand represents a control command for a device
type DeviceCommand struct {
	DeviceID  string
	Command   string
	Arguments map[string]any
}

// Device represents a physical or logical device
type Device struct {
	ID           string
	Name         string
	Type         string
	Integration  string
	ZoneID       string
	AssetID      string
	Enabled      bool
	LastSeen     time.Time
	Metadata     map[string]string
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

// Sensor represents a sensor within a device
type Sensor struct {
	ID        string
	DeviceID  string
	Name      string
	Type      string
	Unit      string
	Metadata  map[string]string
	CreatedAt time.Time
	UpdatedAt time.Time
}

// Home represents the top-level location
type Home struct {
	ID        string
	Name      string
	Address   string
	Metadata  map[string]string
	CreatedAt time.Time
	UpdatedAt time.Time
}

// Zone represents a logical area within a home
type Zone struct {
	ID        string
	HomeID    string
	Name      string
	Type      string // "basement", "bathroom", "kitchen", etc.
	ParentID  string // for nested zones
	Metadata  map[string]string
	CreatedAt time.Time
	UpdatedAt time.Time
}

// Asset represents a physical asset that may have sensors
type Asset struct {
	ID          string
	HomeID      string
	ZoneID      string
	Name        string
	Type        string // "sump_pump", "water_heater", "hvac", etc.
	Manufacturer string
	Model       string
	InstallDate time.Time
	Metadata    map[string]string
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// IncidentSeverity levels
type IncidentSeverity string

const (
	SeverityCritical IncidentSeverity = "critical"
	SeverityHigh     IncidentSeverity = "high"
	SeverityMedium   IncidentSeverity = "medium"
	SeverityLow      IncidentSeverity = "low"
	SeverityInfo     IncidentSeverity = "info"
)

// IncidentStatus states
type IncidentStatus string

const (
	StatusOpen       IncidentStatus = "open"
	StatusAcknowledged IncidentStatus = "acknowledged"
	StatusResolved   IncidentStatus = "resolved"
)

// Incident represents a detected issue or alert
type Incident struct {
	ID          string
	Title       string
	Description string
	Severity    IncidentSeverity
	Status      IncidentStatus
	DeviceID    string
	SensorID    string
	ZoneID      string
	AssetID     string
	RuleName    string
	Data        map[string]any
	CreatedAt   time.Time
	UpdatedAt   time.Time
	ResolvedAt  *time.Time
}

// Task represents a maintenance or action item
type Task struct {
	ID          string
	Title       string
	Description string
	Priority    string
	Status      string
	AssetID     string
	ZoneID      string
	DueDate     *time.Time
	CompletedAt *time.Time
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// MetricPoint represents a time-series data point
type MetricPoint struct {
	Timestamp time.Time
	Value     float64
	Labels    map[string]string
}
