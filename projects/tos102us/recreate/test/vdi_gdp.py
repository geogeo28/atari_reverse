"""What the GDP batteries share (`src/vdi/gdp.c`): vdi_gdp ($fcbbcc, opcode 11) entered as the dispatcher's `jsr`
leaves the machine, over the staging of the workers its arms call.

THE WORKERS' BATTERIES STAGED THE MACHINE AS THE ARMS LEAVE IT (`test/vdi_arcs.py`, `test/vdi_gtext.py`): the arc
scratch the circle and ellipse arms set up, the line ends the outlined rounded box clears, the call's arrays for the
arms that only `jsr`. A case here runs the REAL arm over the same call instead, and `assert_same_machine` holds the
end of that run to the end of the worker's own run from the staged state — so the arm's set-up is pinned by the
differential AND the staging the worker was verified over is proved to be what the arm really leaves.

THE BAR (GDP 1) is vr_recfl over the call's corners and, when WS_FILL_PER is exactly 1, their outline through
polyline in the fill colour vr_recfl left in COLBIT: `bar_pokes` stages the fill fields apart from the line fields,
so an outline drawn in the line colour, or through v_pline, changes bits the ROM left alone.
"""
from pathlib import Path

import harness
from harness import addrs

import case
import routines
import vdi
import vdi_arcs

HEADER = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/gdp.h", known={**addrs.ADDRS, **vdi.CONSTANTS})
VDI_GDP_BAR = HEADER["VDI_GDP_BAR"]
VDI_GDP_JUSTIFIED = HEADER["VDI_GDP_JUSTIFIED"]
VDI_BAR_OUTLINE_POINTS = HEADER["VDI_BAR_OUTLINE_POINTS"]

# The bar's perimeter colour differs from every line colour `vdi_arcs.workstation` stages.
BAR_FILL_COLOUR = 0b1001

# Every arm's worst case draws a curve or a string: the curve workers' budget.
GDP_INSNS = vdi_arcs.ARC_INSNS


def run_gdp(pokes, **kwargs):
    """vdi_gdp over `pokes` (a call staged by `vdi_arcs.gdp_pokes` or one of the builders below)."""
    return vdi.run_function("VDI_ROM_GDP", pokes, **{"max_insns": GDP_INSNS, **kwargs})


def register(label, pokes):
    vdi.register(f"{routines.core_symbol('VDI_ROM_GDP')}, {label}", addrs.VDI_ROM_GDP, pokes)


def bar_pokes(corners, *, perimeter=vdi.VDI_FILL_PERIMETER_ON, pattern="8 rows", colour=BAR_FILL_COLOUR, **line):
    """GDP 1 over `corners` (x0, y0, x1, y1) as the caller passed them, the fill fields and `line`'s line fields
    (`vdi_arcs.workstation`) in the dispatched record."""
    work = vdi_arcs.workstation(pattern=pattern, fill_colour=colour, perimeter=perimeter, **line)
    return vdi_arcs.gdp_pokes(VDI_GDP_BAR, work, ptsin=corners)


def outlined_rbox_pokes(corners, **fields):
    """GDP 8 over the line ends a caller left in the record — which `vdi_arcs.rbox_pokes` stages cleared, as the
    arm leaves them for gdp_rbox."""
    return vdi_arcs.gdp_pokes(vdi_arcs.VDI_GDP_ROUNDED_BOX, vdi_arcs.workstation(**fields), ptsin=corners)


# ---- the arm's end held to the worker's --------------------------------------------------------------
STACK_BAND = case.STACK_BAND


def assert_same_machine(result, reference, *, allowed=()):
    """`result` (vdi_gdp's run) ended in the machine `reference` (the worker's run from the staged state) ended in:
    every byte outside the stack band — whose frames differ by the arm's own — and the `allowed` (lo, hi) spans a
    case names, each for a field the arm writes after its worker returned."""
    def excluded(at):
        return any(lo <= at < hi for lo, hi in allowed)

    # The differential's own spans — the image minus the stack band — and its chunked walk.
    differing = harness.differing_addresses(memoryview(result.final), memoryview(reference.final), harness.diff_spans(),
                                            excluded)
    assert not differing, f"{len(differing)} bytes differ from the worker's run, first at {differing[0]:#x}"


def work_field_span(name, at=vdi.VDI_PHYS_WORK):
    spec = vdi.field("WS", name)
    return at + spec.at, at + spec.at + spec.width


def run_worker(name, pokes, *, regs=None, **kwargs):
    """The worker `addrs.<name>` entered as the arm `jsr`s it, over `pokes` (`vdi_arcs.run_call`)."""
    return vdi_arcs.run_call(name, (), pokes, regs=regs, **kwargs)

