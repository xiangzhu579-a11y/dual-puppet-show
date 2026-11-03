"""K230 脱机自启动入口（不需要 CanMV IDE / 电脑）。

原理：CanMV 固件上电后会执行 TF 卡根目录的 main.py。把本文件和 deploy_cls.py
一起放到 /sdcard，上电即自动跑手势识别，并把状态通过 UART1 发给 FPGA。

调试时想临时停掉自启动：把本文件改名为 main.py.bak（或在 CanMV IDE 里删除它）。

出错时：把 traceback 追加写入 /sdcard/boot_error.log，等 3 秒后自动重启，
避免现场“黑屏且不知道为什么”。
"""

import gc
import sys
import time

LOG = "/sdcard/boot_error.log"


def log_error(exc):
    try:
        f = open(LOG, "a")
        f.write("\n===== %s =====\n" % str(time.time()))
        sys.print_exception(exc, f)
        f.close()
    except Exception:
        pass


def main():
    # 启动横幅：即使没接 IDE，也能从日志确认跑了哪一版
    try:
        f = open("/sdcard/boot.log", "a")
        f.write("boot %s\n" % str(time.time()))
        f.close()
    except Exception:
        pass

    try:
        import deploy_cls

        deploy_cls.main()
    except Exception as e:
        log_error(e)
        try:
            import machine

            time.sleep(3)
            machine.reset()   # 自愈：重启后重新进 main()
        except Exception:
            # 连 reset 都不可用就停在原地，至少屏幕有最后一帧
            while True:
                gc.collect()
                time.sleep(1)


if __name__ == "__main__":
    main()
