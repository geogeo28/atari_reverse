"""What the arc and rounded-box batteries share (`src/vdi/arcs.c`): the Alcyon signatures, the call door (with the
caller's registers), and the machine AS vdi_gdp's ARMS LEAVE IT for each worker.

THE ALCYON CALLS — clc_pts, clc_arc, gdp_arc, gdp_ell, gdp_rbox — are entered by `jsr`, their one signature
declared here (`vdi.declare_alcyon`); only clc_pts has a frame argument (its ptsin word index). `run_call` is
`vdi_fill.run_call`'s door with the ORACLE's entry registers added, because gdp_rbox sorts the box through its
caller's A5 (`vdi/arcs.h`): vdi_gdp loads it from LINEA_PTSIN at $fcbbe0, so every rounded-box case enters with
A5 = the PTSIN it stages (`RBOX_REGISTERS`), and Tier 3 prices the row with the same register.

WHAT EACH ARM LEAVES ($fcbc0a..$fcbd60), which is what a case stages — the call's arrays DISPATCHED
(`vdi.function_pokes` over a dispatched workstation), contrl[5] the GDP number, and:
  * arc / pie (2, 3) and the elliptical ones (6, 7): nothing more — gdp_arc / gdp_ell read intin and ptsin;
  * circle (4): XC, YC = ptsin[0..1], XRAD = ptsin[4], YRAD = smul_div(XRAD, DEV_TAB[3], DEV_TAB[4]), DEL_ANG 3600,
    BEG_ANG 0, END_ANG 3600, then clc_nsteps — and clc_arc (`circle_arm_pokes`, not `vdi_lines.circle_pokes`,
    which is wline's quarter circle);
  * ellipse (5): XC, YC, XRAD, YRAD = ptsin[0..3] (YRAD from the last row in normalised coordinates), DEL_ANG
    3600, BEG_ANG 0, END_ANG 0, clc_nsteps, clc_arc (`ellipse_pokes`);
  * rounded box (8): WS_LINE_BEG and WS_LINE_END cleared round the call, which the case stages as cleared; the
    filled one (9): nothing more.

THE TWO WORDS BELOW THE LINE-A BLOCK (LINEA_GDP_ANGLE, LINEA_GDP_BEG_ANG at $260c) are declared to the snapshot's
case fields here: `vdi.py` declares the block from LINEA_CUR_FONT up.
"""
import sys
from pathlib import Path

from harness import _lib, addrs

import case
import routines
import vdi
import vdi_fill
import vdi_lines
import vdi_raster
from case import merge_pokes
from vdi import IMAGE_ARG, WORD_ARG, WORD_BYTES

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/arcs.h",
                     known={**addrs.ADDRS, **vdi.CONSTANTS})
sys.modules[__name__].__dict__.update(HEADER)
HELPERS = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/helpers.h",
                      known={**addrs.ADDRS, **vdi.CONSTANTS})
TURN = HELPERS["VDI_TENTHS_PER_TURN"]

vdi.declare_alcyon("VDI_ROM_CLC_PTS", None, (IMAGE_ARG, WORD_ARG))
for _name in ("VDI_ROM_CLC_ARC", "VDI_ROM_GDP_ARC", "VDI_ROM_GDP_ELL", "VDI_ROM_GDP_RBOX"):
    vdi.declare_alcyon(_name, None, (IMAGE_ARG,))

_BELOW_THE_BLOCK = vdi.field("LINEA", "GDP_ANGLE").at
assert vdi.field("LINEA", "GDP_BEG_ANG").at == _BELOW_THE_BLOCK + WORD_BYTES == vdi.LINEA_CUR_FONT - WORD_BYTES
vdi.declare_case_field(_BELOW_THE_BLOCK, 2 * WORD_BYTES, "the arc scratch's two words below LINEA_CUR_FONT")

# vdi_gdp's A5 at every arm: the PTSIN the case stages (the entry's copy, `vdi.call_pokes`' default).
RBOX_REGISTERS = {"a5": vdi.VDI_PTSIN_COPY}

# A curve's discs and fills take more than the differential's default budget.
ARC_INSNS = vdi_lines.LINE_INSNS


def run_call(name, arguments, pokes, *, regs=None, **kwargs):
    """The Alcyon routine `addrs.<name>` entered by `jsr` over its frame, the oracle's registers `regs` staged,
    against its core called with the same `arguments`. Answers a `vdi.Result`."""
    core = getattr(_lib, routines.core_symbol(name))
    arguments = vdi_fill.as_signed(name, arguments)
    staged = merge_pokes(pokes, vdi_fill.frame(name, *arguments))
    info = case.run(getattr(addrs, name), {**(regs or {}), "_pokes": staged}, lambda _lib_, buf: core(buf, *arguments),
                    width=case.NO_RESULT, **{"max_insns": ARC_INSNS, **kwargs})
    return vdi.Result(info, staged)


def register_call(label, name, arguments, pokes, *, regs=None):
    """One Tier 3 row of an Alcyon call, staged as `run_call` stages it."""
    vdi.register(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name),
                 merge_pokes(pokes, vdi_fill.frame(name, *arguments)), regs=regs)


