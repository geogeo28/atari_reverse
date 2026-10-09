"""THE WAITS, WOKEN (`src/aes/evlib.c`, `src/aes/evwait.c`): every call of the waits' batteries that reaches the
dispatcher, TAKEN ON THROUGH IT TO ITS RETURN — the half `test_aes_evlib.py` / `test_aes_evwait.py` cannot hold, which
stop where the C stops (AT DSPTCH): what a routine does when the dispatcher runs it again. apret's order and its
answer's width, ev_block's event bit carried across mwait, ev_rets after the wake, mwait's re-read of the event flags.

TIER 1, EVERY BLOCKED ARRIVAL: `aes_evlib.woken_counterpart(scenario, nth)` is the same routine, frame and machine as the case
held at dsptch, with the scenario's WAKE (`aes_evlib.WAKES`: the ROM's own interrupts at the dispatcher's idles — and,
for a wait on a pipe, the screen manager's own write) — held by `aes_switching.companion`: the C through its own
scheduler against the ROM's one run through the ROM's dispatcher, the same idles, the same answer, every byte outside
the run's stack. NO ROW is made of these (the staged application's are Tier 1 only by rule).

WHAT NO RETURNING RUN WAKES IS SAID, AND HELD ON THE ROM'S OWN RUN (`aes_evlib.NOT_WOKEN`): a rectangle no mouse can
enter, a negative time, a pipe whose other end is the waiter itself, a lock whose holder is a harness call's — each
by the delivery its entry names AND BY A SWEEP of every interrupt there is (`aes_evlib.swept`: a hand-picked
delivery can be the wrong one — the screen manager's rectangle stood in that table until the sweep), EVERY ANSWER OF
WHICH IS PINNED: "idles for ever" is evidence; a run that ends IN ANOTHER PROCESS, or a chain never taken, is none —
and where the lock's holder is a harness-parked process a key ends the run in that holder: the waiter's tail is
UNPINNED on that machine, not unwakeable.

THE ROWS THAT SWITCH (`test_aes_evlib.WOKEN_ROWS`, `test_aes_evwait.WOKEN_ROWS`: registered, priced): each one's
premise on the ROM's run, its second differential ON BOTH BLOBS with its cycles pinned, and what the table prices.
THE ROW WHOSE PROCESS IS NOT THE DESK is the screen manager's write: `Switches.process` is read off the machine, the
foreign window is THE DESK'S (the ROM's desktop, reading its pipe), and the dispatcher that hands back is the ROM's.
"""
import pytest

from harness import addrs, make_image

import aes
import aes_event
import aes_evlib as evlib
import aes_pdpipe
import aes_switch
import aes_switching as switching
import case
import test_aes_evlib as waits
import test_aes_evwait as queued
import test_aes_switching as pilots

SHELL, SCREEN_MANAGER = aes_switch.SHELL, aes_switch.SCREEN_MANAGER
BENCH, SHIPPED = pilots.BENCH, pilots.SHIPPED
RETURN_KEY = pilots.RETURN
BLOCKED = evlib.cases(switching=True)
# mwait's own arrivals under a wait on a pipe: the QPB the queued wait names is no part of a staged machine
# (`aes_evlib.a_pipe_wait_s_qpb_is_no_part_of`); the same wait is woken in the arrivals above them.
UNDER_A_PIPE_WAIT = (("evnt_mesag, none", 4), ("appl_read, none", 3))
WOKEN = [pair for pair in BLOCKED if pair[0] in evlib.WAKES and pair not in UNDER_A_PIPE_WAIT]
NOT_WOKEN = [pair for pair in BLOCKED if pair[0] in evlib.NOT_WOKEN]

pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)


# ---- TIER 1: EVERY BLOCKED ARRIVAL, WOKEN -------------------------------------------------------------------------------------
def test_every_blocked_arrival_is_woken_or_said_never_to_be():
    """THE PARTITION: each arrival of the waits' scenarios that reaches the dispatcher has a woken counterpart here,
    or its scenario is said never to be woken — or it is mwait under a pipe wait whose QPB the machine does not hold
    AND WHOSE WAKE IS THAT PIPE'S WRITER (the six waits of an evnt_multi hold such a wait too, and are woken by a
    key: nobody reads the QPB)."""
    assert sorted(WOKEN + NOT_WOKEN + list(UNDER_A_PIPE_WAIT)) == sorted(BLOCKED) and len(WOKEN) > len(BLOCKED) // 2
    under = [pair for pair in BLOCKED if evlib.a_pipe_wait_s_qpb_is_no_part_of(evlib.arrival(*pair))]
    assert tuple(pair for pair in under if evlib.WAKES.get(pair[0]) is evlib.THE_MENU_CHAIN) == UNDER_A_PIPE_WAIT


@pytest.mark.parametrize("arrival", WOKEN, ids=evlib.case_id)
def test_a_blocked_arrival_taken_on_through_the_dispatcher_is_the_rom_s_to_its_return(arrival):
    """THE WOKEN COUNTERPART of a case held at dsptch: the C blocks where the ROM does, its own scheduler takes the
    scenario's interrupts at the ROM's idles (another process the ROM's own code), and the call RETURNS — the idles,
    the answer and the whole image the ROM's run's through its own dispatcher (`aes_switching.companion`)."""
    row = evlib.woken_counterpart(*arrival)
    assert evlib.switches(row.name, row.arguments, row.machine()), "the premise: the very call the battery holds at dsptch"
    ran = switching.companion(row)
    assert sorted(ran.delivered.at_idles) == sorted(evlib.WAKES[arrival[0]]) and ran.delivered.idles >= len(ran.delivered.at_idles)


