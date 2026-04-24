
from app.auth.passwords import hash_password, verify_password


def test_hash_password_uses_bcrypt_cost_12():
    h = hash_password("Admin@123456")
    assert h.startswith("$2b$12$"), "bcrypt cost must be 12 per Spec §5.6"


def test_verify_password_accepts_correct():
    h = hash_password("Admin@123456")
    assert verify_password("Admin@123456", h) is True


def test_verify_password_rejects_wrong():
    h = hash_password("Admin@123456")
    assert verify_password("wrong-password", h) is False


def test_verify_password_returns_false_on_malformed_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_hash_password_generates_distinct_hashes_for_same_input():
    assert hash_password("same") != hash_password("same")
