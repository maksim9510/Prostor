# Changelog

All notable changes to **Prostor Agent** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 📌 **2026-06-21**: Полный ребренд **Prostor → Prostor** (62 633 замены в 4 121 файле).
> До этой даты — релиз-линейка Prostor Agent (`v2026.x.y`).
> С этой даты — релиз-линейка Prostor (`v0.x.y`).

---

## [Unreleased]

### Planned

- Linux/macOS installers (`npm run dist:linux`, `npm run dist:mac`)
- Замена placeholder-иконок на финальные Prostor-ассеты
- Документация по self-learning loop (memory + skills)
- ENG translation of README.md
- Hacktoberfest participation

---

## [0.17.0] — 2026-06-21

**The Prostor Rebrand Release.**

Первый релиз под именем **Prostor**. Полный ребренд Prostor Agent → Prostor Agent
(62 633 замены в 4 121 файле), русский интерфейс по умолчанию, и **10 новых
оптимизаций**, не существовавших в Prostor.

### 🔥 Highlights

- **Prostor → Prostor rebrand** (62 633 замены, 4121 файл)
- **Russian-first** UI: `ru` как `DEFAULT_LANGUAGE`, `i18n.py` + 1926 строк
  русских переводов в `ru.ts`
- **10 новых оптимизаций** (`tools/`):

| Оптимизация | Метрика | Где |
|---|---|---|
| HashLine — O(1) hash matching | до **4700x** | `tools/hashline.py` |
| HashLine persistent cache | до **7x** на повторных patch | `tools/hashline_persistent_cache.py` |
| batch_patch tool | **1 round-trip** вместо N | `tools/batch_patch_tool.py` |
| batch_read tool | **1 round-trip** вместо N | `tools/batch_read_tool.py` |
| Tool result compression | **99.6%** экономим | `tools/result_compression.py` |
| Token Budget Manager | warn at 75/90/95% | `tools/token_budget.py` |
| Context Window Optimizer | **99.7%** контекста | `tools/context_optimizer.py` |
| Smart Read Cache | mtime+size invalidation | `tools/smart_read_cache.py` |
| Adaptive Tool Router | auto-suggest batch | `tools/adaptive_router.py` |
| SSH Paramiko connector skill | — | `skills/devops/ssh-paramiko-connector/` |

### 📦 Windows installers

- `Prostor-0.17.0-win-x64.exe` — NSIS installer (111 MB)
- `Prostor-0.17.0-win-x64.msi` — MSI installer (125 MB)
- `win-unpacked/Prostor.exe` — распакованная версия (214 MB)

### 🛠 Changed

- Protocol: `prostor://` → `prostor://`
- Executable: `Prostor.exe`
- App ID: `com.nousresearch.prostor`
- `.prostor/` → `.prostor/` (284 файла конфига)
- `prostor-gateway` → `prostor-gateway`
- `@prostor/shared` → `@prostor/shared`
- 422 env vars: `PROSTOR_*` → `PROSTOR_*`

### 🎨 Assets

- `prostor.png` → `prostor.png` (icon, banner)
- `prostor-frames` → `prostor-frames` (TUI splash)
- `icon.ico`, `icon.png`, `icon.icns`, `apple-touch-icon` — обновлены

### ✅ Tests

- Python smoke test: **13/13 PASSED**
- `pytest test_i18n.py`: **47/47 PASSED**
- `pytest test_config.py`: **99 passed, 1 skipped**
- `pytest test_prostor_constants.py`: **46 passed**
- `vitest languages.test.ts`: **4/4 PASSED**
- TypeScript в ru.ts, prostor.ts: **0 ошибок**

### ⚠️ Known issues

