"""SessionCrudMixin - Session CRUD operations.

Extracted from prostor_state.py (#26).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionCrudMixin:
    """Session CRUD operations mixin for SessionDB."""

    def create_session(self, session_id: str, source: str, **kwargs) -> str:
        """Create a new session record. Returns the session_id."""
        self._insert_session_row(session_id, source, **kwargs)
        return session_id

    def end_session(self, session_id: str, end_reason: str) -> None:
        """Mark a session as ended.

        No-ops when the session is already ended. The first end_reason wins:
        compression-split sessions must keep their ``end_reason = 'compression'``
        record even if a later stale ``end_session()`` call (e.g. from a
        desynced CLI session_id after ``/resume`` or ``/branch``) targets them
        with a different reason. Use ``reopen_session()`` first if you
        intentionally need to re-end a closed session with a new reason.
        """
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? "
                "WHERE id = ? AND ended_at IS NULL",
                (time.time(), end_reason, session_id),
            )
        self._execute_write(_do)

    def reopen_session(self, session_id: str) -> None:
        """Clear ended_at/end_reason so a session can be resumed."""
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = NULL, end_reason = NULL WHERE id = ?",
                (session_id,),
            )
        self._execute_write(_do)

    def update_session_cwd(self, session_id: str, cwd: str) -> None:
        """Persist the session working directory when a frontend knows it."""
        if not session_id or not cwd:
            return

        def _do(conn):
            conn.execute("UPDATE sessions SET cwd = ? WHERE id = ?", (cwd, session_id))

        self._execute_write(_do)

    def update_session_meta(
        self,
        session_id: str,
        model_config_json: str,
        model: Optional[str] = None,
    ) -> None:
        """Update model_config and optionally model for an existing session.

        Uses COALESCE so that passing model=None leaves the stored model
        column unchanged.  Routes through _execute_write for the standard
        BEGIN IMMEDIATE + jitter-retry + lock guarantee.
        """
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET model_config = ?, model = COALESCE(?, model) WHERE id = ?",
                (model_config_json, model, session_id),
            )
        self._execute_write(_do)

    def update_session_model(self, session_id: str, model: str) -> None:
        """Update the model for a session after a mid-session switch.

        Unlike ``update_token_counts`` which uses ``COALESCE(model, ?)``
        (only filling in NULL), this unconditionally sets the model column
        so that the dashboard reflects the user's latest /model choice.
        """
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET model = ? WHERE id = ?",
                (model, session_id),
            )
        self._execute_write(_do)

