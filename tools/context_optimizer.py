#!/usr/bin/env python3
"""
Context Window Optimizer — интеллектуальное управление контекстом разговора.

Проблема: каждый tool result остаётся в истории контекста навсегда.
После 20 tool calls контекст раздувается до 50K+ токенов, большинство из которых — 
устаревшие read_file результаты, которые больше не нужны.

Решение: прогрессивное сжатие старых tool results:
- Fresh (0-5 turns ago): полный текст, без изменений
- Warm (5-15 turns ago): compression (dedup, whitespace, hex noise)
- Cold (15-30 turns ago): summary (head 10 + tail 10 lines)
- Frozen (30+ turns ago): 1-line placeholder ("[file.py: 500 lines, read 35 turns ago]")

Дополнительно:
- Reference tracking: если агент ссылается на файл снова → автоматически "размораживает"
- Priority weights: patch/write results важнее read results
- Configurable thresholds через config.yaml
"""

import json
import logging
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Turn thresholds
FRESH_TURNS = 5
WARM_TURNS = 15
COLD_TURNS = 30

# Priority: higher = more likely to keep full
TOOL_PRIORITY = {
    "patch": 10,
    "batch_patch": 10,
    "write_file": 9,
    "terminal": 7,
    "search_files": 5,
    "read_file": 3,
    "batch_read": 3,
    "token_budget": 1,
}


@dataclass
class ContextEntry:
    """One tool result in conversation history."""
    tool_name: str
    result_text: str
    turn: int
    timestamp: float
    file_path: Optional[str] = None
    original_tokens: int = 0
    current_tokens: int = 0
    state: str = "fresh"  # fresh, warm, cold, frozen
    referenced: int = 0  # how many times referenced after initial
    last_referenced_turn: int = 0


