"""
In-place game overlay using PIL image rendering + Win32 colorkey transparency.
PIL guarantees exact pixel values for the colorkey background, avoiding the
GDI/DWM color-management issues that made tkinter canvas background unreliable.
"""
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from utils import is_windows
import os

_KEY_RGB      = (255, 0, 255)     # exact magenta — transparent colorkey
_KEY_HEX      = "#FF00FF"
_KEY_COLORREF = 0x00FF00FF        # COLORREF: R=0xFF G=0x00 B=0xFF

_BG_RGB    = (26, 26, 46)         # dark navy background behind text
_TEXT_RGB  = (224, 224, 255)      # light blue-white text
_BORDER_RGB = (74, 144, 217)      # accent border


def _find_cjk_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msjh.ttc",     # Microsoft JhengHei (Traditional Chinese)
        r"C:\Windows\Fonts\msjhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",     # Microsoft YaHei
        r"C:\Windows\Fonts\simsun.ttc",
        "/Library/Fonts/PingFang.ttc",    # macOS
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


class GameOverlay:
    def __init__(self):
        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_KEY_HEX)

        self.canvas = tk.Canvas(self.win, bg=_KEY_HEX, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._img_ref = None
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

        self.win.update_idletasks()
        self.win.update()

        if is_windows():
            self._setup_windows()

    def _setup_windows(self):
        import ctypes
        u32 = ctypes.windll.user32
        hwnd = self.win.winfo_id()
        GWL_EXSTYLE      = -20
        WS_EX_LAYERED    = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        LWA_COLORKEY     = 0x00000001

        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        # Bypass tkinter wrapper — call Win32 directly with exact COLORREF
        u32.SetLayeredWindowAttributes(hwnd, _KEY_COLORREF, 0, LWA_COLORKEY)
        self.win.update()

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._font_cache:
            self._font_cache[size] = _find_cjk_font(size)
        return self._font_cache[size]

    def update(self, translations: list[tuple], region: dict):
        gx, gy = region["left"], region["top"]
        gw, gh = region["width"], region["height"]

        self.win.geometry(f"{gw}x{gh}+{gx}+{gy}")
        self.canvas.config(width=gw, height=gh)

        # PIL image — background is EXACT keycolor pixels
        img = Image.new("RGB", (gw, gh), _KEY_RGB)
        draw = ImageDraw.Draw(img)

        for bbox, text in translations:
            if not text or text.startswith("["):
                continue
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x3, y3 = int(bbox[2][0]), int(bbox[2][1])
            box_h  = max(1, y3 - y1)
            cx, cy = (x1 + x3) // 2, (y1 + y3) // 2
            fsize  = max(11, min(22, int(box_h * 0.75)))
            font   = self._font(fsize)

            # Measure rendered text size
            tb = draw.textbbox((0, 0), text, font=font, anchor="lt")
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            pad = 4

            # Dark background tight around text
            rx1 = cx - tw // 2 - pad
            ry1 = cy - th // 2 - pad
            rx2 = cx + tw // 2 + pad
            ry2 = cy + th // 2 + pad
            draw.rectangle([rx1, ry1, rx2, ry2],
                           fill=_BG_RGB, outline=_BORDER_RGB, width=1)

            # Text
            draw.text((cx, cy), text,
                      fill=_TEXT_RGB, font=font, anchor="mm")

        tk_img = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=tk_img)
        self._img_ref = tk_img   # prevent GC

    def clear(self):
        self.canvas.delete("all")
        self._img_ref = None

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
