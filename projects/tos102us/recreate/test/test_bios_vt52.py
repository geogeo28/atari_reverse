"""BIOS Bconout(CON:) @ $fc42f2 and Bconout(RAW:) @ $fc42e6 — the VT52 console on a bitmap.

Devices 2 and 5 of the table `test_bios_bconout.py` walks, and the only driver in this project that
is a SUBSYSTEM rather than a leaf: a state machine over the escape sequences, seven control codes, a
glyph renderer, two scrolls, a rectangle clear and a cursor that is locked around every one of them
(`src/bios/vt52.c`, `src/bios/conout_glyph.c`).

IT READS NO HARDWARE, so no case here declares a byte. The screen base is `_v_bas_ad` in RAM and the
cell geometry is what the boot derived from the resolution it came up in, so the whole driver is
ordinary memory and Tier 1 compares every pixel it writes.

THE STATE IS A ROM ADDRESS IN RAM ($4a8) and the entry is a `jmp` through it, which is what lets a
case drive one state at a time: `ESC Y <row> <column>` is three characters and three separate
`Bconout` calls, so the cases below poke the state the second and third of them would have found.
That is the same method `test_bios_bconstat.py` uses for the device tables — read what is in RAM,
stage what the case is about — rather than a three-call harness this file would be alone in having.

THREE THINGS THE CASES ARE BUILT AROUND.

*THE CURSOR'S LOCK IS A DEPTH, NOT A FLAG.* Every screen change brackets itself in `disable += 1` and
a matching decrement, and only the decrement that reaches ZERO puts the cursor back. The captured
desktop left the depth at 2 — a console whose cursor stays off screen — where a program calling
`Bconout` finds 0, so `vt52.staged` defaults to 0 and the cases that want the ROM's own captured
state say so.

*THE UNLOCK LEAVES THE DEPTH IN D0*, which is the register the position routines take a COLUMN in.
`ESC l` erases a line and then places the cursor with whatever D0 holds, so at depth 0 it homes the
cursor and at depth 2 it puts it in column 1. Both are driven.

*WRAP IS OFF IN THE SNAPSHOT.* Bit 3 of the flag byte is clear, so a glyph in the last column moves
nothing at all; the wrap and the scroll it ends in are reached by a case that sets it.
"""
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import bcon
import case
import isr
import test_xbios_cursconf as cursconf
import vt52

DEVICE_CONSOLE = 2
DEVICE_RAW = 5

A_CHARACTER = 0x41                  # 'A'
PRINTABLE = (0x20, A_CHARACTER, 0x7E, 0xB0, 0xFF)
ESC = addrs.CON_ESC

run = bcon.output_runner(addrs.BIOS_BCONOUT, _lib.bios_bconout)

# THE POISON PASS IS OFF HERE, AND THAT IS A CLAIM RATHER THAN A CONVENIENCE. `case.run`'s
# attribution check inverts every byte the oracle WROTE and runs both cores again — and on this
# driver those bytes ARE its control state: the cursor's screen ADDRESS, which the next run's glyph
# and cursor renderer index the screen through, and the state VECTOR at $4a8, which the entry jumps
# through. An inverted cursor address is not a screen address at all and an inverted state vector is
# none of the ROM's six, so the poisoned run is not this routine on a different image — it is a
# different routine, and the reconstruction's own halt fires where the original walks its address
# space. (`docs/agent-playbook.md` §4 names exactly this case: "poisoning an output that also steers
# control flow can perturb a complex function".)
#
# WHAT REPLACES IT, for the cases that are about pixels, is `vt52.canary`: the cell is filled with a
# byte no glyph and no cleared cell can be, so a candidate that skipped a store leaves the canary
# where the oracle left a pixel and the plain diff reds. The two cases that write NO control state —
# the bell and the control codes the gate refuses — keep the real pass.
NO_POISON = False


def console(character, pokes=None, *, device=DEVICE_CONSOLE, poison=NO_POISON, **kwargs):
    """One character to the console, over a staged block (`vt52.staged`'s defaults)."""
    return run(device, character, pokes={**vt52.staged(), **(pokes or {})}, poison=poison, **kwargs)


def raw(character, pokes=None, **kwargs):
    """...and one to the RAW console, which is the same entry one device along."""
    return console(character, pokes, device=DEVICE_RAW, **kwargs)


def escape(character, pokes=None, **kwargs):
    """...and one character to the console with ESC already seen."""
    return console(character, {**vt52.state(addrs.CON_STATE_ESCAPE), **(pokes or {})}, **kwargs)


def screen_writes(info):
    """Only the bytes that landed on SCREEN, as {address: byte}. Everything else the run wrote — the
    console block, the stack the harness drops — is asserted by name where a case is about it."""
    screen_bytes = vt52.ROW_BYTES * (vt52.MAX_ROW + 1)
    return {at: value for at, value in info["writes"].items()
            if vt52.SCREEN <= at < vt52.SCREEN + screen_bytes}


def cursor_after(info, field, size=2):
    """One of the cursor's three fields as the ORACLE left it — a KeyError naming the field if the
    routine never stored it, which is what separates "moved the cursor" from "left it alone"."""
    return case.written(info, field, size)


# ---- the machine these cases describe ------------------------------------------------------------

