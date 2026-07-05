@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Установка бота дежурств ===
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Установите с https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo Ошибка создания .venv
        pause
        exit /b 1
    )
)

echo Устанавливаю зависимости...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Ошибка установки пакетов.
    pause
    exit /b 1
)

echo.
echo === Установка завершена ===
echo Отредактируйте файл .env (BOT_TOKEN).
echo Запуск: start.bat
echo.
pause
