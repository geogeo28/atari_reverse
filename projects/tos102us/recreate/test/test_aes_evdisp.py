"""THE DISPATCHER'S C (`src/aes/evdisp.c`): gemdisp's disp_act, mwait_act and idle — and, off target, the model of
disp over savestate and switchto (`test_aes_evdisp_model.py` holds the model; this file the three routines).

EVERY MACHINE IS AN ARRIVAL: the ROM's own run of something its scheduler does (`aes_switch.SCENARIOS`: a key wakes
the desk; the desk blocks; the desk yields; the lock handed to a waiter), watched at the three routines' entries —
each case the ROM's own call, with the frame and the machine the ROM makes it with. The dispatcher calls them on ITS
OWN stack; a case enters them on the run's, with the same frame.

LABELLED — what no ROM caller hands, said in each case's name:
  * mwait_act handed a process WHOSE EVENT HAS COME. disp calls mwait_act for a process that just asked to wait and
    found nothing; between mwait's test ($fe40c8) and disp's call no event can be posted — an interrupt only queues
    a fork, which runs after — so the ROM's "ready after all" arm ($fe4bb2) is reached by no machine. The arm is
    C here as it is there, and held by a call no caller makes: the desk, woken and not yet moved, handed in.
  * disp_act handed THE SPARE PD behind two processes: a walk past more than one link needs three processes, and the
    snapshot's scheduler has two.
"""
import functools
import struct

import pytest

from harness import addrs, emu, make_image

import aes
import aes_event
import aes_evlib
import aes_switch as switch
import case
import test_aes_evfork_interrupted as interrupted

DISP_ACT, MWAIT_ACT, IDLE = switch.DISP_ACT, switch.MWAIT_ACT, switch.IDLE
SHELL, SCREEN_MANAGER, SPARE_PD = switch.SHELL, switch.SCREEN_MANAGER, switch.SPARE_PD
pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)
IDLE_HOOKS = switch.IDLE_HOOKS


def run_over(name, arguments, machine):
    """The differential of `addrs.<name>` over `machine` with the frame `arguments`, every run of its C first in a
    fork; idle's with the VDI's cores bound for its poll and the idle hook open (a leaf delivers nothing). What steers
    the attribution pass is asked of the run, by the event layer's one loop (`aes_event.run_layer_case`)."""
    hooked = {"hook": IDLE_HOOKS, "serves": switch.FORK_GUARDED[name]} if switch.FORK_GUARDED[name] else {}
    return aes_event.run_layer_case(name, arguments, machine, **hooked)


def run(arrival, arguments=None):
    return run_over(arrival.name, arrival.arguments if arguments is None else arguments, arrival.machine)


def ready(image):
    return aes.list_of(image, aes.AES_RLR)


def not_ready(image):
    return aes.list_of(image, aes.AES_NRL)


# ---- every arrival ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arrival", switch.cases(), ids=switch.case_id)
def test_the_routine_behaves_as_the_rom_at_each_of_its_own_calls(arrival):
    run(switch.arrival(*arrival))


def test_disp_act_puts_a_process_at_the_tail_of_the_ready_list():
    """WHAT THE ARRIVALS ARE, read off the ROM's own runs: onto an EMPTY ready list (idle's wake; the yielding desk),
    and BEHIND the process already there (the screen manager, handed the lock, queued behind the desk)."""
    woken = switch.at("a key wakes the desk", DISP_ACT)
    assert woken.arguments == (SHELL,) and ready(make_image(woken.machine)) == []
    assert ready(run(woken).final) == [SHELL]
    behind = switch.at("the lock handed to the screen manager", DISP_ACT, 1)
    assert behind.arguments == (SCREEN_MANAGER,) and ready(make_image(behind.machine)) == [SHELL]
    after = run(behind).final
    assert ready(after) == [SHELL, SCREEN_MANAGER]
    assert case.word_in(after, SCREEN_MANAGER + aes.PD_STAT) == aes.PD_STAT_READY


