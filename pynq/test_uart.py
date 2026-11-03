"""Driver regressions with fake MMIO, no hardware access."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class DriverTests(unittest.TestCase):
    def load_driver(self, overlay=None, mmio=None):
        pynq = types.ModuleType("pynq")
        pynq.Overlay = overlay
        pynq.MMIO = mmio
        spec = importlib.util.spec_from_file_location(
            "driver_under_test", str(Path(__file__).with_name("dual_uart.py")))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"pynq": pynq}):
            spec.loader.exec_module(module)
        return module

    def test_unused_rx_errors_do_not_abort_tx(self):
        writes = []
        mmio = types.SimpleNamespace(
            read=lambda offset: 0xE4,
            write=lambda offset, value: writes.append((offset, value)))
        driver = self.load_driver(mmio=lambda address, size: mmio)
        overlay = types.SimpleNamespace(ip_dict={
            "axi_uartlite_2": {"phys_addr": 0x42C10000, "addr_range": 65536}})
        uart = driver.AxiUartLite(overlay, "axi_uartlite_2")
        uart.write_all(b"STOP\r\n")
        self.assertEqual(writes, [(4, value) for value in b"STOP\r\n"])

    def test_old_two_uart_metadata_is_rejected_before_download(self):
        downloads = []
        overlay = types.SimpleNamespace(
            ip_dict={"axi_uartlite_0": {}, "axi_uartlite_1": {}},
            download=lambda: downloads.append(True))
        driver = self.load_driver(overlay=lambda *a, **kw: overlay)
        with self.assertRaisesRegex(ValueError, "axi_uartlite_2"):
            driver.TripleUartOverlay(Path(__file__))
        self.assertEqual(downloads, [])

    def test_three_ip_addresses_and_fifo_resets(self):
        writes = []
        addresses = []
        ip_dict = {name: {"phys_addr": address, "addr_range": 65536}
                   for name, address in (("axi_uartlite_0", 0x40600000),
                                         ("axi_uartlite_1", 0x42C00000),
                                         ("axi_uartlite_2", 0x42C10000),
                                         ("axi_gpio_0", 0x41200000))}
        overlay = types.SimpleNamespace(ip_dict=ip_dict, download=lambda: None)
        def mmio(address, size):
            addresses.append(address)
            return types.SimpleNamespace(
                read=lambda offset: 4,
                write=lambda offset, value: writes.append((address, offset, value)))
        driver = self.load_driver(overlay=lambda *a, **kw: overlay, mmio=mmio)
        hardware = driver.TripleUartOverlay(Path(__file__))
        self.assertEqual(addresses, [0x40600000, 0x42C00000, 0x42C10000, 0x41200000])
        self.assertEqual(set(writes), {(addr, 12, 3) for addr in addresses[:3]} |
                         {(0x41200000, 0, 0), (0x41200000, 4, 0)})
        self.assertEqual(hardware.ra6m5_second.base_address, 0x42C10000)

    def test_k230_rx_error_is_reported(self):
        mmio = types.SimpleNamespace(read=lambda offset: 0x44)
        driver = self.load_driver(mmio=lambda address, size: mmio)
        overlay = types.SimpleNamespace(ip_dict={
            "axi_uartlite_1": {"phys_addr": 0x42C00000, "addr_range": 65536}})
        uart = driver.AxiUartLite(overlay, "axi_uartlite_1", check_rx_errors=True)
        with self.assertRaisesRegex(OSError, "axi_uartlite_1 RX error"):
            uart.read_available()

    def test_missing_gpio_is_rejected_before_download(self):
        downloads = []
        overlay = types.SimpleNamespace(
            ip_dict={"axi_uartlite_0": {}, "axi_uartlite_1": {}, "axi_uartlite_2": {}},
            download=lambda: downloads.append(True))
        driver = self.load_driver(overlay=lambda *a, **kw: overlay)
        with self.assertRaisesRegex(ValueError, "axi_gpio_0"):
            driver.TripleUartOverlay(Path(__file__))
        self.assertEqual(downloads, [])


if __name__ == "__main__":
    unittest.main()
