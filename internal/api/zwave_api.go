package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/homesight/homesight/internal/integrations/zwave"
)

// handleZWaveGetController returns controller information
func (s *Server) handleZWaveGetController(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	controller, err := s.zwaveClient.GetController()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	s.zwaveMutex.RLock()
	homeID := s.zwaveHomeID
	s.zwaveMutex.RUnlock()

	response := map[string]interface{}{
		"home_id":    fmt.Sprintf("0x%08x", homeID),
		"connected":  true,
		"ready":      true,
		"controller": controller,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// handleZWaveStartInclusion starts device inclusion (pairing)
func (s *Server) handleZWaveStartInclusion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	// Parse request body for options
	var req struct {
		Strategy      string `json:"strategy"` // "Security_S2", "Security_S0", "Insecure"
		ForceSecurity bool   `json:"force_security"`
	}

	if r.Body != nil {
		json.NewDecoder(r.Body).Decode(&req)
	}

	// Default to S2 security
	if req.Strategy == "" {
		req.Strategy = "Security_S2"
	}

	err := s.zwaveClient.BeginInclusion(zwave.InclusionOptions{
		Strategy:      req.Strategy,
		ForceSecurity: req.ForceSecurity,
		Timeout:       60 * time.Second,
	})

	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":   "started",
		"message":  "Press the button on your Z-Wave device to pair",
		"strategy": req.Strategy,
	})
}

// handleZWaveStopInclusion stops device inclusion
func (s *Server) handleZWaveStopInclusion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	err := s.zwaveClient.StopInclusion()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "stopped",
	})
}

// handleZWaveStartExclusion starts device exclusion (removal)
func (s *Server) handleZWaveStartExclusion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	err := s.zwaveClient.BeginExclusion()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "started",
		"message": "Press the button on your Z-Wave device to remove it",
	})
}

// handleZWaveStopExclusion stops device exclusion
func (s *Server) handleZWaveStopExclusion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	err := s.zwaveClient.StopExclusion()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "stopped",
	})
}

// handleZWaveGetNodes returns all Z-Wave nodes
func (s *Server) handleZWaveGetNodes(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	nodes, err := s.zwaveClient.GetNodes()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(nodes)
}

// handleZWaveRemoveFailedNode removes a dead/failed node
func (s *Server) handleZWaveRemoveFailedNode(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	// Get node ID from request body
	var req struct {
		NodeID int `json:"node_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	err := s.zwaveClient.RemoveFailedNode(req.NodeID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "removed",
		"node_id": req.NodeID,
	})
}

// handleZWaveBackupNVM creates a backup of the Z-Wave network
func (s *Server) handleZWaveBackupNVM(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	err := s.zwaveClient.BackupNVM()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "success",
		"message": "NVM backup created",
	})
}

// handleZWaveGetStatistics returns Z-Wave driver statistics
func (s *Server) handleZWaveGetStatistics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if s.zwaveClient == nil || !s.zwaveClient.IsConnected() {
		http.Error(w, "Z-Wave controller not connected", http.StatusServiceUnavailable)
		return
	}

	stats, err := s.zwaveClient.GetStatistics()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}
