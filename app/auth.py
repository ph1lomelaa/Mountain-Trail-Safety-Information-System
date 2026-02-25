import sqlite3

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext

from app.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PERMISSIONS = {
    "hiker": [
        "trails:read",
        "pois:read",
        "safety:checkin",
        "safety:checkout_self",
        "h3:read",
        "events:read",
    ],
    "ranger": [
        "trails:read",
        "pois:read",
        "safety:checkin",
        "safety:checkout_self",
        "safety:view_active",
        "safety:checkout_any",
        "safety:trigger_overdue",
        "h3:read",
        "events:read",
    ],
    "admin": [
        "trails:read",
        "pois:read",
        "safety:checkin",
        "safety:checkout_self",
        "safety:view_active",
        "safety:checkout_any",
        "safety:trigger_overdue",
        "h3:read",
        "events:read",
        "events:write",
        "audit:read",
    ],
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _resolve_demo_user(db: sqlite3.Connection, requested_role: str) -> dict:
    role = requested_role if requested_role in PERMISSIONS else "admin"
    row = db.execute("SELECT * FROM users WHERE role = ? ORDER BY id LIMIT 1", (role,)).fetchone()
    if row is not None:
        return dict(row)
    return {
        "id": -1,
        "username": f"demo_{role}",
        "role": role,
        "full_name": f"Demo {role.title()}",
        "email": f"{role}@demo.local",
        "phone": None,
        "emergency_contact": None,
        "password_hash": None,
    }


def get_current_user(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    requested_role = request.headers.get("X-Demo-Role", "admin").strip().lower()
    return _resolve_demo_user(db, requested_role)


def require_permission(permission: str):
    def checker(user=Depends(get_current_user)):
        role = user.get("role", "")
        if permission not in PERMISSIONS.get(role, []):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user

    return checker


def abac_checkout(user: dict, checkin_row: dict):
    if user["role"] in ("ranger", "admin"):
        return True
    if user["role"] == "hiker" and checkin_row["user_id"] == user["id"]:
        return True
    raise HTTPException(status_code=403, detail="ABAC: You can only checkout your own check-in")
