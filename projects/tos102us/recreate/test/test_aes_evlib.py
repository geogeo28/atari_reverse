"""THE EVENT LIBRARY's single waits and appl_read / appl_write (`src/aes/evlib.c`).

    ev_block(code, parm)                 mask = iasync(code, parm); mwait(mask); return apret(mask)        ($fe6874)
    ap_rdwr(code, pid, length, buffer)   ev_block(code, &its own arguments from pid on)                    ($fe65c4)
    ev_keybd()                           ev_block(5, 0)                                                     ($fe6894)
    ev_button(clicks, mask, state, rets) ev_block(7, clicks << 16 | (mask << 8 | state)); ev_rets(rets)     ($fe68a4)
    ev_mouse(moblk, rets)                ev_block(6, moblk); ev_rets(rets); rets[2] = the buttons now       ($fe68e4)
    ev_mesag(buffer)                     $97fe = 0; ap_rdwr(1, rlr->pid, 16, buffer)                        ($fe6910)
    ev_timer(ms)                         ev_block(3, ldiv(ms, the tick's ms))                               ($fe6936)
    ev_rets(rets)                        the mouse (the last button change's place if one was counted), $c792, the
                                         shift keys; the count of button changes cleared                    ($fe681a)
    ev_mchk(moblk)                       rlr owns the mouse and inside(mouse, rect) != the leave flag       ($fe695c)
    ev_dclick(rate, set)                 set: $c79c = rate, $c768 = table[$c79c] / the tick's ms; return $c79c ($fe6c5e)

EVERY MACHINE IS THE ROM's OWN (`aes_evlib`: the arrivals of an application's own calls over the scheduler's
machines), every frame its caller's — but for the ARGUMENT-CLASS cases, each labelled where it stands.

A CALL THAT REACHES THE DISPATCHER (a wait nothing satisfies) is held to the ROM's memory AT DSPTCH
(`aes_evlib.switched`). A BLOCKED ap_rdwr keeps its QPB's address in its EVB — its own arguments, a place in its
caller's stack — the one longword that differs by nature (`aes_evlib.qpb_address_drop`): EVERY case that drops it —
ap_rdwr's and ev_mesag's alike — is held to both addresses naming the same eight bytes (`aes_evlib.held`).

THE LEAF BATTERIES of ev_block, ap_rdwr and ev_button (the twins of door entries): ev_block over every code iasync
knows, returning and blocking, and two it does not, its code and its event bit at their WORD width; ap_rdwr reading
and writing, served at once, serving the other end's wait, and parked on both ends, each argument at its width and
its answer ev_block's; ev_button's parameter in every field and its four answers.

A ROM FINDING the cases pin (`ev_rets`): the "buttons" ev_rets answers are the high word of the LAST ANSWER APRET
TOOK ($c792), whatever kind of wait it was. A button wait's is the buttons. A mouse wait that parked leaves its
rectangle's WIDTH there (amouse keeps w and h in the EVB's answer); ev_mouse stores the real buttons over it
afterwards, and an evnt_multi — which calls ev_rets BEFORE its aprets — hands out the word the call BEFORE it left.
"""
import signal
import struct

import pytest

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evlib as evlib
import aes_pdpipe
import case
import test_aes_wm_update as wm_update
from aes_evlib import (AP_RDWR, EV_BLOCK, EV_BUTTON, EV_DCLICK, EV_KEYBD, EV_MCHK, EV_MESAG, EV_MOUSE, EV_RETS, EV_TIMER)
from aes_gsx import THROUGH
from case import merge_pokes
from test_host_slots import HEADER as HOST_SLOTS_HEADER

pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)
ROUTINES = (EV_BLOCK, AP_RDWR, EV_KEYBD, EV_BUTTON, EV_MOUSE, EV_MESAG, EV_TIMER, EV_RETS, EV_MCHK, EV_DCLICK)
APPLICATION = evlib.STAGED_APPLICATION
SHELL, SCREEN_MANAGER = evlib.SHELL, evlib.SCREEN_MANAGER
ANSWERS_AT, BUFFER_AT, MESSAGE_AT = evlib.ANSWERS_AT, evlib.BUFFER_AT, evlib.MESSAGE_AT
A_MESSAGE = evlib.A_MESSAGE
MESSAGE_BYTES = len(A_MESSAGE)
FM = aes.header_constants("fmlib.h")
EV = evasync.EV
STALE = aes.STALE_WORD


before = aes_event.before


def answers(image, at=ANSWERS_AT, words=evlib.EV_RETS_WORDS):
    return [case.word_in(image, (at & ~aes.BUS_TAG) + index * aes.WORD_BYTES) for index in range(words)]


def mouse(image):
    return case.word_in(image, aes.AES_XRAT), case.word_in(image, aes.AES_YRAT)


def events(image, pd=SHELL):
    """A process's three event words: the bits its EVBs hold, those it waits for, those that came."""
    return tuple(case.word_in(image, pd + field) for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG))


def pipe(image, pd=SHELL):
    """The bytes a process's pipe holds."""
    return bytes(image[pd + aes.PD_QUEUE:pd + aes.PD_QUEUE + case.word_in(image, pd + aes.PD_QUEUE_INDEX)])


# ---- every arrival ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arrival", evlib.cases(*ROUTINES, switching=True), ids=evlib.case_id)
def test_every_arrival_that_reaches_the_dispatcher_is_the_rom_s_at_dsptch(arrival):
    evlib.run(evlib.arrival(*arrival))


@THROUGH
@pytest.mark.parametrize("arrival", evlib.cases(*ROUTINES, switching=False), ids=evlib.case_id)
def test_every_arrival_that_returns(arrival, through_line_f):
    evlib.run(evlib.arrival(*arrival), through_line_f=through_line_f)


# ---- ev_block: the leaf battery ----------------------------------------------------------------------------------------------
RETURNING = {       # a wait of each kind that is satisfied where it is queued: the scenario, and ev_block's answer
    "a key": ("evnt_keybd, a key queued", None),
    "the buttons": ("evnt_button for the button up, which is up", 0),
    "the mouse": ("evnt_mouse to enter the rectangle the mouse is in", 0),
    "a read": ("appl_read, a message in the pipe", 0),
    "a write": ("appl_write to its own pipe", 0),
}


@pytest.mark.parametrize("scenario, answer", RETURNING.values(), ids=RETURNING)
def test_ev_block_of_a_wait_satisfied_at_once_answers_it_and_leaves_no_evb(scenario, answer):
    """The EVB is back at the head of the free list, off the process's list, and its event bit is out of all three of
    the process's event words: the process holds what it held before."""
    arrival = evlib.at(scenario, EV_BLOCK)
    image = before(arrival)
    result = evlib.run(arrival)
    assert evasync.free_evbs(result.final) == evasync.free_evbs(image)
    assert evasync.evlist(result.final, SHELL) == evasync.evlist(image, SHELL) and evasync.completed(result.final) == []
    assert events(result.final)[0] == events(image)[0] and not events(result.final)[1] and not events(result.final)[2]
    if answer is not None:
        assert result.answer() == answer


def test_ev_block_for_a_key_answers_the_key():
    arrival = evlib.at("evnt_keybd, the queue's front round the ring", EV_BLOCK)
    image = before(arrival)
    queue = case.long_in(image, aes.AES_GL_CDA) + FM["CDA_KEY_QUEUE"]
    key = case.word_in(image, queue + FM["CQUEUE_KEYS"] + case.word_in(image, queue + FM["CQUEUE_FRONT"]) * aes.WORD_BYTES)
    assert evlib.run(arrival).answer() == aes.signed(key) != 0


