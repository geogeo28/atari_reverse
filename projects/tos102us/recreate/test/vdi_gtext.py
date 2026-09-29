"""What the GRAPHIC TEXT batteries share (`src/vdi/gtext.c`): the fonts a string is drawn in, the machine a
v_gtext call is staged over, d_justified's Alcyon signature, and the two GAP records it leaves for v_gtext.

THE FONTS ARE REAL. The three ROM fonts where the ROM has them, and in the text layer's font band
(`vdi_text_c`) the RAM copies a GDOS set would add: a proportional face with a HOR table, the 8x8 from
character 32 (so a control character is missing and drawn as '?'), and the 8x8 over every character 0..$ffff
with a HOR table 32 KB above a staged entry — the face that indexes both tables SIGN-EXTENDED. v_gtext reads
its HOR table ONE BYTE A GLYPH, where vqt_width reads a (left, right) pair — the proportional face's table is
the same bytes either way.

THE MACHINE is the physical workstation DISPATCHED (`vdi.dispatched_pokes`) with the font, effects, alignment,
rotation, scaling, clip, colour and write mode in its record, over a canvas whose every plane differs
(`vdi_raster.CANVAS`) and a stale effects buffer (`vdi_text.SCRATCH`). The Line-A variables v_gtext writes
before anything reads them are staged STALE, and the attribution pass is off (`vdi_text.TEXTBLT_UNPOISONED`:
TextBlt writes its own inputs back, so the pass would hand both shores a glyph 65,000 rows high).
"""
import vdi
import vdi_fill
import vdi_helpers
import vdi_raster
import vdi_text
import vdi_text_c as text
from harness import BASE_IMAGE, addrs
from pathlib import Path
from vdi import IMAGE_ARG, WORD_BYTES
from vdi_text import font_field
from vdi_text_c import header_at, proportional_font, rom_header_pokes

vdi.declare_alcyon("VDI_ROM_D_JUSTIFIED", None, (IMAGE_ARG,))

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/gtext.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
GAPS = {"space": HEADER["VDI_GAP_AFTER_SPACE"], "character": HEADER["VDI_GAP_AFTER_CHARACTER"]}
GAP_FIELDS = ("STEP_X", "STEP_Y", "EXTRA", "EXTRA_X", "EXTRA_Y")
MISSING = HEADER["VDI_TEXT_MISSING_CHARACTER"]
SPACE = HEADER["VDI_TEXT_SPACE"]
GTEXT_OPCODE = addrs.VDI_ROM_V_GTEXT_OPCODE
JUSTIFIED_OPCODE = addrs.VDI_ROM_GDP_OPCODE

THICKEN, LIGHTEN, SKEW, OUTLINE = (vdi.VDI_STYLE_THICKEN_MASK, vdi.VDI_STYLE_LIGHTEN_MASK, vdi.VDI_STYLE_SKEW_MASK,
                                   vdi.VDI_STYLE_OUTLINE_MASK)
UNDERLINE = vdi.VDI_STYLE_UNDERLINE_MASK
ALL_EFFECTS = THICKEN | LIGHTEN | SKEW | OUTLINE | UNDERLINE
ROTATIONS = vdi_text.ROTATIONS

# ---- the fonts ---------------------------------------------------------------------------------------------
PROPORTIONAL = header_at(4)
FIRST_32 = header_at(5)
WRAPPING = header_at(6)
THICK_UNDERLINE = header_at(7)       # the 8x16 with a three-row underline: the only kind that shifts LN_MASK twice
THICK_UNDERLINE_ROWS = 3
DEEP = header_at(9)                  # the 8x16 with a bottom line below its descent, as GDOS faces have one
DEEP_BOTTOM = 4
FONTS = {**vdi_text.FONTS, "ram 8x8": vdi.FONT_RAM_8X8, "proportional": PROPORTIONAL, "first 32": FIRST_32,
         "wrapping": WRAPPING, "thick underline": THICK_UNDERLINE, "deep": DEEP}
