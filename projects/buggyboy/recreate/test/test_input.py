"""Differential tests for the IKBD input functions (read_joystick @ 0x12110, ...).

read_joystick busy-waits the IKBD ACIA's transmit-ready bit then sends the 0x16 joystick-
interrogate command. Under the oracle this used to spin forever: reads above the 1 MiB image
returned 0, so the TDRE bit was never set. shim.c now models the ACIA status as always-ready, so
the loop terminates. The command write lands on hardware (above the image) and the reply arrives
via an interrupt we don't run, so the function has no image effect — the whole-image diff against
the no-op reconstruction is therefore empty, and reaching rts is itself the thing being verified.
"""
import ctypes

import harness
from harness import differential, report

harness._lib.g_read_joystick.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_read_joystick.restype = None


def test_read_joystick():
    # Run to rts (only possible now that the shim models IKBD_STATUS as TDRE-ready) and confirm
    # read_joystick writes nothing to the image, matching the no-op glue.
    diffs, _ = differential(0x12110, {}, lambda l, b: l.g_read_joystick(b))
    assert not diffs, report(diffs[:12])
