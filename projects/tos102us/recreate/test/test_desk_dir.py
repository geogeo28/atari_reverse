"""THE COPY ENGINE'S HELPERS (`src/desk/deskdir.c`; band 6 wave 1b, group G4, unit C): fourteen routines of
`$fdcf04..$fdd917` — the dialogs' drawing, the path editors, the DOS verdict and the delete, the check that a folder is
not copied into itself — HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

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
    reaches that arm inside d_dofdel), and par_chk's refusal by a run (a folder dragged into its own window: the second
    window's folder opens over a forced media change, which the model refuses by name — tried, `aes_desk`'s block).
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_boot
import aes_deskarrive as da
import aes_deskbind as db
import aes_deskdir as cdir
import aes_deskleaves as dl
import case
import layouts

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
    """The ROM's "\\*.*" four times and "*.*" twice, at the addresses the header names."""
    texts = {name: bytes(BASE_IMAGE[at:BASE_IMAGE.index(b"\0", at)]) for name, at in cdir.CONSTANTS.items()
             if name.startswith("AES_DESK_") and name.endswith(("TAIL", "SOURCE", "DESTINATION"))}
    assert texts == {"AES_DESK_ADD_PATH_TAIL": b"\\*.*", "AES_DESK_SUB_PATH_TAIL": b"\\*.*", "AES_DESK_DEL_FNAME_TAIL": b"\\*.*",
                     "AES_DESK_PAR_CHK_TAIL": b"\\*.*", "AES_DESK_PAR_CHK_END_SOURCE": b"*.*", "AES_DESK_PAR_CHK_END_DESTINATION": b"*.*"}


def test_the_unit_is_linked_and_unbound(blob):
    da.unbound(blob, cdir.UNIT_C)
