"""Tests for ai_finder.logger module and logging integration."""

from __future__ import annotations

import asyncio
import logging
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_finder.logger import configure_logging, get_logger, _PACKAGE_LOGGER_NAME


# ---------------------------------------------------------------------------
# get_logger tests
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("ai_finder.test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_preserved(self):
        logger = get_logger("ai_finder.crawler")
        assert logger.name == "ai_finder.crawler"

    def test_loggers_are_children_of_package_root(self):
        logger = get_logger("ai_finder.extractor")
        # The logger is a child of the package root logger.
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        assert logger.parent is root or logger.name.startswith(_PACKAGE_LOGGER_NAME)

    def test_same_name_returns_same_instance(self):
        a = get_logger("ai_finder.some_module")
        b = get_logger("ai_finder.some_module")
        assert a is b


# ---------------------------------------------------------------------------
# configure_logging tests
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def _fresh_root(self):
        """Return the package root logger with no handlers (clean slate)."""
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        root.handlers.clear()
        return root

    def test_sets_requested_level(self):
        self._fresh_root()
        configure_logging(level="DEBUG")
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        assert root.level == logging.DEBUG

    def test_default_level_is_info(self):
        self._fresh_root()
        configure_logging()
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        assert root.level == logging.INFO

    def test_adds_console_handler(self):
        self._fresh_root()
        configure_logging(level="INFO")
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_console_handler_writes_to_stderr(self):
        self._fresh_root()
        configure_logging(level="INFO")
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert any(h.stream is sys.stderr for h in stream_handlers)

    def test_file_handler_created_when_log_file_given(self, tmp_path):
        self._fresh_root()
        log_file = str(tmp_path / "test.log")
        configure_logging(level="INFO", log_file=log_file)
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_log_file_receives_messages(self, tmp_path):
        self._fresh_root()
        log_file = str(tmp_path / "output.log")
        configure_logging(level="DEBUG", log_file=log_file)
        logger = get_logger("ai_finder._test_log_file")
        logger.info("hello from test")
        # Flush handlers
        for h in logging.getLogger(_PACKAGE_LOGGER_NAME).handlers:
            h.flush()
        content = Path(log_file).read_text(encoding="utf-8")
        assert "hello from test" in content

    def test_duplicate_configure_clears_handlers(self):
        self._fresh_root()
        configure_logging(level="INFO")
        configure_logging(level="DEBUG")
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        # Only one console handler should be present after the second call.
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) == 1

    def test_log_file_parent_dir_created(self, tmp_path):
        self._fresh_root()
        log_file = str(tmp_path / "subdir" / "nested" / "app.log")
        configure_logging(level="INFO", log_file=log_file)
        assert Path(log_file).exists()

    def test_level_case_insensitive(self):
        self._fresh_root()
        configure_logging(level="warning")
        root = logging.getLogger(_PACKAGE_LOGGER_NAME)
        assert root.level == logging.WARNING


# ---------------------------------------------------------------------------
# Integration: crawler emits expected log records
# ---------------------------------------------------------------------------


class TestCrawlerLogging:
    """Verify that Crawler emits log records at the expected levels."""

    def test_crawl_logs_start_info(self, tmp_path, caplog):
        from ai_finder.crawler import Crawler

        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")

        async def _run():
            with patch.object(crawler, "discover_urls", new=AsyncMock(return_value=[])):
                return await crawler.crawl(urls_file=urls_file)

        with caplog.at_level(logging.INFO, logger="ai_finder.crawler"):
            asyncio.run(_run())

        messages = " ".join(caplog.messages)
        assert "crawl" in messages

    def test_crawl_logs_existing_url_count(self, tmp_path, caplog):
        from ai_finder.crawler import Crawler

        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")
        Path(urls_file).write_text("https://example.com/a\n", encoding="utf-8")

        async def _run():
            with patch.object(crawler, "discover_urls", new=AsyncMock(return_value=[])):
                return await crawler.crawl(urls_file=urls_file)

        with caplog.at_level(logging.INFO, logger="ai_finder.crawler"):
            asyncio.run(_run())

        assert any("existing_urls=1" in m for m in caplog.messages)

    def test_filter_reachable_logs_counts(self, caplog):
        from ai_finder.crawler import Crawler

        crawler = Crawler()

        async def _run():
            with patch.object(
                crawler, "check_url", new=AsyncMock(return_value=True)
            ), patch("aiohttp.ClientSession") as mock_cls:
                mock_session = AsyncMock()
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                return await crawler.filter_reachable(["https://example.com/a"])

        with caplog.at_level(logging.INFO, logger="ai_finder.crawler"):
            asyncio.run(_run())

        assert any("filter_reachable" in m for m in caplog.messages)

    def test_check_url_debug_logged(self, caplog):
        from ai_finder.crawler import Crawler

        crawler = Crawler()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = MagicMock()
            mock_session.head = MagicMock(return_value=mock_resp)
            return await crawler.check_url(mock_session, "https://example.com/CLAUDE.md")

        with caplog.at_level(logging.DEBUG, logger="ai_finder.crawler"):
            asyncio.run(_run())

        assert any("check_url" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Integration: extractor emits expected log records
# ---------------------------------------------------------------------------


class TestExtractorLogging:
    """Verify that FileExtractor emits log records at the expected levels."""

    def test_fetch_debug_logged_on_success(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = AsyncMock(return_value="content")
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)

            extractor = FileExtractor(session=mock_session)
            return await extractor.fetch("https://example.com/CLAUDE.md")

        with caplog.at_level(logging.DEBUG, logger="ai_finder.extractor"):
            asyncio.run(_run())

        assert any("fetch" in m for m in caplog.messages)

    def test_fetch_warning_logged_on_error(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_session = MagicMock()
            mock_session.get = MagicMock(side_effect=Exception("network error"))
            extractor = FileExtractor(session=mock_session)
            return await extractor.fetch("https://example.com/bad.md")

        with caplog.at_level(logging.WARNING, logger="ai_finder.extractor"):
            asyncio.run(_run())

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("FAILED" in m or "error" in m.lower() for m in warning_messages)

    def test_fetch_many_info_logged(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = AsyncMock(return_value="content")
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)

            extractor = FileExtractor(session=mock_session)
            return await extractor.fetch_many(
                ["https://example.com/a", "https://example.com/b"]
            )

        with caplog.at_level(logging.INFO, logger="ai_finder.extractor"):
            asyncio.run(_run())

        assert any("fetch_many" in m for m in caplog.messages)

    def test_github_search_debug_logged(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = AsyncMock(return_value={"items": []})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)

            extractor = FileExtractor(session=mock_session)
            return await extractor.search_github("filename:CLAUDE.md")

        with caplog.at_level(logging.DEBUG, logger="ai_finder.extractor"):
            asyncio.run(_run())

        assert any("github_search" in m for m in caplog.messages)

    def test_github_search_warning_on_rate_limit(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 403
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)

            extractor = FileExtractor(session=mock_session)
            return await extractor.search_github("filename:CLAUDE.md")

        with caplog.at_level(logging.WARNING, logger="ai_finder.extractor"):
            asyncio.run(_run())

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("skipped" in m or "403" in m for m in warning_messages)

    def test_gitlab_search_debug_logged(self, caplog):
        from ai_finder.extractor import FileExtractor

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = AsyncMock(return_value=[])
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)

            extractor = FileExtractor(session=mock_session)
            return await extractor.search_gitlab("CLAUDE.md")

        with caplog.at_level(logging.DEBUG, logger="ai_finder.extractor"):
            asyncio.run(_run())

        assert any("gitlab_search" in m for m in caplog.messages)
