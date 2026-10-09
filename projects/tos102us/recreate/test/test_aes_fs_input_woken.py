r"""fs_input's SESSIONS THE USER IS WAITED FOR IN, PRICED (`test_aes_fs_input_rows.PRICED_WOKEN`): a session whose
waits BLOCK and are woken through the dispatcher is a row that switches CUT INTO SLICES
(`aes_event.register_woken_slices`) — each slice between two arrivals of the selector's OWN process
(`aes_event.Marks`), held on two counts, net of every turn of another process.

Two sessions: one in which only the user is waited for (a row clicked, then Return, each while a wait is blocked),
and one in which the selector is called while THE SCREEN MANAGER'S MENU HOLDS THE SCREEN — fm_do's lock is waited
for, and what ends that wait is the screen manager's own three turns: one foreign window, inside a slice and inside
one door call. Held here: each session's premise on the ROM's own run, its Tier 1 companion, the whole session's
second differential on both blobs, each slice's price, the partition across the switch — and the REDs of what makes
a slice's marks one process's.
"""
import re

import pytest

from harness import bench_tier3

import aes
import aes_event
import aes_fs_sessions as ss
import aes_fslib as fsl
import aes_switching
import case
import test_aes_fs_input as sessions
import vdi
from test_aes_fs_input_rows import HELD_UP, PRICED_WOKEN, PUT_AWAY, THE_LOCK_WAITED_FOR, WAITED, woken_slices_of


# bench/tier3.py imports every battery, so it is loaded where a test first asks, not here.
@pytest.fixture(scope="module")
def tier3():
    return bench_tier3()


@pytest.fixture(scope="module")
def bench(tier3):
    return tier3.RomBench()


# ---- what each session and each slice is held to -----------------------------------------------------------------------------
SHELL, MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
BENCH_BLOB, SHIPPED_BLOB = "bench", "bench_shipped"
THE_MANAGER_LETS_ITS_MENU_GO = (1, 338080, 124096)      # one window, three turns of it: whole cycles, and in the AES's text
NO_WINDOW = aes_switching.NO_WINDOW
# What the ROM's own run of each IS (`aes_switching.Premise`): the idles it takes a delivery at, the idles it makes,
# the process that makes the call, the processes its dispatcher enters, the word fs_input answers.
WOKEN_PREMISES = {
    WAITED: aes_switching.Premise((0, 1), 2, SHELL, (SHELL, SHELL), sessions.DONE),
    HELD_UP: aes_switching.Premise((0, 1, 2), 3, SHELL, (MANAGER, MANAGER, MANAGER, SHELL, SHELL), sessions.DONE),
}
# THE WHOLE RUN on each blob (the ROM's cycles, ours, net of the entry both share) and its foreign windows.
WOKEN_WHOLE_RUN = {
    WAITED: ({BENCH_BLOB: (5097098, 5053486), SHIPPED_BLOB: (5097098, 4961284)}, NO_WINDOW),
    HELD_UP: ({BENCH_BLOB: (4989256, 4976948), SHIPPED_BLOB: (4989256, 4896116)}, THE_MANAGER_LETS_ITS_MENU_GO),
}
# WHAT THE TABLE PRICES of each slice (`aes_switching.Priced`): each shore's OWN cycles (ours, the ROM's), THE
# CALLER'S OWN (net of the rebound entries' calls), the calls inside it, and the foreign windows INSIDE THE SLICE —
# in neither column. A row that moves says why: the selector's body, a twin, the dispatcher.
WOKEN_PRICED = {
    (WAITED, "the first wait blocked; a file's row clicked while it waits: selected, its name the selection"):
        ((106680, 164226), (82826, 127668), 5, NO_WINDOW),
    (WAITED, "the next wait blocked; Return typed while it waits: to the form's end"): ((46278, 69306), (25748, 38014), 2, NO_WINDOW),
    (WAITED, PUT_AWAY): ((77992, 89024), (77784, 88658), 1, NO_WINDOW),
    (HELD_UP, THE_LOCK_WAITED_FOR): ((32860, 50126), (16594, 25832), 3, THE_MANAGER_LETS_ITS_MENU_GO),
    (HELD_UP, "the first wait blocked; Return typed while it waits: to the form's end"): ((41270, 64160), (22068, 34158), 2, NO_WINDOW),
}
# The door calls each whole session makes — and, of them, the one a foreign window lies inside.
WOKEN_DOOR_CALLS = {WAITED: 10, HELD_UP: 6}
THE_MUTEX_WAIT = 1                      # HELD UP's door call of ordinal 1: ev_block, after tak_flag's refusal
MOUSE_SHOWN = aes.header_constants("gsx.h")["AES_GL_MOUSE_SHOWN"]      # 0 hidden, 1 shown: inside the name scratch's span
# Every case here is ONE session's: collected with it (`test/conftest.py`), by the session's name.
of_a_woken_session = pytest.mark.collected_with(by=lambda params: params.get("session") or params["key"][0])
of_the_held_up_session = pytest.mark.collected_with(HELD_UP)


