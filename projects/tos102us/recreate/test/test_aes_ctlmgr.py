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
import struct
import types
from collections import namedtuple

import pytest

from harness import addrs, bench_tier3, make_image

import aes
import aes_boot
import aes_ctlmgr as cm
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
    cm.Woken(THE_MENU, gc.THE_DESK, {0: (onto(VIEW),), **THE_MENU_WORKED}, EVERY_ROW_S),
    cm.Woken(PAST_THE_TITLES, A, dict(handlers.A_FIRST_TURN), PARKED_LAST),
    cm.Woken(THE_CLOSER, A, ON_THE_TOP_WINDOW("the closer", click), EVERY_ROW_S),
    cm.Woken(BOTH, A, {0: (onto(VIEW), click), **THE_MENU_WORKED}, EVERY_ROW_S),
    cm.Woken(AN_ARROW, A, ON_THE_TOP_WINDOW("the up arrow", click), EVERY_ROW_S),
    cm.Woken(A_DRAG, A, ON_THE_TOP_WINDOW("the title", PRESS, onto(handlers.A_DRAG_TO), RELEASE), EVERY_ROW_S),
    cm.Woken(TOPPED, A, {0: (onto(handlers.THE_OTHER_WINDOW_S_TITLE),), 1: (click,)}, (*EVERY_ROW_S, cm.THE_TOPPED_WORDS)),
    cm.Woken(THE_ENTRY, gc.HIDING, dict(handlers.THE_BAR_HIDDEN), SAVE_FRAME_ALONE),
    cm.Woken(THE_COUNT_AT_3_A_BUTTON, W, ON_THE_TOP_WINDOW("the closer", click, key=W), EVERY_ROW_S),
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
    THE_BAR: {BENCH: (812236, 776976), SHIPPED: (812236, 770550)},
    THE_MENU: {BENCH: (1975728, 1890968), SHIPPED: (1975728, 1877252)},
    PAST_THE_TITLES: {BENCH: (85630, 73634), SHIPPED: (85630, 71684)},
    THE_CLOSER: {BENCH: (313410, 247890), SHIPPED: (313410, 244420)},
    BOTH: {BENCH: (1987850, 1901016), SHIPPED: (1987850, 1886866)},
    AN_ARROW: {BENCH: (225718, 167786), SHIPPED: (225718, 164514)},
    A_DRAG: {BENCH: (605006, 532494), SHIPPED: (605006, 526624)},
    TOPPED: {BENCH: (147904, 129556), SHIPPED: (147904, 126398)},
    THE_ENTRY: {BENCH: (1051754, 955602), SHIPPED: (1051754, 941620)},
    THE_COUNT_AT_3_A_BUTTON: {BENCH: (362068, 294810), SHIPPED: (362068, 291344)},
    THE_COUNT_AT_3_THE_BAR: {BENCH: (811980, 776834), SHIPPED: (811980, 770264)},
}
# ...and how many windows of the ROM's processes each run holds beside the screen manager's turns.
THE_ROM_S_WINDOWS = {THE_BAR: 0, THE_MENU: 1, PAST_THE_TITLES: 0, THE_CLOSER: 1, BOTH: 1, AN_ARROW: 1, A_DRAG: 1, TOPPED: 1,
                     THE_ENTRY: 2, THE_COUNT_AT_3_A_BUTTON: 1, THE_COUNT_AT_3_THE_BAR: 0}
TURNS = {label: 2 if label == THE_ENTRY else 1 for label in WOKEN}
# HOW DEEP EACH ctlmgr GOES ON THE SCREEN MANAGER'S REAL STACK in the row's run — its top less the lowest byte the run
# stores there: (the ROM's, ours on the bench blob, ours on the shipped blob), THE MACHINE'S VDI (the ROM's) under
# the traps. (The build's OWN VDI under its traps — handlers and engines bound — is `test_aes_stack.py`'s staging
# and the bound's subject: a menu dropped 864 there on the shipped blob, 832 here.) Each fits its 1,196 bytes with
# the worst nest of interrupts on top, on both blobs.
DEEPEST = {THE_BAR: (722, 828, 832), THE_MENU: (722, 828, 832), PAST_THE_TITLES: (272, 298, 308), THE_CLOSER: (474, 528, 538),
           BOTH: (722, 828, 832), AN_ARROW: (346, 396, 404), A_DRAG: (548, 640, 650), TOPPED: (340, 360, 366),
           THE_ENTRY: (616, 740, 750), THE_COUNT_AT_3_A_BUTTON: (474, 528, 538), THE_COUNT_AT_3_THE_BAR: (722, 828, 832)}


