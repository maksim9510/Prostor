#!/usr/bin/env python3
"""
Adaptive Tool Router — автоматическое обнаружение паттернов последовательных
tool calls и предложение batch-альтернатив для экономии токенов.

Проблема: LLM часто делает 3-5 последовательных patch вызовов вместо одного
batch_patch. Каждый call = round-trip + tool schema overhead (~200-500 токенов).

Решение: отслеживание последовательных однотипных calls:
- 2+ patch подряд → warning: "use batch_patch instead (save ~N tokens)"
- 3+ read_file подряд → warning: "use batch_read instead"
- 2+ search_files подряд → suggestion: combine searches
- Автоматическое объединение при достижении threshold

Дополнительно:
- Pattern learning: запоминает какие паттерны агент использует чаще всего
- Session insights: "In this session, batch_patch would have saved 15K tokens"
- Auto-batch: при включённом режиме — автоматически объединяет 2+ calls
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds
PATCH_BATCH_THRESHOLD = 2     # 2+ patches → suggest batch_patch
READ_BATCH_THRESHOLD = 3      # 3+ reads → suggest batch_read
SEARCH_BATCH_THRESHOLD = 2    # 2+ searches → suggest combine
WINDOW_SIZE = 10              # Track last 10 tool calls

# Tool schema overhead estimate (tokens)
SCHEMA_OVERHEAD = {
    "patch": 350,
    "read_file": 300,
    "search_files": 250,
    "batch_patch": 400,
    "batch_read": 350,
}

# Batchable tool groups
BATCHABLE = {
    "patch": "batch_patch",
    "read_file": "batch_read",
    "search_files": None,  # no batch search yet, just suggest
}


@dataclass
class ToolCallRecord:
    tool_name: str
    timestamp: float
    args_summary: Dict[str, Any] = field(default_factory=dict)
    tokens_estimated: int = 0


class AdaptiveToolRouter:
    """Detect sequential tool call patterns and suggest batch alternatives."""

    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = window_size
        self._recent_calls: deque = deque(maxlen=window_size)
        self._lock = threading.Lock()
        self._suggestions_issued: int = 0
        self._tokens_saved_potential: int = 0
        self._auto_batch_enabled: bool = False
        self._pattern_counts: Dict[str, int] = defaultdict(int)
        self._session_start: float = time.time()

    def record_call(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        tokens: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Record a tool call and check for batchable patterns.

        Returns suggestion dict if a batch alternative is recommended,
        None otherwise.
        """
        args = args or {}
        args_summary = {}
        # Extract key args for pattern matching
        if "path" in args:
            args_summary["path"] = args["path"]
        if "pattern" in args:
            args_summary["pattern"] = args["pattern"][:50]

        record = ToolCallRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            args_summary=args_summary,
            tokens_estimated=tokens,
        )

        with self._lock:
            self._recent_calls.append(record)

        # Check for batchable patterns
        return self._check_pattern(tool_name)

    def _check_pattern(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Check if recent calls form a batchable pattern."""
        with self._lock:
            recent = list(self._recent_calls)

        # Count consecutive same-tool calls (from most recent backwards)
        consecutive = 0
        for call in reversed(recent):
            if call.tool_name == tool_name:
                consecutive += 1
            else:
                break

        if consecutive < 2:
            return None

        batch_tool = BATCHABLE.get(tool_name)
        if not batch_tool:
            return None

        # Check thresholds
        threshold = {
            "patch": PATCH_BATCH_THRESHOLD,
            "read_file": READ_BATCH_THRESHOLD,
            "search_files": SEARCH_BATCH_THRESHOLD,
        }.get(tool_name, 3)

        if consecutive < threshold:
            return None

        # Calculate potential savings
        schema_cost = SCHEMA_OVERHEAD.get(tool_name, 300)
        batch_schema_cost = SCHEMA_OVERHEAD.get(batch_tool, 400)
        # N individual calls vs 1 batch call
        savings = (consecutive * schema_cost) - batch_schema_cost

        # Get the actual calls that could be batched
        batchable_calls = list(recent[-consecutive:])

        self._suggestions_issued += 1
        self._tokens_saved_potential += savings
        self._pattern_counts[f"{tool_name}→{batch_tool}"] += 1

        suggestion = {
            "type": "batch_suggestion",
            "current_tool": tool_name,
            "batch_tool": batch_tool,
            "consecutive_calls": consecutive,
            "potential_savings_tokens": savings,
            "message": (
                f"💡 Detected {consecutive} consecutive '{tool_name}' calls. "
                f"Use '{batch_tool}' instead to save ~{savings} tokens "
                f"({consecutive} round-trips → 1)."
            ),
            "calls": [
                {
                    "tool": c.tool_name,
                    "args": c.args_summary,
                }
                for c in batchable_calls
            ],
        }

        logger.info(
            "Adaptive router: %d consecutive %s → suggest %s (save ~%d tokens)",
            consecutive, tool_name, batch_tool, savings,
        )

        return suggestion

    def get_pending_batch(
        self,
        tool_name: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get pending batchable operations for a tool.

        If auto_batch is enabled, collects all consecutive same-tool calls
        and returns them as a batch operations list.
        """
        if not self._auto_batch_enabled:
            return None

        with self._lock:
            recent = list(self._recent_calls)

        # Collect consecutive same-tool calls
        batch = []
        for call in reversed(recent):
            if call.tool_name == tool_name:
                batch.append(call.args_summary)
            else:
                break

        if len(batch) < 2:
            return None

        batch.reverse()
        return batch

    def get_insights(self) -> Dict[str, Any]:
        """Get session insights — patterns detected, potential savings."""
        with self._lock:
            recent = list(self._recent_calls)

        # Count tool usage
        tool_counts: Dict[str, int] = defaultdict(int)
        for call in recent:
            tool_counts[call.tool_name] += 1

        # Find missed batch opportunities
        missed = self._find_missed_batches(recent)

        # Calculate actual missed savings
        missed_savings = sum(m["savings"] for m in missed)

        return {
            "session_seconds": round(time.time() - self._session_start, 1),
            "total_calls": len(recent),
            "tool_counts": dict(tool_counts),
            "suggestions_issued": self._suggestions_issued,
            "potential_savings_tokens": self._tokens_saved_potential,
            "missed_batches": missed,
            "missed_savings_tokens": missed_savings,
            "auto_batch_enabled": self._auto_batch_enabled,
            "pattern_counts": dict(self._pattern_counts),
            "recommendations": self._generate_recommendations(tool_counts, missed),
        }

    def _find_missed_batches(self, calls: List[ToolCallRecord]) -> List[Dict[str, Any]]:
        """Find sequences where batch tools should have been used."""
        missed = []
        i = 0

        while i < len(calls):
            tool = calls[i].tool_name
            batch_tool = BATCHABLE.get(tool)

            if not batch_tool:
                i += 1
                continue

            # Count consecutive
            j = i
            while j < len(calls) and calls[j].tool_name == tool:
                j += 1

            count = j - i
            threshold = {
                "patch": PATCH_BATCH_THRESHOLD,
                "read_file": READ_BATCH_THRESHOLD,
            }.get(tool, 3)

            if count >= threshold:
                schema_cost = SCHEMA_OVERHEAD.get(tool, 300)
                batch_cost = SCHEMA_OVERHEAD.get(batch_tool, 400)
                savings = (count * schema_cost) - batch_cost

                missed.append({
                    "tool": tool,
                    "batch_tool": batch_tool,
                    "count": count,
                    "savings": savings,
                    "turns": f"{i + 1}-{j}",
                })

            i = j

        return missed

    def _generate_recommendations(
        self,
        tool_counts: Dict[str, int],
        missed: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate actionable recommendations."""
        recs = []

        if not missed:
            recs.append("✅ No missed batch opportunities — good token efficiency!")
            return recs

        for m in missed[:3]:
            recs.append(
                f"⚠️ {m['count']}x {m['tool']} (turns {m['turns']}) → "
                f"use {m['batch_tool']} to save ~{m['savings']} tokens"
            )

        total_missed = sum(m["savings"] for m in missed)
        if total_missed > 5000:
            recs.append(f"🔥 Total missed savings: {total_missed} tokens — consider using batch tools more")

        return recs

    def enable_auto_batch(self):
        """Enable auto-batch mode."""
        self._auto_batch_enabled = True
        logger.info("Adaptive router: auto-batch enabled")

    def disable_auto_batch(self):
        """Disable auto-batch mode."""
        self._auto_batch_enabled = False

    def reset(self):
        """Reset for new session."""
        with self._lock:
            self._recent_calls.clear()
            self._suggestions_issued = 0
            self._tokens_saved_potential = 0
            self._pattern_counts.clear()
            self._session_start = time.time()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_router: Optional[AdaptiveToolRouter] = None
_router_lock = threading.Lock()


def get_tool_router() -> AdaptiveToolRouter:
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = AdaptiveToolRouter()
    return _router


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

ADAPTIVE_ROUTER_SCHEMA = {
    "name": "adaptive_router",
    "description": (
        "Analyze tool call patterns and get recommendations for batch operations. "
        "Detects when consecutive patch/read calls could be combined into "
        "batch_patch/batch_read to save tokens.\n\n"
        "Actions:\n"
        "- 'insights': Get session insights and recommendations (default)\n"
        "- 'enable_auto': Enable auto-batch mode\n"
        "- 'disable_auto': Disable auto-batch mode\n"
        "- 'reset': Reset for new session"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["insights", "enable_auto", "disable_auto", "reset"],
                "description": "Action (default: insights)",
                "default": "insights",
            },
        },
        "required": [],
    },
}


def _handle_adaptive_router(args, **kw):
    router = get_tool_router()
    action = args.get("action", "insights")

    if action == "insights":
        insights = router.get_insights()
        return json.dumps(insights, ensure_ascii=False, indent=2)
    elif action == "enable_auto":
        router.enable_auto_batch()
        return json.dumps({"success": True, "auto_batch": True})
    elif action == "disable_auto":
        router.disable_auto_batch()
        return json.dumps({"success": True, "auto_batch": False})
    elif action == "reset":
        router.reset()
        return json.dumps({"success": True, "message": "Router reset"})
    return json.dumps({"error": f"Unknown action: {action}"})


def _check_router_reqs() -> bool:
    return True


try:
    from tools.registry import registry
    registry.register(
        name="adaptive_router",
        toolset="file",
        schema=ADAPTIVE_ROUTER_SCHEMA,
        handler=_handle_adaptive_router,
        check_fn=_check_router_reqs,
        emoji="🧭",
        max_result_size_chars=10_000,
    )
except Exception as e:
    logger.debug("Could not register adaptive_router: %s", e)


__all__ = ["AdaptiveToolRouter", "get_tool_router"]