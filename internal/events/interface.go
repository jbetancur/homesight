package events

import "github.com/homesight/homesight/internal/model"

// EventBus provides pub/sub for device events
type EventBus interface {
	// Publish sends an event to all subscribers
	Publish(event model.DeviceEvent)

	// Subscribe returns a channel of events
	Subscribe() <-chan model.DeviceEvent

	// Close shuts down the event bus
	Close() error
}
