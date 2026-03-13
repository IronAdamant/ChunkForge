# ChunkForge — Project Specification

## Purpose

ChunkForge is a purely local, persistent KV-cache rollback and offload engine. It enables long-horizon LLM agents (especially 1M+ context models) to avoid re-scanning or re-processing unmodified documents. Unchanged chunks instantly restore pre-computed KV states; only modified chunks trigger lightweight double-checks.

## Architecture

```
User / Agent
     |
     v
+-----------+     +-----------+     +----------------+
|    CLI    | --> | ChunkForge| --> | StorageBackend |
+-----------+     |  (core)   |     |  (SQLite + FS) |
                  +-----------+     +----------------+
+-----------+         |
| MCPServer | --------+
+-----------+         |
                  +-----------+
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

### `core.py` — ChunkForge Engine
- `ChunkForge` class: orchestrates indexing, change detection, KV management, sessions
- `Chunk` class: represents a text/code chunk with lazy-computed hash, signature, token count
- `_cosine_similarity()`: shared helper for vector similarity
- Initializes and delegates to modality-specific chunkers
- Three-tier change detection: hash match → semantic similarity → reprocess

### `storage.py` — StorageBackend
- SQLite database for metadata (chunks, documents, sessions, session_chunks, chunk_history)
- Filesystem storage for KV-cache blobs (`~/.chunkforge/kv_cache/`)
- Session rollback (delete turns after target)
- Chunk pruning by relevance score
- Serialization: msgspec (if available) with pickle fallback

### `index.py` — HNSW Vector Index
- Pure-Python Hierarchical Navigable Small World graph
- O(log n) approximate nearest neighbor search
- `VectorIndex` wrapper for chunk-specific operations
- Standalone module with zero internal dependencies

### `mcp_server.py` — MCP Tool Server
- HTTP/JSON server on localhost (default port 9876)
- Endpoints: `GET /tools`, `POST /call`, `GET /health`
- Exposes all ChunkForge operations as discoverable tools

### `cli.py` — Command-Line Interface
- Subcommands: `serve`, `index`, `detect`, `stats`, `clear`
- Entry point: `chunkforge = "chunkforge.cli:main"` (pyproject.toml)

### `chunkers/` — Modality-Specific Chunkers
- `base.py`: `BaseChunker` ABC + `Chunk` dataclass (multi-modal variant with `modality` field)
- `text.py`: Paragraph-based, adaptive, sliding-window chunking
- `code.py`: Python AST parsing, regex patterns for other languages
- `image.py`, `pdf.py`, `audio.py`, `video.py`: Optional-dependency chunkers

## Design Decisions

1. **Two Chunk classes**: `core.Chunk` (regular class with numpy integration) is used by the engine. `chunkers.base.Chunk` (dataclass with `modality` field) is used by chunkers. They share the interface but differ in implementation.

2. **Lazy properties**: Content hash, semantic signature, token count, and chunk ID are all computed on first access and cached.

3. **Optional dependency detection**: Each chunker module has its own `HAS_*` flag. The `chunkers/__init__.py` re-exports these as `HAS_*_CHUNKER` flags by checking the inner flags, not just whether the module imported.

4. **Zero required dependencies**: Core text/code functionality uses only Python stdlib. numpy operations have a `_NumpyFallback` class. msgspec has pickle fallback.

5. **Semantic signatures**: 128-dimensional vectors using character trigram frequencies (64 dims), word frequency distribution (32 dims), and structural features (32 dims). Normalized to unit vectors for cosine similarity.

## Data Model

### SQLite Tables
- `chunks`: chunk_id, document_path, content_hash, semantic_signature, positions, token_count, version
- `chunk_history`: chunk_id, version, content_hash, semantic_signature, created_at
- `documents`: document_path, content_hash, chunk_count, timestamps
- `sessions`: session_id, turn_count, total_tokens, timestamps
- `session_chunks`: session_id, chunk_id, turn_number, kv_path, relevance_score
