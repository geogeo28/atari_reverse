"""Differential tests for the sprite banks and the blitters that read them (src/sprite.c):
ship_sprite_deinterleave @ 0x13bde, sprite_bank_build_preshift8 @ 0x153c0,
sprite_preshift8_2px @ 0x153f6, sprite_preshift4_4px @ 0x15420, asteroid_preshift_bank @ 0x15758,
mothership_sprite_expand @ 0x157ca, mothership_sprite_preshift @ 0x15838,
draw_sprite_masked @ 0x15ace and draw_sprite_masked_collide @ 0x15b7c.

THE BUILDERS RUN ON THE GAME'S OWN GRAPHIC FILES wherever one exists. `_start` reads each .DAT off
the disk and hands it straight to a builder, so ../bin/disk holds the exact bytes each of them is
really given — and a masked sprite's edges (0xffff mask words, wholly transparent margin cells) are
what make a carry chain's boundaries visible as something other than an arbitrary bit.
"""
import ctypes
import pathlib
import random

import pytest

import abi
import emu
import harness

REC = pathlib.Path(__file__).resolve().parents[1]
from harness import differential, hi_garbage, report

ENTRY_SHIP_SPRITE_DEINTERLEAVE = 0x13bde
ENTRY_SPRITE_BANK_BUILD_PRESHIFT8 = 0x153c0
ENTRY_SPRITE_PRESHIFT8_2PX = 0x153f6
ENTRY_SPRITE_PRESHIFT4_4PX = 0x15420
ENTRY_ASTEROID_PRESHIFT_BANK = 0x15758
ENTRY_MOTHERSHIP_SPRITE_EXPAND = 0x157ca
ENTRY_MOTHERSHIP_SPRITE_PRESHIFT = 0x15838
ENTRY_DRAW_SPRITE_MASKED = 0x15ace
ENTRY_DRAW_SPRITE_MASKED_COLLIDE = 0x15b7c

# Scratch layout. The disjoint destination has to clear the largest source or table a case builds:
# 8 * FUZZ_MAX_FRAME_BYTES = 0x2000 bytes for the rotation tables, and SHIP_DST_BYTES for the split.
DISJOINT_SHIP_DST = abi.SCRATCH + 0x4000
DISJOINT_PRESHIFT_DST = abi.SCRATCH + 0x8000
OVERLAP_BASE = abi.SCRATCH + 0x2000
# ...and the whole-file bank builder's own pair, clear of everything above and of the blit arena at
# +0x10000. The largest bank any case builds is 8 frames x 8 slots x 0xa0 = 0x2800 bytes.
BANK_BUILD_SRC = abi.SCRATCH + 0xa000
BANK_BUILD_DST = abi.SCRATCH + 0xd000

# ---- ship_sprite_deinterleave geometry (mirror of src/sprite.c) ----
SHIP_SPRITE_ROWS = 20
SHIP_SPRITE_HALF_BYTES = 10
SHIP_SPRITE_GAP = 1600
SHIP_SRC_BYTES = SHIP_SPRITE_ROWS * 2 * SHIP_SPRITE_HALF_BYTES     # 400: the record size `_start` steps by
SHIP_DST_BYTES = SHIP_SPRITE_GAP + SHIP_SPRITE_ROWS * SHIP_SPRITE_HALF_BYTES   # first byte past the second block

# ---- preshift-bank geometry ----
PRESHIFT_SLOTS = 8                    # `lsl.l #3,d5`
PRESHIFT_SLOT_SHIFT = 3               # the same count spelt as a shift (`lsl.l #3,d3` at 0x153c2)
# Every width the game passes, direct and inherited. src/sprite.c's "SHIPPED WIDTHS" comment is the
# one home for where each comes from — 15 of the 16 call sites load D2 from an immediate, the 16th
# inherits it — and this tuple is the battery's use of that finding, not a second copy of it.
SHIPPED_FRAME_BYTES = (0x1e, 0x50, 0x5a, 0x6e, 0xa0, 0xc8)

# ---- mirrors of include/video.h ----
# Declared once here rather than beside the battery that first needed one, so that a second use —
# `A_backdrop_page0`, which is BOTH the front end's compose page and asteroid bank 0 — cannot become
# a bare literal further down the file. Every one of these is in MIRRORS at the bottom.
A_SCREEN_BACK = 0x1797e
A_BACKDROP_PAGE0 = 0x1a8ae
SCREEN_BYTES = 32000
SCREEN_PIXELS_WIDE = 320
PLAYFIELD_TOP_Y = 32
PLAYFIELD_ROWS = 144
PLAYFIELD_BOTTOM_Y = PLAYFIELD_TOP_Y + PLAYFIELD_ROWS

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_asteroid_preshift_bank.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_asteroid_preshift_bank.restype = None
harness._lib.g_mothership_sprite_expand.argtypes = [_u8p]
harness._lib.g_mothership_sprite_expand.restype = None
harness._lib.g_draw_sprite_masked.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_draw_sprite_masked.restype = None
harness._lib.g_draw_sprite_masked_collide.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_draw_sprite_masked_collide.restype = None
harness._lib.g_mothership_sprite_preshift.argtypes = [_u8p]
harness._lib.g_mothership_sprite_preshift.restype = None
harness._lib.g_sprite_bank_build_preshift8.argtypes = [_u8p] + [ctypes.c_uint32] * 4
harness._lib.g_sprite_bank_build_preshift8.restype = None
harness._lib.g_ship_sprite_deinterleave.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_ship_sprite_deinterleave.restype = None
for _sym in ("g_sprite_preshift8_2px", "g_sprite_preshift4_4px"):
    getattr(harness._lib, _sym).argtypes = [_u8p] + [ctypes.c_uint32] * 3
    getattr(harness._lib, _sym).restype = ctypes.c_uint32


# ================================================================= ship_sprite_deinterleave @ 0x13bde

def _ship_case(src, dst, seed, poison=False):
    """Call ship_sprite_deinterleave(A0 = src, A1 = dst) at its own entry.

    Both the source and the whole destination extent are seeded with noise, so a candidate that
    writes too few rows — or the right rows to the wrong block — leaves bytes that differ.
    """
    pokes = abi.seed_spans(seed, ((src, src + SHIP_SRC_BYTES), (dst, dst + SHIP_DST_BYTES)))
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
    pokes = abi.seed_spans(seed, ((src, src + width), (dst, dst + PRESHIFT_SLOTS * width)))
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


# ======================================================== asteroid_preshift_bank @ 0x15758

SPRITE_MASKED_ROW_WORDS = 5
SPRITE_MASKED_ROW_BYTES = 10
SPRITE_MASK_TRANSPARENT = 0xffff
ASTEROID_FRAME_ROWS = 32
ASTEROID_FRAME_CELLS = 3
ASTEROID_CELL_BYTES = ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES
ASTEROID_FRAME_BYTES = ASTEROID_FRAME_CELLS * ASTEROID_CELL_BYTES
ASTEROID_BANK_BYTES = PRESHIFT_SLOTS * ASTEROID_FRAME_BYTES

# The six banks `_start` preshifts (`lea $1a8ae.l,a0` .. `lea $23eae.l,a0` at 0x15720..0x15752),
# which is also the store video.h's A_backdrop_page0 names — one buffer, two uses in sequence.
ASTEROID_BANKS = tuple(A_BACKDROP_PAGE0 + index * ASTEROID_BANK_BYTES
                       for index in range(6))
# ...and the file the builder at 0x156ac expands into them: six asteroid SIZES of eight frames, one
# 640-byte source block each (`lea 640(a0),a0`), read by `load_file` with d1 = 0xf00 = its own size.
ASTEROID_SOURCE_FILE = "BIGAST.DAT"
ASTEROID_SOURCE_BLOCK_BYTES = ASTEROID_FRAME_ROWS * 2 * SPRITE_MASKED_ROW_BYTES

