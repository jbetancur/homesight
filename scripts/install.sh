#!/bin/bash
set -e

echo "Installing HomeSight..."

# Check for root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Create homesight user if it doesn't exist
if ! id -u homesight > /dev/null 2>&1; then
    echo "Creating homesight user..."
    useradd -r -s /bin/false homesight
fi

# Create directories
echo "Creating directories..."
mkdir -p /etc/homesight
mkdir -p /var/lib/homesight/models
mkdir -p /var/log/homesight
mkdir -p /opt/homesight/ai-sidecar

# Set ownership
chown -R homesight:homesight /var/lib/homesight
chown -R homesight:homesight /var/log/homesight

# Install Go binary
echo "Installing HomeSight daemon..."
cp bin/homesightd /usr/local/bin/
chmod +x /usr/local/bin/homesightd

# Install Python AI sidecar
echo "Installing AI sidecar..."
cp -r ai-sidecar/* /opt/homesight/ai-sidecar/
chown -R homesight:homesight /opt/homesight/ai-sidecar

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r /opt/homesight/ai-sidecar/requirements.txt

# Install configuration
if [ ! -f /etc/homesight/config.yaml ]; then
    echo "Installing default configuration..."
    cp config.yaml /etc/homesight/config.yaml
    chown homesight:homesight /etc/homesight/config.yaml
else
    echo "Configuration already exists, skipping..."
fi

# Install systemd services
echo "Installing systemd services..."
cp systemd/*.service /etc/systemd/system/
systemctl daemon-reload

# Enable services
echo "Enabling services..."
systemctl enable homesightd.service
systemctl enable homesight-ai.service

echo ""
echo "HomeSight installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /etc/homesight/config.yaml for your environment"
echo "2. Place your LLM model in /var/lib/homesight/models/"
echo "3. Start services:"
echo "   sudo systemctl start homesight-ai"
echo "   sudo systemctl start homesightd"
echo "4. Check status:"
echo "   sudo systemctl status homesightd"
echo "   sudo journalctl -u homesightd -f"
