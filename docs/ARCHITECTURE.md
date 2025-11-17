# HomeSight Architecture

## Overview

HomeSight is a local-only home monitoring and maintenance system designed for reliability, modularity, and privacy. The system consists of a Go-based core daemon and a Python-based AI sidecar.

## Core Principles

1. **Interface-First Design**: All major components use Go interfaces for testability and flexibility
2. **Local-Only Operation**: No cloud dependencies, all data stays local
3. **Separation of Concerns**: Go handles orchestration, Python handles AI/ML
4. **Resilient by Design**: Handles failures gracefully, recovers from restarts
5. **Modular**: Components can be developed and tested independently

## System Components

### Go Core Daemon (`homesightd`)

The main orchestrator written in Go. Responsibilities:
- Device integration and discovery
- Event bus for distributing sensor readings
- Rules engine for incident detection
- Incident management
- Metrics collection and storage interface
- REST API server
- SQLite database management

### Python AI Sidecar

Python service for all AI/ML operations:
- Local LLM inference using llama.cpp
- RAG (Retrieval-Augmented Generation) for home maintenance knowledge
- Metric anomaly detection
- Incident analysis and recommendations
- Chat interface for user assistance

### Supporting Services

- **MQTT Broker** (Mosquitto): Message bus for sensors and integrations
- **Prometheus**: Time-series database for metrics (abstracted via interface)
- **Zigbee2MQTT**: Bridge for Zigbee and Thread devices
- **SQLite**: Local database for configuration and state

## Data Flow

```
Sensors/Devices
     ↓
Integration Layer (Matter, Zigbee, MQTT, LAN)
     ↓
Event Bus
     ↓
  ┌──┴──┐
  ↓     ↓     ↓
Rules  Metrics  Logging
Engine  Sink
  ↓
Incident
Service
  ↓
Database / API
```

## Integration Layer

All device integrations implement the `Integration` interface:

```go
type Integration interface {
    Discover(ctx context.Context) ([]DeviceDescriptor, error)
    Subscribe(ctx context.Context, events chan<- DeviceEvent) error
    Control(ctx context.Context, cmd DeviceCommand) error
}
```

Supported integrations:
- **Matter**: Auto-discovery of Matter devices (placeholder for full implementation)
- **Zigbee2MQTT**: Zigbee devices via MQTT bridge
- **MQTT**: Generic MQTT sensor support
- **LAN**: REST-based devices (Shelly, Tapo, Govee)

## Event Bus

Central pub/sub mechanism for device events. All sensor readings flow through the event bus, allowing multiple consumers to process events independently.

## Rules Engine

Evaluates events against configured rules to detect issues:
- Leak detection (critical)
- Freeze risk detection (temperature thresholds)
- Sump pump cycle monitoring
- Device offline detection
- Low battery alerts

Rules can be extended by implementing the `RuleEngine` interface.

## Metrics Storage

Abstracted via `MetricsSink` interface with implementations:
- **PrometheusMetricsSink**: Production metrics storage
- **MockMetricsSink**: In-memory testing

This abstraction allows swapping time-series databases without changing application code.

## Database Schema

SQLite stores all persistent data:
- **homes**: Top-level location
- **zones**: Logical areas within home
- **assets**: Physical equipment (sump pumps, water heaters, etc.)
- **devices**: Sensors and actuators
- **sensors**: Individual sensor channels
- **incidents**: Detected issues and alerts
- **tasks**: Maintenance and action items

## API

REST API provides access to all system data and operations:
- `GET /incidents` - List incidents
- `GET /devices` - List devices
- `GET /metrics/{sensorID}` - Query sensor metrics
- `POST /ai/chat` - Chat with AI assistant
- `POST /ai/analyze` - Request AI analysis

## Security Considerations

- Local-only operation eliminates cloud attack surface
- systemd sandboxing with `ProtectSystem=strict`
- Minimal privileges for service accounts
- No external network access required

## Deployment

Services are managed by systemd with proper dependencies:
1. MQTT broker starts first
2. Zigbee2MQTT depends on MQTT
3. Prometheus starts independently
4. AI sidecar starts with homesightd
5. homesightd orchestrates everything

## Testing Strategy

- Unit tests for all business logic
- Mock implementations for all interfaces
- Integration tests with in-memory database
- End-to-end tests with real MQTT broker
