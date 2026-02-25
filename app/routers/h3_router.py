import sqlite3

import h3
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.database import get_db
from app.services.checkin_cells import ensure_checkin_cells_table

router = APIRouter(prefix="/h3", tags=["H3 Spatial"])


def project_cell_to_resolution(h3_index: str, resolution: int) -> str:
    source_resolution = h3.h3_get_resolution(h3_index)
    if source_resolution == resolution:
        return h3_index
    if source_resolution > resolution:
        return h3.h3_to_parent(h3_index, resolution)
    return h3_index


def collect_checkin_counts_by_cell(db: sqlite3.Connection) -> dict[str, int]:
    ensure_checkin_cells_table(db)
    statuses = ("active", "overdue")
    status_ph = ",".join("?" for _ in statuses)

    cell_rows = db.execute(
        f"""
        SELECT c.h3_index, COUNT(DISTINCT c.checkin_id) as cnt
        FROM safety_checkin_cells c
        JOIN safety_checkins s ON s.id = c.checkin_id
        WHERE s.status IN ({status_ph})
        GROUP BY c.h3_index
        """,
        statuses,
    ).fetchall()

    counts: dict[str, int] = {row["h3_index"]: row["cnt"] for row in cell_rows}

    fallback_rows = db.execute(
        f"""
        SELECT s.h3_index, COUNT(*) as cnt
        FROM safety_checkins s
        WHERE s.status IN ({status_ph})
          AND NOT EXISTS (
              SELECT 1 FROM safety_checkin_cells c WHERE c.checkin_id = s.id
          )
        GROUP BY s.h3_index
        """,
        statuses,
    ).fetchall()

    for row in fallback_rows:
        counts[row["h3_index"]] = counts.get(row["h3_index"], 0) + row["cnt"]

    return counts


def h3_region_stats(resolution: int, db: sqlite3.Connection) -> list[dict]:
    trail_rows = db.execute("SELECT h3_index, COUNT(*) as cnt FROM trails GROUP BY h3_index").fetchall()
    poi_rows = db.execute("SELECT h3_index, COUNT(*) as cnt FROM pois GROUP BY h3_index").fetchall()
    checkin_counts = collect_checkin_counts_by_cell(db)

    cells: dict[str, dict] = {}
    for row in trail_rows:
        parent = project_cell_to_resolution(row["h3_index"], resolution)
        cells.setdefault(parent, {"h3_index": parent, "trails": 0, "pois": 0, "active_checkins": 0})
        cells[parent]["trails"] += row["cnt"]

    for row in poi_rows:
        parent = project_cell_to_resolution(row["h3_index"], resolution)
        cells.setdefault(parent, {"h3_index": parent, "trails": 0, "pois": 0, "active_checkins": 0})
        cells[parent]["pois"] += row["cnt"]

    for cell, cnt in checkin_counts.items():
        parent = project_cell_to_resolution(cell, resolution)
        cells.setdefault(parent, {"h3_index": parent, "trails": 0, "pois": 0, "active_checkins": 0})
        cells[parent]["active_checkins"] += cnt

    return list(cells.values())


@router.get("/region/{resolution}/boundaries")
def h3_region_boundaries(
    resolution: int,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("h3:read")),
):
    if resolution < 0 or resolution > 15:
        raise HTTPException(status_code=400, detail="Resolution must be between 0 and 15")

    region_rows = h3_region_stats(resolution=resolution, db=db)
    response = []
    for row in region_rows:
        response.append(
            {
                **row,
                "boundary": h3.h3_to_geo_boundary(row["h3_index"], geo_json=True),
            }
        )
    return response
