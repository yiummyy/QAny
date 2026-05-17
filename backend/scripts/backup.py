#!/usr/bin/env python3
"""PostgreSQL backup script with 7-day retention.

Usage:
    python scripts/backup.py          # Full backup
    python scripts/backup.py --list   # List existing backups
"""

import asyncio
import subprocess
import sys
import time
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_LOG = BACKUP_DIR / "backup.log"
RETENTION_DAYS = 7


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with open(BACKUP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_db_url(url: str) -> dict[str, str]:
    """Parse DATABASE_URL into pg_dump-compatible parameters."""
    pattern = r"postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    m = re.match(pattern, url)
    if not m:
        raise ValueError(f"Cannot parse DATABASE_URL: {url}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": m.group(4),
        "dbname": m.group(5),
    }


async def main() -> int:
    settings = get_settings()
    today = datetime.now().strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / f"{today}.sql"

    db = parse_db_url(settings.DATABASE_URL)
    log(f"Starting backup → {backup_path}")
    t0 = time.monotonic()

    env = {"PGPASSWORD": db["password"]}
    cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-acl",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            log(f"pg_dump failed (rc={proc.returncode}): {err}")
            return 1

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        with open(backup_path, "wb") as f:
            f.write(stdout)

        size_mb = backup_path.stat().st_size / (1024 * 1024)
        elapsed = time.monotonic() - t0
        log(f"Backup complete: {size_mb:.1f} MB in {elapsed:.1f}s")

    except FileNotFoundError:
        log("ERROR: pg_dump not found — install PostgreSQL client tools")
        return 1

    cleanup_count = 0
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for f in sorted(BACKUP_DIR.glob("*.sql")):
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            f.unlink()
            cleanup_count += 1

    if cleanup_count:
        log(f"Cleaned up {cleanup_count} old backup(s) older than {RETENTION_DAYS}d")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
