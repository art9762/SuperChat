<#
.SYNOPSIS
Скрипт установки мессенджера "SuperChat" для Windows

.DESCRIPTION
Этот скрипт клонирует репозиторий, настраивает виртуальное окружение Python
и создает глобальную команду "superchat" для запуска мессенджера.
#>

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "    Установка SuperChat Messenger" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Проверка наличия Python
try {
    $pythonVersion = & python --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Python not found" }
} catch {
    Write-Host "❌ Ошибка: Python не установлен. Пожалуйста, скачайте и установите Python 3 с python.org (не забудьте поставить галочку 'Add Python to PATH' при установке)." -ForegroundColor Red
    exit 1
}

# Проверка наличия Git
try {
    $gitVersion = & git --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Git not found" }
} catch {
    Write-Host "❌ Ошибка: Git не установлен. Пожалуйста, установите Git for Windows (git-scm.com)." -ForegroundColor Red
    exit 1
}

$installDir = Join-Path $env:USERPROFILE ".superchat"
$binDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"

Write-Host "📂 Создание директории установки $installDir..." -ForegroundColor Yellow
if (!(Test-Path $installDir)) {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
}
if (!(Test-Path $binDir)) {
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
}

# Клонирование или обновление репозитория
$gitDir = Join-Path $installDir ".git"
if (Test-Path $gitDir) {
    Write-Host "🔄 Обновление SuperChat..." -ForegroundColor Yellow
    Set-Location $installDir
    & git pull origin main
} else {
    Write-Host "📥 Загрузка исходного кода..." -ForegroundColor Yellow
    & git clone https://github.com/art9762/SuperChat.git $installDir
    Set-Location $installDir
}

# Настройка виртуального окружения
Write-Host "🐍 Настройка виртуального окружения Python..." -ForegroundColor Yellow
Set-Location $installDir
& python -m venv venv

# Запуск скрипта активации и установка зависимостей
Write-Host "📦 Установка зависимостей..." -ForegroundColor Yellow
$activateScript = Join-Path $installDir "venv\Scripts\activate.ps1"

# Выполняем установку внутри окружения, напрямую обращаясь к pip в venv
$pipExe = Join-Path $installDir "venv\Scripts\pip.exe"
& $pipExe install --upgrade pip
& $pipExe install -r client\requirements.txt

# Создание запускаемого файла (.cmd)
Write-Host "⚙️ Создание команды 'superchat'..." -ForegroundColor Yellow
$cmdFile = Join-Path $binDir "superchat.cmd"

$cmdContent = @"
@echo off
set "INSTALL_DIR=%USERPROFILE%\.superchat"
call "%USERPROFILE%\.superchat\venv\Scripts\activate.bat"
python "%USERPROFILE%\.superchat\client\ui.py" %*
"@

Set-Content -Path $cmdFile -Value $cmdContent -Encoding UTF8

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Установка успешно завершена!" -ForegroundColor Green
Write-Host "Теперь вы можете открыть командную строку (cmd) или PowerShell и ввести:" -ForegroundColor White
Write-Host "   superchat" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan