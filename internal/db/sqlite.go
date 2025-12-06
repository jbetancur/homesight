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

		CREATE TABLE IF NOT EXISTS home_profiles (
			id TEXT PRIMARY KEY,
			home_id TEXT NOT NULL UNIQUE,
			year_built INTEGER,
			square_feet INTEGER,
			stories INTEGER,
			foundation_type TEXT,
			roof_type TEXT,
			roof_age INTEGER,
			siding_type TEXT,
			window_type TEXT,
			insulation TEXT,
			hvac_type TEXT,
			hvac_age INTEGER,
			has_ac BOOLEAN,
			ac_type TEXT,
			heating_type TEXT,
			thermostat_type TEXT,
			has_humidifier BOOLEAN,
			has_dehumidifier BOOLEAN,
			has_air_purifier BOOLEAN,
			water_heater_type TEXT,
			water_heater_age INTEGER,
			water_heater_fuel TEXT,
			has_well_water BOOLEAN,
			has_sewer_system BOOLEAN,
			has_septic_system BOOLEAN,
			has_sump_pump BOOLEAN,
			electrical_panel TEXT,
			has_generator_backup BOOLEAN,
			has_solar_panels BOOLEAN,
			has_battery_backup BOOLEAN,
			has_security_system BOOLEAN,
			has_fire_alarms BOOLEAN,
			has_co_alarms BOOLEAN,
			has_sprinklers BOOLEAN,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (home_id) REFERENCES homes(id)
		);

		CREATE TABLE IF NOT EXISTS attribute_definitions (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL UNIQUE,
			label TEXT NOT NULL,
			type TEXT NOT NULL,
			scope TEXT NOT NULL,
			category TEXT,
			description TEXT,
			options TEXT,
			default_value TEXT,
			required BOOLEAN DEFAULT 0,
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL
		);

		CREATE TABLE IF NOT EXISTS zone_attribute_values (
			zone_id TEXT NOT NULL,
			attribute_id TEXT NOT NULL,
			value TEXT,
			PRIMARY KEY (zone_id, attribute_id),
			FOREIGN KEY (zone_id) REFERENCES zones(id),
			FOREIGN KEY (attribute_id) REFERENCES attribute_definitions(id)
		);

		CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
		CREATE INDEX IF NOT EXISTS idx_incidents_device ON incidents(device_id);
		CREATE INDEX IF NOT EXISTS idx_devices_zone ON devices(zone_id);
		CREATE INDEX IF NOT EXISTS idx_sensors_device ON sensors(device_id);
		CREATE INDEX IF NOT EXISTS idx_kb_device ON knowledge_base(device_id);
		CREATE INDEX IF NOT EXISTS idx_kb_model ON knowledge_base(manufacturer, model);
		CREATE INDEX IF NOT EXISTS idx_zones_type ON zones(type);
		CREATE INDEX IF NOT EXISTS idx_home_profiles_home ON home_profiles(home_id);
		CREATE INDEX IF NOT EXISTS idx_attribute_defs_scope ON attribute_definitions(scope);
		CREATE INDEX IF NOT EXISTS idx_zone_attrs_zone ON zone_attribute_values(zone_id);
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

// HomeProfileRepo implements HomeProfileRepository
type HomeProfileRepo struct {
	db *sql.DB
}

// NewHomeProfileRepo creates a new home profile repository
func NewHomeProfileRepo(db *SQLiteDB) *HomeProfileRepo {
	return &HomeProfileRepo{db: db.db}
}

