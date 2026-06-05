"""
MCP Server 入口（FastMCP / stdio）。

把 desktop.py 的原子动作封装成 MCP 工具，供 Hermes Agent 等 MCP 客户端调用。
每个工具职责单一；动作类工具返回简短中文确认，模型应在关键动作后自行调用
`screenshot` 复核（详见 skills/desktop-automation/SKILL.md）。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from . import desktop

mcp = FastMCP("hermes-computer-use")


def _coord_hint(geo: desktop.ScreenGeometry) -> str:
    """统一的坐标系提示，让模型清楚该在多大的画布上给坐标。"""
    return (
        f"坐标系：请在 {geo.view_width}x{geo.view_height} 的截图画布上给出像素坐标"
        f"（左上角为原点）。"
    )


@mcp.tool()
def screenshot() -> list:
    """截取当前主屏幕，返回 PNG 图像。

    这是「看屏幕」的唯一手段。建议在每次重要操作前后各截一次，
    用于决策与验证。返回内容含坐标系尺寸提示。
    """
    png, geo = desktop.capture_png()
    return [_coord_hint(geo), Image(data=png, format="png")]


@mcp.tool()
def get_screen_info() -> str:
    """获取屏幕几何信息：模型坐标空间尺寸、真实逻辑分辨率、缩放比。"""
    geo = desktop.get_geometry()
    return (
        f"模型坐标空间(view)：{geo.view_width}x{geo.view_height}\n"
        f"真实逻辑分辨率(logical)：{geo.logical_width}x{geo.logical_height}\n"
        f"缩放比 scale：{geo.scale:.4f}（view = logical × scale）"
    )


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """把鼠标移动到截图坐标 (x, y)，不点击。"""
    lx, ly = desktop.move(x, y)
    return f"鼠标已移动到 view({x},{y}) → 实际 logical({lx},{ly})。"


@mcp.tool()
def click(x: int, y: int, button: str = "left") -> str:
    """在截图坐标 (x, y) 单击。button 可选 left/right/middle，默认 left。"""
    lx, ly = desktop.click(x, y, button=button, clicks=1)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处 {button} 键单击。"


@mcp.tool()
def double_click(x: int, y: int) -> str:
    """在截图坐标 (x, y) 双击（左键）。"""
    lx, ly = desktop.click(x, y, button="left", clicks=2)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处双击。"


@mcp.tool()
def right_click(x: int, y: int) -> str:
    """在截图坐标 (x, y) 右键单击（通常用于呼出上下文菜单）。"""
    lx, ly = desktop.click(x, y, button="right", clicks=1)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处右键单击。"


@mcp.tool()
def drag(start_x: int, start_y: int, end_x: int, end_y: int, button: str = "left") -> str:
    """按住鼠标从 (start_x, start_y) 拖拽到 (end_x, end_y)。用于拖动、框选、滑块等。"""
    (sx, sy), (ex, ey) = desktop.drag(start_x, start_y, end_x, end_y, button=button)
    return f"已从 logical({sx},{sy}) 拖拽到 logical({ex},{ey})。"


@mcp.tool()
def scroll(x: int, y: int, clicks: int = 3) -> str:
    """在 (x, y) 处滚动滚轮。clicks 正数向上、负数向下，绝对值越大滚得越多。"""
    lx, ly = desktop.scroll(x, y, clicks)
    direction = "向上" if clicks >= 0 else "向下"
    return f"已在 logical({lx},{ly}) 处{direction}滚动 {abs(clicks)} 格。"


@mcp.tool()
def type_text(text: str) -> str:
    """在当前焦点（光标所在输入框）逐字符输入文本。需先点击目标输入框获取焦点。"""
    n = desktop.type_text(text)
    return f"已输入 {n} 个字符。"


@mcp.tool()
def press_key(keys: str) -> str:
    """按下按键或组合键。

    示例：'enter'、'esc'、'tab'、'backspace'、'ctrl+c'、'ctrl+v'、
    'alt+f4'、'ctrl+shift+esc'、'winleft+d'。用 '+' 连接组合键。
    """
    parsed = desktop.press_key(keys)
    return f"已按下：{' + '.join(parsed)}"


@mcp.tool()
def cursor_position() -> str:
    """查询当前鼠标位置（同时给出截图坐标 view 与真实坐标 logical）。"""
    pos = desktop.cursor_position()
    return f"光标位置 view={pos['view']}，logical={pos['logical']}。"


@mcp.tool()
def wait(seconds: float = 1.0) -> str:
    """等待若干秒，用于等界面加载/动画结束。受上限保护（默认最多 30 秒）。"""
    actual = desktop.wait(seconds)
    return f"已等待 {actual:.2f} 秒。"


def main() -> None:
    """控制台入口：以 stdio 传输启动 MCP server。"""
    mcp.run()


if __name__ == "__main__":
    main()
