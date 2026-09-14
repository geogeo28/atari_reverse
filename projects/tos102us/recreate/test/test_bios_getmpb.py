"""BIOS Getmpb (function 0) @ $fc0a46 — the initial GEMDOS memory parameter block.

The routine writes TWO structures: the three-longword MPB the caller supplies a pointer to, and the
single memory descriptor at $048e that both of its lists point at. The descriptor spans the TPA and
is rebuilt from `_membot` and `_memtop` on every call — so the sharp cases are the ones that move
those two, which is also what pins that the length is a SUBTRACTION and not a stored constant.

...and the sharpest is the one that moves them BY CALLING THE ROUTINE. The MPB pointer is the
caller's and nothing bounds it, so an MPB laid over the system variables has its own stores land on
`_membot` before the routine reads it. That is what fixes the ORDER of the ROM's eleven instructions
rather than merely their effect (`test_the_tpa_is_read_after_the_mpb_is_stored_and_not_before`).

The MPB goes in `staging.SCRATCH`, dead RAM the capture leaves empty, and the whole-image diff is
what proves both structures. The explicit reads below are a second, named statement of the fields'
layout, so a failure says which one moved rather than "a byte at $60004".
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case
import staging

_lib.bios_getmpb.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.bios_getmpb.restype = None

MPB_AT = staging.SCRATCH
MPB_BYTES = 12                  # three list heads, which is the whole structure

# An MPB laid over the system variables, positioned so that `mp_rover` — the LAST of the three
# stores — lands exactly on `_membot`, the variable the routine goes on to read.
ALIASED_MPB = addrs.SYSVAR_MEMBOT - addrs.MPB_ROVER


def long_at(image, address):
    return int.from_bytes(bytes(image[address:address + 4]), "big")


def argument_poke(mpb):
    return {abi.FIRST_ARG: struct.pack(">I", mpb)}


def tpa_poke(membot, memtop):
    return {addrs.SYSVAR_MEMBOT: struct.pack(">I", membot),
            addrs.SYSVAR_MEMTOP: struct.pack(">I", memtop)}


def run(mpb=MPB_AT, pokes=None, poison=True):
    def glue(lib, buf):
        lib.bios_getmpb(buf, mpb)

    return case.run(addrs.BIOS_GETMPB,
                    {"a5": 0, "_pokes": {**argument_poke(mpb), **(pokes or {})}},
                    glue, width=case.NO_RESULT, poison=poison)


def test_the_mpb_names_the_os_s_own_descriptor_twice():
    """`mp_mfl` and `mp_rover` are the SAME pointer — the free list's single entry — and `mp_mal` is
    empty. Three longwords, all of them stored.

    `mp_mal` is the one a byte compare cannot see: the staging band is already zero, so storing zero
    over it leaves an image identical to the one a candidate that skipped the store would leave.
    WHAT CATCHES THAT IS `poison=True` — the attribution pass inverts every oracle-written byte and
    re-runs both cores, and the canary survives wherever the candidate did not write. `info["writes"]`
    is the ORACLE's own ledger and can never redden for a candidate; it is asserted here because it
    states a fact about the ROM, namely that all three are stores rather than two stores and a skip.
    """
    info = run(poison=True)
    assert case.written_long(info, MPB_AT + addrs.MPB_FREE_LIST) == addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(info, MPB_AT + addrs.MPB_ALLOCATED_LIST) == 0
    assert case.written_long(info, MPB_AT + addrs.MPB_ROVER) == addrs.OS_MEMORY_DESCRIPTOR


def test_the_descriptor_spans_the_tpa_the_system_variables_describe():
    """...and it is the SNAPSHOT's TPA, so this case is about the machine that was captured."""
    membot = long_at(BASE_IMAGE, addrs.SYSVAR_MEMBOT)
    memtop = long_at(BASE_IMAGE, addrs.SYSVAR_MEMTOP)
    info = run()
    at = addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(info, at + addrs.MD_LINK) == 0, "the free list must end at its entry"
    assert case.written_long(info, at + addrs.MD_START) == membot
    assert case.written_long(info, at + addrs.MD_LENGTH) == memtop - membot
    assert case.written_long(info, at + addrs.MD_OWNER) == 0


@pytest.mark.parametrize("membot,memtop", ((0, 0x100000), (0x1000, 0x1000), (0xca00, 0xf8000),
                                           (0xf8000, 0xca00), (0x7fffffff, 0x80000000)))
def test_the_length_is_memtop_minus_membot_and_is_not_clamped(membot, memtop):
    """Including the two the ROM never produces: an EMPTY TPA (equal bounds) and an INVERTED one,
    whose length wraps to a huge unsigned value because the `sub.l` is not checked. A reconstruction
    that clamped at zero, or that stored a constant length, diverges on exactly these."""
    info = run(pokes=tpa_poke(membot, memtop))
    at = addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(info, at + addrs.MD_START) == membot
    assert case.written_long(info, at + addrs.MD_LENGTH) == (memtop - membot) & 0xFFFFFFFF


def test_the_tpa_is_read_after_the_mpb_is_stored_and_not_before():
    """THE ORDER OF THE ELEVEN INSTRUCTIONS, and the only case that can see it.

    `ALIASED_MPB` puts `mp_rover` on `_membot`, so the third store overwrites the variable the
    routine reads next: the descriptor it then builds describes a TPA starting at $048e, which is the
    descriptor's own address that the store just wrote there. A reconstruction that read `_membot`
    once at entry — the obvious C — would describe the TPA the machine had a moment earlier and
    diverge on both descriptor fields at once.
    """
    memtop = long_at(BASE_IMAGE, addrs.SYSVAR_MEMTOP)
    info = run(mpb=ALIASED_MPB)
    at = addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(info, ALIASED_MPB + addrs.MPB_ROVER) == addrs.OS_MEMORY_DESCRIPTOR, (
        "the case only means something while mp_rover really lands on _membot")
    assert case.written_long(info, at + addrs.MD_START) == addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(info, at + addrs.MD_LENGTH) == \
        (memtop - addrs.OS_MEMORY_DESCRIPTOR) & 0xFFFFFFFF


@pytest.mark.parametrize("offset", (0, 4, 0x100, staging.SCRATCH_BYTES - MPB_BYTES))
def test_the_mpb_is_written_wherever_the_caller_points(offset):
    """The pointer is the caller's and is used unchecked — so the routine's whole effect moves with
    it. An ODD offset is not tested: the 68000 faults on a misaligned longword, and that is the
    caller's bug rather than this routine's behaviour."""
    mpb = MPB_AT + offset
    info = run(mpb=mpb)
    assert case.written_long(info, mpb + addrs.MPB_FREE_LIST) == addrs.OS_MEMORY_DESCRIPTOR


def test_a_second_call_rebuilds_the_first_call_s_descriptor():
    """The descriptor is the OS's, not the caller's: two MPBs share it. Stated as a case because it
    is the surprising half of the design and a reconstruction that allocated per-MPB state would
    pass every case above."""
    first = run(mpb=MPB_AT)
    second = run(mpb=MPB_AT + 0x100)
    at = addrs.OS_MEMORY_DESCRIPTOR
    assert case.written_long(first, at + addrs.MD_START) == \
        case.written_long(second, at + addrs.MD_START)
    assert case.written_long(second, MPB_AT + 0x100 + addrs.MPB_FREE_LIST) == at
