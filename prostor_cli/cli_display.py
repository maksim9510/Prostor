#!/usr/bin/env python3
"""
CLI Display Utilities — rendering, markdown stripping, terminal helpers.

Extracted from cli.py to reduce god-file size. These functions handle:
- ANSI color conversion and light-mode remapping
- Markdown syntax stripping for plain-text display
- Terminal width detection for streaming
- Rich text rendering from ANSI escapes
- Windows path dot-segment preservation

All functions are stateless or use only stdlib — no CLI class dependencies.
"""

import re
import shutil
from typing import Any


# ANSI building blocks for conversation display
ACCENT_ANSI_DEFAULT = "\033[1;38;2;255;215;0m"  # True-color #FFD700 bold — fallback
BOLD = "\033[1m"
RST = "\033[0m"
STREAM_PAD = "    "  # 4-space indent for streamed response text (matches Panel padding)


def hex_to_ansi(hex_color: str, *, bold: bool = False) -> str:
    """Convert a hex color like '#268bd2' to a true-color ANSI escape.

    Auto-remaps known dark-mode-tuned colors to readable light-mode
    equivalents when running on a light terminal (see
    _maybe_remap_for_light_mode + _LIGHT_MODE_REMAP).
    """
    from prostor_cli.cli_skin import maybe_remap_for_light_mode as _remap
    hex_color = _remap(hex_color)
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        prefix = "1;" if bold else ""
        return f"\033[{prefix}38;2;{r};{g};{b}m"
    except (ValueError, IndexError):
        return ACCENT_ANSI_DEFAULT if bold else "\033[38;2;184;134;11m"


def rich_text_from_ansi(text: str) -> Any:
    """Safely render assistant/tool output that may contain ANSI escapes.

    Using Rich Text.from_ansi preserves literal bracketed text like
    ``[not markup]`` while still interpreting real ANSI color codes.
    """
    try:
        from rich.text import Text as _RichText
        return _RichText.from_ansi(text or "")
    except ImportError:
        return text or ""


def strip_markdown_syntax(text: str) -> str:
    """Best-effort markdown marker removal for plain-text display."""
    plain = rich_text_from_ansi(text or "")
    if hasattr(plain, "plain"):
        plain = plain.plain
    # Avoid stripping cron-style expressions like "* * * * *" as if they were
    # Markdown horizontal rules. CommonMark treats three or more "*" as an HR,
    # but in Prostor output it's common to display cron schedules verbatim.
    #
    # Keep the behavior for "-" / "_" HR markers, and only strip "*" HR lines
    # when there are exactly 3 asterisks (with optional whitespace).
    plain = re.sub(r"^\s{0,3}(?:[-_]\s*){3,}$", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s{0,3}(?:\*\s*){3}\s*$", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s{0,3}#{1,6}\s+", "", plain, flags=re.MULTILINE)
    # Preserve blockquotes, lists, and checkboxes because they carry structure.
    plain = re.sub(r"(```+|~~~+)", "", plain)
    plain = re.sub(r"`([^`]*)`", r"\1", plain)
    plain = re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", plain)
    plain = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)___([^_]+)___(?!\\w)", r"\1", plain)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)__([^_]+)__(?!\\w)", r"\1", plain)
    # Only strip `*emphasis*` markers when the inner text is non-whitespace.
    # This avoids corrupting cron expressions like "* * * * *".
    plain = re.sub(r"\*([^\s*][^*]*?[^\s*])\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)_([^_]+)_(?!\\w)", r"\1", plain)
    plain = re.sub(r"~~([^~]+)~~", r"\1", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip("\n")


_WINDOWS_PATH_WITH_DOT_SEGMENT_RE = re.compile(
    r"(?i)(?:\b[a-z]:\\|\\\\)[^\s`]*\\\.[^\s`]*"
)


def preserve_windows_dot_segments_for_markdown(text: str) -> str:
    r"""Keep Windows path separators before hidden directories in Markdown.

    CommonMark treats ``\.`` as an escaped literal dot, so Rich Markdown would
    render ``D:\repo\.ai`` as ``D:\repo.ai``.  Doubling only that separator
    inside Windows path-looking tokens preserves the path without changing
    ordinary markdown escapes like ``1\. not a list``.
    """
    if "\\." not in text:
        return text

    def _protect(match: re.Match[str]) -> str:
        return re.sub(r"(?<!\\)\\(?=\.)", r"\\\\", match.group(0))

    return _WINDOWS_PATH_WITH_DOT_SEGMENT_RE.sub(_protect, text)


def terminal_width_for_streaming() -> int:
    """Display cells available inside the streamed response box.

    The streaming path indents every line by ``STREAM_PAD`` (4 cells)
    inside an open response panel.  The realigner uses this number as
    its budget when deciding whether to keep a horizontal table or
    fall back to vertical key-value rendering.  We subtract a small
    safety margin so terminal-resize races don't push a borderline
    table into mid-cell soft-wrap.
    """
    try:
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    return max(20, cols - len(STREAM_PAD) - 2)


# Backward-compat aliases for existing call sites in cli.py
_HEX_TO_ANSI = hex_to_ansi
_RICH_TEXT_FROM_ANSI = rich_text_from_ansi
_STRIP_MARKDOWN_SYNTAX = strip_markdown_syntax
_TERMINAL_WIDTH_FOR_STREAMING = terminal_width_for_streaming
