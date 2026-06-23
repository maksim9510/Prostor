#!/bin/bash
set -euo pipefail

# ╔══════════════════════════════════════════════════════════════╗
# ║  build-deb.sh — двухэтапный установщик Prostor Agent          ║
# ║  Stage 1: .deb (~50-80 MB) — только Python код + setup скрипт  ║
# ║  Stage 2: setup.sh — докачивает venv, node_modules, frontend   ║
# ╚══════════════════════════════════════════════════════════════╝

PKG_NAME="prostor-agent"
PKG_VERSION="0.18.0"
PKG_MAINTAINER="Nous Research <contact@nousresearch.com>"
SRC_DIR="/opt/prostor"
BUILD_DIR="/tmp/prostor-deb-build"
DEB_OUT="/opt/prostor/dist"

echo "=== Building .deb package for Prostor Agent v${PKG_VERSION} (Stage 1: minimal) ==="

# Очистка
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$DEB_OUT"

# ───────────────────────────────────────────────────────────────
# 1. Копируем ТОЛЬКО исходный код (whitelist, без тяжёлых deps)
# ───────────────────────────────────────────────────────────────
echo "→ Копирую исходники (без venv, node_modules, dist, __pycache__)..."

mkdir -p "$BUILD_DIR/opt/prostor"

# Whitelist: только нужные директории и файлы
DIRS_TO_COPY=(
    prostor_core
    prostor_cli
    prostor_state.py
    prostor_state_*_mixin.py
    prostor_constants.py
    prostor_bootstrap.py
    gateway
    agent
    tools
    skills
    optional-skills
    plugins
    scripts
    installer
    assets
    apps/desktop/electron
    apps/desktop/dist
    apps/desktop/package.json
    apps/desktop/package-lock.json
    apps/desktop/assets
    apps/desktop/build
)

for dir in "${DIRS_TO_COPY[@]}"; do
    if [ -e "$SRC_DIR/$dir" ]; then
        mkdir -p "$BUILD_DIR/opt/prostor/$(dirname "$dir")"
        cp -a "$SRC_DIR/$dir" "$BUILD_DIR/opt/prostor/$dir"
    fi
done

# Отдельные файлы в корне
ROOT_FILES=(
    cli.py
    package.json
    package-lock.json
    pyproject.toml
    setup.cfg
    prostor_cli/__init__.py
)

for f in "${ROOT_FILES[@]}"; do
    if [ -e "$SRC_DIR/$f" ]; then
        mkdir -p "$BUILD_DIR/opt/prostor/$(dirname "$f")"
        cp -a "$SRC_DIR/$f" "$BUILD_DIR/opt/prostor/$f"
    fi
done

# ───────────────────────────────────────────────────────────────
# 2. Очищаем скопированное от кэшей и мусора
# ───────────────────────────────────────────────────────────────
echo "→ Очищаю кэши и мусор..."
find "$BUILD_DIR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true
find "$BUILD_DIR" -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name 'node_modules' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name 'dist' -path '*/apps/*' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name '.git' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

# ───────────────────────────────────────────────────────────────
# 3. Копируем setup.sh и update.sh из installer/linux/
# ───────────────────────────────────────────────────────────────
echo "→ Копирую first-run скрипты..."
mkdir -p "$BUILD_DIR/opt/prostor/installer/linux"
cp "$SRC_DIR/installer/linux/setup.sh" "$BUILD_DIR/opt/prostor/installer/linux/setup.sh"
cp "$SRC_DIR/installer/linux/update.sh" "$BUILD_DIR/opt/prostor/installer/linux/update.sh"
chmod +x "$BUILD_DIR/opt/prostor/installer/linux/"*.sh

# ───────────────────────────────────────────────────────────────
# 4. Launcher скрипты
# ───────────────────────────────────────────────────────────────
echo "→ Создаю launchers..."
mkdir -p "$BUILD_DIR/usr/local/bin"

