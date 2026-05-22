@echo off
chcp 65001 >nul
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [錯誤] 啟動失敗，請先執行 install.bat 安裝相依套件。
    pause
)
