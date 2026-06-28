"""Structured logging with verbosity levels for diskstat."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import IO, Any, Optional


class StructuredFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        # Include extra fields
        for key in ("path", "files", "dirs", "elapsed", "size", "phase"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class VerbosityLevel:
    """Map -v/-q flags to log levels."""

    @staticmethod
    def from_flags(verbosity: int, quiet: bool) -> int:
        if quiet:
            return logging.CRITICAL + 1  # suppress everything
        if verbosity >= 2:
            return logging.DEBUG
        if verbosity == 1:
            return logging.INFO
        return logging.WARNING


def setup_logging(
    level: int = logging.WARNING,
    log_file: Optional[str] = None,
    stream: Optional[IO] = None,
) -> logging.Logger:
    """Configure the diskstat logger.

    Args:
        level: logging level (e.g. logging.INFO)
        log_file: optional file path for structured JSON logs
        stream: output stream (defaults to stderr)
    """
    logger = logging.getLogger("diskstat")
    logger.setLevel(level)
    logger.handlers.clear()

    target = stream or sys.stderr

    if level <= logging.DEBUG:
        # Human-readable format for verbose mode
        fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-7s] %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        fmt = logging.Formatter(fmt="%(message)s")

    shandler = logging.StreamHandler(target)
    shandler.setFormatter(fmt)
    shandler.setLevel(level)
    logger.addHandler(shandler)

    if log_file:
        sfmt = StructuredFormatter()
        fhandler = logging.FileHandler(log_file, encoding="utf-8")
        fhandler.setFormatter(sfmt)
        fhandler.setLevel(logging.DEBUG)
        logger.addHandler(fhandler)

    return logger


def get_logger() -> logging.Logger:
    """Get the diskstat logger (or a basic one if not set up)."""
    logger = logging.getLogger("diskstat")
    if not logger.handlers:
        setup_logging()
    return logger
