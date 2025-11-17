#!/bin/bash
# Test auto-discovery for all supported protocols

echo "🔍 HomeSight Auto-Discovery Test"
echo "================================="
echo ""

echo "Scanning network for 10 seconds..."
echo ""

# Run a Go program to test discovery
cat > /tmp/test_discovery.go << 'EOF'
package main

import (
	"fmt"
	"time"
	"github.com/homesight/homesight/internal/discovery"
)

func main() {
	fmt.Println("📡 MQTT Brokers:")
	brokers, _ := discovery.DiscoverMQTTBrokers(5 * time.Second)
	if len(brokers) == 0 {
		fmt.Println("  (none found)")
	}
	for _, b := range brokers {
		fmt.Printf("  ✓ %s at %s:%d\n", b.Name, b.Host, b.Port)
	}
	fmt.Println()

	fmt.Println("🏠 Matter Devices:")
	matter, _ := discovery.DiscoverMatterDevices(5 * time.Second)
	if len(matter) == 0 {
		fmt.Println("  (none found)")
	}
	for _, d := range matter {
		fmt.Printf("  ✓ %s at %s:%d\n", d.Name, d.Host, d.Port)
	}
	fmt.Println()

	fmt.Println("💡 Shelly Devices:")
	shelly, _ := discovery.DiscoverShellyDevices(5 * time.Second)
	if len(shelly) == 0 {
		fmt.Println("  (none found)")
	}
	for _, d := range shelly {
		fmt.Printf("  ✓ %s (%s) at %s:%d\n", d.Name, d.Model, d.Host, d.Port)
	}
	fmt.Println()

	fmt.Println("🔌 Tasmota Devices:")
	tasmota, _ := discovery.DiscoverTasmotaDevices(5 * time.Second)
	if len(tasmota) == 0 {
		fmt.Println("  (none found)")
	}
	for _, d := range tasmota {
		fmt.Printf("  ✓ %s at %s:%d\n", d.Name, d.Host, d.Port)
	}
	fmt.Println()

	fmt.Println("🌐 ESPHome Devices:")
	esphome, _ := discovery.DiscoverESPHomeDevices(5 * time.Second)
	if len(esphome) == 0 {
		fmt.Println("  (none found)")
	}
	for _, d := range esphome {
		fmt.Printf("  ✓ %s at %s:%d\n", d.Name, d.Host, d.Port)
	}
	fmt.Println()

	fmt.Println("Summary:")
	total := len(brokers) + len(matter) + len(shelly) + len(tasmota) + len(esphome)
	fmt.Printf("  Total devices discovered: %d\n", total)
}
EOF

cd /home/john/development/homesight
go run /tmp/test_discovery.go
rm /tmp/test_discovery.go

echo ""
echo "Note: Devices must advertise via mDNS/Bonjour to be discovered."
echo "If you have devices but they weren't found, they may:"
echo "  - Not support mDNS"
echo "  - Be on a different network/VLAN"
echo "  - Have mDNS disabled in their config"
