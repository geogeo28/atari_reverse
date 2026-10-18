"""ctlmgr's OWN ROWS (`$fe49d2`, `src/aes/ctlmgr.c`; FLIP 4) — THE SCREEN MANAGER WOKEN, both shores from a booted
machine's idle to its next (`test/aes_ctlmgr.py`, `bench/tier3.py`'s `idle_to_idle_on`).

  the ROM's shore   the machine the ROM booted, the ROM's ctlmgr asleep in its main wait;
  our shore         THE SAME BOOT WITH THE SCREEN MANAGER OURS — `aes_rom_ctlmgr` entered by the ROM's own switchto at
                    the screen manager's first entry (the registry's mapping, which ictlmgr's own row proves is what
                    our ictlmgr + pstart store), asleep in ITS OWN frames on the screen manager's real 1,196 bytes.

Each row is one thing a user does, taken to the idle the machine reaches with nothing left: the screen manager's
turn(s) are our ctlmgr's — its loop, its two handlers and everything under them, its dispatcher — and the desk's or
an accessory's turn after it is the ROM's own code on both shores. WHAT IS HELD is said where it is held
(`tier3.idle_to_idle_on`); here, per row: the premise on the ROM's run (which handlers its ctlmgr called, with what,
and who ran after), both blobs with their pins, the table's price, and the REDs of each rule.

WHAT IS NOT A ROW HERE, each said: A KEY EATEN (no machine routes a key to the screen manager: a labelled staging,
Tier 1 — `test_aes_gemctrl.py`'s two key turns); THE SPIN WITH NO MENU BAR (the machine never idles again: no end to
run to — Tier 1, its two turns); the multi-click count's argument classes (Tier 1, the same battery).
"""
import pathlib
import re
import struct
import types
from collections import namedtuple

import pytest

from harness import addrs, bench_tier3, make_image

import aes
import aes_accessory_turns_pinned
import aes_boot
import aes_ctlmgr as cm
import aes_desk
import aes_stack as stack
import aes_event
import aes_gemctrl as gc
import aes_switching as switching
import aes_takeover
import case
import routines
import transcription
import test_aes_gemctrl as handlers

tier3 = bench_tier3
RECREATE = pathlib.Path(__file__).resolve().parents[1]
# The closed waves' entries of the ledger: slice E's (band 5 wave 2) states the count of the Tier 1-only cases held below.
THE_LEDGER_S_ARCHIVE = RECREATE / "STATUS_ARCHIVE.md"
onto, click, PRESS, RELEASE = gc.onto, gc.click, gc.PRESS, gc.RELEASE
A, W, VIEW = gc.TWO_WINDOWS, gc.TWO_WAITERS, aes_event.THE_VIEW_TITLE_S_POINT
SM, DESK, FIRST, SECOND = gc.THE_SCREEN_MANAGER, gc.THE_DESK_S_PROCESS, gc.FIRST_ACCESSORY, gc.SECOND_ACCESSORY
BUTTON, RECT = gc.HCTL_BUTTON, gc.HCTL_RECT
BENCH, SHIPPED = "bench", "bench_shipped"
# WHAT EVERY ROW'S TWO MACHINES DIFFER IN WHERE ITS RUNS END (`aes_ctlmgr.CLASSES`): the screen manager's context and
# its stack — two programs' frames — and the dispatcher's stack, on which our dispatcher ran...
EVERY_ROW_S = (cm.THE_DISPATCHER_S_STACK, cm.ITS_SAVED_CONTEXT, cm.ITS_STACK)
# ...and, WHERE THE SCREEN MANAGER PARKS LAST (no process of the ROM's runs after it), two more — MEASURED, FLIP 4's
# review: both shores make THE SAME BIOS AND VDI CALLS on every row (the cycles at the two trap handlers' first
# instructions are equal), so neither is behaviour:
#   * THE BIOS'S SAVE FRAME under savptr, ITS TEN SAVED REGISTERS ALONE (`tier3._classes_over`: D3-D7, A3-A7 — the
#     saved PC, `$fca7d4`, and SR are compared, and equal). The run's last BIOS trap was taken inside the screen
#     manager's turn and no process of the ROM's runs after to take another: the saved A6 and A7 point INTO THE
#     SCREEN MANAGER'S OWN STACK (the ROM's `$a72c` / `$a718`, the shipped blob's `$a6f6` / `$a6e2` on the bar's row)
#     and D3-D7 hold each ctlmgr's own registers.
#   * THE LINE-F MASK WORD, which the ROM's ctlmgr's last masked return rewrote (`$3080`) and no C does (`$2000`).
PARKED_LAST = (*EVERY_ROW_S, cm.THE_MASK_WORD, cm.THE_TRAP_SAVE)
# ...and THE SAVE FRAME ALONE on the accessory-entry row: the run's last BIOS trap is EACH BUILD'S DISPATCHER'S, as
# the screen manager parks its last turn — the saved A6 and A7 point into the dispatcher's stack (the ROM's `$8b78`
# / `$8b64`, ours `$8b44` / `$8b30`), D3 / D4 hold our screen manager's registers — and the accessory's final turn
# takes none; that turn rewrites the mask word alike on both shores, so the row is refused that class.
SAVE_FRAME_ALONE = (*EVERY_ROW_S, cm.THE_TRAP_SAVE)
# SINCE THE NARROW DOOR FLIP (band 5 wave 3) THE ACCESSORY MACHINES' ROWS RUN BEHIND OUR DOOR, and an accessory that
# reads its message and waits again PARKS THROUGH OUR DISPATCHER, as the screen manager does: WHERE AN ACCESSORY PARKS
# LAST the same two classes differ, for the same two reasons — the run's last BIOS trap is OUR idle's keyboard poll
# (each build's dispatcher's registers saved), and no masked return of the ROM's follows the accessory's turn (the
# mask word stays what our build's last ROM call left). MEASURED, both blobs: the six rows below that an accessory
# ends — the accessory-entry row among them, which `SAVE_FRAME_ALONE` named while the accessory's final turn was
# the ROM's code and rewrote the mask word alike on both shores (it has no row left).
AN_ACCESSORY_PARKED_LAST = PARKED_LAST
# SINCE BAND 6's BINDING (slice B0) THE DESK PARKS THROUGH OUR DISPATCHER TOO — the ROM's desk calls our AES through our
# Line-F table — so WHERE THE DESK PARKS LAST (it reads the message a row wrote it, and waits again) the same two
# classes differ, for the same two reasons: our idle's keyboard poll took the run's last BIOS trap, and no masked
# return of the ROM's AES follows the desk's turn. MEASURED, both blobs: the two rows that write the desk MN_SELECTED.
THE_DESK_PARKED_LAST = PARKED_LAST
THE_MENU_WORKED = {1: (aes_event.ONTO_ITS_PLAIN_ITEM,), 2: (click,)}
ON_THE_TOP_WINDOW = lambda name, *does, key=A: {0: (onto(gc.gadget(key, name)),), **{1 + nth: (each,) for nth, each in enumerate(does)}}  # noqa: E731

THE_BAR, THE_MENU, PAST_THE_TITLES, THE_CLOSER, BOTH, AN_ARROW, A_DRAG, TOPPED, THE_ENTRY = (
    "woken by the mouse onto a menu title: the bar's handler drops the menu and waits in it",
    "woken by the bar, an item chosen: MN_SELECTED written to the desk, which reads it",
    "woken by a click on the bar past the titles: the button's handler, nothing sent",
    "woken by a click on the top window's closer: WM_CLOSED written to its owner, which reads it",
    "woken by a button and the bar in one wake: the button's handler, then the menu worked",
    "woken by a click on the up arrow: the lock let go for a yield, WM_ARROWED written",
    "woken by a press on the title, a drag and the release: WM_MOVED written",
    "woken by a click on the other window's title: WM_TOPPED written, its four stale words the ROM's stack's",
    "woken by the desk menu's accessory entry chosen: AC_OPEN written; the accessory hides the bar")
# ...and THE MULTI-CLICK COUNT ABOVE 1 (gl_bpend, `$c84e`, which ctlmgr steps down once before a handler while it is above one) — the machine
# whose two accessories each wait for two clicks beside the desk holds 3 at its idle, the ROM's own. One row an arm:
# the button's steps it to 2 before hctl_button, the bar's before hctl_rect (where the menu's own waits then count it
# on: the step shows in the image at the dispatcher's stops, not where the run ends).
THE_COUNT_AT_3_A_BUTTON, THE_COUNT_AT_3_THE_BAR = (
    "woken by a click on the closer, two more processes in a two-click wait: the count stepped from 3 by the button's arm",
    "woken by the mouse onto a menu title, two more processes in a two-click wait: the count stepped from 3 by the bar's arm")
WOKEN = {woken.label: cm.register(woken) for woken in (
    cm.Woken(THE_BAR, gc.THE_DESK, {0: (onto(VIEW),)}, PARKED_LAST),
    cm.Woken(THE_MENU, gc.THE_DESK, {0: (onto(VIEW),), **THE_MENU_WORKED}, THE_DESK_PARKED_LAST),
    cm.Woken(PAST_THE_TITLES, A, dict(handlers.A_FIRST_TURN), PARKED_LAST),
    cm.Woken(THE_CLOSER, A, ON_THE_TOP_WINDOW("the closer", click), AN_ACCESSORY_PARKED_LAST),
    cm.Woken(BOTH, A, {0: (onto(VIEW), click), **THE_MENU_WORKED}, THE_DESK_PARKED_LAST),
    cm.Woken(AN_ARROW, A, ON_THE_TOP_WINDOW("the up arrow", click), AN_ACCESSORY_PARKED_LAST),
    cm.Woken(A_DRAG, A, ON_THE_TOP_WINDOW("the title", PRESS, onto(handlers.A_DRAG_TO), RELEASE), AN_ACCESSORY_PARKED_LAST),
    cm.Woken(TOPPED, A, {0: (onto(handlers.THE_OTHER_WINDOW_S_TITLE),), 1: (click,)},
             (*AN_ACCESSORY_PARKED_LAST, cm.THE_TOPPED_WORDS)),
    cm.Woken(THE_ENTRY, gc.HIDING, dict(handlers.THE_BAR_HIDDEN), AN_ACCESSORY_PARKED_LAST),
    cm.Woken(THE_COUNT_AT_3_A_BUTTON, W, ON_THE_TOP_WINDOW("the closer", click, key=W), AN_ACCESSORY_PARKED_LAST),
    cm.Woken(THE_COUNT_AT_3_THE_BAR, W, {0: (onto(VIEW),)}, PARKED_LAST),
)}
# THE PREMISE, read off the ROM's own run: the idles a delivery is taken at, the handlers the ROM's ctlmgr called (in
# order, with the mouse it handed each), and who the dispatcher entered — the screen manager, then whoever its
# message woke (the desk reads MN_SELECTED through its 46 polls of the keyboard; an accessory reads and drops).
Premise = namedtuple("Premise", "idles handlers entered")
VIEW_X, VIEW_Y = VIEW
PREMISES = {
    THE_BAR: Premise(1, ((RECT, VIEW),), (SM,)),
    THE_MENU: Premise(3, ((RECT, VIEW),), (SM,) * 3 + (DESK,) * 44),
    PAST_THE_TITLES: Premise(2, ((BUTTON, gc.ON_THE_BAR_PAST_THE_TITLES),), (SM,)),
    THE_CLOSER: Premise(2, ((BUTTON, gc.gadget(A, "the closer")),), (SM, SECOND, SECOND)),
    BOTH: Premise(3, ((BUTTON, VIEW), (RECT, VIEW)), (SM,) * 3 + (DESK,) * 44),
    AN_ARROW: Premise(2, ((BUTTON, gc.gadget(A, "the up arrow")),), (SM, SM, SECOND, SECOND)),
    A_DRAG: Premise(4, ((BUTTON, gc.gadget(A, "the title")),), (SM,) * 3 + (SECOND,) * 2),
    TOPPED: Premise(2, ((BUTTON, handlers.THE_OTHER_WINDOW_S_TITLE),), (SM, FIRST, FIRST)),
    THE_ENTRY: Premise(3, ((RECT, gc.THE_DESK_TITLE_S_POINT), (BUTTON, gc.accessory_entry_point(gc.HIDING))),
                       (SM,) * 3 + (FIRST,) * 3 + (SM, FIRST)),
    THE_COUNT_AT_3_A_BUTTON: Premise(2, ((BUTTON, gc.gadget(W, "the closer")),), (SM, SECOND, SECOND)),
    THE_COUNT_AT_3_THE_BAR: Premise(1, ((RECT, VIEW),), (SM,)),
}
# THE WHOLE RUNS' CYCLES, the ROM's and ours net of the entry both share, by blob; the turns themselves are
# `aes_turns_pinned`'s (by the row's name: `tools/repin.py` writes both from a recorded run).
WHOLE_RUN = {
    THE_BAR: {BENCH: (812236, 772548), SHIPPED: (812236, 766410)},
    THE_MENU: {BENCH: (1975728, 1780276), SHIPPED: (1975728, 1770122)},
    PAST_THE_TITLES: {BENCH: (85630, 69792), SHIPPED: (85630, 68252)},
    THE_CLOSER: {BENCH: (313410, 236178), SHIPPED: (313410, 232282)},
    BOTH: {BENCH: (1987850, 1788948), SHIPPED: (1987850, 1778368)},
    AN_ARROW: {BENCH: (225718, 156022), SHIPPED: (225718, 152322)},
    A_DRAG: {BENCH: (605006, 520786), SHIPPED: (605006, 514486)},
    TOPPED: {BENCH: (147904, 117254), SHIPPED: (147904, 113578)},
    THE_ENTRY: {BENCH: (1051754, 940020), SHIPPED: (1051754, 925488)},
    THE_COUNT_AT_3_A_BUTTON: {BENCH: (362068, 274678), SHIPPED: (362068, 268506)},
    THE_COUNT_AT_3_THE_BAR: {BENCH: (811980, 772420), SHIPPED: (811980, 766138)},
}
# ...and how many windows of the ROM's processes each run holds beside the screen manager's turns: THE DESK'S, where
# its message woke the desk — and none an accessory's since the narrow door flip: behind our door an accessory's turn
# is a turn of OURS, priced by itself (`aes_accessory_turns_pinned`), and how many of those each run holds is pinned
# beside (the accessory-entry row's two: the accessory reads AC_OPEN and hides the bar, then reads again).
# (SINCE BAND 6's BINDING no row of ctlmgr's has a window of the ROM's process left: the desk's, on the two rows that
# write it MN_SELECTED, is A TURN OF OURS — the ROM's desk text over our AES, ruling W6-R7: `THE_DESK_S_TURNS`.)
THE_ROM_S_WINDOWS = {THE_BAR: 0, THE_MENU: 0, PAST_THE_TITLES: 0, THE_CLOSER: 0, BOTH: 0, AN_ARROW: 0, A_DRAG: 0, TOPPED: 0,
                     THE_ENTRY: 0, THE_COUNT_AT_3_A_BUTTON: 0, THE_COUNT_AT_3_THE_BAR: 0}
