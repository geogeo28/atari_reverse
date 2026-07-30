"""Differential tests for Joust's object / physics / collision layer (src/object.c).

Covered here, leaves first: pixel_collision @ 0x13fe6, test_overlap @ 0x13ef2,
joust_bounce @ 0x140fe, check_platform @ 0x13300, erase_egg_sprite @ 0x129b4,
draw_egg_sprite @ 0x12914, ptero_avoid_platform @ 0x15226, ptero_spot_player @ 0x15276 and
count_objects_and_pad @ 0x1033e.
"""
import ctypes
import random
import struct

import pytest

import abi
import emu
import harness
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin test at the end

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_COUNT_OBJECTS = 0x1033e
ENTRY_DRAW_EGG_SPRITE = 0x12914
ENTRY_ERASE_EGG_SPRITE = 0x129b4
ENTRY_CHECK_PLATFORM = 0x13300
ENTRY_TEST_OVERLAP = 0x13ef2
ENTRY_PIXEL_COLLISION = 0x13fe6
ENTRY_JOUST_BOUNCE = 0x140fe
ENTRY_PTERO_AVOID_PLATFORM = 0x15226
ENTRY_PTERO_SPOT_PLAYER = 0x15276

# ---- globals (mirror of include/object.h, which mirrors ../../names.txt) ----
A_PLATFORM_PRESENT = 0x10cfa
A_GAME_PHASE = 0x10d08
A_LIVE_OBJECT_COUNT = 0x10d0a
A_EGG_COUNT = 0x10d0b
A_MESSAGE_CHAR_COUNT = 0x10d0c
A_PTERO_SPAWN_COUNT = 0x10d0d
A_SND_PRIORITY = 0x10d4c    # the sound layer's (include/sound.h): ptero_spot_player stages it,
                            # because play_sound reads and writes it on its behalf
A_PLAYFIELD_BOTTOM = 0x10d60
A_HIT_BOX_A = 0x10da0
A_HIT_BOX_B = 0x10db0
A_HIT_ROWS = 0x10dc0
A_COLLISION_HIT = 0x10dc1
A_DRAW_DST = 0x10de8
A_DRAW_X = 0x10dec
A_DRAW_SRC = 0x10df0
A_DRAW_SHIFT = 0x10df4
A_DRAW_ROWS = 0x10df6
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36
A_PTERODACTYL_TABLE = 0x113ba
A_PLATFORM_TABLE = 0x117b4
A_PLATFORM_SPRITES = 0x119d4

# ---- record geometry ----
OBJ_SIZE, N_OBJECTS = 0x4e, 14
MSG_RECORD, N_MESSAGES = 0xc, 24
PSPR_RECORD, N_PLATFORMS = 0x10, 8
PLAT_RECORD = 8
PTERO_SIZE = 0x20
CELL_BYTES = 8
SCREEN_ROW_BYTES = 0xa0
CELLS_PER_ROW = SCREEN_ROW_BYTES // CELL_BYTES     # 20 — test_overlap's `sub.w #$14`
CELL_PLANE_WORDS = 4                               # plane words per cell — every `moveq #$4` blit

# ---- scratch areas, all clear of the program (ends 0x2b7ae), abi.STUB/RESULT (0x40000..0x40207),
# the staged-file table (0xbf000) and the stack guard. Unpoked bytes read back as zero, which for a
# sprite means "no pixels", so a read that runs past a poked block is harmless but still in-image.
SPRITE_A = 0x50000
SPRITE_B = 0x60000
SCREEN = 0x70000
STRINGS = 0x80000

UNWRITTEN_W = 0x5a5a         # pre-filled into output slots so a missing write shows as a diff
JUNK_RESULT = 0xa5a5a5a5     # pre-filled into abi.RESULT for the register-result stubs

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs in (("g_pixel_collision", 2), ("g_test_overlap", 0), ("g_joust_bounce", 4),
                      ("g_check_platform", 3), ("g_erase_egg_sprite", 1), ("g_draw_egg_sprite", 1),
                      ("g_ptero_avoid_platform", 3), ("g_ptero_spot_player", 3),
                      ("g_count_objects_and_pad", 0)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = None


# ------------------------------------------------------------------ shared staging helpers

def _result_stub(routine, reg):
    """Pokes for `jsr routine ; move.l Dn,(abi.RESULT).l ; rts`.

    check_platform returns its flags in D0 and ptero_avoid_platform its step in D1; an image diff
    cannot see either, so the oracle is entered through this stub and the candidate's glue writes
    the same longword to the same address (the convention test/abi.py documents).
    """
    store = {0: b"\x23\xc0", 1: b"\x23\xc1"}[reg]        # move.l d0/d1,(xxx).L
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")
            + store + abi.RESULT.to_bytes(4, "big")
            + b"\x4e\x75")
    return {abi.STUB: code, abi.RESULT: JUNK_RESULT.to_bytes(4, "big")}


def _box(dst, src, cols, shift, rows, cur_col=UNWRITTEN_W, y=0):
    """One 0x10-byte collision box, as staged in hit_box_a / hit_box_b."""
    return struct.pack(">IIHBBHH", dst, src, cols, shift, rows, cur_col, y)


# Which of a cell's 16 pixel columns each plane word carries, interleaved so no plane is empty and
# no plane holds the whole mask. Putting the mask in plane 0 alone would let a candidate that ORed
# only the first plane reproduce every case exactly.
_PLANE_BIT_MASKS = tuple(sum(1 << bit for bit in range(16) if bit % CELL_PLANE_WORDS == plane)
                         for plane in range(CELL_PLANE_WORDS))


def _sprite(masks):
    """Sprite bytes from a [row][col] table of 16-bit occupancy masks.

    Each cell is four plane words, and the mask is SPLIT across them by bit position, so the
    routines' OR of the four planes reproduces the mask exactly while every plane carries part of
    it. Rows are contiguous, which is the stride both routines step by (cols * 8).
    """
    out = bytearray()
    for row in masks:
        for cell in row:
            out += struct.pack(">HHHH", *(cell & plane for plane in _PLANE_BIT_MASKS))
    return bytes(out)


def _object(**fields):
    """A 0x4e-byte object record; every field not named is zero."""
    rec = bytearray(OBJ_SIZE)
    layout = {"flags": (0x00, "H"), "x": (0x02, "H"), "y": (0x04, "H"), "vx": (0x06, "H"),
              "vy": (0x08, "H"), "anim_timer": (0x0a, "B"), "step_timer": (0x0b, "B"),
              "flap_frame": (0x0e, "H"), "prev_dst": (0x14, "I"), "egg_state": (0x1e, "B"),
              "egg_x": (0x20, "H"), "egg_y": (0x22, "H"), "egg_dst": (0x2a, "I"),
              "egg_src": (0x2e, "I"), "egg_rows": (0x32, "B"), "egg_shift": (0x33, "B")}
    for name, value in fields.items():
        off, fmt = layout[name]
        struct.pack_into(">" + fmt, rec, off, value)
    return bytes(rec)


# ------------------------------------------------------------------ pixel_collision @ 0x13fe6

