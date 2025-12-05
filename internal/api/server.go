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
	"strconv"
	"strings"
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
	mqttint "github.com/homesight/homesight/internal/integrations/mqtt"
	"github.com/homesight/homesight/internal/integrations/zwave"
	"github.com/homesight/homesight/internal/metrics"
	"github.com/homesight/homesight/internal/model"
)

// Server is the REST API server
type Server struct {
	router            *chi.Mux
	incidentService   incidents.IncidentService
	deviceRepo        db.DeviceRepository
	sensorRepo        db.SensorRepository
	zoneRepo          db.ZoneRepository
	knowledgeBaseRepo db.KnowledgeBaseRepository
	metricsSink       metrics.MetricsSink
	aiClient          ai.Client
	addr              string
	discoveryListener *discovery.MQTTDiscoveryListener
	discoveryMutex    sync.RWMutex
	eventBus          *EventBus
	cfg               *config.Config

	// MQTT publisher for device commands
	mqttPublisher *mqttint.Publisher

	// Z-Wave integration
	zwaveClient *zwave.Client
	zwaveHomeID int
	zwaveMutex  sync.RWMutex
}

// NewServer creates a new API server
func NewServer(
	addr string,
	incidentService incidents.IncidentService,
	deviceRepo db.DeviceRepository,
	sensorRepo db.SensorRepository,
	zoneRepo db.ZoneRepository,
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
		zoneRepo:          zoneRepo,
		knowledgeBaseRepo: knowledgeBaseRepo,
		metricsSink:       metricsSink,
		aiClient:          aiClient,
		addr:              addr,
		eventBus:          NewEventBus(),
		cfg:               cfg,
	}

	// Initialize Z-Wave if enabled
	if cfg.ZWave.Enabled {
		s.initZWave()
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

// SetMQTTPublisher registers an MQTT publisher for device commands
func (s *Server) SetMQTTPublisher(publisher *mqttint.Publisher) {
	s.mqttPublisher = publisher
}

// setupRoutes configures the API routes
func (s *Server) setupRoutes() {
	s.router.Use(middleware.Logger)
	s.router.Use(middleware.Recoverer)
	s.router.Use(middleware.Timeout(60 * time.Second))
	s.router.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"},
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
			r.Patch("/{id}", s.updateDevice) // Update device fields (alias, zone_id, etc.)
			r.Get("/{id}/sensors", s.listDeviceSensors)
			r.Get("/{id}/sensors/{sensorID}", s.getDeviceSensor)
			r.Get("/{id}/knowledge-base", s.getDeviceKnowledgeBase)
			r.Get("/{id}/incidents", s.listDeviceIncidents)             // Get incidents for a specific device
			r.Post("/{id}/command", s.handleDeviceCommand)              // Send command to device via MQTT
			r.Post("/{id}/reingest-docs", s.handleReingestDeviceDocs)   // Re-trigger document discovery for a device
			r.Post("/{id}/docs-status", s.handleUpdateDeviceDocsStatus) // Update device documentation status and generate KB articles (called by AI sidecar)
			// Demo/Testing endpoints - In production, guard with admin authentication
			r.Post("/", s.createDevice)       // Manual device creation (testing only - normally auto-discovered)
			r.Delete("/{id}", s.deleteDevice) // Hard delete (testing/cleanup only)
		})

		// Zones/Rooms
		r.Route("/zones", func(r chi.Router) {
			r.Get("/", s.handleListZones)
			r.Get("/schema", s.handleGetZoneSchema)
			r.Post("/", s.handleCreateZone)
			r.Get("/{id}", s.handleGetZone)
			r.Put("/{id}", s.handleUpdateZone)
			r.Delete("/{id}", s.handleDeleteZone)
		})

		// Metrics
		r.Route("/metrics", func(r chi.Router) {
			r.Get("/{sensorID}", s.getMetrics)
		})

		// Discovery & Onboarding
		// r.Get("/discovery", s.handleDiscovery)
		r.Post("/onboard/device", s.handleOnboardDevice)
		r.Post("/onboard/broker", s.handleOnboardBroker)

		// Z-Wave
		r.Route("/zwave", func(r chi.Router) {
			r.Get("/controller", s.handleZWaveGetController)
			r.Get("/nodes", s.handleZWaveGetNodes)
			r.Get("/statistics", s.handleZWaveGetStatistics)
			r.Post("/inclusion/start", s.handleZWaveStartInclusion)
			r.Post("/inclusion/stop", s.handleZWaveStopInclusion)
			r.Post("/exclusion/start", s.handleZWaveStartExclusion)
			r.Post("/exclusion/stop", s.handleZWaveStopExclusion)
			r.Post("/remove-failed", s.handleZWaveRemoveFailedNode)
			r.Post("/backup", s.handleZWaveBackupNVM)
		})

		// AI proxy
		r.Route("/ai", func(r chi.Router) {
			r.Post("/chat", s.aiChat)
			r.Post("/analyze", s.aiAnalyze)
		})

		// HSIL proxy (HomeSight Intelligence Layer)
		r.Route("/hsil", func(r chi.Router) {
			r.Post("/events", s.hsilProcessEvent)
			r.Post("/chat", s.hsilChat)
			r.Post("/feedback", s.hsilFeedback)
			r.Get("/state", s.hsilGetState)
			r.Get("/stats", s.hsilGetStats)
			r.Get("/preferences", s.hsilGetPreferences)
			r.Get("/erratic", s.hsilGetErratic)
			r.Get("/model-health", s.hsilGetModelHealth)
			r.Get("/device-health", s.hsilGetDeviceHealth)
			r.Get("/weather", s.handleWeather)
		})

		// Weather (also available at /api/weather for convenience)
		r.Get("/weather", s.handleWeather)

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

	// Get incident before resolving to include in event
	incident, err := s.incidentService.Get(ctx, id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if incident == nil {
		http.Error(w, "incident not found", http.StatusNotFound)
		return
	}

	if err := s.incidentService.Resolve(ctx, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Get updated incident after resolution
	resolvedIncident, _ := s.incidentService.Get(ctx, id)
	if resolvedIncident != nil {
		incident = resolvedIncident
	}

	// Publish incident updated/resolved event
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: IncidentUpdated, Data: incident})
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

