"""Centralized logging setup.

The spec calls for separate logs per concern (application, trades, errors,
scheduler, market data). We configure five named loggers here, each with
its own rotating file handler, so any module can do:

    import logging
    logger = logging.getLogger("trades")

and have it land in logs/trades.log automatically, without every module
needing to know about file paths or formatting.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_NAMES = ("app", "trades", "errors", "scheduler", "market_data")
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def configure_logging(logs_dir: Path, console_level: int = logging.INFO) -> None:
    """Idempotently wire up the named loggers. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    for name in _LOG_NAMES:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        file_handler = RotatingFileHandler(
            logs_dir / f"{name}.log", maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    # Only the general "app" logger also echoes to the console.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(console_level)
    logging.getLogger("app").addHandler(console_handler)

    # Every unhandled exception anywhere should also land in errors.log.
    error_logger = logging.getLogger("errors")

    def _log_uncaught(exc_type, exc_value, exc_traceback):  # type: ignore[no-untyped-def]
        error_logger.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    import sys

    sys.excepthook = _log_uncaught

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Fetch one of the pre-configured named loggers (falls back to stdlib behavior if unconfigured)."""
    return logging.getLogger(name)
