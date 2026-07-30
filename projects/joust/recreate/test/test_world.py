"""Differential tests for Joust's world layer (src/world.c).

Covered here, leaves first: troll_erase_hand @ 0x149b8, troll_draw_hand @ 0x14a32,
start_death_anim @ 0x14098, raise_floor @ 0x1757a, draw_platforms @ 0x1052e,
flash_spawn_pad @ 0x13628, animate_ground_shrink @ 0x175de and dissolve_platforms @ 0x17438.

Their two drivers are deliberately absent: lava_troll @ 0x146f6 calls play_sound and score_update,
and wave_manager @ 0x1783c calls find_free_message and the two score_update entries — none of them
reconstructed, so neither driver can be run against the oracle yet.

`poison=True` is on wherever the routine's outputs are pure data. It is off — with a note at each
site — for the three routines whose outputs are POINTERS the next run dereferences (playfield_bottom,
the ground-burn sprite cursors, the dissolve cursors): inverting those hands both cores a wild
address, which is not a test of anything. Those routines instead pre-fill their output slots with a
sentinel, so a write the candidate skips still shows up as a diff.
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
ENTRY_DRAW_PLATFORMS = 0x1052e
ENTRY_FLASH_SPAWN_PAD = 0x13628
ENTRY_START_DEATH_ANIM = 0x14098
ENTRY_TROLL_ERASE_HAND = 0x149b8
ENTRY_TROLL_DRAW_HAND = 0x14a32
ENTRY_DISSOLVE_PLATFORMS = 0x17438
ENTRY_RAISE_FLOOR = 0x1757a
ENTRY_ANIMATE_GROUND_SHRINK = 0x175de

# ---- globals (mirror of include/world.h and include/addrs.h, which mirror ../../names.txt) ----
A_WAVE_NUM = 0x10cf3
A_PLATFORM_PRESENT = 0x10cfa
A_PLAYFIELD_BOTTOM = 0x10d60
A_FLOOR_STEP_TIMER = 0x10d64
A_FLOOR_ROWS_LEFT = 0x10d65
A_GROUND_ANIM_TIMER = 0x10d66
A_GROUND_ANIM = 0x10d68
A_GROUND_ANIM_NEXT = 0x10d84
A_TROLL_PREV_DST = 0x10dc6
A_TROLL_PREV_SRC = 0x10dca
A_TROLL_PREV_SHIFT = 0x10dce
A_TROLL_PREV_ROWS = 0x10dd8
A_SCREEN_BASE = 0x10dde
A_DRAW_DST = 0x10de8
A_DRAW_SRC = 0x10df0
A_DRAW_SHIFT = 0x10df4
A_DRAW_ROWS = 0x10df6
A_RNG_PTR = 0x10dfe
A_OBJECT_TABLE = 0x10f36
A_EFFECT_TABLE = 0x1137a
A_EFFECT_TABLE_END = 0x113ba
A_GROUND_X0 = 0x117b8
A_GROUND_X1 = 0x117ba
A_SPAWN_PAD_COLORS = 0x11944
A_SPAWN_PAD_PATTERN = 0x1194c
A_SPAWN_POINTS = 0x11964
A_PLATFORM_SPRITES = 0x119d4
A_DEATH_SPRITE_P1 = 0x1922a
A_DEATH_SPRITE_OTHER = 0x193da

# ---- record geometry ----
OBJ_SIZE = 0x4e
PSPR_RECORD, N_PLATFORMS = 0x10, 8
EFF_RECORD = 0x10
N_EFFECTS = (A_EFFECT_TABLE_END - A_EFFECT_TABLE) // EFF_RECORD
GA_BLOCK_BYTES = 0x1c
SPR_MASK_OFF = 0x90
SPAWN_RECORD = 0x14
CELL_BYTES = 8
CELL_PLANE_WORDS = 4
SCREEN_ROW_BYTES = 0xa0

# The four flame frames animate_ground_shrink cycles (real program data, left in place).
FLAME_FRAME_BYTES = 0xd8
FLAME_FRAME_FIRST = 0x18636
FLAME_FRAME_END = 0x18996
FLAME_FRAMES = tuple(range(FLAME_FRAME_FIRST, FLAME_FRAME_END, FLAME_FRAME_BYTES))

# ---- scratch areas, all clear of the program (ends 0x2b7ae), abi.STUB/RESULT (0x40000..0x40207),
# the staged-file table (0xbf000) and the stack guard.
SPRITE = 0x50000
NOISE = 0x60000
SCREEN = 0x70000
SCREEN_ALT = 0x80000     # a second framebuffer, so screen_base is read rather than assumed
OBJ_A = 0x48000          # an object record away from object_table, so the P1 identity is a choice

# The bases every battery whose routine reads screen_base is swept over. SCREEN_ALT is the one that
# catches a hard-coded framebuffer outright; the two near misses catch a base that is re-read but
# rounded — to a cell (+2) or to a row (+SCREEN_ROW_BYTES).
SCREEN_BASES = (SCREEN, SCREEN + 2, SCREEN + SCREEN_ROW_BYTES, SCREEN_ALT)

SCREEN_BYTES = 0x8000    # what the tests pre-fill and let the blits roam over
UNWRITTEN = 0x5a          # pre-filled into output areas so a missing write shows as a diff
JUNK_RESULT = 0xa5a5a5a5  # pre-filled into abi.RESULT for the register-result stub

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs in (("g_draw_platforms", 0), ("g_raise_floor", 0), ("g_flash_spawn_pad", 2),
                      ("g_troll_erase_hand", 0), ("g_troll_draw_hand", 1),
                      ("g_start_death_anim", 3), ("g_animate_ground_shrink", 0),
                      ("g_dissolve_platforms", 0)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = None


# ------------------------------------------------------------------ shared staging helpers

def _result_stub(routine):
    """Pokes for `jsr routine ; move.l d0,(abi.RESULT).l ; rts`.

    start_death_anim returns the object's new flags in D0, which an image diff cannot see, so the
    oracle is entered through this stub and the candidate's glue writes the same longword to the
    same address (the convention test/abi.py documents).
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")
            + b"\x23\xc0" + abi.RESULT.to_bytes(4, "big")     # move.l d0,(xxx).L
            + b"\x4e\x75")
    return {abi.STUB: code, abi.RESULT: JUNK_RESULT.to_bytes(4, "big")}


# The screen every battery starts from. All FOUR bitplane words differ, which is load-bearing, not
# decoration: over a uniform fill the four planes of a cell are identical, and then a candidate that
# read or wrote the wrong plane — a transposed `and_cell`, a `paint_floor_row` that ORed one plane
# instead of all four, a crumble that skipped its planes-0-1 narrowing — produces byte-identical
# output and passes. Poison does not cover that hole either: the byte IS written, with the value the
# oracle wrote. The fill is the only defence, so keep the four words distinct.
_SCREEN_CELL = struct.pack(">HHHH", 0x0f0f, 0x00ff, 0x3333, 0x5a5a)


