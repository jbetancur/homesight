package incidents

import (
	"context"

	"github.com/homesight/homesight/internal/model"
)

// EventPublisher is an interface for publishing incident events
type EventPublisher interface {
	PublishIncidentCreated(incident *model.Incident)
	PublishIncidentUpdated(incident *model.Incident)
	PublishIncidentResolved(incident *model.Incident)
}

// EventAwareService wraps an IncidentService and publishes events
type EventAwareService struct {
	service   IncidentService
	publisher EventPublisher
}

// NewEventAwareService creates a new event-aware incident service
func NewEventAwareService(service IncidentService, publisher EventPublisher) *EventAwareService {
	return &EventAwareService{
		service:   service,
		publisher: publisher,
	}
}

// CreateOrUpdate creates or updates an incident and publishes events
func (s *EventAwareService) CreateOrUpdate(ctx context.Context, incident *model.Incident) error {
	// Check if incident exists
	existing, _ := s.service.Get(ctx, incident.ID)
	isNew := existing == nil

	// Call underlying service
	if err := s.service.CreateOrUpdate(ctx, incident); err != nil {
		return err
	}

	// Publish appropriate event
	if s.publisher != nil {
		if isNew {
			s.publisher.PublishIncidentCreated(incident)
		} else {
			s.publisher.PublishIncidentUpdated(incident)
		}
	}

	return nil
}

// Get retrieves an incident by ID
func (s *EventAwareService) Get(ctx context.Context, id string) (*model.Incident, error) {
	return s.service.Get(ctx, id)
}

// ListOpen returns all open incidents
func (s *EventAwareService) ListOpen(ctx context.Context) ([]model.Incident, error) {
	return s.service.ListOpen(ctx)
}

// List returns incidents with optional filters
func (s *EventAwareService) List(ctx context.Context, filters map[string]any) ([]model.Incident, error) {
	return s.service.List(ctx, filters)
}

// Resolve marks an incident as resolved and publishes event
func (s *EventAwareService) Resolve(ctx context.Context, id string) error {
	// Call underlying service
	if err := s.service.Resolve(ctx, id); err != nil {
		return err
	}

	// Get resolved incident for event
	if s.publisher != nil {
		if incident, err := s.service.Get(ctx, id); err == nil && incident != nil {
			s.publisher.PublishIncidentResolved(incident)
		}
	}

	return nil
}

// Delete removes an incident (for demo/testing purposes)
func (s *EventAwareService) Delete(ctx context.Context, id string) error {
	return s.service.Delete(ctx, id)
}

// Close shuts down the incident service
func (s *EventAwareService) Close() error {
	return s.service.Close()
}