- `.github/workflows/deploy-site.yml` падает на Docusaurus build —
  поле `url` содержит `/maksim9510/Prostor`, нужно перенести в `baseUrl`
  (см. issue #6)
- `VERCEL_DEPLOY_HOOK_URL` secret не задан → deploy-vercel job падает
- `/docs/api/skills-index.json` не публикуется на GitHub Pages
  (watchdog в `skills-index-freshness.yml` отслеживает)

---

## [2026.6.19] — Prostor Agent v0.17.0

The Reach Release — iMessage via Photon, Raft channel, async subagents,
image editing, Cursor Composer via xAI Grok, dashboard profile builder,
memory tool upgrade, WhatsApp Business Cloud, rich Telegram,
curator cost optimization.

---

## [2026.6.5] — Prostor Agent v0.16.0

The Surface Release — native desktop app, browser admin panel,
remote-gateway connect, Simplified Chinese desktop UI, leaner default
skill set, NVIDIA/skills trusted tap, fuzzy model picker, /undo.

---

## [2026.5.29.2] — Prostor Agent v0.15.2

Weekly release.

---

## [2026.5.29] — Prostor Agent v0.15.1

Same-day hotfix for v0.15.0. Headline: dashboard infinite-reload loop
in loopback mode (Docker / hosted Prostor / fresh installs). Plus kanban
worker SIGTERM, `/model` picker unification, `/yolo` session bypass,
skills.sh full catalog, `.md` media delivery restore, gateway
probe-stepdown safety, web URL redaction passthrough, kanban worker
vision on referenced images, hindsight observation-default.
Docker hardening: `--insecure` explicit env opt-in, MCP bare-command
PATH resolution, arm64 cache fix.

28 commits, 21 PRs, 9 contributors since v0.15.0.

---

## [2026.5.28] — Prostor Agent v0.15.0

The Velocity Release. `run_agent.py` 16k→3.8k LOC refactor, kanban
grows into a multi-agent platform (104 PRs), cold-start perf wave
continues, session_search **4500x** faster, promptware defense,
Bitwarden Secrets Manager, Krea + FAL plugin.

---

## [2026.5.16] — Prostor Agent v0.14.0

The Foundation Release — Prostor installs and runs anywhere.
Native Windows (early beta), PyPI wheel, cold-start perf wave,
supply-chain hardening, OpenAI-compatible local proxy for OAuth
providers, cross-session Claude prompt cache, 2 new platforms
(LINE + SimpleX), Microsoft Graph foundation, `/handoff` live,
x_search, vision_analyze passthrough, LSP diagnostics,
video_generate plugin surface, computer_use cua-driver,
9 new skills, 12 P0 + 50 P1 closures.

---

## [2026.5.7] — Prostor Agent v0.13.0

The Tenacity Release — Prostor Agent now finishes what it starts.
Durable multi-agent Kanban, `/goal` persistent goals, Checkpoints v2.

---

## [2026.4.30] — Prostor Agent v0.12.0

The Curator release — Prostor Agent now maintains itself. Autonomous
background Curator + substantially upgraded self-improvement loop.
Four new inference providers, Microsoft Teams (via pluggable gateway).

---

## [2026.4.23] — Prostor Agent v0.11.0

The Interface release — new Ink-based TUI, pluggable transport
architecture, native AWS Bedrock, five new inference paths,
GPT-5.5 via Codex OAuth, QQBot (17th platform), expanded plugin
surface, and dashboard plugin system.

---

## [2026.4.16] — Prostor Agent v0.10.0

Tool Gateway release — paid Nous Portal subscribers get web search,
image gen, TTS, and browser automation through their existing
subscription.

---

## [2026.4.13] — Prostor Agent v0.9.0

The everywhere release — Prostor goes mobile with Termux/Android,
adds iMessage and WeChat, ships Fast Mode for OpenAI and Anthropic,
introduces background process monitoring, launches a local web
interface.

---

## [2026.4.8] — Prostor Agent v0.8.0

The intelligence release — native Google AI Studio, live model
switching, self-optimized GPT/Codex guidance, smart inactivity
timeouts, approval buttons, MCP OAuth 2.1, centralized logging,
and 209 merged PRs.

---

## [2026.4.3] — Prostor Agent v0.7.0

The resilience release — pluggable memory providers, credential
pools, Camofox browser, inline diffs, gateway hardening, secret
exfiltration blocking. 168 PRs, 46 issues, 40+ contributors.

---

## [2026.3.30] — Prostor Agent v0.6.0

The multi-instance release — Profiles, MCP server mode, Docker
container, fallback provider chains, Feishu/Lark, WeCom,
Telegram webhook mode, Slack multi-workspace OAuth, 95 PRs.

---

## [2026.3.28] — Prostor Agent v0.5.0

The hardening release — Nous Portal 400+ models, Hugging Face
provider, Telegram Private Chat Topics, native Modal SDK,
plugin lifecycle hooks, improved OpenAI model reliability,
Nix flake, supply chain hardening.

---

## [2026.3.23] — Prostor Agent v0.4.0

The biggest release yet — 300 merged PRs in one week. Streaming
output, native browser tools, Skills Hub, plugin system,
7 new messaging platforms, MCP server management, `@` context
references, prompt caching, API server, and a sweeping reliability
overhaul.

---

## [2026.3.17] — Prostor Agent v0.3.0

The streaming, plugins, and provider release — 248 merged PRs,
15 contributors. Highlights: unified streaming, plugin architecture,
native Anthropic provider, smart approvals, `/browser` connect via
CDP, Vercel AI Gateway, ACP IDE integration, voice mode, PII
redaction, persistent shell, and 50+ bug fixes.

---

## [2026.3.12] — Prostor Agent v0.2.0

First tagged release since v0.1.0. Covers 216 merged PRs from
63 contributors.

---

## [0.1.0] — Initial Prostor release

The first Prostor Agent release under Nous Research. Foundation
release with CLI, gateway, MCP, and 16 messaging platforms.

---

## Types of changes

- **🔥 Highlights** — biggest changes
- **✨ Added** — new features
- **🔧 Changed** — changes in existing functionality
- **🗑 Deprecated** — soon-to-be removed features
- **🚫 Removed** — removed features
- **🐛 Fixed** — bug fixes
- **🔒 Security** — vulnerability fixes
- **⚠️ Known issues** — bugs that will be fixed soon

[Unreleased]: https://github.com/maksim9510/Prostor/compare/v0.17.0...HEAD
[0.17.0]: https://github.com/maksim9510/Prostor/releases/tag/v0.17.0
[2026.6.19]: https://github.com/maksim9510/Prostor/releases/tag/2026.6.19
[2026.6.5]: https://github.com/maksim9510/Prostor/releases/tag/2026.6.5
[2026.5.29.2]: https://github.com/maksim9510/Prostor/releases/tag/2026.5.29.2
[2026.5.29]: https://github.com/maksim9510/Prostor/releases/tag/2026.5.29
[2026.5.28]: https://github.com/maksim9510/Prostor/releases/tag/2026.5.28
[2026.5.16]: https://github.com/maksim9510/Prostor/releases/tag/2026.5.16
[2026.5.7]: https://github.com/maksim9510/Prostor/releases/tag/2026.5.7
[2026.4.30]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.30
[2026.4.23]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.23
[2026.4.16]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.16
[2026.4.13]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.13
[2026.4.8]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.8
[2026.4.3]: https://github.com/maksim9510/Prostor/releases/tag/2026.4.3
[2026.3.30]: https://github.com/maksim9510/Prostor/releases/tag/2026.3.30
[2026.3.28]: https://github.com/maksim9510/Prostor/releases/tag/2026.3.28
[2026.3.23]: https://github.com/maksim9510/Prostor/releases/tag/2026.3.23
[2026.3.17]: https://github.com/maksim9510/Prostor/releases/tag/2026.3.17
[2026.3.12]: https://github.com/maksim9510/Prostor/releases/tag/2026.3.12
[0.1.0]: https://github.com/maksim9510/Prostor/releases/tag/v0.1.0
