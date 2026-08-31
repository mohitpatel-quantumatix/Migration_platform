from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

_run_id: str = uuid.uuid4().hex
_logger: logging.Logger | None = None
_stdout_enabled: bool = True   # set to False when rich display takes over


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        logger = logging.getLogger("migration_platform.audit")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        _logger = logger
    return _logger


def configure_file_logging(log_dir: str = "logs", suppress_stdout: bool = False) -> str:
    """
    Add a file handler so every JSON audit line is persisted to disk.

    Returns the path of the log file created.
    Call this once at startup (after set_run_id).
    """
    global _stdout_enabled
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{_run_id}.jsonl")

    logger = _get_logger()

    # Remove duplicate file handlers
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            logger.removeHandler(h)

    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)

    if suppress_stdout:
        _stdout_enabled = False
        for h in logger.handlers[:]:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                logger.removeHandler(h)

    return log_path


def set_run_id(run_id: str | None = None) -> None:
    global _run_id
    _run_id = run_id or uuid.uuid4().hex


def get_run_id() -> str:
    return _run_id


def audit_log(
    phase: str,
    status: str,
    details: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id or _run_id,
        "phase": phase,
        "status": status,
    }
    if details is not None:
        event["details"] = details
    _get_logger().info(json.dumps(event))