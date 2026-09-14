"""BIOS Setexc (function 5) @ $fc0a72 — read, and optionally install, a 68000 exception vector.

This is the whole of vector installation in TOS: every AUTO program, every accessory and the OS's
own GEMDOS init go through these nine instructions. It does not decompile (COMPONENTS.md lists it
among the 73 Alcyon-shaped failures), so the reconstruction is from the disassembly and this battery
is what stands in for a decompiler's reading of it.

Three claims carry the file:

* the index is computed in a WORD (`lsl.w #2`) and then SIGN-EXTENDED into the address, so vector
  $4000 is vector 0 — tested, because a reconstruction using 32-bit arithmetic agrees everywhere
  else;
* there is no bounds check at all, so a vector number far past the 256-entry table addresses
  ordinary RAM and is installed there;
* `handler` is tested as a SIGNED LONG, so every address with bit 31 set is a read.

What a case may NOT reach is vector $2000..$3fff, whose index sign-extends to $ffff8000 — the I/O
page, which ROM mode refuses (../README.md). The C states that bound as a host-only assert.

EVERY SLOT THIS FILE TOUCHES IS DECLARED, as `CASE_SPANS`, and `test_boot_snapshot.py` folds them
into `CASE_FIELDS`. That matters more here than anywhere else in the project: the out-of-range cases
write at $1ffc, $4000 and $7ffc, far outside the vector table itself, and the snapshot has
non-deterministic regions BETWEEN those addresses. Without the declaration a future capture whose
mask grew over one of them would leave this battery resting on bytes two boots disagree about, and
nothing would say so.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case

_lib.bios_setexc.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16, ctypes.c_uint32]
_lib.bios_setexc.restype = ctypes.c_uint32

# The 68000's own table: 256 slots, and the end of what a vector NUMBER is supposed to name.
VECTOR_TABLE_BYTES = 0x400
# Above this a word-sized slot index is negative, and sign-extends into the I/O page.
SIGN_EXTENSION_BOUNDARY = 0x8000

# The documented "just tell me what is installed", and the whole family it belongs to.
READ_ONLY = 0xFFFFFFFF
# A plausible handler: an address in the free TPA, even, and with bit 31 clear so it is a store.
A_HANDLER = 0x00031234
# The one vector the handler-side cases use: an ordinary slot inside the table, so that what they
# vary is the HANDLER and nothing else.
A_VECTOR = 2


def argument_poke(vector, handler):
    """4(sp) is the vector NUMBER as a word, 6(sp) the handler as a longword."""
    return {abi.FIRST_ARG: struct.pack(">HI", vector & 0xFFFF, handler & 0xFFFFFFFF)}


def run(vector, handler, poison=True, pokes=None):
    def glue(lib, buf):
        return lib.bios_setexc(buf, vector & 0xFFFF, handler & 0xFFFFFFFF)

    return case.run(addrs.BIOS_SETEXC,
                    {"a5": 0, "_pokes": {**argument_poke(vector, handler), **(pokes or {})}},
                    glue, poison=poison)


def slot_of(vector):
    """Where the index arithmetic puts a vector: `lsl.w #2` INSIDE the word, then sign-extended.

    Every vector this file uses keeps the product below `SIGN_EXTENSION_BOUNDARY`, where that sign
    extension is the identity — the ones above it address the I/O page and no case can run them — so
    this stays a plain mask, and the case below is what keeps that true of the lists.
    """
    return (vector * addrs.VECTOR_BYTES) & 0xFFFF


def vector_in_snapshot(vector):
    at = slot_of(vector)
    return int.from_bytes(bytes(BASE_IMAGE[at:at + addrs.VECTOR_BYTES]), "big")


def stored(info, vector):
    """The longword the ORACLE wrote at the vector's slot, from its own ledger."""
    return case.written_long(info, slot_of(vector))


