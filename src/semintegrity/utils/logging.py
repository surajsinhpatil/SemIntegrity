"""Structured logging.

One logger configuration for laptop, login node and Slurm job, so that a log
line means the same thing wherever it was produced. Slurm job id and node name
are attached automatically when present.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("SLURM_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURMD_NODENAME"):
            if key in os.environ:
                payload[key.lower()] = os.environ[key]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO", *, json_format: bool | None = None) -> None:
    """Configure the root logger once.

    Defaults to JSON when running under Slurm (logs are parsed later) and to a
    human-readable line otherwise.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    if json_format is None:
        json_format = "SLURM_JOB_ID" in os.environ
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        _JsonFormatter()
        if json_format
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level.upper()))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