def _name(label):
    return cm.row_name(WOKEN[label])


def _pd(label, who):
    return gc.pd_of(WOKEN[label].machine, who)


def test_every_row_of_ctlmgr_is_registered_pinned_and_in_the_table():
    assert WOKEN.keys() == PREMISES.keys() == WHOLE_RUN.keys() == THE_ROM_S_WINDOWS.keys() == DEEPEST.keys()
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
    assert len(measured.its_turns) == TURNS[label] and measured.foreign.windows == THE_ROM_S_WINDOWS[label]
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
        tier3().idle_to_idle_on(_shipped(), "a row", WOKEN[THE_CLOSER]._replace(differs=(*EVERY_ROW_S, cm.THE_TOPPED_WORDS)))


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


# ---- OUR ctlmgr ARRIVES: the handlers' own cases, met by our screen manager where the ROM's meets them ------------------------
# Every case of the handlers' battery is AN ARRIVAL OF THE ROM'S OWN ctlmgr (`test_aes_gemctrl.py`: the returning
# ones priced, the switching ones rows that switch, the rest Tier 1) and stays one: the differential starts at the
# handler, on the harness's stack. WHAT THE FLIP OWES THEM is that OUR ctlmgr — and our handlers above the one
# arrived at — bring the screen manager to that same call: the same chain, over the same boot with the screen
# manager ours, ends at OUR core of the handler with THE SAME FRAME over THE SAME MACHINE.
# ...BUT ct_msgup's: IN OUR BUILD IT HAS NO ARRIVAL OF ITS OWN. GCC inlines it into its two callers (hctl_window, hctl_rect:
# one translation unit) on both blobs — no instruction of either names its entry, which exists for its own rows — so
# our screen manager never stands at "ct_msgup's first instruction" (held below: the day a blob calls it, its cases
# join). What our ct_msgup does under our callers is in the arrivals of hctl_window and hctl_rect whose run goes on
# through it, in ctlmgr's own rows, and in its own rows from the ROM's arrivals.
INLINED_INTO_ITS_CALLERS = gc.CT_MSGUP
EVERY_ARRIVAL = {f"{gc.name_of(routine)}, {label}": each.arrival
                 for table in (handlers.RETURNING, handlers.SWITCHING, handlers.UNPRICED)
                 for (routine, label), each in table.items() if each.arrival.chain is not None}
ARRIVALS = {name: arrival for name, arrival in EVERY_ARRIVAL.items() if arrival.routine != INLINED_INTO_ITS_CALLERS}
THE_BOOT_S_OWN = [each.arrival for each in handlers.RETURNING.values() if each.arrival.chain is None]


def test_every_case_of_the_handlers_is_an_arrival_this_battery_meets():
    assert len(EVERY_ARRIVAL) == len(handlers.RETURNING) + len(handlers.SWITCHING) + len(handlers.UNPRICED) - 1 and THE_BOOT_S_OWN == [gc.BOOT_ARRIVAL]
    assert {arrival.routine for arrival in ARRIVALS.values()} == set(gc.ROUTINES) - {INLINED_INTO_ITS_CALLERS}
    assert len(ARRIVALS) == len(EVERY_ARRIVAL) - sum(arrival.routine == INLINED_INTO_ITS_CALLERS for arrival in EVERY_ARRIVAL.values())


def test_ct_msgup_is_called_by_no_instruction_of_a_blob_and_its_arrival_is_refused_by_name(blob):
    """THE ONE HANDLER WITH NO ARRIVAL OF ITS OWN ON A BLOB (above): no instruction of the blob calls or branches to
    `aes_ct_msgup` — it is inlined into its callers — and a run asked to end at its entry is refused BY NAME where the
    machine idles with the handler never called, not run to a budget."""
    core = routines.core_symbol(INLINED_INTO_ITS_CALLERS)
    naming = [line for line in transcription.listing(blob.elf).splitlines() if f"<{core}>" in line and "\t" in line]
    assert not naming, f"a blob names ct_msgup's entry: its cases have an arrival now — {naming[:2]}"
    name, arrival = next((name, arrival) for name, arrival in EVERY_ARRIVAL.items()
                         if arrival.routine == INLINED_INTO_ITS_CALLERS and "WM_CLOSED, the button up" in name)
    with pytest.raises(switching.Refused, match="was\\s+never called: the screen manager did not arrive there"):
        tier3().arrives_alike_on(blob, name, arrival.machine, cm.arriving(arrival))


