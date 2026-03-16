"""
MCP (Model Context Protocol) server for ChunkForge.

Provides a minimal HTTP/JSON server running on localhost that exposes
ChunkForge tools for compatible coding agents. Uses only Python standard
library (http.server + json) with zero external dependencies.

The server implements the MCP tool discovery protocol, allowing agents
to discover and call ChunkForge tools naturally.

Supports multi-modal content: text, code, images, PDFs, audio, video.
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from chunkforge.engine import ChunkForge
from chunkforge.chunkers import (
    HAS_IMAGE_CHUNKER,
    HAS_PDF_CHUNKER,
    HAS_AUDIO_CHUNKER,
    HAS_VIDEO_CHUNKER,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schemas — single source of truth for tool discovery.
#
# Every tool in _get_tool_map() MUST have a matching entry here.  If a tool
# is added to the map but not to the schemas, discovery will auto-generate a
# minimal entry so it never silently disappears from /tools.
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "index_documents": {
        "description": "Index one or more documents for KV-cache management. Supports text, code, images, PDFs, audio, and video.",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document paths to index",
                },
                "force_reindex": {
                    "type": "boolean",
                    "description": "Force re-indexing even if document hasn't changed",
                    "default": False,
                },
            },
            "required": ["paths"],
        },
    },
    "detect_modality": {
        "description": "Detect the modality of a file (text, code, image, pdf, audio, video).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file",
                },
            },
            "required": ["path"],
        },
    },
    "get_supported_formats": {
        "description": "Get list of supported file formats by modality.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "detect_changes_and_update": {
        "description": "Detect changes in documents and update KV-cache accordingly.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "document_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of paths to check (defaults to all indexed)",
                },
            },
            "required": ["session_id"],
        },
    },
    "get_relevant_kv": {
        "description": "Get KV-cache for chunks most relevant to a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "query": {
                    "type": "string",
                    "description": "Query text to find relevant chunks for",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top chunks to return",
                    "default": 10,
                },
            },
            "required": ["session_id", "query"],
        },
    },
    "save_kv_state": {
        "description": "Save KV-cache state for a session.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "kv_data": {
                    "type": "object",
                    "description": "Dictionary mapping chunk_id to KV data",
                },
                "chunk_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of chunk IDs to save (defaults to all)",
                },
            },
            "required": ["session_id", "kv_data"],
        },
    },
    "rollback": {
        "description": "Rollback session to a previous turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "target_turn": {
                    "type": "integer",
                    "description": "Target turn number to rollback to",
                },
            },
            "required": ["session_id", "target_turn"],
        },
    },
    "prune_chunks": {
        "description": "Prune low-relevance chunks to stay under token limit.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum total tokens to keep",
                },
            },
            "required": ["session_id", "max_tokens"],
        },
    },
    "search": {
        "description": "Semantic search across indexed chunks. Returns content ranked by relevance.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    "get_context": {
        "description": "Get cached context for documents. Returns unchanged chunks, flags changed/new.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Document paths to get context for",
                },
            },
            "required": ["document_paths"],
        },
    },
    "find_references": {
        "description": "Find all definitions and references for a symbol name across indexed documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to search for",
                },
            },
            "required": ["symbol"],
        },
    },
    "find_definition": {
        "description": "Find the definition location of a symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to find",
                },
            },
            "required": ["symbol"],
        },
    },
    "impact_radius": {
        "description": "Find all chunks potentially affected by a change to a given chunk.",
        "parameters": {
            "type": "object",
            "properties": {
                "chunk_id": {
                    "type": "string",
                    "description": "Chunk ID to analyze",
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum hops to traverse (default: 2)",
                    "default": 2,
                },
            },
            "required": ["chunk_id"],
        },
    },
    "rebuild_symbol_graph": {
        "description": "Rebuild the symbol graph for all indexed documents.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "stale_chunks": {
        "description": "Find chunks with staleness scores above a threshold, grouped by document.",
        "parameters": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Minimum staleness score (default: 0.1)",
                    "default": 0.1,
                },
            },
            "required": [],
        },
    },
}


class MCPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MCP server."""

    def __init__(self, *args: Any, chunkforge: ChunkForge, **kwargs: Any):
        """Initialize with ChunkForge instance."""
        self.chunkforge = chunkforge
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger."""
        logger.info(format % args)

    def do_GET(self) -> None:
        """Handle GET requests (tool discovery)."""
        parsed = urlparse(self.path)

        if parsed.path == "/tools":
            self._handle_tools_discovery()
        elif parsed.path == "/health":
            self._handle_health()
        else:
            self._send_error(404, "Not found")

    def do_POST(self) -> None:
        """Handle POST requests (tool execution)."""
        parsed = urlparse(self.path)

        if parsed.path == "/call":
            self._handle_tool_call()
        else:
            self._send_error(404, "Not found")

    def _get_tool_map(self) -> Dict[str, Callable[..., Any]]:
        """Build tool name → callable mapping.

        Uses the same keys as _TOOL_SCHEMAS so discovery and execution
        always stay in sync.
        """
        def _get_supported_formats(**_: Any) -> Dict[str, Any]:
            formats = {
                "text": self.chunkforge.chunkers["text"].supported_extensions(),
                "code": self.chunkforge.chunkers["code"].supported_extensions(),
            }
            for modality, flag in [
                ("image", HAS_IMAGE_CHUNKER),
                ("pdf", HAS_PDF_CHUNKER),
                ("audio", HAS_AUDIO_CHUNKER),
                ("video", HAS_VIDEO_CHUNKER),
            ]:
                if flag and modality in self.chunkforge.chunkers:
                    formats[modality] = self.chunkforge.chunkers[
                        modality
                    ].supported_extensions()
            return {"formats": formats}

        def _detect_modality(path: str = "", **_: Any) -> Dict[str, Any]:
            return {"path": path, "modality": self.chunkforge.detect_modality(path)}

        return {
            "index_documents": self.chunkforge.index_documents,
            "detect_changes_and_update": self.chunkforge.detect_changes_and_update,
            "get_relevant_kv": self.chunkforge.get_relevant_kv,
            "save_kv_state": self.chunkforge.save_kv_state,
            "rollback": self.chunkforge.rollback,
            "prune_chunks": self.chunkforge.prune_chunks,
            "search": self.chunkforge.search,
            "get_context": self.chunkforge.get_context,
            "detect_modality": _detect_modality,
            "get_supported_formats": _get_supported_formats,
            "find_references": self.chunkforge.find_references,
            "find_definition": self.chunkforge.find_definition,
            "impact_radius": self.chunkforge.impact_radius,
            "rebuild_symbol_graph": self.chunkforge.rebuild_symbol_graph,
            "stale_chunks": self.chunkforge.stale_chunks,
        }

    def _handle_tools_discovery(self) -> None:
        """Return list of available tools.

        Generated dynamically from _get_tool_map() keys + _TOOL_SCHEMAS.
        Tools added to the map but missing from schemas get a minimal entry,
        so they're always discoverable.
        """
        tool_map = self._get_tool_map()
        tools: List[Dict[str, Any]] = []
        for name in tool_map:
            schema = _TOOL_SCHEMAS.get(name, {
                "description": name,
                "parameters": {"type": "object", "properties": {}, "required": []},
            })
            tools.append({"name": name, **schema})
        self._send_json_response({"tools": tools})

    def _handle_health(self) -> None:
        """Return health status."""
        stats = self.chunkforge.get_stats()
        self._send_json_response(
            {
                "status": "healthy",
                "version": stats["version"],
                "storage": stats["storage"],
            }
        )

    def _handle_tool_call(self) -> None:
        """Handle tool execution request."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request = json.loads(body.decode("utf-8"))

            tool_name = request.get("tool")
            parameters = request.get("parameters", {})

            if not tool_name:
                self._send_error(400, "Missing 'tool' field")
                return

            result = self._execute_tool(tool_name, parameters)
            self._send_json_response(result)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            logger.exception("Error executing tool")
            self._send_error(500, str(e))

    def _execute_tool(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a ChunkForge tool by name."""
        tool_map = self._get_tool_map()

        if tool_name not in tool_map:
            return {
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(tool_map.keys()),
            }

        try:
            result = tool_map[tool_name](**parameters)
            return {"success": True, "result": result}
        except TypeError as e:
            return {"error": f"Invalid parameters for {tool_name}: {e}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {e}"}

    def _send_json_response(self, data: Dict[str, Any], status: int = 200) -> None:
        """Send JSON response."""
        response = json.dumps(data, indent=2).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        self.wfile.write(response)

    def _send_error(self, status: int, message: str) -> None:
        """Send error response."""
        self._send_json_response({"error": message}, status)


class MCPServer:
    """MCP server for ChunkForge.

    Provides a minimal HTTP server that exposes ChunkForge tools
    for compatible coding agents.
    """

    def __init__(
        self,
        chunkforge: ChunkForge,
        host: str = "localhost",
        port: int = 9876,
    ):
        self.chunkforge = chunkforge
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = False) -> None:
        """Start the MCP server."""
        def handler_factory(*args: Any, **kwargs: Any) -> MCPRequestHandler:
            return MCPRequestHandler(*args, chunkforge=self.chunkforge, **kwargs)

        self.server = HTTPServer((self.host, self.port), handler_factory)

        logger.info(f"ChunkForge MCP server starting on http://{self.host}:{self.port}")
        logger.info("Available endpoints:")
        logger.info("  GET  /tools   - Discover available tools")
        logger.info("  GET  /health  - Health check")
        logger.info("  POST /call    - Execute a tool")

        if blocking:
            self.server.serve_forever()
        else:
            self._thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
                name="chunkforge-mcp-server",
            )
            self._thread.start()
            logger.info("Server running in background thread")

    def stop(self) -> None:
        """Stop the MCP server."""
        if self.server:
            logger.info("Stopping ChunkForge MCP server")
            self.server.shutdown()
            self.server = None

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def get_url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"
