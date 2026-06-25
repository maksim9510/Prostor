# Prostor — Инструкция по upstream sync и rebrand

## Быстрый старт (для опытных)

```bash
# Один скрипт делает всё:
python scripts/rebrand/post_merge.py
```

## Подробная инструкция (для понимания)

### Ситуация 1: Обновить Prostor (prostor update)

Когда появилось обновление и нужно подтянуть новые фичи/фиксы.

```bash
# 1. Запустить обновление
prostor update

# 2. Если что-то сломалось (hermes_cli not found, IPC bridge unavailable):
python scripts/rebrand/restore_prostor.py

# 3. Проверить что работает
prostor --version
```

**Почему это работает:**
- `prostor update` теперь скачивает ZIP с **нашего форка** (maksim9510/Prostor)
- rebrand сохраняется, PROTECTED файлы на месте
- Если всё равно что-то сломалось → `restore_prostor.py` восстановит

---

### Ситуация 2: Синхронизация с upstream ( NousResearch/hermes-agent)

Когда upstream добавил много нового и нужно подтянуть.

```bash
# Шаг 1: Merge upstream
git fetch upstream main
git merge upstream/main

# Шаг 2: Если конфликты — решить вручную
# (git status покажет conflicted файлы)

# Шаг 3: Rebrand
python scripts/rebrand/apply_rebrand.py

# Шаг 4: Syntax check
python -c "import py_compile; py_compile.compile('prostor_cli/main.py', doraise=True)"

# Шаг 5: Commit & push
git add -A
git commit -m "sync: upstream merge + rebrand"
git push origin main

# Шаг 6: Обновить установленную копию
python scripts/rebrand/restore_prostor.py
```

---

### Ситуация 3: Собрать новый installer

```bash
cd apps/desktop
npm install --legacy-peer-deps
npm run build
npm run dist:win
# Результат: apps/desktop/release/Prostor-0.17.0-win-x64.exe
```

---

## Что защищено (PROTECTED — никогда не перезаписывается)

```
tools/hashline.py          — O(1) hash matching (4700x)
tools/batch_patch_tool.py  — N patches за 1 round-trip
tools/batch_read_tool.py   — N reads за 1 round-trip
tools/token_budget.py      — Auto-warn 75/90/95%
tools/context_optimizer.py — Priority-aware compression
tools/adaptive_router.py   — Batch hints
tools/result_compression.py — 99.6% savings
toolsets.py                — Tier system (22 core + 28 tier2)
prostor_constants.py       — Aliases для совместимости
hermes_cli/main.py         — Shim для Electron
prostor_cli/*_mixin.py     — Все миксины (10 CLI + 11 gateway)
AGENTS.md                  — Руководство для разработчиков
```

## Что ре-брендится автоматически

| Паттерн | Замена | Куда |
|---------|--------|------|
| `hermes_cli` | `prostor_cli` | Python imports |
| `HERMES_HOME` | `PROSTOR_HOME` | Env vars |
| `hermesDesktop` | `prostorDesktop` | TypeScript |
| `normalizeHermesHomeRoot` | `normalizeProstorHomeRoot` | Electron |
| `load_hermes_dotenv` | `load_prostor_dotenv` | Python |
| `hermesActiveSessions` | `prostorActiveSessions` | i18n |

## Скрипты

| Скрипт | Когда использовать |
|--------|-------------------|
| `scripts/rebrand/post_merge.py` | После upstream merge |
| `scripts/rebrand/apply_rebrand.py` | Только rebrand (без merge) |
| `scripts/rebrand/restore_prostor.py` | После `prostor update` |

## Часто задаваемые вопросы

### Q: Как часто делать upstream sync?
A: 2-3 раза в неделю. Upstream активен (~100 коммитов/день).

### Q: Что делать если `prostor update` сломался?
A: Запустить `python scripts/rebrand/restore_prostor.py`

### Q: Что делать если `prostor update` не запускается?
A: Скопировать исправленные файлы из dev repo:
```bash
cp prostor_cli/main.py C:/Users/admin1/AppData/Local/prostor/prostor-agent/prostor_cli/
cp hermes_cli/main.py C:/Users/admin1/AppData/Local/prostor/prostor-agent/hermes_cli/
cp prostor_constants.py C:/Users/admin1/AppData/Local/prostor/prostor-agent/
```

### Q: Как проверить что rebrand применился?
A:
```bash
grep -rn "hermes_cli" prostor_cli/ --include='*.py' | wc -l
# Должно быть 0 (или только комментарии)
```

### Q: Как добавить новый PROTECTED файл?
A: Отредактировать `scripts/rebrand/rebrand_manifest.json` → `protected_files`

### Q: Как добавить новый паттерн rebrand?
A: Отредактировать `scripts/rebrand/rebrand_manifest.json` → нужный section
