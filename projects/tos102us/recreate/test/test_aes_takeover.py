"""THE SCREEN MANAGER MADE OURS ON A ROW'S MACHINE (`test/aes_takeover.py`; FLIP 4) — the machinery's own cases.

A row whose run enters the screen manager runs, on our shore, over its machine WITH THE SCREEN MANAGER OURS: its
saved context and its stack as our build's own run through the machine's history leaves them. Held here:

  * THE BASE: the boot snapshot's screen manager, and every booted machine's, stands exactly as the desk's boot
    leaves it — on the ROM's shore and (the takeover machines) on each blob;
  * THE PROVENANCE: the machines a ROM run left it elsewhere in are noted by that run, and made ours by our build's
    own run of it; a state no history reaches is refused by name;
  * WHICH ROWS: exactly those whose ROM run enters the screen manager as another process than their own — read off
    the run, none excused — each with its turns pinned on both blobs;
  * WHO RAN: in a turn of ours not one cycle is spent in the ROM's ctlmgr (`$fe49d2..$fe4a6a`) and our own entry's
    body runs — and the same counters READ THE ROM'S ctlmgr RUNNING where the row is left on the ROM's;
  * THE REFUSALS, each by name: a machine made ours and resumed in the ROM's text; a ROM-made one resumed in the
    blob; a run nobody prepared; a turn the price forgot.
"""
import copy
import types

import pytest

from harness import BASE_IMAGE, bench_tier3, emu, make_image

import aes
import aes_boot
import aes_event
import aes_evlib as evlib
import aes_gemctrl as gc
import aes_switching as switching
import aes_takeover as takeover
import aes_turns_pinned
import test_aes_ctlmgr as its_own
import test_aes_evdisp_model as model
import test_boot_snapshot  # noqa: F401  (every battery's rows registered, and the runs that left the screen manager elsewhere noted)

tier3 = bench_tier3
SM = aes.SCREEN_MANAGER_PD
PILOT = next(row for row in model.WOKEN_ROWS if row.label == model.THROUGH_THE_SCREEN_MANAGER)
BENCH, SHIPPED = "bench", "bench_shipped"
THE_ROM_S_CTLMGR = its_own.cm.THE_ROM_S_BODY


def _rows_with_the_screen_manager_ours():
    return {name: held for name, held in aes_event.SWITCHING_ROWS.items() if takeover.named_in(held.drops)}


# ---- THE BASE: how the screen manager stands where a boot leaves it ---------------------------------------------------------
def test_the_boot_snapshot_s_screen_manager_stands_as_the_rom_s_boot_leaves_it():
    """THE PREMISE OF EVERY ROW OVER THE SNAPSHOT: the snapshot's screen manager — nine hundred vertical blanks after
    the boot's first idle — has the saved context and the live frames of `aes_boot.desk_machine()`'s, byte for byte:
    it parked once, at its main wait, and nothing has woken it since. (Its dead stack below, where interrupts landed
    meanwhile, is no part of how it stands.) A capture decides none of it: held on whichever the tree holds."""
    (state, booted), = takeover.the_boot_s().items()
    assert takeover.state_of(BASE_IMAGE) == state == takeover.state_of(booted.image())
    at = takeover.spans_of(BASE_IMAGE)
    assert at.stack[1] - at.stack[0] == its_own.handlers.USABLE_STACK_BYTES and at.stack[0] < at.parked < at.stack[1]
    assert aes.AES_TEXT[0] <= aes_boot.parked_pc(BASE_IMAGE, SM) < aes.AES_TEXT[1], "parked in the ROM's text"


@pytest.mark.parametrize("key", gc.MACHINES)
def test_every_boot_parks_the_screen_manager_alike_on_each_shore(key, blob):
    """...AND EVERY BOOTED MACHINE'S — the desk alone, the accessories in each of their modes — parks it THE SAME: one
    state on the ROM's shore, and on a blob one context and one run of live frames whatever the machine (the takeover
    machine of each boot). So one boot stands for all where a machine's screen manager is made ours."""
    (state, _booted), = takeover.the_boot_s().items()
    assert takeover.state_of(gc.machine(key).image()) == state
    modes = gc.ACCESSORY_MODES.get(key)
    taken = aes_boot.desk_machine(ours=blob) if modes is None else aes_boot.accessory_machine(*modes, ours=blob)
    ours = takeover.state_of(taken.image())
    assert ours == takeover.state_of(aes_boot.desk_machine(ours=blob).image()) != state
    assert len(ours.live) > len(state.live), "our ctlmgr parks deeper than the ROM's (its frames, the call's ABI)"


def test_two_blobs_are_two_machines():
    """THE FRAMES HOLD BLOB ADDRESSES: what a machine's screen manager is made ours from is one blob's own."""
    made = [takeover.prepared(tier3().RomBench(directory), {}) for directory in (None, tier3().SHIPPED_BENCH_DIR)]
    assert made[0].keys() == made[1].keys() and made[0] != made[1]
    at = takeover.spans_of(BASE_IMAGE)
    assert sorted(made[0]) == [at.context[0], at.stack[0]]
    assert [len(made[0][lo]) for lo in sorted(made[0])] == [at.context[1] - at.context[0], at.stack[1] - at.stack[0]]


