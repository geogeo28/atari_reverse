"""THE ROWS THAT SWITCH (`test/aes_switching.py`, `bench/tier3.py`'s foreign windows): a call that blocks, leaves by
the dispatcher and is woken through it, as ONE RETURNING RUN on both shores — held, and each of its refusals RED.

THE PILOTS are `test_aes_evdisp_model.WOKEN_ROWS`, registered and priced like any row: a key typed ahead (no
delivery), a key and a delay's ticks DELIVERED AT AN IDLE of our own dispatcher, a wait during which THE SCREEN
MANAGER RUNS — the snapshot's own other process, the ROM's code on both shores: a FOREIGN WINDOW — and a key
DELIVERED AT A POLL THAT IS NO IDLE, while that process stands woken. Here:

  * each row's premise on the ROM's own run, and its second differential ON BOTH BLOBS (the table prices a row on
    one), its cycles pinned;
  * what the table reads of each: its own cycles, its foreign windows;
  * THE WATCH'S REFUSALS, each made to happen: a delivery never handed, one laid over another machine, a run that
    never waited, a fork queued where the dispatcher changes hands, a poll that is no idle's;
  * THE FOREIGN WINDOW'S: a delivery relocated for the ROM's forker (the mixture the rule exists for), the general
    guard without the window declared, the code slot a foreign process stored, two shores that ran other windows;
  * A DOOR USER'S CALL LEFT OPEN ACROSS THE SWITCH — wind_update handing the lock over inside unsync's call — priced on
    TWO COUNTS. A Tier 3 measurement of the machinery, not a registered row: a door user under the host's model is
    the wave's own work (its companion), and the same call is held on the host at dsptch (`test_aes_wm_update`).
"""
import itertools
import re
import types

import pytest

from harness import addrs, bench_tier3, make_image
from recreate_kit import rom_bench

import aes
import aes_event
import aes_evinput as evinput
import aes_evlib as evlib
import aes_switch
import aes_switching as switching
import case
import test_aes_evdisp_model as model
import test_aes_wm_update as wm_update
import test_boot_snapshot
import test_status

SHELL, SCREEN_MANAGER = aes_switch.SHELL, aes_switch.SCREEN_MANAGER
ROWS = {row.label: row for row in model.WOKEN_ROWS}
FOREIGN, AT_A_POLL = model.THROUGH_THE_SCREEN_MANAGER, model.POLLED_WHILE_THE_MANAGER_STANDS_WOKEN
BENCH, SHIPPED = "bench", "bench_shipped"
# WHAT EACH PILOT IS, read off the ROM's own run of it (`aes_switching.Premise`): the idles it takes a delivery at,
# how many idles it makes, the process that makes the call, the processes its dispatcher enters, and what the call
# answers (a key's wait the key; a delay's nothing: 0).
RETURN, NOTHING = evinput.RETURN_KEY_CODE, 0
Premise, Priced = switching.Premise, switching.Priced
PREMISES = {
    model.A_KEY_TYPED_AHEAD_LABEL: Premise((), 1, SHELL, (SHELL,), RETURN),
    model.WOKEN_BY_A_KEY: Premise((0,), 1, SHELL, (SHELL,), RETURN),
    model.A_DELAY_RUN_OUT: Premise((0,), 1, SHELL, (SHELL,), NOTHING),
    FOREIGN: Premise((0, 1), 2, SHELL, (SCREEN_MANAGER, SHELL), RETURN),
    AT_A_POLL: Premise((0,), 1, SHELL, (SCREEN_MANAGER, SHELL), RETURN, at_polls=(model.THE_POLL_AFTER_THE_FIRST_IDLE,)),
}
# THE WHOLE RUN'S CYCLES, the ROM's and ours net of the entry both share, by blob — the second differential's own
# measurement (`aes_switching.measured_on`). A row that moves says why: a frame, a path, the dispatcher itself.
WHOLE_RUN = {
    model.A_KEY_TYPED_AHEAD_LABEL: {BENCH: (31690, 26556), SHIPPED: (31690, 26242)},
    model.WOKEN_BY_A_KEY: {BENCH: (31690, 26556), SHIPPED: (31690, 26242)},
    model.A_DELAY_RUN_OUT: {BENCH: (30166, 25576), SHIPPED: (30166, 25264)},
    FOREIGN: {BENCH: (831626, 826684), SHIPPED: (831626, 826416)},
    AT_A_POLL: {BENCH: (831668, 823942), SHIPPED: (831668, 823798)},
}
# ...and WHAT THE TABLE PRICES (`aes_switching.Priced`; `tier3.measure`, the shipped blob: ev_block's C reaches a
# transcribed core): each shore's OWN cycles, no second count (ev_block's own rows call no rebound entry), and the
# row's foreign windows — how many, their whole cycles, their cycles in the AES's text.
NO_WINDOW, ONE_COUNT = switching.NO_WINDOW, (None, None)
PRICED = {
    model.A_KEY_TYPED_AHEAD_LABEL: Priced((11046, 17146), *ONE_COUNT, NO_WINDOW),
    model.WOKEN_BY_A_KEY: Priced((11046, 17146), *ONE_COUNT, NO_WINDOW),
    model.A_DELAY_RUN_OUT: Priced((11088, 16642), *ONE_COUNT, NO_WINDOW),
    FOREIGN: Priced((13018, 18972), *ONE_COUNT, (1, 797112, 155862)),
    AT_A_POLL: Priced((17368, 26258), *ONE_COUNT, (1, 782086, 148618)),
}
# THE ONE CODE SLOT THE SCREEN MANAGER'S RUN STORES: the ROM's own keyboard poll, inside the foreign window, queues
# the ROM's kchange for the Return it finds — in the fork queue's third entry (the two before it held the mouse's).
THE_SLOT_THE_ROM_S_POLL_QUEUED = aes_event.FORK_CODE_SLOTS[2]


tier3, table_row = bench_tier3, switching.table_row


def unregistered(row, **replaced):
    """A SWITCHING ROW NO REGISTRY HOLDS, as Tier 3 reads one: settled from the ROM's own runs like a registered row,
    for a case that measures the machinery over another run than a pilot's."""
    made = switching.settled(row)
    verified = case.verified_row(switching.row_name(row), getattr(addrs, row.name), {}, made.pokes, delivered=made.switches)
    unanswered = {} if row.answered else {"returns": tier3().RETURNS_NOTHING}
    return tier3()._row(verified)._replace(dropped=made.drops, **unanswered, **replaced)


