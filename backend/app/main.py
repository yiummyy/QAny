from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.config import Settings, get_settings
from app.logging_conf import configure_logging, get_logger

_log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.environment)
    _log.info("app_startup", env=settings.environment)
    yield


app = FastAPI(title="Enterprise QA MVP", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, object]:  # noqa: B008
    return {"status": "ok", "deps": {}, "env": settings.environment}
