"""Gateway helper modules extracted from gateway/run.py (#23 Phase 1).

Re-exports all public names so callers can do:
    from gateway.helpers import _redact_gateway_user_facing_secrets
"""
from gateway.helpers.errors import (
    _GATEWAY_AUTH_ERROR_RE,
    _GATEWAY_RATE_LIMIT_RE,
    _GATEWAY_SECRET_PATTERNS,
    _GATEWAY_PROVIDER_ERROR_SHAPE_RE,
    _TELEGRAM_NOISY_STATUS_RE,
    _TELEGRAM_COMMAND_MENTION_RE,
    _ensure_windows_gateway_venv_imports,
    _gateway_platform_value,
    _non_conversational_metadata,
    _is_transient_network_error,
    _gateway_loop_exception_handler,
    _redact_gateway_user_facing_secrets,
    _gateway_provider_error_reply,
    _looks_like_gateway_provider_error,
    _sanitize_gateway_final_response,
    _prepare_gateway_status_message,
    render_notice_line,
    _send_or_update_status_coro,
)
from gateway.helpers.platform_display import (
    _resolve_progress_thread_id,
    _has_platform_display_override,
    _resolve_gateway_display_bool,
    _coerce_gateway_timestamp,
    _auto_continue_freshness_window,
    _float_env,
    _is_fresh_gateway_interruption,
)
from gateway.helpers.history import (
    _build_replay_entry,
    _uses_telegram_observed_group_context,
    _message_timestamps_enabled,
    _build_gateway_agent_history,
    _wrap_current_message_with_observed_context,
    _last_transcript_timestamp,
)
from gateway.helpers.tool_results import (
    _is_interrupted_tool_result,
    _strip_interrupted_tool_tails,
    _strip_dangling_tool_call_tail,
    _is_auto_continue_noise,
    _strip_auto_continue_noise,
)
from gateway.helpers.media import (
    _build_media_placeholder,
    _build_document_context_note,
    _format_duration,
    _probe_audio_duration,
    _collect_auto_append_media_tags,
)
from gateway.helpers.config import (
    _home_target_env_var,
    _home_thread_env_var,
    _restart_notification_pending,
    _planned_restart_notification_path,
    _planned_restart_notification_pending,
    _clear_planned_restart_notification,
    _reload_runtime_env_preserving_config_authority,
    _bridge_max_turns_from_config,
    _current_max_iterations,
    _profile_runtime_scope,
    _platform_config_key,
    _teams_pipeline_plugin_enabled,
    _load_gateway_config,
    _load_gateway_runtime_config,
    _resolve_gateway_model,
    _resolve_prostor_bin,
    _parse_session_key,
    _format_gateway_process_notification,
    _drain_gateway_watch_events,
)
from gateway.helpers.skills_commands import (
    _dequeue_pending_event,
    _is_control_interrupt_message,
    _skill_slug_from_frontmatter,
    _check_unavailable_skill,
)
from gateway.helpers.agent_kwargs import (
    _resolve_runtime_agent_kwargs,
    _try_resolve_fallback_provider,
    _normalize_empty_agent_response,
    _should_clear_resume_pending_after_turn,
    _preserve_queued_followup_history_offset,
    _dispose_unused_adapter,
)