# ---- THE PILOTS ------------------------------------------------------------------------------------------------------------
def test_every_pilot_is_a_registered_row_that_switches():
    """(The registry holds every battery's rows that switch — the waits', ev_multi's, the door users': each battery
    pins its own. Here, the pilots: each registered, each with its premise and both its pins.)"""
    assert set(map(switching.row_name, ROWS.values())) <= set(aes_event.SWITCHING_ROWS)
    assert ROWS.keys() == PREMISES.keys() == WHOLE_RUN.keys() == PRICED.keys()


@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_of_a_pilot_is_what_its_name_says(label):
    """THE PREMISE, on the ROM's run through its own dispatcher over the row's settled machine: it returns to the
    process that made the call, each interrupt taken at an idle, the dispatcher entering exactly the processes named
    — and the row carries that run's deliveries (`aes_switching.vet_the_premise`: the settling changed nothing an
    interrupt reads or writes)."""
    switching.vet_the_premise(ROWS[label], PREMISES[label])


@pytest.mark.parametrize("label", ROWS)
def test_a_pilot_is_parked_by_our_own_dispatcher_and_woken_on_both_blobs(label, blob):
    """THE SECOND DIFFERENTIAL OF A REAL SWITCH, on each blob: our twin blocks in OUR mwait, OUR dsptch and disp park
    it, the row's interrupts land at the idles the ROM's run took them at, and the process is resumed inside our
    mwait — BY OUR SWITCHTO where no other process ran; AFTER THE SCREEN MANAGER'S TURN BY THE ROM'S DISPATCHER, on
    both shores (that process's own dispatch: in neither column). The image the ROM's but for the row's drops, the
    answer, every callee-saved register back (GCC's frame across savestate and switchto) — and, on THIS path too,
    the foreign windows held equal to the cycle and our run out of the AES's ROM everywhere else."""
    switching.vet_on_a_blob(blob, ROWS[label], PREMISES[label], PRICED[label].windows, WHOLE_RUN[label])


def _the_window_line_under(table, row):
    """The foreign-window line `table` (the text of the bench's file) prints UNDER THE ROW `row`, or None — the
    indented lines that follow that row's own line, up to the next row's. Refused by name where the file has no
    line for the row: it predates the tree."""
    its_line = re.compile(rf"^\S.*\${switching._entry(row):x}\s+{re.escape(row.label)}\s+\d+/\d+\s")
    lines = table.splitlines()
    at = next((index for index, line in enumerate(lines) if its_line.match(line)), None)
    assert at is not None, (f"{test_status.BENCH_TABLE} has no line for `{switching.row_name(row)}`: the file predates "
                            f"the tree — run `make bench`")
    under = itertools.takewhile(lambda line: line[:1].isspace(), lines[at + 1:])
    return next((line for line in under if "foreign window(s)" in line), None)


@pytest.mark.parametrize("label", ROWS)
def test_the_table_prices_a_pilot_on_its_own_process_s_cycles(label):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's OWN cycles on each shore — ours at the
    blob's PCs, the ROM's in the AES's text less its foreign windows — under the bar, and the windows themselves:
    equal on the two shores to the cycle (the measurement refuses otherwise), in neither own column."""
    measured = switching.vet_the_table_s_price(ROWS[label], PRICED[label])
    windows, whole, in_the_aes = PRICED[label].windows
    said = (f"{windows} foreign window(s): another process ran {whole} cycles of the ROM's own code on both shores "
            f"({in_the_aes} in the AES's text)")
    assert not windows or said in tier3()._foreign_line(measured, 0)
    # ...which the table SAYS under THIS row (`make bench`'s own file: the suite's prerequisite) — and says nothing
    # of the kind under a row with no window.
    line = _the_window_line_under(test_status.BENCH_TABLE.read_text(), ROWS[label])
    assert (line is not None and said in line) if windows else line is None, (
        f"{label}: the bench's file says {line!r} under the row — if it predates the tree, run `make bench`")


def test_the_table_says_a_foreign_window_under_every_row_that_has_one_and_under_no_other():
    """...AND OVER THE WHOLE REGISTRY: one such line a row whose dispatcher enters another process than its own."""
    table = test_status.BENCH_TABLE.read_text()
    with_a_window = [held for held in aes_event.SWITCHING_ROWS.values() if set(held.entered) != {held.switches.process}]
    said = table.count("foreign window(s)")
    assert said == len(with_a_window), (
        f"{test_status.BENCH_TABLE} says a foreign window under {said} row(s) where the registry holds "
        f"{len(with_a_window)} whose run enters another process — if the file predates the tree, run `make bench`")


A_HIGH_WORD_NO_CALLER_READS = 0x10000


@pytest.mark.parametrize("astray, refused", ((dict(idles=2), "the C's run idled 2 times, the ROM's 1"),
                                             (dict(polls=3), "the C's run polled 3 times, the ROM's 2"),
                                             (dict(answer=evinput.RETURN_KEY_CODE ^ 1), "answers 0x1c0c, the ROM's run 0x1c0d"),
                                             (dict(answer=evinput.RETURN_KEY_CODE | A_HIGH_WORD_NO_CALLER_READS), None)),
                         ids=("an idle more", "a poll more", "another answer", "the same answer under another high word"))
def test_a_companion_holds_the_idles_and_the_answer_beside_the_image(monkeypatch, astray, refused):
    """A ROW'S TIER 1 (`aes_switching.companion`) holds more than the image: the C's run handed back as one that
    idled once more, polled the keyboard once more, or answered another key, over the very image the ROM's run
    leaves, is refused by name — the answer AT THE WIDTH ITS CORE DECLARES: an Alcyon `int` is D0's word, and what
    lies above it is nobody's."""
    modelled = aes_switch.modelled
    monkeypatch.setattr(aes_switch, "modelled", lambda *run, **named: modelled(*run, **named)._replace(**astray))
    if refused is None:
        assert switching.companion(ROWS[model.WOKEN_BY_A_KEY]).answer == astray["answer"]
        return
    with pytest.raises(AssertionError, match=refused):
        switching.companion(ROWS[model.WOKEN_BY_A_KEY])