func (r *HomeProfileRepo) Get(ctx context.Context, homeID string) (*model.HomeProfile, error) {
	row := r.db.QueryRowContext(ctx,
		`SELECT id, home_id, year_built, square_feet, stories, foundation_type, roof_type, roof_age,
				siding_type, window_type, insulation, hvac_type, hvac_age, has_ac, ac_type, heating_type,
				thermostat_type, has_humidifier, has_dehumidifier, has_air_purifier,
				water_heater_type, water_heater_age, water_heater_fuel,
				has_well_water, has_sewer_system, has_septic_system, has_sump_pump,
				electrical_panel, has_generator_backup, has_solar_panels, has_battery_backup,
				has_security_system, has_fire_alarms, has_co_alarms, has_sprinklers,
				created_at, updated_at
		 FROM home_profiles WHERE home_id = ?`, homeID)

	var p model.HomeProfile
	err := row.Scan(&p.ID, &p.HomeID, &p.YearBuilt, &p.SquareFeet, &p.Stories,
		&p.FoundationType, &p.RoofType, &p.RoofAge, &p.SidingType, &p.WindowType, &p.Insulation,
		&p.HVACType, &p.HVACAge, &p.HasAC, &p.ACType, &p.HeatingType, &p.ThermostatType,
		&p.HasHumidifier, &p.HasDehumidifier, &p.HasAirPurifier,
		&p.WaterHeaterType, &p.WaterHeaterAge, &p.WaterHeaterFuel,
		&p.HasWellWater, &p.HasSewerSystem, &p.HasSepticSystem, &p.HasSumpPump,
		&p.ElectricalPanel, &p.HasGeneratorBackup, &p.HasSolarPanels, &p.HasBatteryBackup,
		&p.HasSecuritySystem, &p.HasFireAlarms, &p.HasCOAlarms, &p.HasSprinklers,
		&p.CreatedAt, &p.UpdatedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (r *HomeProfileRepo) Upsert(ctx context.Context, profile *model.HomeProfile) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO home_profiles 
		 (id, home_id, year_built, square_feet, stories, foundation_type, roof_type, roof_age,
		  siding_type, window_type, insulation, hvac_type, hvac_age, has_ac, ac_type, heating_type,
		  thermostat_type, has_humidifier, has_dehumidifier, has_air_purifier,
		  water_heater_type, water_heater_age, water_heater_fuel,
		  has_well_water, has_sewer_system, has_septic_system, has_sump_pump,
		  electrical_panel, has_generator_backup, has_solar_panels, has_battery_backup,
		  has_security_system, has_fire_alarms, has_co_alarms, has_sprinklers,
		  created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		profile.ID, profile.HomeID, profile.YearBuilt, profile.SquareFeet, profile.Stories,
		profile.FoundationType, profile.RoofType, profile.RoofAge, profile.SidingType, profile.WindowType, profile.Insulation,
		profile.HVACType, profile.HVACAge, profile.HasAC, profile.ACType, profile.HeatingType, profile.ThermostatType,
		profile.HasHumidifier, profile.HasDehumidifier, profile.HasAirPurifier,
		profile.WaterHeaterType, profile.WaterHeaterAge, profile.WaterHeaterFuel,
		profile.HasWellWater, profile.HasSewerSystem, profile.HasSepticSystem, profile.HasSumpPump,
		profile.ElectricalPanel, profile.HasGeneratorBackup, profile.HasSolarPanels, profile.HasBatteryBackup,
		profile.HasSecuritySystem, profile.HasFireAlarms, profile.HasCOAlarms, profile.HasSprinklers,
		profile.CreatedAt, profile.UpdatedAt)
	return err
}

func (r *HomeProfileRepo) Delete(ctx context.Context, homeID string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM home_profiles WHERE home_id = ?`, homeID)
	return err
}

// AttributeDefinitionRepo implements AttributeDefinitionRepository
type AttributeDefinitionRepo struct {
	db *sql.DB
}

// NewAttributeDefinitionRepo creates a new attribute definition repository
func NewAttributeDefinitionRepo(db *SQLiteDB) *AttributeDefinitionRepo {
	return &AttributeDefinitionRepo{db: db.db}
}

func (r *AttributeDefinitionRepo) Get(ctx context.Context, id string) (*model.AttributeDefinition, error) {
	row := r.db.QueryRowContext(ctx,
		`SELECT id, name, label, type, scope, category, description, options, default_value, required, created_at, updated_at
		 FROM attribute_definitions WHERE id = ?`, id)

	var def model.AttributeDefinition
	var optionsJSON sql.NullString

	err := row.Scan(&def.ID, &def.Name, &def.Label, &def.Type, &def.Scope, &def.Category,
		&def.Description, &optionsJSON, &def.DefaultValue, &def.Required, &def.CreatedAt, &def.UpdatedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	if optionsJSON.Valid {
		json.Unmarshal([]byte(optionsJSON.String), &def.Options)
	}

	return &def, nil
}

func (r *AttributeDefinitionRepo) List(ctx context.Context, scope model.AttributeScope) ([]model.AttributeDefinition, error) {
	query := `SELECT id, name, label, type, scope, category, description, options, default_value, required, created_at, updated_at
			  FROM attribute_definitions`
	var rows *sql.Rows
	var err error

	if scope != "" {
		query += ` WHERE scope = ?`
		rows, err = r.db.QueryContext(ctx, query, scope)
	} else {
		rows, err = r.db.QueryContext(ctx, query)
	}

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var defs []model.AttributeDefinition
	for rows.Next() {
		var def model.AttributeDefinition
		var optionsJSON sql.NullString

		if err := rows.Scan(&def.ID, &def.Name, &def.Label, &def.Type, &def.Scope, &def.Category,
			&def.Description, &optionsJSON, &def.DefaultValue, &def.Required, &def.CreatedAt, &def.UpdatedAt); err != nil {
			return nil, err
		}

		if optionsJSON.Valid {
			json.Unmarshal([]byte(optionsJSON.String), &def.Options)
		}

		defs = append(defs, def)
	}

	return defs, nil
}

func (r *AttributeDefinitionRepo) Upsert(ctx context.Context, def *model.AttributeDefinition) error {
	optionsJSON, _ := json.Marshal(def.Options)

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO attribute_definitions 
		 (id, name, label, type, scope, category, description, options, default_value, required, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		def.ID, def.Name, def.Label, def.Type, def.Scope, def.Category,
		def.Description, string(optionsJSON), def.DefaultValue, def.Required, def.CreatedAt, def.UpdatedAt)
	return err
}

func (r *AttributeDefinitionRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM attribute_definitions WHERE id = ?`, id)
	return err
}

