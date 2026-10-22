"""UNIT K, THE DESK'S MAIN LOOP'S HELPERS (`src/desk/desktop.c`; band 6 wave 1b, group G2): HELD AT TIER 1 AT THE
ARRIVALS OF ROM RUNS — AND, SINCE BAND 6 SLICE F2, FLIPPED (i_find since slice F2b; men_update, held there by a measured
reason, since slice F2c): the Line-F table's entry for each is its thunk, and every case of theirs at an arrival is a
Tier 3 row (`ROWS`) but men_update's boot arrival (`NOT_A_ROW`).

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
import aes_desktop
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


# ---- band 6 slice F2 (group G2): THE UNIT'S ROWS — every case at an arrival of a flipped routine (men_list, do_viewmenu,
# cnx_put) a row that switches with NO DOOR (`aes_deskapp.register_switching`; MEASURED, the table's second count: none
# makes a call of the event layer's door); the classes stay Tier 1's (i_find's rows: slice F2b's, below; men_update's:
# slice F2c's). Their pins — DATA, measured
# by the table's own measurement and each blob's second differential from the rows as registered; re-pinned from a
# recorded run, never by hand.
FLIPPED = tuple(name for name in aes_desktop.UNIT_K if name not in aes_desktop.HELD_AT_F2)
# ...BUT A PLAIN ROW where the ROM's run reaches no binding that yields (MEASURED: its dispatcher entered no process) —
# cnx_put with no window open, do_viewmenu asked the view the window already has; a plain row's run is refused by name
# where it reaches the dispatcher.
NO_SWITCH = frozenset({(CNX_PUT, BOOT), (CNX_PUT, "Options > Save Desktop, Return"), (CNX_PUT, "window: its closer clicked"),
                       (DO_VIEWMENU, BOOT), (DO_VIEWMENU, "window: View > Show as Icons (the view it has)")})


def _registered(routine, chain, nth):
    arrived = da.arrival(routine, chain, nth)
    if (routine, chain) in NO_SWITCH:
        return da.register_plain(arrived)
    return da.register_switching(arrived, door_user=False)


# men_update's BOOT ARRIVAL: NOT A ROW, by name — its machine's screen manager stands where no history of ours is known
# to leave it (the takeover refuses it by name: menu_ienable's own boot arrival's class, `test_desk_bind.NOT_A_ROW`).
NOT_A_ROW = {(MEN_UPDATE, BOOT, 0): "the boot's screen manager stands where no history of ours reaches (`aes_takeover`)"}
ROWS = {f"{routine} {chain} {nth}": _registered(routine, chain, nth) for routine, chain, nth in AT_ARRIVALS
        if routine in FLIPPED and (routine, chain, nth) not in NOT_A_ROW}
# ---- band 6 slice F2b: i_find FLIPPED — its three arrivals PLAIN ROWS (no binding under it). (men_update, held at F2b,
# FLIPPED at slice F2c: its rows are `ROWS`' above, rows that switch with no door.)
ROWS.update({f"{I_FIND} {chain} {nth}": da.register_plain(da.arrival(I_FIND, chain, nth)) for chain, nth in I_FIND_ARRIVALS})
NO_DOOR_PREMISES = {
    "aes_cnx_put, arrival 0 of files: the right arrow clicked, then Options > Save Desktop, Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_cnx_put, arrival 0 of window: Options > Save Desktop, Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Date":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0, ()),
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Type":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0, ()),
    "aes_do_viewmenu, arrival 0 of window: View > Show as Text":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0, ()),
    "aes_do_viewmenu, arrival 0 of window: View > Sort by Size":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), 0, ()),
    "aes_men_list, arrival 0 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 1 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 2 of A: opened":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_men_list, arrival 3 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 4 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 5 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 6 of A: opened":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_men_list, arrival 7 of A: opened":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 0 of Desk > Desktop Info, Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 1 of Desk > Desktop Info, Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 2 of Desk > Desktop Info, Return":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 0 of drive A: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 1 of drive A: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 2 of drive A: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 0 of file: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 1 of file: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 2 of file: selected":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    "aes_men_list, arrival 3 of file: selected":
        ((), 0, 0xae5e, (0xae5e,), None, ()),
    "aes_men_list, arrival 0 of the boot of the DESKTOP.INF machine":
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_men_update, arrival 0 of Desk > Desktop Info, Return':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_men_update, arrival 0 of drive A: selected':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
    'aes_men_update, arrival 0 of a rubber box on the desktop, round drive B: and the trash':
        ((), 0, 0xae5e, (0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e, 0xae5e), None, ()),
}
NO_DOOR_PRICED = {
    "aes_cnx_put, arrival 0 of files: the right arrow clicked, then Options > Save Desktop, Return":
        ((13666, 22582), None, None, (0, 0, 0)),
    "aes_cnx_put, arrival 0 of window: Options > Save Desktop, Return":
        ((13666, 22582), None, None, (0, 0, 0)),
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Date":
        ((12302, 17504), None, None, (0, 0, 0)),
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Type":
        ((12336, 17504), None, None, (0, 0, 0)),
    "aes_do_viewmenu, arrival 0 of window: View > Show as Text":
        ((12426, 17606), None, None, (0, 0, 0)),
    "aes_do_viewmenu, arrival 0 of window: View > Sort by Size":
        ((12332, 17504), None, None, (0, 0, 0)),
    "aes_men_list, arrival 0 of A: opened":
        ((22596, 32602), None, None, (0, 0, 0)),
    "aes_men_list, arrival 1 of A: opened":
        ((49108, 71652), None, None, (0, 0, 0)),
    "aes_men_list, arrival 2 of A: opened":
        ((5652, 8276), None, None, (0, 0, 0)),
    "aes_men_list, arrival 3 of A: opened":
        ((28190, 40664), None, None, (0, 0, 0)),
    "aes_men_list, arrival 4 of A: opened":
        ((22596, 32602), None, None, (0, 0, 0)),
    "aes_men_list, arrival 5 of A: opened":
        ((49108, 71652), None, None, (0, 0, 0)),
    "aes_men_list, arrival 6 of A: opened":
        ((5652, 8276), None, None, (0, 0, 0)),
    "aes_men_list, arrival 7 of A: opened":
        ((28190, 40664), None, None, (0, 0, 0)),
    "aes_men_list, arrival 0 of Desk > Desktop Info, Return":
        ((22596, 32602), None, None, (0, 0, 0)),
    "aes_men_list, arrival 1 of Desk > Desktop Info, Return":
        ((17002, 24540), None, None, (0, 0, 0)),
    "aes_men_list, arrival 2 of Desk > Desktop Info, Return":
        ((28190, 40664), None, None, (0, 0, 0)),
    "aes_men_list, arrival 0 of drive A: selected":
        ((22596, 32602), None, None, (0, 0, 0)),
    "aes_men_list, arrival 1 of drive A: selected":
        ((11408, 16478), None, None, (0, 0, 0)),
    "aes_men_list, arrival 2 of drive A: selected":
        ((17002, 24540), None, None, (0, 0, 0)),
    "aes_men_list, arrival 0 of file: selected":
        ((22596, 32602), None, None, (0, 0, 0)),
    "aes_men_list, arrival 1 of file: selected":
        ((17002, 24540), None, None, (0, 0, 0)),
    "aes_men_list, arrival 2 of file: selected":
        ((49108, 71652), None, None, (0, 0, 0)),
    "aes_men_list, arrival 3 of file: selected":
        ((5652, 8276), None, None, (0, 0, 0)),
    "aes_men_list, arrival 0 of the boot of the DESKTOP.INF machine":
        ((22596, 32602), None, None, (0, 0, 0)),
    'aes_men_update, arrival 0 of Desk > Desktop Info, Return':
        ((196108, 285288), None, None, (0, 0, 0)),
    'aes_men_update, arrival 0 of drive A: selected':
        ((180858, 264318), None, None, (0, 0, 0)),
    'aes_men_update, arrival 0 of a rubber box on the desktop, round drive B: and the trash':
        ((237424, 348214), None, None, (0, 0, 0)),
}
NO_DOOR_WHOLE_RUN = {
    "aes_cnx_put, arrival 0 of files: the right arrow clicked, then Options > Save Desktop, Return":
        {"bench": (36106, 27818), "bench_shipped": (36106, 28094)},
    "aes_cnx_put, arrival 0 of window: Options > Save Desktop, Return":
        {"bench": (36106, 27818), "bench_shipped": (36106, 28094)},
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Date":
        {"bench": (31028, 26138), "bench_shipped": (31028, 26378)},
    "aes_do_viewmenu, arrival 0 of files: View > Sort by Type":
        {"bench": (31028, 26172), "bench_shipped": (31028, 26412)},
    "aes_do_viewmenu, arrival 0 of window: View > Show as Text":
        {"bench": (31130, 26262), "bench_shipped": (31130, 26502)},
    "aes_do_viewmenu, arrival 0 of window: View > Sort by Size":
        {"bench": (31028, 26168), "bench_shipped": (31028, 26408)},
    "aes_men_list, arrival 0 of A: opened":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    "aes_men_list, arrival 1 of A: opened":
        {"bench": (132510, 111370), "bench_shipped": (132510, 112450)},
    "aes_men_list, arrival 2 of A: opened":
        {"bench": (15038, 12570), "bench_shipped": (15038, 12690)},
    "aes_men_list, arrival 3 of A: opened":
        {"bench": (74474, 62780), "bench_shipped": (74474, 63380)},
    "aes_men_list, arrival 4 of A: opened":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    "aes_men_list, arrival 5 of A: opened":
        {"bench": (132510, 111370), "bench_shipped": (132510, 112450)},
    "aes_men_list, arrival 6 of A: opened":
        {"bench": (15038, 12570), "bench_shipped": (15038, 12690)},
    "aes_men_list, arrival 7 of A: opened":
        {"bench": (74474, 62780), "bench_shipped": (74474, 63380)},
    "aes_men_list, arrival 0 of Desk > Desktop Info, Return":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    "aes_men_list, arrival 1 of Desk > Desktop Info, Return":
        {"bench": (44826, 37756), "bench_shipped": (44826, 38116)},
    "aes_men_list, arrival 2 of Desk > Desktop Info, Return":
        {"bench": (74474, 62780), "bench_shipped": (74474, 63380)},
    "aes_men_list, arrival 0 of drive A: selected":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    "aes_men_list, arrival 1 of drive A: selected":
        {"bench": (30002, 25244), "bench_shipped": (30002, 25484)},
    "aes_men_list, arrival 2 of drive A: selected":
        {"bench": (44826, 37756), "bench_shipped": (44826, 38116)},
    "aes_men_list, arrival 0 of file: selected":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    "aes_men_list, arrival 1 of file: selected":
        {"bench": (44826, 37756), "bench_shipped": (44826, 38116)},
    "aes_men_list, arrival 2 of file: selected":
        {"bench": (132510, 111370), "bench_shipped": (132510, 112450)},
    "aes_men_list, arrival 3 of file: selected":
        {"bench": (15038, 12570), "bench_shipped": (15038, 12690)},
    "aes_men_list, arrival 0 of the boot of the DESKTOP.INF machine":
        {"bench": (59650, 50268), "bench_shipped": (59650, 50748)},
    'aes_men_update, arrival 0 of Desk > Desktop Info, Return':
        {"bench": (521958, 438238), "bench_shipped": (521958, 442438)},
    'aes_men_update, arrival 0 of drive A: selected':
        {"bench": (480702, 402232), "bench_shipped": (480702, 406074)},
    'aes_men_update, arrival 0 of a rubber box on the desktop, round drive B: and the trash':
        {"bench": (632218, 527976), "bench_shipped": (632218, 533020)},
}


def test_men_update_s_boot_arrival_alone_runs_the_screen_manager_where_no_history_of_ours_leaves_it(blob):
    """`NOT_A_ROW`, MEASURED (slice F2c): of men_update's arrivals only the boot's row runs the screen manager (its
    settled drops name its two spans: `aes_takeover.named_in`) — and the takeover refuses that machine by name, as it
    refuses menu_ienable's own boot arrival (`test_desk_bind.NOT_A_ROW`); every other arrival names no span of it."""
    import aes_switching
    import aes_takeover
    for routine, chain, nth in AT_ARRIVALS:
        if routine != MEN_UPDATE:
            continue
        made = aes_switching.settled(da.switching_row(da.arrival(routine, chain, nth), door_user=False))
        assert aes_takeover.named_in(made.drops) == ((routine, chain, nth) in NOT_A_ROW), chain
        if (routine, chain, nth) in NOT_A_ROW:
            with pytest.raises(aes_takeover.Refused, match="STANDS PARKED WHERE NO HISTORY OF OURS IS KNOWN TO LEAVE IT"):
                aes_takeover.prepared(blob, made.pokes)


