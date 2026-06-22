# Prostor Agent — обновление
# Запускается как `prostor update` или напрямую из setup.sh

set -e

PROSTOR_HOME="${PROSTOR_HOME:-$HOME/.prostor}"
PROSTOR_REPO="https://github.com/maksim9510/Prostor.git"
PROSTOR_BRANCH="${PROSTOR_BRANCH:-main}"

log() { echo -e "\033[0;34m▶\033[0m $1"; }
ok() { echo -e "\033[0;32m✓\033[0m $1"; }
warn() { echo -e "\033[1;33m⚠\033[0m $1"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Prostor Agent — обновление              ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if [ ! -d "$PROSTOR_HOME/prostor-agent" ]; then
    warn "Prostor не установлен. Запустите сначала setup.sh"
    exit 1
fi

cd "$PROSTOR_HOME/prostor-agent"

# 1. Сохраняем текущую версию для возможного отката
CURRENT_COMMIT=$(git rev-parse --short HEAD)
log "Текущая версия: $CURRENT_COMMIT"

# 2. Получаем обновления
log "Получаю обновления..."
git fetch origin "$PROSTOR_BRANCH"

LATEST_COMMIT=$(git rev-parse --short "origin/$PROSTOR_BRANCH")
if [ "$CURRENT_COMMIT" = "$LATEST_COMMIT" ]; then
    ok "Уже последняя версия"
    exit 0
fi

log "Обновляю: $CURRENT_COMMIT → $LATEST_COMMIT"
git reset --hard "origin/$PROSTOR_BRANCH"

# 3. Обновляем Python зависимости
log "Обновляю Python пакеты..."
# shellcheck source=/dev/null
source venv/bin/activate
pip install -e . --quiet
ok "Python пакеты обновлены"

# 4. Обновляем Node зависимости
log "Обновляю Node зависимости..."
npm ci --silent --no-audit --no-fund 2>&1 | tail -3
ok "Node зависимости обновлены"

# 5. Пересобираем frontend
log "Пересобираю frontend..."
npm run build 2>&1 | tail -3
ok "Frontend пересобран"

# 6. Перезапускаем gateway если запущен
if pgrep -f "gateway.run" > /dev/null 2>&1; then
    log "Перезапускаю gateway..."
    prostor gateway restart 2>/dev/null || true
fi

echo ""
ok "Prostor обновлён до $LATEST_COMMIT"
echo ""