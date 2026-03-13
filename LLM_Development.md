# LLM Development Log

Chronological log of development work on ChunkForge.

---

## 2026-03-12 — v0.1.0: Initial Release

- Created core ChunkForge engine with dynamic semantic chunking
- Implemented hybrid indexing (SHA-256 + TF-style semantic signatures)
- Built persistent storage backend (SQLite + filesystem KV-cache)
- Added session management with rollback support
- Built MCP HTTP/JSON server for agent integration
- Created CLI interface (serve, index, detect, stats, clear)
- Pure-Python fallbacks for numpy and msgspec

## 2026-03-12 — v0.2.0: Test Suite & CI/CD

- Added comprehensive pytest suite (14 tests)
- Set up GitHub Actions CI (Python 3.9-3.12) and PyPI publish workflow
- Made msgspec and numpy optional (zero required dependencies)
- Added issue/PR templates, CONTRIBUTING.md, CHANGELOG.md

## 2026-03-12 — v0.3.0: Multi-Modal Support

- Implemented modular chunker architecture (BaseChunker ABC)
- Added ImageChunker (Pillow), PDFChunker (pymupdf), AudioChunker (librosa), VideoChunker (opencv)
- Refactored TextChunker and created CodeChunker with AST parsing
- Auto-detection of file modality by extension
- Optional dependency extras: `[image]`, `[pdf]`, `[audio]`, `[video]`, `[all]`

## 2026-03-12 — v0.4.0: Vector Index & Compression

- Implemented pure-Python HNSW vector index (O(log n) similarity search)
- Added zlib compression for KV-cache files (50-80% savings)
- Chunk versioning and history tracking
- Adaptive chunk sizing and sliding window options
- Enhanced semantic signatures with structural features

## 2026-03-13 — v0.4.1: Code Audit & Cleanup

Full codebase audit performed. Changes:

### Bugs Fixed
- **Optional dependency detection**: `HAS_IMAGE_CHUNKER` etc. flags were set to `True` even when the underlying library (Pillow, pymupdf, librosa, opencv) wasn't installed. The module imported fine but the constructor raised `ImportError`. Fixed by checking inner availability flags (`HAS_PIL`, `HAS_PYMUPDF`, etc.). This fixed 6 previously failing tests.
- **msgspec guard in storage**: `store_kv_state()` and `load_kv_state()` called `msgspec` methods without checking `HAS_MSGSPEC`. Crashed with `AttributeError` when msgspec was not installed.
- **Test version mismatch**: `test_get_stats` asserted version `"0.1.0"` but actual was `"0.4.0"`.

### Dead Code Removed (~300 lines)
- `TextChunk`, `PDFChunk`, `ImageChunk`, `AudioChunk`, `VideoChunk` — subclasses defined in each chunker module but never imported or used anywhere
- `ChunkForge.get_chunker()` — method defined but never called
- `BaseChunker.read_file()` — method defined but never called
- `import io` in video.py — unused
- Unused type imports (`Optional`, `Counter`, `Tuple`) across 5 files

### Code Simplification
- Merged `TextChunker._chunk_paragraphs()` and `_chunk_adaptive()` (90%+ identical code) into single `_chunk_by_paragraphs(adaptive: bool)` method
- Extracted duplicated cosine similarity computation into shared `_cosine_similarity()` helper in core.py

### Documentation
- Updated README.md (corrected codebase line count)
- Updated CHANGELOG.md with v0.4.1 entry
- Created `COMPLETE_PROJECT_DOCUMENTATION.md` (file table with paths, purposes, deps)
- Created `LLM_Development.md` (this file)
- Created `wiki-local/` with `index.md`, `spec-project.md`, `glossary.md`

### Test Results
- All 49 tests passing (previously 6 were failing due to optional dep detection bug)

## 2026-03-13 — v0.5.2: Persistent HNSW Index

Added persistent serialization for the HNSW vector index so it doesn't rebuild from SQLite on every startup.

### New Files
- `chunkforge/index_store.py` (~90 LOC) — save/load/staleness detection for VectorIndex
- `tests/test_index_store.py` (~160 LOC) — 14 tests for serialization, staleness, integration

### Changes
- `index.py`: Added `to_dict()`/`from_dict()` on both `HNSWIndex` and `VectorIndex`
- `engine.py`: Replaced `_rebuild_index()` with `_load_or_rebuild_index()` that checks persisted index first; added `_save_index()` called after `index_documents()` and `detect_changes_and_update()`
- Staleness detection via SHA-256 hash of sorted chunk IDs — if chunks changed, persisted index is discarded and rebuilt
- Index file: `~/.chunkforge/indices/hnsw_index.json.zlib` (JSON + zlib, atomic writes via temp-then-rename)

