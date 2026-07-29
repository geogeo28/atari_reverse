"""Pin the run-time half of the `tos_malloc_unused` waiver (kit: `emu._vet_no_malloc_over_program`).

Joust's program covers the TOS model's Malloc heap (`OS_HEAP_BASE = 0x20000` lies inside
`0x10000`–`0x2b7ae`), so `project.toml` waives the kit's import-time overlap check by declaring
that the game issues no GEMDOS Malloc. If that declaration were ever wrong the failure mode is the
worst one this system has: the oracle would hand out a block on top of the program, the candidate
mirrors the same `OS_HEAP_BASE` by convention and would scribble the identical bytes over the
identical program area, and the differential would come back CLEAN while proving nothing.

The kit therefore re-tests the claim after every oracle run instead of trusting the flag once. This
is the only project the guard is armed for (BuggyBoy's program ends below the heap), so it is the
only place it can be exercised — hence a Joust test for a kit behaviour.
"""
import pytest

import abi
import emu
import harness
from recreate_kit import harness as kit_harness   # the guard's internals aren't re-exported by `*`

RTS_STUB = b"\x4e\x75"

# Sizes that a GEMDOS Malloc rounds to ZERO bytes, so the call is fully serviced (it returns a block
# at OS_HEAP_BASE) while leaving the bump pointer exactly where it was. -1 is the canonical GEMDOS
# "how big is the largest free block?" query, which most Atari PRGs issue. The guard must key on the
# call happening, not on the pointer moving, or these two walk straight past it.
ZERO_ROUNDING_SIZES = (0xffffffff, 0)

_NO_OP_GLUE = lambda lib, buf: None   # noqa: E731 — the guard fires before the candidate ever runs


def malloc_stub(size):
    """A stub that asks TOS for a `size`-byte block, then unwinds its own 6-byte argument push:

        move.l #size,-(a7) ; move.w #$48,-(a7) ; trap #1 ; lea 6(a7),a7 ; rts
    """
    return (b"\x2f\x3c" + (size & 0xffffffff).to_bytes(4, "big")
            + b"\x3f\x3c\x00\x48" b"\x4e\x41" b"\x4f\xef\x00\x06" b"\x4e\x75")


def test_guard_is_armed_for_this_project():
    """Without the overlap the tests below would pass for the wrong reason (nothing to guard)."""
    assert kit_harness._HEAP_OVER_PROGRAM, (
        "OS_HEAP_BASE no longer lies inside Joust's program — the waiver in project.toml is now "
        "unnecessary, and this file no longer tests anything")
    assert kit_harness._CFG.tos_malloc_unused is True


def test_a_run_without_malloc_passes():
    diffs, info = harness.differential(abi.STUB, {"_pokes": {abi.STUB: RTS_STUB}}, _NO_OP_GLUE)
    assert not diffs
    assert info["regs"]["malloc_calls"] == 0
    assert info["regs"]["heap"] == harness.OS_HEAP_BASE, "nothing allocated, so the heap must not move"


@pytest.mark.parametrize("size", (0x1000,) + ZERO_ROUNDING_SIZES)
def test_a_run_that_mallocs_is_rejected(size):
    with pytest.raises(AssertionError, match="tos_malloc_unused"):
        harness.differential(abi.STUB, {"_pokes": {abi.STUB: malloc_stub(size)}}, _NO_OP_GLUE)


@pytest.mark.parametrize("size", ZERO_ROUNDING_SIZES)
def test_a_zero_rounding_malloc_is_serviced_without_moving_the_heap(size):
    """Why the guard counts calls: these sizes ARE serviced, and the bump pointer never moves.

    Read the oracle's globals after the guard has fired — they are what it saw. `heap` unchanged is
    exactly the state a pointer-based check would have read as "no allocation happened".
    """
    with pytest.raises(AssertionError, match="tos_malloc_unused"):
        emu.run(harness.make_image({abi.STUB: malloc_stub(size)}), abi.STUB)
    assert emu._LIB.osh_malloc_count() == 1
    assert emu._LIB.osh_heap() == harness.OS_HEAP_BASE


def test_the_guard_covers_a_bare_emu_run():
    """It lives in emu.run(), not differential(), so oracle-only runs are guarded too — including
    the poison re-run inside harness._attribution_check, where a candidate-perturbed image can
    steer the original somewhere the clean run never reached."""
    with pytest.raises(AssertionError, match="tos_malloc_unused"):
        emu.run(harness.make_image({abi.STUB: malloc_stub(0x1000)}), abi.STUB)
