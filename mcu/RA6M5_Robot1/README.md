# 第1台机械臂完整工程

工程名：RA6M5_Robot1。RA6M5 / R7FA6M5BF2CBG，e² studio 2023-04、FSP 4.5.0、GNU Arm 10.3.1，No RTOS。

初始指令脉宽（1～13号，μs）：`[1000, 2166, 500, 1000, 500, 900, 900, 500, 2000, 500, 1500, 1200, 1500]`。

上电保持本机初始姿态；收到 `START\r\n` 后循环ACT01～ACT06；收到 `STOP\r\n` 后停止底盘并回初始姿态。重复START不重启动作，重复STOP不延长回位。PC串口和外部控制串口均支持同一命令协议。

导入：e² studio → File → Import → General → Existing Projects into Workspace，选择本目录。两个工程名称已区分，可以同时导入。使用Debug配置，Clean后Build；调试器连接和下载配置按所用探针新建。

也可在安装Python 3与对应GNU Arm工具链后执行：

```text
python build.py --gcc "工具链bin目录/arm-none-eabi-gcc.exe"
```

生成结果在Build_Check目录。工程自带FSP/CMSIS依赖、硬件配置、链接脚本；不携带旧ELF、对象文件或调试日志。

应用源码：hal_entry.c负责串口、PWM映射与调度；action_player.c/.h负责命令解析和插值；action_groups.h保存六组动作；robot_config.h保存初始值及逐路范围；ra6m5_echo_reference.c为早期参考入口，主程序不调用该测试入口。

外部控制串口：SCI2，实例名g_uart6，TX=P112、RX=P113；PC串口：SCI7/g_uart7，TX=P613、RX=P614。均为115200/8N1。13路PWM频率50Hz，底盘1500μs停止。

软件范围：3号固定本机初始值，4号只向脉宽增加方向100μs；5/7/8/9/11/12号相对初始±200μs，变化的帧目标至少50μs；其他可动路±100μs。受全局500～2500μs和底盘1400～1600μs限制。运行时20ms插值沿用原实现。

版本依据：第一台已调试完成的冻结工程，保留原源码及原栈配置。