def _woken(session_name):
    """The registered session `session_name` as its row (`aes_switching.SwitchingRow`)."""
    return ss.woken_row(PRICED_WOKEN[session_name][0], session_name)


def _woken_slice(tier3, session_name, label):
    return tier3.row_named(("aes_fs_input", f"{session_name}: {label}"))


@pytest.fixture(scope="module")
def priced_sessions(tier3, bench):
    """This worker's memo of the sessions measured (`tier3.Sessions`): a session's slices share one pair of runs."""
    return tier3.Sessions(bench)


def test_every_slice_of_a_session_that_switches_is_pinned_here_and_shares_its_session_s_one_record():
    """THE REGISTRY'S SLICED ROWS THAT SWITCH ARE THE PINNED ONES — and each session's slices are ONE record
    (`aes_event.session_of`: one settling, one companion, one pair of runs), a door user's, registered with the
    companion its drops need and the budget its derivations are held to."""
    registered = {name: held for name, held in aes_event.SWITCHING_ROWS.items() if name in aes_event.SLICED_ROWS}
    assert sorted(registered) == sorted(f"aes_fs_input, {session}: {label}" for session, label in WOKEN_PRICED)
    for session_name in PRICED_WOKEN:
        records = {id(aes_event.session_of(f"aes_fs_input, {label}")) for label in woken_slices_of(session_name)}
        held = aes_event.session_of(f"aes_fs_input, {next(iter(woken_slices_of(session_name)))}")
        assert len(records) == 1 and held.row == _woken(session_name) and held.row.door and held.row.budget
    assert all(name in case.tier3_undropped() for name in registered), "a switching row drops, and has its companion"


@pytest.mark.parametrize("session", PRICED_WOKEN)
@of_a_woken_session
def test_the_rom_s_own_run_of_a_session_the_user_is_waited_for_in_is_what_its_name_says(session):
    """THE PREMISE (`aes_switching.vet_the_premise`), on the ROM's run through its own dispatcher over the session's
    settled machine: every wake taken at the idle it is named at, the dispatcher entering exactly the processes
    named — the selector's alone where only the user is waited for, THE SCREEN MANAGER'S three times where its menu
    holds the screen — fs_input answering DONE; and the GEMDOS calls that run makes are its script's, to the last,
    each handed the frame the script's answer was given to.
    HOW IT ENDS: the session over the same user's own machine ends AS THAT USER NEVER WAITED FOR ENDS (the selector,
    what it hands back, the screen). The one over the screen manager's menu runs over ANOTHER machine, and the
    property is not claimed of it (`aes_fs_sessions`): what it differs by is THE MOUSE, pinned — the cursor's own
    pixels (it was moved onto the bar and off it) and the word that says it is shown, which lies in the span of the
    selector's name scratch — and nothing else of what is visible."""
    woken = PRICED_WOKEN[session][0]
    the_rom_s = aes_switching.vet_the_premise(_woken(session), WOKEN_PREMISES[session])
    ss.vet_its_gemdos_calls(woken, the_rom_s.memory)
    if woken.running is None:
        ss.vet_it_ends_as_never_waited_for(woken, the_rom_s.memory, sessions.VISIBLE)
        return
    with pytest.raises(AssertionError, match="is not claimed to end as `same` ends"):
        ss.vet_it_ends_as_never_waited_for(woken, the_rom_s.memory, sessions.VISIBLE)
    assert ss.spans_differing_from_never_waited_for(woken, the_rom_s.memory, sessions.VISIBLE) == [fsl.NAME, vdi.SCREEN.base]
    never_waited_for = ss.machine_of(woken.same)[2].memory
    in_the_scratch_s_span = {at for at in range(fsl.NAME, fsl.NAME + fsl.NAME_ROOM) if the_rom_s.memory[at] != never_waited_for[at]}
    assert in_the_scratch_s_span <= set(range(MOUSE_SHOWN, MOUSE_SHOWN + aes.WORD_BYTES)), "the name scratch itself is the same"
    assert (case.word_in(the_rom_s.memory, MOUSE_SHOWN), case.word_in(never_waited_for, MOUSE_SHOWN)) == (0, 1)


