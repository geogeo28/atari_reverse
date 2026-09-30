"""The BIOS console's ONE bus policy: every screen write wraps on the 24-bit bus before it is bounded.

The console forms each screen address as the ROM does — a plain 32-bit sum off `_v_bas_ad` — and the 68000
drives 24 bits of it. A cursor row of $ffff (vs_curaddress of 0, or `ESC Y` with a row byte below the bias,
which the N-flag clamp passes) is $ffff text rows down: past 16 MB, and ONE TEXT ROW ABOVE THE SCREEN once the
bus drops the top byte. All three of the console's screen writers reach it — the cursor inversion, the glyph
and the rectangle clear — so each is driven here, in a real sequence (a cursor placed, a character, then an
erase to the end of the line, each run starting from the one before it ended in: `case.continued`), through
both doors: `Bconout(CON:)` and the VDI escape's v_curtext / v_eeol.

The one address the bus does NOT bring back is a COLUMN of $ffff, which lies past the 1 MB machine even
wrapped; that refusal stays pinned where it is (`test_vdi_escape.py`, `include/bios/vt52.h`).
"""
import pytest

from harness import BASE_IMAGE, addrs
from recreate_kit import os_map

import case
import test_bios_vt52 as vt52_cases
import vdi_escape as escape
import vt52

WRAPPING_ROW = 0xFFFF                   # $ffff text rows down: one row above the screen, on the bus
COLUMN = 8                              # an even column, so the next glyph is the same group's odd half
A_CHARACTER = vt52_cases.A_CHARACTER
ESCAPE_K = ord("K")
ROW_BELOW_THE_BIAS = addrs.CON_ESCAPE_BIAS - 1


def on_the_bus(column, row):
    """A cell's bytes as the 68000 drives them: the ROM's sum, top byte dropped."""
    return [at & os_map.OS_BUS_ADDR_MASK for at in vt52.cell_bytes(column, row)]


def test_the_wrapping_row_is_the_text_row_just_above_the_screen():
    """The premise every case below stands on, in the captured geometry."""
    first = on_the_bus(0, WRAPPING_ROW)[0]
    assert first == vt52.SCREEN + vt52.CURSOR_OFFSET - vt52.ROW_BYTES


def assert_drawn_above_the_screen(final, column):
    """The glyph's cell, wrapped, holds what the oracle wrote there and lies before the screen."""
    cell = on_the_bus(column, WRAPPING_ROW)
    assert all(at < vt52.SCREEN for at in cell)
    assert any(final[at] != BASE_IMAGE[at] for at in cell), "no glyph byte landed on the wrapped cell"


def assert_line_tail_cleared(final, from_column, cursor_drawn):
    """ESC K's rectangle, wrapped: every cell from the cursor's to the last is the background (0) — and the
    cursor's own inverted over it again when the unlock that ends the erase redraws it."""
    cursor_cell = 0xFF if cursor_drawn else 0
    for column in range(from_column, vt52.MAX_COLUMN + 1):
        expected = cursor_cell if column == from_column else 0
        assert all(final[at] == expected for at in on_the_bus(column, WRAPPING_ROW)), f"column {column}"


# ---- Bconout(CON:) ---------------------------------------------------------------------------------------------

def bconout(character, pokes):
    """One character to the console over `pokes`, as a `Result` the next character continues from."""
    return case.Result(vt52_cases.console(character, pokes), pokes)


@pytest.mark.parametrize("cursor_depth", (0, 1))
def test_bconout_draws_a_glyph_on_a_wrapping_row_and_erases_the_line_after_it(cursor_depth):
    """A glyph on row $ffff, then ESC K from the cell the cursor stepped to: both writes land one text row above
    the screen, where the original's own do."""
    glyph = bconout(A_CHARACTER, vt52.staged(COLUMN, WRAPPING_ROW, cursor_depth=cursor_depth))
    assert_drawn_above_the_screen(glyph.final, COLUMN)
    escaped = bconout(addrs.CON_ESC, case.continued(glyph))
    erased = bconout(ESCAPE_K, case.continued(escaped))
    assert_line_tail_cleared(erased.final, COLUMN + 1, cursor_depth == 0)


def test_bconout_raw_draws_a_glyph_on_a_wrapping_row():
    """...and the RAW console, the same glyph writer with no state machine in front of it."""
    pokes = vt52.staged(COLUMN, WRAPPING_ROW)
    assert_drawn_above_the_screen(case.Result(vt52_cases.raw(A_CHARACTER, pokes), pokes).final, COLUMN)


# ---- the VDI escape: vs_curaddress, v_curtext, v_eeol --------------------------------------------------------

@pytest.mark.parametrize("cursor_depth", (0, 2))
def test_vs_curaddress_0_then_v_curtext_then_v_eeol_write_where_the_bus_wraps(cursor_depth):
    """vs_curaddress's row of 0 is n = $ffff; a character through v_curtext, then v_eeol from the next cell."""
    placed = escape.run_console(escape.call("VS_CURADDRESS", (0, COLUMN + 1),
                                            escape.console(3, 3, cursor_depth=cursor_depth)))
    drawn = escape.run_console(escape.call("V_CURTEXT", (A_CHARACTER,), case.continued(placed)))
    assert_drawn_above_the_screen(drawn.final, COLUMN)
    erased = escape.run_console(escape.call("V_EEOL", onto=case.continued(drawn)))
    assert_line_tail_cleared(erased.final, COLUMN + 1, cursor_depth == 0)


def test_v_curtext_s_esc_y_below_the_bias_then_a_glyph_and_esc_k():
    """...and the same three through the console's own state machine, in one v_curtext."""
    words = (addrs.CON_ESC, ord("Y"), ROW_BELOW_THE_BIAS, addrs.CON_ESCAPE_BIAS + COLUMN, A_CHARACTER,
             addrs.CON_ESC, ESCAPE_K)
    result = escape.run_console(escape.call("V_CURTEXT", words, escape.console(3, 3)))
    assert_drawn_above_the_screen(result.final, COLUMN)
    assert_line_tail_cleared(result.final, COLUMN + 1, cursor_drawn=True)
