"""`src/vdi/text_raster.S` — the text raster as the ROM wrote it, which the target build ships because its C
measures over Tier 3's 1.10 bar (`include/transcribed.h`).

Two claims hold it, neither of which needs the C: its WORDS are the ROM's, region by region, save the four
references that measure to where the blob links things (each relocated to its exact value); and it BEHAVES as
the ROM over the batteries' own cases — the same image, the whole register file and the same traffic, through
Tier 3's transcription relation. The front ends reach the ROM's bodies through their vectors on both sides; the
BODIES are entered through callers that build their front ends' stacks (`vdi_text.BODY_CALLERS`).

THE MUTATION SWEEP of `src/vdi/text_raster.S` against these BEHAVIOUR cases alone (the byte pin deselected;
strict classifier): 28 same-size mutants over the masks, the row-loop choice, the op index, the plane loop, the
row loops and the thicken fragment — 24 KILLED, 4 SURVIVED: the leftward flag `ori` as `eori` (the bit is clear
after a `neg` of a negative) and THICKEN's first-word edge compare's equal case and cleared spill (the C
sweep's equivalents, above in `test_vdi_textblt.py`) — EQUIVALENT; and a shift of 0 taken as leftward, which
`test_a_wide_row_with_no_shift` does not tell apart — the left loop over a zero shift reads the same words
and its carry mask ($ffff) takes every bit from the carried word — believed EQUIVALENT, not proved.
"""

import pytest

import test_vdi_text_raster_fast as fast
import test_vdi_textblt as textblt
import transcription
import vdi
import vdi_raster
import vdi_text
from case import merge_pokes
from vdi_text import LIGHTEN, OUTLINE, SKEW, THICKEN, textblt_pokes

# ---- the words ------------------------------------------------------------------------------------------------
REGIONS = (
    transcription.pinned_region(0xFCEE54, 0xFCEE66, "LINEA_ROM_TEXTBLT", ()),
    transcription.pinned_region(0xFCF964, 0xFCF9BE, "LINEA_ROM_FAST_TEXT", ()),
    transcription.pinned_region(*vdi_text.BODIES_REGION, "LINEA_ROM_CPU_FAST_TEXT", ("LINEA_ROM_CPU_TEXTBLT",)),
)
_ACROSS = "a reference from this file into another's region, which measures to where the blob links it"
RELOCATED = {
    0xFD1E3A: transcription.Relocated(transcription.PC_RELATIVE, "VDI_ROM_ACT_SIZ", f"TextBlt's `bsr.w` to act_siz: {_ACROSS}"),
    0xFD21C0: transcription.Relocated(transcription.ABSOLUTE, "LINEA_ROM_CONCAT", f"the final blit's `jsr` to concat: {_ACROSS}"),
    0xFD2286: transcription.Relocated(transcription.ABSOLUTE, "LINEA_ROM_LINE_PLANE_WORDS",
                                      "the blit's `lea (table).l` of the fringe masks: the ROM's own table at $fca55c, which "
                                      "raster.S carries in its second region — so the reference is to raster.S's copy"),
    0xFD24DA: transcription.Relocated(transcription.ABSOLUTE, "LINEA_ROM_CPU_FAST_TEXT",
                                      "the row loops' `movea.l #.Lfragments,a3`: this file's own fragment base"),
}


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_region_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


def test_the_textblt_body_s_caller_clears_a3_and_keeps_every_other_register():
    """Its cost is `test_transcribed.py`'s to measure, with every other caller's: here, that the
    epilogue stand-in hands back A5/A6 as the caller pushed them and only A3 is changed."""
    left = transcription.assert_caller_cost(vdi_text.TEXTBLT_BODY_CALLER)
    assert transcription.changed_from_dirty(left) == {"a3"}
    assert left["a3"] == 0


# ---- the behaviour, over the batteries' own cases ---------------------------------------------------------------

def run_both(pokes):
    """The front end (through vector 9 into the ROM's body on both sides) and the body itself."""
    vdi_text.run_transcription("LINEA_ROM_TEXTBLT", pokes)
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", pokes)


@pytest.mark.parametrize("x", textblt.XS)
@pytest.mark.parametrize("font", textblt.FONTS)
@pytest.mark.parametrize("mode", [*vdi_text.MODES, 4, 9, 14, 19])
def test_glyphs(x, font, mode):
    run_both(textblt_pokes(font, ord("g"), x=x, mode=mode))


@pytest.mark.parametrize("effect", textblt.EFFECTS.values(), ids=textblt.EFFECTS.keys())
@pytest.mark.parametrize("run", textblt.RUNS.values(), ids=textblt.RUNS.keys())
def test_every_row_loop_with_every_effect(effect, run):
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes(run, style=effect, colour=0b0110))