WRAPPED_HOR_BYTES = bytes([0x85, 0x06])        # the byte 32 KB below WRAPPING's HOR table, and the next
FONT_POKES = vdi.merge_pokes(
    proportional_font(PROPORTIONAL),
    rom_header_pokes(FIRST_32, "8x8", FIRST_ADE=32, OFF_TABLE=font_field("8x8", "OFF_TABLE") + 32 * WORD_BYTES),
    rom_header_pokes(WRAPPING, "8x8", FIRST_ADE=0, LAST_ADE=0xFFFF, HOR_TABLE=text.WRAPPED_HOR_TABLE,
                     FLAGS=font_field("8x8", "FLAGS") | vdi.FONT_FLAG_HOR_TABLE_MASK),
    {text.WRAPPED_HOR_ENTRY_AT: WRAPPED_HOR_BYTES},
    rom_header_pokes(THICK_UNDERLINE, "8x16", UL_SIZE=THICK_UNDERLINE_ROWS),
    rom_header_pokes(DEEP, "8x16", BOTTOM=DEEP_BOTTOM))
FONT_IMAGE = vdi.make_image(FONT_POKES)
# The ROM font each staged one is a copy of — whose form, and so whose height, it draws with.
BASE_FONT = {**{name: name for name in vdi_text.FONTS}, "ram 8x8": "8x8", "proportional": "8x8", "first 32": "8x8",
             "wrapping": "8x8", "thick underline": "8x16", "deep": "8x16"}


def font_word(font, name):
    """A field of `font` (a FONTS name) as the case stages it."""
    return vdi.read_field(FONT_IMAGE, "FONT", name, FONTS[font])


# ---- the stale Line-A words v_gtext writes before any reader ----------------------------------------------
# WEIGHT stale at a weight a previous bold face would leave, not $5a5a. TextBlt reads WEIGHT only under the bold
# bit, which v_gtext stores it under first, so no correct run reads the stale word; a mutant that skips the store
# does, and a bold of 3 then DIFFERS (a red), where one of 23,130 pixels is past the effects buffer — the ROM
# writing over its own RAM, the host refusing it by name (TextBlt's scratch bound): a halt, not a red.
STALE_WEIGHT = 3
STALE_LINEA = vdi.linea_pokes(**{name: vdi.STALE_WORD for name in (
    "LITEMASK", "L_OFF", "R_OFF", "SKEWMASK", "FWIDTH", "TEXT_FG", "DELY", "SOURCEX", "SOURCEY", "DELX",
    "XACC_DDA", "X1", "Y1", "X2", "Y2", "LN_MASK", "COLBIT0", "COLBIT1", "COLBIT2", "COLBIT3")},
    FBASE=vdi.STALE_LONG, WEIGHT=STALE_WEIGHT)
# Where the last text stopped: what a rotation that is not a right angle draws from.
LAST_TEXT_END = (133, 97)
STALE_EXTENT = {vdi.VDI_EXTENT_SCRATCH: vdi.pack_words(vdi.STALE_WORD, vdi.STALE_WORD)}
POINTS_ANSWERED = vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT

# The clip rectangles (xmin, ymin, xmax, ymax): the snapshot's desktop window, and a tight one a string crosses.
WINDOW = vdi_text.WINDOW
TIGHT = vdi_text.TIGHT


def scale_record(font, requested):
    """SCALED, DDA_INC and T_SCLSTS as vst_height leaves them for `font` drawn `requested` high — the DDA out of
    the reconstructed clc_dda (`vdi_text.scale_pokes`) — or the doubling marker for `requested` "double"."""
    if requested == "double":
        return dict(SCALED=1, DDA_INC=vdi_helpers.VDI_DDA_DOUBLE, T_SCLSTS=vdi_helpers.VDI_SCALE_UP)
    image = vdi.make_image(vdi_text.scale_pokes(font, requested))
    return dict(SCALED=1, DDA_INC=vdi.linea(image, "DDA_INC"), T_SCLSTS=vdi.linea(image, "T_SCLSTS"))


