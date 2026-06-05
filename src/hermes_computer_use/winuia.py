"""
Windows 原生「元素级」桌面控制后端（对标 Hermes macOS cua-driver，填 Windows 空白）。

通过 UI Automation 直接按控件调用（Invoke / SetValue 等）+ PrintWindow 后台截图，
实现"操作主机程序但**不移动你的物理鼠标、不抢焦点**"。操作前用 overlay 假指针滑到目标 +
draw_outline 红框高亮，让你看得见它在操作什么。

仅 Windows；依赖 pywinauto（可选）：pip install "hermes-computer-use[winuia]"。
与视觉坐标后端(desktop.py)互补：标准业务软件(Win32/WinForms/WPF/UWP)优先用本后端更稳；
不暴露 UIA 的程序(游戏/自绘/部分Electron)再回退视觉坐标或 VM。
"""

from __future__ import annotations

import io
import platform
import re

from . import overlay as _overlay_mod

_desktop = None              # pywinauto Desktop(backend="uia") 单例
_import_error: Exception | None = None
_last_elements: dict[str, list] = {}   # 每个窗口最近一次 inspect 的控件缓存（供按编号操作）


def is_supported() -> tuple[bool, str | None]:
    if platform.system() != "Windows":
        return False, "Windows UIA 后端仅支持 Windows。"
    return True, None


def _ui():
    """惰性初始化 pywinauto UIA Desktop。未装依赖/非 Windows 时抛可读错误。"""
    global _desktop, _import_error
    if _desktop is not None:
        return _desktop
    if _import_error is not None:
        raise _import_error
    ok, msg = is_supported()
    if not ok:
        _import_error = RuntimeError(msg)
        raise _import_error
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        _import_error = RuntimeError(
            '未安装 Windows UIA 依赖：pip install "hermes-computer-use[winuia]"'
        )
        raise _import_error from exc
    _desktop = Desktop(backend="uia")
    return _desktop


def _key(title: str) -> str:
    return title.strip().lower()


def _rect(wrapper) -> list[int] | None:
    try:
        r = wrapper.rectangle()
        return [r.left, r.top, r.right, r.bottom]
    except Exception:
        return None


def _center(wrapper) -> tuple[int, int] | None:
    r = _rect(wrapper)
    if not r:
        return None
    return (r[0] + r[2]) // 2, (r[1] + r[3]) // 2


def _connect(title: str):
    """按标题子串连接窗口，返回 pywinauto WindowSpecification。"""
    desk = _ui()
    spec = desk.window(title_re=f".*{re.escape(title)}.*")
    try:
        spec.wait("exists", timeout=3)
    except Exception as exc:
        raise RuntimeError(f"未找到窗口（标题含“{title}”）：{exc}")
    return spec


def _feedback(wrapper) -> None:
    """操作前的可视反馈：假指针滑到目标中心 + 红框高亮（失败不影响真实操作）。"""
    center = _center(wrapper)
    if center:
        try:
            _overlay_mod.get_overlay().move_to(*center)
        except Exception:
            pass
    try:
        wrapper.draw_outline(colour="red")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 对外能力
# ---------------------------------------------------------------------------

def list_apps() -> list[dict]:
    """列出可连接的顶层窗口（标题、控件类型、矩形）。"""
    desk = _ui()
    apps = []
    for w in desk.windows():
        try:
            title = (w.window_text() or "").strip()
            if not title:
                continue
            apps.append({"title": title,
                         "control_type": w.element_info.control_type,
                         "rect": _rect(w)})
        except Exception:
            continue
    return apps


