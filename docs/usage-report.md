# Computer Use 调用报告

> 记录本项目 computer-use 能力的调用方式与两个真实任务的执行流程、性能数据。
> **所有涉及隐私的具体内容（平台名/账号/IMEI/门店/机型明细）均已脱敏，用占位符代替。**

## 1. 能力概览（v0.4.3，33 个 MCP 工具）

| 分组 | 工具 |
|---|---|
| 视觉/信息 | `screenshot`、`zoom`(区域原分辨率)、`get_screen_info`、`check_environment` |
| OCR 定位 | `ocr_screen`、`find_text`、`click_relative`(锚文字+偏移) |
| 鼠标/键盘 | `move_mouse`/`click`/`double_click`/`right_click`/`drag`/`scroll`/`type_text`/`press_key`/`cursor_position` |
| 等待 | `wait`、`wait_stable`(轮询到界面稳定) |
| 窗口 | `list_windows`/`get_active_window`/`activate`/`minimize`/`maximize` |
| 统一编号目标 | `targets`/`tap`/`tap_until`/`fill` |
| Windows 元素级(UIA·不抢鼠标) | `win_list_apps`/`win_inspect`/`win_invoke`/`win_set_text`/`win_capture`/`win_wake_accessibility` |

**两套后端 + 分诊**：视觉坐标（会移动光标）与 Windows UIA 元素级（不抢鼠标）并存，由
`computer-use-orchestrator` 技能按"目标软件×平台"路由；网页则硬规则导向浏览器 DOM 工具。

## 2. 典型调用闭环

```
check_environment        → 探明 OS/GUI/OCR/平台
screenshot / win_inspect → 看清当前界面 / 拿控件树
find_text / targets      → 定位目标（文字 or 编号控件）
click / tap / fill        → 执行（优先 UIA 无光标，回退视觉坐标）
wait_stable / tap_until   → 轮询到界面稳定/预期文字出现
screenshot               → 复核结果
```

## 3. 实战案例（已脱敏）

### 案例 A：网页内退出登录（某网页平台）

| 步骤 | 调用 | 说明 |
|---|---|---|
| 1 | `screenshot`(多屏) | 发现目标网页开在副屏某浏览器(InPrivate) |
| 2 | 单独抓副屏 + `zoom` | 整屏降采样看不清，放大读顶栏 |
| 3 | OCR 定位锚文字 → 推算头像位置 | 账号头像是**图标无文字**，靠"锚文字右侧偏移" |
| 4 | `click` 头像 | 弹出账号下拉菜单 |
| 5 | `find_text`("Logout") → `click` | OCR 拿精确坐标点击退出 |
| 6 | `screenshot` 复核 | 头像消失 + 跳转公开页 → 确认已登出 |

**复盘教训**：网页内操作用纯视觉**更脆**（坐标不确定、首次点击未生效需重试、图标难定位）。
→ 已转化为优化：`click_relative`(图标定位)、全分辨率 OCR、**浏览器窗口🌐路由提示 + 硬规则**(优先 DOM 工具)。

### 案例 B：桌面 ERP 搜索（某门店管理桌面客户端，CEF）

| 步骤 | 调用 | 说明 |
|---|---|---|
| 1 | `list_windows`/`win_list_apps` | 定位客户端窗口（主屏） |
| 2 | `activate` + `win_inspect` | 激活 + UIA 枚举控件树，找到搜索栏位置 |
| 3 | `click` 搜索栏 + `type_text`(查询) + `press_key` enter | 搜索栏是 CEF 输入、UIA 未暴露为 Edit → 点击聚焦+键入 |
| 4 | 抓窗口区域 + `ocr_screen` | CEF 用直接抓屏(避 PrintWindow 黑屏)，OCR 读结果 |

**结果**：返回 1 条匹配记录（机型 / IMEI / 成本/零售价 / 库存状态等字段——**此处脱敏**）。

**计时数据（端到端 4.86s）**：
| 步骤 | 耗时 | 类型 |
|---|---:|---|
| 冷导入依赖 | 159 ms | 处理(一次性) |
| 定位窗口 | 1.3 ms | 处理 |
| 激活窗口 | 0.2 ms | 处理 |
| 等待前台稳定 | 600 ms | ⏳固定等待 |
| UIA 枚举控件(49个) | 724 ms | 处理 |
| 点击搜索栏 | 105 ms | 处理 |
| 清空+键入查询 | 406 ms | 处理 |
| 回车 | 101 ms | 处理 |
| 等待结果加载 | 2000 ms | ⏳固定等待 |
| 截图窗口区域 | 7 ms | 处理 |
| OCR 引擎初始化 | 301 ms | 处理(一次性) |
| OCR 识别 | 452 ms | 处理 |
| **真实处理合计** | **2.26 s** | |
| **固定等待合计** | **2.60 s** | 可优化 |
| **端到端** | **4.86 s** | |

> 注：以上为**脚本层自动化耗时**。Agent 实际墙钟时间更长——每步之间还有模型"看图→决策→下一步"的往返。

## 4. 性能优化数据

| 优化 | 效果 |
|---|---|
| 全分辨率 OCR | 同屏识别段数 **83 → 194（≈2.3x）**，小字可读 |
| `wait_stable` 替代固定 wait | 界面已稳时 **2.0s → 0.47s**（单次省 ~1.5s） |
| UIA 元素级 vs 视觉坐标 | 元素级有明确成败、不抢鼠标，标准控件更可靠 |

## 5. 已知短板与进度

详见 [windows-backend-design.md §14](windows-backend-design.md) 与 [som-integration-design.md](som-integration-design.md)：
- ✅ 已落地：全分辨率 OCR、浏览器路由提示、`wait_stable`/`settle`/`tap_until`、`click_relative`、`zoom`
- 🔲 中期待定：SOM/UI 元素检测（补"自绘/无 UIA 且无文字"这类，性价比待评估，已出选型稿）

---
*本报告所有真实业务/账号数据均已脱敏，仅保留流程与性能指标。*
