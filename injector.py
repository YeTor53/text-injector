# -*- coding: utf-8 -*-
# Windows SendInput 文本注入层
# 职责：把一段文本变成 Windows 输入事件（英文/符号走硬件扫描码，非 ASCII 走 Unicode），
#       并提供四种待注入文本流的生成规则。本模块无 GUI、无第三方依赖，可单独测试。
import ctypes
import random
import threading
import time
from ctypes import POINTER, Structure, Union, cast, wintypes

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MAPVK_VSC_TO_VK_EX = 3

SHIFT_SCANCODE = 0x2A

_user32 = ctypes.windll.user32
_SendInput = _user32.SendInput


class KEYBDINPUT(Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class HARDWAREINPUT(Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


_SendInput.argtypes = (wintypes.UINT, POINTER(INPUT), ctypes.c_int)
_SendInput.restype = wintypes.UINT


# ---------------------------------------------------------------------------
# 扫描码表（US 布局）。值 = (扫描码, 是否需要 Shift)
# 字母/数字的 Shift 变体由 _build_scancodes 自动生成；符号的 Shift 变体必须显式列出。
# ---------------------------------------------------------------------------
_SC_DIGITS = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
}
_SC_LETTERS = {
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16,
    "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24,
    "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
}
_SC_OTHER = {
    "-": 0x0C, "=": 0x0D, "[": 0x1A, "]": 0x1B, ";": 0x27, "'": 0x28,
    "\\": 0x2B, ",": 0x33, ".": 0x34, "/": 0x35, "`": 0x29,
}
# 需要 Shift 的符号 -> 基础键扫描码（原本错位一档的 ^ 与 & 已按 Windows 表修正）
_SC_SHIFTED = {
    "!": 0x02, "@": 0x03, "#": 0x04, "$": 0x05, "%": 0x06, "^": 0x07, "&": 0x08,
    "*": 0x09, "(": 0x0A, ")": 0x0B,
    "_": 0x0C, "+": 0x0D,
    "{": 0x1A, "}": 0x1B, ":": 0x27, '"': 0x28, "|": 0x2B,
    "<": 0x33, ">": 0x34, "?": 0x35, "~": 0x29,
}
_SC_SPECIAL = {" ": 0x39, "\n": 0x1C, "\r": 0x1C, "\t": 0x0F, "\b": 0x0E}


def _build_scancodes():
    table = {}
    for ch, sc in _SC_DIGITS.items():
        table[ch] = (sc, False)
    for ch, sc in _SC_LETTERS.items():
        table[ch] = (sc, False)
        table[ch.upper()] = (sc, True)
    for ch, sc in _SC_OTHER.items():
        table[ch] = (sc, False)
    for ch, sc in _SC_SHIFTED.items():
        table[ch] = (sc, True)
    for ch, sc in _SC_SPECIAL.items():
        table[ch] = (sc, False)
    return table


SCANCODES = _build_scancodes()


def scancode_to_vk(scancode):
    # MAPVK_VSC_TO_VK_EX：区分左右 Shift，其余返回大写字模的虚拟键码
    return _user32.MapVirtualKeyW(scancode, MAPVK_VSC_TO_VK_EX)


def vk_for_char(char):
    # VkKeyScanW：低字节虚拟键码，高字节 shift 状态（bit0=Shift, bit1=Ctrl, bit2=Alt）
    res = _user32.VkKeyScanW(ord(char))
    if res == -1:
        return None
    return res & 0xFF, bool((res >> 8) & 0x01), bool((res >> 8) & 0x02), bool((res >> 8) & 0x04)


# ---------------------------------------------------------------------------
# 事件构造
# ---------------------------------------------------------------------------
def _key_event(scancode, key_up, unicode_code=None):
    ev = INPUT()
    ev.type = INPUT_KEYBOARD
    if unicode_code is None:
        flags = KEYEVENTF_SCANCODE
        if key_up:
            flags |= KEYEVENTF_KEYUP
        ev.union.ki = KEYBDINPUT(0, scancode, flags, 0, 0)
    else:
        flags = KEYEVENTF_UNICODE
        if key_up:
            flags |= KEYEVENTF_KEYUP
        ev.union.ki = KEYBDINPUT(0, unicode_code, flags, 0, 0)
    return ev


def _mouse_event(dx, dy, flags):
    ev = INPUT()
    ev.type = INPUT_MOUSE
    ev.union.mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
    return ev


# ---------------------------------------------------------------------------
# 四种待注入文本流的生成规则
# ---------------------------------------------------------------------------
# 换行处理：同一份文本里的 \r\n / \r / \n 一律当一个换行；换行的按键方式可切换
NEWLINE_ENTER = "enter"
NEWLINE_SHIFT_ENTER = "shift_enter"
NEWLINE_CHAR = "char"

NEWLINE_MODES = [
    (NEWLINE_ENTER, "回车（Enter）"),
    (NEWLINE_SHIFT_ENTER, "Shift+回车"),
    (NEWLINE_CHAR, "换行符（Unicode）"),
]

SC_NEWLINE = 0x1C


def normalize_newlines(text):
    # Windows 文本里常见 \r\n；若不归一化，一次换行会被注入成两次回车
    return text.replace("\r\n", "\n").replace("\r", "\n")


MODE_HYBRID = "hybrid"
MODE_CODE = "code"
MODE_RANDOM = "random"
MODE_RANDOM_LIKE = "random_like"

MODES = [
    (MODE_HYBRID, "混合注入（原样）"),
    (MODE_CODE, "代码模式（压缩空白）"),
    (MODE_RANDOM, "随机汉字（10000 字 + 500 换行）"),
    (MODE_RANDOM_LIKE, "等长乱码（按每行长度）"),
]

RANDOM_CHARS = 10000
RANDOM_NEWLINES = 500
HANZI_START = 0x4E00
HANZI_END = 0x9FFF


def random_hanzi(length, rng=None):
    rng = rng or random
    span = HANZI_END - HANZI_START + 1
    return "".join(chr(HANZI_START + rng.randrange(span)) for _ in range(length))


INDENT_SPACES = "    "


def compact_code(text):
    # 代码模式：制表符展开为 4 空格、行首缩进保留、行内连续空格压成一个、
    # 去掉行尾空白、连续空行压成一个空行、去掉首尾空行。
    lines = []
    for line in text.replace("\t", INDENT_SPACES).split("\n"):
        indent_len = len(line) - len(line.lstrip(" "))
        indent = line[:indent_len]
        body = line[indent_len:]
        out = []
        prev_space = False
        for ch in body:
            if ch == " ":
                if prev_space:
                    continue
                prev_space = True
            else:
                prev_space = False
            out.append(ch)
        lines.append(indent + "".join(out).rstrip())
    result = []
    for line in lines:
        if not line and result and not result[-1]:
            continue
        result.append(line)
    while result and not result[0]:
        result.pop(0)
    while result and not result[-1]:
        result.pop()
    return "\n".join(result)


def build_stream(mode, text, rng=None):
    rng = rng or random
    text = normalize_newlines(text)
    if mode == MODE_CODE:
        return compact_code(text)
    if mode == MODE_RANDOM:
        body = list(random_hanzi(RANDOM_CHARS, rng))
        positions = rng.sample(range(1, len(body)), RANDOM_NEWLINES)
        for pos in sorted(positions, reverse=True):
            body.insert(pos, "\n")
        return "".join(body)
    if mode == MODE_RANDOM_LIKE:
        return "\n".join(random_hanzi(len(line), rng) for line in text.split("\n"))
    return text  # 混合模式：原样注入（换行已在上面归一化）


# ---------------------------------------------------------------------------
# 注入器
# ---------------------------------------------------------------------------
class TextInjector(object):
    # 默认逐字符提交：实测把一批事件一起发（或间隔 0ms）时目标会成片丢字，
    # 逐字符 + 2ms 间隔在 54 字混合文本上 100% 到达。间隔可在界面调，0 = 最快但可能丢字。
    DEFAULT_INTERVAL_MS = 2
    DEFAULT_BATCH_SIZE = 1

    def __init__(self, interval_ms=DEFAULT_INTERVAL_MS, batch_size=DEFAULT_BATCH_SIZE,
                 newline=NEWLINE_ENTER):
        self.interval_ms = int(interval_ms)
        self.batch_size = max(1, int(batch_size))
        self.newline = newline
        self._cancel = threading.Event()
        self.sent = 0
        self.events_sent = 0
        self.events_failed = 0

    def reset(self):
        self._cancel.clear()
        self.sent = 0
        self.events_sent = 0
        self.events_failed = 0

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def _send(self, events):
        if not events:
            return
        n = len(events)
        arr = (INPUT * n)(*events)
        accepted = _SendInput(n, cast(arr, POINTER(INPUT)), ctypes.sizeof(INPUT))
        self.events_sent += accepted
        self.events_failed += max(0, n - accepted)

    def newline_events(self):
        # 换行的三种发法：回车 / Shift+回车（聊天框内换行不发送） / 直接发换行符
        if self.newline == NEWLINE_SHIFT_ENTER:
            return [_key_event(SHIFT_SCANCODE, False), _key_event(SC_NEWLINE, False),
                    _key_event(SC_NEWLINE, True), _key_event(SHIFT_SCANCODE, True)]
        if self.newline == NEWLINE_CHAR:
            return [_key_event(None, False, 0x0A), _key_event(None, True, 0x0A)]
        return [_key_event(SC_NEWLINE, False), _key_event(SC_NEWLINE, True)]

    def char_events(self, char):
        if char == "\n" or char == "\r":
            return self.newline_events()
        # 非 BMP 字符（emoji 等）按 UTF-16 代理对逐个发送
        if ord(char) > 0xFFFF:
            data = char.encode("utf-16-le")
            units = [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]
            events = []
            for unit in units:
                events.append(_key_event(None, False, unit))
                events.append(_key_event(None, True, unit))
            return events

        entry = SCANCODES.get(char) if ord(char) < 128 else None
        if entry is None:
            # 非 ASCII（中文等）或表外字符：走 Unicode 注入
            return [_key_event(None, False, ord(char)), _key_event(None, True, ord(char))]

        scancode, need_shift = entry
        events = []
        if need_shift:
            events.append(_key_event(SHIFT_SCANCODE, False))
        events.append(_key_event(scancode, False))
        events.append(_key_event(scancode, True))
        if need_shift:
            events.append(_key_event(SHIFT_SCANCODE, True))
        return events

    def send_text(self, text, on_progress=None):
        # 返回实际发出的字符数（被中断时 < len(text)）
        self.reset()
        batch = []
        in_batch = 0
        for char in text:
            if self.cancelled:
                break
            batch.extend(self.char_events(char))
            self.sent += 1
            in_batch += 1
            if in_batch >= self.batch_size:
                self._send(batch)
                batch = []
                in_batch = 0
                if on_progress is not None:
                    on_progress(self.sent)
                if self.interval_ms > 0:
                    time.sleep(self.interval_ms * self.batch_size / 1000.0)
        if batch:
            self._send(batch)
            if on_progress is not None:
                on_progress(self.sent)
        return self.sent

    def mouse_click(self, x=None, y=None):
        # 点击指定屏幕坐标（默认当前鼠标位置），用于激活目标输入框
        if x is None or y is None:
            pt = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))
            x, y = pt.x, pt.y
        vx = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        nx = int(round((x - vx) * 65535.0 / max(1, vw - 1)))
        ny = int(round((y - vy) * 65535.0 / max(1, vh - 1)))
        self._send([
            _mouse_event(nx, ny, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
            _mouse_event(0, 0, MOUSEEVENTF_LEFTDOWN),
            _mouse_event(0, 0, MOUSEEVENTF_LEFTUP),
        ])
