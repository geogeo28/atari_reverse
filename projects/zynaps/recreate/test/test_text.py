"""Differential tests for the character blitter and its two drivers (src/text.c).

THE FONT IS BSS AND SO IS NOT IN THE .PRG. `_start` loads extchars.dat over it, so every case here
stages the real 1920 bytes of that file at `A_FONT_GLYPHS` from ../bin/disk — drawing against the
zeroed bss would make every mask 0x00 and every plane byte 0x00, which is a cleared cell for EVERY
character and would hide any glyph-indexing mistake at all.
"""
import ctypes
import random
from pathlib import Path

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_DRAW_CHAR = 0x13710
ENTRY_DRAW_BCD_NUMBER = 0x136f6
ENTRY_DRAW_TEXT_RECORD = 0x12e40

A_FONT_GLYPHS = 0x6be6e          # mirror of include/text.h
A_CHAR_TO_GLYPH_TABLE = 0x198d6
SCREEN_ROW_BYTES = 0xa0
GLYPH_BYTES = 0x28
GLYPH_ROWS = 8
CHAR_SPACE = 0x20
CHAR_CLEAR_CELL = 1
CHAR_FILL_CELL = 2
CHAR_FIRST_LETTER = 0x41
LETTER_GLYPH_BIAS = 0x37
CHAR_MAP_FIRST = 0x20
BCD_DIGITS = 8

FONT_FILE = Path(__file__).resolve().parents[2] / "bin" / "disk" / "EXTCHARS.DAT"
FONT_BYTES = FONT_FILE.read_bytes()
FONT_GLYPHS = len(FONT_BYTES) // GLYPH_BYTES

# The screen the cases draw into: a whole 320x200 four-plane frame, so a record at the title
# screen's own row 168 still lands inside the seeded band. It is `abi.SCRATCH` rather than the
# game's own buffer because a case drives A0 directly and the routine cares about nothing else.
SCREEN = abi.SCRATCH
SCREEN_BYTES = SCREEN_ROW_BYTES * 200

harness._lib.g_draw_char.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_char.restype = None
harness._lib.g_draw_bcd_number.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_bcd_number.restype = None
harness._lib.g_draw_text_record.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_text_record.restype = None

FUZZ_CHUNKS = 4


def staged_screen(seed):
    """A noisy frame plus the real font.

    NOISE, NOT ZEROES, and that is what makes the AND mask visible at all: over a zeroed screen the
    mask changes nothing and a candidate that dropped it entirely would still match.

    Public because `test_asm_text.py` drives the ASM TWINS over these same cases.
    """
    return {SCREEN: random.Random(seed).randbytes(SCREEN_BYTES), A_FONT_GLYPHS: FONT_BYTES}


def _char_case(character, column, seed=0, extra_pokes=None, poison=False):
    pokes = staged_screen(seed)
    pokes.update(extra_pokes or {})
    regs = {"a0": SCREEN, "d0": character, "d1": column, "_pokes": pokes}
    diffs, _ = differential(
        ENTRY_DRAW_CHAR, regs,
        lambda lib, buf: lib.g_draw_char(buf, SCREEN, column, character), poison=poison)
    assert not diffs, f"char={character:#x} column={column:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_every_character_code(chunk):
    """All 256 byte values D0 can hold, sharded four ways.

    Exhaustive because the routine forks five ways on the character (space, clear, fill, letter,
    table) and the two boundaries between the last three are single values — 0x40 goes through the
    table and 0x41 does not. Above 0x7f the arithmetic arm indexes PAST the 48-glyph font into the
    bss behind it, and below 0x20 the table arm indexes before the table; both stay inside the image
    and both are what the instructions do, so they are driven rather than avoided.
    """
    for character in range(chunk, 0x100, FUZZ_CHUNKS):
        _char_case(character, 4)


@pytest.mark.parametrize("character", (CHAR_SPACE, CHAR_CLEAR_CELL, CHAR_FILL_CELL,
                                       CHAR_FIRST_LETTER - 1, CHAR_FIRST_LETTER, 0x30, 0x39, 0x5a))
def test_every_column(character):
    """Columns 0..39 and one past, for each of the routine's five arms.

    The odd/even split is the whole point: a pair of columns shares one 16-pixel group, so column
    2n and 2n+1 differ by ONE byte while 2n and 2n+2 differ by eight. A cell address built as
    `column * 4` would agree with the original on every even column and be wrong on every odd one.
    """
    for column in range(41):
        _char_case(character, column, seed=column)


def test_space_draws_nothing():
    """The space is a no-op, not a cleared cell — an empty diff over a NOISY screen is the claim,
    and the noise is what makes it one."""
    _char_case(CHAR_SPACE, 7, seed=99)


