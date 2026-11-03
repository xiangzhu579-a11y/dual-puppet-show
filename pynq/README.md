> 仓库不含 `triple_uart.bit` / `triple_uart.hwh`（体积原因），请从 Releases 下载并与本目录的 Python 文件放在一起。

# K230 → PYNQ-Z2 → 两块 RA6M5

## 四个运行指示 LED

使用当前 Vivado 的 axi_gpio_0（0x41200000，4 位全输出），LED0～3 分别对应 R14、P14、N16、M14，高电平点亮。

| LED | 行为 |
|---|---|
| LED0 | 主监听循环每 0.5 秒翻转一次，完整闪烁周期约 1 秒；无串口数据时也闪烁 |
| LED1 | 收到 READY 后亮；重复 READY 不改变状态 |
| LED2 | 两块 RA6M5 的 START 发送均成功后亮；两路 STOP 均成功后灭 |
| LED3 | 非法/超长命令行、K230 RX 硬件错误、发送失败或运行异常触发后保持亮 |

LED3 的非法行告警不会阻止下一条有效指令。K230 RX 硬件错误、发送失败和未处理异常会结束监听，LED0 熄灭，LED3 保持亮。不检测静默断线（当前无心跳协议），也不把未连接 MCU 导致的 RX 错误当作 TX 失败。重新运行程序并加载 Overlay 后清除旧灯态。

LED2 表示最近一次成功提交给两路 UART 的命令，不代表两块 MCU 已执行。部分发送失败时 LED2 保留之前的状态，结合 LED3 判断。正常中断或 systemd 的 SIGTERM 停止时只熄灭 LED0，其余灯保留；不会自动发送 STOP。

LED0 由主循环驱动，没有独立闪灯线程；程序卡住时会停止翻转，但可能停在亮或灭的状态。强制杀死、系统死机或 GPIO/位流初始化之前的错误，软件无法保证点亮 LED3。

新增 status_leds.py 与 test_leds.py。更新后的 triple_uart.bit/.hwh 已包含三 UART 和 LED GPIO，需要成对使用。更新后必须重启 Notebook 内核再运行；若已有开机服务，则停止旧程序后重启服务即可，入口仍为 main.py。

## 启动

1. 停止旧程序及其它串口测试 Notebook。更新后关闭旧页面，重新打开 main_project.ipynb，选择 Kernel → Restart，避免使用缓存的旧模块。
2. 运行 `%run main.py`。看到三路 UART 信息和“持续监听已开始”后，启动 K230。
3. K230 初始化完成发送 READY，之后发送 START 或 STOP。每条命令以换行结束。

也可在 PYNQ 终端进入本目录运行 `python3 main.py`。两个入口只能运行一个。入口保留互斥锁，但其它旧测试程序不遵守此锁，需要自行停止。

## 协议

| K230 输入 | PYNQ 行为 | 第一块 RA6M5 | 第二块 RA6M5 |
|---|---|---|---|
| `READY\n` | 记录初始化成功，继续监听 | 不发送 | 不发送 |
| `START\n` | 同一条指令提交给两个 UART | `START\r\n` | `START\r\n` |
| `STOP\n` | 同一条指令提交给两个 UART | `STOP\r\n` | `STOP\r\n` |

输入为 ASCII 大写，接受 LF 或 CRLF，必须带换行。支持拆包、连续多条命令，丢弃未知、损坏和超长行。重复 READY 只打印第一次，但每条都计数；重复 START/STOP 每条均转发给两块。

沿用原工程语义：READY 为初始化通知，未收到 READY 也转发 START/STOP，避免 PYNQ 晚启动而错过一次性通知。再次 READY 不改变 RA6M5 状态。

两路发送先分别写 TX FIFO，再等待两路 FIFO 排空，不先等待第一路发送完成才提交第二路。两路由独立 UART 硬件发送，但 Linux/Python 写寄存器有先后差，没有固定的最大同步误差；并非同一个时钟沿启动。严格同步需额外设计硬件触发或带执行时间的 MCU 协议。

日志 `K230 -> RA6M5-1 + RA6M5-2: START` 仅表示两路均已提交发送并通过 TX FIFO 等待，不证明两块 RA6M5 已接收或舵机执行。当前无 ACK 协议。

## 硬件与文件

采用当前 Vivado 已编译的三 UART 位流，源为 puppet_show_pjt.runs/impl_1/design_1_wrapper.bit，配套 hw_handoff/design_1.hwh。部署后命名为 triple_uart.bit、triple_uart.hwh。

| 设备 | IP | 基地址 | PYNQ RX | PYNQ TX |
|---|---|---|---|---|
| K230 | axi_uartlite_1 | 0x42C00000 | Pmod A Pin 1 / Y18 | Pmod A Pin 2 / Y19 |
| RA6M5-1 | axi_uartlite_0 | 0x40600000 | Pmod B Pin 1 / W14 | Pmod B Pin 2 / Y14 |
| RA6M5-2 | axi_uartlite_2 | 0x42C10000 | Pmod B Pin 3 / T11 | Pmod B Pin 4 / T10 |

三路均为 115200、8N1，IP 时钟 100 MHz。PYNQ TX 接 MCU RX，PYNQ RX 接 MCU TX。Pmod B Pin 5、Pin 11 分别连接两块 RA6M5 GND；K230 也须共地。独立供电时不连接 3.3V 电源脚。只发送时，两块 RA6M5 的回传 TX 可不接。

- main.py：独立入口与互斥锁。
- dual_uart.py：为延续原工程保留模块文件名；现在包含 TripleUartOverlay，管理三个 UART。
- gesture_bridge.py：持续接收及双板转发。
- test_bridge.py、test_uart.py：模拟串口测试，不触发板卡发送。
- main_project.ipynb：Jupyter 运行入口。

原 dual_uart.bit/.hwh 保留供回退参考，新入口不会使用它们。本次更新前的板端文件另存于目录内 backup_before_leds_... 文件夹。

## 停止与异常

中断 Notebook 或 Ctrl+C 退出监听，不自动发送 STOP。需停止人偶时，先让 K230 发送 STOP，再退出监听。

未连接 MCU 时，RX 悬空产生的接收错误不会导致 TX 发送报错。真正写入或 TX 等待超时会尝试另一条通道后报出具体失败通道并退出；此时另一块可能已经执行，统计不会计为双板发送成功，也不会自动重试。

启动会下载新 Overlay、清空 FIFO，因此建议先启动 PYNQ 再启动 K230。本工程用于低频手势指令，Linux 轮询小容量 FIFO 不保证满速突发数据无丢失。

## 验证与验收

在本目录执行 `python3 -m unittest discover -v`。测试覆盖两路相同输出、先提交两路再等待、分包、重复 READY、非法输入、1000 条命令的顺序、单路失败不误报双路成功，以及驱动地址和悬空 RX 回归。

实际验收需由 K230 发送 READY、START、STOP，在两块 RA6M5 调试端分别确认收到 START 和 STOP。软件模拟测试不替代实际接线和接收验证。

