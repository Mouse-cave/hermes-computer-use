---
name: desktop-automation
description: 当需要直接操作电脑图形界面（点击按钮、填写表单、操作没有 API 的桌面软件、跨应用搬运数据、看屏幕找东西）时使用。依赖 computer-use MCP 服务提供的截图与鼠标键盘工具。
version: 0.1.0
platforms: [windows, macos, linux]
metadata:
  hermes:
    tags: [computer-use, gui, automation, desktop, mcp]
  category: automation
---

# 桌面自动化（Desktop Automation）

教你用 `computer-use` MCP 服务「看屏幕 + 操作鼠标键盘」来完成图形界面任务。
核心是一个闭环：**截图看清楚 → 想清楚下一步 → 执行一个动作 → 再截图验证**。

## 何时使用（When to Use）

- 目标软件**没有 API/命令行**，只能用鼠标键盘操作（如桌面客户端、老旧 ERP、微信开发者工具）。
- 需要**跨应用**把数据从 A 搬到 B。
- 需要**看屏幕**判断当前状态（弹窗、加载、报错）后再决定操作。

> 能用命令行 / 文件工具 / 浏览器工具直接完成的，**优先用那些**，不要绕到桌面点击——它们更快更稳。

## 可用工具（Quick Reference）

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `screenshot` | 截当前主屏，返回图片 + 坐标系尺寸 | 无 |
| `get_screen_info` | 查坐标空间/真实分辨率/缩放比 | 无 |
| `move_mouse` | 移动鼠标不点击 | x, y |
| `click` | 单击 | x, y, button(left/right/middle) |
| `double_click` | 双击 | x, y |
| `right_click` | 右键（呼出菜单） | x, y |
| `drag` | 拖拽（拖动/框选/滑块） | start_x, start_y, end_x, end_y |
| `scroll` | 滚轮（正=上，负=下） | x, y, clicks |
| `type_text` | 在焦点处输入文字 | text |
| `press_key` | 按键/组合键 | keys 如 `enter`、`ctrl+c` |
| `cursor_position` | 查当前鼠标位置 | 无 |
| `wait` | 等待加载/动画（≤30s） | seconds |
| `find_text` | **按文字找可点击坐标**（首选定位方式） | query, exact |
| `click_relative` | 锚文字+偏移点击**无文字图标**（如头像在某文字右侧） | anchor_text, dx, dy |
| `zoom` | 某区域**原分辨率**放大，看清小字/图标 | x, y, w, h |
| `ocr_screen` | 识别屏幕全部文字 + 坐标 | 无 |
| `list_windows` / `get_active_window` | 列窗口 / 查前台窗口 | 无 |
| `activate_window` / `minimize_window` / `maximize_window` | 按标题操作窗口 | title |

**坐标系铁律**：所有坐标都基于 `screenshot` 返回的那张图的像素（左上角为原点）。
截图会告诉你画布尺寸（如 1280×720），你的 x/y 必须落在这个范围内。服务会自动
把它换算成真实屏幕坐标，**你不需要自己换算 DPI/缩放**。

## 操作流程（Procedure）

1. **先截图**：调用 `screenshot` 看清当前界面，确认坐标系尺寸。
2. **定位目标**：在图上找到要操作的元素，读出它中心点的像素坐标。
   - 若目标是**带文字的按钮/菜单/链接**，优先 `find_text("登录")` 直接拿到可点击坐标，比肉眼估坐标更准。
   - 先用 `list_windows` / `activate_window` 把目标程序窗口切到前台，再操作。
3. **执行一个动作**：`click` / `type_text` / `press_key` 等，一次只做一步。
4. **验证**：再 `screenshot`，确认界面如预期变化（按钮按下、文本出现、弹窗关闭）。
5. **循环**：未完成则回到第 2 步。

输入文本的标准姿势：
1. `click` 目标输入框获取焦点 → 2. 需要时 `press_key` `ctrl+a` 全选清空 →
3. `type_text` 输入内容 → 4. `press_key` `enter` 或 `tab` 提交/换焦点。

## 常见坑（Pitfalls）

- **不截图就点**：界面会变（弹窗、加载、布局位移），凭记忆点坐标极易点错。每个关键动作后都要复核。
- **坐标空间搞混**：必须用最近一次 `screenshot` 的画布尺寸，不要用真实分辨率数字。
- **没获取焦点就输入**：`type_text` 只往「当前光标处」输入，先 `click` 输入框。
- **动作太快**：页面/动画没加载完就操作会落空。**优先用 `wait_stable`（轮询到界面稳定即返回，比写死 `wait` 省时）**，或给会触发加载的 `click`/`press_key`/`tap`/`fill` 传 `settle=true`。
- **组合键写法**：用 `+` 连接，如 `ctrl+c`、`alt+f4`、`ctrl+shift+esc`；单键直接写 `enter`。
- **急停**：如果操作失控，把鼠标**甩到屏幕左上角**会触发 FAILSAFE 立即中止。
- **危险操作**：删除、提交订单、发送消息、关闭未保存窗口前，先截图确认，必要时向用户确认。
- **被安全护栏拦截**：`type_text` 输入疑似破坏命令、或 `press_key` 命中快捷键黑名单会被拦截并返回原因；**确认安全**后可对该次调用传 `force=true` 放行。
- **限速**：默认每分钟最多 120 个动作，触发上限说明操作太密，应放慢并多用 `find_text` 精准定位减少试错。

## 验证（Verification）

确认 MCP 服务可用：
- 调用 `get_screen_info`，应返回坐标空间与缩放比。
- 调用 `screenshot`，应返回一张当前屏幕的图。
若两者任一失败，检查 `computer-use` MCP 服务是否已在 Hermes 配置中启用、依赖是否装好。
