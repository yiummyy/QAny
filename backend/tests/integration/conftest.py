import pytest
import subprocess
from testcontainers.postgres import PostgresContainer


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
        ["alembic", "-x", f"sqlalchemy.url={sync_url}", "upgrade", "head"],
        cwd="backend",
    )
    return url
