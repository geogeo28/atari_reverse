"""BAND 6 W3a, STAGE 2 — THE SELECTION OPENED AND SHOWN, AND TWO MENUS' HANDLERS, IN C AND FLIPPED (`src/desk/desksupp.c`'s
three: do_open, do_aopen, do_info; `src/desk/desktop.c`'s two: do_optnmenu, do_deskmenu), HELD TARGET-ONLY (the user's
R3: no host twin, no Tier 1 case):

  * THE FLIP: each one's Line-F table entry its thunk, on both blobs (`aes_deskarrive.flipped`). Their ROM callers —
    hndl_msg, hndl_menu, do_filemenu, hndl_button — stay the ROM's until stage 3 and enter the C through the table.
  * THE ROWS: ONE PER ARRIVAL CLASS THE W3a CUT MEASURED (its §2.2 key, re-measured over every chain since: the TTP
    chain's do_aopen arrival a class of its own) — a row that switches over the ROM's own arrival machine, its waits
    ended by the hand its chain gave there, registered TARGET-ONLY (`aes_desk_w3a.register_target_only_switching`). A
    class's row stands at the first of its arrivals a row can hold; where that is not its first, the reason is said
    beside it (`REPRESENTED_BY`).
  * THE STAGINGS, each the precedent's, said in the row's name: stage 1's GEMDOS REPLAYED (fslib's, or the copy engine's
    with every pointer recorded as handed for the disk's Show Info) and GETREZ STAGED; THE ROM'S FLOPPY DRIVER REPLAYED
    beside GEMDOS's where the run reaches drive_check (F3's, `aes_desksupp.floppy_staged`), with AES_BIOS_RETURN NAMED
    BY NATURE (`aes_desksupp.BIOS_DOOR_PARKED`, R9's kind: the shipped glue parks its own return) — which the
    target-only kind admits where the ROM's run stores it UNCHANGED (the arrival already holds drive_check's own park)
    or INSIDE THE DOOR'S PARK THAT RUN STORES INTO (the orchestrator's ruling at this stage: a window by address, the
    park longword only, off the run's own write ledger — `aes_switching.door_park_windows`); and Save Desktop's
    app_save over its own recorder (`aes_deskapp.GEMDOS`, F3's).
  * THE CLASSES NO ROW HOLDS, BY NAME (`REFUSED`, the standing rulings): the Show / Print / Cancel alert's Show (its
    pro_run: W6-R8's launch arm), the program launched (W6-R8's chain), Print Screen (its alert raised and not answered:
    its OK prints, R-H-2's ledger not authorized).
  * A NAMED ROW'S BUDGET: ONE NAMED CONSTANT (`ROW_INSNS`) where a row's own run is past the default margin.
"""
from collections import namedtuple

import pytest
from harness import addrs, make_image

import aes
import aes_desk
import aes_deskapp
import aes_deskarrive as da
import aes_deskdir as cdir
import aes_desksupp as ds
import aes_deskfun as fun
import aes_desk_w3a as w3a
import aes_event
import aes_switching
import case
import vdi
import test_desk_w3a_stage1 as stage_1
from test_aes_desk_ours import LAUNCHED, REFUSED_ON_OUR_SHORE

STAGE_2 = w3a.STAGES[2]

# ---- THE HANDS (stage 1's), AND A RUN THAT RETURNS IN PLACE: no wait, no hand ----------------------------------------------
RETURN_TYPED, CANCEL_CLICKED = stage_1.RETURN_TYPED, stage_1.CANCEL_CLICKED
IN_PLACE = fun.Wake(lambda _chain: {}, lambda _chain: ())
WAKE_NAMED = {**stage_1.WAKE_NAMED, IN_PLACE: "no wait"}

# ---- THE STAGINGS: stage 1's, the floppy's beside GEMDOS's where the run reaches drive_check, and app_save's own ---------
REPLAYED, GETREZ_STAGED, REPLAYED_AS_HANDED = stage_1.REPLAYED, stage_1.GETREZ_STAGED, stage_1.REPLAYED_AS_HANDED
FLOPPY = f"{REPLAYED}; {ds.DRIVER_REPLAYED}"
DISK_FLOPPY = f"{REPLAYED_AS_HANDED}; {ds.DRIVER_REPLAYED}"     # ...the disk's Show Info: inf_disk's own (stage 1's)