# prostor — проверяет venv, если нет — запускает setup
cat > "$BUILD_DIR/usr/local/bin/prostor" << 'LAUNCHER'
#!/bin/bash
# Prostor CLI launcher (two-stage)
PROSTOR_DIR="/opt/prostor"
VENV_PYTHON="$PROSTOR_DIR/venv/bin/python"

# Если venv не существует — запускаем first-run setup
if [ ! -f "$VENV_PYTHON" ]; then
    echo "🔧 Первый запуск Prostor — устанавливаю зависимости..."
    bash "$PROSTOR_DIR/installer/linux/setup.sh"
    # Проверяем что venv создан
    if [ ! -f "$VENV_PYTHON" ]; then
        echo "❌ Ошибка: venv не создан. Запустите вручную: $PROSTOR_DIR/installer/linux/setup.sh"
        exit 1
    fi
fi

exec "$VENV_PYTHON" -m prostor_cli.main "$@"
LAUNCHER
chmod +x "$BUILD_DIR/usr/local/bin/prostor"

# prostor-update — обновление
cat > "$BUILD_DIR/usr/local/bin/prostor-update" << 'LAUNCHER'
#!/bin/bash
# Prostor self-update
exec bash /opt/prostor/installer/linux/update.sh "$@"
LAUNCHER
chmod +x "$BUILD_DIR/usr/local/bin/prostor-update"

# prostor-desktop — Electron launcher (с проверкой node_modules)
cat > "$BUILD_DIR/usr/local/bin/prostor-desktop" << 'LAUNCHER'
#!/bin/bash
# Prostor Desktop (Electron) launcher
PROSTOR_DIR="/opt/prostor"
DESKTOP_DIR="$PROSTOR_DIR/apps/desktop"

# Если node_modules/electron нет — запускаем setup (докачает Electron + deps)
if [ ! -d "$DESKTOP_DIR/node_modules/electron" ] || [ ! -d "$DESKTOP_DIR/dist" ]; then
    echo "🔧 Первый запуск Prostor Desktop — устанавливаю зависимости..."
    bash "$PROSTOR_DIR/installer/linux/setup.sh"
    # Проверяем что Electron установлен
    if [ ! -d "$DESKTOP_DIR/node_modules/electron" ]; then
        echo "❌ Electron не установлен. Запустите вручную: $PROSTOR_DIR/installer/linux/setup.sh"
        exit 1
    fi
fi

export DISPLAY="${DISPLAY:-:0}"
cd "$DESKTOP_DIR"
exec "$DESKTOP_DIR/node_modules/.bin/electron" electron/main.cjs "$@"
LAUNCHER
chmod +x "$BUILD_DIR/usr/local/bin/prostor-desktop"

# ───────────────────────────────────────────────────────────────
# 5. .desktop файл
# ───────────────────────────────────────────────────────────────
echo "→ Создаю .desktop entry..."
mkdir -p "$BUILD_DIR/usr/share/applications"
cat > "$BUILD_DIR/usr/share/applications/prostor.desktop" << 'DESKTOP'
[Desktop Entry]
Version=1.0
Type=Application
Name=Prostor Agent
Name[ru]=Prostor Агент
GenericName=AI Agent
GenericName[ru]=ИИ Агент
Comment=Self-learning AI agent with Desktop GUI
Comment[ru]=Самообучающийся ИИ-агент с десктопным GUI
Exec=/usr/local/bin/prostor-desktop
Icon=prostor
Terminal=false
Categories=Network;InstantMessaging;Development;Utility;
Keywords=ai;agent;chat;llm;assistant;
StartupNotify=true
StartupWMClass=Prostor
DESKTOP

# ───────────────────────────────────────────────────────────────
# 6. Иконка
# ───────────────────────────────────────────────────────────────
if [ -f "$SRC_DIR/assets/banner.png" ]; then
    mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"
    if command -v convert >/dev/null 2>&1; then
        convert "$SRC_DIR/assets/banner.png" -resize 256x256 \
            "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/prostor.png" 2>/dev/null || true
    else
        cp "$SRC_DIR/assets/banner.png" "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/prostor.png" 2>/dev/null || true
    fi