# ---- THE PROVENANCE: the machines a ROM run left the screen manager elsewhere in ----------------------------------------------
def test_a_rom_run_that_leaves_the_screen_manager_elsewhere_is_noted_and_one_that_does_not_is_not():
    """`aes_switching.left_by` NOTES A RUN where it leaves the screen manager in another state than it found it: the
    key waited for across the bar's wake (its menu bar live, the lock its own) is the provenance of the machine it
    leaves; the hand-over that only makes it READY changes nothing of how it stands, and the state it is in is still
    the earlier run's — the one that queued it on the lock."""
    held_by_the_menu = takeover.state_of(make_image(evlib.the_manager_s_menu_holds_the_lock()))
    queued, handed = (takeover.state_of(make_image(machine())) for machine in (
        evlib.the_manager_queued_itself_on_the_lock, evlib.the_manager_handed_the_lock))
    boot, = takeover.the_boot_s()
    assert len({held_by_the_menu, queued, boot}) == 3 and handed == queued
    assert takeover.PROVENANCE[held_by_the_menu].name == evlib.EV_KEYBD
    assert takeover.PROVENANCE[queued].name == evlib.EV_BLOCK
    assert takeover.state_of(make_image(takeover.PROVENANCE[held_by_the_menu].machine)) == boot, "its history ends at the boot"
    assert boot not in takeover.PROVENANCE


def test_every_row_s_machine_is_one_a_history_of_ours_reaches(blob):
    """EVERY ROW THAT RUNS WITH THE SCREEN MANAGER OURS starts from the boot's state or from one a noted ROM run
    left — and each is MADE (`prepared`: the takeover boot's, or our build's own run of the noted call, on this
    blob), two spans whose live part is not the ROM's."""
    states = {takeover.state_of(make_image(held.pokes)) for held in _rows_with_the_screen_manager_ours().values()}
    (boot, _booted), = takeover.the_boot_s().items()
    assert boot in states and states - {boot} == set(takeover.PROVENANCE) and len(takeover.PROVENANCE) == 3
    for held in _rows_with_the_screen_manager_ours().values():
        image = make_image(held.pokes)
        made, at = takeover.prepared(blob, held.pokes), takeover.spans_of(image)
        assert takeover.ours_over(blob, image) is made
        assert made[at.context[0]] != bytes(image[at.context[0]:at.context[1]])


def test_a_screen_manager_parked_where_no_history_leaves_it_is_refused_by_name(blob):
    """A MACHINE NO RUN OF OURS REACHES IS REFUSED: one byte of the screen manager's live frames changed — a state
    neither the boot's nor any noted run's — and nothing is laid over it."""
    at = takeover.spans_of(BASE_IMAGE)
    astray = {at.parked + 8: bytes([BASE_IMAGE[at.parked + 8] ^ 0xff])}
    with pytest.raises(takeover.Refused, match="STANDS PARKED WHERE NO HISTORY OF OURS IS KNOWN TO LEAVE IT"):
        takeover.prepared(blob, astray)
    with pytest.raises(takeover.Refused, match="saved stack pointer .* lies outside its own stack"):
        uda = aes_event.uda_of(SM, BASE_IMAGE)
        takeover.prepared(blob, {uda + aes.UDA_SUPER_SP: (at.stack[1] + 2).to_bytes(4, "big")})


def test_a_run_nobody_prepared_is_refused_where_it_is_entered(blob, monkeypatch):
    """MADE BEFORE A MEASUREMENT'S OWN RUNS, NEVER INSIDE THEM (a boot, or a run of our build, would fall inside the
    measurement's profile): entered over a machine nobody prepared, the run is refused by name."""
    monkeypatch.setattr(takeover, "_OURS", {})
    monkeypatch.setattr(tier3(), "screen_manager_made_ours", lambda *_asked: None)
    with pytest.raises(takeover.Refused, match="entered over a machine nobody prepared it for"):
        switching.measured_on(blob, PILOT)


