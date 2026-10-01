"""AES gemgrlib's box animations that never wait on an event — `src/aes/grlib.c`, through `test/aes_gsx.py`'s door and
`test_aes_gemgraf.py`'s band and signatures.

    gr_setup      gsx_sclip(gl_rscreen); gsx_attr(line, XOR, colour)
    gr_scale      gr_setup(1); count = the bits of x + y (`lsr.w`) less one; each step max(1, distance / count),
                  or 1 for no count; D0 = the x step
    gr_stepcalc   *cx = r->w/2 - w/2, *cy = r->h/2 - h/2 (`lsr.w` halves); gr_scale(*cx, *cy, ...) read back;
                  *cx += r->x, *cy += r->y
    gr_xor        count + 1 times (`dbf`): gsx_xcbox or gsx_xbox of its own frame's GRECT, stepped back by the
                  steps (and widened by twice them when it grows)
    gr_movebox    gr_scale(|dx|, |dy|) into its saved registers' words, the steps' signs the direction's; gsx_moff;
                  gr_xor twice (drawn, undrawn); gsx_mon
    gr_growbox    gr_stepcalc(from's size centred in to); gr_movebox(from -> the centre); gsx_moff; gr_xor of the
                  corners, grown, twice; gsx_mon.     gr_shrinkbox: the corners shrunk from `to`, then gr_movebox back

Every case runs in the door's machine (the cursor hidden by the ROM's own gsx_moff) unless it says the snapshot's,
and the WHOLE image is compared, the screen included. gr_stepcalc has no Line-F call word (only gr_growbox's and
gr_shrinkbox's shared prologue reaches it, by `bsr`); every other routine is entered through its word once.
"""
import pytest

import aes
import aes_gsx as gsx
import test_aes_gemgraf as graf
from case import merge_pokes
from test_aes_gemgraf import THROUGH, answer_at, rect_at, rect_pokes
from test_aes_gsx import screen_changed

COUNT, X_STEP, Y_STEP, CENTRE_X, CENTRE_Y = (answer_at(index) for index in range(5))
SCALE_POINTERS = (COUNT, X_STEP, Y_STEP)
STALE_ANSWERS = graf.STALE_ANSWERS


def scale_answers(result):
    return [aes.signed(word) for word in result.words(COUNT, 3)]


