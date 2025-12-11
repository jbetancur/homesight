package api

import (
	"encoding/json"
	"net/http"
)

// SystemPreferences represents user-configurable system preferences
type SystemPreferences struct {
	TemperatureUnit string `json:"temperature_unit"` // "celsius" or "fahrenheit"
	Timezone        string `json:"timezone"`
}

// handleGetSystemPreferences returns system-wide preferences
// GET /api/system/preferences
func (s *Server) handleGetSystemPreferences(w http.ResponseWriter, r *http.Request) {
	prefs := SystemPreferences{
		TemperatureUnit: s.cfg.System.TemperatureUnit,
		Timezone:        s.cfg.System.Timezone,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(prefs)
}