def _the_floppy_replayed(arrived):
    """drive_check's own floppy replay at the chain's first arrival there — the one under this row's run (F3's)."""
    replay, _drive = ds.floppy_replay(arrived.chain)
    return ds.floppy_staged(replay)


def gemdos_and_the_floppy_replayed(arrived, wake):
    """Stage 1's GEMDOS replay, and the floppy's (`_the_floppy_replayed`)."""
    return case.merge_pokes(stage_1.gemdos_replayed(arrived, wake), _the_floppy_replayed(arrived))


def gemdos_as_handed_and_the_floppy_replayed(arrived, wake):
    """Stage 1's inf_disk replay (the copy engine's recorder, every pointer recorded as handed), and the floppy's."""
    return case.merge_pokes(stage_1.gemdos_replayed_as_handed(arrived, wake), _the_floppy_replayed(arrived))


# ...Save Desktop's: app_save's own recorder (its F3 rows': each call's own frame bytes and no more — fslib's replay records
# six bytes whatever the function, a Dgetdrv's the stack beyond its frame), scripted with the ROM's own run in place's
# answers, the created handle's record laid as that run left it
SCRIPTED = f"{aes_deskapp.SCRIPTED}; the created handle's record the run's"


def gemdos_scripted(arrived, wake):
    ran = cdir.in_place(arrived, wake.receptions(arrived.chain))
    return case.merge_pokes(aes_deskapp.GEMDOS.pokes(ran.answers), ran.handles)


STAGINGS = {REPLAYED: stage_1.gemdos_replayed, GETREZ_STAGED: stage_1.getrez_staged, FLOPPY: gemdos_and_the_floppy_replayed,
            DISK_FLOPPY: gemdos_as_handed_and_the_floppy_replayed, SCRIPTED: gemdos_scripted}
# the stagings under which the run reaches the BIOS door: AES_BIOS_RETURN its own
PARKED = {FLOPPY: ds.BIOS_DOOR_PARKED, DISK_FLOPPY: ds.BIOS_DOOR_PARKED}
THE_PARK_DRIVE_CHECK_HOLDS = ds.RWABS_BACK          # drive_check's last BIOS call's site: its park, where an arrival holds it

# ---- A NAMED ROW'S BUDGET: one constant, every row that declares one (its own runs measured: 375,709 .. 726,111) ----------
ROW_INSNS = 3_700_000

# ---- THE ARRIVAL CLASSES (the cut's key, re-measured over every chain: `scratchpad/b6/W3a/S2/classes.json`) ---------------
DRIVE_OPENED, FILE_OPEN_ON_A_DRIVE, FOLDER_OPENED = "A: opened", "A: File > Open", "folder: opened"
TTP, CARTRIDGE = aes_desk.TTP_INSTALLED_THEN_CANCELLED, aes_desk.CARTRIDGE_OPENED
FILE_INFO, PROGRAM_INFO = "file: File > Show Info, Return", "files: the program selected, File > Show Info, Return"
DISK_INFO = "A: File > Show Info, Return"
PREFERENCES, SAVE_DESKTOP = "Options > Set Preferences, Return", "Options > Save Desktop, Return"
INSTALL_DISK = "A: Options > Install Disk Drive, Return"
INSTALL_APP = "files: the program selected, Options > Install Application, Return"
DESK_INFO = "Desk > Desktop Info, Return"
Class = namedtuple("Class", "name chain wake staging budget nth", defaults=(RETURN_TYPED, None, None, 0))
CLASSES = (
    Class(w3a.DO_OPEN, DRIVE_OPENED, IN_PLACE, FLOPPY, ROW_INSNS),
    Class(w3a.DO_OPEN, FOLDER_OPENED, IN_PLACE, FLOPPY, ROW_INSNS),
    Class(w3a.DO_OPEN, TTP, CANCEL_CLICKED, REPLAYED, ROW_INSNS),
    Class(w3a.DO_OPEN, CARTRIDGE, IN_PLACE, None, ROW_INSNS),
    Class(w3a.DO_OPEN, FILE_OPEN_ON_A_DRIVE, IN_PLACE, FLOPPY, ROW_INSNS),
    Class(w3a.DO_AOPEN, TTP, CANCEL_CLICKED, REPLAYED, ROW_INSNS),
    Class(w3a.DO_INFO, FILE_INFO, RETURN_TYPED, FLOPPY, ROW_INSNS),
    Class(w3a.DO_INFO, PROGRAM_INFO, RETURN_TYPED, FLOPPY, ROW_INSNS),
    Class(w3a.DO_INFO, DISK_INFO, RETURN_TYPED, DISK_FLOPPY),
    Class(w3a.DO_OPTNMENU, PREFERENCES, RETURN_TYPED, GETREZ_STAGED),
    Class(w3a.DO_OPTNMENU, SAVE_DESKTOP, RETURN_TYPED, SCRIPTED),
    Class(w3a.DO_OPTNMENU, INSTALL_DISK, RETURN_TYPED),
    Class(w3a.DO_OPTNMENU, INSTALL_APP, RETURN_TYPED, REPLAYED, ROW_INSNS),
    Class(w3a.DO_DESKMENU, DESK_INFO, RETURN_TYPED),
)
CLASSES_BY_ROUTINE = {w3a.DO_OPEN: 5, w3a.DO_AOPEN: 1, w3a.DO_INFO: 3, w3a.DO_OPTNMENU: 4, w3a.DO_DESKMENU: 1}
# ...where a class's row stands at another of its arrivals than its first: `{(routine, the chain held): (the first's, why)}`
REPRESENTED_BY = {
    (w3a.DO_OPEN, FOLDER_OPENED): ("file: double-clicked (the alert)", "the first's chain ends with the alert up: no hand ends it"),
    (w3a.DO_OPEN, TTP): (LAUNCHED, "the first is W6-R8's launch"),
}


