#!/usr/bin/env python3
"""
Batch Read Tool — множественное чтение файлов за один вызов LLM.

Ключевые преимущества:
- 1 round-trip к LLM вместо N (экономия ~60-70% токенов на tool schema)
- Hardware-aware ThreadPoolExecutor (переиспользует detection из batch_patch)
- Token-efficient: auto-truncation + line limit per file
- Smart output: только нужные строки, не весь файл

Паттерн использования:
    batch_read(files=[
        {path: "src/main.py", limit: 50},
        {path: "src/utils.py"},
        {path: "tests/test_main.py", offset: 10, limit: 30}
    ])
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Reuse hardware detection from batch_patch
try:
    from tools.batch_patch_tool import _compute_workers, _detect_hardware
except ImportError:
    _detect_hardware = None
    _compute_workers = None


def _read_single_file(op: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """Read a single file. Called from worker threads."""
    path = op.get("path", "")
    offset = op.get("offset", 1)
    limit = op.get("limit", 500)

    if not path:
        return {"path": "", "success": False, "error": "path required"}

    t0 = time.perf_counter()

    try:
        from tools.file_tools import read_file_tool
        result_str = read_file_tool(
            path=path,
            offset=offset,
            limit=limit,
            task_id=task_id,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        # read_file_tool returns JSON string
        try:
            result = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            # Plain text result
            return {
                "path": path,
                "success": True,
                "content": result_str[:50000],  # cap at 50K chars
                "total_lines": None,
                "ms": round(elapsed, 2),
                "truncated": len(result_str) > 50000,
            }

        if isinstance(result, dict):
            if result.get("error"):
                return {
                    "path": path,
                    "success": False,
                    "error": str(result["error"])[:500],
                    "ms": round(elapsed, 2),
                }

            content = result.get("content", "")
            total_lines = result.get("total_lines")
            actual_offset = result.get("offset", offset)
            actual_limit = result.get("limit", limit)

            # Auto-truncate content if too large
            max_chars = 50000  # ~12K tokens per file
            truncated = False
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... [truncated]"
                truncated = True

            return {
                "path": path,
                "success": True,
                "content": content,
                "total_lines": total_lines,
                "offset": actual_offset,
                "limit": actual_limit,
                "ms": round(elapsed, 2),
                "truncated": truncated,
            }
        else:
            return {
                "path": path,
                "success": True,
                "content": str(result)[:50000],
                "ms": round(elapsed, 2),
            }

    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "path": path,
            "success": False,
            "error": str(e)[:500],
            "ms": round(elapsed, 2),
        }


def batch_read_tool(files: List[Dict[str, Any]],
                    task_id: str = "default") -> str:
    """Read multiple files in parallel.

    Args:
        files: List of read operations, each with:
            - path (str, required): file path
            - offset (int, optional): start line (1-indexed, default 1)
            - limit (int, optional): max lines (default 500)
        task_id: Task/session ID

    Returns:
        JSON string with results array + summary stats.
    """
    if not files:
        return json.dumps({"success": False, "error": "files list is empty"})

    if not isinstance(files, list):
        return json.dumps({"success": False, "error": "files must be a list"})

    # Validate
    for i, op in enumerate(files):
        if not isinstance(op, dict):
            return json.dumps({"success": False, "error": f"file {i} is not a dict"})
        if not op.get("path"):
            return json.dumps({"success": False, "error": f"file {i}: path required"})

    num_ops = len(files)

    # Compute workers
    if _compute_workers:
        workers, hw_info = _compute_workers(num_ops)
    else:
        workers = min(max(1, (os.cpu_count() or 2) - 1), num_ops)
        hw_info = {"cpu_cores": os.cpu_count() or 2, "available_gb": 4}

    logger.info("batch_read: %d files, %d workers", num_ops, workers)

    results: List[Dict[str, Any]] = [None] * num_ops
    t0 = time.perf_counter()

    if workers <= 1 or num_ops <= 1:
        for i, op in enumerate(files):
            results[i] = _read_single_file(op, task_id)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="batch_read") as executor:
            future_to_idx = {
                executor.submit(_read_single_file, op, task_id): i
                for i, op in enumerate(files)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {
                        "path": files[idx].get("path", ""),
                        "success": False,
                        "error": str(e)[:500],
                    }

    elapsed_total = (time.perf_counter() - t0) * 1000

    succeeded = sum(1 for r in results if r and r.get("success"))
    failed = num_ops - succeeded
    total_ms = sum(r.get("ms", 0) for r in results if r)
    speedup = total_ms / elapsed_total if elapsed_total > 0 else 1.0

    # Total content size for token estimation
    total_chars = sum(len(r.get("content", "")) for r in results if r and r.get("success"))
    est_tokens = total_chars // 4  # rough: 4 chars ≈ 1 token

    summary = {
        "success": failed == 0,
        "total": num_ops,
        "succeeded": succeeded,
        "failed": failed,
        "workers": workers,
        "hardware": {
            "cpu_cores": hw_info.get("cpu_cores", "?"),
            "available_gb": hw_info.get("available_gb", "?"),
        },
        "timing": {
            "total_ms": round(elapsed_total, 2),
            "sum_ms": round(total_ms, 2),
            "speedup": round(speedup, 2),
        },
        "content": {
            "total_chars": total_chars,
            "est_tokens": est_tokens,
        },
        "files": results,
    }

    return json.dumps(summary, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

BATCH_READ_SCHEMA = {
    "name": "batch_read",
    "description": (
        "Read multiple files in ONE call with parallel I/O. "
        "Uses hardware-aware ThreadPoolExecutor for concurrent reads. "
        "Auto-truncates large files to 50K chars (~12K tokens) per file.\n\n"
        "PASS a list of file specs, each with: path (required), offset (optional, default 1), limit (optional, default 500).\n"
        "Example: batch_read(files=[{path: 'a.py', limit: 50}, {path: 'b.py'}])\n\n"
        "Saves 60-70% tokens vs N separate read_file calls (1 round-trip instead of N)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": (
                    "List of file read operations. Each is an object with: "
                    "'path' (str, required), 'offset' (int, optional, 1-indexed start line, default 1), "
                    "'limit' (int, optional, max lines to read, default 500)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                        "offset": {"type": "integer", "description": "Start line (1-indexed, default 1)", "default": 1},
                        "limit": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
                    },
                    "required": ["path"],
                },
            },
        },
        "required": ["files"],
    },
}


def _handle_batch_read(args, **kw):
    tid = kw.get("task_id") or "default"
    files = args.get("files", [])
    return batch_read_tool(files, task_id=tid)


def check_batch_read_requirements() -> bool:
    """Batch read works whenever file tools work."""
    from tools.file_tools import _check_file_reqs
    return _check_file_reqs()


# Auto-register on import
try:
    from tools.registry import registry
    registry.register(
        name="batch_read",
        toolset="file",
        schema=BATCH_READ_SCHEMA,
        handler=_handle_batch_read,
        check_fn=check_batch_read_requirements,
        emoji="📚",
        max_result_size_chars=200_000,
    )
except Exception as e:
    logger.debug("Could not register batch_read: %s", e)