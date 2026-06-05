---
name: computer-use-orchestrator
description: 当任务可能需要"操作电脑"时（点击图形界面、操作没有 API 的桌面软件、跨应用搬运数据、或在网页/文件/命令之间做选择）先用本技能分诊：判断该不该用桌面控制、环境是否具备、用哪种方式最稳，然后再调用对应工具。是 computer-use 系列的入口与调度。
version: 0.1.0
platforms: [windows, macos, linux]
metadata:
  hermes:
    tags: [computer-use, routing, preflight, gui, automation]
  category: automation
---

# Computer Use 情景分诊（Orchestrator）

拿到任何"操作电脑"的任务，**先分诊，后动手**。目的：能用更稳的原生工具就不要瞎点；
环境不具备时引导用户搭好桌面，而不是闷头失败；动手前让用户知情。

## 何时使用（When to Use）

任务里出现"帮我点 / 在某软件里操作 / 把 A 的数据填到 B / 自动化某界面 / 截图看看屏幕"
等需要与电脑交互的诉求时，**第一步先用本技能**，再决定后续。

## 第一步：选对工具层（别一上来就点鼠标）

| 任务目标 | 首选方式 | 原因 |
|---|---|---|
| 网页操作（可走浏览器） | **Hermes 自带浏览器工具** | 基于 DOM，更快更稳；除非站点反自动化或必须真实点击 |
| 读写文件 / 跑命令 | **Hermes 自带 terminal / 文件工具** | 直接、可靠，无需视觉 |
| **无 API 的桌面软件 / 跨应用 GUI** | **computer-use 桌面控制** | 只有这种才值得用截图+鼠标键盘 |

> 判断不了就问自己：这件事有没有命令行/API/浏览器能直接做？有就别用桌面控制。

## 第二步：环境自检（确认能不能用）

1. 优先调用 `check_environment`（若可用），拿到：操作系统、**截图是否成功(=有无 GUI)**、
   屏幕尺寸/缩放、OCR 是否可用、窗口管理是否可用。
   - 若没有该工具，则调用 `get_screen_info` 替代：能正常返回≈有 GUI；报错≈无 GUI。
2. 按结果分支：

   - **没有 GUI（截图/几何获取失败）**：不要硬点。告知用户「当前环境没有可操作的图形桌面」，
     并给出选项：装虚拟显示(Xvfb)、用虚拟机、或 Windows Sandbox / Docker(noVNC)。等用户就绪再继续。
   - **有 GUI，但是用户的主桌面**：先**知会用户**——「接下来我会接管这台电脑的鼠标键盘，
     期间请勿手动操作；要中止可把鼠标甩到屏幕左上角触发急停」。若用户不希望被打扰，
     建议改用隔离桌面（VM / Sandbox / Docker）。
   - **macOS 且点击/截图疑似无效**：提示用户到 系统设置 → 隐私与安全性，
     给终端授权 **辅助功能(Accessibility)** 和 **屏幕录制(Screen Recording)**。
   - **任务需要"按文字定位"但 OCR 不可用**：提示安装 `pip install "hermes-computer-use[ocr]"`；
     未装则退化为纯坐标点击（靠截图肉眼定位）。

## 第三步：执行（交给 desktop-automation 闭环）

进入"截图 → 操作一步 → 再截图验证"的闭环（详见 desktop-automation 技能）。多窗口时先
`list_windows` / `activate_window` 把目标程序切到前台。

### 定位与理解：OCR 与 vision_analyze 分工（关键）

二者**不是二选一，而是分工组合**——各自擅长不同的事：

| 需求 | 用哪个 | 为什么 |
|---|---|---|
| **点击某个文字控件**（按钮/菜单/链接） | **OCR `find_text`** | 给出可直接 click 的**精确坐标**，本地、便宜、确定；VLM 报坐标普遍不准 |
| **理解屏幕 / 判断状态 / 找图标按钮 / 处理歧义 / 核对复杂结果** | **`vision_analyze`** | 语义理解是 OCR 给不了的（图标、颜色、布局、报错弹窗…） |

**推荐串起来用：**
```
vision_analyze 判断"现在该点登录"     ← 语义决策（VLM 擅长）
        ↓
find_text("登录") 拿到精确坐标         ← 精确定位（OCR 擅长）
        ↓
click(x, y)                            ← 执行
        ↓
vision_analyze 核对"是否登录成功/有无报错"  ← 复杂状态判断
```

注意：`screenshot` 已把原图直接回传给主模型，主模型本身就"看得见"屏幕。因此每一步都用
`vision_analyze` 分析整张图**很烧 token**——能用 `find_text` 廉价定位的，就别动用视觉分析。

## 平台差异（Platform Notes）

- **Windows**：开箱即用；注意锁屏/息屏会中断；DPI 已自动对齐。
- **macOS**：必须先授权辅助功能 + 屏幕录制，否则操作静默失败。
- **Linux**：需要 X11 显示（DISPLAY 已设）；**Wayland 默认禁止合成输入**，
  需切到 X11 会话或使用 Xvfb 虚拟显示。

## 常见坑（Pitfalls）

- 该用浏览器/命令行的活却去点鼠标 → 慢且脆，先回到"第一步"重判。
- 无 GUI 还硬调点击 → 必然失败，应先引导用户准备桌面。
- 在用户主桌面默默接管 → 体验差，**动手前一定先知会**。
- 每步都 `vision_analyze` 整屏 → 烧 token，定位优先 `find_text`。
- 忽视平台权限/显示要求（macOS 授权、Linux Wayland）→ 排查半天。

## 验证（Verification）

- `check_environment`（或 `get_screen_info`）能返回 → 环境就绪。
- 截图成功 + `find_text` 能定位到目标文字 → 可进入操作闭环。
