"""
验证：UIA 无光标输入 + 证明真实鼠标坐标全程不变（"不抢鼠标"）。

用「运行」对话框做安全标的（标准 Win32 Edit，可控可撤销）：
  记录鼠标坐标 → Win+R 打开运行 → winuia.set_text 往输入框填字 → 回读校验 →
  再记录鼠标坐标，断言未变 → 按 Esc 关闭(不执行任何命令)。
仅 Windows，需 [winuia]。运行：python spikes/winuia_cursor_proof.py
"""

from __future__ import annotations

import time

import pyautogui

from hermes_computer_use import winuia


def main() -> None:
    ok, msg = winuia.is_supported()
    if not ok:
        print(f"[SKIP] {msg}")
        return

    from pywinauto import uia_defines

    print("⚠️ 接下来 ~2 秒请勿移动鼠标（要测真实光标是否被我们的代码移动）。")
    pyautogui.hotkey("win", "r")  # 打开"运行"（键盘，不移动鼠标）
    time.sleep(1.2)

    title = None
    for cand in ("运行", "Run"):
        hits = [a for a in winuia.list_apps() if cand in a["title"]]
        if hits:
            title = hits[0]["title"]
            break
    if not title:
        print("未找到「运行」对话框，已放弃。")
        return

    try:
        items = winuia.inspect_window(title)
        target = next((it for it in items if it["control_type"] in ("Edit", "ComboBox")), None)
        if target is None:
            print("运行对话框里未找到输入控件。")
            return

        text = "hermes-uia-no-cursor-test"
        # 把真实光标停到固定基准点，紧接着 UIA 操作、立刻读坐标——压缩人手干扰窗口
        pyautogui.moveTo(300, 300)
        pos0 = tuple(pyautogui.position())
        res = winuia.set_text(title, text, index=target["index"])
        pos1 = tuple(pyautogui.position())  # 立刻读，中间只有 UIA 调用

        # 用 ValuePattern 正确回读输入框当前值
        el = winuia._resolve(title, index=target["index"])
        back = ""
        for cand in [el] + [c for c in el.descendants()
                            if c.element_info.control_type == "Edit"]:
            try:
                back = uia_defines.get_elem_interface(cand.element_info.element, "Value").CurrentValue
                if back:
                    break
            except Exception:
                continue

        moved = pos0 != pos1
        print(f"set_text 结果 : {res}")
        print(f"回读输入框值  : {back!r}")
        print(f"基准光标      : {pos0}  →  操作后 {pos1}")
        print(f"鼠标是否移动  : {'❌ 动了（可能你手动了鼠标）' if moved else '✅ 未移动（没抢鼠标）'}")
        success = (text in (back or "")) and not moved
        print(f"结论          : {'✅ UIA 无光标输入成功，且真实鼠标未动' if success else '⚠️ 见上方明细（文本是否填入 / 鼠标是否被你手动）'}")
    finally:
        pyautogui.press("esc")  # 关闭运行对话框，绝不执行任何命令


if __name__ == "__main__":
    main()