BLOCKING = {        # a wait of each kind that nothing satisfies: the scenario, and the list its EVB is left on
    "a key": ("evnt_keybd, none", lambda image: case.long_in(image, aes.AES_GL_CDA) + aes.CDA_KEYBOARD_WAIT),
    "the buttons": ("evnt_button for a press", lambda image: case.long_in(image, aes.AES_GL_CDA) + aes.CDA_BUTTON_WAIT),
    "the mouse": ("evnt_mouse to leave the rectangle the mouse is in",
                  lambda image: case.long_in(image, aes.AES_GL_CDA) + aes.CDA_MOUSE_WAIT),
    "a delay": ("evnt_timer", lambda image: EV["AES_DELAY_LIST"]),
    "a read": ("appl_read, none", lambda image: SHELL + aes.PD_QUEUE_READERS),
    "a write": ("appl_write to a full pipe", lambda image: SHELL + aes.PD_QUEUE_WRITERS),
    "the screen's lock": ("wind_update(BEG), the lock another's", lambda image: evlib.WIND_SPB + evlib.SPB_WAIT),
}


@pytest.mark.parametrize("scenario, waits_on", BLOCKING.values(), ids=BLOCKING)
def test_ev_block_of_a_wait_nothing_satisfies_queues_it_and_blocks(scenario, waits_on):
    arrival = evlib.at(scenario, EV_BLOCK)
    image = before(arrival)
    running = evasync.running(image)
    evb = evasync.free_evbs(image)[0]
    switched = evlib.run(arrival)
    assert evlib.BLOCKS in switched.stderr
    assert evasync.wait_list(switched.image, waits_on(switched.image))[0] == evb
    assert evasync.evlist(switched.image, running)[0] == evb and evasync.free_evbs(switched.image) == evasync.free_evbs(image)[1:]
    bit = evasync.evb_of(switched.image, evb)["MASK"]
    assert events(switched.image, running)[1] == bit and not events(switched.image, running)[2] & bit
    assert case.word_in(switched.image, running + aes.PD_STAT) == aes.PD_STAT_WAITING


@pytest.mark.parametrize("code", (0, 8, -1), ids=("0", "8", "-1"))
def test_ev_block_with_a_code_of_no_wait_blocks_for_good(code):
    """AN ARGUMENT-CLASS CASE (a code no caller hands): iasync queues the EVB on no list, nothing completes it, and
    mwait enters the dispatcher — a process no event will ever wake."""
    machine = evlib.desk_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    switched = evlib.switched(EV_BLOCK, (code, 0), machine)
    block = evasync.evb_of(switched.image, evb)
    assert (block["LINK"], block["PRED"]) == (0, 0) and evasync.evlist(switched.image, SHELL) == [evb]


@pytest.mark.parametrize("machine, holds", ((evlib.desk_running, 1), (wm_update.locked, 2)), ids=("a free lock", "its own"))
def test_ev_block_for_a_lock_tak_flag_takes_returns_with_it(machine, holds):
    """AN ARGUMENT-CLASS CASE: wind_update calls ev_block only after tak_flag refused, so no ROM run makes this call
    over a lock amutex's own tak_flag then takes. Over the scheduler's machine: the lock taken, the wait answered 0."""
    result = evlib.returning(EV_BLOCK, (evlib.MUTEX, evlib.WIND_SPB), machine(),
                         steered=(evlib.STEERS_THE_EVENT_BITS, evlib.STEERS_THE_LISTS, evlib.STEERS_THE_LOCK))
    assert evlib.lock(result.final) == (holds, SHELL, []) and result.answer() == 0
    assert evasync.free_evbs(result.final) == evasync.free_evbs(make_image(machine()))


A_KEY_WAIT_IN_ITS_LOW_BYTE = 0x0105     # a code of no wait whose low byte is the key wait's
# What steers the attribution pass over a process that holds event bits already: the lists' links alone — its event
# words inverted still leave the wait a free bit, and the run returns.
MORE_BITS_HELD = (evlib.STEERS_THE_LISTS,)


def test_ev_block_hands_its_code_on_as_a_word():
    """AN ARGUMENT-CLASS CASE (a code no caller hands), a key queued: $105 is no wait's code — the EVB queued
    nowhere, the call blocks for good. A code cut to its low byte would be the key wait, and return the key."""
    assert isinstance(evlib.held(EV_BLOCK, (A_KEY_WAIT_IN_ITS_LOW_BYTE, 0), evlib.key_queued()), evlib.Switched)


def test_ev_block_waits_for_and_answers_an_event_bit_above_the_low_byte():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.eight_event_bits_held`): the wait's bit is $100, and mwait and apret
    are handed the WORD — a wait the buttons satisfy returns, its EVB freed, the eight bits still held."""
    machine = evlib.eight_event_bits_held()
    image = make_image(machine)
    assert events(image)[0] == 0xFF
    result = evlib.returning(EV_BLOCK, (evlib.BUTTON, evlib.THE_BUTTON_UP), machine, steered=MORE_BITS_HELD)
    assert events(result.final) == (0xFF, 0, 0)
    assert evasync.free_evbs(result.final) == evasync.free_evbs(image)


def test_ev_block_answers_its_own_wait_when_other_events_have_come():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.two_events_come`): two waits completed and unanswered, a third queued and
    satisfied — apret is handed the THIRD's bit (mwait answers all three: not what is passed on), and the two others
    stay come."""
    result = evlib.returning(EV_BLOCK, (evlib.BUTTON, evlib.THE_BUTTON_UP), evlib.two_events_come(), steered=MORE_BITS_HELD)
    assert events(result.final) == (3, 0, 3)


def test_ev_block_takes_its_parameter_s_pointer_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the MOBLK's pointer with a top byte."""
    arrival = evlib.at("evnt_mouse to enter the rectangle the mouse is in", EV_BLOCK)
    evlib.run(arrival, (arrival.arguments[0], arrival.arguments[1] | aes.BUS_TAG))


# ---- ap_rdwr: the leaf battery -----------------------------------------------------------------------------------------------
def test_ap_rdwr_writes_a_message_into_the_pipe():
    arrival = evlib.at("appl_write to its own pipe", AP_RDWR)
    image = before(arrival)
    result = evlib.run(arrival)
    assert pipe(image) == b"" and pipe(result.final) == A_MESSAGE and result.answer() == 0


def test_ap_rdwr_writes_as_many_bytes_as_it_is_told():
    arrival = evlib.at("appl_write of two messages at once", AP_RDWR)
    assert pipe(evlib.run(arrival).final) == A_MESSAGE + evlib.ANOTHER_MESSAGE


def test_ap_rdwr_writes_into_the_pipe_of_the_process_it_names():
    arrival = evlib.at("appl_write to the screen manager's pipe", AP_RDWR)
    result = evlib.run(arrival)
    assert pipe(result.final, SCREEN_MANAGER) == A_MESSAGE and pipe(result.final) == b""


def test_ap_rdwr_s_write_serves_the_process_waiting_to_read_and_wakes_it():
    """The screen manager's appl_write to the desk, parked on its message wait: the message goes through the pipe
    into the desk's own buffer, its wait is completed and the desk made ready."""
    arrival = evlib.at("appl_write to the parked desk", AP_RDWR)
    image = before(arrival)
    result = evlib.run(arrival)
    assert evasync.running(image) == SCREEN_MANAGER and aes.list_of(image, aes.AES_NRL) == [SHELL]
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL] and aes.list_of(result.final, aes.AES_NRL) == []
    assert pipe(result.final) == b"" and evasync.wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) == []


