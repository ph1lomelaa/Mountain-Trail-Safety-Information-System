import sqlite3
from datetime import datetime, timezone
from app.services.audit import write_audit_log


def detect_overdue_hikers(db: sqlite3.Connection, triggered_by_user_id: int):
    now = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        """SELECT sc.*, u.username, u.emergency_contact
           FROM safety_checkins sc
           JOIN users u ON sc.user_id = u.id
           WHERE sc.status = 'active' AND sc.expected_return < ?""",
        (now,)
    ).fetchall()

    overdue = []
    for row in rows:
        r = dict(row)
        db.execute(
            "UPDATE safety_checkins SET status = 'overdue' WHERE id = ?",
            (r["id"],)
        )
        write_audit_log(
            db,
            user_id=triggered_by_user_id,
            action="OVERDUE_DETECTED",
            entity_type="safety_checkin",
            entity_id=r["id"],
            details=f"Hiker {r['username']} overdue. Emergency contact: {r.get('emergency_contact', 'N/A')}"
        )
        overdue.append(r)

    db.commit()
    return overdue
