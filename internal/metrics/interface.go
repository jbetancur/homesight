package metrics

import (
	"context"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// MetricsSink abstracts the time-series database
type MetricsSink interface {
	// Record stores a metric data point
	Record(ctx context.Context, sensorID string, ts time.Time, value float64, labels map[string]string) error

	// Query retrieves metrics for a sensor within a time range
	Query(ctx context.Context, sensorID string, from, to time.Time) ([]model.MetricPoint, error)

	// Close shuts down the metrics sink
	Close() error
}
