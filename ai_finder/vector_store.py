"""
vector_store.py — Vector database integration for semantic search.

Indexes the content of discovered AI agent files into a ChromaDB collection
so that natural-language queries can be used to find relevant entries.

Example
-------
    from ai_finder.vector_store import VectorStore
    from ai_finder.processor import ProcessedFile

    store = VectorStore(persist_directory="./vector_db")
    store.index(processed_file)
    results = store.search("agents with permission to run bash scripts")

The module ships with a lightweight, **offline-capable** embedding function
built on numpy so it works without network access or large model downloads.
A custom :class:`chromadb.EmbeddingFunction` can be injected at construction
time to swap in any richer model (e.g. OpenAI, Cohere, sentence-transformers).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

import numpy as np

import chromadb
from chromadb import EphemeralClient, PersistentClient
from chromadb.api.types import EmbeddingFunction, Embeddings

from ai_finder.processor import ProcessedFile
from ai_finder.scanner import SecretScanner

# ---------------------------------------------------------------------------
# Default embedding function (offline, no model download required)
# ---------------------------------------------------------------------------

_EMBEDDING_DIM = 512  # Vector dimensionality


class _HashEmbeddingFunction(EmbeddingFunction):
    """Lightweight, deterministic embedding function using the hash trick.

    Maps tokenised text into a fixed-size float vector via feature hashing
    and L2 normalisation.  Works entirely offline with no model downloads.

    This is intentionally simple — it captures lexical similarity well and
    performs reasonably for the short AI-config documents targeted here.
    Users can swap in a richer embedding function (e.g. sentence-transformers)
    by passing ``embedding_fn`` to :class:`VectorStore`.
    """

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:  # required by newer chromadb versions
        return "hash_embedding"

    def get_config(self) -> dict:  # required by newer chromadb versions
        return {"dim": _EMBEDDING_DIM}

    def __call__(self, input: list[str]) -> Embeddings:  # type: ignore[override]
        result: list[list[float]] = []
        for text in input:
            vec = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            tokens = re.findall(r"\b\w+\b", text.lower())
            for token in tokens:
                # Feature hashing: two independent hash positions per token
                h1 = int(hashlib.md5(token.encode()).hexdigest(), 16)
                h2 = int(hashlib.sha1(token.encode()).hexdigest(), 16)
                vec[h1 % _EMBEDDING_DIM] += 1.0
                vec[h2 % _EMBEDDING_DIM] += 0.5
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            result.append(vec.tolist())
        return result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

_COLLECTION_NAME = "ai_agent_files"


class VectorStore:
    """ChromaDB-backed vector store for AI agent file content.

    Parameters
    ----------
    persist_directory:
        Path to a directory where ChromaDB will persist its data.
        Pass ``None`` (default) to use an in-memory ephemeral client.
    embedding_fn:
        A ChromaDB :class:`~chromadb.api.types.EmbeddingFunction` to use for
        generating embeddings.  Defaults to :class:`_HashEmbeddingFunction`.
    collection_name:
        Name of the ChromaDB collection.  Defaults to ``"ai_agent_files"``.
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        embedding_fn: Optional[EmbeddingFunction] = None,
        collection_name: str = _COLLECTION_NAME,
    ) -> None:
        if persist_directory is not None:
            self._client = PersistentClient(path=persist_directory)
        else:
            self._client = EphemeralClient()

        self._ef = embedding_fn or _HashEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index(self, processed: ProcessedFile) -> bool:
        """Add a single :class:`ProcessedFile` to the vector index.

        Documents are deduplicated by their content hash — re-indexing the
        same content is a no-op.

        Returns ``True`` if the document was newly added, ``False`` if it was
        already present or invalid.
        """
        ef = processed.source
        if not ef.is_valid:
            return False

        doc_id = ef.content_hash
        # Avoid duplicates
        existing = self._collection.get(ids=[doc_id])
        if existing["ids"]:
            return False

        document = self._build_document(processed)
        metadata = self._build_metadata(processed)

        self._collection.add(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )
        return True

    def index_many(self, processed_files: list[ProcessedFile]) -> int:
        """Index multiple :class:`ProcessedFile` objects.

        Returns the count of newly added documents.
        """
        return sum(self.index(pf) for pf in processed_files)

    # ------------------------------------------------------------------
    # Searching
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict[str, Any]] = None,
    ) -> list[dict]:
        """Perform a semantic search against indexed content.

        Parameters
        ----------
        query:
            Natural-language query, e.g.
            ``"agents with permission to execute bash scripts"``.
        n_results:
            Maximum number of results to return.
        where:
            Optional ChromaDB ``where`` filter dict to narrow results by
            metadata (e.g. ``{"platform": "claude"}``).

        Returns
        -------
        list[dict]
            Each result dict contains:
            ``id``, ``document`` (excerpt), ``distance``, and all metadata
            fields (``url``, ``platform``, ``tags``, ``has_secrets``).
        """
        total = self.count()
        if total == 0:
            return []

        effective_n = min(n_results, total)

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": effective_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        results: list[dict] = []
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
            results.append(
                {
                    "id": doc_id,
                    "document": doc[:500],  # truncated excerpt
                    "distance": round(float(dist), 4),
                    "url": meta.get("url", ""),
                    "platform": meta.get("platform", "unknown"),
                    "tags": meta.get("tags", ""),
                    "has_secrets": bool(meta.get("has_secrets", 0)),
                }
            )

        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the total number of indexed documents."""
        return self._collection.count()

    def delete(self, content_hash: str) -> None:
        """Remove a document from the index by its content hash."""
        self._collection.delete(ids=[content_hash])

    def reset(self) -> None:
        """Delete and recreate the collection (removes all documents)."""
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_document(processed: ProcessedFile) -> str:
        """Build the text document string to embed for a ProcessedFile."""
        ef = processed.source
        parts: list[str] = []

        # Prioritise system-prompt blocks if available
        if ef.system_prompt_blocks:
            parts.extend(ef.system_prompt_blocks[:3])

        # Append raw content (truncated to keep embeddings tractable)
        if ef.raw_content:
            parts.append(ef.raw_content[:4000])

        text = "\n\n".join(parts)
        return text[:8000]  # hard cap

    @staticmethod
    def _build_metadata(processed: ProcessedFile) -> dict:
        """Build the ChromaDB metadata dict for a ProcessedFile."""
        ef = processed.source
        has_secrets = int(SecretScanner().has_secrets(ef.raw_content))
        return {
            "url": ef.url,
            "platform": processed.platform,
            "tags": ",".join(processed.tags),
            "has_secrets": has_secrets,
            "content_hash": ef.content_hash,
        }
