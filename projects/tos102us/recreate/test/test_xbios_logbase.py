"""XBIOS Logbase (function 3) @ $fc0aa6 — where the VDI and the console are drawing.

One instruction and a return, and the case is about its input: `_v_bas_ad` at $044e, the LOGICAL
screen base. Its sibling `Physbase` ($fc0a92) asks the shifter instead of RAM and is therefore out
of ROM mode's reach — which is the whole reason this one has a row and that one does not.

On the snapshot the two agree (`_v_bas_ad` == `_memtop`, the screen at the top of the TPA); a poked
base is what separates "reports the variable" from "reports the screen".
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_logbase.restype = ctypes.c_uint32


def base_poke(base):
    return {addrs.SYSVAR_V_BAS_AD: base.to_bytes(4, "big")}


def run(pokes=None, poison=True):
    def glue(lib, buf):
        return lib.xbios_logbase(buf)

    return case.run(addrs.XBIOS_LOGBASE, {"a5": 0, "_pokes": pokes or {}}, glue, poison=poison)


def test_the_snapshot_draws_at_the_top_of_its_tpa():
    """The machine as captured: one screen, at `_memtop`, logical and physical the same."""
    memtop = int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_MEMTOP:addrs.SYSVAR_MEMTOP + 4]), "big")
    assert run()["regs"]["d0"] == memtop


@pytest.mark.parametrize("base", (0, 0x100, 0x78000, 0xF8000, 0x00FF_FFFF, 0xFFFF_FFFF))
def test_the_whole_longword_is_reported(base):
    """Including values no Setscreen would ever store: the routine does not validate, it reports."""
    assert run(base_poke(base))["regs"]["d0"] == base
