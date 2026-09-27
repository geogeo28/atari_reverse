"""v_gtext's fast path: `$fcf96a` fast_text_try and vector 5's CPU body `$fd1cc4` — `src/vdi/text_raster.c`.

    $fcf964  move.l (sp)+,a5 / moveq #0,d0 / rts      <- the SHARED refusal, BEFORE the entry
    $fcf96a  x & 7 must be 0; with CLIP, y >= ymin, y + DELY < ymax, x >= xmin, x + 8 * count < xmax;
             a5 = &LINEA_FBASE / jmp (LINEA_VECTOR_FAST_TEXT)
    $fd1cc4  the glyphs' screen byte from (x, y); `dbf d3,$fd1d36` INTO the character loop's own `dbf`;
             per character and plane, one of eight byte arms by WRT_MODE and the plane's colour bit

v_gtext calls it for an unscaled, unstyled, monospaced eight-pixel font ($fcdb84..$fcdba2): the RAM 8x8 and
8x16 fonts are those, and every case draws their real glyphs from intin, over the canvas whose every plane
differs. It answers 1 drawn or 0 refused, compared in D0.
"""
import pytest

import vdi
import vdi_raster
import vdi_text
from vdi_text import fast_text_pokes, run_fast_text

TEXT = "Aq@~ !"


def drawn(result):
    return result.info["regs"]["d0"]


