import mss
import numpy as np
from PIL import Image


class ScreenCapture:
    def __init__(self):
        self._sct = mss.mss()

    def capture_region(self, region: dict) -> np.ndarray | None:
        """region: {left, top, width, height}"""
        try:
            raw = self._sct.grab({
                "left": region["left"],
                "top": region["top"],
                "width": region["width"],
                "height": region["height"],
            })
            return np.array(raw)[:, :, :3]
        except Exception:
            return None

    def get_window_region(self, title: str) -> dict | None:
        """Return current bounding box of a window by title, or None if not found."""
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(title)
            if not wins:
                return None
            w = wins[0]
            if w.width <= 0 or w.height <= 0:
                return None
            return {"left": w.left, "top": w.top, "width": w.width, "height": w.height}
        except Exception:
            return None

    def capture_window(self, title: str) -> tuple[np.ndarray | None, dict | None]:
        """Capture a window by title. Returns (image, region) or (None, None)."""
        region = self.get_window_region(title)
        if region is None:
            return None, None
        return self.capture_region(region), region

    def capture_full_screen(self, monitor_index: int = 1) -> np.ndarray:
        monitor = self._sct.monitors[monitor_index]
        raw = self._sct.grab(monitor)
        return np.array(raw)[:, :, :3]

    def get_monitor_info(self) -> list[dict]:
        return self._sct.monitors[1:]