def test_every_case_at_an_arrival_of_a_flipped_routine_is_a_row_and_its_pins_are_the_switching_ones():
    import aes_switching
    switching = [row for row in ROWS.values() if hasattr(row, "door")]       # (a plain row is a tuple)
    assert {da.entry_of(name) for name in FLIPPED} == {row[1] if not hasattr(row, "door") else da.entry_of(row.name) for row in ROWS.values()}
    plain = len(NO_SWITCH) + len(I_FIND_ARRIVALS)
    assert (len(ROWS), len(switching)) == (36, 36 - plain) and all(row.door is None for row in switching)
    assert {aes_switching.row_name(row) for row in switching} == set(NO_DOOR_PREMISES) == set(NO_DOOR_PRICED) == set(NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PREMISES)
def test_a_row_has_its_premise_on_the_rom_s_run(name):
    da.vet_the_premise(name, NO_DOOR_PREMISES)


@pytest.mark.parametrize("name", NO_DOOR_WHOLE_RUN)
def test_a_row_is_parked_and_woken_by_our_dispatcher_on_both_blobs(name, blob):
    da.vet_on_a_blob(blob, name, NO_DOOR_PREMISES, NO_DOOR_PRICED, NO_DOOR_WHOLE_RUN)


@pytest.mark.parametrize("name", NO_DOOR_PRICED)
def test_a_row_is_priced_as_pinned_and_under_the_bar(name):
    da.vet_the_price(name, NO_DOOR_PRICED)


