# ChunkForge — Project Specification

## Purpose

ChunkForge is a purely local, persistent context cache and offload engine. It enables long-horizon LLM agents (especially 1M+ context models) to avoid re-scanning or re-processing unmodified documents. Unchanged chunks instantly restore pre-computed context cache states; only modified chunks trigger lightweight double-checks.

## Architecture

```
User / Agent
     |
     v
+-----------+     +-------------+     +----------------+
|    CLI    | --> |  ChunkForge | --> | StorageBackend |
+-----------+     |  (engine)   |     |  (SQLite + FS) |
                  +-------------+     +----------------+
+-----------+         |                     |
| MCP stdio | --------+              +--------------+
+-----------+         |              | SessionStore |
                  +-----------+      +--------------+
                  |  Chunkers |
                  +-----------+
                  | Text Code |
                  | Image PDF |
                  | Audio Vid |
                  +-----------+
                      |
                  +-----------+
                  | HNSWIndex |
                  +-----------+
```

## Module Responsibilities

### `engine.py` — ChunkForge Engine
- `ChunkForge` class: main entry point that routes through chunkers + HNSW index
- Orchestrates indexing, change detection, context cache management
- `search()`: semantic search across indexed chunks using HNSW vector index
- `get_context()`: retrieve relevant context for a query
- Three-tier change detection: hash match → semantic similarity → reprocess
- Delegates session ops (`save_kv_state`, `rollback`, `prune_chunks`, `get_relevant_kv`) to `SessionManager`

### `core.py` — Backward-Compatibility Shim
- Re-exports `Chunk` from `chunkers.base` for backward compatibility
- Legacy entry point; new code should use `engine.py` or `chunkers.base`

### `session.py` — SessionManager
- `SessionManager` class: manages conversation sessions and turn tracking
- HNSW-accelerated chunk retrieval (`get_relevant_chunks`)
- Session creation, save, rollback, prune, and lifecycle management
- Delegates persistence to `session_storage.py`
- Engine delegates all session operations here (single source of truth)

### `storage.py` — StorageBackend
- SQLite database for metadata (chunks, documents, chunk_history)
- Stores chunk text content in SQLite, enabling retrieval
- Filesystem storage for context cache blobs (`~/.chunkforge/kv_cache/`)
- Chunk pruning by relevance score

### `session_storage.py` — Session Persistence
- Extracted session operations from `storage.py`
- Session and session_chunks table management
- Serialization: JSON + zlib (replaces pickle)

### `numpy_compat.py` — NumPy Compatibility
- Extracted numpy fallback from core
- `_NumpyFallback` class for environments without numpy
- `cosine_similarity()` helper function

### `index.py` — HNSW Vector Index
- Pure-Python Hierarchical Navigable Small World graph
- O(log n) approximate nearest neighbor search
- `VectorIndex` wrapper for chunk-specific operations
- `to_dict()`/`from_dict()` for serialization round-trips
- Wired into engine for search and change detection
- Standalone module with zero internal dependencies

### `index_store.py` — Index Persistence
- Saves/loads `VectorIndex` to compressed JSON (`indices/hnsw_index.json.zlib`)
- Staleness detection via SHA-256 hash of sorted chunk IDs
- Atomic writes via temp-file-then-rename
- Engine calls `_save_index()` after `index_documents()` and `detect_changes_and_update()`

### `mcp_stdio.py` — MCP Server (JSON-RPC over stdio)
- Real MCP server using JSON-RPC protocol over stdio
- Replaces the previous HTTP-based `mcp_server.py`
- Exposes all ChunkForge operations as discoverable tools

### `cli.py` — Command-Line Interface
- Subcommands: `serve`, `index`, `detect`, `stats`, `clear`, `serve-mcp`, `search`
- Entry point: `chunkforge = "chunkforge.cli:main"` (pyproject.toml)

### `chunkers/` — Modality-Specific Chunkers
- `base.py`: `BaseChunker` ABC + unified `Chunk` dataclass (the single Chunk class for the whole project)
- `text.py`: Paragraph-based, adaptive, sliding-window chunking
- `code.py`: Python AST parsing, regex patterns for other languages
- `image.py`, `pdf.py`, `audio.py`, `video.py`: Optional-dependency chunkers

## Design Decisions

1. **Unified Chunk class**: There is now only one `Chunk` class, defined in `chunkers.base`. `core.py` re-exports it as a backward-compatibility shim. All code uses the same Chunk dataclass.

2. **Lazy properties**: Content hash, semantic signature, token count, and chunk ID are all computed on first access and cached.

3. **Optional dependency detection**: Each chunker module has its own `HAS_*` flag. The `chunkers/__init__.py` re-exports these as `HAS_*_CHUNKER` flags by checking the inner flags, not just whether the module imported.

4. **Zero required dependencies**: Core text/code functionality uses only Python stdlib. numpy operations have a `_NumpyFallback` class in `numpy_compat.py`.

5. **Semantic signatures**: 128-dimensional vectors using character trigram frequencies (64 dims), word frequency distribution (32 dims), and structural features (32 dims). Normalized to unit vectors for cosine similarity.

6. **JSON only, no pickle**: Session storage uses JSON + zlib. Pickle fallback was removed in v0.5.1 for security.

7. **Chunk content stored**: SQLite now stores the actual text content of chunks, enabling retrieval via `search()` and `get_context()` APIs.

8. **HNSW wired into engine**: The vector index is used directly by the engine for semantic search and change detection, not just as a standalone module.

## Data Model

### SQLite Tables
- `chunks`: chunk_id, document_path, content_hash, content, semantic_signature, positions, token_count, version
- `chunk_history`: chunk_id, version, content_hash, semantic_signature, created_at
- `documents`: document_path, content_hash, chunk_count, timestamps
- `sessions`: session_id, turn_count, total_tokens, timestamps (managed by `session_storage.py`)
- `session_chunks`: session_id, chunk_id, turn_number, kv_path, relevance_score (managed by `session_storage.py`)
