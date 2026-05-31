"""
TR Trans - 韓服 Tales Runner 實時翻譯器
Run: python main.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys

from config import Config
from capture import ScreenCapture
from ocr import OCREngine
from translator import TranslationEngine
from overlay import TranslationOverlay
from game_overlay import GameOverlay
from region_selector import select_region
from window_picker import pick_window
from utils import cjk_font
from math_solver import solve as math_solve


class AnswerPopup:
    """
    Always-on-top window that shows a large math answer.
    • Drag  to reposition (position saved to config automatically).
    • Right-click  to close immediately.
    • Auto-dismisses after timeout.
    """
    W, H = 240, 130

    def __init__(self, root: tk.Tk, config):
        self.root    = root
        self.config  = config
        self._win: tk.Toplevel | None = None
        self._lbl_expr: tk.Label | None = None
        self._lbl_ans:  tk.Label | None = None
        self._job: str | None = None
        # Drag state
        self._drag_sx = self._drag_sy = 0
        self._dragging = False

    # ── internals ─────────────────────────────────────────────────────────────
    def _saved_pos(self) -> tuple[int, int]:
        """Return saved (x, y) or default top-centre."""
        x = self.config.get("answer_popup_x", None)
        y = self.config.get("answer_popup_y", None)
        if x is None or y is None:
            sw = self.root.winfo_screenwidth()
            x  = sw // 2 - self.W // 2
            y  = 8
        return int(x), int(y)

    def _save_pos(self):
        if self._win and self._win.winfo_exists():
            self.config.set("answer_popup_x", self._win.winfo_x())
            self.config.set("answer_popup_y", self._win.winfo_y())

    def _ensure_window(self):
        if self._win and self._win.winfo_exists():
            return
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.attributes('-alpha', 0.93)
        w.configure(bg='#0d0d1a', cursor='fleur')   # move cursor

        # ── drag to reposition ────────────────────────────────────────────────
        def _press(e):
            self._drag_sx = e.x
            self._drag_sy = e.y
            self._dragging = False

        def _drag(e):
            self._dragging = True
            nx = w.winfo_x() + e.x - self._drag_sx
            ny = w.winfo_y() + e.y - self._drag_sy
            w.geometry(f'+{nx}+{ny}')

        def _release(_e):
            if self._dragging:
                self._save_pos()   # persist new position
            self._dragging = False

        w.bind('<ButtonPress-1>',   _press)
        w.bind('<B1-Motion>',       _drag)
        w.bind('<ButtonRelease-1>', _release)
        w.bind('<Button-3>',        lambda _: self.hide())   # right-click = close

        # ── layout ───────────────────────────────────────────────────────────
        border = tk.Frame(w, bg='#4a90d9', padx=2, pady=2)
        border.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(border, bg='#0d0d1a')
        inner.pack(fill=tk.BOTH, expand=True)

        self._lbl_expr = tk.Label(
            inner, text='', bg='#0d0d1a', fg='#89b4fa',
            font=cjk_font(11),
        )
        self._lbl_expr.pack(pady=(6, 0))

        self._lbl_ans = tk.Label(
            inner, text='', bg='#0d0d1a', fg='#f9e2af',
            font=('Arial', 48, 'bold'),
        )
        self._lbl_ans.pack(pady=(0, 6))

        x, y = self._saved_pos()
        w.geometry(f'{self.W}x{self.H}+{x}+{y}')
        self._win = w

    # ── public API ────────────────────────────────────────────────────────────
    def show(self, expression: str, answer: str, timeout_ms: int = 8000):
        self._ensure_window()
        self._lbl_expr.config(text=expression[:32])
        self._lbl_ans.config(text=answer)
        self._win.deiconify()
        self._win.lift()
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(timeout_ms, self.hide)

    def hide(self):
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def destroy(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()


class TRTransApp:
    # UI colors
    BG = "#1e1e2e"
    BG2 = "#2a2a3e"
    FG = "#cdd6f4"
    ACCENT = "#4a90d9"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"

    def __init__(self):
        self.config = Config()
        self.capture = ScreenCapture()
        self.ocr = OCREngine()
        self.translator = TranslationEngine(config=self.config)
        self.overlay: TranslationOverlay | None = None
        self.game_overlay: GameOverlay | None = None

        self.running = False
        self._thread: threading.Thread | None = None
        self._last_text = ""
        self._pending_text = ""
        self._pending_count = 0
        self._no_text_count = 0
        self._last_new_text_time = 0.0   # timestamp of last successful new translation
        self._ocr_ready = False

        self.root = tk.Tk()
        self._mode = tk.StringVar(value=self.config.get("mode", "inplace"))
        self._answer_popup: AnswerPopup | None = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self.root.title("TR Trans - 韓服翻譯器")
        self.root.geometry("480x580")
        self.root.resizable(True, True)
        self.root.minsize(420, 480)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)

        self._apply_styles()

        # ── Header ──────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.ACCENT, height=40)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="  TR Trans  |  Tales Runner 韓服翻譯器",
            bg=self.ACCENT, fg="white",
            font=cjk_font(12, bold=True), anchor="w",
        ).pack(fill=tk.BOTH, expand=True, padx=4)

        content = tk.Frame(self.root, bg=self.BG, padx=12, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # ── Capture source ───────────────────────────────────────────────
        sec1 = self._section(content, "擷取來源")
        self._region_var = tk.StringVar(value="尚未設定")
        tk.Label(
            sec1, textvariable=self._region_var,
            bg=self.BG2, fg=self.YELLOW,
            font=("Consolas", 9), anchor="w", padx=6,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Button(
            sec1, text="選擇視窗", command=self._select_window,
            **self._btn_style(),
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            sec1, text="手動框選", command=self._select_region,
            **self._btn_style(),
        ).pack(side=tk.RIGHT, padx=(6, 0))
        self._restore_region_label()

        # ── Mode ────────────────────────────────────────────────────────
        sec_mode = self._section(content, "翻譯模式")
        for label, value in [
            ("覆蓋原文位置", "inplace"),
            ("浮窗面板",     "panel"),
            ("🔢 算數",      "math"),
        ]:
            tk.Radiobutton(
                sec_mode, text=label, variable=self._mode, value=value,
                bg=self.BG, fg=self.FG, selectcolor=self.BG2,
                activebackground=self.BG, font=cjk_font(10),
                command=self._on_mode_change,
            ).pack(side=tk.LEFT, padx=(0, 12))

        # ── Controls ────────────────────────────────────────────────────
        sec2 = self._section(content, "控制")
        self._start_btn = tk.Button(
            sec2, text="▶  開始翻譯", command=self._toggle,
            **self._btn_style(width=14),
        )
        self._start_btn.pack(side=tk.LEFT)

        self._status_dot = tk.Label(sec2, text="●", fg=self.RED, bg=self.BG, font=("Arial", 14))
        self._status_dot.pack(side=tk.LEFT, padx=8)
        self._status_lbl = tk.Label(sec2, text="停止中", bg=self.BG, fg=self.FG,
                                    font=cjk_font(10))
        self._status_lbl.pack(side=tk.LEFT)

        # ── Translation backend ─────────────────────────────────────────
        sec_tr = self._section(content, "翻譯引擎")
        tr_grid = tk.Frame(sec_tr, bg=self.BG)
        tr_grid.pack(fill=tk.X)

        self._backend_var = tk.StringVar(value=self.config.get("translation_backend", "google"))
        tk.Radiobutton(tr_grid, text="Google Translate（免費）",
                       variable=self._backend_var, value="google",
                       bg=self.BG, fg=self.FG, selectcolor=self.BG2,
                       activebackground=self.BG, font=cjk_font(10),
                       command=self._on_backend_change,
                       ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Radiobutton(tr_grid, text="DeepSeek AI（需要 API Key）",
                       variable=self._backend_var, value="deepseek",
                       bg=self.BG, fg=self.FG, selectcolor=self.BG2,
                       activebackground=self.BG, font=cjk_font(10),
                       command=self._on_backend_change,
                       ).grid(row=1, column=0, columnspan=2, sticky="w")

        tk.Label(tr_grid, text="API Key:", bg=self.BG, fg=self.FG,
                 font=cjk_font(10)).grid(row=2, column=0, sticky="w", pady=(4, 1))
        self._apikey_var = tk.StringVar(value=self.config.get("deepseek_api_key", ""))
        self._apikey_entry = tk.Entry(
            tr_grid, textvariable=self._apikey_var, show="*",
            bg=self.BG2, fg=self.FG, insertbackground="white",
            relief=tk.FLAT, font=("Consolas", 9), width=34,
        )
        self._apikey_entry.grid(row=2, column=1, sticky="w", padx=(6, 0))

        tk.Label(tr_grid, text="模型:", bg=self.BG, fg=self.FG,
                 font=cjk_font(10)).grid(row=3, column=0, sticky="w", pady=(2, 0))
        self._model_var = tk.StringVar(value=self.config.get("deepseek_model", "deepseek-v4-flash"))
        tk.Entry(
            tr_grid, textvariable=self._model_var,
            bg=self.BG2, fg=self.FG, insertbackground="white",
            relief=tk.FLAT, font=("Consolas", 9), width=20,
        ).grid(row=3, column=1, sticky="w", padx=(6, 0))

        self._on_backend_change()  # set initial enabled state

        # ── OCR settings ────────────────────────────────────────────────
        sec_ocr = self._section(content, "OCR 設定")
        self._hanzi_var = tk.BooleanVar(value=self.config.get("ocr_hanzi", False))
        tk.Checkbutton(
            sec_ocr,
            text="啟用漢字識別（ch_sim，首次多下載 ~200MB，適合含漢字題目的遊戲模式）",
            variable=self._hanzi_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, font=cjk_font(9),
        ).pack(anchor="w")

        # ── Settings ────────────────────────────────────────────────────
        sec3 = self._section(content, "其他設定")
        settings_grid = tk.Frame(sec3, bg=self.BG)
        settings_grid.pack(fill=tk.X)

        # Auto-stop
        self._autostop_var = tk.BooleanVar(value=self.config.get("auto_stop", True))
        tk.Checkbutton(
            settings_grid, text="翻譯成功後自動停止（再按「開始翻譯」繼續下一題）",
            variable=self._autostop_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, font=cjk_font(10),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)

        # Capture interval
        tk.Label(settings_grid, text="擷取間隔 (秒):", bg=self.BG, fg=self.FG,
                 font=cjk_font(10)).grid(row=1, column=0, sticky="w", pady=3)
        self._interval_var = tk.DoubleVar(value=self.config.get("capture_interval"))
        interval_spin = tk.Spinbox(
            settings_grid, from_=0.2, to=5.0, increment=0.1,
            textvariable=self._interval_var, width=6,
            bg=self.BG2, fg=self.FG, buttonbackground=self.BG2,
            relief=tk.FLAT, font=("Consolas", 10),
            command=lambda: self.config.set("capture_interval", self._interval_var.get()),
        )
        interval_spin.grid(row=1, column=1, sticky="w", padx=8)

        # Font size
        tk.Label(settings_grid, text="浮窗字體大小:", bg=self.BG, fg=self.FG,
                 font=cjk_font(10)).grid(row=2, column=0, sticky="w", pady=3)
        self._fontsize_var = tk.IntVar(value=self.config.get("overlay_font_size"))
        font_spin = tk.Spinbox(
            settings_grid, from_=10, to=24, increment=1,
            textvariable=self._fontsize_var, width=6,
            bg=self.BG2, fg=self.FG, buttonbackground=self.BG2,
            relief=tk.FLAT, font=("Consolas", 10),
        )
        font_spin.grid(row=2, column=1, sticky="w", padx=8)

        # Overlay opacity
        tk.Label(settings_grid, text="浮窗透明度:", bg=self.BG, fg=self.FG,
                 font=cjk_font(10)).grid(row=3, column=0, sticky="w", pady=3)
        self._alpha_var = tk.DoubleVar(value=self.config.get("overlay_alpha"))
        alpha_scale = tk.Scale(
            settings_grid, from_=0.3, to=1.0, resolution=0.05,
            variable=self._alpha_var, orient=tk.HORIZONTAL, length=120,
            bg=self.BG, fg=self.FG, troughcolor=self.BG2,
            highlightthickness=0, relief=tk.FLAT,
        )
        alpha_scale.grid(row=3, column=1, sticky="w", padx=8)

        btn_row = tk.Frame(sec3, bg=self.BG)
        btn_row.pack(pady=(8, 0), fill=tk.X)
        tk.Button(
            btn_row, text="套用設定", command=self._apply_settings,
            **self._btn_style(),
        ).pack(side=tk.LEFT)
        tk.Button(
            btn_row, text="測試翻譯", command=self._test_translation,
            **self._btn_style(),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ── Log ─────────────────────────────────────────────────────────
        log_frame = tk.LabelFrame(
            content, text=" 日誌 ",
            bg=self.BG, fg=self.ACCENT,
            font=cjk_font(9),
            labelanchor="nw", bd=1, relief=tk.SOLID,
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self._log_text = tk.Text(
            log_frame, height=7, bg=self.BG2, fg=self.FG,
            font=("Consolas", 9), relief=tk.FLAT,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        sb = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._log("就緒。請選擇「視窗」或「手動框選」，再按「開始翻譯」。")

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _select_window(self):
        if self.running:
            messagebox.showwarning("提示", "請先停止翻譯再重新選擇。")
            return
        title = pick_window(self.root)
        if title:
            self.config.set("window_title", title)
            self.config.set("capture_region", None)
            self._region_var.set(f"視窗：{title}")
            self._log(f"已選取視窗：{title}")

    def _select_region(self):
        if self.running:
            messagebox.showwarning("提示", "請先停止翻譯再重新選擇。")
            return
        self._log("正在截圖，請切換到遊戲視窗...")
        self.root.after(300, self._do_select_region)

    def _do_select_region(self):
        self.root.withdraw()
        time.sleep(0.3)
        try:
            full = self.capture.capture_full_screen()
            region = select_region(full)
            if region:
                self.config.set("capture_region", region)
                self.config.set("window_title", None)
                self._region_var.set(
                    f"左:{region['left']}  上:{region['top']}  "
                    f"寬:{region['width']}  高:{region['height']}"
                )
                self._log(f"區域已設定: {region}")
            else:
                self._log("已取消選取區域。")
        except Exception as e:
            self._log(f"選取失敗: {e}")
        finally:
            self.root.deiconify()

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _on_mode_change(self):
        self.config.set("mode", self._mode.get())
        if self.running:
            self._stop()

    def _start(self):
        if not self.config.get("window_title") and not self.config.get("capture_region"):
            messagebox.showwarning("提示", "請先選擇視窗或手動框選擷取區域。")
            return

        mode = self._mode.get()
        if mode == "inplace":
            if self.game_overlay is None or not self.game_overlay.exists():
                self.game_overlay = GameOverlay()
            if self.overlay and self.overlay.win.winfo_exists():
                self.overlay.win.withdraw()
        elif mode == "panel":
            if self.overlay is None or not self.overlay.win.winfo_exists():
                self.overlay = TranslationOverlay(self.config, on_close=self._on_overlay_close)
            if self.game_overlay and self.game_overlay.exists():
                self.game_overlay.hide()
        else:   # math mode
            # Ensure the answer popup exists (created lazily in _process_math)
            if self.overlay and self.overlay.win.winfo_exists():
                self.overlay.win.withdraw()
            if self.game_overlay and self.game_overlay.exists():
                self.game_overlay.hide()

        # Apply current OCR hanzi setting before starting
        self.ocr.set_hanzi(self.config.get("ocr_hanzi", False))
        # Pre-load English model in background when math mode is selected
        if mode == "math":
            threading.Thread(
                target=lambda: self.ocr._ensure_en_loaded(self._log_threadsafe),
                daemon=True,
            ).start()

        self.running = True
        self._set_status(True)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        mode_labels = {"inplace": "覆蓋模式", "panel": "浮窗模式", "math": "算數模式"}
        self._log(f"開始（{mode_labels.get(mode, mode)}）...")

    def _stop(self):
        self.running = False
        self._set_status(False)
        if self.game_overlay and self.game_overlay.exists():
            self.root.after(0, self.game_overlay.clear)
        self._log("已停止。")

    def _on_overlay_close(self):
        self._stop()
        self.overlay = None

    def _on_backend_change(self):
        is_deepseek = self._backend_var.get() == "deepseek"
        state = tk.NORMAL if is_deepseek else tk.DISABLED
        self._apikey_entry.config(state=state)

    def _apply_settings(self):
        self.config.set("overlay_font_size", self._fontsize_var.get())
        self.config.set("overlay_alpha", self._alpha_var.get())
        self.config.set("capture_interval", self._interval_var.get())
        backend = self._backend_var.get()
        api_key = self._apikey_var.get().strip()
        model   = self._model_var.get().strip() or "deepseek-v4-flash"
        self.config.set("auto_stop", self._autostop_var.get())
        self.config.set("translation_backend", backend)
        self.config.set("deepseek_api_key", api_key)
        self.config.set("deepseek_model", model)
        self._log(f"[設定] 引擎={backend}  Key={'已填' if api_key else '空白'}  模型={model}")
        hanzi = self._hanzi_var.get()
        self.config.set("ocr_hanzi", hanzi)
        self.ocr.set_hanzi(hanzi)
        if not hanzi:
            self._ocr_ready = False  # reload without ch_sim next start
        self.translator.update_config(self.config)
        if self.overlay and self.overlay.win.winfo_exists():
            self.overlay.win.attributes("-alpha", self._alpha_var.get())
        self._log("設定已套用。")

    def _test_translation(self):
        self._log("測試翻譯中：「안녕하세요」→ ...")
        def _do():
            try:
                result = self.translator.translate("안녕하세요")
                self._log_threadsafe(f"翻譯成功：「{result}」（網路正常）")
            except Exception as e:
                self._log_threadsafe(f"翻譯失敗：{e}（請確認網路連線）")
        threading.Thread(target=_do, daemon=True).start()

    def _on_quit(self):
        self.running = False
        if self.overlay and self.overlay.win.winfo_exists():
            self.overlay.win.destroy()
        if self.game_overlay and self.game_overlay.exists():
            self.game_overlay.destroy()
        if self._answer_popup:
            self._answer_popup.destroy()
        self.root.destroy()

    # ------------------------------------------------------------------ #
    # Translation loop                                                     #
    # ------------------------------------------------------------------ #

    def _loop(self):
        if not self._ocr_ready:
            self.ocr._ensure_loaded(log_cb=self._log_threadsafe)
            self._ocr_ready = True

        self._log_threadsafe("OCR 就緒，開始擷取...")

        while self.running:
            try:
                win_title = self.config.get("window_title")
                if win_title:
                    img, region = self.capture.capture_window(win_title)
                    if img is None:
                        self._log_threadsafe(f"找不到視窗「{win_title}」，請確認遊戲已開啟。")
                        time.sleep(2)
                        continue
                else:
                    region = self.config.get("capture_region")
                    if not region:
                        time.sleep(0.5)
                        continue
                    img = self.capture.capture_region(region)
                    if img is None:
                        self._log_threadsafe("截圖失敗，重試中...")
                        time.sleep(0.2)
                        continue

                mode = self._mode.get()
                if mode == "inplace":
                    self._process_inplace(img, region)
                elif mode == "math":
                    self._process_math(img)
                else:
                    self._process_panel(img)


            except Exception as e:
                import traceback
                self._log_threadsafe(f"錯誤: {e}\n{traceback.format_exc()[-300:]}")

            time.sleep(self.config.get("capture_interval"))

    def _process_inplace(self, img, region):
        """OCR with bboxes → stability check → batch translate → update overlay."""
        items = self.ocr.extract_with_boxes(img)

        if not items:
            self._no_text_count += 1
            self._pending_count = 0
            # Log the first empty frame, then every 5th, so user can see loop is alive
            if self._no_text_count == 1 or self._no_text_count % 5 == 0:
                self._log_threadsafe(f"[擷取] 未偵測到文字（第 {self._no_text_count} 幀）")
            # Clear overlay only after 3 consecutive empty frames (avoids flicker)
            if self._no_text_count >= 3 and self.game_overlay and self.game_overlay.exists():
                self.root.after(0, self.game_overlay.clear)
            return

        self._no_text_count = 0
        flat = " ".join(t for _, t in items)
        self._log_threadsafe(f"[OCR原] ({len(items)}項) {flat[:80]}{'…' if len(flat)>80 else ''}")

        # Stability gate: disabled for auto-stop mode (user presses start each time,
        # so the first detected frame is already intentional).
        # For continuous mode, require 2 identical consecutive frames.
        threshold = 1 if self.config.get("auto_stop", True) else 2

        if flat == self._pending_text:
            self._pending_count += 1
        else:
            self._pending_text = flat
            self._pending_count = 1

        if self._pending_count < threshold:
            self._log_threadsafe(f"[穩定門] {self._pending_count}/{threshold}，等待下一幀…")
            return

        if flat == self._last_text:
            self._log_threadsafe("[穩定門] 與上次相同，跳過。")
            return  # already translated this exact content

        self._last_text = flat
        self._last_new_text_time = time.time()
        self._log_threadsafe(f"[OCR] {flat[:60]}{'…' if len(flat) > 60 else ''}")

        # Batch translate all bboxes in one API call
        bboxes = [bbox for bbox, _ in items]
        texts  = [text for _, text in items]
        translated = self.translator.translate_batch(texts, log_cb=self._log_threadsafe)
        translated_items = list(zip(bboxes, translated))

        if self.game_overlay and self.game_overlay.exists():
            self.root.after(
                0, lambda ti=translated_items, r=region:
                self.game_overlay.update(ti, r)
            )
        self._log_threadsafe(f"[翻] {translated[0][:60]}{'…' if len(translated[0]) > 60 else ''}")
        if self.config.get("auto_stop", True):
            self.root.after(0, self._stop)

    def _process_panel(self, img):
        """Plain OCR → stability check → translate → update floating panel."""
        text = self.ocr.extract_text(img).strip()
        if not text:
            self._no_text_count += 1
            if self._no_text_count == 1 or self._no_text_count % 5 == 0:
                self._log_threadsafe(f"[擷取] 未偵測到文字（第 {self._no_text_count} 幀）")
            return

        self._no_text_count = 0
        self._log_threadsafe(f"[OCR原] {text[:80]}{'…' if len(text)>80 else ''}")
        threshold = 1 if self.config.get("auto_stop", True) else 2

        if text == self._pending_text:
            self._pending_count += 1
        else:
            self._pending_text = text
            self._pending_count = 1

        if self._pending_count < threshold or text == self._last_text:
            return

        self._last_text = text
        self._last_new_text_time = time.time()
        self._log_threadsafe(f"[OCR] {text[:60]}{'…' if len(text) > 60 else ''}")

        translated = self.translator.translate_batch([text], log_cb=self._log_threadsafe)[0]
        if translated and self.overlay:
            self.overlay.win.after(0, lambda t=translated, o=text: self.overlay.update_text(t, o))
            self._log_threadsafe(f"[翻] {translated[:60]}{'…' if len(translated) > 60 else ''}")
        if self.config.get("auto_stop", True):
            self.root.after(0, self._stop)

    def _process_math(self, img):
        """OCR → arithmetic detection → show answer in popup.
        Math mode always runs continuously (ignores auto_stop).
        Falls back to plain translation display if no math is found.
        """
        text = self.ocr.extract_text_math(img, log_cb=self._log_threadsafe).strip()
        if not text:
            self._no_text_count += 1
            if self._no_text_count == 1 or self._no_text_count % 5 == 0:
                self._log_threadsafe(
                    f"[擷取] 未偵測到文字（第 {self._no_text_count} 幀）")
            # Reset last_text between rounds so the same equation can be
            # shown again if it reappears in the next round.
            if self._no_text_count >= 3:
                self._last_text = ""
            return

        self._no_text_count = 0

        # No stability gate in math mode — respond on the first clean frame.
        if text == self._last_text:
            return                       # already showing this equation

        self._last_text = text
        self._log_threadsafe(
            f"[OCR] {text[:80]}{'…' if len(text) > 80 else ''}")

        # ── Try math first ────────────────────────────────────────────────────
        result = math_solve(text)
        if result:
            expr, answer = result
            self._log_threadsafe(f"[算數] {expr}  →  答案: {answer}")
            if self._answer_popup is None:
                self._answer_popup = AnswerPopup(self.root, self.config)
            expr_pretty = expr.replace('*', '×').replace('/', '÷')
            self.root.after(
                0, lambda e=expr_pretty, a=answer: self._answer_popup.show(e, a))
            return   # keep running — no auto_stop in math mode

        # ── No math: log the translation but don't stop ───────────────────────
        self._log_threadsafe("[算數] 未偵測到算式 → 嘗試翻譯...")
        translated = self.translator.translate_batch(
            [text], log_cb=self._log_threadsafe)[0]
        self._log_threadsafe(
            f"[翻] {translated[:60]}{'…' if len(translated) > 60 else ''}")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _set_status(self, active: bool):
        if active:
            self._status_dot.config(fg=self.GREEN)
            self._status_lbl.config(text="翻譯中...")
            self._start_btn.config(text="■  停止")
        else:
            self._status_dot.config(fg=self.RED)
            self._status_lbl.config(text="停止中")
            self._start_btn.config(text="▶  開始翻譯")

    def _log(self, msg: str):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, msg + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _log_threadsafe(self, msg: str):
        self.root.after(0, lambda: self._log(msg))

    def _restore_region_label(self):
        t = self.config.get("window_title")
        if t:
            self._region_var.set(f"視窗：{t}")
            return
        r = self.config.get("capture_region")
        if r:
            self._region_var.set(
                f"左:{r['left']}  上:{r['top']}  寬:{r['width']}  高:{r['height']}"
            )

    def _section(self, parent, title: str) -> tk.Frame:
        tk.Label(
            parent, text=title, bg=self.BG, fg=self.ACCENT,
            font=cjk_font(10, bold=True),
        ).pack(anchor="w", pady=(8, 2))
        f = tk.Frame(parent, bg=self.BG)
        f.pack(fill=tk.X)
        return f

    def _btn_style(self, width: int = 10) -> dict:
        return dict(
            bg=self.ACCENT, fg="white", relief=tk.FLAT,
            font=cjk_font(10), cursor="hand2",
            padx=8, pady=4, width=width,
            activebackground="#357abd", activeforeground="white",
        )

    def _apply_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background=self.BG2, troughcolor=self.BG, borderwidth=0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = TRTransApp()
    app.run()
