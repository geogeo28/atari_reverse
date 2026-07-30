"""Differential tests for the drawing/blit layer (src/draw.c)."""
import ctypes
import random
import struct

import pytest

import abi
import emu
import harness
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin tests at the end

ENTRY_FILL_SCREEN = 0x102e2
ENTRY_DRAW_STRING = 0x10700
ENTRY_SELECT_SPRITE_BASE = 0x135f4
ENTRY_PAINT_FLOOR_ROW = 0x175ba
ENTRY_BLIT_PATTERN_ROWS = 0x1369c
ENTRY_BLIT_MASK_WIDE = 0x15098
ENTRY_BLIT_SPRITE_PLANES = 0x1510c
ENTRY_DRAW_OBJECT_DATA = 0x136e8
ENTRY_DRAW_OBJECT_MASK = 0x137bc

A_SCREEN_BASE = 0x10dde   # names.txt: screen_base
A_OBJECT_TABLE = 0x10f36  # names.txt: object_table — player 1's slot, and the table's base
A_PLAYER2 = 0x10f84       # names.txt: player2

CELL_BYTES = 8            # bytes per 4-plane cell (mirror of include/joust.h)
SCREEN_BYTES = 0x7d00     # 320x200 at 4 bitplanes: the real framebuffer
SCREEN_ROW_BYTES = 0xa0   # one low-res scanline (mirror of include/joust.h)

# Scratch screen: clear of the program, of abi.STUB/ARG_BLOCK, and far below the staged-file table.
DRAW_SCREEN = 0x50000

# fill_screen and draw_string call subroutines, so the oracle builds real 68000 frames just under
# abi's pre-poked return slot. The candidate is pure C and has no machine stack, so that band is
# dropped from the diff — it is provably scratch (harness._vet_exclude_bands re-checks that it
# reaches past the deepest A7 the run touched and covers no named global). The measured floor is
# ARG_BLOCK - 62 (draw_string, through pos_to_screen); 0x80 leaves headroom while still stopping
# well above abi.STUB at 0x40000, whose poked entry code must stay in the comparison.
CALL_FRAME_BAND = (abi.ARG_BLOCK - 0x80, abi.ARG_BLOCK - 4)


def _sx16(value):
    """A word folded into an address with `adda.w` is SIGN-extended, so 0xff60 means -0xa0."""
    return value - 0x10000 if value & 0x8000 else value


def _seed_rows(pokes, rng, first_row, rows, width):
    """Seed `rows` scanlines of noise under a blit, one poke per row.

    One poke per row rather than a single block spanning the rectangle: the rows are a scanline
    apart but only `width` bytes wide, and a contiguous block would seed the gaps between them too
    — which silently rewrites neighbouring globals when a sprite is deliberately aimed at the
    program's own data (see test_blit_sprite_planes_retests_the_suppressors_every_row).
    """
    for row in range(rows):
        pokes[(first_row + row * SCREEN_ROW_BYTES) & 0xffffffff] = rng.randbytes(width)


def _assert_record_zeroed(final, record, fields, where):
    """Row 0 of a blit aimed at its own record must have cleared each field it covered.

    Shared by the three read-once tests below. Each of those stages the listed fields NON-zero and
    masks row 0 with zeros, so "reads zero afterwards" is what proves a per-row re-read would see a
    different value — without it the test would pass against a re-reading reconstruction too.
    """
    for field in fields:
        assert not any(bytes(final)[record + field:record + field + 2]), (
            f"{where}: row 0 left the record's field at +{field:#x} intact — nothing is pinned")


harness._lib.g_fill_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_fill_screen.restype = None
harness._lib.g_select_sprite_base.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_select_sprite_base.restype = ctypes.c_uint32
harness._lib.g_paint_floor_row.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_paint_floor_row.restype = None
harness._lib.g_blit_pattern_rows.argtypes = ([ctypes.POINTER(ctypes.c_uint8)]
                                             + [ctypes.c_uint32] * 5)
harness._lib.g_blit_pattern_rows.restype = None
harness._lib.g_blit_mask_wide.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_blit_mask_wide.restype = None
harness._lib.g_blit_sprite_planes.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_blit_sprite_planes.restype = None


# ---------------------------------------------------------------- fill_screen @ 0x102e2

# `move.l #$fa0,d3` + `dbf` = 4001 cells of 8 bytes = 32008, eight PAST the framebuffer. Pinned
# outright by test_fill_screen_overruns_the_framebuffer below.
FILL_SCREEN_BYTES = 0xfa1 * CELL_BYTES


def _fill_screen_pokes(screen_base, colour, seed):
    rng = random.Random(seed)
    pokes = abi.stack_call_pokes(ENTRY_FILL_SCREEN)
    pokes[A_SCREEN_BASE] = screen_base.to_bytes(4, "big")
    # Noise under the whole fill (overrun included): a candidate that stopped at the framebuffer's
    # last byte would leave noise where the original left pattern.
    pokes[screen_base] = rng.randbytes(FILL_SCREEN_BYTES)
    pokes[abi.ARG_BLOCK] = struct.pack(">H", colour)
    return pokes


def _fill_screen_case(colour, seed, poison=False):
    pokes = _fill_screen_pokes(DRAW_SCREEN, colour, seed)
    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: lib.g_fill_screen(buf, abi.ARG_BLOCK),
                            exclude=[CALL_FRAME_BAND], poison=poison)
    assert not diffs, f"colour={colour:#x} seed={seed}\n{report(diffs)}"


# The colour reaches make_fill_pattern unchanged, where only bit 0 survives (see src/fill.c), so
# these pin the forwarding rather than the pattern: 0x100/0x101 in particular separate the `move.w`
# the original does from a byte read, which would pick up the high half instead.
_FILL_SCREEN_COLOURS = (0, 1, 2, 3, 0xff, 0x100, 0x101, 0x7fff, 0x8000, 0xfffe, 0xffff)


@pytest.mark.parametrize("colour", _FILL_SCREEN_COLOURS)
def test_fill_screen_colours(colour):
    _fill_screen_case(colour, seed=colour)


def test_fill_screen_attribution():
    # poison=True proves the candidate really writes every cell, rather than matching because the
    # seeded noise happened to agree.
    for colour in (0, 1):
        _fill_screen_case(colour, seed=0x900 + colour, poison=True)


def test_fill_screen_overruns_the_framebuffer():
    """Pin the shipped overrun: 4001 cells are written where the screen holds 4000.

    Harmless on the real machine — Physbase is 256-byte aligned, so the eight bytes past the screen
    are slack — and reproduced because the differential compares them like any other byte. Stated
    outright so the reason for FILL_SCREEN_BYTES is on the record rather than buried in a diff.
    """
    pokes = _fill_screen_pokes(DRAW_SCREEN, colour=1, seed=0)
    _, writes, _ = emu.run(harness.make_image(pokes), abi.STUB)
    screen_writes = [a for a in writes if DRAW_SCREEN <= a < DRAW_SCREEN + 0x10000]
    assert min(screen_writes) == DRAW_SCREEN
    # Measured against the FRAMEBUFFER, not against FILL_SCREEN_BYTES — comparing the seeding
    # constant with itself would state the overrun rather than observe it.
    assert max(screen_writes) - DRAW_SCREEN + 1 == SCREEN_BYTES + CELL_BYTES


def test_fill_screen_starts_at_screen_base():
    """The fill follows screen_base, so a moved screen must move the whole 32008-byte run."""
    for offset in (0, CELL_BYTES, 0x2000):
        pokes = _fill_screen_pokes(DRAW_SCREEN + offset, colour=1, seed=offset)
        diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                                lambda lib, buf: lib.g_fill_screen(buf, abi.ARG_BLOCK),
                                exclude=[CALL_FRAME_BAND])
        assert not diffs, f"screen_base offset {offset:#x}\n{report(diffs)}"


# ---------------------------------------------------------------- select_sprite_base @ 0x135f4

# The three rider sprite sets, and the offset to each one's mirrored (facing-right) half.
SPRITE_SET_PLAYER1, SPRITE_SET_PLAYER2, SPRITE_SET_ENEMY = 0x1c64a, 0x1ebaa, 0x22f4a
SPRITE_SET_FACING = 0x130
FACING_RIGHT_BIT = 15     # btst #15,d0 — a LONGWORD bit test on a data register


def _select_sprite_base_case(object_ptr, flags):
    """Enter the routine directly: it reads no memory and writes none, so its whole output is D1.

    That makes the image diff trivially empty here (it still guards against a candidate that
    scribbles); the contract under test is the register, compared against the reconstruction's
    return value the way test_fill.py compares fill_pattern_n's end pointer.
    """
    diffs, info = differential(ENTRY_SELECT_SPRITE_BASE, {"a0": object_ptr, "d0": flags},
                               lambda lib, buf: lib.g_select_sprite_base(object_ptr, flags))
    assert not diffs, f"object={object_ptr:#x} flags={flags:#x}\n{report(diffs)}"
    assert info["ret"] == info["regs"]["d1"], (
        f"object={object_ptr:#x} flags={flags:#x}: sprite base "
        f"cand={info['ret']:#x} oracle={info['regs']['d1']:#x}")


# Object pointers: the two identities that own a sprite set, their immediate neighbours (the
# original compares the FULL longword, so one byte off must fall through to the enemy set), a real
# enemy slot, and 0.
_SPRITE_OBJECTS = (A_OBJECT_TABLE, A_OBJECT_TABLE - 1, A_OBJECT_TABLE + 1,
                   A_PLAYER2, A_PLAYER2 - 1, A_PLAYER2 + 1,
                   0x10fd2, 0, 0xffffffff)
# Flags: bit 15 on and off, with noise in the bits around it that must not matter — including bit
# 31, which a word-sized test would confuse with bit 15.
_SPRITE_FLAGS = (0, 1, 0x7fff, 0x8000, 0x8001, 0xffff, 0x10000, 0x80000000, 0xffff7fff, 0xffffffff)


@pytest.mark.parametrize("object_ptr", _SPRITE_OBJECTS)
def test_select_sprite_base_identities(object_ptr):
    for flags in _SPRITE_FLAGS:
        _select_sprite_base_case(object_ptr, flags)


def test_select_sprite_base_values():
    """State the three bases and the facing offset outright, so a silent retable is caught here.

    The differential cases above already refuse a wrong answer, but they never say what the right
    one IS — and these four constants are the routine's entire content.
    """
    expected = {(A_OBJECT_TABLE, 0): SPRITE_SET_PLAYER1,
                (A_PLAYER2, 0): SPRITE_SET_PLAYER2,
                (0x10fd2, 0): SPRITE_SET_ENEMY,
                (A_OBJECT_TABLE, 1 << FACING_RIGHT_BIT): SPRITE_SET_PLAYER1 + SPRITE_SET_FACING}
    for (object_ptr, flags), base in expected.items():
        _, _, regs = emu.run(harness.make_image(), ENTRY_SELECT_SPRITE_BASE,
                             {"a0": object_ptr, "d0": flags})
        assert regs["d1"] == base, f"object={object_ptr:#x} flags={flags:#x} -> {regs['d1']:#x}"


def test_select_sprite_base_fuzz():
    rng = random.Random(ENTRY_SELECT_SPRITE_BASE)
    for _ in range(200):
        # Half the draws land on a real object slot so the identity branches stay exercised; a
        # uniform 32-bit pointer would take the enemy fall-through essentially every time.
        object_ptr = (rng.choice(_SPRITE_OBJECTS) if rng.random() < 0.5
                      else rng.randrange(1 << 32))
        _select_sprite_base_case(object_ptr, rng.randrange(1 << 32))


# ---------------------------------------------------------------- paint_floor_row @ 0x175ba