# ---- the attributes: the line fields v_pline / polyline / wline read, and the fill fields plygn reads -------
def workstation(*, pattern="8 rows", fill_colour=0b1001, perimeter=0, onto=None, **line):
    """The physical workstation, dispatched over the canvas: `vdi_lines.line_workstation`'s line fields (so
    `width`, `colour`, `index`, `begin`, `end`, `mode`, `clip`), and a fill pattern, colour and perimeter."""
    patptr, patmsk = vdi_raster.PATTERNS[pattern]
    return vdi_lines.line_workstation(onto=onto, PATPTR=patptr, PATMSK=patmsk, FILL_COLOR=fill_colour,
                                      FILL_PER=perimeter, **line)


def gdp_pokes(gdp, work, *, intin=(), ptsin=()):
    """vdi_gdp's call of GDP `gdp` as the dispatcher leaves it: contrl[5] = `gdp`, the arrays, `work`."""
    return vdi.function_pokes("VDI_ROM_GDP", intin=intin, ptsin=ptsin, subfunction=gdp, workstation_pokes=work)


# ---- the arms' own staging of the arc scratch (circle and ellipse call clc_arc themselves) ----------------
def _is_signed_word(value):
    return vdi.signed_word(value & 0xFFFF) == value


def smul_div(multiplicand, multiplier, divisor):
    """$fca186 where it is exact — non-negative factors, a positive divisor, a quotient that fits a word: the product
    over the divisor, a half rounded up. Outside that the ROM rounds a negative remainder its own way
    (`test_vdi_helpers_arithmetic`), so an operand there is refused rather than staged as a value no arm leaves."""
    product = multiplicand * multiplier
    assert multiplicand >= 0 and multiplier >= 0 and divisor > 0, (multiplicand, multiplier, divisor)
    quotient = (2 * product + divisor) // (2 * divisor)
    assert _is_signed_word(quotient), (multiplicand, multiplier, divisor)
    return quotient


def n_steps(xrad, yrad):
    """$fcc6b4: a quarter of the larger radius (`asr.w`), held to 32..128 — for radii that are signed words, as
    the ROM compares them (a radius past 32767 is negative to it)."""
    assert _is_signed_word(xrad) and _is_signed_word(yrad), (xrad, yrad)
    return min(max(max(xrad, yrad) >> 2, 32), 128)


PIXEL_WIDTH, PIXEL_HEIGHT = vdi_lines.ASPECTS["low"]


def scratch_pokes(xc, yc, xrad, yrad, begin, end, sweep):
    """The arc scratch as an arm leaves it for clc_arc: centre, radii, the three angles, and N_STEPS."""
    return vdi.linea_pokes(GDP_XC=xc, GDP_YC=yc, GDP_XRAD=xrad, GDP_YRAD=yrad, GDP_BEG_ANG=begin,
                           GDP_END_ANG=end, GDP_DEL_ANG=sweep, GDP_N_STEPS=n_steps(xrad, yrad))


def circle_call(xc, yc, radius, work):
    """GDP 4 as a caller makes it: the centre and, as the third point's x, the radius."""
    return gdp_pokes(VDI_GDP_CIRCLE, work, ptsin=(xc, yc, 0, 0, radius, 0))


def circle_arm_pokes(xc, yc, radius, work):
    """vdi_gdp's circle arm (GDP 4) up to its `bsr clc_arc` ($fcbc70..$fcbcc0): the call, and the scratch it makes."""
    yrad = smul_div(radius, PIXEL_WIDTH, PIXEL_HEIGHT)
    return merge_pokes(circle_call(xc, yc, radius, work), scratch_pokes(xc, yc, radius, yrad, 0, TURN, TURN))


def ellipse_call(xc, yc, xrad, yrad, work):
    """GDP 5 as a caller makes it: the centre and the two radii."""
    return gdp_pokes(VDI_GDP_ELLIPSE, work, ptsin=(xc, yc, xrad, yrad))


def ellipse_pokes(xc, yc, xrad, yrad, work):
    """vdi_gdp's ellipse arm (GDP 5) up to its `bsr clc_arc` ($fcbcc8..$fcbd18), in raster coordinates: the call, and
    the scratch it makes."""
    return merge_pokes(ellipse_call(xc, yc, xrad, yrad, work), scratch_pokes(xc, yc, xrad, yrad, 0, 0, TURN))


def rbox_work(*, outlined=True, **fields):
    """The workstation for a rounded box: for the outlined one (8) the line ends vdi_gdp clears ($fcbd24)."""
    if outlined:
        fields.update(begin="square", end="square")
    return workstation(**fields)


def rbox_pokes(corners, *, outlined=True, **fields):
    """vdi_gdp's rounded-box arm: `corners` (x0, y0, x1, y1) as the caller passed them, unsorted."""
    return gdp_pokes(VDI_GDP_ROUNDED_BOX if outlined else VDI_GDP_FILLED_ROUNDED_BOX,
                     rbox_work(outlined=outlined, **fields), ptsin=corners)
