"""手势判决逻辑（纯 Python，不依赖硬件，可在 PC 上单元测试）。

deploy_cls.py 负责摄像头/KPU/UART，判决和串口帧内容都在这里，
所以这份文件同时是"FPGA 会收到什么"的唯一依据。
"""

# ---------------- 模型与阈值 ----------------
MODEL_CLASSES = 2          # 2 = fist/palm；3 = fist/no_gesture/palm（新模型改成 3）
LABELS = ["fist", "palm"] if MODEL_CLASSES == 2 else ["fist", "no_gesture", "palm"]
NONE_LABELS = ("no_gesture",)   # 这些类别统一上报 NONE

CONF_THRESH = 0.80 if MODEL_CLASSES == 2 else 0.50
# 两分类模型对空画面会硬猜出 0.6~0.7，所以阈值要抬高；
# 三分类有 no_gesture 兜底，阈值可以放低，正常手势不容易被误判成 NONE。
STABLE_FRAMES = 3          # 连续多少帧一致才确认手势
NONE_FRAMES = 5            # 连续多少帧无手势才确认 NONE

# ---------------- 串口帧 ----------------
# 只有三个指令：READY / STOP / START
#   拳头       -> START
#   手掌       -> STOP
#   无手势     -> READY（等同于"空闲/就绪"，上电时也发一次 READY）
CMD_FIST = "START"
CMD_PALM = "STOP"
CMD_NONE = "READY"         # 无手势（置信度不足 / no_gesture）也上报 READY
CMD_READY = "READY"        # 上电就绪
HEARTBEAT_MS = 500


def command_for(label):
    """把模型类别名翻译成串口帧；label 为 None 表示无手势。"""
    if label is None:
        return CMD_NONE
    if label == "fist":
        return CMD_FIST
    if label == "palm":
        return CMD_PALM
    return label.upper()


def parse_result(res):
    """兼容不同固件 libs.YOLO 的返回结构，返回 (index, score)。"""
    try:
        if isinstance(res, dict):
            return int(res.get("idx", -1)), float(res.get("score", 0.0))
        if isinstance(res, (tuple, list)):
            if len(res) >= 2 and isinstance(res[0], (int, float)):
                return int(res[0]), float(res[1])
            if len(res) == 1 and isinstance(res[0], (tuple, list)) and len(res[0]) >= 2:
                return int(res[0][0]), float(res[0][1])
    except Exception:
        pass
    return -1, 0.0


class GestureState:
    """帧级防抖：返回需要发送的新状态（None 表示本帧不需要发）。"""

    def __init__(self):
        self.state = None        # 已经上报过的状态："FIST"/"PALM"/"NONE"/None
        self.candidate = ""      # 正在累计的候选（"" = 未初始化）
        self.count = 0

    def update(self, index, score):
        label = LABELS[index] if (0 <= index < len(LABELS) and score >= CONF_THRESH) else None
        if label in NONE_LABELS:
            label = None          # 三分类模型的 no_gesture 也走 NONE 通道

        if label == self.candidate:
            self.count += 1
        else:
            self.candidate = label
            self.count = 1

        need = STABLE_FRAMES if self.candidate is not None else NONE_FRAMES
        if self.count < need:
            return None

        new_state = command_for(self.candidate)
        if new_state == self.state:
            return None
        self.state = new_state
        return new_state