THE_DESK_S_TURNS = {THE_BAR: 0, THE_MENU: 1, PAST_THE_TITLES: 0, THE_CLOSER: 0, BOTH: 1, AN_ARROW: 0, A_DRAG: 0, TOPPED: 0,
                    THE_ENTRY: 0, THE_COUNT_AT_3_A_BUTTON: 0, THE_COUNT_AT_3_THE_BAR: 0}
THE_ACCESSORIES_TURNS = {THE_BAR: 0, THE_MENU: 0, PAST_THE_TITLES: 0, THE_CLOSER: 1, BOTH: 0, AN_ARROW: 1, A_DRAG: 1, TOPPED: 1,
                         THE_ENTRY: 2, THE_COUNT_AT_3_A_BUTTON: 1, THE_COUNT_AT_3_THE_BAR: 0}
TURNS = {label: 2 if label == THE_ENTRY else 1 for label in WOKEN}
# HOW DEEP EACH ctlmgr GOES ON THE SCREEN MANAGER'S REAL STACK in the row's run — its top less the lowest byte the run
# stores there: (the ROM's, ours on the bench blob, ours on the shipped blob), THE MACHINE'S VDI (the ROM's) under
# the traps. (The build's OWN VDI under its traps — handlers and engines bound — is `test_aes_stack.py`'s staging
# and the bound's subject: a menu dropped 782 there on the shipped blob, 750 here.) Each fits its 1,196 bytes with
# the worst nest of interrupts on top, on both blobs.
# RE-PINNED BY THE DOOR DIET (band 5 wave 3; ours alone, the ROM's unmoved): every run that draws a menu is 82 bytes
# shallower — ob_draw holds everyobj's walk as its own body and calls just_draw as C calls, where three frames stood
# under each object drawn — and the closer's by 18: gr_watchbox's wait is a routine of its own (its frame 40 less;
# the run's lowest store stands 18 higher).
DEEPEST = {THE_BAR: (722, 746, 750), THE_MENU: (722, 746, 750), PAST_THE_TITLES: (272, 298, 308), THE_CLOSER: (474, 510, 520),
           BOTH: (722, 746, 750), AN_ARROW: (346, 396, 404), A_DRAG: (548, 640, 650), TOPPED: (340, 360, 366),
           THE_ENTRY: (616, 658, 668), THE_COUNT_AT_3_A_BUTTON: (474, 510, 520), THE_COUNT_AT_3_THE_BAR: (722, 746, 750)}


def _name(label):
    return cm.row_name(WOKEN[label])


def _pd(label, who):
    return gc.pd_of(WOKEN[label].machine, who)


def test_every_row_of_ctlmgr_is_registered_pinned_and_in_the_table():
    assert WOKEN.keys() == PREMISES.keys() == WHOLE_RUN.keys() == THE_ROM_S_WINDOWS.keys() == DEEPEST.keys() == THE_ACCESSORIES_TURNS.keys()
    assert set(map(_name, WOKEN)) == set(cm.ROWS)
    rows = [row for row in tier3().ROWS if tier3().is_a_woken_row(row)]
    assert sorted(row.case for row in rows) == sorted(WOKEN) and {row.address for row in rows} == {addrs.AES_ROM_CTLMGR}
    assert all(row.function == cm.FUNCTION and row.entry == addrs.AES_ROM_DISP_LOOP for row in rows)


@pytest.mark.parametrize("label", WOKEN)
def test_the_rom_s_ctlmgr_woken_calls_the_handlers_the_row_says_and_the_machine_idles_again(label):
    """THE PREMISE, on the ROM's own run from the booted machine's idle: every delivery of the chain taken at an idle,
    the ROM's ctlmgr calling exactly the handlers the row names — the button's before the bar's where one wake brings
    both — each with the mouse of that wake, and the dispatcher entering the screen manager and then whoever its
    message woke, to the idle with nothing left."""
    woken, premise = WOKEN[label], PREMISES[label]
    made = cm.made(woken)
    assert (made.switches.idles, sorted(made.switches.at_idles)) == (premise.idles, list(range(premise.idles)))
    assert made.switches.process is None and not made.switches.at_calls
    assert made.handlers == premise.handlers, f"{label}: the ROM's ctlmgr called {made.handlers}"
    assert made.entered == tuple(_pd(label, who) for who in premise.entered), f"{label}: entered {[hex(pd) for pd in made.entered]}"
    assert made.entered[0] == gc.SCREEN_MANAGER


@pytest.mark.parametrize("label", WOKEN)
def test_our_ctlmgr_woken_on_its_own_stack_does_what_the_rom_s_does_on_both_blobs(label, blob):
    """THE ROW, ON EACH BLOB (`tier3.idle_to_idle_on`: every rule it holds is said there): our `aes_rom_ctlmgr`, asleep
    on the screen manager's real stack of a machine the ROM booted, is woken by what the ROM's is and leaves the
    ROM's machine at the next idle — outside the classes the row names, each of which it needs. WHO RAN is held
    inside; here the pins: the whole runs' cycles, the turns (`aes_turns_pinned`), each turn under the bar by
    itself, and the windows of the ROM's processes beside them."""
    measured = tier3().idle_to_idle_on(blob, _name(label), WOKEN[label])
    assert len(measured.its_turns) == TURNS[label] and tier3().the_rom_s_windows(measured).windows == THE_ROM_S_WINDOWS[label]
    assert len(switching.accessory_turns_measured(measured)) == THE_ACCESSORIES_TURNS[label]
    assert len(switching.desk_turns_measured(measured)) == THE_DESK_S_TURNS[label]
    assert len(measured.turns) == THE_ACCESSORIES_TURNS[label] + THE_DESK_S_TURNS[label]
    assert measured.own_cycles == (sum(turn.ours for turn in measured.its_turns), sum(turn.the_rom_s for turn in measured.its_turns))
    switching.vet_the_whole_run(_name(label), blob, measured, WHOLE_RUN[label])
    switching.vet_its_turns(_name(label), blob, measured)
    # ...AND THE STACK, MEASURED ON THIS VERY RUN (the real entry, the real stack): how deep each ctlmgr went, pinned —
    # and ours fits the screen manager's 1,196 bytes with the worst nest of this build's interrupts on top.
    the_rom_s, bench, shipped = DEEPEST[label]
    assert measured.deepest == (the_rom_s, {BENCH: bench, SHIPPED: shipped}[blob.elf.parent.name]), (
        f"{label}: the two ctlmgrs went {measured.deepest} deep on the screen manager's stack: say which frame moved")
    lo, top, _why = gc.its_stack(cm.the_rom_s_machine(WOKEN[label]))
    assert top - lo == handlers.USABLE_STACK_BYTES and measured.deepest[1] + stack.nest(stack.shore_of(blob)) <= handlers.USABLE_STACK_BYTES


@pytest.mark.parametrize("label", WOKEN)
def test_the_table_prices_a_row_of_ctlmgr_on_its_turns(label):
    """WHAT THE TABLE READS: the row's own cycles are THE SCREEN MANAGER'S TURNS' — our build's own in them against the
    ROM's ctlmgr's — as the shipped blob runs them (the pinned turns), under the bar with their thunks; the windows
    of the ROM's processes in neither column; the general guard asked and passed."""
    row, = (row for row in tier3().ROWS if row.registered == _name(label))
    measured = tier3().measure(row, tier3().RomBench())
    pinned = switching.turns_pinned(_name(label), SHIPPED)
    assert measured.own_cycles == (sum(turn[0] for turn in pinned), sum(turn[1] for turn in pinned))
    assert tier3().glue_cycles_of(measured) == sum(turn[2] for turn in pinned)
    assert tier3().goes_through_the_os(row) and tier3().counts_within_bar_with_glue(measured)
    assert tier3().shared_cycles(measured)[0] == tier3().shared_cycles(measured)[1] > 0


# ---- THE REDS ----------------------------------------------------------------------------------------------------------------
def _shipped():
    return tier3().shipped_bench()


def test_a_class_named_and_not_needed_or_needed_and_not_named_is_refused():
    """EACH CLASS A ROW NAMES MUST DIFFER, AND NOTHING DIFFERS OUTSIDE THEM: the closer's row with the Line-F mask
    word named beside its three (the accessory's turn after the screen manager's rewrites it alike on both shores) is
    refused as naming a class it does not need; with its stack's class taken away it is refused by the bytes."""
    woken = WOKEN[THE_CLOSER]
    with pytest.raises(AssertionError, match="a class named and not needed excuses a store for nothing"):
        tier3().idle_to_idle_on(_shipped(), "a row", woken._replace(differs=(*woken.differs, cm.THE_MASK_WORD)))
    with pytest.raises(AssertionError, match="OUR MACHINE IS NOT THE ROM'S outside the classes the row names"):
        tier3().idle_to_idle_on(_shipped(), "a row", woken._replace(differs=(cm.THE_DISPATCHER_S_STACK, cm.ITS_SAVED_CONTEXT)))


def test_wm_topped_s_four_words_are_what_they_are_and_are_named_by_the_row_that_sends_them_alone():
    """THE DECLARED DIVERGENCE ON THE SCREEN MANAGER'S REAL STACK (ruling W2-R2). On the ROM's run of the row the
    message's words 4..7 are RESIDUE OF hctl_button'S wm_find, the call before hctl_window's (traced: the eight bytes
    are last stored inside wm_find's Line-F call of ob_find, `$feca5e`, and one word between its return and
    hctl_window's entry) — VETTED AS WHAT THEY ARE, in the order the message carries them: word 4 THE HIGH HALF OF A
    RETURN ADDRESS INTO THE AES'S TEXT (ob_find's caller's); words 6:5 ONE LONGWORD, A SAVED FRAME POINTER — an
    address inside the screen manager's own stack (`$0000a85a`: wm_find's frame, saved by ob_find's `link`); word 7
    THE WORD UNDER IT, 2 on this machine (ob_find's first local: its depth argument and the window it found are
    both 2 here — not told apart). Our run sends four zeroes; the row names exactly those eight bytes IN THE THREE
    PLACES the write carries them — the manager's buffer, the owner's pipe (by the machine's own pointer), the
    buffer the owner read into (`aes_ctlmgr.THE_TOPPED_WORDS`) — is red without them, and a row that sends another
    message is refused the class."""
    woken = WOKEN[TOPPED]
    rom = make_image({0: cm.the_rom_s_machine(woken)})
    watch = switching.IdleToIdle(cm.made(woken).switches)
    tier3()._run_to_its_next_idle(rom, watch, _shipped())
    places = cm.the_topped_words_places(rom)
    lo, hi = cm.STALE_WORDS_AT
    text_half, frame_low, frame_high, under_it = struct.unpack(">4H", bytes(rom[lo:hi]))
    stack_lo, stack_hi, _why = gc.its_stack(rom)
    assert aes.AES_TEXT[0] >> 16 <= text_half <= (aes.AES_TEXT[1] - 1) >> 16
    assert stack_lo <= frame_high << 16 | frame_low < stack_hi and (frame_high, under_it) == (0, 2)
    _manager, owner, _again = PREMISES[TOPPED].entered             # ...the window's owner: who the dispatcher enters next
    owner_s_pipe = case.long_in(rom, _pd(TOPPED, owner) + aes.PD_QUEUE_ADDRESS) & aes.OS_BUS_ADDR_MASK
    in_the_pipe = [place for place in places if owner_s_pipe <= place[0] and place[1] <= owner_s_pipe + aes.PD_QUEUE_BYTES]
    assert len(places) == 3 and (lo, hi) in places and len(in_the_pipe) == 1, (places, hex(owner_s_pipe))
    with pytest.raises(AssertionError, match="OUR IMAGE IS NOT THE ROM'S"):
        tier3().idle_to_idle_on(_shipped(), "a row", woken._replace(differs=EVERY_ROW_S))
    with pytest.raises(AssertionError, match="a class named and not needed"):
        tier3().idle_to_idle_on(_shipped(), "a row", WOKEN[THE_CLOSER]._replace(differs=(*WOKEN[THE_CLOSER].differs, cm.THE_TOPPED_WORDS)))


def test_a_machine_whose_screen_manager_is_the_rom_s_is_refused_where_it_is_resumed(monkeypatch):
    """WHO RAN, READ OFF THE RUN: our shore handed THE ROM-BOOTED MACHINE with the blob laid beside it — the screen
    manager parked in the ROM's frames — is refused BY NAME at switchto's `rte`: its turn would be the ROM's ctlmgr,
    priced as ours."""
    def the_rom_s_with_the_blob_laid(woken, blob):
        ram = bytearray(cm.the_rom_s_machine(woken))
        ram[blob.base:blob.base + len(blob.blob)] = blob.blob
        return bytes(ram)
    monkeypatch.setattr(cm, "our_machine", the_rom_s_with_the_blob_laid)
    with pytest.raises(switching.Refused, match="A ROW ON A TAKEOVER MACHINE WHOSE SCREEN MANAGER RESUMES IN THE ROM'S TEXT"):
        tier3().idle_to_idle_on(_shipped(), "a row", WOKEN[THE_BAR])


def test_a_delivery_our_run_is_not_handed_ends_another_run_and_is_refused():
    """THE SCHEDULE IS HELD ON BOTH SHORES: handed one delivery fewer (the click never comes), the run idles where
    the ROM's took an interrupt and ends there — another run than the row's, refused by name."""
    woken = WOKEN[THE_CLOSER]
    made = cm.made(woken)
    short = made.switches._replace(at_idles={0: made.switches.at_idles[0]}, idles=1)
    watch = switching.IdleToIdle(short)
    tier3()._run_to_its_next_idle(make_image({0: cm.the_rom_s_machine(woken)}), watch, _shipped())
    assert watch.entered == [] and watch.idles == 2
    with pytest.raises(switching.Refused, match="the run made 1 idle\\(s\\) with a delivery and .* where the ROM's own makes 2"):
        watch.switches = made.switches
        watch.vet_ended("a run")


