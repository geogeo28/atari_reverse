"""THE DESK'S WINDOWS — THE VIEW, THE WINDOW LIST, THE LAYOUT LEAVES (`src/desk/deskview.c`; band 6 wave 1b, group G1,
unit L), HELD AT TIER 1 AT THE ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

How a case is taken, run and held is the group's (`aes_deskwin.py`; `test_desk_win.py` says it whole): an arrival of
a chain of the hands, the routine's arguments read off its caller's frame; a row that switches where the routine
reaches a binding of unit D's, else the plain differential; the DOS glue's `trap #1`s scripted with the answers the
ROM's run in place got (SCRIPTED, in the id) where win_top and win_ontop make the window's path current; a LABELLED
ARGUMENT CLASS where no chain makes an arm, said in the id; UNPINNED BY NAME where neither can.

D0 AT RETURN: held at the declared width where the core answers; GEM's VOID routines are `void` in C, the word the
ROM leaves a NAMED, COUNTED DIVERGENCE that no instruction of the ROM reads (`aes_deskbind.answer_readers`).
"""
import struct
from collections import Counter

import pytest

from harness import addrs

import aes
import aes_deskbind as db
import aes_deskview as v
import aes_deskwin as w
import case
import layouts

Case = w.Case

OPEN, TWO_WINDOWS = "A: File > Open", "window: A: opened again (two windows)"
SHOWN, SHOWN_LONG = "file: shown, a key at its end", "files: the long file shown, a blank at each page's end and at its end"
AS_TEXT, BY_SIZE = "window: View > Show as Text", "window: View > Sort by Size"
SAVED, SELECTED = "Options > Save Desktop, Return", "drive A: selected"
SCROLLED_RIGHT = "files: the right arrow clicked, then the window made full"
SORTED_SCROLLED = "files: the right arrow clicked, then View > Sort by Size"
NEW_FOLDER, FILES = "folder: File > New Folder, 'A', Return", "files: A: opened"
NEITHER_VIEW = 2                        # a view word that is neither V_ICON nor V_TEXT
A_NARROW_WIDTH = 0x50                   # two items of the icon view's pitch across (72 + 8)
NO_SUCH_WINDOW = 5                      # a GEM window handle no WNODE holds at the arrival

