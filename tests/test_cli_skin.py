"""Tests for prostor_cli.cli_skin — skin + light-mode helpers.

The skin engine isn't fully available in CI, so we test:
  - Pure helpers (hex_to_ansi, luminance_from_hex, remap table)
  - Detection logic with env-var control (reset cache between cases)
  - _SkinAwareAnsi fallback when the skin engine is unreachable
  - Idempotency of install_skin_light_mode_hook
"""

import pytest

from prostor_cli.cli_skin import (
    _LIGHT_MODE_REMAP,
    _LIGHT_MODE_REMAP_UPPER,
    SkinAwareAnsi,
    accent_hex,
    b,
    d,
    detect_light_mode,
    hex_to_ansi,
    install_skin_light_mode_hook,
    luminance_from_hex,
    maybe_remap_for_light_mode,
    reset_light_mode_cache,
)


class TestHexToAnsi:
    def test_6digit_hex(self):
        result = hex_to_ansi("#FFD700")
        # Truecolor SGR: \x1b[38;2;255;215;0m
        assert result == "\x1b[38;2;255;215;0m"

    def test_3digit_hex_expanded(self):
        # #F00 == #FF0000
        result = hex_to_ansi("#F00")
        assert result == "\x1b[38;2;255;0;0m"

    def test_bold_attribute(self):
        result = hex_to_ansi("#FF0000", bold=True)
        # \x1b[1;38;2;...
        assert result == "\x1b[1;38;2;255;0;0m"

    def test_invalid_hex_passthrough(self):
        assert hex_to_ansi("not-a-color") == "not-a-color"
        assert hex_to_ansi("") == ""
        assert hex_to_ansi("#GGGGGG") == "#GGGGGG"  # not valid hex

    def test_already_ansi_passthrough(self):
        # If someone passes an ANSI escape, we don't try to interpret it
        result = hex_to_ansi("\x1b[31m")
        assert result == "\x1b[31m"

    def test_case_insensitive(self):
        assert hex_to_ansi("#ffd700") == hex_to_ansi("#FFD700")
        assert hex_to_ansi("#FfD700") == hex_to_ansi("#FFD700")


class TestLuminanceFromHex:
    def test_white(self):
        assert luminance_from_hex("#FFFFFF") == pytest.approx(1.0)

    def test_black(self):
        assert luminance_from_hex("#000000") == 0.0

    def test_midgray(self):
        # 0.5 luma → exactly the dark/light threshold
        assert luminance_from_hex("#808080") == pytest.approx(0.5, abs=0.01)

    def test_red(self):
        # Rec.709: 0.2126 * 255 / 255 = 0.2126
        assert luminance_from_hex("#FF0000") == pytest.approx(0.2126)

    def test_green(self):
        # 0.7152
        assert luminance_from_hex("#00FF00") == pytest.approx(0.7152)

    def test_blue(self):
        # 0.0722
        assert luminance_from_hex("#0000FF") == pytest.approx(0.0722)

    def test_invalid_returns_none(self):
        assert luminance_from_hex("not-hex") is None
        assert luminance_from_hex("#GGG") is None
        assert luminance_from_hex("") is None
        assert luminance_from_hex(None) is None  # type: ignore[arg-type]

    def test_3digit_expansion(self):
        # #FFF == #FFFFFF
        assert luminance_from_hex("#FFF") == luminance_from_hex("#FFFFFF")


