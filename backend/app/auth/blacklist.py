"""Redis-backed JWT jti blacklist + access↔refresh pair tracking.

Two key spaces:
- `jwt_blacklist:{jti}`      — jti is revoked (user logged out or admin kicked)
- `jwt_pair:{jti}`           — value = partner jti (access←→refresh pairing)

Logout flow uses `pop_pair` to cascade-revoke the partner token so that a
stolen refresh cannot mint a new access after the owner logs out.
"""

from __future__ import annotations

from app.storage.redis_client import get_redis

_BLACKLIST_PREFIX = "jwt_blacklist"
_PAIR_PREFIX = "jwt_pair"


def _bl_key(jti: str) -> str:
    return f"{_BLACKLIST_PREFIX}:{jti}"


def _pair_key(jti: str) -> str:
    return f"{_PAIR_PREFIX}:{jti}"


async def revoke(*, jti: str, ttl_seconds: int) -> None:
    """Add jti to blacklist with TTL = remaining_exp.

    TTL<=0 is a no-op: token is already expired naturally, no need to track.
    """
    if ttl_seconds <= 0:
        return
    await get_redis().setex(_bl_key(jti), ttl_seconds, "1")


async def is_revoked(jti: str) -> bool:
    return bool(await get_redis().exists(_bl_key(jti)))


async def register_pair(*, access_jti: str, refresh_jti: str, ttl_seconds: int) -> None:
    """Mark access↔refresh as paired. TTL 建议用 refresh_ttl（两者里较长的那个）。"""
    if ttl_seconds <= 0:
        return
    r = get_redis()
    pipe = r.pipeline()
    pipe.setex(_pair_key(access_jti), ttl_seconds, refresh_jti)
    pipe.setex(_pair_key(refresh_jti), ttl_seconds, access_jti)
    await pipe.execute()


async def pop_pair(jti: str) -> str | None:
    """Return the partner jti if registered, and delete both pair entries.

    Returns None if no pair is registered (or already popped).
    """
    r = get_redis()
    partner = await r.get(_pair_key(jti))
    if partner is None:
        return None
    pipe = r.pipeline()
    pipe.delete(_pair_key(jti))
    pipe.delete(_pair_key(partner))
    await pipe.execute()
    return partner
