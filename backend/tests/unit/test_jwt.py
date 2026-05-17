import time

import pytest
from jose import JWTError

from app.auth.jwt import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_access_token_round_trip():
    token, jti = create_access_token(
        user_id="u_001",
        username="zhangsan",
        role="employee",
        permission_level="L2",
        department="HR",
    )
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == "u_001"
    assert payload["username"] == "zhangsan"
    assert payload["role"] == "employee"
    assert payload["pl"] == "L2"
    assert payload["dept"] == "HR"
    assert payload["jti"] == jti
    assert payload["token_type"] == "access"
    assert isinstance(payload["exp"], int)
    assert isinstance(payload["iat"], int)
    assert 890 <= payload["exp"] - payload["iat"] <= 910


def test_refresh_token_has_minimal_claims():
    token, jti = create_refresh_token(user_id="u_001")
    payload = decode_token(token, expected_type=TokenType.REFRESH)
    assert payload["sub"] == "u_001"
    assert payload["jti"] == jti
    assert payload["token_type"] == "refresh"
    for sensitive in ("role", "pl", "dept", "username"):
        assert sensitive not in payload


def test_decode_token_rejects_expired(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1")
    from app.config import get_settings
    get_settings.cache_clear()
    token, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    time.sleep(2)
    with pytest.raises(JWTError):
        decode_token(token, expected_type=TokenType.ACCESS)
    get_settings.cache_clear()


def test_decode_token_rejects_wrong_secret(monkeypatch):
    token, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    monkeypatch.setenv("JWT_SECRET", "y" * 32)
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(JWTError):
        decode_token(token, expected_type=TokenType.ACCESS)
    get_settings.cache_clear()


def test_decode_token_rejects_wrong_type():
    access, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    with pytest.raises(JWTError):
        decode_token(access, expected_type=TokenType.REFRESH)


def test_token_jti_is_unique_per_issue():
    t1, j1 = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    t2, j2 = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    assert j1 != j2
    assert t1 != t2
