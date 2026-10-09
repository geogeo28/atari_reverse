"""gemdosif's HAND 68000 as the target build ships it (`src/aes/gemdosif.S`): pgmld with the hop it reaches `__DOS`
by (`$fe39b4..$fe3a0b`), `__DOS` itself and THE VECTORS GEM TAKES — restore_trap2, install_trap2, retake, giveerr and
takeerr (`$fe3c3e..$fe3cbd`) — the ROM's own instructions.

Their C (`src/aes/gemdosif.c`) is what every Tier 1 case proves (`test_aes_vectors.py`, `test_aes_pgmld.py`); it
measures over the 1.10 bar — restore_trap2 1.42, install_trap2 1.23, giveerr and retake 1.13, takeerr 1.04 with the
BIOS's Setexc in both columns (the image pointer's floor on two to six instructions), pgmld 1.11 on the arm where
Pexec fails — and none is a C function's shape (retake falls into the Setexc tail, giveerr branches into it, takeerr
calls it and branches into it; pgmld's command tail is a word of its own text and its two calls `bsr` a hop). So by
the user's rule the target carries the ROM's code. Two claims hold it: its BYTES are the ROM's, every one of the two
regions, ONE long relocated (the hop's `jmp` to `__DOS`, where the `.S` lays it out); and it BEHAVES as the ROM — the
image and the WHOLE REGISTER FILE — through Tier 3's transcription relation, over the C battery's own machines.

TWO SURFACES, as a vector take has two:
  * THE VECTORS' MEMORY, over the machine's own BIOS: both shores take the real `trap #13` into the ROM's Setexc (its
    register save in the stack band, where the trap's return PC — inside the `.S` on one shore, inside the ROM on the
    other — is not compared);
  * THE SETEXC LEDGER, over a recording `trap #13` (`aes_gemdosif.BIOS`: vector `$b4` pointed at a staged handler):
    every call's function, vector number and handler in order, and what the routine makes of the answer it is
    scripted — the order of takeerr's two calls, and that it asks before it installs.

pgmld's ONE: the recording, scripted `trap #1` (`test_aes_pgmld.py`'s machines) — and THE THREE ADDRESSES OF ITS OWN
TEXT IT LEAVES IN RAM (the two sites `__DOS` parks, the command tail's): the ROM's on one shore, the `.S`'s own on
the other, MAPPED through Tier 3's relocation registry (`aes_event.TEXT_SITES`) and compared exactly — no drop.

THE CALLER is the VDI binding's frame caller (`test_aes_gsx_transcription.entered`).
"""
import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import aes_gemdosif as gd
import case
import test_aes_gsx_transcription as frames
import test_aes_pgmld as battery_pgmld
import test_aes_vectors as battery
import transcription
from transcription import ABSOLUTE, Relocated
from case import merge_pokes
from opcodes import RTS

RESTORE_TRAP2, INSTALL_TRAP2, RETAKE, GIVEERR, TAKEERR = (
    battery.RESTORE_TRAP2, battery.INSTALL_TRAP2, battery.RETAKE, battery.GIVEERR, battery.TAKEERR)
TAKEERR_BYTES = 18                      # $fe3cac..$fe3cbd, to its `bra.s` into the tail: crit_err begins behind it
DOS_TRAP = addrs.AES_ROM_GEM_DOS_TRAP                     # `__DOS`: the park, the trap, the verdict, `jmp (a0)` — $fe3c3e..$fe3c61
REGION = transcription.pinned_region(DOS_TRAP, addrs.AES_ROM_TAKEERR + TAKEERR_BYTES,
                                     RESTORE_TRAP2, (INSTALL_TRAP2, RETAKE, GIVEERR, TAKEERR))
