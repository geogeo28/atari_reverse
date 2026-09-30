"""The VDI's ESCAPE, opcode 5 @ $fc427a — its dispatch, its answers, and the console arms (`src/vdi/escape.c`).

Every arm number the ROM can be handed is driven: the twenty table arms, the two it tests for past the table,
and the numbers that fall through its two compares — 0 (the table's own `rts`), 20 and 21 just past it, 100
and 103 either side of the two extras, and the ones an UNSIGNED `cmp.w #19 / bhi` sends past the table rather
than into it (negative words, $8000). The arms that are the BIOS console's own escape bodies are driven at
every edge the body tests; the console's text arm through control codes, an escape it leaves half-read, a wrap
and a scroll; the two graphic-cursor arms into the mouse's hide count; v_hardcopy into a staged dump routine.
`vdi_escape.py`'s header says how the console and the dump are staged, and why the console arms do not poison.

THE THREE ARMS PAST THE CONSOLE — v_offset, v_fontinit and the answering inquiries — are held to ROM data
where it exists: v_fontinit is handed the ROM's own three system fonts, and the geometry it derives is asserted
against the fonts' headers as well as against the original.
"""
import signal
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu
from recreate_kit import os_map

import case
import isr
import staging
import vdi
import vdi_escape as escape
import vdi_helpers
import vdi_mouse
import vdi_raster
import vt52
from case import merge_pokes
from opcodes import CMP_W_IMMEDIATE_D0, RTS_WORD

ARMS = escape.ARMS
CONSOLE_ARMS = tuple(escape.CONSOLE_LETTERS)
LAST_COLUMN, LAST_ROW = vt52.MAX_COLUMN, vt52.MAX_ROW
MIDDLE = (7, 5)                                     # a cell no edge test touches
FONTS = {"6x6": vdi.FONT_ROM_6X6, "8x8": vdi.FONT_ROM_8X8, "8x16": vdi.FONT_ROM_8X16}


def written_outside_the_stack(result):
    """The addresses the ORACLE stored to, less its own stack band (the frames every run leaves)."""
    stack = range(emu.STACK_GUARD_LO, emu.STACK_BAND_HI)
    return {at for at in result.info["writes"] if at not in stack}


def cursor(result):
    """(column, row) as the run left them."""
    return result.word(addrs.CON_CURSOR_COLUMN), result.word(addrs.CON_CURSOR_ROW)


# ---- the dispatch -------------------------------------------------------------------------------------------

def test_every_table_arm_is_named_and_every_console_arm_is_the_console_s_own_body():
    """The escape's table is WORD offsets from itself (`VDI_ESCAPE_TABLE`); ESC's two are the same shape. An arm
    `escape.c` enters by letter must be the very address ESC reaches with that letter."""
    def entry(table, index):
        return table + vdi.signed_word(vdi.rom_word(table + index * vdi.WORD_BYTES))

    assert sorted(value for value in ARMS.values() if value <= vdi.VDI_ESCAPE_LAST) == \
        list(range(vdi.VDI_ESCAPE_LAST + 1))
    for arm, letter in escape.CONSOLE_LETTERS.items():
        if letter.isupper():
            body = entry(addrs.CON_ESCAPE_UPPER_TABLE, ord(letter) - addrs.CON_ESCAPE_UPPER_FIRST)
        else:
            body = entry(addrs.CON_ESCAPE_LOWER_TABLE, ord(letter) - addrs.CON_ESCAPE_LOWER_FIRST)
        assert entry(vdi.VDI_ESCAPE_TABLE, ARMS[arm]) == body, arm


def test_every_arm_has_its_own_number_and_those_past_the_table_are_the_rom_s_compares():
    """The header's rule — every `VDI_ESCAPE_<X>` is an arm but the `ANSWER_` ones — held to the ROM: no two arms
    share a number, and the ones past the table are the immediates of the `cmp.w #n,d0`s between the table's end
    and the dispatch's closing `rts`, read out of the ROM."""
    assert len(set(ARMS.values())) == len(ARMS)
    at, compared = vdi.VDI_ESCAPE_TABLE + (vdi.VDI_ESCAPE_LAST + 1) * vdi.WORD_BYTES, set()
    while vdi.rom_word(at) != RTS_WORD:
        if vdi.rom_word(at) == CMP_W_IMMEDIATE_D0:
            compared.add(vdi.rom_word(at + vdi.WORD_BYTES))
        at += vdi.WORD_BYTES
    assert {value for value in ARMS.values() if value > vdi.VDI_ESCAPE_LAST} == compared


# 0 is the table's own `rts`; every other number here falls past both compares. $8000 and $ffff are NEGATIVE
# words, which the unsigned `bhi` sends past the table — a signed compare would index below it — and the last
# three have an arm's number in their LOW byte, which a byte compare would take.
NOTHING = (0, 20, 21, 100, 103, 0x7F, 0x80, 0x7FFF, 0x8000, 0xFFFF, 0xFF65, 0x0101, 0x0165, 0x0166)


