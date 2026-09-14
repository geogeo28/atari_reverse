"""XBIOS Cursconf (function 21) @ $fc4698 — configure the BIOS console's alpha cursor.

An eight-arm jump through a table of signed WORD displacements at $fc46b2, into the console driver's
own code — Cursconf is implemented there rather than beside the rest of the XBIOS, because the state
it edits is the block the driver and the VDI escape share at $2994.

WHAT THIS FILE COVERS is the six arms whose whole body is that block, plus the out-of-range return:

    2 blink   `bset #0,($2994)`        3 steady  `bclr #0,($2994)`
    4 set rate `move.b 7(sp),($2982)`  5 get rate
    6 set spare `move.b 7(sp),($2995)` 7 get spare

Functions 0 and 1 — hide and show — are the cursor RENDERER at $fc45d8/$fc45be: they keep a hide
depth at $2840 and XOR the cursor cell into the screen through the console's font and line tables.
That is a body of its own and is NOT reconstructed here; the C halts on them rather than guessing,
and `test_the_two_drawing_arms_are_a_different_body` pins that they really are elsewhere.

WHAT EACH ARM LEAVES IN D0 is the subtle half, and it is not guessable from the arm alone: the
dispatch overwrites D0 with the arm's own DISPLACEMENT out of the jump table (`move.w TABLE(pc,d0.w),
d0`) before jumping. So 2, 3 and 4 — which set no result — return $0010, $0016 and $001c, not their
function numbers; 6 overwrites only D0's low BYTE, over a displacement whose high byte is zero; 5 and
7 open with `moveq #0,d0`; and only the out-of-range arm escapes before the overwrite and comes back
as itself. The expected values are READ OUT OF THE ROM below rather than written down, so a table
that moved would move the case with it.

AND THE WIDTH IS PART OF THAT CLAIM. Every arm but the two `get`s writes D0's low word or low byte
alone, so the caller's high half comes back; the `get` arms clear all 32 bits. The core therefore
takes the caller's D0 and returns the whole register, and `case.run` compares the whole of it — a
16-bit result would report the same number for both shapes.

The parametrized values are boundaries rather than sweeps: each arm's claim is a TRUNCATION (a word
argument stored as a byte, a byte read back zero-extended), so what separates a right answer from a
wrong one is 0, the top of the byte, and a word whose low byte is not its low word.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_cursconf.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                                ctypes.c_uint16, ctypes.c_uint16]
_lib.xbios_cursconf.restype = ctypes.c_uint32

BLINK_BIT = 1 << addrs.CON_FLAG_BLINKS
JUMP_TABLE_ENTRIES = addrs.CURSCONF_MAX_FUNCTION + 1
JUMP_TABLE_ENTRY_BYTES = 2                  # signed WORD displacements from the table's own address
# A caller's D0 with a marked high half, for the two cases that ask what each arm leaves of it.
MARKED_D0 = 0xDEAD_0000
# The snapshot's own blink rate, as the ROM's boot leaves it.
SNAPSHOT_BLINK_RATE = 30
# What a byte-wide store or read has to be tested at: zero, the top of the byte, and a WORD whose
# low byte is not its low word.
BYTE_BOUNDARIES = (0, 0xFF, 0x1234)
READ_BACK_BOUNDARIES = (0, 0x80, 0xFF)
# ...and what a read-modify-write of a flag byte has to be tested at: every other bit clear, every
# other bit set with bit 0 clear, and every bit set.
FLAG_BOUNDARIES = (0x00, 0xFE, 0xFF)


def run(function, rate=0, pokes=None, entry_d0=0, poison=True):
    def glue(lib, buf):
        return lib.xbios_cursconf(buf, entry_d0, function & 0xFFFF, rate & 0xFFFF)

    return case.run(addrs.XBIOS_CURSCONF,
                    {"a5": 0, "d0": entry_d0,
                     "_pokes": {**case.word_args(function, rate), **(pokes or {})}},
                    glue, poison=poison)


def result(info):
    return info["regs"]["d0"] & 0xFFFF


def displacement(function):
    """The word the dispatch leaves in D0 for an arm: that arm's entry in the ROM's jump table."""
    at = addrs.CURSCONF_JUMP_TABLE + JUMP_TABLE_ENTRY_BYTES * function
    return int.from_bytes(bytes(BASE_IMAGE[at:at + JUMP_TABLE_ENTRY_BYTES]), "big")


def flags_poke(flags):
    return {addrs.CON_STATE_FLAGS: bytes([flags])}


def test_the_two_drawing_arms_are_a_different_body():
    """Signed word displacements from the table's own address. Two of them point BACKWARDS, into the
    cursor renderer — which is exactly the claim that 0 and 1 are a body this file does not
    reconstruct."""
    targets = [addrs.CURSCONF_JUMP_TABLE + int.from_bytes(
        bytes(BASE_IMAGE[addrs.CURSCONF_JUMP_TABLE + JUMP_TABLE_ENTRY_BYTES * i:
                         addrs.CURSCONF_JUMP_TABLE + JUMP_TABLE_ENTRY_BYTES * (i + 1)]),
        "big", signed=True) for i in range(JUMP_TABLE_ENTRIES)]
    assert targets[addrs.CURSCONF_HIDE] < addrs.CURSCONF_JUMP_TABLE
    assert targets[addrs.CURSCONF_SHOW] < addrs.CURSCONF_JUMP_TABLE
    assert all(target > addrs.CURSCONF_JUMP_TABLE for target in targets[addrs.CURSCONF_BLINK:])
    assert len(set(targets)) == JUMP_TABLE_ENTRIES, "two functions would share an arm"


def test_the_snapshot_has_a_blinking_cursor_at_the_rom_s_default_rate():
    """The desktop as captured, so the default image already exercises one side of every flag case."""
    assert BASE_IMAGE[addrs.CON_STATE_FLAGS] & BLINK_BIT
    assert BASE_IMAGE[addrs.CON_BLINK_RATE] == SNAPSHOT_BLINK_RATE


@pytest.mark.parametrize("flags", FLAG_BOUNDARIES)
def test_blink_sets_bit_0_and_touches_no_other(flags):
    """`bset #0,(a4)` — a read-modify-write of the whole byte, so the other seven bits are output
    too even though nothing here changes them."""
    info = run(addrs.CURSCONF_BLINK, pokes=flags_poke(flags))
    assert info["writes"][addrs.CON_STATE_FLAGS] == flags | BLINK_BIT
    assert result(info) == displacement(addrs.CURSCONF_BLINK), (
        "the arm sets no result, so D0 keeps the dispatch's own jump-table displacement")


@pytest.mark.parametrize("flags", FLAG_BOUNDARIES)
def test_steady_clears_bit_0_and_touches_no_other(flags):
    info = run(addrs.CURSCONF_STEADY, pokes=flags_poke(flags))
    assert info["writes"][addrs.CON_STATE_FLAGS] == flags & ~BLINK_BIT
    assert result(info) == displacement(addrs.CURSCONF_STEADY)


@pytest.mark.parametrize("rate", BYTE_BOUNDARIES)
def test_set_rate_stores_the_low_byte_of_the_second_argument(rate):
    """`move.b 7(sp),-18(a4)`: the argument is a WORD and only its low byte is stored, so $1234
    sets the rate to $34."""
    info = run(addrs.CURSCONF_SET_RATE, rate)
    assert info["writes"][addrs.CON_BLINK_RATE] == (rate & 0xFF)
    assert result(info) == displacement(addrs.CURSCONF_SET_RATE)


@pytest.mark.parametrize("rate", READ_BACK_BOUNDARIES)
def test_get_rate_reports_the_byte_zero_extended(rate):
    """`moveq #0,d0` then `move.b`: $ff comes back as 255."""
    info = run(addrs.CURSCONF_GET_RATE, pokes={addrs.CON_BLINK_RATE: bytes([rate])})
    assert result(info) == rate
    assert not info["writes"], "a get arm wrote to memory"


@pytest.mark.parametrize("value", BYTE_BOUNDARIES)
def test_set_spare_stores_the_low_byte_and_leaves_it_in_d0(value):
    """The only set arm that touches D0: `move.b 7(sp),d0` before the store, so the RATE byte ends
    up in D0's low byte over the DISPLACEMENT — whose high byte is zero, so D0.w is the byte."""
    info = run(addrs.CURSCONF_SET_SPARE, value)
    assert info["writes"][addrs.CON_STATE_SPARE] == (value & 0xFF)
    assert displacement(addrs.CURSCONF_SET_SPARE) & 0xFF00 == 0, (
        "the arm's displacement has a high byte, so the result is no longer the rate alone")
    assert result(info) == (value & 0xFF)


