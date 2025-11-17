# HomeSight

HomeSight is a local-only home health and maintenance monitoring system for detecting leaks, monitoring sump pumps, freeze sensors, temperature sensors, and more.

## Architecture

```mermaid
graph TB
    subgraph "Devices & Sensors"
        MQTT_DEV[MQTT Devices]
        ZIGBEE[Zigbee/Thread Devices]
        LAN_DEV[LAN REST Devices]
        MATTER[Matter Devices]
    end

    subgraph "Message Bus"
        MOSQUITTO[MQTT Broker<br/>:1883]
    end

    subgraph "HomeSight Core Daemon :8080"
        direction TB
        API[REST API Server]
        EVENTS[Event Bus]
        
        subgraph "Integrations"
            INT_MQTT[MQTT Integration]
            INT_ZIGBEE[Zigbee2MQTT]
            INT_LAN[LAN Integration]
            INT_MATTER[Matter Integration]
        end
        
        subgraph "Processing"
            RULES[Rules Engine<br/>- Leak Detection<br/>- Freeze Risk<br/>- Battery Low<br/>- Device Offline<br/>- Sump Pump Cycles]
            INCIDENTS[Incident Service]
        end
        
        subgraph "Storage"
            DB[(SQLite DB<br/>- Devices<br/>- Sensors<br/>- Incidents<br/>- Tasks<br/>- Homes/Zones/Assets)]
            METRICS[Metrics Sink]
        end
        
        AI_CLIENT[AI Client]
    end

    subgraph "AI Sidecar :8001"
        AI_API[FastAPI Server]
        LLM[Local LLM<br/>llama.cpp]
        RAG[RAG Engine<br/>- Embeddings<br/>- Vector Search]
    end

    subgraph "Monitoring"
        PROM[Prometheus<br/>:9090]
    end

    %% Device connections
    MQTT_DEV --> MOSQUITTO
    ZIGBEE --> MOSQUITTO
    LAN_DEV --> INT_LAN
    MATTER --> INT_MATTER
    
    %% Integration connections
    MOSQUITTO --> INT_MQTT
    MOSQUITTO --> INT_ZIGBEE
    INT_MQTT --> EVENTS
    INT_ZIGBEE --> EVENTS
    INT_LAN --> EVENTS
    INT_MATTER --> EVENTS
    
    %% Event processing
    EVENTS --> RULES
    RULES --> INCIDENTS
    INCIDENTS --> DB
    EVENTS --> METRICS
    
    %% API connections
    API --> INCIDENTS
    API --> DB
    API --> AI_CLIENT
    API --> METRICS
    
    %% AI connections
    AI_CLIENT -->|HTTP| AI_API
    AI_API --> LLM
    AI_API --> RAG
    
    %% Metrics
    METRICS -->|Scrape| PROM
    
    %% Styling
    classDef core fill:#4a9eff,stroke:#2d5f9f,stroke-width:2px,color:#fff
    classDef storage fill:#66bb6a,stroke:#388e3c,stroke-width:2px,color:#fff
    classDef ai fill:#ff9800,stroke:#e65100,stroke-width:2px,color:#fff
    classDef device fill:#9e9e9e,stroke:#616161,stroke-width:2px,color:#fff
    classDef bus fill:#ab47bc,stroke:#6a1b9a,stroke-width:2px,color:#fff
    
    class API,EVENTS,RULES,INCIDENTS core
    class DB,METRICS storage
    class AI_API,LLM,RAG,AI_CLIENT ai
    class MQTT_DEV,ZIGBEE,LAN_DEV,MATTER device
    class MOSQUITTO,PROM bus
```

**Components:**

- **Go Core Daemon** (`homesightd`): Main orchestrator and event processor
- **Python AI Sidecar**: Local LLM inference and RAG service
- **Prometheus**: Time-series metrics database (abstracted via interface)
- **MQTT Broker**: Message bus for sensors and devices
- **Zigbee2MQTT**: Zigbee and Thread device support
- **SQLite**: Local database for devices, incidents, and configuration
- **systemd**: Service supervision

## Design Principles

- **Interface-first**: All subsystems use Go interfaces for testability
- **Local-only**: No cloud dependencies
- **Go for orchestration**: Python only for LLM/AI workloads
- **Modular**: Each component is independently testable
- **Resilient**: Handles sensor outages, restarts, and partial failures

## Project Structure

```
homesight/
├── cmd/
│   └── homesightd/        # Main daemon entry point
├── internal/
│   ├── api/               # REST API server
│   ├── ai/                # AI client (calls Python sidecar)
│   ├── config/            # Configuration management
│   ├── db/                # SQLite repositories
│   ├── integrations/      # Device integrations (Matter, Zigbee, MQTT, LAN)
│   ├── events/            # Event bus
│   ├── metrics/           # Metrics sink (Prometheus abstraction)
│   ├── rules/             # Rules engine
│   ├── incidents/         # Incident management
│   ├── model/             # Core domain models
│   └── system/            # System utilities
├── pkg/
│   └── common/            # Shared utilities
├── ai-sidecar/            # Python AI service
├── scripts/               # Setup and deployment scripts
├── systemd/               # systemd service files
└── docs/                  # Documentation
```

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.

### One-Command Control

```bash
# Start everything (daemon + AI + Docker services)
./scripts/homesight.sh start

# Stop everything
./scripts/homesight.sh status

# Check status
./scripts/homesight.sh status

# View logs
./scripts/homesight.sh logs daemon
./scripts/homesight.sh logs ai
```

### Prerequisites

- Go 1.25+
- Python 3.10+
- Docker & Docker Compose
- SQLite3 (included)

### Build & Run

```bash
# Build
make build

# Start all services
./scripts/homesight.sh start

# Test the API
curl http://localhost:8080/health
curl http://localhost:8080/devices
curl http://localhost:8080/incidents
```

## Scripts

- `homesight.sh` - Main control script (start/stop/restart/status)
- `build.sh` - Build the Go binary
- `verify.sh` - Verify installation and dependencies
- `install.sh` - Install system-wide with systemd

## Configuration

Configuration is stored in `config.yaml` (development) or `/etc/homesight/config.yaml` (production).

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Development guide
- [API.md](docs/API.md) - API reference

## License

MIT
