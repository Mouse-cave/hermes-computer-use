"""
屏幕 OCR：识别屏幕上的文字及其坐标，让模型可以「按文字点击」而非纯猜坐标。

基于 RapidOCR（onnxruntime），中英文开箱即用，纯 pip 安装、无需系统级依赖。
OCR 跑在「模型视图(view)」空间的截图上，因此返回坐标可**直接用于 click**。

属可选依赖，未安装时调用相关工具会得到清晰的安装提示：
    pip install "hermes-computer-use[ocr]"
"""

from __future__ import annotations

import io

from . import desktop
from .config import config

_engine = None
_import_error: Exception | None = None


def _get_engine():
    """惰性初始化 RapidOCR 引擎（单例）。未安装依赖时抛出带安装指引的错误。"""
    global _engine, _import_error
    if _engine is not None:
        return _engine
    if _import_error is not None:
        raise _import_error
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        _import_error = RuntimeError(
            '未安装 OCR 依赖。请运行：pip install "hermes-computer-use[ocr]"'
            "（或 pip install rapidocr-onnxruntime）"
        )
        raise _import_error from exc
    _engine = RapidOCR()
    return _engine


def ocr_screen() -> list[dict]:
    """对当前主屏做 OCR。返回 [{text, center:[x,y], score}]，坐标为 view 空间像素。

    默认在**原始分辨率**截图上识别（小字更准），再把坐标按比例映射回 view；
    HCU_OCR_FULLRES=off 则直接在降采样的 view 图上识别（更快、省内存）。
    """
    engine = _get_engine()
    import numpy as np

    if config.ocr_fullres:
        img, geo = desktop.capture_native()
        nw, nh = img.size
        rx = (geo.view_width / nw) if nw else 1.0   # 原图坐标 → view 坐标 的缩放比
        ry = (geo.view_height / nh) if nh else 1.0
    else:
        from PIL import Image as PILImage
        png, geo = desktop.capture_png()
        img = PILImage.open(io.BytesIO(png)).convert("RGB")
        rx = ry = 1.0

    result, _ = engine(np.array(img))

    items: list[dict] = []
    if not result:
        return items
    for box, text, score in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(round(sum(xs) / len(xs) * rx))
        cy = int(round(sum(ys) / len(ys) * ry))
        items.append({"text": text, "center": [cx, cy], "score": round(float(score), 3)})
    return items


def find_text(query: str, exact: bool = False) -> list[dict]:
    """在屏幕上查找包含 query 的文字。exact=True 时要求完全相等。

    返回命中项（含可点击的 center 坐标），按置信度从高到低排序。
    """
    q = query.strip()
    matches = []
    for item in ocr_screen():
        text = item["text"]
        hit = (text == q) if exact else (q.lower() in text.lower())
        if hit:
            matches.append(item)
    matches.sort(key=lambda it: it["score"], reverse=True)
    return matches
