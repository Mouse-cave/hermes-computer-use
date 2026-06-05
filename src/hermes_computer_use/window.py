"""
窗口管理：列出窗口、按标题激活/最小化/最大化（基于 pygetwindow）。

pygetwindow 在 Windows 上功能完整；macOS/Linux 支持有限。不支持的平台上，
各函数抛出带说明的 RuntimeError（由上层转成友好提示），而不是让进程崩溃。

注意：本模块不提供「关闭窗口」，避免误关导致未保存数据丢失。
"""

from __future__ import annotations

_gw = None
_import_error: Exception | None = None


def _module():
    """惰性加载 pygetwindow。当前平台不支持时抛出可读错误。"""
    global _gw, _import_error
    if _gw is not None:
        return _gw
    if _import_error is not None:
        raise _import_error
    try:
        import pygetwindow as gw
    except (ImportError, NotImplementedError) as exc:
        _import_error = RuntimeError("当前平台不支持窗口管理（pygetwindow 不可用）。")
        raise _import_error from exc
    _gw = gw
    return _gw


def list_windows() -> list[dict]:
    """列出所有有标题的窗口：标题、是否激活、是否最小化、尺寸、位置。"""
    gw = _module()
    wins: list[dict] = []
    for w in gw.getAllWindows():
        title = (w.title or "").strip()
        if not title:
            continue
        wins.append(
            {
                "title": title,
                "active": bool(getattr(w, "isActive", False)),
                "minimized": bool(getattr(w, "isMinimized", False)),
                "size": [w.width, w.height],
                "pos": [w.left, w.top],
            }
        )
    return wins


def _find_one(title: str):
    """按标题子串找第一个窗口，找不到抛错。"""
    gw = _module()
    wins = gw.getWindowsWithTitle(title)
    if not wins:
        raise RuntimeError(f"未找到标题包含 “{title}” 的窗口。")
    return wins[0]


def activate_window(title: str) -> str:
    """把标题含 title 的窗口置前并激活（若最小化则先还原）。返回该窗口完整标题。"""
    w = _find_one(title)
    try:
        if getattr(w, "isMinimized", False):
            w.restore()
        w.activate()
    except Exception:
        # 某些窗口 activate 偶发失败，用 minimize→restore 兜底把它带到前台
        try:
            w.minimize()
            w.restore()
        except Exception as exc:  # noqa: BLE001 - 转成可读信息上抛
            raise RuntimeError(f"激活窗口失败：{exc}") from exc
    return w.title


def get_active_window() -> dict | None:
    """返回当前激活窗口的信息；无激活窗口时返回 None。"""
    gw = _module()
    w = gw.getActiveWindow()
    if w is None:
        return None
    return {"title": w.title, "size": [w.width, w.height], "pos": [w.left, w.top]}


def minimize_window(title: str) -> str:
    """最小化标题含 title 的窗口。返回该窗口完整标题。"""
    w = _find_one(title)
    w.minimize()
    return w.title


def maximize_window(title: str) -> str:
    """最大化标题含 title 的窗口。返回该窗口完整标题。"""
    w = _find_one(title)
    w.maximize()
    return w.title
