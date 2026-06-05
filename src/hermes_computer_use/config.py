"""
运行配置（全部通过环境变量覆盖，无需改代码）。

基础：
- HCU_MAX_WIDTH      返回给模型的截图最大宽度（像素）。屏幕更宽时按比例降采样，
                     可降低 token 消耗并提升模型点击精度。设为 0 表示不缩放。默认 1280。
- HCU_FAILSAFE       是否启用 pyautogui 安全急停：鼠标甩到屏幕左上角立即中止操作。默认 true。
- HCU_PAUSE          每个 pyautogui 动作后的固定停顿（秒），给界面反应时间。默认 0.1。
- HCU_TYPING_INTERVAL 逐字符输入的间隔（秒）。某些输入框过快会丢字，可调大。默认 0.0。
- HCU_MAX_ACTION_DELAY wait() 工具允许的最大等待秒数，防止模型一次睡太久。默认 30。

安全护栏（safety.py）：
- HCU_SAFETY              安全护栏总开关。默认 true。设为 false 关闭以下全部检查。
- HCU_RATE_LIMIT          每分钟允许的动作次数上限，防失控循环。0=不限。默认 120。
- HCU_BLOCK_DANGEROUS_TEXT 是否拦截疑似破坏性命令的输入文本（rm -rf、DROP TABLE…）。默认 true。
- HCU_BLOCKED_HOTKEYS     危险快捷键黑名单，逗号分隔（如 "ctrl+alt+delete,win+l"）。默认 ctrl+alt+delete。

Windows 元素级后端（winuia.py / overlay.py）：
- HCU_OVERLAY             "假鼠标"指针覆盖层开关（操作元素时假指针滑到目标，纯视觉提示）。默认 true。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    """从环境变量读取的不可变配置快照。"""

    # 截图与输入
    max_width: int = _get_int("HCU_MAX_WIDTH", 1280)
    failsafe: bool = _get_bool("HCU_FAILSAFE", True)
    pause: float = _get_float("HCU_PAUSE", 0.1)
    typing_interval: float = _get_float("HCU_TYPING_INTERVAL", 0.0)
    max_action_delay: float = _get_float("HCU_MAX_ACTION_DELAY", 30.0)

    # 安全护栏
    safety_enabled: bool = _get_bool("HCU_SAFETY", True)
    rate_limit_per_min: int = _get_int("HCU_RATE_LIMIT", 120)
    block_dangerous_text: bool = _get_bool("HCU_BLOCK_DANGEROUS_TEXT", True)
    blocked_hotkeys: str = os.environ.get("HCU_BLOCKED_HOTKEYS", "ctrl+alt+delete")

    # Windows 元素级后端
    overlay_enabled: bool = _get_bool("HCU_OVERLAY", True)


# 进程级单例：服务启动时读取一次环境变量
config = Config()
