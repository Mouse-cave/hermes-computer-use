"""
路由提示：帮模型在"该用浏览器 DOM 工具"时不要硬走纯视觉 computer use。

网页内的操作（点链接/按钮、填表单、登录登出）用浏览器工具(DOM/ref，带 aria-label/role)
远比截图+坐标点击稳。这里只做"是不是浏览器窗口"的轻量判断 + 统一文案，
由 server 工具在返回里附上提示。
"""

from __future__ import annotations

# 浏览器窗口标题里常见的标记（小写匹配；已去掉零宽空格等）
_BROWSER_MARKERS = (
    "microsoft edge",
    "google chrome",
    "mozilla firefox",
    "chromium",
    "brave",
    "opera",
    "vivaldi",
)

BROWSER_HINT = "（浏览器窗口 → 网页内操作请优先用浏览器 DOM 工具，比纯视觉点击更稳、更准）"


def is_browser_window(title: str) -> bool:
    """根据窗口标题判断是否浏览器窗口（跨平台、零依赖）。"""
    t = (title or "").replace("​", "").replace("‎", "").lower()
    return any(m in t for m in _BROWSER_MARKERS)
