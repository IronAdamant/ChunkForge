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
