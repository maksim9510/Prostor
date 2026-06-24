<p align="center">
  <img src="assets/banner.png" alt="Prostor Agent" width="100%">
</p>

# Prostor Agent ☤
<p align="center">
  <a href="https://github.com/maksim9510/Prostor/">Prostor Agent</a> | <a href="https://github.com/maksim9510/Prostor/">Prostor Desktop</a>
</p>
<p align="center">
  <a href="https://github.com/maksim9510/Prostor/docs/"><img src="https://img.shields.io/badge/Документация-prostor--agent.nousresearch.com-FFD700?style=for-the-badge" alt="Документация"></a>
  <a href="https://discord.gg/NousResearch"><img src="https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://github.com/maksim9510/Prostor/blob/main/LICENSE"><img src="https://img.shields.io/badge/Лицензия-MIT-green?style=for-the-badge" alt="Лицензия: MIT"></a>
  <a href="https://nousresearch.com"><img src="https://img.shields.io/badge/Создано%20в-Nous%20Research-blueviolet?style=for-the-badge" alt="Built by Nous Research"></a>
</p>


<p align="center">
  <a href="https://github.com/maksim9510/Prostor/releases/latest"><img src="https://img.shields.io/github/v/release/maksim9510/Prostor?style=flat-square&logo=github&logoColor=white&color=blue" alt="Latest Release"/></a>
  <a href="https://github.com/maksim9510/Prostor/blob/main/LICENSE"><img src="https://img.shields.io/github/license/maksim9510/Prostor?style=flat-square&color=green" alt="License"/></a>
  <a href="https://github.com/maksim9510/Prostor/stargazers"><img src="https://img.shields.io/github/stars/maksim9510/Prostor?style=flat-square&logo=github" alt="Stars"/></a>
  <a href="https://github.com/maksim9510/Prostor/network/members"><img src="https://img.shields.io/github/forks/maksim9510/Prostor?style=flat-square&logo=github" alt="Forks"/></a>
  <a href="https://github.com/maksim9510/Prostor/issues"><img src="https://img.shields.io/github/issues/maksim9510/Prostor?style=flat-square&logo=github" alt="Open Issues"/></a>
  <a href="https://github.com/maksim9510/Prostor/pulls"><img src="https://img.shields.io/github/issues-pr/maksim9510/Prostor?style=flat-square&logo=github" alt="Open PRs"/></a>
  <br>
  <a href="https://github.com/maksim9510/Prostor/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow-status/maksim9510/Prostor/tests.yml?branch=main&style=flat-square&logo=github-actions&logoColor=white&label=tests" alt="Tests"/></a>
  <a href="https://github.com/maksim9510/Prostor/actions/workflows/lint.yml"><img src="https://img.shields.io/github/actions/workflow-status/maksim9510/Prostor/lint.yml?branch=main&style=flat-square&logo=github-actions&logoColor=white&label=lint" alt="Lint"/></a>
  <a href="https://github.com/maksim9510/Prostor/actions/workflows/typecheck.yml"><img src="https://img.shields.io/github/actions/workflow-status/maksim9510/Prostor/typecheck.yml?branch=main&style=flat-square&logo=github-actions&logoColor=white&label=typecheck" alt="Typecheck"/></a>
  <a href="https://github.com/maksim9510/Prostor/commits/main"><img src="https://img.shields.io/github/last-commit/maksim9510/Prostor?style=flat-square&logo=github" alt="Last Commit"/></a>
  <a href="https://github.com/maksim9510/Prostor/graphs/contributors"><img src="https://img.shields.io/github/contributors/maksim9510/Prostor?style=flat-square&logo=github" alt="Contributors"/></a>
  <a href="https://github.com/maksim9510/Prostor"><img src="https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+"/></a>
  <a href="https://github.com/maksim9510/Prostor"><img src="https://img.shields.io/badge/node-20%2B-339933?style=flat-square&logo=node.js&logoColor=white" alt="Node 20+"/></a>
  <a href="https://codecov.io/gh/maksim9510/Prostor"><img src="https://img.shields.io/codecov/c/github/maksim9510/Prostor?style=flat-square&logo=codecov&logoColor=white" alt="Coverage"/></a>
