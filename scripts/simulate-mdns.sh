#!/bin/bash
#
# Simulate mDNS/Zeroconf traffic for testing HomeSight discovery
#
# This script uses avahi-publish-service to broadcast fake devices
# that HomeSight can discover via mDNS
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                              ║${NC}"
echo -e "${BLUE}║          🔍  mDNS Traffic Simulator  🔍                     ║${NC}"
echo -e "${BLUE}║                                                              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if avahi-publish-service is available
if ! command -v avahi-publish-service &> /dev/null; then
    echo -e "${RED}❌ avahi-publish-service not found${NC}"
    echo -e "Install with: ${YELLOW}sudo apt-get install avahi-utils${NC}"
    exit 1
fi

# Check if avahi-daemon is running
if ! systemctl is-active --quiet avahi-daemon 2>/dev/null; then
    echo -e "${RED}❌ avahi-daemon is not running${NC}"
    echo -e "Start with: ${YELLOW}sudo systemctl start avahi-daemon${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Avahi daemon is running${NC}"
echo ""

# Create temp directory for PIDs
TEMP_DIR=$(mktemp -d)
trap "cleanup" EXIT

cleanup() {
    echo ""
    echo -e "${YELLOW}🧹 Stopping simulated services...${NC}"
    
    # Kill all background jobs
    jobs -p | xargs -r kill 2>/dev/null || true
    
    # Remove temp directory
    rm -rf "$TEMP_DIR"
    
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

echo -e "${BLUE}📡 Broadcasting simulated devices...${NC}"
echo ""

# Function to publish a service
publish_service() {
    local name=$1
    local service=$2
    local port=$3
    local txt=$4
    
    echo -e "   ${GREEN}▶${NC} $name"
    avahi-publish-service "$name" "$service" "$port" $txt > /dev/null 2>&1 &
    echo $! >> "$TEMP_DIR/pids.txt"
}

# Simulate MQTT Brokers
echo -e "${CYAN}MQTT Brokers:${NC}"
publish_service "Test MQTT Broker" "_mqtt._tcp" 1883 ""
publish_service "Home Assistant MQTT" "_mqtt._tcp" 1883 ""
sleep 1

# Simulate Shelly devices
echo ""
echo -e "${CYAN}Shelly Devices:${NC}"
publish_service "shelly-plug-kitchen" "_http._tcp" 80 "model=Shelly Plug S"
publish_service "shelly-dimmer-livingroom" "_http._tcp" 80 "model=Shelly Dimmer 2"
publish_service "shelly-1pm-garage" "_http._tcp" 80 "model=Shelly 1PM"
sleep 1

# Simulate Tasmota devices
echo ""
echo -e "${CYAN}Tasmota Devices:${NC}"
publish_service "tasmota-switch-01" "_http._tcp" 80 "tasmota=1 model=Basic"
publish_service "tasmota-sensor-temp" "_http._tcp" 80 "tasmota=1 model=TH16"
sleep 1

# Simulate ESPHome devices
echo ""
echo -e "${CYAN}ESPHome Devices:${NC}"
publish_service "esphome-doorbell" "_esphomelib._tcp" 6053 ""
publish_service "esphome-garage-sensor" "_esphomelib._tcp" 6053 ""
sleep 1

# Simulate Matter devices
echo ""
echo -e "${CYAN}Matter Devices:${NC}"
publish_service "matter-light-01" "_matter._tcp" 5540 ""
publish_service "matter-sensor-02" "_matter._tcp" 5540 ""
sleep 1

# Simulate Z-Wave JS gateway
echo ""
echo -e "${CYAN}Z-Wave Gateway:${NC}"
publish_service "zwavejs2mqtt" "_z-wave-js._tcp" 3000 "version=8.0.0"
sleep 1

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ All simulated services are broadcasting!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${BLUE}📊 Summary:${NC}"
echo -e "   2 MQTT Brokers"
echo -e "   3 Shelly Devices"
echo -e "   2 Tasmota Devices"
echo -e "   2 ESPHome Devices"
echo -e "   2 Matter Devices"
echo -e "   1 Z-Wave Gateway"
echo ""

echo -e "${YELLOW}🧪 Testing Discovery:${NC}"
echo ""
echo -e "1. In another terminal, query HomeSight discovery API:"
echo -e "   ${GREEN}curl http://localhost:8080/api/discovery | jq${NC}"
echo ""
echo -e "2. Or use the dashboard:"
echo -e "   ${GREEN}./scripts/homesight.sh dashboard${NC}"
echo -e "   ${GREEN}Press TAB to switch to Discovery view${NC}"
echo ""
echo -e "3. Or check with avahi-browse:"
echo -e "   ${GREEN}avahi-browse -a -t${NC}"
echo ""

echo -e "${BLUE}Press Ctrl+C to stop all simulated services${NC}"
echo ""

# Keep script running
wait
