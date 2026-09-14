"""BIOS Tickcal (function 6) @ $fc0a8a — milliseconds between two system-timer ticks.

`clr.l d0` then `move.w $442,d0`, so the answer is a WORD zero-extended into a longword. The two
things a case can separate here are the width of the read (a byte read would agree only below 256)
and the `clr.l` (without it the high half of D0 would be the caller's, and the ROM's own value 20 is
small enough that nothing else would show it).
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.bios_tickcal.restype = ctypes.c_uint32

# 200 Hz: 5 ms a tick. The ROM stores it as 20 — it is the MFP timer C's period in the units the
# variable is documented in, not 1000/200 — so the value is read off the snapshot rather than derived.
SNAPSHOT_TIMR_MS = 20


def timr_ms_poke(value):
    return {addrs.SYSVAR_TIMR_MS: value.to_bytes(2, "big")}


def run(pokes=None, regs=None, poison=True):
    def glue(lib, buf):
        return lib.bios_tickcal(buf)

    return case.run(addrs.BIOS_TICKCAL,
                    {"a5": 0, **(regs or {}), "_pokes": pokes or {}}, glue, poison=poison)


def test_the_snapshot_reports_the_machine_s_own_calibration():
    value = int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_TIMR_MS:addrs.SYSVAR_TIMR_MS + 2]), "big")
    assert value == SNAPSHOT_TIMR_MS
    assert run()["regs"]["d0"] == SNAPSHOT_TIMR_MS


@pytest.mark.parametrize("value", (0x100, 0x1234, 0xffff))
def test_the_whole_word_is_reported_and_not_sign_extended(value):
    """`clr.l` then `move.w`: $ffff comes back as 65535 and not as -1, and $100 is not 0 — which is
    the whole claim, so it is these three and not a sweep. A byte read agrees below $100 and a
    sign-extending one agrees below $8000, so the boundary of each is here and nothing else is."""
    assert run(timr_ms_poke(value))["regs"]["d0"] == value


def test_the_high_half_of_d0_is_cleared_and_not_inherited():
    """The `clr.l` that opens the routine, which nothing else in this file could see: the snapshot's
    own value is 20, so a missing clear would only show against a caller that left D0 dirty."""
    assert run(regs={"d0": 0xdead_beef})["regs"]["d0"] == SNAPSHOT_TIMR_MS
