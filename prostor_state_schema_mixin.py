"""SessionSchemaMixin - Schema initialization, column reconciliation.

Extracted from prostor_state.py (#26).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionSchemaMixin:
    """Schema initialization, column reconciliation mixin for SessionDB."""

    def __init__(self, db_path: Path = None, read_only: bool = False):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.read_only = read_only

        self._lock = threading.Lock()
        self._write_count = 0
        self._fts_enabled = False
        self._trigram_available = False
        self._fts_unavailable_warned = False
        self._conn = None
        try:
            if read_only:
                # Read-only attach for cross-profile aggregation: SELECT-only,
                # so we skip schema init entirely (no DDL, no FTS probe, no
                # column reconcile). Crucially this takes NO write lock, so
                # polling another profile's live DB on every sidebar refresh
                # never contends with that profile's running backend. The DB
                # must already exist + be initialised (callers guard on
                # db_path.exists()); a SELECT against an empty file raises and
                # the caller degrades per-profile.
                self._conn = sqlite3.connect(
                    f"file:{self.db_path}?mode=ro",
                    uri=True,
                    check_same_thread=False,
                    timeout=1.0,
                    isolation_level=None,
                )
                self._conn.row_factory = sqlite3.Row
                return

            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            def _connect_and_init():
                self._conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    # Short timeout — application-level retry with random
                    # jitter handles contention instead of sitting in
                    # SQLite's internal busy handler for up to 30s.
                    timeout=1.0,
                    # auto-starts transactions on DML, which conflicts with
                    # our explicit BEGIN IMMEDIATE.  None = we manage
                    # transactions ourselves.
                    isolation_level=None,
                )
                self._conn.row_factory = sqlite3.Row
                apply_wal_with_fallback(self._conn, db_label="state.db")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._init_schema()

            try:
                _connect_and_init()
            except sqlite3.DatabaseError as exc:
                # The malformed-schema class (e.g. a duplicate sqlite_master
                # row for messages_fts) fails on the very first statement —
                # before _init_schema can run — so it can't be caught at the
                # FTS-rebuild layer. Recover by repairing sqlite_master in
                # place (backup first; canonical sessions/messages preserved),
                # then reopen once. This is what lets Desktop/Dashboard
                # self-heal instead of silently showing "no sessions".
                if not is_malformed_db_error(exc) or not _claim_repair_attempt(self.db_path):
                    raise
                logger.error(
                    "state.db schema is malformed (%s) — attempting automatic "
                    "repair (a backup copy is made first).", exc,
                )
                try:
                    if self._conn is not None:
                        self._conn.close()
                except Exception:
                    pass
                report = repair_state_db_schema(self.db_path)
                if not report.get("repaired"):
                    raise
                _connect_and_init()
        except Exception as exc:
            # Capture the cause so /resume and friends can surface WHY the
            # session DB is unavailable instead of a bare "Session database
            # not available."  Callers that catch this exception keep their
            # existing ``self._session_db = None`` degradation path.
            #
            # Note: we deliberately do NOT clear _last_init_error on the
            # success path (no else branch).  In multi-threaded callers
            # (gateway, web_server per-request SessionDB()), a concurrent
            # successful open racing past this failure would erase the
            # cause that another thread's /resume is about to format.
            # Tests that need to reset the state can call
            # ``prostor_state._set_last_init_error(None)`` explicitly.
            _set_last_init_error(f"{type(exc).__name__}: {exc}")
            raise

    def _ensure_fts_schema(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        ddl: str,
    ) -> bool:
        status = self._fts_table_probe(cursor, table_name)
        if status is None:
            return False
        try:
            # Run even when the virtual table exists so any dropped or missing
            # triggers are recreated after a previous no-FTS5 runtime disabled
            # them to keep message writes working.
            cursor.executescript(ddl)
            return True
        except sqlite3.OperationalError as exc:
            if not self._is_fts5_unavailable_error(exc):
                raise
            # Only disable FTS entirely when the whole FTS5 module is missing.
            # A missing specific tokenizer (e.g. trigram) means only that
            # particular table cannot be created — the base FTS5 table is fine.
            if self._is_trigram_unavailable_error(exc):
                self._warn_trigram_unavailable(exc)
            else:
                self._warn_fts5_unavailable(exc)
            return False

    def _parse_schema_columns(schema_sql: str) -> Dict[str, Dict[str, str]]:
        """Extract expected columns per table from SCHEMA_SQL.

        Uses an in-memory SQLite database to parse the SQL — SQLite itself
        handles all syntax (DEFAULT expressions with commas, inline
        REFERENCES, CHECK constraints, etc.) so there are zero regex
        edge cases.  The in-memory DB is opened, the schema DDL is
        executed, and PRAGMA table_info extracts the column metadata.

        Adding a column to SCHEMA_SQL is all that's needed; the
        reconciliation loop picks it up automatically.
        """
        ref = sqlite3.connect(":memory:")
        try:
            ref.executescript(schema_sql)
            table_columns: Dict[str, Dict[str, str]] = {}
            for (tbl,) in ref.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall():
                cols: Dict[str, str] = {}
                for row in ref.execute(
                    f'PRAGMA table_info("{tbl}")'
                ).fetchall():
                    # row: (cid, name, type, notnull, dflt_value, pk)
                    col_name = row[1]
                    col_type = row[2] or ""
                    notnull = row[3]
                    default = row[4]
                    pk = row[5]
                    # Reconstruct the type expression for ALTER TABLE ADD COLUMN
                    parts = [col_type] if col_type else []
                    if notnull and not pk:
                        parts.append("NOT NULL")
                    if default is not None:
                        parts.append(f"DEFAULT {default}")
                    cols[col_name] = " ".join(parts)
                table_columns[tbl] = cols
            return table_columns
        finally:
            ref.close()

    def _reconcile_columns(self, cursor: sqlite3.Cursor) -> None:
        """Ensure live tables have every column declared in SCHEMA_SQL.

        Follows the Beets/sqlite-utils pattern: the CREATE TABLE definition
        in SCHEMA_SQL is the single source of truth for the desired schema.
        On every startup this method diffs the live columns (via PRAGMA
        table_info) against the declared columns, and ADDs any that are
        missing.

        This makes column additions a declarative operation — just add
        the column to SCHEMA_SQL and it appears on the next startup.
        Version-gated migration blocks are no longer needed for ADD COLUMN.
        """
        expected = self._parse_schema_columns(SCHEMA_SQL)
        for table_name, declared_cols in expected.items():
            # Get current columns from the live table
            try:
                rows = cursor.execute(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()
            except sqlite3.OperationalError:
                continue  # Table doesn't exist yet (shouldn't happen after executescript)
            live_cols = set()
            for row in rows:
                # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
                name = row[1] if isinstance(row, (tuple, list)) else row["name"]
                live_cols.add(name)

            for col_name, col_type in declared_cols.items():
                if col_name not in live_cols:
                    safe_name = col_name.replace('"', '""')
                    try:
                        cursor.execute(
                            f'ALTER TABLE "{table_name}" ADD COLUMN "{safe_name}" {col_type}'
                        )
                    except sqlite3.OperationalError as exc:
                        # Expected: "duplicate column name" from a race or
                        # re-run.  Unexpected: "Cannot add a NOT NULL column
                        # with default value NULL" from a schema mistake.
                        # Log at DEBUG so it's visible in agent.log.
                        logger.debug(
                            "reconcile %s.%s: %s", table_name, col_name, exc,
                        )

    def _init_schema(self):
        """Create tables and FTS if they don't exist, reconcile columns.

        Schema management follows the declarative reconciliation pattern
        (Beets, sqlite-utils): SCHEMA_SQL is the single source of truth.
        On existing databases, _reconcile_columns() diffs live columns
        against SCHEMA_SQL and ADDs any missing ones.  This eliminates
        the version-gated migration chain for column additions, making
        it impossible for reordered or inserted migrations to skip columns.

        The schema_version table is retained for future data migrations
        (transforming existing rows) which cannot be handled declaratively.
        """
        cursor = self._conn.cursor()

        cursor.executescript(SCHEMA_SQL)

        # ── Declarative column reconciliation ──────────────────────────
        # Diff live tables against SCHEMA_SQL and ADD any missing columns.
        # This is idempotent and self-healing: even if a version-gated
        # migration was skipped (e.g. due to version renumbering), the
        # column gets created here.
        self._reconcile_columns(cursor)

        # Indexes that reference reconciler-added columns must be created
        # AFTER _reconcile_columns runs — declaring them in SCHEMA_SQL
        # makes the initial executescript fail on legacy DBs (the index's
        # WHERE clause references a column that doesn't exist yet).
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_platform_msg_id "
                "ON messages(session_id, platform_message_id) "
                "WHERE platform_message_id IS NOT NULL"
            )
        except sqlite3.OperationalError as exc:
            logger.debug("idx_messages_platform_msg_id create skipped: %s", exc)

        # Deferred indexes that reference the reconciler-added ``active``
        # column (idx_messages_session_active) — same ordering constraint.
        cursor.executescript(DEFERRED_INDEX_SQL)

        fts5_available = self._sqlite_supports_fts5(cursor)
        fts_migrations_complete = True
        if not fts5_available:
            # Existing FTS triggers can still fire on messages INSERT/UPDATE
            # even though the current sqlite runtime cannot read the virtual
            # tables they target. Drop only the triggers so core persistence
            # continues; if a future runtime has FTS5, _ensure_fts_schema()
            # recreates them.
            self._drop_fts_triggers(cursor)

        # ── Schema version bookkeeping ─────────────────────────────────
        # Bump to current so future data migrations (if any) can gate on
        # version.  No version-gated column additions remain.
        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        else:
            current_version = row["version"] if isinstance(row, sqlite3.Row) else row[0]
            # Data migrations that can't be expressed declaratively (row
            # backfills, index changes tied to a specific version step) stay
            # in a version-gated chain. Column additions are handled by
            # _reconcile_columns() above and no longer need entries here.
            if current_version < 10 and SCHEMA_VERSION == 10:
                # v10: trigram FTS5 table for CJK/substring search. The
                # virtual table + triggers are created unconditionally via
                # FTS_TRIGRAM_SQL below, but existing rows need a one-time
                # backfill into the FTS index.
                #
                # Only run this when v10 itself is the target schema. Current
                # v11+ code drops and rebuilds both FTS tables below, so doing
                # the v10-only trigram backfill first only burns startup time
                # and WAL space before v11 throws the work away.
                if fts5_available:
                    _fts_trigram_exists = self._fts_table_probe(
                        cursor, "messages_fts_trigram"
                    )
                    if _fts_trigram_exists is False:
                        if self._ensure_fts_schema(
                            cursor, "messages_fts_trigram", FTS_TRIGRAM_SQL
                        ):
                            cursor.execute(
                                "INSERT INTO messages_fts_trigram(rowid, content) "
                                "SELECT id, content FROM messages WHERE content IS NOT NULL"
                            )
                        else:
                            fts_migrations_complete = False
                    elif _fts_trigram_exists is None:
                        fts_migrations_complete = False
                else:
                    fts_migrations_complete = False
            if current_version < 11:
                # v11: re-index FTS5 tables to cover tool_name + tool_calls and
                # switch from external-content to inline mode. Existing DBs have
                # old-schema FTS tables and triggers that IF NOT EXISTS won't
                # overwrite, so we drop them explicitly and let the post-migration
                # existence checks (below) recreate them from FTS_SQL /
                # FTS_TRIGRAM_SQL, then backfill every message row. Fixes #16751.
                if fts5_available:
                    self._drop_fts_triggers(cursor)
                    for _tbl in ("messages_fts", "messages_fts_trigram"):
                        try:
                            cursor.execute(f"DROP TABLE IF EXISTS {_tbl}")
                        except sqlite3.OperationalError as exc:
                            if not self._is_fts5_unavailable_error(exc):
                                raise
                            if self._is_trigram_unavailable_error(exc):
                                self._warn_trigram_unavailable(exc)
                            else:
                                self._warn_fts5_unavailable(exc)
                                fts5_available = False
                                fts_migrations_complete = False
                            break

                    if fts5_available:
                        # Recreate virtual tables + triggers with the new inline-mode
                        # schema that indexes content || tool_name || tool_calls.
                        # Handle base and trigram independently — a missing
                        # trigram tokenizer should not prevent base FTS backfill.
                        base_fts_ok = self._ensure_fts_schema(
                            cursor, "messages_fts", FTS_SQL
                        )
                        if base_fts_ok:
                            cursor.execute(
                                "INSERT INTO messages_fts(rowid, content) "
                                "SELECT id, "
                                "COALESCE(content, '') || ' ' || "
                                "COALESCE(tool_name, '') || ' ' || "
                                "COALESCE(tool_calls, '') "
                                "FROM messages"
                            )
                        trigram_ok = self._ensure_fts_schema(
                            cursor, "messages_fts_trigram", FTS_TRIGRAM_SQL
                        )
                        if trigram_ok:
                            cursor.execute(
                                "INSERT INTO messages_fts_trigram(rowid, content) "
                                "SELECT id, "
                                "COALESCE(content, '') || ' ' || "
                                "COALESCE(tool_name, '') || ' ' || "
                                "COALESCE(tool_calls, '') "
                                "FROM messages"
                            )
                        if not base_fts_ok:
                            fts_migrations_complete = False
                        # Track trigram availability for CJK LIKE fallback.
                        self._trigram_available = trigram_ok
                    else:
                        fts_migrations_complete = False
                else:
                    fts_migrations_complete = False
            if current_version < 12:
                # v12: messages.active flag for rewind/undo soft-deletion.
                # The declarative reconcile_columns() above adds the
                # column itself; this UPDATE is belt-and-suspenders to
                # ensure any rows that pre-existed the ADD COLUMN have
                # active=1 rather than NULL.
                try:
                    cursor.execute(
                        "UPDATE messages SET active = 1 WHERE active IS NULL"
                    )
                except sqlite3.OperationalError:
                    pass
            if current_version < 16:
                # v16: tag delegate subagent rows so pickers stay clean after
                # parent deletes that used to orphan them (parent_session_id → NULL).
                try:
                    cursor.execute(
                        "UPDATE sessions SET model_config = json_set("
                        "COALESCE(model_config, '{}'), '$._delegate_from', parent_session_id) "
                        f"WHERE parent_session_id IS NOT NULL "
                        "AND json_extract(COALESCE(model_config, '{}'), '$._delegate_from') IS NULL "
                        f"AND {_ephemeral_child_sql('sessions')}"
                    )
                    cursor.execute(
                        "UPDATE sessions SET model_config = json_set("
                        "COALESCE(model_config, '{}'), '$._delegate_from', '__orphaned__') "
                        "WHERE parent_session_id IS NULL "
                        "AND json_extract(COALESCE(model_config, '{}'), '$._delegate_from') IS NULL "
                        "AND json_extract(COALESCE(model_config, '{}'), '$._branched_from') IS NULL "
                        "AND title IS NULL "
                        "AND message_count <= 25 "
                        "AND EXISTS (SELECT 1 FROM messages m "
                        "            WHERE m.session_id = sessions.id AND m.role = 'tool') "
                        "AND NOT EXISTS (SELECT 1 FROM sessions ch "
                        "                WHERE ch.parent_session_id = sessions.id)"
                    )
                except sqlite3.OperationalError:
                    pass
            if current_version < SCHEMA_VERSION and fts_migrations_complete:
                cursor.execute(
                    "UPDATE schema_version SET version = ?",
                    (SCHEMA_VERSION,),
                )

        # Unique title index — always ensure it exists
        try:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_title_unique "
                "ON sessions(title) WHERE title IS NOT NULL"
            )
        except sqlite3.OperationalError:
            pass  # Index already exists

        if fts5_available:
            # FTS5 setup. Run the DDL even when the virtual table exists so
            # CREATE TRIGGER IF NOT EXISTS repairs trigger-only degradation from
            # an earlier no-FTS5 runtime.
            triggers_need_repair = self._fts_trigger_count(cursor) < len(_FTS_TRIGGERS)
            self._fts_enabled = self._ensure_fts_schema(cursor, "messages_fts", FTS_SQL)

            # Trigram FTS5 for CJK/substring search. This is optional relative
            # to the main FTS table; if it cannot be created, CJK search falls
            # back to LIKE.
            if self._fts_enabled:
                trigram_enabled = self._ensure_fts_schema(
                    cursor, "messages_fts_trigram", FTS_TRIGRAM_SQL
                )
                self._trigram_available = trigram_enabled
                if triggers_need_repair:
                    self._rebuild_fts_indexes(
                        cursor,
                        include_trigram=trigram_enabled,
                    )

        self._conn.commit()
