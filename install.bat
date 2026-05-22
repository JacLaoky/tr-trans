@echo off
echo ================================================
echo  TR Trans - Tales Runner KR Translator  SETUP
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/2] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [2/2] Installing packages (EasyOCR needs ~2-3 GB, please wait)...
python -m pip install -r requirements.txt

echo.
echo Done! Run run.bat to start.
echo.
pause
