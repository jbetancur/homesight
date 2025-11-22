package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// HTTPClient implements Client using HTTP to communicate with Python AI sidecar
type HTTPClient struct {
	baseURL string
	client  *http.Client
}

// NewHTTPClient creates a new HTTP-based AI client
func NewHTTPClient(baseURL string) *HTTPClient {
	return &HTTPClient{
		baseURL: baseURL,
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

// Chat sends a chat message to the AI
func (c *HTTPClient) Chat(ctx context.Context, req ChatRequest) (ChatResponse, error) {
	url := fmt.Sprintf("%s/chat", c.baseURL)

	body, err := json.Marshal(req)
	if err != nil {
		return ChatResponse{}, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return ChatResponse{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		return ChatResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return ChatResponse{}, fmt.Errorf("AI service returned status %d: %s", resp.StatusCode, string(body))
	}

	var chatResp ChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return ChatResponse{}, err
	}

	return chatResp, nil
}

// Analyze requests metric analysis from the AI
func (c *HTTPClient) Analyze(ctx context.Context, req AnalyzeRequest) (AnalyzeResponse, error) {
	url := fmt.Sprintf("%s/analyze", c.baseURL)

	body, err := json.Marshal(req)
	if err != nil {
		return AnalyzeResponse{}, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return AnalyzeResponse{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		return AnalyzeResponse{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return AnalyzeResponse{}, fmt.Errorf("AI service returned status %d: %s", resp.StatusCode, string(body))
	}

	var analyzeResp AnalyzeResponse
	if err := json.NewDecoder(resp.Body).Decode(&analyzeResp); err != nil {
		return AnalyzeResponse{}, err
	}

	return analyzeResp, nil
}

// Close shuts down the AI client
func (c *HTTPClient) Close() error {
	return nil
}

// GetBaseURL returns the base URL of the AI service
func (c *HTTPClient) GetBaseURL() string {
	return c.baseURL
}
