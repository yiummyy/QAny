# Phase 1: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起可 `./deploy.sh start` 一键启动的空骨架：PG + ES + Redis + FastAPI（仅 `/healthz`）+ 前端脚手架 + Alembic 所有表迁移 + ES qa_chunks 索引 + seed users。为后续 6 个 Phase 奠地基。

**Architecture:** 后端 Python 3.11 + FastAPI + SQLAlchemy 2 async + asyncpg + Alembic + structlog；前端 Vite + React 18 + TypeScript；存储 PostgreSQL 16 + Elasticsearch 8.11 (infinilabs IK) + Redis 7；docker-compose 编排，deploy.sh 包装。

**Tech Stack:** Python 3.11, FastAPI 0.110+, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic-settings, structlog, bcrypt, redis-py 5.0+, elasticsearch-py 8.11, Vite 5, React 18, TypeScript 5, TailwindCSS 3, pytest, pytest-asyncio, testcontainers, ruff, mypy。

---

## Phase 1 Definition of Done（硬门）

- [ ] `./deploy.sh start` 后 60 秒内 `./deploy.sh ps` 所有服务 `healthy`
- [ ] `curl http://localhost:8000/healthz` 返回 `{"status":"ok","deps":{"pg":"ok","es":"ok","redis":"ok"}}`
- [ ] Alembic `upgrade head` 建出 users / documents / qa_logs / feedbacks / qa_settings 五张表
- [ ] `qa_settings` 存在单行默认配置（rerank_enabled=true 等）
- [ ] ES `qa_chunks` 索引已创建，`GET qa_chunks/_mapping` 含 1024 维 `dense_vector` + `ik_smart_plus` analyzer
- [ ] `seed_users.py` 写入 admin / employee / guest 三条测试账户，bcrypt hash 正确
- [ ] 前端 `npm run build` 生成 `dist/`，Nginx 容器可访问
- [ ] CI workflow (ruff + mypy + pytest unit + frontend tsc) 全绿
- [ ] 无 Secrets 泄漏：`.env` 未入库，`.env.example` 只含占位

---

## File Structure 先定盘

按 Spec §1.3 的目录树落地。本 Phase 创建的文件（其余 Phase 再添）：

```
qa-system/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # /healthz + 依赖健康检查
│   │   ├── config.py                # pydantic-settings Settings
│   │   ├── logging_conf.py          # structlog JSON 配置
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── pg.py                # async engine + get_db
│   │   │   ├── es_client.py         # AsyncElasticsearch 单例
│   │   │   └── redis_client.py      # async redis 单例
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── base.py              # DeclarativeBase + common mixin
│   │       ├── user.py
│   │       ├── document.py
│   │       ├── qa_log.py
│   │       ├── feedback.py
│   │       └── settings.py
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial.py      # 所有 5 表 DDL + qa_settings 默认行
│   ├── scripts/
│   │   ├── init_es.py               # 创建 qa_chunks 索引
│   │   └── seed_users.py            # admin/employee/guest 三账户
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   │   ├── test_config.py
│   │   │   ├── test_logging.py
│   │   │   ├── test_healthz.py
│   │   │   └── test_models_smoke.py
│   │   └── integration/
│   │       ├── conftest.py          # testcontainers fixtures
│   │       ├── test_migrations.py
│   │       ├── test_redis.py
│   │       ├── test_es_index.py
│   │       └── test_seed_users.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   └── .dockerignore
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   └── index.css
│   └── .dockerignore
├── docker-compose.yml
├── deploy.sh
├── .env.example
└── .github/
    └── workflows/
        └── ci.yml
```

分工原则：`storage/` 只做客户端封装（单例 + lifecycle），`models/` 只做 ORM 定义，`scripts/` 是一次性工具（从 `app` 复用 config/storage 但不被 app 导入），`migrations/` 由 Alembic 管，**迁移 SQL 才是真理**，ORM 是配套类型。

---

## 分支与 Commit 策略

本 Phase 全程在独立分支 `phase1-foundation`。每个 Task 完成后单独 commit，Task 完整跑通后 push。

```bash
git checkout -b phase1-foundation
# 每个 Task 结尾：
git add <listed files>
git commit -m "<conventional prefix>: <task summary>"
```

---

## Task 1: Backend 项目骨架 + `/healthz` 最小闭环

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/unit/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/unit/test_healthz.py`
- Create: `backend/.dockerignore`
- Create: `.gitignore` 的新条目（已存在则跳过）

- [ ] **Step 1: 写失败测试 `tests/unit/test_healthz.py`**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_healthz_returns_ok_without_deps():
    """默认 /healthz 返回 200 + status=ok，不探测依赖（shallow mode）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "deps" in body  # 后续 Task 会填充
```

- [ ] **Step 2: 执行测试确认失败**

```bash
cd backend
pip install -e '.[dev]' || true   # 第一次还没 pyproject，继续
pytest tests/unit/test_healthz.py -v
```

预期：`ModuleNotFoundError: No module named 'app.main'` 或 `httpx` 未装。

- [ ] **Step 3: 写 `backend/pyproject.toml`**

```toml
[project]
name = "qa-backend"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "structlog>=24.1",
    "python-json-logger>=2.0",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "redis>=5.0",
    "elasticsearch>=8.11,<9",
    "bcrypt>=4.1",
    "python-jose[cryptography]>=3.3",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "httpx>=0.27",
    "respx>=0.20",
    "testcontainers[postgres,elasticsearch,redis]>=4.0",
    "ruff>=0.3",
    "mypy>=1.9",
    "types-redis",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "integration: require external services (pg/es/redis)",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "B", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 4: 写 `backend/app/main.py`（shallow healthz）**

```python
from fastapi import FastAPI

