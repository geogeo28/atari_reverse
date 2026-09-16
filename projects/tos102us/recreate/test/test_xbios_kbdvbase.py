"""XBIOS Kbdvbase (function $22) @ $fc30bc — the address of the IKBD/MIDI vector table.

    move.l  #$e12,d0
    rts

TWO INSTRUCTIONS AND NO MEMORY ACCESS AT ALL, which is what makes the cases below about the ADDRESS
rather than about the routine: the number is right or the whole table a caller goes on to patch is
somebody else's memory. So the battery proves the constant three ways that do not rest on each
other — the block it names really is a table of installed handlers, the routine does not read it
(perturbing the table changes nothing), and the answer is a whole longword rather than a word.

KBDVECS is what a program asks for when it wants its own mouse, joystick or clock packets: it stores
its handler into the slot it wants and the ACIA interrupt dispatches through the table. `Initmous`
next door does exactly that with `mousevec`, at `+$10`, which is the other reason this address has
to be right — two reconstructions reach the same block through two constants.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_kbdvbase.argtypes = []
_lib.xbios_kbdvbase.restype = ctypes.c_uint32

# The slots this project has named so far, and what each one is for. The list is short deliberately:
# a slot nothing reaches is a claim nothing checks.
NAMED_SLOTS = ((addrs.KBDVECS_MOUSEVEC, "mousevec, which Initmous installs"),
               (addrs.KBDVECS_MIDISYS, "midisys, the MIDI 6850's service routine"),
               (addrs.KBDVECS_IKBDSYS, "ikbdsys, the IKBD 6850's"))
# A caller's D0 with a marked high half: the ROM writes the whole register, so nothing of it survives.
MARKED_D0 = 0xDEAD_BEEF


def run(pokes=None, entry_d0=0, poison=True):
    def glue(lib, buf):
        del buf                       # the routine reads no memory; see the module docstring
        return lib.xbios_kbdvbase()

    return case.run(addrs.XBIOS_KBDVBASE, {"a5": 0, "d0": entry_d0, "_pokes": pokes or {}}, glue,
                    poison=poison)


def test_it_reports_the_address_of_the_vector_table():
    assert run()["regs"]["d0"] == addrs.KBDVECS


def long_at(address):
    return int.from_bytes(bytes(BASE_IMAGE[address:address + addrs.VECTOR_BYTES]), "big")


@pytest.mark.parametrize("offset,what", NAMED_SLOTS)
def test_the_block_it_names_holds_installed_rom_handlers(offset, what):
    """What says `$e12` is KBDVECS and not an arbitrary word of low RAM: every slot this project
    names holds a ROM address, because the boot filled the table with the ROM's own handlers."""
    handler = long_at(addrs.KBDVECS + offset)
    assert addrs.ROM_BASE <= handler < addrs.ROM_BASE + addrs.ROM_BYTES, (
        f"KBDVECS + {offset:#x} ({what}) holds {handler:#x}, which is not a ROM handler — so "
        f"{addrs.KBDVECS:#x} is not the table Kbdvbase claims")


def test_the_whole_table_is_inside_the_os_s_own_low_ram():
    """...and it is a TABLE: nine longwords, all of them below the OS's BSS and clear of the
    keyboard-table struct at $e62 that Keytbl owns. A `KBDVECS` off by a slot would overlap it."""
    end = addrs.KBDVECS + addrs.KBDVECS_LONGWORDS * addrs.VECTOR_BYTES
    assert end <= addrs.KEYTBL_STRUCT, (
        f"KBDVECS runs to {end:#x}, into the keyboard-table struct at {addrs.KEYTBL_STRUCT:#x}")
    assert all(addrs.ROM_BASE <= long_at(at) < addrs.ROM_BASE + addrs.ROM_BYTES or long_at(at) == 0
               for at in range(addrs.KBDVECS, end, addrs.VECTOR_BYTES))


def test_it_reports_the_address_whatever_the_table_holds():
    """`move.l #`, not a load: the routine hands back where the table IS, never what is in it. A
    reconstruction that read the first slot would agree with the snapshot and with nothing else."""
    scrambled = bytes(range(addrs.KBDVECS_LONGWORDS * addrs.VECTOR_BYTES))
    assert run({addrs.KBDVECS: scrambled})["regs"]["d0"] == addrs.KBDVECS


def test_the_result_is_a_whole_longword():
    """`move.l #$e12,d0` writes all 32 bits, so a caller's high half does NOT survive — unlike
    Kbrate's and Cursconf's `move.w` arms next door. `case.run` compares the candidate's return
    against the whole of D0, so this pins the width on both sides."""
    assert run(entry_d0=MARKED_D0)["regs"]["d0"] == addrs.KBDVECS


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row, measured rather than estimated."""
    from harness import emu, make_image
    _final, _writes, regs = emu.run(make_image(), addrs.XBIOS_KBDVBASE, {"a5": 0})
    assert (regs["ninsns"], regs["cycles"]) == (3, 68), (
        f"Kbdvbase now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