@pytest.mark.parametrize("value", READ_BACK_BOUNDARIES)
def test_get_spare_reports_the_byte_zero_extended(value):
    info = run(addrs.CURSCONF_GET_SPARE, pokes={addrs.CON_STATE_SPARE: bytes([value])})
    assert result(info) == value
    assert not info["writes"]


def test_the_rate_and_the_spare_are_different_bytes():
    """$2982 and $2995 are 19 bytes apart and a reconstruction that confused them would pass every
    case above, where only one of the two is ever poked."""
    both = {addrs.CON_BLINK_RATE: b"\x11", addrs.CON_STATE_SPARE: b"\x22"}
    assert result(run(addrs.CURSCONF_GET_RATE, pokes=both)) == 0x11
    assert result(run(addrs.CURSCONF_GET_SPARE, pokes=both)) == 0x22


@pytest.mark.parametrize("function", (8, 0x8000, 0xFFFF))
def test_an_out_of_range_function_returns_without_doing_anything(function):
    """`cmp.w #7,d0 / bhi` — an UNSIGNED compare, so $8000 and $ffff are above 7 and not below 0.
    D0 keeps the function number, because nothing after the compare touches it."""
    info = run(function, 0x42)
    assert not info["writes"], "an out-of-range Cursconf changed the console state"
    assert result(info) == function


def test_the_high_half_of_d0_is_the_caller_s_and_is_not_cleared():
    """...for the arms that do not set a result. The dispatch's `move.w` writes half the register,
    and `bset`/`bclr` leave D0 entirely alone."""
    info = run(addrs.CURSCONF_BLINK, entry_d0=MARKED_D0)
    assert info["regs"]["d0"] == MARKED_D0 | displacement(addrs.CURSCONF_BLINK)


def test_a_get_arm_clears_the_high_half_of_d0():
    """...and the arms that DO set one open with `moveq #0,d0`, which is the whole register. The
    candidate's result is compared against the whole of D0, so this separates the two on both
    sides rather than only on the oracle's."""
    info = run(addrs.CURSCONF_GET_RATE, entry_d0=MARKED_D0, pokes={addrs.CON_BLINK_RATE: b"\x07"})
    assert info["regs"]["d0"] == 7
