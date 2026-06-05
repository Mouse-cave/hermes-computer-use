"""
非破坏性冒烟测试：验证「能截图、几何/坐标换算正确、按键解析正确、安全护栏生效、
窗口管理可用、OCR（若已安装）可用、MCP 工具齐全」，不会真正移动鼠标或敲键盘，
安全可重复运行。

运行：python tests/smoke_test.py   （建议加 PYTHONUTF8=1 以正常显示中文）
"""

from __future__ import annotations

import asyncio

from hermes_computer_use import desktop, environment, safety, window, winuia
from hermes_computer_use.config import config
from hermes_computer_use.safety import SafetyError
from hermes_computer_use.server import mcp


def test_geometry() -> None:
    geo = desktop.get_geometry()
    assert geo.logical_width > 0 and geo.logical_height > 0
    assert 0 < geo.scale <= 1.0
    assert abs(geo.view_width - round(geo.logical_width * geo.scale)) <= 1
    print(f"[OK] geometry: view={geo.view_width}x{geo.view_height} "
          f"logical={geo.logical_width}x{geo.logical_height} scale={geo.scale:.4f}")


def test_coord_roundtrip() -> None:
    geo = desktop.get_geometry()
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


def test_safety_text() -> None:
    # 危险命令应被拦截
    for bad in ["rm -rf /", "sudo rm -Rf ~", "DROP TABLE users;", "format c:"]:
        raised = False
        try:
            safety.check_text(bad)
        except SafetyError:
            raised = True
        assert raised, f"危险文本未被拦截：{bad!r}"
    # 正常表单内容不应被拦截
    for ok in ["张三", "iPhone 13 Pro 256G 成色95新", "价格 4500.00"]:
        safety.check_text(ok)  # 不抛即通过
    # force=true 放行
    safety.check_text("rm -rf /", force=True)
    print("[OK] safety(text): 危险拦截 + 正常放行 + force 旁路 均正确")


def test_safety_hotkey() -> None:
    raised = False
    try:
        safety.check_hotkey(["ctrl", "alt", "delete"])
    except SafetyError:
        raised = True
    assert raised, "ctrl+alt+delete 未被拦截"
    safety.check_hotkey(["ctrl", "c"])           # 正常组合键放行
    safety.check_hotkey(["ctrl", "alt", "delete"], force=True)  # force 放行
    print("[OK] safety(hotkey): 黑名单拦截 + 正常放行 + force 旁路 均正确")


def test_safety_rate_limit() -> None:
    if config.rate_limit_per_min <= 0:
        print("[SKIP] safety(rate): 限速已关闭")
        return
    # 连续触发到上限，下一个应被拦截
    raised = False
    try:
        for _ in range(config.rate_limit_per_min + 1):
            safety.gate()
    except SafetyError:
        raised = True
    assert raised, "超过每分钟上限未触发限速"
    print(f"[OK] safety(rate): 超过 {config.rate_limit_per_min}/min 正确限速")


def test_environment() -> None:
    info = environment.probe()
    assert info["gui_available"] is True, "本机有桌面，gui_available 应为 True"
    assert info["screen"] is not None and info["verdict"]
    assert isinstance(info["ocr_available"], bool)
    assert info["ecosystem"] in ("Windows", "macOS", "Linux")
    assert isinstance(info["in_container"], bool) and isinstance(info["is_wsl"], bool)
    print(f"[OK] environment: ecosystem={info['ecosystem']} container={info['in_container']} "
          f"gui={info['gui_available']} ocr={info['ocr_available']} win={info['window_management_available']}")


def test_window() -> None:
    try:
        wins = window.list_windows()
    except RuntimeError as e:
        print(f"[SKIP] window: 当前平台不支持（{e}）")
        return
    assert isinstance(wins, list)
    print(f"[OK] window: 列出 {len(wins)} 个窗口")


def test_winuia() -> None:
    ok, msg = winuia.is_supported()
    if not ok:
        print(f"[SKIP] winuia: {msg}")
        return
    try:
        apps = winuia.list_apps()
    except RuntimeError as e:
        print(f"[SKIP] winuia: {e}")  # 未装 pywinauto
        return
    assert isinstance(apps, list)
    out = f"列出 {len(apps)} 个窗口"
    if apps:
        title = apps[0]["title"]
        try:
            items = winuia.inspect_window(title, max_items=20)
            png = winuia.capture_window(title)
            assert isinstance(items, list) and png[:8] == b"\x89PNG\r\n\x1a\n"
            out += f"；inspect 首窗得 {len(items)} 控件；capture {len(png)}B PNG"
        except Exception as e:  # noqa: BLE001 - 个别窗口枚举/截图失败不算硬错误
            out += f"（inspect/capture 跳过：{e}）"
    print(f"[OK] winuia: {out}")


def test_wait_stable() -> None:
    import time as _t
    t = _t.perf_counter()
    elapsed, ok = desktop.wait_until_stable(timeout=3.0)
    real = _t.perf_counter() - t
    assert isinstance(elapsed, float) and isinstance(ok, bool)
    assert real <= 3.6, "不应超时太多"
    print(f"[OK] wait_stable: 稳定={ok} 用时={elapsed:.2f}s (上限3s)")


def test_targets() -> None:
    from hermes_computer_use import targets as targets_mod
    title = ""
    try:
        apps = winuia.list_apps()
        if apps:
            title = apps[0]["title"]
    except Exception:
        pass
    items = targets_mod.build(title)
    assert isinstance(items, list)
    assert all(it["id"] == i for i, it in enumerate(items)), "目标编号应连续"
    srcs = {it["source"] for it in items}
    print(f"[OK] targets: 枚举 {len(items)} 个目标（来源={srcs or '空'}，窗口='{title}'）")


def test_ocr() -> None:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        print('[SKIP] ocr: 未安装（pip install "hermes-computer-use[ocr]" 后可测）')
        return
    from hermes_computer_use import ocr
    items = ocr.ocr_screen()
    assert isinstance(items, list)
    print(f"[OK] ocr: 识别到 {len(items)} 段文字" +
          (f"，示例: {items[0]['text']!r} @ {items[0]['center']}" if items else ""))


def test_tools_registered() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "screenshot", "get_screen_info", "check_environment", "ocr_screen", "find_text",
        "move_mouse", "click", "double_click", "right_click", "drag", "scroll",
        "type_text", "press_key", "cursor_position", "wait",
        "list_windows", "get_active_window", "activate_window",
        "minimize_window", "maximize_window",
        "win_list_apps", "win_inspect", "win_invoke", "win_set_text", "win_capture",
        "win_wake_accessibility", "targets", "tap", "fill", "wait_stable",
    }
    missing = expected - names
    assert not missing, f"缺少工具：{missing}"
    print(f"[OK] MCP tools registered: {len(names)} 个 -> {sorted(names)}")


def main() -> None:
    test_geometry()
    test_coord_roundtrip()
    test_screenshot()
    test_key_parsing()
    test_safety_text()
    test_safety_hotkey()
    test_safety_rate_limit()
    test_environment()
    test_window()
    test_winuia()
    test_wait_stable()
    test_targets()
    test_ocr()
    test_tools_registered()
    print("\n[ALL PASSED] 全部冒烟测试通过")


if __name__ == "__main__":
    main()
