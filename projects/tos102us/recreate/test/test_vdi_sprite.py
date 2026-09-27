"""The SPRITE PAIR (`src/vdi/mouse.c`): $fcffb0 `$a00d` draw_sprite and $fd0184 `$a00c` undraw_sprite.

Every draw is staged over `vdi_raster`'s pseudo-random canvas — every plane of every group differs from its
neighbours — with a form whose every row word is its own (`vdi_mouse.RANDOM_ROWS`), a save block FILLed, and
junk in the position registers' high words, which the ROM never reads. The byte diff then sees the screen
AND the save block: which words were saved, in which order, and how they were combined.

THE COLOURS reach a plane as `$fd00c8`'s index — the form's XOR sign, then that plane's fg bit, then its bg
bit — so fg = %0011 over bg = %0101 runs all four REPLACE fragments in one four-plane draw, and the same
with the planes word negative runs the four XOR ones.

WHAT NO CASE HERE STAGES: a row count the clip makes NEGATIVE (a y or x far past the screen, or a hot spot 16
or more away — only a Line-A caller's own form) runs the `dbf` 65,535 times over memory, and the restore of
a length of 0 runs 65,536 rows: memory smashes across the whole address space, reconstructed to the ROM's
arithmetic (`mouse.c`) and left unstaged.

THE STRICT MUTATION SWEEP over mouse.c (`recreate/README.md`, "Mutation sweeps"): three survivors, each
EQUIVALENT — the top clip taken at y = hot_y and the bottom at y = DEV_TAB[1] - 15 (both arms compute the
same 16 rows from row 0 or y), and a form row's data word read before its mask (two reads, nothing between).
A poll_key whose test is inverted reads an empty ring and ABORTS on the BIOS core's own diagnostic: ABNORMAL.
"""
import pytest

from harness import BASE_IMAGE, addrs

import case
import vdi
import vdi_mouse as mouse
from case import merge_pokes

DRAW = "LINEA_ROM_DRAW_SPRITE"
UNDRAW = "LINEA_ROM_UNDRAW_SPRITE"
HIGH_JUNK = 0x5A5A_0000             # the position registers' high words: never read
ALL_REPLACE_OPS = (0b0011, 0b0101)  # (fg, bg): planes 0..3 take fragments 3, 2, 1, 0
XOR_PLANES = (0xFFFF, 0x8000)       # the planes word's sign selects the XOR fragments
MIDDLE = (160, 100)
LAST_X, LAST_Y = mouse.LOW["last"]
EDGE = mouse.SPRITE_ROWS - 1        # the last x (y) all sixteen columns (rows) fit at is LAST - EDGE
NOTHING_SAVED = 0xFE                # a STAT byte with every bit but the valid one set


def draw_pokes(resolution=mouse.LOW, **form):
    return merge_pokes(mouse.canvas_pokes(resolution), mouse.form_pokes(**form), mouse.save_block_pokes())


def draw(x, y, pokes):
    return vdi.run_primitive(DRAW, mouse.sprite_registers(HIGH_JUNK | x & 0xFFFF, HIGH_JUNK | y & 0xFFFF), pokes)


def saved_length(result):
    return result.word(mouse.SAVE_BLOCK_AT + mouse.SAVE_LEN)


def saved_status(result):
    return result.after(mouse.SAVE_BLOCK_AT + mouse.SAVE_STAT, 1)[0]


LONG_ROWS = 1 << mouse.MOUSE_H["SPRITE_SAVE_LONG_BIT"]
VALID = 1 << mouse.MOUSE_H["SPRITE_SAVE_VALID_BIT"]


# ---- every x alignment, and the colour fragments --------------------------------------------------------

@pytest.mark.parametrize("shift", range(16))
def test_draw_at_every_alignment_spreads_the_form_over_two_groups(shift):
    """`ror.l` below 8 pixels in and `rol.l` from 8 on: one spread, `(word << 16) >> shift`."""
    fg, bg = ALL_REPLACE_OPS
    result = draw(MIDDLE[0] + shift, MIDDLE[1], draw_pokes(fg=fg, bg=bg, hot_x=0, hot_y=0))
    assert saved_status(result) & (VALID | LONG_ROWS) == VALID | LONG_ROWS
    assert saved_length(result) == mouse.SPRITE_ROWS


@pytest.mark.parametrize("planes", XOR_PLANES)
@pytest.mark.parametrize("shift", (0, 7, 8, 15))
def test_a_negative_planes_word_draws_with_the_xor_fragments(planes, shift):
    fg, bg = ALL_REPLACE_OPS
    draw(MIDDLE[0] + shift, MIDDLE[1], draw_pokes(fg=fg, bg=bg, planes=planes, hot_x=3, hot_y=9))


