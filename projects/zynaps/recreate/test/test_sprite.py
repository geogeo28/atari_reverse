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
ENTRY_ASTEROID_PRESHIFT_BANK = 0x15758
ENTRY_MOTHERSHIP_SPRITE_EXPAND = 0x157ca
ENTRY_DRAW_SPRITE_MASKED = 0x15ace

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


def _blit_case(x, y, height, half_frame, seed, poison=False):
    """Call draw_sprite_masked(A2 = the record, D2 = half a preshift frame) at its own entry.

    THE RECORD IS CONSTRUCTED, and it has to be: entity_table and entity_boss_parts are bss, so the
    binary carries no record to seed from — the game writes them at run time. What the cases do NOT
    do is invent a shape the game cannot produce: every field is one the spawner sets, `half_frame`
    is one of the two values the two call sites load, and the coordinates walk the same playfield
    box the routine clips against.
    """
    pokes = abi.seed_spans(seed, ((BLIT_SPRITE, BLIT_SPRITE + BLIT_SPRITE_BYTES),
                                (abi.SCREEN_BACK, abi.SCREEN_BACK + SCREEN_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[BLIT_ENTITY] = _entity_record(x, y, height, BLIT_SPRITE)
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
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


def _blit_fuzz_cases():
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
    for i, x, y, height, half_frame, seed in _blit_fuzz_cases():
        if i % BLIT_FUZZ_CHUNKS != chunk:
            continue
        _blit_case(x, y, height, half_frame, seed)


def test_geometry_constants_agree_with_their_derivations():
    """The C keeps each of these as the ORIGINAL'S OWN IMMEDIATE rather than as a product, because
    that is the only form `test_constants.py`'s scraper can pin across the language boundary — it
    reads literals, not expressions. The relationships BETWEEN them are therefore unpinned in the C,
    and this is where they are held: a frame that stops being cells x rows x row-bytes, or a row
    that stops being five words, fails here instead of quietly resizing a seeded span.
    """
    assert SPRITE_MASKED_ROW_BYTES == 2 * SPRITE_MASKED_ROW_WORDS
    assert ASTEROID_FRAME_BYTES == ASTEROID_FRAME_CELLS * ASTEROID_CELL_BYTES
    assert ASTEROID_CELL_BYTES == ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES
    assert BOSS_SPRITE_FRAME_BYTES == BOSS_SPRITE_FRAME_CELLS * BOSS_SPRITE_CELL_BYTES
    assert BOSS_SPRITE_CELL_BYTES == BOSS_SPRITE_ROWS * SPRITE_MASKED_ROW_BYTES
    assert BOSS_SPRITE_SOURCE_BYTES == BOSS_SPRITE_SOURCE_CELLS * BOSS_SPRITE_CELL_BYTES
    assert PLAYFIELD_BOTTOM_Y - PLAYFIELD_TOP_Y == PLAYFIELD_ROWS


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("SHIP_SPRITE_ROWS", "src/sprite.c", "SHIP_SPRITE_ROWS"),
    ("SHIP_SPRITE_HALF_BYTES", "src/sprite.c", "SHIP_SPRITE_HALF_BYTES"),
    ("SHIP_SPRITE_GAP", "src/sprite.c", "SHIP_SPRITE_GAP"),
    ("PRESHIFT_SLOTS", "include/sprite.h", "SPRITE_PRESHIFT_SLOTS"),
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
)
ENTRY_PROLOGUES = {
    "ENTRY_SHIP_SPRITE_DEINTERLEAVE": "323c001345e9064022d8",
    "ENTRY_SPRITE_PRESHIFT8_2PX": "42853a02e78d9a423602",
    "ENTRY_SPRITE_PRESHIFT4_4PX": "42853a02e78d9a429a42",
    "ENTRY_ASTEROID_PRESHIFT_BANK": "41e803c03e3c0006383c",
    "ENTRY_MOTHERSHIP_SPRITE_EXPAND": "41f90005ed7e43f90003",
    "ENTRY_DRAW_SPRITE_MASKED": "20790001797e302a0000",
}