def _pixel_case(box_a, box_b, hit_rows, sprite_a, sprite_b, swap=False, poison=False):
    """Run pixel_collision with A1/A2 pointing at the two staged boxes.

    `swap` stages the two boxes in the opposite globals — hit_box_b holds box_a's bytes — and passes
    the pointers to match. The routine sees the same inputs at different addresses, which is what
    catches a candidate that reached for hit_box_a/hit_box_b directly instead of its arguments;
    test_overlap really does call it either way round, via `exg a1,a2`.
    """
    addr_a, addr_b = (A_HIT_BOX_B, A_HIT_BOX_A) if swap else (A_HIT_BOX_A, A_HIT_BOX_B)
    pokes = {addr_a: box_a, addr_b: box_b,
             A_HIT_ROWS: bytes([hit_rows]), A_COLLISION_HIT: b"\x00",
             SPRITE_A: sprite_a, SPRITE_B: sprite_b}
    diffs, _ = differential(ENTRY_PIXEL_COLLISION,
                            {"a1": addr_a, "a2": addr_b, "_pokes": pokes},
                            lambda lib, buf: lib.g_pixel_collision(buf, addr_a, addr_b),
                            poison=poison)
    assert not diffs, f"hit_rows={hit_rows} swap={swap}\n{report(diffs)}"


# A two-column sprite whose second cell is the one under test, so the "previous cell" the spill
# path reads (-8(a3)) is a real, distinct cell rather than whatever precedes the block.
_COLS = 2
_SECOND_CELL = CELL_BYTES


def _two_col_sprite(rows, first, second):
    return _sprite([[first[r], second[r]] for r in range(rows)])


def test_pixel_collision_hit_row():
    """A shared bit on each row in turn, plus the case where no row shares one."""
    rows = 4
    for hit_row in (None, 0, 1, 3):
        a = _two_col_sprite(rows, [0] * rows, [0x0001 if r == hit_row else 0x0002
                                               for r in range(rows)])
        b = _two_col_sprite(rows, [0] * rows, [0x0001] * rows)
        _pixel_case(_box(0, SPRITE_A + _SECOND_CELL, _COLS, 0, rows, cur_col=1),
                    _box(0, SPRITE_B + _SECOND_CELL, _COLS, 0, rows, cur_col=1),
                    rows, a, b, poison=True)


def test_pixel_collision_spill_from_previous_cell():
    """With a shift in play the previous cell's bits slide into this one — and only then.

    Sprite A has pixels ONLY in its first cell; shifted right by 4 they land in the top 4 bits of
    the cell under test. Sprite B has a bit there. So the hit exists only while both the shift and
    a non-zero column cursor let the spill happen.
    """
    rows = 2
    a = _two_col_sprite(rows, [0x000f] * rows, [0] * rows)
    b = _two_col_sprite(rows, [0] * rows, [0xf000] * rows)
    for shift, cur_col in ((4, 1), (4, 0), (0, 1), (0, 0)):
        _pixel_case(_box(0, SPRITE_A + _SECOND_CELL, _COLS, shift, rows, cur_col=cur_col),
                    _box(0, SPRITE_B + _SECOND_CELL, _COLS, 0, rows, cur_col=1),
                    rows, a, b, poison=True)


# LSR.L takes its count modulo 64 and a count of 32..63 shifts every bit out, so a shift byte far
# past a cell's 16 pixels is not merely "a big shift": 32 blanks the sprite and 64 is no shift at
# all. The shift field is a byte, so every one of these is expressible.
_WIDE_SHIFTS = (0, 1, 15, 16, 17, 31, 32, 33, 63, 64, 65, 0x80, 0xff)


@pytest.mark.parametrize("shift", _WIDE_SHIFTS)
def test_pixel_collision_wide_shifts(shift):
    rows = 3
    a = _two_col_sprite(rows, [0xffff] * rows, [0xffff] * rows)
    b = _two_col_sprite(rows, [0xffff] * rows, [0xffff] * rows)
    for swap in (False, True):
        _pixel_case(_box(0, SPRITE_A + _SECOND_CELL, _COLS, shift, rows, cur_col=1),
                    _box(0, SPRITE_B + _SECOND_CELL, _COLS, shift, rows, cur_col=1),
                    rows, a, b, swap=swap)


def test_pixel_collision_row_count_is_a_byte():
    """`subq.b #1,d1` counts the low byte only, so hit_rows = 0 means 256 rows, not none.

    Nothing shares a bit, so a 0 that meant "no rows" and a 0 that means 256 differ only in how far
    the source pointers walk — which is invisible unless a late row can hit. Row 200 of sprite A is
    therefore the only one that can, and it only fires on the 256-row reading.
    """
    rows = 256
    late = 200
    a = _sprite([[0x0001 if r == late else 0x0002] for r in range(rows)])
    b = _sprite([[0x0001] for _ in range(rows)])
    for hit_rows in (0, 1, 2, 199, 200, 201, 255):
        _pixel_case(_box(0, SPRITE_A, 1, 0, rows & 0xff),
                    _box(0, SPRITE_B, 1, 0, rows & 0xff),
                    hit_rows, a, b)


def test_pixel_collision_row_advance_sign_extends():
    """`adda.w` folds only the LOW WORD of cols*8 into the source pointer, sign-extended.

    cols = 0x1000 makes that word 0x8000, i.e. -0x8000: the sprite walks BACKWARDS up the image one
    row at a time. The reconstruction's sign_ext16 has to bend the same way, so the second row is
    read 0x8000 bytes below the first.
    """
    cols = 0x1000
    base = SPRITE_A + 0x8000                       # row 1 lands back at SPRITE_A
    sprite_rows = {base: _sprite([[0x0001]]), SPRITE_A: _sprite([[0x0001]])}
    other = _sprite([[0x0000], [0x0001]])          # row 0 misses, row 1 would hit
    pokes = {A_HIT_BOX_A: _box(0, base, cols, 0, 2),
             A_HIT_BOX_B: _box(0, SPRITE_B, cols, 0, 2),
             A_HIT_ROWS: b"\x02", A_COLLISION_HIT: b"\x00", SPRITE_B: other}
    pokes.update(sprite_rows)
    diffs, _ = differential(ENTRY_PIXEL_COLLISION,
                            {"a1": A_HIT_BOX_A, "a2": A_HIT_BOX_B, "_pokes": pokes},
                            lambda lib, buf: lib.g_pixel_collision(buf, A_HIT_BOX_A, A_HIT_BOX_B))
    assert not diffs, report(diffs)


def _random_masks(rng, rows, cols):
    """Sparse random occupancy: dense masks would make every case hit on row 0."""
    def word():
        if rng.random() < 0.35:
            return 0
        bits = 0
        for _ in range(rng.randint(1, 3)):
            bits |= 1 << rng.randrange(16)
        return bits
    return [[word() for _ in range(cols)] for _ in range(rows)]


PIXEL_FUZZ_CHUNKS = 4


def _pixel_fuzz_cases():
    rng = random.Random(0x13FE6)                 # seeded ONCE — every chunk replays this stream
    for i in range(400):
        cols = rng.randint(1, 6)
        rows = rng.randint(1, 40)
        # The source starts one cell in so the spill path has a previous cell to read, and the
        # blocks are far enough apart that rows * cols * 8 cannot run out of either.
        yield (i, cols, rows,
               _sprite(_random_masks(rng, rows, cols)),
               _sprite(_random_masks(rng, rows, cols)),
               rng.choice((0, 0, 1, 3, 8, 15, 16, 31)),
               rng.choice((0, 0, 1, 3, 8, 15, 16, 31)),
               rng.randrange(cols), rng.randrange(cols),
               rng.randint(1, rows), rng.random() < 0.5)


@pytest.mark.parametrize("chunk", range(PIXEL_FUZZ_CHUNKS))
def test_pixel_collision_fuzz(chunk):
    for (i, cols, rows, sprite_a, sprite_b, shift_a, shift_b,
         col_a, col_b, hit_rows, swap) in _pixel_fuzz_cases():
        if i % PIXEL_FUZZ_CHUNKS != chunk:
            continue
        _pixel_case(_box(0, SPRITE_A + col_a * CELL_BYTES, cols, shift_a, rows, cur_col=col_a),
                    _box(0, SPRITE_B + col_b * CELL_BYTES, cols, shift_b, rows, cur_col=col_b),
                    hit_rows, sprite_a, sprite_b, swap=swap)


