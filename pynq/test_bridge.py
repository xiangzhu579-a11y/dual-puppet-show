"""Protocol tests: no PYNQ hardware access and no serial transmission."""

import unittest

from gesture_bridge import CommandParser, GestureBridge


class FakeUart:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.sent = []

    def read_available(self):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data):
        self.sent.append(data)

    def wait_tx_empty(self):
        pass


class BridgeTests(unittest.TestCase):
    def bridge(self, chunks):
        return GestureBridge(FakeUart(chunks), FakeUart(), FakeUart(), log=lambda _: None)

    def test_ready_is_local_and_commands_forward_in_order(self):
        bridge = self.bridge([b"READY\nSTART\r\nSTOP\n"])
        bridge.poll()
        self.assertTrue(bridge.k230_ready)
        self.assertEqual(bridge.ra6m5.sent, [b"START\r\n", b"STOP\r\n"])
        self.assertEqual(bridge.ra6m5_second.sent, bridge.ra6m5.sent)

    def test_every_possible_split(self):
        stream = b"READY\r\nSTART\nSTOP\r\n"
        for split in range(len(stream) + 1):
            bridge = self.bridge([stream[:split], stream[split:]])
            bridge.poll()
            bridge.poll()
            self.assertEqual(bridge.ra6m5.sent, [b"START\r\n", b"STOP\r\n"])
            self.assertEqual(bridge.ra6m5_second.sent, bridge.ra6m5.sent)
            self.assertEqual(bridge.stats["ready"], 1)

    def test_missing_ready_and_repeated_commands(self):
        bridge = self.bridge([b"STOP\nSTART\nSTART\nREADY\nSTOP\n"])
        bridge.poll()
        self.assertEqual(bridge.ra6m5.sent,
                         [b"STOP\r\n", b"START\r\n", b"START\r\n", b"STOP\r\n"])
        self.assertEqual(bridge.ra6m5_second.sent, bridge.ra6m5.sent)

    def test_noise_and_incomplete_lines_never_forward(self):
        bridge = self.bridge([b"ST\xffART\nstart\nHELLO\n\nSTART"])
        bridge.poll()
        self.assertEqual(bridge.ra6m5.sent, [])
        self.assertEqual(bridge.ra6m5_second.sent, [])
        self.assertEqual(bridge.parser.invalid_lines, 3)
        bridge.k230.chunks.append(b"\n")
        bridge.poll()
        self.assertEqual(bridge.ra6m5.sent, [b"START\r\n"])
        self.assertEqual(bridge.ra6m5_second.sent, bridge.ra6m5.sent)

    def test_oversized_line_cannot_turn_into_a_valid_suffix(self):
        parser = CommandParser()
        self.assertEqual(parser.feed(b"x" * 65), [])
        self.assertEqual(parser.feed(b"START\nSTOP\n"), ["STOP"])
        self.assertEqual(parser.invalid_lines, 1)

    def test_transmit_failure_does_not_report_success(self):
        bridge = self.bridge([b"START\n"])
        def fail(data):
            raise TimeoutError("TX blocked")
        bridge.ra6m5.write = fail
        with self.assertRaisesRegex(OSError, "RA6M5-1 enqueue failed"):
            bridge.poll()
        self.assertEqual(bridge.ra6m5_second.sent, [b"START\r\n"])
        self.assertEqual(bridge.stats["start"], 0)
        self.assertIsNone(bridge.last_forwarded)

    def test_idle_poll_returns_without_timeout(self):
        bridge = self.bridge([])
        self.assertFalse(bridge.poll())
        self.assertEqual(bridge.ra6m5.sent, [])
        self.assertEqual(bridge.ra6m5_second.sent, [])

    def test_both_fifos_filled_before_waiting(self):
        bridge = self.bridge([b"START\n"])
        calls = []
        bridge.ra6m5.write = lambda data: calls.append(("write1", data))
        bridge.ra6m5_second.write = lambda data: calls.append(("write2", data))
        bridge.ra6m5.wait_tx_empty = lambda: calls.append("wait1")
        bridge.ra6m5_second.wait_tx_empty = lambda: calls.append("wait2")
        bridge.poll()
        self.assertEqual(calls, [("write1", b"START\r\n"),
                                 ("write2", b"START\r\n"), "wait1", "wait2"])

    def test_second_uart_failure_is_not_reported_as_broadcast_success(self):
        bridge = self.bridge([b"STOP\n"])
        def fail():
            raise TimeoutError("TX blocked")
        bridge.ra6m5_second.wait_tx_empty = fail
        with self.assertRaisesRegex(OSError, "RA6M5-2 TX wait failed"):
            bridge.poll()
        self.assertEqual(bridge.stats["stop"], 0)
        self.assertIsNone(bridge.last_forwarded)

    def test_repeated_ready_is_local_and_logged_once(self):
        bridge = self.bridge([b"READY\nREADY\r\nREADY\n"])
        logs = []
        bridge.log = logs.append
        bridge.poll()
        self.assertEqual(bridge.stats["ready"], 3)
        self.assertEqual(len(logs), 1)
        self.assertEqual(bridge.ra6m5.sent, [])
        self.assertEqual(bridge.ra6m5_second.sent, [])

    def test_many_commands_preserve_both_output_sequences(self):
        commands = [b"START\r\n", b"STOP\r\n"] * 500
        stream = b"READY\n" + b"".join(commands)
        bridge = self.bridge([stream[i:i+11] for i in range(0, len(stream), 11)])
        while bridge.k230.chunks:
            bridge.poll()
        self.assertEqual(bridge.ra6m5.sent, commands)
        self.assertEqual(bridge.ra6m5_second.sent, commands)
        self.assertEqual(bridge.stats["start"], 500)
        self.assertEqual(bridge.stats["stop"], 500)


if __name__ == "__main__":
    unittest.main()
