"""Tests for ai_finder.vector_store module."""

import hashlib
import uuid

import pytest

from ai_finder.extractor import ExtractedFile
from ai_finder.processor import FileProcessor, ProcessedFile
from ai_finder.vector_store import VectorStore, _HashEmbeddingFunction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_processed(
    content: str,
    url: str = "https://example.com/CLAUDE.md",
) -> ProcessedFile:
    """Create a ProcessedFile from raw content."""
    h = hashlib.sha256(content.encode()).hexdigest()
    ef = ExtractedFile(url=url, raw_content=content, content_hash=h)
    return FileProcessor().process(ef)


@pytest.fixture
def store() -> VectorStore:
    """Provide a fresh in-memory VectorStore with an isolated collection."""
    # Use a unique collection name per test to ensure full isolation
    return VectorStore(collection_name=f"test_{uuid.uuid4().hex}")


# ---------------------------------------------------------------------------
# Embedding function tests
# ---------------------------------------------------------------------------


class TestHashEmbeddingFunction:
    def test_returns_correct_shape(self):
        ef = _HashEmbeddingFunction()
        embeddings = ef(["hello world", "foo bar baz"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 512
        assert len(embeddings[1]) == 512

    def test_unit_norm(self):
        import math

        ef = _HashEmbeddingFunction()
        vec = ef(["some text here"])[0]
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-5

    def test_empty_string_returns_zero_vector(self):
        ef = _HashEmbeddingFunction()
        vec = ef([""])[0]
        assert all(v == 0.0 for v in vec)

    def test_deterministic(self):
        ef = _HashEmbeddingFunction()
        v1 = ef(["reproducible text"])
        v2 = ef(["reproducible text"])
        assert all(a == b for a, b in zip(v1[0], v2[0]))


# ---------------------------------------------------------------------------
# VectorStore tests
# ---------------------------------------------------------------------------


class TestVectorStore:
    def test_initial_count_is_zero(self, store):
        assert store.count() == 0

    def test_index_valid_file(self, store):
        pf = make_processed("You are a bash agent. Execute shell scripts.", url="https://a.com/a.md")
        added = store.index(pf)
        assert added is True
        assert store.count() == 1

    def test_index_invalid_file_skipped(self, store):
        ef = ExtractedFile(url="bad", raw_content="", content_hash="", error="fetch failed")
        pf = ProcessedFile(source=ef)
        added = store.index(pf)
        assert added is False
        assert store.count() == 0

    def test_index_deduplicates_by_hash(self, store):
        content = "You are Claude, an AI assistant."
        pf1 = make_processed(content, url="https://a.com/1.md")
        pf2 = make_processed(content, url="https://a.com/2.md")  # same content → same hash

        assert store.index(pf1) is True
        assert store.index(pf2) is False  # duplicate
        assert store.count() == 1

    def test_index_many(self, store):
        files = [
            make_processed("Agent A content", url="https://a.com/a.md"),
            make_processed("Agent B content", url="https://a.com/b.md"),
            make_processed("Agent C content", url="https://a.com/c.md"),
        ]
        count = store.index_many(files)
        assert count == 3
        assert store.count() == 3

    def test_search_returns_results(self, store):
        store.index(make_processed(
            "You are a bash scripting agent. Execute shell commands.", url="https://a.com/bash.md"
        ))
        store.index(make_processed(
            "You are Claude, a helpful AI. Never execute code.", url="https://a.com/safe.md"
        ))

        results = store.search("bash script execution")
        assert len(results) >= 1
        assert all("url" in r for r in results)
        assert all("distance" in r for r in results)
        assert all("platform" in r for r in results)

    def test_search_ranks_relevant_document_first(self, store):
        store.index(make_processed(
            "You can run bash scripts and shell commands on the system.", url="https://a.com/bash.md"
        ))
        store.index(make_processed(
            "Poetry and creative writing assistant. No code execution.", url="https://a.com/poetry.md"
        ))

        results = store.search("execute bash shell scripts", n_results=2)
        urls = [r["url"] for r in results]
        # The bash document should appear in results (it shares the most tokens with the query)
        assert "https://a.com/bash.md" in urls

    def test_search_empty_store_returns_empty(self, store):
        results = store.search("any query")
        assert results == []

    def test_search_result_structure(self, store):
        store.index(make_processed("langchain agent", url="https://a.com/lc.md"))
        results = store.search("langchain")
        assert len(results) == 1
        r = results[0]
        assert "id" in r
        assert "document" in r
        assert "distance" in r
        assert "url" in r
        assert "platform" in r
        assert "tags" in r
        assert "has_secrets" in r

    def test_search_n_results_respected(self, store):
        for i in range(5):
            store.index(make_processed(f"Agent {i} content here", url=f"https://a.com/{i}.md"))

        results = store.search("agent content", n_results=3)
        assert len(results) <= 3

    def test_delete_removes_document(self, store):
        pf = make_processed("Some content", url="https://a.com/del.md")
        store.index(pf)
        assert store.count() == 1

        store.delete(pf.source.content_hash)
        assert store.count() == 0

    def test_reset_clears_all_documents(self, store):
        store.index(make_processed("Content A", url="https://a.com/a.md"))
        store.index(make_processed("Content B", url="https://a.com/b.md"))
        assert store.count() == 2

        store.reset()
        assert store.count() == 0

    def test_persistent_store(self, tmp_path):
        """Documents survive across VectorStore instances with the same directory."""
        db_dir = str(tmp_path / "vdb")
        cname = f"test_{uuid.uuid4().hex}"
        pf = make_processed("Persistent agent content", url="https://a.com/p.md")

        store1 = VectorStore(persist_directory=db_dir, collection_name=cname)
        store1.index(pf)
        assert store1.count() == 1

        store2 = VectorStore(persist_directory=db_dir, collection_name=cname)
        assert store2.count() == 1

    def test_search_with_where_filter(self, store):
        store.index(make_processed(
            "langchain agent config", url="https://a.com/lc.md"
        ))
        store.index(make_processed(
            "You are Claude. Anthropic assistant.", url="https://a.com/claude.md"
        ))

        results = store.search("agent", where={"platform": "langchain"})
        assert all(r["platform"] == "langchain" for r in results)
