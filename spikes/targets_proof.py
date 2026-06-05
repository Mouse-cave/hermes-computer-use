"""
验证统一目标层（M2）：targets 枚举 → fill 编号目标(走 UIA 无光标) → 校验值 + 真实光标未动。

用「运行」对话框做安全标的（不执行任何命令，最后 Esc 关闭）。仅 Windows，需 [winuia]。
运行：python spikes/targets_proof.py
"""

from __future__ import annotations

import time

import pyautogui
from pywinauto import uia_defines

from hermes_computer_use import targets as targets_mod
from hermes_computer_use import winuia


def main() -> None:
    ok, msg = winuia.is_supported()
    if not ok:
        print(f"[SKIP] {msg}")
        return

    print("⚠️ 接下来 ~2 秒请勿移动鼠标。")
    pyautogui.hotkey("win", "r")
    time.sleep(1.2)

    title = None
    for cand in ("运行", "Run"):
        hits = [a for a in winuia.list_apps() if cand in a["title"]]
        if hits:
            title = hits[0]["title"]
            break
    if not title:
        print("未找到「运行」对话框。")
        return

    try:
        items = targets_mod.build(title)
        edit = next((t for t in items if t["control_type"] in ("Edit", "ComboBox")), None)
        if edit is None:
            print("未找到可填的编号目标。")
            return

        text = "hermes-targets-fill-test"
        pyautogui.moveTo(300, 300)
        pos0 = tuple(pyautogui.position())
        res = targets_mod.fill(edit["id"], text)
        pos1 = tuple(pyautogui.position())

        el = winuia._resolve(title, index=edit["uia_index"])
        back = ""
        for cand in [el] + [d for d in el.descendants()
                            if d.element_info.control_type == "Edit"]:
            try:
                back = uia_defines.get_elem_interface(cand.element_info.element, "Value").CurrentValue
                if back:
                    break
            except Exception:
                continue

        moved = pos0 != pos1
        print(f'目标 #{edit["id"]} [{edit["source"]}·{edit["control_type"]}] "{edit["name"]}"')
        print(f"fill 结果   : {res}")
        print(f"回读值      : {back!r}")
        print(f"基准光标    : {pos0} → {pos1}")
        success = (text in (back or "")) and not moved
        print(f"结论        : {'✅ targets.fill 经 UIA 成功填字，真实鼠标未动' if success else '⚠️ 见上方明细'}")
    finally:
        pyautogui.press("esc")


if __name__ == "__main__":
    main()
