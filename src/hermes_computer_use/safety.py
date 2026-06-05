"""
安全护栏：动作限速、危险输入文本拦截、危险快捷键拦截。

设计前提：本服务只发鼠标/键盘/截图事件，**不直接执行命令**。真正的风险是：
  1) 失控循环高频操作  → 限速（滑动窗口）
  2) 把破坏性命令"打字"进终端（如 rm -rf /、DROP TABLE） → 危险文本拦截
  3) 触发系统级快捷键 → 快捷键黑名单
命中即抛 SafetyError 并给出中文原因。可整体关闭（HCU_SAFETY=off），
或在单次调用时传 force=true 绕过对应检查。
"""

from __future__ import annotations

import re
import time
from collections import deque

from .config import config


class SafetyError(RuntimeError):
    """被安全护栏拦截时抛出，message 为中文原因。"""


# 破坏性命令文本模式：仅在「输入文本」时检查。模式力求具体，避免误伤正常表单填写。
_DANGEROUS_TEXT_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-[a-z]*r[a-z]*f", "rm -rf 递归强制删除"),
    (r"\bmkfs\b", "mkfs 格式化文件系统"),
    (r"dd\s+if=.+of=/dev/", "dd 直写磁盘设备"),
    (r":\s*\(\s*\)\s*\{.*\}\s*;\s*:", "fork bomb"),
    (r"\bformat\s+[a-zA-Z]:", "format 盘符（格式化磁盘）"),
    (r"\bdel\b.*/[sq]", "del /s /q 强制递归删除"),
    (r"\brmdir\s+/s", "rmdir /s 递归删目录"),
    (r"Remove-Item\b.*-Recurse\b.*-Force", "Remove-Item -Recurse -Force"),
    (r"\bshutdown\b", "shutdown 关机/重启"),
    (r"\b(poweroff|halt|reboot)\b", "关机/重启命令"),
    (r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", "DROP 删除表/库"),
    (r"\bTRUNCATE\s+TABLE\b", "TRUNCATE 清空表"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), desc) for p, desc in _DANGEROUS_TEXT_PATTERNS]

# 动作时间戳滑动窗口（限速用，进程级）
_action_times: "deque[float]" = deque()


def _blocked_hotkey_set() -> set[str]:
    """把配置里的黑名单解析为「键名排序后用+连接」的集合，做到顺序无关比较。"""
    result: set[str] = set()
    for combo in (config.blocked_hotkeys or "").split(","):
        combo = combo.strip().lower()
        if combo:
            result.add("+".join(sorted(combo.split("+"))))
    return result


def check_text(text: str, force: bool = False) -> None:
    """检查待输入文本是否疑似破坏性命令。命中抛 SafetyError。"""
    if not config.safety_enabled or not config.block_dangerous_text or force:
        return
    for pattern, desc in _COMPILED:
        if pattern.search(text):
            raise SafetyError(
                f"输入内容疑似危险命令（{desc}），已拦截。"
                f"确认无误可加 force=true 重试。"
            )


def check_hotkey(parsed_keys: list[str], force: bool = False) -> None:
    """检查组合键是否在黑名单。parsed_keys 为已规范化的键名列表。命中抛 SafetyError。"""
    if not config.safety_enabled or force:
        return
    key = "+".join(sorted(k.lower() for k in parsed_keys))
    if key in _blocked_hotkey_set():
        raise SafetyError(
            f"快捷键 {'+'.join(parsed_keys)} 在黑名单中，已拦截。"
            f"如需放行可调整 HCU_BLOCKED_HOTKEYS 或加 force=true。"
        )


def gate() -> None:
    """动作限速闸门：每个动作类工具执行前调用一次。超限抛 SafetyError。"""
    if not config.safety_enabled or config.rate_limit_per_min <= 0:
        return
    now = time.monotonic()
    window_start = now - 60.0
    while _action_times and _action_times[0] < window_start:
        _action_times.popleft()
    if len(_action_times) >= config.rate_limit_per_min:
        raise SafetyError(
            f"动作过于频繁：已达每分钟上限 {config.rate_limit_per_min} 次。"
            f"请放慢节奏，或调大 HCU_RATE_LIMIT。"
        )
    _action_times.append(now)
