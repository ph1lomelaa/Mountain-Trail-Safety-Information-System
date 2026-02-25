from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from app.routers import (
    auth_router,
    trails_router,
    pois_router,
    safety_router,
    h3_router,
    audit_router,
    events_router,
)
from app.services.demo_seed import ensure_demo_users
from app.services.checkin_cells import backfill_missing_checkin_cells
from app.database import DB_PATH

app = FastAPI(
    title="🏔️ Mountain Trail & Safety Information System",
    description=(
        "Mountain routes, POI data and safety check-ins with H3 map overlays."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(trails_router.router)
app.include_router(pois_router.router)
app.include_router(safety_router.router)
app.include_router(h3_router.router)
app.include_router(audit_router.router)
app.include_router(events_router.router)


@app.on_event("startup")
def seed_demo_accounts():
    ensure_demo_users()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        backfill_missing_checkin_cells(conn)
        conn.commit()
    finally:
        conn.close()


@app.get("/", tags=["Root"])
def root():
    return {
        "system": "Mountain Trail & Safety Information System (MTSIS)",
        "version": "1.0.0",
        "docs": "/docs",
        "h3_info": "Route occupancy is aggregated on H3 boundaries, default map resolution is 9.",
    }
