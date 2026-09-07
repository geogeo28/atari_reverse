"""Differential tests for src/sprite.c: the twelve masked sprite blitters, the five restore
blitters, the seam copy, the overlay tile merge, and `render_frame` @ 0x14446 that drives all of
them.

TWO KINDS OF STAGING, and the difference is deliberate.

The blitters are LEAVES with a register ABI — source, destination, shift, row count — so their
cases build their own arena in `abi.SCRATCH`: a 200-row screen seeded with random background (so an
AND that did not happen and an OR that did are both visible), and either a REAL sprite record's
pixels out of A\\SPRITES.cru or a seeded blob. Both matter: the real records carry mask words that
are mostly 0xffff or 0x0000, which is what a game's artwork looks like and what a carry chain's
boundaries are visible against, while a seeded blob puts every bit of every mask in play.

`render_frame` is not a leaf: it reads nine screen pointers, the map cursor, the scroll phase and
223 display records, and writes four screens. So its cases run on a MID-LEVEL image STAGED BY THE
ORIGINAL — `title_attract_loop`'s own prescroll (0x104f6 -> 0x10544, 108 calls to render_frame with
`prescroll_flag` set) replayed under the oracle from the post-load fixture. That leaves real terrain
in all four screens, `map_row_ptr` seven rows into LEVEL1.MAP and the scroll phase mid-tile, which
is the machine the routine actually runs on. `test_the_prescroll_staging_is_the_originals_own_work`
pins that the staging touched nothing but the ring and the band of scroll globals.
"""
import ctypes
import functools
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

# ---- the twelve masked sprite blitters ----------------------------------------------------------
ENTRY_SPRITE_BLIT_W16 = 0x153b2
ENTRY_SPRITE_BLIT_W32 = 0x15408
ENTRY_SPRITE_BLIT_W48 = 0x154a4
ENTRY_SPRITE_BLIT_W64 = 0x15586
ENTRY_SPRITE_BLIT_W16_CLIP_LEFT = 0x14dda
ENTRY_SPRITE_BLIT_W32_CLIP_LEFT = 0x14e98
ENTRY_SPRITE_BLIT_W48_CLIP_LEFT = 0x14fd8
ENTRY_SPRITE_BLIT_W64_CLIP_LEFT = 0x15188
ENTRY_SPRITE_BLIT_W16_CLIP_RIGHT = 0x14df0
ENTRY_SPRITE_BLIT_W32_CLIP_RIGHT = 0x14ec0
ENTRY_SPRITE_BLIT_W48_CLIP_RIGHT = 0x15012
ENTRY_SPRITE_BLIT_W64_CLIP_RIGHT = 0x151d2

# ---- the five restore blitters, the seam copy and the overlay tile merge ------------------------
ENTRY_RESTORE_BLIT_W16 = 0x14d58
ENTRY_RESTORE_BLIT_W32 = 0x14d6a
ENTRY_RESTORE_BLIT_W48 = 0x14d80
ENTRY_RESTORE_BLIT_W64 = 0x14d9a
ENTRY_RESTORE_BLIT_W80 = 0x14db8
ENTRY_SCROLL_WRAP_COPY_1280 = 0x156ae
ENTRY_TILE_BLIT_OVERLAY_MASKED = 0x14d0a

# ---- the frame ---------------------------------------------------------------------------------
ENTRY_RENDER_FRAME = 0x14446
# `title_attract_loop` @ 0x104f2 entered one instruction past its palette blackout, and stopped on
# the `clr.b prescroll_flag` that ENDS the prescroll — so the staged image still has the flag set and
# a case that wants a real frame clears it itself.
ENTRY_TITLE_PRESCROLL = 0x104f6
STOP_TITLE_PRESCROLL = 0x10544

# ---- mirrors of include/sprite.h (MIRROR_HEADER below) and of the two headers it reads ----------
A_BLIT_CLIP_MASK = 0x16426
A_SPRITE_BLIT_TBL = 0x16396
A_SPRITE_BLIT_CLIP_LEFT_TBL = 0x163a6
A_SPRITE_BLIT_CLIP_RIGHT_TBL = 0x163b6
A_RESTORE_BLIT_TBL = 0x163c6
A_TILE_SPLIT_ROW_TABLE = 0x163da
A_MAP_ROW_PTR = 0x16402
A_MAP_ROW_PTR_RESET = 0x163fe
A_SCREEN_RING_INDEX = 0x1642e
A_SCROLL_FINE = 0x16430
A_PRESCROLL_FLAG = 0x1642c
A_VBL_TICK = 0x17720
BLIT_TABLE_ENTRY_BYTES = 4
RESTORE_BLIT_TABLE_ENTRIES = 5
RESTORE_CLASS_W16 = 4
SPRITE_WIDTH_CLASSES = 4
SPRITE_GROUP_BYTES = 10
SPRITE_PLANES = 4
SCREEN_ROW_BYTES = 160
SCREEN_GROUP_BYTES = 8
SCREEN_ROWS = 200
SCREEN_LAST_ROW = 199
SCROLL_WRAP_COPY_LONGS = 80
TILE_BYTES = 512
TILE_ROW_BYTES = 16
TILE_PIXELS = 32
TILE_BAND_ROWS = 8
MAP_COLUMNS = 10
MAP_CELL_BYTES = 2
MAP_CELL_OVERLAY = 1
MAP_ROW_BYTES = 20
RENDER_FRAME_VBL_BUDGET = 3
RESTORE_LIST_LOOKBACK = 2
SCREEN_RING_SLOTS = 4

# ---- mirrors of include/display_list.h ----------------------------------------------------------
A_DISPLAY_LIST = 0x177ce
A_DISPLAY_LIST_END = 0x17d08
DISPLAY_REC_BYTES = 6
DISPLAY_REC_X = 0
DISPLAY_REC_Y = 2
DISPLAY_REC_FRAME = 4
DISPLAY_REC_ACTIVE = 5
DISPLAY_ACTIVE_HIDDEN = 0x00
DISPLAY_ACTIVE_UNDER_SCENERY = 0xff
DISPLAY_ACTIVE_ON_TOP = 0x01
DISPLAY_ACTIVE_ON_TOP_MAX = 0x7f
A_TILE_REPAIR_GRID = 0x17e0c
TILE_REPAIR_COLUMNS = 10
TILE_REPAIR_ROW_BYTES = 20
TILE_REPAIR_ID_BYTE = 1
DISPLAY_LIST_RECORDS = 223
SPRITE_RESTORE_REC_BYTES = 6
SPRITE_RESTORE_OFFSET = 0
SPRITE_RESTORE_CLASS = 2
SPRITE_RESTORE_ROWS = 4

# ---- mirrors of include/globals.h ---------------------------------------------------------------
A_SPRITE_BANK = 0x1be36
SPRITE_RECORDS = 256
SPRITE_RECORD_BYTES = 20
A_SPRITE_RESTORE_LISTS = 0x18014
SPRITE_RESTORE_LIST_BYTES = 0x200
SPRITE_RESTORE_TERMINATOR = 0xffff
A_SCREEN_DRAW = 0x16416
A_SCREEN_PREV1 = 0x1641a
A_SCREEN_PREV2 = 0x1641e
A_SCREEN_RING = 0x16406
A_SCREEN_RING_BASE = 0x16422
SCREEN_RING_BYTES = 0x1f900
SCREEN_BYTES = 0x7d00
A_TILE_BANKS = 0x38928
A_LEVEL_MAP_COLS = 0x16432

# ---- the record fields the cases read ------------------------------------------------------------
SPRITE_REC_DATA = 0
SPRITE_REC_WIDTH_CLASS = 4
SPRITE_REC_ROWS = 6
SPRITE_REC_DRAW_DX = 8
SPRITE_REC_DRAW_DY = 10

# ---- this battery's own arena, inside abi.SCRATCH -----------------------------------------------
BLIT_SCREEN = abi.SCRATCH                      # a 200-row screen, 0x7d00 bytes
BLIT_SOURCE = abi.SCRATCH + 0x8000             # seeded pixel data for the blitters
RESTORE_LIST = abi.SCRATCH + 0x9000            # a fake restore list a clipped blitter may rewrite
TILE_SCRATCH = abi.SCRATCH + 0xa000            # a base tile and an overlay tile, back to back
SCRATCH_SCREEN_BYTES = SCREEN_ROWS * SCREEN_ROW_BYTES

# Somewhere in the middle of that screen with room either side for the widest sprite and the tallest
# row count, so an unclipped case's writes are entirely inside the arena.
BLIT_DST_ROW = 60
BLIT_DST_COLUMN_BYTES = 10 * SCREEN_GROUP_BYTES
BLIT_DST = BLIT_SCREEN + BLIT_DST_ROW * SCREEN_ROW_BYTES + BLIT_DST_COLUMN_BYTES

# One real bitmap record per width class, and the shortest one there is. Every id is checked against
# the bank by `test_the_sample_sprite_records_are_the_classes_they_are_used_as`, so a bank that moved
# would fail by name rather than blit the wrong shape.
SAMPLE_RECORD = (163, 17, 68, 71)      # class 0..3; rows - 1 = 30, 31, 60, 63
SINGLE_ROW_RECORD = 47                 # class 0 with rows - 1 == 0: the `dbf`'s smallest count

# SAMPLE_RECORD[1] is record 17, whose draw offset is (+16, +9) — the only sample with one. Every
# sweep below therefore uses a record whose offset is ZERO, so the parameter IS the coordinate the
# clip ladders see; `test_render_frame_applies_the_records_own_draw_offset` is where the offset is
# exercised instead. (Measured: with record 17 the pass-A sweep's x values land at 0x60..0x150 and
# it reaches neither the left ladder nor the 0x110 threshold, contrary to its own docstring.)
ZERO_OFFSET_RECORD = SAMPLE_RECORD[3]      # record 71, class 3, draw offset (0, 0)
DRAW_OFFSET_RECORD = SAMPLE_RECORD[1]      # record 17, class 1, draw offset (+16, +9)

harness._lib.g_sprite_blit_w16.restype = None
harness._lib.g_sprite_blit_w32.restype = None
harness._lib.g_sprite_blit_w48.restype = None
harness._lib.g_sprite_blit_w64.restype = None
harness._lib.g_restore_blit_w16.restype = None
harness._lib.g_restore_blit_w32.restype = None
harness._lib.g_restore_blit_w48.restype = None
harness._lib.g_restore_blit_w64.restype = None
harness._lib.g_restore_blit_w80.restype = None
harness._lib.g_scroll_wrap_copy_1280.restype = None
harness._lib.g_tile_blit_overlay_masked.restype = None
harness._lib.g_render_frame.restype = None
for _side in ("left", "right"):
    for _width in (16, 32, 48, 64):
        getattr(harness._lib, f"g_sprite_blit_w{_width}_clip_{_side}").restype = ctypes.c_uint32

BLIT_GLUE = tuple(getattr(harness._lib, f"g_sprite_blit_w{width}") for width in (16, 32, 48, 64))
CLIP_LEFT_GLUE = tuple(getattr(harness._lib, f"g_sprite_blit_w{width}_clip_left")
                       for width in (16, 32, 48, 64))
CLIP_RIGHT_GLUE = tuple(getattr(harness._lib, f"g_sprite_blit_w{width}_clip_right")
                        for width in (16, 32, 48, 64))
