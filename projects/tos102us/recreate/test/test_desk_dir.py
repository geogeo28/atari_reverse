"""THE COPY ENGINE'S HELPERS (`src/desk/deskdir.c`; band 6 wave 1b, group G4, unit C): fourteen routines of
`$fdcf04..$fdd917` — the dialogs' drawing, the path editors, the DOS verdict and the delete, the check that a folder is
not copied into itself — HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2, TEN OF THEM FLIPPED,
the four dialog drawers that call unit D's objc_draw (draw_dial, show_dial, draw_fld and do_namecon, which calls two of
them) SINCE SLICE F2c, with objc_draw: the Line-F table's entry for each is its thunk, and every case of theirs at an
arrival is a Tier 3 row (`ROWS`, below).

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`) — four of the routines only at the chains this wave added
    (`aes_desk`'s group G4 block: the name conflict, a folder copied into a folder, a folder holding a folder deleted)
    — or A LABELLED ARGUMENT CLASS, said in its name, where no run reaches the arm. Never a poke.
  * WHAT YIELDS is a row that switches, through its wake where it waits (do_namecon's dialog, an alert answered by
    Return); the rest are the kit's plain differential. d_dofdel's `trap #1` is SCRIPTED (`SCRIPTED`, in the id):
    `aes_deskleaves`' recording trap answers what GEMDOS answered the ROM's own run in place.
  * D0 AT RETURN: held at the declared width where the C answers; the five `void` routines (draw_dial, show_dial,
    draw_fld, get_fname, do_namecon) leave their last callee's word in the ROM: A NAMED, COUNTED DIVERGENCE, read by no
    instruction of the ROM (`aes_deskbind.answer_readers`).
  * HELD IN TWO HALVES, NOT ONE CASE: d_dofdel where GEMDOS refuses the delete (the read-only file): the scripted trap
    cannot be taken through the companion, and the refusal's alert yields. dos_delete's EACCDN is unit O's arrival case
    and d_errmsg's alert this battery's; d_dofdel's own failing arm is the class of an answer that shows no alert.
  * UNPINNED BY NAME: d_errmsg failing with an answer above -32 at its own entry (no run leaves one: the class above
    reaches that arm inside d_dofdel); d_errmsg's alert BOUNDARY itself, an answer of exactly -32 alerted (no run
    reaches -32..-35: EACCDN's -36 is the only answer alerted — the slice F2 review's R1, its MB3 survives; no poked
    class, by the policy); and par_chk's refusal by a run (a folder dragged into its own window: the second
    window's folder opens over a forced media change, which the model refuses by name — tried, `aes_desk`'s block).
"""
import functools
import struct
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_boot
import aes_deskarrive as da
import aes_deskbind as db
import aes_deskdir as cdir
import aes_deskleaves as dl
import aes_event
import case
import layouts
from aes_desk import EMPTIED_INFO, KEY_RELEASED, READ_ONLY_COPIED, SCAN_B, SCAN_BACKSPACE, SCAN_RETURN

Case = da.Case
RETURN = da.RETURN_TYPED
P = cdir.PREFIX
DRAW_DIAL, DO_NAMECON, HIDE_DIAL, SHOW_DIAL, DRAW_FLD = (P + short for short in ("DRAW_DIAL", "DO_NAMECON", "HIDE_DIAL", "SHOW_DIAL", "DRAW_FLD"))
ADD_PATH, SUB_PATH, ADD_FNAME, DEL_FNAME, GET_FNAME = (P + short for short in ("ADD_PATH", "SUB_PATH", "ADD_FNAME", "DEL_FNAME", "GET_FNAME"))
D_ERRMSG, D_DOFDEL, PATH_PART, PAR_CHK = (P + short for short in ("D_ERRMSG", "D_DOFDEL", "PATH_PART", "PAR_CHK"))
VOID = (DRAW_DIAL, SHOW_DIAL, DRAW_FLD, GET_FNAME, DO_NAMECON)

FILE_CONFLICT = "folder: the file dragged onto it again, Return — the name conflict, Return"
FOLDER_CONFLICT = "folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)"
UNCONFIRMED_CONFLICT = "folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return"
B_INTO_A, A_DELETED = "folders: B dragged onto A, Return", "folders: A (holding B) dragged to the trash, OK"
TRASHED, DENIED = "file: dragged to the trash, OK", "file: read-only, dragged to the trash, OK — access denied, Return"
NEW_FOLDER, COPIED = "folder: File > New Folder, 'A', Return", "folder: the file dragged onto it, Return"
FOLDER_TRASHED, AUTO_TRASHED = "folder: dragged to the trash, OK", "files: the folder (not empty) dragged to the trash, OK"
README_COPIED, READ_ONLY = "files: the long file dragged onto the folder, Return", "file: File > Show Info, Read-Only pressed, Return"
EACCDN = aes.signed(addrs.parse(aes.INCLUDE / "gemdos" / "fs.h")["GEMDOS_EACCDN"], bits=32)   # access denied
GEMDOS_ERROR = -1                       # GEMDOS's generic ERROR: an answer above -32, which d_errmsg shows no alert for
PAR_CHK_DESTINATION = 2                 # par_chk's third argument
FPD = layouts.parse_constants((db.GLOBALS_HEADER, aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)


def _the_buffer_par_chk_left(arrived):
    """par_chk's own arguments, the destination its second path buffer — where its last turn (the drag of B onto A) left
    "A:\\B\\*.*": the selected folder B's own path."""
    desk = case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS)
    return (*arrived.arguments[:PAR_CHK_DESTINATION], desk + cdir.CONSTANTS["DESK_PAR_DESTINATION"])


def _another_drive(arrived):
    """...the destination one byte on: its first character another drive's letter (`:`)."""
    return (*arrived.arguments[:PAR_CHK_DESTINATION], arrived.arguments[PAR_CHK_DESTINATION] + 1)


def _every_folder_selected(arrived):
    """LAID: every folder of par_chk's list SELECTED on the screen's tree (the chains select one icon at a time; the
    window B was dragged from holds A and B, two folders)."""
    ram, desk = arrived.boot.ram, case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & db.BUS
    objects, pokes = desk + db.DESK_GLOBALS["DESK_G_SCREEN_OBJECTS"], {}
    node = arrived.arguments[1] & db.BUS
    while node:
        if ram[node + FPD["FNODE_ATTR"]] == FPD["FNODE_ATTR_SUBDIR"]:
            state = objects + case.word_in(ram, node + FPD["FNODE_OBID"]) * aes.OB_BYTES + aes.OB_STATE
            pokes[state] = struct.pack(">H", case.word_in(ram, state) | 1 << aes.OB_STATE_SELECTED_BIT)
        node = case.long_in(ram, node + FPD["FNODE_NEXT"]) & db.BUS
    assert len(pokes) == FOLDERS_IN_A, f"{len(pokes)} folders in the list"
    return pokes


FOLDERS_IN_A = 2
LEAST_ALERTED = cdir.CONSTANTS["D_ERRMSG_LEAST_ALERTED"]


def _failed_with(answer):
    """LAID: the DOS glue's verdict failed (AES_DOS_ERR 1) and its answer word `answer` (AES_DOS_AX)."""
    return lambda _arrived: {aes.AES_DOS_ERR: struct.pack(">H", 1), aes.AES_DOS_AX: struct.pack(">h", answer)}


MENU_BAR = 1                            # the menu tree's bar: an object with children, and they theirs


def _the_menu(arrived):
    """The menu bar's tree in place of the dialog's (gl_mntree): a tree three levels deep, where the desk's dialogs are
    one — so a depth handed objc_draw tells."""
    return (case.long_in(arrived.boot.ram, aes.AES_GL_MNTREE),)


def _the_menu_s_bar(arrived):
    return (case.long_in(arrived.boot.ram, aes.AES_GL_MNTREE), MENU_BAR)


def Plain(*fields, **named):
    return Case(*fields, yields=False, **named)