FLOOR_ROW_CELLS = 5       # `moveq #$5,d1` — a fixed count, not an argument
PLANE3_OFFSET = 6         # `or.w d2,6(a1)` — the only word the routine writes per cell
FLOOR_ROW_BYTES = FLOOR_ROW_CELLS * CELL_BYTES


def _floor_row_case(row, pixels, poison=False):
    diffs, _ = differential(ENTRY_PAINT_FLOOR_ROW, {"a1": row, "_pokes": {row: pixels}},
                            lambda lib, buf: lib.g_paint_floor_row(buf, row), poison=poison)
    assert not diffs, f"row={row:#x} pixels={pixels.hex()}\n{report(diffs)}"


def _floor_row_noise(seed):
    return random.Random(seed).randbytes(FLOOR_ROW_BYTES)


# Uniform cell contents, repeated across the row. Zero is the case the routine exists for (colour 0
# becomes colour 8); all-ones is its opposite; the two half patterns separate "plane 3 already set"
# from "some other plane set", which the OR of all four must treat alike.
_FLOOR_ROW_UNIFORM = (b"\x00" * CELL_BYTES,
                      b"\xff" * CELL_BYTES,
                      b"\x00\x00\x00\x00\x00\x00\xff\xff",   # only plane 3 lit
                      b"\xff\xff\x00\x00\x00\x00\x00\x00",   # only plane 0 lit
                      b"\xf0\x0f" * 4)


@pytest.mark.parametrize("cell", _FLOOR_ROW_UNIFORM)
def test_paint_floor_row_uniform(cell):
    _floor_row_case(DRAW_SCREEN, cell * FLOOR_ROW_CELLS)


def test_paint_floor_row_noise():
    for seed in range(16):
        _floor_row_case(DRAW_SCREEN, _floor_row_noise(seed))


def test_paint_floor_row_attribution():
    # An all-ones row leaves plane 3 unchanged in every cell, so a candidate that skipped cells
    # would match by coincidence; poisoning the oracle's writes makes the omission show.
    for pixels in (b"\xff" * FLOOR_ROW_BYTES, b"\x00" * FLOOR_ROW_BYTES, _floor_row_noise(0xf100)):
        _floor_row_case(DRAW_SCREEN, pixels, poison=True)


def test_paint_floor_row_writes_only_plane3_of_five_cells():
    """Pin the shape: five cells, and within each one only the plane-3 word.

    This is a repair pass, not a fill — the other three planes are read and never written — and the
    count is baked into the routine rather than passed in, so half a floor row takes two calls.
    """
    pokes = {DRAW_SCREEN: _floor_row_noise(0x175ba)}
    _, writes, _ = emu.run(harness.make_image(pokes), ENTRY_PAINT_FLOOR_ROW, {"a1": DRAW_SCREEN})
    expected = {DRAW_SCREEN + cell * CELL_BYTES + PLANE3_OFFSET + byte
                for cell in range(FLOOR_ROW_CELLS) for byte in (0, 1)}
    assert set(writes) == expected


# ---------------------------------------------------------------- blit_pattern_rows @ 0x1369c

PATTERN_ROWS = 3          # rows at strides 0 / 0xa0 / 0x140, all four planes each
PATTERN_SPAN = 2 * SCREEN_ROW_BYTES + CELL_BYTES   # bytes the three rows reach across


def _pattern_rows_case(dst, plane_select, masks, seed, poison=False):
    pokes = {dst: random.Random(seed).randbytes(PATTERN_SPAN)}
    regs = {"a3": dst, "d2": plane_select, "_pokes": pokes}
    regs.update(zip(("d5", "d6", "d7"), masks))
    diffs, _ = differential(
        ENTRY_BLIT_PATTERN_ROWS, regs,
        lambda lib, buf: lib.g_blit_pattern_rows(buf, dst, plane_select, *masks), poison=poison)
    assert not diffs, (f"planes={plane_select:#x} masks={[hex(m) for m in masks]} seed={seed}\n"
                       + report(diffs))


# One mask per row, so a candidate that fed the wrong row's mask (or reused one) diverges.
_PATTERN_MASKS = ((0xffff, 0x0000, 0xaaaa), (0x8001, 0x7ffe, 0xffff), (0, 0, 0),
                  (0xf0f0, 0x0f0f, 0x00ff))


@pytest.mark.parametrize("plane_select", range(16))
def test_blit_pattern_rows_plane_selects(plane_select):
    """Every combination of the four plane bits: each one picks OR-in or AND-out for its plane."""
    for seed, masks in enumerate(_PATTERN_MASKS):
        _pattern_rows_case(DRAW_SCREEN, plane_select, masks, seed=seed)


def test_blit_pattern_rows_ignores_bits_above_the_four_planes():
    """`btst d4,d2` only ever asks for bits 0..3, so the rest of the longword must not matter."""
    rng = random.Random(0x1369c)
    for plane_select in range(16):
        noisy = plane_select | (rng.randrange(1 << 28) << 4)
        _pattern_rows_case(DRAW_SCREEN, noisy, (0xffff, 0x1234, 0x5678), seed=plane_select)


def test_blit_pattern_rows_masks_are_word_sized():
    """The masks arrive in D5/D6/D7 but every combine is `or.w`/`and.w`: the high halves are junk."""
    rng = random.Random(0x36a4)
    for plane_select in (0, 5, 0xa, 0xf):
        masks = tuple(harness.hi_garbage(rng, low) for low in (0xffff, 0x0f0f, 0x8000))
        _pattern_rows_case(DRAW_SCREEN, plane_select, masks, seed=plane_select)


def test_blit_pattern_rows_attribution():
    # An all-ones mask on a set plane, or an all-zeros mask on a clear one, leaves the destination
    # untouched — so poisoning is what proves the candidate wrote the word at all.
    for plane_select, masks in ((0xf, (0xffff,) * 3), (0, (0,) * 3), (0x9, (0x1234,) * 3)):
        _pattern_rows_case(DRAW_SCREEN, plane_select, masks, seed=plane_select, poison=True)


def test_blit_pattern_rows_writes_all_twelve_plane_words():
    """Both branches write, so every plane of every row is stored whatever the plane select is."""
    pokes = {DRAW_SCREEN: random.Random(0xba5e).randbytes(PATTERN_SPAN)}
    regs = {"a3": DRAW_SCREEN, "d2": 0b0101, "d5": 0x1234, "d6": 0x5678, "d7": 0x9abc}
    _, writes, _ = emu.run(harness.make_image(pokes), ENTRY_BLIT_PATTERN_ROWS, regs)
    expected = {DRAW_SCREEN + row * SCREEN_ROW_BYTES + plane * 2 + byte
                for row in range(PATTERN_ROWS) for plane in range(4) for byte in (0, 1)}
    assert set(writes) == expected


def test_blit_pattern_rows_fuzz():
    rng = random.Random(0x36dc)
    for i in range(200):
        masks = tuple(rng.randrange(1 << 32) for _ in range(PATTERN_ROWS))
        _pattern_rows_case(DRAW_SCREEN, rng.randrange(1 << 32), masks, seed=i)


# ---------------------------------------------------------------- blit_mask_wide @ 0x15098

# The pterodactyl record's fields (mirrors PTERO_* in include/draw.h).
PTERO_DST_BASE, PTERO_SRC, PTERO_SHIFT, PTERO_DST_OFF, PTERO_ROWS = 0x02, 0x06, 0x0a, 0x16, 0x18
PTERO_MASK_OFF = 0x120         # the erase mask sits this far into the sprite set
PTERO_MASK_ROW_BYTES = 8       # two longwords per row
PTERO_RECORD_BYTES = 0x1a
PTERO_DST_CELLS = 3            # the two mask longwords are laid across three screen cells

PTERO_RECORD = 0x60000         # scratch record and sprite set, clear of DRAW_SCREEN's rows
PTERO_SPRITE = 0x62000


def _ptero_record(dst_base, src, shift, dst_off, rows):
    record = bytearray(PTERO_RECORD_BYTES)
    struct.pack_into(">I", record, PTERO_DST_BASE, dst_base)
    struct.pack_into(">I", record, PTERO_SRC, src)
    struct.pack_into(">HH", record, PTERO_SHIFT, shift, 0)
    struct.pack_into(">HH", record, PTERO_DST_OFF, dst_off & 0xffff, rows & 0xffff)
    return bytes(record)


def _bge_rows(rows):
    """Passes a `subq.w #1,dn / bge` row counter makes: the count if positive, none otherwise.

    Shared by blit_mask_wide, blit_sprite_planes and the two ground blitters, which all count rows
    that way — including at 0x8000, where the decrement overflows to +0x7fff but BGE (N == V) still
    fails, so the routine draws nothing.
    """
    return max(rows if rows < 0x8000 else rows - 0x10000, 0)


def _mask_wide_case(shift, rows, seed, dst_off=0, screen_base=DRAW_SCREEN, mask=None, poison=False):
    passes = _bge_rows(rows)
    rng = random.Random(seed)
    pokes = {PTERO_RECORD: _ptero_record(0, PTERO_SPRITE, shift, dst_off, rows),
             A_SCREEN_BASE: screen_base.to_bytes(4, "big"),
             PTERO_SPRITE + PTERO_MASK_OFF: mask if mask is not None
             else rng.randbytes(max(passes, 1) * PTERO_MASK_ROW_BYTES)}
    _seed_rows(pokes, rng, screen_base + _sx16(dst_off), passes, PTERO_DST_CELLS * CELL_BYTES)
    diffs, _ = differential(ENTRY_BLIT_MASK_WIDE, {"a0": PTERO_RECORD, "_pokes": pokes},
                            lambda lib, buf: lib.g_blit_mask_wide(buf, PTERO_RECORD), poison=poison)
    assert not diffs, f"shift={shift:#x} rows={rows:#x} dst_off={dst_off:#x}\n{report(diffs)}"


# Shift/rotate counts, shared by every routine below that takes one in a register: the boundaries
# are 0 (identity), a cell (16), a whole longword (32 — which a rotate returns to identity at and a
# shift clears at), and 0x3f, the top of the count field the 68000 actually reads.
_SHIFT_COUNTS = (0, 1, 4, 8, 15, 16, 17, 24, 31, 32, 33, 47, 63, 64, 0x3f0, 0xffff)


@pytest.mark.parametrize("shift", _SHIFT_COUNTS)
def test_blit_mask_wide_shifts(shift):
    for rows in (1, 2, 5):
        _mask_wide_case(shift, rows, seed=shift * 8 + rows)


def test_blit_mask_wide_row_counts():
    for rows in (1, 2, 3, 8, 0x40):
        _mask_wide_case(shift=5, rows=rows, seed=rows)


def test_blit_mask_wide_draws_nothing_for_a_non_positive_count():
    """`subq.w #1,d7 / bge` up front: 0 and every negative count fall straight through to the rts.

    0x8000 is the case a naive "decrement, then test the sign of the result" reading gets wrong —
    the decrement overflows to +0x7fff, but BGE tests N == V and so still fails.
    """
    for rows in (0, 1, 0xffff, 0x8000, 0x8001, 0xfffe):
        pokes = {PTERO_RECORD: _ptero_record(0, PTERO_SPRITE, 3, 0, rows),
                 A_SCREEN_BASE: DRAW_SCREEN.to_bytes(4, "big"),
                 PTERO_SPRITE + PTERO_MASK_OFF: b"\x00" * PTERO_MASK_ROW_BYTES,
                 DRAW_SCREEN: b"\xff" * (PTERO_DST_CELLS * CELL_BYTES)}
        _, writes, _ = emu.run(harness.make_image(pokes), ENTRY_BLIT_MASK_WIDE, {"a0": PTERO_RECORD})
        assert bool(writes) == (_bge_rows(rows) > 0), f"rows={rows:#x} wrote {len(writes)}"
        _mask_wide_case(shift=3, rows=rows, seed=rows)


