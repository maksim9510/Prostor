"""Pydantic models for the Prostor web server API.

Extracted from web_server.py (#24).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = ['ConfigUpdate', 'EnvVarUpdate', 'EnvVarDelete', 'EnvVarReveal', 'MemoryProviderConfigUpdate', 'MessagingPlatformUpdate', 'TelegramOnboardingStart', 'TelegramOnboardingApply', 'AudioTranscriptionRequest', 'ManagedFileUpload', 'ManagedDirectoryCreate', 'ManagedFileDelete', 'ModelAssignment', 'CuratorPause', 'DebugShareRequest', 'TTSSpeakRequest', 'OAuthSubmitBody', 'BulkDeleteSessions', 'SessionRename', 'SessionPrune', 'CronJobCreate', 'CronJobUpdate', 'AutomationBlueprintInstantiate', 'MCPServerCreate', 'MCPEnabledToggle', 'MCPCatalogInstall', 'PairingApprove', 'PairingRevoke', 'WebhookCreate', 'WebhookEnabledToggle', 'CredentialPoolAdd', 'MemoryProviderSelect', 'MemoryReset', 'BackupRequest', 'ImportRequest', 'HookCreate', 'HookDelete', 'SkillInstallRequest', 'SkillUninstallRequest', 'SkillsUpdateRequest', 'ProfileCreate', 'ProfileRename', 'ProfileSoulUpdate', 'ProfileActiveUpdate', 'ProfileDescriptionUpdate', 'ProfileModelUpdate', 'ProfileDescribeAuto', 'SkillToggle', 'SkillCreate', 'SkillContentUpdate', 'ToolsetToggle', 'ToolsetProviderSelect', 'ToolsetEnvUpdate', 'ToolsetPostSetup', 'RawConfigUpdate', 'ThemeSetBody', 'FontSetBody', '_AgentPluginInstallBody', '_PluginProvidersPutBody', '_PluginVisibilityBody']


class ConfigUpdate(BaseModel):
    config: dict
    profile: str | None = None


class EnvVarUpdate(BaseModel):
    key: str
    value: str
    profile: str | None = None
    # Optional bearer key for the connectivity probe of a custom/local endpoint
    # (``key == "OPENAI_BASE_URL"``). Self-hosted endpoints that gate
    # ``/v1/models`` behind auth otherwise look "reachable but empty"; sending
    # the key lets the probe enumerate the served models. Ignored for the
    # regular PUT /api/env path (which only reads key/value).
    api_key: str = ""


class EnvVarDelete(BaseModel):
    key: str
    profile: str | None = None


class EnvVarReveal(BaseModel):
    key: str
    profile: str | None = None


class MemoryProviderConfigUpdate(BaseModel):
    values: dict[str, str] = {}


class MessagingPlatformUpdate(BaseModel):
    enabled: bool | None = None
    env: dict[str, str] = {}
    clear_env: list[str] = []
    # Explicit body profile beats the query param injected by the global
    # dashboard profile switcher (same precedence as other scoped writes).
    profile: str | None = None


class TelegramOnboardingStart(BaseModel):
    bot_name: str | None = None


class TelegramOnboardingApply(BaseModel):
    allowed_user_ids: list[str]
    profile: str | None = None


class AudioTranscriptionRequest(BaseModel):
    data_url: str
    mime_type: str | None = None


class ManagedFileUpload(BaseModel):
    path: str
    data_url: str
    overwrite: bool = True


class ManagedDirectoryCreate(BaseModel):
    path: str


class ManagedFileDelete(BaseModel):
    path: str
    recursive: bool = False


class ModelAssignment(BaseModel):
    """Payload for POST /api/model/set — assign a provider/model to a slot.

    scope="main"        → writes model.provider + model.default
    scope="auxiliary"   → writes auxiliary.<task>.provider + auxiliary.<task>.model
    scope="auxiliary" with task=""  → applied to every auxiliary.* slot
    scope="auxiliary" with task="__reset__"  → resets every slot to provider="auto"
    """
    scope: str
    provider: str
    model: str
    task: str = ""
    # Optional OpenAI-compatible endpoint URL. Only honored for custom/local
    # providers on the main slot — lets the GUI configure a self-hosted endpoint
    # (vLLM, llama.cpp, Ollama, …) that needs no API key. The runtime resolver
    # reads model.base_url from config (it ignores OPENAI_BASE_URL), so this is
    # the path that actually wires a local endpoint into resolution.
    base_url: str = ""
    # Optional API key for a custom/local endpoint. Persisted to
    # ``model.api_key`` (where the runtime resolver reads it) so a self-hosted
    # endpoint that requires auth works from the GUI — mirrors the key the
    # ``prostor model`` custom flow collects. Honored only on the main slot for
    # custom/local providers.
    api_key: str = ""
    confirm_expensive_model: bool = False
    profile: str | None = None


class CuratorPause(BaseModel):
    paused: bool


class DebugShareRequest(BaseModel):
    # Redaction is ON by default — force-mode scrubs credential-shaped tokens
    # out of log content before it leaves the machine. The toggle exists so an
    # operator who knows the logs are clean can opt out for fuller fidelity.
    redact: bool = True
    # Recent log lines included in the summary tail (full logs are separate).
    lines: int = 200


class TTSSpeakRequest(BaseModel):
    text: str


class OAuthSubmitBody(BaseModel):
    session_id: str
    code: str


class BulkDeleteSessions(BaseModel):
    ids: list[str]
    profile: str | None = None


class SessionRename(BaseModel):
    title: str | None = None
    archived: bool | None = None
    # Mutate a session belonging to another profile (opens its state.db). Omit
    # for the current/default profile.
    profile: str | None = None


class SessionPrune(BaseModel):
    older_than_days: int = 90
    source: str | None = None
    profile: str | None = None


class CronJobCreate(BaseModel):
    prompt: str
    schedule: str
    name: str = ""
    deliver: str = "local"
    skills: list[str] | None = None


class CronJobUpdate(BaseModel):
    updates: dict


class AutomationBlueprintInstantiate(BaseModel):
    blueprint: str                      # blueprint key, e.g. "morning-brief"
    values: dict[str, Any] = {}      # filled slot values from the form


class MCPServerCreate(BaseModel):
    name: str
    url: str | None = None
    command: str | None = None
    args: list[str] = []
    # env: KEY=VALUE map for stdio servers (API keys, etc.)
    env: dict[str, str] = {}
    # auth: "oauth" | "header" | None
    auth: str | None = None
    profile: str | None = None


class MCPEnabledToggle(BaseModel):
    enabled: bool
    profile: str | None = None


class MCPCatalogInstall(BaseModel):
    name: str
    # env: KEY=VALUE map for catalog entries that declare required env vars.
    env: dict[str, str] = {}
    enable: bool = True
    profile: str | None = None


class PairingApprove(BaseModel):
    platform: str
    code: str


class PairingRevoke(BaseModel):
    platform: str
    user_id: str


class WebhookCreate(BaseModel):
    name: str
    description: str | None = None
    events: list[str] = []
    prompt: str | None = None
    skills: list[str] = []
    deliver: str = "log"
    deliver_only: bool = False
    deliver_chat_id: str | None = None
    # secret: omit to auto-generate
    secret: str | None = None


class WebhookEnabledToggle(BaseModel):
    enabled: bool


class CredentialPoolAdd(BaseModel):
    provider: str
    # api_key for API-key providers; OAuth pooling stays CLI-only (it needs
    # an interactive browser flow that doesn't belong in a single POST).
    api_key: str
    label: str | None = None


class MemoryProviderSelect(BaseModel):
    # "" or "built-in" disables the external provider (built-in only).
    provider: str


class MemoryReset(BaseModel):
    # "all" | "memory" | "user"
    target: str = "all"


class BackupRequest(BaseModel):
    # Optional output path; defaults to a timestamped zip in the home dir.
    output: str | None = None


class ImportRequest(BaseModel):
    archive: str
    # Pass --force to `prostor import`. The spawned action runs with
    # stdin=DEVNULL, so the CLI's interactive "Continue? [y/N]" overwrite
    # prompt hits EOF and auto-aborts ("Aborted.", exit 1) whenever the
    # target already has a config — which it always does when the dashboard
    # itself is running from it. The dashboard shows its own confirm modal
    # before calling this endpoint, then sends force=True so the restore
    # proceeds non-interactively.
    force: bool = False


class HookCreate(BaseModel):
    event: str
    command: str
    matcher: str | None = None
    timeout: int | None = None
    # approve: write the consent allowlist entry too (the operator using the
    # authenticated dashboard is giving consent). Without it the hook is
    # configured but won't fire until approved.
    approve: bool = True


class HookDelete(BaseModel):
    event: str
    command: str


class SkillInstallRequest(BaseModel):
    identifier: str
    profile: str | None = None


class SkillUninstallRequest(BaseModel):
    name: str
    profile: str | None = None


class SkillsUpdateRequest(BaseModel):
    profile: str | None = None


class ProfileCreate(BaseModel):
    name: str
    clone_from: str | None = None
    # Backward compatibility for older dashboard/desktop clients. New clients
    # send clone_from="default" (or another profile name) explicitly.
    clone_from_default: bool = False
    clone_all: bool = False
    no_skills: bool = False
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    # Profile-builder additions — all optional, all applied best-effort AFTER
    # the profile directory exists, so a hiccup in any of them never 500s the
    # create (the user can fix it from the relevant dashboard page afterward).
    # MCP servers to write into the new profile's config.yaml.
    mcp_servers: list[MCPServerCreate] = []
    # Built-in / optional skills to KEEP active. When this list is non-empty,
    # the builder uses "replace" semantics: the bundle is seeded, then every
    # seeded skill NOT in this list is added to the profile's disabled list.
    # Empty list = leave the seeded bundle untouched (legacy behaviour).
    keep_skills: list[str] = []
    # Skills-hub identifiers to install into the new profile. Installed async
    # via a subprocess scoped to the profile (`prostor -p <name> skills install`)
    # because skills_hub.SKILLS_DIR is import-time-bound and the PROSTOR_HOME
    # override can't redirect it. Returns spawned PIDs for the UI to poll.
    hub_skills: list[str] = []


class ProfileRename(BaseModel):
    new_name: str


class ProfileSoulUpdate(BaseModel):
    content: str


class ProfileActiveUpdate(BaseModel):
    name: str


class ProfileDescriptionUpdate(BaseModel):
    description: str = ""


class ProfileModelUpdate(BaseModel):
    provider: str
    model: str


class ProfileDescribeAuto(BaseModel):
    overwrite: bool = False


class SkillToggle(BaseModel):
    name: str
    enabled: bool
    profile: str | None = None


class SkillCreate(BaseModel):
    name: str
    content: str
    category: str | None = None
    profile: str | None = None


class SkillContentUpdate(BaseModel):
    name: str
    content: str
    profile: str | None = None


class ToolsetToggle(BaseModel):
    enabled: bool
    profile: str | None = None


class ToolsetProviderSelect(BaseModel):
    provider: str
    profile: str | None = None


class ToolsetEnvUpdate(BaseModel):
    env: dict[str, str]
    profile: str | None = None


class ToolsetPostSetup(BaseModel):
    key: str
    profile: str | None = None


class RawConfigUpdate(BaseModel):
    yaml_text: str
    profile: str | None = None


class ThemeSetBody(BaseModel):
    name: str


class FontSetBody(BaseModel):
    font: str


class _AgentPluginInstallBody(BaseModel):
    identifier: str
    force: bool = False
    enable: bool = True


class _PluginProvidersPutBody(BaseModel):
    memory_provider: str | None = None
    context_engine: str | None = None


class _PluginVisibilityBody(BaseModel):
    hidden: bool
