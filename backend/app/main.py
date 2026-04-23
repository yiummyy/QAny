import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.config import Settings, get_settings
from app.logging_conf import configure_logging, get_logger
from app.storage.pg import dispose_engine, get_sessionmaker
from app.storage.redis_client import close_redis, get_redis

_PROBE_TIMEOUT_SECONDS = 3.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.environment)
    log = get_logger(__name__)
    log.info("app_startup", env=settings.environment)
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()


app = FastAPI(title="Enterprise QA MVP", version="0.1.0", lifespan=lifespan)


async def _check_pg() -> str:
    async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> str:
    async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
        pong = await get_redis().ping()
    return "ok" if pong else "down"


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, object]:  # noqa: B008
    pg_result, redis_result = await asyncio.gather(
        _check_pg(), _check_redis(), return_exceptions=True
    )
    deps: dict[str, str] = {
        "pg": pg_result if isinstance(pg_result, str) else "down",
        "redis": redis_result if isinstance(redis_result, str) else "down",
    }
    status = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {"status": status, "deps": deps, "env": settings.environment}