app = FastAPI(title="Enterprise QA MVP", version="0.1.0")

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "deps": {}}
```

写 `backend/app/__init__.py`（空文件）、`backend/tests/__init__.py`（空）、`backend/tests/unit/__init__.py`（空）、`backend/tests/conftest.py`：

```python
import pytest

@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 5: 再跑测试确认通过**

```bash
cd backend
pip install -e '.[dev]'
pytest tests/unit/test_healthz.py -v
```

预期：1 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/app/main.py \
        backend/tests/__init__.py backend/tests/unit/__init__.py \
        backend/tests/conftest.py backend/tests/unit/test_healthz.py
git commit -m "feat(backend): scaffold FastAPI app with shallow healthz"
```

---

## Task 2: 配置管理（pydantic-settings） + fail-fast

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/tests/unit/test_config.py`
- Modify: `backend/app/main.py`（注入 settings）

- [ ] **Step 1: 写失败测试 `tests/unit/test_config.py`**

```python
import os
import pytest
from pydantic import ValidationError

def test_settings_fail_fast_on_missing_required(monkeypatch):
    """缺必填环境变量必须启动即失败，不得默默跑。"""
    for k in ["DATABASE_URL", "ES_URL", "REDIS_URL", "JWT_SECRET"]:
        monkeypatch.delenv(k, raising=False)
    # 重新导入以触发验证
    import importlib
    import app.config as cfg
    with pytest.raises(ValidationError):
        importlib.reload(cfg)
        cfg.Settings()  # 显式实例化

def test_settings_accepts_minimal_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ES_URL", "http://localhost:9200")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    s = cfg.Settings()
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert len(s.jwt_secret) >= 32
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_config.py -v
```

预期：`ModuleNotFoundError: app.config`。

- [ ] **Step 3: 实现 `backend/app/config.py`**

```python
from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Storage
    database_url: str = Field(..., min_length=1)
    es_url: str = Field(..., min_length=1)
    redis_url: str = Field(..., min_length=1)

    # Auth
    jwt_secret: SecretStr = Field(..., min_length=32)
    jwt_access_ttl_seconds: int = 900      # 15min
    jwt_refresh_ttl_seconds: int = 604_800  # 7d

    # LLM (Phase 4 使用，这里提前预留并允许空)
    dashscope_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None

    # Runtime
    data_dir: str = "/app/data"
    log_level: str = "INFO"
    environment: str = "dev"  # dev|prod

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Main 引用 Settings（暂不暴露）**

修改 `backend/app/main.py`：

```python
from fastapi import FastAPI
from app.config import get_settings

settings = get_settings()
app = FastAPI(title="Enterprise QA MVP", version="0.1.0")

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "deps": {}, "env": settings.environment}
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/unit/test_config.py tests/unit/test_healthz.py -v
```

测试 healthz 需要设置临时环境变量；在 `tests/conftest.py` 追加 autouse fixture：

```python
import pytest

@pytest.fixture(autouse=True)
def _default_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("ES_URL", "http://localhost:9200")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ENVIRONMENT", "test")
```

重跑：预期全绿。

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/unit/test_config.py backend/tests/conftest.py
git commit -m "feat(backend): add pydantic-settings with fail-fast validation"
```

---

## Task 3: 结构化日志（structlog JSON + trace_id 占位）

**Files:**
- Create: `backend/app/logging_conf.py`
- Create: `backend/tests/unit/test_logging.py`
- Modify: `backend/app/main.py`（启动 logger）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_logging.py
import json
import logging
from app.logging_conf import configure_logging, get_logger

def test_log_is_json_and_contains_required_fields(capsys):
    configure_logging(level="INFO", env="dev")
    logger = get_logger("test")
    logger.info("hello", session_id="s1", trace_id="t1")
    captured = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(captured)
    assert data["event"] == "hello"
    assert data["session_id"] == "s1"
    assert data["trace_id"] == "t1"
    assert data["logger"] == "test"
    assert "ts" in data
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_logging.py -v
```

- [ ] **Step 3: 实现 `app/logging_conf.py`**

```python
import logging
import sys
import structlog

def configure_logging(level: str = "INFO", env: str = "dev") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
    )
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if env == "dev":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer(sort_keys=True))
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 4: `main.py` 启动时调用**

```python
from fastapi import FastAPI
from app.config import get_settings
from app.logging_conf import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.log_level, env=settings.environment)
log = get_logger(__name__)
app = FastAPI(title="Enterprise QA MVP", version="0.1.0")

@app.on_event("startup")
async def _on_start() -> None:
    log.info("app_startup", env=settings.environment)

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "deps": {}, "env": settings.environment}
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/unit/test_logging.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/logging_conf.py backend/app/main.py backend/tests/unit/test_logging.py
git commit -m "feat(backend): wire structlog JSON logging with contextvars"
```

---

## Task 4: PostgreSQL 异步引擎 + ORM Base

**Files:**
- Create: `backend/app/storage/__init__.py`
- Create: `backend/app/storage/pg.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/tests/unit/test_models_smoke.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/unit/test_models_smoke.py
from app.models.base import Base, TimestampMixin
from sqlalchemy import Column, String
import pytest

def test_base_is_declarative():
    assert hasattr(Base, "metadata")
    assert Base.metadata is not None

def test_timestamp_mixin_exposes_columns():
    class Dummy(Base, TimestampMixin):
        __tablename__ = "dummy"
        id = Column(String, primary_key=True)
    cols = {c.name for c in Dummy.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/test_models_smoke.py -v
```

