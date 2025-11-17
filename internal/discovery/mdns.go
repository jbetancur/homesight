package discovery

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/grandcat/zeroconf"
)

// MQTTBroker represents a discovered MQTT broker
type MQTTBroker struct {
	Host     string
	Port     int
	Name     string
	Protocol string // tcp or ssl
}

// LANDevice represents a discovered LAN device
type LANDevice struct {
	Host         string
	Port         int
	Name         string
	Manufacturer string
	Model        string
	Type         string // "shelly", "tasmota", "esphome", "matter"
}

// DiscoverMQTTBrokers finds MQTT brokers on the local network via mDNS/Zeroconf
func DiscoverMQTTBrokers(timeout time.Duration) ([]MQTTBroker, error) {
	resolver, err := zeroconf.NewResolver(nil)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize resolver: %w", err)
	}

	entries := make(chan *zeroconf.ServiceEntry)
	brokers := []MQTTBroker{}
	done := make(chan bool)

	go func() {
		defer func() { done <- true }()
		for entry := range entries {
			if len(entry.AddrIPv4) > 0 {
				broker := MQTTBroker{
					Host:     entry.AddrIPv4[0].String(),
					Port:     entry.Port,
					Name:     entry.Instance,
					Protocol: "tcp",
				}
				brokers = append(brokers, broker)
				log.Printf("Discovered MQTT broker: %s at %s:%d", broker.Name, broker.Host, broker.Port)
			}
		}
	}()

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Look for MQTT services (_mqtt._tcp)
	err = resolver.Browse(ctx, "_mqtt._tcp", "local.", entries)

	<-ctx.Done()
	<-done

	return brokers, err
}

// DiscoverMatterDevices finds Matter devices on the local network
func DiscoverMatterDevices(timeout time.Duration) ([]LANDevice, error) {
	return discoverService(timeout, "_matter._tcp", "matter")
}

// DiscoverShellyDevices finds Shelly devices on the local network
func DiscoverShellyDevices(timeout time.Duration) ([]LANDevice, error) {
	return discoverService(timeout, "_http._tcp", "shelly")
}

// DiscoverTasmotaDevices finds Tasmota devices on the local network
func DiscoverTasmotaDevices(timeout time.Duration) ([]LANDevice, error) {
	return discoverService(timeout, "_http._tcp", "tasmota")
}

// DiscoverESPHomeDevices finds ESPHome devices on the local network
func DiscoverESPHomeDevices(timeout time.Duration) ([]LANDevice, error) {
	return discoverService(timeout, "_esphomelib._tcp", "esphome")
}

// DiscoverZWaveJSDevices finds Z-Wave JS gateways on the local network
func DiscoverZWaveJSDevices(timeout time.Duration) ([]LANDevice, error) {
	return discoverService(timeout, "_z-wave-js._tcp", "zwave")
}

// DiscoverAllmDNSServices finds ALL mDNS services on the network (generic discovery)
func DiscoverAllmDNSServices(timeout time.Duration) ([]LANDevice, error) {
	devices := []LANDevice{}
	seen := make(map[string]bool) // Deduplicate by host:port

	// Smart home monitoring service types (removed entertainment/voice assistants)
	serviceTypes := []string{
		"_hap._tcp",            // HomeKit devices (sensors, switches)
		"_home-assistant._tcp", // Home Assistant
		"_matter._tcp",         // Matter devices
		"_http._tcp",           // HTTP-enabled devices (Shelly, Tasmota)
		"_https._tcp",          // HTTPS-enabled devices
		"_esphomelib._tcp",     // ESPHome devices
		"_z-wave-js._tcp",      // Z-Wave gateways
	}

	// Discover each service type sequentially to avoid channel conflicts
	// Use shorter timeout per service type
	perServiceTimeout := timeout / time.Duration(len(serviceTypes))
	if perServiceTimeout < 1*time.Second {
		perServiceTimeout = 1 * time.Second
	}

	for _, serviceType := range serviceTypes {
		resolver, err := zeroconf.NewResolver(nil)
		if err != nil {
			log.Printf("Failed to create resolver for %s: %v", serviceType, err)
			continue
		}

		entries := make(chan *zeroconf.ServiceEntry)
		ctx, cancel := context.WithTimeout(context.Background(), perServiceTimeout)

		go func() {
			for entry := range entries {
				if entry == nil || len(entry.AddrIPv4) == 0 {
					continue
				}

				key := fmt.Sprintf("%s:%d", entry.AddrIPv4[0].String(), entry.Port)
				if seen[key] {
					continue
				}
				seen[key] = true

				// Determine device type from service name
				deviceType := "unknown"
				serviceName := entry.Service

				if containsShelly(entry) {
					deviceType = "shelly"
				} else if containsTasmota(entry) {
					deviceType = "tasmota"
				} else if serviceName == "_esphomelib._tcp" {
					deviceType = "esphome"
				} else if serviceName == "_matter._tcp" {
					deviceType = "matter"
				} else if serviceName == "_z-wave-js._tcp" {
					deviceType = "zwave"
				} else if serviceName == "_mqtt._tcp" {
					cancel()
					return // Skip MQTT brokers (handled separately)
				} else {
					deviceType = serviceName // Use service name as type
				}

				device := LANDevice{
					Host:         entry.AddrIPv4[0].String(),
					Port:         entry.Port,
					Name:         entry.Instance,
					Type:         deviceType,
					Model:        extractModel(entry),
					Manufacturer: entry.Domain,
				}
				devices = append(devices, device)
				log.Printf("Discovered mDNS service: %s (%s) at %s:%d", device.Name, deviceType, device.Host, device.Port)
			}
		}()

		resolver.Browse(ctx, serviceType, "local.", entries)
		<-ctx.Done()
		cancel()
	}

	return devices, nil
}

