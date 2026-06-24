"""Restart-related mixin for GatewayRunner.

Extracted from gateway/run.py (Issue #23 god-file refactor) to isolate the
9 methods that manage gateway restart lifecycle — drain-timeout loading,
restart-failure counting, detached/systemd restart launchers, the
in-chat ``request_restart`` entry point, stale-redelivery detection,
restart-back-online notification, and the SIGUSR1 signal handler.

All methods are defined on GatewayRunner via mixin inheritance; ``self``
refers to the GatewayRunner instance and accesses shared state
(``self.adapters``, ``self.config``, ``self.session_store``, etc.).
``restart_signal_handler`` is a ``@staticmethod`` that receives the runner
explicitly so it can be installed as a bare signal callback from
``start_gateway``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
import time
from pathlib import Path

from prostor_core import get_prostor_home
from prostor_cli.config import cfg_get
from utils import atomic_json_write

from gateway.config import Platform
from gateway.helpers import _load_gateway_runtime_config, _non_conversational_metadata, _resolve_prostor_bin
from gateway.platforms.base import MessageEvent
from gateway.restart import DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT, parse_restart_drain_timeout

logger = logging.getLogger(__name__)

_prostor_home = get_prostor_home()


class GatewayRestartMixin:
    """Restart lifecycle management — extracted from GatewayRunner."""

    @staticmethod
    def _load_restart_drain_timeout() -> float:
        """Load graceful gateway restart/stop drain timeout in seconds."""
        raw = os.getenv("PROSTOR_RESTART_DRAIN_TIMEOUT", "").strip()
        if not raw:
            cfg = _load_gateway_runtime_config()
            raw = str(cfg_get(cfg, "agent", "restart_drain_timeout", default="") or "").strip()
        value = parse_restart_drain_timeout(raw)
        if raw and value == DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT:
            try:
                float(raw)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid restart_drain_timeout '%s', using default %.0fs",
                    raw,
                    DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT,
                )
        return value

    def _increment_restart_failure_counts(self, active_session_keys: set) -> None:
        """Increment restart-failure counters for sessions active at shutdown.

        Persists to a JSON file so counters survive across restarts.
        Sessions NOT in active_session_keys are removed (they completed
        successfully, so the loop is broken).
        """
        import json

        path = _prostor_home / self._STUCK_LOOP_FILE
        try:
            counts = json.loads(path.read_text()) if path.exists() else {}
        except Exception:
            counts = {}

        # Increment active sessions, remove inactive ones (loop broken)
        new_counts = {}
        for key in active_session_keys:
            new_counts[key] = counts.get(key, 0) + 1
        # Keep any entries that are still above 0 even if not active now
        # (they might become active again next restart)

        try:
            atomic_json_write(path, new_counts, indent=None)
        except Exception:
            pass

    def _clear_restart_failure_count(self, session_key: str) -> None:
        """Clear the restart-failure counter for a session that completed OK.

        Called after a successful agent turn to signal the loop is broken.
        """
        import json

        path = _prostor_home / self._STUCK_LOOP_FILE
        if not path.exists():
            return
        try:
            counts = json.loads(path.read_text())
            if session_key in counts:
                del counts[session_key]
                if counts:
                    atomic_json_write(path, counts, indent=None)
                else:
                    path.unlink(missing_ok=True)
        except Exception:
            pass

    async def _launch_detached_restart_command(self) -> None:
        import shutil
        import subprocess

        prostor_cmd = _resolve_prostor_bin()
        if not prostor_cmd:
            logger.error("Could not locate prostor binary for detached /restart")
            return

        current_pid = os.getpid()

        # On Windows there's no bash/setsid chain — spawn a tiny Python
        # watcher directly via sys.executable instead.  The watcher polls
        # current_pid, waits for our exit, then runs `prostor gateway
        # restart` with detach flags so the respawn survives the CLI
        # that triggered the /restart command closing its console.
        if sys.platform == "win32":
            import textwrap

            from prostor_cli._subprocess_compat import windows_detach_popen_kwargs

            cmd_argv = [*prostor_cmd, "gateway", "restart"]
            watcher = textwrap.dedent(
                """
                import os, subprocess, sys, time
                pid = int(sys.argv[1])
                cmd = sys.argv[2:]
                deadline = time.monotonic() + 120

                def _alive(p):
                    # On Windows, os.kill(pid, 0) is NOT a no-op — it maps to
                    # GenerateConsoleCtrlEvent(0, pid) (bpo-14484). Use the
                    # Win32 handle-based existence check instead.
                    if os.name == 'nt':
                        import ctypes
                        k32 = ctypes.windll.kernel32
                        k32.OpenProcess.restype = ctypes.c_void_p
                        k32.WaitForSingleObject.restype = ctypes.c_uint
                        k32.GetLastError.restype = ctypes.c_uint
                        h = k32.OpenProcess(0x1000 | 0x100000, False, int(p))
                        if not h:
                            return k32.GetLastError() != 87
                        try:
                            return k32.WaitForSingleObject(h, 0) == 0x102
                        finally:
                            k32.CloseHandle(h)
                    try:
                        os.kill(int(p), 0)
                        return True
                    except ProcessLookupError:
                        return False
                    except PermissionError:
                        return True
                    except OSError:
                        return False

                while time.monotonic() < deadline:
                    if not _alive(pid):
                        break
                    time.sleep(0.2)
                _CREATE_NEW_PROCESS_GROUP = 0x00000200
                _DETACHED_PROCESS = 0x00000008
                _CREATE_NO_WINDOW = 0x08000000
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_CREATE_NEW_PROCESS_GROUP | _DETACHED_PROCESS | _CREATE_NO_WINDOW,
                )
                """
            ).strip()
            watcher_env = os.environ.copy()
            # This watcher is intentionally outside the running gateway. If it
            # inherits the gateway marker, `prostor gateway restart` refuses to
            # run as a self-restart loop guard and the gateway stays stopped.
            watcher_env.pop("_PROSTOR_GATEWAY", None)
            project_root = Path(__file__).resolve().parent.parent
            venv_dir = Path(watcher_env.get("VIRTUAL_ENV") or project_root / "venv")
            site_packages = venv_dir / "Lib" / "site-packages"
            if site_packages.exists():
                watcher_env["VIRTUAL_ENV"] = str(venv_dir)
                pythonpath = [str(project_root), str(site_packages)]
                if watcher_env.get("PYTHONPATH"):
                    pythonpath.append(watcher_env["PYTHONPATH"])
                watcher_env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath))
            subprocess.Popen(
                [sys.executable, "-c", watcher, str(current_pid), *cmd_argv],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=watcher_env,
                **windows_detach_popen_kwargs(),
            )
            return

        cmd = " ".join(shlex.quote(part) for part in prostor_cmd)
        shell_cmd = (
            f"while kill -0 {current_pid} 2>/dev/null; do sleep 0.2; done; "
            f"{cmd} gateway restart"
        )
        # Same marker scrub as the Windows watcher above: this watcher runs
        # `prostor gateway restart` from outside the gateway, but it inherits
        # _PROSTOR_GATEWAY=1 from us, and the CLI's self-restart loop guard
        # refuses to run when that marker is set — silently (DEVNULL), so the
        # gateway stops and never comes back.
        watcher_env = os.environ.copy()
        watcher_env.pop("_PROSTOR_GATEWAY", None)
        setsid_bin = shutil.which("setsid")
        if setsid_bin:
            subprocess.Popen(
                [setsid_bin, "bash", "-lc", shell_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=watcher_env,
                start_new_session=True,
            )
        else:
            subprocess.Popen(
                ["bash", "-lc", shell_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=watcher_env,
                start_new_session=True,
            )

    def _launch_systemd_restart_shortcut(self) -> None:
        """Best-effort helper to bypass systemd's automatic restart delay.

        For planned in-chat restarts, the gateway exits cleanly so systemd does
        not record a failure.  However, units with RestartSteps still count
        automatic restarts and can delay repeated /restart tests.  A transient
        user service survives our cgroup teardown and explicitly starts the
        gateway as soon as this PID exits, while the unit keeps its normal
        backoff for real crash loops.
        """
        if sys.platform != "linux" or not os.environ.get("INVOCATION_ID"):
            return

        try:
            import shutil
            import subprocess

            systemd_run = shutil.which("systemd-run")
            systemctl = shutil.which("systemctl")
            if not systemd_run or not systemctl:
                return

            try:
                from prostor_cli.gateway import get_service_name

                service_name = get_service_name()
            except Exception:
                service_name = "prostor-gateway"

            current_pid = os.getpid()
            show = subprocess.run(
                [
                    systemctl,
                    "--user",
                    "show",
                    service_name,
                    "--property=MainPID",
                    "--value",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if (show.stdout or "").strip() != str(current_pid):
                return

            systemctl_user = "systemctl --user"
            service_arg = shlex.quote(service_name)
            shell_cmd = (
                f"while kill -0 {current_pid} 2>/dev/null; do sleep 0.2; done; "
                f"{systemctl_user} reset-failed {service_arg}; "
                f"{systemctl_user} restart {service_arg}"
            )
            unit_name = f"{service_name}-planned-restart-{current_pid}".replace(".", "-")
            subprocess.Popen(
                [
                    systemd_run,
                    "--user",
                    "--collect",
                    "--unit",
                    unit_name,
                    "/bin/sh",
                    "-lc",
                    shell_cmd,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info(
                "Launched systemd planned-restart helper for %s (pid=%s)",
                service_name,
                current_pid,
            )
        except Exception as e:
            logger.debug("Failed to launch systemd planned-restart helper: %s", e)

    def request_restart(self, *, detached: bool = False, via_service: bool = False) -> bool:
        if self._restart_task_started:
            return False
        self._restart_requested = True
        self._restart_detached = detached
        self._restart_via_service = via_service
        self._restart_task_started = True

        async def _run_restart() -> None:
            await asyncio.sleep(0.05)
            await self.stop(restart=True, detached_restart=detached, service_restart=via_service)

        task = asyncio.create_task(_run_restart())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return True

    def _is_stale_restart_redelivery(self, event: MessageEvent) -> bool:
        """Return True if this /restart is a Telegram re-delivery we already handled.

        The previous gateway wrote ``.restart_last_processed.json`` with the
        triggering platform + update_id when it processed the /restart.  If
        we now see a /restart on the same platform with an update_id <= that
        recorded value AND the marker is recent (< 5 minutes), it's a
        redelivery and should be ignored.

        Only applies to Telegram today (the only platform that exposes a
        numeric cross-session update ordering); other platforms return False.
        """
        if event is None or event.source is None:
            return False
        if event.platform_update_id is None:
            return False
        if event.source.platform is None:
            return False
        # Only Telegram populates platform_update_id currently; be explicit
        # so future platforms aren't accidentally gated by this check.
        try:
            platform_value = event.source.platform.value
        except Exception:
            return False
        if platform_value != "telegram":
            return False

        try:
            marker_path = _prostor_home / ".restart_last_processed.json"
            if not marker_path.exists():
                return False
            data = json.loads(marker_path.read_text())
        except Exception:
            return False

        if data.get("platform") != platform_value:
            return False
        recorded_uid = data.get("update_id")
        if not isinstance(recorded_uid, int):
            return False
        # Staleness guard: ignore markers older than 5 minutes.  A legitimately
        # old marker (e.g. crash recovery where notify never fired) should not
        # swallow a fresh /restart from the user.
        requested_at = data.get("requested_at")
        if isinstance(requested_at, (int, float)):
            if time.time() - requested_at > 300:
                return False
        return event.platform_update_id <= recorded_uid

    async def _send_restart_notification(self) -> tuple[str, str, str | None] | None:
        """Notify the chat that initiated /restart that the gateway is back."""
        notify_path = _prostor_home / ".restart_notify.json"
        if not notify_path.exists():
            return None

        try:
            data = json.loads(notify_path.read_text())
            platform_str = data.get("platform")
            chat_id = data.get("chat_id")
            chat_type = data.get("chat_type")
            thread_id = data.get("thread_id")
            message_id = data.get("message_id")

            if not platform_str or not chat_id:
                return None

            platform = Platform(platform_str)
            adapter = self.adapters.get(platform)
            if not adapter:
                logger.debug(
                    "Restart notification skipped: %s adapter not connected",
                    platform_str,
                )
                return None

            platform_cfg = self.config.platforms.get(platform)
            if platform_cfg is not None and not platform_cfg.gateway_restart_notification:
                logger.info(
                    "Restart notification suppressed: %s has gateway_restart_notification=false",
                    platform_str,
                )
                return None

            metadata = self._thread_metadata_for_target(
                platform,
                chat_id,
                thread_id,
                chat_type=chat_type,
                reply_to_message_id=message_id,
                adapter=adapter,
            )
            result = await adapter.send(
                str(chat_id),
                "♻ Gateway restarted successfully. Your session continues.",
                metadata=_non_conversational_metadata(metadata, platform=platform),
            )
            # adapter.send() catches provider errors (e.g. "Chat not found")
            # and returns SendResult(success=False) rather than raising, so
            # we must inspect the result before claiming success — otherwise
            # the log line is misleading and hides real delivery failures.
            if result is not None and getattr(result, "success", True) is False:
                logger.warning(
                    "Restart notification to %s:%s was not delivered: %s",
                    platform_str,
                    chat_id,
                    getattr(result, "error", "send returned success=False"),
                )
                return None

            logger.info(
                "Sent restart notification to %s:%s",
                platform_str,
                chat_id,
            )
            return str(platform_str), str(chat_id), str(thread_id) if thread_id else None
        except Exception as e:
            logger.warning("Restart notification failed: %s", e)
            return None
        finally:
            notify_path.unlink(missing_ok=True)

    @staticmethod
    def restart_signal_handler(runner: "GatewayRestartMixin") -> None:
        runner.request_restart(detached=False, via_service=True)