def test_mwait_act_puts_a_waiting_process_at_the_head_of_the_not_ready_list():
    blocked = switch.at("the desk blocks", MWAIT_ACT)
    before = make_image(blocked.machine)
    assert blocked.arguments == (SHELL,) and not_ready(before) == [SCREEN_MANAGER]
    assert case.word_in(before, SHELL + aes.PD_STAT) == aes.PD_STAT_WAITING
    assert not case.word_in(before, SHELL + aes.PD_EVWAIT) & case.word_in(before, SHELL + aes.PD_EVFLG)
    assert not_ready(run(blocked).final) == [SHELL, SCREEN_MANAGER]


def test_idle_moves_two_processes_woken_at_once_in_the_order_they_were_woken():
    both = switch.at("a delay run out and the mouse on the bar: two processes woken at once", IDLE)
    before = make_image(both.machine)
    assert aes.list_of(before, aes.AES_DRL) == [SHELL, SCREEN_MANAGER] and ready(before) == []
    after = run(both).final
    assert ready(after) == [SHELL, SCREEN_MANAGER] and aes.list_of(after, aes.AES_DRL) == []


def test_idle_polls_once_and_moves_every_woken_process():
    """idle's three arrivals: nothing ready and a key typed — its poll queues the key and it returns for forker; the
    desk woken — moved to the ready list; a process ready already — one poll, nothing moved."""
    polls = switch.at("a key wakes the desk", IDLE, 0)
    assert switch.waits_for_an_interrupt(make_image(polls.machine)), "the premise: the machine at its first idle"
    assert [code for code, _data in aes_event.fork_queue(run(polls).final)] == [addrs.AES_ROM_KCHANGE]
    moves = switch.at("a key wakes the desk", IDLE, 1)
    assert aes.list_of(make_image(moves.machine), aes.AES_DRL) == [SHELL]
    after = run(moves).final
    assert ready(after) == [SHELL] and aes.list_of(after, aes.AES_DRL) == []
    resumes = switch.at("the desk yields", IDLE)
    assert ready(make_image(resumes.machine)) == [SHELL] == ready(run(resumes).final)


# ---- what no ROM caller hands, labelled -------------------------------------------------------------------------------------
def _the_desk_woken_and_not_yet_moved():
    return switch.at("a key wakes the desk", IDLE, 1).machine


def _the_desk_queued_by_its_address_on_the_bus():
    """What the ROM's own disp_act leaves when it is handed the desk with a top byte: the ready list's head holds the
    pointer AS HANDED, tag and all (a machine no caller makes; every byte of it the ROM's store)."""
    arrival = switch.at("the desk yields", DISP_ACT)
    staged = aes.staged(DISP_ACT, (SHELL | aes.BUS_TAG,), arrival.machine)
    final, _writes, _regs = emu.run(make_image(staged), addrs.AES_ROM_DISP_ACT)
    return aes_event.as_pokes(final, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES)


A_DELAY_TICKS = 5
THE_SECOND_EVENT = aes.header_constants("evwait.h")["IASYNC_FIRST_EVENT"] << 1


@functools.cache
def _waiting_for_the_one_of_two_events_that_has_not_come():
    """mwait_act's own arrival over AN ARGUMENT-CLASS MACHINE BY THE ROM'S OWN iasync (`aes_evlib.after_iasync`): the
    desk queued itself twice — for a key, which is queued and so has come, and for a delay — and then WAITS for the
    delay alone (the ROM's mwait, to the dispatcher's loop). It holds an event that has come and that it does not
    wait for: what tells PD_EVWAIT from PD_EVBITS in mwait_act's test."""
    queued = aes_evlib.after_iasync(aes_evlib.after_iasync(aes_evlib.key_queued(), aes_evlib.KEYBOARD, 0),
                                    aes_evlib.DELAY, A_DELAY_TICKS)
    arrival, = switch.LAYER.watched(queued, addrs.AES_ROM_EV_MWAIT, {addrs.AES_ROM_DISP_LOOP},
                                    struct.pack(">h", THE_SECOND_EVENT)).arrivals
    return arrival


def _a_process_on_the_woken_list_whose_event_has_not_come():
    """The desk on the woken list (the ROM's own forker put it there) with its event flags CLEARED: a process no
    signal wakes. What tells idle's `disp_act` from a `mwait_act` there, which would queue this one to wait."""
    return case.merge_pokes(_the_desk_woken_and_not_yet_moved(), {SHELL + aes.PD_EVFLG: bytes(aes.WORD_BYTES)})