</p>

**Самообучающийся AI-агент на русском языке, созданный на базе [Nous Research](https://nousresearch.com).** Prostor — единственный агент со встроенным циклом обучения: он создаёт навыки из опыта, улучшает их во время использования, напоминает себе сохранять знания, ищет в истории прошлых разговоров и формирует всё более глубокую модель пользователя от сессии к сессии. Запускайте его на VPS за $5, на GPU-кластере или в serverless-инфраструктуре, которая в простое стоит практически ничего. Он не привязан к вашему ноутбуку — общайтесь с ним из Telegram, пока он работает на облачной VM.

Используйте любую модель — [Nous Portal](https://portal.nousresearch.com), [OpenRouter](https://openrouter.ai) (200+ моделей), [NovitaAI](https://novita.ai), [NVIDIA NIM](https://build.nvidia.com), [Xiaomi MiMo](https://platform.xiaomimimo.com), [z.ai/GLM](https://z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [MiniMax](https://www.minimax.io), [Hugging Face](https://huggingface.co), OpenAI или свой собственный endpoint. Переключайтесь командой `prostor model` — без изменения кода и без привязки к провайдеру.

<table>
<tr><td><b>Настоящий терминальный интерфейс</b></td><td>Полноценный TUI с многострочным редактированием, автодополнением slash-команд, историей разговоров, прерыванием и перенаправлением, потоковым выводом инструментов.</td></tr>
<tr><td><b>Живёт там же, где вы</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal и CLI — всё через единый процесс gateway. Транскрипция голосовых сообщений, непрерывность разговоров между платформами.</td></tr>
<tr><td><b>Замкнутый цикл обучения</b></td><td>Курируемая агентом память с периодическими напоминаниями. Автономное создание навыков после сложных задач. Навыки самоулучшаются во время использования. FTS5-поиск по сессиям с LLM-саммаризацией для межсессионного восстановления контекста. <a href="https://github.com/plastic-labs/honcho">Honcho</a> диалектическое моделирование пользователя. Совместим с открытым стандартом <a href="https://agentskills.io">agentskills.io</a>.</td></tr>
<tr><td><b>Запланированные автоматизации</b></td><td>Встроенный cron-планировщик с доставкой на любую платформу. Ежедневные отчёты, ночные резервные копии, еженедельные аудиты — всё на естественном языке, работает без присмотра.</td></tr>
<tr><td><b>Делегирует и распараллеливает</b></td><td>Создавайте изолированные субагенты для параллельных потоков работы. Пишите Python-скрипты, вызывающие инструменты через RPC, сворачивая многошаговые пайплайны в ходы с нулевой стоимостью контекста.</td></tr>
<tr><td><b>Запускается где угодно, не только на ноутбуке</b></td><td>Шесть терминальных бэкендов — local, Docker, SSH, Singularity, Modal и Daytona. Daytona и Modal предлагают serverless-персистентность: окружение агента засыпает в простое и просыпается по запросу, costing практически ничего между сессиями.</td></tr>
<tr><td><b>HashLine — ключевое преимущество</b></td><td>Интегрирован <b>HashLine</b> — система сопоставления строк на основе хешей, заменяющая медленный fuzzy_match. Сопоставление выполняется за <b>0.11 мс</b> вместо <b>526 мс</b> у классического fuzzy-подхода — ускорение в ~4700 раз. HashLine используется для точного и быстрого поиска в файлах, патч-операций и навигации по коду.</td></tr>
<tr><td><b>Готов к исследованиям</b></td><td>Пакетная генерация траекторий, сжатие траекторий для обучения следующего поколения моделей с tool-calling.</td></tr>
</table>

---

## ⚡ Оптимизации, которых нет в других агентах

Prostor — единственный open-source агент с **полным набором оптимизаций**, который раньше встречался только в проприетарных системах. Каждая метрика измерена на реальных задачах, не маркетинговых бенчмарках.

### 🛠 10 встроенных оптимизаций

| # | Оптимизация | Метрика | Файл |
|---|---|---|---|
| 1 | **HashLine** — O(1) hash matching | **до 4700x** быстрее fuzzy | [`tools/hashline.py`](tools/hashline.py) |
| 2 | **batch_patch tool** | 1 round-trip к LLM вместо N | [`tools/batch_patch_tool.py`](tools/batch_patch_tool.py) |
| 3 | **batch_read tool** | 1 round-trip к LLM вместо N | [`tools/batch_read_tool.py`](tools/batch_read_tool.py) |
| 4 | **Persistent Index Cache** | **до 7x** на повторных patch | [`tools/hashline_persistent_cache.py`](tools/hashline_persistent_cache.py) |
| 5 | **Tool result compression** | **99.6%** токенов | [`tools/result_compression.py`](tools/result_compression.py) |
| 6 | **SSH Paramiko connector skill** | безопасный remote exec | [`skills/devops/ssh-paramiko-connector/`](skills/devops/ssh-paramiko-connector/) |
| 7 | **Token Budget Manager** | auto-warn 75/90/95% бюджета | [`tools/token_budget.py`](tools/token_budget.py) |
| 8 | **Context Window Optimizer** | priority-aware warm compression | [`tools/context_optimizer.py`](tools/context_optimizer.py) |
| 9 | **Tier System** | 22 vs 50 tools, −11.2K tokens/call | [`toolsets.py`](toolsets.py) |
| 10 | **Adaptive Tool Router** | auto-suggest batch вместо N calls | [`tools/adaptive_router.py`](tools/adaptive_router.py) |

### 🏎 Реальные результаты бенчмарка HashLine

Замер на файле 50 000 строк (1.8 MB), `tools/hashline.py` vs классический `fuzzy_match`:

| Сценарий | HashLine | fuzzy_match | **Ускорение** |
|---|---|---|---|
| Точная замена | 2.05 ms | 2.47 ms | 1.2x |
| Грязная замена (другие пробелы) | **0.58 ms** | **6548.9 ms** | 🔥 **11,280x** |
| 50 замен подряд | 103 ms | 3750 ms | 36x |

> 📊 Бенчмарк воспроизводим: `python scripts/bench_hashline.py` (см. [`skills/devops/prostor-perf-benchmark`](skills/devops/prostor-perf-benchmark/)).

### 🔥 HashLine — ключевое преимущество

> **Сопоставление строк за 0.11 ms вместо 526 ms — ускорение в ~4700 раз.**
>
> HashLine — это многоуровневый хеш-индекс (`line hash` + `block hash` + `token hash` + `bloom filter`), который заменяет медленный `fuzzy_match` с 9 стратегиями последовательного перебора. Используется для точного и быстрого поиска в файлах, патч-операций и навигации по коду. Drop-in fast path: если HashLine нашёл — ответ мгновенный; если нет — fallback на fuzzy.

---

## 🔒 Безопасность

Prostor включает **10 security fix'ов** из upstream v2026.6.19:

- **MCP-persistence attack surface** — защита от атак через MCP серверы
- **Shell injection** — квотирование переменных окружения в remote execution
- **Approval guard hardening** — защита от prompt injection в approval
- **Credential stores** — запрет root-level credential storage в media delivery
- **Dashboard plugin import** — auto-import Python backend только для bundled plugins
- **IPv6 scope ID bypass** — fail-closed для unparseable IP addresses
- **WebSocket peer** — fail-closed для empty peer в loopback mode
- **Kanban markdown HTML** — санитайзинг HTML в kanban контенте
- **Path traversal** — защита от path traversal в restore_quick_snapshot
- **Credential redact** — сокрытие credentials в TUI approval prompts

---

## 🚀 Быстрые победы (v0.17.0)

- **Result sizes 100K→50K** — large results persisted to disk, −11K tokens/result
- **pytest-xdist** — параллельное выполнение тестов (2-4x speedup)
- **delegate_task schema −48%** — 7.8K→4.0K chars (−954 tokens/call)
- **Tier System** — 22 core tools (~8K tokens) vs 50 full (~20K tokens)

---

## ✨ Что умеет Prostor

<table>
<tr><td><b>🔌 <code>prostor model</code></b></td><td>Без изменения кода и без привязки к провайдеру. Переключение между <a href="https://portal.nousresearch.com">Nous Portal</a>, <a href="https://openrouter.ai">OpenRouter</a> (200+ моделей), <a href="https://novita.ai">NovitaAI</a>, <a href="https://build.nvidia.com">NVIDIA NIM</a>, <a href="https://platform.xiaomimimo.com">Xiaomi MiMo</a>, <a href="https://z.ai">z.ai/GLM</a>, <a href="https://platform.moonshot.ai">Kimi/Moonshot</a>, <a href="https://www.minimax.io">MiniMax</a>, <a href="https://huggingface.co">Hugging Face</a>, OpenAI или собственный endpoint.</td></tr>
<tr><td><b>🖥 Настоящий терминальный интерфейс</b></td><td>Полноценный TUI с многострочным редактированием, автодополнением slash-команд, историей разговоров, прерыванием и перенаправлением, потоковым выводом инструментов.</td></tr>
<tr><td><b>📱 Живёт там же, где вы</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal и CLI — всё через единый процесс gateway. Транскрипция голосовых сообщений, непрерывность разговоров между платформами.</td></tr>
<tr><td><b>🧠 Замкнутый цикл обучения</b></td><td>Курируемая агентом память с периодическими напоминаниями. Автономное создание навыков после сложных задач. Навыки самоулучшаются во время использования. FTS5-поиск по сессиям с LLM-саммаризацией для межсессионного восстановления контекста. <a href="https://github.com/plastic-labs/honcho">Honcho</a> диалектическое моделирование пользователя. Совместим с открытым стандартом <a href="https://agentskills.io">agentskills.io</a>.</td></tr>
<tr><td><b>⏰ Запланированные автоматизации</b></td><td>Встроенный cron-планировщик с доставкой на любую платформу. Ежедневные отчёты, ночные резервные копии, еженедельные аудиты — всё на естественном языке, работает без присмотра.</td></tr>
<tr><td><b>🪄 Делегирует и распараллеливает</b></td><td>Создавайте изолированные субагенты для параллельных потоков работы. Пишите Python-скрипты, вызывающие инструменты через RPC, сворачивая многошаговые пайплайны в ходы с нулевой стоимостью контекста.</td></tr>
<tr><td><b>☁️ Запускается где угодно</b></td><td>Шесть терминальных бэкендов — local, Docker, SSH, Singularity, Modal и Daytona. Daytona и Modal предлагают serverless-персистентность: окружение агента засыпает в простое и просыпается по запросу, costing практически ничего между сессиями.</td></tr>
<tr><td><b>🧬 Готов к исследованиям</b></td><td>Пакетная генерация траекторий, сжатие траекторий для обучения следующего поколения моделей с tool-calling. Встроенные инструменты для dataset curation, evaluation и benchmark'инга.</td></tr>
</table>

---

## Быстрая установка

### Linux (Debian, Ubuntu, Astra, RedOS, Fedora, Arch, Manjaro, Alpine, NixOS)

Установщик **автоматически определяет** дистрибутив и ставит все нужные пакеты
через `apt` / `dnf` / `pacman` / `apk` / `nix` соответственно.

```bash
curl -fsSL https://raw.githubusercontent.com/maksim9510/Prostor/main/install.sh | bash
```

**Режимы:**

```bash
./install.sh                         # стандартная установка с sudo (только CLI)
./install.sh --user                  # без sudo, в ~/.local
./install.sh --minimal               # без Docker и ffmpeg extras
./install.sh --no-system             # только Python пакет, без системных deps
./install.sh --no-systemd            # без создания service user
./install.sh --with-desktop          # + Desktop приложение (Electron, нужен X11/Wayland + Node.js 22+)
./install.sh --no-desktop            # явно без desktop (по умолчанию)
PROSTOR_VERSION=v0.18.0 ./install.sh # конкретная версия
./install.sh --verbose               # подробный вывод
./install.sh --dry-run               # показать что будет без выполнения
./install.sh --help                  # все опции
```

Подробнее: [`install.sh`](install.sh) — поддерживает Debian/Ubuntu, **Astra Linux 1.8 (Smolensk)**,
RHEL/CentOS/**RedOS**, Fedora, **Arch/Manjaro**, Alpine, NixOS.

### macOS, WSL2, Termux

```bash
curl -fsSL https://raw.githubusercontent.com/maksim9510/Prostor/main/install.sh | bash
```

> macOS: требуется [Homebrew](https://brew.sh). Prostor работает через `uv` (brew install uv).
> WSL2: работает как обычный Linux. Prostor автоматически определит WSL.
> Termux: используется специальный bundle `.[termux]` — см. [гайд](docs/getting-started/termux).

### Windows (нативно, PowerShell)

> **Внимание:** Native Windows работает без WSL — CLI, gateway, TUI и инструменты работают нативно. Если предпочитаете WSL2, подойдёт one-liner для Linux/macOS выше. Нашли баг? [Создайте issue](https://github.com/maksim9510/Prostor/issues).

Выполните в PowerShell:

```powershell
iex (irm https://github.com/maksim9510/Prostor/install.ps1)
```

Установщик берёт на себя всё: uv, Python 3.11, Node.js, ripgrep, ffmpeg, **и портативный Git Bash** (MinGit, распаковывается в `%LOCALAPPDATA%\prostor\git` — не требует прав администратора, полностью изолирован от системного Git). Prostor использует этот встроенный Git Bash для выполнения shell-команд.

Если Git уже установлен, установщик обнаружит его и использует. Иначе нужен лишь ~45 MB загрузки MinGit — он не затронет системный Git.

> **Android / Termux:** Проверенный ручной путь описан в [руководстве по Termux](https://github.com/maksim9510/Prostor/docs/getting-started/termux). В Termux Prostor устанавливает кураторский набор `.[termux]`, так как полный `.[all]` тянет Android-несовместимые голосовые зависимости.
>
> **Windows:** Native Windows полностью поддерживается — PowerShell-установщик выше ставит всё. Если предпочитаете WSL2, подойдёт Linux-команда. Установка на native Windows размещается в `%LOCALAPPDATA%\prostor`; установка в WSL2 — в `~/.prostor`, как в Linux.

После установки:

```bash
source ~/.bashrc    # перезагрузите shell (или: source ~/.zshrc)
prostor              # начните общение!
```

---

## Начало работы

```bash
prostor              # Интерактивный CLI — начать разговор
prostor model        # Выбрать LLM-провайдера и модель
prostor tools        # Настроить включённые инструменты
prostor config set   # Установить отдельные значения конфигурации
prostor gateway      # Запустить messaging gateway (Telegram, Discord и т.д.)
prostor setup        # Запустить полный мастер настройки (настраивает всё сразу)
prostor claw migrate # Миграция с OpenClaw (если переходите с OpenClaw)
prostor update       # Обновиться до последней версии
prostor doctor       # Диагностика проблем
```

📖 **[Полная документация →](https://github.com/maksim9510/Prostor/docs/)**

---

## Обход сбора API-ключей — Nous Portal

Prostor работает с любым провайдером — это не изменится. Но если не хочется собирать пять отдельных API-ключей для модели, веб-поиска, генерации изображений, TTS и облачного браузера, **[Nous Portal](https://portal.nousresearch.com)** покрывает их все одной подпиской:

- **300+ моделей** — выбирайте любую через `/model <name>`
- **Tool Gateway** — веб-поиск (Firecrawl), генерация изображений (FAL), text-to-speech (OpenAI), облачный браузер (Browser Use) — всё через вашу подписку. Без лишних аккаунтов.

Одна команда с чистой установки:

```bash
prostor setup --portal
```

Это логинит вас через OAuth, устанавливает Nous как провайдера и включает Tool Gateway. Проверить подключение в любой момент: `prostor portal info`. Подробности — на странице документации [Tool Gateway](https://maksim9510.github.io/Prostor/docs/user-guide/features/tool-gateway).

Вы можете использовать свои ключи для отдельных инструментов когда угодно — gateway настраивается по каждому бэкенду, а не «всё или ничего».

---

## Краткая справка: CLI vs Messaging

У Prostor две точки входа: запустите терминальный UI командой `prostor` или запустите gateway и общайтесь через Telegram, Discord, Slack, WhatsApp, Signal или Email. Внутри разговора многие slash-команды общие для обоих интерфейсов.

| Действие                        | CLI                                           | Messaging-платформы                                                              |
| ------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------- |
| Начать общение                  | `prostor`                                      | Запустите `prostor gateway setup` + `prostor gateway start`, затем отправьте боту сообщение |
| Новый разговор                  | `/new` или `/reset`                            | `/new` или `/reset`                                                               |
| Сменить модель                  | `/model [provider:model]`                     | `/model [provider:model]`                                                        |
| Задать личность                 | `/personality [name]`                         | `/personality [name]`                                                            |
| Повторить или отменить последний ход | `/retry`, `/undo`                             | `/retry`, `/undo`                                                                |
| Сжать контекст / проверить использование | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]`                                        |
| Просмотреть навыки              | `/skills` или `/<skill-name>`                  | `/<skill-name>`                                                                  |
| Прервать текущую работу         | `Ctrl+C` или отправить новое сообщение        | `/stop` или отправить новое сообщение                                            |
| Статус по платформам             | `/platforms`                                  | `/status`, `/sethome`                                                            |

Полные списки команд — в [руководстве по CLI](https://maksim9510.github.io/Prostor/docs/user-guide/cli) и [руководстве по Messaging Gateway](https://maksim9510.github.io/Prostor/docs/user-guide/messaging).

---

## Документация

Вся документация находится на **[github.com/maksim9510/Prostor/docs](https://github.com/maksim9510/Prostor/docs/)**:

| Раздел                                                                                             | Что покрыто                                                |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [Быстрый старт](https://github.com/maksim9510/Prostor/docs/getting-started/quickstart)                 | Установка → настройка → первый разговор за 2 минуты        |
| [Использование CLI](https://maksim9510.github.io/Prostor/docs/user-guide/cli)                              | Команды, горячие клавиши, личности, сессии                  |
| [Конфигурация](https://maksim9510.github.io/Prostor/docs/user-guide/configuration)                | Файл конфигурации, провайдеры, модели, все опции           |
| [Messaging Gateway](https://maksim9510.github.io/Prostor/docs/user-guide/messaging)                | Telegram, Discord, Slack, WhatsApp, Signal, Home Assistant |
| [Безопасность](https://maksim9510.github.io/Prostor/docs/user-guide/security)                          | Одобрение команд, DM-pairing, изоляция в контейнере       |
| [Инструменты и наборы инструментов](https://maksim9510.github.io/Prostor/docs/user-guide/features/tools)            | 40+ инструментов, система toolset, терминальные бэкенды    |
| [Система навыков](https://maksim9510.github.io/Prostor/docs/user-guide/features/skills)              | Процедурная память, Skills Hub, создание навыков           |
| [Память](https://maksim9510.github.io/Prostor/docs/user-guide/features/memory)                     | Персистентная память, профили пользователей, best practices |
| [Интеграция MCP](https://maksim9510.github.io/Prostor/docs/user-guide/features/mcp)               | Подключение любого MCP-сервера для расширенных возможностей |
| [Cron-планировщик](https://maksim9510.github.io/Prostor/docs/user-guide/features/cron)              | Запланированные задачи с доставкой на платформы           |
| [Контекстные файлы](https://maksim9510.github.io/Prostor/docs/user-guide/features/context-files)       | Контекст проекта, влияющий на каждый разговор             |
| [Архитектура](https://github.com/maksim9510/Prostor/docs/developer-guide/architecture)             | Структура проекта, цикл агента, ключевые классы           |
| [Контрибуция](https://github.com/maksim9510/Prostor/docs/developer-guide/contributing)             | Настройка разработки, процесс PR, стиль кода              |
| [Справочник CLI](https://github.com/maksim9510/Prostor/docs/reference/cli-commands)                  | Все команды и флаги                                       |
| [Переменные окружения](https://github.com/maksim9510/Prostor/docs/reference/environment-variables) | Полный справочник по env vars                              |

---

## Миграция с OpenClaw

Если вы переходите с OpenClaw, Prostor может автоматически импортировать ваши настройки, память, навыки и API-ключи.

**При первичной настройке:** Мастер настройки (`prostor setup`) автоматически обнаруживает `~/.openclaw` и предлагает миграцию до начала конфигурации.

**В любое время после установки:**

```bash
prostor claw migrate              # Интерактивная миграция (полный пресет)
prostor claw migrate --dry-run    # Предпросмотр того, что будет мигрировано
prostor claw migrate --preset user-data   # Миграция без секретов
prostor claw migrate --overwrite  # Перезаписать существующие конфликты
```

Что импортируется:

- **SOUL.md** — файл персоны
- **Память** — записи MEMORY.md и USER.md
- **Навыки** — созданные пользователем навыки → `~/.prostor/skills/openclaw-imports/`
- **Список разрешённых команд** — паттерны одобрения
- **Настройки messaging** — конфиги платформ, разрешённые пользователи, рабочая директория
- **API-ключи** — разрешённые секреты (Telegram, OpenRouter, OpenAI, Anthropic, ElevenLabs)
- **TTS-ассеты** — рабочие аудиофайлы
- **Инструкции рабочего пространства** — AGENTS.md (с `--workspace-target`)

См. `prostor claw migrate --help` для всех опций или используйте навык `openclaw-migration` для интерактивной миграции с предпросмотром dry-run.

---

## Архитектура

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
├── agent/                # Внутренности агента (адаптеры провайдеров, память, кэширование, сжатие и т.д.)
├── prostor_cli/           # CLI-подкоманды, мастер настройки, загрузчик плагинов, движок скинов
├── tools/                # Реализации инструментов — автообнаружение через tools/registry.py
│   └── environments/     # Терминальные бэкенды (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging gateway — run.py + session.py + platforms/
│   ├── platforms/        # Адаптеры по платформам (telegram, discord, slack, whatsapp, signal, ...)
│   └── builtin_hooks/    # Точка расширения для всегда-зарегистрированных gateway-хуков
├── plugins/              # Система плагинов (см. раздел «Плагины» в AGENTS.md)
├── optional-skills/      # Тяжёлые/нишевые навыки, поставляемые, но не активные по умолчанию
├── skills/               # Встроенные навыки, поставляемые с репозиторием
├── ui-tui/               # Ink (React) терминальный UI — `prostor --tui`
├── tui_gateway/          # Python JSON-RPC бэкенд для TUI
├── acp_adapter/          # ACP-сервер (интеграция VS Code / Zed / JetBrains)
├── cron/                 # Планировщик — jobs.py, scheduler.py
├── scripts/              # run_tests.sh, release.py, вспомогательные скрипты
├── website/              # Docusaurus-сайт документации
└── tests/                # Набор тестов pytest
```

**Конфигурация пользователя:** `~/.prostor/config.yaml` (настройки), `~/.prostor/.env` (только API-ключи).
**Логи:** `~/.prostor/logs/` — `agent.log` (INFO+), `errors.log` (WARNING+), `gateway.log` при работе gateway. С учётом профилей через `get_prostor_home()`.
Просмотр: `prostor logs [--follow] [--level ...] [--session ...]`.

---

## Русский язык — основной язык продукта

Русский язык является основным языком Prostor по умолчанию:

- `DEFAULT_LANGUAGE='ru'` — язык интерфейса агента по умолчанию
- `DEFAULT_LOCALE='ru'` — региональные настройки по умолчанию
- Вся документация ведётся на русском языке
- Технические термины (API, CLI, Electron, React и т.п.) сохраняются на английском

Переключить язык можно через `config.yaml` (`agent.language`) или переменную окружения `PROSTOR_LANGUAGE`.

---

## Переменные окружения

Все переменные окружения Prostor используют префикс `PROSTOR_*`:

| Переменная | Назначение |
|------------|-----------|
| `PROSTOR_HOME` | Базовая директория данных (по умолчанию `~/.prostor`) |
| `PROSTOR_LANGUAGE` | Язык агента (по умолчанию `ru`) |
| `PROSTOR_LOCALE` | Региональные настройки (по умолчанию `ru`) |
| `PROSTOR_TUI` | Установите `1` для запуска TUI-режима |
| `PROSTOR_KANBAN_BOARD` | Закреплённая доска Kanban для worker-агента |

Полный справочник — на странице [Переменные окружения](https://github.com/maksim9510/Prostor/docs/reference/environment-variables).

---

## Контрибуция

Мы приветствуем контрибуции! См. [Руководство контрибьютора](CONTRIBUTING.md) и [документацию для разработчиков](https://github.com/maksim9510/Prostor/docs/developer-guide/contributing).

Быстрый старт для контрибьюторов — используйте стандартный установщик, затем работайте в
полной git-копии, которую он создаёт в `$PROSTOR_HOME/prostor-agent` (обычно
`~/.prostor/prostor-agent`). Это соответствует layout, используемому `prostor update`,
управляемым venv, ленивыми зависимостями, gateway и инструментарием документации.

```bash
curl -fsSL https://github.com/maksim9510/Prostor/install.sh | bash
cd "${PROSTOR_HOME:-$HOME/.prostor}/prostor-agent"
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

Ручное клонирование (для одноразовых клонов/CI, где не нужен managed install layout):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

---

## Сообщество

- 💬 [Discord](https://discord.gg/NousResearch)
- 📚 [Skills Hub](https://agentskills.io)
- 🐛 [Issues](https://github.com/maksim9510/Prostor/issues)
- 🔌 [computer-use-linux](https://github.com/avifenesh/computer-use-linux) — Linux MCP-сервер для управления рабочим столом для Prostor и других MCP-хостов, с AT-SPI accessibility trees, вводом Wayland/X11, скриншотами и таргетингом окон композитора.
- 🔌 [ProstorClaw](https://github.com/AaronWong1999/prostorclaw) — Community WeChat-мост: запуск Prostor Agent и OpenClaw на одном аккаунте WeChat.

---

## Contributors

Спасибо всем, кто делает Prostor лучше! 🎉

<!-- ALL-CONTRIBUTORS-LIST:START -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<!-- Здесь будут контрибьюторы — генерируются all-contributors bot -->
<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

Хотите попасть сюда? См. [`.all-contributorsrc`](.all-contributorsrc) для списка типов контрибуций (код, документация, баг-репорты, ревью, тесты, переводы, инфра).

Этот список автоматически обновляется через [all-contributors bot](https://allcontributors.org) — после первого контрибьютора бот появится в PR как авто-update.

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

Создано [Nous Research](https://nousresearch.com). Форк поддерживается на [github.com/maksim9510/Prostor](https://github.com/maksim9510/Prostor).
