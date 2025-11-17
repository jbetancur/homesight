package api

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/homesight/homesight/internal/ai"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/metrics"
)

// Server is the REST API server
type Server struct {
	router          *chi.Mux
	incidentService incidents.IncidentService
	deviceRepo      db.DeviceRepository
	metricsSink     metrics.MetricsSink
	aiClient        ai.Client
	addr            string
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
	}

	s.setupRoutes()
	return s
}

// setupRoutes configures the API routes
func (s *Server) setupRoutes() {
	s.router.Use(middleware.Logger)
	s.router.Use(middleware.Recoverer)
	s.router.Use(middleware.Timeout(60 * time.Second))

	s.router.Get("/health", s.handleHealth)

	// Incidents
	s.router.Route("/incidents", func(r chi.Router) {
		r.Get("/", s.listIncidents)
		r.Get("/{id}", s.getIncident)
		r.Post("/{id}/resolve", s.resolveIncident)
	})

	// Devices
	s.router.Route("/devices", func(r chi.Router) {
		r.Get("/", s.listDevices)
		r.Get("/{id}", s.getDevice)
	})

	// Metrics
	s.router.Route("/metrics", func(r chi.Router) {
		r.Get("/{sensorID}", s.getMetrics)
	})

	// AI proxy
	s.router.Route("/ai", func(r chi.Router) {
		r.Post("/chat", s.aiChat)
		r.Post("/analyze", s.aiAnalyze)
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
