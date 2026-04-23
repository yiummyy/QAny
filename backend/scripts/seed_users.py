"""Seed three test accounts for local smoke runs."""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.pg import dispose_engine, get_engine

SEED_USERS = [
    {
        "username": "admin",
        "password": "Admin@123456",
        "role": "admin",
        "permission_level": "L3",
        "department": "IT",
    },
    {
        "username": "employee_demo",
        "password": "Employee@12345",
        "role": "employee",
        "permission_level": "L2",
        "department": "HR",
    },
    {
        "username": "guest_demo",
        "password": "Guest@123456",
        "role": "guest",
        "permission_level": "L1",
        "department": None,
    },
]


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


async def seed() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for user in SEED_USERS:
            await conn.execute(
                text(
                    """
                    INSERT INTO users
                      (user_id, username, password_hash, role, permission_level,
                       department, is_active, created_at)
                    VALUES (:uid, :username, :password_hash, :role, :permission_level,
                            :department, TRUE, :created_at)
                    ON CONFLICT (username) DO NOTHING
                    """
                ),
                {
                    "uid": f"u_{uuid.uuid4().hex[:8]}",
                    "username": user["username"],
                    "password_hash": _hash(user["password"]),
                    "role": user["role"],
                    "permission_level": user["permission_level"],
                    "department": user["department"],
                    "created_at": datetime.now(timezone.utc),
                },
            )
    print(f"[seed_users] ensured {len(SEED_USERS)} accounts")


async def main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
