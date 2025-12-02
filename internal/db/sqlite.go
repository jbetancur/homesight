package db

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/homesight/homesight/internal/model"
	_ "github.com/mattn/go-sqlite3"
)

// SQLiteDB wraps the SQLite database connection
type SQLiteDB struct {
	db *sql.DB
}

// NewSQLiteDB creates a new SQLite database connection
func NewSQLiteDB(path string) (*SQLiteDB, error) {
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	sqlDB := &SQLiteDB{db: db}
	if err := sqlDB.initSchema(); err != nil {
		return nil, fmt.Errorf("failed to initialize schema: %w", err)
	}

	return sqlDB, nil
}

// initSchema creates the database schema
func (s *SQLiteDB) initSchema() error {
	schema := `
		CREATE TABLE IF NOT EXISTS homes (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			address TEXT,
			metadata TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL
		);

		CREATE TABLE IF NOT EXISTS zones (
			id TEXT PRIMARY KEY,
			home_id TEXT NOT NULL,
			name TEXT NOT NULL,
			type TEXT,
			parent_id TEXT,
			attributes TEXT,
			metadata TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (home_id) REFERENCES homes(id)
		);

		CREATE TABLE IF NOT EXISTS assets (
			id TEXT PRIMARY KEY,
			home_id TEXT NOT NULL,
			zone_id TEXT,
			name TEXT NOT NULL,
			type TEXT,
			manufacturer TEXT,
			model TEXT,
			install_date DATETIME,
			metadata TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (home_id) REFERENCES homes(id),
			FOREIGN KEY (zone_id) REFERENCES zones(id)
		);

		CREATE TABLE IF NOT EXISTS devices (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			alias TEXT,
			type TEXT,
			integration TEXT,
			zone_id TEXT,
			asset_id TEXT,
			enabled BOOLEAN DEFAULT 1,
			last_seen DATETIME,
			metadata TEXT,
			docs_ingested BOOLEAN DEFAULT 0,
			docs_ingested_at DATETIME,
			docs_status TEXT DEFAULT 'pending',
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (zone_id) REFERENCES zones(id),
			FOREIGN KEY (asset_id) REFERENCES assets(id)
		);

		CREATE TABLE IF NOT EXISTS sensors (
			id TEXT PRIMARY KEY,
			device_id TEXT NOT NULL,
			name TEXT NOT NULL,
			type TEXT,
			unit TEXT,
			metadata TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (device_id) REFERENCES devices(id)
		);

		CREATE TABLE IF NOT EXISTS incidents (
			id TEXT PRIMARY KEY,
			type TEXT NOT NULL DEFAULT 'generic',
			title TEXT NOT NULL,
			description TEXT,
			severity TEXT NOT NULL,
			status TEXT NOT NULL,
			device_id TEXT,
			sensor_id TEXT,
			zone_id TEXT,
			asset_id TEXT,
			rule_name TEXT,
			data TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			resolved_at DATETIME,
			analysis_status TEXT DEFAULT 'pending',
			analysis TEXT,
			insights TEXT,
			actions TEXT,
			analysis_data TEXT,
			analyzed_at DATETIME,
			FOREIGN KEY (device_id) REFERENCES devices(id),
			FOREIGN KEY (sensor_id) REFERENCES sensors(id),
			FOREIGN KEY (zone_id) REFERENCES zones(id),
			FOREIGN KEY (asset_id) REFERENCES assets(id)
		);

		CREATE TABLE IF NOT EXISTS tasks (
			id TEXT PRIMARY KEY,
			title TEXT NOT NULL,
			description TEXT,
			priority TEXT,
			status TEXT NOT NULL,
			asset_id TEXT,
			zone_id TEXT,
			due_date DATETIME,
			completed_at DATETIME,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (asset_id) REFERENCES assets(id),
			FOREIGN KEY (zone_id) REFERENCES zones(id)
		);

		CREATE TABLE IF NOT EXISTS knowledge_base (
			id TEXT PRIMARY KEY,
			device_id TEXT NOT NULL,
			manufacturer TEXT,
			model TEXT,
			content TEXT,
			source TEXT,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (device_id) REFERENCES devices(id)
		);

		CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
		CREATE INDEX IF NOT EXISTS idx_incidents_device ON incidents(device_id);
		CREATE INDEX IF NOT EXISTS idx_devices_zone ON devices(zone_id);
		CREATE INDEX IF NOT EXISTS idx_sensors_device ON sensors(device_id);
		CREATE INDEX IF NOT EXISTS idx_kb_device ON knowledge_base(device_id);
		CREATE INDEX IF NOT EXISTS idx_kb_model ON knowledge_base(manufacturer, model);
		CREATE INDEX IF NOT EXISTS idx_zones_type ON zones(type);
	`

	_, err := s.db.Exec(schema)
	if err != nil {
		return err
	}

	// Run migrations for existing databases
	return s.runMigrations()
}

