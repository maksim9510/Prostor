#!/usr/bin/env python3
"""Show/display methods for ``ProstorCLI``.

Extracted from ``cli.py`` as part of the god-file decomposition campaign.
This mixin holds the display cluster: banner, status, help, tools, toolsets,
config, history, and session listing.

All methods expect ``self`` to be a ``ProstorCLI`` instance.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CLIShowMixin:
    """Show/display methods for the CLI."""

    def show_banner(self):
        """Display the welcome banner in Claude Code style."""
        self.console.clear()
        ctx_len = None
        if hasattr(self, 'agent') and self.agent and hasattr(self.agent, 'context_compressor'):
            ctx_len = self.agent.context_compressor.context_length

        term_width = shutil.get_terminal_size().columns
        use_compact = self.compact or term_width < 80

        if use_compact:
            from prostor_cli.banner import _build_compact_banner
            self._console_print(_build_compact_banner())
            self._show_status()
        else:
            from model_tools import get_tool_definitions
            from prostor_cli.banner import build_welcome_banner
            tools = get_tool_definitions(enabled_toolsets=self.enabled_toolsets, quiet_mode=True)
            cwd = os.getenv("TERMINAL_CWD", os.getcwd())
            build_welcome_banner(
                console=self.console,
                model=self.model,
                cwd=cwd,
                tools=tools,
                enabled_toolsets=self.enabled_toolsets,
                session_id=self.session_id,
                context_length=ctx_len,
            )

        if os.environ.get("PROSTOR_DEFER_AGENT_STARTUP") != "1":
            self._show_tool_availability_warnings()

        from agent.model_metadata import MINIMUM_CONTEXT_LENGTH
        if ctx_len and ctx_len < MINIMUM_CONTEXT_LENGTH:
            self._console_print()
            self._console_print(
                f"[yellow]⚠️  Context length is only {ctx_len:,} tokens — "
                f"this is likely too low for agent use with tools.[/]"
            )
            self._console_print(
                f"[dim]   Prostor needs at least {MINIMUM_CONTEXT_LENGTH:,} tokens.[/]"
            )

        self._console_print()

    def _restore_session_cwd(self, session_meta: dict, *, quiet: bool = False) -> None:
        """Relaunch a resumed session in the directory it was started from."""
        recorded = (session_meta or {}).get("cwd")
        if not recorded:
            return
        recorded = os.path.expanduser(str(recorded))
        try:
            current = os.getcwd()
        except OSError:
            current = None
        if current and os.path.realpath(recorded) == os.path.realpath(current):
            return

        if not os.path.isdir(recorded):
            msg = f"⚠ Session's working directory is gone: {recorded} — staying in {current or '.'}"
            if quiet:
                print(msg, file=sys.stderr)
            else:
                self._console_print(f"[dim]{msg}[/dim]")
            return

        try:
            os.chdir(recorded)
        except OSError as e:
            msg = f"⚠ Could not enter session's working directory {recorded}: {e}"
            if quiet:
                print(msg, file=sys.stderr)
            else:
                self._console_print(f"[dim]{msg}[/dim]")
            return

        os.environ["TERMINAL_CWD"] = recorded
        msg = f"↻ Working directory: {recorded}"
        if quiet:
            print(msg, file=sys.stderr)
        else:
            self._console_print(f"[dim]{msg}[/dim]")

    def _render_resume_history_panel_lines(self, panel) -> list[str]:
        """Render the resume panel at the current terminal width."""
        from io import StringIO
        from rich.console import Console

        buf = StringIO()
        width = shutil.get_terminal_size((80, 24)).columns
        console = Console(file=buf, force_terminal=True, color_system="truecolor", highlight=False, width=width)
        console.print(panel)
        return buf.getvalue().rstrip("\n").splitlines()

    def _try_attach_clipboard_image(self) -> bool:
        """Check clipboard for an image and attach it if found."""
        from prostor_cli.clipboard import save_clipboard_image
        from prostor_constants import get_prostor_home

        img_dir = get_prostor_home() / "images"
        self._image_counter += 1
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = img_dir / f"clip_{ts}_{self._image_counter}.png"

        if save_clipboard_image(img_path):
            self._attached_images.append(img_path)
            return True
        self._image_counter -= 1
        return False

    def _resolve_checkpoint_ref(self, ref: str, checkpoints: list) -> str | None:
        """Resolve a checkpoint number or hash to a full commit hash."""
        try:
            idx = int(ref) - 1
            if 0 <= idx < len(checkpoints):
                return checkpoints[idx]["hash"]
            else:
                print(f"  Invalid checkpoint number. Use 1-{len(checkpoints)}.")
                return None
        except ValueError:
            return ref

    def _write_osc52_clipboard(self, text: str) -> None:
        """Copy text to terminal clipboard via OSC 52."""
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        seq = f"\x1b]52;c;{payload}\x07"
        out = getattr(self, "_app", None)
        output = getattr(out, "output", None) if out else None
        if output and hasattr(output, "write_raw"):
            output.write_raw(seq)
            output.flush()
            return
        if output and hasattr(output, "write"):
            output.write(seq)
            output.flush()
            return
        sys.stdout.write(seq)
        sys.stdout.flush()

    def _recover_terminal_input_modes(self, *, reason: str) -> None:
        """Best-effort reset when leaked mouse reports indicate mode drift."""
        now = time.monotonic()
        if now - self._last_input_mode_recovery < 0.5:
            return
        self._last_input_mode_recovery = now

        out = getattr(self, "_app", None)
        output = getattr(out, "output", None) if out else None
        try:
            if output and hasattr(output, "write_raw"):
                output.write_raw(_TERMINAL_INPUT_MODE_RESET_SEQ)
                output.flush()
            elif output and hasattr(output, "write"):
                output.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
                output.flush()
            else:
                sys.stdout.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
                sys.stdout.flush()
        except Exception:
            return

        logger.warning("Recovered terminal input modes after leak: %s", reason)

    def _preprocess_images_with_vision(self, text: str, images: list, *, announce: bool = True) -> str:
        """Analyze attached images via the vision tool and return enriched text."""
        import asyncio as _asyncio
        from tools.vision_tools import vision_analyze_tool

        analysis_prompt = (
            "Describe everything visible in this image in thorough detail. "
            "Include any text, code, data, objects, people, layout, colors, "
            "and any other notable visual information."
        )

        enriched_parts = []
        for img_path in images:
            if not img_path.exists():
                continue
            size_kb = img_path.stat().st_size // 1024
            if announce:
                _cprint(f"  {_DIM}👁️  analyzing {img_path.name} ({size_kb}KB)...{_RST}")
            try:
                result_json = _asyncio.run(
                    vision_analyze_tool(image_url=str(img_path), user_prompt=analysis_prompt)
                )
                result = json.loads(result_json)
                if result.get("success"):
                    description = result.get("analysis", "")
                    enriched_parts.append(
                        f"[The user attached an image. Here's what it contains:\n{description}]\n"
                        f"[If you need a closer look, use vision_analyze with "
                        f"image_url: {img_path}]"
                    )
                    if announce:
                        _cprint(f"  {_DIM}✓ image analyzed{_RST}")
                else:
                    enriched_parts.append(
                        f"[The user attached an image but it couldn't be analyzed. "
                        f"You can try examining it with vision_analyze using "
                        f"image_url: {img_path}]"
                    )
            except Exception as e:
                enriched_parts.append(
                    f"[The user attached an image but analysis failed ({e}). "
                    f"You can try examining it with vision_analyze using "
                    f"image_url: {img_path}]"
                )

        user_text = text if isinstance(text, str) and text else ""
        if enriched_parts:
            prefix = "\n\n".join(enriched_parts)
            return f"{prefix}\n\n{user_text}" if user_text else prefix
        return user_text or "What do you see in this image?"

    def _show_tool_availability_warnings(self):
        """Show warnings about disabled tools due to missing API keys."""
        try:
            from model_tools import check_tool_availability
            available, unavailable = check_tool_availability()
            api_key_missing = [u for u in unavailable if u["missing_vars"]]
            if api_key_missing:
                self._console_print()
                self._console_print("[yellow]⚠️  Some tools disabled (missing API keys):[/]")
                for item in api_key_missing:
                    self._console_print(f"   [dim]• {item['name']}[/] [dim italic]({', '.join(item['missing_vars'])})[/]")
                self._console_print("[dim]   Run 'prostor setup' to configure[/]")
        except Exception:
            pass

    def _show_status(self):
        """Show compact startup status line."""
        from model_tools import get_tool_definitions

        if os.environ.get("PROSTOR_DEFER_AGENT_STARTUP") == "1":
            tool_status = "tools deferred"
        else:
            tools = get_tool_definitions(enabled_toolsets=self.enabled_toolsets, quiet_mode=True)
            tool_count = len(tools) if tools else 0
            tool_status = f"{tool_count} tools"

        model_short = self.model.split("/")[-1] if "/" in self.model else self.model
        if len(model_short) > 30:
            model_short = model_short[:27] + "..."

        if self.api_key:
            api_indicator = "[green bold]●[/]"
        else:
            api_indicator = "[red bold]●[/]"

        try:
            from prostor_cli.skin_engine import get_active_skin
            skin = get_active_skin()
            separator_color = skin.get_color("banner_dim", "#B8860B")
            accent_color = skin.get_color("ui_accent", "#FFBF00")
            label_color = skin.get_color("ui_label", "#DAA520")
        except Exception:
            separator_color, accent_color, label_color = "#B8860B", "#FFBF00", "cyan"

        self._console_print(
            f"  {api_indicator} [{accent_color}]{model_short}[/] "
            f"[dim {separator_color}]·[/] [bold {label_color}]{tool_status}[/]"
        )

    def _show_session_status(self):
        """Show gateway-style status for the current CLI session."""
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

        agent = getattr(self, "agent", None)
        total_tokens = getattr(agent, "session_total_tokens", 0) or 0
        provider = getattr(self, "provider", None) or "unknown"
        model = getattr(self, "model", None) or "(unknown)"

        lines = [
            "Prostor CLI Status",
            "",
            f"Session ID: {self.session_id}",
        ]
        if title:
            lines.append(f"Title: {title}")
        lines.extend([
            f"Model: {model} ({provider})",
            f"Created: {created_at.strftime('%Y-%m-%d %H:%M')}",
            f"Tokens: {total_tokens:,}",
        ])
        self._console_print("\n".join(lines), highlight=False, markup=False)

    def _fast_command_available(self) -> bool:
        try:
            from prostor_cli.models import model_supports_fast_mode
        except Exception:
            return False
        agent = getattr(self, "agent", None)
        model = getattr(agent, "model", None) or getattr(self, "model", None)
        return model_supports_fast_mode(model)

    def _command_available(self, slash_command: str) -> bool:
        if slash_command == "/fast":
            return self._fast_command_available()
        return True

    def show_help(self):
        """Display help information with categorized commands."""
        from prostor_cli.commands import COMMANDS_BY_CATEGORY

        try:
            from prostor_cli.skin_engine import get_active_help_header
            header = get_active_help_header("(^_^)? Available Commands")
        except Exception:
            header = "(^_^)? Available Commands"
        header = (header or "").strip() or "(^_^)? Available Commands"
        inner_width = 55
        if len(header) > inner_width:
            header = header[:inner_width]

        try:
            from prostor_cli.cli import _cprint, _BOLD, _RST, _DIM, _accent_hex, ChatConsole, _escape
        except ImportError:
            return

        _cprint(f"\n{_BOLD}+{'-' * inner_width}+{_RST}")
        _cprint(f"{_BOLD}|{header:^{inner_width}}|{_RST}")
        _cprint(f"{_BOLD}+{'-' * inner_width}+{_RST}")

        for category, commands in COMMANDS_BY_CATEGORY.items():
            _cprint(f"\n  {_BOLD}── {category} ──{_RST}")
            for cmd, desc in commands.items():
                if not self._command_available(cmd):
                    continue
                ChatConsole().print(f"    [bold {_accent_hex()}]{cmd:<15}[/] [dim]-[/] {_escape(desc)}")

        _cprint(f"\n  {_DIM}Tip: Just type your message to chat with Prostor!{_RST}")
        _cprint(f"  {_DIM}Multi-line: Alt+Enter for a new line{_RST}")

    def show_tools(self):
        """Display available tools with kawaii ASCII art."""
        from model_tools import get_tool_definitions, get_toolset_for_tool

        tools = get_tool_definitions(enabled_toolsets=self.enabled_toolsets, quiet_mode=True)
        if not tools:
            print("(;_;) No tools available")
            return

        print()
        title = "(^_^)/ Available Tools"
        width = 78
        pad = width - len(title)
        print("+" + "-" * width + "+")
        print("|" + " " * (pad // 2) + title + " " * (pad - pad // 2) + "|")
        print("+" + "-" * width + "+")
        print()

        toolsets = {}
        for tool in sorted(tools, key=lambda t: t["function"]["name"]):
            name = tool["function"]["name"]
            toolset = get_toolset_for_tool(name) or "unknown"
            if toolset not in toolsets:
                toolsets[toolset] = []
            desc = tool["function"].get("description", "")
            desc = desc.split("\n")[0]
            if ". " in desc:
                desc = desc[:desc.index(". ") + 1]
            toolsets[toolset].append((name, desc))

        for toolset in sorted(toolsets.keys()):
            print(f"  [{toolset}]")
            for name, desc in toolsets[toolset]:
                print(f"    * {name:<20} - {desc}")
            print()

        print(f"  Total: {len(tools)} tools  ヽ(^o^)ノ")
        print()

    def show_toolsets(self):
        """Display available toolsets with kawaii ASCII art."""
        from model_tools import get_all_toolsets, get_toolset_info

        all_toolsets = get_all_toolsets()
        print()
        title = "(^_^)b Available Toolsets"
        width = 58
        pad = width - len(title)
        print("+" + "-" * width + "+")
        print("|" + " " * (pad // 2) + title + " " * (pad - pad // 2) + "|")
        print("+" + "-" * width + "+")
        print()

        for name in sorted(all_toolsets.keys()):
            info = get_toolset_info(name)
            if info:
                tool_count = info["tool_count"]
                desc = info["description"]
                marker = "(*)" if self.enabled_toolsets and name in self.enabled_toolsets else "   "
                print(f"  {marker} {name:<18} [{tool_count:>2} tools] - {desc}")

        print()
        print("  (*) = currently enabled")
        print()

    def show_config(self):
        """Display current configuration with kawaii ASCII art."""
        terminal_env = os.getenv("TERMINAL_ENV", "local")
        terminal_cwd = os.getenv("TERMINAL_CWD", os.getcwd())
        terminal_timeout = os.getenv("TERMINAL_TIMEOUT", "60")

        from prostor_constants import get_prostor_home
        _prostor_home = get_prostor_home()
        user_config_path = _prostor_home / 'config.yaml'
        config_path = user_config_path if user_config_path.exists() else Path('cli-config.yaml')
        config_status = "(loaded)" if config_path.exists() else "(not found)"

        from agent.azure_identity_adapter import is_token_provider
        if is_token_provider(self.api_key):
            api_key_display = "Microsoft Entra ID"
        elif isinstance(self.api_key, str) and len(self.api_key) > 12:
            api_key_display = f"{self.api_key[:8]}...{self.api_key[-4:]}"
        else:
            api_key_display = "Not set!"

        print()
        title = "(^_^) Configuration"
        width = 50
        pad = width - len(title)
        print("+" + "-" * width + "+")
        print("|" + " " * (pad // 2) + title + " " * (pad - pad // 2) + "|")
        print("+" + "-" * width + "+")
        print()
        print(f"  Model:     {self.model}")
        print(f"  Base URL:  {self.base_url}")
        print(f"  API Key:   {api_key_display}")
        print()
        print(f"  Environment:  {terminal_env}")
        print(f"  Working Dir:  {terminal_cwd}")
        print(f"  Timeout:      {terminal_timeout}s")
        print()

    def _list_recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent CLI sessions for in-chat browsing/resume affordances."""
        if not self._session_db:
            return []
        try:
            from prostor_cli.session_listing import query_session_listing
            return query_session_listing(
                self._session_db,
                source="cli",
                current_session_id=self.session_id,
                include_all_sources=False,
                include_unnamed=True,
                limit=limit,
                exclude_sources=["tool"],
            )
        except Exception:
            return []

    def _show_recent_sessions(self, *, reason: str = "history", limit: int = 10) -> bool:
        """Render recent sessions inline from the active chat TUI."""
        sessions = self._list_recent_sessions(limit=limit)
        if not sessions:
            return False

        from prostor_cli.main import _relative_time

        print()
        if reason == "history":
            print("(._.) No messages in the current chat yet — here are recent sessions:")
        else:
            print("  Recent sessions:")
        print()
        print(f"  {'#':<3} {'Title':<32} {'Preview':<40} {'Last Active':<13} {'ID'}")
        print(f"  {'─' * 3} {'─' * 32} {'─' * 40} {'─' * 13} {'─' * 24}")
        for idx, session in enumerate(sessions, start=1):
            title = session.get("title") or "—"
            preview = (session.get("preview") or "")[:38]
            last_active = _relative_time(session.get("last_active"))
            print(f"  {idx:<3} {title:<32} {preview:<40} {last_active:<13} {session['id']}")
        print()
        print("  Use /resume <number>, /resume <session id>, or /resume <title> to continue.")
        print()
        return True

    def show_history(self):
        """Display conversation history."""
        if not self.conversation_history:
            if not self._show_recent_sessions(reason="history"):
                print("(._.) No conversation history yet.")
            return

        preview_limit = 400
        hidden_tool_messages = 0
        show_ts = bool(getattr(self, "show_timestamps", False))

        def _ts_suffix(message: dict) -> str:
            if not show_ts:
                return ""
            ts = message.get("timestamp")
            if not ts:
                return ""
            try:
                return f"  [{datetime.fromtimestamp(float(ts)).strftime('%H:%M')}]"
            except (ValueError, OSError, TypeError):
                return ""

        for msg in self.conversation_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "tool":
                hidden_tool_messages += 1
                continue
            if role == "user":
                text = str(content)[:preview_limit]
                print(f"  [bold]You:[/] {text}{_ts_suffix(msg)}")
            elif role == "assistant":
                text = str(content)[:preview_limit]
                if text.strip():
                    print(f"  [bold]Prostor:[/] {text}{_ts_suffix(msg)}")
            print()
