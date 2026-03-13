# ChunkForge - Complete Project Documentation

## File Table

| Path | Purpose | Dependencies | Wiki Link |
|------|---------|-------------|-----------|
| `chunkforge/__init__.py` | Package entry point; exports `ChunkForge`, `StorageBackend`, `SessionManager`, `MCPServer`, `__version__` | engine, storage, session, mcp_server | [index](wiki-local/index.md) |
| `chunkforge/engine.py` | Main `ChunkForge` class; chunker routing, HNSW integration, search, get_context, change detection | storage, index, chunkers, numpy_compat | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/core.py` | Backward-compat shim; re-exports `ChunkForge` from engine, `Chunk` from chunkers.base | engine, chunkers.base, numpy_compat | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/storage.py` | `StorageBackend` class; SQLite metadata + chunk content persistence, delegates session ops to SessionStorage | session_storage, numpy (optional) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/session_storage.py` | `SessionStorage` class; session lifecycle, KV-cache serialization (JSON+zlib), rollback, pruning | msgspec (optional) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/session.py` | `SessionManager` class; high-level session operations with HNSW-accelerated retrieval | storage, index, chunkers.base, numpy_compat | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/index.py` | `HNSWIndex` and `VectorIndex` classes; pure-Python HNSW for O(log n) similarity search | (none) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/cli.py` | CLI entry point (`chunkforge` command); serve, serve-mcp, index, search, detect, stats, clear | engine, mcp_server, mcp_stdio | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/mcp_server.py` | `MCPServer` + `MCPRequestHandler`; HTTP/JSON REST server on localhost | engine, chunkers | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/mcp_stdio.py` | Real MCP server using JSON-RPC over stdio; for Claude Desktop integration | engine, mcp SDK (optional) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/chunkers/__init__.py` | Chunkers package; imports all chunkers, exports availability flags (`HAS_*_CHUNKER`) | base, text, code, image?, pdf?, audio?, video? | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/numpy_compat.py` | Shared numpy fallback (`_NumpyFallback`), `cosine_similarity()`, `sig_to_bytes()`, `sig_from_bytes()` | numpy (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/base.py` | `BaseChunker` ABC and `Chunk` dataclass with rich 128-dim semantic signatures | numpy_compat | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/text.py` | `TextChunker`; paragraph-based, adaptive, and sliding-window text chunking | base | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/code.py` | `CodeChunker`; AST-based chunking for Python, regex for other languages | base | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/image.py` | `ImageChunker`; whole-image or tile-based chunking with perceptual hashing | base, Pillow (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/pdf.py` | `PDFChunker`; page-based PDF chunking with text extraction | base, pymupdf (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/audio.py` | `AudioChunker`; time-based segmentation with MFCC/spectral features | base, librosa (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/video.py` | `VideoChunker`; keyframe extraction with frame hashing | base, opencv-python (optional) | [glossary](wiki-local/glossary.md) |
| `tests/__init__.py` | Test package marker | - | - |
| `tests/conftest.py` | Shared pytest fixtures (`tmp_storage_dir`, sample files) | pytest | - |
| `tests/test_core.py` | Backward compat tests for `Chunk`, `ChunkForge`, `StorageBackend` via core shim | chunkforge | - |
| `tests/test_engine.py` | Tests for engine: chunker routing, HNSW integration, search, get_context, content storage | chunkforge.engine | - |
| `tests/test_session.py` | Tests for SessionManager: get_relevant_chunks, save_state, rollback, prune | chunkforge.session | - |
| `tests/test_chunkers.py` | Tests for `TextChunker`, `CodeChunker`, `Chunk` dataclass | chunkforge.chunkers | - |
| `tests/test_index.py` | Tests for `HNSWIndex`, `VectorIndex` | chunkforge.index | - |
| `tests/test_mcp_stdio.py` | Tests for MCP stdio server: tool logic, engine creation, graceful fallback | chunkforge.mcp_stdio | - |
| `tests/test_storage_migration.py` | Tests for schema migration, content column, JSON serialization | chunkforge.storage | - |
| `pyproject.toml` | Package configuration, dependencies, entry points | - | - |
| `pytest.ini` | Pytest configuration | - | - |
| `README.md` | Overview, installation, quickstart, API reference | - | - |
| `CHANGELOG.md` | Version history (Keep a Changelog format) | - | - |
| `CONTRIBUTING.md` | Contribution guidelines, dev setup, code style | - | - |
| `LICENSE` | MIT License | - | - |
| `.github/workflows/test.yml` | CI: runs pytest on Python 3.9-3.12 | - | - |
| `.github/workflows/publish.yml` | CD: publishes to PyPI on tag | - | - |

## Dependency Graph

```
chunkforge/__init__.py
  -> chunkforge.engine (ChunkForge)
      -> chunkforge.storage (StorageBackend)
          -> chunkforge.session_storage (SessionStorage)
      -> chunkforge.index (VectorIndex)
      -> chunkforge.chunkers (TextChunker, CodeChunker, optional chunkers)
          -> chunkforge.chunkers.base (BaseChunker, Chunk)
              -> chunkforge.chunkers.numpy_compat (np, cosine_similarity)
  -> chunkforge.session (SessionManager)
      -> chunkforge.storage, chunkforge.index, chunkforge.chunkers.base
  -> chunkforge.mcp_server (MCPServer, HTTP)
      -> chunkforge.engine
  -> chunkforge.mcp_stdio (MCP stdio server)
      -> chunkforge.engine

chunkforge.core (backward-compat shim)
  -> chunkforge.engine (ChunkForge)
  -> chunkforge.chunkers.base (Chunk)
  -> chunkforge.chunkers.numpy_compat

chunkforge.cli (entry point)
  -> chunkforge.engine
  -> chunkforge.mcp_server
  -> chunkforge.mcp_stdio

chunkforge.index (standalone, no internal deps)
```

## Architecture Notes

- **Single Chunk class**: `chunkforge.chunkers.base.Chunk` is the unified dataclass used everywhere. `core.py` re-exports it for backward compat.
- **Engine delegates to SessionManager**: `engine.py` holds a `SessionManager` and delegates `save_kv_state`, `rollback`, `prune_chunks`, `get_relevant_kv` to it — no duplicated session logic.
- **Engine pattern**: `engine.py` is the main orchestrator. It initializes chunkers, VectorIndex, StorageBackend, and SessionManager, and wires them together.
- **HNSW index**: Rebuilt from SQLite on startup via `storage.search_chunks()`. Used for `search()`, `get_relevant_kv()`, and change detection.
- **Content persistence**: Chunk text stored in SQLite `content` column, retrievable without re-reading source files.
- **JSON serialization**: Session storage uses JSON+zlib. No pickle fallback (removed in v0.5.1).
- **Signature compatibility**: `numpy_compat.py` is the single source for `sig_to_bytes()`, `sig_from_bytes()`, `cosine_similarity()`. All modules import from there.
- **Optional dependencies**: Availability checked via inner flags (`HAS_PIL`, `HAS_PYMUPDF`, etc.) re-exported as `HAS_*_CHUNKER` flags.
- **Zero required deps**: Core text/code functionality uses only Python stdlib. numpy, msgspec, and mcp have pure-Python fallbacks or graceful degradation.
