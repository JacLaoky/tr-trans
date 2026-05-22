import mss
import numpy as np
from PIL import Image


class ScreenCapture:
    def __init__(self):
        self._sct = mss.mss()

    def capture_region(self, region: dict) -> np.ndarray | None:
        """region: {left, top, width, height}"""
        try:
            monitor = {
                "left": region["left"],
                "top": region["top"],
                "width": region["width"],
                "height": region["height"],
            }
            raw = self._sct.grab(monitor)
            img = np.array(raw)
            # mss returns BGRA; drop alpha → BGR
            return img[:, :, :3]
        except Exception:
            return None

    def capture_full_screen(self, monitor_index: int = 1) -> np.ndarray:
        monitor = self._sct.monitors[monitor_index]
        raw = self._sct.grab(monitor)
        return np.array(raw)[:, :, :3]

    def get_monitor_info(self) -> list[dict]:
        return self._sct.monitors[1:]  # skip combined monitor at index 0
