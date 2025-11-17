package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/homesight/homesight/internal/ai"
	"github.com/homesight/homesight/internal/api"
	"github.com/homesight/homesight/internal/config"
	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/events"
	"github.com/homesight/homesight/internal/incidents"
	"github.com/homesight/homesight/internal/integrations"
	"github.com/homesight/homesight/internal/metrics"
	"github.com/homesight/homesight/internal/model"
	"github.com/homesight/homesight/internal/rules"
)

func main() {
	log.Println("Starting HomeSight daemon...")

	// Load configuration
	cfgPath := os.Getenv("HOMESIGHT_CONFIG")
	if cfgPath == "" {
		cfgPath = "/etc/homesight/config.yaml"
	}

	cfg, err := config.Load(cfgPath)
	if err != nil {
		log.Printf("Failed to load config, using defaults: %v", err)
		cfg = config.Default()
	}

	// Initialize database
	database, err := db.NewSQLiteDB(cfg.Database.Path)
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer database.Close()

	// Create repositories
	deviceRepo := db.NewDeviceRepo(database)
	incidentRepo := db.NewIncidentRepo(database)

	// Initialize metrics sink
	var metricsSink metrics.MetricsSink
	metricsSink, err = metrics.NewPrometheusMetricsSink(cfg.Prometheus.URL)
	if err != nil {
		log.Printf("Failed to initialize Prometheus, using mock: %v", err)
		metricsSink = metrics.NewMockMetricsSink()
	}
	defer metricsSink.Close()

	// Initialize event bus
	eventBus := events.NewChannelEventBus()
	defer eventBus.Close()

	// Initialize rules engine
	ruleEngine := rules.NewDefaultRuleEngine()
	defer ruleEngine.Close()

	// Initialize incident service
	incidentService := incidents.NewService(incidentRepo)
	defer incidentService.Close()

	// Initialize AI client
	aiClient := ai.NewHTTPClient(cfg.AI.ServiceURL)
	defer aiClient.Close()

	// Initialize integrations
	var activeIntegrations []integrations.Integration

	if cfg.Integrations.MQTT {
		mqttIntegration, err := integrations.NewMQTTIntegration(cfg.MQTT.BrokerURL, "homesight")
		if err != nil {
			log.Printf("Failed to initialize MQTT integration: %v", err)
		} else {
			activeIntegrations = append(activeIntegrations, mqttIntegration)
			log.Println("MQTT integration enabled")
		}
	}

	if cfg.Integrations.Zigbee {
		zigbeeIntegration, err := integrations.NewZigbee2MQTTIntegration(cfg.MQTT.BrokerURL)
		if err != nil {
			log.Printf("Failed to initialize Zigbee2MQTT integration: %v", err)
		} else {
			activeIntegrations = append(activeIntegrations, zigbeeIntegration)
			log.Println("Zigbee2MQTT integration enabled")
		}
	}

	if cfg.Integrations.Matter {
		matterIntegration := integrations.NewMatterIntegration()
		activeIntegrations = append(activeIntegrations, matterIntegration)
		log.Println("Matter integration enabled")
	}

	if cfg.Integrations.LAN {
		lanIntegration := integrations.NewLANIntegration()
		activeIntegrations = append(activeIntegrations, lanIntegration)
		log.Println("LAN integration enabled")
	}

	// Start integration subscriptions
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	for _, integration := range activeIntegrations {
		go func(intg integrations.Integration) {
			eventChan := make(chan model.DeviceEvent, 100)
			go func() {
				for event := range eventChan {
					eventBus.Publish(event)
				}
			}()
			if err := intg.Subscribe(ctx, eventChan); err != nil {
				log.Printf("Integration subscription error: %v", err)
			}
		}(integration)
	}

	// Start event processing
	go processEvents(ctx, eventBus, ruleEngine, incidentService, metricsSink)

	// Start API server
	server := api.NewServer(cfg.API.Addr, incidentService, deviceRepo, metricsSink, aiClient)
	go func() {
		log.Printf("Starting API server on %s", cfg.API.Addr)
		if err := server.Start(); err != nil {
			log.Fatalf("API server failed: %v", err)
		}
	}()

	log.Println("HomeSight daemon started successfully")

	// Wait for shutdown signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down HomeSight daemon...")
}

// processEvents handles all device events
func processEvents(
	ctx context.Context,
	eventBus events.EventBus,
	ruleEngine rules.RuleEngine,
	incidentService incidents.IncidentService,
	metricsSink metrics.MetricsSink,
) {
	events := eventBus.Subscribe()

	for {
		select {
		case <-ctx.Done():
			return
		case event := <-events:
			handleEvent(ctx, event, ruleEngine, incidentService, metricsSink)
		}
	}
}

// handleEvent processes a single device event
func handleEvent(
	ctx context.Context,
	event model.DeviceEvent,
	ruleEngine rules.RuleEngine,
	incidentService incidents.IncidentService,
	metricsSink metrics.MetricsSink,
) {
	// Record metric if numeric
	if event.ValueType == "float" || event.ValueType == "float64" {
		if val, ok := event.Value.(float64); ok {
			if err := metricsSink.Record(ctx, event.SensorID, event.Timestamp, val, event.Metadata); err != nil {
				log.Printf("Failed to record metric: %v", err)
			}
		}
	}

	// Evaluate rules
	incidents, err := ruleEngine.Process(ctx, event)
	if err != nil {
		log.Printf("Rule processing error: %v", err)
		return
	}

	// Create incidents
	for _, incident := range incidents {
		if err := incidentService.CreateOrUpdate(ctx, &incident); err != nil {
			log.Printf("Failed to create incident: %v", err)
		} else {
			log.Printf("Incident created: %s - %s", incident.Severity, incident.Title)
		}
	}
}
