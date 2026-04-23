import json

from app.logging_conf import configure_logging, get_logger


def test_log_is_json_and_contains_required_fields(capsys):
    configure_logging(level="INFO", env="dev")
    logger = get_logger("test")
    logger.info("hello", session_id="s1", trace_id="t1")
    captured = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(captured)
    assert data["event"] == "hello"
    assert data["session_id"] == "s1"
    assert data["trace_id"] == "t1"
    assert data["logger"] == "test"
    assert "ts" in data
