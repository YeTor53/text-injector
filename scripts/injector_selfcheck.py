# -*- coding: utf-8 -*-
# 离线自检：不注入任何按键，只校验逻辑与结构
# 跑法：python scripts/injector_selfcheck.py
import ctypes
import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hotkey as hotkey_mod
import injector as injector_mod

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append("%s %s" % (name, detail))
        print("FAIL %s %s" % (name, detail))


def norm_vk(vk):
    # MapVirtualKey 返回大写字母的虚拟键码，VkKeyScan 返回小写，比较前归一
    if 0x61 <= vk <= 0x7A:
        return vk - 0x20
    return vk


print("== 1. 扫描码表 vs Windows 键表（95 个可打印 ASCII） ==")
printable = string.printable
chars = [c for c in printable if c in string.ascii_letters + string.digits + string.punctuation + " "]
check("可打印 ASCII 数量", len(chars) == 95, "got %d" % len(chars))
for ch in chars:
    entry = injector_mod.SCANCODES.get(ch)
    if entry is None:
        check("字符在表中", False, repr(ch))
        continue
    scancode, need_shift = entry
    res = injector_mod._user32.VkKeyScanW(ord(ch))
    exp_vk = res & 0xFF
    exp_shift = bool((res >> 8) & 0x01)
    exp_ctrl = bool((res >> 8) & 0x02)
    exp_alt = bool((res >> 8) & 0x04)
    our_vk = injector_mod.scancode_to_vk(scancode)
    check("虚拟键一致 %r" % ch, norm_vk(our_vk) == norm_vk(exp_vk),
          "ours=0x%02X win=0x%02X" % (our_vk, exp_vk))
    check("Shift 状态一致 %r" % ch, need_shift == exp_shift,
          "ours=%s win=%s" % (need_shift, exp_shift))
    check("不需要 Ctrl/Alt %r" % ch, (not exp_ctrl) and (not exp_alt))

print("== 2. 曾错位的符号（原版把 ^ 与 & 各差一档） ==")
for ch, expect in (("^", 0x08), ("&", 0x09), ("%", 0x07), ("(", 0x0A), (")", 0x0B), ("*", 0x09)):
    pass
for ch, expect_sc in (("^", 0x07), ("&", 0x08), ("%", 0x06), ("$", 0x05), ("(", 0x0A), (")", 0x0B), ("*", 0x09)):
    got = injector_mod.SCANCODES[ch]
    check("符号 %s 扫描码" % ch, got == (expect_sc, True), "got %s" % (got,))

print("== 3. 事件结构 ==")
check("sizeof(INPUT) == 40", ctypes.sizeof(injector_mod.INPUT) == 40)
ev = injector_mod.TextInjector().char_events("a")
check("小写字母 2 个事件", len(ev) == 2, "got %d" % len(ev))
check("小写字母走扫描码", ev[0].union.ki.dwFlags == injector_mod.KEYEVENTF_SCANCODE,
      "flags=0x%X" % ev[0].union.ki.dwFlags)
check("小写字母 wVk 为 0", ev[0].union.ki.wVk == 0)
check("第二事件是抬起", ev[1].union.ki.dwFlags == (injector_mod.KEYEVENTF_SCANCODE | injector_mod.KEYEVENTF_KEYUP))
ev = injector_mod.TextInjector().char_events("A")
check("大写字母 4 个事件（含 Shift 按下/抬起）", len(ev) == 4, "got %d" % len(ev))
check("Shift 先按下", ev[0].union.ki.wScan == injector_mod.SHIFT_SCANCODE and not (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_KEYUP))
check("Shift 最后抬起", ev[3].union.ki.wScan == injector_mod.SHIFT_SCANCODE and bool(ev[3].union.ki.dwFlags & injector_mod.KEYEVENTF_KEYUP))
ev = injector_mod.TextInjector().char_events("中")
check("中文走 Unicode 注入", len(ev) == 2 and (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_UNICODE))
check("中文 wScan == 0x4E2D", ev[0].union.ki.wScan == 0x4E2D, "got 0x%X" % ev[0].union.ki.wScan)
ev = injector_mod.TextInjector().char_events("\n")
check("换行走回车扫描码", ev[0].union.ki.wScan == 0x1C and (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_SCANCODE))
ev = injector_mod.TextInjector().char_events("\U0001F600")
check("emoji 按代理对发 4 个事件", len(ev) == 4, "got %d" % len(ev))

