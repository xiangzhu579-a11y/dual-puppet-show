"""K230 CanMV 板端：fist / palm 手势识别 + UART1 上报给 FPGA/PYNQ。

用法：
  1. kmodel 放到板子 /data/fist_palm.kmodel
  2. CanMV IDE 打开本文件运行（脱机则由 main.py 自启动）
  3. 画面显示识别结果，同时通过 UART1（GPIO9 TX）上报

串口帧（ASCII，\\n 结尾，115200 8N1），只有三个指令：
    READY   上电就绪；也用于"没有手势"（置信度不足 / no_gesture）
    START   识别到拳头（fist）
    STOP    识别到手掌（palm）

判决与帧内容都在 gesture_logic.py，本文件只负责硬件。
"""

import gc
import os
import sys
import time

from libs.PipeLine import PipeLine, ScopedTiming
from libs.YOLO import YOLOv5

import gesture_logic as gl

# ---------------- 可调参数 ----------------
KMOEL_PATH = "/data/fist_palm.kmodel"
RGB888P_SIZE = [1280, 720]
DISPLAY_SIZE = [640, 480]
MODEL_INPUT_SIZE = [224, 224]
DEBUG_MODE = 0
SHOW_NONE_TEXT = True              # 无手势时在画面叠加 NONE

# ---------------- UART 参数 ----------------
UART_ENABLE = True                 # 不需要串口时改 False
UART_TX_PIN = 9                    # GPIO9 -> UART1_TXD
UART_RX_PIN = 10                   # GPIO10 <- UART1_RXD
UART_BAUDRATE = 115200
DEBUG_RESULT = True                # 前 30 帧打印原始识别结果


class GestureUart:
    """UART1 发送器；初始化失败不会影响视觉部分。"""

    def __init__(self, tx_pin=UART_TX_PIN, rx_pin=UART_RX_PIN, baudrate=UART_BAUDRATE):
        self.ok = False
        self.uart = None
        if not UART_ENABLE:
            print("UART 已关闭（UART_ENABLE=False）")
            return
        try:
            from machine import FPIOA, UART

            fpioa = FPIOA()
            fpioa.set_function(tx_pin, FPIOA.UART1_TXD, ie=0, oe=1)
            fpioa.set_function(rx_pin, FPIOA.UART1_RXD, ie=1, oe=0)
            self.uart = UART(
                UART.UART1,
                baudrate=baudrate,
                bits=UART.EIGHTBITS,
                parity=UART.PARITY_NONE,
                stop=UART.STOPBITS_ONE,
            )
            self.ok = True
            print("UART1 就绪: GPIO%d TX / GPIO%d RX @ %d" % (tx_pin, rx_pin, baudrate))
        except Exception as e:
            print("UART 初始化失败（视觉继续运行）:", repr(e))

    def send(self, command):
        if not self.ok:
            return
        try:
            self.uart.write(command + "\n")
            print("TX:", command)
        except Exception as e:
            print("TX 失败:", repr(e))

    def close(self):
        if self.uart is not None:
            try:
                self.uart.deinit()
            except Exception:
                pass


def main():
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_size=DISPLAY_SIZE, display_mode="lcd")
    pl.create()

    yolo = YOLOv5(
        task_type="classify",
        mode="video",
        kmodel_path=KMOEL_PATH,
        labels=gl.LABELS,
        rgb888p_size=RGB888P_SIZE,
        model_input_size=MODEL_INPUT_SIZE,
        display_size=DISPLAY_SIZE,
        conf_thresh=gl.CONF_THRESH,
        debug_mode=DEBUG_MODE,
    )
    yolo.config_preprocess()

    link = GestureUart()
    link.send(gl.CMD_READY)

    sm = gl.GestureState()
    sm.state = gl.CMD_READY     # 上电已发过一次 READY，避免无手势时立刻重复发
    last_tx = time.ticks_ms()
    frame_no = 0
    now = last_tx

    try:
        while True:
            os.exitpoint()
            with ScopedTiming("total", 1):
                img = pl.get_frame()
                res = yolo.run(img)
                yolo.draw_result(res, pl.osd_img)

                frame_no += 1
                if DEBUG_RESULT and frame_no <= 30:
                    print("raw result:", res)

                idx, score = gl.parse_result(res)
                cmd = sm.update(idx, score)
                now = time.ticks_ms()
                if cmd:
                    link.send(cmd)
                    last_tx = now

                if SHOW_NONE_TEXT and sm.state == gl.CMD_NONE:
                    try:
                        pl.osd_img.draw_string_advanced(20, 20, 40, gl.CMD_NONE, (255, 0, 0))
                    except Exception:
                        pass

                pl.show_image()
                gc.collect()

            # 心跳：状态不变时重发当前状态，FPGA 可据此判断链路存活
            if time.ticks_diff(now, last_tx) >= gl.HEARTBEAT_MS:
                link.send(sm.state if sm.state else gl.CMD_NONE)
                last_tx = now

    except Exception as e:
        sys.print_exception(e)
    finally:
        link.send(gl.CMD_NONE)
        link.close()
        yolo.deinit()
        pl.destroy()


if __name__ == "__main__":
    main()
