import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.api.errors import install_exception_handlers
import app.tools.create_ticket as _  # noqa: F401 — trigger @register_agent_tool
import app.tools.escalate as _  # noqa: F401
import app.tools.generate_answer as _  # noqa: F401 — trigger @register
import app.tools.generate_proposal as _  # noqa: F401
import app.tools.hallucination_check as _  # noqa: F401
import app.tools.hybrid_search as _  # noqa: F401
import app.tools.lookup_ticket as _  # noqa: F401
import app.tools.permission_check as _  # noqa: F401
import app.tools.query_knowledge as _  # noqa: F401
import app.tools.query_monitoring as _  # noqa: F401
import app.tools.rerank as _  # noqa: F401
import app.tools.rewrite_query as _  # noqa: F401
import app.tools.run_diagnostic as _  # noqa: F401
import app.tools.search_crm as _  # noqa: F401
import app.tools.search_knowledge as _  # noqa: F401
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.eval import router as eval_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.qa import router as qa_router
from app.config import Settings, get_settings
from app.logging_conf import configure_logging, get_logger
from app.middleware.trace import TraceIDMiddleware
from app.storage.es_client import close_es, get_es
from app.storage.pg import dispose_engine, get_sessionmaker
from app.storage.redis_client import close_redis, get_redis

_PROBE_TIMEOUT_SECONDS = 3.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.environment)
    log = get_logger(__name__)
    log.info("app_startup", env=settings.environment)

    # Pre-warm embedding and reranker models in background so the first request
    # doesn't suffer the full cold-start cost (model download + load).
    asyncio.create_task(_warmup_embedder(log))
    asyncio.create_task(_warmup_reranker(log))

    try:
        yield
    finally:
        await close_es()
        await close_redis()
        await dispose_engine()


async def _warmup_embedder(log) -> None:
    """Load the SentenceTransformer embedding model in the background.

    The first call to encode_query() would otherwise block the request for
    several minutes while downloading/loading the model.  Running this at
    startup hides that latency behind the health-check window.
    """
    try:
        from app.knowledge.embedder import get_embedder

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, get_embedder)
        log.info("embedder_warmup_done")
    except Exception as exc:
        log.warning("embedder_warmup_failed: %s", exc)


async def _warmup_reranker(log) -> None:
    """Load the BGE-Reranker-v2-m3 model in the background.

    The first call to rerank() would otherwise block while downloading the
    ~1.2GB model, causing the client to time out.
    """
    try:
        from app.knowledge.reranker import get_reranker

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, get_reranker)
        log.info("reranker_warmup_done")
    except Exception as exc:
        log.warning("reranker_warmup_failed: %s", exc)


app = FastAPI(title="Enterprise QA MVP", version="0.1.0", lifespan=lifespan)

# --- Middleware stack (outermost first) ---

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceIDMiddleware)

# --- Prometheus ---

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

# --- Exception handlers ---

install_exception_handlers(app)

# --- Routers ---

app.include_router(auth_router)
app.include_router(qa_router)
app.include_router(eval_router)
app.include_router(feedback_router)
app.include_router(admin_router)
app.include_router(knowledge_router)


async def _check_pg() -> str:
    async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> str:
    async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
        pong = await get_redis().ping()
    return "ok" if pong else "down"


async def _check_es() -> str:
    async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
        info = await get_es().info()
    return "ok" if "version" in info else "down"


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, object]:  # noqa: B008
    pg_result, redis_result, es_result = await asyncio.gather(
        _check_pg(), _check_redis(), _check_es(), return_exceptions=True
    )
    deps: dict[str, str] = {
        "pg": pg_result if isinstance(pg_result, str) else "down",
        "redis": redis_result if isinstance(redis_result, str) else "down",
        "es": es_result if isinstance(es_result, str) else "down",
    }
    status = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {"status": status, "deps": deps, "env": settings.environment}