print("== 4. 四种模式的文本流 ==")
check("hybrid 原样返回", injector_mod.build_stream("hybrid", "abc\n中文") == "abc\n中文")
code_in = "\tfoo    bar  \n\n\nbaz   "
code_out = injector_mod.build_stream("code", code_in)
check("code 模式：Tab 展开为 4 空格并压空白", code_out == "    foo bar\n\nbaz", repr(code_out))
check("code 模式：保留行首缩进", injector_mod.build_stream("code", "        x = 1") == "        x = 1")
check("code 模式：去掉行尾空白", injector_mod.build_stream("code", "a   \n") == "a")
check("code 模式：连续空行压成一个",
      injector_mod.build_stream("code", "a\n\n\n\nb") == "a\n\nb")
rng = random.Random(42)
stream = injector_mod.build_stream("random", "", rng)
check("random 长度 = 10000 + 500 换行", len(stream) == 10500, "got %d" % len(stream))
check("random 换行个数 = 500", stream.count("\n") == 500, "got %d" % stream.count("\n"))
bad = [c for c in stream if c != "\n" and not (0x4E00 <= ord(c) <= 0x9FFF)]
check("random 非换行字符全为汉字", not bad, "got %r" % bad[:5])
rng = random.Random(7)
like = injector_mod.build_stream("random_like", "abc\n中文行\n\nzz", rng)
lines = like.split("\n")
check("random_like 行数不变", len(lines) == 4, "got %d" % len(lines))
check("random_like 每行等长", [len(x) for x in lines] == [3, 3, 0, 2], "%s" % [len(x) for x in lines])
check("random_like 内容全为汉字",
      all(c == "\n" or 0x4E00 <= ord(c) <= 0x9FFF for c in like))

print("== 4b. 换行处理 ==")
inj = injector_mod.TextInjector()
check("CRLF 只当一个换行", injector_mod.normalize_newlines("a\r\nb") == "a\nb")
check("孤立 CR 也当一个换行", injector_mod.normalize_newlines("a\rb") == "a\nb")
check("混合换行归一化", injector_mod.normalize_newlines("a\r\n\r\nb") == "a\n\nb")
check("hybrid 模式 CRLF 文本归一化",
      injector_mod.build_stream("hybrid", "x\r\ny").count("\n") == 1)
code_crlf = injector_mod.build_stream("code", "x   \r\n\r\ny")
check("code 模式 CRLF 不变成双换行（x / 空行 / y = 2 个换行）",
      code_crlf.count("\n") == 2 and code_crlf == "x\n\ny", repr(code_crlf))

ev = injector_mod.TextInjector(newline=injector_mod.NEWLINE_ENTER).char_events("\n")
check("回车模式 2 个事件", len(ev) == 2, "got %d" % len(ev))
check("回车模式用 Enter 扫描码", ev[0].union.ki.wScan == injector_mod.SC_NEWLINE
      and (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_SCANCODE))
ev = injector_mod.TextInjector(newline=injector_mod.NEWLINE_SHIFT_ENTER).char_events("\n")
check("Shift+回车 4 个事件", len(ev) == 4, "got %d" % len(ev))
check("Shift+回车 先按 Shift", ev[0].union.ki.wScan == injector_mod.SHIFT_SCANCODE
      and not (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_KEYUP))