def test_the_state_vector_and_the_four_screen_routines_are_the_ones_reconstructed():
    """All five are LONGWORDS OF RAM. The state decides which of six routines a character reaches;
    the other four are the screen primitives, and TOS 1.02 installs its BLITTER variants instead on a
    machine that has one — so a reconstruction reads them rather than assuming them, and this is what
    says the captured machine is the plain ST the CPU set belongs to."""
    vector = isr.vector_in_snapshot

    assert vector(addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL
    assert vector(addrs.CON_VECTOR_GLYPH) == addrs.CONOUT_GLYPH_CPU
    assert vector(addrs.CON_VECTOR_SCROLL_UP) == addrs.CONOUT_SCROLL_UP_CPU
    assert vector(addrs.CON_VECTOR_SCROLL_DOWN) == addrs.CONOUT_SCROLL_DOWN_CPU
    assert vector(addrs.CON_VECTOR_CLEAR) == addrs.CONOUT_CLEAR_CPU


def test_the_captured_console_is_a_colour_screen_with_the_cursor_locked_away():
    """What the cases below are staged against, asserted rather than assumed: four planes of 40x25
    cells, a text row that is the cell height times the line pitch, and a desktop that had locked the
    cursor twice and turned WRAP off."""
    assert vt52.ROW_BYTES == vt52.LINE_BYTES * vt52.CELL_HEIGHT
    assert vt52.PLANES * 2 == vt52.GROUP_BYTES
    assert (vt52.MAX_COLUMN + 1) * vt52.PLANES == vt52.LINE_BYTES
    assert (vt52.MAX_ROW + 1) * vt52.ROW_BYTES <= addrs.ST_RAM_BYTES - vt52.SCREEN
    assert vt52.SNAPSHOT_CURSOR_DEPTH == 2
    assert not vt52.SNAPSHOT_FLAGS & vt52.WRAP


# ---- the glyph ------------------------------------------------------------------------------------

@pytest.mark.parametrize("character", PRINTABLE)
def test_a_glyph_is_the_font_s_own_column_in_every_plane(character):
    """THE PIXELS, not just an agreement about them. The font's offset table is in BITS and its form
    rows are `CON_FONT_FORM_BYTES` apart, so the case can derive the eight bytes a character's column
    is and assert that each plane got exactly them — white on black being `$ffff` over `0`, which is
    "every plane's foreground bit set" whatever the plane count."""
    expected = vt52.glyph_column(character)
    info = console(character, {**vt52.staged(cursor_depth=1), **vt52.canary(0, 0)})
    for plane in range(vt52.PLANES):
        for line, byte in enumerate(expected):
            at = vt52.cell_address(0, 0) + plane * 2 + line * vt52.LINE_BYTES
            assert case.written(info, at, 1) == byte, f"plane {plane}, line {line}"
    assert set(screen_writes(info)) == set(vt52.cell_bytes(0, 0))


@pytest.mark.parametrize("column", (0, 1, 2, 3, 38, 39))
def test_a_glyph_lands_on_the_half_of_its_sixteen_pixel_group_its_column_names(column):
    """A character cell is EIGHT pixels and a screen group is SIXTEEN, so an even column is a group's
    first byte and an odd one the byte after it. `bclr #0,d2 / sne d4 / mulu.w PLANES,d2 / addx.l` is
    the ROM's way of saying that, and a reconstruction that multiplied the column itself would put
    every odd one a whole group too far along."""
    info = console(A_CHARACTER, {**vt52.staged(column, 0, cursor_depth=1),
                                 **vt52.canary(column, 0)})
    assert set(screen_writes(info)) == set(vt52.cell_bytes(column, 0))


@pytest.mark.parametrize("row", (0, 1, 12, 24))
def test_a_glyph_lands_on_the_text_row_the_cursor_names(row):
    info = console(A_CHARACTER, {**vt52.staged(0, row, cursor_depth=1), **vt52.canary(0, row)})
    assert set(screen_writes(info)) == set(vt52.cell_bytes(0, row))


@pytest.mark.parametrize("foreground, background, selector, why", (
    (0xFFFF, 0x0000, "glyph", "white on black: every plane takes the font's own bits"),
    (0x0000, 0x0000, "clear", "black on black: every plane is stored as zero, and the font is not "
                              "read at all"),
    (0xFFFF, 0xFFFF, "solid", "white on white: every plane is stored as $ff"),
    (0x0000, 0xFFFF, "inverted", "black on white: every plane takes the font's bits complemented"),
))
def test_the_two_colours_choose_what_each_plane_s_byte_is(foreground, background, selector, why):
    """`lsr.w #1,d6 / addx.w / lsr.w #1,d7 / roxl.w #3,d5` indexes a FOUR-entry jump table per plane,
    and two of its arms never look at the font. One bit of each colour per plane, LSB first."""
    glyph = vt52.glyph_column(A_CHARACTER)
    expected = {"glyph": glyph, "clear": [0x00] * vt52.CELL_HEIGHT,
                "solid": [0xFF] * vt52.CELL_HEIGHT,
                "inverted": [byte ^ 0xFF for byte in glyph]}[selector]
    info = console(A_CHARACTER, {**vt52.staged(cursor_depth=1), **vt52.canary(0, 0),
                                 **vt52.colours(foreground, background)})
    for plane in range(vt52.PLANES):
        for line, byte in enumerate(expected):
            at = vt52.cell_address(0, 0) + plane * 2 + line * vt52.LINE_BYTES
            assert case.written(info, at, 1) == byte, why


def test_each_plane_takes_its_own_bit_of_each_colour():
    """The sweep above moves both colours together, which four identical planes cannot tell from a
    reconstruction that read bit 0 four times. This one gives every plane a different pair."""
    glyph = vt52.glyph_column(A_CHARACTER)
    foreground, background = 0b0101, 0b0110
    per_plane = [glyph, [byte ^ 0xFF for byte in glyph], [0xFF] * vt52.CELL_HEIGHT,
                 [0x00] * vt52.CELL_HEIGHT]
    info = console(A_CHARACTER, {**vt52.staged(cursor_depth=1), **vt52.canary(0, 0),
                                 **vt52.colours(foreground, background)})
    for plane, expected in enumerate(per_plane):
        for line, byte in enumerate(expected):
            at = vt52.cell_address(0, 0) + plane * 2 + line * vt52.LINE_BYTES
            assert case.written(info, at, 1) == byte, f"plane {plane}"


def test_reverse_video_swaps_the_two_colours_for_the_glyph_alone():
    """`btst #4,(a4) / exg d6,d7` — the flag `ESC p` sets. It swaps the REGISTERS and leaves the two
    words in the block alone, so nothing about the console's state changes with it."""
    plain = console(A_CHARACTER, vt52.staged(cursor_depth=1))
    reversed_ = console(A_CHARACTER, vt52.staged(cursor_depth=1, extra_flags=vt52.REVERSE))
    for at, byte in screen_writes(plain).items():
        assert screen_writes(reversed_)[at] == byte ^ 0xFF
    assert addrs.CON_COLOUR_FOREGROUND not in reversed_["writes"]
    assert addrs.CON_COLOUR_BACKGROUND not in reversed_["writes"]


@pytest.mark.parametrize("first, last, character, draws, why", (
    (0x00, 0xFF, 0x41, True, "the snapshot's own range, as the control every other row needs"),
    (0x42, 0xFF, 0x41, False, "below the first code the font draws"),
    (0x00, 0x40, 0x41, False, "...and above the last"),
    (0x41, 0x41, 0x40, False, "a one-character font, from below"),
    (0x41, 0x41, 0x42, False, "...and from above"),
    (0x0000, 0x8000, 0x41, True,
     "`bhi`, not `bgt`: a LAST code with bit 15 set is a huge one and not a negative one, so every "
     "code the entry can produce is still inside the font"),
    (0x8000, 0x7FFF, 0x41, False,
     "...and `bcs`, not `blt`, on the FIRST: a signed reading would admit this as `65 > -32768`"),
))
def test_the_font_range_is_two_unsigned_compares_and_its_arm_does_nothing_at_all(
        first, last, character, draws, why):
    """`cmp.w FONT_FIRST,d1 / bcs` and `cmp.w FONT_LAST,d1 / bhi` — and the arm they take is a plain
    `rts`, so on a character the font does not draw not even the cursor moves.

    THE RANGE IS WHAT A CASE MOVES, because the captured font covers the whole byte and the entry's
    own `and.w #$ff` can never leave it. So the two early-outs are unreachable on the machine as it
    stands, and the last two rows above are the only thing in this project that says these two
    compares are UNSIGNED.
    """
    assert (vt52.FONT_FIRST, vt52.FONT_LAST) == (0x00, 0xFF), (
        "the captured font draws every code the entry can produce; the rows above narrow it")
    pokes = {**vt52.staged(cursor_depth=1),
             addrs.CON_FONT_LAST: struct.pack(">HH", last, first)}   # LAST then FIRST: $2988, $298a
    info = raw(character, pokes)
    assert (screen_writes(info) != {}) is draws, why
    assert (addrs.CON_CURSOR_COLUMN in info["writes"]) is draws, why


# ---- the cursor step a glyph ends in --------------------------------------------------------------

@pytest.mark.parametrize("column", (0, 1, 2, 7, 38))
def test_the_cursor_steps_one_cell_and_across_a_group_on_every_other_one(column):
    """`addq.w #1,a1` always, plus `lea -2(a1,PLANES*2.w),a1` when the NEW column is EVEN — because
    an even column starts a new 16-pixel group and the odd one before it was the same group's second
    byte."""
    info = console(A_CHARACTER, vt52.staged(column, 3, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == column + 1
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 3
    assert cursor_after(info, addrs.CON_CURSOR_ADDRESS, 4) == vt52.cell_address(column + 1, 3)


def test_the_last_column_moves_nothing_when_wrap_is_off():
    """`btst #3,(a4) / beq` straight to the unlock: the glyph is drawn and the cursor stays where it
    is, which is the snapshot's own setting and what a `Bconout` loop past the right margin does."""
    info = console(A_CHARACTER, vt52.staged(vt52.MAX_COLUMN, 3, cursor_depth=1,
                                            without_flags=vt52.WRAP))
    assert set(screen_writes(info)) == set(vt52.cell_bytes(vt52.MAX_COLUMN, 3))
    assert addrs.CON_CURSOR_COLUMN not in info["writes"]
    assert addrs.CON_CURSOR_ADDRESS not in info["writes"]


def test_the_last_column_wraps_to_the_next_row_when_wrap_is_on():
    info = console(A_CHARACTER, vt52.staged(vt52.MAX_COLUMN, 3, cursor_depth=1,
                                            extra_flags=vt52.WRAP))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 4
    assert cursor_after(info, addrs.CON_CURSOR_ADDRESS, 4) == vt52.cell_address(0, 4)


def test_the_last_cell_of_the_screen_scrolls_and_leaves_the_cursor_on_the_last_row():
    """The corner case of the corner: wrap on, last column, last row. The screen moves up a row, the
    cursor goes to column 0 of the row it is already on, and the row it vacated is cleared — so the
    top row now holds what the second row held and the bottom one is background."""
    row_above = {at: BASE_IMAGE[at] for at in range(vt52.SCREEN + vt52.ROW_BYTES,
                                                    vt52.SCREEN + 2 * vt52.ROW_BYTES)}
    info = console(A_CHARACTER, vt52.staged(vt52.MAX_COLUMN, vt52.MAX_ROW, cursor_depth=1,
                                            extra_flags=vt52.WRAP))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == vt52.MAX_ROW
    assert cursor_after(info, addrs.CON_CURSOR_ADDRESS, 4) == vt52.cell_address(0, vt52.MAX_ROW)
    for at, byte in row_above.items():
        assert case.written(info, at - vt52.ROW_BYTES, 1) == byte, "row 1 did not move to row 0"
    last_row = vt52.SCREEN + vt52.MAX_ROW * vt52.ROW_BYTES
    assert all(case.written(info, last_row + offset, 1) == 0
               for offset in range(0, vt52.ROW_BYTES, 97)), "the vacated row is not background"


# ---- the control codes ----------------------------------------------------------------------------

# Every code below $20, and whether the ROM's `subq.w #7 / bmi / cmp.w #6 / bgt` gate lets it act.
ACTIVE_CONTROL_CODES = (addrs.CON_BEL, addrs.CON_BS, addrs.CON_TAB, addrs.CON_LF, addrs.CON_VT,
                        addrs.CON_FF, addrs.CON_CR, ESC)


@pytest.mark.parametrize("code", [code for code in range(0x20) if code not in ACTIVE_CONTROL_CODES])
def test_a_control_code_outside_the_gate_changes_nothing(code):
    """`$00`..`$06` and `$0e`..`$1f` bar ESC: the gate's two branches both reach a bare `rts`, so
    neither the screen nor the block nor the state moves."""
    info = console(code, vt52.staged(5, 5), poison=True)
    assert screen_writes(info) == {}
    assert addrs.CON_STATE_VECTOR not in info["writes"]
    assert addrs.CON_CURSOR_COLUMN not in info["writes"]


def test_escape_only_changes_the_state():
    info = console(ESC, vt52.staged(5, 5))
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_ESCAPE
    assert screen_writes(info) == {}


@pytest.mark.parametrize("code", (addrs.CON_LF, addrs.CON_VT, addrs.CON_FF))
def test_line_feed_vertical_tab_and_form_feed_are_one_arm(code):
    """Three table entries, one address: all three move the cursor one row down and none of them
    touches the column."""
    info = console(code, vt52.staged(7, 5, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 6
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 7


def test_a_line_feed_on_the_last_row_scrolls_instead_of_moving():
    row_above = {at: BASE_IMAGE[at] for at in range(vt52.SCREEN + vt52.ROW_BYTES,
                                                    vt52.SCREEN + 2 * vt52.ROW_BYTES, 89)}
    info = console(addrs.CON_LF, vt52.staged(7, vt52.MAX_ROW, cursor_depth=1))
    assert addrs.CON_CURSOR_ROW not in info["writes"], "the cursor stays on the last row"
    for at, byte in row_above.items():
        assert case.written(info, at - vt52.ROW_BYTES, 1) == byte


def test_carriage_return_goes_to_column_zero_of_the_same_row():
    info = console(addrs.CON_CR, vt52.staged(7, 5, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 5


@pytest.mark.parametrize("column, expected", ((0, 8), (1, 8), (7, 8), (8, 16), (33, vt52.MAX_COLUMN),
                                              (vt52.MAX_COLUMN, vt52.MAX_COLUMN)))
def test_tab_goes_to_the_next_multiple_of_eight_and_is_clamped_rather_than_bounded(column,
                                                                                   expected):
    """`andi.w #-8,d0 / addq.w #8,d0`, with NO check against the last column — so a tab from column
    33 asks for 40 and it is `cell_address`'s own clamp that brings it back to 39, and a tab from the
    last column asks for 40 too rather than staying put."""
    info = console(addrs.CON_TAB, vt52.staged(column, 5, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == expected


@pytest.mark.parametrize("column, expected", ((0x8000, vt52.MAX_COLUMN),
                                              (0x8027, vt52.MAX_COLUMN),
                                              (0x8028, 0x8028)))
def test_the_column_clamp_is_the_n_flag_of_a_word_difference_and_not_a_signed_compare(column,
                                                                                      expected):
    """`cmp.w d0,d2 / bpl` at $fc49c8 reads bit 15 of `max_column - column` and nothing else, so it
    parts company with `column > max_column` exactly where that subtraction OVERFLOWS a word.

    ESC A carries the stored column straight into `cell_address`, which is where the clamp is. The
    first two rows are inside the overflow window — $27 - $8000 is $8027 and $27 - $8027 is $8000,
    both negative, so the ROM clamps where a signed compare would not — and the third is the first
    column past it ($27 - $8028 is $7fff), which neither reading clamps. That third row is the
    control: it says the first two red on the FLAG and not on the clamp firing everywhere.
    """
    info = escape(0x41, vt52.staged(column, 5, cursor_depth=1))      # ESC A, cursor up
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == expected


def test_the_row_clamp_is_the_same_n_flag_test():
    """The second half, `cmp.w d1,d2 / bpl` at $fc49d2. ESC B steps a row of $8001 to $8002, and
    `max_row - $8002` overflows negative just as the column's does, so the row comes back clamped."""
    info = escape(0x42, vt52.staged(7, 0x8001, cursor_depth=1))      # ESC B, cursor down
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == vt52.MAX_ROW


@pytest.mark.parametrize("column, moves", ((0, False), (1, True), (vt52.MAX_COLUMN, True)))
def test_backspace_is_the_same_arm_as_escape_d(column, moves):
    plain = console(addrs.CON_BS, vt52.staged(column, 5, cursor_depth=1))
    as_escape = escape(0x44, vt52.staged(column, 5, cursor_depth=1))   # ESC D
    assert (addrs.CON_CURSOR_COLUMN in plain["writes"]) is moves
    assert screen_writes(plain) == screen_writes(as_escape)


@pytest.mark.parametrize("conterm, rings", ((1 << addrs.CONTERM_BELL_BIT, True), (0x00, False),
                                            (0xFF, True), (0xFF & ~(1 << addrs.CONTERM_BELL_BIT),
                                                            False)))
def test_the_bell_arms_the_sound_driver_and_takes_no_trap(conterm, rings):
    """BEL is TWO STORES INTO RAM: the ROM's own bell list becomes the 200 Hz driver's next command
    and the delay before it is cleared, which `src/bios/timerc.c` then plays. `conterm` bit 2 is the
    gate, and a machine with it clear writes nothing at all."""
    info = console(addrs.CON_BEL, {**vt52.staged(5, 5), addrs.SYSVAR_CONTERM: bytes([conterm])},
                   poison=True)
    assert (addrs.SOUND_LIST_POINTER in info["writes"]) is rings
    if rings:
        assert case.written_long(info, addrs.SOUND_LIST_POINTER) == addrs.BELL_SOUND_LIST
        assert case.written(info, addrs.SOUND_LIST_DELAY, 1) == 0
    assert screen_writes(info) == {}


# ---- the escape sequences --------------------------------------------------------------------------

@pytest.mark.parametrize("character, column, row, expected, why", (
    (0x41, 7, 5, (7, 4), "ESC A: up"),
    (0x41, 7, 0, None, "...and nothing at the top"),
    (0x42, 7, 5, (7, 6), "ESC B: down"),
    (0x42, 7, vt52.MAX_ROW, None, "...and nothing at the bottom"),
    (0x43, 7, 5, (8, 5), "ESC C: right"),
    (0x43, vt52.MAX_COLUMN, 5, None, "...and nothing at the right margin"),
    (0x44, 7, 5, (6, 5), "ESC D: left"),
    (0x44, 0, 5, None, "...and nothing at the left margin"),
    (0x48, 7, 5, (0, 0), "ESC H: home"),
))
def test_a_cursor_escape_stops_at_the_edge_rather_than_wrapping(character, column, row, expected,
                                                                why):
    info = escape(character, vt52.staged(column, row, cursor_depth=1))
    if expected is None:
        assert addrs.CON_CURSOR_COLUMN not in info["writes"], why
        return
    assert (cursor_after(info, addrs.CON_CURSOR_COLUMN),
            cursor_after(info, addrs.CON_CURSOR_ROW)) == expected, why


@pytest.mark.parametrize("character", (0x46, 0x47, 0x67, 0x68, 0x69, 0x6D, 0x6E, 0x72, 0x73, 0x74,
                                       0x75))
def test_an_escape_whose_table_entry_is_a_bare_rts_does_nothing(character):
    """`ESC F`, `ESC G` and the nine lower-case entries that point at $fc4376. They are in the ROM's
    tables — this is not the out-of-range arm below — and they are all the same `rts`."""
    info = escape(character, vt52.staged(7, 5))
    assert screen_writes(info) == {}
    assert addrs.CON_CURSOR_COLUMN not in info["writes"]
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL


@pytest.mark.parametrize("character", (0x00, 0x20, 0x40, 0x4E, 0x58, 0x5A, 0x61, 0x78, 0xFF))
def test_an_escape_outside_the_three_ranges_costs_exactly_one_character(character):
    """Below `A`, between `M` and `Y`, between `Y` and `b`, and above `w`. The state is put back to
    normal FIRST, whatever follows — so an unimplemented escape swallows its own letter and the next
    character is an ordinary one."""
    info = escape(character, vt52.staged(7, 5))
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL
    assert screen_writes(info) == {}


@pytest.mark.parametrize("character, state", ((0x59, addrs.CON_STATE_AWAIT_Y_ROW),
                                              (0x62, addrs.CON_STATE_AWAIT_FOREGROUND),
                                              (0x63, addrs.CON_STATE_AWAIT_BACKGROUND)))
def test_the_three_escapes_that_take_an_argument_install_a_state_for_it(character, state):
    info = escape(character, vt52.staged(7, 5))
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == state
    assert screen_writes(info) == {}


@pytest.mark.parametrize("flag_character, bit, why", (
    (0x70, vt52.REVERSE, "ESC p: reverse video on"),
    (0x76, vt52.WRAP, "ESC v: wrap at the last column on"),
))
def test_an_escape_that_sets_a_flag_sets_only_that_bit(flag_character, bit, why):
    clear = vt52.SNAPSHOT_FLAGS & ~(bit | vt52.DRAWN)
    info = escape(flag_character, {**vt52.staged(7, 5, cursor_depth=1), **vt52.flags(clear)})
    assert case.written(info, addrs.CON_STATE_FLAGS, 1) == clear | bit, why


@pytest.mark.parametrize("flag_character, bit, why", (
    (0x71, vt52.REVERSE, "ESC q: reverse video off"),
    (0x77, vt52.WRAP, "ESC w: wrap off"),
))
def test_an_escape_that_clears_a_flag_clears_only_that_bit(flag_character, bit, why):
    info = escape(flag_character, {**vt52.staged(7, 5, cursor_depth=1), **vt52.flags(0xFF)})
    assert case.written(info, addrs.CON_STATE_FLAGS, 1) == 0xFF & ~bit, why


# ---- the argument states ----------------------------------------------------------------------------

@pytest.mark.parametrize("character", (0x20, 0x21, 0x41, 0xFF))
def test_escape_y_holds_its_row_and_waits_for_the_column(character):
    """`sub.w #32,d1 / move.w d1,CON_ESCAPE_Y_ROW` — a WORD, and biased by a space, which is how
    VT52 spells a small number as a printable character. A character below a space underflows into a
    row the column state will then clamp."""
    info = console(character, {**vt52.staged(7, 5),
                               **vt52.state(addrs.CON_STATE_AWAIT_Y_ROW)})
    assert case.written(info, addrs.CON_ESCAPE_Y_ROW, 2) == (character - 0x20) & 0xFFFF
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_AWAIT_Y_COLUMN


@pytest.mark.parametrize("row_argument, column_character, expected, why", (
    (0x20, 0x20, (0, 0), "ESC Y <space> <space> is the home position"),
    (0x25, 0x28, (8, 5), "...and both arguments are biased by a space"),
    (0x20 + vt52.MAX_ROW, 0x20 + vt52.MAX_COLUMN, (vt52.MAX_COLUMN, vt52.MAX_ROW),
     "the bottom right cell"),
    (0x7F, 0x7F, (vt52.MAX_COLUMN, vt52.MAX_ROW), "...and anything past it is CLAMPED, not wrapped"),
))
def test_escape_y_places_the_cursor_and_clamps_both_coordinates(row_argument, column_character,
                                                                expected, why):
    """`cmp.w d0,d2 / bpl` twice, and the clamp is what the caller's own D0 comes back as.

    WHICH `b??` THOSE TWO ARE is half driven and half read off the disassembly. `bpl` against a
    `blt` is DRIVEN, two cases above, at the window where the word difference overflows. `bpl`
    against a `bcc` is not, and is out of this battery's reach: it would take a coordinate whose
    unclamped cell address is not in the machine's megabyte, so the reconstruction's own bound
    fires where the original walks its address space. Recorded as an honest gap rather than
    claimed (`recreate/STATUS.md`).
    """
    pokes = {**vt52.staged(7, 5, cursor_depth=1),
             **vt52.state(addrs.CON_STATE_AWAIT_Y_COLUMN),
             addrs.CON_ESCAPE_Y_ROW: struct.pack(">H", (row_argument - 0x20) & 0xFFFF)}
    info = console(column_character, pokes)
    assert (cursor_after(info, addrs.CON_CURSOR_COLUMN),
            cursor_after(info, addrs.CON_CURSOR_ROW)) == expected, why
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL


@pytest.mark.parametrize("state, field", ((addrs.CON_STATE_AWAIT_FOREGROUND,
                                           addrs.CON_COLOUR_FOREGROUND),
                                          (addrs.CON_STATE_AWAIT_BACKGROUND,
                                           addrs.CON_COLOUR_BACKGROUND)))
@pytest.mark.parametrize("character", (0x20, 0x2F, 0x20 + 15, 0x00))
def test_a_colour_escape_stores_its_biased_argument_as_a_word(state, field, character):
    """One bit a plane, so a four-plane screen uses four of the sixteen and the rest are stored and
    ignored. The bias is a space here as it is for `ESC Y`, and the store is a WORD."""
    info = console(character, {**vt52.staged(7, 5), **vt52.state(state)})
    assert case.written(info, field, 2) == (character - 0x20) & 0xFFFF
    assert case.written_long(info, addrs.CON_STATE_VECTOR) == addrs.CON_STATE_NORMAL


# ---- the erasing escapes -----------------------------------------------------------------------------

def screen_byte_after(info, at):
    """One screen byte as the run left it: what the oracle wrote there, or what the snapshot held if
    it wrote nothing. Every claim below is about the SCREEN rather than about which words the ROM's
    read-modify-writes happened to touch, which is not the same question — see `unchanged`."""
    return info["writes"].get(at, BASE_IMAGE[at])


def cleared(info, column, row):
    """Every byte of one character cell is the background colour — zero in each plane, which is what
    the snapshot's `CON_COLOUR_BACKGROUND` of 0 makes it."""
    return all(screen_byte_after(info, at) == 0 for at in vt52.cell_bytes(column, row))


def unchanged(info, column, row):
    """...and every byte of it is what it was.

    NOT "nothing was written here": a character cell is EIGHT pixels and the clear works in
    16-pixel GROUPS, so the cell beside an odd edge sits in a word the ROM's `and.l`/`or.l` pair
    re-stores with the value it already had. The edge MASK is what keeps it, and that is the claim —
    a test of the access width instead would fail on a correct reconstruction.
    """
    return all(screen_byte_after(info, at) == BASE_IMAGE[at] for at in vt52.cell_bytes(column, row))


def test_escape_k_clears_from_the_cursor_to_the_end_of_its_line_and_no_further():
    info = escape(0x4B, vt52.staged(7, 5, cursor_depth=1))
    assert cleared(info, 7, 5) and cleared(info, vt52.MAX_COLUMN, 5)
    assert unchanged(info, 6, 5) and unchanged(info, 0, 6) and unchanged(info, 0, 4)


def test_escape_j_clears_from_the_cursor_to_the_bottom_right():
    info = escape(0x4A, vt52.staged(7, 5, cursor_depth=1))
    assert cleared(info, 7, 5) and cleared(info, 0, 6) and cleared(info, vt52.MAX_COLUMN,
                                                                   vt52.MAX_ROW)
    assert unchanged(info, 6, 5) and unchanged(info, vt52.MAX_COLUMN, 4)


def test_escape_j_on_the_last_row_clears_only_that_row_s_tail():
    """`cmp.w d3,d1 / beq` — the second clear is skipped outright, which is what separates this from
    a reconstruction that asked for rows 25..24 and cleared nothing, or everything."""
    info = escape(0x4A, vt52.staged(7, vt52.MAX_ROW, cursor_depth=1))
    assert cleared(info, 7, vt52.MAX_ROW) and unchanged(info, 6, vt52.MAX_ROW)
    assert unchanged(info, 0, vt52.MAX_ROW - 1)


def test_escape_o_clears_from_the_start_of_the_line_to_the_cursor_inclusive():
    info = escape(0x6F, vt52.staged(7, 5, cursor_depth=1))
    assert cleared(info, 0, 5) and cleared(info, 7, 5)
    assert unchanged(info, 8, 5)


def test_escape_d_clears_everything_above_the_cursor_and_its_line_up_to_it():
    info = escape(0x64, vt52.staged(7, 5, cursor_depth=1))
    assert cleared(info, 0, 0) and cleared(info, vt52.MAX_COLUMN, 4) and cleared(info, 7, 5)
    assert unchanged(info, 8, 5) and unchanged(info, 0, 6)


def test_escape_d_on_the_top_row_clears_only_that_row_s_head():
    info = escape(0x64, vt52.staged(7, 0, cursor_depth=1))
    assert cleared(info, 0, 0) and cleared(info, 7, 0) and unchanged(info, 8, 0)
    assert unchanged(info, 0, 1)


# BACKGROUNDS WHOSE TWO PLANE PAIRS DIFFER, and the reason they are here is a measured hole. The
# four-plane fill stores a whole 16-pixel group as TWO LONGWORDS — planes 0/1, then planes 2/3
# (`src/bios/conout_glyph.c`) — and the snapshot's own background is 0, which makes both of them
# zero: swapping the two stores survives this whole battery (measured 2026-09-19). A background
# whose low pair is not its high pair is what tells them apart, and 0 is deliberately not in the set.
UNEQUAL_PLANE_PAIRS = (0b0001, 0b0011, 0b1100, 0b1011)

# ...and a column in the middle of a cleared row, which is the run of WHOLE groups rather than
# either masked edge.
A_MIDDLE_COLUMN = 10


def cell_planes(info, column, row):
    """The distinct byte each plane of one character cell holds, as {plane: {bytes}}."""
    return {plane: {screen_byte_after(info, vt52.cell_address(column, row) + plane * 2
                                      + line * vt52.LINE_BYTES)
                    for line in range(vt52.CELL_HEIGHT)}
            for plane in range(vt52.PLANES)}


@pytest.mark.parametrize("background", UNEQUAL_PLANE_PAIRS)
def test_a_cleared_group_takes_each_plane_s_own_bit_of_the_background(background):
    """ONE BIT A PLANE, all ones where it is set — `lsr.w #1,d6 / subx.l d0,d0` builds exactly that
    word per plane before the fill, and the fill then stores them in the ROM's own order."""
    info = escape(0x45, {**vt52.staged(7, 5, cursor_depth=1), **vt52.colours(0, background)})
    assert cell_planes(info, A_MIDDLE_COLUMN, 5) == \
        {plane: {0xFF if background >> plane & 1 else 0x00} for plane in range(vt52.PLANES)}


def test_escape_e_homes_the_cursor_and_clears_the_whole_screen():
    info = escape(0x45, vt52.staged(7, 5, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 0
    assert cleared(info, 0, 0) and cleared(info, vt52.MAX_COLUMN, vt52.MAX_ROW)


@pytest.mark.parametrize("cursor_depth", (0, 1, 2, 5))
def test_escape_l_erases_the_line_and_then_places_the_cursor_with_whatever_d0_holds(cursor_depth):
    """THE QUIRK. `bsr <clear> / bra <place cursor>`, and the clear's own unlock left the LOCK DEPTH
    in D0 — which is the register `place cursor` reads a COLUMN out of. So the cursor lands in the
    column the lock was deep: 0 for a console a program is writing to, and the captured desktop's
    own 2 for one whose cursor has been hidden twice.

    Faithful, reachable from a `Bconout` any program can make, and a reconstruction that tidied it
    to "column 0" agrees with this one on exactly one row of this sweep."""
    info = escape(0x6C, vt52.staged(7, 5, cursor_depth=cursor_depth))
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == cursor_depth
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 5
    assert cleared(info, vt52.MAX_COLUMN, 5), "the line is erased whichever column the cursor lands in"


@pytest.mark.parametrize("planes, words_per_group, why", (
    (1, 1, "a monochrome screen: one word a 16-pixel group"),
    (2, 2, "four colours: two"),
    (3, 2, "...and THREE planes take the two-plane arm, because the index is `(planes >> 1) * 4`"),
    (4, 4, "sixteen colours: four, which is the captured machine's own"),
    (5, 4, "...and five planes take the four-plane arm for the same reason"),
))
def test_the_clear_fills_a_group_in_the_words_the_plane_count_names(planes, words_per_group, why):
    """`lsr.w #1,PLANES` chooses between THREE fill routines off a table at $fd15ba, and the words
    each writes per group is `1 << (planes >> 1)` — so an odd plane count is filled at the EVEN one
    below it while its glyphs are still drawn in all of them. The ROM's own inconsistency, and each
    routine here is faithful to its own.

    Six or more planes index past that three-entry table, which is the halt `src/bios/vt52.c`
    carries rather than a fourth arm.
    """
    pokes = {**vt52.staged(0, 0, cursor_depth=1), addrs.CON_PLANES: struct.pack(">H", planes)}
    info = escape(0x4B, pokes)                                  # ESC K across the whole top row
    first_line = sorted(at - vt52.SCREEN for at in screen_writes(info)
                        if vt52.SCREEN <= at < vt52.SCREEN + vt52.LINE_BYTES)
    groups = vt52.MAX_COLUMN // 2 + 1
    assert first_line == list(range(groups * words_per_group * 2)), why


@pytest.mark.parametrize("planes", (1, 2, 4))
def test_a_glyph_is_drawn_in_every_plane_there_is(planes):
    """`dbf` over `CON_PLANES`, which is the count and not the index into anything — so unlike the
    clear above, three planes really are three."""
    pokes = {**vt52.staged(0, 0, cursor_depth=1), addrs.CON_PLANES: struct.pack(">H", planes)}
    info = console(A_CHARACTER, pokes)
    expected = {vt52.cell_address(0, 0) + plane * 2 + line * vt52.LINE_BYTES
                for plane in range(planes) for line in range(vt52.CELL_HEIGHT)}
    assert set(screen_writes(info)) == expected


# ---- the scrolling escapes ----------------------------------------------------------------------------

def row_bytes_of(image, row, step=89):
    """A sample of one text row, thinned by a stride that is not a factor of anything here."""
    at = vt52.SCREEN + row * vt52.ROW_BYTES
    return {offset: image[at + offset] for offset in range(0, vt52.ROW_BYTES, step)}


def test_escape_i_at_the_top_scrolls_the_screen_down_and_blanks_the_first_row():
    before = row_bytes_of(BASE_IMAGE, 0)
    info = escape(0x49, vt52.staged(7, 0, cursor_depth=1))
    for offset, byte in before.items():
        assert case.written(info, vt52.SCREEN + vt52.ROW_BYTES + offset, 1) == byte
    assert cleared(info, 0, 0) and cleared(info, vt52.MAX_COLUMN, 0)


def test_escape_i_below_the_top_is_a_plain_cursor_up():
    info = escape(0x49, vt52.staged(7, 5, cursor_depth=1))
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 4
    assert screen_writes(info) == {}


def test_escape_l_inserts_a_blank_line_at_the_cursor_and_pushes_the_rest_down():
    before = row_bytes_of(BASE_IMAGE, 5)
    info = escape(0x4C, vt52.staged(7, 5, cursor_depth=1))
    for offset, byte in before.items():
        assert case.written(info, vt52.SCREEN + 6 * vt52.ROW_BYTES + offset, 1) == byte
    assert cleared(info, 0, 5) and cleared(info, vt52.MAX_COLUMN, 5)
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0
    assert cursor_after(info, addrs.CON_CURSOR_ROW) == 5


def test_escape_m_deletes_the_cursor_s_line_and_pulls_the_rest_up():
    before = row_bytes_of(BASE_IMAGE, 6)
    info = escape(0x4D, vt52.staged(7, 5, cursor_depth=1))
    for offset, byte in before.items():
        assert case.written(info, vt52.SCREEN + 5 * vt52.ROW_BYTES + offset, 1) == byte
    assert cleared(info, 0, vt52.MAX_ROW) and cleared(info, vt52.MAX_COLUMN, vt52.MAX_ROW)
    assert cursor_after(info, addrs.CON_CURSOR_COLUMN) == 0


@pytest.mark.parametrize("character, row", ((0x4C, vt52.MAX_ROW), (0x4D, vt52.MAX_ROW)))
def test_a_scroll_of_no_rows_still_clears_the_row_it_opened(character, row):
    """`sub.w d1,d7 / beq` skips the COPY and jumps straight to the clear vector — so `ESC L` and
    `ESC M` on the last row both blank it and move nothing."""
    info = escape(character, vt52.staged(7, row, cursor_depth=1))
    assert cleared(info, 0, row) and cleared(info, vt52.MAX_COLUMN, row)
    assert unchanged(info, 0, row - 1)


# ---- the cursor renderer -------------------------------------------------------------------------------

def test_a_cursor_move_inverts_the_cell_it_leaves_and_the_one_it_arrives_at():
    """THE RENDERER, which is what `CON_FLAG_DRAWN` gates: the lock inverts the old cell off the
    screen and the unlock inverts the new one on. Both are `not.b` down every plane of the cell, so
    each byte comes back as the complement of what the snapshot holds there."""
    info = escape(0x43, vt52.staged(7, 5))          # ESC C, cursor unlocked and on screen
    for at in vt52.cell_bytes(7, 5):
        assert case.written(info, at, 1) == BASE_IMAGE[at] ^ 0xFF, "the old cell"
    for at in vt52.cell_bytes(8, 5):
        assert case.written(info, at, 1) == BASE_IMAGE[at] ^ 0xFF, "the new cell"
    assert case.written(info, addrs.CON_STATE_FLAGS, 1) & vt52.DRAWN


def test_a_locked_cursor_is_neither_erased_nor_drawn():
    """The same move over the captured desktop's own depth of 2: the lock goes to 3 and back to 2,
    never reaching zero, and not one screen byte moves."""
    info = escape(0x43, vt52.staged(7, 5, cursor_depth=vt52.SNAPSHOT_CURSOR_DEPTH))
    assert screen_writes(info) == {}
    assert case.written(info, addrs.CON_CURSOR_DISABLE, 2) == vt52.SNAPSHOT_CURSOR_DEPTH


def test_a_nonzero_spare_byte_suppresses_the_redraw_and_becomes_the_blink_timer():
    """`move.b CON_STATE_SPARE,d6 / bne` jumps PAST the draw and straight to the timer store, so the
    byte `Cursconf(6)` writes both stops the console drawing its cursor and decides what the blink
    timer is reloaded with. Not guessable from the arm; only from the branch."""
    spare = 0x5A
    info = escape(0x43, {**vt52.staged(7, 5), addrs.CON_STATE_SPARE: bytes([spare])})
    assert case.written(info, addrs.CON_BLINK_TIMER, 1) == spare
    for at in vt52.cell_bytes(8, 5):
        assert at not in info["writes"], "the cursor was drawn over a nonzero spare byte"


@pytest.mark.parametrize("cursor_depth", (0, 1, 2, 7))
def test_escape_f_locks_the_cursor_one_level_deeper(cursor_depth):
    info = escape(0x66, vt52.staged(7, 5, cursor_depth=cursor_depth))
    assert case.written(info, addrs.CON_CURSOR_DISABLE, 2) == cursor_depth + 1
    assert (screen_writes(info) != {}) is (cursor_depth == 0), \
        "the cell comes off the screen only if it was on it"


@pytest.mark.parametrize("cursor_depth", (1, 2, 7))
def test_escape_e_forces_the_cursor_back_on_screen_from_any_depth(cursor_depth):
    """`move.w #1,CON_CURSOR_DISABLE` — the depth is not decremented, it is REPLACED, so one `ESC e`
    undoes any number of locks."""
    info = escape(0x65, vt52.staged(7, 5, cursor_depth=cursor_depth))
    assert case.written(info, addrs.CON_CURSOR_DISABLE, 2) == 0
    for at in vt52.cell_bytes(7, 5):
        assert case.written(info, at, 1) == BASE_IMAGE[at] ^ 0xFF


def test_escape_e_on_a_cursor_that_is_not_locked_does_nothing():
    info = escape(0x65, vt52.staged(7, 5, cursor_depth=0))
    assert screen_writes(info) == {}
    assert addrs.CON_CURSOR_DISABLE not in info["writes"]


# ---- what ESC j saved and ESC k puts back ------------------------------------------------------------

def test_escape_j_saves_the_column_and_row_as_one_longword():
    info = escape(0x6A, vt52.staged(7, 5))
    assert case.written_long(info, addrs.CON_SAVED_POSITION) == (7 << 16) | 5
    assert case.written(info, addrs.CON_STATE_FLAGS, 1) & vt52.POSITION_SAVED


def test_escape_k_goes_back_to_the_saved_position_and_forgets_it():
    pokes = {**vt52.staged(7, 5, cursor_depth=1, extra_flags=vt52.POSITION_SAVED),
             addrs.CON_SAVED_POSITION: struct.pack(">HH", 3, 9)}
    info = escape(0x6B, pokes)
    assert (cursor_after(info, addrs.CON_CURSOR_COLUMN),
            cursor_after(info, addrs.CON_CURSOR_ROW)) == (3, 9)
    assert not case.written(info, addrs.CON_STATE_FLAGS, 1) & vt52.POSITION_SAVED


def test_escape_k_with_nothing_saved_homes_the_cursor():
    """`bclr #5,(a4) / beq` — the bit is cleared either way, and its OLD value decides between the
    saved position and `ESC H`."""
    pokes = {**vt52.staged(7, 5, cursor_depth=1, without_flags=vt52.POSITION_SAVED),
             addrs.CON_SAVED_POSITION: struct.pack(">HH", 3, 9)}
    info = escape(0x6B, pokes)
    assert (cursor_after(info, addrs.CON_CURSOR_COLUMN),
            cursor_after(info, addrs.CON_CURSOR_ROW)) == (0, 0)


# ---- the RAW console, and Cursconf's two drawing arms --------------------------------------------------

@pytest.mark.parametrize("character", (addrs.CON_BEL, addrs.CON_CR, ESC, 0x00, 0x1F))
def test_the_raw_console_draws_a_control_code_where_the_vt52_obeys_it(character):
    """$fc42e6 is the glyph renderer with no state machine in front of it, which is the whole of the
    difference between devices 5 and 2."""
    drawn = raw(character, vt52.staged(7, 5, cursor_depth=1))
    assert set(screen_writes(drawn)) == set(vt52.cell_bytes(7, 5))
    assert addrs.CON_STATE_VECTOR not in drawn["writes"]
    assert screen_writes(console(character, vt52.staged(7, 5, cursor_depth=1))) == {}


@pytest.mark.parametrize("character", PRINTABLE)
def test_a_printable_character_is_the_same_through_both_devices(character):
    """...and for everything from a space up the two are the same routine, reached two different
    ways — so a reconstruction that had given the raw console its own renderer reds here."""
    staged = vt52.staged(7, 5, cursor_depth=1)
    assert screen_writes(raw(character, staged)) == screen_writes(console(character, staged))


@pytest.mark.parametrize("function, cursor_depth, draws, why", (
    (addrs.CURSCONF_HIDE, 0, True, "hide: the cell comes off the screen"),
    (addrs.CURSCONF_HIDE, 1, False, "...and a cursor already locked is only locked deeper"),
    (addrs.CURSCONF_SHOW, 1, True, "show: the cell goes back on, whatever the depth was"),
    (addrs.CURSCONF_SHOW, 0, False, "...and one that was never locked is already there"),
))
def test_cursconf_s_two_drawing_arms_are_the_console_s_own_renderer(function, cursor_depth, draws,
                                                                    why):
    """THE TWO ARMS `src/xbios/cursconf.c` HALTED ON. Its jump table sends them straight into the
    console driver at $fc45d8 and $fc45be, so they became a real differential the moment
    `Bconout(CON:)` did. Neither writes D0 — the arm's own displacement out of the dispatch's table
    is what comes back, exactly as for `blink` and `steady` beside them."""
    info = cursconf.run(function, pokes=vt52.staged(7, 5, cursor_depth=cursor_depth))
    inverted = all(screen_byte_after(info, at) == BASE_IMAGE[at] ^ 0xFF
                   for at in vt52.cell_bytes(7, 5))
    assert inverted is draws, why
    assert cursconf.result(info) == cursconf.displacement(function)
