# PYNQ-Z2 FPGA 工程

Zynq-7020（`xc7z020clg400-1`）上的三路 AXI UART Lite + 4 位 GPIO，供 PYNQ 的 Python 程序通过 MMIO 访问。

## 内容

| 路径 | 说明 |
|---|---|
| `puppet_show_pjt.xpr` | Vivado 工程（2026.1） |
| `puppet_show_pjt.srcs/sources_1/bd/design_1/` | Block Design 源（`.bd` / `.bda` / 各 IP 的 `.xci`） |
| `puppet_show_pjt.srcs/constrs_1/new/top.xdc` | 引脚与时序约束 |
| `puppet_show_pjt.hw/` | 硬件交接信息 |

仓库**不包含** `.gen`、`.ipcfg`、`.runs`、`.cache` 等可再生产物，也不包含 Vivado 安装目录。

## 地址分配

| IP | 基地址 | 用途 |
|---|---|---|
| `axi_uartlite_0` | `0x40600000` | 第一台 RA6M5 |
| `axi_uartlite_1` | `0x42C00000` | K230 手势输入 |
| `axi_uartlite_2` | `0x42C10000` | 第二台 RA6M5 |
| `axi_gpio_0` | `0x41200000` | 板载 LED0～3 |

三路 UART 均 115200 / 8N1，PL 时钟 100 MHz。

## 重新生成位流

1. 安装 **Vivado 2026.1** 与 PYNQ-Z2 板卡文件；
2. 打开 `puppet_show_pjt.xpr`，确认器件为 `xc7z020clg400-1`、BD 为 `design_1`、顶层为 `design_1_wrapper`；
3. 工具提示缺少 run 产物时：重新生成 BD Output Products → Reset Runs → Synthesis → Implementation → Generate Bitstream；
4. 产物在 `puppet_show_pjt.runs/impl_1/design_1_wrapper.bit`，配套 `hw_handoff/design_1.hwh`。

## 只想运行

**不需要重新综合**：直接从仓库 Releases 下载 `triple_uart.bit` 与 `triple_uart.hwh`（必须成对），
放到 PYNQ 的 `pynq/runtime/` 目录即可（文件名需一致）。

## 资源与时序

原实现报告见 `docs/verification/vivado-reports/`：LUT 840（1.58%）、FF 1057（0.99%）、
BRAM 0、DSP 0；WNS 3.555 ns、WHS 0.069 ns，无失败端点。
