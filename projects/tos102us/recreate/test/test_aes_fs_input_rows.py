r"""fs_input PRICED (`src/aes/fslib.c`): Tier 3's rows of the file selector run whole — and what holds a slice cut at
a GEMDOS call.

One call of fs_input is 450,000 to a million ROM instructions, past what one row may spend, so it is priced BY ITS
SHAPES (`aes_event.register_slices`): four sessions a user drives (`test/aes_fs_sessions.py`), each cut where both
shores arrive at one PC — a door call, a GEMDOS call, or a VDI call. Before fm_do's first door call the selector draws
itself, reads its directory, sorts, formats and draws the list with no door call at all (344,000 instructions, more
over a long directory): that stretch is cut at its GEMDOS calls, which over the REPLAY (`aes_fslib`: the handler a
priced run's `trap #1` reaches on both shores) arrive at one PC, the handler's own — and where the sort ends, at the
VDI call that follows it.

The three refusals for want of memory wait on nothing, so each is a plain row over a replay of its own (GEMDOS's
answers the ROM's, derived over an arena the ROM's own Malloc exhausted).
"""
import pytest

from harness import bench_tier3

import aes_event
import aes_fs_sessions as ss
import aes_fslib as fsl
import test_aes_fs_input as sessions
import test_aes_fslib as real
from aes_fs_sessions import (A_C_ROW, AB_TXT_ROW, AUTO_ROW, CANCEL, CLOSER, DOWN_ARROW, LONG, LONGER, MIDDLE, MIXED, RETURN,
                             SHUFFLED, TITLE, TOOLS_ROW, Session, at, click, folder, press, release, schedule)

INPUT, ARGUMENTS = fsl.INPUT, fsl.ARGUMENTS
ENTRY, RETURNED = aes_event.ENTRY, aes_event.RETURN
WAIT, LOCK, UNLOCK = (getattr(aes_event.addrs, name) for name in ("AES_ROM_EV_MULTI", "AES_ROM_TAK_FLAG", "AES_ROM_UNSYNC"))


def wait(nth):
    """The selector's wait of ordinal `nth`: its ev_multi call."""
    return aes_event.door_call(WAIT, nth)


def gemdos(nth):
    """The session's GEMDOS call of ordinal `nth`, where both shores reach the replay's handler."""
    return aes_event.trap_taken(fsl.HANDLER_AT, nth)


def read_of(functions, nth):
    """`(first, last)`: the ordinals of the GEMDOS calls that begin and end the session's directory read `nth` — its
    Fsetdta, and the last call of the search after it (an Fsnext that finds no more, or the bell)."""
    first = [ordinal for ordinal, function in enumerate(functions) if function == fsl.FSETDTA][nth]
    last = first
    while last + 1 < len(functions) and functions[last + 1] in (*fsl.SEARCHES, fsl.CCONOUT_FN):
        last += 1
    return first, last


def priced(path, steps, budget):
    """A priced session: the cursor SHOWN — what an application that hides nothing runs the selector over, and the
    dearer of the two (each draw hides and shows it)."""
    return Session(path, "", schedule(steps), budget, shown=True)


# THE FOUR SESSIONS. Each wait takes what the user does there, never a key typed ahead. The object the folder is
# clicked in is the second row's: after the scroll it holds MIXED's last folder, ZOO, which is empty.
CLICKED = priced(MIXED, [click(A_C_ROW), (release, click(AB_TXT_ROW)), (release, click(AB_TXT_ROW)),
                         (release, click(DOWN_ARROW)), (release, click(TOOLS_ROW)), (release, click(CLOSER)),
                         (release, RETURN)], LONGER)
# ...its waits, by what the user does at each (one fm_do each: the screen is taken and given back once per wait).
A_ROW, ANOTHER_ROW, THE_SAME_ROW, THE_ARROW, A_FOLDER, THE_CLOSE_BOX, THE_RETURN = range(7)
# Thirteen files of one extension, which "*.TXT" keeps whole: the directory whose read and listing measure dearest.
RESPECCED = priced(folder("REVERSE"), [*sessions.RESPEC, click(A_C_ROW), (release, RETURN)], LONG)
DRAGGED_BY = sessions.DRAGGED_BY        # pixels the elevator is dragged: ten rows of the 28-name list, all nine redrawn
DRAGGED = priced(SHUFFLED, [at(sessions.on_the_elevator(), press), at(sessions.on_the_elevator(DRAGGED_BY)), release,
                            at(sessions.low_in_the_track, press), (release, click(TITLE)), (release, click(CANCEL)),
                            release], LONGER)
