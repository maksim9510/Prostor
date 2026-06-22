# Prostor First-Run Setup (Windows)
# Устанавливает недостающие зависимости и собирает frontend

$ErrorActionPreference = "Stop"

$ProstorHome = if ($env:PROSTOR_HOME) { $env:PROSTOR_HOME } else { "$env:LOCALAPPDATA\Prostor" }
$ProstorRepo = "https://github.com/maksim9510/Prostor.git"
$ProstorBranch = if ($env:PROSTOR_BRANCH) { $env:PROSTOR_BRANCH } else { "main" }
$NodeVersion = if ($env:NODE_VERSION) { $env:NODE_VERSION } else { "22" }

function Write-Header { param($msg) Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Prostor Agent — первый запуск          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 1. Проверяем системные зависимости
Write-Header "Проверка системных зависимостей"
$missing = @()
foreach ($cmd in @("git", "python", "pip")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        $missing += $cmd
    }
}

if ($missing.Count -gt 0) {
    Write-Warn "Отсутствуют: $($missing -join ', ')"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Устанавливаю через winget..."
        foreach ($pkg in $missing) {
            winget install --accept-package-agreements --accept-source-agreements --id $pkg
        }
    } else {
        Write-Err "winget не найден. Установите вручную: $($missing -join ', ')"
    }
}
Write-Ok "Системные зависимости готовы"

# 2. Node.js
Write-Header "Проверка Node.js"
$nodeVersion = $null
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVersion = (node -v).TrimStart('v').Split('.')[0]
}

if (-not $nodeVersion -or [int]$nodeVersion -lt [int]$NodeVersion) {
    Write-Warn "Node.js $NodeVersion+ не найден"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Устанавливаю fnm..."
        winget install --accept-package-agreements --accept-source-agreements Schniz.fnm
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    }
    Write-Host "Устанавливаю Node.js $NodeVersion через fnm..."
    fnm install $NodeVersion
    fnm use $NodeVersion
    fnm default $NodeVersion
}
Write-Ok "Node.js $(node -v) готов"

# 3. Клонируем или обновляем репозиторий
Write-Header "Проверка репозитория"
if (-not (Test-Path "$ProstorHome\prostor-agent")) {
    Write-Host "Клонирую $ProstorRepo..."
    New-Item -ItemType Directory -Path $ProstorHome -Force | Out-Null
    git clone --depth 1 --branch $ProstorBranch $ProstorRepo "$ProstorHome\prostor-agent"
    Write-Ok "Репозиторий склонирован"
} else {
    Write-Host "Обновляю репозиторий..."
    Set-Location "$ProstorHome\prostor-agent"
    git fetch origin $ProstorBranch
    git reset --hard "origin/$ProstorBranch"
    Write-Ok "Репозиторий обновлён"
}

Set-Location "$ProstorHome\prostor-agent"

# 4. Python venv
Write-Header "Python зависимости"
if (-not (Test-Path "venv")) {
    Write-Host "Создаю virtual environment..."
    python -m venv venv
}
& "venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip --quiet
pip install -e . --quiet
Write-Ok "Python пакеты установлены"

# 5. Node зависимости
Write-Header "Node зависимости"
if (-not (Test-Path "node_modules") -or ((Get-Item "package.json").LastWriteTime -gt (Get-Item "node_modules").LastWriteTime)) {
    npm ci --silent --no-audit --no-fund
}
Write-Ok "Node зависимости установлены"

# 6. Frontend
Write-Header "Сборка frontend"
if (-not (Test-Path "dist") -or (Get-ChildItem "src" -Recurse -File -Filter "*.ts*" | Where-Object { $_.LastWriteTime -gt (Get-Item "dist").LastWriteTime } | Select-Object -First 1)) {
    npm run build 2>&1 | Select-Object -Last 5
}
Write-Ok "Frontend собран"

# 7. Проверяем CLI
Write-Header "Проверка установки"
$prostorCmd = Get-Command prostor -ErrorAction SilentlyContinue
if ($prostorCmd) {
    $version = prostor --version 2>&1
    Write-Ok "prostor установлен: $version"
} else {
    Write-Warn "prostor не найден в PATH. Добавьте $ProstorHome\prostor-agent\venv\Scripts в PATH"
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅ Prostor готов к работе!             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Запустите: prostor start"
Write-Host "Обновить:  prostor update"