def test_our_machine_is_the_takeover_of_the_row_s_own_boot():
    """THE MACHINE OUR SHORE RUNS OVER (`aes_ctlmgr.our_machine`) is the takeover machine of the row's own boot: the
    ROM-booted megabyte outside the classes a takeover differs in by nature, this blob laid, the screen manager's
    p_ldaddr our entry and its parked PC in the blob."""
    blob, woken = _shipped(), WOKEN[THE_CLOSER]
    ram = cm.our_machine(woken, blob)
    assert bytes(ram[blob.base:blob.base + len(blob.blob)]) == blob.blob
    assert case.long_in(ram, gc.SCREEN_MANAGER + aes.PD_LDADDR) == blob.entry(cm.SYMBOL)
    assert blob.base <= aes_boot.parked_pc(ram, gc.SCREEN_MANAGER) < blob.end
    assert aes_takeover.state_of(ram) != aes_takeover.state_of(cm.the_rom_s_machine(woken))


def test_the_multi_click_count_stands_above_one_on_the_machine_its_two_rows_run_over():
    """THE COUNT'S TWO ROWS ARE WHAT THEY SAY: their machine holds gl_bpend at 3 where it idles (two accessories in a
    two-click wait beside the desk's own) — the ROM's own count, nothing staged — where every other machine holds 1,
    at which ctlmgr's step does nothing. WHERE THE STEP SHOWS: not where a run ends (the accessory, woken, waits for
    its two clicks again and the count is 3 once more; under the menu the menu's own waits count it on) but IN THE
    IMAGE AT THE DISPATCHER'S STOPS between — the count read at 2 there on the ROM's run of the button's row — which
    is what a build that drops the step on either arm is refused by (the sweep's two mutants)."""
    woken = WOKEN[THE_COUNT_AT_3_A_BUTTON]
    rom, seen = make_image({0: cm.the_rom_s_machine(woken)}), []
    assert aes.signed(case.word_in(rom, gc.AES_GL_BPEND)) == 3
    watch = switching.IdleToIdle(cm.made(woken).switches, images=lambda memory: seen.append(aes.signed(case.word_in(memory, gc.AES_GL_BPEND))))
    tier3()._run_to_its_next_idle(rom, watch, _shipped())
    assert 2 in seen and seen[0] == 3 == aes.signed(case.word_in(rom, gc.AES_GL_BPEND)), seen
    assert aes.signed(case.word_in(cm.the_rom_s_machine(WOKEN[THE_CLOSER]), gc.AES_GL_BPEND)) == 1, "every other machine holds 1"


def test_the_image_at_a_stop_is_held_on_every_path_that_measures_a_run_that_switches(monkeypatch):
    """THE BLOB-SIDE HOLD HAS TEETH ON ALL THREE PATHS (`tier3.vet_the_images_at_the_stops`): our image read with ONE
    BYTE OTHER at one stop of the dispatcher's watch — the mouse's column, as a store made before a yield and undone
    after it would leave it — is refused by the stop and the page: by the table's measurement of a row that switches,
    by a named blob's, and by a row of ctlmgr's own. The run's END is the ROM's in all three: nothing else sees it."""
    import test_aes_evdisp_model as model
    pilot = next(row for row in model.WOKEN_ROWS if row.label == model.WOKEN_BY_A_KEY)
    pages, asked = aes_event.image_pages, []

    def one_byte_other_at_its_second_stop(memory, also=()):
        asked.append(len(asked))
        if len(asked) % 2 == 0 and len(asked) == 4:     # the second shore's second stop: ours, the runs made in order
            memory = bytearray(memory[:addrs.ST_RAM_BYTES])
            memory[aes.AES_GL_WCHAR] ^= 1
        return pages(memory, also)
    for measure in (lambda: tier3().measure(switching.table_row(pilot), tier3().RomBench()),
                    lambda: switching.measured_on(_shipped(), pilot),
                    lambda: tier3().idle_to_idle_on(_shipped(), "a row", WOKEN[THE_BAR])):
        asked.clear()
        monkeypatch.setattr(aes_event, "image_pages", one_byte_other_at_its_second_stop)
        with pytest.raises(AssertionError, match="of the dispatcher's watch OUR IMAGE IS NOT THE ROM'S"):
            measure()
        monkeypatch.setattr(aes_event, "image_pages", pages)
        measure()


# ---- THE HANDLERS' OWN CASES, MEASURED WHERE EACH SHORE'S OWN ctlmgr ARRIVES AT ITS OWN HANDLER (slice E) ----------------------
# Every case of the handlers' battery is AN ARRIVAL (`test_aes_gemctrl.py`). Its TIER 1 starts at the ROM's arrival, on
# the host. Its TIER 3 is measured where a build really runs the handler (`tier3.at_its_arrival_on`): both shores from
# the booted machine's idle — ours the same boot with the screen manager ours — through the case's own chain to the
# handler's first instruction (the ROM's ctlmgr at the ROM's routine; OUR ctlmgr, and our handlers above the one
# arrived at, at OUR core) and ON THROUGH THE HANDLER TO ITS RETURN, on the screen manager's real stack. The priced
# cases are the table's rows so (`handlers.MEASURED_AT_ITS_ARRIVAL`), pinned on both blobs; the Tier 1-only cases are
# held the same way, to the same rules, and pinned nowhere.
# ...BUT ct_msgup's: IN OUR BUILD IT HAS NO ARRIVAL OF ITS OWN. GCC inlines it into its two callers (hctl_window, hctl_rect:
# one translation unit) on both blobs — no instruction of either names its entry, which exists for its own rows — so
# our screen manager never stands at "ct_msgup's first instruction" (held below: the day a blob calls it, its cases
# join). What our ct_msgup does under our callers is in the rows of hctl_window and hctl_rect whose run goes on
# through it — measured here, at our arrivals — in ctlmgr's own rows, and in its own rows from the ROM's arrivals.
INLINED_INTO_ITS_CALLERS = gc.CT_MSGUP
# ...whose Line-F callers in the ROM's text are two of the screen manager's handlers, each OURS (C) on a machine of ours:
# the table's thunk of ct_msgup is reached by no ROM caller that still runs.
ROM_CALLERS_OF_CT_MSGUP = {"AES_ROM_HCTL_WINDOW", "AES_ROM_HCTL_RECT"}
EVERY_CASE = {**handlers.RETURNING, **handlers.SWITCHING, **handlers.UNPRICED}
EVERY_ARRIVAL = {handlers.registered_name(key): key for key, each in EVERY_CASE.items() if each.arrival.chain is not None}
ARRIVALS = {name: key for name, key in EVERY_ARRIVAL.items() if key[0] != INLINED_INTO_ITS_CALLERS}
THE_BOOT_S_OWN = [each.arrival for each in handlers.RETURNING.values() if each.arrival.chain is None]
# THE WHOLE RUNS' CYCLES OF THE HANDLERS THAT RETURN WITHOUT A SWITCH, the ROM's and ours net of the entry both share,
# by blob (a handler that switches is pinned in its own battery, `handlers.WHOLE_RUN`: the same pairs it held as a call
# over the ROM's arrival's machine — the move changed no number of either shore's).
RETURNING_WHOLE_RUN = {
    "aes_hctl_button, the hidden bar's two clicks, counted twice and posted once: counted down to one":
        {BENCH: (362, 100), SHIPPED: (362, 100)},
    "aes_hctl_button, a real click on a window's closer after them: the count still one, the click swallowed":
        {BENCH: (362, 100), SHIPPED: (362, 100)},
    "aes_hctl_button, a click on the bar past the titles: the desktop's place, nothing":
        {BENCH: (7460, 4660), SHIPPED: (7460, 4368)},
    "aes_hctl_button, the top window's closer clicked: the window found and worked":
        {BENCH: (193484, 138286), SHIPPED: (193484, 136356)},
    "aes_hctl_window, the closer clicked: WM_CLOSED":
        {BENCH: (188444, 135016), SHIPPED: (188444, 133246)},
    "aes_hctl_window, the fuller clicked: WM_FULLED":
        {BENCH: (185108, 132570), SHIPPED: (185108, 130932)},
    "aes_hctl_window, the title clicked: WM_MOVED to where it is":
        {BENCH: (246240, 200796), SHIPPED: (246240, 199346)},
    "aes_hctl_window, the sizer clicked: WM_SIZED to the point clicked":
        {BENCH: (329794, 284994), SHIPPED: (329794, 283342)},
    "aes_hctl_window, the information line clicked: no gadget's, nothing sent":
        {BENCH: (62456, 27502), SHIPPED: (62456, 27800)},
    "aes_hctl_window, a window that is not the top one: WM_TOPPED":
        {BENCH: (15260, 9790), SHIPPED: (15260, 8462)},
    "aes_hctl_window, the title of a window with a SIZER and no MOVER clicked: nothing sent":
        {BENCH: (66294, 29940), SHIPPED: (66294, 29972)},
    "aes_hctl_window, the corner of a window with a MOVER and no SIZER clicked: nothing sent":
        {BENCH: (61882, 27254), SHIPPED: (61882, 27550)},
    "aes_hctl_rect, the mouse off the titles again, along the bar, before the manager ran: nothing":
        {BENCH: (664, 422), SHIPPED: (664, 422)},
    "aes_hctl_rect, no menu bar: nothing":
        {BENCH: (298, 154), SHIPPED: (298, 154)},
}


def _handled(name):
    return handlers.handled(ARRIVALS[name])


def _pinned(name):
    """The whole run's pinned pairs of the case `name`, by blob — None for a Tier 1-only case."""
    key = ARRIVALS[name]
    return handlers.WHOLE_RUN.get(key[1]) if key in handlers.SWITCHING else RETURNING_WHOLE_RUN.get(name)


def test_every_case_of_the_handlers_is_an_arrival_this_battery_measures_at_or_says_why_not():
    assert len(EVERY_ARRIVAL) == len(EVERY_CASE) - 1 and THE_BOOT_S_OWN == [gc.BOOT_ARRIVAL]
    assert {key[0] for key in ARRIVALS.values()} == set(gc.ROUTINES) - {INLINED_INTO_ITS_CALLERS}
    assert len(ARRIVALS) == len(EVERY_ARRIVAL) - sum(key[0] == INLINED_INTO_ITS_CALLERS for key in EVERY_ARRIVAL.values())
    # THE TABLE'S ROWS: every priced case is measured at its arrival, or is one of the two kinds its battery names.
    priced = {handlers.registered_name(key) for key in (*handlers.RETURNING, *handlers.SWITCHING)}
    assert set(cm.HANDLED) == set(handlers.MEASURED_AT_ITS_ARRIVAL) == priced & set(ARRIVALS)
    assert priced - set(cm.HANDLED) == {handlers.registered_name(key) for key in handlers.NOT_MEASURED_AT_AN_ARRIVAL_OF_OURS}
    assert sorted(key[0] for key in handlers.NOT_MEASURED_AT_AN_ARRIVAL_OF_OURS) == sorted([gc.HCTL_BUTTON] + [gc.CT_MSGUP] * 4)
    rows = {row.registered: row for row in tier3().ROWS if tier3().is_measured_at_its_arrival(row)}
    assert set(rows) == set(cm.HANDLED) and not any(row.dropped for row in rows.values())
    assert {name for name in ARRIVALS if _pinned(name)} == set(cm.HANDLED), "every row measured at its arrival is pinned on both blobs"
    assert all(pairs.keys() == {BENCH, SHIPPED} for pairs in RETURNING_WHOLE_RUN.values())


def test_ct_msgup_is_called_by_no_instruction_of_a_blob_and_its_arrival_is_refused_by_name(blob):
    """THE ONE HANDLER WITH NO ARRIVAL OF ITS OWN ON A BLOB OF OURS (above): no instruction of the blob's own code calls
    or branches to `aes_ct_msgup` — it is inlined into its callers — and a run asked to arrive at its entry is refused
    BY NAME where the machine idles with the handler never called, not run to a budget. ONE CALLER OF IT IS THE
    TABLE'S since band 6's binding: the Line-F thunk, which a ROM caller's Line-F word reaches — and no ROM caller is
    left to make one (its callers in the ROM's text are the screen manager's, ours: `ROM_CALLERS_OF_CT_MSGUP`)."""
    core = routines.core_symbol(INLINED_INTO_ITS_CALLERS)
    naming = [line for line in transcription.listing(blob.elf).splitlines() if f"<{core}>" in line and "\t" in line]
    thunk, = (symbol for symbol in transcription.symbol_table(blob.elf) if symbol.name == transcription.LINEF_THUNK_PREFIX + core)
    in_the_thunk = [line for line in naming if thunk.start <= int(line.split(":")[0], 16) < thunk.start + thunk.size]
    assert len(in_the_thunk) == 1, f"the table's thunk of ct_msgup calls it once: {in_the_thunk}"
    naming = [line for line in naming if line not in in_the_thunk]
    assert not naming, f"a blob names ct_msgup's entry: its cases have an arrival now — {naming[:2]}"
    import test_aes_rom_data as rom_census      # (here: imported at the head, it would move the registry's order)
    callers = {rom_census._the_c_routine_holding(site) for sites in aes.line_f_call_sites(INLINED_INTO_ITS_CALLERS).values()
               for site in sites}
    assert callers == ROM_CALLERS_OF_CT_MSGUP, f"ct_msgup's Line-F callers in the ROM's text: {callers}"
    name, key = next((name, key) for name, key in EVERY_ARRIVAL.items()
                     if key[0] == INLINED_INTO_ITS_CALLERS and "WM_CLOSED, the button up" in name)
    with pytest.raises(switching.Refused, match="was\\s+never called: the screen manager did not arrive there"):
        tier3().at_its_arrival_on(blob, name, handlers.handled(key))