# ==== BAND 6 WAVE 2 (group G3): cnx_get `$fe2618` ==================================================================
# The desk restarted after a file is shown (deskmain again): the INF's windows opened again — each through
# do_diropen, which reads its path (pn_active) and makes it current (win_top's pro_chdir): GEMDOS REPLAYED
# (`aes_desksupp.replayed_row`, said in the id), a row that switches.
import aes_desksupp as ds               # noqa: E402 — wave 2's, kept with its section
import aes_desktop as dt                # noqa: E402
import aes_deskwin as w                 # noqa: E402

SHOWN_FILE, SHOWN_LONG = "file: shown, a key at its end", "files: the long file shown, a blank at each page's end and at its end"
ESCAPE, A_KEY = "window: Esc typed (the top window read again)", "a key typed at the desk's idle"
ESC_ASCII_ALONE = 0x001b                # Esc's ASCII byte alone (the scan code 0)
SCROLLED_KEPT, SORT_KEPT = "files: the right arrow clicked, then the long file shown", "files: View > Sort by Size, then the long file shown"
VIEW_KEPT = "files: View > Show as Text, then the long file's line shown"
CASES_WAVE_2 = (w.Case("AES_ROM_CNX_GET", SHOWN_FILE, budget=4_000_000), w.Case("AES_ROM_CNX_GET", SHOWN_LONG, budget=4_000_000),
                # (the fix pass's, restored from G3's) the INF kept a window scrolled a column right; and the sort by
                # size: its view and sort words told apart
                w.Case("AES_ROM_CNX_GET", SCROLLED_KEPT, budget=4_000_000), w.Case("AES_ROM_CNX_GET", SORT_KEPT, budget=4_000_000),
                w.Case("AES_ROM_CNX_GET", VIEW_KEPT, budget=4_000_000),
                # hndl_kbd: Esc with a window on top (fun_rebld: its path read again, GEMDOS replayed), and 'a' (nothing)
                w.Case("AES_ROM_HNDL_KBD", ESCAPE, arm=lambda a: a == (0x011b,)),
                w.Case("AES_ROM_HNDL_KBD", A_KEY, arm=lambda a: a != (0x011b,)),
                # (the fix pass's) a key whose LOW byte is Esc's and whose scan is not: no Esc (the word compared)
                w.Case("AES_ROM_HNDL_KBD", ESCAPE, arguments=lambda a: (ESC_ASCII_ALONE,),
                       why="the key $001b — Esc's ASCII with no scan code: hndl_kbd compares the WORD, nothing done"))