ev = injector_mod.TextInjector(newline=injector_mod.NEWLINE_CHAR).char_events("\n")
check("换行符模式用 Unicode 0x0A", len(ev) == 2
      and (ev[0].union.ki.dwFlags & injector_mod.KEYEVENTF_UNICODE)
      and ev[0].union.ki.wScan == 0x0A)
check("默认换行方式 = 回车", injector_mod.TextInjector().newline == injector_mod.NEWLINE_ENTER)
check("默认逐字符发送", injector_mod.TextInjector().batch_size == 1)
check("默认间隔 2ms", injector_mod.TextInjector().interval_ms == 2)
check("换行模式选项 3 种", len(injector_mod.NEWLINE_MODES) == 3)

print("== 5. 批量发送与中断（替换 SendInput，不真按键） ==")
calls = []
real_send = injector_mod._SendInput


def fake_send(count, ptr, size):
    arr = ctypes.cast(ptr, ctypes.POINTER(injector_mod.INPUT))
    calls.append([(arr[i].union.ki.wScan, arr[i].union.ki.dwFlags) for i in range(count)])
    return count


injector_mod._SendInput = fake_send
try:
    inj = injector_mod.TextInjector(interval_ms=0, batch_size=2)
    sent = inj.send_text("abcd")
    check("send_text 返回字符数 4", sent == 4, "got %d" % sent)
    check("每批 2 字 -> 2 次 SendInput", len(calls) == 2, "got %d" % len(calls))
    check("事件总数 = 8", sum(len(c) for c in calls) == 8, "got %d" % sum(len(c) for c in calls))

    calls[:] = []
    inj = injector_mod.TextInjector(interval_ms=0, batch_size=2)

    def progress(n):
        if n >= 2:
            inj.cancel()

    sent = inj.send_text("abcdef", on_progress=progress)
    check("中断后停止发送", sent == 2, "got %d" % sent)
    check("中断后只发了 1 批", len(calls) == 1, "got %d" % len(calls))

    calls[:] = []
    inj = injector_mod.TextInjector(interval_ms=0, batch_size=64)
    sent = inj.send_text("中文abc")
    flat = [x for c in calls for x in c]
    check("中英混合共 5 字", sent == 5)
    unicode_events = [1 for sc, fl in flat if fl & injector_mod.KEYEVENTF_UNICODE]
    check("2 个汉字 -> 4 个 Unicode 事件", len(unicode_events) == 4, "got %d" % len(unicode_events))
finally:
    injector_mod._SendInput = real_send

print("== 6. 热键工具 ==")
check("F9 -> 0x78", hotkey_mod.vk_from_keysym("F9") == 0x78)
check("a -> 0x41", hotkey_mod.vk_from_keysym("a") == 0x41)
check("semicolon -> 0xBA", hotkey_mod.vk_from_keysym("semicolon") == 0xBA)
check("Return -> 0x0D", hotkey_mod.vk_from_keysym("Return") == 0x0D)
check("F24 -> 0x87", hotkey_mod.vk_from_keysym("F24") == 0x87)
check("未知键返回 None", hotkey_mod.vk_from_keysym("Multi_key") is None)
check("组合键格式化", hotkey_mod.format_hotkey(
    hotkey_mod.MOD_CONTROL | hotkey_mod.MOD_ALT | hotkey_mod.MOD_SHIFT, 0x54) == "Ctrl+Alt+Shift+T")
check("Win 组合格式化", hotkey_mod.format_hotkey(hotkey_mod.MOD_WIN, 0x20) == "Win+Space")
check("pressed_modifiers 返回整数", isinstance(hotkey_mod.pressed_modifiers(), int))

print("")
print("总计 %d 项，失败 %d 项" % (PASS + FAIL, FAIL))
if FAILED:
    print("失败清单：")
    for item in FAILED:
        print("  -", item)
sys.exit(1 if FAIL else 0)
