package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/homesight/homesight/internal/discovery"
	"github.com/homesight/homesight/internal/model"
)

// DiscoveredDevice represents a device found on the network but not yet onboarded
type DiscoveredDevice struct {
	ID           string            `json:"id"`
	Name         string            `json:"name"`
	Type         string            `json:"type"`
	Integration  string            `json:"integration"`
	Host         string            `json:"host,omitempty"`
	Port         int               `json:"port,omitempty"`
	Manufacturer string            `json:"manufacturer,omitempty"`
	Model        string            `json:"model,omitempty"`
	Metadata     map[string]string `json:"metadata,omitempty"`
	DiscoveredAt time.Time         `json:"discovered_at"`
}

// DiscoveredBroker represents an MQTT broker found on the network
type DiscoveredBroker struct {
	Name         string    `json:"name"`
	Host         string    `json:"host"`
	Port         int       `json:"port"`
	URL          string    `json:"url"`
	DiscoveredAt time.Time `json:"discovered_at"`
}

// handleDiscovery runs network discovery and returns found devices/brokers
func (s *Server) handleDiscovery(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Check if test mode is enabled
	if r.URL.Query().Get("test") == "true" {
		s.handleTestDiscovery(w, r)
		return
	}

	// Run broker and device discovery in parallel
	type discoveryResult struct {
		brokers []DiscoveredBroker
		devices []DiscoveredDevice
	}

	resultChan := make(chan discoveryResult, 1)

	go func() {
		var wg sync.WaitGroup
		var brokersMu, devicesMu sync.Mutex

		result := discoveryResult{
			brokers: []DiscoveredBroker{},
			devices: []DiscoveredDevice{},
		}

		// Discover MQTT brokers in parallel
		wg.Add(1)
		go func() {
			defer wg.Done()
			brokers, err := discovery.DiscoverMQTTBrokers(3 * time.Second)
			if err == nil && len(brokers) > 0 {
				discoveredBrokers := make([]DiscoveredBroker, 0, len(brokers))
				for _, b := range brokers {
					discoveredBrokers = append(discoveredBrokers, DiscoveredBroker{
						Name:         b.Name,
						Host:         b.Host,
						Port:         b.Port,
						URL:          b.BrokerURL(),
						DiscoveredAt: time.Now(),
					})
				}
				brokersMu.Lock()
				result.brokers = discoveredBrokers
				brokersMu.Unlock()
			}
		}()

		// Discover LAN devices in parallel
		wg.Add(1)
		go func() {
			defer wg.Done()
			discoveredDevices := make([]DiscoveredDevice, 0)

			// Check if user wants generic mDNS discovery (all services)
			useGenericDiscovery := r.URL.Query().Get("generic") == "true"

			var lanDevices []discovery.LANDevice
			var err error

			if useGenericDiscovery {
				// Discover ALL mDNS services on the network
				lanDevices, err = discovery.DiscoverAllmDNSServices(3 * time.Second)
			} else {
				// Discover only known device types (default)
				lanDevices, err = discovery.DiscoverAllLANDevices(3 * time.Second)
			}

			if err == nil && len(lanDevices) > 0 {
				for _, ld := range lanDevices {
					// Generate ID from host:port
					deviceID := ld.Host
					if ld.Port > 0 {
						deviceID = ld.Host + ":" + strconv.Itoa(ld.Port)
					}

					discoveredDevices = append(discoveredDevices, DiscoveredDevice{
						ID:           deviceID,
						Name:         ld.Name,
						Type:         ld.Type,
						Integration:  ld.Type, // Use device type as integration
						Host:         ld.Host,
						Port:         ld.Port,
						Manufacturer: ld.Manufacturer,
						Model:        ld.Model,
						Metadata:     make(map[string]string),
						DiscoveredAt: time.Now(),
					})
				}
			}

			// Add MQTT-discovered devices (from any connected broker)
			s.discoveryMutex.RLock()
			if s.discoveryListener != nil {
				mqttDevices := s.discoveryListener.GetDevices()
				if len(mqttDevices) > 0 {
					for _, md := range mqttDevices {
						discoveredDevices = append(discoveredDevices, DiscoveredDevice{
							ID:           md.ID,
							Name:         md.Name,
							Type:         md.Type,
							Integration:  md.Integration,
							Manufacturer: md.Manufacturer,
							Model:        md.Model,
							Metadata:     md.Metadata,
							DiscoveredAt: md.DiscoveredAt,
						})
					}
				}
			}
			s.discoveryMutex.RUnlock()

			devicesMu.Lock()
			result.devices = discoveredDevices
			devicesMu.Unlock()
		}()

		wg.Wait()
		resultChan <- result
	}()

	// Wait for parallel discovery to complete
	result := <-resultChan

	response := map[string]interface{}{
		"brokers": result.brokers,
		"devices": result.devices,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// handleTestDiscovery returns simulated devices for testing/demo
// This simulates discovery of various power/water/HVAC devices
func (s *Server) handleTestDiscovery(w http.ResponseWriter, r *http.Request) {
	now := time.Now()

	// Simulate a wide range of power/water/HVAC devices for POC
	devices := []DiscoveredDevice{
		// Water safety & management devices
		{
			ID:           "water-heater-001",
			Name:         "AO Smith Water Heater",
			Type:         "water_heater",
			Integration:  "mqtt",
			Manufacturer: "AO Smith",
			Model:        "EG12-50R-055D",
			Metadata: map[string]string{
				"capacity":     "50 gallons",
				"power":        "4500W",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "sump-pump-basement",
			Name:         "Zoeller Sump Pump",
			Type:         "sump_pump",
			Integration:  "mqtt",
			Manufacturer: "Zoeller",
			Model:        "M53",
			Metadata: map[string]string{
				"hp":           "1/3",
				"flow_rate":    "43 GPM",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "kitchen-leak-sensor",
			Name:         "Kitchen Sink Leak Detector",
			Type:         "water_leak",
			Integration:  "zigbee2mqtt",
			Manufacturer: "Aqara",
			Model:        "SJCGQ11LM",
			DiscoveredAt: now,
		},
		{
			ID:           "water-shutoff-main",
			Name:         "Main Water Shutoff Valve",
			Type:         "water_valve",
			Integration:  "zwave",
			Manufacturer: "Dome",
			Model:        "DMWV1",
			DiscoveredAt: now,
		},
		{
			ID:           "bathroom-leak-sensor",
			Name:         "Bathroom Leak Detector",
			Type:         "water_leak",
			Integration:  "zigbee2mqtt",
			Manufacturer: "Aqara",
			Model:        "SJCGQ11LM",
			DiscoveredAt: now,
		},

		// HVAC devices
		{
			ID:           "thermostat-main-floor",
			Name:         "Ecobee SmartThermostat",
			Type:         "thermostat",
			Integration:  "mqtt",
			Manufacturer: "Ecobee",
			Model:        "EB-STATE5-01",
			Metadata: map[string]string{
				"stages_heat":  "2",
				"stages_cool":  "2",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "furnace-monitor",
			Name:         "Trane Furnace Monitor",
			Type:         "furnace",
			Integration:  "esphome",
			Manufacturer: "Trane",
			Model:        "S9V2-VS100",
			Metadata: map[string]string{
				"btu":          "100000",
				"efficiency":   "96% AFUE",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "hvac-temp-sensor-bedroom",
			Name:         "Bedroom Temperature Sensor",
			Type:         "temperature",
			Integration:  "zigbee2mqtt",
			Manufacturer: "Aqara",
			Model:        "WSDCGQ11LM",
			DiscoveredAt: now,
		},

		// Power monitoring devices
		{
			ID:           "circuit-monitor-main",
			Name:         "Emporia Vue Energy Monitor",
			Type:         "energy_monitor",
			Integration:  "esphome",
			Manufacturer: "Emporia",
			Model:        "Vue-002",
			Metadata: map[string]string{
				"circuits":     "16",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "smart-plug-hvac",
			Name:         "HVAC Equipment Smart Plug",
			Type:         "smart_plug",
			Integration:  "shelly",
			Manufacturer: "Shelly",
			Model:        "Plug S",
			Metadata: map[string]string{
				"max_load":     "2500W",
			},
			DiscoveredAt: now,
		},
		{
			ID:           "backup-battery-sump",
			Name:         "Sump Pump Battery Backup",
			Type:         "battery_backup",
			Integration:  "mqtt",
			Manufacturer: "Wayne",
			Model:        "ESP25",
			DiscoveredAt: now,
		},
	}

	// Simulate MQTT broker discovery
	brokers := []DiscoveredBroker{
		{
			Name:         "Home Assistant",
			Host:         "homeassistant.local",
			Port:         1883,
			URL:          "tcp://homeassistant.local:1883",
			DiscoveredAt: now,
		},
	}

	response := map[string]interface{}{
		"brokers":   brokers,
		"devices":   devices,
		"test_mode": true,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// handleOnboardBroker onboards a discovered MQTT broker
func (s *Server) handleOnboardBroker(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		BrokerURL string `json:"broker_url"`
		Username  string `json:"username,omitempty"`
		Password  string `json:"password,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Note: Dynamic broker onboarding would require hot-reloading integrations
	// For MVP, user must add broker to config.yaml and restart
	// Future: Implement integration manager with Add/Remove methods

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "pending",
		"message": "Add this broker to config.yaml and restart",
		"broker":  req.BrokerURL,
	})
}

// handleOnboardDevice onboards a discovered device
func (s *Server) handleOnboardDevice(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var device model.Device
	if err := json.NewDecoder(r.Body).Decode(&device); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Set last_seen to now when onboarding
	device.LastSeen = time.Now()
	device.Enabled = true

	// Create the device using Upsert
	if err := s.deviceRepo.Upsert(r.Context(), &device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(device)
}