@pytest.mark.parametrize("case_name", ARRIVALS)
def test_a_handler_is_measured_where_our_ctlmgr_arrives_at_it_on_the_real_stack_on_both_blobs(case_name, blob):
    """THE ROW (`tier3.at_its_arrival_on`: every rule it holds is said there), ON EACH BLOB: from the booted machine's
    idle, through the case's own chain, our screen manager — `aes_rom_ctlmgr` on its real stack, and for a handler
    called by another (hctl_window under hctl_button) our handlers above it — arrives at OUR core of the case's
    handler with the frame the ROM's caller pushed, AND THE HANDLER RUNS ON TO ITS RETURN THERE: the image at every
    stop the ROM's, the megabyte where it returns the ROM's outside the classes the case names (each needed), the
    same door calls, the same windows, and not one cycle of it in the ROM's own text of the handler. THE PINS, for a
    priced case: the slice's cycles on each shore — the very pairs the row held as a call over the ROM's arrival's
    machine. AND THE STACK: our deepest store on the screen manager's 1,196 bytes, from the machine's idle to the
    handler's return, fits with the worst nest of this build's interrupts on top."""
    handled = _handled(case_name)
    measured = tier3().at_its_arrival_on(blob, case_name, handled)
    if _pinned(case_name):
        switching.vet_the_whole_run(case_name, blob, measured, _pinned(case_name))
    assert tier3().counts_within_bar_with_glue(measured), f"{case_name}: over the bar on one of its counts"
    lo, top, _why = gc.its_stack(gc.machine(handled.arrival.machine).ram)
    assert top - lo == handlers.USABLE_STACK_BYTES and measured.deepest[1] + stack.nest(stack.shore_of(blob)) <= handlers.USABLE_STACK_BYTES


def test_the_table_measures_a_handler_s_row_at_its_arrival_and_says_what_it_leaves_out(monkeypatch):
    """THE TABLE'S OWN ROAD (`tier3.measure` → `at_its_arrival_on`, on the blob that prices the row as shipped): a
    priced case's measurement IS the one at its arrival — the same costs to the instruction — with the general guard
    asked and passed; and the lines under the row name its classes, not a kit call's drops."""
    name = next(name for name, key in handlers.MEASURED_AT_ITS_ARRIVAL.items() if key in handlers.RETURNING and key[0] == gc.HCTL_WINDOW)
    row, = (row for row in tier3().ROWS if row.registered == name)
    asked, made, at_its_arrival_on = [], [], tier3().at_its_arrival_on

    def at_its_arrival(blob, who, handled):
        asked.append((who, handled))
        made.append(at_its_arrival_on(blob, who, handled))
        return made[-1]
    monkeypatch.setattr(tier3(), "at_its_arrival_on", at_its_arrival)
    measured = tier3().measure(row, tier3().RomBench())
    assert asked == [(name, cm.HANDLED[name])], "the table's road measures the row at its arrival, once (the kit's call costs the same: asked by itself)"
    assert measured is made[0], "...and what the table prices IS that measurement, not another road's answer beside it"
    at_its_arrival = at_its_arrival_on(_shipped(), name, cm.HANDLED[name])
    assert tier3()._costs(measured) == tier3()._costs(at_its_arrival) and measured.own_cycles == at_its_arrival.own_cycles
    assert measured.deepest == at_its_arrival.deepest and measured.deepest[1] > measured.deepest[0] > 0, "...on the screen manager's real stack"
    lines = tier3()._where_the_handler_returns_lines(cm.HANDLED[name], 0)
    assert len(lines) == len(cm.HANDLED[name].differs) and all(tier3().WHERE_THE_HANDLER_RETURNS in line for line in lines)


def test_a_named_blob_s_battery_measures_a_handler_s_row_at_its_arrival_too(monkeypatch):
    """...AND SO DOES A NAMED BLOB'S (`aes_switching.measured_on`, what `vet_on_a_blob` and the recorder go through): a
    handler's row that switches is measured through its handler at its arrival, once, and the watch answered is the
    handler's own run's — its idles, polls and door calls numbered from the handler's entry. (HELD BY ITSELF: the
    kit's call over the ROM's arrival's machine measures the same pairs, so a road that fell back to it would pass
    every pin.)"""
    row = handlers.ROWS[ARRIVALS[THE_CLOSER_HELD][1]]
    asked, made, through = [], [], tier3().through_its_handler_on

    def through_its_handler(blob, who, handled):
        asked.append((who, handled))
        made.append(through(blob, who, handled))
        return made[-1]
    monkeypatch.setattr(tier3(), "through_its_handler_on", through_its_handler)
    measured, watch, foreign = switching.measured_on(_shipped(), row)
    assert asked == [(THE_CLOSER_HELD, cm.HANDLED[THE_CLOSER_HELD])] and foreign == measured.foreign
    assert (measured, watch) == made[0] and measured is made[0][0], "...and what is answered IS that run's measurement and its watch"
    premise = handlers.premise(row.label)
    assert (watch.idles, tuple(watch.entered)) == (premise.idles, tuple(premise.entered)) and watch.inner.closed == watch.inner.calls > 0
    assert watch.switches.process == gc.SCREEN_MANAGER and measured.deepest[1] > 0


def test_a_return_address_reached_with_the_frame_still_pushed_is_no_return():
    """THE SLICE'S END IS THE HANDLER'S RETURN (`aes_switching.ThroughAHandler`), on stand-in watches: the address its
    caller left at the arrival, reached with the stack pointer anywhere but one longword above the arrival's, is a
    stop like any other and handed to the handler's own watch; reached with the frame popped it ends the run, the
    second mark taken there."""
    returns_to, arrival_sp, memory = 0xfe4a40, 0xa800, bytearray(0x10000)
    memory[arrival_sp:arrival_sp + aes.LONG_BYTES] = returns_to.to_bytes(aes.LONG_BYTES, "big")
    seen, marks = [], iter(("at the arrival", "at the return"))

    class Arriving:
        first = frozenset({0x100})

        def stopped(self, pc, sp, memory):
            raise aes_event.Ended

    class Handling:
        first = frozenset({0x200})

        def stopped(self, pc, sp, memory):
            seen.append((pc, sp))
            return self.first
    through = switching.ThroughAHandler(Arriving(), lambda _memory, _sp: Handling(), lambda: next(marks))
    assert through.stopped(0x100, arrival_sp, memory) == {0x200, returns_to} and through.arrived_at == "at the arrival"
    assert through.stopped(returns_to, arrival_sp - 8, memory) == {0x200} and seen == [(returns_to, arrival_sp - 8)]
    assert through.stopped(0x200, arrival_sp - 8, memory) == {returns_to} and through.returned_at is None
    with pytest.raises(aes_event.Ended):
        through.stopped(returns_to, arrival_sp + aes.LONG_BYTES, memory)
    assert through.returned_at == "at the return" and len(seen) == 2


def test_the_boot_s_own_arrival_is_our_ctlmgr_s_too(blob):
    """...AND THE ONE ARRIVAL THAT IS NO DISPATCHER'S: the desk's menu_bar posts the screen manager a click and the
    boot calls hctl_button with it before its first idle. The same boot with the screen manager ours, stopped at OUR
    hctl_button's first instruction (`aes_boot.booted(until=)`: an address of the blob), is there with the ROM's
    frame — the click's point — on the screen manager's own stack, in our ctlmgr's first turn. (MET, NOT MEASURED:
    no run from a machine's idle reaches it; its row is a call over the ROM's arrival's machine.)"""
    name, arguments, _pokes = gc.at(gc.BOOT_ARRIVAL)
    ours = aes_boot.ours_of(blob)
    core = dict(ours.handlers)[getattr(addrs, name)]
    boot = aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=core, ours=ours)
    sp = boot.registers["isp"]
    lo, top, _why = gc.its_stack(boot.ram)
    assert boot.registers["pc"] == core and lo < sp < top and blob.base <= case.long_in(boot.ram, sp) < blob.end
    assert tier3()._frame_our_caller_pushed(len(arguments))(boot.ram, sp) == arguments


# ---- THE REDS OF A ROW MEASURED AT ITS ARRIVAL ---------------------------------------------------------------------------------
A_CLICK_ON_THE_CLOSER = handlers.registered_name((gc.HCTL_WINDOW, "the closer clicked: WM_CLOSED"))
THE_CLOSER_HELD = handlers.registered_name((gc.HCTL_WINDOW, "the closer held; released inside it: WM_CLOSED"))
THE_ARROW_HELD = handlers.registered_name((gc.HCTL_WINDOW, "the up arrow held: sent, read by its owner, sent again; released"))
THE_DESK_S_OWN_ITEM = handlers.registered_name(
    (gc.HCTL_RECT, "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds"))
NOTHING_SENT = handlers.registered_name((gc.HCTL_WINDOW, "the information line clicked: no gadget's, nothing sent"))
TOPPED_AT_ONCE = handlers.registered_name((gc.HCTL_WINDOW, "a window that is not the top one: WM_TOPPED"))


def _our_image_read_one_byte_other(monkeypatch, at=None):
    """OUR SHORE'S READER OF THE IMAGE AT A STOP (`tier3._HandlerStopImages.ours`), reading ONE BYTE OTHER (the mouse's
    column's metric) at the asking `reading.at` (None: at none) of each run begun with `reading.asked` emptied: the
    `reading`. (The reader itself, not `aes_event.image_pages`: a derivation made on the way reads pages too, and its
    askings are not the watch's.)"""
    reader, reading = tier3()._HandlerStopImages.ours, types.SimpleNamespace(at=at, asked=[])

    def ours(self, memory):
        reading.asked.append(None)
        if len(reading.asked) == reading.at:
            memory = bytearray(memory[:addrs.ST_RAM_BYTES])
            memory[aes.AES_GL_WCHAR] ^= 1
        return reader(self, memory)
    monkeypatch.setattr(tier3()._HandlerStopImages, "ours", ours)
    return reading


def test_the_image_at_an_arrival_is_held_too(monkeypatch):
    """..."OVER THE ROM'S MACHINE" HAS TEETH: our image read with one byte other AT THE ARRIVAL ITSELF — the last stop
    of our run before the handler's own — is refused by that stop and its page; the frame alone would not have seen
    it. (A handler that returns without a switch: its own run makes no stop of the dispatcher's.)"""
    arriving = cm.arriving(_handled(A_CLICK_ON_THE_CLOSER).arrival)
    stops = arriving.switches.polls + len(arriving.entered) + 1             # our run's polls, resumes and its arrival
    reading = _our_image_read_one_byte_other(monkeypatch, at=stops)
    with pytest.raises(AssertionError, match="to its arrival: at arrival 0 of the dispatcher's watch OUR IMAGE IS NOT THE ROM'S"):
        tier3().at_its_arrival_on(_shipped(), A_CLICK_ON_THE_CLOSER, _handled(A_CLICK_ON_THE_CLOSER))
    assert len(reading.asked) == stops


def test_the_image_at_a_stop_inside_the_handler_is_held_too(monkeypatch):
    """...AND SO HAS THE HANDLER'S OWN RUN: our image read with one byte other at THE LAST STOP OF THE DISPATCHER'S
    WATCH INSIDE THE HANDLER (a press held on the closer: the handler blocks and is woken) is refused by that stop —
    a store made before a switch and undone after it, which where the handler returns nothing would see."""
    handled = _handled(THE_CLOSER_HELD)
    arriving, reading = cm.arriving(handled.arrival), _our_image_read_one_byte_other(monkeypatch)
    tier3().at_its_arrival_on(_shipped(), THE_CLOSER_HELD, handled)        # ...counted first: every stop of our run
    stops = len(reading.asked)
    inside = stops - (arriving.switches.polls + len(arriving.entered) + 1)
    assert inside >= cm.taken_through(handled).polls > 0, "the handler's own run stops at the dispatcher"
    reading.at, reading.asked[:] = stops, []
    with pytest.raises(AssertionError, match=f"{re.escape(THE_CLOSER_HELD)}: at (poll|resume) \\d+ of the dispatcher's watch OUR IMAGE IS NOT THE ROM'S"):
        tier3().at_its_arrival_on(_shipped(), THE_CLOSER_HELD, handled)
    assert len(reading.asked) == stops


def test_an_arrival_with_another_frame_than_the_rom_s_case_is_refused(monkeypatch):
    """...AND THE FRAME IS COMPARED WHERE THE RUNS ARRIVE: the same case held to a frame one word other than the ROM's
    run derived is refused by name."""
    name = next(name for name, key in ARRIVALS.items() if key[0] == gc.HCTL_BUTTON)
    arriving = cm.arriving(_handled(name).arrival)
    monkeypatch.setattr(cm, "arriving", lambda _arrival: arriving._replace(words=(arriving.words[0] + 1, *arriving.words[1:])))
    with pytest.raises(AssertionError, match="our ctlmgr hands AES_ROM_HCTL_BUTTON"):
        tier3().at_its_arrival_on(_shipped(), name, _handled(name))


def test_a_class_a_handler_s_row_names_and_does_not_need_or_needs_and_does_not_name_is_refused():
    """EACH CLASS A ROW NAMES WHERE ITS HANDLER RETURNS MUST DIFFER, AND NOTHING DIFFERS OUTSIDE THEM: the information
    line's row (no wait: the save frame is the one the last poll before the arrival left, equal on both shores) with
    the save frame named is refused as naming a class it does not need; the closer's row — a wait of its own — with
    the save frame taken away is refused by the bytes; and so is any row without its stack's class."""
    # (SINCE BAND 6's BINDING every handler's row names the save frame — its arrival's frame is our idle's poll's on
    # every machine — so the class named and not needed is shown with WM_TOPPED's words on a row that sends none.)
    nothing_sent, closer = _handled(NOTHING_SENT), _handled(A_CLICK_ON_THE_CLOSER)
    assert cm.THE_TRAP_SAVE in nothing_sent.differs and cm.THE_TRAP_SAVE in closer.differs
    assert cm.THE_TOPPED_WORDS not in nothing_sent.differs
    with pytest.raises(AssertionError, match="a class named and not needed excuses a store for nothing"):
        tier3().at_its_arrival_on(_shipped(), "a row", nothing_sent._replace(differs=(*nothing_sent.differs, cm.THE_TOPPED_WORDS)))
    for without in (cm.THE_TRAP_SAVE, cm.ITS_STACK, cm.THE_MASK_WORD):
        with pytest.raises(AssertionError, match="OUR MACHINE IS NOT THE ROM'S outside the classes the row names"):
            tier3().at_its_arrival_on(_shipped(), "a row", closer._replace(differs=tuple(each for each in closer.differs if each != without)))


