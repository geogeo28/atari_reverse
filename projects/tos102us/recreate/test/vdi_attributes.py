"""The ATTRIBUTE SETTERS' shared staging (`src/vdi/attributes.c`): one call over a dispatched workstation.

Every setter battery (`test_vdi_attr_*.py`) stages the same shape — `vdi.call_pokes` over the physical
workstation or a VIRTUAL one, each dispatched, with the fields the setter is about seeded to a value
no arm of it stores (`STALE`) — so that a store the reconstruction SKIPPED reads as a wrong byte on
the arm whose answer happens to equal what the snapshot held. This module is that shape, once.

WHAT EVERY SETTER IS ALSO HELD TO, by `overlap_cases` below: the ORDER of its stores. The ROM's order
is only visible when the caller's arrays overlap one another or the workstation, so each setter is
also run with intout laid over contrl[4], over the workstation field it sets, and over intin itself.
"""
from harness import BASE_IMAGE, addrs, emu

import case
import routines
import vdi
from case import merge_pokes

# A value no setter stores into any field it sets: every clamp here answers a small index, a pen, a
# width under 41, a multiple of 900 or a pointer into ROM.
STALE = 0x5A5A
A_HANDLE = 7


def work_at(virtual):
    return vdi.VIRTUAL_WORK_AT if virtual else vdi.VDI_PHYS_WORK


def workstation(*, virtual=False, onto=None, **fields):
    """The workstation a setter runs over, dispatched: the physical one, or a virtual one made current
    (`vdi.virtual_workstation`). `onto` stages what the dispatcher's copies READ — a Line-A table a
    setter bounds against is staged there too, so one merge carries both."""
    if virtual:
        return vdi.virtual_workstation(A_HANDLE, onto=onto, **fields)
    return vdi.dispatched_pokes(onto=onto, **fields)


def call(name, intin=(), ptsin=(), *, virtual=False, onto=None, fields=None, pointers=None, linea=None):
    """`addrs.<name>`'s call: its arrays, its workstation dispatched with `fields`, and `linea` —
    Line-A variables laid over the whole, AFTER the dispatcher's copies (a copy staged apart from its
    record is how a case shows a setter leaves the copy alone)."""
    staged = vdi.function_pokes(name, intin, ptsin, pointers=pointers,
                            workstation_pokes=workstation(virtual=virtual, onto=onto, **(fields or {})))
    return merge_pokes(staged, vdi.linea_pokes(**linea)) if linea else staged


def run(name, pokes, **kwargs):
    return vdi.run_function(name, pokes, **kwargs)


def rom_map_col(index):
    """The pen `VDI_MAP_COL` gives colour `index`, out of the ROM itself."""
    return case.word_in(BASE_IMAGE, vdi.VDI_MAP_COL + index * vdi.WORD_BYTES)


def colour_count_pokes(count):
    """DEV_TAB with `count` as its colour count (DEV_TAB[13]), the bound every colour setter reads."""
    table = vdi.linea(BASE_IMAGE, "DEV_TAB")
    table[vdi.VDI_DEV_TAB_COLOURS_INDEX] = count
    return vdi.linea_pokes(DEV_TAB=table)


# The four setters that bound a colour index against that count, and the pen field each stores.
COLOUR_SETTERS = (("VDI_ROM_VSL_COLOR", "LINE_COLOR"), ("VDI_ROM_VSM_COLOR", "MARK_COLOR"),
                  ("VDI_ROM_VSF_COLOR", "FILL_COLOR"), ("VDI_ROM_VST_COLOR", "TEXT_COLOR"))


def writes_outside_the_stack(result):
    """The addresses the ORIGINAL wrote, less its own stack frames."""
    return [at for at in result.info["writes"] if not emu.STACK_GUARD_LO <= at < emu.STACK_BAND_HI]


def assert_physical_untouched(result):
    """A setter run over a VIRTUAL workstation left the physical record alone — which a
    reconstruction writing `VDI_PHYS_WORK` rather than `LINEA_CUR_WORK` would not."""
    stray = [at for at in result.info["writes"] if vdi.VDI_PHYS_WORK <= at < vdi.VDI_PHYS_WORK + vdi.WS_BYTES]
    assert not stray, f"the physical workstation was written at {[hex(at) for at in stray]}"


def register(label, name, pokes):
    """A Tier 3 row for `addrs.<name>`, labelled as the other VDI rows are: `vdi_<fn>, <label>`."""
    return vdi.register(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), pokes)


# ---- the store-order cases every setter shares ------------------------------------------------------
# Where intout is laid: over contrl[4] (the count against the first answer), over intin (the answer
# against an argument read after it — `vsin_mode` reads its device only after echoing its mode), and
# one word into intin (`vst_alignment` reads intin[1] only after answering intout[0]).
OVERLAPS = {
    "intout over contrl[4]": vdi.COUNT_OVERLAP,
    "intout over intin": vdi.INTIN_AT,
    "intout over intin[1]": vdi.INTIN_AT + vdi.WORD_BYTES,
}


def overlap_cases(name, field, intin, ptsin=()):
    """`(label, pokes)` for `addrs.<name>` with intout laid over each of `OVERLAPS` and over the
    workstation's `field` (the answer against the store, whichever the ROM makes first — visible only
    where the two values differ: an index answered and its PEN stored; where a setter answers the very
    word it stores, the order is not a fact any machine state can show). The
    differential is the claim: both shores run the same overlap, and only one order leaves each."""
    base = call(name, intin, ptsin, fields={field: STALE})
    spots = {**OVERLAPS, f"intout over WS_{field}": vdi.VDI_PHYS_WORK + vdi.field("WS", field).at}
    return [(label, vdi.intout_over(base, at)) for label, at in spots.items()]


def point_overlap_cases(name, field, ptsin):
    """...and for a setter that answers a POINT (vsl_width, vsm_height): ptsout laid over contrl[2] (the
    point count against the first coordinate), and over the workstation's `field` with each of its two
    words — the second is what shows the store against the answer where the first answers the value
    stored."""
    base = call(name, ptsin=ptsin, fields={field: STALE})
    field_at = vdi.VDI_PHYS_WORK + vdi.field("WS", field).at
    spots = {"ptsout over contrl[2]": vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT,
             f"ptsout over WS_{field}": field_at,
             f"ptsout[1] over WS_{field}": field_at - vdi.WORD_BYTES}
    return [(label, merge_pokes(base, vdi.linea_pokes(PTSOUT=at))) for label, at in spots.items()]
