#!/usr/bin/env bash
set -e

COMMAND=$1

case "$COMMAND" in
  start)
    echo "Starting QA System..."
    # Disable BuildKit for CLI to avoid moby/buildkit pull issues
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0
    docker compose up -d --build
    ;;
  stop)
    echo "Stopping QA System..."
    docker compose down
    ;;
  ps)
    docker compose ps
    ;;
  init)
    echo "Initializing Database..."
    docker compose exec backend alembic upgrade head
    echo "Initializing Elasticsearch..."
    docker compose exec backend python scripts/init_es.py
    echo "Seeding Users..."
    docker compose exec backend python scripts/seed_users.py
    echo "Initialization Complete."
    ;;
  *)
    echo "Usage: $0 {start|stop|ps|init}"
    exit 1
    ;;
esac
