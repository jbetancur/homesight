package zwave

import "time"

// ZWaveNode represents a Z-Wave device node
type ZWaveNode struct {
	NodeID           int                    `json:"nodeId"`
	Status           int                    `json:"status"`
	Ready            bool                   `json:"ready"`
	ManufacturerID   int                    `json:"manufacturerId"`
	ProductType      int                    `json:"productType"`
	ProductID        int                    `json:"productId"`
	FirmwareVersion  string                 `json:"firmwareVersion"`
	Security         string                 `json:"security"`         // "S2_Authenticated", "S0_Legacy", etc.
	InterviewStage   int                    `json:"interviewStage"`   // Numeric stage: 0-5+
	IsListening      bool                   `json:"isListening"`
	IsFrequentListening bool                `json:"isFrequentListening"`
	SupportsBeaming  bool                   `json:"supportsBeaming"`
	CommandClasses   map[int]CommandClass   `json:"commandClasses"`
	Values           interface{}            `json:"values"` // Can be array or map depending on context
	DeviceConfig     DeviceConfig           `json:"deviceConfig"`
}

// DeviceConfig contains device metadata from Z-Wave JS device database
type DeviceConfig struct {
	Manufacturer string `json:"manufacturer"`
	Label        string `json:"label"`        // Product name
	Description  string `json:"description"`
	Comments     string `json:"comments"`
}

// CommandClass represents a Z-Wave command class
type CommandClass struct {
	ID       int    `json:"id"`
	Name     string `json:"name"`
	Version  int    `json:"version"`
	IsSecure bool   `json:"isSecure"`
}

// ValueID identifies a specific value in a Z-Wave node
type ValueID struct {
	CommandClass int         `json:"commandClass"`
	Property     string      `json:"property"`
	PropertyKey  interface{} `json:"propertyKey,omitempty"`
	Endpoint     int         `json:"endpoint,omitempty"`
}

// ValueMetadata contains metadata about a Z-Wave value
type ValueMetadata struct {
	Type        string      `json:"type"`        // "number", "boolean", "string", etc.
	Readable    bool        `json:"readable"`
	Writeable   bool        `json:"writeable"`
	Label       string      `json:"label"`
	Description string      `json:"description"`
	Unit        string      `json:"unit,omitempty"`
	Min         interface{} `json:"min,omitempty"`
	Max         interface{} `json:"max,omitempty"`
	States      map[int]string `json:"states,omitempty"`  // For enum values
}

// Event types from Z-Wave JS
const (
	EventDriverReady      = "driver ready"
	EventNodeAdded        = "node added"
	EventNodeRemoved      = "node removed"
	EventNodeReady        = "node ready"
	EventNodeInterview    = "node interview stage complete"
	EventValueUpdated     = "value updated"
	EventValueAdded       = "value added"
	EventValueRemoved     = "value removed"
	EventNotification     = "notification"
	EventNodeDead         = "node dead"
	EventNodeAlive        = "node alive"
	EventNodeWakeUp       = "node wake up"
	EventNodeSleep        = "node sleep"
	EventInclusionStarted = "inclusion started"
	EventInclusionFailed  = "inclusion failed"
	EventInclusionStopped = "inclusion stopped"
	EventExclusionStarted = "exclusion started"
	EventExclusionFailed  = "exclusion failed"
	EventExclusionStopped = "exclusion stopped"
)

// ValueUpdatedEvent represents a value change event
type ValueUpdatedEvent struct {
	NodeID        int         `json:"nodeId"`
	Args          ValueChange `json:"args"`
}

// ValueChange contains the changed value details
type ValueChange struct {
	CommandClass  int         `json:"commandClass"`
	Property      string      `json:"property"`
	PropertyKey   interface{} `json:"propertyKey,omitempty"`
	Endpoint      int         `json:"endpoint,omitempty"`
	NewValue      interface{} `json:"newValue"`
	PrevValue     interface{} `json:"prevValue,omitempty"`
	PropertyName  string      `json:"propertyName,omitempty"`
}

// NotificationEvent represents a notification (alarm) event
type NotificationEvent struct {
	NodeID int                    `json:"nodeId"`
	Args   NotificationArgs       `json:"args"`
}

// NotificationArgs contains notification details
type NotificationArgs struct {
	CommandClass     int         `json:"commandClass"`
	Type             int         `json:"type"`             // Notification type (e.g., 5 = Water)
	Event            int         `json:"event"`            // Event code (e.g., 1 = Leak detected)
	Label            string      `json:"label"`
	EventLabel       string      `json:"eventLabel"`
	Parameters       interface{} `json:"parameters,omitempty"`
}

// NodeAddedEvent represents a new node being added
type NodeAddedEvent struct {
	NodeID int       `json:"nodeId"`
}

// NodeReadyEvent represents a node completing interview
type NodeReadyEvent struct {
	NodeID     int       `json:"nodeId"`
	NodeInfo   *ZWaveNode `json:"nodeInfo"`
}

// InclusionOptions configures device inclusion behavior
type InclusionOptions struct {
	Strategy      string        // "Default", "Security_S2", "Security_S0", "Insecure"
	ForceSecurity bool          // Force security even if not supported
	Timeout       time.Duration // How long to wait for device
}

// Command Class IDs (from Z-Wave specification)
const (
	CC_BASIC                = 0x20
	CC_SWITCH_BINARY        = 0x25
	CC_SWITCH_MULTILEVEL    = 0x26
	CC_SENSOR_BINARY        = 0x30
	CC_SENSOR_MULTILEVEL    = 0x31
	CC_METER                = 0x32
	CC_COLOR_SWITCH         = 0x33
	CC_CONFIGURATION        = 0x70
	CC_NOTIFICATION          = 0x71
	CC_MANUFACTURER_SPECIFIC = 0x72
	CC_BATTERY              = 0x80
	CC_WAKE_UP              = 0x84
	CC_ASSOCIATION          = 0x85
	CC_VERSION              = 0x86
	CC_INDICATOR            = 0x87
)

// Notification types (Command Class 0x71)
const (
	NOTIFICATION_SMOKE      = 1
	NOTIFICATION_CO         = 2
	NOTIFICATION_CO2        = 3
	NOTIFICATION_HEAT       = 4
	NOTIFICATION_WATER      = 5
	NOTIFICATION_ACCESS     = 6
	NOTIFICATION_BURGLAR    = 7
	NOTIFICATION_POWER      = 8
	NOTIFICATION_SYSTEM     = 9
	NOTIFICATION_EMERGENCY  = 10
	NOTIFICATION_CLOCK      = 11
	NOTIFICATION_APPLIANCE  = 12
	NOTIFICATION_HOME_HEALTH = 13
	NOTIFICATION_SIREN      = 14
)

// Water notification events
const (
	WATER_LEAK_DETECTED          = 1
	WATER_LEAK_DETECTED_UNKNOWN  = 2
	WATER_LEVEL_DROPPED          = 3
	WATER_REPLACE_FILTER         = 4
	WATER_FLOW_ALARM             = 5
	WATER_PRESSURE_ALARM         = 6
	WATER_TEMPERATURE_ALARM      = 7
	WATER_LEVEL_ALARM            = 8
	WATER_PUMP_ALARM             = 9
	WATER_QUALITY_ALARM          = 10
	WATER_LEAK_ALARM_THRESHOLD   = 11
	WATER_EVENT_CLEARED          = 0
)