# ...and its waits: the elevator pressed, moved and let go (the drag's own three), the track, the title, Cancel.
PRESSED, MOVED, LET_GO, THE_TRACK, THE_TITLE, THE_CANCEL = range(6)
RESPEC_WAITS = len(sessions.RESPEC)     # the waits the path's edit takes: the row is clicked at the next
A_HUNDRED = priced(sessions.HUNDRED, [RETURN], MIDDLE)
CLOSED_AT_THE_ROOT = priced(sessions.NO_DRIVE_ROOT, [click(CLOSER), (release, RETURN)], LONG)
# The longest spec whose title fs_newdir builds inside its scratch (a longer one writes over gl_mntree): its title
# still runs over its own 28 bytes of text into the first row's, whose kind byte is then a character of the spec.
LONGEST_SPEC = ("ABCDEFGH" * 5)[:real.LONGEST_SPEC_THAT_FITS - len("*.*")] + "*.*"
ROW_UNDER_A_LONG_SPEC = priced(folder("MIXED", LONGEST_SPEC), [click(AUTO_ROW), (release, RETURN)], MIDDLE)
# EVERY SESSION ENDS ON THE SAME STRETCH, fs_input's own: from where the last fm_do gives the screen back to the
# return — both strings handed back, fm_dial(FMD_FINISH), the button answered, the three blocks freed. A row of its
# own in each session: cut from the last WAIT instead, it is averaged with fm_do's handling of the key or the click
# (0.59-0.68, priced under fm_do) and prints 0.81-0.83.
PUT_AWAY = "the selector put away: the strings handed back, the screen given back, the blocks freed"


def lock(nth):
    """Where the screen is taken for the `nth` time: an fm_do's start, or the drag's (fm_own, twice over)."""
    return aes_event.door_call(LOCK, nth)


def unlock(nth):
    """...and given back: an fm_do's end, or the drag's."""
    return aes_event.door_call(UNLOCK, nth)


def clicked_slices(functions):
    folder_s, parent_s = read_of(functions, 1), read_of(functions, 2)
    return {
        "the form taken, to its first wait": (lock(A_ROW), wait(A_ROW)),
        "a file's row clicked: selected, its name the selection": (wait(A_ROW), wait(ANOTHER_ROW)),
        "another row clicked: the first put down": (wait(ANOTHER_ROW), wait(THE_SAME_ROW)),
        "the same row clicked again": (wait(THE_SAME_ROW), wait(THE_ARROW)),
        "the down arrow: the list scrolled a row": (wait(THE_ARROW), wait(A_FOLDER)),
        "a folder's row clicked: the path made, to its directory's read": (wait(A_FOLDER), gemdos(folder_s[0])),
        "an empty folder read": (gemdos(folder_s[0]), gemdos(folder_s[1])),
        "an empty list formatted and drawn": (gemdos(folder_s[1]), lock(THE_CLOSE_BOX)),
        "the close box: the path cut, to its directory's read": (wait(THE_CLOSE_BOX), gemdos(parent_s[0])),
        "Return: to the form's end": (wait(THE_RETURN), unlock(THE_RETURN)),
        PUT_AWAY: (unlock(THE_RETURN), RETURNED),
    }


# The VDI calls fs_input has made when its first directory is read and sorted — the selector drawn, the path field
# drawn again, the busy mouse set — whatever the directory: the next (`SORTED`) is fs_active setting the arrow back,
# its sort done (`test_the_first_vdi_call_after_the_read_is_the_sort_s_end` holds it to the run).
VDI_CALLS_TO_THE_SORT_S_END = 87
SORTED = aes_event.trap_taken(fsl.VDI_TRAP, VDI_CALLS_TO_THE_SORT_S_END)


def respecced_slices(functions):
    listing, respec = read_of(functions, 0), read_of(functions, 1)
    return {
        "the selector drawn, to its directory's read": (ENTRY, gemdos(listing[0])),
        "its directory read: thirteen files": (gemdos(listing[0]), gemdos(listing[1])),
        "the list formatted and drawn": (SORTED, lock(0)),
        "the path edited, a row clicked: to its directory's read": (wait(RESPEC_WAITS), gemdos(respec[0])),
        "the new spec's names read, listed, the row selected": (gemdos(respec[0]), wait(RESPEC_WAITS + 1)),
        PUT_AWAY: (unlock(1), RETURNED),
    }


# The screen is taken once by each fm_do — and twice round the drag, after the fm_do the press ended has given it back:
# by fs_input's fm_own, then by gr_dragbox under it. So the drag's last giving back is of ordinal 2, and the fm_do
# after it takes the screen for the fourth time (ordinal 3).
DRAG_LOCKS = 2


