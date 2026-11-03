# PYNQ 脱机运行

本工程使用 SD 卡上的 PYNQ Linux 和 systemd 服务，不烧写 QSPI。保留 SD 卡并选择 SD 启动，接独立电源、K230 和两块 RA6M5 的 UART 及共地，即可脱离电脑、浏览器和网线运行。

上电后先完成系统原有 bootpy 启动脚本，再运行 puppet-show.service。服务运行 main.py，加载本目录 triple_uart.bit/.hwh，驱动四个 LED 并持续监听 K230。系统启动需一定时间，以 LED0 持续闪烁为准备完成的依据。建议此时再启动 K230；监听前发出的命令可能丢失。

## 灯态

- LED0：主循环每 0.5 秒翻转。
- LED1：收到 READY 后亮。
- LED2：两路 START 提交成功后亮，两路 STOP 成功后灭；不是 MCU 执行确认。
- LED3：检测到非法指令或异常后亮。

服务发生异常退出时 5 秒后尝试重启；120 秒内最多启动 5 次，避免持续重启。重新加载位流会清除灯态，因此异常退出后的 LED3 可能只亮到下次重启；故障详情查看日志。非法行只报警、不退出，此时 LED3 保持亮。

## 管理命令（PYNQ 终端）

```bash
sudo systemctl status puppet-show.service --no-pager
sudo journalctl -u puppet-show.service -b -n 60 --no-pager
sudo journalctl -u puppet-show.service -f
```

Notebook 手动调试前先停止后台服务，避免同一个 Overlay 被多个程序访问：

```bash
sudo systemctl stop puppet-show.service
```

调试结束后停止 Notebook 中的程序，再启动服务：

```bash
sudo systemctl start puppet-show.service
```

更新本目录程序或成对更新 bit/hwh 后：

```bash
sudo systemctl restart puppet-show.service
```

修复导致连续失败的问题后：

```bash
sudo systemctl reset-failed puppet-show.service
sudo systemctl start puppet-show.service
```

取消开机自启并停止服务：

```bash
sudo systemctl disable --now puppet-show.service
```

重新启用：

```bash
sudo systemctl enable --now puppet-show.service
```

服务文件安装在 /etc/systemd/system/puppet-show.service，本目录保留相同副本。入口路径和虚拟环境路径必须保持可用。

## 启停语义

上电只启动监听，不主动发送 START。即使错过 READY，后续 START/STOP 仍会转发。若 K230 正在持续发送 START，监听恢复后就会转发该指令。

停止服务、重启 PYNQ 或 PYNQ 断电，不等于向 RA6M5 发送 STOP。需要停止人偶时，先通过 K230 发送 STOP。当前无 MCU 心跳超时和 STOPPED 应答，独立供电的 MCU 不一定会随 PYNQ 停止而停止。

下电前可执行 sudo poweroff，待系统关机后切断电源。最终冷启动验收：断开电脑和网线，重新上电，等待 LED0 闪烁，再由 K230 发送 READY/START/STOP，检查两块 RA6M5 的实际行为。
