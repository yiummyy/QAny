import subprocess
import sys
import time

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container, monkeypatch_session):
    raw = pg_container.get_connection_url()  # postgresql+psycopg2://...
    url = raw.replace("psycopg2", "asyncpg")
    monkeypatch_session.setenv("DATABASE_URL", url)
    # Alembic needs a sync URL
    sync_url = raw.replace("psycopg2", "psycopg")
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "-x", f"sqlalchemy.url={sync_url}", "upgrade", "head"],
        cwd="backend",
    )
    return url


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def redis_url(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


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
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9200)
        url = f"http://{host}:{port}"
        # ES 冷启动最慢，等待 /_cluster/health 可达
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                r = httpx.get(f"{url}/_cluster/health", timeout=2.0)
                if r.status_code == 200 and r.json().get("status") in ("green", "yellow"):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("elasticsearch container did not become healthy in 120s")
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def es_url(es_container):
    host = es_container.get_container_host_ip()
    port = es_container.get_exposed_port(9200)
    return f"http://{host}:{port}"