ENTRY_BLIT = (ENTRY_SPRITE_BLIT_W16, ENTRY_SPRITE_BLIT_W32,
              ENTRY_SPRITE_BLIT_W48, ENTRY_SPRITE_BLIT_W64)
ENTRY_CLIP_LEFT = (ENTRY_SPRITE_BLIT_W16_CLIP_LEFT, ENTRY_SPRITE_BLIT_W32_CLIP_LEFT,
                   ENTRY_SPRITE_BLIT_W48_CLIP_LEFT, ENTRY_SPRITE_BLIT_W64_CLIP_LEFT)
ENTRY_CLIP_RIGHT = (ENTRY_SPRITE_BLIT_W16_CLIP_RIGHT, ENTRY_SPRITE_BLIT_W32_CLIP_RIGHT,
                    ENTRY_SPRITE_BLIT_W48_CLIP_RIGHT, ENTRY_SPRITE_BLIT_W64_CLIP_RIGHT)
ENTRY_RESTORE = (ENTRY_RESTORE_BLIT_W32, ENTRY_RESTORE_BLIT_W48, ENTRY_RESTORE_BLIT_W64,
                 ENTRY_RESTORE_BLIT_W80, ENTRY_RESTORE_BLIT_W16)   # restore_blit_tbl's own order
RESTORE_GLUE = tuple(getattr(harness._lib, f"g_restore_blit_w{width}")
                     for width in (32, 48, 64, 80, 16))


# =============================================================== helpers the cases share

def seeded(seed, length):
    """`length` pseudo-random bytes. The seed is the case's own, so a failure replays exactly."""
    return random.Random(seed).randbytes(length)


def screen_pokes(seed):
    """A scratch screen full of random background: an AND that never happened is then visible."""
    return {BLIT_SCREEN: seeded(seed, SCRATCH_SCREEN_BYTES)}


def sprite_record(image, record_id):
    """(data address, width class, rows - 1) of one record of the RELOCATED sprite directory."""
    base = A_SPRITE_BANK + record_id * SPRITE_RECORD_BYTES

    def word(offset):
        return int.from_bytes(image[base + offset:base + offset + 2], "big", signed=True)

    return (int.from_bytes(image[base:base + 4], "big"),
            word(SPRITE_REC_WIDTH_CLASS), word(SPRITE_REC_ROWS))


def source_row_bytes(width_class):
    return (width_class + 1) * SPRITE_GROUP_BYTES


# =============================================================== the four unclipped blitters

def _blit_case(width_class, src, shift, rows_minus_one, seed, dst=BLIT_DST, poison=False):
    pokes = screen_pokes(seed)
    regs = {"a0": src, "a1": dst, "d6": shift, "d7": rows_minus_one, "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_BLIT[width_class], regs,
        lambda lib, buf: BLIT_GLUE[width_class](buf, src, dst, shift, rows_minus_one),
        poison=poison)
    assert not diffs, (f"class={width_class} shift={shift} rows-1={rows_minus_one} "
                       f"src={src:#x}\n{report(diffs)}")


@pytest.mark.parametrize("shift", range(16))
@pytest.mark.parametrize("width_class", range(SPRITE_WIDTH_CLASSES))
def test_sprite_blit_every_shift_of_a_real_record(post_load_image, width_class, shift):
    """The whole `ror.l d6` range at every width, over the game's own artwork. Shift 0 is the case
    that has to leave the overflow group alone (its mask rotates to 0xffff and its planes to 0)."""
    src, klass, rows = sprite_record(post_load_image, SAMPLE_RECORD[width_class])
    assert klass == width_class
    _blit_case(width_class, src, shift, rows, seed=width_class * 16 + shift)


@pytest.mark.parametrize("width_class", range(SPRITE_WIDTH_CLASSES))
def test_sprite_blit_one_row(post_load_image, width_class):
    """`dbf` with a count of 0 still draws one row — the smallest thing this loop can do."""
    src, _klass, _rows = sprite_record(post_load_image, SAMPLE_RECORD[width_class])
    _blit_case(width_class, src, shift=7, rows_minus_one=0, seed=0x100 + width_class)


def test_sprite_blit_the_shortest_record_in_the_bank(post_load_image):
    """Record 47 carries rows - 1 == 0 in the bank itself, so the one-row path is game data and not
    only a count this battery chose."""
    src, klass, rows = sprite_record(post_load_image, SINGLE_ROW_RECORD)
    assert (klass, rows) == (0, 0)
    _blit_case(klass, src, shift=3, rows_minus_one=rows, seed=SINGLE_ROW_RECORD)


def test_sprite_blit_attribution():
    """Poison: the mask is what makes a masked blit attributable — a candidate that ORed the planes
    in without ANDing the background out would differ, and one that wrote nothing stays canary."""
    _blit_case(1, BLIT_SOURCE, shift=5, rows_minus_one=7, seed=0x153b2, poison=True)


BLIT_FUZZ_CHUNKS = 4
BLIT_FUZZ_CASES = 96
# The tallest record in the bank is 64 rows (rows - 1 = 63) and the shortest a single row, so this
# is the whole height range the game's own data can ask for.
BLIT_FUZZ_MAX_ROWS = 64


def blit_fuzz_cases():
    rng = random.Random(ENTRY_SPRITE_BLIT_W16)     # seeded ONCE: every chunk replays this stream
    for i in range(BLIT_FUZZ_CASES):
        yield (i,
               rng.randrange(SPRITE_WIDTH_CLASSES),
               rng.randrange(16),
               rng.randrange(BLIT_FUZZ_MAX_ROWS),
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(BLIT_FUZZ_CHUNKS))
def test_sprite_blit_fuzz(chunk):
    """RANDOM PIXEL DATA, not the game's: every bit of every mask word is in play, which the real
    artwork's runs of 0xffff and 0x0000 are not. Both are needed — the real records are what the
    carry between groups has to be right about, and these are what a mask bit dropped in the middle
    of a word would show up in."""
    for i, width_class, shift, rows_minus_one, seed in blit_fuzz_cases():
        if i % BLIT_FUZZ_CHUNKS != chunk:
            continue
        pokes = screen_pokes(seed)
        pokes[BLIT_SOURCE] = seeded(seed ^ 0x5a5a,
                                    (rows_minus_one + 1) * source_row_bytes(width_class))
        regs = {"a0": BLIT_SOURCE, "a1": BLIT_DST, "d6": shift, "d7": rows_minus_one,
                "_pokes": pokes}
        diffs, _info = differential(
            ENTRY_BLIT[width_class], regs,
            lambda lib, buf, c=width_class, r=rows_minus_one, s=shift:
                BLIT_GLUE[c](buf, BLIT_SOURCE, BLIT_DST, s, r))
        assert not diffs, (f"case {i}: class={width_class} shift={shift} rows-1={rows_minus_one}\n"
                           f"{report(diffs)}")


# =============================================================== the eight clipped blitters
#
# Each ladder's edges, transcribed from the `cmp.w` chain at the head of each routine. The cases
# below walk each rung one pixel inside its edge, at the edge itself, and one past the last one.

CLIP_LEFT_EDGES = (
    (-0x10,),
    (-0x10, -0x20),
    (-0x10, -0x20, -0x30),
    (-0x10, -0x20, -0x30, -0x40),
)
CLIP_RIGHT_EDGES = (
    (0x130, 0x140),
    (0x120, 0x130, 0x140),
    (0x110, 0x120, 0x130, 0x140),
    (0x100, 0x110, 0x120, 0x130, 0x140),
)
# The two rungs that also NARROW the restore record behind the cursor, as (class, x, new class), and
# the two classes that have no such rung. The gate byte each rung installs is not restated: it lands
# in `blit_clip_mask` at 0x16426, which is inside the image and therefore inside the byte diff.
CLIP_RIGHT_RESTORE_REWRITES = ((0, 0x138, RESTORE_CLASS_W16), (1, 0x128, 0),
                               (1, 0x138, RESTORE_CLASS_W16), (2, 0x138, None), (3, 0x138, None))

# The restore record the clipped blitters may rewrite or take back. The cursor points one record PAST
# it, exactly as render_frame leaves it, so the routine's `-4(a5)` reaches its class word.
RESTORE_CURSOR = RESTORE_LIST + SPRITE_RESTORE_REC_BYTES
PENDING_RESTORE_OFFSET = 0x1234
PENDING_RESTORE_CLASS = 3
PENDING_RESTORE_ROWS = 31


def restore_record(offset, width_class, rows_minus_one):
    """One six-byte restore record, built through include/display_list.h's frozen field offsets."""
    record = bytearray(SPRITE_RESTORE_REC_BYTES)
    record[SPRITE_RESTORE_OFFSET:SPRITE_RESTORE_OFFSET + 2] = offset.to_bytes(2, "big")
    record[SPRITE_RESTORE_CLASS:SPRITE_RESTORE_CLASS + 2] = width_class.to_bytes(2, "big")
    record[SPRITE_RESTORE_ROWS:SPRITE_RESTORE_ROWS + 2] = rows_minus_one.to_bytes(2, "big")
    return bytes(record)


PENDING_RESTORE_RECORD = restore_record(PENDING_RESTORE_OFFSET, PENDING_RESTORE_CLASS,
                                        PENDING_RESTORE_ROWS)
# ...followed by terminators, so a blitter that walked past the record it was given is not reading
# whatever the scratch map happened to hold.
RESTORE_LIST_TAIL = SPRITE_RESTORE_TERMINATOR.to_bytes(2, "big") * 3


# The widest, tallest blob any clip case can ask for, so `_clip_case` can seed one source buffer
# without knowing which class and row count it is about to be given.
CLIP_SOURCE_BYTES = SPRITE_WIDTH_CLASSES * SPRITE_GROUP_BYTES * (BLIT_FUZZ_MAX_ROWS + 1)


def _clip_case(entry, glue, width_class, src, x, shift, rows_minus_one, seed, poison=False):
    pokes = screen_pokes(seed)
    pokes[BLIT_SOURCE] = seeded(seed ^ 0x3c3c, CLIP_SOURCE_BYTES)
    pokes[RESTORE_LIST] = PENDING_RESTORE_RECORD + RESTORE_LIST_TAIL
    regs = {"a0": src, "a1": BLIT_DST, "d6": shift, "d7": rows_minus_one,
            "d4": x & 0xffff, "a5": RESTORE_CURSOR, "_pokes": pokes}
    diffs, info = differential(
        entry, regs,
        lambda lib, buf: glue(buf, src, BLIT_DST, shift, rows_minus_one, x & 0xffff,
                              RESTORE_CURSOR),
        poison=poison)
    assert not diffs, (f"class={width_class} x={x:#x} shift={shift} rows-1={rows_minus_one}\n"
                       f"{report(diffs)}")
    return info


def _assert_cursor_agrees(info, expected):
    """The restore cursor is a REGISTER answer: an abort's only other effect is that it drew
    nothing, which an untouched screen cannot tell from a sprite whose gate was empty."""
    assert info["regs"]["a5"] == expected, (
        f"oracle left a5 = {info['regs']['a5']:#x}, candidate returned {expected:#x}")
    assert info["ret"] == expected