@pytest.mark.parametrize("subfunction", NOTHING)
def test_an_arm_that_does_nothing_writes_nothing(subfunction):
    result = escape.run(escape.call(subfunction, onto=escape.console(*MIDDLE)))
    assert not written_outside_the_stack(result)


# ---- the three that answer ------------------------------------------------------------------------------------

def test_vq_chcells_answers_the_rows_then_the_columns():
    result = escape.run(escape.call("VQ_CHCELLS"))
    assert result.intout(2) == [LAST_ROW + 1, LAST_COLUMN + 1]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == escape.CELLS_WORDS


def test_vq_chcells_stores_the_count_first_then_the_columns_then_the_rows():
    """intout over contrl[4]: the count is overwritten by intout[0], and intout[1] lands on contrl[5]."""
    result = escape.run(vdi.intout_over(escape.call("VQ_CHCELLS")))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == LAST_ROW + 1
    assert result.contrl(vdi.CONTRL_SUBFUNCTION) == LAST_COLUMN + 1


def test_vq_chcells_reads_the_rows_after_storing_the_columns():
    """intout laid over the console's own two geometry words (columns, then rows): the columns' answer lands
    on the ROW word before the rows are read, so what is answered for them is that answer plus one."""
    result = escape.run(vdi.intout_over(escape.call("VQ_CHCELLS"), addrs.CON_MAX_COLUMN))
    assert result.word(addrs.CON_MAX_ROW) == LAST_COLUMN + 1
    assert result.word(addrs.CON_MAX_COLUMN) == LAST_COLUMN + 2


@pytest.mark.parametrize("column,row", ((0, 0), MIDDLE, (LAST_COLUMN, LAST_ROW)))
def test_vq_curaddress_answers_1_based(column, row):
    result = escape.run(escape.call("VQ_CURADDRESS", onto=vt52.at(column, row)))
    assert result.intout(2) == [row + 1, column + 1]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == escape.CELLS_WORDS


def test_vq_curaddress_stores_the_count_then_the_row_then_the_column():
    result = escape.run(vdi.intout_over(escape.call("VQ_CURADDRESS", onto=vt52.at(*MIDDLE))))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == MIDDLE[1] + 1
    assert result.contrl(vdi.CONTRL_SUBFUNCTION) == MIDDLE[0] + 1


@pytest.mark.parametrize("overlap", (False, True))
def test_vq_tabstatus_answers_one(overlap):
    pokes = escape.call("VQ_TABSTATUS")
    result = escape.run(vdi.intout_over(pokes) if overlap else pokes)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == escape.TABLET_WORDS
    if not overlap:
        assert result.intout(1) == [escape.TABLET]


# ---- the console's own escape bodies ----------------------------------------------------------------------------
# (arm, column, row, where the cursor ends): each body at the edge it stops at and inside it.
MOVES = (
    ("V_CURUP", *MIDDLE, (MIDDLE[0], MIDDLE[1] - 1)),
    ("V_CURUP", MIDDLE[0], 0, (MIDDLE[0], 0)),
    ("V_CURDOWN", *MIDDLE, (MIDDLE[0], MIDDLE[1] + 1)),
    ("V_CURDOWN", MIDDLE[0], LAST_ROW, (MIDDLE[0], LAST_ROW)),
    ("V_CURRIGHT", *MIDDLE, (MIDDLE[0] + 1, MIDDLE[1])),
    ("V_CURRIGHT", LAST_COLUMN, MIDDLE[1], (LAST_COLUMN, MIDDLE[1])),
    ("V_CURLEFT", *MIDDLE, (MIDDLE[0] - 1, MIDDLE[1])),
    ("V_CURLEFT", 0, MIDDLE[1], (0, MIDDLE[1])),
    ("V_CURLEFT", 1, LAST_ROW, (0, LAST_ROW)),          # onto the first cell of a 16-pixel group
    ("V_CURHOME", *MIDDLE, (0, 0)),
    ("V_CURHOME", 0, 0, (0, 0)),
)


@pytest.mark.parametrize("depth", (0, 2))
@pytest.mark.parametrize("arm,column,row,ends", MOVES)
def test_a_cursor_move_stops_at_the_edge(arm, column, row, ends, depth):
    """At depth 0 the cursor is on screen and a move inverts it off one cell and onto the next; at the captured
    desktop's depth 2 nothing is drawn and only the three fields move."""
    result = escape.run_console(escape.call(arm, onto=escape.console(column, row, cursor_depth=depth)))
    assert cursor(result) == ends
    assert result.word(addrs.CON_CURSOR_DISABLE) == depth


# (arm, column, row): each erase from the middle, from the last cell of a row, and from the last row.
ERASES = (("V_EEOL", *MIDDLE), ("V_EEOL", LAST_COLUMN, MIDDLE[1]), ("V_EEOL", 0, LAST_ROW),
          ("V_EEOS", *MIDDLE), ("V_EEOS", LAST_COLUMN, LAST_ROW), ("V_EEOS", 0, 0))


