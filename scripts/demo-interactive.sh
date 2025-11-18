#!/bin/bash
# Interactive demo script that simulates sensor lifecycle
# Run this while watching the dashboard: ./scripts/homesight.sh dashboard

API_URL="http://localhost:8080/api"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       🏠 HomeSight Interactive Demo                      ║${NC}"
echo -e "${CYAN}║       Sensor Discovery & Onboarding Simulation           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📺 Open the dashboard in another terminal:${NC}"
echo -e "   ${GREEN}./scripts/homesight.sh dashboard${NC}"
echo ""
read -p "Press Enter when dashboard is open..."
echo ""

# Function to pause between steps
pause() {
    echo ""
    read -p "Press Enter to continue..."
    echo ""
}

# Step 1: Discover basement leak sensor
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 1: 🔍 Discovering new sensor...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "Simulating Zigbee2MQTT discovering a new water leak sensor..."
pause

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement-leak-sensor-001",
    "name": "Basement Leak Sensor",
    "type": "water_leak",
    "integration": "zigbee2mqtt",
    "enabled": true,
    "metadata": {
      "manufacturer": "Aqara",
      "model": "SJCGQ11LM",
      "location": "Basement"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}✅ Device discovered and registered!${NC}"
pause

# Step 2: Add sump pump monitor
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 2: 📡 Onboarding sump pump monitor...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "Adding Shelly power monitoring switch..."
pause

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sump-pump-monitor-001",
    "name": "Sump Pump Monitor",
    "type": "power_monitor",
    "integration": "lan",
    "enabled": true,
    "metadata": {
      "manufacturer": "Shelly",
      "model": "Plug S",
      "location": "Basement",
      "ip": "192.168.1.150"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}✅ Sump pump monitor online!${NC}"
pause

# Step 3: Add temperature sensors
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 3: 🌡️  Deploying temperature sensors...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "Adding temperature/humidity sensors..."
pause

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement-temp-sensor-001",
    "name": "Basement Temperature",
    "type": "temperature",
    "integration": "zigbee2mqtt",
    "enabled": true,
    "metadata": {
      "manufacturer": "Aqara",
      "model": "WSDCGQ11LM",
      "location": "Basement"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo ""

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "attic-temp-sensor-001",
    "name": "Attic Temperature",
    "type": "temperature",
    "integration": "zigbee2mqtt",
    "enabled": true,
    "metadata": {
      "manufacturer": "Aqara",
      "model": "WSDCGQ11LM",
      "location": "Attic"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}✅ Temperature sensors deployed!${NC}"
pause

# Step 4: Simulate an incident
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 4: 🚨 Simulating water detection incident...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "Basement leak sensor detected water!"
pause

curl -s -X POST $API_URL/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "id": "incident-water-001",
    "title": "Water Detected in Basement",
    "description": "Leak sensor triggered - water detected near water heater",
    "severity": "critical",
    "deviceID": "basement-leak-sensor-001",
    "ruleName": "leak_detection",
    "data": {
      "sensor_reading": "wet",
      "location": "basement",
      "confidence": "high"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}🔴 CRITICAL incident created!${NC}"
pause

# Step 5: Add more devices
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 5: 📱 Expanding sensor network...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
pause

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "front-door-sensor-001",
    "name": "Front Door Sensor",
    "type": "contact",
    "integration": "zigbee2mqtt",
    "enabled": true,
    "metadata": {
      "manufacturer": "Aqara",
      "model": "MCCGQ11LM",
      "location": "Front Entrance"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo ""

curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "garage-door-sensor-001",
    "name": "Garage Door Sensor",
    "type": "contact",
    "integration": "zigbee2mqtt",
    "enabled": true,
    "metadata": {
      "manufacturer": "Aqara",
      "model": "MCCGQ11LM",
      "location": "Garage"
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}✅ Additional sensors online!${NC}"
pause

# Step 6: Add a warning incident
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Step 6: ⚠️  Low battery warning...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
pause

curl -s -X POST $API_URL/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "id": "incident-battery-001",
    "title": "Low Battery - Front Door Sensor",
    "description": "Battery level at 15% - replacement needed soon",
    "severity": "medium",
    "deviceID": "front-door-sensor-001",
    "ruleName": "battery_low",
    "data": {
      "battery_level": 15,
      "threshold": 20
    }
  }' | python3 -m json.tool 2>/dev/null || cat

echo -e "${CYAN}🟡 Medium priority incident logged!${NC}"
pause

# Summary
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    Demo Complete! 🎉                     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Current System Status:${NC}"
echo "  📱 6 devices registered and online"
echo "  🚨 2 active incidents (1 critical, 1 medium)"
echo "  ✅ All integrations active"
echo ""
echo -e "${YELLOW}To clean up demo data:${NC}"
echo "  ./scripts/cleanup-demo.sh"
echo ""
echo -e "${YELLOW}To view the dashboard:${NC}"
echo "  ./scripts/homesight.sh dashboard"
echo ""