TRAPS_K = {(ESCAPE, "AES_ROM_HNDL_KBD"), *((chain, "AES_ROM_CNX_GET") for chain in (SHOWN_FILE, SHOWN_LONG, SCROLLED_KEPT, SORT_KEPT, VIEW_KEPT))}
BY_LABEL_WAVE_2 = {w.label(each) + (f"; {ds.REPLAYED}" if (each.chain, each.name) in TRAPS_K else ""): each for each in CASES_WAVE_2}


@pytest.mark.parametrize("name", BY_LABEL_WAVE_2)
def test_a_wave_2_routine_at_its_arrival_is_the_rom_s(name):
    """THE CASE: the row over the arrival (GEMDOS replayed where its run traps); no idle — or, where the run reaches no
    binding ('a' at the idle: hndl_kbd returns at once), the kit's plain differential."""
    each = BY_LABEL_WAVE_2[name]
    if (each.chain, each.name) not in TRAPS_K:
        w.ran(each, False)
        return
    the_row = ds.replayed_row(each)
    w.held(the_row)
    assert not w.the_rom_s_run(the_row).idles


def test_hndl_kbd_answers_0_read_by_its_caller():
    """hndl_kbd's word (0 on both arms, compared on every case) is read by its one caller (`answer_readers`)."""
    assert len(db.answer_readers(da.entry_of("AES_ROM_HNDL_KBD"))) == 1