class ContextWindowOptimizer:
    """Manage and optimize tool results in conversation context."""

    def __init__(
        self,
        fresh_turns: int = FRESH_TURNS,
        warm_turns: int = WARM_TURNS,
        cold_turns: int = COLD_TURNS,
    ):
        self.fresh_turns = fresh_turns
        self.warm_turns = warm_turns
        self.cold_turns = cold_turns
        self._entries: OrderedDict[str, ContextEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._current_turn: int = 0
        self._total_saved_tokens: int = 0
        self._file_refs: Dict[str, str] = {}  # file_path → entry_id

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return max(1, len(text) // 4) if text else 0

    def _entry_id(self, tool_name: str, turn: int, file_path: str = "") -> str:
        return f"{tool_name}:{turn}:{file_path}"

    def add_result(
        self,
        tool_name: str,
        result_text: str,
        file_path: Optional[str] = None,
    ) -> str:
        """Register a new tool result. Returns entry_id."""
        self._current_turn += 1
        entry_id = self._entry_id(tool_name, self._current_turn, file_path or "")
        tokens = self._estimate_tokens(result_text)

        entry = ContextEntry(
            tool_name=tool_name,
            result_text=result_text,
            turn=self._current_turn,
            timestamp=time.time(),
            file_path=file_path,
            original_tokens=tokens,
            current_tokens=tokens,
            state="fresh",
            last_referenced_turn=self._current_turn,
        )

        with self._lock:
            self._entries[entry_id] = entry
            if file_path:
                self._file_refs[file_path] = entry_id

        return entry_id

    def reference_file(self, file_path: str) -> bool:
        """Mark a file as referenced again (unfreeze if frozen).

        Returns True if the entry was unfrozen.
        """
        with self._lock:
            entry_id = self._file_refs.get(file_path)
            if not entry_id:
                return False

            entry = self._entries.get(entry_id)
            if not entry:
                return False

            entry.referenced += 1
            entry.last_referenced_turn = self._current_turn

            # Unfreeze: restore to warm state
            if entry.state == "frozen":
                entry.state = "warm"
                # We can't restore original text if it was replaced by placeholder
                # But we mark it for re-read if needed
                logger.debug("Unfroze %s (referenced again)", file_path)
                return True

        return False

    def optimize(self, current_turn: Optional[int] = None) -> Dict[str, Any]:
        """Run optimization pass on all entries.

        Progressively compresses/summarizes/freeszes entries based on age.
        Returns stats dict.
        """
        if current_turn is not None:
            self._current_turn = current_turn

        stats = {
            "total_entries": 0,
            "fresh": 0,
            "warm": 0,
            "cold": 0,
            "frozen": 0,
            "saved_tokens": 0,
        }

        with self._lock:
            for entry_id, entry in self._entries.items():
                age = self._current_turn - entry.turn
                priority = TOOL_PRIORITY.get(entry.tool_name, 5)

                # Adjust thresholds by priority
                # High-priority tools (patch, write) stay fresh longer
                fresh_limit = self.fresh_turns + (priority // 3)
                warm_limit = self.warm_turns + (priority // 2)
                cold_limit = self.cold_turns + priority

                # Also check reference recency
                ref_age = self._current_turn - entry.last_referenced_turn
                # Use the more recent of creation and last reference
                effective_age = min(age, ref_age)

                old_state = entry.state
                old_tokens = entry.current_tokens

                if effective_age <= fresh_limit:
                    entry.state = "fresh"
                    # No compression
                elif effective_age <= warm_limit:
                    if entry.state != "warm":
                        entry.state = "warm"
                        entry.result_text = self._compress(entry.result_text)
                elif effective_age <= cold_limit:
                    if entry.state != "cold":
                        entry.state = "cold"
                        entry.result_text = self._summarize(entry.result_text, entry.tool_name)
                else:
                    if entry.state != "frozen":
                        entry.state = "frozen"
                        entry.result_text = self._freeze(entry)

                entry.current_tokens = self._estimate_tokens(entry.result_text)
                saved = old_tokens - entry.current_tokens
                if saved > 0:
                    self._total_saved_tokens += saved
                    stats["saved_tokens"] += saved

                stats[entry.state] = stats.get(entry.state, 0) + 1
                stats["total_entries"] += 1

        stats["total_saved"] = self._total_saved_tokens
        return stats

    def _compress(self, text: str) -> str:
        """Apply compression to warm entries."""
        try:
            from tools.result_compression import compress_result
            compressed, _ = compress_result(text, "context_optimizer", max_chars=20000)
            return compressed
        except ImportError:
            # Fallback: simple whitespace compression
            import re
            text = re.sub(r'\n{4,}', '\n\n', text)
            return text

    def _summarize(self, text: str, tool_name: str) -> str:
        """Create summary for cold entries."""
        if len(text) < 1000:
            return text  # already small

        lines = text.split("\n")
        total = len(lines)

        if total <= 20:
            return text

        head = lines[:10]
        tail = lines[-10:]

        return (
            f"[SUMMARY: {tool_name}, {total} lines, was {len(text)} chars]\n"
            + "=== FIRST 10 LINES ===\n"
            + "\n".join(head)
            + f"\n... [{total - 20} lines omitted] ...\n"
            + "=== LAST 10 LINES ===\n"
            + "\n".join(tail)
            + "\n[/SUMMARY]"
        )

    def _freeze(self, entry: ContextEntry) -> str:
        """Create minimal placeholder for frozen entries."""
        if entry.file_path:
            return f"[{entry.tool_name}: {entry.file_path} — {entry.original_tokens} tokens, turn {entry.turn}]"
        else:
            return f"[{entry.tool_name}: {entry.original_tokens} tokens, turn {entry.turn}]"

    def get_context_text(self, entry_id: str) -> str:
        """Get the current (possibly compressed) text for an entry."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry:
                return entry.result_text
        return ""

    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics."""
        with self._lock:
            total_original = sum(e.original_tokens for e in self._entries.values())
            total_current = sum(e.current_tokens for e in self._entries.values())
            return {
                "entries": len(self._entries),
                "current_turn": self._current_turn,
                "total_original_tokens": total_original,
                "total_current_tokens": total_current,
                "total_saved_tokens": self._total_saved_tokens,
                "compression_pct": round(
                    (total_original - total_current) / total_original * 100, 1
                ) if total_original > 0 else 0,
                "states": {
                    "fresh": sum(1 for e in self._entries.values() if e.state == "fresh"),
                    "warm": sum(1 for e in self._entries.values() if e.state == "warm"),
                    "cold": sum(1 for e in self._entries.values() if e.state == "cold"),
                    "frozen": sum(1 for e in self._entries.values() if e.state == "frozen"),
                },
                "tracked_files": len(self._file_refs),
            }

    def get_stats_json(self) -> str:
        return json.dumps(self.get_stats(), ensure_ascii=False, indent=2)

    def reset(self):
        """Reset for new session."""
        with self._lock:
            self._entries.clear()
            self._file_refs.clear()
            self._current_turn = 0
            self._total_saved_tokens = 0


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_optimizer: Optional[ContextWindowOptimizer] = None
_opt_lock = threading.Lock()


def get_context_optimizer() -> ContextWindowOptimizer:
    global _optimizer
    if _optimizer is None:
        with _opt_lock:
            if _optimizer is None:
                _optimizer = ContextWindowOptimizer()
    return _optimizer


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

CONTEXT_OPTIMIZER_SCHEMA = {
    "name": "context_optimizer",
    "description": (
        "Manage conversation context efficiency. Shows which tool results "
        "are fresh/warm/cold/frozen and how many tokens are saved by "
        "progressive compression of older results.\n\n"
        "Actions:\n"
        "- 'stats': Get current context statistics (default)\n"
        "- 'optimize': Run optimization pass (compress old results)\n"
        "- 'reference': Mark a file as referenced (unfreeze if frozen)\n"
        "- 'reset': Reset for new session"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["stats", "optimize", "reference", "reset"],
                "description": "Action to perform (default: stats)",
                "default": "stats",
            },
            "file_path": {
                "type": "string",
                "description": "File path (for 'reference' action — mark file as recently used)",
            },
        },
        "required": [],
    },
}


def _handle_context_optimizer(args, **kw):
    opt = get_context_optimizer()
    action = args.get("action", "stats")

    if action == "stats":
        return opt.get_stats_json()
    elif action == "optimize":
        stats = opt.optimize()
        return json.dumps({"success": True, "optimization": stats}, ensure_ascii=False, indent=2)
    elif action == "reference":
        fp = args.get("file_path", "")
        if not fp:
            return json.dumps({"error": "file_path required for reference action"})
        unfroze = opt.reference_file(fp)
        return json.dumps({"success": True, "unfrozen": unfroze, "file": fp})
    elif action == "reset":
        opt.reset()
        return json.dumps({"success": True, "message": "Context optimizer reset"})
    return json.dumps({"error": f"Unknown action: {action}"})


def _check_optimizer_reqs() -> bool:
    return True


try:
    from tools.registry import registry
    registry.register(
        name="context_optimizer",
        toolset="file",
        schema=CONTEXT_OPTIMIZER_SCHEMA,
        handler=_handle_context_optimizer,
        check_fn=_check_optimizer_reqs,
        emoji="🧊",
        max_result_size_chars=10_000,
    )
except Exception as e:
    logger.debug("Could not register context_optimizer: %s", e)


__all__ = ["ContextWindowOptimizer", "get_context_optimizer"]