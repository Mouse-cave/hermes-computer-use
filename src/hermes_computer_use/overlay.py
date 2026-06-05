"""
假鼠标 overlay 控制器（在 MCP server 进程内）。

以子进程方式启动 overlay_proc.py，并通过其 stdin 发指令（move/show/hide/quit）。
对外提供线程安全、永不抛错的 move_to / show / hide / stop。

仅 Windows 且 HCU_OVERLAY 开启时启用；其它情况返回 no-op 实现，调用全部静默忽略，
绝不影响真实操作。
"""

from __future__ import annotations

import platform
import subprocess
import sys

from .config import config


class _NoOpOverlay:
    """降级实现：所有调用都安全地什么都不做。"""

    def move_to(self, x: int, y: int) -> None: ...
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def stop(self) -> None: ...


class _ProcessOverlay:
    """真正的覆盖层：驱动 overlay_proc 子进程。"""

    def __init__(self) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "hermes_computer_use.overlay_proc"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def _send(self, line: str) -> None:
        try:
            if self._proc.poll() is None and self._proc.stdin:
                self._proc.stdin.write(line + "\n")
                self._proc.stdin.flush()
        except Exception:
            pass  # 子进程已退出/管道断开等，静默忽略

    def move_to(self, x: int, y: int) -> None:
        self._send(f"move {int(x)} {int(y)}")

    def show(self) -> None:
        self._send("show")

    def hide(self) -> None:
        self._send("hide")

    def stop(self) -> None:
        self._send("quit")
        try:
            self._proc.terminate()
        except Exception:
            pass


_overlay: _NoOpOverlay | _ProcessOverlay | None = None


def get_overlay():
    """返回进程级单例 overlay。非 Windows / 关闭 / 启动失败时返回 no-op。"""
    global _overlay
    if _overlay is not None:
        return _overlay
    if platform.system() != "Windows" or not config.overlay_enabled:
        _overlay = _NoOpOverlay()
        return _overlay
    try:
        _overlay = _ProcessOverlay()
    except Exception:
        _overlay = _NoOpOverlay()
    return _overlay
