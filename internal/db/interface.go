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
	Update(ctx context.Context, id string, updates map[string]interface{}) error
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

// HomeProfileRepository manages home profile persistence
type HomeProfileRepository interface {
	Get(ctx context.Context, homeID string) (*model.HomeProfile, error)
	Upsert(ctx context.Context, profile *model.HomeProfile) error
	Delete(ctx context.Context, homeID string) error
}

// AttributeDefinitionRepository manages custom attribute definitions
type AttributeDefinitionRepository interface {
	Get(ctx context.Context, id string) (*model.AttributeDefinition, error)
	List(ctx context.Context, scope model.AttributeScope) ([]model.AttributeDefinition, error)
	Upsert(ctx context.Context, def *model.AttributeDefinition) error
	Delete(ctx context.Context, id string) error
}

// ZoneAttributeValueRepository manages zone attribute values
type ZoneAttributeValueRepository interface {
	Get(ctx context.Context, zoneID, attributeID string) (string, error)
	ListByZone(ctx context.Context, zoneID string) (map[string]string, error)
	Set(ctx context.Context, zoneID, attributeID, value string) error
	Delete(ctx context.Context, zoneID, attributeID string) error
}

// KnowledgeBase represents a single knowledge base document for a device
// Simplified from multiple articles to one comprehensive document per device model
type KnowledgeBase struct {
	ID           string
	DeviceID     string
	Manufacturer string // For model-level deduplication
	Model        string // For model-level deduplication
	Content      string // Markdown content with all sections
	Source       string // e.g., "Official Zooz Documentation + AI Summary"
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

// SensorReadingRepository manages time-series sensor readings
type SensorReadingRepository interface {
	Insert(ctx context.Context, deviceID, readingType string, value float64, outdoorTemp *float64) error
	Query(ctx context.Context, deviceID, readingType string, since time.Time, limit int) ([]SensorReading, error)
	CleanupOld(ctx context.Context, olderThan time.Duration) (int64, error)
}

// KnowledgeBaseRepository manages knowledge base persistence
type KnowledgeBaseRepository interface {
	GetByDevice(ctx context.Context, deviceID string) (*KnowledgeBase, error)
	// GetByManufacturerModel finds KB from any device with the same manufacturer/model
	// Used for model-level deduplication - generate KB once per model, share across devices
	GetByManufacturerModel(ctx context.Context, manufacturer, model string) (*KnowledgeBase, error)
	Upsert(ctx context.Context, kb *KnowledgeBase) error
	DeleteByDevice(ctx context.Context, deviceID string) error
	// DeleteByManufacturerModel deletes all KB entries for a given manufacturer/model
	// Used when force-regenerating KB to prevent deduplication from copying old content
	DeleteByManufacturerModel(ctx context.Context, manufacturer, model string) error
}
