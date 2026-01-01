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
	// Core Identity
	ID           string `json:"id"`
	Name         string `json:"name"`                   // Original device name from integration
	DisplayName  string `json:"display_name,omitempty"` // User-defined friendly name
	Type         string `json:"type"`
	Integration  string `json:"integration"`
	Manufacturer string `json:"manufacturer,omitempty"`
	Model        string `json:"model,omitempty"`

	// Placement
	ZoneID  string `json:"zone_id"`
	AssetID string `json:"asset_id"`

	// Status
	Enabled  bool      `json:"enabled"`
	LastSeen time.Time `json:"last_seen"`

	// Unified Data Contract
	Readings     *DeviceReadings     `json:"readings,omitempty"`     // Sensor values
	Controls     *DeviceControls     `json:"controls,omitempty"`     // Control capabilities
	Battery      *DeviceBattery      `json:"battery,omitempty"`      // Battery info
	Connectivity *DeviceConnectivity `json:"connectivity,omitempty"` // Connection status
	Entities     []DeviceEntity      `json:"entities,omitempty"`     // Entities (Z-Wave, etc.)

	// Raw Integration Data (preserved for debugging and advanced use)
	RawData map[string]interface{} `json:"raw_data,omitempty"`

	// Documentation
	DocsIngested   bool       `json:"docs_ingested"`    // Whether documentation has been processed
	DocsIngestedAt *time.Time `json:"docs_ingested_at"` // When documentation was last processed
	DocsStatus     string     `json:"docs_status"`      // pending/success/partial/error

	// Timestamps
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// GetDisplayName returns the display name if set, otherwise the original name
func (d *Device) GetDisplayName() string {
	if d.DisplayName != "" {
		return d.DisplayName
	}
	return d.Name
}

// DeviceReadings contains normalized sensor values
type DeviceReadings struct {
	// Temperature (always in °F for consistency)
	TemperatureF *float64 `json:"temperature_f,omitempty"`

	// Humidity (0-100%)
	Humidity *float64 `json:"humidity,omitempty"`

	// Binary sensors (true = detected/triggered)
	Water   *bool `json:"water,omitempty"`   // Water leak
	Motion  *bool `json:"motion,omitempty"`  // Motion detected
	Contact *bool `json:"contact,omitempty"` // Door/window open
	Tamper  *bool `json:"tamper,omitempty"`  // Tamper detected
	Smoke   *bool `json:"smoke,omitempty"`   // Smoke detected
	CO      *bool `json:"co,omitempty"`      // Carbon monoxide detected

	// Power/Energy
	PowerW    *float64 `json:"power_w,omitempty"`    // Current power (watts)
	EnergyKWh *float64 `json:"energy_kwh,omitempty"` // Total energy (kilowatt-hours)
	VoltageV  *float64 `json:"voltage_v,omitempty"`  // Voltage
	CurrentA  *float64 `json:"current_a,omitempty"`  // Current (amps)

	// Light level
	Illuminance *float64 `json:"illuminance,omitempty"` // Lux

	// Air quality
	CO2  *float64 `json:"co2,omitempty"`  // CO2 (ppm)
	VOC  *float64 `json:"voc,omitempty"`  // VOC (ppb)
	PM25 *float64 `json:"pm25,omitempty"` // PM2.5 (µg/m³)

	// Other
	Pressure *float64 `json:"pressure,omitempty"` // Atmospheric pressure (hPa)
	UVIndex  *float64 `json:"uv_index,omitempty"` // UV index
}

// DeviceControls contains available control capabilities and current state
type DeviceControls struct {
	// Binary switch (on/off)
	Switch *SwitchControl `json:"switch,omitempty"`

	// Multilevel (dimmer, blinds, etc.)
	Level *LevelControl `json:"level,omitempty"`

	// Color control (RGB lights)
	Color *ColorControl `json:"color,omitempty"`

	// Thermostat
	Thermostat *ThermostatControl `json:"thermostat,omitempty"`

	// Lock
	Lock *LockControl `json:"lock,omitempty"`
}

// SwitchControl represents a binary switch
type SwitchControl struct {
	Value    bool `json:"value"`    // Current state
	Settable bool `json:"settable"` // Can be controlled
}

// LevelControl represents a multilevel control (dimmer, blinds, etc.)
type LevelControl struct {
	Value    int  `json:"value"` // 0-100
	Settable bool `json:"settable"`
	Min      int  `json:"min"`
	Max      int  `json:"max"`
}

// ColorControl represents RGB color control
type ColorControl struct {
	R        int  `json:"r"` // 0-255
	G        int  `json:"g"` // 0-255
	B        int  `json:"b"` // 0-255
	Settable bool `json:"settable"`
}

// ThermostatControl represents thermostat control
type ThermostatControl struct {
	Mode           string   `json:"mode"`                    // "heat", "cool", "auto", "off"
	SetpointHeat   *float64 `json:"setpoint_heat,omitempty"` // Target temp (heat)
	SetpointCool   *float64 `json:"setpoint_cool,omitempty"` // Target temp (cool)
	Settable       bool     `json:"settable"`
	AvailableModes []string `json:"available_modes,omitempty"`
}

// LockControl represents lock control
type LockControl struct {
	Locked   bool `json:"locked"`
	Settable bool `json:"settable"`
}

