"""Four active-high PYNQ-Z2 LEDs on AXI GPIO channel 1."""

import time


class StatusLeds:
    HEARTBEAT = 1
    READY = 2
    RUN = 4
    ERROR = 8

    def __init__(self, mmio, clock=time.monotonic):
        self.mmio = mmio
        self.clock = clock
        self.value = 0
        self.next_toggle = 0.0
        self.mmio.write(0x00, 0)
        self.mmio.write(0x04, 0)  # Channel 1 direction: outputs.

    def set_bit(self, mask, enabled):
        value = (self.value | mask) if enabled else (self.value & ~mask)
        if value != self.value:
            self.mmio.write(0x00, value)
            self.value = value

    def begin(self):
        self.set_bit(self.HEARTBEAT, True)
        self.next_toggle = self.clock() + 0.5

    def tick(self):
        now = self.clock()
        if now >= self.next_toggle:
            self.set_bit(self.HEARTBEAT, not bool(self.value & self.HEARTBEAT))
            self.next_toggle = now + 0.5

    def ready(self):
        self.set_bit(self.READY, True)

    def command(self, command):
        self.set_bit(self.RUN, command == "START")

    def fault(self):
        self.set_bit(self.ERROR, True)

    def stop(self):
        # Preserve READY, last transmitted command, and any latched fault.
        self.set_bit(self.HEARTBEAT, False)