# ---- gr_setup ----------------------------------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("colour", (1, 3), ids=("black", "a colour"))
def test_gr_setup_clips_the_screen_and_xors(colour, through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_SETUP", (colour,), through_line_f=through_line_f)
    assert graf.clip_of(result) == (0, 0, 320, 200)
    assert (result.field("AES", "GL_MODE"), result.field("AES", "GL_LCOLOR")) == (graf.GRAF["GSX_MODE_XOR"], colour)


# ---- gr_scale ----------------------------------------------------------------------------------------------------------------
# (x, y, count, x step, y step): no distance, distances under one step, the steps' floor of 1, and a sum that wraps.
SCALE = {
    "no distance": (0, 0, 0, 1, 1),
    "one pixel: no steps": (1, 0, 0, 1, 1),
    "three pixels": (3, 0, 1, 3, 1),
    "a window's way": (100, 50, 7, 14, 7),
    "the y step's floor": (300, 2, 8, 37, 1),
    "the most": (0x7FFF, 0x7FFF, 15, 2184, 2184),
    "-32768: the unsigned shift counts it large, the step's floor holds": (-0x8000, 0, 15, 1, 1),
}


@pytest.mark.parametrize("x, y, count, x_step, y_step", SCALE.values(), ids=SCALE)
def test_gr_scale(x, y, count, x_step, y_step):
    result = gsx.run_gsx("AES_ROM_GR_SCALE", (x, y, *SCALE_POINTERS), STALE_ANSWERS)
    assert scale_answers(result) == [count, x_step, y_step]
    assert result.answer() == x_step


@THROUGH
def test_gr_scale_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_SCALE", (100, 50, *SCALE_POINTERS), STALE_ANSWERS, through_line_f=through_line_f)
    assert scale_answers(result) == [7, 14, 7]


def test_gr_scale_stores_its_answers_in_order():
    """The three pointers on one word: the count, then the x step, then the y step, the last left."""
    result = gsx.run_gsx("AES_ROM_GR_SCALE", (100, 50, COUNT, COUNT, COUNT), STALE_ANSWERS)
    assert result.word(COUNT) == 7


def test_gr_scale_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GR_SCALE", (100, 50, *(at | aes.BUS_TAG for at in SCALE_POINTERS)), STALE_ANSWERS)
    assert scale_answers(result) == [7, 14, 7]


# ---- gr_stepcalc ------------------------------------------------------------------------------------------------------------
STEPCALC_POINTERS = (CENTRE_X, CENTRE_Y, COUNT, X_STEP, Y_STEP)


def stepcalc(width, height, rect, pointers=STEPCALC_POINTERS, pokes=None):
    staged = merge_pokes(STALE_ANSWERS, rect_pokes(*rect), pokes)
    return gsx.run_gsx("AES_ROM_GR_STEPCALC", (width, height, rect_at(0), *pointers), staged)


# (w, h, the GRECT): centred in a larger one, a box larger than the GRECT (negative half-differences), odd sizes.
STEPCALC = {
    "an icon in a window": (32, 32, (40, 30, 200, 120)),
    "a box larger than the GRECT": (200, 120, (40, 30, 32, 32)),
    "odd sizes: the halves rounded down": (33, 31, (40, 30, 201, 119)),
    "a negative size: halved unsigned": (-2, 4, (40, 30, 20, 20)),
}


@pytest.mark.parametrize("width, height, rect", STEPCALC.values(), ids=STEPCALC)
def test_gr_stepcalc(width, height, rect):
    result = stepcalc(width, height, rect)
    x, y, w, h = rect
    assert result.words(CENTRE_X, 2) == [((w & 0xFFFF) // 2 - (width & 0xFFFF) // 2 + x) & 0xFFFF,
                                         ((h & 0xFFFF) // 2 - (height & 0xFFFF) // 2 + y) & 0xFFFF]


def test_gr_stepcalc_reads_the_grect_after_its_first_store():
    """The ORDER: the x centre's pointer IS the GRECT's height, so the height read for the y centre is the x
    centre just stored — and the corner added at the end is read after gr_scale."""
    result = stepcalc(32, 32, (40, 30, 200, 120), pointers=(rect_at(0) + aes.GRECT_H, CENTRE_Y, COUNT, X_STEP, Y_STEP))
    assert result.word(CENTRE_Y) == ((100 - 16) // 2 - 16 + 30) & 0xFFFF


def test_gr_stepcalc_reads_its_centre_back_after_gr_scale():
    """...and the count's pointer IS the x centre's: gr_scale's count lands on it before the corner is added."""
    result = stepcalc(32, 32, (40, 30, 200, 120), pointers=(CENTRE_X, CENTRE_Y, CENTRE_X, X_STEP, Y_STEP))
    assert result.word(CENTRE_X) == 7 + 40


def test_gr_stepcalc_reads_both_centres_back_before_gr_scale():
    """...the two centres on one word: the y centre stored over the x one, and gr_scale handed that word twice — then
    the corner's x and y both added to it, in that order."""
    result = stepcalc(32, 32, (40, 30, 200, 120), pointers=(CENTRE_X, CENTRE_X, COUNT, X_STEP, Y_STEP))
    assert scale_answers(result) == [6, 7, 7]
    assert result.word(CENTRE_X) == (120 // 2 - 32 // 2) + 40 + 30


def test_gr_stepcalc_reads_the_corner_s_y_after_the_x_centre_is_added():
    """...and the x centre's pointer IS the GRECT's y: the x centre added in place there, then read as the corner's y
    for the y centre."""
    result = stepcalc(32, 32, (40, 30, 200, 120), pointers=(rect_at(0) + aes.GRECT_Y, CENTRE_Y, COUNT, X_STEP, Y_STEP))
    x_centre = (200 // 2 - 32 // 2) + 40
    assert result.word(CENTRE_Y) == (120 // 2 - 32 // 2) + x_centre


def test_gr_stepcalc_s_pointers_are_put_on_the_bus():
    result = stepcalc(32, 32, (40, 30, 200, 120), pointers=tuple(at | aes.BUS_TAG for at in STEPCALC_POINTERS))
    assert result.words(CENTRE_X, 2) == [124, 74]


# ---- gr_xor ------------------------------------------------------------------------------------------------------------------
# (corners, count, x, y, w, h, x step, y step, grows): one box, a box stepped, corners growing, corners shrinking.
# A count of $ffff (65536 boxes, `dbf`) is UNREACHABLE: every ROM caller (gr_movebox, gr_growbox, gr_shrinkbox) hands
# gr_scale's count, at most 15 (`lsr.w` of a word).
XOR = {
    "one box": (0, 0, 40, 30, 100, 50, 0, 0, 0),
    "a box stepped three times": (0, 3, 40, 30, 100, 50, -10, -5, 0),
    "corners growing": (1, 3, 120, 80, 32, 32, 8, 6, 1),
    "corners shrinking": (1, 2, 40, 30, 200, 120, -8, -6, 1),
}


@pytest.mark.parametrize("arguments", XOR.values(), ids=XOR)
def test_gr_xor(arguments):
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_XOR", arguments))


@THROUGH
def test_gr_xor_through_its_callers_word(through_line_f):
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_XOR", XOR["a box stepped three times"], through_line_f=through_line_f))


# ---- gr_movebox, gr_growbox, gr_shrinkbox ------------------------------------------------------------------------------------
MOVEBOX = {
    "down and right": (32, 32, 20, 20, 200, 120),
    "up and left: the steps negated": (32, 32, 200, 120, 20, 20),
    "nowhere": (32, 32, 60, 60, 60, 60),
    "across only: no y to step": (32, 32, 20, 60, 200, 60),
}


@pytest.mark.parametrize("arguments", MOVEBOX.values(), ids=MOVEBOX)
def test_gr_movebox(arguments):
    """Drawn and undrawn in XOR: the screen as it was, the clip and attributes gr_setup leaves the only change."""
    result = gsx.run_gsx("AES_ROM_GR_MOVEBOX", arguments)
    assert not screen_changed(result)
    assert graf.clip_of(result) == (0, 0, 320, 200)


@THROUGH
def test_gr_movebox_through_its_callers_word(through_line_f):
    gsx.run_gsx("AES_ROM_GR_MOVEBOX", MOVEBOX["down and right"], through_line_f=through_line_f)


def test_gr_movebox_hides_the_snapshot_s_cursor_round_it():
    result = gsx.run_gsx("AES_ROM_GR_MOVEBOX", MOVEBOX["down and right"], onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN


FROM, TO = rect_at(0), rect_at(1)
ICON_TO_WINDOW = merge_pokes(rect_pokes(64, 40, 32, 32, slot=0), rect_pokes(20, 20, 280, 160, slot=1))


@THROUGH
@pytest.mark.parametrize("name", ("AES_ROM_GR_GROWBOX", "AES_ROM_GR_SHRINKBOX"), ids=("grow", "shrink"))
def test_a_box_grows_and_shrinks(name, through_line_f):
    result = gsx.run_gsx(name, (FROM, TO), ICON_TO_WINDOW, through_line_f=through_line_f)
    assert not screen_changed(result)
    assert result.words(rect_at(0), 4) == [64, 40, 32, 32]


@pytest.mark.parametrize("name", ("AES_ROM_GR_GROWBOX", "AES_ROM_GR_SHRINKBOX"), ids=("grow", "shrink"))
def test_a_box_grows_and_shrinks_over_the_snapshot_s_cursor(name):
    result = gsx.run_gsx(name, (FROM, TO), ICON_TO_WINDOW, onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN


@pytest.mark.parametrize("name", ("AES_ROM_GR_GROWBOX", "AES_ROM_GR_SHRINKBOX"), ids=("grow", "shrink"))
def test_a_box_grows_and_shrinks_through_tagged_pointers(name):
    gsx.run_gsx(name, (FROM | aes.BUS_TAG, TO | aes.BUS_TAG), ICON_TO_WINDOW)


# A `to` over ptsin, rewritten by every box drawn, makes the ROM's run long, but it ends: MEASURED (a bisection of
# max_insns over the six to-over-ptsin cases below) the longest takes 205,175 instructions, just past the oracle's
# default 200,000 — the budget is twice that.
TO_OVER_PTSIN_MEASURED_INSNS = 205_175
TO_OVER_PTSIN_INSNS = 2 * TO_OVER_PTSIN_MEASURED_INSNS


@pytest.mark.parametrize("name", ("AES_ROM_GR_GROWBOX", "AES_ROM_GR_SHRINKBOX"), ids=("grow", "shrink"))
@pytest.mark.parametrize("over, at", (("from", 0), ("to", 0), ("to", 4), ("to", 8)), ids=("from", "to+0", "to+4", "to+8"))
def test_a_box_over_ptsin_is_read_again_each_pass(name, over, at):
    """`from` or `to` laid over ptsin (at a word offset), which every box drawn rewrites: growing reads `from`'s size
    again for each pass, shrinking `to` (and `from` for the move back) — so each pass sees what the last left there."""
    small, large = (64, 40, 32, 32), (20, 20, 280, 160)
    over_ptsin = aes.AES_GSX_PTSIN + at
    if over == "from":
        pokes = merge_pokes(rect_pokes(*small, at=over_ptsin), rect_pokes(*large, slot=1))
        gsx.run_gsx(name, (over_ptsin, TO), pokes)
    else:
        pokes = merge_pokes(rect_pokes(*small, slot=0), rect_pokes(*large, at=over_ptsin))
        gsx.run_gsx(name, (FROM, over_ptsin), pokes, max_insns=TO_OVER_PTSIN_INSNS)


# ---- the registry ----------------------------------------------------------------------------------------------------------
_ROWS = {
    "black": ("AES_ROM_GR_SETUP", (1,), None),
    "a window's way": ("AES_ROM_GR_SCALE", (100, 50, *SCALE_POINTERS), STALE_ANSWERS),
    "no distance": ("AES_ROM_GR_SCALE", (0, 0, *SCALE_POINTERS), STALE_ANSWERS),
    "an icon in a window": ("AES_ROM_GR_STEPCALC", (32, 32, rect_at(0), *STEPCALC_POINTERS),
                            merge_pokes(STALE_ANSWERS, rect_pokes(40, 30, 200, 120))),
    "a box stepped three times": ("AES_ROM_GR_XOR", XOR["a box stepped three times"], None),
    "corners growing": ("AES_ROM_GR_XOR", XOR["corners growing"], None),
    "corners shrinking": ("AES_ROM_GR_XOR", XOR["corners shrinking"], None),
    "down and right": ("AES_ROM_GR_MOVEBOX", MOVEBOX["down and right"], None),
    "an icon to a window": ("AES_ROM_GR_GROWBOX", (FROM, TO), ICON_TO_WINDOW),
    "a window to an icon": ("AES_ROM_GR_SHRINKBOX", (FROM, TO), ICON_TO_WINDOW),
}
gsx.register_rows(_ROWS, line_f=("black", "a window's way", "a box stepped three times", "down and right",
                                 "an icon to a window", "a window to an icon"))
