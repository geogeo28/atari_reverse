"""`aes_event`'s helpers that EVERY battery's import stands on, held where no battery is imported: the one vocabulary
of interrupts (what each of a user's actions is, as the ROM's own interrupt code leaves it) and the settling of a
priced row's words. A change that breaks one of these breaks the registries' own derivations — every battery then
fails to IMPORT, and a suite that cannot be collected names no assertion. These tests import the door's module alone
(it registers no row), so such a change fails HERE, by name.
"""
import pytest

from harness import addrs, make_image

import aes
import aes_event
import case
import vdi
from case import merge_pokes

LEFT, RIGHT, UP = aes_event.LEFT_BUTTON, aes_event.MOUSE_STAT_RIGHT_BUTTON, 0
ONE_CLICK, TWO_CLICKS = 1, 2


def test_a_kept_run_s_image_is_the_one_the_run_left():
    """`aes_event.derived` keeps a run's LEDGER, not its sixteen-megabyte image, and answers the image as the machine
    with the ledger laid in it (and the return address the oracle plants for a run, which is in no ledger): byte
    for byte the image the run itself left — the first time (made) and the second (served)."""
    entry, machine = addrs.AES_ROM_CHKKBD, aes_event.machine()
    left, _writes, _regs = aes_event._rom_run(make_image(merge_pokes(aes.leaf_machine(), machine)), entry,
                                              stop_pc=addrs.AES_ROM_DSPTCH)
    for _made_then_served in range(2):
        written, final, _registers = aes_event.derived(entry, machine)
        assert bytes(final) == bytes(left) and written == case.written_by(_writes)


def test_a_run_whose_image_is_not_its_ledger_s_is_refused_and_nothing_kept(monkeypatch):
    """...and the premise is HELD AT THE RUN, for every run kept: an image holding a byte no ledger entry stored (a
    store the oracle made and did not report) is not answered by the ledger — refused by name, where it would have
    been kept and served as the machine with that byte missing."""
    rom_run, machine = aes_event._rom_run, aes_event.machine()      # the machine made first: by the ROM's runs as they are
    ring = range(aes.AES_FORK_QUEUE, aes.AES_FORK_QUEUE + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES)

    def storing_off_its_ledger(*run, **named):
        final, writes, regs = rom_run(*run, **named)
        untold = next(at for at in ring if at not in writes)        # chkkbd queues one entry at most: the rest untouched
        final[untold] ^= 0xFF
        return final, writes, regs
    monkeypatch.setattr(aes_event, "_rom_run", storing_off_its_ledger)
    with pytest.raises(AssertionError, match="left an image that is not its machine with its write ledger laid in it"):
        aes_event.derived(addrs.AES_ROM_CHKKBD, machine)


def _held(image):
    """The buttons the VDI's mouse interrupt last recorded down (CUR_MS_STAT)."""
    return image[vdi.LINEA_CUR_MS_STAT] & aes_event.MOUSE_STAT_BUTTONS_MASK


# What each action IS, over the snapshot's machine (no button down, no click count open): the button changes it queues
# for forker — each the buttons then down and the clicks counted — and the buttons left down.
ACTIONS = {
    "a press": (aes_event.PRESSING, [aes_event.button_change(LEFT, ONE_CLICK)], LEFT),
    "a click": (aes_event.CLICKING, [aes_event.button_change(LEFT, ONE_CLICK), aes_event.button_change(UP, ONE_CLICK)], UP),
    "a double click": (aes_event.DOUBLE_CLICKING, [aes_event.button_change(LEFT, TWO_CLICKS)], LEFT),
    "a right press": (aes_event.RIGHT_PRESSING, [aes_event.button_change(RIGHT, ONE_CLICK)], RIGHT),
    "a press, then its release": (aes_event.in_turn(aes_event.PRESSING, aes_event.RELEASING),
                                  [aes_event.button_change(LEFT, ONE_CLICK), aes_event.button_change(UP, ONE_CLICK)], UP),
}


@pytest.mark.parametrize("sequence, queued, held", ACTIONS.values(), ids=ACTIONS)
def test_each_of_a_user_s_actions_is_what_the_rom_s_interrupts_make_of_it(sequence, queued, held):
    """A sequence of the vocabulary taken over the snapshot (`taken_in_place`: the VDI's mouse interrupt per packet,
    the AES's tick glue per tick): the click count it opened has RUN OUT, the changes it made are queued for forker in
    order — the buttons down and the clicks b_click counted — and the VDI holds the buttons it left down."""
    image = make_image({})
    assert not aes_event.fork_queue(image) and _held(image) == UP, "the premise: the snapshot's machine is idle"
    wrote = aes_event.taken_in_place(image, sequence)
    assert wrote and case.word_in(image, aes.AES_GL_CLICK_TICKS) == 0
    assert aes_event.fork_queue(image) == queued and _held(image) == held


