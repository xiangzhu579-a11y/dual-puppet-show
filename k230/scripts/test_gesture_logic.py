"""在 PC 上验证 gesture_logic 的判决结果（也就是 FPGA 会收到的串口帧）。

用法：python test_gesture_logic.py
"""
import importlib
import os
import sys

# 兼容两种布局：工程内 scripts/../k230，以及仓库内 k230/scripts/..
_here = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_here, ".."), os.path.join(_here, "..", "k230")):
    if os.path.isfile(os.path.join(_cand, "gesture_logic.py")):
        sys.path.insert(0, _cand)
        break

import gesture_logic as gl  # noqa: E402


def run(name, frames, classes=None):
    """frames: [(index, score), ...] 模拟逐帧模型输出；打印实际发送的帧。"""
    if classes is not None:
        gl.MODEL_CLASSES = classes
        gl.LABELS = ["fist", "palm"] if classes == 2 else ["fist", "no_gesture", "palm"]
        gl.CONF_THRESH = 0.80 if classes == 2 else 0.50
    sm = gl.GestureState()
    sent = []
    for i, (idx, score) in enumerate(frames):
        cmd = sm.update(idx, score)
        if cmd:
            sent.append((i, cmd))
    print(f"\n[{name}] 模型类别数={gl.MODEL_CLASSES} 阈值={gl.CONF_THRESH}")
    print("  发送序列:", " → ".join(f"帧{i}:{c}" for i, c in sent) if sent else "（无）")
    return [c for _, c in sent]


def main():
    # ---------- 两分类模型 ----------
    run("空画面被硬猜成 fist 0.65", [(0, 0.65)] * 10, classes=2)
    run("真握拳 0.95", [(0, 0.95)] * 10, classes=2)
    run("真张掌 0.93", [(1, 0.93)] * 10, classes=2)
    run("握拳后手放下", [(0, 0.95)] * 5 + [(0, 0.62)] * 10, classes=2)
    run("两帧抖动不应触发", [(0, 0.95), (1, 0.9), (0, 0.95)] + [(0, 0.6)] * 6, classes=2)


    # ---------- 帧内容断言（只有 READY / START / STOP） ----------
    ok = True
    ok &= run("断言: 空画面只能出 READY", [(0, 0.65)] * 10, classes=2) == ["READY"]
    ok &= run("断言: 握拳=START, 放下=READY", [(0, 0.95)] * 5 + [(0, 0.62)] * 10, classes=2) == ["START", "READY"]
    ok &= run("断言: 张掌=STOP, 放下=READY", [(1, 0.93)] * 5 + [(1, 0.62)] * 10, classes=2) == ["STOP", "READY"]
    print("\n结论:", "全部断言通过" if ok else "存在不符合预期的用例")


if __name__ == "__main__":
    main()