def test_character_high_bits():
    """The three special characters are compared as BYTES and the letter threshold as a WORD, so
    junk above the low byte cannot make a space stop being a space, and junk above the low word
    cannot reach the comparison at all."""
    rng = random.Random(ENTRY_DRAW_CHAR)
    for character in (CHAR_SPACE, CHAR_CLEAR_CELL, CHAR_FILL_CELL, 0x41, 0x30):
        _char_case(hi_garbage(rng, character), 5)
        _char_case(hi_garbage(rng, character | 0xff00), 5)


def test_column_high_bits():
    """Every step of the cell address is a word operation, so D1's high half must not reach it."""
    rng = random.Random(ENTRY_DRAW_CHAR + 1)
    for column in (0, 1, 12, 39):
        _char_case(0x41, hi_garbage(rng, column))


@pytest.mark.parametrize("glyph", (0, 1, FONT_GLYPHS - 1))
def test_every_shipped_glyph_is_reachable(glyph):
    """Walk the real table and draw the character that selects each end of the font.

    Pins `A_CHAR_TO_GLYPH_TABLE` and the 0x28 stride together against real data rather than against
    a synthetic index: the character is found by searching the shipped table for the glyph, so a
    wrong table address makes the search itself fail.
    """
    mapped = CHAR_FIRST_LETTER - CHAR_MAP_FIRST      # the characters the table describes
    table = bytes(harness.BASE_IMAGE[A_CHAR_TO_GLYPH_TABLE:A_CHAR_TO_GLYPH_TABLE + mapped])
    characters = [CHAR_MAP_FIRST + i for i, value in enumerate(table) if value == glyph]
    characters += [glyph + LETTER_GLYPH_BIAS] if glyph + LETTER_GLYPH_BIAS >= CHAR_FIRST_LETTER \
        else []
    assert characters, f"no shipped character selects glyph {glyph}"
    for character in characters:
        _char_case(character, 3, seed=glyph)


@pytest.mark.parametrize("character", (0x41, 0x30, CHAR_CLEAR_CELL, CHAR_FILL_CELL))
def test_char_attribution(character):
    """Poison every byte the blit writes: a candidate drawing fewer rows or fewer planes stays
    canary on the ones it skipped."""
    _char_case(character, 6, seed=7, poison=True)


# =================================================================================================
# draw_bcd_number @ 0x136f6
# =================================================================================================

def _bcd_case(digits, column, seed=0, poison=False):
    pokes = staged_screen(seed)
    regs = {"a0": SCREEN, "d1": column, "d6": digits, "_pokes": pokes}
    diffs, _ = differential(
        ENTRY_DRAW_BCD_NUMBER, regs,
        lambda lib, buf: lib.g_draw_bcd_number(buf, SCREEN, column, digits), poison=poison)
    assert not diffs, f"digits={digits:#010x} column={column:#x}\n{report(diffs)}"


# The score is a 4-byte BCD value (names.txt, player_score_bcd), so a real one has only 0..9 in each
# nibble; the two with 0xa..0xf are this battery's, and they draw ':' through '?' because the digit
# is turned into a character by adding 0x30 with no range check at all.
BCD_VALUES = (0x00000000, 0x00000001, 0x12345678, 0x99999999, 0x0000abcd, 0xffffffff)


@pytest.mark.parametrize("digits", BCD_VALUES)
def test_bcd_number(digits):
    """Eight nibbles right to left. The count is fixed, so a zero score draws eight zeroes."""
    _bcd_case(digits, 20, seed=digits & 0xff)


def test_bcd_number_walks_left():
    """The column steps BACKWARDS, one per digit — drawn from a column under 8 the run walks off
    the left of the row and into the previous one, which is what a forward-stepping candidate would
    not do. The rightmost column here is chosen so the eighth digit lands at column 0."""
    _bcd_case(0x12345678, BCD_DIGITS - 1)


def test_bcd_number_high_bits():
    """D1 is a word column and D6 the whole longword: junk above D1's low word must not reach the
    cell address, while every bit of D6 is real data."""
    rng = random.Random(ENTRY_DRAW_BCD_NUMBER)
    _bcd_case(0x13570246, hi_garbage(rng, 30))


def test_bcd_attribution():
    """Poison all eight cells: a candidate drawing seven digits stays canary on the eighth."""
    _bcd_case(0x24681357, 15, seed=3, poison=True)


# =================================================================================================
# draw_text_record @ 0x12e40
# =================================================================================================

_RECORD_STORES = ("a6",)

