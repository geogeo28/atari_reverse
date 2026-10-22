"""THE DESK'S WINDOW OBJECTS AND PROGRAM LEAVES (`src/desk/deskwin.c`; band 6 wave 1b, group G1, unit I), HELD AT TIER 1
AT THE ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2, FLIPPED (do_wredraw, which calls the objc_draw binding, since
slice F2c): the Line-F table's entry for each is its thunk, and its cases at arrivals are Tier 3 rows (`ROWS`, below).

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
  * FLIPPED (band 6 slice F2), held on both blobs: each flipped routine's thunk of the table calls its core, and no
    function outside the unbound desk refers to a core still held; EVERY CASE AT AN ARRIVAL OF A FLIPPED ROUTINE IS A
    ROW (`ROWS`), priced by Tier 3 over the arrival's machine (the orchestrator's provisional ruling R6) — desk_rsrc_load's
    two among them: a row that switches (its rom_ram yields through ini_tree and the rsrc_gaddr binding, as ini_tree's).

WHAT IS NOT HELD: the argument classes' prices (Tier 1's alone).
"""
from collections import Counter

import pytest

from harness import addrs

import aes
import aes_deskbind as db
import aes_event
import aes_deskwin as w
import aes_switching
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
    # (the desk restarted after a file is shown: rom_ram's C yields through ini_tree and the rsrc_gaddr binding — a row that
    # switches, as ini_tree's; the F2 fix pass, reviewer A's A1)
    Case("AES_ROM_DESK_RSRC_LOAD", SHOWN), Case("AES_ROM_DESK_RSRC_LOAD", SHOWN_LONG),
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
A_CLASS = [name for name, each in BY_LABEL.items() if each.why]
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]


# ---- TIER 1 ----------------------------------------------------------------------------------------------------------------------
@EVERY_CASE
def test_a_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core held to the ROM's routine from the same entry — the row's companion (the idles, the image
    at every dispatch and where it returns) or the plain differential; the answer at the declared width. No case
    idles: no routine of the unit waits."""
    each = BY_LABEL[name]
    _answer, _rom_d0, idles = w.ran(each, each.name in w.YIELDS_I)
    assert not idles, f"{name}: the ROM's run idles {idles} time(s)"


ARRIVALS, CLASSES = 43, 5


def test_every_routine_has_a_case_at_an_arrival_of_its_own():
    """Sixteen routines, each with a case at its own arrival; the classes by routine."""
    assert {BY_LABEL[name].name for name in AT_ITS_OWN_ARRIVAL} == set(w.UNIT_I)
    assert len(w.UNIT_I) == 16
    assert {BY_LABEL[name].name for name in A_CLASS} == {"AES_ROM_PRO_CHDIR", "AES_ROM_DO_XYFIX"}
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
    """...and what that D0 is at desk_rsrc_load's two: the ROM's routine in place at its arrival answers 1, done."""
    assert w.in_place("AES_ROM_DESK_RSRC_LOAD", chain).returned.registers["d0"] & aes.WORD_MASK == 1


def test_the_answers_that_are_not_the_rom_s_are_counted_by_name():
    """THE COUNT, over the battery's cases: how many answer nothing in C where the ROM leaves a word."""
    assert Counter(BY_LABEL[name].name in VOID_IN_C for name in BY_LABEL)[True] == 23


# ---- FLIPPED (band 6 slice F2, group G1) -----------------------------------------------------------------------------------------
FLIPPED = tuple(name for name in w.UNIT_I if name not in w.HELD_AT_F2)


def test_each_flipped_routine_s_thunk_calls_its_core_and_nothing_outside_the_unbound_desk_refers_to_a_held_core(blob):
    """THE FLIP: every flipped routine's core linked and CALLED BY ITS OWN THUNK of the table (`linef_to_<core>`) — and
    the desk's one unbound pin (`aes_deskbind.bound_referrers`) holds for the cores still held, the held one's among them
    (do_wredraw: no thunk, no function outside the unbound desk refers to it)."""
    assert not w.thunks_not_calling_their_core(blob, FLIPPED)
    assert not db.bound_referrers(blob, w.HELD_AT_F2)


