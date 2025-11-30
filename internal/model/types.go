package model

import "time"

// DeviceDescriptor describes a discovered device
type DeviceDescriptor struct {
	ID           string            `json:"id"`
	Name         string            `json:"name"`
	Type         string            `json:"type"`        // "leak_sensor", "temp_sensor", "sump_pump", etc.
	Integration  string            `json:"integration"` // "matter", "zigbee", "mqtt", "lan"
	Capabilities []string          `json:"capabilities"`
	Metadata     map[string]string `json:"metadata"`
}

// DeviceEvent represents a normalized sensor event
type DeviceEvent struct {
	DeviceID  string            `json:"device_id"`
	SensorID  string            `json:"sensor_id"`
	Timestamp time.Time         `json:"timestamp"`
	ValueType string            `json:"value_type"` // "bool", "float", "string"
	Value     any               `json:"value"`
	Metadata  map[string]string `json:"metadata"`
}

// DeviceCommand represents a control command for a device
type DeviceCommand struct {
	DeviceID  string         `json:"device_id"`
	Command   string         `json:"command"`
	Arguments map[string]any `json:"arguments"`
}

// Device represents a physical or logical device
type Device struct {
	ID              string            `json:"id"`
	Name            string            `json:"name"`
	Type            string            `json:"type"`
	Integration     string            `json:"integration"`
	ZoneID          string            `json:"zone_id"`
	AssetID         string            `json:"asset_id"`
	Enabled         bool              `json:"enabled"`
	LastSeen        time.Time         `json:"last_seen"`
	Metadata        map[string]string `json:"metadata"`
	DocsIngested    bool              `json:"docs_ingested"`     // Whether documentation has been processed
	DocsIngestedAt  *time.Time        `json:"docs_ingested_at"`  // When documentation was last processed
	DocsStatus      string            `json:"docs_status"`       // pending/success/partial/error
	CreatedAt       time.Time         `json:"created_at"`
	UpdatedAt       time.Time         `json:"updated_at"`
}

// Sensor represents a sensor within a device
type Sensor struct {
	ID        string            `json:"id"`
	DeviceID  string            `json:"device_id"`
	Name      string            `json:"name"`
	Type      string            `json:"type"`
	Unit      string            `json:"unit"`
	Metadata  map[string]string `json:"metadata"`
	CreatedAt time.Time         `json:"created_at"`
	UpdatedAt time.Time         `json:"updated_at"`
}

// Home represents the top-level location
type Home struct {
	ID        string            `json:"id"`
	Name      string            `json:"name"`
	Address   string            `json:"address"`
	Metadata  map[string]string `json:"metadata"`
	CreatedAt time.Time         `json:"created_at"`
	UpdatedAt time.Time         `json:"updated_at"`
}

// Zone represents a logical area within a home
type Zone struct {
	ID        string            `json:"id"`
	HomeID    string            `json:"home_id"`
	Name      string            `json:"name"`
	Type      string            `json:"type"`      // "basement", "bathroom", "kitchen", etc.
	ParentID  string            `json:"parent_id"` // for nested zones
	Metadata  map[string]string `json:"metadata"`
	CreatedAt time.Time         `json:"created_at"`
	UpdatedAt time.Time         `json:"updated_at"`
}

// Asset represents a physical asset that may have sensors
type Asset struct {
	ID           string            `json:"id"`
	HomeID       string            `json:"home_id"`
	ZoneID       string            `json:"zone_id"`
	Name         string            `json:"name"`
	Type         string            `json:"type"` // "sump_pump", "water_heater", "hvac", etc.
	Manufacturer string            `json:"manufacturer"`
	Model        string            `json:"model"`
	InstallDate  time.Time         `json:"install_date"`
	Metadata     map[string]string `json:"metadata"`
	CreatedAt    time.Time         `json:"created_at"`
	UpdatedAt    time.Time         `json:"updated_at"`
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
	StatusOpen         IncidentStatus = "open"
	StatusAcknowledged IncidentStatus = "acknowledged"
	StatusResolved     IncidentStatus = "resolved"
)

// IncidentType represents the type of incident
type IncidentType string

const (
	IncidentTypeWaterLeak    IncidentType = "water_leak"
	IncidentTypeSmoke        IncidentType = "smoke_alarm"
	IncidentTypeCO           IncidentType = "co_alarm"
	IncidentTypeMotion       IncidentType = "motion_alarm"
	IncidentTypeContact      IncidentType = "contact_alarm"
	IncidentTypeTamper       IncidentType = "tamper_alarm"
	IncidentTypeHeat         IncidentType = "heat_alarm"
	IncidentTypePower        IncidentType = "power_alarm"
	IncidentTypeGlassBreak   IncidentType = "glass_break"
	IncidentTypeBurglar      IncidentType = "burglar_alarm"
	IncidentTypeFreeze       IncidentType = "freeze_alarm"
	IncidentTypeGeneric      IncidentType = "generic"
)

// Incident represents a detected issue or alert
type Incident struct {
	ID             string           `json:"id"`
	Type           IncidentType     `json:"type"`            // Type of incident (water_leak, smoke, etc.)
	Title          string           `json:"title"`
	Description    string           `json:"description"`
	Severity       IncidentSeverity `json:"severity"`
	Status         IncidentStatus   `json:"status"`
	DeviceID       string           `json:"device_id"`
	SensorID       string           `json:"sensor_id"`
	ZoneID         string           `json:"zone_id"`
	AssetID        string           `json:"asset_id"`
	RuleName       string           `json:"rule_name"`
	Data           map[string]any   `json:"data"`
	CreatedAt      time.Time        `json:"created_at"`
	UpdatedAt      time.Time        `json:"updated_at"`
	ResolvedAt     *time.Time       `json:"resolved_at"`
	// AI Analysis fields
	AnalysisStatus string           `json:"analysis_status"` // "pending", "completed", "failed"
	Analysis       string           `json:"analysis"`
	Insights       []string         `json:"insights"`
	Actions        []string         `json:"actions"`
	AnalysisData   map[string]any   `json:"analysis_data"`   // metadata, sources, etc.
	AnalyzedAt     *time.Time       `json:"analyzed_at"`
}

// Task represents a maintenance or action item
type Task struct {
	ID          string     `json:"id"`
	Title       string     `json:"title"`
	Description string     `json:"description"`
	Priority    string     `json:"priority"`
	Status      string     `json:"status"`
	AssetID     string     `json:"asset_id"`
	ZoneID      string     `json:"zone_id"`
	DueDate     *time.Time `json:"due_date"`
	CompletedAt *time.Time `json:"completed_at"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

// MetricPoint represents a time-series data point
type MetricPoint struct {
	Timestamp time.Time         `json:"timestamp"`
	Value     float64           `json:"value"`
	Labels    map[string]string `json:"labels"`
}