THE_DISPATCHER_S_STACK, THE_MASK_WORD = aes_switch.DISPATCHER_STACK, aes.LINE_F_MASK_WINDOW[0][:2]


@pytest.mark.parametrize("laid_back", (THE_DISPATCHER_S_STACK, THE_MASK_WORD), ids=("the dispatcher's stack", "the Line-F mask word"))
def test_each_part_a_foreign_turn_is_not_laid_back_over_is_needed_by_a_companion(monkeypatch, laid_back):
    """`aes_switch.STORED_BY_NO_C` IS TWO THINGS, EACH NEEDED: the screen manager's turn — the ROM's own code in the
    host's run — stores the ROM's dispatcher frames and the Line-F handler's mask, which the ROM's whole run goes on
    to rewrite and no C of ours does. Laid back over the C's image, either one makes the pilot's companion differ
    from the ROM's run on no fault of the C; and the rule is those two and no third (the SR save words were in it,
    and no companion needed them left out: they are laid back and compared)."""
    assert set(aes_switch.STORED_BY_NO_C) == {THE_DISPATCHER_S_STACK, THE_MASK_WORD}
    switching.companion(ROWS[FOREIGN])
    monkeypatch.setattr(aes_switch, "STORED_BY_NO_C", tuple(part for part in aes_switch.STORED_BY_NO_C if part != laid_back))
    with pytest.raises(AssertionError, match="differ"):
        switching.companion(ROWS[FOREIGN])


def test_the_sweeps_replay_a_switching_row_watched_at_its_dispatcher():
    """THE ORIGINAL OF A REGISTERED ROW, as every sweep runs it (`test_boot_snapshot.run_original`): a row that
    switches is replayed WATCHED AT THE DISPATCHER (`aes_event.delivering`), its deliveries laid at its idles — the
    run that returns Return, in the memory the ROM's scheduled run leaves."""
    row = ROWS[FOREIGN]
    registered = case.registered_case(switching.row_name(row))
    final, _writes, regs = test_boot_snapshot.run_original(registered)
    assert regs["d0"] & aes.WORD_MASK == evinput.RETURN_KEY_CODE
    reference = switching.scheduled(row, switching.settled(row).pokes)
    assert bytes(final[:addrs.ST_RAM_BYTES]) == bytes(reference.memory[:addrs.ST_RAM_BYTES])


# ---- WHAT A ROW THAT SWITCHES CARRIES ---------------------------------------------------------------------------------------
def test_what_a_switching_row_is_taken_through_is_never_read_as_door_calls():
    """`aes_event.Switches` stands where a door row's `{door call: (found, wrote)}` stands, and is no dict: a reader
    that indexes it by a door call's ordinal fails where it reads, instead of laying an idle's interrupt at a call."""
    switches = switching.settled(ROWS[model.WOKEN_BY_A_KEY]).switches
    assert aes_event.switching(switches) is switches and aes_event.at_door_calls(switches) == {}
    assert aes_event.switching({0: ({}, {})}) is None and aes_event.at_door_calls({0: ({}, {})}) == {0: ({}, {})}
    assert aes_event.switching({}) is None and aes_event.at_door_calls(None) == {}
    assert aes_event.Switches({}, 1, SHELL), "true with nothing delivered too (a key typed ahead): the row still switches"
    with pytest.raises(TypeError):
        switches[min(switches.at_idles)]                # ordinal 0, read as a door call's
    with pytest.raises(TypeError):
        min(switches)                                   # ...or walked as `{door call: ...}`


def test_a_sliced_session_that_switches_is_refused_by_name():
    """A SLICE'S MARKS ARE ONE PROCESS'S: no mark is taken across a dispatch, so a sliced row whose run switches is
    refused where it would be measured — never cut between two marks one of which a foreign window hides."""
    a_slice = next(iter(aes_event.SLICED_ROWS.values()))
    with pytest.raises(AssertionError, match="a session cut into slices whose run SWITCHES"):
        tier3().measure(table_row(ROWS[model.WOKEN_BY_A_KEY])._replace(slice=a_slice), tier3().RomBench())


# ---- THE WATCH'S REFUSALS ---------------------------------------------------------------------------------------------------
def _our_run(blob, row, switches, relocated=None):
    """Our twin of `row` on `blob` watched through `switches` — the row's own, or a case's tampered ones."""
    made = switching.settled(row)
    if relocated is None:
        relocated = tier3().deliveries_for_our_shore(switches.at_idles, blob.elf, switching._core(row))
    watch = switching.ours(blob, switches, relocated,
                           relocated_polls=tier3().deliveries_for_our_shore(switches.at_polls, blob.elf, switching._core(row)))
    measured = blob.measure(switching._entry(row), switching._core(row), (0, *row.arguments), {}, made.pokes,
                            returns=tier3().CALL[row.name].returns, dropped=made.drops, watch=watch,
                            original_watch=switching.the_rom_s(made.switches, switching._entry(row)))
    return measured, watch


def test_a_delivery_our_run_is_never_handed_is_refused_at_the_idle_it_would_wait_at_for_ever(blob):
    """THE IDLE RULE: held to the row's idles and handed NO delivery, our run passes the idle the ROM's run made and
    is refused at the next, by name — the call would block. (It used to be the oracle's budget, sixteen million
    instructions of our dispatcher's idle loop.)"""
    row = ROWS[model.WOKEN_BY_A_KEY]
    never_handed = switching.settled(row).switches._replace(at_idles={})
    with pytest.raises(switching.Refused, match=r"idle 1 \(our own dispatcher.*idles once more than the ROM's own run did \(1\)"):
        _our_run(blob, row, never_handed)


def test_a_delivery_laid_over_another_machine_than_the_rom_s_is_refused_where_it_lands(blob):
    """A DELIVERY IS CHECKED BEFORE IT IS LAID: one byte of what the ROM's run held where the key's interrupt writes,
    changed — our run's memory is then not the machine the delivery was taken over, and laying it would erase that."""
    row = ROWS[model.WOKEN_BY_A_KEY]
    switches = switching.settled(row).switches
    found, wrote = switches.at_idles[0]
    first = min(found)
    other = {**found, first: bytes([found[first][0] ^ 1]) + found[first][1:]}
    with pytest.raises(AssertionError, match="differs from the ROM's where an interrupt is delivered at idle 0"):
        _our_run(blob, row, switches, relocated={0: (other, wrote)})


