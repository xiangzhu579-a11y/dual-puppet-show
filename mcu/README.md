# RA6M5 执行端工程

两台独立的 RA6M5 工程：`RA6M5_Robot1`（第一台，冻结版本）、`RA6M5_Robot2`（第二台，独立初始姿态与差异动作）。
两台的 `robot_config.h` 和动作表**不可互换**。

## 环境

| 项 | 版本 |
|---|---|
| MCU | R7FA6M5BF2CBG |
| IDE | e² studio 2023-04 |
| FSP | 4.5.0 |
| 编译器 | GNU Arm 10.3.1 |
| RTOS | 无（裸机 + 中断） |

## 导入与构建

1. e² studio → `File → Import → General → Existing Projects into Workspace`，分别选择
   `RA6M5_Robot1`、`RA6M5_Robot2`（工程名已区分，可同时导入）；
2. **本仓库不包含 Renesas FSP 源码**（按其许可不随仓库分发）。导入前请任选一种方式补齐：
   - 用 e² studio 打开 `configuration.xml`，让 FSP 4.5.0 重新生成 `ra/fsp`；
   - 或把本机 e² studio 安装目录下的 FSP 4.5.0 `ra/fsp` 复制回工程；
3. Clean → Build，按各板调试探针配置下载。

无 IDE 时只编译、不下载：

```bash
python build.py --gcc "<工具链>/bin/arm-none-eabi-gcc.exe"
# 产物在 Build_Check/ 下
```

## 外设与引脚

| 功能 | 外设 | 引脚 |
|---|---|---|
| 外部控制串口（接 PYNQ） | SCI2（实例名 `g_uart6`） | TX P112 / RX P113 |
| PC 调试串口 | SCI7（实例名 `g_uart7`） | TX P613 / RX P614 |
| 13 路舵机 PWM | GPT0/1/3/4/5/6/7 | 见技术文档「十三路 PWM」表 |
| 底盘 | GPT3 A | P111（1500 μs 停止） |

串口均为 115200 / 8N1；PWM 50 Hz，位置通道按 20 ms 节拍插值。

## 命令

| 命令 | 行为 |
|---|---|
| `START\r\n` | 从 ACT01 循环播放到 ACT06；重复 START 不重启 |
| `STOP\r\n` | 先停底盘，再用 1000 ms 归位；重复 STOP 不延长 |
| 其它行 | 丢弃并记录错误（可配置是否停机） |

## 安全与边界

- 逐路限幅在 `robot_config.h` 中配置（3 号固定、4 号单向 +100 μs、其余 ±100/±200 μs），
  是**软件指令限制**，不是实测机械限位；
- 默认 `ROBOT_STOP_ON_RX_ERROR = 0`，串口错误不保证自动停机；
- 没有硬件急停、没有编码器/电流反馈。