# ------------------------------------------------------------------ test_overlap @ 0x13ef2

def _overlap_case(box_a, box_b, sprite_a, sprite_b):
    """Run test_overlap on the two staged boxes.

    Both column cursors are pre-filled with UNWRITTEN_W (via _box's default) so a candidate that
    failed to write one would differ. poison=True is deliberately NOT used here: test_overlap's own
    outputs include HB_SRC, and an inverted sprite pointer would send the pixel pass reading far
    outside the image, which the oracle rejects as unmodeled rather than diffing.
    """
    pokes = {A_HIT_BOX_A: box_a, A_HIT_BOX_B: box_b,
             A_HIT_ROWS: b"\x00", A_COLLISION_HIT: b"\xff",   # so `clr.b` is observable
             SPRITE_A: sprite_a, SPRITE_B: sprite_b}
    diffs, _ = differential(ENTRY_TEST_OVERLAP, {"_pokes": pokes},
                            lambda lib, buf: lib.g_test_overlap(buf))
    assert not diffs, report(diffs)


# A screen address far enough into the image that the column arithmetic below never underflows.
_DST = 0x70000


def test_overlap_y_band_miss():
    """No overlap in y: the routine clears collision_hit and returns without touching anything."""
    solid = _sprite([[0xffff]] * 4)
    for y_a, rows_a, y_b in ((100, 4, 104), (100, 4, 200), (100, 0, 100), (0, 1, 1)):
        _overlap_case(_box(_DST, SPRITE_A, 1, 0, rows_a, y=y_a),
                      _box(_DST, SPRITE_B, 1, 0, 4, y=y_b), solid, solid)


def test_overlap_y_band_add_is_a_byte():
    """`add.b 11(a1),d1` adds the row count into the LOW BYTE of y with no carry.

    y = 0x00fe with 4 rows therefore ends at 0x0002, not 0x0102 — so a box that visibly extends
    past the lower one is judged not to reach it. Reproduced, not corrected.
    """
    solid = _sprite([[0xffff]] * 8)
    for y_a in (0x00fc, 0x00fe, 0x00ff, 0x0100, 0x01fe):
        for y_b in (0x0001, 0x0002, 0x0003, 0x0100, 0x0101):
            _overlap_case(_box(_DST, SPRITE_A, 1, 0, 4, y=y_a),
                          _box(_DST, SPRITE_B, 1, 0, 4, y=y_b), solid, solid)


def test_overlap_column_alignment():
    """The column offset between the two sprites, on both sides of `cmp.w 8(a1),d1`.

    A gap of `n` cells inside the upper sprite's width starts it at column n; a gap wider than that
    is re-measured backwards from the scanline (CELLS_PER_ROW - n) and starts the LOWER sprite
    instead, or gives up when even that lands outside it.
    """
    sprite = _sprite([[0x0001] * 4] * 4)
    for gap_cells in range(CELLS_PER_ROW):
        _overlap_case(_box(_DST, SPRITE_A, 4, 0, 4, y=10),
                      _box(_DST + gap_cells * CELL_BYTES, SPRITE_B, 4, 0, 4, y=12),
                      sprite, sprite)


def test_overlap_column_offset_spans_rows():
    """The gap is taken modulo one scanline: only its remainder after `divu.w #$a0` counts."""
    sprite = _sprite([[0x0001] * 4] * 4)
    for rows_down in (0, 1, 2, 37):
        for gap_cells in (0, 1, 3, 19):
            gap = rows_down * SCREEN_ROW_BYTES + gap_cells * CELL_BYTES
            _overlap_case(_box(_DST, SPRITE_A, 4, 0, 4, y=10),
                          _box(_DST + gap, SPRITE_B, 4, 0, 4, y=12), sprite, sprite)


DIVU_ROW_OVERFLOW = SCREEN_ROW_BYTES * 0x10000


def test_overlap_column_divu_overflow():
    """`divu.w #$a0` on a gap >= 0xa0 * 0x10000 leaves the register UNCHANGED (V set, untested).

    The raw byte gap then flows straight into the column arithmetic instead of its remainder.
    """
    sprite = _sprite([[0x0001] * 4] * 4)
    for gap in (DIVU_ROW_OVERFLOW - CELL_BYTES, DIVU_ROW_OVERFLOW,
                DIVU_ROW_OVERFLOW + CELL_BYTES, 0x7ffffff8):
        _overlap_case(_box(_DST, SPRITE_A, 4, 0, 4, y=10),
                      _box((_DST + gap) & 0xffffffff, SPRITE_B, 4, 0, 4, y=12), sprite, sprite)


def test_overlap_exg_orders_the_boxes():
    """Whichever box sits lower in memory becomes the `upper` one, whichever slot it was staged in."""
    sprite = _sprite([[0x0001] * 2] * 6)
    for gap in (CELL_BYTES, SCREEN_ROW_BYTES, 2 * SCREEN_ROW_BYTES):
        _overlap_case(_box(_DST, SPRITE_A, 2, 0, 6, y=10),
                      _box(_DST + gap, SPRITE_B, 2, 0, 6, y=12), sprite, sprite)
        _overlap_case(_box(_DST + gap, SPRITE_A, 2, 0, 6, y=12),
                      _box(_DST, SPRITE_B, 2, 0, 6, y=10), sprite, sprite)


def test_overlap_row_count_clamped_to_lower_box():
    """hit_rows = upper.rows + upper.y - lower.y, clamped (signed byte) to the lower box's height."""
    sprite = _sprite([[0x0000] * 2] * 20)          # no pixels: only the bookkeeping is under test
    for rows_a, y_a, rows_b, y_b in ((20, 10, 2, 12), (20, 10, 20, 12), (4, 10, 20, 11),
                                     (20, 10, 0, 12), (255, 10, 3, 11), (1, 10, 1, 10)):
        _overlap_case(_box(_DST, SPRITE_A, 2, 0, rows_a, y=y_a),
                      _box(_DST + CELL_BYTES, SPRITE_B, 2, 0, rows_b, y=y_b), sprite, sprite)


def test_overlap_hit_ends_the_column_loop():
    """A pixel hit parks the upper box's cursor at COLS - 1, so the next `addq.w` ends the sweep."""
    rows = 4
    for hit_col in (0, 1, 2, 3, None):
        a = _sprite([[0x0001 if c == hit_col else 0 for c in range(4)] for _ in range(rows)])
        b = _sprite([[0x0001] * 4 for _ in range(rows)])
        _overlap_case(_box(_DST, SPRITE_A, 4, 0, rows, y=10),
                      _box(_DST, SPRITE_B, 4, 0, rows, y=10), a, b)


OVERLAP_FUZZ_CHUNKS = 4


def _overlap_fuzz_cases():
    rng = random.Random(0x13EF2)                 # seeded ONCE — every chunk replays this stream
    for i in range(300):
        cols_a, cols_b = rng.randint(1, 5), rng.randint(1, 5)
        rows_a, rows_b = rng.randint(1, 24), rng.randint(1, 24)
        # Gaps mostly land within a couple of scanlines (where the interesting column arithmetic
        # is) but sometimes anywhere in the 32-bit range, to reach the divu overflow path.
        near = rng.random() < 0.8
        gap = (rng.randrange(-3 * SCREEN_ROW_BYTES, 3 * SCREEN_ROW_BYTES) if near
               else rng.randrange(1 << 32))
        yield (i,
               _box(_DST, SPRITE_A, cols_a, rng.choice((0, 0, 1, 7, 15)), rows_a,
                    y=rng.randrange(0x200)),
               _box((_DST + gap) & 0xffffffff, SPRITE_B, cols_b, rng.choice((0, 0, 1, 7, 15)),
                    rows_b, y=rng.randrange(0x200)),
               _sprite(_random_masks(rng, rows_a + 24, cols_a)),
               _sprite(_random_masks(rng, rows_b + 24, cols_b)))


