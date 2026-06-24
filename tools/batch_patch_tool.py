#!/usr/bin/env python3
"""
Batch Patch Tool — множественная правка файлов за один вызов LLM.

Ключевые преимущества:
- 1 round-trip к LLM вместо N (экономия ~60-70% токенов на tool schema)
- Hardware-aware ThreadPoolExecutor: автоматически определяет количество потоков
- HashLine работает в каждом потоке (index cache per-file, mtime-based)
- Token-efficient output: только diff summary, не полные файлы

Hardware detection:
- psutil: physical cores - 1, available RAM / 1GB per thread
- fallback: os.cpu_count() - 1
- hard cap: min(workers, len(operations))
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------

_HW_CACHE: dict[str, int] | None = None
_HW_CACHE_LOCK = threading.Lock()
_HW_CACHE_TS: float = 0.0
_HW_CACHE_TTL: float = 5.0  # cache for 5 seconds


def _detect_hardware() -> dict[str, int]:
    """Detect available parallelism capacity.

    Returns dict with:
        cpu_cores: physical CPU cores
        logical_cores: logical CPU cores (hyperthreading)
        available_gb: available RAM in GB
        max_workers: recommended max parallel workers
    """
    global _HW_CACHE, _HW_CACHE_TS

    now = time.monotonic()
    with _HW_CACHE_LOCK:
        if _HW_CACHE is not None and (now - _HW_CACHE_TS) < _HW_CACHE_TTL:
            return _HW_CACHE

    result: dict[str, int] = {}

    try:
        import psutil
        result["cpu_cores"] = psutil.cpu_count(logical=False) or 1
        result["logical_cores"] = psutil.cpu_count(logical=True) or 1
        result["available_gb"] = max(1, int(psutil.virtual_memory().available / (1024**3)))
        # Heuristic: 1 worker per physical core, but leave 1 for system
        max_by_cpu = max(1, result["cpu_cores"] - 1) if result["cpu_cores"] > 1 else 1
        # Memory: ~512MB per hashline worker (index + file content)
        max_by_mem = max(1, result["available_gb"] * 2)
        result["max_workers"] = min(max_by_cpu, max_by_mem)
    except ImportError:
        # psutil not available — conservative fallback
        logical = os.cpu_count() or 1
        result["cpu_cores"] = logical
        result["logical_cores"] = logical
        result["available_gb"] = 4  # assume 4GB
        max_by_cpu = max(1, logical - 1) if logical > 1 else 1
        result["max_workers"] = max_by_cpu
    except Exception as e:
        logger.debug("Hardware detection failed: %s", e)
        logical = os.cpu_count() or 1
        result["cpu_cores"] = logical
        result["logical_cores"] = logical
        result["available_gb"] = 4
        result["max_workers"] = max(1, logical - 1) if logical > 1 else 1

    with _HW_CACHE_LOCK:
        _HW_CACHE = result
        _HW_CACHE_TS = now

    return result


def _compute_workers(num_operations: int) -> tuple[int, dict[str, int]]:
    """Compute optimal worker count for given number of operations.

    Returns (workers, hw_info).
    """
    hw = _detect_hardware()
    max_hw = hw["max_workers"]
    # Don't spawn more workers than operations
    workers = min(max_hw, max(1, num_operations))
    # If only 1 operation, no need for threads
    if num_operations <= 1:
        workers = 1
    return workers, hw


# ---------------------------------------------------------------------------
# Token-efficient output
# ---------------------------------------------------------------------------

def _summarize_result(path: str, success: bool, match_count: int,
                      strategy: str = "", error: str = "",
                      elapsed_ms: float = 0.0) -> dict[str, Any]:
    """Create compact token-efficient result summary."""
    return {
        "path": path,
        "success": success,
        "matches": match_count,
        "strategy": strategy,
        "error": error if not success else None,
        "ms": round(elapsed_ms, 2),
    }


# ---------------------------------------------------------------------------
# Batch patch execution
# ---------------------------------------------------------------------------

def _execute_single_patch(op: dict[str, Any], task_id: str,
                           cross_profile: bool = False) -> dict[str, Any]:
    """Execute a single patch operation. Called from worker threads.

    Each thread gets its own file_ops instance — no shared state.
    HashLine index cache is per-file (mtime-based), so concurrent
    patches to different files don't interfere.
    """
    path = op.get("path", "")
    old_string = op.get("old_string", "")
    new_string = op.get("new_string", "")
    replace_all = op.get("replace_all", False)

    if not path:
        return _summarize_result("", False, 0, error="path required")

    t0 = time.perf_counter()

    try:
        # Import here to avoid circular deps and ensure hashline is loaded
        from tools.file_tools import patch_tool
        result_str = patch_tool(
            mode="replace",
            path=path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            task_id=task_id,
            cross_profile=cross_profile,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        # Parse result — patch_tool returns JSON string
        try:
            result = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            # Not JSON — check for error indicators
            if "error" in result_str.lower() or "failed" in result_str.lower():
                return _summarize_result(path, False, 0, error=result_str[:500],
                                        elapsed_ms=elapsed)
            return _summarize_result(path, True, 1, strategy="ok",
                                    elapsed_ms=elapsed)

        # Extract match count and strategy from result
        if isinstance(result, dict):
            # Check for error in result
            if result.get("error"):
                return _summarize_result(path, False, 0,
                                        error=str(result["error"])[:500],
                                        elapsed_ms=elapsed)
            # Success — extract details
            match_count = 1  # patch_tool returns success/failure
            strategy = result.get("strategy", "")
            return _summarize_result(path, True, match_count, strategy=strategy,
                                    elapsed_ms=elapsed)
        else:
            return _summarize_result(path, True, 1, elapsed_ms=elapsed)

    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return _summarize_result(path, False, 0, error=str(e)[:500],
                                elapsed_ms=elapsed)


def batch_patch_tool(operations: list[dict[str, Any]],
                     task_id: str = "default",
                     cross_profile: bool = False) -> str:
    """Apply multiple patch operations in parallel.

    Args:
        operations: List of patch operations, each with:
            - path (str, required): file path
            - old_string (str, required): text to find
            - new_string (str, required): replacement text
            - replace_all (bool, optional): replace all occurrences
        task_id: Task/session ID for path resolution
        cross_profile: Allow cross-profile edits

    Returns:
        JSON string with results array + summary stats.
    """
    if not operations:
        return json.dumps({
            "success": False,
            "error": "operations list is empty",
        })

    if not isinstance(operations, list):
        return json.dumps({
            "success": False,
            "error": "operations must be a list",
        })

    # Validate each operation
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            return json.dumps({
                "success": False,
                "error": f"operation {i} is not a dict",
            })
        if not op.get("path"):
            return json.dumps({
                "success": False,
                "error": f"operation {i}: path required",
            })
        if op.get("old_string") is None or op.get("new_string") is None:
            return json.dumps({
                "success": False,
                "error": f"operation {i}: old_string and new_string required",
            })

    # Check sensitive paths
    from tools.file_tools import _check_cross_profile_path, _check_sensitive_path, tool_error
    for op in operations:
        path = op["path"]
        sensitive_err = _check_sensitive_path(path, task_id)
        if sensitive_err:
            return tool_error(sensitive_err)
        if not cross_profile:
            cross_warning = _check_cross_profile_path(path, task_id)
            if cross_warning:
                return tool_error(cross_warning)

    num_ops = len(operations)
    workers, hw_info = _compute_workers(num_ops)

    logger.info(
        "batch_patch: %d operations, %d workers (cpu_cores=%d, avail_gb=%d)",
        num_ops, workers, hw_info["cpu_cores"], hw_info["available_gb"],
    )

    results: list[dict[str, Any]] = [None] * num_ops  # preserve order
    t0 = time.perf_counter()

    if workers <= 1 or num_ops <= 1:
        # Sequential execution — no thread overhead
        for i, op in enumerate(operations):
            results[i] = _execute_single_patch(op, task_id, cross_profile)
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="batch_patch") as executor:
            # Submit all operations, keeping index for ordered results
            future_to_idx = {
                executor.submit(_execute_single_patch, op, task_id, cross_profile): i
                for i, op in enumerate(operations)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = _summarize_result(
                        operations[idx].get("path", ""), False, 0,
                        error=str(e)[:500],
                    )

    elapsed_total = (time.perf_counter() - t0) * 1000

    # Build summary
    succeeded = sum(1 for r in results if r and r["success"])
    failed = num_ops - succeeded
    total_ms = sum(r.get("ms", 0) for r in results if r)
    # Sequential time would be ~total_ms; parallel is elapsed_total
    speedup = total_ms / elapsed_total if elapsed_total > 0 else 1.0

    summary = {
        "success": failed == 0,
        "total": num_ops,
        "succeeded": succeeded,
        "failed": failed,
        "workers": workers,
        "hardware": {
            "cpu_cores": hw_info["cpu_cores"],
            "logical_cores": hw_info["logical_cores"],
            "available_gb": hw_info["available_gb"],
        },
        "timing": {
            "total_ms": round(elapsed_total, 2),
            "sum_ms": round(total_ms, 2),
            "speedup": round(speedup, 2),
        },
        "results": results,
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

BATCH_PATCH_SCHEMA = {
    "name": "batch_patch",
    "description": (
        "Apply multiple find-and-replace patches to different files in ONE call. "
        "Uses hardware-aware parallel execution (ThreadPoolExecutor with auto-detected worker count). "
        "Each patch uses HashLine for O(1) matching (0.11ms vs 526ms fuzzy). "
        "Returns compact per-file results + timing stats.\n\n"
        "PASS a list of operations, each with: path, old_string, new_string, replace_all (optional).\n"
        "Example: batch_patch(operations=[{path: 'a.py', old: 'x', new: 'y'}, {path: 'b.py', old: 'z', new: 'w'}])\n\n"
        "Saves 60-70% tokens vs N separate patch calls (1 round-trip instead of N)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "description": (
                    "List of patch operations. Each operation is an object with: "
                    "'path' (str, required), 'old_string' (str, required), "
                    "'new_string' (str, required), 'replace_all' (bool, optional, default false)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to edit"},
                        "old_string": {"type": "string", "description": "Text to find. Must be unique unless replace_all=true."},
                        "new_string": {"type": "string", "description": "Replacement text. Pass '' to delete."},
                        "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)", "default": False},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
            "cross_profile": {
                "type": "boolean",
                "description": "Opt out of cross-profile guard. Default false.",
                "default": False,
            },
        },
        "required": ["operations"],
    },
}


def _handle_batch_patch(args, **kw):
    tid = kw.get("task_id") or "default"
    operations = args.get("operations", [])
    cross_profile = bool(args.get("cross_profile", False))
    return batch_patch_tool(operations, task_id=tid, cross_profile=cross_profile)


def check_batch_patch_requirements() -> bool:
    """Batch patch works whenever file tools work."""
    from tools.file_tools import _check_file_reqs
    return _check_file_reqs()


# Auto-register on import
try:
    from tools.registry import registry
    registry.register(
        name="batch_patch",
        toolset="file",
        schema=BATCH_PATCH_SCHEMA,
        handler=_handle_batch_patch,
        check_fn=check_batch_patch_requirements,
        emoji="⚡",
        max_result_size_chars=100_000,
    )
except Exception as e:
    logger.debug("Could not register batch_patch: %s", e)
