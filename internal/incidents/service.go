package incidents

import (
	"context"
	"fmt"
	"time"

	"github.com/homesight/homesight/internal/db"
	"github.com/homesight/homesight/internal/model"
)

// Service implements IncidentService
type Service struct {
	repo db.IncidentRepository
}

// NewService creates a new incident service
func NewService(repo db.IncidentRepository) *Service {
	return &Service{
		repo: repo,
	}
}

// CreateOrUpdate creates a new incident or updates an existing one
func (s *Service) CreateOrUpdate(ctx context.Context, incident *model.Incident) error {
	if incident.ID == "" {
		return fmt.Errorf("incident ID is required")
	}

	// Check if incident exists
	existing, err := s.repo.Get(ctx, incident.ID)
	if err == nil && existing != nil {
		// Update existing
		incident.CreatedAt = existing.CreatedAt
		incident.UpdatedAt = time.Now()
	} else {
		// New incident
		incident.CreatedAt = time.Now()
		incident.UpdatedAt = time.Now()
	}

	return s.repo.Upsert(ctx, incident)
}

// Get retrieves an incident by ID
func (s *Service) Get(ctx context.Context, id string) (*model.Incident, error) {
	return s.repo.Get(ctx, id)
}

// ListOpen returns all open incidents
func (s *Service) ListOpen(ctx context.Context) ([]model.Incident, error) {
	filters := map[string]any{
		"status": model.StatusOpen,
	}
	return s.repo.List(ctx, filters)
}

// List returns incidents with optional filters
func (s *Service) List(ctx context.Context, filters map[string]any) ([]model.Incident, error) {
	return s.repo.List(ctx, filters)
}

// Resolve marks an incident as resolved
func (s *Service) Resolve(ctx context.Context, id string) error {
	incident, err := s.repo.Get(ctx, id)
	if err != nil {
		return err
	}

	now := time.Now()
	incident.Status = model.StatusResolved
	incident.ResolvedAt = &now
	incident.UpdatedAt = now

	return s.repo.Upsert(ctx, incident)
}

// Close shuts down the incident service
func (s *Service) Close() error {
	return nil
}
