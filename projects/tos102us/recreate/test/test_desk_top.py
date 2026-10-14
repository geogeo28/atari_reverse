"""UNIT K, THE DESK'S MAIN LOOP'S HELPERS (`src/desk/desktop.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE
ARRIVALS OF ROM RUNS — LINKED, AND NOTHING BOUND.

  * EVERY CASE IS AN ARRIVAL (`aes_deskapp.arrival`) and A ROW THAT SWITCHES: each routine's menu changes go through
    unit D's bindings, which yield — the C through the host's scheduler held to the ROM's scheduled run, nothing
    dropped (`aes_switching.companion`).
  * D0 AT RETURN: men_list answers nothing in C — the word the ROM leaves (its last binding's) is a COUNTED divergence,
    READ BY NO CALLER (`aes_deskbind.answer_readers`).
"""
import pytest

import aes
import aes_boot
import aes_desk
import aes_deskapp as da
import aes_deskbind as db
import aes_desktop  # noqa: F401  (the unit's signatures, declared)
import case

BOOT = da.THE_BOOT
MEN_LIST, MEN_UPDATE, I_FIND = "AES_ROM_MEN_LIST", "AES_ROM_MEN_UPDATE", "AES_ROM_I_FIND"
DO_VIEWMENU, CNX_PUT = "AES_ROM_DO_VIEWMENU", "AES_ROM_CNX_PUT"
# ---- THE ARRIVALS: `{routine: ((chain, how many of its arrivals), ...)}` ----------------------------------------------------------
ARRIVALS = {
    MEN_LIST: ((BOOT, 1), ("Desk > Desktop Info, Return", 3), ("drive A: selected", 3), ("file: selected", 4), ("A: opened", 8)),
    # (...and TWO ICONS SELECTED at once, drive B: and the trash boxed: the many-selected list — the fix pass's chain)
    MEN_UPDATE: ((BOOT, 1), ("Desk > Desktop Info, Return", 1), ("drive A: selected", 1),
                 ("a rubber box on the desktop, round drive B: and the trash", 1)),
    # (the sort items by date and by type — group G3's chains — and Show as Icons over a window in icons: the fix pass's)
    DO_VIEWMENU: ((BOOT, 1), ("window: View > Show as Text", 1), ("window: View > Sort by Size", 1),
                  ("files: View > Sort by Date", 1), ("files: View > Sort by Type", 1),
                  ("window: View > Show as Icons (the view it has)", 1)),
    # (...and Save Desktop WITH A WINDOW OPEN: the per-window entry — wind_get, do_xyfix, the scroll, the icon, the path —
    # and with its view scrolled a column right, so that the scroll's column and row are told apart)
    CNX_PUT: ((BOOT, 1), ("Options > Save Desktop, Return", 1), ("window: its closer clicked", 1),
              ("window: Options > Save Desktop, Return", 1), ("files: the right arrow clicked, then Options > Save Desktop, Return", 1)),
}
AT_ARRIVALS = [(routine, chain, nth) for routine, takes in ARRIVALS.items() for chain, count in takes for nth in range(count)]


@pytest.mark.parametrize("routine, chain, nth", AT_ARRIVALS,
                         ids=[f"{routine[len('AES_ROM_'):].lower()} — arrival {nth} of {chain}" for routine, chain, nth in AT_ARRIVALS])
def test_a_routine_at_its_arrival_is_the_rom_s_through_its_bindings_yields(routine, chain, nth):
    """THE CASE: the row that switches over the arrival's megabyte — every menu_ienable's yield taken through the
    dispatcher on both shores, the image held at each, no idle (nothing waits)."""
    arrived = da.arrival(routine, chain, nth)
    the_rom_s = da.the_rom_s_run(da.row_of(arrived))
    da.held(da.row_of(arrived))
    assert not the_rom_s.idles


def test_men_list_s_arrivals_enable_and_disable():
    """The arrivals' lists (the ROM's byte tables at $fef64a..) are both ENABLED (1: a file selected, a window opened)
    and DISABLED (0) — and every item of them is under $80: the signed byte's redraw is no arrival's."""
    enables = {da.arrival(MEN_LIST, chain, nth).arguments[2] for chain, count in ARRIVALS[MEN_LIST] for nth in range(count)}
    assert enables == {0, 1}


def test_no_caller_in_the_rom_reads_what_men_list_leaves_in_d0():
    """BY READING EVERY CALL SITE: the word the ROM's men_list leaves (its last binding's 1 at every arrival) is read by
    nothing — the counted divergence of the case where the C answers nothing."""
    assert db.calls_of(da.entry_of(MEN_LIST))
    assert not db.answer_readers(da.entry_of(MEN_LIST))
    assert sum(count for _chain, count in ARRIVALS[MEN_LIST]) == 19


# men_list's SIGNED BYTE (no table of the ROM's has an item of $80 or more): a list LAID in the group's band.
LIST_AT = da.BAND_AT + da.BAND_BYTES - 0x10
HIGH_ITEM_LIST = bytes((0x92, 0x00))
assert da.GEMDOS.end <= LIST_AT