UNPINNED_WAVE_2 = {
    "AES_ROM_CNX_GET": "a kept window win_alloc refuses (four open), and a kept path pro_chdir refuses (the window freed): "
                       "every chain's restart keeps one window of the disk's own path",
}


def test_cnx_get_is_gem_s_void_one_and_no_rom_caller_reads_what_it_leaves():
    """THE NAMED DIVERGENCE: cnx_get is `void` in C (its D0 cnx_put's leftover) — read by no instruction of the ROM."""
    assert db.calls_of(da.entry_of("AES_ROM_CNX_GET")) and not db.answer_readers(da.entry_of("AES_ROM_CNX_GET"))


# ---- FLIPPED (band 6 slice F3, stage 2): cnx_get; hndl_kbd HELD, UNBOUND (stage 3) -----------------------------------------
def test_cnx_get_is_flipped_and_hndl_kbd_held_unbound(blob):
    """THE FLIP PIN of cnx_get (`aes_deskarrive.flipped`) and THE UNBOUND PIN of hndl_kbd (`aes_deskarrive.unbound`: its
    entry the ROM's, no registry row, no function outside the unbound desk refers to a held core) — held to stage 3
    (`aes_desktop.UNIT_K_WAVE_2_HELD_AT_F3`)."""
    import aes_deskarrive as dar
    dar.flipped(blob, dt.UNIT_K_WAVE_2_FLIPPED)
    dar.unbound(blob, dt.UNIT_K_WAVE_2_HELD_AT_F3)


