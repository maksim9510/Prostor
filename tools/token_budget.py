#!/usr/bin/env python3
"""
Token Budget Manager — отслеживание и ограничение потребления токенов.

Возможности:
- Подсчёт токенов на каждый tool call
- Кумулятивный трекинг по сессии
- Предупреждения при 75%, 90%, 95% бюджета
- Auto-compression при 90% (агрессивнее)
- Auto-truncation при 95% (минимум)
- Per-tool статистика
- Session report
"""

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_CHARS_PER_TOKEN_CJK = 2

WARN_THRESHOLD = 0.75
COMPRESS_THRESHOLD = 0.90
TRUNCATE_THRESHOLD = 0.95


@dataclass
class ToolCallStats:
    calls: int = 0
    input_chars: int = 0
    output_chars: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_call: float = 0.0


class TokenBudgetManager:
    """Track and manage token consumption across a session."""

    def __init__(self, max_budget: int = 500_000):
        self.max_budget = max_budget
        self._used_tokens: int = 0
        self._tool_stats: dict[str, ToolCallStats] = defaultdict(ToolCallStats)
        self._lock = threading.Lock()
        self._warnings_issued: set = set()
        self._session_start: float = time.time()
        self._compression_enabled: bool = True
        self._history: list[dict[str, Any]] = []

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length."""
        if not text:
            return 0
        total_chars = len(text)
        cjk_count = 0
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or 0x3040 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF):
                cjk_count += 1
        if cjk_count > total_chars * 0.1:
            return cjk_count // _CHARS_PER_TOKEN_CJK + (total_chars - cjk_count) // _CHARS_PER_TOKEN
        return total_chars // _CHARS_PER_TOKEN

    def process_tool_result(
        self,
        result: str,
        tool_name: str = "",
        max_output_tokens: int = 12_000,
    ) -> str:
        """Process a tool result: track tokens, compress if needed."""
        if not result:
            return result

        result_tokens = self.estimate_tokens(result)
        budget_pct = self._used_tokens / self.max_budget if self.max_budget > 0 else 0

        compressed = result
        compression_applied = False

        if self._compression_enabled:
            try:
                from tools.result_compression import compress_json_result, compress_result

                if result_tokens > max_output_tokens:
                    max_chars = max_output_tokens * _CHARS_PER_TOKEN
                    if result.strip().startswith("{"):
                        compressed = compress_json_result(result, tool_name, max_chars)
                    else:
                        compressed, _ = compress_result(result, tool_name, max_chars)
                    compression_applied = True

                elif budget_pct > COMPRESS_THRESHOLD:
                    max_chars = min(len(result), max_output_tokens * _CHARS_PER_TOKEN // 2)
                    if result.strip().startswith("{"):
                        compressed = compress_json_result(result, tool_name, max_chars)
                    else:
                        compressed, _ = compress_result(result, tool_name, max_chars)
                    compression_applied = True

                elif budget_pct > TRUNCATE_THRESHOLD:
                    max_chars = max_output_tokens * _CHARS_PER_TOKEN // 4
                    compressed = result[:max_chars] + "\n... [BUDGET CRITICAL]"
                    compression_applied = True
            except ImportError:
                pass

        compressed_tokens = self.estimate_tokens(compressed)
        saved_tokens = result_tokens - compressed_tokens

        with self._lock:
            stats = self._tool_stats[tool_name]
            stats.calls += 1
            stats.input_chars += len(result)
            stats.output_chars += len(compressed)
            stats.input_tokens += result_tokens
            stats.output_tokens += compressed_tokens
            stats.last_call = time.time()
            self._used_tokens += compressed_tokens
            self._history.append({
                "tool": tool_name,
                "ts": time.time(),
                "input_tokens": result_tokens,
                "output_tokens": compressed_tokens,
                "saved": saved_tokens,
                "compressed": compression_applied,
            })

        self._check_warnings(budget_pct)
        return compressed

    def _check_warnings(self, budget_pct: float):
        pct_int = int(budget_pct * 100)
        if pct_int >= 75 and 75 not in self._warnings_issued:
            self._warnings_issued.add(75)
            logger.warning("Token budget at %d%% (%d/%d)", pct_int, self._used_tokens, self.max_budget)
        if pct_int >= 90 and 90 not in self._warnings_issued:
            self._warnings_issued.add(90)
            logger.warning("Token budget at %d%% — aggressive compression", pct_int)
        if pct_int >= 95 and 95 not in self._warnings_issued:
            self._warnings_issued.add(95)
            logger.warning("Token budget CRITICAL at %d%% — truncating", pct_int)

    def track_api_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read_tokens: int = 0,
    ):
        """Track real API-level token usage for budget warnings.

        Called from conversation_loop after each successful API response.
        Unlike process_tool_result (which tracks tool output tokens),
        this tracks what the model actually consumed — the accurate signal
        for budget exhaustion warnings.
        """
        if prompt_tokens <= 0 and completion_tokens <= 0:
            return

        with self._lock:
            # Use prompt_tokens as the primary budget signal — this is what
            # the model sees and what triggers context-length errors.
            self._used_tokens = prompt_tokens
            self._history.append({
                "tool": "__api__",
                "ts": time.time(),
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "saved": 0,
                "compressed": False,
                "cache_read_tokens": cache_read_tokens,
            })

        budget_pct = prompt_tokens / self.max_budget if self.max_budget > 0 else 0
        self._check_warnings(budget_pct)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_saved = sum(s.input_tokens - s.output_tokens for s in self._tool_stats.values())
            per_tool = []
            for name, s in sorted(self._tool_stats.items(), key=lambda x: x[1].input_tokens, reverse=True):
                per_tool.append({
                    "tool": name,
                    "calls": s.calls,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "saved_tokens": s.input_tokens - s.output_tokens,
                    "compression_pct": round((s.input_tokens - s.output_tokens) / s.input_tokens * 100) if s.input_tokens > 0 else 0,
                })
            return {
                "session_seconds": round(time.time() - self._session_start, 1),
                "max_budget": self.max_budget,
                "used_tokens": self._used_tokens,
                "remaining_tokens": max(0, self.max_budget - self._used_tokens),
                "budget_pct": round(self._used_tokens / self.max_budget * 100, 1) if self.max_budget > 0 else 0,
                "total_saved": total_saved,
                "compression_enabled": self._compression_enabled,
                "warnings_issued": sorted(self._warnings_issued),
                "per_tool": per_tool[:10],
                "total_calls": sum(s.calls for s in self._tool_stats.values()),
            }

    def get_stats_json(self) -> str:
        return json.dumps(self.get_stats(), ensure_ascii=False, indent=2)

    def reset(self):
        with self._lock:
            self._used_tokens = 0
            self._tool_stats.clear()
            self._warnings_issued.clear()
            self._session_start = time.time()
            self._history.clear()

    def set_budget(self, max_budget: int):
        with self._lock:
            self.max_budget = max_budget

    def set_compression(self, enabled: bool):
        self._compression_enabled = enabled


_token_tracker: TokenBudgetManager | None = None
_tracker_lock = threading.Lock()


def get_token_tracker() -> TokenBudgetManager:
    global _token_tracker
    if _token_tracker is None:
        with _tracker_lock:
            if _token_tracker is None:
                _token_tracker = TokenBudgetManager()
    return _token_tracker


TOKEN_BUDGET_SCHEMA = {
    "name": "token_budget",
    "description": (
        "Track and manage token consumption. Shows per-tool statistics, "
        "budget usage, and compression savings. Use this to monitor "
        "token efficiency and identify which tools consume the most."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["stats", "reset", "set_budget", "enable_compression", "disable_compression"],
                "description": "Action to perform (default: stats)",
                "default": "stats",
            },
            "max_tokens": {
                "type": "integer",
                "description": "New max token budget (for set_budget action)",
            },
        },
        "required": [],
    },
}


def _handle_token_budget(args, **kw):
    tracker = get_token_tracker()
    action = args.get("action", "stats")
    if action == "stats":
        return tracker.get_stats_json()
    elif action == "reset":
        tracker.reset()
        return json.dumps({"success": True, "message": "Token tracker reset"})
    elif action == "set_budget":
        max_tokens = args.get("max_tokens", 500000)
        tracker.set_budget(int(max_tokens))
        return json.dumps({"success": True, "max_budget": tracker.max_budget})
    elif action == "enable_compression":
        tracker.set_compression(True)
        return json.dumps({"success": True, "compression": True})
    elif action == "disable_compression":
        tracker.set_compression(False)
        return json.dumps({"success": True, "compression": False})
    return json.dumps({"error": f"Unknown action: {action}"})


def _check_token_budget_reqs() -> bool:
    return True


try:
    from tools.registry import registry
    registry.register(
        name="token_budget",
        toolset="file",
        schema=TOKEN_BUDGET_SCHEMA,
        handler=_handle_token_budget,
        check_fn=_check_token_budget_reqs,
        emoji="📊",
        max_result_size_chars=10_000,
    )
except Exception as e:
    logger.debug("Could not register token_budget: %s", e)


__all__ = ["TokenBudgetManager", "get_token_tracker"]