@pytest.mark.parametrize("width_class", range(SPRITE_WIDTH_CLASSES))
def test_sprite_blit_clip_left_every_rung(post_load_image, width_class):
    """Every rung of a left ladder at its own edge and one pixel inside it, then one pixel past the
    last: that last x draws NOTHING and rewinds the caller's restore cursor by a record."""
    src, _klass, rows = sprite_record(post_load_image, SAMPLE_RECORD[width_class])
    edges = CLIP_LEFT_EDGES[width_class]

    for edge in edges:
        for x in (edge, edge + 1):
            info = _clip_case(ENTRY_CLIP_LEFT[width_class], CLIP_LEFT_GLUE[width_class],
                              width_class, src, x, shift=x & 0xf, rows_minus_one=rows,
                              seed=0x2000 + width_class * 0x100 + (x & 0xff))
            _assert_cursor_agrees(info, RESTORE_CURSOR)

    off_screen = edges[-1] - 1
    info = _clip_case(ENTRY_CLIP_LEFT[width_class], CLIP_LEFT_GLUE[width_class], width_class, src,
                      off_screen, shift=off_screen & 0xf, rows_minus_one=rows,
                      seed=0x3000 + width_class)
    _assert_cursor_agrees(info, RESTORE_CURSOR - SPRITE_RESTORE_REC_BYTES)


@pytest.mark.parametrize("width_class", range(SPRITE_WIDTH_CLASSES))
def test_sprite_blit_clip_right_every_rung(post_load_image, width_class):
    """The same for the right ladders — where two of the four also NARROW the restore record they
    find behind the cursor, and the other two do not (`../STATUS.md` records that asymmetry as the
    original's own bug, reproduced)."""
    src, _klass, rows = sprite_record(post_load_image, SAMPLE_RECORD[width_class])
    edges = CLIP_RIGHT_EDGES[width_class]

    for edge in edges:
        for x in (edge - 1, edge - 0x10):
            info = _clip_case(ENTRY_CLIP_RIGHT[width_class], CLIP_RIGHT_GLUE[width_class],
                              width_class, src, x, shift=x & 0xf, rows_minus_one=rows,
                              seed=0x4000 + width_class * 0x100 + (x & 0xff))
            _assert_cursor_agrees(info, RESTORE_CURSOR)

    off_screen = edges[-1]
    info = _clip_case(ENTRY_CLIP_RIGHT[width_class], CLIP_RIGHT_GLUE[width_class], width_class, src,
                      off_screen, shift=off_screen & 0xf, rows_minus_one=rows,
                      seed=0x5000 + width_class)
    _assert_cursor_agrees(info, RESTORE_CURSOR - SPRITE_RESTORE_REC_BYTES)


# ---- the clip gate is READ FROM MEMORY, once per group per row --------------------------------
#
# A destination whose first screen group covers `blit_clip_mask` itself. Group 0's fourth plane word
# is written at dst + 6, so dst = 0x16426 - 6 puts the gate byte under it and group 1's own
# `btst #0,$16426.l` then reads what group 0 just wrote.
CLIP_MASK_OVERLAP_DST = A_BLIT_CLIP_MASK - 6
CLIP_MASK_OVERLAP_SHIFT = 7
# Five source words for one 16-pixel group, chosen so the byte group 0 leaves on the gate has BIT 0
# CLEAR while the rung installed 0x03 (both groups). The mask word is 0 and the fourth plane word is
# 0, which at this shift makes the merged word's bit 8 — the gate byte's bit 0 — zero; the other
# three planes carry low bits so that group 1, if it draws at all, visibly changes the screen.
CLIP_MASK_OVERLAP_SOURCE = b"".join(w.to_bytes(2, "big") for w in (0x0000, 0x7f7f, 0x7f7f, 0x7f7f,
                                                                   0x0000))
# The x that selects CLIP_RIGHT_W16's first rung, whose gate is 0x03: both of a class-0 sprite's
# screen groups, which is what makes group 0's write reach group 1's test.
CLIP_MASK_OVERLAP_X = 0x12f


