"""THE DESK'S WINDOW OBJECTS AND PROGRAM LEAVES (`src/desk/deskwin.c`; band 6 wave 1b, group G1, unit I), HELD AT TIER 1
AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskwin.arrival`): a chain of the hands stopped at the routine's first
    instruction, the arguments read off the frame the desk's own caller pushed. Where no chain makes the machine an
    arm needs, the case is A LABELLED ARGUMENT CLASS, said in its id: the same routine over an arrival's machine with
    other arguments. Never a poke. Where neither reaches an arm, it is UNPINNED BY NAME (`UNPINNED`).
  * TIER 1 (`aes_deskwin.ran`): a routine that reaches the dispatcher through a binding of unit D's is a row that
    switches, held by `aes_switching.companion` with nothing dropped; any other is the kit's plain differential.
    pro_chdir's two `trap #1`s are answered by the recording, scripted trap with the answers its run in place got
    (SCRIPTED, in the id).
  * D0 AT RETURN. Where the core answers it is held to the ROM's D0 at the declared width. GEM's VOID routines are
    `void` in C: the word the ROM leaves is a NAMED, COUNTED DIVERGENCE, and NO CALLER IN THE ROM READS IT
    (`aes_deskbind.answer_readers`, every call site, both arms of every branch).
  * UNBOUND, on both blobs: no function outside the desk's cores linked and not flipped refers to one of unit I's,
    every Line-F entry naming one stays the ROM's, no registry names one.

WHAT IS NOT HELD: any row, any price, anything of a blob's run.
"""
from collections import Counter

import pytest

from harness import addrs

import aes
import aes_deskbind as db
import aes_deskwin as w
import case
import layouts

Case = w.Case