def test_blit_mask_wide_destination_is_base_plus_screen_plus_signed_offset():
    """dst = record.dst_base + screen_base + dst_off, the last folded in with a SIGN-extended adda.w."""
    for dst_off in (0, CELL_BYTES, SCREEN_ROW_BYTES, 0x7fff & ~1, 0x10000 - SCREEN_ROW_BYTES,
                    0x10000 - 2 * SCREEN_ROW_BYTES):
        base = DRAW_SCREEN + 0x1000    # headroom so a negative offset still lands in the scratch
        _mask_wide_case(shift=7, rows=3, seed=dst_off, dst_off=dst_off, screen_base=base)


def test_blit_mask_wide_attribution():
    # An all-ones mask leaves the destination untouched, so only poisoning proves the candidate
    # wrote every plane of every cell.
    for shift in (0, 4, 16):
        _mask_wide_case(shift, rows=3, seed=shift,
                        mask=b"\xff" * (3 * PTERO_MASK_ROW_BYTES), poison=True)


def test_blit_mask_wide_masks_the_middle_cell_twice_per_row():
    """Cell 1 takes the left longword's LOW half and the right longword's HIGH half.

    Both are plain ANDs, so their order is invisible on a normal draw; it becomes observable when
    the mask source lies inside the rectangle being masked, which is what this builds. The RECORD is
    a separate matter and lies outside this rectangle — see the read-once test below.
    """
    rows = 4
    overlap_src = DRAW_SCREEN - PTERO_MASK_OFF   # so the mask rows ARE the destination's own bytes
    pokes = {PTERO_RECORD: _ptero_record(0, overlap_src, 6, 0, rows),
             A_SCREEN_BASE: DRAW_SCREEN.to_bytes(4, "big"),
             DRAW_SCREEN: random.Random(0x15098).randbytes(
                 (rows - 1) * SCREEN_ROW_BYTES + PTERO_DST_CELLS * CELL_BYTES)}
    diffs, _ = differential(ENTRY_BLIT_MASK_WIDE, {"a0": PTERO_RECORD, "_pokes": pokes},
                            lambda lib, buf: lib.g_blit_mask_wide(buf, PTERO_RECORD))
    assert not diffs, "mask read back out of the rectangle it is masking\n" + report(diffs)


# Aim the erase at its OWN record. The rectangle spans PTERO_DST_CELLS cells (24 bytes) and the
# record is PTERO_RECORD_BYTES (26), so where row 0 lands decides which fields it reaches: starting
# 2 bytes in covers +0x02..+0x19, i.e. every field the routine reads and nothing but the two unused
# leading bytes left over.
MASK_WIDE_SELF_OVERLAP = 0x02
_MASK_WIDE_RECORD_FIELDS = (PTERO_DST_BASE, PTERO_SRC, PTERO_SHIFT, PTERO_DST_OFF, PTERO_ROWS)
MASK_WIDE_SELF_DST_OFF = 0x10   # non-zero, so zeroing it MOVES the destination


def test_blit_mask_wide_reads_its_record_once():
    """Pin "every field is read once, before the loop" by masking the RECORD with row 0.

    Row 0's two mask longwords are all zeros, so every field comes out zeroed; rows 1.. then run
    over ordinary noise. A reconstruction that re-read any field per row would take a shift of 0, a
    source of 0, a destination of 0 or a row count of 0 from row 1 on, and diverge — none of which
    the middle-cell test above can see, since its destination overlaps only the mask SOURCE.
    """
    rows, shift = 4, 5
    dst = PTERO_RECORD + MASK_WIDE_SELF_OVERLAP
    rng = random.Random(ENTRY_BLIT_MASK_WIDE)
    pokes = {A_SCREEN_BASE: (0).to_bytes(4, "big"),
             PTERO_SPRITE + PTERO_MASK_OFF: bytes(PTERO_MASK_ROW_BYTES)
                                            + rng.randbytes((rows - 1) * PTERO_MASK_ROW_BYTES)}
    # Rows 1.. only: row 0 IS the record, and seeding it would bury the fields under test.
    _seed_rows(pokes, rng, dst + SCREEN_ROW_BYTES, rows - 1, PTERO_DST_CELLS * CELL_BYTES)
    pokes[PTERO_RECORD] = _ptero_record(dst - MASK_WIDE_SELF_DST_OFF, PTERO_SPRITE, shift,
                                        MASK_WIDE_SELF_DST_OFF, rows)

    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_BLIT_MASK_WIDE, {"a0": PTERO_RECORD})
    _assert_record_zeroed(final, PTERO_RECORD, _MASK_WIDE_RECORD_FIELDS, "blit_mask_wide")

    diffs, _ = differential(ENTRY_BLIT_MASK_WIDE, {"a0": PTERO_RECORD, "_pokes": pokes},
                            lambda lib, buf: lib.g_blit_mask_wide(buf, PTERO_RECORD))
    assert not diffs, "erase aimed at its own record\n" + report(diffs)


def test_blit_mask_wide_fuzz():
    rng = random.Random(0x50b6)
    for i in range(150):
        _mask_wide_case(rng.randrange(1 << 16), rng.randrange(1, 12), seed=i)


# ---------------------------------------------------------------- blit_sprite_planes @ 0x1510c

# The staged sprite the pterodactyl's draw pass reads (names.txt / include/draw.h).
A_DRAW_DST = 0x10de8          # .l
A_DRAW_SRC = 0x10df0          # .l
A_DRAW_SHIFT = 0x10df4        # .w here (a BYTE to the rider blitter — see include/draw.h)
A_DRAW_ROWS = 0x10df6         # .w here, likewise
A_DRAW_DST_OFF = 0x10df8      # .w, folded in with a SIGN-extended adda.w
# The three are consecutive words, which is why one `>HHH` poke at A_DRAW_SHIFT stages all of them.
A_DRAW_CLIP_CELL0 = 0x10d0e   # .b, and the two after it: nonzero suppresses the leading cell
                              # (dst + 0), the middle one (dst + 8) and the trailing one (dst + 16)
                              # respectively. They are consecutive, so one poke stages all three.

PTERO_SRC_ROW_BYTES = 0x18    # adda.w #$18,a1 — 12 words per row, of which 8 are read
PTERO_SRC_ROW_READ = 0x12     # `move.l 14(a1)` reaches two bytes past the eight it uses


def _sprite_planes_pokes(src, dst, shift, rows, clips, seed, dst_off=0, screen_base=DRAW_SCREEN,
                         src_data=None):
    passes = _bge_rows(rows)      # the same subq.w/bge counter
    rng = random.Random(seed)
    pokes = {A_SCREEN_BASE: screen_base.to_bytes(4, "big"),
             A_DRAW_SRC: src.to_bytes(4, "big"),
             A_DRAW_DST: dst.to_bytes(4, "big"),
             A_DRAW_SHIFT: struct.pack(">HHH", shift, rows & 0xffff, dst_off & 0xffff),
             src: src_data if src_data is not None
             else rng.randbytes(max(passes - 1, 0) * PTERO_SRC_ROW_BYTES + PTERO_SRC_ROW_READ)}
    _seed_rows(pokes, rng, screen_base + _sx16(dst_off) + dst, passes,
               PTERO_DST_CELLS * CELL_BYTES)
    # The suppressors go in LAST: a destination aimed at them (the retest case below) would
    # otherwise be seeded with noise on top of the values under test.
    pokes[A_DRAW_CLIP_CELL0] = bytes(clips)
    return pokes


def _sprite_planes_case(shift, rows, clips=(0, 0, 0), seed=0, poison=False, **kwargs):
    pokes = _sprite_planes_pokes(PTERO_SPRITE, 0, shift, rows, clips, seed, **kwargs)
    diffs, _ = differential(ENTRY_BLIT_SPRITE_PLANES, {"_pokes": pokes},
                            lambda lib, buf: lib.g_blit_sprite_planes(buf), poison=poison)
    assert not diffs, f"shift={shift:#x} rows={rows:#x} clips={clips}\n{report(diffs)}"


@pytest.mark.parametrize("shift", _SHIFT_COUNTS)
def test_blit_sprite_planes_shifts(shift):
    for rows in (1, 2, 5):
        _sprite_planes_case(shift, rows, seed=shift * 8 + rows)


@pytest.mark.parametrize("clips", [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)])
def test_blit_sprite_planes_clip_combinations(clips):
    """Each suppressor drops its own cell and only its own, in every combination."""
    for shift in (0, 6, 16):
        _sprite_planes_case(shift, rows=3, clips=clips, seed=shift)


def test_blit_sprite_planes_suppressors_are_any_nonzero_byte():
    """`tst.b` + `bne`: the byte is a flag, not a count — 0x80 and 0xff suppress like 1 does."""
    for value in (1, 2, 0x7f, 0x80, 0xff):
        _sprite_planes_case(shift=5, rows=2, clips=(value, 0, value), seed=value)
        _sprite_planes_case(shift=5, rows=2, clips=(0, value, 0), seed=value)


def test_blit_sprite_planes_row_counts():
    for rows in (0, 1, 2, 3, 0x20, 0xffff, 0x8000, 0x8001):
        _sprite_planes_case(shift=9, rows=rows, seed=rows)


def test_blit_sprite_planes_destination_offset_is_sign_extended():
    for dst_off in (0, CELL_BYTES, SCREEN_ROW_BYTES, 0x10000 - SCREEN_ROW_BYTES,
                    0x10000 - 2 * SCREEN_ROW_BYTES):
        _sprite_planes_case(shift=7, rows=3, seed=dst_off, dst_off=dst_off,
                            screen_base=DRAW_SCREEN + 0x1000)


def test_blit_sprite_planes_attribution():
    # An all-ones source leaves an all-ones destination unchanged, so poisoning is what proves the
    # candidate wrote every plane of all three cells.
    ones = b"\xff" * (3 * PTERO_SRC_ROW_BYTES + PTERO_SRC_ROW_READ)
    for shift in (0, 4, 16):
        _sprite_planes_case(shift, rows=3, seed=shift, poison=True, src_data=ones)


# Where the source starts relative to the destination, for the self-overdraw case below. What makes
# the third pass's phase order observable is a delta that puts a trailing word it has yet to read
# (src+8..15) under a word it has already written (dst+16..23) — that is 2, 4 and 6. Delta 8, the
# obvious choice, is blind: there the trailing words ARE the third cell, so reading before or
# between the writes produces the same memory.
_SPRITE_PLANES_OVERDRAW_DELTAS = (0, 2, 4, 6, 8, 10, 16)
# And a shift of at least 9. The word a pass writes carries the source's low `shift` bits up into
# positions 16-shift..15, while the read that follows only looks at bits 0..shift-1 — so below 9
# the two never touch and the overdraw, though real, changes nothing. (Found the hard way: a sweep
# fixed at shift 6 passed against a reconstruction that interleaved the reads.)
_SPRITE_PLANES_OVERDRAW_SHIFTS = (6, 9, 12, 16, 24)


