import logging
import sys
from collections.abc import Sequence

import structlog
from structlog.typing import Processor


def configure_logging(level: str = "INFO", env: str = "dev") -> None:
    """Configure structlog for JSON output.

    Call once at application startup (or in each unit test that exercises logging).
    ``cache_logger_on_first_use=False`` ensures tests can call this repeatedly and
    always pick up the new configuration.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    json_renderer = (
        structlog.processors.JSONRenderer(sort_keys=True)
        if env == "prod"
        else structlog.processors.JSONRenderer()
    )
    shared_processors: Sequence[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
        json_renderer,
    ]
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a structlog bound logger with the given name pre-bound as ``logger``."""
    return structlog.get_logger().bind(logger=name)  # type: ignore[no-any-return]
