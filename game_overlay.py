"""
In-place game overlay — pure Win32 layered window, no tkinter.

Root cause of previous failures:
  tkinter Toplevel creates an outer "frame" HWND + an inner "client" HWND.
  winfo_id() returns the INNER HWND.  UpdateLayeredWindow on the inner HWND
  works, but the outer frame HWND is painted on top of it, hiding everything.

Fix: create the overlay window directly with Win32 CreateWindowExW so we
own the HWND and there is no hidden wrapper.
"""
import threading
import os
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw, ImageFont
from utils import is_windows


# ── Colours (RGBA) ────────────────────────────────────────────────────────────
_BG_RGBA     = (26,  26,  46,  220)
_TEXT_RGBA   = (224, 224, 255, 255)
_BORDER_RGBA = (74,  144, 217, 255)


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
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp",             ctypes.c_ubyte),
        ("BlendFlags",          ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat",         ctypes.c_ubyte),
    ]

class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd",    wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam",  wintypes.WPARAM),
        ("lParam",  wintypes.LPARAM),
        ("time",    wintypes.DWORD),
        ("pt",      _POINT),
    ]


# ── Font helpers ──────────────────────────────────────────────────────────────
def _find_cjk_font(size: int):
    candidates = [
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\batang.ttc",
        r"C:\Windows\Fonts\gulim.ttc",
        "/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    probe = ImageDraw.Draw(Image.new("RGB", (60, 40)))
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                bb   = probe.textbbox((0, 0), "貝", font=font, anchor="lt")
                if bb[2] > bb[0]:
                    print(f"[overlay] font: {os.path.basename(path)}", flush=True)
                    return font
            except Exception:
                pass
    print("[overlay] WARNING: no CJK font found", flush=True)
    return ImageFont.load_default()


def _to_premult_bgra(img: Image.Image) -> bytes:
    """RGBA → premultiplied BGRA for Win32 UpdateLayeredWindow."""
    try:
        import numpy as np
        a    = np.array(img, dtype=np.uint16)
        alph = a[:, :, 3:4]
        a[:, :, :3] = a[:, :, :3] * alph // 255
        a    = a.astype(np.uint8)
        return a[:, :, [2, 1, 0, 3]].tobytes()
    except ImportError:
        data = img.tobytes()
        out  = bytearray(len(data))
        for i in range(0, len(data), 4):
            r, g, b, a = data[i], data[i+1], data[i+2], data[i+3]
            f = a / 255.0
            out[i], out[i+1], out[i+2], out[i+3] = int(b*f), int(g*f), int(r*f), a
        return bytes(out)


# ── Overlay ───────────────────────────────────────────────────────────────────
class GameOverlay:
    """
    Transparent click-through overlay using a pure Win32 layered window.

    On Windows: creates a WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
    popup window via ctypes.  UpdateLayeredWindow sets per-pixel RGBA content.

    On non-Windows: no-op (macOS testing uses the panel overlay instead).
    """

    _WIN_CLASS = "TRTransOverlay"
    _cls_registered = False
    _cls_lock       = threading.Lock()

    def __init__(self):
        self._hwnd: int | None = None
        self._font_cache: dict = {}
        self._last_region: dict | None = None
        self._alive  = True
        self._ready  = threading.Event()

        if is_windows():
            t = threading.Thread(target=self._msg_loop, daemon=True)
            t.start()
            ok = self._ready.wait(timeout=5.0)
            if not ok or not self._hwnd:
                print("[overlay] ERROR: window creation timed out", flush=True)

    # ── Win32 window thread ──────────────────────────────────────────────────
    def _msg_loop(self):
        u32   = ctypes.windll.user32
        k32   = ctypes.windll.kernel32
        hInst = k32.GetModuleHandleW(None)

        # Register window class (once per process)
        with GameOverlay._cls_lock:
            if not GameOverlay._cls_registered:
                WNDPROC = ctypes.WINFUNCTYPE(
                    wintypes.LPARAM,
                    wintypes.HWND, wintypes.UINT,
                    wintypes.WPARAM, wintypes.LPARAM,
                )

                class _WNDCLASSEX(ctypes.Structure):
                    _fields_ = [
                        ("cbSize",        wintypes.UINT),
                        ("style",         wintypes.UINT),
                        ("lpfnWndProc",   WNDPROC),
                        ("cbClsExtra",    ctypes.c_int),
                        ("cbWndExtra",    ctypes.c_int),
                        ("hInstance",     wintypes.HMODULE),
                        ("hIcon",         wintypes.HANDLE),
                        ("hCursor",       wintypes.HANDLE),
                        ("hbrBackground", wintypes.HANDLE),
                        ("lpszMenuName",  wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR),
                        ("hIconSm",       wintypes.HANDLE),
                    ]

                @WNDPROC
                def _wnd_proc(hwnd, msg, wParam, lParam):
                    if msg == 0x0002:   # WM_DESTROY
                        u32.PostQuitMessage(0)
                    return u32.DefWindowProcW(hwnd, msg, wParam, lParam)

                self._wndproc_ref = _wnd_proc   # prevent GC

                wc = _WNDCLASSEX()
                wc.cbSize        = ctypes.sizeof(_WNDCLASSEX)
                wc.lpfnWndProc   = _wnd_proc
                wc.hInstance     = hInst
                wc.lpszClassName = GameOverlay._WIN_CLASS
                u32.RegisterClassExW(ctypes.byref(wc))
                GameOverlay._cls_registered = True

        # CreateWindowExW — set return/arg types for 64-bit safety
        u32.CreateWindowExW.restype  = ctypes.c_void_p
        u32.CreateWindowExW.argtypes = [
            wintypes.DWORD,    # dwExStyle
            wintypes.LPCWSTR,  # lpClassName
            wintypes.LPCWSTR,  # lpWindowName
            wintypes.DWORD,    # dwStyle
            ctypes.c_int, ctypes.c_int,   # x, y
            ctypes.c_int, ctypes.c_int,   # nWidth, nHeight
            ctypes.c_void_p,   # hWndParent
            ctypes.c_void_p,   # hMenu
            wintypes.HMODULE,  # hInstance
            ctypes.c_void_p,   # lpParam
        ]

        WS_POPUP          = 0x80000000
        WS_EX_LAYERED     = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOPMOST     = 0x00000008
        WS_EX_TOOLWINDOW  = 0x00000080   # no taskbar entry

        self._hwnd = u32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            GameOverlay._WIN_CLASS,
            "TR Trans Overlay",
            WS_POPUP,
            -9999, -9999, 1, 1,
            None, None, hInst, None,
        )
        print(f"[overlay] HWND={self._hwnd}", flush=True)
        self._ready.set()

        # Pump messages
        msg = _MSG()
        while self._alive:
            ret = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    # ── Font ─────────────────────────────────────────────────────────────────
    def _font(self, size: int):
        if size not in self._font_cache:
            self._font_cache[size] = _find_cjk_font(size)
        return self._font_cache[size]

    # ── Public API ────────────────────────────────────────────────────────────
    def update(self, translations: list, region: dict):
        if not is_windows() or not self._hwnd:
            return

        gx, gy = region["left"],  region["top"]
        gw, gh = region["width"], region["height"]
        self._last_region = region

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
            tb     = draw.textbbox((0, 0), text, font=font, anchor="lt")
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            pad    = 4
            draw.rectangle(
                [cx-tw//2-pad, cy-th//2-pad, cx+tw//2+pad, cy+th//2+pad],
                fill=_BG_RGBA, outline=_BORDER_RGBA, width=1,
            )
            draw.text((cx, cy), text, fill=_TEXT_RGBA, font=font, anchor="mm")

        ok = self._ulw(img, gx, gy)
        print(f"[overlay] win=({gx},{gy}) {gw}x{gh}  ulw={'OK' if ok else 'FAIL'}",
              flush=True)

    def clear(self):
        if not is_windows() or not self._hwnd or not self._last_region:
            return
        r     = self._last_region
        blank = Image.new("RGBA", (r["width"], r["height"]), (0, 0, 0, 0))
        self._ulw(blank, r["left"], r["top"])
        self.hide()

    def show(self):
        if is_windows() and self._hwnd:
            self._swp(0x0001 | 0x0002 | 0x0010 | 0x0040)  # NOSIZE|NOMOVE|NOACTIVATE|SHOW

    def hide(self):
        if is_windows() and self._hwnd:
            u32 = ctypes.windll.user32
            u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
            u32.ShowWindow.restype  = ctypes.c_bool
            u32.ShowWindow(self._hwnd, 0)   # SW_HIDE

    def exists(self) -> bool:
        return bool(self._hwnd) and self._alive

    def destroy(self):
        self._alive = False
        if self._hwnd:
            u32 = ctypes.windll.user32
            u32.PostMessageW.argtypes = [
                ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
            ]
            u32.PostMessageW(self._hwnd, 0x0010, 0, 0)   # WM_CLOSE
            self._hwnd = None

    # ── Internals ─────────────────────────────────────────────────────────────
    def _swp(self, flags: int):
        """SetWindowPos helper — HWND_TOPMOST + given flags."""
        u32 = ctypes.windll.user32
        u32.SetWindowPos.restype  = ctypes.c_bool
        u32.SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]
        u32.SetWindowPos(self._hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, flags)

    def _ulw(self, img: Image.Image, win_x: int, win_y: int) -> bool:
        """Blit a premultiplied-BGRA PIL image via UpdateLayeredWindow."""
        w, h   = img.size
        pixels = _to_premult_bgra(img)

        u32   = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        u32.GetDC.restype              = ctypes.c_void_p
        u32.GetDC.argtypes             = [ctypes.c_void_p]
        u32.ReleaseDC.restype          = ctypes.c_int
        u32.ReleaseDC.argtypes         = [ctypes.c_void_p, ctypes.c_void_p]
        u32.UpdateLayeredWindow.restype  = ctypes.c_bool
        u32.UpdateLayeredWindow.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(_POINT), ctypes.POINTER(_SIZE),
            ctypes.c_void_p, ctypes.POINTER(_POINT),
            wintypes.DWORD, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD,
        ]
        gdi32.CreateCompatibleDC.restype  = ctypes.c_void_p
        gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        gdi32.CreateDIBSection.restype    = ctypes.c_void_p
        gdi32.CreateDIBSection.argtypes   = [
            ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD,
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
        bi.bmiHeader.biSize      = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.bmiHeader.biWidth     = w
        bi.bmiHeader.biHeight    = -h
        bi.bmiHeader.biPlanes    = 1
        bi.bmiHeader.biBitCount  = 32
        bi.bmiHeader.biSizeImage = 0

        pBits = ctypes.c_void_p()
        hbm   = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bi), 0,
                                        ctypes.byref(pBits), None, 0)
        if not hbm:
            gdi32.DeleteDC(hdc_mem)
            u32.ReleaseDC(None, hdc_screen)
            return False

        ctypes.memmove(pBits, pixels, len(pixels))
        old_bm = gdi32.SelectObject(hdc_mem, hbm)

        blend = _BLENDFUNCTION()
        blend.BlendOp             = 0      # AC_SRC_OVER
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat         = 1      # AC_SRC_ALPHA

        pt_dst = _POINT(win_x, win_y)
        pt_src = _POINT(0, 0)
        sz     = _SIZE(w, h)

        ok = u32.UpdateLayeredWindow(
            self._hwnd, hdc_screen,
            ctypes.byref(pt_dst), ctypes.byref(sz),
            hdc_mem, ctypes.byref(pt_src),
            0, ctypes.byref(blend), 2,   # ULW_ALPHA
        )

        gdi32.SelectObject(hdc_mem, old_bm)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        u32.ReleaseDC(None, hdc_screen)

        # Show + re-assert topmost atomically
        self._swp(0x0001 | 0x0002 | 0x0010 | 0x0040)  # NOSIZE|NOMOVE|NOACTIVATE|SHOW

        return bool(ok)
