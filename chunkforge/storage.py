"""
Storage backend for ChunkForge.

Handles persistent storage of:
- Chunk metadata (hashes, semantic signatures, positions)
- KV-cache tensors (serialized with msgspec or pickle, compressed with zlib)
- Session state and rollback history
- Document indexing information
- Chunk versioning and history

Uses SQLite for metadata and filesystem for KV-cache blobs.
All storage is local-only with zero network dependencies.
"""

import hashlib
import json
import os
import pickle
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import msgspec
    HAS_MSGSPEC = True
except ImportError:
    HAS_MSGSPEC = False
    msgspec = None  # type: ignore

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore


class StorageBackend:
    """
    Persistent storage backend for ChunkForge.
    
    Manages SQLite database for metadata and filesystem for KV-cache blobs.
    Provides methods for chunk storage, retrieval, and session management.
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize storage backend.
        
        Args:
            base_dir: Base directory for storage. Defaults to ~/.chunkforge/
        """
        if base_dir is None:
            base_dir = os.path.expanduser("~/.chunkforge")
        
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "chunkforge.db"
        self.kv_dir = self.base_dir / "kv_cache"
        self.index_dir = self.base_dir / "indices"
        
        # Create directories
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.kv_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Chunks table: stores chunk metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    semantic_signature BLOB NOT NULL,
                    start_pos INTEGER NOT NULL,
                    end_pos INTEGER NOT NULL,
                    token_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1
                )
            """)
            
            # Chunk history table: tracks chunk versions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_history (
                    chunk_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    semantic_signature BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (chunk_id, version),
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
                )
            """)
            
            # Documents table: tracks indexed documents
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at REAL NOT NULL,
                    last_modified REAL NOT NULL
                )
            """)
            
            # Sessions table: tracks KV-cache sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    turn_count INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0
                )
            """)
            
            # Session chunks: links chunks to sessions with KV state
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_chunks (
                    session_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    kv_path TEXT,
                    relevance_score REAL DEFAULT 1.0,
                    PRIMARY KEY (session_id, chunk_id, turn_number),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
                )
            """)
            
            # Create indices for fast lookups
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_chunks_session ON session_chunks(session_id)")
            
            conn.commit()
    
    def store_chunk(
        self,
        chunk_id: str,
        document_path: str,
        content_hash: str,
        semantic_signature: Any,
        start_pos: int,
        end_pos: int,
        token_count: int,
    ) -> None:
        """
        Store chunk metadata in database.
        
        Args:
            chunk_id: Unique identifier for the chunk
            document_path: Path to source document
            content_hash: SHA-256 hash of chunk content
            semantic_signature: Numpy array or list of semantic features
            start_pos: Start character position in document
            end_pos: End character position in document
            token_count: Estimated token count
        """
        now = time.time()
        
        # Convert semantic signature to bytes
        if HAS_NUMPY and hasattr(semantic_signature, 'tobytes'):
            sig_bytes = semantic_signature.tobytes()
        else:
            # Fallback: convert list to bytes using struct
            import struct
            sig_bytes = struct.pack(f'{len(semantic_signature)}f', *semantic_signature)
        
        # Get current version
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT version FROM chunks WHERE chunk_id = ?", (chunk_id,)
            )
            row = cursor.fetchone()
            version = (row[0] + 1) if row else 1
        
        with sqlite3.connect(self.db_path) as conn:
            # Store current version in history
            if row:
                conn.execute("""
                    INSERT INTO chunk_history
                    (chunk_id, version, content_hash, semantic_signature, created_at)
                    SELECT chunk_id, version, content_hash, semantic_signature, created_at
                    FROM chunks WHERE chunk_id = ?
                """, (chunk_id,))
            
            # Update or insert chunk
            conn.execute("""
                INSERT OR REPLACE INTO chunks
                (chunk_id, document_path, content_hash, semantic_signature,
                 start_pos, end_pos, token_count, created_at, last_accessed,
                 access_count, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (chunk_id, document_path, content_hash, sig_bytes,
                  start_pos, end_pos, token_count, now, now, version))
            conn.commit()
    
    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve chunk metadata by ID.
        
        Args:
            chunk_id: Unique identifier for the chunk
            
        Returns:
            Dictionary with chunk metadata or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return None
            
            # Update access statistics
            conn.execute("""
                UPDATE chunks 
                SET last_accessed = ?, access_count = access_count + 1
                WHERE chunk_id = ?
            """, (time.time(), chunk_id))
            conn.commit()
            
            return dict(row)
    
    def get_chunks_by_hash(self, content_hash: str) -> List[Dict[str, Any]]:
        """
        Find all chunks with a given content hash.
        
        Args:
            content_hash: SHA-256 hash to search for
            
        Returns:
            List of chunk metadata dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE content_hash = ?", (content_hash,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_document_chunks(self, document_path: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a document.
        
        Args:
            document_path: Path to the document
            
        Returns:
            List of chunk metadata dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE document_path = ? ORDER BY start_pos",
                (document_path,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def store_document(
        self,
        document_path: str,
        content_hash: str,
        chunk_count: int,
        last_modified: float,
    ) -> None:
        """
        Store document indexing information.
        
        Args:
            document_path: Path to the document
            content_hash: SHA-256 hash of document content
            chunk_count: Number of chunks created
            last_modified: Last modification timestamp
        """
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO documents
                (document_path, content_hash, chunk_count, indexed_at, last_modified)
                VALUES (?, ?, ?, ?, ?)
            """, (document_path, content_hash, chunk_count, now, last_modified))
            conn.commit()
    
    def get_document(self, document_path: str) -> Optional[Dict[str, Any]]:
        """
        Get document indexing information.
        
        Args:
            document_path: Path to the document
            
        Returns:
            Dictionary with document metadata or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM documents WHERE document_path = ?", (document_path,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_session(self, session_id: str) -> None:
        """
        Create a new KV-cache session.
        
        Args:
            session_id: Unique identifier for the session
        """
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO sessions
                (session_id, created_at, last_updated, turn_count, total_tokens)
                VALUES (?, ?, ?, 0, 0)
            """, (session_id, now, now))
            conn.commit()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session information.
        
        Args:
            session_id: Unique identifier for the session
            
        Returns:
            Dictionary with session metadata or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_session(
        self,
        session_id: str,
        turn_count: Optional[int] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        """
        Update session metadata.
        
        Args:
            session_id: Unique identifier for the session
            turn_count: New turn count (optional)
            total_tokens: New total token count (optional)
        """
        now = time.time()
        updates = ["last_updated = ?"]
        params: List[Any] = [now]
        
        if turn_count is not None:
            updates.append("turn_count = ?")
            params.append(turn_count)
        
        if total_tokens is not None:
            updates.append("total_tokens = ?")
            params.append(total_tokens)
        
        params.append(session_id)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                params
            )
            conn.commit()
    
    def store_kv_state(
        self,
        session_id: str,
        chunk_id: str,
        turn_number: int,
        kv_data: Any,
        relevance_score: float = 1.0,
    ) -> str:
        """
        Store KV-cache state for a chunk in a session.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            turn_number: Turn number in session
            kv_data: KV-cache data to store
            relevance_score: Relevance score for pruning
            
        Returns:
            Path to stored KV file
        """
        # Create session-specific directory
        session_kv_dir = self.kv_dir / session_id
        session_kv_dir.mkdir(exist_ok=True)
        
        # Generate filename
        kv_filename = f"{chunk_id}_turn{turn_number}.kv"
        kv_path = session_kv_dir / kv_filename
        
        # Serialize and store KV data
        try:
            # Try msgspec first (faster)
            encoded = msgspec.json.encode(kv_data)
            kv_path.write_bytes(encoded)
        except (TypeError, msgspec.EncodeError):
            # Fallback to pickle for complex objects
            with open(kv_path, "wb") as f:
                pickle.dump(kv_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Store reference in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO session_chunks
                (session_id, chunk_id, turn_number, kv_path, relevance_score)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, chunk_id, turn_number, str(kv_path), relevance_score))
            conn.commit()
        
        return str(kv_path)
    
    def load_kv_state(
        self,
        session_id: str,
        chunk_id: str,
        turn_number: int,
    ) -> Optional[Any]:
        """
        Load KV-cache state for a chunk in a session.
        
        Args:
            session_id: Session identifier
            chunk_id: Chunk identifier
            turn_number: Turn number in session
            
        Returns:
            KV-cache data or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT kv_path FROM session_chunks
                WHERE session_id = ? AND chunk_id = ? AND turn_number = ?
            """, (session_id, chunk_id, turn_number))
            row = cursor.fetchone()
        
        if row is None or row[0] is None:
            return None
        
        kv_path = Path(row[0])
        if not kv_path.exists():
            return None
        
        # Try to load with msgspec first
        try:
            data = kv_path.read_bytes()
            return msgspec.json.decode(data)
        except (msgspec.DecodeError, UnicodeDecodeError):
            # Fallback to pickle
            try:
                with open(kv_path, "rb") as f:
                    return pickle.load(f)
            except (pickle.UnpicklingError, EOFError):
                return None
    
    def get_session_chunks(
        self,
        session_id: str,
        turn_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks associated with a session.
        
        Args:
            session_id: Session identifier
            turn_number: Optional turn number filter
            
        Returns:
            List of chunk metadata with KV paths
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if turn_number is not None:
                cursor = conn.execute("""
                    SELECT sc.*, c.content_hash, c.semantic_signature, c.token_count
                    FROM session_chunks sc
                    JOIN chunks c ON sc.chunk_id = c.chunk_id
                    WHERE sc.session_id = ? AND sc.turn_number = ?
                    ORDER BY sc.relevance_score DESC
                """, (session_id, turn_number))
            else:
                cursor = conn.execute("""
                    SELECT sc.*, c.content_hash, c.semantic_signature, c.token_count
                    FROM session_chunks sc
                    JOIN chunks c ON sc.chunk_id = c.chunk_id
                    WHERE sc.session_id = ?
                    ORDER BY sc.turn_number DESC, sc.relevance_score DESC
                """, (session_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def rollback_session(self, session_id: str, target_turn: int) -> int:
        """
        Rollback session to a previous turn.
        
        Args:
            session_id: Session identifier
            target_turn: Target turn number to rollback to
            
        Returns:
            Number of chunks removed
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get current turn count
            cursor = conn.execute(
                "SELECT turn_count FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            
            current_turn = row[0]
            if target_turn >= current_turn:
                return 0
            
            # Remove chunks after target turn
            cursor = conn.execute("""
                DELETE FROM session_chunks
                WHERE session_id = ? AND turn_number > ?
            """, (session_id, target_turn))
            removed_count = cursor.rowcount
            
            # Update session turn count
            conn.execute("""
                UPDATE sessions SET turn_count = ?, last_updated = ?
                WHERE session_id = ?
            """, (target_turn, time.time(), session_id))
            
            conn.commit()
        
        # Clean up KV files
        self._cleanup_orphaned_kv_files(session_id)
        
        return removed_count
    
    def prune_chunks(
        self,
        session_id: str,
        max_tokens: int,
    ) -> int:
        """
        Prune low-relevance chunks to stay under token limit.
        
        Args:
            session_id: Session identifier
            max_tokens: Maximum total tokens to keep
            
        Returns:
            Number of chunks pruned
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get all chunks sorted by relevance (ascending = prune lowest first)
            cursor = conn.execute("""
                SELECT sc.chunk_id, sc.turn_number, c.token_count, sc.relevance_score
                FROM session_chunks sc
                JOIN chunks c ON sc.chunk_id = c.chunk_id
                WHERE sc.session_id = ?
                ORDER BY sc.relevance_score ASC
            """, (session_id,))
            
            chunks = [dict(row) for row in cursor.fetchall()]
            
            # Calculate total tokens
            total_tokens = sum(c["token_count"] for c in chunks)
            
            if total_tokens <= max_tokens:
                return 0
            
            # Remove lowest relevance chunks until under limit
            pruned_count = 0
            for chunk in chunks:
                if total_tokens <= max_tokens:
                    break
                
                conn.execute("""
                    DELETE FROM session_chunks
                    WHERE session_id = ? AND chunk_id = ? AND turn_number = ?
                """, (session_id, chunk["chunk_id"], chunk["turn_number"]))
                
                total_tokens -= chunk["token_count"]
                pruned_count += 1
            
            conn.commit()
        
        # Clean up KV files
        self._cleanup_orphaned_kv_files(session_id)
        
        return pruned_count
    
    def _cleanup_orphaned_kv_files(self, session_id: str) -> None:
        """Remove KV files that are no longer referenced in database."""
        session_kv_dir = self.kv_dir / session_id
        if not session_kv_dir.exists():
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT kv_path FROM session_chunks WHERE session_id = ?",
                (session_id,)
            )
            referenced_paths = {row[0] for row in cursor.fetchall() if row[0]}
        
        # Remove unreferenced files
        for kv_file in session_kv_dir.glob("*.kv"):
            if str(kv_file) not in referenced_paths:
                kv_file.unlink()
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with storage statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count chunks
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]
            
            # Count documents
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            doc_count = cursor.fetchone()[0]
            
            # Count sessions
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            session_count = cursor.fetchone()[0]
            
            # Calculate total tokens
            cursor = conn.execute("SELECT SUM(token_count) FROM chunks")
            total_tokens = cursor.fetchone()[0] or 0
            
            # Count chunk versions
            cursor = conn.execute("SELECT COUNT(*) FROM chunk_history")
            version_count = cursor.fetchone()[0]
        
        # Calculate disk usage
        kv_size = sum(f.stat().st_size for f in self.kv_dir.rglob("*") if f.is_file())
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        return {
            "chunk_count": chunk_count,
            "document_count": doc_count,
            "session_count": session_count,
            "total_tokens": total_tokens,
            "version_count": version_count,
            "kv_cache_size_bytes": kv_size,
            "database_size_bytes": db_size,
            "storage_dir": str(self.base_dir),
        }
    
    def clear_all(self) -> None:
        """Clear all stored data. Use with caution!"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM session_chunks")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM chunk_history")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.commit()
        
        # Remove KV cache files
        for kv_file in self.kv_dir.rglob("*.kv"):
            kv_file.unlink()
    
    def get_chunk_history(self, chunk_id: str) -> List[Dict[str, Any]]:
        """
        Get version history for a chunk.
        
        Args:
            chunk_id: Chunk identifier
            
        Returns:
            List of version metadata dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM chunk_history
                WHERE chunk_id = ?
                ORDER BY version DESC
            """, (chunk_id,))
            return [dict(row) for row in cursor.fetchall()]
