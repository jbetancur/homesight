package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/homesight/homesight/internal/ai"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/discovery"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/metrics"
	"github.com/homesight/homesight/internal/model"
)

// Server is the REST API server
type Server struct {
	router            *chi.Mux
	incidentService   incidents.IncidentService
	deviceRepo        db.DeviceRepository
	metricsSink       metrics.MetricsSink
	aiClient          ai.Client
	addr              string
	discoveryListener *discovery.MQTTDiscoveryListener
	discoveryMutex    sync.RWMutex
	eventBus          *EventBus
}

// NewServer creates a new API server
func NewServer(
	addr string,
	incidentService incidents.IncidentService,
	deviceRepo db.DeviceRepository,
	metricsSink metrics.MetricsSink,
	aiClient ai.Client,
) *Server {
	s := &Server{
		router:          chi.NewRouter(),
		incidentService: incidentService,
		deviceRepo:      deviceRepo,
		metricsSink:     metricsSink,
		aiClient:        aiClient,
		addr:            addr,
		eventBus:        NewEventBus(),
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

	// Individual service status endpoints (non-blocking, fast responses)
	s.router.Get("/api/status/ai", s.handleAIStatus)
	s.router.Get("/api/status/ai_sidecar", s.handleAIStatus)
	s.router.Get("/api/status/prometheus", s.handlePrometheusStatus)
	s.router.Get("/api/status/database", s.handleDatabaseStatus)

	s.router.Route("/api", func(r chi.Router) {
		// Incidents
		r.Route("/incidents", func(r chi.Router) {
			r.Get("/", s.listIncidents)
			r.Get("/{id}", s.getIncident)
			r.Post("/{id}/resolve", s.resolveIncident)
			// Demo/Testing endpoints - In production, guard with admin authentication
			r.Post("/", s.createIncident)       // Manual incident creation (testing only)
			r.Delete("/{id}", s.deleteIncident) // Hard delete (testing/cleanup only)
		})

		// Devices
		r.Route("/devices", func(r chi.Router) {
			r.Get("/", s.listDevices)
			r.Get("/{id}", s.getDevice)
			r.Post("/{id}/reingest-docs", s.handleReingestDeviceDocs) // Re-trigger document discovery for a device
			r.Post("/{id}/docs-status", s.handleUpdateDeviceDocsStatus) // Update device documentation status (called by AI sidecar)
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

// handleSystemStatus returns summary stats and service list
// Individual service status endpoints (/api/status/{service}) are called by UI
func (s *Server) handleSystemStatus(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	// Summary counts (fast, no blocking calls)
	devices, _ := s.deviceRepo.List(ctx)
	openIncidents, _ := s.incidentService.List(ctx, map[string]any{"status": "open"})
	allIncidents, _ := s.incidentService.List(ctx, map[string]any{})

	// Service list (no health checks here - UI calls individual endpoints)
	services := map[string]interface{}{
		"ai_sidecar":     map[string]string{"name": "AI Sidecar"},
		"prometheus":     map[string]string{"name": "Prometheus", "url": "http://localhost:9090"},
		"database":       map[string]string{"name": "SQLite Database"},
		"mqtt_discovery": map[string]string{"name": "MQTT Discovery"},
	}

	status := map[string]interface{}{
		"timestamp": time.Now().Format(time.RFC3339),
		"services":  services,
		"summary": map[string]interface{}{
			"devices":         len(devices),
			"open_incidents":  len(openIncidents),
			"total_incidents": len(allIncidents),
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
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
	status := map[string]interface{}{
		"name": "Prometheus",
		"url":  "http://localhost:9090",
	}
	promClient := &http.Client{Timeout: 1 * time.Second}
	if resp, err := promClient.Get("http://localhost:9090/-/healthy"); err == nil {
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

// toInterfaceSlice converts a slice of any type to a slice of empty interfaces

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

	if err := s.incidentService.CreateOrUpdate(ctx, &incident); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Publish incident added event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: IncidentAdded, Data: incident})
	}

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
