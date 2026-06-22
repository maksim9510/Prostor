# Prostor Installer

Двухэтапный установщик Prostor Agent. Stage 1 устанавливает только CLI и
first-run скрипт; Stage 2 запускается при первом старте и докачивает
Python/Node зависимости и собирает frontend из GitHub.

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Пакет (.deb / .exe / .msi) ~50-100 MB          │
│  ─────────────────────────────────────────────────       │
│  • prostor CLI (Python)                                   │
│  • prostor gateway (Python)                               │
│  • setup.sh / setup.ps1 (first-run)                       │
│  • config.yaml (defaults)                                 │
│  • DEBIAN/postinst (запускает setup.sh)                   │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼  при первом `prostor start`
┌─────────────────────────────────────────────────────────┐
│  Stage 2: setup.sh / setup.ps1                            │
│  ─────────────────────────────────────────────────       │
│  1. Проверяет системные зависимости (git, python, pip)   │
│  2. Устанавливает Node.js 22 через nvm/fnm               │
│  3. Клонирует или обновляет репозиторий                   │
│     → $HOME/.prostor/prostor-agent                       │
│  4. Создаёт Python venv и ставит пакеты (pip install)    │
│  5. Ставит Node зависимости (npm ci)                     │
│  6. Собирает frontend (npm run build)                    │
└─────────────────────────────────────────────────────────┘
```

## Обновление

```bash
# Linux
prostor update          # или напрямую: ~/.prostor/update.sh

# Windows
prostor update          # или напрямую: %LOCALAPPDATA%\Prostor\update.ps1
```

Обновление делает:
1. `git fetch && git reset --hard origin/main`
2. `pip install -e .`
3. `npm ci && npm run build`
4. Перезапускает gateway если запущен

## Файлы

- `linux/setup.sh` — Linux/macOS first-run
- `linux/update.sh` — Linux/macOS update
- `windows/setup.ps1` — Windows first-run
- `windows/update.ps1` — Windows update

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `PROSTOR_HOME` | `$HOME/.prostor` (Linux) / `%LOCALAPPDATA%\Prostor` (Win) | Директория установки |
| `PROSTOR_BRANCH` | `main` | Git ветка |
| `NODE_VERSION` | `22` | Версия Node.js |

## TODO (Stage 1 уменьшение .deb)

Сейчас Stage 1 .deb весит 2.0 GB. Для реального уменьшения до ~100 MB нужно:

1. Не включать `venv/` в пакет — создаётся при setup
2. Не включать `node_modules/` — ставится при setup
3. Не включать `dist/` (frontend) — собирается при setup
4. Не включать `.npm/`, `__pycache__/`, `.next/` и прочие кэши
5. Оставить только:
   - `*.py` файлы (prostor_core, prostor_cli, gateway, agent, tools)
   - `package.json`, `package-lock.json`
   - `setup.sh`, `update.sh`, `config.yaml`
   - `bin/prostor` (entry point)

Текущий `build-deb.sh` копирует всё содержимое. Нужно переписать с whitelist.