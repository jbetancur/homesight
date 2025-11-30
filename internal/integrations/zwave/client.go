package zwave

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

// Client manages WebSocket connection to Z-Wave JS server
type Client struct {
	wsURL         string
	conn          *websocket.Conn
	messageID     atomic.Uint64
	pending       sync.Map // messageID -> response channel
	eventHandlers map[string]EventHandler
	connected     atomic.Bool
	mu            sync.RWMutex
	writeMu       sync.Mutex // Protects websocket writes

	// State cache (populated from events)
	stateMu    sync.RWMutex
	controller map[string]interface{}
	nodes      map[int]*ZWaveNode // nodeID -> node
	homeID     uint32

	// Callbacks
	onConnect    func()
	onDisconnect func()

	// Context for cancellation
	ctx    context.Context
	cancel context.CancelFunc
}

// EventHandler processes Z-Wave events
type EventHandler func(event Event)

// Request represents a Z-Wave JS API call
type Request struct {
	Type      string                 `json:"type"`
	Command   string                 `json:"command"`
	MessageID string                 `json:"messageId"`
	Args      map[string]interface{} `json:"args,omitempty"`
}

// Response represents a Z-Wave JS API response
type Response struct {
	Type      string      `json:"type"`
	MessageID string      `json:"messageId,omitempty"`
	Success   bool        `json:"success"`
	Result    interface{} `json:"result,omitempty"`
	Message   string      `json:"message,omitempty"`
	Error     string      `json:"error,omitempty"`
}

// Event represents a Z-Wave event (from Z-Wave JS Server)
type Event struct {
	Type  string                 `json:"type"`
	Data  map[string]interface{} `json:"data,omitempty"`
	Event map[string]interface{} `json:"event,omitempty"` // Nested event data for type="event"
}

// NewClient creates a new Z-Wave JS WebSocket client
func NewClient(wsURL string) *Client {
	ctx, cancel := context.WithCancel(context.Background())

	return &Client{
		wsURL:         wsURL,
		eventHandlers: make(map[string]EventHandler),
		nodes:         make(map[int]*ZWaveNode),
		controller:    make(map[string]interface{}),
		ctx:           ctx,
		cancel:        cancel,
	}
}

// Connect establishes WebSocket connection to Z-Wave JS
func (c *Client) Connect() error {
	for {
		select {
		case <-c.ctx.Done():
			return fmt.Errorf("client stopped")
		default:
		}

		conn, _, err := websocket.DefaultDialer.Dial(c.wsURL, nil)
		if err != nil {
			log.Printf("[ZWAVE] Failed to connect to Z-Wave JS, retrying in 5s: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		c.mu.Lock()
		c.conn = conn
		c.mu.Unlock()

		c.connected.Store(true)
		log.Printf("[ZWAVE] Connected to Z-Wave JS WebSocket at %s", c.wsURL)

		// Note: onConnect callback will be called AFTER start_listening completes
		// and the initial state is loaded (see handleMessage function)

		// Start health check
		go c.healthCheck()

		// Listen for messages
		go c.listen()

		// Send start_listening command to get initial state
		go func() {
			// Wait a bit for the listener to be ready
			time.Sleep(500 * time.Millisecond)
			if _, err := c.Call("start_listening", nil); err != nil {
				log.Printf("[ZWAVE] Failed to start listening: %v", err)
			} else {
				log.Printf("[ZWAVE] Started listening for events")
			}
		}()

		return nil
	}
}

// listen processes incoming WebSocket messages
func (c *Client) listen() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[ZWAVE] Panic in message listener: %v", r)
			c.handleDisconnect()
		}
	}()

	for {
		if !c.connected.Load() {
			return
		}

		c.mu.RLock()
		conn := c.conn
		c.mu.RUnlock()

		if conn == nil {
			return
		}

		_, message, err := conn.ReadMessage()
		if err != nil {
			log.Printf("[ZWAVE] WebSocket read error: %v", err)
			c.handleDisconnect()
			return
		}

		c.handleMessage(message)
	}
}

