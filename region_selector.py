"""
Full-screen region selector.
Call select_region() → returns {left, top, width, height} or None.
"""
import tkinter as tk
from PIL import Image, ImageTk
import numpy as np
from utils import cjk_font, is_macos


def select_region(screenshot_bgr: np.ndarray) -> dict | None:
    """Show full-screen selector overlay; user draws a rectangle. Returns region dict or None."""
    import cv2

    h, w = screenshot_bgr.shape[:2]
    rgb = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    result = {}

    root = tk.Toplevel()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.55)
    root.configure(bg="black")
    root.geometry(f"{w}x{h}+0+0")
    root.lift()
    root.focus_force()

    canvas = tk.Canvas(root, cursor="crosshair", bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Show dimmed screenshot
    tk_img = ImageTk.PhotoImage(pil_img)
    canvas.create_image(0, 0, anchor="nw", image=tk_img)
    canvas.image = tk_img  # keep ref

    # Instruction label
    canvas.create_text(
        w // 2, 30, text="拖曳選取要監控的遊戲文字區域  |  按 Esc 取消",
        fill="white", font=cjk_font(14, bold=True),
        tags="hint",
    )

    state = {"x0": 0, "y0": 0, "rect": None, "dragging": False}

    def on_press(event):
        state["x0"] = event.x
        state["y0"] = event.y
        state["dragging"] = True
        if state["rect"]:
            canvas.delete(state["rect"])
            state["rect"] = None

    def on_drag(event):
        if not state["dragging"]:
            return
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            state["x0"], state["y0"], event.x, event.y,
            outline="#4a90d9", width=2, fill="",
        )

    def on_release(event):
        state["dragging"] = False
        x0, y0 = state["x0"], state["y0"]
        x1, y1 = event.x, event.y
        left, top = min(x0, x1), min(y0, y1)
        rw, rh = abs(x1 - x0), abs(y1 - y0)
        if rw > 10 and rh > 10:
            result["region"] = {"left": left, "top": top, "width": rw, "height": rh}
        root.destroy()

    def on_escape(event):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.wait_window()
    return result.get("region")
