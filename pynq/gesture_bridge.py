"""Continuous K230 -> PYNQ -> two RA6M5 boards command forwarding."""

import time


class CommandParser:
    """LF/CRLF framing; discard an entire oversized line before resyncing."""

    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False
        self.invalid_lines = 0

    def feed(self, data):
        commands = []
        for value in data:
            if value == 10:
                if not self.discarding:
                    line = bytes(self.buffer)
                    if line.endswith(b"\r"):
                        line = line[:-1]
                    if line in (b"READY", b"START", b"STOP"):
                        commands.append(line.decode("ascii"))
                    elif line:
                        self.invalid_lines += 1
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                self.buffer.append(value)
                if len(self.buffer) > 64:
                    self.buffer.clear()
                    self.discarding = True
                    self.invalid_lines += 1
        return commands


class GestureBridge:
    def __init__(self, k230_uart, ra6m5_uart, ra6m5_second_uart, log=print, leds=None):
        self.k230 = k230_uart
        self.ra6m5 = ra6m5_uart
        self.ra6m5_second = ra6m5_second_uart
        self.log = log
        self.leds = leds
        self.parser = CommandParser()
        self.k230_ready = False
        self.ready_reported = False
        self.last_forwarded = None
        self.stats = {"rx_bytes": 0, "ready": 0, "start": 0, "stop": 0}

    def forward(self, command):
        payload = (command + "\r\n").encode("ascii")
        queued = []
        errors = []
        # Fill both independent FIFOs before waiting for either to empty.
        for name, uart in (("RA6M5-1", self.ra6m5),
                           ("RA6M5-2", self.ra6m5_second)):
            try:
                uart.write(payload)
                queued.append((name, uart))
            except OSError as exc:
                errors.append("{} enqueue failed: {}".format(name, exc))
        for name, uart in queued:
            try:
                uart.wait_tx_empty()
            except OSError as exc:
                errors.append("{} TX wait failed: {}".format(name, exc))
        if errors:
            raise IOError("{} broadcast incomplete; the other UART may have sent it. "
                          "No automatic retry. {}".format(command, "; ".join(errors)))

    def poll(self):
        if self.leds is not None:
            self.leds.tick()
        data = self.k230.read_available()
        self.stats["rx_bytes"] += len(data)
        previous_invalid = self.parser.invalid_lines
        commands = self.parser.feed(data)
        if self.parser.invalid_lines != previous_invalid and self.leds is not None:
            self.leds.fault()
        for command in commands:
            if command == "READY":
                self.k230_ready = True
                self.stats["ready"] += 1
                if self.leds is not None:
                    self.leds.ready()
                if not self.ready_reported:
                    self.log("K230 READY: 初始化成功，继续等待指令")
                    self.ready_reported = True
            else:
                # Forward every command, including STOP received before READY.
                self.forward(command)
                self.last_forwarded = command
                self.stats[command.lower()] += 1
                if self.leds is not None:
                    self.leds.command(command)
                self.log("K230 -> RA6M5-1 + RA6M5-2: " + command)
        return bool(data)

    def snapshot(self):
        return dict(self.stats, k230_ready=self.k230_ready,
                    last_forwarded=self.last_forwarded,
                    invalid_lines=self.parser.invalid_lines)

    def run(self):
        try:
            if self.leds is not None:
                self.leds.begin()
            self.log("持续监听已开始。请启动 K230；Jupyter 中断按钮 / Ctrl+C 可退出。")
            while True:
                if not self.poll():
                    time.sleep(0.0005)
        except KeyboardInterrupt:
            self.log("监听已退出；退出操作不会自动向 RA6M5 发送 STOP。")
        except Exception:
            if self.leds is not None:
                self.leds.fault()
            raise
        finally:
            if self.leds is not None:
                self.leds.stop()
            self.log(str(self.snapshot()))
