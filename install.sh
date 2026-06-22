#!/usr/bin/env bash
# ============================================================================
# Prostor Agent — Universal Linux Installer
# ============================================================================
# Автоопределение дистрибутива и установка всех зависимостей + самого агента.
#
# Поддерживаемые дистрибутивы:
#   - Debian / Ubuntu / Astra Linux / Mint / Pop!_OS  (apt/dpkg)
#   - RHEL / CentOS / RedOS / Fedora / Rocky / Alma    (dnf/rpm)
#   - Arch / Manjaro / EndeavourOS                     (pacman)
#   - Alpine                                            (apk)
#   - NixOS                                             (nix profile)
#
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/maksim9510/Prostor/main/install.sh | bash
#   # или
#   ./install.sh                         # установить
#   ./install.sh --user                  # установить без sudo (в ~/.local)
#   ./install.sh --minimal               # без Docker, без ffmpeg extras
#   ./install.sh --no-system             # только Python пакет, без системных deps
#   PROSTOR_VERSION=v0.18.0 ./install.sh # конкретная версия
#
# Требования:
#   - bash 4+
#   - curl или wget
#   - Права root для системной установки (apt/dnf/pacman)
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Константы и defaults
# ---------------------------------------------------------------------------
readonly SCRIPT_VERSION="1.0.0"
readonly MIN_PYTHON_VERSION="3.11"
readonly PROSTOR_REPO="https://github.com/maksim9510/Prostor.git"
readonly PROSTOR_VERSION="${PROSTOR_VERSION:-}"
readonly INSTALL_DIR="${PROSTOR_INSTALL_DIR:-/opt/prostor}"
readonly DATA_DIR="${PROSTOR_DATA_DIR:-/var/lib/prostor}"
readonly SERVICE_USER="${PROSTOR_USER:-prostor}"
PROSTORD_BIN="/usr/local/bin/prostor"

# Флаги
INSTALL_USER_MODE=false    # --user
MINIMAL_MODE=false         # --minimal
NO_SYSTEM_DEPS=false       # --no-system
SKIP_SYSTEMCTL=false       # без systemd unit (для AstraLite, контейнеров)
DRY_RUN=false              # --dry-run
VERBOSE=false              # --verbose

# Цвета (если терминал поддерживает)
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    readonly C_RED='\033[0;31m'
    readonly C_GREEN='\033[0;32m'
    readonly C_YELLOW='\033[1;33m'
    readonly C_BLUE='\033[0;34m'
    readonly C_CYAN='\033[0;36m'
    readonly C_BOLD='\033[1m'
    readonly C_NC='\033[0m'
else
    readonly C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_CYAN='' C_BOLD='' C_NC=''
fi

# ---------------------------------------------------------------------------
# Утилиты логирования
# ---------------------------------------------------------------------------
log_info()    { echo -e "${C_BLUE}==>${C_NC} $*"; }
log_ok()      { echo -e "${C_GREEN} ✓${C_NC}  $*"; }
log_warn()    { echo -e "${C_YELLOW} ⚠${C_NC}  $*"; }
log_err()     { echo -e "${C_RED} ✗${C_NC}  $*" >&2; }
log_section() { echo -e "\n${C_BOLD}${C_CYAN}── $* ──${C_NC}"; }

die() { log_err "$*"; exit 1; }

# Verbose mode
if [ "${VERBOSE}" = "true" ]; then
    set -x
fi

# ---------------------------------------------------------------------------
# Парсинг аргументов
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --user)         INSTALL_USER_MODE=true; shift ;;
            --minimal)      MINIMAL_MODE=true; shift ;;
            --no-system)    NO_SYSTEM_DEPS=true; shift ;;
            --no-systemd)   SKIP_SYSTEMCTL=true; shift ;;
            --dry-run)      DRY_RUN=true; shift ;;
            --verbose|-v)   VERBOSE=true; shift ;;
            --version)      echo "install.sh v${SCRIPT_VERSION}"; exit 0 ;;
            --help|-h)
                sed -n '2,30p' "$0" | sed 's/^# \?//'
                exit 0
                ;;
            *)
                die "Unknown argument: $1. Try --help."
                ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Детекция дистрибутива
