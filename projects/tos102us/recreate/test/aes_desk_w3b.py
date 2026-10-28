"""BAND 6 W3b — deskmain `$fe272e`, THE DESK'S LAST ROUTINE BUT THE CARTRIDGE'S PAIR: its PREP (`test_desk_w3b.py`).

deskmain's signature is declared with the cycle it calls (`aes_desk_w3a.W3B`: target-only, `() -> word`) and held THE
ROM'S by the generator (`linef_table.DECLARED_NOT_LINKED`) until its flip. This module is what the flip will need of
the harness, made now and proved neutral while held:

  * THE RETURN SITES its Line-F calls park (`desk/desktop.h`), held here to the ROM's own words;
  * ITS ROWS' ARRIVALS (the W3b cut's §2.2 (A), the orchestrator's O3 / O7): A TARGET-ONLY ROW THAT SWITCHES at each
    arrival at deskmain's entry — the FIRST ENTRY of each boot machine (the ROM's own boot stopped there: the arrival
    a takeover at deskmain's entry would be made over, R6) and the RE-ENTRIES after a built-in (a chain of the hands
    stopped there: `aes_deskarrive.arrival`) — each run from deskmain's entry to the FIRST IDLE (the desk parked in its
    own evnt_multi: the row's wake is none). Every arrival is vetted now, on the ROM's machine (`vet_an_arrival`: the
    shell's call, the ROM's stack pointer, a machine a row may be made over, a run that idles before deskmain returns);
    REGISTERED AT THE FLIP (`register_at_the_flip`), REFUSED BY NAME while deskmain is held.

The other two pieces of the prep live where they are read: U1's label (`aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_
DESKMAIN`, `bench/tier3.py`'s TALLY_OUR_DESKMAIN) and O4's invariant (`test_aes_desk_ours.ROM_GEM_TEXT_ON_OUR_WALKS`).
"""
import functools
import sys
from pathlib import Path

from harness import addrs

import aes
import aes_boot
import aes_desk
import aes_desk_w3a as w3a
import aes_deskarrive as da
import case
import test_aes_ourboot

DESKMAIN = w3a.DESKMAIN
DESKMAIN_ENTRY = getattr(addrs, DESKMAIN)
# ---- THE RETURN SITES (`include/desk/desktop.h`): `{name: the routine the Line-F call word before it calls}` ------------------
RETURN_SITES = {"AES_DESKMAIN_BLITMODE_ASKED_RETURN": "AES_ROM_TRP14", "AES_DESKMAIN_BLITMODE_SET_RETURN": "AES_ROM_TRP14",
                "AES_DESKMAIN_GDRV_RETURN": "AES_ROM_DOS_GDRV"}
_its_name, SH_MAIN_S_CALL = aes_boot.SERVED_ROUTINES[DESKMAIN_ENTRY]    # sh_main's Line-F call word of deskmain, `$feb1dc`
RETURNS_TO_SH_MAIN = SH_MAIN_S_CALL + aes.WORD_BYTES    # `$feb1de move.w d0,-6(a6)`: where deskmain's word is read
# The ROM's SP at deskmain's entry, `$a364`: the desk door's DESK_DOOR_SP_IN_SH_MAIN (`aes/deskdoor.h`) less the return
# the call pushes — W4-R4's figure, the one the our-boot holds the ROM's boot to (`test_aes_ourboot.py`).
SP_AT_ITS_ENTRY = test_aes_ourboot.THE_ROM_ENTERS_DESKMAIN_AT


# ---- THE ARRIVALS ---------------------------------------------------------------------------------------------------------------
# `{the row's label: (a key of aes_desk.MACHINES — or a chain of aes_desk.CHAINS —, FIRST_ENTRY or RE_ENTRY)}`. Five first
# entries (the cartridge's machine LABELLED, its class said in its name), five re-entries — one a built-in's class (the
# viewer, Format's EXIT, the copy's EXIT) and two on the printer machine (O7: the run after a print prints nothing).
FIRST_ENTRY, RE_ENTRY = "its machine's boot, stopped at deskmain's first entry", "a chain of the hands, at its re-entry"
THE_DESK_ALONE = "the desk alone (the blank disk)"
BOOTS = {THE_DESK_ALONE: lambda: (aes_boot.preinit(), aes_boot.blank_disk()),
         aes_desk.INF_ICONS: lambda: (aes_boot.inf_preinit(), aes_boot.inf_disk_of()),
         aes_desk.INF_TEXT: lambda: (aes_boot.inf_preinit(), aes_boot.inf_disk_of(aes_boot.VIEW_AS_TEXT)),
         aes_desk.FILES: lambda: (aes_boot.files_preinit(), aes_boot.files_disk_of()),
         aes_desk.CARTRIDGE_A_DRIVE: lambda: (aes_boot.inf_preinit(), aes_boot.cartridge_drive_disk())}
