import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_upgrade_head_creates_all_tables(pg_url):
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        )
        names = {row[0] for row in result}
    await engine.dispose()
    assert {"users", "documents", "qa_logs", "feedbacks", "qa_settings"}.issubset(names)


@pytest.mark.asyncio
async def test_qa_settings_has_default_row(pg_url):
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT id, config FROM qa_settings WHERE id=1")
        )).first()
    await engine.dispose()
    assert row is not None
    cfg = row[1]
    assert cfg["rerank_enabled"] is True
    assert cfg["hallucination_threshold"] == 0.6
    assert cfg["max_context_docs"] == 5
