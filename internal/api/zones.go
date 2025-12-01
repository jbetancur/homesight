package api

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/homesight/homesight/internal/model"
)

// ZoneAttributeOption represents an option for a zone attribute field
type ZoneAttributeOption struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

// ZoneAttributeField describes a zone attribute field for the UI
type ZoneAttributeField struct {
	Name        string                `json:"name"`
	Label       string                `json:"label"`
	Type        string                `json:"type"` // "select", "number", "boolean", "tags"
	Category    string                `json:"category"`
	Options     []ZoneAttributeOption `json:"options,omitempty"`
	Description string                `json:"description,omitempty"`
}

// ZoneSchema describes the zone attributes schema for UI rendering
type ZoneSchema struct {
	ZoneTypes  []ZoneAttributeOption `json:"zone_types"`
	Attributes []ZoneAttributeField  `json:"attributes"`
}

// handleGetZoneSchema returns the zone attributes schema for UI rendering
func (s *Server) handleGetZoneSchema(w http.ResponseWriter, r *http.Request) {
	schema := ZoneSchema{
		ZoneTypes: []ZoneAttributeOption{
			{Value: "basement", Label: "Basement"},
			{Value: "bathroom", Label: "Bathroom"},
			{Value: "bedroom", Label: "Bedroom"},
			{Value: "dining-room", Label: "Dining Room"},
			{Value: "garage", Label: "Garage"},
			{Value: "hallway", Label: "Hallway"},
			{Value: "kitchen", Label: "Kitchen"},
			{Value: "laundry", Label: "Laundry Room"},
			{Value: "living-room", Label: "Living Room"},
			{Value: "office", Label: "Office"},
			{Value: "outdoor", Label: "Outdoor"},
			{Value: "storage", Label: "Storage"},
			{Value: "utility", Label: "Utility Room"},
			{Value: "other", Label: "Other"},
		},
		Attributes: []ZoneAttributeField{
			// Basic Properties
			{
				Name:     "floor_type",
				Label:    "Floor Type",
				Type:     "select",
				Category: "basic",
				Options: []ZoneAttributeOption{
					{Value: "hardwood", Label: "Hardwood"},
					{Value: "carpet", Label: "Carpet"},
					{Value: "tile", Label: "Tile"},
					{Value: "vinyl", Label: "Vinyl"},
					{Value: "laminate", Label: "Laminate"},
					{Value: "concrete", Label: "Concrete"},
					{Value: "marble", Label: "Marble"},
					{Value: "stone", Label: "Stone"},
				},
			},
			{
				Name:        "square_feet",
				Label:       "Square Feet",
				Type:        "number",
				Category:    "basic",
				Description: "Room size in square feet",
			},
			{
				Name:     "has_windows",
				Label:    "Has Windows",
				Type:     "boolean",
				Category: "basic",
			},
			{
				Name:     "has_fireplace",
				Label:    "Has Fireplace",
				Type:     "boolean",
				Category: "basic",
			},
			// HVAC & Climate
			{
				Name:        "has_hvac_return",
				Label:       "Has HVAC Return",
				Type:        "boolean",
				Category:    "hvac",
				Description: "Main HVAC return vent location",
			},
			{
				Name:     "has_hvac_vent",
				Label:    "Has HVAC Vent",
				Type:     "boolean",
				Category: "hvac",
			},
			{
				Name:     "has_radiant_heat",
				Label:    "Has Radiant Heat",
				Type:     "boolean",
				Category: "hvac",
			},
			{
				Name:     "has_ceiling_fan",
				Label:    "Has Ceiling Fan",
				Type:     "boolean",
				Category: "hvac",
			},
			// Plumbing & Water
			{
				Name:        "has_plumbing",
				Label:       "Has Plumbing",
				Type:        "boolean",
				Category:    "plumbing",
				Description: "Sinks, toilets, or other plumbing fixtures",
			},
			{
				Name:     "has_water_heater",
				Label:    "Has Water Heater",
				Type:     "boolean",
				Category: "plumbing",
			},
			{
				Name:     "has_washer",
				Label:    "Has Washer/Dryer",
				Type:     "boolean",
				Category: "plumbing",
			},
			{
				Name:     "has_sump_pump",
				Label:    "Has Sump Pump",
				Type:     "boolean",
				Category: "plumbing",
			},
			// Safety & Occupancy
			{
				Name:        "has_valuables",
				Label:       "Contains Valuables",
				Type:        "boolean",
				Category:    "safety",
				Description: "Electronics, jewelry, or other valuable items",
			},
			{
				Name:     "has_pets",
				Label:    "Has Pets",
				Type:     "boolean",
				Category: "safety",
			},
			{
				Name:     "has_infant",
				Label:    "Has Infant/Child",
				Type:     "boolean",
				Category: "safety",
			},
			{
				Name:     "has_elderly",
				Label:    "Has Elderly",
				Type:     "boolean",
				Category: "safety",
			},
			{
				Name:        "is_occupied_daily",
				Label:       "Occupied Daily",
				Type:        "boolean",
				Category:    "safety",
				Description: "Regularly occupied vs storage/utility",
			},
			// Custom tags
			{
				Name:        "tags",
				Label:       "Custom Tags",
				Type:        "tags",
				Category:    "custom",
				Description: "Add custom tags for flexibility",
			},
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(schema)
}

// handleListZones returns all zones from database
func (s *Server) handleListZones(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	zones, err := s.zoneRepo.List(ctx)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(zones)
}

// handleGetZone returns a specific zone
func (s *Server) handleGetZone(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	zone, err := s.zoneRepo.Get(ctx, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if zone == nil {
		http.Error(w, "zone not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(zone)
}

// handleCreateZone creates a new zone
func (s *Server) handleCreateZone(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var zone model.Zone
	if err := json.NewDecoder(r.Body).Decode(&zone); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Set timestamps and defaults
	now := time.Now()
	zone.CreatedAt = now
	zone.UpdatedAt = now
	if zone.HomeID == "" {
		zone.HomeID = "default"
	}

	if err := s.zoneRepo.Upsert(ctx, &zone); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish zone added event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: "zone_added", Data: zone})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(zone)
}

// handleUpdateZone updates an existing zone
func (s *Server) handleUpdateZone(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	// Get existing zone
	existingZone, err := s.zoneRepo.Get(ctx, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if existingZone == nil {
		http.Error(w, "zone not found", http.StatusNotFound)
		return
	}

	// Parse update payload
	var updateData model.Zone
	if err := json.NewDecoder(r.Body).Decode(&updateData); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Merge updates (preserve ID and CreatedAt)
	updateData.ID = id
	updateData.CreatedAt = existingZone.CreatedAt
	updateData.UpdatedAt = time.Now()
	if updateData.HomeID == "" {
		updateData.HomeID = existingZone.HomeID
	}

	if err := s.zoneRepo.Upsert(ctx, &updateData); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish zone updated event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: "zone_updated", Data: updateData})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(updateData)
}

// handleDeleteZone deletes a zone
func (s *Server) handleDeleteZone(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	if err := s.zoneRepo.Delete(ctx, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish zone removed event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: "zone_removed", Data: map[string]string{"id": id}})
	}

	w.WriteHeader(http.StatusNoContent)
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
