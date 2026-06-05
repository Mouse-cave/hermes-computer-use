"""
假鼠标 overlay 子进程：由 overlay.py 以子进程方式启动，从 stdin 读指令驱动。

每行一条指令：
  move <x> <y>   假指针平滑移动到屏幕坐标(物理像素)并显示
  show / hide    显示 / 隐藏
  quit           退出
stdin 关闭(父进程退出)时自动收尾退出。

独立进程的意义：本进程设为 DPI-aware（假指针落在真实物理坐标上），且与父进程(MCP server)
隔离——不改变父进程里 pyautogui/mss 的坐标行为。纯视觉，不产生任何真实鼠标/键盘事件。
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes


def _set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_set_dpi_aware()

import tkinter as tk  # noqa: E402 —— DPI 设置后再导入

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
TRANSPARENT = "#010203"

user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]

# 黑箭头 + 白边（默认大小≈真实光标）
_ARROW = [(0, 0), (0, 22), (5, 17), (9, 24), (12, 23), (8, 15), (15, 15)]
_SCALE = 0.9

_state = {"target": None, "pos": None, "visible": False, "alive": True}
_lock = threading.Lock()


def _reader() -> None:
    """后台线程：读 stdin 指令，仅更新普通变量（不触碰 Tk）。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        with _lock:
            if parts[0] == "move" and len(parts) >= 3:
                try:
                    _state["target"] = (float(parts[1]), float(parts[2]))
                    _state["visible"] = True
                except ValueError:
                    pass
            elif parts[0] == "hide":
                _state["visible"] = False
            elif parts[0] == "show":
                _state["visible"] = True
            elif parts[0] == "quit":
                _state["alive"] = False
                break
    with _lock:
        _state["alive"] = False


class _Overlay:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSPARENT)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.sw}x{self.sh}+0+0")
        self.canvas = tk.Canvas(self.root, width=self.sw, height=self.sh,
                                bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.root.update_idletasks()
        self._make_click_through()
        self._ids: list[int] = []

    def _make_click_through(self) -> None:
        hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        signed = ex - (1 << 32) if ex >= (1 << 31) else ex
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_long(signed))

    def _draw(self, x: float, y: float) -> None:
        for i in self._ids:
            self.canvas.delete(i)
        self._ids.clear()
        pts = [(x + dx * _SCALE, y + dy * _SCALE) for dx, dy in _ARROW]
        flat = [c for p in pts for c in p]
        self._ids.append(self.canvas.create_polygon(*flat, fill="black", outline="white", width=1))

    def _clear(self) -> None:
        for i in self._ids:
            self.canvas.delete(i)
        self._ids.clear()

    def tick(self) -> None:
        with _lock:
            alive, vis, target, pos = (_state["alive"], _state["visible"],
                                       _state["target"], _state["pos"])
        if not alive:
            self.root.destroy()
            return
        if vis and target:
            if pos is None:
                pos = target
            nx = pos[0] + (target[0] - pos[0]) * 0.35  # 缓动跟随
            ny = pos[1] + (target[1] - pos[1]) * 0.35
            with _lock:
                _state["pos"] = (nx, ny)
            self._draw(nx, ny)
        else:
            self._clear()
        self.root.after(12, self.tick)

    def run(self) -> None:
        threading.Thread(target=_reader, daemon=True).start()
        self.root.after(20, self.tick)
        try:
            self.root.mainloop()
        except tk.TclError:
            pass


if __name__ == "__main__":
    try:
        _Overlay().run()
    except Exception:
        pass