CASES = (
    # the dialogs: the name conflict's tree drawn again and the copy dialog's (`$fdcf62`, `$fdcf96`)
    Case(DRAW_DIAL, FILE_CONFLICT, 0), Case(DRAW_DIAL, FILE_CONFLICT, 1), Case(DRAW_DIAL, FOLDER_CONFLICT, 0),
    Case(DRAW_DIAL, FILE_CONFLICT, 0, arguments=_the_menu,
         why="the menu bar's tree, three levels deep (the desk's dialogs are one): the depth objc_draw is handed tells"),
    # do_namecon: the conflict over a copy dialog that is up (a file's, a folder's), and with copies unconfirmed — the
    # dialog put up the first time, no copy dialog
    Case(DO_NAMECON, FILE_CONFLICT, wake=RETURN), Case(DO_NAMECON, FOLDER_CONFLICT, wake=RETURN),
    Case(DO_NAMECON, UNCONFIRMED_CONFLICT, wake=RETURN),
    Case(HIDE_DIAL, TRASHED), Case(HIDE_DIAL, NEW_FOLDER), Case(HIDE_DIAL, COPIED),
    Case(SHOW_DIAL, TRASHED), Case(SHOW_DIAL, NEW_FOLDER), Case(SHOW_DIAL, COPIED),
    Case(DRAW_FLD, TRASHED), Case(DRAW_FLD, FOLDER_TRASHED),
    Case(DRAW_FLD, TRASHED, arguments=_the_menu_s_bar,
         why="the menu bar, an object with children (every field the desk draws has none): drawn alone, depth 0"),
    # the path editors
    Plain(ADD_PATH, FOLDER_TRASHED), Plain(ADD_PATH, AUTO_TRASHED), Plain(ADD_PATH, A_DELETED, 1),
    Plain(SUB_PATH, A_DELETED), Plain(SUB_PATH, A_DELETED, 1),
    Plain(ADD_FNAME, TRASHED), Plain(ADD_FNAME, NEW_FOLDER), Plain(ADD_FNAME, COPIED, 1),
    Plain(DEL_FNAME, TRASHED), Plain(DEL_FNAME, COPIED), Plain(DEL_FNAME, AUTO_TRASHED),
    Plain(GET_FNAME, COPIED), Plain(GET_FNAME, COPIED, 1), Plain(GET_FNAME, FILE_CONFLICT),
    # d_errmsg: done (twice), and GEMDOS's EACCDN's alert answered
    Plain(D_ERRMSG, TRASHED), Plain(D_ERRMSG, READ_ONLY), Case(D_ERRMSG, DENIED, wake=RETURN),
    Case(D_ERRMSG, TRASHED, wake=RETURN, arguments=(),
         why="failed with -32 exactly (no GEMDOS call of the chains answers it): alerted — the bound is the ROM's `bgt`",
         laid=("AES_DOS_ERR 1, AES_DOS_AX -32", _failed_with(LEAST_ALERTED))),
    # par_chk: no folder selected (a file copied), a folder copied (its paths walked), and the two arms no run reaches
    Plain(PAR_CHK, COPIED), Plain(PAR_CHK, README_COPIED), Plain(PAR_CHK, FOLDER_CONFLICT), Plain(PAR_CHK, B_INTO_A),
    Case(PAR_CHK, B_INTO_A, wake=RETURN, arguments=_the_buffer_par_chk_left,
         why="the destination par_chk's OWN second path buffer, where its last turn left `A:\\B\\*.*` — an aliased buffer no "
             "ROM caller hands: a folder into itself, refused, its alert answered"),
    # (the destination the source's own path, the window's root: the walk ends at its "*.*" for either folder, so no
    # alert either way — and the source's copy the desk keeps in g_tmppth is the chosen folder's path)
    Plain(PAR_CHK, B_INTO_A, arguments=lambda a: (a.arguments[0], a.arguments[1], a.arguments[0]),
          why="two folders selected (the chains select one icon at a time), the destination the source's own root: the "
              "LAST one's path built",
          laid=("every folder of the list SELECTED", _every_folder_selected)),
    Plain(PAR_CHK, B_INTO_A, arguments=_another_drive, why="a destination of another drive (the model holds A: alone)"),
    Plain(PATH_PART, FOLDER_CONFLICT, 0), Plain(PATH_PART, FOLDER_CONFLICT, 1), Plain(PATH_PART, B_INTO_A, 2),
)
BY_LABEL = da.by_label(CASES)


@pytest.mark.parametrize("name", BY_LABEL)
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine from the same entry — through the companion where it yields
    (the idles, the image at every dispatch), else the plain differential — its answer at its width where the C has one."""
    each = BY_LABEL[name]
    da.tier_1(each, answered=each.name not in VOID)


# ---- d_dofdel: dos_delete's `trap #1` SCRIPTED ----------------------------------------------------------------------------
SCRIPTED = "GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers"      # unit O's words (`test_desk_leaves`)
DELETES = {"a file deleted": (TRASHED, 0), "a file inside a folder deleted": (AUTO_TRASHED, 0)}


def _fdelete_answered(arrived):
    """What GEMDOS answered the ROM's own run of d_dofdel IN PLACE: D0 where `__DOS`'s trap returns."""
    back = aes_boot.continued(arrived.boot, (), arrived.budget, dl.GEM_DOS_BACK, da.entry_of(arrived.name))
    return aes.signed(back.registers["d0"], bits=32)


def _scripted(arrived, answers):
    return aes.run_function(arrived.name, arrived.arguments, dl.megabyte(arrived, dl.GEMDOS.pokes(answers)), hook=dl.scripted_hook,
                            poison=False)


@pytest.mark.parametrize("what", DELETES, ids=[f"{what} — {SCRIPTED}" for what in DELETES])
def test_d_dofdel_at_its_arrival_with_gemdos_scripted_is_the_rom_s(what):
    """THE DELETE AT ITS ARRIVAL: GEMDOS answered as it answered the ROM's run in place (done, 0), the frame Fdelete
    was handed recorded on both shores, d_errmsg's 1 answered."""
    chain, nth = DELETES[what]
    arrived = da.arrival(D_DOFDEL, chain, nth)
    answered = _fdelete_answered(arrived)
    assert answered == 0
    assert _scripted(arrived, [answered]).answer() == cdir.CONSTANTS["D_ERRMSG_DONE"]


def test_d_dofdel_an_argument_class_gemdos_answering_an_error_above_minus_32_fails_with_no_alert_scripted():
    """ARGUMENT CLASS, SCRIPTED (no GEMDOS answers Fdelete above -32 but 0): ERROR (-1) — failed, 0, and no alert
    shown (the run does not yield): d_errmsg's arm of an answer above -32, reached through d_dofdel."""
    arrived = da.arrival(D_DOFDEL, TRASHED)
    assert _scripted(arrived, [GEMDOS_ERROR]).answer() == cdir.CONSTANTS["D_ERRMSG_FAILED"]


def test_the_denied_delete_is_held_in_two_halves_each_at_its_arrival():
    """d_dofdel OF THE READ-ONLY FILE: the ROM's run in place answers EACCDN, and its next call is d_errmsg, entered on
    the machine this battery's d_errmsg case takes (its arrival in the same chain) — dos_delete's own EACCDN arrival is
    unit O's (`test_desk_leaves.GLUE_ARRIVALS`)."""
    arrived = da.arrival(D_DOFDEL, DENIED)
    assert _fdelete_answered(arrived) == EACCDN
    assert any(each.name == D_ERRMSG and each.chain == DENIED for each in CASES)


ARRIVALS, CLASSES = 38, 6       # ...and d_dofdel's two arrivals and one class, scripted, below them


def test_every_routine_of_the_unit_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES if not each.why]
    assert {each.name for each in at_its_own} | {D_DOFDEL} == set(cdir.UNIT_C)
    assert (len(at_its_own), len(CASES) - len(at_its_own)) == (ARRIVALS, CLASSES)


def test_the_arrivals_do_namecon_was_chosen_for_take_its_arms():
    """do_namecon's arms are its machine's, not its arguments: the two conflicts under a copy dialog find it up and
    their dialog up already (the arm that draws it again and redraws the copy dialog's item); copies unconfirmed, both
    flags are clear (the arm that puts the dialog up and marks it)."""
    flags = {}
    for chain in (FILE_CONFLICT, FOLDER_CONFLICT, UNCONFIRMED_CONFLICT):
        ram = da.arrival(DO_NAMECON, chain).boot.ram
        desk = case.long_in(ram, aes.AES_DESK_GLOBALS)
        flags[chain] = tuple(case.word_in(ram, desk + cdir.CONSTANTS[flag]) for flag in ("DESK_NAMECON_UP", "DESK_COPY_DIALOG_UP"))
    assert flags == {FILE_CONFLICT: (1, 1), FOLDER_CONFLICT: (1, 1), UNCONFIRMED_CONFLICT: (0, 0)}