def _blank_screen(base=SCREEN, cell=_SCREEN_CELL, size=SCREEN_BYTES):
    """The patterned fill, laid at `base`.

    The four SCREEN_BASES batteries pass their own screen_base here, so the fill follows the
    framebuffer and the default block is left at the loaded image's zeros. That is what makes the
    sweep bite: a candidate that hard-coded the usual framebuffer paints over zeros while the oracle
    paints over the pattern, and the two images disagree in both places.

    The two troll helpers deliberately do NOT thread their screen_base in — their only non-default
    base is 0, and filling 0x8000 bytes from there would bury the vector page and the program. They
    pop the default block instead (see the two playfield_bottom-reread tests). A new troll battery
    that wants to sweep bases has to solve that first, not just pass the argument through.
    """
    return {base: cell * (size // len(cell))}


def _rows(*words):
    """Plane words, big-endian, as a sprite/screen byte string."""
    return struct.pack(">" + "H" * len(words), *(w & 0xffff for w in words))


# How many rows of sprite a case actually needs staged. A signed-word row count of 0 or less draws
# nothing, and a huge positive one is cut off by the lava long before it runs out of sprite, so
# staging `rows` rows literally would poke a quarter of a megabyte over the neighbouring scratch
# blocks (and break this file's own SPRITE budget assert) for no coverage at all.
SPRITE_ROWS_STAGED = 32
TROLL_MASK_ROW_BYTES = 4      # `_mask_rows` packs one `>I` per row


def _rows_to_stage(rows):
    return min(max((rows if rows < 0x8000 else 0), 1), SPRITE_ROWS_STAGED)


def _sprite_rows(rows, shape):
    """`rows` rows of four plane words; `shape(row) -> (p0, p1, p2, p3)`."""
    return b"".join(_rows(*shape(r)) for r in range(rows))


def _mask_rows(rows, shape):
    """`rows` rotated AND-mask longwords, one per row."""
    return b"".join(struct.pack(">I", shape(r) & 0xffffffff) for r in range(rows))


# ------------------------------------------------------------------ troll_erase_hand @ 0x149b8

# A hand sprite: the data half is unused by the erase pass, the mask half is what it ANDs in.
_HAND_ROWS = 6


def _hand_masks(rows=_HAND_ROWS, shape=None):
    """A sprite block whose mask (at SPR_MASK_OFF) is one distinct longword per row.

    The masks are deliberately not all-ones and not all-zero: a row that cleared everything or
    nothing would be reproduced by a blitter that got the rotation wrong.
    """
    shape = shape or (lambda r: 0xf0f0_0f0f ^ (0x1111_1111 * r))
    return bytes(SPR_MASK_OFF) + _mask_rows(rows, shape)


def _erase_case(pokes, poison=True, note=""):
    diffs, _ = differential(ENTRY_TROLL_ERASE_HAND, {"_pokes": pokes},
                            lambda lib, buf: lib.g_troll_erase_hand(buf), poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


def _erase_pokes(shift, rows, dst_off=0, src=SPRITE, prev=None, playfield=None,
                 screen_base=SCREEN):
    """Stage troll_prev_* and the draw_* the early-out compares them against.

    `prev` overrides what the draw_* globals hold; by default they differ from troll_prev_*, so the
    erase actually runs. `playfield` is the lava surface, far below the sprite unless a test moves it.
    """
    draw_src, draw_dst, draw_shift = prev or (src + 4, dst_off + 4, shift + 1)
    pokes = _blank_screen()
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_PLAYFIELD_BOTTOM: struct.pack(">I", playfield if playfield is not None
                                        else SCREEN + SCREEN_BYTES),
        A_TROLL_PREV_SRC: struct.pack(">I", src),
        A_TROLL_PREV_DST: struct.pack(">I", dst_off),
        A_TROLL_PREV_SHIFT: struct.pack(">H", shift & 0xffff),
        A_TROLL_PREV_ROWS: struct.pack(">H", rows & 0xffff),
        A_DRAW_SRC: struct.pack(">I", draw_src),
        A_DRAW_DST: struct.pack(">I", draw_dst),
        A_DRAW_SHIFT: struct.pack(">H", draw_shift & 0xffff),
        SPRITE: _hand_masks(),
    })
    return pokes


def test_troll_erase_hand_early_out_needs_all_three_to_match():
    """The routine bails only when src, dst AND shift all still hold last frame's values.

    Each case below leaves exactly one of the three different, so a candidate that compared any two
    of them (or ORed the tests) erases where the original does not, or the other way round.
    """
    shift, rows, dst_off = 3, _HAND_ROWS, 0x140
    same = (SPRITE, dst_off, shift)
    for prev in (same,
                 (SPRITE + 4, dst_off, shift),
                 (SPRITE, dst_off + 8, shift),
                 (SPRITE, dst_off, shift + 1)):
        _erase_case(_erase_pokes(shift, rows, dst_off=dst_off, prev=prev),
                    note=f"prev={prev}")


@pytest.mark.parametrize("shift", (0, 1, 4, 15, 16, 17, 31, 32, 33, 0x3f, 0x40, 0xffff))
def test_troll_erase_hand_shifts(shift):
    """ROR.L takes its count mod 32, so 32 is no rotation at all and 0xffff is 31."""
    _erase_case(_erase_pokes(shift, _HAND_ROWS, dst_off=0x140), note=f"shift={shift}")


@pytest.mark.parametrize("rows", (0, 1, 2, _HAND_ROWS, 0x8000, 0xffff))
def test_troll_erase_hand_row_counts_are_signed_words(rows):
    """`subq.w #1,d7 ; blt` — a count of 0 or less draws NOTHING (unlike blit.c's byte counters,
    where 0 means 256). 0xffff is -1 and 0x8000 the most negative word."""
    pokes = _erase_pokes(0, rows, dst_off=0x140)
    pokes[SPRITE] = _hand_masks(rows=_rows_to_stage(rows))
    _erase_case(pokes, note=f"rows={rows}")


def test_troll_erase_hand_stops_at_the_lava():
    """`cmpa.l playfield_bottom-8,a1 ; bcc` cuts the blit off at the lava surface, one cell short."""
    rows = 8
    for stop_row in range(rows + 2):
        pokes = _erase_pokes(5, rows, dst_off=0x140,
                             playfield=SCREEN + 0x140 + stop_row * SCREEN_ROW_BYTES + CELL_BYTES)
        pokes[SPRITE] = _hand_masks(rows=rows)
        _erase_case(pokes, note=f"stop_row={stop_row}")


def test_troll_erase_hand_rereads_playfield_bottom_every_row():
    """playfield_bottom is fetched INSIDE the row loop, so a mask that lands on it truncates the
    blit that is drawing it.

    The destination is aimed so that row 2 covers playfield_bottom itself. Its four plane words are
    ANDed with the same mask, which knocks the surface down to a value below row 3 — and the blit
    stops there. Hoisting the read out of the loop would run all 8 rows instead.

    poison is off: the poisoned image would hand both cores an inverted playfield_bottom, i.e. an
    arbitrary address, which tests nothing. The surrounding cases carry the attribution instead.
    """
    rows, screen_base, dst_off = 8, 0, A_PLAYFIELD_BOTTOM - 2 * SCREEN_ROW_BYTES
    pokes = _erase_pokes(0, rows, dst_off=dst_off, screen_base=screen_base,
                         playfield=0x0f010f0f)
    pokes[SPRITE] = _hand_masks(rows=rows, shape=lambda r: 0x00ff_00ff)
    pokes.pop(SCREEN)
    _erase_case(pokes, poison=False)


def test_troll_erase_hand_reads_a_row_before_writing_it():
    """Each row's mask longword is read before either of its two cells is ANDed.

    Aiming the destination at the sprite block makes the orders differ: a blitter that pre-read the
    whole mask column, or that wrote the leading cell before reading the next row, would feed its
    own output back in. The draw pass has the same test; without this one the erase pass never sees
    a destination that overlaps its source at all.
    """
    rows = 6
    for delta in (0, 8, 0x10, -8, SPR_MASK_OFF, SPR_MASK_OFF + 4, SCREEN_ROW_BYTES):
        pokes = _erase_pokes(3, rows, dst_off=(SPRITE + delta - SCREEN) & 0xffffffff)
        pokes[SPRITE] = _hand_masks(rows=rows)
        _erase_case(pokes, poison=False, note=f"delta={delta}")


ERASE_FUZZ_CHUNKS = 2


def _erase_fuzz_cases():
    rng = random.Random(0x149B8)                 # seeded ONCE — every chunk replays this stream
    for i in range(200):
        rows = rng.randint(1, 24)
        yield (i, rng.choice((0, 1, 3, 8, 15, 16, 31, 32, 47)), rows,
               rng.randrange(0, 0x2000) & ~1,
               [rng.randrange(1 << 32) for _ in range(rows)])


@pytest.mark.parametrize("chunk", range(ERASE_FUZZ_CHUNKS))
def test_troll_erase_hand_fuzz(chunk):
    for i, shift, rows, dst_off, masks in _erase_fuzz_cases():
        if i % ERASE_FUZZ_CHUNKS != chunk:
            continue
        pokes = _erase_pokes(shift, rows, dst_off=dst_off)
        pokes[SPRITE] = bytes(SPR_MASK_OFF) + b"".join(struct.pack(">I", m) for m in masks)
        _erase_case(pokes, poison=False, note=f"case {i}")


# ------------------------------------------------------------------ troll_draw_hand @ 0x14a32

def _hand_pixels(rows, shape=None):
    """Sprite data for the draw pass: four plane words per row, 8 bytes apart."""
    shape = shape or (lambda r: (0xf00f ^ (0x1111 * r), 0x0ff0, 0x8001 * (r + 1), 0xaa55))
    return _sprite_rows(rows, shape)


def _draw_pokes(shift, rows, state=1, dst_off=0, src=SPRITE, playfield=None,
                screen_base=SCREEN, sprite=None):
    pokes = _blank_screen()
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_PLAYFIELD_BOTTOM: struct.pack(">I", playfield if playfield is not None
                                        else SCREEN + SCREEN_BYTES),
        A_DRAW_SRC: struct.pack(">I", src),
        A_DRAW_DST: struct.pack(">I", dst_off),
        A_DRAW_SHIFT: struct.pack(">H", shift & 0xffff),
        A_DRAW_ROWS: struct.pack(">H", rows & 0xffff),
        SPRITE: sprite if sprite is not None else _hand_pixels(_rows_to_stage(rows)),
    })
    return pokes, state


def _draw_case(pokes, state, poison=True, note=""):
    diffs, _ = differential(ENTRY_TROLL_DRAW_HAND, {"d0": state, "_pokes": pokes},
                            lambda lib, buf: lib.g_troll_draw_hand(buf, state), poison=poison)
    assert not diffs, f"state={state:#x} {note}\n{report(diffs)}"


@pytest.mark.parametrize("state", (0, 1, 2, 3, 0xfffe, 0xffff, 0x1_0000, 0x1_0001))
def test_troll_draw_hand_is_gated_on_bit0_alone(state):
    """`btst #0,d0` on the whole longword: every other bit of the troll state is ignored here."""
    pokes, _ = _draw_pokes(2, 5, dst_off=0x140)
    _draw_case(pokes, state, note="bit0 gate")


@pytest.mark.parametrize("shift", (0, 1, 4, 15, 16, 17, 31, 32, 33, 0x3f, 0x40))
def test_troll_draw_hand_shifts(shift):
    """LSR.L takes its count mod 64: 32..63 shift every pixel out, 64 is no shift at all."""
    pokes, state = _draw_pokes(shift, 6, dst_off=0x140)
    _draw_case(pokes, state, note=f"shift={shift}")


@pytest.mark.parametrize("rows", (0, 1, 2, 6, 0x8000, 0xffff))
def test_troll_draw_hand_row_counts_are_signed_words(rows):
    pokes, state = _draw_pokes(3, rows, dst_off=0x140)
    _draw_case(pokes, state, note=f"rows={rows}")


def test_troll_draw_hand_stops_at_the_lava():
    rows = 8
    for stop_row in range(rows + 2):
        pokes, state = _draw_pokes(5, rows, dst_off=0x140,
                                   playfield=SCREEN + 0x140 + stop_row * SCREEN_ROW_BYTES
                                   + CELL_BYTES)
        _draw_case(pokes, state, note=f"stop_row={stop_row}")


def test_troll_draw_hand_rereads_playfield_bottom_every_row():
    """As for the erase pass, but the other way round: playfield_bottom starts at 0, so
    `playfield_bottom - 8` wraps to 0xfffffff8 and every row passes. Row 2 ORs a value into it, and
    from then on the surface is a small address that cuts the blit off.

    poison is off for the same reason as the erase pass — see that test.
    """
    rows, screen_base, dst_off = 8, 0, A_PLAYFIELD_BOTTOM - 2 * SCREEN_ROW_BYTES
    # Row 2's plane 1 word lands at playfield_bottom + 2, making the surface 0x00000100.
    sprite = _hand_pixels(rows, shape=lambda r: (0, 0x0100, 0, 0) if r == 2 else (0, 0, 0, 0))
    pokes, state = _draw_pokes(0, rows, dst_off=dst_off, screen_base=screen_base,
                               playfield=0, sprite=sprite)
    pokes.pop(SCREEN)
    _draw_case(pokes, state, poison=False)