@pytest.mark.parametrize("depth", (0, 2))
@pytest.mark.parametrize("arm,column,row", ERASES)
def test_an_erase_clears_from_the_cursor_and_leaves_it_there(arm, column, row, depth):
    result = escape.run_console(escape.call(arm, onto=escape.console(column, row, cursor_depth=depth)))
    assert cursor(result) == (column, row)
    last_line = vt52.cell_address(LAST_COLUMN, row) + (vt52.CELL_HEIGHT - 1) * vt52.LINE_BYTES
    assert result.after(last_line, vt52.GROUP_BYTES) != bytes(escape.SCREEN[vdi.SCREEN.base][
        last_line - vdi.SCREEN.base:last_line - vdi.SCREEN.base + vt52.GROUP_BYTES])


@pytest.mark.parametrize("arm,flag_set", (("V_RVON", True), ("V_RVOFF", False)))
@pytest.mark.parametrize("before", (0, vt52.REVERSE))
def test_reverse_video_is_the_flag_alone(arm, flag_set, before):
    result = escape.run_console(escape.call(arm, onto=escape.console(*MIDDLE, extra_flags=before)))
    assert bool(result.after(addrs.CON_STATE_FLAGS, 1)[0] & vt52.REVERSE) == flag_set
    assert written_outside_the_stack(result) <= {addrs.CON_STATE_FLAGS}


# ---- entering and leaving alpha mode --------------------------------------------------------------------------

@pytest.mark.parametrize("arm", ("V_EXIT_CUR", "V_ENTER_CUR"))
@pytest.mark.parametrize("depth", (0, 1, 2))
@pytest.mark.parametrize("at", ((0, 0), MIDDLE, (LAST_COLUMN, LAST_ROW)))
def test_alpha_mode_clears_the_screen_and_homes_the_cursor(arm, depth, at):
    """v_exit_cur locks the cursor one level deeper FIRST, so the screen is cleared with it off and it stays
    off; v_enter_cur clears and then forces it on whatever the depth — 0 afterwards either way it came in."""
    result = escape.run_console(escape.call(arm, onto=escape.console(*at, cursor_depth=depth)))
    assert cursor(result) == (0, 0)
    assert result.word(addrs.CON_CURSOR_DISABLE) == (depth + 1 if arm == "V_EXIT_CUR" else 0)


def test_v_exit_cur_takes_the_lock_before_the_cursor_moves():
    """Locked FIRST, the home and the clear run with the cursor off and never redraw it — so the blink timer,
    which only a redraw reloads, is left as it was. Taken after, the home would redraw it and reload the timer
    before the lock took it off again."""
    stale_timer = BASE_IMAGE[addrs.CON_BLINK_RATE] + 1
    staged = merge_pokes(escape.console(*MIDDLE, cursor_depth=0), {addrs.CON_BLINK_TIMER: bytes([stale_timer])})
    result = escape.run_console(escape.call("V_EXIT_CUR", onto=staged))
    assert result.after(addrs.CON_BLINK_TIMER, 1)[0] == stale_timer


@pytest.mark.parametrize("rate", (1, 20))
def test_v_enter_cur_with_a_blink_rate_in_the_spare_byte(rate):
    """`Cursconf(6)`'s byte: nonzero, the unlock reloads the blink timer from it and draws NOTHING."""
    staged = merge_pokes(escape.console(*MIDDLE, cursor_depth=1), {addrs.CON_STATE_SPARE: bytes([rate])})
    result = escape.run_console(escape.call("V_ENTER_CUR", onto=staged))
    assert result.after(addrs.CON_BLINK_TIMER, 1)[0] == rate


# ---- vs_curaddress ----------------------------------------------------------------------------------------------
# The intin value whose `n = value - 1` is the LAST that `max - n` leaves negative as a word ($8000): one more
# wraps the difference to $7fff, which passes the clamp.
UNCLAMPED_ROW = LAST_ROW + 0x8001
UNCLAMPED_COLUMN = LAST_COLUMN + 0x8001


@pytest.mark.parametrize("row,column,ends", (
    (1, 1, (0, 0)),
    (MIDDLE[1] + 1, MIDDLE[0] + 1, MIDDLE),
    (LAST_ROW + 1, LAST_COLUMN + 1, (LAST_COLUMN, LAST_ROW)),
    (LAST_ROW + 2, LAST_COLUMN + 2, (LAST_COLUMN, LAST_ROW)),       # one past: clamped
    (0x7FFF, 0x7FFF, (LAST_COLUMN, LAST_ROW)),
    (UNCLAMPED_ROW, UNCLAMPED_COLUMN, (LAST_COLUMN, LAST_ROW)),     # ...the first n whose `max - n` is negative
))
@pytest.mark.parametrize("depth", (0, 2))
def test_vs_curaddress_places_the_cursor_1_based_and_clamped(row, column, ends, depth):
    result = escape.run_console(escape.call("VS_CURADDRESS", (row, column), escape.console(*MIDDLE, cursor_depth=depth)))
    assert cursor(result) == ends


@pytest.mark.parametrize("row,column", ((0, 0), (0, MIDDLE[0] + 1), (MIDDLE[1] + 1, 0),
                                        (UNCLAMPED_ROW + 1, UNCLAMPED_COLUMN + 1)))