@pytest.mark.parametrize("fg,bg", ((0, 0), (0xF, 0xF), (0xF, 0), (0, 0xF), (0b1001, 0b0110), (0xFFF0, 0x000F)))
@pytest.mark.parametrize("planes", (1, 0x7FFF, -1))
def test_every_colour_pair_shifts_one_bit_a_plane(fg, bg, planes):
    """The colours are shifted right a bit per plane on the ROM's own stack (`lsr.w 2(sp)`); bits past
    the last plane are never read, and a positive planes word of any size draws by REPLACE."""
    draw(MIDDLE[0] + 5, MIDDLE[1] + 3, draw_pokes(fg=fg, bg=bg, planes=planes, hot_x=2, hot_y=2))


# ---- the clip, at each edge and corner ---------------------------------------------------------------------
# (x, y, hot_x, hot_y) in low resolution (319 x 199), and what the save block says about it.
LEFT, RIGHT, TOP, BOTTOM = "left", "right", "top", "bottom"
CLIPS = {
    "left, one column off": (4, 100, 5, 0),
    "left, fifteen off": (0, 100, 15, 0),
    "left, x itself below the hot spot by one": (0, 100, 1, 0),
    "right, the last unclipped x": (304, 100, 0, 0),
    "right, one past it": (305, 100, 0, 0),
    "right, the last column": (319, 100, 0, 0),
    "right, past the screen": (330, 100, 0, 0),
    "top, one row off": (100, 3, 0, 4),
    "top, fifteen off": (100, 0, 0, 15),
    "bottom, the last unclipped y": (100, 184, 0, 0),
    "bottom, one past it": (100, 185, 0, 0),
    "bottom, the last row": (100, 199, 0, 0),
    "top-left corner": (2, 1, 9, 6),
    "top-right corner": (316, 0, 0, 12),
    "bottom-left corner": (0, 199, 3, 0),
    "bottom-right corner": (319, 199, 1, 1),
}


@pytest.mark.parametrize("name", CLIPS)
def test_the_sprite_clipped_at_each_edge_saves_and_draws_what_is_left(name):
    x, y, hot_x, hot_y = CLIPS[name]
    fg, bg = ALL_REPLACE_OPS
    result = draw(x, y, draw_pokes(fg=fg, bg=bg, hot_x=hot_x, hot_y=hot_y))
    clipped_x = x < hot_x or x - hot_x > LAST_X - EDGE
    assert bool(saved_status(result) & LONG_ROWS) == (not clipped_x)


@pytest.mark.parametrize("name", ("left, one column off", "right, one past it", "top, one row off",
                                  "bottom, one past it"))
def test_the_clipped_sprite_by_xor(name):
    x, y, hot_x, hot_y = CLIPS[name]
    fg, bg = ALL_REPLACE_OPS
    draw(x, y, draw_pokes(fg=fg, bg=bg, planes=-1, hot_x=hot_x, hot_y=hot_y))


def test_the_clip_reads_dev_tab_not_the_screen_s_width():
    """A DEV_TAB below 15 makes `max - 15` negative, which the UNSIGNED compare reads as huge: nothing is
    clipped at the right or bottom however far out the sprite is."""
    pokes = merge_pokes(draw_pokes(), vdi.linea_pokes(DEV_TAB=[10, 12]))
    result = draw(40, 30, pokes)
    assert saved_status(result) & LONG_ROWS and saved_length(result) == mouse.SPRITE_ROWS


# ---- the three screen shapes -------------------------------------------------------------------------------

@pytest.mark.parametrize("resolution", ("medium", "high"))
@pytest.mark.parametrize("where", ((321, 150), (0, 0), (639, 199), (636, 197), (8, 3)))
def test_one_and_two_planes(resolution, where):
    shape = mouse.RESOLUTIONS[resolution]
    fg, bg = ALL_REPLACE_OPS
    draw(*where, draw_pokes(shape, fg=fg, bg=bg, hot_x=4, hot_y=4))


@pytest.mark.parametrize("resolution", ("medium", "high"))
def test_one_and_two_planes_by_xor(resolution):
    draw(333, 111, draw_pokes(mouse.RESOLUTIONS[resolution], fg=0b10, bg=0b01, planes=-1))


def test_a_planes_word_of_zero_draws_by_replace():
    """`tst.w` / `bge`: zero is not negative — what vsc_form stores for intin[2] = 0."""
    fg, bg = ALL_REPLACE_OPS
    draw(MIDDLE[0] + 3, MIDDLE[1], draw_pokes(fg=fg, bg=bg, planes=0))


