"""The VDI's array pointers on the 24-bit bus: a `trap #2` parameter block whose five pointers carry a TOP BYTE.

A program hands the VDI longwords, and the 68000 drives 24 bits of each: the entry stores the pointers as they
came (`src/vdi/entry.c`), and every function then reads its arguments and stores its answers through them —
the accessors of `include/vdi/vdi.h` (`contrl_word`, `intin_word`, `ptsin_word`, `answer_intout`, …), which add
the field's offset FIRST and only then put the sum on the bus, as the 68000's `d16(An)` does
(`bus_dereference`: free on target, where the bus drops the byte itself).

Each case runs one REAL function end to end — the entry, the dispatcher, the function — twice: once with every
pointer of the block clean and once with its top byte set. The machines the two leave are the same but for the
four Line-A pointers the entry stored as given (PTSIN is the entry's own copy either way). A pointer read raw
walks the host out of its image, where the original reads its own RAM.
"""
import pytest

from harness import addrs

import vdi
import vdi_entry
import vdi_lines
from case import merge_pokes

TOP_BYTE = 0xA5 << 24
ARRAYS = {"contrl": vdi.CONTRL_AT, "intin": vdi.INTIN_AT, "ptsin": vdi.PTSIN_AT, "intout": vdi.INTOUT_AT,
          "ptsout": vdi.PTSOUT_AT}
STORED_AS_GIVEN = ("CONTRL", "INTIN", "INTOUT", "PTSOUT")
HEIGHT, PLINE, INPUT_MODE = "VDI_ROM_VSM_HEIGHT", "VDI_ROM_V_PLINE", "VDI_ROM_VQIN_MODE"
LOCATOR = 1                                     # vqin_mode's first device, one with an arm
PATH = (20, 30, 60, 34, 41, 70)                 # three points, (x, y) flat, one of them a joint


def trapped(name, call, top_byte):
    """`call` (a `vdi.function_pokes` staging, the caller's points at PTSIN_AT) entered through `trap #2`, every
    pointer of the block carrying `top_byte`."""
    block = vdi_entry.block_pokes(**{array: top_byte | at for array, at in ARRAYS.items()})
    staged = merge_pokes(vdi_entry.over_a_call(call), vdi_entry.stale_entry(), block)
    result, calls = vdi_entry.run_entry(staged, vdi_entry.function(name), max_insns=vdi_lines.LINE_INSNS)
    assert calls == [getattr(addrs, name)]
    return result


def outside_the_pointers(final, pointers=STORED_AS_GIVEN):
    """The machine a run left, less where the pointers themselves are: the block the case staged, the Line-A
    pointers the entry stores as given, and the stack band (the registers the ROM saves hold them)."""
    image = bytearray(final)
    spans = [(vdi.PARAMETER_BLOCK_AT, vdi.PB_BYTES), (vdi.emu.STACK_GUARD_LO, vdi.emu.STACK_BAND_HI - vdi.emu.STACK_GUARD_LO)]
    spans += [(vdi.field("LINEA", name).at, vdi.field("LINEA", name).width) for name in pointers]
    for at, size in spans:
        image[at:at + size] = bytes(size)
    return bytes(image)


def polyline(workstation):
    return vdi.function_pokes(PLINE, ptsin=PATH, workstation_pokes=workstation, ptsin_at=vdi.PTSIN_AT)


CALLS = {
    "vsm_height": (HEIGHT, lambda: vdi.function_pokes(HEIGHT, ptsin=(0, 11), ptsin_at=vdi.PTSIN_AT)),
    "v_pline, one pixel wide": (PLINE, lambda: polyline(vdi_lines.line_workstation())),
    "v_pline, wide (wline)": (PLINE, lambda: polyline(vdi_lines.line_workstation(width=5))),
    "vqin_mode, the locator": (INPUT_MODE, lambda: vdi.function_pokes(INPUT_MODE, (LOCATOR,), ptsin_at=vdi.PTSIN_AT)),
}


@pytest.mark.parametrize("label", tuple(CALLS))
def test_a_top_byte_on_every_pointer_reaches_the_same_arrays(label):
    name, call = CALLS[label]
    staged = call()
    clean, dirty = trapped(name, staged, 0), trapped(name, staged, TOP_BYTE)
    assert [dirty.linea(variable) for variable in STORED_AS_GIVEN] == [
        TOP_BYTE | ARRAYS[variable.lower()] for variable in STORED_AS_GIVEN], "stored as given"
    assert outside_the_pointers(dirty.final) == outside_the_pointers(clean.final), label


# ---- ...and a function entered as the dispatcher leaves it, with PTSIN dirty too ------------------------------------
# Through `trap #2` PTSIN is the entry's own copy, always clean; a call the dispatcher did not make (a Line-A
# program's own pointers) can hand it a top byte as well — which is what reaches wline's walk over the caller's points.
DIRECT = ("vsm_height", "v_pline, wide (wline)", "vqin_mode, the locator")


def direct(name, call, top_byte):
    pointers = {variable: top_byte | at for variable, at in zip(vdi.POINTER_VARIABLES, ARRAYS.values())}
    return vdi.run_function(name, merge_pokes(call, vdi.linea_pokes(**pointers)), max_insns=vdi_lines.LINE_INSNS)


@pytest.mark.parametrize("label", DIRECT)
def test_a_top_byte_on_every_line_a_pointer_reaches_the_same_arrays(label):
    name, call = CALLS[label]
    staged = call()
    clean, dirty = direct(name, staged, 0), direct(name, staged, TOP_BYTE)
    every = vdi.POINTER_VARIABLES
    assert outside_the_pointers(dirty.final, every) == outside_the_pointers(clean.final, every), label
