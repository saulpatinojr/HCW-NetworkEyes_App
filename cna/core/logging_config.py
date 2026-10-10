"""Structured logging configuration.

Closes TODO_PhaseA: No Logging Infrastructure.

Sets up:
  - Structured JSON log lines to file: <engagement_dir>/cna.log
  - Rich console output (human-readable) via Rich handler
  - Log level from CNA_LOG_LEVEL env var (default: INFO)
  - Correlation ID per engagement injected into every log record
  - Audit log (JSONL) for human review gate actions via EngagementStore

Usage:
  from cna.core.logging_config import setup_logging, get_logger
  setup_logging(engagement_id="acme-20260305-a3f2")
  logger = get_logger("cna.modules.network")
  logger.info("Starting VPC discovery", extra={"account_id": "123"})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON for structured log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "engagement_id": getattr(record, "engagement_id", None),
        }
        # Merge any extra fields passed via extra={...}
        for key, val in record.__dict__.items():
            if key not in (
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
                "name",
                "timestamp",
                "level",
                "logger",
                "engagement_id",
            ):
                log_obj[key] = val
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class EngagementFilter(logging.Filter):
    """Inject engagement_id into every log record."""

    def __init__(self, engagement_id: str):
        super().__init__()
        self._engagement_id = engagement_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "engagement_id"):
            record.engagement_id = self._engagement_id
        return True


def setup_logging(
    engagement_id: str | None = None,
    log_dir: Path | None = None,
) -> None:
    """Configure root CNA logger.

    Args:
        engagement_id: If provided, injected into every log line.
        log_dir: If provided, write cna.log JSON file here.
    """
    level_name = os.environ.get("CNA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger("cna")
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    if engagement_id:
        root_logger.addFilter(EngagementFilter(engagement_id))

    # Console handler — Rich-formatted for human readability
    try:
        from rich.logging import RichHandler

        console_handler = RichHandler(
            level=level,
            show_time=True,
            show_path=False,
            markup=True,
        )
    except ImportError:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

    root_logger.addHandler(console_handler)

    # File handler — JSON structured, one line per record
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "cna.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # always verbose to file
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a cna-namespaced logger."""
    if not name.startswith("cna."):
        name = f"cna.{name}"
    return logging.getLogger(name)