def test_wm_topped_s_four_words_are_named_by_the_handler_s_row_that_sends_them_and_show_in_the_frame_it_hands():
    """THE DECLARED DIVERGENCE ON THE REAL STACK, IN A HANDLER'S OWN ROW (ruling W2-R2): where the handler returns the
    ROM's message carries its stack's residue in two places — the manager's buffer and the owner's pipe (the owner
    has not run yet) — and ours four zeroes; AND THE WRITE'S OWN FRAME carries them, so the row that names the class
    holds our door calls to the ROM's read with the C's four zeroes (`the_topped_words_as_the_c_sends_them`) and to
    nothing else. Without the class the row is refused BY THE FRAME our build hands the door; a row that sends
    another message is refused the class."""
    handled = _handled(TOPPED_AT_ONCE)
    assert cm.THE_TOPPED_WORDS in handled.differs
    tier3().at_its_arrival_on(_shipped(), TOPPED_AT_ONCE, handled)
    with pytest.raises(AssertionError, match="our build handed the door"):
        tier3().at_its_arrival_on(_shipped(), "a row", handled._replace(differs=tuple(each for each in handled.differs if each != cm.THE_TOPPED_WORDS)))
    closer = _handled(A_CLICK_ON_THE_CLOSER)
    with pytest.raises(AssertionError, match="a class named and not needed"):
        tier3().at_its_arrival_on(_shipped(), "a row", closer._replace(differs=(*closer.differs, cm.THE_TOPPED_WORDS)))
    write = aes_event.Handed(addrs.AES_ROM_AP_RDWR, (2, 2, aes.AP_MSG_BYTES, struct.pack(">8H", cm.WM_TOPPED, 1, 0, 2, 0xfe, 0xa85a, 0, 2)))
    other = write._replace(arguments=(*write.arguments[:-1], struct.pack(">8H", cm.WM_TOPPED + 1, 1, 0, 2, 0xfe, 0xa85a, 0, 2)))
    as_sent, untouched = tier3().the_topped_words_as_the_c_sends_them([write, other])
    assert as_sent.arguments[-1] == struct.pack(">8H", cm.WM_TOPPED, 1, 0, 2, 0, 0, 0, 0) and untouched == other


def test_a_handler_s_row_s_own_window_it_does_not_need_is_refused():
    """...AND A ROW'S OWN NAMED WINDOW (`also_dropped`: the stale count under a menu worked with the mouse shown) IS
    HELD AS A CLASS IS: on the row that names it the two machines differ there where the handler returns; named by
    a row whose run leaves the same word on both shores it is refused."""
    key = sorted(handlers.THE_MOUSE_SHOWN_AGAIN_LAST & set(handlers.SWITCHING))[0]
    assert handlers.handled(key).row.also_dropped == handlers.THE_STALE_COUNT
    held = _handled(THE_CLOSER_HELD)
    with pytest.raises(AssertionError, match="a window named and not needed excuses a store for nothing"):
        tier3().at_its_arrival_on(_shipped(), "a row", held._replace(row=held.row._replace(also_dropped=handlers.THE_STALE_COUNT)))


def test_who_ran_a_handler_is_asked_and_refuses_a_run_of_the_rom_s_own(monkeypatch):
    """WHO RAN'S CALL, AND ITS ARITHMETIC (`tier3.vet_who_ran_the_handler`): a row measured at its arrival asks it
    once, with our run's cycles in the ROM's own text of the handler — NONE, from the machine's idle on — and in our
    core of it; and the guard, handed a run of ours with one cycle in the ROM's handler, or none in our core, or a
    ROM run with a cycle in the blob, refuses each by name."""
    asked, the_guard = [], tier3().vet_who_ran_the_handler
    monkeypatch.setattr(tier3(), "vet_who_ran_the_handler", lambda who, *held: (asked.append((who, held)), the_guard(who, *held))[1])
    tier3().at_its_arrival_on(_shipped(), A_CLICK_ON_THE_CLOSER, _handled(A_CLICK_ON_THE_CLOSER))
    ((who, (routine, symbol, the_rom_s, ours, in_the_rom_s_windows)),) = asked
    assert (who, routine, symbol) == (A_CLICK_ON_THE_CLOSER, gc.HCTL_WINDOW, routines.core_symbol(gc.HCTL_WINDOW))
    assert ours.so_far.the_rom_s_body == 0 < the_rom_s.spent.the_rom_s_body and ours.spent.our_core > 0 == the_rom_s.so_far.blob
    assert ours.spent.aes == in_the_rom_s_windows == 0
    the_guard(who, routine, symbol, the_rom_s, ours, in_the_rom_s_windows)
    for astray in (dict(ours=ours._replace(so_far=ours.so_far._replace(the_rom_s_body=4))),
                   dict(ours=ours._replace(spent=ours.spent._replace(our_core=0))),
                   dict(the_rom_s=the_rom_s._replace(so_far=the_rom_s.so_far._replace(blob=4))),
                   dict(the_rom_s=the_rom_s._replace(spent=the_rom_s.spent._replace(the_rom_s_body=0))),
                   dict(ours=ours._replace(in_the_rom_s_ctlmgr=4)),
                   dict(in_the_rom_s_windows=8)):
        with pytest.raises(AssertionError, match="WHO RAN"):
            the_guard(who, routine, symbol, **{**dict(the_rom_s=the_rom_s, ours=ours, in_the_rom_s_windows=in_the_rom_s_windows), **astray})


def test_the_callee_saved_registers_are_held_where_our_handler_returns_as_a_kit_call_holds_them(monkeypatch):
    """THE CALLEE-SAVED FILE, ON THE REAL CALLER'S OWN VALUES (`tier3.vet_the_handler_kept_its_caller_s_registers`): a
    row at its arrival asks the guard once, with D2-D7 and A2-A6 as the CPU held them where our ctlmgr called our
    handler and where the handler returned — the kit's eleven, each read at both stops: the caller's own values (our
    hctl_button's, here), not the kit's seeds — and the guard, handed one register
    other at the return, refuses it BY THAT REGISTER'S NAME."""
    asked, the_guard = [], tier3().vet_the_handler_kept_its_caller_s_registers
    monkeypatch.setattr(tier3(), "vet_the_handler_kept_its_caller_s_registers", lambda *held: (asked.append(held), the_guard(*held))[1])
    tier3().at_its_arrival_on(_shipped(), THE_CLOSER_HELD, _handled(THE_CLOSER_HELD))
    ((who, symbol, at_the_arrival, at_the_return),) = asked
    assert (who, symbol) == (THE_CLOSER_HELD, routines.core_symbol(gc.HCTL_WINDOW))
    assert tuple(at_the_arrival) == tuple(at_the_return) == tier3().CALLEE_SAVED == ("d2", "d3", "d4", "d5", "d6", "d7", "a2", "a3", "a4", "a5", "a6")
    assert at_the_arrival == at_the_return and any(at_the_arrival.values())
    for name in tier3().CALLEE_SAVED:
        with pytest.raises(AssertionError, match=f"RETURNED TO ITS CALLER WITH {name} = 0xffffffff, entered with"):
            the_guard(who, symbol, at_the_arrival, {**at_the_return, name: 0xffffffff})


def test_the_rom_s_own_text_of_each_handler_is_the_routine_names_txt_bounds():
    """WHO RAN'S RANGE IS THE ROUTINE (`aes_ctlmgr.the_rom_s_body_of`): from the handler's entry to THE NEXT ROUTINE
    `names.txt` names — ct_msgup to hctl_window, on to hctl_button, hctl_rect, and hctl_rect to ct_chgown (which lies
    before ctlmgr) — the four contiguous, none a word short of its own `rts`."""
    names = (RECREATE.parent / "names.txt").read_text()
    routines_named = sorted(int(address, 16) for address in re.findall(r"^fn (0x[0-9a-f]+) ", names, re.M))
    bodies = [cm.the_rom_s_body_of(routine) for routine in cm.THE_HANDLERS]
    for routine, (lo, hi) in zip(cm.THE_HANDLERS, bodies):
        assert lo == getattr(addrs, routine) and hi == routines_named[routines_named.index(lo) + 1], f"{routine}: [{lo:#x}, {hi:#x})"
    assert all(body[1] == after[0] for body, after in zip(bodies, bodies[1:])) and bodies[-1][1] == addrs.AES_ROM_CT_CHGOWN < addrs.AES_ROM_CTLMGR


def test_two_runs_whose_streams_or_shared_os_differ_are_refused(monkeypatch):
    """TWO HOLDS OF A ROW AT ITS ARRIVAL THAT NO HONEST RUN TRIPS, each made to: THE OFF-IMAGE STREAMS — our run handed
    back with one hardware write more than the ROM's — and THE OS BOTH RUN — its cycles between the arrival and the
    return read one apart — are each refused by name."""
    handled, run = _handled(A_CLICK_ON_THE_CLOSER), tier3()._run_to_its_next_idle
    runs = []

    def one_write_more_on_ours(image, watch, blob):
        ran = run(image, watch, blob)
        runs.append(ran)
        return ran if len(runs) == 1 else ran._replace(streams={**ran.streams, "hw_writes": [*ran.streams["hw_writes"], (0xff8240, 0)]})
    monkeypatch.setattr(tier3(), "_run_to_its_next_idle", one_write_more_on_ours)
    with pytest.raises(AssertionError, match="the two runs' off-image streams or odd accesses differ"):
        tier3().at_its_arrival_on(_shipped(), "a row", handled)
    monkeypatch.setattr(tier3(), "_run_to_its_next_idle", run)
    shared = tier3().shared_cycles
    monkeypatch.setattr(tier3(), "shared_cycles", lambda measured: (shared(measured)[0] + 1, shared(measured)[1]))
    with pytest.raises(AssertionError, match="the OS both sides run cost ours \\d+ cycles and the ROM's \\d+ between the arrival and the return"):
        tier3().at_its_arrival_on(_shipped(), "a row", handled)


def test_a_window_left_out_at_the_stops_alone_that_no_stop_needs_is_refused():
    """`Handled.at_stops_only` IS NEEDED AT A STOP, OR REFUSED: the stale count named so on the closer held — whose run
    works no menu, so both shores hold one word there at every stop — is refused by name; on the one case that names
    it (the menu left by a press HELD: the word differs between the menu's re-show and the rise's own VDI call) the
    two shores do differ there at a stop (that case's own run, above, passes with it and is red without)."""
    held = _handled(THE_CLOSER_HELD)
    with pytest.raises(AssertionError, match="a window named and not needed hides a page for nothing"):
        tier3().at_its_arrival_on(_shipped(), "a row", held._replace(at_stops_only=handlers.THE_STALE_COUNT))
    needs, = handlers.THE_STALE_COUNT_IS_OVERWRITTEN
    overwritten = handlers.handled(needs)
    assert overwritten.at_stops_only == handlers.THE_STALE_COUNT
    with pytest.raises(AssertionError, match="of the dispatcher's watch OUR IMAGE IS NOT THE ROM'S"):
        tier3().at_its_arrival_on(_shipped(), "a row", overwritten._replace(at_stops_only=()))


def test_the_cases_held_at_their_arrival_and_pinned_nowhere_are_the_ones_status_counts():
    """THE TIER 1-ONLY CASES RUN THROUGH THEIR HANDLER AT OUR ARRIVALS, counted off the registries and held to what the
    ledger says: every arrival this battery measures at that is no row of the table."""
    unpinned = [key for name, key in ARRIVALS.items() if name not in cm.HANDLED]
    assert sorted(unpinned) == sorted(key for key in handlers.UNPRICED if key[0] != INLINED_INTO_ITS_CALLERS)
    by_handler = {routine: sum(key[0] == routine for key in unpinned) for routine in {key[0] for key in unpinned}}
    status = THE_LEDGER_S_ARCHIVE.read_text()
    said = re.findall(r"THE (\d+) TIER 1-ONLY CASES of those handlers \(hctl_window's (\d+), hctl_rect's (\d+)\)", status)
    assert said == [(str(len(unpinned)), str(by_handler[gc.HCTL_WINDOW]), str(by_handler[gc.HCTL_RECT]))], (said, by_handler)
    assert len(ARRIVALS) == len(cm.HANDLED) + len(unpinned) and set(by_handler) == {gc.HCTL_WINDOW, gc.HCTL_RECT}


def test_a_handler_whose_run_does_not_return_to_its_caller_is_refused_by_name():
    """THE SLICE ENDS WHERE THE HANDLER RETURNS, or the row is refused: a handler that switches, asked for as one that
    takes no delivery (the release never comes), idles where no delivery is named — refused there by the handler's
    own watch, not run to a budget."""
    held = _handled(THE_CLOSER_HELD)
    with pytest.raises(switching.Refused, match="the dispatcher idles once more than the ROM's own run did"):
        tier3().at_its_arrival_on(_shipped(), "a row", held._replace(row=None))


def test_who_ran_is_asked_of_a_row_of_ctlmgr_s_own(monkeypatch):
    """WHO RAN'S CALL, not its arithmetic alone (`test_aes_takeover.py` refuses that each way): a row from idle to idle
    asks `vet_who_ran` once, with OUR run's cycles in the ROM's ctlmgr — none — and in our entry. On an honest run the
    guard is silent whether asked or not (the windows' own rules imply it), so its being asked is held by itself."""
    asked, the_guard = [], tier3().vet_who_ran
    monkeypatch.setattr(tier3(), "vet_who_ran", lambda who, rom, ours, *held: (asked.append((who, rom, ours)), the_guard(who, rom, ours, *held))[1])
    label = next(iter(WOKEN))
    tier3().idle_to_idle_on(_shipped(), _name(label), WOKEN[label])
    ((who, rom, ours),) = asked
    assert who == _name(label) and ours.in_the_rom_s_ctlmgr == 0 < rom.in_the_rom_s_ctlmgr and ours.in_our_entry > 0


# ---- BEHIND OUR DOOR (the narrow door flip, band 5 wave 3): the guards the accessory machines' rows stand on ----------------
THE_OS_S_OWN_PROCESSES = 2              # the screen manager's PD and the desk's: every PD past them is a loaded program's


