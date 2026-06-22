"""Config loading, notifications, env vars.
Extracted from gateway/run.py (#23).
"""
from __future__ import annotations
import logging, os
from pathlib import Path
from typing import Any, Dict, Optional
logger = logging.getLogger(__name__)

def _home_target_env_var(platform_name: str) -> str:
    """Return the configured home-target env var for a platform.

    Consults built-in ``_HOME_TARGET_ENV_VARS`` first, then the plugin
    registry via ``cron.scheduler._resolve_home_env_var``, then falls back
    to ``<PLATFORM>_HOME_CHANNEL`` for unknown names.
    """
    from cron.scheduler import _resolve_home_env_var

    resolved = _resolve_home_env_var(platform_name)
    if resolved:
        return resolved
    return f"{platform_name.upper()}_HOME_CHANNEL"


def _home_thread_env_var(platform_name: str) -> str:
    """Return the optional thread/topic env var for a platform home target."""
    return f"{_home_target_env_var(platform_name)}_THREAD_ID"


def _restart_notification_pending() -> bool:
    """Return True when a /restart completion marker is waiting to be delivered."""
    return (_prostor_home / ".restart_notify.json").exists()


def _planned_restart_notification_path() -> Path:
    return _prostor_home / ".restart_pending.json"


def _planned_restart_notification_pending() -> bool:
    """Return True when a non-chat planned restart should notify home channels."""
    return _planned_restart_notification_path().exists()


def _clear_planned_restart_notification() -> None:
    _planned_restart_notification_path().unlink(missing_ok=True)


def _reload_runtime_env_preserving_config_authority() -> None:
    """Reload .env for fresh credentials without letting stale .env override config.

    Gateway processes are long-lived, so per-turn code reloads ~/.prostor/.env to
    pick up rotated API keys. config.yaml remains authoritative for agent budget
    settings such as agent.max_turns; otherwise a stale PROSTOR_MAX_ITERATIONS in
    .env can replace the startup bridge on later turns.

    In multiplex mode this is a NO-OP for the credential reload: secrets come
    from the per-turn ``set_secret_scope`` (installed by ``_profile_runtime_scope``)
    which loads the routed profile's ``.env`` into an isolated mapping. Mutating
    the process-global ``os.environ`` here would defeat that isolation and leak
    the default profile's keys to every profile's turns and subprocesses.
    """
    from agent.secret_scope import is_multiplex_active
    if is_multiplex_active():
        # Credentials are resolved from the active profile's secret scope, not
        # os.environ. Still honor config.yaml's agent.max_turns bridge below
        # using the scoped home, but never reload .env into global env.
        _bridge_max_turns_from_config(_prostor_home)
        return

    load_prostor_dotenv(
        prostor_home=_prostor_home,
        project_env=Path(__file__).resolve().parents[1] / '.env',
    )
    _bridge_max_turns_from_config(_prostor_home)