// DeviceBattery contains battery information
type DeviceBattery struct {
	Level      int  `json:"level"`       // 0-100 percentage
	IsLow      bool `json:"is_low"`      // True if < 20%
	IsCharging bool `json:"is_charging"` // True if charging
}

// DeviceConnectivity contains connection information
type DeviceConnectivity struct {
	Online         bool      `json:"online"`
	SignalStrength *int      `json:"signal_strength,omitempty"` // RSSI or percentage
	LastSeen       time.Time `json:"last_seen"`
	FirmwareVer    string    `json:"firmware_version,omitempty"`
}

// EntityType represents the type of entity
type EntityType string

const (
	EntityTypeSensor       EntityType = "sensor"
	EntityTypeBinarySensor EntityType = "binary_sensor"
	EntityTypeSwitch       EntityType = "switch"
	EntityTypeNumber       EntityType = "number"
	EntityTypeAlarm        EntityType = "alarm"
	EntityTypeDiagnostic   EntityType = "diagnostic"
	EntityTypeConfig       EntityType = "config"
)

// DeviceEntity represents a controllable entity (Z-Wave, etc.)
type DeviceEntity struct {
	ID         string                 `json:"id"`
	DeviceID   string                 `json:"device_id,omitempty"`
	Name       string                 `json:"name,omitempty"`
	Type       string                 `json:"type,omitempty"`
	EntityType EntityType             `json:"entity_type,omitempty"`
	Category   string                 `json:"category,omitempty"`
	Value      interface{}            `json:"value,omitempty"`
	Unit       string                 `json:"unit,omitempty"`
	Settable   bool                   `json:"settable"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
	UpdatedAt  time.Time              `json:"updated_at,omitempty"`
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

// Zone represents a logical area within a home
type Zone struct {
	ID         string                 `json:"id"`
	HomeID     string                 `json:"home_id"`
	Name       string                 `json:"name"`
	Type       string                 `json:"type"`       // "basement", "bathroom", "kitchen", etc.
	ParentID   string                 `json:"parent_id"`  // for nested zones
	Attributes map[string]interface{} `json:"attributes"` // Dynamic attributes from attribute definitions
	Hidden     bool                   `json:"hidden"`     // Whether zone is hidden from UI
	Metadata   map[string]string      `json:"metadata"`
	CreatedAt  time.Time              `json:"created_at"`
	UpdatedAt  time.Time              `json:"updated_at"`
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
	StatusIgnored      IncidentStatus = "ignored" // Dismissed as false positive or not actionable
)

// IncidentType represents the type of incident
type IncidentType string

const (
	IncidentTypeWaterLeak  IncidentType = "water_leak"
	IncidentTypeSmoke      IncidentType = "smoke_alarm"
	IncidentTypeCO         IncidentType = "co_alarm"
	IncidentTypeMotion     IncidentType = "motion_alarm"
	IncidentTypeContact    IncidentType = "contact_alarm"
	IncidentTypeTamper     IncidentType = "tamper_alarm"
	IncidentTypeHeat       IncidentType = "heat_alarm"
	IncidentTypePower      IncidentType = "power_alarm"
	IncidentTypeGlassBreak IncidentType = "glass_break"
	IncidentTypeBurglar    IncidentType = "burglar_alarm"
	IncidentTypeFreeze     IncidentType = "freeze_alarm"
	IncidentTypeGeneric    IncidentType = "generic"
)

// Incident represents a detected issue or alert
type Incident struct {
	ID          string           `json:"id"`
	Type        IncidentType     `json:"type"` // Type of incident (water_leak, smoke, etc.)
	Title       string           `json:"title"`
	Description string           `json:"description"`
	Severity    IncidentSeverity `json:"severity"`
	Status      IncidentStatus   `json:"status"`
	DeviceID    string           `json:"device_id"`
	SensorID    string           `json:"sensor_id"`
	ZoneID      string           `json:"zone_id"`
	AssetID     string           `json:"asset_id"`
	RuleName    string           `json:"rule_name"`
	Data        map[string]any   `json:"data"`
	CreatedAt   time.Time        `json:"created_at"`
	UpdatedAt   time.Time        `json:"updated_at"`
	ResolvedAt  *time.Time       `json:"resolved_at"`
	// Status change tracking
	AcknowledgedAt *time.Time `json:"acknowledged_at,omitempty"` // When user acknowledged the incident
	IgnoredAt      *time.Time `json:"ignored_at,omitempty"`      // When user dismissed/ignored the incident
	Notes          string     `json:"notes,omitempty"`           // User notes on status change
	// AI Analysis fields
	AnalysisStatus string         `json:"analysis_status"` // "pending", "completed", "failed"
	Analysis       string         `json:"analysis"`
	Insights       []string       `json:"insights"`
	Actions        []string       `json:"actions"`
	AnalysisData   map[string]any `json:"analysis_data"` // metadata, sources, etc.
	AnalyzedAt     *time.Time     `json:"analyzed_at"`
}

// MetricPoint represents a time-series data point
type MetricPoint struct {
	Timestamp time.Time         `json:"timestamp"`
	Value     float64           `json:"value"`
	Labels    map[string]string `json:"labels"`
}