# Every {column, row, text, 0} record the game ships, from ../names.txt. THE FIRST TWO ADDRESSES
# ARE names.txt's PLUS ONE: `var 0x19932 msg_player` and `var 0x19a0a msg_please_enter_your_name`
# both point at the previous record's terminator, while the code loads 0x19933 (`lea` @ 0x1346c)
# and 0x19a0b (`lea` @ 0x12fdc). The code is the evidence and these follow it; see
# ../out/names_sound.txt for the correction the name map needs.
SHIPPED_RECORDS = {
    "msg_prepare_for_combat": 0x1991e,
    "msg_player": 0x19933,
    "msg_converted_by_microwish": 0x1993d,
    "msg_coding_howie": 0x19956,
    "msg_graphics_pete_lyon": 0x19967,
    "msg_music_and_sound_fx": 0x1997e,
    "msg_menu_one_or_two_players": 0x199a3,
    "msg_role_of_honour": 0x199c8,
    "msg_game_over_player": 0x199d9,
    "msg_new_high_score": 0x199ee,
    "msg_please_enter_your_name": 0x19a0b,
    "msg_you_are_not_rated": 0x19a24,
}


def _record_case(record, seed=0, extra_pokes=None, poison=False):
    pokes = staged_screen(seed)
    pokes[abi.RESULT] = bytes(range(0x71, 0x75))
    pokes.update(abi.register_dump_pokes(ENTRY_DRAW_TEXT_RECORD, _RECORD_STORES))
    pokes.update(extra_pokes or {})
    regs = {"a0": SCREEN, "a6": record, "_pokes": pokes}
    diffs, _ = differential(
        abi.STUB, regs,
        lambda lib, buf: lib.g_draw_text_record(buf, SCREEN, record, abi.RESULT), poison=poison)
    assert not diffs, f"record={record:#x}\n{report(diffs)}"


@pytest.mark.parametrize("name,record", sorted(SHIPPED_RECORDS.items()))
def test_shipped_record(name, record):
    """Every string the game ships, drawn at its own column and row from the image's own bytes.

    Real data rather than a synthetic record: the column byte is SIGN-extended and the row byte is
    not, and these rows run to 168 — a signed reading of the row would put the credit lines above
    the screen instead of below the middle.
    """
    _record_case(record, seed=record & 0xff)


def _synthetic_record(column, row, text):
    return bytes([column & 0xff, row & 0xff]) + text + b"\x00"


@pytest.mark.parametrize("column,row,text", (
    (0, 0, b"A"),                       # the shortest record that draws anything
    (0, 0, b""),                        # ...and the shortest that draws nothing
    (39, 0, b"Z"),                      # the last column of the row
    (0xff, 8, b"AB"),                   # column -1: SIGN-extended, so one cell left of the base
    (0x80, 16, b"AB"),                  # ...and the most negative column a byte can hold
    (4, 0xff, b"AB"),                   # row 255: ZERO-extended, 40800 bytes down
    (2, 0, bytes(range(0x21, 0x41))),   # a run through the table arm and the space
))
def test_synthetic_record(column, row, text):
    """The record's own edges: an empty string, both ends of the column byte's SIGN, and a row byte
    at 0xff, which a signed reading would put 22 rows ABOVE the base instead of 255 below it."""
    record = abi.SCRATCH + SCREEN_BYTES
    _record_case(record, seed=column + row, extra_pokes={record: _synthetic_record(column, row, text)})


def test_record_attribution():
    """Poison every cell one record writes, plus the cursor the stub dumps."""
    _record_case(SHIPPED_RECORDS["msg_role_of_honour"], seed=11, poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_FONT_GLYPHS", "include/text.h", "A_font_glyphs"),
    ("A_CHAR_TO_GLYPH_TABLE", "include/text.h", "A_char_to_glyph_table"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("GLYPH_BYTES", "include/text.h", "GLYPH_BYTES"),
    ("GLYPH_ROWS", "include/text.h", "GLYPH_ROWS"),
    ("CHAR_SPACE", "include/text.h", "CHAR_SPACE"),
    ("CHAR_CLEAR_CELL", "include/text.h", "CHAR_CLEAR_CELL"),
    ("CHAR_FILL_CELL", "include/text.h", "CHAR_FILL_CELL"),
    ("CHAR_FIRST_LETTER", "include/text.h", "CHAR_FIRST_LETTER"),
    ("LETTER_GLYPH_BIAS", "include/text.h", "LETTER_GLYPH_BIAS"),
    ("CHAR_MAP_FIRST", "include/text.h", "CHAR_MAP_FIRST"),
    ("BCD_DIGITS", "include/text.h", "BCD_DIGITS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_DRAW_CHAR": "2f08b03c002067000082",
    "ENTRY_DRAW_BCD_NUMBER": "7e071006c07c000fd07c",
    "ENTRY_DRAW_TEXT_RECORD": "2f08121e4881141ec47c",
}