def _bridge_max_turns_from_config(home: "Path") -> None:
    """Bridge config.yaml agent.max_turns into PROSTOR_MAX_ITERATIONS (a global)."""
    config_path = home / 'config.yaml'
    if not config_path.exists():
        return
    try:
        import yaml as _yaml
        with open(config_path, encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        from prostor_cli.config import _expand_env_vars
        cfg = _expand_env_vars(cfg)
        # Managed scope: keep administrator-pinned values authoritative on every
        # turn too. This per-turn reload re-bridges config→env, so without the
        # overlay a managed agent.max_turns / timezone / redact_secrets would be
        # replaced by the user's value after the first turn. Fail-open.
        try:
            from prostor_cli import managed_scope
            cfg = managed_scope.apply_managed_overlay(cfg)
        except Exception:
            pass
    except Exception:
        return

    agent_cfg = cfg.get("agent", {})
    if isinstance(agent_cfg, dict) and "max_turns" in agent_cfg:
        os.environ["PROSTOR_MAX_ITERATIONS"] = str(agent_cfg["max_turns"])


def _current_max_iterations() -> int:
    """Return the current per-turn iteration budget after runtime env refresh."""
    _reload_runtime_env_preserving_config_authority()
    try:
        return int(os.getenv("PROSTOR_MAX_ITERATIONS", "90"))
    except (TypeError, ValueError):
        return 90


from contextlib import contextmanager as _contextmanager


# Platforms that bind a host TCP port (HTTP/webhook listeners). In a profile
# multiplexer the default profile owns the single shared listener and serves
# every profile through the /p/<profile>/ URL prefix, so a SECONDARY profile
# enabling one of these is always a misconfiguration: it would try to bind a
# port already held by the default's listener. We hard-error on it rather than
# silently dropping the adapter (see _start_one_profile_adapters).
# Stored as platform .value strings since the Platform enum is imported below.
_PORT_BINDING_PLATFORM_VALUES = frozenset({
    "webhook",
    "api_server",
    "msgraph_webhook",
    "feishu",
    "wecom_callback",
    "bluebubbles",
    "sms",
})


class MultiplexConfigError(RuntimeError):
    """A profile multiplexer config is invalid (fail-fast at startup).

    Distinct from a transient adapter-connect failure: a transient error is
    logged and the gateway stays alive to retry, but a config error means the
    operator must fix config.yaml, so it aborts startup cleanly.
    """


@_contextmanager
def _profile_runtime_scope(profile_home: "Path"):
    """Scope config/skills/memory AND credentials to a profile for one turn.

    Combines the two seams the multiplexer needs:
      1. ``set_prostor_home_override`` — redirects ``get_prostor_home()`` (config,
         skills, memory, SOUL, sessions) to the profile's home. Contextvar, so
         it propagates into the agent worker thread via ``copy_context()``.
      2. ``set_secret_scope`` — installs the profile's ``.env`` secrets as the
         authoritative credential source, so ``get_secret`` reads this profile's
         keys and never the process-global ``os.environ`` (which in a
         multiplexer may hold another profile's values).

    Only used on the multiplexed inbound path. Single-profile gateways never
    enter this scope, so their behavior is unchanged. Loading the profile's
    ``.env`` here does NOT mutate ``os.environ`` — ``build_profile_secret_scope``
    returns an isolated dict — which is what keeps subprocesses (MCP, kanban)
    from inheriting cross-profile secrets.
    """
    from prostor_constants import set_prostor_home_override, reset_prostor_home_override
    from agent.secret_scope import (
        build_profile_secret_scope,
        set_secret_scope,
        reset_secret_scope,
    )

    home_token = set_prostor_home_override(str(profile_home))
    secret_token = set_secret_scope(build_profile_secret_scope(Path(profile_home)))
    try:
        yield
    finally:
        reset_secret_scope(secret_token)
        reset_prostor_home_override(home_token)


def _platform_config_key(platform: "Platform") -> str:
    """Map a Platform enum to its config.yaml key (LOCAL→"cli", rest→enum value)."""
    return "cli" if platform == Platform.LOCAL else platform.value


def _teams_pipeline_plugin_enabled() -> bool:
    """Return True when the standalone Teams pipeline plugin is enabled."""
    config = _load_gateway_config()
    enabled = cfg_get(config, "plugins", "enabled", default=[])
    if not isinstance(enabled, list):
        return False
    return "teams_pipeline" in enabled or "teams-pipeline" in enabled


def _load_gateway_config() -> dict:
    """Load and parse ~/.prostor/config.yaml, returning {} on any error.

    Uses the module-level ``_prostor_home`` (so tests that monkeypatch it
    still see their fixture) and shares the mtime-keyed raw-yaml cache
    from ``prostor_cli.config.read_raw_config`` when the paths match.

    Managed scope is overlaid on the result (via the shared helper) so the
    gateway honors administrator-pinned values — neither read_raw_config nor a
    direct yaml.safe_load carries the managed merge on its own. Fail-open.
    """
    config_path = _prostor_home / 'config.yaml'
    raw: dict = {}
    used_canonical = False
    try:
        from prostor_cli.config import get_config_path, read_raw_config
        # Fast path: if _prostor_home agrees with the canonical config
        # location, reuse the shared cache. Otherwise fall through to a
        # direct read (keeps test fixtures with a monkeypatched
        # _prostor_home working).
        if config_path == get_config_path():
            raw = read_raw_config()
            used_canonical = True
    except Exception:
        pass

    if not used_canonical:
        try:
            if config_path.exists():
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    raw = yaml.safe_load(f) or {}
        except Exception:
            logger.debug("Could not load gateway config from %s", config_path)
            raw = {}

    # Overlay managed scope. read_raw_config() returns the user's raw YAML
    # WITHOUT the managed merge (that lives in load_config/_load_config_impl),
    # so the overlay is required on both paths for the gateway to honor pinned
    # values. Helper is fail-open and a no-op when no managed scope exists.
    try:
        from prostor_cli import managed_scope
        raw = managed_scope.apply_managed_overlay(raw if isinstance(raw, dict) else {})
    except Exception:
        pass
    return raw if isinstance(raw, dict) else {}


def _load_gateway_runtime_config() -> dict:
    """Load gateway config for runtime reads, expanding supported ``${VAR}`` refs.

    Runtime helpers should honor the same env-template expansion documented for
    ``config.yaml`` while still respecting tests that monkeypatch
    ``gateway.run._prostor_home``. Build on ``_load_gateway_config()`` rather
    than calling the canonical loader directly so both behaviors stay aligned.

    Expansion failures are intentionally NOT swallowed — silently returning
    the unexpanded dict would mask the very bug this helper exists to fix.
    """
    cfg = _load_gateway_config()
    if not isinstance(cfg, dict) or not cfg:
        return {}
    from prostor_cli.config import _expand_env_vars

    expanded = _expand_env_vars(cfg)
    return expanded if isinstance(expanded, dict) else {}


def _resolve_gateway_model(config: dict | None = None) -> str:
    """Read model from config.yaml — single source of truth.

    Without this, temporary AIAgent instances (e.g. /compress) fall
    back to the hardcoded default which fails when the active provider is
    openai-codex.
    """
    cfg = config if config is not None else _load_gateway_config()
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, str):
        return model_cfg
    elif isinstance(model_cfg, dict):
        return model_cfg.get("default") or model_cfg.get("model") or ""
    return ""