@pytest.mark.parametrize("x", (96, 104, 0, 312))
@pytest.mark.parametrize("font", ("8x8", "8x16"))
@pytest.mark.parametrize("mode", vdi_text.MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_every_mode_and_colour_on_both_bytes_of_a_group(x, font, mode, colour):
    """x on a group (the even byte) and half way through one (the odd byte), and at the screen's edges."""
    text = TEXT if x < 300 else "W"
    assert drawn(run_fast_text(fast_text_pokes(text, font=font, x=x, mode=mode, colour=colour, window=None))) == 1


@pytest.mark.parametrize("count", (0, 1, 2, 3, 40))
def test_the_character_count_is_contrl_3(count):
    """None — the `dbf` on the count falls straight through — one, two in one group, three across groups,
    and a whole line of forty."""
    text = ("0123456789" * 4)[:count]
    assert drawn(run_fast_text(fast_text_pokes(text, x=0, window=None))) == 1


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_fewer_planes(shape, mode):
    run_fast_text(fast_text_pokes(TEXT, x=24, mode=mode, colour=0b01, window=None,
                                  extra=vdi_raster.geometry_pokes(shape)))


@pytest.mark.parametrize("skew", vdi_raster.WIDTH_SKEWS)
def test_rows_are_placed_by_bytes_lin_and_stepped_by_width(skew):
    run_fast_text(fast_text_pokes(TEXT, x=40, window=None, extra=vdi_raster.width_skew_pokes(skew)))


# ---- the refusals, and the clip test that makes them -------------------------------------------------------
# The tight window (97, 51)..(170, 80). The test REFUSES MORE THAN IT NEEDS TO: a last row or column that
# would touch ymax or xmax refuses, though it is inside.
XMIN, YMIN, XMAX, YMAX = vdi_text.TIGHT
PLACES = {"inside": (104, 60, 1), "unaligned x": (101, 60, 0), "above ymin": (104, YMIN - 1, 0),
          "on ymin": (104, YMIN, 1), "last row one short of ymax": (104, YMAX - 17, 1),
          "last row on ymax - 1": (104, YMAX - 16, 0), "left of xmin": (96, 60, 0),
          "past xmax": (160, 60, 0), "last column one short of xmax": (112, 60, 1)}


@pytest.mark.parametrize("place", PLACES.values(), ids=PLACES.keys())
def test_the_clip_test_accepts_and_refuses(place):
    x, y, expected = place
    text = "ABCDEFG"[:(XMAX - 112) // vdi_text.FAST_GLYPH_PIXELS] if x == 112 else "AB"
    assert drawn(run_fast_text(fast_text_pokes(text, x=x, y=y, window=vdi_text.TIGHT))) == expected


# A window whose sides are on bytes, so a string can start exactly on xmin and end exactly on xmax.
BYTE_WINDOW = (96, 51, 176, 80)
BYTE_EDGES = {"starting on xmin": (96, 60, "AB", 1), "one byte left of xmin": (88, 60, "AB", 0),
              "ending on xmax": (160, 60, "AB", 0), "ending a pixel short of xmax": (160, 60, "A", 1)}


@pytest.mark.parametrize("edge", BYTE_EDGES.values(), ids=BYTE_EDGES.keys())
def test_the_clip_test_at_byte_aligned_edges(edge):
    x, y, text, expected = edge
    assert drawn(run_fast_text(fast_text_pokes(text, x=x, y=y, window=BYTE_WINDOW))) == expected


def test_the_count_is_a_whole_word():
    """contrl[3] of 257 is `lsl.w #3`'d whole into the clip test — 2,056 pixels, refused — where its low byte
    alone would be one character, inside."""
    pokes = fast_text_pokes("A", x=104, window=BYTE_WINDOW)
    staged = vdi.merge_pokes(pokes, {vdi.CONTRL_AT: vdi.contrl(vdi_text.GTEXT_OPCODE, 0, 0x101)})
    assert drawn(run_fast_text(staged)) == 0


def test_without_clip_it_draws_anywhere_on_a_byte():
    assert drawn(run_fast_text(fast_text_pokes("AB", x=8, y=2, window=None))) == 1
    assert drawn(run_fast_text(fast_text_pokes("AB", x=9, y=2, window=None))) == 0


@pytest.mark.parametrize("mode", range(len(vdi_text.MODES), 2 * len(vdi_text.MODES)))
def test_a_mode_past_3_with_the_colour_clear_takes_a_neighbouring_arm(mode):
    """WRT_MODE 4..7 index the arm table's second half — the colour-set arms of modes 0..3 — when the
    plane's colour bit is clear (with it set they run past the table into code: halted in the C)."""
    run_fast_text(fast_text_pokes(TEXT, x=48, mode=mode, colour=0, window=None))


def test_through_the_vdi_s_own_array_pointers():
    """The count is read through LINEA_CONTRL and the characters through LINEA_INTIN AT THE CALL: an
    intin laid somewhere else is followed."""
    pokes = fast_text_pokes("", x=48, window=None)
    staged = vdi.merge_pokes(pokes, {vdi.CONTRL_AT: vdi.contrl(vdi_text.GTEXT_OPCODE, 0, 3), vdi.PTSOUT_AT: vdi.pack_words(*b"xyz")},
                             vdi.linea_pokes(INTIN=vdi.PTSOUT_AT))
    run_fast_text(staged)


# Tier 3's rows: a whole line of the 8x16 font, a short transparent string inside the clip, and a refusal.
TIER3_ROWS = {"forty characters, replace": fast_text_pokes("0123456789" * 4, x=0, mode="replace", colour=0b1010,
                                                           window=None),
              "six characters, transparent": fast_text_pokes(TEXT, x=104, mode="transparent", colour=0b0110),
              "refused": fast_text_pokes("AB", x=101)}
# Each a C row and `.S` rows (`text_raster.S`): the front end, and — where it draws — vector 5's body itself.
for _label, _pokes in TIER3_ROWS.items():
    vdi.register(f"linea_fast_text, {_label}", vdi.addrs.LINEA_ROM_FAST_TEXT, _pokes)
    vdi_text.register_transcription("LINEA_ROM_FAST_TEXT", _label, _pokes)
    if _label != "refused":
        vdi_text.register_transcription("LINEA_ROM_CPU_FAST_TEXT", _label, _pokes, vdi_text.fast_body_registers(_pokes))
