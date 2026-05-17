#!/usr/bin/env bash
set -e

COMMAND=$1
ARG=$2

case "$COMMAND" in
  start)
    echo "Starting QA System..."
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0
    docker compose up -d --build
    ;;
  stop)
    echo "Stopping QA System..."
    docker compose down
    ;;
  restart)
    if [ -z "$ARG" ]; then
      echo "Usage: $0 restart <service>"
      exit 1
    fi
    docker compose restart "$ARG"
    ;;
  ps)
    docker compose ps
    ;;
  health)
    echo "Checking system health..."
    curl -s http://localhost:8000/healthz | python3 -m json.tool 2>/dev/null || \
      curl -s http://localhost:8000/healthz
    ;;
  logs)
    if [ -z "$ARG" ]; then
      docker compose logs -f
    else
      docker compose logs -f "$ARG"
    fi
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
  reindex)
    echo "Rebuilding ES index from PostgreSQL documents..."
    if [ -z "$ARG" ]; then
      docker compose exec backend python scripts/reindex.py
    else
      docker compose exec backend python scripts/reindex.py "$ARG"
    fi
    ;;
  backup)
    echo "Running PostgreSQL backup..."
    docker compose exec backend python scripts/backup.py
    ;;
  monitoring)
    case "$ARG" in
      up)
        echo "Starting monitoring stack (Prometheus + Grafana)..."
        docker compose --profile monitoring up -d prometheus grafana
        echo "Prometheus: http://localhost:9090"
        echo "Grafana:    http://localhost:3000 (admin/admin)"
        ;;
      down)
        echo "Stopping monitoring stack..."
        docker compose --profile monitoring down
        ;;
      ps)
        docker compose --profile monitoring ps
        ;;
      *)
        echo "Usage: $0 monitoring {up|down|ps}"
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Usage: $0 {start|stop|restart <svc>|ps|health|logs <svc>|init|reindex [doc_id]|backup|monitoring {up|down|ps}}"
    exit 1
    ;;
esac
