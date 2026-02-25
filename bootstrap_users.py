"""
Bootstrap script to add test users to the database.
"""
import sqlite3
import os
from passlib.context import CryptContext

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mountain.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_USERS = [
    ("hiker_arman", "hiker123", "hiker", "Arman Talgat", "arman@mail.kz", "+77031234567"),
    ("hiker_madina", "hiker123", "hiker", "Madina Yerbol", "madina@mail.kz", "+77041234567"),
    ("hiker_timur", "hiker123", "hiker", "Timur Serik", "timur@mail.kz", "+77051234567"),
    ("ranger_aibek", "ranger123", "ranger", "Aibek Nurlan", "aibek@mtsis.kz", "+77011234567"),
    ("ranger_dana", "ranger123", "ranger", "Dana Samat", "dana@mtsis.kz", "+77021234567"),
]

def main():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found. Run 'python init_db.py' first.")
        exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    
    for username, password, role, full_name, email, phone in TEST_USERS:
        password_hash = pwd_context.hash(password)
        try:
            conn.execute(
                """INSERT INTO users (username, password_hash, role, full_name, email, phone)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, password_hash, role, full_name, email, phone),
            )
            print(f"✅ Created user: {username} ({role})")
        except sqlite3.IntegrityError:
            print(f"⚠️  User already exists: {username}")
    
    conn.commit()
    conn.close()
    print("\n✅ Bootstrap complete!")
    print("\n🔑 Test credentials:")
    for username, password, role, _, _, _ in TEST_USERS:
        print(f"  {username:20} / {password:20} (role: {role})")

if __name__ == "__main__":
    main()
