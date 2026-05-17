import json
import logging

import pytest

from app.logging_conf import configure_logging, get_logger


def test_log_is_json_and_contains_required_fields(capsys: pytest.CaptureFixture[str]) -> None:
    logging.getLogger().handlers.clear()
    configure_logging(level="INFO", env="dev")
    logger = get_logger("test")
    logger.info("hello", session_id="s1", trace_id="t1")
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1, f"Expected one log line, got {len(lines)}: {lines}"
    data = json.loads(lines[0])
    assert data["event"] == "hello"
    assert data["session_id"] == "s1"
    assert data["trace_id"] == "t1"
    assert data["logger"] == "test"
    assert "ts" in data
    assert data["level"] == "info"
