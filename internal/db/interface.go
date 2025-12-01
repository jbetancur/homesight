package db

import (
	"context"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// DeviceRepository manages device persistence
type DeviceRepository interface {
	Get(ctx context.Context, id string) (*model.Device, error)
	List(ctx context.Context) ([]model.Device, error)
	Upsert(ctx context.Context, device *model.Device) error
	Delete(ctx context.Context, id string) error
}

// SensorRepository manages sensor persistence
type SensorRepository interface {
	Get(ctx context.Context, id string) (*model.Sensor, error)
	ListByDevice(ctx context.Context, deviceID string) ([]model.Sensor, error)
	Upsert(ctx context.Context, sensor *model.Sensor) error
	Delete(ctx context.Context, id string) error
}

// HomeRepository manages home persistence
type HomeRepository interface {
	Get(ctx context.Context, id string) (*model.Home, error)
	List(ctx context.Context) ([]model.Home, error)
	Upsert(ctx context.Context, home *model.Home) error
	Delete(ctx context.Context, id string) error
}

// ZoneRepository manages zone persistence
type ZoneRepository interface {
	Get(ctx context.Context, id string) (*model.Zone, error)
	List(ctx context.Context) ([]model.Zone, error)
	ListByHome(ctx context.Context, homeID string) ([]model.Zone, error)
	Upsert(ctx context.Context, zone *model.Zone) error
	Delete(ctx context.Context, id string) error
}

// AssetRepository manages asset persistence
type AssetRepository interface {
	Get(ctx context.Context, id string) (*model.Asset, error)
	ListByHome(ctx context.Context, homeID string) ([]model.Asset, error)
	ListByZone(ctx context.Context, zoneID string) ([]model.Asset, error)
	Upsert(ctx context.Context, asset *model.Asset) error
	Delete(ctx context.Context, id string) error
}

// IncidentRepository manages incident persistence
type IncidentRepository interface {
	Get(ctx context.Context, id string) (*model.Incident, error)
	List(ctx context.Context, filters map[string]any) ([]model.Incident, error)
	Upsert(ctx context.Context, incident *model.Incident) error
	Delete(ctx context.Context, id string) error
}

// TaskRepository manages task persistence
type TaskRepository interface {
	Get(ctx context.Context, id string) (*model.Task, error)
	List(ctx context.Context, filters map[string]any) ([]model.Task, error)
	Upsert(ctx context.Context, task *model.Task) error
	Delete(ctx context.Context, id string) error
}

// KnowledgeBaseArticle represents a knowledge base article
type KnowledgeBaseArticle struct {
	ID          string
	DeviceID    string
	Title       string
	Type        string
	Source      string
	Description string
	Available   bool
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// KnowledgeBaseRepository manages knowledge base article persistence
type KnowledgeBaseRepository interface {
	GetByDevice(ctx context.Context, deviceID string) ([]KnowledgeBaseArticle, error)
	Upsert(ctx context.Context, article *KnowledgeBaseArticle) error
	DeleteByDevice(ctx context.Context, deviceID string) error
}
