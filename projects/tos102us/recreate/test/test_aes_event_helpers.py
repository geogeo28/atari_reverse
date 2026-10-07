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
