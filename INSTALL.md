# HomeSight Installation Guide

Complete setup guide for running HomeSight on Ubuntu without requiring sudo.

## Prerequisites

- Ubuntu 20.04 LTS or later
- A user account with `sudo` privileges (for initial setup only)
- Minimum 2GB RAM
- Internet connection

## Quick Start

### Automated Installation (Recommended)

```bash
# Clone the HomeSight repository
git clone <repository-url> ~/homesight
cd ~/homesight

# Run the installer script as root
sudo bash scripts/install.sh
```

This script will:

1. Update system packages
2. Install Docker and dependencies
3. Download pre-built binary from GitHub releases
4. Set up systemd services
5. Configure everything for production

To install a specific version:

```bash
HOMESIGHT_VERSION=v1.0.0 sudo bash scripts/install.sh
```

### Manual Installation

Follow the steps below if you prefer manual installation.

## Manual Installation Steps

### Step 1: Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Step 2: Install Docker

Following [official Docker documentation](https://docs.docker.com/engine/install/ubuntu/):

```bash
# Install dependencies
sudo apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  sqlite3 \
  git

# Add Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

### Step 3: Configure Docker for Non-Root User

```bash
# Create docker group (if it doesn't exist)
sudo groupadd docker 2>/dev/null || true

# Add your user to the docker group
sudo usermod -aG docker $USER

# Activate group membership
newgrp docker

# Start Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Test Docker without sudo
docker ps
```

### Step 4: Install Go 1.25

```bash
# Create local directory
mkdir -p ~/.local

# Determine your architecture
ARCH=$(uname -m)
case $ARCH in
  x86_64) GO_ARCH="amd64" ;;
  aarch64) GO_ARCH="arm64" ;;
esac

# Download Go 1.25
cd /tmp
wget https://go.dev/dl/go1.25.0.linux-${GO_ARCH}.tar.gz

# Extract to ~/.local
tar -xzf go1.25.0.linux-${GO_ARCH}.tar.gz -C ~/.local/
rm go1.25.0.linux-${GO_ARCH}.tar.gz

# Add Go to PATH
echo 'export PATH=$PATH:$HOME/.local/go/bin:$HOME/.local/bin' >> ~/.bashrc
echo 'export GOPATH=$HOME/go' >> ~/.bashrc
echo 'export GOBIN=$HOME/.local/bin' >> ~/.bashrc

# Apply changes to current session
export PATH=$PATH:$HOME/.local/go/bin:$HOME/.local/bin
export GOPATH=$HOME/go
export GOBIN=$HOME/.local/bin

# Verify installation
go version
```

If you use `zsh`, also add to `~/.zshrc`:

```bash
echo 'export PATH=$PATH:$HOME/.local/go/bin:$HOME/.local/bin' >> ~/.zshrc
echo 'export GOPATH=$HOME/go' >> ~/.zshrc
echo 'export GOBIN=$HOME/.local/bin' >> ~/.zshrc
```

### Step 5: Install Git

```bash
sudo apt-get install -y git
```

### Step 6: Clone HomeSight Repository

```bash
cd ~
git clone <repository-url> homesight
cd homesight
```

## Post-Installation

### 1. Verify Installation

Check that all components are installed:

```bash
# Check Docker
docker --version

# Check Go
go version

# Check Git
git --version

# Test Docker without sudo
docker ps
```

Expected output:
```
Docker version 24.0.0+ (or later)
go version go1.25.0 linux/amd64
git version 2.30+
CONTAINER ID   IMAGE       COMMAND   CREATED   STATUS    PORTS     NAMES
(should show no containers initially, but no permission error)
```

### 2. Log Out and Back In (Important!)

The docker group changes won't take effect until you log out and log back in:

```bash
# Log out
exit

# Log back in and verify
docker ps
```

If you don't want to log out, you can activate group membership temporarily:

```bash
newgrp docker
```

### 3. Start Docker Containers

HomeSight uses several containerized services. Start them with:

```bash
cd ~/homesight
docker-compose up -d
```

This will start:
- PostgreSQL database (if configured)
- Redis cache (if configured)
- AI sidecar service
- Other supporting services

### 4. Build HomeSight

```bash
cd ~/homesight
go build -o ./bin/homesightd ./cmd/homesightd
```

### 5. Run HomeSight

```bash
./bin/homesightd
```

The daemon will start on port 8080 by default.

## Environment Variables

Create a `.env` file in the HomeSight directory:

```bash
# Database
DATABASE_URL=sqlite:///var/lib/homesight/homesight.db

# API
API_HOST=0.0.0.0
API_PORT=8080

# MQTT (optional)
MQTT_BROKER_URL=tcp://localhost:1883
MQTT_USERNAME=
MQTT_PASSWORD=

# AI Sidecar
AI_SERVICE_URL=http://localhost:8001

# Prometheus (optional)
PROMETHEUS_URL=http://localhost:9090
```

## Troubleshooting

### Docker Permission Denied

**Problem**: `permission denied while trying to connect to the Docker daemon`

**Solutions**:

1. Check group membership:
   ```bash
   groups $USER
   ```
   Output should include `docker`

2. If not present, add user to group:
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```

3. Restart Docker daemon:
   ```bash
   sudo systemctl restart docker
   ```

4. Log out and back in

### Go Command Not Found

**Problem**: `go: command not found`

**Solution**:

1. Check installation:
   ```bash
   ls -la ~/.local/go/bin/
   ```

2. Ensure PATH is set:
   ```bash
   echo $PATH | grep go/bin
   ```

3. If not present, add to shell config:
   ```bash
   export PATH=$PATH:$HOME/.local/go/bin
   ```

4. Apply changes:
   ```bash
   source ~/.bashrc  # or ~/.zshrc
   ```

### Docker Daemon Not Running

**Problem**: Cannot connect to Docker daemon

**Solution**:

```bash
# Start Docker
sudo systemctl start docker

# Enable auto-start on boot
sudo systemctl enable docker

# Verify
sudo systemctl status docker
```

### Port Already in Use

**Problem**: `address already in use :8080`

**Solution**:

1. Find process using port:
   ```bash
   lsof -i :8080
   ```

2. Kill process or use different port:
   ```bash
   export API_PORT=8081
   ./bin/homesightd
   ```

## Uninstallation

To remove HomeSight and related services:

```bash
# Stop running containers
cd ~/homesight
docker-compose down

# Remove HomeSight directory (optional)
rm -rf ~/homesight

# To completely remove Docker:
sudo apt-get remove docker-ce docker-ce-cli containerd.io
sudo apt-get purge docker-ce docker-ce-cli containerd.io  # Remove config
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd
sudo groupdel docker  # Remove docker group

# To remove Go:
rm -rf ~/.local/go
rm -rf ~/go
```

## Support

For issues or questions:

1. Check the [GitHub Issues](https://github.com/homesight/homesight/issues)
2. Review logs: `docker-compose logs`
3. Check daemon logs: `journalctl -u docker.service`

## Security Notes

- The Docker daemon runs with your user account (no privilege escalation)
- HomeSight database credentials should be stored securely
- Use strong MQTT broker credentials
- Consider using a reverse proxy (nginx) in production
- Regularly update Docker and Go:
  ```bash
  # Update Docker
  sudo apt-get update && sudo apt-get upgrade docker-ce

  # Update Go (download from https://go.dev/dl)
  rm -rf ~/.local/go
  # Then re-download and extract
  ```

## Next Steps

After installation:

1. Configure MQTT integration (if using)
2. Set up devices and sensors
3. Configure automation rules
4. Access web UI at `http://localhost:8080`

Enjoy HomeSight! 🏠
