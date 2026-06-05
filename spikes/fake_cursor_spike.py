"""
假鼠标指针 overlay —— 技术验证 spike（独立原型，未接入 server）。

验证四件事能否凑对：
  1) 置顶(topmost)        —— 浮在所有窗口之上
  2) 点击穿透(click-through) —— 鼠标点在假指针上也会穿过去点到下面的真实窗口
  3) 假指针动画           —— 一个画出来的箭头在屏幕上平滑移动 + 点击脉冲
  4) DPI 对位             —— 进程 DPI-aware，假指针落在真实屏幕坐标上不错位

用法：
  python spikes/fake_cursor_spike.py                 # 看效果：假指针绕屏幕走 ~12 秒
  python spikes/fake_cursor_spike.py --duration 4 --selftest   # 自检：打印样式校验后 4 秒自关

注意：本脚本不产生任何真实鼠标/键盘事件，纯视觉。
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes

# ---- 必须在创建 Tk 之前设置 DPI 感知，假指针才能落在真实物理坐标上 ----
def _set_dpi_aware() -> str:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        return "shcore.SetProcessDpiAwareness(2)"
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "user32.SetProcessDPIAware()"
        except Exception as exc:  # noqa: BLE001
            return f"failed: {exc}"


_DPI_MODE = _set_dpi_aware()

import tkinter as tk  # noqa: E402  —— 在 DPI 设置之后再导入/创建

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020      # 点击穿透
WS_EX_NOACTIVATE = 0x08000000       # 不抢焦点
WS_EX_TOOLWINDOW = 0x00000080       # 不出现在 Alt-Tab
GA_ROOT = 2
TRANSPARENT = "#010203"             # 颜色键：这个色会变全透明

user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]


def _make_click_through(root: tk.Tk) -> tuple[int, int]:
    """给 Tk 顶层窗口加上 分层+点击穿透+不抢焦点 扩展样式。返回 (hwnd, 最终ExStyle)。"""
    hwnd = user32.GetAncestor(root.winfo_id(), GA_ROOT)
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_long(ex - (1 << 32) if ex >= (1 << 31) else ex))
    final = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    return hwnd, final


# 经典指针箭头的多边形（相对于尖端 (0,0)）
_ARROW = [(0, 0), (0, 22), (5, 17), (9, 24), (12, 23), (8, 15), (15, 15)]
_SCALE = 0.9  # 接近真实系统光标大小


class FakeCursor:
    def __init__(self, duration: float, selftest: bool):
        self.duration = duration
        self.selftest = selftest
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
        self.hwnd, self.exstyle = _make_click_through(self.root)
        self._arrow_ids: list[int] = []

        # 假指针巡游路径：屏幕中心周围四个点 + 回中心
        cx, cy = self.sw // 2, self.sh // 2
        d = min(self.sw, self.sh) // 4
        self.waypoints = [(cx - d, cy - d), (cx + d, cy - d),
                          (cx + d, cy + d), (cx - d, cy + d), (cx, cy)]
        self.pos = [float(cx), float(cy)]
        self._draw_arrow(*self.pos)

    # --- 绘制 ---
    def _draw_arrow(self, x: float, y: float) -> None:
        for i in self._arrow_ids:
            self.canvas.delete(i)
        self._arrow_ids.clear()
        pts = [(x + dx * _SCALE, y + dy * _SCALE) for dx, dy in _ARROW]
        flat = [c for p in pts for c in p]
        # 黑箭头 + 白边，避免和真实(白)光标或浅色背景混淆
        self._arrow_ids.append(self.canvas.create_polygon(
            *flat, fill="black", outline="white", width=1))

    # --- 动画 ---
    def _glide_to(self, target, on_done) -> None:
        tx, ty = target
        steps = 24

        def frame(i: int):
            if i > steps:
                self.root.after(350, on_done)  # 到位停顿，不做点击动画
                return
            t = i / steps
            ease = t * t * (3 - 2 * t)  # smoothstep 缓动
            x = self.pos[0] + (tx - self.pos[0]) * ease
            y = self.pos[1] + (ty - self.pos[1]) * ease
            self._draw_arrow(x, y)
            self.root.after(12, lambda: frame(i + 1))

        frame(0)

    def _tour(self, idx: int = 0) -> None:
        if idx >= len(self.waypoints):
            idx = 0

        def after_pulse():
            self.pos = list(self.waypoints[idx])
            self._tour(idx + 1)

        self._glide_to(self.waypoints[idx], after_pulse)

    def run(self) -> None:
        if self.selftest:
            self._print_selftest()
        self.root.after(80, lambda: self._tour(0))
        self.root.after(int(self.duration * 1000), self.root.destroy)
        try:
            self.root.mainloop()
        except tk.TclError:
            pass  # destroy 后回调收尾的正常异常

    def _print_selftest(self) -> None:
        def has(bit, name):
            return f"{name}={'ON' if self.exstyle & bit else 'off'}"
        print("=== 假鼠标 overlay 自检 ===")
        print(f"DPI 模式      : {_DPI_MODE}")
        print(f"屏幕尺寸      : {self.sw}x{self.sh}（DPI-aware 下为物理像素）")
        print(f"顶层 HWND     : {self.hwnd}")
        print(f"ExStyle(hex)  : 0x{self.exstyle:08X}")
        print("点击穿透/样式 : " + ", ".join([
            has(WS_EX_LAYERED, "LAYERED"),
            has(WS_EX_TRANSPARENT, "TRANSPARENT(穿透)"),
            has(WS_EX_NOACTIVATE, "NOACTIVATE(不抢焦点)"),
            has(WS_EX_TOOLWINDOW, "TOOLWINDOW"),
        ]))
        ok = all(self.exstyle & b for b in
                 (WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE))
        print(f"结论          : {'✅ 关键样式齐全，点击穿透+不抢焦点已生效' if ok else '❌ 样式缺失'}")
        print(f"将运行 {self.duration:.0f}s 后自动关闭。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=12.0, help="运行秒数后自关")
    ap.add_argument("--selftest", action="store_true", help="打印样式校验信息")
    args = ap.parse_args()
    FakeCursor(args.duration, args.selftest).run()


if __name__ == "__main__":
    main()
