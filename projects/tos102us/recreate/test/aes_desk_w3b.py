"""BAND 6 W3b — deskmain `$fe272e`, THE DESK'S LAST ROUTINE BUT THE CARTRIDGE'S PAIR: its prep, and its FLIP
(`test_desk_w3b.py`).

deskmain's signature is declared with the cycle it calls (`aes_desk_w3a.W3B`: target-only, `() -> word`); its C is
`src/desk/desktop.c`'s, its table entry and sh_main's desk door its thunk since the flip. This module holds:

  * THE RETURN SITES its Line-F calls park (`desk/desktop.h`), held here to the ROM's own words;
  * ITS ROWS' ARRIVALS (the W3b cut's §2.2 (A), the orchestrator's O3 / O7): the FIRST ENTRY of each boot machine (the
    ROM's own boot stopped there, R6) and the RE-ENTRIES after a built-in (a chain of the hands stopped there:
    `aes_deskarrive.arrival`), each vetted on the ROM's machine (`vet_an_arrival`);
  * THE ROWS (`row_of`): A TARGET-ONLY ROW THAT SWITCHES OF THE PARKED KIND (the user's ruling of 2026-10-28: "a new
    target-only row kind that ends at the first idle" — `aes_switching.SwitchingRow.ends_at_its_first_idle`), each run
    from deskmain's entry to the desk's first idle, its answer not compared (it never returns), its stagings said in
    its label — THE XBIOS'S GETREZ STAGED (the bring-up's app_blddesk: the arrival's own shifter mode; Blitmode's
    answer the same stub's: no blitter, O6) and GEMDOS REPLAYED by a frame-telling handler of the band's own (the
    ROM's run in place to its first idle: `aes_deskdir.in_place(parks=True)`) — and the XBIOS door's park named (R9's
    declared kind, `test_desk_app.XBIOS_DOOR_PARKED`);
  * WHERE EACH ROW'S SCREEN MANAGER IS MADE OURS FROM (the takeover, `aes_takeover`): a first entry's, THE BOOT ITSELF
    STOPPED AT deskmain's ENTRY (`note_a_stopped_boot`); a re-entry's, THE BUILT-IN'S OWN REGISTERED ROW whose ROM run
    leaves the screen manager in the arrival's state (`note_a_registered_row`) — measured, by state;
  * REGISTERED AT THE FLIP (`register_at_the_flip`), refused by name while the generator holds deskmain.

The other two pieces of the prep live where they are read: U1's label (`aes_desk_turns_pinned.PARKED_IN_THE_ROM_S_
DESKMAIN`, `bench/tier3.py`'s TALLY_OUR_DESKMAIN) and O4's invariant (`test_aes_desk_ours.ROM_GEM_TEXT_ON_OUR_WALKS`).
"""
import functools
import importlib.util
import sys
from pathlib import Path

from harness import addrs

import aes
import aes_boot
import aes_desk
import aes_desk_w3a as w3a
import aes_deskapp
import aes_deskarrive as da
import aes_deskdir as cdir
import aes_desksupp as ds
import aes_event
import aes_fslib as fsl
import aes_shell as sh
import aes_shmain
import aes_takeover
import case
import preinit_snapshot
import rom_data
import test_aes_ourboot
from harness import make_image
from test_desk_app import XBIOS_DOOR_PARKED

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


# ---- WHAT THE ROWS' PINS READ OFF THE MACHINE: deskmain's menu tree and the Options box (`desk/desktop.h`, one source) ----------
_DESKTOP_H = rom_data.constants_of(rom_data.RECREATE / "include" / "desk" / "desktop.h")
DESK_MENU_TREE, OPTIONS_BOX, OPTN_PRINT_SCREEN = (_DESKTOP_H[name] for name in ("DESK_MENU_TREE", "OPTIONS_BOX", "OPTN_PRINT_SCREEN"))
OB_BYTES, OB_TAIL = _DESKTOP_H["OB_BYTES"], _DESKTOP_H["OB_TAIL"]


