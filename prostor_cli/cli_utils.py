"""Pure utility functions extracted from cli.py.

These are stateless helpers with no module-level side effects.
Safe to import from any context without triggering config load,
logging setup, or other cli.py initialization.

The lazy-import wrappers (CanonicalUsage, estimate_usage_cost,
is_table_divider, etc.) stay in cli.py because they re-export
agent-internal helpers and benefit from the same import-order
guarantees as the rest of the CLI surface.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Number / duration / token formatting (used by status bar + display layer)
# ---------------------------------------------------------------------------

def format_duration_compact(seconds: float) -> str:
    """Format a duration in seconds as a compact human-readable string.

    Examples:
        42       -> "42s"
        125      -> "2m"
        3725     -> "1h 2m"
        125000   -> "1.4d"
    """
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"


def format_token_count_compact(value: int) -> str:
    """Format a token count as a compact human-readable string.

    Examples:
        850      -> "850"
        12500    -> "12.5K"
        1_500_000 -> "1.5M"
    """
    value = int(value)
    abs_value = abs(value)
    if abs_value < 1_000:
        return str(value)

    sign = "-" if value < 0 else ""
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))
    for threshold, suffix in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            if scaled < 10:
                text = f"{scaled:.2f}"
            elif scaled < 100:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.0f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"

    return f"{value:,}"


# ---------------------------------------------------------------------------
# Reasoning-tag / tool-call-XML stripping (display-layer cleanup)
# ---------------------------------------------------------------------------

_REASONING_TAGS = (
    "REASONING_SCRATCHPAD",
    "think",
    "thinking",
    "reasoning",
    "thought",
)


def strip_reasoning_tags(text: str) -> str:
    """Remove reasoning/thinking blocks from displayed text.

    Handles every case:
      * Closed pairs ``<tag>…</tag>`` (case-insensitive, multi-line).
      * Unterminated open tags that run to end-of-text (e.g. truncated
        generations on NIM/MiniMax where the close tag is dropped).
      * Stray orphan close tags (``stuff</think>answer``) left behind by
        partial-content dumps.

    Covers the variants emitted by reasoning models today: ``<think>``,
    ``<thinking>``, ``<reasoning>``, ``<REASONING_SCRATCHPAD>``, and
    ``<thought>`` (Gemma 4).  Must stay in sync with
    ``run_agent.py::_strip_think_blocks`` and the stream consumer's
    ``_OPEN_THINK_TAGS`` / ``_CLOSE_THINK_TAGS`` tuples.

    Also strips tool-call XML blocks some open models leak into visible
    content (``<tool_call>``, ``<function_calls>``, Gemma-style
    ``<function name="…">…</function>``). Ported from
    openclaw/openclaw#67318.
    """
    cleaned = text
    for tag in _REASONING_TAGS:
        # Closed pair — case-insensitive so <THINK>…</THINK> is handled too.
        cleaned = re.sub(
            rf"<{tag}>.*?</{tag}>\s*",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Unterminated open tag — strip from the tag to end of text.
        cleaned = re.sub(
            rf"<{tag}>.*$",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Stray orphan close tag left behind by partial dumps.
        cleaned = re.sub(
            rf"</{tag}>\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
    # Tool-call XML blocks (openclaw/openclaw#67318).
    for tc_tag in ("tool_call", "tool_calls", "tool_result",
                   "function_call", "function_calls"):
        cleaned = re.sub(
            rf"<{tc_tag}\b[^>]*>.*?</{tc_tag}>\s*",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # <function name="..."> — boundary + attribute gated to avoid prose FPs.
    cleaned = re.sub(
        r'(?:(?<=^)|(?<=[\n\r.!?:]))[ \t]*'
        r'<function\b[^>]*\bname\s*=[^>]*>'
        r'(?:(?:(?!</function>).)*)</function>\s*',
        '',
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Stray tool-call close tags.
    cleaned = re.sub(
        r'</(?:tool_call|tool_calls|tool_result|function_call|function_calls|function)>\s*',
        '',
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def assistant_content_as_text(content: Any) -> str:
    """Flatten assistant message content (str | list[dict] | None) to text.

    For list content (the OpenAI/Anthropic structured content shape), only
    text-type parts are kept; non-text parts (tool_use, images, etc.) are
    silently dropped — this is the *display* path, not the model path.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return str(content)


def assistant_copy_text(content: Any) -> str:
    """User-facing copy text: flattened + reasoning stripped.

    This is what gets written to the clipboard when the user copies an
    assistant message. It must NEVER leak ``<think>…</think>`` or
    leaked ``<tool_call>…</tool_call>`` XML.
    """
    return strip_reasoning_tags(assistant_content_as_text(content))


__all__ = [
    "format_duration_compact",
    "format_token_count_compact",
    "strip_reasoning_tags",
    "assistant_content_as_text",
    "assistant_copy_text",
]
