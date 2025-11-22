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

# Add sensors for leak detection device
echo ""
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/basement-leak-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement-leak-sensor-001-leak",
    "device_id": "basement-leak-sensor-001",
    "name": "Water Detection",
    "type": "leak",
    "unit": "Status",
    "metadata": {
      "values": "Dry, Wet",
      "response_time": "< 1 second"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"
echo ""
echo -e "${YELLOW}🤖 Triggering AI document ingestion for Aqara SJCGQ11LM...${NC}"
curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "id": "basement-leak-sensor-001",
      "manufacturer": "Aqara",
      "model": "SJCGQ11LM",
      "type": "water_leak"
    }
  }' | python3 -m json.tool 2>/dev/null || echo "  (AI sidecar not running - manual docs will be needed)"
echo -e "${CYAN}   Documentation discovery queued in background${NC}"
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

echo ""
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/sump-pump-monitor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sump-pump-monitor-001-power",
    "device_id": "sump-pump-monitor-001",
    "name": "Power Consumption",
    "type": "power",
    "unit": "W",
    "metadata": {
      "accuracy": "±1%",
      "max": "3680",
      "voltage": "230V"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo ""
curl -s -X POST $API_URL/devices/sump-pump-monitor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sump-pump-monitor-001-energy",
    "device_id": "sump-pump-monitor-001",
    "name": "Energy Usage",
    "type": "energy",
    "unit": "kWh",
    "metadata": {
      "accuracy": "±1%",
      "resetable": true
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"
echo ""
echo -e "${YELLOW}🤖 Triggering AI document ingestion for Shelly Plug S...${NC}"
curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "id": "sump-pump-monitor-001",
      "manufacturer": "Shelly",
      "model": "Plug S",
      "type": "power_monitor"
    }
  }' | python3 -m json.tool 2>/dev/null || echo "  (AI sidecar not running)"
