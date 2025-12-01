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
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, created_at, updated_at
		 FROM zones WHERE id = ?`, id).Scan(
		&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.CreatedAt, &z.UpdatedAt)

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
		var attrs model.ZoneAttributes
		if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
			z.Attributes = &attrs
		}
	}

	return &z, nil
}

func (r *ZoneRepo) List(ctx context.Context) ([]model.Zone, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, created_at, updated_at
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

		if err := rows.Scan(&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.CreatedAt, &z.UpdatedAt); err != nil {
			return nil, err
		}

		if metadataJSON.Valid && metadataJSON.String != "" {
			json.Unmarshal([]byte(metadataJSON.String), &z.Metadata)
		}
		if attributesJSON.Valid && attributesJSON.String != "" {
			var attrs model.ZoneAttributes
			if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
				z.Attributes = &attrs
			}
		}

		zones = append(zones, z)
	}

	return zones, nil
}

func (r *ZoneRepo) ListByHome(ctx context.Context, homeID string) ([]model.Zone, error) {
	rows, err := r.db.QueryContext(ctx,
		`SELECT id, home_id, name, type, parent_id, attributes, metadata, created_at, updated_at
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

		if err := rows.Scan(&z.ID, &z.HomeID, &z.Name, &z.Type, &z.ParentID, &attributesJSON, &metadataJSON, &z.CreatedAt, &z.UpdatedAt); err != nil {
			return nil, err
		}

		if metadataJSON.Valid && metadataJSON.String != "" {
			json.Unmarshal([]byte(metadataJSON.String), &z.Metadata)
		}
		if attributesJSON.Valid && attributesJSON.String != "" {
			var attrs model.ZoneAttributes
			if err := json.Unmarshal([]byte(attributesJSON.String), &attrs); err == nil {
				z.Attributes = &attrs
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
		`INSERT OR REPLACE INTO zones (id, home_id, name, type, parent_id, attributes, metadata, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		zone.ID, zone.HomeID, zone.Name, zone.Type, zone.ParentID, string(attributesJSON), string(metadataJSON), zone.CreatedAt, zone.UpdatedAt)
	return err
}

func (r *ZoneRepo) Delete(ctx context.Context, id string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM zones WHERE id = ?`, id)
	return err
}

// SeedDefaultZones creates default zones if none exist
func (r *ZoneRepo) SeedDefaultZones(ctx context.Context) error {
	// Check if zones already exist
	zones, err := r.List(ctx)
	if err != nil {
		return err
	}
	if len(zones) > 0 {
		return nil // Already seeded
	}

	now := time.Now()
	defaultZones := []model.Zone{
		{
			ID:     "living-room",
			Name:   "Living Room",
			Type:   "living_room",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType:       "hardwood",
				HasWindows:      true,
				HasHVACVent:     true,
				IsOccupiedDaily: true,
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			ID:     "kitchen",
			Name:   "Kitchen",
			Type:   "kitchen",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType:       "tile",
				HasWindows:      true,
				HasPlumbing:     true,
				HasHVACVent:     true,
				IsOccupiedDaily: true,
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			ID:     "bedroom",
			Name:   "Bedroom",
			Type:   "bedroom",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType:       "carpet",
				HasWindows:      true,
				HasHVACVent:     true,
				IsOccupiedDaily: true,
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			ID:     "bathroom",
			Name:   "Bathroom",
			Type:   "bathroom",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType:   "tile",
				HasPlumbing: true,
				HasHVACVent: true,
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			ID:     "basement",
			Name:   "Basement",
			Type:   "basement",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType:     "concrete",
				HasSumpPump:   true,
				HasHVACReturn: true,
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			ID:     "garage",
			Name:   "Garage",
			Type:   "garage",
			HomeID: "default",
			Attributes: &model.ZoneAttributes{
				FloorType: "concrete",
			},
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	for _, zone := range defaultZones {
		if err := r.Upsert(ctx, &zone); err != nil {
			return err
		}
	}

	return nil
}