def test_ap_rdwr_reads_a_message_out_of_the_pipe():
    arrival = evlib.at("appl_read, a message in the pipe", AP_RDWR)
    image = before(arrival)
    result = evlib.run(arrival)
    assert pipe(image) and result.after(BUFFER_AT, MESSAGE_BYTES) == pipe(image) and pipe(result.final) == b""


def test_ap_rdwr_s_read_serves_the_process_waiting_to_write_and_wakes_it():
    """The desk's pipe full, the screen manager parked in a write: the read takes the first message, the rest moves
    down, the waiting write goes in behind it and the screen manager is made ready."""
    arrival = evlib.at(SERVES_A_WRITER, AP_RDWR)
    image = before(arrival)
    result = evlib.run(arrival)
    held = pipe(image)
    assert len(held) == aes.PD_QUEUE_BYTES and evasync.wait_list(image, SHELL + aes.PD_QUEUE_WRITERS)
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == held[:MESSAGE_BYTES]
    assert pipe(result.final)[:-MESSAGE_BYTES] == held[MESSAGE_BYTES:] and len(pipe(result.final)) == aes.PD_QUEUE_BYTES
    assert aes.list_of(result.final, aes.AES_DRL) == [SCREEN_MANAGER]
    assert evasync.wait_list(result.final, SHELL + aes.PD_QUEUE_WRITERS) == []


PARKED = {      # the scenario, the process whose pipe it is, and the end the wait is left on
    "a write to a full pipe": ("appl_write to a full pipe", SHELL, aes.PD_QUEUE_WRITERS),
    "a read of an empty pipe": ("appl_read, none", SHELL, aes.PD_QUEUE_READERS),
    "a read of another's empty pipe": ("appl_read of the screen manager's pipe, empty", SCREEN_MANAGER,
                                       aes.PD_QUEUE_READERS),
}


@pytest.mark.parametrize("scenario, pd, end", PARKED.values(), ids=PARKED)
def test_ap_rdwr_parks_on_the_pipe_s_end_with_its_arguments_as_the_qpb(scenario, pd, end):
    """The wait's EVB on the pipe's end, its parameter the QPB's ADDRESS — the one longword dropped by name, and
    held by `aes_evlib.held` on each shore to eight bytes in that shore's stack band that are the same QPB: the
    process, the length, the buffer the caller handed. The two addresses differ: that is the drop."""
    arrival = evlib.at(scenario, AP_RDWR)
    evb = evasync.free_evbs(before(arrival))[0]
    switched = evlib.run(arrival)
    assert evlib.BLOCKS in switched.stderr and evasync.wait_list(switched.image, pd + end) == [evb]
    assert evasync.evb_of(switched.image, evb)["PARM"] != evasync.evb_of(switched.rom_memory, evb)["PARM"] == evlib.ROM_QPB_AT


def _with_its_qpb_s_last_byte_changed(shore, evb):
    tampered = bytearray(shore)
    tampered[evasync.evb_of(shore, evb)["PARM"] + aes_pdpipe.QPB.size - 1] ^= 1
    return bytes(tampered)


@pytest.mark.parametrize("scenario, routine", (("appl_read, none", AP_RDWR), ("evnt_mesag, none", EV_MESAG)))
def test_a_parked_qpb_that_is_not_the_one_handed_is_refused_by_name(scenario, routine):
    """THE VET IS NOT VACUOUS: the C's image with its QPB's buffer changed — eight bytes in the stack band, which no
    comparison at dsptch reads — is refused as not the ROM's; and with BOTH shores' changed alike, as not the one
    the call was handed."""
    arrival = evlib.at(scenario, routine)
    switched = evlib.run(arrival)
    evb = evasync.free_evbs(before(arrival))[0]
    ours = switched._replace(image=_with_its_qpb_s_last_byte_changed(switched.image, evb))
    with pytest.raises(AssertionError, match="the QPB the parked wait names .* is not the ROM's"):
        evlib.vet_the_parked_qpb(routine, arrival.arguments, arrival.machine, ours)
    both = ours._replace(rom_memory=_with_its_qpb_s_last_byte_changed(switched.rom_memory, evb))
    with pytest.raises(AssertionError, match="the parked wait names the QPB .*, handed"):
        evlib.vet_the_parked_qpb(routine, arrival.arguments, arrival.machine, both)


def test_every_case_that_drops_a_parked_qpb_s_address_is_held_to_the_qpb(monkeypatch):
    """...ap_rdwr's and ev_mesag's alike: `aes_evlib.held` vets wherever it drops."""
    vetted = []
    monkeypatch.setattr(evlib, "vet_the_parked_qpb", lambda name, *_rest: vetted.append(name))
    evlib.run(evlib.at("appl_read, none", AP_RDWR))
    evlib.run(evlib.at("evnt_mesag, none", EV_MESAG))
    evlib.run(evlib.at("evnt_keybd, none", EV_KEYBD))
    assert vetted == [AP_RDWR, EV_MESAG]


def test_only_a_call_that_parks_a_qpb_drops_its_address():
    """ap_rdwr on a pipe and ev_mesag; not ap_rdwr with a code of another wait (it hands ev_block the same address,
    and no routine keeps it), nor any other routine."""
    machine = evlib.desk_running()
    read = (evlib.READ, evlib.SHELL_PID, MESSAGE_BYTES, BUFFER_AT)
    assert evlib.qpb_drop_of(AP_RDWR, read, machine) and evlib.qpb_drop_of(EV_MESAG, (BUFFER_AT,), machine)
    assert not evlib.qpb_drop_of(AP_RDWR, (evlib.KEYBOARD, *read[1:]), machine)
    assert not evlib.qpb_drop_of(EV_BLOCK, (evlib.KEYBOARD, 0), machine)


def test_ap_rdwr_parks_with_its_buffer_s_long_as_handed():
    """AN ARGUMENT-CLASS CASE (the buffer's pointer with a top byte): the QPB keeps the LONG, tag and all — held on
    both shores by `aes_evlib.held`."""
    arrival = evlib.at("appl_read, none", AP_RDWR)
    code, process, length, buffer = arrival.arguments
    switched = evlib.run(arrival, (code, process, length, buffer | aes.BUS_TAG))
    qpb = evasync.evb_of(switched.image, evasync.free_evbs(before(arrival))[0])["PARM"]
    assert aes_pdpipe.QPB.unpack_from(switched.image, qpb)[2] == buffer | aes.BUS_TAG


HOST_PROCESSES = addrs.parse(HOST_SLOTS_HEADER)["HOST_PROCESSES"]
REFUSED_FOR_NO_PROCESS_OF_THE_AES = "a frame local kept per process, for a running process whose id is none of the AES's"


