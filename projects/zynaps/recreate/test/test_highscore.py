"""Differential tests for the ROLE OF HONOUR screen (src/highscore.c).

The screen composes routines that already have batteries of their own — `screen_clear`,
`blit_graphic_block`, `draw_text_record`, `draw_bcd_number` and `screen_flip_buffers` — so what
these cases are for is the COMPOSITION: which buffer each piece goes into, that the logo's three
strips walk one source pointer rather than three, and that the five scores are drawn at the
routine's own row displacements and not at the rows the records carry.

WHAT THE DIFFERENTIAL CANNOT SEE HERE: `screen_flip_buffers` publishes the new front buffer to the
shifter at $ff8201/$ff8203, which is not an image address. The POINTER SWAP it makes is diffed;
the publish is not, and reaches only src/video.c's sink (include/video.h). STATUS.md carries that
residual, which is the video subsystem's rather than this one's.
"""
import ctypes
from pathlib import Path

import pytest

import abi
import harness
from abi import seed_spans
from harness import differential, report

ENTRY_ROLE_OF_HONOUR_SCREEN = 0x13338

# mirrors of include/highscore.h
A_HIGHSCORE_TABLE = 0x19d5a
HIGHSCORE_ENTRIES = 5
HIGHSCORE_ENTRY_BYTES = 0x16
HIGHSCORE_ENTRY_RECORD = 4
HIGHSCORE_DIGITS_COLUMN = 0xe
HIGHSCORE_FIRST_SCORE_OFFSET = 0x44c0
HIGHSCORE_SCORE_ROW_STEP = 0x780

# mirrors of include/hud.h
A_ZYNAPS_LOGO = 0x6c8ee
LOGO_STRIPS = 3
LOGO_STRIP_BYTES = 0x800

# mirrors of include/text.h
A_FONT_GLYPHS = 0x6be6e

# mirrors of include/video.h
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
SCREEN_BYTES = 32000
SCREEN_ROW_BYTES = 160

DISK = Path(__file__).resolve().parents[2] / "bin" / "disk"
SCREEN_BACK_BUFFER = abi.SCREEN_BACK
SCREEN_FRONT_BUFFER = abi.SCREEN_FRONT

harness._lib.g_role_of_honour_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_role_of_honour_screen.restype = None


def _pokes(seed, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None):
    """Noise over both framebuffers, the real font and the real ZYNAPS logo, plus a case's own.

    Both graphics are bss — `_start` loads EXTCHARS.DAT and ZYNLOGO.DAT over them — so against a
    fresh image every glyph and every logo strip would blit zeroes and a wrong source address would
    be invisible. The guard bands are what turn a blit one row too far into a difference.
    """
    spans = [(back, back + SCREEN_BYTES), (front, front + SCREEN_BYTES)]
    pokes = seed_spans(seed, spans, guard=abi.GUARD_BYTES)
    pokes[A_FONT_GLYPHS] = (DISK / "EXTCHARS.DAT").read_bytes()
    pokes[A_ZYNAPS_LOGO] = (DISK / "ZYNLOGO.DAT").read_bytes()
    pokes[A_SCREEN_BACK] = back.to_bytes(4, "big")
    pokes[A_SCREEN_FRONT] = front.to_bytes(4, "big")
    pokes.update(extra or {})
    return pokes


def _case(seed=0, back=SCREEN_BACK_BUFFER, front=SCREEN_FRONT_BUFFER, extra=None, poison=False):
    pokes = _pokes(seed, back=back, front=front, extra=extra)
    diffs, _ = differential(
        ENTRY_ROLE_OF_HONOUR_SCREEN, {"_pokes": pokes},
        lambda lib, buf: lib.g_role_of_honour_screen(buf), poison=poison)
    assert not diffs, f"seed={seed} back={back:#x} front={front:#x}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (11, 12, 13))
def test_shipped_table(seed):
    """The screen as the game ships it: five names and five scores from the .PRG's own table."""
    _case(seed=seed)


def test_draws_into_the_back_buffer_whichever_it_is():
    """It takes the draw buffer from 0x1797e and flips at the end, so a candidate that hard-coded a
    buffer would agree only while the pointers happen to be the way `_start` left them."""
    _case(seed=21, back=SCREEN_FRONT_BUFFER, front=SCREEN_BACK_BUFFER)
    _case(seed=22, back=abi.SCRATCH, front=SCREEN_FRONT_BUFFER)


def _table_with(entries):
    """The five-entry table rebuilt from (score, column, row, name) tuples."""
    blob = b""
    for score, column, row, name in entries:
        name = name.ljust(HIGHSCORE_ENTRY_BYTES - HIGHSCORE_ENTRY_RECORD - 3, b" ")
        blob += score.to_bytes(4, "big") + bytes([column & 0xff, row & 0xff]) + name + b"\x00"
    assert len(blob) == HIGHSCORE_ENTRIES * HIGHSCORE_ENTRY_BYTES
    return {A_HIGHSCORE_TABLE: blob}