fi

# ───────────────────────────────────────────────────────────────
# 7. control файл
# ───────────────────────────────────────────────────────────────
echo "→ Создаю control файл..."
mkdir -p "$BUILD_DIR/DEBIAN"
cat > "$BUILD_DIR/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${PKG_VERSION}
Section: net
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.11), python3-venv, python3-pip, ca-certificates, curl, git
Recommends: ffmpeg, ripgrep, libolm3
Suggests: nodejs (>= 22), npm
Maintainer: ${PKG_MAINTAINER}
Description: Prostor Agent — self-learning AI agent (Stage 1: minimal)
 Prostor Agent is an open-source AI agent with:
 .
  * True terminal interface (TUI) with multiline editing and slash commands
  * Multi-channel gateway (Telegram, Discord, Slack, WhatsApp, Signal, CLI)
  * Self-improvement loop with agent-curated memory and skill auto-creation
  * Cross-session context recovery via FTS5 search
  * Cron scheduler with natural-language automation
  * Subagent delegation for parallel workstreams
 .
 This is a Stage 1 minimal package (~50-80 MB).
 Dependencies (Python venv, Node.js, frontend) are installed
 automatically on first run via /opt/prostor/installer/linux/setup.sh.
 .
 Homepage: https://github.com/maksim9510/Prostor
CONTROL

# ───────────────────────────────────────────────────────────────
# 8. postinst — показывает сообщение о первом запуске
# ───────────────────────────────────────────────────────────────
cat > "$BUILD_DIR/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Prostor Agent v0.18.0 установлен (Stage 1: minimal)!   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📦 Это минимальная установка (~50-80 MB)."
echo "   При первом запуске prostor автоматически:"
echo "   • Создаст Python venv и установит пакеты"
echo "   • Установит Node.js 22 (через nvm, если нет)"
echo "   • Установит Node зависимости (npm ci)"
echo "   • Соберёт frontend (npm run build)"
echo ""
echo "🚀 Команды:"
echo "   prostor           — первый запуск (докачает зависимости)"
echo "   prostor-desktop   — GUI окно (Electron)"
echo "   prostor-update    — обновление"
echo ""
echo "📖 Документация: https://github.com/maksim9510/Prostor"
echo ""
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi
exit 0
POSTINST
chmod +x "$BUILD_DIR/DEBIAN/postinst"

# ───────────────────────────────────────────────────────────────
# 9. prerm
# ───────────────────────────────────────────────────────────────
cat > "$BUILD_DIR/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e
echo "Удаление Prostor Agent..."
# Останавливаем gateway если запущен
if pgrep -f "gateway.run" > /dev/null 2>&1; then
    pkill -f "gateway.run" 2>/dev/null || true
fi
exit 0
PRERM
chmod +x "$BUILD_DIR/DEBIAN/prerm"

# ───────────────────────────────────────────────────────────────
# 10. Сборка через dpkg-deb (с fakeroot)
# ───────────────────────────────────────────────────────────────
echo "→ Собираю .deb..."
fakeroot dpkg-deb --build "$BUILD_DIR" "$DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb"

# ───────────────────────────────────────────────────────────────
# 11. Проверка
# ───────────────────────────────────────────────────────────────
echo ""
echo "=== Результат ==="
ls -lh "$DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb"
echo ""
echo "=== Содержимое пакета (топ-20 по размеру) ==="
dpkg-deb --contents "$DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb" 2>/dev/null | \
    sort -k5 -rn | head -20 || true
echo ""
echo "=== Информация о пакете ==="
dpkg-deb --info "$DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb" | head -20
echo ""
echo "✓ Готово: $DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb"

# 12. lintian (проверка качества)
if command -v lintian >/dev/null 2>&1; then
    echo ""
    echo "=== Lintian check ==="
    lintian "$DEB_OUT/${PKG_NAME}_${PKG_VERSION}_amd64.deb" 2>&1 | head -20 || true
fi