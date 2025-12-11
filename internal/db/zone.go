package db

import (
	"context"
	"database/sql"
	"encoding/json"
	"time"

	"github.com/homesight/homesight/internal/model"
)

// ZoneRepo implements zone repository
type ZoneRepo struct {
	db *sql.DB
}

// NewZoneRepo creates a new zone repository
func NewZoneRepo(db *SQLiteDB) *ZoneRepo {
	return &ZoneRepo{db: db.db}
}

func (r *ZoneRepo) Get(ctx context.Context, id string) (*model.Zone, error) {
	var z model.Zone
	var metadataJSON sql.NullString
	var attributesJSON sql.NullString

	err := r.db.QueryRowContext(ctx,
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, hidden, created_at, updated_at
		 FROM zones WHERE id = ?`, id).Scan(
		&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.Hidden, &z.CreatedAt, &z.UpdatedAt)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	if metadataJSON.Valid && metadataJSON.String != "" {
		json.Unmarshal([]byte(metadataJSON.String), &z.Metadata)
	}
	if attributesJSON.Valid && attributesJSON.String != "" {
		var attrs map[string]interface{}
		if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
			z.Attributes = attrs
		}
	}

	return &z, nil
}

func (r *ZoneRepo) List(ctx context.Context) ([]model.Zone, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, hidden, created_at, updated_at
		 FROM zones ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	zones := make([]model.Zone, 0)
	for rows.Next() {
		var z model.Zone
		var metadataJSON sql.NullString
		var attributesJSON sql.NullString

		if err := rows.Scan(&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.Hidden, &z.CreatedAt, &z.UpdatedAt); err != nil {
			return nil, err
		}

		if metadataJSON.Valid && metadataJSON.String != "" {
			json.Unmarshal([]byte(metadataJSON.String), &z.Metadata)
		}
		if attributesJSON.Valid && attributesJSON.String != "" {
			var attrs map[string]interface{}
			if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
				z.Attributes = attrs
			}
		}

		zones = append(zones, z)
	}

	return zones, nil
}

func (r *ZoneRepo) ListByHome(ctx context.Context, homeID string) ([]model.Zone, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, hidden, created_at, updated_at
		 FROM zones WHERE home_id = ? ORDER BY name`, homeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	zones := make([]model.Zone, 0)
	for rows.Next() {
		var z model.Zone
		var metadataJSON sql.NullString
		var attributesJSON sql.NullString

		if err := rows.Scan(&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.Hidden, &z.CreatedAt, &z.UpdatedAt); err != nil {
			return nil, err
		}

		if metadataJSON.Valid && metadataJSON.String != "" {
			json.Unmarshal([]byte(metadataJSON.String), &z.Metadata)
		}
		if attributesJSON.Valid && attributesJSON.String != "" {
			var attrs map[string]interface{}
			if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
				z.Attributes = attrs
			}
		}

		zones = append(zones, z)
	}

	return zones, nil
}

func (r *ZoneRepo) Upsert(ctx context.Context, zone *model.Zone) error {
	metadataJSON, _ := json.Marshal(zone.Metadata)
	attributesJSON, _ := json.Marshal(zone.Attributes)
	zone.UpdatedAt = time.Now()
	if zone.CreatedAt.IsZero() {
		zone.CreatedAt = zone.UpdatedAt
	}

	_, err := r.db.ExecContext(ctx,
		`INSERT OR REPLACE INTO zones (id, home_id, name, type, parent_id, attributes, metadata, hidden, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		zone.ID, zone.HomeID, zone.Name, zone.Type, zone.ParentID, string(attributesJSON), string(metadataJSON), zone.Hidden, zone.CreatedAt, zone.UpdatedAt)
	return err
}

func (r *ZoneRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM zones WHERE id = ?`, id)
	return err
}
