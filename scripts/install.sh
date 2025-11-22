#!/bin/bash
#
# HomeSight Installation Script for Ubuntu/Debian
# Supports: Ubuntu 20.04+, Debian 11+, Raspberry Pi OS
#
# Usage: 
#   curl -fsSL https://raw.githubusercontent.com/jbetancur/homesight/main/install.sh | bash
#   or
#   ./install.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/homesight"
CONFIG_DIR="/etc/homesight"
DATA_DIR="/var/lib/homesight"
LOG_DIR="/var/log/homesight"
SERVICE_USER="homesight"

echo -e "${BLUE}"
cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              🏠  HomeSight Installer  🏠                    ║
║                                                              ║
║     Smart Home Intelligence & Device Management              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}" 
   exit 1
fi

echo -e "${GREEN}🔍 Checking system compatibility...${NC}"

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
    echo -e "   OS: $OS $VER"
else
    echo -e "${RED}Cannot detect OS. This script supports Ubuntu/Debian only.${NC}"
    exit 1
fi

# Check architecture
ARCH=$(uname -m)
echo -e "   Architecture: $ARCH"

if [[ "$ARCH" != "x86_64" && "$ARCH" != "aarch64" && "$ARCH" != "armv7l" ]]; then
    echo -e "${YELLOW}⚠️  Warning: Untested architecture. May have issues.${NC}"
fi

echo ""
echo -e "${GREEN}📦 Installing system dependencies...${NC}"

# Update package lists
apt-get update -qq

# Install required packages
echo -e "   Installing core dependencies..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    build-essential \
    sqlite3 \
    ca-certificates \
    gnupg \
    lsb-release \
    avahi-daemon \
    avahi-utils \
    libnss-mdns \
    > /dev/null 2>&1

echo -e "${GREEN}✅ System dependencies installed${NC}"

# Install Go
echo ""
echo -e "${GREEN}🔧 Installing Go 1.23...${NC}"

GO_VERSION="1.25.4"
GO_ARCH=""
case "$ARCH" in
    x86_64)
        GO_ARCH="amd64"
        ;;
    aarch64)
        GO_ARCH="arm64"
        ;;
    armv7l)
        GO_ARCH="armv6l"
        ;;
    *)
        echo -e "${RED}Unsupported architecture for Go: $ARCH${NC}"
        exit 1
        ;;
esac

if ! command -v go &> /dev/null; then
    GO_TAR="go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
    
    echo -e "   Downloading Go ${GO_VERSION}..."
    wget -q "https://go.dev/dl/${GO_TAR}" -O "/tmp/${GO_TAR}"
    
    echo -e "   Installing Go..."
    rm -rf /usr/local/go
    tar -C /usr/local -xzf "/tmp/${GO_TAR}"
    rm "/tmp/${GO_TAR}"
    
    # Add to PATH
    if ! grep -q "/usr/local/go/bin" /etc/environment; then
        echo 'PATH="/usr/local/go/bin:$PATH"' >> /etc/environment
    fi
    
    export PATH="/usr/local/go/bin:$PATH"
    echo -e "${GREEN}✅ Go ${GO_VERSION} installed${NC}"
else
    GO_CURRENT=$(go version | awk '{print $3}' | sed 's/go//')
    echo -e "   Go already installed: ${GO_CURRENT}"
fi

# Install Python 3.10+
echo ""
echo -e "${GREEN}🐍 Setting up Python environment...${NC}"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
REQUIRED_PYTHON="3.10"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 not found. Installing...${NC}"
    apt-get install -y python3 python3-pip python3-venv
elif [ "$(printf '%s\n' "$REQUIRED_PYTHON" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_PYTHON" ]; then
    echo -e "${RED}Python ${PYTHON_VERSION} found. HomeSight requires Python ${REQUIRED_PYTHON}+${NC}"
    echo -e "${YELLOW}Installing Python 3.10+...${NC}"
    apt-get install -y python3.10 python3.10-venv python3-pip || apt-get install -y python3 python3-venv python3-pip
