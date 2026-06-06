"""
hermes-computer-use
====================

适配 Hermes Agent 的「Computer Use（通用桌面控制）」MCP 服务。
视觉坐标核心跨平台（库层面），UIA 元素级后端与假鼠标 overlay 仅 Windows；当前实测平台为 Windows。

通过 MCP 协议向 Hermes 暴露原子级桌面操作工具：截图、移动/点击鼠标、
键盘输入、滚动、拖拽等。配合 skills/ 下的 SKILL.md 形成「截图→理解→
操作→再截图验证」的闭环。
"""

__version__ = "0.5.0"
