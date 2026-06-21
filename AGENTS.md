# Prostor Agent — Руководство для разработчиков

Инструкции для AI-ассистентов и разработчиков, работающих с кодовой базой prostor-agent.

**Никогда не сдавайтесь в поисках правильного решения.**

## Что такое Prostor

Prostor — персональный AI-агент, который запускает одно и то же ядро в CLI,
messaging gateway (Telegram, Discord, Slack и ~20 других платформах), TUI
и Electron-приложении. Он обучается между сессиями (память + навыки),
делегирует субагентам, выполняет запланированные задачи и управляет
настоящим терминалом и браузером. Расширяется в основном через **плагины
и навыки**, а не разрастанием ядра.

Два свойства определяют почти каждое архитектурное решение и являются
критерием review любых изменений:

- **Per-conversation prompt caching неприкосновенен.** Долгоживущий разговор
  повторно использует кэшированный префикс каждый ход. Всё, что мутирует
  прошлый контекст, меняет toolset или пересобирает system prompt
  mid-conversation, инвалидирует кэш и умножает стоимость для пользователя.
  Мы этого не делаем (единственное исключение — сжатие контекста).
- **Ядро — узкая талия; возможности живут на краях.** Каждый model tool,
  который мы добавляем, отправляется на каждый API-вызов, поэтому планка для
  нового *core* tool высокая. Большинство новых возможностей должно
  приходить как CLI-команда + skill, service-gated tool или плагин — а не
  как core surface.

## Рубрика контрибуции — что мы хотим / чего не хотим

Это intent layer проекта. Используйте двумя способами:

1. **Для людей и для собственной работы** — что мержится, а что
   отклоняется, чтобы контрибуция попадала в цель.
2. **Для автоматического review (триаж-свипер)** — руководство, когда PR
   безопасно закрыть по трём разрешённым причинам (`implemented_on_main`,
   `cannot_reproduce`, `incoherent`) и, что не менее важно, **когда НЕ
   закрывать** PR. Вкус-based «мы это не хотим / вне scope» закрытия — НЕ
   автоматическое решение, оно остаётся за человеком-мейнтейнером. Задача
   свипера — распознать design intent и *избежать ошибочного закрытия
   легитимной контрибуции*, а не делать вызов won't-implement.

Читайте баланс верно: Prostor отгружает **много** — большинство мержей — это
bug fix'ы к реально сообщённому поведению, а продуктовая поверхность
(платформы, каналы, провайдеры, модели, desktop/TUI-фичи) расширяется
агрессивно и намереренно. Ограничения ниже направлены исключительно на
**core agent + model tool schema** — единственное место, где каждое
добавление оплачивается на каждом API-вызове. «Smallest footprint»
управляет *как возможность встроена в ядро*, а НЕ тем, разрешено ли продукту
расти. Мы экспансивны на краях и консервативны в талии.

### Что мы хотим

- **Хорошо фиксить реальные баги.** Основная масса — `fix(...)` против
  реального сообщённого симптома. Хороший фикс воспроизводит симптом на
  текущем `main`, указывает на точную строку, где он проявляется, и фиксит
  весь класс багов — включая смежные пути — а не только тот, на который
  наткнулся репортер.
- **Расширять охват на краях.** Новые платформенные адаптеры, каналы,
  провайдеры, модели и desktop/TUI/dashboard-фичи приветствуются и
  мержатся регулярно, включая крупные (новый messaging-канал, session-cap
  фича, Windows PTY-мост). Широта продукта — цель, а не footprint-concern —
  при условии, что интеграция идёт через существующий setup/config UX
  (`prostor tools`, `prostor setup`, auto-install), а не через сырую env var.
- **Рефакторить god-файлы в чистые модули.** Извлечение много-тысячестрочного
  кластера из `cli.py` / `run_agent.py` / `gateway/run.py` в фокусный mixin
  или модуль — желанная работа, даже если diff огромный и механический
  (крупные `+N/-N` рефакторы мержатся регулярно). Тест «каждая строка ведёт
  к запросу» применяется к *feature* PR; запрос объявленного рефактора — это
  извлечение.
- **Держать ядро узким.** Новые *model tools* — дорогое исключение: каждый
  tool уходит на каждом API-вызове. Предпочтение по порядку: расширить
  существующий код → CLI-команда + skill → service-gated tool (`check_fn`) →
  плагин → MCP server в каталоге → новый core tool (последнее средство).
  См. «Footprint Ladder».
- **Расширять, не дублировать.** Перед добавлением модуля/manager/hook
  проверьте, не покрывает ли существующая инфраструктура этот use case.
  Когда несколько PR интегрируют одну *категорию*, спроектируйте один общий
  интерфейс, а не мержите их по одному (см. ABC + orchestrator note под
  Footprint Ladder).
- **Контракты поведения, а не снапшоты.** Тесты должны проверять, как две
  части данных должны соотноситься (инварианты), а не замораживать текущее
  значение (списки моделей, литералы версий config, counts перечислений).
  См. «Не пишите change-detector тесты».
- **E2E-валидация, а не только зелёные unit-моки.** Для всего, что касается
  resolution chains, распространения конфига, security boundaries, удалённых
  бэкендов или file/network I/O, гоните реальный путь с реальными импортами
  против temp `PROSTOR_HOME`. Моки скрывают интеграционные баги.
- **Cache-, alternation- и invariant-safe.** Сохраняйте prompt caching, строгую
  ролевую альтернацию сообщений (никогда два same-role сообщения подряд; никогда
  синтетическое user message, инжектированное mid-loop), и system prompt,
  байт-стабильный в течение жизни разговора.
- **Кредит контрибьютора сохранён.** Спасайте внешнюю работу через
  cherry-pick (rebase-merge), чтобы авторство сохранялось в git history;
  не переписывайте с нуля, если можно строить поверх.

### Чего мы не хотим (отклоняется даже при качественной реализации)

- **Спекулятивная инфраструктура.** Хуки, callback'и или точки расширения без
  конкретного потребителя. Добавить хук легко; удалить после того, как плагины
  зависят от него — сложно. Хук НЕ спекулятивный, если у контрибьютора есть
  реальный, заявленный use case — даже если потребитель отгружается отдельно.
- **Новые `PROSTOR_*` env vars для non-secret конфигурации.** `.env` — только
  для секретов (API-ключи, токены, пароли). Все поведенческие настройки —
  таймауты, пороги, feature flags, display prefs — идут в `config.yaml`.
  Бриджите во внутреннюю env var, если механизм требует, но user-facing docs
  указывают на `config.yaml`. Отклоняйте PR, которые говорят пользователям
  «установите X в .env», если X — не credential.
- **Новый core tool, когда terminal + file уже справляются, или когда справился
  бы skill.** Если единственный барьер — видимость файлов на удалённом бэкенде,
  фиксите mount, а не toolset.
- **Lazy-reading escape hatches на instructional tools.** Никакой
  `offset`/`limit` пагинации на инструментах, загружающих контент, который
  агент должен прочитать полностью (skills, prompts, playbooks). Модели
  прочитают страницу 1 и пропустят остальное.
- **«Фиксы», убивающие фичу, которую они защищают.** Митигация, убивающая
  назначение фичи — неправильная митигация. Читайте intent оригинального
  коммита (`git log -p -S`) до ограничения поведения; найдите фикс,
  сохраняющий фичу.
- **Outbound telemetry / usage attribution без opt-in gating.** Никакой
  новой аналитики, сторонней идентификации или attribution tags, пока не
  существует generic user-facing opt-in (config gate + setup prompt +
  `prostor tools` toggle). Паркуйте за label, не мержите.
- **Change-detector тесты, cache-breaking mid-conversation, мёртвый код,
  подключённый без E2E-доказательств, и плагины, трогающие core-файлы.**
  Плагины живут в своей директории и работают в рамках предоставленных
  ABCs/hooks; если плагину нужно больше — расширяйте generic plugin surface,
  а не специализируйте в core.

### Прежде чем назвать это багом — проверьте предпосылку (и когда НЕ закрывать)

Самая частая причина закрытия хорошо написанного PR — не качество кода, а то,
что изменение построено на **неверной предпосылке** или трактует
**намеренный дизайн как пробел**. Эти паттерны работают в обе стороны: они
подсказывают human-reviewer'у, что scrutinize, и automated sweeper'у, когда PR
НЕ безопасно закрывать как `implemented_on_main` / `cannot_reproduce` (в
сомнениях — оставляйте человеку). Они дистиллированы из реальных закрытий.

- **«Намеренный дизайн, а не пробел.»** Ограничение, выглядящее как упущение,
  часто сделано специально. Перед «фиксом» недостающего звена или ограничения
  спросите, не является ли изоляция дизайном. Пример: profiles — независимые
  острова намеренно — PR с live config inheritance от default profile был
  закрыт, потому что связывание профилей — именно то, что дизайн предотвращает
  (путь copy-at-creation `--clone` уже покрывает легитимный «начать с моего
  default»). Читайте intent оригинального коммита (`git log -p -S "<symbol>"`)
  прежде чем считать что-то незавершённым.