def test_a_clipped_blit_re_reads_its_gate_from_memory_every_group():
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    The original never holds `blit_clip_mask` in a register: every screen group of every row is
    gated by its own `btst #n,$16426.l` (0x14e40, 0x14e6c, 0x1512e, 0x1515c and the rest), inside
    the row loop. So a blit whose own destination covers 0x16426 draws its later groups under the
    gate its earlier ones wrote — and a reconstruction that read the gate once and passed it down
    would draw group 1 here, where the machine does not.

    Nothing the game does can reach this: every destination it computes is inside the screen ring at
    0x60000 and above, and 0x16426 is in the program's own data. Only a poked destination separates
    the two spellings, which is what this is.
    """
    pokes = {BLIT_SOURCE: CLIP_MASK_OVERLAP_SOURCE,
             RESTORE_LIST: PENDING_RESTORE_RECORD + RESTORE_LIST_TAIL}
    regs = {"a0": BLIT_SOURCE, "a1": CLIP_MASK_OVERLAP_DST, "d6": CLIP_MASK_OVERLAP_SHIFT, "d7": 0,
            "d4": CLIP_MASK_OVERLAP_X, "a5": RESTORE_CURSOR, "_pokes": pokes}
    diffs, info = differential(
        ENTRY_CLIP_RIGHT[0], regs,
        lambda lib, buf: CLIP_RIGHT_GLUE[0](buf, BLIT_SOURCE, CLIP_MASK_OVERLAP_DST,
                                            CLIP_MASK_OVERLAP_SHIFT, 0, CLIP_MASK_OVERLAP_X,
                                            RESTORE_CURSOR))
    assert not diffs, f"gate re-read\n{report(diffs)}"
    _assert_cursor_agrees(info, RESTORE_CURSOR)


def test_sprite_blit_clip_narrows_the_restore_record():
    """The rungs that rewrite `-4(a5)`, and the two classes that have no such rung.

    The differential alone would pin this — the class word is in the image, so both sides write it
    — but it would not SAY which value, and a reader of the ladder tables has no other way to check
    the third column. So the case also reads the record back out of the ORACLE's own final image and
    names the value: `RESTORE_CLASS_W16`, class 0, or the class the record already held.
    """
    for width_class, x, new_class in CLIP_RIGHT_RESTORE_REWRITES:
        info = _clip_case(ENTRY_CLIP_RIGHT[width_class], CLIP_RIGHT_GLUE[width_class], width_class,
                          BLIT_SOURCE, x, shift=x & 0xf, rows_minus_one=3,
                          seed=0x6000 + width_class * 0x100 + (x & 0xff))
        _assert_cursor_agrees(info, RESTORE_CURSOR)
        # `info["writes"]` is the ORACLE's write set, {address: byte}. Nothing else in the run
        # touches the pending record, so these two bytes are present exactly when the rung rewrote
        # the class, and hold exactly what it wrote.
        written = tuple(info["writes"].get(RESTORE_LIST + SPRITE_RESTORE_CLASS + byte)
                        for byte in range(2))
        expected = (None, None) if new_class is None else tuple(new_class.to_bytes(2, "big"))
        assert written == expected, (
            f"class {width_class} at x={x:#x}: the original wrote {written} into the pending "
            f"restore record's class word, not {expected}")


def test_sprite_blit_clip_attribution():
    """Poison over a partly gated blit: the groups the gate lets through must really be written and
    the ones it stops must really be left alone."""
    info = _clip_case(ENTRY_CLIP_LEFT[3], CLIP_LEFT_GLUE[3], 3, BLIT_SOURCE, -0x20, shift=0,
                      rows_minus_one=5, seed=0x15188, poison=True)
    _assert_cursor_agrees(info, RESTORE_CURSOR)


CLIP_FUZZ_CHUNKS = 4
CLIP_FUZZ_CASES = 96
# One group past the widest sprite either side, so every rung and both aborts are inside the sweep.
CLIP_FUZZ_X_LOW = -0x50
CLIP_FUZZ_X_HIGH = 0x150


def clip_fuzz_cases():
    rng = random.Random(ENTRY_SPRITE_BLIT_W64_CLIP_LEFT)
    for i in range(CLIP_FUZZ_CASES):
        width_class = rng.randrange(SPRITE_WIDTH_CLASSES)
        at_left = rng.randrange(2)
        x = (rng.randrange(CLIP_FUZZ_X_LOW, 0) if at_left
             else rng.randrange(0xf0, CLIP_FUZZ_X_HIGH))
        yield (i, width_class, at_left, x, rng.randrange(16),
               rng.randrange(BLIT_FUZZ_MAX_ROWS), rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(CLIP_FUZZ_CHUNKS))
def test_sprite_blit_clip_fuzz(chunk):
    """Both ladders, every class, random pixel data — and the restore cursor checked on every case,
    so an abort that forgot the rewind fails here even where it wrote nothing either way."""
    for i, width_class, at_left, x, shift, rows_minus_one, seed in clip_fuzz_cases():
        if i % CLIP_FUZZ_CHUNKS != chunk:
            continue
        entries, glues, edges = ((ENTRY_CLIP_LEFT, CLIP_LEFT_GLUE, CLIP_LEFT_EDGES) if at_left
                                 else (ENTRY_CLIP_RIGHT, CLIP_RIGHT_GLUE, CLIP_RIGHT_EDGES))
        pokes = screen_pokes(seed)
        pokes[BLIT_SOURCE] = seeded(seed ^ 0x5a5a,
                                    (rows_minus_one + 1) * source_row_bytes(width_class))
        pokes[RESTORE_LIST] = PENDING_RESTORE_RECORD + RESTORE_LIST_TAIL
        regs = {"a0": BLIT_SOURCE, "a1": BLIT_DST, "d6": shift, "d7": rows_minus_one,
                "d4": x & 0xffff, "a5": RESTORE_CURSOR, "_pokes": pokes}
        diffs, info = differential(
            entries[width_class], regs,
            lambda lib, buf, g=glues, c=width_class, s=shift, r=rows_minus_one, xx=x:
                g[c](buf, BLIT_SOURCE, BLIT_DST, s, r, xx & 0xffff, RESTORE_CURSOR))
        assert not diffs, (f"case {i}: class={width_class} x={x:#x} shift={shift} "
                           f"rows-1={rows_minus_one}\n{report(diffs)}")
        last_edge = edges[width_class][-1]
        drawn = x >= last_edge if at_left else x < last_edge
        _assert_cursor_agrees(
            info, RESTORE_CURSOR if drawn else RESTORE_CURSOR - SPRITE_RESTORE_REC_BYTES)


# =============================================================== the restore blitters and the seam

RESTORE_SRC = BLIT_SCREEN + 40 * SCREEN_ROW_BYTES
RESTORE_DST = BLIT_SCREEN + 100 * SCREEN_ROW_BYTES + 24


@pytest.mark.parametrize("rows_minus_one", (0, 1, 31, 63))
@pytest.mark.parametrize("index", range(RESTORE_BLIT_TABLE_ENTRIES))
def test_restore_blit_every_width(index, rows_minus_one):
    """All five entries of `restore_blit_tbl`, INDEX 4 INCLUDED — the 16-pixel one the notes said
    nothing reached. Each copies its own byte count per row and then steps both cursors a whole
    160-byte row, which a wrong `lea` would shear."""
    pokes = screen_pokes(0x7000 + index * 0x100 + rows_minus_one)
    regs = {"a0": RESTORE_SRC, "a1": RESTORE_DST, "d7": rows_minus_one, "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_RESTORE[index], regs,
        lambda lib, buf: RESTORE_GLUE[index](buf, RESTORE_SRC, RESTORE_DST, rows_minus_one))
    assert not diffs, f"restore index={index} rows-1={rows_minus_one}\n{report(diffs)}"


def test_restore_blit_attribution():
    """Poison over the widest one: a candidate that copied nothing leaves the canary standing."""
    pokes = screen_pokes(ENTRY_RESTORE_BLIT_W80)
    regs = {"a0": RESTORE_SRC, "a1": RESTORE_DST, "d7": 9, "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_RESTORE_BLIT_W80, regs,
        lambda lib, buf: harness._lib.g_restore_blit_w80(buf, RESTORE_SRC, RESTORE_DST, 9),
        poison=True)
    assert not diffs, report(diffs)


def test_scroll_wrap_copy_1280_copies_two_whole_rows():
    """80 longwords with nothing between them: the routine's whole content is that it is 320 bytes
    and not 319 or 321, which a seeded destination shows at either end."""
    src = BLIT_SCREEN + 8 * SCREEN_ROW_BYTES
    dst = BLIT_SCREEN + 120 * SCREEN_ROW_BYTES
    pokes = screen_pokes(ENTRY_SCROLL_WRAP_COPY_1280)
    regs = {"a0": src, "a1": dst, "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_SCROLL_WRAP_COPY_1280, regs,
        lambda lib, buf: harness._lib.g_scroll_wrap_copy_1280(buf, src, dst), poison=True)
    assert not diffs, report(diffs)


# =============================================================== tile_blit_overlay_masked

TILE_BASE_SRC = TILE_SCRATCH
TILE_OVERLAY_SRC = TILE_SCRATCH + TILE_BYTES


@pytest.mark.parametrize("rows_minus_one", (0, 3, 7, 31))
def test_tile_blit_overlay_masked_over_seeded_tiles(rows_minus_one):
    """A random base under a random overlay: with pseudo-random planes the keep mask is different in
    every word, which a colour-0 test applied per LONGWORD rather than per word would fail."""
    dst = BLIT_SCREEN + 20 * SCREEN_ROW_BYTES + 32
    pokes = screen_pokes(0x8000 + rows_minus_one)
    pokes[TILE_SCRATCH] = seeded(0x14d0a + rows_minus_one, 2 * TILE_BYTES)
    regs = {"a0": TILE_BASE_SRC, "a5": TILE_OVERLAY_SRC, "a2": dst, "d3": rows_minus_one,
            "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_TILE_BLIT_OVERLAY_MASKED, regs,
        lambda lib, buf: harness._lib.g_tile_blit_overlay_masked(
            buf, TILE_BASE_SRC, TILE_OVERLAY_SRC, dst, rows_minus_one))
    assert not diffs, f"rows-1={rows_minus_one}\n{report(diffs)}"


def test_tile_blit_overlay_masked_over_the_games_own_tiles(post_load_image):
    """The real HSC banks: an overlay tile is mostly colour 0, so this is the case where the keep
    mask is nearly all ones and a dropped AND would still look almost right."""
    dst = BLIT_SCREEN + 50 * SCREEN_ROW_BYTES + 48
    base = A_TILE_BANKS + 1 * TILE_BYTES
    overlay = A_TILE_BANKS + 2 * TILE_BYTES
    pokes = screen_pokes(0x9000)
    regs = {"a0": base, "a5": overlay, "a2": dst, "d3": TILE_PIXELS - 1, "_pokes": pokes}
    diffs, _info = differential(
        ENTRY_TILE_BLIT_OVERLAY_MASKED, regs,
        lambda lib, buf: harness._lib.g_tile_blit_overlay_masked(
            buf, base, overlay, dst, TILE_PIXELS - 1),
        poison=True)
    assert not diffs, report(diffs)


# =============================================================== render_frame @ 0x14446

RENDER_FRAME_MAX_INSNS = 2_000_000
PRESCROLL_MAX_INSNS = 8_000_000
# The two bands the prescroll staging is allowed to have moved. Everything else it touched would be
# state this battery does not know it is running on, so `test_the_prescroll_staging_...` refuses it.
STAGED_GLOBALS = (A_MAP_ROW_PTR_RESET, A_LEVEL_MAP_COLS)
# `abi.SCREEN_RING_SPAN` is that expression's one home, and its comment says why: the span
# cannot drift from the model the cores compile against. Restating it here would void that.
STAGED_RING = abi.SCREEN_RING_SPAN


@functools.lru_cache(maxsize=None)
def _prescrolled(post_load_bytes):
    """The post-load image with `title_attract_loop`'s own prescroll run ON IT BY THE ORIGINAL.

    Cached on the fixture's bytes, so the 108 frames run once per session however many cases ask.
    """
    final, _writes, _regs = emu.run(bytearray(post_load_bytes), ENTRY_TITLE_PRESCROLL,
                                    stop_pc=STOP_TITLE_PRESCROLL, max_insns=PRESCROLL_MAX_INSNS)
    return bytes(final)


def staged_pokes(post_load_image):
    """The prescrolled machine as pokes over the post-load base, in its two bands."""
    staged = _prescrolled(bytes(post_load_image))
    return {lo: staged[lo:hi] for lo, hi in (STAGED_GLOBALS, STAGED_RING)}


def _frame_pokes(post_load_image, records=(), prescroll=False, extra=None):
    """A render_frame case's image: the staged level, the VBL budget already spent, and `records`
    poked into the display list as (slot, x, y, frame id, active).

    `extra` is applied LAST and is meant to overlap: several cases override one global inside the
    staged bands (a screen pointer, the scroll phase, the ring index) or replace a whole band.
    `harness.make_image` walks the poke dict in insertion order, so a later key wins over an earlier
    one that covers the same bytes — which is why `extra` is added after everything else and not
    merged into it.
    """
    pokes = staged_pokes(post_load_image)
    pokes[A_PRESCROLL_FLAG] = bytes([1 if prescroll else 0])
    pokes[A_VBL_TICK] = RENDER_FRAME_VBL_BUDGET.to_bytes(4, "big")
    for slot, x, y, frame, active in records:
        record = bytearray(DISPLAY_REC_BYTES)
        record[DISPLAY_REC_X:DISPLAY_REC_X + 2] = (x & 0xffff).to_bytes(2, "big")
        record[DISPLAY_REC_Y:DISPLAY_REC_Y + 2] = (y & 0xffff).to_bytes(2, "big")
        record[DISPLAY_REC_FRAME] = frame
        record[DISPLAY_REC_ACTIVE] = active
        pokes[A_DISPLAY_LIST + slot * DISPLAY_REC_BYTES] = bytes(record)
    for addr, data in (extra or {}).items():
        pokes[addr] = data
    return pokes


def _frame_case(post_load_image, what, **kwargs):
    pokes = _frame_pokes(post_load_image, **kwargs)
    diffs, _info = differential(ENTRY_RENDER_FRAME, {"_pokes": pokes},
                                lambda lib, buf: lib.g_render_frame(buf),
                                max_insns=RENDER_FRAME_MAX_INSNS)
    assert not diffs, f"{what}\n{report(diffs)}"


def test_render_frame_prescroll_skips_everything_that_draws(post_load_image):
    """`prescroll_flag` set: no display-list pass, no overlay repaint, NO Setscreen and no Vsync —
    only the seam, the scroll step, the new tile band and the restore replay. The event ledger is
    compared on every case, so a candidate that published a frame here fails on the ledger even
    though the pixels would agree."""
    _frame_case(post_load_image, "prescroll", prescroll=True)


# The instruction the original's under-budget wait re-reads `vbl_tick` at, and the frame budget it
# waits for. Only the VBL handler moves that counter, so the wait is spelt through the kit's
# SCHEDULED WRITE model on both shores (`tools/recreate_kit/include/sched.h`).
WAIT_PC_VBL_BUDGET = 0x1479c


@pytest.mark.parametrize("entry_tick", (0, RENDER_FRAME_VBL_BUDGET - 1))
@pytest.mark.parametrize("arrival", (1, 2, 5))
def test_render_frame_waits_out_the_rest_of_its_frame_budget(post_load_image, arrival, entry_tick):
    """The arm no other case reaches: `vbl_tick` BELOW the budget on entry, so the routine spins
    instead of calling Vsync until the level-4 handler has counted the third VBL.

    An external agent supplies that handler's store — the same mechanism `test_hud.py` uses for the
    two ACIA waits — arriving before the 1st, 2nd and 5th time round the loop. Without it the wait
    never ends on either side, which is why every OTHER case in this battery enters with the budget
    already spent. `entry_tick` is what pins the budget FROM BELOW: at a tick of BUDGET - 1 the gate
    still falls through to the wait, and a smaller budget would Vsync instead and make no poll at
    all — measured, that mutation survives every case that enters at 0.

    The `Vsync` the other arm makes is an ordered OS EVENT, so the two arms are separable by the
    event ledger as well as by the counter this run leaves cleared.
    """
    pokes = _frame_pokes(post_load_image, records=[PASS_A_SPRITE])
    pokes[A_VBL_TICK] = entry_tick.to_bytes(4, "big")
    diffs, _info = differential(
        ENTRY_RENDER_FRAME, {"_pokes": pokes},
        lambda lib, buf: lib.g_render_frame(buf),
        max_insns=RENDER_FRAME_MAX_INSNS,
        schedule=[{"pc": WAIT_PC_VBL_BUDGET, "nth": arrival, "addr": A_VBL_TICK, "width": 4,
                   "value": RENDER_FRAME_VBL_BUDGET}])
    assert not diffs, f"vbl wait from {entry_tick}, arrival {arrival}\n{report(diffs)}"


def test_render_frame_with_an_empty_display_list(post_load_image):
    """The ordinary frame with nothing published: both passes walk all 223 records and draw none,
    the terminator lands at the head of this screen's restore list, and Setscreen + Vsync go into
    the event ledger."""
    _frame_case(post_load_image, "empty list")


PASS_A_SPRITE = (17, 0x50, 0x40, SAMPLE_RECORD[1], DISPLAY_ACTIVE_UNDER_SCENERY)
PASS_B_SPRITE = (18, 0x80, 0x60, SAMPLE_RECORD[2], DISPLAY_ACTIVE_ON_TOP)


@pytest.mark.parametrize("x", (0x50, 0x51, 0x5f, -0x10, -1, 0x10f, 0x110, 0x13f, 0x140))
def test_render_frame_draws_one_pass_a_sprite(post_load_image, x):
    """One record with a negative active byte, walked across the screen: the middle, every sub-word
    phase boundary, both clip ladders and one x past each of them. 0x10f/0x110 is pass A's own
    right-edge threshold, which nothing else in this battery separates from a lower one. Pass A also
    marks the tile repair grid, so the overlay repaint that follows is driven by this sprite."""
    _frame_case(post_load_image, f"pass A at x={x:#x}",
                records=[(17, x, 0x40, ZERO_OFFSET_RECORD, DISPLAY_ACTIVE_UNDER_SCENERY)])


def test_render_frame_applies_the_records_own_draw_offset(post_load_image):
    """The sprite record's `+8`/`+10` draw offset, added to the display record's x and y BEFORE
    either clip. Record 17 carries (+16, +9) — the only sample that has one — so this display record
    at x = 0x100 is a sprite at 0x110, over pass A's right-edge threshold, where the same x with a
    zero-offset record is not. Every sweep above uses a zero-offset record for exactly that reason:
    with record 17 they would sweep 0x60..0x150 and reach neither ladder (measured)."""
    _frame_case(post_load_image, "draw offset",
                records=[(17, 0x100, 0x37, DRAW_OFFSET_RECORD, DISPLAY_ACTIVE_UNDER_SCENERY)])


@pytest.mark.parametrize("x", (0x80, 0xf0, 0xf1, 0x13f, 0x140))
def test_render_frame_draws_one_pass_b_sprite(post_load_image, x):
    """Pass B's right-edge clip starts at x > 0xf0, not at 0x110 — the two passes really do use
    different thresholds, and 0xf0/0xf1 is where a transcription that used one for both would fail
    (measured: nothing else in this battery separates them)."""
    _frame_case(post_load_image, f"pass B at x={x:#x}",
                records=[(18, x, 0x60, SAMPLE_RECORD[2], DISPLAY_ACTIVE_ON_TOP)])   # dx = 0


@pytest.mark.parametrize("y", (-0x40, -0x3f, -1, 0, 1, 0xc6, 0xc7, 0xc8, 0x100))
def test_render_frame_clips_a_sprite_vertically(post_load_image, y):
    """The top clip advances the SOURCE by (class + 1) * 10 a hidden row and the bottom clip cuts
    the row count at row 199. Record 71 is 64 rows, so y = -0x3f leaves EXACTLY ONE and y = -0x40
    leaves none — the pair that tells the `bmi` after `add.w d1,d7` from a `ble` (measured: `< 0`
    mutated to `<= 0` survives every other case). y = 0xc7 is the last row that draws at all."""
    _frame_case(post_load_image, f"vertical clip y={y:#x}",
                records=[(19, 0x60, y, ZERO_OFFSET_RECORD, DISPLAY_ACTIVE_UNDER_SCENERY)])


def test_render_frame_draws_both_passes_and_repaints_the_scenery(post_load_image):
    """The whole pipeline in one frame: a pass-A sprite marked into the repair grid, the overlay
    tiles painted back over it, then a pass-B sprite on top. The two restore records are appended to
    ONE list and the terminator goes past the second."""
    _frame_case(post_load_image, "both passes", records=[PASS_A_SPRITE, PASS_B_SPRITE])


# LEVEL1.MAP's own overlay data. Rows 180-182 carry non-zero overlay bytes in columns 4 and 5
# (`tools/extract_assets.py`'s "sparse second layer"); 122 of the 183 rows carry some, but these
# three sit in a block, which is what lets one sprite land on four non-zero cells at once. The
# staged cursor is at row 176, whose neighbourhood is all zeros, so a case that wants the repaint to
# have work must move the cursor — the map is the game's own, only the cursor is the case's.
A_LEVEL_MAP_CELLS = 0x16436
OVERLAY_MAP_ROW = 180
# ...and a sprite whose top-left corner lands in that row's column 4 and straddles into column 5 and
# the row below. row = (y + 32 - scroll_fine) >> 5 and column = x >> 5, at the staged phase of 22.
OVERLAY_SPRITE_X = 0x84
OVERLAY_SPRITE_Y = 5


def _overlay_map_pokes(row=OVERLAY_MAP_ROW):
    return {A_MAP_ROW_PTR: (A_LEVEL_MAP_CELLS + row * MAP_ROW_BYTES).to_bytes(4, "big")}


def test_render_frame_repaints_the_maps_own_overlay_tiles(post_load_image):
    """A pass-A sprite over four map cells that really carry overlay tiles, so pass A's four
    `move.b` copies each move a NON-ZERO id into the grid and the repaint has four tiles to paint
    back over the sprite.

    The cursor is moved because the staged one sits in a run of empty rows: measured, the case this
    replaces poked overlay bytes into cells the sprite did not touch and changed no grid byte at
    all, so it exercised the tile BAND's masked path and nothing of the repair grid.
    """
    _frame_case(post_load_image, "overlay repaint",
                records=[(20, OVERLAY_SPRITE_X, OVERLAY_SPRITE_Y, SAMPLE_RECORD[0],
                          DISPLAY_ACTIVE_UNDER_SCENERY)],
                extra=_overlay_map_pokes())


@pytest.mark.parametrize("x,y", ((OVERLAY_SPRITE_X & ~0x1f, OVERLAY_SPRITE_Y),
                                 (OVERLAY_SPRITE_X, 22),
                                 (OVERLAY_SPRITE_X & ~0x1f, 22)))
def test_render_frame_marks_only_the_cells_a_sprite_straddles(post_load_image, x, y):
    """The two span conditions, each switched off in turn and then both. A sprite on a 32-pixel
    column boundary marks no cell to its right (`andi.w #$1f,d1 / beq`), one on the phase's own row
    boundary marks none below it, and one on both marks a single cell."""
    _frame_case(post_load_image, f"repair-grid spans at ({x:#x}, {y})",
                records=[(20, x, y, SAMPLE_RECORD[0], DISPLAY_ACTIVE_UNDER_SCENERY)],
                extra=_overlay_map_pokes())


# Map rows 24-26 carry overlays in COLUMN 9 (193, 203, 205) — the far side of the row, which is
# where a cell index of -1 lands when the marking walks backwards off column 0.
NEGATIVE_COLUMN_MAP_ROW = 24


def test_render_frame_marks_a_cell_before_the_grid(post_load_image):
    """A sprite clipped off the LEFT edge gives column -1 — `asr.w #5,d1` on a negative x — so the
    cell index is NEGATIVE and all four marks land before the cell the row starts at. The original's
    own behaviour, and the only case that separates the signed shift from a logical one (measured: a
    logical shift survives every other case in this battery). The cursor is put on map row 24 so the
    four cells the negative index really names carry the game's own non-zero overlay ids; over an
    empty row the case would copy zero over zero and see nothing."""
    _frame_case(post_load_image, "negative repair-grid column",
                records=[(20, -8, OVERLAY_SPRITE_Y + TILE_PIXELS, SAMPLE_RECORD[0],
                          DISPLAY_ACTIVE_UNDER_SCENERY)],
                extra=_overlay_map_pokes(NEGATIVE_COLUMN_MAP_ROW))


# The band's split pair at each of the three shapes its two halves can take. The upper half is drawn
# from the cursor's own cell and the lower from the cell one map row on, so a phase that zeroes
# either count leaves that call unmade.
BAND_SPLIT_LOWER_ONLY = 0     # table[0..1] = (8, 0)
BAND_SPLIT_BOTH_HALVES = 2    # table[2..3] = (6, 2)
BAND_SPLIT_UPPER_ONLY = 8     # table[8..9] = (0, 8), and the staged phase of 22 is the same pair


@pytest.mark.parametrize("scroll_fine", (BAND_SPLIT_LOWER_ONLY, BAND_SPLIT_BOTH_HALVES,
                                         BAND_SPLIT_UPPER_ONLY))
def test_render_frame_merges_overlay_tiles_into_the_band(post_load_image, scroll_fine):
    """The tile band's MASKED path, at all three split shapes. Measured: with only the staged phase
    the lower half's `tile_blit_overlay_masked` call is never made at all, and deleting it — or the
    screen-cursor advance after the upper half — survives the whole battery."""
    _frame_case(post_load_image, f"band overlay merge at phase {scroll_fine}",
                extra={**_overlay_map_pokes(), A_SCROLL_FINE: scroll_fine.to_bytes(2, "big")})


# Two cursor positions where exactly ONE of a column's two cells carries an overlay, out of the
# map's own data: row 165 has overlays and row 166 has none (upper only); row 179 has none and row
# 180 does (lower only). Both are needed — with both cells set, reading either one alone agrees.
UPPER_ONLY_MAP_ROW = 165
LOWER_ONLY_MAP_ROW = 179


@pytest.mark.parametrize("row", (UPPER_ONLY_MAP_ROW, LOWER_ONLY_MAP_ROW))
def test_render_frame_takes_the_masked_band_path_on_either_cells_overlay(post_load_image, row):
    """`move.b 1(a3),d1 / or.b 21(a3),d1` — the path is chosen on the OR of the column's two cells,
    so a column whose overlay is on only ONE of them still merges. Both halves have to be running
    for the difference to show, which is why the phase is forced."""
    _frame_case(post_load_image, f"masked band from map row {row} only",
                extra={**_overlay_map_pokes(row),
                       A_SCROLL_FINE: BAND_SPLIT_BOTH_HALVES.to_bytes(2, "big")})


# `tile_split_row_table`'s ODD entries do not sum to TILE_BAND_ROWS — index 1 is (0, 6) and index 3
# is (2, 4) — which is the only input that separates the band's screen advance from a fixed
# +16 a column. The game cannot produce an odd phase: it is seeded 0x1e, stepped +2 and masked to
# 0x1f, and the one other writer (`restart_level_at_checkpoint` @ 0x14bb6, which restores a
# checkpoint record's +4 word) is fed from five shipped tables whose every phase field is even.
# CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.
@pytest.mark.parametrize("scroll_fine", (1, 3, 7))
def test_render_frame_at_an_odd_scroll_phase(post_load_image, scroll_fine):
    """A split pair that does NOT sum to 8, so the tile band's `lea -1264(a2),a2` lands somewhere
    other than the next column's top and every column after the first is drawn 304 bytes lower."""
    _frame_case(post_load_image, f"odd scroll phase {scroll_fine}",
                extra={A_SCROLL_FINE: scroll_fine.to_bytes(2, "big")})


