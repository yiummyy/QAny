"""Password hashing/verification helpers — bcrypt cost=12 per Spec §5.6."""

import bcrypt

_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Return a bcrypt hash (cost=12) of the plaintext password."""
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verify.

    Returns False for malformed hashes instead of raising — callers should
    treat any verification failure uniformly to avoid info leak.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
