# Stele TODO

## Longer-Term (needs discussion)

### Tree-sitter for non-Python code chunking
- Current regex patterns for JS/TS/Java/C++/Go/Rust are brittle for nested structures
- Tree-sitter would give proper AST parsing for all supported languages
- Would be a new optional dependency (`[tree-sitter]` extra)
- Scope: replace `CodeChunker._chunk_regex()` path with tree-sitter walker
- Open questions: which tree-sitter bindings? grammar bundle size? fallback behavior?