# ---- WHICH ROWS -------------------------------------------------------------------------------------------------------------------
def test_the_rows_with_the_screen_manager_ours_are_those_whose_run_enters_it_and_each_has_its_turns_pinned():
    """READ OFF THE ROM'S RUN, NOT DECLARED: a registered row names the screen manager's two spans exactly when its
    dispatcher enters the screen manager as ANOTHER process than the row's own — no row is left on the ROM's — and
    each has its turns pinned on both blobs (`aes_turns_pinned`), but the one slice of a session whose window lies in
    the session's other slice. The screen manager's own rows (its handlers') name neither span in the registry:
    their process IS the screen manager — and at Tier 3 they are measured where each shore's own ctlmgr arrives at
    its handler (`aes_ctlmgr.HANDLED`), where the two spans are classes each such row names."""
    ours = _rows_with_the_screen_manager_ours()
    enters = {name for name, held in aes_event.SWITCHING_ROWS.items() if held.switches.process != SM and SM in held.entered}
    assert set(ours) == enters and len(ours) == 33
    assert not [name for name, held in aes_event.SWITCHING_ROWS.items() if held.row.the_rom_s_screen_manager]
    assert not [name for name, held in aes_event.SWITCHING_ROWS.items() if held.switches.process == SM and name in ours]
    pinned = {name for name in aes_turns_pinned.PINNED if not name.startswith(its_own.cm.SYMBOL)}
    # (A SESSION CUT INTO SLICES is pinned whole, under its session's own name — its battery holds the whole run on
    # each blob — where the registry holds its slices: the file selector's session behind the menu, two slices.)
    slices, the_session = set(ours) - pinned, pinned - set(ours)
    assert len(slices) == 2 and slices <= set(aes_event.SLICED_ROWS) and len(the_session) == 1
    assert all(name.startswith("aes_fs_input, ") for name in slices | the_session)
    for name in pinned:
        turns = aes_turns_pinned.PINNED[name]
        assert turns.keys() == {BENCH, SHIPPED} and all(ours > 0 and the_rom_s > 0 for each in turns.values() for ours, the_rom_s, _glue in each)


# ---- WHO RAN ------------------------------------------------------------------------------------------------------------------------
def _its_body_counted(blob, tally):
    """`tally` (`tier3._our_foreign_tally`'s, for `blob`) with two counters more: the cycles spent in THE ROM'S
    ctlmgr's body, and in our own entry's (`aes_rom_ctlmgr`'s span in the blob)."""
    entry, = tier3()._function_ranges(blob.elf)[its_own.cm.SYMBOL]
    return lambda: (*tally(), emu.prof_cycles(*THE_ROM_S_CTLMGR), emu.prof_cycles(*entry))


IN_THE_ROM_S_CTLMGR, IN_OUR_ENTRY = 4, 5


def _windows_with_the_bodies_counted(blob, row, monkeypatch):
    counted = tier3()._our_foreign_tally
    monkeypatch.setattr(tier3(), "_our_foreign_tally", lambda on, glue: _its_body_counted(on, counted(on, glue)))
    try:
        _measured, watch, _foreign = switching.measured_on(blob, row)
    finally:
        monkeypatch.setattr(tier3(), "_our_foreign_tally", counted)
    return watch


def test_in_a_turn_of_ours_the_rom_s_ctlmgr_runs_no_instruction_and_our_entry_does(blob, monkeypatch):
    """WHO RAN, COUNTED AT THE PCs: over the pilot (a key waited for; the bar wakes the screen manager, which drops its
    menu and waits) our run's one window is read off the run as OURS and holds NOT ONE CYCLE at a PC of the ROM's
    ctlmgr (`$fe49d2..$fe4a6a`), some in our entry's own body (its loop: the lock taken, the bar's handler called) —
    AND THE COUNTER SEES THE ROM'S ctlmgr WHERE IT RUNS: the same row left on the ROM's screen manager spends its
    cycles there and none in our entry."""
    watch = _windows_with_the_bodies_counted(blob, PILOT, monkeypatch)
    (window,), entered = watch.foreign, dict(zip(watch.entered, watch.resumed_in))
    assert watch.window_classes == [switching.OURS] and entered[SM] == switching.OURS
    assert window[IN_THE_ROM_S_CTLMGR] == 0 == window[tier3().TALLY_AES] and window[IN_OUR_ENTRY] > 0
    left = PILOT._replace(the_rom_s_screen_manager="WHO RAN's own control: the pilot as it stood before the flip")
    watch = _windows_with_the_bodies_counted(blob, left, monkeypatch)
    (window,) = watch.foreign
    assert watch.window_classes == [switching.THE_ROM_S] and window[IN_THE_ROM_S_CTLMGR] > 0 == window[IN_OUR_ENTRY]


# ---- THE REFUSALS -------------------------------------------------------------------------------------------------------------------
def test_a_machine_said_ours_whose_screen_manager_resumes_in_the_rom_s_text_is_refused(blob, monkeypatch):
    """A ROW ON A TAKEOVER MACHINE WHOSE SCREEN MANAGER RESUMES IN THE ROM'S TEXT: the row names the spans, and what is
    laid over them is the ROM's own (as if nothing had been made ours) — refused BY NAME at switchto's `rte`, read
    off the PC it resumes at, never priced as a turn of ours."""
    as_the_machine_came = lambda _blob, image: {lo: bytes(image[lo:hi]) for lo, hi in takeover.spans_of(image)[:2]}   # noqa: E731
    monkeypatch.setattr(takeover, "ours_over", as_the_machine_came)
    with pytest.raises(switching.Refused, match="A ROW ON A TAKEOVER MACHINE WHOSE SCREEN MANAGER RESUMES IN THE ROM'S TEXT"):
        switching.measured_on(blob, PILOT)


