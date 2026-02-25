import json
import sqlite3

import h3
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.database import get_db
from app.schemas.schemas import TrailOut

router = APIRouter(prefix="/trails", tags=["Trails"])


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


@router.get("/", response_model=list[TrailOut])
def list_trails(
    difficulty: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("trails:read")),
):
    if difficulty:
        rows = db.execute("SELECT * FROM trails WHERE difficulty = ?", (difficulty,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM trails").fetchall()
    return [dict(r) for r in rows]


@router.get("/{trail_id}/h3-cells")
def get_trail_h3_cells(
    trail_id: int,
    resolution: int = 9,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("trails:read")),
):
    if resolution < 0 or resolution > 15:
        raise HTTPException(status_code=400, detail="Resolution must be between 0 and 15")

    row = db.execute("SELECT * FROM trails WHERE id = ?", (trail_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Trail not found")
    trail = dict(row)

    points = geometry_points_from_trail_row(trail)
    if len(points) < 2:
        raise HTTPException(status_code=404, detail="Trail geometry not available")

    cells = cells_from_points(points, resolution)
    return {
        "trail_id": trail["id"],
        "trail_name": trail["name"],
        "resolution": resolution,
        "cells": [
            {
                "h3_index": cell,
                "boundary": h3.h3_to_geo_boundary(cell, geo_json=True),
            }
            for cell in cells
        ],
    }
