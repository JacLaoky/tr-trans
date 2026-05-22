import tkinter as tk
from tkinter import font as tkfont
import sys
from utils import cjk_font


class TranslationOverlay:
    BG = "#1a1a2e"
    TEXT_COLOR = "#e0e0ff"
    ACCENT = "#4a90d9"
    BORDER = "#2a2a4e"

    def __init__(self, config, on_close=None):
        self._config = config
        self._on_close = on_close
        self._visible = True
        self._history: list[str] = []

        self.win = tk.Toplevel()
        self.win.title("TR Trans 翻譯")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", config.get("overlay_alpha"))
        self.win.configure(bg=self.BORDER)

        self._setup_ui()
        self._restore_position()
        self._bind_drag()

    def _setup_ui(self):
        font_size = self._config.get("overlay_font_size")
        width = self._config.get("overlay_width")

        # Title bar
        bar = tk.Frame(self.win, bg=self.ACCENT, height=22)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Label(
            bar, text="  TR Trans", bg=self.ACCENT, fg="white",
            font=cjk_font(9, bold=True), anchor="w"
        ).pack(side=tk.LEFT, fill=tk.Y)

        btn_frame = tk.Frame(bar, bg=self.ACCENT)
        btn_frame.pack(side=tk.RIGHT)

        # Clear button
        self._btn_clear = tk.Button(
            btn_frame, text="清", bg=self.ACCENT, fg="white",
            relief=tk.FLAT, bd=0, font=cjk_font(8),
            cursor="hand2", command=self.clear,
            padx=5, pady=1,
        )
        self._btn_clear.pack(side=tk.LEFT)

        # Close button
        self._btn_close = tk.Button(
            btn_frame, text="×", bg="#c0392b", fg="white",
            relief=tk.FLAT, bd=0, font=("Arial", 11, "bold"),
            cursor="hand2", command=self._close,
            padx=6, pady=0,
        )
        self._btn_close.pack(side=tk.LEFT)

        # Drag handle = title bar
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>", self._drag_move)
        for child in bar.winfo_children():
            if child not in (self._btn_clear, self._btn_close):
                child.bind("<ButtonPress-1>", self._drag_start)
                child.bind("<B1-Motion>", self._drag_move)

        # Text area
        body = tk.Frame(self.win, bg=self.BG, padx=6, pady=4)
        body.pack(fill=tk.BOTH, expand=True)

        self._font = tkfont.Font(family=cjk_font(font_size)[0], size=font_size)
        self._text = tk.Text(
            body,
            bg=self.BG, fg=self.TEXT_COLOR,
            font=self._font,
            relief=tk.FLAT,
            wrap=tk.WORD,
            width=int(width // (font_size * 0.65)),
            height=self._config.get("history_size") + 1,
            state=tk.DISABLED,
            cursor="arrow",
            spacing1=3, spacing3=3,
        )
        self._text.pack(fill=tk.BOTH, expand=True)

        # Resize grip
        grip = tk.Label(self.win, text="⠿", bg=self.BORDER, fg="#555", cursor="size_nw_se")
        grip.pack(anchor="se")
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)

        self._drag_x = 0
        self._drag_y = 0
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_w = 0
        self._resize_h = 0

    def update_text(self, translated: str, original: str = ""):
        if not translated:
            return
        entry = {"tr": translated, "orig": original}
        self._history.append(entry)
        max_h = self._config.get("history_size")
        if len(self._history) > max_h:
            self._history = self._history[-max_h:]
        self._render()

    def _render(self):
        ORIG_COLOR = "#666688"
        DIM   = ["#888899", "#aaaacc", "#ccccee"]

        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)

        for i, entry in enumerate(self._history):
            if i > 0:
                self._text.insert(tk.END, "\n")
            idx = len(self._history) - 1 - i
            tr_color = DIM[min(idx, len(DIM)-1)]
            tr_tag  = f"tr{i}"
            orig_tag = f"orig{i}"
            self._text.tag_configure(tr_tag,   foreground=tr_color)
            self._text.tag_configure(orig_tag, foreground=ORIG_COLOR,
                                     font=(cjk_font(self._font.cget("size") - 2)))

            # Translation line
            self._text.insert(tk.END, entry["tr"], tr_tag)
            # Original line (dim, smaller) — only show if different from translation
            if entry.get("orig") and entry["orig"] != entry["tr"]:
                self._text.insert(tk.END, f"\n  ↑ {entry['orig']}", orig_tag)

        self._text.config(state=tk.DISABLED)
        self._text.see(tk.END)

    def clear(self):
        self._history.clear()
        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.config(state=tk.DISABLED)

    def _close(self):
        self._save_position()
        self.win.destroy()
        if self._on_close:
            self._on_close()

    def _restore_position(self):
        x = self._config.get("overlay_x")
        y = self._config.get("overlay_y")
        w = self._config.get("overlay_width")
        self.win.geometry(f"{w}x200+{x}+{y}")

    def _save_position(self):
        geo = self.win.geometry()  # "WxH+X+Y"
        try:
            size, rest = geo.split("+", 1)
            x, y = rest.split("+")
            self._config.set("overlay_x", int(x))
            self._config.set("overlay_y", int(y))
        except Exception:
            pass

    # --- Drag ---
    def _bind_drag(self):
        pass  # bindings done in _setup_ui

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()

    def _drag_move(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")

    # --- Resize ---
    def _resize_start(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_w = self.win.winfo_width()
        self._resize_h = self.win.winfo_height()

    def _resize_move(self, event):
        dw = event.x_root - self._resize_start_x
        dh = event.y_root - self._resize_start_y
        new_w = max(200, self._resize_w + dw)
        new_h = max(80, self._resize_h + dh)
        self.win.geometry(f"{new_w}x{new_h}")