@pytest.mark.parametrize("index", range(SCREEN_RING_SLOTS))
def test_render_frame_every_screen_in_the_ring(post_load_image, index):
    """The four rotating buffers: which list is written, which is replayed, and which pointer the
    scroll step decrements all key off this index."""
    _frame_case(post_load_image, f"ring index {index}",
                extra={A_SCREEN_RING_INDEX: index.to_bytes(2, "big")})


# Every screen base the game can hold is `ring_base + k * 0x500`: boot_init's four offsets are 24,
# 50, 75 and 100 of them, the scroll step subtracts one, and the reseat adds 0x1f900 = 101 of them.
# So k = 25 lands EXACTLY on the seam's limit and k = 24 is the highest that is inside it — the pair
# that separates the `bge` from a `bgt`, and both of them bases the game really reaches.
SCREEN_STEP_BYTES = 0x500
SEAM_LIMIT_STEPS = SCREEN_BYTES // SCREEN_STEP_BYTES        # 25, and 25 * 0x500 == SCREEN_BYTES


@pytest.mark.parametrize("steps", (1, SEAM_LIMIT_STEPS - 1, SEAM_LIMIT_STEPS))
def test_render_frame_copies_the_ring_seam(post_load_image, steps):
    """The draw base inside the ring's lowest frame is the only thing that arms the four
    `scroll_wrap_copy_1280` calls — the staged image's own base is well above it, so nothing else in
    this battery reaches them through render_frame. `steps == SEAM_LIMIT_STEPS` is the base AT the
    limit, which is not copied: `cmpa.l a1,a0 / bge` and a `bgt` agree everywhere else (measured —
    the mutation survives without this case)."""
    base = abi.SCREEN_RING_BASE + steps * SCREEN_STEP_BYTES
    _frame_case(post_load_image, f"seam copy at ring_base + {steps} steps",
                extra={A_SCREEN_DRAW: base.to_bytes(4, "big")})