@pytest.mark.parametrize("case_name", ARRIVALS)
def test_our_ctlmgr_arrives_at_the_handler_with_the_rom_s_frame_over_the_rom_s_machine(case_name, blob):
    """THE HANDLERS' CASES CARRY OVER (`tier3.arrives_alike_on`): from the booted machine's idle, through the case's own
    chain, our screen manager — `aes_rom_ctlmgr` on its real stack, and for a handler called by another (hctl_window
    under hctl_button, ct_msgup under either) our handlers above it — arrives at OUR core of the case's handler, at
    the arrival the case names, with the frame the ROM's caller pushed; the image at every stop of the dispatcher's
    watch and AT THE ARRIVAL is the ROM's outside the screen manager's own spans; and none of it ran the ROM's ctlmgr."""
    arrival = ARRIVALS[case_name]
    arriving = cm.arriving(arrival)
    assert tier3().arrives_alike_on(blob, case_name, arrival.machine, arriving) == gc.at(arrival).arguments


def test_the_boot_s_own_arrival_is_our_ctlmgr_s_too(blob):
    """...AND THE ONE ARRIVAL THAT IS NO DISPATCHER'S: the desk's menu_bar posts the screen manager a click and the
    boot calls hctl_button with it before its first idle. The same boot with the screen manager ours, stopped at OUR
    hctl_button's first instruction (`aes_boot.booted(until=)`: an address of the blob), is there with the ROM's
    frame — the click's point — on the screen manager's own stack, in our ctlmgr's first turn."""
    name, arguments, _pokes = gc.at(gc.BOOT_ARRIVAL)
    ours = aes_boot.ours_of(blob)
    core = dict(ours.handlers)[getattr(addrs, name)]
    boot = aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=core, ours=ours)
    sp = boot.registers["isp"]
    lo, top, _why = gc.its_stack(boot.ram)
    assert boot.registers["pc"] == core and lo < sp < top and blob.base <= case.long_in(boot.ram, sp) < blob.end
    assert tier3()._frame_our_caller_pushed(len(arguments))(boot.ram, sp) == arguments


def test_the_image_at_an_arrival_is_held_too(monkeypatch):
    """...AND "OVER THE ROM'S MACHINE" HAS TEETH: our image read with one byte other AT THE ARRIVAL ITSELF — the last
    stop of our run — is refused by that stop and its page; the frame alone would not have seen it."""
    name, arrival = next((name, arrival) for name, arrival in ARRIVALS.items() if arrival.routine == gc.HCTL_WINDOW)
    arriving, pages = cm.arriving(arrival), aes_event.image_pages
    stops = 2 * (arriving.switches.polls + len(arriving.entered) + 1)       # each shore's polls, resumes and its arrival

    def one_byte_other_at_our_arrival(memory, also=()):
        asked.append(None)
        if len(asked) == stops:
            memory = bytearray(memory[:addrs.ST_RAM_BYTES])
            memory[aes.AES_GL_WCHAR] ^= 1
        return pages(memory, also)
    asked = []
    monkeypatch.setattr(aes_event, "image_pages", one_byte_other_at_our_arrival)
    with pytest.raises(AssertionError, match="at arrival 0 of the dispatcher's watch OUR IMAGE IS NOT THE ROM'S"):
        tier3().arrives_alike_on(_shipped(), name, arrival.machine, arriving)
    assert len(asked) == stops


def test_an_arrival_with_another_frame_than_the_rom_s_case_is_refused():
    """...AND THE FRAME IS COMPARED WHERE THE RUNS END, not by this battery's reading of the answer alone: the same
    case asked for with one word of its frame other than the ROM's run derived is refused by name."""
    name, arrival = next((name, arrival) for name, arrival in ARRIVALS.items() if arrival.routine == gc.HCTL_BUTTON)
    arriving = cm.arriving(arrival)
    other = arriving._replace(words=(arriving.words[0] + 1, *arriving.words[1:]))
    with pytest.raises(AssertionError, match="our ctlmgr hands AES_ROM_HCTL_BUTTON"):
        tier3().arrives_alike_on(_shipped(), name, arrival.machine, other)


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
