"""BAND 6 W3a, STAGE 1 — THE NINE DIALOGS, IN C AND FLIPPED (`src/desk/deskinf.c`'s seven: inf_show, inf_finish,
inf_file, inf_folder_dlg, inf_disk, inf_pref, opn_appl; the new `src/desk/deskins.c`'s two: ins_disk, ins_app),
HELD TARGET-ONLY (the user's R3: no host twin, no Tier 1 case):

  * THE FLIP: each one's Line-F table entry its thunk, on both blobs (`aes_deskarrive.flipped`); inf_show's call of
    hndl_msg — the cycle's one back-edge, the ROM's still until stage 3 — made BY THE ROM'S OWN CALL WORD
    (`aes_desk_w3a.CALLS_THROUGH_THE_TABLE`), once, in its body.
  * THE ROWS: ONE PER ARRIVAL CLASS THE W3a CUT MEASURED (its §2.2) — a row that switches over the ROM's own arrival
    machine (`aes_deskarrive.arrival`: a chain of the hands stopped at the routine's entry), its dialog's wait ended
    by the hand its chain gave there, registered TARGET-ONLY (`aes_desk_w3a.register_target_only_switching`: its
    by-nature drops vouched for by the ROM run's own write ledger, no companion). TWO labelled stagings, each
    the precedent's, said in its row's name: GEMDOS REPLAYED from the ROM's own run in place (G3's replay, F3's rows of the
    windows' openers) — the redraws of a window under the dialog (pro_chdir) and Show Info's count walk; and inf_pref's
    Getrez STAGED to the arrival's own shifter mode (app_blddesk's rows') — and a third, inf_disk's (below).
  * inf_disk's ONE CLASS, under the user's ruling of 2026-10-25: its dos_label hands GEMDOS ITS OWN FRAME'S ADDRESS
    (the DTA, the search's path) and its dos_space hands Dfree its own (the DISKINFO) — a stack address on either
    shore, which the replay's recorder keeps (ledger and DTA cell): "A FRAME ADDRESS HANDED TO GEMDOS", A BY-NATURE
    WINDOW of its own read off the ROM run's trap ledger by address (`aes_switching.frame_addresses_handed`), its
    refusals crafted below. Staged over the copy engine's recorder with Dfree's pointer RECORDED AS HANDED
    (`aes_deskdir.ENGINE_DFREE_AS_HANDED`): no recorder's zeros.
  * A NAMED ROW'S BUDGET (the user's ruling of 2026-10-24): the rows whose own run is past the derivation's default
    margin declare ONE NAMED CONSTANT (`DIALOG_ROW_INSNS`), held both ways by every derivation of the row.
"""
import re
from collections import namedtuple

import pytest

from harness import addrs, make_image

import aes
import aes_desk
import aes_desk_w3a as w3a
import aes_deskapp
import aes_deskarrive as da
import aes_deskbind as db
import aes_deskdir as cdir
import aes_desksupp as ds
import aes_deskfun as fun
import aes_event
import aes_fslib as fsl
import aes_shmain
import aes_switching
import case
import layouts
import preinit_snapshot
import routines
import transcription
import vdi
from aes_desk import SCAN_RETURN

STAGE_1 = w3a.STAGES[1]

# ---- THE HANDS THAT END A DIALOG'S WAIT, as its chain gave them (`aes_deskfun.Wake`) --------------------------------------
RETURN_TYPED = fun.keys_typed(SCAN_RETURN)
DIALOG_UP = -2                          # the chain's step that leaves the dialog up: the one before its last
CANCEL_CLICKED = fun.clicked(fun.dialog_button_point("Cancel"), DIALOG_UP)
WAKE_NAMED = {RETURN_TYPED: "Return at the first idle", CANCEL_CLICKED: "the dialog's Cancel clicked"}