- [ ] **Step 3: 实现 `app/models/base.py`**

```python
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

`app/models/__init__.py`：

```python
from app.models.base import Base, TimestampMixin  # noqa: F401
```

- [ ] **Step 4: 实现 `app/storage/pg.py`**

```python
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None

def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
            future=True,
        )
    return _engine

def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, autoflush=False
        )
    return _factory

async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session

async def dispose_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _factory = None
```

`app/storage/__init__.py` 留空。

- [ ] **Step 5: 跑测试**

```bash
pytest tests/unit/test_models_smoke.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/storage/ backend/app/models/ backend/tests/unit/test_models_smoke.py
git commit -m "feat(backend): add async SQLAlchemy engine and ORM base"
```

---

## Task 5: ORM 模型（5 张表）

严格对齐 Spec §4.4 DDL。模型只负责 Python 端类型，权威 DDL 在 Task 6 迁移里。

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/document.py`
- Create: `backend/app/models/qa_log.py`
- Create: `backend/app/models/feedback.py`
- Create: `backend/app/models/settings.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 写 smoke 测试（追加到 `test_models_smoke.py`）**

```python
def test_all_models_have_table_names():
    from app.models import User, Document, QALog, Feedback, QASettings
    assert User.__tablename__ == "users"
    assert Document.__tablename__ == "documents"
    assert QALog.__tablename__ == "qa_logs"
    assert Feedback.__tablename__ == "feedbacks"
    assert QASettings.__tablename__ == "qa_settings"

def test_user_required_columns():
    from app.models import User
    cols = {c.name for c in User.__table__.columns}
    for c in ["user_id", "username", "password_hash", "role", "permission_level",
              "is_active", "created_at"]:
        assert c in cols
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_models_smoke.py -v
```

- [ ] **Step 3: 实现 5 个模型**

`backend/app/models/user.py`:

```python
from datetime import datetime
from sqlalchemy import Boolean, String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(8), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("idx_users_role", "role"),)
```

`backend/app/models/document.py`:

```python
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Document(Base):
    __tablename__ = "documents"
    doc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(8), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.user_id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_file_hash", "file_hash", unique=True),
    )
```

`backend/app/models/qa_log.py`:

```python
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class QALog(Base):
    __tablename__ = "qa_logs"
    log_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.user_id"), nullable=False)
    scene: Mapped[str] = mapped_column(String(16), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tools_called: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(8), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_rmb: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("idx_qa_logs_user_created", "user_id", "created_at"),
        Index("idx_qa_logs_session", "session_id"),
        Index("idx_qa_logs_created", "created_at"),
    )