# BYTES_LIN large enough that the row's offset passes 32767, where `adda.w` takes it NEGATIVE: the sprite
# lands 64 KB below where the row would be — in free RAM below the screen, which the diff compares.
WRAPPING_BYTES_LIN = 0xC0
WRAPPING_ROW = 190


def test_a_row_offset_past_32767_is_added_as_a_negative_word():
    pokes = merge_pokes(draw_pokes(), vdi.linea_pokes(BYTES_LIN=WRAPPING_BYTES_LIN))
    assert WRAPPING_ROW * WRAPPING_BYTES_LIN > 0x7FFF
    draw(100, WRAPPING_ROW, pokes)


@pytest.mark.parametrize("planes", (0, 3, 8))
def test_any_plane_count(planes):
    fg, bg = ALL_REPLACE_OPS
    draw(96, 60, merge_pokes(draw_pokes(fg=fg, bg=bg), vdi.linea_pokes(PLANES=planes)))


def test_the_line_step_is_width_and_the_row_bytes_lin():
    """WIDTH steps a row (`adda.w d4`); concat places the first by BYTES_LIN — made to disagree."""
    for skew in (-8, 8):
        draw(150, 60, merge_pokes(draw_pokes(), vdi.linea_pokes(WIDTH=160 + skew)))


# A Line-A caller's save block laid so its save area IS the form's first row: each row's screen words are
# saved (`move.l d2,(a2)+`) BEFORE its form words are read (`jmp (a3)`), so the form the draw combines is
# the screen it just saved — row by row, down the form. Unclipped (long saves) and clipped at each edge (word
# saves, the form hot spot moved to put x left of it).
SAVE_AREA_OVER_THE_FORM = mouse.FORM_AT + mouse.MOUSE_H["SPRITE_FORM_ROWS"] - mouse.SAVE_AREA
OVERLAPPED_DRAWS = {"both groups": (MIDDLE[0] + 5, 0), "clipped left": (3, 8), "clipped right": (LAST_X - 4, 0)}


@pytest.mark.parametrize("x, hot_x", OVERLAPPED_DRAWS.values(), ids=OVERLAPPED_DRAWS.keys())
def test_a_row_is_saved_before_its_form_words_are_read(x, hot_x):
    fg, bg = ALL_REPLACE_OPS
    pokes = merge_pokes(mouse.canvas_pokes(), mouse.form_pokes(fg=fg, bg=bg, hot_x=hot_x))
    vdi.run_primitive(DRAW, mouse.sprite_registers(x, MIDDLE[1], save_block=SAVE_AREA_OVER_THE_FORM), pokes)


# ---- the restore -------------------------------------------------------------------------------------------

def restore(result, save_block=mouse.SAVE_BLOCK_AT, refilled=()):
    """`$a00c` over the machine `result` left — both shores start from it."""
    return vdi.run_primitive(UNDRAW, {"a2": save_block}, case.continued(result, refilled))


ROUND_TRIPS = {
    "low, both groups": ("low", 150, 90),
    "low, clipped left": ("low", 2, 90),
    "low, clipped right": ("low", 318, 90),
    "low, clipped top and left": ("low", 1, 2),
    "low, clipped bottom and right": ("low", 316, 198),
    "medium, both groups": ("medium", 400, 100),
    "medium, clipped right": ("medium", 638, 20),
    "high, both groups": ("high", 401, 300),
    "high, clipped left": ("high", 3, 300),
}


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_draw_then_undraw_puts_the_screen_back(name):
    resolution, x, y = ROUND_TRIPS[name]
    shape = mouse.RESOLUTIONS[resolution]
    fg, bg = ALL_REPLACE_OPS
    drawn = draw(x, y, draw_pokes(shape, fg=fg, bg=bg, hot_x=4, hot_y=6))
    restored = restore(drawn)
    screen = vdi.SCREEN
    before = vdi.make_image(draw_pokes(shape))
    assert bytes(restored.final[screen.base:screen.base + screen.bytes]) == \
        bytes(before[screen.base:screen.base + screen.bytes])
    assert not saved_status(restored) & VALID


def test_an_undraw_with_nothing_saved_only_clears_the_bit():
    """`bclr` WRITES the byte back whether the bit was set or not. Not poisoned: the attribution pass
    inverts that byte — setting the bit — and the run would then restore $fefe rows from $fefefefe."""
    pokes = merge_pokes(mouse.canvas_pokes(), mouse.save_block_pokes(fill=NOTHING_SAVED))
    result = vdi.run_primitive(UNDRAW, {"a2": mouse.SAVE_BLOCK_AT}, pokes, poison=False)
    assert saved_status(result) == NOTHING_SAVED


def save_block(length, address, status, area):
    """A save block by field: rows, the screen word, STAT, and the saved words."""
    return {mouse.SAVE_BLOCK_AT: vdi.pack_words(length) + address.to_bytes(4, "big") + bytes([status, 0])
            + bytes(area)}


