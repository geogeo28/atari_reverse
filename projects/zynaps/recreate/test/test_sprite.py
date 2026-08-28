"""Differential tests for the boot-time sprite table builders (src/sprite.c):
ship_sprite_deinterleave @ 0x13bde, sprite_preshift8_2px @ 0x153f6, sprite_preshift4_4px @ 0x15420.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_SHIP_SPRITE_DEINTERLEAVE = 0x13bde
ENTRY_SPRITE_PRESHIFT8_2PX = 0x153f6
ENTRY_SPRITE_PRESHIFT4_4PX = 0x15420

# Scratch layout. The disjoint destination has to clear the largest source or table a case builds:
# 8 * FUZZ_MAX_FRAME_BYTES = 0x2000 bytes for the rotation tables, and SHIP_DST_BYTES for the split.
DISJOINT_SHIP_DST = abi.SCRATCH + 0x4000
DISJOINT_PRESHIFT_DST = abi.SCRATCH + 0x8000
OVERLAP_BASE = abi.SCRATCH + 0x2000

# ---- ship_sprite_deinterleave geometry (mirror of src/sprite.c) ----
SHIP_SPRITE_ROWS = 20
SHIP_SPRITE_HALF_BYTES = 10
SHIP_SPRITE_GAP = 1600
SHIP_SRC_BYTES = SHIP_SPRITE_ROWS * 2 * SHIP_SPRITE_HALF_BYTES     # 400: the record size `_start` steps by
SHIP_DST_BYTES = SHIP_SPRITE_GAP + SHIP_SPRITE_ROWS * SHIP_SPRITE_HALF_BYTES   # first byte past the second block

# ---- preshift-bank geometry ----
PRESHIFT_SLOTS = 8                    # `lsl.l #3,d5`
# Every width the game passes, direct and inherited. src/sprite.c's "SHIPPED WIDTHS" comment is the
# one home for where each comes from — 15 of the 16 call sites load D2 from an immediate, the 16th
# inherits it — and this tuple is the battery's use of that finding, not a second copy of it.
SHIPPED_FRAME_BYTES = (0x1e, 0x50, 0x5a, 0x6e, 0xa0, 0xc8)

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_ship_sprite_deinterleave.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_ship_sprite_deinterleave.restype = None
for _sym in ("g_sprite_preshift8_2px", "g_sprite_preshift4_4px"):
    getattr(harness._lib, _sym).argtypes = [_u8p] + [ctypes.c_uint32] * 3
    getattr(harness._lib, _sym).restype = ctypes.c_uint32


def _seed_spans(seed, spans):
    """Noise over every byte the run touches, as a poke dict.

    Overlapping spans are merged first: two pokes over one byte would leave the second silently
    winning, which reads as "both regions were seeded" when only one was.
    """
    merged = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    rng = random.Random(seed)
    return {lo: rng.randbytes(hi - lo) for lo, hi in merged}


# ================================================================= ship_sprite_deinterleave @ 0x13bde

def _ship_case(src, dst, seed, poison=False):
    """Call ship_sprite_deinterleave(A0 = src, A1 = dst) at its own entry.

    Both the source and the whole destination extent are seeded with noise, so a candidate that
    writes too few rows — or the right rows to the wrong block — leaves bytes that differ.
    """
    pokes = _seed_spans(seed, ((src, src + SHIP_SRC_BYTES), (dst, dst + SHIP_DST_BYTES)))
    regs = {"a0": src, "a1": dst, "_pokes": pokes}
    diffs, _ = differential(ENTRY_SHIP_SPRITE_DEINTERLEAVE, regs,
                            lambda lib, buf: lib.g_ship_sprite_deinterleave(buf, src, dst),
                            poison=poison)
    assert not diffs, f"src={src:#x} dst={dst:#x}\n{report(diffs)}"


def test_ship_disjoint():
    """The ordinary shape: a staged file read into a block far from it."""
    _ship_case(abi.SCRATCH, DISJOINT_SHIP_DST, seed=1)


def test_ship_in_place():
    """src == dst, which the last of the seven call sites does (`bsr` at 0x10132, both 0x577fe).

    This shape is NOT where the read/write ordering shows: the write cursor trails the read cursor
    by 10 bytes a row and the second block sits 1600 bytes past the 400-byte source, so no store
    ever lands on a byte still to be read. `test_ship_overlapping` is what holds the ordering. The
    case is here because it is the one geometry the game actually runs in place.
    """
    _ship_case(abi.SCRATCH, abi.SCRATCH, seed=2)


@pytest.mark.parametrize("delta", (-SHIP_SPRITE_GAP, -SHIP_SPRITE_HALF_BYTES, -2, 2, SHIP_SPRITE_HALF_BYTES,
                                   SHIP_SPRITE_ROWS * SHIP_SPRITE_HALF_BYTES, SHIP_SPRITE_GAP))
def test_ship_overlapping(delta):
    """Every overlap the two blocks and the source can have with each other, at row and word
    granularity.

    THIS is the ordering test: reversing the two half-row copies inside the row loop is caught by
    the +2, +10, +200 and -1600 offsets (measured) and by nothing else in the suite.
    """
    _ship_case(OVERLAP_BASE, OVERLAP_BASE + delta, seed=3 + delta)


def test_ship_attribution():
    """Poison every byte the oracle wrote: a candidate that skips a row stays canary there."""
    _ship_case(abi.SCRATCH, DISJOINT_SHIP_DST, seed=4, poison=True)
    _ship_case(abi.SCRATCH, abi.SCRATCH, seed=5, poison=True)


# ============================================== sprite_preshift8_2px @ 0x153f6 / _4-px @ 0x15420

_PRESHIFT_ENTRIES = {
    "2px": (ENTRY_SPRITE_PRESHIFT8_2PX, "g_sprite_preshift8_2px"),
    "4px": (ENTRY_SPRITE_PRESHIFT4_4PX, "g_sprite_preshift4_4px"),
}


def _preshift_case(variant, src, dst, frame_bytes, seed, poison=False):
    """Call one builder (A0 = src, A1 = dst, D2 = frame_bytes) at its own entry.

    The seeded span is the whole 8-slot bank, not just the slots the variant writes: the 4-px entry
    writes slots 2, 4 and 6 only, and leaving 1, 3, 5 and 7 as untouched zeroes would let a
    candidate that wrote them all pass.
    """
    width = frame_bytes & 0xffff
    pokes = _seed_spans(seed, ((src, src + width), (dst, dst + PRESHIFT_SLOTS * width)))
    regs = {"a0": src, "a1": dst, "d2": frame_bytes, "_pokes": pokes}
    entry, glue_name = _PRESHIFT_ENTRIES[variant]
    diffs, info = differential(entry, regs,
                               lambda lib, buf: getattr(lib, glue_name)(buf, src, dst, frame_bytes),
                               poison=poison)
    assert not diffs, f"{variant} src={src:#x} dst={dst:#x} frame_bytes={frame_bytes:#x}\n{report(diffs)}"
    # A1 is left one word past the last row's block-0 slot; the reconstruction returns the same.
    assert info["ret"] == info["regs"]["a1"], (
        f"{variant} frame_bytes={frame_bytes:#x}: end ptr cand={info['ret']:#x} "
        f"oracle={info['regs']['a1']:#x}")


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
@pytest.mark.parametrize("frame_bytes", SHIPPED_FRAME_BYTES)
def test_preshift_shipped_widths_in_place(variant, frame_bytes):
    """Exactly what every call site does: build the table over the row already sitting at `dst`."""
    _preshift_case(variant, abi.SCRATCH, abi.SCRATCH, frame_bytes, seed=frame_bytes)


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
@pytest.mark.parametrize("frame_bytes", (2, 4, 6, 0x50, 0x100, 0x400))
def test_preshift_widths_disjoint(variant, frame_bytes):
    """The source somewhere else entirely, down to the smallest width the loop can take (2 bytes,
    one word, one row)."""
    _preshift_case(variant, abi.SCRATCH, DISJOINT_PRESHIFT_DST, frame_bytes, seed=frame_bytes)


# The slot step each variant advances by between stores: one frame for the 2-px entry
# (`move.w d2,d3`), two for the 4-px one (`lsl.w #1,d3`). Mirrors src/sprite.c's *_SPAN constants.
_PRESHIFT_SLOT_SPAN = {"2px": 1, "4px": 2}


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
@pytest.mark.parametrize("slots_back,words_back", ((1, 1), (1, 2), (2, 1), (2, 2)))
def test_preshift_overlapping(variant, slots_back, words_back):
    """The source inside a slot the run WRITES, which is what makes the read/store order observable.

    Both builders read one word and then store it `copies` times before reading the next, so the
    order only shows when a store lands on a word not yet read. Row r stores at
    `dst + j*step + 2r`; row r' reads at `src + 2r'`. Putting the source `words_back` words below
    slot `slots_back` makes those the same address with r = r' - words_back, so the store happens
    FIRST and the later read must see it. Measured: without these cases, hoisting every read ahead
    of every store passes the whole suite.

    SYNTHETIC, AND JUSTIFIED — the same justification the ship battery's overlaps run on. The
    routines take a bare pointer pair and the game itself aliases them (all sixteen call sites pass
    A0 == A1), so behaviour under aliasing is something the game already relies on; these cases
    explore the same dimension at neighbouring offsets. What they do NOT do is invent a game record:
    the inputs are pointers, not fabricated entity or sprite data. The in-place shape the game
    actually uses cannot observe the order on its own, because every store lands in slots 1..7 and
    every read comes from slot 0.
    """
    frame_bytes = 0x50
    step = frame_bytes * _PRESHIFT_SLOT_SPAN[variant]
    dst = DISJOINT_PRESHIFT_DST
    src = dst + slots_back * step - words_back * 2
    _preshift_case(variant, src, dst, frame_bytes, seed=slots_back * 8 + words_back)


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
def test_preshift_frame_bytes_high_half_ignored(variant):
    """Every step reads D2 as a WORD (`move.w d2,d5`, `move.w d2,d3`, `lsr.w`, `sub.w`), so junk
    above it must change neither the table nor the end pointer."""
    rng = random.Random(0x153F6)
    for low in SHIPPED_FRAME_BYTES:
        _preshift_case(variant, abi.SCRATCH, abi.SCRATCH, hi_garbage(rng, low), seed=low)


# One word per row for 65536 rows: what a zero width makes the routine copy. Kept as its own
# constant because both the poke and the instruction cap are sized from it.
ZERO_WIDTH_ROWS = 0x10000
ZERO_WIDTH_BYTES = ZERO_WIDTH_ROWS * 2
INSNS_PER_ROW = 33   # move.w, moveq, 7 x (adda/ror/move.w/dbf), suba, lea, dbf — for the cap below


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
def test_preshift_zero_width_runs_the_full_word(variant):
    """frame_bytes 0 is the one input for which the `dbf`'s wrap is observable — and it IS reachable.

    `lsr.w #1,d2` leaves 0, `sub.w #$1,d2` wraps it to 0xffff, and the loop runs 65536 rows instead
    of none. It stays inside the image because the block step is `sign_ext16(0)` = 0: all seven (or
    three) stores of a row land on the same word, and the cursor advances only the two bytes
    `lea 2(a1),a1` gives it. So the run reads 64 Ki words and rewrites each one rotated.

    No call site passes 0 — this covers the routine's contract, not the game's data. Kept to a
    single case per variant: ~2.2M oracle instructions, well past the harness's default cap.
    """
    entry, glue_name = _PRESHIFT_ENTRIES[variant]
    src = dst = abi.SCRATCH                       # in place, which is the shape every caller uses
    pokes = {src: random.Random(variant).randbytes(ZERO_WIDTH_BYTES)}
    regs = {"a0": src, "a1": dst, "d2": 0, "_pokes": pokes}
    diffs, info = differential(entry, regs,
                               lambda lib, buf: getattr(lib, glue_name)(buf, src, dst, 0),
                               max_insns=ZERO_WIDTH_ROWS * INSNS_PER_ROW + 1000)
    assert not diffs, f"{variant} frame_bytes=0\n{report(diffs)}"
    assert info["ret"] == info["regs"]["a1"], (
        f"{variant} frame_bytes=0: end ptr cand={info['ret']:#x} oracle={info['regs']['a1']:#x}")


@pytest.mark.parametrize("variant", sorted(_PRESHIFT_ENTRIES))
def test_preshift_attribution(variant):
    """Poison the table: a candidate that writes one block too few stays canary in it."""
    _preshift_case(variant, abi.SCRATCH, abi.SCRATCH, 0x50, seed=0x50, poison=True)
    _preshift_case(variant, abi.SCRATCH, DISJOINT_PRESHIFT_DST, 0x50, seed=0x51, poison=True)


FUZZ_CHUNKS = 4
FUZZ_CASES = 240
# Widths stay even and modest so every store lands word-aligned (the 68000 faults otherwise) and
# the whole 8-block table stays inside the image. THE CAP IS LOAD-BEARING, not tidiness: from
# frame_bytes 0x2000 the step-back's `sub.w` borrows and the cursor drifts ~0x10000 bytes backwards
# per row, off the image entirely — where the oracle silently drops the access and the candidate
# indexes the host heap. `make guarded` only guards inputs a case actually drives, so this bound is
# what keeps the sweep meaningful. See STATUS.md for why that arm stays unpinned.
FUZZ_MAX_FRAME_BYTES = 0x400


def _fuzz_cases():
    rng = random.Random(0x15420)                 # seeded ONCE — every chunk replays this stream
    for i in range(FUZZ_CASES):
        yield (i,
               sorted(_PRESHIFT_ENTRIES)[rng.randrange(len(_PRESHIFT_ENTRIES))],
               2 * rng.randrange(1, FUZZ_MAX_FRAME_BYTES // 2 + 1),
               rng.randrange(2) == 0,           # in place?
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_preshift_fuzz(chunk):
    for i, variant, frame_bytes, in_place, seed in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        dst = abi.SCRATCH if in_place else DISJOINT_PRESHIFT_DST
        _preshift_case(variant, abi.SCRATCH, dst, frame_bytes, seed)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("SHIP_SPRITE_ROWS", "src/sprite.c", "SHIP_SPRITE_ROWS"),
    ("SHIP_SPRITE_HALF_BYTES", "src/sprite.c", "SHIP_SPRITE_HALF_BYTES"),
    ("SHIP_SPRITE_GAP", "src/sprite.c", "SHIP_SPRITE_GAP"),
    ("PRESHIFT_SLOTS", "include/sprite.h", "SPRITE_PRESHIFT_SLOTS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_SHIP_SPRITE_DEINTERLEAVE": "323c001345e9064022d8",
    "ENTRY_SPRITE_PRESHIFT8_2PX": "42853a02e78d9a423602",
    "ENTRY_SPRITE_PRESHIFT4_4PX": "42853a02e78d9a429a42",
}
