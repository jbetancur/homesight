package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
)

// handleGetSensorReadings returns time-series readings for a sensor
// GET /api/sensors/{deviceId}/readings?type=temperature&since=2024-01-01T00:00:00Z&limit=1000
func (s *Server) handleGetSensorReadings(w http.ResponseWriter, r *http.Request) {
	deviceID := chi.URLParam(r, "deviceId")
	if deviceID == "" {
		http.Error(w, "device_id required", http.StatusBadRequest)
		return
	}

	// Parse query parameters
	readingType := r.URL.Query().Get("type")
	if readingType == "" {
		readingType = "temperature" // Default
	}

	// Parse since parameter (default: last 24 hours)
	sinceStr := r.URL.Query().Get("since")
	var since time.Time
	if sinceStr != "" {
		var err error
		since, err = time.Parse(time.RFC3339, sinceStr)
		if err != nil {
			http.Error(w, "invalid since parameter (use RFC3339 format)", http.StatusBadRequest)
			return
		}
	} else {
		since = time.Now().Add(-24 * time.Hour)
	}

	// Parse limit (default: 1000)
	limit := 1000
	if limitStr := r.URL.Query().Get("limit"); limitStr != "" {
		var err error
		limit, err = strconv.Atoi(limitStr)
		if err != nil || limit <= 0 || limit > 10000 {
			http.Error(w, "invalid limit (must be 1-10000)", http.StatusBadRequest)
			return
		}
	}

	// Query readings from database
	readings, err := s.sensorReadingRepo.Query(r.Context(), deviceID, readingType, since, limit)
	if err != nil {
		http.Error(w, "failed to query readings: "+err.Error(), http.StatusInternalServerError)
		return
	}

	// Return as JSON
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(readings)
}

// handleRecordSensorReading manually records a sensor reading (for testing or external integrations)
// POST /api/sensors/{deviceId}/readings
// Body: {"type": "temperature", "value": 72.5, "outdoor_temp": 45.2}
func (s *Server) handleRecordSensorReading(w http.ResponseWriter, r *http.Request) {
	deviceID := chi.URLParam(r, "deviceId")
	if deviceID == "" {
		http.Error(w, "device_id required", http.StatusBadRequest)
		return
	}

	var req struct {
		Type        string   `json:"type"`
		Value       float64  `json:"value"`
		OutdoorTemp *float64 `json:"outdoor_temp,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}

	if req.Type == "" {
		http.Error(w, "type required", http.StatusBadRequest)
		return
	}

	// Insert reading
	if err := s.sensorReadingRepo.Insert(r.Context(), deviceID, req.Type, req.Value, req.OutdoorTemp); err != nil {
		http.Error(w, "failed to insert reading: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]string{"status": "created"})
}