# pgmld's: the zero word, the hop, the routine, and the two return tails behind it ($fe3a04 `moveq #0 / rts`,
# dos_sfirst's and dos_open's miss, carried as bytes; $fe3a08 `moveq #1 / rts`, shared with dos_sfirst).
PGMLD = battery_pgmld.PGMLD
DOS_HOP, PGMLD_END = 0xFE39B6, addrs.AES_ROM_BELL
JMP_OPERAND = DOS_HOP + aes.WORD_BYTES
PGMLD_REGION = transcription.pinned_region(addrs.AES_PGMLD_EMPTY_TAIL, PGMLD_END, PGMLD)
RELOCATED = {JMP_OPERAND: Relocated(ABSOLUTE, RESTORE_TRAP2, "the hop's `jmp` to `__DOS`, where the .S lays it out")}
SETEXC, CRITIC_NUMBER = addrs.BIOS_SETEXC_FN, battery.SETEXC_CRITIC
JMP_ABSOLUTE_LONG = b"\x4e\xf9"


def test_the_transcription_is_the_rom_s_bytes_exactly():
    """THE BYTE PIN: every word the ROM's — no reference leaves the region, and the two handlers it installs are the
    ROM's own immediates until band 5's wave 3 links ours (`test_aes_rom_data.py` reds the day they exist)."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_pgmld_s_transcription_is_the_rom_s_bytes_but_the_hop_s_operand():
    """...and pgmld's region: every word the ROM's but ONE long — where the hop jumps."""
    transcription.assert_transcribed(PGMLD_REGION, relocated=RELOCATED)


def test_pgmld_s_region_is_the_tail_the_hop_the_routine_and_the_shared_returns():
    assert case.word_in(BASE_IMAGE, addrs.AES_PGMLD_EMPTY_TAIL) == 0 and DOS_HOP == addrs.AES_PGMLD_EMPTY_TAIL + aes.WORD_BYTES
    assert bytes(BASE_IMAGE[DOS_HOP:JMP_OPERAND]) == JMP_ABSOLUTE_LONG and case.long_in(BASE_IMAGE, JMP_OPERAND) == DOS_TRAP
    assert addrs.AES_ROM_PGMLD == JMP_OPERAND + aes.LONG_BYTES
    assert bytes(BASE_IMAGE[PGMLD_END - len(RTS):PGMLD_END]) == RTS
    # the two sites `__DOS` parks for it are the instructions after its two `bsr.s` of the hop
    for site in (addrs.AES_PGMLD_PEXEC_RETURN, addrs.AES_PGMLD_MSHRINK_RETURN):
        bsr, displacement = BASE_IMAGE[site - 2], BASE_IMAGE[site - 1]
        assert bsr == 0x61 and site + displacement - 0x100 == DOS_HOP


def test_the_region_is_dos_and_the_five_routines_and_ends_where_crit_err_begins():
    assert REGION.hi == addrs.AES_ROM_CRIT_ERR
    assert bytes(BASE_IMAGE[addrs.AES_ROM_RESTORE_TRAP2 - len(RTS):addrs.AES_ROM_RESTORE_TRAP2]) != RTS, (
        "what precedes it is `__DOS`'s `jmp (a0)`: no routine falls into restore_trap2")
    assert bytes(BASE_IMAGE[addrs.AES_ROM_INSTALL_TRAP2 - len(RTS):addrs.AES_ROM_INSTALL_TRAP2]) == RTS
    assert bytes(BASE_IMAGE[addrs.AES_ROM_GIVEERR - len(RTS):addrs.AES_ROM_GIVEERR]) == RTS, "the shared tail's `rts`"


# ---- over the machine's own BIOS: the vectors' memory --------------------------------------------------------------------
STALE = battery.STALE
longs = battery.longs
OWN_BIOS = {
    (RESTORE_TRAP2, "GEM up: the BIOS's door put back"): battery.gem_up,
    (INSTALL_TRAP2, "the vectors given back"): lambda: merge_pokes(battery.given_back(), longs(vdi_door=STALE)),
    (INSTALL_TRAP2, "over a program's handler"): lambda: battery.a_program_s_own(longs(vdi_door=STALE)),
    (TAKEERR, "the vectors given back"): lambda: merge_pokes(battery.given_back(), longs(old_critic=STALE)),
    (TAKEERR, "GEM up already"): battery.gem_up,
    (GIVEERR, "GEM up: the BIOS's handler installed again"): battery.gem_up,
    (GIVEERR, "a saved longword with bit 31 set: nothing installed"):
        lambda: merge_pokes(battery.gem_up(), longs(old_critic=0x8000_0000 | battery.PROGRAM_S_CRITIC)),
    (RETAKE, "a program's own handlers in both vectors"): battery.a_program_s_own,
    (RETAKE, "the vectors given back"): battery.given_back,
}


def machine(pokes):
    return aes.leaf_machine(onto=pokes)


@pytest.mark.parametrize("name,shape", sorted(OWN_BIOS), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom_over_the_machine_s_own_bios(name, shape):
    frames.run(name, (), machine(OWN_BIOS[(name, shape)]()))


# ---- over the recording trap: the Setexc ledger ---------------------------------------------------------------------------
PREVIOUS, DISPLACED = 0x0012_3450, 0x0065_4320      # what the scripted Setexc answers: handlers no machine holds


def setexc(handler):
    return gd.BIOS.call(SETEXC, ("w", CRITIC_NUMBER), ("l", handler))


# (the routine, the machine, the script's answers) -> the calls recorded, in order
RECORDED = {
    (RETAKE, "GEM up"): (battery.gem_up, [DISPLACED], [setexc(battery.CRIT_ERR)]),
    (GIVEERR, "GEM up"): (battery.gem_up, [DISPLACED], [setexc(battery.BIOS_CRITIC)]),
    (GIVEERR, "a staged saved handler"):
        (lambda: merge_pokes(battery.gem_up(), longs(old_critic=battery.PROGRAM_S_CRITIC | aes.BUS_TAG)), [DISPLACED],
         [setexc(battery.PROGRAM_S_CRITIC | aes.BUS_TAG)]),
    (TAKEERR, "GEM up"): (lambda: merge_pokes(battery.gem_up(), longs(old_critic=STALE)), [PREVIOUS, DISPLACED],
                          [setexc(0xFFFF_FFFF), setexc(battery.CRIT_ERR)]),
}


def recorded_machine(name, shape):
    pokes, answers, _calls = RECORDED[(name, shape)]
    return machine(merge_pokes(pokes(), gd.BIOS.pokes(answers)))


@pytest.mark.parametrize("name,shape", sorted(RECORDED), ids=lambda value: value)
def test_the_transcription_makes_the_rom_s_setexc_calls_in_order(name, shape):
    """Both shores trap into the recording handler: the ledger — Setexc, vector number $101, the handler — and the
    script's pointers are compared image, the answers handed back register for register. And the ledger is WHAT THE
    ROUTINE'S NAME SAYS (read off the ORIGINAL's side of the measurement): takeerr asks ($ffffffff) BEFORE it
    installs, and keeps the first answer."""
    frames.run(name, (), recorded_machine(name, shape))
    _pokes, answers, calls = RECORDED[(name, shape)]
    image, _writes, regs = emu.run(make_image(recorded_machine(name, shape)), getattr(addrs, name), {})
    assert gd.BIOS.calls(image) == calls and regs["d0"] == answers[-1]
    if name == TAKEERR:
        assert case.long_in(image, aes.AES_OLD_CRITIC) == answers[0]


# ---- Tier 3's rows ----------------------------------------------------------------------------------------------------------
for (_name, _shape), _pokes in sorted(OWN_BIOS.items()):
    frames.register(_shape, _name, (), machine(_pokes()))
for _name, _shape in sorted(RECORDED):
    frames.register(f"{_shape}, Setexc recorded", _name, (), recorded_machine(_name, _shape))