def test_every_row_from_an_idle_runs_behind_our_door__the_desk_s_own_machine_s_too():
    """WHICH MACHINE OUR SHORE'S RUNS START FROM (`aes_ctlmgr.our_machine`): THE DOOR MACHINE, for every machine —
    vector `$88` and `$404` the blob's own handlers, and every other longword the door maps the blob's own routine
    (the full flip: justretf's slot, the tick glue's two, the trampoline's, the VDI's button and motion vectors);
    every loaded program taken (its stack span handed the watches) — and, since band 6's binding, THE DESK beside them
    (PD0's stack handed the watches too: it parks through our dispatcher). EVERY MACHINE stands in OUR dispatcher's
    idle where the ROM-booted one stands in the ROM's — THE DESK'S OWN MACHINE too since the binding (it loads no
    program, so its door is vectors alone; its desk calls our AES through our table)."""
    blob = _shipped()
    for key in (gc.THE_DESK, A, W, gc.HIDING):
        woken = types.SimpleNamespace(machine=key)
        ours, programs = make_image({0: cm.our_machine(woken, blob)}), cm.our_machine_s_programs(woken, blob)
        assert tier3().behind_our_door(ours, blob) and programs[-1][0] == aes.SHELL_PD and (len(programs) > 1) == (key != gc.THE_DESK)
        handler, critic = (case.long_in(ours, at) for at in (addrs.VECTOR_TRAP_GEM, aes_event.ETV_CRITIC))
        assert (handler, critic) == (blob.entry("aes_rom_trap2"), blob.entry("aes_rom_crit_err"))
        rom_s = gc.machine(key)
        for part in aes_event.THE_DOOR:
            for slot in aes_event.THE_MACHINE_S_VECTORS.get(part.what, ()):
                assert part.symbols[rom_s.long(slot)] and case.long_in(ours, slot) == blob.entry(part.symbols[rom_s.long(slot)]), f"{slot:#x}"
        if key != gc.THE_DESK:          # (the desk's own machine: the spare static PD has its UDA and no program)
            assert [pd for pd, _stack in programs[:-1]] == [pd for pd in aes_event.processes_of(ours)[THE_OS_S_OWN_PROCESSES:]
                                                            if case.long_in(ours, pd + aes.PD_UDA)]
        assert cm._taken(key, blob).idle == aes_boot.OURS and rom_s.idle == aes_boot.THE_ROM_S


def test_the_desk_s_machine_behind_the_door_is_wave_2_s_takeover_but_for_the_longwords_the_door_maps(blob):
    """RULING W4-R10, HELD: the desk's own machine behind THE DOOR is wave 2's takeover machine — the same boot, the
    same stop — BUT FOR THE NINE LONGWORDS THE DOOR MAPS (no program is loaded: no frame), each the ROM's routine
    there and the blob's own here — AND, SINCE BAND 6's BINDING (the ninth longword: the handler copy's table), BUT
    FOR WHAT THE DESK'S RUN OVER OUR AES TO THE IDLE LEAVES BY NATURE (`aes_ctlmgr.the_bound_desk_s_classes`, and our
    dispatcher's idle where wave 2's machine stands in the ROM's: its stack, the save frame, the mask word). The door's
    who-ran says our `trap #2` handler ran from the lay on (the desk's own VDI calls) and no ROM text of any part did."""
    built = blob
    wave_2_s, behind = aes_boot.desk_machine(ours=built), cm._taken(gc.THE_DESK, built)
    mapped = behind.door.vectors
    assert set(mapped) == {slot for part in aes_event.THE_DOOR for slot in aes_event.THE_MACHINE_S_VECTORS.get(part.what, ())} and len(mapped) == 9
    assert behind.door.programs == () and wave_2_s.door is None and (behind.idle, wave_2_s.idle) == (aes_boot.OURS, aes_boot.THE_ROM_S)
    rom = gc.machine(gc.THE_DESK)
    _classes, two_idles = aes_boot.by_nature(rom, behind)
    by_nature = [*cm.the_bound_desk_s_classes(rom, behind).values(), *two_idles.values(), aes_event.DISPATCHER_STACK]
    differing = aes_boot.differing_runs(wave_2_s.ram, behind.ram)
    mapped_or_by_nature = {at for slot in mapped for at in range(slot, slot + aes.LONG_BYTES)} | {
        at for lo, hi in by_nature for at in range(lo, hi)}
    assert {at for at, length in differing for at in range(at, at + length)} <= mapped_or_by_nature
    for slot, (the_rom_s, ours) in mapped.items():
        assert (wave_2_s.long(slot), behind.long(slot)) == (the_rom_s, ours) and built.base <= ours < built.end
    ran = behind.door.ran
    assert all(in_the_rom_s == 0 for _ours, in_the_rom_s in ran.values()) and ran[aes_event.GEM_TRAP_VECTOR.what][0] > 0


def test_who_ran_the_door_reads_the_rom_s_text_of_every_part_of_the_door():
    """`tier3.THE_ROM_S_DOOR` — what a run behind our door executes NOT ONE CYCLE of — IS THE ROM'S TEXT OF EVERY PART
    OF THE DOOR, spelt here by the ROM's own addresses: the trap handler past its selector switch with its way out,
    aes_entry, gotopgm, crit_err — AND, SINCE THE FULL FLIP, justretf, the tick glue, the desk's trampoline, the
    button and motion glues. (No Tier 3 row takes an interrupt through the VDI's vectors — a row's deliveries are
    laid — so a who-ran blind to the glue's text would be missed by no row: it is held here, and the glue's run by
    the continuations of `test_aes_boot_w4.py`.) Each span once, none over the selector switch."""
    spans = tier3().THE_ROM_S_DOOR
    assert len(spans) == len(set(spans)) and set(spans) == {
        (addrs.GEM_TRAP2_PTERM_ARM, addrs.AES_ROM_UB_TRAMPOLINE), (addrs.AES_ROM_ENTRY, addrs.AES_ROM_AP_RDWR),
        (addrs.AES_ROM_GOTOPGM, addrs.AES_ROM_SAVESTATE), (addrs.AES_ROM_CRIT_ERR, addrs.AES_ROM_DOS_EXEC),
        (addrs.AES_ROM_JUSTRETF, addrs.AES_ROM_TICK_GLUE), (addrs.AES_ROM_TICK_GLUE, addrs.AES_ROM_CART_INIT),
        (addrs.AES_ROM_UB_TRAMPOLINE, addrs.AES_ROM_SIGNAL),
        (addrs.AES_ROM_BUTTON_GLUE, addrs.AES_ROM_MOTION_GLUE), (addrs.AES_ROM_MOTION_GLUE, addrs.AES_ROM_DRAWRAT)}
    selector_lo, selector_hi = tier3().GEM_SELECTOR_SWITCH
    assert not any(lo < selector_hi and selector_lo < hi for lo, hi in spans), "the selector switch: both shores run it from the same bytes"
    assert all(aes.AES_TEXT[0] <= lo < hi <= aes.AES_TEXT[1] for lo, hi in spans)


def test_who_ran_the_door_is_refused_each_way_on_two_runs_counted_by_hand():
    """`tier3.vet_who_ran_the_door`'s OWN ARITHMETIC, over stand-in runs. BEHIND OUR DOOR: our run not one cycle in the
    ROM's door nor in its selector switch, the ROM's none in ours, and the two selector switches the same cycles —
    each refused by name. ON A MACHINE WITH NO DOOR: REFUSED, whatever the counts (the full flip: `$88` is the
    build's at every run's entry — a row from an idle runs over a machine that holds it as it stands)."""
    ran = lambda **counted: types.SimpleNamespace(**{"in_the_rom_s_door": 0, "in_the_rom_s_selector": 0, "in_our_selector": 0, **counted})   # noqa: E731
    rom, ours = ran(in_the_rom_s_door=1450, in_the_rom_s_selector=920), ran(in_our_selector=920)
    vet = tier3().vet_who_ran_the_door
    vet("a row", rom, ours, True)
    for astray, refused in ((dict(in_the_rom_s_door=636), "BEHIND OUR DOOR our run spent 636 cycles in the ROM's own trap door"),
                            (dict(in_the_rom_s_selector=92), "and 92 in its\\s+selector switch"),
                            (dict(in_our_selector=828), "cost our run\\s+828 cycles in ours and the ROM's 920 in its own")):
        with pytest.raises(AssertionError, match=refused):
            vet("a row", rom, types.SimpleNamespace(**{**vars(ours), **astray}), True)
    with pytest.raises(AssertionError, match="the ROM's run spent 74 cycles in OUR selector switch"):
        vet("a row", types.SimpleNamespace(**{**vars(rom), "in_our_selector": 74}), ours, True)
    for no_door in (ran(in_the_rom_s_selector=920), ours):
        with pytest.raises(AssertionError, match="A ROW FROM AN IDLE ON A MACHINE WITH NO DOOR OF OURS: its `\\$88` is the ROM's"):
            vet("a row", rom, no_door, False)


@pytest.mark.parametrize("label", (THE_CLOSER, THE_BAR), ids=("a machine with accessories", "the desk's own machine"))
def test_who_ran_the_door_is_asked_of_both_kinds_of_row_and_reads_real_cycles(label, monkeypatch):
    """ITS CALL, held by itself (the guard is silent on honest numbers): a row of ctlmgr's own and a handler's row
    each ask it once, BEHIND OUR DOOR ON EVERY MACHINE (the desk's own too, since the full flip) — our selector
    switch's cycles equal to the ROM's own and both above zero, our run none in the ROM's switch nor in the ROM's
    text of any part of the door; and the ROM's run spent some in its door exactly where a program traps into the
    AES (an accessory's own traps: none on the desk's machine, whose desk calls the AES by Line-F)."""
    asked, the_guard = [], tier3().vet_who_ran_the_door
    monkeypatch.setattr(tier3(), "vet_who_ran_the_door", lambda who, rom, ours, door: (asked.append((rom, ours, door)), the_guard(who, rom, ours, door))[1])
    tier3().idle_to_idle_on(_shipped(), _name(label), WOKEN[label])
    held = _handled(THE_ARROW_HELD if label == THE_CLOSER else THE_DESK_S_OWN_ITEM)
    tier3().at_its_arrival_on(_shipped(), "a row", held)
    assert len(asked) == 2
    for rom, ours, door in asked:
        assert door
        assert ours.in_our_selector == rom.in_the_rom_s_selector > 0 == ours.in_the_rom_s_selector == ours.in_the_rom_s_door
        assert (rom.in_the_rom_s_door > 0) == (label == THE_CLOSER), "the accessory's own AES traps: the ROM's door on the ROM's shore"


def test_a_loaded_program_s_spans_are_held_by_content_wherever_it_does_not_run():
    """`aes_switching.Switching`'s HOLD OF EVERY LOADED PROGRAM'S SAVED CONTEXT AND STACK behind our door, on its own
    inputs: over the door machine at its idle (every program parked) the spans are kept; a byte of a program's stack
    or of its saved context changed by anybody else is REFUSED BY NAME where the run ends and where that program is
    next resumed — but the SR word of its `rte` frame, the dispatcher's own, where it is resumed."""
    blob, woken = _shipped(), WOKEN[THE_CLOSER]
    programs = cm.our_machine_s_programs(woken, blob)
    (first, (lo, top)), *_others = programs

    def watching():
        memory = make_image({0: cm.our_machine(woken, blob)})
        watch = switching.IdleToIdle(cm.made(woken).switches, ours=switching.our_dispatcher(blob), takeover=True, door=True,
                                     programs=programs)
        watch._hold_the_programs_spans(memory)
        return memory, watch
    memory, watch = watching()
    assert set(watch._programs_stood) == {pd for pd, _stack in programs}
    watch.vet_the_programs_spans_stood(memory, "where the run ends")
    parked = case.long_in(memory, aes_event.uda_of(first, memory) + aes.UDA_SUPER_SP) & aes.OS_BUS_ADDR_MASK
    assert lo < parked < top
    for at in (top - 1, lo, aes_event.uda_of(first, memory) + aes.UDA_REGS):
        memory, watch = watching()
        memory[at] ^= 0xFF
        with pytest.raises(switching.Refused, match=rf"THE SAVED CONTEXT OR THE STACK OF THE PROGRAM AT {first:#x} HOLDS OTHER BYTES"):
            watch.vet_the_programs_spans_stood(memory, "where the run ends")
    memory, watch = watching()
    memory[parked] ^= 0xFF              # ...the `rte` frame's SR word: the dispatcher's, where the program is resumed
    watch._entering = first
    watch._a_program_resumed(memory)
    assert first not in watch._programs_stood
    memory, watch = watching()
    memory[parked + aes.WORD_BYTES] ^= 0xFF
    watch._entering = first
    with pytest.raises(switching.Refused, match=rf"where the program at {first:#x} is resumed"):
        watch._a_program_resumed(memory)


def test_an_accessory_s_turn_over_the_bar_is_over_whatever_the_row_s_own_counts():
    """RULING W3-R3, HELD: an accessory's turn is priced BY ITSELF — the row's measurement with its accessory's turn
    made dearer, past the bar with its thunks, is OVER by the table's own rule, the row's own ratio untouched; and
    its line says whose turn it is."""
    row = next(row for row in tier3().ROWS if tier3().is_a_woken_row(row) and row.case == THE_CLOSER)
    measured = tier3().idle_to_idle_on(_shipped(), _name(THE_CLOSER), WOKEN[THE_CLOSER])
    (turn,), bar = measured.turns, tier3().TIER3_FUNCTION_BAR
    assert turn.whose == switching.AN_ACCESSORY_S and all(each.whose == switching.THE_MANAGER_S for each in measured.its_turns)
    assert tier3().turns_within_bar(measured) and tier3()._turn_lines(measured, 0)[0].lstrip().startswith("an accessory's turn: ours ")
    no_other = lambda *_asked: pytest.fail("the verdict of a row through the OS asks no other row's measurement")   # noqa: E731
    assert tier3().verdict(row, measured, 0, no_other) in ("net", "pinned")
    measured.turns = (turn._replace(glue=int(turn.the_rom_s * bar) - turn.ours + 1),)
    assert not tier3().turns_within_bar(measured) and tier3().verdict(row, measured, 0, no_other) == "OVER"
    assert "OVER THE BAR BY ITSELF" in tier3()._turn_lines(measured, 0)[0]