def test_troll_draw_hand_reads_a_row_before_writing_it():
    """All four planes of a row are read before any of them is written (`move.l`x4, then the ORs).

    Aiming the destination at the sprite's own bytes makes the two orders differ: a blitter that
    wrote plane 0 before reading plane 1 would feed its own output back in.
    """
    rows = 4
    for delta in (0, 8, 0x10, -8, SCREEN_ROW_BYTES, SCREEN_ROW_BYTES - 8):
        pokes, state = _draw_pokes(4, rows, dst_off=(SPRITE + delta - SCREEN) & 0xffffffff,
                                   screen_base=SCREEN)
        _draw_case(pokes, state, poison=False, note=f"delta={delta}")


DRAW_FUZZ_CHUNKS = 2


def _draw_fuzz_cases():
    rng = random.Random(0x14A32)                 # seeded ONCE — every chunk replays this stream
    for i in range(200):
        rows = rng.randint(1, 24)
        yield (i, rng.choice((0, 1, 3, 8, 15, 16, 31, 32, 47)), rows,
               rng.randrange(0, 0x2000) & ~1,
               [tuple(rng.randrange(1 << 16) for _ in range(CELL_PLANE_WORDS))
                for _ in range(rows)])


@pytest.mark.parametrize("chunk", range(DRAW_FUZZ_CHUNKS))
def test_troll_draw_hand_fuzz(chunk):
    for i, shift, rows, dst_off, planes in _draw_fuzz_cases():
        if i % DRAW_FUZZ_CHUNKS != chunk:
            continue
        pokes, state = _draw_pokes(shift, rows, dst_off=dst_off,
                                   sprite=_sprite_rows(rows, lambda r: planes[r]))
        _draw_case(pokes, state, poison=False, note=f"case {i}")


# ------------------------------------------------------------------ start_death_anim @ 0x14098

OBJ_PREV_DST = 0x14
OBJ_PREV_SHIFT = 0x1d
OBJ_EGG_STATE = 0x1e
OBJ_EGG_DST = 0x2a
OBJ_EGG_SRC = 0x2e
OBJ_EGG_ROWS = 0x32
OBJ_EGG_SHIFT = 0x33
OBJ_EGG_CHAIN = 0x35
OBJ_SCORE_PENDING = 0x43

DEATH_SPRITE_RISE = 0x280


def _death_object(prev_dst, prev_shift=0, chain=0xcc, score=0, egg_dst=0xdeadbeef):
    rec = bytearray(UNWRITTEN.to_bytes(1, "big") * OBJ_SIZE)   # every output slot starts as junk
    struct.pack_into(">I", rec, OBJ_PREV_DST, prev_dst)
    rec[OBJ_PREV_SHIFT] = prev_shift
    rec[OBJ_EGG_CHAIN] = chain
    rec[OBJ_SCORE_PENDING] = score
    struct.pack_into(">I", rec, OBJ_EGG_DST, egg_dst)
    return bytes(rec)


def _death_case(object_addr, flags, prev_dst, screen_base, poison=True, **fields):
    pokes = _result_stub(ENTRY_START_DEATH_ANIM)
    pokes[A_SCREEN_BASE] = struct.pack(">I", screen_base)
    pokes[object_addr] = _death_object(prev_dst, **fields)
    diffs, _ = differential(
        abi.STUB, {"a0": object_addr, "d0": flags, "_pokes": pokes},
        lambda lib, buf: lib.g_start_death_anim(buf, object_addr, flags, abi.RESULT),
        poison=poison)
    assert not diffs, (f"object={object_addr:#x} flags={flags:#x} prev_dst={prev_dst:#x} "
                       f"screen_base={screen_base:#x}\n{report(diffs)}")


def test_start_death_anim_picks_the_sprite_by_identity():
    """Player 1's slot gets one dismount sprite and egg state, everything else the other pair.

    The comparison is a full-longword `cmpa.l`, so the record one byte either side of object_table
    is NOT player 1.
    """
    for obj in (A_OBJECT_TABLE, A_OBJECT_TABLE + 1, A_OBJECT_TABLE - 1,
                A_OBJECT_TABLE + OBJ_SIZE, OBJ_A):
        _death_case(obj, flags=0, prev_dst=SCREEN + 0x1000, screen_base=SCREEN)


def test_start_death_anim_clamps_the_sprite_to_the_framebuffer():
    """The death sprite starts DEATH_SPRITE_RISE above the rider — unless that is off the top of
    the screen, in which case it stays where the rider was (`cmp.l ... ; blt`, SIGNED)."""
    base = SCREEN
    for prev_dst in (base, base + DEATH_SPRITE_RISE - 1, base + DEATH_SPRITE_RISE,
                     base + DEATH_SPRITE_RISE + 1, base + 0x1000, base - 0x1000):
        _death_case(OBJ_A, flags=0, prev_dst=prev_dst & 0xffffffff, screen_base=base)


def test_start_death_anim_clamp_compare_is_signed():
    """A screen_base with bit 31 set is NEGATIVE to the compare, so it never clamps — while the
    same value read as unsigned would clamp every time."""
    for screen_base in (0x8000_0000, 0xffff_ff00, 0x7fff_ff00):
        _death_case(OBJ_A, flags=0, prev_dst=0x0000_1000, screen_base=screen_base)


@pytest.mark.parametrize("flags", (0, 1, 0x3000, 0x1000, 0x2000, 0x8000, 0xffff,
                                   0xffff_0000, 0xdead_beef))
def test_start_death_anim_sets_the_dead_and_removed_bits(flags):
    """`bset #13 ; bset #12` on the whole longword: bits 12 and 13 go up, nothing else moves."""
    _death_case(OBJ_A, flags=flags, prev_dst=SCREEN + 0x1000, screen_base=SCREEN)


@pytest.mark.parametrize("score", (0, 1, 0xfa, 0xfb, 0xfe, 0xff))
def test_start_death_anim_score_is_a_byte_add(score):
    """`addq.b #5,67(a0)` wraps inside the byte — 0xff becomes 4, it does not carry."""
    _death_case(OBJ_A, flags=0, prev_dst=SCREEN + 0x1000, screen_base=SCREEN, score=score)


@pytest.mark.parametrize("prev_shift", (0, 1, 0x0f, 0x80, 0xff))
def test_start_death_anim_copies_the_riders_pixel_phase(prev_shift):
    _death_case(OBJ_A, flags=0, prev_dst=SCREEN + 0x1000, screen_base=SCREEN,
                prev_shift=prev_shift)


# ------------------------------------------------------------------ raise_floor @ 0x1757a

def _floor_case(rows_left, step_timer, playfield, note=""):
    """poison is off throughout: playfield_bottom is an output the NEXT call dereferences, so an
    inverted copy of it would send paint_floor_row at an arbitrary address. The screen is pre-filled
    with a sentinel instead, which catches a paint pass the candidate skips."""
    pokes = _blank_screen()
    pokes.update({
        A_FLOOR_ROWS_LEFT: bytes([rows_left]),
        A_FLOOR_STEP_TIMER: bytes([step_timer]),
        A_PLAYFIELD_BOTTOM: struct.pack(">I", playfield),
    })
    diffs, _ = differential(ENTRY_RAISE_FLOOR, {"_pokes": pokes},
                            lambda lib, buf: lib.g_raise_floor(buf))
    assert not diffs, (f"rows_left={rows_left} step_timer={step_timer} "
                       f"playfield={playfield:#x} {note}\n{report(diffs)}")


@pytest.mark.parametrize("rows_left", (0, 1, 2, 0x7f, 0x80, 0xff))
def test_raise_floor_is_gated_on_rows_left(rows_left):
    """rows_left is tested for ZERO, not for sign: 0x80 (-128 as a signed byte) still raises."""
    _floor_case(rows_left, step_timer=1, playfield=SCREEN + 0x2000)


@pytest.mark.parametrize("step_timer", (0, 1, 2, 3, 7, 8, 0xff))
def test_raise_floor_step_timer_is_a_byte_countdown(step_timer):
    """`subq.b #1` on a byte: only a timer that reaches exactly 0 fires, and a timer of 0 wraps to
    0xff — 256 calls away from firing, not one."""
    _floor_case(rows_left=3, step_timer=step_timer, playfield=SCREEN + 0x2000)


@pytest.mark.parametrize("row", (0, 1, 2, 20, 100))
def test_raise_floor_paints_two_strips_of_the_exposed_row(row):
    """The surface moves up one scanline, and paint_floor_row runs at cells 0-4 and 15-19 of it.

    The second call's address is where the FIRST call left the address register plus 0x50 — the
    original passes a1 and paint_floor_row advances it — so a reconstruction that treated the two
    calls as "row" and "row + 0x50" paints the wrong half of the screen.
    """
    _floor_case(rows_left=5, step_timer=1,
                playfield=SCREEN + 0x1000 + row * SCREEN_ROW_BYTES, note=f"row={row}")


def test_raise_floor_does_not_clip_the_surface():
    """Nothing stops the surface walking off the top of the framebuffer — it just keeps going.

    Two bounds keep these cases meaningful rather than merely low. A playfield_bottom under one
    scanline would wrap the longword and aim paint_floor_row at a 32-bit address the reconstruction
    (which indexes a 1 MiB buffer) cannot follow. And a row inside the 68000 vector page is off
    limits to ANY case here: the oracle installs its TOS trap vectors at 0x84..0xbb for the duration
    of a run and restores them afterwards, so a routine that reads those bytes sees values the
    candidate never can. Both are harness limits, stated rather than silently avoided.
    """
    for playfield in (0x1000, 0x2000, SCREEN):
        _floor_case(rows_left=1, step_timer=1, playfield=playfield)


