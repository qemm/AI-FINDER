"""Tests for ai_finder.web_search module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_finder.web_search import WebSearcher


# ---------------------------------------------------------------------------
# HTML URL-extraction helper tests
# ---------------------------------------------------------------------------


class TestExtractUrlsFromHtml:
    def test_extracts_plain_href(self):
        html = '<a href="https://example.com/CLAUDE.md">link</a>'
        result = WebSearcher._extract_urls_from_html(html)
        assert "https://example.com/CLAUDE.md" in result

    def test_ignores_relative_hrefs(self):
        html = '<a href="/relative/path">link</a>'
        result = WebSearcher._extract_urls_from_html(html)
        assert result == []

    def test_ignores_excluded_domains(self):
        html = (
            '<a href="https://www.google.com/search?q=test">google</a>'
            '<a href="https://duckduckgo.com/?q=test">ddg</a>'
            '<a href="https://example.com/AGENTS.md">external</a>'
        )
        result = WebSearcher._extract_urls_from_html(html)
        assert all("google.com" not in u for u in result)
        assert all("duckduckgo.com" not in u for u in result)
        assert "https://example.com/AGENTS.md" in result

    def test_unwraps_google_redirect_url(self):
        html = '<a href="/url?q=https://example.com/CLAUDE.md&sa=t">link</a>'
        result = WebSearcher._extract_urls_from_html(html)
        assert "https://example.com/CLAUDE.md" in result

    def test_unwraps_duckduckgo_uddg_param(self):
        html = (
            '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2FCLAUDE.md">link</a>'
        )
        result = WebSearcher._extract_urls_from_html(html)
        assert "https://example.com/CLAUDE.md" in result

    def test_deduplicates_urls(self):
        html = (
            '<a href="https://example.com/CLAUDE.md">1</a>'
            '<a href="https://example.com/CLAUDE.md">2</a>'
        )
        result = WebSearcher._extract_urls_from_html(html)
        assert result.count("https://example.com/CLAUDE.md") == 1

    def test_returns_empty_for_no_links(self):
        result = WebSearcher._extract_urls_from_html("<html><body>No links</body></html>")
        assert result == []

    def test_preserves_insertion_order(self):
        html = (
            '<a href="https://a.example.com/">first</a>'
            '<a href="https://b.example.com/">second</a>'
            '<a href="https://c.example.com/">third</a>'
        )
        result = WebSearcher._extract_urls_from_html(html)
        assert result == [
            "https://a.example.com/",
            "https://b.example.com/",
            "https://c.example.com/",
        ]


# ---------------------------------------------------------------------------
# WebSearcher._fetch_page tests
# ---------------------------------------------------------------------------


class TestWebSearcherFetchPage:
    def test_returns_empty_string_on_non_200(self):
        searcher = WebSearcher()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 403
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)
            searcher._session = mock_session

            return await searcher._fetch_page("https://example.com/search", {})

        result = asyncio.run(_run())
        assert result == ""

    def test_returns_html_on_200(self):
        searcher = WebSearcher()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value="<html>result</html>")
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_resp)
            searcher._session = mock_session

            return await searcher._fetch_page("https://example.com/search", {})

        result = asyncio.run(_run())
        assert result == "<html>result</html>"

    def test_returns_empty_string_on_exception(self):
        searcher = WebSearcher()

        async def _run():
            mock_session = MagicMock()
            mock_session.get = MagicMock(side_effect=Exception("network error"))
            searcher._session = mock_session

            return await searcher._fetch_page("https://example.com/search", {})

        result = asyncio.run(_run())
        assert result == ""


# ---------------------------------------------------------------------------
# WebSearcher engine-specific tests (mocked _fetch_page)
# ---------------------------------------------------------------------------


class TestWebSearcherEngines:
    SAMPLE_HTML = (
        '<a href="https://raw.githubusercontent.com/u/r/main/CLAUDE.md">link</a>'
        '<a href="https://example.com/AGENTS.md">link2</a>'
    )

    def _make_searcher(self) -> WebSearcher:
        return WebSearcher()

    def test_search_duckduckgo_returns_urls(self):
        searcher = self._make_searcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=self.SAMPLE_HTML),
            ):
                return await searcher.search_duckduckgo("CLAUDE.md site:github.com")

        result = asyncio.run(_run())
        assert len(result) > 0
        assert any("CLAUDE.md" in u for u in result)

    def test_search_google_returns_urls(self):
        searcher = self._make_searcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=self.SAMPLE_HTML),
            ):
                return await searcher.search_google("CLAUDE.md site:github.com")

        result = asyncio.run(_run())
        assert len(result) > 0

    def test_search_yandex_returns_urls(self):
        searcher = self._make_searcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=self.SAMPLE_HTML),
            ):
                return await searcher.search_yandex("CLAUDE.md")

        result = asyncio.run(_run())
        assert len(result) > 0

    def test_search_respects_max_results(self):
        searcher = self._make_searcher()
        many_links = "".join(
            f'<a href="https://site{i}.example.com/CLAUDE.md">l</a>'
            for i in range(20)
        )

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=many_links),
            ):
                return await searcher.search_duckduckgo("test", max_results=5)

        result = asyncio.run(_run())
        assert len(result) <= 5

    def test_search_returns_empty_on_fetch_failure(self):
        searcher = self._make_searcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=""),
            ):
                return await searcher.search_duckduckgo("test query")

        result = asyncio.run(_run())
        assert result == []


# ---------------------------------------------------------------------------
# WebSearcher.search_all tests
# ---------------------------------------------------------------------------


class TestWebSearcherSearchAll:
    def test_search_all_aggregates_engines(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "search_duckduckgo",
                new=AsyncMock(return_value=["https://a.com/CLAUDE.md"]),
            ), patch.object(
                searcher,
                "search_google",
                new=AsyncMock(return_value=["https://b.com/CLAUDE.md"]),
            ), patch.object(
                searcher,
                "search_yandex",
                new=AsyncMock(return_value=["https://c.com/CLAUDE.md"]),
            ):
                return await searcher.search_all(
                    "CLAUDE.md",
                    engines=("duckduckgo", "google", "yandex"),
                )

        result = asyncio.run(_run())
        assert "https://a.com/CLAUDE.md" in result
        assert "https://b.com/CLAUDE.md" in result
        assert "https://c.com/CLAUDE.md" in result

    def test_search_all_deduplicates_across_engines(self):
        searcher = WebSearcher()
        shared = "https://example.com/CLAUDE.md"

        async def _run():
            with patch.object(
                searcher,
                "search_duckduckgo",
                new=AsyncMock(return_value=[shared]),
            ), patch.object(
                searcher,
                "search_google",
                new=AsyncMock(return_value=[shared]),
            ), patch.object(
                searcher,
                "search_yandex",
                new=AsyncMock(return_value=[]),
            ):
                return await searcher.search_all(shared, engines=("duckduckgo", "google", "yandex"))

        result = asyncio.run(_run())
        assert result.count(shared) == 1

    def test_search_all_skips_unknown_engine(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "search_duckduckgo",
                new=AsyncMock(return_value=["https://example.com/a"]),
            ):
                return await searcher.search_all(
                    "test", engines=("duckduckgo", "unknown_engine")
                )

        result = asyncio.run(_run())
        assert "https://example.com/a" in result


# ---------------------------------------------------------------------------
# WebSearcher.search_with_dorks tests
# ---------------------------------------------------------------------------


class TestWebSearcherSearchWithDorks:
    def test_search_with_dorks_aggregates_results(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "search_all",
                new=AsyncMock(return_value=["https://example.com/CLAUDE.md"]),
            ):
                return await searcher.search_with_dorks(
                    engines=("duckduckgo",),
                    max_dorks=2,
                )

        result = asyncio.run(_run())
        assert "https://example.com/CLAUDE.md" in result

    def test_search_with_dorks_respects_max_dorks(self):
        searcher = WebSearcher()
        call_count = {"n": 0}

        async def _patched_search_all(query, *, engines, max_results):
            call_count["n"] += 1
            return []

        async def _run():
            with patch.object(
                searcher,
                "search_all",
                new=AsyncMock(side_effect=_patched_search_all),
            ):
                await searcher.search_with_dorks(
                    engines=("duckduckgo",),
                    max_dorks=3,
                )

        asyncio.run(_run())
        assert call_count["n"] == 3

    def test_search_with_dorks_deduplicates_results(self):
        searcher = WebSearcher()
        dup_url = "https://example.com/CLAUDE.md"

        async def _run():
            with patch.object(
                searcher,
                "search_all",
                new=AsyncMock(return_value=[dup_url]),
            ):
                return await searcher.search_with_dorks(
                    engines=("duckduckgo",),
                    max_dorks=5,
                )

        result = asyncio.run(_run())
        assert result.count(dup_url) == 1


# ---------------------------------------------------------------------------
# WebSearcher context manager tests
# ---------------------------------------------------------------------------


class TestWebSearcherContextManager:
    def test_creates_and_closes_session(self):
        searcher = WebSearcher()

        async def _run():
            async with searcher as s:
                assert s._session is not None

        asyncio.run(_run())

    def test_uses_provided_session(self):
        mock_session = MagicMock()
        searcher = WebSearcher(session=mock_session)

        async def _run():
            async with searcher as s:
                assert s._session is mock_session

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# WebSearcher rate-limiting tests
# ---------------------------------------------------------------------------


class TestWebSearcherRequestDelay:
    def test_request_delay_parameter_is_stored(self):
        searcher = WebSearcher(request_delay=3.0)
        assert searcher._request_delay == 3.0

    def test_default_request_delay_is_positive(self):
        searcher = WebSearcher()
        assert searcher._request_delay > 0

    def test_sleep_called_between_dork_queries(self):
        """asyncio.sleep must be called once between each pair of queries."""
        from unittest.mock import patch

        searcher = WebSearcher(request_delay=2.0)
        sleep_calls: list[float] = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        async def _run():
            with patch("ai_finder.web_search.asyncio.sleep", new=fake_sleep), patch.object(
                searcher, "search_all", new=AsyncMock(return_value=[])
            ):
                async with searcher:
                    await searcher.search_with_dorks(
                        engines=("duckduckgo",),
                        max_dorks=3,
                    )

        asyncio.run(_run())
        # 3 dorks → 2 sleeps (before dork 2 and dork 3)
        assert len(sleep_calls) == 2
        assert all(s == 2.0 for s in sleep_calls)

    def test_no_sleep_before_first_dork_query(self):
        """No sleep should occur before the very first dork query."""
        from unittest.mock import patch

        searcher = WebSearcher(request_delay=1.0)
        sleep_calls: list[float] = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        async def _run():
            with patch("ai_finder.web_search.asyncio.sleep", new=fake_sleep), patch.object(
                searcher, "search_all", new=AsyncMock(return_value=[])
            ):
                async with searcher:
                    await searcher.search_with_dorks(
                        engines=("duckduckgo",),
                        max_dorks=1,
                    )

        asyncio.run(_run())
        assert sleep_calls == []

    def test_zero_delay_skips_sleep(self):
        """request_delay=0 must not call asyncio.sleep."""
        from unittest.mock import patch

        searcher = WebSearcher(request_delay=0)
        sleep_calls: list[float] = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        async def _run():
            with patch("ai_finder.web_search.asyncio.sleep", new=fake_sleep), patch.object(
                searcher, "search_all", new=AsyncMock(return_value=[])
            ):
                async with searcher:
                    await searcher.search_with_dorks(
                        engines=("duckduckgo",),
                        max_dorks=3,
                    )

        asyncio.run(_run())
        assert sleep_calls == []


# ---------------------------------------------------------------------------
# WebSearcher.search_bing tests
# ---------------------------------------------------------------------------


class TestWebSearcherBing:
    SAMPLE_HTML = (
        '<a href="https://example.com/CLAUDE.md">link</a>'
        '<a href="https://example.org/AGENTS.md">link2</a>'
    )

    def test_search_bing_returns_urls(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=self.SAMPLE_HTML),
            ):
                return await searcher.search_bing("CLAUDE.md")

        result = asyncio.run(_run())
        assert len(result) > 0
        assert any("CLAUDE.md" in u for u in result)

    def test_search_bing_respects_max_results(self):
        searcher = WebSearcher()
        many_links = "".join(
            f'<a href="https://site{i}.example.com/CLAUDE.md">l</a>'
            for i in range(20)
        )

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=many_links),
            ):
                return await searcher.search_bing("test", max_results=5)

        result = asyncio.run(_run())
        assert len(result) <= 5

    def test_search_bing_returns_empty_on_fetch_failure(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "_fetch_page",
                new=AsyncMock(return_value=""),
            ):
                return await searcher.search_bing("test query")

        result = asyncio.run(_run())
        assert result == []

    def test_search_bing_excluded_from_results(self):
        """bing.com URLs must never appear in the returned list."""
        html = (
            '<a href="https://www.bing.com/search?q=test">bing result</a>'
            '<a href="https://example.com/CLAUDE.md">real result</a>'
        )
        result = WebSearcher._extract_urls_from_html(html)
        assert all("bing.com" not in u for u in result)
        assert "https://example.com/CLAUDE.md" in result


# ---------------------------------------------------------------------------
# _build_dorks helper tests
# ---------------------------------------------------------------------------


class TestBuildDorks:
    def test_github_source_returns_github_dorks(self):
        from ai_finder.web_search import _build_dorks

        dorks = _build_dorks("github")
        assert len(dorks) > 0
        assert all(d.platform == "google" for d in dorks)

    def test_web_source_returns_web_dorks(self):
        from ai_finder.web_search import _build_dorks

        dorks = _build_dorks("web")
        assert len(dorks) > 0
        assert all(d.platform == "web" for d in dorks)

    def test_all_source_returns_both(self):
        from ai_finder.web_search import _build_dorks
        from ai_finder.discovery import GoogleDorkGenerator, WebDorkGenerator

        dorks = _build_dorks("all")
        github_count = len(GoogleDorkGenerator().all_dorks())
        web_count = len(WebDorkGenerator().all_dorks())
        # Total should be github + web (deduplicated, but no overlap expected)
        assert len(dorks) == github_count + web_count

    def test_all_source_is_deduplicated(self):
        from ai_finder.web_search import _build_dorks

        dorks = _build_dorks("all")
        queries = [d.query for d in dorks]
        assert len(queries) == len(set(queries))

    def test_invalid_source_raises_value_error(self):
        from ai_finder.web_search import _build_dorks

        with pytest.raises(ValueError, match="Invalid dork_sources"):
            _build_dorks("invalid_source")

    def test_github_and_web_queries_are_disjoint(self):
        """GitHub-targeted and open-web dork sets must not overlap."""
        from ai_finder.web_search import _build_dorks

        github_queries = {d.query for d in _build_dorks("github")}
        web_queries = {d.query for d in _build_dorks("web")}
        assert github_queries.isdisjoint(web_queries)


# ---------------------------------------------------------------------------
# search_with_dorks dork_sources tests
# ---------------------------------------------------------------------------


class TestSearchWithDorksSources:
    def test_dork_sources_github_uses_github_dorks(self):
        from ai_finder.discovery import GoogleDorkGenerator
        from ai_finder.web_search import _build_dorks

        expected = len(GoogleDorkGenerator().all_dorks())
        assert len(_build_dorks("github")) == expected

    def test_dork_sources_web_uses_web_dorks(self):
        from ai_finder.discovery import WebDorkGenerator
        from ai_finder.web_search import _build_dorks

        expected = len(WebDorkGenerator().all_dorks())
        assert len(_build_dorks("web")) == expected

    def test_search_with_dorks_passes_through_web_dork_sources(self):
        """search_with_dorks must use web dorks when dork_sources='web'."""
        from ai_finder.discovery import WebDorkGenerator

        searcher = WebSearcher()
        call_args: list[str] = []

        async def _patched_search_all(query, *, engines, max_results):
            call_args.append(query)
            return []

        async def _run():
            with patch.object(
                searcher,
                "search_all",
                new=AsyncMock(side_effect=_patched_search_all),
            ):
                async with searcher:
                    await searcher.search_with_dorks(
                        engines=("duckduckgo",),
                        max_dorks=None,
                        dork_sources="web",
                    )

        asyncio.run(_run())
        expected_web_queries = {d.query for d in WebDorkGenerator().all_dorks()}
        actual_queries = set(call_args)
        assert actual_queries == expected_web_queries

    def test_search_with_dorks_all_covers_both_generators(self):
        from ai_finder.discovery import GoogleDorkGenerator, WebDorkGenerator

        searcher = WebSearcher()
        call_args: list[str] = []

        async def _patched_search_all(query, *, engines, max_results):
            call_args.append(query)
            return []

        async def _run():
            with patch.object(
                searcher,
                "search_all",
                new=AsyncMock(side_effect=_patched_search_all),
            ):
                async with searcher:
                    await searcher.search_with_dorks(
                        engines=("duckduckgo",),
                        dork_sources="all",
                    )

        asyncio.run(_run())
        github_queries = {d.query for d in GoogleDorkGenerator().all_dorks()}
        web_queries = {d.query for d in WebDorkGenerator().all_dorks()}
        all_expected = github_queries | web_queries
        assert set(call_args) == all_expected

    def test_search_all_includes_bing_engine(self):
        searcher = WebSearcher()

        async def _run():
            with patch.object(
                searcher,
                "search_duckduckgo",
                new=AsyncMock(return_value=["https://a.com/CLAUDE.md"]),
            ), patch.object(
                searcher,
                "search_google",
                new=AsyncMock(return_value=["https://b.com/CLAUDE.md"]),
            ), patch.object(
                searcher,
                "search_bing",
                new=AsyncMock(return_value=["https://c.com/CLAUDE.md"]),
            ), patch.object(
                searcher,
                "search_yandex",
                new=AsyncMock(return_value=["https://d.com/CLAUDE.md"]),
            ):
                return await searcher.search_all(
                    "CLAUDE.md",
                    engines=("duckduckgo", "google", "bing", "yandex"),
                )

        result = asyncio.run(_run())
        assert "https://a.com/CLAUDE.md" in result
        assert "https://b.com/CLAUDE.md" in result
        assert "https://c.com/CLAUDE.md" in result
        assert "https://d.com/CLAUDE.md" in result
