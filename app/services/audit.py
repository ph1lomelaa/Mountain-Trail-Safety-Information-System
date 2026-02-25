import sqlite3
from datetime import datetime, timezone


def write_audit_log(db: sqlite3.Connection, user_id: int, action: str, entity_type: str,
                    entity_id: int = None, details: str = None):
    db.execute(
        """INSERT INTO audit_log (user_id, action, entity_type, entity_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, action, entity_type, entity_id, details,
         datetime.now(timezone.utc).isoformat())
    )
    db.commit()