# ------------------------------------------------------------------ draw_platforms @ 0x1052e

PSPR_PRESENT, PSPR_ROWS, PSPR_COLS, PSPR_SRC, PSPR_DST_OFF = 0x0, 0x4, 0x6, 0x8, 0xc
PLATFORM_SPENT = 0xff
FLOOR_STEP_FRAMES = 7


def _platform_sprite(present_ptr, rows, cols, src, dst_off):
    return struct.pack(">IHHII", present_ptr, rows & 0xffff, cols & 0xffff, src, dst_off)


def _platform_case(present, rows=2, cols=2, dst_step=0x400, present_order=None,
                   screen_base=SCREEN, poison=True, note=""):
    """Eight platform_sprites records, each with its own present byte and its own screen strip.

    `present_order[n]` is the platform_present INDEX record n points at. It defaults to the identity
    map, which is what the game ships — but an identity map cannot tell the pointer indirection
    (`movea.l (a6),a0 ; tst.b (a0)`) apart from indexing platform_present by the loop counter, so
    one case below permutes it.
    """
    order = present_order or range(N_PLATFORMS)
    records = b"".join(
        _platform_sprite(A_PLATFORM_PRESENT + slot, rows, cols,
                         SPRITE + n * 0x100, n * dst_step)
        for n, slot in enumerate(order))
    pokes = _blank_screen(screen_base)
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_PLATFORM_PRESENT: bytes(present),
        A_PLATFORM_SPRITES: records,
        SPRITE: bytes(range(1, 0x100)) * 0x40,  # never zero, so every OR is visible
    })
    diffs, _ = differential(ENTRY_DRAW_PLATFORMS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_draw_platforms(buf), poison=poison)
    assert not diffs, (f"present={list(present)} screen_base={screen_base:#x} "
                       f"{note}\n{report(diffs)}")


@pytest.mark.parametrize("count", (0, 1, 2, 3, 0x7f, 0x80, 0x81, 0xfe, 0xff))
def test_draw_platforms_present_count_is_a_signed_byte(count):
    """A count above zero redraws and ticks down; 0 and every NEGATIVE byte (0x80..0xff) is skipped.

    A count that ticks down to exactly zero latches at -1 instead of stopping at 0, which is what
    keeps a redrawn platform quiet on the next pass.
    """
    _platform_case([count] * N_PLATFORMS)


def test_draw_platforms_pairs_2_3_and_6_7_are_forced_to_agree():
    """Each pair is the two halves of one structure, so the LARGER count wins — a signed compare,
    so a live count beats the -1 latch and 0x80 loses to 0."""
    for a, b in ((0, 0), (0, 1), (1, 0), (2, 5), (5, 2), (0xff, 1), (1, 0xff),
                 (0x80, 0), (0, 0x80), (3, 3)):
        present = [0] * N_PLATFORMS
        present[2], present[3] = a, b
        present[6], present[7] = b, a
        _platform_case(present, note=f"pair={a:#x},{b:#x}")


def test_draw_platforms_present_is_reached_through_the_records_pointer():
    """Each record carries a POINTER to its countdown byte, and nothing says record n owns byte n.

    With the map reversed, a candidate that indexed platform_present by the loop counter arms the
    wrong platform and draws the wrong strip — which the identity map every other case uses cannot
    show. The pair sync still works on indices 2/3 and 6/7 of the BYTES, so a reversed map also
    moves which records those two pairs govern.
    """
    reversed_order = list(reversed(range(N_PLATFORMS)))
    for armed in range(N_PLATFORMS):
        present = [0] * N_PLATFORMS
        present[armed] = 4
        _platform_case(present, present_order=reversed_order, note=f"byte {armed} armed")


def test_draw_platforms_only_the_armed_platforms_are_drawn():
    """One platform at a time, so a candidate that indexed the wrong record shows up as a strip
    drawn in the wrong place."""
    for n in range(N_PLATFORMS):
        present = [0] * N_PLATFORMS
        present[n] = 4
        _platform_case(present, note=f"platform {n}")


@pytest.mark.parametrize("rows,cols", ((1, 1), (1, 4), (3, 1), (5, 3), (0, 2), (2, 0)))
def test_draw_platforms_blit_extents(rows, cols):
    """blit_or counts both extents with `subq.b`, so a 0 in either means 256 passes, not none.

    A 256-cell row is 2 KiB and 256 rows is 40 KiB, so these stay inside the staged screen only
    because the records are spaced 0x400 apart and the screen runs to SCREEN_BYTES; the overspill
    is harmless (both cores write the same bytes) and deliberate — it is what the original does.

    poison is off here because the poisoned pass would re-run a 256x256 blit on top of the normal
    one; the same shapes at poison=True are covered by the batteries above.
    """
    present = [0] * N_PLATFORMS
    present[1] = 2
    _platform_case(present, rows=rows, cols=cols, poison=False, note=f"{rows}x{cols}")


@pytest.mark.parametrize("screen_base", SCREEN_BASES)
def test_draw_platforms_screen_bases(screen_base):
    """A record's PSPR_DST_OFF is an offset FROM screen_base, which is re-read from the image.

    Every other case in this battery stages the framebuffer at the same address, so a candidate that
    hard-coded it would pass them all.
    """
    present = [0] * N_PLATFORMS
    present[1] = 2
    _platform_case(present, screen_base=screen_base)


# ------------------------------------------------------------------ flash_spawn_pad @ 0x13628

OBJ_VY = 0x08
OBJ_STEP_TIMER = 0x0b
SPAWN_SHIFT = 0x1
SPAWN_DST_OFF = 0xe
SPAWN_PAD_CELLS = 3
SPAWN_PAD_ROW_STRIDE = 8      # `struct.pack(">6I")` lays the three row masks 8 bytes apart
SPAWN_PAD_CELL_STRIDE = 2     # ... and steps two bytes per cell
SPAWN_PAD_PHASE_MASK = 3
SPAWN_PAD_PHASE_ALT = 1
SPAWN_PAD_ALT_FLAG = 4
SPAWN_PAD_COLOR_MASK = 7


def _spawn_point(shift, dst_off):
    rec = bytearray(SPAWN_RECORD)
    rec[SPAWN_SHIFT] = shift & 0xff       # the field is a byte, read zero-extended (`clr.l` + move.b)
    struct.pack_into(">H", rec, SPAWN_DST_OFF, dst_off & 0xffff)
    return bytes(rec)


def _spawn_case(step_timer, flags, spawn_index=0, shift=0, dst_off=0x400,
                colors=(0x0, 0x1, 0x2, 0x4, 0x8, 0x7, 0xf, 0x3), pattern=None,
                screen_base=SCREEN, poison=True):
    spawn_points = b"".join(_spawn_point(shift + n, dst_off + n * 0x100) for n in range(4))
    obj = bytearray(UNWRITTEN.to_bytes(1, "big") * OBJ_SIZE)
    obj[OBJ_STEP_TIMER] = step_timer
    struct.pack_into(">H", obj, OBJ_VY, (spawn_index * SPAWN_RECORD) & 0xffff)

    pokes = _blank_screen(screen_base)
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_SPAWN_PAD_COLORS: bytes(colors),
        A_SPAWN_PAD_PATTERN: pattern if pattern is not None
        else struct.pack(">6I", 0x0000ffff, 0xfffc0000, 0x00003fff,
                         0xfff00000, 0x00000fff, 0xffc00000),
        A_SPAWN_POINTS: spawn_points,
        OBJ_A: bytes(obj),
    })
    diffs, _ = differential(
        ENTRY_FLASH_SPAWN_PAD, {"a0": OBJ_A, "d0": flags, "_pokes": pokes},
        lambda lib, buf: lib.g_flash_spawn_pad(buf, OBJ_A, flags), poison=poison)
    assert not diffs, (f"step_timer={step_timer:#x} flags={flags:#x} spawn={spawn_index} "
                       f"shift={shift} screen_base={screen_base:#x}\n{report(diffs)}")


@pytest.mark.parametrize("step_timer", (0, 1, 2, 3, 4, 5, 6, 7, 0xfd, 0xfe, 0xff))
def test_flash_spawn_pad_phase_is_the_step_timer_mod_4(step_timer):
    """`and.l #$3` on the rider's step timer picks one of the first four colours."""
    _spawn_case(step_timer, flags=0)


@pytest.mark.parametrize("flags", (0, 1, 2, 3, 4, 5, 6, 7, 0xfff8, 0xffff))
def test_flash_spawn_pad_phase_1_substitutes_the_flags(flags):
    """On phase 1 ONLY, and only with bit 2 of the flags set, the colour index becomes flags & 7 —
    which is the only way the last four colour-table entries are ever reached."""
    for step_timer in (0, 1, 2, 3):
        _spawn_case(step_timer, flags=flags)


@pytest.mark.parametrize("colour", range(16))
def test_flash_spawn_pad_every_plane_select(colour):
    """Only the low four bits of the table byte matter (`btst d4,d2` for d4 = 3..0), and a clear bit
    ANDs the pad OUT of that plane rather than leaving it alone."""
    _spawn_case(0, flags=0, colors=(colour,) * 8)


@pytest.mark.parametrize("shift", (0, 1, 8, 15, 16, 17, 31, 32, 63, 64, 0xff))
def test_flash_spawn_pad_pixel_phase(shift):
    """The pad's row masks are shifted, not rotated (LSR.L, count mod 64), and only the low word of
    each result reaches the screen."""
    _spawn_case(0, flags=0, shift=shift)


@pytest.mark.parametrize("dst_off", (0x400, 0x7ffe, 0x8000, 0xfc00, 0xffff, 0))
def test_flash_spawn_pad_screen_offset_sign_extends(dst_off):
    """`adda.w 14(a1),a3` folds in the LOW WORD, sign-extended, so a record with bit 15 set paints
    ABOVE screen_base. Every other case here stages a small positive offset, which zero- and
    sign-extension agree on; these four do not."""
    _spawn_case(0, flags=0, dst_off=dst_off, shift=4)