@pytest.mark.parametrize("delta", _SPRITE_PLANES_OVERDRAW_DELTAS)
def test_blit_sprite_planes_reads_every_pair_before_it_writes_anything(delta):
    """Pin the phase order by drawing the sprite over its own source rows.

    The original loads all four leading/trailing pairs, writes the middle cell, then the leading
    one, and only then re-reads the trailing words — all four of them — before writing the third
    cell. A reconstruction that interleaved any of those reads with the writes, or that reused the
    pair it already held, reads bytes the original had not yet written.
    """
    rows = 4
    src = DRAW_SCREEN + delta             # the source sits inside the rectangle being drawn on
    for shift in _SPRITE_PLANES_OVERDRAW_SHIFTS:
        rng = random.Random(0x5136 + delta * 0x100 + shift)
        pokes = _sprite_planes_pokes(src, 0, shift, rows, clips=(0, 0, 0), seed=0x1510c)
        # Re-keyed after the helper's own pokes: make_image applies them in insertion order, and
        # the helper seeds the destination rows AFTER the source, so assigning pokes[src] in place
        # would leave the row-0 noise sitting on top of the sprite's first row.
        pokes.pop(src, None)
        pokes[src] = rng.randbytes((rows - 1) * PTERO_SRC_ROW_BYTES + PTERO_SRC_ROW_READ)

        diffs, _ = differential(ENTRY_BLIT_SPRITE_PLANES, {"_pokes": pokes},
                                lambda lib, buf: lib.g_blit_sprite_planes(buf))
        assert not diffs, (f"sprite drawn over its own source rows at +{delta}, shift {shift}\n"
                           + report(diffs))


def test_blit_sprite_planes_retests_the_suppressors_every_row():
    """Pin that each suppressor is read once per row — by drawing the sprite ONTO them.

    The three bytes are consecutive at 0x10d0e, so a destination at 0x10d00 puts plane 3 of the
    middle cell exactly on top of clip_cell0/clip_cell1 and the trailing cell on clip_cell2. Row 0
    therefore ORs them non-zero and rows 1..2 must find themselves suppressed — which a
    reconstruction that hoisted the tests out of the row loop, or re-read them per plane, gets
    wrong. screen_base is 0 so the destination is exactly draw_dst.
    """
    rows = 3
    dst = A_DRAW_CLIP_CELL0 - 14          # so dst+14 (middle cell, plane 3) lands on clip_cell0
    pokes = _sprite_planes_pokes(PTERO_SPRITE, dst, shift=4, rows=rows, clips=(0, 0, 0),
                                 seed=0x510c, screen_base=0)
    pokes[PTERO_SPRITE] = b"\xff" * ((rows - 1) * PTERO_SRC_ROW_BYTES + PTERO_SRC_ROW_READ)
    diffs, _ = differential(ENTRY_BLIT_SPRITE_PLANES, {"_pokes": pokes},
                            lambda lib, buf: lib.g_blit_sprite_planes(buf))
    assert not diffs, "sprite drawn onto its own suppressor bytes\n" + report(diffs)


# Aiming the pterodactyl's draw pass at the draw_* globals themselves. They are consecutive from
# A_DRAW_DST, so a three-cell rectangle there puts row 0's leading cell on draw_dst, its middle cell
# on draw_src / draw_shift / draw_rows and its trailing cell on draw_dst_off.
#
# The eight source words of row 0 are chosen, for SELF_DRAW_SHIFT = 4, to move every one of those
# fields: the leading cell receives w[p] >> 4, the middle cell ((w[p] & 0xf) << 12) | (w[p+4] >> 4),
# and the trailing cell (w[p+4] & 0xf) << 12. The row count is pushed NEGATIVE rather than larger,
# so a reconstruction that re-read it stops after row 0 instead of running away down the image.
SELF_DRAW_SHIFT, SELF_DRAW_ROWS, SELF_DRAW_DST_OFF = 4, 3, 0x10
_SELF_DRAW_ROW0 = (0x0000, 0x0020, 0x0020, 0x0008, 0x0001, 0x0020, 0x0020, 0x0000)
SELF_DRAW_SET_BIT = 0x0002      # ORed into draw_dst, draw_src and draw_shift
SELF_DRAW_ROWS_BIT = 0x8000     # ORed into draw_rows: 3 becomes a negative count
SELF_DRAW_OFF_BIT = 0x1000      # ORed into draw_dst_off


def test_blit_sprite_planes_reads_the_draw_globals_once():
    """Pin that draw_dst / draw_src / draw_shift / draw_rows / draw_dst_off are read ONCE — by
    drawing the sprite ONTO them.

    Row 0 ORs a chosen pattern over all five, so from row 1 a reconstruction that re-read any of
    them would use a different source, a different destination, a different shift, or no rows at
    all. The suppressor test above aims at 0x10d0e and cannot see any of that.
    """
    dst_addr = A_DRAW_DST                      # the rectangle starts on the globals block itself
    rng = random.Random(ENTRY_BLIT_SPRITE_PLANES)
    source = bytearray(struct.pack(">8H", *_SELF_DRAW_ROW0))
    source += bytes(PTERO_SRC_ROW_BYTES - len(source))          # pad row 0 out to its stride
    source += rng.randbytes((SELF_DRAW_ROWS - 1) * PTERO_SRC_ROW_BYTES + PTERO_SRC_ROW_READ)
    pokes = {A_SCREEN_BASE: (0).to_bytes(4, "big"),
             A_DRAW_CLIP_CELL0: bytes(3),                       # no cell suppressed
             PTERO_SPRITE: bytes(source)}
    # Rows 1.. only: row 0 IS the globals block, and seeding it would bury the staged values.
    _seed_rows(pokes, rng, dst_addr + SCREEN_ROW_BYTES, SELF_DRAW_ROWS - 1,
               PTERO_DST_CELLS * CELL_BYTES)
    pokes[A_DRAW_DST] = struct.pack(">I", dst_addr - SELF_DRAW_DST_OFF)
    pokes[A_DRAW_SRC] = PTERO_SPRITE.to_bytes(4, "big")
    pokes[A_DRAW_SHIFT] = struct.pack(">HHH", SELF_DRAW_SHIFT, SELF_DRAW_ROWS, SELF_DRAW_DST_OFF)

    # (format, value staged, bit row 0 must OR in). The bit has to be CLEAR in the staged value, or
    # a per-row re-read would read back what it already had and this would pin nothing — so that is
    # checked too, rather than left to the reader to confirm.
    moved = {A_DRAW_DST: (">I", dst_addr - SELF_DRAW_DST_OFF, SELF_DRAW_SET_BIT),
             A_DRAW_SRC: (">I", PTERO_SPRITE, SELF_DRAW_SET_BIT),
             A_DRAW_SHIFT: (">H", SELF_DRAW_SHIFT, SELF_DRAW_SET_BIT),
             A_DRAW_ROWS: (">H", SELF_DRAW_ROWS, SELF_DRAW_ROWS_BIT),
             A_DRAW_DST_OFF: (">H", SELF_DRAW_DST_OFF, SELF_DRAW_OFF_BIT)}
    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_BLIT_SPRITE_PLANES)
    for addr, (fmt, staged, bit) in moved.items():
        assert not staged & bit, (
            f"{harness.label(addr)} is staged with {bit:#x} already set — row 0 would move nothing")
        got = struct.unpack_from(fmt, bytes(final), addr)[0]
        assert got == staged | bit, (
            f"row 0 left {harness.label(addr)} at {got:#x}, not {staged | bit:#x} — a per-row "
            f"re-read would see no difference there")

    diffs, _ = differential(ENTRY_BLIT_SPRITE_PLANES, {"_pokes": pokes},
                            lambda lib, buf: lib.g_blit_sprite_planes(buf))
    assert not diffs, "sprite drawn onto the draw_* globals it reads\n" + report(diffs)


def test_blit_sprite_planes_fuzz():
    rng = random.Random(0x5130)
    for i in range(150):
        clips = tuple(rng.randrange(256) if rng.random() < 0.3 else 0 for _ in range(3))
        _sprite_planes_case(rng.randrange(1 << 16), rng.randrange(1, 12), clips=clips, seed=i)


# ------------------------------------ blit_sprite_mask @ 0x17752 / blit_sprite @ 0x177a2

# The ground-animation record both routines read through A5 (mirrors SPR_* in include/draw.h).
SPR_SRC, SPR_DST_OFF, SPR_SHIFT, SPR_CELL_SELECT = 0x00, 0x04, 0x08, 0x0a
SPR_MASK_OFF = 0x90            # the AND mask sits this far into the sprite set
SPR_MASK_ROW_BYTES = 4         # `move.l (a3)+` — one rotated longword per row
SPR_DATA_ROW_BYTES = 8         # `adda.w #$8,a1` — four plane words per row
SPR_DATA_ROW_READ = 0x0a       # `move.l 6(a1)` reaches two bytes past the eight it uses
SPR_RECORD_BYTES = 0x0c
SPR_DST_CELLS = 2              # the rotated mask covers the leading cell and the trailing one

SPR_RECORD = 0x64000
SPR_SPRITE = 0x66000

# Both routines take the row count in D7 and read the same record, so every case runs against both.
GROUND_BLITS = {"blit_sprite_mask": 0x17752, "blit_sprite": 0x177a2}

for _name in GROUND_BLITS:
    getattr(harness._lib, "g_" + _name).argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                                    ctypes.c_uint32, ctypes.c_uint32]
    getattr(harness._lib, "g_" + _name).restype = None


def _spr_record(src, dst_off, shift, cell_select):
    record = bytearray(SPR_RECORD_BYTES)
    struct.pack_into(">IIHH", record, 0, src, dst_off, shift, cell_select & 0xffff)
    return bytes(record)


def _spr_pokes(shift, rows, cell_select, seed, src=SPR_SPRITE, dst_off=0,
               screen_base=DRAW_SCREEN, data=None):
    passes = _bge_rows(rows & 0xffff)     # the same subq.w/bge counter as the pterodactyl
    rng = random.Random(seed)
    pokes = {SPR_RECORD: _spr_record(src, dst_off, shift, cell_select),
             A_SCREEN_BASE: screen_base.to_bytes(4, "big"),
             src + SPR_MASK_OFF: rng.randbytes(max(passes, 1) * SPR_MASK_ROW_BYTES)}
    # The colour data is seeded for BOTH routines even though only blit_sprite reads it: leaving it
    # zero would make an erase pass that wrongly ORed the data in indistinguishable from one that
    # did not, since ORing zeros changes nothing.
    pokes[src] = data if data is not None else rng.randbytes(
        max(passes - 1, 0) * SPR_DATA_ROW_BYTES + SPR_DATA_ROW_READ)
    _seed_rows(pokes, rng, screen_base + dst_off, passes, SPR_DST_CELLS * CELL_BYTES)
    return pokes


def _spr_case(name, shift, rows, cell_select, seed, poison=False, **kwargs):
    pokes = _spr_pokes(shift, rows, cell_select, seed, **kwargs)
    diffs, _ = differential(GROUND_BLITS[name], {"a5": SPR_RECORD, "d7": rows, "_pokes": pokes},
                            lambda lib, buf: getattr(lib, "g_" + name)(buf, SPR_RECORD, rows),
                            poison=poison)
    assert not diffs, (f"{name} shift={shift:#x} rows={rows:#x} select={cell_select:#x}\n"
                       + report(diffs))