CASES = (
    Case("AES_ROM_WIN_VIEW", AS_TEXT, arm=lambda a: a[0] == 1), Case("AES_ROM_WIN_VIEW", BY_SIZE, arm=lambda a: a == (0, 2)),
    Case("AES_ROM_WIN_VIEW", SHOWN, arm=lambda a: a == (0, 0)),
    Case("AES_ROM_WIN_VIEW", BY_SIZE, arguments=lambda a: (NEITHER_VIEW, a.arguments[1]),
         why="a view neither icons nor text (no caller of the desk's hands one): the extents kept, the pitch made again"),
    Case("AES_ROM_WIN_START", SHOWN), Case("AES_ROM_WIN_START", SHOWN_LONG),
    Case("AES_ROM_WIN_ALLOC", OPEN), Case("AES_ROM_WIN_ALLOC", TWO_WINDOWS),
    Case("AES_ROM_WIN_FREE", "window: File > Close Window"), Case("AES_ROM_WIN_FREE", "window: its closer clicked"),
    Case("AES_ROM_WIN_FIND", OPEN), Case("AES_ROM_WIN_FIND", TWO_WINDOWS, 2, arm=lambda a: a == (2,)),
    Case("AES_ROM_WIN_FIND", OPEN, arguments=(NO_SUCH_WINDOW,), why="a handle no WNODE holds: 0"),
    Case("AES_ROM_WIN_TOP", OPEN, traps=2), Case("AES_ROM_WIN_TOP", TWO_WINDOWS, traps=2),
    Case("AES_ROM_WIN_ONTOP", "Desk > Desktop Info, Return"), Case("AES_ROM_WIN_ONTOP", AS_TEXT, traps=2),
    Case("AES_ROM_WIN_CNT", SAVED, arm=lambda a: a == (1,)), Case("AES_ROM_WIN_CNT", SAVED, 3, arm=lambda a: a == (3,)),
    Case("AES_ROM_WIN_CNT", AS_TEXT, arm=lambda a: a == (4,)),
    Case("AES_ROM_WIN_ITH", SAVED), Case("AES_ROM_WIN_ITH", AS_TEXT),
    Case("AES_ROM_WIN_OCALC", OPEN), Case("AES_ROM_WIN_OCALC", AS_TEXT, arm=lambda a: a[1] == 0),
    Case("AES_ROM_WIN_OCALC", "window: its fuller clicked"), Case("AES_ROM_WIN_OCALC", TWO_WINDOWS),
    # (its columns scrolled one right, the window made full: the scroll pulled back)
    Case("AES_ROM_WIN_OCALC", SCROLLED_RIGHT),
    Case("AES_ROM_WIN_OCALC", SORTED_SCROLLED),          # (its scroll kept: the first file shown the second)
    Case("AES_ROM_WIN_ICALC", OPEN), Case("AES_ROM_WIN_ICALC", NEW_FOLDER, arm=lambda a: True),
    Case("AES_ROM_WIN_ICALC", FILES, 4),                # (the program: an application's ANODE)
    Case("AES_ROM_WIN_BLDVIEW", OPEN), Case("AES_ROM_WIN_BLDVIEW", AS_TEXT), Case("AES_ROM_WIN_BLDVIEW", FILES),
    Case("AES_ROM_WIN_BLDVIEW", "files: View > Show as Text"), Case("AES_ROM_WIN_BLDVIEW", TWO_WINDOWS),
    Case("AES_ROM_WIN_BLDVIEW", SORTED_SCROLLED),
    Case("AES_ROM_WIN_BLDVIEW", FILES, arguments=lambda a: (*a.arguments[:3], A_NARROW_WIDTH, a.arguments[4]),
         why="a rectangle two items wide over the four files' row (the desk's own windows fit every column): three columns "
             "laid, the fourth skipped at the row's end"),
    Case("AES_ROM_WIN_SHWALL", AS_TEXT), Case("AES_ROM_WIN_SHWALL", BY_SIZE),
    Case("AES_ROM_WIN_ISEL", SELECTED, arm=lambda a: a[2] == 0), Case("AES_ROM_WIN_ISEL", SELECTED, 2, arm=lambda a: a[2] != 0),
    Case("AES_ROM_WIN_ISEL", "Desk > Desktop Info, Return"), Case("AES_ROM_WIN_ISEL", "a rubber box on the desktop, round the trash", 2),
    Case("AES_ROM_WIN_INAME", SELECTED), Case("AES_ROM_WIN_INAME", "drive A: dragged to the trash, Return"),
    Case("AES_ROM_WIN_SINFO", OPEN), Case("AES_ROM_WIN_SINFO", "file: File > Show Info, Return"),
    Case("AES_ROM_WIN_SNAME", OPEN), Case("AES_ROM_WIN_SNAME", "folder: opened"), Case("AES_ROM_WIN_SNAME", TWO_WINDOWS),
)
# THE ARMS NO RUN REACHES AND NO ARGUMENT CLASS CAN MAKE (each depends on the MACHINE, which a class may not poke).
UNPINNED = {
    "AES_ROM_WIN_VIEW": "a screen wider than 320 pixels (the text line of 45 cells, its space two cells less a pixel), and one of "
                        "more than 300 lines (the icons' space of 8): the machine's screen is 320 x 200; and the neither-view "
                        "arm apart from the icon arm — every arrival holds the icons' extents already, and over the desk's "
                        "restart (its extents zeros) that arm divides by zero (the 68000's vector 5; the C refuses by name)",
    "AES_ROM_WIN_ALLOC": "four windows open (the count refuses a fifth); no window root free; wind_create refusing — no chain "
                         "opens a fifth window",
    "AES_ROM_WIN_BLDVIEW": "a view neither icons nor text (g_iview is the desk's own, and every caller of win_view hands 0 or 1); "
                           "a SECOND ROW after columns skipped — no machine of the hands has more files than the desk has "
                           "columns (the files machine: four items, four columns), so the skip's effect is never seen",
    "AES_ROM_WIN_OCALC": "rows rounded up past a whole row (the same: no machine has more files than columns, and never a "
                         "multiple short of a row)",
    "AES_ROM_WIN_TOP": "a cartridge's window (its name \"Cartridge\": no path made current) — no cartridge (ruling W3-R6)",
}

BY_LABEL = {w.label(each): each for each in CASES}
assert len(BY_LABEL) == len(CASES), "two cases of one name"
EVERY_CASE = pytest.mark.parametrize("name", BY_LABEL)
A_CLASS = [name for name, each in BY_LABEL.items() if each.why]
AT_ITS_OWN_ARRIVAL = [name for name, each in BY_LABEL.items() if not each.why]