- **«Предпосылка не выдерживает проверку тем, как X реально работает.»**
  Обоснование PR часто держится на неверной ментальной модели существующего
  механизма. Трассируйте реальный код/runtime, прежде чем принимать rationale.
  Два реальных закрытия: rate-limit «re-probe during cooldown» PR (breaker
  срабатывает только на *confirmed-empty* account bucket, поэтому re-probe
  просто бьёт по bucket, который уже доказан пустым); usage-accumulation fix,
  чья новая ветка **никогда не выполняется в runtime**, потому что более
  ранний guard уже вынул состояние, от которого она зависела. Если не можете
  указать точную строку, где баг проявляется, И показать, что фикс меняет
  поведение этой строки — предпосылка не верифицирована.
- **«Этот фикс был неверным — отсутствие/упущение было намеренным.»** Добавление
  очевидно недостающего куска может сломать то, что упущение защищало. Пример:
  восстановление «недостающих» `__init__.py` файлов сделало тестовое дерево
  импортируемым как dotted package, затеняющий реальный плагин и удаляющий
  его `register()` при импорте. Отсутствие было load-bearing.
- **«Overreached / воскресил подход, от которого ушли.»** Scope creep, который
  подменяет согласованный base, или воскрешает направление, которое мейнтейнеры
  намеренно закрыли, отклоняется, даже если код работает. Держите изменение в
  узком куске, который реально был согласован; остальное предлагайте как
  фокусный follow-up.

Сквозное: **проверяйте claim И intent против кодовой базы до написания или
мержа фикса.** Подтверждённое воспроизведение на текущем `main` плюс
line-level account того, где фикс действует, побеждает правдоподобно звучащий
rationale каждый раз. В сомнениях о intent — дешевле спросить, чем отгружать
фикс, борющийся с дизайном.

### Footprint Ladder (решение о новой возможности)

Каждая ступень добавляет больше постоянной поверхности, чем предыдущая.
Выбирайте высшую (наименее footprint) ступень, корректно решающую проблему:

1. **Расширить существующий код** — возможность — вариация того, что уже есть.
   Ноль новой поверхности.
2. **CLI-команда + skill** — управляет config/state/infra, выразимым как shell
   команды. Агент запускает `prostor <subcommand>` под управлением skill. Ноль
   model-tool footprint. Дефолт для подписок, scheduled tasks, service setup.
   Примеры: `prostor webhook`, `prostor cron`, `prostor tools`.
3. **Service-gated tool (`check_fn`)** — нужны структурированные params/returns
   И появляется только когда prerequisite настроен. Ноль footprint в остальном.
   Примеры: Home Assistant tools (gated on token), memory-provider tools.
4. **Плагин** — third-party/niche/user-specific возможность, не отгружается в
   core. Живёт в `~/.prostor/plugins/` или pip-пакете, обнаруживается в runtime.
5. **MCP server (в каталоге)** — если возможность действительно должна быть
   tool (структурированный I/O, который агент вызывает), но не core-fundamental,
   предпочитайте MCP server в каталоге росту core toolset. Агент подключается
   через встроенный MCP-клиент; ноль постоянного core-schema footprint, и
   переиспользуемо любым MCP-хостом.
6. **Новый core tool** — только когда возможность фундаментальна, широко полезна
   почти каждому пользователю и недостижима через terminal + file (или MCP
   server). Примеры корректных core tools: terminal, read_file, web_search,
   browser_navigate.

Когда 3+ открытых PR пытаются интегрировать одну *категорию* (memory backends,
providers, notifiers), не мержите по одному — спроектируйте ABC + orchestrator,
оберните существующий built-in как первого provider и превратите конкурирующие
PR в плагины против этого интерфейса.

## Среда разработки

```bash
# Предпочитайте .venv; fallback на venv, если у вашего checkout его нет.
source .venv/bin/activate   # или: source venv/bin/activate
```

`scripts/run_tests.sh` пробует `.venv`, затем `venv`, затем
`$HOME/.prostor/prostor-agent/venv` (для worktree, разделяющих venv с
основным checkout).

## Структура проекта

Количество файлов меняется постоянно — не считайте дерево ниже исчерпывающим.
Канонический источник — файловая система. Комментарии отмечают load-bearing
точки входа, которые вы реально будете редактировать.

```
prostor-agent/
├── run_agent.py          # Класс AIAgent — основной цикл разговора (~12k LOC)
├── model_tools.py        # Оркестрация инструментов, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # Определения toolset, список _PROSTOR_CORE_TOOLS
├── cli.py                # Класс ProstorCLI — интерактивный CLI-оркестратор (~11k LOC)
├── prostor_state.py       # SessionDB — SQLite-хранилище сессий (FTS5-поиск)
├── prostor_constants.py   # get_prostor_home(), display_prostor_home() — пути с учётом профилей
├── prostor_logging.py     # setup_logging() — agent.log / errors.log / gateway.log (с учётом профилей)
├── batch_runner.py       # Параллельная пакетная обработка
├── agent/                # Внутренности агента (адаптеры провайдеров, память, кэширование, сжатие)
├── prostor_cli/           # CLI-подкоманды, мастер настройки, загрузчик плагинов, движок скинов
├── tools/                # Реализации инструментов — автообнаружение через tools/registry.py
│   └── environments/     # Терминальные бэкенды (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging gateway — run.py + session.py + platforms/
│   ├── platforms/        # Адаптеры по платформам (telegram, discord, slack, whatsapp,
│   │                     #   homeassistant, signal, matrix, mattermost, email, sms,
│   │                     #   dingtalk, wecom, weixin, feishu, qqbot, bluebubbles,
│   │                     #   yuanbao, webhook, api_server, ...). См. ADDING_A_PLATFORM.md.
│   └── builtin_hooks/    # Точка расширения для всегда-зарегистрированных gateway-хуков
├── plugins/              # Система плагинов (см. раздел «Плагины» ниже)
│   ├── memory/           # Плагины memory-provider (honcho, mem0, supermemory, ...)
│   ├── context_engine/   # Плагины context-engine
│   ├── model-providers/  # Плагины inference backend (openrouter, anthropic, gmi, ...)
│   ├── kanban/           # Multi-agent board dispatcher + worker plugin
│   ├── prostor-achievements/  # Геймифицированный tracking достижений
│   ├── observability/    # Плагин метрик / трейсов / логов
│   ├── image_gen/        # Плагины генерации изображений
│   └── <others>/         # disk-cleanup, google_meet, platforms, spotify,
│                         #   strike-freedom-cockpit, ...
├── optional-skills/      # Тяжёлые/нишевые навыки, отгружаемые, но НЕ активные по умолчанию
├── skills/               # Встроенные навыки, поставляемые с репозиторием
├── ui-tui/               # Ink (React) терминальный UI — `prostor --tui`
│   └── src/              # entry.tsx, app.tsx, gatewayClient.ts + app/components/hooks/lib
├── tui_gateway/          # Python JSON-RPC бэкенд для TUI
├── acp_adapter/          # ACP-сервер (интеграция VS Code / Zed / JetBrains)
├── cron/                 # Планировщик — jobs.py, scheduler.py
├── scripts/              # run_tests.sh, release.py, вспомогательные скрипты
├── website/              # Docusaurus-сайт документации
└── tests/                # Набор pytest (~17k тестов в ~900 файлах по состоянию на май 2026)
```

**Конфигурация пользователя:** `~/.prostor/config.yaml` (настройки),
`~/.prostor/.env` (только API-ключи).
**Логи:** `~/.prostor/logs/` — `agent.log` (INFO+), `errors.log` (WARNING+),
`gateway.log` при работе gateway. С учётом профилей через `get_prostor_home()`.
Просмотр: `prostor logs [--follow] [--level ...] [--session ...]`.

## TypeScript-стиль

Применяется к TypeScript во всём Prostor: desktop, TUI, website и будущим TS-пакетам.

- Предпочитайте небольшие nanostores вместо component state, когда state
  разделяется, переиспользуется или читается удалённым UI.
- Каждый feature владеет своими atoms. Chat state — рядом с chat, shell state —
  рядом с shell, shared state — в `src/store`.
- Компоненты, рендерящие из atom, используют `useStore`. Non-rendering actions
  читают через `$atom.get()`.
- Не прокидывайте state через три компонента, если leaf может подписаться на atom.
- Держите персистентность рядом с atom, владеющим ей.
- Держите route roots тонкими. Они компонуют routes и shell; не должны становиться
  контроллерами.
- Никаких монолитных hooks. Hook должен владеть одной узкой задачей.
- Предпочитайте colocated action-модули скрытым god hooks.
- Если callback — чистый side effect, используйте terse void form:
  `onState={st => void setGatewayState(st)}`.
- Async UI handlers должны делать intent явным:
  `onClick={() => void save()}`.
- Предпочитайте interfaces для public props и shared object shapes. Избегайте
  `type X = { ... }` для object props.
