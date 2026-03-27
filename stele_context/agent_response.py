"""
Token-bounded and compact responses for LLM agents.

Pure helpers — no engine imports. Keeps search/map/stats payloads within
predictable context budgets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stele_context.chunkers.base import estimate_tokens

__all__ = [
    "trim_content_to_token_budget",
    "truncate_search_results",
    "compact_map_payload",
    "compact_stats_payload",
    "parse_agent_notes_field",
    "build_project_brief",
]


def trim_content_to_token_budget(
    content: str,
    max_tokens: int,
) -> tuple[str, bool]:
    """Trim content to at most ``max_tokens`` (estimated). Returns (text, truncated)."""
    if max_tokens <= 0 or estimate_tokens(content) <= max_tokens:
        return content, False
    lo, hi = 0, len(content)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(content[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return content[:lo] + "\n…[truncated]", True


def truncate_search_results(
    results: list[dict[str, Any]],
    *,
    max_result_tokens: int | None,
    compact: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cap total estimated tokens across result bodies.

    With ``compact``, replaces ``content`` with ``content_preview`` (~400 chars).
    """
    if not results:
        return [], {"total_results": 0, "returned": 0, "truncated": False}

    if max_result_tokens is None and not compact:
        return results, {
            "total_results": len(results),
            "returned": len(results),
            "truncated": False,
        }

    out: list[dict[str, Any]] = []
    used = 0
    budget = max_result_tokens if max_result_tokens is not None else 10**18

    for r in results:
        cpy = dict(r)
        content = cpy.get("content") or ""
        if compact:
            prev = content
            preview = content[:400] + ("…" if len(content) > 400 else "")
            cpy["content_preview"] = preview
            cpy["content_token_estimate"] = estimate_tokens(prev)
            cpy.pop("content", None)
            piece_tokens = estimate_tokens(preview) + 32
        else:
            piece_tokens = estimate_tokens(content)

        if used + piece_tokens > budget:
            break
        out.append(cpy)
        used += piece_tokens

    return out, {
        "total_results": len(results),
        "returned": len(out),
        "truncated": len(out) < len(results),
        "estimated_tokens_used": used,
    }


def compact_map_payload(
    data: dict[str, Any],
    *,
    max_documents: int | None,
    max_annotation_chars: int,
) -> dict[str, Any]:
    """Sort documents by total_tokens desc, cap count, shorten annotations."""
    docs = list(data.get("documents") or [])
    docs.sort(key=lambda d: d.get("total_tokens") or 0, reverse=True)
    if max_documents is not None and max_documents > 0:
        docs = docs[:max_documents]

    slim: list[dict[str, Any]] = []
    for d in docs:
        entry = {
            "path": d.get("path"),
            "chunk_count": d.get("chunk_count"),
            "total_tokens": d.get("total_tokens"),
            "indexed_at": d.get("indexed_at"),
        }
        anns = d.get("annotations") or []
        if anns and max_annotation_chars >= 0:
            short_anns = []
            for a in anns:
                c = a.get("content") or ""
                if len(c) > max_annotation_chars:
                    c = c[:max_annotation_chars] + "…"
                short_anns.append(
                    {"id": a.get("id"), "content": c, "tags": a.get("tags")}
                )
            entry["annotations"] = short_anns
        else:
            entry["annotations"] = []
        slim.append(entry)

    out = dict(data)
    out["documents"] = slim
    out["compact"] = True
    if max_documents is not None:
        out["documents_omitted"] = max(0, data.get("total_documents", 0) - len(slim))
    return out


def compact_stats_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Smaller stats dict for quick agent orientation."""
    storage = data.get("storage") or {}
    idx = data.get("index") or {}
    cfg = data.get("config") or {}
    health = data.get("index_health")
    return {
        "version": data.get("version"),
        "project_root": data.get("project_root"),
        "compact": True,
        "storage": {
            "storage_dir": storage.get("storage_dir"),
            "document_count": storage.get("document_count"),
            "chunk_count": storage.get("chunk_count"),
            "total_tokens": storage.get("total_tokens"),
        },
        "index": {
            "chunk_count": idx.get("chunk_count"),
            "node_count": idx.get("node_count"),
        },
        "config": {
            "chunk_size": cfg.get("chunk_size"),
            "search_alpha": cfg.get("search_alpha"),
        },
        "index_health": health,
    }


def parse_agent_notes_field(raw: str | None) -> Any:
    """Return parsed JSON object if valid, else raw string."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return raw


def build_project_brief(
    storage: Any,
    *,
    top_n: int = 40,
) -> dict[str, Any]:
    """Stable JSON: largest files by tokens, extension counts, totals."""
    documents = storage.get_all_documents()
    rows: list[dict[str, Any]] = []
    ext_counts: dict[str, int] = {}
    total_tokens = 0

    for doc in documents:
        path = doc["document_path"]
        chunks = storage.search_chunks(document_path=path)
        doc_tokens = sum(c["token_count"] for c in chunks)
        total_tokens += doc_tokens
        ext = Path(path).suffix.lower() or "(no extension)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        rows.append(
            {
                "path": path,
                "chunk_count": doc["chunk_count"],
                "total_tokens": doc_tokens,
                "indexed_at": doc.get("indexed_at"),
            }
        )

    rows.sort(key=lambda r: r["total_tokens"], reverse=True)
    top = rows[: max(1, top_n)]

    return {
        "purpose": "One-screen orientation for LLM agents; use before deep search.",
        "totals": {
            "documents": len(documents),
            "chunks": storage.get_storage_stats().get("chunk_count", 0),
            "total_tokens": total_tokens,
        },
        "extensions": dict(sorted(ext_counts.items(), key=lambda x: -x[1])[:20]),
        "largest_files_by_tokens": top,
        "index_health": storage.get_index_health_snapshot(),
    }
