package db

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
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

		CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
		CREATE INDEX IF NOT EXISTS idx_incidents_device ON incidents(device_id);
		CREATE INDEX IF NOT EXISTS idx_devices_zone ON devices(zone_id);
		CREATE INDEX IF NOT EXISTS idx_sensors_device ON sensors(device_id);
	`

	_, err := s.db.Exec(schema)
	return err
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

	err := r.db.QueryRowContext(ctx,
		`SELECT id, name, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at
		 FROM devices WHERE id = ?`, id).Scan(
		&d.ID, &d.Name, &d.Type, &d.Integration, &d.ZoneID, &d.AssetID, &d.Enabled, &lastSeen, &metadataJSON, &d.DocsIngested, &docsIngestedAt, &d.DocsStatus, &d.CreatedAt, &d.UpdatedAt)

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

	return &d, nil
}

func (r *DeviceRepo) List(ctx context.Context) ([]model.Device, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, name, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at
		 FROM devices ORDER BY name`)
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

		if err := rows.Scan(&d.ID, &d.Name, &d.Type, &d.Integration, &d.ZoneID, &d.AssetID, &d.Enabled, &lastSeen, &metadataJSON, &d.DocsIngested, &docsIngestedAt, &d.DocsStatus, &d.CreatedAt, &d.UpdatedAt); err != nil {
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

		devices = append(devices, d)
	}

	return devices, nil
}

func (r *DeviceRepo) Upsert(ctx context.Context, device *model.Device) error {
	metadataJSON, _ := json.Marshal(device.Metadata)
	device.UpdatedAt = time.Now()

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO devices (id, name, type, integration, zone_id, asset_id, enabled, last_seen, metadata, docs_ingested, docs_ingested_at, docs_status, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		device.ID, device.Name, device.Type, device.Integration, device.ZoneID, device.AssetID, device.Enabled,
		device.LastSeen, string(metadataJSON), device.DocsIngested, device.DocsIngestedAt, device.DocsStatus, device.CreatedAt, device.UpdatedAt)
	return err
}

func (r *DeviceRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM devices WHERE id = ?`, id)
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

	err := r.db.QueryRowContext(ctx,
		`SELECT id, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at
		 FROM incidents WHERE id = ?`, id).Scan(
		&i.ID, &i.Title, &i.Description, &i.Severity, &i.Status, &i.DeviceID, &i.SensorID, &i.ZoneID, &i.AssetID, &i.RuleName, &dataJSON, &i.CreatedAt, &i.UpdatedAt, &resolvedAt)

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

	return &i, nil
}

func (r *IncidentRepo) List(ctx context.Context, filters map[string]any) ([]model.Incident, error) {
	query := `SELECT id, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at FROM incidents WHERE 1=1`
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

		if err := rows.Scan(&i.ID, &i.Title, &i.Description, &i.Severity, &i.Status, &i.DeviceID, &i.SensorID, &i.ZoneID, &i.AssetID, &i.RuleName, &dataJSON, &i.CreatedAt, &i.UpdatedAt, &resolvedAt); err != nil {
			return nil, err
		}

		if resolvedAt.Valid {
			i.ResolvedAt = &resolvedAt.Time
		}
		if dataJSON.Valid {
			json.Unmarshal([]byte(dataJSON.String), &i.Data)
		}

		incidents = append(incidents, i)
	}

	return incidents, nil
}

func (r *IncidentRepo) Upsert(ctx context.Context, incident *model.Incident) error {
	dataJSON, _ := json.Marshal(incident.Data)

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO incidents (id, title, description, severity, status, device_id, sensor_id, zone_id, asset_id, rule_name, data, created_at, updated_at, resolved_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		incident.ID, incident.Title, incident.Description, incident.Severity, incident.Status,
		incident.DeviceID, incident.SensorID, incident.ZoneID, incident.AssetID, incident.RuleName,
		string(dataJSON), incident.CreatedAt, incident.UpdatedAt, incident.ResolvedAt)
	return err
}

func (r *IncidentRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM incidents WHERE id = ?`, id)
	return err
}
