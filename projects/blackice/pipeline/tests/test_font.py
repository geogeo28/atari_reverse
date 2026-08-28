"""Contract tests for the HUD bitmap font.

The 68000 side indexes font_bytes() by arithmetic alone (glyph N at N*8) and
shifts row bytes MSB-first, so the invariants that matter are the layout ones:
size, glyph count, slice identity, and bit order. A regression in any of them
corrupts every string the engine draws, with no runtime error to catch it.
"""

import numpy as np
import pytest

from stepix.sprite import TRANSPARENT_INDEX

from stepix.font import (
    DEFAULT_INK_INDEX,
    FONT_BYTES,
    FONT_BYTES_PER_GLYPH,
    FONT_CHAR_COUNT,
    FONT_CHAR_H,
    FONT_CHAR_W,
    FONT_FIRST_CHAR,
    GLYPH_ART,
    GLYPH_ART_H,
    GLYPH_ART_W,
    PLACEHOLDER_ART,
    font_bytes,
    font_sheet,
    glyph_rows,
    render_text,
)

FONT_LAST_CHAR = FONT_FIRST_CHAR + FONT_CHAR_COUNT - 1
ALL_CHARS = [chr(code) for code in range(FONT_FIRST_CHAR, FONT_LAST_CHAR + 1)]

MAX_ROW_BYTE = 255
DEFAULT_BG = 0
DEFAULT_SHEET_COLUMNS = 16

# 'I' is the cell-by-cell bit-order witness: a 3-pixel serif at rows 0 and 6 over
# a 1-pixel stem, all inside columns 1..3, so every bit position is pinned.
GLYPH_I_ROWS = [0x70, 0x20, 0x20, 0x20, 0x20, 0x20, 0x70, 0x00]


def test_cell_and_count_constants_are_coherent():
    assert FONT_CHAR_W == 8
    assert FONT_CHAR_H == 8
    assert FONT_BYTES_PER_GLYPH == FONT_CHAR_H
    assert FONT_CHAR_COUNT == 96
    assert FONT_FIRST_CHAR == 32
    assert FONT_LAST_CHAR == 127
    assert FONT_BYTES == FONT_CHAR_COUNT * FONT_BYTES_PER_GLYPH == 768


def test_drawable_area_is_strictly_smaller_than_the_cell():
    """Pins the guard itself: widening it to the full cell would erase the gap."""
    assert GLYPH_ART_W < FONT_CHAR_W
    assert GLYPH_ART_H < FONT_CHAR_H


@pytest.mark.parametrize("ch", sorted(GLYPH_ART))
def test_art_literals_fit_the_drawable_area(ch):
    art = GLYPH_ART[ch]
    assert len(art) <= GLYPH_ART_H, f"glyph {ch!r} has too many art lines"
    assert all(len(line) <= GLYPH_ART_W for line in art), f"glyph {ch!r} has an over-wide art line"


def test_font_bytes_has_exact_length():
    assert len(font_bytes()) == FONT_BYTES


def test_every_glyph_slice_matches_glyph_rows():
    blob = font_bytes()
    for index, ch in enumerate(ALL_CHARS):
        start = index * FONT_BYTES_PER_GLYPH
        assert list(blob[start : start + FONT_BYTES_PER_GLYPH]) == glyph_rows(ch), f"glyph {ch!r} at index {index}"


def test_glyph_i_matches_expected_row_bytes():
    """Pins bit 7 = leftmost: 'I' would still be symmetric if the bits reversed."""
    assert glyph_rows("I") == GLYPH_I_ROWS


def test_bit7_is_the_leftmost_pixel():
    """'L' row 0 lights only column 0, so exactly bit 7 must be set."""
    assert glyph_rows("L")[0] == 0x80


@pytest.mark.parametrize("ch", ALL_CHARS)
def test_every_char_in_range_returns_eight_row_bytes(ch):
    rows = glyph_rows(ch)
    assert len(rows) == FONT_BYTES_PER_GLYPH
    assert all(isinstance(row, int) for row in rows)
    assert all(0 <= row <= MAX_ROW_BYTE for row in rows)