NO_WORD_IN_C = 16


def test_the_answers_the_c_has_not_are_counted_and_read_by_no_caller():
    """THE DIVERGENCE, NAMED AND COUNTED: the cases of the five `void` routines — and no instruction of the ROM reads
    their D0; the answers the C has are read where the table says."""
    assert sum(1 for each in CASES if each.name in VOID) == NO_WORD_IN_C
    read = {name: len(db.answer_readers(da.entry_of(name))) for name in cdir.UNIT_C}
    assert {name: sites for name, sites in read.items() if sites} == {D_ERRMSG: 15, D_DOFDEL: 2, PATH_PART: 2, PAR_CHK: 1}


def test_the_strings_the_unit_names_are_the_rom_s():
    """The ROM's "\\*.*" seven times and "*.*" twice, at the addresses the header names — and the copy engine's five
    count templates, "%W" each (band 6 wave 2)."""
    texts = {name: bytes(BASE_IMAGE[at:BASE_IMAGE.index(b"\0", at)]) for name, at in cdir.CONSTANTS.items()
             if name.startswith("AES_DESK_") and name.endswith(("TAIL", "SOURCE", "DESTINATION", "FORMAT"))}
    tails = ("ADD_PATH", "SUB_PATH", "DEL_FNAME", "PAR_CHK", "DOOP_RMDIR", "DOOP_MKDIR", "DIR_OP_FOLDER")
    formats = ("DIR_OP_FILES", "DIR_OP_FOLDERS", "DIR_OP_FILE", "DOOP_FOLDER", "DOOP_FILE")
    assert texts == {**{f"AES_DESK_{tail}_TAIL": b"\\*.*" for tail in tails},
                     **{f"AES_DESK_{each}_FORMAT": b"%W" for each in formats},
                     "AES_DESK_PAR_CHK_END_SOURCE": b"*.*", "AES_DESK_PAR_CHK_END_DESTINATION": b"*.*"}


def test_the_unit_s_fourteen_are_flipped_and_none_held_unbound(blob):
    da.flipped(blob, FLIPPED)
    da.unbound(blob, cdir.UNIT_C_HELD_AT_F2)


# ---- band 6 slice F2: THE UNIT'S ROWS — every case at an arrival of a flipped routine registered
# (`aes_deskarrive.register_row`): a plain row, or a row that switches THROUGH ITS DOOR (a DOOR USER, measured: d_errmsg's
# alert answered through form_error's waits; hide_dial's form_dial FINISH, whose desktop redraw reaches the event door —
# registered with no door, its companion's fork is refused at `recreate_call_event_door`) — and d_dofdel's two over its
# GEMDOS SCRIPTED (the recording trap answering the ROM's run in place, said in the row's name). The classes stay Tier
# 1's. Its door users' pins are read by `test_tier3.py`'s door users.
#   * SINCE SLICE F2c the four dialog drawers' rows: do_namecon's three a DOOR USER's (MEASURED, the table's second count:
#     5 calls of a rebound entry each — its dialog's form_do waits for the Return), draw_dial's, show_dial's and
#     draw_fld's ROWS THAT SWITCH WITH NO DOOR (objc_draw's yield alone: the walk served, slice H2's P1), held here three
#     ways (premise, whole run on both blobs, price — `NO_DOOR_*`).
FLIPPED = tuple(name for name in cdir.UNIT_C if name not in cdir.UNIT_C_HELD_AT_F2)
DOOR_USERS = frozenset((D_ERRMSG, HIDE_DIAL, DO_NAMECON))
ROWS = {name: da.register_row(each, answered=each.name not in VOID, door=each.name in DOOR_USERS)
        for name, each in da.at_arrivals(CASES).items() if each.name in FLIPPED}


def _deletes_machine(what):
    """d_dofdel's row's machine: the arrival's (`row_machine_of`), its `trap #1` answered as the run in place answered it."""
    chain, nth = DELETES[what]
    arrived = da.arrival(D_DOFDEL, chain, nth)
    return arrived, case.merge_pokes(da.row_machine_of(arrived), dl.GEMDOS.pokes([_fdelete_answered(arrived)]))


def _deletes_row(what):
    chain, nth = DELETES[what]
    return da.register_row(Plain(D_DOFDEL, chain, nth), pokes=_deletes_machine(what)[1],
                           label_said=f"{da.label(Plain(D_DOFDEL, chain, nth))} [{SCRIPTED}]")


ROWS.update({f"{D_DOFDEL} — {what}": _deletes_row(what) for what in DELETES})


@pytest.mark.parametrize("what", DELETES)
def test_d_dofdel_s_row_takes_the_arm_its_name_says_the_delete_done(what):
    """THE ROW'S OWN MACHINE (not the Tier 1 case's) takes the arm the row is named for: over it both shores answer
    d_errmsg's DONE — the script the run in place's own answer, which a row priced over another arm would not be."""
    arrived, machine = _deletes_machine(what)
    ran = aes.run_function(D_DOFDEL, arrived.arguments, machine, hook=dl.scripted_hook, poison=False)
    assert ran.answer() == cdir.CONSTANTS["D_ERRMSG_DONE"]