def label_of(each):
    said = f"arrival {each.nth} of {each.chain!r}; {WAKE_NAMED[each.wake]}"
    return said + (f" [{each.staging}]" if each.staging else "")


def row_of(each):
    """The class's row that switches: the arrival's machine (its staging laid over it), its waits ended by its wake, its
    answer compared, AES_BIOS_RETURN its own where its run reaches the BIOS door."""
    arrived = da.arrival(each.name, each.chain, each.nth)
    machine = da.row_machine_of(arrived)
    if each.staging:
        machine = case.merge_pokes(machine, STAGINGS[each.staging](arrived, each.wake))
    return aes_switching.SwitchingRow(label_of(each), each.name, arrived.arguments, lambda: machine,
                                      each.wake.at_idle(each.chain), vdi.ALCYON[each.name].restype is not None,
                                      budget=each.budget, also_dropped=PARKED.get(each.staging, ()))


ROWS = {aes_switching.row_name(row): row for row in map(w3a.register_target_only_switching, map(row_of, CLASSES))}

# ---- THE CLASSES NO ROW HOLDS, by name: `{(routine, the class's key, its arrivals' chains): why}` -------------------------------
THE_SHOW_ARM = "the alert answered Show: pro_cmd and pro_run, the viewer run by the shell — W6-R8's launch arm (do_aopen's pro_run)"
THE_LAUNCH = REFUSED_ON_OUR_SHORE[LAUNCHED][0]
PRINT_SCREEN = ("the alert raised and not answered (the chain's last hand): its OK is gsx_hardcopy, a print — R-H-2's ledger "
                "is not authorized")
SHOWN = ("file: File > Open (the Show / Print / Cancel alert)", "file: shown, a key at its end — the file clicked, File > Open, shown again",
         "files: the long file shown, AUTO opened, its file shown, then File > Close in the restored window")
LONG_SHOWN = ("files: the long file shown, a blank at each page's end and at its end",
              "files: View > Show as Text, then the long file's line shown",
              "files: the long file shown, then the folder AUTO double-clicked in the restored window")
SCROLLED_SHOWN = ("files: the right arrow clicked, then the long file shown", "files: View > Sort by Size, then the long file shown")
REFUSED = {
    (w3a.DO_OPEN, "args 0x9 0x20 0x0 0x0", SHOWN): THE_SHOW_ARM,
    (w3a.DO_OPEN, "args 0xb 0x20 0x0 0x0", LONG_SHOWN): THE_SHOW_ARM,
    (w3a.DO_OPEN, "args 0xa 0x20 0x0 0x0", SCROLLED_SHOWN): THE_SHOW_ARM,
    (w3a.DO_AOPEN, "args 0x1 0x741e 0x0 0x9", (*SHOWN, "file: double-clicked (the alert)")): THE_SHOW_ARM,
    (w3a.DO_AOPEN, "args 0x1 0x741e 0x0 0xb", LONG_SHOWN): THE_SHOW_ARM,
    (w3a.DO_AOPEN, "args 0x1 0x741e 0x0 0xa", SCROLLED_SHOWN): THE_SHOW_ARM,
    (w3a.DO_AOPEN, "args 0x1 0x7472 0x1 0xc", (LAUNCHED,)): THE_LAUNCH,
    (w3a.DO_OPTNMENU, "args 0x2a 0x0 0x0 0x0", (aes_desk.PRINT_SCREEN_S_ALERT,)): PRINT_SCREEN,
}


