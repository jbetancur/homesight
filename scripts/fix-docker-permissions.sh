#!/bin/bash
# Fix Docker permissions for WSL2
# This script adds your user to the docker group so you don't need sudo

set -e

echo "🔧 Fixing Docker permissions..."

# Check if docker group exists
if ! getent group docker > /dev/null 2>&1; then
    echo "Creating docker group..."
    sudo groupadd docker
fi

# Add current user to docker group
echo "Adding $USER to docker group..."
sudo usermod -aG docker $USER

echo ""
echo "✅ Docker permissions configured!"
echo ""
echo "⚠️  IMPORTANT: You need to log out and log back in for this to take effect."
echo ""
echo "Quick fix without logout (for current shell only):"
echo "  newgrp docker"
echo ""
echo "After that, you can run docker commands without sudo:"
echo "  docker ps"
echo "  make docker-logs"
echo ""