@pytest.mark.parametrize("arrival", NOT_WOKEN, ids=evlib.case_id)
def test_a_wait_no_returning_run_wakes_is_held_on_the_rom_s_own_run(arrival):
    """...AND THE REST, each on the ROM's own run through its dispatcher with what could have woken it delivered: the
    machine idles for ever (`aes_switch.IDLES`, or the driver's refusal of a run that idles on after its deliveries),
    or the run reaches its return in a process a harness call parked — never in the caller's."""
    how, tried, _why = evlib.NOT_WOKEN[arrival[0]]
    made = evlib.arrival(*arrival)
    frame = evlib.frame_of(made.name, made.arguments)
    refusal = {evlib.NEVER: "idles for ever AFTER its deliveries", evlib.ANOTHER_PROCESS_RETURNS: "its return in ANOTHER process"}[how]
    if tried:
        with pytest.raises(AssertionError, match=refusal):
            aes_switch.scheduled(getattr(addrs, made.name), frame, made.machine, tried)
        return
    the_rom_s = aes_switch.scheduled(getattr(addrs, made.name), frame, made.machine)
    assert (the_rom_s.ended, the_rom_s.entered) == (aes_switch.IDLES, ())


# ---- WHAT THE SWEEP ANSWERS OVER NOT_WOKEN BESIDE "IDLES FOR EVER" — pinned by scenario (the same at each of its arrivals) ----
# (1) THE RUN ENDS IN ANOTHER PROCESS. Two kinds, and only the second is in the table's own words:
#   * THE HOLDER IS A HARNESS-PARKED PROCESS (`aes_evlib.THE_HOLDER_IS_HARNESS_PARKED`): the desk holds the lock and
#     was parked FOR A KEY by a harness call — so every member that brings a key at an IDLE un-parks the holder, whose
#     continuation is the run's sentinel. The waiter's tail is NOT RUN: UNPINNED on this machine, not "unwakeable"
#     (the same call over a ROM-RUN holder — the screen manager's menu — is `aes_evlib.THE_LOCK_THE_MENU_HOLDS`: both
#     its blocked arrivals are among WOKEN, taken on to their return, and ev_block's is a registered row).
#   * A STAGED APPLICATION'S DELAY RUNS OUT FIRST (`NOT_WOKEN`'s own `ANOTHER_PROCESS_RETURNS` entries): the ticks.
# (2) THE CHAIN IS NEVER TAKEN: over the lock held by the desk, the mouse onto the bar wakes nobody (the screen
#     manager is the caller, or queued on the lock) — the run makes no poll after its first idle, so the three chains
#     that deliver there are not delivered. Three of the sweep's 26 members say nothing of those four arrivals.
A_KEY_AT_AN_IDLE = {"Return", f"{evlib.ONTO_THE_MENU_BAR}, then Return at the next idle", f"{evlib.OFF_IT}, then Return at the next idle"}
TICKS = "more ticks than any time"
THE_TICKS_ANYWHERE = {TICKS, f"{TICKS}, at each of four successive idles", f"{evlib.ONTO_THE_MENU_BAR}, then {TICKS} at the next idle",
                      f"{evlib.ONTO_THE_MENU_BAR}, then {TICKS} at the poll after it", f"{evlib.OFF_IT}, then {TICKS} at the next idle"}
SAID_TO_END_IN_ANOTHER_PROCESS = {scenario for scenario, (how, _tried, _why) in evlib.NOT_WOKEN.items()
                                  if how == evlib.ANOTHER_PROCESS_RETURNS}
ENDS_IN_ANOTHER_PROCESS = {**dict.fromkeys(evlib.THE_HOLDER_IS_HARNESS_PARKED, A_KEY_AT_AN_IDLE),
                           **dict.fromkeys(SAID_TO_END_IN_ANOTHER_PROCESS, THE_TICKS_ANYWHERE)}
AT_THE_POLL_AFTER_THE_FIRST_IDLE = {name for name, chain in evlib.EVERY_CHAIN.items() if chain.at_polls}
NEVER_TAKEN = dict.fromkeys(evlib.THE_HOLDER_IS_HARNESS_PARKED, AT_THE_POLL_AFTER_THE_FIRST_IDLE)


def test_the_sweep_s_other_answers_are_of_exactly_the_scenarios_that_say_so():
    """WHICH scenarios the sweep ends in another process, held to what the tables SAY of them: the two whose lock a
    harness-parked process holds (their entry and their fact say so: `THE_HOLDER_IS_HARNESS_PARKED`, each with
    nothing "tried" and a fact read off the machine) and those `NOT_WOKEN` itself calls a return in another process
    — no other. And the chains never taken are the three at a poll, on the first kind alone."""
    assert len(SAID_TO_END_IN_ANOTHER_PROCESS) == 2 and not SAID_TO_END_IN_ANOTHER_PROCESS & set(evlib.THE_HOLDER_IS_HARNESS_PARKED)
    assert set(evlib.THE_HOLDER_IS_HARNESS_PARKED) < set(evlib.ONLY_ANOTHER_PROCESS)
    assert ENDS_IN_ANOTHER_PROCESS.keys() | NEVER_TAKEN.keys() <= {scenario for scenario, _nth in NOT_WOKEN}
    assert len(AT_THE_POLL_AFTER_THE_FIRST_IDLE) == len(evlib.TAKEN_BETWEEN_TWO_TURNS)
    holders = [pair for pair in NOT_WOKEN if pair[0] in evlib.THE_HOLDER_IS_HARNESS_PARKED]
    assert len(holders) == 4 and all(len(evlib.swept(*pair)) - len(NEVER_TAKEN[pair[0]]) == 23 for pair in holders)
    # ...and the tail those four leave unrun IS run over a ROM-run holder: the same routines' arrivals, woken.
    over_a_real_holder = [pair for pair in WOKEN if pair[0] == evlib.THE_LOCK_THE_MENU_HOLDS]
    assert [evlib.arrival(*pair).name for pair in over_a_real_holder] == [
        evlib.arrival(*pair).name for pair in holders if pair[0] == evlib.THE_HOLDER_IS_HARNESS_PARKED[0]]
    assert evlib.WAKES[evlib.THE_LOCK_THE_MENU_HOLDS] is evlib.THE_MENU_LET_GO