# Возвращает: ID дистрибутива в lowercase (debian, ubuntu, astra, rhel, ...)
# ---------------------------------------------------------------------------
detect_distro() {
    if [ ! -f /etc/os-release ]; then
        echo "unknown"
        return
    fi

    # Astra Linux особенный — у него свой ID в os-release, но мы
    # хотим группировать с Debian-based (apt работает так же)
    local id="" id_like="" name=""
    id=$(. /etc/os-release && echo "${ID:-unknown}" | tr '[:upper:]' '[:lower:]')
    id_like=$(. /etc/os-release && echo "${ID_LIKE:-}" | tr '[:upper:]' '[:lower:]')
    name=$(. /etc/os-release && echo "${NAME:-}" | tr '[:upper:]' '[:lower:]')

    # Astra Linux (Smolensk 1.8+, Orel, Vyborg) — отдельный ID в разных версиях
    case "$id" in
        astra*|smolensk|orel|vyborg)        echo "astra"; return ;;
    esac

    # RedOS (офиц. русский RHEL-клон)
    case "$id" in
        redos|red_os|red-os)                echo "redos"; return ;;
    esac

    # Если ID не распознан, смотрим на NAME
    case "$name" in
        *astra*)                            echo "astra"; return ;;
        *redos*|*red\ os*|*red-os*)         echo "redos"; return ;;
    esac

    # Стандартные семейства
    case "$id" in
        debian|ubuntu|linuxmint|pop|kubuntu|xubuntu|elementary|zorin) echo "debian" ;;
        centos|rhel|fedora|rocky|almalinux|ol|openmandriva)              echo "rhel" ;;
        arch|manjaro|endeavouros|garuda|arco)                            echo "arch" ;;
        alpine)                                                           echo "alpine" ;;
        nixos)                                                            echo "nixos" ;;
        *)
            # Fallback по ID_LIKE
            case "$id_like" in
                *debian*)  echo "debian" ;;
                *rhel*|*fedora*|*centos*)  echo "rhel" ;;
                *arch*)  echo "arch" ;;
                *alpine*) echo "alpine" ;;
                *) echo "unknown" ;;
            esac
            ;;
    esac
}

# Возвращает ОС-специфичные имена пакетов для установки
# Использует bash-массив PACKAGE_MANAGER_CMDS
get_packages() {
    local distro="$1"
    case "$distro" in
        debian)
            echo "python3 python3-venv python3-dev build-essential \
                  ca-certificates curl wget git ripgrep ffmpeg \
                  libolm3 libolm-dev pkg-config \
                  docker.io"
            ;;
        astra)
            # Astra 1.8 (Smolensk) — Python 3.7 в стандартных репах!
            # Нужно явно ставить 3.11 из testing или собирать.
            echo "python3 python3-dev python3-venv build-essential \
                  ca-certificates curl wget git ripgrep ffmpeg \
                  libolm3 libolm-dev pkg-config \
                  docker.io"
            ;;
        rhel|redos)
            echo "python3.11 python3.11-devel gcc gcc-c++ make cmake \
                   ca-certificates curl wget git ripgrep ffmpeg \
                   libolm libolm-devel pkgconfig \
                   docker"
            ;;
        arch)
            echo "python python-pip base-devel \
                  ca-certificates curl wget git ripgrep ffmpeg \
                   libolm docker"
            ;;
        alpine)
            echo "python3 py3-pip py3-virtualenv gcc musl-dev linux-headers \
                  ca-certificates curl wget git ripgrep ffmpeg4-libav libolm-dev docker"
            ;;
        nixos)
            echo ""
            ;;
        *)
            echo ""
            ;;
    esac
}