def test_the_watch_refuses_a_process_resumed_in_code_its_machine_does_not_say_it_runs(blob):
    """THE CLASSIFICATION'S REFUSALS, at the watch (`Switching._vet_whose`): on a machine whose screen manager is NOT
    ours a foreign process resumed in the blob; a PC that is neither's; and on one that is, the screen manager in the
    ROM's text, and ANOTHER process than the screen manager in the blob (no machine has one today: the day a second
    process is ours, its window is not the screen manager's turn) — the desk or an accessory in the ROM's text is the
    ROM's process, and passes. WHOSE A PC IS, AT THE EDGES: the blob's first byte and not its end; the AES's text's
    first instruction and its last word, and neither the word under it nor the one at its end (the Line-F table)."""
    switches = switching.settled(PILOT).switches
    desk_s = aes.AES_TEXT[0] + 0x100
    for takes_over, entering, pc, refused in (
            (False, SM, blob.base + 0x100, "ANOTHER PROCESS than the row's, is resumed IN OUR BUILD'S TEXT"),
            (False, SM, 0x400, "neither in the blob nor in the AES's ROM text"),
            (True, SM, desk_s, "WHOSE SCREEN MANAGER RESUMES IN THE ROM'S TEXT"),
            (True, aes.SHELL_PD, blob.base + 0x100, "A PROCESS THAT IS NOT THE SCREEN MANAGER, is resumed IN OUR BUILD'S TEXT")):
        watch = switching.ours(blob, switches, switches.at_idles, takeover=takes_over)
        watch._entering = entering
        with pytest.raises(switching.Refused, match=refused):
            watch._vet_whose(watch._whose(pc), pc)
    watch = switching.ours(blob, switches, switches.at_idles, takeover=True)
    watch._entering = aes.SHELL_PD
    watch._vet_whose(watch._whose(desk_s), desk_s)
    assert (watch._whose(blob.base), watch._whose(blob.end), watch._whose(desk_s)) == (switching.OURS, None, switching.THE_ROM_S)
    lo, hi = aes.AES_TEXT
    assert [watch._whose(pc) for pc in (lo - aes.WORD_BYTES, lo, hi - aes.WORD_BYTES, hi)] == [None, switching.THE_ROM_S, switching.THE_ROM_S, None]


def test_a_turn_the_price_forgets_breaks_the_row_s_identity(monkeypatch):
    """THE PRICE OFF BY ONE WINDOW: the pilot's turn left out of what the row is priced net of — read, then, as a
    window of the ROM's process, which on our shore held not one cycle of the AES's ROM — is refused by name before
    anything is priced: our run's cycles in the AES's ROM are not its windows'."""
    row = switching.table_row(PILOT)
    monkeypatch.setattr(tier3(), "turns_made", lambda *_watches: ())
    with pytest.raises(AssertionError, match="our build spent -\\d+ cycles inside the AES's own ROM spans"):
        tier3().measure(row, tier3().RomBench())


def test_the_identity_is_refused_where_a_window_is_missing_or_counted_twice():
    """...AND THE IDENTITY'S OWN ARITHMETIC (`tier3.vet_the_identity`), on a measurement made by hand: whole = own +
    thunks + our turns + the ROM's windows + the OS outside them, the last ONE number on both shores — a turn's
    cycles left in a column, or a window's taken off twice, is refused; and the windows are the watches' own."""
    made = tier3().Measurement((0, 1000 + 40), (0, 900 + 40), (1, 40))
    made.own_cycles, made.glue_cycles = (100, 170), 10
    made.turns = (tier3().Turn(200, 260, 20, 300),)                     # ours 200 + 20 + 300 whole; the ROM's 260 + 300
    made.foreign = tier3().Foreign(2, 260 + 300 + 90, 260 + 50)         # ...and one window of the ROM's process, 90
    ours, the_rom_s = (types.SimpleNamespace(foreign=windows) for windows in (
        [(520, 0, 220, 20), (90, 50, 0, 0)], [(560, 260), (90, 50)]))
    tier3().vet_the_identity("a row", made, ours, the_rom_s)            # 900 = 100 + 10 + 520 + 90 + 180; 1000 = 170 + 560 + 90 + 180
    forgotten = copy.copy(made)
    forgotten.turns = ()                                                # the turn's cycles left in nobody's column
    with pytest.raises(AssertionError, match="THE IDENTITY DOES NOT HOLD"):
        tier3().vet_the_identity("a row", forgotten, ours, the_rom_s)
    dearer = copy.copy(made)
    dearer.own_cycles = (101, 170)                                      # a cycle of the turn's counted as the caller's own
    with pytest.raises(AssertionError, match="THE IDENTITY DOES NOT HOLD"):
        tier3().vet_the_identity("a row", dearer, ours, the_rom_s)
    with pytest.raises(AssertionError, match="a window is missing from the price, or counted twice"):
        tier3().vet_the_identity("a row", made, types.SimpleNamespace(foreign=ours.foreign[:1]), the_rom_s)