@pytest.mark.parametrize("session", PRICED_WOKEN)
@of_a_woken_session
def test_a_session_the_user_is_waited_for_in_is_held_at_tier_1_through_its_wakes(session):
    """ITS COMPANION (`aes_switching.companion`, every slice's): the C through the host's model, the door bound, held
    to the ROM's own run through its dispatcher — every frame handed, every byte outside the run's own stack — the
    screen manager's turns the ROM's own code in the host's run too."""
    ran = aes_event.held_through_its_wake(_woken(session))
    assert ran.answer == sessions.DONE and len(ran.calls) == WOKEN_DOOR_CALLS[session]
    assert tuple(ran.entered) == tuple(WOKEN_PREMISES[session].entered)


@pytest.mark.parametrize("session", PRICED_WOKEN)
@of_a_woken_session
def test_a_session_the_user_is_waited_for_in_switches_through_our_dispatcher_on_both_blobs(session, blob):
    """THE SECOND DIFFERENTIAL OF THE WHOLE SESSION ON EACH BLOB (`aes_switching.vet_on_a_blob`): the selector parked
    by OUR dsptch at each wait that blocks and resumed — by our switchto where only the user was waited for, by the
    ROM's dispatcher after the screen manager's turns — every door call opened closed, handed the ROM's frames; the
    image the ROM's but for the row's drops, every callee-saved register back across each switch."""
    whole, windows = WOKEN_WHOLE_RUN[session]
    _measured, watch, _foreign = aes_switching.vet_on_a_blob(blob, _woken(session), WOKEN_PREMISES[session], windows, whole)
    assert (watch.inner.closed, watch.inner.calls) == (WOKEN_DOOR_CALLS[session],) * 2
    inside = [nth for nth, window in enumerate(watch.inner.foreign_inside) if any(window)]
    assert inside == ([THE_MUTEX_WAIT] if windows != NO_WINDOW else []), "the window lies inside ev_block's call, and no other"


@pytest.mark.parametrize("key", WOKEN_PRICED, ids=[f"{session}: {label}" for session, label in WOKEN_PRICED])
@of_a_woken_session
def test_a_slice_of_a_session_that_switches_is_priced_on_its_own_process_s_cycles(key, tier3, priced_sessions):
    """WHAT THE TABLE READS OF EACH SLICE: its OWN cycles on each shore — the wait that blocks, our dispatcher's park
    and the wake inside them — THE CALLER'S OWN net of the rebound entries' calls, PINNED (a second count net of the
    wrong thing stays under the bar), and the foreign windows inside the slice in NEITHER column: the slice the
    screen manager's turns lie in is priced on the selector's own 5,817 instructions, not on the menu's. Both counts
    under the bar with their thunks; the slice under the cap ON THE ROW'S OWN RUN."""
    row = _woken_slice(tier3, *key)
    measured = tier3.measure(row, priced_sessions.bench, priced_sessions)
    read = aes_switching.Priced(measured.own_cycles, tier3.caller_own_cycles(measured), measured.rebound_calls,
                                tuple(tier3.foreign_of(measured)))
    assert read == aes_switching.Priced(*WOKEN_PRICED[key]), f"{key}: the table prices {read}: say why it moved"
    assert tier3.counts_within_bar_with_glue(measured) and measured.original_insns < aes_event.SLICE_INSNS