// enrichDeviceWithState enriches a device with current sensor values and incident state
func (s *Server) enrichDeviceWithState(ctx context.Context, device model.Device) map[string]interface{} {
	// Compute display name (alias if set, otherwise original name)
	displayName := device.Name
	if device.Alias != "" {
		displayName = device.Alias
	}

	// Start with all original device fields
	enriched := map[string]interface{}{
		"id":               device.ID,
		"name":             device.Name,
		"alias":            device.Alias,
		"display_name":     displayName,
		"type":             device.Type,
		"integration":      device.Integration,
		"zone_id":          device.ZoneID,
		"asset_id":         device.AssetID,
		"enabled":          device.Enabled,
		"last_seen":        device.LastSeen,
		"metadata":         device.Metadata,
		"docs_ingested":    device.DocsIngested,
		"docs_ingested_at": device.DocsIngestedAt,
		"docs_status":      device.DocsStatus,
		"created_at":       device.CreatedAt,
		"updated_at":       device.UpdatedAt,
		// Add enrichment fields
		"state":  "normal",
		"active": false,
		"value":  nil,
		"unit":   "",
		"trend":  nil,
	}

	// Extract battery level and sensor readings from metadata
	if device.Metadata != nil {
		// Battery level
		if batteryStr, ok := device.Metadata["battery_level"]; ok {
			if battery, err := strconv.Atoi(batteryStr); err == nil {
				enriched["battery_level"] = battery
				enriched["battery_low"] = battery < 20
			}
		}

		// Extract sensor readings from metadata
		// Z-Wave stores as: value_<property> (e.g., value_temperature, value_humidity)
		// MQTT stores as: state_<key> (e.g., state_temperature, state_leak)
		readings := make(map[string]interface{})

		for key, val := range device.Metadata {
			// Handle Z-Wave value_ prefix
			if strings.HasPrefix(key, "value_") {
				readingKey := strings.TrimPrefix(key, "value_")
				// Skip internal properties
				if readingKey == "level" || readingKey == "idle" {
					continue
				}
				readings[readingKey] = parseReadingValue(val)
			}
			// Handle MQTT state_ prefix
			if strings.HasPrefix(key, "state_") {
				readingKey := strings.TrimPrefix(key, "state_")
				readings[readingKey] = parseReadingValue(val)
			}
			// Handle MQTT attr_ prefix
			if strings.HasPrefix(key, "attr_") {
				readingKey := strings.TrimPrefix(key, "attr_")
				readings[readingKey] = parseReadingValue(val)
			}
		}

		// Also check for common direct metadata keys
		commonReadings := []string{"temperature", "humidity", "leak", "motion", "contact", "tamper", "power", "energy", "brightness", "on"}
		for _, key := range commonReadings {
			if val, ok := device.Metadata[key]; ok {
				readings[key] = parseReadingValue(val)
			}
		}

		if len(readings) > 0 {
			enriched["readings"] = readings
		}
	}

	// Get latest sensor values from sensor repository (if any)
	sensors, err := s.sensorRepo.ListByDevice(ctx, device.ID)
	if err == nil && len(sensors) > 0 {
		// Use first sensor's value (most devices have one primary sensor)
		sensor := sensors[0]

		// Query latest metric (last 1 minute)
		to := time.Now()
		from := to.Add(-1 * time.Minute)
		metrics, err := s.metricsSink.Query(ctx, sensor.ID, from, to)
		if err == nil && len(metrics) > 0 {
			// Get most recent metric
			metric := metrics[len(metrics)-1]
			enriched["value"] = metric.Value
			enriched["unit"] = sensor.Unit
			enriched["last_updated"] = metric.Timestamp
		}
	}

	// Check for active (unresolved) incidents
	allIncidents, err := s.incidentService.List(ctx, map[string]any{
		"device_id": device.ID,
	})
	if err == nil {
		// Filter to only unresolved incidents
		var unresolvedIncidents []model.Incident
		for _, incident := range allIncidents {
			if incident.Status != "resolved" {
				unresolvedIncidents = append(unresolvedIncidents, incident)
			}
		}

		if len(unresolvedIncidents) > 0 {
			enriched["active"] = true

			// Determine state based on severity
			highestSeverity := "normal"
			for _, incident := range unresolvedIncidents {
				switch incident.Severity {
				case "critical":
					highestSeverity = "critical"
				case "warning":
					if highestSeverity != "critical" {
						highestSeverity = "warning"
					}
				}
			}
			enriched["state"] = highestSeverity
		}
	}

	return enriched
}