def test_ap_rdwr_by_a_process_whose_id_is_none_of_the_aes_s_is_refused_by_name_off_target():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the running PD's id word; no machine holds a tenth process): the
    ROM's ap_rdwr never reads the id — its QPB is its own arguments, on whatever stack it runs on. Off target the
    QPB is a host slot PER PROCESS, chosen by that id: the last id that is one of the AES's is served, the first
    that is not is a refusal BY NAME (it was a bare `assert`), never a frame past the slots."""
    arrival = evlib.at("appl_write to its own pipe", AP_RDWR)
    id_at = (evasync.running(before(arrival)) & aes_event.OS_BUS_ADDR_MASK) + aes.PD_PID

    def by_process(process):
        machine = merge_pokes(arrival.machine, {id_at: struct.pack(">H", process)})
        return aes_event.core_in_a_fork(AP_RDWR, arrival.arguments, machine)
    assert by_process(HOST_PROCESSES - 1).returncode == 0
    refused = by_process(HOST_PROCESSES)
    assert refused.returncode == -int(signal.SIGABRT) and REFUSED_FOR_NO_PROCESS_OF_THE_AES in refused.stderr, refused


A_LENGTH_ABOVE_A_BYTE = 0x0110          # 272 bytes: more than a pipe holds; its low byte is one message's 16


def test_ap_rdwr_s_length_is_a_word():
    """AN ARGUMENT-CLASS CASE (appl_write of a length an application may hand): 272 bytes fit no pipe — the write
    parks, its QPB's count the whole word. Its low byte alone would be a message that fits, and is written."""
    machine = merge_pokes(evlib.desk_running(), {MESSAGE_AT: A_MESSAGE})
    switched = evlib.held(AP_RDWR, (evlib.WRITE, evlib.SHELL_PID, A_LENGTH_ABOVE_A_BYTE, MESSAGE_AT), machine)
    assert isinstance(switched, evlib.Switched) and pipe(switched.image) == b""


def test_ap_rdwr_answers_what_ev_block_answers():
    """AN ARGUMENT-CLASS CASE (a code appl_read and appl_write never hand) and A ROM FINDING CORRECTED: ap_rdwr's
    answer is ev_block's word, not 0 — 0 only because a pipe's wait answers 0. With the key wait's code it answers
    the key queued."""
    result = evlib.held(AP_RDWR, (evlib.KEYBOARD, evlib.SHELL_PID, 0, 0), evlib.key_queued())
    assert not isinstance(result, evlib.Switched) and result.answer() != 0


def test_ap_rdwr_hands_its_code_on_as_a_word():
    """AN ARGUMENT-CLASS CASE, a key queued: $105 is no wait's code, and the call blocks for good (ev_block's own
    case, above) — parking no QPB's address: nothing is dropped."""
    assert isinstance(evlib.held(AP_RDWR, (A_KEY_WAIT_IN_ITS_LOW_BYTE, evlib.SHELL_PID, 0, 0), evlib.key_queued()), evlib.Switched)


@pytest.mark.parametrize("process", (5, 0x100), ids=("5", "$100: a low byte of PD0's"))
def test_ap_rdwr_to_a_process_id_no_pd_has_is_refused_by_name(process):
    """AN ARGUMENT-CLASS CASE, C alone (the ROM's run does not return: `src/aes/pdpipe.c`, aqueue's refusal): the
    process id ap_rdwr laid in its QPB is the one aqueue looks up — the WORD."""
    forked = aes_event.core_in_a_fork(AP_RDWR, (evlib.WRITE, process, MESSAGE_BYTES, MESSAGE_AT), evlib.desk_running())
    assert forked.returncode != 0 and "a pipe of a process id no PD has" in forked.stderr


@pytest.mark.parametrize("scenario", ("appl_write to its own pipe", "appl_read, a message in the pipe"))
def test_ap_rdwr_takes_its_buffer_through_the_bus(scenario):
    """AN ARGUMENT-CLASS CASE: the buffer's pointer with a top byte."""
    arrival = evlib.at(scenario, AP_RDWR)
    evlib.run(arrival, arrival.arguments[:3] + (arrival.arguments[3] | aes.BUS_TAG,))


@pytest.mark.parametrize("length", (0, 2, MESSAGE_BYTES + 2), ids=("nothing", "two bytes", "a message and a word"))
def test_ap_rdwr_writes_a_length_that_is_no_message_s(length):
    """AN ARGUMENT-CLASS CASE (appl_write of a length an application may hand): the length is the QPB's count."""
    machine = merge_pokes(evlib.desk_running(), {MESSAGE_AT: A_MESSAGE + evlib.ANOTHER_MESSAGE})
    result = evlib.returning(AP_RDWR, (evlib.WRITE, evlib.SHELL_PID, length, MESSAGE_AT), machine)
    assert pipe(result.final) == (A_MESSAGE + evlib.ANOTHER_MESSAGE)[:length]


# ---- ap_rdwr: two processes' frames live at once --------------------------------------------------------------------------
def test_two_processes_parked_in_ap_rdwr_keep_their_qpbs_in_two_places():
    """The QPB is the calling PROCESS's (on its own stack in the ROM): PD0's parked appl_read and the screen
    manager's parked read of its own pipe leave their waits pointing at two disjoint places of the stack band, a
    process id apart."""
    desk, manager = evlib.desk_running(), evlib.manager_running()
    read = (evlib.READ, evlib.SHELL_PID, MESSAGE_BYTES, BUFFER_AT)
    the_desk_s = evlib.parked_qpb_at(evlib.held(AP_RDWR, read, desk), desk)
    the_manager_s = evlib.parked_qpb_at(evlib.held(AP_RDWR, (evlib.READ, evlib.SCREEN_MANAGER_PID, *read[2:]), manager), manager)
    assert the_manager_s - the_desk_s == (evlib.SCREEN_MANAGER_PID - evlib.SHELL_PID) * aes_pdpipe.QPB.size


def test_a_write_serves_a_read_parked_in_another_process_s_own_qpb():
    """THE COMMONEST TWO-PROCESS MACHINE (`aes_evlib.reader_parked_in_its_own_frame`): PD0 parked in its appl_read,
    the screen manager's appl_write to it. The write is served THROUGH the reader's QPB — its buffer takes the
    message, its wait is completed, PD0 made ready — while the writer's own QPB is live: one host slot for both
    would hand aqueue the writer's QPB for the reader's (the message "read" into the writer's own buffer)."""
    machine, the_reader_s = evlib.reader_parked_in_its_own_frame()
    image = make_image(merge_pokes(machine, {MESSAGE_AT: A_MESSAGE}))
    assert evasync.running(image) == SCREEN_MANAGER and aes.list_of(image, aes.AES_NRL) == [SHELL]
    assert aes_pdpipe.QPB.unpack_from(image, the_reader_s) == (evlib.SHELL_PID, MESSAGE_BYTES, BUFFER_AT)
    result = evlib.held(AP_RDWR, (evlib.WRITE, evlib.SHELL_PID, MESSAGE_BYTES, MESSAGE_AT), merge_pokes(machine, {MESSAGE_AT: A_MESSAGE}))
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == A_MESSAGE != bytes(image[BUFFER_AT:BUFFER_AT + MESSAGE_BYTES])
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL] and pipe(result.final) == b""
    assert evasync.wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) == []


# ---- ev_keybd ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario, key", (("evnt_keybd, a key queued", None), ("evnt_keybd, Alt-= queued", evlib.ALT_EQUALS)))
def test_ev_keybd_answers_the_key_queued(scenario, key):
    arrival = evlib.at(scenario, EV_KEYBD)
    image = before(arrival)
    queue = case.long_in(image, aes.AES_GL_CDA) + FM["CDA_KEY_QUEUE"]
    front = case.word_in(image, queue + FM["CQUEUE_KEYS"] + case.word_in(image, queue + FM["CQUEUE_FRONT"]) * aes.WORD_BYTES)
    result = evlib.run(arrival)
    assert result.answer() & aes.WORD_MASK == front and (key is None or front == key)


