"""Tests for ai_finder.storage module."""

import hashlib
import os
import tempfile
import pytest

from ai_finder.extractor import ExtractedFile
from ai_finder.processor import FileProcessor, ProcessedFile
from ai_finder.storage import Storage


def make_processed(
    content: str,
    url: str = "https://example.com/CLAUDE.md",
) -> ProcessedFile:
    """Helper: create a ProcessedFile from raw content."""
    h = hashlib.sha256(content.encode()).hexdigest()
    ef = ExtractedFile(url=url, raw_content=content, content_hash=h)
    return FileProcessor().process(ef)


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a fresh temporary SQLite database path."""
    return str(tmp_path / "test.db")


class TestStorage:
    def test_save_and_retrieve_by_url(self, tmp_db):
        storage = Storage(tmp_db)
        pf = make_processed("You are Claude, a helpful assistant.", url="https://ex.com/a.md")
        row_id = storage.save(pf)
        assert row_id is not None

        record = storage.get_by_url("https://ex.com/a.md")
        assert record is not None
        assert record["url"] == "https://ex.com/a.md"
        assert record["platform"] == "claude"

    def test_save_deduplicates_by_hash(self, tmp_db):
        storage = Storage(tmp_db)
        content = "from langchain import LLMChain"
        pf1 = make_processed(content, url="https://ex.com/file1.py")
        pf2 = make_processed(content, url="https://ex.com/file2.py")

        id1 = storage.save(pf1)
        id2 = storage.save(pf2)
        # Second save should return the existing row ID (same hash)
        assert id1 == id2
        assert storage.count() == 1

    def test_save_skips_invalid_file(self, tmp_db):
        storage = Storage(tmp_db)
        ef = ExtractedFile(url="x", raw_content="", content_hash="", error="fail")
        pf = ProcessedFile(source=ef)
        result = storage.save(pf)
        assert result is None
        assert storage.count() == 0

    def test_count_increments(self, tmp_db):
        storage = Storage(tmp_db)
        assert storage.count() == 0
        storage.save(make_processed("content A", url="https://ex.com/a.md"))
        storage.save(make_processed("content B", url="https://ex.com/b.md"))
        assert storage.count() == 2

    def test_list_all_returns_records(self, tmp_db):
        storage = Storage(tmp_db)
        storage.save(make_processed("crewai content", url="https://ex.com/crew.yaml"))
        rows = storage.list_all()
        assert len(rows) == 1
        assert rows[0]["url"] == "https://ex.com/crew.yaml"

    def test_list_by_platform(self, tmp_db):
        storage = Storage(tmp_db)
        storage.save(make_processed("from langchain import LLMChain", url="https://a.com/l.py"))
        storage.save(make_processed("from crewai import Crew", url="https://b.com/c.py"))

        langchain_rows = storage.list_by_platform("langchain")
        assert len(langchain_rows) >= 1
        assert all(r["platform"] == "langchain" for r in langchain_rows)

    def test_list_with_secrets(self, tmp_db):
        storage = Storage(tmp_db)
        clean = make_processed("Clean content here.", url="https://a.com/clean.md")
        leaky = make_processed(
            "api_key = sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
            url="https://b.com/leak.md",
        )
        storage.save(clean)
        storage.save(leaky)

        secrets_rows = storage.list_with_secrets()
        urls_with_secrets = [r["url"] for r in secrets_rows]
        assert "https://b.com/leak.md" in urls_with_secrets
        assert "https://a.com/clean.md" not in urls_with_secrets

    def test_get_by_hash(self, tmp_db):
        storage = Storage(tmp_db)
        pf = make_processed("unique content xyz", url="https://ex.com/u.md")
        storage.save(pf)

        h = hashlib.sha256("unique content xyz".encode()).hexdigest()
        record = storage.get_by_hash(h)
        assert record is not None
        assert record["content_hash"] == h

    def test_export_json(self, tmp_db, tmp_path):
        storage = Storage(tmp_db)
        storage.save(make_processed("Some AI config content.", url="https://ex.com/x.md"))
        json_path = str(tmp_path / "export.json")
        storage.export_json(json_path)

        import json
        with open(json_path) as f:
            data = json.loads(f.read())
        assert "files" in data
        assert "secret_findings" in data
        assert data["total_files"] >= 1
        assert "exported_at" in data
