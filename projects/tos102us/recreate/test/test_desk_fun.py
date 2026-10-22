"""THE DESK'S ALERT AND ITS MESSAGE TO ITSELF (`src/desk/deskfun.c`; band 6 wave 1b, group G4, unit H): fun_alert
`$fdfd58` and fun_msg `$fdfda6`, HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2, FLIPPED: the
Line-F table's entry for each is its thunk, and every case at an arrival is a Tier 3 row (`ROWS`, below).

  * EVERY CASE IS AN ARRIVAL (`aes_deskarrive.arrival`): a chain of the hands stopped at the routine's first
    instruction, the arguments read off the frame the desk's caller pushed. Where no chain makes the machine an arm
    needs, the case is A LABELLED ARGUMENT CLASS, said in its name (the same routine over an arrival's machine, other
    arguments). Never a poke.
  * BOTH YIELD (each ends on a binding of unit D): every case is a row that switches, held through the companion,
    fun_alert's through its wake (the alert answered by Return).
  * D0 AT RETURN: both answer their binding's word — held to the ROM's D0.w on every case, no divergence.
  * FLIPPED (band 6 slice F2): each core called by its own thunk of the table; no function outside the unbound desk
    refers to a core still held. EVERY CASE AT AN ARRIVAL IS A ROW THAT SWITCHES THROUGH ITS DOOR (both end on a binding
    whose AES routine waits: form_alert's, appl_write's), pinned for `test_tier3.py`'s door users.
"""
import pytest

import aes_deskarrive as da
import aes_deskbind as db
import aes_deskfun as fun

Case = da.Case
RETURN = da.RETURN_TYPED
FORMAT_WARNED = "A: File > Format, Return (the warning answered)"
OPEN_ALERT = "file: File > Open (the Show / Print / Cancel alert)"
AS_TEXT, FILE_INFO = "window: View > Show as Text", "file: File > Show Info, Return"
PROGRAM_INFO = "files: the program selected, File > Show Info, Return"
NO_PARAMETERS = 0
A_WORD_THE_SENDER_IS_NOT = 0x7777       # fun_msg's unread second word, other than gl_apid (0: its one caller pushes it)


def _unread_word(arrived):
    return (arrived.arguments[0], A_WORD_THE_SENDER_IS_NOT, *arrived.arguments[2:])


CASES = (
    # fun_alert: the merge arm (a parameter) at the format warning, none at Open's. (The drive's trash alert — a
    # parameter too, `drive A: dragged to the trash, Return` — was tried and is not kept: its scheduled run idles for
    # ever after a Return at its first or its second idle; not debugged.)
    Case(fun.FUN_ALERT, FORMAT_WARNED, wake=RETURN, arm=lambda a: a[2] != NO_PARAMETERS),
    Case(fun.FUN_ALERT, OPEN_ALERT, wake=RETURN, arm=lambda a: a[2] == NO_PARAMETERS),
    # fun_msg: its two callers' sites (the text view's redraw, Show Info's), and a window of another rectangle
    Case(fun.FUN_MSG, AS_TEXT), Case(fun.FUN_MSG, FILE_INFO), Case(fun.FUN_MSG, PROGRAM_INFO),
    Case(fun.FUN_MSG, AS_TEXT, arguments=_unread_word,
         why="its second word other than gl_apid (its one kind of caller pushes gl_apid, 0): the sender is gl_apid's, read again"),
)
BY_LABEL = da.by_label(CASES)
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)


@EVERY_CASE
def test_a_routine_of_the_unit_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core through the host's scheduler held to the ROM's routine from the same entry — the idles,
    the image at every dispatch and where it returns, the answer (the binding's word) at its width."""
    da.tier_1(BY_LABEL[name])


ARRIVALS, CLASSES = 5, 1


def test_every_routine_of_the_unit_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES if not each.why]
    assert {each.name for each in at_its_own} == set(fun.UNIT_H)
    assert (len(at_its_own), len(CASES) - len(at_its_own)) == (ARRIVALS, CLASSES)


def test_both_answer_their_binding_s_word_which_five_instructions_read_of_fun_alert_and_none_of_fun_msg():
    """D0: each answers the word its binding answers (the C has it: no divergence) — fun_alert's read by five
    instructions of the ROM, fun_msg's by none (`aes_deskbind.answer_readers`)."""
    assert {name: len(db.answer_readers(da.entry_of(name))) for name in fun.UNIT_H} == {fun.FUN_ALERT: 5, fun.FUN_MSG: 0}


def test_the_unit_is_flipped(blob):
    da.flipped(blob, fun.UNIT_H)


