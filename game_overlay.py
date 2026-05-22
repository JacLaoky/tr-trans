"""
In-place game overlay using Win32 UpdateLayeredWindow for per-pixel alpha.

Why this approach:
  SetLayeredWindowAttributes / colorkey transparency is unreliable on modern
  Windows because DWM colour-management can silently shift pixel values, so
  the colorkey never matches and the whole window stays pink.

  UpdateLayeredWindow bypasses colorkey entirely.  We hand DWM a 32-bit
  premultiplied-BGRA bitmap; pixels with alpha=0 are fully transparent
  (and click-through because WS_EX_TRANSPARENT is still set), pixels
  with alpha>0 are composited at the hardware level — no colour shifts,
  no GDI interference, no magenta.
"""
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont
from utils import is_windows
import os
import ctypes
from ctypes import wintypes


# ── colours (RGBA) ───────────────────────────────────────────────────────────
_BG_RGBA     = (26,  26,  46,  220)   # dark navy, mostly opaque
_TEXT_RGBA   = (224, 224, 255, 255)   # light blue-white
_BORDER_RGBA = (74,  144, 217, 255)   # accent border


# ── Win32 structs ─────────────────────────────────────────────────────────────
class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          wintypes.DWORD),
        ("biWidth",         wintypes.LONG),
        ("biHeight",        wintypes.LONG),
        ("biPlanes",        wintypes.WORD),
        ("biBitCount",      wintypes.WORD),
        ("biCompression",   wintypes.DWORD),
        ("biSizeImage",     wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed",       wintypes.DWORD),
        ("biClrImportant",  wintypes.DWORD),
    ]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]

class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp",             ctypes.c_ubyte),
        ("BlendFlags",          ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat",         ctypes.c_ubyte),
    ]


# ── helpers ───────────────────────────────────────────────────────────────────
def _find_cjk_font(size: int):
    """
    Find a font that can actually render CJK (Chinese/Korean) characters.
    Korean Windows often lacks Traditional Chinese fonts, so we try Korean
    fonts (Batang/Gulim) which include the full CJK Unified Ideographs block.
    We verify each candidate by measuring a sample CJK character.
    """
    candidates = [
        # Traditional Chinese (ideal)
        r"C:\Windows\Fonts\msjh.ttc",     # Microsoft JhengHei
        r"C:\Windows\Fonts\msjhbd.ttc",
        # Simplified Chinese (covers most CJK)
        r"C:\Windows\Fonts\msyh.ttc",     # Microsoft YaHei
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simsun.ttc",   # SimSun
        r"C:\Windows\Fonts\simhei.ttf",   # SimHei
        # Korean fonts — Batang & Gulim include CJK Unified Ideographs
        r"C:\Windows\Fonts\batang.ttc",   # Batang (Korean serif, has CJK)
        r"C:\Windows\Fonts\gulim.ttc",    # Gulim (Korean sans, has CJK)
        # macOS
        "/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
    ]
    probe_img  = Image.new("RGB", (60, 40))
    probe_draw = ImageDraw.Draw(probe_img)
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                # Verify it can actually render a CJK character
                bb = probe_draw.textbbox((0, 0), "貝", font=font, anchor="lt")
                if bb[2] > bb[0]:          # non-zero width → can render CJK
                    print(f"[overlay] font: {os.path.basename(path)}", flush=True)
                    return font
            except Exception:
                pass
    # Absolute last resort — load_default() can't render CJK but at least won't crash
    print("[overlay] WARNING: no CJK font found, text may be invisible", flush=True)
    return ImageFont.load_default()


def _to_premult_bgra(img: Image.Image) -> bytes:
    """
    Convert an RGBA PIL image to premultiplied BGRA bytes suitable for a
    Win32 32-bpp DIBSection used with UpdateLayeredWindow / AC_SRC_ALPHA.

    Layout per pixel (little-endian in memory):  [B*a, G*a, R*a, A]
    where the R/G/B values are pre-multiplied by (A/255).
    """
    try:
        import numpy as np
        arr   = np.array(img, dtype=np.uint16)     # H×W×4, channels = RGBA
        alpha = arr[:, :, 3:4]                      # keep dims for broadcast
        arr[:, :, :3] = arr[:, :, :3] * alpha // 255   # premultiply RGB
        arr   = arr.astype(np.uint8)
        bgra  = arr[:, :, [2, 1, 0, 3]]            # RGBA → BGRA
        return bgra.tobytes()
    except ImportError:
        # Slow fallback (numpy not available — shouldn't happen)
        data = img.tobytes()
        out  = bytearray(len(data))
        for i in range(0, len(data), 4):
            r, g, b, a = data[i], data[i+1], data[i+2], data[i+3]
            f = a / 255.0
            out[i]   = int(b * f)
            out[i+1] = int(g * f)
            out[i+2] = int(r * f)
            out[i+3] = a
        return bytes(out)


