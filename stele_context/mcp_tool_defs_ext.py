"""
Tool definitions for the Stele MCP stdio server (extended tools).

Part 2: search (agent-optimized), symbols, sessions, document locking,
agents, environment, embeddings, chunk history, and notifications.
Each entry is a dict with name, description, and inputSchema.
Standalone module with zero internal dependencies.
"""

from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS_EXT: list[dict[str, Any]] = [
    # -- Primary: Agent Search (exact + structured) ---------------------------
    {
        "name": "agent_grep",
        "description": "Primary search tool for LLM agents — like grep but with "
        "scope annotation (enclosing function/class), syntactic classification "
        "(comment/import/definition/string/code), deduplication of identical "
        "lines, and token budgeting to prevent context overflow. "
        "USE WHEN: auditing symbol usage, verifying dead code, understanding "
        "how a pattern is used across the codebase, or any search needing "
        "structured context-aware results. Preferred over search_text and "
        "search for all verification and audit workflows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat pattern as a regex (default: false)",
                    "default": False,
                },
                "document_path": {
                    "type": "string",
                    "description": "Scope search to a specific file",
                },
                "classify": {
                    "type": "boolean",
                    "description": "Tag each match: comment/import/definition/string/code (default: true)",
                    "default": True,
                },
                "include_scope": {
                    "type": "boolean",
                    "description": "Annotate each match with enclosing function/class (default: true)",
                    "default": True,
                },
                "group_by": {
                    "type": "string",
                    "enum": ["file", "scope", "classification"],
                    "description": "How to group results (default: file)",
                    "default": "file",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Token budget for results — matches added until budget reached (default: 4000)",
                    "default": 4000,
                },
                "deduplicate": {
                    "type": "boolean",
                    "description": "Collapse structurally identical match lines (default: true)",
                    "default": True,
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context above/below each match (default: 0)",
                    "default": 0,
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_text",
        "description": "Exact substring or regex search with perfect recall — "
        "guaranteed to find every occurrence across all indexed chunks. "
        "USE WHEN: need guaranteed completeness for simple patterns without "
        "enrichment. For structured results with scope/classification, "
        "prefer agent_grep.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text pattern to search for",
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat pattern as a regex (default: false)",
                    "default": False,
                },
                "document_path": {
                    "type": "string",
                    "description": "Limit search to a specific document",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max chunks to return (default: 50)",
                    "default": 50,
                },
            },
            "required": ["pattern"],
        },
    },
    # -- Primary: Symbol Graph ------------------------------------------------
    {
        "name": "find_references",
        "description": "Find all definitions and usages of a symbol across the "
        "codebase (LSP-style). Returns a verdict field "
        "(unreferenced/referenced/external/not_found) for quick dead-code "
        "checks. More precise than text search — uses the parsed symbol graph. "
        "USE WHEN: verifying dead code before deletion, checking all callers "
        "before refactoring a function signature, understanding who depends "
        "on a symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name (function, class, CSS class like '.btn', CSS ID like '#app')",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "find_definition",
        "description": "Jump to where a symbol is defined, with full chunk content. "
        "USE WHEN: reading a function/class implementation, verifying a "
        "symbol's signature, understanding what a symbol does.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to find definition for",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "impact_radius",
        "description": "Find all chunks affected by changing a chunk or file "
        "(transitive dependents via symbol graph). "
        "Accepts chunk_id or document_path (at least one required). "
        "USE WHEN: assessing blast radius before editing, prioritizing test "
        "coverage, understanding downstream effects of a change.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Chunk ID to analyze impact for",
                },
                "document_path": {
                    "type": "string",
                    "description": "File path to analyze impact for (all chunks in file used as seeds)",
                },
                "depth": {
                    "type": "integer",
                    "description": "Max hops through dependency graph (default: 2)",
                    "default": 2,
                },
            },
        },
    },
    {
        "name": "coupling",
        "description": "Find files semantically coupled to a given file via shared "
        "symbol dependencies. Returns coupled files sorted by strength with "
        "direction (depends_on / depended_on_by / bidirectional) and shared "
        "symbol names. "
        "USE WHEN: assessing which files need co-modification, understanding "
        "tight coupling for refactoring, identifying related files to review "
        "together.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "File path to find coupled files for",
                },
            },
            "required": ["document_path"],
        },
    },
    {
        "name": "stale_chunks",
        "description": "Find chunks whose dependencies changed — detects context "
        "rot through the symbol graph. Staleness score: 0.8 = direct "
        "dependency changed, 0.64 = transitive. "
        "USE WHEN: checking if cached context is still valid after edits, "
        "identifying stale files that need re-review after upstream changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Minimum staleness score (0.0-1.0, default 0.3)",
                    "default": 0.3,
                },
            },
        },
    },
    {
        "name": "rebuild_symbols",
        "description": "Rebuild the entire symbol graph from stored chunks. "
        "USE WHEN: after upgrade, to repair a corrupted graph, or after "
        "bulk re-indexing.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # -- Secondary: Sessions --------------------------------------------------
    {
        "name": "list_sessions",
        "description": "List sessions, optionally filtered by agent ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Filter sessions by agent identifier",
                },
            },
        },
    },
    # -- Infrastructure: Document Locking -------------------------------------
    {
        "name": "acquire_document_lock",
        "description": "Acquire exclusive write lock on a document (multi-agent). "
        "Auto-acquired by MCP server when agent_id is set.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Document path to lock",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent claiming ownership",
                },
                "ttl": {
                    "type": "number",
                    "description": "Lock TTL in seconds (default: 300)",
                    "default": 300,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force-steal lock from another agent",
                    "default": False,
                },
            },
            "required": ["document_path", "agent_id"],
        },
    },
    {
        "name": "refresh_document_lock",
        "description": "Refresh lock TTL without releasing — prevents expiry during long operations",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Document path whose lock to refresh",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent that holds the lock",
                },
                "ttl": {
                    "type": "number",
                    "description": "New TTL in seconds (default: keep current)",
                },
            },
            "required": ["document_path", "agent_id"],
        },
    },
    {
        "name": "release_document_lock",
        "description": "Release write lock on a document",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Document path to unlock",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent releasing ownership",
                },
            },
            "required": ["document_path", "agent_id"],
        },
    },
    {
        "name": "get_document_lock_status",
        "description": "Check if a document is locked and by which agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Document path to check",
                },
            },
            "required": ["document_path"],
        },
    },
    {
        "name": "release_agent_locks",
        "description": "Release all document locks held by an agent (cleanup on disconnect)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent whose locks to release",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "get_conflicts",
        "description": "Get lock conflict audit log for documents or agents",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {
                    "type": "string",
                    "description": "Filter by document path",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Filter by agent ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries to return",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "reap_expired_locks",
        "description": "Clear all expired document locks and return what was reaped",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # -- Infrastructure: Agent Coordination -----------------------------------
    {
        "name": "list_agents",
        "description": "List agents registered across all worktrees with heartbeat status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "Only show active agents (default: true)",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "get_notifications",
        "description": "Get change notifications from other agents — what files "
        "changed since your last check. "
        "USE WHEN: checking for concurrent edits in multi-agent workflows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {
                    "type": "number",
                    "description": "Unix timestamp; only show notifications after this",
                },
                "exclude_self": {
                    "type": "string",
                    "description": "Agent ID to exclude from results",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max notifications (default: 100)",
                    "default": 100,
                },
            },
        },
    },
    # -- Infrastructure: Environment ------------------------------------------
    {
        "name": "environment_check",
        "description": "Check for stale __pycache__, editable install mismatches, "
        "and other environment issues",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clean_bytecache",
        "description": "Remove orphaned .pyc files from stale __pycache__ directories",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # -- Secondary: Semantic Enrichment ---------------------------------------
    {
        "name": "store_semantic_summary",
        "description": "Store semantic summary for a chunk to improve search quality. "
        "USE WHEN: you understand what a chunk does and want to improve "
        "future search results for it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Chunk ID to annotate",
                },
                "summary": {
                    "type": "string",
                    "description": "Semantic description (e.g. 'JWT middleware that validates tokens')",
                },
            },
            "required": ["chunk_id", "summary"],
        },
    },
    {
        "name": "bulk_store_summaries",
        "description": "Batch-store per-chunk semantic summaries. Each chunk gets "
        "its own agent signature computed from its summary. "
        "USE WHEN: after indexing, when you have per-chunk descriptions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Mapping of chunk_id to semantic summary text. "
                    'Example: {"chunk_abc123": "Database connection pool with retry logic"}',
                },
            },
            "required": ["summaries"],
        },
    },
    {
        "name": "store_embedding",
        "description": "Store a raw embedding vector for a chunk — for agents with "
        "embedding API access",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Chunk ID to update",
                },
                "vector": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Embedding vector (normalized to unit length)",
                },
            },
            "required": ["chunk_id", "vector"],
        },
    },
    # -- Secondary: Chunk History ---------------------------------------------
    {
        "name": "get_chunk_history",
        "description": "Get chunk version history — shows how chunks changed over "
        "indexing cycles",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Filter by specific chunk ID",
                },
                "document_path": {
                    "type": "string",
                    "description": "Filter by document path",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries to return (default: 50)",
                    "default": 50,
                },
            },
        },
    },
]
