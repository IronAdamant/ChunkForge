# ChunkForge Wiki

## Pages

- [spec-project.md](spec-project.md) — Architecture, design decisions, module responsibilities
- [glossary.md](glossary.md) — Key terms and concepts

## Quick Reference

| Component | File | LOC | Purpose |
|-----------|------|-----|---------|
| Core Engine | `chunkforge/core.py` | ~1,050 | Chunking, indexing, change detection, KV management |
| Storage | `chunkforge/storage.py` | ~715 | SQLite + filesystem persistence |
| Vector Index | `chunkforge/index.py` | ~513 | HNSW approximate nearest neighbor search |
| MCP Server | `chunkforge/mcp_server.py` | ~409 | HTTP/JSON tool server |
| CLI | `chunkforge/cli.py` | ~369 | Command-line interface |
| Chunkers | `chunkforge/chunkers/` | ~1,800 | Modality-specific content splitting |
| Tests | `tests/` | ~970 | pytest suite (49 tests) |

## Version

Current: **v0.4.1** (2026-03-13)
