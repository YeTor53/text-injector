# -*- coding: utf-8 -*-
# WebTry 文本注入器 主程序
# 职责：界面装配与调度——配置读写、文件打开/保存、倒计时、后台注入线程、全局热键、进度显示。
# 注入细节在 injector.py，编辑区在 editor.py，热键注册在 hotkey.py。
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import editor as editor_mod
import hotkey as hotkey_mod
import injector as injector_mod

if getattr(sys, "frozen", False):
    # 打包成 exe 后：配置写在 exe 旁边，图标等只读资源来自解包目录
    APP_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = APP_DIR
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
ICON_PATH = os.path.join(RES_DIR, "assets", "icon.ico")
APP_TITLE = "文本注入器"
TEXT_TYPES = [("文本文件", "*.txt"), ("Markdown", "*.md"), ("Python", "*.py"), ("所有文件", "*.*")]

DEFAULT_CONFIG = {
    "mode": injector_mod.MODE_HYBRID,
    "interval_ms": 2,
    "batch_size": 1,
    "newline": injector_mod.NEWLINE_ENTER,
    "countdown_s": 3,
    "click_before": False,
    "wrap": False,
    "font_family": "Consolas",
    "font_size": 12,
    "hotkey_mods": 0,
    "hotkey_vk": 0x78,
    "last_dir": "",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg.update(json.load(fh) or {})
        except Exception:
            pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


class HotkeyDialog(tk.Toplevel):
    # 按键捕获：按什么组合就注册什么，修饰键状态直接问 Win32 要
    def __init__(self, master, mods, vk):
        tk.Toplevel.__init__(self, master)
        self.title("设置全局热键")
        self.resizable(False, False)
        self.transient(master)
        self.result = None
        self._mods = mods
        self._vk = vk
        self.grab_set()

        ttk.Label(self, text="请按下要使用的组合键（可用 Ctrl / Alt / Shift / Win + 任意键）"
                  ).pack(padx=18, pady=(16, 6))
        self.current = ttk.Label(self, text=hotkey_mod.format_hotkey(mods, vk),
                                 font=("Segoe UI", 16, "bold"))
        self.current.pack(pady=6)
        self.capture = ttk.Entry(self, width=28, justify="center")
        self.capture.pack(pady=6)
        self.capture.focus_set()
        self.hint = ttk.Label(self, text="", foreground="#b00")
        self.hint.pack(pady=2)
        ttk.Label(self, text="提示：单独一个键（无修饰键）会被全局独占，建议加 Ctrl / Alt",
                  foreground="#666").pack(pady=(2, 8))

        buttons = ttk.Frame(self)
        buttons.pack(pady=(0, 14))
        ttk.Button(buttons, text="确定", width=10, command=self._ok).pack(side="left", padx=6)
        ttk.Button(buttons, text="取消", width=10, command=self.destroy).pack(side="left", padx=6)

        self.capture.bind("<KeyPress>", self._on_key)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._ok())

    def _on_key(self, event):
        keysym = event.keysym
        if keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                      "Super_L", "Super_R", "Win_L", "Win_R", "Caps_Lock", "Num_Lock"):
            self.hint.configure(text="这只是修饰键，请再按一个主键")
            return "break"
        mods = hotkey_mod.pressed_modifiers()
        vk = hotkey_mod.vk_from_keysym(keysym, event.char)
        if vk is None:
            self.hint.configure(text="无法识别该键：%s" % keysym)
            return "break"
        self._mods, self._vk = mods, vk
        self.current.configure(text=hotkey_mod.format_hotkey(mods, vk))
        self.hint.configure(text="")
        return "break"

    def _ok(self):
        self.result = (self._mods, self._vk)
        self.destroy()


