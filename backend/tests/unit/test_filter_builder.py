from app.auth.claims import UserClaims
from app.rbac.filter_builder import ROLE_LEVEL_MATRIX, build_es_filter


def _c(role: str) -> UserClaims:
    return UserClaims(sub="u", username="u", role=role, pl="L1", jti="j")


def test_matrix_matches_spec():
    assert ROLE_LEVEL_MATRIX == {
        "guest": ["L1"],
        "employee": ["L1", "L2"],
        "admin": ["L1", "L2", "L3"],
    }


def test_guest_filter_only_l1():
    f = build_es_filter(_c("guest"))
    terms = f["bool"]["filter"][0]["terms"]["permission_level"]
    assert terms == ["L1"]
    assert "L2" not in terms
    assert "L3" not in terms


def test_employee_filter_l1_l2():
    f = build_es_filter(_c("employee"))
    terms = f["bool"]["filter"][0]["terms"]["permission_level"]
    assert set(terms) == {"L1", "L2"}
    assert "L3" not in terms


def test_admin_filter_all_levels():
    f = build_es_filter(_c("admin"))
    terms = f["bool"]["filter"][0]["terms"]["permission_level"]
    assert set(terms) == {"L1", "L2", "L3"}