def test_men_list_of_an_item_of_92_hex_asks_the_bar_redrawn__an_argument_class():
    """A LABELLED ARGUMENT CLASS — THE LIST LAID in the group's band: the item $92, a signed byte, is the word $ff92 —
    its top bit the binding's redraw, the rest an object far past the menu's own (the ROM's do_chg reaches it as the
    C does). Over "file: selected"'s third arrival, enable 1."""
    arrived = da.arrival(MEN_LIST, "file: selected", 2)
    laid = da.with_arguments(arrived, arrived.arguments[0], LIST_AT, 1)
    row = da.row_of(laid, label="men_list — the list $92 LAID __an_argument_class", layers=({LIST_AT: HIGH_ITEM_LIST},))
    da.held(row)



# ---- men_update where a window is on top: G1's win_ontop TRAPS (Dsetdrv, Dsetpath) ------------------------------------------
WINDOW_ON_TOP_TRAPS = 4


@pytest.mark.parametrize("chain", ("file: selected", "files: the program selected, File > Show Info, Return"),
                         ids=[f"men_update — arrival 0 of {chain} — {da.SCRIPTED}" for chain in
                              ("file: selected", "files: the program selected, File > Show Info, Return")])
def test_men_update_with_a_file_selected_in_a_window_is_the_rom_s__scripted(chain):
    """men_update where a FILE is selected in a window on top — a document ("file: selected") and A PROGRAM (the
    files machine's, its ANODE's is_app 1: the program's list): i_find of a window's item, the file's list, the window
    items enabled — and win_ontop's four GEMDOS calls answered by band 5's recording trap SCRIPTED WITH THE ROM'S OWN
    RUN'S ANSWERS (its child binds the twins)."""
    arrived = da.arrival(MEN_UPDATE, chain)
    answers, _back = da.dos_answers_in_place(arrived, WINDOW_ON_TOP_TRAPS)
    da.held(da.scripted_row(arrived, answers))


# ---- i_find: a plain routine (no binding under it) ------------------------------------------------------------------------
I_FIND_ARRIVALS = (("drive A: selected", 0), ("file: selected", 0), ("A: File > Open", 0))


@pytest.mark.parametrize("chain, nth", I_FIND_ARRIVALS, ids=[f"i_find — arrival {nth} of {chain}" for chain, nth in I_FIND_ARRIVALS])
def test_i_find_at_its_arrival_is_the_rom_s(chain, nth):
    """i_find on the desktop (drive A:'s icon) and in a window (the file's): the ANODE the ROM's run answers, the FNODE
    stored through its pointer, app_afind's is-a-program; the run in place leaves the same longword."""
    arrived = da.arrival(I_FIND, chain, nth)
    result = da.plain(arrived, poison=False)
    assert result.long_answer() == da.returned_in_place(arrived).registers["d0"]


def test_i_find_s_arrivals_take_both_arms():
    assert {da.arrival(I_FIND, chain, nth).arguments[0] == 0 for chain, nth in I_FIND_ARRIVALS} == {True, False}


PAST_THE_VIEW_MENU = 36                 # the ROM's switch `$fef6c4` covers the View menu's items 29..35


def test_do_viewmenu_of_an_item_past_the_menu_s__an_argument_class():
    """A LABELLED ARGUMENT CLASS over "window: View > Sort by Size"'s arrival — an item outside the View menu's table
    (36), which no menu hands it: nothing moved. (Show as Icons, Sort by Date and Sort by Type are arrivals above.)"""
    arrived = da.arrival(DO_VIEWMENU, "window: View > Sort by Size")
    da.held(da.row_of(da.with_arguments(arrived, PAST_THE_VIEW_MENU),
                      label="do_viewmenu an item past the menu's (36): nothing __an_argument_class"))


def test_the_new_arrivals_take_the_arms_they_were_added_for():
    """READ OFF THE ARRIVALS: do_viewmenu's items 33, 35 and 29 (over a window in icons already); men_update with two
    icons selected; cnx_put with a window open (the desk's open count 1)."""
    items = {da.arrival(DO_VIEWMENU, chain).arguments[0] for chain in
             ("files: View > Sort by Date", "files: View > Sort by Type", "window: View > Show as Icons (the view it has)")}
    assert items == {33, 35, 29}
    boxed = aes_boot.Machine(da.arrival(MEN_UPDATE, "a rubber box on the desktop, round drive B: and the trash").boot)
    assert (aes_desk.drive_is_selected(boxed, "B"), aes_desk.icon_is_selected(boxed, aes_desk.THE_TRASH),
            aes_desk.drive_is_selected(boxed, "A")) == (True, True, False)
    ram = da.arrival(CNX_PUT, "window: Options > Save Desktop, Return").boot.ram
    assert case.word_in(ram, (case.long_in(ram, aes.AES_DESK_GLOBALS) & da.BUS) + da.CONSTANTS["DESK_G_WINDOWS_OPEN"]) == 1


def test_no_caller_reads_what_men_update_or_cnx_put_leave_in_d0():
    """men_update's and cnx_put's D0 (their last binding's leftover) read by nothing: counted divergences."""
    for routine in (MEN_UPDATE, CNX_PUT):
        assert db.calls_of(da.entry_of(routine)) and not db.answer_readers(da.entry_of(routine))
