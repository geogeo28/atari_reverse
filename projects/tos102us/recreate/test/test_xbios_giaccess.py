"""XBIOS Giaccess ($1c) @ $fc2ea4 — TOS's one door onto the YM2149's register file.

The second Tier 1 differential, and the one that says ROM mode keeps the OFF-IMAGE models: the
routine's whole effect is the sound chip, which lives at $ff8800/$ff8802 — addresses that are
numerically INSIDE this project's 16 MB image and must nonetheless reach the seeded PSG model rather
than the image's bytes. Nothing in the memory diff could catch that: if the ports were served as
ordinary RAM, both sides would... not even be comparable, since the candidate calls `psg_port_*`.
What compares them is psg.h's ordered access ledger and the register file behind it, which
`harness.differential` diffs on every case (TRAP_MODEL.md, Phase 6).

ARGUMENTS ARRIVE ON THE STACK, as they do from the XBIOS dispatcher: `Giaccess(data.w, reg.w)` with
`data` at 4(sp) and `reg` at 6(sp). The harness forces A7 to `emu.STACK_TOP` and writes the sentinel
return address there, so the two argument words are poked at `abi.FIRST_ARG` — inside the band the
diff drops as machine stack, which is exactly where a caller's frame belongs.

`reg` carries the direction in bit 7: set means "write `data` to the register first". Either way the
routine reads the selected register back and returns it, which is what makes it usable as the
read-modify-write primitive Ongibit/Offgibit next door are built from.
"""
import ctypes

import pytest

# `emu` comes THROUGH the shim rather than as a bare `import emu`: the kit's oracle directory only
# reaches sys.path once `harness` has bound the project, so importing it first fails.
from harness import (OS_PSG_EVENT_READ, OS_PSG_EVENT_WRITE, OS_PSG_PORT_SELECT, _lib, addrs,
                     differential, report)

# The register set, the declared entry file and the argument poke come from `cases_xbios`, which
# Tier 3's bench reads too — one spelling, so a ratio is measured over the machine a case was
# verified on. That module's docstring says why.
from cases_xbios import ENTRY_FILE, REGISTERS, argument_poke

_lib.xbios_giaccess.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
_lib.xbios_giaccess.restype = ctypes.c_uint8


def run(data, reg_and_flag, psg_seed=None, poison=True, pokes=None):
    """One differential of XBIOS Giaccess. Returns its info."""
    def glue(lib, buf):
        del buf                         # the chip is not in the image; see the module docstring
        return lib.xbios_giaccess(data & 0xFFFF, reg_and_flag & 0xFFFF)

    diffs, info = differential(addrs.XBIOS_GIACCESS,
                               {"a5": 0,
                                "_pokes": {**argument_poke(data, reg_and_flag), **(pokes or {})}},
                               glue, psg_seed=psg_seed, poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] == info["regs"]["d0"], (
        f"the candidate returned {info['ret']:#x} where the ROM left {info['regs']['d0']:#x} in D0")
    return info


@pytest.mark.parametrize("reg", REGISTERS)
def test_a_read_answers_the_register_the_case_declared(reg):
    """No write flag: select, then read back. The byte can only come from the case's declaration —
    the model refuses to invent what the chip held (TRAP_MODEL.md, Phase 6)."""
    info = run(0, reg, psg_seed=ENTRY_FILE)
    assert info["regs"]["d0"] == ENTRY_FILE[reg], "the ROM read a register other than the selected one"
    assert info["regs"]["psg_events"] == [(OS_PSG_EVENT_READ, reg, ENTRY_FILE[reg])]


@pytest.mark.parametrize("reg", REGISTERS)
def test_a_write_stores_the_byte_and_reads_it_straight_back(reg):
    """Bit 7 set: select, write the data port, then read the same register — so the value returned
    is the one just written, and no seed is needed for it."""
    value = (reg * 0x0F + 3) & 0xFF
    info = run(value, addrs.GIACCESS_WRITE_FLAG | reg)
    assert info["regs"]["d0"] == value
    assert info["regs"]["psg_events"] == [(OS_PSG_EVENT_WRITE, reg, value),
                                          (OS_PSG_EVENT_READ, reg, value)]


@pytest.mark.parametrize("data", (0x0000, 0x00FF, 0xFF00, 0x1234, 0xFFFF))
def test_only_the_low_byte_of_the_data_word_reaches_the_chip(data):
    """`move.b d0,2(a0)` — the argument is read as a word and stored as a byte."""
    info = run(data, addrs.GIACCESS_WRITE_FLAG | 7)
    assert info["regs"]["d0"] == (data & 0xFF)


@pytest.mark.parametrize("reg_and_flag", (0x0000, 0x0007, 0x0080, 0x008F, 0x00FF,
                                          0x8007, 0x8087, 0xFF07, 0xFF87, 0x0170, 0x01F0))
def test_the_direction_and_the_register_come_from_the_low_byte_alone(reg_and_flag):
    """`move.b d1,d2` then `andi.b #$0f,d1` / `asl.b #1,d2`: the high half of the argument word is
    ignored entirely, and the write flag is bit 7 of the LOW byte. A reconstruction that tested the
    whole word — or masked the register with $ff — diverges on exactly these."""
    run(0x5A, reg_and_flag, psg_seed=ENTRY_FILE)


def test_the_ports_are_not_served_out_of_the_image():
    """The claim ROM mode has to get right: $ff8800 is numerically inside a 16 MB image and must
    still reach the seeded model. A decoy byte planted at that very address is what says so — a shim
    that served the image would answer $99 instead of the declared register, and the image would
    come back with the select write in it."""
    decoy = 0x99
    info = run(0, 3, psg_seed=ENTRY_FILE, pokes={OS_PSG_PORT_SELECT: bytes([decoy])})
    assert info["regs"]["d0"] == ENTRY_FILE[3], "the read answered the image, not the PSG model"
