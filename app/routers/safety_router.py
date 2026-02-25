from fastapi import APIRouter, Depends, HTTPException
import sqlite3
import h3
from datetime import datetime, timezone
from app.database import get_db
from app.auth import require_permission, get_current_user, abac_checkout
from app.schemas.schemas import SafetyCheckinCreate, SafetyCheckinOut
from app.services.audit import write_audit_log
from app.services.checkin_cells import (
    ROUTE_H3_RESOLUTION,
    route_cells_from_trail,
    save_checkin_cells,
)
from app.services.events import detect_overdue_hikers

router = APIRouter(prefix="/safety", tags=["Safety Check-ins"])

H3_RESOLUTION = 7


@router.post("/checkin", response_model=SafetyCheckinOut)
def create_checkin(
    body: SafetyCheckinCreate,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("safety:checkin")),
):
    h3_index = h3.geo_to_h3(body.latitude, body.longitude, H3_RESOLUTION)
    route_h3_start = h3.geo_to_h3(body.latitude, body.longitude, ROUTE_H3_RESOLUTION)

    trail_row = db.execute("SELECT * FROM trails WHERE id = ?", (body.trail_id,)).fetchone()
    trail_cells = route_cells_from_trail(dict(trail_row)) if trail_row else []
    if not trail_cells:
        trail_cells = [route_h3_start]

    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO safety_checkins
           (user_id, trail_id, status, expected_return, emergency_contact, phone_number,
            group_size, notes, h3_index, latitude, longitude, checked_in_at)
           VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user["id"], body.trail_id, body.expected_return, body.emergency_contact or user.get("emergency_contact"),
         body.phone_number or user.get("phone"), body.group_size, body.notes,
         h3_index, body.latitude, body.longitude, now),
    )

    save_checkin_cells(db, cur.lastrowid, trail_cells, ROUTE_H3_RESOLUTION)
    db.commit()
    write_audit_log(db, user["id"], "SAFETY_CHECKIN", "safety_checkin", cur.lastrowid,
                    f"Trail {body.trail_id}, expected return: {body.expected_return}")
    row = db.execute("SELECT * FROM safety_checkins WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/active", response_model=list[SafetyCheckinOut])
def get_active_checkins(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("safety:view_active")),
):
    rows = db.execute(
        "SELECT * FROM safety_checkins WHERE status IN ('active', 'overdue') ORDER BY expected_return"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/mine", response_model=list[SafetyCheckinOut])
def get_my_checkins(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("safety:checkin")),
):
    rows = db.execute(
        """SELECT * FROM safety_checkins
           WHERE user_id = ? AND status IN ('active', 'overdue')
           ORDER BY checked_in_at DESC""",
        (user["id"],),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/checkout/{checkin_id}")
def checkout(
    checkin_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(get_current_user),
):
    row = db.execute("SELECT * FROM safety_checkins WHERE id = ?", (checkin_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Check-in not found")
    checkin = dict(row)
    abac_checkout(user, checkin)

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE safety_checkins SET status = 'returned', checked_out_at = ? WHERE id = ?",
        (now, checkin_id),
    )
    db.commit()
    write_audit_log(db, user["id"], "SAFETY_CHECKOUT", "safety_checkin", checkin_id,
                    f"Hiker returned safely")
    return {"detail": "Checked out successfully", "checked_out_at": now}


@router.post("/trigger-overdue")
def trigger_overdue(
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("safety:trigger_overdue")),
):
    overdue = detect_overdue_hikers(db, user["id"])
    return {
        "detail": f"Found {len(overdue)} overdue hiker(s)",
        "overdue_checkins": [
            {
                "id": r["id"],
                "username": r["username"],
                "emergency_contact": r.get("emergency_contact"),
                "expected_return": r["expected_return"],
                "trail_id": r["trail_id"],
                "h3_index": r["h3_index"],
            }
            for r in overdue
        ],
    }
