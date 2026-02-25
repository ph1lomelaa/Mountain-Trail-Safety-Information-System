"""
Database initialization script.
Creates empty schema for the Mountain Trail & Safety IS (no hardcoded domain seed data).
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mountain.db")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('hiker', 'ranger', 'admin')),
    full_name TEXT,
    email TEXT,
    phone TEXT,
    emergency_contact TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE trails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'moderate', 'hard', 'extreme')),
    length_km REAL NOT NULL,
    elevation_gain_m REAL NOT NULL,
    start_lat REAL NOT NULL,
    start_lng REAL NOT NULL,
    end_lat REAL NOT NULL,
    end_lng REAL NOT NULL,
    h3_index TEXT NOT NULL,
    h3_resolution INTEGER DEFAULT 7,
    geometry_json TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE pois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('cafe', 'restaurant', 'shelter', 'viewpoint', 'water_source', 'campsite')),
    description TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    h3_index TEXT NOT NULL,
    trail_id INTEGER REFERENCES trails(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE safety_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    trail_id INTEGER NOT NULL REFERENCES trails(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'returned', 'overdue', 'rescued')),
    expected_return TEXT NOT NULL,
    emergency_contact TEXT,
    phone_number TEXT,
    group_size INTEGER DEFAULT 1,
    notes TEXT,
    h3_index TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    checked_in_at TEXT NOT NULL,
    checked_out_at TEXT
);

CREATE TABLE safety_checkin_cells (
    checkin_id INTEGER NOT NULL REFERENCES safety_checkins(id) ON DELETE CASCADE,
    h3_index TEXT NOT NULL,
    h3_resolution INTEGER NOT NULL DEFAULT 9,
    PRIMARY KEY (checkin_id, h3_index)
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    event_date TEXT NOT NULL,
    location_lat REAL NOT NULL,
    location_lng REAL NOT NULL,
    h3_index TEXT NOT NULL,
    trail_id INTEGER REFERENCES trails(id) ON DELETE SET NULL,
    max_participants INTEGER,
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE h3_analytics (
    h3_index TEXT PRIMARY KEY,
    resolution INTEGER NOT NULL,
    total_trails INTEGER DEFAULT 0,
    total_pois INTEGER DEFAULT 0,
    total_checkins INTEGER DEFAULT 0,
    total_events INTEGER DEFAULT 0,
    last_updated TEXT
);

CREATE INDEX idx_trails_h3 ON trails(h3_index);
CREATE INDEX idx_pois_h3 ON pois(h3_index);
CREATE INDEX idx_checkins_h3 ON safety_checkins(h3_index);
CREATE INDEX idx_checkin_cells_h3 ON safety_checkin_cells(h3_index);
CREATE INDEX idx_events_h3 ON events(h3_index);
CREATE INDEX idx_checkins_status ON safety_checkins(status);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE UNIQUE INDEX idx_trails_source ON trails(source, source_id) WHERE source_id IS NOT NULL;
CREATE UNIQUE INDEX idx_pois_source ON pois(source, source_id) WHERE source_id IS NOT NULL;
CREATE UNIQUE INDEX idx_events_source ON events(source, source_id) WHERE source_id IS NOT NULL;
"""


def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()

    print(f"✅ Empty database created at: {DB_PATH}")
    print("ℹ️ No hardcoded domain data inserted.")
    print("   Next: import live Almaty data with `python scripts/import_almaty_osm.py`.")


if __name__ == "__main__":
    main()
