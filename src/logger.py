"""Structured, dual-output logging for Symbiote AI.

Every module calls ``get_logger(__name__)`` and gets a logger that writes:
- INFO+ to the console (human-readable, timestamped)
- DEBUG+ to logs/symbiote_YYYYMMDD.log (full context for debugging)
"""

import logging
import os
from datetime import datetime

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

# Shared file handler — one log file per calendar day, shared across all loggers
_file_handler: logging.FileHandler | None = None


def _get_file_handler() -> logging.FileHandler:
    global _file_handler
    if _file_handler is None:
        log_path = os.path.join(_LOG_DIR, f"symbiote_{datetime.now().strftime('%Y%m%d')}.log")
        _file_handler = logging.FileHandler(log_path, encoding="utf-8")
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    return _file_handler


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(f"symbiote.{name}")
    if logger.handlers:
        return logger  # already configured; avoid duplicate handlers

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console: INFO+ in a clean, scannable format
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(console)

    # File: DEBUG+ with full context for post-mortem analysis
    logger.addHandler(_get_file_handler())

    return logger