def _resolve_prostor_bin() -> Optional[list[str]]:
    """Resolve the Prostor update command as argv parts.

    Tries in order:
    1. ``shutil.which("prostor")`` — standard PATH lookup
    2. ``sys.executable -m prostor_cli.main`` — fallback when Prostor is running
       from a venv/module invocation and the ``prostor`` shim is not on PATH

    Returns argv parts ready for quoting/joining, or ``None`` if neither works.
    """
    import shutil

    prostor_bin = shutil.which("prostor")
    if prostor_bin:
        return [prostor_bin]

    try:
        import importlib.util

        if importlib.util.find_spec("prostor_cli") is not None:
            return [sys.executable, "-m", "prostor_cli.main"]
    except Exception:
        pass

    return None


def _parse_session_key(session_key: str) -> "dict | None":
    """Parse a session key into its component parts.

    Session keys follow the format
    ``agent:main:{platform}:{chat_type}:{chat_id}[:{extra}...]``.
    Returns a dict with ``platform``, ``chat_type``, ``chat_id``, and
    optionally ``thread_id`` keys, or None if the key doesn't match.

    The 6th element is only returned as ``thread_id`` for chat types where
    it is unambiguous (``dm`` and ``thread``).  For group/channel sessions
    the suffix may be a user_id (per-user isolation) rather than a
    thread_id, so we leave ``thread_id`` out to avoid mis-routing.
    """
    parts = session_key.split(":")
    if len(parts) >= 5 and parts[0] == "agent" and parts[1] == "main":
        result = {
            "platform": parts[2],
            "chat_type": parts[3],
            "chat_id": parts[4],
        }
        if len(parts) > 5 and parts[3] in {"dm", "thread"}:
            result["thread_id"] = parts[5]
        return result
    return None


def _format_gateway_process_notification(evt: dict) -> "str | None":
    """Format a watch pattern event from completion_queue into a [IMPORTANT:] message."""
    evt_type = evt.get("type", "completion")
    _sid = evt.get("session_id", "unknown")
    _cmd = evt.get("command", "unknown")

    if evt_type == "watch_disabled":
        return f"[IMPORTANT: {evt.get('message', '')}]"

    if evt_type == "watch_match":
        _pat = evt.get("pattern", "?")
        _out = evt.get("output", "")
        _sup = evt.get("suppressed", 0)
        text = (
            f"[IMPORTANT: Background process {_sid} matched "
            f"watch pattern \"{_pat}\".\n"
            f"Command: {_cmd}\n"
            f"Matched output:\n{_out}"
        )
        if _sup:
            text += f"\n({_sup} earlier matches were suppressed by rate limit)"
        text += "]"
        return text

    if evt_type == "async_delegation":
        # Reuse the shared rich formatter (self-contained task-source block).
        from tools.process_registry import format_process_notification
        return format_process_notification(evt)

    return None


def _drain_gateway_watch_events(completion_queue) -> "list[dict]":
    """Drain gateway-owned watch events without spinning on requeued events.

    Watch events are handled by the post-turn gateway drain. Process
    completions are owned by their per-process watcher task, and async
    delegation completions are owned by ``_async_delegation_watcher``.
    Requeueing async events inside ``while not queue.empty()`` would make the
    loop non-terminating, so detach the current batch first, then requeue any
    events this drain does not own after the queue is empty.
    """
    watch_events: list[dict] = []
    requeue: list[dict] = []
    while not completion_queue.empty():
        try:
            evt = completion_queue.get_nowait()
        except Exception:
            break
        evt_type = evt.get("type", "completion")
        if evt_type in {"watch_match", "watch_disabled"}:
            watch_events.append(evt)
        elif evt_type == "async_delegation":
            requeue.append(evt)
        # else: process completion events are handled by the watcher task
    for evt in requeue:
        completion_queue.put(evt)
    return watch_events