# ---- THE STAGING, the precedent's, said in its row's name: GEMDOS REPLAYED (G3's replay — fslib's ledger and script,
# each call's own frame bytes recorded, pro_chdir's Dsetdrv and Dsetpath among them; `aes_desksupp.replay_pokes`), its
# script THE ROM'S OWN RUN IN PLACE from the arrival to its return, its wake taken in at its idle (`aes_deskdir.in_place`:
# each call's answer, the DTA each search left). A dialog over a window redraws it after the dialog (pro_chdir), and
# Show Info's count walks the folder (Fsetdta, Fsfirst, Fsnext) ----
REPLAYED = ds.REPLAYED


def gemdos_replayed(arrived, wake):
    """The replay's pokes (`aes_desksupp.replay_pokes`) over the script of the ROM's own run in place."""
    ran = cdir.in_place(arrived, wake.receptions(arrived.chain))
    fills = iter(ran.fills)
    script = tuple((answer, next(fills) if function in fsl.SEARCHES else fsl.NO_DTA)
                   for function, answer in zip(ran.functions, ran.answers))
    return ds.replay_pokes(script)


# ...and inf_pref's Getrez (the XBIOS's trap staged to answer THE ARRIVAL'S OWN SHIFTER MODE: `aes_deskapp.GETREZ_STAGED`,
# app_blddesk's rows): the ROM's Getrez reads the shifter, an I/O byte no seeded model serves
GETREZ_STAGED = aes_deskapp.GETREZ_STAGED


def getrez_staged(arrived, _wake):
    mode = arrived.boot.io[addrs.SHIFTER_RESOLUTION - preinit_snapshot.IO_AT] & aes_deskapp.SHIFTER_MODE_BITS
    return aes_shmain.getrez_pokes(mode)


# ...and inf_disk's: the COPY ENGINE'S recorder (the DTA each search left, Dfree's DISKINFO laid — `aes_deskdir.in_place`
# with `DFREE_FILLED`) with Dfree's pointer recorded AS HANDED, its script the ROM's own run in place: what the class "a
# frame address handed to GEMDOS" is read off
REPLAYED_AS_HANDED = f"{cdir.REPLAYED}; Dfree's DISKINFO laid, every pointer recorded as handed"


def gemdos_replayed_as_handed(arrived, wake):
    ran = cdir.in_place(arrived, wake.receptions(arrived.chain), captures=cdir.DFREE_FILLED)
    return cdir.replayed(ran, recorder=cdir.ENGINE_DFREE_AS_HANDED)


STAGINGS = {REPLAYED: gemdos_replayed, GETREZ_STAGED: getrez_staged, REPLAYED_AS_HANDED: gemdos_replayed_as_handed}


# ---- THE DECLARED BACK-EDGE, ITS COST (`aes_desk_w3a.ROWS_THROUGH_THE_TABLE`, Tier 3's general guard): a dialog over a
# window puts the window's redraw in the desk's pipe, and inf_show's C hands it to hndl_msg — THE ROM'S — by the ROM's
# own Line-F word. MEASURED, each such row on both blobs: 626 cycles in hndl_msg's body (the ROM's own run's 626, the
# same instructions over the same machine) and 682 in the Line-F handler's copy (the call and its return, and hndl_msg's
# one call of desk_clear's thunk). A row over no window queues no redraw for the desk: hndl_msg is not entered.
HNDL_MSG_S_REDRAW = w3a.ThroughTheTable(body=626, handler=682)

# ---- A NAMED ROW'S BUDGET: one constant, every row that declares one (its own runs measured: 444,737 .. 534,646) -------------
DIALOG_ROW_INSNS = 3_000_000

