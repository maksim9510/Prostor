"""Skin + light-mode helpers extracted from cli.py.

Pure functions + a small class (_SkinAwareAnsi) + a single module-level
side-effect (installing the light-mode remap hook on SkinConfig.get_color).

The side-effect is preserved (re-ran at import time) because it must be
in place before any other module reads skin colors. Tests that import
this module do not trigger visual changes — the hook is idempotent and
degrades gracefully if prostor_cli.skin_engine is unavailable.

What stays in cli.py:
  - _STREAM_PAD constant (tightly coupled to streaming layout)
  - _render_final_assistant_content (depends on Rich Markdown, not skin)
  - _rich_text_from_ansi aliasing this module's version
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any


# ---------------------------------------------------------------------------
# Hex / luminance primitives
# ---------------------------------------------------------------------------

def hex_to_ansi(hex_color: str, bold: bool = False) -> str:
    """Convert ``#RRGGBB`` (or ``#RGB``) to a truecolor SGR escape sequence.

    Returns the original input unchanged when it isn't a valid hex color
    (caller may pass an already-escaped ANSI sequence, a palette index, or
    a fallback string).
    """
    s = (hex_color or "").strip()
    if not s:
        return s
    if not s.startswith("#"):
        return s
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        return hex_color
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return hex_color
    open_attr = "\x1b[1;" if bold else "\x1b["
    return f"{open_attr}38;2;{r};{g};{b}m"


def luminance_from_hex(hex_str: str) -> float | None:
    """Rec.709 luma in [0, 1], or None if input isn't a valid hex color.

    >= 0.5 is conventionally treated as a "light" background. We use the
    ITU-R BT.709 coefficients (matches the W3C accessibility definition).
    """
    s = (hex_str or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        return None
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


# ---------------------------------------------------------------------------
# OSC 11 background query (best-effort, no-op on SSH / non-TTY)
# ---------------------------------------------------------------------------

def query_osc11_background() -> str | None:
    """Ask the terminal for its background color via OSC 11.

    Most modern terminals reply with \\x1b]11;rgb:RRRR/GGGG/BBBB\\x1b\\\\
    within a few ms.  We wait up to 100ms total before giving up.
    Returns "#RRGGBB" or None on timeout / non-tty.

    Skipped over SSH: the round-trip routinely exceeds our 100ms budget, so a
    late reply lands after prompt_toolkit has grabbed the tty — its payload
    leaks in as typed text and the BEL terminator reads as Ctrl+G (open
    editor), trapping the user in a stray editor. Remote sessions fall back to
    COLORFGBG / env hints / the dark default instead.
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    if any(os.environ.get(v) for v in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return None
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except Exception:
        return None
    try:
        try:
            tty.setcbreak(fd)
        except Exception:
            return None
        try:
            sys.stdout.write("\x1b]11;?\x1b\\")
            sys.stdout.flush()
        except Exception:
            return None
        import select
        deadline = time.monotonic() + 0.1
        buf = b""
        while time.monotonic() < deadline:
            r, _, _ = select.select([fd], [], [], deadline - time.monotonic())
            if not r:
                continue
            try:
                chunk = os.read(fd, 64)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if b"\x1b\\" in buf or b"\x07" in buf:
                break
        m = re.search(rb"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", buf)
        if not m:
            return None

        def _norm(h: bytes) -> int:
            v = int(h, 16)
            bits = len(h) * 4
            return (v * 255) // ((1 << bits) - 1) if bits else 0

        r, g, b = _norm(m.group(1)), _norm(m.group(2)), _norm(m.group(3))
        return f"#{r:02X}{g:02X}{b:02X}"
    finally:
        # TCSAFLUSH discards any unread input as it restores the original
        # attributes — scrubs a slow/partial OSC 11 reply out of the tty
        # buffer before prompt_toolkit can read it as keystrokes.
        try:
            import termios as _termios
            _termios.tcsetattr(fd, _termios.TCSAFLUSH, old)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Light-mode detection (cached per process)
# ---------------------------------------------------------------------------

_TRUE_RE = re.compile(r"^(1|true|on|yes|y)$")
_FALSE_RE = re.compile(r"^(0|false|off|no|n)$")
_LIGHT_DEFAULT_TERM_PROGRAMS: frozenset[str] = frozenset()  # Apple_Terminal doesn't reliably indicate; require explicit

# Cached after first call so we don't query the terminal repeatedly.
_LIGHT_MODE_CACHE: bool | None = None


def detect_light_mode() -> bool:
    """Decide whether to apply the light-mode color remap.

    Resolution order (first hit wins):
      1. ``PROSTOR_LIGHT`` / ``PROSTOR_TUI_LIGHT`` env var (true/false)
      2. ``PROSTOR_TUI_THEME`` (light/dark)
      3. ``PROSTOR_TUI_BACKGROUND`` hex (luminance >= 0.5 → light)
      4. ``COLORFGBG`` xterm hint (bg=7 or 15 → light)
      5. OSC 11 query (interactive TTY only, skipped over SSH)
      6. ``TERM_PROGRAM`` allow-list (currently empty)
    """
    global _LIGHT_MODE_CACHE
    if _LIGHT_MODE_CACHE is not None:
        return _LIGHT_MODE_CACHE
    result = False
    try:
        # 1. Explicit env override
        for var in ("PROSTOR_LIGHT", "PROSTOR_TUI_LIGHT"):
            v = (os.environ.get(var) or "").strip().lower()
            if _TRUE_RE.match(v):
                result = True
                _LIGHT_MODE_CACHE = result
                return result
            if _FALSE_RE.match(v):
                _LIGHT_MODE_CACHE = result
                return result
        # 2. Theme hint
        theme = (os.environ.get("PROSTOR_TUI_THEME") or "").strip().lower()
        if theme == "light":
            result = True
            _LIGHT_MODE_CACHE = result
            return result
        if theme == "dark":
            _LIGHT_MODE_CACHE = result
            return result
        # 3. Explicit bg hex
        bg_hint = os.environ.get("PROSTOR_TUI_BACKGROUND") or ""
        bg_lum = luminance_from_hex(bg_hint)
        if bg_lum is not None:
            result = bg_lum >= 0.5
            _LIGHT_MODE_CACHE = result
            return result
        # 4. COLORFGBG (xterm/Konsole/urxvt)
        cfgbg = (os.environ.get("COLORFGBG") or "").strip()
        if cfgbg:
            last = cfgbg.split(";")[-1] if ";" in cfgbg else cfgbg
            if last.isdigit():
                bg = int(last)
                if bg in {7, 15}:
                    result = True
                    _LIGHT_MODE_CACHE = result
                    return result
                if 0 <= bg < 16:
                    _LIGHT_MODE_CACHE = result
                    return result
        # 5. OSC 11 query (best-effort, only when stdin/stdout are TTY)
        bg_color = query_osc11_background()
        if bg_color:
            lum = luminance_from_hex(bg_color)
            if lum is not None:
                result = lum >= 0.5
                _LIGHT_MODE_CACHE = result
                return result
        # 6. TERM_PROGRAM allow-list (currently empty)
        tp = (os.environ.get("TERM_PROGRAM") or "").strip()
        if tp in _LIGHT_DEFAULT_TERM_PROGRAMS:
            result = True
    except Exception:
        result = False
    _LIGHT_MODE_CACHE = result
    return result


def reset_light_mode_cache() -> None:
    """Clear the cached light-mode decision. Test helper only."""
    global _LIGHT_MODE_CACHE
    _LIGHT_MODE_CACHE = None


# ---------------------------------------------------------------------------
# Light-mode remap table
# ---------------------------------------------------------------------------

# Light-mode equivalents of skin colors that are unreadable on cream
# Terminal.app backgrounds.  Used by _SkinAwareAnsi to remap colors
# at resolution time when light mode is detected.
#
# IMPORTANT: only remap colors that are used as STANDALONE foregrounds
# on the terminal's background.  Don't remap colors that are paired
# with a dark bg (e.g. status bar text on bg:#1a1a2e) — those would
# become invisible the OTHER direction (dark gray on dark navy).
_LIGHT_MODE_REMAP: dict[str, str] = {
    # Original (dark-mode) -> Light-mode replacement (darker, readable)
    "#FFF8DC": "#1A1A1A",   # cornsilk -> near-black
    "#FFD700": "#9A6B00",   # gold -> dark goldenrod (readable on cream)
    "#FFBF00": "#8A5A00",   # amber -> dark amber
    "#B8860B": "#5C4500",   # dark goldenrod -> deeper brown (more contrast)
    "#DAA520": "#6B4F00",   # goldenrod -> dark olive
    "#F1E6CF": "#1A1A1A",   # cream -> near-black
    "#c9d1d9": "#24292F",   # github-light fg
    "#EAF7FF": "#0F1B26",   # ice
    "#F5F5F5": "#1A1A1A",
    "#FFF0D4": "#1A1A1A",
    "#CD7F32": "#8A4F1A",   # bronze -> darker bronze
    "#FFEFB5": "#3A2A00",
    # NOTE: skipping #C0C0C0/#888888/#555555/#8B8682 — those are
    # status-bar foregrounds paired with dark navy bg, where dark
    # remap values would become invisible.
}

# Pre-uppercased lookup table for case-insensitive remapping
_LIGHT_MODE_REMAP_UPPER: dict[str, str] = {k.upper(): v for k, v in _LIGHT_MODE_REMAP.items()}


def maybe_remap_for_light_mode(hex_color: str) -> str:
    """If we're in light mode, remap a dark-mode-tuned color to a
    higher-contrast equivalent.  No-op in dark mode."""
    if not detect_light_mode():
        return hex_color
    if not hex_color or not hex_color.startswith("#"):
        return hex_color
    upper = hex_color.upper()
    if upper in _LIGHT_MODE_REMAP_UPPER:
        return _LIGHT_MODE_REMAP_UPPER[upper]
    return hex_color


# ---------------------------------------------------------------------------
# Skin engine integration — install light-mode remap hook on SkinConfig
# ---------------------------------------------------------------------------

def install_skin_light_mode_hook() -> bool:
    """Wrap SkinConfig.get_color so EVERY skin color read goes through the
    light-mode remap.  Idempotent.

    Returns True on success, False if the skin engine isn't importable
    (e.g. running under minimal test config).
    """
    try:
        from prostor_cli.skin_engine import SkinConfig  # type: ignore[import]
    except Exception:
        return False
    if getattr(SkinConfig, "_prostor_light_mode_hook_installed", False):
        return True
    _orig_get_color = SkinConfig.get_color

    def _wrapped_get_color(self: Any, key: str, fallback: str = "") -> str:
        value = _orig_get_color(self, key, fallback)
        try:
            return maybe_remap_for_light_mode(value)
        except Exception:
            return value

    SkinConfig.get_color = _wrapped_get_color  # type: ignore[method-assign]
    SkinConfig._prostor_light_mode_hook_installed = True  # type: ignore[attr-defined]
    return True


# Install the hook at import time (idempotent).
install_skin_light_mode_hook()


# Prime the light-mode detection cache early (at module load) when
# we're running interactively so OSC 11 happens before pt grabs the
# tty.  Skip for non-tty contexts (subagents, gateway, tests).
try:
    if sys.stdin.isatty() and sys.stdout.isatty():
        detect_light_mode()
except Exception:
    pass


# ---------------------------------------------------------------------------
# _SkinAwareAnsi — lazy ANSI escape that resolves from the skin engine
# ---------------------------------------------------------------------------

class SkinAwareAnsi:
    """Lazy ANSI escape that resolves from the skin engine on first use.

    Acts as a string in f-strings and concatenation.  Call ``.reset()`` to
    force re-resolution after a ``/skin`` switch.
    """

    def __init__(self, skin_key: str, fallback_hex: str = "#FFD700", *, bold: bool = False):
        self._skin_key = skin_key
        self._fallback_hex = fallback_hex
        self._bold = bold
        self._cached: str | None = None

    def __str__(self) -> str:
        if self._cached is None:
            try:
                from prostor_cli.skin_engine import get_active_skin
                self._cached = hex_to_ansi(
                    get_active_skin().get_color(self._skin_key, self._fallback_hex),
                    bold=self._bold,
                )
            except Exception:
                self._cached = hex_to_ansi(self._fallback_hex, bold=self._bold)
        return self._cached

    def __add__(self, other: str) -> str:
        return str(self) + other

    def __radd__(self, other: str) -> str:
        return other + str(self)

    def reset(self) -> None:
        """Clear cache so the next access re-reads the skin."""
        self._cached = None


# ---------------------------------------------------------------------------
# Bold / dim text helpers (TTY-aware)
# ---------------------------------------------------------------------------

def b(s: str) -> str:
    """Bold if stdout is a real TTY; plain text otherwise (slash-worker safe)."""
    try:
        return f"\x1b[1m{s}\x1b[0m" if sys.stdout.isatty() else str(s)
    except Exception:
        return str(s)


def d(s: str) -> str:
    """Dim-italic if stdout is a real TTY; plain text otherwise."""
    try:
        return f"\x1b[2;3m{s}\x1b[0m" if sys.stdout.isatty() else str(s)
    except Exception:
        return str(s)


def accent_hex() -> str:
    """Return the active skin accent color for legacy CLI output lines."""
    try:
        from prostor_cli.skin_engine import get_active_skin
        return get_active_skin().get_color("ui_accent", "#FFBF00")
    except Exception:
        return "#FFBF00"


# Pre-built global accent for legacy use (matches the dark-mode default)
ACCENT = SkinAwareAnsi("response_border", "#FFD700", bold=True)
# Use ANSI dim+italic attributes (\x1b[2;3m) instead of a hardcoded
# hex color so dim/thinking text inherits the terminal's default
# foreground color and stays readable in both light and dark
# Terminal.app modes.  Hardcoded skin colors like #B8860B
# (dark goldenrod) become invisible against light cream backgrounds.
DIM = "\x1b[2;3m"


__all__ = [
    "hex_to_ansi",
    "luminance_from_hex",
    "query_osc11_background",
    "detect_light_mode",
    "reset_light_mode_cache",
    "maybe_remap_for_light_mode",
    "install_skin_light_mode_hook",
    "SkinAwareAnsi",
    "b",
    "d",
    "accent_hex",
    "ACCENT",
    "DIM",
]