// handleMessage processes a WebSocket message
func (c *Client) handleMessage(message []byte) {
	// Try to parse as Response (RPC reply)
	var resp Response
	if err := json.Unmarshal(message, &resp); err == nil && resp.MessageID != "" {
		// This is an RPC response
		if !resp.Success {
			log.Printf("[ZWAVE] RPC response failed: messageId=%s success=%v error=%s message=%s raw=%s", resp.MessageID, resp.Success, resp.Error, resp.Message, string(message))
		}

		// If this is a start_listening response, extract state
		if resp.Success && resp.Result != nil {
			if resultMap, ok := resp.Result.(map[string]interface{}); ok {
				if state, ok := resultMap["state"].(map[string]interface{}); ok {
					c.handleInitialState(state)
					// Trigger onConnect callback after initial state is loaded
					if c.onConnect != nil {
						go c.onConnect()
					}
				}
			}
		}

		if ch, ok := c.pending.LoadAndDelete(resp.MessageID); ok {
			ch.(chan Response) <- resp
		}
		return
	}

	// Try to parse as Event
	var event Event
	if err := json.Unmarshal(message, &event); err == nil {
		// Log all raw events for debugging
		if event.Type == "event" {
			log.Printf("[ZWAVE] 📥 Raw event wrapper: %s", string(message))
		}
		c.handleEvent(event)
		return
	}

	log.Printf("[ZWAVE] ❌ Failed to parse message: %s", string(message))
}

// handleInitialState processes the initial state from start_listening response
func (c *Client) handleInitialState(state map[string]interface{}) {
	c.stateMu.Lock()
	defer c.stateMu.Unlock()

	// Debug: log all keys in state
	stateJSON, _ := json.Marshal(state)
	log.Printf("[ZWAVE] Received initial state from start_listening: %s", string(stateJSON))

	// Extract controller info
	if ctrl, ok := state["controller"].(map[string]interface{}); ok {
		c.controller = ctrl
		if homeIdFloat, ok := ctrl["homeId"].(float64); ok {
			c.homeID = uint32(homeIdFloat)
		}
		log.Printf("[ZWAVE] Controller initialized with homeId: 0x%08x", c.homeID)
	}

	// Extract nodes - can be either array or object
	if nodesArray, ok := state["nodes"].([]interface{}); ok {
		// Nodes as array
		log.Printf("[ZWAVE] Nodes array has %d items", len(nodesArray))
		for _, nodeData := range nodesArray {
			c.parseAndStoreNodeLocked(nodeData)
		}
		log.Printf("[ZWAVE] Loaded %d nodes from initial state (array format)", len(c.nodes))
	} else if nodesMap, ok := state["nodes"].(map[string]interface{}); ok {
		// Nodes as object/map keyed by node ID
		log.Printf("[ZWAVE] Nodes map has %d items", len(nodesMap))
		for _, nodeData := range nodesMap {
			c.parseAndStoreNodeLocked(nodeData)
		}
		log.Printf("[ZWAVE] Loaded %d nodes from initial state (map format)", len(c.nodes))
	} else {
		log.Printf("[ZWAVE] No nodes found in initial state (nodes field type: %T)", state["nodes"])
	}
}

// handleEvent dispatches events to registered handlers
func (c *Client) handleEvent(event Event) {
	// Z-Wave JS Server wraps events: { type: "event", event: { source, event, ... } }
	// Unwrap nested events
	if event.Type == "event" && event.Event != nil {
		// Extract the actual event type and data from the nested event
		if eventType, ok := event.Event["event"].(string); ok {
			// Create a new unwrapped event with the actual type
			unwrappedEvent := Event{
				Type: eventType,
				Data: event.Event,
			}
			// Log all events, with special attention to removal-related events
			if strings.Contains(eventType, "remov") || strings.Contains(eventType, "exclusion") {
				log.Printf("[ZWAVE] ⚠️ REMOVAL EVENT: %s (source: %v) - Data: %+v", eventType, event.Event["source"], event.Event)
			} else {
				log.Printf("[ZWAVE] Event received: %s (source: %v)", eventType, event.Event["source"])
			}
			c.updateStateFromEvent(unwrappedEvent)

			// Dispatch to handlers
			c.mu.RLock()
			handler, exists := c.eventHandlers[eventType]
			c.mu.RUnlock()
			if exists && handler != nil {
				go handler(unwrappedEvent)
			}
		} else {
			log.Printf("[ZWAVE] Event with missing event field: %+v", event.Event)
		}
		return
	}

	// Handle non-wrapped events (like "version")
	log.Printf("[ZWAVE] Event received: %s", event.Type)
	c.updateStateFromEvent(event)

	// Dispatch to external handlers
	c.mu.RLock()
	handler, exists := c.eventHandlers[event.Type]
	c.mu.RUnlock()

	if exists && handler != nil {
		go handler(event)
	}
}

