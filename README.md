# hermes-computer-use

适配 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的**跨平台 Computer Use（通用桌面控制）**能力，让 Hermes 能像人一样「看屏幕 + 操作鼠标键盘」，从而操作任何**没有 API 的桌面软件**。

采用 **MCP Server + Skill** 双层架构：

```
┌──────────────────────────────────────────────┐
│              Hermes Agent (视觉LLM)           │
└──────────────┬──────────────────┬─────────────┘
        MCP协议 │                  │ Skill(markdown)
   ┌────────────▼─────────┐   ┌────▼────────────────┐
   │ computer-use MCP     │   │ desktop-automation  │
   │ 截图/点击/输入/滚动/  │   │ SKILL.md            │
   │ 拖拽 …（原子能力）    │   │ 教模型「截图→操作   │
   │ mss + pyautogui      │   │ →验证」闭环         │
   └──────────┬───────────┘   └─────────────────────┘
              ▼
       桌面 / 任意应用（Windows / macOS / Linux）
```

- **MCP Server**（`src/hermes_computer_use/`）：向 Hermes 暴露原子级桌面操作工具。
- **Skill**（`skills/desktop-automation/SKILL.md`）：教 Hermes 何时用、怎么用这些工具。

> 文件/命令行、浏览器自动化，Hermes **自带工具**已基本覆盖；本项目专注补齐它缺失的**通用桌面控制**核心。

## 前提条件

- Python ≥ 3.10
- Hermes 接入的是**支持视觉（读图）的模型**（如 GPT-4o / Claude / Qwen-VL），否则它「看不见」屏幕。
- 一个有图形桌面的真实/虚拟机器（无头服务器需配虚拟显示）。
- Linux 额外需要：`scrot`、`python3-xlib` 等（pyautogui 依赖）。

## 安装

```powershell
# 在项目根目录（基础功能：截图 + 鼠标键盘 + 窗口管理 + 安全护栏）
pip install -e .

# 如需 OCR（按文字定位/点击，含 onnxruntime，体积较大）：
pip install -e ".[ocr]"

# 如需 Windows 原生「元素级」后端（UIA，操作主机程序不抢鼠标，仅 Windows）：
pip install -e ".[winuia]"
```

## 接入 Hermes

### 1) 注册 MCP 服务

把 [`examples/hermes-config.yaml`](examples/hermes-config.yaml) 的片段合并进 Hermes 配置文件：

- Linux/macOS：`~/.hermes/config.yaml`
- Windows：`%LOCALAPPDATA%\hermes\config.yaml`

改完在 Hermes 里执行 `/reload-mcp`（或重启）。

### 2) 安装 Skill

把技能目录复制到 Hermes 的 skills 目录：

```powershell
# Windows
Copy-Item -Recurse skills\desktop-automation "$env:USERPROFILE\.hermes\skills\desktop-automation"
```

```bash
# Linux/macOS
cp -r skills/desktop-automation ~/.hermes/skills/desktop-automation
```

之后让 Hermes 做需要操作界面的任务时，它会自动加载该技能并使用 computer-use 工具。

## 工具清单

**统一「编号目标」入口（推荐）** —— 一套接口，UIA/OCR 两种来源透明，执行自动回退
| 工具 | 作用 |
|---|---|
| `targets` | 枚举可操作目标并**编号**：Windows 窗口优先 UIA 控件(不抢鼠标)，否则 OCR 文字 |
| `tap` | 点击 #编号目标，自动回退 **UIA无光标 → 消息坐标 → 视觉坐标** |
| `fill` | 往 #编号目标填文本，优先 UIA 无光标（含危险文本拦截） |

**视觉 / 信息**
| 工具 | 作用 |
|---|---|
| `screenshot` | 截当前主屏（返回图片 + 坐标系尺寸） |
| `get_screen_info` | 坐标空间 / 真实分辨率 / 缩放比 |
| `check_environment` | 环境自检：OS / GUI 是否可用 / OCR / 窗口管理 / 安全配置 + 结论 |

**OCR（需 `[ocr]` 依赖）** —— 按文字定位，比纯猜坐标更稳
| 工具 | 作用 |
|---|---|
| `ocr_screen` | 识别屏幕全部文字 + 中心坐标（可直接 click） |
| `find_text` | 查找指定文字，返回可点击坐标（如 `find_text("登录")`） |

