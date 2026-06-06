# SOM / UI 元素检测 接入选型（调研稿）

> 目的：评估是否给 computer-use 接入「Set-of-Mark（截图里所有可点元素自动框选+编号，模型按 #N 点）」，
> 给出方案对比、硬件/许可/耗时代价与推荐。**调研性质，确认后再实施。**

## 1. 先厘清：SOM 到底补哪块缺口（别高估）

我们现有的「定位」手段已覆盖大部分：

| 场景 | 现有手段 | 效果 |
|---|---|---|
| Windows 原生控件 | **UIA**（winuia.inspect / targets，含 bbox+name+类型+交互性）| ✅ 等于"免费的 SOM" |
| 任意文字/按钮 | **OCR**（find_text / click_relative）| ✅ 文字类很稳 |
| 网页内元素 | **浏览器 DOM 工具**（aria-label/role）| ✅ 路由硬规则已就位 |
| **自绘 UI / CEF canvas / 游戏 / 无文字图标且无 UIA** | ❌ 仅 click_relative 勉强缓解 | **← SOM 真正补的就是这一类** |

> 结论：**SOM 只补"最后一类硬骨头"**（不暴露 UIA、又没文字的元素），不是主路。
> 评估它值不值，要按"你实际有多少这类目标程序"来定。

## 2. 本机硬件（影响可行性）

- GPU：**NVIDIA RTX 5070 / 12GB VRAM**，`nvidia-smi` 正常 → 重模型(OmniParser V2)可跑。
- 注意：5070 是 Blackwell(sm_120)，需较新的 CUDA/PyTorch(cu12.x) 才支持。
- 但**跨平台分发不能假设有 GPU**——多数用户是 CPU。

## 3. 方案对比

| 方案 | 输出 | 依赖/体积 | 硬件 | 单帧耗时 | 许可 | 与本栈契合 |
|---|---|---|---|---|---|---|
| **A. OmniParser V2**(YOLOv8检测 + Florence-2 描述) | bbox + 是否可交互 + 文字描述 | torch+transformers+ultralytics，模型 ~1GB+ | GPU≥8GB(舒适)，CPU 可但慢 | GPU 0.6–0.8s / **CPU 8–24s** | icon_detect **AGPL** / caption MIT | 重（torch 生态），与轻量 ONNX 栈不一致 |
| **B. 轻量 YOLO-ONNX 仅检测**(无描述) | bbox（编号给模型自己看图判断）| onnxruntime + 1 个 yolo.onnx ~数十 MB | **CPU 可**(~200–500ms) | CPU 0.2–0.5s | 取决于所选检测模型权重 | ✅ 高（复用现有 onnxruntime/RapidOCR 同栈）|
| **C. 大型 grounding VLM**(UGround / OS-Atlas, 7B+) | 直接出点击坐标 | 巨型权重(数 GB~十几 GB) | 大显存 GPU | 慢、重 | 各异 | ❌ 研究级，过重 |
| **D. 云 API**(如 Replicate 跑 OmniParser) | 同 A | 本地零依赖 | 无 | 网络往返 | 服务条款 | ❌ 需联网+按次计费+**截图外传(隐私)**，违背本地优先 |
| **E. 不做**(维持 UIA+OCR+浏览器+click_relative) | — | 0 | — | — | — | ✅ 覆盖~90%，自绘类仍弱 |

## 4. 推荐

**分层、可选、slot 进现有 `targets`：**

1. **默认不变**：UIA + OCR + 浏览器路由 已覆盖绝大多数，保持轻量。
2. **SOM 做成可选 `[som]` 扩展**，作为 `targets` 的**第三个来源 `detector`**（与现有 uia/ocr 并列），
   并可返回一张 **SoM 标注截图**（框+编号）供模型按 #N 操作——**直接复用现有 `tap`/`fill`**（按编号→坐标）。
3. 引擎二选一（按硬件）：
   - **有 GPU → 方案 A OmniParser V2**（能力最强，带交互性+描述）；
   - **无 GPU → 方案 B 轻量 YOLO-ONNX 仅检测**（CPU 可用，无描述，靠模型看标注图判断）。
4. **优先级：中期**，且**建议"按需触发"**——仅当 `targets` 的 UIA/OCR 来源在某窗口枚举为空
   （典型自绘/CEF）时，才提示可启用 detector，避免每步都付检测开销。

## 5. 接入设计（确认后实施）

```
targets(source="auto"):
   uia(原生) → 空? → ocr(文字) → 空/不足? → detector(SOM, 需[som]) → 编号目标
som.py:
   detect(image) -> [boxes];  可选 caption;  draw_marks(image,boxes) -> 标注PNG
   坐标全部 view 空间，编号塞进现有 Target 结构
新增工具(可选)：marked_screenshot()  返回带编号的 SoM 截图
```
- 复用：`targets`/`tap`/`fill` 编号体系、view 坐标契约、safety 护栏。
- 新增：`som.py`（检测引擎封装）、`[som]` 可选依赖、`HCU_SOM`/`HCU_SOM_ENGINE` 开关。

## 6. 风险

- **许可**：OmniParser icon_detect 为 **AGPL** → 随仓库分发权重有传染风险。
  规避：不内置权重，让用户自行下载/接受；或方案 B 选 MIT/Apache 的检测器。
- **GPU/环境**：方案 A 需 torch+CUDA；5070(sm_120) 需新版 torch，安装可能折腾。
- **体积/耗时**：A 加 ~GB 依赖、每步 +0.6s；B 轻但仅 bbox 无语义。
- **维护**：多一条重链路，跨平台测试成本上升。

## 7. 工作量评估

- **方案 B（轻量 ONNX）**：~1–2 天（选/接一个 UI 检测 onnx + targets 第三来源 + 标注图）。
- **方案 A（OmniParser 全量）**：~2–3 天（torch/CUDA 环境 + 管线 + 可选 extra + 标注图），含 5070 环境调试。

## 8. 待你拍板

- **要不要做**？（考虑你实际遇到的"自绘/无UIA"程序多不多）
- 若做，**走 A（你有 5070，能力最强）还是先 B（轻、可分发）**？
- 还是**先搁置**，等真出现 UIA/OCR 都搞不定的目标程序再启用。