def test_render_frame_wraps_a_screen_pointer_round_the_ring(post_load_image):
    """The slot the scroll step decrements lands ON the ring's low limit, so it is reseated a whole
    ring higher rather than stepped — and the reseat takes the LIMIT plus a ring, not the pointer
    plus a ring, which at any other value would look the same."""
    _frame_case(post_load_image, "ring wrap",
                extra={A_SCREEN_RING_INDEX: (0).to_bytes(2, "big"),
                       A_SCREEN_RING + 4: (abi.SCREEN_RING_BASE + 0x500).to_bytes(4, "big")})


# Tile rows that can start above screen row 199: `scroll_fine - 32 + 32k < 199` gives 8 of them at
# phase 0 and 7 at every other. NOT `TILE_BAND_ROWS`, which is a different 8 — the scanlines one
# frame of scroll exposes.
TILE_REPAIR_ROWS_ON_SCREEN = 8


@pytest.mark.parametrize("scroll_fine", (0, 2, 7, 8, 9, 10, 30))
def test_render_frame_repaints_a_full_grid(post_load_image, scroll_fine):
    """The repaint's own clip arms, which no other case reaches.

    `repaint_overlay_tiles` does work only where the grid holds a NON-ZERO tile id, and pass A only
    marks the cells a sprite lands on — so a frame with a sprite or two drains three or four words
    out of 160 and never gets near the top or bottom row. This case fills the whole grid with real
    tile ids and sweeps the scroll phase, which is what walks the top-clipped first row (its source
    starts `32 - phase` rows into the tile), the full rows, and the bottom-clipped last one at both
    of the two row counts the phase selects between.
    """
    grid_words = TILE_REPAIR_ROWS_ON_SCREEN * TILE_REPAIR_COLUMNS
    grid = b"".join((0x40 + (i % 0x30)).to_bytes(2, "big") for i in range(grid_words))
    _frame_case(post_load_image, f"full grid at phase {scroll_fine}",
                extra={A_TILE_REPAIR_GRID: grid,
                       A_SCROLL_FINE: scroll_fine.to_bytes(2, "big")})


# ---- the width class the four-entry blitter tables have no entry for ---------------------------
#
# The three tables the dispatch can pick are back to back in DATA (0x16396 / 0x163a6 / 0x163b6, four
# longwords each, then `A_restore_blit_tbl` @ 0x163c6), and the index is `class * 4` with no bound —
# so a class of 4 reaches the FIRST ENTRY OF THE NEXT TABLE. All 256 shipped records hold 0..3.
OVERFLOW_WIDTH_CLASS = 4
# Three x positions, one per table the dispatch can pick: on screen (plain -> clip-left w16), off the
# left edge (clip-left -> clip-right w16), and past the right-clip threshold on a pass-B sprite
# (clip-right -> `restore_blit_w32`, which is not a blitter at all).
OVERFLOW_CLASS_POSITIONS = (0x50, -8, 0x118)


@pytest.mark.parametrize("x", OVERFLOW_CLASS_POSITIONS)
def test_render_frame_draws_a_sprite_whose_width_class_the_tables_have_no_entry_for(post_load_image,
                                                                                    x):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    `lsl.w #2,d2 / adda.w d2,a2 / movea.l (a2),a2 / jsr (a2)` @ 0x145ae indexes the chosen table by
    the width class and bounds nothing. A class of 4 therefore lands on the next table's first
    entry, and which wrong routine that is depends on which table the sprite's x picked — the third
    position reaches `restore_blit_w32`, an unmasked copy loop, through the masked blitters' door.

    A reconstruction that indexed a four-element host array here would be undefined behaviour rather
    than wrong output, and neither the byte diff nor `make guarded` would see it: `make guarded`
    bounds the IMAGE, not the candidate's own rodata. Only a poked bank record separates them.
    """
    record = SAMPLE_RECORD[0]
    klass_at = A_SPRITE_BANK + record * SPRITE_RECORD_BYTES + SPRITE_REC_WIDTH_CLASS
    _frame_case(post_load_image, f"class {OVERFLOW_WIDTH_CLASS} at x={x:#x}",
                records=[(20, x, 0x60, record, DISPLAY_ACTIVE_ON_TOP)],
                extra={klass_at: OVERFLOW_WIDTH_CLASS.to_bytes(2, "big")})


# The scroll phase the game itself can never hold. `advance_scroll` keeps `A_scroll_fine` in 0..31,
# and 0xffff is the shortest spelling of a phase whose WORD IS NEGATIVE.
SCROLL_FINE_NEGATIVE = 0xffff


def test_render_frame_repaints_at_a_NEGATIVE_scroll_phase(post_load_image):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    The repaint's bottom clip picks between two row counts with `cmpi.w #$8,$16430 / blt` @ 0x14626,
    and `blt` is SIGNED — so a phase whose word is negative takes the SMALL count (7 rows minus the
    phase) where an unsigned reading would take the large one (0x27). Every phase the game can hold
    is 0..31, where the two readings agree, which is why this separation needs a poked phase.

    At 0xffff the last tile row starts at y = 191 and the signed reading paints 9 rows to the bottom
    of the screen exactly; the unsigned one would paint 41 and run off it.
    """
    grid_words = TILE_REPAIR_ROWS_ON_SCREEN * TILE_REPAIR_COLUMNS
    grid = b"".join((0x40 + (i % 0x30)).to_bytes(2, "big") for i in range(grid_words))
    _frame_case(post_load_image, f"full grid at the negative phase {SCROLL_FINE_NEGATIVE:#x}",
                extra={A_TILE_REPAIR_GRID: grid,
                       A_SCROLL_FINE: SCROLL_FINE_NEGATIVE.to_bytes(2, "big")})


