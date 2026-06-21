# Контрибуция в Prostor Agent

Спасибо за интерес к контрибуции в Prostor Agent! Это руководство покрывает всё необходимое: настройку среды разработки, понимание архитектуры, решение что строить и прохождение PR-процесса.

---

## Приоритеты контрибуции

Мы ценим контрибуции в следующем порядке:

1. **Исправление багов** — краши, некорректное поведение, потеря данных. Всегда высший приоритет.
2. **Кроссплатформенная совместимость** — macOS, различные дистрибутивы Linux и WSL2 на Windows. Мы хотим, чтобы Prostor работал везде.
3. **Усиление безопасности** — shell injection, prompt injection, path traversal, privilege escalation. См. [Безопасность](#соображения-безопасности).
4. **Производительность и надёжность** — retry-логика, обработка ошибок, graceful degradation.
5. **Новые навыки (skills)** — но только широко полезные. См. [Должно ли это быть Skill или Tool?](#должно-ли-это-быть-skill-или-tool)
6. **Новые инструменты (tools)** — редко требуется. Большинство возможностей должно быть skills. См. ниже.
7. **Документация** — исправления, уточнения, новые примеры.

---

## Должно ли это быть Skill или Tool?

Это самый частый вопрос для новых контрибьюторов. Ответ почти всегда — **skill**.

### Делайте Skill, когда:

- Возможность выражается как инструкции + shell-команды + существующие инструменты
- Оборачивает внешний CLI или API, который агент может вызвать через `terminal` или `web_extract`
- Не требует кастомной Python-интеграции или управления API-ключами внутри агента
- Примеры: поиск arXiv, git-воркфлоу, управление Docker, обработка PDF, email через CLI-инструменты

### Делайте Tool, когда:

- Требуется end-to-end интеграция с API-ключами, auth-потоками или multi-component конфигурацией, управляемой agent harness
- Нужна кастомная логика обработки, которая должна выполняться точно каждый раз (не «best effort» из LLM-интерпретации)
- Обрабатывает бинарные данные, streaming или real-time events, не проходящие через терминал
- Примеры: browser automation (Browserbase session management), TTS (audio encoding + platform delivery), vision analysis (base64 image handling)

### Должен ли Skill быть bundled?

Bundled skills (в `skills/`) отгружаются с каждой установкой Prostor. Они должны быть **широко полезны большинству пользователей**:

- Работа с документами, веб-исследования, общие dev-воркфлоу, системное администрирование
- Регулярно используются широким кругом людей

Если ваш skill официальный и полезный, но не универсальный (например, платная интеграция, тяжёлая зависимость), поместите его в **`optional-skills/`** — он отгружается с репо, но не активируется по умолчанию. Пользователи могут обнаружить его через `prostor skills browse` (с пометкой «official») и установить через `prostor skills install` (без предупреждения о third-party, built-in trust).

Если ваш skill специализированный, community-contributed или нишевый, лучше подойдёт **Skills Hub** — загрузите его в реестр skills и поделитесь в [Nous Research Discord](https://discord.gg/NousResearch). Пользователи установят через `prostor skills install`.

---

## Memory Providers: публикуйте как standalone-плагин

**Мы больше не принимаем новые memory providers в этот репозиторий.** Набор built-in providers в `plugins/memory/` (honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb) закрыт. Если хотите добавить новый memory backend, опубликуйте его как **standalone plugin repo**, который пользователи устанавливают в `~/.prostor/plugins/` (или через pip entry point).

Standalone memory plugins:

- Реализуют тот же `MemoryProvider` ABC (`agent/memory_provider.py`) — `sync_turn`, `prefetch`, `shutdown`, и опционально `post_setup(prostor_home, config)` для setup-wizard интеграции
- Используют ту же систему discovery — `discover_memory_providers()` находит их в user/project plugin-директориях и pip entry points
- Интегрируются с `prostor memory setup` через `post_setup()` — не нужно трогать core code
- Могут регистрировать собственные CLI subcommands через `register_cli(subparser)` в файле `cli.py`
- Получают все те же lifecycle hooks и config plumbing, что и in-tree providers

PR, добавляющие новую директорию в `plugins/memory/`, будут закрыты с указанием опубликовать provider как отдельный repo. Существующие in-tree providers остаются; bug fix'ы к ним приветствуются.

Это не quality bar — это решение о coupling и maintenance. Memory providers — самый частый тип плагинов, и они не должны все жить в этом tree.

---

## Настройка среды разработки

### Предварительные требования

| Требование | Примечания |
|------------|-----------|
| **Git** | С установленным расширением `git-lfs` |
| **Python 3.11+** | uv установит, если отсутствует |
| **uv** | Быстрый Python package manager ([установка](https://docs.astral.sh/uv/)) |
| **Node.js 20+** | Опционально — нужно для browser tools и WhatsApp bridge (соответствует root `package.json` engines) |

### Установка через стандартный установщик

Для большинства контрибьюторов лучший bootstrap — тот же путь, что у пользователей: запустите стандартный установщик, затем работайте внутри репозитория, который он клонировал. Установщик создаёт Prostor venv, подключает команду `prostor`, stamps install method для `prostor update` и клонирует полный git-проект в `$PROSTOR_HOME/prostor-agent` (обычно `~/.prostor/prostor-agent`). Это держит вашу среду разработки на том же layout, который CLI, updater, lazy dependency installer, gateway и docs предполагают.

```bash
curl -fsSL https://github.com/maksim9510/Prostor/install.sh | bash
cd "${PROSTOR_HOME:-$HOME/.prostor}/prostor-agent"

# Добавьте dev/test extras поверх стандартной установки.
uv pip install -e ".[all,dev]"

# Опционально: browser tools / зависимости сайта документации.
npm install
```

После этого создавайте ветки и запускайте тесты из этого checkout:

```bash
git checkout -b fix/description
scripts/run_tests.sh
```

### Ручное клонирование (fallback)

Используйте, только если намеренно не хотите managed install layout Prostor (например, одноразовый клон внутри контейнера или CI job). При такой установке убедитесь, что запускаете entrypoint `prostor` из этого venv; запуск system `python3 -m prostor_cli.main` может подхватить несвязанные системные Python-пакеты.

```bash
git clone https://github.com/maksim9510/Prostor.git
cd prostor-agent

# Создайте venv с Python 3.11
uv venv venv --python 3.11
export VIRTUAL_ENV="$(pwd)/venv"

# Установите со всеми extras (messaging, cron, CLI menus, dev tools)
uv pip install -e ".[all,dev]"

# Опционально: browser tools
npm install
```

### Настройка для разработки

```bash
mkdir -p ~/.prostor/{cron,sessions,logs,memories,skills}
cp cli-config.yaml.example ~/.prostor/config.yaml
touch ~/.prostor/.env

# Добавьте минимум ключ LLM-провайдера:
echo "OPENROUTER_API_KEY=***" >> ~/.prostor/.env
```

### Запуск

```bash
# Стандартный установщик уже положил `prostor` на PATH.
prostor doctor
prostor chat -q "Привет"
```

Если использовали ручное клонирование, запускайте `./prostor` из checkout или symlink'ните venv этого клона явно:

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/venv/bin/prostor" ~/.local/bin/prostor
```

### Запуск тестов

```bash
# Предпочтительно — соответствует CI (hermetic env, 4 xdist workers); см. AGENTS.md
scripts/run_tests.sh

# Альтернатива (активируйте venv сначала). Wrapper всё равно рекомендуется
# для parity с GitHub Actions перед PR:
pytest tests/ -v
```

---

## Структура проекта

```
prostor-agent/
├── run_agent.py              # Класс AIAgent — основной цикл разговора, tool dispatch, session persistence
├── cli.py                    # Класс ProstorCLI — интерактивный TUI, prompt_toolkit интеграция
├── model_tools.py            # Оркестрация инструментов (тонкий layer над tools/registry.py)
├── toolsets.py               # Группировка tools и пресеты (prostor-cli, prostor-telegram и т.д.)
├── prostor_state.py           # SQLite session database с FTS5 full-text search, session titles
├── batch_runner.py           # Параллельная пакетная обработка для trajectory generation
│
├── agent/                    # Внутренности агента (извлечённые модули)
│   ├── prompt_builder.py         # Сборка system prompt (identity, skills, context files, memory)
│   ├── context_compressor.py     # Auto-summarization при приближении к context limits
│   ├── auxiliary_client.py       # Резолвит auxiliary OpenAI clients (summarization, vision)
│   ├── display.py                # KawaiiSpinner, tool progress formatting
│   ├── model_metadata.py         # Model context lengths, token estimation
│   └── trajectory.py             # Helpers сохранения trajectory
│
├── prostor_cli/               # Реализации CLI-команд
│   ├── main.py                   # Entry point, парсинг аргументов, command dispatch
│   ├── config.py                 # Управление конфигом, миграция, env var definitions
│   ├── setup.py                  # Интерактивный мастер настройки
│   ├── auth.py                   # Provider resolution, OAuth, Nous Portal
│   ├── models.py                 # OpenRouter model selection lists
│   ├── banner.py                 # Welcome banner, ASCII art
│   ├── commands.py               # Центральный slash command registry (CommandDef), autocomplete, gateway helpers
│   ├── callbacks.py              # Интерактивные callbacks (clarify, sudo, approval)
│   ├── doctor.py                 # Диагностика
│   ├── skills_hub.py             # Skills Hub CLI + /skills slash command
│   └── skin_engine.py            # Skin/theme engine — data-driven CLI visual customization
│
├── tools/                    # Реализации инструментов (self-registering)
│   ├── registry.py               # Центральный tool registry (schemas, handlers, dispatch)
│   ├── approval.py               # Dangerous command detection + per-session approval
│   ├── terminal_tool.py          # Терминальная оркестрация (sudo, env lifecycle, backends)
│   ├── file_operations.py        # read_file, write_file, search, patch и т.д.
│   ├── web_tools.py              # web_search, web_extract (Parallel/Firecrawl + Gemini summarization)
│   ├── vision_tools.py           # Анализ изображений через multimodal models
│   ├── delegate_tool.py          # Spawning субагентов и параллельное выполнение задач
│   ├── code_execution_tool.py    # Sandboxed Python с RPC tool access
│   ├── session_search_tool.py    # Поиск прошлых разговоров с FTS5 + anchored windows
│   ├── cronjob_tools.py          # Управление scheduled tasks
│   ├── skill_tools.py            # Skill search, load, manage
│   └── environments/             # Терминальные backends выполнения
│       ├── base.py                   # BaseEnvironment ABC
│       ├── local.py, docker.py, ssh.py, singularity.py, modal.py, daytona.py
│
├── gateway/                  # Messaging gateway
│   ├── run.py                    # GatewayRunner — platform lifecycle, message routing, cron
│   ├── config.py                 # Platform configuration resolution
│   ├── session.py                # Session store, context prompts, reset policies
│   └── platforms/                # Платформенные адаптеры
│       ├── telegram.py, discord_adapter.py, slack.py, whatsapp.py
│
├── scripts/                  # Установочные и bridge-скрипты
│   ├── install.sh                # Linux/macOS установщик
│   ├── install.ps1               # Windows PowerShell установщик
│   └── whatsapp-bridge/          # Node.js WhatsApp bridge (Baileys)
│
├── skills/                   # Bundled skills (копируются в ~/.prostor/skills/ при установке)
├── optional-skills/          # Официальные опциональные skills (обнаруживаются через hub, не активны по умолчанию)
├── tests/                    # Набор тестов
├── website/                  # Сайт документации (github.com/maksim9510/Prostor)
│
├── cli-config.yaml.example   # Пример конфигурации (копируется в ~/.prostor/config.yaml)
└── AGENTS.md                 # Руководство для разработчиков для AI coding assistants
```

### Пользовательская конфигурация (хранится в `~/.prostor/`)

| Путь | Назначение |
|------|-----------|
| `~/.prostor/config.yaml` | Настройки (model, terminal, toolsets, compression и т.д.) |
| `~/.prostor/.env` | API-ключи и секреты |
| `~/.prostor/auth.json` | OAuth credentials (Nous Portal) |
| `~/.prostor/skills/` | Все активные skills (bundled + hub-installed + agent-created) |
| `~/.prostor/memories/` | Персистентная память (MEMORY.md, USER.md) |
| `~/.prostor/state.db` | SQLite session database |
| `~/.prostor/sessions/` | Gateway routing index (`sessions.json`), request-dump breadcrumbs, gateway `*.jsonl` transcripts, и (опционально) per-session JSON snapshots когда `sessions.write_json_snapshots: true`. Per-session snapshots off по умолчанию; state.db — canonical. |
| `~/.prostor/cron/` | Данные scheduled jobs |
| `~/.prostor/whatsapp/session/` | WhatsApp bridge credentials |

---

## Обзор архитектуры

### Основной цикл

```
User message → AIAgent._run_agent_loop()
  ├── Build system prompt (prompt_builder.py)
  ├── Build API kwargs (model, messages, tools, reasoning config)
  ├── Call LLM (OpenAI-compatible API)
  ├── If tool_calls in response:
  │     ├── Execute each tool via registry dispatch
  │     ├── Add tool results to conversation
  │     └── Loop back to LLM call
  ├── If text response:
  │     ├── Persist session to DB
  │     └── Return final_response
  └── Context compression if approaching token limit
```

### Ключевые паттерны проектирования

- **Self-registering tools**: каждый tool file вызывает `registry.register()` при import. `model_tools.py` запускает discovery, импортируя все tool modules.
- **Toolset grouping**: tools сгруппированы в toolsets (`web`, `terminal`, `file`, `browser` и т.д.), которые можно enable/disable per platform.
- **Session persistence**: все разговоры хранятся в SQLite (`prostor_state.py`) с full-text search и уникальными session titles. Per-session JSON snapshots в `~/.prostor/sessions/` superseded SQLite store и off по умолчанию; opt-in через `sessions.write_json_snapshots: true`, если есть external tooling, потребляющее JSON файлы напрямую.
- **Ephemeral injection**: system prompts и prefill messages инжектируются при API call time, никогда не persist в database или logs.
- **Provider abstraction**: агент работает с любым OpenAI-compatible API. Provider resolution происходит при init time (Nous Portal OAuth, OpenRouter API key, или custom endpoint).
- **Provider routing**: при использовании OpenRouter `provider_routing` в config.yaml контролирует выбор provider (sort по throughput/latency/price, allow/ignore specific providers, data retention policies). Они инжектируются как `extra_body.provider` в API requests.

---

## Стиль кода

- **PEP 8** с практическими исключениями (мы не enforce strict line length)
- **Комментарии**: только для объяснения non-obvious intent, trade-offs или API quirks. Не пересказывайте, что код делает — `# increment counter` ничего не добавляет
- **Обработка ошибок**: ловите конкретные exceptions. Логгируйте через `logger.warning()`/`logger.error()` — используйте `exc_info=True` для unexpected errors, чтобы stack traces попадали в logs
- **Кроссплатформенность**: никогда не предполагайте Unix. См. [Кроссплатформенная совместимость](#кроссплатформенная-совместимость)

---

## Добавление нового Tool

Перед написанием tool спросите: [должно ли это быть skill?](#должно-ли-это-быть-skill-или-tool)

Tools self-register с центральным registry. Каждый tool file co-locate'ит свой schema, handler и registration:

```python
"""my_tool — Краткое описание что делает этот tool."""

import json
from tools.registry import registry


def my_tool(param1: str, param2: int = 10, **kwargs) -> str:
    """Handler. Возвращает строку результата (часто JSON)."""
    result = do_work(param1, param2)
    return json.dumps(result)


MY_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "Что этот tool делает и когда агент должен его использовать.",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "Что такое param1"},
                "param2": {"type": "integer", "description": "Что такое param2", "default": 10},
            },
            "required": ["param1"],
        },
    },
}


def _check_requirements() -> bool:
    """Возвращает True если зависимости tool доступны."""
    return True


registry.register(
    name="my_tool",
    toolset="my_toolset",
    schema=MY_TOOL_SCHEMA,
    handler=lambda args, **kw: my_tool(**args, **kw),
    check_fn=_check_requirements,
)
```

**Wire в toolset (обязательно):** Built-in tools auto-discover'ятся: любой
`tools/*.py` файл с top-level `registry.register(...)` вызовом
импортируется `discover_builtin_tools()` в `tools/registry.py` когда
`model_tools` loads. **Нет** ручного import list в `model_tools.py` для поддержки.

Вы должны добавить tool name в соответствующий list в `toolsets.py`
(например `_PROSTOR_CORE_TOOLS` или dedicated toolset); иначе tool
register'ится, но никогда не exposed to agent. Если вводите новый toolset,
добавьте его в `toolsets.py` и wire в соответствующие platform presets.

См. `AGENTS.md` (раздел **Adding New Tools**) для profile-aware paths и
plugin vs core guidance.

---

## Добавление Skill

Bundled skills живут в `skills/`, организованы по категориям. Официальные опциональные skills используют ту же структуру в `optional-skills/`:

```
skills/
├── research/
│   └── arxiv/
│       ├── SKILL.md              # Обязательно: главные инструкции
│       └── scripts/              # Опционально: helper-скрипты
│           └── search_arxiv.py
├── productivity/
│   └── ocr-and-documents/
│       ├── SKILL.md
│       ├── scripts/
│       └── references/
└── ...
```

### Формат SKILL.md

```markdown
---
name: my-skill
description: Краткое описание (показывается в результатах поиска skills)
version: 1.0.0
author: Your Name
license: MIT
platforms: [macos, linux]          # Опционально — ограничить конкретными OS
                                   #   Valid: macos, linux, windows
                                   #   Omit для загрузки на всех платформах (default)
required_environment_variables:    # Опционально — secure setup-on-load metadata
  - name: MY_API_KEY
    prompt: API key
    help: Где получить
    required_for: full functionality
prerequisites:                     # Опциональные legacy runtime requirements
  env_vars: [MY_API_KEY]           #   Backward-compatible alias для required env vars
  commands: [curl, jq]             #   Advisory only; не скрывает skill
metadata:
  prostor:
    tags: [Category, Subcategory, Keywords]
    related_skills: [other-skill-name]
    fallback_for_toolsets: [web]       # Опционально — показывать только когда toolset unavailable
    requires_toolsets: [terminal]      # Опционально — показывать только когда toolset available
---

# Skill Title

Краткое intro.

## When to Use
Trigger conditions — когда агент должен загрузить этот skill?

## Quick Reference
Таблица общих команд или API-вызовов.

## Procedure
Пошаговые инструкции, которым агент следует.

## Pitfalls
Известные failure modes и как с ними работать.

## Verification
Как агент подтверждает, что сработало.
```

### Платформо-специфичные skills

Skills могут декларировать поддерживаемые OS-платформы через `platforms` frontmatter field. Skills с этим field автоматически скрываются из system prompt, `skills_list()` и slash commands на несовместимых платформах.

```yaml
platforms: [macos]            # только macOS (например, iMessage, Apple Reminders)
platforms: [macos, linux]     # macOS и Linux
platforms: [windows]          # только Windows
```

Если field omitted или empty, skill загружается на всех платформах (backward compatible). См. `skills/apple/` для примеров macOS-only skills.

### Условная активация skills

Skills могут декларировать условия, контролирующие когда они появляются в system prompt, на основе доступных tools и toolsets в текущей сессии. Используется в основном для **fallback skills** — альтернатив, которые должны показываться только когда primary tool unavailable.

Четыре field поддерживаются под `metadata.prostor`:

```yaml
metadata:
  prostor:
    fallback_for_toolsets: [web]      # Показывать ТОЛЬКО когда эти toolsets unavailable
    requires_toolsets: [terminal]     # Показывать ТОЛЬКО когда эти toolsets available
    fallback_for_tools: [web_search]  # Показывать ТОЛЬКО когда эти specific tools unavailable
    requires_tools: [terminal]        # Показывать ТОЛЬКО когда эти specific tools available
```

**Семантика:**
- `fallback_for_*`: skill — backup. **Скрыт** когда перечисленные tools/toolsets available, **показан** когда unavailable. Используйте для free alternatives к premium tools.
- `requires_*`: skill нуждается в определённых tools. **Скрыт** когда перечисленные tools/toolsets unavailable. Используйте для skills, зависящих от конкретных возможностей (например, skill, имеющий смысл только с terminal access).
- Если указаны оба — оба условия должны быть удовлетворены для показа skill.
- Если не указано ни одного — skill показывается всегда (backward compatible).

**Примеры:**

```yaml
# DuckDuckGo search — показывается когда Firecrawl (web toolset) unavailable
metadata:
  prostor:
    fallback_for_toolsets: [web]

# Smart home skill — полезна только когда terminal available
metadata:
  prostor:
    requires_toolsets: [terminal]

# Local browser fallback — показывается когда Browserbase unavailable
metadata:
  prostor:
    fallback_for_toolsets: [browser]
```

Фильтрация происходит при prompt build time в `agent/prompt_builder.py`. Функция `build_skills_system_prompt()` получает набор доступных tools и toolsets от агента и использует `_skill_should_show()` для оценки условий каждого skill.

### Setup metadata для skills

Skills могут декларировать secure setup-on-load metadata через `required_environment_variables` frontmatter field. Недостающие значения не скрывают skill из discovery; они trigger'ят CLI-only secure prompt, когда skill фактически загружается.

```yaml
required_environment_variables:
  - name: TENOR_API_KEY
    prompt: Tenor API key
    help: Получите ключ на https://developers.google.com/tenor
    required_for: full functionality
```

Пользователь может skip setup и продолжить загрузку skill. Prostor экспонирует модели только metadata (`stored_as`, `skipped`, `validated`) — никогда секретное значение.

Legacy `prerequisites.env_vars` остаётся поддерживаемым и нормализуется в новое представление.

```yaml
prerequisites:
  env_vars: [TENOR_API_KEY]       # Legacy alias для required_environment_variables
  commands: [curl, jq]            # Advisory CLI checks
```

Gateway и messaging sessions никогда не собирают секреты in-band; они инструктируют пользователя запустить `prostor setup` или обновить `~/.prostor/.env` локально.

**Когда декларировать required environment variables:**
- Skill использует API key или token, который должен собираться безопасно при load time
- Skill всё ещё полезен, если пользователь skip'нул setup, но может деградировать gracefully

**Когда декларировать command prerequisites:**
- Skill зависит от CLI tool, который может быть не установлен (например, `himalaya`, `openhue`, `ddgs`)
- Рассматривайте command checks как guidance, не discovery-time hiding

См. `skills/gifs/gif-search/` и `skills/email/himalaya/` для примеров.

### Стандарты authoring skills (HARDLINE)

Каждый новый или модернизируемый skill — bundled, optional или contributed — должен соответствовать этим стандартам до merge. Reviewers отклоняют PR, нарушающие их.

1. **`description` ≤ 60 символов, одно предложение, заканчивается точкой.** Длинные descriptions раздувают skill listing UI и разбавляют внимание модели, когда загружено много skills. State capability, не implementation. Без marketing words («мощный», «комплексный», «бесшовный», «продвинутый»). Не повторяйте name skill. Проверьте:
   ```python
   import re, pathlib
   m = re.search(r'^description: (.*)$',
                 pathlib.Path('skills/<cat>/<name>/SKILL.md').read_text(),
                 re.MULTILINE)
   assert len(m.group(1)) <= 60, len(m.group(1))
   ```

   Хорошо: `Search arXiv papers by keyword, author, category, or ID.`
   Плохо: `Мощный и комплексный skill, позволяющий агенту искать arXiv по релевантным академическим статьям, используя различные критерии, включая ключевые слова, авторов и категории.`

2. **Tools, упомянутые в SKILL.md prose, должны быть native Prostor tools или MCP servers, которые skill явно ожидает.** Когда skill нуждается в возможности, указывайте proper tool по имени в backticks: `` `terminal` ``, `` `web_extract` ``, `` `web_search` ``, `` `read_file` ``, `` `write_file` ``, `` `patch` ``, `` `search_files` ``, `` `vision_analyze` ``, `` `browser_navigate` ``, `` `delegate_task` ``, `` `image_generate` ``, `` `text_to_speech` ``, `` `cronjob` ``, `` `memory` ``, `` `skill_view` ``, `` `todo` ``, `` `execute_code` ``.

   НЕ называйте shell utilities, которые агент уже обёрнул:

   | Не говорите | Говорите |
   |---|---|
   | `grep`, `rg` | `search_files` |
   | `cat`, `head`, `tail` | `read_file` |
   | `sed`, `awk` | `patch` |
   | `find`, `ls` | `search_files` (с `target='files'`) |
   | `curl` для извлечения контента | `web_extract` |
   | `echo > file`, `cat <<EOF` | `write_file` |

   Если skill зависит от MCP server, назовите MCP server и задокументируйте setup в `## Prerequisites`. Third-party CLIs (например, `ffmpeg`, `gh`, конкретный SDK) — fine для вызова из script files, но prose должна frame'нуть взаимодействие как «invoke через `terminal` tool», не как ручную shell session.

3. **`platforms:` gating проверен против реальных script imports.** Skills, использующие POSIX-only primitives (`fcntl`, `termios`, `os.setsid`, `os.kill(pid, 0)` для liveness, `/proc`, хардкод `/tmp` paths, `signal.SIGKILL`, bash heredocs, `osascript`, `apt`, `systemctl`), должны декларировать поддерживаемые platforms через `platforms:` frontmatter. Дефолт — сначала попытаться cross-platform fix: `tempfile.gettmpdir()`, `pathlib.Path`, `psutil.pid_exists()`, Python-level filtering вместо `grep`. Gate на narrower set только когда зависимость genuinely platform-bound (например, `osascript` — macOS-only, `/proc` — Linux-only).

4. **`author` кредитует human contributor первым.** Для внешних контрибуций — real name + GitHub handle контрибьютора первым (`Jane Doe (jane-doe)`); "Prostor Agent" — secondary collaborator. Если commit контрибьютора показывает "Prostor Agent" как author (потому что они использовали Prostor для drafting skill), замените на actual name — кредитуйте human, не tool.

5. **SKILL.md body использует modern section order.** `# <Skill> Skill` title, 2-3 предложения intro, затем:
   - `## When to Use` — trigger conditions
   - `## Prerequisites` — env vars, install steps, MCP setup, API key sourcing
   - `## How to Run` — canonical invocation через `terminal` tool
   - `## Quick Reference` — flat command/API reference
   - `## Procedure` — numbered steps с copy-paste командами
   - `## Pitfalls` — known limits, rate limits, что выглядит сломанным, но не сломано
   - `## Verification` — single command, доказывающий, что skill работает

   Target ~200 строк для complex skill, ~100 строк для simple one. Cut redundant intro fluff, marketing prose, и re-explanations env vars уже задокументированных в `## Prerequisites`.

6. **Scripts в `scripts/`, references в `references/`, templates в `templates/`.** Не ожидайте, что модель inline-write parsers, XML walkers или non-trivial logic каждый call — ship helper script. Reference scripts из SKILL.md по path relative to skill directory.

7. **Tests живут в `tests/skills/test_<skill>_skill.py`** и используют только stdlib + pytest + `unittest.mock`. No live network calls. Run через `scripts/run_tests.sh tests/skills/test_<skill>_skill.py -q`. Must pass под hermetic CI env (no API keys leaking through). Используйте `monkeypatch` и `tmp_path` для любых env-var или filesystem зависимостей.

8. **`.env.example` additions изолированы в чётко delimited block.** Не трогайте surrounding file — contributor-supplied `.env.example` versions обычно stale, и edits вне skill's own block будут dropped при salvage. Comment all values с `#` (это documentation, не live config).

### Skill guidelines

- **Без внешних зависимостей, если абсолютно не нужно.** Предпочитайте stdlib Python, curl и существующие Prostor tools (`web_extract`, `terminal`, `read_file`).
- **Progressive disclosure.** Ставьте самый common workflow первым. Edge cases и advanced usage — внизу.
- **Включайте helper scripts** для XML/JSON parsing или complex logic — не ожидайте, что LLM пишет parsers inline каждый раз.
- **Тестируйте.** Запустите `prostor --toolsets skills -q "Use the X skill to do Y"` и verify, что агент следует инструкциям корректно.

---

## Добавление Skin / Theme

Prostor использует data-driven skin system — код не нужен для нового skin.

**Опция A: User skin (YAML-файл)**

Создайте `~/.prostor/skins/<name>.yaml`:

```yaml
name: mytheme
description: Краткое описание темы

colors:
  banner_border: "#HEX"     # Цвет border панели
  banner_title: "#HEX"      # Цвет title панели
  banner_accent: "#HEX"     # Цвет section header
  banner_dim: "#HEX"        # Цвет muted/dim text
  banner_text: "#HEX"       # Цвет body text
  response_border: "#HEX"   # Цвет border response box

spinner:
  waiting_faces: ["(⚔)", "(⛨)"]
  thinking_faces: ["(⚔)", "(⌁)"]
  thinking_verbs: ["forging", "plotting"]
  wings:                     # Опциональные left/right decorations
    - ["⟪⚔", "⚔⟫"]

branding:
  agent_name: "My Agent"
  welcome: "Welcome message"
  response_label: " ⚔ Agent "
  prompt_symbol: "⚔"

tool_prefix: "╎"             # Префикс строки tool output
```

Все fields опциональны — недостающие values наследуют от default skin.

**Опция B: Built-in skin**

Добавьте в `_BUILTIN_SKINS` dict в `prostor_cli/skin_engine.py`. Используйте ту же schema, что выше, но как Python dict. Built-in skins отгружаются с package и всегда доступны.

**Активация:**
- CLI: `/skin mytheme` или set `display.skin: mytheme` в config.yaml
- Config: `display: { skin: mytheme }`

См. `prostor_cli/skin_engine.py` для полной schema и существующих skins как примеров.

---

## Кроссплатформенная совместимость

Prostor работает на Linux, macOS и native Windows (плюс WSL2). При написании кода, затрагивающего OS, предполагайте, что *любая* платформа может попасть в ваш code path.

> **Перед PR:** запустите `scripts/check-windows-footguns.py` для поимки common Windows-unsafe patterns в вашем diff. Он grep-based и дешёвый; CI тоже запускает его на каждом PR.

### Критические правила

1. **Никогда не вызывайте `os.kill(pid, 0)` для liveness checks.** `os.kill(pid, 0)` — стандартная POSIX-идиома для проверки «жив ли этот PID» — signal 0 это no-op permission check. **На Windows это НЕ no-op.** Python Windows `os.kill` мапит `sig=0` на `CTRL_C_EVENT` (они коллидируют по integer value 0) и route'ит через `GenerateConsoleCtrlEvent(0, pid)`, который broadcast'ит Ctrl+C в **entire console process group**, содержащую target PID. «Probe if alive» silently становится «kill the target и часто unrelated processes sharing его console.» См. [bpo-14484](https://bugs.python.org/issue14484) (open с 2012 — никогда не будет fixed по compat reasons).

   **Предпочтительно:** используйте `psutil` (core dependency — всегда доступен):

   ```python
   import psutil
   if psutil.pid_exists(pid):
       # process is alive — safe на каждой платформе
       ...
   ```

   Если конкретно нужен prostor wrapper (он имеет stdlib fallback для scaffold-phase imports до завершения pip install), используйте `gateway.status._pid_exists(pid)`. Он вызывает `psutil.pid_exists` сначала и fallback'ит на hand-rolled `OpenProcess + WaitForSingleObject` dance на Windows только когда psutil somehow missing.

   Audit grep для новых callsites: `rg "os\.kill\([^,]+,\s*0\s*\)"`. Любой hit в non-test code — presumptively Windows silent-kill bug.

2. **Используйте `shutil.which()` перед shelling out — не предполагайте, что Windows имеет инструменты Linux.** `wmic` удалён в Windows 10 21H1 и позже. `ps`, `kill`, `grep`, `awk`, `fuser`, `lsof`, `pgrep` и большинство POSIX CLI tools просто не существуют на Windows. Проверяйте availability через `shutil.which("tool")` и fallback'ите на Windows-native equivalent — обычно PowerShell через `subprocess.run(["powershell", "-NoProfile", "-Command", ...])`.

   Для enumeration processes: PowerShell `Get-CimInstance Win32_Process` — современная замена `wmic process`. См. `prostor_cli/gateway.py::_scan_gateway_pids` для pattern.

3. **`termios` и `fcntl` — Unix-only.** Всегда ловите оба `ImportError` и `NotImplementedError`:
   ```python
   try:
       from simple_term_menu import TerminalMenu
       menu = TerminalMenu(options)
       idx = menu.show()
   except (ImportError, NotImplementedError):
       # Fallback: numbered menu для Windows
       for i, opt in enumerate(options):
           print(f"  {i+1}. {opt}")
       idx = int(input("Choice: ")) - 1
   ```

4. **Кодировка файлов.** Windows может сохранять `.env` файлы в `cp1252`. Всегда обрабатывайте encoding errors:
   ```python
   try:
       load_dotenv(env_path)
   except UnicodeDecodeError:
       load_dotenv(env_path, encoding="latin-1")
   ```
   Config files (`config.yaml`) могут быть сохранены с UTF-8 BOM от Notepad и подобных editors — используйте `encoding="utf-8-sig"` при чтении файлов, которые могли быть затронуты Windows GUI editor.

5. **Управление процессами.** `os.setsid()`, `os.killpg()`, `os.fork()`, `os.getuid()` и POSIX signal handling differ на Windows. Guard с `platform.system()`, `sys.platform` или `hasattr(os, "setsid")`:
   ```python
   if platform.system() != "Windows":
       kwargs["preexec_fn"] = os.setsid
   else:
       kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
   ```

   **Предпочтительно:** для killing процесса AND его children (что `os.killpg` делает на POSIX), используйте `psutil` — работает на каждой платформе:
   ```python
   import psutil
   try:
       parent = psutil.Process(pid)
       # Kill children first (leaf-up), затем parent.
       for child in parent.children(recursive=True):
           child.kill()
       parent.kill()
   except psutil.NoSuchProcess:
       pass
   ```

6. **Signals, не существующие на Windows: `SIGALRM`, `SIGCHLD`, `SIGHUP`, `SIGUSR1`, `SIGUSR2`, `SIGPIPE`, `SIGQUIT`, `SIGKILL`.** Python `signal` module raise'ает `AttributeError` при import time, если вы ссылаетесь на них на Windows. Используйте `getattr(signal, "SIGKILL", signal.SIGTERM)` или gate весь block за platform check. `loop.add_signal_handler` raise'ает `NotImplementedError` на Windows — всегда ловите.

7. **Path separators.** Используйте `pathlib.Path` вместо string concatenation с `/`. Forward slashes работают почти везде на Windows, но `subprocess.run(["cmd.exe", "/c", ...])` и другие shell contexts могут требовать backslashes — конвертируйте через `str(path)` на subprocess boundary, не внутри Python logic.

8. **Symlinks требуют elevated privileges на Windows** (если не включён Developer Mode). Тесты, создающие symlinks, нуждаются в `@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")`.

9. **POSIX file modes (0o600, 0o644 и т.д.) НЕ enforced на NTFS** по умолчанию. Тесты, assert'ящие на `stat().st_mode & 0o777`, должны skip на Windows — концепция не переводится. Используйте ACLs (`icacls`, `pywin32`) для Windows secret-file protection, если нужно.

10. **Detached background daemons на Windows нуждаются в `pythonw.exe`, НЕ `python.exe`.** `python.exe` всегда allocate'ит или attach'ится к console, что делает его уязвимым к `CTRL_C_EVENT` broadcasts от любого sibling process. `pythonw.exe` — no-console variant. Комбинируйте с `CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB` в `subprocess.Popen(creationflags=...)`. См. `prostor_cli/gateway_windows.py::_spawn_detached` для reference implementation.

11. **`subprocess.Popen` с `.cmd` или `.bat` shim'ами нуждается в `shutil.which` для resolution.** Передача `"agent-browser"` в `Popen` на Windows находит extensionless POSIX shebang shim в `node_modules/.bin/`, который `CreateProcessW` не может execute — получите `WinError 193 "not a valid Win32 application"`. Используйте `shutil.which("agent-browser", path=local_bin)`, который honor'ит PATHEXT и picks `.CMD` variant на Windows.

12. **Не используйте shell shebangs как способ запуска Python.** `#!/usr/bin/env python` работает только когда файл executed через Unix shell. `subprocess.run(["./myscript.py"])` на Windows fails даже если файл имеет shebang line. Всегда invoke Python явно: `[sys.executable, "myscript.py"]`.

13. **Shell-команды в установщиках.** Если меняете `scripts/install.sh`, сделайте эквивалентное изменение в `scripts/install.ps1`. Два скрипта — canonical example «works on Linux does not mean works on Windows» и drift'или multiple times — держите их в lockstep.

14. **Known paths, которые OneDrive-redirected на Windows:** Desktop, Documents, Pictures, Videos. «Real» path, когда OneDrive Backup enabled — `%USERPROFILE%\OneDrive\Desktop` (и т.д.), НЕ `%USERPROFILE%\Desktop` (который существует как empty husk). Resolve real location через `ctypes` + `SHGetKnownFolderPath` или чтение `Shell Folders` registry key — никогда не предполагайте `~/Desktop`.

15. **CRLF vs LF в generated scripts.** Windows `cmd.exe` и `schtasks` parse построчно; mixed или LF-only line endings могут сломать multi-line `.cmd` / `.bat` files. Используйте `open(path, "w", encoding="utf-8", newline="\r\n")` — или `open(path, "wb")` + explicit bytes — при генерации scripts, которые Windows будет execute.

16. **Две разные quoting schemes в одной command line.** `subprocess.run(["schtasks", "/TR", some_cmd])` → schtasks сам parse'ит `/TR`, И `some_cmd` string re-parse'ится `cmd.exe` когда task fires. Разные parsers, разные escape rules. Используйте два отдельных quoting helpers и никогда не cross'ите их. См. `prostor_cli/gateway_windows.py::_quote_cmd_script_arg` и `_quote_schtasks_arg` для reference pair.

### Кроссплатформенное тестирование

Тесты, использующие POSIX-only syscalls, нуждаются в skip marker. Common ones:
- Symlinks → `@pytest.mark.skipif(sys.platform == "win32", ...)`
- `0o600` file modes → `@pytest.mark.skipif(sys.platform.startswith("win"), ...)`
- `signal.SIGALRM` → Unix-only (см. `tests/conftest.py::_enforce_test_timeout`)
- `os.setsid` / `os.fork` → Unix-only
- Live Winsock / Windows-specific regression tests →
  `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific regression")`

Если monkeypatch'ите `sys.platform` для cross-platform tests, также patch `platform.system()` / `platform.release()` / `platform.mac_ver()` — каждый re-read'ит real OS независимо, поэтому half-patched tests всё ещё route через wrong branch на Windows runner.

---

## Соображения безопасности

Prostor имеет terminal access. Security matters.

### Существующие защиты

| Layer | Реализация |
|-------|-----------|
| **Sudo password piping** | Использует `shlex.quote()` для предотвращения shell injection |
| **Dangerous command detection** | Regex patterns в `tools/approval.py` с user approval flow |
| **Cron prompt injection** | Scanner в `tools/cronjob_tools.py` блокирует instruction-override patterns |
| **Write deny list** | Protected paths (`~/.ssh/authorized_keys`, `/etc/shadow`) resolved через `os.path.realpath()` для предотвращения symlink bypass |
| **Skills guard** | Security scanner для hub-installed skills (`tools/skills_guard.py`) |
| **Code execution sandbox** | `execute_code` child process runs с API keys stripped из environment |
| **Container hardening** | Docker: все capabilities dropped, no privilege escalation, PID limits, size-limited tmpfs |

### При контрибуции security-sensitive кода

- **Всегда используйте `shlex.quote()`** при интерполяции user input в shell commands
- **Resolve symlinks** через `os.path.realpath()` перед path-based access control checks
- **Не логгируйте секреты.** API keys, tokens и passwords никогда не должны появляться в log output
- **Ловите broad exceptions** вокруг tool execution, чтобы single failure не крашила agent loop
- **Тестируйте на всех платформах**, если change затрагивает file paths, process management или shell commands

Если ваш PR затрагивает security, отметьте это явно в description.

### Политика пиннинга зависимостей (supply chain hardening)

После [litellm supply chain compromise](https://github.com/BerriAI/litellm/issues/24512) в марте 2026 и [Mini Shai-Hulud worm campaign](https://socket.dev/blog/tanstack-npm-packages-compromised-mini-shai-hulud-supply-chain-attack) в мае 2026, все зависимости должны следовать этим правилам:

| Source type | Required treatment | Rationale |
|---|---|---|
| **PyPI package** | `>=floor,<next_major` | PyPI versions immutable после publish, но new versions могут быть push'нуты в ваш range. `<next_major` ceiling останавливает 1.x install от upgrade к malicious 2.0.0. |
| **Git URL** (atroposlib, tinker, yc-bench, Baileys) | Full commit SHA | Branches и tags — mutable refs; SHA — content-addressed. |
| **GitHub Actions** | Full commit SHA + version comment | Action tags — mutable refs (например tj-actions/changed-files март 2025). Pin как `uses: owner/action@<sha>  # vX.Y.Z` |
| **CI-only pip installs** | `==exact` | Hermetic CI builds; churn acceptable. |

**Каждая новая PyPI-зависимость в PR должна иметь `<next_major` upper bound.** PR с unbounded `>=X.Y.Z` specs будут отклонены reviewers. `supply-chain-audit.yml` CI workflow также flags dependency manifest changes для manual review.

**Как определить ceiling:**
- Если package на version `1.x.y`, используйте `<2`.
- Если package на version `0.x.y` (pre-1.0), используйте `<0.(current_minor + 2)` — например, если current `0.29.x`, используйте `<0.32`. Это даёт ~2 minor versions headroom, держа window достаточно малым, что hostile takeover version unlikely land inside.
- Exception: packages с очень стабильными APIs (например, `aiohttp-socks`) могут использовать `<1` на reviewer discretion.

**Примеры:**
```toml
# ✅ Correct — post-1.0
"openai>=2.21.0,<3"
"pydantic>=2.12.5,<3"

# ✅ Correct — pre-1.0 (tight minor window)
"asyncpg>=0.29,<0.32"
"aiosqlite>=0.20,<0.23"
"hindsight-client>=0.4.22,<0.5"

# ❌ Rejected — no upper bound
"some-package>=1.2.3"

# ❌ Rejected — too tight (blocks legitimate patches)
"some-package==1.2.3"

# ❌ Rejected — too loose для pre-1.0 (allows 80 minor versions)
"some-package>=0.20,<1"
```

**Reference PRs:** #2796 (litellm removal), #2810 (upper bounds pass), #9801 (SHA pinning + supply-chain-audit CI).

---

## Процесс Pull Request

### Именование веток

```
fix/description        # Bug fixes
feat/description       # New features
docs/description       # Documentation
test/description       # Tests
refactor/description   # Code restructuring
```

### Перед отправкой

1. **Запустите тесты**: `scripts/run_tests.sh` (recommended; same as CI) или `pytest tests/ -v` с активированным project venv
2. **Протестируйте вручную**: Запустите `prostor` и проверьте code path, который вы изменили
3. **Проверьте кроссплатформенное влияние**: Если затрагиваете file I/O, process management или terminal handling, рассмотрите macOS, Linux и WSL2
4. **Держите PR focused**: Одно логическое изменение на PR. Не смешивайте bug fix с refactor с new feature.

### Описание PR

Включите:
- **Что** изменилось и **почему**
- **Как тестировать** (reproduction steps для bugs, usage examples для features)
- **На каких платформах** вы тестировали
- Reference на related issues, если есть

### Commit messages

Мы используем [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

| Type | Использовать для |
|------|---------|
| `fix` | Bug fixes |
| `feat` | New features |
| `docs` | Documentation |
| `test` | Tests |
| `refactor` | Code restructuring (no behavior change) |
| `chore` | Build, CI, dependency updates |

Scopes: `cli`, `gateway`, `tools`, `skills`, `agent`, `install`, `whatsapp`, `security` и т.д.

Примеры:
```
fix(cli): prevent crash in save_config_value when model is a string
feat(gateway): add WhatsApp multi-user session isolation
fix(security): prevent shell injection in sudo password piping
test(tools): add unit tests for file_operations
```

---

## Отчёт об ошибках

- Используйте [GitHub Issues](https://github.com/maksim9510/Prostor/issues)
- Включите: OS, Python version, Prostor version (`prostor version`), полный error traceback
- Включите steps для воспроизведения
- Проверьте существующие issues перед созданием дубликатов
- Для security vulnerabilities, пожалуйста, сообщайте приватно

---

## Сообщество

- **Discord**: [discord.gg/NousResearch](https://discord.gg/NousResearch) — для вопросов, демонстрации проектов и обмена skills
- **GitHub Discussions**: Для design proposals и архитектурных обсуждений
- **Skills Hub**: Загружайте специализированные skills в реестр и делитесь с сообществом

---

## Лицензия

Контрибьютя, вы соглашаетесь, что ваши контрибуции будут лицензированы под [MIT License](LICENSE).