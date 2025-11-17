#!/bin/bash
set -e

echo "Building HomeSight..."

# Build Go daemon
echo "Building Go daemon..."
go build -o bin/homesightd ./cmd/homesightd

# Build dashboard
echo "Building TUI dashboard..."
go build -o bin/homesight-dashboard ./cmd/dashboard

# Check if build was successful
if [ ! -f bin/homesightd ]; then
    echo "Build failed!"
    exit 1
fi

if [ ! -f bin/homesight-dashboard ]; then
    echo "Dashboard build failed!"
    exit 1
fi

echo "Build complete! Binary: bin/homesightd"
echo ""
echo "To install, run: sudo ./scripts/install.sh"
