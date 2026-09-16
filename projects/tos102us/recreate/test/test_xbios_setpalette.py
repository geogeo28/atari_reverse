"""XBIOS Setpalette (function $06) @ $fc0b06 — hand sixteen colour words to the vertical blank.

TWO INSTRUCTIONS, AND WHAT MAKES THEM WORTH A BATTERY IS WHAT IS ABSENT. Every neighbour in this
block of the ROM opens with a `tst`/`bmi` — "a negative argument means report only" — and this one
does not: `move.l 4(sp),$45a` / `rts`, unconditionally, for every argument there is. So `-1` is
stored like any other pointer, and a reconstruction that had copied the idiom from `Setscreen` next
door would pass a case that only ever passed it a real palette.

IT ALSO APPLIES NOTHING AND REPORTS NOTHING. The consumer is the VBL handler at $fc06de, which tests
`_colorptr` for zero, copies sixteen words from it into $ff8240, and CLEARS it ($fc074e..$fc0768) —
so a caller that passes 0 cancels a pending palette and one that passes -1 makes the next vertical
blank read sixteen words from $ffffffff. Neither is this routine's business and neither is checked
here: the handler is the interrupt half of this wave, and the boundary between the two is exactly the
longword this stores.

IT SETS NO RESULT, AND THAT IS A CLAIM ABOUT D0. `move.l 4(sp),$45a / rts` never touches the
register, so the caller's own comes back whole — the core takes the entering D0 and returns it, and
`case.FULL_D0` compares all 32 bits of it against the D0 the ROM left. A `void` core would have said
nothing here and would have agreed with one that left the stored pointer in D0.

ARGUMENTS: one longword at 4(sp), and the dispatcher's A5 = 0 — which IS load-bearing, since the ROM
reaches the variable as `$45a(a5)`.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case

_lib.xbios_setpalette.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32]
_lib.xbios_setpalette.restype = ctypes.c_uint32

# What the captured desktop holds: nothing pending. Asserted rather than assumed, because the case
# that stores 0 would otherwise be storing the value already there without saying so.
SNAPSHOT_COLORPTR = 0
# A caller's D0 with both halves marked, for the claim that the routine leaves the whole register.
MARKED_D0 = 0xDEAD_BEEF


def argument_poke(palette):
    return {abi.FIRST_ARG: struct.pack(">I", palette & 0xFFFFFFFF)}


def run(palette, entry_d0=0, poison=True):
    def glue(lib, buf):
        return lib.xbios_setpalette(buf, entry_d0, palette & 0xFFFFFFFF)

    return case.run(addrs.XBIOS_SETPALETTE,
                    {"a5": 0, "d0": entry_d0, "_pokes": argument_poke(palette)}, glue,
                    poison=poison)


def test_the_snapshot_has_no_palette_pending():
    assert int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_COLORPTR:addrs.SYSVAR_COLORPTR + 4]),
                          "big") == SNAPSHOT_COLORPTR


# Every pointer that says something different about the store: an ordinary address in the TPA; the
# largest NON-negative longword and the smallest negative one, which is the boundary the absent
# `bmi` would have been about; $ffffffff, the spelling that means "keep" in `Setscreen`, `Kbrate`,
# `Keytbl` and `Setexc` and means nothing here; and 0, which the VBL reads as "nothing pending" and
# is therefore the only argument with a meaning of its own — a meaning this routine still does not
# act on.
PALETTES = (0x000A_0000, 0x7FFF_FFFF, 0x8000_0000, 0xFFFF_FFFF, 0x0000_0000)


@pytest.mark.parametrize("palette", PALETTES)
def test_every_argument_is_stored_including_the_negative_ones(palette):
    """THE CASE THIS FILE EXISTS FOR. Read back out of the ORACLE's write ledger, so an argument the
    routine skipped is a KeyError naming `_colorptr` rather than a stale byte that reads right."""
    assert case.written_long(run(palette), addrs.SYSVAR_COLORPTR) == palette


def test_storing_the_value_already_there_is_still_a_store():
    """0 over the snapshot's own 0 — the case the poison pass is for: with the attribution run the
    byte is inverted first, so a reconstruction that skipped the store reds instead of matching by
    coincidence. Without it this call and an empty routine are the same image."""
    assert case.written_long(run(SNAPSHOT_COLORPTR), addrs.SYSVAR_COLORPTR) == SNAPSHOT_COLORPTR


def test_it_touches_nothing_else():
    """The whole effect is four bytes: no hardware store — the palette itself is the VBL's — and no
    other image byte."""
    info = run(0x000A_0000, poison=False)
    assert sorted(info["writes"]) == [addrs.SYSVAR_COLORPTR + i for i in range(4)]
    assert info["regs"]["hw_writes"] == [], "Setpalette wrote the shifter; that is the VBL's job"


@pytest.mark.parametrize("palette", (0x000A_0000, 0xFFFF_FFFF))
def test_the_callers_whole_d0_comes_back(palette):
    """`rts` with D0 untouched, on the only arm there is. `case.run` compares the candidate's result
    against the ROM's D0 on every case in this file; this one marks BOTH halves of the register, so
    a core that had returned the pointer it stored — or cleared what the ROM leaves alone — is the
    one thing separable here."""
    info = run(palette, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row. `ninsns` counts one more than the instructions executed
    (the reset iteration; shim.c's run loop says why)."""
    from harness import emu, make_image
    _final, _writes, regs = emu.run(make_image(argument_poke(0x000A_0000)), addrs.XBIOS_SETPALETTE,
                                    {"a5": 0})
    assert (regs["ninsns"], regs["cycles"]) == (3, 84), (
        f"Setpalette now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