def test_the_score_rows_are_the_routines_own():
    """THE SCORES DO NOT FOLLOW THE RECORDS. Each score is drawn at a `lea` displacement of the
    routine's own — 17600 and four steps of 1920 — while each NAME is drawn at the row byte inside
    its record. The shipped table makes those the same five rows, so the only way to tell them apart
    is a table where they differ, which is what this case builds: the names move and the scores must
    not. A reconstruction that read the row from the record passes every other case here.
    """
    entries = [(0x00010000 * (i + 1), 0x10, 20 + i * 4, b"NAME%d" % i)
               for i in range(HIGHSCORE_ENTRIES)]
    _case(seed=31, extra=_table_with(entries))


def test_every_score_is_its_own_entry():
    """Five different scores at five different rows: a candidate that drew one entry's score five
    times, or walked the table with the wrong stride, differs on four rows out of five."""
    entries = [(0x12345678, 0x10, 110, b"AAA"), (0x00000000, 0x10, 122, b"BBB"),
               (0x99999999, 0x10, 134, b"CCC"), (0x00000001, 0x10, 146, b"DDD"),
               (0xffffffff, 0x10, 158, b"EEE")]
    _case(seed=41, extra=_table_with(entries))


def test_record_columns_are_the_records_own():
    """The name records carry their own column, and the routine passes each one through untouched —
    including a NEGATIVE one, which draw_text_record sign-extends to the left of the buffer."""
    entries = [(0x00000100 * (i + 1), column, 110 + i * 12, b"X")
               for i, column in enumerate((0, 1, 0x27, 0xff, 0x80))]
    _case(seed=51, extra=_table_with(entries))


def test_the_logo_strips_walk_one_source():
    """`blit_graphic_block` ADVANCES its source, and the routine loads it once for all three strips,
    so strip 1 starts where strip 0 stopped. Poking the logo's three strips to three distinguishable
    patterns is what separates that from three blits of strip 0."""
    logo = b"".join(bytes([0x11 * (strip + 1)]) * LOGO_STRIP_BYTES for strip in range(LOGO_STRIPS))
    _case(seed=61, extra={A_ZYNAPS_LOGO: logo})


# NO POISON PASS, and it is not an oversight: MEASURED, it crashes the candidate. The screen ends
# in `screen_flip_buffers`, which WRITES 0x1797e/0x17982 — so the attribution pass poisons the very
# pointer the routine reads its draw buffer from, and the re-run then draws at a canary address.
# That is the same shape as test_sound.py's two no-poison routines: an output the routine also
# steers on cannot be a canary. What the pass would have bought is bought instead by the pieces this
# screen is made of, every one of which has its own poison cases (test_text.py's draw_char /
# draw_bcd_number / draw_text_record, test_video.py's screen_clear / blit_graphic_block), plus
# `test_the_logo_strips_walk_one_source` and `test_every_score_is_its_own_entry` above, which fail
# on a candidate that writes the right bytes in the wrong places.


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_HIGHSCORE_TABLE", "include/highscore.h", "A_highscore_table"),
    ("HIGHSCORE_ENTRIES", "include/highscore.h", "HIGHSCORE_ENTRIES"),
    ("HIGHSCORE_ENTRY_BYTES", "include/highscore.h", "HIGHSCORE_ENTRY_BYTES"),
    ("HIGHSCORE_ENTRY_RECORD", "include/highscore.h", "HIGHSCORE_ENTRY_RECORD"),
    ("HIGHSCORE_DIGITS_COLUMN", "include/highscore.h", "HIGHSCORE_DIGITS_COLUMN"),
    ("HIGHSCORE_FIRST_SCORE_OFFSET", "include/highscore.h", "HIGHSCORE_FIRST_SCORE_OFFSET"),
    ("HIGHSCORE_SCORE_ROW_STEP", "include/highscore.h", "HIGHSCORE_SCORE_ROW_STEP"),
    ("A_ZYNAPS_LOGO", "include/hud.h", "A_zynaps_logo"),
    ("LOGO_STRIPS", "include/hud.h", "LOGO_STRIPS"),
    ("LOGO_STRIP_BYTES", "include/hud.h", "LOGO_STRIP_BYTES"),
    ("A_FONT_GLYPHS", "include/text.h", "A_font_glyphs"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
)
ENTRY_PROLOGUES = {
    # Ten bytes is not enough here: `title_screen_draw` @ 0x12a28 opens with the SAME
    # `lea $6c8ee,a6 / movea.l $1797e,a0` and the two separate only at byte 16.
    "ENTRY_ROLE_OF_HONOUR_SCREEN": "4df90006c8ee20790001797e2f086100f626",
}
