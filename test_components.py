"""
逐項測試各元件，方便排查問題。
執行: python3 test_components.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))


def check(label):
    print(f"\n{'─'*40}\n測試: {label}")

def ok(msg=""):
    print(f"  ✓ {msg}")

def fail(msg=""):
    print(f"  ✗ {msg}")


# ── 1. 基本 import ──────────────────────────────────────────────
check("基本套件 import")
missing = []
for pkg, mod in [("mss", "mss"), ("Pillow", "PIL"), ("numpy", "numpy"),
                 ("opencv", "cv2"), ("deep-translator", "deep_translator")]:
    try:
        __import__(mod)
        ok(pkg)
    except ImportError:
        fail(f"{pkg} 未安裝")
        missing.append(pkg)

if missing:
    print(f"\n  尚未安裝: {', '.join(missing)}")
    print("  請先執行: pip3 install mss Pillow numpy opencv-python-headless deep-translator")
    sys.exit(1)


# ── 2. 翻譯（需要網路）──────────────────────────────────────────
check("翻譯引擎 (Google Translate, 需要網路)")
try:
    from translator import TranslationEngine
    t = TranslationEngine()
    result = t.translate("안녕하세요")
    ok(f"「안녕하세요」→「{result}」")
except Exception as e:
    fail(str(e))


# ── 3. 截圖 ─────────────────────────────────────────────────────
check("截圖 (需要 macOS 螢幕錄製權限)")
try:
    from capture import ScreenCapture
    cap = ScreenCapture()
    img = cap.capture_full_screen()
    h, w = img.shape[:2]
    if w < 100 or img.mean() < 1:
        fail(f"截到黑畫面 ({w}x{h}) — 請到「系統設定 > 隱私權 > 螢幕錄製」允許 Terminal")
    else:
        ok(f"截圖成功，解析度 {w}x{h}")
except Exception as e:
    fail(str(e))


# ── 4. OCR（需要 easyocr + PyTorch）────────────────────────────
check("OCR 引擎 (easyocr)")
try:
    import easyocr
    ok("easyocr 已安裝")
    check("  OCR 識別韓文（用合成圖測試，首次會下載模型）")
    import numpy as np, cv2
    # 合成一張含韓文的白底黑字圖
    img = np.ones((80, 300, 3), dtype=np.uint8) * 255
    cv2.putText(img, "?? ? ????", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    from ocr import OCREngine
    engine = OCREngine()
    text = engine.extract_text(img, log_cb=lambda m: print(f"  [{m}]"))
    ok(f"OCR 回傳: 「{text}」")
except ImportError:
    fail("easyocr 未安裝 — 執行: pip3 install easyocr  （約 2GB，需時較長）")
except Exception as e:
    fail(str(e))


# ── 5. tkinter 視窗 ──────────────────────────────────────────────
check("tkinter 視窗（會短暫彈出一個視窗）")
try:
    import tkinter as tk
    root = tk.Tk()
    root.title("TR Trans 測試")
    root.geometry("300x100")
    from utils import cjk_font
    tk.Label(root, text="測試視窗，3 秒後自動關閉", font=cjk_font(12)).pack(expand=True)
    root.after(3000, root.destroy)
    root.mainloop()
    ok("tkinter 視窗正常")
except Exception as e:
    fail(str(e))


print(f"\n{'─'*40}")
print("測試完成。")
