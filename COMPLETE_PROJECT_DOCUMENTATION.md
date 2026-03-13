# ChunkForge - Complete Project Documentation

## File Table

| Path | Purpose | Dependencies | Wiki Link |
|------|---------|-------------|-----------|
| `chunkforge/__init__.py` | Package entry point; exports `ChunkForge`, `StorageBackend`, `MCPServer`, `__version__` | core, storage, mcp_server | [index](wiki-local/index.md) |
| `chunkforge/core.py` | Main `ChunkForge` class and `Chunk` class; chunking, indexing, change detection, KV management, session rollback | storage, chunkers, numpy (optional) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/storage.py` | `StorageBackend` class; SQLite metadata + filesystem KV-cache persistence, session management, pruning | msgspec (optional), numpy (optional) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/index.py` | `HNSWIndex` and `VectorIndex` classes; pure-Python HNSW for O(log n) similarity search | (none) | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/cli.py` | CLI entry point (`chunkforge` command); serve, index, detect, stats, clear subcommands | core, mcp_server | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/mcp_server.py` | `MCPServer` + `MCPRequestHandler`; HTTP/JSON MCP tool server on localhost | core, chunkers | [spec-project](wiki-local/spec-project.md) |
| `chunkforge/chunkers/__init__.py` | Chunkers package; imports all chunkers, exports availability flags (`HAS_*_CHUNKER`) | base, text, code, image?, pdf?, audio?, video? | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/base.py` | `BaseChunker` ABC and `Chunk` dataclass; shared interface for all chunkers | (none) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/text.py` | `TextChunker`; paragraph-based, adaptive, and sliding-window text chunking | base | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/code.py` | `CodeChunker`; AST-based chunking for Python, regex for other languages | base | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/image.py` | `ImageChunker`; whole-image or tile-based chunking with perceptual hashing | base, Pillow (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/pdf.py` | `PDFChunker`; page-based PDF chunking with text extraction | base, pymupdf (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/audio.py` | `AudioChunker`; time-based segmentation with MFCC/spectral features | base, librosa (optional) | [glossary](wiki-local/glossary.md) |
| `chunkforge/chunkers/video.py` | `VideoChunker`; keyframe extraction with frame hashing | base, opencv-python (optional) | [glossary](wiki-local/glossary.md) |
| `tests/__init__.py` | Test package marker | - | - |
| `tests/conftest.py` | Shared pytest fixtures (`tmp_storage_dir`, sample files) | pytest | - |
| `tests/test_core.py` | Tests for `Chunk`, `ChunkForge`, `StorageBackend` | chunkforge | - |
| `tests/test_chunkers.py` | Tests for `TextChunker`, `CodeChunker`, `Chunk` dataclass | chunkforge.chunkers | - |
| `tests/test_index.py` | Tests for `HNSWIndex`, `VectorIndex` | chunkforge.index | - |
| `pyproject.toml` | Package configuration, dependencies, entry points | - | - |
| `pytest.ini` | Pytest configuration | - | - |
| `README.md` | Overview, installation, quickstart, API reference | - | - |
| `CHANGELOG.md` | Version history (Keep a Changelog format) | - | - |
| `CONTRIBUTING.md` | Contribution guidelines, dev setup, code style | - | - |
| `LICENSE` | MIT License | - | - |
| `.github/workflows/test.yml` | CI: runs pytest on Python 3.9-3.12 | - | - |
| `.github/workflows/publish.yml` | CD: publishes to PyPI on tag | - | - |
| `plans/v0.2-roadmap-and-release-checklist.md` | v0.2 planning doc | - | - |
| `plans/multimodal-assessment.md` | Multi-modal support assessment | - | - |

## Dependency Graph

```
chunkforge/__init__.py
  -> chunkforge.core (ChunkForge, Chunk)
      -> chunkforge.storage (StorageBackend)
      -> chunkforge.chunkers (TextChunker, CodeChunker, optional chunkers)
          -> chunkforge.chunkers.base (BaseChunker, Chunk dataclass)
  -> chunkforge.storage (StorageBackend)
  -> chunkforge.mcp_server (MCPServer)
      -> chunkforge.core
      -> chunkforge.chunkers

chunkforge.cli (entry point)
  -> chunkforge.core
  -> chunkforge.mcp_server

chunkforge.index (standalone, no internal deps)
```

## Architecture Notes

- **Two Chunk classes**: `chunkforge.core.Chunk` (regular class, used by ChunkForge engine) and `chunkforge.chunkers.base.Chunk` (dataclass, used by modality-specific chunkers). They share the same interface but have different implementations.
- **Optional dependencies**: Availability checked via inner flags (`HAS_PIL`, `HAS_PYMUPDF`, `HAS_LIBROSA`, `HAS_OPENCV`) re-exported as `HAS_*_CHUNKER` flags.
- **Zero required deps**: Core text/code functionality uses only Python stdlib. numpy and msgspec have pure-Python fallbacks.