SHOWN, SHOWN_LONG = "file: shown, a key at its end", "files: the long file shown, a blank at each page's end and at its end"
OPEN, TWO_WINDOWS = "A: File > Open", "window: A: opened again (two windows)"
REMOVED = "A: Options > Install Disk Drive, Remove pressed"
SELECTED, CLOSED, FULLER = "drive A: selected", "window: File > Close Window", "window: its fuller clicked"
DESK_DRIVE = 1                          # obj_wfree's and obj_ialloc's parent where the desktop's icons are made
NO_DRIVE, CURRENT_DRIVE = 99, 0         # pro_chdir's two drives of no Dsetdrv
VIEW = layouts.parse_constants((aes.INCLUDE / "desk" / "deskview.h", aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)


def _the_window_s_spec(arrived):
    """pro_chdir's own drive, and — for its path — the search spec of the window whose name's path it was handed
    (its `*.*`: a wildcard to cut at), read off the arrival's WNODE and its PNODE."""
    window = arrived.arguments[1] - VIEW["WNODE_NAME_PATH"]
    return arrived.arguments[0], case.long_in(arrived.boot.ram, window + VIEW["WNODE_PATH"]) + VIEW["PNODE_SPEC"]

CASES = (
    Case("AES_ROM_OBJ_INIT", SHOWN), Case("AES_ROM_OBJ_INIT", SHOWN_LONG),
    Case("AES_ROM_OBJ_WALLOC", OPEN), Case("AES_ROM_OBJ_WALLOC", TWO_WINDOWS),       # (window 2 taken: the second root)
    Case("AES_ROM_OBJ_WFREE", OPEN), Case("AES_ROM_OBJ_WFREE", CLOSED), Case("AES_ROM_OBJ_WFREE", REMOVED),
    Case("AES_ROM_OBJ_WFREE", TWO_WINDOWS),
    Case("AES_ROM_OBJ_IALLOC", OPEN), Case("AES_ROM_OBJ_IALLOC", REMOVED), Case("AES_ROM_OBJ_IALLOC", REMOVED, 2),
    Case("AES_ROM_OBJ_IALLOC", TWO_WINDOWS),
    Case("AES_ROM_PRO_CHDIR", OPEN, traps=2), Case("AES_ROM_PRO_CHDIR", OPEN, 2, traps=2),
    Case("AES_ROM_PRO_CHDIR", "file: File > Open (the Show / Print / Cancel alert)", 2, traps=2),
    Case("AES_ROM_PRO_CHDIR", OPEN, 2, arguments=_the_window_s_spec, traps=2,
         why="the window's search spec for its path (the desk hands its name's path, which holds no `*`): cut at the wildcard"),
    # (the two drives of no Dsetdrv: the scripted trap staged all the same, so that a C which traps where the ROM's
    # routine does not is caught by its ledger)
    Case("AES_ROM_PRO_CHDIR", OPEN, arguments=lambda a: (NO_DRIVE, a.arguments[1]), traps=2,
         why="drive 99, none (no caller of the chains' hands it): the glue's verdict cleared, nothing trapped"),
    Case("AES_ROM_PRO_CHDIR", OPEN, arguments=lambda a: (CURRENT_DRIVE, a.arguments[1]), traps=2,
         why="drive 0 (no caller of the chains' hands it): nothing made current"),
    Case("AES_ROM_PRO_CMD", SHOWN), Case("AES_ROM_PRO_CMD", SHOWN_LONG),
    Case("AES_ROM_PRO_EXEC", SHOWN), Case("AES_ROM_PRO_EXEC", "files: the program double-clicked — launched"),
    # (desk_rsrc_load's C cannot run at its arrivals: below, AT ITS ARRIVAL ONLY THE ROM'S RUN)
    Case("AES_ROM_DESK_RSRC_LOAD", w.LEAF_MACHINE, arguments=(),
         why="arrivals exist, the desk restarted after a file is shown; there rom_ram's C yields through the desk's "
             "rsrc_gaddr binding (band 6 slice B0), outside the dispatcher — a harness limit, not a machine no run makes"),
    Case("AES_ROM_INI_TREE", SHOWN), Case("AES_ROM_INI_TREE", SHOWN, 2), Case("AES_ROM_INI_TREE", SHOWN, 3),
    Case("AES_ROM_INI_STR", SHOWN), Case("AES_ROM_INI_STR", SHOWN_LONG),
    Case("AES_ROM_DO_WREDRAW", SELECTED, arm=lambda a: a[0] == 0), Case("AES_ROM_DO_WREDRAW", OPEN, 2, arm=lambda a: a[0] == 1),
    Case("AES_ROM_DO_WREDRAW", TWO_WINDOWS, 3, arm=lambda a: a[0] == 2),
    Case("AES_ROM_DO_WREDRAW", "a rubber box on the desktop, round the trash"),
    Case("AES_ROM_GET_XYWH", "Options > Set Preferences, Return"), Case("AES_ROM_GET_XYWH", OPEN), Case("AES_ROM_GET_XYWH", OPEN, 2),
    Case("AES_ROM_GET_SPEC", "A: File > Show Info, Return"), Case("AES_ROM_GET_SPEC", "drive A: dragged to the trash, Return"),
    Case("AES_ROM_DO_XYFIX", OPEN), Case("AES_ROM_DO_XYFIX", FULLER), Case("AES_ROM_DO_XYFIX", "folder: opened"),
    Case("AES_ROM_DO_XYFIX", OPEN, arguments=lambda a: (a.arguments[1], a.arguments[1]),
         why="x through the caller's y word ($18: past its column's middle — every x the desk hands lies before it): the next column"),
    Case("AES_ROM_DO_XYFIX", FULLER, arguments=lambda a: (a.arguments[0], a.arguments[0]),
         why="y through the caller's x word (0: above the desk's work area — every y the desk hands lies at or below its top): "
             "the work area's top"),
    Case("AES_ROM_ZOOM_CLOSED", CLOSED, arm=lambda a: a[0] == 1), Case("AES_ROM_ZOOM_CLOSED", "folder: File > Close", arm=lambda a: a[0] == 0),
    Case("AES_ROM_DO_WFULL", FULLER), Case("AES_ROM_DO_WFULL", "files: the window made full"),
    # (the window full: back to its size — a box shrunk and the window redrawn, 403,178 instructions)
    Case("AES_ROM_DO_WFULL", "window: its fuller clicked again (back to its size)", budget=2_100_000),
)
# THE ARMS NO RUN REACHES AND NO ARGUMENT CLASS CAN MAKE (each depends on the MACHINE, which a class may not poke).
UNPINNED = {
    "AES_ROM_DESK_RSRC_LOAD": "AT ITS ARRIVALS (the desk restarted after a file is shown): rom_ram's C sizes the desktop through "
                              "ini_tree and the desk's rsrc_gaddr binding, whose yield outside the dispatcher no plain case "
                              "follows (band 5's `src/aes/resource.c`, band 6 slice B0) — held over the leaf machine, its "
                              "arrivals' D0 by the ROM's run in place",
    "AES_ROM_OBJ_WALLOC": "every window root sized (none free): win_alloc refuses a fifth window before it asks; and a root of "
                          "a width and no height, which no desk call makes (obj_wfree frees at 0, 0, 0, 0)",
    "AES_ROM_OBJ_IALLOC": "every icon object 6..132 on a list: 127 icons at once",
    "AES_ROM_ZOOM_CLOSED": "graf_shrinkbox's second rectangle (the work area's) w and h as handed — UNOBSERVABLE AT TIER 1: the "
                           "shrink's XOR boxes leave no byte of memory changed, and the binding's frame is its host slot, "
                           "which no case compares (reviewer A's RA-I2 survives so)",
}

BY_LABEL = {w.label(each): each for each in CASES}
assert len(BY_LABEL) == len(CASES), "two cases of one name"
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)
A_CLASS = [name for name, each in BY_LABEL.items() if each.why and each.chain != w.LEAF_MACHINE]
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]
UNPINNED_AT_ITS_ARRIVALS = [name for name, each in BY_LABEL.items() if each.chain == w.LEAF_MACHINE]


