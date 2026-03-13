# ChunkForge Glossary

## Core Concepts

**Chunk** — A semantically coherent unit of content (text, code, image data, etc.) that can be independently indexed, cached, and restored. Typically 256-4096 tokens.

**KV-Cache** — Key-Value cache state from an LLM's attention mechanism. ChunkForge stores these so unchanged chunks don't need to be re-processed.

**Semantic Signature** — A 128-dimensional vector representing the semantic content of a chunk. Used for similarity comparison without requiring an LLM. Composed of character trigram frequencies, word distributions, and structural features.

**Content Hash** — SHA-256 hash of a chunk's content. Used for fast exact-match change detection.

**Session** — An independent context for KV-cache management. Each session tracks turns (conversation steps) and can be rolled back.

**Turn** — A single step in a session. KV states are stored per-chunk per-turn, enabling rollback to any previous turn.

**Modality** — The type of content: `text`, `code`, `image`, `pdf`, `audio`, `video`.

## Change Detection Tiers

1. **Hash Match** — Content hash unchanged → load cached KV instantly (zero tokens)
2. **Semantic Match** — Hash differs but cosine similarity > 0.85 → lightweight double-check, likely unchanged
3. **Reprocess** — Significant semantic change → mark chunk for full LLM reprocessing

## Chunking Strategies

**Paragraph-Based** — Split on `\n\n` boundaries, accumulate until target token count reached.

**Adaptive** — Like paragraph-based but adjusts target size based on content density. Dense content (code, lists) gets smaller chunks; sparse content (prose) gets larger chunks.

**Sliding Window** — Split on sentence boundaries with configurable overlap between adjacent chunks for context continuity.

**AST-Based** — For Python code: parse the AST and split at function/class definition boundaries.

**Regex-Based** — For non-Python code: use language-specific regex patterns to find function/class boundaries.

## Index Types

**HNSW** — Hierarchical Navigable Small World graph. A multi-layer graph structure for approximate nearest neighbor search in O(log n) time. Parameters: M (max connections), ef_construction (build quality), ef_search (query quality).

## Chunker Classes

| Chunker | Modality | Dependency | Extensions |
|---------|----------|------------|------------|
| `TextChunker` | text | (none) | .txt, .md, .rst, .csv, .log |
| `CodeChunker` | code | (none) | .py, .js, .ts, .java, .go, .rs, etc. |
| `ImageChunker` | image | Pillow | .png, .jpg, .gif, .webp, .bmp, .tiff |
| `PDFChunker` | pdf | pymupdf | .pdf |
| `AudioChunker` | audio | librosa | .mp3, .wav, .ogg, .flac, .m4a |
| `VideoChunker` | video | opencv | .mp4, .avi, .mov, .mkv, .webm |

## Configuration Defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 256 | Target tokens per initial chunk |
| `max_chunk_size` | 4096 | Maximum tokens per merged chunk |
| `merge_threshold` | 0.7 | Cosine similarity threshold for merging adjacent chunks |
| `change_threshold` | 0.85 | Cosine similarity threshold for considering a chunk "unchanged" |
| `storage_dir` | `~/.chunkforge/` | Base directory for all persistent data |
| `MCP port` | 9876 | Default MCP server port |