def _asteroid_bank_from_the_real_file(size_index):
    """One bank as the builder at 0x156ac leaves it: eight identical copies of one 48x32 frame,
    two cells straight out of BIGAST.DAT and a wholly transparent third.

    Built from the game's own bytes rather than from noise because this is the exact input the
    routine is handed on the real machine — the noise cases below cover the rest of its domain.
    """
    source = (harness.PRG.parent / "disk" / ASTEROID_SOURCE_FILE).read_bytes()
    block = source[size_index * ASTEROID_SOURCE_BLOCK_BYTES:][:ASTEROID_SOURCE_BLOCK_BYTES]
    assert len(block) == ASTEROID_SOURCE_BLOCK_BYTES, f"{ASTEROID_SOURCE_FILE} is short"

    cells = [bytearray(), bytearray(), bytearray()]
    blank = SPRITE_MASK_TRANSPARENT.to_bytes(2, "big") + bytes(SPRITE_MASKED_ROW_BYTES - 2)
    for row in range(ASTEROID_FRAME_ROWS):
        at = row * 2 * SPRITE_MASKED_ROW_BYTES
        cells[0] += block[at:at + SPRITE_MASKED_ROW_BYTES]
        cells[1] += block[at + SPRITE_MASKED_ROW_BYTES:at + 2 * SPRITE_MASKED_ROW_BYTES]
        cells[2] += blank
    return bytes(cells[0] + cells[1] + cells[2]) * PRESHIFT_SLOTS


def _guard_bands_only(lo, hi):
    """The two margins around [lo, hi) and not the span itself.

    Used where the span's own bytes are REAL GAME DATA: seeding it and then poking the real bytes
    over the top would make the case depend on `harness.make_image` applying a poke dict in
    insertion order, which is the hazard `abi.seed_spans` exists to avoid rather than to rely on.
    """
    return ((lo - abi.GUARD_BYTES, lo), (hi, hi + abi.GUARD_BYTES))


def _asteroid_case(bank, contents, seed, poison=False):
    """Call asteroid_preshift_bank(A0 = bank) at its own entry over `contents`, or noise if None."""
    span = (bank, bank + ASTEROID_BANK_BYTES)
    if contents is None:
        pokes = abi.seed_spans(seed, (span,), guard=abi.GUARD_BYTES)
    else:
        assert len(contents) == ASTEROID_BANK_BYTES, "a bank is eight whole frames"
        pokes = abi.seed_spans(seed, _guard_bands_only(*span))
        pokes[bank] = contents
    diffs, _ = differential(ENTRY_ASTEROID_PRESHIFT_BANK, {"a0": bank, "_pokes": pokes},
                            lambda lib, buf: lib.g_asteroid_preshift_bank(buf, bank), poison=poison)
    assert not diffs, f"bank={bank:#x}\n{report(diffs)}"


@pytest.mark.parametrize("size_index", range(len(ASTEROID_BANKS)))
def test_asteroid_preshift_bank_real_data(size_index):
    """Every one of the six banks, holding the frame the game's own builder would have put there.

    Real data is what makes the MASK column's carry-in visible for what it is: the shipped frames
    have 0xffff mask words at their edges and a wholly transparent third cell, so a shift that fed
    the mask a 0 would tear a hole down the sprite's left edge rather than merely differing.
    """
    _asteroid_case(ASTEROID_BANKS[size_index], _asteroid_bank_from_the_real_file(size_index),
                   seed=size_index)


@pytest.mark.parametrize("bank", (ASTEROID_BANKS[0], abi.SCRATCH))
def test_asteroid_preshift_bank_noise(bank):
    """Noise over the whole bank — the routine has no data-dependent branch, so every bit pattern
    is a legal input and noise is what separates the five word columns and the three cells from one
    another. A bank that is not one of the six says the base comes from A0."""
    _asteroid_case(bank, None, seed=bank)


def test_asteroid_preshift_bank_attribution():
    """Poison: frame 0 is never written, so a candidate that shifted it would differ; a candidate
    that skipped frame 7's fourteenth pass stays canary."""
    _asteroid_case(ASTEROID_BANKS[0], _asteroid_bank_from_the_real_file(0), seed=0x15758,
                   poison=True)


# ===================================================== mothership_sprite_expand @ 0x157ca

# ---- mirrors of include/mothership.h, which OWNS the boss's data ----
A_MOTHERSHIP_SPRITE_SOURCE = 0x5ed7e
A_MOTHERSHIP_SPRITE_BANK = 0x310ae
BOSS_SPRITE_ROWS = 40
BOSS_SPRITE_SOURCE_CELLS = 4
BOSS_SPRITE_FRAME_CELLS = 5
BOSS_SPRITE_CELL_BYTES = BOSS_SPRITE_ROWS * SPRITE_MASKED_ROW_BYTES
BOSS_SPRITE_FRAME_BYTES = BOSS_SPRITE_FRAME_CELLS * BOSS_SPRITE_CELL_BYTES
BOSS_SPRITE_SOURCE_BYTES = BOSS_SPRITE_ROWS * BOSS_SPRITE_SOURCE_CELLS * SPRITE_MASKED_ROW_BYTES
BOSS_SPRITE_BANK_BYTES = PRESHIFT_SLOTS * BOSS_SPRITE_FRAME_BYTES

# The five boss sprites on the disk, each exactly the 64x40 masked block this routine expands.
BOSS_SPRITE_FILES = tuple(f"MOTHER{n}.DAT" for n in range(1, 6))


def _mothership_case(source, seed, poison=False):
    src_span = (A_MOTHERSHIP_SPRITE_SOURCE, A_MOTHERSHIP_SPRITE_SOURCE + BOSS_SPRITE_SOURCE_BYTES)
    bank_span = (A_MOTHERSHIP_SPRITE_BANK, A_MOTHERSHIP_SPRITE_BANK + BOSS_SPRITE_BANK_BYTES)
    if source is None:
        pokes = abi.seed_spans(seed, (src_span, bank_span), guard=abi.GUARD_BYTES)
    else:
        # The bank is the output and gets noise with its margins; the source is the disk's own
        # bytes, so only ITS margins are seeded — see `_guard_bands_only`.
        bank_lo, bank_hi = bank_span
        widened_bank = (bank_lo - abi.GUARD_BYTES, bank_hi + abi.GUARD_BYTES)
        pokes = abi.seed_spans(seed, _guard_bands_only(*src_span) + (widened_bank,))
        pokes[A_MOTHERSHIP_SPRITE_SOURCE] = source
    diffs, _ = differential(ENTRY_MOTHERSHIP_SPRITE_EXPAND, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_sprite_expand(buf), poison=poison)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("name", BOSS_SPRITE_FILES)
def test_mothership_sprite_expand_real_sprites(name):
    """Each boss sprite the disk ships, at the address `load_file` reads it to. Their length is the
    pin on the geometry: 1600 bytes is exactly 40 rows of four 10-byte masked cells."""
    source = (harness.PRG.parent / "disk" / name).read_bytes()
    assert len(source) == BOSS_SPRITE_SOURCE_BYTES, f"{name} is not one 64x40 masked block"
    _mothership_case(source, seed=BOSS_SPRITE_FILES.index(name))


def test_mothership_sprite_expand_noise():
    """Noise in place of a sprite, which is what separates the four source cells from each other:
    a real sprite is symmetric enough that a transposed cell could still match."""
    _mothership_case(None, seed=0x157ca)


def test_mothership_sprite_expand_attribution():
    """Poison: the synthesised fifth cell is the arm this catches — its mask word is 0xffff and its
    four planes are zero, and zeroes over poison are indistinguishable from nothing written unless
    the canary is there to differ."""
    _mothership_case((harness.PRG.parent / "disk" / BOSS_SPRITE_FILES[0]).read_bytes(),
                     seed=0x157cb, poison=True)


# ============================================================ draw_sprite_masked @ 0x15ace

# ---- mirrors of include/entity.h ----
ENTITY_X = 0x00
ENTITY_Y = 0x04
ENTITY_HEIGHT = 0x08
ENTITY_SPRITE = 0x0a
ENTITY_STRIDE = 0x2c

SPRITE_X_PHASE_MASK = 0xf

