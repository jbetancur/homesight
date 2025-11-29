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

	// Set defaults
	if cfg.Database.Path == "" {
		cfg.Database.Path = "/var/lib/homesight/homesight.db"
	}
	if cfg.MQTT.BrokerURL == "" {
		cfg.MQTT.BrokerURL = "tcp://localhost:1883"
	}
	if cfg.Prometheus.URL == "" {
		cfg.Prometheus.URL = "http://localhost:9090"
	}
	if cfg.AI.ServiceURL == "" {
		cfg.AI.ServiceURL = "http://localhost:8001"
	}
	if cfg.API.Addr == "" {
		cfg.API.Addr = ":8000"
	}
	if cfg.ZWave.WebSocketURL == "" {
		cfg.ZWave.WebSocketURL = "ws://localhost:3001"
	}

	return &cfg, nil
}

// Default returns a configuration with default values
func Default() *Config {
	cfg := &Config{}
	cfg.Database.Path = "/var/lib/homesight/homesight.db"
	cfg.MQTT.BrokerURL = "tcp://localhost:1883"
	cfg.Prometheus.URL = "http://localhost:9090"
	cfg.AI.ServiceURL = "http://localhost:8001"
	cfg.API.Addr = ":8000"
	cfg.ZWave.Enabled = false
	cfg.ZWave.WebSocketURL = "ws://localhost:3001"
	return cfg
}