def test_who_ran_is_refused_each_way_on_two_runs_counted_by_hand():
    """WHO RAN'S OWN ARITHMETIC (`tier3.vet_who_ran`), over stand-in runs: the ROM's run in its ctlmgr and out of the
    blob, ours out of the ROM's ctlmgr and in its own entry, our cycles in the AES's ROM exactly the ROM's processes'
    and the first dispatch's, every cycle of our build a turn's — each refused by name where it is not so. (On a real
    run each is implied twice over by the windows' own rules, which refuse first: a turn of ours holds no cycle of the
    AES's ROM, and what runs outside every window is the same on both shores.)"""
    ran = lambda **counted: types.SimpleNamespace(**{"in_the_rom_s_ctlmgr": 0, "in_our_entry": 0, "in_the_aes": 0, "blob": 0, **counted})   # noqa: E731
    rom, ours = ran(in_the_rom_s_ctlmgr=900, in_the_aes=5000), ran(in_our_entry=700, in_the_aes=1200, blob=3000)
    tier3().vet_who_ran("a row", rom, ours, 1200, 3000)
    for astray, refused in ((dict(in_the_rom_s_ctlmgr=16), "WHO RAN — our run spent 16 cycles in the ROM's ctlmgr"),
                            (dict(in_our_entry=0), "WHO RAN — our run spent 0 cycles in the ROM's ctlmgr and 0 in"),
                            (dict(in_the_aes=1216), "OUR run spent 1216 cycles at the PCs of the AES's own ROM"),
                            (dict(blob=3001), "our build ran 3001 cycles and its screen manager's turns hold 3000")):
        with pytest.raises(AssertionError, match=refused):
            tier3().vet_who_ran("a row", rom, types.SimpleNamespace(**{**vars(ours), **astray}), 1200, 3000)
    for astray in (dict(in_the_rom_s_ctlmgr=0), dict(blob=4)):
        with pytest.raises(AssertionError, match="WHO RAN"):
            tier3().vet_who_ran("a row", types.SimpleNamespace(**{**vars(rom), **astray}), ours, 1200, 3000)


def test_a_row_with_a_turn_over_the_bar_is_over_whatever_its_own_counts(monkeypatch):
    """A TURN IS HELD TO THE BAR BY ITSELF, AND NO WORD CARRIES IT: the pilot's measurement with its one turn made
    dearer — past 1.10 with its thunks — is OVER by the table's own rule (`tier3.verdict`), its own two counts
    untouched and well under the bar; with the turn as measured it is `net`. Without its thunks the same turn is under
    the bar: it is the number that ships that is held."""
    row = switching.table_row(PILOT)
    measured = tier3().measure(row, tier3().RomBench())
    no_other = lambda *_asked: pytest.fail("the verdict of a row through the OS asks no other row's measurement")   # noqa: E731
    (turn,), bar = measured.turns, tier3().TIER3_FUNCTION_BAR
    assert tier3().verdict(row, measured, 0, no_other) == "net" and tier3().turns_within_bar(measured)
    dearer = turn._replace(glue=int(turn.the_rom_s * bar) - turn.ours + 1)
    assert tier3().turn_ratio(dearer) < bar < tier3().turn_ratio_with_glue(dearer)
    measured.turns = (dearer,)
    assert not tier3().turns_within_bar(measured) and tier3().counts_within_bar_with_glue(measured)
    assert tier3().verdict(row, measured, 0, no_other) == "OVER"
    assert "OVER THE BAR BY ITSELF" in tier3()._turn_lines(measured, 0)[0]


def test_the_identity_is_asked_of_the_table_s_measurement_of_a_row_that_switches(monkeypatch):
    """THE IDENTITY'S CALL, not its arithmetic alone (which the cases above refuse each way): THE TABLE'S measurement
    of the pilot (`tier3.measure`: the one path that carries the own columns it re-adds) asks `vet_the_identity`
    once, of that row's two runs. A guard nothing calls reds nowhere — on honest numbers it is
    silent whether asked or not — so its being asked is held by itself (mutation sweep, FLIP 4: the call dropped
    survived every battery until this)."""
    asked, the_guard = [], tier3().vet_the_identity
    monkeypatch.setattr(tier3(), "vet_the_identity", lambda who, *runs: (asked.append(who), the_guard(who, *runs))[1])
    row = switching.table_row(PILOT)
    tier3().measure(row, tier3().RomBench())
    assert len(asked) == 1 and row.case in asked[0]