// ZoneAttributeValueRepo implements ZoneAttributeValueRepository
type ZoneAttributeValueRepo struct {
	db *sql.DB
}

// NewZoneAttributeValueRepo creates a new zone attribute value repository
func NewZoneAttributeValueRepo(db *SQLiteDB) *ZoneAttributeValueRepo {
	return &ZoneAttributeValueRepo{db: db.db}
}

func (r *ZoneAttributeValueRepo) Get(ctx context.Context, zoneID, attributeID string) (string, error) {
	row := r.db.QueryRowContext(ctx,
		`SELECT value FROM zone_attribute_values WHERE zone_id = ? AND attribute_id = ?`,
		zoneID, attributeID)

	var value string
	err := row.Scan(&value)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return value, nil
}

func (r *ZoneAttributeValueRepo) ListByZone(ctx context.Context, zoneID string) (map[string]string, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT attribute_id, value FROM zone_attribute_values WHERE zone_id = ?`, zoneID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	values := make(map[string]string)
	for rows.Next() {
		var attributeID, value string
		if err := rows.Scan(&attributeID, &value); err != nil {
			return nil, err
		}
		values[attributeID] = value
	}

	return values, nil
}

func (r *ZoneAttributeValueRepo) Set(ctx context.Context, zoneID, attributeID, value string) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO zone_attribute_values (zone_id, attribute_id, value)
		 VALUES (?, ?, ?)`,
		zoneID, attributeID, value)
	return err
}

func (r *ZoneAttributeValueRepo) Delete(ctx context.Context, zoneID, attributeID string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM zone_attribute_values WHERE zone_id = ? AND attribute_id = ?`, zoneID, attributeID)
	return err
}
