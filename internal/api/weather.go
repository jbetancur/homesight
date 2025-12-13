package api

import (
	"encoding/json"
	"net/http"
)

// handleWeather gets weather data from Go weather service
func (s *Server) handleWeather(w http.ResponseWriter, r *http.Request) {
	if s.weatherService == nil {
		http.Error(w, "Weather service not initialized", http.StatusServiceUnavailable)
		return
	}

	ctx := s.weatherService.GetCurrent()
	if ctx == nil {
		http.Error(w, "Weather data not available", http.StatusServiceUnavailable)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(ctx)
}