# ---- NOBODY BUT THE SCREEN MANAGER STORES IN ITS CONTEXT AND ITS STACK (FLIP 4's review, finding 1) --------------------------
# On a row whose screen manager is ours its two spans — 1,264 bytes — are out of every compare of the two shores (two
# builds' frames). What that hid: a store there BY THE ROW'S OWN PROCESS, which no pin sees where it costs nothing and
# which crashes the screen manager at its next wake on iron. `Switching` now holds the spans BY CONTENT wherever the
# screen manager does not run — from the run's entry to its first turn, between its turns, from its last to where
# the run ends — on both shores; the one word excepted is the SR of the `rte` frame the dispatcher stores as it hands
# the machine back, at the stack pointer the screen manager stood parked at.
ANOTHER_BYTE, THE_SAME_BYTE = "another byte", "the byte it held, stored again"


def _stray_store_where_the_row_s_process_is_first_resumed(monkeypatch, at, what=ANOTHER_BYTE):
    """OUR run given a stray store at `at` WHERE THE ROW'S OWN PROCESS IS FIRST RESUMED — laid at the watch: no cycle
    spent, so no pin moves — ANOTHER_BYTE in its memory, or THE_SAME_BYTE: nothing in its memory, the address in its
    write ledger (a store of the value the byte held). What a stray store of the row's own code would leave."""
    real, laid = switching.Switching._resumed, []

    def resumed(self, pc, sp, memory):
        its_own_process = self._entering == self.switches.process
        real(self, pc, sp, memory)
        if self._ours is not None and its_own_process and not laid:
            if what == ANOTHER_BYTE:
                memory[at] ^= 0xff
            else:
                the_run_s = self._ledger
                self._ledger = lambda: frozenset(the_run_s()) | {at}
            laid.append(at)
    monkeypatch.setattr(switching.Switching, "_resumed", resumed)
    return laid


# TWO ROWS, the two places such a store is found: THE PILOT's own process is first resumed AFTER the screen manager's
# one turn (the store is found where the run ends); the lock's row's is resumed BEFORE the screen manager's turns (its
# own dispatch brings it back first: found where the screen manager is next resumed).
THE_LOCK_S_ROW = "aes_all_run, the screen manager's menu holds the lock: the caller waits until the menu is let go"
FOUND = {"after the screen manager's turn": (lambda: PILOT, "where the run ends"),
         "before the screen manager's turn": (lambda: aes_event.SWITCHING_ROWS[THE_LOCK_S_ROW].row, "where the screen manager is resumed")}
assert list(FOUND) == ["after the screen manager's turn", "before the screen manager's turn"]


DEAD, LIVE, CONTEXT = "its dead stack", "its live frames", "its saved context"
AFTER, BEFORE = "after the screen manager's turn", "before the screen manager's turn"
# WHAT THE LEDGER HALF CANNOT SEE, AND SO IS NOT ASKED: the same byte stored again AFTER the screen manager's turn at an
# address ITS OWN TURN STORED IN THIS RUN (its live frames, its saved context) — the ledger keeps addresses, not who
# stored them last (held as the limit it is, below).
SEEN = [(where, when, ANOTHER_BYTE) for when in (AFTER, BEFORE) for where in (DEAD, LIVE, CONTEXT)] + [
    (DEAD, AFTER, THE_SAME_BYTE), (DEAD, BEFORE, THE_SAME_BYTE), (LIVE, BEFORE, THE_SAME_BYTE), (CONTEXT, BEFORE, THE_SAME_BYTE)]
UNSEEN = [(LIVE, AFTER, THE_SAME_BYTE), (CONTEXT, AFTER, THE_SAME_BYTE)]


def _where_in_its_spans(row, where):
    spans = takeover.spans_of(make_image(switching.settled(row).pokes))
    return {DEAD: spans.stack[0] + 0x14, LIVE: spans.stack[1] - 0x20, CONTEXT: spans.context[0] + 6}[where]


@pytest.mark.parametrize("where, when, what", UNSEEN)
def test_the_same_byte_stored_again_where_the_screen_manager_s_own_turn_stored_is_seen_by_nothing(where, when, what, blob, monkeypatch):
    """THE HOLD'S LIMIT, HELD AS ONE (STATUS says it): a store by the row's own process, after the screen manager's
    turn, of the value the byte holds, at an address that turn itself stored — no content changes, and the ledger
    holds the address already. The measurement passes. (The day a ledger says who stored last, this turns red:
    move the two cases to the others.)"""
    row = FOUND[when][0]()
    made = switching.settled(row)
    tier3().screen_manager_made_ours(blob, made.pokes, made.drops)
    laid = _stray_store_where_the_row_s_process_is_first_resumed(monkeypatch, _where_in_its_spans(row, where), what)
    switching.measured_on(blob, row)
    assert len(laid) == 1