# ---- TIER 1 ----------------------------------------------------------------------------------------------------------------------
@EVERY_CASE
def test_a_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core held to the ROM's routine from the same entry — the row's companion (the idles, the image
    at every dispatch and where it returns) or the plain differential; the answer at the declared width. No case
    idles: no routine of the unit waits."""
    each = BY_LABEL[name]
    _answer, _rom_d0, idles = w.ran(each, each.name in w.YIELDS_I)
    assert not idles, f"{name}: the ROM's run idles {idles} time(s)"


ARRIVALS, CLASSES = 41, 5


def test_every_routine_has_a_case_at_an_arrival_of_its_own():
    """Sixteen routines, each with a case at its own arrival but desk_rsrc_load (UNPINNED AT ITS ARRIVALS — the C held
    over the leaf machine, no class); the classes by routine."""
    assert {BY_LABEL[name].name for name in AT_ITS_OWN_ARRIVAL} | {"AES_ROM_DESK_RSRC_LOAD"} == set(w.UNIT_I)
    assert len(w.UNIT_I) == 16
    assert {BY_LABEL[name].name for name in A_CLASS} == {"AES_ROM_PRO_CHDIR", "AES_ROM_DO_XYFIX"}
    assert [BY_LABEL[name].name for name in UNPINNED_AT_ITS_ARRIVALS] == ["AES_ROM_DESK_RSRC_LOAD"]
    assert (len(AT_ITS_OWN_ARRIVAL), len(A_CLASS)) == (ARRIVALS, CLASSES)
    assert set(UNPINNED) <= set(w.UNIT_I)


# ---- D0 AT RETURN -----------------------------------------------------------------------------------------------------------------
VOID_IN_C = frozenset(name for name, (restype, _frame) in w.SIGNATURES.items() if restype is None)


def test_the_void_routines_are_gem_s_void_ones_and_no_rom_caller_reads_what_they_leave():
    """THE NAMED DIVERGENCE: seven routines are `void` in C where the ROM leaves a word (a callee's, or its own last
    store's — obj_wfree's -1) — and BY READING EVERY CALLER (`answer_readers`), no instruction of the ROM's reads it."""
    assert VOID_IN_C == {"AES_ROM_OBJ_INIT", "AES_ROM_OBJ_WFREE", "AES_ROM_DO_WREDRAW", "AES_ROM_GET_XYWH", "AES_ROM_DO_XYFIX",
                         "AES_ROM_ZOOM_CLOSED", "AES_ROM_DO_WFULL"}
    for name in VOID_IN_C:
        assert db.calls_of(getattr(addrs, name)), f"{name}: nothing calls it — no reader to find"
        assert not db.answer_readers(getattr(addrs, name)), f"{name}: a ROM caller reads what it leaves in D0"


