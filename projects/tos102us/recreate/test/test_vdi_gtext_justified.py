"""d_justified ($fce9e8) — GDP 10's worker, `src/vdi/gtext.c`: entered by `jsr` as the GDP's arm 10 leaves the
machine (contrl[0] = 11, contrl[5] = 10, the workstation dispatched).

    $fce9e8  contrl[3] -= 2 (left so); intin[0] / intin[1] the word and character flags; INTIN past them and
             PTSOUT at a frame; the spaces counted; vqt_extent; contrl[2] = 0; the length = ptsin[2]
    $fcea68  words spread (flag, and a space): slack / spaces (`divs.w`), the remainder made positive IN MEMORY
             ($170e) with its sign kept as the unit; spreading the characters too, the step held within half
             the widest cell (the remainder dropped with a cut) and what the words take added to the width
    $fcebc2  characters spread (flag, and two of them): what is left of the slack over count - 1
    $fcecd4  the width = the length; v_gtext; contrl[2] = the count given; PTSOUT, INTIN back

The gap records' STEPS are compared with a model of the ROM's arithmetic (`model`, below) — a restatement that
names what each case is FOR, following the ROM step for step; the evidence is the differential, which compares
the records byte for byte. Their COUNTS are what is left after v_gtext spent them on the string it drew. Every
case also draws — the text itself is compared by the differential, glyph by glyph.
"""
import pytest

import vdi
import vdi_gtext as g
import vdi_text
from case import merge_pokes
from vdi_gtext import THICKEN, UNDERLINE, justified_call, run_justified, screen_changed

QUICK = "The quick brown fox"
ROTATIONS = g.ROTATIONS
QUARTER_TURN, HALF_TURN, THREE_QUARTER_TURN, FULL_TURN = (vdi_text.QUARTER_TURN, vdi_text.HALF_TURN,
                                                       vdi_text.THREE_QUARTER_TURN, vdi_text.FULL_TURN)


def _signed(value):
    return vdi.signed_word(value & 0xFFFF)


def _divide(slack, gaps):
    """`divs.w` of a sign-extended word: the quotient toward 0, the remainder with the dividend's sign."""
    quotient = int(slack / gaps)
    return quotient, slack - quotient * gaps


def _turned(step, unit, rotation):
    return {0: (step, 0, unit, 0), QUARTER_TURN: (0, -step, 0, -unit), HALF_TURN: (-step, 0, -unit, 0),
            THREE_QUARTER_TURN: (0, step, 0, unit)}.get(rotation)


def model(width, length, spaces, count, *, words, characters, cell, rotation):
    """The two gap records d_justified leaves — `{kind: (STEP_X, STEP_Y, EXTRA, EXTRA_X, EXTRA_Y)}`, None for a
    field it does not write — before v_gtext spends their counts."""
    records = {}
    if words and spaces:
        step, extra = _divide(_signed(length - width), spaces)
        unit = -1 if extra < 0 else 1
        extra = abs(extra)
        if characters:
            limit = cell >> 1
            if step > limit or step < -limit:
                step, extra = max(-limit, min(limit, step)), 0
            width = _signed(width + _signed(step * spaces) + _signed(unit * extra))
        records["space"] = (step, unit, extra)
    else:
        records["space"] = None
    if characters and count > 1:
        step, extra = _divide(_signed(length - width), count - 1)
        unit = -1 if extra < 0 else 1
        records["character"] = (step, unit, abs(extra))
    else:
        records["character"] = None
    return {kind: _record(entry, rotation) for kind, entry in records.items()}


def _record(entry, rotation):
    if entry is None:
        return {"STEP_X": 0, "STEP_Y": 0, "EXTRA": 0}
    step, unit, extra = entry
    turned = _turned(step, unit, rotation)
    if turned is None:
        return {"EXTRA": extra}
    return dict(zip(("STEP_X", "STEP_Y", "EXTRA_X", "EXTRA_Y"), turned), EXTRA=extra)


