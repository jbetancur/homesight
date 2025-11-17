package metrics

import (
	"context"
	"sync"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// MockMetricsSink is an in-memory metrics sink for testing
type MockMetricsSink struct {
	mu     sync.RWMutex
	points map[string][]model.MetricPoint
}

// NewMockMetricsSink creates a new mock metrics sink
func NewMockMetricsSink() *MockMetricsSink {
	return &MockMetricsSink{
		points: make(map[string][]model.MetricPoint),
	}
}

// Record stores a metric data point
func (s *MockMetricsSink) Record(ctx context.Context, sensorID string, ts time.Time, value float64, labels map[string]string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	point := model.MetricPoint{
		Timestamp: ts,
		Value:     value,
		Labels:    labels,
	}

	s.points[sensorID] = append(s.points[sensorID], point)
	return nil
}

// Query retrieves metrics for a sensor within a time range
func (s *MockMetricsSink) Query(ctx context.Context, sensorID string, from, to time.Time) ([]model.MetricPoint, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	all := s.points[sensorID]
	filtered := make([]model.MetricPoint, 0)

	for _, p := range all {
		if (p.Timestamp.Equal(from) || p.Timestamp.After(from)) &&
			(p.Timestamp.Equal(to) || p.Timestamp.Before(to)) {
			filtered = append(filtered, p)
		}
	}

	return filtered, nil
}

// Close shuts down the metrics sink
func (s *MockMetricsSink) Close() error {
	return nil
}
