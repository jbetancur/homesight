package api

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/homesight/homesight/internal/model"
)

// handleListZones returns all zones
func (s *Server) handleListZones(w http.ResponseWriter, r *http.Request) {
	// TODO: Query from database when ZoneRepository is implemented
	// For now, return common room types for demos
	zones := []model.Zone{
		{
			ID:     "living-room",
			Name:   "Living Room",
			Type:   "living_room",
			HomeID: "default",
		},
		{
			ID:     "kitchen",
			Name:   "Kitchen",
			Type:   "kitchen",
			HomeID: "default",
		},
		{
			ID:     "bedroom",
			Name:   "Bedroom",
			Type:   "bedroom",
			HomeID: "default",
		},
		{
			ID:     "bathroom",
			Name:   "Bathroom",
			Type:   "bathroom",
			HomeID: "default",
		},
		{
			ID:     "basement",
			Name:   "Basement",
			Type:   "basement",
			HomeID: "default",
		},
		{
			ID:     "garage",
			Name:   "Garage",
			Type:   "garage",
			HomeID: "default",
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(zones)
}

// handleUpdateDeviceZone updates a device's zone assignment
func (s *Server) handleUpdateDeviceZone(w http.ResponseWriter, r *http.Request) {
	deviceID := chi.URLParam(r, "id")

	var req struct {
		ZoneID string `json:"zone_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Get the device
	device, err := s.deviceRepo.Get(r.Context(), deviceID)
	if err != nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Update zone
	device.ZoneID = req.ZoneID

	// Save to database
	if err := s.deviceRepo.Upsert(r.Context(), device); err != nil {
		http.Error(w, "Failed to update device", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(device)
}
