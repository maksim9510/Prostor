#!/usr/bin/env python3
"""
fuzzy_match_patch — Monkey-patch wrapper for hashline integration.

When loaded alongside tools.hashline, this module patches
fuzzy_find_and_replace to try hashline first (fast path), falling
back to the original 9-strategy fuzzy_match if hashline doesn't find a match.

This approach:
  - Does NOT modify fuzzy_match.py source
  - Does NOT break existing behavior
  - Automatically falls back to fuzzy_match
  - Easy to uninstall (just remove hashline.py + this file)

Activation: tools/hashline.py imports this module at the bottom.
Deactivation: remove tools/hashline.py — fuzzy_match works as before.
"""

import os
import sys
from typing import Optional, Tuple

# No threshold — hashline is faster than fuzzy_match on ALL file sizes
# after the exact-match fast path optimization (str.find before index build).
# Hashline tries: exact str.find → quick reject → hash index → fuzzy fallback.
HASHLINE_THRESHOLD = 0  # disabled — hashline always


def apply_patch():
    """Monkey-patch fuzzy_find_and_replace to try hashline first."""
    try:
        from tools import fuzzy_match
        from tools.hashline import hashline_find_and_replace
    except ImportError:
        # hashline or fuzzy_match not available — skip patch
        return False

    # Check if already patched (avoid double-patch)
    if getattr(fuzzy_match.fuzzy_find_and_replace, "_hashline_patched", False):
        return True

    _original_fuzzy = fuzzy_match.fuzzy_find_and_replace

    def patched_find_and_replace(
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        file_path: Optional[str] = None,
        file_mtime: Optional[float] = None,
        **kwargs,
    ) -> Tuple[str, int, Optional[str], Optional[str]]:
        """Patched find_and_replace: hashline always → fuzzy fallback."""
        # Hashline for ALL file sizes (no threshold)
        try:
            result = hashline_find_and_replace(
                content, old_string, new_string, replace_all,
                file_path=file_path, file_mtime=file_mtime,
            )
            # result = (new_content, match_count, strategy, error)
            if result[1] > 0:
                # hashline found a match — return it
                return result
            if result[3] and "Found" in result[3] and "matches" in result[3]:
                # Multiple matches error — return it (same as fuzzy would)
                return result
            # hashline didn't find → fall through to fuzzy_match
        except Exception:
            # hashline error → fall through to fuzzy_match (safe fallback)
            pass

        # Fallback: original fuzzy_match (9 strategies)
        return _original_fuzzy(content, old_string, new_string, replace_all)

    # Mark as patched
    patched_find_and_replace._hashline_patched = True
    patched_find_and_replace._original = _original_fuzzy

    # Apply patch
    fuzzy_match.fuzzy_find_and_replace = patched_find_and_replace

    return True


def revert_patch():
    """Revert the monkey-patch (restore original fuzzy_find_and_replace)."""
    try:
        from tools import fuzzy_match
        current = fuzzy_match.fuzzy_find_and_replace
        if getattr(current, "_hashline_patched", False):
            fuzzy_match.fuzzy_find_and_replace = current._original
            return True
    except ImportError:
        pass
    return False


# Auto-apply patch when this module is imported
apply_patch()