def spent(record, taken):
    """A record's count after v_gtext took `taken` gaps of its kind."""
    return {**record, "EXTRA": max(0, record["EXTRA"] - taken)}


def assert_the_gaps(result, string, length, *, words, characters, font="8x16", rotation=0, width=None):
    count = len(string)
    cell = g.font_word(font, "MAX_CELL_WIDTH")
    width = count * cell if width is None else width
    spaces = string.count(" ")
    expected = model(width, length, spaces, count, words=words, characters=characters, cell=cell, rotation=rotation)
    drawn = count > 0
    expected = {"space": spent(expected["space"], spaces if drawn else 0),
                "character": spent(expected["character"], count if drawn else 0)}
    for kind in ("space", "character"):
        found = g.gap(result, kind)
        stale = {name: vdi.signed_word(vdi.STALE_WORD) for name in g.GAP_FIELDS if name not in expected[kind]}
        assert found == {**stale, **expected[kind]}, kind


def run(string, length, **kwargs):
    return run_justified(justified_call(string, length, **kwargs))


# ---- the flags, the slack --------------------------------------------------------------------------------------
LENGTHS = {"longer, a remainder": 211, "longer, exact": 184, "the same": 152, "shorter": 140, "much shorter": 60}


@pytest.mark.parametrize("length", LENGTHS)
@pytest.mark.parametrize("words,characters", ((1, 0), (0, 1), (1, 1), (0, 0), (0x8000, 0x0100)))
def test_the_slack_spread_over_the_words_and_the_characters(words, characters, length):
    """Positive, zero and negative slack, each flag alone, both, neither — any nonzero word is a flag."""
    result = run(QUICK, LENGTHS[length], words=words, characters=characters)
    assert_the_gaps(result, QUICK, LENGTHS[length], words=words, characters=characters)
    assert screen_changed(result)


@pytest.mark.parametrize("length", (400, -200, 153, 151, 164, 167, 140, 137))
def test_the_word_step_is_held_within_half_a_cell_when_characters_spread_too(length):
    """Half of 8: a slack of +248 over three spaces would step 82 and one of -352 step -117 — both cut to 4
    and the remainder dropped; just over and just under the width still step 0; +12 and -12 step exactly 4
    (kept), +15 and -15 one past it (cut)."""
    result = run(QUICK, length, words=1, characters=1)
    assert_the_gaps(result, QUICK, length, words=1, characters=1)


@pytest.mark.parametrize("font", ("6x6", "proportional"))
def test_the_cut_is_the_font_s_own_half_cell(font):
    """6x6: a cell of 6, so 3; the proportional face (the 8x8's cell of 8), its width MEASURED, not counted."""
    result = run(QUICK, 300, words=1, characters=1, font=font)
    assert g.gap(result, "space")["STEP_X"] == g.font_word(font, "MAX_CELL_WIDTH") >> 1
    assert result.word(vdi.VDI_EXTENT_SCRATCH) == 300, "the width v_gtext aligns by is the length asked for"


@pytest.mark.parametrize("string", ("Justified", "Hi", "A", "", "one two"))
@pytest.mark.parametrize("length", (100, 30))
def test_a_single_word_and_short_strings(string, length):
    """No space: the word gaps are closed. One character: no character gap. No text: v_gtext draws nothing."""
    result = run(string, length, words=1, characters=1)
    assert_the_gaps(result, string, length, words=1, characters=1)
    assert screen_changed(result) == bool(string)


@pytest.mark.parametrize("rotation", ROTATIONS + (FULL_TURN,))
def test_the_gaps_are_turned_for_the_rotation(rotation):
    """Each right angle turns both records; any other leaves their steps as they were (stale) — only the counts
    are written — and v_gtext draws from where the last text stopped."""
    result = run(QUICK, 200, words=1, characters=1, rotation=rotation, x=160, y=100)
    assert_the_gaps(result, QUICK, 200, words=1, characters=1, rotation=rotation)