class App(object):
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.injector = injector_mod.TextInjector(
            self.cfg["interval_ms"], self.cfg["batch_size"],
            newline=self.cfg.get("newline", injector_mod.NEWLINE_ENTER))
        self.hotkey = None
        self.events = queue.Queue()
        self.injecting = False
        self.worker = None
        self.countdown_left = 0
        self.countdown_job = None
        self.total_chars = 0
        self.sent_chars = 0
        self.inject_error = None
        self.current_path = None

        self.status_var = tk.StringVar(value="就绪")
        self.pos_var = tk.StringVar(value="")

        root.title(APP_TITLE)
        root.geometry("980x720")
        root.minsize(760, 520)
        self._set_icon()
        self._build_ui()
        self._bind_shortcuts()
        self._register_hotkey(self.cfg["hotkey_mods"], self.cfg["hotkey_vk"], initial=True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._pump)

    # ---------------- 界面 ----------------
    def _set_icon(self):
        if os.path.exists(ICON_PATH):
            try:
                self.root.iconbitmap(ICON_PATH)
            except Exception:
                pass

    def _build_ui(self):
        toolbar = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="模式").pack(side="left")
        self.mode_labels = [label for _, label in injector_mod.MODES]
        self.mode_var = tk.StringVar(value=self._label_for_mode(self.cfg["mode"]))
        self.mode_box = ttk.Combobox(toolbar, textvariable=self.mode_var, values=self.mode_labels,
                                     state="readonly", width=26)
        self.mode_box.pack(side="left", padx=(4, 14))

        ttk.Label(toolbar, text="间隔(ms)").pack(side="left")
        self.interval_var = tk.IntVar(value=int(self.cfg["interval_ms"]))
        ttk.Spinbox(toolbar, from_=0, to=500, increment=1, width=5,
                    textvariable=self.interval_var).pack(side="left", padx=(4, 14))

        ttk.Label(toolbar, text="倒计时(s)").pack(side="left")
        self.countdown_var = tk.IntVar(value=int(self.cfg["countdown_s"]))
        ttk.Spinbox(toolbar, from_=0, to=10, increment=1, width=4,
                    textvariable=self.countdown_var).pack(side="left", padx=(4, 14))

        ttk.Label(toolbar, text="换行").pack(side="left")
        self.newline_labels = [label for _, label in injector_mod.NEWLINE_MODES]
        self.newline_var = tk.StringVar(value=self._label_for_newline(
            self.cfg.get("newline", injector_mod.NEWLINE_ENTER)))
        ttk.Combobox(toolbar, textvariable=self.newline_var, values=self.newline_labels,
                     state="readonly", width=14).pack(side="left", padx=(4, 14))

        self.click_var = tk.BooleanVar(value=bool(self.cfg["click_before"]))
        ttk.Checkbutton(toolbar, text="注入前点击鼠标位置", variable=self.click_var).pack(side="left", padx=(0, 14))

        self.start_button = ttk.Button(toolbar, text="开始注入", width=12, command=self.toggle_inject)
        self.start_button.pack(side="left")
        ttk.Button(toolbar, text="停止", width=8, command=self.stop_inject).pack(side="left", padx=6)

        middle = ttk.Frame(self.root, padding=(10, 4))
        middle.pack(fill="both", expand=True)
        self.editor = editor_mod.TextEditor(
            middle,
            font_family=self.cfg["font_family"],
            font_size=self.cfg["font_size"],
            wrap=bool(self.cfg["wrap"]),
            on_status=self._on_status,
        )
        self.editor.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.root, padding=(10, 4, 10, 8))
        bottom.pack(fill="x")

        ttk.Button(bottom, text="新建", width=7, command=self.new_file).pack(side="left")
        ttk.Button(bottom, text="打开", width=7, command=self.open_file).pack(side="left", padx=4)
        ttk.Button(bottom, text="保存", width=7, command=self.save_file).pack(side="left")

        ttk.Label(bottom, text="字体").pack(side="left", padx=(16, 0))
        families = sorted(set(tkfont.families(self.root)))
        self.font_var = tk.StringVar(value=self.cfg["font_family"])
        font_box = ttk.Combobox(bottom, textvariable=self.font_var, values=families, width=20)
        font_box.pack(side="left", padx=4)
        font_box.bind("<<ComboboxSelected>>", lambda e: self.apply_font())
        self.size_var = tk.IntVar(value=int(self.cfg["font_size"]))
        size_box = ttk.Spinbox(bottom, from_=8, to=36, width=4, textvariable=self.size_var,
                               command=self.apply_font)
        size_box.pack(side="left")
        size_box.bind("<Return>", lambda e: self.apply_font())
        self.wrap_var = tk.BooleanVar(value=bool(self.cfg["wrap"]))
        ttk.Checkbutton(bottom, text="自动换行", variable=self.wrap_var,
                        command=self.apply_wrap).pack(side="left", padx=10)

        ttk.Button(bottom, text="查找/替换", width=11,
                   command=self.editor.show_search).pack(side="left", padx=(6, 0))
        self.hotkey_button = ttk.Button(bottom, text="", width=18, command=self.set_hotkey)
        self.hotkey_button.pack(side="right")
        self._refresh_hotkey_button()

        status = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="determinate", maximum=1000, length=280)
        self.progress.pack(side="left")
        ttk.Label(status, textvariable=self.status_var).pack(side="left", padx=10)
        ttk.Label(status, textvariable=self.pos_var, foreground="#555").pack(side="right")

    def _bind_shortcuts(self):
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-f>", lambda e: self.editor.show_search())
        self.root.bind("<Escape>", lambda e: self.stop_inject())

    # ---------------- 配置 / 状态 ----------------
    def _label_for_mode(self, mode):
        for key, label in injector_mod.MODES:
            if key == mode:
                return label
        return injector_mod.MODES[0][1]

    def _mode_for_label(self, label):
        for key, text in injector_mod.MODES:
            if text == label:
                return key
        return injector_mod.MODE_HYBRID

    def _label_for_newline(self, value):
        for key, label in injector_mod.NEWLINE_MODES:
            if key == value:
                return label
        return injector_mod.NEWLINE_MODES[0][1]

    def _newline_for_label(self, label):
        for key, text in injector_mod.NEWLINE_MODES:
            if text == label:
                return key
        return injector_mod.NEWLINE_ENTER

    def _on_status(self, text):
        self.pos_var.set(text)

    def _refresh_hotkey_button(self):
        self.hotkey_button.configure(
            text="热键: %s（点击修改）" % hotkey_mod.format_hotkey(self.cfg["hotkey_mods"], self.cfg["hotkey_vk"]))

    def collect_config(self):
        return {
            "mode": self._mode_for_label(self.mode_var.get()),
            "interval_ms": int(self.interval_var.get()),
            "batch_size": self.cfg.get("batch_size", 1),
            "newline": self._newline_for_label(self.newline_var.get()),
            "countdown_s": int(self.countdown_var.get()),
            "click_before": bool(self.click_var.get()),
            "wrap": bool(self.wrap_var.get()),
            "font_family": self.font_var.get(),
            "font_size": int(self.size_var.get()),
            "hotkey_mods": int(self.cfg["hotkey_mods"]),
            "hotkey_vk": int(self.cfg["hotkey_vk"]),
            "last_dir": self.cfg.get("last_dir", ""),
        }

    def apply_font(self):
        self.editor.set_font(self.font_var.get(), self.size_var.get())
        self.cfg = self.collect_config()
        save_config(self.cfg)

    def apply_wrap(self):
        self.editor.set_wrap(self.wrap_var.get())
        self.cfg = self.collect_config()
        save_config(self.cfg)

    # ---------------- 文件 ----------------
    def new_file(self):
        if self.editor.get_text().strip() and not messagebox.askyesno(APP_TITLE, "当前内容会丢失，继续新建？"):
            return
        self.editor.set_text("")
        self.current_path = None
        self.root.title(APP_TITLE)
        self.status_var.set("新建")

    def open_file(self):
        path = filedialog.askopenfilename(title="打开文本", filetypes=TEXT_TYPES,
                                          initialdir=self.cfg.get("last_dir") or APP_DIR)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, "打开失败：%s" % exc)
            return
        self.editor.set_text(content)
        self.current_path = path
        self.cfg["last_dir"] = os.path.dirname(path)
        save_config(self.collect_config())
        self.root.title("%s - %s" % (APP_TITLE, os.path.basename(path)))
        self.status_var.set("已打开 %s（%d 字）" % (os.path.basename(path), len(content)))

    def save_file(self):
        content = self.editor.get_text()
        path = self.current_path
        if not path:
            path = filedialog.asksaveasfilename(title="保存文本", defaultextension=".txt",
                                                filetypes=TEXT_TYPES,
                                                initialdir=self.cfg.get("last_dir") or APP_DIR)
            if not path:
                return
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, "保存失败：%s" % exc)
            return
        self.current_path = path
        self.cfg["last_dir"] = os.path.dirname(path)
        save_config(self.collect_config())
        self.root.title("%s - %s" % (APP_TITLE, os.path.basename(path)))
        self.status_var.set("已保存 %s（%d 字）" % (os.path.basename(path), len(content)))

    # ---------------- 热键 ----------------
    def set_hotkey(self):
        dialog = HotkeyDialog(self.root, self.cfg["hotkey_mods"], self.cfg["hotkey_vk"])
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        mods, vk = dialog.result
        old = (self.cfg["hotkey_mods"], self.cfg["hotkey_vk"])
        if not self._register_hotkey(mods, vk):
            self._register_hotkey(old[0], old[1])
            messagebox.showwarning(APP_TITLE, "该组合键注册失败（可能已被其它程序占用），已保留原热键")
            return
        self.cfg["hotkey_mods"] = mods
        self.cfg["hotkey_vk"] = vk
        save_config(self.collect_config())
        self._refresh_hotkey_button()
        self.status_var.set("热键已改为 %s" % hotkey_mod.format_hotkey(mods, vk))

    def _register_hotkey(self, mods, vk, initial=False):
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        hk = hotkey_mod.GlobalHotkey(vk, mods, lambda: self.events.put("toggle"))
        ok = hk.start()
        if ok:
            self.hotkey = hk
        elif not initial:
            self.status_var.set("热键注册失败")
        return ok

    # ---------------- 注入 ----------------
    def toggle_inject(self):
        if self.injecting:
            self.stop_inject()
        elif self.countdown_job is not None:
            self._cancel_countdown()
        else:
            self.start_inject()

    def start_inject(self):
        mode = self._mode_for_label(self.mode_var.get())
        text = self.editor.get_text()
        if mode == injector_mod.MODE_RANDOM:
            pass
        elif not text.strip():
            messagebox.showwarning(APP_TITLE, "请输入要注入的文本")
            return

        self.inject_error = None
        self.total_chars = 0
        self.sent_chars = 0
        self.progress.configure(value=0)
        self.cfg = self.collect_config()
        save_config(self.cfg)

        seconds = int(self.countdown_var.get())
        if seconds > 0:
            self.countdown_left = seconds
            self._tick_countdown()
        else:
            self._launch()

    def _tick_countdown(self):
        if self.countdown_left <= 0:
            self.countdown_job = None
            self._launch()
            return
        self.start_button.configure(text="倒计时 %d" % self.countdown_left)
        self.status_var.set("请把焦点切到目标窗口，%d 秒后开始注入" % self.countdown_left)
        self.countdown_left -= 1
        self.countdown_job = self.root.after(1000, self._tick_countdown)

    def _cancel_countdown(self):
        if self.countdown_job is not None:
            self.root.after_cancel(self.countdown_job)
            self.countdown_job = None
        self.start_button.configure(text="开始注入")
        self.status_var.set("已取消")

    def _launch(self):
        mode = self._mode_for_label(self.mode_var.get())
        text = self.editor.get_text()
        if self.click_var.get():
            x, y = self.root.winfo_pointerxy()
            self.injector.mouse_click(x, y)
        self.injector = injector_mod.TextInjector(
            int(self.interval_var.get()),
            int(self.cfg.get("batch_size", 1)),
            newline=self._newline_for_label(self.newline_var.get()))
        self.injecting = True
        self.start_button.configure(text="注入中…")
        self.status_var.set("正在注入…")

        def work():
            try:
                stream = injector_mod.build_stream(mode, text)
                self.total_chars = len(stream)
                self.injector.send_text(stream, lambda n: setattr(self, "sent_chars", n))
            except Exception as exc:
                self.inject_error = str(exc)
            finally:
                self.events.put("done")

        self.worker = threading.Thread(target=work, name="injector", daemon=True)
        self.worker.start()

    def stop_inject(self):
        if self.countdown_job is not None:
            self._cancel_countdown()
            return
        if self.injecting:
            self.injector.cancel()
            self.status_var.set("正在停止…")

    def _finish_inject(self):
        self.injecting = False
        self.start_button.configure(text="开始注入")
        total = self.total_chars
        sent = self.sent_chars
        if self.inject_error:
            self.status_var.set("注入出错：%s" % self.inject_error)
            messagebox.showwarning(APP_TITLE, "注入出错：%s" % self.inject_error)
            return
        if total and sent >= total:
            self.progress.configure(value=1000)
            self.status_var.set("完成：已注入 %d 字" % sent)
        elif total:
            self.progress.configure(value=int(1000.0 * sent / total))
            self.status_var.set("已停止：注入 %d / %d 字" % (sent, total))
        else:
            self.status_var.set("没有可注入的内容")

    # ---------------- 主循环轮询 ----------------
    def _pump(self):
        try:
            while True:
                msg = self.events.get_nowait()
                if msg == "toggle":
                    self.toggle_inject()
                elif msg == "done":
                    self._finish_inject()
        except queue.Empty:
            pass
        if self.injecting and self.total_chars:
            self.progress.configure(value=int(1000.0 * self.sent_chars / self.total_chars))
            self.status_var.set("正在注入 %d / %d 字" % (self.sent_chars, self.total_chars))
        self.root.after(100, self._pump)

    def on_close(self):
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.injecting:
            self.injector.cancel()
        self.cfg = self.collect_config()
        save_config(self.cfg)
        self.root.destroy()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    if "--selftest" in sys.argv:
        root.withdraw()  # 自检时不显示窗口，避免打断用户
    app = App(root)
    if "--selftest" in sys.argv:
        root.update()
        root.update_idletasks()
        print("selftest ok: 模式 %d 项，编辑区 %s" % (len(injector_mod.MODES), app.editor.text.winfo_exists()))
        if app.hotkey is not None:
            app.hotkey.stop()
        root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
