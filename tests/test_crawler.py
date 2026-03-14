"""Tests for ai_finder.crawler module."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_finder.crawler import Crawler, load_urls, update_urls_file


# ---------------------------------------------------------------------------
# File helper tests
# ---------------------------------------------------------------------------


class TestLoadUrls:
    def test_returns_empty_set_when_file_missing(self, tmp_path):
        path = str(tmp_path / "nonexistent.txt")
        assert load_urls(path) == set()

    def test_loads_urls_from_file(self, tmp_path):
        p = tmp_path / "urls.txt"
        p.write_text(
            "https://example.com/a\nhttps://example.com/b\n", encoding="utf-8"
        )
        result = load_urls(str(p))
        assert result == {"https://example.com/a", "https://example.com/b"}

    def test_ignores_blank_lines(self, tmp_path):
        p = tmp_path / "urls.txt"
        p.write_text("\nhttps://example.com/a\n\n", encoding="utf-8")
        result = load_urls(str(p))
        assert result == {"https://example.com/a"}

    def test_ignores_comment_lines(self, tmp_path):
        p = tmp_path / "urls.txt"
        p.write_text(
            "# comment\nhttps://example.com/a\n# another comment\n",
            encoding="utf-8",
        )
        result = load_urls(str(p))
        assert result == {"https://example.com/a"}

    def test_strips_whitespace(self, tmp_path):
        p = tmp_path / "urls.txt"
        p.write_text("  https://example.com/a  \n", encoding="utf-8")
        result = load_urls(str(p))
        assert result == {"https://example.com/a"}


class TestUpdateUrlsFile:
    def test_creates_file_if_missing(self, tmp_path):
        path = str(tmp_path / "urls.txt")
        update_urls_file(path, set(), ["https://example.com/new"])
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "https://example.com/new" in content

    def test_merges_existing_and_new(self, tmp_path):
        path = str(tmp_path / "urls.txt")
        existing = {"https://example.com/a"}
        new_urls = ["https://example.com/b"]
        update_urls_file(path, existing, new_urls)
        result = load_urls(path)
        assert result == {"https://example.com/a", "https://example.com/b"}

    def test_deduplicates_overlap(self, tmp_path):
        path = str(tmp_path / "urls.txt")
        existing = {"https://example.com/a"}
        new_urls = ["https://example.com/a", "https://example.com/b"]
        update_urls_file(path, existing, new_urls)
        result = load_urls(path)
        assert result == {"https://example.com/a", "https://example.com/b"}

    def test_output_sorted(self, tmp_path):
        path = str(tmp_path / "urls.txt")
        update_urls_file(
            path,
            {"https://z.example.com"},
            ["https://a.example.com", "https://m.example.com"],
        )
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        assert lines == sorted(lines)

    def test_file_ends_with_newline(self, tmp_path):
        path = str(tmp_path / "urls.txt")
        update_urls_file(path, set(), ["https://example.com/a"])
        content = Path(path).read_text(encoding="utf-8")
        assert content.endswith("\n")


# ---------------------------------------------------------------------------
# Crawler.check_url tests
# ---------------------------------------------------------------------------


class TestCrawlerCheckUrl:
    def _make_crawler(self) -> Crawler:
        return Crawler()

    def test_returns_true_for_2xx(self):
        crawler = self._make_crawler()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.head = MagicMock(return_value=mock_resp)

            return await crawler.check_url(mock_session, "https://example.com/file.md")

        result = asyncio.run(_run())
        assert result is True

    def test_returns_false_for_404(self):
        crawler = self._make_crawler()

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status = 404
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.head = MagicMock(return_value=mock_resp)

            return await crawler.check_url(mock_session, "https://example.com/missing")

        result = asyncio.run(_run())
        assert result is False

    def test_returns_false_on_network_error(self):
        crawler = self._make_crawler()

        async def _run():
            mock_session = MagicMock()
            mock_session.head = MagicMock(side_effect=Exception("Connection error"))
            return await crawler.check_url(mock_session, "https://example.com/file.md")

        result = asyncio.run(_run())
        assert result is False

    def test_falls_back_to_get_on_405(self):
        crawler = self._make_crawler()

        async def _run():
            head_resp = MagicMock()
            head_resp.status = 405
            head_resp.__aenter__ = AsyncMock(return_value=head_resp)
            head_resp.__aexit__ = AsyncMock(return_value=False)

            get_resp = MagicMock()
            get_resp.status = 200
            get_resp.__aenter__ = AsyncMock(return_value=get_resp)
            get_resp.__aexit__ = AsyncMock(return_value=False)

            mock_session = MagicMock()
            mock_session.head = MagicMock(return_value=head_resp)
            mock_session.get = MagicMock(return_value=get_resp)

            return await crawler.check_url(mock_session, "https://example.com/file.md")

        result = asyncio.run(_run())
        assert result is True


# ---------------------------------------------------------------------------
# Crawler.filter_reachable tests
# ---------------------------------------------------------------------------


class TestCrawlerFilterReachable:
    def test_returns_only_reachable_urls(self):
        crawler = Crawler()

        async def _run():
            with patch.object(
                crawler,
                "check_url",
                new=AsyncMock(
                    side_effect=lambda session, url: url.endswith("/good")
                ),
            ):
                import aiohttp as _aiohttp

                with patch("aiohttp.ClientSession") as mock_cls:
                    mock_session = AsyncMock()
                    mock_cls.return_value.__aenter__ = AsyncMock(
                        return_value=mock_session
                    )
                    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                    return await crawler.filter_reachable(
                        [
                            "https://example.com/good",
                            "https://example.com/bad",
                        ]
                    )

        result = asyncio.run(_run())
        assert "https://example.com/good" in result
        assert "https://example.com/bad" not in result

    def test_returns_empty_list_when_all_unreachable(self):
        crawler = Crawler()

        async def _run():
            with patch.object(
                crawler, "check_url", new=AsyncMock(return_value=False)
            ):
                with patch("aiohttp.ClientSession") as mock_cls:
                    mock_session = AsyncMock()
                    mock_cls.return_value.__aenter__ = AsyncMock(
                        return_value=mock_session
                    )
                    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                    return await crawler.filter_reachable(
                        ["https://example.com/a", "https://example.com/b"]
                    )

        result = asyncio.run(_run())
        assert result == []


# ---------------------------------------------------------------------------
# Crawler.discover_urls tests (mocked search APIs)
# ---------------------------------------------------------------------------


class TestCrawlerDiscoverUrls:
    def test_discover_returns_github_urls(self):
        crawler = Crawler(github_token="test-token")

        async def _run():
            with patch(
                "ai_finder.extractor.FileExtractor.search_github",
                new=AsyncMock(
                    return_value=["https://raw.githubusercontent.com/u/r/main/CLAUDE.md"]
                ),
            ), patch(
                "ai_finder.extractor.FileExtractor.search_gitlab",
                new=AsyncMock(return_value=[]),
            ):
                return await crawler.discover_urls(use_github=True, use_gitlab=False)

        urls = asyncio.run(_run())
        assert "https://raw.githubusercontent.com/u/r/main/CLAUDE.md" in urls

    def test_discover_deduplicates_results(self):
        crawler = Crawler()
        dup_url = "https://raw.githubusercontent.com/u/r/main/CLAUDE.md"

        async def _run():
            with patch(
                "ai_finder.extractor.FileExtractor.search_github",
                new=AsyncMock(return_value=[dup_url, dup_url]),
            ), patch(
                "ai_finder.extractor.FileExtractor.search_gitlab",
                new=AsyncMock(return_value=[dup_url]),
            ):
                return await crawler.discover_urls()

        urls = asyncio.run(_run())
        assert urls.count(dup_url) == 1

    def test_discover_respects_max_queries(self):
        crawler = Crawler()
        call_count = {"github": 0}

        async def patched_search_github(self, extractor, max_queries, per_page):
            from ai_finder.discovery import GitHubQueryGenerator
            queries = GitHubQueryGenerator().all_queries()
            if max_queries is not None:
                queries = queries[:max_queries]
            for _ in queries:
                call_count["github"] += 1
            return []

        async def _run():
            with patch.object(
                Crawler, "_search_github", new=patched_search_github
            ), patch.object(
                Crawler, "_search_gitlab", new=AsyncMock(return_value=[])
            ):
                return await crawler.discover_urls(
                    use_github=True,
                    use_gitlab=False,
                    max_queries=3,
                )

        asyncio.run(_run())
        assert call_count["github"] == 3

    def test_discover_gitlab_only(self):
        crawler = Crawler()

        async def _run():
            with patch(
                "ai_finder.extractor.FileExtractor.search_gitlab",
                new=AsyncMock(
                    return_value=[
                        "https://gitlab.com/api/v4/projects/1/repository/files/CLAUDE.md/raw?ref=main"
                    ]
                ),
            ), patch(
                "ai_finder.extractor.FileExtractor.search_github",
                new=AsyncMock(return_value=[]),
            ):
                return await crawler.discover_urls(use_github=False, use_gitlab=True)

        urls = asyncio.run(_run())
        assert any(u.startswith("https://gitlab.com/") for u in urls)


# ---------------------------------------------------------------------------
# Crawler.crawl integration tests (all I/O mocked)
# ---------------------------------------------------------------------------


class TestCrawlerCrawl:
    def test_crawl_writes_new_urls_to_file(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")
        new_url = "https://raw.githubusercontent.com/u/r/main/CLAUDE.md"

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[new_url]),
            ), patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[new_url]),
            ):
                return await crawler.crawl(urls_file=urls_file)

        result = asyncio.run(_run())
        assert result == [new_url]
        assert new_url in load_urls(urls_file)

    def test_crawl_skips_existing_urls(self, tmp_path):
        crawler = Crawler()
        existing_url = "https://raw.githubusercontent.com/u/r/main/CLAUDE.md"
        urls_file = str(tmp_path / "urls.txt")
        # Pre-populate the file
        Path(urls_file).write_text(existing_url + "\n", encoding="utf-8")

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[existing_url]),
            ), patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[]),
            ) as mock_check:
                result = await crawler.crawl(urls_file=urls_file)
                # filter_reachable must NOT be called since there are no new URLs
                mock_check.assert_not_called()
                return result

        result = asyncio.run(_run())
        assert result == []

    def test_crawl_no_check_skips_reachability(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")
        new_url = "https://raw.githubusercontent.com/u/r/main/AGENTS.md"

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[new_url]),
            ), patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[]),
            ) as mock_check:
                result = await crawler.crawl(
                    urls_file=urls_file, check_reachability=False
                )
                mock_check.assert_not_called()
                return result

        result = asyncio.run(_run())
        assert result == [new_url]
        assert new_url in load_urls(urls_file)

    def test_crawl_creates_urls_file_if_missing(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "subdir" / "urls.txt")
        # Create the parent directory
        (tmp_path / "subdir").mkdir()
        new_url = "https://raw.githubusercontent.com/u/r/main/CLAUDE.md"

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[new_url]),
            ), patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[new_url]),
            ):
                return await crawler.crawl(urls_file=urls_file)

        asyncio.run(_run())
        assert Path(urls_file).exists()

    def test_crawl_returns_empty_when_none_found(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[]),
            ):
                return await crawler.crawl(urls_file=urls_file)

        result = asyncio.run(_run())
        assert result == []
        # File should not be created when nothing was found
        assert not Path(urls_file).exists()

    def test_crawl_with_target_url_enumerates_paths(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")
        target = "https://example.com"
        found_url = "https://example.com/CLAUDE.md"

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[]),
            ), patch.object(
                crawler,
                "enumerate_paths",
                new=AsyncMock(return_value=[found_url]),
            ) as mock_enum, patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[found_url]),
            ):
                result = await crawler.crawl(
                    urls_file=urls_file, target_url=target
                )
                mock_enum.assert_called_once_with(target, check_reachability=False)
                return result

        result = asyncio.run(_run())
        assert result == [found_url]
        assert found_url in load_urls(urls_file)

    def test_crawl_target_url_deduplicates_with_api_results(self, tmp_path):
        crawler = Crawler()
        urls_file = str(tmp_path / "urls.txt")
        shared_url = "https://example.com/CLAUDE.md"

        async def _run():
            with patch.object(
                crawler,
                "discover_urls",
                new=AsyncMock(return_value=[shared_url]),
            ), patch.object(
                crawler,
                "enumerate_paths",
                new=AsyncMock(return_value=[shared_url]),
            ), patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(return_value=[shared_url]),
            ):
                return await crawler.crawl(
                    urls_file=urls_file,
                    target_url="https://example.com",
                )

        result = asyncio.run(_run())
        # Despite appearing from both sources, the URL should appear only once
        assert result.count(shared_url) == 1


# ---------------------------------------------------------------------------
# Crawler.enumerate_paths tests
# ---------------------------------------------------------------------------


class TestCrawlerEnumeratePaths:
    def test_enumerate_paths_builds_candidates_from_target(self):
        crawler = Crawler()
        target = "https://example.com"

        async def _run():
            return await crawler.enumerate_paths(
                target, check_reachability=False
            )

        result = asyncio.run(_run())
        assert "https://example.com/CLAUDE.md" in result
        assert "https://example.com/AGENTS.md" in result
        assert "https://example.com/.cursorrules" in result

    def test_enumerate_paths_strips_trailing_slash_from_base(self):
        crawler = Crawler()

        async def _run():
            return await crawler.enumerate_paths(
                "https://example.com/", check_reachability=False
            )

        result = asyncio.run(_run())
        # Should not produce double slashes
        assert all("example.com//" not in url for url in result)
        assert "https://example.com/CLAUDE.md" in result

    def test_enumerate_paths_uses_custom_paths(self):
        crawler = Crawler()
        custom_paths = ["custom/path.md", "other/file.txt"]

        async def _run():
            return await crawler.enumerate_paths(
                "https://example.com",
                paths=custom_paths,
                check_reachability=False,
            )

        result = asyncio.run(_run())
        assert result == [
            "https://example.com/custom/path.md",
            "https://example.com/other/file.txt",
        ]

    def test_enumerate_paths_filters_reachable(self):
        crawler = Crawler()

        async def _run():
            with patch.object(
                crawler,
                "filter_reachable",
                new=AsyncMock(
                    return_value=["https://example.com/CLAUDE.md"]
                ),
            ) as mock_filter:
                result = await crawler.enumerate_paths(
                    "https://example.com", check_reachability=True
                )
                mock_filter.assert_called_once()
                return result

        result = asyncio.run(_run())
        assert result == ["https://example.com/CLAUDE.md"]

    def test_enumerate_paths_covers_all_default_filenames(self):
        from ai_finder.discovery import TARGET_FILENAMES

        crawler = Crawler()

        async def _run():
            return await crawler.enumerate_paths(
                "https://example.com", check_reachability=False
            )

        result = asyncio.run(_run())
        assert len(result) == len(TARGET_FILENAMES)