@pytest.mark.parametrize("arrival", NOT_WOKEN, ids=evlib.case_id)
def test_no_interrupt_wakes_a_wait_said_never_to_be_woken(arrival):
    """THE CLASS IS HELD BY A SWEEP, NOT BY THE ONE DELIVERY ITS ENTRY PICKED (`aes_evlib.what_wakes`): every kind of
    interrupt there is — a key, each button event, the ticks, the mouse into and out of every rectangle a scenario
    names, onto the bar (the other process's turn) — taken alone at the dispatcher's first idle, AND EVERY CHAIN
    (`aes_evlib.EVERY_CHAIN`: the menu chain, ticks at successive idles, each interrupt after the mouse has gone
    onto the bar or off it, a key, a press and the ticks between two processes' turns), on the ROM's own run: none
    makes this call return in its caller. A scenario some member wakes is no member of NOT_WOKEN: it has a tail
    nothing would run.
    EVERY MEMBER'S ANSWER IS HELD, NOT ONLY "NONE RETURNED" (`aes_evlib.swept`): each idles for ever — the one answer
    that says the member does not wake the wait — BUT those pinned as ending the run IN ANOTHER PROCESS
    (`ENDS_IN_ANOTHER_PROCESS`: the waiter was never seen woken or not) and the chains this machine NEVER TAKES
    (`NEVER_TAKEN`: no evidence at all). None spins."""
    assert evlib.what_wakes(*arrival) == set()
    expected = {**dict.fromkeys((*evlib.EVERY_INTERRUPT, *evlib.EVERY_CHAIN), evlib.NEVER),
                **dict.fromkeys(ENDS_IN_ANOTHER_PROCESS.get(arrival[0], ()), evlib.ANOTHER_PROCESS_RETURNS),
                **dict.fromkeys(NEVER_TAKEN.get(arrival[0], ()), evlib.NOT_TAKEN)}
    assert evlib.swept(*arrival) == expected


@pytest.mark.parametrize("arrival", WOKEN, ids=evlib.case_id)
def test_the_sweep_wakes_every_arrival_a_registered_wake_is_known_to_wake(arrival):
    """THE SWEEP IS NOT BLIND WHERE THE BATTERY SEES (its non-vacuity, over EVERY woken arrival — it answered
    nothing for sixteen of them while it took one interrupt alone at the first idle: the menu chain's, the queued
    delays'): each arrival `WAKES` takes on through the dispatcher to its return, SOME MEMBER OF THE SWEEP wakes
    too — so a wake of the kind those rows make cannot hide among NOT_WOKEN behind a sweep that could not find it.
    (An arrival that needs NO wake — unsync's hand-over, which yields and comes back — returns with nothing
    delivered and before any idle: there is nothing for a sweep to find, and that is what is held of it.)"""
    if not evlib.WAKES[arrival[0]]:
        made = evlib.arrival(*arrival)
        the_rom_s = aes_switch.scheduled(getattr(addrs, made.name), evlib.frame_of(made.name, made.arguments), made.machine)
        assert (the_rom_s.ended, the_rom_s.idles) == (aes_switch.RETURNED, 0)
        return
    assert evlib.the_sweep_wakes(*arrival), f"{arrival}: WAKES names {sorted(evlib.WAKES[arrival[0]])} idle(s), and no member of the sweep wakes it"


CHAINS_ONLY = {("evnt_mesag, none", 0): {"the menu chain"},
               (evlib.BEHIND_THREE_DELAYS, 0): {"more ticks than any time, at each of four successive idles"}}


@pytest.mark.parametrize("arrival", CHAINS_ONLY, ids=evlib.case_id)
def test_a_wake_that_takes_a_chain_is_found_by_its_chain_and_by_no_interrupt_alone(arrival):
    """THE RED OF THE CHAINS, on the two kinds the single sweep was blind to: a message only the screen manager's
    own write brings (three idles, three turns of it) and a time queued behind three delays of its own process (a
    delay run out at each idle) — no interrupt taken alone wakes either, and exactly its chain does."""
    assert arrival in WOKEN and evlib.woken_alone_by(*arrival) == set()
    assert evlib.woken_in_turn_by(*arrival) == CHAINS_ONLY[arrival] == evlib.what_wakes(*arrival)


def test_a_button_held_down_on_an_item_of_the_dropped_menu_wakes_nobody_and_never_idles_again():
    """WHY THE SWEEP'S MENU CHAIN ENDS IN A CLICK, shown once on the ROM's own run of a wait the screen manager's
    message is not for: the press HELD on the item is waited out by ctlmgr IN A LOOP OF YIELDS — the dispatcher
    never idles again and the caller never runs (`aes_evlib.SPINS`: a derivation's whole budget spent) — where the
    same press LET GO leaves the machine idle, unwoken. (Where the desk is the reader the press alone wakes it:
    `WAKES`' chain, which every wake of a message is taken through.)"""
    made = evlib.arrival("evnt_mouse to enter a rectangle above the screen", 0)
    frame = evlib.frame_of(made.name, made.arguments)
    onto_the_item = (evlib.ONTO_THE_VIEW_TITLE, evlib.ONTO_ITS_PLAIN_ITEM)
    assert evlib.EVERY_CHAIN["the menu chain"].at_idles == (*onto_the_item, "a click")
    assert evlib.ends_taken_through(made.name, frame, made.machine, (*onto_the_item, "a press")) == evlib.SPINS
    assert evlib.ends_taken_through(made.name, frame, made.machine, (*onto_the_item, "a click")) == evlib.NEVER


A_KEY_S_WAIT = ("evnt_keybd, none", 0)
RETURN_AFTER_AN_OPENER = {f"{evlib.ONTO_THE_MENU_BAR}, then Return at the next idle", f"{evlib.OFF_IT}, then Return at the next idle",
                          f"{evlib.ONTO_THE_MENU_BAR}, then Return at the poll after it"}
