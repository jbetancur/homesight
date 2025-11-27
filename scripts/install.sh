#!/bin/bash

set -e

# HomeSight Unified Installation Script for Ubuntu
# Installs HomeSight as a production system service
# - Uses official Docker repository (not snap)
# - Downloads pre-built binaries from GitHub releases
# - Sets up systemd services for daemon and Docker containers
# - Configures everything for production deployment
#
# Based on: https://docs.docker.com/engine/install/ubuntu/

echo "🏠 HomeSight Installation for Ubuntu"
echo "====================================="
echo ""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="homesight/homesight"
RELEASE_VERSION="${HOMESIGHT_VERSION:-latest}"
INSTALL_DIR="/opt/homesight"
DATA_DIR="/var/lib/homesight"
HOMESIGHT_HOME="/home/homesight"
SYSTEMD_DIR="/etc/systemd/system"

# Check if running on Ubuntu
if [ ! -f /etc/os-release ]; then
  echo -e "${RED}Error: This script is designed for Ubuntu systems.${NC}"
  exit 1
fi

. /etc/os-release

if [ "$ID" != "ubuntu" ]; then
  echo -e "${RED}Error: This script is designed for Ubuntu. Detected: $ID${NC}"
  exit 1
fi

echo -e "${BLUE}Detected Ubuntu $VERSION_ID${NC}"
echo ""

# Check if user is root (required for system-wide installation)
if [ "$(id -u)" != "0" ]; then
  echo -e "${RED}Error: This script must be run as root.${NC}"
  echo "Please run with: sudo bash $0"
  exit 1
fi

# Clean up any conflicting Docker repository entries BEFORE first apt-get update
# This prevents "Conflicting values set for option Signed-By" errors and duplicate sources
echo "Cleaning up any conflicting Docker repository entries..."
rm -f /etc/apt/sources.list.d/docker.list
rm -f /etc/apt/sources.list.d/docker.sources
rm -f /etc/apt/keyrings/docker.gpg /etc/apt/keyrings/docker.gpg.asc
echo ""

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
  BINARY_ARCH="amd64"
  DOCKER_ARCH="amd64"
elif [ "$ARCH" = "aarch64" ]; then
  BINARY_ARCH="arm64"
  DOCKER_ARCH="arm64"
else
  echo -e "${RED}Error: Unsupported architecture: $ARCH${NC}"
  exit 1
fi

echo -e "${YELLOW}Step 1: System Update${NC}"
echo "Updating system packages..."
apt-get update -qq
echo -e "${GREEN}✓ System updated${NC}"
echo ""

# Install dependencies
echo -e "${YELLOW}Step 2: Installing Dependencies${NC}"
echo "Installing required packages..."
apt-get install -y -qq \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  wget \
  sqlite3 \
  git \
  build-essential

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Install Docker using official repository
echo -e "${YELLOW}Step 3: Installing Docker from Official Repository${NC}"
echo "Setting up Docker GPG key and repository..."

# Create directory for keyrings
mkdir -p /etc/apt/keyrings

# Add Docker GPG key (using .asc format - latest approach)
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# Set up Docker repository (using .asc key)
echo \
  "deb [arch=$DOCKER_ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index
apt-get update -qq

# Install Docker
echo "Installing Docker Engine, CLI, and Compose..."
apt-get install -y -qq \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

echo -e "${GREEN}✓ Docker installed from official repository${NC}"
echo ""

# Start Docker service
echo -e "${YELLOW}Starting Docker Service${NC}"
systemctl start docker
systemctl enable docker
echo -e "${GREEN}✓ Docker service started and enabled${NC}"
echo ""

# Create homesight system user and group
echo -e "${YELLOW}Step 4: Creating System User and Group${NC}"

# Create homesight group if it doesn't exist
if ! getent group homesight > /dev/null 2>&1; then
  echo "Creating homesight group..."
  groupadd --system homesight
  echo -e "${GREEN}✓ Group created${NC}"
else
  echo -e "${GREEN}✓ Group already exists${NC}"
fi

# Create homesight system user if it doesn't exist
if ! id -u homesight > /dev/null 2>&1; then
  echo "Creating homesight system user..."
  useradd --system --home "$HOMESIGHT_HOME" --shell /bin/false --gid homesight --create-home homesight
  echo -e "${GREEN}✓ System user created${NC}"
else
  echo -e "${GREEN}✓ System user already exists${NC}"
fi

# Add homesight to docker group
if ! groups homesight | grep -q docker; then
  usermod -aG docker homesight
  echo -e "${GREEN}✓ Added homesight to docker group${NC}"
fi

echo ""

# Create installation directories
echo -e "${YELLOW}Step 5: Creating Installation Directories${NC}"

