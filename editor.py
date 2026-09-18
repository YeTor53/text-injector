# -*- coding: utf-8 -*-
# 文本编辑器组件
# 职责：提供带行号、查找替换、字体字号、自动换行开关的编辑区；
#       只负责"编辑"这件事，文件读写与注入调度由主程序完成。
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

HANZI_START = 0x4E00
HANZI_END = 0x9FFF
INDENT = "    "
MAX_HIGHLIGHT = 4000


def count_hanzi(text):
    n = 0
    for ch in text:
        if HANZI_START <= ord(ch) <= HANZI_END:
            n += 1
    return n


class TextEditor(ttk.Frame):
    def __init__(self, master, font_family="Consolas", font_size=12, wrap=False,
                 on_status=None, on_change=None, **kw):
        ttk.Frame.__init__(self, master, **kw)
        self.on_status = on_status
        self.on_change = on_change
        self._font_obj = tkfont.Font(family=font_family, size=font_size)
        self._case_sensitive = tk.BooleanVar(value=False)
        self._hits = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.linenumbers = tk.Canvas(self, width=52, highlightthickness=0,
                                     background="#f2f2f2", cursor="arrow")
        self.linenumbers.grid(row=0, column=0, sticky="ns")

        self.vsb = ttk.Scrollbar(self, orient="vertical")
        self.hsb = ttk.Scrollbar(self, orient="horizontal")
        self.text = tk.Text(self, undo=True, maxundo=-1, autoseparators=True,
                            wrap="char" if wrap else "none", font=self._font_obj,
                            tabs=(self._font_obj.measure(INDENT),), insertwidth=2,
                            padx=8, pady=4, borderwidth=0, highlightthickness=1,
                            highlightbackground="#d0d0d0")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=1, sticky="ew")
        self.vsb.configure(command=self._yview)
        self.hsb.configure(command=self.text.xview)
        self.text.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self.hsb.set)

        self.text.tag_configure("searchhit", background="#fff2a8")
        self.text.tag_configure("searchcur", background="#ffb347")

        self.text.bind("<KeyRelease>", self._on_key)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<ButtonRelease-1>", self._on_key)
        self.text.bind("<MouseWheel>", self._on_wheel)
        self.text.bind("<Tab>", self._on_tab)
        self.linenumbers.bind("<MouseWheel>", self._on_wheel)
        self.linenumbers.bind("<Button-1>", lambda e: self.text.focus_set())
        self.text.bind("<Configure>", lambda e: self.redraw_linenumbers())

        self._build_searchbar()
        self.redraw_linenumbers()
        self.report_status()

    # ---------------- 状态 ----------------
    def report_status(self):
        if self.on_status is None:
            return
        index = self.text.index("insert")
        line, col = index.split(".")
        content = self.text.get("1.0", "end-1c")
        self.on_status("行 %s 列 %s | 字符 %d | 汉字 %d" % (line, int(col) + 1, len(content), count_hanzi(content)))

    def _on_key(self, event=None):
        self.redraw_linenumbers()
        self.report_status()

    def _on_modified(self, event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.redraw_linenumbers()
            self.report_status()
            if self.on_change is not None:
                self.on_change()

    def _on_wheel(self, event):
        self.text.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.redraw_linenumbers()
        return "break"

    def _on_tab(self, event):
        self.text.insert("insert", INDENT)
        return "break"

    def _yview(self, *args):
        self.text.yview(*args)
        self.redraw_linenumbers()

    def _on_yscroll(self, *args):
        self.vsb.set(*args)
        self.redraw_linenumbers()

    # ---------------- 行号 ----------------
    def redraw_linenumbers(self):
        canvas = self.linenumbers
        canvas.delete("all")
        total = int(self.text.index("end-1c").split(".")[0])
        width = 16 + 8 * len(str(total))
        try:
            current = int(float(canvas.cget("width")))
        except Exception:
            current = 52
        if abs(current - width) >= 4:
            canvas.configure(width=width)

        rows = []
        index = self.text.index("@0,0")
        while True:
            dline = self.text.dlineinfo(index)
            if dline is None:
                break
            rows.append((index.split(".")[0], dline[1], dline[3]))
            index = self.text.index("%s+1line" % index)

        insert_line = self.text.index("insert").split(".")[0]
        for lineno, y, height in rows:
            if lineno == insert_line:
                canvas.create_rectangle(1, y - 1, width - 1, y + height, outline="", fill="#e2e8f0")
        for lineno, y, height in rows:
            canvas.create_text(width - 7, y, anchor="ne", text=lineno,
                               font=self._font_obj, fill="#7a7a7a")

    # ---------------- 字体 / 换行 ----------------
    def set_font(self, family, size):
        self._font_obj.configure(family=family, size=int(size))
        self.text.configure(font=self._font_obj, tabs=(self._font_obj.measure(INDENT),))
        self.redraw_linenumbers()

    def set_wrap(self, enabled):
        self.text.configure(wrap="char" if enabled else "none")
        self.redraw_linenumbers()

    def font_settings(self):
        return self._font_obj.actual("family"), self._font_obj.actual("size")

    # ---------------- 内容 ----------------
    def get_text(self):
        return self.text.get("1.0", "end-1c")

    def set_text(self, content):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.mark_set("insert", "1.0")
        self.text.see("1.0")
        self.clear_highlight()
        self.redraw_linenumbers()
        self.report_status()

    # ---------------- 查找替换 ----------------
    def _build_searchbar(self):
        self.searchbar = ttk.Frame(self)
        self.searchbar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(3, 0))
        ttk.Label(self.searchbar, text="查找").pack(side="left")
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        entry = ttk.Entry(self.searchbar, textvariable=self.find_var, width=22)
        entry.pack(side="left", padx=(4, 6))
        entry.bind("<Return>", lambda e: self.find_next())
        entry.bind("<Escape>", lambda e: self.hide_search())
        ttk.Label(self.searchbar, text="替换为").pack(side="left")
        ttk.Entry(self.searchbar, textvariable=self.replace_var, width=22).pack(side="left", padx=(4, 6))
        ttk.Checkbutton(self.searchbar, text="区分大小写", variable=self._case_sensitive,
                        command=self.highlight_all).pack(side="left")
        ttk.Button(self.searchbar, text="下一个", width=7, command=self.find_next).pack(side="left", padx=2)
        ttk.Button(self.searchbar, text="替换", width=6, command=self.replace_current).pack(side="left", padx=2)
        ttk.Button(self.searchbar, text="全部替换", width=8, command=self.replace_all).pack(side="left", padx=2)
        self.search_info = ttk.Label(self.searchbar, text="")
        self.search_info.pack(side="left", padx=6)
        ttk.Button(self.searchbar, text="关闭", width=6, command=self.hide_search).pack(side="right")
        self.find_var.trace_add("write", lambda *a: self.highlight_all())
        self.searchbar.grid_remove()

    def show_search(self):
        self.searchbar.grid()
        self.searchbar.winfo_children()[1].focus_set()
        self.highlight_all()

    def hide_search(self):
        self.clear_highlight()
        self.searchbar.grid_remove()
        self.text.focus_set()

    def search_visible(self):
        return bool(self.searchbar.winfo_manager())

    def _search_args(self):
        return {"nocase": not self._case_sensitive.get()}

    def highlight_all(self):
        term = self.find_var.get()
        self.clear_highlight()
        if not term:
            self.search_info.configure(text="")
            return
        count = 0
        start = "1.0"
        while count < MAX_HIGHLIGHT:
            pos = self.text.search(term, start, stopindex="end", **self._search_args())
            if not pos:
                break
            end = "%s+%dc" % (pos, len(term))
            self.text.tag_add("searchhit", pos, end)
            self._hits.append((pos, end))
            start = end
            count += 1
        if count >= MAX_HIGHLIGHT:
            self.search_info.configure(text="匹配 %d+ 处" % count)
        elif count:
            self.search_info.configure(text="匹配 %d 处" % count)
        else:
            self.search_info.configure(text="无匹配")

    def clear_highlight(self):
        self.text.tag_remove("searchhit", "1.0", "end")
        self.text.tag_remove("searchcur", "1.0", "end")
        self._hits = []

    def find_next(self):
        term = self.find_var.get()
        if not term:
            return
        self.highlight_all()
        args = self._search_args()
        start = self.text.index("insert")
        pos = self.text.search(term, start, stopindex="end", **args)
        if not pos:
            pos = self.text.search(term, "1.0", stopindex="end", **args)
        if not pos:
            self.search_info.configure(text="无匹配")
            return
        end = "%s+%dc" % (pos, len(term))
        self.text.tag_remove("searchcur", "1.0", "end")
        self.text.tag_add("searchcur", pos, end)
        self.text.mark_set("insert", end)
        self.text.see(pos)
        self.redraw_linenumbers()

    def replace_current(self):
        term = self.find_var.get()
        if not term:
            return
        args = self._search_args()
        pos = self.text.search(term, "insert", stopindex="end", **args)
        if not pos:
            self.find_next()
            return
        end = "%s+%dc" % (pos, len(term))
        self.text.delete(pos, end)
        self.text.insert(pos, self.replace_var.get())
        self.text.see(pos)
        self.highlight_all()
        self.report_status()

    def replace_all(self):
        term = self.find_var.get()
        if not term:
            return
        args = self._search_args()
        count = 0
        start = "1.0"
        while True:
            pos = self.text.search(term, start, stopindex="end", **args)
            if not pos:
                break
            end = "%s+%dc" % (pos, len(term))
            self.text.delete(pos, end)
            self.text.insert(pos, self.replace_var.get())
            start = "%s+%dc" % (pos, len(self.replace_var.get()))
            count += 1
        self.highlight_all()
        self.report_status()
        self.search_info.configure(text="已替换 %d 处" % count)