AN_EVENT_ABOVE_THE_BYTE = 0x0100        # PD_EVWAIT's and PD_EVFLG's ninth bit: the AES's eight events end at $80
A_COUNT_OF_ITS_HIGH_BYTE_ALONE = 0x0100


def _waiting_for_an_event_above_the_byte_that_has_come():
    """ARGUMENT-CLASS, POKED: the desk as it blocks, the event it waits for and the event that has come both the one
    bit ABOVE the byte — what tells mwait_act's WORD test (`move.w`, `and.w`: $fe4ba6) from a byte's."""
    blocked = switch.at("the desk blocks", MWAIT_ACT).machine
    return case.merge_pokes(blocked, aes.field_pokes("PD", SHELL, EVWAIT=AN_EVENT_ABOVE_THE_BYTE, EVFLG=AN_EVENT_ABOVE_THE_BYTE))


def _the_count_s_high_byte_alone():
    """ARGUMENT-CLASS, POKED: idle's own arrival with nothing ready and the fork queue's count 256 — its low byte 0.
    What tells idle's WORD test of the count (`tst.w $c906`) from a byte's: the ROM's idle returns at once."""
    waiting = switch.at("a key wakes the desk", IDLE, 0).machine
    return case.merge_pokes(waiting, {aes.AES_FORK_COUNT: A_COUNT_OF_ITS_HIGH_BYTE_ALONE.to_bytes(aes.WORD_BYTES, "big")})


LABELLED = {
    "mwait_act handed a process whose event has come (no ROM caller hands one): ready after all":
        lambda: (MWAIT_ACT, (SHELL,), _the_desk_woken_and_not_yet_moved()),
    "mwait_act for a process that queued itself twice (the ROM's iasync) and waits for the event that has not come":
        lambda: (MWAIT_ACT, _waiting_for_the_one_of_two_events_that_has_not_come().arguments,
                 _waiting_for_the_one_of_two_events_that_has_not_come().machine),
    "disp_act handed the spare PD behind two processes (no third process runs): a walk past two links":
        lambda: (DISP_ACT, (SPARE_PD,), switch.scenario("the lock handed to the screen manager").machine),
    "disp_act handed the process already last on the ready list (no caller does): it is linked to itself":
        lambda: (DISP_ACT, (SHELL,), switch.at("the desk yields", IDLE).machine),
    "disp_act behind a process queued by its address on the bus (no caller queues one): the walk is on the bus":
        lambda: (DISP_ACT, (SCREEN_MANAGER,), _the_desk_queued_by_its_address_on_the_bus()),
    "idle over a woken process whose event has not come (no signal wakes one): made ready all the same":
        lambda: (IDLE, (), _a_process_on_the_woken_list_whose_event_has_not_come()),
    "mwait_act handed a process that waits for, and holds, an event above the byte (no event of the AES is): ready":
        lambda: (MWAIT_ACT, (SHELL,), _waiting_for_an_event_above_the_byte_that_has_come()),
    "idle with 256 forks counted and none queued (the queue holds 32): the count is a word, and it returns":
        lambda: (IDLE, (), _the_count_s_high_byte_alone()),
    "disp_act, the PD on the bus": lambda: (DISP_ACT, (SHELL | aes.BUS_TAG,), switch.at("the desk yields", DISP_ACT).machine),
    "mwait_act, the PD on the bus": lambda: (MWAIT_ACT, (SHELL | aes.BUS_TAG,), switch.at("the desk blocks", MWAIT_ACT).machine),
}


@pytest.mark.parametrize("label", LABELLED)
def test_a_labelled_call_behaves_as_the_rom(label):
    name, arguments, machine = LABELLED[label]()
    run_over(name, arguments, machine)


def test_a_process_waits_on_though_another_event_of_its_own_has_come():
    """The second labelled machine's premise, and what mwait_act makes of it: the desk HOLDS an event that has come
    (the key's bit, in PD_EVBITS and PD_EVFLG) and WAITS for another (the delay's, PD_EVWAIT) — so it is queued to
    wait, as the ROM's test of PD_EVWAIT has it."""
    arrival = _waiting_for_the_one_of_two_events_that_has_not_come()
    before = make_image(arrival.machine)
    held, waited, come = (case.word_in(before, SHELL + field) for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG))
    assert arrival.name == MWAIT_ACT and waited == THE_SECOND_EVENT and held & come and not waited & come
    assert not_ready(run(arrival).final)[0] == SHELL


