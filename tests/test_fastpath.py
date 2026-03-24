"""Tests for mtime+size fast-path to skip redundant file reads."""

import sqlite3
import time

from stele_context.engine import Stele
from stele_context.engine_utils import file_unchanged
from stele_context.storage import StorageBackend


class TestFileUnchangedHelper:
    """Tests for the file_unchanged() fast-path helper."""

    def test_unchanged_file_returns_true(self, tmp_path):
        """Matching mtime+size returns True."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        st = f.stat()
        stored_doc = {
            "last_modified": st.st_mtime,
            "file_size": st.st_size,
        }
        assert file_unchanged(f, stored_doc) is True

    def test_changed_content_returns_false(self, tmp_path):
        """Different size after content change returns False."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        st = f.stat()
        stored_doc = {
            "last_modified": st.st_mtime,
            "file_size": st.st_size,
        }
        f.write_text("hello world")  # changes size and mtime
        assert file_unchanged(f, stored_doc) is False

    def test_missing_file_size_returns_false(self, tmp_path):
        """Pre-migration docs without file_size fall through to full read."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        stored_doc = {
            "last_modified": f.stat().st_mtime,
            "file_size": None,
        }
        assert file_unchanged(f, stored_doc) is False

    def test_missing_file_returns_false(self, tmp_path):
        """Non-existent file returns False (stat error)."""
        stored_doc = {"last_modified": 1.0, "file_size": 5}
        assert file_unchanged(tmp_path / "gone.txt", stored_doc) is False

    def test_size_match_mtime_mismatch_returns_false(self, tmp_path):
        """Same size but different mtime returns False."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        stored_doc = {
            "last_modified": f.stat().st_mtime - 1.0,
            "file_size": f.stat().st_size,
        }
        assert file_unchanged(f, stored_doc) is False


class TestFileSizeMigration:
    """Tests for the file_size column migration."""

    def test_file_size_column_exists(self, tmp_path):
        """Migration adds file_size to documents table."""
        storage = StorageBackend(base_dir=str(tmp_path / "storage"))
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = {row[1] for row in cursor.fetchall()}
        assert "file_size" in columns

    def test_store_document_with_file_size(self, tmp_path):
        """store_document persists file_size."""
        storage = StorageBackend(base_dir=str(tmp_path / "storage"))
        storage.store_document("test.txt", "hash123", 1, 1000.0, file_size=42)
        doc = storage.get_document("test.txt")
        assert doc["file_size"] == 42

    def test_store_document_without_file_size(self, tmp_path):
        """Backward compat: file_size defaults to None."""
        storage = StorageBackend(base_dir=str(tmp_path / "storage"))
        storage.store_document("test.txt", "hash123", 1, 1000.0)
        doc = storage.get_document("test.txt")
        assert doc["file_size"] is None

    def test_migration_from_old_schema(self, tmp_path):
        """file_size column added to existing DB without it."""
        db_path = tmp_path / "storage" / "stele_context.db"
        db_path.parent.mkdir(parents=True)

        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE documents (
                    document_path TEXT PRIMARY KEY,
                    content_hash TEXT, chunk_count INTEGER,
                    indexed_at REAL, last_modified REAL)
            """)
            conn.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
                ("old.txt", "oldhash", 1, 1.0, 2.0),
            )
            # Create minimal required tables
            conn.execute("""
                CREATE TABLE chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    semantic_signature BLOB NOT NULL,
                    start_pos INTEGER NOT NULL,
                    end_pos INTEGER NOT NULL,
                    token_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1)
            """)
            conn.execute("""
                CREATE TABLE chunk_history (
                    chunk_id TEXT, version INTEGER,
                    content_hash TEXT, semantic_signature BLOB,
                    created_at REAL, PRIMARY KEY (chunk_id, version))
            """)
            conn.execute("""
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL, last_updated REAL,
                    turn_count INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0)
            """)
            conn.execute("""
                CREATE TABLE session_chunks (
                    session_id TEXT, chunk_id TEXT, turn_number INTEGER,
                    kv_path TEXT, relevance_score REAL DEFAULT 1.0,
                    PRIMARY KEY (session_id, chunk_id, turn_number))
            """)
            conn.commit()

        storage = StorageBackend(base_dir=str(tmp_path / "storage"))
        doc = storage.get_document("old.txt")
        assert doc is not None
        assert doc["file_size"] is None  # migrated column has NULL


class TestIndexFastPath:
    """Tests for fast-path skip in index_documents."""

    def test_index_skip_on_unchanged_file(self, tmp_path):
        """Second index of unchanged file skips without reading."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        r1 = engine.index_documents([str(f)])
        assert len(r1["indexed"]) == 1

        # Second index should skip via fast-path (no content read)
        r2 = engine.index_documents([str(f)])
        assert len(r2["skipped"]) == 1
        assert r2["skipped"][0]["reason"] == "Unchanged"

    def test_index_detects_changed_file(self, tmp_path):
        """Modified file triggers re-indexing."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        time.sleep(0.05)
        f.write_text("goodbye world")

        r2 = engine.index_documents([str(f)])
        assert len(r2["indexed"]) == 1

    def test_force_reindex_bypasses_fastpath(self, tmp_path):
        """force_reindex=True bypasses the fast-path."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        r2 = engine.index_documents([str(f)], force_reindex=True)
        assert len(r2["indexed"]) == 1
        assert len(r2["skipped"]) == 0

    def test_file_size_stored_after_index(self, tmp_path):
        """file_size is persisted in the documents table after indexing."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        expected_size = f.stat().st_size

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        doc = engine.storage.get_document(str(f))
        assert doc["file_size"] == expected_size


class TestDetectChangesFastPath:
    """Tests for fast-path skip in detect_changes_and_update."""

    def test_detect_unchanged_skips_read(self, tmp_path):
        """Unchanged files hit fast-path in detect_changes."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        r = engine.detect_changes_and_update("session-1", [str(f)])
        assert str(f) in r["unchanged"] or any(
            str(f).endswith(p) for p in r["unchanged"]
        )
        assert len(r["modified"]) == 0

    def test_detect_modified_after_change(self, tmp_path):
        """Modified file detected even with fast-path."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        time.sleep(0.05)
        f.write_text("goodbye world")

        r = engine.detect_changes_and_update("session-2", [str(f)])
        assert len(r["modified"]) == 1


class TestGetContextFastPath:
    """Tests for fast-path skip in get_context."""

    def test_get_context_unchanged_skips_read(self, tmp_path):
        """get_context serves from DB when file unchanged."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        r = engine.get_context([str(f)])
        assert len(r["unchanged"]) == 1
        assert r["unchanged"][0]["chunks"]
        assert len(r["changed"]) == 0

    def test_get_context_detects_change(self, tmp_path):
        """get_context reports changed when file differs."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        engine = Stele(storage_dir=str(tmp_path / "storage"))
        engine.index_documents([str(f)])

        time.sleep(0.05)
        f.write_text("goodbye world")

        r = engine.get_context([str(f)])
        assert len(r["changed"]) == 1