else
    echo -e "   Python ${PYTHON_VERSION} found ✅"
fi

apt-get install -y python3-pip python3-venv

echo -e "${GREEN}✅ Python environment ready${NC}"

# Install Docker (optional but recommended)
echo ""
echo -e "${GREEN}🐳 Checking Docker...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "   Docker not found. Would you like to install Docker? (recommended for Prometheus/MQTT)"
    read -p "   Install Docker? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        echo -e "   Installing Docker..."
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
        sh /tmp/get-docker.sh > /dev/null 2>&1
        rm /tmp/get-docker.sh
        
        # Install Docker Compose
        DOCKER_COMPOSE_VERSION="2.24.0"
        curl -SL "https://github.com/docker/compose/releases/download/v${DOCKER_COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        
        systemctl enable docker
        systemctl start docker
        echo -e "${GREEN}✅ Docker installed${NC}"
    else
        echo -e "${YELLOW}⚠️  Skipping Docker. You'll need to run MQTT/Prometheus separately.${NC}"
    fi
else
    echo -e "   Docker already installed ✅"
fi

# Create system user
echo ""
echo -e "${GREEN}👤 Creating HomeSight user...${NC}"

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false $SERVICE_USER
    echo -e "   User '$SERVICE_USER' created"
else
    echo -e "   User '$SERVICE_USER' already exists"
fi

# Add to docker group if Docker is installed
if command -v docker &> /dev/null; then
    usermod -aG docker $SERVICE_USER || true
fi

# Create directories
echo ""
echo -e "${GREEN}📁 Creating directories...${NC}"

mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"/{db,rag,manuals}
mkdir -p "$LOG_DIR"

echo -e "   $INSTALL_DIR"
echo -e "   $CONFIG_DIR"
echo -e "   $DATA_DIR"
echo -e "   $LOG_DIR"

# # Clone or update repository
# echo ""
# echo -e "${GREEN}📥 Downloading HomeSight...${NC}"

# if [ -d "$INSTALL_DIR/.git" ]; then
#     echo -e "   Updating existing installation..."
#     cd "$INSTALL_DIR"
#     git pull origin main
# else
#     echo -e "   Cloning repository..."
#     git clone https://github.com/jbetancur/homesight.git "$INSTALL_DIR"
# fi

cd "$INSTALL_DIR"

# Build Go daemon
echo ""
echo -e "${GREEN}🔨 Building HomeSight daemon...${NC}"

export PATH="/usr/local/go/bin:$PATH"
make build

if [ ! -f "$INSTALL_DIR/bin/homesightd" ]; then
    echo -e "${RED}Failed to build HomeSight daemon${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Daemon built successfully${NC}"

# Set up Python AI sidecar
echo ""
echo -e "${GREEN}🤖 Setting up AI sidecar...${NC}"

cd "$INSTALL_DIR/ai-sidecar"

# Remove old venv if it exists and is broken
if [ -d "venv" ] && [ ! -f "venv/bin/python" ]; then
    echo -e "   Removing broken virtual environment..."
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    echo -e "   Creating Python virtual environment..."
    python3 -m venv venv
    
    if [ ! -f "venv/bin/python" ]; then
        echo -e "${RED}Failed to create Python virtual environment${NC}"
        exit 1
    fi
fi

echo -e "   Installing Python dependencies (this may take a few minutes)..."
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip > /dev/null 2>&1

# Install dependencies with better error handling
if ! pip install -r requirements.txt; then
    echo -e "${RED}Failed to install Python dependencies${NC}"
    echo -e "${YELLOW}Please check the error above and ensure you have:${NC}"
    echo -e "  - Python 3.10+ installed"
    echo -e "  - Internet connection"
    echo -e "  - Sufficient disk space"
    deactivate
    exit 1
fi

deactivate

echo -e "${GREEN}✅ AI sidecar ready${NC}"

