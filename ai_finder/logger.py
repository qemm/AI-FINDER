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


# ---------------------------------------------------------------------------
# aiohttp request/response trace config (enabled at DEBUG level)
# ---------------------------------------------------------------------------

_HTTP_TRACE_LOG = logging.getLogger("ai_finder.http")


def build_trace_config():  # type: ignore[return]
    """Return an :class:`aiohttp.TraceConfig` that logs every HTTP request and
    response at ``DEBUG`` level under the ``ai_finder.http`` logger.

    Attach the returned object to any :class:`aiohttp.ClientSession` to get
    full request/response traces::

        import aiohttp
        from ai_finder.logger import build_trace_config

        async with aiohttp.ClientSession(
            trace_configs=[build_trace_config()]
        ) as session:
            ...

    The ``Authorization`` header value is automatically redacted so that
    tokens are never written to log files in plain text.
    """
    import aiohttp  # local import keeps logger.py free of hard dependencies

    tc = aiohttp.TraceConfig()

    def _redact_headers(headers: object) -> dict[str, str]:
        """Return a plain dict copy of *headers* with the Authorization value masked."""
        result: dict[str, str] = {}
        for k, v in dict(headers).items():  # type: ignore[arg-type]
            if k.lower() == "authorization":
                parts = v.split(" ", 1)
                v = f"{parts[0]} [REDACTED]" if len(parts) == 2 else "[REDACTED]"
            result[k] = v
        return result

    async def _on_request_start(
        session: object,
        ctx: object,
        params: "aiohttp.TraceRequestStartParams",
    ) -> None:
        if not _HTTP_TRACE_LOG.isEnabledFor(logging.DEBUG):
            return
        _HTTP_TRACE_LOG.debug(
            ">>> %s %s\n    headers: %s",
            params.method,
            params.url,
            _redact_headers(params.headers),
        )

    async def _on_request_end(
        session: object,
        ctx: object,
        params: "aiohttp.TraceRequestEndParams",
    ) -> None:
        if not _HTTP_TRACE_LOG.isEnabledFor(logging.DEBUG):
            return
        resp = params.response
        _HTTP_TRACE_LOG.debug(
            "<<< %s %s  status=%d\n    resp-headers: %s",
            params.method,
            params.url,
            resp.status,
            dict(resp.headers),
        )

    async def _on_request_exception(
        session: object,
        ctx: object,
        params: "aiohttp.TraceRequestExceptionParams",
    ) -> None:
        if not _HTTP_TRACE_LOG.isEnabledFor(logging.DEBUG):
            return
        _HTTP_TRACE_LOG.debug(
            "!!! %s %s  exception=%s",
            params.method,
            params.url,
            params.exception,
        )

    tc.on_request_start.append(_on_request_start)
    tc.on_request_end.append(_on_request_end)
    tc.on_request_exception.append(_on_request_exception)
    return tc
