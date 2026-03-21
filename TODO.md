# Stele TODO

## Completed (v0.9.0)

- ~~Tree-sitter for non-Python code chunking~~ — Implemented with `pip install stele[tree-sitter]`. Supports JS/TS, Java, C/C++, Go, Rust, Ruby, PHP. Falls back to regex when not installed.
- ~~`.stele.toml` configuration system~~ — Reads from `<project_root>/.stele.toml` with minimal TOML parser fallback for Python 3.9-3.10.
- ~~Chunk history query tools~~ — `get_chunk_history()` exposed via MCP.
- ~~Performance benchmarks~~ — `benchmarks/` directory with chunking, storage, and search benchmarks.

## Remaining (nice-to-have)

### Documentation polish
- Architecture Mermaid diagram in README
- Comparison table vs alternatives (LangChain, LlamaIndex, EverMemOS)
- FAQ and troubleshooting sections

### CODE_OF_CONDUCT.md
- Contributor Covenant or similar

### Test coverage enforcement
- Add `--cov --cov-fail-under=90` to CI workflow

### Local sentence embeddings (advanced signatures)
- Small ONNX model for semantic embeddings
- Would be `[embeddings]` optional dependency
- Currently using 128-dim statistical signatures (trigrams, bigrams, structural)
