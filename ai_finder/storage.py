"""
storage.py — Persistence layer (SQLite + optional JSON export).

Schema
------
files
  id            INTEGER PRIMARY KEY
  url           TEXT NOT NULL UNIQUE
  content_hash  TEXT NOT NULL
  platform      TEXT
  indexed_at    TEXT   (ISO-8601)
  raw_content   TEXT
  tags          TEXT   (comma-separated)
  has_secrets   INTEGER (0/1)

secret_findings
  id            INTEGER PRIMARY KEY
  file_id       INTEGER REFERENCES files(id)
  rule_name     TEXT
  line_number   INTEGER
  redacted      TEXT
  context       TEXT
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from ai_finder.extractor import ExtractedFile
from ai_finder.processor import ProcessedFile
from ai_finder.scanner import SecretScanner

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT    NOT NULL UNIQUE,
    content_hash TEXT    NOT NULL,
    platform     TEXT    DEFAULT 'unknown',
    indexed_at   TEXT    NOT NULL,
    raw_content  TEXT,
    tags         TEXT    DEFAULT '',
    has_secrets  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS secret_findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    rule_name   TEXT,
    line_number INTEGER,
    redacted    TEXT,
    context     TEXT
);
"""


# ---------------------------------------------------------------------------
# Storage class
# ---------------------------------------------------------------------------


class Storage:
    """Thread-safe SQLite-backed storage for discovered AI agent files."""

    def __init__(self, db_path: str = "ai_finder.db") -> None:
        self._db_path = db_path
        self._scanner = SecretScanner()
        self._init_db()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, processed: ProcessedFile) -> Optional[int]:
        """Persist a :class:`ProcessedFile`; skip if hash already stored.

        Returns the row *id* (new or existing), or ``None`` on failure.
        """
        ef: ExtractedFile = processed.source
        if not ef.is_valid:
            return None

        secret_report = self._scanner.report(ef.raw_content, ef.url)
        now_iso = datetime.now(timezone.utc).isoformat()
        tags_str = ",".join(processed.tags)

        with self._conn() as conn:
            # Check for duplicate by content hash
            row = conn.execute(
                "SELECT id FROM files WHERE content_hash = ?",
                (ef.content_hash,),
            ).fetchone()
            if row:
                return int(row["id"])  # already stored

            cur = conn.execute(
                """
                INSERT INTO files (url, content_hash, platform, indexed_at,
                                   raw_content, tags, has_secrets)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ef.url,
                    ef.content_hash,
                    processed.platform,
                    now_iso,
                    ef.raw_content,
                    tags_str,
                    int(secret_report["has_secrets"]),
                ),
            )
            file_id = cur.lastrowid

            # Store individual secret findings
            for finding in secret_report["findings"]:
                conn.execute(
                    """
                    INSERT INTO secret_findings
                        (file_id, rule_name, line_number, redacted, context)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        finding["rule"],
                        finding["line"],
                        finding["redacted"],
                        finding["context"],
                    ),
                )

            return file_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_url(self, url: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE url = ?", (url,)
            ).fetchone()
            return dict(row) if row else None

    def get_by_hash(self, content_hash: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return dict(row) if row else None

    def list_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM files ORDER BY indexed_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_by_platform(self, platform: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE platform = ? ORDER BY indexed_at DESC",
                (platform,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_with_secrets(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE has_secrets = 1 ORDER BY indexed_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
            return int(row[0])

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self, output_path: str) -> None:
        """Export the full catalogue to a JSON file."""
        with self._conn() as conn:
            files = [dict(r) for r in conn.execute("SELECT * FROM files").fetchall()]
            findings = [
                dict(r) for r in conn.execute("SELECT * FROM secret_findings").fetchall()
            ]

        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_files": len(files),
            "files": files,
            "secret_findings": findings,
        }
        Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
