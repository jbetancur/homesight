package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
)

// HSIL proxy handlers - forward requests to ai-sidecar HSIL endpoints

// getHSILBaseURL returns the HSIL base URL from environment or default
func getHSILBaseURL() string {
	aiServiceURL := os.Getenv("AI_SERVICE_URL")
	if aiServiceURL == "" {
		aiServiceURL = "http://ai-sidecar:8001" // Docker network default
	}
	return aiServiceURL + "/hsil"
}

// hsilProcessEvent forwards sensor events to HSIL
func (s *Server) hsilProcessEvent(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/events")
}

// hsilChat forwards chat requests to HSIL
func (s *Server) hsilChat(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/chat")
}

// hsilFeedback forwards user feedback to HSIL
func (s *Server) hsilFeedback(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/feedback")
}

// hsilGetState gets enriched home state from HSIL
func (s *Server) hsilGetState(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/state")
}

// hsilGetStats gets HSIL learning statistics
func (s *Server) hsilGetStats(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/stats")
}

// hsilGetPreferences gets learned user preferences
func (s *Server) hsilGetPreferences(w http.ResponseWriter, r *http.Request) {
	s.proxyToHSIL(w, r, "/preferences")
}

// proxyToHSIL is a generic proxy helper for HSIL endpoints
func (s *Server) proxyToHSIL(w http.ResponseWriter, r *http.Request, path string) {
	// Build target URL
	targetURL := getHSILBaseURL() + path

	// Read request body
	var body []byte
	var err error
	if r.Body != nil {
		body, err = io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, fmt.Sprintf("Failed to read request body: %v", err), http.StatusBadRequest)
			return
		}
		defer r.Body.Close()
	}

	// Create proxy request
	var proxyReq *http.Request
	if len(body) > 0 {
		proxyReq, err = http.NewRequest(r.Method, targetURL, bytes.NewBuffer(body))
	} else {
		proxyReq, err = http.NewRequest(r.Method, targetURL, nil)
	}

	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to create proxy request: %v", err), http.StatusInternalServerError)
		return
	}

	// Copy headers
	proxyReq.Header.Set("Content-Type", "application/json")
	for k, v := range r.Header {
		if k == "Content-Length" {
			continue
		}
		proxyReq.Header[k] = v
	}

	// Execute request
	client := &http.Client{}
	resp, err := client.Do(proxyReq)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to contact HSIL service: %v", err), http.StatusServiceUnavailable)
		return
	}
	defer resp.Body.Close()

	// Read response
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to read HSIL response: %v", err), http.StatusInternalServerError)
		return
	}

	// Copy response headers
	for k, v := range resp.Header {
		w.Header()[k] = v
	}

	// Set status code
	w.WriteHeader(resp.StatusCode)

	// Write response body
	w.Write(respBody)
}

// ForwardEventToHSIL is a helper to send events to HSIL from other parts of the code
// Use this in your MQTT consumer or event handlers
func (s *Server) ForwardEventToHSIL(deviceID, sensorID, eventType string, value interface{}, location, deviceType string) error {
	payload := map[string]interface{}{
		"device_id":   deviceID,
		"sensor_id":   sensorID,
		"event_type":  eventType,
		"value":       value,
		"location":    location,
		"device_type": deviceType,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	resp, err := http.Post(getHSILBaseURL()+"/events", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to forward to HSIL: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HSIL returned non-OK status: %d", resp.StatusCode)
	}

	return nil
}