AREA = bytes(range(0x100))                  # a ramp: every saved word its own


@pytest.mark.parametrize("planes", (0, 1, 2, 3, 4, 5, 8))
@pytest.mark.parametrize("long_rows", (False, True))
def test_each_plane_count_restores_in_its_own_layout(planes, long_rows):
    """Fewer than two planes (0 too), two, and "more" — FOUR: three planes or five are restored as if
    there were four. The area is a ramp so every word is its own."""
    status = VALID | (LONG_ROWS if long_rows else 0) | 0x40
    rows = 5
    pokes = merge_pokes(mouse.canvas_pokes(), vdi.linea_pokes(PLANES=planes),
                        save_block(rows, vdi.SCREEN.base + 160 * 20 + 16, status, AREA))
    vdi.run_primitive(UNDRAW, {"a2": mouse.SAVE_BLOCK_AT}, pokes)


@pytest.mark.parametrize("rows", (1, 16, 17))
def test_the_restore_runs_the_saved_length(rows):
    pokes = merge_pokes(mouse.canvas_pokes(), save_block(rows, vdi.SCREEN.base + 160 * 100 + 40, VALID, AREA))
    vdi.run_primitive(UNDRAW, {"a2": mouse.SAVE_BLOCK_AT}, pokes)


def test_the_restore_steps_by_width():
    pokes = merge_pokes(mouse.canvas_pokes(), vdi.linea_pokes(WIDTH=152),
                        save_block(9, vdi.SCREEN.base + 160 * 100 + 40, VALID | LONG_ROWS, AREA))
    vdi.run_primitive(UNDRAW, {"a2": mouse.SAVE_BLOCK_AT}, pokes)


def test_the_captured_machine_s_own_save_block_restores_the_arrow():
    """LINEA_SAVE_BLOCK as the boot left it: the arrow drawn at (159, 99) in low resolution."""
    assert vdi.linea(BASE_IMAGE, "SAVE_STAT") & VALID
    result = vdi.run_primitive(UNDRAW, {"a2": vdi.LINEA_SAVE_BLOCK}, {})
    assert not result.linea("SAVE_STAT") & VALID


# ---- through the Line-A exception -------------------------------------------------------------------------

def test_a00d_and_a00c_through_the_exception():
    fg, bg = ALL_REPLACE_OPS
    pokes = draw_pokes(fg=fg, bg=bg, hot_x=1, hot_y=1)
    registers = mouse.sprite_registers(77, 77)
    vdi.run_through_exception(DRAW, 0xD, registers, pokes)
    vdi.run_through_exception(UNDRAW, 0xC, {"a2": vdi.LINEA_SAVE_BLOCK}, {})


# ---- the rows Tier 3 prices -------------------------------------------------------------------------------
_FG, _BG = ALL_REPLACE_OPS
vdi.register("linea_draw_sprite, four planes, two groups", addrs.LINEA_ROM_DRAW_SPRITE,
             draw_pokes(fg=_FG, bg=_BG, hot_x=1, hot_y=1), regs=mouse.sprite_registers(101, 51))
vdi.register("linea_draw_sprite, four planes, clipped left", addrs.LINEA_ROM_DRAW_SPRITE,
             draw_pokes(fg=_FG, bg=_BG, hot_x=6, hot_y=1), regs=mouse.sprite_registers(2, 51))
vdi.register("linea_draw_sprite, one plane, by xor", addrs.LINEA_ROM_DRAW_SPRITE,
             draw_pokes(mouse.HIGH, fg=1, bg=1, planes=-1), regs=mouse.sprite_registers(300, 200))
vdi.register("linea_undraw_sprite, four planes, long rows", addrs.LINEA_ROM_UNDRAW_SPRITE,
             merge_pokes(mouse.canvas_pokes(), save_block(16, vdi.SCREEN.base + 160 * 50 + 48, VALID | LONG_ROWS, AREA)),
             regs={"a2": mouse.SAVE_BLOCK_AT})
vdi.register("linea_undraw_sprite, one plane", addrs.LINEA_ROM_UNDRAW_SPRITE,
             merge_pokes(mouse.canvas_pokes(mouse.HIGH), save_block(16, vdi.SCREEN.base + 80 * 50 + 8, VALID | LONG_ROWS,
                                                                    AREA)),
             regs={"a2": mouse.SAVE_BLOCK_AT})
vdi.register("linea_undraw_sprite, nothing saved", addrs.LINEA_ROM_UNDRAW_SPRITE, mouse.save_block_pokes(fill=NOTHING_SAVED),
             regs={"a2": mouse.SAVE_BLOCK_AT})