@pytest.mark.parametrize("name", GROUND_BLITS)
@pytest.mark.parametrize("shift", _SHIFT_COUNTS)
def test_ground_blit_shifts(name, shift):
    for rows in (1, 2, 5):
        _spr_case(name, shift, rows, cell_select=0, seed=shift * 8 + rows)


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_cell_select_is_a_signed_low_byte(name):
    """`tst.b d5` twice — `blt` skips the trailing cell, `bgt` the leading one, so 0 draws both.

    The field is a word but only its low byte is tested, and as a SIGNED byte: 0x80..0xff pick the
    leading cell alone. The high byte is swept alongside to prove it is never looked at.
    """
    for low in (0, 1, 0x7f, 0x80, 0xc0, 0xff):
        for high in (0, 0x7f, 0x80, 0xff):
            _spr_case(name, shift=5, rows=3, cell_select=(high << 8) | low, seed=low * 4 + high)


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_row_counts(name):
    for rows in (0, 1, 2, 3, 12, 0xffff, 0x8000, 0x8001):
        _spr_case(name, shift=9, rows=rows, cell_select=0, seed=rows)


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_row_count_high_half_ignored(name):
    """The count arrives in D7 as a longword but `subq.w` reads the word: garbage above it is junk."""
    rng = random.Random(0x776a)
    for low in (1, 2, 5, 0):
        _spr_case(name, shift=4, rows=harness.hi_garbage(rng, low), cell_select=0, seed=low)


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_attribution(name):
    # An all-ones mask over an all-ones destination changes nothing, so poisoning is what proves
    # the candidate wrote every plane of both cells.
    for cell_select in (0, 1, 0xff):
        _spr_case(name, shift=6, rows=3, cell_select=cell_select, seed=cell_select, poison=True,
                  data=b"\x00" * (2 * SPR_DATA_ROW_BYTES + SPR_DATA_ROW_READ))


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_reads_the_row_before_it_writes_it(name):
    """Draw the sprite over its own data rows: every read of a row happens before any write of it.

    blit_sprite in particular masks and then ORs the same four words, and takes its next row's
    plane words out of memory the previous row has already been drawn on — so a reconstruction
    that re-read the data after the AND pass, or that ORed before masking, diverges here.
    """
    rows = 5
    # src == dst, so data row r lands on bytes row r-1 has already masked and ORed.
    pokes = _spr_pokes(shift=6, rows=rows, cell_select=0, seed=0x77a2, src=DRAW_SCREEN)
    diffs, _ = differential(GROUND_BLITS[name], {"a5": SPR_RECORD, "d7": rows, "_pokes": pokes},
                            lambda lib, buf: getattr(lib, "g_" + name)(buf, SPR_RECORD, rows))
    assert not diffs, f"{name} drawn over its own source rows\n{report(diffs)}"


@pytest.mark.parametrize("name", GROUND_BLITS)
def test_ground_blit_destination_is_screen_base_plus_a_full_longword_offset(name):
    """dst = screen_base + record.dst_off, added with `adda.l` — a full longword, not a word."""
    base = DRAW_SCREEN + 0x1000     # headroom so a negative offset still lands in the scratch
    for dst_off in (0, CELL_BYTES, SCREEN_ROW_BYTES, 0x8000, -SCREEN_ROW_BYTES & 0xffffffff):
        _spr_case(name, shift=7, rows=3, cell_select=0, seed=dst_off & 0xffff,
                  dst_off=dst_off, screen_base=base)


# Aiming a ground blit at its OWN record, whose 0x0c bytes fit inside the two-cell (0x10) rectangle.
# Row 0's mask — and, for blit_sprite, its colour data — is all zeros, so every field it reaches
# comes out zeroed. cell_select decides how much that is, and is itself one of the fields:
#   0 draws both cells, so row 0 covers the whole record and moves src, dst_off and shift;
#   1 draws the trailing cell alone, reaching shift and cell_select — and zeroing cell_select is
#     what makes a re-reading reconstruction draw BOTH cells from row 1 on.
_GROUND_RECORD_MOVED = {0: (SPR_SRC, SPR_DST_OFF, SPR_SHIFT),
                        1: (SPR_SHIFT, SPR_CELL_SELECT)}
GROUND_SELF_SHIFT = 5


@pytest.mark.parametrize("name", GROUND_BLITS)
@pytest.mark.parametrize("cell_select", _GROUND_RECORD_MOVED)
def test_ground_blit_reads_its_record_once(name, cell_select):
    """Pin that src / dst_off / shift / cell_select are read ONCE, by masking the RECORD with row 0.

    Rows 1.. then run over ordinary noise, so a reconstruction that re-read any field per row would
    take a source of 0, a destination of 0, a rotate of 0 or a different pair of cells from row 1
    on. The self-overdraw test above aims at the sprite's data rows and cannot see any of that.
    """
    rows = 4
    rng = random.Random(GROUND_BLITS[name] + cell_select)
    pokes = {A_SCREEN_BASE: (0).to_bytes(4, "big"),
             SPR_SPRITE + SPR_MASK_OFF: bytes(SPR_MASK_ROW_BYTES)
                                        + rng.randbytes((rows - 1) * SPR_MASK_ROW_BYTES),
             SPR_SPRITE: bytes(SPR_DATA_ROW_BYTES)
                         + rng.randbytes((rows - 2) * SPR_DATA_ROW_BYTES + SPR_DATA_ROW_READ)}
    # Rows 1.. only: row 0 IS the record, and seeding it would bury the fields under test.
    _seed_rows(pokes, rng, SPR_RECORD + SCREEN_ROW_BYTES, rows - 1, SPR_DST_CELLS * CELL_BYTES)
    pokes[SPR_RECORD] = _spr_record(SPR_SPRITE, SPR_RECORD, GROUND_SELF_SHIFT, cell_select)

    final, _, _ = emu.run(harness.make_image(pokes), GROUND_BLITS[name],
                          {"a5": SPR_RECORD, "d7": rows})
    _assert_record_zeroed(final, SPR_RECORD, _GROUND_RECORD_MOVED[cell_select], name)

    diffs, _ = differential(GROUND_BLITS[name], {"a5": SPR_RECORD, "d7": rows, "_pokes": pokes},
                            lambda lib, buf: getattr(lib, "g_" + name)(buf, SPR_RECORD, rows))
    assert not diffs, f"{name} aimed at its own record, cell_select={cell_select}\n{report(diffs)}"


GROUND_FUZZ_CHUNKS = 2


def _ground_fuzz_cases():
    rng = random.Random(0x77bc)                  # seeded ONCE — every chunk replays this stream
    for i in range(200):
        yield i, rng.randrange(1 << 16), rng.randrange(1, 12), rng.randrange(1 << 16)


@pytest.mark.parametrize("name", GROUND_BLITS)
@pytest.mark.parametrize("chunk", range(GROUND_FUZZ_CHUNKS))
def test_ground_blit_fuzz(chunk, name):
    for i, shift, rows, cell_select in _ground_fuzz_cases():
        if i % GROUND_FUZZ_CHUNKS == chunk:
            _spr_case(name, shift, rows, cell_select, seed=i)


# ------------------------------------ draw_object_data @ 0x136e8 / draw_object_mask @ 0x137bc

A_DRAW_HALF_SELECT = 0x10dc2   # .b — bit1 skips the leading pass, bit0 the wrap column
A_PLAYFIELD_BOTTOM = 0x10d60   # .l — screen address of the lava line

# Object-record fields (mirrors OBJ_* in include/draw.h).
OBJ_FLAGS, OBJ_X = 0x00, 0x02
OBJ_PREV_X, OBJ_PREV_DST, OBJ_PREV_SRC, OBJ_PREV_ROWS, OBJ_PREV_SHIFT = 0x10, 0x14, 0x18, 0x1c, 0x1d
OBJ_FLAG_IN_LAVA = 0x0100
OBJ_RECORD_BYTES = 0x20

SPRITE_SRC_ROW_BYTES = 0x10    # two cells of four plane words per sprite row
SPRITE_WRAP_X = 0x130          # from this x on, the wrap column is pulled back one scanline
HALF_SELECT_SKIP_LEADING = 0x02
HALF_SELECT_SKIP_WRAP = 0x01

RIDER_OBJECT = 0x68000
RIDER_SPRITE = 0x6a002         # deliberately not longword-round: see the wrap-pass re-read test
RIDER_DST = DRAW_SCREEN + 0x1000    # headroom below it for the wrap column's pulled-back row
NO_LAVA = 0x7fffffff           # a playfield_bottom no destination in these tests can reach
JUNK_BYTE = 0xa5               # poked beside each byte-wide global: a word read would see it

harness._lib.g_draw_object_data.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_object_data.restype = None
harness._lib.g_draw_object_mask.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_object_mask.restype = None


def _passes_byte(count):
    """The `subq.b` loop count both rider passes use: 0 means 256 rows."""
    return ((count - 1) & 0xff) + 1


def _rider_span(rows):
    """Noise across every scanline the two passes can reach, from the wrap column's pulled-back
    row (one scanline above the destination) to the last row of the leading pass."""
    return (rows + 1) * SCREEN_ROW_BYTES + 2 * CELL_BYTES


def _object_data_pokes(shift, rows, x, half_select, seed, flags=1, bottom=NO_LAVA, noise_rows=None):
    passes = _passes_byte(rows)
    noise_rows = passes if noise_rows is None else noise_rows
    rng = random.Random(seed)
    record = bytearray(OBJ_RECORD_BYTES)
    struct.pack_into(">HH", record, OBJ_FLAGS, flags, x & 0xffff)
    pokes = {RIDER_OBJECT: bytes(record),
             A_PLAYFIELD_BOTTOM: (bottom & 0xffffffff).to_bytes(4, "big"),
             A_DRAW_HALF_SELECT: bytes((half_select,)),
             A_DRAW_DST: RIDER_DST.to_bytes(4, "big"),
             A_DRAW_SRC: RIDER_SPRITE.to_bytes(4, "big"),
             # draw_shift and draw_rows are BYTE reads in this routine (they are words to the
             # pterodactyl blitter — see include/draw.h), so the byte beside each is junk: a
             # word-wide reconstruction would take a different shift and a different row count.
             A_DRAW_SHIFT: bytes((shift, JUNK_BYTE, rows, JUNK_BYTE)),
             RIDER_SPRITE: rng.randbytes(max(passes, noise_rows) * SPRITE_SRC_ROW_BYTES),
             RIDER_DST - SCREEN_ROW_BYTES: rng.randbytes(_rider_span(noise_rows))}
    return pokes


def _object_data_case(shift, rows, x=0, half_select=0, seed=0, poison=False, **kwargs):
    pokes = _object_data_pokes(shift, rows, x, half_select, seed, **kwargs)
    diffs, _ = differential(ENTRY_DRAW_OBJECT_DATA, {"a0": RIDER_OBJECT, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_object_data(buf, RIDER_OBJECT),
                            poison=poison)
    assert not diffs, (f"shift={shift:#x} rows={rows:#x} x={x:#x} half={half_select:#x}\n"
                       + report(diffs))


# The shift is a byte fed to `lsr.l`, whose count is the low 6 bits: 32 and up clear the word
# outright, and 0x40 wraps back to a shift of 0.
_RIDER_SHIFTS = (0, 1, 4, 8, 15, 16, 17, 31, 32, 33, 63, 64, 0x80, 0xff)


@pytest.mark.parametrize("shift", _RIDER_SHIFTS)
def test_draw_object_data_shifts(shift):
    for rows in (1, 2, 5):
        _object_data_case(shift, rows, seed=shift * 8 + rows)


def test_draw_object_data_row_counts():
    for rows in (1, 2, 3, 0x10, 0xff):
        _object_data_case(shift=5, rows=rows, seed=rows)


def test_draw_object_data_zero_rows_is_two_hundred_and_fifty_six():
    """`subq.b`: a draw_rows of 0 runs both passes 256 times, not none."""
    _object_data_case(shift=5, rows=0, seed=0x100)


@pytest.mark.parametrize("x", (0, 1, 0x12f, SPRITE_WRAP_X, 0x131, 0x7fff, 0x8000, 0xffff))
def test_draw_object_data_wrap_column_follows_x(x):
    """`cmp.w #$130,d4 / blt`: from x = 0x130 the wrap column is pulled back a whole scanline.

    The compare is signed, so a "negative" x (0x8000 and up) counts as below the threshold.
    """
    for shift in (0, 6, 15):
        _object_data_case(shift, rows=4, x=x, seed=x + shift)


@pytest.mark.parametrize("half_select", (0, 1, 2, 3, 4, 0xfc, 0xff))
def test_draw_object_data_half_select(half_select):
    """bit1 skips the leading pass, bit0 the wrap column; the other six bits are never tested."""
    _object_data_case(shift=7, rows=4, half_select=half_select, seed=half_select)


def test_draw_object_data_empty_slot_draws_nothing():
    """`tst.w 0(a0)` — a zero flags word returns before anything is read or written."""
    for shift, rows in ((0, 4), (9, 1)):
        _object_data_case(shift, rows, seed=shift, flags=0)


def test_draw_object_data_attribution():
    for shift, rows, x in ((0, 3, 0), (6, 3, SPRITE_WRAP_X), (16, 2, 0)):
        _object_data_case(shift, rows, x=x, seed=0x900 + shift, poison=True)


# --- the lava check -------------------------------------------------------------------------------

def _lava_bottom(row):
    """A playfield_bottom the leading pass reaches exactly at `row`."""
    return RIDER_DST + row * SCREEN_ROW_BYTES


@pytest.mark.parametrize("stop_row", range(6))
def test_draw_object_data_lava_stops_the_leading_pass(stop_row):
    """At playfield_bottom the object is flagged (bit 8) and draw_rows becomes the rows drawn.

    The wrap column then re-reads draw_rows and stops on the same scanline — except at stop_row 0,
    where draw_rows is left at 0 and the wrap pass's `subq.b` loop reads that as 256 rows.
    """
    rows = 5
    wrap_rows = 256 if stop_row == 0 else stop_row
    _object_data_case(shift=4, rows=rows, seed=stop_row, bottom=_lava_bottom(stop_row),
                      noise_rows=max(rows, wrap_rows))


def test_draw_object_data_lava_flag_and_row_count():
    """State the two side effects outright: flags bit 8 set, draw_rows = the rows actually drawn."""
    rows, stop_row = 5, 3
    pokes = _object_data_pokes(shift=4, rows=rows, x=0, half_select=HALF_SELECT_SKIP_WRAP,
                               seed=0xfa, bottom=_lava_bottom(stop_row))
    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_DRAW_OBJECT_DATA, {"a0": RIDER_OBJECT})
    assert struct.unpack_from(">H", bytes(final), RIDER_OBJECT + OBJ_FLAGS)[0] & OBJ_FLAG_IN_LAVA
    assert final[A_DRAW_ROWS] == stop_row