@pytest.mark.parametrize("h_align", (1, 2))
def test_aligned_by_the_length_asked_for(h_align):
    result = run(QUICK, 200, words=1, characters=0, h_align=h_align, x=200, y=100, style=UNDERLINE | THICKEN)
    assert result.word(vdi.VDI_EXTENT_SCRATCH) == 200
    assert screen_changed(result)


# ---- what it leaves the caller --------------------------------------------------------------------------------------
def test_contrl_3_is_left_less_two_and_contrl_2_gets_the_count():
    result = run(QUICK, 200)
    assert result.contrl(vdi.CONTRL_N_INTIN) == len(QUICK)
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == len(QUICK) + 2
    assert (result.linea("INTIN"), result.linea("PTSOUT")) == (vdi.INTIN_AT, vdi.PTSOUT_AT)


@pytest.mark.parametrize("given", (2, 1, 0, -5))
def test_two_words_or_fewer_draw_nothing(given):
    pokes = merge_pokes(justified_call("xy", 90), {vdi.CONTRL_AT + vdi.CONTRL_N_INTIN: vdi.pack_words(given)})
    result = run_justified(pokes)
    assert not screen_changed(result)
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == given & 0xFFFF


# ---- the order of reads and stores ----------------------------------------------------------------------------------
def test_the_length_is_read_after_the_string_is_measured():
    """ptsin laid on the dispatcher's alignment copies: ptsin[2] IS the width word — read after vqt_extent wrote it,
    so the slack is 0 — and the string is drawn at (H_ALIGN, V_ALIGN)."""
    pokes = merge_pokes(justified_call("a b c", 0, words=1, characters=1),
                        vdi.linea_pokes(PTSIN=vdi.VDI_TEXT_H_ALIGN))
    result = run_justified(pokes)
    width = 5 * g.font_word("8x16", "MAX_CELL_WIDTH")
    assert g.gap(result, "space")["STEP_X"] == 0 and result.word(vdi.VDI_EXTENT_SCRATCH) == width


def test_the_length_is_read_after_contrl_2_is_cleared():
    """ptsin laid on contrl: ptsin[2] IS contrl[2] — vqt_extent's 4, cleared to 0 before the length is read, so
    the string is spread to 0 (and drawn at contrl[0..1], (11, 2))."""
    pokes = merge_pokes(justified_call(QUICK, 0, words=1, characters=0), vdi.linea_pokes(PTSIN=vdi.CONTRL_AT))
    result = run_justified(pokes)
    assert_the_gaps(result, QUICK, 0, words=1, characters=0)


# ==== Tier 3: the worst realistic rows ======================================================================
vdi.register("vdi_d_justified, words and characters, turned", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call(QUICK, 211, words=1, characters=1, rotation=QUARTER_TURN, x=160, y=150))
vdi.register("vdi_d_justified, one word, characters spread", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call("Justified", 100, words=1, characters=1))
vdi.register("vdi_d_justified, nothing to draw", g.addrs.VDI_ROM_D_JUSTIFIED, justified_call("", 100))
vdi.register("vdi_d_justified, words and characters, clipped away", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call(QUICK, 211, words=1, characters=1, y=150, window=g.TIGHT))
# ...and where the per-glyph cost is the whole of it: a long line with many spaces scrolled out of view, every
# glyph at TextBlt's trivial clip — words and characters both spread over 80 and 120 characters of "a a a ...",
# and a line of nothing but spaces (every glyph takes both gaps).
SPACED = "a "
vdi.register("vdi_d_justified, eighty characters, forty spaces, both spread, clipped away", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call(SPACED * 40, 700, words=1, characters=1, y=150, window=g.TIGHT))
vdi.register("vdi_d_justified, a hundred and twenty characters, both spread, clipped away", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call(SPACED * 60, 900, words=1, characters=1, y=150, window=g.TIGHT))
vdi.register("vdi_d_justified, eighty spaces, both spread, clipped away", g.addrs.VDI_ROM_D_JUSTIFIED,
             justified_call(" " * 80, 700, words=1, characters=1, y=150, window=g.TIGHT))