# Команды пакетного менеджера для каждого дистрибутива
# Результат в переменных: PKG_INSTALL, PKG_UPDATE, PKG_QUERY_INSTALLED
set_pkg_manager() {
    local distro="$1"
    case "$distro" in
        debian|astra)
            PKG_UPDATE="apt-get update"
            PKG_INSTALL="apt-get install -y --no-install-recommends"
            PKG_QUERY_INSTALLED="dpkg -l"
            ;;
        rhel|redos)
            if command -v dnf >/dev/null 2>&1; then
                PKG_UPDATE="dnf check-update || true"
                PKG_INSTALL="dnf install -y"
            else
                PKG_UPDATE="yum check-update || true"
                PKG_INSTALL="yum install -y"
            fi
            PKG_QUERY_INSTALLED="rpm -q"
            ;;
        arch)
            PKG_UPDATE="pacman -Sy --noconfirm"
            PKG_INSTALL="pacman -S --noconfirm --needed"
            PKG_QUERY_INSTALLED="pacman -Q"
            ;;
        alpine)
            PKG_UPDATE="apk update"
            PKG_INSTALL="apk add --no-cache"
            PKG_QUERY_INSTALLED="apk info -e"
            ;;
        nixos)
            PKG_UPDATE=""
            PKG_INSTALL=""
            PKG_QUERY_INSTALLED=""
            ;;
        *)
            PKG_UPDATE=""
            PKG_INSTALL=""
            PKG_QUERY_INSTALLED=""
            ;;
    esac
}

# Проверка — установлен ли пакет (по его бинарнику/команде)
is_installed() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1
}

# Требуется root?
needs_root() {
    if [ "$(id -u)" -ne 0 ] && [ "$INSTALL_USER_MODE" = "false" ]; then
        return 0  # нужен root
    fi
    return 1  # не нужен
}

# Запросить sudo пароль один раз
ensure_sudo() {
    if [ "$(id -u)" -ne 0 ]; then
        log_info "Запрашиваю sudo для системной установки..."
        sudo -v || die "Не удалось получить sudo. Запустите от root или используйте --user."
    fi
}

# Запустить с sudo если не root
run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

# ---------------------------------------------------------------------------
# Установка uv (Astral's Python package manager)
# ---------------------------------------------------------------------------
install_uv() {
    log_section "Установка uv"

    if command -v uv >/dev/null 2>&1; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null | awk '{print $2}')
        log_ok "uv уже установлен ($uv_version)"
        return 0
    fi

    local uv_installer
    uv_installer=$(mktemp 2>/dev/null || echo "/tmp/prostor-uv-install-$$.sh")

    log_info "Скачиваю uv installer..."
    if ! curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer"; then
        log_err "Не удалось скачать uv installer"
        rm -f "$uv_installer"
        return 1
    fi

    log_info "Устанавливаю uv..."
    if [ "$INSTALL_USER_MODE" = "true" ]; then
        # user-mode — без sudo
        export XDG_BIN_HOME="$HOME/.local/bin"
        sh "$uv_installer" >/dev/null 2>&1
    else
        sh "$uv_installer" >/dev/null 2>&1
    fi
    rm -f "$uv_installer"

    # Проверка
    if command -v uv >/dev/null 2>&1; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null | awk '{print $2}')
        log_ok "uv установлен ($uv_version)"
        return 0
    fi

    # Fallback: pip install uv
    log_warn "uv installer не сработал — пробую через pip"
    if command -v pip3 >/dev/null 2>&1; then
        run_root pip3 install --upgrade uv || die "Не удалось установить uv через pip"
        log_ok "uv установлен через pip"
        return 0
    fi

    die "Не удалось установить uv. Установите вручную: https://docs.astral.sh/uv/"
}

# ---------------------------------------------------------------------------
# Проверка Python
# ---------------------------------------------------------------------------
check_python() {
    log_section "Проверка Python ${MIN_PYTHON_VERSION}+"

    if command -v uv >/dev/null 2>&1; then
        # uv может сам скачать нужный Python
        log_info "uv сам установит Python ${MIN_PYTHON_VERSION} если нужно"
        return 0
    fi

    # Без uv — проверяем системный Python
    local py=""
    for candidate in python3.11 python3.12 python3.13 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            py="$candidate"
            break
        fi
    done

    if [ -z "$py" ]; then
        die "Python не найден. Установите python3.11+ через пакетный менеджер."
    fi

    local version
    version=$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        die "Найден Python $version, требуется ${MIN_PYTHON_VERSION}+"
    fi

    log_ok "Python $version найден ($py)"
}

