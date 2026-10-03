"""THE STORE ABOVE RAM, REFUSED BY NAME (`include/m68k_idioms.h`, `ram_store`): every host store the bound guards, run
once with its address at the top of RAM, in a child — refused by name, where the oracle drops the store and an ST loses
it or takes a bus error. The set_bus_* family is pinned by fm_strbrk's own cases (`test_aes_fmlib.py`); here, one case
per OTHER guarded site, so a site that lost its guard is red. ONE SITE HAS NO CASE OF ITS OWN: the sprite draw's
screen-word store (`SPRITE_SAVE_ADDR`, +2..+5 of the save block) can reach the top of RAM only with the block's status
byte (+6) above it too, and the status is stored first on every path — its guard refuses there.
"""
import signal
import struct

import pytest

from harness import addrs
import aes
import aes_resource as rs
import routines
import test_aes_fmlib as fmlib
import vdi
import vdi_arcs
import vdi_helpers
import vdi_mouse as mouse
from case import merge_pokes

TOP = addrs.ST_RAM_BYTES                # the first byte above RAM
LONG_ROWS = 1 << mouse.MOUSE_H["SPRITE_SAVE_LONG_BIT"]
VALID = 1 << mouse.MOUSE_H["SPRITE_SAVE_VALID_BIT"]
SPRITE_AT = (160, 100)                  # the middle of the low-resolution screen: the form spread over both groups
SPRITE_CLIPPED_LEFT = (3, 8)            # ...and clipped at the left edge: one group a row


def _long_at(at, value):
    return {at: struct.pack(">I", value)}


def _arguments(*values):
    return tuple(("ctypes.c_uint32", hex(value)) for value in values)


def _vsl(name, **pointers):
    """vsl_type / vsl_width over the physical workstation, the Line-A `pointers` moved."""
    staged = vdi.function_pokes(name, intin=(1,), ptsin=(3, 0))
    return routines.core_symbol(name), merge_pokes(staged, vdi.linea_pokes(**pointers)), ()


def _sprite_drawn(save_block, where, **linea):
    pokes = merge_pokes(mouse.canvas_pokes(), mouse.form_pokes(), vdi.linea_pokes(**linea))
    return "linea_draw_sprite", pokes, _arguments(mouse.FORM_AT, save_block, *where)


def _sprite_restored(status):
    """A save block holding one row saved from the top of RAM, `status` its STAT byte, restored on ONE plane (the
    layout whose two-word rows are moved as a long)."""
    block = (vdi.pack_words(1) + struct.pack(">I", TOP) + bytes([status, 0])
             + bytes(vdi.LINEA_SAVE_BLOCK_BYTES - mouse.SAVE_AREA))
    pokes = merge_pokes(mouse.canvas_pokes(), vdi.linea_pokes(PLANES=1), {mouse.SAVE_BLOCK_AT: block})
    return "linea_undraw_sprite", pokes, _arguments(mouse.SAVE_BLOCK_AT)


def _rounded_box_outlined():
    """The outlined rounded box over a current workstation record ending at the top of RAM: the line-start style,
    cleared for the call, the first store into it (`set_work_word`)."""
    staged = vdi.function_pokes("VDI_ROM_GDP", subfunction=vdi_arcs.VDI_GDP_ROUNDED_BOX, ptsin=(10, 10, 50, 40))
    return routines.core_symbol("VDI_ROM_GDP"), merge_pokes(staged, vdi.linea_pokes(CUR_WORK=TOP - vdi.WS_LINE_BEG)), ()


# v_clsvwk's unlink: the current record (a virtual one, handle 2) follows a record whose WS_NEXT straddles the top of
# RAM — its high word the current one's (a record on a 64 KB boundary, so the word above RAM the oracle reads as 0 is
# its low word): the walk finds it, and the store that relinks it is the first above RAM (`set_work_long`).
VIRTUAL_RECORD_AT = 0x80000
STRADDLING_RECORD_AT = TOP - aes.WORD_BYTES - vdi.WS_NEXT
VIRTUAL_HANDLE = 2