def test_vs_curaddress_of_0_is_minus_1_and_not_clamped(row, column):
    """`subq.w #1` unchecked, and the clamp is the N flag of `max - n`: $ffff passes it, and so does every n
    down to `max + $8001`, so the cell address lands far outside the screen. At the desktop's depth nothing is
    drawn there, and the fields are stored as the original stores them."""
    result = escape.run_console(escape.call("VS_CURADDRESS", (row, column), escape.console(*MIDDLE, cursor_depth=2)))
    assert cursor(result) == ((column - 1) & 0xFFFF, (row - 1) & 0xFFFF)


def staged_byte(at):
    """The byte `escape.console` stages at `at`: the canvas on the screen, the snapshot's RAM elsewhere."""
    canvas = escape.SCREEN[vdi.SCREEN.base]
    offset = at - vdi.SCREEN.base
    return canvas[offset] if 0 <= offset < len(canvas) else BASE_IMAGE[at]


# A row whose cell address the 24-bit bus WRAPS back into the machine: 0 is n = $ffff, $ffff text rows down, which
# wraps to the row just before the screen; $ccce is n = $cccd, whose rows' bytes wrap to one row and a bit INTO it.
WRAPPING_ROWS = (0, 0xCCCE)


@pytest.mark.parametrize("row", WRAPPING_ROWS)
@pytest.mark.parametrize("column", (1, MIDDLE[0] + 1))
def test_vs_curaddress_of_a_row_past_the_bus_draws_where_the_bus_wraps(row, column):
    """...and at depth 0 the original draws the cursor at that address — a plain 32-bit sum the 68000's 24
    address bits wrap back into RAM (`console_screen_byte`), stored in the cursor's address unwrapped."""
    result = escape.run_console(escape.call("VS_CURADDRESS", (row, column), escape.console(*MIDDLE, cursor_depth=0)))
    placed = ((column - 1) & 0xFFFF, (row - 1) & 0xFFFF)
    assert cursor(result) == placed
    assert result.long(addrs.CON_CURSOR_ADDRESS) == vt52.cell_address(*placed) & 0xFFFFFFFF
    for at in (at & os_map.OS_BUS_ADDR_MASK for at in vt52.cell_bytes(*placed)):
        assert result.after(at, 1)[0] == staged_byte(at) ^ 0xFF, f"${at:x} is not inverted"


def test_vs_curaddress_of_column_0_with_the_cursor_on_is_refused_by_the_host():
    """A COLUMN of 0 is $ffff columns across, which even wrapped on the bus lies past the 1 MB machine: the
    original inverts a cell no RAM answers, where its writes go nowhere, and the host's bound on a console
    screen write (`console_screen_byte`) stops instead. Unpinned by a differential, for that reason alone."""
    pokes = escape.call("VS_CURADDRESS", (0, 0), escape.console(*MIDDLE, cursor_depth=0))
    returncode, stderr, _ = vdi_helpers.refusal_over("vdi_escape", pokes, read_back=False)
    assert returncode == -signal.SIGABRT and "ST_RAM_BYTES" in stderr, (returncode, stderr)


# ---- v_curtext --------------------------------------------------------------------------------------------------

def text(string):
    return tuple(ord(character) for character in string)


ESC, CR, LF, BS, TAB, BEL = addrs.CON_ESC, addrs.CON_CR, addrs.CON_LF, addrs.CON_BS, addrs.CON_TAB, addrs.CON_BEL