# ---- THE FLIP ----------------------------------------------------------------------------------------------------------------
def test_the_five_are_flipped(blob):
    """THE FLIP PIN of stage 2's five (`aes_deskarrive.flipped`: each core called by its own thunk, each entry ours)."""
    da.flipped(blob, STAGE_2)


# ---- THE ROWS -----------------------------------------------------------------------------------------------------------------
def test_every_arrival_class_held_is_a_target_only_row_of_its_routine():
    """ONE ROW PER CLASS HELD, each registered target-only and switching; with the refused classes, the measured classes
    of stage 2's routines (the cut's 8 + 4 + 3 + 5 + 1, and the TTP chain's do_aopen class) every one."""
    held = [each.name for each in CLASSES]
    assert {name: held.count(name) for name in STAGE_2} == CLASSES_BY_ROUTINE
    assert len(ROWS) == len(CLASSES) and set(ROWS) <= set(aes_event.TARGET_ONLY_SWITCHING_ROWS)
    every = [name for name, _key, _chains in REFUSED] + held
    assert {name: every.count(name) for name in STAGE_2} == MEASURED_CLASSES


MEASURED_CLASSES = {w3a.DO_OPEN: 8, w3a.DO_AOPEN: 5, w3a.DO_INFO: 3, w3a.DO_OPTNMENU: 5, w3a.DO_DESKMENU: 1}


def test_each_class_s_arrival_holds_the_arguments_measured():
    assert {name: tuple(row.arguments) for name, row in ROWS.items()} == ARGUMENTS


ARGUMENTS = {   # `{row: its arrival's frame}`, as measured (`classes.json`)
    f"aes_do_open, {label_of(CLASSES[0])}": (8,),
    f"aes_do_open, {label_of(CLASSES[1])}": (9,),
    f"aes_do_open, {label_of(CLASSES[2])}": (12,),
    f"aes_do_open, {label_of(CLASSES[3])}": (7,),
    f"aes_do_open, {label_of(CLASSES[4])}": (8,),
    f"aes_do_aopen, {label_of(CLASSES[5])}": (95430, 1, 12, 65, 41472, 103532),
    f"aes_do_info, {label_of(CLASSES[6])}": (9,),
    f"aes_do_info, {label_of(CLASSES[7])}": (12,),
    f"aes_do_info, {label_of(CLASSES[8])}": (8,),
    f"aes_do_optnmenu, {label_of(CLASSES[9])}": (40,),
    f"aes_do_optnmenu, {label_of(CLASSES[10])}": (41,),
    f"aes_do_optnmenu, {label_of(CLASSES[11])}": (37,),
    f"aes_do_optnmenu, {label_of(CLASSES[12])}": (38,),
    f"aes_do_deskmenu, {label_of(CLASSES[13])}": (9,),
}


def _the_rom_s_run(name):
    """The registered row `name`'s ROM run, replayed over its settled machine: `(row, held, staged, final, writes)`."""
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
    _reference, _watch, final, writes = aes_switching._replayed(held.row, held.pokes)
    return held.row, held, make_image(held.pokes), final, writes