### Test Results
- 102 tests passing (was 88), 1 skipped (MCP SDK not installed)

## 2026-03-13 — v0.5.1: Codebase Audit & Cleanup

Full codebase audit via 6 parallel agents, followed by systematic fixes.

### Bugs Fixed
- **`detect_changes_and_update` never persisted updated chunks** — now stores re-chunked content, signatures, and document records after detecting modifications
- **`store_chunk` INSERT OR REPLACE reset `access_count` to 0** — now uses UPDATE for existing chunks, preserving access history
- **`prune_chunks` never updated `total_tokens` in sessions table** — now updates after pruning so session state stays accurate
- **Binary content signatures were 64-dim vs 128-dim** — padded hash-based signatures to full 128-dim to match text signatures
- **`results["new"]` had inconsistent types** (strings vs dicts) in `detect_changes_and_update` — now always returns dicts
- **`store_kv_state` inconsistent compression** — msgspec fallback path now also applies zlib compression
- **`get_session()` called per-chunk inside loop** — hoisted outside for efficiency

### Dead Code Removed
- Unused imports across 12 files: `np`/`HAS_NUMPY` (engine), `hashlib`/`Tuple` (storage), `os` (session_storage), `parse_qs`/`List` (mcp_server), `Path` (cli), `Optional` (code.py), `hashlib`/`Dict` (image.py), `Dict` (video.py), `SessionStorage` (session.py), `math` (test_index), `json` (test_mcp_stdio), `tempfile`/`Path` (test files)
- All 4 unused conftest.py fixtures removed
- Unused `current_start` variable in code.py `_chunk_regex`
- Pickle fallback in session_storage.py removed (security improvement)

### Duplication Resolved
- Engine session methods (`save_kv_state`, `rollback`, `prune_chunks`, `get_relevant_kv`) now delegate to `SessionManager` instead of duplicating ~80 lines of identical logic
- `storage.py` numpy import replaced with `sig_to_bytes()` from numpy_compat (single source of truth)
- Raw SQL in `engine.py` (`_rebuild_index`, `detect_changes_and_update`) replaced with `StorageBackend` API methods
- Raw SQL in `mcp_stdio.py` `read_resource` replaced with storage API

### Code Simplification
- `_estimate_token_count` collapsed identical str/bytes branches
- `_extract_words` simplified to one-liner with Counter comprehension
- `_extract_trigrams` removed redundant isinstance check (only called after type guard)
- Removed redundant loop guards in `_compute_semantic_signature`

### Test Results
- All 88 tests passing, 1 skipped (MCP SDK not installed)

## 2026-03-13 — v0.5.0: Complete Overhaul

Major overhaul to wire all components together, reframe as a context cache, and add real MCP support.

### Problems Fixed
- `index_documents()` bypassed all chunkers, reimplemented paragraph splitting inline — now routes through CodeChunker/TextChunker
- HNSW vector index (513 LOC, fully tested) was never imported by the engine — now wired in for all search/change detection
- Chunk text content was discarded after indexing — now stored in SQLite `content` column
- MCP server was HTTP REST, not JSON-RPC over stdio — added real `mcp_stdio.py` using MCP SDK
- Pickle used for KV serialization (security risk) — replaced with JSON+zlib
- `core.py` was 1038 LOC with two responsibilities — extracted into engine.py, session.py, session_storage.py
- Two incompatible Chunk classes — unified to single Chunk from `chunkers.base`

### New Files Created
- `chunkforge/engine.py` (~450 LOC) — new ChunkForge class with chunker routing + HNSW
- `chunkforge/session.py` (~200 LOC) — SessionManager class
- `chunkforge/session_storage.py` (~280 LOC) — extracted from storage.py
- `chunkforge/chunkers/numpy_compat.py` (~75 LOC) — shared numpy fallback
- `chunkforge/mcp_stdio.py` (~250 LOC) — real MCP server
- `tests/test_engine.py`, `tests/test_session.py`, `tests/test_mcp_stdio.py`, `tests/test_storage_migration.py`

### Modified Files
- `chunkforge/chunkers/base.py` — upgraded to rich 128-dim semantic signatures
- `chunkforge/storage.py` — added content column, migration, delegated sessions
- `chunkforge/core.py` — converted to backward-compat shim (~25 LOC)
- `chunkforge/__init__.py` — updated exports, reframed docstring
- `chunkforge/cli.py` — added `serve-mcp` and `search` commands
- `chunkforge/mcp_server.py` — added `search` and `get_context` tools
- `pyproject.toml` — version 0.5.0, new keywords, MCP optional dep, entry point

### Test Results
- 88 tests passing (was 49), 1 skipped (MCP SDK not installed)
- New coverage: engine routing, HNSW integration, search API, content storage, schema migration, JSON serialization