- Расширяйте React primitives для props: `React.ComponentProps<'button'>`,
  `React.ComponentProps<typeof Dialog>`, `Omit<...>`, `Pick<...>`.
- Table-driven превосходит condition ladders при маппинге id, routes, views.
- `src/app` владеет routes, pages и page-specific компонентами.
- `src/store` владеет shared atoms.
- `src/lib` владеет shared pure helpers.

## Цепочка файловых зависимостей

```
tools/registry.py  (нет deps — импортируется всеми tool-файлами)
       ↑
tools/*.py  (каждый вызывает registry.register() при импорте)
       ↑
model_tools.py  (импортирует tools/registry + запускает tool discovery)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

---

## Класс AIAgent (run_agent.py)

Реальный `AIAgent.__init__` принимает ~60 параметров (credentials, routing,
callbacks, session context, budget, credential pool и т.д.). Сигнатура ниже —
минимальное подмножество, которое вы обычно будете трогать — читайте
`run_agent.py` для полного списка.

```python
class AIAgent:
    def __init__(self,
        base_url: str = None,
        api_key: str = None,
        provider: str = None,
        api_mode: str = None,              # "chat_completions" | "codex_responses" | ...
        model: str = "",                   # пусто → резолвится из config/provider позже
        max_iterations: int = 90,          # итерации tool-calling (shared с субагентами)
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,              # "cli", "telegram", и т.д.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        credential_pool=None,
        # ... плюс callbacks, thread/user/chat IDs, iteration_budget, fallback_model,
        # checkpoints config, prefill_messages, service_tier, reasoning_config, и т.д.
    ): ...

    def chat(self, message: str) -> str:
        """Простой интерфейс — возвращает финальную строку ответа."""

    def run_conversation(self, user_message: str, system_message: str = None,
                         conversation_history: list = None, task_id: str = None) -> dict:
        """Полный интерфейс — возвращает dict с final_response + messages."""
```

### Цикл агента

Основной цикл внутри `run_conversation()` — полностью синхронный, с проверками
прерывания, tracking бюджетом и one-turn grace call:

```python
while (api_call_count < self.max_iterations and self.iteration_budget.remaining > 0) \
        or self._budget_grace_call:
    if self._interrupt_requested: break
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Сообщения в формате OpenAI: `{"role": "system/user/assistant/tool", ...}`.
Reasoning content хранится в `assistant_msg["reasoning"]`.

---

## Архитектура CLI (cli.py)

- **Rich** для banner/panels, **prompt_toolkit** для ввода с автодополнением
- **KawaiiSpinner** (`agent/display.py`) — анимированные лица во время API-вызовов,
  `┊` activity feed для результатов инструментов
- `load_cli_config()` в cli.py мержит хардкод default'ы + user config YAML
- **Skin engine** (`prostor_cli/skin_engine.py`) — data-driven CLI-темы; инициализируется
  из `display.skin` config key при старте; скины кастомизируют цвета баннера,
  спиннер faces/verbs/wings, префикс инструментов, response box, branding text
- `process_command()` — метод на `ProstorCLI` — диспетчеризует по canonical command name,
  резолвимому через `resolve_command()` из центрального registry
- Skill slash-команды: `agent/skill_commands.py` сканирует `~/.prostor/skills/`,
  инжектирует как **user message** (не system prompt) для сохранения prompt caching

### Slash Command Registry (`prostor_cli/commands.py`)

Все slash-команды определены в центральном `COMMAND_REGISTRY` — список `CommandDef`
объектов. Каждый downstream consumer наследует из этого registry автоматически:

- **CLI** — `process_command()` резолвит алиасы через `resolve_command()`,
  диспетчеризует по canonical name
- **Gateway** — `GATEWAY_KNOWN_COMMANDS` frozenset для хук-эмиссии, `resolve_command()`
  для диспетчеризации
- **Gateway help** — `gateway_help_lines()` генерирует `/help` output
- **Telegram** — `telegram_bot_commands()` генерирует BotCommand menu
- **Slack** — `slack_subcommand_map()` генерирует `/prostor` subcommand routing
- **Autocomplete** — `COMMANDS` flat dict feeds `SlashCommandCompleter`
- **CLI help** — `COMMANDS_BY_CATEGORY` dict feeds `show_help()`

### Добавление slash-команды

1. Добавьте `CommandDef` в `COMMAND_REGISTRY` в `prostor_cli/commands.py`:
```python
CommandDef("mycommand", "Описание что делает", "Session",
           aliases=("mc",), args_hint="[arg]"),
```
2. Добавьте handler в `ProstorCLI.process_command()` в `cli.py`:
```python
elif canonical == "mycommand":
    self._handle_mycommand(cmd_original)
```
3. Если команда доступна в gateway, добавьте handler в `gateway/run.py`:
```python
if canonical == "mycommand":
    return await self._handle_mycommand(event)
```
4. Для персистентных настроек используйте `save_config_value()` в `cli.py`

**Поля CommandDef:**
- `name` — canonical name без слэша (напр. `"background"`)
- `description` — human-readable описание
- `category` — один из `"Session"`, `"Configuration"`, `"Tools & Skills"`, `"Info"`, `"Exit"`
- `aliases` — tuple альтернативных имён (напр. `("bg",)`)
- `args_hint` — плейсхолдер аргумента в help (напр. `"<prompt>"`, `"[name]"`)
- `cli_only` — только в интерактивном CLI
- `gateway_only` — только в messaging-платформах
- `gateway_config_gate` — config dotpath (напр. `"display.tool_progress_command"`);
  когда установлен на `cli_only`-команде, команда становится доступной в gateway,
  если config value truthy. `GATEWAY_KNOWN_COMMANDS` всегда включает config-gated
  команды, чтобы gateway мог диспетчеризовать; help/menus показывает их только
  когда gate открыт.

**Добавление алиаса** требует только добавления в `aliases` tuple существующего
`CommandDef`. Других изменений не нужно — dispatch, help text, Telegram menu,
Slack mapping и autocomplete обновятся автоматически.

---

## Архитектура TUI (ui-tui + tui_gateway)

TUI — полноценная замена классического (prompt_toolkit) CLI, активируется через
`prostor --tui` или `PROSTOR_TUI=1`.

### Модель процессов

```
prostor --tui
  └─ Node (Ink)  ──stdio JSON-RPC──  Python (tui_gateway)
       │                                  └─ AIAgent + tools + sessions
       └─ renders transcript, composer, prompts, activity
```

TypeScript владеет экраном. Python владеет sessions, tools, model calls и
slash-command logic.

### Транспорт

Newline-delimited JSON-RPC over stdio. Запросы из Ink, события из Python.
См. `tui_gateway/server.py` для полного каталога methods/events.

### Ключевые поверхности

| Surface | Ink компонент | Gateway метод |
|---------|---------------|----------------|
| Chat streaming | `app.tsx` + `messageLine.tsx` | `prompt.submit` → `message.delta/complete` |
| Tool activity | `thinking.tsx` | `tool.start/progress/complete` |
| Approvals | `prompts.tsx` | `approval.respond` ← `approval.request` |
| Clarify/sudo/secret | `prompts.tsx`, `maskedPrompt.tsx` | `clarify/sudo/secret.respond` |
| Session picker | `sessionPicker.tsx` | `session.list/resume` |
| Slash commands | Local handler + fallthrough | `slash.exec` → `_SlashWorker`, `command.dispatch` |
| Completions | `useCompletion` hook | `complete.slash`, `complete.path` |
| Theming | `theme.ts` + `branding.tsx` | `gateway.ready` with skin data |

### Поток slash-команд

1. Built-in клиентские команды (`/help`, `/quit`, `/clear`, `/resume`, `/copy`,
   `/paste` и т.д.) обрабатываются локально в `app.tsx`
2. Всё остальное → `slash.exec` (в persistent `_SlashWorker` subprocess) →
   `command.dispatch` fallback

### Dev-команды

```bash
cd ui-tui
npm install       # первый раз
npm run dev       # watch mode (пересобирает prostor-ink + tsx --watch)
npm start         # production
npm run build     # полная сборка (prostor-ink + tsc)
npm run typecheck # только typecheck (tsc --noEmit)
npm run lint      # eslint
npm run fmt       # prettier
npm test          # vitest
```

### TUI в Dashboard (`prostor dashboard` → `/chat`)

Dashboard встраивает реальный `prostor --tui` — **не** rewrite. См.
`prostor_cli/pty_bridge.py` + endpoint `@app.websocket("/api/pty")` в
`prostor_cli/web_server.py`.

- Браузер грузит `web/src/pages/ChatPage.tsx`, который монтирует xterm.js
  `Terminal` с WebGL renderer, `@xterm/addon-fit` для resize по контейнеру и
  `@xterm/addon-unicode11` для современных wide-character widths.
- `/api/pty?token=…` апгрейдится до WebSocket; auth использует тот же ephemeral
  `_SESSION_TOKEN` как REST, через query param (браузеры не могут установить
  `Authorization` на WS upgrade).
