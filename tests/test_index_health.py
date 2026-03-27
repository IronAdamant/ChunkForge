"""Unit tests for stele_context.index_health (stdlib-only diagnostics)."""

from __future__ import annotations

from stele_context.index_health import compute_index_health_snapshot


class TestComputeIndexHealthSnapshot:
    def test_empty_store_alerts(self):
        h = compute_index_health_snapshot(
            document_count=0,
            chunk_count=0,
            symbol_count=0,
            storage_dir="/tmp/x",
            latest_indexed_at=None,
            now=1_000_000.0,
        )
        assert h["chunk_store_status"] == "empty"
        assert h["symbol_graph_status"] == "empty"
        assert any("No documents indexed" in a for a in h["alerts"])

    def test_chunks_but_no_symbols_alerts(self):
        h = compute_index_health_snapshot(
            document_count=1,
            chunk_count=3,
            symbol_count=0,
            storage_dir="/tmp/x",
            latest_indexed_at=1_000_000.0,
            now=1_000_100.0,
        )
        assert h["symbol_graph_status"] == "empty_with_chunks"
        assert h["chunk_store_status"] == "ready"
        assert any("symbol graph is empty" in a for a in h["alerts"])

    def test_stale_index_alert(self):
        now = 10_000_000.0
        old = now - 10 * 86400  # 10 days
        h = compute_index_health_snapshot(
            document_count=2,
            chunk_count=2,
            symbol_count=5,
            storage_dir="/tmp/x",
            latest_indexed_at=old,
            now=now,
        )
        assert any("day" in a and "detect_changes" in a for a in h["alerts"])
        assert h["seconds_since_last_index"] == 10 * 86400

    def test_fresh_index_no_stale_alert(self):
        now = 10_000_000.0
        h = compute_index_health_snapshot(
            document_count=1,
            chunk_count=1,
            symbol_count=1,
            storage_dir="/tmp/x",
            latest_indexed_at=now - 3600.0,
            now=now,
        )
        assert not any("day(s) old" in a for a in h["alerts"])
