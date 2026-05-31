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

    def _ensure_en_loaded(self, log_cb=None):
        """Lazily load the English OCR model (used for math mode)."""
        if self._reader_en is not None:
            return
        if log_cb:
            log_cb("[OCR] 載入英文模型（算數模式用）...")
        import easyocr
        self._reader_en = easyocr.Reader(["en"], gpu=False, verbose=False)
        if log_cb:
            log_cb("[OCR] 英文模型載入完成。")

    def extract_text_math(self, img_bgr: np.ndarray, log_cb=None) -> str:
        """
        Dual-pass OCR for math equations.

        English model handles +, -, × well (reads operators as ASCII).
        Korean model handles ÷ reliably (reads it as '응', which we substitute).

        Strategy:
          1. Run English model → try math_solve()
          2. If result contains '=' (complete equation) → use it
          3. Otherwise run Korean model → try math_solve()
          4. If Korean gives complete equation → prefer it
          5. Fall back to whichever gave any result
        """
        from math_solver import solve as math_solve

        self._ensure_loaded(log_cb)
        self._ensure_en_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr, scale=True)

        def _read(reader):
            res = reader.readtext(processed, detail=0, paragraph=True,
                                  contrast_ths=0.1, adjust_contrast=0.7)
            return " ".join(res).strip()

        en_text = _read(self._reader_en)
        en_result = math_solve(en_text)
        # English gives a complete match (has '=') → already good
        if en_result and '=' in en_result[0]:
            return en_text

        ko_text = _read(self._reader)
        ko_result = math_solve(ko_text)
        if ko_result and '=' in ko_result[0]:
            return ko_text          # Korean gives complete match (e.g. ÷ → 응 → /)

        # Neither gave a complete equation — return whichever gave any result
        if en_result:
            return en_text
        if ko_result:
            return ko_text
        return en_text              # last resort

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
