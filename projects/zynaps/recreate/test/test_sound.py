"""Differential tests for sound_lookup_tune @ 0x16b32 (src/sound.c)."""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_SOUND_LOOKUP_TUNE = 0x16b32

A_TUNE_INDEX = 0x17058   # mirror of include/sound.h
A_TUNE_DATA = 0x171e8
# The first sound number whose table word has bit 15 set (0x80c8), and so the first that resolves
# BELOW A_TUNE_DATA once `adda.w` sign-extends it. Measured off the image, not inferred: the offsets
# are NOT ascending up to here — they climb from 0x019a to 0x04d2 over numbers 0..10, drop back at
# 11/12/13 (0x0006, 0x0081, 0x0107), then climb again. names.txt reads the real table as 45 entries,
# which is why this is also where the data ends; the two facts coincide but are not the same claim.
TUNE_FIRST_NEGATIVE_OFFSET = 45
TUNE_BOOT_NUMBER = 0x0b      # what `_start` fires at 0x1007c (`moveq #$b,d1`)

# The routine writes no memory at all — its answers are A1 and D1 — so the stub stores them where
# the image diff can see them. Order matters: it is the order test/abi.py pokes the stores in.
_STORES = ("a1", "d1")

harness._lib.g_sound_lookup_tune.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                             ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_sound_lookup_tune.restype = None


def _case(number, poison=False):
    """Call sound_lookup_tune(D1 = number) through the stub that stores A1 then D1 at A0."""
    pokes = abi.register_call_pokes(ENTRY_SOUND_LOOKUP_TUNE, _STORES)
    pokes[abi.RESULT] = bytes(range(0x61, 0x69))     # neither answer, so silence shows up
    regs = {"d1": number, "a0": abi.RESULT, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_sound_lookup_tune(buf, number, abi.RESULT),
                            poison=poison)
    assert not diffs, f"number={number:#x}\n{report(diffs)}"


FUZZ_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_every_tune_number(chunk):
    """All 256 values `andi.w #$ff,d1` can leave — the routine's whole input range.

    Exhaustive rather than sampled because the table is not uniform: names.txt reads 45 real
    entries, and past those the bytes are tune data being read as offsets, 52 of them with bit 15
    set. Those are what exercise `adda.w`'s SIGN EXTENSION — number 45 resolves to 0xf2b0, below the
    load base — so dropping `sign_ext16` from the reconstruction turns this test red there.

    Sharded four ways so no single item gates the wall clock; every chunk walks the same range and
    takes its own quarter, so coverage is byte-identical to one 256-case loop.
    """
    assert TUNE_BOOT_NUMBER < 0x100, "the boot tune must be inside the range this test walks"
    for number in range(chunk, 0x100, FUZZ_CHUNKS):
        _case(number)


def test_only_the_low_byte_indexes():
    """`andi.w #$ff,d1` masks to a byte, and nothing else ever reads the rest of D1 — so a number
    with junk above its low byte must resolve to the same entry, and D1's HIGH WORD must come back
    untouched (every step of the routine is a word or byte operation)."""
    rng = random.Random(ENTRY_SOUND_LOOKUP_TUNE)
    for low in (0, 1, TUNE_BOOT_NUMBER, 0xff,
                TUNE_FIRST_NEGATIVE_OFFSET - 1, TUNE_FIRST_NEGATIVE_OFFSET):
        _case(hi_garbage(rng, low))
        _case(low | 0xff00)


@pytest.mark.parametrize("number", (0, TUNE_BOOT_NUMBER, TUNE_FIRST_NEGATIVE_OFFSET, 0xff))
def test_attribution(number):
    """Poison both result longwords: a candidate that stores only one of them stays canary."""
    _case(number, poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_TUNE_INDEX", "include/sound.h", "A_tune_index"),
    ("A_TUNE_DATA", "include/sound.h", "A_tune_data"),
)
ENTRY_PROLOGUES = {"ENTRY_SOUND_LOOKUP_TUNE": "43fa0524024100ffe349"}
