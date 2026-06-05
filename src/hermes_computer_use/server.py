"""
MCP Server 入口（FastMCP / stdio）。

把 desktop / ocr / window 的能力封装成 MCP 工具，供 Hermes Agent 等 MCP 客户端调用。
动作类工具统一经过 safety 护栏（限速 + 危险输入/快捷键拦截）。
每个工具职责单一；动作后建议 `screenshot` 复核（见 skills/desktop-automation/SKILL.md）。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from . import desktop, environment, ocr, safety, window, winuia

mcp = FastMCP("hermes-computer-use")


def _coord_hint(geo: desktop.ScreenGeometry) -> str:
    """统一的坐标系提示，让模型清楚该在多大的画布上给坐标。"""
    return (
        f"坐标系：请在 {geo.view_width}x{geo.view_height} 的截图画布上给出像素坐标"
        f"（左上角为原点）。"
    )


# ===========================================================================
# 视觉 / 信息（只读，不计入限速）
# ===========================================================================

@mcp.tool()
def screenshot() -> list:
    """截取当前主屏幕，返回 PNG 图像。

    这是「看屏幕」的唯一手段。建议在每次重要操作前后各截一次用于决策与验证。
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
def check_environment() -> str:
    """环境自检（只读）：操作系统、GUI 是否可用、屏幕尺寸/缩放、OCR/窗口管理是否可用、
    安全配置与总体结论。建议在执行桌面控制任务前先调用，用于分诊决策。"""
    return environment.report()


# ===========================================================================
# OCR（按文字找坐标，比纯猜坐标更稳；返回坐标可直接 click）
# ===========================================================================

@mcp.tool()
def ocr_screen() -> str:
    """对当前屏幕做 OCR，列出所有识别到的文字及其中心坐标(view 空间，可直接 click)。"""
    items = ocr.ocr_screen()
    if not items:
        return "未识别到文字。"
    lines = [f"识别到 {len(items)} 段文字（坐标为截图像素，可直接 click）："]
    for it in items:
        cx, cy = it["center"]
        lines.append(f'- "{it["text"]}"  @({cx},{cy})  score={it["score"]}')
    return "\n".join(lines)


@mcp.tool()
def find_text(query: str, exact: bool = False) -> str:
    """在屏幕上查找文字 query，返回可点击坐标。exact=True 要求完全相等，否则子串匹配。

    用法示例：找到「登录」按钮 → find_text("登录") → 拿到坐标后 click。
    """
    matches = ocr.find_text(query, exact=exact)
    if not matches:
        return f'未在屏幕上找到文字 "{query}"。'
    lines = [f'找到 {len(matches)} 处包含 "{query}" 的文字：']
    for it in matches:
        cx, cy = it["center"]
        lines.append(f'- "{it["text"]}"  @({cx},{cy})  score={it["score"]}')
    return "\n".join(lines)


# ===========================================================================
# 鼠标 / 键盘（动作类，经过 safety 限速）
# ===========================================================================

@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """把鼠标移动到截图坐标 (x, y)，不点击。"""
    safety.gate()
    lx, ly = desktop.move(x, y)
    return f"鼠标已移动到 view({x},{y}) → 实际 logical({lx},{ly})。"


@mcp.tool()
def click(x: int, y: int, button: str = "left") -> str:
    """在截图坐标 (x, y) 单击。button 可选 left/right/middle，默认 left。"""
    safety.gate()
    lx, ly = desktop.click(x, y, button=button, clicks=1)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处 {button} 键单击。"


@mcp.tool()
def double_click(x: int, y: int) -> str:
    """在截图坐标 (x, y) 双击（左键）。"""
    safety.gate()
    lx, ly = desktop.click(x, y, button="left", clicks=2)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处双击。"


@mcp.tool()
def right_click(x: int, y: int) -> str:
    """在截图坐标 (x, y) 右键单击（通常用于呼出上下文菜单）。"""
    safety.gate()
    lx, ly = desktop.click(x, y, button="right", clicks=1)
    return f"已在 view({x},{y}) → logical({lx},{ly}) 处右键单击。"


@mcp.tool()
def drag(start_x: int, start_y: int, end_x: int, end_y: int, button: str = "left") -> str:
    """按住鼠标从 (start_x, start_y) 拖拽到 (end_x, end_y)。用于拖动、框选、滑块等。"""
    safety.gate()
    (sx, sy), (ex, ey) = desktop.drag(start_x, start_y, end_x, end_y, button=button)
    return f"已从 logical({sx},{sy}) 拖拽到 logical({ex},{ey})。"


@mcp.tool()
def scroll(x: int, y: int, clicks: int = 3) -> str:
    """在 (x, y) 处滚动滚轮。clicks 正数向上、负数向下，绝对值越大滚得越多。"""
    safety.gate()
    lx, ly = desktop.scroll(x, y, clicks)
    direction = "向上" if clicks >= 0 else "向下"
    return f"已在 logical({lx},{ly}) 处{direction}滚动 {abs(clicks)} 格。"


@mcp.tool()
def type_text(text: str, force: bool = False) -> str:
    """在当前焦点（光标所在输入框）逐字符输入文本。需先点击目标输入框获取焦点。

    安全：默认拦截疑似破坏性命令文本（rm -rf、DROP TABLE…）；确认安全可传 force=true。
    """
    safety.check_text(text, force=force)
    safety.gate()
    n = desktop.type_text(text)
    return f"已输入 {n} 个字符。"