def test_a_move_keeps_the_buttons_as_they_are_held_and_queues_no_button_change():
    """`moving_by` / `moving_to`: every packet the IKBD sends carries the buttons, so a packet that only MOVES carries
    the ones held — a move with the button down leaves it down, and queues the move alone."""
    image = make_image({})
    aes_event.taken_in_place(image, aes_event.PRESSING)
    before = aes_event.fork_queue(image)
    aes_event.taken_in_place(image, aes_event.in_turn(aes_event.moving_by((5, 0)), aes_event.moving_to(200, 120)))
    after = aes_event.fork_queue(image)
    assert _held(image) == LEFT and aes_event._cursor(image) == (200, 120)
    assert after[:len(before)] == before and len(after) > len(before)
    assert {function for function, _data in after[len(before):]} == {addrs.AES_ROM_MCHANGE}, "a move queued a button change"


def test_ticks_are_counted_one_interrupt_each():
    """`ticking(n)` is n runs of the tick glue; `click_counted`, as many as the open count holds — none where none is
    open."""
    assert list(aes_event.ticking(3)(lambda: None)) == [aes_event.TICK] * 3
    idle = make_image({})
    assert list(aes_event.click_counted(lambda: idle)) == []
    aes_event.taken_in_place(idle, aes_event.packets(aes_event.LEFT_DOWN_PACKET))
    opened = case.word_in(idle, aes.AES_GL_CLICK_TICKS)
    assert opened > 1, "the premise: a press opens a click count of several ticks"
    counting = aes_event.click_counted(lambda: idle)
    assert [next(counting) for _tick in range(opened)] == [aes_event.TICK] * opened
    with pytest.raises(AssertionError, match="the ticks did not resolve the click"):
        next(counting)                  # ...the ticks were handed out and none was TAKEN: the count is still open


# ---- a priced row's words, settled (`aes_event.settled_where_stored`) -------------------------------------------------
MASK_WORD, SPL = aes.AES_LINEF_MASK_WORD, aes.AES_SR_SPL
A_MACHINE = {0x7000: b"\x01\x02"}


def _stored(*words):
    """A write ledger that holds a word at each of `words`: `{address: byte}`."""
    return {word + offset: value for word in words for offset, value in ((0, 0x27), (1, 0x00))}


def test_a_word_is_staged_and_dropped_only_where_the_rom_s_run_stored_it():
    """`settled_where_stored`: each word the run STORED is staged at the value the run left and its named drop added,
    in the order the words are given; a word the run left alone is neither — the row's Tier 3 compare holds it."""
    words = aes_event.MASK_WORD_AND_SPL
    assert [word for word, _drop in words] == [MASK_WORD, SPL]
    mask_drop, spl_drop = (tuple(drop) for _word, drop in words)
    assert aes_event.settled_where_stored(A_MACHINE, _stored(), words) == (A_MACHINE, ())
    pokes, drops = aes_event.settled_where_stored(A_MACHINE, _stored(SPL), words)
    assert pokes == {**A_MACHINE, SPL: b"\x27\x00"} and drops == spl_drop
    pokes, drops = aes_event.settled_where_stored(A_MACHINE, _stored(SPL, MASK_WORD), words)
    assert pokes == case.merge_pokes(A_MACHINE, {MASK_WORD: b"\x27\x00", SPL: b"\x27\x00"}) and drops == mask_drop + spl_drop
    assert aes_event.settled_where_stored(A_MACHINE, _stored(MASK_WORD), words[1:]) == (A_MACHINE, ())


@pytest.mark.parametrize("word, half", [(SPL, 0), (SPL, 1), (MASK_WORD, 0), (MASK_WORD, 1)],
                         ids=["the SR word's high byte", "its low byte", "the mask word's high byte", "its low byte"])