# ---- THE BIOS'S SAVE FRAME: ITS REGISTERS DIFFER BY NATURE, ITS PC AND SR DO NOT (FLIP 4's review) ----------------------------
def test_the_save_frame_s_class_is_its_ten_registers_and_a_saved_pc_or_sr_that_differs_is_refused():
    """THE CLASS IS NO WIDER THAN WHAT DIFFERS BY NATURE (`tier3.the_trap_save_s_registers`): the forty bytes of D3-D7
    and A3-A7 under the booted machine's savptr — and the saved PC and SR above them are COMPARED: two machines that
    differ in a saved register pass with the class named; with the saved SR other, or the saved PC, they are refused
    by the bytes, the class named or not (a class two bytes wider would have hidden the first: the review's mutant)."""
    its = bytearray(gc.machine(gc.THE_DESK).ram)
    top = case.long_in(its, addrs.SYSVAR_SAVPTR) & aes.OS_BUS_ADDR_MASK
    lo, hi = tier3().the_trap_save_s_registers(its)
    assert (lo, hi) == (top - addrs.TRAP_SAVE_FRAME_BYTES, top - aes.LONG_BYTES - aes.WORD_BYTES) and hi - lo == 40

    def held(at, named):
        other = bytearray(its)
        other[at] ^= 1
        ran = lambda memory: types.SimpleNamespace(memory=memory)   # noqa: E731
        tier3().vet_the_machines_where_the_runs_end("a row", _shipped(), ran(its), ran(other), named)
    held(hi - 1, (cm.THE_TRAP_SAVE,))                               # the last byte of the saved A7: the class's
    for at in (hi, top - 1):                                        # the saved PC's first byte, the saved SR's last
        for named in ((cm.THE_TRAP_SAVE,), ()):
            with pytest.raises(AssertionError, match="OUR MACHINE IS NOT THE ROM'S outside the classes the row names"):
                held(at, named)
    with pytest.raises(AssertionError, match="OUR MACHINE IS NOT THE ROM'S outside the classes the row names"):
        held(hi - 1, ())


def test_the_booted_machine_s_save_frame_is_left_out_at_the_stops_only_where_the_snapshot_s_is_another(monkeypatch):
    """THE STOP-LEVEL LEAVE-OUT OF THE SAVE FRAME IS THE OTHER SNAPSHOT PHASE'S (`_IdleStopImages`): the booted
    machines' savptr is `$93a`, and every page already leaves out the frame under THE SNAPSHOT'S savptr — the same
    frame on a capture set taken at `$93a` (nothing is named: no window), another on one taken at `$90c`, where the
    booted machine's frame must be named or the image at the first stop after the screen manager's BIOS trap is two
    builds' registers. Held on whichever phase this tree's captures are: no window where the two are one frame; and,
    where they are two, the row red at a stop without it."""
    booted = gc.machine(gc.THE_DESK).ram
    frame = gc.its_trap_save(booted)[:2]
    named = gc.its_trap_save_beside_the_snapshot_s(booted)
    assert frame[1] == 0x93a and bool(named) == (frame != aes_event.THE_POLL_S_TRAP_SAVE)
    if not named:
        return
    monkeypatch.setattr(gc, "its_trap_save_beside_the_snapshot_s", lambda _ram: ())
    with pytest.raises(AssertionError, match="OUR IMAGE IS NOT THE ROM'S"):
        tier3().idle_to_idle_on(_shipped(), _name(THE_BAR), WOKEN[THE_BAR])


# ---- THE FIX PASS OF THE NARROW DOOR FLIP: holds its two reviews found asked of nothing ---------------------------------------
def _stood_in(memory):
    """A run, as `vet_the_machines_where_the_runs_end` reads one: its memory."""
    return types.SimpleNamespace(memory=memory)


def test_a_loaded_program_s_span_that_holds_the_rom_s_own_bytes_where_the_runs_end_is_refused():
    """EACH PROGRAM'S SAVED CONTEXT AND STACK ARE REQUIRED TO DIFFER (review mutant A5: the requirement taken out,
    everything passed). Over two copies of the ROM-booted machine — a door machine whose accessories were the ROM's
    after all — every span is equal and the vet refuses by name; and with every span but one given another byte, it
    refuses still and names THAT span: the requirement is per span, not "some span differs"."""
    blob, woken = _shipped(), WOKEN[THE_CLOSER]
    programs = cm.our_machine_s_programs(woken, blob)
    its = bytearray(cm.the_rom_s_machine(woken))
    windows = [window for program in programs for window in tier3().program_windows(its, program)]
    assert len(windows) == 2 * len(programs) == 6         # (two accessories, and the desk since band 6's binding)
    with pytest.raises(AssertionError, match="BEHIND OUR DOOR A LOADED PROGRAM'S SPAN HOLDS THE ROM'S OWN BYTES"):
        tier3().vet_the_machines_where_the_runs_end("a row", blob, _stood_in(its), _stood_in(bytearray(its)), (), programs=programs)
    for equal_lo, equal_hi, _why in windows:
        other = bytearray(its)
        for lo, _hi, _why in windows:
            if lo != equal_lo:
                other[lo] ^= aes.BYTE_MASK
        with pytest.raises(AssertionError, match=rf"HOLDS THE ROM'S OWN BYTES where the runs end — \('{equal_lo:#x}', '{equal_hi:#x}'"):
            tier3().vet_the_machines_where_the_runs_end("a row", blob, _stood_in(its), _stood_in(other), (), programs=programs)


def _parameter(memory, evb):
    return case.long_in(memory, evb + aes.EVB_PARM) & aes.OS_BUS_ADDR_MASK


def test_a_parked_address_is_named_only_where_it_names_a_place_of_a_program_s_own_stack():
    """`tier3.parked_addresses_named`'s BOUND (review mutant B13: every EVB's parameter rewritten on both shores
    before every compare — a compare that hides — passed). OVER THE DOOR MACHINE AS IT IDLES: an EVB whose parameter
    names a place inside a loaded program's stack (the machine has some: each accessory's message wait keeps its
    QPB's address) is given that stack's top, and EVERY OTHER EVB'S PARAMETER IS LEFT AS IT STANDS — nothing else of
    the megabyte moves. AT THE BOUND'S EDGES, over stand-in values laid in one EVB that names no such place (the
    function's own arithmetic, labelled): the stack's first byte and its last are inside, the byte under it and its
    top are not."""
    blob, woken = _shipped(), WOKEN[THE_CLOSER]
    programs = cm.our_machine_s_programs(woken, blob)
    ram = bytearray(cm.our_machine(woken, blob))
    evbs = tier3().every_evb_of(ram)
    top_of = {evb: top for evb in evbs for _pd, (lo, top) in programs if lo <= _parameter(ram, evb) < top}
    assert top_of and len(top_of) < len(evbs), "the machine holds EVBs of both kinds"
    named = tier3().parked_addresses_named(bytearray(ram), programs)
    assert {evb: _parameter(named, evb) for evb in evbs} == {evb: top_of.get(evb, _parameter(ram, evb)) for evb in evbs}
    slots = {at for evb in top_of for at in range(evb + aes.EVB_PARM, evb + aes.EVB_PARM + aes.LONG_BYTES)}
    assert all(named[at] == ram[at] for at in range(len(ram)) if at not in slots), "and nothing else of the megabyte"
    assert tier3().parked_addresses_named(bytearray(ram), ()) == ram, "no program: no door, nothing named"
    spare = next(evb for evb in evbs if evb not in top_of)
    lowest, highest = min(stack for _pd, stack in programs), max(stack for _pd, stack in programs)
    for held, becomes in ((lowest[0], lowest[1]), (highest[1] - 1, highest[1]), (lowest[0] - 1, lowest[0] - 1), (highest[1], highest[1])):
        staged = bytearray(ram)
        staged[spare + aes.EVB_PARM:spare + aes.EVB_PARM + aes.LONG_BYTES] = held.to_bytes(aes.LONG_BYTES, "big")
        assert _parameter(tier3().parked_addresses_named(staged, programs), spare) == becomes, f"{held:#x}"


def _the_rom_s_handler_stored_back_in_our_run(monkeypatch):
    """Every pair of runs from an idle with OUR run's machine handed back holding THE ROM'S trap handler in `$88` — A
    STAND-IN STORE, labelled: what a retake of the ROM's inside the run would leave (no accessory mode calls one)."""
    run, runs = tier3()._run_to_its_next_idle, []

    def taken_back(image, watch, blob):
        ran = run(image, watch, blob)
        runs.append(ran)
        if len(runs) % 2 == 0:          # the ROM's run first, then ours
            image[addrs.VECTOR_TRAP_GEM:addrs.VECTOR_TRAP_GEM + aes.LONG_BYTES] = addrs.GEM_TRAP2.to_bytes(aes.LONG_BYTES, "big")
        return ran
    monkeypatch.setattr(tier3(), "_run_to_its_next_idle", taken_back)


def test_a_door_the_rom_took_back_inside_a_row_s_run_is_refused_by_the_registry_s_vet(monkeypatch):
    """A DOOR TAKEN BACK INSIDE A TIER 3 RUN (STATUS, slice F (f); review mutant A7 — every ROM address let travel —
    passed): the door machine came with OUR handler in `$88`, so the ROM's `$fe3ea6` there where our run ends is a
    STORE, and the registry's vet refuses it by name — on a row of ctlmgr's own and on a handler's row."""
    _the_rom_s_handler_stored_back_in_our_run(monkeypatch)
    refused = rf"OUR run left THE ROM'S OWN address {addrs.GEM_TRAP2:#x} in {re.escape(aes_event.GEM_TRAP_VECTOR.what)}"
    with pytest.raises(AssertionError, match=refused):
        tier3().idle_to_idle_on(_shipped(), _name(THE_CLOSER), WOKEN[THE_CLOSER])
    with pytest.raises(AssertionError, match=refused):
        tier3().at_its_arrival_on(_shipped(), "a row", _handled(THE_ARROW_HELD))


A_STRAY_CYCLE_COUNT = 4                 # one `nop` of our build's, run outside every turn: the stand-in below


def test_who_ran_is_handed_the_turns_own_cycles__a_cycle_of_ours_outside_every_turn_is_refused(monkeypatch):
    """WHO RAN'S THIRD RULE AT ITS CALL — "every cycle of our build is one of the turns of ours" — is handed THE SUM OF
    THE TURNS (review mutant A10: handed the build's own total, a tautology, it passed this battery and the
    takeover's). A STAND-IN, labelled: the run's turns as they are but the first four cycles short, as if our build
    had run four cycles outside every window — refused by name, by that rule."""
    made = tier3().turns_made

    def four_cycles_outside_every_turn(*watches):
        first, *others = made(*watches)
        return (first._replace(ours=first.ours - A_STRAY_CYCLE_COUNT), *others)
    monkeypatch.setattr(tier3(), "turns_made", four_cycles_outside_every_turn)
    with pytest.raises(AssertionError, match=r"our build ran (\d+) cycles and the turns of ours hold \d+") as refused:
        tier3().idle_to_idle_on(_shipped(), _name(THE_CLOSER), WOKEN[THE_CLOSER])
    ran, held = (int(count) for count in re.findall(r"\d+", str(refused.value).split("our build ran")[1])[:2])
    assert ran - held == A_STRAY_CYCLE_COUNT


WITH_AN_ACCESSORY_S_TURN = sorted(aes_accessory_turns_pinned.PINNED)
# (`test_status.BENCH_TABLE`'s file, spelt here: importing that module would hand this battery out behind the registry —
# `test_derived.py`, "fewest imports first".)
THE_TABLE_S_FILE = RECREATE / "build" / "bench" / "tier3.txt"


def test_the_rows_with_an_accessory_s_turn_are_seven_and_hold_eight():
    assert len(WITH_AN_ACCESSORY_S_TURN) == 7
    assert sum(len(by_blob[SHIPPED]) for by_blob in aes_accessory_turns_pinned.PINNED.values()) == 8
    assert {_name(label) for label, turns in THE_ACCESSORIES_TURNS.items() if turns} | {THE_ARROW_HELD} == set(WITH_AN_ACCESSORY_S_TURN)


@pytest.mark.parametrize("registered", WITH_AN_ACCESSORY_S_TURN)
def test_the_figure_net_of_the_line_f_handler_beside_an_accessory_s_turn_is_made_of_its_own_tallies(registered):
    """THE FIGURE THE LINE PRINTS BESIDE A TURN (`tier3._line_f_of`; review mutant B11 — the convention's ratio printed
    in its place — passed 4,132 tests): derived HERE from the measured turn's own four tallies, never from the line —
    our build's own cycles and its thunks' over the ROM's AES subtree LESS its Line-F handler's RAM copy — for each of
    the eight accessory turns as the table measures them (the shipped blob), and the table's file says that line."""
    row, = (row for row in tier3().ROWS if row.registered == registered)
    measured = tier3().measure(row, tier3().RomBench())
    turns = tier3().the_accessories_turns(tier3().turns_of(measured))
    assert tuple((turn.ours, turn.the_rom_s, turn.glue) for turn in turns) == switching.accessory_turns_pinned(registered, SHIPPED) != ()
    lines = [line for line in tier3()._turn_lines(measured, 0) if line.lstrip().startswith("an accessory's turn: ")]
    table = {line.strip() for line in THE_TABLE_S_FILE.read_text().splitlines()}
    for turn, line in zip(turns, lines, strict=True):
        assert 0 < turn.line_f < turn.the_rom_s and turn.glue > 0
        net_of_the_handler = (turn.ours + turn.glue) / (turn.the_rom_s - turn.line_f)
        assert line.endswith(f"; the ROM's Line-F handler alone is {turn.line_f} of its {turn.the_rom_s} "
                             f"({turn.line_f / turn.the_rom_s:.0%}): net of it {net_of_the_handler:.2f}"), line
        assert f"= {turn.ours / turn.the_rom_s:.2f} — " in line and f"{(turn.ours + turn.glue) / turn.the_rom_s:.2f} with them" in line
        assert net_of_the_handler > (turn.ours + turn.glue) / turn.the_rom_s, "another figure than the convention's"
        assert line.strip() in table, f"{THE_TABLE_S_FILE} does not say this line: run `make bench`"


# ---- band 6 slice B0's fix pass (reviewer A's F1): THE DESK'S LIVE FRAMES ------------------------------------------------------
THE_FOUR_MACHINES = (gc.THE_DESK, A, W, gc.HIDING)


