package events

import (
	"sync"

	"github.com/homesight/homesight/internal/model"
)

// ChannelEventBus is an in-memory event bus using Go channels
type ChannelEventBus struct {
	subscribers []chan model.DeviceEvent
	mu          sync.RWMutex
	closed      bool
}

// NewChannelEventBus creates a new channel-based event bus
func NewChannelEventBus() *ChannelEventBus {
	return &ChannelEventBus{
		subscribers: make([]chan model.DeviceEvent, 0),
	}
}

// Publish sends an event to all subscribers
func (b *ChannelEventBus) Publish(event model.DeviceEvent) {
	b.mu.RLock()
	defer b.mu.RUnlock()

	if b.closed {
		return
	}

	for _, ch := range b.subscribers {
		select {
		case ch <- event:
		default:
			// Skip slow consumers
		}
	}
}

// Subscribe returns a channel of events
func (b *ChannelEventBus) Subscribe() <-chan model.DeviceEvent {
	b.mu.Lock()
	defer b.mu.Unlock()

	ch := make(chan model.DeviceEvent, 100)
	b.subscribers = append(b.subscribers, ch)
	return ch
}

// Close shuts down the event bus
func (b *ChannelEventBus) Close() error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if b.closed {
		return nil
	}

	b.closed = true
	for _, ch := range b.subscribers {
		close(ch)
	}
	b.subscribers = nil
	return nil
}
