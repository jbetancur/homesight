# HomeSight Quick Start Guide

Get HomeSight up and running in minutes.

## 5-Minute Setup

### Prerequisites

- Ubuntu 20.04 LTS or later
- User account with `sudo` access

### Installation

```bash
# 1. Clone the repository
git clone <repository-url> ~/homesight
cd ~/homesight

# 2. Run the installer (requires root/sudo)
sudo bash scripts/install.sh

# 3. The script will automatically:
#    - Download pre-built binary
#    - Set up systemd services
#    - Create configuration files

# 4. Start the services
sudo systemctl enable --now homesight-docker
sudo systemctl enable --now homesight

# 5. Access the web UI
#    http://localhost:8080
```

### Verify It's Working

In another terminal:

```bash
curl http://localhost:8080/health
```

You should see:

```json
{"status":"healthy","time":"2025-11-22T..."}
```

## Access the Web UI

Open your browser and navigate to:

```
http://localhost:8080
```

You should see the HomeSight dashboard.

## Common Tasks

### Stop HomeSight

```bash
# Stop the daemon
pkill homesightd

# Stop containers
cd ~/homesight
docker-compose down
```

### View Logs

```bash
# Daemon logs (check terminal where it's running)
# Press Ctrl+C to stop

# Docker container logs
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
```

### Rebuild After Changes

```bash
cd ~/homesight
go build -o ./bin/homesightd ./cmd/homesightd
./bin/homesightd
```

### Add Devices

Use the web UI to:

1. Navigate to Devices
2. Click "Add Device"
3. Configure your device details

## Troubleshooting

### "docker: command not found"

```bash
newgrp docker
# or log out and back in
```

### "permission denied"

```bash
# Verify docker group
groups $USER

# Should include 'docker'. If not:
sudo usermod -aG docker $USER
newgrp docker
```

### Container won't start

```bash
# Check container status
docker-compose ps

# View error logs
docker-compose logs

# Rebuild containers
docker-compose down
docker-compose up -d
```

### Port already in use

```bash
# Find what's using port 8080
lsof -i :8080

# Kill the process or use different port
export API_PORT=8081
./bin/homesightd
```

## Next Steps

- Read [INSTALL.md](INSTALL.md) for detailed installation instructions
- Check [README.md](README.md) for project overview
- Explore the web UI and add your first device
- Configure MQTT integration if needed

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 4+ GB |
| Disk | 10 GB | 50+ GB |
| Ubuntu | 20.04 LTS | 22.04 LTS or later |

## Files Created During Installation

- `~/.local/go/` - Go 1.25 installation
- `~/go/` - Go workspace
- `~/.local/bin/` - Go binaries
- `~/homesight/` - HomeSight source code
- `/var/lib/docker/` - Docker data (requires sudo to view)

## Getting Help

- Check the [Troubleshooting](#troubleshooting) section above
- Review full [INSTALL.md](INSTALL.md) guide
- Check daemon logs for error messages
- Visit GitHub Issues for bug reports

## Tips & Tricks

### Run in Background

```bash
# Use nohup
nohup ./bin/homesightd > homesight.log 2>&1 &

# Or use tmux
tmux new-session -d -s homesight './bin/homesightd'
tmux attach -t homesight  # attach later
```

### Development Setup

```bash
# Rebuild on every change
find . -name "*.go" | entr -r make

# Or use a simple loop
while true; do
  inotifywait -r . -e modify --include '\.go$'
  go build -o ./bin/homesightd ./cmd/homesightd
  # Restart service...
done
```

### View Database

```bash
# For SQLite
sqlite3 ~/.local/homesight/homesight.db

# For PostgreSQL
docker exec -it homesight-postgres psql -U homesight
```

### Check System Status

```bash
# Docker
docker ps
docker stats

# Disk usage
df -h

# Memory usage
free -h

# Network
netstat -tlnp | grep 8080
```

Enjoy! 🎉