// updateStateFromEvent updates the internal state cache from events
func (c *Client) updateStateFromEvent(event Event) {
	c.stateMu.Lock()
	defer c.stateMu.Unlock()

	switch event.Type {
	case "driver ready":
		// Extract controller info and homeId from event data
		if ctrl, ok := event.Data["controller"].(map[string]interface{}); ok {
			c.controller = ctrl
		}
		if homeIdFloat, ok := event.Data["homeId"].(float64); ok {
			c.homeID = uint32(homeIdFloat)
		}
		// Extract initial nodes if present
		if nodesMap, ok := event.Data["nodes"].(map[string]interface{}); ok {
			for _, nodeData := range nodesMap {
				c.parseAndStoreNodeLocked(nodeData)
			}
		}

	case "node added", "ready", "interview stage completed":
		// Parse and store node data from the "node" or "nodeState" field
		var nodeData interface{}
		var ok bool

		// Try "nodeState" first (used by "ready" event)
		if nodeData, ok = event.Data["nodeState"]; ok {
			c.parseAndStoreNodeLocked(nodeData)
		} else if nodeData, ok = event.Data["node"]; ok {
			// Fallback to "node" field
			c.parseAndStoreNodeLocked(nodeData)
		} else {
			log.Printf("[ZWAVE-CLIENT] Event %s missing 'node'/'nodeState' field, data keys: %v", event.Type, getMapKeys(event.Data))
		}

	case "node removed":
		// Remove node from cache
		// Try direct nodeId field first
		if nodeIDFloat, ok := event.Data["nodeId"].(float64); ok {
			nodeID := int(nodeIDFloat)
			log.Printf("[ZWAVE-CLIENT] ⚠️ REMOVING NODE %d from cache (had %d nodes)", nodeID, len(c.nodes))
			delete(c.nodes, nodeID)
			log.Printf("[ZWAVE-CLIENT] ✅ Node %d removed from cache (now have %d nodes)", nodeID, len(c.nodes))
		} else if nodeObj, ok := event.Data["node"].(map[string]interface{}); ok {
			// Node data is nested in "node" object
			if nodeIDFloat, ok := nodeObj["nodeId"].(float64); ok {
				nodeID := int(nodeIDFloat)
				log.Printf("[ZWAVE-CLIENT] ⚠️ REMOVING NODE %d from cache via nested 'node.nodeId' (had %d nodes)", nodeID, len(c.nodes))
				delete(c.nodes, nodeID)
				log.Printf("[ZWAVE-CLIENT] ✅ Node %d removed from cache (now have %d nodes)", nodeID, len(c.nodes))
			} else {
				log.Printf("[ZWAVE-CLIENT] ❌ Failed to extract nodeId from node object, keys: %v", getMapKeys(nodeObj))
			}
		} else {
			log.Printf("[ZWAVE-CLIENT] ❌ Failed to extract nodeId from node removed event, data keys: %v", getMapKeys(event.Data))
		}

	case "value updated", "value added":
		// Update node value in cache
		// Note: We're not currently tracking individual value updates in the cache
		// Values are stored as part of the node's initial state
		// TODO: Implement value tracking if needed
		_ = event // Suppress unused variable warning
	}
}

// parseAndStoreNodeLocked parses node data and stores it in the cache (caller must hold lock)
func (c *Client) parseAndStoreNodeLocked(nodeData interface{}) {
	data, err := json.Marshal(nodeData)
	if err != nil {
		log.Printf("[ZWAVE] Failed to marshal node data: %v", err)
		return
	}

	var node ZWaveNode
	if err := json.Unmarshal(data, &node); err != nil {
		log.Printf("[ZWAVE] Failed to unmarshal node data: %v, data=%s", err, string(data[:min(200, len(data))]))
		return
	}

	log.Printf("[ZWAVE-CLIENT] Storing node %d: %s (ready=%v, status=%d, interviewStage=%d)",
		node.NodeID, node.DeviceConfig.Label, node.Ready, node.Status, node.InterviewStage)
	c.nodes[node.NodeID] = &node
}

// On registers an event handler
func (c *Client) On(eventType string, handler EventHandler) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.eventHandlers[eventType] = handler
}