// runMigrations applies schema updates for existing databases
func (s *SQLiteDB) runMigrations() error {
	// Migration: Add attributes column to zones if it doesn't exist
	_, err := s.db.Exec(`ALTER TABLE zones ADD COLUMN attributes TEXT`)
	if err != nil {
		// Ignore error if column already exists
		// SQLite doesn't have "IF NOT EXISTS" for ALTER TABLE
	}

	// Migration: Add alias column to devices if it doesn't exist
	_, err = s.db.Exec(`ALTER TABLE devices ADD COLUMN alias TEXT`)
	if err != nil {
		// Ignore error if column already exists
	}

	return nil
}

// Close closes the database connection
func (s *SQLiteDB) Close() error {
	return s.db.Close()
}

// DeviceRepo implements DeviceRepository
type DeviceRepo struct {
	db *sql.DB
}

// NewDeviceRepo creates a new device repository
func NewDeviceRepo(db *SQLiteDB) *DeviceRepo {
	return &DeviceRepo{db: db.db}
}

func (r *DeviceRepo) Get(ctx context.Context, id string) (*model.Device, error) {
	var d model.Device
	var metadataJSON sql.NullString
	var lastSeen sql.NullTime
	var docsIngestedAt sql.NullTime
	var alias sql.NullString

	err := r.db.QueryRowContext(ctx,
		`SELECT id, name, alias, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at
		 FROM devices WHERE id = ?`, id).Scan(
		&d.ID, &d.Name, &alias, &d.Type, &d.Integration, &d.ZoneID, &d.AssetID, &d.Enabled, &lastSeen, &metadataJSON, &d.DocsIngested, &docsIngestedAt, &d.DocsStatus, &d.CreatedAt, &d.UpdatedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	if lastSeen.Valid {
		d.LastSeen = lastSeen.Time
	}
	if docsIngestedAt.Valid {
		d.DocsIngestedAt = &docsIngestedAt.Time
	}
	if metadataJSON.Valid {
		json.Unmarshal([]byte(metadataJSON.String), &d.Metadata)
	}
	if alias.Valid {
		d.Alias = alias.String
	}

	return &d, nil
}

func (r *DeviceRepo) List(ctx context.Context) ([]model.Device, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, name, alias, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at
		 FROM devices ORDER BY COALESCE(alias, name)`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	devices := make([]model.Device, 0)
	for rows.Next() {
		var d model.Device
		var metadataJSON sql.NullString
		var lastSeen sql.NullTime
		var docsIngestedAt sql.NullTime
		var alias sql.NullString

		if err := rows.Scan(&d.ID, &d.Name, &alias, &d.Type, &d.Integration, &d.ZoneID, &d.AssetID, &d.Enabled, &lastSeen, &metadataJSON, &d.DocsIngested, &docsIngestedAt, &d.DocsStatus, &d.CreatedAt, &d.UpdatedAt); err != nil {
			return nil, err
		}

		if lastSeen.Valid {
			d.LastSeen = lastSeen.Time
		}
		if docsIngestedAt.Valid {
			d.DocsIngestedAt = &docsIngestedAt.Time
		}
		if metadataJSON.Valid {
			json.Unmarshal([]byte(metadataJSON.String), &d.Metadata)
		}
		if alias.Valid {
			d.Alias = alias.String
		}

		devices = append(devices, d)
	}

	return devices, nil
}

func (r *DeviceRepo) Upsert(ctx context.Context, device *model.Device) error {
	metadataJSON, _ := json.Marshal(device.Metadata)
	device.UpdatedAt = time.Now()

	// Use nullAlias to properly handle empty strings as NULL
	var nullAlias sql.NullString
	if device.Alias != "" {
		nullAlias = sql.NullString{String: device.Alias, Valid: true}
	}

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO devices (id, name, alias, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		device.ID, device.Name, nullAlias, device.Type, device.Integration, device.ZoneID, device.AssetID, device.Enabled,
		device.LastSeen, string(metadataJSON), device.DocsIngested, device.DocsIngestedAt, device.DocsStatus, device.CreatedAt, device.UpdatedAt)
	return err
}

// Update updates specific fields of a device
func (r *DeviceRepo) Update(ctx context.Context, id string, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	// Build dynamic UPDATE query
	setClauses := make([]string, 0, len(updates)+1)
	args := make([]interface{}, 0, len(updates)+2)

	// Allowed fields that can be updated
	allowedFields := map[string]bool{
		"alias":   true,
		"name":    true,
		"type":    true,
		"zone_id": true,
		"enabled": true,
	}

	for field, value := range updates {
		if !allowedFields[field] {
			continue // Skip disallowed fields
		}

		// Handle nullable string fields
		if field == "alias" {
			if strVal, ok := value.(string); ok {
				if strVal == "" {
					setClauses = append(setClauses, field+" = NULL")
				} else {
					setClauses = append(setClauses, field+" = ?")
					args = append(args, strVal)
				}
			}
		} else {
			setClauses = append(setClauses, field+" = ?")
			args = append(args, value)
		}
	}

	if len(setClauses) == 0 {
		return nil
	}

	// Always update updated_at
	setClauses = append(setClauses, "updated_at = ?")
	args = append(args, time.Now())

	// Add id for WHERE clause
	args = append(args, id)

	query := fmt.Sprintf("UPDATE devices SET %s WHERE id = ?", strings.Join(setClauses, ", "))
	_, err := r.db.ExecContext(ctx, query, args...)
	return err
}

func (r *DeviceRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM devices WHERE id = ?`, id)
	return err
}

