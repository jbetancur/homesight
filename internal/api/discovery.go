package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
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

// DiscoveredReceiver represents a Z-Wave USB receiver found on the system
type DiscoveredReceiver struct {
	Name         string `json:"name"`
	DevicePath   string `json:"device_path"`
	Type         string `json:"type"`
	Online       bool   `json:"online"`
	SerialNumber string `json:"serial_number,omitempty"`
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

	// Run broker, device, and receiver discovery in parallel
	type discoveryResult struct {
		brokers   []DiscoveredBroker
		devices   []DiscoveredDevice
		receivers []DiscoveredReceiver
	}

	resultChan := make(chan discoveryResult, 1)

	go func() {
		var wg sync.WaitGroup
		var brokersMu, devicesMu, receiversMu sync.Mutex

		result := discoveryResult{
			brokers:   []DiscoveredBroker{},
			devices:   []DiscoveredDevice{},
			receivers: []DiscoveredReceiver{},
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

		// Discover Z-Wave USB receivers in parallel
		wg.Add(1)
		go func() {
			defer wg.Done()
			receivers, err := discovery.DiscoverZWaveUSBReceivers()
			if err == nil && len(receivers) > 0 {
				discoveredReceivers := make([]DiscoveredReceiver, 0, len(receivers))
				for _, r := range receivers {
					discoveredReceivers = append(discoveredReceivers, DiscoveredReceiver{
						Name:         r.Name,
						DevicePath:   r.DevicePath,
						Type:         "zwave_usb",
						Online:       r.Online,
						SerialNumber: r.SerialNumber,
					})
				}
				receiversMu.Lock()
				result.receivers = discoveredReceivers
				receiversMu.Unlock()
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
		"brokers":   result.brokers,
		"devices":   result.devices,
		"receivers": result.receivers,
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
				"capacity": "50 gallons",
				"power":    "4500W",
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
				"hp":        "1/3",
				"flow_rate": "43 GPM",
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
				"stages_heat": "2",
				"stages_cool": "2",
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
				"btu":        "100000",
				"efficiency": "96% AFUE",
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
				"circuits": "16",
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
				"max_load": "2500W",
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

	// Simulate Z-Wave USB receiver
	receivers := []DiscoveredReceiver{
		{
			Name:         "Zooz 800 Z-Wave Stick",
			DevicePath:   "/dev/ttyACM0",
			Type:         "zwave_usb",
			Online:       true,
			SerialNumber: "533D004242",
		},
	}

	response := map[string]interface{}{
		"brokers":   brokers,
		"devices":   devices,
		"receivers": receivers,
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
// force=true will clear caches and re-ingest everything (used for re-ingestion)
func (s *Server) notifyAIDeviceCreated(device model.Device, force ...bool) {
	// Extract manufacturer and model from metadata
	manufacturer := device.Metadata["manufacturer"]
	model := device.Metadata["model"]

	// Default force to false, but can be overridden by caller
	forceRefresh := false
	if len(force) > 0 {
		forceRefresh = force[0]
	}

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

	// Add force flag if re-ingesting
	if forceRefresh {
		eventPayload["force"] = true
	}

	// Send event to AI sidecar asynchronously
	reqBody, err := json.Marshal(eventPayload)
	if err != nil {
		log.Printf("[AI] Failed to marshal device event: %v", err)
		return
	}

	// POST to AI sidecar with timeout
	// Use the configured AI service URL (from environment, defaults to Docker network address)
	aiURL := "http://ai-sidecar:8001/events/device" // Default to Docker network
	if httpClient, ok := s.aiClient.(*ai.HTTPClient); ok {
		aiURL = httpClient.GetBaseURL() + "/events/device"
	}
	log.Printf("[AI] Sending device event to: %s", aiURL)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(
		aiURL,
		"application/json",
		bytes.NewBuffer(reqBody),
	)
	if err != nil {
		log.Printf("[AI] Failed to send device event: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		log.Printf("[AI] Device event returned status %d: %s", resp.StatusCode, string(body))
	} else {
		log.Printf("[AI] Device event sent successfully for %s", device.ID)
	}
}

// handleReingestDeviceDocs re-triggers document discovery for an existing device
// Query params:
//   - force=true: Also delete KB entries for other devices with same manufacturer/model
func (s *Server) handleReingestDeviceDocs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract device ID from URL (chi router)
	deviceID := chi.URLParam(r, "id")
	if deviceID == "" {
		http.Error(w, "Device ID required", http.StatusBadRequest)
		return
	}

	// Check for force param - if true, also clear KB for same manufacturer/model
	forceRegen := r.URL.Query().Get("force") == "true"

	// Get the device
	device, err := s.deviceRepo.Get(r.Context(), deviceID)
	if err != nil || device == nil {
		http.Error(w, "Device not found", http.StatusNotFound)
		return
	}

	// Delete old KB so it gets regenerated fresh
	if err := s.knowledgeBaseRepo.DeleteByDevice(r.Context(), device.ID); err != nil {
		log.Printf("Warning: failed to delete old KB for %s: %v", device.ID, err)
	}

	// If force=true, also delete KB for other devices with same manufacturer/model
	// This prevents deduplication from copying old KB content
	if forceRegen && device.Metadata != nil {
		manufacturer := device.Metadata["manufacturer"]
		model := device.Metadata["model"]
		if manufacturer != "" && model != "" {
			if err := s.knowledgeBaseRepo.DeleteByManufacturerModel(r.Context(), manufacturer, model); err != nil {
				log.Printf("Warning: failed to delete KB for %s %s: %v", manufacturer, model, err)
			} else {
				log.Printf("Force regen: deleted all KB entries for %s %s", manufacturer, model)
			}
		}
	}

	// Set docs_status to "pending" immediately so UI updates
	device.DocsStatus = "pending"
	device.DocsIngested = false // Reset ingestion flag to force re-processing
	device.UpdatedAt = time.Now()
	if err := s.deviceRepo.Upsert(r.Context(), device); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Emit device_updated event for real-time UI updates
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceUpdated, Data: device})
	}

	// Trigger document discovery asynchronously (force=true for re-ingestion)
	go s.notifyAIDeviceCreated(*device, true)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "queued",
		"message": "Document re-ingestion queued for device",
		"device":  device.ID,
		"force":   forceRegen,
	})
}

// handleUpdateDeviceDocsStatus updates device documentation ingestion status
// Called by AI sidecar when document discovery completes
func (s *Server) handleUpdateDeviceDocsStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract device ID from URL (chi router)
	deviceID := chi.URLParam(r, "id")
	if deviceID == "" {
		http.Error(w, "Device ID required", http.StatusBadRequest)
		return
	}

	var updateReq struct {
		Status     string     `json:"status"`      // success/partial/error
		Ingested   bool       `json:"ingested"`    // whether docs were successfully ingested
		IngestedAt *time.Time `json:"ingested_at"` // optional timestamp
		KBContent  string     `json:"kb_content"`  // generated KB content from AI sidecar
		SourceURLs []string   `json:"source_urls"` // documentation source URLs
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

	// Emit device_updated event for real-time UI updates with the final status
	if s.eventBus != nil {
		s.eventBus.Publish(Event{Type: DeviceUpdated, Data: device})
	}

	// Store KB content if provided by AI sidecar (no need to regenerate)
	fmt.Printf("Docs status update for %s: ingested=%v, status=%q, kb_content_len=%d\n", device.ID, updateReq.Ingested, updateReq.Status, len(updateReq.KBContent))
	if updateReq.Ingested && updateReq.Status == "success" {
		if updateReq.KBContent != "" {
			// AI sidecar provided KB content - store directly
			fmt.Printf("Storing KB content from AI sidecar for %s\n", device.ID)
			go s.storeKnowledgeBase(device, updateReq.KBContent, updateReq.SourceURLs)
		} else {
			// Fallback: generate KB if content not provided (backward compatibility)
			fmt.Printf("No KB content from AI sidecar, generating for %s\n", device.ID)
			go s.generateAndStoreKnowledgeBase(device)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "updated",
		"message": "Device documentation status updated",
		"device":  device.ID,
	})
}

// storeKnowledgeBase stores KB content provided by the AI sidecar directly
// No regeneration needed - content is already generated by AI sidecar with better context
func (s *Server) storeKnowledgeBase(device *model.Device, content string, sourceURLs []string) {
	manufacturer := ""
	modelName := ""
	if device.Metadata != nil {
		if mfg, ok := device.Metadata["manufacturer"]; ok {
			manufacturer = mfg
		}
		if m, ok := device.Metadata["model"]; ok {
			modelName = m
		}
	}

	ctx := context.Background()

	// Delete existing KB for this device
	if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, device.ID); err != nil {
		fmt.Printf("Warning: failed to delete old KB for %s: %v\n", device.ID, err)
	}

	now := time.Now()
	source := "AI-Generated Knowledge Base"
	if manufacturer != "" {
		source = fmt.Sprintf("AI-Generated from %s Documentation", manufacturer)
	}

	kb := &db.KnowledgeBase{
		ID:           fmt.Sprintf("%s-kb", device.ID),
		DeviceID:     device.ID,
		Manufacturer: manufacturer,
		Model:        modelName,
		Content:      content,
		Source:       source,
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	if err := s.knowledgeBaseRepo.Upsert(ctx, kb); err != nil {
		fmt.Printf("Warning: failed to store KB for %s: %v\n", device.ID, err)
		return
	}

	fmt.Printf("KB stored for %s: %d chars from AI sidecar\n", device.ID, len(content))
}

// generateAndStoreKnowledgeBase generates a single knowledge base document and stores it in the database
// Uses model-level deduplication: if KB already exists for this (manufacturer, model), copy it instead of regenerating
// NOTE: This is a fallback method - prefer storeKnowledgeBase when AI sidecar provides content
func (s *Server) generateAndStoreKnowledgeBase(device *model.Device) {
	// Build device info for AI queries
	deviceInfo := fmt.Sprintf("%s (%s) - %s device", device.Name, device.Type, device.Integration)
	manufacturer := ""
	modelName := ""
	if device.Metadata != nil {
		if mfg, ok := device.Metadata["manufacturer"]; ok {
			manufacturer = mfg
			if m, ok := device.Metadata["model"]; ok {
				modelName = m
				deviceInfo = fmt.Sprintf("%s - %s %s", device.Name, mfg, m)
			}
		}
	}

	ctx := context.Background()

	// Model-level deduplication: check if KB already exists for this manufacturer/model
	// This avoids redundant OpenAI calls when multiple devices share the same model
	if manufacturer != "" && modelName != "" {
		existingKB, err := s.knowledgeBaseRepo.GetByManufacturerModel(ctx, manufacturer, modelName)
		if err == nil && existingKB != nil && existingKB.Content != "" {
			// Found existing KB for this model - copy to new device
			fmt.Printf("KB Dedup: Found existing KB for %s %s, copying to %s\n", manufacturer, modelName, device.ID)

			// Delete any existing KB for this device first
			if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, device.ID); err != nil {
				fmt.Printf("Warning: failed to delete old KB for %s: %v\n", device.ID, err)
			}

			now := time.Now()
			newKB := &db.KnowledgeBase{
				ID:           fmt.Sprintf("%s-kb", device.ID),
				DeviceID:     device.ID,
				Manufacturer: manufacturer,
				Model:        modelName,
				Content:      existingKB.Content,
				Source:       existingKB.Source,
				CreatedAt:    now,
				UpdatedAt:    now,
			}
			if err := s.knowledgeBaseRepo.Upsert(ctx, newKB); err != nil {
				fmt.Printf("Warning: failed to copy KB for %s: %v\n", device.ID, err)
			} else {
				fmt.Printf("KB Dedup: Copied KB to %s (saved OpenAI call)\n", device.ID)
			}
			return
		}
	}

	// No existing KB found - generate new KB via AI
	fmt.Printf("KB Generation for %s: manufacturer=%q, model=%q (no existing KB found, generating new)\n", device.ID, manufacturer, modelName)

	// Build context for RAG filtering
	deviceContext := map[string]interface{}{
		"device_name":  device.Name,
		"manufacturer": manufacturer,
		"model":        modelName,
		"device_type":  string(device.Type),
	}

	// Create a timeout context for AI call (45s to allow for OpenAI latency)
	aiCtx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()

	// Generate a comprehensive KB document in markdown with detailed sections
	kbPrompt := fmt.Sprintf(`Generate a comprehensive knowledge base document for the %s device based on the ingested documentation.

IMPORTANT: Extract and include ALL specific details from the documentation. Do not generalize or omit technical details.

Format as a single markdown document with these sections:

## Overview
- Device description and primary purpose
- Key features (list all from documentation)
- Typical use cases and placement recommendations

## Installation
- Step-by-step installation/setup instructions
- Battery installation (exact battery type, how to access battery compartment)
- Initial pairing/inclusion process
- LED indicator meanings during setup

## Configuration
- Z-Wave/Zigbee inclusion and exclusion procedures (exact button sequences)
- Factory reset procedure (exact steps)
- Wake-up intervals and how to adjust them
- Association groups (if applicable)
- Advanced parameters/settings with parameter numbers, values, and defaults

## Troubleshooting
- Device not pairing/responding
- False alerts or missed detections
- Connectivity issues
- Battery issues
- LED indicator troubleshooting
Include specific solutions from the documentation.

## Specifications
- Model number
- Power source (exact battery type)
- Operating temperature range
- Wireless range
- Dimensions and weight
- IP rating (if applicable)
- Supported command classes
- Compatibility information

Extract ALL specific values, procedures, and technical details from the ingested documentation. Be thorough and precise.`, deviceInfo)

	kbResp, err := s.aiClient.Chat(aiCtx, ai.ChatRequest{
		Message: kbPrompt,
		Context: deviceContext,
	})

	// Default content if API call fails
	content := fmt.Sprintf(`## Overview
%s device - documentation pending.

## Installation
Installation instructions not yet available.

## Configuration
Configuration details not yet available.

## Troubleshooting
Troubleshooting information not yet available.

## Specifications
Technical specifications not yet available.`, device.Name)

	if err == nil && kbResp.Response != "" {
		content = kbResp.Response
		fmt.Printf("KB Generation for %s: successfully generated content\n", device.ID)
	} else if err != nil {
		fmt.Printf("KB Generation for %s: API call failed: %v\n", device.ID, err)
	}

	// Delete existing KB for this device
	if err := s.knowledgeBaseRepo.DeleteByDevice(ctx, device.ID); err != nil {
		fmt.Printf("Warning: failed to delete old KB for %s: %v\n", device.ID, err)
	}

	now := time.Now()
	source := "AI-Generated Knowledge Base"
	if manufacturer != "" {
		source = fmt.Sprintf("AI-Generated from %s Documentation", manufacturer)
	}

	// Store single KB document
	kb := &db.KnowledgeBase{
		ID:           fmt.Sprintf("%s-kb", device.ID),
		DeviceID:     device.ID,
		Manufacturer: manufacturer,
		Model:        modelName,
		Content:      content,
		Source:       source,
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	if err := s.knowledgeBaseRepo.Upsert(ctx, kb); err != nil {
		fmt.Printf("Warning: failed to store KB for %s: %v\n", device.ID, err)
		return
	}
	fmt.Printf("KB Generation for %s: stored successfully\n", device.ID)
}
