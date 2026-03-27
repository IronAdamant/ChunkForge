"""Tests for agent_response helpers (token bounds, project brief)."""

from __future__ import annotations

from stele_context.agent_response import (
    build_project_brief,
    compact_map_payload,
    truncate_search_results,
)


def test_truncate_search_results_full_when_no_limits():
    results = [{"chunk_id": "a", "content": "hello", "relevance_score": 1.0}]
    out, meta = truncate_search_results(results, max_result_tokens=None, compact=False)
    assert out == results
    assert meta["truncated"] is False


def test_truncate_search_results_compact():
    results = [{"chunk_id": "a", "content": "x" * 500, "relevance_score": 1.0}]
    out, meta = truncate_search_results(results, max_result_tokens=None, compact=True)
    assert "content_preview" in out[0]
    assert "content" not in out[0]
    assert meta["returned"] == 1


def test_compact_map_payload_caps_documents():
    data = {
        "documents": [
            {
                "path": "a.py",
                "chunk_count": 1,
                "total_tokens": 10,
                "indexed_at": 1.0,
                "annotations": [],
            },
            {
                "path": "b.py",
                "chunk_count": 1,
                "total_tokens": 100,
                "indexed_at": 1.0,
                "annotations": [],
            },
        ],
        "total_documents": 2,
        "total_tokens": 110,
        "index_health": {},
    }
    compacted = compact_map_payload(data, max_documents=1, max_annotation_chars=50)
    assert len(compacted["documents"]) == 1
    assert compacted["documents"][0]["path"] == "b.py"
    assert compacted.get("compact") is True


def test_build_project_brief(tmp_path):
    from stele_context.storage import StorageBackend

    s = StorageBackend(str(tmp_path / ".stele-context"))
    s.store_document(
        "src/foo.py",
        "abc",
        1,
        last_modified=1.0,
        file_size=3,
    )
    s.store_chunk(
        "c1",
        "src/foo.py",
        "abc",
        [0.0] * 128,
        0,
        3,
        10,
        content="hello world",
    )
    brief = build_project_brief(s, top_n=5)
    assert brief["totals"]["documents"] == 1
    assert len(brief["largest_files_by_tokens"]) == 1
