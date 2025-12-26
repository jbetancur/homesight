package incidents

import (
	"context"

	"github.com/homesight/homesight/internal/model"
)

// IncidentService manages incident lifecycle
type IncidentService interface {
	// CreateOrUpdate creates a new incident or updates an existing one
	CreateOrUpdate(ctx context.Context, incident *model.Incident) error

	// Get retrieves an incident by ID
	Get(ctx context.Context, id string) (*model.Incident, error)

	// ListOpen returns all open incidents
	ListOpen(ctx context.Context) ([]model.Incident, error)

	// List returns incidents with optional filters
	List(ctx context.Context, filters map[string]any) ([]model.Incident, error)

	// Resolve marks an incident as resolved
	Resolve(ctx context.Context, id string) error

	// Acknowledge marks an incident as acknowledged (user has seen it)
	Acknowledge(ctx context.Context, id string, notes string) error

	// Ignore marks an incident as ignored/dismissed (false positive or not actionable)
	Ignore(ctx context.Context, id string, notes string) error

	// Delete removes an incident (for demo/testing purposes)
	Delete(ctx context.Context, id string) error

	// Close shuts down the incident service
	Close() error
}
