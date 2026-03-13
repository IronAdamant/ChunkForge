# ChunkForge Wiki

## Pages

- [spec-project.md](spec-project.md) — Architecture, design decisions, module responsibilities
- [glossary.md](glossary.md) — Key terms and concepts

## Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Engine | `chunkforge/engine.py` | Main ChunkForge class, routes through chunkers + HNSW index |
| Core (shim) | `chunkforge/core.py` | Backward-compat shim, re-exports Chunk from chunkers.base |
| Storage | `chunkforge/storage.py` | SQLite + filesystem persistence (chunks, documents) |
| Session Manager | `chunkforge/session.py` | Session lifecycle and turn management |
| Session Storage | `chunkforge/session_storage.py` | Session persistence (JSON + zlib) |
| NumPy Compat | `chunkforge/numpy_compat.py` | NumPy fallback + cosine_similarity helper |
| Vector Index | `chunkforge/index.py` | HNSW approximate nearest neighbor search |
| Index Store | `chunkforge/index_store.py` | Persistent index serialization + staleness detection |
| MCP Server | `chunkforge/mcp_stdio.py` | JSON-RPC over stdio MCP server |
| CLI | `chunkforge/cli.py` | Command-line interface (index, detect, search, serve-mcp, etc.) |
| Chunkers | `chunkforge/chunkers/` | Modality-specific content splitting |
| Tests | `tests/` | pytest suite (102 tests) |

## Version

Current: **v0.5.2** (2026-03-13)