DOOR_USERS_PRICED = {
    "aes_desk_d_errmsg, arrival 0 of file: read-only, dragged to the trash, OK — access denied, Return; Return at the first idle":
        ((161430, 247578), (140694, 213798), 7, (0, 0, 0)),
    "aes_desk_hide_dial, arrival 0 of file: dragged to the trash, OK":
        ((321042, 423182), (315934, 414274), 1, (0, 0, 0)),
    "aes_desk_hide_dial, arrival 0 of folder: File > New Folder, 'A', Return":
        ((264628, 353536), (259052, 343992), 1, (0, 0, 0)),
    "aes_desk_hide_dial, arrival 0 of folder: the file dragged onto it, Return":
        ((321042, 423182), (315934, 414274), 1, (0, 0, 0)),
    'aes_desk_do_namecon, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return; Return at the first idle':
        ((283894, 376078), (263514, 342976), 5, (0, 0, 0)),
    "aes_desk_do_namecon, arrival 0 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B); Return at the first idle":
        ((278830, 371362), (258450, 338260), 5, (0, 0, 0)),
    'aes_desk_do_namecon, arrival 0 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return; Return at the first idle':
        ((187058, 255406), (166678, 222304), 5, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN = {
    "aes_desk_d_errmsg, arrival 0 of file: read-only, dragged to the trash, OK — access denied, Return; Return at the first idle":
        {"bench": (1485378, 1425216), "bench_shipped": (1485378, 1413098)},
    "aes_desk_hide_dial, arrival 0 of file: dragged to the trash, OK":
        {"bench": (2096028, 2033426), "bench_shipped": (2096028, 2032396)},
    "aes_desk_hide_dial, arrival 0 of folder: File > New Folder, 'A', Return":
        {"bench": (1781540, 1724800), "bench_shipped": (1781540, 1724940)},
    "aes_desk_hide_dial, arrival 0 of folder: the file dragged onto it, Return":
        {"bench": (2091866, 2029264), "bench_shipped": (2091866, 2028234)},
    'aes_desk_do_namecon, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return; Return at the first idle':
        {"bench": (1930388, 1885124), "bench_shipped": (1930388, 1867904)},
    "aes_desk_do_namecon, arrival 0 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B); Return at the first idle":
        {"bench": (1925672, 1878562), "bench_shipped": (1925672, 1862840)},
    'aes_desk_do_namecon, arrival 0 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return; Return at the first idle':
        {"bench": (1129358, 1090714), "bench_shipped": (1129358, 1078366)},
}
NO_DOOR_PREMISES = {
    'aes_desk_draw_dial, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_desk_draw_dial, arrival 1 of folder: the file dragged onto it again, Return — the name conflict, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_desk_draw_dial, arrival 0 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_desk_show_dial, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_desk_show_dial, arrival 0 of folder: File > New Folder, 'A', Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_desk_show_dial, arrival 0 of folder: the file dragged onto it, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_desk_draw_fld, arrival 0 of file: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_desk_draw_fld, arrival 0 of folder: dragged to the trash, OK':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED = {
    'aes_desk_draw_dial, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return':
        ((99258, 123362), None, None, (0, 0, 0)),
    'aes_desk_draw_dial, arrival 1 of folder: the file dragged onto it again, Return — the name conflict, Return':
        ((99516, 123790), None, None, (0, 0, 0)),
    "aes_desk_draw_dial, arrival 0 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)":
        ((97600, 121756), None, None, (0, 0, 0)),
    'aes_desk_show_dial, arrival 0 of file: dragged to the trash, OK':
        ((102608, 128388), None, None, (0, 0, 0)),
    "aes_desk_show_dial, arrival 0 of folder: File > New Folder, 'A', Return":
        ((83968, 106466), None, None, (0, 0, 0)),
    'aes_desk_show_dial, arrival 0 of folder: the file dragged onto it, Return':
        ((101072, 126632), None, None, (0, 0, 0)),
    'aes_desk_draw_fld, arrival 0 of file: dragged to the trash, OK':
        ((29852, 40606), None, None, (0, 0, 0)),
    'aes_desk_draw_fld, arrival 0 of folder: dragged to the trash, OK':
        ((30392, 41274), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    'aes_desk_draw_dial, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return':
        {"bench": (827982, 821852), "bench_shipped": (827982, 815934)},
    'aes_desk_draw_dial, arrival 1 of folder: the file dragged onto it again, Return — the name conflict, Return':
        {"bench": (813244, 806212), "bench_shipped": (813244, 801622)},
    "aes_desk_draw_dial, arrival 0 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B)":
        {"bench": (826376, 819460), "bench_shipped": (826376, 814276)},
    'aes_desk_show_dial, arrival 0 of file: dragged to the trash, OK':
        {"bench": (807250, 798522), "bench_shipped": (807250, 793986)},
    "aes_desk_show_dial, arrival 0 of folder: File > New Folder, 'A', Return":
        {"bench": (637806, 627714), "bench_shipped": (637806, 625916)},
    'aes_desk_show_dial, arrival 0 of folder: the file dragged onto it, Return':
        {"bench": (801990, 792958), "bench_shipped": (801990, 788794)},
    'aes_desk_draw_fld, arrival 0 of file: dragged to the trash, OK':
        {"bench": (334132, 328428), "bench_shipped": (334132, 326230)},
    'aes_desk_draw_fld, arrival 0 of folder: dragged to the trash, OK':
        {"bench": (355868, 350156), "bench_shipped": (355868, 347838)},
}
ROWS_MADE = 40                          # the 38 cases at arrivals of the fourteen flipped, and d_dofdel's two


def _registered_row(name):
    return aes_event.SWITCHING_ROWS[name].row


def test_every_flipped_routine_of_the_unit_has_a_row_at_an_arrival_and_its_pins_are_the_rows():
    import aes_switching
    entries = {da.entry_of(row.name) if hasattr(row, "door") else row[1] for row in ROWS.values()}      # (a plain row is a tuple)
    assert entries == {da.entry_of(name) for name in FLIPPED} and len(ROWS) == ROWS_MADE
    switching = [row for row in ROWS.values() if hasattr(row, "door")]
    door_users = {aes_switching.row_name(row) for row in switching if row.door}
    assert set(DOOR_USERS_PRICED) == door_users == set(DOOR_USERS_WHOLE_RUN)
    assert set(NO_DOOR_PREMISES) == set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN) == {
        aes_switching.row_name(row) for row in switching if not row.door}


def _vet_the_premise(name, premises):
    import aes_switching
    aes_switching.vet_the_premise(_registered_row(name), aes_switching.Premise(*premises[name]))


def _vet_on_a_blob(name, blob, premises, priced, whole):
    import aes_switching
    premise = aes_switching.Premise(*premises[name])
    aes_switching.vet_on_a_blob(blob, _registered_row(name), premise, priced[name][3], whole[name])


def _vet_the_price(name, priced):
    import aes_switching
    aes_switching.vet_the_table_s_price(_registered_row(name), aes_switching.Priced(*priced[name]))


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    _vet_the_premise(name, NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    _vet_on_a_blob(name, blob, NO_DOOR_PREMISES, NO_DOOR_PRICED, NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    _vet_the_price(name, NO_DOOR_PRICED)


# THE THUNKS G4'S FLIP LEAVES ENTERED BY NO WALKED CHAIN (`test_aes_desk_ours.NOT_ENTERED_ON_OUR_SHORE`, group G4's block):
# every Line-F call word of each in the ROM's GEM text lies in a routine G4 flipped — so on our shore only our C calls it.
CALLED_BY_G4_ALONE = {"AES_ROM_DESK_MY_ITOA": {"AES_ROM_DESK_FMT_TIME", "AES_ROM_DESK_FMT_DATE"},
                      "AES_ROM_DESK_FMT_TIME": {"AES_ROM_DESK_OB_SFCB", "AES_ROM_DESK_INF_DTTMSZ"},
                      "AES_ROM_DESK_FMT_DATE": {"AES_ROM_DESK_OB_SFCB", "AES_ROM_DESK_INF_DTTMSZ"},
                      PATH_PART: {PAR_CHK}, "AES_ROM_DESK_APPL_WRITE": {"AES_ROM_DESK_FUN_MSG"},
                      "AES_ROM_DESK_FORM_ERROR": {D_ERRMSG}, "AES_ROM_DOS_DELETE": {D_DOFDEL}}


def test_the_routines_g4_s_flip_leaves_entered_by_no_chain_are_called_by_g4_s_flipped_routines_alone():
    import test_aes_desk_ours
    held = da._linef_table().LINKED_AND_NOT_FLIPPED
    for name, callers in CALLED_BY_G4_ALONE.items():
        assert da.rom_callers(name) == {da.entry_of(caller) for caller in callers}, name
        assert not callers & set(held), name
    # (SINCE BAND 6 W3b's FLIP who-ran reads a C core's run as its entry's (the orchestrator's O4): each of these runs
    # through its core on a walked chain, or is listed as INLINED into its callers — never "called by our C alone")
    listed = test_aes_desk_ours.NOT_ENTERED_ON_OUR_SHORE
    assert not [name for name in CALLED_BY_G4_ALONE if "called by our C alone" in listed.get(name, "")]


# ==== BAND 6 WAVE 2, group G1: THE COPY ENGINE — d_dofcopy, d_doop, dir_op ===========================================
# EVERY CASE IS AN ARRIVAL of a chain of the hands, its GEMDOS REPLAYED from the ROM's own run in place
# (`aes_deskdir.in_place`: the answers, the DTA each search left, the handles laid open for the host — `REPLAYED`, in the
# id), its waits ended by the keys the chain itself typed there (`wakes`, one a idle: the same make code taken in by the
# in-place run and delivered by the row). A case whose run reaches a binding of unit D (a dialog, a field drawn) is a
# ROW THAT SWITCHES; one that reaches none, the plain differential. Both shores' ledgers are the same bytes (the
# megabyte); `the_ledger_is_the_run_in_place` holds that the calls made are the ROM's run's own.
D_DOFCOPY, D_DOOP, DIR_OP = cdir.UNIT_C_WAVE_2
SHOW_INFO_A, FOLDER_SHOW_INFO = "A: File > Show Info, Return", "folder: selected, File > Show Info, Return"
TRASH_CANCELLED = "file: dragged to the trash, Return (Cancel, the dialog's default)"
AUTO_AS_B = "files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB)"
FILE_DELETED_UNASKED = "folder: deletes unconfirmed — the file dragged to the trash"
FOLDER_DELETED_UNASKED = "folder: deletes unconfirmed — the folder dragged to the trash"
AS_B = (SCAN_RETURN, SCAN_BACKSPACE, SCAN_B, SCAN_RETURN)        # the copy dialog's Return, then the conflict's new name
RENAMED = (SCAN_BACKSPACE, SCAN_B, SCAN_RETURN)                  # the conflict's name's last letter made a B
# Each row past the default derivation budget declares its own (`aes_event`: 5 N <= B <= 10 N), from the run measured:
COPY_RUN_BUDGET = 3_000_000             # dir_op copying a file over its conflict: 512,420 instructions
FILE_COPY_BUDGET = 2_000_000            # ...a file copied, a folder copied: 323,943 and 325,464
AS_B_BUDGET = 3_000_000                 # ...a folder copied as B over its conflict: 549,917

READ_ONLY_ARCHIVED_ATTRIBUTES, A_TIME = 0x21, 0x1234
ARCHIVED_ATTRIBUTES = 0x20             # the archive bit alone: a read-only file IS copied by a chain (READ_ONLY_COPIED)


def _fnode_laid(arrived):
    """LAID: the one SELECTED file of dir_op's list archived, its time $1234."""
    ram, desk = arrived.boot.ram, case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & db.BUS
    objects, node, laid = desk + db.DESK_GLOBALS["DESK_G_SCREEN_OBJECTS"], arrived.arguments[2] & db.BUS, {}
    while node:
        shown = case.word_in(ram, node + FPD["FNODE_OBID"])
        if shown != cdir.CONSTANTS["FNODE_NO_OBJECT"] and case.word_in(ram, objects + shown * aes.OB_BYTES + aes.OB_STATE) & 1:
            laid[node + FPD["FNODE_ATTR"]] = bytes((ARCHIVED_ATTRIBUTES,))
            laid[node + FPD["FNODE_TIME"]] = struct.pack(">H", A_TIME)
        node = case.long_in(ram, node + FPD["FNODE_NEXT"]) & db.BUS
    assert len(laid) == 2, "one selected file"
    return laid


EngineCase = namedtuple("EngineCase", "name chain nth wakes yields budget laid", defaults=(0, (), False, None, None))
EngineCase.__doc__ = """A case of the copy engine: `name` at the `nth` arrival of `chain`, the make codes `wakes` typed
one an idle (the chain's own), `yields` where its run reaches a binding (a row that switches), `budget` its row's
declared derivation budget (`aes_event`); `laid`: `(what, arrival -> pokes)`, A LABELLED STAGING laid over the
arrival's megabyte BEFORE the ROM's own run in place is taken (`LAID` in the id)."""
ENGINE_CASES = (
    # d_dofcopy: a file copied into a folder — fitting the buffer, the long file; over the name conflict, Return (the same
    # name: copied over), with the copy dialog up and with copies unconfirmed (the conflict's dialog put up first)
    EngineCase(D_DOFCOPY, COPIED), EngineCase(D_DOFCOPY, README_COPIED),
    EngineCase(D_DOFCOPY, FILE_CONFLICT, 0, (SCAN_RETURN,), True), EngineCase(D_DOFCOPY, UNCONFIRMED_CONFLICT, 0, (SCAN_RETURN,), True),
    # ...and over the conflict with ANOTHER NAME typed (its keys, not the chain's): the destination renamed, the typed
    # name kept as the next conflict's source, the new name opened again — free — and created
    EngineCase(D_DOFCOPY, FILE_CONFLICT, 0, RENAMED, True),
    # d_doop: Show Info's count of drive A: and of a folder; a folder deleted, one holding a file, one holding a folder
    # (counted first, then deleted); a folder copied into another, and as B over the conflict
    EngineCase(D_DOOP, SHOW_INFO_A), EngineCase(D_DOOP, FOLDER_SHOW_INFO),
    EngineCase(D_DOOP, FOLDER_TRASHED, 1, (), True), EngineCase(D_DOOP, AUTO_TRASHED, 1, (), True),
    EngineCase(D_DOOP, A_DELETED), EngineCase(D_DOOP, A_DELETED, 1, (), True),
    EngineCase(D_DOOP, B_INTO_A, 2, (), True), EngineCase(D_DOOP, FOLDER_CONFLICT, 2, (), True),
    # dir_op: the selection counted (a file, a folder holding a file, a folder holding a folder); the delete dialog
    # cancelled; a file copied (the copy dialog's Return), over the conflict, with copies unconfirmed; a folder copied,
    # and as B over the folder's conflict
    EngineCase(DIR_OP, TRASHED), EngineCase(DIR_OP, AUTO_TRASHED), EngineCase(DIR_OP, A_DELETED),
    EngineCase(DIR_OP, TRASH_CANCELLED, 1, (SCAN_RETURN,), True),
    EngineCase(DIR_OP, COPIED, 2, (SCAN_RETURN,), True, FILE_COPY_BUDGET),
    EngineCase(DIR_OP, FILE_CONFLICT, 2, (SCAN_RETURN, SCAN_RETURN), True, COPY_RUN_BUDGET),
    EngineCase(DIR_OP, UNCONFIRMED_CONFLICT, 2, (SCAN_RETURN,), True, COPY_RUN_BUDGET),
    EngineCase(DIR_OP, B_INTO_A, 2, (SCAN_RETURN,), True, FILE_COPY_BUDGET),
    EngineCase(DIR_OP, FOLDER_CONFLICT, 2, AS_B, True, AS_B_BUDGET),
    # deletes unconfirmed (the group's chains): no dialog — a file deleted by dir_op, a folder walked and deleted by
    # d_doop with no tree
    EngineCase(DIR_OP, FILE_DELETED_UNASKED, 1), EngineCase(DIR_OP, FOLDER_DELETED_UNASKED, 1),
    EngineCase(D_DOOP, FOLDER_DELETED_UNASKED, 1),
    # a folder holding a file copied (the group's chain: AUTO copied into drive A:'s root as AUTB): the walk's file copied
    # by d_dofcopy from its DTA's time, date and attributes
    EngineCase(D_DOOP, AUTO_AS_B, 2, (), True), EngineCase(DIR_OP, AUTO_AS_B, 2, AS_B, True, AS_B_BUDGET),
    # the copied file's FNODE LAID archived ($20) with a time of $1234 — every file of the model's disks has a time of 0
    # and no archive bit (the read-only bit is an arrival's: READ_ONLY_COPIED, below): its attributes and stamp handed
    EngineCase(DIR_OP, COPIED, 2, (SCAN_RETURN,), True, FILE_COPY_BUDGET,
               ("the selected file's FNODE archived, its time $1234", lambda arrived: _fnode_laid(arrived))),
    # (the fix pass's) A READ-ONLY FILE COPIED (the chain READ_ONLY_COPIED: the file made read-only, a folder made, the
    # file dragged onto it): d_dofcopy handed attributes $01 — Fcreate's read-only bit dropped (the ROM's `andi.w #-2`)
    # — and dir_op's copy of it; (Show Info of drive A: emptied by a delete) d_doop's walk over an EMPTY root: Fsfirst's
    # EFILNF at its first search (a folder's own search finds "." first) — AX 18 by the search glue, as ENMFIL: the AX-2
    # arm (dos_open's EFILNF) no search of the walk can give
    EngineCase(D_DOFCOPY, READ_ONLY_COPIED), EngineCase(DIR_OP, READ_ONLY_COPIED, 2, (SCAN_RETURN,), True, FILE_COPY_BUDGET),
    EngineCase(D_DOOP, EMPTIED_INFO),
)


def engine_label(each):
    typed = f"; {len(each.wakes)} key(s) typed at its idles" if each.wakes else ""
    laid = f" [{da.LAID}: {each.laid[0]}]" if each.laid else ""
    return f"{each.name} — arrival {each.nth} of {each.chain} [{cdir.REPLAYED}]{laid}{typed}"


ENGINE_BY_LABEL = {engine_label(each): each for each in ENGINE_CASES}
assert len(ENGINE_BY_LABEL) == len(ENGINE_CASES), "two engine cases of one name"


def _received(scancode):
    return (aes_boot.ikbd(scancode), aes_boot.ikbd(scancode | KEY_RELEASED))


@functools.cache
def engine_replay(each):
    """The case's arrival and the ROM's own run of it in place (`aes_deskdir.in_place`)."""
    arrived = da.arrival(each.name, each.chain, each.nth)
    if each.laid:
        arrived = da._laid_over(arrived, each.laid[1](arrived))
    return arrived, cdir.in_place(arrived, [_received(scancode) for scancode in each.wakes])


def engine_run(each):
    """THE CASE AT TIER 1 — the row through the companion (its idles the wakes'), or the plain differential: the image
    the C left."""
    arrived, replay = engine_replay(each)
    pokes = case.merge_pokes(da.machine_of(arrived), cdir.replayed(replay))
    if not each.yields:
        return aes.run_function(each.name, arrived.arguments, pokes, hook=cdir.engine_hook, poison=False).final
    at_idle = {idle: aes_event.key(scancode) for idle, scancode in enumerate(each.wakes)}
    row = aes_event.woken_row(engine_label(each), each.name, arrived.arguments, lambda: pokes, at_idle, objects=True,
                              answered=True, budget=each.budget)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert the_rom_s.idles == len(each.wakes), f"{engine_label(each)}: the ROM's run idles {the_rom_s.idles} time(s)"
    return ran.image


@pytest.mark.parametrize("name", ENGINE_BY_LABEL)
def test_the_copy_engine_from_its_arrival_with_gemdos_replayed_is_the_rom_s(name):
    """THE CASE: the C core against the ROM's routine from the same entry, GEMDOS replayed on both shores — its answer
    at its width, every byte of the megabyte (the ledger among them) — and THE CALLS MADE ARE THE ROM'S RUN'S OWN."""
    each = ENGINE_BY_LABEL[name]
    image = engine_run(each)
    assert tuple(function for function, _frame in cdir.engine_calls(image)) == engine_replay(each)[1].functions


READ_ONLY = 0x01                        # (GEMDOS's FA_RDONLY)
EFILNF_ANSWER = addrs.parse(aes.INCLUDE / "gemdos" / "process.h")["GEMDOS_EFILNF"]


def test_the_fix_pass_s_arrivals_take_the_arms_they_are_there_for():
    """READ OFF THE ARRIVALS, not the chains' names: d_dofcopy over READ_ONLY_COPIED is handed attributes $01 (the
    read-only bit Fcreate drops); d_doop over EMPTIED_INFO searches an empty root — its first Fsfirst answers EFILNF."""
    assert da.arrival(D_DOFCOPY, READ_ONLY_COPIED).arguments[-1] == READ_ONLY
    _arrived, replay = engine_replay(EngineCase(D_DOOP, EMPTIED_INFO))
    assert replay.functions[-1] == cdir.FSFIRST and replay.answers[-1] == EFILNF_ANSWER & aes.LONG_MASK


# THE NAME CONFLICT'S SKIP (the fix pass's: a dialog button clicked — unit H's click wake, `aes_deskfun.clicked`, the
# conflict's dialog up after the chain's step before its last): its NAMECON_SKIP button reads "Cancel", and the copy
# dialog under it holds one too — the lower of the two is clicked; the run in place creates nothing (pinned below).
import aes_desk                         # noqa: E402
import aes_deskfun as fun               # noqa: E402

SKIP_TEXT = "Cancel"                     # the conflict dialog's NAMECON_SKIP button reads "Cancel" in this ROM
SKIP_CLICKED = fun.clicked(aes_desk.lowest_button_point(SKIP_TEXT), -2)


def test_d_dofcopy_s_name_conflict_skipped_by_a_click_is_the_rom_s():
    arrived = da.arrival(D_DOFCOPY, FILE_CONFLICT, 0)
    replay = cdir.in_place(arrived, SKIP_CLICKED.receptions(FILE_CONFLICT))
    pokes = case.merge_pokes(da.machine_of(arrived), cdir.replayed(replay))
    row = aes_event.woken_row(f"{D_DOFCOPY} — arrival 0 of {FILE_CONFLICT} [{cdir.REPLAYED}]; the conflict's Skip clicked",
                              D_DOFCOPY, arrived.arguments, lambda: pokes, SKIP_CLICKED.at_idle(FILE_CONFLICT), objects=True,
                              answered=True)
    assert cdir.FCREATE not in replay.functions, "the conflict skipped: nothing created"
    ran = da.held(row)
    assert da.the_rom_s_run(row).idles
    assert tuple(function for function, _frame in cdir.engine_calls(ran.image)) == replay.functions


def test_the_copy_engine_is_flipped(blob):
    """FLIPPED at band 6 slice F3, stage 1 (`aes_deskarrive.flipped`): each core called by its own thunk of the table,
    each entry ours through it."""
    da.flipped(blob, cdir.UNIT_C_WAVE_2)


# ---- d_dofcopy's arms no chain's GEMDOS reaches: LABELLED ARGUMENT CLASSES, GEMDOS SCRIPTED ------------------------------
# The model's disk answers every read and write, and no floppy holds a file larger than free memory: so these arms are
# taken over the ARRIVAL of a plain copy (the file fitting the buffer) with GEMDOS SCRIPTED — the same recorder, its
# answers made up as said in each id (the arrival's own frames and handles; a second handle laid open beside the first,
# for the copy whose source stays open). Every answer below -32 would show an alert; these are ERROR (-1) or EFILNF,
# which d_errmsg shows none for, but the short write's own alert.
SCRIPTED_CLASS = "GEMDOS SCRIPTED: answers no run gives"
ERROR, EFILNF, A_SHORT_WRITE = -1, -33, 0x100
SOURCE, DESTINATION = 6, 7              # the handles: the source, and the destination where the source stays open


def _copy_class(answers, *, chain=COPIED, second_handle=False):
    """(the arrival of a copy — d_dofcopy's case at arrival 0 of `chain` —, its replay with `answers` in place of the
    run's) — the file's length the run's own first Fread answer, the buffer's the arrival's DESK_G_XLEN."""
    arrived, replay = engine_replay(next(each for each in ENGINE_CASES if (each.name, each.chain, each.nth) == (D_DOFCOPY, chain, 0)))
    desk = case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & db.BUS
    length, buffer = replay.answers[1], case.long_in(arrived.boot.ram, desk + cdir.CONSTANTS["DESK_G_XLEN"])
    script = tuple((length if each == "length" else buffer if each == "buffer" else each) & aes.LONG_MASK for each in answers)
    handles = dict(replay.handles)
    if second_handle:
        handles[cdir.handle_record(DESTINATION)] = handles[cdir.handle_record(SOURCE)]
    return arrived, replay._replace(answers=script, handles=handles)


FOPEN, FREAD, FCLOSE, FCREATE, FWRITE, FDATIME, FDELETE = (cdir.FOPEN, cdir.FREAD, cdir.FCLOSE, cdir.FCREATE, cdir.FWRITE,
                                                         cdir.FDATIME, cdir.FDELETE)
CopyClass = namedtuple("CopyClass", "answers functions verdict wakes second_handle chain arguments",
                       defaults=((), False, COPIED, None))
COPY_CLASSES = {
    "the source's Fopen failing (EFILNF): 0 at once": CopyClass((EFILNF,), (FOPEN,), 0),
    "its Fread failing (ERROR): 0 at once, the source left open (the ROM's)": CopyClass((SOURCE, ERROR), (FOPEN, FREAD), 0),
    "the destination's Fopen failing otherwise (ERROR): d_errmsg's 0, the source closed AGAIN (the ROM's)": CopyClass(
        (SOURCE, "length", 0, ERROR, 0), (FOPEN, FREAD, FCLOSE, FOPEN, FCLOSE), 0),
    "a file larger than the buffer, its first write failing (ERROR): no second read, the source left open, the copy "
    "stamped — 1 (the ROM's)": CopyClass((SOURCE, "buffer", EFILNF, DESTINATION, ERROR, 0, 0),
                                         (FOPEN, FREAD, FOPEN, FCREATE, FWRITE, FDATIME, FCLOSE), 1, (), True),
    "Fcreate failing (ERROR): 0": CopyClass((SOURCE, "length", 0, EFILNF, ERROR), (FOPEN, FREAD, FCLOSE, FOPEN, FCREATE), 0),
    "a write short of the read (the disk full): the alert, both closed, the copy deleted, 0": CopyClass(
        (SOURCE, "length", 0, EFILNF, SOURCE, A_SHORT_WRITE, 0, 0, 0),
        (FOPEN, FREAD, FCLOSE, FOPEN, FCREATE, FWRITE, FCLOSE, FCLOSE, FDELETE), 0, (SCAN_RETURN,)),
    "a write failing (ERROR): its verdict overwritten by the stamp's — 1 (the ROM's)": CopyClass(
        (SOURCE, "length", 0, EFILNF, SOURCE, ERROR, 0, 0), (FOPEN, FREAD, FCLOSE, FOPEN, FCREATE, FWRITE, FDATIME, FCLOSE), 1),
    "a file larger than the buffer: read and written a buffer at a time, the source closed at its end": CopyClass(
        (SOURCE, "buffer", EFILNF, DESTINATION, "buffer", "length", 0, "length", 0, 0),
        (FOPEN, FREAD, FOPEN, FCREATE, FWRITE, FREAD, FCLOSE, FWRITE, FDATIME, FCLOSE), 1, (), True),
    "...its second read failing (ERROR): the copy kept short and stamped, 1 (the ROM's)": CopyClass(
        (SOURCE, "buffer", EFILNF, DESTINATION, "buffer", ERROR, 0, 0, 0),
        (FOPEN, FREAD, FOPEN, FCREATE, FWRITE, FREAD, FCLOSE, FDATIME, FCLOSE), 1, (), True),
    # (the run's own answers — the copy of a file fitting the buffer — over arguments no caller hands at these arrivals)
    "an ARCHIVED source (attributes $20 — the read-only bit is an arrival's): created as $20": CopyClass(
        (SOURCE, "length", 0, EFILNF, SOURCE, "length", 0, 0), (FOPEN, FREAD, FCLOSE, FOPEN, FCREATE, FWRITE, FDATIME, FCLOSE),
        1, arguments=lambda arrived: (*arrived.arguments[:3], ARCHIVED_ATTRIBUTES)),
    "the destination THE SOURCE ITSELF, over the conflict, Return: the same file — the source closed, nothing copied, 1":
        CopyClass((SOURCE, "length", 0, SOURCE, 0, 0), (FOPEN, FREAD, FCLOSE, FOPEN, FCLOSE, FCLOSE), 1, (SCAN_RETURN,),
                  chain=FILE_CONFLICT, arguments=lambda arrived: (arrived.arguments[0], arrived.arguments[0], *arrived.arguments[2:])),
}


@pytest.mark.parametrize("what", COPY_CLASSES, ids=[f"{D_DOFCOPY} — ARGUMENT CLASS ({what}), over arrival 0 of "
                                                   f"{COPY_CLASSES[what].chain} [{SCRIPTED_CLASS}]" for what in COPY_CLASSES])
def test_d_dofcopy_an_argument_class_gemdos_scripted_is_the_rom_s(what):
    """THE CLASS: the C against the ROM's routine over the plain copy's arrival, GEMDOS scripted on both shores — the
    calls made the ones said, the answer the one said."""
    each = COPY_CLASSES[what]
    arrived, replay = _copy_class(each.answers, chain=each.chain, second_handle=each.second_handle)
    if each.arguments:
        arrived = arrived._replace(arguments=each.arguments(arrived))
    pokes = case.merge_pokes(da.machine_of(arrived), cdir.replayed(replay))
    # (a row even where no binding is reached: a C that put up an alert the ROM's run does not is then held to that
    # run's dispatcher — an assertion — where a plain differential would end in the yield's refusal)
    at_idle = {idle: aes_event.key(scancode) for idle, scancode in enumerate(each.wakes)}
    row = aes_event.woken_row(what, D_DOFCOPY, arrived.arguments, lambda: pokes, at_idle, objects=True, answered=True)
    ran = da.held(row)
    assert da.the_rom_s_run(row).idles == len(each.wakes)
    image, answer = ran.image, ran.answer
    assert tuple(function for function, _frame in cdir.engine_calls(image)) == each.functions
    assert answer == each.verdict


ENGINE_ARRIVALS, ENGINE_CLASSES = 30, 13         # (with d_doop's DTA class, below)        # ...and the classes all d_dofcopy's, over its plain copy's arrival


def test_every_routine_of_the_engine_has_a_case_at_an_arrival_of_its_own():
    assert {each.name for each in ENGINE_CASES} == set(cdir.UNIT_C_WAVE_2)
    laid, doop_dta_class = sum(1 for each in ENGINE_CASES if each.laid), 1
    assert (len(ENGINE_CASES) - laid, len(COPY_CLASSES) + laid + doop_dta_class) == (ENGINE_ARRIVALS, ENGINE_CLASSES)


def test_the_engine_s_answers_are_held_at_the_word_and_read_where_the_table_says():
    """No divergence of D0: the three answer a word in C, compared on every case — d_dofcopy's read by d_doop and
    dir_op, d_doop's by dir_op and inf_folder, dir_op's (always 1) by no instruction of the ROM."""
    assert all(da.vdi.ALCYON[name].restype is aes.WORD_ANSWER for name in cdir.UNIT_C_WAVE_2)
    read = {name: len(db.answer_readers(da.entry_of(name))) for name in cdir.UNIT_C_WAVE_2}
    assert read == {D_DOFCOPY: 2, D_DOOP: 2, DIR_OP: 0}


# ...and d_doop's file copied from a DTA no disk of the model's leaves: every file's time is 0 and none is read-only —
# AN ARGUMENT CLASS over the AUTB copy's arrival, the walk's DTA of INSIDE.TXT SCRIPTED read-only and archived ($21 —
# no run copies a read-only file out of a walked folder: READ_ONLY_COPIED's is a single file's copy),
# its time $1234: the stamp and the attributes handed d_dofcopy, read off the DTA.
INSIDE = b"INSIDE.TXT"
DTA = layouts.parse_constants((aes.INCLUDE / "gemdos" / "fs.h",), known=aes.CONSTANTS)


def _inside_read_only(fill):
    if fill[DTA["DTA_NAME"]:].split(b"\0")[0] != INSIDE:
        return fill
    laid = bytearray(fill)
    laid[DTA["DTA_FOUND_ATTR"]] = READ_ONLY_ARCHIVED_ATTRIBUTES
    laid[DTA["DTA_TIME"]:DTA["DTA_TIME"] + aes.WORD_BYTES] = struct.pack(">H", A_TIME)
    return bytes(laid)


def test_d_doop_an_argument_class_the_walk_s_file_read_only_with_a_time_scripted():
    each = EngineCase(D_DOOP, AUTO_AS_B, 2, (), True)
    arrived, replay = engine_replay(each)
    fills = tuple(_inside_read_only(fill) for fill in replay.fills)
    assert fills != replay.fills, "the walk finds INSIDE.TXT"
    pokes = case.merge_pokes(da.machine_of(arrived), cdir.replayed(replay._replace(fills=fills)))
    row = aes_event.woken_row(f"{D_DOOP} — ARGUMENT CLASS (INSIDE.TXT's DTA read-only, a time) [{SCRIPTED_CLASS}]", D_DOOP,
                              arrived.arguments, lambda: pokes, {}, objects=True, answered=True)
    ran = da.held(row)
    calls = cdir.engine_calls(ran.image)
    assert tuple(function for function, _frame in calls) == replay.functions
    created = [frame for function, frame in calls if function == FCREATE]
    assert created and created[0][aes.LONG_BYTES:aes.LONG_BYTES + aes.WORD_BYTES] == struct.pack(">H", READ_ONLY_ARCHIVED_ATTRIBUTES & ~1)


# ---- band 6 slice F3, stage 1: THE ENGINE'S ROWS ----------------------------------------------------------------------------
# EVERY CASE AT AN ARRIVAL REGISTERED OVER ITS OWN STAGING (the orchestrator's ruling (c): the wave's own recorder as a row
# kind — no wider ledger; `aes_deskdir.ENGINE`'s 24 entries, not band 5's 11): the arrival's megabyte whole but the
# harness's window with the ROM's own run in place laid over it as the recorder's script (`aes_deskdir.replayed`, `REPLAYED`
# in the row's name), its chain's keys at its idles, the replay's twins its companion's (`aes_deskarrive.register_row`'s
# `pokes`, `hook`, `at_idle`). A plain row where the case reaches no binding; a row that switches where it does — A DOOR
# USER where its run waits at an alert or a dialog (MEASURED: the table's second count, its door calls), one WITH NO DOOR
# where its yield is objc_draw's alone (measured: no door call — registered as a door user it has no second count). The
# LAID case and the classes stay Tier 1's.
# dir_op's seven copies, each run past the default derivation margin, DECLARE THEIR OWN BUDGET — Tier 1's, measured
# (the user's ruling of 2026-10-21, "rows may declare budget"; band 6 slice F3, stage 2: NOT A ROW until then).


def engine_row_label(each):
    """A row's label: the arrival, the staging, the keys (the routine is its name's core)."""
    typed = f"; {len(each.wakes)} key(s) typed at its idles" if each.wakes else ""
    return f"arrival {each.nth} of {each.chain} [{cdir.REPLAYED}]{typed}"


def _engine_row(each):
    arrived, replay = engine_replay(each)
    pokes = case.merge_pokes(da.row_machine_of(arrived), cdir.replayed(replay))
    at_idle = {idle: aes_event.key(scancode) for idle, scancode in enumerate(each.wakes)}
    return da.register_row(da.Case(each.name, each.chain, each.nth, yields=each.yields), pokes=pokes,
                           label_said=engine_row_label(each), hook=cdir.engine_hook, at_idle=at_idle, door=bool(each.wakes),
                           budget=each.budget)


ENGINE_ROWS = {engine_label(each): _engine_row(each) for each in ENGINE_CASES if not each.laid}
ENGINE_ROWS_MADE, ENGINE_BUDGETED = 30, 7       # the 30 engine cases at arrivals (the thirty-first is the LAID one); dir_op's copies
ENGINE_DOOR_USERS_PRICED = {
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((305362, 408642), (284982, 375540), 5, (0, 0, 0)),
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((208526, 287970), (188146, 254868), 5, (0, 0, 0)),
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 3 key(s) typed at its idles":
        ((480270, 659488), (424394, 571226), 7, (0, 0, 0)),
    "aes_desk_dir_op, arrival 1 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((469518, 625872), (444030, 583862), 6, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((519742, 697380), (494254, 655370), 6, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 2 key(s) typed at its idles":
        ((815900, 1093568), (770032, 1018456), 11, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((534724, 719042), (509236, 677032), 6, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of folders: B dragged onto A, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((514314, 689022), (488826, 647012), 6, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 4 key(s) typed at its idles":
        ((933188, 1271930), (851824, 1141658), 13, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 4 key(s) typed at its idles":
        ((977908, 1333686), (896544, 1203414), 13, (0, 0, 0)),
    "aes_desk_dir_op, arrival 2 of file: read-only — File > New Folder, 'A', Return, the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        ((519742, 697380), (494254, 655370), 6, (0, 0, 0)),
}
ENGINE_DOOR_USERS_WHOLE_RUN = {
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (1997048, 1946430), "bench_shipped": (1997048, 1925164)},
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (1196018, 1152020), "bench_shipped": (1196018, 1135626)},
    "aes_desk_d_dofcopy, arrival 0 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 3 key(s) typed at its idles":
        {"bench": (2592834, 2494136), "bench_shipped": (2592834, 2456296)},
    "aes_desk_dir_op, arrival 1 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (3068076, 2971338), "bench_shipped": (3068076, 2965830)},
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (3444594, 3335344), "bench_shipped": (3444594, 3325580)},
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it again, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 2 key(s) typed at its idles":
        {"bench": (5419150, 5260648), "bench_shipped": (5419150, 5230982)},
    "aes_desk_dir_op, arrival 2 of folder: the file dragged onto it again, copies unconfirmed — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (3292882, 3185026), "bench_shipped": (3292882, 3166524)},
    "aes_desk_dir_op, arrival 2 of folders: B dragged onto A, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (3459812, 3351542), "bench_shipped": (3459812, 3343360)},
    "aes_desk_dir_op, arrival 2 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 4 key(s) typed at its idles":
        {"bench": (5883642, 5678802), "bench_shipped": (5883642, 5642596)},
    "aes_desk_dir_op, arrival 2 of files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 4 key(s) typed at its idles":
        {"bench": (6228946, 6014624), "bench_shipped": (6228946, 5974544)},
    "aes_desk_dir_op, arrival 2 of file: read-only — File > New Folder, 'A', Return, the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 1 key(s) typed at its idles":
        {"bench": (3444594, 3335344), "bench_shipped": (3444594, 3325580)},
}
ENGINE_NO_DOOR_PREMISES = {
    "aes_desk_d_doop, arrival 1 of folder: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0x1, ()),
    "aes_desk_d_doop, arrival 1 of files: the folder (not empty) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), 0x1, ()),
    "aes_desk_d_doop, arrival 1 of folders: A (holding B) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), 0x1, ()),
    "aes_desk_d_doop, arrival 2 of folders: B dragged onto A, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0x1, ()),
    "aes_desk_d_doop, arrival 2 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0x1, ()),
    "aes_desk_d_doop, arrival 2 of files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), 0x1, ()),
}
ENGINE_NO_DOOR_PRICED = {
    "aes_desk_d_doop, arrival 1 of folder: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((34688, 47862), None, None, (0, 0, 0)),
    "aes_desk_d_doop, arrival 1 of files: the folder (not empty) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((67896, 94486), None, None, (0, 0, 0)),
    "aes_desk_d_doop, arrival 1 of folders: A (holding B) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((71572, 98946), None, None, (0, 0, 0)),
    "aes_desk_d_doop, arrival 2 of folders: B dragged onto A, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((33392, 46058), None, None, (0, 0, 0)),
    "aes_desk_d_doop, arrival 2 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((32592, 45106), None, None, (0, 0, 0)),
    "aes_desk_d_doop, arrival 2 of files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((75248, 104760), None, None, (0, 0, 0)),
}
ENGINE_NO_DOOR_WHOLE_RUN = {
    "aes_desk_d_doop, arrival 1 of folder: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (368444, 361008), "bench_shipped": (368444, 358458)},
    "aes_desk_d_doop, arrival 1 of files: the folder (not empty) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (705908, 690776), "bench_shipped": (705908, 685634)},
    "aes_desk_d_doop, arrival 1 of folders: A (holding B) dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (737014, 720786), "bench_shipped": (737014, 716140)},
    "aes_desk_d_doop, arrival 2 of folders: B dragged onto A, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (342396, 335058), "bench_shipped": (342396, 332826)},
    "aes_desk_d_doop, arrival 2 of folder: dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as B) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (336720, 329302), "bench_shipped": (336720, 327150)},
    "aes_desk_d_doop, arrival 2 of files: the folder dragged onto drive A:'s icon, Return — the name conflict, Backspace, 'B', Return (copied as AUTB) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (668332, 651554), "bench_shipped": (668332, 645444)},
}


def test_every_engine_case_at_an_arrival_is_a_row_and_its_pins_are_the_rows():
    import aes_switching
    at_arrivals = [engine_label(each) for each in ENGINE_CASES if not each.laid]
    assert sorted(at_arrivals) == sorted(ENGINE_ROWS)
    budgeted = {engine_label(each) for each in ENGINE_CASES if each.budget and not each.laid}
    assert (len(ENGINE_ROWS), len(budgeted)) == (ENGINE_ROWS_MADE, ENGINE_BUDGETED)
    assert {ENGINE_ROWS[name].name for name in budgeted} == {DIR_OP} and all(ENGINE_ROWS[name].budget for name in budgeted)
    assert {da.entry_of(each.name) for each in ENGINE_CASES if engine_label(each) in ENGINE_ROWS} == {
        da.entry_of(name) for name in cdir.UNIT_C_WAVE_2}
    switching = [row for row in ENGINE_ROWS.values() if hasattr(row, "door")]
    assert set(ENGINE_DOOR_USERS_PRICED) == set(ENGINE_DOOR_USERS_WHOLE_RUN) == {
        aes_switching.row_name(row) for row in switching if row.door}
    assert set(ENGINE_NO_DOOR_PREMISES) == set(ENGINE_NO_DOOR_PRICED) == set(ENGINE_NO_DOOR_WHOLE_RUN) == {
        aes_switching.row_name(row) for row in switching if not row.door}


def test_an_engine_row_s_declared_budget_is_its_tier_1_case_s_own():
    """EACH ENGINE ROW DECLARES ITS TIER 1 CASE'S OWN BUDGET (dir_op's seven copies), and none where its case declares
    none — a plain row has no budget to declare."""
    at_arrivals = {engine_label(each): each for each in ENGINE_CASES if not each.laid}
    assert {name: getattr(ENGINE_ROWS[name], "budget", None) for name in at_arrivals} == {
        name: each.budget for name, each in at_arrivals.items()}


@pytest.mark.parametrize("name", ENGINE_NO_DOOR_PREMISES)
def test_an_engine_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    _vet_the_premise(name, ENGINE_NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", ENGINE_NO_DOOR_WHOLE_RUN)
def test_an_engine_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    _vet_on_a_blob(name, blob, ENGINE_NO_DOOR_PREMISES, ENGINE_NO_DOOR_PRICED, ENGINE_NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", ENGINE_NO_DOOR_PRICED)
def test_an_engine_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    _vet_the_price(name, ENGINE_NO_DOOR_PRICED)