mkdir -p "$INSTALL_DIR"/bin
mkdir -p "$HOMESIGHT_HOME"/{logs,db,manuals,rag}

chown -R homesight:homesight "$INSTALL_DIR" "$HOMESIGHT_HOME"
chmod 750 "$INSTALL_DIR" "$HOMESIGHT_HOME"

# Make directories group-accessible so homesight group members can access logs/data
chmod -R g+rx "$INSTALL_DIR" "$HOMESIGHT_HOME"

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Download binary from GitHub releases
echo -e "${YELLOW}Step 6: Downloading HomeSight Binary${NC}"

if [ "$RELEASE_VERSION" = "latest" ]; then
  DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/latest/download/homesightd-linux-$BINARY_ARCH"
  echo "Downloading latest release..."
else
  DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/download/$RELEASE_VERSION/homesightd-linux-$BINARY_ARCH"
  echo "Downloading $RELEASE_VERSION..."
fi

if curl -fsSL "$DOWNLOAD_URL" -o "$INSTALL_DIR/bin/homesightd"; then
  echo -e "${GREEN}✓ Binary downloaded from GitHub releases${NC}"
elif [ -f "./bin/homesightd" ]; then
  echo -e "${YELLOW}⚠ GitHub release not found, using local binary${NC}"
  cp ./bin/homesightd "$INSTALL_DIR/bin/homesightd"
  echo -e "${GREEN}✓ Local binary installed${NC}"
else
  echo -e "${RED}✗ Failed to find homesightd binary${NC}"
  echo ""
  echo "Possible solutions:"
  echo "  1. Build the binary from source:"
  echo "     make build"
  echo "  2. Or download from GitHub releases:"
  echo "     https://github.com/$GITHUB_REPO/releases"
  echo ""
  exit 1
fi

chmod 755 "$INSTALL_DIR/bin/homesightd"
chown homesight:homesight "$INSTALL_DIR/bin/homesightd"

echo -e "${GREEN}✓ Binary downloaded and installed${NC}"
echo ""

# Install systemd service files
echo -e "${YELLOW}Step 7: Installing Systemd Services${NC}"

cat > "$SYSTEMD_DIR/homesight.service" << EOF
[Unit]
Description=HomeSight Application
Documentation=https://github.com/$GITHUB_REPO
After=network-online.target docker.service
Wants=network-online.target
PartOf=homesight.target

[Service]
Type=simple
User=homesight
Group=homesight
WorkingDirectory=$HOMESIGHT_HOME

Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EnvironmentFile=-/etc/default/homesight

ExecStart=$INSTALL_DIR/bin/homesightd
StandardOutput=append:$HOMESIGHT_HOME/logs/daemon.log
StandardError=append:$HOMESIGHT_HOME/logs/daemon.log

Restart=always
RestartSec=10s

LimitNOFILE=65536
LimitNPROC=65536

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$INSTALL_DIR $HOMESIGHT_HOME

[Install]
WantedBy=homesight.target
EOF

cat > "$SYSTEMD_DIR/homesight-docker.service" << EOF
[Unit]
Description=HomeSight Docker Containers
Documentation=https://github.com/$GITHUB_REPO
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service
PartOf=homesight.target

[Service]
Type=oneshot
User=homesight
Group=docker
WorkingDirectory=$HOMESIGHT_HOME

ExecStart=/usr/bin/docker compose -f $HOMESIGHT_HOME/docker-compose.yml up -d
ExecStop=/usr/bin/docker compose -f $HOMESIGHT_HOME/docker-compose.yml down
RemainAfterExit=yes

Restart=always
RestartSec=10s

[Install]
WantedBy=homesight.target
EOF

chmod 644 "$SYSTEMD_DIR/homesight.service"
chmod 644 "$SYSTEMD_DIR/homesight-docker.service"

# Create homesight.target to group services
cat > "$SYSTEMD_DIR/homesight.target" << EOF
[Unit]
Description=HomeSight Application Target
Documentation=https://github.com/$GITHUB_REPO
After=network-online.target docker.service
Wants=network-online.target

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SYSTEMD_DIR/homesight.target"

systemctl daemon-reload
systemctl enable homesight.target homesight.service homesight-docker.service

echo -e "${GREEN}✓ Systemd services installed and enabled${NC}"
echo ""

# Create default configuration
echo -e "${YELLOW}Step 8: Creating Configuration${NC}"

if [ ! -f "$HOMESIGHT_HOME/config.yaml" ]; then
  cat > "$HOMESIGHT_HOME/config.yaml" << 'EOF'
# HomeSight Configuration

database:
  path: $HOMESIGHT_HOME/db/homesight.db

