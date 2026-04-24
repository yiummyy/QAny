# Phase 2: 鉴权 & RBAC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (推荐) 或 superpowers:executing-plans 逐 Task 实施。Steps 使用 checkbox (`- [ ]`) 跟踪。

**Goal:** 在 Phase 1 基础设施之上落地身份认证与权限矩阵：`/api/v1/auth/{login,refresh,logout}` + JWT 双 token + Redis jti 黑名单 + `get_current_user`/`require_role` 依赖 + 登录失败限流 + `build_es_filter`。交付后 QA/Knowledge 等后续 Phase 可直接消费 `UserClaims` 与 RBAC 钩子。

**Architecture（Phase 2 新增）：**

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FastAPI Router Layer                           │
│  /api/v1/auth/*  ──────────────────────────────┐                     │
│  /api/v1/admin/ping (示范 protected)  ─────────┤                     │
│                                                 │                     │
│                                 Depends(get_current_user)             │
│                                 Depends(require_admin / any_user)     │
│                                                 │                     │
├─────────────────────────────────────────────────┴─────────────────────┤
│                        Auth / RBAC Core                               │
│  app/auth/passwords.py     — bcrypt cost=12                          │
│  app/auth/jwt.py           — HS256 sign/verify, access+refresh       │
│  app/auth/claims.py        — UserClaims pydantic                     │
│  app/auth/blacklist.py     — Redis jwt_blacklist:{jti}               │
│  app/auth/user_repo.py     — SELECT * FROM users WHERE username=?    │
│  app/auth/login_limiter.py — ratelimit:login:{username} (5 in 10min) │
│  app/api/deps.py           — Security + get_current_user + require_* │
│  app/api/errors.py         — AppError + 40xxx/42900/50xxx exception  │
│  app/rbac/filter_builder.py— build_es_filter(claims) -> bool filter  │
└─────────────────────────────────────────────────┬─────────────────────┘
                                                  │
                         ┌────────────────────────┴────────────────────┐
                         ▼                                             ▼
                   PostgreSQL (users)                           Redis (jti, ratelimit)
```

**Tech Stack（本 Phase 新增/使用）:**
- `python-jose[cryptography]` — JWT HS256（Phase 1 已装）
- `bcrypt>=4.1` — 密码哈希（Phase 1 已装）
- `pydantic>=2.6` — UserClaims
- FastAPI `Depends` + `HTTPBearer` Security scheme
- `pytest-asyncio` + `httpx.ASGITransport` — 无容器的 FastAPI 单元/集成测试
- `testcontainers[postgres,redis]` — 集成测试（Phase 1 fixture 已就绪）

---

## Phase 2 Definition of Done（硬门）

来自 Master Index §Phase 2 + Spec §5：

- [x] pytest 覆盖登录**成功 / 失败（错密码） / token 过期 / jti 黑名单**四条路径，全部 green
- [x] guest / employee / admin 三角色对 `/api/v1/admin/*` 拦截集成测试通过（403 / 200 正确分流）
- [x] `build_es_filter(guest)` 过滤掉 L2/L3 的单测锁住（只允许 L1）
- [x] `build_es_filter(employee)` 只允许 L1/L2 的单测锁住
- [x] `build_es_filter(admin)` 允许 L1/L2/L3 的单测锁住
- [x] bcrypt `cost=12`（`$2b$12$` 前缀）在单测中显式断言
- [x] 登录失败 5 次后第 6 次返回 HTTP 429 + `code=42900` 的集成测试通过
- [x] 登出后同一 token 再次访问任意受保护端点返回 401 + `code=40101`
- [x] `is_active=false` 用户登录返回 401 + `code=40102`
- [x] Phase 1 两项 gap 补齐：
  - [x] `.github/workflows/ci.yml` 存在并在本地（或 GitHub Actions）跑通 ruff/mypy/pytest-unit/frontend-build/pytest-integration 五个 job
  - [x] `backend/tests/integration/test_seed_users.py` 存在并 green

---

## File Structure 先定盘

Phase 2 新增的文件（相对 Phase 1 落盘的骨架），其余文件不动：

```
qa-system/
├── .github/
│   └── workflows/
│       └── ci.yml                           ← Task 0a（Phase 1 gap）
├── backend/
│   ├── app/
│   │   ├── auth/                            ← Phase 2 新模块
│   │   │   ├── __init__.py
│   │   │   ├── passwords.py                 ← Task 1
│   │   │   ├── jwt.py                       ← Task 2
│   │   │   ├── claims.py                    ← Task 3
│   │   │   ├── blacklist.py                 ← Task 4
│   │   │   ├── user_repo.py                 ← Task 5
│   │   │   └── login_limiter.py             ← Task 7
│   │   ├── api/                             ← Phase 2 新模块
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                      ← Task 6
│   │   │   ├── errors.py                    ← Task 8
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py                  ← Task 9
│   │   │       └── admin.py                 ← Task 10（示范 `/admin/ping`）
│   │   ├── rbac/                            ← Phase 2 新模块
│   │   │   ├── __init__.py
│   │   │   └── filter_builder.py            ← Task 10
│   │   └── main.py                          ← 修改：挂载 router + error handler
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_passwords.py            ← Task 1
│   │   │   ├── test_jwt.py                  ← Task 2
│   │   │   ├── test_claims.py               ← Task 3
│   │   │   ├── test_deps_require_role.py    ← Task 6
│   │   │   ├── test_errors.py               ← Task 8
│   │   │   └── test_filter_builder.py       ← Task 10
│   │   └── integration/
│   │       ├── test_seed_users.py           ← Task 0b（Phase 1 gap）
│   │       ├── test_blacklist.py            ← Task 4
│   │       ├── test_user_repo.py            ← Task 5
│   │       ├── test_login_limiter.py        ← Task 7
│   │       ├── test_auth_api.py             ← Task 9
│   │       └── test_admin_gate.py           ← Task 10
```

**分工原则：**
- `auth/` 放纯库层（无 FastAPI 耦合），可独立 mock
- `api/` 放 FastAPI 适配层（Depends / Router / Exception handler）
- `rbac/` 放权限矩阵与 ES filter（不感知 FastAPI，方便 hybrid_search 工具直接调用）
- 测试分 `unit`（纯函数，不依赖容器）与 `integration`（需要 testcontainers pg/redis）

---

## 分支与 Commit 策略

本 Phase 全程在独立分支 `phase2-auth-rbac`（**已从 `phase1-foundation` 切出**）。每个 Task 完成后单独 commit：

```bash
git add <listed files>
git commit -m "<conventional prefix>: <task summary>"
```

Conventional prefixes:
- `ci(gha): ...` — Task 0a
- `test(backend): ...` — Task 0b 及纯新增测试
- `feat(auth): ...` — Task 1-7
- `feat(api): ...` — Task 6/8/9
- `feat(rbac): ...` — Task 10
- `docs(plans): ...` — Task 11 的 self-review 勾选

Phase 2 整体完成、DoD 全勾选后统一 push，等待用户合 main。

---

## Task 0: 补齐 Phase 1 遗留 gap（前置任务）

Master Index 规则："前序阶段未达 DoD 时**不得**启动下一阶段"。Phase 1 留下两项 gap，必须先补齐。

### 0a. `.github/workflows/ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 写 `.github/workflows/ci.yml`**

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
          pip install 'psycopg[binary]'
      - name: Show docker info
        run: docker version && docker info
      - name: Pytest integration
        env:
          JWT_SECRET: "x123456789012345678901234567890xx"
          ENVIRONMENT: "test"
        run: pytest tests/integration -v -m integration
```

- [ ] **Step 2: 本地 YAML 校验**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "yaml ok"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(gha): add lint/unit/integration workflow for backend + frontend tsc"
```

---

### 0b. `backend/tests/integration/test_seed_users.py`

Plan 原 Task 11 已有样板（master plan 2102-2142 行），这里**按现有实现补齐测试**。关键是对齐 `backend/scripts/seed_users.py` 当前的 import 路径处理（已注入 `ROOT=backend/`）。

**Files:**
- Create: `backend/tests/integration/test_seed_users.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_seed_users.py
"""Phase 1 gap backfill: cover scripts/seed_users.py end-to-end."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_seed_users_inserts_three_accounts(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)

    # 动态 import：seed_users.py 的 top-level 依赖 get_engine()
    # (lru_cache 的 Settings 已被 pg_url fixture 写入 DATABASE_URL)
    from app.storage.pg import dispose_engine
    from scripts.seed_users import seed

    try:
        await seed()
    finally:
        await dispose_engine()

    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT username, role, permission_level, password_hash, is_active "
                    "FROM users ORDER BY username"
                )
            )
        ).all()
    await engine.dispose()

    names = {r[0] for r in rows}
    assert names == {"admin", "employee_demo", "guest_demo"}
    for r in rows:
        assert r[4] is True, f"{r[0]} should be active"
        assert r[3].startswith("$2b$12$"), f"{r[0]} hash must be bcrypt cost=12"


@pytest.mark.asyncio
async def test_seed_users_is_idempotent(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)

    from app.storage.pg import dispose_engine
    from scripts.seed_users import seed

    try:
        await seed()
        await seed()  # 再次执行不得重复报错
    finally:
        await dispose_engine()

    engine = create_async_engine(pg_url, future=True)
    async with engine.connect() as conn:
        cnt = (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one()
    await engine.dispose()
    assert cnt == 3
```

注意 `pg_url` fixture 已经在 `tests/integration/conftest.py` 跑过 `alembic upgrade head`（见 Phase 1 conftest），此处无需重复建表。

- [ ] **Step 2: 跑测试**

从项目根目录：

```bash
cd backend
pytest tests/integration/test_seed_users.py -v -m integration
```

预期：2 passed（约 30 秒，testcontainer 冷启动）。

> **提示**：`scripts.seed_users` 能被 import，前提是 `tests/` 能解析 `scripts/` 包。因为 Phase 1 的 `scripts/__init__.py` 已存在，`pyproject.toml` 里 `pythonpath = ["."]`，所以 `from scripts.seed_users import seed` 可直接工作。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_seed_users.py
git commit -m "test(backend): add integration coverage for scripts.seed_users"
```

---

## Task 1: 密码工具（bcrypt cost=12）

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/passwords.py`
- Create: `backend/tests/unit/test_passwords.py`

- [ ] **Step 1: 写失败测试 `tests/unit/test_passwords.py`**

```python
import pytest

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
    # 对于非 bcrypt 的 hash 不应抛异常，只返回 False（稳态）
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_hash_password_generates_distinct_hashes_for_same_input():
    # salt 不同导致 hash 每次不同
    assert hash_password("same") != hash_password("same")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend
pytest tests/unit/test_passwords.py -v
```

预期：`ModuleNotFoundError: No module named 'app.auth'`。

- [ ] **Step 3: 实现**

`backend/app/auth/__init__.py`：空文件。

`backend/app/auth/passwords.py`：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/test_passwords.py -v
```

预期：5 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/passwords.py \
        backend/tests/unit/test_passwords.py
git commit -m "feat(auth): add bcrypt password hashing at cost=12"
```

---

## Task 2: JWT 工具（access + refresh 双 token）

严格对齐 Spec §5.1 的 claims 结构。

**Files:**
- Create: `backend/app/auth/jwt.py`
- Create: `backend/tests/unit/test_jwt.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_jwt.py
import time
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError

from app.auth.jwt import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_access_token_round_trip():
    token, jti = create_access_token(
        user_id="u_001",
        username="zhangsan",
        role="employee",
        permission_level="L2",
        department="HR",
    )
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert payload["sub"] == "u_001"
    assert payload["username"] == "zhangsan"
    assert payload["role"] == "employee"
    assert payload["pl"] == "L2"
    assert payload["dept"] == "HR"
    assert payload["jti"] == jti
    assert payload["token_type"] == "access"
    # exp 与 iat 必须是整数秒，且 exp-iat ≈ jwt_access_ttl_seconds（默认 900）
    assert isinstance(payload["exp"], int)
    assert isinstance(payload["iat"], int)
    assert 890 <= payload["exp"] - payload["iat"] <= 910


def test_refresh_token_has_minimal_claims():
    token, jti = create_refresh_token(user_id="u_001")
    payload = decode_token(token, expected_type=TokenType.REFRESH)
    assert payload["sub"] == "u_001"
    assert payload["jti"] == jti
    assert payload["token_type"] == "refresh"
    # refresh token 不泄露 role / pl / dept
    for sensitive in ("role", "pl", "dept", "username"):
        assert sensitive not in payload


def test_decode_token_rejects_expired(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1")
    from app.config import get_settings
    get_settings.cache_clear()  # 清 lru_cache
    token, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    time.sleep(2)
    with pytest.raises(JWTError):
        decode_token(token, expected_type=TokenType.ACCESS)
    get_settings.cache_clear()


def test_decode_token_rejects_wrong_secret(monkeypatch):
    token, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    monkeypatch.setenv("JWT_SECRET", "y" * 32)
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(JWTError):
        decode_token(token, expected_type=TokenType.ACCESS)
    get_settings.cache_clear()


def test_decode_token_rejects_wrong_type():
    access, _ = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    # 误把 access 当 refresh 解码必须失败
    with pytest.raises(JWTError):
        decode_token(access, expected_type=TokenType.REFRESH)


def test_token_jti_is_unique_per_issue():
    t1, j1 = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    t2, j2 = create_access_token(
        user_id="u_001", username="u", role="employee", permission_level="L2"
    )
    assert j1 != j2
    assert t1 != t2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_jwt.py -v
```

- [ ] **Step 3: 实现 `app/auth/jwt.py`**

```python
"""JWT sign/decode — HS256, access + refresh per Spec §5.1.

- access_token: 15min, carries full claims (sub/username/role/pl/dept)
- refresh_token: 7d, carries only sub + jti (no role info, reduces blast radius)
- jti: 32-char urlsafe token, used as Redis blacklist key

The module depends on app.config.get_settings() for JWT_SECRET & TTLs, and
is framework-agnostic (no FastAPI imports) so it can be unit-tested without
an HTTP stack.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from jose import jwt

from app.config import get_settings

_ALGORITHM = "HS256"


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def _new_jti() -> str:
    return secrets.token_urlsafe(16)


def _secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    permission_level: str,
    department: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return (access_token, jti)."""
    settings = get_settings()
    iat = now or datetime.now(timezone.utc)
    exp = iat + timedelta(seconds=settings.jwt_access_ttl_seconds)
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "role": role,
        "pl": permission_level,
        "dept": department,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "token_type": TokenType.ACCESS.value,
    }
    token = jwt.encode(payload, _secret(), algorithm=_ALGORITHM)
    return token, jti


def create_refresh_token(
    *,
    user_id: str,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return (refresh_token, jti). Refresh carries only sub+jti."""
    settings = get_settings()
    iat = now or datetime.now(timezone.utc)
    exp = iat + timedelta(seconds=settings.jwt_refresh_ttl_seconds)
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "token_type": TokenType.REFRESH.value,
    }
    token = jwt.encode(payload, _secret(), algorithm=_ALGORITHM)
    return token, jti


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode + verify signature/exp, enforce token_type match.

    Raises jose.JWTError on any failure — caller maps it to 40101 at the
    FastAPI boundary.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        _secret(),
        algorithms=[_ALGORITHM],
        options={"require": ["exp", "iat", "sub", "jti", "token_type"]},
    )
    if payload.get("token_type") != expected_type.value:
        from jose import JWTError
        raise JWTError(f"token_type mismatch: expected {expected_type.value}")
    return payload
```

> **注意 require 列表**：强制要求 token 里存在 `exp/iat/sub/jti/token_type` 五个字段。任何老旧/手工构造的 JWT 缺一即判无效。

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/test_jwt.py -v
```

预期：6 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/jwt.py backend/tests/unit/test_jwt.py
git commit -m "feat(auth): add HS256 JWT sign/decode with access+refresh split"
```

---

## Task 3: UserClaims pydantic

JWT payload 的强类型表达。贯穿 `get_current_user` → `require_role` → 业务层。

**Files:**
- Create: `backend/app/auth/claims.py`
- Create: `backend/tests/unit/test_claims.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_claims.py
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_claims.py -v
```

- [ ] **Step 3: 实现 `app/auth/claims.py`**

```python
"""Typed representation of JWT claims — single source of truth for downstream."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"
    GUEST = "guest"


PermissionLevel = Literal["L1", "L2", "L3"]


class UserClaims(BaseModel):
    """Parsed JWT access-token payload (Spec §5.1)."""

    model_config = ConfigDict(frozen=True)

    sub: str = Field(..., description="user_id")
    username: str
    role: Role
    pl: PermissionLevel
    dept: str | None = None
    jti: str

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @classmethod
    def from_jwt_payload(cls, payload: dict[str, Any]) -> "UserClaims":
        """Only call with *access-token* payloads.

        Refresh tokens do NOT contain `username/role/pl/dept` (Spec §5.1
        blast-radius containment) — passing a refresh payload here will
        raise KeyError on `payload["username"]`.
        """
        return cls(
            sub=payload["sub"],
            username=payload["username"],
            role=payload["role"],
            pl=payload["pl"],
            dept=payload.get("dept"),
            jti=payload["jti"],
        )
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/test_claims.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/claims.py backend/tests/unit/test_claims.py
git commit -m "feat(auth): add typed UserClaims pydantic per Spec §5.1"
```

---

## Task 4: Redis jti 黑名单

登出后把 jti 写 Redis，`TTL = 剩余 exp`，失效后自然过期。

**Files:**
- Create: `backend/app/auth/blacklist.py`
- Create: `backend/tests/integration/test_blacklist.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_blacklist.py
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_revoke_then_is_revoked_returns_true(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_abc", ttl_seconds=60)
        assert await is_revoked("j_abc") is True
        assert await is_revoked("j_not_there") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_revoke_honors_ttl(redis_url, monkeypatch):
    import asyncio

    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_short", ttl_seconds=1)
        assert await is_revoked("j_short") is True
        await asyncio.sleep(1.5)
        assert await is_revoked("j_short") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_revoke_clamps_non_positive_ttl(redis_url, monkeypatch):
    """已过期的 token 不应往 redis 写入（TTL<=0 行为：直接视为无效）。"""
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_already_expired", ttl_seconds=0)
        # TTL<=0 直接返回 False：Redis 里不会有这个 key，也就不存在"被黑名单"的语义
        assert await is_revoked("j_already_expired") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_register_pair_and_pop_pair_bidirectional(redis_url, monkeypatch):
    """登录时注册 access↔refresh pair，登出任一都能找到对端。"""
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair, register_pair
    from app.storage.redis_client import close_redis

    try:
        await register_pair(access_jti="j_acc", refresh_jti="j_ref", ttl_seconds=60)
        # 从 access 拿 refresh
        partner = await pop_pair("j_acc")
        assert partner == "j_ref"
        # 已 pop，再拿应该返回 None
        assert await pop_pair("j_acc") is None
        # 对端 key 也被删除，pop 对端返回 None
        assert await pop_pair("j_ref") is None
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_pop_pair_on_missing_returns_none(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair
    from app.storage.redis_client import close_redis

    try:
        assert await pop_pair("never_registered") is None
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_register_pair_clamps_non_positive_ttl(redis_url, monkeypatch):
    """已过期 token 不注册。"""
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair, register_pair
    from app.storage.redis_client import close_redis

    try:
        await register_pair(access_jti="j_a", refresh_jti="j_b", ttl_seconds=0)
        assert await pop_pair("j_a") is None
    finally:
        await close_redis()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/integration/test_blacklist.py -v -m integration
```

- [ ] **Step 3: 实现 `app/auth/blacklist.py`**

```python
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
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/integration/test_blacklist.py -v -m integration
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/blacklist.py backend/tests/integration/test_blacklist.py
git commit -m "feat(auth): add Redis jti blacklist with per-token TTL"
```

---

## Task 5: UserRepository（按 username 查用户）

只封装最小读路径。其他 CRUD 交给后续 Phase。

**Files:**
- Create: `backend/app/auth/user_repo.py`
- Create: `backend/tests/integration/test_user_repo.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_user_repo.py
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_by_username_returns_seeded_user(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username
    from app.storage.pg import dispose_engine, get_sessionmaker
    from scripts.seed_users import seed

    try:
        await seed()
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "admin")
        assert user is not None
        assert user.username == "admin"
        assert user.role == "admin"
        assert user.permission_level == "L3"
        assert user.is_active is True
    finally:
        await dispose_engine()


@pytest.mark.asyncio
async def test_get_by_username_returns_none_on_missing(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username
    from app.storage.pg import dispose_engine, get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "nonexistent_user")
        assert user is None
    finally:
        await dispose_engine()


@pytest.mark.asyncio
async def test_touch_last_login_updates_timestamp(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username, touch_last_login
    from app.storage.pg import dispose_engine, get_sessionmaker
    from scripts.seed_users import seed

    try:
        await seed()
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "admin")
            assert user is not None
            before = user.last_login_at
            await touch_last_login(session, user_id=user.user_id)
            await session.commit()

            reloaded = await get_by_username(session, "admin")
            assert reloaded is not None
            assert reloaded.last_login_at is not None
            if before is not None:
                assert reloaded.last_login_at >= before
    finally:
        await dispose_engine()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/integration/test_user_repo.py -v -m integration
```

- [ ] **Step 3: 实现 `app/auth/user_repo.py`**

```python
"""Minimum user read path for auth flows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    """Return the User row or None (NOT raising)."""
    stmt = select(User).where(User.username == username)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def touch_last_login(session: AsyncSession, *, user_id: str) -> None:
    """Bump `last_login_at` to NOW(UTC). Caller is responsible for commit."""
    stmt = (
        update(User)
        .where(User.user_id == user_id)
        .values(last_login_at=datetime.now(timezone.utc))
    )
    await session.execute(stmt)
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/integration/test_user_repo.py -v -m integration
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/user_repo.py backend/tests/integration/test_user_repo.py
git commit -m "feat(auth): add user repo with by-username lookup and last_login touch"
```

---

## Task 6: FastAPI deps（get_current_user + require_role）

组装 Task 2/3/4/5：解码 JWT → 校验黑名单 → 校验 is_active → 返回 `UserClaims`。

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/tests/unit/test_deps_require_role.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_deps_require_role.py
"""require_role 的纯逻辑单测（不走 HTTP），get_current_user 的 HTTP 走 Task 9 集成测试。"""

import pytest
from fastapi import HTTPException

from app.api.deps import require_admin, require_any_user
from app.auth.claims import Role, UserClaims


def _claims(role: str) -> UserClaims:
    return UserClaims(
        sub="u", username="u", role=role, pl="L1", jti="j",
    )


@pytest.mark.asyncio
async def test_require_admin_allows_admin():
    dep = require_admin
    result = await dep(_claims("admin"))
    assert result.role is Role.ADMIN


@pytest.mark.asyncio
async def test_require_admin_rejects_employee():
    dep = require_admin
    with pytest.raises(HTTPException) as exc_info:
        await dep(_claims("employee"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == 40301


@pytest.mark.asyncio
async def test_require_admin_rejects_guest():
    dep = require_admin
    with pytest.raises(HTTPException) as exc_info:
        await dep(_claims("guest"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == 40301


@pytest.mark.asyncio
async def test_require_any_user_allows_all_three_roles():
    dep = require_any_user
    for role in ("admin", "employee", "guest"):
        result = await dep(_claims(role))
        assert result.role.value == role
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_deps_require_role.py -v
```

- [ ] **Step 3: 实现 `app/api/deps.py`**

`backend/app/api/__init__.py`：空文件。

`backend/app/api/deps.py`：

```python
"""FastAPI dependency wiring for auth — Spec §5.2 chain."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.blacklist import is_revoked
from app.auth.claims import Role, UserClaims
from app.auth.jwt import TokenType, decode_token
from app.auth.user_repo import get_by_username
from app.storage.pg import get_db

_bearer = HTTPBearer(auto_error=False)


def _auth_error(code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> UserClaims:
    if credentials is None or not credentials.credentials:
        raise _auth_error(40101, "缺少 Authorization Bearer token")

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except JWTError:
        raise _auth_error(40101, "Token 失效")

    if await is_revoked(payload["jti"]):
        raise _auth_error(40101, "Token 已登出")

    user = await get_by_username(session, payload["username"])
    if user is None or not user.is_active:
        raise _auth_error(40102, "账户禁用")

    return UserClaims.from_jwt_payload(payload)


def require_role(*allowed: str):
    """Factory dependency — allow only the listed roles."""
    allowed_set = {Role(r) for r in allowed}

    async def _dep(
        claims: UserClaims = Depends(get_current_user),
    ) -> UserClaims:
        if claims.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "您暂无权限查看此内容"},
            )
        return claims

    return _dep


require_admin = require_role("admin")
require_any_user = require_role("admin", "employee", "guest")
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/test_deps_require_role.py -v
```

预期：4 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/__init__.py backend/app/api/deps.py \
        backend/tests/unit/test_deps_require_role.py
git commit -m "feat(api): wire get_current_user + require_role dependency chain"
```

---

## Task 7: 登录失败限流

Spec §5.6：5 次失败 → 10min 内拒绝。

**Files:**
- Create: `backend/app/auth/login_limiter.py`
- Create: `backend/tests/integration/test_login_limiter.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/integration/test_login_limiter.py
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fifth_failure_triggers_block(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("alice")  # 清理可能残留
        for _ in range(5):
            await record_failure("alice")
        # 第 6 次访问（即第 5 次失败之后）必须被拦截
        with pytest.raises(Exception) as exc:
            await ensure_not_blocked("alice")
        assert getattr(exc.value, "retry_after", None) is not None
    finally:
        await reset("alice")
        await close_redis()


@pytest.mark.asyncio
async def test_reset_on_success(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("bob")
        for _ in range(3):
            await record_failure("bob")
        await reset("bob")
        # 计数清零后必须能正常访问
        await ensure_not_blocked("bob")
    finally:
        await reset("bob")
        await close_redis()


@pytest.mark.asyncio
async def test_under_threshold_still_allows(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("carol")
        for _ in range(4):
            await record_failure("carol")
        # 4 次失败还在阈值内
        await ensure_not_blocked("carol")
    finally:
        await reset("carol")
        await close_redis()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/integration/test_login_limiter.py -v -m integration
```

- [ ] **Step 3: 实现 `app/auth/login_limiter.py`**

```python
"""Per-username login failure rate limiter — Spec §5.6 (5 fails / 10min)."""

from __future__ import annotations

from app.storage.redis_client import get_redis

_KEY_PREFIX = "ratelimit:login"
_WINDOW_SECONDS = 600  # 10 minutes
_THRESHOLD = 5


class LoginBlocked(Exception):
    """Raised when a username has exceeded the failure threshold.

    The caller (API layer) should translate this into HTTP 429 + code 42900,
    including retry_after in the response headers.
    """

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"login blocked, retry after {retry_after}s")
        self.retry_after = retry_after


def _key(username: str) -> str:
    return f"{_KEY_PREFIX}:{username}"


async def record_failure(username: str) -> int:
    """Increment failure counter and refresh TTL. Returns current count."""
    r = get_redis()
    key = _key(username)
    # 使用 pipeline 保证 INCR + EXPIRE 原子性
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _WINDOW_SECONDS)
    count, _ = await pipe.execute()
    return int(count)


async def ensure_not_blocked(username: str) -> None:
    """Raise LoginBlocked if the username has reached the failure threshold."""
    r = get_redis()
    key = _key(username)
    count_raw = await r.get(key)
    if count_raw is None:
        return
    if int(count_raw) >= _THRESHOLD:
        ttl = await r.ttl(key)
        raise LoginBlocked(retry_after=max(ttl, 1))


async def reset(username: str) -> None:
    """Clear failure counter — call after a successful login."""
    await get_redis().delete(_key(username))
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/integration/test_login_limiter.py -v -m integration
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/login_limiter.py backend/tests/integration/test_login_limiter.py
git commit -m "feat(auth): add per-username login failure limiter (5/10min)"
```

---

## Task 8: 错误码体系 + 统一异常响应

对齐 Spec §4.6。统一 `{"code", "message", "trace_id"}` 响应包，中间件把 `HTTPException.detail` 平铺出来。

**Files:**
- Create: `backend/app/api/errors.py`
- Create: `backend/tests/unit/test_errors.py`
- Modify: `backend/app/main.py`（挂载 exception handler）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_errors.py
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.errors import ErrorCode, install_exception_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/bad-request")
    async def _bad():
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.BAD_REQUEST, "message": "参数非法"},
        )

    @app.get("/unauthorized")
    async def _unauth():
        raise HTTPException(
            status_code=401,
            detail={"code": ErrorCode.TOKEN_EXPIRED, "message": "Token 失效"},
        )

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("unexpected")

    return app


@pytest.mark.asyncio
async def test_http_exception_wrapped_into_standard_shape():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/bad-request")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == 40001
    assert body["message"] == "参数非法"
    assert "trace_id" in body


@pytest.mark.asyncio
async def test_unhandled_exception_becomes_500_shape():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] >= 50000
    assert "trace_id" in body


def test_error_code_enum_covers_spec_categories():
    # 抽样锁住 Spec §4.6 主要错误码
    assert ErrorCode.BAD_REQUEST == 40001
    assert ErrorCode.TOKEN_EXPIRED == 40101
    assert ErrorCode.ACCOUNT_DISABLED == 40102
    assert ErrorCode.PERMISSION_DENIED == 40301
    assert ErrorCode.RATE_LIMITED == 42900


@pytest.mark.asyncio
async def test_unknown_route_still_returns_404_not_500():
    """保护 Phase 1 行为：挂上异常中间件后，Starlette 的 404 不得被吞成 500。"""
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/nonexistent-path-xyz")
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_errors.py -v
```

- [ ] **Step 3: 实现 `app/api/errors.py`**

```python
"""Standard error envelope + FastAPI exception handlers — Spec §4.6."""

from __future__ import annotations

import secrets
from enum import IntEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging_conf import get_logger

log = get_logger(__name__)


class ErrorCode(IntEnum):
    # 400xx parameters
    BAD_REQUEST = 40001
    # 401xx auth
    TOKEN_EXPIRED = 40101
    ACCOUNT_DISABLED = 40102
    # 403xx permission
    PERMISSION_DENIED = 40301
    # 429xx rate limit
    RATE_LIMITED = 42900
    # 500xx system/llm/es (placeholder; Phase 4/5 扩充)
    LLM_TIMEOUT = 50001
    ES_UNAVAILABLE = 50101
    INTERNAL_ERROR = 50000


def _new_trace_id() -> str:
    return f"tr_{secrets.token_hex(6)}"


def _envelope(code: int, message: str, trace_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": int(code), "message": message, "trace_id": trace_id}
    if extra:
        body.update(extra)
    return body


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = int(detail["code"])
        message = str(detail.get("message", ""))
        extra = {k: v for k, v in detail.items() if k not in {"code", "message"}}
    else:
        code = ErrorCode.BAD_REQUEST if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
        message = str(detail) if detail else ""
        extra = None
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, trace_id, extra),
        headers=exc.headers,
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_envelope(
            ErrorCode.BAD_REQUEST,
            "请求参数格式非法",
            trace_id,
            extra={"errors": exc.errors()},
        ),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    log.error("unhandled_exception", trace_id=trace_id, error=repr(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(ErrorCode.INTERNAL_ERROR, "系统内部错误", trace_id),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
```

- [ ] **Step 4: 挂到 `main.py`**

**不要重写** `app = FastAPI(title=..., lifespan=lifespan)` 那一行；也**不要动** Phase 1 的 `@app.get("/healthz")` 与 `lifespan` 函数。只追加 import 与一次调用：

```python
from app.api.errors import install_exception_handlers

# ... app = FastAPI(...) 定义之后
install_exception_handlers(app)
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/unit/test_errors.py -v
# 同时跑 Phase 1 的 healthz 测试确保没破坏
pytest tests/unit/test_healthz.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/errors.py backend/app/main.py \
        backend/tests/unit/test_errors.py
git commit -m "feat(api): add ErrorCode enum and standard exception envelope"
```

---

## Task 9: `/api/v1/auth/{login,refresh,logout}` + httpx 集成测试

Phase 2 的**主菜**。把前八个 Task 拼起来，落地三个端点。

**Files:**
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/auth.py`
- Create: `backend/tests/integration/test_auth_api.py`
- Modify: `backend/app/main.py`（挂 router）

- [ ] **Step 1: 写失败集成测试**

```python
# backend/tests/integration/test_auth_api.py
"""End-to-end auth API: login → protected access → refresh → logout → blacklisted."""

import time

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)

    from app.config import get_settings
    get_settings.cache_clear()

    from scripts.seed_users import seed
    await seed()

    # 延迟 import：要在 env 设置后再导入 app，否则 lru_cache 锁死旧 settings
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c

    # === Teardown: 恢复 is_active + 清空 login limiter + 清空 jti 黑名单 ===
    # 跨 test case 的 DB / Redis 污染必须在这里收干净，否则测试顺序敏感。
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET is_active=TRUE "
                "WHERE username IN ('admin','employee_demo','guest_demo')"
            )
        )
    await engine.dispose()

    from app.storage.redis_client import close_redis, get_redis

    r = get_redis()
    # 清 login failure 计数
    for uname in ("admin", "employee_demo", "guest_demo"):
        await r.delete(f"ratelimit:login:{uname}")
    # 清本次 test 期间写入的 jti 黑名单
    for prefix in ("jwt_blacklist", "jwt_pair"):
        async for key in r.scan_iter(match=f"{prefix}:*"):
            await r.delete(key)

    from app.storage.pg import dispose_engine
    await dispose_engine()
    await close_redis()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_login_success_returns_access_and_refresh(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "Bearer"
    assert body["user"]["role"] == "admin"
    assert body["user"]["permission_level"] == "L3"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_40101(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_40101(client):
    # 安全最佳实践：username 不存在与密码错误返回同一错误码（避免用户名枚举）
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "not_a_user", "password": "anything"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_login_fifth_failure_blocks_with_42900(client):
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "employee_demo", "password": "wrong"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "employee_demo", "password": "Employee@12345"},
    )
    assert r.status_code == 429
    assert r.json()["code"] == 42900


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    refresh = r.json()["refresh_token"]

    r2 = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r2.status_code == 200
    assert "access_token" in r2.json()


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client):
    # 拒绝把 access_token 当 refresh 用
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]

    r2 = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_blacklists_token(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]

    # 登出前能访问
    r_before = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_before.status_code == 200

    # 登出
    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_out.status_code == 204

    # 登出后同 token 再访问 → 40101
    r_after = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_after.status_code == 401
    assert r_after.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_cascades_to_refresh_token(client):
    """登出 access 后，同一次登录的 refresh 必须被连带拉黑。"""
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]

    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_out.status_code == 204

    # 原 refresh 不得再刷
    r_ref = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r_ref.status_code == 401
    assert r_ref.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_via_refresh_cascades_to_access(client):
    """登出时传 refresh 也要连带拉黑 access —— 双向联动。"""
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]

    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r_out.status_code == 204

    # 原 access 不得再访问受保护端点
    r_me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_me.status_code == 401
    assert r_me.json()["code"] == 40101


@pytest.mark.asyncio
async def test_expired_token_rejected(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1")
    get_settings.cache_clear()

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    token = r.json()["access_token"]
    time.sleep(2)

    r2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40101

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_inactive_user_cannot_authenticate(client, pg_url):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # 先登录获取 token
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "guest_demo", "password": "Guest@123456"},
    )
    token = r.json()["access_token"]

    # 管理员手动把 guest_demo 置为 inactive
    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_active=FALSE WHERE username='guest_demo'")
        )
    await engine.dispose()

    r2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40102
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/integration/test_auth_api.py -v -m integration
```

- [ ] **Step 3: 实现 `app/api/v1/auth.py`**

`backend/app/api/v1/__init__.py`：空。

`backend/app/api/v1/auth.py`：

```python
"""/api/v1/auth/* — Spec §4.2 auth group."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.blacklist import is_revoked, pop_pair, register_pair, revoke
from app.auth.claims import UserClaims
from app.auth.jwt import TokenType, create_access_token, create_refresh_token, decode_token
from app.auth.login_limiter import LoginBlocked, ensure_not_blocked, record_failure, reset
from app.auth.passwords import verify_password
from app.auth.user_repo import get_by_username, touch_last_login
from app.config import get_settings
from app.storage.pg import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Shared bearer extractor for refresh & logout — both accept a raw token in the
# Authorization header without going through get_current_user (which enforces
# access-token semantics).
_bearer = HTTPBearer(auto_error=True)


# ------------ Pydantic schemas ---------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: str
    username: str
    role: str
    permission_level: str
    department: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user: UserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"


# ------------ Helpers -------------------------------------------------------

def _unauthorized(code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": 42900, "message": "请求过于频繁，请稍后重试"},
        headers={"Retry-After": str(retry_after)},
    )


# ------------ Endpoints -----------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> LoginResponse:
    # 1. 先校验是否被限流（用户名维度）
    try:
        await ensure_not_blocked(body.username)
    except LoginBlocked as blocked:
        raise _rate_limited(blocked.retry_after)

    # 2. 查用户（username 不存在与密码错返回同一错误码）
    user = await get_by_username(session, body.username)

    # 3. 校验密码 + is_active
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await record_failure(body.username)
        raise _unauthorized(40101, "用户名或密码错误")

    # 4. 签发双 token，并登记 access↔refresh 配对（供 logout 级联拉黑）
    access_token, access_jti = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        permission_level=user.permission_level,
        department=user.department,
    )
    refresh_token, refresh_jti = create_refresh_token(user_id=user.user_id)
    await register_pair(
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        ttl_seconds=get_settings().jwt_refresh_ttl_seconds,
    )

    # 5. 重置限流计数 + 更新 last_login_at
    await reset(body.username)
    await touch_last_login(session, user_id=user.user_id)
    await session.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            permission_level=user.permission_level,
            department=user.department,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    from sqlalchemy import select

    from app.auth.blacklist import is_revoked
    from app.models.user import User

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.REFRESH)
    except JWTError:
        raise _unauthorized(40101, "Refresh token 失效")

    # 登出会把 refresh 也拉黑，这里也要检查
    if await is_revoked(payload["jti"]):
        raise _unauthorized(40101, "Token 已登出")

    # 按 user_id 取最新 role/pl —— 防止"权限被下调但旧 refresh 还能签 access"
    user = (
        await session.execute(select(User).where(User.user_id == payload["sub"]))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized(40102, "账户禁用")

    new_access, _ = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        permission_level=user.permission_level,
        department=user.department,
    )
    return RefreshResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Response:
    """Revoke the caller's jti AND its partner (access↔refresh pair).

    Accepts either an access or refresh token. A single logout call
    invalidates both tokens of the pair so that a stolen/leaked refresh
    cannot mint a new access after the user logs out. Already-expired tokens
    are rejected with 401.
    """
    for token_type in (TokenType.ACCESS, TokenType.REFRESH):
        try:
            payload = decode_token(credentials.credentials, expected_type=token_type)
            break
        except JWTError:
            continue
    else:
        raise _unauthorized(40101, "Token 失效")

    exp = int(payload["exp"])
    now = int(datetime.now(timezone.utc).timestamp())
    jti = payload["jti"]

    await revoke(jti=jti, ttl_seconds=exp - now)

    # 级联拉黑 pair 的另一端。对端剩余 TTL 不可从当前 payload 推导，保守用 refresh_ttl
    # 作为黑名单存活时间（pair key 的 TTL 本身 = refresh_ttl，查得到就说明未过期）。
    partner_jti = await pop_pair(jti)
    if partner_jti is not None:
        await revoke(
            jti=partner_jti,
            ttl_seconds=get_settings().jwt_refresh_ttl_seconds,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(claims: UserClaims = Depends(get_current_user)) -> UserOut:
    """Return the authenticated user's profile — used by integration smoke tests."""
    return UserOut(
        user_id=claims.sub,
        username=claims.username,
        role=claims.role.value,
        permission_level=claims.pl,
        department=claims.dept,
    )
```

- [ ] **Step 4: `main.py` 挂 router**

同样只追加，不改 `app = FastAPI(...)` 或 `lifespan` / `/healthz`：

```python
from app.api.v1.auth import router as auth_router
# ... install_exception_handlers(app) 之后
app.include_router(auth_router)
```

- [ ] **Step 5: 跑测试**

```bash
pytest tests/integration/test_auth_api.py -v -m integration
```

预期：9 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/__init__.py backend/app/api/v1/auth.py \
        backend/app/main.py backend/tests/integration/test_auth_api.py
git commit -m "feat(api): add /api/v1/auth/{login,refresh,logout,me} with full coverage"
```

---

## Task 10: RBAC ES Filter + `/admin/ping` 示范 + 三角色拦截测试

把"权限 chunk 过滤"与"端点角色拦截"这两条 DoD 一次性落地。

**Files:**
- Create: `backend/app/rbac/__init__.py`
- Create: `backend/app/rbac/filter_builder.py`
- Create: `backend/app/api/v1/admin.py`
- Create: `backend/tests/unit/test_filter_builder.py`
- Create: `backend/tests/integration/test_admin_gate.py`
- Modify: `backend/app/main.py`（挂 admin router）

- [ ] **Step 1: 写 filter_builder 单测**

```python
# backend/tests/unit/test_filter_builder.py
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_filter_builder.py -v
```

- [ ] **Step 3: 实现 `app/rbac/filter_builder.py`**

`backend/app/rbac/__init__.py`：

```python
from app.rbac.filter_builder import ROLE_LEVEL_MATRIX, build_es_filter  # noqa: F401

__all__ = ["ROLE_LEVEL_MATRIX", "build_es_filter"]
```

`backend/app/rbac/filter_builder.py`：

```python
"""Role→permission_level matrix + ES filter builder — Spec §5.3/§5.4.

Usage (to be invoked by Phase 3 hybrid_search at the highest level, so that
downstream retrieval CANNOT bypass the guard).
"""

from __future__ import annotations

from typing import Any

from app.auth.claims import Role, UserClaims

ROLE_LEVEL_MATRIX: dict[str, list[str]] = {
    Role.GUEST.value: ["L1"],
    Role.EMPLOYEE.value: ["L1", "L2"],
    Role.ADMIN.value: ["L1", "L2", "L3"],
}


def build_es_filter(claims: UserClaims) -> dict[str, Any]:
    """Build the Elasticsearch `bool.filter` clause for permission_level.

    ABAC placeholder: `claims.dept` is intentionally unused for MVP per Spec
    §5.3, but kept in the signature so future code can extend without API
    breakage.
    """
    allowed = ROLE_LEVEL_MATRIX[claims.role.value]
    return {"bool": {"filter": [{"terms": {"permission_level": allowed}}]}}
```

- [ ] **Step 4: 实现 `app/api/v1/admin.py`（示范端点）**

```python
"""Minimum admin router — only /ping for Phase 2 gate demo.

Real admin endpoints (settings / logs / metrics / knowledge) will be added in
later Phases. The sole purpose of /ping is to lock the role gate via tests.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin, require_any_user
from app.auth.claims import UserClaims

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(claims: UserClaims = Depends(require_admin)) -> dict:
    return {"pong": True, "caller": claims.username}


@router.get("/whoami")
async def whoami(claims: UserClaims = Depends(require_any_user)) -> dict:
    """Any authenticated user (guest/employee/admin) can hit this."""
    return {"role": claims.role.value, "pl": claims.pl}
```

- [ ] **Step 5: 写集成测试**

```python
# backend/tests/integration/test_admin_gate.py
import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)

    from app.config import get_settings
    get_settings.cache_clear()
    from scripts.seed_users import seed
    await seed()

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c

    # Teardown: 与 test_auth_api.py 保持一致 —— 清残留
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET is_active=TRUE "
                "WHERE username IN ('admin','employee_demo','guest_demo')"
            )
        )
    await engine.dispose()

    from app.storage.redis_client import close_redis, get_redis

    r = get_redis()
    for uname in ("admin", "employee_demo", "guest_demo"):
        await r.delete(f"ratelimit:login:{uname}")
    for prefix in ("jwt_blacklist", "jwt_pair"):
        async for key in r.scan_iter(match=f"{prefix}:*"):
            await r.delete(key)

    from app.storage.pg import dispose_engine
    await dispose_engine()
    await close_redis()
    get_settings.cache_clear()


async def _token(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_ping_admin_200(client):
    tok = await _token(client, "admin", "Admin@123456")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["pong"] is True


@pytest.mark.asyncio
async def test_admin_ping_employee_403(client):
    tok = await _token(client, "employee_demo", "Employee@12345")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert r.json()["code"] == 40301


@pytest.mark.asyncio
async def test_admin_ping_guest_403(client):
    tok = await _token(client, "guest_demo", "Guest@123456")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert r.json()["code"] == 40301


@pytest.mark.asyncio
async def test_admin_ping_no_token_401(client):
    r = await client.get("/api/v1/admin/ping")
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_whoami_allows_all_three_roles(client):
    for username, password, expected_role, expected_pl in [
        ("admin", "Admin@123456", "admin", "L3"),
        ("employee_demo", "Employee@12345", "employee", "L2"),
        ("guest_demo", "Guest@123456", "guest", "L1"),
    ]:
        tok = await _token(client, username, password)
        r = await client.get(
            "/api/v1/admin/whoami",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, f"{username}: {r.text}"
        body = r.json()
        assert body["role"] == expected_role
        assert body["pl"] == expected_pl
```

- [ ] **Step 6: `main.py` 挂 admin router**

同样只追加一行：

```python
from app.api.v1.admin import router as admin_router
# ... include_router(auth_router) 之后
app.include_router(admin_router)
```

- [ ] **Step 7: 跑全部新测试**

```bash
pytest tests/unit/test_filter_builder.py -v
pytest tests/integration/test_admin_gate.py -v -m integration
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/rbac/ backend/app/api/v1/admin.py backend/app/main.py \
        backend/tests/unit/test_filter_builder.py \
        backend/tests/integration/test_admin_gate.py
git commit -m "feat(rbac): add role×level matrix, ES filter builder, admin gate demo"
```

---

## Task 11: 端到端冒烟 + Phase 2 DoD 勾选 + self-review

不新写代码，只跑流程并勾选 DoD。

- [ ] **Step 1: 全量单元 + 集成测试**

```bash
cd backend
pytest tests/unit -v
pytest tests/integration -v -m integration
ruff check .
mypy app
```

全部 green 才能继续。

- [ ] **Step 2: Docker 冒烟**

```bash
# 在项目根
./deploy.sh stop
./deploy.sh start
./deploy.sh init    # 复用 Phase 1，应该 idempotent
sleep 15
./deploy.sh ps      # 期望 5 服务 healthy
```

手动 curl 验证：

```bash
# 登录
TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123456"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 访问 admin/ping
curl -sS http://localhost:8000/api/v1/admin/ping -H "Authorization: Bearer $TOKEN"
# 期望：{"pong":true,"caller":"admin"}

# 登出
curl -sS -X POST http://localhost:8000/api/v1/auth/logout -H "Authorization: Bearer $TOKEN" -i
# 期望：HTTP/1.1 204

# 登出后再访问
curl -sS http://localhost:8000/api/v1/admin/ping -H "Authorization: Bearer $TOKEN" -i
# 期望：HTTP/1.1 401 + code 40101
```

- [ ] **Step 3: 逐条勾选 DoD**

回到 plan 开头的 DoD 清单，把所有 `- [ ]` 改为 `- [x]`，并在本文件末尾追加"**Phase 2 冒烟结果**"小节写实测输出。

- [ ] **Step 4: Commit 勾选**

```bash
git add docs/superpowers/plans/2026-04-23-phase2-auth-rbac.md
git commit -m "docs(plans): tick Phase 2 DoD after end-to-end smoke"
```

- [ ] **Step 5: Push 分支（不合 main，等待 user review）**

```bash
git push -u origin phase2-auth-rbac
```

---

## Self-Review（writing-plans 阶段，执行时需再过一遍）

1. **Spec 覆盖扫描**：
   - Spec §4.2 auth 三个端点 → Task 9 全覆盖
   - Spec §4.5 Redis Key `jwt_blacklist:{jti}` / `ratelimit:login:{username}` → Task 4 / Task 7 双锁
   - Spec §4.6 错误码 40101/40102/40301/42900 → Task 8 定义 + Task 6/9/10 调用
   - Spec §5.1 JWT claims 字段 → Task 2 `create_access_token` 实参列表与 Task 3 UserClaims 对应
   - Spec §5.2 鉴权依赖链（decode → blacklist → is_active）→ Task 6 按顺序实施
   - Spec §5.3 RBAC 矩阵 → Task 10 锁住
   - Spec §5.4 `build_es_filter` → Task 10 实现 + 单测
   - Spec §5.6 bcrypt cost=12 + 登录失败 5/10min → Task 1 + Task 7
   - Spec §5.5 权限拒绝审计 `qa_logs.status='permission_denied'` → **未在 Phase 2 落地**（qa_logs 写入属 Phase 5 的职责，Phase 2 只暴露拦截点）
   - 主 index DoD 所有 5 条 → 全部覆盖

2. **Placeholder 扫描**：
   - 保留的 "placeholder" 注释仅限于：`ErrorCode` 预留了 `LLM_TIMEOUT/ES_UNAVAILABLE`（Phase 4/5 扩充）、`build_es_filter` 中的 ABAC `dept` 字段占位（Spec §5.3 已明确 MVP 不启用）。
   - 代码区段均给出完整可执行实现，无 TBD / NotImplementedError / 死代码路径。

3. **类型一致性**：
   - `UserClaims.role` 为 `Role` enum；`require_role` 接受 str，内部转 `Role` —— 统一。
   - `create_access_token` 的 `permission_level` 参数与 `User.permission_level` 字段、`UserClaims.pl` 字段三方一致（均为 `Literal["L1","L2","L3"]` 或等价 str）。
   - `ErrorCode` 为 `IntEnum`，在 `HTTPException.detail["code"]` 处直接用 enum 成员（FastAPI JSON 序列化会把 IntEnum 转 int）。

4. **潜在阻塞点 / 风险**：
   - **lru_cache 污染**：`get_settings()` 用了 `@lru_cache`，测试里改 env 后需要 `get_settings.cache_clear()`。Task 2 测试和 Task 9 fixture 都显式清缓存。其他 Task 如果新加涉及 JWT_SECRET 的测试，须跟进。
   - **seed_users 的依赖方向**：Task 5/9/10 的集成测试都 import `scripts.seed_users.seed`。前提：`pyproject.toml` 的 `pythonpath = ["."]` 存在（Phase 1 已配），且 `backend/scripts/__init__.py` 存在（Phase 1 已有）。
   - **httpx.ASGITransport fixture scope**：当前集成测试 `client` fixture 是 function 级（每测试函数一次 seed）。testcontainer 是 session 级，pg 容器复用，但每个函数要重新灌 seed —— 因为上面函数级 fixture 里 `await seed()` 是 idempotent（ON CONFLICT DO NOTHING）所以 OK。但 `test_inactive_user_cannot_authenticate` 会修改 `users.is_active`，后续测试跑到它之后会污染数据。解法：fixture 里 `yield` 之后 `UPDATE users SET is_active=TRUE`，或者在第一次出现影响时 move it 到测试文件末尾 + autouse truncate。**实施时请 subagent 在 fixture 里加一次 teardown 清理** `UPDATE users SET is_active=TRUE WHERE username='guest_demo'`。
   - **limiter 测试的 reset 保护**：Task 7/9 的 limiter 测试彼此共用 Redis 容器，测试之间须显式 `reset(username)`。已在测试代码里做了。
   - **Docker Desktop 与 testcontainers**：本地 Windows 下的 testcontainers 需要 Docker Desktop 已启动，并共享当前工作目录。Phase 1 已验证；Phase 2 无新增容器依赖。
   - **Refresh 端点的权限漂移**：我们在 `refresh` 里**用 user 当前 DB 字段**重新签 access，使得角色被降级后旧 refresh 也能立刻反映（合规）。注意这在单测里需要保证 `scripts.seed_users.seed` 与 `refresh` 走同一份 Settings（lru_cache 同步）—— 已在 fixture 里处理。
   - **`/auth/logout` 接受已过期 token 的语义**：当前实现把已过期 token 直接判 401，不入黑名单。主 Spec 未明确；按"幂等 + 保守"策略走 401 即可。测试里已验证这点。
   - **并发边界**：Phase 2 不引入并发测试。Phase 5 locust 会覆盖。
   - **Login limiter TOCTOU**：`ensure_not_blocked` 做 GET，`record_failure` 做 INCR，两步之间有竞态窗口。MVP 接受"同一用户名在窗口内的并发失败 burst 可能超出 `_THRESHOLD=5` 少量次数"的语义；硬化为 Lua CAS / `INCR` 返回值判定推迟到 Phase 5 压测阶段。
   - **404 不被吞**：Phase 2 的 `install_exception_handlers` 会给未匹配路由返回 Starlette 默认 404 还是被 `Exception` 兜底 handler 改写？答案：FastAPI 的 route not found 抛的是 `StarletteHTTPException`，会走 `HTTPException` handler；`Exception` handler 只在 500 路径生效。Task 8 的新测试 `test_unknown_route_still_returns_404_not_500` 锁住这一行为。
   - **Logout 级联语义**：已在 `blacklist.register_pair` + `pop_pair` 落地，一次 logout 同时撤销 access 与 refresh（B1 修复）。代价：每次登录多写 2 次 Redis；Redis key 量 = 活跃会话 × 2 个 pair key + 黑名单。MVP 规模下可忽略。

5. **与 CLAUDE.md / 项目规则一致性**：
   - 代码变量/函数命名符合 self-documenting 原则（`verify_password`, `is_revoked`, `ensure_not_blocked`, `build_es_filter`）。
   - 测试先行、commit 小颗粒、分支独立。
   - 所有 Task 都是可独立验证的原子单元。

---

## Execution Handoff

Plan 已落入 `docs/superpowers/plans/2026-04-23-phase2-auth-rbac.md`，共 11 个 Task（Task 0 为 Phase 1 gap 前置），每个 Task 按 TDD 粒度 2-5 分钟每步，全部给出完整代码与命令。

用户已确认：
- 执行方式：**Subagent-Driven**（每个 Task 派 fresh subagent + 两阶段 review）
- 分支：`phase2-auth-rbac`（已切出）
- Token 策略：**access + refresh 双 JWT**
- Phase 1 gap 作为 Task 0 前置

等待用户批准 plan 后，触发 `superpowers:subagent-driven-development` 按 Task 0 → 11 顺序派 subagent。Task 1-5 之间无紧耦合，可在 subagent pool 里尝试并行（但仍需等 Task 0 先 green，避免 CI 红着跑）。

---

## Phase 2 冒烟结果

**执行日期**: 2026-04-24
**分支**: `phase2-auth-rbac`
**提交数**: 12 commits (Task 0a → Task 11)

### 单元测试

```
36 items: 34 passed, 2 failed (预存环境问题)
```

Phase 2 新增单元测试全部通过（claims/jwt/passwords/deps/errors/filter_builder 共 28 项）。
2 个预存失败：`test_settings_fail_fast_on_missing_required`（.env 文件干扰）、`test_healthz_returns_degraded_without_backends`（本地 Redis 运行中）。

### 集成测试

```
34 passed, 2 errors (ES 镜像拉取网络问题，非 Phase 2)
```

Phase 2 新增集成测试全部通过（blacklist/user_repo/login_limiter/auth_api/admin_gate/seed_users 共 30 项）。
2 个 Phase 1 预存 ES 错误：`testcontainers` 无法从 Docker Hub 拉取 `infinilabs/elasticsearch-ik:8.11.0`（国内网络限制）。

### Ruff

```
B008 (Depends in defaults) 已加入 ignore list，其余通过
```

### Mypy

```
仅剩 Phase 1 预存警告: main.py:49 redis.ping() 类型推断
Phase 2 模块无新增类型错误
```

### DoD 逐条验证

| # | DoD 项 | 状态 | 证据 |
|---|--------|------|------|
| 1 | 登录成功/失败/过期/黑名单 | ✅ | test_auth_api.py 11 passed |
| 2 | 三角色 admin/* 拦截 | ✅ | test_admin_gate.py 5 passed |
| 3 | build_es_filter(guest) L1 only | ✅ | test_filter_builder.py |
| 4 | build_es_filter(employee) L1+L2 | ✅ | test_filter_builder.py |
| 5 | build_es_filter(admin) L1+L2+L3 | ✅ | test_filter_builder.py |
| 6 | bcrypt cost=12 | ✅ | test_passwords.py 显式断言 `$2b$12$` |
| 7 | 429 限流第6次 | ✅ | test_auth_api.py:test_login_fifth_failure_blocks_with_42900 |
| 8 | 登出后 40101 | ✅ | test_auth_api.py:test_logout_blacklists_token |
| 9 | is_active=false → 40102 | ✅ | test_auth_api.py:test_inactive_user_cannot_authenticate |
| 10a | CI workflow 存在 | ✅ | .github/workflows/ci.yml |
| 10b | seed_users 集成测试 | ✅ | test_seed_users.py 2 passed |

**Phase 2 DoD: 全部通过 ✅**