def test_the_desk_s_live_frames_differ_at_the_takeover_in_dead_bytes_alone_and_are_laid_as_the_rom_s():
    """THE MEASURED REASON PD0's CLASS STAYS THE WHOLE STACK (`aes_ctlmgr`'s note), on each machine behind the door: the
    desk's live frames — from its lowest ROM frame to UDA0's top — DIFFER from the ROM-booted machine's (dead locals),
    the frame chain through them THE SAME (every link and return); the staging a row's runs are entered with lays
    them, and the two are then one."""
    blob = _shipped()
    for key in THE_FOUR_MACHINES:
        rom, ours = gc.machine(key).ram, bytearray(cm.our_machine(types.SimpleNamespace(machine=key), blob))
        lo, top = cm.the_desk_s_live_frames(rom)
        assert aes.AES_THEGLO < lo < top == aes.AES_UDA1 and ours[lo:top] != rom[lo:top], key
        assert cm.lay_the_desk_s_live_frames(ours, rom) > 0 and ours[lo:top] == rom[lo:top], key


def test_the_lay_refuses_a_desk_standing_in_other_frames():
    """THE STAGING LAYS DEAD BYTES ALONE: our machine's desk with a return of its frame chain changed is refused."""
    rom = gc.machine(gc.THE_DESK).ram
    ours = bytearray(cm.our_machine(types.SimpleNamespace(machine=gc.THE_DESK), _shipped()))
    lo, _top = cm.the_desk_s_live_frames(rom)
    ours[lo:lo + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)        # (the return slot of the call the desk is parked under)
    with pytest.raises(AssertionError, match="the desk's frame chain on our machine is not the ROM's"):
        cm.lay_the_desk_s_live_frames(ours, rom)


def test_where_the_runs_end_a_byte_of_the_desk_s_live_frames_is_compared():
    """`tier3.vet_the_desk_s_live_frames`, read by hand: two runs ending on the ROM-booted desk's machine pass; one byte
    of a desk's local changed on ours is refused by name — and nothing is asked of a machine whose desk is no process
    of ours."""
    blob, rom = _shipped(), gc.machine(gc.THE_DESK).ram
    programs = ((aes.SHELL_PD, cm.the_desk_s_stack(gc.machine(gc.THE_DESK))),)
    lo, top = cm.the_desk_s_live_frames(rom)
    tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(bytearray(rom)), programs)
    other = bytearray(rom)
    other[top - 1] ^= 1
    with pytest.raises(AssertionError, match=r"THE DESK'S LIVE FRAMES .* ARE NOT THE ROM'S — 1 byte"):
        tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(other), programs)
    tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(other), ())


# ---- band 6 slice H2: THE DESK'S LIVE FRAMES UNDER A FLIPPED evnt_multi BINDING (it flips at F2c) -----------------------------------
# (a) THE STAGING TAUGHT: the desk's own frames begin at the first frame whose return lies in desk text STILL THE ROM'S on
# the blob (`aes_ctlmgr.the_desk_s_text`) — under a flipped binding, at its caller's call. (b) THE ROM'S BINDING'S RESIDUE:
# the out words it copies from answer words no store of its run reached (`aes_ctlmgr.ResidueCopies`), the one class by
# nature of the live frames, read off each run — excused only where BOTH runs copied residue there and each run's end
# still holds what it copied (the RH2 review's narrowing). evnt_multi is held until F2c: each piece is held here over today's
# machines and rows — the binding's state laid, where a test needs it, by the flipped set alone (`aes_desk.flipped`).
def _the_binding_laid(monkeypatch, flipped):
    """`aes_desk.flipped` as the blob's own, with evnt_multi's binding in it (`flipped`) or out of it."""
    as_built = aes_desk.flipped
    monkeypatch.setattr(aes_desk, "flipped", lambda blob=None: as_built(blob) - {cm.EVNT_MULTI_BINDING}
                        | ({cm.EVNT_MULTI_BINDING} if flipped else set()))


def _the_binding_s_text():
    starts = aes_desk.inventoried()
    return range(cm.EVNT_MULTI_BINDING, starts[starts.index(cm.EVNT_MULTI_BINDING) + 1])


def test_under_a_flipped_binding_the_desk_s_frames_begin_at_its_caller_s_call(monkeypatch):
    """ON THE DESK'S MACHINE, PARKED IN evnt_multi's BINDING: while the binding is the ROM's, the desk's own frames begin
    at the AES's frame under it (its return into the binding); FLIPPED, at THE BINDING'S OWN FRAME — the one the AES's
    links to, its return into deskmain's call — so the binding's frame is below the live frames, its build's own by
    nature as the AES's is. The staging over the flipped set lays from there, and refuses a changed return as before."""
    blob, rom = _shipped(), gc.machine(gc.THE_DESK).ram
    ours = bytearray(cm.our_machine(types.SimpleNamespace(machine=gc.THE_DESK), blob))
    _the_binding_laid(monkeypatch, flipped=False)
    (held_lowest, *_), _top = cm._the_desk_s_frames(rom, blob)
    assert case.long_in(rom, held_lowest + aes.LONG_BYTES) & aes_boot.BUS in _the_binding_s_text()
    _the_binding_laid(monkeypatch, flipped=True)
    assert not any(lo <= cm.EVNT_MULTI_BINDING < hi for lo, hi in cm.the_desk_s_text(blob))
    (lowest, *_), _top = cm._the_desk_s_frames(rom, blob)
    assert lowest == case.long_in(rom, held_lowest) & aes_boot.BUS
    assert case.long_in(rom, lowest + aes.LONG_BYTES) & aes_boot.BUS not in _the_binding_s_text()
    lo, top = cm.the_desk_s_live_frames(rom, blob)
    assert lo == lowest + aes.LONG_BYTES and cm.lay_the_desk_s_live_frames(ours, rom, blob) > 0 and ours[lo:top] == rom[lo:top]
    ours[lo:lo + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    with pytest.raises(AssertionError, match="the desk's frame chain on our machine is not the ROM's"):
        cm.lay_the_desk_s_live_frames(ours, rom, blob)


THE_ANSWER_WORDS = 6                    # ev_multi's: the mouse's x and y, the buttons, the keys' state, the key, the clicks
ITS_PACKED_LONGWORDS = ("%fp@(-4)", "%fp@(-8)")     # the button word, the timer: what it stores in its frame before it parks


def _the_binding_before(called):
    """The ROM's evnt_multi binding's instructions before its Line-F call of `called`."""
    listing = cm.the_binding_s_listing()
    return listing[:next(index for index, (_at, _length, _text, names) in enumerate(listing) if names == called)]


def test_the_rom_s_binding_copies_out_six_answer_words_it_never_writes_before_it_parks():
    """BY READING (`aes_ctlmgr.the_binding_s_copies`): desk_evnt_multi copies SIX consecutive answer words of its frame out
    through its caller's six pointers, after its yield (the instruction after its `dsptch`); and before its Line-F call
    of ev_multi — where it parks — it stores into its frame only its two packed longwords and the argument slot at the
    `link`'s stack pointer (the answers' address it hands): none of the six."""
    reading = cm.the_binding_s_copies()
    answers = tuple(answer for answer, _out in reading.copies)
    assert len(answers) == THE_ANSWER_WORDS and answers == tuple(range(answers[0], answers[0] + THE_ANSWER_WORDS * aes.WORD_BYTES,
                                                                       aes.WORD_BYTES))
    yielded = next(at for at, _length, _text, called in cm.the_binding_s_listing() if called == addrs.AES_ROM_DSPTCH)
    assert reading.at == yielded + aes.WORD_BYTES
    before = [text for _at, _length, text, _called in _the_binding_before(addrs.AES_ROM_EV_MULTI) if text]
    into_its_frame = sorted({text.rpartition(",")[2] for text in before if text.rpartition(",")[2].startswith("%fp@(-")})
    assert into_its_frame == sorted(ITS_PACKED_LONGWORDS)
    assert all(int(at[len("%fp@("):-1]) >= answers[-1] + aes.WORD_BYTES for at in ITS_PACKED_LONGWORDS)
    unpushed = before[:next(index for index, text in enumerate(before) if text.endswith(",%sp@-"))]
    assert [text for text in unpushed if "%sp@" in text] == ["movel %fp,%sp@", f"addil #{answers[0]},%sp@"]


def test_a_menu_row_s_rom_run_copies_the_key_and_the_clicks_out_of_its_binding_s_residue(monkeypatch):
    """BY RUN (`aes_ctlmgr.ResidueCopies`, read off the ROM's run where its binding copies out): an item chosen from the
    bar wakes the desk with MU_MESAG alone — ev_multi answers the mouse, the buttons and the keys' state (ev_rets), no key
    and no clicks: THOSE TWO words are the binding's residue, and only they. Our shore's copies, to the same six out words,
    carry the same verdicts — the ROM's binding's while it is held (until F2c), OUR C binding's once flipped
    (`aes_ctlmgr.our_copying`, read off our build's listing)."""
    seen = []
    vet = bench_tier3().vet_the_desk_s_live_frames

    def kept(who, blob, rom, ours, programs, copies=None):
        seen.append(copies)
        vet(who, blob, rom, ours, programs, copies)
    monkeypatch.setattr(bench_tier3(), "vet_the_desk_s_live_frames", kept)
    bench_tier3().idle_to_idle_on(_shipped(), THE_MENU, WOKEN[THE_MENU])
    (the_rom_s, ours), = seen
    verdicts = [residue for _word, residue in the_rom_s.copied.values()]
    assert verdicts == [False] * (THE_ANSWER_WORDS - 2) + [True] * 2, "the key's and the clicks', the last two it copies"
    assert ({to: residue for to, (_word, residue) in ours.copied.items()}
            == {to: residue for to, (_word, residue) in the_rom_s.copied.items()})


def test_where_the_runs_end_a_residue_word_may_differ_and_nothing_else():
    """`aes_ctlmgr.residue_where_the_runs_end` and the vet, read by hand over the ROM-booted desk's machine: an out word
    BOTH runs copied from residue may differ, where each run's end still holds the word it copied; NOT where our run
    copied no word there, nor copied an answer, nor copied a word its end does not hold (a C that copies another word
    there: the RH2 review's M4), nor where the ROM's word was an answer, nor where the ROM's run left another value there
    since; and a byte beside it is compared as ever."""
    blob, rom = _shipped(), gc.machine(gc.THE_DESK).ram
    programs = ((aes.SHELL_PD, cm.the_desk_s_stack(gc.machine(gc.THE_DESK))),)
    lo, top = cm.the_desk_s_live_frames(rom, blob)
    word_at = top - 4 * aes.WORD_BYTES
    word = bytes(rom[word_at:word_at + aes.WORD_BYTES])
    other = bytearray(rom)
    other[word_at] ^= 1
    ours_held = bytes(other[word_at:word_at + aes.WORD_BYTES])

    def copies(rom_s, ours=None):
        made = [cm.ResidueCopies(lambda: ({}, False)) for _shore in range(2)]
        made[0].copied, made[1].copied = rom_s, ours or {}
        return tuple(made)
    residue, ours_residue = {word_at: (word, True)}, {word_at: (ours_held, True)}
    bench_tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(other), programs,
                                            copies(residue, ours_residue))
    for refused in (copies(residue), copies(residue, {word_at: (ours_held, False)}), copies(residue, {word_at: (word, True)}),
                    copies({word_at: (word, False)}, ours_residue),
                    copies({word_at: (bytes(b ^ 0xFF for b in word), True)}, ours_residue), None):
        with pytest.raises(AssertionError, match=r"THE DESK'S LIVE FRAMES .* ARE NOT THE ROM'S — 1 byte"):
            bench_tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(other), programs, refused)
    beside = bytearray(other)
    beside[word_at + aes.WORD_BYTES] ^= 1
    with pytest.raises(AssertionError, match=r"ARE NOT THE ROM'S — 1 byte"):
        bench_tier3().vet_the_desk_s_live_frames("a row", blob, _stood_in(rom), _stood_in(beside), programs,
                                                copies(residue, ours_residue))


def test_an_answer_word_is_residue_only_where_no_byte_of_it_was_stored():
    """`aes_ctlmgr.ResidueCopies` read by hand at a copy-out (the RH2 review's F3): the word copied is RESIDUE only where
    no store of the run reached EITHER byte of it — one byte stored makes it an answer; a store beside it does not; and
    a saturated ledger is refused by name."""
    sp, answer, out, to = 0x1000, 0x10, 0x40, 0x2000        # a stand-in copy-out: one word, one pointer, off SP
    copy_out = 0xF00
    at = sp + answer
    memory = bytearray(to + aes.LONG_BYTES)
    memory[sp + out:sp + out + aes.LONG_BYTES] = to.to_bytes(aes.LONG_BYTES, "big")
    memory[at:at + aes.WORD_BYTES] = word = bytes((0x12, 0x34))
    for stored, residue in (((), True), ((at - 1, at + aes.WORD_BYTES), True), ((at,), False), ((at + 1,), False),
                            ((at, at + 1), False)):
        made = cm.ResidueCopies(lambda: (dict.fromkeys(stored, 0), False), (copy_out, ((answer, out),)))
        made.observing[copy_out](memory, sp)
        assert made.copied == {to: (word, residue)}, f"stored {[hex(byte) for byte in stored]}"
    saturated = cm.ResidueCopies(lambda: ({}, True), (copy_out, ((answer, out),)))
    with pytest.raises(AssertionError, match="ledger saturated"):
        saturated.observing[copy_out](memory, sp)


def test_the_first_dispatch_is_held_to_the_bar_by_itself():
    """THE FIRST DISPATCH'S LINE IS PRICED (the fix pass, reviewer A's F2): at the bar it passes, over it — or a cost of
    ours against none of the ROM's — it is refused by name, never accepted (every row of ctlmgr's asks it: its
    measurement, `tier3.idle_to_idle_on`)."""
    bar = tier3().TIER3_FUNCTION_BAR
    tier3().vet_the_first_dispatch_within_the_bar("a row", (round(1000 * bar), 1000))
    for over in ((round(1000 * bar) + 1, 1000), (1, 0)):
        with pytest.raises(AssertionError, match="THE FIRST DISPATCH .* over the 1.10 bar by itself"):
            tier3().vet_the_first_dispatch_within_the_bar("a row", over)