def dragged_slices(functions):
    title_s = read_of(functions, 1)
    return {
        "the elevator pressed: the screen taken, to the drag's first wait": (wait(PRESSED), wait(MOVED)),
        "the elevator dragged: a move": (wait(MOVED), wait(LET_GO)),
        "the elevator let go: the screen given back": (wait(LET_GO), unlock(DRAG_LOCKS)),
        # From where the screen is given back to where the next fm_do takes it: the scroll itself. Cut there because
        # each whole stretch between two waits is past the cap.
        "the list scrolled to where it was dragged: ten rows": (unlock(DRAG_LOCKS), lock(DRAG_LOCKS + 1)),
        "the track clicked: a page scrolled": (unlock(DRAG_LOCKS + 1), lock(DRAG_LOCKS + 2)),
        "the title clicked: to its directory's read": (wait(THE_TITLE), gemdos(title_s[0])),
        "Cancel clicked: to the form's end": (wait(THE_CANCEL), unlock(DRAG_LOCKS + 3)),
        PUT_AWAY: (unlock(DRAG_LOCKS + 3), RETURNED),
    }


def hundred_slices(functions):
    listing = read_of(functions, 0)
    return {
        "its directory read: a hundred names, the bell": (gemdos(listing[0]), gemdos(listing[1])),
        "the list sorted": (gemdos(listing[1]), SORTED),
        PUT_AWAY: (unlock(0), RETURNED),
    }


def no_drive_slices(functions):
    root_again = read_of(functions, 1)
    return {
        # THE ROM's DEFECT priced (`test_aes_fs_input.py`): fs_back scans down from below the path's buffer, 849 bytes
        # in this machine. Cut from the wait, as the close box's other row is.
        "the close box: fs_back's scan below the path's buffer, to its directory's read": (wait(0), gemdos(root_again[0])),
        # ...and THE ARM ALONE, from where fm_do gives the screen back: the scan with nothing of fm_do's in front of it.
        "the close box's arm alone, from the form's end: the scan, to its directory's read": (unlock(0), gemdos(root_again[0])),
        PUT_AWAY: (unlock(1), RETURNED),
    }


def long_spec_slices(functions):
    listing, folder_s = read_of(functions, 0), read_of(functions, 1)
    return {
        "the selector drawn over a path of 46 characters, to its directory's read": (ENTRY, gemdos(listing[0])),
        "a row clicked whose kind is the title's overrun: the path made, to its directory's read": (wait(0), gemdos(folder_s[0])),
        PUT_AWAY: (unlock(1), RETURNED),
    }


CLICKS, RESPEC, DRAG, LISTED, NO_DRIVE, LONG_SPEC = (
    "rows, a scroll, a folder, the close box, Return", "a spec typed, a row", "a drag, a page, the title, Cancel",
    "a hundred names", "a root with no drive", "a spec that fills the title's scratch")
PRICED_SESSIONS = {CLICKS: (CLICKED, clicked_slices), RESPEC: (RESPECCED, respecced_slices), DRAG: (DRAGGED, dragged_slices),
                   LISTED: (A_HUNDRED, hundred_slices), NO_DRIVE: (CLOSED_AT_THE_ROOT, no_drive_slices),
                   LONG_SPEC: (ROW_UNDER_A_LONG_SPEC, long_spec_slices)}


def slices_of(session_name):
    """`{row label: Slice ends}` of the priced session `session_name`."""
    session, cut = PRICED_SESSIONS[session_name]
    _real, _replayed, script = ss.machine_of(session)
    return {f"{session_name}: {label}": ends for label, ends in cut(script.functions).items()}


# The no-memory arms, by how many bytes GEMDOS's arena is left with.
NO_MEMORY_ROWS = {"no memory: the names refused": sessions.NO_MEMORY_ARMS["no memory at all: the names refused"][0],
                  "the index refused: the names freed": sessions.NO_MEMORY_ARMS[
                      "room for the names alone: the index refused, the names freed"][0],
                  "the DTA refused: the names and the index freed": sessions.NO_MEMORY_ARMS[
                      "room for the names and the index: the DTA refused, both freed"][0]}


