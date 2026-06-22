# Prostor Agent — обновление (Windows)

$ErrorActionPreference = "Stop"

$ProstorHome = if ($env:PROSTOR_HOME) { $env:PROSTOR_HOME } else { "$env:LOCALAPPDATA\Prostor" }
$ProstorBranch = if ($env:PROSTOR_BRANCH) { $env:PROSTOR_BRANCH } else { "main" }

function Write-Header { param($msg) Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "⚠ $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Prostor Agent — обновление              ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path "$ProstorHome\prostor-agent")) {
    Write-Warn "Prostor не установлен. Запустите сначала setup.ps1"
    exit 1
}

Set-Location "$ProstorHome\prostor-agent"

# 1. Текущая версия
$currentCommit = (git rev-parse --short HEAD).Trim()
Write-Header "Текущая версия: $currentCommit"

# 2. Получаем обновления
Write-Header "Получение обновлений"
git fetch origin $ProstorBranch
$latestCommit = (git rev-parse --short "origin/$ProstorBranch").Trim()

if ($currentCommit -eq $latestCommit) {
    Write-Ok "Уже последняя версия"
    exit 0
}

Write-Host "Обновляю: $currentCommit → $latestCommit"
git reset --hard "origin/$ProstorBranch"

# 3. Python
Write-Header "Обновление Python пакетов"
& "venv\Scripts\Activate.ps1"
pip install -e . --quiet
Write-Ok "Python пакеты обновлены"

# 4. Node
Write-Header "Обновление Node зависимостей"
npm ci --silent --no-audit --no-fund
Write-Ok "Node зависимости обновлены"

# 5. Frontend
Write-Header "Пересборка frontend"
npm run build 2>&1 | Select-Object -Last 5
Write-Ok "Frontend пересобран"

# 6. Перезапуск gateway
$gatewayRunning = Get-Process -Name "prostor" -ErrorAction SilentlyContinue
if ($gatewayRunning) {
    Write-Header "Перезапуск gateway"
    prostor gateway restart 2>$null
}

Write-Host ""
Write-Ok "Prostor обновлён до $latestCommit"
Write-Host ""