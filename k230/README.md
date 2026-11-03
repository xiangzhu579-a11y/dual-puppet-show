# K230 视觉端

手势识别与串口上报。识别结果：`START`（拳头）/ `STOP`（手掌）/ `READY`（无有效手势）。

## 文件

| 文件 | 作用 |
|---|---|
| `deploy_cls.py` | 主程序：摄像头采集、YOLOv5 分类、显示、UART 发送 |
| `gesture_logic.py` | 判决逻辑：类别→指令映射、3/5 帧防抖、阈值（可 PC 单测） |
| `main.py` | 脱机自启动入口，异常写日志并自动重启 |
| `check_env.py` | 板端环境自检（kmodel、`/sdcard`、`libs`） |
| `scripts/` | 数据构建、训练、ONNX 导出、kmodel 转换、状态机单测 |

## 部署

1. 从仓库 **Releases** 下载 `best.kmodel`（两分类裁手版）；
2. `main.py`、`deploy_cls.py`、`gesture_logic.py` → 板子 `/sdcard/`；
3. `best.kmodel` → 板子 `/data/fist_palm.kmodel`；
4. CanMV IDE 运行 `deploy_cls.py`，或上电由 `main.py` 自启。

固件需自带兼容的 `libs.PipeLine` / `libs.YOLO` 与 nncase 2.9 运行时。

## 串口

UART1，GPIO9 TX / GPIO10 RX，115200 8N1，3.3 V，TX/RX 交叉并与 PYNQ 共地。

| 指令 | 触发 |
|---|---|
| `READY\n` | 上电；或连续 5 帧无有效手势 |
| `START\n` | 拳头连续 3 帧 |
| `STOP\n` | 手掌连续 3 帧 |

状态变化立即发送；状态稳定时每 500 ms 重发一次。阈值与防抖参数在 `gesture_logic.py` 顶部。

## 重新训练 / 转换

需要自备 YOLOv5 v7.0 源码与 HaGRID 数据集（均不在本仓库）：

```bash
# 1) 数据：HaGRID 采样 → fist/palm，按标注框裁手
python scripts/prepare_dataset.py --zip <hagrid.zip> --out datasets/fist_palm
python scripts/build_crop_dataset.py          # 路径见脚本顶部，可改

# 2) 训练（在 yolov5 目录）
python classify/train.py --model yolov5n-cls.pt --data datasets/fist_palm_crop \
  --epochs 80 --batch-size 32 --imgsz 224 --device 0 --workers 0 --cache ram

# 3) 导出 opset 12 / IR 7
python scripts/export_onnx_legacy.py --weights runs/fist_palm_crop/weights/best.pt \
  --out runs/fist_palm_crop/weights/best_op12.onnx

# 4) 量化（Linux + nncase 2.9）
bash scripts/convert_only.sh <best_op12.onnx> <输出.kmodel> <校准图目录>
```

精度自检：`python scripts/eval_onnx.py --onnx <onnx> --val datasets/fist_palm_crop/val`，
判决逻辑单测：`python scripts/test_gesture_logic.py`。

## 注意

两分类模型没有“无手势”类别，空画面仍可能以较低置信度误报，阈值（0.80）只能降低概率；
如需更稳，可增加 `no_gesture` 类别或用“检测+分类”两阶段方案。