def machine(font="8x16", *, style=0, rotation=0, h_align=0, v_align=0, scale=None, colour=0b1010, mode="replace",
            window=WINDOW, virtual=None, onto=None):
    """The physical workstation dispatched with the text attributes — or a virtual one, `virtual` its handle —
    over the fonts, the canvas, the stale effects buffer and the stale Line-A words."""
    record = dict(CUR_FONT=FONTS[font], STYLE=style, CHUP=rotation, H_ALIGN=h_align, V_ALIGN=v_align,
                  TEXT_COLOR=colour, WRT_MODE=vdi_text.mode_number(mode), SCALED=0, **vdi_fill.clip_values(window))
    if scale is not None:
        record.update(scale_record(BASE_FONT[font], scale))
    staged = vdi.merge_pokes(FONT_POKES, vdi_raster.CANVAS, vdi_text.SCRATCH, STALE_LINEA, STALE_EXTENT,
                             vdi.linea_pokes(DESTX=LAST_TEXT_END[0], DESTY=LAST_TEXT_END[1]), onto)
    if virtual is not None:
        return vdi.virtual_workstation(virtual, onto=staged, **record)
    return vdi.dispatched_pokes(onto=staged, **record)


def gtext_call(string, x=101, y=60, **attributes):
    """v_gtext of `string` (characters or codes) at (x, y) over `machine(**attributes)`."""
    return vdi.function_pokes("VDI_ROM_V_GTEXT", intin=vdi_text.codes(string), ptsin=(x, y),
                              workstation_pokes=machine(**attributes))


def run_gtext(pokes):
    return vdi.run_function("VDI_ROM_V_GTEXT", pokes, **vdi_text.TEXTBLT_UNPOISONED)


# ---- the gaps d_justified leaves ------------------------------------------------------------------------------
def gap_pokes(kind, **fields):
    """A GAP record's words by field — the rest stale."""
    at = GAPS[kind]
    words = [fields.get(name, vdi.STALE_WORD) for name in GAP_FIELDS]
    return {at: vdi.pack_words(*words)}


def gap(result, kind):
    """A GAP record back out of a run, as signed words by field."""
    return dict(zip(GAP_FIELDS, map(vdi.signed_word, result.words(GAPS[kind], len(GAP_FIELDS)))))


STALE_GAPS = vdi.merge_pokes(gap_pokes("space"), gap_pokes("character"))


def screen_changed(result, staged_image=vdi_raster.CANVAS_IMAGE):
    """Whether the run drew anything at all — a text case that draws nothing proves nothing about glyphs."""
    screen = vdi.SCREEN
    return bytes(result.final[screen.base:screen.base + screen.bytes]) != \
        bytes(staged_image[screen.base:screen.base + screen.bytes])


def assert_dead_in_the_snapshot():
    text.assert_dead_in_the_snapshot()
    assert BASE_IMAGE[text.WRAPPED_HOR_ENTRY_AT:text.WRAPPED_HOR_ENTRY_AT + 2] == bytes(2)


# ---- d_justified: GDP 10, as the GDP's arm `jsr`s it -----------------------------------------------------------
JUSTIFIED_SUBFUNCTION = 10           # the GDP's arm that calls it ($fcbd56, the switch table's tenth entry)


def justified_call(string, length, *, words=1, characters=0, x=20, y=60, **attributes):
    """GDP 10 of `string` spread to `length` pixels at (x, y): intin[0] the word flag, intin[1] the character
    flag, then the text; ptsin[2] the length — over `machine(**attributes)` with STALE gap records."""
    pokes = vdi.call_pokes(JUSTIFIED_OPCODE, intin=(words, characters, *vdi_text.codes(string)), ptsin=(x, y, length, 0),
                           subfunction=JUSTIFIED_SUBFUNCTION, workstation_pokes=machine(**attributes))
    return vdi.merge_pokes(pokes, STALE_GAPS)


def run_justified(pokes):
    """d_justified entered by `jsr` as GDP 10 does, against its core — unpoisoned for v_gtext's TextBlt, and for
    INTIN, which it moves past the flags and puts back (`vdi.READS_A_POINTER_IT_WRITES`)."""
    return vdi_helpers.run_call("VDI_ROM_D_JUSTIFIED", {}, (), pokes, **vdi.READS_A_POINTER_IT_WRITES)