LET_GO_BY_A_CLICK = {"the menu chain", f"{evlib.OFF_IT}, then a click at the next idle"}


def test_each_kind_of_chain_wakes_the_registered_wake_of_its_shape_and_the_sweep_names_what_it_found():
    """EVERY KIND OF MEMBER IS SEEN TO WAKE SOMETHING (a member that could wake nothing holds NOT_WOKEN to nothing):
    the pairs after each opener and the poll between two turns — a key waited for is woken by Return after the mouse
    went onto the bar (the screen manager's turn first), after it went off it, and polled while the screen manager
    stands woken, by exactly those three chains; THE LOCK THE SCREEN MANAGER'S MENU HOLDS (the registered row) is
    given up to no interrupt alone and to exactly two chains — the mouse off the bar then a click, and the menu
    chain, whose click on an item ends the menu too. And `the_sweep_wakes` answers THE MEMBER IT FOUND — an
    interrupt alone before a chain — and None where none wakes."""
    assert evlib.woken_in_turn_by(*A_KEY_S_WAIT) == RETURN_AFTER_AN_OPENER
    lock_s = ROWS[f"aes_ev_block, {waits.THE_LOCK_WAITED_FOR}"]
    frame, machine = evlib.frame_of(lock_s.name, lock_s.arguments), lock_s.machine()
    assert not [alone for alone in evlib.EVERY_INTERRUPT if evlib._taken_alone(lock_s.name, frame, machine, alone) == evlib.RETURNS]
    assert {chain for chain in evlib.EVERY_CHAIN if evlib._taken_in_turn(lock_s.name, frame, machine, chain) == evlib.RETURNS} == LET_GO_BY_A_CLICK
    assert evlib.the_sweep_wakes(*A_KEY_S_WAIT) == "Return" and evlib.the_sweep_wakes("evnt_mesag, none", 0) == "the menu chain"
    assert evlib.the_sweep_wakes(*NOT_WOKEN[0]) is None
    kinds = [(len(chain.at_idles), bool(chain.at_polls)) for chain in evlib.EVERY_CHAIN.values()]
    pairs = 2 * len(evlib.OF_EACH_KIND) - 1                 # each kind after each opener, the mouse off the bar after itself aside
    assert sorted(kinds) == sorted([(3, False), (evlib.TICKS_AT_SUCCESSIVE_IDLES, False), *[(2, False)] * pairs,
                                    *[(1, True)] * len(evlib.TAKEN_BETWEEN_TWO_TURNS)])


ANOTHER_PROCESS_S = [pair for pair in NOT_WOKEN if pair[0] in evlib.ONLY_ANOTHER_PROCESS]


@pytest.mark.parametrize("arrival", ANOTHER_PROCESS_S, ids=evlib.case_id)
def test_what_only_another_process_could_satisfy_is_a_fact_of_the_machine(arrival):
    """THE STATED REASON, READ OFF THE ROM-MADE MACHINE at every arrival of the five scenarios nothing was "tried"
    on (`aes_evlib.ONLY_ANOTHER_PROCESS`): the full pipe is the caller's own, nobody waits to read it and the only
    other process is parked; the empty pipe has no writer waiting and its owner is parked; the lock is held by
    another process than the caller, which is parked AND WAITS FOR A KEY (what the holder itself waits for is read:
    that is why a key ends those runs in the holder, and why their tail is unpinned rather than unwakeable) — or,
    counted to -1, by nobody."""
    assert evlib.held_by_no_process_that_could(*arrival)


def test_a_fact_of_the_machine_is_false_of_a_machine_it_does_not_describe():
    """...AND EACH FACT IS ONE (RED): a reason that were true of every machine would say nothing. Asked of the
    snapshot's desk running — its own pipe empty, the lock free — the only one that holds is the empty pipe's (that
    IS its scenario's machine); and that one is false once a message lies in the screen manager's pipe (the ROM's
    own appl_write to it: the pipe holds sixteen bytes, and its owner is no longer parked)."""
    empty_pipe = "appl_read of the screen manager's pipe, empty"
    plain = make_image(evlib.desk_running())
    assert [name for name, fact in evlib.ONLY_ANOTHER_PROCESS.items() if fact(plain)] == [empty_pipe]
    written = make_image(aes_pdpipe.sent(aes_pdpipe.running(), evlib.SCREEN_MANAGER_PID, evlib.A_MESSAGE))
    assert not evlib.ONLY_ANOTHER_PROCESS[empty_pipe](written)
    # ...and WHO IS PARKED is read, not presumed: over that snapshot the screen manager is, the running desk is not.
    assert evlib._parked(plain, evlib.SCREEN_MANAGER) and not evlib._parked(plain, evlib.SHELL)
    # ...AND WHAT A PARKED HOLDER WAITS FOR: the desk holding the lock was parked for a key; the screen manager's menu
    # holding it (the registered wake's machine) waits for no key — the lock's fact, asked of that holder, is false.
    held_by_the_desk = make_image(evlib.lock_held_by_the_desk())
    held_by_the_menu = make_image(evlib.the_manager_s_menu_holds_the_lock())
    assert evlib.waits_for_a_key(held_by_the_desk, evlib.SHELL) and not evlib.waits_for_a_key(plain, evlib.SHELL)
    assert evlib.lock(held_by_the_menu)[1] == evlib.SCREEN_MANAGER and evlib._parked(held_by_the_menu, evlib.SCREEN_MANAGER)
    assert not evlib.waits_for_a_key(held_by_the_menu, evlib.SCREEN_MANAGER)
    assert not evlib._a_lock_whose_holder_is_parked_for_a_key(evlib.SCREEN_MANAGER)(held_by_the_menu)
    other_s = {scenario for scenario, _nth in ANOTHER_PROCESS_S}
    assert other_s == set(evlib.ONLY_ANOTHER_PROCESS), "every scenario with a fact has a blocked arrival it is read at"


THE_MANAGER_S_WAIT = (evlib.THE_MANAGER_S_RECTANGLE, 3)