# ---- THE ARRIVAL CLASSES (the W3a cut's §2.2, `classes.json`): one row each --------------------------------------------------
DESK_INFO, PREFERENCES = "Desk > Desktop Info, Return", "Options > Set Preferences, Return"
DISK_INFO, INSTALL_DISK = "A: File > Show Info, Return", "A: Options > Install Disk Drive, Return"
FILE_INFO, FOLDER_INFO = "file: File > Show Info, Return", "folder: selected, File > Show Info, Return"
PROGRAM_INFO = "files: the program selected, File > Show Info, Return"
INSTALL_APP = "files: the program selected, Options > Install Application, Return"
OPEN_APPL = aes_desk.TTP_INSTALLED_THEN_CANCELLED
# ...and the fix pass's two (review RS1's F4: real data seeded by a hand, `aes_desk`'s block of them): the folder's
# dialog over a folder NOT EMPTY, and Install Application asked again of the program installed TOS-takes-parameters —
# its SECOND arrival (`nth` 1), the first the install itself
FILLED_FOLDER_INFO, ASKED_AGAIN = aes_desk.FILLED_FOLDER_INFO, aes_desk.TTP_INSTALLED_THEN_ASKED_AGAIN
Class = namedtuple("Class", "name chain wake staging budget nth", defaults=(RETURN_TYPED, None, None, 0))
WINDOWED = (FILE_INFO, FOLDER_INFO, PROGRAM_INFO, INSTALL_APP, OPEN_APPL,   # the chains with a window open under the dialog
            FILLED_FOLDER_INFO, ASKED_AGAIN)