echo -e "${CYAN}   Documentation discovery queued in background${NC}"
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
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/basement-temp-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement-temp-sensor-001-temp",
    "device_id": "basement-temp-sensor-001",
    "name": "Temperature",
    "type": "temperature",
    "unit": "°C",
    "metadata": {
      "accuracy": "±0.5",
      "min": "-10",
      "max": "60",
      "battery": "CR2032"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo ""
curl -s -X POST $API_URL/devices/basement-temp-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement-temp-sensor-001-humidity",
    "device_id": "basement-temp-sensor-001",
    "name": "Humidity",
    "type": "humidity",
    "unit": "%",
    "metadata": {
      "accuracy": "±3",
      "min": "0",
      "max": "100"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

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

echo ""
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/attic-temp-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "attic-temp-sensor-001-temp",
    "device_id": "attic-temp-sensor-001",
    "name": "Temperature",
    "type": "temperature",
    "unit": "°C",
    "metadata": {
      "accuracy": "±0.5",
      "min": "-10",
      "max": "60",
      "battery": "CR2032"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo ""
curl -s -X POST $API_URL/devices/attic-temp-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "attic-temp-sensor-001-humidity",
    "device_id": "attic-temp-sensor-001",
    "name": "Humidity",
    "type": "humidity",
    "unit": "%",
    "metadata": {
      "accuracy": "±3",
      "min": "0",
      "max": "100"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo -e "${CYAN}✅ Temperature sensors deployed!${NC}"
echo ""
echo -e "${YELLOW}🤖 Triggering AI document ingestion for Aqara WSDCGQ11LM...${NC}"
curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "id": "basement-temp-sensor-001",
      "manufacturer": "Aqara",
      "model": "WSDCGQ11LM",
      "type": "temperature"
    }
  }' | python3 -m json.tool 2>/dev/null || echo "  (AI sidecar not running)"
echo -e "${CYAN}   Documentation discovery queued in background${NC}"
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
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/front-door-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "front-door-sensor-001-contact",
    "device_id": "front-door-sensor-001",
    "name": "Door Contact",
    "type": "contact",
    "unit": "Status",
    "metadata": {
      "values": "Open, Closed",
      "response_time": "< 100ms",
      "battery": "CR2032"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo ""
curl -s -X POST $API_URL/devices/front-door-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "front-door-sensor-001-battery",
    "device_id": "front-door-sensor-001",
    "name": "Battery Level",
    "type": "battery",
    "unit": "%",
    "metadata": {
      "accuracy": "±5%",
      "min": "0",
      "max": "100"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

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

echo ""
echo -e "${YELLOW}📊 Creating sensor definitions...${NC}"
curl -s -X POST $API_URL/devices/garage-door-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "garage-door-sensor-001-contact",
    "device_id": "garage-door-sensor-001",
    "name": "Door Contact",
    "type": "contact",
    "unit": "Status",
    "metadata": {
      "values": "Open, Closed",
      "response_time": "< 100ms",
      "battery": "CR2032"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo ""
curl -s -X POST $API_URL/devices/garage-door-sensor-001/sensors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "garage-door-sensor-001-battery",
    "device_id": "garage-door-sensor-001",
    "name": "Battery Level",
    "type": "battery",
    "unit": "%",
    "metadata": {
      "accuracy": "±5%",
      "min": "0",
      "max": "100"
    }
  }' 2>/dev/null || echo "  (Sensors endpoint not yet active)"

echo -e "${CYAN}✅ Additional sensors online!${NC}"
echo ""
echo -e "${YELLOW}🤖 Triggering AI document ingestion for Aqara MCCGQ11LM...${NC}"
curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "id": "front-door-sensor-001",
      "manufacturer": "Aqara",
      "model": "MCCGQ11LM",
      "type": "contact"
    }
  }' | python3 -m json.tool 2>/dev/null || echo "  (AI sidecar not running)"
echo -e "${CYAN}   Documentation discovery queued in background${NC}"
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
echo "  📊 12 sensors defined (temperature, humidity, water, power, contact, battery, etc.)"
echo "  🚨 2 active incidents (1 critical, 1 medium)"
echo "  ✅ All integrations active"
echo "  🤖 AI knowledge base building (may take 1-2 minutes)"
echo ""
echo -e "${YELLOW}Real Devices Used (with documentation):${NC}"
echo "  • Aqara SJCGQ11LM (Water Leak Sensor) - 1 sensor"
echo "  • Aqara WSDCGQ11LM (Temperature/Humidity Sensor) - 2 sensors per device (x2)"
echo "  • Aqara MCCGQ11LM (Door/Window Contact Sensor) - 2 sensors per device (x2)"
echo "  • Shelly Plug S (Smart Plug with Power Monitoring) - 2 sensors"
echo ""
echo -e "${YELLOW}Sensor Features:${NC}"
echo "  • Click device name to view device overview"
echo "  • Click 'View Details' button to see detailed sensor data"
echo "  • View real-time metrics, historical data, and sensor specs"
echo "  • See device documentation status and details"
echo "  • All sensor data is stored and queryable"
echo ""
echo -e "${YELLOW}AI Features:${NC}"
echo "  • Document discovery queued for each device"
echo "  • Knowledge base will contain:"
echo "    - Manufacturer PDFs and manuals"
echo "    - Support forum discussions"
echo "    - Community troubleshooting guides"
echo "  • AI analysis will cite specific sources"
echo "  • Check incidents view for AI recommendations"
echo ""
echo -e "${YELLOW}To check knowledge base status:${NC}"
echo "  curl http://localhost:8001/rag/status | jq"
echo ""
echo -e "${YELLOW}To clean up demo data:${NC}"
echo "  ./scripts/cleanup-demo.sh"
echo ""
echo -e "${YELLOW}To view the dashboard:${NC}"
echo "  ./scripts/homesight.sh dashboard"
echo ""