def test_ev_keybd_with_no_key_blocks_on_the_keyboard_wait():
    switched = evlib.run(evlib.at("evnt_keybd, none", EV_KEYBD))
    assert len(evasync.wait_list(switched.image, case.long_in(switched.image, aes.AES_GL_CDA) + aes.CDA_KEYBOARD_WAIT)) == 1


# ---- ev_button: the leaf battery ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario, buttons, shift", (
    ("evnt_button for the button up, which is up", 0, 0),
    ("evnt_button for the button down, which is down", evlib.LEFT, 0),
    ("evnt_button for either button not up, the left down", evlib.LEFT, 0),
    ("evnt_button for the button up, Alt held", 0, evlib.ALT_HELD),
))
def test_ev_button_satisfied_at_once_answers_the_mouse_the_buttons_and_the_shift_keys(scenario, buttons, shift):
    arrival = evlib.at(scenario, EV_BUTTON)
    image = before(arrival)
    assert answers(image) == [STALE] * 4
    result = evlib.run(arrival)
    assert answers(result.final) == [*mouse(image), buttons, shift] and result.answer() == 0
    assert case.word_in(result.final, evasync.BUTTON_STATE) == buttons


@pytest.mark.parametrize("scenario, packed", (
    ("evnt_button for a press", evasync.button_wait(evlib.SINGLE)),
    ("evnt_button for a double click", evasync.button_wait(evlib.DOUBLE)),
    ("evnt_button for the right button down", evasync.button_wait(evlib.SINGLE, evlib.RIGHT, evlib.RIGHT)),
    ("evnt_button for either button not up, which they are", evasync.button_wait(evlib.EITHER | evlib.SINGLE, evlib.LEFT | evlib.RIGHT, evlib.UP)),
    ("evnt_button with a state wider than a byte", evasync.button_wait(evlib.SINGLE, evlib.LEFT, evlib.WIDE_STATE)),
    ("evnt_button with state bits outside its mask", evasync.button_wait(evlib.SINGLE, evlib.LEFT, evlib.OUTSIDE_THE_MASK)),
    # ...the mask is shifted as a WORD (`lsl.w #8`): its high byte is lost, and never reaches the clicks.
    ("evnt_button with a mask wider than a byte", evasync.button_wait(evlib.SINGLE, evlib.WIDE_MASK & aes.BYTE_MASK, evlib.LEFT)),
))
def test_ev_button_packs_its_wait_s_parameter_and_blocks_writing_no_answer(scenario, packed):
    """The clicks WORD in the high word (its high byte the "either" sense), the mask a byte above the state — and
    the state ORed in WHOLE: one wider than a byte reaches the mask."""
    arrival = evlib.at(scenario, EV_BUTTON)
    evb = evasync.free_evbs(before(arrival))[0]
    switched = evlib.run(arrival)
    assert evlib.BLOCKS in switched.stderr and evasync.evb_of(switched.image, evb)["PARM"] == packed
    assert answers(switched.image) == [STALE] * 4


def test_ev_button_takes_its_answers_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the answers' pointer with a top byte."""
    arrival = evlib.at("evnt_button for the button down, which is down", EV_BUTTON)
    result = evlib.run(arrival, arrival.arguments[:3] + (ANSWERS_AT | aes.BUS_TAG,))
    assert answers(result.final)[2] == evlib.LEFT


A_BUTTON_NO_MOUSE_HAS = 0x80             # a mask and a state whose packed low word, $8080, has its top bit set


def test_ev_button_keeps_a_low_word_with_its_top_bit_set_out_of_the_clicks():
    """AN ARGUMENT-CLASS CASE (a mask of $80, a button no mouse has): the low word $8080 is ORed in ZERO-extended
    (`swap / clr.w / swap`) — the clicks word above it stays 1, its sense byte 0, and the wait parks."""
    machine = evlib.desk_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    switched = evlib.held(EV_BUTTON, (evlib.SINGLE, A_BUTTON_NO_MOUSE_HAS, A_BUTTON_NO_MOUSE_HAS, ANSWERS_AT), machine)
    parked_with = evasync.button_wait(evlib.SINGLE, A_BUTTON_NO_MOUSE_HAS, A_BUTTON_NO_MOUSE_HAS)
    assert isinstance(switched, evlib.Switched) and evasync.evb_of(switched.image, evb)["PARM"] == parked_with


@pytest.mark.parametrize("clicks, mask, state", ((-1, -1, -1), (0, 0, 0), (0x7FFF, 0x80, 0x80)),
                         ids=("every bit", "no bit", "the sign bits"))
def test_ev_button_over_words_no_application_hands(clicks, mask, state):
    """AN ARGUMENT-CLASS CASE: the parameter's three words at their widths — the clicks unsigned into the high word,
    the low word never sign-extended into the high."""
    evlib.held(EV_BUTTON, (clicks, mask, state, ANSWERS_AT), evlib.desk_running())
    evlib.held(EV_BUTTON, (clicks, mask, state, ANSWERS_AT), evlib.button_held())


# ---- ev_mouse ------------------------------------------------------------------------------------------------------------------
def test_ev_mouse_answers_the_buttons_as_they_are_not_as_ev_rets_left_them():
    """The button down, the wait satisfied at once: apret's answer has no high word, so ev_rets hands 0 for the
    buttons — and ev_mouse stores the buttons themselves over it."""
    arrival = evlib.at("evnt_mouse to enter the rectangle the mouse is in, the button down", EV_MOUSE)
    image = before(arrival)
    result = evlib.run(arrival)
    assert case.word_in(result.final, evasync.BUTTON_STATE) == 0 != case.word_in(image, aes.AES_BUTTON)
    assert answers(result.final) == [*mouse(image), evlib.LEFT, 0]


@pytest.mark.parametrize("answers_at", (aes.AES_BUTTON, aes.AES_BUTTON - evlib.EVLIB["EV_RETS_Y"],
                                        aes.AES_BUTTON - evlib.EVLIB["EV_RETS_SHIFT_KEYS"]),
                         ids=("the first answer", "the second", "the fourth"))
def test_ev_mouse_reads_the_buttons_after_ev_rets_has_stored_its_answers(answers_at):
    """ARGUMENT-CLASS CASES (the answers laid OVER the buttons' own word, the button down): ev_rets stores the
    mouse's x, its y or the shift keys there FIRST, and the "buttons" ev_mouse then stores over the third answer are
    read after — that word, not the buttons the call began with."""
    arrival = evlib.at("evnt_mouse to enter the rectangle the mouse is in, the button down", EV_MOUSE)
    evlib.returning(EV_MOUSE, (arrival.arguments[0], answers_at), arrival.machine)


def test_ev_mouse_blocks_with_its_rectangle_queued_and_no_answer_written():
    switched = evlib.run(evlib.at("evnt_mouse to leave the rectangle the mouse is in", EV_MOUSE))
    assert evlib.BLOCKS in switched.stderr and answers(switched.image) == [STALE] * 4