@pytest.mark.parametrize("chunk", range(OVERLAP_FUZZ_CHUNKS))
def test_overlap_fuzz(chunk):
    for i, box_a, box_b, sprite_a, sprite_b in _overlap_fuzz_cases():
        if i % OVERLAP_FUZZ_CHUNKS == chunk:
            _overlap_case(box_a, box_b, sprite_a, sprite_b)


# ------------------------------------------------------------------ joust_bounce @ 0x140fe

OBJ_A = A_OBJECT_TABLE                          # slot 0 (player 1)
OBJ_B = A_OBJECT_TABLE + OBJ_SIZE               # slot 1 (player 2)


def _bounce_case(x_a, x_b, vx_a, vx_b, flags_a, flags_b, poison=False):
    pokes = {OBJ_A: _object(flags=UNWRITTEN_W, x=x_a & 0xffff, vx=vx_a & 0xffff),
             OBJ_B: _object(flags=UNWRITTEN_W, x=x_b & 0xffff, vx=vx_b & 0xffff)}
    regs = {"a0": OBJ_A, "a3": OBJ_B, "d0": flags_a, "d1": flags_b, "_pokes": pokes}
    diffs, _ = differential(ENTRY_JOUST_BOUNCE, regs,
                            lambda lib, buf: lib.g_joust_bounce(buf, OBJ_A, OBJ_B,
                                                                flags_a, flags_b),
                            poison=poison)
    assert not diffs, (f"x={x_a:#x}/{x_b:#x} vx={vx_a:#x}/{vx_b:#x} "
                       f"flags={flags_a:#x}/{flags_b:#x}\n{report(diffs)}")


# The gap A.x - B.x either side of both thresholds. -18..-1 and >= 302 mean "A is on the left"; the
# playfield is 320 wide and x wraps, which is why a gap of -19 or less means the opposite.
_BOUNCE_GAPS = (0, 1, -1, -18, -19, -20, 0x12d, 0x12e, 0x12f, 0x140, -0x140,
                0x7fff, -0x8000, -0x7fff)


@pytest.mark.parametrize("gap", _BOUNCE_GAPS)
def test_joust_bounce_gap_thresholds(gap):
    base_x = 0x1000                               # keeps A.x - B.x exact for every gap above
    for vx_a in (0, 4, -4):
        for vx_b in (0, 4, -4):
            _bounce_case(base_x + gap, base_x, vx_a, vx_b, 0, 0)


def test_joust_bounce_flag_bits_and_attribution():
    """Only bit 15 of each flags word may change, and only its LOW WORD is ever stored."""
    for flags_a, flags_b in ((0, 0), (0x8000, 0x8000), (0xffff, 0xffff),
                             (0x1234, 0x4321), (0xdead8000, 0xbeef0000), (0xffffffff, 0x7fffffff)):
        for gap in (0, -19, -1, 0x12e):
            _bounce_case(0x1000 + gap, 0x1000, 4, -4, flags_a, flags_b, poison=True)


def test_joust_bounce_velocity_extremes():
    """`neg.w` of 0x8000 is 0x8000 again, and a velocity already pointing the right way is left
    untouched — the routine writes it only when it actually flips."""
    for vx in (0, 1, -1, 0x7fff, -0x8000):
        for gap in (0, -19):
            _bounce_case(0x1000 + gap, 0x1000, vx, vx, 0, 0, poison=True)


# ------------------------------------------------------------------ check_platform @ 0x13300

PLAT_Y0, PLAT_Y1, PLAT_X0, PLAT_X1 = 60, 66, 100, 180


def _platform_table(boxes):
    out = bytearray()
    for y0, y1, x0, x1 in boxes:
        out += struct.pack(">HHHH", y0 & 0xffff, y1 & 0xffff, x0 & 0xffff, x1 & 0xffff)
    return bytes(out)


_DEFAULT_PLATFORMS = [(PLAT_Y0 + i * 20, PLAT_Y1 + i * 20, PLAT_X0, PLAT_X1)
                      for i in range(N_PLATFORMS)]


def _platform_case(x, y, flags, present=(1,) * N_PLATFORMS, flap_frame=0,
                   platforms=None, poison=False):
    pokes = _result_stub(ENTRY_CHECK_PLATFORM, reg=0)
    pokes[A_PLATFORM_PRESENT] = bytes(present)
    pokes[A_PLATFORM_TABLE] = _platform_table(platforms or _DEFAULT_PLATFORMS)
    pokes[OBJ_A] = _object(x=x & 0xffff, y=y & 0xffff, flap_frame=flap_frame,
                           anim_timer=0x5a, step_timer=0x5a, vy=UNWRITTEN_W)
    regs = {"a0": OBJ_A, "d0": flags, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_check_platform(buf, OBJ_A, flags, abi.RESULT),
                            poison=poison)
    assert not diffs, f"x={x} y={y} flags={flags:#x}\n{report(diffs)}"


def test_check_platform_box_edges():
    """Every edge of the first platform's box, inclusive on all four sides."""
    for y in (PLAT_Y0 - 1, PLAT_Y0, PLAT_Y0 + 1, PLAT_Y1 - 1, PLAT_Y1, PLAT_Y1 + 1):
        for x in (PLAT_X0 - 1, PLAT_X0, PLAT_X0 + 1, PLAT_X1 - 1, PLAT_X1, PLAT_X1 + 1):
            _platform_case(x, y, flags=0)


def test_check_platform_absent_platforms_are_skipped():
    """platform_present gates each record; a 0 byte makes the platform invisible to the scan."""
    inside = (PLAT_X0 + 10, PLAT_Y0 + 2)
    for present in ((1,) * N_PLATFORMS, (0,) * N_PLATFORMS, (0, 1, 1, 1, 1, 1, 1, 1),
                    (0xff, 0, 0, 0, 0, 0, 0, 0)):
        _platform_case(inside[0], inside[1], flags=0, present=present, poison=True)


def test_check_platform_scans_every_slot():
    """Every platform record in the table is reached, not just the first."""
    for slot in range(N_PLATFORMS):
        _platform_case(PLAT_X0 + 10, PLAT_Y0 + 2 + slot * 20, flags=0)


def test_check_platform_present_is_indexed_per_slot():
    """`tst.b (a2)+` walks platform_present in step with platform_table, so slot n's byte gates
    slot n's box — and only that one.

    Every other case here puts the object inside platform 0's box, where a scan that always read
    platform_present[0] would agree; these put it in slot n's box with the presence flags set only
    at n, and then only away from n.
    """
    for slot in range(N_PLATFORMS):
        y = PLAT_Y0 + 2 + slot * 20
        only_this_one = tuple(1 if i == slot else 0 for i in range(N_PLATFORMS))
        all_but_this_one = tuple(0 if i == slot else 1 for i in range(N_PLATFORMS))
        _platform_case(PLAT_X0 + 10, y, flags=0, present=only_this_one, poison=True)
        _platform_case(PLAT_X0 + 10, y, flags=0, present=all_but_this_one, poison=True)