# ---- TIER 1 ----------------------------------------------------------------------------------------------------------------------
@EVERY_CASE
def test_a_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE: the C core held to the ROM's routine from the same entry — the row's companion or the plain
    differential; the answer at the declared width. No case idles: no routine of the unit waits."""
    each = BY_LABEL[name]
    _answer, _rom_d0, idles = w.ran(each, each.name in v.YIELDS_L)
    assert not idles, f"{name}: the ROM's run idles {idles} time(s)"


TALL_CELL = 16                          # gl_hchar of a high-resolution machine's 8 x 16 cell


def test_win_view_of_the_text_view_takes_the_cell_s_height__a_labelled_staging():
    """A LABELLED STAGING — gl_hchar LAID 16 (every machine of the hands is 320 x 200, its cell 8 by 8: a text item's
    height read from the cell's width or its height is the same there): win_view at its text arrival, the item's
    height gl_hchar's — reviewer A's RA-L5, the width read for it, is told apart."""
    each = Case("AES_ROM_WIN_VIEW", AS_TEXT, arm=lambda a: a[0] == 1)
    pokes, arguments = w.machine_of(each)
    w.plain(each.name, arguments, case.merge_pokes(pokes, {aes.AES_GL_HCHAR: struct.pack(">H", TALL_CELL)}))


ARRIVALS, CLASSES = 48, 3


def test_every_routine_has_a_case_at_an_arrival_of_its_own():
    """Seventeen routines, each with a case at its own arrival; the classes by routine."""
    assert {BY_LABEL[name].name for name in AT_ITS_OWN_ARRIVAL} == set(v.UNIT_L) and len(v.UNIT_L) == 17
    assert {BY_LABEL[name].name for name in A_CLASS} == {"AES_ROM_WIN_VIEW", "AES_ROM_WIN_FIND", "AES_ROM_WIN_BLDVIEW"}
    assert (len(AT_ITS_OWN_ARRIVAL), len(A_CLASS)) == (ARRIVALS, CLASSES)
    assert set(UNPINNED) <= set(v.UNIT_L)


VIEW = layouts.parse_constants((aes.INCLUDE / "desk" / "deskview.h", aes.INCLUDE / "desk" / "deskfpd.h"), known=aes.CONSTANTS)


def _arrival_of(routine, chain, nth=1):
    return w.arrival_of(next(each for each in CASES if (each.name, each.chain, each.nth, each.why) == (routine, chain, nth, None)))


def test_the_arrivals_chosen_for_an_arm_are_the_machines_that_make_it():
    """WHAT AN `arm` OF THE ARGUMENTS ALONE CANNOT SAY, read off the arrival's machine: win_icalc's New Folder arrival
    is handed THE FOLDER's FNODE (F_SUBDIR: the folders' ANODEs searched); win_ocalc's arrival on the window scrolled
    a column right and made full holds a scroll it must pull back (W_CVCOL 1 of four columns, all four now fitting);
    its arrival on the window scrolled and SORTED keeps the scroll (three columns fit beside it): the first file shown
    is the second."""
    folder = _arrival_of("AES_ROM_WIN_ICALC", NEW_FOLDER)
    assert folder.boot.ram[folder.arguments[0] + VIEW["FNODE_ATTR"]] & VIEW["FNODE_ATTR_SUBDIR"]
    scrolled = _arrival_of("AES_ROM_WIN_OCALC", SCROLLED_RIGHT)
    window, fit = scrolled.arguments[0], scrolled.arguments[1]
    columns, scroll = (case.word_in(scrolled.boot.ram, window + VIEW[field]) for field in ("WNODE_VNCOL", "WNODE_CVCOL"))
    assert scroll == 1 and fit > columns - scroll
    kept = _arrival_of("AES_ROM_WIN_OCALC", SORTED_SCROLLED)
    window, fit = kept.arguments[0], kept.arguments[1]
    columns, scroll = (case.word_in(kept.boot.ram, window + VIEW[field]) for field in ("WNODE_VNCOL", "WNODE_CVCOL"))
    assert scroll == 1 and fit <= columns - scroll, "the sorted view's scroll is kept: its first file shown is the second"


# ---- D0 AT RETURN -----------------------------------------------------------------------------------------------------------------
VOID_IN_C = frozenset(name for name, (restype, _frame) in v.SIGNATURES.items() if restype is None)
# ...the one that leaves its CALLER's D0: it stores none of its own (win_sname's copy runs through A3 and A4).
NO_ANSWER_OF_ITS_OWN = ("AES_ROM_WIN_SNAME",)


def test_the_void_routines_are_gem_s_void_ones_and_no_rom_caller_reads_what_they_leave():
    """THE NAMED DIVERGENCE: ten routines are `void` in C where the ROM leaves a word — and BY READING EVERY CALLER
    (`answer_readers`), no instruction of the ROM's reads it."""
    assert VOID_IN_C == {"AES_ROM_WIN_VIEW", "AES_ROM_WIN_START", "AES_ROM_WIN_FREE", "AES_ROM_WIN_TOP", "AES_ROM_WIN_OCALC",
                         "AES_ROM_WIN_ICALC", "AES_ROM_WIN_BLDVIEW", "AES_ROM_WIN_SHWALL", "AES_ROM_WIN_SINFO", "AES_ROM_WIN_SNAME"}
    for name in VOID_IN_C:
        assert db.calls_of(getattr(addrs, name)), f"{name}: nothing calls it — no reader to find"
        assert not db.answer_readers(getattr(addrs, name)), f"{name}: a ROM caller reads what it leaves in D0"