def test_the_labelled_machines_are_what_their_labels_say():
    name, arguments, machine = next(iter(LABELLED.values()))()
    before = make_image(machine)
    assert case.word_in(before, SHELL + aes.PD_EVWAIT) & case.word_in(before, SHELL + aes.PD_EVFLG), "its event has come"
    assert ready(run_over(name, arguments, machine).final) == [SHELL], "...so it is made ready, not queued to wait"
    name, arguments, machine = LABELLED["disp_act handed the spare PD behind two processes (no third process runs): "
                                        "a walk past two links"]()
    assert ready(make_image(machine)) == [SHELL, SCREEN_MANAGER]
    assert aes.list_of(run_over(name, arguments, machine).final, aes.AES_RLR) == [SHELL, SCREEN_MANAGER, SPARE_PD]
    name, arguments, machine = LABELLED["disp_act handed the process already last on the ready list (no caller does): "
                                        "it is linked to itself"]()
    assert ready(make_image(machine)) == [SHELL]
    assert case.long_in(run_over(name, arguments, machine).final, SHELL + aes.PD_LINK) == SHELL, "the ROM's own order"
    name, arguments, machine = LABELLED["disp_act behind a process queued by its address on the bus (no caller queues "
                                        "one): the walk is on the bus"]()
    assert case.long_in(make_image(machine), aes.AES_RLR) == SHELL | aes.BUS_TAG
    assert case.long_in(run_over(name, arguments, machine).final, SHELL + aes.PD_LINK) == SCREEN_MANAGER


def test_idle_makes_a_woken_process_ready_whatever_its_flags_say():
    name, arguments, machine = LABELLED["idle over a woken process whose event has not come (no signal wakes one): "
                                        "made ready all the same"]()
    before = make_image(machine)
    assert aes.list_of(before, aes.AES_DRL) == [SHELL]
    assert not case.word_in(before, SHELL + aes.PD_EVWAIT) & case.word_in(before, SHELL + aes.PD_EVFLG)
    final = run_over(name, arguments, machine).final
    assert ready(final) == [SHELL] and SHELL not in not_ready(final)


def test_idle_does_not_wait_where_a_fork_is_queued():
    """WHERE THE HOST'S IDLE ASKS ITS HOOK is where the machine waits for an interrupt — nothing ready, nothing woken
    AND NOTHING QUEUED. Idle's own arrival with the desk blocked asks once (the premise); the same machine with the
    fork queue's count at one (LABELLED: the count alone poked — what an interrupt between forker's pass and idle
    leaves is a whole queued fork) asks NOT AT ALL: it polls once and returns to forker, as the ROM's does."""
    arrival = switch.at("a key wakes the desk", IDLE, 0)
    before = make_image(arrival.machine)
    assert not ready(before) and not aes.list_of(before, aes.AES_DRL) and not case.word_in(before, aes.AES_FORK_COUNT)
    core = "aes_idle"
    asked_once = switch.modelled(core, (), arrival.machine, None, answered=False)
    assert (asked_once.returncode, asked_once.idles) == (0, 1), asked_once.stderr
    queued = case.merge_pokes(arrival.machine, {aes.AES_FORK_COUNT: (1).to_bytes(aes.WORD_BYTES, "big")})
    not_asked = switch.modelled(core, (), queued, None, answered=False)
    assert (not_asked.returncode, not_asked.idles) == (0, 0), not_asked.stderr
    run_over(IDLE, (), queued)


WAITING_MACHINES = {
    "the snapshot as it waits": dict,
    # ...the word AFTER the fork queue's count nonzero, by the ROM's own runs: the count is tested as a WORD.
    "the snapshot, the control manager holding a mouse it found shown": lambda: switch.grabbed_while_shown({}),
}


