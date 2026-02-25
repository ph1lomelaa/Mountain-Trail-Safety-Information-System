import sqlite3

from fastapi import APIRouter, Depends

from app.auth import require_permission
from app.database import get_db
from app.schemas.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = 100,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("audit:read")),
):
    rows = db.execute(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