# The two D2 values the game's own call sites load: `move.w #$3e8,d2` at 0x1590a and
# `move.w #$1e0,d2` at 0x159d8. They are DERIVED here rather than transcribed, because that is the
# claim being made — D2 is half a preshift frame (src/sprite.c's `draw_sprite_masked` comment is
# the one home for why), so the derivation is what the two immediates confirm.
SHIPPED_PRESHIFT_HALVES = (BOSS_SPRITE_FRAME_BYTES // 2, ASTEROID_FRAME_BYTES // 2)
assert SHIPPED_PRESHIFT_HALVES == (0x3e8, 0x1e0), (
    "D2 is half a preshift frame; the two call sites load 0x3e8 and 0x1e0, so a frame geometry "
    "that no longer halves to those has moved away from the game's own immediates")

# A case's own arena. The sprite bank has to hold the largest slot a phase can reach —
# 14 * 0x3e8 plus a frame's rows — so it gets 32 KB of its own.
BLIT_SPRITE = abi.SCRATCH + 0x10000
BLIT_SPRITE_BYTES = 0x8000
BLIT_ENTITY = abi.SCRATCH + 0x1f000


def _entity_record(x, y, height, sprite):
    record = bytearray(ENTITY_STRIDE)
    record[ENTITY_X:ENTITY_X + 2] = (x & 0xffff).to_bytes(2, "big")
    record[ENTITY_Y:ENTITY_Y + 2] = (y & 0xffff).to_bytes(2, "big")
    record[ENTITY_HEIGHT:ENTITY_HEIGHT + 2] = (height & 0xffff).to_bytes(2, "big")
    record[ENTITY_SPRITE:ENTITY_SPRITE + 4] = sprite.to_bytes(4, "big")
    return bytes(record)


def blit_pokes(x, y, height, seed):
    """The staging one `draw_sprite_masked` case needs: the sprite arena, the framebuffer, the
    record and the `screen_back` pointer that sends the blit there.

    THE RECORD IS CONSTRUCTED, and it has to be: entity_table and entity_boss_parts are bss, so the
    binary carries no record to seed from — the game writes them at run time. What the cases do NOT
    do is invent a shape the game cannot produce: every field is one the spawner sets, `half_frame`
    is one of the two values the two call sites load, and the coordinates walk the same playfield
    box the routine clips against.

    Public because `test_asm_sprite.py` drives the ASM TWIN over these same cases — a second,
    parallel staging there would be a second thing to keep true, and the twin has to match the C on
    the C's OWN cases rather than on cases chosen to suit it.
    """
    pokes = abi.seed_spans(seed, ((BLIT_SPRITE, BLIT_SPRITE + BLIT_SPRITE_BYTES),
                                (abi.SCREEN_BACK, abi.SCREEN_BACK + SCREEN_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[BLIT_ENTITY] = _entity_record(x, y, height, BLIT_SPRITE)
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    return pokes


def _blit_case(x, y, height, half_frame, seed, poison=False):
    """Call draw_sprite_masked(A2 = the record, D2 = half a preshift frame) at its own entry."""
    pokes = blit_pokes(x, y, height, seed)
    regs = {"a2": BLIT_ENTITY, "d2": half_frame, "_pokes": pokes}
    diffs, _ = differential(ENTRY_DRAW_SPRITE_MASKED, regs,
                            lambda lib, buf: lib.g_draw_sprite_masked(buf, BLIT_ENTITY, half_frame),
                            poison=poison)
    assert not diffs, f"x={x} y={y} height={height} d2={half_frame:#x}\n{report(diffs)}"


BLIT_HEIGHT = 32   # one asteroid frame's rows; small enough that every clip arm has room either side


@pytest.mark.parametrize("half_frame", SHIPPED_PRESHIFT_HALVES)
@pytest.mark.parametrize("phase", range(0, SPRITE_X_PHASE_MASK + 1, 2))
def test_draw_sprite_masked_every_phase(half_frame, phase):
    """The eight even sub-cell phases, which is every slot `and.w #$fffe` can ask for, at both
    shipped frame sizes — so the `mulu.w d2,d0` slot arithmetic is walked end to end."""
    _blit_case(0x40 + phase, 0x40, BLIT_HEIGHT, half_frame, seed=phase * 16 + half_frame)


@pytest.mark.parametrize("x", (0, 2, 0x10, 0x12, 0x130, 0x13e))
def test_draw_sprite_masked_across_the_row(x):
    """Cell 0 to the last cell that fits, which is what pins `and.w #$fff0` + `lsr.w #1` as a cell
    index times eight rather than as a pixel offset."""
    _blit_case(x, 0x40, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=x)


@pytest.mark.parametrize("x", (-1, -2, -0x8000, SCREEN_PIXELS_WIDE, SCREEN_PIXELS_WIDE + 1, 0x7ffe))
def test_draw_sprite_masked_rejects_x_off_screen(x):
    """Both x rejections, each one step either side of its edge. A rejection writes NOTHING, so the
    seeded screen coming back untouched is the whole assertion — and the odd values are there
    because `and.w #$fffe` runs before both tests."""
    _blit_case(x, 0x40, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=x & 0xffff)


@pytest.mark.parametrize("y", (PLAYFIELD_BOTTOM_Y, PLAYFIELD_BOTTOM_Y + 1, 0x7fff,
                               PLAYFIELD_TOP_Y - BLIT_HEIGHT, PLAYFIELD_TOP_Y - BLIT_HEIGHT - 1,
                               -0x8000))
def test_draw_sprite_masked_rejects_y_off_playfield(y):
    """Both y rejections at their exact edges: at the bottom the test is `>=`, and at the top it is
    y + height `<=` PLAYFIELD_TOP_Y — so a sprite whose last row is the top row draws nothing."""
    _blit_case(0x40, y, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=y & 0xffff)


@pytest.mark.parametrize("y", (PLAYFIELD_TOP_Y - BLIT_HEIGHT + 1, PLAYFIELD_TOP_Y - BLIT_HEIGHT // 2,
                               PLAYFIELD_TOP_Y - 1))
def test_draw_sprite_masked_clips_the_top(y):
    """y above the playfield: the SOURCE steps forward ten bytes a hidden row and the destination
    stays on the playfield's first row. One row visible, half, and all but one."""
    _blit_case(0x40, y, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=0x1000 + (y & 0xfff))


@pytest.mark.parametrize("y", (PLAYFIELD_BOTTOM_Y - BLIT_HEIGHT, PLAYFIELD_BOTTOM_Y - BLIT_HEIGHT + 1,
                               PLAYFIELD_BOTTOM_Y - BLIT_HEIGHT // 2, PLAYFIELD_BOTTOM_Y - 1))
def test_draw_sprite_masked_clips_the_bottom(y):
    """y inside the playfield: the ROW COUNT is cut at the bottom edge and the destination steps
    down. The first case is the tallest that needs no clip at all, which is the boundary."""
    _blit_case(0x40, y, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=0x2000 + y)


# Taller than the playfield, which no shipped sprite is (the tallest is the mothership's 40 rows).
# It is the ONLY height at which the two clip arms disagree, so it is contract coverage rather than
# game coverage — STATUS.md says so rather than letting the number read as something the game does.
BLIT_OVERSIZE_HEIGHT = PLAYFIELD_ROWS + 8


@pytest.mark.parametrize("y", (PLAYFIELD_TOP_Y - 1, PLAYFIELD_TOP_Y, PLAYFIELD_TOP_Y + 1))
def test_draw_sprite_masked_clip_arms_are_exclusive(y):
    """The two clips are exclusive arms of one `bge`, so a sprite tall enough to span the whole
    playfield from ABOVE it is clipped at the top and NOT at the bottom — it runs off the last row —
    while the same sprite one pixel lower is clipped at the bottom instead.

    y == PLAYFIELD_TOP_Y is the case that pins WHICH arm the boundary belongs to: at that y the two
    arms agree on the source and the destination and differ only in the bottom clip, so nothing
    shorter than BLIT_OVERSIZE_HEIGHT can tell `<` from `<=` (measured — the mutation survives the
    rest of the battery).
    """
    _blit_case(0x40, y, BLIT_OVERSIZE_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=0x3000 + y)


def test_draw_sprite_masked_attribution():
    """Poison: the mask is what makes this attributable at all — a candidate that wrote the planes
    without ANDing the background in would differ, and one that wrote nothing stays canary."""
    _blit_case(0x40, 0x40, BLIT_HEIGHT, SHIPPED_PRESHIFT_HALVES[1], seed=0x15ace, poison=True)


BLIT_FUZZ_CHUNKS = 4
BLIT_FUZZ_CASES = 200
# Heights stay in [1, PLAYFIELD_ROWS]. THE LOWER BOUND IS LOAD-BEARING, and it excludes TWO shapes,
# not one: `sub.w #$1,d2` on a height of 0 wraps to 0xffff, and a height with BIT 15 SET is negative
# as a word and survives both rejections while still negative (y = 100, height = 0xfff8 gives
# bottom = 92, so neither `y >= 176` nor `bottom <= 32` fires). Either way the `dbf` walks ~65536
# rows at 160 bytes each, straight off the image — where the oracle drops the accesses and the
# candidate would index the host heap. `draw_sprite_masked` does NOT mask the field (its sibling
# 0x15b7c does, `and.w #$7fff,d2`), so this is the routine's own behaviour and the cap is what keeps
# the sweep meaningful rather than a repair. STATUS.md records both arms as unreachable-by-data.
BLIT_FUZZ_MIN_HEIGHT = 1


def blit_fuzz_cases():
    rng = random.Random(ENTRY_DRAW_SPRITE_MASKED)     # seeded ONCE — every chunk replays the stream
    for i in range(BLIT_FUZZ_CASES):
        yield (i,
               rng.randrange(-0x40, SCREEN_PIXELS_WIDE + 0x40),
               rng.randrange(-PLAYFIELD_ROWS, PLAYFIELD_BOTTOM_Y + 0x40),
               rng.randrange(BLIT_FUZZ_MIN_HEIGHT, PLAYFIELD_ROWS + 1),
               SHIPPED_PRESHIFT_HALVES[rng.randrange(len(SHIPPED_PRESHIFT_HALVES))],
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(BLIT_FUZZ_CHUNKS))
def test_draw_sprite_masked_fuzz(chunk):
    for i, x, y, height, half_frame, seed in blit_fuzz_cases():
        if i % BLIT_FUZZ_CHUNKS != chunk:
            continue
        _blit_case(x, y, height, half_frame, seed)


# ===================================================== sprite_bank_build_preshift8 @ 0x153c0

# The eight call sites, read off the four instructions above each `bsr` in `_start`: the file
# `load_file` has just read, the address it read it to, D2 and D7. `_start` passes src == dst every
# time, so the bank is built over the file where it lies — and the file's own length is the pin on
# the pair, since frames * frame_bytes is exactly it. The alien sprite is loaded twice, to two
# different banks, with `_start` patching the letter in "alienb.dat" between the two reads (0x108e8).
SHIPPED_BANK_BUILDS = (
    ("SPINNERS.DAT", 0x50, 4, 0x6115e),
    ("SEEKER2.DAT",  0x6e, 8, 0x6421e),
    ("ALTEXPL.DAT",  0xa0, 8, 0x6791e),
    ("ALSEEK.DAT",   0x6e, 8, 0x65d9e),
    ("NEWBULS2.DAT", 0x1e, 4, 0x62a5e),
    ("GEMGRAF.DAT",  0xa0, 4, 0x5f3be),
    ("ALIENA.DAT",   0xa0, 4, 0x54ffe),
    ("ALIENB.DAT",   0xa0, 4, 0x563fe),
)


def _bank_build_case(src, dst, frame_bytes, frames, contents, seed, poison=False):
    """Call sprite_bank_build_preshift8(A0 = src, A1 = dst, D2 = frame_bytes, D7 = frames - 1).

    The whole destination bank is seeded — every slot, not just the ones a frame reaches — so a
    candidate that spreads the frames the wrong distance apart, or preshifts one bank too few,
    leaves a seeded byte standing. `contents` is what sits at `src` on entry: the disk's own file,
    or None for noise.
    """
    bank_bytes = frames * PRESHIFT_SLOTS * frame_bytes
    spans = [(dst, dst + bank_bytes)]
    if src != dst:
        spans.append((src, src + frames * frame_bytes))
    pokes = abi.seed_spans(seed, tuple(spans), guard=abi.GUARD_BYTES)
    if contents is not None:
        assert len(contents) == frames * frame_bytes, "a file is exactly its frames"
        pokes[src] = contents
    regs = {"a0": src, "a1": dst, "d2": frame_bytes, "d7": frames - 1, "_pokes": pokes}
    diffs, _ = differential(
        ENTRY_SPRITE_BANK_BUILD_PRESHIFT8, regs,
        lambda lib, buf: lib.g_sprite_bank_build_preshift8(buf, src, dst, frame_bytes, frames - 1),
        poison=poison)
    assert not diffs, (f"src={src:#x} dst={dst:#x} frame_bytes={frame_bytes:#x} frames={frames}\n"
                       f"{report(diffs)}")


# The poke that carries the file has to be applied AFTER the noise that covers the same span, and
# `harness.make_image` walks a poke dict in insertion order — which `abi.seed_spans` exists to keep
# nobody depending on. The in-place cases dodge it by not overlapping: the seed covers the whole
# bank, the file poke is inserted second, and the assertion below is what says the second one is a
# strict prefix of the first rather than a partial overlap of two seeded regions.
def _bank_build_shipped_case(index, src, dst, seed, poison=False):
    name, frame_bytes, frames, _real = SHIPPED_BANK_BUILDS[index]
    contents = (harness.PRG.parent / "disk" / name).read_bytes()
    assert len(contents) == frames * frame_bytes, (
        f"{name} is {len(contents)} bytes, not the {frames} x {frame_bytes:#x} frames _start "
        f"builds a bank from — the call site's D2/D7 no longer match the file")
    _bank_build_case(src, dst, frame_bytes, frames, contents, seed, poison=poison)


@pytest.mark.parametrize("index", range(len(SHIPPED_BANK_BUILDS)))
def test_bank_build_every_shipped_file_in_place(index):
    """All eight call sites, each over its own file at its own bank address, src == dst.

    In place is the only shape the game uses and it is the one that could go wrong: the first pass
    rewrites the buffer it is reading from, and it only works because frame i is written eight banks
    further out than any frame still to be read. A pass running the other way would eat its source.
    """
    _bank_build_shipped_case(index, SHIPPED_BANK_BUILDS[index][3], SHIPPED_BANK_BUILDS[index][3],
                             seed=0x153c0 + index)


@pytest.mark.parametrize("index", (0, 1, 4))
def test_bank_build_disjoint(index):
    """src != dst — which no call site does, and which is what says A0 and A1 are separate cursors
    rather than one buffer. The source is left untouched, so its own bytes are part of the diff."""
    _bank_build_shipped_case(index, BANK_BUILD_SRC, BANK_BUILD_DST, seed=0x2000 + index)


@pytest.mark.parametrize("frames", (1, 2, 8))
def test_bank_build_noise(frames):
    """Noise in place of a graphic. The routine has no data-dependent branch, so any bit pattern is
    a legal input, and noise separates the eight rotations from one another better than a sprite
    does — a real frame has runs of zeroes that several rotations agree on."""
    _bank_build_case(BANK_BUILD_SRC, BANK_BUILD_SRC, 0xa0, frames, None, seed=0x3000 + frames)


def test_bank_build_attribution():
    """Poison: slot 0 of each bank comes from the COPY pass and slots 1..7 from the preshift, so a
    candidate that ran only one of the two passes stays canary in the other's slots."""
    _bank_build_shipped_case(0, SHIPPED_BANK_BUILDS[0][3], SHIPPED_BANK_BUILDS[0][3],
                             seed=0x153c1, poison=True)


BANK_FUZZ_CHUNKS = 2
BANK_FUZZ_CASES = 40
# frame_bytes stays at or above 2 and frames at or above 1. THE LOWER BOUND ON frame_bytes IS
# LOAD-BEARING: 0 halves to 0 words, and both passes count through a `dbf`, so `copy_block_words`
# would copy 0x10000 words and the preshifter walk 0x10000 rows with a slot step of 0 — 128 KB of
# traffic per frame for a width no call site passes. The two counts are exercised at their own edges
# by the cases above instead.
BANK_FUZZ_MIN_FRAME_BYTES = 2
BANK_FUZZ_MAX_FRAME_BYTES = 0xa0


def _bank_fuzz_cases():
    rng = random.Random(ENTRY_SPRITE_BANK_BUILD_PRESHIFT8)   # seeded ONCE — every chunk replays it
    for i in range(BANK_FUZZ_CASES):
        yield (i,
               rng.randrange(BANK_FUZZ_MIN_FRAME_BYTES, BANK_FUZZ_MAX_FRAME_BYTES + 1),
               rng.randrange(1, PRESHIFT_SLOTS + 1),
               rng.randrange(2) == 0,                        # in place, or into a separate bank?
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(BANK_FUZZ_CHUNKS))
def test_bank_build_fuzz(chunk):
    """Widths the game does not ship, including odd ones — `lsr.l #1` discards the odd byte in the
    copy pass and `lsr.w #1` discards it again in the preshift, so an odd width is a legal input
    that rounds down twice."""
    for i, frame_bytes, frames, in_place, seed in _bank_fuzz_cases():
        if i % BANK_FUZZ_CHUNKS != chunk:
            continue
        dst = BANK_BUILD_SRC if in_place else BANK_BUILD_DST
        _bank_build_case(BANK_BUILD_SRC, dst, frame_bytes, frames, None, seed)


# ===================================================== mothership_sprite_preshift @ 0x15838

# The four bytes the routine arms the encounter with on its way out. Three are named in
# include/mothership.h and the fourth is borrowed into include/sprite.h — see the BORROWED note
# there, and STATUS.md. All four are in MIRRORS at the bottom of this file.
A_BOSS_SEQUENCE_ACTIVE = 0x19aad
A_MOTHERSHIP_READY = 0x198b0
A_MOTHERSHIP_PREP_STAGE = 0x19911
A_MOTHERSHIP_PHASE_TIMER = 0x19efe

# TWO OF THE FOUR ARE CLEARED, NOT SET, and all four live in bss — so leaving them at their loaded
# zeroes would make `clr.l`/`clr.b` write zeroes over zeroes and differ nowhere. Every case seeds
# them with a value that is neither what the routine writes nor what the image already holds.
BOSS_FLAG_SEEDS = ((A_BOSS_SEQUENCE_ACTIVE, b"\x5a"), (A_MOTHERSHIP_READY, b"\xa5"),
                   (A_MOTHERSHIP_PREP_STAGE, b"\x3c"), (A_MOTHERSHIP_PHASE_TIMER, b"\xde\xad\xbe\xef"))


def _boss_bank_from_the_real_file(name):
    """The bank `mothership_sprite_expand` @ 0x157ca would have left behind for `name`.

    Eight identical five-cell frames: the file's four 40-row cells copied across and a fifth
    synthesised transparent one. Built here from the disk's own bytes rather than by running the
    expander, so the preshifter's case does not depend on the expander's own reconstruction.
    """
    source = (harness.PRG.parent / "disk" / name).read_bytes()
    assert len(source) == BOSS_SPRITE_SOURCE_BYTES, f"{name} is not one 64x40 masked block"
    blank = SPRITE_MASK_TRANSPARENT.to_bytes(2, "big") + bytes(SPRITE_MASKED_ROW_BYTES - 2)
    cells = [bytearray() for _ in range(BOSS_SPRITE_FRAME_CELLS)]
    for row in range(BOSS_SPRITE_ROWS):
        at = row * BOSS_SPRITE_SOURCE_CELLS * SPRITE_MASKED_ROW_BYTES
        for cell in range(BOSS_SPRITE_SOURCE_CELLS):
            start = at + cell * SPRITE_MASKED_ROW_BYTES
            cells[cell] += source[start:start + SPRITE_MASKED_ROW_BYTES]
        cells[BOSS_SPRITE_FRAME_CELLS - 1] += blank
    return bytes(b"".join(cells)) * PRESHIFT_SLOTS


def _boss_preshift_case(contents, seed, poison=False):
    """Call mothership_sprite_preshift() at its own entry. It takes no register argument at all —
    the bank is an immediate and so are the four flags — so the bank's contents are the whole input.
    """
    span = (A_MOTHERSHIP_SPRITE_BANK, A_MOTHERSHIP_SPRITE_BANK + BOSS_SPRITE_BANK_BYTES)
    if contents is None:
        pokes = abi.seed_spans(seed, (span,), guard=abi.GUARD_BYTES)
    else:
        assert len(contents) == BOSS_SPRITE_BANK_BYTES, "a bank is eight whole five-cell frames"
        pokes = abi.seed_spans(seed, _guard_bands_only(*span))
        pokes[A_MOTHERSHIP_SPRITE_BANK] = contents
    pokes.update(BOSS_FLAG_SEEDS)
    diffs, _ = differential(ENTRY_MOTHERSHIP_SPRITE_PRESHIFT, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_sprite_preshift(buf), poison=poison)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("name", BOSS_SPRITE_FILES)
def test_mothership_sprite_preshift_real_sprites(name):
    """Every boss sprite the disk ships, in the bank the expander would have left it in.

    Real data is what makes the carry chain's two starting values visible for what they are: the
    mask column feeds in a 1 (`move.w #$1,d3 / lsr.w #1` leaves X set) and the four colour planes a
    0, so a shifted sprite keeps a transparent left edge and gains no phantom pixels. The
    synthesised fifth cell is where fourteen pixels of the sprite end up, which is what makes the
    fifth link of the chain something other than dead work.
    """
    _boss_preshift_case(_boss_bank_from_the_real_file(name), seed=BOSS_SPRITE_FILES.index(name))


def test_mothership_sprite_preshift_noise():
    """Noise over the whole bank: there is no data-dependent branch, so every bit pattern is legal,
    and noise separates the five word columns and the five cells from one another."""
    _boss_preshift_case(None, seed=ENTRY_MOTHERSHIP_SPRITE_PRESHIFT)


def test_mothership_sprite_preshift_attribution():
    """Poison: frame 0 is never touched, so a candidate that shifted it differs, and one that
    stopped before frame 7's fourteenth pass stays canary."""
    _boss_preshift_case(_boss_bank_from_the_real_file(BOSS_SPRITE_FILES[0]), seed=0x15839,
                        poison=True)


def test_mothership_sprite_preshift_arms_the_encounter():
    """The four flag bytes, seeded so that the two CLEARS are visible.

    A separate case rather than a rider on the ones above only in what it asserts: the differential
    already compares those bytes, and this reads them back out of the oracle's own final image so
    the failure message names the flag rather than an address in the middle of a 16 KB bank.
    """
    span = (A_MOTHERSHIP_SPRITE_BANK, A_MOTHERSHIP_SPRITE_BANK + BOSS_SPRITE_BANK_BYTES)
    pokes = abi.seed_spans(0x1583a, (span,), guard=abi.GUARD_BYTES)
    pokes.update(BOSS_FLAG_SEEDS)
    image = harness.make_image(pokes)
    final, _writes, _regs = emu.run(image, ENTRY_MOTHERSHIP_SPRITE_PRESHIFT, {})
    assert final[A_BOSS_SEQUENCE_ACTIVE] == 1, "the boss is not marked as owning the playfield"
    assert final[A_MOTHERSHIP_READY] == 1, "the encounter is not armed"
    assert final[A_MOTHERSHIP_PREP_STAGE] == 0, "the multi-frame build's stage is not reset"
    assert bytes(final[A_MOTHERSHIP_PHASE_TIMER:A_MOTHERSHIP_PHASE_TIMER + 4]) == bytes(4), (
        "the phase timer is not cleared")


# ================================================== draw_sprite_masked_collide @ 0x15b7c

# ---- mirrors of the headers this blitter reads ----
ENTITY_PIXEL_HIT = 0x0f          # include/entity.h
ENTITY_HEIGHT_MASK = 0x7fff      # include/collision.h
SCC_BYTE_TRUE = 0xff             # include/enemy.h
A_SHIFT_MASK_TABLE = 0x1821e     # include/sprite.h
SPRITE_SHIFT_MASK_STRIDE = 2
SPRITE_COLLIDE_ORIGIN_X = 0x40
SPRITE_COLLIDE_LEFT_EDGE = 0x30
SPRITE_COLLIDE_RIGHT_EDGE = 0x170
SPRITE_COLLIDE_RIGHT_OFF = 0x180
SPRITE_CELL_BYTES = 8
SCREEN_ROW_BYTES = 160

# A flag byte clear of everything else a case pokes, for the shape where A5 is NOT inside the record.
COLLIDE_FLAG = abi.SCRATCH + 0x1f100
# What the flag holds on entry. Neither 0 (which would make a missing `st` invisible against bss)
# nor SCC_BYTE_TRUE (which would make a spurious one invisible).
COLLIDE_FLAG_SEED = 0x5a

COLLIDE_HEIGHT = 32              # the asteroid frame's rows; room either side of every clip edge


def collide_sprite(rows, mask, planes, phase_slots=PRESHIFT_SLOTS):
    """A preshift bank of `phase_slots` slots, every row of every slot (mask, planes x 4).

    Public because `test_asm_sprite.py` builds the same sprites for the twin.

    Built rather than seeded so that a case can say what the collision test should SEE: an opaque
    sprite (mask 0) over background, or a wholly transparent one (mask 0xffff, planes 0) that must
    leave both the screen and the flag alone.
    """
    row = mask.to_bytes(2, "big") + b"".join(p.to_bytes(2, "big") for p in planes)
    return row * (rows * phase_slots)


def collide_staging(x, y, height, seed, sprite_bytes=None, screen_bytes=None, hit_flag=None):
    """(the pokes, the flag address) for one `draw_sprite_masked_collide` case.

    The record is constructed for the same reason `blit_pokes`'s is — `entity_table` is bss — and
    within the same limits: every field is one a spawner writes, and the coordinates walk the world
    box the three x bands and the two y clips divide up. Public for `test_asm_sprite.py`, which
    drives the twin over exactly these cases.
    """
    flag = BLIT_ENTITY + ENTITY_PIXEL_HIT if hit_flag is None else hit_flag
    spans = [(BLIT_SPRITE, BLIT_SPRITE + BLIT_SPRITE_BYTES),
             (abi.SCREEN_BACK, abi.SCREEN_BACK + SCREEN_BYTES)]
    pokes = abi.seed_spans(seed, tuple(spans), guard=abi.GUARD_BYTES)
    if sprite_bytes is not None:
        pokes[BLIT_SPRITE] = sprite_bytes
    if screen_bytes is not None:
        pokes[abi.SCREEN_BACK] = screen_bytes
    pokes[BLIT_ENTITY] = _entity_record(x, y, height, BLIT_SPRITE)
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    if hit_flag is not None:
        pokes[hit_flag] = bytes([COLLIDE_FLAG_SEED])
    return pokes, flag


def _collide_case(x, y, height, seed, sprite_bytes=None, screen_bytes=None,
                  hit_flag=None, poison=False):
    """Call draw_sprite_masked_collide(A2 = the record, A5 = the flag) at its own entry."""
    pokes, flag = collide_staging(x, y, height, seed, sprite_bytes, screen_bytes, hit_flag)
    regs = {"a2": BLIT_ENTITY, "a5": flag, "_pokes": pokes}
    diffs, _ = differential(
        ENTRY_DRAW_SPRITE_MASKED_COLLIDE, regs,
        lambda lib, buf: lib.g_draw_sprite_masked_collide(buf, BLIT_ENTITY, flag), poison=poison)
    assert not diffs, f"x={x} y={y} height={height} flag={flag:#x}\n{report(diffs)}"


@pytest.mark.parametrize("phase", range(0, SPRITE_X_PHASE_MASK + 1, 2))
def test_collide_every_phase(phase):
    """The eight even sub-cell phases. Each picks a different `shift_mask_table` entry AND a
    different preshift slot, so this walks the keep-mask split and the `(x & 0xf) * (rows * 5)` slot
    arithmetic together — a phase indexing one but not the other lands the wrong half of the wrong
    slot in both cells."""
    _collide_case(SPRITE_COLLIDE_ORIGIN_X + 0x40 + phase, 0x40, COLLIDE_HEIGHT, seed=0x100 + phase)


@pytest.mark.parametrize("x", (0x40, 0x42, 0x50, 0x52, 0x160, 0x170))
def test_collide_across_the_row(x):
    """Column 0 to the last x whose SECOND cell is still on screen, which is what pins the origin
    subtraction and `and.w #$fff0` + `lsr.w #1` as a cell index rather than a pixel offset."""
    _collide_case(x, 0x40, COLLIDE_HEIGHT, seed=0x200 + x)


@pytest.mark.parametrize("x", (0x32, 0x38, 0x3e))
def test_collide_left_edge_band(x):
    """World x strictly inside (0x30, 0x40): the sprite's own cell is off screen and only the half
    that rotated OUT of it is drawn, in column 0, with the COMPLEMENT of the keep-mask. There is no
    column offset at all on this arm — the row is left where the y clip put it."""
    _collide_case(x, 0x40, COLLIDE_HEIGHT, seed=0x300 + x)


@pytest.mark.parametrize("x", (0x172, 0x178, 0x17e))
def test_collide_right_edge_band(x):
    """World x strictly inside (0x170, 0x180): only the sprite's own half fits, in the row's LAST
    cell — a fixed `lea 152(a0)` rather than the middle band's computed offset, so a candidate that
    kept computing it would land eight bytes short at 0x178."""
    _collide_case(x, 0x40, COLLIDE_HEIGHT, seed=0x400 + x)


@pytest.mark.parametrize("x", (SPRITE_COLLIDE_LEFT_EDGE, SPRITE_COLLIDE_LEFT_EDGE - 2, 0, -2,
                               -0x8000, SPRITE_COLLIDE_RIGHT_OFF, SPRITE_COLLIDE_RIGHT_OFF + 2,
                               0x7ffe))
def test_collide_rejects_x_off_screen(x):
    """Both x rejections at their exact edges. 0x30 itself is rejected (`bgt`) and 0x180 itself is
    rejected (`blt`), so the two live bands are the OPEN intervals either side. A rejection writes
    nothing at all — not even the flag — so the seeded screen and record coming back untouched is
    the whole assertion."""
    _collide_case(x, 0x40, COLLIDE_HEIGHT, seed=0x500 + (x & 0xffff))


@pytest.mark.parametrize("y", (PLAYFIELD_BOTTOM_Y, PLAYFIELD_BOTTOM_Y + 1, 0x7fff,
                               PLAYFIELD_TOP_Y - COLLIDE_HEIGHT,
                               PLAYFIELD_TOP_Y - COLLIDE_HEIGHT - 1, -0x8000))
def test_collide_rejects_y_off_playfield(y):
    """The same two y rejections as 0x15ace's, tested at the same edges — they are the same four
    instructions in the same order."""
    _collide_case(0x80, y, COLLIDE_HEIGHT, seed=0x600 + (y & 0xffff))


@pytest.mark.parametrize("y", (PLAYFIELD_TOP_Y - COLLIDE_HEIGHT + 1,
                               PLAYFIELD_TOP_Y - COLLIDE_HEIGHT // 2, PLAYFIELD_TOP_Y - 1,
                               PLAYFIELD_BOTTOM_Y - COLLIDE_HEIGHT,
                               PLAYFIELD_BOTTOM_Y - COLLIDE_HEIGHT // 2, PLAYFIELD_BOTTOM_Y - 1))
def test_collide_clips_top_and_bottom(y):
    """Above the playfield the SOURCE steps forward ten bytes a hidden row; inside it the row count
    is cut at the bottom edge and the destination steps down. One row visible, half and all but one
    at each end."""
    _collide_case(0x80, y, COLLIDE_HEIGHT, seed=0x700 + (y & 0xffff))


@pytest.mark.parametrize("y", (PLAYFIELD_TOP_Y - 1, PLAYFIELD_TOP_Y, PLAYFIELD_TOP_Y + 1))
def test_collide_clip_arms_are_exclusive(y):
    """The two clips are exclusive arms of one `bge` here too, so a sprite tall enough to span the
    playfield from above it runs off the last row instead of being clipped at the bottom. Only a
    height past PLAYFIELD_ROWS can tell `<` from `<=` at the boundary — contract coverage, not game
    coverage, exactly as BLIT_OVERSIZE_HEIGHT is for the sibling."""
    _collide_case(0x80, y, BLIT_OVERSIZE_HEIGHT, seed=0x800 + y)


@pytest.mark.parametrize("height", (COLLIDE_HEIGHT, COLLIDE_HEIGHT | 0x8000))
def test_collide_masks_the_height_flag(height):
    """Bit 15 of the height field is the weapon code's lock-slot flag, and THIS blitter masks it off
    (`and.w #$7fff,d2`) where 0x15ace does not. Both spellings of 32 rows must draw the same 32
    rows — and the mask runs twice, once before the `mulu.w #$5` that sizes the preshift step and
    once for the row count, so dropping either one moves the source as well as the loop."""
    _collide_case(0x80, 0x40, height, seed=0x900 + (height & 0xffff))


# A wholly transparent row and a wholly opaque one, in the masked format include/sprite.h describes.
COLLIDE_TRANSPARENT_ROW = (SPRITE_MASK_TRANSPARENT, (0, 0, 0, 0))
COLLIDE_OPAQUE_ROW = (0x0000, (0xffff, 0xffff, 0xffff, 0xffff))


# Public for the same reason `collide_sprite` is: `test_asm_sprite.py` stages the same screens.
def cell_with_planes(plane_words):
    """One 16-pixel four-plane screen cell holding `plane_words` (planes 0..3)."""
    return b"".join(word.to_bytes(2, "big") for word in plane_words)


def screen_with_planes(plane_words):
    """A whole framebuffer whose every 16-pixel cell holds `plane_words`.

    Used to say what the collision test should see: planes 2 and 3 are the terrain the scroller
    draws, and they are the only two the test consults.
    """
    return cell_with_planes(plane_words) * (SCREEN_BYTES // SPRITE_CELL_BYTES)


def test_collide_transparent_sprite_sets_no_flag():
    """A wholly transparent sprite over noise: `~mask` is zero on every row, so no pixel of the
    background is ever under an opaque one and the flag keeps its seeded value. It also writes no
    screen byte, the four zero planes being OR'd into an untouched background."""
    _collide_case(0x80, 0x40, COLLIDE_HEIGHT, seed=0xa00, hit_flag=COLLIDE_FLAG,
                  sprite_bytes=collide_sprite(COLLIDE_HEIGHT, *COLLIDE_TRANSPARENT_ROW))


def test_collide_ignores_the_low_planes():
    """An OPAQUE sprite over a background that has planes 0 and 1 set and planes 2 and 3 clear: the
    sprite covers every pixel and the flag still keeps its seeded value.

    This is the case that says the test reads planes 2 and 3 and not "any pixel" — with a noise
    screen every case hits, so nothing else in the battery could tell the two readings apart.
    """
    _collide_case(0x80, 0x40, COLLIDE_HEIGHT, seed=0xb00, hit_flag=COLLIDE_FLAG,
                  sprite_bytes=collide_sprite(COLLIDE_HEIGHT, *COLLIDE_OPAQUE_ROW),
                  screen_bytes=screen_with_planes((0xffff, 0xffff, 0, 0)))


def test_collide_sets_the_flag_on_terrain():
    """The same opaque sprite over a background whose plane 2 is set: the flag becomes 0xff.

    Paired with the case above, the two differ in one plane word and in nothing else, so between
    them they pin WHICH planes the `and.l` consults rather than merely that it consults something.
    """
    _collide_case(0x80, 0x40, COLLIDE_HEIGHT, seed=0xc00, hit_flag=COLLIDE_FLAG,
                  sprite_bytes=collide_sprite(COLLIDE_HEIGHT, *COLLIDE_OPAQUE_ROW),
                  screen_bytes=screen_with_planes((0, 0, 0xffff, 0)))


@pytest.mark.parametrize("phase", (2, 8, 14))
def test_collide_second_cell_is_tested_too(phase):
    """Terrain in the SECOND cell only, so the near test misses and the far one has to fire.

    The two tests store the same 0xff, so nothing can tell them apart while both would hit — this
    is the only shape that can. The screen alternates cells: even cells hold no terrain planes and
    odd ones do, and the sprite sits on an even cell, so every pixel that rotated out of it lands on
    terrain and nothing else does. Phase 0 is excluded on purpose: at phase 0 the keep-mask is all
    ones, the far half is empty, and there is nothing in the second cell to find.
    """
    clear_cell = cell_with_planes((0xffff, 0xffff, 0, 0))
    terrain_cell = cell_with_planes((0, 0, 0xffff, 0xffff))
    row = (clear_cell + terrain_cell) * (SCREEN_ROW_BYTES // (2 * SPRITE_CELL_BYTES))
    _collide_case(SPRITE_COLLIDE_ORIGIN_X + phase, 0x40, COLLIDE_HEIGHT, seed=0xd00 + phase,
                  hit_flag=COLLIDE_FLAG,
                  sprite_bytes=collide_sprite(COLLIDE_HEIGHT, *COLLIDE_OPAQUE_ROW),
                  screen_bytes=row * (SCREEN_BYTES // SCREEN_ROW_BYTES))


def test_collide_flag_inside_the_record():
    """The shape the game's own frame loop runs: A5 is the record's ENTITY_PIXEL_HIT byte, so the
    blitter writes into the record it is reading. The other call site (0x13096) points A5 at a
    front-end byte instead, which every other case in this battery uses."""
    _collide_case(0x80, 0x40, COLLIDE_HEIGHT, seed=0xe00)


def test_collide_attribution():
    """Poison: the mask AND the keep-mask are what make this attributable — a candidate that wrote
    the planes without splitting them between the two cells differs, and one that wrote nothing
    stays canary. The flag byte is poisoned too, so a missing `st` shows up as the canary."""
    _collide_case(0x80, 0x40, COLLIDE_HEIGHT, seed=ENTRY_DRAW_SPRITE_MASKED_COLLIDE, poison=True)


COLLIDE_FUZZ_CHUNKS = 4
COLLIDE_FUZZ_CASES = 200
# Heights stay in [1, PLAYFIELD_ROWS] for the same reason `BLIT_FUZZ_MIN_HEIGHT` does — a height of
# 0 wraps `subq.w #1` to 0xffff and walks ~65536 rows straight off the image. Bit 15 is NOT a hazard
# here, unlike the sibling, because this routine masks it off; the case above covers it.
COLLIDE_FUZZ_MIN_HEIGHT = 1


def collide_fuzz_cases():
    rng = random.Random(ENTRY_DRAW_SPRITE_MASKED_COLLIDE)   # seeded ONCE — every chunk replays it
    for i in range(COLLIDE_FUZZ_CASES):
        yield (i,
               rng.randrange(0, SPRITE_COLLIDE_RIGHT_OFF + 0x40),
               rng.randrange(-PLAYFIELD_ROWS, PLAYFIELD_BOTTOM_Y + 0x40),
               rng.randrange(COLLIDE_FUZZ_MIN_HEIGHT, PLAYFIELD_ROWS + 1),
               rng.randrange(2) == 0,                       # flag inside the record, or outside?
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(COLLIDE_FUZZ_CHUNKS))
def test_collide_fuzz(chunk):
    for i, x, y, height, in_record, seed in collide_fuzz_cases():
        if i % COLLIDE_FUZZ_CHUNKS != chunk:
            continue
        _collide_case(x, y, height, seed, hit_flag=None if in_record else COLLIDE_FLAG)


def test_shift_mask_table_is_the_rotation_split():
    """`shift_mask_table` @ 0x1821e holds 0xffff >> s for the eight even shifts, each word twice.

    The claim src/sprite.c makes about this table — that it re-splits a ROTATED sprite word between
    two cells — is exactly the claim that entry s keeps the low 16-s bits. It is read as a LONGWORD
    at a two-byte stride, so the doubling is what makes one read serve a plane pair; the only shifts
    the blitter can ask for are EVEN (`bclr #0` forces x even), so those reads are disjoint. This is
    where both halves of that reading are pinned against the binary's own bytes.
    """
    read_at = []
    for shift in range(0, SPRITE_X_PHASE_MASK + 1, 2):
        at = A_SHIFT_MASK_TABLE + shift * SPRITE_SHIFT_MASK_STRIDE
        keep = int.from_bytes(bytes(harness.BASE_IMAGE[at:at + 4]), "big")
        expected = (0xffff >> shift) * 0x00010001
        assert keep == expected, f"shift {shift}: {keep:#010x} is not {expected:#010x}"
        read_at.append(at)
    # ...and the eight reads do not overlap, which is what the two-byte stride would otherwise mean.
    assert read_at == sorted(read_at) and all(b - a == 4 for a, b in zip(read_at, read_at[1:]))


def test_geometry_constants_agree_with_their_derivations():
    """The C keeps each of these as the ORIGINAL'S OWN IMMEDIATE rather than as a product, because
    that is the only form `test_constants.py`'s scraper can pin across the language boundary — it
    reads literals, not expressions. The relationships BETWEEN them are therefore unpinned in the C,
    and this is where they are held: a frame that stops being cells x rows x row-bytes, or a row
    that stops being five words, fails here instead of quietly resizing a seeded span.
    """
    assert SPRITE_MASKED_ROW_BYTES == 2 * SPRITE_MASKED_ROW_WORDS
    # The bank's depth and the shift the whole-file builder scales a frame by are ONE fact, and the
    # C keeps both spellings because the original does; this is where they are held equal.
    assert 1 << PRESHIFT_SLOT_SHIFT == PRESHIFT_SLOTS
    assert ASTEROID_FRAME_BYTES == ASTEROID_FRAME_CELLS * ASTEROID_CELL_BYTES
    assert ASTEROID_CELL_BYTES == ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES
    assert BOSS_SPRITE_FRAME_BYTES == BOSS_SPRITE_FRAME_CELLS * BOSS_SPRITE_CELL_BYTES
    assert BOSS_SPRITE_CELL_BYTES == BOSS_SPRITE_ROWS * SPRITE_MASKED_ROW_BYTES
    assert BOSS_SPRITE_SOURCE_BYTES == BOSS_SPRITE_SOURCE_CELLS * BOSS_SPRITE_CELL_BYTES
    assert PLAYFIELD_BOTTOM_Y - PLAYFIELD_TOP_Y == PLAYFIELD_ROWS
    # `lea 152(a0),a0` in the collide blitter's right-edge band, which the C spells as a derivation
    # rather than as a third 152 in this project (scroll.h's SCROLL_WINDOW_BYTES is the same number
    # under a different meaning — the ring window's width, not the last cell's offset).
    assert SCREEN_ROW_BYTES - SPRITE_CELL_BYTES == 152
    # The last world x the MIDDLE band takes maps to the row's LAST cell — so its second cell lands
    # on the next row's first. include/sprite.h says why that is the original's behaviour and not an
    # edge to be narrowed; this is where the arithmetic behind the claim is held.
    assert ((SPRITE_COLLIDE_RIGHT_EDGE - SPRITE_COLLIDE_ORIGIN_X) & 0xfff0) // 2 == (
        SCREEN_ROW_BYTES - SPRITE_CELL_BYTES)


def test_the_borrowed_boss_flag_has_not_been_claimed_by_its_owner():
    """`A_boss_sequence_active` (0x19aad) is the MOTHERSHIP subsystem's per ../out/globals.tsv, and
    include/sprite.h carries it only because `mothership_sprite_preshift` had to be portable this
    wave (see the BORROWED note there).

    The clash it risks is a `test_constants.py` failure whose message names sprite.h — a file the
    mothership agent is told never to edit. This is that clash caught HERE first, with a message
    that names the move instead: the moment mothership.h spells 0x19aad under any name, drop the
    define from sprite.h and include mothership.h for it, as src/sprite.c already does for the boss
    sprite's two addresses.
    """
    mothership_h = (REC / "include/mothership.h").read_text()
    assert "0x19aad" not in mothership_h, (
        "include/mothership.h now names 0x19aad — move A_boss_sequence_active out of "
        "include/sprite.h and read it from mothership.h instead (sprite.h's BORROWED note)")


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("SHIP_SPRITE_ROWS", "src/sprite.c", "SHIP_SPRITE_ROWS"),
    ("SHIP_SPRITE_HALF_BYTES", "src/sprite.c", "SHIP_SPRITE_HALF_BYTES"),
    ("SHIP_SPRITE_GAP", "include/sprite.h", "SHIP_SPRITE_GAP"),
    ("PRESHIFT_SLOTS", "include/sprite.h", "SPRITE_PRESHIFT_SLOTS"),
    ("PRESHIFT_SLOT_SHIFT", "include/sprite.h", "SPRITE_PRESHIFT_SLOT_SHIFT"),
    ("SPRITE_MASKED_ROW_WORDS", "include/sprite.h", "SPRITE_MASKED_ROW_WORDS"),
    ("SPRITE_MASKED_ROW_BYTES", "include/sprite.h", "SPRITE_MASKED_ROW_BYTES"),
    ("SPRITE_MASK_TRANSPARENT", "include/sprite.h", "SPRITE_MASK_TRANSPARENT"),
    ("ASTEROID_FRAME_ROWS", "include/sprite.h", "ASTEROID_FRAME_ROWS"),
    ("ASTEROID_FRAME_CELLS", "include/sprite.h", "ASTEROID_FRAME_CELLS"),
    ("A_MOTHERSHIP_SPRITE_SOURCE", "include/mothership.h", "A_mothership_sprite_source"),
    ("A_MOTHERSHIP_SPRITE_BANK", "include/mothership.h", "A_mothership_sprite_bank"),
    ("BOSS_SPRITE_ROWS", "include/sprite.h", "BOSS_SPRITE_ROWS"),
    ("BOSS_SPRITE_SOURCE_CELLS", "include/sprite.h", "BOSS_SPRITE_SOURCE_CELLS"),
    ("BOSS_SPRITE_FRAME_CELLS", "include/sprite.h", "BOSS_SPRITE_FRAME_CELLS"),
    ("SPRITE_X_PHASE_MASK", "include/sprite.h", "SPRITE_X_PHASE_MASK"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
    ("SCREEN_PIXELS_WIDE", "include/video.h", "SCREEN_PIXELS_WIDE"),
    ("PLAYFIELD_TOP_Y", "include/video.h", "PLAYFIELD_TOP_Y"),
    ("PLAYFIELD_ROWS", "include/video.h", "PLAYFIELD_ROWS"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_PIXEL_HIT", "include/entity.h", "ENTITY_PIXEL_HIT"),
    ("ENTITY_HEIGHT_MASK", "include/collision.h", "ENTITY_HEIGHT_MASK"),
    ("SCC_BYTE_TRUE", "include/enemy.h", "SCC_BYTE_TRUE"),
    ("A_SHIFT_MASK_TABLE", "include/sprite.h", "A_shift_mask_table"),
    ("SPRITE_SHIFT_MASK_STRIDE", "include/sprite.h", "SPRITE_SHIFT_MASK_STRIDE"),
    ("A_BOSS_SEQUENCE_ACTIVE", "include/sprite.h", "A_boss_sequence_active"),
    ("A_MOTHERSHIP_READY", "include/mothership.h", "A_mothership_ready"),
    ("A_MOTHERSHIP_PREP_STAGE", "include/mothership.h", "A_mothership_prep_stage"),
    ("A_MOTHERSHIP_PHASE_TIMER", "include/mothership.h", "A_mothership_phase_timer"),
    ("SPRITE_COLLIDE_ORIGIN_X", "include/sprite.h", "SPRITE_COLLIDE_ORIGIN_X"),
    ("SPRITE_COLLIDE_LEFT_EDGE", "include/sprite.h", "SPRITE_COLLIDE_LEFT_EDGE"),
    ("SPRITE_COLLIDE_RIGHT_EDGE", "include/sprite.h", "SPRITE_COLLIDE_RIGHT_EDGE"),
    ("SPRITE_COLLIDE_RIGHT_OFF", "include/sprite.h", "SPRITE_COLLIDE_RIGHT_OFF"),
    ("SPRITE_CELL_BYTES", "include/sprite.h", "SPRITE_CELL_BYTES"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
)
# TWELVE BYTES FOR THE TWO BLITTERS, not the usual ten. 0x15ace and 0x15b7c open with the identical
# `movea.l $1797e,a0 / move.w 0(a2),d0` and separate only at byte 10, where one forces x even with
# `and.w #$fffe` and the other with `bclr #0` — so a ten-byte prologue would let either address
# stand for the other, and a mistyped entry would run the wrong blitter and still come back clean.
ENTRY_PROLOGUES = {
    "ENTRY_SHIP_SPRITE_DEINTERLEAVE": "323c001345e9064022d8",
    "ENTRY_SPRITE_BANK_BUILD_PRESHIFT8": "2602e78b48e731c048e7",
    "ENTRY_SPRITE_PRESHIFT8_2PX": "42853a02e78d9a423602",
    "ENTRY_SPRITE_PRESHIFT4_4PX": "42853a02e78d9a429a42",
    "ENTRY_ASTEROID_PRESHIFT_BANK": "41e803c03e3c0006383c",
    "ENTRY_MOTHERSHIP_SPRITE_EXPAND": "41f90005ed7e43f90003",
    "ENTRY_MOTHERSHIP_SPRITE_PRESHIFT": "41f9000310ae41e807d0",
    "ENTRY_DRAW_SPRITE_MASKED": "20790001797e302a0000c07c",
    "ENTRY_DRAW_SPRITE_MASKED_COLLIDE": "20790001797e302a00000880",
}