# ---- band 6 slice F2: THE UNIT'S ROWS — every case at an arrival a row that switches, a DOOR USER'S (MEASURED: fun_alert's
# run arrives at form_alert's door calls, fun_msg's at appl_write's); the class stays Tier 1's. Their pins — DATA, measured
# by the table's own measurement and by each blob's second differential from the rows as registered (`tools/repin.py`
# re-pins them from a recorded run, never by hand) — are read by `test_tier3.py`'s door users.
ROWS = {name: da.register_row(each) for name, each in da.at_arrivals(CASES).items()}
DOOR_USERS_PRICED = {
    "aes_desk_fun_alert, arrival 0 of A: File > Format, Return (the warning answered); Return at the first idle":
        ((199694, 292828), (178958, 259048), 7, (0, 0, 0)),
    "aes_desk_fun_alert, arrival 0 of file: File > Open (the Show / Print / Cancel alert); Return at the first idle":
        ((192650, 287304), (171914, 253524), 7, (0, 0, 0)),
    "aes_desk_fun_msg, arrival 0 of file: File > Show Info, Return":
        ((9168, 14772), (4110, 5914), 1, (0, 0, 0)),
    "aes_desk_fun_msg, arrival 0 of files: the program selected, File > Show Info, Return":
        ((9168, 14772), (4110, 5914), 1, (0, 0, 0)),
    "aes_desk_fun_msg, arrival 0 of window: View > Show as Text":
        ((9168, 14772), (4110, 5914), 1, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN = {
    "aes_desk_fun_alert, arrival 0 of A: File > Format, Return (the warning answered); Return at the first idle":
        {"bench": (1730532, 1666256), "bench_shipped": (1730532, 1654282)},
    "aes_desk_fun_alert, arrival 0 of file: File > Open (the Show / Print / Cancel alert); Return at the first idle":
        {"bench": (1745930, 1677362), "bench_shipped": (1745930, 1669464)},
    "aes_desk_fun_msg, arrival 0 of file: File > Show Info, Return":
        {"bench": (21534, 17370), "bench_shipped": (21534, 16414)},
    "aes_desk_fun_msg, arrival 0 of files: the program selected, File > Show Info, Return":
        {"bench": (21534, 17370), "bench_shipped": (21534, 16414)},
    "aes_desk_fun_msg, arrival 0 of window: View > Show as Text":
        {"bench": (21534, 17370), "bench_shipped": (21534, 16414)},
}


def test_every_routine_of_the_unit_has_a_row_at_an_arrival_and_its_pins_are_the_rows():
    import aes_switching
    assert {row.name for row in ROWS.values()} == set(fun.UNIT_H) and len(ROWS) == ARRIVALS
    assert {aes_switching.row_name(row) for row in ROWS.values()} == set(DOOR_USERS_PRICED) == set(DOOR_USERS_WHOLE_RUN)




# ==== BAND 6 WAVE 2, group G2 (unit H): THE OPERATIONS' DRIVERS ==================================================================
# EVERY DRIVER YIELDS (an alert, a dialog, a binding): each case is a ROW THAT SWITCHES, through its WAKE where the
# ROM's run waits (`aes_deskfun`'s Wake: keys typed, a button clicked — the same hands the run in place takes in). A
# driver whose run reaches GEMDOS (pn_active's searches, Dcreate, the copy engine) runs over unit C's recorder
# REPLAYING THE ROM'S OWN RUN IN PLACE to the driver's return (`aes_deskfun.in_place`; `REPLAYED`, in the id), bound in
# the row's child; the calls the C made are held to the run's own. Each driver's frame handed on by address is its host
# slot (group G2's window), held across those waits.
import functools
import struct
from collections import namedtuple

from harness import addrs

import aes
import aes_event
import case
import layouts
import vdi
from aes_desk import SCAN_A, SCAN_RETURN

RETURN_KEY, RETURN_TWICE = fun.keys_typed(SCAN_RETURN), fun.keys_typed(SCAN_RETURN, SCAN_RETURN)
TYPED_A, TYPED_A_TAKEN = fun.keys_typed(SCAN_A, SCAN_RETURN), fun.keys_typed(SCAN_A, SCAN_RETURN, SCAN_RETURN)
UP_BEFORE_THE_LAST = -2                 # the chains' step that leaves an alert or a dialog up: the one before their last
NEW_FOLDER_UP = 2                       # ...and New Folder's: the menu item's click (its name is typed after it)
# A ONE-BUTTON ALERT ASKED WITH DEFAULT BUTTON 2 — fun_d2desk's "You cannot drag a disk to the trash can" — has no
# default: Return does nothing and the run waits on (a ROM behaviour; wave 1b's "idles for ever after a Return",
# explained). Its wake is the button clicked.
ALERT_OK_CLICKED = fun.clicked(fun.alert_button_point("OK"), UP_BEFORE_THE_LAST)
DIALOG_OK_CLICKED = fun.clicked(fun.dialog_button_point("OK"), UP_BEFORE_THE_LAST)
CANCEL_CLICKED = fun.clicked(fun.dialog_button_point("Cancel"), NEW_FOLDER_UP)
WAKE_NAMED = {RETURN_KEY: "Return", RETURN_TWICE: "Return, Return", TYPED_A: "'A' typed, Return",
              TYPED_A_TAKEN: "'A' typed, Return, Return at the alert", ALERT_OK_CLICKED: "the alert's OK clicked",
              DIALOG_OK_CLICKED: "the dialog's OK clicked", CANCEL_CLICKED: "the dialog's Cancel clicked"}

# THE CHAINS
D2DESK_TRASH, D2DESK_COPY = "drive A: dragged to the trash, Return", "drive A: dragged onto drive B:, Return"
D2DESK_ICON_ON_ICON = "the trash dragged onto drive A:, Return"
TRASHED, TRASH_CANCELLED = "file: dragged to the trash, OK", "file: dragged to the trash, Return (Cancel, the dialog's default)"
COPIED, README_COPIED = "folder: the file dragged onto it, Return", "files: the long file dragged onto the folder, Return"
B_INTO_A = "folders: B dragged onto A, Return"
NEW_FOLDER, NAME_TAKEN = "folder: File > New Folder, 'A', Return", "folder: File > New Folder again, 'A', Return — the name taken, Return"
TRASH_INTO_A, DRIVE_INTO_A = "A: opened, the trash dragged into its window, Return", "A: opened, drive A: dragged into its window, Return"
ONTO_DRIVE_A = "file: dragged onto drive A:'s icon, Return — the name conflict, Return"
EMPTIED_INTO_A = "file: dragged to the trash, OK — then drive A: dragged into its window"

# THE LAYOUTS THE STAGINGS READ (`desk/deskglobals.h`, `desk/deskfpd.h`, `desk/deskview.h`, `desk/deskfun.h`), GEMDOS's errors
DESK = layouts.parse_constants((db.GLOBALS_HEADER, *(aes.INCLUDE / "desk" / f"{unit}.h" for unit in ("deskfpd", "deskview", "deskfun"))),
                               known=aes.CONSTANTS)
WNODE_ID, WNODE_PATH, WNODE_NAME, WNODE_BYTES = (DESK[field] for field in ("WNODE_ID", "WNODE_PATH", "WNODE_NAME", "WNODE_BYTES"))
DESK_WINDOWS, PNODE_SPEC, ANODE_NEXT, ANODE_TYPE = DESK["DESK_WINDOWS"], DESK["PNODE_SPEC"], DESK["ANODE_NEXT"], DESK["ANODE_TYPE"]
ANODE_OBID, ANODE_LETTER, AT_ISCART = DESK["ANODE_OBID"], DESK["ANODE_LETTER"], DESK["AT_ISCART"]
OP_NONE, AT_ISTRSH = DESK["OP_NONE"], DESK["AT_ISTRSH"]
WNODES = aes.header_constants("deskmem.h")["AES_DESK_BLOCK_920"]
EACCDN = addrs.parse(aes.INCLUDE / "gemdos" / "fs.h")["GEMDOS_EACCDN"]         # access denied, a longword
EFILNF = addrs.parse(aes.INCLUDE / "gemdos" / "process.h")["GEMDOS_EFILNF"]    # file not found, a longword


def _desk(arrived):
    return case.long_in(arrived.boot.ram, aes.AES_DESK_GLOBALS) & db.BUS


def _windows(arrived):
    """The desk's four WNODEs (`aes/deskmem.h`'s block), off the arrival's megabyte."""
    first = case.long_in(arrived.boot.ram, WNODES) & db.BUS
    return [first + index * WNODE_BYTES for index in range(DESK_WINDOWS)]


def _window_of(arrived, handle):
    return next(window for window in _windows(arrived) if case.word_in(arrived.boot.ram, window + WNODE_ID) == handle)


def _a_closed_window(arrived):
    """A WNODE of the four whose window is closed (its id 0)."""
    return next(window for window in _windows(arrived) if not case.word_in(arrived.boot.ram, window + WNODE_ID))


def _anodes(arrived):
    """The desk's icons in use, off the arrival's own list."""
    node = case.long_in(arrived.boot.ram, _desk(arrived) + DESK["DESK_ANODES_IN_USE"])
    while node:
        yield node & db.BUS
        node = case.long_in(arrived.boot.ram, (node & db.BUS) + ANODE_NEXT)


def _typed_cartridge(which):
    """LAID: the ANODE `which(arrived, node)` picks typed AT_ISCART — the cartridge's icon, which no machine of ours has."""
    def laid(arrived):
        nodes = [node for node in _anodes(arrived) if which(arrived, node)]
        assert len(nodes) == 1, f"{len(nodes)} icons are the one to lay"
        return {nodes[0] + ANODE_TYPE: struct.pack(">H", AT_ISCART)}
    return laid


def _of_object(index):
    """...the icon shown by the arrival's argument `index` (a desktop object)."""
    return lambda arrived, node: case.word_in(arrived.boot.ram, node + ANODE_OBID) == arrived.arguments[index]


def _of_drive(letter):
    return lambda arrived, node: case.word_in(arrived.boot.ram, node + ANODE_LETTER) == ord(letter)


def _spec_nine_deep(arrived):
    """LAID: the window's path's spec nine folders down (no chain opens a folder so deep: each needs a folder made)."""
    path = case.long_in(arrived.boot.ram, (arrived.arguments[0] & db.BUS) + WNODE_PATH) & db.BUS
    return {path + PNODE_SPEC: b"A:\\B\\C\\D\\E\\F\\G\\H\\I\\*.*\0"}


def _named_as_the_cartridge_s(index):
    """LAID: the window of handle `arguments[index]` named as the cartridge's window is — AES_DESK_ROOT_NAME's text,
    empty at every arrival: the name's first byte NUL."""
    return lambda arrived: {_window_of(arrived, arrived.arguments[index]) + WNODE_NAME: b"\0"}


def _destination_laid(text):
    """LAID: g_1text, fun_op's destination, the text `text`."""
    return lambda arrived: {_desk(arrived) + DESK["DESK_G_1TEXT"]: text + b"\0"}


def _replay_with(wake, answer_of, *more):
    """The run in place's replay (its wake taken in), each call's answer made `answer_of(function, answer)`; `more`
    laid with it."""
    def laid(arrived):
        replay = fun.in_place(arrived, wake.receptions(arrived.chain) if wake else ())
        answers = tuple(answer_of(function, answer) for function, answer in zip(replay.functions, replay.answers))
        return case.merge_pokes(fun._dd.replayed(replay._replace(answers=answers)), *(each(arrived) for each in more))
    return laid


def _replayed_and(wake, *more):
    return _replay_with(wake, lambda _function, answer: answer, *more)


def _of_type(a_type):
    return lambda arrived, node: case.word_in(arrived.boot.ram, node + ANODE_TYPE) == a_type


def _object_of_drive(arrived, letter):
    """The desktop object of drive `letter`'s icon."""
    node = next(node for node in _anodes(arrived) if _of_drive(letter)(arrived, node))
    return case.word_in(arrived.boot.ram, node + ANODE_OBID)


FNODE_NEXT, FNODE_OBID, STALE_OBJECT = DESK["FNODE_NEXT"], DESK["FNODE_OBID"], 0x7777
FREE_NODES_LAID = 8                     # more than drive A:'s root holds


def _free_nodes_shown(arrived):
    """LAID: the free file list's first nodes each as a file an object showed (a freed node keeps its old object word;
    on this machine they hold 0)."""
    pokes, node = {}, case.long_in(arrived.boot.ram, _desk(arrived) + DESK["DESK_FILES_FREE"])
    for _each in range(FREE_NODES_LAID):
        pokes[(node & db.BUS) + FNODE_OBID] = struct.pack(">H", STALE_OBJECT)
        node = case.long_in(arrived.boot.ram, (node & db.BUS) + FNODE_NEXT)
    return pokes


def _refused_dcreate(function, answer):
    return EACCDN if function == fun._dd.DCREATE else answer


Case2 = namedtuple("Case2", "name chain wake nth why arguments laid replayed budget unanswered yields",
                   defaults=(None, 0, None, None, None, False, None, None, True))
Case2.__doc__ = """One driver's case: `name` at the `nth` arrival of `chain`, its waits ended by `wake` (a Wake named in
WAKE_NAMED; None: it returns without one). `replayed`: GEMDOS replayed from the run in place to its return (the
id says so). AN ARGUMENT CLASS has a `why` and `arguments` (a tuple, or `arrival -> tuple`). `laid`: `(what, arrival
-> pokes)`, a labelled staging over the arrival (with the replay where both: the class's own pokes). `budget`: the
row's own derivation budget where its run passes the default's margin (`aes_event`). `unanswered`: why the ROM's D0
is not compared — A NAMED DIVERGENCE (a word no C has), counted. `yields` False: an arm that returns before any binding
— the kit's plain differential."""
MKDIR_ROW_INSNS = 3_000_000             # fun_mkdir typed into, the folder made, its window rebuilt: 450,972 measured
CLICKED_COPY_INSNS = 2_000_000          # fun_d2desk's disk copy OK'd: pro_cmd, pro_run's launch set-up: 335,971
COPY_ROW_INSNS = 3_000_000              # a driver over the copy engine copying a file, or a delete and the window rebuilt:
                                        # 330,459 .. 492,041 measured
DELETE_ROW_INSNS = 2_000_000            # fun_op's and fun_ddst's delete OK'd: 330,459 and 330,505
DRIVE_ROW_INSNS = 5_000_000             # fun_desk2win over drive A:'s copy into its own window: 725,023


def label2(each):
    said = f"{each.name} — " + (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + f"arrival {each.nth} of {each.chain}"
    said += f" [{fun._dd.REPLAYED}]" if each.replayed else ""
    said += f" [LAID: {each.laid[0]}]" if each.laid else ""
    return said + (f"; {WAKE_NAMED[each.wake]}" if each.wake else "")


CASES_WAVE_2 = (
    # fun_d2desk: a disk onto the trash (the drive named), onto a disk (the copy's alert: Return its default Cancel; OK —
    # DISKCOPY kept and run), the trash onto a disk (refused); the cartridge's icon at either end (LAID)
    Case2(fun.FUN_D2DESK, D2DESK_TRASH, ALERT_OK_CLICKED), Case2(fun.FUN_D2DESK, D2DESK_COPY, RETURN_KEY),
    Case2(fun.FUN_D2DESK, D2DESK_COPY, ALERT_OK_CLICKED, budget=CLICKED_COPY_INSNS),
    Case2(fun.FUN_D2DESK, D2DESK_ICON_ON_ICON, RETURN_KEY),
    Case2(fun.FUN_D2DESK, D2DESK_COPY, RETURN_KEY, why="the destination the cartridge's icon: refused",
          laid=("drive B:'s icon typed the cartridge's", _typed_cartridge(_of_object(0)))),
    Case2(fun.FUN_D2DESK, D2DESK_COPY, RETURN_KEY, why="a source the cartridge's icon: refused as the trash is",
          laid=("drive A:'s icon typed the cartridge's", _typed_cartridge(_of_drive("A")))),
    # fun_rebld: A:'s window read again after Show Info (one file, four), a file deleted, a copy; a closed window's node
    *(Case2(fun.FUN_REBLD, chain, replayed=True) for chain in (FILE_INFO, PROGRAM_INFO, TRASHED, COPIED)),
    Case2(fun.FUN_REBLD, FILE_INFO, why="a closed window's node: no open window shows its spec, none read",
          arguments=lambda a: (_a_closed_window(a),)),
    # fun_mkdir: a folder made; its name taken (the alert, Cancel); no name; the dialog cancelled; a window nine folders
    # down (LAID); Dcreate refused (its answer EACCDN)
    Case2(fun.FUN_MKDIR, NEW_FOLDER, TYPED_A, replayed=True, budget=MKDIR_ROW_INSNS),
    Case2(fun.FUN_MKDIR, NAME_TAKEN, TYPED_A_TAKEN, replayed=True, budget=MKDIR_ROW_INSNS),
    Case2(fun.FUN_MKDIR, NEW_FOLDER, RETURN_KEY), Case2(fun.FUN_MKDIR, NEW_FOLDER, CANCEL_CLICKED),
    Case2(fun.FUN_MKDIR, NEW_FOLDER, RETURN_KEY, why="a window nine folders down: refused, the alert",
          laid=("the window's spec nine separators deep", _spec_nine_deep)),
    Case2(fun.FUN_MKDIR, NEW_FOLDER, TYPED_A_TAKEN, why="Dcreate refused, EACCDN (no disk of ours fills its root): the alert",
          laid=(f"{fun._dd.REPLAYED}; Dcreate answering EACCDN", _replay_with(TYPED_A, _refused_dcreate)), budget=MKDIR_ROW_INSNS),
    # fun_op: a file copied into a folder, a folder into a folder; a file's delete cancelled, and OK'd; nothing to do
    # (OP_NONE); a folder into itself (par_chk: the alert); a copy too deep (the alert)
    Case2(fun.FUN_OP, COPIED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_OP, TRASH_CANCELLED, RETURN_KEY, replayed=True),
    Case2(fun.FUN_OP, TRASHED, DIALOG_OK_CLICKED, replayed=True, budget=DELETE_ROW_INSNS),
    Case2(fun.FUN_OP, COPIED, why="nothing to do (OP_NONE, fun_ddst's answer for no icon of its kinds): 0",
          arguments=lambda a: (OP_NONE & aes.WORD_MASK, a.arguments[1]), yields=False),
    Case2(fun.FUN_OP, B_INTO_A, RETURN_KEY, why="a folder copied into itself: par_chk refuses, the alert", arguments=lambda a: a.arguments,
          laid=("g_1text A:\\B\\*.*, the selected folder's own", _destination_laid(b"A:\\B\\*.*"))),
    Case2(fun.FUN_OP, COPIED, RETURN_KEY, why="a destination ten folders down: past the deepest copy, the alert",
          arguments=lambda a: a.arguments,
          laid=(f"{fun._dd.REPLAYED}; g_1text ten separators deep",
                _replayed_and(RETURN_KEY, _destination_laid(b"A:\\B\\C\\D\\E\\F\\G\\H\\I\\J\\*.*")))),
    # fun_ddst: onto the trash (deleted), onto a disk (copied to its root, the conflict renamed B); onto the cartridge
    # (LAID: refused); onto no icon (nothing)
    Case2(fun.FUN_DDST, TRASHED, DIALOG_OK_CLICKED, replayed=True, budget=DELETE_ROW_INSNS),
    Case2(fun.FUN_DDST, ONTO_DRIVE_A, RETURN_TWICE, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_DDST, TRASHED, RETURN_KEY, why="onto the cartridge's icon: refused, the alert", arguments=lambda a: a.arguments,
          laid=("the trash's icon typed the cartridge's", lambda a: {a.arguments[1] + ANODE_TYPE: struct.pack(">H", AT_ISCART)})),
    Case2(fun.FUN_DDST, TRASHED, why="no icon (a NULL ANODE): nothing to do, 0", arguments=lambda a: (a.arguments[0], 0, a.arguments[2]),
          yields=False),
    # fun_wdst: into a folder of the window (two files), into the window's own path (fun_disk's drop of A:'s files)
    Case2(fun.FUN_WDST, COPIED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_WDST, README_COPIED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_WDST, DRIVE_INTO_A, RETURN_TWICE, replayed=True, budget=COPY_ROW_INSNS),
    # fun_win2win: a file onto a folder of its own window; either window the cartridge's (LAID: refused)
    Case2(fun.FUN_WIN2WIN, COPIED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_WIN2WIN, COPIED, RETURN_KEY, why="the source window the cartridge's: refused, the alert",
          arguments=lambda a: a.arguments, laid=("the source window named as the cartridge's", _named_as_the_cartridge_s(0))),
    Case2(fun.FUN_WIN2WIN, COPIED, RETURN_KEY, why="the destination window the cartridge's: refused, the alert",
          arguments=lambda a: a.arguments, laid=("the destination window named as the cartridge's", _named_as_the_cartridge_s(1))),
    # fun_win2desk: a file onto the trash (cancelled, OK'd); from the cartridge's window onto the trash (GEM's error 5)
    # and onto a disk (refused)
    Case2(fun.FUN_WIN2DESK, TRASHED, DIALOG_OK_CLICKED, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_WIN2DESK, TRASH_CANCELLED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_WIN2DESK, TRASHED, RETURN_KEY, why="from the cartridge's window onto the trash: fm_error(5)",
          arguments=lambda a: a.arguments, laid=("the window named as the cartridge's", _named_as_the_cartridge_s(0))),
    Case2(fun.FUN_WIN2DESK, TRASHED, RETURN_KEY, why="from the cartridge's window onto a disk: refused, the alert",
          arguments=lambda a: (a.arguments[0], _object_of_drive(a, "A")),
          laid=("the window named as the cartridge's", _named_as_the_cartridge_s(0))),
    # fun_disk: drive A:'s files dropped into A:'s window (the copy, each a conflict with itself); A: emptied by a delete
    # first (the fix pass's chain: its search answers EFILNF, nothing dropped); no path node free (the ROM answers its
    # caller's D7: a NAMED DIVERGENCE)
    Case2(fun.FUN_DISK, DRIVE_INTO_A, RETURN_TWICE, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_DISK, EMPTIED_INTO_A, replayed=True),
    Case2(fun.FUN_DISK, DRIVE_INTO_A, RETURN_TWICE, why="the free file nodes' objects stale: each file's cleared",
          arguments=lambda a: a.arguments, budget=COPY_ROW_INSNS,
          laid=(f"{fun._dd.REPLAYED}; the free file nodes' object words $7777", _replayed_and(RETURN_TWICE, _free_nodes_shown))),
    Case2(fun.FUN_DISK, DRIVE_INTO_A, why="no path node free: pn_open's 0", arguments=lambda a: a.arguments,
          laid=("the free path list's head 0", lambda a: {_desk(a) + DESK["DESK_PATHS_FREE"]: bytes(aes.LONG_BYTES)}),
          unanswered="the ROM answers D7 as its caller left it: no C has that word", yields=False),
    # fun_desk2win: the trash into a window (the alert), drive A: into A:'s window (fun_disk); the cartridge's icon (LAID)
    Case2(fun.FUN_DESK2WIN, TRASH_INTO_A, RETURN_KEY),
    Case2(fun.FUN_DESK2WIN, DRIVE_INTO_A, RETURN_TWICE, replayed=True, budget=DRIVE_ROW_INSNS),
    Case2(fun.FUN_DESK2WIN, TRASH_INTO_A, RETURN_KEY, why="the cartridge's icon into a window: refused, the alert",
          arguments=lambda a: a.arguments, laid=("the trash's icon typed the cartridge's", _typed_cartridge(_of_type(AT_ISTRSH)))),
    # fun_drag: window to window, window to an icon, desktop to an icon, desktop to a window; window to the desktop's
    # background (the alert), desktop to its background (nothing)
    Case2(fun.FUN_DRAG, COPIED, RETURN_KEY, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_DRAG, TRASHED, DIALOG_OK_CLICKED, replayed=True, budget=COPY_ROW_INSNS),
    Case2(fun.FUN_DRAG, D2DESK_COPY, RETURN_KEY), Case2(fun.FUN_DRAG, TRASH_INTO_A, RETURN_KEY),
    Case2(fun.FUN_DRAG, TRASHED, RETURN_KEY, why="a window's file let go on the desktop's background: refused, the alert",
          arguments=lambda a: (a.arguments[0], 0, a.arguments[2], a.arguments[2])),
    Case2(fun.FUN_DRAG, D2DESK_ICON_ON_ICON, why="a desktop icon (the trash) let go on the desktop's background: nothing, 0",
          arguments=lambda a: (0, 0, a.arguments[2], a.arguments[2]), yields=False),
)
BY_LABEL_WAVE_2 = {label2(each): each for each in CASES_WAVE_2}
assert len(BY_LABEL_WAVE_2) == len(CASES_WAVE_2), "two driver cases of one id"


@functools.cache
def _arrival2(each):
    arrived = da.arrival(each.name, each.chain, each.nth)
    if each.why:
        arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
        arrived = arrived._replace(arguments=tuple(arrived.arguments if arguments is None else arguments))
    return arrived


def _pokes2(each):
    arrived = _arrival2(each)
    layers = [each.laid[1](arrived)] if each.laid else []
    if each.replayed:
        layers.insert(0, fun.engine_replayed(each.wake)[1](arrived))
    return case.merge_pokes(da.machine_of(arrived), *layers)


def tier_1_wave_2(each):
    """THE CASE: a row that switches (`aes_event.woken_row`, through the companion), its waits ended by its wake — the
    C core through the host's scheduler held to the ROM's routine from the same entry: the idles, the image at every
    dispatch and where it returns, the answer at its width. Its `CompanionRun`."""
    arrived, pokes = _arrival2(each), _pokes2(each)
    if not each.yields:
        return aes.run_function(each.name, arrived.arguments, pokes, answer_compared=not each.unanswered)
    at_idle = each.wake.at_idle(each.chain) if each.wake else {}
    row = aes_event.woken_row(label2(each), each.name, arrived.arguments, lambda: pokes, at_idle, None, objects=True,
                              answered=vdi.ALCYON[each.name].restype is not None and not each.unanswered, budget=each.budget)
    ran, the_rom_s = da.held(row), da.the_rom_s_run(row)
    assert bool(the_rom_s.idles) == (each.wake is not None), f"{label2(each)}: the ROM's run idles {the_rom_s.idles} time(s)"
    assert ran.entered and ran.entered[-1] == aes.SHELL_PD, f"{label2(each)}: the run does not end in the desk's own process"
    return ran


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_driver_from_its_arrival_is_the_rom_s(name):
    """THE CASE (`tier_1_wave_2`) — and where GEMDOS is replayed, THE CALLS THE C MADE ARE THE ROM'S RUN'S OWN (the
    ledger both shores leave, read back)."""
    each = BY_LABEL_WAVE_2[name]
    ran = tier_1_wave_2(each)
    if each.replayed:
        made = tuple(function for function, _frame in fun._dd.engine_calls(ran.image))
        assert made == fun.in_place(_arrival2(each), each.wake.receptions(each.chain) if each.wake else ()).functions


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 31, 19


def test_every_driver_has_a_case_at_an_arrival_of_its_own():
    at_its_own = [each for each in CASES_WAVE_2 if not each.why]
    assert {each.name for each in at_its_own} == set(fun.UNIT_H_WAVE_2)
    assert (len(at_its_own), len(CASES_WAVE_2) - len(at_its_own)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)


VOID_WAVE_2 = [name for name, (restype, _frame) in fun.SIGNATURES_WAVE_2.items() if restype is None]


READERS_WAVE_2 = {fun.FUN_MKDIR: 0, fun.FUN_OP: 4, fun.FUN_DDST: 2, fun.FUN_WDST: 2, fun.FUN_DISK: 1, fun.FUN_D2DESK: 1,
                  fun.FUN_DRAG: 1}


def test_no_caller_in_the_rom_reads_what_a_void_driver_leaves_in_d0_and_who_reads_the_others():
    """D0 (`aes_deskbind.answer_readers`): the four void drivers' D0 — their last callee's — is read by no instruction of
    the ROM; of the answering drivers', fun_mkdir's by none (the File menu's handler drops it) and the others' by their
    callers (fun_op's by fun_win2win, fun_win2desk and fun_disk's two drops; fun_drag's by the button handler)."""
    assert {name: db.answer_readers(da.entry_of(name)) for name in VOID_WAVE_2} == {name: set() for name in VOID_WAVE_2}
    assert {name: len(db.answer_readers(da.entry_of(name))) for name in READERS_WAVE_2} == READERS_WAVE_2


NO_WORD_IN_C_WAVE_2, CALLER_S_D7 = 15, 1


def test_the_cases_whose_d0_the_c_does_not_have_are_counted():
    """THE COUNT: the cases of void drivers (the ROM's D0 a leftover the C has no word for), and fun_disk's one arm
    that answers its caller's D7 (no path node free)."""
    assert sum(each.name in VOID_WAVE_2 for each in CASES_WAVE_2) == NO_WORD_IN_C_WAVE_2
    assert sum(bool(each.unanswered) for each in CASES_WAVE_2) == CALLER_S_D7


def test_fun_disk_s_emptied_arrival_finds_no_file():
    """READ OFF THE RUN IN PLACE, not the chain's name: over EMPTIED_INTO_A fun_disk's one search answers EFILNF."""
    replay = fun.in_place(_arrival2(Case2(fun.FUN_DISK, EMPTIED_INTO_A, replayed=True)))
    assert replay.functions[-1] == fun._dd.FSFIRST and replay.answers[-1] == EFILNF & aes.LONG_MASK


# ---- FLIPPED (band 6 slice F3, stage 2, author A): the drivers but fun_d2desk and fun_drag, HELD UNBOUND to stage 3 ----
def test_the_drivers_are_flipped_and_two_held_unbound(blob):
    """THE FLIP PIN of the nine (`aes_deskarrive.flipped`: each core called by its own thunk of the table, its entry
    ours through it) and THE UNBOUND PIN of fun_d2desk and fun_drag (`aes_deskarrive.unbound`: their entries the ROM's,
    no registry row, no function outside the unbound desk refers to a held core) — held to stage 3
    (`aes_deskfun.UNIT_H_WAVE_2_HELD_AT_F3`)."""
    da.flipped(blob, fun.UNIT_H_WAVE_2_FLIPPED)
    da.unbound(blob, fun.UNIT_H_WAVE_2_HELD_AT_F3)


# ---- band 6 slice F3, stage 2: THE DRIVERS' ROWS -------------------------------------------------------------------------
# EVERY CASE AT AN ARRIVAL OF A FLIPPED DRIVER REGISTERED (`aes_deskarrive.register_row`) OVER ITS OWN STAGING — the
# orchestrator's ruling (c), stage 1's row kind: the arrival's megabyte whole but the harness's window, where GEMDOS is
# reached the ROM's own run in place laid over it as the copy engine's recorder's script (`aes_deskdir.replayed`,
# `REPLAYED` in the row's name; its 24 entries, not band 5's 11), the case's wake at the row's idles (`at_idle`), the
# recorder's twins bound in the row's child (`aes_deskfun.REACH_GEMDOS`'s declared child doors). Every one SWITCHES: A
# DOOR USER where its run calls a rebound entry of the event layer (MEASURED: the table's second count), one WITH NO DOOR
# else. A row whose run is past the default derivation margin DECLARES ITS OWN BUDGET — its case's, measured at Tier 1
# (the user's ruling of 2026-10-21, "rows may declare budget": held both ways by every derivation of the row). The
# classes stay Tier 1's.
AT_ARRIVALS_WAVE_2 = [each for each in CASES_WAVE_2 if not each.why and each.name in fun.UNIT_H_WAVE_2_FLIPPED]


def driver_row_label(each):
    """A row's label: the arrival, the staging, the wake (the routine is its name's core)."""
    said = f"arrival {each.nth} of {each.chain}" + (f" [{fun._dd.REPLAYED}]" if each.replayed else "")
    return said + (f"; {WAKE_NAMED[each.wake]}" if each.wake else "")


def _driver_row_pokes(each):
    arrived = _arrival2(each)
    replayed = [fun.engine_replayed(each.wake)[1](arrived)] if each.replayed else []
    return case.merge_pokes(da.row_machine_of(arrived), *replayed)


def _driver_row(each):
    at_idle = each.wake.at_idle(each.chain) if each.wake else {}
    return da.register_row(da.Case(each.name, each.chain, each.nth, yields=each.yields), pokes=_driver_row_pokes(each),
                           label_said=driver_row_label(each), at_idle=at_idle, budget=each.budget,
                           door=label2(each) not in DRIVER_ROWS_WITH_NO_DOOR)


# MEASURED (the table's second count): every driver row calls a rebound entry — the alerts', form_do's, the rebuilt
# window's bindings — but these.
DRIVER_ROWS_WITH_NO_DOOR = frozenset((label2(Case2(fun.FUN_DISK, EMPTIED_INTO_A, replayed=True)),))   # its search finds no file
DRIVER_ROWS = {label2(each): _driver_row(each) for each in AT_ARRIVALS_WAVE_2}
DRIVER_DOOR_USERS_PRICED = {
    "aes_desk_fun_rebld, arrival 0 of file: File > Show Info, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((345398, 604938), (338560, 592690), 11, (0, 0, 0)),
    "aes_desk_fun_rebld, arrival 0 of files: the program selected, File > Show Info, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((391440, 670850), (384602, 658602), 11, (0, 0, 0)),
    "aes_desk_fun_rebld, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((323680, 577956), (316364, 565062), 11, (0, 0, 0)),
    "aes_desk_fun_rebld, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((355212, 620530), (347896, 607636), 11, (0, 0, 0)),
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 'A' typed, Return":
        ((871984, 1339074), (821442, 1256600), 18, (0, 0, 0)),
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder again, 'A', Return — the name taken, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 'A' typed, Return, Return at the alert":
        ((705942, 1001060), (641970, 897690), 14, (0, 0, 0)),
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return; Return":
        ((437834, 600410), (412346, 558400), 6, (0, 0, 0)),
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return; the dialog's Cancel clicked":
        ((466304, 643286), (410216, 555584), 8, (0, 0, 0)),
    "aes_desk_fun_op, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((525924, 704158), (500436, 662148), 6, (0, 0, 0)),
    "aes_desk_fun_op, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((472120, 628662), (446632, 586652), 6, (0, 0, 0)),
    "aes_desk_fun_op, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        ((548448, 742182), (493874, 656210), 8, (0, 0, 0)),
    "aes_desk_fun_ddst, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        ((548526, 742746), (493952, 656774), 8, (0, 0, 0)),
    "aes_desk_fun_ddst, arrival 0 of file: dragged onto drive A:'s icon, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        ((818926, 1095430), (773058, 1020318), 11, (0, 0, 0)),
    "aes_desk_fun_wdst, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((527132, 706032), (501644, 664022), 6, (0, 0, 0)),
    "aes_desk_fun_wdst, arrival 0 of files: the long file dragged onto the folder, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((528700, 707722), (503212, 665712), 6, (0, 0, 0)),
    "aes_desk_fun_wdst, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        ((819328, 1095666), (773460, 1020554), 11, (0, 0, 0)),
    "aes_desk_fun_win2win, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((885668, 1332970), (852864, 1278066), 17, (0, 0, 0)),
    "aes_desk_fun_win2desk, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        ((873526, 1323502), (811636, 1224636), 19, (0, 0, 0)),
    "aes_desk_fun_win2desk, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        ((818518, 1236692), (785714, 1181788), 17, (0, 0, 0)),
    "aes_desk_fun_disk, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        ((960040, 1285376), (914172, 1210264), 11, (0, 0, 0)),
    "aes_desk_fun_desk2win, arrival 0 of A: opened, the trash dragged into its window, Return; Return":
        ((144998, 230448), (124262, 196668), 7, (0, 0, 0)),
    "aes_desk_fun_desk2win, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        ((1309510, 1898632), (1256326, 1810626), 22, (0, 0, 0)),
}
DRIVER_DOOR_USERS_WHOLE_RUN = {
    "aes_desk_fun_rebld, arrival 0 of file: File > Show Info, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (1833908, 1600222), "bench_shipped": (1833908, 1603052)},
    "aes_desk_fun_rebld, arrival 0 of files: the program selected, File > Show Info, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (2085436, 1837678), "bench_shipped": (2085436, 1838438)},
    "aes_desk_fun_rebld, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (1775252, 1547274), "bench_shipped": (1775252, 1548208)},
    "aes_desk_fun_rebld, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (1850344, 1613086), "bench_shipped": (1850344, 1614498)},
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 'A' typed, Return":
        {"bench": (4910250, 4540000), "bench_shipped": (4910250, 4527624)},
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder again, 'A', Return — the name taken, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; 'A' typed, Return, Return at the alert":
        {"bench": (4755536, 4554718), "bench_shipped": (4755536, 4532234)},
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return; Return":
        {"bench": (2773604, 2667240), "bench_shipped": (2773604, 2660176)},
    "aes_desk_fun_mkdir, arrival 0 of folder: File > New Folder, 'A', Return; the dialog's Cancel clicked":
        {"bench": (2817738, 2699972), "bench_shipped": (2817738, 2691392)},
    "aes_desk_fun_op, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (3451372, 3342016), "bench_shipped": (3451372, 3331946)},
    "aes_desk_fun_op, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (3070866, 2974184), "bench_shipped": (3070866, 2968524)},
    "aes_desk_fun_op, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        {"bench": (3544284, 3421194), "bench_shipped": (3544284, 3410962)},
    "aes_desk_fun_ddst, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        {"bench": (3544848, 3421272), "bench_shipped": (3544848, 3411040)},
    "aes_desk_fun_ddst, arrival 0 of file: dragged onto drive A:'s icon, Return — the name conflict, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        {"bench": (5422940, 5265426), "bench_shipped": (5422940, 5235996)},
    "aes_desk_fun_wdst, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (3453246, 3343752), "bench_shipped": (3453246, 3333430)},
    "aes_desk_fun_wdst, arrival 0 of files: the long file dragged onto the folder, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (3466526, 3356964), "bench_shipped": (3466526, 3346588)},
    "aes_desk_fun_wdst, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        {"bench": (5425204, 5268068), "bench_shipped": (5425204, 5238558)},
    "aes_desk_fun_win2win, arrival 0 of folder: the file dragged onto it, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (5309998, 4960490), "bench_shipped": (5309998, 4951528)},
    "aes_desk_fun_win2desk, arrival 0 of file: dragged to the trash, OK [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; the dialog's OK clicked":
        {"bench": (5322900, 4969940), "bench_shipped": (5322900, 4960660)},
    "aes_desk_fun_win2desk, arrival 0 of file: dragged to the trash, Return (Cancel, the dialog's default) [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return":
        {"bench": (4902574, 4570190), "bench_shipped": (4902574, 4567412)},
    "aes_desk_fun_disk, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        {"bench": (5965870, 5773002), "bench_shipped": (5965870, 5743326)},
    "aes_desk_fun_desk2win, arrival 0 of A: opened, the trash dragged into its window, Return; Return":
        {"bench": (1319720, 1253584), "bench_shipped": (1319720, 1247230)},
    "aes_desk_fun_desk2win, arrival 0 of A: opened, drive A: dragged into its window, Return [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]; Return, Return":
        {"bench": (7802976, 7372224), "bench_shipped": (7802976, 7345458)},
}
DRIVER_NO_DOOR_PREMISES = {
    "aes_desk_fun_disk, arrival 0 of file: dragged to the trash, OK — then drive A: dragged into its window [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), 0x0, ()),
}
DRIVER_NO_DOOR_PRICED = {
    "aes_desk_fun_disk, arrival 0 of file: dragged to the trash, OK — then drive A: dragged into its window [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        ((137234, 184920), None, None, (0, 0, 0)),
}
DRIVER_NO_DOOR_WHOLE_RUN = {
    "aes_desk_fun_disk, arrival 0 of file: dragged to the trash, OK — then drive A: dragged into its window [GEMDOS REPLAYED: the ROM's own run in place — its answers, its DTAs at each search]":
        {"bench": (530436, 495000), "bench_shipped": (530436, 495538)},
}
DRIVER_ROWS_MADE, DRIVER_BUDGETED = 23, 14      # every case at an arrival of the nine flipped (none LAID); those past the margin


def test_every_driver_case_at_an_arrival_is_a_row_and_its_pins_are_the_rows():
    """EVERY CASE AT AN ARRIVAL OF A FLIPPED DRIVER A ROW (those past the margin under their declared budget), every
    flipped driver with a row; the door users' pins (read by `test_tier3.py`) and the no-door rows' exactly the rows of
    each kind."""
    import aes_switching
    assert {BY_LABEL_WAVE_2[name].name for name in DRIVER_ROWS} == set(fun.UNIT_H_WAVE_2_FLIPPED)
    assert (len(DRIVER_ROWS), sum(bool(row.budget) for row in DRIVER_ROWS.values())) == (DRIVER_ROWS_MADE, DRIVER_BUDGETED)
    door_users = {aes_switching.row_name(row) for row in DRIVER_ROWS.values() if row.door}
    assert set(DRIVER_DOOR_USERS_PRICED) == set(DRIVER_DOOR_USERS_WHOLE_RUN) == door_users
    assert set(DRIVER_NO_DOOR_PREMISES) == set(DRIVER_NO_DOOR_PRICED) == set(DRIVER_NO_DOOR_WHOLE_RUN) == {
        aes_switching.row_name(row) for row in DRIVER_ROWS.values() if not row.door}


def test_a_driver_row_s_declared_budget_is_its_tier_1_case_s_own():
    """EACH DRIVER ROW DECLARES ITS TIER 1 CASE'S OWN BUDGET — not merely one the rule admits (a budget copied from
    another case would fit it too) — and none where its case declares none."""
    assert {name: row.budget for name, row in DRIVER_ROWS.items()} == {name: BY_LABEL_WAVE_2[name].budget for name in DRIVER_ROWS}


def test_a_plain_row_declaring_a_budget_is_refused_by_name_by_aes_deskarrive():
    """A PLAIN ROW DECLARES NO BUDGET (`aes_deskarrive.register_row`): its path forwards none to `aes.register`, so a
    declaration there would be dropped in silence — it is refused by name, before anything is registered."""
    with pytest.raises(AssertionError, match="a plain row declares no derivation budget"):
        da.register_row(da.Case(*SHORT_CASE, yields=False), budget=aes_event.DERIVATION_INSNS + 1)


@pytest.mark.parametrize("name", DRIVER_NO_DOOR_PREMISES)
def test_a_driver_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    import aes_deskapp
    aes_deskapp.vet_the_premise(name, DRIVER_NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", DRIVER_NO_DOOR_WHOLE_RUN)
def test_a_driver_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    import aes_deskapp
    aes_deskapp.vet_on_a_blob(blob, name, DRIVER_NO_DOOR_PREMISES, DRIVER_NO_DOOR_PRICED, DRIVER_NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", DRIVER_NO_DOOR_PRICED)
def test_a_driver_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    import aes_deskapp
    aes_deskapp.vet_the_price(name, DRIVER_NO_DOOR_PRICED)


# ---- A NAMED ROW'S DECLARED BUDGET, HELD BOTH WAYS (the user's ruling of 2026-10-21): over fun_win2win's copy (its run
# measured LONG_RUN instructions) and fun_rebld's Show Info (a run the default admits), each declaration the rule
# refuses is refused by name at the row's derivation — not fitted, stale, undeclared, unneeded.
LONG_RUN, LONG_CASE = 493_673, (fun.FUN_WIN2WIN, COPIED)
SHORT_CASE = (fun.FUN_REBLD, FILE_INFO)


def _derived_with(case_key, budget):
    import aes_switching
    each = next(each for each in AT_ARRIVALS_WAVE_2 if (each.name, each.chain) == case_key)
    at_idle = each.wake.at_idle(each.chain) if each.wake else {}
    pokes = _driver_row_pokes(each)
    row = da.row_of(_arrival2(each), "a budget probed", True, at_idle=at_idle, pokes=pokes, budget=budget)
    return aes_switching.settled(row)


BUDGET_REFUSED = {
    "not fitted (under five times the run)": (LONG_CASE, LONG_RUN * aes_event.DERIVATION_MARGIN - 1,
                                              r"inside its declared budget's .* margin of 5: raise the row's budget"),
    "stale (over ten times the run)": (LONG_CASE, LONG_RUN * aes_event.DERIVATION_MARGIN * aes_event.DERIVATION_STALE + 1,
                                       r"the declaration is stale — .* a declared budget may be at most"),
    "undeclared on a long row": (LONG_CASE, None, r"inside DERIVATION_INSNS' margin of 5: raise the budget"),
    "declared on a short row (not needed)": (SHORT_CASE, aes_event.DERIVATION_INSNS + 1,
                                             r"the declaration is stale — DERIVATION_INSNS .* admits this run"),
}


@pytest.mark.parametrize("which", BUDGET_REFUSED)
def test_a_named_row_s_budget_is_refused_by_name_where_the_rule_refuses_it(which):
    case_key, budget, said = BUDGET_REFUSED[which]
    with pytest.raises(AssertionError, match=said):
        _derived_with(case_key, budget)


def test_a_named_row_s_budget_is_admitted_exactly_where_it_fits_and_is_not_stale():
    """GREEN at both ends of the window: five times the run, and ten."""
    for budget in (LONG_RUN * aes_event.DERIVATION_MARGIN, LONG_RUN * aes_event.DERIVATION_MARGIN * aes_event.DERIVATION_STALE):
        _derived_with(LONG_CASE, budget)