def _virtual_closed():
    staged = merge_pokes(vdi.function_pokes("VDI_ROM_V_CLSVWK"), vdi.linea_pokes(CUR_WORK=VIRTUAL_RECORD_AT),
                         {VIRTUAL_RECORD_AT + vdi.WS_HANDLE: struct.pack(">H", VIRTUAL_HANDLE)},
                         _long_at(vdi.VDI_PHYS_WORK + vdi.WS_NEXT, STRADDLING_RECORD_AT),
                         {STRADDLING_RECORD_AT + vdi.WS_NEXT: struct.pack(">H", VIRTUAL_RECORD_AT >> 16)})
    return routines.core_symbol("VDI_ROM_V_CLSVWK"), staged, ()


def _font_loaded():
    """vst_load_fonts handed a chain of ONE font whose header ends past the top of RAM: its flags word above it (the
    form not yet swapped, a zero-sized one), so the store that marks it swapped is the first above RAM."""
    font = TOP - vdi.FONT_FLAGS
    staged = vdi.function_pokes("VDI_ROM_VST_LOAD_FONTS")
    chain = _long_at(vdi.CONTRL_AT + vdi.CONTRL_FONT_CHAIN, font)
    header = {font: bytes(vdi.FONT_FLAGS)}
    return routines.core_symbol("VDI_ROM_VST_LOAD_FONTS"), merge_pokes(staged, chain, header), ()


# (the C symbol, its machine, its C arguments): each with ONE store at or above the top of RAM, through the site named.
SITES = {
    "vdi.h answer_intout (vsl_type)": lambda: _vsl("VDI_ROM_VSL_TYPE", INTOUT=TOP),
    "vdi.h answer_ptsout (vsl_width)": lambda: _vsl("VDI_ROM_VSL_WIDTH", PTSOUT=TOP),
    "vdi.h set_contrl_word (vsl_type's count)": lambda: _vsl("VDI_ROM_VSL_TYPE", CONTRL=TOP - vdi.CONTRL_N_INTOUT),
    "vdi.h set_current_work_word (vsl_type's style)": lambda: _vsl("VDI_ROM_VSL_TYPE", CUR_WORK=TOP - vdi.WS_LINE_INDEX),
    "vdi.h set_work_word (the outlined rounded box)": _rounded_box_outlined,
    "vdi.h set_work_long (v_clsvwk's unlink)": _virtual_closed,
    "mouse.c the VBL slot, the cursor on (mouse_init)": lambda: (
        "vdi_mouse_init", _long_at(addrs.SYSVAR_VBLQUEUE, TOP), ()),
    "mouse.c the VBL slot emptied (mouse_off)": lambda: (
        "vdi_mouse_off", _long_at(addrs.SYSVAR_VBLQUEUE, TOP), ()),
    # no plane, so nothing is saved: the status the only store above RAM (the screen word and the length lie below it)
    "mouse.c the sprite's status, drawn": lambda: _sprite_drawn(TOP - mouse.SAVE_STAT, SPRITE_AT, PLANES=0),
    "mouse.c the sprite's status, undrawn": lambda: (
        "linea_undraw_sprite", mouse.canvas_pokes(), _arguments(TOP - mouse.SAVE_STAT)),
    "mouse.c a row saved, both groups (a long)": lambda: _sprite_drawn(TOP - mouse.SAVE_AREA, SPRITE_AT),
    "mouse.c a row saved, one group (poke16)": lambda: _sprite_drawn(TOP - mouse.SAVE_AREA, SPRITE_CLIPPED_LEFT),
    "mouse.c a row restored, two words (a long)": lambda: _sprite_restored(VALID | LONG_ROWS),
    "mouse.c a row restored, one word (poke16)": lambda: _sprite_restored(VALID),
    "text.c a loaded font marked swapped (vst_load_fonts)": _font_loaded,
    "resource.c rs_gaddr's answer": lambda: (
        "aes_rs_gaddr", aes.leaf_machine(onto=rs.STALE_GLOBALS),
        _arguments(rs.DESK_GLOBAL, rs.R_TREE, 1, TOP - aes.WORD_BYTES)),
}


@pytest.mark.parametrize("site", SITES)
def test_a_store_at_the_top_of_ram_is_refused_by_name(site):
    symbol, pokes, arguments = SITES[site]()
    returncode, stderr, _image = vdi_helpers.refusal_over(symbol, pokes, arguments=arguments, read_back=False)
    assert returncode == -signal.SIGABRT and fmlib.TOP_OF_RAM_REFUSAL in stderr.splitlines(), (returncode, stderr)
