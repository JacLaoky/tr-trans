#!/bin/bash
set -e

echo "================================================"
echo " TR Trans - 韓服 Tales Runner 翻譯器 安裝程式"
echo "================================================"
echo ""

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[錯誤] 找不到 python3，請先安裝 Python 3.10+"
    echo " 建議使用 Homebrew: brew install python"
    exit 1
fi

echo "[1/3] 升級 pip..."
python3 -m pip install --upgrade pip

echo ""
echo "[2/3] 安裝相依套件（EasyOCR 含 PyTorch，約 2-3 GB，請耐心等候）..."
python3 -m pip install -r requirements.txt

echo ""
echo "[3/3] 安裝完成！"
echo ""
echo " macOS 重要提示："
echo "   首次執行時，macOS 會要求「螢幕錄製」權限。"
echo "   請前往 系統設定 > 隱私權與安全性 > 螢幕錄製"
echo "   將 Terminal（或你的 Python/IDE）加入允許清單。"
echo ""
echo " 執行方式：bash run.sh 或 python3 main.py"
echo ""
