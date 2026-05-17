"""Long-term memory — FAQ cache + user profile (B3)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FAQ_CACHE_TTL = 7 * 86400  # 7 days
FAQ_PROMOTION_THRESHOLD = 5  # queries/day before caching


# ---------------------------------------------------------------------------
# FAQ Cache (Redis)
# ---------------------------------------------------------------------------


def _faq_key(agent_name: str, query_hash: str) -> str:
    return f"faq:{agent_name}:{query_hash}"


def _normalize_query(query: str) -> str:
    """Normalize query for consistent hashing."""
    return "".join(query.lower().split())


async def faq_cache_get(agent_name: str, query: str) -> dict | None:
    """Check FAQ cache for exact query match. Returns cached answer or None."""
    query_hash = hashlib.md5(_normalize_query(query).encode()).hexdigest()[:12]
    key = _faq_key(agent_name, query_hash)

    try:
        from app.storage.redis_client import get_redis

        redis = get_redis()
        raw = await redis.get(key)
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            logger.info("faq_cache: hit agent=%s hash=%s", agent_name, query_hash)
            return data
    except Exception:
        pass
    return None


async def faq_cache_set(
    agent_name: str, query: str, answer: str, sources: list[dict] | None = None,
    frequency: int = 1,
) -> None:
    """Store an answer in FAQ cache if frequency exceeds threshold."""
    if frequency < FAQ_PROMOTION_THRESHOLD:
        return

    query_hash = hashlib.md5(_normalize_query(query).encode()).hexdigest()[:12]
    key = _faq_key(agent_name, query_hash)

    data = {
        "query_hash": query_hash,
        "query": query[:200],
        "answer": answer[:2000],
        "sources": (sources or [])[:5],
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from app.storage.redis_client import get_redis

        redis = get_redis()
        await redis.set(key, json.dumps(data, ensure_ascii=False), ex=FAQ_CACHE_TTL)
        logger.info("faq_cache: stored agent=%s hash=%s", agent_name, query_hash)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# User Profile (PostgreSQL)
# ---------------------------------------------------------------------------


async def get_user_profile(user_id: str) -> dict | None:
    """Load user's long-term preferences from PostgreSQL."""
    try:
        from app.models.user_profile import UserProfile
        from app.storage.pg import get_sessionmaker

        async with get_sessionmaker()() as session:
            row = await session.get(UserProfile, user_id)
            if row:
                return {
                    "user_id": row.user_id,
                    "preferred_scene": row.preferred_scene,
                    "department": row.department,
                    "expertise_domains": row.expertise_domains or [],
                }
    except Exception:
        pass
    return None


async def upsert_user_profile(
    user_id: str,
    preferred_scene: str | None = None,
    department: str | None = None,
    expertise_domains: list[str] | None = None,
) -> None:
    """Create or update user's long-term preferences."""
    try:
        from app.models.user_profile import UserProfile
        from app.storage.pg import get_sessionmaker

        async with get_sessionmaker()() as session:
            row = await session.get(UserProfile, user_id)
            if row:
                if preferred_scene is not None:
                    row.preferred_scene = preferred_scene
                if department is not None:
                    row.department = department
                if expertise_domains is not None:
                    row.expertise_domains = expertise_domains
                row.updated_at = datetime.now(timezone.utc)
            else:
                row = UserProfile(
                    user_id=user_id,
                    preferred_scene=preferred_scene or "general",
                    department=department,
                    expertise_domains=expertise_domains or [],
                )
                session.add(row)
            await session.commit()
    except Exception:
        logger.warning("upsert_user_profile failed for %s", user_id, exc_info=True)
