package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/homesight/homesight/internal/ai"
	"github.com/homesight/homesight/internal/db"
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

	// Notify AI sidecar about the new device for document discovery
	// This triggers automatic ingestion of device documentation (manuals, forums, etc.)
	go s.notifyAIDeviceCreated(device)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(device)
}

// notifyAIDeviceCreated sends device creation event to AI sidecar for document discovery
func (s *Server) notifyAIDeviceCreated(device model.Device) {
	// Extract manufacturer and model from metadata
	manufacturer := device.Metadata["manufacturer"]
	model := device.Metadata["model"]

	// Build event payload for AI sidecar
	eventPayload := map[string]interface{}{
		"type": "device.created",
		"data": map[string]interface{}{
			"id":           device.ID,
			"name":         device.Name,
			"manufacturer": manufacturer,
			"model":        model,
			"type":         device.Type,
		},
	}

	// Send event to AI sidecar asynchronously
	reqBody, err := json.Marshal(eventPayload)
	if err != nil {
		return
	}

	// POST to AI sidecar with timeout
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(
		"http://localhost:8001/events/device",
		"application/json",
		bytes.NewBuffer(reqBody),
	)
	if err != nil {
		return
	}
	defer resp.Body.Close()
}

// handleReingestDeviceDocs re-triggers document discovery for an existing device
func (s *Server) handleReingestDeviceDocs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract device ID from URL
	deviceID := r.PathValue("id")
	if deviceID == "" {
		http.Error(w, "Device ID required", http.StatusBadRequest)
		return
	}

	// Get the device
	device, err := s.deviceRepo.Get(r.Context(), deviceID)
	if err != nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Set docs_status to "pending" immediately so UI updates
	device.DocsStatus = "pending"
	device.UpdatedAt = time.Now()
	if err := s.deviceRepo.Upsert(r.Context(), device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Emit device_updated event for real-time UI updates
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceUpdated, Data: device})
	}

	// Trigger document discovery asynchronously
	go s.notifyAIDeviceCreated(*device)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "queued",
		"message": "Document re-ingestion queued for device",
		"device":  device.ID,
	})
}

// handleUpdateDeviceDocsStatus updates device documentation ingestion status
// Called by AI sidecar when document discovery completes
func (s *Server) handleUpdateDeviceDocsStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract device ID from URL
	deviceID := r.PathValue("id")
	if deviceID == "" {
		http.Error(w, "Device ID required", http.StatusBadRequest)
		return
	}

	var updateReq struct {
		Status    string `json:"status"`    // success/partial/error
		Ingested  bool   `json:"ingested"`  // whether docs were successfully ingested
		IngestedAt *time.Time `json:"ingested_at"`
	}

	if err := json.NewDecoder(r.Body).Decode(&updateReq); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Get the device
	device, err := s.deviceRepo.Get(r.Context(), deviceID)
	if err != nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Update documentation status fields
	device.DocsStatus = updateReq.Status
	device.DocsIngested = updateReq.Ingested
	if updateReq.IngestedAt != nil {
		device.DocsIngestedAt = updateReq.IngestedAt
	} else if updateReq.Ingested {
		// If ingested but no timestamp provided, use current time
		now := time.Now()
		device.DocsIngestedAt = &now
	}
	device.UpdatedAt = time.Now()

	// Save updated device
	if err := s.deviceRepo.Upsert(r.Context(), device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Emit device_updated event for real-time UI updates
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceUpdated, Data: device})
	}

	// Auto-generate knowledge base articles if docs were successfully ingested
	if updateReq.Ingested && updateReq.Status == "success" {
		// Launch knowledge base generation in the background to avoid blocking
		go s.generateAndStoreKnowledgeBase(device)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "updated",
		"message": "Device documentation status updated",
		"device":  device.ID,
	})
}

