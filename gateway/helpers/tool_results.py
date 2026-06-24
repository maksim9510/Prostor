"""Tool result processing, interrupted tool detection, auto-continue.
Extracted from gateway/run.py (#23).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _is_interrupted_tool_result(content: Any) -> bool:
    """Return True if a tool result indicates the tool was interrupted."""
    if not isinstance(content, str):
        return False
    lowered = content.lower()
    if "[command interrupted]" in lowered:
        return True
    if "exit_code" in lowered and ("130" in lowered or "-1" in lowered):
        return "interrupt" in lowered
    return False


def _strip_interrupted_tool_tails(
    agent_history: List[dict[str, Any]],
) -> List[dict[str, Any]]:
    """Strip interrupted assistant→tool sequences from replay history.

    Older interrupted gateway turns can be followed by a queued real user
    message, so the interrupted assistant/tool block is not necessarily the
    final tail by the time we rebuild replay history.  Remove any contiguous
    assistant(tool_calls) + tool-result block that contains an interrupted tool
    result, while preserving successful tool-call sequences intact.
    """
    if not agent_history:
        return agent_history

    cleaned: List[dict[str, Any]] = []
    i = 0
    n = len(agent_history)
    while i < n:
        msg = agent_history[i]
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            j = i + 1
            tool_results: List[dict[str, Any]] = []
            while j < n and agent_history[j].get("role") == "tool":
                tool_results.append(agent_history[j])
                j += 1
            if tool_results and any(
                _is_interrupted_tool_result(m.get("content", ""))
                for m in tool_results
            ):
                logger.debug(
                    "Stripping interrupted assistant→tool replay block "
                    "(indices %d–%d, tool_results=%d)",
                    i, j - 1, len(tool_results),
                )
                i = j
                continue
        if msg.get("role") == "tool" and _is_interrupted_tool_result(msg.get("content", "")):
            logger.debug("Stripping orphan interrupted tool result from replay history")
            i += 1
            continue
        cleaned.append(msg)
        i += 1

    return cleaned


def _strip_dangling_tool_call_tail(
    agent_history: List[dict[str, Any]],
) -> List[dict[str, Any]]:
    """Strip a trailing ``assistant(tool_calls)`` block left with NO answers.

    When a tool call itself kills the gateway process (``docker restart``,
    ``systemctl restart``, ``kill``, ``prostor gateway restart``), the process
    is terminated by SIGKILL *mid-call* — before the tool result is ever
    written and before the orderly shutdown rewind
    (``_drop_trailing_empty_response_scaffolding``) can run.  The last thing
    persisted is the ``assistant`` message that issued the ``tool_calls``,
    with zero matching ``tool`` rows.

    On resume the model sees an unanswered tool call at the tail and naturally
    re-issues it — which restarts the gateway again, producing the infinite
    reboot loop in #49201.  ``_strip_interrupted_tool_tails`` does not catch
    this because there is no tool result to inspect for an interrupt marker.

    This strips that dangling tail at the source so there is nothing for the
    model to re-execute.  It only acts when the tail is an
    ``assistant(tool_calls)`` whose calls have NO corresponding ``tool``
    results — a completed assistant→tool pair (any tool answers present) is
    left untouched so genuine mid-progress tool loops still resume.
    """
    if not agent_history:
        return agent_history

    last = agent_history[-1]
    if not (
        isinstance(last, dict)
        and last.get("role") == "assistant"
        and last.get("tool_calls")
    ):
        return agent_history

    logger.debug(
        "Stripping dangling unanswered assistant(tool_calls) tail "
        "(%d call(s)) — process likely killed mid-tool-call by a "
        "restart/shutdown command (#49201)",
        len(last.get("tool_calls") or []),
    )
    return agent_history[:-1]


_AUTO_CONTINUE_NOTE_PREFIX = "[System note: Your previous turn"
_AUTO_CONTINUE_FALLBACK_PREFIX = "[System note: A new message"


def _is_auto_continue_noise(content: Any) -> bool:
    """Return True if this user-message content is a gateway-injected
    auto-continue note that should NOT be replayed as a real user turn."""
    if not isinstance(content, str):
        return False
    return (
        content.startswith(_AUTO_CONTINUE_NOTE_PREFIX)
        or content.startswith(_AUTO_CONTINUE_FALLBACK_PREFIX)
    )


def _strip_auto_continue_noise(content: Any) -> Any:
    """Remove persisted gateway auto-continue note prefix from user text.

    Older gateway builds prepended the recovery note directly to the user
    message, so the transcript row can contain both the synthetic note and
    the user's real question.  Strip one or more leading synthetic notes while
    preserving any real text that follows.
    """
    if not _is_auto_continue_noise(content):
        return content
    text = str(content)
    while _is_auto_continue_noise(text):
        end = text.find("]")
        if end < 0:
            return ""
        text = text[end + 1 :].lstrip()
    return text