def test_draw_object_data_rereads_playfield_bottom_every_row():
    """Pin the per-row `cmpa.l $d60.l,a3` by drawing the sprite ONTO playfield_bottom.

    Row 0 ORs the sign bit into the longword at 0x10d60, so from row 1 on the destination compares
    as greater than a now-negative bottom and the pass must stop. A reconstruction that hoisted the
    read into a local keeps drawing all five rows.
    """
    rows, positive_bottom = 5, 0x70000000
    dst = A_PLAYFIELD_BOTTOM
    rng = random.Random(0x3720)
    record = bytearray(OBJ_RECORD_BYTES)
    struct.pack_into(">HH", record, OBJ_FLAGS, 1, 0)
    # Row 0's first plane word carries 0x8000, which lands on the top word of playfield_bottom.
    sprite = bytearray(struct.pack(">HHHH", 0x8000, 0, 0, 0))
    sprite += rng.randbytes(rows * SPRITE_SRC_ROW_BYTES - len(sprite))
    pokes = {RIDER_OBJECT: bytes(record), RIDER_SPRITE: bytes(sprite)}
    # One poke per row: a block spanning them would reseed the draw_* globals between the rows.
    _seed_rows(pokes, rng, dst, rows, CELL_BYTES)
    pokes.update({A_PLAYFIELD_BOTTOM: positive_bottom.to_bytes(4, "big"),
                  A_DRAW_HALF_SELECT: bytes((HALF_SELECT_SKIP_WRAP,)),
                  A_DRAW_DST: dst.to_bytes(4, "big"),
                  A_DRAW_SRC: RIDER_SPRITE.to_bytes(4, "big"),
                  A_DRAW_SHIFT: bytes((0, JUNK_BYTE, rows, JUNK_BYTE))})
    diffs, _ = differential(ENTRY_DRAW_OBJECT_DATA, {"a0": RIDER_OBJECT, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_object_data(buf, RIDER_OBJECT))
    assert not diffs, "sprite drawn onto playfield_bottom\n" + report(diffs)


def test_draw_object_data_rereads_draw_rows_when_the_lava_stops_it():
    """Pin `sub.b $df6.l,d1 / neg.b d1` by drawing the sprite ONTO draw_rows.

    The rows-drawn count the routine leaves behind is a FRESH read of draw_rows minus its own
    counter, not the loop index. Row 0 lands on draw_rows and ORs it up to 0xf5; the lava then
    stops row 1 with four rows still on the counter, so the byte stored is 0xf5 - 4, not 1.
    """
    rows, drawn_rows, glyph = 5, 1, 0xf000
    dst = A_DRAW_ROWS                       # so row 0's first plane word lands on draw_rows itself
    rng = random.Random(0x3734)
    record = bytearray(OBJ_RECORD_BYTES)
    struct.pack_into(">HH", record, OBJ_FLAGS, 1, 0)
    sprite = bytearray(struct.pack(">HHHH", glyph, 0, 0, 0))
    sprite += rng.randbytes(rows * SPRITE_SRC_ROW_BYTES - len(sprite))
    pokes = {RIDER_OBJECT: bytes(record), RIDER_SPRITE: bytes(sprite)}
    _seed_rows(pokes, rng, dst, rows, CELL_BYTES)
    # The globals go in LAST: the destination rows above cover draw_rows itself.
    pokes.update({A_PLAYFIELD_BOTTOM: (dst + drawn_rows * SCREEN_ROW_BYTES).to_bytes(4, "big"),
                  A_DRAW_HALF_SELECT: bytes((HALF_SELECT_SKIP_WRAP,)),
                  A_DRAW_DST: dst.to_bytes(4, "big"),
                  A_DRAW_SRC: RIDER_SPRITE.to_bytes(4, "big"),
                  A_DRAW_SHIFT: bytes((0, JUNK_BYTE, rows, JUNK_BYTE))})
    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_DRAW_OBJECT_DATA, {"a0": RIDER_OBJECT})
    assert final[A_DRAW_ROWS] == (((rows | (glyph >> 8)) - (rows - drawn_rows)) & 0xff)

    diffs, _ = differential(ENTRY_DRAW_OBJECT_DATA, {"a0": RIDER_OBJECT, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_object_data(buf, RIDER_OBJECT))
    assert not diffs, "sprite drawn onto draw_rows\n" + report(diffs)


def test_draw_object_data_fuzz():
    rng = random.Random(ENTRY_DRAW_OBJECT_DATA)
    for i in range(150):
        rows = rng.randrange(1, 10)
        # A third of the cases put the lava inside the sprite, so the early exit and the shortened
        # wrap column stay exercised rather than being left to the hand-picked cases above.
        stop_row = rng.randrange(rows + 1) if rng.random() < 0.33 else None
        _object_data_case(rng.randrange(256), rows, x=rng.randrange(1 << 16),
                          half_select=rng.randrange(4), seed=i,
                          bottom=NO_LAVA if stop_row is None else _lava_bottom(stop_row),
                          noise_rows=max(rows, 256 if stop_row == 0 else rows))


# --- draw_object_mask: the same two passes over the object's PREVIOUS position --------------------

def _object_mask_pokes(shift, rows, prev_x, seed, dst=RIDER_DST, src=RIDER_SPRITE):
    passes = _passes_byte(rows)
    rng = random.Random(seed)
    record = bytearray(OBJ_RECORD_BYTES)
    struct.pack_into(">H", record, OBJ_PREV_X, prev_x & 0xffff)
    struct.pack_into(">II", record, OBJ_PREV_DST, dst, src)
    record[OBJ_PREV_ROWS], record[OBJ_PREV_SHIFT] = rows, shift
    return {RIDER_OBJECT: bytes(record),
            src: rng.randbytes(passes * SPRITE_SRC_ROW_BYTES),
            dst - SCREEN_ROW_BYTES: rng.randbytes(_rider_span(passes))}


def _object_mask_case(shift, rows, prev_x=0, seed=0, poison=False):
    pokes = _object_mask_pokes(shift, rows, prev_x, seed)
    diffs, _ = differential(ENTRY_DRAW_OBJECT_MASK, {"a0": RIDER_OBJECT, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_object_mask(buf, RIDER_OBJECT),
                            poison=poison)
    assert not diffs, f"shift={shift:#x} rows={rows:#x} prev_x={prev_x:#x}\n{report(diffs)}"


@pytest.mark.parametrize("shift", _RIDER_SHIFTS)
def test_draw_object_mask_shifts(shift):
    for rows in (1, 2, 5):
        _object_mask_case(shift, rows, seed=shift * 8 + rows)


def test_draw_object_mask_row_counts():
    for rows in (1, 2, 3, 0x10, 0xff, 0):     # 0 is the `subq.b` wrap: 256 rows, not none
        _object_mask_case(shift=5, rows=rows, seed=rows)


@pytest.mark.parametrize("prev_x", (0, 0x12f, SPRITE_WRAP_X, 0x131, 0x8000, 0xffff))
def test_draw_object_mask_wrap_column_follows_prev_x(prev_x):
    """The erase pass reads the object's PREVIOUS x (+0x10), not the current one (+0x02)."""
    for shift in (0, 6, 15):
        _object_mask_case(shift, rows=4, prev_x=prev_x, seed=prev_x + shift)


def test_draw_object_mask_attribution():
    # A source of noise over a noise destination usually clears something, but poisoning is what
    # proves every plane of every row was written rather than left alone.
    for shift, prev_x in ((0, 0), (6, SPRITE_WRAP_X), (16, 0)):
        _object_mask_case(shift, rows=3, prev_x=prev_x, seed=0x900 + shift, poison=True)


# The four plane words row 0 lays over the record when the erase pass is aimed at +0x18 below.
# The mask is AND-NOT, so each bit set here CLEARS the record bit under it:
#   word 1 -> prev_src's low word, dropping RIDER_SPRITE's bit 1 (so 0x6a002 becomes 0x6a000);
#   word 2 -> prev_rows:prev_shift, dropping bit 2 of the row count (7 becomes 3).
_MASK_SELF_ERASE_WORDS = (0, 0x0002, 0x0400, 0)
_MASK_SELF_ERASE_ROWS = 7


def test_draw_object_mask_rereads_rows_and_source_for_the_wrap_column():
    """Pin the second pass's re-reads by aiming the first pass AT the record's own fields.

    The original reloads prev_rows (+0x1c) and prev_src (+0x18) before the wrap column, but keeps
    prev_dst and prev_shift in registers across both passes. Row 0 here erases bits out of exactly
    those two fields, so the wrap column must run three rows from 0x6a000 rather than seven from
    0x6a002 — while still drawing at the destination and shift it started with.
    """
    rows = _MASK_SELF_ERASE_ROWS
    dst = RIDER_OBJECT + OBJ_PREV_SRC       # row 0's four plane words land on +0x18..+0x1f
    rng = random.Random(ENTRY_DRAW_OBJECT_MASK)
    record = bytearray(OBJ_RECORD_BYTES)
    struct.pack_into(">II", record, OBJ_PREV_DST, dst, RIDER_SPRITE)
    record[OBJ_PREV_ROWS], record[OBJ_PREV_SHIFT] = rows, 0
    # Seed from RIDER_SPRITE - 2: the wrap column reads from there once prev_src has lost its bit.
    pokes = {RIDER_SPRITE - 2: rng.randbytes((rows + 1) * SPRITE_SRC_ROW_BYTES),
             RIDER_SPRITE: struct.pack(">HHHH", *_MASK_SELF_ERASE_WORDS)}
    _seed_rows(pokes, rng, dst + SCREEN_ROW_BYTES, rows - 1, CELL_BYTES)   # rows 1.. of the erase
    _seed_rows(pokes, rng, dst + CELL_BYTES, rows, CELL_BYTES)             # the wrap column
    pokes[RIDER_OBJECT] = bytes(record)      # last: row 0 of the erase pass IS the record

    diffs, _ = differential(ENTRY_DRAW_OBJECT_MASK, {"a0": RIDER_OBJECT, "_pokes": pokes},
                            lambda lib, buf: lib.g_draw_object_mask(buf, RIDER_OBJECT))
    assert not diffs, "erase pass aimed at the record's own fields\n" + report(diffs)

    final, _, _ = emu.run(harness.make_image(pokes), ENTRY_DRAW_OBJECT_MASK, {"a0": RIDER_OBJECT})
    assert struct.unpack_from(">I", bytes(final), RIDER_OBJECT + OBJ_PREV_SRC)[0] == RIDER_SPRITE - 2
    assert final[RIDER_OBJECT + OBJ_PREV_ROWS] == rows & ~0x04


def test_draw_object_mask_fuzz():
    rng = random.Random(0x37bc)
    for i in range(150):
        _object_mask_case(rng.randrange(256), rng.randrange(1, 10),
                          prev_x=rng.randrange(1 << 16), seed=i)


# ---------------------------------------------------------------- draw_string @ 0x10700

# The text engine's state block, all consecutive from text_ptr (names.txt / include/draw.h).
A_TEXT_PTR = 0x10e0a       # .l — screen address of the next character cell
A_TEXT_SHIFT = 0x10e0e     # .b — pixels into that cell
A_TEXT_COLOR = 0x10e0f     # .b — one bit per bitplane: set = OR the glyph in, clear = mask it out
A_TEXT_BG_COLOR = 0x10e10  # .b — likewise for the background bar
A_TEXT_FLAGS = 0x10e11     # .b
A_TEXT_X = 0x10e12         # .w — written by the set-position control byte
A_TEXT_Y = 0x10e14         # .w

TEXT_FLAG_BACKGROUND = 0x10
TEXT_FLAG_LARGE_FONT = 0x80

# The in-line control bytes. Everything else is a glyph, including 0x0b/0x0c/0x0e..0x1f, which the
# font lookup takes below ' ' and reads out of the bytes preceding the table.
TEXT_END, TEXT_SET_POS, TEXT_COLOUR, TEXT_BACKGROUND = 0x00, 0x01, 0x02, 0x03
TEXT_BACKSPACE, TEXT_FONT = 0x08, 0x09
TEXT_NOPS = (0x04, 0x05, 0x06, 0x07, 0x0a, 0x0d)
TEXT_BACKSPACE_PIXELS = 6  # `subq.l #6,d3` — the LARGE font's advance, whichever font is selected
CELL_PIXELS = 16

TEXT_STRING = 0x6c000                 # where the string itself is staged
TEXT_CURSOR = DRAW_SCREEN + 0x1000    # headroom below it for backspacing off the left edge
TEXT_SCREEN_BYTES = 0x8000            # noise under every cursor position these cases can reach
UNWRITTEN_W = 0x5a5a                  # pre-filled into text_x/text_y: a slot left alone shows up

harness._lib.g_draw_string.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_string.restype = None


def _text_pokes(text, seed, cursor=TEXT_CURSOR, shift=0, color=0xf, bg_color=0, flags=0):
    rng = random.Random(seed)
    pokes = abi.stack_call_pokes(ENTRY_DRAW_STRING)
    pokes[abi.ARG_BLOCK] = TEXT_STRING.to_bytes(4, "big")
    pokes[A_SCREEN_BASE] = DRAW_SCREEN.to_bytes(4, "big")
    pokes[DRAW_SCREEN] = rng.randbytes(TEXT_SCREEN_BYTES)
    pokes[TEXT_STRING] = bytes(text) + bytes((TEXT_END,))
    # text_ptr/shift/color/bg_color/flags are five consecutive fields; x and y follow them.
    pokes[A_TEXT_PTR] = struct.pack(">IBBBBHH", cursor, shift, color, bg_color, flags,
                                    UNWRITTEN_W, UNWRITTEN_W)
    return pokes


def _text_case(text, seed=0, poison=False, **kwargs):
    pokes = _text_pokes(text, seed, **kwargs)
    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: lib.g_draw_string(buf, abi.ARG_BLOCK),
                            exclude=[CALL_FRAME_BAND], poison=poison)
    assert not diffs, f"text={bytes(text)!r} {kwargs}\n{report(diffs)}"


def _set_pos(x, y):
    return struct.pack(">BHH", TEXT_SET_POS, x, y)


@pytest.mark.parametrize("flags", (0, TEXT_FLAG_LARGE_FONT))
def test_draw_string_plain_text(flags):
    for seed, text in enumerate((b"A", b"HI", b"SCORE 1234567890", b" ", b"~", b"JOUST")):
        _text_case(text, seed=seed, flags=flags)


@pytest.mark.parametrize("flags", (0, TEXT_FLAG_LARGE_FONT))
def test_draw_string_every_glyph_byte(flags):
    """Each byte that is not a control code, one per call.

    That includes 0x0b, 0x0c and 0x0e..0x1f — decoded by none of the `cmp.b` chain, so they reach
    the font as characters below ' ' and index BACKWARDS out of the table — and 0x80..0xff, which
    `sub.b #$20` wraps into the far end of it.
    """
    controls = {TEXT_END, TEXT_SET_POS, TEXT_COLOUR, TEXT_BACKGROUND, TEXT_BACKSPACE, TEXT_FONT}
    controls |= set(TEXT_NOPS)
    for ch in range(0x100):
        if ch not in controls:
            _text_case(bytes((ch,)), seed=ch, flags=flags)


@pytest.mark.parametrize("shift", range(CELL_PIXELS))
def test_draw_string_sub_cell_shifts(shift):
    """A glyph straddles two cells: its high half goes to the cursor cell, its low half 8 bytes on."""
    for flags in (0, TEXT_FLAG_LARGE_FONT):
        _text_case(b"AB", seed=shift, shift=shift, flags=flags)


def test_draw_string_shift_beyond_a_cell():
    """text_shift is a byte fed straight to `lsr.l`, whose count is its low 6 bits: 32+ clears it."""
    for shift in (0x10, 0x1f, 0x20, 0x21, 0x3f, 0x40, 0x80, 0xff):
        _text_case(b"AB", seed=shift, shift=shift)


@pytest.mark.parametrize("color", range(16))
def test_draw_string_colour_bits(color):
    """One bit per bitplane: set ORs the glyph into that plane, clear masks it out of it."""
    _text_case(b"WM", seed=color, color=color)


@pytest.mark.parametrize("bg_color", range(16))
def test_draw_string_background_bar(bg_color):
    """With bit 4 of text_flags the bar is laid down first, in text_bg_color, then the glyph."""
    _text_case(b"WM", seed=bg_color, bg_color=bg_color, flags=TEXT_FLAG_BACKGROUND)


def test_draw_string_colour_high_bits_are_ignored():
    """`btst d4,$e0f.l` only ever asks for bits 0..3 of the byte."""
    for extra in (0x10, 0xf0, 0xff):
        _text_case(b"A", seed=extra, color=extra, bg_color=extra, flags=TEXT_FLAG_BACKGROUND)


def test_draw_string_set_position():
    """Control 1: two words, stored through text_x/text_y and then pushed to pos_to_screen."""
    for seed, (x, y) in enumerate(((0, 0), (16, 3), (17, 3), (159, 10), (319, 20), (7, 0), (0, 30))):
        _text_case(_set_pos(x, y) + b"AB", seed=seed)


def test_draw_string_set_position_replaces_only_the_low_word_of_the_shift():
    """`move.w (a7)+,d3` — pos_to_screen's shift lands in the low word; the high word is kept."""
    for shift in (0, 5, 0xff):
        _text_case(_set_pos(17, 4) + b"A", seed=shift, shift=shift)


def test_draw_string_colour_control():
    for colour in (0, 1, 0xf, 0xff):
        _text_case(bytes((TEXT_COLOUR, colour)) + b"AB", seed=colour)


def test_draw_string_background_control():
    """Control 3 sets bit 4 first and clears it again when the new colour is 0.

    So "background 0" means the bar off, not a bar in colour 0 — and it leaves text_bg_color at 0
    either way.
    """
    for colour in (0, 1, 7, 0xff):
        _text_case(bytes((TEXT_BACKGROUND, colour)) + b"AB", seed=colour)
        _text_case(bytes((TEXT_BACKGROUND, colour)) + b"AB", seed=colour,
                   flags=TEXT_FLAG_BACKGROUND)


def test_draw_string_font_control():
    """Control 9: a non-zero byte selects the 8-row font, zero the 5-row one."""
    for select in (0, 1, 0x80, 0xff):
        for flags in (0, TEXT_FLAG_LARGE_FONT):
            _text_case(bytes((TEXT_FONT, select)) + b"Ag", seed=select, flags=flags)


@pytest.mark.parametrize("nop", TEXT_NOPS)
def test_draw_string_inert_control_bytes(nop):
    """Each of these has its own `beq` back to the top of the loop: consumed, and nothing else."""
    _text_case(bytes((nop,)) + b"AB", seed=nop)


def test_draw_string_backspace():
    """Control 8 always backs up the LARGE font's 6 pixels, whichever font is selected.

    Under 6 the subtraction goes negative and a whole cell is borrowed — which is how 0 - 6 lands
    on the previous cell's column 10 — so every starting shift in a cell is swept here.
    """
    for shift in range(CELL_PIXELS):
        for flags in (0, TEXT_FLAG_LARGE_FONT):
            _text_case(bytes((TEXT_BACKSPACE,)) + b"A", seed=shift, shift=shift, flags=flags)


def test_draw_string_repeated_backspace_walks_back_through_cells():
    _text_case(bytes((TEXT_BACKSPACE,)) * 8 + b"AB", seed=0x8888)


def test_draw_string_cursor_and_shift_persist():
    """The terminator stores the cursor and the sub-cell shift back for the next call."""
    text = b"ABCDE"
    pokes = _text_pokes(text, seed=0xc0, shift=3)
    final, _, _ = emu.run(harness.make_image(pokes), abi.STUB)
    advanced = 3 + len(text) * 4                       # the 5-row font advances 4 pixels a glyph
    assert struct.unpack_from(">I", bytes(final), A_TEXT_PTR)[0] == (
        TEXT_CURSOR + advanced // CELL_PIXELS * CELL_BYTES)
    assert final[A_TEXT_SHIFT] == advanced % CELL_PIXELS


def test_draw_string_empty_string_still_stores_the_cursor():
    _text_case(b"", seed=0, shift=7)


def test_draw_string_rereads_the_colour_state_it_is_drawing_over():
    """Pin the per-plane re-reads by aiming the cursor AT the text engine's own state block.

    `btst #4,$e11.l`, `btst d4,$e0f.l` and `btst d4,$e10.l` all sit INSIDE the plane loop, so a
    glyph laid over text_flags / text_color / text_bg_color changes its own colour partway through
    the character. The same write lands on text_ptr, which the routine keeps in A2 — so the cursor
    must NOT move with it. No noise is seeded here: the destination is the program's own data, and
    both cores start from identical bytes either way.
    """
    cursor = A_TEXT_SHIFT - 6      # so the character's two cells span text_ptr .. text_y
    # A shift past 8 is what makes this bite: below it the glyph's low half is all zeros, so the
    # write that lands on text_bg_color / text_flags (the SECOND cell) would change nothing.
    shift = 12
    pokes = abi.stack_call_pokes(ENTRY_DRAW_STRING)
    pokes[abi.ARG_BLOCK] = TEXT_STRING.to_bytes(4, "big")
    pokes[A_SCREEN_BASE] = DRAW_SCREEN.to_bytes(4, "big")
    pokes[TEXT_STRING] = b"WM" + bytes((TEXT_END,))
    pokes[A_TEXT_PTR] = struct.pack(">IBBBBHH", cursor, shift, 0x5, 0x3, TEXT_FLAG_BACKGROUND,
                                    UNWRITTEN_W, UNWRITTEN_W)
    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: lib.g_draw_string(buf, abi.ARG_BLOCK),
                            exclude=[CALL_FRAME_BAND])
    assert not diffs, "text drawn onto the text engine's own state\n" + report(diffs)


# NO poison=True anywhere in this section, deliberately. draw_string's outputs ARE its inputs —
# text_ptr, text_shift, text_color, text_bg_color and text_flags are all read on entry and written
# back — so the attribution pass, which re-runs both cores on an image whose oracle-written bytes
# are inverted, would hand the routine a garbage cursor and send it writing outside the image
# (harness.differential says as much: poisoning an output that also steers control flow is unsafe).
# Attribution is covered instead by the noise every case seeds across the whole screen: a byte the
# candidate failed to write keeps a random value the oracle's own write would have replaced.
def test_draw_string_over_a_cleared_screen():
    """The one shape the seeded noise cannot speak for: a screen that is already all zeros.

    Every OR then leaves the destination equal to what a candidate skipping the write would leave,
    so this case is here to be run against the AND (mask-out) side, where a cleared plane is only
    reached by actually writing it.
    """
    for seed, text in enumerate((b"A", _set_pos(17, 4) + b"BC", bytes((TEXT_BACKSPACE,)) + b"D")):
        pokes = _text_pokes(text, seed=seed)
        pokes[DRAW_SCREEN] = bytes(TEXT_SCREEN_BYTES)
        diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                                lambda lib, buf: lib.g_draw_string(buf, abi.ARG_BLOCK),
                                exclude=[CALL_FRAME_BAND])
        assert not diffs, f"text={text!r} on a cleared screen\n{report(diffs)}"