# ---- the registry: Tier 3's rows ------------------------------------------------------------------------------------------
# Each shape's WORST realistic row, the candidates measured as Tier 3 measures a slice (four digits, then as printed).
# THE WORST OF ALL is the close box's arm over a root with no drive, ALONE — from fm_do's end, where no handling of
# the click (0.59) is in front of it: 0.96, and 1.00 with its thunks. The ROM's defect makes fs_back scan 849 bytes;
# the C calls fs_back there as the ROM does (`fs_back_called`: 78 cycles a byte against the ROM's 64). INLINED, that
# scan cost 114 a byte and the arm measured 1.20 (1.25 with thunks), over the bar, behind a wait-cut row of 1.03.
# Then the selector's put-away, 0.88 in every session (0.98 with thunks): the long spec's 0.8821, 0.8754-0.8784 the
# others'.
# Left out, none its shape's worst:
#   * every row with the cursor hidden (0.000-0.013 lower);
#   * over a spec that fills the title's scratch: its read 0.72, its list formatted and drawn 0.8122 (thirteen
#     files' 0.8162);
#   * the listing over other directories — read: twenty-eight names 0.82, twelve with folders among them 0.81, the
#     root's folders 0.76, a missing folder 0.75; sorted: thirteen names in reverse order 0.75; formatted and drawn:
#     a hundred names 0.8159 against the thirteen's 0.8162, twelve with folders 0.80 (with their sort);
#   * an empty row clicked 0.64; a row up 0.71, up at the top 0.61; the list's own box 0.59; a five-row drag's scroll
#     0.78, a drag back up 0.78, a page up 0.78; OK clicked 0.78, a file double-clicked 0.75, an empty row
#     double-clicked 0.75.
def _register_rows():
    for session_name, (session, _cut) in PRICED_SESSIONS.items():
        real, replayed, _script = ss.machine_of(session)
        aes_event.register_slices(INPUT, ARGUMENTS, replayed, ss.interrupts_of(session, real), slices_of(session_name),
                                  objects=True, budget=session.budget)
    for label, left in NO_MEMORY_ROWS.items():
        fsl.register(label, INPUT, ARGUMENTS, sessions.no_memory_replayed(left), door=fsl.replay_doors())
    # ...and through its call word: verified, unpriced.
    fsl.register("no memory: the names refused", INPUT, ARGUMENTS, sessions.no_memory_replayed(0), door=fsl.replay_doors(),
                 through_line_f=True)


_register_rows()


# bench/tier3.py imports every battery — this module among them — so it is loaded where a test first asks, not here.
@pytest.fixture(scope="module")
def tier3():
    return bench_tier3()


@pytest.fixture(scope="module")
def bench(tier3):
    return tier3.RomBench()


def _row(tier3, session_name, label):
    return tier3.row_named(("aes_fs_input", f"{session_name}: {label}"))


# ---- A SLICE CUT AT A GEMDOS CALL: ours held to the ROM's there ----------------------------------------------------------
READ_ROW = (RESPEC, "its directory read: thirteen files")
UNREAD_BYTE = aes_event.UNREAD_BYTE     # where a RED test takes our run astray (`aes_event.astray`)
# Every case here is ONE priced session's: collected with it (`test/conftest.py`), by the session's name.
of_the_respec_session = pytest.mark.collected_with(RESPEC)
of_the_drag_session = pytest.mark.collected_with(DRAG)


@of_the_respec_session
def test_a_slice_between_two_gemdos_calls_is_priced_with_our_memory_the_rom_s_at_both(tier3, bench):
    """The directory's read, from its Fsetdta to its last Fsnext — no door call before, inside or at either end: our
    build reaches the replay's handler as the ROM does, its memory the ROM's at both arrivals, and is priced on the
    instructions the ROM spends between them."""
    row = _row(tier3, *READ_ROW)
    assert all(end.pc == fsl.HANDLER_AT for end in row.slice)
    spent = aes_event.slice_cost_of(tier3.registered(row), row.slice)
    measured = tier3.measure(row, bench)
    assert (measured.original_insns, measured.original_cycles) == (spent["insns"], spent["cycles"])
    assert not measured.door_windows, "the premise: no door call inside the read"


def _our_run_astray(tier3, monkeypatch, from_stop, until_stop):
    """Our blob's run with UNREAD_BYTE inverted from its stop of ordinal `from_stop` until its stop `until_stop`,
    where it is put back (the stops of a marked run: each door call and its return, each GEMDOS call and its return):
    a C astray over that stretch in a byte nothing reads, whose final image is the ROM's again (`aes_event.astray`)."""
    our_windows = tier3.our_windows
    monkeypatch.setattr(tier3, "our_windows", lambda elf, delivered=None: aes_event.astray(
        our_windows(elf, delivered), lambda _watch, nth: nth in (from_stop, until_stop)))


STOPS_PER_CALL = 2                      # a marked trap is stopped at twice: its handler, and where it returns to


