"""The ASM-TWIN differential for the score panel and the character blitter it ends in: each twin in
../src/asm/text.S must leave the image byte-for-byte where its C core leaves it.

    original  ==(test_hud.py / test_text.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE THOSE TWO BATTERIES', IMPORTED RATHER THAN RESTATED — `test_hud.py::score_panel_pokes`
and `test_text.py::staged_screen`, which already stage both framebuffers with the real panel strip
and a noisy frame with the disk's own font. A second, parallel case table here would be a second
thing to keep true, and the twin has to match the C on the C's OWN cases.

THE THREE TWINS ARE ONE PIECE OF CODE (src/asm/text.S says why: 0x136c8 falls through into 0x136f6,
which `bsr`s 0x13710), so a panel case exercises all three at once and the two smaller entry points
are driven separately for their own C-ABI prologues.

WHAT A DIVERGENCE MEANS is `test_asm_scroll.py`'s paragraph word for word. Requires the assembled
twins (`make asm`, which `make test` runs first).
"""
import pytest

import asm_twins
import harness
import test_hud as hud
import test_text as text
from asm_twins import REJECTS

PANEL_TWIN = "draw_score_panel_asm"
BCD_TWIN = "draw_bcd_number_asm"
CHAR_TWIN = "draw_char_asm"


# ============================================================== draw_score_panel @ 0x136c8

def _panel_case(buffer, score=None, seed=0):
    image = harness.make_image(hud.score_panel_pokes(buffer, score, seed))
    return asm_twins.matches_the_c(
        image, PANEL_TWIN, (buffer,),
        lambda lib, buf: lib.g_draw_score_panel(buf, buffer))


@pytest.mark.parametrize("buffer", hud.SCORE_PANEL_BUFFERS)
def test_panel_twin_every_buffer(buffer):
    """The twin's one argument is the whole of its destination — both framebuffers and one that is
    neither, which is what says A6 comes from the caller rather than from `screen_back`."""
    _panel_case(buffer, seed=buffer & 0xff)


@pytest.mark.parametrize("score", (0x00000000, 0x00000001, 0x12345678, 0x99999999, 0xffffffff))
def test_panel_twin_draws_the_score(score):
    """The strip and then the eight digits, which the twin reaches by FALLING THROUGH into
    draw_bcd_number and then by eight plain `bsr`s — so all three bodies are in this diff."""
    _panel_case(hud.A_SCREEN_BACK_BUFFER, score=score, seed=score & 0xff)


# =============================================================== draw_bcd_number @ 0x136f6

def _bcd_case(digits, column, seed=0):
    image = harness.make_image(text.staged_screen(seed))
    return asm_twins.matches_the_c(
        image, BCD_TWIN, (text.SCREEN, column, digits),
        lambda lib, buf: lib.g_draw_bcd_number(buf, text.SCREEN, column, digits))


@pytest.mark.parametrize("digits", text.BCD_VALUES)
def test_bcd_twin_every_value(digits):
    """`test_text.py`'s own values, including the two with 0xa..0xf nibbles that draw ':' through
    '?' — the digit becomes a character by adding 0x30 with no range check at all."""
    _bcd_case(digits, 20, seed=digits & 0xff)


def test_bcd_twin_walks_left():
    """The column steps BACKWARDS: eight digits from column 7 land on columns 7 down to 0.

    It does NOT reach a negative column, and no case in this file does — `adda.w` sign-extends, so
    a negative d1 would step the cursor back into the previous row, and the LONG form of that add
    would land 64 KB away. Both call sites load 0x26 and HIGHSCORE_DIGITS_COLUMN and no shipped
    record byte is >= 0x80, so the arm is unreachable from the game's own data rather than
    untested-by-oversight; STATUS.md records it that way."""
    _bcd_case(0x12345678, text.BCD_DIGITS - 1)


# ==================================================================== draw_char @ 0x13710

def _char_case(character, column, seed=0, must_write=True):
    image = harness.make_image(text.staged_screen(seed))
    return asm_twins.matches_the_c(
        image, CHAR_TWIN, (text.SCREEN, column, character),
        lambda lib, buf: lib.g_draw_char(buf, text.SCREEN, column, character),
        must_write=must_write)


def _char_control(character):
    """Which pole a character's case is held to: the SPACE arm alone must write nothing, and the
    other 255 byte values all reach one of the four arms that do. The comparison is on the LOW
    BYTE because that is what the routine's three `cmp.b`s test."""
    return REJECTS if (character & 0xff) == text.CHAR_SPACE else True


CHAR_TWIN_FUZZ_CHUNKS = text.FUZZ_CHUNKS


@pytest.mark.parametrize("chunk", range(CHAR_TWIN_FUZZ_CHUNKS))
def test_char_twin_every_character_code(chunk):
    """All 256 byte values, sharded — the routine forks FIVE ways on the character and two of the
    boundaries are single values, so nothing short of exhaustive covers the dispatch the twin
    transcribes. Only the SPACE arm writes nothing, and it says so — the other 255 keep the
    positive control rather than switching it off for the whole parametrization."""
    for character in range(chunk, 0x100, CHAR_TWIN_FUZZ_CHUNKS):
        _char_case(character, 4, must_write=_char_control(character))


@pytest.mark.parametrize("character", (text.CHAR_SPACE, text.CHAR_CLEAR_CELL, text.CHAR_FILL_CELL,
                                       text.CHAR_FIRST_LETTER - 1, text.CHAR_FIRST_LETTER,
                                       0x30, 0x39, 0x5a))
def test_char_twin_every_column(character):
    """Columns 0..40 for each of the five arms. The odd/even split is the point: a cell address
    built as `column * 4` would agree on every even column and be wrong on every odd one."""
    for column in range(41):
        _char_case(character, column, seed=column, must_write=_char_control(character))


