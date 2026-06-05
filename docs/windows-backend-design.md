# Windows 原生桌面控制后端 — 设计文档（v0.3 草案）

> 状态：**待确认**。确认后再落代码。

## 1. 目标与定位

补齐 Hermes 在 **Windows** 的空白：Hermes 官方 Computer Use 只支持 macOS（cua-driver，
用 Apple 私有 SPI），Windows/Linux 不支持、只能让用户「改用浏览器工具」兜底。本后端做
Windows 的对应物，目标四点：

1. **不抢鼠标/焦点**：操作主机此刻开着的程序，不移动用户的物理光标、不强夺焦点。
2. **可观测**：虽无"第二个真实光标"，但操作时高亮被作用元素 + 前后截图，能看清它在干嘛。
3. **不怕不通用**：UIA 不灵时按梯子回退，最坏退到视觉坐标 / VM。
4. **模型只学一套**：统一「编号目标」接口，UIA 与 视觉 两种来源对模型透明。

与现有**视觉坐标后端**（desktop.py，pyautogui 移动光标）**并存**，由 orchestrator 分诊二选一。

## 2. 总体架构

```
模型(Hermes)
   │  统一工具：targets / tap / fill / shot
   ▼
┌─────────────── 统一目标层 (targets.py) ───────────────┐
│  Target{id, source, name, control_type, rect, center, │
│         actions}  ← 给每个可操作元素编号(SOM)          │
│  执行回退梯子：UIA → 消息坐标 → 视觉坐标 → 建议VM      │
└───────────┬───────────────────────────┬───────────────┘
            ▼                           ▼
   UIA Provider (winuia.py)     Vision Provider (复用)
   pywinauto/UIA·不抢光标        ocr.py + desktop.py
            │                           │
            ▼                           ▼
       Windows 原生控件            任意像素界面(兜底)
```

复用：`ocr.py`(找文字)、`desktop.py`(视觉坐标点击)、`window.py`(列窗口)、
`safety.py`(限速/危险拦截)、`environment.py`(平台探测)、`orchestrator` 分诊。

## 3. 模块划分

| 模块 | 职责 | 新/复用 |
|---|---|---|
| `winuia.py` | UIA Provider：连接窗口、枚举控件、invoke/set_value、后台截图、draw_outline 高亮 | 新 |
| `overlay.py` | **"假鼠标"指针覆盖层** + 高亮反馈（置顶·点击穿透·不夺焦的纯视觉提示） | 新 |
| `targets.py` | 统一目标抽象：聚合 UIA/视觉来源、编号、执行回退梯子 | 新 |
| `desktop.py` | 视觉坐标点击/截图（梯子第③层兜底） | 复用 |
| `ocr.py` | 文字定位（视觉来源的目标） | 复用 |
| `window.py` `safety.py` `environment.py` | 列窗口 / 安全 / 平台探测 | 复用 |
| `server.py` | 注册新工具 | 改 |

## 4. 数据结构：Target

```python
Target = {
  "id": 5,                     # 编号(SOM)，模型按号操作
  "source": "uia" | "ocr",     # 目标来源
  "name": "登录",              # 控件名/识别到的文字
  "control_type": "Button",    # 仅 UIA 来源有
  "rect": [l, t, r, b],        # 屏幕坐标
  "center": [x, y],            # view 坐标(回退到坐标点击时用)
  "actions": ["invoke", "set_text"],  # 该目标支持的动作
}
```

## 5. 工具清单（MCP）

**统一接口（推荐模型优先用）**
| 工具 | 作用 |
|---|---|
| `targets(title="", refresh=true)` | 枚举窗口(或全屏)的**编号目标**，UIA 优先、缺则用 OCR |
| `tap(title, id)` | 点击/激活编号目标（内部走回退梯子 + 高亮） |
| `fill(title, id, text, force=false)` | 往编号目标填文本（无光标；危险文本拦截，可 force） |
| `shot(title="")` | 截图：给了 title 截该窗口(后台 PrintWindow)，否则全屏 |

**底层 UIA（调试/高级，可直接用）**
| 工具 | 作用 |
|---|---|
| `win_list_apps()` | 列可连接的顶层窗口 |
| `win_inspect(title, control_type="", max_items=200)` | 导出原始控件树(编号+名称+类型+automation_id+rect) |
| `win_invoke(title, name="", index=-1, control_type="")` | 按名/号无光标调用控件 |
| `win_set_text(title, text, name="", index=-1, force=false)` | 按名/号无光标填值 |
| `win_capture(title)` | 后台单窗口截图 |

## 6. 回退梯子（targets.tap / targets.fill 内部）

对一个 Target 执行 action，依次尝试，命中即停：

1. **UIA 模式调用**（无光标）：`invoke()` / `set_value()` / `toggle()` / `select()`。
2. **窗口内消息坐标点击**（无光标）：用 Win32 `PostMessage(WM_LBUTTONDOWN/UP)` 发到目标
   窗口的相对坐标（对响应消息但无 UIA 的旧控件有效）。
3. **视觉坐标·前台点击**（复用 `desktop.py`，**会移动光标**）：先 `activate_window` 再
   `click(center)`。**此层会抢鼠标，执行前由 orchestrator 知会用户**。
4. **仍失败** → 报错并建议改用 **VM 可视操作**（游戏/DirectInput/纯自绘）。

每层执行前 `winuia.draw_outline()` 高亮目标；每个动作经 `safety.gate()` 限速；
`fill` 经 `safety.check_text()` 危险文本拦截。

