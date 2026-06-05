"""
非破坏性冒烟测试：只验证「能截图、几何/坐标换算正确、按键解析正确、
MCP 工具已注册」，不会真正移动鼠标或敲键盘，安全可重复运行。

运行：python -m tests.smoke_test  （在项目根目录）
"""

from __future__ import annotations

import asyncio

from hermes_computer_use import desktop
from hermes_computer_use.server import mcp


def test_geometry() -> None:
    geo = desktop.get_geometry()
    assert geo.logical_width > 0 and geo.logical_height > 0
    assert 0 < geo.scale <= 1.0
    # view = logical * scale（允许四舍五入 1px 误差）
    assert abs(geo.view_width - round(geo.logical_width * geo.scale)) <= 1
    print(f"[OK] geometry: view={geo.view_width}x{geo.view_height} "
          f"logical={geo.logical_width}x{geo.logical_height} scale={geo.scale:.4f}")


def test_coord_roundtrip() -> None:
    geo = desktop.get_geometry()
    # view 中心点换算到 logical，应落在屏幕范围内且接近真实中心
    cx, cy = geo.view_width // 2, geo.view_height // 2
    lx, ly = desktop._to_logical(cx, cy, geo)
    assert 0 <= lx < geo.logical_width and 0 <= ly < geo.logical_height
    print(f"[OK] coord roundtrip: view({cx},{cy}) -> logical({lx},{ly})")


def test_screenshot() -> None:
    png, geo = desktop.capture_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "返回的不是合法 PNG"
    assert len(png) > 1000, "PNG 过小，可能截图失败"
    print(f"[OK] screenshot: {len(png)} bytes PNG @ {geo.view_width}x{geo.view_height}")


def test_key_parsing() -> None:
    cases = {
        "enter": ["enter"],
        "Ctrl+C": ["ctrl", "c"],
        "ctrl + shift + esc": ["ctrl", "shift", "esc"],
        "win+d": ["winleft", "d"],
        "Return": ["enter"],
    }
    for raw, expected in cases.items():
        got = desktop._normalize_keys(raw)
        assert got == expected, f"{raw!r} -> {got}，期望 {expected}"
    print("[OK] key parsing: 全部用例通过")


def test_tools_registered() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "screenshot", "get_screen_info", "move_mouse", "click", "double_click",
        "right_click", "drag", "scroll", "type_text", "press_key",
        "cursor_position", "wait",
    }
    missing = expected - names
    assert not missing, f"缺少工具：{missing}"
    print(f"[OK] MCP tools registered: {len(names)} 个 -> {sorted(names)}")


def main() -> None:
    test_geometry()
    test_coord_roundtrip()
    test_screenshot()
    test_key_parsing()
    test_tools_registered()
    print("\n[ALL PASSED] 全部冒烟测试通过")


if __name__ == "__main__":
    main()
