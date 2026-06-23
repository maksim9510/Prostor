#!/bin/bash
# Prostor First-Run Setup
# Устанавливает недостающие зависимости и собирает frontend

set -e

PROSTOR_HOME="${PROSTOR_HOME:-$HOME/.prostor}"
PROSTOR_REPO="https://github.com/maksim9510/Prostor.git"
PROSTOR_BRANCH="${PROSTOR_BRANCH:-main}"
NODE_VERSION="${NODE_VERSION:-22}"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}▶${NC} $1"; }
ok() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Prostor Agent — первый запуск          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Проверяем системные зависимости
log "Проверяю системные зависимости..."
MISSING_DEPS=()
for cmd in git python3 pip; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING_DEPS+=("$cmd")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    warn "Отсутствуют: ${MISSING_DEPS[*]}"
    if command -v apt-get &> /dev/null; then
        log "Устанавливаю через apt-get..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq "${MISSING_DEPS[@]}"
        ok "Системные зависимости установлены"
    elif command -v dnf &> /dev/null; then
        log "Устанавливаю через dnf..."
        sudo dnf install -y "${MISSING_DEPS[@]}"
        ok "Системные зависимости установлены"
    else
        err "Не найден пакетный менеджер. Установите вручную: ${MISSING_DEPS[*]}"
        exit 1
    fi
else
    ok "Все системные зависимости найдены"
fi

# 2. Проверяем/устанавливаем Node.js
log "Проверяю Node.js..."
if ! command -v node &> /dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 22 ]; then
    warn "Node.js 22+ не найден"

    # Пробуем через nvm
    export NVM_DIR="$HOME/.nvm"
    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
        log "Устанавливаю nvm..."
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    fi
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

    log "Устанавливаю Node.js $NODE_VERSION..."
    nvm install "$NODE_VERSION"
    nvm use "$NODE_VERSION"
    nvm alias default "$NODE_VERSION"
    ok "Node.js $(node -v) установлен"
else
    ok "Node.js $(node -v) найден"
fi

# 3. Клонируем или обновляем репозиторий
log "Проверяю репозиторий Prostor..."
if [ ! -d "$PROSTOR_HOME/prostor-agent" ]; then
    log "Клонирую $PROSTOR_REPO..."
    mkdir -p "$PROSTOR_HOME"
    git clone --depth 1 --branch "$PROSTOR_BRANCH" "$PROSTOR_REPO" "$PROSTOR_HOME/prostor-agent"
    ok "Репозиторий склонирован в $PROSTOR_HOME/prostor-agent"
else
    log "Обновляю репозиторий..."
    cd "$PROSTOR_HOME/prostor-agent"
    git fetch origin "$PROSTOR_BRANCH"
    git reset --hard "origin/$PROSTOR_BRANCH"
    ok "Репозиторий обновлён"
fi

cd "$PROSTOR_HOME/prostor-agent"

# 4. Устанавливаем Python зависимости
log "Устанавливаю Python пакеты..."
if [ ! -d "venv" ]; then
    log "Создаю virtual environment..."
    python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -e . --quiet
ok "Python пакеты установлены"

# 5. Устанавливаем Node зависимости и собираем frontend
log "Устанавливаю Node зависимости..."
if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
    npm ci --silent --no-audit --no-fund 2>&1 | tail -3
fi
ok "Node зависимости установлены"

log "Собираю frontend..."
if [ ! -d "dist" ] || [ -n "$(find src -newer dist -name '*.ts' -o -newer dist -name '*.tsx' 2>/dev/null | head -1)" ]; then
    npm run build 2>&1 | tail -5
fi
ok "Frontend собран"

# 6. Устанавливаем Electron (для prostor-desktop)
log "Устанавливаю Electron для Desktop GUI..."
if [ -d "apps/desktop" ]; then
    cd apps/desktop
    if [ ! -d "node_modules/electron" ]; then
        npm install --silent --no-audit --no-fund 2>&1 | tail -3
    fi
    ok "Electron установлен"
    cd "$PROSTOR_HOME/prostor-agent"
fi

# 6. Проверяем CLI
log "Проверяю установку..."
if command -v prostor &> /dev/null; then
    PROSTOR_VERSION=$(prostor --version 2>&1 || echo "unknown")
    ok "prostor установлен: $PROSTOR_VERSION"
else
    warn "prostor не найден в PATH. Добавьте $PROSTOR_HOME/prostor-agent/venv/bin в PATH"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ Prostor готов к работе!             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Запустите: prostor start"
echo "Обновить:  prostor update"
echo ""