@pytest.mark.parametrize("spawn_index", (0, 1, 2, 3))
def test_flash_spawn_pad_indexes_the_spawn_point_from_the_object(spawn_index):
    """The respawn path parks the spawn point's BYTE offset in the rider's velocity field, and it
    is folded in with `adda.w` — sign-extended."""
    _spawn_case(0, flags=0, spawn_index=spawn_index, shift=3)


@pytest.mark.parametrize("screen_base", SCREEN_BASES)
def test_flash_spawn_pad_screen_bases(screen_base):
    """The spawn point's SPAWN_DST_OFF is an offset FROM screen_base, which is re-read from the
    image — every other case in this battery stages the framebuffer at the same address."""
    _spawn_case(0, flags=0, shift=4, screen_base=screen_base)


def test_flash_spawn_pad_spawn_offset_sign_extends():
    """A negative offset walks BACKWARDS from spawn_points; the record is staged where it lands."""
    back = 0x40
    obj = bytearray(UNWRITTEN.to_bytes(1, "big") * OBJ_SIZE)
    struct.pack_into(">h", obj, OBJ_VY, -back)
    pokes = _blank_screen()
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", SCREEN),
        A_SPAWN_PAD_COLORS: bytes((0x5,) * 8),
        A_SPAWN_PAD_PATTERN: struct.pack(">6I", 0x0f0f0f0f, 0xf0f0f0f0, 0x00ff00ff,
                                         0xff00ff00, 0x33333333, 0xcccccccc),
        A_SPAWN_POINTS - back: _spawn_point(5, 0x800),
        OBJ_A: bytes(obj),
    })
    diffs, _ = differential(ENTRY_FLASH_SPAWN_PAD, {"a0": OBJ_A, "d0": 0, "_pokes": pokes},
                            lambda lib, buf: lib.g_flash_spawn_pad(buf, OBJ_A, 0), poison=True)
    assert not diffs, report(diffs)


FLASH_PAD_FUZZ_CHUNKS = 2


def _flash_pad_fuzz_cases():
    rng = random.Random(0x13628)                 # seeded ONCE — every chunk replays this stream
    for i in range(200):
        yield (i, rng.randrange(0x100), rng.randrange(0x100), rng.randrange(4),
               rng.choice((0, 1, 3, 7, 12, 15, 16, 31, 40)),
               tuple(rng.randrange(16) for _ in range(8)),
               struct.pack(">6I", *(rng.randrange(1 << 32) for _ in range(6))))


@pytest.mark.parametrize("chunk", range(FLASH_PAD_FUZZ_CHUNKS))
def test_flash_spawn_pad_fuzz(chunk):
    for i, step_timer, flags, spawn_index, shift, colors, pattern in _flash_pad_fuzz_cases():
        if i % FLASH_PAD_FUZZ_CHUNKS != chunk:
            continue
        _spawn_case(step_timer, flags, spawn_index=spawn_index, shift=shift,
                    colors=colors, pattern=pattern, poison=False)


# ------------------------------------------------------------------ animate_ground_shrink @ 0x175de

GA_ROWS_LATCH, GA_ROWS, GA_FLAME_LEFT, GA_FLAME_RIGHT = 0x0, 0x2, 0x4, 0x10
SPR_SRC, SPR_DST_OFF, SPR_SHIFT, SPR_CELL_SELECT = 0x0, 0x4, 0x8, 0xa
GROUND_SINK_SHIFT, GROUND_SINK_GAP, GROUND_ROWS_MIN, GROUND_SHRINK_WAVE = 0xc, 0x60, 0x11, 3
GROUND_X1_WRAP, GROUND_X1_RESET, GROUND_X0_RESET = 0x13e, 0x134, 0xfff5
CELL_PIXELS = 16        # the phase a creeping flame rolls over at (`cmpi.w #$10`)


def _flame(src, dst_off, shift, cell_select=0):
    return struct.pack(">IIHH", src, dst_off, shift & 0xffff, cell_select & 0xffff)


def _ga_block(rows_latch, rows, left, right):
    block = struct.pack(">HH", rows_latch & 0xffff, rows & 0xffff) + left + right
    assert len(block) == GA_BLOCK_BYTES
    return block


def _ground_case(rows_latch=8, rows=8, timer=1, wave=GROUND_SHRINK_WAVE,
                 left=None, right=None, ground_x=(0x20, 0x100), screen_base=SCREEN, note=""):
    """poison is off throughout: the block's SPR_SRC / SPR_DST_OFF are ADDRESSES the blits then
    dereference, so an inverted copy would aim both cores at random memory. The screen is
    pre-filled with a sentinel instead, and the block's own bytes are all outputs the diff sees."""
    left = left if left is not None else _flame(FLAME_FRAMES[0], 0x1000, 4)
    right = right if right is not None else _flame(FLAME_FRAMES[2], 0x1400, 0xa)
    pokes = _blank_screen(screen_base)
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_WAVE_NUM: bytes([wave]),
        A_GROUND_ANIM_TIMER: bytes([timer]),
        A_GROUND_ANIM: _ga_block(rows_latch, rows, left, right),
        A_GROUND_ANIM_NEXT: bytes([UNWRITTEN]) * GA_BLOCK_BYTES,
        A_GROUND_X0: struct.pack(">HH", ground_x[0] & 0xffff, ground_x[1] & 0xffff),
    })
    diffs, _ = differential(ENTRY_ANIMATE_GROUND_SHRINK, {"_pokes": pokes},
                            lambda lib, buf: lib.g_animate_ground_shrink(buf))
    assert not diffs, (f"latch={rows_latch} rows={rows} timer={timer} wave={wave} "
                       f"screen_base={screen_base:#x} {note}\n{report(diffs)}")


@pytest.mark.parametrize("rows_latch", (0, 1, 2, 8, 0x8000, 0xffff, 0x7fff))
def test_animate_ground_shrink_is_gated_on_the_latch(rows_latch):
    """`tst.w 0(a0) ; ble` — the latch is SIGNED, so 0xffff (-1) disarms the routine just as 0 does."""
    _ground_case(rows_latch=rows_latch)


@pytest.mark.parametrize("timer", (0, 1, 2, 3, 4, 0xff))
def test_animate_ground_shrink_steps_every_third_call(timer):
    """`subq.b #1` again: only a timer that reaches exactly 0 steps, and 0 wraps to 0xff."""
    _ground_case(timer=timer)


@pytest.mark.parametrize("src", FLAME_FRAMES + (FLAME_FRAME_END - FLAME_FRAME_BYTES - 1,
                                                FLAME_FRAME_END - FLAME_FRAME_BYTES,
                                                FLAME_FRAME_END, FLAME_FRAME_END + 1, 0xf0000))
def test_animate_ground_shrink_flame_frames_wrap(src):
    """Both flames step a whole frame per tick and wrap once the cursor reaches the end of the set.

    The compare is a SIGNED `cmpi.l` + `blt`, but that cannot be shown here: a cursor with bit 31
    set is also a cursor the blits would then dereference, and the reconstruction indexes a 1 MiB
    buffer where the 68000 masks to 24 bits. So the signed reading is asserted from the listing and
    exercised only over the in-image range, where signed and unsigned agree.
    """
    _ground_case(left=_flame(src, 0x1000, 4), right=_flame(src, 0x1400, 0xa),
                 note=f"src={src:#x}")


def test_animate_ground_shrink_sinks_when_the_flames_meet():
    """The sink needs BOTH the right flame's phase to be exactly GROUND_SINK_SHIFT and the two
    flames' byte gap to be at or under GROUND_SINK_GAP. The gap is a longword subtraction the
    original compares as a WORD, so only its low half decides."""
    left_dst = 0x1000
    for shift in (GROUND_SINK_SHIFT - 1, GROUND_SINK_SHIFT, GROUND_SINK_SHIFT + 1):
        for gap in (0, 1, GROUND_SINK_GAP - 1, GROUND_SINK_GAP, GROUND_SINK_GAP + 1,
                    0x10000, 0x10000 + GROUND_SINK_GAP, -0x10, 0x8000):
            _ground_case(rows=GROUND_ROWS_MIN + 1,
                         left=_flame(FLAME_FRAMES[0], left_dst, 4),
                         right=_flame(FLAME_FRAMES[1], (left_dst + gap) & 0xffffffff, shift),
                         note=f"shift={shift} gap={gap:#x}")


@pytest.mark.parametrize("rows", (1, 0x10, GROUND_ROWS_MIN, GROUND_ROWS_MIN + 1, 0x8000, 0xffff))
def test_animate_ground_shrink_climbs_back_when_too_short(rows):
    """Below GROUND_ROWS_MIN rows the strip climbs a scanline and grows a row back — and, unlike the
    sink branch, does NOT refresh the latch, so it cannot re-arm a routine that has run down."""
    _ground_case(rows_latch=8, rows=rows,
                 right=_flame(FLAME_FRAMES[2], 0x1400, GROUND_SINK_SHIFT + 1))


@pytest.mark.parametrize("wave", (0, 2, 3, 4, 0xff))
def test_animate_ground_shrink_only_wave_3_narrows_the_ground(wave):
    _ground_case(rows=GROUND_ROWS_MIN + 1, wave=wave,
                 right=_flame(FLAME_FRAMES[2], 0x1400, GROUND_SINK_SHIFT + 1))


@pytest.mark.parametrize("x1", (0x100, GROUND_X1_WRAP - 1, GROUND_X1_WRAP, GROUND_X1_WRAP + 1,
                                GROUND_X1_WRAP + 2, 0x8000, 0xffff))
def test_animate_ground_shrink_ground_edges_wrap(x1):
    """Past GROUND_X1_WRAP the two edges restart from a full width; either way both then step one
    pixel inward. The compare is signed, so 0x8000 (-32768) does not wrap."""
    _ground_case(rows=GROUND_ROWS_MIN + 1, ground_x=(0x20, x1),
                 right=_flame(FLAME_FRAMES[2], 0x1400, GROUND_SINK_SHIFT + 1))


