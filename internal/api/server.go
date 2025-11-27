package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/homesight/homesight/internal/ai"
	"github.com/homesight/homesight/internal/config"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/discovery"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/metrics"
	"github.com/homesight/homesight/internal/model"
)

// Server is the REST API server
type Server struct {
	router              *chi.Mux
	incidentService     incidents.IncidentService
	deviceRepo          db.DeviceRepository
	sensorRepo          db.SensorRepository
	knowledgeBaseRepo   db.KnowledgeBaseRepository
	metricsSink         metrics.MetricsSink
	aiClient            ai.Client
	addr                string
	discoveryListener   *discovery.MQTTDiscoveryListener
	discoveryMutex      sync.RWMutex
	eventBus            *EventBus
	cfg                 *config.Config
}

// NewServer creates a new API server
func NewServer(
	addr string,
	incidentService incidents.IncidentService,
	deviceRepo db.DeviceRepository,
	sensorRepo db.SensorRepository,
	knowledgeBaseRepo db.KnowledgeBaseRepository,
	metricsSink metrics.MetricsSink,
	aiClient ai.Client,
	cfg *config.Config,
) *Server {
	s := &Server{
		router:            chi.NewRouter(),
		incidentService:   incidentService,
		deviceRepo:        deviceRepo,
		sensorRepo:        sensorRepo,
		knowledgeBaseRepo: knowledgeBaseRepo,
		metricsSink:       metricsSink,
		aiClient:          aiClient,
		addr:              addr,
		eventBus:          NewEventBus(),
		cfg:               cfg,
	}

	s.setupRoutes()
	return s
}

// SetDiscoveryListener registers an MQTT discovery listener with the server
func (s *Server) SetDiscoveryListener(listener *discovery.MQTTDiscoveryListener) {
	s.discoveryMutex.Lock()
	defer s.discoveryMutex.Unlock()
	s.discoveryListener = listener
}

// setupRoutes configures the API routes
func (s *Server) setupRoutes() {
	s.router.Use(middleware.Logger)
	s.router.Use(middleware.Recoverer)
	s.router.Use(middleware.Timeout(60 * time.Second))
	s.router.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token"},
		ExposedHeaders:   []string{"Link"},
		AllowCredentials: false,
		MaxAge:           300,
	}))

	s.router.Get("/health", s.handleHealth)

	s.router.Route("/api", func(r chi.Router) {
		// Individual service status endpoints (non-blocking, fast responses)
		r.Get("/status/ai", s.handleAIStatus)
		r.Get("/status/ai_sidecar", s.handleAIStatus)
		r.Get("/status/prometheus", s.handlePrometheusStatus)
		r.Get("/status/database", s.handleDatabaseStatus)

		// Incidents
		r.Route("/incidents", func(r chi.Router) {
			r.Get("/", s.listIncidents)
			r.Get("/{id}", s.getIncident)
			r.Post("/{id}/resolve", s.resolveIncident)
			r.Patch("/{id}/analysis", s.updateIncidentAnalysis) // Update incident analysis (from AI sidecar)
			// Demo/Testing endpoints - In production, guard with admin authentication
			r.Post("/", s.createIncident)       // Manual incident creation (testing only)
			r.Delete("/{id}", s.deleteIncident) // Hard delete (testing/cleanup only)
		})

		// Devices
		r.Route("/devices", func(r chi.Router) {
			r.Get("/", s.listDevices)
			r.Get("/{id}", s.getDevice)
			r.Get("/{id}/sensors", s.listDeviceSensors)
			r.Get("/{id}/sensors/{sensorID}", s.getDeviceSensor)
			r.Get("/{id}/knowledge-base", s.getDeviceKnowledgeBase)
			r.Post("/{id}/reingest-docs", s.handleReingestDeviceDocs) // Re-trigger document discovery for a device
			r.Post("/{id}/docs-status", s.handleUpdateDeviceDocsStatus) // Update device documentation status and generate KB articles (called by AI sidecar)
			// Demo/Testing endpoints - In production, guard with admin authentication
			r.Post("/", s.createDevice)       // Manual device creation (testing only - normally auto-discovered)
			r.Delete("/{id}", s.deleteDevice) // Hard delete (testing/cleanup only)
		})

		// Metrics
		r.Route("/metrics", func(r chi.Router) {
			r.Get("/{sensorID}", s.getMetrics)
		})

		// Discovery & Onboarding
		r.Get("/discovery", s.handleDiscovery)
		r.Post("/onboard/device", s.handleOnboardDevice)
		r.Post("/onboard/broker", s.handleOnboardBroker)

		// AI proxy
		r.Route("/ai", func(r chi.Router) {
			r.Post("/chat", s.aiChat)
			r.Post("/analyze", s.aiAnalyze)
		})

		// Events
		r.Get("/events", s.handleEvents)
	})
}

