"""Gateway helper modules extracted from gateway/run.py (#23 Phase 1).

Re-exports all public names so callers can do:
    from gateway.helpers import _redact_gateway_user_facing_secrets
"""
from gateway.helpers.agent_kwargs import (
    _dispose_unused_adapter as _dispose_unused_adapter,
)
from gateway.helpers.agent_kwargs import (
    _normalize_empty_agent_response as _normalize_empty_agent_response,
)
from gateway.helpers.agent_kwargs import (
    _preserve_queued_followup_history_offset as _preserve_queued_followup_history_offset,
)
from gateway.helpers.agent_kwargs import (
    _resolve_runtime_agent_kwargs as _resolve_runtime_agent_kwargs,
)
from gateway.helpers.agent_kwargs import (
    _should_clear_resume_pending_after_turn as _should_clear_resume_pending_after_turn,
)
from gateway.helpers.agent_kwargs import (
    _try_resolve_fallback_provider as _try_resolve_fallback_provider,
)
from gateway.helpers.config import (
    _bridge_max_turns_from_config as _bridge_max_turns_from_config,
)
from gateway.helpers.config import (
    _clear_planned_restart_notification as _clear_planned_restart_notification,
)
from gateway.helpers.config import (
    _current_max_iterations as _current_max_iterations,
)
from gateway.helpers.config import (
    _drain_gateway_watch_events as _drain_gateway_watch_events,
)
from gateway.helpers.config import (
    _format_gateway_process_notification as _format_gateway_process_notification,
)
from gateway.helpers.config import (
    _home_target_env_var as _home_target_env_var,
)
from gateway.helpers.config import (
    _home_thread_env_var as _home_thread_env_var,
)
from gateway.helpers.config import (
    _load_gateway_config as _load_gateway_config,
)
from gateway.helpers.config import (
    _load_gateway_runtime_config as _load_gateway_runtime_config,
)
from gateway.helpers.config import (
    _parse_session_key as _parse_session_key,
)
from gateway.helpers.config import (
    _planned_restart_notification_path as _planned_restart_notification_path,
)
from gateway.helpers.config import (
    _planned_restart_notification_pending as _planned_restart_notification_pending,
)
from gateway.helpers.config import (
    _platform_config_key as _platform_config_key,
)
from gateway.helpers.config import (
    _profile_runtime_scope as _profile_runtime_scope,
)
from gateway.helpers.config import (
    _reload_runtime_env_preserving_config_authority as _reload_runtime_env_preserving_config_authority,
)
from gateway.helpers.config import (
    _resolve_gateway_model as _resolve_gateway_model,
)
from gateway.helpers.config import (
    _resolve_prostor_bin as _resolve_prostor_bin,
)
from gateway.helpers.config import (
    _restart_notification_pending as _restart_notification_pending,
)
from gateway.helpers.config import (
    _teams_pipeline_plugin_enabled as _teams_pipeline_plugin_enabled,
)
from gateway.helpers.errors import (
    _GATEWAY_AUTH_ERROR_RE as _GATEWAY_AUTH_ERROR_RE,
)
from gateway.helpers.errors import (
    _GATEWAY_PROVIDER_ERROR_SHAPE_RE as _GATEWAY_PROVIDER_ERROR_SHAPE_RE,
)
from gateway.helpers.errors import (
    _GATEWAY_RATE_LIMIT_RE as _GATEWAY_RATE_LIMIT_RE,
)
from gateway.helpers.errors import (
    _GATEWAY_SECRET_PATTERNS as _GATEWAY_SECRET_PATTERNS,
)
from gateway.helpers.errors import (
    _TELEGRAM_COMMAND_MENTION_RE as _TELEGRAM_COMMAND_MENTION_RE,
)
from gateway.helpers.errors import (
    _TELEGRAM_NOISY_STATUS_RE as _TELEGRAM_NOISY_STATUS_RE,
)
from gateway.helpers.errors import (
    _ensure_windows_gateway_venv_imports as _ensure_windows_gateway_venv_imports,
)
from gateway.helpers.errors import (
    _gateway_loop_exception_handler as _gateway_loop_exception_handler,
)
from gateway.helpers.errors import (
    _gateway_platform_value as _gateway_platform_value,
)
from gateway.helpers.errors import (
    _gateway_provider_error_reply as _gateway_provider_error_reply,
)
from gateway.helpers.errors import (
    _is_transient_network_error as _is_transient_network_error,
)
from gateway.helpers.errors import (
    _looks_like_gateway_provider_error as _looks_like_gateway_provider_error,
)
from gateway.helpers.errors import (
    _non_conversational_metadata as _non_conversational_metadata,
)
from gateway.helpers.errors import (
    _prepare_gateway_status_message as _prepare_gateway_status_message,
)
from gateway.helpers.errors import (
    _redact_gateway_user_facing_secrets as _redact_gateway_user_facing_secrets,
)
from gateway.helpers.errors import (
    _sanitize_gateway_final_response as _sanitize_gateway_final_response,
)
from gateway.helpers.errors import (
    _send_or_update_status_coro as _send_or_update_status_coro,
)
from gateway.helpers.errors import (
    render_notice_line as render_notice_line,
)
from gateway.helpers.history import (
    _build_gateway_agent_history as _build_gateway_agent_history,
)
from gateway.helpers.history import (
    _build_replay_entry as _build_replay_entry,
)
from gateway.helpers.history import (
    _last_transcript_timestamp as _last_transcript_timestamp,
)
from gateway.helpers.history import (
    _message_timestamps_enabled as _message_timestamps_enabled,
)
from gateway.helpers.history import (
    _uses_telegram_observed_group_context as _uses_telegram_observed_group_context,
)
from gateway.helpers.history import (
    _wrap_current_message_with_observed_context as _wrap_current_message_with_observed_context,
)
from gateway.helpers.media import (
    _build_document_context_note as _build_document_context_note,
)
from gateway.helpers.media import (
    _build_media_placeholder as _build_media_placeholder,
)
from gateway.helpers.media import (
    _collect_auto_append_media_tags as _collect_auto_append_media_tags,
)
from gateway.helpers.media import (
    _format_duration as _format_duration,
)
from gateway.helpers.media import (
    _probe_audio_duration as _probe_audio_duration,
)
from gateway.helpers.platform_display import (
    _auto_continue_freshness_window as _auto_continue_freshness_window,
)
from gateway.helpers.platform_display import (
    _coerce_gateway_timestamp as _coerce_gateway_timestamp,
)
from gateway.helpers.platform_display import (
    _float_env as _float_env,
)
from gateway.helpers.platform_display import (
    _has_platform_display_override as _has_platform_display_override,
)
from gateway.helpers.platform_display import (
    _is_fresh_gateway_interruption as _is_fresh_gateway_interruption,
)
from gateway.helpers.platform_display import (
    _resolve_gateway_display_bool as _resolve_gateway_display_bool,
)
from gateway.helpers.platform_display import (
    _resolve_progress_thread_id as _resolve_progress_thread_id,
)
from gateway.helpers.skills_commands import (
    _check_unavailable_skill as _check_unavailable_skill,
)
from gateway.helpers.skills_commands import (
    _dequeue_pending_event as _dequeue_pending_event,
)
from gateway.helpers.skills_commands import (
    _is_control_interrupt_message as _is_control_interrupt_message,
)
from gateway.helpers.skills_commands import (
    _skill_slug_from_frontmatter as _skill_slug_from_frontmatter,
)
from gateway.helpers.tool_results import (
    _is_auto_continue_noise as _is_auto_continue_noise,
)
from gateway.helpers.tool_results import (
    _is_interrupted_tool_result as _is_interrupted_tool_result,
)
from gateway.helpers.tool_results import (
    _strip_auto_continue_noise as _strip_auto_continue_noise,
)
from gateway.helpers.tool_results import (
    _strip_dangling_tool_call_tail as _strip_dangling_tool_call_tail,
)
from gateway.helpers.tool_results import (
    _strip_interrupted_tool_tails as _strip_interrupted_tool_tails,
)
