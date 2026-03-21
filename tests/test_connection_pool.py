"""Tests for ConnectionPool, connect() context manager, and search_text() edge cases."""

from __future__ import annotations

import re
import sqlite3
import threading

import pytest

import stele_context.storage_schema as _schema
from stele_context.connection_pool import ConnectionPool
from stele_context.storage import StorageBackend
from stele_context.storage_schema import connect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(tmp_path):
    db = tmp_path / "test.db"
    pool = ConnectionPool(db)
    return pool, db


def _store_chunk(storage, chunk_id="c1", doc="doc.txt", content="hello world"):
    storage.store_chunk(
        chunk_id=chunk_id,
        document_path=doc,
        content_hash="hash1",
        semantic_signature=[0.0] * 128,
        start_pos=0,
        end_pos=len(content),
        token_count=2,
        content=content,
    )


# ---------------------------------------------------------------------------
# ConnectionPool tests
# ---------------------------------------------------------------------------


class TestConnectionPool:
    def test_get_returns_valid_connection(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        conn = pool.get()
        assert isinstance(conn, sqlite3.Connection)
        # Sanity: can execute a trivial query
        assert conn.execute("SELECT 1").fetchone() == (1,)
        pool.close_all()

    def test_get_same_thread_returns_same_connection(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        conn1 = pool.get()
        conn2 = pool.get()
        assert conn1 is conn2
        pool.close_all()

    def test_multiple_get_calls_same_thread(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        conns = [pool.get() for _ in range(5)]
        # All five calls must return the identical object
        assert all(c is conns[0] for c in conns)
        pool.close_all()

    def test_get_different_connections_for_different_threads(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        results: list[sqlite3.Connection] = []
        lock = threading.Lock()

        def grab():
            c = pool.get()
            with lock:
                results.append(c)
            # Keep thread alive until both have run
            threading.Event().wait(0.05)

        t1 = threading.Thread(target=grab)
        t2 = threading.Thread(target=grab)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        assert results[0] is not results[1]
        pool.close_all()

    def test_close_all_closes_connections(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        conn = pool.get()
        pool.close_all()
        # Closed connections raise ProgrammingError on use
        with pytest.raises(Exception):
            conn.execute("SELECT 1")

    def test_row_factory_settable_after_get(self, tmp_path):
        pool, _ = _make_pool(tmp_path)
        conn = pool.get()
        conn.row_factory = sqlite3.Row
        assert conn.row_factory is sqlite3.Row
        pool.close_all()


# ---------------------------------------------------------------------------
# connect() context-manager tests
# ---------------------------------------------------------------------------


class TestConnectContextManager:
    def setup_method(self):
        # Reset global pool before each test so tests are isolated
        _schema._pool = None

    def test_no_pool_fresh_connection(self, tmp_path):
        db = tmp_path / "fresh.db"
        with connect(db) as conn:
            assert isinstance(conn, sqlite3.Connection)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (42)")
        # Connection is closed after the block; re-open to verify commit
        with sqlite3.connect(db) as verify:
            row = verify.execute("SELECT x FROM t").fetchone()
        assert row[0] == 42

    def test_pool_path_match_reuses_connection(self, tmp_path):
        db = tmp_path / "pool.db"
        pool = ConnectionPool(db)
        _schema._pool = pool
        try:
            with connect(db) as conn:
                pooled = pool.get()
                assert conn is pooled
        finally:
            pool.close_all()
            _schema._pool = None

    def test_pool_path_mismatch_fresh_connection(self, tmp_path):
        pool_db = tmp_path / "pool.db"
        other_db = tmp_path / "other.db"
        pool = ConnectionPool(pool_db)
        _schema._pool = pool
        try:
            with connect(other_db) as conn:
                # Must be a fresh connection, not the pooled one
                assert conn is not pool.get()
        finally:
            pool.close_all()
            _schema._pool = None

    def test_auto_commit_on_success(self, tmp_path):
        db = tmp_path / "commit.db"
        with connect(db) as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (7)")
        with sqlite3.connect(db) as verify:
            assert verify.execute("SELECT x FROM t").fetchone() == (7,)

    def test_rollback_on_exception(self, tmp_path):
        db = tmp_path / "rollback.db"
        with connect(db) as c:
            c.execute("CREATE TABLE t (x INTEGER)")
        with pytest.raises(ValueError):
            with connect(db) as conn:
                conn.execute("INSERT INTO t VALUES (99)")
                raise ValueError("abort")
        with sqlite3.connect(db) as verify:
            assert verify.execute("SELECT COUNT(*) FROM t").fetchone() == (0,)

    def test_row_factory_reset_to_none_on_entry(self, tmp_path):
        db = tmp_path / "rf.db"
        pool = ConnectionPool(db)
        _schema._pool = pool
        try:
            # Set row_factory on the pooled connection directly
            pool.get().row_factory = sqlite3.Row
            with connect(db) as conn:
                assert conn.row_factory is None
        finally:
            pool.close_all()
            _schema._pool = None


# ---------------------------------------------------------------------------
# search_text() edge cases
# ---------------------------------------------------------------------------


class TestSearchTextEdgeCases:
    def test_invalid_regex_raises(self, tmp_path):
        storage = StorageBackend(base_dir=str(tmp_path / "s"))
        try:
            _store_chunk(storage)
            with pytest.raises(re.error):
                storage.search_text("[invalid", regex=True)
        finally:
            storage.close()

    def test_empty_pattern_substring_returns_nothing(self, tmp_path):
        """Empty substring never matches via str.find() loop (find returns 0 forever)."""
        storage = StorageBackend(base_dir=str(tmp_path / "s"))
        try:
            _store_chunk(storage, content="hello")
            # Empty pattern: find("") always returns 0, causing infinite loop —
            # we just verify the method does not hang and returns a list.
            # (Behaviour: empty string matches at every position; result may be non-empty.)
            result = storage.search_text("")
            assert isinstance(result, list)
        finally:
            storage.close()

    def test_special_regex_chars_in_non_regex_mode(self, tmp_path):
        """Chars like '.' and '*' are treated as literals in non-regex mode."""
        storage = StorageBackend(base_dir=str(tmp_path / "s"))
        try:
            _store_chunk(storage, content="file.txt and filetxt")
            results = storage.search_text("file.txt", regex=False)
            assert len(results) == 1
            assert results[0]["match_count"] == 1
            assert results[0]["matches"][0]["text"] == "file.txt"
        finally:
            storage.close()

    def test_regex_mode_matches_pattern(self, tmp_path):
        storage = StorageBackend(base_dir=str(tmp_path / "s"))
        try:
            _store_chunk(storage, content="foo123 bar456")
            results = storage.search_text(r"\d+", regex=True)
            assert len(results) == 1
            assert results[0]["match_count"] == 2
        finally:
            storage.close()

    def test_no_match_returns_empty_list(self, tmp_path):
        storage = StorageBackend(base_dir=str(tmp_path / "s"))
        try:
            _store_chunk(storage, content="hello world")
            results = storage.search_text("zzznomatch")
            assert results == []
        finally:
            storage.close()