// generateAndStoreKnowledgeBase generates knowledge base articles and stores them in the database
func (s *Server) generateAndStoreKnowledgeBase(device *model.Device) {
	// Build device info for AI queries
	deviceInfo := fmt.Sprintf("%s (%s) - %s device", device.Name, device.Type, device.Integration)
	if device.Metadata != nil {
		if mfg, ok := device.Metadata["manufacturer"]; ok {
			if model, ok := device.Metadata["model"]; ok {
				deviceInfo = fmt.Sprintf("%s - %s %s", device.Name, mfg, model)
			}
		}
	}

	// Create a timeout context for AI calls
	aiCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	// Generate articles concurrently from AI sidecar
	overviewChan := make(chan string, 1)
	troubleshootChan := make(chan string, 1)
	docChan := make(chan string, 1)

	// Overview
	go func() {
		overviewResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
			Message: fmt.Sprintf("Provide a comprehensive overview of the %s device. Include typical use cases, key features, and maintenance tips. Keep it concise.", deviceInfo),
		})
		if err == nil && overviewResp.Response != "" {
			overviewChan <- overviewResp.Response
		}
		close(overviewChan)
	}()

	// Troubleshooting
	go func() {
		troubleshootResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
			Message: fmt.Sprintf("Provide a troubleshooting guide for the %s device. List common issues and solutions. Keep it concise.", deviceInfo),
		})
		if err == nil && troubleshootResp.Response != "" {
			troubleshootChan <- troubleshootResp.Response
		}
		close(troubleshootChan)
	}()

	// Documentation
	go func() {
		if device.Metadata != nil && device.Metadata["manufacturer"] != "" {
			docResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
				Message: fmt.Sprintf("Summarize the official technical specifications and documentation for the %s. Include important settings, specifications, and compatibility information. Keep it concise.", deviceInfo),
			})
			if err == nil && docResp.Response != "" {
				docChan <- docResp.Response
			}
		}
		close(docChan)
	}()

	// Collect results with defaults
	overviewContent := "Comprehensive overview of " + device.Name + " including typical use cases, configuration, and maintenance"
	troubleshootContent := "Common issues and solutions for " + device.Name
	docContent := "Official manual and technical specifications"

	// Wait for results or timeout
	overviewContent = getValue(overviewChan, overviewContent)
	troubleshootContent = getValue(troubleshootChan, troubleshootContent)
	docContent = getValue(docChan, docContent)

	ctx := context.Background()

	// Delete existing articles for this device
	if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, device.ID); err != nil {
		fmt.Printf("Warning: failed to delete old KB articles for %s: %v\n", device.ID, err)
		return
	}

	now := time.Now()

	// Store Device Overview
	overviewArticle := &db.KnowledgeBaseArticle{
		ID:          fmt.Sprintf("%s-overview", device.ID),
		DeviceID:    device.ID,
		Title:       "Device Overview",
		Type:        "generated",
		Source:      "AI-Generated Knowledge Base",
		Description: overviewContent,
		Available:   true,
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	if err := s.knowledgeBaseRepo.Upsert(ctx, overviewArticle); err != nil {
		fmt.Printf("Warning: failed to store overview article for %s: %v\n", device.ID, err)
		return
	}

	// Store Troubleshooting Guide
	troubleshootArticle := &db.KnowledgeBaseArticle{
		ID:          fmt.Sprintf("%s-troubleshoot", device.ID),
		DeviceID:    device.ID,
		Title:       "Troubleshooting Guide",
		Type:        "generated",
		Source:      "AI-Generated Knowledge Base",
		Description: troubleshootContent,
		Available:   true,
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	if err := s.knowledgeBaseRepo.Upsert(ctx, troubleshootArticle); err != nil {
		fmt.Printf("Warning: failed to store troubleshoot article for %s: %v\n", device.ID, err)
		return
	}

	// Store Official Documentation if available
	if device.Metadata != nil && device.Metadata["manufacturer"] != "" {
		docArticle := &db.KnowledgeBaseArticle{
			ID:          fmt.Sprintf("%s-official-docs", device.ID),
			DeviceID:    device.ID,
			Title:       "Official Documentation",
			Type:        "manufacturer",
			Source:      "Official " + device.Metadata["manufacturer"] + " Documentation",
			Description: docContent,
			Available:   true,
			CreatedAt:   now,
			UpdatedAt:   now,
		}
		if err := s.knowledgeBaseRepo.Upsert(ctx, docArticle); err != nil {
			fmt.Printf("Warning: failed to store official docs article for %s: %v\n", device.ID, err)
			return
		}
	}
}