def test_the_grabbed_machine_holds_a_word_after_the_count_and_the_snapshot_none():
    """THE SECOND MACHINE'S PREMISE: the word after the fork queue's count — the control manager's record of the
    cursor it found — is nonzero there, by the ROM's own two runs, and zero in the snapshot; the count itself is zero
    in both, so the two machines tell a word's test of it from a longword's."""
    grabbed, plain = (make_image(machine()) for machine in reversed(WAITING_MACHINES.values()))
    assert case.word_in(grabbed, switch.AES_CT_MOUSE_SHOWN) and not case.word_in(plain, switch.AES_CT_MOUSE_SHOWN)
    assert not case.word_in(grabbed, aes.AES_FORK_COUNT) and not case.word_in(plain, aes.AES_FORK_COUNT)
    assert switch.AES_CT_MOUSE_SHOWN == aes.AES_FORK_COUNT + aes.WORD_BYTES


@pytest.mark.parametrize("machine", WAITING_MACHINES.values(), ids=WAITING_MACHINES)
def test_an_idle_that_would_wait_for_ever_is_refused_by_name(machine):
    """THE IDLE HOOK'S REFUSAL: idle entered over a machine that waits — nothing ready, woken, queued or typed —
    polls once (a leaf's one free idle) and, back at its loop with nothing changed, is refused: the ROM's own idle
    spins there for ever (held: its run reaches its poll a second time), which no case's run may do."""
    pokes = machine()
    assert switch.waits_for_an_interrupt(make_image(pokes))
    spins = switch.the_rom_s_idle_polls_again(pokes)
    assert spins, "the premise: the ROM's own idle, over this machine, comes back to its poll"
    forked = aes_event.core_in_a_fork(IDLE, (), pokes, hook=IDLE_HOOKS)
    assert forked.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), forked.stderr
    assert "the dispatcher idles once more than the ROM's own run did" in forked.stderr
    assert "the dispatcher idles — no process ready, none woken, no fork queued" in forked.stderr


# ---- AN INTERRUPT BETWEEN TWO OF idle'S INSTRUCTIONS (`test_aes_evfork_interrupted.py`'s surface) ---------------------------
# idle TESTS a word the interrupts count — the fork queue's count — once a turn, after the ready list. It counts
# nothing itself: what the sweep holds is that an interrupt's forkq taken at ANY boundary of its body leaves the
# machine the ROM's idle leaves — the count read in memory, once, where the ROM reads it.
BLOBS = interrupted.BLOBS
IDLE_INTERRUPTED = "a key wakes the desk"
# idle's two arrivals of that scenario, swept both: with NOTHING READY (a key typed ahead: its poll queues the key,
# and its loop ends on THE COUNT — the shared word, read) and with a woken process to move (its loop ends on the
# ready list, the count never read).
IDLE_ARRIVALS = {"nothing ready: the loop ends on the fork queue's count": 0, "a woken process to move": 1}
READS_THE_COUNT = "nothing ready: the loop ends on the fork queue's count"


def _idle_arrival(which=READS_THE_COUNT):
    return switch.at(IDLE_INTERRUPTED, IDLE, IDLE_ARRIVALS[which])


def test_the_swept_arrival_reads_the_shared_word():
    """THE SWEEP'S PREMISE, on the ROM's own run: idle's first arrival EXECUTES its test of the fork queue's count
    (`tst.w $c906`) — and its second, a process ready by then, leaves before it: a sweep over that one alone would
    hold the interleaving of a body that never reads the word the interrupts count."""
    reads = {which: switch.the_rom_s_idle_tests_the_count(_idle_arrival(which).machine) for which in IDLE_ARRIVALS}
    assert reads == {READS_THE_COUNT: True, "a woken process to move": False}


# How many states the ROM's own idle can be left in, by where the move lands: ONE where idle queues nothing itself;
# TWO where its own poll queues the key — the move queued BEFORE the key or AFTER it, the order forker then runs
# the two in. Never a third: the count is the two forks' whichever comes first.
STATES_THE_ROM_S_IDLE_IS_LEFT_IN = {READS_THE_COUNT: 2, "a woken process to move": 1}