## 7. 可观测（"假鼠标" + 高亮，替代真实第二光标）

真实第二光标拿不到，但用三层**纯视觉反馈**让用户"看见它在操作"——其中第①层把"看着光标移过去"的体验补回来：

1. **假鼠标指针覆盖层（overlay.py）**：一个**置顶、点击穿透、不夺焦**的透明窗口，上面画一个
   **假的鼠标指针图标**。每次要操作某目标前，让这个假指针从上一位置**平滑移动到目标元素中心**，
   到位后做一个"点击"脉冲动画。**它不拦截任何输入、不是真光标、不真的点**，纯粹告诉用户
   "它正在点这里"。真实操作仍由 UIA 在后台完成，用户自己的真光标完全不受影响。
2. **红框高亮**：到位后对目标 `draw_outline()` 画红框（pywinauto 内置），进一步确认作用对象。
3. **前后截图**：`tap/fill` 可选返回操作前后的 `win_capture`，界面变化一目了然。

> 效果：用户体验回到"看着一个光标移过去、点下去"，但全程**不占用真鼠标**。

**实现要点（overlay.py）**
- 窗口扩展样式 `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE`
  （点击穿透 + 置顶 + 不抢焦点）；用 Tkinter(`-transparentcolor`) 或 win32 分层窗口实现，
  **Tkinter 为 Python 标准库、无新依赖**。
- 假指针在**真实屏幕坐标(physical)** 移动；overlay 设为 DPI-aware，直接用 UIA 的屏幕 rect
  作为目标位置（与 desktop.py 的 view/logical 换算解耦，避免错位）。
- 在**独立线程/进程**里跑（拥有自己的 Tk 主循环），通过坐标队列接收"移动到 (x,y)"指令，
  不阻塞 MCP server 的 stdio 循环；动画用分步插值（~150–300ms 移动 + 脉冲）。
- 开关：`HCU_OVERLAY=on|off`（默认 on）；无 GUI 或不需要时自动关闭。降级失败不影响真实操作。

## 8. 与 orchestrator / check_environment 集成

- `check_environment` 已报 `ecosystem=Windows`、`in_container`、GUI 状态。
- orchestrator「选择执行环境」分支细化：
  - Windows 原生程序 + 用户不想被抢鼠标 → **优先 `targets`/`tap`/`fill`（UIA）**；
  - UIA 不灵 → 自动回退梯子；到第③层(视觉坐标)前**知会用户会占用鼠标**；
  - 游戏/DirectInput/纯自绘 → 直接建议 **VM 可视操作**。
- 统一编号目标 = Hermes 浏览器工具 `@e1/@e2` 同范式，模型迁移成本低。

## 9. 依赖

- 可选附加：`[winuia] = ["pywinauto>=0.6.8"]`（带 comtypes + pywin32），**仅 Windows**。
- 非 Windows 或未安装 → 工具返回友好提示（不崩溃），自动只用视觉来源。
- 基础安装不变，不增加默认体积。

## 10. 安全

- `tap`/`fill`/`win_invoke`/`win_set_text` 经 `safety.gate()` 限速。
- `fill`/`win_set_text` 经 `safety.check_text()` 拦截危险命令文本（可 `force`）。
- **不提供**关闭窗口/系统级危险操作工具。
- `draw_outline`/`inspect`/`capture` 只读，不改状态。

## 11. 测试计划

- **非破坏性冒烟**（进 CI）：`is_supported`、`win_list_apps` 返回列表、对前台窗口
  `win_inspect` 返回列表、`win_capture` 返回合法 PNG、`targets` 返回带编号列表。
- **受控功能验证**（手动一次）：用 **记事本** 验证闭环——
  开 notepad → `fill` 写入文本 → 读回校验 → **记录操作前后鼠标坐标，断言未变（证明不抢鼠标）**
  → `taskkill` 关闭（避免保存弹窗）。
- 破坏性动作不进默认测试。

## 12. 已知限制

- 游戏 / DirectInput / 纯自绘 UI / 不响应合成消息的程序 → 元素级与消息层都不灵，回退视觉或 VM。
- 无真实"第二光标"（用高亮 + 截图替代可观测）。
- UIA 枚举超大窗口可能慢 → 深度/数量上限、按 `control_type` 过滤。
- 目前主显示器、单窗口连接；多窗口/多屏后续。

## 13. 里程碑（建议分步落地）

- **M1（✅ 已完成）**：`winuia.py` 基础 + `win_inspect`/`win_capture`/`win_invoke`/`win_set_text`，
  `overlay.py` 假鼠标指针 + `draw_outline` 高亮。已验证「运行对话框 UIA 填字、真实光标未动」。
- **M2（✅ 已完成）**：`targets.py` 统一编号目标 + `targets`/`tap`/`fill` + 回退梯子
  （UIA无光标 → 消息坐标 → 视觉坐标）。已验证 targets.fill 经 UIA 成功、鼠标未动。
- **M3（✅ 基本完成）**：✅ 消息坐标中间层(`message_click`)、✅ Electron/Chromium 无障碍唤醒
  (`wake_accessibility`)、✅ 多窗口(按标题连接，含后台窗口)、✅ **多显示器**(opt-in
  `HCU_MULTI_MONITOR`，虚拟桌面截图+跨屏坐标，已验证双屏几何/坐标)；🔲 性能优化(大窗口枚举)、
  🔲 混合 DPI 多屏精确化。
```
