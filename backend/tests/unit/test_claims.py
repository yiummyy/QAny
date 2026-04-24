import pytest
from pydantic import ValidationError

from app.auth.claims import Role, UserClaims


def test_user_claims_valid():
    c = UserClaims(
        sub="u_001",
        username="zhangsan",
        role="employee",
        pl="L2",
        dept="HR",
        jti="j_xxx",
    )
    assert c.role is Role.EMPLOYEE
    assert c.is_admin is False


def test_user_claims_role_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        UserClaims(
            sub="u_001", username="x", role="superadmin", pl="L2", jti="j",
        )


def test_user_claims_permission_level_must_be_l1_l2_l3():
    with pytest.raises(ValidationError):
        UserClaims(sub="u", username="x", role="guest", pl="L0", jti="j")


def test_user_claims_dept_is_optional():
    c = UserClaims(sub="u", username="x", role="guest", pl="L1", jti="j")
    assert c.dept is None


def test_user_claims_from_jwt_payload_round_trip():
    payload = {
        "sub": "u_001",
        "username": "zhangsan",
        "role": "admin",
        "pl": "L3",
        "dept": "IT",
        "jti": "j_abc",
        "iat": 1,
        "exp": 2,
        "token_type": "access",
    }
    c = UserClaims.from_jwt_payload(payload)
    assert c.is_admin is True
    assert c.sub == "u_001"
