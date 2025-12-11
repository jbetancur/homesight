package model

import "time"

// HomeProfile contains detailed home construction and system information
// This helps AI provide better contextual recommendations
type HomeProfile struct {
	ID         string `json:"id"`
	HomeID     string `json:"home_id"`
	YearBuilt  int    `json:"year_built,omitempty"`
	SquareFeet int    `json:"square_feet,omitempty"`
	Stories    int    `json:"stories,omitempty"`

	// Construction
	FoundationType string `json:"foundation_type,omitempty"` // slab, crawlspace, basement, pier
	RoofType       string `json:"roof_type,omitempty"`       // shingle, metal, tile, flat
	RoofAge        int    `json:"roof_age,omitempty"`        // years
	SidingType     string `json:"siding_type,omitempty"`     // vinyl, brick, wood, stucco
	WindowType     string `json:"window_type,omitempty"`     // single-pane, double-pane, triple-pane
	Insulation     string `json:"insulation,omitempty"`      // poor, average, good, excellent

	// HVAC Systems
	HVACType           string `json:"hvac_type,omitempty"`            // central, mini-split, radiant, heat-pump, geothermal
	HVACAge            int    `json:"hvac_age,omitempty"`             // years
	HasAC              bool   `json:"has_ac,omitempty"`
	ACType             string `json:"ac_type,omitempty"`              // central, window, mini-split
	HeatingType        string `json:"heating_type,omitempty"`         // gas, electric, oil, heat-pump, wood, propane
	HeatingSystemType  string `json:"heating_system_type,omitempty"`  // forced-air, steam, hot-water, radiant-floor, baseboard, heat-pump
	ThermostatType     string `json:"thermostat_type,omitempty"`      // manual, programmable, smart
	HasHumidifier   bool   `json:"has_humidifier,omitempty"`
	HasDehumidifier bool   `json:"has_dehumidifier,omitempty"`
	HasAirPurifier  bool   `json:"has_air_purifier,omitempty"`

	// Water/Plumbing
	WaterHeaterType string `json:"water_heater_type,omitempty"` // tank, tankless, heat-pump, solar
	WaterHeaterAge  int    `json:"water_heater_age,omitempty"`  // years
	WaterHeaterFuel string `json:"water_heater_fuel,omitempty"` // gas, electric, propane
	HasWellWater    bool   `json:"has_well_water,omitempty"`
	HasSewerSystem  bool   `json:"has_sewer_system,omitempty"`
	HasSepticSystem bool   `json:"has_septic_system,omitempty"`
	HasSumpPump     bool   `json:"has_sump_pump,omitempty"`

	// Electrical
	ElectricalPanel    string `json:"electrical_panel,omitempty"` // 100A, 200A, 400A
	HasGeneratorBackup bool   `json:"has_generator_backup,omitempty"`
	HasSolarPanels     bool   `json:"has_solar_panels,omitempty"`
	HasBatteryBackup   bool   `json:"has_battery_backup,omitempty"`

	// Security & Safety
	HasSecuritySystem bool `json:"has_security_system,omitempty"`
	HasFireAlarms     bool `json:"has_fire_alarms,omitempty"`
	HasCOAlarms       bool `json:"has_co_alarms,omitempty"`
	HasSprinklers     bool `json:"has_sprinklers,omitempty"`

	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// AttributeFieldType defines the type of an attribute field
type AttributeFieldType string

const (
	FieldTypeText        AttributeFieldType = "text"
	FieldTypeNumber      AttributeFieldType = "number"
	FieldTypeBoolean     AttributeFieldType = "boolean"
	FieldTypeSelect      AttributeFieldType = "select"
	FieldTypeMultiSelect AttributeFieldType = "multiselect"
	FieldTypeTags        AttributeFieldType = "tags"
)

// AttributeScope defines where an attribute can be applied
type AttributeScope string

const (
	ScopeHome AttributeScope = "home"
	ScopeZone AttributeScope = "zone"
)

// AttributeDefinition defines a custom attribute that can be added by users
type AttributeDefinition struct {
	ID           string             `json:"id"`
	Name         string             `json:"name"`              // e.g., "has_pool"
	Label        string             `json:"label"`             // e.g., "Has Swimming Pool"
	Type         AttributeFieldType `json:"type"`              // text, number, boolean, select, etc.
	Scope        AttributeScope     `json:"scope"`             // home or zone
	Category     string             `json:"category"`          // for grouping in UI
	Description  string             `json:"description"`       // help text
	Options      []string           `json:"options,omitempty"` // for select/multiselect
	DefaultValue string             `json:"default_value,omitempty"`
	Required     bool               `json:"required"`
	CreatedAt    time.Time          `json:"created_at"`
	UpdatedAt    time.Time          `json:"updated_at"`
}
