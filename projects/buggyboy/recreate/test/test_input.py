"""Differential tests for the IKBD input functions (read_joystick, read_input, check_abort).

read_joystick busy-waits the IKBD ACIA's transmit-ready bit then sends the 0x16 joystick-
interrogate command. Under the oracle this used to spin forever: reads above the 1 MiB image
returned 0, so the TDRE bit was never set. shim.c now models the ACIA status as always-ready, so
the loop terminates. The command write lands on hardware (above the image) and the reply arrives
via an interrupt we don't run, so the function has no image effect.

read_input / check_abort are pure logic over the input globals (input_state/last_key/input_prev),
which the harness pokes as inputs (the interrupt that sets them isn't run — see HARNESS.md).
check_abort's only output is its return value (no image effect), so its test compares d0.
"""
import ctypes
import random

import harness
from harness import differential, report

A_INPUT_PREV, A_INPUT_STATE, A_LAST_KEY = 0x18c42, 0x18c44, 0x18c46

harness._lib.g_read_joystick.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_read_joystick.restype = None
harness._lib.g_read_input.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_read_input.restype = None
harness._lib.g_check_abort.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_check_abort.restype = ctypes.c_uint32
harness._lib.g_install_handlers.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_install_handlers.restype = None

KBDVBASE = 0x500               # must match OS_KBDVBASE in os.h (shim returns it for Kbdvbase)
A_KBDVBASE_PTR = 0x18bda       # saved vectors written by install_handlers
KBDV_MOUSEVEC, KBDV_JOYVEC = 0x10, 0x18


def test_read_joystick():
    # Run to rts (only possible now that the shim models IKBD_STATUS as TDRE-ready) and confirm
    # read_joystick writes nothing to the image, matching the no-op glue.
    diffs, _ = differential(0x12110, {}, lambda l, b: l.g_read_joystick(b))
    assert not diffs, report(diffs[:12])


def test_install_handlers():
    # Kbdvbase() -> OS_KBDVBASE (modeled by the shim); install_handlers saves the old mousevec/joyvec
    # vectors and installs the game's handlers. Stage distinct old vectors so the save+patch shows.
    for seed in range(8):
        rng = random.Random(seed)
        pokes = {
            KBDVBASE + KBDV_MOUSEVEC: rng.randint(0, 0xffffffff).to_bytes(4, "big"),
            KBDVBASE + KBDV_JOYVEC: rng.randint(0, 0xffffffff).to_bytes(4, "big"),
        }
        diffs, _ = differential(0x12124, {"_pokes": pokes},
                                lambda l, b: l.g_install_handlers(b))
        assert not diffs, f"seed={seed}\n{report(diffs[:12])}"


# The scancodes read_input maps, plus a few that map to nothing (0 result) and a joystick-present case.
_KEYS = (0x39, 0x48, 0x4b, 0x4d, 0x50, 0x00, 0x1c, 0xff)


def test_read_input():
    rng = random.Random(1)
    for i in range(40):
        # Sweep input_state (joystick-present vs empty) x last_key (each mapped scancode + misses).
        input_state = rng.choice((0x0000, 0x0001, 0x0080, 0x8f00 | rng.randint(0, 0xff), rng.randint(0, 0xffff)))
        last_key = rng.choice(_KEYS) if i % 2 else rng.randint(0, 0xffff)
        pokes = {A_INPUT_STATE: input_state.to_bytes(2, "big"), A_LAST_KEY: last_key.to_bytes(2, "big")}
        diffs, _ = differential(0x120b0, {"_pokes": pokes},
                                lambda l, b: l.g_read_input(b), poison=True)
        assert not diffs, f"input_state={input_state:#06x} last_key={last_key:#06x}\n{report(diffs[:12])}"


def test_check_abort():
    rng = random.Random(2)
    # Explicit branch coverage + fuzz: abort (live!=0 and live!=baseline) vs the Crawio path.
    cases = [(0x00, 0x00), (0x05, 0x05), (0x05, 0x00), (0x00, 0x42), (0x80, 0x01)]
    cases += [(rng.randint(0, 0xff), rng.randint(0, 0xff)) for _ in range(40)]
    for live, baseline in cases:
        # low byte is at addr+1 (big-endian word); high byte kept as noise to prove it's ignored.
        input_state = (rng.randint(0, 0xff) << 8) | live
        input_prev = (rng.randint(0, 0xff) << 8) | baseline
        pokes = {A_INPUT_STATE: input_state.to_bytes(2, "big"), A_INPUT_PREV: input_prev.to_bytes(2, "big")}
        diffs, info = differential(0x128ea, {"_pokes": pokes}, lambda l, b: l.g_check_abort(b))
        assert not diffs, f"live={live:#04x} baseline={baseline:#04x}\n{report(diffs[:12])}"
        assert info["ret"] == info["regs"]["d0"], (
            f"live={live:#04x} baseline={baseline:#04x}: "
            f"cand d0={info['ret']:#x} != oracle d0={info['regs']['d0']:#x}")
