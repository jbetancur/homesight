package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"
)

// SetEntityValueRequest is the request body for setting an entity value
type SetEntityValueRequest struct {
	Value interface{} `json:"value"`
}

// handleSetEntityValue sets the value of a device entity via MQTT
func (s *Server) handleSetEntityValue(w http.ResponseWriter, r *http.Request) {
	log.Printf("[API] handleSetEntityValue called - URL: %s", r.URL.Path)

	deviceID := chi.URLParam(r, "id")

	log.Printf("[API] Extracted device ID: %s", deviceID)

	// Parse request body - entity ID and value are in the body
	var req struct {
		EntityID string      `json:"entity_id"`
		Value    interface{} `json:"value"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("[API] Failed to parse request body: %v", err)
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	entityID := req.EntityID

	log.Printf("[API] Extracted params: deviceID=%s, entityID=%s, value=%v", deviceID, entityID, req.Value)

	// Get device
	device, err := s.deviceRepo.Get(context.Background(), deviceID)
	if err != nil || device == nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Find the entity
	var targetEntity *struct {
		ID       string
		Metadata map[string]interface{}
		Settable bool
	}

	if device.Entities != nil {
		for _, entity := range device.Entities {
			if entity.ID == entityID {
				targetEntity = &struct {
					ID       string
					Metadata map[string]interface{}
					Settable bool
				}{
					ID:       entity.ID,
					Metadata: entity.Metadata,
					Settable: entity.Settable,
				}
				break
			}
		}
	}

	if targetEntity == nil {
		http.Error(w, "Entity not found", http.StatusNotFound)
		return
	}

	if !targetEntity.Settable {
		http.Error(w, "Entity is not settable", http.StatusBadRequest)
		return
	}

	// Check if MQTT publisher is available
	if s.mqttPublisher == nil {
		http.Error(w, "MQTT publisher not available", http.StatusServiceUnavailable)
		return
	}

	// Publish entity set command via MQTT (event-based, non-blocking)
	topic := fmt.Sprintf("homesight/entity/set/%s", deviceID)
	payload := map[string]interface{}{
		"entity_id": entityID,
		"value":     req.Value,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[API] Failed to marshal entity set payload: %v", err)
		http.Error(w, "Internal error", http.StatusInternalServerError)
		return
	}

	if err := s.mqttPublisher.Publish(topic, payloadBytes); err != nil {
		log.Printf("[API] Failed to publish entity set command: %v", err)
		http.Error(w, fmt.Sprintf("Failed to publish command: %v", err), http.StatusInternalServerError)
		return
	}

	log.Printf("[API] ✓ Published entity set command via MQTT: device=%s entity=%s value=%v", deviceID, entityID, req.Value)

	// Return success (optimistic - actual result will come via SSE)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted) // 202 = queued for processing
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "queued",
		"message": "Entity update queued (listen to SSE for confirmation)",
		"entity":  entityID,
		"value":   req.Value,
	})
}