def test_check_platform_first_match_wins():
    """With overlapping boxes the scan stops at the LOWEST-numbered present platform containing the
    object, so it is snapped to that record's y0 rather than a later record's.

    The default table's boxes are disjoint, so nothing above can tell the scan's direction apart.
    Here every box contains the object and each has a distinct y0, which the landing writes out.
    """
    overlapping = [(PLAT_Y0 + i, PLAT_Y1 + 40, PLAT_X0, PLAT_X1) for i in range(N_PLATFORMS)]
    inside_all = PLAT_Y1 + 39
    for first_present in range(N_PLATFORMS):
        present = tuple(1 if i >= first_present else 0 for i in range(N_PLATFORMS))
        _platform_case(PLAT_X0 + 10, inside_all, flags=0, platforms=overlapping,
                       present=present, poison=True)


def test_check_platform_flap_frame_nudge():
    """Flap frame 4 puts the rider one pixel below the platform top; every other frame does not."""
    for flap_frame in (0, 3, 4, 5, 0xffff):
        _platform_case(PLAT_X0 + 10, PLAT_Y0 + 2, flags=0, flap_frame=flap_frame, poison=True)


def test_check_platform_leaving_resets_the_walk():
    """Off every platform: bit 9 is cleared, and if it HAD been set the walk state is reset too."""
    for flags in (0, 0x200, 0xffff, 0xfffffdff, 0xffffffff, 0x12345678, 0x12345778):
        _platform_case(0, 0, flags=flags, poison=True)
        _platform_case(PLAT_X0 + 10, PLAT_Y0 + 2, flags=flags, poison=True)


def test_check_platform_negative_coordinates():
    """The box compares are SIGNED words, so a negative coordinate is below every platform."""
    boxes = [(0x8000, 0x7fff, 0x8000, 0x7fff)] + _DEFAULT_PLATFORMS[1:]
    for x, y in ((-1, -1), (-0x8000, -0x8000), (0x7fff, 0x7fff), (0, 0)):
        _platform_case(x, y, flags=0, platforms=boxes)


# ------------------------------------------------------------------ egg sprite blits

EGG_ROWS = 6
EGG_SRC_ROW_BYTES = 0x10        # 4 plane words read + 4 skipped by `adda.w #$8`
EGG_WRAP_X = 0x130


def _egg_source(rows):
    """Egg sprite source: `rows` rows of four plane words, EGG_SRC_ROW_BYTES apart.

    Unlike _sprite the four planes are independent here — the egg blits write each plane through to
    its own screen word rather than OR-ing them together — so every plane gets a distinct pattern.
    """
    out = bytearray()
    for r in range(rows):
        row = bytearray(EGG_SRC_ROW_BYTES)
        for plane in range(CELL_PLANE_WORDS):
            word = 0x8421 ^ (r * 0x1111) ^ (plane * 0x0f0f)
            struct.pack_into(">H", row, plane * 2, word & 0xffff)
        out += row
    return bytes(out)


def _screen_backdrop(rows):
    """Non-zero screen bytes under the sprite, so an AND-NOT that clears nothing still shows."""
    return bytes((0xa5 + i) & 0xff for i in range((rows + 2) * SCREEN_ROW_BYTES))


def _erase_case(rows, shift, egg_x, dst=SCREEN, poison=False):
    pokes = {OBJ_A: _object(egg_x=egg_x & 0xffff, egg_dst=dst, egg_src=SPRITE_A,
                            egg_rows=rows, egg_shift=shift),
             SPRITE_A: _egg_source(max(rows, 1) if rows else 256),
             SCREEN: _screen_backdrop(rows if rows else 256)}
    diffs, _ = differential(ENTRY_ERASE_EGG_SPRITE, {"a0": OBJ_A, "_pokes": pokes},
                            lambda lib, buf: lib.g_erase_egg_sprite(buf, OBJ_A), poison=poison)
    assert not diffs, f"rows={rows} shift={shift} x={egg_x:#x}\n{report(diffs)}"


@pytest.mark.parametrize("shift", (0, 1, 4, 8, 15, 16, 17, 31, 32, 33, 63, 64, 0xff))
def test_erase_egg_sprite_shifts(shift):
    for egg_x in (0, EGG_WRAP_X - 1, EGG_WRAP_X, EGG_WRAP_X + 1):
        _erase_case(EGG_ROWS, shift, egg_x)


def test_erase_egg_sprite_wrap_column():
    """Past EGG_WRAP_X the spill column belongs to the previous scanline, so the wrap pass starts a
    whole row back instead of one cell right."""
    for egg_x in (0, 0x100, EGG_WRAP_X - 1, EGG_WRAP_X, 0x13f, 0x8000, 0xffff):
        _erase_case(EGG_ROWS, 5, egg_x, dst=SCREEN + SCREEN_ROW_BYTES, poison=True)


def test_erase_egg_sprite_row_count_is_a_byte():
    """`subq.b #1` — a row count of 0 erases 256 rows, marching 0xa000 bytes down the image."""
    for rows in (0, 1, 2, 255):
        _erase_case(rows, 3, 0)