# Create configuration
echo ""
echo -e "${GREEN}⚙️  Setting up configuration...${NC}"

if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml" "$CONFIG_DIR/config.yaml"
    
    # Update paths in config
    sed -i "s|path: ./data/homesight.db|path: $DATA_DIR/homesight.db|g" "$CONFIG_DIR/config.yaml"
    
    echo -e "   Configuration created at $CONFIG_DIR/config.yaml"
    echo -e "${YELLOW}   ⚠️  Please edit $CONFIG_DIR/config.yaml with your settings${NC}"
else
    echo -e "   Configuration already exists at $CONFIG_DIR/config.yaml"
fi

# Create systemd services
echo ""
echo -e "${GREEN}🚀 Creating systemd services...${NC}"

# HomeSight Daemon service
cat > /etc/systemd/system/homesight.service << EOF
[Unit]
Description=HomeSight Smart Home Intelligence Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="HOMESIGHT_CONFIG=$CONFIG_DIR/config.yaml"
ExecStart=$INSTALL_DIR/bin/homesightd
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/daemon.log
StandardError=append:$LOG_DIR/daemon.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR

[Install]
WantedBy=multi-user.target
EOF

# AI Sidecar service
cat > /etc/systemd/system/homesight-ai.service << EOF
[Unit]
Description=HomeSight AI Sidecar Service
After=network-online.target homesight.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/ai-sidecar
Environment="HOMESIGHT_CONFIG=$CONFIG_DIR/config.yaml"
ExecStart=$INSTALL_DIR/ai-sidecar/venv/bin/python $INSTALL_DIR/ai-sidecar/main.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/ai.log
StandardError=append:$LOG_DIR/ai.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR

[Install]
WantedBy=multi-user.target
EOF

echo -e "   Created homesight.service"
echo -e "   Created homesight-ai.service"

# Set permissions
echo ""
echo -e "${GREEN}🔒 Setting permissions...${NC}"

chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"
chown -R $SERVICE_USER:$SERVICE_USER "$DATA_DIR"
chown -R $SERVICE_USER:$SERVICE_USER "$LOG_DIR"
chown root:$SERVICE_USER "$CONFIG_DIR/config.yaml"
chmod 640 "$CONFIG_DIR/config.yaml"

# Reload systemd
systemctl daemon-reload

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ HomeSight installation complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📝 Next steps:${NC}"
echo ""
echo -e "1. Edit configuration:"
echo -e "   ${YELLOW}sudo nano $CONFIG_DIR/config.yaml${NC}"
echo ""
echo -e "2. Start HomeSight services:"
echo -e "   ${YELLOW}sudo systemctl enable homesight homesight-ai${NC}"
echo -e "   ${YELLOW}sudo systemctl start homesight homesight-ai${NC}"
echo ""
echo -e "3. Check status:"
echo -e "   ${YELLOW}sudo systemctl status homesight${NC}"
echo -e "   ${YELLOW}sudo systemctl status homesight-ai${NC}"
echo ""
echo -e "4. View logs:"
echo -e "   ${YELLOW}sudo journalctl -u homesight -f${NC}"
echo -e "   ${YELLOW}tail -f $LOG_DIR/daemon.log${NC}"
echo ""
echo -e "5. Access services:"
echo -e "   ${YELLOW}http://localhost:8080${NC} - HomeSight API"
echo -e "   ${YELLOW}http://localhost:8001${NC} - AI Service"
echo ""

if command -v docker &> /dev/null; then
    echo -e "6. Start Docker services (optional):"
    echo -e "   ${YELLOW}cd $INSTALL_DIR && sudo docker compose up -d${NC}"
    echo ""
fi

echo -e "${BLUE}📚 Documentation:${NC}"
echo -e "   README: $INSTALL_DIR/README.md"
echo -e "   Config: $CONFIG_DIR/config.yaml"
echo -e "   Logs:   $LOG_DIR/"
echo ""
echo -e "${GREEN}Happy home automating! 🏠${NC}"
