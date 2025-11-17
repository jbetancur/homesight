# HomeSight Quick Start Guide

This guide will help you get HomeSight up and running quickly.

## Prerequisites

Before you begin, ensure you have:

- **Go 1.25+** installed
- **Python 3.10+** installed
- **Docker** (optional, for development services)
- **Linux system** with systemd

## Quick Development Setup

### 1. Clone and Build

```bash
cd /home/john/development/homesight

# Download Go dependencies
go mod download

# Build the daemon
make build
```

### 2. Set Up Python Virtual Environment

```bash
cd ai-sidecar
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cd ..
```

### 3. Start Development Services

The easiest way to get started is using Docker for MQTT and Prometheus:

```bash
./scripts/dev.sh
```

This will start:
- MQTT broker on `tcp://localhost:1883`
- Prometheus on `http://localhost:9090`

### 4. Configure

Edit `config.yaml` if needed. The defaults work for local development.

### 5. Run HomeSight

Open 3 terminals:

**Terminal 1 - AI Sidecar:**
```bash
cd ai-sidecar
source venv/bin/activate
python main.py
```

**Terminal 2 - HomeSight Daemon:**
```bash
export HOMESIGHT_CONFIG=$(pwd)/config.yaml
./bin/homesightd
```

**Terminal 3 - Test the API:**
```bash
# Health check
curl http://localhost:8080/health

# List devices
curl http://localhost:8080/devices

# List incidents
curl http://localhost:8080/incidents

# AI chat test (requires AI sidecar running)
curl -X POST http://localhost:8080/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is HomeSight?"}'
```

## Production Installation

### 1. Build

```bash
make build
```

### 2. Install System-Wide

```bash
sudo ./scripts/install.sh
```

This will:
- Create `homesight` user and directories
- Install binaries to `/usr/local/bin`
- Install configuration to `/etc/homesight`
- Install systemd service files
- Enable services

### 3. Configure

Edit `/etc/homesight/config.yaml` for your environment.

### 4. Install LLM Model (Optional)

Download a GGUF model and place it in `/var/lib/homesight/models/`:

```bash
# Example: Download a small model
wget https://huggingface.co/.../llama-2-7b-chat.gguf \
  -O /var/lib/homesight/models/llama-2-7b-chat.gguf
```

### 5. Start Services

```bash
sudo systemctl start homesight-ai
sudo systemctl start homesightd
```

### 6. Check Status

```bash
# View status
sudo systemctl status homesightd

# Follow logs
sudo journalctl -u homesightd -f
```

## Adding Your First Device

### MQTT Device

Publish device data to MQTT:

```bash
mosquitto_pub -h localhost -t "homesight/sensor_1/state" \
  -m '{"device_id":"sensor_1","sensor_id":"sensor_1","value":23.5}'
```

### Zigbee Device

1. Install and configure Zigbee2MQTT
2. Set `integrations.zigbee: true` in `config.yaml`
3. Restart homesightd
4. Devices will be discovered automatically

### LAN Device (Shelly, Tapo, etc.)

Add to the LAN integration in code or via API (future enhancement).

## Viewing Data

### API Endpoints

```bash
# List all devices
curl http://localhost:8000/devices

# List open incidents
curl http://localhost:8000/incidents?status=open

# Get metrics for a sensor
curl "http://localhost:8000/metrics/sensor_1?from=2024-01-01T00:00:00Z"
```

### Database

```bash
sqlite3 /var/lib/homesight/homesight.db
.tables
SELECT * FROM devices;
SELECT * FROM incidents WHERE status='open';
```

## Troubleshooting

### HomeSight won't start

1. Check logs: `sudo journalctl -u homesightd -n 50`
2. Verify config file exists and is valid
3. Check database permissions
4. Ensure MQTT broker is running

### AI service not responding

1. Check AI service logs: `sudo journalctl -u homesight-ai -n 50`
2. Verify Python dependencies are installed
3. Check if model file exists (optional, will use mock if missing)

### No devices discovered

1. Check integration configuration in `config.yaml`
2. Verify MQTT broker is accessible
3. Check device-specific setup (Zigbee2MQTT, etc.)

### MQTT connection failed

1. Ensure mosquitto is running: `sudo systemctl status mosquitto`
2. Check broker URL in config
3. Test connection: `mosquitto_sub -h localhost -t '#' -v`

## Next Steps

1. **Read the Documentation**
   - [Architecture](docs/ARCHITECTURE.md) - System design
   - [Development Guide](docs/DEVELOPMENT.md) - Contributing
   - [API Reference](docs/API.md) - HTTP API

2. **Add Integrations**
   - Configure your sensor protocols
   - Add device-specific integrations

3. **Customize Rules**
   - Edit `internal/rules/default.go`
   - Add custom detection rules

4. **Set Up Monitoring**
   - Configure Prometheus dashboards
   - Set up alerting

5. **Enhance AI**
   - Add domain-specific knowledge to RAG
   - Fine-tune prompts for your use case

## Getting Help

- Check logs: `sudo journalctl -u homesightd -f`
- Review documentation in `docs/`
- Check configuration: `/etc/homesight/config.yaml`
- Verify service status: `sudo systemctl status homesightd`

## Common Commands

```bash
# Start services
sudo systemctl start homesightd
sudo systemctl start homesight-ai

# Stop services
sudo systemctl stop homesightd
sudo systemctl stop homesight-ai

# Restart after config changes
sudo systemctl restart homesightd

# View logs
sudo journalctl -u homesightd -f
sudo journalctl -u homesight-ai -f

# Check status
sudo systemctl status homesightd
sudo systemctl status homesight-ai

# Rebuild and reinstall
make build
sudo systemctl stop homesightd
sudo cp bin/homesightd /usr/local/bin/
sudo systemctl start homesightd
```
