"""
Index / symbol freshness diagnostics for map, stats, and agents.

Pure stdlib — no imports from chunkers or optional deps.  Keeps
StorageBackend.get_index_health_snapshot thin.
"""

from __future__ import annotations

import time
from typing import Any

# Age beyond which we surface a "re-check index" hint (wall-clock, not git).
_STALE_INDEX_SECONDS = 7 * 24 * 3600


def compute_index_health_snapshot(
    *,
    document_count: int,
    chunk_count: int,
    symbol_count: int,
    storage_dir: str,
    latest_indexed_at: float | None,
    now: float | None = None,
) -> dict[str, Any]:
    """Build index_health dict with actionable alerts and simple staleness hints.

    ``latest_indexed_at`` is the max ``documents.indexed_at`` (unix time).
    """
    t = time.time() if now is None else now
    docs = int(document_count)
    chunks = int(chunk_count)
    sym = int(symbol_count)

    if sym > 0:
        sym_status = "ready"
    elif chunks > 0:
        sym_status = "empty_with_chunks"
    else:
        sym_status = "empty"

    if chunks > 0:
        chunk_status = "ready"
    elif docs > 0:
        chunk_status = "empty_with_documents"
    else:
        chunk_status = "empty"

    alerts: list[str] = []
    if docs == 0:
        alerts.append(
            "No documents indexed; run index on project paths before search or symbols."
        )
    if chunks > 0 and sym == 0:
        alerts.append(
            "Chunk store has data but the symbol graph is empty; index source files "
            "then run rebuild_symbols."
        )
    if latest_indexed_at is not None and docs > 0:
        age = t - float(latest_indexed_at)
        if age > _STALE_INDEX_SECONDS:
            days = int(age // 86400)
            alerts.append(
                f"Last document index time is about {days} day(s) old; run "
                "detect_changes and re-index files you have edited."
            )

    seconds_since_last_index: float | None = None
    if latest_indexed_at is not None:
        seconds_since_last_index = t - float(latest_indexed_at)

    return {
        "documents": docs,
        "chunks": chunks,
        "symbol_rows": sym,
        "symbols_ready": sym > 0,
        "latest_indexed_at": latest_indexed_at,
        "storage_dir": storage_dir,
        "symbol_graph_status": sym_status,
        "chunk_store_status": chunk_status,
        "seconds_since_last_index": seconds_since_last_index,
        "alerts": alerts,
    }