@pytest.mark.parametrize("ch", ALL_CHARS)
def test_bottom_row_and_right_columns_stay_blank(ch):
    """The inter-character gap: without it, adjacent HUD glyphs touch."""
    rows = glyph_rows(ch)
    gap_columns_mask = 0b00000111
    assert rows[FONT_CHAR_H - 1] == 0, f"glyph {ch!r} has ink on its bottom gap row"
    assert all(row & gap_columns_mask == 0 for row in rows), f"glyph {ch!r} has ink in its right gap columns"


@pytest.mark.parametrize("lower", [chr(code) for code in range(ord("a"), ord("z") + 1)])
def test_lowercase_maps_to_uppercase(lower):
    assert glyph_rows(lower) == glyph_rows(lower.upper())


def test_unmapped_in_range_char_falls_back_to_placeholder():
    """DEL has no art; it must draw the hollow box, not raise or blank out."""
    placeholder_top_row = 0b11111000
    rows = glyph_rows(chr(FONT_LAST_CHAR))
    assert rows[0] == placeholder_top_row
    assert len(PLACEHOLDER_ART) == 7


@pytest.mark.parametrize("ch", [chr(FONT_FIRST_CHAR - 1), chr(FONT_LAST_CHAR + 1), "\n", "é", "€"])
def test_out_of_range_char_raises_value_error(ch):
    with pytest.raises(ValueError):
        glyph_rows(ch)


@pytest.mark.parametrize("bad", ["", "AB"])
def test_non_single_character_raises_value_error(bad):
    with pytest.raises(ValueError):
        glyph_rows(bad)


def test_render_text_shape_and_dtype():
    text = "AMMO:42%"
    image = render_text(text)
    assert image.shape == (FONT_CHAR_H, FONT_CHAR_W * len(text))
    assert image.dtype == np.uint8


def test_render_text_uses_only_fg_and_bg():
    fg, bg = 7, 3
    image = render_text("AMMO:42%", fg=fg, bg=bg)
    assert set(np.unique(image).tolist()) == {fg, bg}


def test_render_text_defaults_are_the_named_ink_on_bg0():
    image = render_text("A")
    assert set(np.unique(image).tolist()) == {DEFAULT_INK_INDEX, DEFAULT_BG}


def test_default_ink_is_not_the_transparency_key():
    """Text drawn in the key colour is punched back out by every sprite/HUD blit."""
    assert DEFAULT_INK_INDEX != TRANSPARENT_INDEX


def test_render_text_of_empty_string_is_zero_width():
    image = render_text("")
    assert image.shape == (FONT_CHAR_H, 0)


def test_render_text_matches_glyph_rows_bitwise():
    """Ties the rendered array back to the byte contract the engine consumes."""
    ch = "H"
    image = render_text(ch, fg=1, bg=0)
    for y, row in enumerate(glyph_rows(ch)):
        expected = [(row >> (FONT_CHAR_W - 1 - x)) & 1 for x in range(FONT_CHAR_W)]
        assert image[y].tolist() == expected


def test_font_sheet_default_shape():
    sheet = font_sheet()
    sheet_rows = FONT_CHAR_COUNT // DEFAULT_SHEET_COLUMNS
    assert sheet.shape == (sheet_rows * FONT_CHAR_H, DEFAULT_SHEET_COLUMNS * FONT_CHAR_W)
    assert sheet.dtype == np.uint8


@pytest.mark.parametrize("columns", [1, 7, 10, 16, 96, 100])
def test_font_sheet_shape_covers_all_glyphs(columns):
    sheet = font_sheet(columns=columns)
    expected_rows = -(-FONT_CHAR_COUNT // columns)
    assert sheet.shape == (expected_rows * FONT_CHAR_H, columns * FONT_CHAR_W)


def test_font_sheet_uses_only_fg_and_bg():
    fg, bg = 9, 2
    assert set(np.unique(font_sheet(fg=fg, bg=bg)).tolist()) == {fg, bg}


def test_font_sheet_first_cell_is_the_first_glyph():
    sheet = font_sheet(fg=1, bg=0)
    first_cell = sheet[:FONT_CHAR_H, :FONT_CHAR_W]
    assert first_cell.sum() == 0  # glyph 0 is space

