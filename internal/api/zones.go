package api

import (
	"encoding/json"
	"fmt"
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
	ctx := r.Context()

	// Fetch zone-scoped attribute definitions from database
	attrDefs, err := s.attributeDefinitionRepo.List(ctx, model.ScopeZone)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Convert to UI schema format
	attributes := make([]ZoneAttributeField, 0, len(attrDefs))
	for _, def := range attrDefs {
		field := ZoneAttributeField{
			Name:        def.Name,
			Label:       def.Label,
			Type:        string(def.Type),
			Category:    def.Category,
			Description: def.Description,
		}

		// Convert options
		if len(def.Options) > 0 {
			field.Options = make([]ZoneAttributeOption, len(def.Options))
			for i, opt := range def.Options {
				field.Options[i] = ZoneAttributeOption{
					Value: opt,
					Label: opt,
				}
			}
		}

		attributes = append(attributes, field)
	}

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
		Attributes: attributes,
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

// updateDevice updates device fields (display_name, zone_id, etc.)
func (s *Server) updateDevice(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")

	var req map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Verify device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, fmt.Sprintf("Error fetching device: %v", err), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Update using the generic Update method
	if err := s.deviceRepo.Update(ctx, deviceID, req); err != nil {
		http.Error(w, "Failed to update device", http.StatusInternalServerError)
		return
	}

	// Reload device to get updated data
	device, _ = s.deviceRepo.Get(ctx, deviceID)

	// Enrich and return
	enriched := s.enrichDeviceWithState(ctx, *device)

	// Publish update event for SSE
	s.eventBus.Publish(Event{
		Type: DeviceUpdated,
		Data: device,
	})

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(enriched)
}