# The OS's own vectors, named rather than numbered — the four trap slots addrs.h already carries plus
# the VBL, which is where the snapshot was captured.
OS_VECTORS = (addrs.VECTOR_TRAP_GEMDOS // addrs.VECTOR_BYTES,
              addrs.VECTOR_TRAP_GEM // addrs.VECTOR_BYTES,
              addrs.VECTOR_TRAP_BIOS // addrs.VECTOR_BYTES,
              addrs.VECTOR_TRAP_XBIOS // addrs.VECTOR_BYTES,
              addrs.VECTOR_VBL // addrs.VECTOR_BYTES)
# Slots inside the table, including the reserved ones: the routine has no notion of a reserved slot.
INSTALLED_VECTORS = (0, 1, 2, 5, 0x1c, 0x21, 0x2d, 0x2e, 0xff)
# ...and past it, where the index walks into ordinary RAM: $400 and up is the system-variable block,
# and $1fff * 4 is $7ffc, inside GEMDOS's.
OUT_OF_RANGE_VECTORS = (0x100, 0x200, 0x7ff, 0x1000, 0x1fff)
# Vector numbers whose word-sized index lands back in LOW RAM: `vector mod $4000` must stay below
# $2000, or the index's top bit is set and it sign-extends into the I/O page — the bound the C states
# as a host-only assert and no case can run (the module docstring says why).
WRAPPING_VECTORS = (0x4000, 0x4021, 0x5000, 0x5fff)

ALL_VECTORS = (*OS_VECTORS, *INSTALLED_VECTORS, *OUT_OF_RANGE_VECTORS, *WRAPPING_VECTORS, A_VECTOR)

# Every byte this battery reads or writes, for `test_boot_snapshot.py`'s CASE_FIELDS: the vector
# table itself, plus each individual slot outside it that a case reaches. Spelt slot by slot rather
# than as one span up to the highest, because the snapshot's non-deterministic regions lie BETWEEN
# them — a span would claim bytes no case here touches and would redden on a perfectly good mask.
CASE_SPANS = ((0, VECTOR_TABLE_BYTES, "the 68000 vector table Setexc reads and writes"),
              *((slot, addrs.VECTOR_BYTES, f"the RAM slot Setexc reaches at {slot:#x}")
                for slot in sorted({slot_of(vector) for vector in ALL_VECTORS
                                    if slot_of(vector) >= VECTOR_TABLE_BYTES})))


def test_every_vector_this_battery_uses_lands_in_low_ram():
    """`slot_of` treats the index as unsigned, and these lists are what makes that honest. A vector
    added whose product passed $8000 would address the I/O page: ROM mode refuses such a run, and
    `slot_of` would have been reporting the wrong address to every assertion in the file."""
    for vector in ALL_VECTORS:
        assert slot_of(vector) + addrs.VECTOR_BYTES <= SIGN_EXTENSION_BOUNDARY, (
            f"vector {vector:#x} indexes {slot_of(vector):#x}, past this file's declared span")


@pytest.mark.parametrize("vector", OS_VECTORS)
def test_reading_an_os_vector_answers_what_the_boot_installed(vector):
    """The strongest available statement that the index arithmetic is right: these five longwords
    were put there by the ROM's own boot and are asserted to be in the ROM."""
    info = run(vector, READ_ONLY)
    handler = info["regs"]["d0"]
    assert handler == vector_in_snapshot(vector)
    assert addrs.ROM_BASE <= handler < addrs.ROM_BASE + addrs.ROM_BYTES
    assert not info["writes"], "a read-only Setexc wrote to memory"


@pytest.mark.parametrize("handler", (READ_ONLY, 0x80000000, 0xFFFF0000, 0xDEADBEEF))
def test_every_handler_with_bit_31_set_is_a_read(handler):
    """`bmi` on the longword. $80000000 is the boundary case and $deadbeef the one that looks most
    like a real argument."""
    info = run(A_VECTOR, handler)
    assert info["regs"]["d0"] == vector_in_snapshot(A_VECTOR)
    assert not info["writes"]


@pytest.mark.parametrize("vector", INSTALLED_VECTORS)
def test_installing_a_vector_reports_the_old_one_and_stores_the_new(vector):
    """Vector 0 included: the routine has no notion of a reserved slot, so it will happily overwrite
    the reset SSP at address 0."""
    info = run(vector, A_HANDLER)
    assert info["regs"]["d0"] == vector_in_snapshot(vector), "the OLD vector is the result"
    assert stored(info, vector) == A_HANDLER


@pytest.mark.parametrize("vector", OUT_OF_RANGE_VECTORS)
def test_there_is_no_bounds_check_on_the_vector_number(vector):
    """Past the 256-entry table the routine writes ordinary RAM. Reproduced rather than clamped."""
    info = run(vector, A_HANDLER)
    assert stored(info, vector) == A_HANDLER


@pytest.mark.parametrize("vector", WRAPPING_VECTORS)
def test_the_index_is_computed_in_a_word_and_wraps(vector):
    """`lsl.w #2`: $4000 * 4 is 0 in a word, so this IS vector 0 and the routine reports and installs
    the reset SSP. A reconstruction that multiplied in 32 bits would index past the image instead."""
    info = run(vector, A_HANDLER)
    assert stored(info, vector) == A_HANDLER
    assert info["regs"]["d0"] == vector_in_snapshot(vector)


def test_installing_the_handler_a_vector_already_holds_is_still_a_store():
    """A candidate that skipped a store whose value already matched would leave an image identical
    to the ORACLE's, so the byte compare cannot see it. WHAT CATCHES IT IS `poison=True` — the
    attribution pass inverts every oracle-written byte and re-runs both cores, and the canary
    survives wherever the candidate did not write. `info["writes"]` is the ORACLE's own ledger and
    could never redden for a candidate; `stored` is asserted here because it states a fact about the
    ROM, namely that this arm stores unconditionally rather than comparing first."""
    info = run(A_VECTOR, vector_in_snapshot(A_VECTOR), poison=True)
    assert stored(info, A_VECTOR) == vector_in_snapshot(A_VECTOR)
