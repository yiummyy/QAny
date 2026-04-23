import pytest


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ES_URL", "http://localhost:9200")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ENVIRONMENT", "test")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
