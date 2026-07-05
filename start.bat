@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите setup.bat
    pause
    exit /b 1
)

if not exist ".env" (
    echo Файл .env не найден. Скопируйте .env.example в .env и заполните.
    pause
    exit /b 1
)

echo Запуск бота... (остановка: Ctrl+C)
".venv\Scripts\python.exe" main.py
pause