def test_the_sweep_finds_the_wake_a_hand_picked_delivery_missed():
    """THE RED OF THE SWEEP, on the scenario that stood among NOT_WOKEN: the screen manager's wait TO ENTER a
    rectangle. The move its entry had tried (out of the rectangle) leaves the ROM's run idling for ever — which is
    all the old test asked — and the sweep finds what wakes it: the move INTO the rectangle, and no other."""
    assert THE_MANAGER_S_WAIT in WOKEN and THE_MANAGER_S_WAIT[0] not in evlib.NOT_WOKEN
    made = evlib.arrival(*THE_MANAGER_S_WAIT)
    with pytest.raises(AssertionError, match="idles for ever AFTER its deliveries"):
        aes_switch.scheduled(getattr(addrs, made.name), evlib.frame_of(made.name, made.arguments), made.machine, {0: evlib.AWAY})
    assert evlib.woken_alone_by(*THE_MANAGER_S_WAIT) == {"the mouse into the rectangle round where it was"}


# One blocked arrival of each kind of wait an interrupt satisfies, and the members of the sweep that wake it. THREE
# ROM FACTS SHOW IN IT: a move onto the menu bar does not satisfy the desk's wait to LEAVE a rectangle (the mouse
# becomes the screen manager's there, and mchange posts a move to its owner's waits alone); the negative-height
# rectangle's first row lies inside the other rectangle (they share a corner); and every button event wakes a
# five-tick timer — a press brings the ticks of its click count (`aes_event.PRESSING`).
INTO_THE_OTHER = {"the mouse into the other rectangle", "the mouse onto the first row of the rectangle of negative height"}
EACH_KIND_S_WAKERS = {
    ("evnt_keybd, none", 0): {"Return"},
    ("evnt_button for a press", 0): {"a press", "a click", "a double click"},
    ("evnt_button for the right button down", 0): {"a right press"},
    ("evnt_mouse to leave the rectangle the mouse is in", 0): INTO_THE_OTHER | {
        "the mouse out of both, into neither", "the mouse under the rectangle above the screen"},
    ("evnt_mouse to enter a rectangle the mouse is not in", 0): INTO_THE_OTHER,
    ("evnt_timer", 0): {"more ticks than any time", "a press", "a click", "a double click", "a right press"},
}


@pytest.mark.parametrize("arrival", EACH_KIND_S_WAKERS, ids=evlib.case_id)
def test_the_sweep_wakes_a_wait_of_each_kind_an_interrupt_satisfies(arrival):
    """...AND THE SWEEP IS NOT VACUOUS: over a wait of each kind an interrupt can satisfy — a key's, a button's (the
    left and the right), a rectangle's to enter and to leave, a timer's — exactly the members that bring that event
    wake it. Every kind NOT_WOKEN could hide a wakeable wait of is one the sweep is seen to wake."""
    assert arrival in WOKEN and evlib.woken_alone_by(*arrival) == EACH_KIND_S_WAKERS[arrival]


def test_a_staged_application_s_woken_cases_register_no_row():
    """THE STAGED-APPLICATION CLASS STAYS TIER 1 ONLY: its blocked cases are woken above on the host's model (the
    desk's shorter timer; the lock handed on with two processes queued), and no registry holds a row over one."""
    labelled = [pair for pair in WOKEN if evlib.STAGED_APPLICATION in pair[0]]
    assert len(labelled) >= 4 and not [name for name in aes_event.SWITCHING_ROWS if evlib.STAGED_APPLICATION in name]