mqtt:
  # Optional: Specify a single broker URL for manual configuration
  # If empty, HomeSight auto-discovers ALL MQTT brokers on the network via mDNS (_mqtt._tcp)
  broker_url: ""  # Leave empty for auto-discovery (recommended)

  # Credentials (applied to all discovered brokers)
  username: ""
  password: ""

prometheus:
  url: http://localhost:9090

rag:
  batch_size_documents: 3      # For PDF/official documentation ingestion
  batch_size_community: 2      # For community source (forum/reddit/etc) ingestion

  # Known manufacturer documentation URL patterns
  manufacturers:
    Aqara:
      base_url: "https://cdn.aqara.com/cdn/website/mainland/static/docs"
      patterns:
        "SJCGQ11LM": "Water-Leak-Sensor_Manuals_EU.pdf"

queues:
  discovery:
    max_concurrent: 2
    max_queue_depth: 10
    cpu_threshold: 0.80
    memory_threshold: 0.85

  ingestion:
    max_concurrent: 2
    max_queue_depth: 5
    cpu_threshold: 0.85
    memory_threshold: 0.80

  analysis:
    max_concurrent: 4
    max_queue_depth: 20
    cpu_threshold: 0.90
    memory_threshold: 0.90

ai:
  openai_api_key: ""  # Set this from environment or .env file

  llm:
    chat_mode: "cloud"  # "cloud" = OpenAI gpt-4o-mini, "local" = Local Llama 3.2

    local:
      model_path: "./models/llama-3.2-3b-instruct.gguf"
      auto_download: true
      download_source:
        repo_id: "bartowski/Llama-3.2-3B-Instruct-GGUF"
        filename: "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
      n_ctx: 4096
      n_threads: 8
      n_gpu_layers: 0
      temperature: 0.7

    openai:
      model: "gpt-4o-mini"

    inference:
      max_concurrent_tasks: 4

api:
  addr: :8080

backend_url: "http://localhost:8080"

integrations:
  matter: true
  zigbee: true
  mqtt: true
  lan: true
EOF
  chown homesight:homesight "$HOMESIGHT_HOME/config.yaml"
  chmod 640 "$HOMESIGHT_HOME/config.yaml"
  echo -e "${GREEN}✓ Configuration created${NC}"
else
  echo -e "${GREEN}✓ Configuration already exists${NC}"
fi

# Create environment file for systemd
cat > /etc/default/homesight << EOF
# HomeSight Environment Variables
HOMESIGHT_CONFIG=$HOMESIGHT_HOME/config.yaml
HOMESIGHT_LOGS=$HOMESIGHT_HOME/logs
EOF

chmod 644 /etc/default/homesight

# Download docker-compose if needed
if [ ! -f "$HOMESIGHT_HOME/docker-compose.yml" ]; then
  echo -e "${YELLOW}Downloading docker-compose configuration...${NC}"

  if ! curl -fsSL "https://raw.githubusercontent.com/$GITHUB_REPO/main/docker-compose.yml" -o "$HOMESIGHT_HOME/docker-compose.yml"; then
    echo -e "${YELLOW}⚠ Could not download docker-compose.yml from repo${NC}"
    echo "You may need to manually copy docker-compose.yml to $HOMESIGHT_HOME/"
  else
    chown homesight:homesight "$HOMESIGHT_HOME/docker-compose.yml"
    echo -e "${GREEN}✓ docker-compose.yml downloaded${NC}"
  fi
fi

echo ""

# Summary and next steps
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ HomeSight Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Installation:${NC}"
echo "  Application:  $HOMESIGHT_HOME"
echo "  Binary:       $INSTALL_DIR/bin/homesightd"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. (Optional) Review and edit configuration:"
echo "   nano $HOMESIGHT_HOME/config.yaml"
echo ""
echo "2. Start HomeSight:"
echo "   systemctl start homesight"
echo ""
echo "3. Check status:"
echo "   systemctl status homesight"
echo ""
echo "4. View logs (all consolidated in one directory):"
echo "   Daemon logs:   tail -f $HOMESIGHT_HOME/logs/daemon.log"
echo "   Docker logs:   docker compose -f $HOMESIGHT_HOME/docker-compose.yml logs -f"
echo "   Journalctl:    journalctl -u homesight -f"
echo ""
echo "5. Access web UI:"
echo "   http://localhost:8080"
echo ""
echo -e "${YELLOW}Service Management:${NC}"
echo "  systemctl {start|stop|restart|status} homesight"
echo ""
echo "  Services are configured to auto-start on system reboot."
echo ""
echo "To manage HomeSight without sudo, add your user to the homesight group:"
echo "  sudo usermod -aG homesight \$USER"
echo "  (then log out and back in)"
echo ""
echo "Happy hacking! 🎉"
