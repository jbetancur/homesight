package api

import (
	"encoding/json"
	"net/http"

	"github.com/homesight/homesight/internal/timezone"
)

// TimezoneInfo represents timezone information
type TimezoneInfo struct {
	Name     string   `json:"name"`
	Detected bool     `json:"detected"`
	Offset   string   `json:"offset"`
	Local    string   `json:"local_time"`
	Options  []string `json:"options"`
}

// handleGetTimezone returns the current timezone configuration
func (s *Server) handleGetTimezone(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	tzSvc := s.timezoneService
	if tzSvc == nil {
		http.Error(w, "Timezone service not initialized", http.StatusInternalServerError)
		return
	}

	now := tzSvc.Now()
	_, offset := now.Zone()
	offsetHours := offset / 3600
	offsetMins := (offset % 3600) / 60

	info := TimezoneInfo{
		Name:     tzSvc.GetName(),
		Detected: s.cfg.System.Timezone == "" || s.cfg.System.Timezone == "auto",
		Offset:   formatOffset(offsetHours, offsetMins),
		Local:    now.Format("2006-01-02 15:04:05 MST"),
		Options:  timezone.ListCommonTimezones(),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(info)
}

// handleSetTimezone updates the timezone configuration
func (s *Server) handleSetTimezone(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		Timezone string `json:"timezone"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate timezone
	if err := timezone.ValidateTimezone(req.Timezone); err != nil {
		http.Error(w, "Invalid timezone: "+err.Error(), http.StatusBadRequest)
		return
	}

	// Create new timezone service
	tzSvc, err := timezone.NewService(req.Timezone, s.cfg.Weather.ZipCode)
	if err != nil {
		http.Error(w, "Failed to set timezone: "+err.Error(), http.StatusInternalServerError)
		return
	}

	s.timezoneService = tzSvc
	s.cfg.System.Timezone = req.Timezone

	// TODO: Persist to config file
	// For now, this change is in-memory only

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":   "success",
		"timezone": tzSvc.GetName(),
		"message":  "Timezone updated (restart required for persistence)",
	})
}

// formatOffset formats timezone offset as +HH:MM or -HH:MM
func formatOffset(hours, mins int) string {
	sign := "+"
	if hours < 0 {
		sign = "-"
		hours = -hours
	}
	return sign + formatTwoDigit(hours) + ":" + formatTwoDigit(mins)
}

func formatTwoDigit(n int) string {
	if n < 10 {
		return "0" + string(rune('0'+n))
	}
	return string(rune('0'+n/10)) + string(rune('0'+n%10))
}
