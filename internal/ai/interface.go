package ai

import "context"

// Client defines the interface for communicating with the AI sidecar
type Client interface {
	// Chat sends a chat message to the AI
	Chat(ctx context.Context, req ChatRequest) (ChatResponse, error)

	// Analyze requests metric analysis from the AI
	Analyze(ctx context.Context, req AnalyzeRequest) (AnalyzeResponse, error)

	// Close shuts down the AI client
	Close() error
}

// ChatRequest is a chat message sent to the AI
type ChatRequest struct {
	Message string                 `json:"message"`
	Context map[string]interface{} `json:"context,omitempty"`
}

// ChatResponse is the AI's response to a chat message
type ChatResponse struct {
	Response string `json:"response"`
}

// AnalyzeRequest requests analysis of metrics or incidents
type AnalyzeRequest struct {
	Type    string                 `json:"type"` // "metrics", "incident"
	Data    map[string]interface{} `json:"data"`
	Context map[string]interface{} `json:"context,omitempty"`
}

// AnalyzeResponse is the AI's analysis
type AnalyzeResponse struct {
	Analysis string                 `json:"analysis"`
	Insights []string               `json:"insights"`
	Actions  []string               `json:"actions,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}
