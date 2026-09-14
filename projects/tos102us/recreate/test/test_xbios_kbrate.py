"""XBIOS Kbrate (function 35) @ $fc309a — the keyboard auto-repeat delay and interval.

Two adjacent BYTES at $0e82 and $0e83, counted in vertical blanks, reported as the WORD they form
and each replaceable on its own — except that they are not independent:

    tst.w   4(sp) / bmi .done       ; a negative DELAY skips the repeat store as well

so `Kbrate(-1, 3)` changes nothing at all. That is the case this file is built around; a
reconstruction testing each argument separately passes every other case here.

THE RESULT IS A WORD OF A 32-BIT REGISTER. `move.w $0e82,d0` leaves D0's high half as the caller had
it, so the core takes the caller's D0 as an argument and returns the whole register — and the cases
compare the whole of it. A `uint16_t` core would report the same number as one that had cleared the
high half, which is what Tickcal next door really does (`clr.l d0` first) and this does not.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_kbrate.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                              ctypes.c_uint16, ctypes.c_uint16]
_lib.xbios_kbrate.restype = ctypes.c_uint32

KEEP = 0xFFFF
# The ROM's power-on pair, as the boot leaves it: 15 vertical blanks before the repeat starts, 2
# between repeats. Read off the snapshot in its own case below rather than assumed here.
SNAPSHOT_DELAY, SNAPSHOT_REPEAT = 0x0F, 0x02
# A caller's D0 with a marked high half, for the cases that ask what the routine leaves alone.
MARKED_D0 = 0xDEAD_0000
# Three negative delays, each with a perfectly valid repeat beside it: the sign boundary, the one
# whose LOW BYTE looks positive (the ROM tests the word, not the byte it stores), and -1.
NEGATIVE_DELAY_PAIRS = ((KEEP, 3), (0x8000, 0), (0xFF80, 0x7FFF))


def run(delay, repeat, pokes=None, entry_d0=0, poison=True):
    def glue(lib, buf):
        return lib.xbios_kbrate(buf, entry_d0, delay & 0xFFFF, repeat & 0xFFFF)

    return case.run(addrs.XBIOS_KBRATE,
                    {"a5": 0, "d0": entry_d0,
                     "_pokes": {**case.word_args(delay, repeat), **(pokes or {})}},
                    glue, poison=poison)


def pair_poke(delay, repeat):
    return {addrs.KBRATE_DELAY: bytes([delay, repeat])}


def result(info):
    """The WORD the routine reports — D0's low half, which is all it sets."""
    return info["regs"]["d0"] & 0xFFFF


def test_the_snapshot_holds_the_rom_s_power_on_pair():
    assert BASE_IMAGE[addrs.KBRATE_DELAY] == SNAPSHOT_DELAY
    assert BASE_IMAGE[addrs.KBRATE_REPEAT] == SNAPSHOT_REPEAT
    assert result(run(KEEP, KEEP)) == (SNAPSHOT_DELAY << 8) | SNAPSHOT_REPEAT


def test_the_two_bytes_are_reported_as_one_word_in_that_order():
    """Delay in the high byte, repeat in the low — a reconstruction that swapped them would agree
    with the snapshot's own pair only if the two were equal, which they are not."""
    assert result(run(KEEP, KEEP, pair_poke(0x12, 0x34))) == 0x1234


def test_the_high_half_of_d0_is_the_caller_s_and_is_not_cleared():
    """There is no `clr.l`, unlike Tickcal next door: `move.w` writes half the register. The
    candidate's own result is compared against the whole of D0 by `case.run`, so this case pins the
    high half on both sides rather than only on the oracle's."""
    info = run(KEEP, KEEP, entry_d0=MARKED_D0)
    assert info["regs"]["d0"] == MARKED_D0 | ((SNAPSHOT_DELAY << 8) | SNAPSHOT_REPEAT)


@pytest.mark.parametrize("delay,repeat", ((0, 0), (1, 1), (0x0F, 0x02), (0x7F, 0x80), (0xFF, 0xFF),
                                          (0x1234, 0x5678)))
def test_a_non_negative_pair_stores_both_low_bytes(delay, repeat):
    """`move.b d1,...` twice: $1234 stores $34, which is where storing the word would diverge."""
    info = run(delay, repeat)
    assert result(info) == (SNAPSHOT_DELAY << 8) | SNAPSHOT_REPEAT, "the OLD pair is the result"
    assert info["writes"][addrs.KBRATE_DELAY] == (delay & 0xFF)
    assert info["writes"][addrs.KBRATE_REPEAT] == (repeat & 0xFF)


@pytest.mark.parametrize("repeat", (KEEP, 0x8000, 0xFFFE))
def test_a_negative_repeat_leaves_the_repeat_byte_alone(repeat):
    info = run(0x20, repeat)
    assert info["writes"][addrs.KBRATE_DELAY] == 0x20
    assert addrs.KBRATE_REPEAT not in info["writes"]


@pytest.mark.parametrize("delay,repeat", NEGATIVE_DELAY_PAIRS)
def test_a_negative_delay_skips_the_repeat_store_as_well(delay, repeat):
    """THE CASE THIS FILE EXISTS FOR. The ROM's `bmi` jumps past BOTH stores, so Kbrate(-1, 3) is a
    pure read — even though the repeat argument is perfectly valid on its own."""
    info = run(delay, repeat)
    assert not info["writes"], "a negative delay stored something"


def test_storing_the_pair_it_already_holds_is_still_two_stores():
    """A candidate that skipped a store whose value already matched would leave an image identical
    to the ORACLE's, so the byte compare cannot see it. WHAT CATCHES IT IS `poison=True` — the
    attribution pass inverts every oracle-written byte and re-runs both cores, and the canary
    survives wherever the candidate did not write. `info["writes"]` is the ORACLE's own ledger and
    could never redden for a candidate; it is asserted because it states a fact about the ROM."""
    info = run(SNAPSHOT_DELAY, SNAPSHOT_REPEAT, poison=True)
    assert info["writes"][addrs.KBRATE_DELAY] == SNAPSHOT_DELAY
    assert info["writes"][addrs.KBRATE_REPEAT] == SNAPSHOT_REPEAT
