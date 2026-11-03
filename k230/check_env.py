"""上板前自检：确认 kmodel 在位、libs 可用。

注意：CanMV 的 MicroPython 里 `os` 模块没有 `os.path` 子模块，
所以这里全部用 os.stat / os.listdir 判断，不能用 os.path.exists。
"""

import os
import sys

KMODEL = "/data/fist_palm.kmodel"

print("=== 1. kmodel 检查 ===")
print("路径:", KMODEL)
try:
    st = os.stat(KMODEL)
    print("存在: True")
    print("大小: %d 字节 (%.2f MB)" % (st[6], st[6] / 1048576))
except Exception as e:
    print("存在: False  ->", repr(e))

print("\n=== 2. 目录内容 ===")
for d in ("/data", "/sdcard"):
    try:
        print(d, "->", os.listdir(d)[:30])
    except Exception as e:
        print(d, "-> 读取失败", repr(e))

print("\n=== 3. libs 可用性 ===")
try:
    from libs.PipeLine import PipeLine, ScopedTiming
    from libs.YOLO import YOLOv5

    print("libs.PipeLine / libs.YOLO 导入成功")
except Exception as e:
    print("libs 导入失败（脚本可能不在 /sdcard 根目录，或固件不带 libs）:")
    sys.print_exception(e)

print("\n=== 4. 运行环境 ===")
try:
    print("implementation:", sys.implementation)
except Exception:
    pass
try:
    print("uname:", os.uname())
except Exception:
    pass
try:
    print("cwd:", os.getcwd())
except Exception:
    pass

print("\n自检结束")
