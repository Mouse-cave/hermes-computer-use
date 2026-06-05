"""
统一「编号目标」层 + 执行回退梯子（M2）。

把两种来源统一成带编号的可操作目标，模型只需 targets 枚举、tap 点击、fill 填字：
  - UIA 控件（Windows，元素级，**不抢光标**）
  - OCR 文字（任意像素界面，兜底）

执行回退梯子（命中即停）：
  ① UIA 无光标调用            （source=uia）
  ② 窗口内消息坐标点击·无光标  （best-effort，对传统控件有效）
  ③ 视觉坐标·前台点击          （**会移动真实光标**，最终兜底）
"""

from __future__ import annotations

import platform

from . import desktop, ocr
from . import winuia as _winuia

_CACHE: list[dict] = []


def _winuia_available() -> bool:
    ok, _ = _winuia.is_supported()
    if not ok:
        return False
    try:
        _winuia._ui()
        return True
    except Exception:
        return False


def build(title: str = "", max_items: int = 200) -> list[dict]:
    """枚举目标并编号。给了 Windows 窗口标题优先 UIA 控件，否则/为空用 OCR 文字兜底。"""
    global _CACHE
    targets: list[dict] = []

    if title and platform.system() == "Windows" and _winuia_available():
        try:
            for it in _winuia.inspect_window(title, max_items=max_items):
                rect = it.get("rect")
                if not rect:
                    continue
                scx, scy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
                vx, vy = desktop.logical_to_view(scx, scy)
                targets.append({
                    "id": len(targets), "source": "uia", "name": it["name"],
                    "control_type": it["control_type"], "uia_index": it["index"],
                    "win_title": title, "screen_center": [scx, scy], "center_view": [vx, vy],
                })
        except Exception:
            pass

    if not targets:  # OCR 兜底（无 UIA 结果或未指定窗口）
        try:
            for t in ocr.ocr_screen():
                targets.append({
                    "id": len(targets), "source": "ocr", "name": t["text"],
                    "control_type": "Text", "win_title": title,
                    "center_view": t["center"], "screen_center": None,
                })
        except Exception:
            pass

    _CACHE = targets
    return targets


def _get(target_id: int) -> dict:
    if not _CACHE or target_id < 0 or target_id >= len(_CACHE):
        raise RuntimeError("目标编号无效或缓存已过期，请先调用 targets 枚举。")
    return _CACHE[target_id]


def tap(target_id: int) -> str:
    """点击编号目标，按回退梯子执行。"""
    t = _get(target_id)
    notes: list[str] = []
    if t["source"] == "uia":
        try:  # ① UIA 无光标
            return f"[①UIA·无光标] {_winuia.invoke(t['win_title'], index=t['uia_index'])}"
        except Exception as exc:  # noqa: BLE001
            notes.append(f"UIA失败({exc})")
        if t.get("screen_center"):
            try:  # ② 消息坐标·无光标（best-effort）
                r = _winuia.message_click(t["win_title"], *t["screen_center"])
                return f"[②消息坐标·无光标] {r}（UIA 不可用时回退）"
            except Exception as exc:  # noqa: BLE001
                notes.append(f"消息坐标失败({exc})")
    # ③ 视觉坐标·前台点击（会移动真实光标）
    vx, vy = t["center_view"]
    desktop.click(vx, vy)
    tail = ("；前序：" + "；".join(notes)) if notes else ""
    return f"[③视觉坐标·已移动光标] 点击 view({vx},{vy}){tail}"


def fill(target_id: int, text: str) -> str:
    """往编号目标填文本，按回退梯子执行。"""
    t = _get(target_id)
    if t["source"] == "uia":
        try:  # ① UIA 无光标
            return f"[①UIA·无光标] {_winuia.set_text(t['win_title'], text, index=t['uia_index'])}"
        except Exception:  # noqa: BLE001
            pass
    # ③ 视觉坐标：点击获取焦点后键入（会移动真实光标）
    vx, vy = t["center_view"]
    desktop.click(vx, vy)
    desktop.type_text(text)
    return f"[③视觉坐标·已移动光标] 已点击 view({vx},{vy}) 并键入 {len(text)} 字符"
