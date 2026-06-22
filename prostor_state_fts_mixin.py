"""SessionFtsMixin - Full-text search (FTS5) and trigram support.

Extracted from prostor_state.py (#26).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionFtsMixin:
    """Full-text search (FTS5) and trigram support mixin for SessionDB."""

    def _is_fts5_unavailable_error(exc: sqlite3.OperationalError) -> bool:
        err = str(exc).lower()
        if "no such module" in err and "fts5" in err:
            return True
        # SQLite builds that have FTS5 but lack the optional trigram tokenizer
        # raise "no such tokenizer: trigram" instead of "no such module".
        # Scope to trigram specifically to avoid masking unrelated tokenizer errors.
        if "no such tokenizer: trigram" in err:
            return True
        return False

    def _is_trigram_unavailable_error(exc: sqlite3.OperationalError) -> bool:
        """True when only the trigram tokenizer is missing (FTS5 itself works)."""
        return "no such tokenizer: trigram" in str(exc).lower()

    def _warn_trigram_unavailable(self, exc: sqlite3.OperationalError) -> None:
        """Log once that the trigram tokenizer is missing; base FTS5 stays enabled."""
        if getattr(self, "_trigram_unavailable_warned", False):
            return
        self._trigram_unavailable_warned = True
        logger.info(
            "SQLite trigram tokenizer unavailable for %s "
            "(requires SQLite >= 3.34, this build is %s); "
            "CJK/substring search will fall back to LIKE: %s",
            self.db_path,
            sqlite3.sqlite_version,
            exc,
        )

    def _warn_fts5_unavailable(self, exc: sqlite3.OperationalError) -> None:
        self._fts_enabled = False
        if self._fts_unavailable_warned:
            return
        self._fts_unavailable_warned = True
        logger.warning(
            "SQLite FTS5 unavailable for %s; full-text session search "
            "disabled. Run `prostor update` to rebuild the venv with a "
            "current Python (managed uv guarantees FTS5). "
            "(underlying error: %s)",
            self.db_path,
            exc,
        )

    def _sqlite_supports_fts5(self, cursor: sqlite3.Cursor) -> bool:
        try:
            cursor.execute("CREATE VIRTUAL TABLE temp._prostor_fts5_probe USING fts5(x)")
            cursor.execute("DROP TABLE temp._prostor_fts5_probe")
            return True
        except sqlite3.OperationalError as exc:
            if not self._is_fts5_unavailable_error(exc):
                raise
            self._warn_fts5_unavailable(exc)
            return False

    def _drop_fts_triggers(cursor: sqlite3.Cursor) -> None:
        for trigger in _FTS_TRIGGERS:
            try:
                cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            except sqlite3.OperationalError:
                pass

    def _fts_trigger_count(cursor: sqlite3.Cursor) -> int:
        placeholders = ",".join("?" for _ in _FTS_TRIGGERS)
        row = cursor.execute(
            f"SELECT COUNT(*) FROM sqlite_master "
            f"WHERE type = 'trigger' AND name IN ({placeholders})",
            _FTS_TRIGGERS,
        ).fetchone()
        return int(row[0] if not isinstance(row, sqlite3.Row) else row[0])

    def _rebuild_fts_indexes(
        cursor: sqlite3.Cursor,
        *,
        include_trigram: bool = True,
    ) -> None:
        cursor.execute("DELETE FROM messages_fts")
        cursor.execute(
            "INSERT INTO messages_fts(rowid, content) "
            "SELECT id, "
            "COALESCE(content, '') || ' ' || "
            "COALESCE(tool_name, '') || ' ' || "
            "COALESCE(tool_calls, '') "
            "FROM messages"
        )
        if not include_trigram:
            return
        cursor.execute("DELETE FROM messages_fts_trigram")
        cursor.execute(
            "INSERT INTO messages_fts_trigram(rowid, content) "
            "SELECT id, "
            "COALESCE(content, '') || ' ' || "
            "COALESCE(tool_name, '') || ' ' || "
            "COALESCE(tool_calls, '') "
            "FROM messages"
        )

    def _fts_table_probe(self, cursor: sqlite3.Cursor, table_name: str) -> Optional[bool]:
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
            return True
        except sqlite3.OperationalError as exc:
            if self._is_fts5_unavailable_error(exc):
                # Only disable FTS entirely when the whole module is missing.
                # A missing trigram tokenizer only affects trigram searches.
                if self._is_trigram_unavailable_error(exc):
                    self._warn_trigram_unavailable(exc)
                else:
                    self._warn_fts5_unavailable(exc)
                return None
            if "no such table" in str(exc).lower():
                return False
            raise

    def _sanitize_fts5_query(query: str) -> str:
        """Sanitize user input for safe use in FTS5 MATCH queries.

        FTS5 has its own query syntax where characters like ``"``, ``(``, ``)``,
        ``+``, ``*``, ``{``, ``}``, the column-filter operator ``:`` and bare
        boolean operators (``AND``, ``OR``, ``NOT``) have special meaning.
        Passing raw user input directly to MATCH can cause
        ``sqlite3.OperationalError``.

        Strategy:
        - Preserve properly paired quoted phrases (``"exact phrase"``)
        - Strip unmatched FTS5-special characters that would cause errors
        - Wrap unquoted hyphenated and dotted terms in quotes so FTS5
          matches them as exact phrases instead of splitting on the
          hyphen/dot (e.g. ``chat-send``, ``P2.2``, ``my-app.config.ts``)
        """
        # Step 1: Extract balanced double-quoted phrases and protect them
        # from further processing via numbered placeholders.
        _quoted_parts: list = []

        def _preserve_quoted(m: re.Match) -> str:
            _quoted_parts.append(m.group(0))
            return f"\x00Q{len(_quoted_parts) - 1}\x00"

        sanitized = re.sub(r'"[^"]*"', _preserve_quoted, query)

        # Step 2: Strip remaining (unmatched) FTS5-special characters.  ``:`` is
        # FTS5's column-filter operator (``col:term``); since the FTS table has a
        # single ``content`` column, an unquoted colon query like ``TODO: fix``
        # parses as ``column:term`` and raises "no such column" — swallowed at
        # the execute site into zero results.  Strip it like the others.
        sanitized = re.sub(r'[+{}():\"^]', " ", sanitized)

        # Step 3: Collapse repeated * (e.g. "***") into a single one,
        # and remove leading * (prefix-only needs at least one char before *)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)

        # Step 4: Remove dangling boolean operators at start/end that would
        # cause syntax errors (e.g. "hello AND" or "OR world")
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())

        # Step 5: Wrap unquoted dotted and/or hyphenated terms in double
        # quotes.  FTS5's tokenizer splits on dots and hyphens, turning
        # ``chat-send`` into ``chat AND send`` and ``P2.2`` into ``p2 AND 2``.
        # Quoting preserves phrase semantics.  A single pass avoids the
        # double-quoting bug that would occur if dotted, hyphenated and underscored
        # patterns were applied sequentially (e.g. ``my-app.config``).
        sanitized = re.sub(r"\b(\w+(?:[._-]\w+)+)\b", r'"\1"', sanitized)

        # Step 6: Restore preserved quoted phrases
        for i, quoted in enumerate(_quoted_parts):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", quoted)

        return sanitized.strip()

    def _fts_table_exists(self, name: str) -> bool:
        """True if an FTS5 virtual table is queryable in this DB."""
        try:
            self._conn.execute(f"SELECT 1 FROM {name} LIMIT 0")
            return True
        except sqlite3.OperationalError:
            return False

    def optimize_fts(self) -> int:
        """Merge fragmented FTS5 b-tree segments into one per index.

        FTS5 indexes grow as a series of incremental segments — one per
        ``INSERT`` batch driven by the message triggers. Over tens of
        thousands of messages these segments accumulate, which both bloats
        the ``*_data`` shadow tables and slows ``MATCH`` queries that must
        scan every segment. The special ``'optimize'`` command rewrites each
        index as a single merged segment.

        This is purely a maintenance operation — it changes neither search
        results nor ``snippet()`` output, only on-disk layout and query
        speed. It is complementary to VACUUM: ``optimize`` compacts the FTS
        index internally, then VACUUM returns the freed pages to the OS.

        Skips any FTS table that does not exist (e.g. the trigram index when
        disabled via ``PROSTOR_DISABLE_FTS_TRIGRAM`` or not yet created), so
        it is safe to call unconditionally.

        Returns the number of FTS indexes that were optimized.
        """
        optimized = 0
        with self._lock:
            for tbl in self._FTS_TABLES:
                if not self._fts_table_exists(tbl):
                    continue
                try:
                    # The column name in the INSERT must match the table name
                    # for FTS5 special commands.
                    self._conn.execute(
                        f"INSERT INTO {tbl}({tbl}) VALUES('optimize')"
                    )
                    optimized += 1
                except sqlite3.OperationalError as exc:
                    logger.warning(
                        "FTS optimize failed for %s: %s", tbl, exc
                    )
        return optimized

