"""
視窗選擇器：列出所有開啟的視窗，讓使用者選取遊戲視窗。
"""
import tkinter as tk
from tkinter import messagebox
from utils import cjk_font


def pick_window(parent) -> str | None:
    """顯示視窗列表，回傳選取的視窗標題，或 None。"""
    try:
        import pygetwindow as gw
        all_titles = sorted(set(t.strip() for t in gw.getAllTitles() if t.strip()))
    except Exception as e:
        messagebox.showerror("錯誤", f"無法取得視窗列表：{e}", parent=parent)
        return None

    result = {}

    dlg = tk.Toplevel(parent)
    dlg.title("選擇遊戲視窗")
    dlg.geometry("420x360")
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.configure(bg="#1e1e2e")

    # ── 搜尋框 ──────────────────────────────────────────────────
    search_var = tk.StringVar()
    tk.Label(dlg, text="搜尋視窗名稱：", bg="#1e1e2e", fg="#cdd6f4",
             font=cjk_font(10)).pack(anchor="w", padx=12, pady=(12, 2))
    search_entry = tk.Entry(dlg, textvariable=search_var,
                            bg="#2a2a3e", fg="#cdd6f4", insertbackground="white",
                            relief=tk.FLAT, font=cjk_font(10))
    search_entry.pack(fill=tk.X, padx=12)
    search_entry.focus_set()

    # ── 列表 ────────────────────────────────────────────────────
    frame = tk.Frame(dlg, bg="#1e1e2e")
    frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    listbox = tk.Listbox(
        frame, yscrollcommand=scrollbar.set,
        bg="#2a2a3e", fg="#cdd6f4", selectbackground="#4a90d9",
        relief=tk.FLAT, font=cjk_font(10),
        activestyle="none", borderwidth=0,
    )
    listbox.pack(fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)

    def refresh_list(*_):
        q = search_var.get().lower()
        listbox.delete(0, tk.END)
        for t in all_titles:
            if q in t.lower():
                listbox.insert(tk.END, "  " + t)
        # 自動選取包含 "tales" 的項目
        for i in range(listbox.size()):
            if "tales" in listbox.get(i).lower():
                listbox.selection_set(i)
                listbox.see(i)
                break

    search_var.trace_add("write", refresh_list)
    refresh_list()

    # ── 按鈕 ────────────────────────────────────────────────────
    btn_frame = tk.Frame(dlg, bg="#1e1e2e")
    btn_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

    def on_confirm():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一個視窗。", parent=dlg)
            return
        title = listbox.get(sel[0]).strip()
        result["title"] = title
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    tk.Button(btn_frame, text="確定", command=on_confirm,
              bg="#4a90d9", fg="white", relief=tk.FLAT,
              font=cjk_font(10), padx=16, pady=4, cursor="hand2").pack(side=tk.LEFT)
    tk.Button(btn_frame, text="取消", command=on_cancel,
              bg="#3a3a5e", fg="#cdd6f4", relief=tk.FLAT,
              font=cjk_font(10), padx=16, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=(8, 0))

    listbox.bind("<Double-Button-1>", lambda e: on_confirm())
    dlg.bind("<Return>", lambda e: on_confirm())
    dlg.bind("<Escape>", lambda e: on_cancel())

    parent.wait_window(dlg)
    return result.get("title")