def inspect_window(title: str, control_type: str = "", max_items: int = 200) -> list[dict]:
    """枚举窗口内可交互控件，给每个编号(SOM)。返回 [{index,control_type,name,automation_id,rect}]。

    编号会缓存，后续 invoke/set_text 可用 index 引用（也可用 name）。
    """
    spec = _connect(title)
    try:
        descendants = spec.descendants()
    except Exception as exc:
        raise RuntimeError(f"枚举控件失败：{exc}")

    items: list[dict] = []
    cache: list = []
    for el in descendants:
        try:
            info = el.element_info
            ctype = info.control_type
            if control_type and ctype != control_type:
                continue
            name = (info.name or "").strip()
            # 跳过无名装饰元素，但保留输入类(可能靠 automation_id 定位)
            if not name and ctype not in ("Edit", "ComboBox", "Document"):
                continue
            if not el.is_visible():
                continue
            items.append({"index": len(cache), "control_type": ctype, "name": name,
                          "automation_id": info.automation_id, "rect": _rect(el)})
            cache.append(el)
            if len(items) >= max_items:
                break
        except Exception:
            continue
    _last_elements[_key(title)] = cache
    return items


def _resolve(title: str, index: int = -1, name: str = "", control_type: str = ""):
    """按 index(取自最近 inspect 缓存) 或 name 解析出控件 wrapper。"""
    if index is not None and index >= 0:
        cache = _last_elements.get(_key(title))
        if not cache or index >= len(cache):
            raise RuntimeError("index 无效或缓存已过期，请先调用 inspect_window。")
        return cache[index]
    if name:
        spec = _connect(title)
        kwargs = {"title": name}
        if control_type:
            kwargs["control_type"] = control_type
        try:
            return spec.child_window(**kwargs).wrapper_object()
        except Exception as exc:
            raise RuntimeError(f"未找到控件 name={name!r}：{exc}")
    raise ValueError("需提供 index 或 name 之一。")


def invoke(title: str, index: int = -1, name: str = "", control_type: str = "") -> str:
    """按编号/名称无光标调用控件（按钮/菜单项/复选框等）。返回操作描述。"""
    from pywinauto import uia_defines

    el = _resolve(title, index, name, control_type)
    _feedback(el)
    # 1) Invoke 模式（标准按钮/菜单项），规范调用、不移动光标
    try:
        uia_defines.get_elem_interface(el.element_info.element, "Invoke").Invoke()
        return _describe(el, "invoke")
    except Exception:
        pass
    # 2) Toggle / Selection / Expand 等其它模式
    for method in ("toggle", "select", "expand"):
        if hasattr(el, method):
            try:
                getattr(el, method)()
                return _describe(el, method)
            except Exception:
                continue
    raise RuntimeError("该元素不支持无光标调用（无 Invoke/Toggle/Select），建议改用视觉坐标工具。")


def set_text(title: str, text: str, index: int = -1, name: str = "", control_type: str = "") -> str:
    """按编号/名称无光标设置文本（UIA ValuePattern）。ComboBox 等容器会自动找其下 Edit。"""
    from pywinauto import uia_defines

    el = _resolve(title, index, name, control_type)
    _feedback(el)
    # 候选：元素自身 + 其下的 Edit（应对 ComboBox/Document 等容器）
    candidates = [el]
    try:
        candidates += [c for c in el.descendants()
                       if c.element_info.control_type == "Edit"]
    except Exception:
        pass
    errors: list[str] = []
    for cand in candidates:
        try:
            uia_defines.get_elem_interface(cand.element_info.element, "Value").SetValue(text)
            return _describe(el, "set_value")
        except Exception as exc:  # noqa: BLE001 - 收集后统一上报
            errors.append(str(exc))
    if hasattr(el, "set_edit_text"):
        try:
            el.set_edit_text(text)
            return _describe(el, "set_text")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    raise RuntimeError("无法无光标设置文本：" + "；".join(errors[:2]))


def capture_window(title: str) -> bytes:
    """后台截取指定窗口（PrintWindow），返回 PNG。可在窗口非前台时使用。"""
    spec = _connect(title)
    try:
        img = spec.capture_as_image()
    except Exception as exc:
        raise RuntimeError(f"窗口截图失败：{exc}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _describe(wrapper, action: str) -> str:
    try:
        info = wrapper.element_info
        return f'已对 {info.control_type} "{(info.name or "").strip()}" 执行 {action}（未移动真实鼠标）。'
    except Exception:
        return f"已执行 {action}（未移动真实鼠标）。"
