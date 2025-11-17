package metrics

import (
	"context"
	"fmt"
	"time"

	"github.com/homesight/homesight/internal/model"
	promapi "github.com/prometheus/client_golang/api"
	promv1 "github.com/prometheus/client_golang/api/prometheus/v1"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	prommodel "github.com/prometheus/common/model"
)

// PrometheusMetricsSink implements MetricsSink using Prometheus
type PrometheusMetricsSink struct {
	gauges map[string]prometheus.Gauge
	client promv1.API
}

// NewPrometheusMetricsSink creates a new Prometheus metrics sink
func NewPrometheusMetricsSink(prometheusURL string) (*PrometheusMetricsSink, error) {
	client, err := promapi.NewClient(promapi.Config{
		Address: prometheusURL,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create Prometheus client: %w", err)
	}

	return &PrometheusMetricsSink{
		gauges: make(map[string]prometheus.Gauge),
		client: promv1.NewAPI(client),
	}, nil
}

// Record stores a metric data point
func (s *PrometheusMetricsSink) Record(ctx context.Context, sensorID string, ts time.Time, value float64, labels map[string]string) error {
	gauge, ok := s.gauges[sensorID]
	if !ok {
		promLabels := prometheus.Labels{"sensor_id": sensorID}
		for k, v := range labels {
			promLabels[k] = v
		}

		gauge = promauto.NewGauge(prometheus.GaugeOpts{
			Name:        fmt.Sprintf("homesight_sensor_%s", sensorID),
			Help:        fmt.Sprintf("Sensor reading for %s", sensorID),
			ConstLabels: promLabels,
		})
		s.gauges[sensorID] = gauge
	}

	gauge.Set(value)
	return nil
}

// Query retrieves metrics for a sensor within a time range
func (s *PrometheusMetricsSink) Query(ctx context.Context, sensorID string, from, to time.Time) ([]model.MetricPoint, error) {
	query := fmt.Sprintf(`homesight_sensor_%s`, sensorID)
	r := promv1.Range{
		Start: from,
		End:   to,
		Step:  time.Minute,
	}

	result, warnings, err := s.client.QueryRange(ctx, query, r)
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}
	if len(warnings) > 0 {
		// Log warnings if needed
	}

	matrix, ok := result.(prommodel.Matrix)
	if !ok {
		return nil, fmt.Errorf("unexpected result type: %T", result)
	}

	points := make([]model.MetricPoint, 0)
	for _, stream := range matrix {
		labels := make(map[string]string)
		for k, v := range stream.Metric {
			labels[string(k)] = string(v)
		}

		for _, value := range stream.Values {
			points = append(points, model.MetricPoint{
				Timestamp: value.Timestamp.Time(),
				Value:     float64(value.Value),
				Labels:    labels,
			})
		}
	}

	return points, nil
}

// Close shuts down the metrics sink
func (s *PrometheusMetricsSink) Close() error {
	return nil
}
