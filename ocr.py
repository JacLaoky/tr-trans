import cv2
import numpy as np
import sys


class OCREngine:
    def __init__(self):
        self._reader    = None          # Korean model (translation + ÷ detection)
        self._reader_en = None          # English model (math +/-/× detection)
        self._langs     = ["ko"]        # default: Korean only
        self._use_hanzi = False

    def set_hanzi(self, enabled: bool):
        """Enable/disable Chinese character (漢字) recognition.
        Requires an extra ~200MB model download on first use.
        Resets the reader so it reloads on next use.
        """
        langs = ["ko", "ch_sim"] if enabled else ["ko"]
        if langs != self._langs:
            self._langs = langs
            self._reader = None   # force reload with new language list
            self._use_hanzi = enabled

    def _ensure_loaded(self, log_cb=None):
        if self._reader is not None:
            return

        langs_str = " + 漢字(ch_sim)" if "ch_sim" in self._langs else ""
        if log_cb:
            log_cb(f"正在載入 OCR 模型 [韓文{langs_str}]（首次需下載，請稍候）...")

        import easyocr

        # Intercept stdout so EasyOCR's tqdm download bars appear in our log
        class _LogCapture:
            def __init__(self, cb):
                self._cb = cb
                self._buf = ""
            def write(self, s):
                self._buf += s
                if "\n" in self._buf:
                    lines = self._buf.split("\n")
                    for line in lines[:-1]:
                        line = line.strip()
                        if line and self._cb:
                            self._cb(f"[下載] {line}")
                    self._buf = lines[-1]
            def flush(self):
                pass

        old_stdout = sys.stdout
        if log_cb:
            sys.stdout = _LogCapture(log_cb)
        try:
            self._reader = easyocr.Reader(self._langs, gpu=False, verbose=True)
        finally:
            sys.stdout = old_stdout

        if log_cb:
            log_cb("OCR 模型載入完成。")

    # ── Tesseract (number-specific OCR, optional) ─────────────────────────────
    @staticmethod
    def _tesseract_available() -> bool:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    @staticmethod
    def _gold_mask(img_bgr: np.ndarray) -> np.ndarray:
        """Extract golden/orange game digits via HSV color mask, scaled 3×."""
        hsv    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        mask   = cv2.inRange(hsv, np.array([8, 100, 120]), np.array([48, 255, 255]))
        k5     = np.ones((5, 5), np.uint8)
        filled = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k5)
        h, w   = filled.shape
        return cv2.resize(filled, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)

    @staticmethod
    def _read_with_tesseract(gold: np.ndarray) -> str:
        """Run Tesseract in single-line digit mode on a gold-mask image."""
        import pytesseract
        from PIL import Image as _PILImage
        pil = _PILImage.fromarray(gold)
        # psm 7 = single text line; whitelist to digits + common math operators
        cfg = (r'--psm 7 --oem 3 '
               r'-c tessedit_char_whitelist=0123456789+\-*/=?')
        return pytesseract.image_to_string(pil, config=cfg).strip()

    def _ensure_math_loaded(self, log_cb=None):
        """Lazily load English EasyOCR (fallback when Tesseract unavailable)."""
        if self._reader_en is not None:
            return
        if log_cb:
            log_cb("[OCR] 載入算數模型（English EasyOCR）...")
        import easyocr
        self._reader_en = easyocr.Reader(["en"], gpu=False, verbose=False)
        if log_cb:
            log_cb("[OCR] 算數模型載入完成。")

    def extract_text_math(self, img_bgr: np.ndarray, log_cb=None) -> str:
        """
        Number-focused OCR for math equations.

        Preferred path – Tesseract (digit-specific model, fast, accurate):
          Uses gold-mask preprocessing (isolates orange digits on black).
          Restricted to digits + math operators.
          If Tesseract gives a parseable equation → return immediately.

        Fallback path – EasyOCR two-stage (when Tesseract not installed):
          Stage 1: English model (good for +, -, ×).
          Stage 2: Korean model (÷ reads as '응' → substitution → '/').

        Install Tesseract for best results:
          Windows: https://github.com/UB-Mannheim/tesseract/wiki
          then: pip install pytesseract
        """
        import re as _re
        from math_solver import solve as _solve

        # ── Tesseract path (preferred) ────────────────────────────────────────
        if self._tesseract_available():
            gold = self._gold_mask(img_bgr)
            text = self._read_with_tesseract(gold)
            result = _solve(text)
            if result and _re.search(r'[+\-*/]', result[0]):
                return text
            # Tesseract gave something but no clear operator → also try EasyOCR

        # ── EasyOCR fallback ──────────────────────────────────────────────────
        self._ensure_math_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr, scale=True)

        def _read(reader):
            res = reader.readtext(processed, detail=0, paragraph=True,
                                  contrast_ths=0.1, adjust_contrast=0.7)
            return " ".join(res).strip()

        en_text   = _read(self._reader_en)
        en_result = _solve(en_text)
        if (en_result
                and '=' in en_result[0]
                and _re.search(r'[+\-*/]', en_result[0])):
            return en_text

        self._ensure_loaded(log_cb)
        return _read(self._reader)

    def extract_text(self, img_bgr: np.ndarray, log_cb=None) -> str:
        self._ensure_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr)
        results = self._reader.readtext(
            processed, detail=0, paragraph=True,
            contrast_ths=0.1, adjust_contrast=0.7,
        )
        return "\n".join(results).strip()

    def extract_with_boxes(self, img_bgr: np.ndarray, log_cb=None) -> list[tuple]:
        self._ensure_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr, scale=False)
        results = self._reader.readtext(
            processed, detail=1, paragraph=False,
            contrast_ths=0.1, adjust_contrast=0.7,
        )
        return [(r[0], r[1]) for r in results if r[2] >= 0.2]


def _preprocess_for_ocr(img_bgr: np.ndarray, scale: bool = True) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Auto-invert dark backgrounds (chalkboard quiz screens = white text on dark green)
    if np.mean(gray) < 128:
        gray = cv2.bitwise_not(gray)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    gray = clahe.apply(gray)

    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, kernel)
    gray = np.clip(gray, 0, 255).astype(np.uint8)

    if scale:
        h, w = gray.shape
        if h < 100:
            factor = max(2, 100 // h)
            gray = cv2.resize(gray, (w * factor, h * factor),
                              interpolation=cv2.INTER_CUBIC)

    return gray
