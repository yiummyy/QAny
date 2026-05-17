"""Phase 1 gap backfill: cover scripts/seed_users.py end-to-end."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_seed_users_inserts_three_accounts(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)

    from app.storage.pg import dispose_engine
    from scripts.seed_users import seed

    try:
        await seed()
    finally:
        await dispose_engine()

    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT username, role, permission_level, password_hash, is_active "
                    "FROM users ORDER BY username"
                )
            )
        ).all()
    await engine.dispose()

    names = {r[0] for r in rows}
    assert names == {"admin", "employee_demo", "guest_demo"}
    for r in rows:
        assert r[4] is True, f"{r[0]} should be active"
        assert r[3].startswith("$2b$12$"), f"{r[0]} hash must be bcrypt cost=12"


@pytest.mark.asyncio
async def test_seed_users_is_idempotent(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)

    from app.storage.pg import dispose_engine
    from scripts.seed_users import seed

    try:
        await seed()
        await seed()
    finally:
        await dispose_engine()

    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        cnt = (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one()
    await engine.dispose()
    assert cnt == 3