**鼠标 / 键盘**
| 工具 | 作用 |
|---|---|
| `move_mouse` / `click` / `double_click` / `right_click` | 鼠标移动与点击 |
| `drag` | 拖拽（拖动 / 框选 / 滑块） |
| `scroll` | 滚轮（正=上，负=下） |
| `type_text` | 在焦点处输入文本（含危险命令拦截，可 `force`） |
| `press_key` | 按键 / 组合键（`enter`、`ctrl+c`…，黑名单拦截，可 `force`） |
| `cursor_position` / `wait` | 查光标位置 / 等待加载 |

**窗口管理**
| 工具 | 作用 |
|---|---|
| `list_windows` / `get_active_window` | 列出窗口 / 查前台窗口 |
| `activate_window` / `minimize_window` / `maximize_window` | 按标题激活 / 最小化 / 最大化 |

**Windows 原生·元素级（需 `[winuia]`，仅 Windows）** —— 操作主机程序**不抢鼠标**
| 工具 | 作用 |
|---|---|
| `win_list_apps` | 列出可连接的顶层窗口 |
| `win_inspect` | 枚举窗口控件并**编号**（供按 #号操作） |
| `win_invoke` | 无光标调用控件（点按钮/菜单/勾选） |
| `win_set_text` | 无光标往输入框填文本（含危险文本拦截） |
| `win_capture` | 后台截取指定窗口（PrintWindow） |
| `win_wake_accessibility` | 唤醒 Chromium/Electron 程序的无障碍树（之后才能枚举其控件） |

> 对标 Hermes macOS cua-driver，填 Windows 空白：通过 UI Automation 按元素操作 + 后台截图，
> **不移动你的真鼠标、不抢焦点**；操作时「假鼠标」滑到目标 + 红框高亮，仍可观测。
> 不暴露 UIA 的程序（游戏/自绘/部分 Electron）需回退视觉坐标或 VM。

**坐标系**：所有坐标基于 `screenshot`（与 OCR）返回的像素（左上角原点）。服务自动处理 DPI 与缩放，模型无需自己换算。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `HCU_MAX_WIDTH` | `1280` | 截图最大宽度；屏幕更宽时按比例降采样（省 token、提精度）。`0`=不缩放 |
| `HCU_OCR_FULLRES` | `true` | OCR 在原始分辨率图上识别（小字更准），坐标映射回 view；`false` 则在降采样图上跑（更快） |
| `HCU_FAILSAFE` | `true` | 鼠标甩到屏幕左上角立即急停 |
| `HCU_PAUSE` | `0.1` | 每个动作后的固定停顿（秒） |
| `HCU_TYPING_INTERVAL` | `0.0` | 逐字符输入间隔（秒），丢字就调大 |
| `HCU_MAX_ACTION_DELAY` | `30` | `wait` 工具允许的最大秒数 |
| `HCU_SAFETY` | `true` | 安全护栏总开关，`false` 关闭以下全部检查 |
| `HCU_RATE_LIMIT` | `120` | 每分钟动作上限，防失控循环；`0`=不限 |
| `HCU_BLOCK_DANGEROUS_TEXT` | `true` | 拦截疑似破坏性命令的输入文本（rm -rf、DROP TABLE…） |
| `HCU_BLOCKED_HOTKEYS` | `ctrl+alt+delete` | 危险快捷键黑名单，逗号分隔 |
| `HCU_OVERLAY` | `true` | Windows 元素级操作时的「假鼠标」指针覆盖层（纯视觉提示）开关 |
| `HCU_MULTI_MONITOR` | `false` | 实验性：开启后截图覆盖整个虚拟桌面、坐标跨屏；默认仅主屏 |

## 安全须知

- 这些工具会**真实操作你的电脑**。请在你掌控的机器上使用。
- 保留 `HCU_FAILSAFE=true`：失控时把鼠标甩到**屏幕左上角**即可中止。
- 内置安全护栏：**动作限速**（默认 120/分）、**危险输入文本拦截**（rm -rf / DROP TABLE 等）、**危险快捷键黑名单**。确认安全的单次操作可在 `type_text` / `press_key` 传 `force=true` 放行。
- 删除、提交、发送等不可逆操作前，建议让 Hermes 先截图确认、必要时向你二次确认。

## 当前限制（MVP）

- 默认仅操作**主显示器**；多屏可 `HCU_MULTI_MONITOR=true` 开启（实验性，跨屏截图+坐标；混合 DPI 下可能有偏差）。
- OCR 运行在降采样后的视图截图上，极小字体可能漏识；必要时把 `HCU_MAX_WIDTH` 调大或设 0。
- 窗口管理依赖 pygetwindow，Windows 功能完整，macOS/Linux 支持有限（不支持时工具会返回提示）。
- 浏览器/文件/命令行复用 Hermes 自带工具，本项目不重复造。

## 许可证

MIT