@pytest.mark.parametrize("label,words,at,flags,ends", (
    ("none", (), MIDDLE, 0, MIDDLE),
    ("a word", text("GEM"), MIDDLE, 0, (MIDDLE[0] + 3, MIDDLE[1])),
    ("high bytes dropped", (0x0141, 0xFF42, 0x8043), MIDDLE, 0, (MIDDLE[0] + 3, MIDDLE[1])),
    ("controls", (*text("ab"), BS, TAB, CR, LF, *text("c")), MIDDLE, 0, (1, MIDDLE[1] + 1)),
    ("the last column, no wrap", text("xyz"), (LAST_COLUMN - 1, 3), 0, (LAST_COLUMN, 3)),
    ("the last column, wrapping", text("xyz"), (LAST_COLUMN - 1, 3), vt52.WRAP, (1, 4)),
    ("a line feed at the bottom", (*text("end"), CR, LF), (0, LAST_ROW), 0, (0, LAST_ROW)),
    ("wrapping at the bottom", text("wrap"), (LAST_COLUMN - 1, LAST_ROW), vt52.WRAP, (2, LAST_ROW)),
    ("an ESC Y inside", (ESC, ord("Y"), 0x20 + 2, 0x20 + 9, *text("at")), MIDDLE, 0, (11, 2)),
    ("an ESC K and an ESC j", (ESC, ord("K"), *text("s"), ESC, ord("j")), MIDDLE, 0, (MIDDLE[0] + 1, MIDDLE[1])),
    ("the bell", (BEL, *text("!")), MIDDLE, 0, (MIDDLE[0] + 1, MIDDLE[1])),
))
@pytest.mark.parametrize("depth", (0, 2))
def test_v_curtext_is_bconout_con_word_by_word(label, words, at, flags, ends, depth):
    result = escape.run_console(escape.call("V_CURTEXT", words, escape.console(*at, cursor_depth=depth,
                                                                              extra_flags=flags)))
    assert cursor(result) == ends, label
    assert result.long(addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL


ROW_BELOW_THE_BIAS = addrs.CON_ESCAPE_BIAS - 1          # ESC Y's row byte for row $ffff


def test_v_curtext_s_esc_y_with_a_row_byte_below_the_bias_wraps_on_the_bus():
    """ESC Y's row byte $1f is row $ffff — the same wrap as vs_curaddress of 0, reached through the console's own
    state machine with the cursor drawn."""
    column = 8
    result = escape.run_console(escape.call("V_CURTEXT", (ESC, ord("Y"), ROW_BELOW_THE_BIAS, addrs.CON_ESCAPE_BIAS + column),
                                            escape.console(*MIDDLE, cursor_depth=0)))
    assert cursor(result) == (column, 0xFFFF)


def test_v_curtext_leaves_an_escape_half_read_for_the_next_call():
    """The console's state is RAM, so an ESC Y cut after its row finishes on the next v_curtext — a real
    sequence of two calls, the second starting from the first's end state."""
    first = escape.run_console(escape.call("V_CURTEXT", (ESC, ord("Y"), 0x20 + 4), escape.console(*MIDDLE)))
    assert first.long(addrs.CON_STATE_VECTOR) == addrs.CON_STATE_AWAIT_Y_COLUMN
    second = escape.run_console(escape.call("V_CURTEXT", (0x20 + 12, *text("x")), case.continued(first)))
    assert cursor(second) == (13, 4)


def test_v_curtext_reads_each_word_after_the_glyph_before_it_is_drawn():
    """intin ON THE SCREEN, at the cell the first glyph is drawn to: the second word is the first glyph's own
    plane-1 byte pair, so a core that read the text ahead of drawing it sends the canvas instead."""
    column, row = MIDDLE[0] - 1, MIDDLE[1]                  # an EVEN cell: a word read there is aligned
    pokes = escape.call("V_CURTEXT", (0,) * 3, escape.console(column, row))
    result = escape.run_console(merge_pokes(pokes, vdi.linea_pokes(INTIN=vt52.cell_address(column, row))))
    assert cursor(result)[1] == row


def test_a_state_vector_no_escape_installs_is_refused_by_the_host():
    """$4a8 is RAM a program may point anywhere; the original jumps there, the host names it and stops
    (`src/bios/vt52.c`) — the same refusal `Bconout(CON:)` makes."""
    pokes = escape.call("V_CURTEXT", text("x"), merge_pokes(escape.console(*MIDDLE), vt52.state(escape.DUMP_STUB)))
    returncode, stderr, _ = vdi_helpers.refusal_over("vdi_escape", pokes, read_back=False)
    assert returncode == -signal.SIGABRT and "state vector" in stderr, (returncode, stderr)


# A count of $8000 is UNSIGNED to the `dbf`: 32,768 words, here the free RAM's zeros — NULs, which the console
# ignores — ending on one character in a band of this battery's own. A signed loop would send none.
LONG_TEXT_WORDS = 0x8000
LONG_TEXT_BAND_AT = 0xF7F00         # the top page of the free TPA's zeros, just under the screen
LONG_TEXT_BAND_BYTES = 0x10
LONG_TEXT_END = staging.HIGH_BANDS.claim(LONG_TEXT_BAND_AT, LONG_TEXT_BAND_BYTES,
                                         "test_vdi_escape.py: the last word of a $8000-word text")
LONG_TEXT_AT = LONG_TEXT_END - (LONG_TEXT_WORDS - 1) * vdi.WORD_BYTES
LONG_TEXT_INSNS = 2_000_000          # ~14 instructions a NUL on the original


def test_v_curtext_s_count_is_unsigned():
    assert all(byte == 0 for byte in BASE_IMAGE[LONG_TEXT_AT:LONG_TEXT_END])
    pokes = merge_pokes(escape.call("V_CURTEXT", (), escape.console(*MIDDLE)),
                        vdi.linea_pokes(INTIN=LONG_TEXT_AT), {LONG_TEXT_END: vdi.pack_words(ord("x"))},
                        {vdi.CONTRL_AT + vdi.CONTRL_N_INTIN: vdi.pack_words(LONG_TEXT_WORDS)})
    result = escape.run_console(pokes, max_insns=LONG_TEXT_INSNS)
    assert cursor(result) == (MIDDLE[0] + 1, MIDDLE[1])


def test_v_curtext_reads_its_count_from_contrl_3_not_from_intin():
    """A count shorter than the words staged: only that many are sent."""
    pokes = escape.call("V_CURTEXT", text("four"), escape.console(*MIDDLE))
    pokes = merge_pokes(pokes, {vdi.CONTRL_AT + vdi.CONTRL_N_INTIN: vdi.pack_words(2)})
    result = escape.run_console(pokes)
    assert cursor(result) == (MIDDLE[0] + 2, MIDDLE[1])


# ---- the graphic cursor ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("depth", (0, 1, 3))
@pytest.mark.parametrize("staged_word", (0, 1))
def test_v_dspcur_clears_intin_0_and_forces_the_arrow_on(depth, staged_word):
    pokes = escape.call("V_DSPCUR", (staged_word,),
                        merge_pokes(vdi.linea_pokes(M_HID_CT=depth, GCURX=40, GCURY=30), vdi_raster.CANVAS))
    result = escape.run(pokes)
    assert result.word(vdi.INTIN_AT) == 0
    assert result.linea("M_HID_CT") == 0


@pytest.mark.parametrize("depth", (0, 1))
def test_v_rmcur_is_v_hide_c(depth):
    result = escape.run(escape.call("V_RMCUR", onto=vdi.linea_pokes(M_HID_CT=depth)))
    assert result.linea("M_HID_CT") == depth + 1


# ---- v_hardcopy -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("dumpflg", (0, 1, 0xFFFF))
def test_v_hardcopy_is_xbios_scrdmp(dumpflg):
    """Through the ROM's own `trap #14` on the oracle: the routine `scr_dump` names is called ONCE — not the
    decoy beside it — finding `_dumpflg` as the caller left it, which Scrdmp sets to -1 only AFTER the call."""
    result = escape.run_hardcopy(escape.hardcopy_pokes(dumpflg))
    assert case.written(result.info, escape.DUMP_REPORT, isr.FLAG_REPORT_BYTES) == dumpflg << 8 | 1
    assert not isr.marked(result.info, escape.DECOY_MARK)
    assert [call[0] for call in isr.CALLS] == [escape.DUMP_STUB]
    assert case.written(result.info, addrs.SYSVAR_DUMPFLG, 2) == 0xFFFF


def test_scrdmp_is_the_xbios_table_s_entry_its_number_names():
    """`XBIOS_SCRDMP` / `XBIOS_SCRDMP_FN`, read out of the ROM's XBIOS table: the routine v_hardcopy's trap reaches."""
    count = vdi.rom_word(addrs.XBIOS_FUNCTION_TABLE)
    entry = addrs.XBIOS_FUNCTION_TABLE + addrs.TRAP_TABLE_COUNT_BYTES + addrs.XBIOS_SCRDMP_FN * addrs.TRAP_TABLE_ENTRY_BYTES
    assert addrs.XBIOS_SCRDMP_FN < count
    assert case.long_in(BASE_IMAGE, entry) == addrs.XBIOS_SCRDMP


# ---- v_offset ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lines", (0, 8, 199, 0x8000, 0xFFFF))
@pytest.mark.parametrize("depth", (0, 2))
def test_v_offset_is_lines_times_the_line_pitch_and_moves_no_cursor(lines, depth):
    """`mulu.w`, the product's low word; under the cursor's lock, which inverts it off and back on at the SAME
    cell — the address is not recomputed until the cursor is next placed."""
    staged = escape.console(*MIDDLE, cursor_depth=depth)
    result = escape.run_console(escape.call("V_OFFSET", (lines,), staged))
    assert result.word(addrs.CON_CURSOR_OFFSET) == (lines * vt52.LINE_BYTES) & 0xFFFF
    assert result.long(addrs.CON_CURSOR_ADDRESS) == vt52.cell_address(*MIDDLE)


def test_v_offset_reads_intin_under_the_lock():
    """intin laid over the lock's own depth word: the word read is the depth AFTER the lock took its level."""
    result = escape.run_console(merge_pokes(escape.call("V_OFFSET", (), escape.console(*MIDDLE, cursor_depth=2)),
                                            vdi.linea_pokes(INTIN=addrs.CON_CURSOR_DISABLE)))
    assert result.word(addrs.CON_CURSOR_OFFSET) == 3 * vt52.LINE_BYTES


def test_v_offset_reaches_the_screen_at_the_next_placement():
    first = escape.run_console(escape.call("V_OFFSET", (vt52.CELL_HEIGHT,), escape.console(*MIDDLE)))
    second = escape.run_console(escape.call("VS_CURADDRESS", (1, 1), case.continued(first)))
    assert second.long(addrs.CON_CURSOR_ADDRESS) == vt52.SCREEN + vt52.ROW_BYTES


# ---- v_fontinit ----------------------------------------------------------------------------------------------

def fontinit(font, onto=None):
    return escape.call("V_FONTINIT", ((font >> 16) & 0xFFFF, font & 0xFFFF), onto)


@pytest.mark.parametrize("name", FONTS)
def test_v_fontinit_takes_the_geometry_from_the_header(name):
    font = FONTS[name]
    header = lambda field: vdi.rom_word(font + vdi.field("FONT", field).at)   # noqa: E731
    height, width = header("FORM_HEIGHT"), header("MAX_CELL_WIDTH")
    result = escape.run_console(fontinit(font))
    assert result.word(addrs.CON_CELL_HEIGHT) == height
    assert result.word(addrs.CON_ROW_BYTES) == vt52.LINE_BYTES * height
    assert result.word(addrs.CON_MAX_ROW) == vdi.SCREEN.height // height - 1
    assert result.word(addrs.CON_MAX_COLUMN) == vdi.SCREEN.width // width - 1
    assert result.long(addrs.CON_FONT_FORM) == case.long_in(BASE_IMAGE, font + vdi.field("FONT", "DAT_TABLE").at)


def test_the_new_font_draws_on_the_next_call():
    """v_fontinit (the 8x16), then v_enter_cur — the screen cleared in the new rows — then text in the new
    last row, sixteen scan lines a glyph: three calls, each from the one before's end state."""
    first = escape.run_console(fontinit(vdi.FONT_ROM_8X16, escape.console(*MIDDLE)))
    second = escape.run_console(escape.call("V_ENTER_CUR", onto=case.continued(first)))
    rows = vdi.SCREEN.height // vdi.rom_word(vdi.FONT_ROM_8X16 + vdi.field("FONT", "FORM_HEIGHT").at)
    third = escape.run_console(escape.call("V_CURTEXT", (ESC, ord("Y"), 0x20 + rows - 1, 0x20, *text("Hi")),
                                           case.continued(second)))
    assert cursor(third) == (2, rows - 1)
    fourth = escape.run(escape.call("VQ_CHCELLS", onto=case.continued(third)))
    assert fourth.intout(2) == [rows, vdi.SCREEN.width // vt52.CELL_HEIGHT]


# Two headers laid over the console's OWN block, so each reads back what it has just stored. The first's cell
# width IS CON_MAX_ROW, stored one step before it is read (and its height is the screen's width); the second's
# last character IS CON_FONT_FIRST, stored one step before it is read (its height and form width are two of the
# Line-A colour words, staged, as a zero height would divide by it).
FONT_OVER_THE_ROWS = addrs.CON_MAX_ROW - vdi.field("FONT", "MAX_CELL_WIDTH").at
FONT_OVER_THE_RANGE = addrs.CON_FONT_FIRST - vdi.field("FONT", "LAST_ADE").at
A_FORM_WIDTH = 0x100


@pytest.mark.parametrize("font", (FONT_OVER_THE_ROWS, FONT_OVER_THE_RANGE))
def test_v_fontinit_reads_each_field_after_the_store_before_it(font):
    colours = vdi.linea_pokes(COLBIT2=vt52.CELL_HEIGHT, COLBIT1=A_FORM_WIDTH)
    result = escape.run_console(fontinit(font, merge_pokes(escape.console(*MIDDLE), colours)))
    if font == FONT_OVER_THE_ROWS:
        assert result.word(addrs.CON_MAX_ROW) == (vdi.SCREEN.height // vdi.SCREEN.width - 1) & 0xFFFF
    else:
        assert result.word(addrs.CON_FONT_LAST) == result.word(addrs.CON_FONT_FIRST) == vt52.FONT_LAST


@pytest.mark.parametrize("field", ("FORM_HEIGHT", "MAX_CELL_WIDTH"))
def test_v_fontinit_of_a_0_divisor_is_a_zero_divide(field):
    """A header whose height or cell width is 0: `divu.w` by it — vector 5 on the machine, the idiom's named
    refusal here."""
    header = vdi.font_pokes(**{"FORM_HEIGHT": vt52.CELL_HEIGHT, "MAX_CELL_WIDTH": vt52.CELL_HEIGHT, field: 0})
    pokes = fontinit(vdi.FONT_AT, merge_pokes(escape.console(*MIDDLE), header))
    returncode, stderr, _ = vdi_helpers.refusal_over("vdi_escape", pokes, read_back=False)
    assert returncode == -signal.SIGABRT and "divu.w by zero" in stderr, (returncode, stderr)


# ---- the rows Tier 3 prices: each arm's WORST realistic case -------------------------------------------------
# The console arms with the cursor ON screen (depth 0: inverted off one cell and onto the next), the erases and
# the alpha-mode pair over the WHOLE screen from the top, the text arm over a full line that ends in a scroll.
A_LINE = (*text("The VDI escape writes this line through Bconout(CON:)"[:LAST_COLUMN + 1]), CR, LF)
ROWS = (
    ("nothing, past the table", escape.call(103, onto=escape.console(*MIDDLE))),
    ("nothing, the table's own rts", escape.call(0, onto=escape.console(*MIDDLE))),
    ("nothing, 20 just past the table", escape.call(vdi.VDI_ESCAPE_LAST + 1, onto=escape.console(*MIDDLE))),
    ("vq_chcells", escape.call("VQ_CHCELLS")),
    ("vq_curaddress", escape.call("VQ_CURADDRESS", onto=vt52.at(*MIDDLE))),
    ("vq_tabstatus", escape.call("VQ_TABSTATUS")),
    ("v_exit_cur, the screen cleared", escape.call("V_EXIT_CUR", onto=escape.console(*MIDDLE))),
    ("v_enter_cur, the screen cleared", escape.call("V_ENTER_CUR", onto=escape.console(*MIDDLE, cursor_depth=1))),
    ("v_curup, the cursor drawn", escape.call("V_CURUP", onto=escape.console(*MIDDLE))),
    ("v_curdown, the cursor drawn", escape.call("V_CURDOWN", onto=escape.console(*MIDDLE))),
    ("v_curright, the cursor drawn", escape.call("V_CURRIGHT", onto=escape.console(*MIDDLE))),
    ("v_curleft, the cursor drawn", escape.call("V_CURLEFT", onto=escape.console(*MIDDLE))),
    ("v_curhome, the cursor drawn", escape.call("V_CURHOME", onto=escape.console(*MIDDLE))),
    ("v_eeos, the whole screen", escape.call("V_EEOS", onto=escape.console(0, 0))),
    ("v_eeol, a whole line", escape.call("V_EEOL", onto=escape.console(0, MIDDLE[1]))),
    ("vs_curaddress, the cursor drawn", escape.call("VS_CURADDRESS", (MIDDLE[1] + 1, MIDDLE[0] + 1),
                                                    escape.console(0, 0))),
    ("v_curtext, a line and a scroll", escape.call("V_CURTEXT", A_LINE, escape.console(0, LAST_ROW))),
    ("v_rvon", escape.call("V_RVON", onto=escape.console(*MIDDLE))),
    ("v_rvoff", escape.call("V_RVOFF", onto=escape.console(*MIDDLE, extra_flags=vt52.REVERSE))),
    ("v_hardcopy, a staged dump", escape.hardcopy_pokes()),
    ("v_dspcur, forced", escape.call("V_DSPCUR", (1,), merge_pokes(vdi.linea_pokes(M_HID_CT=3, GCURX=40, GCURY=30),
                                                                   vdi_raster.CANVAS))),
    ("v_rmcur, the arrow removed", escape.call("V_RMCUR")),
    ("v_offset, under the cursor", escape.call("V_OFFSET", (vt52.CELL_HEIGHT,), escape.console(*MIDDLE))),
    ("v_fontinit, the 8x16", fontinit(vdi.FONT_ROM_8X16, escape.console(*MIDDLE))),
    # ...and each arm's WORST realistic row, where that is not the heavy one above: a move refused at the edge, and
    # the arms at the captured desktop's own cursor depth (2), where nothing is drawn to amortise the dispatch.
    ("v_curup, at the top", escape.call("V_CURUP", onto=escape.console(MIDDLE[0], 0))),
    ("v_curdown, at the bottom", escape.call("V_CURDOWN", onto=escape.console(MIDDLE[0], LAST_ROW))),
    ("v_curright, at the last column", escape.call("V_CURRIGHT", onto=escape.console(LAST_COLUMN, MIDDLE[1]))),
    ("v_curleft, at column 0", escape.call("V_CURLEFT", onto=escape.console(0, MIDDLE[1]))),
    ("v_curhome, the cursor hidden", escape.call("V_CURHOME", onto=escape.console(*MIDDLE, cursor_depth=2))),
    ("vs_curaddress, the cursor hidden", escape.call("VS_CURADDRESS", (MIDDLE[1] + 1, MIDDLE[0] + 1),
                                                     escape.console(0, 0, cursor_depth=2))),
    ("v_curtext, one character, the cursor hidden",
     escape.call("V_CURTEXT", text("a"), escape.console(*MIDDLE, cursor_depth=2))),
    # ...and the two words a sequence or a string most often begins with, which the console answers by state alone.
    ("v_curtext, one ESC, the cursor hidden", escape.call("V_CURTEXT", (ESC,), escape.console(*MIDDLE, cursor_depth=2))),
    ("v_curtext, one NUL, the cursor hidden", escape.call("V_CURTEXT", (0,), escape.console(*MIDDLE, cursor_depth=2))),
    ("v_eeol, the last cell, the cursor hidden",
     escape.call("V_EEOL", onto=escape.console(LAST_COLUMN, MIDDLE[1], cursor_depth=2))),
    ("v_eeos, the last cell, the cursor hidden",
     escape.call("V_EEOS", onto=escape.console(LAST_COLUMN, LAST_ROW, cursor_depth=2))),
    ("v_offset, the cursor hidden", escape.call("V_OFFSET", (vt52.CELL_HEIGHT,), escape.console(*MIDDLE, cursor_depth=2))),
    ("v_dspcur, not drawn", escape.call("V_DSPCUR", (1,), vdi.linea_pokes(M_HID_CT=0))),
    ("v_rmcur, already hidden", escape.call("V_RMCUR", onto=vdi.linea_pokes(M_HID_CT=1))),
)
for _label, _pokes in ROWS:
    vdi.register(f"vdi_escape, {_label}", addrs.VDI_ROM_ESCAPE, _pokes)


@pytest.mark.parametrize("label,pokes", ROWS)
def test_every_priced_row_is_a_differential(label, pokes):
    runner = escape.run_hardcopy if label.startswith("v_hardcopy") else escape.run_console
    runner(pokes)
