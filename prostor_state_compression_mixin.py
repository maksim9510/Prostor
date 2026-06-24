"""SessionCompressionMixin - Compression lock management.

Extracted from prostor_state.py (#26).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SessionCompressionMixin:
    """Compression lock management mixin for SessionDB."""

    def try_acquire_compression_lock(
        self,
        session_id: str,
        holder: str,
        ttl_seconds: float = 300.0,
    ) -> bool:
        """Try to atomically acquire the compression lock for ``session_id``.

        Returns ``True`` on success (caller now owns the lock and must
        release via :meth:`release_compression_lock`).  Returns ``False``
        if another holder already owns a non-expired lock — the caller
        MUST NOT proceed with compression in that case (its rotation would
        race against the holder's, splitting the session lineage).

        Expired locks (``expires_at < now``) are reclaimed transparently:
        the stale row is deleted and the new holder acquires it. This
        prevents a crashed compressor from permanently blocking the
        session.

        Implementation: single-transaction DELETE-expired + INSERT-or-IGNORE,
        followed by a SELECT to confirm we got the row. SQLite serialises
        writes, so the whole sequence is atomic against other writers.
        """
        if not session_id:
            return False
        now = time.time()
        expires_at = now + ttl_seconds

        def _do(conn):
            # First: reclaim any expired lock for this session_id.
            conn.execute(
                "DELETE FROM compression_locks "
                "WHERE session_id = ? AND expires_at < ?",
                (session_id, now),
            )
            # Then: try to insert. INSERT OR IGNORE returns no rowcount
            # difference — verify ownership via SELECT.
            conn.execute(
                "INSERT OR IGNORE INTO compression_locks "
                "(session_id, holder, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, holder, now, expires_at),
            )
            row = conn.execute(
                "SELECT holder FROM compression_locks WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row is not None and (
                row["holder"] if isinstance(row, sqlite3.Row) else row[0]
            ) == holder

        try:
            return bool(self._execute_write(_do))
        except sqlite3.Error as exc:
            logger.warning(
                "try_acquire_compression_lock(%s) failed: %s",
                session_id, exc,
            )
            # Fail open: returning False makes the caller skip compression,
            # which is the safe behaviour when the lock subsystem is broken.
            return False

    def release_compression_lock(self, session_id: str, holder: str) -> None:
        """Release the compression lock for ``session_id`` iff we own it.

        Idempotent: no-op when the lock has already expired and been
        reclaimed by a different holder, or when no lock exists. The
        ``holder`` check prevents a late-returning compressor from
        clobbering a fresh lock held by someone else.
        """
        if not session_id:
            return

        def _do(conn):
            conn.execute(
                "DELETE FROM compression_locks "
                "WHERE session_id = ? AND holder = ?",
                (session_id, holder),
            )

        try:
            self._execute_write(_do)
        except sqlite3.Error as exc:
            logger.warning(
                "release_compression_lock(%s) failed: %s",
                session_id, exc,
            )

    def get_compression_lock_holder(self, session_id: str) -> str | None:
        """Return the current (non-expired) holder for ``session_id``, or None.

        Diagnostic helper — not used by the locking protocol itself.
        """
        if not session_id:
            return None
        now = time.time()
        row = self._conn.execute(
            "SELECT holder FROM compression_locks "
            "WHERE session_id = ? AND expires_at >= ?",
            (session_id, now),
        ).fetchone()
        if row is None:
            return None
        return row["holder"] if isinstance(row, sqlite3.Row) else row[0]

    def finalize_orphaned_compression_sessions(self) -> int:
        """Mark orphaned compression continuation sessions as ended.

        Targets child sessions that were never finalized: parent is ended
        with reason='compression', child has messages but no end_reason/ended_at
        and api_call_count=0.  Non-destructive: preserves all messages and sets
        end_reason='orphaned_compression'.  Fix for #20001.
        """
        cutoff = time.time() - 604800  # 7 days

        def _do(conn):
            now = time.time()
            result = conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?,
                    end_reason = 'orphaned_compression'
                WHERE api_call_count = 0
                  AND end_reason IS NULL
                  AND ended_at IS NULL
                  AND started_at < ?
                  AND parent_session_id IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM sessions p
                      WHERE p.id = sessions.parent_session_id
                        AND p.end_reason = 'compression'
                        AND p.ended_at IS NOT NULL
                  )
                  AND EXISTS (
                      SELECT 1 FROM messages m
                      WHERE m.session_id = sessions.id
                  )
                """,
                (now, cutoff),
            )
            return result.rowcount

        return self._execute_write(_do) or 0

    def _is_compression_ancestor(
        self, conn, *, ancestor_id: str, descendant_id: str
    ) -> bool:
        """Return True if *ancestor_id* is a compression predecessor of
        *descendant_id* (walking parent links up the continuation chain).

        The continuation edge is the canonical one shared with
        :func:`_ephemeral_child_sql` / :meth:`set_session_archived`
        (``_COMPRESSION_CHILD_SQL``): a parent → child edge counts only when the
        parent ended with ``end_reason = 'compression'`` and the child started
        at or after the parent's ``ended_at``, which distinguishes continuations
        from delegate subagents / branch children that also carry a
        ``parent_session_id``. Expressed as a single recursive CTE rather than a
        per-hop Python walk so the edge definition lives in exactly one place.
        """
        if not ancestor_id or not descendant_id or ancestor_id == descendant_id:
            return False
        # Walk parent links up from the descendant, following only compression
        # continuation edges, and check whether ancestor_id is reached.
        edge = _COMPRESSION_CHILD_SQL.format(a="child")
        row = conn.execute(
            f"""
            WITH RECURSIVE ancestors(id) AS (
                SELECT ?
                UNION
                SELECT parent.id
                FROM ancestors a
                JOIN sessions child ON child.id = a.id
                JOIN sessions parent ON parent.id = child.parent_session_id
                WHERE {edge}
            )
            SELECT 1 FROM ancestors WHERE id = ? AND id != ? LIMIT 1
            """,
            (descendant_id, ancestor_id, descendant_id),
        ).fetchone()
        return row is not None

    def get_compression_tip(self, session_id: str) -> str | None:
        """Walk the compression-continuation chain forward and return the tip.

        A compression continuation is a child session where:
        1. The parent's ``end_reason = 'compression'``
        2. The child was created AFTER the parent was ended (started_at >= ended_at)

        The second condition distinguishes compression continuations from
        delegate subagents or branch children, which can also have a
        ``parent_session_id`` but were created while the parent was still live.

        Returns the session_id of the latest continuation in the chain, or the
        input ``session_id`` if it isn't part of a compression chain (or if the
        input itself doesn't exist).
        """
        current = session_id
        # Bound the walk defensively — compression chains this deep are
        # pathological and shouldn't happen in practice. 100 = plenty.
        for _ in range(100):
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT id FROM sessions "
                    "WHERE parent_session_id = ? "
                    "  AND started_at >= ("
                    "      SELECT ended_at FROM sessions "
                    "      WHERE id = ? AND end_reason = 'compression'"
                    "  ) "
                    "ORDER BY started_at DESC LIMIT 1",
                    (current, current),
                )
                row = cursor.fetchone()
            if row is None:
                return current
            current = row["id"]
        return current
