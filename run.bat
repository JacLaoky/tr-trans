@echo off
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Please run install.bat first.
    pause
)