# ---- THE STAGINGS (band 6 W3b's flip), each said in its row's label ------------------------------------------------------------
GETREZ_STAGED = aes_deskapp.GETREZ_STAGED       # the XBIOS's trap answered the arrival's own shifter mode (stage 1's)
SHIFTER_MODE_BITS = aes_deskapp.SHIFTER_MODE_BITS
# GEMDOS REPLAYED by THE BAND'S OWN FRAME-TELLING HANDLER: G3's replay (`aes_desksupp.replay_pokes`) — the ROM's run in
# place's answers and DTAs — told Dgetdrv's frame too, NONE (`aes_shell.FRAME_BYTES`: one source; band 6 W3a stage 3's
# FRAMED precedent): deskmain's bring-up makes it four times, and the six bytes an untold call is recorded past its
# frame are the caller's stack (the ROM's return address on its shore, our frame's word on ours), which no build
# reproduces. Its own handler span:
DGETDRV = addrs.GEMDOS_DGETDRV_FN
REPLAYED = f"{ds.REPLAYED}; Dgetdrv's own frame told"
TOLD_ARGUMENT_BYTES = {**ds.REPLAY_ARGUMENT_BYTES, DGETDRV: sh.FRAME_BYTES[DGETDRV]}
TOLD_HANDLER_OFFSET, TOLD_HANDLER_BYTES = 0x2F00, 0xC0      # the gap between aes_deskutil.py's band and aes_gemsuper.py's (measured)
TOLD_HANDLER_AT = aes.SPAN.claim(aes.WINDOW_AT + TOLD_HANDLER_OFFSET, TOLD_HANDLER_BYTES,
                                 "test/aes_desk_w3b.py: GEMDOS replayed, Dgetdrv's own frame told")
TOLD_HANDLER = fsl.replay_handler(TOLD_ARGUMENT_BYTES)
assert len(TOLD_HANDLER) <= TOLD_HANDLER_BYTES
sh.GEMDOS_LEDGERS.append(functools.partial(sh.GemdosLedger, TOLD_HANDLER_AT, TOLD_HANDLER, fsl.LEDGER, TOLD_ARGUMENT_BYTES,
                                           fsl.RECORDED_ARGUMENT_BYTES, fsl.DTA_CELL_AT))
STAGED_AS = f"{GETREZ_STAGED}; {REPLAYED}"


def in_place(arrived):
    """THE ROM'S OWN RUN IN PLACE from `arrived` to the desk's first idle (`aes_deskdir.in_place`, the parked kind's)."""
    return cdir.in_place(arrived, parks=True)


def staged(arrived):
    """The row's stagings over the arrival's machine: Getrez answered the arrival's shifter mode, GEMDOS replayed
    (`in_place`'s answers and the DTA each search left) through the band's frame-telling handler."""
    mode = arrived.boot.io[addrs.SHIFTER_RESOLUTION - preinit_snapshot.IO_AT] & SHIFTER_MODE_BITS
    ran = in_place(arrived)
    fills = iter(ran.fills)
    script = tuple((answer, next(fills) if function in fsl.SEARCHES else fsl.NO_DTA) for function, answer in zip(ran.functions, ran.answers))
    return case.merge_pokes(aes_shmain.getrez_pokes(mode), ds.replay_pokes(script, TOLD_HANDLER_AT, TOLD_ARGUMENT_BYTES))