// Start starts the API server
func (s *Server) Start() error {
	return http.ListenAndServe(s.addr, s.router)
}

// handleHealth returns service health status
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]string{
		"status": "healthy",
		"time":   time.Now().Format(time.RFC3339),
	})
}

// handleAIStatus returns AI sidecar health status
func (s *Server) handleAIStatus(w http.ResponseWriter, r *http.Request) {
	status := map[string]interface{}{"name": "AI Sidecar"}
	aiClient := &http.Client{Timeout: 1 * time.Second}
	if httpClient, ok := s.aiClient.(*ai.HTTPClient); ok {
		status["url"] = httpClient.GetBaseURL()
		if resp, err := aiClient.Get(httpClient.GetBaseURL() + "/health"); err == nil {
			defer resp.Body.Close()
			if resp.StatusCode == 200 {
				status["status"] = "healthy"
				var healthData map[string]interface{}
				if err := json.NewDecoder(resp.Body).Decode(&healthData); err == nil {
					status["details"] = healthData
				}
			} else {
				status["status"] = "unhealthy"
			}
		} else {
			status["status"] = "unavailable"
			status["error"] = err.Error()
		}
	} else {
		status["status"] = "unknown"
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

// handlePrometheusStatus returns Prometheus health status
func (s *Server) handlePrometheusStatus(w http.ResponseWriter, r *http.Request) {
	promURL := "http://localhost:9090"
	if s.cfg != nil && s.cfg.Prometheus.URL != "" {
		promURL = s.cfg.Prometheus.URL
	}

	status := map[string]interface{}{
		"name": "Prometheus",
		"url":  promURL,
	}
	promClient := &http.Client{Timeout: 1 * time.Second}
	if resp, err := promClient.Get(promURL + "/-/healthy"); err == nil {
		resp.Body.Close()
		if resp.StatusCode == 200 {
			status["status"] = "healthy"
		} else {
			status["status"] = "unhealthy"
		}
	} else {
		status["status"] = "unavailable"
		status["error"] = err.Error()
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

// handleDatabaseStatus returns database health status
func (s *Server) handleDatabaseStatus(w http.ResponseWriter, r *http.Request) {
	status := map[string]interface{}{"name": "SQLite Database"}
	ctx := r.Context()
	if _, err := s.deviceRepo.List(ctx); err == nil {
		status["status"] = "healthy"
	} else {
		status["status"] = "unhealthy"
		status["error"] = err.Error()
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

// listIncidents returns all incidents with optional filters
func (s *Server) listIncidents(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	status := r.URL.Query().Get("status")

	filters := make(map[string]any)
	if status != "" {
		filters["status"] = status
	}

	incidents, err := s.incidentService.List(ctx, filters)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(incidents)
}

// getIncident returns a specific incident
func (s *Server) getIncident(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	incident, err := s.incidentService.Get(ctx, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if incident == nil {
		http.Error(w, "incident not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(incident)
}

// resolveIncident marks an incident as resolved
func (s *Server) resolveIncident(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	if err := s.incidentService.Resolve(ctx, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "resolved"})
}

// updateIncidentAnalysis updates the analysis results for an incident (called by AI sidecar)
func (s *Server) updateIncidentAnalysis(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	var payload struct {
		AnalysisStatus string                 `json:"analysis_status"`
		Analysis       string                 `json:"analysis"`
		Insights       []string               `json:"insights"`
		Actions        []string               `json:"actions"`
		AnalysisData   map[string]interface{} `json:"analysis_data"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Get existing incident to preserve all fields
	incident, err := s.incidentService.Get(ctx, id)
	if err != nil || incident == nil {
		http.Error(w, "incident not found", http.StatusNotFound)
		return
	}

	// Update only the analysis fields, preserving all other fields
	now := time.Now()
	incident.AnalysisStatus = payload.AnalysisStatus
	incident.Analysis = payload.Analysis
	incident.Insights = payload.Insights
	incident.Actions = payload.Actions
	incident.AnalysisData = payload.AnalysisData
	incident.AnalyzedAt = &now
	incident.UpdatedAt = now

	// Save using CreateOrUpdate (which handles timestamps correctly)
	if err := s.incidentService.CreateOrUpdate(ctx, incident); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish SSE event so UI updates in real-time
	if s.eventBus != nil {
		if payload.AnalysisStatus == "completed" {
			s.eventBus.Publish(Event{
				Type: "incident_analysis_completed",
				Data: map[string]interface{}{
					"incident_id": id,
					"analysis":    payload.Analysis,
					"insights":    payload.Insights,
					"actions":     payload.Actions,
					"metadata":    payload.AnalysisData,
				},
			})
		} else if payload.AnalysisStatus == "failed" {
			s.eventBus.Publish(Event{
				Type: "incident_analysis_failed",
				Data: map[string]interface{}{
					"incident_id": id,
					"error":       payload.Analysis, // Use analysis field for error message
				},
			})
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(incident)
}

// listDevices returns all devices
func (s *Server) listDevices(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	devices, err := s.deviceRepo.List(ctx)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(devices)
}

// getDevice returns a specific device
func (s *Server) getDevice(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	device, err := s.deviceRepo.Get(ctx, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(device)
}

// getMetrics returns metrics for a sensor
func (s *Server) getMetrics(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	sensorID := chi.URLParam(r, "sensorID")

	// Parse time range from query params
	from := time.Now().Add(-24 * time.Hour)
	to := time.Now()

	if fromStr := r.URL.Query().Get("from"); fromStr != "" {
		if t, err := time.Parse(time.RFC3339, fromStr); err == nil {
			from = t
		}
	}
	if toStr := r.URL.Query().Get("to"); toStr != "" {
		if t, err := time.Parse(time.RFC3339, toStr); err == nil {
			to = t
		}
	}

	points, err := s.metricsSink.Query(ctx, sensorID, from, to)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(points)
}

// listDeviceSensors returns all sensors for a device
func (s *Server) listDeviceSensors(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")

	// Verify device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	// Get sensors for this device
	sensors, err := s.sensorRepo.ListByDevice(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(sensors)
}

// getDeviceSensor returns a specific sensor for a device
func (s *Server) getDeviceSensor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")
	sensorID := chi.URLParam(r, "sensorID")

	// Verify device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	// Get sensor
	sensor, err := s.sensorRepo.Get(ctx, sensorID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if sensor == nil {
		http.Error(w, "sensor not found", http.StatusNotFound)
		return
	}

	// Verify sensor belongs to this device
	if sensor.DeviceID != deviceID {
		http.Error(w, "sensor not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(sensor)
}

// getDeviceKnowledgeBase retrieves pre-generated knowledge base articles for a device from database
func (s *Server) getDeviceKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")

	// Verify device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	// Retrieve pre-generated articles from database
	dbArticles, err := s.knowledgeBaseRepo.GetByDevice(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Convert database articles to JSON format
	articles := []map[string]interface{}{}
	for _, article := range dbArticles {
		articles = append(articles, map[string]interface{}{
			"title":       article.Title,
			"type":        article.Type,
			"source":      article.Source,
			"description": article.Description,
			"available":   article.Available,
		})
	}

	// Return knowledge base response
	knowledgeBase := map[string]interface{}{
		"device_id":     deviceID,
		"device_name":   device.Name,
		"docs_status":   device.DocsStatus,
		"docs_ingested": device.DocsIngested,
		"ingested_at":   device.DocsIngestedAt,
		"articles":      articles,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(knowledgeBase)
}

// generateDeviceKnowledgeBase generates and stores knowledge base articles for a device
func (s *Server) generateDeviceKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")

	// Verify device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	// Build device info for AI queries
	deviceInfo := fmt.Sprintf("%s (%s) - %s device", device.Name, device.Type, device.Integration)
	if device.Metadata != nil {
		if mfg, ok := device.Metadata["manufacturer"]; ok {
			if model, ok := device.Metadata["model"]; ok {
				deviceInfo = fmt.Sprintf("%s - %s %s", device.Name, mfg, model)
			}
		}
	}

	// Create a timeout context for AI calls (30s to allow for OpenAI latency)
	// Use Background() not ctx to avoid inheriting HTTP request deadline
	aiCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Generate articles concurrently from AI sidecar
	overviewChan := make(chan string, 1)
	troubleshootChan := make(chan string, 1)
	docChan := make(chan string, 1)

	// Overview - launch concurrent
	go func() {
		overviewResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
			Message: fmt.Sprintf("Provide a comprehensive overview of the %s device. Include typical use cases, key features, and maintenance tips. Keep it concise.", deviceInfo),
		})
		if err == nil && overviewResp.Response != "" {
			overviewChan <- overviewResp.Response
		}
		close(overviewChan)
	}()

	// Troubleshooting - launch concurrent
	go func() {
		troubleshootResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
			Message: fmt.Sprintf("Provide a troubleshooting guide for the %s device. List common issues and solutions. Keep it concise.", deviceInfo),
		})
		if err == nil && troubleshootResp.Response != "" {
			troubleshootChan <- troubleshootResp.Response
		}
		close(troubleshootChan)
	}()

	// Documentation - launch concurrent
	go func() {
		if device.Metadata != nil && device.Metadata["manufacturer"] != "" {
			docResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
				Message: fmt.Sprintf("Summarize the official technical specifications and documentation for the %s. Include important settings, specifications, and compatibility information. Keep it concise.", deviceInfo),
			})
			if err == nil && docResp.Response != "" {
				docChan <- docResp.Response
			}
		}
		close(docChan)
	}()

	// Collect results - only store if AI sidecar returns actual content
	overviewContent := getValueWithContext(aiCtx, overviewChan, "")
	troubleshootContent := getValueWithContext(aiCtx, troubleshootChan, "")
	docContent := getValueWithContext(aiCtx, docChan, "")

	// Delete existing articles for this device
	if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, deviceID); err != nil {
		http.Error(w, fmt.Sprintf("failed to delete old articles: %v", err), http.StatusInternalServerError)
		return
	}

	now := time.Now()
	articlesStored := 0

	// Store Device Overview - only if content exists
	if overviewContent != "" {
		overviewArticle := &db.KnowledgeBaseArticle{
			ID:          fmt.Sprintf("%s-overview", deviceID),
			DeviceID:    deviceID,
			Title:       "Device Overview",
			Type:        "generated",
			Source:      "AI-Generated Knowledge Base",
			Description: overviewContent,
			Available:   true,
			CreatedAt:   now,
			UpdatedAt:   now,
		}
		if err := s.knowledgeBaseRepo.Upsert(ctx, overviewArticle); err != nil {
			http.Error(w, fmt.Sprintf("failed to store overview article: %v", err), http.StatusInternalServerError)
			return
		}
		articlesStored++
	}

	// Store Troubleshooting Guide - only if content exists
	if troubleshootContent != "" {
		troubleshootArticle := &db.KnowledgeBaseArticle{
			ID:          fmt.Sprintf("%s-troubleshoot", deviceID),
			DeviceID:    deviceID,
			Title:       "Troubleshooting Guide",
			Type:        "generated",
			Source:      "AI-Generated Knowledge Base",
			Description: troubleshootContent,
			Available:   true,
			CreatedAt:   now,
			UpdatedAt:   now,
		}
		if err := s.knowledgeBaseRepo.Upsert(ctx, troubleshootArticle); err != nil {
			http.Error(w, fmt.Sprintf("failed to store troubleshoot article: %v", err), http.StatusInternalServerError)
			return
		}
		articlesStored++
	}

	// Store Official Documentation - only if content exists
	if docContent != "" && device.Metadata != nil && device.Metadata["manufacturer"] != "" {
		docArticle := &db.KnowledgeBaseArticle{
			ID:          fmt.Sprintf("%s-official-docs", deviceID),
			DeviceID:    deviceID,
			Title:       "Official Documentation",
			Type:        "manufacturer",
			Source:      "Official " + device.Metadata["manufacturer"] + " Documentation",
			Description: docContent,
			Available:   true,
			CreatedAt:   now,
			UpdatedAt:   now,
		}
		if err := s.knowledgeBaseRepo.Upsert(ctx, docArticle); err != nil {
			http.Error(w, fmt.Sprintf("failed to store official docs article: %v", err), http.StatusInternalServerError)
			return
		}
		articlesStored++
	}

	// Return success with generated articles
	response := map[string]interface{}{
		"device_id": deviceID,
		"status":    "success",
		"message":   "Knowledge base articles generated and stored successfully",
		"articles":  articlesStored,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// aiChat proxies chat requests to AI sidecar
func (s *Server) aiChat(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ai.ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	resp, err := s.aiClient.Chat(ctx, req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

// aiAnalyze proxies analysis requests to AI sidecar
func (s *Server) aiAnalyze(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ai.AnalyzeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	resp, err := s.aiClient.Analyze(ctx, req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

// handleEvents streams real-time updates via SSE
func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	// Subscribe to event bus for delta events
	ch := s.eventBus.Subscribe()
	defer s.eventBus.Unsubscribe(ch)

	heartbeat := time.NewTicker(15 * time.Second)
	defer heartbeat.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case event := <-ch:
			data, _ := json.Marshal(event)
			fmt.Fprintf(w, "data: %s\n\n", data)
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
		case <-heartbeat.C:
			// Send SSE comment as heartbeat
			fmt.Fprintf(w, ": heartbeat\n\n")
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
		}
	}
}

// ==================================================================================
// Demo/Testing Endpoints - In production, add admin authentication middleware
// ==================================================================================
// NOTE: These endpoints are for testing and demos. In a real deployment:
// - Devices should be auto-discovered via integrations (Zigbee2MQTT, LAN, etc.)
// - Incidents are auto-created by the rule engine and auto-resolved when conditions clear
// - Manual creation/deletion should require admin privileges

// createDevice manually creates a device (normally auto-discovered via integrations)
func (s *Server) createDevice(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var device model.Device
	if err := json.NewDecoder(r.Body).Decode(&device); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Set timestamps
	now := time.Now()
	device.CreatedAt = now
	device.UpdatedAt = now
	device.LastSeen = now

	if err := s.deviceRepo.Upsert(ctx, &device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish device added event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceAdded, Data: device})
	}

	// Notify AI sidecar about the new device for document discovery
	// This triggers automatic ingestion of device documentation (manuals, forums, etc.)
	go s.notifyAIDeviceCreated(device)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(device)
}

// deleteDevice permanently removes a device (for cleanup/testing only)
func (s *Server) deleteDevice(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	if err := s.deviceRepo.Delete(ctx, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish device removed event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceRemoved, Data: map[string]string{"id": id}})
	}

	w.WriteHeader(http.StatusNoContent)
}

// createIncident manually creates an incident (normally auto-created by rule engine)
func (s *Server) createIncident(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var incident model.Incident
	if err := json.NewDecoder(r.Body).Decode(&incident); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Set timestamps
	now := time.Now()
	incident.CreatedAt = now
	incident.UpdatedAt = now
	if incident.Status == "" {
		incident.Status = "open"
	}
	// Set analysis status to pending (will be updated when AI sidecar completes)
	incident.AnalysisStatus = "pending"

	if err := s.incidentService.CreateOrUpdate(ctx, &incident); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish incident added event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: IncidentAdded, Data: incident})
	}

	// Notify AI sidecar to start background analysis
	go s.notifyAIIncidentCreated(incident)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(incident)
}

// deleteIncident permanently removes an incident (for cleanup/testing only)
// Note: Incidents normally auto-resolve when conditions clear. Use POST /{id}/resolve for manual resolution.
func (s *Server) deleteIncident(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	id := chi.URLParam(r, "id")

	if err := s.incidentService.Delete(ctx, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish incident removed event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: IncidentRemoved, Data: map[string]string{"id": id}})
	}

	w.WriteHeader(http.StatusNoContent)
}

// getValueWithContext receives a value from a channel with a reasonable timeout
func getValueWithContext(ctx context.Context, ch <-chan string, defaultValue string) string {
	// Use a generous 60-second timeout to account for OpenAI API latency
	// This is used for background knowledge base generation where we're not blocking HTTP requests
	timer := time.NewTimer(60 * time.Second)
	defer timer.Stop()

	select {
	case value, ok := <-ch:
		if ok && value != "" {
			return value
		}
		return defaultValue
	case <-timer.C:
		// Timeout - return default
		return defaultValue
	}
}

// getValue receives a value from a channel with a timeout fallback
func getValue(ch <-chan string, defaultValue string) string {
	select {
	case value, ok := <-ch:
		if ok && value != "" {
			return value
		}
		return defaultValue
	case <-time.After(12 * time.Second):
		// Wait up to 12 seconds for AI sidecar response (15s context timeout - 3s buffer)
		return defaultValue
	}
}

// notifyAIIncidentCreated sends an incident creation event to the AI sidecar for background analysis
func (s *Server) notifyAIIncidentCreated(incident model.Incident) {
	aiSidecarURL := os.Getenv("AI_SIDECAR_URL")
	if aiSidecarURL == "" {
		aiSidecarURL = "http://localhost:8001"
	}

	url := fmt.Sprintf("%s/events/incident", aiSidecarURL)

	payload := map[string]interface{}{
		"type": "incident.created",
		"data": incident,
	}

	body, _ := json.Marshal(payload)
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("Failed to notify AI sidecar of incident %s: %v", incident.ID, err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		log.Printf("AI sidecar returned status %d for incident %s: %s", resp.StatusCode, incident.ID, string(bodyBytes))
	} else {
		log.Printf("✅ Notified AI sidecar of incident %s for background analysis", incident.ID)
	}
}