def test_render_frame_reseats_a_screen_base_below_the_ring(post_load_image):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    The reseat takes `ring_base + 0x1f900`, not `base + 0x1f900`. Every base the game can hold is
    `ring_base + k * 0x500` and the step subtracts exactly one, so the pointer lands ON ring_base and
    never below it — where the two formulas give the same answer, which is why the mutation survives
    every other case. Poking a base off that grid is the only way to separate them, and it is a
    machine state the game's own arithmetic cannot produce.
    """
    off_grid = abi.SCREEN_RING_BASE + SCREEN_STEP_BYTES - 0x200
    _frame_case(post_load_image, "reseat from below the ring",
                extra={A_SCREEN_RING_INDEX: (0).to_bytes(2, "big"),
                       A_SCREEN_RING + 4: off_grid.to_bytes(4, "big")})


def test_render_frame_replays_a_restore_list(post_load_image):
    """Records planted in the list this frame will REPLAY (two ring slots back), one per restore
    width including index 4, so the replay's dispatch and its `+0x280` source skew are exercised
    without waiting three frames for render_frame to have written them itself.

    OVER A RANDOMISED RING, and that is load-bearing: the prescroll leaves neighbouring screen rows
    holding near-identical terrain, so a source skew of 0x180 instead of 0x280 and a dispatch table
    with two entries swapped BOTH copy the wrong bytes and land the same values. Measured — both
    mutations survive this case against the prescrolled ring and die against a random one."""
    # The replay runs AFTER the scroll step has advanced the index, so a frame ENTERED at
    # index 0 replays list (0 + 1 - 2) & 3. Getting this wrong plants records in a list
    # nothing reads, and the case then passes over a replay that did nothing.
    list_index = (0 + 1 - RESTORE_LIST_LOOKBACK) & (SCREEN_RING_SLOTS - 1)
    records = b"".join(restore_record(*row) for row in ((0x100, 0, 7), (0x400, 1, 3),
                                                        (0x800, 2, 15), (0xc00, 3, 1),
                                                        (0x1000, RESTORE_CLASS_W16, 31)))
    ring_lo, ring_hi = STAGED_RING
    _frame_case(post_load_image, "restore replay",
                extra={A_SCREEN_RING_INDEX: (0).to_bytes(2, "big"),
                       ring_lo: seeded(0x14912, ring_hi - ring_lo),
                       A_SPRITE_RESTORE_LISTS + list_index * SPRITE_RESTORE_LIST_BYTES:
                           records + RESTORE_LIST_TAIL})


def test_render_frame_restore_record(post_load_image):
    """Two sprites in pass A and one in pass B: the three restore records this frame APPENDS, in
    order, with the terminator past the last. The list is part of the image, so the record layout in
    include/display_list.h is pinned by this case rather than asserted here."""
    _frame_case(post_load_image, "restore records",
                records=[(17, 0x50, 0x40, SAMPLE_RECORD[1], DISPLAY_ACTIVE_UNDER_SCENERY),
                         (30, -8, 0x20, SAMPLE_RECORD[0], DISPLAY_ACTIVE_UNDER_SCENERY),
                         PASS_B_SPRITE])


@pytest.mark.parametrize("active", (0x00, 0x01, 0x7f, 0x80, 0xff))
def test_render_frame_passes_are_selected_by_the_active_byte(post_load_image, active):
    """Every boundary of the two `tst.b`: 0 is in neither pass, 1..0x7f is pass B, 0x80..0xff is
    pass A. 0x7f/0x80 is the pair a `bmi` written as a `> 0x80` test would get wrong."""
    _frame_case(post_load_image, f"active={active:#x}",
                records=[(21, 0x70, 0x50, SAMPLE_RECORD[0], active)])


def test_render_frame_over_a_randomised_ring(post_load_image):
    """A whole frame over four screens of pseudo-random pixels instead of the prescroll's terrain.

    THIS IS THE ATTRIBUTION CASE, and it is this shape because `poison=True` cannot be used on
    render_frame at all: the poison pass inverts every byte the oracle WROTE, and among those are
    `vbl_tick` (always written as 0, so poisoned to -1, which sends both cores into the VBL wait
    nothing can end) and the four screen pointers and the scroll phase — outputs that steer the next
    run rather than merely record it, which `harness.differential`'s own docstring names as the
    limit of the pass. What a randomised ring buys instead is that the terrain the prescroll leaves
    is full of colour-0 zeroes, so a masked write that never happened can match by coincidence; over
    random background it cannot. Every leaf this routine calls IS poisoned, in its own case above.
    """
    ring_lo, ring_hi = STAGED_RING
    _frame_case(post_load_image, "randomised ring",
                records=[PASS_A_SPRITE, PASS_B_SPRITE],
                extra={ring_lo: seeded(ENTRY_RENDER_FRAME, ring_hi - ring_lo)})


FRAME_FUZZ_CHUNKS = 4
FRAME_FUZZ_CASES = 24
FRAME_FUZZ_SPRITES = 5
# The 12 records with rows - 1 == -1 carry a hit box and NO bitmap; the game never publishes one, and
# a blit with that count would `dbf` 65,536 rows straight off the image. Only ids with a bitmap are
# fuzzed, and ../STATUS.md records the arm as unreachable by the game's own data.
FRAME_FUZZ_BITMAP_IDS = tuple(i for i in range(230) if i not in
                              (38, 39, 40, 42, 43, 44, 45, 46, 48, 49, 141, 152))


def frame_fuzz_cases():
    rng = random.Random(ENTRY_RENDER_FRAME)
    for i in range(FRAME_FUZZ_CASES):
        yield (i,
               [(rng.randrange(60), rng.randrange(-0x40, 0x150), rng.randrange(-0x40, 0xd0),
                 FRAME_FUZZ_BITMAP_IDS[rng.randrange(len(FRAME_FUZZ_BITMAP_IDS))],
                 rng.choice((DISPLAY_ACTIVE_UNDER_SCENERY, DISPLAY_ACTIVE_ON_TOP)))
                for _ in range(FRAME_FUZZ_SPRITES)],
               rng.randrange(0, 32, 2),
               rng.randrange(SCREEN_RING_SLOTS))


@pytest.mark.parametrize("chunk", range(FRAME_FUZZ_CHUNKS))
def test_render_frame_fuzz(post_load_image, chunk):
    """Whole frames with five random sprites from the real bank at random positions, a random scroll
    phase and a random ring index — so the passes, both clip ladders, the repair grid, the repaint
    and the restore list all run against each other rather than one at a time."""
    for i, records, scroll_fine, index in frame_fuzz_cases():
        if i % FRAME_FUZZ_CHUNKS != chunk:
            continue
        _frame_case(post_load_image, f"frame fuzz case {i}", records=records,
                    extra={A_SCROLL_FINE: scroll_fine.to_bytes(2, "big"),
                           A_SCREEN_RING_INDEX: index.to_bytes(2, "big")})


# =============================================================== pins on the data this file reads

def test_the_sample_sprite_records_are_the_classes_they_are_used_as(post_load_image):
    """SAMPLE_RECORD picks one bitmap record per width class out of the relocated directory. A bank
    that moved, or a record renumbered, would otherwise blit a different shape and still be green
    against an oracle doing the same thing."""
    for width_class, record_id in enumerate(SAMPLE_RECORD):
        data, klass, rows = sprite_record(post_load_image, record_id)
        assert klass == width_class, f"record {record_id} is class {klass}, not {width_class}"
        assert rows >= 0, f"record {record_id} carries no bitmap"
        assert A_SPRITE_BANK <= data < A_TILE_BANKS


# The draw offsets each sample carries, read off the bank and stated here so that a bank whose
# offsets moved fails BY NAME rather than by shifting every sweep's coordinates under it. Every
# sweep bar `test_render_frame_applies_the_records_own_draw_offset` needs a ZERO offset, so that the
# x or y a case names is the coordinate the clip ladders actually see.
SAMPLE_RECORD_DRAW_OFFSETS = ((0, 0), (0x10, 9), (0, 0), (0, 0))


def test_the_sample_records_draw_offsets_are_the_ones_the_sweeps_assume(post_load_image):
    """The sweeps' coordinates are only the clip ladders' coordinates while the record's own draw
    offset is zero, and only ONE sample has an offset. Both halves are stated in the comment beside
    `SAMPLE_RECORD` and neither was checked: a bank in which record 68 grew an offset would move the
    pass-B threshold sweep off 0xf0/0xf1 and it would still pass, because the oracle would move with
    it. This is what makes those cases mean what their docstrings say."""
    for record_id, expected in zip(SAMPLE_RECORD, SAMPLE_RECORD_DRAW_OFFSETS):
        base = A_SPRITE_BANK + record_id * SPRITE_RECORD_BYTES

        def word(offset, base=base):
            return int.from_bytes(post_load_image[base + offset:base + offset + 2], "big",
                                  signed=True)

        offset = (word(SPRITE_REC_DRAW_DX), word(SPRITE_REC_DRAW_DY))
        assert offset == expected, f"record {record_id}'s draw offset is {offset}, not {expected}"


def test_no_record_in_the_bank_has_a_width_class_the_blitter_tables_cover_only_by_accident(
        post_load_image):
    """EVERY one of the 256 records is class 0..3, which is what `src/sprite.c`'s dispatch cites.

    That file models what a class of 4 reaches — the next jump table's first entry, because the
    three tables are back to back in DATA — and says so rather than asserting the class away. The
    reason it can call that unreachable is this scan, over the bank the game itself loads. A record
    that grew a wider class would fail here, where the sentence lives, rather than by quietly
    blitting through the wrong table in a frame case nobody would read as a bank change.
    """
    wider = [record_id for record_id in range(SPRITE_RECORDS)
             if not 0 <= sprite_record(post_load_image, record_id)[1] < SPRITE_WIDTH_CLASSES]
    assert not wider, (
        f"{len(wider)} of A\\SPRITES.cru's records carry a width class outside "
        f"0..{SPRITE_WIDTH_CLASSES - 1}: {wider[:8]}")


def test_the_bitmapless_records_are_exactly_the_ones_the_fuzz_excludes(post_load_image):
    """FRAME_FUZZ_BITMAP_IDS is a LIST OF IDS, and the bank is where the fact lives. This re-derives
    it: a record with rows - 1 == -1 has no bitmap at all (it shares the previous record's data
    pointer and occupies zero bytes, existing only to give `sprite_hit_test` a box), and blitting one
    would `dbf` 65,536 rows straight off the image. If the bank ever changes, the fuzz's exclusion
    list fails here rather than by walking the candidate off its buffer."""
    bitmapless = tuple(record_id for record_id in range(SPRITE_RECORDS)
                       if sprite_record(post_load_image, record_id)[2] < 0)
    excluded = tuple(record_id for record_id in range(SPRITE_RECORDS)
                     if record_id not in FRAME_FUZZ_BITMAP_IDS and record_id < 230)
    assert bitmapless == excluded, f"the bank's bitmapless records are {bitmapless}"


# `move.l $17720.l,d1` — the instruction the VBL wait re-reads the counter at, which is what both
# shores key their clocks to. Not an `ENTRY_*` (it is a PC inside a routine, not a call target), so
# `check_entry_prologues` does not demand a row for it; this is that row.
WAIT_PC_VBL_BUDGET_PROLOGUE = "2239" "00017720"


def test_the_vbl_wait_site_is_the_instruction_that_re_reads_the_counter():
    """A wait site one instruction off would count arrivals the original does not make, and the
    candidate's poll count would disagree for a reason nothing else in the case names."""
    bytes_there = bytes(harness.BASE_IMAGE[WAIT_PC_VBL_BUDGET:WAIT_PC_VBL_BUDGET + 6])
    assert bytes_there == bytes.fromhex(WAIT_PC_VBL_BUDGET_PROLOGUE), (
        f"{WAIT_PC_VBL_BUDGET:#x} holds {bytes_there.hex()}, not the `move.l $17720.l,d1` the wait "
        f"re-reads the counter at")


def test_the_frozen_display_list_geometry_agrees_with_itself():
    """`include/display_list.h`'s three derived figures, re-derived. The header is a FROZEN block
    other subsystems publish through, so every line of it wants a reader — a claim nothing checks is
    the thing freezing a layout is meant to avoid."""
    assert (A_DISPLAY_LIST_END - A_DISPLAY_LIST) == DISPLAY_LIST_RECORDS * DISPLAY_REC_BYTES
    assert TILE_REPAIR_ROW_BYTES == TILE_REPAIR_COLUMNS * MAP_CELL_BYTES
    # The overlay id is the ODD byte of a cell and of a grid word alike, which is why one index
    # walks both: `move.b 1(a3,d0.w),1(a2,d0.w)`.
    assert TILE_REPAIR_ID_BYTE == MAP_CELL_OVERLAY


def test_the_blit_tables_name_the_routines_this_file_dispatches_to():
    """src/sprite.c dispatches on the width class directly instead of `jsr`ing through the tables.
    THIS is what makes that sound: all seventeen longwords, read out of the loaded image, are the
    entries this battery names — including `restore_blit_tbl`'s FIFTH, which is
    `restore_blit_w16` and which ../notes/gameplay.md says is unreachable."""
    def table(address, count):
        return [int.from_bytes(harness.BASE_IMAGE[address + i * BLIT_TABLE_ENTRY_BYTES:
                                                  address + (i + 1) * BLIT_TABLE_ENTRY_BYTES],
                               "big")
                for i in range(count)]

    assert table(A_SPRITE_BLIT_TBL, SPRITE_WIDTH_CLASSES) == list(ENTRY_BLIT)
    assert table(A_SPRITE_BLIT_CLIP_LEFT_TBL, SPRITE_WIDTH_CLASSES) == list(ENTRY_CLIP_LEFT)
    assert table(A_SPRITE_BLIT_CLIP_RIGHT_TBL, SPRITE_WIDTH_CLASSES) == list(ENTRY_CLIP_RIGHT)
    assert table(A_RESTORE_BLIT_TBL, RESTORE_BLIT_TABLE_ENTRIES) == list(ENTRY_RESTORE)


# The row-closing `lea N(a1),a1 / dbf d7,<entry>` of each unclipped blitter, as (address, N). The
# four routines share their first 192 bytes — a class-2 and a class-3 blitter differ only in how
# many groups they unroll — so ENTRY_PROLOGUES below cannot tell them apart at any sane length.
# The tail can: the `dbf`'s displacement names the entry, and the `lea` names the class's geometry.
BLIT_ROW_TAILS = {
    "ENTRY_SPRITE_BLIT_W16": (0x153fe, 146),
    "ENTRY_SPRITE_BLIT_W32": (0x1549a, 138),
    "ENTRY_SPRITE_BLIT_W48": (0x1557c, 130),
    "ENTRY_SPRITE_BLIT_W64": (0x156a4, 122),
}
LEA_DISPLACEMENT_A1 = 0x43e9      # `lea d16(a1),a1`
DBF_D7 = 0x51cf                   # `dbf d7,<pc-relative>`


def test_each_unclipped_blitter_loops_back_to_the_entry_this_battery_names():
    """What ENTRY_PROLOGUES cannot check for these four, checked here instead."""
    def word(address):
        return int.from_bytes(harness.BASE_IMAGE[address:address + 2], "big")

    for name, (lea, remainder) in BLIT_ROW_TAILS.items():
        entry = globals()[name]
        assert word(lea) == LEA_DISPLACEMENT_A1 and word(lea + 2) == remainder, (
            f"{name}: {lea:#x} is not `lea {remainder}(a1),a1`")
        dbf = lea + 4
        displacement = int.from_bytes(harness.BASE_IMAGE[dbf + 2:dbf + 4], "big", signed=True)
        assert word(dbf) == DBF_D7 and dbf + 2 + displacement == entry, (
            f"{name}: the `dbf` at {dbf:#x} does not branch back to {entry:#x}")


def test_the_tile_split_row_table_pairs_sum_to_the_band(post_load_image):
    """Every pair `draw_exposed_tile_band` can index sums to the 8 rows the scroll exposes. The
    band's screen step (`lea -1264`) assumes it, and a pair that did not would shear the column."""
    for phase in range(0, 32, 2):
        lower = post_load_image[A_TILE_SPLIT_ROW_TABLE + phase]
        upper = post_load_image[A_TILE_SPLIT_ROW_TABLE + phase + 1]
        assert lower + upper == TILE_BAND_ROWS, f"phase {phase}: {lower} + {upper}"


