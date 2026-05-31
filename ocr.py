import cv2
import numpy as np
import sys


def _split_as_division(digits: str) -> str | None:
    """
    Recover 'A/B' when Tesseract merges or misreads the ÷ operator.

    Phase 1 — simple split: try every position, pick first where A÷B is
    a positive integer (prefers positions near the centre).
    Handles: '030006' → '030/006' (÷ invisible)

    Phase 2 — remove one char: if phase 1 fails, try removing each
    internal character (the operator was read as a digit, e.g. ÷→4).
    Handles: '4804008' → remove '4' at pos 3 → '480/008' → 480÷8=60
    """
    n = len(digits)
    if n < 2:
        return None
    mid = n // 2
    order = sorted(range(1, n), key=lambda i: abs(i - mid))

    def _try(left: str, right: str) -> bool:
        a = int(left.lstrip('0') or '0')
        b = int(right.lstrip('0') or '0')
        # Both operands must be ≤ 999 (game equations use small numbers)
        return b > 0 and a > 0 and a % b == 0 and a <= 999 and b <= 999

    # Phase 1: simple split
    for i in order:
        if _try(digits[:i], digits[i:]):
            return f'{digits[:i]}/{digits[i:]}'

    # Phase 2: remove one internal character (operator misread as digit)
    for rm in sorted(range(1, n - 1), key=lambda i: abs(i - mid)):
        left, right = digits[:rm], digits[rm + 1:]
        if left and right and _try(left, right):
            return f'{left}/{right}'

    return None


class OCREngine:
    def __init__(self, config=None):
        self._reader    = None          # Korean model (translation + ÷ detection)
        self._reader_en = None          # English model (math +/-/× detection)
        self._langs     = ["ko"]        # default: Korean only
        self._use_hanzi = False
        self._config    = config        # optional Config for tesseract_path

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
    def _tesseract_available(self) -> bool:
        try:
            import pytesseract
            # Apply user-configured path if set
            path = self._config.get("tesseract_path", "") if self._config else ""
            if path and path.strip():
                pytesseract.pytesseract.tesseract_cmd = path.strip()
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    @staticmethod
    def _gold_mask(img_bgr: np.ndarray) -> np.ndarray:
        """Extract golden/orange game digits via HSV color mask, scaled 3×.
        Use a small 3×3 close kernel so the two dots of '÷' are NOT merged
        into the horizontal bar — keeping them distinct helps Tesseract.
        """
        hsv    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        mask   = cv2.inRange(hsv, np.array([8, 100, 120]), np.array([48, 255, 255]))
        k3     = np.ones((3, 3), np.uint8)
        filled = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3)
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
               r'-c tessedit_char_whitelist=0123456789+\-*/÷x')
        return pytesseract.image_to_string(pil, config=cfg).strip()

    def extract_text_math(self, img_bgr: np.ndarray, log_cb=None) -> str:
        """Tesseract-only math OCR. Returns raw text for math_solver to parse."""
        if not self._tesseract_available():
            if log_cb:
                log_cb("[OCR] 未偵測到 Tesseract，請安裝：\n"
                       "  1. https://github.com/UB-Mannheim/tesseract/wiki\n"
                       "  2. pip install pytesseract")
            return ""
        gold = self._gold_mask(img_bgr)
        text = self._read_with_tesseract(gold)

        # If Tesseract still returns only digits (operator was invisible),
        # try to split the merged string at each position and see which
        # split gives integer division — insert '/' there.
        import re as _re
        if text and _re.fullmatch(r'[\d\s]+', text):
            digits = text.replace(' ', '')
            best = _split_as_division(digits)
            if best:
                text = best

        if log_cb:
            log_cb(f"[OCR] {text!r}")
        return text

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