@pytest.mark.parametrize("session", PRICED_WOKEN)
@of_a_woken_session
def test_the_slices_of_a_session_that_switches_and_its_stretches_are_its_whole_run_net_of_its_windows(session, tier3, bench, priced_sessions):
    """THE PARTITION HOLDS ACROSS A SWITCH, ON EACH PRICED SESSION: the session's slices and the stretches no slice
    prices are together the WHOLE run's own cycles on each shore (which the whole run's measurement holds net of
    its foreign windows) and its rebound entries' calls — so nothing of the screen manager's turns is in any slice
    or stretch, nothing of the selector's is lost at a mark beside one, and where only the user is waited for
    nothing is lost at a self-resume either."""
    rows = [tier3.row_named(("aes_fs_input", label)) for label in woken_slices_of(session)]
    priced = [tier3.measure(row, bench, priced_sessions) for row in rows]
    stretches = tier3.uncovered_stretches(rows[0], bench)
    whole, _blob, _original, _windows = tier3._held_through_the_os(rows[0], bench)
    assert tuple(tier3.foreign_of(whole)) == WOKEN_WHOLE_RUN[session][1]
    own = [stretch.own_cycles for stretch in stretches] + [each.own_cycles for each in priced]
    assert tuple(map(sum, zip(*own))) == whole.own_cycles
    inside = [stretch.rebound_own for stretch in stretches] + [tier3.rebound_own_of(each) for each in priced]
    assert tuple(map(sum, zip(*inside))) == tier3.rebound_own_of(whole)


# ---- A SLICE'S MARKS ARE THE ROW'S PROCESS'S: the REDs, on the session another process runs in ---------------------------
def _the_lock_s_slice(tier3):
    row = _woken_slice(tier3, HELD_UP, THE_LOCK_WAITED_FOR)
    assert aes_event.switching(row.delivered) and row.slice, "the premise: a slice of a session that switches"
    return row


@of_the_held_up_session
def test_marks_never_told_of_a_foreign_window_price_the_slice_on_another_process_s_cycles_and_are_refused(tier3, bench, monkeypatch):
    """THE RED of the telling (`aes_event.Marks.foreign_window_opened` / `_closed`): with the marks deaf to the
    window, the ROM's shore's own cycles between the slice's two marks hold the screen manager's 124,096 in the
    AES's text and ours hold none — the slice would print 0.19 where it is 0.66. Refused by name: the OS both sides
    run no longer costs the two shores the same."""
    row = _the_lock_s_slice(tier3)
    monkeypatch.setattr(aes_event.Marks, "foreign_window_opened", lambda self: None)
    monkeypatch.setattr(aes_event.Marks, "foreign_window_closed", lambda self: None)
    with pytest.raises(AssertionError, match="inside its slice the OS both sides run cost ours"):
        tier3.measure(row, bench)


@of_the_held_up_session
def test_a_mark_s_memory_is_compared_outside_the_dispatcher_s_stack_which_is_ours_until_the_run_ends(tier3, bench, monkeypatch):
    """THE RED of what a mark's compare leaves out (`tier3._differing_at_a_mark`): our dispatcher's frames lie on the
    dispatcher's stack from the first switch on — deeper than the ROM's, in bytes the ROM's run never stored, so no
    drop of the row names them — and our image is given back over them only as the run ends. Compared at a mark
    they are a divergence that is none: every byte named lies in that stack."""
    row = _the_lock_s_slice(tier3)
    differing_at_a_mark, put_back_for = tier3._differing_at_a_mark, tier3.put_back_for

    def comparing_the_stack(*row_and_blob):
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(tier3, "put_back_for", lambda _dropped: ())
            return differing_at_a_mark(*row_and_blob)
    monkeypatch.setattr(tier3, "_differing_at_a_mark", comparing_the_stack)
    with pytest.raises(AssertionError, match="our run diverged inside the slice") as differs:
        tier3.measure(row, bench)
    lo, hi = aes_event.DISPATCHER_STACK
    named = [int(at, 16) for at in re.findall(r"(0x[0-9a-f]+) the ROM's=", str(differs.value))]
    assert named and all(lo <= at < hi for at in named) and put_back_for(row.dropped) == ((lo, hi),)