// Call makes a synchronous RPC call to Z-Wave JS
func (c *Client) Call(command string, args map[string]interface{}) (interface{}, error) {
	if !c.connected.Load() {
		return nil, fmt.Errorf("not connected to Z-Wave JS")
	}

	msgID := fmt.Sprintf("%d", c.messageID.Add(1))

	// Build the outgoing message as a flexible map so we can place fields
	// like nodeId at the top level when required by zwave-js-server.
	msg := map[string]interface{}{
		"type":      "request",
		"command":   command,
		"messageId": msgID,
	}

	// If args provided, and command is a node.* command, pull nodeId to top-level
	if args != nil {
		// Copy args to avoid mutating caller map
		argsCopy := make(map[string]interface{})
		for k, v := range args {
			argsCopy[k] = v
		}

		if strings.HasPrefix(command, "node.") || strings.HasPrefix(command, "controller.") {
			if nid, ok := argsCopy["nodeId"]; ok {
				msg["nodeId"] = nid
				delete(argsCopy, "nodeId")
			}
		}

		if len(argsCopy) > 0 {
			msg["args"] = argsCopy
		}
	}

	// Create response channel
	respChan := make(chan Response, 1)
	c.pending.Store(msgID, respChan)
	defer c.pending.Delete(msgID)

	// Send request (protect write with mutex)
	c.writeMu.Lock()
	c.mu.RLock()
	conn := c.conn
	c.mu.RUnlock()

	// If the connection is nil (race or disconnect), avoid a nil-pointer panic
	if conn == nil {
		c.writeMu.Unlock()
		return nil, fmt.Errorf("connection lost")
	}

	// Marshal request to JSON so we can log the exact payload sent to the server.
	reqBytes, _ := json.Marshal(msg)
	log.Printf("[ZWAVE] Sending request: %s", string(reqBytes))
	err := conn.WriteMessage(websocket.TextMessage, reqBytes)
	c.writeMu.Unlock()

	if err != nil {
		return nil, fmt.Errorf("failed to send command: %w", err)
	}

	// Wait for response with timeout
	select {
	case resp := <-respChan:
		if !resp.Success {
			log.Printf("[ZWAVE] Command failed response: messageId=%s error=%s message=%s", resp.MessageID, resp.Error, resp.Message)
			return nil, fmt.Errorf("command failed: %s", resp.Error)
		}
		return resp.Result, nil

	case <-time.After(30 * time.Second):
		return nil, fmt.Errorf("command timeout")

	case <-c.ctx.Done():
		return nil, fmt.Errorf("client stopped")
	}
}

// healthCheck periodically pings Z-Wave JS
func (c *Client) healthCheck() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if !c.connected.Load() {
				return
			}

			// Simple ping - just check if we can write
			c.writeMu.Lock()
			c.mu.RLock()
			conn := c.conn
			c.mu.RUnlock()

			if conn == nil {
				c.writeMu.Unlock()
				c.handleDisconnect()
				return
			}

			err := conn.WriteControl(websocket.PingMessage, []byte{}, time.Now().Add(10*time.Second))
			c.writeMu.Unlock()

			if err != nil {
				log.Printf("[ZWAVE] Health check failed: %v", err)
				c.handleDisconnect()
				return
			}

		case <-c.ctx.Done():
			return
		}
	}
}

// handleDisconnect handles connection loss
func (c *Client) handleDisconnect() {
	if !c.connected.Swap(false) {
		return // Already disconnected
	}

	c.mu.Lock()
	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
	c.mu.Unlock()

	log.Printf("[ZWAVE] Disconnected from Z-Wave JS, attempting reconnect...")

	if c.onDisconnect != nil {
		c.onDisconnect()
	}

	// Attempt reconnect after delay
	time.Sleep(5 * time.Second)
	c.Connect()
}

// Close shuts down the client
func (c *Client) Close() error {
	c.cancel()
	c.connected.Store(false)

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn != nil {
		return c.conn.Close()
	}

	return nil
}

// IsConnected returns connection status
func (c *Client) IsConnected() bool {
	return c.connected.Load()
}

// SetOnConnect sets callback for connection events
func (c *Client) SetOnConnect(fn func()) {
	c.onConnect = fn
}

// SetOnDisconnect sets callback for disconnection events
func (c *Client) SetOnDisconnect(fn func()) {
	c.onDisconnect = fn
}

// getMapKeys returns the keys from a map for debugging
func getMapKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