@of_the_respec_session
def test_a_slice_our_build_diverged_before_its_gemdos_call_is_refused_by_name(tier3, bench, monkeypatch):
    """THE RED: our run astray from its first GEMDOS call (the names' Malloc) until past the Fsetdta the slice starts
    at, and back as the ROM's before it returns — the whole run's differential sees nothing; the mark at the GEMDOS
    call does, and refuses by name."""
    row = _row(tier3, *READ_ROW)
    start = row.slice.start.nth
    _our_run_astray(tier3, monkeypatch, 0, STOPS_PER_CALL * start + 1)
    with pytest.raises(AssertionError, match=rf"our run diverged before the slice's start — at arrival {start} at "
                                             rf"{fsl.HANDLER_AT:#x} .*1 bytes differ.*{UNREAD_BYTE:#x}"):
        tier3.measure(row, bench)


@of_the_respec_session
def test_a_divergence_healed_before_the_gemdos_call_is_no_refusal(tier3, bench, monkeypatch):
    """...and the same byte put back BEFORE the slice's start (at the first Malloc's return) is not its business."""
    row = _row(tier3, *READ_ROW)
    whole = tier3.measure(row, bench)
    _our_run_astray(tier3, monkeypatch, 0, 1)
    assert tier3.measure(row, bench).own_cycles == whole.own_cycles


@of_the_respec_session
def test_a_slice_our_build_diverged_inside_is_refused_at_its_gemdos_call(tier3, bench, monkeypatch):
    """...and astray from the slice's start until past its end — the last Fsnext — it is refused at the end."""
    row = _row(tier3, *READ_ROW)
    start, stop = (end.nth for end in row.slice)
    _our_run_astray(tier3, monkeypatch, STOPS_PER_CALL * start + 1, STOPS_PER_CALL * stop + 1)
    with pytest.raises(AssertionError, match="our run diverged inside the slice"):
        tier3.measure(row, bench)


# ---- the sessions' cuts --------------------------------------------------------------------------------------------------
def _registered(session_name):
    """The registered session `session_name` (`aes_event.INTERRUPTED_ROWS`, by its first row)."""
    return aes_event.INTERRUPTED_ROWS[f"aes_fs_input, {next(iter(slices_of(session_name)))}"]


def _spent(registered, *ends):
    return aes_event.slice_cost_of(registered, aes_event.Slice(*ends))


@of_the_respec_session
def test_the_listing_s_four_cuts_partition_the_stretch_before_the_first_door_call():
    """The selector drawn, its directory read, the list sorted, the list formatted and drawn: what the ROM spends in
    each sums to what it spends from its entry to fm_do's first door call — a stretch itself past the cap."""
    registered = _registered(RESPEC)
    drawn, read, formatted = list(slices_of(RESPEC).values())[:3]
    assert drawn[1] == read[0] and formatted[0] == SORTED
    parts = [_spent(registered, *ends) for ends in (drawn, read, (read[1], SORTED), formatted)]
    marks, _memory = aes_event.sliced_of(registered, aes_event.Slice(ENTRY, lock(0)))
    whole = marks.spent("the listing")
    assert {total: sum(part[total] for part in parts) for total in whole} == whole
    assert whole["insns"] > aes_event.SLICE_INSNS


@of_the_respec_session
def test_the_first_vdi_call_after_the_read_is_the_sort_s_end():
    """Between the read's last GEMDOS call and the VDI call the sort's slice ends at, the ROM makes no VDI call: the
    arrival of that ordinal is the first after the read."""
    registered = _registered(RESPEC)
    read_s_end = slices_of(RESPEC)[f"{RESPEC}: its directory read: thirteen files"][1]
    timeline = aes_event.timeline_of(registered, traps=(fsl.HANDLER_AT, fsl.VDI_TRAP))
    arrivals = [arrival.at for arrival in timeline if arrival.at != RETURNED]
    assert arrivals[arrivals.index(read_s_end) + 1] == SORTED


@of_the_drag_session
@pytest.mark.parametrize("ends", ((wait(LET_GO), wait(THE_TRACK)), (wait(THE_TRACK), wait(THE_TITLE))),
                         ids=("the drag's scroll", "the page"))
def test_a_scroll_of_the_whole_list_between_its_two_waits_is_past_the_cap(ends):
    """Why the ten-row drag's scroll and the page are cut at fm_do's own door calls: from the wait the scroll is
    asked at to the next, the ROM spends more than a slice may."""
    with pytest.raises(AssertionError, match="past SLICE_INSNS"):
        _spent(_registered(DRAG), *ends)