// parseReadingValue attempts to parse a string value into an appropriate type
func parseReadingValue(val string) interface{} {
	// Try parsing as float
	if f, err := strconv.ParseFloat(val, 64); err == nil {
		// Round to 1 decimal place for display
		return float64(int(f*10)) / 10
	}
	// Try parsing as bool
	if val == "true" {
		return true
	}
	if val == "false" {
		return false
	}
	// Return as string
	return val
}

// enrichEventData enriches device events with battery_level, readings, etc.
// This ensures SSE events contain the same enriched data as the REST API
func (s *Server) enrichEventData(ctx context.Context, event Event) Event {
	// Only enrich device-related events
	if event.Type != DeviceAdded && event.Type != DeviceUpdated {
		return event
	}

	// Try to extract device from event data
	var device *model.Device
	switch d := event.Data.(type) {
	case model.Device:
		device = &d
	case *model.Device:
		device = d
	default:
		// Not a device type we can enrich
		return event
	}

	// Enrich the device data
	enriched := s.enrichDeviceWithState(ctx, *device)

	return Event{
		Type: event.Type,
		Data: enriched,
	}
}

// listDevices returns all devices
func (s *Server) listDevices(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	devices, err := s.deviceRepo.List(ctx)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Enrich devices with sensor values and incident states
	enrichedDevices := make([]map[string]interface{}, 0, len(devices))
	for _, device := range devices {
		enriched := s.enrichDeviceWithState(ctx, device)
		enrichedDevices = append(enrichedDevices, enriched)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(enrichedDevices)
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

	// Enrich device with current state and sensor values
	enriched := s.enrichDeviceWithState(ctx, *device)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(enriched)
}

// handleDeviceCommand sends a command to a device via MQTT
func (s *Server) handleDeviceCommand(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	deviceID := chi.URLParam(r, "id")

	// Parse command from request body
	var req struct {
		Command   string                 `json:"command"`
		Arguments map[string]interface{} `json:"args"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	// Validate device exists
	device, err := s.deviceRepo.Get(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if device == nil {
		http.Error(w, "device not found", http.StatusNotFound)
		return
	}

	// Check if MQTT publisher is available
	if s.mqttPublisher == nil {
		http.Error(w, "MQTT publisher not available", http.StatusServiceUnavailable)
		return
	}

	// Publish command via MQTT
	cmd := model.DeviceCommand{
		DeviceID:  deviceID,
		Command:   req.Command,
		Arguments: req.Arguments,
	}

	if err := s.mqttPublisher.PublishCommand(cmd); err != nil {
		log.Printf("[API] Failed to publish command to %s: %v", deviceID, err)
		http.Error(w, fmt.Sprintf("failed to send command: %v", err), http.StatusInternalServerError)
		return
	}

	log.Printf("[API] Command sent to %s: %s", deviceID, req.Command)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    "success",
		"device_id": deviceID,
		"command":   req.Command,
		"message":   "Command sent via MQTT",
	})
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

// getDeviceKnowledgeBase retrieves pre-generated knowledge base for a device from database
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

	// Retrieve pre-generated KB from database
	kb, err := s.knowledgeBaseRepo.GetByDevice(ctx, deviceID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Return knowledge base response
	response := map[string]interface{}{
		"device_id":     deviceID,
		"device_name":   device.Name,
		"docs_status":   device.DocsStatus,
		"docs_ingested": device.DocsIngested,
		"ingested_at":   device.DocsIngestedAt,
	}

	if kb != nil {
		response["content"] = kb.Content
		response["source"] = kb.Source
		response["manufacturer"] = kb.Manufacturer
		response["model"] = kb.Model
		response["created_at"] = kb.CreatedAt
		response["updated_at"] = kb.UpdatedAt
	} else {
		response["content"] = ""
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// listDeviceIncidents returns all incidents for a specific device
func (s *Server) listDeviceIncidents(w http.ResponseWriter, r *http.Request) {
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

	// Optional status filter
	status := r.URL.Query().Get("status")

	filters := map[string]any{
		"device_id": deviceID,
	}
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
	manufacturer := ""
	modelName := ""
	if device.Metadata != nil {
		if mfg, ok := device.Metadata["manufacturer"]; ok {
			manufacturer = mfg
			if m, ok := device.Metadata["model"]; ok {
				modelName = m
				deviceInfo = fmt.Sprintf("%s - %s %s", device.Name, mfg, m)
			}
		}
	}

	// Create a timeout context for AI call (45s to allow for OpenAI latency)
	aiCtx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()

	// Build context for RAG filtering
	deviceContext := map[string]interface{}{
		"device_name":  device.Name,
		"manufacturer": manufacturer,
		"model":        modelName,
		"device_type":  string(device.Type),
	}

	// Generate a single comprehensive KB document in markdown
	kbPrompt := fmt.Sprintf(`Generate a comprehensive knowledge base document for the %s device.

Format as a single markdown document with these sections:

## Overview
Device overview with typical use cases, key features, and maintenance tips.

## Troubleshooting
Common issues and solutions in numbered list format.

## Specifications
Technical specifications, settings, and compatibility information.

Keep it concise but informative. Use proper markdown formatting.`, deviceInfo)

	kbResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
		Message: kbPrompt,
		Context: deviceContext,
	})

	// Default content if API call fails
	content := fmt.Sprintf(`## Overview
Comprehensive overview of %s including typical use cases, configuration, and maintenance.

## Troubleshooting
Common issues and solutions for %s.

## Specifications
Technical specifications and settings.`, device.Name, device.Name)

	if err == nil && kbResp.Response != "" {
		content = kbResp.Response
	}

	// Delete existing KB for this device
	if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, deviceID); err != nil {
		http.Error(w, fmt.Sprintf("failed to delete old KB: %v", err), http.StatusInternalServerError)
		return
	}

	now := time.Now()
	source := "AI-Generated Knowledge Base"
	if manufacturer != "" {
		source = fmt.Sprintf("AI-Generated from %s Documentation", manufacturer)
	}

	// Store single KB document
	kb := &db.KnowledgeBase{
		ID:           fmt.Sprintf("%s-kb", deviceID),
		DeviceID:     deviceID,
		Manufacturer: manufacturer,
		Model:        modelName,
		Content:      content,
		Source:       source,
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	if err := s.knowledgeBaseRepo.Upsert(ctx, kb); err != nil {
		http.Error(w, fmt.Sprintf("failed to store KB: %v", err), http.StatusInternalServerError)
		return
	}

	// Return success
	response := map[string]interface{}{
		"device_id": deviceID,
		"status":    "success",
		"message":   "Knowledge base generated and stored successfully",
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
			// Enrich device events with battery_level, readings, etc.
			enrichedEvent := s.enrichEventData(r.Context(), event)
			data, _ := json.Marshal(enrichedEvent)
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
	aiSidecarURL := os.Getenv("AI_SERVICE_URL") // Use same env var as other places
	if aiSidecarURL == "" {
		aiSidecarURL = "http://ai-sidecar:8001" // Docker network default
	}

	url := fmt.Sprintf("%s/events/incident", aiSidecarURL)

	payload := map[string]interface{}{
		"type": "incident.created",
		"data": incident,
	}

	body, _ := json.Marshal(payload)
	log.Printf("[AI-NOTIFY] Sending incident notification to %s for incident %s", url, incident.ID)

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("[AI-NOTIFY] ❌ Failed to notify AI sidecar of incident %s: %v", incident.ID, err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		log.Printf("[AI-NOTIFY] ⚠️ AI sidecar returned status %d for incident %s: %s", resp.StatusCode, incident.ID, string(bodyBytes))
	} else {
		log.Printf("[AI-NOTIFY] ✅ Notified AI sidecar of incident %s for background analysis", incident.ID)
	}
}