def _draw_case(rows, shift, draw_x, bottom, egg_state=1, dst=SCREEN, poison=False):
    src_rows = rows if rows else 256
    pokes = {OBJ_A: _object(egg_state=egg_state),
             A_DRAW_DST: dst.to_bytes(4, "big"),
             A_DRAW_SRC: SPRITE_A.to_bytes(4, "big"),
             A_DRAW_X: (draw_x & 0xffff).to_bytes(2, "big"),
             A_DRAW_SHIFT: bytes([shift]),
             A_DRAW_ROWS: bytes([rows]),
             A_PLAYFIELD_BOTTOM: (bottom & 0xffffffff).to_bytes(4, "big"),
             SPRITE_A: _egg_source(src_rows),
             SCREEN: _screen_backdrop(src_rows)}
    diffs, _ = differential(ENTRY_DRAW_EGG_SPRITE, {"a0": OBJ_A, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_egg_sprite(buf, OBJ_A), poison=poison)
    assert not diffs, (f"rows={rows} shift={shift} x={draw_x:#x} bottom={bottom:#x} "
                       f"state={egg_state:#x}\n{report(diffs)}")


def test_draw_egg_sprite_needs_an_egg():
    """State 0 means the slot carries no egg, and the routine returns before touching anything."""
    for egg_state in (0, 1, 0x22, 0xff):
        _draw_case(EGG_ROWS, 4, 0, SCREEN + 0x8000, egg_state=egg_state, poison=True)


@pytest.mark.parametrize("shift", (0, 1, 4, 15, 16, 31, 32, 64, 0xff))
def test_draw_egg_sprite_shifts(shift):
    # poison is safe here and nowhere else in this routine's battery: with playfield_bottom far
    # below, the only bytes the oracle writes are screen bytes. The lava cases below write
    # draw_rows, which steers the wrap pass, so poisoning them would change the run under test.
    for draw_x in (0, EGG_WRAP_X - 1, EGG_WRAP_X):
        _draw_case(EGG_ROWS, shift, draw_x, SCREEN + 0x8000, poison=True)


def test_draw_egg_sprite_lava_line():
    """Reaching playfield_bottom stops the draw, flags the egg as fallen, and rewrites draw_rows to
    the number of rows actually drawn — which the wrap pass then repeats.

    A bottom AT the destination stops on row 0, leaving draw_rows = 0; `subq.b` reads that as 256,
    so the wrap pass marches 256 scanlines down the image. That is what the original does.
    """
    for rows_drawn in range(EGG_ROWS + 2):
        _draw_case(EGG_ROWS, 4, 0, SCREEN + rows_drawn * SCREEN_ROW_BYTES)


def test_draw_egg_sprite_lava_compare_is_signed():
    """`cmpa.l` + `blt` compares the addresses SIGNED, so a 'negative' playfield_bottom is above
    every destination and the draw stops immediately."""
    for bottom in (0, 1, SCREEN, 0x7fffffff, 0x80000000, 0xffffffff):
        _draw_case(EGG_ROWS, 4, 0, bottom)


def test_draw_egg_sprite_row_count_is_a_byte():
    for rows in (0, 1, 255):
        _draw_case(rows, 2, 0, SCREEN + 0x8000)


EGG_FUZZ_CHUNKS = 2


def _egg_fuzz_cases():
    rng = random.Random(0x12914)                 # seeded ONCE — every chunk replays this stream
    for i in range(200):
        yield (i, rng.randint(1, 40), rng.choice((0, 1, 2, 7, 8, 15, 16, 17, 33, 64, 255)),
               rng.choice((0, 0x100, EGG_WRAP_X - 1, EGG_WRAP_X, 0x13f, 0xffff)),
               rng.randrange(45))


@pytest.mark.parametrize("chunk", range(EGG_FUZZ_CHUNKS))
def test_egg_sprite_fuzz(chunk):
    for i, rows, shift, x, rows_before_lava in _egg_fuzz_cases():
        if i % EGG_FUZZ_CHUNKS != chunk:
            continue
        _erase_case(rows, shift, x)
        _draw_case(rows, shift, x, SCREEN + rows_before_lava * SCREEN_ROW_BYTES)


# ------------------------------------------------------------------ ptero_avoid_platform @ 0x15226

PTERO = A_PTERODACTYL_TABLE


def _platform_sprites(records):
    """platform_sprites: {present ptr.l, rows.w, cols.w, src.l, dst offset.l} x 8."""
    out = bytearray()
    for slot, (rows, dst_off) in enumerate(records):
        out += struct.pack(">IHHII", A_PLATFORM_PRESENT + slot, rows & 0xffff, 2, SPRITE_B,
                           dst_off & 0xffffffff)
    return bytes(out)


def _ptero_record(x, y, swoop_timer=UNWRITTEN_W & 0xff):
    rec = bytearray(PTERO_SIZE)
    struct.pack_into(">H", rec, 0x0c, x & 0xffff)
    struct.pack_into(">H", rec, 0x0e, y & 0xffff)
    rec[0x1e] = swoop_timer
    return bytes(rec)


# A within-row byte offset folded into every default dst offset, so `divu.w #$a0` leaves a NON-ZERO
# remainder in D1's high half. Without it every record divides exactly and a candidate that dropped
# the high half on the hit path would look correct. It is smaller than a scanline, so each record's
# recovered row — what the band test uses — is unchanged.
PLATFORM_COLUMN_BYTES = 0x37

_DEFAULT_SPRITE_ROWS = [(8, (20 + slot * 12) * SCREEN_ROW_BYTES + PLATFORM_COLUMN_BYTES)
                        for slot in range(N_PLATFORMS)]


def _avoid_case(x, y, scratch, present=(1,) * N_PLATFORMS, records=None, poison=False):
    pokes = _result_stub(ENTRY_PTERO_AVOID_PLATFORM, reg=1)
    pokes[A_PLATFORM_PRESENT] = bytes(present)
    pokes[A_PLATFORM_SPRITES] = _platform_sprites(records or _DEFAULT_SPRITE_ROWS)
    pokes[PTERO] = _ptero_record(x, y)
    regs = {"a0": PTERO, "d1": scratch, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_ptero_avoid_platform(buf, PTERO, scratch,
                                                                        abi.RESULT),
                            poison=poison)
    assert not diffs, f"x={x} y={y} scratch={scratch:#x}\n{report(diffs)}"


PTERO_X_MIN, PTERO_X_MAX = 0x3c, 0xfa


@pytest.mark.parametrize("x", (0, PTERO_X_MIN - 1, PTERO_X_MIN, PTERO_X_MIN + 1,
                               PTERO_X_MAX - 1, PTERO_X_MAX, PTERO_X_MAX + 1, 0x8000, 0xffff))
def test_ptero_avoid_x_band(x):
    """Outside the x band the routine returns 0 without looking at a single platform."""
    for y in (0, 25, 200):
        _avoid_case(x, y, scratch=0x1234abcd)


def test_ptero_avoid_row_band():
    """A platform blocks the pterodactyl while its row band, extended 13 rows upward, brackets y."""
    row = 20
    records = [(8, row * SCREEN_ROW_BYTES)] + [(0, 0)] * (N_PLATFORMS - 1)
    for y in range(row - 16, row + 12):
        _avoid_case(PTERO_X_MIN + 10, y, scratch=0, present=(1, 0, 0, 0, 0, 0, 0, 0),
                    records=records)


def test_ptero_avoid_scratch_high_word_survives():
    """Only D1's LOW word is written, so the caller's high half comes back on the clear paths — and
    the divu remainder of the matching record comes back on a hit."""
    for scratch in (0, 0xffffffff, 0xdead0000, 0x0000beef, 0x12345678):
        _avoid_case(0, 0, scratch=scratch, poison=True)                      # x band reject
        _avoid_case(PTERO_X_MIN + 10, 0, scratch=scratch, poison=True)       # scanned, no hit
        _avoid_case(PTERO_X_MIN + 10, 22, scratch=scratch, poison=True)      # hit


def test_ptero_avoid_absent_platforms_and_divu_overflow():
    """An absent platform is skipped through its present pointer; a dst offset past 0xa0 * 0x10000
    leaves `divu.w` — and so the recovered row — undivided."""
    for present in ((1,) * N_PLATFORMS, (0,) * N_PLATFORMS, (0, 0, 1, 0, 0, 0, 0, 0)):
        _avoid_case(PTERO_X_MIN + 10, 45, scratch=0x5a5a5a5a, present=present)
    for dst_off in (DIVU_ROW_OVERFLOW - 1, DIVU_ROW_OVERFLOW, 0xffffffff):
        _avoid_case(PTERO_X_MIN + 10, 45, scratch=0,
                    records=[(8, dst_off)] * N_PLATFORMS)


# ------------------------------------------------------------------ ptero_spot_player @ 0x15276

SND_PTERO_SWOOP = 3
PT_FLAG_MOVING_RIGHT = 1 << 2
PLAYER = A_OBJECT_TABLE


def _spot_pokes(ptero_x, ptero_y, player_x, player_y, priority=0x10):
    return {PTERO: _ptero_record(ptero_x, ptero_y),
            PLAYER: _object(x=player_x & 0xffff, y=player_y & 0xffff),
            A_SND_PRIORITY: (priority & 0xffff).to_bytes(2, "big")}


def _spot_final(ptero_x, ptero_y, player_x, player_y, flags, priority=0x10):
    """The oracle's final image for one flags word, so two flags words can be compared directly.

    Every effect the routine has is in there: the swoop timer it arms, and — through play_sound —
    snd_priority. The Dosound list itself is off-image but is the same constant on both sides.
    The stack guard is cut off exactly as harness.differential cuts it: on the path that reaches
    play_sound the routine PUSHES D0, so two flags words that agree on bit 2 still leave two
    different stacks.
    """
    image = harness.make_image(_spot_pokes(ptero_x, ptero_y, player_x, player_y, priority))
    final, _, _ = emu.run(image, ENTRY_PTERO_SPOT_PLAYER, {"a0": PTERO, "a3": PLAYER, "d0": flags})
    return bytes(final[:emu.STACK_GUARD_LO])


def _spot_case(ptero_x, ptero_y, player_x, player_y, flags, priority=0x10, poison=False):
    pokes = _spot_pokes(ptero_x, ptero_y, player_x, player_y, priority)
    regs = {"a0": PTERO, "a3": PLAYER, "d0": flags, "_pokes": pokes}
    diffs, _ = differential(ENTRY_PTERO_SPOT_PLAYER, regs,
                            lambda lib, buf: lib.g_ptero_spot_player(buf, PTERO, PLAYER, flags),
                            poison=poison)
    assert not diffs, (f"ptero=({ptero_x},{ptero_y}) player=({player_x},{player_y}) "
                       f"flags={flags:#x} priority={priority:#x}\n{report(diffs)}")


@pytest.mark.parametrize("row_gap", range(-8, 12))
def test_ptero_spot_row_band(row_gap):
    """`addq.w #4` then an UNSIGNED `cmpi.w #$a` — one test covers both signs, admitting a y gap of
    -4..+6 rows and nothing else."""
    for flags in (0, PT_FLAG_MOVING_RIGHT):
        _spot_case(0x80, 0x40 + row_gap, 0x40, 0x40, flags)


# The gap `ahead` the routine actually tests is `8 - x_gap` flying left and `x_gap - 8` flying
# right, so every threshold needs a pair of x_gaps to be reached from both directions: the -0x5f..
# -0x62 and 0x6f..0x72 groups straddle the far threshold (0x69) the way -0x11..-0xf and 8..9
# straddle the near one.
_SPOT_X_GAPS = (-0x80, -0x71, -0x70, -0x6f, -0x62, -0x61, -0x60, -0x5f, -0x11, -0x10, -0xf, -1,
                0, 1, 8, 9, 0x60, 0x61, 0x68, 0x69, 0x6a, 0x6f, 0x70, 0x71, 0x72, 0x100)


@pytest.mark.parametrize("x_gap", _SPOT_X_GAPS)
def test_ptero_spot_x_window(x_gap):
    """The +8 bias is applied BEFORE the direction flip, so the window is asymmetric: 1..0x60
    pixels to the left when flying left, 0x11..0x70 to the right when flying right."""
    for flags in (0, PT_FLAG_MOVING_RIGHT):
        _spot_case(0x100, 0x40, 0x100 + x_gap, 0x40, flags)


def test_ptero_spot_ignores_the_other_flag_bits():
    """`btst #2,d0` reads one bit, so a full flags word behaves as its bit 2 alone does. One gap
    each way is enough — sweeping every gap again would only re-run the two paths above.

    Each pair is run against the reconstruction AND compared with itself: the two oracle images
    must come out identical, which is what makes "equivalent" a check rather than a label.
    """
    for x_gap in (-0x20, 0x20):
        position = (0x100, 0x40, 0x100 + x_gap, 0x40)
        for flags, equivalent in ((0xffff, PT_FLAG_MOVING_RIGHT), (0xfffffffb, 0)):
            _spot_case(*position, flags)
            _spot_case(*position, equivalent)
            assert _spot_final(*position, flags) == _spot_final(*position, equivalent), (
                f"flags={flags:#x} did not behave as its bit 2 alone ({equivalent:#x}) does "
                f"at x_gap={x_gap:#x}")


def test_ptero_spot_sound_priority():
    """play_sound drops the call unless SND_PTERO_SWOOP outranks (is <=) the sound already playing;
    the Dosound command list itself is off-image and is compared through the kit's ledger."""
    for priority in (0, 2, 3, 4, 0x10, 0x7fff, 0x8000, 0xffff):
        _spot_case(0x100, 0x40, 0x100 - 0x20, 0x40, flags=0, priority=priority, poison=True)
        _spot_case(0x100, 0x40, 0x100 + 0x100, 0x40, flags=0, priority=priority)   # no trigger


def test_ptero_spot_wrapping_coordinates():
    """The gaps are plain 16-bit subtractions, so coordinates either side of the word wrap are
    handled by the same arithmetic the game's own do."""
    for ptero_x, player_x in ((0, 0xfff0), (0xfff0, 0), (0x8000, 0x7fff), (0x7fff, 0x8000)):
        for flags in (0, PT_FLAG_MOVING_RIGHT):
            _spot_case(ptero_x, 0x40, player_x, 0x40, flags)
            _spot_case(ptero_x, 0, player_x, 0xfffe, flags)


# ------------------------------------------------------------------ count_objects_and_pad @ 0x1033e

def _count_case(game_phase, objects=None, messages=None, strings=b"", poison=False):
    pokes = {A_GAME_PHASE: bytes([game_phase]),
             A_LIVE_OBJECT_COUNT: bytes([UNWRITTEN_W & 0xff]),
             A_EGG_COUNT: bytes([UNWRITTEN_W & 0xff]),
             A_MESSAGE_CHAR_COUNT: bytes([UNWRITTEN_W & 0xff]),
             A_PTERO_SPAWN_COUNT: bytes([UNWRITTEN_W & 0xff]),
             A_OBJECT_TABLE: b"".join(objects or [_object()] * N_OBJECTS),
             A_MESSAGE_TABLE: b"".join(messages or [bytes(MSG_RECORD)] * N_MESSAGES),
             STRINGS: strings}
    diffs, _ = differential(ENTRY_COUNT_OBJECTS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_count_objects_and_pad(buf), poison=poison)
    assert not diffs, f"game_phase={game_phase}\n{report(diffs)}"


def _message(kind, screen_ptr):
    rec = bytearray(MSG_RECORD)
    rec[0] = kind
    struct.pack_into(">I", rec, 4, screen_ptr)
    return bytes(rec)


def test_count_objects_live_and_egg_counts():
    """A slot counts as live unless its flags are 0, or it is awaiting respawn and has never been
    drawn (prev_dst == 0). The egg count is independent: any non-zero egg state counts."""
    RESPAWN = 1 << 7
    variants = [_object(),                                        # empty slot
                _object(flags=1),                                 # plain live object
                _object(flags=RESPAWN),                           # respawning, never drawn
                _object(flags=RESPAWN, prev_dst=0x70000),         # respawning, already drawn
                _object(flags=0, prev_dst=0x70000),               # flags 0 still means empty
                _object(flags=1, egg_state=0x22),                 # live, carrying an egg
                _object(egg_state=1),                             # empty slot, egg state set
                _object(flags=0x8000, egg_state=0xff)]
    for variant in variants:
        _count_case(0, objects=[variant] * N_OBJECTS, poison=True)
    # A mixed table, so the counts are not trivially 0 or N.
    _count_case(0, objects=[variants[i % len(variants)] for i in range(N_OBJECTS)], poison=True)


def test_count_objects_player1_egg_state_window():
    """Player 1's own egg record adds one more live object while its state is 4..0x12 (SIGNED byte
    compares, so 0x80..0xff are all below 4)."""
    for state in (0, 3, 4, 5, 0x11, 0x12, 0x13, 0x7f, 0x80, 0xff):
        objects = [_object(egg_state=state)] + [_object()] * (N_OBJECTS - 1)
        _count_case(0, objects=objects, poison=True)


def test_count_objects_pad_loop_bounds():
    """The pad counts (8 - live) and (0x0e - eggs); a full table drives both to zero and a live
    count above 8 takes the `ble` early-out. The loops themselves write nothing."""
    for live in range(N_OBJECTS + 1):
        objects = [_object(flags=1, egg_state=1)] * live + [_object()] * (N_OBJECTS - live)
        _count_case(0, objects=objects)


def test_count_message_chars_walks_the_screen_pointer():
    """ORIGINAL QUIRK, REPRODUCED: the walk follows the message's SCREEN pointer (+4), not its
    string pointer (+8), so what it counts is screen bytes up to the first zero. Only a delay loop
    consumes the count, so the game never notices."""
    text = b"THY GAME IS OVER\x00"
    for kinds in ((0,) * N_MESSAGES, (1,) + (0,) * (N_MESSAGES - 1), (1,) * N_MESSAGES):
        messages = [_message(kind, STRINGS) for kind in kinds]
        _count_case(1, messages=messages, strings=text, poison=True)


def test_count_message_chars_cap():
    """The walk stops dead at 0x23 characters, wherever in the table it reaches it."""
    for length in (0, 1, 0x22, 0x23, 0x24, 0x40):
        messages = [_message(1, STRINGS)] + [_message(0, STRINGS)] * (N_MESSAGES - 1)
        _count_case(1, messages=messages, strings=b"A" * length + b"\x00")
        many = [_message(1, STRINGS)] * N_MESSAGES
        _count_case(1, messages=many, strings=b"A" * length + b"\x00")


def test_count_objects_game_phase_selects_the_pass():
    """Any non-zero game_phase takes the message pass; only 0 takes the object pass."""
    objects = [_object(flags=1, egg_state=1)] * N_OBJECTS
    messages = [_message(1, STRINGS)] * N_MESSAGES
    for game_phase in (0, 1, 2, 0x80, 0xff):
        _count_case(game_phase, objects=objects, messages=messages, strings=b"ABCDE\x00")


# ------------------------------------------------------------------ the mirrored constants
#
# Everything above restates addresses and record strides that really live in ../../names.txt and
# include/object.h. Nothing makes a drifted mirror FAIL on its own: both cores would simply run
# against the real address, agree byte-for-byte on the game's own static data, and go green while
# the staged inputs landed in dead memory. These two pin the mirrors, the way test_constants.py
# pins the other batteries' — hence the import of its scraper rather than a second copy of it.

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_COUNT_OBJECTS, "count_objects_and_pad"),
                       (ENTRY_DRAW_EGG_SPRITE, "draw_egg_sprite"),
                       (ENTRY_ERASE_EGG_SPRITE, "erase_egg_sprite"),
                       (ENTRY_CHECK_PLATFORM, "check_platform"),
                       (ENTRY_TEST_OVERLAP, "test_overlap"),
                       (ENTRY_PIXEL_COLLISION, "pixel_collision"),
                       (ENTRY_JOUST_BOUNCE, "joust_bounce"),
                       (ENTRY_PTERO_AVOID_PLATFORM, "ptero_avoid_platform"),
                       (ENTRY_PTERO_SPOT_PLAYER, "ptero_spot_player")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_constants_match_the_headers():
    """Every constant this file restates equals the one src/object.c compiles against.

    Four headers, because the constants this layer shares with another were hoisted out of
    object.h: the globals it reads by address into addrs.h, the object record — which the drawing
    layer walks too — into joust.h, and snd_priority into sound.h, whose play_sound owns it on
    ptero_spot_player's behalf. Each header is scraped by name rather than as one merged namespace,
    so a constant that drifts back into the wrong header fails here instead of being found in
    whichever copy still happens to hold the old value.
    """
    header = _defines("include/object.h")
    addrs_h = _defines("include/addrs.h")
    joust_h = _defines("include/joust.h")
    sound_h = _defines("include/sound.h")
    mirrored = {
        "A_platform_present": A_PLATFORM_PRESENT, "A_game_phase": A_GAME_PHASE,
        "A_live_object_count": A_LIVE_OBJECT_COUNT, "A_egg_count": A_EGG_COUNT,
        "A_message_char_count": A_MESSAGE_CHAR_COUNT, "A_ptero_spawn_count": A_PTERO_SPAWN_COUNT,
        "A_hit_box_a": A_HIT_BOX_A, "A_hit_box_b": A_HIT_BOX_B, "A_hit_rows": A_HIT_ROWS,
        "A_collision_hit": A_COLLISION_HIT, "A_draw_x": A_DRAW_X,
        "A_message_table": A_MESSAGE_TABLE, "A_platform_table": A_PLATFORM_TABLE,
        "A_platform_sprites": A_PLATFORM_SPRITES,
        "MSG_RECORD": MSG_RECORD, "PSPR_RECORD": PSPR_RECORD,
        "PLAT_RECORD": PLAT_RECORD, "CELLS_PER_ROW": CELLS_PER_ROW,
        "PT_FLAG_MOVING_RIGHT": PT_FLAG_MOVING_RIGHT,
    }
    for name, value in mirrored.items():
        assert header[name] == value, f"{name}: object.h has {header[name]:#x}, test has {value:#x}"

    for defines, origin, shared_mirrored in (
            (addrs_h, "addrs.h", {"A_playfield_bottom": A_PLAYFIELD_BOTTOM,
                                  "A_object_table": A_OBJECT_TABLE, "A_draw_dst": A_DRAW_DST,
                                  "A_draw_src": A_DRAW_SRC, "A_draw_shift": A_DRAW_SHIFT,
                                  "A_draw_rows": A_DRAW_ROWS}),
            (joust_h, "joust.h", {"OBJ_SIZE": OBJ_SIZE, "CELL_PLANE_WORDS": CELL_PLANE_WORDS}),
            (sound_h, "sound.h", {"A_snd_priority": A_SND_PRIORITY})):
        for name, value in shared_mirrored.items():
            assert defines[name] == value, (f"{name}: {origin} has {defines[name]:#x}, "
                                            f"test has {value:#x}")

    # Field offsets the packers above encode positionally — in a `struct.pack` format string
    # (_box, _platform_table, _platform_sprites) or a literal offset (_object, _ptero_record,
    # _message) — and which therefore no other assertion can catch drifting.
    for name, off in (("PT_X", 0x0c), ("PT_Y", 0x0e), ("PT_SWOOP_TIMER", 0x1e),
                      ("MSG_KIND", 0x0), ("MSG_SCREEN_PTR", 0x4),
                      # _box packs ">IIHBBHH"
                      ("HB_DST", 0x0), ("HB_SRC", 0x4), ("HB_COLS", 0x8), ("HB_SHIFT", 0xa),
                      ("HB_ROWS", 0xb), ("HB_CUR_COL", 0xc), ("HB_Y", 0xe),
                      # _platform_table packs ">HHHH"
                      ("PLAT_Y0", 0x0), ("PLAT_Y1", 0x2), ("PLAT_X0", 0x4), ("PLAT_X1", 0x6),
                      # _platform_sprites packs ">IHHII"
                      ("PSPR_PRESENT", 0x0), ("PSPR_ROWS", 0x4), ("PSPR_COLS", 0x6),
                      ("PSPR_SRC", 0x8), ("PSPR_DST_OFF", 0xc)):
        assert header[name] == off, f"{name}: object.h has {header[name]:#x}, packers use {off:#x}"

    # The object record, likewise encoded positionally by _object — now in joust.h.
    for name, off in (("OBJ_FLAGS", 0x00), ("OBJ_X", 0x02), ("OBJ_Y", 0x04), ("OBJ_VX", 0x06),
                      ("OBJ_VY", 0x08), ("OBJ_ANIM_TIMER", 0x0a), ("OBJ_STEP_TIMER", 0x0b),
                      ("OBJ_FLAP_FRAME", 0x0e), ("OBJ_PREV_DST", 0x14), ("OBJ_EGG_STATE", 0x1e),
                      ("OBJ_EGG_X", 0x20), ("OBJ_EGG_DST", 0x2a), ("OBJ_EGG_SRC", 0x2e),
                      ("OBJ_EGG_ROWS", 0x32), ("OBJ_EGG_SHIFT", 0x33)):
        assert joust_h[name] == off, f"{name}: joust.h has {joust_h[name]:#x}, packers use {off:#x}"
