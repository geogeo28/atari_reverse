"""THE FORK QUEUE and what runs off it (`src/aes/evfork.c`): gemdisp's forkq, forker and chkkbd, geminput's four fork
functions and the cursor call.

    forkq(code, data)      {code, data} at the queue's tail (round the ring of 32), counted, the posted flag set — or,
                           with 32 queued, NOTHING: the entry is dropped
    forker()               rlr := -1; each entry counted out, recorded while appl_trecord runs, CALLED; rlr back
    chkkbd()               VDI 128 (the shift keys); while the keyboard's owner's queue has room VDI 33 + 31 (one key,
                           sampled); a key or changed shift keys → forkq(kchange, key << 16 | shift)
    kchange(key, shift)    kstate := shift; a key → post_keybd(gl_kowner, key)
    bchange(new, clicks)   a first press while the mouse is not the screen manager's re-decides its owner (mowner);
                           the click record; post_button(gl_mowner, new, clicks)
    mchange(x, y)          VDI 124: where the mouse IS; a move past the slop ends an open click count; no button down
                           and a menu bar: crossing the screen manager's rectangle hands it the mouse; post_mouse
    tchange(elapsed)       the delay list counted down, each delay run out completed; the tick re-armed
    drawrat(x, y)          `jsr (*$947a)`, D0 / D1 the point

EVERY MACHINE IS THE ROM'S OWN (`aes_evinput`: arrivals) — THE FORK QUEUE FILLED BY THE ROM'S OWN INTERRUPTS (the
VDI's mouse interrupt through the AES's button and motion glue, the tick glue) and by its own keyboard poll, never
poked — but for the cases SAID to hand an argument no caller does, and those SAID to stand over a STAGED FIELD, six:
forkq's count below 0 and its tail past 31 (two), mchange's `$96d8` at 1 (two), and a cursor routine of the case's
own in `$947a` (two: a poked field and its code). A recording PLAYED BACK is the ROM's own: the desk's appl_tplay.

WHAT forker CALLS: each entry's code is the fork function's ROM address (what the ROM's interrupts queued); the
case's binding of the register-carrying hook serves it by the candidate's own core over the entry's data
(`aes_evinput.HANDED_ROUTINES`), so a forker case runs kchange / bchange / mchange / tchange and everything under
them in C — the whole event of an idle, against the ROM's.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evinput as evinput
import case
import vdi
from aes_evinput import (BCHANGE, CHKKBD, DRAWRAT, FORKER, FORKQ, KCHANGE, MCHANGE, SCREEN_MANAGER, SHELL, TCHANGE)
from case import merge_pokes

pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)
ROUTINES = (FORKQ, FORKER, CHKKBD, KCHANGE, BCHANGE, MCHANGE, TCHANGE, DRAWRAT)
EVI, EVF, FM = evinput.EVI, evinput.EVF, evinput.FM
GSX, GSXIF, WU = (aes.header_constants(name) for name in ("gsx.h", "gsxif.h", "wmupdate.h"))
XRAT, YRAT, BUTTON, KSTATE = GSX["AES_XRAT"], GSX["AES_YRAT"], GSX["AES_BUTTON"], GSXIF["AES_KSTATE"]
GL_MOWNER, GL_COWNER, GL_KOWNER = WU["AES_GL_MOWNER"], EVI["AES_GL_COWNER"], WU["AES_GL_KOWNER"]
CLICK_TICKS = aes.AES_GL_CLICK_TICKS
ENTRIES, ENTRY_BYTES = aes.AES_FORK_ENTRIES, aes.FORK_ENTRY_BYTES
LEFT, RIGHT = 1, 2
A_BUTTON_WORD_WITH_ITS_LOW_BYTE_1 = 0x0101
RETURN_KEY_CODE = evinput.RETURN_KEY_CODE
LEFT_SHIFT, CONTROL = 2, 4              # the BIOS's kbshift bits for the left shift key and Control
KEY, PRESS, CLICK = "a key wakes the desk", "a press wakes the desk", "a click wakes the desk"
BAR = evasync.THE_BAR_WAKES_THE_MANAGER
TYPED_AHEAD, TEN_KEYS = "a key typed ahead of a wait for a press", "ten keys nobody reads"
OVERFLOW, RING = "more moves than the fork queue holds", "the fork queue's ring wraps"
TIMER = "a timer runs out"
MERGED = "a recording: two ticks merged, then a move"
END_KEY = "a recording ended by Control-backslash"
RAN_OUT = "a recording of one event runs out"
PLAYED = "the desk plays a move back"
PLAYED_LEFT = "a move played left of the screen, then a press and a move"
PLAYED_BUTTONS = "a button word above its byte played, then a press on the bar's right"
BAR_CLICK = "a click on the bar while the screen manager waits for a key"
FIRST_OF_TWO = f"{evinput.STAGED_APPLICATION}: the first of two delays runs out"
BOTH_OF_TWO = f"{evinput.STAGED_APPLICATION}: two delays run out together"
fork_queue, waits, button_change = evinput.fork_queue, evinput.waits, evinput.button_change


run = evinput.run


before = aes_event.before


def indices(image):
    return {"head": case.word_in(image, aes.AES_FORK_HEAD), "tail": case.word_in(image, aes.AES_FORK_TAIL),
            "count": case.word_in(image, aes.AES_FORK_COUNT)}


def mouse(image):
    return aes.signed(case.word_in(image, XRAT)), aes.signed(case.word_in(image, YRAT))


# ---- every arrival ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arrival", evinput.cases(*ROUTINES), ids=evinput.case_id)
def test_every_arrival(arrival):
    run(evinput.arrival(*arrival))


THROUGH_LINE_F = {FORKQ: (KEY, 0), FORKER: (KEY, 1), CHKKBD: (KEY, 0), DRAWRAT: None}


@pytest.mark.parametrize("routine", (FORKQ, FORKER, CHKKBD), ids=evinput.short)
def test_each_routine_through_its_call_word(routine):
    scenario, which = THROUGH_LINE_F[routine]
    run(evinput.at(scenario, routine, which), through_line_f=True)


@pytest.mark.parametrize("routine", evinput.FORK_FUNCTIONS, ids=evinput.short)
def test_a_fork_function_has_no_call_word(routine):
    """Entered by forker's `jsr (a0)` alone — its address a queue entry's code, never a Line-F word."""
    assert not aes.line_f_call_sites(routine)


# ---- forkq -----------------------------------------------------------------------------------------------------------------
def test_forkq_puts_the_entry_at_the_tail_and_counts_it():
    arrival = evinput.at(KEY, FORKQ)
    code, data = arrival.arguments
    assert indices(before(arrival)) == {"head": 0, "tail": 0, "count": 0} and not before(arrival)[aes.AES_FORK_POSTED]
    result = run(arrival)
    assert (code, data) == (addrs.AES_ROM_KCHANGE, aes.words_long(RETURN_KEY_CODE))
    assert fork_queue(result.final) == [(code, data)] and indices(result.final) == {"head": 0, "tail": 1, "count": 1}
    assert result.final[aes.AES_FORK_POSTED] == 1


def test_forkq_s_tail_goes_round_the_ring():
    """The thirty-second entry since the boot, queued behind a head already at 20: stored in the last slot, the tail
    back at 0."""
    arrival = evinput.at(RING, FORKQ, ENTRIES - 1)
    assert indices(before(arrival)) == {"head": evinput.RING_HALF, "tail": ENTRIES - 1, "count": ENTRIES - 1 - evinput.RING_HALF}
    result = run(arrival)
    assert indices(result.final) == {"head": evinput.RING_HALF, "tail": 0, "count": ENTRIES - evinput.RING_HALF}
    last = aes.AES_FORK_QUEUE + (ENTRIES - 1) * ENTRY_BYTES
    assert (result.long(last + aes.FORK_CODE), result.long(last + aes.FORK_DATA)) == arrival.arguments


def test_forkq_fills_the_thirty_second_entry():
    arrival = evinput.at(OVERFLOW, FORKQ, ENTRIES - 1)
    result = run(arrival)
    assert indices(result.final) == {"head": 0, "tail": 0, "count": ENTRIES} and len(fork_queue(result.final)) == ENTRIES


@pytest.mark.parametrize("which", (ENTRIES, ENTRIES + 1), ids=("the 33rd", "the 34th"))
def test_forkq_drops_an_entry_for_a_full_queue(which):
    """THE FINDING, CONFIRMED: thirty-two moves queued and nothing run — the next is DROPPED: no store at all (not
    the posted flag, which is set already), its caller not told. A mouse move lost is the least of it: the same
    queue carries the button changes and the timer."""
    arrival = evinput.at(OVERFLOW, FORKQ, which)
    assert indices(before(arrival))["count"] == ENTRIES
    result = run(arrival)
    assert aes.stored_nothing(result) and arrival.arguments not in fork_queue(result.final)


@pytest.mark.parametrize("field, value, entry, after", (
    (aes.AES_FORK_COUNT, -1, 0, {"head": 0, "tail": 1, "count": 0}),
    (aes.AES_FORK_TAIL, 0x1000, -0x8000 // ENTRY_BYTES, {"head": 0, "tail": 0x1001, "count": 1})),
    ids=("a negative count is not full", "the tail's index is a word shifted, then extended"))
def test_forkq_reads_its_count_and_tail_as_signed_words(field, value, entry, after):
    """TWO CASES OVER A STAGED FIELD, labelled: no ROM-made machine holds a fork count below 0 or a tail past 31 (the
    ring wraps both), so the widths forkq reads them at are staged — the count compared SIGNED (`bge`), the tail
    shifted as a WORD and then sign-extended (`asl.w #3 / ext.l`: 4,096 entries on is 32 KB BELOW the queue)."""
    arrival = evinput.at(KEY, FORKQ)
    staged = merge_pokes(arrival.machine, {field: struct.pack(">h", value)})
    result = evinput.run_over(FORKQ, arrival.arguments, staged)
    at = aes.AES_FORK_QUEUE + entry * ENTRY_BYTES
    assert (result.long(at + aes.FORK_CODE), result.long(at + aes.FORK_DATA)) == arrival.arguments
    assert indices(result.final) == {name: value_ & aes.WORD_MASK for name, value_ in after.items()}


def test_forkq_stores_its_code_and_data_whole():
    """AN ARGUMENT-CLASS CASE (a code and a data no caller hands: every bit set differently): two longwords."""
    arrival = evinput.at(KEY, FORKQ)
    result = run(arrival, (0x89ABCDEF, 0xFEDCBA98))
    assert fork_queue(result.final) == [(0x89ABCDEF, 0xFEDCBA98)]


# ---- forker ----------------------------------------------------------------------------------------------------------------
def test_forker_with_nothing_queued():
    arrival = evinput.at(KEY, FORKER, 0)
    result = run(arrival)
    assert not fork_queue(before(arrival)) and evasync.running(result.final) == evasync.running(before(arrival))
    assert result.final[aes.AES_FORKER_BUSY] == 0


def test_forker_runs_a_key_to_the_desk_s_wait():
    """The whole event, in C against the ROM: kchange → post_keybd → evremove → azombie → signal: the desk woken."""
    arrival = evinput.at(KEY, FORKER, 1)
    assert fork_queue(before(arrival)) == [(addrs.AES_ROM_KCHANGE, aes.words_long(RETURN_KEY_CODE))]
    result = run(arrival)
    assert not fork_queue(result.final) and indices(result.final) == {"head": 1, "tail": 1, "count": 0}
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL] and evasync.running(result.final) == evasync.running(before(arrival))


def test_forker_runs_an_entry_a_fork_function_queues():
    """A move inside a click's count: mchange ends the count, b_delay QUEUES the press — behind the move, in the run
    that is taking the move off: forker serves it before it returns."""
    arrival = evinput.at("a move right ends a click's count", FORKER)
    assert [code for code, _data in fork_queue(before(arrival))] == [addrs.AES_ROM_MCHANGE]
    result = run(arrival)
    assert not fork_queue(result.final) and indices(result.final)["head"] == 2
    assert case.word_in(result.final, BUTTON) == LEFT and aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_forker_runs_a_full_queue_dry():
    arrival = evinput.at(OVERFLOW, FORKER)
    assert len(fork_queue(before(arrival))) == ENTRIES
    result = run(arrival)
    assert indices(result.final) == {"head": 0, "tail": 0, "count": 0}, "the head round the ring, to where it began"


def test_forker_runs_with_no_process_running():
    """`rlr` is -1 while the fork functions run (what signal's "not the running process" test then finds), and put
    back after: held on a case whose fork function reads it — a process woken."""
    arrival = evinput.at(PRESS, FORKER)
    was = evasync.running(before(arrival))
    result = run(arrival)
    assert was == 0 and evasync.running(result.final) == 0 and aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_forker_calls_a_fork_function_with_no_process_running_and_its_busy_byte_set():
    """WHAT IS GONE AT forker's RETURN, held where it is: as the fork function is ENTERED. The ROM's own memory there
    is the arrival at kchange inside this very run (`rlr` -1, the busy byte 1); the C's is its image at the hook's
    call."""
    arrival, inside = evinput.at(KEY, FORKER, 1), before(evinput.at(KEY, KCHANGE))
    held = []

    def watching(name):
        function = evinput._fork_function(name)

        def effect(buf, registers):
            held.append((bytes(buf[aes.AES_RLR:aes.AES_RLR + aes.LONG_BYTES]), buf[aes.AES_FORKER_BUSY]))
            function(buf, registers)
        return effect
    handed = {**evinput.HANDED_ROUTINES, **{getattr(addrs, name): (b"", watching(name)) for name in evinput.FORK_FUNCTIONS}}
    run(arrival, hook=aes.doors(evinput.vdi_hook, aes.alcyon_object_hook(handed)))
    the_rom_s = (bytes(inside[aes.AES_RLR:aes.AES_RLR + aes.LONG_BYTES]), inside[aes.AES_FORKER_BUSY])
    assert the_rom_s == (aes.AES_RLR_IN_FORKER.to_bytes(aes.LONG_BYTES, "big"), 1), "the premise: the ROM's, inside"
    assert held and set(held) == {the_rom_s}


def test_forker_counts_an_entry_out_before_it_runs_it():
    """A press, then as many moves as the queue holds, while a recording runs: the first move's mchange ends the
    click's count and b_delay QUEUES the press — which fits only because forker counted the move out BEFORE calling
    it — at the tail, the very slot of the entry being run. The entry was recorded before the call: the record holds
    the move, not the press that overwrote it."""
    arrival = evinput.at("a recording: a press, then as many moves as the queue holds", FORKER)
    full = fork_queue(before(arrival))
    assert len(full) == ENTRIES and {code for code, _data in full} == {addrs.AES_ROM_MCHANGE}
    result = run(arrival)
    assert record(result.final, 1) == [full[0]]
    assert case.word_in(result.final, BUTTON) == LEFT, "the press was queued behind the moves, and run"
    was = indices(before(arrival))
    assert was["head"] == was["tail"], "the premise: full — the tail is the slot of the entry forker takes first"
    once_round = (was["head"] + ENTRIES + 1) % ENTRIES
    assert indices(result.final) == {"head": once_round, "tail": once_round, "count": 0}


def test_forker_records_a_key_that_is_not_control_backslash():
    arrival = evinput.at("a recording: a key", FORKER, 1)
    result = run(arrival)
    assert record(result.final, 1) == [(addrs.AES_ROM_KCHANGE, aes.words_long(RETURN_KEY_CODE))]
    assert recorder(result.final) == {"on": 2, "left": 2, "cursor": evinput.RECORD_AT + ENTRY_BYTES}


def record(image, events):
    """The first `events` records of appl_trecord's buffer: `(code, data)` each."""
    return [(case.long_in(image, evinput.RECORD_AT + index * ENTRY_BYTES), case.long_in(image, evinput.RECORD_AT + index * ENTRY_BYTES + 4))
            for index in range(events)]


def recorder(image):
    return {"on": case.word_in(image, aes.AES_GL_RECD), "left": case.word_in(image, aes.AES_RECORD_LEFT),
            "cursor": case.long_in(image, aes.AES_RECORD_CURSOR)}


def test_forker_records_the_entry_it_runs():
    """appl_trecord of three events, the first tick: the entry copied to the buffer, the cursor on, one fewer left."""
    arrival = evinput.at(MERGED, FORKER, 0)
    assert recorder(before(arrival)) == {"on": 1, "left": 3, "cursor": evinput.RECORD_AT}
    result = run(arrival)
    assert record(result.final, 1) == [(addrs.AES_ROM_TCHANGE, evasync.A_TIMER_TICKS)]
    assert recorder(result.final) == {"on": 2, "left": 2, "cursor": evinput.RECORD_AT + ENTRY_BYTES}


def test_forker_adds_a_tick_to_the_tick_recorded_before_it():
    arrival = evinput.at(MERGED, FORKER, 2)
    assert fork_queue(before(arrival)) == [(addrs.AES_ROM_TCHANGE, evasync.A_TIMER_TICKS)]
    result = run(arrival)
    assert record(result.final, 1) == [(addrs.AES_ROM_TCHANGE, 2 * evasync.A_TIMER_TICKS)]
    assert recorder(result.final) == recorder(before(arrival)), "nothing counted: the two ticks are one record"


def test_forker_records_a_move_after_the_ticks():
    arrival = evinput.at(MERGED, FORKER, 4)
    result = run(arrival)
    assert [code for code, _data in record(result.final, 2)] == [addrs.AES_ROM_TCHANGE, addrs.AES_ROM_MCHANGE]
    assert recorder(result.final)["left"] == 1


def test_forker_stops_recording_at_control_backslash_and_does_not_record_it():
    arrival = evinput.at(END_KEY, FORKER, 1)
    (code, data), = fork_queue(before(arrival))
    assert code == addrs.AES_ROM_KCHANGE and aes.high_word(data) == EVF["RECORD_END_KEY"]
    result = run(arrival)
    assert recorder(result.final)["on"] == 0 and recorder(result.final)["left"] == recorder(before(arrival))["left"]
    assert record(result.final, 2)[1] == record(before(arrival), 2)[1], "the key is not in the record"
    assert evinput.at(END_KEY, evinput.NQ).arguments[0] == EVF["RECORD_END_KEY"], "...and still reaches the keyboard's owner"


def test_forker_stops_recording_when_the_records_run_out():
    arrival = evinput.at(RAN_OUT, FORKER)
    assert recorder(before(arrival)) == {"on": 1, "left": 1, "cursor": evinput.RECORD_AT}
    result = run(arrival)
    assert recorder(result.final) == {"on": 0, "left": 0, "cursor": evinput.RECORD_AT + ENTRY_BYTES}


# ---- chkkbd ----------------------------------------------------------------------------------------------------------------
def test_chkkbd_with_no_key_and_the_shift_keys_as_they_were_queues_nothing():
    arrival = evinput.at(KEY, CHKKBD, 1)
    result = run(arrival)
    assert not fork_queue(result.final)


def test_chkkbd_queues_a_key():
    arrival = evinput.at(KEY, CHKKBD, 0)
    result = run(arrival)
    assert fork_queue(result.final) == [(addrs.AES_ROM_KCHANGE, aes.words_long(RETURN_KEY_CODE))]


def test_chkkbd_queues_the_shift_keys_changed_with_no_key():
    arrival = evinput.at("the shift key alone", CHKKBD, 0)
    result = run(arrival)
    assert case.word_in(before(arrival), KSTATE) == 0
    assert fork_queue(result.final) == [(addrs.AES_ROM_KCHANGE, LEFT_SHIFT)]


def test_chkkbd_queues_a_key_with_the_shift_keys_held():
    """Control-backslash: the key's word high, the shift keys (Control) low."""
    (code, data), = fork_queue(run(evinput.at(END_KEY, CHKKBD, 0)).final)
    assert (code, aes.high_word(data), data & aes.WORD_MASK) == (addrs.AES_ROM_KCHANGE, EVF["RECORD_END_KEY"], CONTROL)


def test_chkkbd_polls_no_key_for_an_owner_whose_queue_is_full():
    """Ten keys typed and nobody reading: after eight the desk's queue is full and chkkbd no longer samples the
    keyboard — the ninth key stays in the BIOS's buffer, nothing queued."""
    arrival = evinput.at(TEN_KEYS, CHKKBD, FM["CQUEUE_ENTRIES"] + 1)
    image = before(arrival)
    waiting = (case.word_in(image, addrs.IOREC_IKBD + addrs.IOREC_HEAD), case.word_in(image, addrs.IOREC_IKBD + addrs.IOREC_TAIL))
    result = run(arrival)
    assert waiting[0] != waiting[1], "the premise: keys still in the keyboard's buffer"
    assert not fork_queue(result.final)
    assert case.word_in(result.final, addrs.IOREC_IKBD + addrs.IOREC_HEAD) == waiting[0], "none taken"


def test_chkkbd_polls_the_eighth_key_for_a_queue_of_seven():
    arrival = evinput.at(TEN_KEYS, CHKKBD, FM["CQUEUE_ENTRIES"] - 1)
    assert case.word_in(before(arrival), case.long_in(before(arrival), SHELL + aes.PD_CDA) + aes.CDA_KEY_COUNT) == 7
    assert fork_queue(run(arrival).final) == [(addrs.AES_ROM_KCHANGE, aes.words_long(RETURN_KEY_CODE))]


def test_chkkbd_looks_at_the_keyboard_owner_s_queue_not_the_running_process_s():
    """The SCREEN MANAGER running, about to wait; the keyboard is the desk's, whose queue is full, and keys are still
    in the BIOS's buffer: no key is polled — the screen manager's own queue is empty, and is not asked."""
    arrival = evinput.at("the screen manager waits while the desk's key queue is full", CHKKBD, -1)
    image = before(arrival)
    counts = [case.word_in(image, case.long_in(image, pd + aes.PD_CDA) + aes.CDA_KEY_COUNT) for pd in (SHELL, SCREEN_MANAGER)]
    assert evasync.running(image) == SCREEN_MANAGER and case.long_in(image, GL_KOWNER) == SHELL and counts == [8, 0]
    assert not fork_queue(run(arrival).final)


# ---- kchange ---------------------------------------------------------------------------------------------------------------
def test_kchange_posts_the_key_and_notes_the_shift_keys():
    arrival = evinput.at(END_KEY, KCHANGE)
    result = run(arrival)
    assert result.word(KSTATE) == CONTROL and evinput.fork_queue(result.final) == []
    assert evinput.at(END_KEY, evinput.POST_KEYBD).arguments == (SHELL, EVF["RECORD_END_KEY"])


def test_kchange_with_no_key_notes_the_shift_keys_alone():
    arrival = evinput.at("the shift key alone", KCHANGE)
    result = run(arrival)
    assert arrival.arguments == (0, LEFT_SHIFT) and result.word(KSTATE) == LEFT_SHIFT
    assert not evasync.completed(result.final), "the desk's keyboard wait is not posted a key of 0"


def test_kchange_posts_to_the_keyboard_s_owner_while_the_mouse_is_another_s():
    """The mouse onto the bar and a key, in one idle: the mouse is the screen manager's by the time the key is run —
    the key still goes to the desk, the keyboard's owner."""
    arrival = evinput.at("the mouse onto the bar and a key in one idle", KCHANGE)
    image = before(arrival)
    waiting, = waits(image, SHELL, aes.CDA_KEYBOARD_WAIT)
    assert (case.long_in(image, GL_MOWNER), case.long_in(image, GL_KOWNER)) == (SCREEN_MANAGER, SHELL)
    assert waiting in evasync.completed(run(arrival).final)


def test_kchange_posts_to_the_keyboard_s_owner():
    arrival = evinput.at(KEY, KCHANGE)
    waiting, = waits(before(arrival), SHELL, aes.CDA_KEYBOARD_WAIT)
    result = run(arrival)
    assert case.long_in(before(arrival), GL_KOWNER) == SHELL and evasync.completed(result.final) == [waiting]


# ---- bchange ---------------------------------------------------------------------------------------------------------------
def click_record(image):
    return {"changes": case.word_in(image, aes.AES_MTRANS), "buttons before": case.word_in(image, aes.AES_PR_BUTTON),
            "clicks before": case.word_in(image, aes.AES_PR_MCLICK),
            "mouse before": (case.word_in(image, aes.AES_PR_XRAT), case.word_in(image, aes.AES_PR_YRAT)),
            "buttons": case.word_in(image, BUTTON), "clicks": case.word_in(image, aes.AES_MCLICK)}


def owner_after(scenario, which=0):
    arrival = evinput.at(scenario, BCHANGE, which)
    return case.long_in(before(arrival), GL_MOWNER), run(arrival).long(GL_MOWNER)


def test_bchange_keeps_the_click_record_and_posts_the_press():
    arrival = evinput.at(PRESS, BCHANGE)
    was = click_record(before(arrival))
    result = run(arrival)
    assert click_record(result.final) == {"changes": was["changes"] + 1, "buttons before": 0, "clicks before": was["clicks"],
                                          "mouse before": mouse(before(arrival)), "buttons": LEFT, "clicks": 1}
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_bchange_of_a_double_click_records_its_clicks():
    arrival = evinput.at("a double click wakes the desk", BCHANGE)
    assert click_record(run(arrival).final)["clicks"] == 2


def test_bchange_of_a_release_records_the_press_before_it():
    arrival = evinput.at(CLICK, BCHANGE, 1)
    result = run(arrival)
    record_ = click_record(result.final)
    assert (record_["buttons before"], record_["buttons"]) == (LEFT, 0)


@pytest.mark.parametrize("scenario, owner", (
    (PRESS, SHELL), ("a press on the desktop beside a window", SHELL), ("a press on a window's title", SCREEN_MANAGER),
    ("a press on the bar's right", SCREEN_MANAGER)),
    ids=("the control rectangle: its owner", "the desktop: window 0's owner", "a window: the screen manager",
         "the menu bar: the screen manager"))
def test_bchange_s_first_press_decides_whose_the_mouse_is(scenario, owner):
    _was, now = owner_after(scenario)
    assert now == owner


def test_bchange_gives_the_mouse_to_the_desk_in_the_control_rectangle_with_the_screen_owned():
    """A press in the control rectangle with the screen owned: the mouse is the desk's. NOT HELD: that it is set from
    gl_cowner rather than from window 0's owner (the desktop arm's source) — in every machine both are the desk, as
    in the desktop arm's own case: telling them apart needs a third process owning the screen (band 5)."""
    arrival = evinput.at("a press inside the control rectangle", BCHANGE)
    assert case.long_in(before(arrival), GL_COWNER) == case.long_in(before(arrival), aes.AES_WINDOWS + aes.WIN_OWNER) == SHELL
    assert run(arrival).long(GL_MOWNER) == SHELL


def test_bchange_compares_the_new_buttons_as_a_word():
    """AN ARGUMENT-CLASS CASE (a button word no interrupt hands: $0101) on a window's title, where a first press
    hands the mouse to the screen manager: the WORD is not 1 — nothing is re-decided."""
    arrival = evinput.at("a press on a window's title", BCHANGE)
    assert arrival.arguments == (EVF["BCHANGE_FIRST_PRESS"], 1) and owner_after("a press on a window's title")[1] == SCREEN_MANAGER
    assert run(arrival, (A_BUTTON_WORD_WITH_ITS_LOW_BYTE_1, 1)).long(GL_MOWNER) == SHELL


def test_bchange_reads_the_buttons_down_as_a_word():
    """A button word of $0100 PLAYED BACK (the desk's appl_tplay: the ROM's own bchange stores the record's word),
    then a real press on the bar's right, where a first press hands the mouse to the screen manager: a button is
    DOWN — the word is not 0, though its low byte is — and nothing is re-decided."""
    arrival = evinput.at(PLAYED_BUTTONS, BCHANGE, 1)
    assert arrival.arguments == (EVF["BCHANGE_FIRST_PRESS"], 1) and mouse(before(arrival)) == evinput.BAR_S_RIGHT
    assert case.word_in(before(arrival), BUTTON) == evinput.A_BUTTON_WORD_ABOVE_ITS_BYTE
    assert run(arrival).long(GL_MOWNER) == SHELL != owner_after("a press on the bar's right")[1]


def test_bchange_leaves_the_owner_when_the_mouse_is_the_screen_manager_s():
    """The mouse on the menu bar (mchange handed it to the screen manager), then a press: no mowner — the screen
    manager's button wait is posted."""
    was, now = owner_after("the screen manager hands the mouse back")
    assert was == now == SCREEN_MANAGER


def test_bchange_leaves_the_owner_the_screen_manager_s_off_the_bar_too():
    """The mouse was handed to the screen manager on the bar and has moved off it again (nothing hands it back but
    ct_chgown): a press in the control rectangle does NOT give it to the rectangle's owner."""
    arrival = evinput.at("a press off the bar while the mouse is the screen manager's", BCHANGE)
    image = before(arrival)
    assert mouse(image) == evinput.SNAPSHOT_S_MOUSE and case.long_in(image, GL_MOWNER) == SCREEN_MANAGER
    assert run(arrival).long(GL_MOWNER) == SCREEN_MANAGER


def test_bchange_of_the_right_button_on_a_window_leaves_the_owner():
    """A first press of the RIGHT button on a window's title: the left one there hands the mouse to the screen
    manager (above) — this one re-decides nothing."""
    arrival = evinput.at("a right press on a window's title", BCHANGE)
    assert run(arrival).long(GL_MOWNER) == case.long_in(before(arrival), GL_MOWNER) == SHELL


@pytest.mark.parametrize("scenario, which", (("a right press wakes nobody", 0), (CLICK, 1),
                                             ("the right button pressed inside the left one's count", 1)),
                         ids=("the right button", "a release", "a second button, one down already"))
def test_bchange_re_decides_nothing_but_on_a_first_left_press(scenario, which):
    arrival = evinput.at(scenario, BCHANGE, which)
    assert evinput.SCENARIOS[scenario].arrivals[evinput.nth_of(scenario, BCHANGE, which) + 1] != evinput.MOWNER
    was, now = owner_after(scenario, which)
    assert was == now and arrival.arguments[0] != EVF["BCHANGE_FIRST_PRESS"] or case.word_in(before(arrival), BUTTON)


# ---- mchange ---------------------------------------------------------------------------------------------------------------
def test_mchange_takes_the_mouse_from_the_vdi_not_from_the_event():
    """Two moves queued, the cursor already at the second's point: the first event's mchange stores where the mouse
    IS (the second point), and posts that."""
    arrival = evinput.at("a press on the bar's right", MCHANGE, 0)
    result = run(arrival)
    assert arrival.arguments != evinput.BAR_S_RIGHT and mouse(result.final) == evinput.BAR_S_RIGHT


def test_mchange_hands_the_mouse_to_the_screen_manager_on_the_bar():
    arrival = evinput.at(BAR, MCHANGE)
    waiting, = waits(before(arrival), SCREEN_MANAGER, aes.CDA_MOUSE_WAIT)
    result = run(arrival)
    assert case.long_in(before(arrival), GL_MOWNER) == SHELL and result.long(GL_MOWNER) == SCREEN_MANAGER
    assert evasync.completed(result.final) == [waiting] and aes.list_of(result.final, aes.AES_DRL) == [SCREEN_MANAGER]


@pytest.mark.parametrize("scenario", ("the mouse onto the bar with the button down",
                                      "the mouse onto the bar with the screen owned"),
                         ids=("a button down", "no menu bar"))
def test_mchange_keeps_the_owner_on_the_bar(scenario):
    arrival = evinput.at(scenario, MCHANGE)
    image = before(arrival)
    assert case.word_in(image, BUTTON) or not case.long_in(image, aes.AES_GL_MNTREE), "the premise"
    result = run(arrival)
    assert result.long(GL_MOWNER) == case.long_in(image, GL_MOWNER) == SHELL and mouse(result.final) == aes_event.MENU_BAR_POINT


@pytest.mark.parametrize("scenario, handed", ((BAR, False), ("a rectangle not entered", True)),
                         ids=("inside the rectangle: kept", "outside it: handed over"))
def test_mchange_compares_the_screen_manager_s_rectangle_with_its_leave_word(scenario, handed):
    """A CASE OVER A STAGED FIELD, labelled: `$96d8` — the LEAVE word of the screen manager's own mouse wait — is
    cleared once at start-up and written by nothing else in the ROM, so every machine holds 0 and the mouse is handed
    over INSIDE the rectangle. Staged 1, the sense turns: handed over outside it, kept inside."""
    arrival = evinput.at(scenario, MCHANGE)
    staged = merge_pokes(arrival.machine, {EVI["AES_GL_CTWAIT_LEAVE"]: struct.pack(">H", 1)})
    result = evinput.run_over(MCHANGE, arrival.arguments, staged)
    assert case.long_in(make_image(staged), GL_MOWNER) == SHELL
    assert result.long(GL_MOWNER) == (SCREEN_MANAGER if handed else SHELL)


def test_mchange_keeps_the_owner_off_the_bar():
    arrival = evinput.at("two rectangles, one left", MCHANGE)
    assert run(arrival).long(GL_MOWNER) == SHELL


@pytest.mark.parametrize("way", ("right", "left", "down", "up"))
def test_mchange_ends_a_click_s_count_on_a_move_past_the_slop(way):
    arrival = evinput.at(f"a move {way} ends a click's count", MCHANGE)
    assert case.word_in(before(arrival), CLICK_TICKS)
    result = run(arrival)
    assert result.word(CLICK_TICKS) == 0 and fork_queue(result.final)[-1] == button_change(LEFT, 1)


@pytest.mark.parametrize("which", range(4), ids=("right", "down", "left", "up"))
def test_mchange_leaves_a_click_s_count_open_on_a_move_of_the_slop(which):
    arrival = evinput.at("moves inside the slop leave a click's count open", MCHANGE, which)
    open_ = case.word_in(before(arrival), CLICK_TICKS)
    result = run(arrival)
    assert open_ and result.word(CLICK_TICKS) == open_


def test_mchange_posts_where_the_mouse_is_not_the_event_s_point():
    """Two moves queued toward a rectangle waited to be entered; the first event's point is outside it, the mouse is
    already inside: the FIRST mchange completes the wait."""
    arrival = evinput.at("a rectangle entered two moves away", MCHANGE, 0)
    waiting, = waits(before(arrival), SHELL, aes.CDA_MOUSE_WAIT)
    result = run(arrival)
    assert arrival.arguments != evinput.INSIDE_ELSEWHERE and mouse(result.final) == evinput.INSIDE_ELSEWHERE
    assert evasync.completed(result.final) == [waiting]


def test_mchange_while_a_recording_plays_puts_the_mouse_at_the_event_s_point():
    """THE ROM'S OWN PLAYBACK — the desk's appl_tplay of one mouse record (gl_play set by ap_tplay, the VDI's cursor
    routine saved by it in `$947a`): the mouse is PUT at the event's point — vsin_mode (the locator, sample), the
    saved cursor routine called with the point (the VDI's own: the point queued for its VBL), vsm_locator — and the
    AES's own record of the mouse is the event's point, not where the VDI said it was."""
    arrival = evinput.at(PLAYED, MCHANGE)
    image = before(arrival)
    assert case.word_in(image, EVF["AES_GL_PLAY"]) == 1 and case.long_in(image, GSXIF["AES_DRWADDR"]) == addrs.VDI_ROM_DEFAULT_USER_CUR
    result = run(arrival)
    assert arrival.arguments == evinput.A_PLAYED_POINT != mouse(image) and mouse(result.final) == evinput.A_PLAYED_POINT
    assert (result.word(vdi.LINEA_GCURX), result.word(vdi.LINEA_GCURY)) == evinput.A_PLAYED_POINT


def test_mchange_stores_a_played_point_as_the_event_s_words():
    """THE FINDING: while it plays, mchange stores the EVENT's words — a played x of -1 leaves the AES's mouse at
    $ffff, off any screen (the VDI clamps its own; the AES's record is not asked of it again)."""
    arrival = evinput.at(PLAYED_LEFT, MCHANGE, 0)
    assert arrival.arguments == evinput.LEFT_OF_THE_SCREEN and run(arrival).word(XRAT) == aes.WORD_MASK


def test_mchange_s_slop_is_a_word_difference():
    """...and the next REAL move, a click's count open: the mouse was at -1 by the AES's record and is at 0 or 1 by
    the VDI — a WORD difference of -1 or -2, inside the slop: the count stays open (65,534 unsigned, far past it)."""
    arrival = evinput.at(PLAYED_LEFT, MCHANGE, 1)
    image = before(arrival)
    ticks = case.word_in(image, CLICK_TICKS)
    assert case.word_in(image, XRAT) == aes.WORD_MASK and ticks, "the premise: the played word, a click count open"
    assert aes.signed(case.word_in(image, XRAT)) - aes_event._cursor(image)[0] in range(-EVF["CLICK_SLOP"], 0)
    assert run(arrival).word(CLICK_TICKS) == ticks


# ---- drawrat -----------------------------------------------------------------------------------------------------------------
def test_drawrat_as_mchange_calls_it_while_a_recording_plays():
    """THE ROM'S OWN CALL (mchange's, under the desk's appl_tplay, the cursor shown): the routine in `$947a` is the
    VDI's own cursor routine, which queues the point in D0 / D1 for its VBL to draw."""
    arrival = evinput.at(PLAYED, DRAWRAT)
    result = run(arrival)
    assert arrival.arguments == evinput.A_PLAYED_POINT == (result.word(vdi.LINEA_CUR_X), result.word(vdi.LINEA_CUR_Y))


def test_drawrat_calls_the_saved_cursor_routine():
    """AN ARGUMENT-CLASS CASE (drawrat called over the desk running, where no ROM caller calls it): the saved routine
    is the snapshot's — the ROM's bare `rts`: nothing stored."""
    assert case.long_in(BASE_IMAGE, GSXIF["AES_DRWADDR"]) == addrs.AES_ROM_JUSTRETF
    result = evinput.run_over(DRAWRAT, (100, 50), aes_event.machine())
    assert aes.stored_nothing(result)


@pytest.mark.parametrize("x, y", ((100, 50), (-1, 0x7FFF)), ids=("a point", "words with every bit"))
def test_drawrat_hands_the_point_in_d0_and_d1(x, y):
    """TWO CASES OVER A STAGED FIELD AND ITS CODE, labelled: `$947a` POKED with the address of a cursor routine of the
    case's own (`aes_evinput.CURSOR_ROUTINE`: it logs D0 and D1) — for the WORDS, each whole: the VDI's own routine,
    which the ROM-made call above runs, shows them only through what it queues."""
    result = evinput.run_over(DRAWRAT, (x, y), merge_pokes(aes_event.machine(), evinput.CURSOR_STAGED), hook=evinput.CURSOR_HOOKS)
    assert (result.word(evinput.CURSOR_LOG_AT), result.word(evinput.CURSOR_LOG_AT + aes.WORD_BYTES)) == (x & aes.WORD_MASK, y & aes.WORD_MASK)


# ---- tchange ---------------------------------------------------------------------------------------------------------------
def delays(image):
    """The delay list: `(evb, ticks after the one before)` each."""
    return [(evb, evasync.evb_of(image, evb)["PARM"]) for evb in evasync.wait_list(image, evasync.EV["AES_DELAY_LIST"])]


def tick_armed(image):
    return case.long_in(image, aes.AES_TIMER_COUNTDOWN), case.long_in(image, aes.AES_TIMER_ELAPSED)


def test_tchange_completes_the_one_delay_run_out_and_leaves_the_tick_unarmed():
    arrival = evinput.at(TIMER, TCHANGE)
    (waiting, ticks), = delays(before(arrival))
    result = run(arrival)
    assert ticks == arrival.arguments[0] == evasync.A_TIMER_TICKS
    assert not delays(result.final) and evasync.completed(result.final) == [waiting]
    assert tick_armed(result.final) == tick_armed(before(arrival)), "no delay left: neither word stored"


def test_tchange_completes_the_first_of_two_delays_and_arms_the_tick_for_the_second():
    """A STAGED APPLICATION's machine (Tier 1 only): two delays, 200 and 600 ms — the list holds 10 ticks, then 20
    more. Ten ticks: the first completed, the second left with its 20, the tick armed with them."""
    arrival = evinput.at(FIRST_OF_TWO, TCHANGE)
    (first, short), (second, more) = delays(before(arrival))
    result = run(arrival)
    assert arrival.arguments == (short,) and delays(result.final) == [(second, more)]
    assert evasync.completed(result.final) == [first] and tick_armed(result.final) == (more, 0)


def test_tchange_completes_two_delays_run_out_together():
    """A STAGED APPLICATION's machine (Tier 1 only): two delays of the same time — the second's difference is 0, so
    one tchange completes both, reading the list again from its head after the first."""
    arrival = evinput.at(BOTH_OF_TWO, TCHANGE)
    (first, _ticks), (second, none) = delays(before(arrival))
    result = run(arrival)
    assert none == 0 and not delays(result.final) and set(evasync.completed(result.final)) == {first, second}


@pytest.mark.parametrize("elapsed, left", ((4, 6), (10, 20), (25, 5), (40, None), (0x80000000 + 10, None)),
                         ids=("fewer than the first", "the first's", "into the second", "past both", "a negative long"))
def test_tchange_carries_the_ticks_down_the_list(elapsed, left):
    """ARGUMENT-CLASS CASES over a STAGED APPLICATION's machine (Tier 1 only): ticks the glue never hands (it hands
    the count it armed — the first delay's own) carried down two delays of 10 and 20: a delay with ticks left stops
    the walk and arms the tick; one at or below 0 — compared as a SIGNED long — is completed."""
    arrival = evinput.at(FIRST_OF_TWO, TCHANGE)
    result = run(arrival, (elapsed,))
    waiting = delays(result.final)
    assert (waiting[0][1] if waiting else None) == left


# ---- Tier 3 ------------------------------------------------------------------------------------------------------------------
ROWS = (                                # each routine's WORST first (measured ratios beside the routine's first row)
    ("the thirty-second entry: the tail round the ring", OVERFLOW, FORKQ, ENTRIES - 1),          # 0.84; 0.40..0.81
    ("an entry into the empty queue", KEY, FORKQ, 0),
    ("dropped: the queue is full", OVERFLOW, FORKQ, ENTRIES),
    ("a key to the desk's wait", KEY, FORKER, 1),                                                # unpriced, every one
    ("a full queue of moves", OVERFLOW, FORKER, 0),
    ("nothing queued", KEY, FORKER, 0),
    ("a tick recorded", MERGED, FORKER, 0),
    ("no key", KEY, CHKKBD, 1),                                                                  # 0.80; 0.69..0.70
    ("a key polled and queued", KEY, CHKKBD, 0),
    ("no key, the shift keys changed", "the shift key alone", CHKKBD, 0),
    ("the owner's queue full: no poll", TEN_KEYS, CHKKBD, FM["CQUEUE_ENTRIES"] + 1),
    ("a key to a waiting process", KEY, KCHANGE, 0),                                             # 0.45; 0.37..0.45
    ("the shift keys alone", "the shift key alone", KCHANGE, 0),
    ("a key to a process not waiting", TYPED_AHEAD, KCHANGE, 0),
    ("a press on the bar, the mouse the screen manager's and no wait of its own for it", BAR_CLICK, BCHANGE, 0),  # 0.873
    ("a release", CLICK, BCHANGE, 1),                                                            # 0.870; 0.53..0.79
    ("a first press in the control rectangle, the screen owned", "a press inside the control rectangle", BCHANGE, 0),
    ("a first press on the desktop beside a window", "a press on the desktop beside a window", BCHANGE, 0),
    ("a first press on a window: the screen manager's", "a press on a window's title", BCHANGE, 0),
    ("a first press in the control rectangle", PRESS, BCHANGE, 0),
    ("a move, another queued behind it", "a press on the bar's right", MCHANGE, 0),             # 0.81; 0.63..0.81
    ("a move nobody waits for", OVERFLOW, MCHANGE, 0),
    ("a move ends a click's count", "a move left ends a click's count", MCHANGE, 0),
    ("a move inside a click's count", "moves inside the slop leave a click's count open", MCHANGE, 0),
    ("onto the bar with the button down", "the mouse onto the bar with the button down", MCHANGE, 0),
    ("onto the bar: the screen manager woken", BAR, MCHANGE, 0),
    ("a move with two rectangles waited for", "two rectangles, one left", MCHANGE, 0),
    ("a move played back", PLAYED, MCHANGE, 0),
    ("the one delay run out", TIMER, TCHANGE, 0),                                                # 0.48, every one
)


evasync.register_rows(evinput.at, evinput.register, ROWS,
                      [(THROUGH_LINE_F[routine][0], routine, THROUGH_LINE_F[routine][1]) for routine in (FORKQ, FORKER, CHKKBD)])