READ_AT = {"AES_ROM_WIN_ALLOC": 2, "AES_ROM_WIN_FIND": 16, "AES_ROM_WIN_ONTOP": 7, "AES_ROM_WIN_CNT": 1, "AES_ROM_WIN_ITH": 3,
           "AES_ROM_WIN_ISEL": 5, "AES_ROM_WIN_INAME": 2}


def test_the_answers_the_c_has_are_read_where_the_reading_says():
    """...and the seven that answer are each read: the count of reading instructions."""
    read = {name: len(db.answer_readers(getattr(addrs, name))) for name in v.UNIT_L if name not in VOID_IN_C}
    assert {name: sites for name, sites in read.items() if sites} == READ_AT


@pytest.mark.parametrize("name", [name for name in AT_ITS_OWN_ARRIVAL
                                  if not BY_LABEL[name].traps and BY_LABEL[name].name not in NO_ANSWER_OF_ITS_OWN])
def test_the_rom_s_routine_in_place_leaves_the_d0_its_harness_run_does(name):
    """THE HARNESS-STACK RUN IS THE MACHINE'S OWN, as far as D0: the ROM's routine run IN PLACE from the arrival leaves
    the D0 the case's ROM run leaves — the whole register for a pointer, its word otherwise."""
    each = BY_LABEL[name]
    _answer, rom_d0, _idles = w.ran(each, each.name in v.YIELDS_L)
    in_place = w.in_place(each.name, each.chain, each.nth).returned.registers["d0"]
    mask = aes.LONG_MASK if v.SIGNATURES[each.name][0] is aes.LONG_ANSWER else aes.WORD_MASK
    assert in_place & mask == rom_d0 & mask