- Сервер спавнит то, что спавнил бы `prostor --tui`, через `ptyprocess`
  (POSIX PTY — WSL работает, native Windows — нет).
- Frames: raw PTY bytes в обе стороны; resize через `\x1b[RESIZE:<cols>;<rows>]`,
  перехватываемый на сервере и применяемый через `TIOCSWINSZ`.

**Не реимплементируйте основной chat experience в React.** Основной transcript,
composer/input flow (включая slash-command behavior) и PTY-backed terminal
принадлежат встроенному `prostor --tui` — всё новое в Ink автоматически
появляется в dashboard. Если ловите себя на перестроении transcript или composer
для dashboard — остановитесь и расширьте Ink.

**Структурированный React UI вокруг TUI разрешён, если это не второй chat surface.**
Sidebar widgets, inspectors, summaries, status panels и подобные supporting views
(напр. `ChatSidebar`, `ModelPickerDialog`, `ToolCall`) — допустимы, когда
комплементируют встроенный TUI, а не заменяют transcript / composer / terminal.
Держите их state независимым от PTY-child сессии и их failures — non-destructive,
чтобы терминальная панель продолжала работать.

### Electron Desktop Chat App (`apps/desktop/`)

**Отдельная** chat surface от классического CLI и встроенного TUI dashboard.
Electron + React + nanostore renderer (`@assistant-ui/react`), общается с
`tui_gateway` backend через JSON-RPC (`requestGateway(method, params)`). НЕ
встраивает `prostor --tui` — имеет свой composer, transcript и slash-command
pipeline. Баги desktop маршрутизируйте в навык `prostor-desktop-app-work`, не
`prostor-dashboard-work`.

**Slash-команды в desktop app курируются client-side, затем диспетчеризуются на backend.**
Пайплайн:

- **Backend уже предоставляет всё.** `tui_gateway/server.py` `commands.catalog`
  (empty-query list) и `complete.slash` (typed-query completions) включают
  built-in команды, user `quick_commands` И skill-derived команды
  (`scan_skill_commands()` / `get_skill_commands()`). Desktop app не нужен новый
  RPC для skills.
- **Renderer курирует через `apps/desktop/src/lib/desktop-slash-commands.ts`.**
  Это load-bearing файл. Содержит `DESKTOP_COMMANDS` (~19 built-ins, показанных
  в палитре) плюс block-lists для terminal-only / messaging-only / picker-owned /
  settings-owned / advanced команд, которые НЕ должны загромождать desktop popover.
  - `isDesktopSlashCommand(name)` — гейт **выполнения**. True для built-ins И для
    любого non-built-in (skill / quick command), так что typed extension commands
    запускаются.
  - `isDesktopSlashSuggestion(name)` — гейт **discovery/completion**. Используется
    BOTH completion paths в `app/chat/composer/hooks/use-slash-completions.ts`
    (empty-query catalog filter + typed-query `complete.slash` filter) и
    `filterDesktopCommandsCatalog`.
  - `isDesktopSlashExtensionCommand(name)` — true, когда команда НЕ известный
    Prostor built-in (т.е. skill или user quick command). Оба suggestion и
    catalog-filter paths пропускают extensions, так что skill commands попадают
    в палитру.
- **Dispatch** живёт в `app/session/hooks/use-prompt-actions.ts` (`runSlash`):
  built-ins, которыми владеет desktop (`/skin`, `/help`, `/new`, …), обрабатываются
  локально или через `commands.catalog`; всё остальное идёт в `slash.exec`,
  fallback на `command.dispatch` (который gateway резолвит в skill / alias / exec
  directives). Skill command резолвится в `{type: "skill", message}` и
  отправляется как обычный prompt.

**Правило:** курирование desktop slash palette — про скрытие шума (terminal-only /
messaging-only built-ins), НЕ про скрытие user-activated extensions. Skill commands
и `quick_commands` — extensions, которые backend surfaces; они принадлежат
completions. Если затягиваете `desktop-slash-commands.ts`, держите
`isDesktopSlashExtensionCommand` протекающим в оба suggestion и catalog-filter paths.
Тесты: `apps/desktop/src/lib/desktop-slash-commands.test.ts` (через repo-root `vitest`,
т.к. `apps/desktop` резолвит deps из root workspace install).

---

## Добавление новых инструментов

Перед добавлением любого tool сначала решите footprint-вопрос (см.
«Footprint Ladder» в Rubric контрибуции): большинство возможностей НЕ должно быть
core tools. Для custom или local-only tools **не** редактируйте Prostor core.
Используйте plugin-маршрут: создайте `~/.prostor/plugins/<name>/plugin.yaml` и
`~/.prostor/plugins/<name>/__init__.py`, затем регистрируйте tools через
`ctx.register_tool(...)`. Plugin toolset'ы обнаруживаются автоматически и могут
включаться/выключаться без touches `tools/` или `toolsets.py`.

Используйте built-in маршрут ниже, только если пользователь явно контрибьютит
новый core Prostor tool, который должен отгружаться в базовой системе.

Built-in/core tools требуют изменений в **2 файлах**:

**1. Создайте `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Добавьте в `toolsets.py`** — либо `_PROSTOR_CORE_TOOLS` (все платформы),
либо новый toolset. **Этот шаг обязателен:** auto-discovery импортирует tool и
регистрирует его schema, но tool *экспонируется агенту* только если его имя
появляется в toolset. `_PROSTOR_CORE_TOOLS` — не мёртвый код; это default bundle,
от которого наследует base toolset каждой платформы.

Auto-discovery: любой `tools/*.py` файл с top-level `registry.register()` вызовом
импортируется автоматически — нет ручного import list. Wiring в toolset —
по-прежнему deliberate, ручной шаг.

Registry обрабатывает schema collection, dispatch, availability checking и
error wrapping. Все handlers MUST возвращать JSON string.

**Path references в tool schemas:** если описание schema упоминает файловые пути
(напр. дефолтные output-директории), используйте `display_prostor_home()` для
profile-aware. Schema генерируется при import time, после `_apply_profile_override()`,
который устанавливает `PROSTOR_HOME`.

**State files:** если tool хранит персистентное state (кэши, логи, checkpoints),
используйте `get_prostor_home()` для base directory — никогда `Path.home() / ".prostor"`.
Это гарантирует каждому профилю своё state.

**Agent-level tools** (todo, memory): перехватываются `run_agent.py` до
`handle_function_call()`. См. `tools/todo_tool.py` для паттерна.

---

## Политика пиннинга зависимостей

Все зависимости должны иметь upper bounds для ограничения surface supply-chain
атак. Политика установлена после litellm compromise (PR #2796, #2810) и
усилена после Mini Shai-Hulud worm campaign (май 2026).

| Source type | Treatment | Example |
|---|---|---|
| PyPI package | `>=floor,<next_major` | `"httpx>=0.28.1,<1"` |
| Git URL | Commit SHA | `git+https://...@<40-char-sha>` |
| GitHub Actions | Commit SHA + comment | `uses: actions/checkout@<sha>  # v4` |
| CI-only pip | `==exact` | `pyyaml==6.0.2` |

**При добавлении новой зависимости в `pyproject.toml`:**
1. Пин `>=current_version,<next_major` для post-1.0 (напр. `>=1.5.0,<2`).
2. Для pre-1.0 пакетов используйте `<0.(current_minor + 2)` (напр. `>=0.29,<0.32`).
3. Никогда не коммитьте bare `>=X.Y.Z` без ceiling — CI и reviewers отклонят.
4. Запустите `uv lock` для регенерации `uv.lock` с хешами.

Reference: #2810 (bounds pass), #9801 (SHA pinning + audit CI).

---

## Добавление конфигурации

### Опции config.yaml:
1. Добавьте в `DEFAULT_CONFIG` в `prostor_cli/config.py`
2. Бампите `_config_version` (проверьте текущее значение в начале `DEFAULT_CONFIG`)
   ТОЛЬКО если нужно активно мигрировать/трансформировать существующий user config
   (переименование ключей, изменение структуры). Добавление нового ключа в
   существующую section обрабатывается автоматически через deep-merge и НЕ
   требует version bump.

### Top-level `config.yaml` sections (не exhaustive):

`model`, `agent`, `terminal`, `compression`, `display`, `stt`, `tts`,
`memory`, `security`, `delegation`, `smart_model_routing`, `checkpoints`,
`auxiliary`, `curator`, `skills`, `gateway`, `logging`, `cron`, `profiles`,
`plugins`, `honcho`.

`auxiliary` хранит per-task override'ы для side-LLM работы (curator, vision,
embedding, title generation, session_search и т.д.) — каждая task может пинить
свой provider/model/base_url/max_tokens/reasoning_effort. См.
`agent/auxiliary_client.py::_resolve_auto` для порядка resolution.

`curator` хранит background skill-maintenance config —
`enabled`, `interval_hours`, `min_idle_hours`, `stale_after_days`,
`archive_after_days`, `backup` (nested).

### .env variables (ТОЛЬКО СЕКРЕТЫ — API-ключи, токены, пароли):
1. Добавьте в `OPTIONAL_ENV_VARS` в `prostor_cli/config.py` с metadata:
```python
"NEW_API_KEY": {
    "description": "Для чего",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
},
```

Non-secret настройки (timeouts, thresholds, feature flags, paths, display
preferences) принадлежат `config.yaml`, не `.env`. Если внутренний код требует
env var mirror для backward compatibility, бриджите из `config.yaml` в env var
в коде (см. `gateway_timeout`, `terminal.cwd` → `TERMINAL_CWD`).

### Config loaders (три пути — знайте, в каком вы):

| Loader | Используется | Location |
|--------|---------|----------|
| `load_cli_config()` | CLI mode | `cli.py` — мержит CLI-specific defaults + user YAML |
| `load_config()` | `prostor tools`, `prostor setup`, большинство CLI subcommands | `prostor_cli/config.py` — мержит `DEFAULT_CONFIG` + user YAML |
| Direct YAML load | Gateway runtime | `gateway/run.py` + `gateway/config.py` — читает user YAML raw |

Если добавили новый ключ и CLI видит его, а gateway — нет (или наоборот), вы
на неправильном loader. Проверьте coverage `DEFAULT_CONFIG`.

### Working directory:
- **CLI** — использует process's current directory (`os.getcwd()`).
- **Messaging** — использует `terminal.cwd` из `config.yaml`. Gateway бриджит это
  в `TERMINAL_CWD` env var для child tools. **`MESSAGING_CWD` удалён** — config
  loader печатает deprecation warning, если он установлен в `.env`. То же для
  `TERMINAL_CWD` в `.env`; canonical setting — `terminal.cwd` в `config.yaml`.

---

## Skin/Theme система

Skin engine (`prostor_cli/skin_engine.py`) — data-driven CLI visual customization.
Скины — **pure data**, код не нужен для нового skin.

### Архитектура

```
prostor_cli/skin_engine.py    # SkinConfig dataclass, built-in skins, YAML loader
~/.prostor/skins/*.yaml       # User-installed custom skins (drop-in)
```

- `init_skin_from_config()` — вызывается при CLI startup, читает `display.skin`
- `get_active_skin()` — возвращает кэшированный `SkinConfig` для текущего skin
- `set_active_skin(name)` — переключает skin в runtime (используется `/skin`)
- `load_skin(name)` — грузит из user skins, затем built-ins, затем fallback
- Недостающие skin values наследуют от `default` skin автоматически

### Что скины кастомизируют

| Element | Skin Key | Used By |
|---------|----------|---------|
| Banner panel border | `colors.banner_border` | `banner.py` |
| Banner panel title | `colors.banner_title` | `banner.py` |
| Banner section headers | `colors.banner_accent` | `banner.py` |
| Banner dim text | `colors.banner_dim` | `banner.py` |
| Banner body text | `colors.banner_text` | `banner.py` |
| Response box border | `colors.response_border` | `cli.py` |
| Spinner faces (waiting) | `spinner.waiting_faces` | `display.py` |
| Spinner faces (thinking) | `spinner.thinking_faces` | `display.py` |
| Spinner verbs | `spinner.thinking_verbs` | `display.py` |
| Spinner wings (optional) | `spinner.wings` | `display.py` |
| Tool output prefix | `tool_prefix` | `display.py` |
| Per-tool emojis | `tool_emojis` | `display.py` → `get_tool_emoji()` |
| Agent name | `branding.agent_name` | `banner.py`, `cli.py` |
| Welcome message | `branding.welcome` | `cli.py` |
| Response box label | `branding.response_label` | `cli.py` |
| Prompt symbol | `branding.prompt_symbol` | `cli.py` |

### Built-in skins

- `default` — Классический Prostor gold/kawaii (текущий look)
- `ares` — Малиново-бронзовая тема бога войны с кастомными spinner wings
- `mono` — Чистый grayscale monochrome
- `slate` — Прохладная blue developer-focused тема

### Добавление built-in skin

Добавьте в `_BUILTIN_SKINS` dict в `prostor_cli/skin_engine.py`:

```python
"mytheme": {
    "name": "mytheme",
    "description": "Короткое описание",
    "colors": { ... },
    "spinner": { ... },
    "branding": { ... },
    "tool_prefix": "┊",
},
```

### User skins (YAML)

Users создают `~/.prostor/skins/<name>.yaml`:

```yaml
name: cyberpunk
description: Neon-soaked terminal theme

colors:
  banner_border: "#FF00FF"
  banner_title: "#00FFFF"
  banner_accent: "#FF1493"

spinner:
  thinking_verbs: ["jacking in", "decrypting", "uploading"]
  wings:
    - ["⟨⚡", "⚡⟩"]

branding:
  agent_name: "Cyber Agent"
  response_label: " ⚡ Cyber "

tool_prefix: "▏"
```

Активация: `/skin cyberpunk` или `display.skin: cyberpunk` в config.yaml.

---

## Плагины

У Prostor две plugin surfaces. Обе живут в `plugins/` в репо, поэтому
repo-shipped plugins обнаруживаются рядом с user-installed в
`~/.prostor/plugins/` и pip entry points.

### General plugins (`prostor_cli/plugins.py` + `plugins/<name>/`)

`PluginManager` обнаруживает плагины в `~/.prostor/plugins/`, `./.prostor/plugins/`,
и pip entry points. Каждый плагин exposes функцию `register(ctx)`, которая может:

- Регистрировать Python-callback lifecycle hooks:
  `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`,
  `on_session_start`, `on_session_end`
- Регистрировать новые tools через `ctx.register_tool(...)`
- Регистрировать CLI subcommands через `ctx.register_cli_command(...)` —
  argparse tree плагина подключается в `prostor` при старте, так что
  `prostor <pluginname> <subcmd>` работает без изменений в `main.py`

Hooks вызываются из `model_tools.py` (pre/post tool) и `run_agent.py`
(lifecycle). **Pitfall discovery timing:** `discover_plugins()` запускается
только как side effect импорта `model_tools.py`. Code paths, читающие plugin
state без импорта `model_tools.py`, должны вызвать `discover_plugins()`
явно (идемпотент).

### Memory-provider plugins (`plugins/memory/<name>/`)

Отдельная система discovery для pluggable memory backends. Текущие built-in
providers: **honcho, mem0, supermemory, byterover, hindsight,
holographic, openviking, retaindb**.

Каждый provider реализует `MemoryProvider` ABC (см. `agent/memory_provider.py`)
и оркеструется `agent/memory_manager.py`. Lifecycle hooks:
`sync_turn(turn_messages)`, `prefetch(query)`, `shutdown()`, и опционально
`post_setup(prostor_home, config)` для setup-wizard integration.

**CLI commands через `plugins/memory/<name>/cli.py`:** если memory plugin
определяет `register_cli(subparser)`, `discover_plugin_cli_commands()`
находит его при argparse setup и подключает в `prostor <plugin>`. Фреймворк
экспонирует CLI команды только для **активного** memory provider (читается из
`memory.provider` в config.yaml), поэтому отключённые providers не
загромождают `prostor --help`.

**Правило (Teknium, май 2026):** плагины НЕ ДОЛЖНЫ модифицировать core-файлы
(`run_agent.py`, `cli.py`, `gateway/run.py`, `prostor_cli/main.py`, и т.д.).
Если плагину нужна возможность, которую фреймворк не экспонирует — расширяйте
generic plugin surface (новый hook, новый ctx method) — никогда не хардкодите
plugin-specific logic в core. PR #5295 удалил 95 строк хардкод honcho argparse
из `main.py` именно по этой причине.

**Новых in-tree memory providers не принимаем (политика, май 2026):** набор
built-in memory providers под `plugins/memory/` закрыт. Новые memory backends
должны отгружаться как **standalone plugin repos**, которые users устанавливают
в `~/.prostor/plugins/` (или через pip entry points) — они реализуют тот же
`MemoryProvider` ABC, регистрируются через тот же discovery path и
интегрируются через `prostor memory setup` / `post_setup()` без попадания в
это tree. PR, добавляющие директорию под `plugins/memory/`, будут закрыты с
указанием опубликовать provider как собственный repo. Существующие in-tree
providers остаются; bug fix'ы к ним приветствуются.

### Model-provider plugins (`plugins/model-providers/<name>/`)

Каждый inference backend (openrouter, anthropic, gmi, deepseek, nvidia, …)
отгружается как плагин здесь. `__init__.py` каждого плагина вызывает
`providers.register_provider(ProviderProfile(...))` при module load.
`providers/__init__.py._discover_providers()` — **lazy, отдельная система
discovery** — сканируется при первом `get_provider_profile()` или
`list_providers()` вызове, НЕ general PluginManager.

Scan order:
1. Bundled: `<repo>/plugins/model-providers/<name>/`
2. User: `$PROSTOR_HOME/plugins/model-providers/<name>/`
3. Legacy: `<repo>/providers/<name>.py` (back-compat)

User plugins с тем же именем override bundled — `register_provider()`
last-writer-wins. Это позволяет third parties заменять любой built-in profile
без repo patch.

General PluginManager записывает `kind: model-provider` manifest, но НЕ
импортирует их (double-instantiate `ProviderProfile`). Плагины без явного
`kind:` авто-coerce'ятся через source-text heuristic (`register_provider` +
`ProviderProfile` в `__init__.py`).

Полный authoring guide: `website/docs/developer-guide/model-provider-plugin.md`.

### Dashboard / context-engine / image-gen plugin directories

`plugins/context_engine/`, `plugins/image_gen/` и т.д. следуют тому же
паттерну (ABC + orchestrator + per-plugin directory). Context engines
подключаются в `agent/context_engine.py`; image-gen providers — в
`agent/image_gen_provider.py`. Reference / docs-companion plugins
(`example-dashboard`, `strike-freedom-cockpit`, `plugin-llm-example`,
`plugin-llm-async-example`) живут в companion-repo
[`prostor-example-plugins`](https://github.com/NousResearch/prostor-example-plugins),
не в этом tree.

---

## Навыки

Две параллельные поверхности:

- **`skills/`** — built-in skills, отгружаемые и загружаемые по умолчанию.
  Организованы по category-директориям (напр. `skills/github/`, `skills/mlops/`).
- **`optional-skills/`** — тяжёлые или нишевые skills, отгружаемые с репо, но
  НЕ активные по умолчанию. Устанавливаются явно через
  `prostor skills install official/<category>/<skill>`. Адаптер в
  `tools/skills_hub.py` (`OptionalSkillSource`). Категории:
  `autonomous-ai-agents`, `blockchain`, `communication`, `creative`,
  `devops`, `email`, `health`, `mcp`, `migration`, `mlops`, `productivity`,
  `research`, `security`, `web-development`.

При review skill PR проверяйте, в какую директорию они нацелены — heavy-dep
или нишевые skills принадлежат `optional-skills/`.

### SKILL.md frontmatter

Standard fields: `name`, `description`, `version`, `author`, `license`,
`platforms` (OS-gating list: `[macos]`, `[linux, macos]`, ...),
`metadata.prostor.tags`, `metadata.prostor.category`,
`metadata.prostor.related_skills`, `metadata.prostor.config` (config.yaml
настройки, которые skill требует — хранятся под `skills.config.<key>`,
запрашиваются при setup, инжектируются при load).

Top-level `tags:` и `category:` также принимаются и зеркалируются из
`metadata.prostor.*` loader'ом.

### Стандарты authoring skills (HARDLINE)

Каждый новый или модернизируемый skill — bundled, optional или contributed —
должен соответствовать этим стандартам до merge. Reviewers отклоняют PR,
нарушающие их.

1. **`description` ≤ 60 символов, одно предложение, заканчивается точкой.**
   Длинные descriptions раздувают skill listings и разбавляют внимание модели,
   когда загружено много skills. State capability, не implementation. Без
   marketing words («мощный», «комплексный», «бесшовный», «продвинутый»).
   Не повторяйте name skill. Проверьте:
   ```python
   import re, pathlib
   m = re.search(r'^description: (.*)$',
                 pathlib.Path('skills/<cat>/<name>/SKILL.md').read_text(),
                 re.MULTILINE)
   assert len(m.group(1)) <= 60, len(m.group(1))
   ```

2. **Tools, упомянутые в SKILL.md prose, должны быть native Prostor tools или
   MCP servers, которые skill явно ожидает.** Когда skill нуждается в
   возможности, указывайте proper tool по имени в backticks
   (`` `terminal` ``, `` `web_extract` ``, `` `read_file` ``,
   `` `patch` ``, `` `search_files` ``, `` `vision_analyze` ``,
   `` `browser_navigate` ``, `` `delegate_task` ``, и т.д.). НЕ называйте
   shell utilities, которые agent уже обёрнул — `grep` →
   `search_files`, `cat`/`head`/`tail` → `read_file`, `sed`/`awk` →
   `patch`, `find`/`ls` → `search_files target='files'`. Если skill
   зависит от MCP server, назовите MCP server и задокументируйте ожидаемый
   setup в `## Prerequisites`. Всё остальное (third-party CLIs, shell
   pipelines и т.д.) — fair game внутри script files, но не должно быть
   headline interaction surface в prose.

3. **`platforms:` gating проверен против реальных script imports.** Skills,
   использующие POSIX-only primitives (`fcntl`, `termios`,
   `os.setsid`, `os.kill(pid, 0)` для liveness, `/proc`, хардкод `/tmp`,
   `signal.SIGKILL`, bash heredocs, `osascript`, `apt`,
   `systemctl`), должны декларировать поддерживаемые platforms. Дефолт:
   сначала попытаться cross-platform fix — `tempfile.gettmpdir`,
   `pathlib.Path`, `psutil.pid_exists`, Python-level filtering вместо
   `grep`. Gate на narrower set только когда зависимость genuinely
   platform-bound.

4. **`author` кредитует human contributor первым.** Для внешних
   контрибуций — real name + GitHub handle контрибьютора первым; "Prostor Agent" —
   secondary collaborator. Если commit контрибьютора показывает "Prostor Agent"
   как author (потому что они использовали Prostor для drafting skill),
   замените на их actual name — кредитуйте human, не tool.

5. **SKILL.md body использует modern section order.** `# <Skill> Skill`
   title, 2-3 предложения intro, `## When to Use`, `## Prerequisites`,
   `## How to Run`, `## Quick Reference`, `## Procedure`, `## Pitfalls`,
   `## Verification`. Target ~200 строк для complex skill,
   ~100 строк для simple one. Cut redundant intro fluff, marketing prose,
   и re-explanations env vars уже в `## Prerequisites`.

6. **Scripts в `scripts/`, references в `references/`,
   templates в `templates/`.** Не ожидайте, что модель inline-write
   parsers, XML walkers или non-trivial logic каждый call — ship helper
   script. Reference по path relative to skill directory.

7. **Tests живут в `tests/skills/test_<skill>_skill.py`** и используют только
   stdlib + pytest + `unittest.mock`. No live network calls. Run via
   `scripts/run_tests.sh tests/skills/test_<skill>_skill.py -q`.

8. **`.env.example` additions изолированы в чётко delimited block.** Не трогайте
   surrounding file — contributor-supplied `.env.example` versions обычно stale,
   и edits вне skill's own block будут dropped при salvage.

Полный salvage / modernization checklist для external skill PR живёт в
навыке `prostor-agent-dev` в
`references/new-skill-pr-salvage.md` — загрузите его перед polishing
contributor skill PR.

---

## Toolsets

Все toolsets определены в `toolsets.py` как единый `TOOLSETS` dict.
Адаптер каждой платформы выбирает base toolset (напр. Telegram использует
`"messaging"`); `_PROSTOR_CORE_TOOLS` — default bundle, от которого наследует
большинство платформ.

Текущие toolset keys: `browser`, `clarify`, `code_execution`, `cronjob`,
`debugging`, `delegation`, `discord`, `discord_admin`, `feishu_doc`,
`feishu_drive`, `file`, `homeassistant`, `image_gen`, `kanban`, `memory`,
`messaging`, `moa`, `rl`, `safe`, `search`, `session_search`, `skills`,
`spotify`, `terminal`, `todo`, `tts`, `video`, `vision`, `web`, `yuanbao`.

Enable/disable per platform через `prostor tools` (curses UI) или
`tools.<platform>.enabled` / `tools.<platform>.disabled` lists в `config.yaml`.

---

## Делегирование (`delegate_task`)

`tools/delegate_tool.py` спавнит субагента с изолированным
context + terminal session. Синхронно: parent ждёт summary child, прежде чем
продолжить свой loop — если parent прерван, child отменяется.

Две формы:

- **Single:** передайте `goal` (+ опционально `context`, `toolsets`).
- **Batch (parallel):** передайте `tasks: [...]` — каждый получает свой subagent
  конкурентно. Concurrency cap через `delegation.max_concurrent_children` (default 3).

Роли:

- `role="leaf"` (default) — фокусный worker. Не может `delegate_task`,
  `clarify`, `memory`, `send_message`, `execute_code`.
- `role="orchestrator"` — сохраняет `delegate_task` для спавна своих workers.
  Gated через `delegation.orchestrator_enabled` (default true) и bounded через
  `delegation.max_spawn_depth` (default 2).

Ключевые config knobs (под `delegation:` в `config.yaml`):
`max_concurrent_children`, `max_spawn_depth`, `child_timeout_seconds`,
`orchestrator_enabled`, `subagent_auto_approve`, `inherit_mcp_toolsets`,
`max_iterations`.

Synchronicity rule: delegate_task **не** durable. Для long-running work,
которое должно пережить текущий turn, используйте `cronjob` или
`terminal(background=True, notify_on_complete=True)`.

---

## Curator (жизненный цикл skills)

Background skill-maintenance система, tracking usage на agent-created skills
и auto-archive stale ones. Users никогда не теряют skills; archives идут в
`~/.prostor/skills/.archive/` и restorable.

- **Core:** `agent/curator.py` (review loop, auto-transitions, LLM review
  prompt) + `agent/curator_backup.py` (pre-run tar.gz snapshots).
- **CLI:** `prostor_cli/curator.py` подключает `prostor curator <verb>`, где
  verbs: `status`, `run`, `pause`, `resume`, `pin`, `unpin`,
  `archive`, `restore`, `prune`, `backup`, `rollback`.
- **Telemetry:** `tools/skill_usage.py` владеет sidecar
  `~/.prostor/skills/.usage.json` — per-skill `use_count`, `view_count`,
  `patch_count`, `last_activity_at`, `state` (active / stale /
  archived), `pinned`.

Инварианты:
- Curator трогает только skills с `created_by: "agent"` provenance —
  bundled + hub-installed skills вне зоны доступа.
- Никогда не удаляет; max destructive action — archive.
- Pinned skills exempt от каждого auto-transition и от LLM review pass.
- `skill_manage(action="delete")` отказывает для pinned skills; patch/edit/
  write_file/remove_file проходят, чтобы агент мог продолжать улучшать
  pinned skills.

Config section (`curator:` в `config.yaml`):
`enabled`, `interval_hours`, `min_idle_hours`, `stale_after_days`,
`archive_after_days`, `backup.*`.

Полные user-facing docs: `website/docs/user-guide/features/curator.md`.

---

## Cron (запланированные задачи)

`cron/jobs.py` (job store) + `cron/scheduler.py` (tick loop). Агенты
планируют jobs через `cronjob` tool; users через `prostor cron <verb>`
(`list`, `add`, `edit`, `pause`, `resume`, `run`, `remove`) или
`/cron` slash command.

Поддерживаемые форматы schedule:
- Duration: `"30m"`, `"2h"`, `"1d"`
- "every" phrase: `"every 2h"`, `"every monday 9am"`
- 5-field cron expression: `"0 9 * * *"`
- ISO timestamp (one-shot): `"2026-06-01T09:00:00Z"`

Per-job fields включают `skills` (load specific skills), `model` /
`provider` overrides, `script` (pre-run data-collection script, чей stdout
инжектируется в prompt; `no_agent=True` превращает script в entire job),
`context_from` (chain output job A в prompt job B), `workdir` (run в
specific directory с его `AGENTS.md`/`CLAUDE.md` loaded), и multi-platform
delivery.

Hardening invariants:
- **3-минутный hard interrupt** на cron sessions — runaway agent loops
  не могут монополизировать scheduler.
- Catchup window: half the job's period, clamped to 120s–2h.
- Grace window: 120s для one-shot jobs, чьё fire time было пропущено.
- File lock в `~/.prostor/cron/.tick.lock` предотвращает duplicate ticks
  across processes.
- Cron sessions pass `skip_memory=True` по умолчанию; memory providers
  намеренно не запускаются во время cron.

Cron deliveries **не** зеркалируются в target gateway session — они
приземляются в свой собственный cron session с header/footer frame, так что
message-role alternation главного разговора остаётся intact.

---

## Kanban (multi-agent work queue)

Durable SQLite-backed board, позволяющий multiple profiles / workers
collaborate на shared tasks. Users drive через `prostor kanban <verb>`;
workers, spawned dispatcher'ом, drive через dedicated `kanban_*`
toolset, так что их schema footprint — ноль, когда они не внутри kanban task.

- **CLI:** `prostor_cli/kanban.py` подключает `prostor kanban` с verbs
  `init`, `create`, `list` (alias `ls`), `show`, `assign`, `link`,
  `unlink`, `comment`, `complete`, `block`, `unblock`, `archive`,
  `tail`, плюс less-commonly-used `watch`, `stats`, `runs`, `log`,
  `assignees`, `heartbeat`, `notify-*`, `dispatch`, `daemon`, `gc`.
- **Worker/orchestrator toolset:** `tools/kanban_tools.py` exposes
  `kanban_show`, `kanban_complete`, `kanban_block`, `kanban_heartbeat`,
  `kanban_comment`, `kanban_create`, `kanban_link`; profiles, которые
  явно enable `kanban` toolset вне dispatcher-spawned
  task, также получают `kanban_list` и `kanban_unblock` для board routing.
- **Dispatcher:** long-lived loop (default every 60s) reclaims
  stale claims, promotes ready tasks, atomically claims, и spawns
  assigned profiles. Runs **inside gateway** по умолчанию через
  `kanban.dispatch_in_gateway: true`.
- **Plugin assets:** `plugins/kanban/dashboard/` (web UI) +
  `plugins/kanban/systemd/` (`prostor-kanban-dispatcher.service` для
  standalone dispatcher deployment).

Isolation model:
- **Board** — hard boundary; workers spawned с
  `PROSTOR_KANBAN_BOARD` pinned в env, так что не видят другие
  boards.
- **Tenant** — soft namespace *within* a board; один specialist
  fleet может serve multiple businesses с workspace-path + memory-key
  isolation.
- После `kanban.failure_limit` consecutive non-success attempts на
  same task (default: 2), dispatcher auto-blocks it для prevent spin
  loops.

Полные user-facing docs: `website/docs/user-guide/features/kanban.md`.

---

## Важные политики

### Prompt Caching не должен ломаться

Prostor-Agent обеспечивает caching valid в течение разговора. **НЕ реализуйте
изменения, которые:**
- Альтерируют прошлый контекст mid-conversation
- Меняют toolset mid-conversation
- Перезагружают memories или пересобирают system prompt mid-conversation

Cache-breaking форсирует драматически более высокие costs. Единственный раз,
когда мы альтерируем context — context compression.

Slash-команды, мутирующие system-prompt state (skills, tools, memory и т.д.),
должны быть **cache-aware**: default на deferred invalidation (change
действует next session), с opt-in `--now` flag для immediate invalidation.
См. `/skills install --now` для canonical pattern.

### Background Process Notifications (Gateway)

Когда `terminal(background=true, notify_on_complete=true)` используется, gateway
запускает watcher, детектирующий completion process и trigger'ящий новый agent
turn. Контролируйте verbosity background process messages через
`display.background_process_notifications`
в config.yaml (или `PROSTOR_BACKGROUND_NOTIFICATIONS` env var):

- `all` — running-output updates + final message (default)
- `result` — только final completion message
- `error` — только final message когда exit code != 0
- `off` — никаких watcher messages

---

## Профили: Multi-Instance Support

Prostor поддерживает **profiles** — multiple fully isolated instances, каждый
со своим `PROSTOR_HOME` directory (config, API keys, memory, sessions, skills,
gateway и т.д.).

Core mechanism: `_apply_profile_override()` в `prostor_cli/main.py` устанавливает
`PROSTOR_HOME` до любого module import. Все `get_prostor_home()` references
автоматически scope к active profile.

### Правила для profile-safe code

1. **Используйте `get_prostor_home()` для всех PROSTOR_HOME путей.** Импорт из
   `prostor_constants`. НИКОГДА не хардкодьте `~/.prostor` или `Path.home() / ".prostor"`
   в коде, который читает/пишет state.
   ```python
   # GOOD
   from prostor_constants import get_prostor_home
   config_path = get_prostor_home() / "config.yaml"

   # BAD — ломает profiles
   config_path = Path.home() / ".prostor" / "config.yaml"
   ```

2. **Используйте `display_prostor_home()` для user-facing messages.** Импорт из
   `prostor_constants`. Возвращает `~/.prostor` для default или
   `~/.prostor/profiles/<name>` для profiles.
   ```python
   # GOOD
   from prostor_constants import display_prostor_home
   print(f"Config saved to {display_prostor_home()}/config.yaml")

   # BAD — показывает wrong path для profiles
   print("Config saved to ~/.prostor/config.yaml")
   ```

3. **Module-level constants — OK** — они кэшируют `get_prostor_home()` при
   import time, который AFTER `_apply_profile_override()` устанавливает env var.
   Просто используйте `get_prostor_home()`, не `Path.home() / ".prostor"`.

4. **Тесты, мокающие `Path.home()`, должны также set `PROSTOR_HOME`** — т.к. код
   теперь использует `get_prostor_home()` (читает env var), не `Path.home() / ".prostor"`:
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"PROSTOR_HOME": str(tmp_path / ".prostor")}):
       ...
   ```

5. **Gateway platform adapters должны использовать token locks** — если adapter
   подключается с unique credential (bot token, API key), вызывайте
   `acquire_scoped_lock()` из `gateway.status` в `connect()`/`start()` method и
   `release_scoped_lock()` в `disconnect()`/`stop()`. Это предотвращает два profiles
   от использования того же credential. См. `gateway/platforms/telegram.py` для
   canonical pattern.

6. **Profile operations — HOME-anchored, не PROSTOR_HOME-anchored** —
   `_get_profiles_root()` возвращает `Path.home() / ".prostor" / "profiles"`,
   НЕ `get_prostor_home() / "profiles"`. Это намеренно — позволяет
   `prostor -p coder profile list` видеть все profiles независимо от того,
   какой active.

## Известные pitfalls

### НЕ хардкодьте пути `~/.prostor`
Используйте `get_prostor_home()` из `prostor_constants` для code paths.
Используйте `display_prostor_home()` для user-facing print/log messages.
Хардкод `~/.prostor` ломает profiles — каждый profile имеет свой `PROSTOR_HOME`
directory. Это было источником 5 багов, пофикшенных в PR #3575.

### НЕ вводите новые `simple_term_menu` usage
Существующие call sites в `prostor_cli/main.py` остаются для legacy fallback;
предпочтительный UI — curses (stdlib), т.к. `simple_term_menu` имеет
ghost-duplication rendering bugs в tmux/iTerm2 с arrow keys. Новые
interactive menus должны использовать `prostor_cli/curses_ui.py` — см.
`prostor_cli/tools_config.py` для canonical pattern.

### НЕ используйте `\033[K` (ANSI erase-to-EOL) в spinner/display code
Утечка как literal `?[K` text под `prompt_toolkit`'s `patch_stdout`.
Используйте space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` — process-global в `model_tools.py`
`_run_single_child()` в `delegate_tool.py` save и restore этот global вокруг
subagent execution. Если добавляете код, читающий этот global, имейте в виду,
что он может быть temporarily stale во время child agent runs.

### НЕ хардкодьте cross-tool references в schema descriptions
Tool schema descriptions не должны упоминать tools из других toolsets по имени
(напр. `browser_navigate` говорит "prefer web_search"). Эти tools могут быть
unavailable (missing API keys, disabled toolset), вызывая hallucination calls к
non-existent tools. Если cross-reference нужен, добавьте динамически в
`get_tool_definitions()` в `model_tools.py` — см. `browser_navigate` /
`execute_code` post-processing blocks для pattern.

### Gateway имеет ДВА message guards — оба должны bypass approval/control commands
Когда agent running, messages проходят через два sequential guards:
(1) **base adapter** (`gateway/platforms/base.py`) queues messages в
`_pending_messages` когда `session_key in self._active_sessions`, и
(2) **gateway runner** (`gateway/run.py`) intercepts `/stop`, `/new`,
`/queue`, `/status`, `/approve`, `/deny` до того, как они достигнут
`running_agent.interrupt()`. Любая новая команда, которая должна достигнуть
runner, пока agent blocked (напр. approval prompts), MUST bypass BOTH guards
и dispatch inline, не через `_process_message_background()`
(которое race'ит session lifecycle).

### Squash merges из stale branches silently revert recent fixes
Перед squash-merge PR, убедитесь, что branch up to date с `main`
(`git fetch origin main && git reset --hard origin/main` в worktree,
затем re-apply PR's commits). Stale branch's version unrelated файла silently
overwrite recent fixes на main при squash. Verify через
`git diff HEAD~1..HEAD` после merge — unexpected deletions — red flag.

### Не подключайте dead code без E2E validation
Unused code, которое никогда не отгружалось, было dead по причине. Перед
wiring unused module в live code path, E2E test реальный resolution chain
с actual imports (не mocks) против temp `PROSTOR_HOME`.

### Тесты не должны писать в `~/.prostor/`
Autouse fixture `_isolate_prostor_home` в `tests/conftest.py` redirects
`PROSTOR_HOME` в temp dir. Никогда не хардкодьте `~/.prostor/` paths в тестах.

**Profile tests:** при тестировании profile features, также mock `Path.home()`,
чтобы `_get_profiles_root()` и `_get_default_prostor_home()` resolved внутри
temp dir. Используйте pattern из `tests/prostor_cli/test_profiles.py`:
```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".prostor"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("PROSTOR_HOME", str(home))
    return home
```

---

## Тестирование

**ВСЕГДА используйте `scripts/run_tests.sh`** — не вызывайте `pytest` напрямую.
Script обеспечивает hermetic environment parity с CI (unset credential vars,
TZ=UTC, LANG=C.UTF-8, `-n auto` xdist workers, in-tree subprocess-isolation
plugin). Direct `pytest` на 16+ core developer machine с API keys set diverges
от CI так, что вызвало multiple «works locally, fails in CI» incidents (и
reverse).

```bash
scripts/run_tests.sh                                  # полный suite, CI-parity
scripts/run_tests.sh tests/gateway/                   # одна директория
scripts/run_tests.sh tests/agent/test_foo.py::test_x  # один тест
scripts/run_tests.sh -v --tb=long                     # pass-through pytest flags
scripts/run_tests.sh --no-isolate tests/foo/          # disable isolation (быстрее, для debugging)
```

### Subprocess-per-test isolation

Каждый тест запускается в freshly-spawned Python subprocess через in-tree plugin
в `tests/_isolate_plugin.py`. Это значит, что module-level dicts/sets и
ContextVars из одного теста не могут утечь в следующий — исторический
`_reset_module_state` autouse fixture упразднён.

Implementation notes:

- Plugin использует `multiprocessing.get_context("spawn")`, который работает
  на Linux, macOS и Windows (POSIX `fork` не используется).
- Per-test overhead ~0.5–1.0s (Python startup + pytest collection). xdist
  parallelism amortizes это across cores; на 20-core box полный suite
  finishes примерно за то же wall time, но flake-free.
- `isolate_timeout` (configured в `pyproject.toml`) caps каждый test на 30s.
  Hangs killed и surfaced как failure report.
- Pass `--no-isolate` для disable isolation — полезно при debugging single test
  interactively, или когда хотите verify state leakage.
- Plugin disables себя в child processes (sentinel envvar
  `PROSTOR_ISOLATE_CHILD=1`), поэтому fork-bomb risk нет.

### Почему wrapper (и почему старое «просто вызови pytest» не работает)

Пять реальных источников local-vs-CI drift, которые script закрывает:

| | Без wrapper | С wrapper |
|---|---|---|
| Provider API keys | Что в env (auto-detects pool) | Все `*_API_KEY`/`*_TOKEN`/etc. unset |
| HOME / `~/.prostor/` | Ваш real config+auth.json | Temp dir per test |
| Timezone | Local TZ (PDT и т.д.) | UTC |
| Locale | Что set | C.UTF-8 |
| xdist workers | `-n auto` = all cores | `-n auto` (safe — subprocess isolation prevents cross-worker flakes) |

`tests/conftest.py` также enforcement points 1-4 как autouse fixture, поэтому
ANY pytest invocation (включая IDE integrations) получает hermetic behavior —
но wrapper — belt-and-suspenders.

### Запуск без wrapper (только если нужно)

Если не можете использовать wrapper (напр. внутри IDE, которая shells pytest
напрямую), minimum — activate venv. Isolation plugin loads автоматически из
`addopts` в `pyproject.toml`, поэтому per-test process isolation тот же.

```bash
source .venv/bin/activate   # или: source venv/bin/activate
python -m pytest tests/ -q
```

Если нужно bypass isolation для fast feedback при debugging:

```bash
python -m pytest tests/agent/test_foo.py -q --no-isolate
```

Всегда запускайте полный suite перед push изменений.

### Не пишите change-detector тесты

Тест — **change-detector**, если он fail'ит когда данные, которые **ожидается
изменить**, обновляются — model catalogs, config version numbers, enumeration
counts, hardcoded lists of provider models. Эти тесты не добавляют
behavioral coverage; они только гарантируют, что routine source updates break
CI и cost engineering time на «fix».

**Не пишите:**

```python
# catalog snapshot — ломается каждый model release
assert "gemini-2.5-pro" in _PROVIDER_MODELS["gemini"]
assert "MiniMax-M2.7" in models

# config version literal — ломается каждый schema bump
assert DEFAULT_CONFIG["_config_version"] == 21

# enumeration count — ломается каждый раз, когда skill/provider добавлен
assert len(_PROVIDER_MODELS["huggingface"]) == 8
```

**Пишите:**

```python
# behavior: работает ли catalog plumbing вообще?
assert "gemini" in _PROVIDER_MODELS
assert len(_PROVIDER_MODELS["gemini"]) >= 1

# behavior: мигрирует ли bump user's version к current latest?
assert raw["_config_version"] == DEFAULT_CONFIG["_config_version"]

# invariant: ни один plan-only model не утекает в legacy list
assert not (set(moonshot_models) & coding_plan_only_models)

# invariant: каждый model в catalog имеет context-length entry
for m in _PROVIDER_MODELS["huggingface"]:
    assert m.lower() in DEFAULT_CONTEXT_LENGTHS_LOWER
```

Правило: если тест читается как snapshot current data — удалите его. Если
читается как contract о том, как две части данных должны соотноситься —
сохраните. Когда PR добавляет new provider/model и нужен тест, делайте test
assert relationship (напр. "catalog entries all have context lengths"), а не
specific names.

Reviewers должны отклонять новые change-detector tests; authors должны
convert'ить их в invariants перед re-request review.