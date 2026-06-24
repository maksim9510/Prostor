#!/usr/bin/env python3
"""Streaming, reasoning preview, and message display methods for ``ProstorCLI``.

Extracted from ``cli.py`` as part of the god-file decomposition campaign.
This mixin holds the streaming cluster: reasoning preview, stream delta
processing, stream text emission, table alignment, and user message preview.

All methods expect ``self`` to be a ``ProstorCLI`` instance with the
attributes referenced (``_stream_buf``, ``show_reasoning``, etc.).
"""

from __future__ import annotations

import logging
import re
import shutil
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CLIStreamingMixin:
    """Streaming, reasoning preview, and message display methods."""

    # ------------------------------------------------------------------
    # Reasoning preview
    # ------------------------------------------------------------------

    def _emit_reasoning_preview(self, reasoning_text: str) -> None:
        """Render a buffered reasoning preview as a single [thinking] block."""
        preview_text = reasoning_text.strip()
        if not preview_text:
            return

        try:
            term_width = shutil.get_terminal_size().columns
        except Exception:
            term_width = 80
        prefix = "  [thinking] "
        wrap_width = max(30, term_width - len(prefix) - 2)

        paragraphs = []
        raw_paragraphs = re.split(r"\n\s*\n+", preview_text.replace("\r\n", "\n"))
        for paragraph in raw_paragraphs:
            compact = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
            if compact:
                paragraphs.append(textwrap.fill(compact, width=wrap_width))
        preview_text = "\n".join(paragraphs)
        if not preview_text:
            return

        from prostor_cli.cli import _cprint, _DIM, _RST
        if self.verbose:
            _cprint(f"  {_DIM}[thinking] {preview_text}{_RST}")
            return

        lines = preview_text.splitlines()
        if len(lines) > 5:
            preview = "\n".join(lines[:5])
            preview += f"\n  ... ({len(lines) - 5} more lines)"
        else:
            preview = preview_text
        _cprint(f"  {_DIM}[thinking] {preview}{_RST}")

    def _flush_reasoning_preview(self, *, force: bool = False) -> None:
        """Flush buffered reasoning text at natural boundaries."""
        buf = getattr(self, "_reasoning_preview_buf", "")
        if not buf:
            return

        try:
            term_width = shutil.get_terminal_size().columns
        except Exception:
            term_width = 80
        target_width = max(40, term_width - len("  [thinking] ") - 4)

        flush_text = ""

        if force:
            flush_text = buf
            buf = ""
        else:
            line_break = buf.rfind("\n")
            min_newline_flush = max(16, target_width // 3)
            if line_break != -1 and (
                line_break >= min_newline_flush
                or buf.endswith("\n\n")
                or buf.endswith(".\n")
                or buf.endswith("!\n")
                or buf.endswith("?\n")
                or buf.endswith(":\n")
            ):
                flush_text = buf[: line_break + 1]
                buf = buf[line_break + 1 :]
            elif len(buf) >= target_width:
                search_start = max(20, target_width // 2)
                search_end = min(len(buf), max(target_width + (target_width // 3), target_width + 8))
                cut = -1
                for boundary in (" ", "\t", ".", "!", "?", ",", ";", ":"):
                    cut = max(cut, buf.rfind(boundary, search_start, search_end))
                if cut != -1:
                    flush_text = buf[: cut + 1]
                    buf = buf[cut + 1 :]

        self._reasoning_preview_buf = buf.lstrip() if flush_text else buf
        if flush_text:
            self._emit_reasoning_preview(flush_text)

    # ------------------------------------------------------------------
    # User message preview
    # ------------------------------------------------------------------

    def _format_submitted_user_message_preview(self, user_input: str) -> str:
        """Format the submitted user-message scrollback preview."""
        try:
            from prostor_cli.cli import _accent_hex
            from rich.markup import escape as _escape
        except ImportError:
            _accent_hex = lambda: "#FFD700"
            _escape = lambda x: x

        ts_suffix = (
            f" [dim]{datetime.now().strftime('%H:%M')}[/]"
            if getattr(self, "show_timestamps", False) else ""
        )
        lines = user_input.split("\n")
        if len(lines) <= 1:
            return f"[bold {_accent_hex()}]●[/] [bold]{_escape(user_input)}[/]{ts_suffix}"

        first_lines = int(getattr(self, "user_message_preview_first_lines", 2))
        last_lines = int(getattr(self, "user_message_preview_last_lines", 2))
        first_lines = max(1, first_lines)
        last_lines = max(0, last_lines)
        head = lines[:first_lines]
        remaining_after_head = max(0, len(lines) - len(head))
        tail_count = min(last_lines, remaining_after_head)
        tail = lines[-tail_count:] if tail_count else []

        hidden_middle_count = len(lines) - len(head) - len(tail)
        if hidden_middle_count < 0:
            hidden_middle_count = 0
            tail = []

        preview_lines = [
            f"[bold {_accent_hex()}]●[/] [bold]{_escape(head[0])}[/]{ts_suffix}"
        ]
        preview_lines.extend(f"[bold]{_escape(line)}[/]" for line in head[1:])

        if hidden_middle_count > 0:
            noun = "line" if hidden_middle_count == 1 else "lines"
            preview_lines.append(f"[dim]... (+{hidden_middle_count} more {noun})[/]")

        preview_lines.extend(f"[bold]{_escape(line)}[/]" for line in tail)
        return "\n".join(preview_lines)

    def _expand_paste_references(self, text: str | None) -> str:
        """Expand [Pasted text #N -> file] placeholders into file contents."""
        if not isinstance(text, str) or "[Pasted text #" not in text:
            return text or ""
        paste_ref_re = re.compile(r'\[Pasted text #\d+: \d+ lines \u2192 (.+?)\]')

        def _expand_ref(match):
            path = Path(match.group(1))
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, IOError):
                logger.warning("Paste file gone or unreadable, returning placeholder: %s", path)
                return match.group(0)

        return paste_ref_re.sub(_expand_ref, text)

    def _print_user_message_preview(self, user_input: str) -> None:
        """Render a user message using the normal chat scrollback style."""
        try:
            from prostor_cli.cli import _accent_hex, ChatConsole
            from rich.markup import escape as _escape
        except ImportError:
            return

        ChatConsole().print(f"[{_accent_hex()}]{'─' * 40}[/]")
        text = str(user_input or "")
        if "\n" in text:
            ChatConsole().print(self._format_submitted_user_message_preview(text))
        else:
            ChatConsole().print(f"[bold {_accent_hex()}]●[/] [bold]{_escape(text)}[/]")

    # ------------------------------------------------------------------
    # Streaming delta processing
    # ------------------------------------------------------------------

    def _stream_reasoning_delta(self, text: str) -> None:
        """Stream reasoning/thinking tokens into a dim box above the response."""
        if not text:
            return
        self._reasoning_shown_this_turn = True
        if getattr(self, "_stream_box_opened", False):
            return

        if not getattr(self, "_reasoning_box_opened", False):
            self._reasoning_box_opened = True
            try:
                from prostor_cli.cli import _cprint, _DIM, _RST
            except ImportError:
                return
            w = self._scrollback_box_width()
            r_label = " Reasoning "
            r_fill = w - 2 - len(r_label)
            _cprint(f"\n{_DIM}┌─{r_label}{'─' * max(r_fill - 1, 0)}┐{_RST}")

        self._reasoning_buf = getattr(self, "_reasoning_buf", "") + text

        try:
            from prostor_cli.cli import _cprint, _DIM, _RST
        except ImportError:
            return
        while "\n" in self._reasoning_buf:
            line, self._reasoning_buf = self._reasoning_buf.split("\n", 1)
            _cprint(f"{_DIM}{line}{_RST}")
        if len(self._reasoning_buf) > 80:
            _cprint(f"{_DIM}{self._reasoning_buf}{_RST}")
            self._reasoning_buf = ""

    def _close_reasoning_box(self) -> None:
        """Close the live reasoning box if it's open."""
        if not getattr(self, "_reasoning_box_opened", False):
            return
        try:
            from prostor_cli.cli import _cprint, _DIM, _RST
        except ImportError:
            return

        buf = getattr(self, "_reasoning_buf", "")
        if buf:
            _cprint(f"{_DIM}{buf}{_RST}")
            self._reasoning_buf = ""
        w = self._scrollback_box_width()
        _cprint(f"{_DIM}└{'─' * (w - 2)}┘{_RST}")
        self._reasoning_box_opened = False

        deferred = getattr(self, "_deferred_content", "")
        if deferred:
            self._deferred_content = ""
            self._emit_stream_text(deferred)

    def _stream_delta(self, text) -> None:
        """Line-buffered streaming callback for real-time token rendering."""
        if text is None:
            self._flush_stream()
            self._reset_stream_state()
            return
        if not text:
            return

        self._stream_started = True

        _OPEN_TAGS = ("<REASONING_SCRATCHPAD>", "<think>", "<reasoning>", "<THINKING>", "<thinking>", "<thought>")
        _CLOSE_TAGS = ("</REASONING_SCRATCHPAD>", "</think>", "</reasoning>", "</THINKING>", "</thinking>", "</thought>")

        self._stream_prefilt = getattr(self, "_stream_prefilt", "") + text

        if not hasattr(self, "_stream_last_was_newline"):
            self._stream_last_was_newline = True

        if not getattr(self, "_in_reasoning_block", False):
            for tag in _OPEN_TAGS:
                search_start = 0
                while True:
                    idx = self._stream_prefilt.find(tag, search_start)
                    if idx == -1:
                        break
                    preceding = self._stream_prefilt[:idx]
                    if idx == 0:
                        is_block_boundary = getattr(self, "_stream_last_was_newline", True)
                    else:
                        last_nl = preceding.rfind("\n")
                        if last_nl == -1:
                            is_block_boundary = (
                                getattr(self, "_stream_last_was_newline", True)
                                and preceding.strip() == ""
                            )
                        else:
                            is_block_boundary = preceding[last_nl + 1:].strip() == ""
                    if is_block_boundary:
                        if preceding:
                            self._emit_stream_text(preceding)
                            self._stream_last_was_newline = preceding.endswith("\n")
                        self._in_reasoning_block = True
                        self._stream_prefilt = self._stream_prefilt[idx + len(tag):]
                        break
                    search_start = idx + 1
                if getattr(self, "_in_reasoning_block", False):
                    break

            if not getattr(self, "_in_reasoning_block", False):
                safe = self._stream_prefilt
                for tag in _OPEN_TAGS:
                    for i in range(1, len(tag)):
                        if self._stream_prefilt.endswith(tag[:i]):
                            safe = self._stream_prefilt[:-i]
                            break
                if safe:
                    self._emit_stream_text(safe)
                    self._stream_last_was_newline = safe.endswith("\n")
                    self._stream_prefilt = self._stream_prefilt[len(safe):]
                return

        if getattr(self, "_in_reasoning_block", False):
            for tag in _CLOSE_TAGS:
                idx = self._stream_prefilt.find(tag)
                if idx != -1:
                    self._in_reasoning_block = False
                    if self.show_reasoning:
                        inner = self._stream_prefilt[:idx]
                        if inner:
                            self._stream_reasoning_delta(inner)
                    after = self._stream_prefilt[idx + len(tag):]
                    self._stream_prefilt = ""
                    if after:
                        self._stream_delta(after)
                    return
            max_tag_len = max(len(t) for t in _CLOSE_TAGS)
            if len(self._stream_prefilt) > max_tag_len:
                if self.show_reasoning:
                    safe_reasoning = self._stream_prefilt[:-max_tag_len]
                    self._stream_reasoning_delta(safe_reasoning)
                self._stream_prefilt = self._stream_prefilt[-max_tag_len:]
            return

    def _emit_stream_text(self, text: str) -> None:
        """Emit filtered text to the streaming display."""
        if not text:
            return

        if self.show_reasoning and getattr(self, "_reasoning_box_opened", False):
            self._deferred_content = getattr(self, "_deferred_content", "") + text
            return

        self._close_reasoning_box()

        if not self._stream_box_opened:
            text = text.lstrip("\n")
            if not text:
                return
            self._stream_box_opened = True
            try:
                from prostor_cli.skin_engine import get_active_skin
                _skin = get_active_skin()
                label = _skin.get_branding("response_label", "⚕ Prostor")
                _text_hex = _skin.get_color("banner_text", "#FFF8DC")
            except Exception:
                label = "⚕ Prostor"
                _text_hex = "#FFF8DC"
            try:
                _r = int(_text_hex[1:3], 16)
                _g = int(_text_hex[3:5], 16)
                _b = int(_text_hex[5:7], 16)
                self._stream_text_ansi = f"\033[38;2;{_r};{_g};{_b}m"
            except (ValueError, IndexError):
                self._stream_text_ansi = ""
            if self.show_timestamps:
                label = f"{label} {datetime.now().strftime('%H:%M')}"
            try:
                from prostor_cli.cli import _cprint, _ACCENT, _RST, ProstorCLI
                w = self._scrollback_box_width()
                fill = w - 2 - ProstorCLI._status_bar_display_width(label)
                _cprint(f"\n{_ACCENT}╭─{label}{'─' * max(fill - 1, 0)}╮{_RST}")
            except ImportError:
                pass

        self._stream_buf += text

        _tc = getattr(self, "_stream_text_ansi", "")

        try:
            from prostor_cli.cli import _cprint, _STREAM_PAD, _RST, looks_like_table_row, is_table_divider, realign_markdown_tables, _terminal_width_for_streaming, _strip_markdown_syntax
        except ImportError:
            return

        def _emit_one(printed_line: str) -> None:
            _cprint(f"{_STREAM_PAD}{_tc}{printed_line}{_RST}" if _tc else f"{_STREAM_PAD}{printed_line}")

        def _flush_table_buf() -> None:
            buf = self._stream_table_buf
            self._stream_table_buf = []
            self._in_stream_table = False
            if not buf:
                return
            joined = "\n".join(buf)
            if self.final_response_markdown == "strip":
                joined = _strip_markdown_syntax(joined)
            block = realign_markdown_tables(joined, _terminal_width_for_streaming())
            for ln in block.split("\n"):
                _emit_one(ln)

        while "\n" in self._stream_buf:
            line, self._stream_buf = self._stream_buf.split("\n", 1)

            if self._in_stream_table:
                if looks_like_table_row(line) or is_table_divider(line):
                    self._stream_table_buf.append(line)
                    continue
                _flush_table_buf()
            elif looks_like_table_row(line):
                self._stream_table_buf.append(line)
                self._in_stream_table = True
                continue

            if self.final_response_markdown == "strip":
                line = _strip_markdown_syntax(line)
            _emit_one(line)

    def _flush_stream(self) -> None:
        """Emit any remaining partial line from the stream buffer and close the box."""
        if getattr(self, "_in_reasoning_block", False) and getattr(self, "_stream_prefilt", ""):
            self._in_reasoning_block = False
            self._emit_stream_text(self._stream_prefilt)
            self._stream_prefilt = ""

        self._close_reasoning_box()

        try:
            from prostor_cli.cli import _cprint, _STREAM_PAD, _RST, looks_like_table_row, is_table_divider, realign_markdown_tables, _terminal_width_for_streaming, _strip_markdown_syntax
        except ImportError:
            return

        _tc = getattr(self, "_stream_text_ansi", "")

        if (
            self._stream_buf
            and getattr(self, "_in_stream_table", False)
            and (looks_like_table_row(self._stream_buf) or is_table_divider(self._stream_buf))
        ):
            self._stream_table_buf.append(self._stream_buf)
            self._stream_buf = ""

        if getattr(self, "_in_stream_table", False):
            self._flush_stream_table()

        if self._stream_buf:
            if self.final_response_markdown == "strip":
                self._stream_buf = _strip_markdown_syntax(self._stream_buf)
            _cprint(f"{_STREAM_PAD}{_tc}{self._stream_buf}{_RST}" if _tc else f"{_STREAM_PAD}{self._stream_buf}")
            self._stream_buf = ""

        if self._stream_box_opened:
            try:
                w = self._scrollback_box_width()
                _cprint(f"{_ACCENT}╰{'─' * (w - 2)}╯{_RST}")
            except Exception:
                pass
            self._stream_box_opened = False

        self._stream_started = False