// SensorRepo implements SensorRepository
type SensorRepo struct {
	db *sql.DB
}

// NewSensorRepo creates a new sensor repository
func NewSensorRepo(db *SQLiteDB) *SensorRepo {
	return &SensorRepo{db: db.db}
}

func (r *SensorRepo) Get(ctx context.Context, id string) (*model.Sensor, error) {
	var s model.Sensor
	var metadataJSON sql.NullString

	err := r.db.QueryRowContext(ctx,
		`SELECT id, device_id, name, type, unit, metadata, created_at, updated_at
		 FROM sensors WHERE id = ?`, id).Scan(
		&s.ID, &s.DeviceID, &s.Name, &s.Type, &s.Unit, &metadataJSON, &s.CreatedAt, &s.UpdatedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	if metadataJSON.Valid {
		json.Unmarshal([]byte(metadataJSON.String), &s.Metadata)
	}

	return &s, nil
}

func (r *SensorRepo) ListByDevice(ctx context.Context, deviceID string) ([]model.Sensor, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, device_id, name, type, unit, metadata, created_at, updated_at
		 FROM sensors WHERE device_id = ? ORDER BY name`, deviceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	sensors := make([]model.Sensor, 0)
	for rows.Next() {
		var s model.Sensor
		var metadataJSON sql.NullString

		if err := rows.Scan(&s.ID, &s.DeviceID, &s.Name, &s.Type, &s.Unit, &metadataJSON, &s.CreatedAt, &s.UpdatedAt); err != nil {
			return nil, err
		}

		if metadataJSON.Valid {
			json.Unmarshal([]byte(metadataJSON.String), &s.Metadata)
		}

		sensors = append(sensors, s)
	}

	return sensors, nil
}

func (r *SensorRepo) Upsert(ctx context.Context, sensor *model.Sensor) error {
	metadataJSON, _ := json.Marshal(sensor.Metadata)
	sensor.UpdatedAt = time.Now()

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO sensors (id, device_id, name, type, unit, metadata, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		sensor.ID, sensor.DeviceID, sensor.Name, sensor.Type, sensor.Unit, string(metadataJSON), sensor.CreatedAt, sensor.UpdatedAt)
	return err
}

func (r *SensorRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM sensors WHERE id = ?`, id)
	return err
}

