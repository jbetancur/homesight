package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Config holds application configuration
type Config struct {
	Database struct {
		Path string `yaml:"path"`
	} `yaml:"database"`

	MQTT struct {
		BrokerURL string `yaml:"broker_url"`
		Username  string `yaml:"username"`
		Password  string `yaml:"password"`
	} `yaml:"mqtt"`

	Prometheus struct {
		URL string `yaml:"url"`
	} `yaml:"prometheus"`

	System struct {
		Timezone       string `yaml:"timezone"`
		TemperatureUnit string `yaml:"temperature_unit"` // "celsius" or "fahrenheit"
		NTP            struct {
			Enabled           bool     `yaml:"enabled"`
			Servers           []string `yaml:"servers"`
			SyncIntervalHours int      `yaml:"sync_interval_hours"`
		} `yaml:"ntp"`
	} `yaml:"system"`

	Weather struct {
		ZipCode             string `yaml:"zip_code"`
		RefreshIntervalMins int    `yaml:"refresh_interval_minutes"`
	} `yaml:"weather"`

	AI struct {
		ServiceURL string `yaml:"service_url"`
	} `yaml:"ai"`

	API struct {
		Addr string `yaml:"addr"`
	} `yaml:"api"`

	ZWave struct {
		Enabled      bool   `yaml:"enabled"`
		WebSocketURL string `yaml:"websocket_url"`
	} `yaml:"zwave"`
}

// getEnvOrDefault returns the environment variable value or a default
func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// Load reads configuration from a YAML file
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	// Apply defaults and environment variable overrides
	// Environment variables take precedence over config file values
	if cfg.Database.Path == "" {
		cfg.Database.Path = "/var/lib/homesight/homesight.db"
	}
	cfg.Database.Path = getEnvOrDefault("HOMESIGHT_DB_PATH", cfg.Database.Path)

	if cfg.MQTT.BrokerURL == "" {
		cfg.MQTT.BrokerURL = "tcp://localhost:1883"
	}
	cfg.MQTT.BrokerURL = getEnvOrDefault("MQTT_BROKER_URL", cfg.MQTT.BrokerURL)

	if cfg.Prometheus.URL == "" {
		cfg.Prometheus.URL = "http://localhost:9090"
	}
	cfg.Prometheus.URL = getEnvOrDefault("PROMETHEUS_URL", cfg.Prometheus.URL)

	if cfg.AI.ServiceURL == "" {
		cfg.AI.ServiceURL = "http://localhost:8001"
	}
	cfg.AI.ServiceURL = getEnvOrDefault("AI_SERVICE_URL", cfg.AI.ServiceURL)

	if cfg.API.Addr == "" {
		cfg.API.Addr = ":8080"
	}
	cfg.API.Addr = getEnvOrDefault("API_ADDR", cfg.API.Addr)

	if cfg.ZWave.WebSocketURL == "" {
		cfg.ZWave.WebSocketURL = "ws://localhost:3001"
	}
	cfg.ZWave.WebSocketURL = getEnvOrDefault("ZWAVE_WEBSOCKET_URL", cfg.ZWave.WebSocketURL)

	// Default to Fahrenheit if not specified
	if cfg.System.TemperatureUnit == "" {
		cfg.System.TemperatureUnit = "fahrenheit"
	}
	cfg.System.TemperatureUnit = getEnvOrDefault("TEMPERATURE_UNIT", cfg.System.TemperatureUnit)

	return &cfg, nil
}

// Default returns a configuration with default values
func Default() *Config {
	cfg := &Config{}
	cfg.Database.Path = getEnvOrDefault("HOMESIGHT_DB_PATH", "/var/lib/homesight/homesight.db")
	cfg.MQTT.BrokerURL = getEnvOrDefault("MQTT_BROKER_URL", "tcp://localhost:1883")
	cfg.Prometheus.URL = getEnvOrDefault("PROMETHEUS_URL", "http://localhost:9090")
	cfg.AI.ServiceURL = getEnvOrDefault("AI_SERVICE_URL", "http://localhost:8001")
	cfg.API.Addr = getEnvOrDefault("API_ADDR", ":8080")
	cfg.ZWave.Enabled = false
	cfg.ZWave.WebSocketURL = getEnvOrDefault("ZWAVE_WEBSOCKET_URL", "ws://localhost:3001")
	cfg.System.TemperatureUnit = getEnvOrDefault("TEMPERATURE_UNIT", "fahrenheit")
	return cfg
}
