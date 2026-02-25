"""
Create an initial user account in an empty database.

Usage:
    python scripts/bootstrap_user.py --username admin --password admin123 --role admin
"""

from __future__ import annotations

import argparse
import os
import sqlite3

from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap first user in empty mountain.db")
    parser.add_argument(
        "--db",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mountain.db"),
        help="Path to SQLite database",
    )
    parser.add_argument("--username", required=True, help="Login username")
    parser.add_argument("--password", required=True, help="Login password")
    parser.add_argument("--role", default="admin", choices=["hiker", "ranger", "admin"], help="User role")
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--email", default=None)
    parser.add_argument("--phone", default=None)
    parser.add_argument("--emergency-contact", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.db):
        raise FileNotFoundError(f"Database not found: {args.db}. Run `python init_db.py` first.")

    conn = sqlite3.connect(args.db)
    try:
        users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if users_count > 0:
            raise RuntimeError("Users already exist. Bootstrap is allowed only on empty users table.")

        password_hash = pwd_context.hash(args.password)
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, email, phone, emergency_contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.username,
                password_hash,
                args.role,
                args.full_name,
                args.email,
                args.phone,
                args.emergency_contact,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"User created: {args.username} ({args.role})")


if __name__ == "__main__":
    main()
