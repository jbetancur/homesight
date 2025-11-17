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

	// Create the device using Upsert
	if err := s.deviceRepo.Upsert(r.Context(), &device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(device)
}