CLASSES = (
    Class(w3a.INF_SHOW, DESK_INFO), Class(w3a.INF_SHOW, PREFERENCES), Class(w3a.INF_SHOW, DISK_INFO),
    Class(w3a.INF_SHOW, INSTALL_DISK), Class(w3a.INF_SHOW, FILE_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_SHOW, FOLDER_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS), Class(w3a.INF_SHOW, PROGRAM_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_SHOW, INSTALL_APP, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_FINISH, DISK_INFO), Class(w3a.INF_FINISH, FOLDER_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_FILE, FILE_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS), Class(w3a.INF_FILE, PROGRAM_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_FOLDER_DLG, FOLDER_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INF_DISK, DISK_INFO, staging=REPLAYED_AS_HANDED),
    Class(w3a.INF_PREF, PREFERENCES, staging=GETREZ_STAGED),
    Class(w3a.INS_DISK, INSTALL_DISK), Class(w3a.INS_APP, INSTALL_APP, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.OPN_APPL, OPEN_APPL, wake=CANCEL_CLICKED, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    # ---- the fix pass's two arrival classes (the cut's key: the routine's arguments, each new) ----
    Class(w3a.INF_FOLDER_DLG, FILLED_FOLDER_INFO, staging=REPLAYED, budget=DIALOG_ROW_INSNS),
    Class(w3a.INS_APP, ASKED_AGAIN, staging=REPLAYED, budget=DIALOG_ROW_INSNS, nth=1),
)
# ...how many each routine has: the cut's §2.2 (inf_show's eight trees, inf_finish's two, inf_file's two; one else)
# ...and the fix pass's: inf_folder_dlg's second, ins_app's second
CLASSES_BY_ROUTINE = {w3a.INF_SHOW: 8, w3a.INF_FINISH: 2, w3a.INF_FILE: 2, w3a.INF_FOLDER_DLG: 2, w3a.INF_DISK: 1,
                      w3a.INF_PREF: 1, w3a.INS_DISK: 1, w3a.INS_APP: 2, w3a.OPN_APPL: 1}


def label_of(each):
    said = f"arrival {each.nth} of {each.chain!r}; {WAKE_NAMED[each.wake]}"
    return said + (f" [{each.staging}]" if each.staging else "")


def row_of(each):
    """The class's row that switches: the arrival's machine (its staging laid over it), its wait ended by its wake, its
    answer compared where its core answers one."""
    arrived = da.arrival(each.name, each.chain, each.nth)
    machine = da.row_machine_of(arrived)
    if each.staging:
        machine = case.merge_pokes(machine, STAGINGS[each.staging](arrived, each.wake))
    return aes_switching.SwitchingRow(label_of(each), each.name, arrived.arguments, lambda: machine,
                                      each.wake.at_idle(each.chain), vdi.ALCYON[each.name].restype is not None,
                                      budget=each.budget)


def registered(each):
    """The class's row registered target-only — and, over a window, its cost through the table declared first."""
    row = row_of(each)
    if each.chain in WINDOWED:
        w3a.ROWS_THROUGH_THE_TABLE[aes_switching.row_name(row)] = HNDL_MSG_S_REDRAW
    return w3a.register_target_only_switching(row)


ROWS = {aes_switching.row_name(row): row for row in map(registered, CLASSES)}


# ---- THE FLIP ----------------------------------------------------------------------------------------------------------------
def test_the_nine_are_flipped(blob):
    """THE FLIP PIN of stage 1's nine (`aes_deskarrive.flipped`: each core called by its own thunk, each entry ours)."""
    da.flipped(blob, STAGE_1)


LINE_F_WORD_BYTES = 2


def _function_words(blob, symbol):
    """The words of `symbol`'s body in `blob`."""
    (found,) = [each for each in transcription.symbol_table(blob.elf) if each.name == symbol]
    data = blob.blob[found.start - blob.base:found.start - blob.base + found.size]
    return [case.word_in(data, at) for at in range(0, len(data) - 1, LINE_F_WORD_BYTES)]


def test_inf_show_calls_hndl_msg_by_the_rom_s_own_word_once_and_no_other_c_makes_a_line_f_call(blob):
    """THE DECLARED BACK-EDGE: inf_show's body holds hndl_msg's call word exactly once (`desk/deskinf.h`'s
    INF_SHOW_HNDL_MSG_CALL_WORD, the ROM's own at its site) — and none of the nine's other bodies holds it."""
    (call,) = w3a.CALLS_THROUGH_THE_TABLE.values()
    core = routines.core_symbol(w3a.INF_SHOW)
    assert _function_words(blob, core).count(call.word) == 1
    others = [routines.core_symbol(name) for name in STAGE_1 if name != w3a.INF_SHOW]
    assert not [symbol for symbol in others if call.word in _function_words(blob, symbol)]


ALIGNMENT_PAD = "nop"                    # what the linker fills a function's tail to its section's alignment with
A_JUMP_TO = re.compile(r"(?:jmp|bra[swl]?) (?:0x)?[0-9a-f]+ <([\w.]+)>")


def test_opn_appl_leaves_to_its_dialog_s_run_by_a_jump():
    """PD0 (opn_appl's Cancel, 16 B under W6-R4's gate): opn_appl's last instruction is a JUMP into its dialog's run
    (a sibling call: its frame, and its fields' call's arguments, popped first) — a call there would stand both under
    the dialog and the redraws after it."""
    body = transcription.listing(transcription.SHIPPED_ELF).split(f"<{routines.core_symbol(w3a.OPN_APPL)}>:\n", 1)[1]
    instructions = [line.split("\t")[-1].strip() for line in body.split("\n\n", 1)[0].splitlines()]
    last = [each for each in instructions if each != ALIGNMENT_PAD][-1]
    assert (found := A_JUMP_TO.fullmatch(last)) and found.group(1).split(".")[0] == "appl_dialog_run", last


# ---- THE ROWS -----------------------------------------------------------------------------------------------------------------
def test_every_arrival_class_the_cut_measured_is_a_target_only_row_of_its_routine():
    """ONE ROW PER CLASS (the cut's §2.2), each registered target-only and switching."""
    held = [(each.name, each.chain) for each in CLASSES]
    assert {name: sum(routine == name for routine, _chain in held) for name in STAGE_1} == CLASSES_BY_ROUTINE
    assert len(ROWS) == len(CLASSES) and set(ROWS) <= set(aes_event.TARGET_ONLY_SWITCHING_ROWS)


def test_each_class_s_arrival_holds_the_arguments_the_cut_classified():
    """The arrival each row stands on is its class's: its routine's frame as the cut read it (`classes.json`)."""
    assert {name: tuple(row.arguments) for name, row in ROWS.items()} == ARGUMENTS


ARGUMENTS = {   # `{row: its arrival's frame}`, as the cut classified each (`classes.json`)
    "aes_desk_inf_show, arrival 0 of 'Desk > Desktop Info, Return'; Return at the first idle":
        (59296, 0),
    "aes_desk_inf_show, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle":
        (61048, 0),
    "aes_desk_inf_show, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle":
        (58864, 0),
    "aes_desk_inf_show, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle":
        (59944, 0),
    "aes_desk_inf_show, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (58576, 0),
    "aes_desk_inf_show, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (59080, 0),
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (58576, 0),
    "aes_desk_inf_show, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (60208, 0),
    "aes_desk_inf_finish, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle":
        (58864, 8),
    "aes_desk_inf_finish, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (59080, 8),
    "aes_desk_inf_file, arrival 0 of 'file: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (82880, 103394),
    "aes_desk_inf_file, arrival 0 of 'files: the program selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (82880, 103514),
    "aes_desk_inf_folder_dlg, arrival 0 of 'folder: selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (82880, 103434),
    "aes_desk_inf_disk, arrival 0 of 'A: File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search; Dfree's DISKINFO laid, every pointer recorded as handed]":
        (65,),
    "aes_desk_inf_pref, arrival 0 of 'Options > Set Preferences, Return'; Return at the first idle [THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode]":
        (),
    "aes_desk_ins_disk, arrival 0 of 'A: Options > Install Disk Drive, Return'; Return at the first idle":
        (95178,),
    "aes_desk_ins_app, arrival 0 of 'files: the program selected, Options > Install Application, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (103532, 95346),
    "aes_desk_opn_appl, arrival 0 of 'files: the program installed as TOS-takes parameters, double-clicked, Cancel (the OPEN APPLICATION dialog: no launch)'; the dialog's Cancel clicked [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (103532, 16709168, 90572, 90705),
    "aes_desk_inf_folder_dlg, arrival 0 of 'files: the long file dragged onto the folder, then the folder selected, File > Show Info, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (82880, 103394),
    "aes_desk_ins_app, arrival 1 of 'files: the program installed as TOS-takes parameters, then Install Application again, Return'; Return at the first idle [GEMDOS REPLAYED: the ROM's run in place's answers and DTAs]":
        (103532, 95430),
}


# ---- THE REACH OF THE FIX PASS'S TWO CHAINS (review RS1F's G5): each arm its row was added for, read off the ROM's own
# run — so the rows' pins of those arms rest on what the chain's data reaches, not on a tally of its steps ----
AF_ISPARM = layouts.parse_constants((aes.INCLUDE / "desk" / "deskins.h",), known={**vdi.CONSTANTS, **aes.CONSTANTS})["AF_ISPARM"]


def test_the_program_asked_again_is_installed_tos_takes_parameters():
    """ins_app's TTP arm (`had & AF_ISPARM`): at the asked-again arrival the ANODE it is handed — TESTPRG.PRG's — holds
    the flag the first Install Application's OK stored."""
    arrived = da.arrival(w3a.INS_APP, ASKED_AGAIN, nth=1)
    _name, anode = arrived.arguments
    assert case.word_in(arrived.boot.ram, anode + db.DESK_GLOBALS["ANODE_FLAGS"]) & AF_ISPARM


def test_the_filled_folder_counts_a_file():
    """inf_folder_dlg's two counts told apart: the ROM's own run in place from the filled folder's arrival leaves its
    files' tally non-zero and unlike its folders' (`DESK_G_NFILES`, `DESK_G_NDIRS`) — the long file dragged in."""
    arrived = da.arrival(w3a.INF_FOLDER_DLG, FILLED_FOLDER_INFO)
    ram = cdir.in_place(arrived, RETURN_TYPED.receptions(arrived.chain)).returned.ram
    desk = case.long_in(ram, aes.AES_DESK_GLOBALS) & db.BUS
    files, folders = (case.long_in(ram, desk + db.DESK_GLOBALS[name]) for name in ("DESK_G_NFILES", "DESK_G_NDIRS"))
    assert files and files != folders, (files, folders)


def test_a_named_row_s_budget_is_the_one_constant():
    """THE BUDGET each declaring row's derivation reads is THE named constant (`is`); the rows that declare it are the
    ones whose own run is past the default margin (each a window's redraw or a dialog over a window)."""
    declaring = {name for name, row in ROWS.items() if row.budget is not None}
    assert declaring == {name for name, each in zip(ROWS, CLASSES) if each.budget is not None}
    assert all(ROWS[name].budget is DIALOG_ROW_INSNS for name in declaring) and len(declaring) == DECLARING


DECLARING = 12


def test_the_rows_through_the_table_are_the_dialogs_over_a_window():
    """THE DECLARED BACK-EDGE'S ROWS: every row over a window, each at hndl_msg's redraw's measured cost, and no other."""
    over_a_window = {name for name, each in zip(ROWS, CLASSES) if each.chain in WINDOWED}
    assert {name: cost for name, cost in w3a.ROWS_THROUGH_THE_TABLE.items() if name in ROWS} == dict.fromkeys(over_a_window, HNDL_MSG_S_REDRAW)
    assert set(w3a.ROWS_THROUGH_THE_TABLE) <= set(ROWS) and len(over_a_window) == THROUGH_THE_TABLE


THROUGH_THE_TABLE = 12


# ---- THE CLASS "A FRAME ADDRESS HANDED TO GEMDOS" (the user's ruling of 2026-10-25), on inf_disk's row ----------------------
# Its windows, read off the ROM run's own recorder (`aes_switching.frame_addresses_handed`): the argument longwords of the
# calls whose frame address the run hands — dos_space's Dfree (its DISKINFO), dos_label's Fsetdta (its DTA) and Fsfirst
# (its path), the ledger's calls 3, 4 and 5 — and the recorder's DTA cell, holding that Fsetdta's address
DISK_ROW = next(name for name, each in zip(ROWS, CLASSES) if each.name == w3a.INF_DISK)
# ...in the run's ledger: the count's Fsetdta, Fsfirst and Fsnext (calls 0-2, the arrival's own DTA), then these three
DFREE_CALL, FSETDTA_CALL, FSFIRST_CALL = 3, 4, 5
RECORDER = cdir.ENGINE_DFREE_AS_HANDED
FRAME_ADDRESS_WINDOWS = (*((RECORDER.ledger.first + nth * RECORDER.ledger.stride + aes.WORD_BYTES,
                            RECORDER.ledger.first + nth * RECORDER.ledger.stride + aes.WORD_BYTES + aes.LONG_BYTES)
                           for nth in (DFREE_CALL, FSETDTA_CALL, FSFIRST_CALL)),
                         (RECORDER.dta_cell, RECORDER.dta_cell + aes.LONG_BYTES))


def _the_rom_s_run(name):
    """The row `name`'s settled `Registered`, and its ROM run's replay: `(held, its machine's image, the memory it left,
    its write ledger)`."""
    held = aes_event.TARGET_ONLY_SWITCHING_ROWS[name]
    _reference, _watch, final, writes = aes_switching._replayed(held.row, held.pokes)
    return held, make_image(held.pokes), final, writes


def _handed(drops):
    return [(lo, hi) for lo, hi, why in drops if why == aes_switching.FRAME_ADDRESS_WHY]


def test_inf_disk_s_frame_addresses_handed_to_gemdos_are_the_class_s_windows_and_its_drops():
    """THE CLASS ON ITS ROW: its windows over the ROM's run are dos_space's and dos_label's three frame addresses in the
    ledger and the DTA cell — and the row's drops of the class are exactly those, every byte stored by the run."""
    held, _staged, final, writes = _the_rom_s_run(DISK_ROW)
    assert _handed(aes_switching.frame_addresses_handed(final)) == list(FRAME_ADDRESS_WINDOWS)
    assert _handed(held.drops) == list(FRAME_ADDRESS_WINDOWS)
    assert all(at in writes for lo, hi in FRAME_ADDRESS_WINDOWS for at in range(lo, hi))


FUNCTION_WORD_DROP = (RECORDER.ledger.first + FSETDTA_CALL * RECORDER.ledger.stride,
                      RECORDER.ledger.first + FSETDTA_CALL * RECORDER.ledger.stride + aes.WORD_BYTES,
                      aes_switching.FRAME_ADDRESS_WHY)


def test_a_drop_of_the_class_s_reason_outside_a_trap_argument_is_refused_by_the_vouch():
    """CRAFTED: the class's reason named by the row's own hand over the ledger's function word of dos_label's Fsetdta —
    a byte the run stores and changes, and no argument — is no window: THE VOUCH refuses it (and the switching census
    refuses it registered: `test_aes_event`'s own crafted case, `FUNCTION_WORD_DROP`)."""
    lo, hi, why = FUNCTION_WORD_DROP
    row = ROWS[DISK_ROW]._replace(also_dropped=(FUNCTION_WORD_DROP,))
    _row, held = aes_switching.held_of(row)
    assert w3a.vouched_for(row, held) == [f"{lo:#x}..{hi:#x}: {why}"]


def test_a_frame_address_outside_the_stack_band_is_no_window_and_its_drop_is_refused():
    """CRAFTED: dos_label's Fsetdta pointer moved ONE PAST THE STACK BAND in the run's memory — it is then no window, nor
    the DTA cell that holds the same address no more of a handed one; the row's drops of both, vouched over those
    windows, are refused by name."""
    held, staged, final, writes = _the_rom_s_run(DISK_ROW)
    crafted = bytearray(final)
    at = FRAME_ADDRESS_WINDOWS[1][0]
    crafted[at:at + aes.LONG_BYTES] = case.STACK_BAND.stop.to_bytes(aes.LONG_BYTES, "big")
    handed = aes_switching.frame_addresses_handed(crafted)
    assert _handed(handed) == [FRAME_ADDRESS_WINDOWS[0], FRAME_ADDRESS_WINDOWS[2]]
    others = tuple(window for window in w3a.by_nature_windows(held.row, held) if window[2] != aes_switching.FRAME_ADDRESS_WHY)
    refused = w3a.drops_unvouched(held.drops, staged, final, writes, others + handed)
    assert refused == [f"{lo:#x}..{hi:#x}: {aes_switching.FRAME_ADDRESS_WHY}" for lo, hi in (FRAME_ADDRESS_WINDOWS[1], FRAME_ADDRESS_WINDOWS[3])]


# ...and CALLS CRAFTED IN THE LEDGER (review RS1F's G1): a word that is no pointer next to one — an attribute, a date, a
# handle — read as a longword with its neighbour lands in the band; the class reads only each function's pointer
# arguments (`aes_shell.POINTER_ARGUMENTS`, less what the recorder substitutes), so none is a window. `(the call
# replaced, its function, its frame's fields)`
STRADDLING = {
    # A: dos_label's Fsfirst handed a path OUTSIDE the band, its attribute word 8 (the run's own) kept: $2308 0008
    "Fsfirst: a path outside the band, attribute 8": (FSFIRST_CALL, cdir.FSFIRST, (("l", 0x00012308), ("w", 0x0008))),
    # B: the engine's Fdatime, whose pointer its recorder REPLACES by the time and date it points at: a file dated
    # 8 August ($1108, any year) on handle 6 reads $11080006
    "the engine's Fdatime: dated $1108, handle 6": (DFREE_CALL, cdir.FDATIME,
                                                    (("w", 0x1234), ("w", 0x1108), ("w", 6), ("w", 0))),
    # ...and at its pointer's own offset: stamped 00:00:14 ($0007) on 1 August 2100 ($f101) it reads $0007f101 there,
    # inside the band — no pointer all the same, its recorder having replaced it
    "the engine's Fdatime: stamped $0007 $f101": (DFREE_CALL, cdir.FDATIME, (("w", 0x0007), ("w", 0xF101), ("w", 6), ("w", 0))),
    # C: Fread on handle 8: the handle and its count's high word read $00080000
    "Fread: handle 8, count $200": (DFREE_CALL, cdir.FREAD, (("w", 8), ("l", 0x200), ("l", 0x00012000))),
}


@pytest.mark.parametrize("crafted", STRADDLING)
def test_a_word_beside_a_pointer_is_no_frame_address(crafted):
    """CRAFTED, over inf_disk's ROM run: the call replaced gives no window — the class's windows are the run's own less
    the one that call's pointer gave, and none new."""
    nth, function, fields = STRADDLING[crafted]
    _held, _staged, final, _writes = _the_rom_s_run(DISK_ROW)
    image = bytearray(final)
    entry = RECORDER.ledger.first + nth * RECORDER.ledger.stride
    frame = RECORDER.ledger.frame(*fields)[:RECORDER.recorded_bytes]
    image[entry:entry + aes.WORD_BYTES + len(frame)] = function.to_bytes(aes.WORD_BYTES, "big") + frame
    replaced = FRAME_ADDRESS_WINDOWS[(DFREE_CALL, FSETDTA_CALL, FSFIRST_CALL).index(nth)]
    assert _handed(aes_switching.frame_addresses_handed(image)) == [window for window in FRAME_ADDRESS_WINDOWS if window != replaced]


def test_a_row_of_another_kind_has_no_window_of_the_class():
    """UNAFFECTED: the folder's dialog (GEMDOS replayed by fslib's recorder, handed no frame address) and Desk Info (no
    recorder at all) — the class reads no window off either run, and neither row drops one."""
    for name, each in zip(ROWS, CLASSES):
        if (each.name, each.chain) in ((w3a.INF_FOLDER_DLG, FOLDER_INFO), (w3a.INF_SHOW, DESK_INFO)):
            held, _staged, final, _writes = _the_rom_s_run(name)
            assert aes_switching.frame_addresses_handed(final) == () and not _handed(held.drops), name


# ---- THE DECLARED BACK-EDGE'S GUARD, its refusals crafted by name (review RS1's F3): over real rows, the declaration moved ---
THROUGH_A_WINDOW = next(name for name, each in zip(ROWS, CLASSES) if each.name == w3a.OPN_APPL)
OVER_NO_WINDOW = next(name for name, each in zip(ROWS, CLASSES) if (each.name, each.chain) == (w3a.INF_SHOW, DESK_INFO))
# ...the general equality's own words (`bench/tier3.py`): the back-edge's whole cost, body and handler, outside any window
AES_ROM_SPENT_UNDECLARED = re.escape(f"OUR run spent {HNDL_MSG_S_REDRAW.body + HNDL_MSG_S_REDRAW.handler} cycles at the PCs "
                                     f"of the AES's own ROM where its windows of the ROM's process hold 0 — ")


def test_the_back_edge_s_guard_refuses_a_declared_row_whose_run_never_reaches_hndl_msg(blob, monkeypatch):
    monkeypatch.setitem(w3a.ROWS_THROUGH_THE_TABLE, OVER_NO_WINDOW, HNDL_MSG_S_REDRAW)
    with pytest.raises(AssertionError, match=rf"OUR run spent 0 cycles in the body .* declares {HNDL_MSG_S_REDRAW.body}"):
        aes_switching.measured_on(blob, ROWS[OVER_NO_WINDOW])


def test_the_back_edge_s_guard_refuses_an_undeclared_row_whose_run_reaches_hndl_msg(blob, monkeypatch):
    monkeypatch.delitem(w3a.ROWS_THROUGH_THE_TABLE, THROUGH_A_WINDOW)
    with pytest.raises(AssertionError, match=AES_ROM_SPENT_UNDECLARED):
        aes_switching.measured_on(blob, ROWS[THROUGH_A_WINDOW])


def test_the_back_edge_s_guard_refuses_a_body_figure_off_by_one(blob, monkeypatch):
    off_by_one = HNDL_MSG_S_REDRAW._replace(body=HNDL_MSG_S_REDRAW.body + 1)
    monkeypatch.setitem(w3a.ROWS_THROUGH_THE_TABLE, THROUGH_A_WINDOW, off_by_one)
    with pytest.raises(AssertionError, match=rf"OUR run spent {HNDL_MSG_S_REDRAW.body} cycles in the body .* declares {off_by_one.body}"):
        aes_switching.measured_on(blob, ROWS[THROUGH_A_WINDOW])
