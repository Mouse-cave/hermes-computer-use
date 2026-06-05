"""
跨平台桌面控制核心。

职责（单一职责：只负责「与桌面交互」，不关心 MCP 协议）：
1. 截图：用 mss 抓主屏，做「物理像素 → 模型视图」的 DPI 对齐 + 可选降采样。
2. 坐标系转换：模型看到的截图坐标(view 空间) ↔ pyautogui 真实操作坐标(logical 空间)。
3. 鼠标 / 键盘 / 滚动 / 拖拽 等原子动作。

坐标系说明（关键）：
- logical 空间：pyautogui.size() 给出的逻辑分辨率，是真正驱动鼠标的坐标系。
- view 空间   ：返回给模型的截图分辨率 = logical * scale（scale ≤ 1）。
  模型永远在「它看到的截图」上给坐标，本模块负责换算回 logical 再操作。
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import mss
import pyautogui
from PIL import Image as PILImage

from .config import config

# 应用安全设置（进程级，导入即生效）
pyautogui.FAILSAFE = config.failsafe  # 鼠标甩到左上角急停
pyautogui.PAUSE = config.pause        # 每个动作后的固定停顿


# 键名别名 → pyautogui 标准键名，容忍模型用各种叫法
_KEY_ALIASES = {
    "control": "ctrl",
    "ctl": "ctrl",
    "cmd": "command",
    "win": "winleft",
    "windows": "winleft",
    "super": "winleft",
    "meta": "winleft",
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "space": "space",
    "spacebar": "space",
}


@dataclass(frozen=True)
class ScreenGeometry:
    """一次操作时刻的屏幕几何信息。"""

    logical_width: int   # pyautogui 坐标空间（真实鼠标坐标）
    logical_height: int
    view_width: int      # 返回给模型的截图尺寸（模型坐标空间）
    view_height: int
    scale: float         # view = logical * scale
    origin_x: int = 0    # 逻辑坐标原点（多显示器虚拟桌面下可能为负；主屏模式为 0）
    origin_y: int = 0


def get_geometry() -> ScreenGeometry:
    """算出 view/logical 几何、缩放比与原点偏移。多显示器模式覆盖整个虚拟桌面。"""
    if config.multi_monitor:
        with mss.mss() as sct:
            vm = sct.monitors[0]  # 所有显示器的包围盒（left/top 可能为负）
        origin_x, origin_y = int(vm["left"]), int(vm["top"])
        logical_w, logical_h = int(vm["width"]), int(vm["height"])
    else:
        origin_x = origin_y = 0
        logical_w, logical_h = pyautogui.size()
    if config.max_width and logical_w > config.max_width:
        scale = config.max_width / logical_w
    else:
        scale = 1.0
    view_w = max(1, round(logical_w * scale))
    view_h = max(1, round(logical_h * scale))
    return ScreenGeometry(logical_w, logical_h, view_w, view_h, scale, origin_x, origin_y)


def _to_logical(x: float, y: float, geo: ScreenGeometry) -> tuple[int, int]:
    """模型坐标(view 空间) → 真实操作坐标(logical 空间)，并夹紧到屏幕范围内。"""
    lx = geo.origin_x + int(round(x / geo.scale))
    ly = geo.origin_y + int(round(y / geo.scale))
    lx = min(max(lx, geo.origin_x), geo.origin_x + geo.logical_width - 1)
    ly = min(max(ly, geo.origin_y), geo.origin_y + geo.logical_height - 1)
    return lx, ly


def _to_view(lx: float, ly: float, geo: ScreenGeometry) -> tuple[int, int]:
    """真实坐标(logical) → 模型坐标(view)，用于回报光标位置。"""
    return (int(round((lx - geo.origin_x) * geo.scale)),
            int(round((ly - geo.origin_y) * geo.scale)))


def logical_to_view(lx: float, ly: float) -> tuple[int, int]:
    """逻辑/屏幕坐标 → view 坐标（供统一目标层把 UIA 屏幕坐标转成可点击的 view 坐标）。"""
    return _to_view(lx, ly, get_geometry())


def capture_png() -> tuple[bytes, ScreenGeometry]:
    """抓取主屏并编码为 PNG（已对齐到 view 空间）。返回 (png_bytes, 几何信息)。"""
    geo = get_geometry()
    with mss.mss() as sct:
        # [0] 是所有屏幕的包围盒（多显示器模式），[1] 是主屏
        monitor = sct.monitors[0 if config.multi_monitor else 1]
        raw = sct.grab(monitor)
    img = PILImage.frombytes("RGB", raw.size, raw.rgb)
    # 一步到位：物理像素 → view 空间。坐标映射只由 scale 定义，与物理分辨率无关。
    if img.size != (geo.view_width, geo.view_height):
        img = img.resize((geo.view_width, geo.view_height), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), geo


# ---------------------------------------------------------------------------
# 原子动作。所有入参坐标均为 view 空间（模型在截图上读到的坐标）。
# ---------------------------------------------------------------------------

def move(x: int, y: int) -> tuple[int, int]:
    """移动鼠标到 (x, y)。返回实际操作的 logical 坐标。"""
    geo = get_geometry()
    lx, ly = _to_logical(x, y, geo)
    pyautogui.moveTo(lx, ly)
    return lx, ly


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> tuple[int, int]:
    """在 (x, y) 点击。button: left/right/middle；clicks: 点击次数。"""
    geo = get_geometry()
    lx, ly = _to_logical(x, y, geo)
    pyautogui.click(lx, ly, clicks=clicks, button=button)
    return lx, ly


def drag(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    button: str = "left",
    duration: float = 0.4,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """从起点按下拖拽到终点。返回 (起点logical, 终点logical)。"""
    geo = get_geometry()
    sx, sy = _to_logical(start_x, start_y, geo)
    ex, ey = _to_logical(end_x, end_y, geo)
    pyautogui.moveTo(sx, sy)
    pyautogui.dragTo(ex, ey, duration=duration, button=button)
    return (sx, sy), (ex, ey)


def scroll(x: int, y: int, clicks: int) -> tuple[int, int]:
    """在 (x, y) 处滚动。clicks 正数向上、负数向下。返回操作的 logical 坐标。"""
    geo = get_geometry()
    lx, ly = _to_logical(x, y, geo)
    pyautogui.moveTo(lx, ly)
    pyautogui.scroll(clicks, x=lx, y=ly)
    return lx, ly


def type_text(text: str) -> int:
    """在当前焦点处逐字符输入文本。返回输入的字符数。"""
    pyautogui.write(text, interval=config.typing_interval)
    return len(text)


def _normalize_keys(keys: str) -> list[str]:
    """把 'ctrl+c'、'Enter'、'ctrl + shift + esc' 解析为 pyautogui 标准键名列表。"""
    parts = [p.strip().lower() for p in keys.replace(" ", "").split("+") if p.strip()]
    return [_KEY_ALIASES.get(p, p) for p in parts]


def press_key(keys: str) -> list[str]:
    """按下按键或组合键。单键如 'enter'；组合如 'ctrl+c'、'alt+f4'。返回解析后的键名。"""
    parsed = _normalize_keys(keys)
    if not parsed:
        raise ValueError("按键不能为空")
    if len(parsed) == 1:
        pyautogui.press(parsed[0])
    else:
        pyautogui.hotkey(*parsed)
    return parsed


def cursor_position() -> dict:
    """返回当前光标位置（同时给出 view 与 logical 两套坐标）。"""
    geo = get_geometry()
    lx, ly = pyautogui.position()
    vx, vy = _to_view(lx, ly, geo)
    return {"view": [vx, vy], "logical": [lx, ly]}


def wait(seconds: float) -> float:
    """等待若干秒（受 HCU_MAX_ACTION_DELAY 上限保护）。返回实际等待秒数。"""
    capped = max(0.0, min(seconds, config.max_action_delay))
    time.sleep(capped)
    return capped