def test_a_run_that_makes_fewer_idles_than_the_row_says_is_refused_as_it_ends():
    """...AND THE OTHER WAY: a run that returned having waited LESS than the row says (a twin that never blocked
    where the ROM does would be one) is refused when it has ended — here the ROM's own run of the key's wait, held
    to a row that says two idles."""
    row = ROWS[model.WOKEN_BY_A_KEY]
    made = switching.settled(row)
    watch = switching.the_rom_s(made.switches._replace(idles=2), switching._entry(row))
    rom_bench.watched_original(make_image(made.pokes), switching._entry(row), watch)
    rom_bench.vet_the_run_just_made("the ROM's replay of the key's wait")
    with pytest.raises(switching.Refused, match=r"the run made 1 idle\(s\) where the ROM's own makes 2"):
        watch.vet_ended("the ROM's replay")


# ---- A DELIVERY AT A POLL THAT IS NO IDLE: named by the poll's ordinal, held ON A BLOB like an idle's ---------------------
# (The derivation's refusals, the ROM's replay and the host's model are held where no registering battery is imported:
# `test_aes_switching_registrar.py`.)
def test_a_poll_s_delivery_carries_how_the_machine_stood_there_and_is_refused_where_it_stands_otherwise(blob):
    """A DELIVERY AT A POLL IS CHECKED AGAINST WHAT IDLE TESTS (`aes_switch.what_idle_tests`), beside the bytes it
    writes: Return was taken with nothing ready, THE SCREEN MANAGER WOKEN and nothing queued — and our run is refused
    by name where its machine stands otherwise at that poll (an idle that moved the woken to the ready list BEFORE it
    polled holds the manager READY there: the same key, the same final image, another place in the loop). RED: the
    row's delivery handed over as if the ROM's run had found the manager ready."""
    row = ROWS[AT_A_POLL]
    switches = switching.settled(row).switches
    found, wrote = switches.at_polls[model.THE_POLL_AFTER_THE_FIRST_IDLE]
    long_at = lambda at: int.from_bytes(found[at], "big") & aes_event.OS_BUS_ADDR_MASK     # noqa: E731
    assert (long_at(aes.AES_RLR), long_at(aes.AES_DRL), found[aes.AES_FORK_COUNT]) == (0, SCREEN_MANAGER, bytes(aes.WORD_BYTES))
    _measured, watch = _our_run(blob, row, switches)
    assert (watch.polls, watch.idles) == (switches.polls, switches.idles)
    moved_first = {**found, aes.AES_RLR: found[aes.AES_DRL], aes.AES_DRL: found[aes.AES_RLR]}
    astray = switches._replace(at_polls={model.THE_POLL_AFTER_THE_FIRST_IDLE: (moved_first, wrote)})
    with pytest.raises(AssertionError, match=r"differs from the ROM's where an interrupt is delivered at poll 1 \(our own dispatcher"):
        _our_run(blob, row, astray)


def test_a_poll_s_delivery_our_run_is_never_handed_or_handed_a_poll_late_is_refused(blob):
    """...AND BOTH SHORES ARE HELD TO THE POLL, as to an idle: our run handed no delivery there passes the poll, the
    screen manager has its turn, and the machine idles once more than the ROM's run did — refused by name; a run
    held to one poll MORE than it makes is refused as it ends; and a watch made with a delivery at a poll the ROM's
    run never makes is refused where it is made (it would never be laid)."""
    row = ROWS[AT_A_POLL]
    switches = switching.settled(row).switches
    with pytest.raises(switching.Refused, match="idles once more than the ROM's own run did"):
        _our_run(blob, row, switches._replace(at_polls={}))
    with pytest.raises(switching.Refused, match=rf"the run's dispatcher polled {switches.polls} time\(s\) where the ROM's own run "
                                                rf"polls {switches.polls + 1}"):
        _measured, watch = _our_run(blob, row, switches._replace(polls=switches.polls + 1))
        watch.vet_ended("our run")
    delivery, = switches.at_polls.values()
    for never_made in (switches.polls, -1):
        with pytest.raises(switching.Refused, match=rf"a delivery is named at poll \[{never_made}\] of a run that makes 4 poll"):
            switching.the_rom_s(switches._replace(at_polls={never_made: delivery}))
    with pytest.raises(switching.Refused, match="a delivery is named at poll 0, which is this idle"):
        _our_run(blob, row, switches._replace(at_polls={0: delivery}))


A_STACK_POINTER = 0x7FF00               # anywhere in the run's own stack band: where a staged stop reads its frame
A_FOREIGN_RESUME = addrs.AES_ROM_EV_MWAIT_RESUMED


def _staged_at_an_rte(process, queued):
    """A LABELLED, STAGED STOP — no run makes it: the machine at switchto's `rte` about to enter `process`, `queued`
    forks in the queue, the frame under SP resuming at mwait."""
    memory = make_image(aes_event.machine())
    memory[aes.AES_RLR:aes.AES_RLR + aes.LONG_BYTES] = process.to_bytes(aes.LONG_BYTES, "big")
    memory[aes.AES_FORK_COUNT:aes.AES_FORK_COUNT + aes.WORD_BYTES] = queued.to_bytes(aes.WORD_BYTES, "big")
    at = A_STACK_POINTER + aes_event.EXCEPTION_FRAME_PC
    memory[at:at + aes.LONG_BYTES] = A_FOREIGN_RESUME.to_bytes(aes.LONG_BYTES, "big")
    return memory