# WHO READS THE ANSWERS THE C HAS: how many instructions of the GEM text read each (through a caller that returns it).
READ_AT = {"AES_ROM_OBJ_WALLOC": 1, "AES_ROM_OBJ_IALLOC": 2, "AES_ROM_PRO_CMD": 4, "AES_ROM_PRO_EXEC": 1, "AES_ROM_INI_STR": 4,
           "AES_ROM_GET_SPEC": 8}


def test_the_answers_the_c_has_are_read_where_the_reading_says():
    """...and of the nine that answer, six are read (the count of reading instructions), three by nothing."""
    read = {name: len(db.answer_readers(getattr(addrs, name))) for name in w.UNIT_I if name not in VOID_IN_C}
    assert {name: sites for name, sites in read.items() if sites} == READ_AT


# ...and the one that leaves its CALLER's D0: it stores none of its own (get_xywh's four stores through A0).
NO_ANSWER_OF_ITS_OWN = ("AES_ROM_GET_XYWH",)


@pytest.mark.parametrize("name", [name for name in AT_ITS_OWN_ARRIVAL
                                  if not BY_LABEL[name].traps and BY_LABEL[name].name not in NO_ANSWER_OF_ITS_OWN])
def test_the_rom_s_routine_in_place_leaves_the_d0_its_harness_run_does(name):
    """THE HARNESS-STACK RUN IS THE MACHINE'S OWN, as far as D0: the ROM's routine run IN PLACE from the arrival (the
    desk's own stack, to the address its caller's call returns to) leaves the D0 the case's ROM run leaves — the whole
    register for a pointer, its word otherwise."""
    each = BY_LABEL[name]
    _answer, rom_d0, _idles = w.ran(each, each.name in w.YIELDS_I)
    in_place = w.in_place(each.name, each.chain, each.nth).returned.registers["d0"]
    mask = aes.LONG_MASK if w.SIGNATURES[each.name][0] is aes.LONG_ANSWER else aes.WORD_MASK
    assert in_place & mask == rom_d0 & mask


@pytest.mark.parametrize("chain", (SHOWN, SHOWN_LONG))
def test_desk_rsrc_load_at_its_arrivals_answers_done_in_the_rom_s_own_run(chain):
    """WHERE ITS C CANNOT RUN (UNPINNED above): the ROM's desk_rsrc_load in place at its arrival answers 1."""
    assert w.in_place("AES_ROM_DESK_RSRC_LOAD", chain).returned.registers["d0"] & aes.WORD_MASK == 1


