"""Task 2: Session Store tests — JSONL append + Redis cache + Task JSON."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.harness.session_store import (
    SESSION_TTL,
    _build_session_key,
    _session_file_path,
    append,
    get_history,
    load_task,
    save_task,
)


class FakeRedis:
    """In-memory Redis stub for testing."""

    def __init__(self):
        self.data: dict[str, dict] = {}
        self.expires: dict[str, int] = {}

    async def hset(self, key, mapping):
        self.data.setdefault(key, {})
        self.data[key].update(mapping)

    async def hgetall(self, key):
        return self.data.get(key, {})

    async def expire(self, key, ttl):
        self.expires[key] = ttl

    async def exists(self, key):
        return key in self.data


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def tmp_data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


def test_build_session_key():
    key = _build_session_key("abc123")
    assert key == "session:abc123"


def test_session_file_path_day_partition():
    p = _session_file_path("sess-1")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today in str(p)
    assert p.name == "sess-1.jsonl"


async def test_append_writes_jsonl(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    record = {"ts": "2026-04-24T14:30:01Z", "type": "user", "content": "年假制度是什么？"}
    await append("sess-test-1", record)

    # Check file exists
    file_path = _session_file_path("sess-test-1")
    assert file_path.exists()
    lines = file_path.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "user"
    assert parsed["content"] == "年假制度是什么？"


async def test_append_writes_redis(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    await append("sess-r-1", {"type": "user", "content": "hello"})

    key = _build_session_key("sess-r-1")
    assert key in fake_redis.data


async def test_append_multiple_lines(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    await append("sess-multi", {"type": "user", "content": "q1"})
    await append("sess-multi", {"type": "assistant_stream", "chunk": "answer"})

    file_path = _session_file_path("sess-multi")
    lines = file_path.read_text().strip().split("\n")
    assert len(lines) == 2


async def test_get_history_from_redis(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    # Pre-populate redis
    key = _build_session_key("sess-hist")
    fake_redis.data[key] = {"records": json.dumps([{"type": "user", "content": "q"}])}

    history = await get_history("sess-hist")
    assert len(history) == 1
    assert history[0]["type"] == "user"


async def test_get_history_empty_session(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    history = await get_history("nonexistent")
    assert history == []


async def test_get_history_fallback_to_file(tmp_data_dir, fake_redis, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    # Write JSONL directly (no Redis)
    file_path = _session_file_path("sess-fallback")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps({"type": "user", "content": "from file"}) + "\n",
        encoding="utf-8",
    )

    history = await get_history("sess-fallback")
    assert len(history) == 1
    assert history[0]["content"] == "from file"


async def test_save_and_load_task(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))

    task_id = "task_test_001"
    task_data = {
        "task_id": task_id,
        "query": "测试问题",
        "sources": [{"chunk_id": "c1", "score": 0.92}],
        "answer": "测试答案",
    }
    await save_task(task_id, task_data)

    loaded = await load_task(task_id)
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["query"] == "测试问题"
    assert len(loaded["sources"]) == 1


async def test_load_task_nonexistent(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))
    loaded = await load_task("no_such_task")
    assert loaded is None


async def test_file_path_uses_data_dir(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.harness.session_store.get_settings", lambda: _fake_settings(tmp_data_dir))
    path = _session_file_path("sess-dir")
    assert str(tmp_data_dir) in str(path)


async def test_session_ttl_constant():
    assert SESSION_TTL == 1800  # 30 min


def _fake_settings(tmp_dir):
    from unittest.mock import MagicMock

    s = MagicMock()
    s.data_dir = str(tmp_dir)
    return s