# ---- THE ROWS THAT SWITCH -------------------------------------------------------------------------------------------------------
ROWS = {**waits.WOKEN_ROWS, **queued.WOKEN_ROWS}
Premise, Priced = switching.Premise, switching.Priced
ONCE, D, S = (0,), SHELL, SCREEN_MANAGER
MENU_IDLES, THE_MENU_S_TURNS = (0, 1, 2), (S, S, S, S, D)
THE_DESK_S_DISPATCHES = 40              # the desk, freed to read its pipe, reads on: forty dispatches of its own
THE_DESK_READS_ITS_PIPE = (D,) * THE_DESK_S_DISPATCHES + (S,)
NOTHING, BOTH_RECTANGLES, ONE_EVENT = 0, 3, 1
THE_RECTANGLE_S_WIDTH = evlib.ROUND_THE_MOUSE[2]    # a mouse wait's answer: apret's low word is the rectangle's width
# WHAT EACH ROW IS, read off the ROM's own run (`aes_switching.Premise`): the idles it takes a delivery at, the idles
# it makes, the process that makes the call, the processes its dispatcher enters, and the word the call answers
# (None: an arm that sets no D0 — unsync's hand-over).
PREMISES = {
    "aes_ev_block, a wait for a double click, blocked; woken by the two presses": Premise(ONCE, 1, D, (D,), 2),
    "aes_ev_block, a wait to leave a rectangle, blocked; woken by the mouse leaving it": Premise(ONCE, 1, D, (D,), THE_RECTANGLE_S_WIDTH),
    f"aes_ev_block, {waits.THE_READ_WOKEN}": Premise(MENU_IDLES, 3, D, THE_MENU_S_TURNS, NOTHING),
    f"aes_ev_block, {waits.THE_WRITE_FREED}": Premise((), 0, S, THE_DESK_READS_ITS_PIPE, NOTHING),
    f"aes_ev_block, {waits.THE_LOCK_WAITED_FOR}": Premise((0, 1), 2, D, (S, S, S, D), NOTHING),
    f"aes_ev_block, {waits.THE_MANAGER_QUEUES_ITSELF}": Premise((0, 1), 2, D, (S, D), RETURN_KEY),
    f"aes_ev_block, {waits.THE_MANAGER_RUNS_WITH_THE_LOCK}": Premise(ONCE, 1, D, (S, D), RETURN_KEY),
    "aes_ev_keybd, no key queued, blocked; woken by Return": Premise(ONCE, 1, D, (D,), RETURN_KEY),
    "aes_ev_button, a double click waited for, blocked; woken by the two presses": Premise(ONCE, 1, D, (D,), 2),
    "aes_ev_button, a press waited for, blocked; woken by it": Premise(ONCE, 1, D, (D,), 1),
    "aes_ev_mouse, the mouse in the rectangle it is to leave, blocked; woken by its leaving": Premise(ONCE, 1, D, (D,), THE_RECTANGLE_S_WIDTH),
    "aes_ev_timer, behind three delays pending, blocked; run out a delay at a time": Premise((0, 1, 2, 3), 4, D, (D,), NOTHING),
    "aes_ev_timer, a time of five ticks, blocked; run out by them": Premise(ONCE, 1, D, (D,), NOTHING),
    "aes_ev_timer, no time, blocked; run out by the next tick": Premise(ONCE, 1, D, (D,), NOTHING),
    f"aes_ev_timer, {waits.THE_REMAINDER_DROPPED}": Premise(ONCE, 1, D, (D,), NOTHING),
    f"aes_ev_mesag, {waits.THE_MESSAGE_WOKEN}": Premise(MENU_IDLES, 3, D, THE_MENU_S_TURNS, NOTHING),
    f"aes_ap_rdwr, {waits.THE_READ_WOKEN}": Premise(MENU_IDLES, 3, D, THE_MENU_S_TURNS, NOTHING),
    f"aes_ap_rdwr, {waits.THE_WRITE_FREED}": Premise((), 0, S, THE_DESK_READS_ITS_PIPE, NOTHING),
    "aes_ev_mwait, two rectangles' waits, blocked; both come in one move": Premise(ONCE, 1, D, (D,), BOTH_RECTANGLES),
    "aes_ev_mwait, six waits, blocked; the key's alone comes": Premise(ONCE, 1, D, (D,), ONE_EVENT),
    f"aes_ev_mwait, {queued.THE_MANAGER_S_WAIT_WOKEN}": Premise(ONCE, 1, S, (S,), ONE_EVENT),
    f"aes_unsync, {queued.QUEUED_ITSELF}": Premise((), 0, D, (D,), None),
}
NO_WINDOW = pilots.NO_WINDOW
THE_MENU_S_WINDOW = (1, 1139762, 278034)
THE_DESK_S_WINDOW = (1, 618792, 341550)
# THE WHOLE RUN'S CYCLES by blob (the ROM's, ours — net of the entry both share: `aes_switching.measured_on`), and
# WHAT THE TABLE PRICES (`aes_switching.Priced`, the shipped blob): each shore's OWN cycles; THE CALLER'S OWN and
# the calls of rebound entries it is net of, where the routine reaches one (a single wait round ev_block's twin,
# ev_mesag round ap_rdwr's; ONE_COUNT where it reaches none); and the row's foreign windows — how many, their whole
# cycles, their cycles in the AES's text. A row that moves says why: a frame, a path, the dispatcher itself.
ONE_COUNT = pilots.ONE_COUNT
MEASURED = {
    "aes_ev_block, a wait for a double click, blocked; woken by the two presses":
        ({BENCH: (33174, 27400), SHIPPED: (33174, 27088)}, Priced((12912, 19650), (11320, 16254), 1, NO_WINDOW)),
    "aes_ev_block, a wait to leave a rectangle, blocked; woken by the mouse leaving it":
        ({BENCH: (39746, 34732), SHIPPED: (39746, 34272)}, Priced((15768, 22186), *ONE_COUNT, NO_WINDOW)),
    f"aes_ev_block, {waits.THE_READ_WOKEN}":
        ({BENCH: (1175732, 1169922), SHIPPED: (1175732, 1169654)}, Priced((13606, 20428), *ONE_COUNT, THE_MENU_S_WINDOW)),
    f"aes_ev_block, {waits.THE_WRITE_FREED}":
        ({BENCH: (637572, 633852), SHIPPED: (637572, 633414)}, Priced((7484, 12018), *ONE_COUNT, THE_DESK_S_WINDOW)),
    f"aes_ev_block, {waits.THE_LOCK_WAITED_FOR}":
        ({BENCH: (377140, 371552), SHIPPED: (377140, 371324)}, Priced((14848, 21500), (14628, 21128), 1, (1, 338080, 124096))),
    f"aes_ev_block, {waits.THE_MANAGER_QUEUES_ITSELF}":
        ({BENCH: (70928, 65986), SHIPPED: (70928, 65718)}, Priced((13018, 18972), *ONE_COUNT, (1, 36414, 21870))),
    f"aes_ev_block, {waits.THE_MANAGER_RUNS_WITH_THE_LOCK}":
        ({BENCH: (809802, 807440), SHIPPED: (809802, 807002)}, Priced((6726, 9902), *ONE_COUNT, (1, 793138, 151888))),
    "aes_ev_keybd, no key queued, blocked; woken by Return":
        ({BENCH: (32036, 26660), SHIPPED: (32036, 26348)}, Priced((11152, 17492), (106, 346), 1, NO_WINDOW)),
    "aes_ev_button, a double click waited for, blocked; woken by the two presses":
        ({BENCH: (34230, 27844), SHIPPED: (34230, 27534)}, Priced((13358, 20706), (446, 1056), 1, NO_WINDOW)),
    "aes_ev_button, a press waited for, blocked; woken by it":
        ({BENCH: (34166, 27754), SHIPPED: (34166, 27444)}, Priced((13268, 20642), (446, 1056), 1, NO_WINDOW)),
    "aes_ev_mouse, the mouse in the rectangle it is to leave, blocked; woken by its leaving":
        ({BENCH: (40692, 35156), SHIPPED: (40692, 34698)}, Priced((16194, 23132), (426, 946), 1, NO_WINDOW)),
    "aes_ev_timer, behind three delays pending, blocked; run out a delay at a time":
        ({BENCH: (70454, 59770), SHIPPED: (70454, 60050)}, Priced((24668, 36644), (708, 912), 1, NO_WINDOW)),
    "aes_ev_timer, a time of five ticks, blocked; run out by them":
        ({BENCH: (31078, 26162), SHIPPED: (31078, 26064)}, Priced((11796, 17554), (708, 912), 1, NO_WINDOW)),
    "aes_ev_timer, no time, blocked; run out by the next tick":
        ({BENCH: (30888, 25958), SHIPPED: (30888, 25874)}, Priced((11606, 17364), (516, 720), 1, NO_WINDOW)),
    f"aes_ev_timer, {waits.THE_REMAINDER_DROPPED}":
        ({BENCH: (31078, 26162), SHIPPED: (31078, 26064)}, Priced((11796, 17554), (708, 912), 1, NO_WINDOW)),
    f"aes_ev_mesag, {waits.THE_MESSAGE_WOKEN}":
        ({BENCH: (1176520, 1170322), SHIPPED: (1176520, 1170058)}, Priced((14010, 21216), (214, 418), 1, THE_MENU_S_WINDOW)),
    f"aes_ap_rdwr, {waits.THE_READ_WOKEN}":
        ({BENCH: (1176102, 1170110), SHIPPED: (1176102, 1169844)}, Priced((13796, 20798), (190, 370), 1, THE_MENU_S_WINDOW)),
    f"aes_ap_rdwr, {waits.THE_WRITE_FREED}":
        ({BENCH: (637942, 634040), SHIPPED: (637942, 633604)}, Priced((7674, 12388), (190, 370), 1, THE_DESK_S_WINDOW)),
    "aes_ev_mwait, two rectangles' waits, blocked; both come in one move":
        ({BENCH: (37150, 31694), SHIPPED: (37150, 32030)}, Priced((13734, 19590), *ONE_COUNT, NO_WINDOW)),
    "aes_ev_mwait, six waits, blocked; the key's alone comes":
        ({BENCH: (27054, 23158), SHIPPED: (27054, 23402)}, Priced((8306, 12510), *ONE_COUNT, NO_WINDOW)),
    f"aes_ev_mwait, {queued.THE_MANAGER_S_WAIT_WOKEN}":
        ({BENCH: (29794, 26082), SHIPPED: (29794, 26372)}, Priced((10186, 14252), *ONE_COUNT, NO_WINDOW)),
    f"aes_unsync, {queued.QUEUED_ITSELF}":
        ({BENCH: (14114, 11740), SHIPPED: (14114, 11862)}, Priced((4824, 7352), *ONE_COUNT, NO_WINDOW)),
}