TEXT_FUZZ_CHUNKS = 2


def _text_fuzz_cases():
    rng = random.Random(ENTRY_DRAW_STRING)        # seeded ONCE — every chunk replays this stream
    for i in range(200):
        text = bytearray()
        for _ in range(rng.randrange(1, 12)):
            pick = rng.random()
            if pick < 0.55:
                text.append(rng.randrange(0x20, 0x100))          # a glyph
            elif pick < 0.65:
                text += _set_pos(rng.randrange(320), rng.randrange(24))
            elif pick < 0.72:
                text += bytes((TEXT_COLOUR, rng.randrange(256)))
            elif pick < 0.79:
                text += bytes((TEXT_BACKGROUND, rng.randrange(256)))
            elif pick < 0.86:
                text += bytes((TEXT_FONT, rng.randrange(256)))
            elif pick < 0.95:
                text.append(TEXT_BACKSPACE)
            else:
                text.append(rng.choice(TEXT_NOPS))
        yield (i, bytes(text), rng.randrange(256), rng.randrange(256), rng.randrange(256),
               rng.choice((0, TEXT_FLAG_BACKGROUND, TEXT_FLAG_LARGE_FONT,
                           TEXT_FLAG_BACKGROUND | TEXT_FLAG_LARGE_FONT)))