# ---- WHERE EACH ROW'S SCREEN MANAGER IS MADE OURS FROM (`aes_takeover`) ------------------------------------------------------------
# A first entry's machine is THE BOOT STOPPED AT deskmain's ENTRY: its takeover machine the same boot with the screen
# manager ours, stopped there. A re-entry's is a built-in's aftermath: THE BUILT-IN'S OWN REGISTERED ROW whose ROM run
# leaves the screen manager in the arrival's state (`BUILT_INS`, measured by state — refused by name where none does).
BUILT_INS = ("AES_ROM_DESK_SHOW_FILE", "AES_ROM_DESK_PRINT_FILE", "AES_ROM_DESK_FORMAT", "AES_ROM_DESK_COPY_DISK")
NO_PROVENANCE = "no registered row of a built-in leaves the screen manager where this re-entry finds it: it cannot be made ours"


def screen_manager_s_provenance(label):
    """`label`'s arrival's screen manager's state, NOTED (`aes_takeover`) where our build can be run to stand there: the
    boot stopped at deskmain's first entry, or a built-in's registered row (`BUILT_INS`) whose ROM run leaves it so —
    refused by name where none does (NO_PROVENANCE). The state."""
    where, kind = ARRIVALS[label]
    arrived = arrival(label)
    state = aes_takeover.state_of(make_image(da.row_machine_of(arrived)))
    if kind == FIRST_ENTRY:
        return aes_takeover.note_a_stopped_boot(
            aes_boot.Machine(arrived.boot),
            lambda blob: aes_boot.Machine(aes_boot.booted(*BOOTS[where](), until=DESKMAIN_ENTRY, ours=aes_boot.ours_of(blob))))
    if state in aes_takeover.PROVENANCE:
        return state
    for _name, held in aes_event.every_switching_row().items():
        if held.row.name in BUILT_INS and aes_takeover.note_a_registered_row(held.row, held) == state:
            return state
    raise aes_takeover.Refused(f"{label}: {NO_PROVENANCE}")


def row_of(label):
    """THE ROW AT `label`'s ARRIVAL (`aes_switching.SwitchingRow`, `aes_deskarrive.row_of`'s): deskmain from its entry,
    no argument, OF THE PARKED KIND — no wake, the run ends at the desk's first idle, its word not compared (it never
    returns) — over the arrival's machine and its stagings (`staged`), the XBIOS door's park named."""
    arrived = arrival(label)
    machine = case.merge_pokes(da.row_machine_of(arrived), staged(arrived))
    row = da.row_of(arrived, f"{label} [{STAGED_AS}]", False, pokes=machine)
    return row._replace(also_dropped=XBIOS_DOOR_PARKED, ends_at_its_first_idle=True)


# ---- REGISTERED AT THE FLIP ------------------------------------------------------------------------------------------------------
STILL_HELD = "deskmain's row registered while the generator still holds its entry the ROM's (DECLARED_NOT_LINKED): no C to run"


def _held_back():
    """The generator's held routines — imported here, not at the module's top (it imports every battery's registry).
    WHERE THE GENERATOR ITSELF IS IMPORTING THE REGISTRY (its module half made: the rows register at import since the
    flip), the hold is read off a second copy of its module — as `python bench/linef_table.py` does, the script
    `__main__` and its import another module."""
    bench = Path(__file__).resolve().parents[1] / "bench"
    sys.path.insert(0, str(bench))
    try:
        import linef_table
    finally:
        sys.path.remove(str(bench))
    if not hasattr(linef_table, "held_back"):
        spec = importlib.util.spec_from_file_location("linef_table_s_hold", bench / "linef_table.py")
        linef_table = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(linef_table)
    return linef_table.held_back()


def register_at_the_flip(label):
    """`label`'s row REGISTERED — a target-only row that switches, of the parked kind
    (`aes_desk_w3a.register_target_only_switching`: its vouch, its census, its companion-free price) — ONCE deskmain IS
    FLIPPED; refused by the row's name while the generator holds it (STILL_HELD). Its screen manager's provenance noted
    first (`screen_manager_s_provenance`). The row."""
    assert DESKMAIN not in _held_back(), f"{label}: {STILL_HELD}"
    vet_an_arrival(label)
    screen_manager_s_provenance(label)
    return w3a.register_target_only_switching(row_of(label))
