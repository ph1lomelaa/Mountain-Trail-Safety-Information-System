import sqlite3

from fastapi import APIRouter, Depends

from app.auth import require_permission
from app.database import get_db
from app.schemas.schemas import POIOut

router = APIRouter(prefix="/pois", tags=["Points of Interest"])


@router.get("/", response_model=list[POIOut])
def list_pois(
    category: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
    user=Depends(require_permission("pois:read")),
):
    if category:
        rows = db.execute("SELECT * FROM pois WHERE category = ?", (category,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM pois").fetchall()
    return [dict(r) for r in rows]
