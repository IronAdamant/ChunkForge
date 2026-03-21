"""
Document ownership and optimistic locking storage for Stele.

Manages per-document locks, version checking, and conflict logging
for multi-agent coordination. Follows the same delegate pattern as
SessionStorage, MetadataStorage, and SymbolStorage.

Shared lock primitives (refresh, record_conflict, get_conflicts,
release_agent_locks, reap_expired_locks) live in ``lock_ops.py``
and are reused by ``CoordinationBackend``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from stele import lock_ops
from stele.storage_schema import connect


class DocumentLockStorage:
    """Per-document ownership, optimistic locking, and conflict log.

    Owns the ``locked_by``, ``locked_at``, ``lock_ttl``, ``doc_version``
    columns on the ``documents`` table, and the ``document_conflicts``
    table.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    # -- Per-document ownership -----------------------------------------------

    def acquire_lock(
        self,
        document_path: str,
        agent_id: str,
        ttl: float = 300.0,
        force: bool = False,
    ) -> dict[str, Any]:
        """Acquire exclusive ownership of a document.

        Expired locks are transparently reclaimed.  If ``force=True``,
        the lock is stolen and a conflict is logged.
        """
        now = time.time()
        with connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT locked_by, locked_at, lock_ttl, doc_version "
                "FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()

            if row is None:
                return {"acquired": False, "reason": "document_not_found"}

            current_owner = row["locked_by"]
            locked_at = row["locked_at"] or 0.0
            current_ttl = row["lock_ttl"] or 300.0
            expired = current_owner and (now > locked_at + current_ttl)

            if current_owner and current_owner != agent_id and not expired:
                if not force:
                    return {
                        "acquired": False,
                        "locked_by": current_owner,
                        "locked_at": locked_at,
                        "expires_at": locked_at + current_ttl,
                    }
                lock_ops.record_conflict(
                    conn,
                    "document_conflicts",
                    document_path,
                    current_owner,
                    agent_id,
                    "lock_stolen",
                    resolution="force_overwritten",
                )

            conn.execute(
                "UPDATE documents SET locked_by = ?, locked_at = ?, lock_ttl = ? "
                "WHERE document_path = ?",
                (agent_id, now, ttl, document_path),
            )
            conn.commit()
            return {"acquired": True, "doc_version": row["doc_version"]}

    def refresh_lock(
        self,
        document_path: str,
        agent_id: str,
        ttl: float | None = None,
    ) -> dict[str, Any]:
        """Reset the TTL timer on an existing lock without releasing it."""
        with connect(self.db_path) as conn:
            return lock_ops.refresh_lock(
                conn,
                "documents",
                document_path,
                agent_id,
                ttl,
                not_found_reason="document_not_found",
            )

    def release_lock(
        self,
        document_path: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """Release ownership.  Only the holder can release."""
        with connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT locked_by FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()
            if row is None:
                return {"released": False, "reason": "document_not_found"}
            if row["locked_by"] != agent_id:
                return {"released": False, "reason": "not_owner"}
            conn.execute(
                "UPDATE documents SET locked_by = NULL, locked_at = NULL "
                "WHERE document_path = ?",
                (document_path,),
            )
            conn.commit()
            return {"released": True}

    def get_lock_status(self, document_path: str) -> dict[str, Any]:
        """Check lock status.  Expired locks are reported as unlocked."""
        now = time.time()
        with connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT locked_by, locked_at, lock_ttl "
                "FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()
            if row is None:
                return {"locked": False, "reason": "document_not_found"}

            owner = row["locked_by"]
            locked_at = row["locked_at"] or 0.0
            ttl = row["lock_ttl"] or 300.0

            if not owner or now > locked_at + ttl:
                return {"locked": False}

            return {
                "locked": True,
                "locked_by": owner,
                "locked_at": locked_at,
                "expires_at": locked_at + ttl,
            }

    def release_agent_locks(self, agent_id: str) -> dict[str, Any]:
        """Release all locks held by an agent (cleanup on disconnect)."""
        with connect(self.db_path) as conn:
            return lock_ops.release_agent_locks(conn, "documents", agent_id)

    def reap_expired_locks(self) -> dict[str, Any]:
        """Clear all expired locks.  Returns details of reaped locks."""
        with connect(self.db_path) as conn:
            return lock_ops.reap_expired_locks(conn, "documents")

    def get_lock_stats(self) -> dict[str, Any]:
        """Get aggregate lock and conflict statistics."""
        now = time.time()
        with connect(self.db_path) as conn:
            total_locked = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE locked_by IS NOT NULL"
            ).fetchone()[0]

            expired_locks = conn.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE locked_by IS NOT NULL "
                "AND (locked_at + lock_ttl) < ?",
                (now,),
            ).fetchone()[0]

            total_conflicts = conn.execute(
                "SELECT COUNT(*) FROM document_conflicts"
            ).fetchone()[0]

            last_conflict_at = conn.execute(
                "SELECT MAX(created_at) FROM document_conflicts"
            ).fetchone()[0]

            active_agents = conn.execute(
                "SELECT COUNT(DISTINCT locked_by) FROM documents "
                "WHERE locked_by IS NOT NULL"
            ).fetchone()[0]

        return {
            "locked_documents": total_locked,
            "expired_locks": expired_locks,
            "active_lock_agents": active_agents,
            "total_conflicts": total_conflicts,
            "last_conflict_at": last_conflict_at,
        }

    # -- Optimistic locking ---------------------------------------------------

    def get_version(self, document_path: str) -> int | None:
        """Get current version of a document."""
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT doc_version FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()
            return row[0] if row else None

    def increment_version(self, document_path: str) -> int:
        """Atomically increment version, return new value."""
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET doc_version = doc_version + 1 "
                "WHERE document_path = ?",
                (document_path,),
            )
            row = conn.execute(
                "SELECT doc_version FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()
            conn.commit()
            return row[0] if row else 1

    def check_and_increment_version(
        self,
        document_path: str,
        expected_version: int,
    ) -> dict[str, Any]:
        """Atomic compare-and-swap on doc_version."""
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT doc_version FROM documents WHERE document_path = ?",
                (document_path,),
            ).fetchone()
            if row is None:
                return {"success": False, "reason": "document_not_found"}

            actual = row[0] or 1
            if actual != expected_version:
                return {
                    "success": False,
                    "expected": expected_version,
                    "actual": actual,
                }

            conn.execute(
                "UPDATE documents SET doc_version = ? WHERE document_path = ?",
                (actual + 1, document_path),
            )
            conn.commit()
            return {"success": True, "new_version": actual + 1}

    # -- Conflict log ---------------------------------------------------------

    def record_conflict(
        self,
        document_path: str,
        agent_a: str,
        agent_b: str,
        conflict_type: str,
        expected_version: int | None = None,
        actual_version: int | None = None,
        resolution: str = "rejected",
        details: dict[str, Any] | None = None,
    ) -> int | None:
        """Log a conflict event.  Returns conflict ID."""
        with connect(self.db_path) as conn:
            return lock_ops.record_conflict(
                conn,
                "document_conflicts",
                document_path,
                agent_a,
                agent_b,
                conflict_type,
                expected_version,
                actual_version,
                resolution,
                details,
            )

    def get_conflicts(
        self,
        document_path: str | None = None,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve conflict history with optional filters."""
        with connect(self.db_path) as conn:
            return lock_ops.query_conflicts(
                conn,
                "document_conflicts",
                document_path,
                agent_id,
                limit,
            )

    def prune_conflicts(
        self,
        max_age_seconds: float | None = None,
        max_entries: int | None = None,
    ) -> int:
        """Prune old conflict entries.  Returns deleted count."""
        deleted = 0
        with connect(self.db_path) as conn:
            if max_age_seconds is not None:
                cutoff = time.time() - max_age_seconds
                cursor = conn.execute(
                    "DELETE FROM document_conflicts WHERE created_at < ?",
                    (cutoff,),
                )
                deleted += cursor.rowcount

            if max_entries is not None:
                cursor = conn.execute(
                    "DELETE FROM document_conflicts WHERE id NOT IN "
                    "(SELECT id FROM document_conflicts ORDER BY created_at DESC LIMIT ?)",
                    (max_entries,),
                )
                deleted += cursor.rowcount

            conn.commit()
        return deleted
