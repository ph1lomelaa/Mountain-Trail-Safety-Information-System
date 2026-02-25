import json
import sqlite3
from typing import Iterable

import h3

ROUTE_H3_RESOLUTION = 9


def ensure_checkin_cells_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS safety_checkin_cells (
            checkin_id INTEGER NOT NULL REFERENCES safety_checkins(id) ON DELETE CASCADE,
            h3_index TEXT NOT NULL,
            h3_resolution INTEGER NOT NULL DEFAULT 9,
            PRIMARY KEY (checkin_id, h3_index)
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_safety_checkin_cells_h3 ON safety_checkin_cells(h3_index)"
    )


def geometry_points_from_trail_row(trail: dict) -> list[tuple[float, float]]:
    geometry_json = trail.get("geometry_json")
    if geometry_json:
        try:
            geometry = json.loads(geometry_json)
            coords = geometry.get("coordinates", [])
            if geometry.get("type") == "LineString":
                return [(float(lat), float(lng)) for lng, lat in coords]
        except Exception:
            pass

    if all(k in trail and trail[k] is not None for k in ("start_lat", "start_lng", "end_lat", "end_lng")):
        return [
            (float(trail["start_lat"]), float(trail["start_lng"])),
            (float(trail["end_lat"]), float(trail["end_lng"])),
        ]
    return []


def cells_from_points(points: list[tuple[float, float]], resolution: int) -> list[str]:
    if not points:
        return []

    point_cells = [h3.geo_to_h3(lat, lng, resolution) for lat, lng in points]
    result: list[str] = []

    for i, cell in enumerate(point_cells):
        if i == 0:
            result.append(cell)
            continue
        prev = point_cells[i - 1]
        if prev == cell:
            continue
        try:
            segment = list(h3.h3_line(prev, cell))
        except Exception:
            segment = [prev, cell]
        for seg_cell in segment:
            if not result or result[-1] != seg_cell:
                result.append(seg_cell)

    return result


def route_cells_from_trail(trail: dict, resolution: int = ROUTE_H3_RESOLUTION) -> list[str]:
    points = geometry_points_from_trail_row(trail)
    return cells_from_points(points, resolution)


def save_checkin_cells(
    db: sqlite3.Connection,
    checkin_id: int,
    h3_cells: Iterable[str],
    resolution: int = ROUTE_H3_RESOLUTION,
) -> None:
    ensure_checkin_cells_table(db)
    rows = [(checkin_id, cell, resolution) for cell in h3_cells]
    if not rows:
        return
    db.executemany(
        """
        INSERT OR IGNORE INTO safety_checkin_cells (checkin_id, h3_index, h3_resolution)
        VALUES (?, ?, ?)
        """,
        rows,
    )


def backfill_missing_checkin_cells(
    db: sqlite3.Connection,
    resolution: int = ROUTE_H3_RESOLUTION,
) -> int:
    """
    Fill safety_checkin_cells for existing check-ins that do not have route cells yet.
    Returns number of check-ins backfilled.
    """
    ensure_checkin_cells_table(db)

    rows = db.execute(
        """
        SELECT s.id, s.trail_id, s.latitude, s.longitude
        FROM safety_checkins s
        WHERE NOT EXISTS (
            SELECT 1 FROM safety_checkin_cells c WHERE c.checkin_id = s.id
        )
        """
    ).fetchall()

    if not rows:
        return 0

    trail_cache: dict[int, list[str]] = {}
    backfilled = 0

    for row in rows:
        trail_id = row["trail_id"]
        if trail_id not in trail_cache:
            trail_row = db.execute("SELECT * FROM trails WHERE id = ?", (trail_id,)).fetchone()
            trail_cache[trail_id] = route_cells_from_trail(dict(trail_row), resolution) if trail_row else []

        cells = list(trail_cache[trail_id])
        if not cells:
            lat = row["latitude"]
            lng = row["longitude"]
            if lat is not None and lng is not None:
                cells = [h3.geo_to_h3(float(lat), float(lng), resolution)]

        if cells:
            save_checkin_cells(db, row["id"], cells, resolution)
            backfilled += 1

    return backfilled
