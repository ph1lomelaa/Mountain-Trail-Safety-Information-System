import sqlite3

from app.auth import hash_password
from app.database import DB_PATH

DEMO_USERS = [
    ("admin", "admin123", "admin", "System Admin", "admin@mtsis.local"),
    ("ranger", "ranger123", "ranger", "Demo Ranger", "ranger@mtsis.local"),
    ("hiker", "hiker123", "hiker", "Demo Hiker", "hiker@mtsis.local"),
    ("hiker_arman", "hiker123", "hiker", "Arman Talgat", "arman@mail.kz"),
    ("ranger_aibek", "ranger123", "ranger", "Aibek Nurlan", "aibek@mtsis.local"),
]


def ensure_demo_users() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for username, password, role, full_name, email in DEMO_USERS:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, full_name, email)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    full_name = excluded.full_name,
                    email = excluded.email
                """,
                (username, hash_password(password), role, full_name, email),
            )
        conn.commit()
    finally:
        conn.close()