@pytest.mark.parametrize("shift", (0, 1, CELL_PIXELS - 2, CELL_PIXELS - 1, CELL_PIXELS,
                                   CELL_PIXELS + 1, 0xffff))
def test_animate_ground_shrink_flames_creep_in_opposite_directions(shift):
    """The left flame's pixel phase counts up and rolls over into a whole cell right; the right
    flame's counts down and rolls over into a cell left. Both clear their cell-select on rollover."""
    _ground_case(rows=GROUND_ROWS_MIN + 1,
                 left=_flame(FLAME_FRAMES[0], 0x1000, shift, cell_select=0x5a5a),
                 right=_flame(FLAME_FRAMES[2], 0x1400, shift, cell_select=0x5a5a),
                 note=f"shift={shift}")


@pytest.mark.parametrize("cell_select", (0, 1, 0xff, 0x100, 0x1ff, 0x8000, 0xff80, 0x007f))
def test_animate_ground_shrink_cell_select_reaches_the_blits(cell_select):
    """blit_sprite reads only the LOW BYTE of the cell-select word, as a signed byte: < 0 draws the
    leading cell alone, > 0 the trailing one, 0 both. The block carries it through untouched unless
    a flame rolls over."""
    _ground_case(rows=GROUND_ROWS_MIN + 1, wave=0,
                 left=_flame(FLAME_FRAMES[0], 0x1000, 4, cell_select=cell_select),
                 right=_flame(FLAME_FRAMES[2], 0x1400, 0xa, cell_select=cell_select),
                 note=f"cell_select={cell_select:#x}")


def test_animate_ground_shrink_sink_outranks_the_climb():
    """With BOTH the sink and the climb conditions true the sink wins — it is the first arm of an
    `else if` chain, and only the sink refreshes the latch. The two named branch tests above each
    pin one arm while disarming the other, so neither reaches this overlap."""
    for rows in (1, GROUND_ROWS_MIN - 1, GROUND_ROWS_MIN):
        _ground_case(rows=rows, left=_flame(FLAME_FRAMES[0], 0x1000, 4),
                     right=_flame(FLAME_FRAMES[1], 0x1000 + GROUND_SINK_GAP, GROUND_SINK_SHIFT),
                     note=f"rows={rows}")


@pytest.mark.parametrize("shift", (GROUND_SINK_SHIFT, GROUND_SINK_SHIFT + 0x100,
                                   GROUND_SINK_SHIFT + 0x8000, GROUND_SINK_SHIFT ^ 0x0100))
def test_animate_ground_shrink_sink_gate_is_a_full_word_compare(shift):
    """`cmpi.w #$c,24(a4)` tests the whole word, so a shift whose LOW BYTE is 0xc but whose high
    byte is not zero must NOT sink. Every other case stages a shift under 0x12, where a low-byte
    compare and a word compare agree."""
    _ground_case(rows=GROUND_ROWS_MIN + 1,
                 left=_flame(FLAME_FRAMES[0], 0x1000, 4),
                 right=_flame(FLAME_FRAMES[1], 0x1000 + GROUND_SINK_GAP, shift),
                 note=f"shift={shift:#x}")


@pytest.mark.parametrize("shift", (0x7ffe, 0x7fff, 0x8000, 0x8001, 0xfffe))
def test_animate_ground_shrink_flame_rollover_is_signed(shift):
    """The rollover tests are signed: the left flame rolls over on `shift >= 16`, so 0x8000 (which
    is -32768) does NOT roll it over, and the right one rolls over on `shift < 0`, so 0x7fff does
    not. An unsigned reading flips both."""
    _ground_case(rows=GROUND_ROWS_MIN + 1,
                 left=_flame(FLAME_FRAMES[0], 0x1000, shift),
                 right=_flame(FLAME_FRAMES[2], 0x1400, shift),
                 note=f"shift={shift:#x}")


@pytest.mark.parametrize("screen_base", SCREEN_BASES)
def test_animate_ground_shrink_screen_bases(screen_base):
    """Both flame blits turn their record's SPR_DST_OFF into an address by adding screen_base, which
    they re-read from the image — every other case in this battery stages it at one address."""
    _ground_case(screen_base=screen_base)


GROUND_FUZZ_CHUNKS = 2


def _ground_fuzz_cases():
    rng = random.Random(0x175DE)                 # seeded ONCE — every chunk replays this stream
    for i in range(150):
        # The two shifts are drawn from the whole word often enough to reach the signed rollover
        # edges and the high half of the sink gate, not only the 0..0x11 band the game itself uses.
        shifts = [rng.randrange(0x12) if rng.random() < 0.7 else rng.randrange(0x10000)
                  for _ in range(2)]
        yield (i, rng.randint(1, 0x18), rng.randint(1, 0x18), rng.choice((0, 3, 4)),
               rng.choice(FLAME_FRAMES), rng.choice(FLAME_FRAMES),
               rng.randrange(0x1000, 0x4000) & ~7, rng.randrange(0x1000, 0x4000) & ~7,
               shifts[0], shifts[1],
               rng.randrange(0x10000), rng.randrange(0x10000))


@pytest.mark.parametrize("chunk", range(GROUND_FUZZ_CHUNKS))
def test_animate_ground_shrink_fuzz(chunk):
    for (i, latch, rows, wave, lsrc, rsrc, ldst, rdst, lshift, rshift,
         x0, x1) in _ground_fuzz_cases():
        if i % GROUND_FUZZ_CHUNKS != chunk:
            continue
        _ground_case(rows_latch=latch, rows=rows, wave=wave, ground_x=(x0, x1),
                     left=_flame(lsrc, ldst, lshift), right=_flame(rsrc, rdst, rshift),
                     note=f"case {i}")


# ------------------------------------------------------------------ dissolve_platforms @ 0x17438

EFF_TIMER, EFF_KIND, EFF_ROWS, EFF_COLS, EFF_SRC, EFF_DST = 0x0, 0x2, 0x4, 0x6, 0x8, 0xc
DISSOLVE_FRAMES = 0x1a
DISSOLVE_NOISE_ADVANCE = 0x8e   # how far rng_ptr is nudged before rng_advance re-steps it
DISSOLVE_PLANE23 = 4            # the planes-2/3 half of a cell
DISSOLVE_SPRITE_BASE = A_PLATFORM_SPRITES - PSPR_RECORD

# rng_ptr walks forwards 10 bytes per cell, so the noise block has to outlast the widest platform
# any case here stages (0x20 rows x 8 cols = 1600 bytes) plus the 0x8e nudge at the end.
NOISE_BYTES = 0x4000


def _effect(timer=0, kind=0, rows=0, cols=0, src=0, dst=0):
    return struct.pack(">HHHHII", timer & 0xffff, kind & 0xffff, rows & 0xffff, cols & 0xffff,
                       src, dst)


