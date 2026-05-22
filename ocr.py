import cv2
import numpy as np


class OCREngine:
    def __init__(self):
        self._reader = None

    def _ensure_loaded(self, log_cb=None):
        if self._reader is not None:
            return
        if log_cb:
            log_cb("正在載入 OCR 模型（首次需要下載，請稍候）...")
        import easyocr
        self._reader = easyocr.Reader(["ko"], gpu=False, verbose=False)
        if log_cb:
            log_cb("OCR 模型載入完成。")

    def extract_text(self, img_bgr: np.ndarray, log_cb=None) -> str:
        self._ensure_loaded(log_cb)
        processed = self._preprocess(img_bgr)
        results = self._reader.readtext(processed, detail=0, paragraph=True)
        return "\n".join(results).strip()

    @staticmethod
    def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # Upscale small regions for better OCR accuracy
        h, w = gray.shape
        if h < 60:
            scale = max(2, 60 // h)
            gray = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
        # Denoise slightly
        gray = cv2.medianBlur(gray, 3)
        return gray
