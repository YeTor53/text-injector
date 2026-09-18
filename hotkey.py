# -*- coding: utf-8 -*-
# 全局热键层（Windows RegisterHotKey）
# 职责：注册/注销全局热键、在自己的消息循环里派发回调、把按键转成 (vk, mods)。
# 本模块不含界面，界面上的"按键捕获"由主程序调用这里提供的工具函数完成。
import ctypes
import threading
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_GetAsyncKeyState = _user32.GetAsyncKeyState

VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "CapsLock",
    0x1B: "Esc", 0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
    0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete", 0x5D: "Menu",
    0x60: "Num0", 0x61: "Num1", 0x62: "Num2", 0x63: "Num3", 0x64: "Num4",
    0x65: "Num5", 0x66: "Num6", 0x67: "Num7", 0x68: "Num8", 0x69: "Num9",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
for _i in range(12):
    VK_NAMES[0x70 + _i] = "F%d" % (_i + 1)
for _i in range(12):
    VK_NAMES[0x7C + _i] = "F%d" % (_i + 13)

_KEYSYM_VK = {
    "Return": 0x0D, "KP_Enter": 0x0D, "Escape": 0x1B, "Tab": 0x09, "BackSpace": 0x08,
    "space": 0x20, "Prior": 0x21, "Next": 0x22, "End": 0x23, "Home": 0x24,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Insert": 0x2D, "Delete": 0x2E,
    "Print": 0x2C, "Pause": 0x13, "Caps_Lock": 0x14, "Num_Lock": 0x90, "Scroll_Lock": 0x91,
    "semicolon": 0xBA, "equal": 0xBB, "comma": 0xBC, "minus": 0xBD, "period": 0xBE,
    "slash": 0xBF, "grave": 0xC0, "bracketleft": 0xDB, "backslash": 0xDC,
    "bracketright": 0xDD, "apostrophe": 0xDE,
    "KP_0": 0x60, "KP_1": 0x61, "KP_2": 0x62, "KP_3": 0x63, "KP_4": 0x64,
    "KP_5": 0x65, "KP_6": 0x66, "KP_7": 0x67, "KP_8": 0x68, "KP_9": 0x69,
    "KP_Multiply": 0x6A, "KP_Add": 0x6B, "KP_Subtract": 0x6D, "KP_Decimal": 0x6E,
    "KP_Divide": 0x6F,
}


def vk_name(vk):
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    return VK_NAMES.get(vk, "VK_%02X" % vk)


def format_hotkey(mods, vk):
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    parts.append(vk_name(vk))
    return "+".join(parts)


def pressed_modifiers():
    # 直接问 Win32 要修饰键状态：比解析 tk 的 event.state 可靠，且能识别 Win 键
    mods = 0
    if _GetAsyncKeyState(VK_CONTROL) & 0x8000:
        mods |= MOD_CONTROL
    if _GetAsyncKeyState(VK_MENU) & 0x8000:
        mods |= MOD_ALT
    if _GetAsyncKeyState(VK_SHIFT) & 0x8000:
        mods |= MOD_SHIFT
    if (_GetAsyncKeyState(VK_LWIN) & 0x8000) or (_GetAsyncKeyState(VK_RWIN) & 0x8000):
        mods |= MOD_WIN
    return mods


def vk_from_keysym(keysym, char=None):
    if keysym in _KEYSYM_VK:
        return _KEYSYM_VK[keysym]
    if len(keysym) == 1:
        if keysym.isalpha():
            return ord(keysym.upper())
        if keysym.isdigit():
            return ord(keysym)
    if len(keysym) >= 2 and keysym[0] == "F" and keysym[1:].isdigit():
        num = int(keysym[1:])
        if 1 <= num <= 24:
            return 0x70 + num - 1
    if char and len(char) == 1:
        res = _user32.VkKeyScanW(ord(char))
        if res != -1:
            return res & 0xFF
    return None


class GlobalHotkey(object):
    # 在本线程外单独起一个线程做 RegisterHotKey + GetMessage 循环，
    # 因此不会和 tkinter 的主循环抢消息，也不会卡界面。
    def __init__(self, vk, mods, callback, hotkey_id=0xB0B1):
        self.vk = int(vk)
        self.mods = int(mods)
        self.callback = callback
        self.hotkey_id = hotkey_id
        self.error = None
        self.tid = None
        self._thread = None
        self._ready = threading.Event()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, timeout=2.0):
        if self.running:
            return True
        self.error = None
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="global-hotkey")
        self._thread.daemon = True
        self._thread.start()
        self._ready.wait(timeout)
        return self.error is None

    def _run(self):
        self.tid = _kernel32.GetCurrentThreadId()
        if not _user32.RegisterHotKey(None, self.hotkey_id, self.mods | MOD_NOREPEAT, self.vk):
            self.error = "注册失败：该组合键可能已被其它程序占用"
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            _user32.UnregisterHotKey(None, self.hotkey_id)

    def stop(self):
        thread = self._thread
        if thread is not None and thread.is_alive():
            if self.tid:
                _user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            thread.join(1.5)
        self._thread = None
        self.tid = None