def test_the_prescroll_staging_is_the_originals_own_work(post_load_image):
    """The staged image is `title_attract_loop`'s own prescroll under the oracle, and the cases poke
    it back over the post-load base in TWO bands. This is what says those two bands are all it
    changed: anything else it wrote would be state the cases run on and nobody declared.

    The oracle's own stack is the one exception, and it is excluded by address rather than by
    tolerance — it is the harness's memory, not the program's.
    """
    staged = _prescrolled(bytes(post_load_image))
    declared = STAGED_GLOBALS, STAGED_RING
    # SPLICE, THEN ONE COMPARE. The green path is what this costs on every run, and a byte-at-a-time
    # scan of a megabyte to find nothing is the wrong shape for it: copy the post-load image, splice
    # the declared bands out of it, and let one `==` answer. The scan below runs only to NAME the
    # first stray, i.e. on the path that is about to fail anyway.
    below_the_stack = emu.STACK_GUARD_LO
    expected = bytearray(post_load_image[:below_the_stack])
    for lo, hi in declared:
        expected[lo:hi] = staged[lo:hi]
    if staged[:below_the_stack] != bytes(expected):
        stray = [addr for addr in range(below_the_stack) if staged[addr] != expected[addr]]
        raise AssertionError(
            f"the prescroll changed {len(stray)} bytes outside the declared bands, first at "
            f"{stray[0]:#x} — a case that pokes only the bands would run on a machine the staging "
            f"did not reproduce")


def test_the_prescroll_really_scrolled(post_load_image):
    """...and that it did something: the map cursor walked, the phase moved off zero and the ring
    holds terrain. Without this the band pin above would pass over a staging that ran nothing."""
    staged = _prescrolled(bytes(post_load_image))
    assert int.from_bytes(staged[A_MAP_ROW_PTR:A_MAP_ROW_PTR + 4], "big") \
        < int.from_bytes(staged[A_MAP_ROW_PTR_RESET:A_MAP_ROW_PTR_RESET + 4], "big")
    assert int.from_bytes(staged[A_SCROLL_FINE:A_SCROLL_FINE + 2], "big") != 0
    assert any(staged[abi.SCREEN_RING_BASE:abi.SCREEN_RING_BASE + SCREEN_RING_BYTES])


# --- test_constants.py collects these; see ../README.md, "Adding a function" ---
MIRROR_HEADER = "include/sprite.h"
MIRRORS = (
    ("A_BLIT_CLIP_MASK", "include/sprite.h", "A_blit_clip_mask"),
    ("A_SPRITE_BLIT_TBL", "include/sprite.h", "A_sprite_blit_tbl"),
    ("A_SPRITE_BLIT_CLIP_LEFT_TBL", "include/sprite.h", "A_sprite_blit_clip_left_tbl"),
    ("A_SPRITE_BLIT_CLIP_RIGHT_TBL", "include/sprite.h", "A_sprite_blit_clip_right_tbl"),
    ("A_RESTORE_BLIT_TBL", "include/sprite.h", "A_restore_blit_tbl"),
    ("A_TILE_SPLIT_ROW_TABLE", "include/sprite.h", "A_tile_split_row_table"),
    ("A_MAP_ROW_PTR", "include/sprite.h", "A_map_row_ptr"),
    ("A_MAP_ROW_PTR_RESET", "include/sprite.h", "A_map_row_ptr_reset"),
    ("A_SCREEN_RING_INDEX", "include/sprite.h", "A_screen_ring_index"),
    ("A_SCROLL_FINE", "include/sprite.h", "A_scroll_fine"),
    ("A_PRESCROLL_FLAG", "include/sprite.h", "A_prescroll_flag"),
    ("A_VBL_TICK", "include/sprite.h", "A_vbl_tick"),
    "BLIT_TABLE_ENTRY_BYTES", "RESTORE_BLIT_TABLE_ENTRIES", "RESTORE_CLASS_W16",
    "SPRITE_WIDTH_CLASSES", "SPRITE_GROUP_BYTES", "SPRITE_PLANES",
    "SCREEN_ROW_BYTES", "SCREEN_GROUP_BYTES", "SCREEN_ROWS", "SCREEN_LAST_ROW",
    "SCROLL_WRAP_COPY_LONGS", "TILE_BYTES", "TILE_ROW_BYTES", "TILE_PIXELS", "TILE_BAND_ROWS",
    "MAP_COLUMNS", "MAP_CELL_BYTES", "MAP_CELL_OVERLAY", "RENDER_FRAME_VBL_BUDGET",
    ("RESTORE_LIST_LOOKBACK", "src/sprite.c", "RESTORE_LIST_LOOKBACK"),
    ("SCREEN_STEP_BYTES", "src/sprite.c", "SCREEN_STEP_BYTES"),
    ("SCREEN_RING_SLOTS", "include/globals.h", "SCREEN_RING_SLOTS"),
    "SPRITE_REC_DATA", "SPRITE_REC_WIDTH_CLASS", "SPRITE_REC_ROWS",
    "SPRITE_REC_DRAW_DX", "SPRITE_REC_DRAW_DY",
    ("A_DISPLAY_LIST", "include/display_list.h", "A_display_list"),
    ("A_DISPLAY_LIST_END", "include/display_list.h", "A_display_list_end"),
    ("DISPLAY_REC_BYTES", "include/display_list.h", "DISPLAY_REC_BYTES"),
    ("DISPLAY_REC_X", "include/display_list.h", "DISPLAY_REC_X"),
    ("DISPLAY_REC_Y", "include/display_list.h", "DISPLAY_REC_Y"),
    ("DISPLAY_REC_FRAME", "include/display_list.h", "DISPLAY_REC_FRAME"),
    ("DISPLAY_REC_ACTIVE", "include/display_list.h", "DISPLAY_REC_ACTIVE"),
    ("DISPLAY_ACTIVE_HIDDEN", "include/display_list.h", "DISPLAY_ACTIVE_HIDDEN"),
    ("DISPLAY_ACTIVE_UNDER_SCENERY", "include/display_list.h", "DISPLAY_ACTIVE_UNDER_SCENERY"),
    ("DISPLAY_ACTIVE_ON_TOP", "include/display_list.h", "DISPLAY_ACTIVE_ON_TOP"),
    ("DISPLAY_ACTIVE_ON_TOP_MAX", "include/display_list.h", "DISPLAY_ACTIVE_ON_TOP_MAX"),
    ("A_TILE_REPAIR_GRID", "include/display_list.h", "A_tile_repair_grid"),
    ("TILE_REPAIR_COLUMNS", "include/display_list.h", "TILE_REPAIR_COLUMNS"),
    ("TILE_REPAIR_ROW_BYTES", "include/display_list.h", "TILE_REPAIR_ROW_BYTES"),
    ("TILE_REPAIR_ID_BYTE", "include/display_list.h", "TILE_REPAIR_ID_BYTE"),
    ("DISPLAY_LIST_RECORDS", "include/display_list.h", "DISPLAY_LIST_RECORDS"),
    ("MAP_ROW_BYTES", "include/sprite.h", "MAP_ROW_BYTES"),
    ("WAIT_PC_VBL_BUDGET", "src/sprite.c", "RENDER_FRAME_VBL_WAIT_PC"),
    ("SPRITE_RESTORE_REC_BYTES", "include/display_list.h", "SPRITE_RESTORE_REC_BYTES"),
    ("SPRITE_RESTORE_OFFSET", "include/display_list.h", "SPRITE_RESTORE_OFFSET"),
    ("SPRITE_RESTORE_CLASS", "include/display_list.h", "SPRITE_RESTORE_CLASS"),
    ("SPRITE_RESTORE_ROWS", "include/display_list.h", "SPRITE_RESTORE_ROWS"),
    ("A_SPRITE_BANK", "include/globals.h", "A_sprite_bank"),
    ("SPRITE_RECORDS", "include/globals.h", "SPRITE_RECORDS"),
    ("SPRITE_RECORD_BYTES", "include/globals.h", "SPRITE_RECORD_BYTES"),
    ("A_SPRITE_RESTORE_LISTS", "include/globals.h", "A_sprite_restore_lists"),
    ("SPRITE_RESTORE_LIST_BYTES", "include/globals.h", "SPRITE_RESTORE_LIST_BYTES"),
    ("SPRITE_RESTORE_TERMINATOR", "include/globals.h", "SPRITE_RESTORE_TERMINATOR"),
    ("A_SCREEN_DRAW", "include/globals.h", "A_screen_draw"),
    ("A_SCREEN_PREV1", "include/globals.h", "A_screen_prev1"),
    ("A_SCREEN_PREV2", "include/globals.h", "A_screen_prev2"),
    ("A_SCREEN_RING", "include/globals.h", "A_screen_ring"),
    ("A_SCREEN_RING_BASE", "include/globals.h", "A_screen_ring_base"),
    ("SCREEN_RING_BYTES", "include/globals.h", "SCREEN_RING_BYTES"),
    ("SCREEN_BYTES", "include/globals.h", "SCREEN_BYTES"),
    ("A_TILE_BANKS", "include/globals.h", "A_tile_banks"),
    ("A_LEVEL_MAP_COLS", "include/globals.h", "A_level_map_cols"),
)

# TWELVE BYTES for the restore family and TWENTY-FOUR for the widest of them: the five routines and
# `scroll_wrap_copy_1280` are runs of the identical `move.l (a0)+,(a1)+` and separate only at the
# `lea` that closes the row, so a ten-byte pin would let any of them stand for another. The four
# unclipped blitters cannot be separated by a prologue at all — see BLIT_ROW_TAILS above.
ENTRY_PROLOGUES = {
    "ENTRY_RENDER_FRAME": "20790001641622790001",
    "ENTRY_TITLE_PRESCROLL": "33f9000176ac00017758",
    "ENTRY_TILE_BLIT_OVERLAY_MASKED": "4c9d00273c008c418c42",
    "ENTRY_RESTORE_BLIT_W16": "22d822d841e8009843e9",
    "ENTRY_RESTORE_BLIT_W32": "22d822d822d822d841e80090",
    "ENTRY_RESTORE_BLIT_W48": "22d822d822d822d822d822d841e80088",
    "ENTRY_RESTORE_BLIT_W64": "22d822d822d822d822d822d822d822d841e80080",
    "ENTRY_RESTORE_BLIT_W80": "22d822d822d822d822d822d822d822d822d822d841e80078",
    "ENTRY_SCROLL_WRAP_COPY_1280": "22d822d822d822d822d822d822d822d822d822d822d822d8",
    "ENTRY_SPRITE_BLIT_W16_CLIP_LEFT": "b87cfff06d0c13fc0001",
    "ENTRY_SPRITE_BLIT_W32_CLIP_LEFT": "b87cfff06d0c13fc0003",
    "ENTRY_SPRITE_BLIT_W48_CLIP_LEFT": "b87cfff06d0c13fc0007",
    "ENTRY_SPRITE_BLIT_W64_CLIP_LEFT": "b87cfff06d0c13fc000f",
    "ENTRY_SPRITE_BLIT_W16_CLIP_RIGHT": "b87c01306c0c13fc0003",
    "ENTRY_SPRITE_BLIT_W32_CLIP_RIGHT": "b87c01206c0c13fc0007",
    "ENTRY_SPRITE_BLIT_W48_CLIP_RIGHT": "b87c01106c0c13fc000f",
    "ENTRY_SPRITE_BLIT_W64_CLIP_RIGHT": "b87c01006c0c13fc001f",
    "ENTRY_SPRITE_BLIT_W16": "223cffffffff428242834284428532183418361838183a18",
    "ENTRY_SPRITE_BLIT_W32": "223cffffffff428242834284428532183418361838183a18",
    "ENTRY_SPRITE_BLIT_W48": "223cffffffff428242834284428532183418361838183a18",
    "ENTRY_SPRITE_BLIT_W64": "223cffffffff428242834284428532183418361838183a18",
}
STOP_PROLOGUES = {
    "STOP_TITLE_PRESCROLL": "42390001642c303c",
}
