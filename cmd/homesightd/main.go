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
	mqttint "github.com/homesight/homesight/internal/integrations/mqtt"
	"github.com/homesight/homesight/internal/integrations/zwave"
	"github.com/homesight/homesight/internal/metrics"
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
	sensorRepo := db.NewSensorRepo(database)
	incidentRepo := db.NewIncidentRepo(database)
	knowledgeBaseRepo := db.NewKnowledgeBaseRepo(database)
	zoneRepo := db.NewZoneRepo(database)
	homeProfileRepo := db.NewHomeProfileRepo(database)
	attributeDefinitionRepo := db.NewAttributeDefinitionRepo(database)
	zoneAttributeValueRepo := db.NewZoneAttributeValueRepo(database)

	// Seed default zones if none exist
	if err := zoneRepo.SeedDefaultZones(context.Background()); err != nil {
		log.Printf("Warning: Failed to seed default zones: %v", err)
	}

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

	// Initialize rules engine with device repository for enrichment
	ruleEngine := rules.NewDefaultRuleEngine(deviceRepo)
	defer ruleEngine.Close()

	// Initialize incident service
	incidentService := incidents.NewService(incidentRepo)
	defer incidentService.Close()

	// Initialize AI client
	aiClient := ai.NewHTTPClient(cfg.AI.ServiceURL)
	defer aiClient.Close()

	// Determine MQTT broker URL for internal message bus
	mqttBrokerURL := cfg.MQTT.BrokerURL
	if mqttBrokerURL == "" {
		mqttBrokerURL = "tcp://localhost:1883" // Default internal broker
	}

	// Initialize MQTT consumer for integration messages
	mqttConsumer, err := mqttint.NewConsumer(
		mqttBrokerURL,
		"homesight-consumer",
		deviceRepo,
		eventBus,
		incidentService,
	)
	if err != nil {
		log.Printf("Failed to create MQTT consumer: %v", err)
	} else {
		if err := mqttConsumer.Start(); err != nil {
			log.Printf("Failed to start MQTT consumer: %v", err)
		} else {
			log.Println("MQTT consumer started - listening for integration messages")
			defer mqttConsumer.Stop()
		}
	}

	// Initialize MQTT publisher for device commands
	mqttPublisher, err := mqttint.NewPublisher(mqttBrokerURL, "homesight-publisher")
	if err != nil {
		log.Printf("Failed to create MQTT publisher: %v", err)
	} else {
		log.Println("MQTT publisher started - ready to send device commands")
		defer mqttPublisher.Close()
	}

	// Initialize Z-Wave MQTT bridge (if enabled)
	var zwaveBridge *zwave.MQTTBridge
	if cfg.ZWave.Enabled {
		zwaveBridge = zwave.NewMQTTBridge(
			cfg.ZWave.WebSocketURL,
			mqttBrokerURL,
		)
		if err := zwaveBridge.Start(); err != nil {
			log.Printf("Failed to start Z-Wave MQTT bridge: %v", err)
		} else {
			log.Printf("Z-Wave MQTT bridge enabled (WebSocket: %s, MQTT: %s)", cfg.ZWave.WebSocketURL, mqttBrokerURL)
		}
		defer zwaveBridge.Stop()
	}

	// Start API server
	server := api.NewServer(
		cfg.API.Addr,
		incidentService,
		deviceRepo,
		sensorRepo,
		zoneRepo,
		knowledgeBaseRepo,
		homeProfileRepo,
		attributeDefinitionRepo,
		zoneAttributeValueRepo,
		metricsSink,
		aiClient,
		cfg,
	)

	// Set MQTT publisher for device commands
	if mqttPublisher != nil {
		server.SetMQTTPublisher(mqttPublisher)
		log.Println("[API] MQTT publisher configured for device commands")
	}

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