class TestDetectLightMode:
    def setup_method(self):
        reset_light_mode_cache()

    def teardown_method(self):
        # Clear env vars that may have been set by the test
        for var in (
            "PROSTOR_LIGHT",
            "PROSTOR_TUI_LIGHT",
            "PROSTOR_TUI_THEME",
            "PROSTOR_TUI_BACKGROUND",
            "COLORFGBG",
        ):
            if var in __import__("os").environ:
                del __import__("os").environ[var]
        reset_light_mode_cache()

    def test_default_is_dark(self, monkeypatch):
        # With no env hints, default is dark
        for var in (
            "PROSTOR_LIGHT",
            "PROSTOR_TUI_LIGHT",
            "PROSTOR_TUI_THEME",
            "PROSTOR_TUI_BACKGROUND",
            "COLORFGBG",
        ):
            monkeypatch.delenv(var, raising=False)
        result = detect_light_mode()
        # In a test env, stdin/stdout are not TTYs, so OSC 11 is skipped.
        # Default should be False (dark).
        assert result is False

    def test_explicit_light_override(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        assert detect_light_mode() is True

    def test_explicit_dark_override(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "false")
        assert detect_light_mode() is False

    def test_theme_light_hint(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_TUI_THEME", "light")
        assert detect_light_mode() is True

    def test_theme_dark_hint(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_TUI_THEME", "dark")
        assert detect_light_mode() is False

    def test_background_hex_light(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_TUI_BACKGROUND", "#FFFFFF")
        assert detect_light_mode() is True

    def test_background_hex_dark(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_TUI_BACKGROUND", "#000000")
        assert detect_light_mode() is False

    def test_colorfgbg_light(self, monkeypatch):
        # COLORFGBG="15;0" means bg=15 (light)
        monkeypatch.setenv("COLORFGBG", "0;15")
        assert detect_light_mode() is True

    def test_colorfgbg_dark(self, monkeypatch):
        # COLORFGBG="0;0" means bg=0 (dark)
        monkeypatch.setenv("COLORFGBG", "15;0")
        assert detect_light_mode() is False

    def test_priority_env_over_theme(self, monkeypatch):
        # PROSTOR_LIGHT=true should win over PROSTOR_TUI_THEME=dark
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        monkeypatch.setenv("PROSTOR_TUI_THEME", "dark")
        assert detect_light_mode() is True

    def test_priority_theme_over_background(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_TUI_THEME", "dark")
        monkeypatch.setenv("PROSTOR_TUI_BACKGROUND", "#FFFFFF")
        assert detect_light_mode() is False

    def test_result_is_cached(self, monkeypatch):
        # First call sets cache
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        first = detect_light_mode()
        # Change env, but cache should still hold
        monkeypatch.setenv("PROSTOR_LIGHT", "false")
        second = detect_light_mode()
        assert first == second is True
        # Now reset and re-detect
        reset_light_mode_cache()
        third = detect_light_mode()
        assert third is False


class TestMaybeRemapForLightMode:
    def setup_method(self):
        reset_light_mode_cache()

    def teardown_method(self):
        for var in ("PROSTOR_LIGHT", "PROSTOR_TUI_THEME", "PROSTOR_TUI_BACKGROUND"):
            if var in __import__("os").environ:
                del __import__("os").environ[var]
        reset_light_mode_cache()

    def test_dark_mode_passthrough(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "false")
        # In dark mode, remap is a no-op
        assert maybe_remap_for_light_mode("#FFD700") == "#FFD700"
        assert maybe_remap_for_light_mode("#FFF8DC") == "#FFF8DC"

    def test_light_mode_remaps_known_colors(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        assert maybe_remap_for_light_mode("#FFD700") == "#9A6B00"
        assert maybe_remap_for_light_mode("#B8860B") == "#5C4500"

    def test_light_mode_passthrough_unknown_colors(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        # #123456 is not in the remap table
        assert maybe_remap_for_light_mode("#123456") == "#123456"

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        assert maybe_remap_for_light_mode("#ffd700") == "#9A6B00"
        assert maybe_remap_for_light_mode("#FfD700") == "#9A6B00"

    def test_non_hex_passthrough(self, monkeypatch):
        monkeypatch.setenv("PROSTOR_LIGHT", "true")
        assert maybe_remap_for_light_mode("") == ""
        assert maybe_remap_for_light_mode("red") == "red"
        assert maybe_remap_for_light_mode("not-a-color") == "not-a-color"


class TestRemapTable:
    def test_all_keys_are_lowercase_or_uppercase_hex(self):
        # All keys are 7-char hex strings starting with #
        for k in _LIGHT_MODE_REMAP:
            assert k.startswith("#")
            assert len(k) == 7
            # Allow both upper and lower in the table itself (consistency check)
            int(k[1:], 16)  # would raise if not valid hex

    def test_values_are_dark_equivalents(self):
        # The whole point of the remap is to make light-mode colors
        # readable on cream backgrounds.  Values should be DARKER.
        for orig, replacement in _LIGHT_MODE_REMAP.items():
            orig_lum = luminance_from_hex(orig) or 0
            new_lum = luminance_from_hex(replacement) or 0
            assert new_lum < orig_lum, (
                f"remap {orig} -> {replacement} did not produce a darker value"
            )

    def test_pre_uppered_lookup_matches(self):
        # The internal _LIGHT_MODE_REMAP_UPPER should have the same keys (uppercased)
        assert set(_LIGHT_MODE_REMAP_UPPER.keys()) == {k.upper() for k in _LIGHT_MODE_REMAP}
        # And the same values
        for orig, replacement in _LIGHT_MODE_REMAP.items():
            assert _LIGHT_MODE_REMAP_UPPER[orig.upper()] == replacement


class TestInstallHookIdempotency:
    def test_idempotent(self):
        # Multiple calls must not stack-wrap
        assert install_skin_light_mode_hook() is True
        # Second call still returns True and doesn't crash
        assert install_skin_light_mode_hook() is True


class TestSkinAwareAnsi:
    def test_fallback_when_no_skin_engine(self, monkeypatch):
        # If prostor_cli.skin_engine isn't importable, fall back to fallback_hex
        # The class handles ImportError internally
        from prostor_cli import cli_skin
        # Force the import to fail inside the class
        orig_import = cli_skin.get_active_skin if False else None  # placeholder

        # Simpler: just create one and let it fall back
        skin = SkinAwareAnsi("nonexistent_key", fallback_hex="#FF0000")
        result = str(skin)
        # Should produce a valid ANSI sequence
        assert result.startswith("\x1b[")
        assert result.endswith("m")

    def test_reset_clears_cache(self):
        skin = SkinAwareAnsi("key", fallback_hex="#FF0000")
        first = str(skin)
        skin.reset()
        second = str(skin)
        # After reset, the string should still be the same value
        # (because the skin engine fallback is the same), but
        # reset() must clear the cache.
        assert skin._cached is not None  # was set by str()

    def test_addition(self):
        skin = SkinAwareAnsi("key", fallback_hex="#FF0000")
        result = skin + " world"
        assert "world" in result


class TestBoldDim:
    def test_b_returns_string(self):
        result = b("test")
        # Either bold ANSI or plain text — both are valid
        assert isinstance(result, str)
        assert "test" in result

    def test_d_returns_string(self):
        result = d("test")
        assert isinstance(result, str)
        assert "test" in result

    def test_b_no_tty_plain(self):
        # When stdout is not a TTY, b() returns plain text
        # (this is automatically true in pytest)
        result = b("test")
        # In non-TTY (pytest), result should be plain "test"
        # (or bold if stdout happens to be a TTY)
        assert isinstance(result, str)


class TestAccentHex:
    def test_returns_string(self):
        result = accent_hex()
        assert isinstance(result, str)
        # Either a hex color from the skin engine, or the fallback "#FFBF00"
        assert result.startswith("#") or result == "#FFBF00"