# ---------------------------------------------------------------------------
# Установка системных пакетов
# ---------------------------------------------------------------------------
install_system_deps() {
    if [ "$NO_SYSTEM_DEPS" = "true" ]; then
        log_info "--no-system: пропускаю установку системных пакетов"
        return 0
    fi

    local distro="$1"
    log_section "Установка системных пакетов ($distro)"

    set_pkg_manager "$distro"

    if [ -z "$PKG_INSTALL" ]; then
        log_warn "Неизвестный дистрибутив '$distro'. Установите пакеты вручную:"
        log_warn "  - python3.11+ python3-dev"
        log_warn "  - build-essential / gcc / make / cmake"
        log_warn "  - ripgrep ffmpeg libolm docker.io"
        return 0
    fi

    local pkgs
    pkgs=$(get_packages "$distro")

    log_info "Обновляю индекс пакетов..."
    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY-RUN] $PKG_UPDATE"
    else
        run_root bash -c "$PKG_UPDATE" || log_warn "Не удалось обновить индекс пакетов (нет сети?)"
    fi

    log_info "Устанавливаю: $pkgs"
    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY-RUN] $PKG_INSTALL $pkgs"
    else
        # shellcheck disable=SC2086
        run_root bash -c "$PKG_INSTALL $pkgs" || {
            log_warn "Некоторые пакеты не установились — продолжаю"
            log_warn "Возможно нужны дополнительные репозитории (contrib, non-free, EPEL)"
        }
    fi

    log_ok "Системные пакеты обработаны"
}

# ---------------------------------------------------------------------------
# Установка Prostor (Python-пакет через uv)
# ---------------------------------------------------------------------------
install_prostor_python() {
    log_section "Установка Prostor (Python-пакет)"

    local uv_cmd="uv"
    if ! command -v "$uv_cmd" >/dev/null 2>&1; then
        if [ -x "$HOME/.local/bin/uv" ]; then
            uv_cmd="$HOME/.local/bin/uv"
        elif [ -x "$HOME/.cargo/bin/uv" ]; then
            uv_cmd="$HOME/.cargo/bin/uv"
        fi
    fi

    if ! command -v "$uv_cmd" >/dev/null 2>&1 && [ ! -x "$uv_cmd" ]; then
        die "uv не найден после установки — что-то пошло не так"
    fi

    # Используем uv tool install для глобальной установки (как pipx)
    local install_args=(tool install "prostor-agent[all]")
    if [ -n "$PROSTOR_VERSION" ]; then
        install_args+=("$PROSTOR_VERSION")
    fi

    log_info "Запускаю: ${uv_cmd} ${install_args[*]}"
    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY-RUN] ${uv_cmd} ${install_args[*]}"
    else
        if "$uv_cmd" "${install_args[@]}"; then
            log_ok "Prostor установлен через uv tool"
        else
            log_warn "uv tool install не сработал — пробую fallback на pip"
            run_root pip3 install --upgrade "prostor-agent[all]" \
                || die "Не удалось установить prostor-agent через pip"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Опционально: создать service user (для systemd / корпоративных установок)