def test_the_table_s_entries_are_the_flipped_routines_thunks_and_the_held_one_s_the_rom_s():
    """...the generator's verdict for each of the fifteen flipped is OURS, THROUGH ITS THUNK; do_wredraw's THE ROM'S, held
    by `LINKED_AND_NOT_FLIPPED` as `HELD_AT_F2` says."""
    assert w.table_verdicts(w.UNIT_I) == w.flipped_verdicts(w.UNIT_I, w.HELD_AT_F2)
    assert set(w.UNIT_I) & set(w._linef_table().LINKED_AND_NOT_FLIPPED) == set(w.HELD_AT_F2)


# ---- band 6 slice F2: THE UNIT'S ROWS ----------------------------------------------------------------------------------------------
# EVERY CASE AT AN ARRIVAL OF A FLIPPED ROUTINE, REGISTERED (`aes_deskwin.register_row`, R6's kind: the arrival's machine
# taken over at the arrival) — a routine that yields A ROW THAT SWITCHES, any other a plain row; pro_chdir's two traps
# answered by band 5's recording trap (`aes_deskwin.ROW_SCRIPTED`, in the row's name).
#   * A DOOR USER'S ROW (`DOOR_USERS`: its run arrives at an entry of the event layer's door — a binding whose AES
#     routine waits) is priced on two counts and pinned in `test_tier3.py`'s door users; the others are rows that
#     switch with no door, held here three ways (premise, whole run on both blobs, price).
#   * THE X FLAG (`aes_switching.THE_X_FLAG_ALONE`): declared on the rows whose yield parks each build's own.
# MEASURED (the table's second count: the run made calls of the door): zoom_closed where its window closes (the
# wind_close binding's wait for the screen's lock) and do_wfull's three (wind_set's) — no other row of the unit's (do_wredraw's
# four, slice F2c's, none: the objc_draw binding's yield alone).
DOOR_USERS = frozenset(name for name in AT_ITS_OWN_ARRIVAL
                       if (BY_LABEL[name].name, BY_LABEL[name].chain) in {("AES_ROM_ZOOM_CLOSED", CLOSED)}
                       or BY_LABEL[name].name == "AES_ROM_DO_WFULL")
# MEASURED (each row's blob differential at `$8995`, `$00` ours / `$10` the ROM's): ini_tree's three, ini_str's two and
# desk_rsrc_load's two (the rsrc_gaddr binding's yield after the C's own arithmetic) and pro_exec's launch (shel_write's,
# as unit D's own row there).
X_FLAG_DIFFERS = frozenset(name for name in AT_ITS_OWN_ARRIVAL
                           if BY_LABEL[name].name in ("AES_ROM_INI_TREE", "AES_ROM_INI_STR", "AES_ROM_DESK_RSRC_LOAD")
                           or (BY_LABEL[name].name, BY_LABEL[name].chain) == ("AES_ROM_PRO_EXEC", "files: the program double-clicked — launched"))
#   * NO ROW, by name (`NOT_A_ROW`): the case at an arrival no row can be made at — said.
NOT_A_ROW = {name: ("its run (the window back to its size: a box shrunk and the window redrawn, 403,178 instructions) is past "
                    "the derivation's margin, and a registered row declares a budget only where it is a session's slice "
                    "(`test_aes_event`'s rule): Tier 1 holds the case, under its own budget; do_wfull's two other arrivals are rows")
             for name in AT_ITS_OWN_ARRIVAL if BY_LABEL[name].budget}