@pytest.mark.parametrize("where, when, what", SEEN)
def test_a_store_by_the_row_s_own_process_into_the_screen_manager_s_spans_is_refused_by_name(where, when, what, blob, monkeypatch):
    """THE REVIEW'S PROBE, RED ON BOTH BLOBS: one byte flipped in our run's memory where the row's own process is
    resumed — in the screen manager's dead stack, in the live frames under its stack's top, in its saved context — is
    refused by name with the address, where before the hold each passed unseen with every pin kept: found WHERE THE
    RUN ENDS when the screen manager has no turn left, WHERE IT IS NEXT RESUMED when it has. AND A STORE THAT LEAVES
    THE BYTE IT FOUND is refused too, by the run's ledger: the content alone cannot see it (the C mutant that showed
    it stored a constant our screen manager's own boot had already stored there)."""
    row, found = FOUND[when]
    row = row()
    made = switching.settled(row)
    entered, row_process = list(made.entered), made.switches.process
    assert (entered.index(SM) < entered.index(row_process)) == (found == "where the run ends")
    tier3().screen_manager_made_ours(blob, made.pokes, made.drops)     # ...made BEFORE the store is armed: a run of its own
    at = _where_in_its_spans(row, where)
    laid = _stray_store_where_the_row_s_process_is_first_resumed(monkeypatch, at, what)
    with pytest.raises(switching.Refused, match=f"IN OUR RUN, {found}.*THE SCREEN MANAGER'S SAVED CONTEXT OR ITS STACK HOLDS OTHER BYTES.*{at:#x} "):
        switching.measured_on(blob, row)
    assert laid == [at] and row_process != SM


def test_the_word_the_dispatcher_stores_as_it_hands_the_machine_back_is_the_one_excepted():
    """WHAT THE HOLD EXCEPTS, AND NOTHING ELSE: where the screen manager is resumed, the two bytes at the stack pointer
    it stood parked at (the SR of its `rte`'s frame, which switchto stores) may have changed; the byte after them, or
    the same two bytes where the run merely ENDS, may not."""
    switches = switching.settled(PILOT).switches
    memory = bytearray(BASE_IMAGE[:0x100000])
    parked = takeover.spans_of(memory).parked
    for at, handed_back, refused in ((parked, True, False), (parked + 1, True, False), (parked + 2, True, True), (parked, False, True)):
        watch = switching.the_rom_s(switches)
        watch.hold_the_manager_s_spans(memory)
        other = bytearray(memory)
        other[at] ^= 1
        if not refused:
            watch.vet_the_manager_s_spans_stood(other, "here", handed_back=handed_back)
            continue
        with pytest.raises(switching.Refused, match=f"IN THE ROM'S RUN, here, THE SCREEN MANAGER'S SAVED CONTEXT OR ITS STACK.*{at:#x} "):
            watch.vet_the_manager_s_spans_stood(other, "here", handed_back=handed_back)


# ---- HOW A ROW LEAVES OUR SCREEN MANAGER PARKED: what holds it, and what does not ---------------------------------------------
def _left(first, last):
    return types.SimpleNamespace(manager_s_states=[first, last])


def test_our_screen_manager_s_last_park_is_held_where_it_can_be_and_refused_where_the_shores_disagree(blob, monkeypatch):
    """`tier3.how_the_screen_manager_is_left`, on states made by hand: parked as it began on both shores; elsewhere on
    both; REFUSED where the ROM's ends as it began and ours does not (or the reverse); and, where the ROM's ends in a
    state our build's own run is known to reach (`aes_takeover.left_as_ours`), held to THAT park byte for byte —
    refused with one byte of our live frames other."""
    how = tier3().how_the_screen_manager_is_left
    a, b, c = (takeover.State(bytes([n]) * 4, bytes([n]) * 8) for n in (1, 2, 3))
    assert how("a row", _left(a, a), _left(b, b)) == tier3().AS_IT_BEGAN
    assert how("a row", _left(a, c), _left(b, c)) == tier3().ELSEWHERE
    for ours, the_rom_s in ((_left(a, c), _left(b, b)), (_left(a, a), _left(b, c))):
        with pytest.raises(switching.Refused, match="LEAVES ITS SCREEN MANAGER PARKED .* AND OURS LEAVES OURS PARKED"):
            how("a row", ours, the_rom_s)
    monkeypatch.setattr(takeover, "left_as_ours", lambda _blob, state: a if state == c else None)
    assert how("a row", _left(b, a), _left(b, c), blob) == tier3().WHERE_A_ROW_BEGINS
    assert how("a row", _left(b, a), _left(b, a), blob) == tier3().ELSEWHERE        # ...no run of ours known to reach it
    with pytest.raises(switching.Refused, match="OURS IS NOT LEFT AS THAT RUN LEFT IT"):
        how("a row", _left(b, a._replace(live=bytes(8))), _left(b, c), blob)


# THE ROWS WHOSE ROM RUN LEAVES THE SCREEN MANAGER WHERE A NOTED RUN LEFT IT (`aes_takeover.PROVENANCE`): our build's
# own run to that state is made for the rows that BEGIN there, and our final park on these is held to it.
LEFT_WHERE_A_ROW_BEGINS = {
    "aes_ev_block, a wait for a key, the lock the desk's; the screen manager queues itself on the lock; then Return",
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager, which runs and waits; then Return",
    "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager; Return polled while it stands woken, before its turn",
    # ...and the recording across its turn (registered at wave 2's close): the very run a playback's machine is made
    # ours from — its own provenance — so our park where it ends is that run's, made again and found the same.
    "aes_ap_trecd, the mouse onto the menu bar and off it: the screen manager's turns inside the recording",
}