def test_a_fork_queued_where_the_dispatcher_changes_hands_is_refused():
    """THE PREMISE OF A FOREIGN WINDOW, HELD AT ITS EDGES: disp runs forker until the queue is empty before it enters
    a process, so no fork is pending when another build's dispatcher takes over — a queue entry's CODE is one
    build's, and the other's forker would `jsr` it. A machine (staged: no run makes it) entering the screen manager
    with a fork queued is refused by name; with none it opens a window, and no door entry is a stop inside it."""
    switches = aes_event.Switches({}, 1, SHELL)
    entries = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS)
    watch = switching.the_rom_s(switches, inner=entries)
    assert frozenset(aes_event.ENTRIES) <= watch.first
    memory = _staged_at_an_rte(SCREEN_MANAGER, queued=0)
    assert watch.stopped(switching.ROM_RTE, A_STACK_POINTER, memory) == {A_FOREIGN_RESUME}
    armed = watch.stopped(A_FOREIGN_RESUME, A_STACK_POINTER, memory)
    assert not armed & frozenset(aes_event.ENTRIES), "a door call inside a foreign window is another process's"
    assert {switching.ROM_POLL, switching.ROM_RTE} <= armed and watch.entered == [SCREEN_MANAGER]
    with pytest.raises(switching.Refused, match="ended inside another process"):
        watch.vet_ended("a run left in the screen manager")
    queued = switching.the_rom_s(switches)
    memory = _staged_at_an_rte(SCREEN_MANAGER, queued=1)
    queued.stopped(switching.ROM_RTE, A_STACK_POINTER, memory)
    with pytest.raises(switching.Refused, match=r"a foreign process is entered .* with 1 fork\(s\) queued"):
        queued.stopped(A_FOREIGN_RESUME, A_STACK_POINTER, memory)