# ---- band 6 slice F3, stage 2: cnx_get's ROWS — every case at an arrival registered as A ROW THAT SWITCHES OVER ITS GEMDOS
# REPLAYED (`aes_desksupp.registered_row`, the replay its Tier 1 case runs, said in the row's name). Each restart opens the
# INF's window anew (do_diropen: its path read, its window drawn) — a run past the default derivation margin
# (440,733–450,410 instructions), so each DECLARES ITS OWN BUDGET, its Tier 1 case's (the user's ruling of 2026-10-21,
# "rows may declare budget"). DOOR USERS, every one (MEASURED, the table's second count: 16 calls of a rebound entry),
# pinned in `DOOR_USERS_*_WAVE_2` and read by `test_tier3.py`.
CNX_GET_AT_ARRIVALS = [name for name, each in BY_LABEL_WAVE_2.items() if each.name == "AES_ROM_CNX_GET"]
ROWS_WAVE_2 = {name: ds.registered_row(BY_LABEL_WAVE_2[name], replayed=True, door_user=True, budget=BY_LABEL_WAVE_2[name].budget)
               for name in CNX_GET_AT_ARRIVALS}
DOOR_USERS_PRICED_WAVE_2 = {
    "aes_cnx_get, arrival 1 of file: shown, a key at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((928818, 1372278), (920080, 1356202), 16, (0, 0, 0)),
    "aes_cnx_get, arrival 1 of files: the long file shown, a blank at each page's end and at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((974844, 1438002), (966106, 1421926), 16, (0, 0, 0)),
    "aes_cnx_get, arrival 1 of files: the right arrow clicked, then the long file shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((966264, 1425218), (957526, 1409142), 16, (0, 0, 0)),
    "aes_cnx_get, arrival 1 of files: View > Sort by Size, then the long file shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((986796, 1455402), (978058, 1439326), 16, (0, 0, 0)),
    "aes_cnx_get, arrival 1 of files: View > Show as Text, then the long file's line shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        ((982864, 1449492), (974126, 1433416), 16, (0, 0, 0)),
}
DOOR_USERS_WHOLE_RUN_WAVE_2 = {
    "aes_cnx_get, arrival 1 of file: shown, a key at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5212378, 4869862), "bench_shipped": (5212378, 4872494)},
    "aes_cnx_get, arrival 1 of files: the long file shown, a blank at each page's end and at its end; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5309940, 4953660), "bench_shipped": (5309940, 4954178)},
    "aes_cnx_get, arrival 1 of files: the right arrow clicked, then the long file shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5290394, 4936888), "bench_shipped": (5290394, 4938192)},
    "aes_cnx_get, arrival 1 of files: View > Sort by Size, then the long file shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5340864, 4979250), "bench_shipped": (5340864, 4979930)},
    "aes_cnx_get, arrival 1 of files: View > Show as Text, then the long file's line shown; GEMDOS REPLAYED: the ROM's run in place's answers and DTAs":
        {"bench": (5344058, 4980236), "bench_shipped": (5344058, 4984854)},
}


def test_every_arrival_of_cnx_get_is_a_door_user_s_row_under_its_case_s_budget():
    import aes_switching
    assert all(row.door and row.budget == BY_LABEL_WAVE_2[name].budget for name, row in ROWS_WAVE_2.items())
    names = {aes_switching.row_name(row) for row in ROWS_WAVE_2.values()}
    assert names == set(DOOR_USERS_PRICED_WAVE_2) == set(DOOR_USERS_WHOLE_RUN_WAVE_2) and len(names) == 5
