"""
In-place game overlay: transparent, click-through window that draws
translated text directly over the original Korean text positions.
"""
import tkinter as tk
from utils import cjk_font, is_windows

# Magenta as transparent color key — unlikely to appear in Tales Runner
_TRANSPARENT = "#FF00FF"


class GameOverlay:
    def __init__(self):
        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_TRANSPARENT)
        self.win.attributes("-transparentcolor", _TRANSPARENT)

        self.canvas = tk.Canvas(
            self.win, bg=_TRANSPARENT, highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        if is_windows():
            self._make_clickthrough()

    def _make_clickthrough(self):
        """Allow mouse clicks to pass through to the game window beneath."""
        import ctypes
        self.win.update_idletasks()
        hwnd = self.win.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_LAYERED = 0x00080000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED
        )

    def update(self, translations: list[tuple], region: dict):
        """
        Position the overlay over `region` and draw each translation.

        translations: [(bbox, translated_text), ...]
          bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in region-local coords
        region: {left, top, width, height} — absolute screen coordinates
        """
        gx, gy = region["left"], region["top"]
        gw, gh = region["width"], region["height"]

        self.win.geometry(f"{gw}x{gh}+{gx}+{gy}")
        self.canvas.config(width=gw, height=gh)
        self.canvas.delete("all")

        for bbox, text in translations:
            if not text:
                continue
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x3, y3 = int(bbox[2][0]), int(bbox[2][1])
            box_h = max(1, y3 - y1)

            # Cover original Korean text
            self.canvas.create_rectangle(
                x1, y1, x3, y3,
                fill="#1a1a2e", outline="#4a90d9", width=1,
            )

            # Draw translated text, scaling font to fit the box height
            font_size = max(9, min(18, int(box_h * 0.72)))
            self.canvas.create_text(
                (x1 + x3) // 2, (y1 + y3) // 2,
                text=text,
                fill="#e0e0ff",
                font=cjk_font(font_size),
                anchor="center",
                width=x3 - x1,  # wrap if needed
            )

    def clear(self):
        self.canvas.delete("all")

    def show(self):
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()

    def exists(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass
