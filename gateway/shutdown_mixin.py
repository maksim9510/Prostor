"""Shutdown/drain mixin for GatewayRunner.

Extracted from gateway/run.py (Issue #23 god-file refactor) to isolate the
methods that manage graceful shutdown — agent draining, interruption,
shutdown notifications, resource cleanup, startup-restore queue draining,
and the shutdown-event waiter.

All methods are defined on GatewayRunner via mixin inheritance; ``self``
refers to the GatewayRunner instance and accesses shared state
(``self._running_agents``, ``self.adapters``, ``self.config``, etc.).

Module-level helpers from ``gateway.run`` (``_AGENT_PENDING_SENTINEL``,
``_parse_session_key``) are imported lazily inside method bodies to avoid a
circular import, following the same pattern used by ``gateway.slash_commands``
and ``gateway.authz_mixin``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from gateway.config import Platform

logger = logging.getLogger(__name__)


class GatewayShutdownMixin:
    """Shutdown/drain lifecycle management — extracted from GatewayRunner."""

    def _queue_during_drain_enabled(self) -> bool:
        # Both "queue" and "steer" modes imply the user doesn't want messages
        # to be lost during restart — queue them for the newly-spawned gateway
        # process to pick up.  "interrupt" mode drops them (current behaviour).
        return self._restart_requested and self._busy_input_mode in {"queue", "steer"}

    async def _drain_active_agents(self, timeout: float) -> tuple[dict[str, Any], bool]:
        snapshot = self._snapshot_running_agents()
        last_active_count = self._running_agent_count()
        last_status_at = 0.0

        def _maybe_update_status(force: bool = False) -> None:
            nonlocal last_active_count, last_status_at
            now = asyncio.get_running_loop().time()
            active_count = self._running_agent_count()
            if force or active_count != last_active_count or (now - last_status_at) >= 1.0:
                self._update_runtime_status("draining")
                last_active_count = active_count
                last_status_at = now

        if not self._running_agents:
            _maybe_update_status(force=True)
            return snapshot, False

        _maybe_update_status(force=True)
        if timeout <= 0:
            return snapshot, True

        deadline = asyncio.get_running_loop().time() + timeout
        while self._running_agents and asyncio.get_running_loop().time() < deadline:
            _maybe_update_status()
            await asyncio.sleep(0.1)
        timed_out = bool(self._running_agents)
        _maybe_update_status(force=True)
        return snapshot, timed_out

    def _interrupt_running_agents(self, reason: str) -> None:
        from gateway.run import _AGENT_PENDING_SENTINEL

        for session_key, agent in list(self._running_agents.items()):
            if agent is _AGENT_PENDING_SENTINEL:
                continue
            try:
                agent.interrupt(reason)
                logger.debug("Interrupted running agent for session %s during shutdown", session_key)
            except Exception as e:
                logger.debug("Failed interrupting agent during shutdown: %s", e)

    async def _notify_active_sessions_of_shutdown(self) -> None:
        """Send shutdown/restart notifications to active chats and home channels.

        Called at the very start of stop() — adapters are still connected so
        messages can be delivered. Best-effort: individual send failures are
        logged and swallowed so they never block the shutdown sequence.
        """
        from gateway.helpers import _parse_session_key

        active = self._snapshot_running_agents()
        restart_source = self._restart_command_source if self._restart_requested else None

        action = "restarting" if self._restart_requested else "shutting down"
        hint = (
            "Your current task will be interrupted. "
            "Send any message after restart and I'll try to resume where you left off."
            if self._restart_requested
            else "Your current task will be interrupted."
        )
        msg = f"⚠️ Gateway {action} — {hint}"

        notified: set[tuple[str, str, str | None]] = set()
        for session_key in active:
            source = None
            try:
                if getattr(self, "session_store", None) is not None:
                    self.session_store._ensure_loaded()
                    entry = self.session_store._entries.get(session_key)
                    source = getattr(entry, "origin", None) if entry else None
            except Exception as e:
                logger.debug(
                    "Failed to load session origin for shutdown notification %s: %s",
                    session_key,
                    e,
                )

            if source is None:
                source = self._get_cached_session_source(session_key)

            if source is not None:
                platform_str = source.platform.value
                chat_id = str(source.chat_id)
                thread_id = source.thread_id
            else:
                # Fall back to parsing the session key when no persisted
                # origin is available (legacy sessions/tests).
                _parsed = _parse_session_key(session_key)
                if not _parsed:
                    continue
                platform_str = _parsed["platform"]
                chat_id = _parsed["chat_id"]
                thread_id = _parsed.get("thread_id")

            # Deduplicate only identical delivery targets. Thread/topic-aware
            # platforms can share a parent chat while still routing to distinct
            # destinations via metadata.
            dedup_key = (platform_str, chat_id, str(thread_id) if thread_id else None)
            if dedup_key in notified:
                continue

            try:
                platform = Platform(platform_str)
                adapter = self.adapters.get(platform)
                if not adapter:
                    continue

                platform_cfg = self.config.platforms.get(platform)
                if platform_cfg is not None and not platform_cfg.gateway_restart_notification:
                    logger.info(
                        "Shutdown notification suppressed for active session: %s has gateway_restart_notification=false",
                        platform_str,
                    )
                    continue

                reply_to_message_id = getattr(source, "message_id", None) if source is not None else None
                if reply_to_message_id is None and restart_source is not None:
                    try:
                        restart_platform = restart_source.platform.value
                        restart_chat_id = str(restart_source.chat_id)
                        restart_thread_id = str(restart_source.thread_id) if restart_source.thread_id else None
                        if (restart_platform, restart_chat_id, restart_thread_id) == dedup_key:
                            reply_to_message_id = getattr(restart_source, "message_id", None)
                    except Exception:
                        pass

                metadata = self._thread_metadata_for_target(
                    platform,
                    chat_id,
                    thread_id,
                    chat_type=getattr(source, "chat_type", None) if source is not None else None,
                    reply_to_message_id=reply_to_message_id,
                    adapter=adapter,
                )

                result = await adapter.send(chat_id, msg, metadata=metadata)
                if result is not None and getattr(result, "success", True) is False:
                    logger.debug(
                        "Failed to send shutdown notification to %s:%s: %s",
                        platform_str,
                        chat_id,
                        getattr(result, "error", "send returned success=False"),
                    )
                    continue

                notified.add(dedup_key)
                logger.info(
                    "Sent shutdown notification to active chat %s:%s",
                    platform_str, chat_id,
                )
            except Exception as e:
                logger.debug(
                    "Failed to send shutdown notification to %s:%s: %s",
                    platform_str, chat_id, e,
                )

        if self._restart_requested and restart_source is not None:
            logger.debug("Skipping home-channel shutdown notifications for in-chat restart")
            return

        # Snapshot adapters up front: adapter.send() can hit a fatal error
        # path that pops the adapter from self.adapters (see _handle_fatal
        # elsewhere), which would otherwise trigger
        # ``RuntimeError: dictionary changed size during iteration`` —
        # observed in a user report during gateway shutdown.
        for platform, adapter in list(self.adapters.items()):
            home = self.config.get_home_channel(platform)
            if not home or not home.chat_id:
                continue

            platform_cfg = self.config.platforms.get(platform)
            if platform_cfg is not None and not platform_cfg.gateway_restart_notification:
                logger.info(
                    "Shutdown notification suppressed for home channel: %s has gateway_restart_notification=false",
                    platform.value,
                )
                continue

            dedup_key = (platform.value, str(home.chat_id), str(home.thread_id) if home.thread_id else None)
            if dedup_key in notified:
                continue

            try:
                metadata = self._thread_metadata_for_target(
                    platform,
                    home.chat_id,
                    home.thread_id,
                    adapter=adapter,
                )
                if metadata:
                    result = await adapter.send(str(home.chat_id), msg, metadata=metadata)
                else:
                    result = await adapter.send(str(home.chat_id), msg)
                if result is not None and getattr(result, "success", True) is False:
                    logger.debug(
                        "Failed to send shutdown notification to home channel %s:%s: %s",
                        platform.value,
                        home.chat_id,
                        getattr(result, "error", "send returned success=False"),
                    )
                    continue

                notified.add(dedup_key)
                logger.info(
                    "Sent shutdown notification to home channel %s:%s",
                    platform.value,
                    home.chat_id,
                )
            except Exception as e:
                logger.debug(
                    "Failed to send shutdown notification to home channel %s:%s: %s",
                    platform.value,
                    home.chat_id,
                    e,
                )

    def _finalize_shutdown_agents(self, active_agents: dict[str, Any]) -> None:
        for agent in active_agents.values():
            try:
                from prostor_cli.plugins import invoke_hook as _invoke_hook
                _invoke_hook(
                    "on_session_finalize",
                    session_id=getattr(agent, "session_id", None),
                    platform="gateway",
                    reason="shutdown",
                )
            except Exception:
                pass
            self._cleanup_agent_resources(agent)

    def _cleanup_agent_resources(self, agent: Any) -> None:
        """Best-effort cleanup for temporary or cached agent instances."""
        if agent is None:
            return
        try:
            if hasattr(agent, "shutdown_memory_provider"):
                # Pass the agent's own conversation transcript so memory
                # providers' ``on_session_end`` hooks see the real messages
                # instead of the empty default (#15165). ``_session_messages``
                # is set on ``AIAgent`` (run_agent.py:1518) and refreshed at
                # the end of every ``run_conversation`` turn via
                # ``_persist_session``; on an agent built through
                # ``object.__new__`` (test stubs) the attribute may be
                # absent, so ``getattr`` with a ``None`` default keeps the
                # call signature-compatible with the pre-fix behaviour
                # (``shutdown_memory_provider(messages=None)``).
                session_messages = getattr(agent, "_session_messages", None)
                if isinstance(session_messages, list):
                    agent.shutdown_memory_provider(session_messages)
                else:
                    agent.shutdown_memory_provider()
        except Exception:
            pass
        # Close tool resources (terminal sandboxes, browser daemons,
        # background processes, httpx clients) to prevent zombie
        # process accumulation.
        try:
            if hasattr(agent, "close"):
                agent.close()
        except Exception:
            pass
        # Auxiliary async clients (session_search/web/vision/etc.) live in a
        # process-global cache and are created inside worker threads. Clean up
        # any entries whose event loop is now dead so their httpx transports do
        # not accumulate across gateway turns.
        try:
            from agent.auxiliary_client import cleanup_stale_async_clients
            cleanup_stale_async_clients()
        except Exception:
            pass

    async def _drain_startup_restore_queue(self) -> int:
        """Replay inbound messages queued while startup auto-resume ran."""
        drained = 0
        queue = getattr(self, "_startup_restore_queue", None)
        if queue is None:
            return 0
        while queue:
            event = queue.pop(0)
            source = getattr(event, "source", None)
            adapter = self.adapters.get(source.platform) if source is not None else None
            if adapter is None:
                logger.debug(
                    "Dropping startup-restore queued message: adapter unavailable for %s",
                    getattr(getattr(source, "platform", None), "value", None),
                )
                continue
            # Mark this replay so _handle_message does not queue it again while
            # the restore gate remains closed for any fresh inbound arrivals.
            try:
                event._prostor_startup_restore_replay = True
            except Exception:
                pass
            await adapter.handle_message(event)
            drained += 1
        return drained

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()