def test_our_keyboard_poll_is_an_idle_only_where_our_idle_calls_it(blob):
    """`aes_chkkbd` IS ev_multi's POLL TOO: a stop at its first instruction is the dispatcher's idle only where the
    return address under SP lies in `aes_idle` — else no idle is counted and no delivery laid, and the entry is a
    stop again once the poll has returned (a staged stop: the machine waits, the caller is not idle)."""
    dispatcher = switching.our_dispatcher(blob)
    watch = switching.ours(blob, aes_event.Switches({}, 0, SHELL), {})
    memory = make_image(aes_event.machine())
    for at in (aes.AES_RLR, aes.AES_DRL):
        memory[at:at + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    assert aes_switch.waits_for_an_interrupt(memory), "the premise: nothing ready, nothing woken, nothing queued"
    elsewhere = blob.entry("aes_ev_multi") + aes.WORD_BYTES
    memory[A_STACK_POINTER:A_STACK_POINTER + aes.LONG_BYTES] = elsewhere.to_bytes(aes.LONG_BYTES, "big")
    armed = watch.stopped(dispatcher.poll, A_STACK_POINTER, memory)
    assert watch.idles == 0 and elsewhere in armed and dispatcher.poll not in armed
    assert dispatcher.poll in watch.stopped(elsewhere, A_STACK_POINTER, memory)
    in_idle = dispatcher.idle[0] + aes.WORD_BYTES
    memory[A_STACK_POINTER:A_STACK_POINTER + aes.LONG_BYTES] = in_idle.to_bytes(aes.LONG_BYTES, "big")
    with pytest.raises(switching.Refused, match="idles once more than the ROM's own run did \\(0\\)"):
        watch.stopped(dispatcher.poll, A_STACK_POINTER, memory)


# ---- THE FOREIGN WINDOW -----------------------------------------------------------------------------------------------------
TWICE = "a wait for a key; the mouse onto the bar and off it — the screen manager entered twice; then Return"


def _entered_twice():
    """The key's wait during which the screen manager runs TWICE: the second interrupt — the mouse off the bar, a
    fork function's code in the queue — is delivered INSIDE the foreign window, at the ROM's idle."""
    call = model.CASES[TWICE]
    return switching.SwitchingRow(TWICE, call.name, call.arguments, call.machine, call.at_idle)


def test_a_delivery_is_relocated_by_who_takes_it_and_a_foreign_window_holds_no_cycle_of_ours(monkeypatch):
    """THE RULE'S REASON, MEASURED AND THEN BROKEN. The screen manager entered twice: both shores run it as ONE
    window (the ROM's dispatcher re-enters it without leaving), cycle for cycle. Then every delivery relocated for
    OUR forker, the one the ROM's idle takes too: the ROM's forker `jsr`s our mchange inside the window — the image
    compare still passes (our mchange is verified) and the row would be priced on a mixture; refused by name."""
    row = unregistered(_entered_twice())
    measured = tier3().measure(row, tier3().RomBench())
    assert tuple(tier3().foreign_of(measured))[0] == 1 and measured.own_cycles == PRICED[FOREIGN].own
    ours = switching.ours

    def relocated_everywhere(blob, switches, relocated, *watching, **named):
        return ours(blob, switches._replace(at_idles=relocated), relocated, *watching, **named)
    monkeypatch.setattr(switching, "ours", relocated_everywhere)
    with pytest.raises(AssertionError, match=r"cycles of OUR build ran inside the foreign windows"):
        tier3().measure(row, tier3().RomBench())


def test_without_its_foreign_window_declared_the_general_guard_refuses_the_row():
    """THE ONE PLACE OUR RUN MAY EXECUTE THE AES'S ROM: the guard holds our run's cycles there to exactly the row's
    foreign windows (which the measurement held equal to the ROM's own). Asked of the same runs with no window
    declared, it refuses the row by name — as it refuses any C that `jsr`s the ROM's AES."""
    row, bench = table_row(ROWS[FOREIGN]), tier3().RomBench()
    measured = tier3().measure(row, bench)
    in_the_aes = PRICED[FOREIGN].windows[2]
    assert tier3().foreign_of(measured).in_the_aes == in_the_aes
    tier3().vet_our_run_kept_out_of_the_aes(row, bench, measured)
    with pytest.raises(AssertionError, match=f"OUR run spent {in_the_aes} cycles at the PCs of the AES's own ROM where the row\\s+declares 0"):
        tier3().vet_our_run_kept_out_of_the_aes(row, bench)


def test_a_window_one_cycle_short_leaves_a_cycle_of_ours_in_the_aes_and_is_refused(monkeypatch):
    """...and the measurement's own equality: the windows read one cycle short (in the AES's text), our run has
    spent a cycle in the AES's ROM that no window accounts for."""
    alike = tier3()._vet_switched_alike

    def one_short(*runs):
        foreign = alike(*runs)
        return foreign._replace(in_the_aes=foreign.in_the_aes - 1)
    monkeypatch.setattr(tier3(), "_vet_switched_alike", one_short)
    with pytest.raises(AssertionError, match="our build spent 1 cycles inside the AES's own ROM spans"):
        tier3().measure(table_row(ROWS[FOREIGN]), tier3().RomBench())


def test_the_code_a_foreign_process_queued_is_no_relocation_our_build_left_unapplied(blob, monkeypatch):
    """A FORK CODE THE ROM'S OWN POLL QUEUED inside the foreign window is the ROM's — no code of ours stored it — and
    the rule "no slot names the ROM after our run" excepts exactly that slot while it holds exactly that code
    (`Switching.foreign_codes`). With the window's stores unread, the rule refuses the run as it must."""
    row = ROWS[FOREIGN]
    _measured, watch, _foreign = switching.measured_on(blob, row)
    assert watch.foreign_codes == {THE_SLOT_THE_ROM_S_POLL_QUEUED: addrs.AES_ROM_KCHANGE}
    monkeypatch.setattr(switching.Switching, "_code_slots", staticmethod(lambda memory: dict.fromkeys(switching.CODE_SLOTS, 0)))
    with pytest.raises(AssertionError, match="OUR run left THE ROM'S OWN address 0xfe5180 in a fork function's code"):
        switching.measured_on(blob, row)


def test_the_exception_for_a_foreign_code_is_one_slot_holding_one_code():
    """...slot by slot and code by code: the ROM's kchange in ANOTHER slot than the window stored, or another ROM
    routine in that slot, is a relocation left un-applied like any other."""
    relocation = tier3().Relocation(aes_event.FORK_CODES.what, aes_event.FORK_CODE_SLOTS,
                                    {addrs.AES_ROM_KCHANGE: 0x31000, addrs.AES_ROM_MCHANGE: 0x32000})
    stored, another = aes_event.FORK_CODE_SLOTS[2], aes_event.FORK_CODE_SLOTS[3]
    foreign = {stored: addrs.AES_ROM_KCHANGE}

    def holding(codes):
        memory = bytearray(make_image({}))
        for slot in aes_event.FORK_CODE_SLOTS:
            memory[slot:slot + aes.LONG_BYTES] = codes.get(slot, 0).to_bytes(aes.LONG_BYTES, "big")
        return memory
    tier3().vet_no_slot_names_the_rom("a run", holding({stored: addrs.AES_ROM_KCHANGE}), [relocation], foreign=foreign)
    for codes in ({another: addrs.AES_ROM_KCHANGE}, {stored: addrs.AES_ROM_MCHANGE}):
        with pytest.raises(AssertionError, match="OUR run left THE ROM'S OWN address"):
            tier3().vet_no_slot_names_the_rom("a run", holding(codes), [relocation], foreign=foreign)


def _a_run(entered, foreign):
    return types.SimpleNamespace(entered=list(entered), foreign=list(foreign), vet_ended=lambda who: None)


def test_two_shores_that_entered_other_processes_or_ran_other_windows_are_refused():
    """THE TWO RUNS ARE ONE SCHEDULE (`tier3._vet_switched_alike`), over stand-in watches: the same processes in the
    same order, the same windows to the cycle — whole and in the AES's text — and no cycle of our build inside one."""
    alike = tier3()._vet_switched_alike
    the_rom_s = _a_run([SCREEN_MANAGER, SHELL], [(797112, 155862)])
    assert alike("a row", _a_run([SCREEN_MANAGER, SHELL], [(797112, 155862, 0)]), the_rom_s) == (1, 797112, 155862)
    with pytest.raises(AssertionError, match="our dispatcher entered the processes"):
        alike("a row", _a_run([SHELL], [(797112, 155862, 0)]), the_rom_s)
    with pytest.raises(AssertionError, match="another process ran another run on the two shores"):
        alike("a row", _a_run([SCREEN_MANAGER, SHELL], [(797112, 155860, 0)]), the_rom_s)
    with pytest.raises(AssertionError, match="another process ran another run on the two shores"):
        alike("a row", _a_run([SCREEN_MANAGER, SHELL], [(797110, 155862, 0)]), the_rom_s)
    with pytest.raises(AssertionError, match=r"\[20\] cycles of OUR build ran inside the foreign windows"):
        alike("a row", _a_run([SCREEN_MANAGER, SHELL], [(797112, 155862, 20)]), the_rom_s)


# ---- A DOOR USER'S CALL, OPEN ACROSS THE SWITCH -------------------------------------------------------------------------------
THE_LOCK_HANDED_OVER = "the lock handed to the screen manager, which waits for it: a yield inside unsync's call"
# wind_update(END_UPDATE) over a lock the screen manager waits for: 474 cycles of the ROM's own round its call of
# unsync, 150 of ours — and the call itself, a yield through the whole dispatcher, in both own columns.
THE_CALLER_S_OWN, ITS_OWN = (150, 474), (4974, 7826)
THE_LOCK_S_RELEASE = switching.SwitchingRow(THE_LOCK_HANDED_OVER, wm_update.WM_UPDATE, (wm_update.END_UPDATE,),
                                            wm_update.waited_on, {}, answered=False)


def test_a_door_user_s_call_stays_open_across_the_switch_and_is_priced_on_two_counts():
    """PER-PROCESS DOOR CALLS: wind_update's call of unsync (a rebound entry: an arrival on both shores) LEAVES BY THE
    DISPATCHER — unsync hands the lock over and yields — and is closed when its process is resumed, on our shore
    through OUR dsptch, disp, savestate and switchto. Nothing is refused "inside a door call"; the call's cost, the
    switch in it, is in both own columns, and the row is held a second time on the caller's own cycles."""
    row = unregistered(THE_LOCK_S_RELEASE)
    assert tier3().arrives_at_an_entry(row) and not row.returns, "the premise: a door user, on an arm that sets no D0"
    measured = tier3().measure(row, tier3().RomBench())
    assert measured.rebound_calls == 1 and tier3().has_a_second_count(measured)
    assert (measured.own_cycles, tier3().caller_own_cycles(measured)) == (ITS_OWN, THE_CALLER_S_OWN)
    assert tier3().counts_within_bar_with_glue(measured) and not tier3().foreign_of(measured).windows


def test_an_arm_that_sets_no_answer_is_compared_at_none_on_a_named_blob_too(blob):
    """`answered=False`: wind_update's release leaves its caller's D0 (the ROM's run: the PD unsync handed the lock
    to; ours: nothing) — the second differential on each blob compares no answer for such a row, and holds the rest."""
    _measured, watch, foreign = switching.measured_on(blob, THE_LOCK_S_RELEASE)
    assert (watch.entered, tuple(foreign)) == ([SHELL], NO_WINDOW)
    with pytest.raises(AssertionError, match="returned 0x0 where the original left"):
        switching.measured_on(blob, THE_LOCK_S_RELEASE._replace(answered=True))


def test_a_door_row_that_does_not_say_it_switches_is_still_refused_at_the_dispatcher():
    """...WHILE EVERY OTHER ROW KEEPS THE REFUSAL: the same call registered as a plain door row — nothing says its run
    switches — is refused where its twin reaches the dispatcher, by name, as before."""
    row = unregistered(THE_LOCK_S_RELEASE, delivered={})
    with pytest.raises(aes_event.Blocked, match=rf"reached the dispatcher \(dsptch, {addrs.AES_ROM_DSPTCH:#x}\)"):
        tier3().measure(row, tier3().RomBench())    # ...on the ROM's own run, the first made: no run of ours follows it


# ---- A ROUTINE OF NO ARGUMENT, AND A DOOR CALL ACROSS ANOTHER PROCESS'S TURN -------------------------------------------------
EV_KEYBD = "AES_ROM_EV_KEYBD"           # evnt_keybd: no argument; it calls ev_block — a rebound entry: an arrival
A_KEY_S_OWN_WAIT = switching.SwitchingRow("a key waited for, woken by Return at the first idle", EV_KEYBD, (),
                                          aes_event.machine, {0: model.RETURN})
A_KEY_S_WAIT_ACROSS_A_TURN = switching.SwitchingRow(
    "a key waited for; the screen manager's turn; then Return", EV_KEYBD, (), aes_event.machine,
    {0: model.ONTO_THE_BAR, 1: model.RETURN})
# What the table prices of each (ours, the ROM's): the row's own cycles — and evnt_keybd's own, net of its one call of
# ev_block's twin: the same with the screen manager's turn inside that call as without it.
A_KEY_S_WAIT_ITS_OWN, A_KEY_S_WAIT_ACROSS_A_TURN_ITS_OWN, EVNT_KEYBD_S_OWN = (11152, 17492), (13124, 19318), (106, 346)


def test_a_routine_of_no_argument_is_settled_measured_and_held_like_any_other(blob):
    """NOTHING AT THE FIRST ARGUMENT'S PLACE (evnt_keybd): the registrar's derivation, the second differential on
    each blob and the companion all take a frame of no bytes — and the row, a door user of ev_block's twin whose
    call stays open across a SELF-RESUME, is priced by the table on two counts."""
    made = switching.settled(A_KEY_S_OWN_WAIT)
    assert (made.switches.idles, made.entered) == (1, (SHELL,))
    _measured, watch, foreign = switching.measured_on(blob, A_KEY_S_OWN_WAIT)
    assert (watch.idles, watch.entered, tuple(foreign)) == (1, [SHELL], NO_WINDOW)
    assert switching.companion(A_KEY_S_OWN_WAIT).answer & aes.WORD_MASK == evinput.RETURN_KEY_CODE
    priced = tier3().measure(unregistered(A_KEY_S_OWN_WAIT), tier3().RomBench())
    assert priced.rebound_calls == 1 and tier3().counts_within_bar_with_glue(priced)
    assert (priced.own_cycles, tier3().caller_own_cycles(priced)) == (A_KEY_S_WAIT_ITS_OWN, EVNT_KEYBD_S_OWN)


def test_a_door_call_open_across_a_foreign_window_is_priced_net_of_the_window():
    """evnt_keybd's call of ev_block's twin blocks, and the screen manager runs INSIDE it: the watch tells its door
    watch where the window opens and closes, and the window comes off the call's own cost on both shores (the door
    users' rule, `test_tier3.py` holds its three REDs) — the row is priced on two counts, its window the pilot's
    own, to the cycle, and in neither column."""
    priced = tier3().measure(unregistered(A_KEY_S_WAIT_ACROSS_A_TURN), tier3().RomBench())
    assert priced.rebound_calls == 1 and tier3().counts_within_bar_with_glue(priced)
    assert tuple(tier3().foreign_of(priced)) == PRICED[FOREIGN].windows
    # THE CALLER'S OWN IS WHAT IT IS WITH NO WINDOW IN ITS CALL — evnt_keybd's own instructions round the call do not
    # change because another process ran inside it: the window came off the call's cost once, on each shore.
    assert (priced.own_cycles, tier3().caller_own_cycles(priced)) == (A_KEY_S_WAIT_ACROSS_A_TURN_ITS_OWN, EVNT_KEYBD_S_OWN)
    assert switching.companion(A_KEY_S_WAIT_ACROSS_A_TURN).answer & aes.WORD_MASK == evinput.RETURN_KEY_CODE


# ---- NO PATH MEASURES A RUN THAT SWITCHES PAST THE RULES --------------------------------------------------------------------
def test_a_named_blob_s_measurement_holds_the_foreign_window_rule_too(blob, monkeypatch):
    """`aes_switching.measured_on` — the path that holds a row on BOTH blobs — is held to what the table's is: every
    delivery relocated for OUR forker, the one the ROM's idle takes too, is refused there by name on each blob (it
    passed in silence while that path tallied nothing: the image compare is green over the mixture)."""
    ours = switching.ours

    def relocated_everywhere(on, switches, relocated, *watching, **named):
        return ours(on, switches._replace(at_idles=relocated), relocated, *watching, **named)
    monkeypatch.setattr(switching, "ours", relocated_everywhere)
    with pytest.raises(AssertionError, match=r"cycles of OUR build ran inside the foreign windows"):
        switching.measured_on(blob, _entered_twice())


def test_a_named_blob_s_measurement_holds_our_run_out_of_the_aes_but_for_its_windows(blob, monkeypatch):
    """...and the general guard's half, on that path: the windows read one cycle short (in the AES's text), our run
    has spent a cycle in the AES's ROM that no window accounts for — refused by name."""
    alike = tier3()._vet_switched_alike

    def one_short(*runs):
        foreign = alike(*runs)
        return foreign._replace(in_the_aes=foreign.in_the_aes - 1)
    monkeypatch.setattr(tier3(), "_vet_switched_alike", one_short)
    with pytest.raises(AssertionError, match=f"OUR run spent {PRICED[FOREIGN].windows[2]} cycles at the PCs of the AES's own ROM"):
        switching.measured_on(blob, ROWS[FOREIGN])


def test_a_row_that_says_it_switches_is_never_measured_on_a_path_that_reads_no_schedule():
    """WHAT A ROW IS TAKEN THROUGH IS NEVER IGNORED: tak_flag — a leaf that reaches neither the VDI nor a door entry —
    carrying a `Switches` of three idles was priced over a run that makes none, at its plain ratio. It is measured
    through the dispatcher's watch like any row that switches, and refused by what its run is not; a plain row
    handed door-call deliveries, or a transcription handed either, is refused by name."""
    leaf = next(row for row in tier3().ROWS if row.symbol == "aes_tak_flag" and not row.delivered and not row.regs)
    with pytest.raises(switching.Refused, match=r"the run made 0 idle\(s\) where the ROM's own makes 3"):
        tier3().measure(leaf._replace(delivered=aes_event.Switches({}, 3, SHELL)), tier3().RomBench())
    with pytest.raises(AssertionError, match=r"taken through interrupts \(door calls\) .* whose measurement lays none"):
        tier3().measure(leaf._replace(delivered={0: ({}, {})}), tier3().RomBench())
    transcribed = next(row for row in tier3().ROWS if row.transcription)
    with pytest.raises(AssertionError, match=r"taken through interrupts \(a run that switches\) .* whose measurement lays none"):
        tier3().measure(transcribed._replace(delivered=aes_event.Switches({}, 1, SHELL)), tier3().RomBench())


def test_a_delivery_named_at_an_idle_the_run_never_makes_is_refused_where_the_watch_is_made():
    """A DELIVERY NO IDLE TAKES was never laid and never refused: the run made its idles, ended in its process, and
    the interrupt simply did not happen. Named past the run's idles (or before the first), it is refused as the
    watch is made — on either shore, on every measuring path."""
    switches = switching.settled(ROWS[model.WOKEN_BY_A_KEY]).switches
    for never_made in (switches.idles, -1):
        astray = switches._replace(at_idles={**switches.at_idles, never_made: switches.at_idles[0]})
        with pytest.raises(switching.Refused, match=rf"named at idle \[{never_made}\] of a run that makes 1 idle"):
            switching.the_rom_s(astray)
    with pytest.raises(switching.Refused, match="it would never be laid"):
        aes_event.delivering(switches._replace(at_idles={1: switches.at_idles[0]}))


def test_a_replay_of_a_switching_row_is_held_to_have_ended_as_the_row_says():
    """EVERY SWEEP'S REPLAY (`aes_event.replayed`) ends by the watch's own vet: handed a row that says one idle more
    than the ROM's run makes, the replay is refused — it was the registrar's derivation and Tier 3 alone that asked."""
    row = ROWS[model.WOKEN_BY_A_KEY]
    made = switching.settled(row)
    with pytest.raises(switching.Refused, match=r"the run made 1 idle\(s\) where the ROM's own makes 2"):
        aes_event.replayed(make_image(made.pokes), switching._entry(row), made.switches._replace(idles=2))


def test_a_drop_is_held_to_what_our_run_stored_outside_its_foreign_windows():
    """"OUR RUN STORED IT TOO" MEANS OUR BUILD'S CODE: the screen manager's own saved context is stored on our shore
    too — by THE ROM'S savestate, inside the foreign window — so a row that dropped it would pass a ledger read over
    the whole run. Held to the stores made outside the windows, that drop is refused by name; the row's own drops
    (the desk's context, the dispatcher's stack: our savestate's, before the window) stand."""
    row, bench = table_row(ROWS[FOREIGN]), tier3().RomBench()
    tier3().measure(row, bench)
    stored_by_the_other_process = aes_switch.uda_context_drop(aes_event.uda_of(SCREEN_MANAGER, aes_switch.BASE_IMAGE))
    with pytest.raises(AssertionError, match="OUR run never stored .* OUTSIDE ITS FOREIGN WINDOWS"):
        tier3().measure(row._replace(dropped=row.dropped + stored_by_the_other_process), bench)


# ---- THE QPB'S ADDRESS A PIPE WAIT LEAVES IN ITS EVB, ON A BLOB ----------------------------------------------------------------
A_MESSAGE_WAITED_FOR = evlib.A_MESSAGE_WAITED_FOR


def test_a_blob_s_parked_wait_is_held_to_name_the_rom_s_qpb(blob, monkeypatch):
    """THE DROP OF A QPB'S ADDRESS IS VETTED ON THE BLOB TOO (`aes_switching.vet_our_qpbs`): our twin's wait, seen
    while its process stood parked, names in OUR stack the very QPB the ROM's names in its own — the process, the
    count, the buffer. Held to another count, or to a watch that saw none, the measurement is refused by name: the
    longword's drop excuses two addresses, not a wait queued with another QPB (which a WRITER reads, in a foreign
    window no compare looks into)."""
    made = switching.settled(A_MESSAGE_WAITED_FOR)
    (at, (process, count, buffer)), = made.qpbs.items()
    _measured, watch, _foreign = switching.measured_on(blob, A_MESSAGE_WAITED_FOR)
    assert watch.qpbs_seen[at] == (process, count, buffer)
    monkeypatch.setattr(switching, "settled", lambda row: made._replace(qpbs={at: (process, count + 1, buffer)}))
    with pytest.raises(AssertionError, match=r"the QPB our parked wait names .* is not the ROM's"):
        switching.measured_on(blob, A_MESSAGE_WAITED_FOR)
    with pytest.raises(AssertionError, match="OUR run was never seen to hold one there"):
        switching.vet_our_qpbs("a row", made.qpbs, types.SimpleNamespace(qpbs_seen={}))