```

`backend/app/models/feedback.py`:

```python
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Feedback(Base):
    __tablename__ = "feedbacks"
    feedback_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    log_id: Mapped[str] = mapped_column(String(32), ForeignKey("qa_logs.log_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.user_id"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("idx_feedbacks_log", "log_id"),)
```

`backend/app/models/settings.py`:

```python
from datetime import datetime
from sqlalchemy import Integer, DateTime, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class QASettings(Base):
    __tablename__ = "qa_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.user_id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("id = 1", name="qa_settings_single_row"),)
```

`app/models/__init__.py`：

```python
from app.models.base import Base, TimestampMixin
from app.models.user import User
from app.models.document import Document
from app.models.qa_log import QALog
from app.models.feedback import Feedback
from app.models.settings import QASettings

__all__ = ["Base", "TimestampMixin", "User", "Document", "QALog", "Feedback", "QASettings"]
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/test_models_smoke.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/
git commit -m "feat(backend): add SQLAlchemy ORM models for 5 core tables"
```

---

## Task 6: Alembic 初始迁移 + qa_settings 默认行

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/0001_initial.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_migrations.py`

- [ ] **Step 1: 写失败集成测试**

```python
# backend/tests/integration/test_migrations.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_upgrade_head_creates_all_tables(pg_url):
    # pg_url fixture 会返回 testcontainer 的 URL 并运行 alembic upgrade head
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        )
        names = {row[0] for row in result}
    await engine.dispose()
    assert {"users", "documents", "qa_logs", "feedbacks", "qa_settings"}.issubset(names)

@pytest.mark.asyncio
async def test_qa_settings_has_default_row(pg_url):
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT id, config FROM qa_settings WHERE id=1")
        )).first()
    await engine.dispose()
    assert row is not None
    cfg = row[1]
    assert cfg["rerank_enabled"] is True
    assert cfg["hallucination_threshold"] == 0.6
    assert cfg["max_context_docs"] == 5
```

`backend/tests/integration/conftest.py`：

```python
import pytest
import subprocess
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
def pg_url(pg_container, monkeypatch_session):
    raw = pg_container.get_connection_url()  # postgresql+psycopg2://...
    url = raw.replace("psycopg2", "asyncpg")
    monkeypatch_session.setenv("DATABASE_URL", url)
    # Alembic 同步 URL
    sync_url = raw.replace("psycopg2", "psycopg")
    subprocess.check_call(
        ["alembic", "-x", f"sqlalchemy.url={sync_url}", "upgrade", "head"],
        cwd=".",
    )
    return url

@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/integration/test_migrations.py -v -m integration
```

预期：`alembic: command not found` 或 migration 不存在。

- [ ] **Step 3: 写 `backend/alembic.ini`**

```ini
[alembic]
script_location = migrations
file_template = %%(rev)s_%%(slug)s
sqlalchemy.url =
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handlers]
keys = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatters]
keys = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 4: 写 `backend/migrations/env.py`**

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.models import Base  # noqa: F401 — 确保所有模型被载入

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`backend/migrations/script.py.mako`（标准 Alembic 模板，复制自 alembic init）：

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: 写 `migrations/versions/0001_initial.py`**

```python
"""initial schema — 5 tables + qa_settings default row

Revision ID: 0001
Revises:
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("permission_level", sa.String(8), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_users_role", "users", ["role"])

    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("permission_level", sa.String(8), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("uploaded_by", sa.String(32), sa.ForeignKey("users.user_id")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_file_hash", "documents", ["file_hash"], unique=True)

    op.create_table(
        "qa_logs",
        sa.Column("log_id", sa.String(32), primary_key=True),
        sa.Column("session_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("scene", sa.String(16), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text),
        sa.Column("intent", sa.String(32)),
        sa.Column("entities", postgresql.JSONB),
        sa.Column("sources", postgresql.JSONB),
        sa.Column("tools_called", postgresql.JSONB),
        sa.Column("confidence", sa.String(8)),
        sa.Column("confidence_score", sa.Numeric(4, 3)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("model_name", sa.String(32)),
        sa.Column("cost_rmb", sa.Numeric(10, 4)),
        sa.Column("response_time_ms", sa.Integer),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.Integer),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_qa_logs_user_created", "qa_logs", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_qa_logs_session", "qa_logs", ["session_id"])
    op.create_index("idx_qa_logs_created", "qa_logs", [sa.text("created_at DESC")])

    op.create_table(
        "feedbacks",
        sa.Column("feedback_id", sa.String(32), primary_key=True),
        sa.Column("log_id", sa.String(32), sa.ForeignKey("qa_logs.log_id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("feedback_type", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32)),
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feedbacks_log", "feedbacks", ["log_id"])

    op.create_table(
        "qa_settings",
        sa.Column("id", sa.Integer, primary_key=True, server_default="1"),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("updated_by", sa.String(32), sa.ForeignKey("users.user_id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="qa_settings_single_row"),
    )
    op.execute("""
        INSERT INTO qa_settings (id, config) VALUES (1, '{
          "rerank_enabled": true,
          "hallucination_threshold": 0.6,
          "max_context_docs": 5,
          "model_routing": {"answer_generation": "qwen-plus", "intent_recognition": "qwen-turbo"},
          "cost_daily_limit_rmb": 1000
        }'::jsonb)
    """)


def downgrade() -> None:
    op.drop_table("qa_settings")
    op.drop_index("idx_feedbacks_log", table_name="feedbacks")
    op.drop_table("feedbacks")
    op.drop_index("idx_qa_logs_created", table_name="qa_logs")
    op.drop_index("idx_qa_logs_session", table_name="qa_logs")
    op.drop_index("idx_qa_logs_user_created", table_name="qa_logs")
    op.drop_table("qa_logs")
    op.drop_index("idx_documents_file_hash", table_name="documents")
    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_table("documents")
    op.drop_index("idx_users_role", table_name="users")
    op.drop_table("users")
```

- [ ] **Step 6: 跑测试**

```bash
pip install psycopg[binary]   # sync driver for alembic
pytest tests/integration/test_migrations.py -v -m integration
```

预期：2 passed（约 30 秒，testcontainer 冷启动）。

- [ ] **Step 7: Commit**

```bash
git add backend/alembic.ini backend/migrations/ backend/tests/integration/
git commit -m "feat(db): alembic initial migration with 5 tables and default qa_settings"
```

---

## Task 7: Redis 客户端 + healthz 联动

**Files:**
- Create: `backend/app/storage/redis_client.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_redis.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_redis.py
import pytest
from app.storage.redis_client import get_redis, close_redis

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_redis_ping(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    r = get_redis()
    assert await r.ping() is True
    await close_redis()

@pytest.mark.asyncio
async def test_redis_setex_and_get(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    r = get_redis()
    await r.setex("k1", 10, "v1")
    assert await r.get("k1") == "v1"
    await close_redis()
```

在 `tests/integration/conftest.py` 追加：

```python
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as r:
        yield r

@pytest.fixture(scope="session")
def redis_url(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/integration/test_redis.py -v -m integration
```

- [ ] **Step 3: 实现 `app/storage/redis_client.py`**

```python
import redis.asyncio as redis
from app.config import get_settings

_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_timeout=3,
        )
    return _client

async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
```

- [ ] **Step 4: 把 /healthz 升级为深度健康检查**

修改 `backend/app/main.py`：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.config import get_settings
from app.logging_conf import configure_logging, get_logger
from app.storage.pg import get_engine, dispose_engine
from app.storage.redis_client import get_redis, close_redis

settings = get_settings()
configure_logging(level=settings.log_level, env=settings.environment)
log = get_logger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("app_startup", env=settings.environment)
    yield
    await dispose_engine()
    await close_redis()
    log.info("app_shutdown")

app = FastAPI(title="Enterprise QA MVP", version="0.1.0", lifespan=lifespan)

async def _check_pg() -> str:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("pg_unhealthy", error=str(exc))
        return "down"

async def _check_redis() -> str:
    try:
        return "ok" if await get_redis().ping() else "down"
    except Exception as exc:  # noqa: BLE001
        log.warning("redis_unhealthy", error=str(exc))
        return "down"

@app.get("/healthz")
async def healthz() -> dict:
    deps = {"pg": await _check_pg(), "redis": await _check_redis(), "es": "pending"}
    overall = "ok" if all(v == "ok" or v == "pending" for v in deps.values()) else "degraded"
    return {"status": overall, "deps": deps, "env": settings.environment}
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/integration/test_redis.py -v -m integration
pytest tests/unit/test_healthz.py -v
```

Unit test 对 `_check_pg/_check_redis` 走兜底路径（没依赖时返回 "down"），需要相应调整 unit test：

```python
# test_healthz.py 补一条 deps degraded 用例
@pytest.mark.asyncio
async def test_healthz_returns_degraded_without_backends():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deps"]["pg"] in ("ok", "down")
    assert body["deps"]["redis"] in ("ok", "down")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/storage/redis_client.py backend/app/main.py \
        backend/tests/integration/test_redis.py backend/tests/integration/conftest.py \
        backend/tests/unit/test_healthz.py
git commit -m "feat(backend): add async redis client and deep healthz probes"
```

---

## Task 8: Elasticsearch 客户端 + qa_chunks 索引 init 脚本

**Files:**
- Create: `backend/app/storage/es_client.py`
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/init_es.py`
- Modify: `backend/app/main.py`（_check_es）
- Create: `backend/tests/integration/test_es_index.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_es_index.py
import pytest
from app.storage.es_client import get_es, close_es

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_es_ping(es_url, monkeypatch):
    monkeypatch.setenv("ES_URL", es_url)
    client = get_es()
    info = await client.info()
    assert "version" in info
    await close_es()

@pytest.mark.asyncio
async def test_init_es_creates_qa_chunks(es_url, monkeypatch):
    monkeypatch.setenv("ES_URL", es_url)
    from backend.scripts.init_es import ensure_index
    await ensure_index()
    client = get_es()
    mapping = await client.indices.get_mapping(index="qa_chunks")
    props = mapping["qa_chunks"]["mappings"]["properties"]
    assert props["embedding"]["type"] == "dense_vector"
    assert props["embedding"]["dims"] == 1024
    assert props["content"]["analyzer"] == "ik_smart_plus"
    assert props["permission_level"]["type"] == "keyword"
    await close_es()
```

`tests/integration/conftest.py` 追加：

```python
from testcontainers.elasticsearch import ElasticSearchContainer

@pytest.fixture(scope="session")
def es_container():
    # IK 镜像镜像内置；仅测试基础 mapping
    with ElasticSearchContainer("elasticsearch:8.11.0") as es:
        yield es

@pytest.fixture(scope="session")
def es_url(es_container):
    return es_container.get_url()
```

注意：ElasticSearchContainer 默认无 IK 分词。集成测试里对 `ik_smart_plus` 断言在本地失败，改为在 `infinilabs/elasticsearch-ik:8.11` 镜像上跑。用环境变量切换：

```python
from testcontainers.core.container import DockerContainer

@pytest.fixture(scope="session")
def es_container():
    container = (
        DockerContainer("infinilabs/elasticsearch-ik:8.11.0")
        .with_env("discovery.type", "single-node")
        .with_env("xpack.security.enabled", "false")
        .with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
        .with_exposed_ports(9200)
    )
    container.start()
    yield container
    container.stop()

@pytest.fixture(scope="session")
def es_url(es_container):
    host = es_container.get_container_host_ip()
    port = es_container.get_exposed_port(9200)
    return f"http://{host}:{port}"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/integration/test_es_index.py -v -m integration
```

预期：ModuleNotFoundError 或 connection refused。

- [ ] **Step 3: 实现 `app/storage/es_client.py`**

```python
from elasticsearch import AsyncElasticsearch
from app.config import get_settings

_client: AsyncElasticsearch | None = None

def get_es() -> AsyncElasticsearch:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncElasticsearch(
            hosts=[settings.es_url],
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
    return _client

async def close_es() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
```

- [ ] **Step 4: 实现 `scripts/init_es.py`（严格对齐 Spec §3.2）**

```python
"""Create qa_chunks index with IK analyzer + 1024-dim dense_vector."""
import asyncio
import sys
from app.storage.es_client import get_es, close_es

INDEX_NAME = "qa_chunks"
INDEX_BODY = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ik_smart_plus": {"type": "custom", "tokenizer": "ik_smart"}
            }
        },
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "doc_name": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text", "analyzer": "ik_smart_plus"},
            "section": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": 1024,
                "similarity": "cosine",
                "index": True,
            },
            "permission_level": {"type": "keyword"},
            "department": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "updated_at": {"type": "date"},
            "content_hash": {"type": "keyword"},
        }
    },
}

async def ensure_index() -> None:
    es = get_es()
    exists = await es.indices.exists(index=INDEX_NAME)
    if exists:
        print(f"[init_es] index '{INDEX_NAME}' already exists — skip")
        return
    await es.indices.create(index=INDEX_NAME, body=INDEX_BODY)
    print(f"[init_es] index '{INDEX_NAME}' created")

async def main() -> None:
    try:
        await ensure_index()
    finally:
        await close_es()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
```

- [ ] **Step 5: 把 healthz 的 ES 检查接上**

`backend/app/main.py` 追加：

```python
from app.storage.es_client import get_es, close_es

async def _check_es() -> str:
    try:
        info = await get_es().info()
        return "ok" if "version" in info else "down"
    except Exception as exc:  # noqa: BLE001
        log.warning("es_unhealthy", error=str(exc))
        return "down"

# healthz 中替换 es: "pending" 为 es: await _check_es()
```

并在 `lifespan` 关闭时 `await close_es()`。

- [ ] **Step 6: 跑测试**

```bash
pytest tests/integration/test_es_index.py -v -m integration
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/storage/es_client.py backend/scripts/ \
        backend/tests/integration/test_es_index.py backend/app/main.py \
        backend/tests/integration/conftest.py
git commit -m "feat(search): add ES async client and qa_chunks index bootstrap"
```

---

## Task 9: 前端 Vite + React + TS 脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/.dockerignore`

- [ ] **Step 1: 写 `frontend/package.json`**

```json
{
  "name": "qa-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --max-warnings 0",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "zustand": "^4.5.0",
    "@tanstack/react-query": "^5.24.0",
    "axios": "^1.6.7"
  },
  "devDependencies": {
    "@types/react": "^18.2.56",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.4",
    "tailwindcss": "^3.4.1",
    "autoprefixer": "^10.4.17",
    "postcss": "^8.4.35"
  }
}
```

- [ ] **Step 2: 写 `vite.config.ts`**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
});
```

- [ ] **Step 3: 写 `tsconfig.json` / `tsconfig.node.json`**

`tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`tsconfig.node.json`：

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: 写 Tailwind / PostCSS 配置**

`tailwind.config.js`：

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
};
```

`postcss.config.js`：

```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 5: 写入口**

`index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>企业知识库问答</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`：

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`src/App.tsx`：

```typescript
export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">企业知识库问答 MVP</h1>
        <p className="text-slate-500 mt-2">Frontend scaffold — Phase 1 OK</p>
      </div>
    </div>
  );
}
```

`src/index.css`：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
```

- [ ] **Step 6: 验证本地构建**

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

预期：`dist/` 生成 `index.html` 和 assets。

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/vite.config.ts frontend/tsconfig*.json \
        frontend/tailwind.config.js frontend/postcss.config.js \
        frontend/index.html frontend/src/ frontend/.dockerignore
git commit -m "feat(frontend): scaffold Vite + React + TS + Tailwind"
```

---

## Task 10: Docker Compose + Dockerfiles + `.env.example`

**Files:**
- Create: `.env.example`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `docker-compose.yml`

- [ ] **Step 1: 写 `.env.example`**

```env
# ===== Database =====
DATABASE_URL=postgresql+asyncpg://qa_user:qa_pass@postgres:5432/qa_db
POSTGRES_USER=qa_user
POSTGRES_PASSWORD=qa_pass
POSTGRES_DB=qa_db

# ===== Elasticsearch =====
ES_URL=http://elasticsearch:9200

# ===== Redis =====
REDIS_URL=redis://redis:6379/0

# ===== Auth =====
JWT_SECRET=change_me_to_random_32_byte_hex_string_0123456789ab
JWT_ACCESS_TTL_SECONDS=900
JWT_REFRESH_TTL_SECONDS=604800

# ===== LLM Providers (Phase 4 填充) =====
DASHSCOPE_API_KEY=
DEEPSEEK_API_KEY=

# ===== Runtime =====
DATA_DIR=/app/data
LOG_LEVEL=INFO
ENVIRONMENT=dev
```

- [ ] **Step 2: 写 `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e '.'

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
RUN mkdir -p /app/data/{sessions,tasks,uploads,backups,cache}
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`backend/.dockerignore`：

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
migrations/__pycache__/
data/
```

- [ ] **Step 3: 写 `frontend/Dockerfile` + `nginx.conf`**

`frontend/Dockerfile`：

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.25-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
```

`frontend/nginx.conf`：

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_buffering off;             # SSE 必须
        proxy_set_header Connection "";  # 保持长连接
        proxy_read_timeout 300s;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

`frontend/.dockerignore`：

```
node_modules/
dist/
```

- [ ] **Step 4: 写 `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - ./data/pg:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  elasticsearch:
    image: infinilabs/elasticsearch-ik:8.11.0
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    volumes:
      - ./data/es:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:9200/_cluster/health | grep -E 'green|yellow'"]
      interval: 10s
      timeout: 5s
      retries: 20

  redis:
    image: redis:7-alpine
    volumes:
      - ./data/redis:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    build: ./backend
    env_file: .env
    volumes:
      - ./backend/data:/app/data
    ports:
      - "8000:8000"
    depends_on:
      postgres: { condition: service_healthy }
      elasticsearch: { condition: service_healthy }
      redis: { condition: service_healthy }

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      backend: { condition: service_healthy }

  # ==== 可选 monitoring profile（Phase 7 启用） ====
  prometheus:
    image: prom/prometheus:v2.49.0
    profiles: ["monitoring"]
    volumes:
      - ./ops/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:10.3.0
    profiles: ["monitoring"]
    ports: ["3000:3000"]
    depends_on: [prometheus]
```

- [ ] **Step 5: 验证 compose 配置**

```bash
cp .env.example .env
docker compose config --quiet && echo "compose config OK"
docker compose build
```

- [ ] **Step 6: 冒烟启动**

```bash
docker compose up -d postgres elasticsearch redis
# 等 30 秒让 ES 起
sleep 30
docker compose ps
# 期望三者 healthy
docker compose up -d backend
sleep 10
curl -sS http://localhost:8000/healthz
# 期望 {"status":"ok","deps":{"pg":"ok","es":"ok","redis":"ok"},...}
docker compose down
```

- [ ] **Step 7: Commit**

```bash
git add .env.example backend/Dockerfile backend/.dockerignore \
        frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore \
        docker-compose.yml
git commit -m "feat(devops): docker-compose with PG/ES/Redis/backend/frontend stack"
```

---

## Task 11: `deploy.sh` + `seed_users.py` + CI workflow

**Files:**
- Create: `deploy.sh`
- Create: `backend/scripts/seed_users.py`
- Create: `backend/tests/integration/test_seed_users.py`
- Create: `.github/workflows/ci.yml`

### 11a. deploy.sh

- [ ] **Step 1: 写 `deploy.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

usage() {
  cat <<EOF
Usage: ./deploy.sh <command> [args]

Commands:
  start              docker compose up -d (no monitoring)
  stop               docker compose down
  restart            stop + start
  logs <service>     tail logs for a service (backend|frontend|postgres|...)
  ps                 show service status
  init               first-time init: alembic upgrade + init ES + seed users
  reindex            rebuild ES qa_chunks from PG source docs
  monitoring         start with monitoring profile (prometheus + grafana)
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  start)       docker compose --env-file "$ENV_FILE" up -d ;;
  stop)        docker compose --env-file "$ENV_FILE" down ;;
  restart)     docker compose --env-file "$ENV_FILE" down && docker compose --env-file "$ENV_FILE" up -d ;;
  logs)        docker compose --env-file "$ENV_FILE" logs -f "${1:-backend}" ;;
  ps)          docker compose --env-file "$ENV_FILE" ps ;;
  init)
    docker compose --env-file "$ENV_FILE" exec backend alembic upgrade head
    docker compose --env-file "$ENV_FILE" exec backend python -m scripts.init_es
    docker compose --env-file "$ENV_FILE" exec backend python -m scripts.seed_users
    ;;
  reindex)     docker compose --env-file "$ENV_FILE" exec backend python -m scripts.reindex ;;
  monitoring)  docker compose --env-file "$ENV_FILE" --profile monitoring up -d ;;
  help|--help|-h) usage ;;
  *)  echo "unknown command: $cmd"; usage; exit 1 ;;
esac
```

- [ ] **Step 2: 赋执行权限并冒烟**

```bash
chmod +x deploy.sh
./deploy.sh help
```

### 11b. seed_users.py

- [ ] **Step 3: 写失败测试**

```python
# backend/tests/integration/test_seed_users.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import bcrypt

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_seed_users_inserts_three_accounts(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from backend.scripts.seed_users import seed
    await seed()
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT username, role, permission_level, password_hash, is_active "
            "FROM users ORDER BY username"
        ))).all()
    await engine.dispose()
    names = {r[0] for r in rows}
    assert names == {"admin", "employee_demo", "guest_demo"}
    for r in rows:
        assert r[4] is True
        assert r[3].startswith("$2b$12$")  # bcrypt cost=12

@pytest.mark.asyncio
async def test_seed_users_is_idempotent(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from backend.scripts.seed_users import seed
    await seed()
    await seed()  # 再跑一次不应重复报错
    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        cnt = (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one()
    await engine.dispose()
    assert cnt == 3
```

- [ ] **Step 4: 实现 `backend/scripts/seed_users.py`**

```python
"""Seed three test accounts — admin / employee_demo / guest_demo.
Idempotent: re-running is a no-op (ON CONFLICT DO NOTHING).
"""
import asyncio
import sys
import uuid
import bcrypt
from datetime import datetime, timezone
from sqlalchemy import text
from app.storage.pg import get_engine, dispose_engine

# 默认密码仅用于开发环境；生产必须 reset。
SEED_USERS = [
    {"username": "admin",          "password": "Admin@123456",    "role": "admin",    "permission_level": "L3", "department": "IT"},
    {"username": "employee_demo",  "password": "Employee@12345",  "role": "employee", "permission_level": "L2", "department": "HR"},
    {"username": "guest_demo",     "password": "Guest@123456",    "role": "guest",    "permission_level": "L1", "department": None},
]

def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

async def seed() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for u in SEED_USERS:
            await conn.execute(
                text("""
                    INSERT INTO users
                      (user_id, username, password_hash, role, permission_level,
                       department, is_active, created_at)
                    VALUES (:uid, :un, :pw, :role, :pl, :dept, TRUE, :now)
                    ON CONFLICT (username) DO NOTHING
                """),
                {
                    "uid": f"u_{uuid.uuid4().hex[:8]}",
                    "un": u["username"],
                    "pw": _hash(u["password"]),
                    "role": u["role"],
                    "pl": u["permission_level"],
                    "dept": u["department"],
                    "now": datetime.now(timezone.utc),
                },
            )
    print(f"[seed_users] ensured {len(SEED_USERS)} accounts")

async def main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/integration/test_seed_users.py -v -m integration
```

### 11c. CI workflow

- [ ] **Step 6: 写 `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
    branches: [main, "phase*"]
  pull_request:
    branches: [main]

jobs:
  backend-lint-unit:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Install deps
        run: |
          pip install --upgrade pip
          pip install -e '.[dev]'
      - name: Ruff
        run: ruff check .
      - name: Mypy
        run: mypy app
      - name: Pytest unit
        env:
          DATABASE_URL: "postgresql+asyncpg://u:p@localhost/db"
          ES_URL: "http://localhost:9200"
          REDIS_URL: "redis://localhost:6379/0"
          JWT_SECRET: "x123456789012345678901234567890xx"
          ENVIRONMENT: "test"
        run: pytest tests/unit -v --cov=app --cov-report=term

  frontend-build:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm install
      - run: npm run typecheck
      - run: npm run build

  backend-integration:
    runs-on: ubuntu-latest
    needs: [backend-lint-unit]
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Install deps
        run: |
          pip install --upgrade pip
          pip install -e '.[dev]'
          pip install psycopg[binary]
      - name: Pytest integration
        run: pytest tests/integration -v -m integration
```

- [ ] **Step 7: 本地 YAML 校验**

```bash
# 可选：有 act 的话本地预演
command -v act >/dev/null && act -l || echo "act not installed; YAML syntax:"
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

- [ ] **Step 8: Commit**

```bash
git add deploy.sh backend/scripts/seed_users.py \
        backend/tests/integration/test_seed_users.py \
        .github/workflows/ci.yml
git commit -m "chore: add deploy.sh, seed_users script and CI workflow"
```

---

## Task 12: 端到端冒烟 — Phase 1 验收

不新写代码，只跑流程并勾选 DoD。如果任一项失败，退回相应 Task 重修。

- [ ] **Step 1: 清理环境**

```bash
docker compose down -v
rm -rf backend/data/pg backend/data/es backend/data/redis
```

- [ ] **Step 2: 首次启动**

```bash
cp .env.example .env
./deploy.sh start
```

- [ ] **Step 3: 等待 healthy**

```bash
for i in {1..12}; do
  state=$(docker compose ps --format json | python -c "
import json,sys
data=[json.loads(l) for l in sys.stdin if l.strip()]
print(all(d.get('Health','healthy')=='healthy' for d in data))
")
  [ "$state" = "True" ] && break
  echo "waiting... $i"
  sleep 5
done
./deploy.sh ps
```

预期：60 秒内 5 个服务全部 `healthy`（frontend 没有 depends_on healthy，但自身 wget 健康检查通过）。

- [ ] **Step 4: 首次初始化**

```bash
./deploy.sh init
```

预期输出：
- `INFO [alembic.runtime.migration] Running upgrade  -> 0001, initial schema...`
- `[init_es] index 'qa_chunks' created`
- `[seed_users] ensured 3 accounts`

- [ ] **Step 5: 校验每条 DoD**

```bash
# 1. /healthz 深度检查
curl -sS http://localhost:8000/healthz | python -m json.tool
# 期望全 ok

# 2. PG 表
docker compose exec postgres psql -U qa_user -d qa_db -c "\dt"
# 期望看到 users, documents, qa_logs, feedbacks, qa_settings

# 3. qa_settings 默认行
docker compose exec postgres psql -U qa_user -d qa_db -c "SELECT config FROM qa_settings;"

# 4. ES mapping
curl -sS http://localhost:9200/qa_chunks/_mapping | python -m json.tool

# 5. 种子账户
docker compose exec postgres psql -U qa_user -d qa_db -c "SELECT username, role, permission_level FROM users;"

# 6. 前端可访问
curl -sS -I http://localhost/
# 期望 HTTP 200
```

- [ ] **Step 6: Commit 收尾说明**

```bash
# 无代码修改，只记录验收
git commit --allow-empty -m "chore(phase1): acceptance — foundation ready for Phase 2"
```

- [ ] **Step 7: 合并到 main**

```bash
git checkout main
git merge --no-ff phase1-foundation
git tag -a v0.1.0-phase1 -m "Phase 1 foundation complete"
```

（push 操作由用户手动执行，不代为推送）

---

## Self-Review（已执行）

1. **Spec 覆盖扫描**：
   - Spec §1.3 目录结构 → Task 1/4/5/9/10 全部落地
   - Spec §4.4 DDL 5 张表 → Task 5/6 完全对齐
   - Spec §4.5 Redis Key 规范 → Task 7 只建客户端，Key 规范由 Phase 2/4 实际写入校验
   - Spec §3.2 ES mapping → Task 8 完整落地
   - Spec §5.6 bcrypt cost=12 → Task 11b 单测锁住 `$2b$12$`
   - Spec §7.5 deploy.sh → Task 11a 覆盖 start/stop/logs/ps/init/reindex/monitoring
   - Spec §7.3 CI 流水线 → Task 11c 覆盖 ruff/mypy/pytest unit+integration/frontend build
   - Spec §7.1 structlog → Task 3
   - 尚未覆盖：prometheus instrumentator（Phase 5 接 API 时加）、`scripts/reindex.py` 空壳留给 Phase 3

2. **Placeholder 扫描**：未出现 TBD / 模糊 "add error handling" 等。所有代码块给出可执行实现，所有命令给出期望输出。

3. **类型一致性**：
   - Settings 字段命名（`database_url` / `es_url` / `redis_url` / `jwt_secret`）在 config、pg、redis_client、es_client 中一致
   - Models 表名（`users` / `documents` / `qa_logs` / `feedbacks` / `qa_settings`）与 migration 0001 一致
   - `get_engine` / `get_redis` / `get_es` / `close_*` / `dispose_engine` 命名风格统一
   - `ik_smart_plus` analyzer 名在 init_es.py 与 Spec §3.2 一致

4. **潜在阻塞点**：
   - `infinilabs/elasticsearch-ik:8.11.0` 镜像国内拉取可能慢，需要在 README 标注镜像源
   - testcontainers 需要 Docker-in-Docker 或 host docker.sock，CI runner 已内置
   - `python -m scripts.init_es` 需要 `backend/scripts/__init__.py`（Task 8 Step 3 已要求）

---

## Execution Handoff

Plan 已写入 `docs/superpowers/plans/2026-04-23-phase1-foundation.md`，共 12 个 Task，TDD 粒度到 2-5 分钟每步，全部给出完整代码与命令。

下一步你挑执行方式：

1. **Subagent-Driven（推荐）** — 我按 `superpowers:subagent-driven-development` 规范，每个 Task 派一个 fresh subagent 实现 + 两阶段 review，Task 间回报进展。
2. **Inline Execution** — 用 `superpowers:executing-plans` 在当前会话里串行执行，Task 批次间我停下来给 checkpoint。

我的建议：Phase 1 单 Task 之间耦合低（每个 Task 独立可验），**Subagent-Driven 收益最大**。但如果你想坐在边上看执行细节，Inline 更直观。
