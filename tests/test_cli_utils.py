"""Tests for prostor_cli.cli_utils — pure utility functions extracted from cli.py."""

import pytest

from prostor_cli.cli_utils import (
    format_duration_compact,
    format_token_count_compact,
    strip_reasoning_tags,
    assistant_content_as_text,
    assistant_copy_text,
)


class TestFormatDurationCompact:
    @pytest.mark.parametrize("seconds,expected", [
        (0, "0s"),
        (42, "42s"),
        (59, "59s"),
        (60, "1m"),
        (125, "2m"),
        (3600, "1h"),
        (3725, "1h 2m"),
        (86400, "1.0d"),
        (129600, "1.5d"),
    ])
    def test_basic_durations(self, seconds, expected):
        assert format_duration_compact(seconds) == expected

    def test_floats_accepted(self):
        assert format_duration_compact(45.7).endswith("s")
        assert format_duration_compact(3725.4) == "1h 2m"


class TestFormatTokenCountCompact:
    @pytest.mark.parametrize("value,expected", [
        (0, "0"),
        (1, "1"),
        (999, "999"),
        # >=1K trailing zeros are stripped: 1.00K -> 1K, 1.50K -> 1.5K
        (1_000, "1K"),
        (9_500, "9.5K"),
        (12_500, "12.5K"),
        (150_000, "150K"),
        (1_500_000, "1.5M"),
        (2_500_000, "2.5M"),
        (250_000_000, "250M"),
        (1_500_000_000, "1.5B"),
    ])
    def test_basic_token_counts(self, value, expected):
        assert format_token_count_compact(value) == expected

    def test_negative_values(self):
        assert format_token_count_compact(-1_500_000) == "-1.5M"
        assert format_token_count_compact(-500) == "-500"


class TestStripReasoningTags:
    def test_closed_pair_think(self):
        text = "before<think>secret</think>after"
        assert strip_reasoning_tags(text) == "beforeafter"

    def test_unterminated_open_tag(self):
        text = "<think>never closes here"
        assert strip_reasoning_tags(text) == ""

    def test_orphan_close_tag(self):
        text = "stuff</think>answer"
        assert strip_reasoning_tags(text) == "stuffanswer"

    def test_case_insensitive(self):
        text = "<THINK>secret</THINK>visible"
        assert strip_reasoning_tags(text) == "visible"

    def test_multiple_tag_variants(self):
        text = "<REASONING_SCRATCHPAD>x</REASONING_SCRATCHPAD><think>y</think><think>z</think>done"
        assert strip_reasoning_tags(text) == "done"

    def test_multiline_content(self):
        text = "<think>line1\nline2\nline3</think>result"
        assert strip_reasoning_tags(text) == "result"

    def test_tool_call_blocks_stripped(self):
        text = "before<tool_call>stuff</tool_call>after"
        assert strip_reasoning_tags(text) == "beforeafter"

    def test_function_call_blocks_stripped(self):
        text = "before<function_calls>x</function_calls>after"
        assert strip_reasoning_tags(text) == "beforeafter"

    def test_gemma_function_with_name(self):
        # Gemma-style: <function name="foo"> ... </function>
        # Must be at sentence boundary to avoid false positives in prose
        # Note: the regex strips ALL whitespace inside the boundary match,
        # so the space before "Done." gets eaten too. Documented behavior.
        text = 'Hi there. <function name="x">call</function> Done.'
        assert strip_reasoning_tags(text) == "Hi there.Done."

    def test_orphan_close_tags_stripped(self):
        text = "before</function_call>after"
        assert strip_reasoning_tags(text) == "beforeafter"

    def test_no_tags_passthrough(self):
        text = "just plain text with no tags"
        assert strip_reasoning_tags(text) == "just plain text with no tags"

    def test_empty_string(self):
        assert strip_reasoning_tags("") == ""

    def test_must_stay_in_sync_with_run_agent(self):
        """The reasoning-tag regexes here must match run_agent.py's _strip_think_blocks.

        If a model emits a new variant (e.g. <reflection>), it should be added
        to BOTH places — this is a known invariant.
        """
        # Sanity check: we cover the documented tag set
        from prostor_cli.cli_utils import _REASONING_TAGS
        required = {"think", "thinking", "reasoning", "thought", "REASONING_SCRATCHPAD"}
        assert required.issubset(set(_REASONING_TAGS))


class TestAssistantContentAsText:
    def test_none_returns_empty(self):
        assert assistant_content_as_text(None) == ""

    def test_string_passthrough(self):
        assert assistant_content_as_text("hello") == "hello"

    def test_list_of_text_dicts(self):
        content = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        assert assistant_content_as_text(content) == "first\nsecond"

    def test_list_filters_non_text(self):
        # tool_use, images, etc. are dropped on the display path
        content = [
            {"type": "text", "text": "before"},
            {"type": "tool_use", "id": "x", "name": "y", "input": {}},
            {"type": "text", "text": "after"},
        ]
        assert assistant_content_as_text(content) == "before\nafter"

    def test_list_with_empty_text_skipped(self):
        content = [
            {"type": "text", "text": "real"},
            {"type": "text", "text": ""},
        ]
        assert assistant_content_as_text(content) == "real"

    def test_dict_non_list_falls_back_to_str(self):
        # Defensive: unexpected shape shouldn't crash the display layer
        assert assistant_content_as_text({"text": "raw"}) == "{'text': 'raw'}"

    def test_int_falls_back_to_str(self):
        assert assistant_content_as_text(42) == "42"


class TestAssistantCopyText:
    def test_string_with_reasoning_stripped(self):
        text = "<think>secret</think>visible"
        assert assistant_copy_text(text) == "visible"

    def test_list_content_with_reasoning_stripped(self):
        content = [
            {"type": "text", "text": "<think>x</think>final"},
        ]
        assert assistant_copy_text(content) == "final"

    def test_none_returns_empty(self):
        assert assistant_copy_text(None) == ""

    def test_never_leaks_think_block(self):
        # This is the key invariant for clipboard — user must never copy leaked XML
        text = "before<think>leaked reasoning</think>after"
        result = assistant_copy_text(text)
        assert "<think>" not in result
        assert "</think>" not in result
        assert result == "beforeafter"
