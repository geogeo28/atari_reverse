"""Differential tests for entity_kill_if_offscreen @ 0x13c9e (src/entity.c)."""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_ENTITY_KILL_IF_OFFSCREEN = 0x13c9e

ENTITY = abi.SCRATCH        # where the test parks the 44-byte record
ENTITY_STRIDE = 44           # the stride the enemy loop at 0x119ee walks (`lea 44(a2),a2`)
ENTITY_X, ENTITY_Y, ENTITY_ALIVE = 0x00, 0x04, 0x0e   # mirror of include/entity.h

# The box edges, so a case can be written as "one inside / one outside" rather than as bare numbers.
KEEP_X_MIN, KEEP_X_MAX = 0x30, 0x180
KEEP_Y_MIN, KEEP_Y_MAX = 0x10, 0xb0

harness._lib.g_entity_kill_if_offscreen.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_entity_kill_if_offscreen.restype = None


def _record(x, y, active, filler):
    """A whole 44-byte record: `filler` everywhere the routine must not touch."""
    rec = bytearray(filler.to_bytes(1, "big") * ENTITY_STRIDE)
    rec[ENTITY_X:ENTITY_X + 2] = (x & 0xffff).to_bytes(2, "big")
    rec[ENTITY_Y:ENTITY_Y + 2] = (y & 0xffff).to_bytes(2, "big")
    rec[ENTITY_ALIVE:ENTITY_ALIVE + 2] = (active & 0xffff).to_bytes(2, "big")
    return bytes(rec)


def _case(x, y, active, filler=0xa5, poison=False):
    pokes = {ENTITY: _record(x, y, active, filler)}
    regs = {"a2": ENTITY, "_pokes": pokes}
    diffs, _ = differential(ENTRY_ENTITY_KILL_IF_OFFSCREEN, regs,
                            lambda lib, buf: lib.g_entity_kill_if_offscreen(buf, ENTITY),
                            poison=poison)
    assert not diffs, f"x={x:#x} y={y:#x} active={active:#x}\n{report(diffs)}"


def test_inactive_record_is_left_alone():
    """`tst.w 14(a2)` / `beq` returns before the box is ever consulted — even far outside it.

    READ-VERIFIED, NOT PINNED, and it cannot be otherwise: the routine's only store is the `clr.b`,
    so on a record whose flag word is already 0 the early return and a fall-through to the clear
    leave byte-identical memory. Deleting the guard survives the whole suite (STATUS.md's ledger).
    The case is kept because it is the shape the game's own inactive slots have.
    """
    for x, y in ((0, 0), (-1, -1), (0x1000, 0x1000), (0x100, 0x50)):
        _case(x, y, active=0)


@pytest.mark.parametrize("x", (KEEP_X_MIN - 1, KEEP_X_MIN, KEEP_X_MIN + 1,
                               KEEP_X_MAX - 1, KEEP_X_MAX, KEEP_X_MAX + 1))
@pytest.mark.parametrize("y", (KEEP_Y_MIN - 1, KEEP_Y_MIN, KEEP_Y_MIN + 1,
                               KEEP_Y_MAX - 1, KEEP_Y_MAX, KEEP_Y_MAX + 1))
def test_box_edges(x, y):
    """Every combination of the four exclusive bounds, one step either side of each."""
    _case(x, y, active=0x0100)


@pytest.mark.parametrize("x,y", ((-1, 0x50), (0x100, -1), (-0x8000, -0x8000), (0x7fff, 0x7fff)))
def test_extreme_coordinates(x, y):
    """Coordinates at the far ends of the word, in and out of the keep band.

    IT DOES NOT PIN THE SIGNEDNESS, and used to claim it did. `ble`/`bge`/`blt` are signed, but the
    keep band (x 0x31..0x17f, y 0x11..0xaf) lies entirely in the positive half, so the two readings
    agree on every input: a value below 0x8000 IS its own unsigned reading, and one at or above
    0x8000 is either negative (signed: under the minimum) or huge (unsigned: over the maximum), and
    both answers are "kill". Measured — swapping both `int16_t` casts for `uint16_t` passes the
    whole suite. See STATUS.md's survivor ledger; the cases stay because extreme coordinates are
    still worth driving, not because they separate the two readings.
    """
    _case(x, y, active=0x0100)


@pytest.mark.parametrize("active", (0x0001, 0x00ff, 0x0100, 0xff00, 0x8000, 0xffff))
def test_flag_is_tested_wide_and_cleared_narrow(active):
    """The routine CLEARS 14(a2) as a byte — the high half only — though it TESTS it as a word.

    So a flag word whose low byte is set survives its own deactivation, and a candidate that
    cleared the WORD diverges on exactly these values.

    The other half of the width clash — `tst.w` against `tst.b` — is NOT pinned here and cannot be:
    the two spellings differ only for a flag word of 0x0001..0x00ff, and on exactly those the word
    test proceeds to `clr.b` a byte that is already 0. Both spellings leave the record untouched.
    See STATUS.md's mutation ledger.
    """
    _case(x=0, y=0, active=active)          # far outside the box: the clear always fires
    _case(x=0x100, y=0x50, active=active)   # ...and well inside it: the clear never does


def test_attribution():
    """Poison the record and re-run, so a candidate that never writes the flag cannot pass by luck.

    Only the CLEARING arm is meaningful. On the in-box arm the oracle's write set is empty, so
    `_attribution_check` has nothing to poison and merely repeats the plain pass — that arm is
    covered by the seeded record in `_case`, not by poison. Kept as one case, not two.
    """
    _case(x=0, y=0, active=0x0100, poison=True)


FUZZ_CHUNKS = 4
FUZZ_CASES = 600


def _fuzz_cases():
    rng = random.Random(0x13C9E)                 # seeded ONCE — every chunk replays this stream
    for i in range(FUZZ_CASES):
        # Coordinates cluster near the box so most cases land on a boundary rather than miles away.
        yield (i,
               rng.randrange(KEEP_X_MIN - 4, KEEP_X_MAX + 4) if i % 3 else rng.randrange(1 << 16),
               rng.randrange(KEEP_Y_MIN - 4, KEEP_Y_MAX + 4) if i % 3 else rng.randrange(1 << 16),
               rng.randrange(1 << 16), rng.randrange(256))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, x, y, active, filler in _fuzz_cases():
        if i % FUZZ_CHUNKS == chunk:
            _case(x, y, active, filler)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("KEEP_X_MIN", "src/entity.c", "ENTITY_KEEP_X_MIN"),
    ("KEEP_X_MAX", "src/entity.c", "ENTITY_KEEP_X_MAX"),
    ("KEEP_Y_MIN", "src/entity.c", "ENTITY_KEEP_Y_MIN"),
    ("KEEP_Y_MAX", "src/entity.c", "ENTITY_KEEP_Y_MAX"),
)
ENTRY_PROLOGUES = {"ENTRY_ENTITY_KILL_IF_OFFSCREEN": "4a6a000e6700002e0c6a"}
