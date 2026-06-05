"""
环境自检：一次性探测运行环境，给 orchestrator 分诊提供事实依据。

探测项：操作系统、Python 版本、GUI 是否可用（能否截图）、屏幕尺寸/缩放、
OCR 是否安装、窗口管理是否可用、安全配置快照，并给出一句总体结论。
全部只读，不产生任何鼠标键盘动作。
"""

from __future__ import annotations

import importlib.util
import os
import platform

from . import desktop
from .config import config


def _gui_status():
    """尝试截图判断有无可用图形桌面。返回 (是否可用, 几何信息 or None, 错误信息 or None)。"""
    try:
        _png, geo = desktop.capture_png()
        return True, geo, None
    except Exception as exc:  # noqa: BLE001 - 任何失败都视为无 GUI
        return False, None, str(exc)


def _ocr_available() -> bool:
    """OCR 依赖是否已安装（不初始化重型引擎，仅查包是否存在）。"""
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def _window_status():
    """窗口管理是否在当前平台可用。返回 (是否可用, 错误信息 or None)。"""
    try:
        from . import window

        window._module()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _runtime_context():
    """探测「跑在什么里」：平台生态、是否在容器内、是否 WSL。供 skill 选执行环境。"""
    system = platform.system()
    ecosystem = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(system, system)
    in_container = False
    is_wsl = False
    if system == "Linux":
        try:
            if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
                in_container = True
            else:
                with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as fp:
                    cgroup = fp.read()
                if any(k in cgroup for k in ("docker", "containerd", "kubepods", "libpod")):
                    in_container = True
        except Exception:  # noqa: BLE001 - 探测失败按"非容器"处理
            pass
        try:
            rel = platform.uname().release.lower()
            is_wsl = "microsoft" in rel or "wsl" in rel
        except Exception:  # noqa: BLE001
            pass
    return ecosystem, in_container, is_wsl


def _verdict(gui_ok: bool, gui_err: str | None, ocr_ok: bool) -> str:
    """根据探测结果给出一句可执行的结论（含平台相关提示）。"""
    if not gui_ok:
        return (
            f"无可用图形桌面（截图失败：{gui_err}）。请在有 GUI 的桌面运行，"
            f"或搭建 Xvfb 虚拟显示 / 虚拟机 / Windows Sandbox / Docker(noVNC) 后再试。"
        )
    notes = ["环境就绪，可进行桌面控制。"]
    if not ocr_ok:
        notes.append('OCR 未安装，按文字定位(find_text)不可用——可 pip install "hermes-computer-use[ocr]"，或退化为坐标点击。')
    system = platform.system()
    if system == "Darwin":
        notes.append("macOS：若点击/截图无效，请到 系统设置→隐私与安全性 授权 辅助功能 + 屏幕录制。")
    elif system == "Linux":
        notes.append("Linux：需 X11 显示(DISPLAY 已设)；Wayland 默认禁合成输入，需切 X11 或用 Xvfb。")
    return " ".join(notes)


def probe() -> dict:
    """探测环境，返回结构化结果（供程序/测试使用）。"""
    gui_ok, geo, gui_err = _gui_status()
    ocr_ok = _ocr_available()
    win_ok, win_err = _window_status()
    ecosystem, in_container, is_wsl = _runtime_context()

    info: dict = {
        "os": f"{platform.system()} {platform.release()}",
        "os_detail": platform.platform(),
        "ecosystem": ecosystem,
        "in_container": in_container,
        "is_wsl": is_wsl,
        "python": platform.python_version(),
        "gui_available": gui_ok,
        "screen": None,
        "ocr_available": ocr_ok,
        "window_management_available": win_ok,
        "safety": {
            "enabled": config.safety_enabled,
            "rate_limit_per_min": config.rate_limit_per_min,
            "block_dangerous_text": config.block_dangerous_text,
            "blocked_hotkeys": config.blocked_hotkeys,
        },
        "verdict": _verdict(gui_ok, gui_err, ocr_ok),
    }
    if gui_ok and geo is not None:
        info["screen"] = {
            "view": [geo.view_width, geo.view_height],
            "logical": [geo.logical_width, geo.logical_height],
            "scale": round(geo.scale, 4),
        }
    else:
        info["gui_error"] = gui_err
    if not win_ok:
        info["window_error"] = win_err
    return info


def report() -> str:
    """把探测结果格式化为人/模型易读的中文报告。"""
    info = probe()
    yn = lambda b: "✅ 可用" if b else "❌ 不可用"  # noqa: E731
    lines = ["环境自检结果："]
    lines.append(f"- 操作系统：{info['os']}（{info['os_detail']}）")
    ctx = []
    if info.get("in_container"):
        ctx.append("容器内")
    if info.get("is_wsl"):
        ctx.append("WSL")
    ctx_txt = f"（{'/'.join(ctx)}）" if ctx else ""
    lines.append(f"- 平台生态：{info['ecosystem']}{ctx_txt}")
    lines.append(f"- Python：{info['python']}")
    lines.append(f"- 图形桌面(GUI)：{yn(info['gui_available'])}")
    if info["screen"]:
        s = info["screen"]
        lines.append(f"- 屏幕：view {s['view'][0]}x{s['view'][1]} / "
                     f"logical {s['logical'][0]}x{s['logical'][1]} / scale {s['scale']}")
    elif info.get("gui_error"):
        lines.append(f"- 截图错误：{info['gui_error']}")
    ocr_tip = "" if info["ocr_available"] else '（pip install "hermes-computer-use[ocr]" 启用按文字定位）'
    lines.append(f"- OCR(按文字定位)：{'✅ 已安装' if info['ocr_available'] else '❌ 未安装'}{ocr_tip}")
    win_tip = "" if info["window_management_available"] else f"（{info.get('window_error', '')}）"
    lines.append(f"- 窗口管理：{yn(info['window_management_available'])}{win_tip}")
    sf = info["safety"]
    lines.append(
        f"- 安全护栏：开启={sf['enabled']}，限速={sf['rate_limit_per_min']}/min，"
        f"危险文本拦截={sf['block_dangerous_text']}，快捷键黑名单={sf['blocked_hotkeys']}"
    )
    lines.append(f"- 结论：{info['verdict']}")
    return "\n".join(lines)