# ---------------------------------------------------------------------------
create_service_user() {
    if [ "$SKIP_SYSTEMCTL" = "true" ]; then
        return 0
    fi
    if [ "$INSTALL_USER_MODE" = "true" ]; then
        return 0
    fi

    log_section "Service user (опционально)"

    if id "$SERVICE_USER" >/dev/null 2>&1; then
        log_ok "User '$SERVICE_USER' уже существует"
    else
        log_info "Создаю user '$SERVICE_USER' для запуска prostor как сервиса..."
        if [ "$DRY_RUN" = "true" ]; then
            log_info "[DRY-RUN] useradd --system --shell /usr/sbin/nologin $SERVICE_USER"
        else
            run_root useradd --system --shell /usr/sbin/nologin --home-dir "$DATA_DIR" "$SERVICE_USER" \
                || log_warn "Не удалось создать user — пропускаю (некритично)"
        fi
    fi

    # Создать data dir
    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY-RUN] mkdir -p $DATA_DIR && chown $SERVICE_USER: $DATA_DIR"
    else
        run_root mkdir -p "$DATA_DIR"
        run_root chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" 2>/dev/null || true
        log_ok "Data dir: $DATA_DIR"
    fi
}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
smoke_test() {
    log_section "Smoke test"

    if [ "$DRY_RUN" = "true" ]; then
        log_info "[DRY-RUN] prostor --version"
        return 0
    fi

    if command -v prostor >/dev/null 2>&1; then
        if prostor --version >/dev/null 2>&1; then
            log_ok "prostor --version: $(prostor --version 2>&1 | head -1)"
        else
            log_warn "prostor найден, но 'prostor --version' упал"
        fi
    else
        log_warn "prostor не найден в PATH"
        log_info "Попробуйте: source ~/.local/bin/env  (если uv tool) или перелогиньтесь"
    fi
}

# ---------------------------------------------------------------------------
# Финальный отчёт
# ---------------------------------------------------------------------------
print_report() {
    local distro="$1"

    cat <<EOF

${C_BOLD}${C_GREEN}╔══════════════════════════════════════════════════════════╗${C_NC}
${C_BOLD}${C_GREEN}║                                                          ║${C_NC}
${C_BOLD}${C_GREEN}║   Prostor Agent установлен успешно!                       ║${C_NC}
${C_BOLD}${C_GREEN}║                                                          ║${C_NC}
${C_BOLD}${C_GREEN}╚══════════════════════════════════════════════════════════╝${C_NC}

${C_CYAN}Дистрибутив:${C_NC}     $distro
${C_CYAN}Режим:${C_NC}          $([ "$INSTALL_USER_MODE" = "true" ] && echo "user (~/.local)" || echo "system")
${C_CYAN}Минимальный:${C_NC}     $MINIMAL_MODE
${C_CYAN}Версия:${C_NC}         ${PROSTOR_VERSION:-latest}

${C_BOLD}Что дальше:${C_NC}

  1. ${C_YELLOW}Проверьте установку:${C_NC}
     $ prostor --version

  2. ${C_YELLOW}Запустите setup wizard:${C_NC}
     $ prostor setup

  3. ${C_YELLOW}Начните разговор:${C_NC}
     $ prostor chat "Привет, расскажи о себе"

  4. ${C_YELLOW}Подключите Telegram/Discord (опционально):${C_NC}
     $ prostor gateway

${C_BOLD}Документация:${C_NC}
  - README:   https://github.com/maksim9510/Prostor
  - Docs:     https://maksim9510.github.io/Prostor
  - Skills:   https://github.com/maksim9510/Prostor/tree/main/skills

${C_BOLD}Если что-то пошло не так:${C_NC}
  - Запустите с --verbose для подробного лога
  - Создайте issue: https://github.com/maksim9510/Prostor/issues
  - Discord:     https://discord.gg/NousResearch

EOF
}

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"

    log_section "Prostor Universal Linux Installer v${SCRIPT_VERSION}"
    log_info "Начинаю установку..."

    # 1. Детекция
    local distro
    distro=$(detect_distro)
    log_ok "Дистрибутив: $distro"

    if [ "$distro" = "unknown" ]; then
        log_warn "Не удалось определить дистрибутив (/etc/os-release отсутствует или неизвестный ID)"
        log_warn "Установлю только Python-пакет и uv, системные пакеты пропущу"
        NO_SYSTEM_DEPS=true
    fi

    # 2. Root check
    if needs_root && [ "$distro" != "nixos" ]; then
        ensure_sudo
    fi

    # 3. Системные пакеты
    install_system_deps "$distro"

    # 4. uv
    install_uv

    # 5. Python check
    check_python

    # 6. Сам Prostor
    install_prostor_python

    # 7. Service user (опционально)
    create_service_user

    # 8. Smoke test
    smoke_test

    # 9. Отчёт
    print_report "$distro"
}

main "$@"
