"""Status LED transitions and main-loop integration without hardware."""

import types
import unittest

from gesture_bridge import GestureBridge
from status_leds import StatusLeds
from test_bridge import FakeUart


class LedTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.writes = []
        self.leds = StatusLeds(types.SimpleNamespace(
            write=lambda offset, value: self.writes.append((offset, value))),
            clock=lambda: self.now)
        self.bridge = GestureBridge(FakeUart(), FakeUart(), FakeUart(),
                                    log=lambda _: None, leds=self.leds)

    def send(self, data):
        self.bridge.k230.chunks.append(data)
        self.bridge.poll()

    def test_heartbeat_runs_on_idle_poll_and_preserves_other_bits(self):
        self.leds.begin()
        self.send(b"READY\nSTART\n")
        self.assertEqual(self.leds.value, 7)
        self.now = 0.49
        self.bridge.poll()
        self.assertEqual(self.leds.value, 7)
        self.now = 0.5
        self.bridge.poll()
        self.assertEqual(self.leds.value, 6)
        self.now = 1.0
        self.bridge.poll()
        self.assertEqual(self.leds.value, 7)

    def test_ready_start_stop(self):
        self.leds.begin()
        self.send(b"READY\nREADY\n")
        self.assertEqual(self.leds.value, 3)
        self.send(b"START\n")
        self.assertEqual(self.leds.value, 7)
        self.send(b"STOP\n")
        self.assertEqual(self.leds.value, 3)

    def test_invalid_line_latches_fault_but_valid_command_still_works(self):
        self.leds.begin()
        self.send(b"garbage\nREADY\nSTART\nSTOP\n")
        self.assertEqual(self.leds.value, 11)
        self.assertEqual(self.bridge.ra6m5.sent, [b"START\r\n", b"STOP\r\n"])

    def test_partial_broadcast_failure_lights_error_without_setting_run(self):
        self.bridge.k230.chunks.append(b"READY\nSTART\n")
        def fail(data):
            raise TimeoutError("TX blocked")
        self.bridge.ra6m5_second.write = fail
        with self.assertRaises(OSError):
            self.bridge.run()
        self.assertEqual(self.leds.value, 10)
        self.assertEqual(self.bridge.stats["start"], 0)

    def test_k230_failure_lights_fault_and_stops_heartbeat(self):
        def fail():
            raise IOError("RX error")
        self.bridge.k230.read_available = fail
        with self.assertRaises(OSError):
            self.bridge.run()
        self.assertEqual(self.leds.value, 8)

    def test_interrupt_is_not_a_fault_or_stop_command(self):
        chunks = iter([b"READY\nSTART\n"])
        def read():
            try:
                return next(chunks)
            except StopIteration:
                raise KeyboardInterrupt
        self.bridge.k230.read_available = read
        self.bridge.run()
        self.assertEqual(self.leds.value, 6)
        self.assertEqual(self.bridge.ra6m5.sent, [b"START\r\n"])
        self.assertEqual(self.bridge.ra6m5_second.sent, [b"START\r\n"])

    def test_initialization_clears_old_state(self):
        self.assertEqual(self.writes, [(0, 0), (4, 0)])
        self.assertEqual(self.leds.value, 0)


if __name__ == "__main__":
    unittest.main()
