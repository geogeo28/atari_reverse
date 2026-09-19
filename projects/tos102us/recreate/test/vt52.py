"""Staging the BIOS console: the block of RAM its whole world is, and how a case says what is in it.

`Bconout(CON:)` reads the screen base out of `_v_bas_ad` and everything else — the cell geometry, the
cursor, the two colours, the font and the four screen routines — out of one block at $2994 and the
words below it (`src/bios/vt52.c`). So a case that wants the cursor in a particular cell, the wrap
on, or the cursor unlocked is a set of POKES into that block, and each is a claim about the machine
rather than a convenience.

THE GEOMETRY IS READ OUT OF THE SNAPSHOT rather than written down. The boot derived it from the
resolution the desktop came up in — 40 columns of 25 rows, four planes, eight scan lines a cell — and
a case that spelt those numbers would stop describing the machine the moment a capture came from
another one. The cases below that depend on a PARTICULAR shape (a glyph crossing a 16-pixel group,
the last row) derive it from these.
"""
import struct

import isr
from harness import BASE_IMAGE, addrs

# "What the CAPTURED machine holds at X", spelt once for the whole project in `test/isr.py`.
_word = isr.word_in_snapshot
_long = isr.long_in_snapshot


MAX_COLUMN = _word(addrs.CON_MAX_COLUMN)
MAX_ROW = _word(addrs.CON_MAX_ROW)
ROW_BYTES = _word(addrs.CON_ROW_BYTES)
PLANES = _word(addrs.CON_PLANES)
LINE_BYTES = _word(addrs.CON_LINE_BYTES)
CELL_HEIGHT = _word(addrs.CON_CELL_HEIGHT)
SCREEN = _long(addrs.SYSVAR_V_BAS_AD)
CURSOR_OFFSET = _word(addrs.CON_CURSOR_OFFSET)
FONT_FIRST = _word(addrs.CON_FONT_FIRST)
FONT_LAST = _word(addrs.CON_FONT_LAST)
FONT_FORM = _long(addrs.CON_FONT_FORM)
FONT_FORM_BYTES = _word(addrs.CON_FONT_FORM_BYTES)
FONT_OFFSETS = _long(addrs.CON_FONT_OFFSETS)
SNAPSHOT_FLAGS = BASE_IMAGE[addrs.CON_STATE_FLAGS]
SNAPSHOT_CURSOR_DEPTH = _word(addrs.CON_CURSOR_DISABLE)

# The flag byte's five bits, by the names the ROM's own `bset`/`btst` immediates carry.
BLINKS = 1 << addrs.CON_FLAG_BLINKS
DRAWN = 1 << addrs.CON_FLAG_DRAWN
WRAP = 1 << addrs.CON_FLAG_WRAP
REVERSE = 1 << addrs.CON_FLAG_REVERSE
POSITION_SAVED = 1 << addrs.CON_FLAG_POSITION_SAVED

# A 16-pixel screen group is `PLANES` words side by side, so two character cells share one group and
# the second of them is the byte after the first.
GROUP_BYTES = PLANES * 2


def cell_address(column, row):
    """$fc49c4's arithmetic, without its clamp: `row * ROW_BYTES + (column & ~1) * PLANES + (column
    & 1)`, off the screen base plus the block's own cursor offset."""
    return SCREEN + CURSOR_OFFSET + row * ROW_BYTES + (column & ~1) * PLANES + (column & 1)


def glyph_column(character):
    """The `CELL_HEIGHT` font bytes a character's column is, straight out of the ROM's font.

    Derived from the font header the boot copied into the block — the offset table is in BITS and the
    form's rows are `FONT_FORM_BYTES` apart — so a case can assert the PIXELS a glyph puts on screen
    rather than only that both cores agree about them.
    """
    bit = _word(FONT_OFFSETS + character * 2)
    at = FONT_FORM + (bit >> 3)
    return [BASE_IMAGE[at + line * FONT_FORM_BYTES] for line in range(CELL_HEIGHT)]


def cell_bytes(column, row):
    """Every screen address one character cell occupies: `CELL_HEIGHT` scan lines of `PLANES`
    planes, the planes two bytes apart and the lines `LINE_BYTES` apart."""
    base = cell_address(column, row)
    return [base + plane * 2 + line * LINE_BYTES
            for plane in range(PLANES) for line in range(CELL_HEIGHT)]


def at(column, row):
    """Pokes putting the cursor on (column, row) — all THREE fields, because the driver reads the
    stored ADDRESS rather than recomputing it, and a case that moved two of the three would be
    describing a console no boot ever left behind."""
    return {addrs.CON_CURSOR_COLUMN: struct.pack(">HH", column & 0xFFFF, row & 0xFFFF),
            addrs.CON_CURSOR_ADDRESS: struct.pack(">I", cell_address(column, row) & 0xFFFFFFFF)}


def flags(value):
    return {addrs.CON_STATE_FLAGS: bytes([value & 0xFF])}


def depth(value):
    """The cursor's hide-DEPTH counter. The captured desktop left it at 2, which is a console whose
    cursor is off screen and stays there; a program calling `Bconout` finds 0."""
    return {addrs.CON_CURSOR_DISABLE: struct.pack(">H", value & 0xFFFF)}


def state(vector):
    return {addrs.CON_STATE_VECTOR: struct.pack(">I", vector)}


def colours(foreground, background):
    """One bit a plane, LSB first: $ffff over 0 is white on black in any plane count."""
    return {addrs.CON_COLOUR_BACKGROUND: struct.pack(">HH", background & 0xFFFF,
                                                     foreground & 0xFFFF)}


# A byte no glyph column and no cleared cell can be: `case.run`'s own POISON pass cannot be used on
# this driver (see `test_bios_vt52.py`), so a case that wants to know a screen byte was really
# WRITTEN rather than already right stages this under it first. A candidate that skipped the store
# leaves the canary where the oracle left a pixel, and the plain byte diff says so.
CANARY = 0xA5


def canary(column, row):
    """One character cell filled with `CANARY` — attribution for the cases about pixels."""
    return {byte: bytes([CANARY]) for byte in cell_bytes(column, row)}


def staged(column=0, row=0, *, cursor_depth=0, extra_flags=0, without_flags=0, **pokes):
    """The console as a PROGRAM would find it, plus whatever the case wants changed.

    The default is the state a `Bconout` from an application runs in: the cursor unlocked and on
    screen (depth 0 and the drawn bit set, which are the same claim said twice — the block is
    inconsistent otherwise), the snapshot's own colours and its own wrap setting. A cursor depth
    above zero clears the drawn bit with it, for the same reason.
    """
    shown = DRAWN if cursor_depth == 0 else 0
    value = (SNAPSHOT_FLAGS & ~DRAWN | shown | extra_flags) & ~without_flags
    return {**at(column, row), **flags(value), **depth(cursor_depth), **pokes}
