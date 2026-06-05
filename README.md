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
# 在项目根目录
pip install -e .
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

| 工具 | 作用 |
|---|---|
| `screenshot` | 截当前主屏（返回图片 + 坐标系尺寸） |
| `get_screen_info` | 坐标空间 / 真实分辨率 / 缩放比 |
| `move_mouse` / `click` / `double_click` / `right_click` | 鼠标移动与点击 |
| `drag` | 拖拽（拖动 / 框选 / 滑块） |
| `scroll` | 滚轮（正=上，负=下） |
| `type_text` | 在焦点处输入文本 |
| `press_key` | 按键 / 组合键（`enter`、`ctrl+c`…） |
| `cursor_position` / `wait` | 查光标位置 / 等待加载 |

**坐标系**：所有坐标基于 `screenshot` 返回图片的像素（左上角原点）。服务自动处理 DPI 与缩放，模型无需自己换算。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `HCU_MAX_WIDTH` | `1280` | 截图最大宽度；屏幕更宽时按比例降采样（省 token、提精度）。`0`=不缩放 |
| `HCU_FAILSAFE` | `true` | 鼠标甩到屏幕左上角立即急停 |
| `HCU_PAUSE` | `0.1` | 每个动作后的固定停顿（秒） |
| `HCU_TYPING_INTERVAL` | `0.0` | 逐字符输入间隔（秒），丢字就调大 |
| `HCU_MAX_ACTION_DELAY` | `30` | `wait` 工具允许的最大秒数 |

## 安全须知

- 这些工具会**真实操作你的电脑**。请在你掌控的机器上使用。
- 保留 `HCU_FAILSAFE=true`：失控时把鼠标甩到**屏幕左上角**即可中止。
- 删除、提交、发送等不可逆操作前，建议让 Hermes 先截图确认、必要时向你二次确认。

## 当前限制（MVP）

- 仅操作**主显示器**（多屏支持待加）。
- 纯坐标点击（基于视觉）；Windows 下后续可选接入 UI Automation 做更稳的「按元素」操作。
- 浏览器/文件/命令行复用 Hermes 自带工具，本项目不重复造。

## 许可证

MIT