@mcp.tool()
def press_key(keys: str, force: bool = False) -> str:
    """按下按键或组合键。

    示例：'enter'、'esc'、'tab'、'backspace'、'ctrl+c'、'ctrl+v'、
    'alt+f4'、'ctrl+shift+esc'。用 '+' 连接组合键。
    安全：黑名单内的系统级快捷键会被拦截，确认安全可传 force=true。
    """
    parsed = desktop._normalize_keys(keys)
    safety.check_hotkey(parsed, force=force)
    safety.gate()
    desktop.press_key(keys)
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


# ===========================================================================
# 窗口管理（pygetwindow；动作类经过限速）
# ===========================================================================

@mcp.tool()
def list_windows() -> str:
    """列出当前所有有标题的窗口（标题、是否激活、是否最小化、尺寸、位置）。"""
    wins = window.list_windows()
    if not wins:
        return "未发现可见窗口。"
    lines = [f"共 {len(wins)} 个窗口："]
    for w in wins:
        flags = []
        if w["active"]:
            flags.append("激活")
        if w["minimized"]:
            flags.append("最小化")
        tag = f"[{'/'.join(flags)}] " if flags else ""
        lines.append(f'- {tag}"{w["title"]}"  size={w["size"]} pos={w["pos"]}')
    return "\n".join(lines)


@mcp.tool()
def get_active_window() -> str:
    """返回当前激活（前台）窗口的标题与尺寸位置。"""
    w = window.get_active_window()
    if w is None:
        return "当前没有激活窗口。"
    return f'激活窗口："{w["title"]}"  size={w["size"]} pos={w["pos"]}'


@mcp.tool()
def activate_window(title: str) -> str:
    """把标题包含 title 的窗口置前并激活（最小化的会先还原）。"""
    safety.gate()
    full = window.activate_window(title)
    return f'已激活窗口："{full}"。'


@mcp.tool()
def minimize_window(title: str) -> str:
    """最小化标题包含 title 的窗口。"""
    safety.gate()
    full = window.minimize_window(title)
    return f'已最小化窗口："{full}"。'


@mcp.tool()
def maximize_window(title: str) -> str:
    """最大化标题包含 title 的窗口。"""
    safety.gate()
    full = window.maximize_window(title)
    return f'已最大化窗口："{full}"。'


# ===========================================================================
# Windows 原生·元素级（UIA，不抢鼠标；需 [winuia]，仅 Windows）
# 操作时假鼠标滑到目标 + 红框高亮，全程不移动真实光标。
# ===========================================================================

@mcp.tool()
def win_list_apps() -> str:
    """【Windows】列出可连接的顶层窗口（用于挑选要操作的程序）。"""
    apps = winuia.list_apps()
    if not apps:
        return "未发现可连接窗口。"
    lines = [f"共 {len(apps)} 个窗口："]
    for a in apps:
        lines.append(f'- "{a["title"]}"  [{a["control_type"]}]')
    return "\n".join(lines)


@mcp.tool()
def win_inspect(title: str, control_type: str = "", max_items: int = 200) -> str:
    """【Windows】枚举窗口内可交互控件并编号，供后续 win_invoke/win_set_text 按编号操作。

    可用 control_type 过滤（如 Button/Edit/MenuItem/CheckBox）。
    """
    items = winuia.inspect_window(title, control_type=control_type, max_items=max_items)
    if not items:
        return f'窗口"{title}"内未枚举到可交互控件（可能无 UIA 暴露，考虑改用视觉坐标工具）。'
    lines = [f'窗口"{title}" 控件（按 #编号 用 win_invoke/win_set_text 操作）：']
    for it in items:
        aid = f" id={it['automation_id']}" if it.get("automation_id") else ""
        lines.append(f'#{it["index"]} [{it["control_type"]}] "{it["name"]}"{aid}')
    return "\n".join(lines)


@mcp.tool()
def win_invoke(title: str, name: str = "", index: int = -1, control_type: str = "") -> str:
    """【Windows】无光标调用控件（点按钮/菜单项/勾选等）。用 name 或 win_inspect 的 #index 指定。"""
    safety.gate()
    return winuia.invoke(title, index=index, name=name, control_type=control_type)


@mcp.tool()
def win_set_text(title: str, text: str, name: str = "", index: int = -1,
                 control_type: str = "", force: bool = False) -> str:
    """【Windows】无光标往输入框填文本。用 name 或 #index 指定。含危险命令文本拦截(可 force)。"""
    safety.check_text(text, force=force)
    safety.gate()
    return winuia.set_text(title, text, index=index, name=name, control_type=control_type)


@mcp.tool()
def win_capture(title: str) -> list:
    """【Windows】后台截取指定窗口（PrintWindow，窗口非前台也可），返回 PNG 图像。"""
    png = winuia.capture_window(title)
    return [f'窗口"{title}"截图：', Image(data=png, format="png")]


def main() -> None:
    """控制台入口：以 stdio 传输启动 MCP server。"""
    mcp.run()


if __name__ == "__main__":
    main()