def test_ev_mouse_takes_both_pointers_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the MOBLK's and the answers' pointers with a top byte."""
    arrival = evlib.at("evnt_mouse to leave a rectangle the mouse is not in", EV_MOUSE)
    result = evlib.run(arrival, tuple(pointer | aes.BUS_TAG for pointer in arrival.arguments))
    assert answers(result.final)[:2] == list(mouse(before(arrival)))


# ---- ev_mesag ------------------------------------------------------------------------------------------------------------------
SENT_MARK = evlib.EVLIB["AES_CTL_MESSAGE_SENT"]


def test_ev_mesag_reads_the_first_message_of_the_running_process_s_pipe():
    arrival = evlib.at("evnt_mesag, two messages in the pipe", EV_MESAG)
    image = before(arrival)
    result = evlib.run(arrival)
    held = pipe(image)
    assert len(held) == 2 * MESSAGE_BYTES
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == held[:MESSAGE_BYTES] and pipe(result.final) == held[MESSAGE_BYTES:]


@pytest.mark.parametrize("scenario", ("evnt_mesag, a message in the pipe", "evnt_mesag, none"))
def test_ev_mesag_clears_the_control_manager_s_sent_mark_before_it_reads(scenario):
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the mark set: the control manager sets it after sending a window
    message, $fe487e — a run this battery does not make): cleared whether the read returns or parks."""
    arrival = evlib.at(scenario, EV_MESAG)
    marked = merge_pokes(arrival.machine, {SENT_MARK: struct.pack(">H", 1)})
    result = evlib.held(EV_MESAG, arrival.arguments, marked)
    assert case.word_in(evlib.image_after(result), SENT_MARK) == 0


def test_ev_mesag_reads_the_screen_manager_s_own_pipe_when_it_runs():
    """The process id is the RUNNING process's: the screen manager's evnt_mesag parks on ITS pipe's readers."""
    machine = evlib.manager_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    switched = evlib.held(EV_MESAG, (BUFFER_AT,), machine)
    assert evasync.wait_list(switched.image, SCREEN_MANAGER + aes.PD_QUEUE_READERS)[0] == evb


def test_ev_mesag_takes_its_buffer_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the buffer's pointer with a top byte."""
    arrival = evlib.at("evnt_mesag, a message in the pipe", EV_MESAG)
    result = evlib.run(arrival, (BUFFER_AT | aes.BUS_TAG,))
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == pipe(before(arrival))


# ---- ev_timer ------------------------------------------------------------------------------------------------------------------
TICK_MS = evlib.TICK_MS