def test_char_twin_space_writes_nothing():
    """The space arm, asserted positively — it is the twin's early `beq.w`, and a differential in
    which neither side wrote would otherwise pass on any transcription at all."""
    _char_case(text.CHAR_SPACE, 4, seed=0x13712, must_write=REJECTS)


# ============================== the transcription pin: which spans ARE the original's own bytes

# The three ROW LOOPS, and the address in the original each starts at. Only the loops, for the gas
# encoding reason src/asm/text.S and test_asm_sprite.py both set out: the dispatch prologues are
# immediate compares, which gas spells CMPI/ANDI/ADDI where the original's assembler used the
# immediate-EA forms. The loops carry no immediate-to-Dn operation and are where a panel's cycles
# are — eight `movem` rows for the strip and eight four-plane rows for each of eight digits.
TRANSCRIBED_SPANS = {
    "draw_score_panel_strip": 0x136d6,   # `movem.l (a4)+,#$07fe` — 40 bytes in ten registers
    "draw_char_glyph": 0x1376c,          # the masked glyph rows, through the `rts` at 0x1379c
    "draw_char_fill": 0x137b0,           # characters 1 and 2, through the `rts` at 0x137c8
}


@pytest.mark.parametrize("name", sorted(TRANSCRIBED_SPANS))
def test_the_twins_transcribe_the_original(name):
    """Each bracketed body against the .PRG — see `asm_twins.assert_transcribes_the_original`."""
    asm_twins.assert_transcribes_the_original(name, TRANSCRIBED_SPANS[name])


# ======================================= what a twin COSTS, against what the original costs

# THE BAR IS PER ENTRY POINT, AND IT IS SET FROM THE MEASUREMENT. Every reading below is the same
# FIXED C-ABI cost — a `movem.l` pair of the callee-saved registers that body clobbers, the argument
# binding, the image-base adds and the `bsr` bracket — over a different call length:
#
#   case                       original    twin   excess   measured   ceiling
#   draw_score_panel             16,008  16,344     +336    1.0210     1.0215
#   draw_bcd_number              14,352  14,616     +264    1.0184     1.019
#   draw_char, a letter           1,736   1,934     +198    1.1141     1.116
#
# THE PANEL'S 336 IS ITS OWN 208 PLUS EIGHT LOTS OF 16: its prologue and epilogue and the two
# absolutes it forms, and then TWO substituted `lea`s inside each of the eight draw_char calls it
# makes — a BCD digit is below CHAR_FIRST_LETTER, so it takes the glyph-table arm and then falls
# into the font arm, paying both (measured: a letter costs +198 and a digit +206). Those eight
# calls pay NO prologue — they go through the original's own `bsr`, 18 cycles — which is what the C
# could not do and most of what this twin is worth. src/asm/text.S says why the two are left where
# the original forms them rather than hoisted.
#
# DRAW_CHAR'S OWN RATIO IS THE LARGE ONE AND IT IS THE ONE THAT MATTERS LEAST, for the same reason:
# 1,400 of the 1,425 draw_char calls in a profiled window come from the panel. The 198 cycles here
# are what a call from C costs, which the panel does not make; it is measured rather than waved away
# so that a regression in this prologue still has a surface.
#
# The margins are 3-9 cycles, which is what makes these bars a gate: ONE more register in any of the
# three `movem` pairs costs 16 cycles and reddens them. DO NOT RAISE A CEILING to make a run pass.
PANEL_COST_CEILING = 1.0215
BCD_COST_CEILING = 1.019
CHAR_COST_CEILING = 1.116

COST_SCORE = 0x12345678     # eight non-zero digits: every one takes the glyph arm and its row loop
COST_COLUMN = 20
COST_CHARACTER = 0x41       # 'A' — the letter arm, which is what the font is asked for


def test_the_panel_twin_costs_what_the_original_costs():
    buffer = hud.A_SCREEN_BACK_BUFFER
    image = harness.make_image(hud.score_panel_pokes(buffer, COST_SCORE, seed=0xb400))
    original, twin = asm_twins.cost_case(
        image, hud.ENTRY_DRAW_SCORE_PANEL, {"a6": buffer},
        PANEL_TWIN, (buffer,),
        lambda lib, buf: lib.g_draw_score_panel(buf, buffer))
    asm_twins.assert_within_the_bar(PANEL_TWIN, original, twin, PANEL_COST_CEILING)


def test_the_bcd_twin_costs_what_the_original_costs():
    image = harness.make_image(text.staged_screen(0xb401))
    original, twin = asm_twins.cost_case(
        image, text.ENTRY_DRAW_BCD_NUMBER,
        {"a0": text.SCREEN, "d1": COST_COLUMN, "d6": COST_SCORE},
        BCD_TWIN, (text.SCREEN, COST_COLUMN, COST_SCORE),
        lambda lib, buf: lib.g_draw_bcd_number(buf, text.SCREEN, COST_COLUMN, COST_SCORE))
    asm_twins.assert_within_the_bar(BCD_TWIN, original, twin, BCD_COST_CEILING)


def test_the_char_twin_costs_what_the_original_costs():
    image = harness.make_image(text.staged_screen(0xb402))
    original, twin = asm_twins.cost_case(
        image, text.ENTRY_DRAW_CHAR,
        {"a0": text.SCREEN, "d0": COST_CHARACTER, "d1": COST_COLUMN},
        CHAR_TWIN, (text.SCREEN, COST_COLUMN, COST_CHARACTER),
        lambda lib, buf: lib.g_draw_char(buf, text.SCREEN, COST_COLUMN, COST_CHARACTER))
    asm_twins.assert_within_the_bar(CHAR_TWIN, original, twin, CHAR_COST_CEILING)