@pytest.mark.parametrize("weight", (1, 16, 17))
@pytest.mark.parametrize("run", ("right, wide", "left, wide", "two words"))
def test_a_line_a_caller_s_weight(weight, run):
    """A whole word of thickening (16): the edge mask the right mask itself, and a row's spill that must be
    dropped before the next row ($fd2600)."""
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes(
        textblt.RUNS[run], style=THICKEN, extra=vdi.linea_pokes(WEIGHT=weight, MONO_STATUS=0)))


# A LITEMASK that is not its own rotation either way (the fonts' $5555 is), so the direction it turns shows.
ASYMMETRIC_LITEMASK = 0x1234


@pytest.mark.parametrize("run", ("right, wide", "left, wide"))
def test_a_lighten_mask_turning_row_by_row(run):
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes(
        textblt.RUNS[run], style=LIGHTEN, extra=vdi.linea_pokes(LITEMASK=ASYMMETRIC_LITEMASK)))


def test_a_wide_row_with_no_shift():
    """The glyph's first pixel on the same bit as the screen's: a shift of 0 is a RIGHT shift ($fd2272 `bpl`)."""
    source_x, _width = vdi_text.glyph("8x16", ord("a"))
    x = textblt.RUNS["right, wide"][0] // vdi.PIXELS_PER_GROUP * vdi.PIXELS_PER_GROUP + source_x % vdi.PIXELS_PER_GROUP
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes((x, 0, 40), style=THICKEN))


@pytest.mark.parametrize("chup", (*vdi_text.ROTATIONS[1:], 450))
@pytest.mark.parametrize("effect", (0, THICKEN | SKEW, OUTLINE, LIGHTEN))
def test_rotation(chup, effect):
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt_pokes("8x16", ord("F"), x=150, y=120, chup=chup,
                                                                       style=effect))


@pytest.mark.parametrize("requested", (4, 12, 24, 32))
@pytest.mark.parametrize("font", textblt.FONTS)
def test_scaling(requested, font):
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt_pokes(font, ord("Q"), x=140, y=110, scale=requested,
                                                                       style=THICKEN))


@pytest.mark.parametrize("place", textblt.PLACES.values(), ids=textblt.PLACES.keys())
def test_clipping(place):
    x, y = place
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt_pokes("8x16", ord("H"), x=x, y=y, style=SKEW,
                                                                       window=vdi_text.TIGHT))


def inside_the_tables(modes):
    """The modes whose every table read `text_raster.S` holds to the ROM's (`vdi_text.LAST_MODE_INSIDE_THE_TABLES`)."""
    return [stray for stray in modes if stray[0] <= vdi_text.LAST_MODE_INSIDE_THE_TABLES]


@pytest.mark.parametrize("stray", inside_the_tables(vdi_text.stray_modes()), ids=str)
def test_a_write_mode_past_19(stray):
    mode, colour, background = stray
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes(
        textblt.RUNS["right, wide"], mode=mode, colour=colour, background=background,
        extra=vdi_raster.geometry_pokes(vdi_raster.HIGH)))


@pytest.mark.parametrize("stray", inside_the_tables(vdi_text.masked_only_modes()), ids=str)
def test_a_write_mode_past_19_whose_masked_slot_alone_is_an_op(stray):
    """...among them the three past 63 (465, 492, 504), whose index's high byte walks the tables through
    TextBlt's own code."""
    mode, colour, background = stray
    vdi_text.run_transcription("LINEA_ROM_CPU_TEXTBLT", textblt.run_pokes(
        textblt.RUNS["two words"], mode=mode, colour=colour, background=background,
        extra=vdi_raster.geometry_pokes(vdi_raster.HIGH)))


@pytest.mark.parametrize("x", (96, 104, 0))
@pytest.mark.parametrize("mode", vdi_text.MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_fast_text(x, mode, colour):
    pokes = vdi_text.fast_text_pokes(fast.TEXT, x=x, mode=mode, colour=colour, window=None)
    vdi_text.run_transcription("LINEA_ROM_FAST_TEXT", pokes)
    vdi_text.run_transcription("LINEA_ROM_CPU_FAST_TEXT", pokes, vdi_text.fast_body_registers(pokes))


@pytest.mark.parametrize("place", fast.PLACES.values(), ids=fast.PLACES.keys())
def test_fast_text_refusals(place):
    x, y, _drawn = place
    vdi_text.run_transcription("LINEA_ROM_FAST_TEXT", vdi_text.fast_text_pokes("AB", x=x, y=y, window=vdi_text.TIGHT))
