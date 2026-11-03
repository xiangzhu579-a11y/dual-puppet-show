"""Run from Jupyter with %run main.py, or on PYNQ with python3 main.py."""

import fcntl
import signal
from pathlib import Path

from dual_uart import TripleUartOverlay
from gesture_bridge import GestureBridge


def terminate(signum, frame):
    raise KeyboardInterrupt


def main():
    # A second notebook must not reload the overlay or consume the same FIFO.
    with open("/tmp/puppet_show_main_project.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("正式工程已运行，请先中断原来的 Notebook 或进程。")
        hardware = TripleUartOverlay(Path(__file__).with_name("triple_uart.bit"))
        previous_handler = signal.signal(signal.SIGTERM, terminate)
        try:
            print(hardware.describe())
            bridge = GestureBridge(hardware.k230, hardware.ra6m5,
                                   hardware.ra6m5_second, leds=hardware.leds)
            bridge.run()
        except Exception:
            hardware.leds.fault()
            raise
        finally:
            hardware.leds.stop()
            signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    main()
