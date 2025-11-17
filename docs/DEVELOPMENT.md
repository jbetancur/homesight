# HomeSight Development Guide

## Getting Started

### Prerequisites

- Go 1.21 or later
- Python 3.10 or later
- Docker (for development services)
- SQLite3
- Make (optional but recommended)

### Initial Setup

1. Clone the repository:
```bash
cd /home/john/development/homesight
```

2. Install Go dependencies:
```bash
go mod download
```

3. Install Python dependencies:
```bash
cd ai-sidecar
pip install -r requirements.txt
cd ..
```

4. Start development services:
```bash
chmod +x scripts/*.sh
./scripts/dev.sh
```

## Project Structure

```
homesight/
├── cmd/
│   └── homesightd/        # Main daemon entry point
├── internal/              # Private application code
│   ├── api/              # REST API server
│   ├── ai/               # AI client interface
│   ├── config/           # Configuration management
│   ├── db/               # Database repositories
│   ├── events/           # Event bus implementation
│   ├── incidents/        # Incident service
│   ├── integrations/     # Device integrations
│   ├── metrics/          # Metrics sink implementations
│   ├── model/            # Domain models
│   └── rules/            # Rules engine
├── ai-sidecar/           # Python AI service
├── systemd/              # systemd service files
├── scripts/              # Build and deployment scripts
└── docs/                 # Documentation
```

## Building

### Build the Go daemon:
```bash
make build
# or
go build -o bin/homesightd ./cmd/homesightd
```

### Run tests:
```bash
make test
# or
go test -v ./...
```

## Running Locally

### Terminal 1 - Start development services:
```bash
./scripts/dev.sh
```

### Terminal 2 - Start AI sidecar:
```bash
cd ai-sidecar
python main.py
```

### Terminal 3 - Start Go daemon:
```bash
export HOMESIGHT_CONFIG=./config.yaml
go run cmd/homesightd/main.go
```

## Adding a New Integration

1. Create a new file in `internal/integrations/`:
```go
package integrations

type MyIntegration struct {
    // fields
}

func NewMyIntegration() *MyIntegration {
    return &MyIntegration{}
}

func (i *MyIntegration) Discover(ctx context.Context) ([]model.DeviceDescriptor, error) {
    // implementation
}

func (i *MyIntegration) Subscribe(ctx context.Context, events chan<- model.DeviceEvent) error {
    // implementation
}

func (i *MyIntegration) Control(ctx context.Context, cmd model.DeviceCommand) error {
    // implementation
}

func (i *MyIntegration) Close() error {
    return nil
}
```

2. Register it in `cmd/homesightd/main.go`

## Adding a New Rule

1. Add rule logic to `internal/rules/default.go`
2. Add a check method following the pattern:
```go
func (e *DefaultRuleEngine) checkMyRule(event model.DeviceEvent) *model.Incident {
    // rule logic
    if condition {
        return &model.Incident{
            // incident details
        }
    }
    return nil
}
```

3. Call it from `Process()` method

## Testing

### Unit Tests
```bash
go test ./internal/...
```

### Integration Tests
```bash
# Start test services
docker-compose -f test/docker-compose.yml up -d

# Run tests
go test -tags=integration ./...
```

### Python Tests
```bash
cd ai-sidecar
pytest
```

## Code Style

### Go
- Follow standard Go conventions
- Run `gofmt` before committing
- Use meaningful variable names
- Add comments for exported types and functions

### Python
- Follow PEP 8
- Use type hints
- Run `black` for formatting

## Debugging

### View logs:
```bash
# Go daemon
journalctl -u homesightd -f

# AI sidecar
journalctl -u homesight-ai -f
```

### Check database:
```bash
sqlite3 /var/lib/homesight/homesight.db
.tables
.schema devices
```

### Test API:
```bash
# Health check
curl http://localhost:8000/health

# List devices
curl http://localhost:8000/devices

# List incidents
curl http://localhost:8000/incidents

# AI chat
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I winterize my pipes?"}'
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Run tests and linting
5. Submit a pull request

## Common Issues

### "Cannot connect to MQTT broker"
- Ensure mosquitto is running: `systemctl status mosquitto`
- Check broker URL in config.yaml

### "Database locked"
- Ensure only one instance of homesightd is running
- Check file permissions on database file

### "AI service unavailable"
- Ensure Python service is running
- Check AI service URL in config.yaml
- Verify model file exists in configured location
