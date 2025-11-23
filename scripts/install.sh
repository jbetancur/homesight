#!/bin/bash

set -e

# HomeSight Unified Installation Script for Ubuntu
# Installs HomeSight as a production system service
# - Downloads pre-built binaries from GitHub releases
# - Sets up systemd services for daemon and Docker containers
# - Configures everything for production deployment

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

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
  BINARY_ARCH="amd64"
elif [ "$ARCH" = "aarch64" ]; then
  BINARY_ARCH="arm64"
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
  docker.io \
  docker-compose

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Create homesight system user and group
echo -e "${YELLOW}Step 3: Creating System User${NC}"

if ! id -u homesight > /dev/null 2>&1; then
  echo "Creating homesight system user..."
  useradd --system --home /var/lib/homesight --shell /bin/false --create-home homesight
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
echo -e "${YELLOW}Step 4: Creating Installation Directories${NC}"

mkdir -p "$INSTALL_DIR"/{bin,config}
mkdir -p "$DATA_DIR"/{db,logs,manuals,rag}

chown -R homesight:homesight "$INSTALL_DIR" "$DATA_DIR"
chmod 750 "$INSTALL_DIR" "$DATA_DIR"

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Download binary from GitHub releases
echo -e "${YELLOW}Step 5: Downloading HomeSight Binary${NC}"

if [ "$RELEASE_VERSION" = "latest" ]; then
  DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/latest/download/homesightd-linux-$BINARY_ARCH"
  echo "Downloading latest release..."
else
  DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/download/$RELEASE_VERSION/homesightd-linux-$BINARY_ARCH"
  echo "Downloading $RELEASE_VERSION..."
fi

if ! curl -fsSL "$DOWNLOAD_URL" -o "$INSTALL_DIR/bin/homesightd"; then
  echo -e "${RED}✗ Failed to download binary from GitHub releases${NC}"
  echo ""
  echo "Possible causes:"
  echo "  • Release doesn't exist yet (CI/CD not completed)"
  echo "  • Wrong version specified"
  echo ""
  echo "Available releases: https://github.com/$GITHUB_REPO/releases"
  exit 1
fi

chmod 755 "$INSTALL_DIR/bin/homesightd"
chown homesight:homesight "$INSTALL_DIR/bin/homesightd"

echo -e "${GREEN}✓ Binary downloaded and installed${NC}"
echo ""

# Install systemd service files
echo -e "${YELLOW}Step 6: Installing Systemd Services${NC}"

cat > "$SYSTEMD_DIR/homesight.service" << EOF
[Unit]
Description=HomeSight Daemon
Documentation=https://github.com/$GITHUB_REPO
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=homesight
Group=homesight
WorkingDirectory=$INSTALL_DIR

Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EnvironmentFile=-/etc/default/homesight

ExecStart=$INSTALL_DIR/bin/homesightd

Restart=always
RestartSec=10s

LimitNOFILE=65536
LimitNPROC=65536

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$DATA_DIR $INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

cat > "$SYSTEMD_DIR/homesight-docker.service" << EOF
[Unit]
Description=HomeSight Docker Containers
Documentation=https://github.com/$GITHUB_REPO
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=homesight
Group=docker
WorkingDirectory=$INSTALL_DIR

ExecStart=/usr/bin/docker-compose -f docker-compose.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.yml down
RemainAfterExit=yes

Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SYSTEMD_DIR/homesight.service"
chmod 644 "$SYSTEMD_DIR/homesight-docker.service"

systemctl daemon-reload
systemctl enable homesight homesight-docker

echo -e "${GREEN}✓ Systemd services installed and enabled${NC}"
echo ""

# Create default configuration
echo -e "${YELLOW}Step 7: Creating Configuration${NC}"

if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
  cat > "$INSTALL_DIR/config.yaml" << 'EOF'
# HomeSight Configuration
api:
  addr: "0.0.0.0:8080"

database:
  path: "/var/lib/homesight/db/homesight.db"

mqtt:
  broker_url: ""
  username: ""
  password: ""

ai:
  service_url: "http://localhost:8001"

prometheus:
  url: "http://localhost:9090"

integrations:
  mqtt: true
  zigbee: false
  matter: false
  lan: false
EOF
  chown homesight:homesight "$INSTALL_DIR/config.yaml"
  chmod 640 "$INSTALL_DIR/config.yaml"
  echo -e "${GREEN}✓ Configuration created${NC}"
else
  echo -e "${GREEN}✓ Configuration already exists${NC}"
fi

# Create environment file for systemd
cat > /etc/default/homesight << EOF
# HomeSight Environment Variables
HOMESIGHT_CONFIG=$INSTALL_DIR/config.yaml
EOF

chmod 644 /etc/default/homesight

# Download docker-compose if needed
if [ ! -f "$INSTALL_DIR/docker-compose.yml" ]; then
  echo -e "${YELLOW}Downloading docker-compose configuration...${NC}"

  if ! curl -fsSL "https://raw.githubusercontent.com/$GITHUB_REPO/main/docker-compose.yml" -o "$INSTALL_DIR/docker-compose.yml"; then
    echo -e "${YELLOW}⚠ Could not download docker-compose.yml from repo${NC}"
    echo "You may need to manually copy docker-compose.yml to $INSTALL_DIR/"
  else
    chown homesight:homesight "$INSTALL_DIR/docker-compose.yml"
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

echo -e "${YELLOW}Configuration:${NC}"
echo "  Location: $INSTALL_DIR/config.yaml"
echo "  Data dir: $DATA_DIR"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. (Optional) Review and edit configuration:"
echo "   sudo nano $INSTALL_DIR/config.yaml"
echo ""
echo "2. Start services now:"
echo "   sudo systemctl start homesight-docker"
echo "   sudo systemctl start homesight"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status homesight"
echo "   sudo systemctl status homesight-docker"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u homesight -f"
echo ""
echo "5. Access web UI:"
echo "   http://localhost:8080"
echo ""
echo -e "${YELLOW}Service Management:${NC}"
echo "  sudo systemctl {start|stop|restart|status} homesight"
echo "  sudo systemctl {start|stop|restart|status} homesight-docker"
echo ""
echo "  Services are configured to auto-start on system reboot."
echo ""
echo "Happy hacking! 🎉"