def test_a_row_under_drive_check_names_the_bios_park_held_at_its_arrival_or_stored_by_its_run():
    """THE PARK, R9's kind: each row whose run reaches the BIOS door names AES_BIOS_RETURN its own — and EITHER its
    arrival already holds drive_check's park there (the ROM's run stores the value the machine holds: `PARK_HELD`), OR
    the arrival holds none (0) and the ROM's run itself STORES INTO THE CELL, read off its write ledger (the door's park,
    a window by address: the orchestrator's ruling at this stage)."""
    parked = {name for name, row in ROWS.items() if row.also_dropped}
    assert parked == {name for name, each in zip(ROWS, CLASSES) if each.staging in PARKED} and len(parked) == PARKED_ROWS
    for name, each in zip(ROWS, CLASSES):
        if name not in parked:
            continue
        assert ROWS[name].also_dropped == ds.BIOS_DOOR_PARKED
        held_at_arrival = case.long_in(da.arrival(each.name, each.chain, each.nth).boot.ram, aes.AES_BIOS_RETURN)
        if each.chain in PARK_HELD:
            assert held_at_arrival == THE_PARK_DRIVE_CHECK_HOLDS, name
            continue
        assert held_at_arrival == 0, name
        _row, _held, _staged, final, writes = _the_rom_s_run(name)
        assert aes.AES_BIOS_RETURN in aes_switching.door_parks_stored(writes), name
        assert case.long_in(final, aes.AES_BIOS_RETURN) == THE_PARK_DRIVE_CHECK_HOLDS, name


PARKED_ROWS = 6
PARK_HELD = (FOLDER_OPENED, FILE_INFO, PROGRAM_INFO)    # the arrivals that hold drive_check's park already


# ---- THE DOOR'S PARK, A WINDOW BY ADDRESS (the orchestrator's ruling on R9's kind) — its crafted negatives, by name ------------
PARK = aes.AES_BIOS_RETURN
A_BYTE_WIDER = {   # `{what: a span one byte wider than the park's longword}`
    "a byte below the longword": (PARK - 1, PARK + aes.LONG_BYTES),
    "a byte past the longword": (PARK, PARK + aes.LONG_BYTES + 1),
}


# Spelt out, not read off `aes_switching.DOOR_PARK_CELLS`: a cell dropped from it must fail here, not vanish from the ids.
EACH_DOOR_S_PARK = {"the BIOS door": aes.AES_BIOS_RETURN, "the XBIOS door": aes.AES_XBIOS_RETURN}


@pytest.mark.parametrize("door", EACH_DOOR_S_PARK)
def test_the_door_s_park_window_is_the_longword_its_run_stores_and_no_wider(door):
    """THE WINDOW, each door's (the XBIOS twin crafted alone: no real row's park drops it): the park's longword, cut to
    the bytes the run stores — never wider, whatever the run stores beside it (the two cells abut); none where the run
    stores nothing of it."""
    cell = EACH_DOOR_S_PARK[door]
    around = frozenset(range(cell - 1, cell + aes.LONG_BYTES + 1))
    assert aes_switching.door_parks_stored(around)[cell] == ((cell, cell + aes.LONG_BYTES, aes_switching.DOOR_PARK_WHY),)
    assert aes_switching.door_parks_stored(frozenset({cell + 1, cell + 2}))[cell] == (
        (cell + 1, cell + 3, aes_switching.DOOR_PARK_WHY),)
    assert cell not in aes_switching.door_parks_stored(frozenset(range(cell - 1, cell)))


@pytest.mark.parametrize("what", A_BYTE_WIDER)
def test_a_span_one_byte_wider_than_the_park_is_refused_where_every_byte_is_stored_and_changed(what):
    """...a span one byte wider than the longword, every byte of it stored and changed: refused by the vouch (and the
    park's own three bytes, beside it, vouched for)."""
    lo, hi = A_BYTE_WIDER[what]
    staged, final = bytes(PARK + 2 * aes.LONG_BYTES), bytearray(PARK + 2 * aes.LONG_BYTES)
    final[lo:hi] = b"\x01" * (hi - lo)
    writes = frozenset(range(lo, hi))
    windows = aes_switching.door_park_windows(writes)
    why = ds.BIOS_DOOR_PARKED[0][2]
    assert w3a.drops_unvouched(((lo, hi, why),), staged, final, writes, windows) == [f"{lo:#x}..{hi:#x}: {why}"]
    assert w3a.drops_unvouched(ds.BIOS_DOOR_PARKED, staged, final, writes, windows) == []


THE_DRIVE_S_OPEN = f"aes_do_open, {label_of(CLASSES[4])}"      # File > Open on a drive: the arrival holds no park
DESK_INFO_ROW = f"aes_do_deskmenu, {label_of(CLASSES[13])}"     # a run that never reaches the BIOS door


# `{what: the bytes of that span File > Open's ROM run leaves unstored}` — the premise that says why each is refused
UNSTORED_ON_THE_DRIVE_S_OPEN = {
    "a byte below the longword": {PARK - 1},
    "a byte past the longword": set(),
}


