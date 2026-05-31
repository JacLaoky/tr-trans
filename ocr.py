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

    def _ensure_math_loaded(self, log_cb=None):
        """Lazily load English-only model for math mode.
        English reads + - × correctly; ÷ becomes '-' but dual-column display
        shows both interpretations so the correct answer is always visible.
        English-only is significantly faster than en+ko combined.
        """
        if self._reader_en is not None:
            return
        if log_cb:
            log_cb("[OCR] 載入算數模型（English）...")
        import easyocr
        self._reader_en = easyocr.Reader(["en"], gpu=False, verbose=False)
        if log_cb:
            log_cb("[OCR] 算數模型載入完成。")

    def extract_text_math(self, img_bgr: np.ndarray, log_cb=None) -> str:
        """
        Smart two-stage OCR for math equations.

        Stage 1 – English model (fast, good for +, -, ×):
          If the parsed result contains '=' AND an arithmetic operator
          → reliable read, return immediately (no Korean needed).

        Stage 2 – Korean model (fallback, only for ÷):
          English reads ÷ as '-' but loses '=' (e.g. '567-0093?').
          If Stage 1 gives no operator or no '=', run Korean model.
          Korean reads ÷ as '응' → substitution table converts it to '/'.

        Net result:
          +  -  ×  → English only  (1 OCR call, fast)
          ÷        → English fails → Korean  (2 calls, slower but accurate)
        """
        import re as _re
        from math_solver import solve as _solve

        self._ensure_math_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr, scale=True)

        def _read(reader):
            res = reader.readtext(processed, detail=0, paragraph=True,
                                  contrast_ths=0.1, adjust_contrast=0.7)
            return " ".join(res).strip()

        en_text   = _read(self._reader_en)
        en_result = _solve(en_text)

        # English gave a complete, parseable equation with an operator → trust it
        if (en_result
                and '=' in en_result[0]
                and _re.search(r'[+\-*/]', en_result[0])):
            return en_text

        # English failed or gave bare number → run Korean for ÷ detection
        self._ensure_loaded(log_cb)
        ko_text = _read(self._reader)
        return ko_text

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
