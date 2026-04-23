import pytest
from pydantic import ValidationError

import app.config as cfg


def test_settings_fail_fast_on_missing_required(monkeypatch):
    """缺必填环境变量必须启动即失败，不得默默跑。"""
    for k in ["DATABASE_URL", "ES_URL", "REDIS_URL", "JWT_SECRET"]:
        monkeypatch.delenv(k, raising=False)
    cfg.get_settings.cache_clear()
    with pytest.raises(ValidationError):
        cfg.get_settings()


def test_settings_accepts_minimal_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ES_URL", "http://localhost:9200")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    s = cfg.get_settings()
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert len(s.jwt_secret.get_secret_value()) >= 32
