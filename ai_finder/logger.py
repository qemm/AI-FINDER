"""
logger.py — Centralised logging configuration for AI-FINDER.

All modules in the package obtain their logger via :func:`get_logger`, which
returns a child of the ``ai_finder`` root logger.  Callers of the library
(e.g. ``poc.py``) configure the root logger once at startup with
:func:`configure_logging`; library code itself never adds handlers or calls
``basicConfig`` so that it remains embedding-friendly.

Typical usage (application entry point)
----------------------------------------
    from ai_finder.logger import configure_logging
    configure_logging(level="DEBUG", log_file="ai_finder.log")

Typical usage (library module)
--------------------------------
    from ai_finder.logger import get_logger
    log = get_logger(__name__)
    log.debug("fetching %s", url)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# The package root logger — all child loggers inherit from this.
_PACKAGE_LOGGER_NAME = "ai_finder"

# Default format: timestamp · level · logger-name · message
_DEFAULT_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a :class:`logging.Logger` scoped to the ``ai_finder`` hierarchy.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module, e.g.
        ``ai_finder.crawler``.  The logger is always a child of the
        ``ai_finder`` root logger so that a single
        ``logging.getLogger("ai_finder").setLevel(…)`` call controls
        verbosity for the entire package.
    """
    return logging.getLogger(name)


def configure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    fmt: str = _DEFAULT_FORMAT,
    date_fmt: str = _DEFAULT_DATE_FORMAT,
) -> None:
    """Configure the ``ai_finder`` package logger.

    Call this **once** from the application entry point (e.g. ``poc.py``)
    before running any pipeline code.  Library modules never call this
    function directly.

    Parameters
    ----------
    level:
        Logging level for the package logger.  Accepted values (case-
        insensitive): ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
        ``CRITICAL``.
    log_file:
        Optional path to a file where log records are written in addition
        to *stderr*.  The file is created (or appended to) automatically.
    fmt:
        ``logging.Formatter`` format string.
    date_fmt:
        Date/time format string for the formatter.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger(_PACKAGE_LOGGER_NAME)
    root.setLevel(numeric_level)

    # Avoid adding duplicate handlers when called more than once (e.g. tests).
    if root.handlers:
        root.handlers.clear()

    formatter = logging.Formatter(fmt=fmt, datefmt=date_fmt)

    # Console handler — writes to stderr so stdout stays clean for machine output.
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(numeric_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional file handler.
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
