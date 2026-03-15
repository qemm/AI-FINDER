"""
test_api.py — Tests for the AI-FINDER FastAPI web API.

Uses FastAPI's TestClient (synchronous httpx-based test runner) to exercise
every endpoint, covering both the happy-path and common error cases.
"""

from __future__ import annotations

import os
import tempfile
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Point the app at a temporary database so tests don't pollute each other.
# We set DB_PATH before importing api.main to ensure the module picks it up.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DB_PATH"] = _tmp_db.name

from api.main import app  # noqa: E402 — must follow env-var setup


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


class TestFrontend:
    def test_root_serves_html(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "AI-FINDER" in r.text

    def test_static_css_served(self, client: TestClient) -> None:
        r = client.get("/static/css/style.css")
        assert r.status_code == 200
        assert "text/css" in r.headers["content-type"]

    def test_static_js_served(self, client: TestClient) -> None:
        r = client.get("/static/js/app.js")
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_shape(self, client: TestClient) -> None:
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "with_secrets" in data
        assert "total_secret_findings" in data
        assert "by_platform" in data
        assert isinstance(data["by_platform"], dict)

    def test_stats_empty_db(self, client: TestClient) -> None:
        """Fresh DB should have zero totals."""
        r = client.get("/api/v1/stats")
        data = r.json()
        assert data["total"] == 0
        assert data["with_secrets"] == 0
        assert data["total_secret_findings"] == 0


# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------


class TestPlatforms:
    def test_platforms_empty(self, client: TestClient) -> None:
        r = client.get("/api/v1/platforms")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class TestResults:
    def test_list_results_defaults(self, client: TestClient) -> None:
        r = client.get("/api/v1/results")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_list_results_pagination_params(self, client: TestClient) -> None:
        r = client.get("/api/v1/results?page=1&per_page=5")
        assert r.status_code == 200
        data = r.json()
        assert data["per_page"] == 5
        assert data["page"] == 1

    def test_list_results_filter_platform(self, client: TestClient) -> None:
        r = client.get("/api/v1/results?platform=claude")
        assert r.status_code == 200

    def test_list_results_filter_secrets(self, client: TestClient) -> None:
        r = client.get("/api/v1/results?has_secrets=true")
        assert r.status_code == 200

    def test_list_results_search(self, client: TestClient) -> None:
        r = client.get("/api/v1/results?q=anthropic")
        assert r.status_code == 200

    def test_get_result_not_found(self, client: TestClient) -> None:
        r = client.get("/api/v1/results/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Dorks
# ---------------------------------------------------------------------------


class TestDorks:
    @pytest.mark.parametrize("dork_type", ["google", "s3", "github", "gitlab"])
    def test_dorks_type(self, client: TestClient, dork_type: str) -> None:
        r = client.get(f"/api/v1/dorks?type={dork_type}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "query" in item
            assert "description" in item
            assert "tags" in item

    def test_dorks_invalid_type(self, client: TestClient) -> None:
        r = client.get("/api/v1/dorks?type=invalid")
        assert r.status_code == 400

    def test_dorks_default_type(self, client: TestClient) -> None:
        r = client.get("/api/v1/dorks")
        assert r.status_code == 200
        assert len(r.json()) > 0


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_empty_urls(self, client: TestClient) -> None:
        """Scan with no URLs should still create a job."""
        with patch("api.main._run_scan", new_callable=AsyncMock):
            r = client.post("/api/v1/scan", json={"urls": []})
        assert r.status_code == 202
        data = r.json()
        assert "job_id" in data
        assert data["status"] in ("queued", "running", "done")

    def test_scan_returns_job_id(self, client: TestClient) -> None:
        with patch("api.main._run_scan", new_callable=AsyncMock):
            r = client.post("/api/v1/scan", json={"urls": ["https://example.com/CLAUDE.md"]})
        assert r.status_code == 202
        assert "job_id" in r.json()

    def test_job_poll(self, client: TestClient) -> None:
        """Create a scan job and poll its status."""
        with patch("api.main._run_scan", new_callable=AsyncMock):
            create = client.post("/api/v1/scan", json={"urls": []})
        job_id = create.json()["job_id"]

        r = client.get(f"/api/v1/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id

    def test_job_not_found(self, client: TestClient) -> None:
        r = client.get("/api/v1/jobs/no-such-job")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------


class TestCrawl:
    def test_crawl_returns_job(self, client: TestClient) -> None:
        with patch("api.main._run_crawl", new_callable=AsyncMock):
            r = client.post("/api/v1/crawl", json={})
        assert r.status_code == 202
        assert "job_id" in r.json()


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    def test_search_without_vector_db(self, client: TestClient) -> None:
        """Should return 503 if VECTOR_DB_PATH is not set."""
        r = client.get("/api/v1/search?q=langchain")
        assert r.status_code == 503

    def test_search_with_mock_vector_db(self, client: TestClient) -> None:
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {
                "url": "https://example.com/CLAUDE.md",
                "platform": "claude",
                "tags": "claude,has-persona",
                "distance": 0.123,
                "has_secrets": False,
                "document": "You are a helpful AI assistant trained by Anthropic.",
            }
        ]
        with (
            patch("api.main._VECTOR_DB_PATH", "/fake/path"),
            patch("api.main.VectorStore", return_value=mock_store),
        ):
            r = client.get("/api/v1/search?q=anthropic")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["platform"] == "claude"
        assert data[0]["distance"] == pytest.approx(0.123)
