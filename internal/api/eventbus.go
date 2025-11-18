package api

import (
	"sync"
)

// EventType represents the type of change
const (
	DeviceAdded     = "device_added"
	DeviceUpdated   = "device_updated"
	DeviceRemoved   = "device_removed"
	IncidentAdded   = "incident_added"
	IncidentUpdated = "incident_updated"
	IncidentRemoved = "incident_removed"
)

type Event struct {
	Type string      `json:"type"`
	Data interface{} `json:"data"`
}

type EventBus struct {
	listeners []chan Event
	mutex     sync.Mutex
}

func NewEventBus() *EventBus {
	return &EventBus{
		listeners: make([]chan Event, 0),
	}
}

func (b *EventBus) Subscribe() chan Event {
	b.mutex.Lock()
	defer b.mutex.Unlock()
	ch := make(chan Event, 10)
	b.listeners = append(b.listeners, ch)
	return ch
}

func (b *EventBus) Publish(event Event) {
	b.mutex.Lock()
	defer b.mutex.Unlock()
	for _, ch := range b.listeners {
		select {
		case ch <- event:
		default:
		}
	}
}

func (b *EventBus) Unsubscribe(ch chan Event) {
	b.mutex.Lock()
	defer b.mutex.Unlock()
	for i, c := range b.listeners {
		if c == ch {
			b.listeners = append(b.listeners[:i], b.listeners[i+1:]...)
			close(c)
			break
		}
	}
}
