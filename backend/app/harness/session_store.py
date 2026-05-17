"""Session SSOT: JSONL disk + Redis hot cache + Task JSON — Spec §2.4."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.storage.redis_client import get_redis

SESSION_TTL = 1800  # 30 min


def _build_session_key(session_id: str) -> str:
    return f"session:{session_id}"


def _session_file_path(session_id: str) -> Path:
    settings = get_settings()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Path(settings.data_dir) / "sessions" / date_str / f"{session_id}.jsonl"


def _task_file_path(task_id: str) -> Path:
    settings = get_settings()
    return Path(settings.data_dir) / "tasks" / f"{task_id}.json"


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def append(session_id: str, record: dict[str, Any]) -> None:
    """Append one line to the session JSONL and sync to Redis cache."""
    record.setdefault("ts", _now_ts())

    file_path = _session_file_path(session_id)
    _ensure_dir(file_path)

    line = json.dumps(record, ensure_ascii=False) + "\n"
    await asyncio.to_thread(_write_line, file_path, line)

    try:
        redis = get_redis()
        key = _build_session_key(session_id)
        existing = await redis.hgetall(key)
        records_json = existing.get("records", "[]")
        records: list = json.loads(records_json)
        records.append(record)
        await redis.hset(key, mapping={"records": json.dumps(records, ensure_ascii=False)})
        await redis.expire(key, SESSION_TTL)
    except Exception:
        pass  # Redis unavailable is non-blocking


def _write_line(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


async def get_history(session_id: str) -> list[dict[str, Any]]:
    """Read session history, Redis-first with JSONL fallback."""
    try:
        redis = get_redis()
        key = _build_session_key(session_id)
        data = await redis.hgetall(key)
        if data and "records" in data:
            return json.loads(data["records"])
    except Exception:
        pass

    # Fallback to JSONL file
    file_path = _session_file_path(session_id)
    if not file_path.exists():
        return []

    content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
    records: list[dict[str, Any]] = []
    for line in content.strip().split("\n"):
        if line.strip():
            records.append(json.loads(line))
    return records


async def save_task(task_id: str, task_data: dict[str, Any]) -> None:
    """Persist full task JSON to disk."""
    file_path = _task_file_path(task_id)
    _ensure_dir(file_path)
    content = json.dumps(task_data, ensure_ascii=False, indent=2)
    await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")


async def load_task(task_id: str) -> dict[str, Any] | None:
    """Load task JSON from disk."""
    file_path = _task_file_path(task_id)
    if not file_path.exists():
        return None
    content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
    return json.loads(content)


def make_task_id() -> str:
    return "task_" + uuid.uuid4().hex[:12]