def _dissolve_pokes(effects, rows=3, cols=2, dst_off=0x1000, noise=None, screen_base=SCREEN):
    """One dissolving platform per staged slot; kind is 1-BASED into platform_sprites."""
    records = b"".join(
        _platform_sprite(A_PLATFORM_PRESENT + n, rows, cols,
                         SPRITE + n * 0x400, dst_off + n * 0x800)
        for n in range(N_PLATFORMS))
    pokes = _blank_screen(screen_base)
    pokes.update({
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_PLATFORM_SPRITES: records,
        A_EFFECT_TABLE: b"".join(effects),
        A_RNG_PTR: struct.pack(">I", NOISE),
        SPRITE: bytes(range(1, 0x100)) * 0x20,
        NOISE: noise if noise is not None else bytes(range(0x100)) * (NOISE_BYTES // 0x100),
    })
    return pokes


def _dissolve_case(pokes, note=""):
    """poison is off: EFF_SRC / EFF_DST are cursors the next call dereferences, so inverting them
    aims both cores at arbitrary memory. Everything the routine writes is compared directly."""
    diffs, _ = differential(ENTRY_DISSOLVE_PLATFORMS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_dissolve_platforms(buf))
    assert not diffs, f"{note}\n{report(diffs)}"


def _free_slots(n):
    return [_effect()] * n


@pytest.mark.parametrize("kind", (0, 1, 2, 3, 8))
def test_dissolve_platforms_kind_zero_is_a_free_slot(kind):
    """EFF_KIND indexes platform_sprites 1-based (the base is one record BELOW the table), and 0
    means the slot is free — the only value that skips the record entirely."""
    _dissolve_case(_dissolve_pokes([_effect(kind=kind)] + _free_slots(N_EFFECTS - 1)),
                   note=f"kind={kind}")


def test_dissolve_platforms_kind_index_is_a_sign_extended_word():
    """`mulu.w #$10,d0 ; adda.w d0,a4` — the record offset is the LOW WORD of kind * 0x10, SIGN
    extended. The game only ever stores 1..8, where both conversions are invisible, so these two
    are the only cases that can tell the reconstruction's `sign_ext16` from a plain 32-bit add.

    kind 0x1001 truncates back onto platform 0's record; kind 0x800 makes the offset -0x8000, which
    lands below the load base — staged with a record of its own so the run stays bounded.
    """
    below_base = DISSOLVE_SPRITE_BASE - 0x8000
    for kind, extra in ((0x1001, {}),
                        (0x800, {below_base: _platform_sprite(A_PLATFORM_PRESENT, 2, 2,
                                                              SPRITE, 0x1000)})):
        pokes = _dissolve_pokes([_effect(kind=kind)] + _free_slots(N_EFFECTS - 1))
        pokes.update(extra)
        _dissolve_case(pokes, note=f"kind={kind:#x}")


@pytest.mark.parametrize("screen_base", SCREEN_BASES)
def test_dissolve_platforms_screen_bases(screen_base):
    """The FIRST frame is the only pass that reads screen_base: it turns the platform record's
    PSPR_DST_OFF into the cursor every later frame then carries in the slot. So the slot has to be
    staged fresh (EFF_TIMER == 0) — a running slot never looks at screen_base at all.
    """
    _dissolve_case(_dissolve_pokes([_effect(kind=1)] + _free_slots(N_EFFECTS - 1),
                                   screen_base=screen_base),
                   note=f"screen_base={screen_base:#x}")


def test_dissolve_platforms_first_frame_latches_the_geometry():
    """A slot with EFF_TIMER == 0 runs the extra pass that copies rows/cols out of the platform
    record, knocks the bitmap down to its plane-3 silhouette and leaves the two cursors at the far
    corner — then dissolves in the same call."""
    # (0x102, 0x101) has the same LOW bytes as (2, 1): the setup sweep's `subq.b` counters must
    # ignore the high halves, which every other pair here leaves at zero.
    for rows, cols in ((1, 1), (1, 4), (3, 2), (5, 3), (8, 6), (0x102, 0x101), (0x100, 0x102)):
        _dissolve_case(_dissolve_pokes([_effect(kind=1)] + _free_slots(N_EFFECTS - 1),
                                       rows=rows, cols=cols),
                       note=f"{rows}x{cols}")


@pytest.mark.parametrize("timer", (1, 2, 3, DISSOLVE_FRAMES - 1, DISSOLVE_FRAMES))
def test_dissolve_platforms_running_slot_skips_the_setup(timer):
    """With EFF_TIMER already set the slot carries its own geometry and cursors, and the setup pass
    must NOT run again. Timer 1 is the last frame, which lays no noise at all."""
    rows, cols = 3, 2
    src = SPRITE + rows * cols * CELL_BYTES
    dst = SCREEN + 0x1000 + (rows - 1) * SCREEN_ROW_BYTES + cols * CELL_BYTES
    _dissolve_case(_dissolve_pokes(
        [_effect(timer=timer, kind=1, rows=rows, cols=cols, src=src, dst=dst)]
        + _free_slots(N_EFFECTS - 1)), note=f"timer={timer}")


def test_dissolve_platforms_extents_count_low_bytes():
    """Both extents are `subq.b` counters: only their low byte counts, and 0 means 256 passes.

    Rows is read once, above the row loop, while COLS is re-read from the record on every row — so
    a cols value whose high byte differs proves the reconstruction reads the same width.
    """
    for rows, cols in ((1, 1), (0x100, 1), (1, 0x100), (0x102, 0x102), (3, 0x203)):
        src = SPRITE
        dst = SCREEN + 0x1000
        _dissolve_case(_dissolve_pokes(
            [_effect(timer=2, kind=1, rows=rows, cols=cols, src=src, dst=dst)]
            + _free_slots(N_EFFECTS - 1)), note=f"{rows:#x}x{cols:#x}")


def test_dissolve_platforms_noise_all_zero_becomes_all_ones():
    """The four noise words are ORed together, and `not.w` flips the result only when it comes out
    ZERO — the one input that makes the crumble solid instead of empty."""
    rows, cols = 2, 2
    for noise in (bytes(NOISE_BYTES),                       # every word zero
                  b"\x00\x01" * (NOISE_BYTES // 2),         # never zero
                  (bytes(10) + b"\xff" * 10) * (NOISE_BYTES // 20)):
        _dissolve_case(_dissolve_pokes(
            [_effect(timer=3, kind=1, rows=rows, cols=cols,
                     src=SPRITE, dst=SCREEN + 0x1000)] + _free_slots(N_EFFECTS - 1),
            noise=noise), note=f"noise={noise[:4]!r}")


def test_dissolve_platforms_rng_cursor_wraps():
    """The cursor is handed back to rng_advance, whose limit compare is SIGNED and whose reset lands
    at the load base. Starting it just under and just over the limit exercises both."""
    limit = _defines("src/rng.c")["RNG_PTR_LIMIT"]
    for start in (limit - DISSOLVE_NOISE_ADVANCE - 4, limit - DISSOLVE_NOISE_ADVANCE - 2,
                  limit, limit + 0x100, NOISE):
        pokes = _dissolve_pokes([_effect(timer=2, kind=1, rows=2, cols=2,
                                         src=SPRITE, dst=SCREEN + 0x1000)]
                                + _free_slots(N_EFFECTS - 1))
        pokes[A_RNG_PTR] = struct.pack(">I", start)
        _dissolve_case(pokes, note=f"rng_ptr={start:#x}")


def test_dissolve_platforms_walks_every_slot():
    """All four slots run in one call, and each carries its own cursors — the noise cursor threads
    from one to the next, so a slot skipped or run twice changes every later slot's crumble."""
    for live in ((0,), (3,), (0, 3), (0, 1, 2, 3), (1, 2)):
        effects = [_effect(timer=2 + n, kind=n + 1, rows=2, cols=2,
                           src=SPRITE + n * 0x400,
                           dst=SCREEN + 0x1000 + n * 0x800) if n in live else _effect()
                   for n in range(N_EFFECTS)]
        _dissolve_case(_dissolve_pokes(effects), note=f"live={live}")


def test_dissolve_platforms_record_is_reread_as_it_is_overdrawn():
    """The crumble re-reads EFF_COLS once per ROW and EFF_TIMER once per CELL; the trailing pass
    reads EFF_COLS ONCE. Nothing can tell those apart unless the destination covers the record.

    So point the cursor at effect_table itself. The first cell's erase ANDs `~dup16(silhouette)`
    over the slot's own header, which with silhouette = 0x0004 knocks EFF_COLS from 5 down to 1 and
    EFF_TIMER from 5 down to 1 — narrowing the next row and turning the noise off partway through.
    Bits can only be cleared, so the walk cannot run away.
    """
    rows, cols, timer, silhouette = 2, 5, 5, 0x0004
    sprite = bytearray(0x400)
    for cell in range(0x80):                       # the plane-3 word of every cell
        struct.pack_into(">H", sprite, cell * CELL_BYTES + 6, silhouette)
    pokes = _dissolve_pokes(
        [_effect(timer=timer, kind=1, rows=rows, cols=cols,
                 src=SPRITE + 0x200, dst=A_EFFECT_TABLE + CELL_BYTES)]
        + _free_slots(N_EFFECTS - 1))
    pokes[SPRITE] = bytes(sprite)
    # The cursor walks backwards out of the record into the memory below it, which the loaded image
    # leaves zero — and an AND of zero writes nothing. Lay the patterned cell there so a row that
    # runs the wrong NUMBER of cells actually shows up as a diff.
    below = A_EFFECT_TABLE - 0x180
    pokes[below] = _SCREEN_CELL * ((A_EFFECT_TABLE - below) // CELL_BYTES)
    _dissolve_case(pokes, note="destination over effect_table")


def test_dissolve_platforms_trailing_pass_reads_its_extent_once():
    """The trailing pass fetches EFF_COLS ONCE — its loop-back lands past the fetch, unlike the
    crumble's, which re-reads it per row.

    The two passes erase with different words of the sprite (plane 3 for the crumble, plane 2 for
    the trailing row), so a sprite with an empty plane 3 leaves the record untouched while the
    walk crosses it, and then lets the trailing pass knock EFF_COLS from 5 down to 1 on its FIRST
    cell. Re-reading would stop it there; the original runs all five.
    """
    rows, cols = 1, 5
    sprite = bytearray(0x400)
    for cell in range(0x80):                       # plane 2 set, plane 3 (offset +6) left clear
        struct.pack_into(">H", sprite, cell * CELL_BYTES + 4, 0x0004)
    pokes = _dissolve_pokes(
        [_effect(timer=3, kind=1, rows=rows, cols=cols,
                 src=SPRITE + 0x200, dst=A_EFFECT_TABLE + cols * CELL_BYTES)]
        + _free_slots(N_EFFECTS - 1))
    pokes[SPRITE] = bytes(sprite)
    _dissolve_case(pokes, note="trailing pass over effect_table")


DISSOLVE_FUZZ_CHUNKS = 2


def _dissolve_fuzz_cases():
    rng = random.Random(0x17438)                 # seeded ONCE — every chunk replays this stream
    for i in range(120):
        rows, cols = rng.randint(1, 10), rng.randint(1, 6)
        yield (i, rng.randint(1, DISSOLVE_FRAMES), rng.randint(1, N_PLATFORMS), rows, cols,
               SPRITE + rng.randrange(0, 0x400) * CELL_BYTES,
               SCREEN + 0x1000 + rng.randrange(0, 0x40) * SCREEN_ROW_BYTES,
               bytes(rng.randrange(0x100) for _ in range(0x200)) * (NOISE_BYTES // 0x200))


@pytest.mark.parametrize("chunk", range(DISSOLVE_FUZZ_CHUNKS))
def test_dissolve_platforms_fuzz(chunk):
    for i, timer, kind, rows, cols, src, dst, noise in _dissolve_fuzz_cases():
        if i % DISSOLVE_FUZZ_CHUNKS != chunk:
            continue
        _dissolve_case(_dissolve_pokes(
            [_effect(timer=timer, kind=kind, rows=rows, cols=cols, src=src, dst=dst)]
            + _free_slots(N_EFFECTS - 1), noise=noise), note=f"case {i}")


# ------------------------------------------------------------------ the mirrored-constant pin

def test_entry_addresses_match_names_txt():
    """Every entry this battery drives is the address names.txt gives that function."""
    expected = {
        ENTRY_DRAW_PLATFORMS: "draw_platforms",
        ENTRY_FLASH_SPAWN_PAD: "flash_spawn_pad",
        ENTRY_START_DEATH_ANIM: "start_death_anim",
        ENTRY_TROLL_ERASE_HAND: "troll_erase_hand",
        ENTRY_TROLL_DRAW_HAND: "troll_draw_hand",
        ENTRY_DISSOLVE_PLATFORMS: "dissolve_platforms",
        ENTRY_RAISE_FLOOR: "raise_floor",
        ENTRY_ANIMATE_GROUND_SHRINK: "animate_ground_shrink",
    }
    for addr, name in expected.items():
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_constants_match_the_headers():
    """Every constant this file restates equals the one src/world.c compiles against.

    This is not optional bookkeeping. A drifted address here would be INVISIBLE to the differential:
    the test would stage its inputs at a dead address, both cores would read the game's own static
    data at the real one, agree, and go green having proved nothing.
    """
    world_h = _defines("include/world.h")
    addrs_h = _defines("include/addrs.h")
    joust_h = _defines("include/joust.h")
    draw_h = _defines("include/draw.h")
    object_h = _defines("include/object.h")
    world_c = _defines("src/world.c")

    for name, value in (
            ("A_wave_num", A_WAVE_NUM),
            ("A_floor_step_timer", A_FLOOR_STEP_TIMER),
            ("A_floor_rows_left", A_FLOOR_ROWS_LEFT),
            ("A_ground_anim_timer", A_GROUND_ANIM_TIMER),
            ("A_ground_anim", A_GROUND_ANIM), ("A_ground_anim_next", A_GROUND_ANIM_NEXT),
            ("A_troll_prev_dst", A_TROLL_PREV_DST),
            ("A_troll_prev_src", A_TROLL_PREV_SRC), ("A_troll_prev_shift", A_TROLL_PREV_SHIFT),
            ("A_troll_prev_rows", A_TROLL_PREV_ROWS),
            ("A_effect_table", A_EFFECT_TABLE), ("A_effect_table_END", A_EFFECT_TABLE_END),
            ("A_ground_x0", A_GROUND_X0), ("A_ground_x1", A_GROUND_X1),
            ("A_spawn_pad_colors", A_SPAWN_PAD_COLORS),
            ("A_spawn_pad_pattern", A_SPAWN_PAD_PATTERN),
            ("A_spawn_points", A_SPAWN_POINTS),
            ("A_death_sprite_p1", A_DEATH_SPRITE_P1),
            ("A_death_sprite_other", A_DEATH_SPRITE_OTHER),
            # field offsets and geometry the packers above encode POSITIONALLY, in a struct.pack
            # format string — nothing else would catch these drifting
            ("PSPR_COLS", PSPR_COLS), ("PSPR_SRC", PSPR_SRC),
            ("SPAWN_SHIFT", SPAWN_SHIFT), ("SPAWN_DST_OFF", SPAWN_DST_OFF),
            ("GA_ROWS_LATCH", GA_ROWS_LATCH), ("GA_ROWS", GA_ROWS),
            ("GA_FLAME_LEFT", GA_FLAME_LEFT), ("GA_FLAME_RIGHT", GA_FLAME_RIGHT),
            ("GA_BLOCK_BYTES", GA_BLOCK_BYTES),
            ("EFF_TIMER", EFF_TIMER), ("EFF_KIND", EFF_KIND), ("EFF_ROWS", EFF_ROWS),
            ("EFF_COLS", EFF_COLS), ("EFF_SRC", EFF_SRC), ("EFF_DST", EFF_DST),
            ("EFF_RECORD", EFF_RECORD),
            # the branch thresholds the batteries above straddle by name
            ("FLAME_FRAME_BYTES", FLAME_FRAME_BYTES), ("FLAME_FRAME_FIRST", FLAME_FRAME_FIRST),
            ("FLAME_FRAME_END", FLAME_FRAME_END),
            ("GROUND_SINK_SHIFT", GROUND_SINK_SHIFT), ("GROUND_SINK_GAP", GROUND_SINK_GAP),
            ("GROUND_ROWS_MIN", GROUND_ROWS_MIN), ("GROUND_SHRINK_WAVE", GROUND_SHRINK_WAVE),
            ("GROUND_X1_WRAP", GROUND_X1_WRAP), ("GROUND_X1_RESET", GROUND_X1_RESET),
            ("GROUND_X0_RESET", GROUND_X0_RESET),
            ("DISSOLVE_FRAMES", DISSOLVE_FRAMES), ("PLATFORM_SPENT", PLATFORM_SPENT),
            ("PLATFORM_COUNT", N_PLATFORMS),
            ("DISSOLVE_NOISE_ADVANCE", DISSOLVE_NOISE_ADVANCE),
            ("DISSOLVE_PLANE23", DISSOLVE_PLANE23),
            ("FLOOR_STEP_FRAMES", FLOOR_STEP_FRAMES),
            # strides and counts the packers/generators encode positionally
            ("TROLL_MASK_ROW_BYTES", TROLL_MASK_ROW_BYTES),
            ("SPAWN_PAD_CELLS", SPAWN_PAD_CELLS),
            ("SPAWN_PAD_ROW_STRIDE", SPAWN_PAD_ROW_STRIDE),
            ("SPAWN_PAD_CELL_STRIDE", SPAWN_PAD_CELL_STRIDE),
            ("SPAWN_PAD_PHASE_MASK", SPAWN_PAD_PHASE_MASK),
            ("SPAWN_PAD_PHASE_ALT", SPAWN_PAD_PHASE_ALT),
            ("SPAWN_PAD_ALT_FLAG", SPAWN_PAD_ALT_FLAG),
            ("SPAWN_PAD_COLOR_MASK", SPAWN_PAD_COLOR_MASK)):
        assert world_h[name] == value, f"{name}: world.h has {world_h[name]:#x}, test has {value:#x}"

    assert world_c["DEATH_SPRITE_RISE"] == DEATH_SPRITE_RISE
    assert A_PLATFORM_SPRITES - object_h["PSPR_RECORD"] == DISSOLVE_SPRITE_BASE

    # raise_floor hands paint_floor_row an address the ORIGINAL's callee advances; world.h spells
    # that advance out, so pin it to the strip src/draw.c actually paints (CLAUDE.md's rule for a
    # value that must agree across two places neither of which can import the other).
    assert world_h["FLOOR_PAINT_ADVANCE"] == _defines("src/draw.c")["FLOOR_ROW_CELLS"] * CELL_BYTES

    for defines, origin, mirrored in (
            (addrs_h, "addrs.h", {"A_screen_base": A_SCREEN_BASE, "A_rng_ptr": A_RNG_PTR,
                                  "A_playfield_bottom": A_PLAYFIELD_BOTTOM,
                                  "A_object_table": A_OBJECT_TABLE, "A_draw_dst": A_DRAW_DST,
                                  "A_draw_src": A_DRAW_SRC, "A_draw_shift": A_DRAW_SHIFT,
                                  "A_draw_rows": A_DRAW_ROWS}),
            (joust_h, "joust.h", {"OBJ_SIZE": OBJ_SIZE, "CELL_BYTES": CELL_BYTES,
                                  "CELL_PIXELS": CELL_PIXELS,
                                  "CELL_PLANE_WORDS": CELL_PLANE_WORDS,
                                  "SCREEN_ROW_BYTES": SCREEN_ROW_BYTES,
                                  "OBJ_VY": OBJ_VY, "OBJ_STEP_TIMER": OBJ_STEP_TIMER,
                                  "OBJ_PREV_DST": OBJ_PREV_DST,
                                  "OBJ_PREV_SHIFT": OBJ_PREV_SHIFT,
                                  "OBJ_EGG_STATE": OBJ_EGG_STATE, "OBJ_EGG_DST": OBJ_EGG_DST,
                                  "OBJ_EGG_SRC": OBJ_EGG_SRC, "OBJ_EGG_ROWS": OBJ_EGG_ROWS,
                                  "OBJ_EGG_SHIFT": OBJ_EGG_SHIFT}),
            (world_h, "world.h", {"OBJ_EGG_CHAIN": OBJ_EGG_CHAIN,
                                  "OBJ_SCORE_PENDING": OBJ_SCORE_PENDING}),
            (draw_h, "draw.h", {"SPR_MASK_OFF": SPR_MASK_OFF, "SPR_SRC": SPR_SRC,
                                "SPR_DST_OFF": SPR_DST_OFF, "SPR_SHIFT": SPR_SHIFT,
                                "SPR_CELL_SELECT": SPR_CELL_SELECT}),
            (object_h, "object.h", {"A_platform_present": A_PLATFORM_PRESENT,
                                    "A_platform_sprites": A_PLATFORM_SPRITES,
                                    "PSPR_PRESENT": PSPR_PRESENT, "PSPR_ROWS": PSPR_ROWS,
                                    "PSPR_DST_OFF": PSPR_DST_OFF,
                                    "PSPR_RECORD": PSPR_RECORD})):
        for name, value in mirrored.items():
            assert defines[name] == value, (f"{name}: {origin} has {defines[name]:#x}, "
                                            f"test has {value:#x}")


def test_scratch_areas_are_clear_of_everything_the_model_owns():
    """The staged blocks must sit above the program and below the stack guard, or a case would be
    poking over the game's own code or into the band the diff drops.

    They must also be disjoint from EACH OTHER, which the SCREEN_BASES sweep depends on: those
    batteries prove screen_base is re-read by filling the block they name and leaving the default one
    at the image's zeros. Let SCREEN_ALT overlap SCREEN and both cores read the same pattern either
    way — every case still passes, having stopped discriminating a hard-coded framebuffer.
    """
    program_end = 0x2b7ae
    blocks = (("SPRITE", SPRITE, 0x8000), ("NOISE", NOISE, NOISE_BYTES),
              ("SCREEN", SCREEN, SCREEN_BYTES), ("SCREEN_ALT", SCREEN_ALT, SCREEN_BYTES),
              ("OBJ_A", OBJ_A, OBJ_SIZE))
    for name, lo, size in blocks:
        assert lo >= program_end, f"{name} overlaps the program"
        assert lo + size <= emu.STACK_GUARD_LO, f"{name} runs into the stack guard"
        assert not (lo < abi.RESULT + 8 and abi.STUB < lo + size), f"{name} overlaps abi's stub"

    for i, (name, lo, size) in enumerate(blocks):
        for other, o_lo, o_size in blocks[i + 1:]:
            assert lo >= o_lo + o_size or o_lo >= lo + size, f"{name} overlaps {other}"
