import sqlite3

import h3
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_permission
from app.database import get_db
from app.schemas.schemas import EventCreate, EventOut

router = APIRouter(prefix="/events", tags=["Events"])

H3_RESOLUTION = 7


@router.get("/", response_model=list[EventOut])
def list_events(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("events:read")),
):
    rows = db.execute("SELECT * FROM events ORDER BY event_date").fetchall()
    return [dict(r) for r in rows]


@router.post("/", response_model=EventOut)
def create_event(
    body: EventCreate,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("events:write")),
):
    if body.trail_id:
        trail = db.execute("SELECT id FROM trails WHERE id = ?", (body.trail_id,)).fetchone()
        if not trail:
            raise HTTPException(status_code=404, detail="Trail not found")

    h3_index = h3.geo_to_h3(body.location_lat, body.location_lng, H3_RESOLUTION)
    cur = db.execute(
        """INSERT INTO events (title, description, event_date, location_lat, location_lng,
           h3_index, trail_id, max_participants)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.title, body.description, body.event_date, body.location_lat,
         body.location_lng, h3_index, body.trail_id, body.max_participants),
    )
    db.commit()
    row = db.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)