RE_ENTRIES = ("file: shown, a key at its end", "A: File > Format, OK, EXIT clicked",
              "drive A: onto drive B:, OK, then Return (EXIT, the default)", "file: the printer not ready, Cancel",
              "file: File > Open, five seconds, Print clicked (printed)")
ARRIVALS = {**{f"the first entry, {machine}": (machine, FIRST_ENTRY) for machine in BOOTS},
            **{f"the re-entry after {chain!r}": (chain, RE_ENTRY) for chain in RE_ENTRIES}}
# A FIRST ENTRY'S RUN to its first idle is the rest of a boot: the boot's own budget, read from where it is spent.
FIRST_ENTRY_INSNS = aes_boot.BOOT_INSNS


@functools.cache
def arrival(label):
    """THE ROM'S MACHINE AT deskmain's ENTRY for the row `label` (an `aes_deskarrive.Arrival`): the boot stopped at its
    first arrival there, or the chain at its first re-entry."""
    where, kind = ARRIVALS[label]
    if kind == RE_ENTRY:
        return da.arrival(DESKMAIN, where)
    boot = aes_boot.booted(*BOOTS[where](), until=DESKMAIN_ENTRY)
    sp = boot.registers["isp"]
    return da.Arrival(DESKMAIN, where, 0, boot, (), case.long_in(boot.ram, sp) & aes.OS_BUS_ADDR_MASK, None, FIRST_ENTRY_INSNS)


NOT_THE_SHELL_S_CALL = "an arrival at deskmain that is not sh_main's call of it on the ROM's stack pointer"
RETURNS_BEFORE_AN_IDLE = "an arrival whose run returns from deskmain before it idles: no row of deskmain's kind ends there"


def vet_an_arrival(label):
    """THE PREMISES OF A ROW AT `label`'s ARRIVAL, on the ROM's own machine (each refused by the row's name): stopped
    at deskmain's entry, in supervisor state, CALLED BY sh_main (its return `$feb1de`) WITH THE ROM'S STACK POINTER
    (`$a364`: the desk door's, W4-R4); its megabyte a row's machine (`aes_desk.arrival_s_machine`: the harness's window
    the snapshot's); and the ROM's run from there IDLES BEFORE deskmain RETURNS (the row ends at the first idle). The
    arrival."""
    arrived = arrival(label)
    registers = arrived.boot.registers
    called = (registers["pc"] & aes.OS_BUS_ADDR_MASK, registers["sr"] & aes_boot.SR_SUPERVISOR, registers["isp"], arrived.returns_to)
    assert called == (DESKMAIN_ENTRY, aes_boot.SR_SUPERVISOR, SP_AT_ITS_ENTRY, RETURNS_TO_SH_MAIN), f"{label}: {NOT_THE_SHELL_S_CALL}: {called}"
    aes_desk.arrival_s_machine(arrived.boot.ram)
    assert da.returned_in_place(arrived) is None, f"{label}: {RETURNS_BEFORE_AN_IDLE}"
    return arrived


def row_of(label):
    """THE ROW AT `label`'s ARRIVAL (`aes_switching.SwitchingRow`, `aes_deskarrive.row_of`'s): deskmain from its entry,
    no argument, its word compared, NO WAKE — the run ends at the desk's first idle."""
    return da.row_of(arrival(label), label, True, pokes=da.row_machine_of(arrival(label)))


# ---- REGISTERED AT THE FLIP ------------------------------------------------------------------------------------------------------
STILL_HELD = "deskmain's row registered while the generator still holds its entry the ROM's (DECLARED_NOT_LINKED): no C to run"


def _held_back():
    """The generator's held routines — imported here, not at the module's top (it imports every battery's registry)."""
    bench = str(Path(__file__).resolve().parents[1] / "bench")
    sys.path.insert(0, bench)
    try:
        import linef_table
    finally:
        sys.path.remove(bench)
    return linef_table.held_back()


def register_at_the_flip(label):
    """`label`'s row REGISTERED — a target-only row that switches (`aes_desk_w3a.register_target_only_switching`: its
    vouch, its census, its companion-free price) — ONCE deskmain IS FLIPPED; refused by the row's name while the
    generator holds it (STILL_HELD). The row."""
    assert DESKMAIN not in _held_back(), f"{label}: {STILL_HELD}"
    vet_an_arrival(label)
    return w3a.register_target_only_switching(row_of(label))