@pytest.mark.parametrize("which", IDLE_ARRIVALS)
def test_the_rom_s_idle_is_left_in_the_states_a_move_can_leave_and_no_other(which):
    arrival = _idle_arrival(which)
    shore = interrupted._the_rom_s(IDLE, arrival.arguments, arrival.machine)
    left = interrupted.states(shore, interrupted.A_MOVE)
    plain = interrupted.interrupted_at(shore, None, interrupted.A_MOVE)
    assert len(left) == STATES_THE_ROM_S_IDLE_IS_LEFT_IN[which]
    assert interrupted.the_interrupt_shows(left, interrupted.state(plain.memory, {}))
    queued = {tuple(code for code, _data in aes_event.fork_queue(interrupted.interrupted_at(shore, boundaries[0],
                                                                                           interrupted.A_MOVE).memory))
              for boundaries in left.values()}
    if which == READS_THE_COUNT:
        assert queued == {(addrs.AES_ROM_MCHANGE, addrs.AES_ROM_KCHANGE), (addrs.AES_ROM_KCHANGE, addrs.AES_ROM_MCHANGE)}


@pytest.mark.parametrize("which", IDLE_ARRIVALS)
@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
def test_an_interrupt_between_any_two_instructions_of_idle_leaves_the_rom_s_state(directory, which):
    """...ours taken through OUR OWN GLUE (`irq.S`'s motion glue, its Alcyon entry, our forkq): the whole of what an
    interrupt runs on target, at every boundary of our idle — the code it queues our own entry of mchange, read as
    the ROM's function."""
    arrival, blob = _idle_arrival(which), interrupted.blob_in(directory)
    codes = {blob.entry(symbol): rom for symbol, rom in interrupted.FORK_FUNCTION_ENTRIES.items()}
    our_move = interrupted.A_MOVE._replace(glue=blob.entry(switch.MOTION_GLUE.symbol))
    ours = interrupted.states(interrupted._ours(blob, IDLE, arrival.arguments, arrival.machine), our_move, codes)
    the_rom_s = interrupted.states(interrupted._the_rom_s(IDLE, arrival.arguments, arrival.machine), interrupted.A_MOVE)
    assert ours.keys() == the_rom_s.keys(), "an interrupt inside our idle leaves a state the ROM's is never left in"


@pytest.mark.parametrize("directory", BLOBS.values(), ids=BLOBS)
def test_idle_changes_no_word_an_interrupt_shares(directory):
    """...and the static half: idle's own instructions change NONE of the shared words — on the ROM, and on both
    blobs (a count it kept in a register and stored back would be a change here)."""
    arrival, blob = _idle_arrival(), interrupted.blob_in(directory)
    assert interrupted.changes_of_the_shared_words(
        interrupted._the_rom_s(IDLE, arrival.arguments, arrival.machine)) == []
    assert interrupted.changes_of_the_shared_words(
        interrupted._ours(blob, IDLE, arrival.arguments, arrival.machine)) == []


# ---- Tier 3's rows: each routine's own calls --------------------------------------------------------------------------------
ROWS = {
    (DISP_ACT, "onto the empty ready list"): ("a key wakes the desk", 0),
    (DISP_ACT, "behind the process running"): ("the lock handed to the screen manager", 1),
    (MWAIT_ACT, "onto the not-ready list"): ("the desk blocks", 0),
    (IDLE, "a poll queues a key typed ahead"): ("a key wakes the desk", 0),
    (IDLE, "a woken process moved to the ready list"): ("a key wakes the desk", 1),
    (IDLE, "a process ready already: one poll"): ("the desk yields", 0),
    (IDLE, "two processes woken at once"): ("a delay run out and the mouse on the bar: two processes woken at once", 0),
}
for (_name, _label), (_scenario, _which) in ROWS.items():
    _arrival = switch.at(_scenario, _name, _which)
    aes_event.register_row(_label, _name, _arrival.arguments, _arrival.machine,
                           hook=IDLE_HOOKS if _name == IDLE else None, polls=_name == IDLE)


def test_each_row_is_a_case_of_this_battery():
    """A row's machine is one of the arrivals the cases above run: nothing is priced that is not verified here."""
    verified = {(switch.arrival(*pair).name, pair) for pair in switch.cases()}
    for (name, _label), (scenario, which) in ROWS.items():
        assert (name, (scenario, switch._SCENARIOS.nth_of(scenario, name, which))) in verified
