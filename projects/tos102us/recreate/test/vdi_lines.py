"""What the polyline and marker batteries share (`src/vdi/lines.c`): the Alcyon signatures, the device aspects,
the quarter circle AS THE ROM BUILDS IT, and the line attributes as the dispatcher leaves them.

THE ALCYON CALLS — cir_dda, wline, perp_off, do_circ, arrow, do_arrow — are entered by `jsr` over their frame
through `vdi_fill.run_call`, the polygon layer's door, which stages the frame from the one signature declared
here (`vdi.declare_alcyon`) and hands the core the same values; `bench/tier3.py` derives their Tier 3 calls
from the same table.

THE QUARTER CIRCLE a disc or a wide segment is drawn from is never spelt by hand: `quarter_circle` runs the
ROM's own cir_dda over the width and aspect a case names and stages what it left — LINEA_Q_CIRCLE,
NUM_QC_LINES and LINE_CW — which is exactly the state wline hands perp_off and do_circ. The snapshot's own
(NUM_QC_LINES 0, LINE_CW -1: nothing has drawn a wide line yet) is the one other state a case starts from.
"""
import functools
import sys
from pathlib import Path

from harness import addrs, emu, make_image

import vdi
import vdi_fill
import vdi_raster
from case import merge_pokes
from vdi import IMAGE_ARG, LONG_ARG, WORD_ARG, WORD_BYTES

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/lines.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
sys.modules[__name__].__dict__.update(HEADER)

for _name, _argtypes in (("VDI_ROM_CIR_DDA", (IMAGE_ARG,)),
                         ("VDI_ROM_WLINE", (IMAGE_ARG,)),
                         ("VDI_ROM_PERP_OFF", (IMAGE_ARG, LONG_ARG, LONG_ARG)),
                         ("VDI_ROM_DO_CIRC", (IMAGE_ARG, WORD_ARG, WORD_ARG)),
                         ("VDI_ROM_ARROW", (IMAGE_ARG,)),
                         ("VDI_ROM_DO_ARROW", (IMAGE_ARG, LONG_ARG, WORD_ARG))):
    vdi.declare_alcyon(_name, None, _argtypes)

register_call = vdi_fill.register_call


# ---- this module's band of the VDI window: perp_off's two words ----------------------------------------
BAND_OFFSET = 0x1C40
BAND_BYTES = 0x20
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_lines.py: the offset perp_off turns in place")
OFFSET_AT = BAND_AT

# ---- the device's aspect: DEV_TAB's pixel width and height in microns, as v_opnwk sets them ($fcb740..) ----
ASPECTS = {"low": (338, 372), "medium": (169, 372), "high": (372, 372)}
PIXEL_SIZE_AT = vdi.LINEA_DEV_TAB + vdi.VDI_DEV_TAB_PIXEL_WIDTH_INDEX * WORD_BYTES
assert vdi.VDI_DEV_TAB_PIXEL_HEIGHT_INDEX == vdi.VDI_DEV_TAB_PIXEL_WIDTH_INDEX + 1


def aspect_pokes(aspect):
    return {PIXEL_SIZE_AT: vdi.pack_words(*ASPECTS[aspect])}


# The widths vsl_width can leave (1..SIZ_TAB[6] = 40, rounded down to odd) and, as staged records, even ones.
WIDEST = 39
QUARTER_CIRCLE_WORDS = vdi.field("LINEA", "Q_CIRCLE").count


@functools.cache
def quarter_circle(width, aspect="low"):
    """`(NUM_QC_LINES, LINE_CW, Q_CIRCLE words)` as the ROM's cir_dda leaves them for `width` in `aspect` —
    run on the oracle alone, the state a caller of perp_off or do_circ finds."""
    staged = merge_pokes(vdi.dispatched_pokes(LINE_WIDTH=width), aspect_pokes(aspect))
    final, _writes, _left = emu.run(make_image(staged), addrs.VDI_ROM_CIR_DDA)
    return (vdi.linea(final, "NUM_QC_LINES"), vdi.linea(final, "LINE_CW"), tuple(vdi.linea(final, "Q_CIRCLE")))


def circle_pokes(width, aspect="low"):
    """The quarter circle for `width` staged, as a wide line of that width leaves it, in `aspect`."""
    rows, built_for, words = quarter_circle(width, aspect)
    return merge_pokes(vdi.linea_pokes(NUM_QC_LINES=rows, LINE_CW=built_for, Q_CIRCLE=words), aspect_pokes(aspect))


# ---- the line attributes, as the dispatcher leaves them --------------------------------------------------
ENDS = {"square": 0, "arrow": 1, "round": 2, "arrow and round bits": 3}


def line_workstation(*, width=1, colour=0b0110, mode="replace", index=0, begin="square", end="square",
                     clip=vdi_fill.DESKTOP_CLIP, onto=None, **values):
    """The physical workstation, dispatched over the canvas, with the line fields v_pline and wline read and
    the fill fields the borrowed outline saves and puts back staged apart from them, so a field not put back
    shows."""
    fields = {"LINE_WIDTH": width, "LINE_COLOR": colour, "LINE_INDEX": index, "LINE_BEG": ENDS.get(begin, begin),
              "LINE_END": ENDS.get(end, end), "WRT_MODE": vdi_raster.MODES[mode], "FILL_COLOR": 0b1001,
              "FILL_PER": 0, **vdi_fill.clip_values(clip)}
    return vdi.dispatched_pokes(onto=merge_pokes(vdi_raster.CANVAS, onto), **{**fields, **values})


def path_pokes(opcode_name, path, workstation, *, count=None):
    """A VDI call of `opcode_name` over `path` [(x, y), ...] as the dispatcher leaves it — contrl[1] =
    `count` (the number of points by default)."""
    flat = [coordinate for point in path for coordinate in point]
    pokes = vdi.function_pokes(opcode_name, ptsin=flat, workstation_pokes=workstation)
    if count is not None:
        pokes = merge_pokes(pokes, {vdi.CONTRL_AT + vdi.CONTRL_N_PTSIN: vdi.pack_words(count)})
    return pokes


# A wide line's discs and quadrilaterals take more than the differential's default budget.
LINE_INSNS = 8_000_000

# THE ATTRIBUTION PASS IS OFF FOR ARROW ALONE — and v_pline's one-pixel path into it: arrow reads LINEA_PTSIN
# again after each do_arrow has put it back, so the poisoned run follows an inverted PTSIN to $ffe625 and reads
# the I/O page; its runs pass `vdi.READS_A_POINTER_IT_WRITES`. What stands in is staging: the canvas is
# pseudo-random and the fill fields s_fa_attr saves are staged apart from the line fields, so a store skipped
# reads as a value no arm produces. Every other routine here runs poisoned. For wline, do_arrow and a wide
# v_pline that pass is nearly vacuous — contrl[1] is an output they also read (left at 5, or put back), its
# inverse is negative, and the poisoned run takes the fewer-than-two-points exit; v_pmarker's still attributes
# its five borrowed fields and its CLIP store, which it makes before the (then empty) loop.


def run_call(name, arguments, pokes, **kwargs):
    """`vdi_fill.run_call`, with this layer's instruction budget."""
    return vdi_fill.run_call(name, arguments, pokes, **{"max_insns": LINE_INSNS, **kwargs})


def run_function(name, pokes, **kwargs):
    return vdi.run_function(name, pokes, **{"max_insns": LINE_INSNS, **kwargs})
