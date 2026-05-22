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
        """Plain text extraction (for floating panel mode)."""
        self._ensure_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr)
        results = self._reader.readtext(
            processed, detail=0, paragraph=True,
            contrast_ths=0.1, adjust_contrast=0.7,
        )
        return "\n".join(results).strip()

    def extract_with_boxes(self, img_bgr: np.ndarray, log_cb=None) -> list[tuple]:
        """
        Return [(bbox, text), ...] with bboxes in original image coordinates.
        Uses the original image (not scaled) so bboxes match screen pixels.
        """
        self._ensure_loaded(log_cb)
        processed = _preprocess_for_ocr(img_bgr, scale=False)
        results = self._reader.readtext(
            processed, detail=1, paragraph=False,
            contrast_ths=0.1, adjust_contrast=0.7,
        )
        return [(r[0], r[1]) for r in results if r[2] >= 0.2]


def _preprocess_for_ocr(img_bgr: np.ndarray, scale: bool = True) -> np.ndarray:
    """
    Game text typically has drop shadows and colored outlines on busy backgrounds.
    Strategy: convert to grayscale, enhance contrast, optionally scale up.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # CLAHE: adaptive contrast enhancement — helps with text on gradient backgrounds
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
    gray = clahe.apply(gray)

    # Light sharpening to make glyph edges crisper
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    gray = cv2.filter2D(gray, -1, kernel)
    gray = np.clip(gray, 0, 255).astype(np.uint8)

    # Scale up small images — EasyOCR works best with text ≥ 20px tall
    if scale:
        h, w = gray.shape
        if h < 80:
            factor = max(2, 80 // h)
            gray = cv2.resize(gray, (w * factor, h * factor),
                              interpolation=cv2.INTER_CUBIC)

    return gray
