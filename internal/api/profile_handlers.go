package api

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/homesight/homesight/internal/model"
)

// Home Profile handlers

// handleGetHomeProfile retrieves the home profile for the default home
func (s *Server) handleGetHomeProfile(w http.ResponseWriter, r *http.Request) {
	// For now, use the first home in the system
	// TODO: Support multi-home via home_id parameter
	zones, err := s.zoneRepo.List(r.Context())
	if err != nil || len(zones) == 0 {
		http.Error(w, "No home found", http.StatusNotFound)
		return
	}

	homeID := zones[0].HomeID
	profile, err := s.homeProfileRepo.Get(r.Context(), homeID)
	if err != nil {
		log.Printf("Error getting home profile: %v", err)
		http.Error(w, "Failed to get home profile", http.StatusInternalServerError)
		return
	}

	// If no profile exists, return empty profile with home_id
	if profile == nil {
		profile = &model.HomeProfile{
			ID:        uuid.New().String(),
			HomeID:    homeID,
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(profile)
}

// handleUpdateHomeProfile updates the home profile
func (s *Server) handleUpdateHomeProfile(w http.ResponseWriter, r *http.Request) {
	var profile model.HomeProfile
	if err := json.NewDecoder(r.Body).Decode(&profile); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// If no ID, create new one
	if profile.ID == "" {
		profile.ID = uuid.New().String()
		profile.CreatedAt = time.Now()
	}
	profile.UpdatedAt = time.Now()

	if err := s.homeProfileRepo.Upsert(r.Context(), &profile); err != nil {
		log.Printf("Error upserting home profile: %v", err)
		http.Error(w, "Failed to update home profile", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(profile)
}

// Attribute Definition handlers

// handleListAttributeDefinitions lists all attribute definitions (optionally filtered by scope)
func (s *Server) handleListAttributeDefinitions(w http.ResponseWriter, r *http.Request) {
	scopeParam := r.URL.Query().Get("scope")
	var scope model.AttributeScope
	if scopeParam != "" {
		scope = model.AttributeScope(scopeParam)
	}

	defs, err := s.attributeDefinitionRepo.List(r.Context(), scope)
	if err != nil {
		log.Printf("Error listing attribute definitions: %v", err)
		http.Error(w, "Failed to list attribute definitions", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(defs)
}

// handleGetAttributeDefinition retrieves a single attribute definition
func (s *Server) handleGetAttributeDefinition(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	def, err := s.attributeDefinitionRepo.Get(r.Context(), id)
	if err != nil {
		log.Printf("Error getting attribute definition: %v", err)
		http.Error(w, "Failed to get attribute definition", http.StatusInternalServerError)
		return
	}

	if def == nil {
		http.Error(w, "Attribute definition not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(def)
}

// handleCreateAttributeDefinition creates a new attribute definition
func (s *Server) handleCreateAttributeDefinition(w http.ResponseWriter, r *http.Request) {
	var def model.AttributeDefinition
	if err := json.NewDecoder(r.Body).Decode(&def); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	def.ID = uuid.New().String()
	def.CreatedAt = time.Now()
	def.UpdatedAt = time.Now()

	if err := s.attributeDefinitionRepo.Upsert(r.Context(), &def); err != nil {
		log.Printf("Error creating attribute definition: %v", err)
		http.Error(w, "Failed to create attribute definition", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(def)
}

// handleUpdateAttributeDefinition updates an existing attribute definition
func (s *Server) handleUpdateAttributeDefinition(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")

	var def model.AttributeDefinition
	if err := json.NewDecoder(r.Body).Decode(&def); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	def.ID = id
	def.UpdatedAt = time.Now()

	if err := s.attributeDefinitionRepo.Upsert(r.Context(), &def); err != nil {
		log.Printf("Error updating attribute definition: %v", err)
		http.Error(w, "Failed to update attribute definition", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(def)
}

// handleDeleteAttributeDefinition deletes an attribute definition
func (s *Server) handleDeleteAttributeDefinition(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")

	if err := s.attributeDefinitionRepo.Delete(r.Context(), id); err != nil {
		log.Printf("Error deleting attribute definition: %v", err)
		http.Error(w, "Failed to delete attribute definition", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// Zone Attribute handlers

// handleGetZoneAttributes retrieves all attribute values for a zone
func (s *Server) handleGetZoneAttributes(w http.ResponseWriter, r *http.Request) {
	zoneID := chi.URLParam(r, "id")

	values, err := s.zoneAttributeValueRepo.ListByZone(r.Context(), zoneID)
	if err != nil {
		log.Printf("Error getting zone attributes: %v", err)
		http.Error(w, "Failed to get zone attributes", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(values)
}

// handleSetZoneAttributes sets attribute values for a zone
func (s *Server) handleSetZoneAttributes(w http.ResponseWriter, r *http.Request) {
	zoneID := chi.URLParam(r, "id")

	var values map[string]string
	if err := json.NewDecoder(r.Body).Decode(&values); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Set each attribute value
	for attrID, value := range values {
		if err := s.zoneAttributeValueRepo.Set(r.Context(), zoneID, attrID, value); err != nil {
			log.Printf("Error setting zone attribute %s: %v", attrID, err)
			http.Error(w, "Failed to set zone attributes", http.StatusInternalServerError)
			return
		}
	}

	// Publish zone_updated event
	s.eventBus.Publish(Event{
		Type: EventTypeZoneUpdated,
		Data: map[string]interface{}{
			"zone_id": zoneID,
		},
	})

	w.WriteHeader(http.StatusNoContent)
}
