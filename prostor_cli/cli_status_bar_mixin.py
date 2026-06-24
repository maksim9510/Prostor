"""Status-bar / TUI footer display methods for ``ProstorCLI``.

Extracted from ``cli.py`` as part of the god-file decomposition campaign
(Phase 4). This mixin holds the status-bar cluster: the post-resize
unsuppress debouncer, context-bar builder, status-bar snapshot, display-width
/ trim helpers, the plain-text and prompt_toolkit-fragment renderers, the
slow-command status message map, and the three ``/status`` screens
(startup line, session status, gateway status).

Behavior-neutral: every method is lifted verbatim from ``ProstorCLI``.
``self.*`` calls resolve unchanged via the MRO. Neutral dependencies are
imported at module top level; ``cli.py``-internal helpers/constants are
imported lazily inside each method (``from cli import ...`` resolves at call
time, when ``cli`` is fully loaded) so this module never imports ``cli`` at
import time -> no import cycle.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from prostor_cli.cli_utils import format_duration_compact, format_token_count_compact


class CLIStatusBarMixin:
    """Mixin holding status-bar / TUI footer display methods for ``ProstorCLI``."""

    def _schedule_status_bar_unsuppress(self, app, delay: float = 0.35) -> None:
        """Clear the post-resize status-bar suppression after the reflow settles.

        Debounced: a fresh resize cancels the pending unsuppress and restarts
        the timer, so a resize storm only repaints the bar once it stops.
        """
        try:
            old_timer = getattr(self, "_status_bar_unsuppress_timer", None)
            if old_timer is not None:
                try:
                    old_timer.cancel()
                except Exception:
                    pass

            def _clear():
                self._status_bar_suppressed_after_resize = False
                try:
                    app.invalidate()
                except Exception:
                    pass

            def _fire():
                try:
                    loop = getattr(app, "loop", None)
                except Exception:
                    loop = None
                if loop is not None:
                    try:
                        loop.call_soon_threadsafe(_clear)
                        return
                    except Exception:
                        pass
                _clear()

            timer = threading.Timer(delay, _fire)
            timer.daemon = True
            self._status_bar_unsuppress_timer = timer
            timer.start()
        except Exception:
            # Fail open: never leave the bar stuck hidden.
            self._status_bar_suppressed_after_resize = False

    def _build_context_bar(self, percent_used: int | None, width: int = 10) -> str:
        safe_percent = max(0, min(100, percent_used or 0))
        filled = round((safe_percent / 100) * width)
        return f"[{('█' * filled) + ('░' * max(0, width - filled))}]"

    def _get_status_bar_snapshot(self) -> dict[str, Any]:
        # Prefer the agent's model name — it updates on fallback.
        # self.model reflects the originally configured model and never
        # changes mid-session, so the TUI would show a stale name after
        # _try_activate_fallback() switches provider/model.
        agent = getattr(self, "agent", None)
        model_name = (getattr(agent, "model", None) or self.model or "unknown")
        model_short = model_name.split("/")[-1] if "/" in model_name else model_name
        if model_short.endswith(".gguf"):
            model_short = model_short[:-5]
        if len(model_short) > 26:
            model_short = f"{model_short[:23]}..."

        elapsed_seconds = max(0.0, (datetime.now() - self.session_start).total_seconds())
        snapshot = {
            "model_name": model_name,
            "model_short": model_short,
            "duration": format_duration_compact(elapsed_seconds),
            "prompt_elapsed": self._format_prompt_elapsed(
                getattr(self, "_prompt_start_time", None),
                getattr(self, "_prompt_duration", 0.0),
                live=getattr(self, "_prompt_start_time", None) is not None,
            ),
            "idle_since": self._format_idle_since(
                getattr(self, "_last_turn_finished_at", None),
                turn_live=getattr(self, "_prompt_start_time", None) is not None,
            ),
            "context_tokens": 0,
            "context_length": None,
            "context_percent": None,
            "session_input_tokens": 0,
            "session_output_tokens": 0,
            "session_cache_read_tokens": 0,
            "session_cache_write_tokens": 0,
            "session_prompt_tokens": 0,
            "session_completion_tokens": 0,
            "session_total_tokens": 0,
            "session_api_calls": 0,
            "compressions": 0,
            "active_background_tasks": 0,
            "active_background_processes": 0,
        }

        # Count live /background tasks. The dict entry is removed in the
        # task thread's finally block, so len() reflects truly-running tasks.
        # len() on a CPython dict is atomic; safe to read without a lock.
        try:
            bg_tasks = getattr(self, "_background_tasks", None)
            if bg_tasks:
                snapshot["active_background_tasks"] = len(bg_tasks)
        except Exception:
            pass

        # Count live background terminal processes (terminal tool background
        # sessions tracked by tools.process_registry). Cheap O(1) read.
        try:
            from tools.process_registry import process_registry
            snapshot["active_background_processes"] = process_registry.count_running()
        except Exception:
            pass

        if not agent:
            return snapshot

        snapshot["session_input_tokens"] = getattr(agent, "session_input_tokens", 0) or 0
        snapshot["session_output_tokens"] = getattr(agent, "session_output_tokens", 0) or 0
        snapshot["session_cache_read_tokens"] = getattr(agent, "session_cache_read_tokens", 0) or 0
        snapshot["session_cache_write_tokens"] = getattr(agent, "session_cache_write_tokens", 0) or 0
        snapshot["session_prompt_tokens"] = getattr(agent, "session_prompt_tokens", 0) or 0
        snapshot["session_completion_tokens"] = getattr(agent, "session_completion_tokens", 0) or 0
        snapshot["session_total_tokens"] = getattr(agent, "session_total_tokens", 0) or 0
        snapshot["session_api_calls"] = getattr(agent, "session_api_calls", 0) or 0

        compressor = getattr(agent, "context_compressor", None)
        if compressor:
            # last_prompt_tokens is parked at the -1 sentinel right after a
            # compression, until the next real API call reports a prompt count
            # (awaiting_real_usage_after_compression). The status bar must not
            # render that sentinel verbatim — it produced "-1/200K" / "-1%".
            # Clamp it to 0 so the one transitional turn reads as empty context.
            context_tokens = getattr(compressor, "last_prompt_tokens", 0) or 0
            if context_tokens < 0:
                context_tokens = 0
            context_length = getattr(compressor, "context_length", 0) or 0
            if context_length < 0:
                context_length = 0
            snapshot["context_tokens"] = context_tokens
            snapshot["context_length"] = context_length or None
            snapshot["compressions"] = getattr(compressor, "compression_count", 0) or 0
            if context_length:
                snapshot["context_percent"] = max(0, min(100, round((context_tokens / context_length) * 100)))

        return snapshot

    @staticmethod
    def _status_bar_display_width(text: str) -> int:
        """Return terminal cell width for status-bar text.

        len() is not enough for prompt_toolkit layout decisions because some
        glyphs can render wider than one Python codepoint. Keeping the status
        bar within the real display width prevents it from wrapping onto a
        second line and leaving behind duplicate rows.
        """
        try:
            from prompt_toolkit.utils import get_cwidth
            return get_cwidth(text or "")
        except Exception:
            return len(text or "")

    @classmethod
    def _trim_status_bar_text(cls, text: str, max_width: int) -> str:
        """Trim status-bar text to a single terminal row."""
        if max_width <= 0:
            return ""
        try:
            from prompt_toolkit.utils import get_cwidth
        except Exception:
            get_cwidth = None

        if cls._status_bar_display_width(text) <= max_width:
            return text

        ellipsis = "..."
        ellipsis_width = cls._status_bar_display_width(ellipsis)
        if max_width <= ellipsis_width:
            return ellipsis[:max_width]

        out = []
        width = 0
        for ch in text:
            ch_width = get_cwidth(ch) if get_cwidth else len(ch)
            if width + ch_width + ellipsis_width > max_width:
                break
            out.append(ch)
            width += ch_width
        return "".join(out).rstrip() + ellipsis

    def _build_status_bar_text(self, width: int | None = None) -> str:
        """Return a compact one-line session status string for the TUI footer."""
        try:
            from cli import _format_context_length

            snapshot = self._get_status_bar_snapshot()
            if width is None:
                width = self._get_tui_terminal_width()
            percent = snapshot["context_percent"]
            percent_label = f"{percent}%" if percent is not None else "--"
            duration_label = snapshot["duration"]

            yolo_active = self._is_session_yolo_active()
            if width < 52:
                text = f"⚕ {snapshot['model_short']} · {duration_label}"
                if yolo_active:
                    text += " · ⚠ YOLO"
                return self._trim_status_bar_text(text, width)
            if width < 76:
                parts = [f"⚕ {snapshot['model_short']}", percent_label]
                compressions = snapshot.get("compressions", 0)
                if compressions:
                    parts.append(f"🗜️ {compressions}")
                bg_count = snapshot.get("active_background_tasks", 0)
                if bg_count:
                    parts.append(f"▶ {bg_count}")
                bg_proc_count = snapshot.get("active_background_processes", 0)
                if bg_proc_count:
                    parts.append(f"⚙ {bg_proc_count}")
                parts.append(duration_label)
                if yolo_active:
                    parts.append("⚠ YOLO")
                return self._trim_status_bar_text(" · ".join(parts), width)

            if snapshot["context_length"]:
                ctx_total = _format_context_length(snapshot["context_length"])
                ctx_used = format_token_count_compact(snapshot["context_tokens"])
                context_label = f"{ctx_used}/{ctx_total}"
            else:
                context_label = "ctx --"

            compressions = snapshot.get("compressions", 0)
            parts = [f"⚕ {snapshot['model_short']}", context_label, percent_label]
            if compressions:
                parts.append(f"🗜️ {compressions}")
            bg_count = snapshot.get("active_background_tasks", 0)
            if bg_count:
                parts.append(f"▶ {bg_count}")
            bg_proc_count = snapshot.get("active_background_processes", 0)
            if bg_proc_count:
                parts.append(f"⚙ {bg_proc_count}")
            parts.append(duration_label)
            prompt_elapsed = snapshot.get("prompt_elapsed")
            if prompt_elapsed:
                parts.append(prompt_elapsed)
            idle_since = snapshot.get("idle_since")
            if idle_since:
                parts.append(idle_since)
            if yolo_active:
                parts.append("⚠ YOLO")
            return self._trim_status_bar_text(" │ ".join(parts), width)
        except Exception:
            return f"⚕ {self.model if getattr(self, 'model', None) else 'Prostor'}"

    def _get_status_bar_fragments(self):
        from cli import _format_context_length

        if not self._status_bar_visible or getattr(self, '_model_picker_state', None):
            return []
        try:
            snapshot = self._get_status_bar_snapshot()
            # Use prompt_toolkit's own terminal width when running inside the
            # TUI — shutil.get_terminal_size() can return stale or fallback
            # values (especially on SSH) that differ from what prompt_toolkit
            # actually renders, causing the fragments to overflow to a second
            # line and produce duplicated status bar rows over long sessions.
            width = self._get_tui_terminal_width()
            duration_label = snapshot["duration"]
            yolo_active = self._is_session_yolo_active()

            if width < 52:
                frags = [
                    ("class:status-bar", " ⚕ "),
                    ("class:status-bar-strong", snapshot["model_short"]),
                    ("class:status-bar-dim", " · "),
                    ("class:status-bar-dim", duration_label),
                ]
                if yolo_active:
                    frags.append(("class:status-bar-dim", " · "))
                    frags.append(("class:status-bar-yolo", "⚠ YOLO"))
                frags.append(("class:status-bar", " "))
            else:
                percent = snapshot["context_percent"]
                percent_label = f"{percent}%" if percent is not None else "--"
                if width < 76:
                    compressions = snapshot.get("compressions", 0)
                    bg_count = snapshot.get("active_background_tasks", 0)
                    bg_proc_count = snapshot.get("active_background_processes", 0)
                    frags = [
                        ("class:status-bar", " ⚕ "),
                        ("class:status-bar-strong", snapshot["model_short"]),
                        ("class:status-bar-dim", " · "),
                        (self._status_bar_context_style(percent), percent_label),
                    ]
                    if compressions:
                        frags.append(("class:status-bar-dim", " · "))
                        frags.append((self._compression_count_style(compressions), f"🗜️ {compressions}"))
                    if bg_count:
                        frags.append(("class:status-bar-dim", " · "))
                        frags.append(("class:status-bar-strong", f"▶ {bg_count}"))
                    if bg_proc_count:
                        frags.append(("class:status-bar-dim", " · "))
                        frags.append(("class:status-bar-strong", f"⚙ {bg_proc_count}"))
                    frags.extend([
                        ("class:status-bar-dim", " · "),
                        ("class:status-bar-dim", duration_label),
                    ])
                    if yolo_active:
                        frags.append(("class:status-bar-dim", " · "))
                        frags.append(("class:status-bar-yolo", "⚠ YOLO"))
                    frags.append(("class:status-bar", " "))
                else:
                    if snapshot["context_length"]:
                        ctx_total = _format_context_length(snapshot["context_length"])
                        ctx_used = format_token_count_compact(snapshot["context_tokens"])
                        context_label = f"{ctx_used}/{ctx_total}"
                    else:
                        context_label = "ctx --"

                    bar_style = self._status_bar_context_style(percent)
                    compressions = snapshot.get("compressions", 0)
                    bg_count = snapshot.get("active_background_tasks", 0)
                    bg_proc_count = snapshot.get("active_background_processes", 0)
                    frags = [
                        ("class:status-bar", " ⚕ "),
                        ("class:status-bar-strong", snapshot["model_short"]),
                        ("class:status-bar-dim", " │ "),
                        ("class:status-bar-dim", context_label),
                        ("class:status-bar-dim", " │ "),
                        (bar_style, self._build_context_bar(percent)),
                        ("class:status-bar-dim", " "),
                        (bar_style, percent_label),
                    ]
                    if compressions:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append((self._compression_count_style(compressions), f"🗜️ {compressions}"))
                    if bg_count:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append(("class:status-bar-strong", f"▶ {bg_count}"))
                    if bg_proc_count:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append(("class:status-bar-strong", f"⚙ {bg_proc_count}"))
                    frags.extend([
                        ("class:status-bar-dim", " │ "),
                        ("class:status-bar-dim", duration_label),
                    ])
                    # Position 7: per-prompt elapsed timer (live or frozen)
                    prompt_elapsed = snapshot.get("prompt_elapsed")
                    if prompt_elapsed:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append(("class:status-bar-dim", prompt_elapsed))
                    # Position 8: idle time since the last final agent response
                    idle_since = snapshot.get("idle_since")
                    if idle_since:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append(("class:status-bar-dim", idle_since))
                    if yolo_active:
                        frags.append(("class:status-bar-dim", " │ "))
                        frags.append(("class:status-bar-yolo", "⚠ YOLO"))
                    frags.append(("class:status-bar", " "))

            total_width = sum(self._status_bar_display_width(text) for _, text in frags)
            if total_width > width:
                plain_text = "".join(text for _, text in frags)
                trimmed = self._trim_status_bar_text(plain_text, width)
                return [("class:status-bar", trimmed)]
            return frags
        except Exception:
            return [("class:status-bar", f" {self._build_status_bar_text()} ")]

    def _slow_command_status(self, command: str) -> str:
        """Return a user-facing status message for slower slash commands."""
        cmd_lower = command.lower().strip()
        if cmd_lower.startswith("/skills search"):
            return "Searching skills..."
        if cmd_lower.startswith("/skills browse"):
            return "Loading skills..."
        if cmd_lower.startswith("/skills inspect"):
            return "Inspecting skill..."
        if cmd_lower.startswith("/skills install"):
            return "Installing skill..."
        if cmd_lower.startswith("/skills"):
            return "Processing skills command..."
        if cmd_lower == "/reload-mcp":
            return "Reloading MCP servers..."
        if cmd_lower == "/reload-skills" or cmd_lower == "/reload_skills":
            return "Reloading skills..."
        if cmd_lower.startswith("/browser"):
            return "Configuring browser..."
        return "Processing command..."

    def _show_status(self):
        """Show compact startup status line."""
        from cli import display_prostor_home, get_tool_definitions

        # Avoid pulling the full tool registry into the bare Termux prompt path.
        if os.environ.get("PROSTOR_DEFER_AGENT_STARTUP") == "1":
            tool_status = "tools deferred"
        else:
            tools = get_tool_definitions(enabled_toolsets=self.enabled_toolsets, quiet_mode=True)
            tool_count = len(tools) if tools else 0
            tool_status = f"{tool_count} tools"

        # Format model name (shorten if needed)
        model_short = self.model.split("/")[-1] if "/" in self.model else self.model
        if len(model_short) > 30:
            model_short = model_short[:27] + "..."

        # Get API status indicator
        if self.api_key:
            api_indicator = "[green bold]●[/]"
        else:
            api_indicator = "[red bold]●[/]"

        # Build status line with proper markup — skin-aware colors
        try:
            from prostor_cli.skin_engine import get_active_skin
            skin = get_active_skin()
            separator_color = skin.get_color("banner_dim", "#B8860B")
            accent_color = skin.get_color("ui_accent", "#FFBF00")
            label_color = skin.get_color("ui_label", "#DAA520")
        except Exception:
            separator_color, accent_color, label_color = "#B8860B", "#FFBF00", "cyan"
        toolsets_info = ""
        if self.enabled_toolsets and "all" not in self.enabled_toolsets:
            toolsets_info = f" [dim {separator_color}]·[/] [{label_color}]toolsets: {', '.join(self.enabled_toolsets)}[/]"

        provider_info = f" [dim {separator_color}]·[/] [dim]provider: {self.provider}[/]"
        if self._provider_source:
            provider_info += f" [dim {separator_color}]·[/] [dim]auth: {self._provider_source}[/]"

        self._console_print(
            f"  {api_indicator} [{accent_color}]{model_short}[/] "
            f"[dim {separator_color}]·[/] [bold {label_color}]{tool_status}[/]"
            f"{toolsets_info}{provider_info}"
        )

    def _show_session_status(self):
        """Show gateway-style status for the current CLI session."""
        from cli import display_prostor_home

        session_meta = {}
        if self._session_db:
            try:
                session_meta = self._session_db.get_session(self.session_id) or {}
            except Exception:
                session_meta = {}

        title = (session_meta.get("title") or "").strip()

        created_at = self.session_start
        started_at = session_meta.get("started_at")
        if started_at:
            try:
                created_at = datetime.fromtimestamp(float(started_at))
            except Exception:
                created_at = self.session_start

        updated_at = created_at
        for field in ("updated_at", "last_updated_at", "last_activity_at"):
            value = session_meta.get(field)
            if not value:
                continue
            try:
                updated_at = datetime.fromtimestamp(float(value))
                break
            except Exception:
                pass

        agent = getattr(self, "agent", None)
        total_tokens = getattr(agent, "session_total_tokens", 0) or 0
        provider = getattr(self, "provider", None) or "unknown"
        model = getattr(self, "model", None) or "(unknown)"
        is_running = bool(getattr(self, "_agent_running", False))

        lines = [
            "Prostor CLI Status",
            "",
            f"Session ID: {self.session_id}",
            f"Path: {display_prostor_home()}",
        ]
        if title:
            lines.append(f"Title: {title}")
        lines.extend([
            f"Model: {model} ({provider})",
            f"Created: {created_at.strftime('%Y-%m-%d %H:%M')}",
            f"Last Activity: {updated_at.strftime('%Y-%m-%d %H:%M')}",
            f"Tokens: {total_tokens:,}",
            f"Agent Running: {'Yes' if is_running else 'No'}",
        ])
        self._console_print("\n".join(lines), highlight=False, markup=False)

    def _show_gateway_status(self):
        """Show status of the gateway and connected messaging platforms."""
        from cli import display_prostor_home
        from gateway.config import Platform, load_gateway_config

        print()
        print("+" + "-" * 60 + "+")
        print("|" + " " * 15 + "(✿◠‿◠) Gateway Status" + " " * 17 + "|")
        print("+" + "-" * 60 + "+")
        print()

        try:
            config = load_gateway_config()

            print("  Messaging Platform Configuration:")
            print("  " + "-" * 55)

            platform_status = {
                Platform.TELEGRAM: ("Telegram", "TELEGRAM_BOT_TOKEN"),
                Platform.DISCORD: ("Discord", "DISCORD_BOT_TOKEN"),
                Platform.SLACK: ("Slack", "SLACK_BOT_TOKEN"),
                Platform.WHATSAPP: ("WhatsApp", "WHATSAPP_ENABLED"),
            }

            for platform, (name, env_var) in platform_status.items():
                pconfig = config.platforms.get(platform)
                if pconfig and pconfig.enabled:
                    home = config.get_home_channel(platform)
                    home_str = f" → {home.name}" if home else ""
                    print(f"    ✓ {name:<12} Enabled{home_str}")
                else:
                    print(f"    ○ {name:<12} Not configured ({env_var})")

            print()
            print("  Session Reset Policy:")
            print("  " + "-" * 55)
            policy = config.default_reset_policy
            print(f"    Mode: {policy.mode}")
            print(f"    Daily reset at: {policy.at_hour}:00")
            print(f"    Idle timeout: {policy.idle_minutes} minutes")

            print()
            print("  To start the gateway:")
            print("    python cli.py --gateway")
            print()
            print(f"  Configuration file: {display_prostor_home()}/config.yaml")
            print()

        except Exception as e:
            print(f"  Error loading gateway config: {e}")
            print()
            print("  To configure the gateway:")
            print("    1. Set environment variables:")
            print("       TELEGRAM_BOT_TOKEN=your_token")
            print("       DISCORD_BOT_TOKEN=your_token")
            print(f"    2. Or configure settings in {display_prostor_home()}/config.yaml")
            print()