// DiscoverAllLANDevices finds all supported LAN devices// DiscoverAllLANDevices finds all supported LAN devices
func DiscoverAllLANDevices(timeout time.Duration) ([]LANDevice, error) {
	var allDevices []LANDevice

	// Discover Matter devices
	matter, _ := DiscoverMatterDevices(timeout)
	allDevices = append(allDevices, matter...)

	// Discover Shelly devices
	shelly, _ := DiscoverShellyDevices(timeout)
	allDevices = append(allDevices, shelly...)

	// Discover Tasmota devices
	tasmota, _ := DiscoverTasmotaDevices(timeout)
	allDevices = append(allDevices, tasmota...)

	// Discover ESPHome devices
	esphome, _ := DiscoverESPHomeDevices(timeout)
	allDevices = append(allDevices, esphome...)

	// Discover Z-Wave JS gateways
	zwave, _ := DiscoverZWaveJSDevices(timeout)
	allDevices = append(allDevices, zwave...)

	return allDevices, nil
}

// discoverService is a helper function for mDNS service discovery
func discoverService(timeout time.Duration, service, deviceType string) ([]LANDevice, error) {
	resolver, err := zeroconf.NewResolver(nil)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize resolver: %w", err)
	}

	entries := make(chan *zeroconf.ServiceEntry)
	devices := []LANDevice{}
	done := make(chan bool)

	go func() {
		defer func() { done <- true }()
		for entry := range entries {
			// Filter based on device type
			if deviceType == "shelly" && !containsShelly(entry) {
				continue
			}
			if deviceType == "tasmota" && !containsTasmota(entry) {
				continue
			}

			if len(entry.AddrIPv4) > 0 {
				device := LANDevice{
					Host:  entry.AddrIPv4[0].String(),
					Port:  entry.Port,
					Name:  entry.Instance,
					Type:  deviceType,
					Model: extractModel(entry),
				}
				devices = append(devices, device)
				log.Printf("Discovered %s device: %s at %s:%d", deviceType, device.Name, device.Host, device.Port)
			}
		}
	}()

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	err = resolver.Browse(ctx, service, "local.", entries)

	<-ctx.Done()
	<-done

	return devices, err
}

// containsShelly checks if entry is a Shelly device
func containsShelly(entry *zeroconf.ServiceEntry) bool {
	// Check hostname or TXT records for "shelly"
	for _, txt := range entry.Text {
		if len(txt) > 6 && txt[:6] == "shelly" {
			return true
		}
	}
	return len(entry.Instance) > 6 && entry.Instance[:6] == "shelly"
}

// containsTasmota checks if entry is a Tasmota device
func containsTasmota(entry *zeroconf.ServiceEntry) bool {
	// Check TXT records for Tasmota identifiers
	for _, txt := range entry.Text {
		if len(txt) > 7 && txt[:7] == "tasmota" {
			return true
		}
	}
	return false
}

// extractModel extracts model information from TXT records
func extractModel(entry *zeroconf.ServiceEntry) string {
	for _, txt := range entry.Text {
		if len(txt) > 6 && txt[:6] == "model=" {
			return txt[6:]
		}
	}
	return ""
}

// BrokerURL returns the connection URL for the broker
func (b *MQTTBroker) BrokerURL() string {
	return fmt.Sprintf("%s://%s:%d", b.Protocol, b.Host, b.Port)
}