ROWS = {name: w.register_row(BY_LABEL[name], BY_LABEL[name].name in w.YIELDS_I, door_user=name in DOOR_USERS,
                             x_flag_differs=name in X_FLAG_DIFFERS)
        for name in AT_ITS_OWN_ARRIVAL if BY_LABEL[name].name in FLIPPED and name not in NOT_A_ROW}

# ---- THE ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by each
# blob's second differential (`aes_switching.measured_on`), from the rows as registered; re-pinned from a recorded run
# (`tools/repin.py`), never by hand.
DOOR_USERS_PRICED = {
    'aes_do_wfull, arrival 1 of files: the window made full':
        ((493460, 641284), (486858, 629276), 4, (0, 0, 0)),
    'aes_do_wfull, arrival 1 of window: its fuller clicked':
        ((493412, 641236), (486810, 629228), 4, (0, 0, 0)),
    'aes_zoom_closed, arrival 1 of window: File > Close Window':
        ((338654, 417390), (337160, 414290), 3, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN = {
    'aes_do_wfull, arrival 1 of files: the window made full':
        {"bench": (3480472, 3398890), "bench_shipped": (3480472, 3396412)},
    'aes_do_wfull, arrival 1 of window: its fuller clicked':
        {"bench": (3468378, 3386770), "bench_shipped": (3468378, 3384318)},
    'aes_zoom_closed, arrival 1 of window: File > Close Window':
        {"bench": (2613394, 2587154), "bench_shipped": (2613394, 2580538)},
}
NO_DOOR_PREMISES = {
    'aes_desk_rsrc_load, arrival 1 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    "aes_desk_rsrc_load, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_do_xyfix, arrival 1 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_do_xyfix, arrival 1 of folder: opened':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_do_xyfix, arrival 1 of window: its fuller clicked':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_ini_str, arrival 1 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 31618, ()),
    "aes_ini_str, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((), 0, 0xae5e, (0xae5e,), 31618, ()),
    'aes_ini_tree, arrival 1 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_ini_tree, arrival 2 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_ini_tree, arrival 3 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e,), 1, ()),
    'aes_obj_ialloc, arrival 1 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e,), 9, ()),
    'aes_obj_ialloc, arrival 1 of A: Options > Install Disk Drive, Remove pressed':
        ((), 0, 0xae5e, (0xae5e,), 6, ()),
    'aes_obj_ialloc, arrival 1 of window: A: opened again (two windows)':
        ((), 0, 0xae5e, (0xae5e,), 10, ()),
    'aes_obj_ialloc, arrival 2 of A: Options > Install Disk Drive, Remove pressed':
        ((), 0, 0xae5e, (0xae5e,), 7, ()),
    'aes_obj_init, arrival 1 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_obj_init, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_pro_exec, arrival 1 of file: shown, a key at its end':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    'aes_pro_exec, arrival 1 of files: the program double-clicked — launched':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 1, ()),
    'aes_zoom_closed, arrival 1 of folder: File > Close':
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    'aes_do_wredraw, arrival 1 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_do_wredraw, arrival 2 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_do_wredraw, arrival 3 of window: A: opened again (two windows)':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_do_wredraw, arrival 1 of a rubber box on the desktop, round the trash':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED = {
    'aes_desk_rsrc_load, arrival 1 of file: shown, a key at its end':
        ((6306, 9968), None, None, (0, 0, 0)),
    "aes_desk_rsrc_load, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((6306, 9968), None, None, (0, 0, 0)),
    'aes_do_xyfix, arrival 1 of A: File > Open':
        ((5302, 8338), None, None, (0, 0, 0)),
    'aes_do_xyfix, arrival 1 of folder: opened':
        ((5302, 8338), None, None, (0, 0, 0)),
    'aes_do_xyfix, arrival 1 of window: its fuller clicked':
        ((5312, 8348), None, None, (0, 0, 0)),
    'aes_ini_str, arrival 1 of file: shown, a key at its end':
        ((4946, 8104), None, None, (0, 0, 0)),
    "aes_ini_str, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((4946, 8104), None, None, (0, 0, 0)),
    'aes_ini_tree, arrival 1 of file: shown, a key at its end':
        ((4586, 7242), None, None, (0, 0, 0)),
    'aes_ini_tree, arrival 2 of file: shown, a key at its end':
        ((4586, 7242), None, None, (0, 0, 0)),
    'aes_ini_tree, arrival 3 of file: shown, a key at its end':
        ((4586, 7242), None, None, (0, 0, 0)),
    'aes_obj_ialloc, arrival 1 of A: File > Open':
        ((4950, 7488), None, None, (0, 0, 0)),
    'aes_obj_ialloc, arrival 1 of A: Options > Install Disk Drive, Remove pressed':
        ((4800, 7176), None, None, (0, 0, 0)),
    'aes_obj_ialloc, arrival 1 of window: A: opened again (two windows)':
        ((5000, 7592), None, None, (0, 0, 0)),
    'aes_obj_ialloc, arrival 2 of A: Options > Install Disk Drive, Remove pressed':
        ((4872, 7264), None, None, (0, 0, 0)),
    'aes_obj_init, arrival 1 of file: shown, a key at its end':
        ((34732, 69680), None, None, (0, 0, 0)),
    "aes_obj_init, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        ((34732, 69680), None, None, (0, 0, 0)),
    'aes_pro_exec, arrival 1 of file: shown, a key at its end':
        ((18152, 23528), None, None, (0, 0, 0)),
    'aes_pro_exec, arrival 1 of files: the program double-clicked — launched':
        ((18154, 23520), None, None, (0, 0, 0)),
    'aes_zoom_closed, arrival 1 of folder: File > Close':
        ((192802, 227734), None, None, (0, 0, 0)),
    'aes_do_wredraw, arrival 1 of drive A: selected':
        ((59386, 78220), None, None, (0, 0, 0)),
    'aes_do_wredraw, arrival 2 of A: File > Open':
        ((50120, 66924), None, None, (0, 0, 0)),
    'aes_do_wredraw, arrival 3 of window: A: opened again (two windows)':
        ((49360, 66102), None, None, (0, 0, 0)),
    'aes_do_wredraw, arrival 1 of a rubber box on the desktop, round the trash':
        ((58536, 77264), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    'aes_desk_rsrc_load, arrival 1 of file: shown, a key at its end':
        {"bench": (16730, 13814), "bench_shipped": (16730, 13452)},
    "aes_desk_rsrc_load, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        {"bench": (16730, 13814), "bench_shipped": (16730, 13452)},
    'aes_do_xyfix, arrival 1 of A: File > Open':
        {"bench": (15100, 12258), "bench_shipped": (15100, 12508)},
    'aes_do_xyfix, arrival 1 of folder: opened':
        {"bench": (15100, 12258), "bench_shipped": (15100, 12508)},
    'aes_do_xyfix, arrival 1 of window: its fuller clicked':
        {"bench": (15110, 12256), "bench_shipped": (15110, 12518)},
    'aes_ini_str, arrival 1 of file: shown, a key at its end':
        {"bench": (14866, 12160), "bench_shipped": (14866, 12076)},
    "aes_ini_str, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        {"bench": (14866, 12160), "bench_shipped": (14866, 12076)},
    'aes_ini_tree, arrival 1 of file: shown, a key at its end':
        {"bench": (14004, 11502), "bench_shipped": (14004, 11624)},
    'aes_ini_tree, arrival 2 of file: shown, a key at its end':
        {"bench": (14004, 11502), "bench_shipped": (14004, 11624)},
    'aes_ini_tree, arrival 3 of file: shown, a key at its end':
        {"bench": (14004, 11502), "bench_shipped": (14004, 11624)},
    'aes_obj_ialloc, arrival 1 of A: File > Open':
        {"bench": (14250, 11930), "bench_shipped": (14250, 12156)},
    'aes_obj_ialloc, arrival 1 of A: Options > Install Disk Drive, Remove pressed':
        {"bench": (13938, 11780), "bench_shipped": (13938, 12006)},
    'aes_obj_ialloc, arrival 1 of window: A: opened again (two windows)':
        {"bench": (14354, 11980), "bench_shipped": (14354, 12206)},
    'aes_obj_ialloc, arrival 2 of A: Options > Install Disk Drive, Remove pressed':
        {"bench": (14026, 11852), "bench_shipped": (14026, 12078)},
    'aes_obj_init, arrival 1 of file: shown, a key at its end':
        {"bench": (103490, 74076), "bench_shipped": (103490, 70738)},
    "aes_obj_init, arrival 1 of files: the long file shown, a blank at each page's end and at its end":
        {"bench": (103490, 74076), "bench_shipped": (103490, 70738)},
    'aes_pro_exec, arrival 1 of file: shown, a key at its end':
        {"bench": (59618, 63320), "bench_shipped": (59618, 55234)},
    'aes_pro_exec, arrival 1 of files: the program double-clicked — launched':
        {"bench": (60144, 63856), "bench_shipped": (60144, 55770)},
    'aes_zoom_closed, arrival 1 of folder: File > Close':
        {"bench": (1248098, 1241390), "bench_shipped": (1248098, 1239186)},
    'aes_do_wredraw, arrival 1 of drive A: selected':
        {"bench": (429524, 416624), "bench_shipped": (429524, 416218)},
    'aes_do_wredraw, arrival 2 of A: File > Open':
        {"bench": (503040, 491092), "bench_shipped": (503040, 490556)},
    'aes_do_wredraw, arrival 3 of window: A: opened again (two windows)':
        {"bench": (378058, 365940), "bench_shipped": (378058, 365484)},
    'aes_do_wredraw, arrival 1 of a rubber box on the desktop, round the trash':
        {"bench": (346418, 333544), "bench_shipped": (346418, 333178)},
}


def _registered_row(name):
    """The registered switching row of that name."""
    return aes_event.SWITCHING_ROWS[name].row


def test_the_rows_are_the_cases_at_arrivals_of_the_flipped_routines_and_split_by_their_door():
    """EVERY FLIPPED ROUTINE HAS A ROW; EVERY ROW THAT SWITCHES PINNED ONCE — a door user's in `DOOR_USERS_*` (read by
    `test_tier3.py`), any other here; the X flag declared on exactly the rows above."""
    assert {BY_LABEL[name].name for name in ROWS} == set(FLIPPED)
    switching = {aes_switching.row_name(row): name for name, row in ROWS.items() if hasattr(row, "door")}
    assert set(DOOR_USERS_PRICED) | set(NO_DOOR_PRICED) == set(switching) and not set(DOOR_USERS_PRICED) & set(NO_DOOR_PRICED)
    assert set(DOOR_USERS_PRICED) == set(DOOR_USERS_WHOLE_RUN) and set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN) == set(NO_DOOR_PREMISES)
    assert {switching[row] for row in DOOR_USERS_PRICED} == set(DOOR_USERS) - set(NOT_A_ROW) and len(NOT_A_ROW) == 1
    assert {name for name, row in ROWS.items() if getattr(row, "x_flag_differs", False)} == set(X_FLAG_DIFFERS)
    assert (len(ROWS), len(switching), len(X_FLAG_DIFFERS)) == (42, 26, 8)      # (slice F2c: do_wredraw's four, no door)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    aes_switching.vet_the_premise(_registered_row(name), aes_switching.Premise(*NO_DOOR_PREMISES[name]))


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    premise = aes_switching.Premise(*NO_DOOR_PREMISES[name])
    aes_switching.vet_on_a_blob(blob, _registered_row(name), premise, NO_DOOR_PRICED[name][3], NO_DOOR_WHOLE_RUN[name])


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    aes_switching.vet_the_table_s_price(_registered_row(name), aes_switching.Priced(*NO_DOOR_PRICED[name]))


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


# ---- FLIPPED (band 6 slice F3, stage 1): desk_clear and desk_verify; pro_run and do_wopen HELD, UNBOUND ------------------
def test_the_wave_2_two_are_flipped_and_the_other_two_held_unbound(blob):
    """THE FLIP PIN of desk_clear and desk_verify (`aes_deskarrive.flipped`) and THE UNBOUND PIN of pro_run and do_wopen
    (`aes_deskarrive.unbound`: their entries the ROM's, no registry row, no function outside the unbound desk refers to a
    held core) — held to stage 2 with unit J (`aes_deskwin.UNIT_I_WAVE_2_HELD_AT_F3`)."""
    import aes_deskarrive as dar
    dar.flipped(blob, w.UNIT_I_WAVE_2_FLIPPED)
    dar.unbound(blob, w.UNIT_I_WAVE_2_HELD_AT_F3)


# ---- band 6 slice F3: THE TWO'S ROWS — every case at an arrival of desk_clear and desk_verify registered
# (`aes_deskwin.register_row`): desk_verify's a plain row where it rebuilds no window (`yields_wave_2`), a row that
# switches where it does; desk_clear's rows that switch. The classes stay Tier 1's.
#   * DOOR USERS (`DOOR_USERS_WAVE_2`, MEASURED, the table's second count: 8 calls of a rebound entry each), pinned in
#     `DOOR_USERS_*_WAVE_2` and read by `test_tier3.py`: desk_verify's two that switch (it rebuilds the window: win_bdall);
#     desk_clear's three make no such call — rows that switch with no door.
DOOR_USERS_WAVE_2 = frozenset(name for name in AT_ITS_OWN_ARRIVAL_WAVE_2
                              if BY_LABEL_WAVE_2[name].name == "AES_ROM_DESK_VERIFY" and yields_wave_2(BY_LABEL_WAVE_2[name]))
X_FLAG_DIFFERS_WAVE_2 = frozenset()
ROWS_WAVE_2 = {name: w.register_row(BY_LABEL_WAVE_2[name], yields_wave_2(BY_LABEL_WAVE_2[name]), door_user=name in DOOR_USERS_WAVE_2,
                                    x_flag_differs=name in X_FLAG_DIFFERS_WAVE_2)
               for name in AT_ITS_OWN_ARRIVAL_WAVE_2 if BY_LABEL_WAVE_2[name].name in w.UNIT_I_WAVE_2_FLIPPED}
PLAIN_WAVE_2 = frozenset(name for name in ROWS_WAVE_2 if not yields_wave_2(BY_LABEL_WAVE_2[name]))

# ---- THE WAVE-2 ROWS' PINS — DATA, MEASURED by the table's own measurement (`aes_switching.priced_by_the_table`) and by
# each blob's second differential (`aes_switching.measured_on`), from the rows as registered (a recorded run, never by hand).
DOOR_USERS_PRICED_WAVE_2 = {
    'aes_desk_verify, arrival 2 of A: File > Open':
        ((251122, 443758), (249698, 441046), 8, (0, 0, 0)),
    'aes_desk_verify, arrival 2 of window: A: opened again (two windows)':
        ((251212, 443992), (249788, 441280), 8, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN_WAVE_2 = {
    'aes_desk_verify, arrival 2 of A: File > Open':
        {"bench": (1181294, 1007012), "bench_shipped": (1181294, 1010894)},
    'aes_desk_verify, arrival 2 of window: A: opened again (two windows)':
        {"bench": (996688, 822262), "bench_shipped": (996688, 826144)},
}
NO_DOOR_PREMISES_WAVE_2 = {
    'aes_desk_clear, arrival 1 of A: File > Open':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    'aes_desk_clear, arrival 2 of window: A: opened again (two windows)':
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_desk_clear, arrival 1 of folder: File > New Folder, 'A', Return":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
}
NO_DOOR_PRICED_WAVE_2 = {
    'aes_desk_clear, arrival 1 of A: File > Open':
        ((9476, 14078), None, None, (0, 0, 0)),
    'aes_desk_clear, arrival 2 of window: A: opened again (two windows)':
        ((9516, 14208), None, None, (0, 0, 0)),
    "aes_desk_clear, arrival 1 of folder: File > New Folder, 'A', Return":
        ((15016, 21056), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN_WAVE_2 = {
    'aes_desk_clear, arrival 1 of A: File > Open':
        {"bench": (20840, 16576), "bench_shipped": (20840, 17034)},
    'aes_desk_clear, arrival 2 of window: A: opened again (two windows)':
        {"bench": (20970, 16616), "bench_shipped": (20970, 17074)},
    "aes_desk_clear, arrival 1 of folder: File > New Folder, 'A', Return":
        {"bench": (27818, 22424), "bench_shipped": (27818, 23430)},
}


def test_the_wave_2_rows_are_the_cases_at_arrivals_and_every_one_that_switches_is_pinned_by_its_door():
    """EVERY CASE AT AN ARRIVAL OF A FLIPPED ROUTINE A ROW; the plain ones exactly those named; EVERY ROW THAT SWITCHES
    PINNED ONCE — a door user's in `DOOR_USERS_*_WAVE_2` (read by `test_tier3.py`), any other here; the X flag declared
    on exactly the rows named."""
    import aes_switching
    switching = {aes_switching.row_name(row): name for name, row in ROWS_WAVE_2.items() if hasattr(row, "door")}
    assert {name for name, row in ROWS_WAVE_2.items() if not hasattr(row, "door")} == set(PLAIN_WAVE_2)
    door_users = {row for row, name in switching.items() if ROWS_WAVE_2[name].door}
    assert {switching[row] for row in door_users} == set(DOOR_USERS_WAVE_2)
    assert set(DOOR_USERS_PRICED_WAVE_2) == set(DOOR_USERS_WHOLE_RUN_WAVE_2) == door_users
    assert set(NO_DOOR_PREMISES_WAVE_2) == set(NO_DOOR_PRICED_WAVE_2) == set(NO_DOOR_WHOLE_RUN_WAVE_2) == set(switching) - door_users
    assert {name for name, row in ROWS_WAVE_2.items() if getattr(row, "x_flag_differs", False)} == set(X_FLAG_DIFFERS_WAVE_2)
    assert (len(ROWS_WAVE_2), len(switching), len(door_users), len(X_FLAG_DIFFERS_WAVE_2)) == (8, 5, 2, 0)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES_WAVE_2)
def test_a_wave_2_row_with_no_door_has_its_premise_on_the_rom_s_run(name):
    aes_switching.vet_the_premise(aes_event.SWITCHING_ROWS[name].row, aes_switching.Premise(*NO_DOOR_PREMISES_WAVE_2[name]))


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN_WAVE_2)
def test_a_wave_2_row_with_no_door_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    premise = aes_switching.Premise(*NO_DOOR_PREMISES_WAVE_2[name])
    aes_switching.vet_on_a_blob(blob, aes_event.SWITCHING_ROWS[name].row, premise, NO_DOOR_PRICED_WAVE_2[name][3],
                                NO_DOOR_WHOLE_RUN_WAVE_2[name])


@pytest.mark.parametrize("name", NO_DOOR_PRICED_WAVE_2)
def test_a_wave_2_row_with_no_door_is_priced_as_pinned_and_under_the_bar(name):
    aes_switching.vet_the_table_s_price(aes_event.SWITCHING_ROWS[name].row, aes_switching.Priced(*NO_DOOR_PRICED_WAVE_2[name]))