// IncidentRepo implements IncidentRepository
type IncidentRepo struct {
	db *sql.DB
}

// NewIncidentRepo creates a new incident repository
func NewIncidentRepo(db *SQLiteDB) *IncidentRepo {
	return &IncidentRepo{db: db.db}
}

func (r *IncidentRepo) Get(ctx context.Context, id string) (*model.Incident, error) {
	var i model.Incident
	var dataJSON sql.NullString
	var resolvedAt sql.NullTime
	var insightsJSON sql.NullString
	var actionsJSON sql.NullString
	var analysisDataJSON sql.NullString
	var analyzedAt sql.NullTime

	err := r.db.QueryRowContext(ctx,
		`SELECT id, type, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at, analysis_status, analysis, insights, actions, analysis_data, analyzed_at
		 FROM incidents WHERE id = ?`, id).Scan(
		&i.ID, &i.Type, &i.Title, &i.Description, &i.Severity, &i.Status, &i.DeviceID, &i.SensorID, &i.ZoneID, &i.AssetID, &i.RuleName, &dataJSON, &i.CreatedAt, &i.UpdatedAt, &resolvedAt, &i.AnalysisStatus, &i.Analysis, &insightsJSON, &actionsJSON, &analysisDataJSON, &analyzedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	if resolvedAt.Valid {
		i.ResolvedAt = &resolvedAt.Time
	}
	if dataJSON.Valid {
		json.Unmarshal([]byte(dataJSON.String), &i.Data)
	}
	if insightsJSON.Valid {
		json.Unmarshal([]byte(insightsJSON.String), &i.Insights)
	}
	if actionsJSON.Valid {
		json.Unmarshal([]byte(actionsJSON.String), &i.Actions)
	}
	if analysisDataJSON.Valid {
		json.Unmarshal([]byte(analysisDataJSON.String), &i.AnalysisData)
	}
	if analyzedAt.Valid {
		i.AnalyzedAt = &analyzedAt.Time
	}

	return &i, nil
}

func (r *IncidentRepo) List(ctx context.Context, filters map[string]any) ([]model.Incident, error) {
	query := `SELECT id, type, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at, analysis_status, analysis, insights, actions, analysis_data, analyzed_at FROM incidents WHERE 1=1`
	args := make([]any, 0)

	if status, ok := filters["status"]; ok {
		query += ` AND status = ?`
		args = append(args, status)
	}
	if deviceID, ok := filters["device_id"]; ok {
		query += ` AND device_id = ?`
		args = append(args, deviceID)
	}

	query += ` ORDER BY created_at DESC`

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	incidents := make([]model.Incident, 0)
	for rows.Next() {
		var i model.Incident
		var dataJSON sql.NullString
		var resolvedAt sql.NullTime
		var insightsJSON sql.NullString
		var actionsJSON sql.NullString
		var analysisDataJSON sql.NullString
		var analyzedAt sql.NullTime

		if err := rows.Scan(&i.ID, &i.Type, &i.Title, &i.Description, &i.Severity, &i.Status, &i.DeviceID, &i.SensorID, &i.ZoneID, &i.AssetID, &i.RuleName, &dataJSON, &i.CreatedAt, &i.UpdatedAt, &resolvedAt, &i.AnalysisStatus, &i.Analysis, &insightsJSON, &actionsJSON, &analysisDataJSON, &analyzedAt); err != nil {
			return nil, err
		}

		if resolvedAt.Valid {
			i.ResolvedAt = &resolvedAt.Time
		}
		if dataJSON.Valid {
			json.Unmarshal([]byte(dataJSON.String), &i.Data)
		}
		if insightsJSON.Valid {
			json.Unmarshal([]byte(insightsJSON.String), &i.Insights)
		}
		if actionsJSON.Valid {
			json.Unmarshal([]byte(actionsJSON.String), &i.Actions)
		}
		if analysisDataJSON.Valid {
			json.Unmarshal([]byte(analysisDataJSON.String), &i.AnalysisData)
		}
		if analyzedAt.Valid {
			i.AnalyzedAt = &analyzedAt.Time
		}

		incidents = append(incidents, i)
	}

	return incidents, nil
}

func (r *IncidentRepo) Upsert(ctx context.Context, incident *model.Incident) error {
	dataJSON, _ := json.Marshal(incident.Data)
	insightsJSON, _ := json.Marshal(incident.Insights)
	actionsJSON, _ := json.Marshal(incident.Actions)
	analysisDataJSON, _ := json.Marshal(incident.AnalysisData)

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO incidents (id, type, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at, analysis_status, analysis, insights, actions, analysis_data, analyzed_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		incident.ID, incident.Type, incident.Title, incident.Description, incident.Severity, incident.Status,
		incident.DeviceID, incident.SensorID, incident.ZoneID, incident.AssetID, incident.RuleName,
		string(dataJSON), incident.CreatedAt, incident.UpdatedAt, incident.ResolvedAt,
		incident.AnalysisStatus, incident.Analysis, string(insightsJSON), string(actionsJSON), string(analysisDataJSON), incident.AnalyzedAt)
	return err
}

func (r *IncidentRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM incidents WHERE id = ?`, id)
	return err
}

// KnowledgeBaseRepo implements KnowledgeBaseRepository
type KnowledgeBaseRepo struct {
	db *sql.DB
}

// NewKnowledgeBaseRepo creates a new knowledge base repository
func NewKnowledgeBaseRepo(db *SQLiteDB) *KnowledgeBaseRepo {
	return &KnowledgeBaseRepo{db: db.db}
}

func (r *KnowledgeBaseRepo) GetByDevice(ctx context.Context, deviceID string) (*KnowledgeBase, error) {
	row := r.db.QueryRowContext(ctx,
		`SELECT id, device_id, manufacturer, model, content, source, created_at, updated_at
		 FROM knowledge_base WHERE device_id = ?`, deviceID)

	var kb KnowledgeBase
	err := row.Scan(&kb.ID, &kb.DeviceID, &kb.Manufacturer, &kb.Model, &kb.Content, &kb.Source, &kb.CreatedAt, &kb.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &kb, nil
}

// GetByManufacturerModel finds KB from any device with the same manufacturer/model.
// This enables model-level KB deduplication - generate once per model, share across all devices.
func (r *KnowledgeBaseRepo) GetByManufacturerModel(ctx context.Context, manufacturer, model string) (*KnowledgeBase, error) {
	row := r.db.QueryRowContext(ctx,
		`SELECT id, device_id, manufacturer, model, content, source, created_at, updated_at
		 FROM knowledge_base 
		 WHERE manufacturer = ? AND model = ?
		 LIMIT 1`, manufacturer, model)

	var kb KnowledgeBase
	err := row.Scan(&kb.ID, &kb.DeviceID, &kb.Manufacturer, &kb.Model, &kb.Content, &kb.Source, &kb.CreatedAt, &kb.UpdatedAt)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &kb, nil
}

func (r *KnowledgeBaseRepo) Upsert(ctx context.Context, kb *KnowledgeBase) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO knowledge_base (id, device_id, manufacturer, model, content, source, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		kb.ID, kb.DeviceID, kb.Manufacturer, kb.Model, kb.Content, kb.Source, kb.CreatedAt, kb.UpdatedAt)
	return err
}

func (r *KnowledgeBaseRepo) DeleteByDevice(ctx context.Context, deviceID string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM knowledge_base WHERE device_id = ?`, deviceID)
	return err
}

// DeleteByManufacturerModel deletes all KB entries for a given manufacturer/model.
// Used when force-regenerating KB to prevent deduplication from copying old content.
func (r *KnowledgeBaseRepo) DeleteByManufacturerModel(ctx context.Context, manufacturer, model string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM knowledge_base WHERE manufacturer = ? AND model = ?`, manufacturer, model)
	return err
}