def test_the_answers_that_are_not_the_rom_s_are_counted_by_name():
    """THE COUNT, over the battery's cases: how many answer nothing in C where the ROM leaves a word."""
    assert Counter(BY_LABEL[name].name in VOID_IN_C for name in BY_LABEL)[True] == 23


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------------
def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_one(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every core of the unit
    linked; and no function outside the unbound desk (the held cores and what only they reach) refers to ANY held core — unit L's,
    another group's and the bindings call unit I's by design."""
    assert not db.bound_referrers(blob, w.UNIT_I)


def test_the_table_s_entries_stay_the_rom_s_and_no_registry_names_one():
    """...the generator's verdict for each of the sixteen is THE ROM'S (`linef_table.LINKED_AND_NOT_FLIPPED`), and no
    registered row is one of theirs."""
    assert w.verdicts_not_the_rom_s(w.UNIT_I) == (set(), [])


# ==== BAND 6 WAVE 2 (group G3): THE UNIT'S LAST FOUR — pro_run, desk_clear, desk_verify, do_wopen ====================
# Held as wave 1b's sixteen are (the module's docstring), over their own case list: wave 1b's counts above stay theirs.
DESKTOP_INFO, PREFERENCES = "Desk > Desktop Info, Return", "Options > Set Preferences, Return"
LAUNCHED, FOLDER_OPENED = "files: the program double-clicked — launched", "folder: opened"
NEW_FOLDER = "folder: File > New Folder, 'A', Return"
NO_WINDOW = layouts.parse_constants((aes.INCLUDE / "desk" / "deskwin.h",), known=aes.CONSTANTS)["PRO_RUN_NO_WINDOW"]  # none

CASES_WAVE_2 = (
    Case("AES_ROM_PRO_RUN", SHOWN), Case("AES_ROM_PRO_RUN", SHOWN_LONG), Case("AES_ROM_PRO_RUN", LAUNCHED),
    Case("AES_ROM_PRO_RUN", SHOWN, arguments=lambda a: (*a.arguments[:2], NO_WINDOW & 0xffff, a.arguments[3]),
         why="window -1, none to open again (no caller of the chains' hands it: every pro_run is a file shown or a "
             "program launched from a window)"),
    Case("AES_ROM_DESK_CLEAR", OPEN, arm=lambda a: a[0] == 1), Case("AES_ROM_DESK_CLEAR", TWO_WINDOWS, 2, arm=lambda a: a[0] == 2),
    Case("AES_ROM_DESK_CLEAR", NEW_FOLDER, arm=lambda a: a[0] == 0),
    Case("AES_ROM_DESK_VERIFY", DESKTOP_INFO, arm=lambda a: a == (0, 0)),
    Case("AES_ROM_DESK_VERIFY", CLOSED, 2, arm=lambda a: a == (0, 1)),
    Case("AES_ROM_DESK_VERIFY", "window: View > Show as Text", arm=lambda a: a == (1, 0)),
    Case("AES_ROM_DESK_VERIFY", OPEN, 2, arm=lambda a: a == (1, 1)),
    Case("AES_ROM_DESK_VERIFY", TWO_WINDOWS, 2, arm=lambda a: a == (2, 1)),
    # (a new window: wind_open's run, 346,795 and 427,943 instructions)
    Case("AES_ROM_DO_WOPEN", OPEN, arm=lambda a: a[0] == 1, budget=2_100_000),
    Case("AES_ROM_DO_WOPEN", TWO_WINDOWS, arm=lambda a: a[0] == 1, budget=2_600_000),
    Case("AES_ROM_DO_WOPEN", SHOWN, arm=lambda a: a[0] == 0), Case("AES_ROM_DO_WOPEN", FOLDER_OPENED, arm=lambda a: a[0] == 0),
    Case("AES_ROM_DO_WOPEN", LAUNCHED, arm=lambda a: a[0] == 0),
)
# (the wave-2 fix pass's) REACHED BY A RUN, NOT HELD: a text view's line shown ("text view: A: opened", the line
# selected, File > Open, Return) reaches do_wopen over the line's G_USERDEF object — its box's width arm (Reviewer B's
# RB2) — but the C's act_chg draws that object through ub_trampoline's call by value (`$fe3f3e`), which a row's child
# does not serve (measured: the fork ends by name). UNPINNED AT ITS ARRIVAL, by name.
UNPINNED_WAVE_2 = {
    "AES_ROM_DO_WOPEN": "a text view's line opened (a G_USERDEF object: the box's width arm) — reached by a run, its C's draw of "
                        "the line a USERDEF far call no row's child serves",
}
BY_LABEL_WAVE_2 = {w.label(each): each for each in CASES_WAVE_2}
assert len(BY_LABEL_WAVE_2) == len(CASES_WAVE_2), "two cases of one name"
A_CLASS_WAVE_2 = [name for name, each in BY_LABEL_WAVE_2.items() if each.why]
AT_ITS_OWN_ARRIVAL_WAVE_2 = [name for name, each in BY_LABEL_WAVE_2.items() if not each.why]
# The routines whose run reaches the dispatcher through a binding of unit D's — desk_verify only where it rebuilds a
# window's view (a window named, and `changed`).
YIELDS_I_WAVE_2 = frozenset({"AES_ROM_PRO_RUN", "AES_ROM_DESK_CLEAR", "AES_ROM_DO_WOPEN"})


def yields_wave_2(each):
    if each.name == "AES_ROM_DESK_VERIFY":
        window, changed = w.arrival_of(each).arguments
        return bool(window and changed)
    return each.name in YIELDS_I_WAVE_2


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE, as wave 1b's: the C core held to the ROM's routine from the same entry; no case idles."""
    each = BY_LABEL_WAVE_2[name]
    _answer, _rom_d0, idles = w.ran(each, yields_wave_2(each))
    assert not idles, f"{name}: the ROM's run idles {idles} time(s)"


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 16, 1


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    """The four, each with a case at its own arrival; the one class pro_run's window -1."""
    assert {BY_LABEL_WAVE_2[name].name for name in AT_ITS_OWN_ARRIVAL_WAVE_2} == set(w.UNIT_I_WAVE_2)
    assert {BY_LABEL_WAVE_2[name].name for name in A_CLASS_WAVE_2} == {"AES_ROM_PRO_RUN"}
    assert (len(AT_ITS_OWN_ARRIVAL_WAVE_2), len(A_CLASS_WAVE_2)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)
    assert set(UNPINNED_WAVE_2) <= set(w.UNIT_I_WAVE_2)


VOID_IN_C_WAVE_2 = frozenset(name for name, (restype, _frame) in w.SIGNATURES_WAVE_2.items() if restype is None)


def test_the_wave_2_void_routines_are_gem_s_void_ones_and_no_rom_caller_reads_what_they_leave():
    """THE NAMED DIVERGENCE: desk_clear, desk_verify and do_wopen are `void` in C where the ROM leaves a callee's word
    (their last instructions store to memory) — and no instruction of the ROM's reads it."""
    assert VOID_IN_C_WAVE_2 == {"AES_ROM_DESK_CLEAR", "AES_ROM_DESK_VERIFY", "AES_ROM_DO_WOPEN"}
    for name in VOID_IN_C_WAVE_2:
        assert db.calls_of(getattr(addrs, name)), f"{name}: nothing calls it — no reader to find"
        assert not db.answer_readers(getattr(addrs, name)), f"{name}: a ROM caller reads what it leaves in D0"


READ_AT_WAVE_2 = {"AES_ROM_PRO_RUN": 2}


def test_the_wave_2_answers_the_c_has_are_read_where_the_reading_says():
    """pro_run answers pro_exec's word: read where the reading says."""
    read = {name: len(db.answer_readers(getattr(addrs, name))) for name in w.UNIT_I_WAVE_2 if name not in VOID_IN_C_WAVE_2}
    assert {name: sites for name, sites in read.items() if sites} == READ_AT_WAVE_2


@pytest.mark.parametrize("name", AT_ITS_OWN_ARRIVAL_WAVE_2)
def test_a_wave_2_rom_routine_in_place_leaves_the_d0_its_harness_run_does(name):
    """As wave 1b's: the ROM's routine IN PLACE leaves the D0 the case's ROM run leaves (its word)."""
    each = BY_LABEL_WAVE_2[name]
    _answer, rom_d0, _idles = w.ran(each, yields_wave_2(each))
    in_place = w.in_place(each.name, each.chain, each.nth).returned.registers["d0"]
    assert in_place & aes.WORD_MASK == rom_d0 & aes.WORD_MASK


def test_the_wave_2_answers_that_are_not_the_rom_s_are_counted_by_name():
    assert Counter(BY_LABEL_WAVE_2[name].name in VOID_IN_C_WAVE_2 for name in BY_LABEL_WAVE_2)[True] == 13


def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_a_wave_2_one(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`), asked of unit I's wave-2 four."""
    assert not db.bound_referrers(blob, w.UNIT_I_WAVE_2)


def test_the_wave_2_table_s_entries_stay_the_rom_s_and_no_registry_names_one():
    assert w.verdicts_not_the_rom_s(w.UNIT_I_WAVE_2) == (set(), [])