# THE ROWS WHOSE WAIT LEAVES ITS QPB'S ADDRESS IN AN EVB — the routine keeps the QPB in its own frame (ap_rdwr's
# arguments; under ev_mesag too): one longword dropped by name and vetted on every shore. ev_block's own rows on a
# pipe are handed a QPB the case stages outside the stack: one address on both shores, compared.
QPB_IN_ITS_OWN_FRAME = (f"aes_ev_mesag, {waits.THE_MESSAGE_WOKEN}", f"aes_ap_rdwr, {waits.THE_READ_WOKEN}",
                        f"aes_ap_rdwr, {waits.THE_WRITE_FREED}")


def test_every_row_the_waits_register_is_pinned_here():
    assert ROWS.keys() == PREMISES.keys() == MEASURED.keys()
    assert ROWS.keys() <= aes_event.SWITCHING_ROWS.keys()
    leaving_a_qpb = [name for name in ROWS if aes_event.SWITCHING_ROWS[name].qpbs]
    assert tuple(leaving_a_qpb) == QPB_IN_ITS_OWN_FRAME
    for name in leaving_a_qpb:
        held = aes_event.SWITCHING_ROWS[name]
        assert held.qpbs == switching.settled(ROWS[name]).qpbs and len(held.qpbs) == 1
        assert sum(why == aes_event.QPB_ADDRESS_WHY for _lo, _hi, why in held.drops) == 1


def test_every_routine_the_batteries_hold_at_dsptch_has_a_row_that_switches():
    """THE ACCEPTANCE, HELD: each routine of the waits' batteries with an arrival that reaches the dispatcher — a twin
    with a tail — has a registered row that switches (ev_block's key and delay are the pilots'); the routines a wait
    is QUEUED by (iasync and the five waits under it) reach it only through mwait, and have none of their own."""
    reaching = {evlib.arrival(*pair).name for pair in BLOCKED}
    with_a_row = {held.row.name for held in aes_event.SWITCHING_ROWS.values()}
    assert reaching - with_a_row == set(), sorted(reaching - with_a_row)
    assert not {evlib.IASYNC, evlib.AKBIN, evlib.ADELAY, evlib.ABUTTON, evlib.AMOUSE, evlib.AMUTEX} & reaching


@pytest.mark.parametrize("name", ROWS)
def test_the_rom_s_own_run_of_a_row_is_what_its_name_says(name):
    """THE PREMISE, on the ROM's run through its own dispatcher over the row's settled machine: it returns to the
    process that made the call, each interrupt taken at an idle, the dispatcher entering exactly the processes named —
    and the row carries that run's deliveries (`aes_switching.vet_the_premise`: the settling changed nothing an
    interrupt reads or writes)."""
    switching.vet_the_premise(ROWS[name], PREMISES[name])


@pytest.mark.parametrize("name", ROWS)
def test_a_row_is_parked_by_our_own_dispatcher_and_woken_on_both_blobs(name, blob):
    """THE SECOND DIFFERENTIAL OF THE SWITCH, on each blob: our twin blocks in OUR mwait (or yields in our unsync), OUR
    dsptch and disp park it, the interrupts land at the idles the ROM's run took them at, and the process is resumed —
    by our switchto where no other process ran, by the ROM's dispatcher after another's turn. The image the ROM's but
    for the row's drops, the answer, every callee-saved register back; the foreign windows equal to the cycle."""
    whole, priced = MEASURED[name]
    switching.vet_on_a_blob(blob, ROWS[name], PREMISES[name], priced.windows, whole)