def test_the_answers_that_are_not_the_rom_s_are_counted_by_name():
    """THE COUNT, over the battery's cases: how many answer nothing in C where the ROM leaves a word."""
    assert Counter(BY_LABEL[name].name in VOID_IN_C for name in BY_LABEL)[True] == 33


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------------
def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_one(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`, one for every unit of the desk): every core of the unit
    linked; and no function outside the unbound desk (the held cores and what only they reach) refers to ANY held core."""
    assert not db.bound_referrers(blob, v.UNIT_L)


def test_the_table_s_entries_stay_the_rom_s_and_no_registry_names_one():
    """...the generator's verdict for each of unit L's is THE ROM'S, and no registered row is one of theirs."""
    assert w.verdicts_not_the_rom_s(v.UNIT_L) == (set(), [])


# ==== BAND 6 WAVE 2 (group G3): THE UNIT'S LAST FIVE — the scrolls and the windows' rebuilds ===========================
# Held as wave 1b's seventeen are, over their own case list: wave 1b's counts above stay theirs. The scroll chains are
# G3's (`aes_desk.py`'s wave-2 block): the arrows themselves, the bar's pages, the slider dragged, the window sized.
RIGHT_PAGE, DOWN_SLIDER = "files: the window's right arrow clicked", "files: the window's down arrow clicked"
LEFT_LINE = "files: the right arrow clicked, then the left arrow clicked"
LEFT_PAGE = "files: the right arrow clicked, then the horizontal bar left of its slider (a page)"
RIGHT_LINE = "files: the window's right arrow gadget itself clicked (a column)"
DOWN_LINE, UP_LINE = "files: the window's down arrow gadget itself clicked (a row)", "files: the window's up arrow gadget clicked (a row)"
SLID_RIGHT = "files: the window's horizontal slider dragged right"
NARROW_PAGE = "files: the window sized smaller, then its right arrow clicked"
VIEW_TEXT, SORT_DATE = "files: View > Show as Text", "files: View > Sort by Date"
FIFTH_DOWN = "files: a fifth entry, then the down arrow gadget clicked (a row)"     # (the fix pass's: a second row)
WA_UPPAGE, WA_DNPAGE = 0, 1             # win_arrow's two words no chain clicks (`desk/deskview.h`)
A_LOW_PLACE = 300                       # win_slide's place, in thousandths: under the half of the one column hidden


def _arrow(word):
    return lambda a: (a.arguments[0], word)


CASES_WAVE_2 = (
    Case("AES_ROM_WIN_BLT", DOWN_SLIDER, arm=lambda a: a[1:] == (1, 0)),           # (no step: done)
    Case("AES_ROM_WIN_BLT", RIGHT_PAGE, arm=lambda a: a[1:] == (0, 3)),            # (a column right: blitted left)
    Case("AES_ROM_WIN_BLT", LEFT_LINE, arm=lambda a: a[1:] == (0, 0)),             # (a column left: blitted right)
    Case("AES_ROM_WIN_BLT", LEFT_PAGE, arm=lambda a: a[1] == 0 and aes.signed(a[2]) < 0),   # (a first column below 0)
    Case("AES_ROM_WIN_BLT", NARROW_PAGE, arm=lambda a: a[1:] == (0, 2)),           # (a step of what is shown: redrawn whole)
    Case("AES_ROM_WIN_SLIDE", DOWN_SLIDER), Case("AES_ROM_WIN_SLIDE", SLID_RIGHT, arm=lambda a: a[2] == 0),
    Case("AES_ROM_WIN_SLIDE", SLID_RIGHT, arguments=lambda a: (a.arguments[0], A_LOW_PLACE, a.arguments[2]),
         why="a place of 300 thousandths (the drag's own, 690, is past the half its one hidden column rounds to: no "
             "other place told apart): the first column 0, not 1"),
    Case("AES_ROM_WIN_ARROW", LEFT_PAGE), Case("AES_ROM_WIN_ARROW", RIGHT_PAGE), Case("AES_ROM_WIN_ARROW", LEFT_LINE),
    Case("AES_ROM_WIN_ARROW", RIGHT_LINE), Case("AES_ROM_WIN_ARROW", DOWN_LINE), Case("AES_ROM_WIN_ARROW", UP_LINE),
    # (the fix pass's) a fifth entry in the files window — a second row — and its down arrow: the vertical arms
    # (win_arrow's rows, win_blt's vertical no-step return: both rows shown)
    Case("AES_ROM_WIN_ARROW", FIFTH_DOWN), Case("AES_ROM_WIN_BLT", FIFTH_DOWN),
    Case("AES_ROM_WIN_ARROW", FIFTH_DOWN, arguments=_arrow(WA_UPPAGE),
         why="a page up over the window of two rows: both shown, its vertical slider fills its bar — no page to click"),
    Case("AES_ROM_WIN_ARROW", FIFTH_DOWN, arguments=_arrow(WA_DNPAGE),
         why="a page down over the window of two rows: both shown, its vertical slider fills its bar — no page to click"),
    Case("AES_ROM_WIN_SRTALL", AS_TEXT), Case("AES_ROM_WIN_SRTALL", SORT_DATE), Case("AES_ROM_WIN_SRTALL", "files: View > Sort by Type"),
    Case("AES_ROM_WIN_BDALL", AS_TEXT), Case("AES_ROM_WIN_BDALL", SORT_DATE), Case("AES_ROM_WIN_BDALL", VIEW_TEXT),
    Case("AES_ROM_WIN_BDALL", "two windows: View > Show as Text"),          # (the fix pass's: a second WNODE rebuilt)
)
# EVERY CASE IS A ROW (`aes_deskwin.row`), even where its run reaches no binding (a step of none: win_blt done
# before its wind_get; win_srtall's sort alone): the kit's plain differential would also make its ATTRIBUTION PASS —
# every byte the ROM stored laid inverted — and win_blt stores the scroll word it read (`add.w d6,14(a5)`, d6 0)
# and win_srtall each list head it sorted, so that pass runs both over a machine no run makes (a scroll the step is
# not 0 from; a list head off the bus) — the C to the dispatcher, the ROM's sort into the ROM window.
UNPINNED_WAVE_2 = {
    "AES_ROM_WIN_BLT": "a VERTICAL blit (rows kept, the uncovered strip below or above): the fix pass's fifth entry gives a "
                       "second row, but both rows are shown — a row-blit needs more rows than shown (nine entries at four "
                       "columns, or a shorter window), not tried; and a work area not wholly below the menu bar (rc_equal "
                       "false: a window pushed off the screen's edge)",
    "AES_ROM_WIN_ARROW": "an arrow word past WA_RTLINE: the ROM scrolls to its caller's D6, a value the C does not have — "
                         "refused by name (the AES's window manager sends 0..7)",
}
BY_LABEL_WAVE_2 = {w.label(each): each for each in CASES_WAVE_2}
assert len(BY_LABEL_WAVE_2) == len(CASES_WAVE_2), "two cases of one name"
A_CLASS_WAVE_2 = [name for name, each in BY_LABEL_WAVE_2.items() if each.why]
AT_ITS_OWN_ARRIVAL_WAVE_2 = [name for name, each in BY_LABEL_WAVE_2.items() if not each.why]


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_from_its_arrival_is_the_rom_s(name):
    """THE CASE, as wave 1b's: the C core held to the ROM's routine from the same entry; no case idles."""
    each = BY_LABEL_WAVE_2[name]
    _answer, _rom_d0, idles = w.ran(each, True)
    assert not idles, f"{name}: the ROM's run idles {idles} time(s)"


ARRIVALS_WAVE_2, CLASSES_WAVE_2 = 22, 3


def test_every_wave_2_routine_has_a_case_at_an_arrival_of_its_own():
    """The five, each with a case at its own arrival; win_arrow's two pages and win_slide's low place the classes."""
    assert {BY_LABEL_WAVE_2[name].name for name in AT_ITS_OWN_ARRIVAL_WAVE_2} == set(v.UNIT_L_WAVE_2)
    assert {BY_LABEL_WAVE_2[name].name for name in A_CLASS_WAVE_2} == {"AES_ROM_WIN_ARROW", "AES_ROM_WIN_SLIDE"}
    assert (len(AT_ITS_OWN_ARRIVAL_WAVE_2), len(A_CLASS_WAVE_2)) == (ARRIVALS_WAVE_2, CLASSES_WAVE_2)
    assert set(UNPINNED_WAVE_2) <= set(v.UNIT_L_WAVE_2)


def test_win_arrow_s_arrivals_and_classes_take_every_arrow_word():
    """Every one of the eight WA_* words is a case: six at arrivals of their own, the two pages as classes."""
    words = {w.arrival_of(each).arguments[1] for each in CASES_WAVE_2 if each.name == "AES_ROM_WIN_ARROW"}
    assert words == set(range(8))


def test_the_wave_2_routines_are_gem_s_void_ones_and_no_rom_caller_reads_what_they_leave():
    """THE NAMED DIVERGENCE: the five are `void` in C (win_blt's no-step arm leaves 0 — `clr.w d0` — every other the
    last callee's word) — and no instruction of the ROM's reads what they leave."""
    assert all(restype is None for restype, _frame in v.SIGNATURES_WAVE_2.values())
    for name in v.UNIT_L_WAVE_2:
        assert db.calls_of(getattr(addrs, name)), f"{name}: nothing calls it — no reader to find"
        assert not db.answer_readers(getattr(addrs, name)), f"{name}: a ROM caller reads what it leaves in D0"


def test_the_wave_2_answers_that_are_not_the_rom_s_are_counted_by_name():
    assert len(BY_LABEL_WAVE_2) == 25


def test_no_function_of_a_blob_outside_the_unbound_desk_refers_to_a_wave_2_one(blob):
    """THE UNBOUND PIN (`aes_deskbind.bound_referrers`), asked of unit L's wave-2 five."""
    assert not db.bound_referrers(blob, v.UNIT_L_WAVE_2)


def test_the_wave_2_table_s_entries_stay_the_rom_s_and_no_registry_names_one():
    assert w.verdicts_not_the_rom_s(v.UNIT_L_WAVE_2) == (set(), [])