# ── overlay class ─────────────────────────────────────────────────────────────
class GameOverlay:
    def __init__(self):
        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        # Start off-screen (size 1×1) so the window exists but is invisible
        self.win.geometry("1x1+-9999+-9999")
        self.win.update_idletasks()         # ensure HWND is realised

        self._font_cache: dict = {}
        self._last_region: dict | None = None

        if is_windows():
            self._setup_windows()

    def _setup_windows(self):
        hwnd              = self.win.winfo_id()
        GWL_EXSTYLE       = -20
        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020

        u32   = ctypes.windll.user32
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        # !! Do NOT call SetLayeredWindowAttributes !!
        # UpdateLayeredWindow and SetLayeredWindowAttributes are mutually
        # exclusive modes; mixing them causes the window to disappear.

    def _font(self, size: int):
        if size not in self._font_cache:
            self._font_cache[size] = _find_cjk_font(size)
        return self._font_cache[size]

    # ── public API ────────────────────────────────────────────────────────────

    def update(self, translations: list, region: dict):
        gx, gy = region["left"],  region["top"]
        gw, gh = region["width"], region["height"]
        self._last_region = region

        # Fully transparent canvas — only drawn boxes will be visible
        img  = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
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

            tb      = draw.textbbox((0, 0), text, font=font, anchor="lt")
            tw, th  = tb[2] - tb[0], tb[3] - tb[1]
            pad     = 4

            rx1 = cx - tw // 2 - pad
            ry1 = cy - th // 2 - pad
            rx2 = cx + tw // 2 + pad
            ry2 = cy + th // 2 + pad

            draw.rectangle([rx1, ry1, rx2, ry2],
                           fill=_BG_RGBA, outline=_BORDER_RGBA, width=1)
            draw.text((cx, cy), text, fill=_TEXT_RGBA, font=font, anchor="mm")

        if is_windows():
            # Set content + position atomically, then show
            ok = self._ulw(img, gx, gy)
            self.win.deiconify()
            # Diagnostic — shows in the console / run.bat window
            first_box = ""
            for bbox, text in translations:
                if text and not text.startswith("["):
                    x1,y1 = int(bbox[0][0]), int(bbox[0][1])
                    x3,y3 = int(bbox[2][0]), int(bbox[2][1])
                    first_box = f"bbox=({x1},{y1})-({x3},{y3})"
                    break
            print(
                f"[overlay] win=({gx},{gy}) size={gw}x{gh}  "
                f"{first_box}  ulw={'OK' if ok else 'FAIL'}",
                flush=True,
            )
        else:
            self.win.deiconify()
            self._show_fallback(img, gx, gy, gw, gh)

    def clear(self):
        if self._last_region:
            r     = self._last_region
            blank = Image.new("RGBA", (r["width"], r["height"]), (0, 0, 0, 0))
            if is_windows():
                self._ulw(blank, r["left"], r["top"])
            elif hasattr(self, "_canvas"):
                self._canvas.delete("all")
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

    # ── Win32 UpdateLayeredWindow ─────────────────────────────────────────────

    def _ulw(self, img: Image.Image, win_x: int, win_y: int):
        """
        Blit an RGBA PIL image to the layered window.

        UpdateLayeredWindow sets BOTH the visual content and the window's
        screen position/size in one atomic call, bypassing all GDI/DWM
        colour-management that broke the colorkey approach.
        """
        w, h   = img.size
        pixels = _to_premult_bgra(img)

        u32   = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd  = self.win.winfo_id()

        # ── 64-bit-safe signatures ───────────────────────────────────────
        # On 64-bit Windows, HWND/HDC/HBITMAP are 64-bit.  ctypes defaults
        # to c_int (32-bit) for unspecified argtypes, causing an overflow
        # when a 64-bit handle is passed.  Setting argtypes to c_void_p
        # (pointer-sized) fixes this.  Setting them here is idempotent —
        # ctypes caches the function objects, so the cost is paid once.
        u32.GetDC.restype              = ctypes.c_void_p
        u32.GetDC.argtypes             = [ctypes.c_void_p]
        u32.ReleaseDC.restype          = ctypes.c_int
        u32.ReleaseDC.argtypes         = [ctypes.c_void_p, ctypes.c_void_p]
        u32.UpdateLayeredWindow.restype  = ctypes.c_bool
        u32.UpdateLayeredWindow.argtypes = [
            ctypes.c_void_p,               # hwnd
            ctypes.c_void_p,               # hdcDst
            ctypes.POINTER(_POINT),        # pptDst
            ctypes.POINTER(_SIZE),         # psize
            ctypes.c_void_p,               # hdcSrc
            ctypes.POINTER(_POINT),        # pptSrc
            wintypes.DWORD,                # crKey
            ctypes.POINTER(_BLENDFUNCTION),# pblend
            wintypes.DWORD,                # dwFlags
        ]
        gdi32.CreateCompatibleDC.restype  = ctypes.c_void_p
        gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        gdi32.CreateDIBSection.restype    = ctypes.c_void_p
        gdi32.CreateDIBSection.argtypes   = [
            ctypes.c_void_p,               # hdc
            ctypes.POINTER(_BITMAPINFO),   # pbmi
            wintypes.UINT,                 # usage
            ctypes.POINTER(ctypes.c_void_p),  # ppvBits
            ctypes.c_void_p,               # hSection
            wintypes.DWORD,                # offset
        ]
        gdi32.SelectObject.restype    = ctypes.c_void_p
        gdi32.SelectObject.argtypes   = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32.DeleteObject.restype    = ctypes.c_bool
        gdi32.DeleteObject.argtypes   = [ctypes.c_void_p]
        gdi32.DeleteDC.restype        = ctypes.c_bool
        gdi32.DeleteDC.argtypes       = [ctypes.c_void_p]

        hdc_screen = u32.GetDC(None)
        hdc_mem    = gdi32.CreateCompatibleDC(hdc_screen)

        bi = _BITMAPINFO()
        bi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.bmiHeader.biWidth       = w
        bi.bmiHeader.biHeight      = -h    # negative = top-down DIB
        bi.bmiHeader.biPlanes      = 1
        bi.bmiHeader.biBitCount    = 32
        bi.bmiHeader.biCompression = 0     # BI_RGB
        bi.bmiHeader.biSizeImage   = 0

        pBits = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(
            hdc_mem, ctypes.byref(bi),
            0,                              # DIB_RGB_COLORS
            ctypes.byref(pBits), None, 0
        )
        if not hbm:
            gdi32.DeleteDC(hdc_mem)
            u32.ReleaseDC(None, hdc_screen)
            return False

        ctypes.memmove(pBits, pixels, len(pixels))
        old_bm = gdi32.SelectObject(hdc_mem, hbm)

        blend = _BLENDFUNCTION()
        blend.BlendOp             = 0    # AC_SRC_OVER
        blend.BlendFlags          = 0
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat         = 1    # AC_SRC_ALPHA — use per-pixel alpha

        pt_dst = _POINT(win_x, win_y)
        pt_src = _POINT(0, 0)
        sz     = _SIZE(w, h)

        ok = u32.UpdateLayeredWindow(
            hwnd,
            hdc_screen,
            ctypes.byref(pt_dst),   # window screen position
            ctypes.byref(sz),       # window size
            hdc_mem,                # source DC
            ctypes.byref(pt_src),   # source origin
            0,                      # crKey (ignored for ULW_ALPHA)
            ctypes.byref(blend),
            2                       # ULW_ALPHA = 2
        )

        gdi32.SelectObject(hdc_mem, old_bm)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        u32.ReleaseDC(None, hdc_screen)
        return bool(ok)

    # ── macOS / Linux fallback ────────────────────────────────────────────────

    def _show_fallback(self, img_rgba: Image.Image,
                       gx: int, gy: int, gw: int, gh: int):
        """Best-effort colorkey fallback for non-Windows platforms."""
        from PIL import ImageTk
        if not hasattr(self, "_canvas"):
            self.win.configure(bg="#FF00FF")
            self._canvas = tk.Canvas(self.win, bg="#FF00FF",
                                     highlightthickness=0)
            self._canvas.pack(fill=tk.BOTH, expand=True)

        self.win.geometry(f"{gw}x{gh}+{gx}+{gy}")

        # Composite over a magenta background so transparent areas become colorkey
        bg       = Image.new("RGBA", img_rgba.size, (255, 0, 255, 255))
        _, _, _, a = img_rgba.split()
        composed = Image.composite(img_rgba, bg, a).convert("RGB")

        tk_img = ImageTk.PhotoImage(composed)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=tk_img)
        self._img_ref = tk_img