@pytest.mark.parametrize("name", ROWS)
def test_the_table_prices_a_row_on_its_own_process_s_cycles(name):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's OWN cycles on each shore under the bar
    — and THE CALLER'S OWN, PINNED, where its run calls a rebound entry (a single wait round ev_block's twin; ev_mesag
    round ap_rdwr's, whose call a foreign window lies INSIDE: a second count net of that window twice is still under
    the bar, and reds here) — and its foreign windows in neither column."""
    switching.vet_the_table_s_price(ROWS[name], MEASURED[name][1])


# ---- TWO RUNS THAT ARE ANOTHER ROW'S, TO THE CYCLE: held at Tier 1, priced once ------------------------------------------------
A_TIME_SHORTER_THAN_A_TICK = switching.SwitchingRow("a time shorter than a tick, blocked; run out by the next tick",
                                                    evlib.EV_TIMER, (waits.HALF_A_TICK_MS,), evlib.desk_running, {0: evlib.ticks(1)})
TWO_TICKS_MS = 2 * evlib.TICK_MS


def test_a_time_shorter_than_a_tick_is_no_time_and_a_tick_and_a_half_is_one_tick():
    """ev_timer's DIVISION, on the ROM's own runs and the C's: half a tick is NO time — the wait of the row "no time",
    the same idles, the same answer, held at Tier 1 (and no row of its own: the same run to the cycle) — and a tick
    and a half is ONE tick's wait (the registered row: woken by the first tick), where two ticks' wait is not."""
    assert switching.companion(A_TIME_SHORTER_THAN_A_TICK).answer is not None
    assert switching.row_name(A_TIME_SHORTER_THAN_A_TICK) not in aes_event.SWITCHING_ROWS
    two_ticks = A_TIME_SHORTER_THAN_A_TICK._replace(arguments=(TWO_TICKS_MS,))
    with pytest.raises(AssertionError, match="idles for ever AFTER its deliveries"):
        switching.scheduled(two_ticks, switching._staged(two_ticks))


def test_the_hand_over_to_a_manager_the_harness_queued_is_a_tier_1_case_and_no_second_row():
    """unsync's hand-over is priced ONCE, over the machine the ROM's own code made (the screen manager queued by its
    own BEG_UPDATE); the same hand-over to a manager queued by the harness's wait — the same run, to the cycle — is
    among the blocked arrivals woken above, and registered nowhere."""
    arrival = ("wind_update(END), the screen manager waiting for the lock", 0)
    assert arrival in WOKEN and evlib.arrival(*arrival).name == evlib.UNSYNC
    assert [name for name in aes_event.SWITCHING_ROWS if name.startswith("aes_unsync,")] == [f"aes_unsync, {queued.QUEUED_ITSELF}"]


# ---- A ROW WHOSE PROCESS IS NOT THE DESK ------------------------------------------------------------------------------------
def test_the_manager_s_own_wait_is_a_row_no_other_process_has_a_turn_in(blob):
    """THE SCREEN MANAGER'S WAIT FOR A RECTANGLE, WOKEN (the scenario that stood among NOT_WOKEN): the row's process
    is the screen manager — its saved context the one dropped — OUR dispatcher parks it and, the move taken at its
    idle, OUR switchto resumes it: no foreign window, the desk never entered."""
    row = ROWS[f"aes_ev_mwait, {queued.THE_MANAGER_S_WAIT_WOKEN}"]
    made = switching.settled(row)
    assert (made.switches.process, made.entered) == (SCREEN_MANAGER, (SCREEN_MANAGER,))
    (lo, hi, _why), = aes_switch.uda_context_drop(aes_event.uda_of(SCREEN_MANAGER, make_image(made.pokes)))
    assert any(lo <= low and high <= hi for low, high, _reason in made.drops), "the dropped context is the screen manager's"
    _measured, watch, foreign = switching.measured_on(blob, row)
    assert (watch.entered, foreign.windows) == ([SCREEN_MANAGER], 0)


def test_the_writer_s_row_is_the_screen_manager_s_and_its_foreign_window_the_desk_s(blob):
    """THE PROCESS IS READ OFF THE MACHINE, AND NOTHING ASSUMES THE DESK: the screen manager's write blocks on the
    desk's full pipe; OUR dispatcher parks the screen manager — its saved context the one dropped, in ITS UDA — and
    enters the DESK, the ROM's own desktop coming out of its evnt_multi: it reads its pipe, which frees the writer,
    and reads on (forty dispatches of its own) until it waits again; the ROM's dispatcher then hands the machine
    back to OUR mwait in the screen manager."""
    row = ROWS[f"aes_ev_block, {waits.THE_WRITE_FREED}"]
    made = switching.settled(row)
    assert made.switches.process == SCREEN_MANAGER and made.entered == THE_DESK_READS_ITS_PIPE
    context = aes_switch.uda_context_drop(aes_event.uda_of(SCREEN_MANAGER, make_image(made.pokes)))
    (lo, hi, _why), = context
    assert any(lo <= low and high <= hi for low, high, _reason in made.drops), "the dropped context is the screen manager's"
    desk_s = aes_switch.uda_context_drop(aes_event.uda_of(SHELL, make_image(made.pokes)))
    (lo, hi, _why), = desk_s
    assert not any(lo <= low < hi for low, _high, _reason in made.drops), "...and nothing of the desk's: its turn is compared"
    _measured, watch, foreign = switching.measured_on(blob, row)
    assert watch.entered[-1] == SCREEN_MANAGER and set(watch.entered[:-1]) == {SHELL} and foreign.windows == 1
    image = make_image(made.pokes)
    assert case.word_in(image, SHELL + aes.PD_QUEUE_INDEX) == aes.PD_QUEUE_BYTES, "the premise: the desk's pipe is full"
    assert len(aes_pdpipe.BLOCKED_WRITE) == aes_event.MESSAGE_BYTES