@pytest.mark.parametrize("milliseconds, ticks", (
    (100, 5), (0, 1), (19, 1), (20, 1), (39, 1), (40, 2), (-100, -5), (-39, -1), (-19, 1), (2_000_000, 100_000),
    (0x7FFFFFFF, 0x7FFFFFFF // 20), (-0x80000000, 1),
), ids=lambda value: str(value))
def test_ev_timer_waits_the_milliseconds_as_ticks(milliseconds, ticks):
    """The milliseconds divided by the tick's as SIGNED LONGS, toward zero (ldiv) — and a delay of no tick is one of
    one (adelay). An application's own evnt_timer over the scheduler's machine; every one blocks. (-$80000000 is
    ldiv's own edge: its magnitude stays negative, the quotient is 0 — one tick.)"""
    machine = evlib.desk_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    switched = evlib.held(EV_TIMER, (milliseconds & aes.LONG_MASK,), machine)
    assert evlib.BLOCKS in switched.stderr
    assert aes.signed(evasync.evb_of(switched.image, evb)["PARM"], 32) == ticks
    assert evasync.wait_list(switched.image, EV["AES_DELAY_LIST"]) == [evb]


# ---- ev_rets -------------------------------------------------------------------------------------------------------------------
def answered(scenario):
    arrival = evlib.at(scenario, EV_RETS)
    image = before(arrival)
    return image, evlib.run(arrival), arrival.arguments[0]


def test_ev_rets_answers_where_the_mouse_is_when_no_button_change_was_counted():
    image, result, at = answered("evnt_multi for a rectangle the mouse is in")
    assert case.word_in(image, aes.AES_MTRANS) == 0
    assert answers(result.final, at) == [*mouse(image), case.word_in(image, evasync.BUTTON_STATE), 0]


def test_ev_rets_answers_where_the_button_changed_when_a_change_was_counted():
    """A press, then the mouse moved on, in one idle: the place answered is the click's own, not the mouse's now —
    and the count of changes is cleared."""
    image, result, at = answered("a press, then the mouse moves, in one idle")
    click = case.word_in(image, aes.AES_PR_XRAT), case.word_in(image, aes.AES_PR_YRAT)
    assert case.word_in(image, aes.AES_MTRANS) == 1 and click != mouse(image)
    assert answers(result.final, at)[:2] == list(click) and case.word_in(result.final, aes.AES_MTRANS) == 0


def test_ev_rets_answers_the_shift_keys():
    image, result, at = answered("evnt_button for the button up, Alt held")
    assert case.word_in(image, aes.AES_KSTATE) == evlib.ALT_HELD and answers(result.final, at)[3] == evlib.ALT_HELD


def test_ev_rets_answers_a_mouse_wait_s_width_as_the_buttons_in_the_evnt_multi_after_it():
    """THE ROM FINDING (the module's docstring): PD0's evnt_multi parked for the mouse to leave a rectangle 20 wide
    and was woken by it; its apret left that wait's high word — the WIDTH — in $c792. The NEXT evnt_multi's ev_rets
    hands it out as the buttons, no button down."""
    image, result, at = answered("evnt_multi for a rectangle the mouse is in, after a mouse wait was woken")
    width = evlib.ROUND_THE_MOUSE[2]
    assert case.word_in(image, evasync.BUTTON_STATE) == width and case.word_in(image, aes.AES_BUTTON) == 0
    assert answers(result.final, at)[2] == width


def test_ev_rets_takes_its_answers_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the answers' pointer with a top byte."""
    arrival = evlib.at("a press, then the mouse moves, in one idle", EV_RETS)
    evlib.run(arrival, (ANSWERS_AT | aes.BUS_TAG,))


# ARGUMENT-CLASS CASES: the answers laid OVER the words ev_rets reads, over the ROM's own machines — the ORDER of its
# reads and stores.
OVERLAPS = {
    # x is stored over $c792, and the buttons answered are read from it after: the mouse's x.
    "the buttons' word under the first answer": evasync.BUTTON_STATE,
    # the fourth answer is stored over the count of button changes, which is cleared LAST.
    "the count of changes under the last answer": aes.AES_MTRANS - evlib.EVLIB["EV_RETS_SHIFT_KEYS"],
    # x is stored over the mouse's y, which is read for the second answer after.
    "the mouse's y under the first answer": aes.AES_YRAT,
    # the buttons are stored over the shift keys, read for the fourth answer after.
    "the shift keys under the third answer": aes.header_constants("gsxif.h")["AES_KSTATE"] - evlib.EVLIB["EV_RETS_BUTTONS"],
}


@pytest.mark.parametrize("scenario", ("evnt_multi for a rectangle the mouse is in",
                                      "a press, then the mouse moves, in one idle",
                                      "evnt_button for the button up, Alt held",
                                      "evnt_multi for a rectangle the mouse is in, after a mouse wait was woken"))
@pytest.mark.parametrize("at", OVERLAPS.values(), ids=OVERLAPS)
def test_ev_rets_reads_each_word_where_the_rom_reads_it(scenario, at):
    arrival = evlib.at(scenario, EV_RETS)
    evlib.returning(EV_RETS, (at,), arrival.machine)


# ---- ev_mchk -------------------------------------------------------------------------------------------------------------------
MOWNER = aes.header_constants("wmupdate.h")["AES_GL_MOWNER"]


def checked(scenario, which=0):
    arrival = evlib.at(scenario, EV_MCHK, which)
    image = before(arrival)
    leave, x, y, width, height = struct.unpack_from(">5h", image, arrival.arguments[0])
    mouse_x, mouse_y = mouse(image)
    inside = x <= mouse_x < x + width and y <= mouse_y < y + height
    owns = case.long_in(image, MOWNER) == evasync.running(image)
    return evlib.run(arrival).answer(), owns, inside, leave


@pytest.mark.parametrize("scenario, which, came", (
    ("evnt_multi for a rectangle the mouse is in", 0, 1),                      # to enter it: in
    ("evnt_multi to leave a rectangle the mouse is not in", 0, 1),             # to leave it: out
    ("evnt_multi for two rectangles, the mouse where neither asks", 0, 0),     # to leave it: in
    ("evnt_multi for two rectangles, the mouse where neither asks", 1, 0),     # to enter it: out
    ("evnt_multi by the screen manager for a rectangle", 0, 0),                # the manager's mouse, to enter: out
    ("evnt_multi for the rectangle the mouse is in, the mouse the screen manager's", 0, 0),    # in, but another's
))
def test_ev_mchk_answers_whether_the_running_process_s_mouse_event_has_come(scenario, which, came):
    answer, owns, inside, leave = checked(scenario, which)
    assert answer == came == int(owns and inside != bool(leave))


def test_ev_mchk_of_a_process_that_does_not_own_the_mouse_never_comes():
    """PD0 running while the mouse is on the menu bar, the screen manager's: the mouse IS in the rectangle PD0 waits
    for it to enter, and the event has not come."""
    answer, owns, inside, leave = checked("evnt_multi for the rectangle the mouse is in, the mouse the screen manager's")
    assert not owns and inside and not leave and answer == 0


@pytest.mark.parametrize("leave, came", ((2, 1), (-1, 1), (0x100, 1)), ids=("2", "-1", "$100"))
def test_ev_mchk_compares_the_leave_flag_as_a_word(leave, came):
    """AN ARGUMENT-CLASS CASE (a MOBLK an application may hand): `cmp.w (a5),d0` — a flag that is neither 0 nor 1
    never equals `inside`'s answer, so the event has always come."""
    arrival = evlib.at("evnt_multi for a rectangle the mouse is in", EV_MCHK)
    for rect in (evlib.ROUND_THE_MOUSE, evlib.ELSEWHERE):
        machine = merge_pokes(arrival.machine, {evlib.MOBLK_AT: evlib.moblk(leave, *rect)})
        assert evlib.returning(EV_MCHK, (evlib.MOBLK_AT,), machine).answer() == came


def test_ev_mchk_compares_the_running_process_and_the_mouse_s_owner_as_longs():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (`rlr` with a top byte: no ROM run stores one): `cmp.l` — the same
    process on the bus is not the mouse's owner, and the event has not come."""
    arrival = evlib.at("evnt_multi for a rectangle the mouse is in", EV_MCHK)
    tagged = merge_pokes(arrival.machine, aes.field_pokes("AES", RLR=SHELL | aes.BUS_TAG))
    assert evlib.returning(EV_MCHK, arrival.arguments, tagged).answer() == 0


def test_ev_mchk_takes_its_moblk_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the MOBLK's pointer with a top byte."""
    arrival = evlib.at("evnt_multi for a rectangle the mouse is in", EV_MCHK)
    assert evlib.run(arrival, (arrival.arguments[0] | aes.BUS_TAG,)).answer() == 1


# ---- ev_dclick -----------------------------------------------------------------------------------------------------------------
DCINDEX, DCLICK = evlib.EVLIB["AES_GL_DCINDEX"], aes.AES_GL_DCLICK
DCLICK_MS = struct.unpack_from(f">{len(evlib.DCLICK_RATES)}h", BASE_IMAGE, evlib.EVLIB["AES_DCLICK_MS_TABLE"])


def test_the_double_click_table_is_the_rom_s_five_rates():
    assert DCLICK_MS == (450, 330, 275, 220, 165)


@pytest.mark.parametrize("rate", evlib.DCLICK_RATES)
def test_ev_dclick_sets_the_rate_and_the_ticks_a_click_stays_open(rate):
    arrival = evlib.at(f"evnt_dclick sets rate {rate}", EV_DCLICK)
    result = evlib.run(arrival)
    assert result.answer() == rate == case.word_in(result.final, DCINDEX)
    assert case.word_in(result.final, DCLICK) == DCLICK_MS[rate] // TICK_MS


def test_ev_dclick_asked_answers_the_rate_and_sets_nothing():
    arrival = evlib.at("evnt_dclick asks the rate", EV_DCLICK)
    image = before(arrival)
    result = evlib.run(arrival)
    assert result.answer() == case.word_in(image, DCINDEX) != arrival.arguments[0]
    assert case.word_in(result.final, DCLICK) == case.word_in(image, DCLICK)


@pytest.mark.parametrize("set_", (-1, 0x100, 2), ids=("-1", "$100", "2"))
def test_ev_dclick_sets_for_any_flag_that_is_not_zero(set_):
    """AN ARGUMENT-CLASS CASE: `tst.w 10(a6)` — the whole word."""
    result = evlib.returning(EV_DCLICK, (4, set_), evlib.desk_running())
    assert result.answer() == 4 and case.word_in(result.final, DCLICK) == DCLICK_MS[4] // TICK_MS


@pytest.mark.parametrize("rate", (-1, -2, 5, 6, 8), ids=lambda rate: str(rate))
def test_ev_dclick_with_a_rate_outside_the_table_reads_the_rom_round_it(rate):
    """AN ARGUMENT-CLASS CASE (a rate an application may hand: nothing bounds it) and A ROM FINDING: the rate is
    stored as handed and indexes the table as a SIGNED word — below it lie the last words of the AES's opcode table,
    above it four words of $ffff and the alert table — and whatever word is there, divided by the tick's
    milliseconds as a signed divide, becomes the click delay."""
    result = evlib.returning(EV_DCLICK, (rate, 1), evlib.desk_running())
    word, = struct.unpack_from(">h", BASE_IMAGE, evlib.EVLIB["AES_DCLICK_MS_TABLE"] + rate * aes.WORD_BYTES)
    assert result.answer() == rate and aes.signed(case.word_in(result.final, DCINDEX)) == rate
    assert aes.signed(case.word_in(result.final, DCLICK)) == int(word / TICK_MS)


# ---- the registry: Tier 3's rows ---------------------------------------------------------------------------------------
# Every RETURNING arrival of every scenario (the staged application's aside) was priced as a row would be; each
# routine's WORST is registered first, then its other shapes. Measured and left out, none any routine's worst:
# ev_block 0.56..0.70, ap_rdwr 0.56..0.69, ev_keybd 0.57, ev_button 0.55, ev_mouse 0.60, ev_mesag 0.60..0.69,
# ev_rets 0.88..0.91, ev_mchk 0.38..0.67, ev_dclick 0.40..0.81. A pipe's worst is the READ OF A FULL ONE — aqueue
# moves the seven messages behind the one taken — by a hair over the read that also serves a waiting writer.
# NO RETURNING ROW: ev_timer (a delay never returns without the dispatcher: its rows are the ones that switch, below).
SERVES_A_WRITER = evlib.SERVES_A_WRITER
A_FULL_PIPE = "appl_read of a full pipe"
ROWS = (
    ("a read of a full pipe", A_FULL_PIPE, EV_BLOCK, 0),
    ("a read that serves the process waiting to write", SERVES_A_WRITER, EV_BLOCK, 0),
    ("a mouse wait satisfied at once", "evnt_mouse to enter the rectangle the mouse is in", EV_BLOCK, 0),
    ("a key queued", "evnt_keybd, a key queued", EV_BLOCK, 0),
    ("a write into its own pipe", "appl_write to its own pipe", EV_BLOCK, 0),
    ("a read of a full pipe", A_FULL_PIPE, AP_RDWR, 0),
    ("a read that serves the process waiting to write", SERVES_A_WRITER, AP_RDWR, 0),
    ("a write that serves the process waiting to read", "appl_write to the parked desk", AP_RDWR, 0),
    ("a key queued", "evnt_keybd, a key queued", EV_KEYBD, 0),
    ("the button up, as waited for", "evnt_button for the button up, which is up", EV_BUTTON, 0),
    ("the button down, as waited for", "evnt_button for the button down, which is down", EV_BUTTON, 0),
    ("the mouse in the rectangle it is to enter", "evnt_mouse to enter the rectangle the mouse is in", EV_MOUSE, 0),
    ("the pipe full", "evnt_mesag, the pipe full", EV_MESAG, 0),
    ("two messages in the pipe", "evnt_mesag, two messages in the pipe", EV_MESAG, 0),
    ("a message in the pipe", "evnt_mesag, a message in the pipe", EV_MESAG, 0),
    ("the mouse where it is", "evnt_button for the button up, which is up", EV_RETS, 0),
    ("the mouse where the button changed", "a press, then the mouse moves, in one idle", EV_RETS, 0),
    ("the mouse in a rectangle it is to leave", "evnt_multi for every event", EV_MCHK, 0),
    ("the mouse where the wait asks", "evnt_multi for a rectangle the mouse is in", EV_MCHK, 0),
    ("the mouse another process's", "evnt_multi for the rectangle the mouse is in, the mouse the screen manager's",
     EV_MCHK, 0),
    ("a rate set", "evnt_dclick sets rate 0", EV_DCLICK, 0),
    ("the rate asked", "evnt_dclick asks the rate", EV_DCLICK, 0),
)
# ...and each routine through its call word: verified, unpriced.
THROUGH_LINE_F = {routine: next(row[1:] for row in ROWS if row[2] == routine) for routine in ROUTINES if routine != EV_TIMER}


evasync.register_rows(evlib.at, evlib.register, ROWS, THROUGH_LINE_F.values())


# ---- the registry: the rows THAT SWITCH -----------------------------------------------------------------------------------
# A WAIT BLOCKED AND WOKEN is one returning run through the dispatcher on both shores (`aes_switching`), and a priced
# row. Every blocked arrival's woken counterpart was priced as a row would be (`test_aes_evlib_woken.py` holds each at
# Tier 1); registered: ev_block under each of its seven codes (its key's and its delay's are the pilots',
# `test_aes_evdisp_model.py`), and each single wait's worst and its other shapes. Own ratios 0.62..0.71 (0.65..0.75
# with their thunks); the single waits are door users of ev_block's twin, held on two counts (the caller's own
# 0.31..0.78).
A_DOUBLE_CLICK, A_PRESS = "evnt_button for a double click", "evnt_button for a press"
LEAVING = "evnt_mouse to leave the rectangle the mouse is in"
THE_READ_WOKEN = "a read of its empty pipe, blocked; woken by the screen manager's own write (the menu chain)"
THE_WRITE_FREED = "the screen manager's write to the desk's full pipe, blocked; freed by the desk's own read"
THE_LOCK_WAITED_FOR = "a wait for the lock the screen manager's menu holds, blocked; handed it when the menu lets go"
THE_MANAGER_QUEUES_ITSELF = "a wait for a key, the lock the desk's; the screen manager queues itself on the lock; then Return"
THE_MANAGER_RUNS_WITH_THE_LOCK = "a wait for a key; the screen manager, handed the lock, runs with it; then Return"
# ev_timer DIVIDES its milliseconds by the tick's and DROPS THE REMAINDER: a tick and a half is one tick's wait — it
# runs out with the first tick, where two ticks' does not. (A time shorter than a tick is no time: the same run as
# the row above it, to the cycle — held at Tier 1 by `test_aes_evlib_woken.py`, not priced twice.)
THE_REMAINDER_DROPPED = "a time of a tick and a half, blocked; run out by ONE tick: the remainder is dropped"
A_TICK_AND_A_HALF_MS, HALF_A_TICK_MS = 3 * TICK_MS // 2, TICK_MS // 2
WOKEN_ROWS = evlib.register_woken((
    evlib.woken_at("a wait for a double click, blocked; woken by the two presses", A_DOUBLE_CLICK, EV_BLOCK),
    evlib.woken_at("a wait to leave a rectangle, blocked; woken by the mouse leaving it", LEAVING, EV_BLOCK),
    evlib.woken_at(THE_READ_WOKEN, "appl_read, none", EV_BLOCK),
    evlib.woken_over(THE_WRITE_FREED, EV_BLOCK, (evlib.WRITE, evlib.QPB_AT), evlib.the_manager_writing_to_a_full_pipe, {}),
    evlib.woken_over(THE_LOCK_WAITED_FOR, EV_BLOCK, (evlib.MUTEX, evlib.WIND_SPB), evlib.the_manager_s_menu_holds_the_lock,
                     evlib.THE_MENU_LET_GO),
    evlib.woken_over(THE_MANAGER_QUEUES_ITSELF, EV_BLOCK, evlib.A_KEY_S_WAIT, wm_update.locked, evlib.A_KEY_AFTER_THE_BAR),
    evlib.woken_over(THE_MANAGER_RUNS_WITH_THE_LOCK, EV_BLOCK, evlib.A_KEY_S_WAIT, evlib.the_manager_handed_the_lock,
                     {0: evlib.RETURN}),
    evlib.woken_at("no key queued, blocked; woken by Return", "evnt_keybd, none", EV_KEYBD),
    evlib.woken_at("a double click waited for, blocked; woken by the two presses", A_DOUBLE_CLICK, EV_BUTTON),
    evlib.woken_at("a press waited for, blocked; woken by it", A_PRESS, EV_BUTTON),
    evlib.woken_at("the mouse in the rectangle it is to leave, blocked; woken by its leaving", LEAVING, EV_MOUSE),
    evlib.woken_at("behind three delays pending, blocked; run out a delay at a time", evlib.BEHIND_THREE_DELAYS, EV_TIMER),
    evlib.woken_at("a time of five ticks, blocked; run out by them", "evnt_timer", EV_TIMER),
    evlib.woken_at("no time, blocked; run out by the next tick", "evnt_timer of no time", EV_TIMER),
    evlib.woken_over(THE_REMAINDER_DROPPED, EV_TIMER, (A_TICK_AND_A_HALF_MS,), evlib.desk_running, {0: evlib.ticks(1)}),
))
# ...and THE WAITS ON A PIPE, whose other end is ANOTHER PROCESS: the wake is a foreign window INSIDE their call of
# ev_block's twin — a door call open across it, the window taken off the call's cost on both shores.
THE_MESSAGE_WOKEN = "no message, blocked; woken by the screen manager's own write (the menu chain)"
WOKEN_ROWS.update(evlib.register_woken((
    evlib.woken_at(THE_MESSAGE_WOKEN, "evnt_mesag, none", EV_MESAG),
    evlib.woken_at(THE_READ_WOKEN, "appl_read, none", AP_RDWR),
    evlib.woken_over(THE_WRITE_FREED, AP_RDWR, evlib.THE_BLOCKED_WRITE, evlib.the_manager_writing_to_a_full_pipe, {}),
)))