@pytest.mark.parametrize("name", sorted(_rows_with_the_screen_manager_ours()))
def test_how_each_row_leaves_our_screen_manager_parked_is_what_status_says(name):
    """THE CENSUS BEHIND STATUS'S STATEMENT (FLIP 4, "what remains unseen"), on the shipped blob, every row whose
    screen manager is ours: NONE ends with it parked as it began (every one of these runs moves it: a menu dropped, a
    message written, the lock queued on); FOUR end where a noted run left it and are held to our build's own run to
    that state; EVERY OTHER ends ELSEWHERE — our screen manager's final saved context and live frames on those rows
    are compared with nothing, and vetted only by the runs that wake it again from a park of that kind."""
    held = aes_event.SWITCHING_ROWS[name]
    blob = tier3().shipped_bench()
    for state in takeover.PROVENANCE:                   # ...every state a row begins from, made first (READ in a run)
        takeover.left_as_ours(blob, state) or takeover.made_for(state, blob)
    _measured, watch, _foreign = switching.measured_on(blob, held.row)
    expected = tier3().WHERE_A_ROW_BEGINS if name in LEFT_WHERE_A_ROW_BEGINS else tier3().ELSEWHERE
    assert watch.manager_left == expected, f"{name}: {watch.manager_left}"


def test_the_rows_held_to_a_known_park_are_rows_with_the_screen_manager_ours():
    assert LEFT_WHERE_A_ROW_BEGINS <= set(_rows_with_the_screen_manager_ours()) and len(LEFT_WHERE_A_ROW_BEGINS) == 4


def test_a_turn_s_line_says_what_the_rom_s_line_f_handler_is_of_it():
    """WHAT A TURN'S RATIO IS MADE OF IS PRINTED (FLIP 4's review): the ROM's side of a turn is its whole AES subtree
    by the table's convention — its text AND its Line-F handler's RAM copy — and the handler's part is tallied on
    the ROM's shore, a part of the ROM's own cycles in the window; the line says it, and the ratio net of it. A
    turn tallied without it (a slice's) says nothing."""
    measured = tier3().measure(switching.table_row(PILOT), tier3().RomBench())
    (turn,) = measured.turns
    assert 0 < turn.line_f < turn.the_rom_s and 0.30 < turn.line_f / turn.the_rom_s < 0.40
    (line,) = tier3()._turn_lines(measured, 0)
    assert f"the ROM's Line-F handler alone is {turn.line_f} of its {turn.the_rom_s}" in line
    assert f"net of it {(turn.ours + turn.glue) / (turn.the_rom_s - turn.line_f):.2f}" in line
    assert tier3()._line_f_of(turn._replace(line_f=0)) == ""


def test_a_store_before_the_run_s_first_stop_is_held_too(blob, monkeypatch):
    """OUR SHORE IS HELD FROM ITS ENTRY, not from the watch's first stop: a byte of the screen manager's dead stack
    made other after the overlay is laid and before our run's first instruction (laid under the kit's own call: what
    a store of the row's process before its first dispatch would leave) is refused where the screen manager is first
    resumed."""
    at, laid = takeover.spans_of(BASE_IMAGE).stack[0] + 0x14, []
    kit_s = tier3().rom_bench.RomBench._call

    def entered(self, image, *arguments, **named):
        if not laid:
            image[at] ^= 0xff
            laid.append(at)
        return kit_s(self, image, *arguments, **named)
    monkeypatch.setattr(tier3().rom_bench.RomBench, "_call", entered)
    with pytest.raises(switching.Refused, match=f"IN OUR RUN, where the screen manager is resumed.*{at:#x} "):
        switching.measured_on(blob, PILOT)


def test_a_row_whose_screen_manager_is_ours_drops_its_saved_context_whole_or_is_refused(blob):
    """OUR SHORE PUTS NONE OF THE SAVED CONTEXT BACK (the ROM's savestate stores every byte of it wherever its screen
    manager parks, so the row drops it whole): a row that names only a part of it is refused by name before its runs."""
    made = switching.settled(PILOT)
    (lo, hi), = [(at, end) for at, end, why in made.drops if why == takeover.CONTEXT_WHY]
    tier3().screen_manager_made_ours(blob, made.pokes, made.drops)
    in_part = tuple((at, end - 2, why) if why == takeover.CONTEXT_WHY else (at, end, why) for at, end, why in made.drops)
    with pytest.raises(AssertionError, match="our shore puts none of it back"):
        tier3().screen_manager_made_ours(blob, made.pokes, in_part)
    assert (lo, hi) == takeover.spans_of(make_image(made.pokes)).context
