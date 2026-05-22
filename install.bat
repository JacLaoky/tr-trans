@echo off
chcp 65001 >nul
echo ================================================
echo  TR Trans - 韓服 Tales Runner 翻譯器 安裝程式
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10+
    echo  下載: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 升級 pip...
python -m pip install --upgrade pip

echo.
echo [2/3] 安裝相依套件（EasyOCR 含 PyTorch，約 2-3 GB，請耐心等候）...
python -m pip install -r requirements.txt

echo.
echo [3/3] 安裝完成！
echo.
echo  執行方式：雙擊 run.bat 或執行 python main.py
echo.
pause