@pytest.mark.parametrize("chunk", range(TEXT_FUZZ_CHUNKS))
def test_draw_string_fuzz(chunk):
    for i, text, shift, color, bg_color, flags in _text_fuzz_cases():
        if i % TEXT_FUZZ_CHUNKS == chunk:
            _text_case(text, seed=i, shift=shift, color=color, bg_color=bg_color, flags=flags)


# ------------------------------------------------------------------ the mirrored constants
#
# Everything above restates addresses, record offsets and control bytes that really live in
# ../../names.txt, include/draw.h and src/draw.c. Nothing makes a drifted mirror FAIL on its own:
# both cores would simply run against the real address, agree byte-for-byte on the game's own
# static data, and go green while the staged inputs landed in dead memory. That is not theory — a
# SPRITE_WRAP_X of 0x140 sweeps a boundary that is not there, and a draw_half_select two bytes off
# stages all seven half_select cases into memory the routine never reads. These pin the mirrors the
# way test_object.py pins its own; hence the import of test_constants' scraper, not a copy of it.


def _check(defines, origin, mirrored):
    """Pin {C name: the value this file restates} against the `#define`s scraped from `origin`."""
    for name, value in mirrored.items():
        got = defines.get(name)
        assert got == value, (f"{name}: {origin} has "
                              f"{'no such #define' if got is None else hex(got)}, "
                              f"test has {value:#x}")


def test_entry_addresses_match_names_txt():
    """Every address this file enters the oracle at is the address names.txt gives that function."""
    entries = ((ENTRY_FILL_SCREEN, "fill_screen"),
               (ENTRY_DRAW_STRING, "draw_string"),
               (ENTRY_SELECT_SPRITE_BASE, "select_sprite_base"),
               (ENTRY_PAINT_FLOOR_ROW, "paint_floor_row"),
               (ENTRY_BLIT_PATTERN_ROWS, "blit_pattern_rows"),
               (ENTRY_BLIT_MASK_WIDE, "blit_mask_wide"),
               (ENTRY_BLIT_SPRITE_PLANES, "blit_sprite_planes"),
               (ENTRY_DRAW_OBJECT_DATA, "draw_object_data"),
               (ENTRY_DRAW_OBJECT_MASK, "draw_object_mask"),
               *((addr, name) for name, addr in GROUND_BLITS.items()))
    for addr, name in entries:
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_globals_match_draw_h():
    """The globals and record offsets restated here are the ones src/draw.c compiles against.

    Only the ones draw.h still owns: the globals and the object record that the object layer reads
    too now live in addrs.h / joust.h, and test_shared_headers_match_the_c pins those.
    """
    header = _defines("include/draw.h")
    _check(header, "draw.h", {
        "A_player2": A_PLAYER2, "A_draw_half_select": A_DRAW_HALF_SELECT,
        "A_draw_dst_off": A_DRAW_DST_OFF,
        "A_draw_clip_cell0": A_DRAW_CLIP_CELL0,
        "A_text_ptr": A_TEXT_PTR, "A_text_shift": A_TEXT_SHIFT, "A_text_color": A_TEXT_COLOR,
        "A_text_bg_color": A_TEXT_BG_COLOR, "A_text_flags": A_TEXT_FLAGS,
        "A_text_x": A_TEXT_X, "A_text_y": A_TEXT_Y,
        "TEXT_FLAG_BACKGROUND": TEXT_FLAG_BACKGROUND,
        "TEXT_FLAG_LARGE_FONT": TEXT_FLAG_LARGE_FONT,
        # Record field offsets. _ptero_record, _spr_record and the object/message packers encode
        # these positionally, so a drifted one stages the field somewhere the routine never looks.
        "PTERO_DST_BASE": PTERO_DST_BASE, "PTERO_SRC": PTERO_SRC, "PTERO_SHIFT": PTERO_SHIFT,
        "PTERO_DST_OFF": PTERO_DST_OFF, "PTERO_ROWS": PTERO_ROWS,
        "PTERO_MASK_OFF": PTERO_MASK_OFF, "PTERO_MASK_ROW_BYTES": PTERO_MASK_ROW_BYTES,
        "SPR_SRC": SPR_SRC, "SPR_DST_OFF": SPR_DST_OFF, "SPR_SHIFT": SPR_SHIFT,
        "SPR_CELL_SELECT": SPR_CELL_SELECT, "SPR_MASK_OFF": SPR_MASK_OFF,
    })
    # One poke stages all three suppressors, which only holds while they are consecutive.
    assert (header["A_draw_clip_cell1"], header["A_draw_clip_cell2"]) == (A_DRAW_CLIP_CELL0 + 1,
                                                                         A_DRAW_CLIP_CELL0 + 2)


def test_mirrored_constants_match_draw_c():
    """...and the values that live in the reconstruction's body rather than in its header."""
    body = _defines("src/draw.c")
    _check(body, "draw.c", {
        "SPRITE_SET_PLAYER1": SPRITE_SET_PLAYER1, "SPRITE_SET_PLAYER2": SPRITE_SET_PLAYER2,
        "SPRITE_SET_ENEMY": SPRITE_SET_ENEMY, "SPRITE_SET_FACING": SPRITE_SET_FACING,
        "SPRITE_SRC_ROW_BYTES": SPRITE_SRC_ROW_BYTES, "SPRITE_WRAP_X": SPRITE_WRAP_X,
        "HALF_SELECT_SKIP_LEADING": HALF_SELECT_SKIP_LEADING,
        "HALF_SELECT_SKIP_WRAP": HALF_SELECT_SKIP_WRAP,
        "PATTERN_ROWS": PATTERN_ROWS,
        "FLOOR_ROW_CELLS": FLOOR_ROW_CELLS, "PLANE3_OFFSET": PLANE3_OFFSET,
        "PTERO_SRC_ROW_BYTES": PTERO_SRC_ROW_BYTES,
        "SPR_MASK_ROW_BYTES": SPR_MASK_ROW_BYTES, "SPR_DATA_ROW_BYTES": SPR_DATA_ROW_BYTES,
        "TEXT_END": TEXT_END, "TEXT_SET_POS": TEXT_SET_POS, "TEXT_COLOUR": TEXT_COLOUR,
        "TEXT_BACKGROUND": TEXT_BACKGROUND, "TEXT_BACKSPACE": TEXT_BACKSPACE,
        "TEXT_FONT": TEXT_FONT,
    })
    # Spelled differently on the two sides, so each needs its own line.
    assert body["FILL_SCREEN_CELLS"] * CELL_BYTES == FILL_SCREEN_BYTES, "the fill length moved"
    assert sorted(body[f"TEXT_NOP_{suffix}"]
                  for suffix in ("4", "5", "6", "7", "LF", "CR")) == sorted(TEXT_NOPS), (
        "the inert control bytes moved — test_draw_string_every_glyph_byte would then render one "
        "of them as a glyph, or skip a byte that really is one")


def test_shared_headers_match_the_c():
    """The cell/scanline geometry, the object record, and the globals shared with the object layer.

    These are the mirrors of what draw.c reads out of joust.h / addrs.h rather than out of draw.h;
    test_object.py pins the same headers from its own side, which is what makes a drift there fail
    on both batteries at once instead of silently in neither.
    """
    _check(_defines("include/joust.h"), "joust.h",
           {"CELL_BYTES": CELL_BYTES, "SCREEN_ROW_BYTES": SCREEN_ROW_BYTES,
            "CELL_PIXELS": CELL_PIXELS,
            "OBJ_FLAGS": OBJ_FLAGS, "OBJ_X": OBJ_X, "OBJ_PREV_X": OBJ_PREV_X,
            "OBJ_PREV_DST": OBJ_PREV_DST, "OBJ_PREV_SRC": OBJ_PREV_SRC,
            "OBJ_PREV_ROWS": OBJ_PREV_ROWS, "OBJ_PREV_SHIFT": OBJ_PREV_SHIFT,
            "OBJ_FLAG_IN_LAVA": OBJ_FLAG_IN_LAVA,
            # Spelled as a bit number on this side, so it needs its own line.
            "OBJ_FLAG_FACING_RIGHT": 1 << FACING_RIGHT_BIT})
    _check(_defines("include/addrs.h"), "addrs.h",
           {"A_screen_base": A_SCREEN_BASE, "A_object_table": A_OBJECT_TABLE,
            "A_playfield_bottom": A_PLAYFIELD_BOTTOM, "A_draw_dst": A_DRAW_DST,
            "A_draw_src": A_DRAW_SRC, "A_draw_shift": A_DRAW_SHIFT, "A_draw_rows": A_DRAW_ROWS})
    assert harness.NAME_MAP.get(A_SCREEN_BASE) == "screen_base"