@of_the_held_up_session
def test_a_slice_whose_end_our_run_reaches_on_the_other_side_of_a_window_is_refused_by_name(tier3, bench, monkeypatch):
    """THE RED of the marks' agreement (`aes_event.vet_the_marks_agree`): our shore's marks counting one window
    fewer than passed — as a run would whose mark fell before the screen manager's turn where the ROM's falls after
    it — is another slice than the ROM's, and is refused where the two are compared, not priced net of another thing."""
    row = _the_lock_s_slice(tier3)
    our_marks = tier3._our_marks

    def a_window_short(*made, **marked):
        marks = our_marks(*made, **marked)
        marks.foreign_window_closed = lambda: type(marks).foreign_window_closed(marks) or setattr(marks, "_windows", 0)
        return marks
    monkeypatch.setattr(tier3, "_our_marks", a_window_short)
    with pytest.raises(AssertionError, match=r"after 0 foreign window\(s\) where the ROM's ends after 1"):
        tier3.measure(row, bench)


def test_two_shores_marks_that_put_other_turns_inside_a_slice_are_refused_by_name(tier3):
    """THE RED of a slice's own windows (`tier3._foreign_inside_the_slice`), on marks made by hand: a slice from the
    entry to the return with one window of 900 cycles (400 of them in the AES's text, on the ROM's shore) is that
    `Foreign` — and our shore's marks holding another turn's cost there, a cycle of OUR build inside it, or no
    window at all, are refused by name: the slice would be priced net of another thing on each shore."""
    def marks(inside=900, **more):
        totals = {"insns": 0, "cycles": 0, **dict.fromkeys(more, 0)}
        made = aes_event.Marks(aes_event.Slice(aes_event.ENTRY, aes_event.RETURN), lambda: dict(totals))
        if inside:
            made.foreign_window_opened()
            totals.update(cycles=inside, **more)
            made.foreign_window_closed()
        totals["insns"] += 1
        made.returned(0)
        return made
    assert tier3._foreign_inside_the_slice("a row", marks(blob=0), marks(aes=400)) == tier3.Foreign(1, 900, 400)
    assert tier3._foreign_inside_the_slice("a row", marks(0, blob=0), marks(0, aes=0)) == tier3.NO_FOREIGN_WINDOW
    for ours in (marks(901, blob=0), marks(blob=4), marks(0, blob=0)):
        with pytest.raises(AssertionError, match="do not put the same turns of another process inside the slice"):
            tier3._foreign_inside_the_slice("a row", ours, marks(aes=400))


def test_a_sliced_row_whose_run_arrives_at_no_door_entry_is_refused_by_name(tier3, bench):
    """A SLICE'S MARKS ARE TAKEN BY THE RUN'S DOOR WATCH (RED): a row that switches and whose run arrives at no door
    entry — a wait of the event layer's own, entered at its twin — has none, and cut into slices it is refused by
    name where it would be measured, never priced between two marks nobody took."""
    leaf = next(row for row in tier3.ROWS if aes_event.switching(row.delivered) and not tier3.arrives_at_an_entry(row))
    a_slice = _woken_slice(tier3, HELD_UP, THE_LOCK_WAITED_FOR).slice
    with pytest.raises(AssertionError, match="a sliced row whose run arrives at no door entry"):
        tier3.measure(leaf._replace(slice=a_slice), bench)
