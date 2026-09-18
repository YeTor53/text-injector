# -*- coding: utf-8 -*-
# 【手动测试，默认不执行】真机注入测试：自建窗口当靶子，把真实文本注入进去再读回来逐字比对。
# 注意：它会把窗口抢到前台并真的敲键盘，只能在没人用电脑时手动跑，绝不要在后台自动运行。
# 跑法：python scripts/manual_focus_test.py --confirm-focus [--wait 2]
import ctypes
import os
import sys
import time
import threading
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import injector as injector_mod

SAMPLE = "Aa1!@#^&*()_+[]{};:'\"\\|,.<>/?~`-="
CJK = "\u4e2d\u6587\u6d4b\u8bd5\uff1b\u6807\u70b9\uff0c\u53e5\u53f7\u3002"
TEST = SAMPLE + "\n" + CJK + "\n" + "ab12^&%$"

if "--confirm-focus" not in sys.argv:
    print("未执行：本脚本会抢焦点并真的敲键盘。确认无人使用电脑后加 --confirm-focus 再跑。")
    sys.exit(3)

wait = 1.5
if "--wait" in sys.argv:
    wait = float(sys.argv[sys.argv.index("--wait") + 1])

u = ctypes.windll.user32
root = tk.Tk()
root.title("WebTry 真机注入测试")
root.geometry("820x280+60+60")
tk.Label(root, text="正在测试 SendInput 文本注入（窗口会自动关闭）", fg="#444").pack(anchor="w", padx=6, pady=4)
text = tk.Text(root, width=110, height=10, font=("Consolas", 11))
text.pack(fill="both", expand=True, padx=6, pady=6)
root.update()
root.attributes("-topmost", True)
root.lift()
text.focus_force()
root.update()
time.sleep(0.5)
me = int(root.wm_frame(), 16)
kernel32 = ctypes.windll.kernel32


def force_foreground(hwnd):
    # Windows 默认不允许非前台进程抢前台，这里用三种常规手段依次尝试
    if u.GetForegroundWindow() == hwnd:
        return True
    u.ShowWindow(hwnd, 9)  # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    if u.GetForegroundWindow() == hwnd:
        return True
    try:
        fg = u.GetForegroundWindow()
        fg_tid = u.GetWindowThreadProcessId(fg, None)
        my_tid = kernel32.GetCurrentThreadId()
        u.AttachThreadInput(my_tid, fg_tid, True)
        u.SetForegroundWindow(hwnd)
        u.AttachThreadInput(my_tid, fg_tid, False)
    except Exception:
        pass
    if u.GetForegroundWindow() == hwnd:
        return True
    u.keybd_event(0x12, 0, 0, 0)  # ALT 按下
    u.SetForegroundWindow(hwnd)
    u.keybd_event(0x12, 0, 2, 0)  # ALT 抬起
    return u.GetForegroundWindow() == hwnd


force_foreground(me)
time.sleep(0.4)
root.update()

if u.GetForegroundWindow() != me:
    print("SKIP 本窗口未能取得前台（hwnd=%s），未注入任何内容" % hex(me))
    root.destroy()
    sys.exit(2)
if str(root.focus_get()) != str(text):
    print("SKIP 键盘焦点不在编辑框（focus_get=%s），未注入任何内容" % root.focus_get())
    root.destroy()
    sys.exit(2)

root.attributes("-topmost", False)
root.update()
time.sleep(wait)

# 与真实程序一致：注入跑在后台线程，主线程持续泵消息（tkinter 主循环等价物）
injector = injector_mod.TextInjector(interval_ms=2, batch_size=8)
result = {}
received = []
text.bind("<Key>", lambda e: received.append(e.char))


def work():
    try:
        result["sent"] = injector.send_text(TEST)
    except Exception as exc:
        result["error"] = str(exc)


started = time.time()
worker = threading.Thread(target=work, daemon=True)
worker.start()
deadline = started + 20
while worker.is_alive() and time.time() < deadline:
    root.update()
    time.sleep(0.01)
worker.join(2)
for _ in range(20):
    root.update()
    time.sleep(0.02)
elapsed = time.time() - started
sent = result.get("sent", 0)
got = text.get("1.0", "end-1c")
print("Tk 层面收到按键事件 %d 个" % len(received))
root.destroy()

symbols = sum(1 for c in TEST if c in "!@#$%^&*()_+[]{};:'\"\\|,.<>/?~`-=")
print("发送字符数: %d | SendInput 接受事件 %d 个，被拒绝 %d 个 | 耗时 %.2fs"
      % (sent, injector.events_sent, injector.events_failed, elapsed))
print("期望 %d 字 / 实际 %d 字" % (len(TEST), len(got)))
if got == TEST:
    print("PASS 逐字一致：%d 个符号 + 8 个汉字 + 2 个换行全部正确" % symbols)
    sys.exit(0)
print("FAIL 内容不一致")
for i in range(max(len(TEST), len(got))):
    a = TEST[i] if i < len(TEST) else "<无>"
    b = got[i] if i < len(got) else "<无>"
    if a != b:
        print("  第 %d 位 期望 %r 实际 %r" % (i + 1, a, b))
print("实际内容:", repr(got))
sys.exit(1)