def test_a_run_that_stored_half_of_a_word_that_differs_by_nature_is_refused(word, half):
    """RED before the settling was word-granular again (one settling for words and windows made it byte by byte: a
    lone byte stored into such a word — no `move.w sr`, no mask store: another variable's byte, a wild pointer — was
    STAGED at the value the run left and DROPPED under the word's own reason, and its companion could not see a C
    that never stored it): refused by name, for somebody to rule on; the whole word beside it settles as ever."""
    with pytest.raises(AssertionError, match=f"stored HALF of the word at {word:#x} that differs by nature"):
        aes_event.settled_where_stored(A_MACHINE, {word + half: 0x04}, aes_event.MASK_WORD_AND_SPL)
    with pytest.raises(AssertionError, match="stored HALF of the word"):
        aes_event.settled_where_stored(A_MACHINE, {**_stored(SPL), MASK_WORD + half: 0x04}, aes_event.WORDS_BY_NATURE)
    assert aes_event.settled_where_stored(A_MACHINE, _stored(word), aes_event.MASK_WORD_AND_SPL)[1]


A_WINDOW = (0x8000, 0x8010, "a window that differs by nature")
ANOTHER = (0x8020, 0x8024, "another")


def test_a_window_is_staged_and_dropped_byte_by_byte_where_the_run_stored_it():
    """`settled_in_windows`, the one settling the words' is a case of: every byte of a staged window the run STORED is
    staged at the value it left — two runs of a window, cut apart by a byte the run left alone — and the drops are
    the windows cut to those same runs, in the windows' order; a window may be staged and NOT dropped (a build
    that stores it as the ROM does stays compared there)."""
    stored = {0x8001: 0x11, 0x8002: 0x22, 0x8004: 0x44, 0x8021: 0xAA, 0x9000: 0xEE}
    pokes, drops = aes_event.settled_in_windows(A_MACHINE, stored, (A_WINDOW, ANOTHER))
    assert pokes == {**A_MACHINE, 0x8001: b"\x11\x22", 0x8004: b"\x44", 0x8021: b"\xaa"}, "nothing outside a window"
    assert drops == ((0x8001, 0x8003, A_WINDOW[2]), (0x8004, 0x8005, A_WINDOW[2]), (0x8021, 0x8022, ANOTHER[2]))
    same_pokes, fewer = aes_event.settled_in_windows(A_MACHINE, stored, (A_WINDOW, ANOTHER), dropped=(ANOTHER,))
    assert same_pokes == pokes and fewer == drops[2:]
    assert aes_event.settled_in_windows(A_MACHINE, {0x9000: 0xEE}, (A_WINDOW,)) == (A_MACHINE, ())
    whole = dict.fromkeys(range(A_WINDOW[0], A_WINDOW[1]), 0x5A)
    assert aes_event.settled_in_windows({}, whole, (A_WINDOW,))[1] == (A_WINDOW,), "a window stored whole is its own drop"


# ---- THE DERIVATION EVERY ROW THAT SWITCHES IS REGISTERED THROUGH (`aes_switch.scheduled`) ---------------------------------
# gr_stilldn waiting, the button down, for the mouse to leave the rectangle it is in — by its ROM entry and frame, no
# battery imported: its one wait is door call 0 of the run.
A_RECTANGLE_ROUND_THE_SNAPSHOT_S_MOUSE = (140, 80, 40, 40)
WAITING_TO_LEAVE = 1


def test_a_scheduled_run_keeps_what_it_took_at_a_door_call_apart_from_what_it_took_at_an_idle():
    """THE ONE DERIVATION THAT TAKES INTERRUPTS AT DOOR CALLS AND AT IDLES books each where it was taken: the rise
    delivered AT THE WAIT'S ENTRY (door call 0) is answered at once — no idle is made, nothing is delivered at one —
    and the same rise delivered AT THE IDLE is no door call's. A registrar that read one as the other would lay an
    idle's interrupt at a door call of every row's replay (and every battery's import would fail on it)."""
    import aes_switch
    frame = aes_event.frame_of(("w", WAITING_TO_LEAVE), *(("w", word) for word in A_RECTANGLE_ROUND_THE_SNAPSHOT_S_MOUSE))
    machine = merge_pokes(aes_event.machine(aes_event.button_down), aes_event.savptr_in_the_band())
    at_the_wait = aes_switch.scheduled(addrs.AES_ROM_GR_STILLDN, frame, machine, at_calls={0: aes_event.release})
    assert (sorted(at_the_wait.at_calls), at_the_wait.delivered, at_the_wait.idles, len(at_the_wait.calls)) == ([0], {}, 0, 1)
    at_the_idle = aes_switch.scheduled(addrs.AES_ROM_GR_STILLDN, frame, machine, {0: aes_event.release})
    assert (at_the_idle.at_calls, sorted(at_the_idle.delivered), at_the_idle.idles, len(at_the_idle.calls)) == ({}, [0], 1, 1)
    assert at_the_wait.ended == at_the_idle.ended == aes_switch.RETURNED and at_the_wait.d0 == at_the_idle.d0
