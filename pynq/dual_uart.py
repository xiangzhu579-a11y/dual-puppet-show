"""Polling helpers for the three AXI UART Lite blocks in the PYNQ overlay."""

import time
from pathlib import Path

from pynq import MMIO, Overlay
from status_leds import StatusLeds


class AxiUartLite:
    RX_FIFO = 0x00
    TX_FIFO = 0x04
    STATUS = 0x08
    CONTROL = 0x0C

    RX_VALID = 1 << 0
    RX_FULL = 1 << 1
    TX_EMPTY = 1 << 2
    TX_FULL = 1 << 3
    OVERRUN_ERROR = 1 << 5
    FRAME_ERROR = 1 << 6
    PARITY_ERROR = 1 << 7

    RESET_TX_FIFO = 1 << 0
    RESET_RX_FIFO = 1 << 1

    def __init__(self, overlay, ip_name, check_rx_errors=False):
        self.overlay = overlay
        self.check_rx_errors = check_rx_errors
        self.ip_name = self._resolve_ip_name(ip_name)
        description = overlay.ip_dict[self.ip_name]
        self.base_address = self._to_int(description["phys_addr"])
        self.address_range = self._to_int(description["addr_range"])
        self.mmio = MMIO(self.base_address, self.address_range)

    def _resolve_ip_name(self, requested):
        if requested in self.overlay.ip_dict:
            return requested
        matches = [name for name in self.overlay.ip_dict if name.endswith(requested)]
        if len(matches) == 1:
            return matches[0]
        raise KeyError(
            f"Cannot uniquely find {requested!r}; available IPs: "
            f"{sorted(self.overlay.ip_dict)}"
        )

    @staticmethod
    def _to_int(value):
        return int(value, 0) if isinstance(value, str) else int(value)

    def status_raw(self):
        # Error bits describe the receiver only.  Do not raise here: this
        # method is also used while filling the TX FIFO, and an unused or
        # floating RA6M5 RX pin must not stop K230 command forwarding.
        return self.mmio.read(self.STATUS)

    def status(self):
        value = self.status_raw()
        return {
            "raw": value,
            "rx_valid": bool(value & self.RX_VALID),
            "rx_full": bool(value & self.RX_FULL),
            "tx_empty": bool(value & self.TX_EMPTY),
            "tx_full": bool(value & self.TX_FULL),
            "overrun_error": bool(value & self.OVERRUN_ERROR),
            "frame_error": bool(value & self.FRAME_ERROR),
            "parity_error": bool(value & self.PARITY_ERROR),
        }

    def reset_fifos(self):
        self.mmio.write(self.CONTROL, self.RESET_TX_FIFO | self.RESET_RX_FIFO)
        time.sleep(0.001)

    def clear_rx(self):
        return self.read_available(limit=65536)

    def write(self, data, timeout=1.0):
        if isinstance(data, str):
            data = data.encode("utf-8")
        data = bytes(data)

        deadline = time.monotonic() + timeout
        for value in data:
            while self.status_raw() & self.TX_FULL:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"{self.ip_name}: TX FIFO remained full after writing bytes"
                    )
                time.sleep(0.0001)
            self.mmio.write(self.TX_FIFO, value)
        return len(data)

    def wait_tx_empty(self, timeout=1.0):
        deadline = time.monotonic() + timeout
        while not (self.status_raw() & self.TX_EMPTY):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{self.ip_name}: TX did not become empty")
            time.sleep(0.0001)

    def write_all(self, data, timeout=1.0):
        count = self.write(data, timeout=timeout)
        self.wait_tx_empty(timeout=timeout)
        return count

    def read_available(self, limit=4096):
        result = bytearray()
        while len(result) < limit:
            status = self.status_raw()
            if self.check_rx_errors and status & (
                    self.OVERRUN_ERROR | self.FRAME_ERROR | self.PARITY_ERROR):
                raise IOError("{} RX error: status=0x{:02x}".format(self.ip_name, status))
            if not status & self.RX_VALID:
                break
            result.append(self.mmio.read(self.RX_FIFO) & 0xFF)
        return bytes(result)

    def read_until(self, terminator=b"\n", timeout=1.0, limit=4096):
        if isinstance(terminator, str):
            terminator = terminator.encode("utf-8")

        result = bytearray()
        deadline = time.monotonic() + timeout
        while len(result) < limit:
            chunk = self.read_available(limit - len(result))
            if chunk:
                result.extend(chunk)
                if terminator and result.endswith(terminator):
                    break
            elif time.monotonic() >= deadline:
                break
            else:
                time.sleep(0.0005)
        return bytes(result)

    def transact(self, request, terminator=b"\n", timeout=1.0, limit=4096):
        self.clear_rx()
        self.write_all(request, timeout=timeout)
        return self.read_until(terminator=terminator, timeout=timeout, limit=limit)


class TripleUartOverlay:
    RA6M5_IP = "axi_uartlite_0"
    K230_IP = "axi_uartlite_1"
    RA6M5_SECOND_IP = "axi_uartlite_2"
    LED_IP = "axi_gpio_0"

    def __init__(self, bitfile="triple_uart.bit", download=True):
        bit_path = Path(bitfile).expanduser().resolve()
        if not bit_path.exists():
            raise FileNotFoundError(f"Overlay bitfile not found: {bit_path}")

        self.overlay = Overlay(str(bit_path), download=False)
        required = (self.RA6M5_IP, self.K230_IP, self.RA6M5_SECOND_IP, self.LED_IP)
        missing = [name for name in required if name not in self.overlay.ip_dict]
        if missing:
            raise ValueError("Three-UART + LED overlay required; missing: " + ", ".join(missing))
        if download:
            self.overlay.download()
        self.ra6m5 = AxiUartLite(self.overlay, self.RA6M5_IP)
        self.k230 = AxiUartLite(self.overlay, self.K230_IP, check_rx_errors=True)
        self.ra6m5_second = AxiUartLite(self.overlay, self.RA6M5_SECOND_IP)
        self.reset_fifos()
        led_info = self.overlay.ip_dict[self.LED_IP]
        self.leds = StatusLeds(MMIO(AxiUartLite._to_int(led_info["phys_addr"]),
                                  AxiUartLite._to_int(led_info["addr_range"])))

    def reset_fifos(self):
        self.ra6m5.reset_fifos()
        self.ra6m5_second.reset_fifos()
        self.k230.reset_fifos()

    def describe(self):
        return {
            "leds": {
                "ip": self.LED_IP,
                "base_address": hex(AxiUartLite._to_int(
                    self.overlay.ip_dict[self.LED_IP]["phys_addr"])),
                "bits": "LED0 heartbeat, LED1 READY, LED2 START, LED3 error",
            },
            "ra6m5": {
                "ip": self.ra6m5.ip_name,
                "base_address": hex(self.ra6m5.base_address),
                "address_range": hex(self.ra6m5.address_range),
                "status": self.ra6m5.status(),
            },
            "k230": {
                "ip": self.k230.ip_name,
                "base_address": hex(self.k230.base_address),
                "address_range": hex(self.k230.address_range),
                "status": self.k230.status(),
            },
            "ra6m5_second": {
                "ip": self.ra6m5_second.ip_name,
                "base_address": hex(self.ra6m5_second.base_address),
                "address_range": hex(self.ra6m5_second.address_range),
                "status": self.ra6m5_second.status(),
            },
        }
