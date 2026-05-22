"""
In-place game overlay: transparent, click-through window that draws
translated text directly over the original Korean text positions.
"""
import tkinter as tk
from utils import cjk_font, is_windows

_TRANSPARENT = "#FF00FF"  # Magenta as transparent color key


class GameOverlay:
    def __init__(self):
        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_TRANSPARENT)

        self.canvas = tk.Canvas(
            self.win, bg=_TRANSPARENT, highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Force window to be mapped before applying Win32 attributes
        self.win.update_idletasks()
        self.win.update()

        if is_windows():
            self._setup_windows_overlay()
        else:
            # macOS: tkinter's wrapper works fine here
            self.win.attributes("-transparentcolor", _TRANSPARENT)

    def _setup_windows_overlay(self):
        """
        Bypass tkinter's -transparentcolor wrapper (unreliable on some Windows
        configs) and call SetLayeredWindowAttributes directly via ctypes.
        COLORREF for magenta (#FF00FF): R=255 G=0 B=255 → 0x00FF00FF
        """
        import ctypes
        user32 = ctypes.windll.user32

        self.win.update()
        hwnd = self.win.winfo_id()

        GWL_EXSTYLE       = -20
        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        LWA_COLORKEY      = 0x00000001
        MAGENTA_COLORREF  = 0x00FF00FF  # RGB(255, 0, 255) as COLORREF

        # Set LAYERED + TRANSPARENT in one call
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

        # Directly register the transparent color key — no tkinter wrapper
        user32.SetLayeredWindowAttributes(hwnd, MAGENTA_COLORREF, 0, LWA_COLORKEY)
        self.win.update()

    def update(self, translations: list[tuple], region: dict):
        """
        Position the overlay over `region` and draw each translation.
        translations: [(bbox, translated_text), ...]
          bbox = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in region-local coords
        region: {left, top, width, height} — absolute screen coordinates
        """
        gx, gy = region["left"], region["top"]
        gw, gh = region["width"], region["height"]

        self.win.geometry(f"{gw}x{gh}+{gx}+{gy}")
        self.canvas.config(width=gw, height=gh)
        self.canvas.delete("all")

        for bbox, text in translations:
            if not text or text.startswith("["):
                continue
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x3, y3 = int(bbox[2][0]), int(bbox[2][1])
            box_h = max(1, y3 - y1)
            cx    = (x1 + x3) // 2
            cy    = (y1 + y3) // 2
            font_size = max(10, min(20, int(box_h * 0.75)))

            # Draw text first, then fit a tight background box around it
            tid = self.canvas.create_text(
                cx, cy,
                text=text,
                fill="#ffffff",
                font=cjk_font(font_size, bold=True),
                anchor="center",
                width=x3 - x1,
            )
            tb = self.canvas.bbox(tid)   # (x0, y0, x1, y1) of the rendered text
            if tb:
                pad = 3
                bid = self.canvas.create_rectangle(
                    tb[0] - pad, tb[1] - pad, tb[2] + pad, tb[3] + pad,
                    fill="#1a1a2e", outline="#4a90d9", width=1,
                )
                self.canvas.tag_lower(bid, tid)  # background behind text

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
