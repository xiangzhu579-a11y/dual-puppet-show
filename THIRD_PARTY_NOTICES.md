# 第三方组件与许可说明

本仓库以 **AGPL-3.0** 发布（见 `LICENSE`）。下列第三方组件/资料按各自许可使用，
其中部分组件**不随本仓库分发**，需按官方渠道获取。

## 随仓库包含

| 组件 | 用途 | 许可 | 说明 |
|---|---|---|---|
| ARM CMSIS 5 | MCU 启动与内核头文件 | Apache-2.0 | 见 `mcu/RA6M5_Robot*/ra/arm/CMSIS_5/LICENSE.txt`（若从 FSP 包恢复） |
| PYNQ 驱动接口 | PYNQ 板端 Python 运行环境 | BSD-3-Clause | 仅调用，未随仓库分发源码 |

## 通过 Releases 分发

| 组件 | 用途 | 许可 | 说明 |
|---|---|---|---|
| YOLOv5 v7.0 / `yolov5n-cls.pt` | 手势分类模型与训练框架 | **AGPL-3.0** | 权重与导出模型作为 Release 附件提供；源码来自 <https://github.com/ultralytics/yolov5> |
| HaGRID 数据集 | 训练数据（未分发） | CC BY-SA 4.0（变体） | 数据集未随仓库或 Release 分发；使用其训练的模型请保留署名，见 README 引用 |

## 不随仓库分发（需自行安装/获取）

| 组件 | 原因 | 获取方式 |
|---|---|---|
| Renesas FSP 4.5.0 | 许可仅授权与 Renesas 产品配合使用，不适合再分发 | e² studio 安装或 <https://github.com/renesas/fsp/releases/tag/v4.5.0> |
| Xilinx Vivado / IP 生成物 | Xilinx 许可；仓库仅保留 `.bd/.xci/.xdc/.xpr` 源文件 | 用 Vivado 2026.1 重新生成 BD 输出 |
| Canaan `test_yolov5` 转换工具 | 原始资料未标注许可 | 嘉楠官方 K230 资料包 |
| PYNQ 系统镜像 | 平台镜像 | PYNQ 官方发布页 |

## 图片与文档

`docs/` 下的系统框图、软件流程图、实物照片由本项目制作/拍摄，随仓库以 AGPL-3.0 提供；
技术文档 PDF 为同一作品的说明材料。

## 参考引用

- HaGRID: Kapitanov et al., *HaGRID — HAnd Gesture Recognition Image Dataset*, WACV 2024.
- YOLOv5: Ultralytics, v7.0.
- PYNQ: PYNQ Project, *Overlay Design Methodology*.
- Renesas: RA6M5 Group User's Manual, FSP 4.5.0.
- Xilinx: AXI UART Lite v2.0 Product Guide (PG142).