@pytest.mark.parametrize("what", A_BYTE_WIDER)
def test_a_span_one_byte_wider_than_the_park_on_a_real_row_is_refused_by_the_vouch(what):
    """...ON A REAL ROW (File > Open on a drive, whose ROM run stores drive_check's park over 0): the span one byte wider
    refused by the vouch (its census half: `test_desk_w3a.py`, which reads the switching census). The two cases refuse
    for DIFFERENT reasons, asserted as the premise: "past" for the WIDTH (every byte stored — the extra one the XBIOS
    park's, stored unchanged — but the span lies in no one window); "below" because its extra byte is UNSTORED by this
    run (it pins "an unstored byte refused", not the width). The width below the longword is pinned by the pure test
    above (`test_a_span_one_byte_wider_than_the_park_is_refused_where_every_byte_is_stored_and_changed`)."""
    lo, hi = A_BYTE_WIDER[what]
    row, held, staged, final, writes = _the_rom_s_run(THE_DRIVE_S_OPEN)
    unstored = {at for at in range(lo, hi) if at not in writes}
    assert unstored == UNSTORED_ON_THE_DRIVE_S_OPEN[what], "the premise: which bytes the run stores"
    wider = (lo, hi, ds.BIOS_DOOR_PARKED[0][2])
    windows = w3a.by_nature_windows(row, held) + aes_switching.door_park_windows(writes)
    drops = tuple(drop for drop in held.drops if drop not in ds.BIOS_DOOR_PARKED) + (wider,)
    assert w3a.drops_unvouched(drops, staged, final, writes, windows) == [f"{lo:#x}..{hi:#x}: {wider[2]}"]


def test_the_park_s_reason_on_a_row_whose_run_never_stores_the_cell_is_refused_by_the_vouch():
    """THE STORE REQUIRED: the park named on Desk Info's row, whose ROM run never enters a door — refused by the vouch
    by the row's drop; its reason admits nothing (its census half: `test_desk_w3a.py`)."""
    row, held, _staged, _final, writes = _the_rom_s_run(DESK_INFO_ROW)
    assert not aes_switching.door_parks_stored(writes), "the premise: its run stores no door's park"
    parked_row, drops = row._replace(also_dropped=ds.BIOS_DOOR_PARKED), held.drops + ds.BIOS_DOOR_PARKED
    lo, hi, why = ds.BIOS_DOOR_PARKED[0]
    assert w3a.vouched_for(parked_row, held._replace(row=parked_row, drops=drops)) == [f"{lo:#x}..{hi:#x}: {why}"]

# ---- THE CLASSES NO ROW HOLDS: what each refusal says, read off the ROM's own walk of its chains -------------------------------
def _entered_by(chain, routine):
    return any(getattr(addrs, routine) in aes_desk.cycles_at(step.profile) for step in aes_desk.walked(chain).steps)


ALERT_LEFT_UP = (SHOWN[0], "file: double-clicked (the alert)")      # the chains whose last hand leaves the alert up


def test_every_show_class_s_chain_runs_pro_run_and_the_viewer():
    """THE SHOW ARM: every chain of a class refused as Show runs pro_run and the file viewer (show_file) in its own steps
    — the arm a row of it would hold — but the alert's chain itself, which ends with the alert up (no hand ends it)."""
    for (_name, _key, chains), why in REFUSED.items():
        if why != THE_SHOW_ARM:
            continue
        for chain in chains:
            if chain in ALERT_LEFT_UP:
                assert not _entered_by(chain, "AES_ROM_PRO_RUN"), chain
            else:
                assert _entered_by(chain, "AES_ROM_PRO_RUN") and _entered_by(chain, "AES_ROM_DESK_SHOW_FILE"), chain


def test_the_launch_and_print_screen_classes_are_the_standing_refusals():
    assert REFUSED[(w3a.DO_AOPEN, "args 0x1 0x7472 0x1 0xc", (LAUNCHED,))] == REFUSED_ON_OUR_SHORE[LAUNCHED][0]
    assert not _entered_by(aes_desk.PRINT_SCREEN_S_ALERT, "AES_ROM_GSX_HARDCOPY")
    assert _entered_by(aes_desk.PRINT_SCREEN_S_ALERT, "AES_ROM_DESK_FORM_ALERT")
