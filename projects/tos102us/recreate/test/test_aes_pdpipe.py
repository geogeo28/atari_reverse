"""PROCESSES AND THEIR PIPES (`src/aes/pdpipe.c`): the scheduler's process table and the message pipes, event-free.

    pd_match(name, pid, pd)      name: pd's eight name bytes copied to the frame, NUL-ended, streq(name, copy); no name:
                                 pd's id == pid
    fpdnm(name, pid)             the first of the three static PDs pd_match accepts, then of the accessories' PDs
                                 ($c6b2[0..$c682)); 0 for none
    getpd()                      $c680 < 3: static PD $c680, its id $c680, $c680++; else accessory PD $c6b2[$c682], its
                                 id $c682 + 3, $c682++; uda_insuper(its UDA); the PD
    uda_insuper(uda)             uda->insuper := 1                                                     (hand 68000)
    psetup(pd, pc)               under IPL 7 (SR parked in $8998): pc.l then $2000.w pushed on the stack pd's UDA
                                 saved, the saved pointer moved down                                   (hand 68000)
    pstart(pc, name, ldaddr)     getpd; its ldaddr; pd_nameit; psetup(pd, pc); its status ready; onto drl's head; the PD
    doq(write, pd, qpb)          write: qpb's bytes copied to the pipe's index; a WM_REDRAW for a window already queued
                                 is merged into that one (rc_union) and adds nothing, else the index moves past it.
                                 read: copied out from the pipe's head, the index less, the rest moved down
    aqueue(write, evb, qpb)      the pipe of fpdnm(0, qpb->pid) can serve it (room for a write, data for a read): doq,
                                 azombie(evb), and the FIRST wait at the other end served at once — NOCANCEL, off its
                                 list, doq of ITS qpb the other way, azombie; else evb->parm := qpb, evinsert at this
                                 end's wait list
    ap_find(name)                the name copied to the frame (lstcpy), fpdnm by it: its id, or -1; served up to eleven
                                 characters (the ROM's own boundary on a static process's stack), refused from twelve

EVERY MACHINE IS THE ROM's (`aes_pdpipe`): PD0 running or the screen manager running as the scheduler makes them, a
pipe as the ROM's own ap_rdwr fills and empties it, an event block as the ROM's iasync hands aqueue one, a writer
parked on a full pipe by its own blocking write. What a caller hands in — a name, a QPB, a message, a buffer — is
staged in the band. A THIRD process is `aes_pdpipe.STAGED_APPLICATION`: made by the ROM's pstart over a three-instruction
stub, every case over it labelled, Tier 1 only.

THE ACCESSORIES' ARMS of fpdnm and getpd (the PDs of `$c6b2[]`) need a loaded accessory — the loader's — and are not
pinned here; what IS pinned is where a machine without one ends: getpd with all three static PDs handed out.
"""
import functools
import inspect
import re
import struct
import sys

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_evasync
import aes_event
import aes_gsx as gsx
import aes_pdpipe as pp
import case
import routines
import transcription
from aes_pdpipe import (AP_FIND, AP_RDWR_READ, AP_RDWR_WRITE, APPLICATION_PID, AQUEUE, BUFFER_AT, DOQ, FPDNM, GETPD,
                        MESSAGE_AT, MESSAGE_BYTES, NAME_AT, PD_MATCH, PIPE_MESSAGES, PSETUP, PSTART, QPB_AT,
                        SCREEN_MANAGER_PID, SHELL_PID, SPARE_PD, STAGED_APPLICATION, STUB_AT, UDA_INSUPER)
from case import merge_pokes

THROUGH = gsx.THROUGH
SHELL, MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
PDPIPE = pp.PDPIPE
COMPLETE, NOCANCEL = aes_evasync.COMPLETE, aes_evasync.NOCANCEL
wait_list = aes_evasync.wait_list      # the EVBs a wait list links (EVB_LINK), in order, as the bus carries them
WRITE, READ = 1, 0                     # doq's `writing` word as iasync hands it ($fe4154 / $fe4160)
# What the attribution pass steers in a routine's run, first met first (`aes_pdpipe`'s reasons): pstart counts a PD
# out (getpd) before psetup pushes through its stack; aqueue's doq moves by the index before any list is stored
# through.
STARTING_STEERS = (pp.STEERS_THE_PD_COUNT, pp.STEERS_THE_STACK)
SERVING_STEERS = (pp.STEERS_THE_INDEX, pp.STEERS_THE_LISTS)
OVER_ITS_OWN_PD_STEERS = (pp.STEERS_THE_INDEX, pp.STEERS_THE_QUEUE_POINTER)    # a copy that lands on the PD's own fields
QUEUED_STEERS = pp.STEERS_THE_LISTS    # a wait queued: no byte moved, the index only compared
BLANK = b" " * aes.PD_NAME_BYTES       # a PD's name before anything names it: the shell's, the spare PD's
MANAGER_NAME = b"SCRENMGR"
APPLICATION_NAME = b"STAGED"
SPARE_UDA, SPARE_STACK_TOP = aes.AES_UDA2, aes.AES_UDA2_STACK_TOP
STALE_SLOTS = merge_pokes(aes.stale_host_slot("AES_PD_MATCH_NAME"), aes.stale_host_slot("AES_AP_FIND_NAME"))
TAG = aes.BUS_TAG


# ---- the machines ---------------------------------------------------------------------------------------------------------
def named(name, machine=None):
    """`machine` (PD0 running, by default) with `name` staged where a caller hands one in, the C's frames stale."""
    return merge_pokes(pp.running() if machine is None else machine, pp.name_pokes(name), STALE_SLOTS)


@functools.cache
def application():
    """THE staged application of this battery: one whose program is ev_mesag(BUFFER_AT) — a wait for a message."""
    return pp.staged_application("AES_ROM_EV_MESAG", BUFFER_AT, name=APPLICATION_NAME)


@functools.cache
def with_the_application():
    """PD0 running, the application made and not yet run (`aes_pdpipe.staged_application`)."""
    return merge_pokes(application().machine, STALE_SLOTS)


@functools.cache
def application_waiting():
    """PD0 running again, the application PARKED by its own program in its wait for a message: three processes, the
    third's EVB on its own pipe's readers' list."""
    return pp.resumed(pp.called(application()))


def pd_name(image, pd):
    return bytes(image[pd + aes.PD_NAME:pd + aes.PD_NAME + aes.PD_NAME_BYTES])


def pd_id(image, pd):
    return case.word_in(image, pd + aes.PD_PID)


def queue_index(image, pd=SHELL):
    return aes.signed(case.word_in(image, pd + aes.PD_QUEUE_INDEX))


def pipe(image, pd=SHELL, messages=PIPE_MESSAGES):
    at = pd + aes.PD_QUEUE
    return bytes(image[at:at + messages * MESSAGE_BYTES])


def flag(image, evb):
    return case.word_in(image, evb + aes.EVB_FLAG)


# ---- the machines are the scheduler's --------------------------------------------------------------------------------------
def test_the_snapshot_s_processes_are_what_these_cases_rely_on():
    """PD0 is named by eight blanks and PD1 SCRENMGR; the spare PD was never started: blank, its id still 0 — so by id
    or by name it is SHADOWED by PD0 until pstart numbers it — and two static PDs are counted, no accessory."""
    image = make_image(pp.running())
    assert [pd_name(image, pd) for pd in (SHELL, MANAGER, SPARE_PD)] == [BLANK, MANAGER_NAME, BLANK]
    assert [pd_id(image, pd) for pd in (SHELL, MANAGER, SPARE_PD)] == [SHELL_PID, SCREEN_MANAGER_PID, SHELL_PID]
    assert case.word_in(image, aes.AES_STATIC_PIDS) == pp.SNAPSHOT_STATIC_PIDS
    assert case.word_in(image, aes.AES_ACCESSORY_COUNT) == 0
    assert case.long_in(image, SPARE_PD + aes.PD_UDA) == SPARE_UDA
    assert case.long_in(image, SPARE_UDA + aes.UDA_SUPER_SP) == SPARE_STACK_TOP


def test_a_writer_waits_on_the_full_pipe_as_the_scheduler_parks_it():
    image = make_image(pp.writer_waiting())
    assert aes_event.scheduler_state(image, SHELL) == aes_event.running_as_switchto_leaves_it(SHELL)
    assert aes.list_of(image, aes.AES_NRL) == [MANAGER] and queue_index(image) == aes.PD_QUEUE_BYTES
    (waiting,) = wait_list(image, SHELL + aes.PD_QUEUE_WRITERS)
    assert case.long_in(image, waiting + aes.EVB_PD) == MANAGER and not wait_list(image, SHELL + aes.PD_QUEUE_READERS)


def test_an_evb_is_handed_to_aqueue_as_iasync_takes_it():
    """Stopped at aqueue's entry: the EVB off the free list and at the head of the running process's, its PD set, its
    flag clear — and the writing word iasync's arm pushes."""
    before = make_image(pp.running())
    handed = pp.at_aqueue(pp.running(), AP_RDWR_WRITE, SHELL_PID, MESSAGE_BYTES, MESSAGE_AT)
    image = make_image(handed.machine)
    assert handed.writing == WRITE and case.long_in(before, aes.AES_EUL) == handed.evb != case.long_in(image, aes.AES_EUL)
    assert case.long_in(image, SHELL + aes.PD_EVLIST) == handed.evb and case.long_in(image, handed.evb + aes.EVB_PD) == SHELL
    assert flag(image, handed.evb) == 0
    assert pp.at_aqueue(pp.holding(1), AP_RDWR_READ, SHELL_PID, MESSAGE_BYTES, BUFFER_AT).writing == READ


# ---- THE STAGED APPLICATION: the class, held to what it allows ---------------------------------------------------------------
def test_the_stub_is_three_instructions_one_of_them_a_line_f_call():
    """The whole program of `STAGED_APPLICATION`: a push of one immediate, the ROM's own call word, the jump to the
    oracle's sentinel — the bytes in the machine are exactly those, and nothing follows them."""
    made = application()
    program = pp.stub("AES_ROM_EV_MESAG", BUFFER_AT)
    assert pp.stub_instructions(program) == [("push", struct.pack(">I", BUFFER_AT)), ("call", addrs.AES_ROM_EV_MESAG),
                                             ("leave", emu.SENTINEL)]
    assert len(pp.stub_instructions(program)) == pp.STUB_INSTRUCTIONS
    image = make_image(made.machine)
    assert bytes(image[made.stub:made.stub + pp.STUB_BYTES]) == program.ljust(pp.STUB_BYTES, b"\0")
    assert pp.stub_instructions(pp.stub("AES_ROM_WM_UPDATE", 1))[0] == ("push", struct.pack(">H", 1))


CALL = struct.pack(">H", aes.line_f_call_word("AES_ROM_EV_MESAG"))
# The shape of a stub's call and none of ALLOWED_CALLS: forkq, which queues a routine by the POINTER it is handed.
NOT_ALLOWED = struct.pack(">H", aes.line_f_call_word("AES_ROM_FORKQ"))
ANOTHER_ADDRESS = addrs.VECTOR_LINE_F + aes.LONG_BYTES * 0x100     # a short absolute address that is not the sentinel
STORE_OF_ITS_OWN = bytes.fromhex("31c00400")           # move.w d0,($0400).w
LINE_F_RETURN = bytes.fromhex("f001")                  # a Line-F RETURN word: an odd one
PUSH = pp.pushed("AES_ROM_EV_MESAG", BUFFER_AT)        # ev_mesag's one argument: a long
A_WORD_PUSHED = pp.pushed("AES_ROM_WM_UPDATE", 1)       # ...and wm_update's: a word
LEAVE = pp.JMP_ABSOLUTE_SHORT + struct.pack(">H", emu.SENTINEL)
NOT_THE_CLASS = {
    "a second call": (PUSH + CALL + CALL + LEAVE, "the class allows"),
    "no push": (CALL + LEAVE, "the class allows"),
    "two pushes": (PUSH + PUSH + CALL + LEAVE, "the class allows"),
    "no call": (PUSH + LEAVE, "the class allows"),
    "a store of its own": (PUSH + CALL + STORE_OF_ITS_OWN + LEAVE, "not a push of an immediate"),
    "a Line-F return": (PUSH + CALL + LINE_F_RETURN + LEAVE, "a return, not a call"),
    "it runs on past the jump": (PUSH + CALL + LEAVE + PUSH, "the class allows"),
    "it leaves for another address": (PUSH + CALL + pp.JMP_ABSOLUTE_SHORT + struct.pack(">H", ANOTHER_ADDRESS), "another address"),
    "nothing": (b"", "the class allows"),
    "a call the class does not name": (PUSH + NOT_ALLOWED + LEAVE, "the class does not name"),
    "a word pushed for a routine's long": (A_WORD_PUSHED + CALL + LEAVE, "whose one argument is 4"),
}


@pytest.mark.parametrize("program, why", NOT_THE_CLASS.values(), ids=NOT_THE_CLASS)
def test_a_stub_that_is_anything_else_is_refused_by_name(program, why):
    with pytest.raises(AssertionError, match=why):
        pp.vet_the_stub(program)


def test_every_call_the_class_allows_is_a_stub_it_accepts():
    """...and each of ALLOWED_CALLS, with its reason, makes a stub the vet passes — the list is what `stub` builds."""
    for call, allowed in pp.ALLOWED_CALLS.items():
        assert allowed.why and pp.stub_instructions(pp.stub(call, 1))[1] == ("call", getattr(addrs, call))


ANOTHER_BUFFER = pp.LONG_WRITE_AT
FORGED = {       # the stub as a machine holds it, changed AFTER the application was made — and the refusal it meets
    "a second call laid behind the first": (lambda program: program[:-len(LEAVE)] + CALL + LEAVE, "the class allows"),
    "its call another routine's": (lambda program: program.replace(CALL, NOT_ALLOWED), "the class does not name"),
    "its call another ALLOWED routine's": (
        lambda program: program.replace(CALL, struct.pack(">H", aes.line_f_call_word("AES_ROM_EV_TIMER"))),
        "does not make the call its application names"),
    "its argument another buffer's": (lambda program: program.replace(PUSH, pp.pushed("AES_ROM_EV_MESAG", ANOTHER_BUFFER)),
                                      "does not push the argument its application names"),
    "its argument a word": (lambda program: program.replace(PUSH, A_WORD_PUSHED), "whose one argument is 4"),
    "bytes left behind its jump out": (lambda program: program + PUSH, "not the band's zeroes"),
}


def _the_dispatcher_run_to_its_aqueue(forged):
    """...the third road into an application's stub: the dispatcher's own loop, run until its program reaches aqueue."""
    return pp.at_aqueue_from_the_dispatcher(forged, aes_event.parked(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT,
                                                                     forged.machine))


ENTERED_BY = {"started": pp.started, "called": pp.called, "the dispatcher run to its aqueue": _the_dispatcher_run_to_its_aqueue}


@pytest.mark.parametrize("enter", ENTERED_BY.values(), ids=ENTERED_BY)
@pytest.mark.parametrize("forge, why", FORGED.values(), ids=FORGED)
def test_a_staged_application_is_vetted_where_it_is_entered_not_only_where_it_is_made(enter, forge, why):
    """THE VET IS AT EVERY USE — every road that runs the dispatcher into the stub: an `Application` whose machine was
    changed after its making — the stub's bytes as they LIE in the machine are no longer the class's, or no longer
    make the call the application names with the argument it names — is refused before the dispatcher enters it,
    each forge BY ITS OWN REASON."""
    made = application()
    program = pp.laid_stub(make_image(made.machine))
    forged = made._replace(machine=merge_pokes(made.machine, {STUB_AT: forge(program).ljust(pp.STUB_BYTES, b"\0")}))
    with pytest.raises(AssertionError, match=why):
        enter(forged)


def test_a_read_that_would_rewrite_a_staged_application_s_program_is_refused_by_name():
    """The stub lies directly behind the read buffer: a QPB reading more than the buffer holds there is refused where
    it is staged — and one that fills the buffer is not."""
    pp.qpb_pokes(SHELL_PID, pp.BUFFER_BYTES, BUFFER_AT)
    with pytest.raises(AssertionError, match="would rewrite its program"):
        pp.qpb_pokes(SHELL_PID, pp.BUFFER_BYTES + 1, BUFFER_AT | TAG)


def test_the_staged_application_is_what_the_rom_s_pstart_makes():
    """Made, not yet run: the spare PD named and numbered 2, ready, alone on the woken list; its UDA marked and its
    stack holding psetup's frame — the stub's address under SR $2000; PD0 still the one running. Outside the band,
    the machine differs from the one it started from EXACTLY where pstart's own run stored (its write ledger,
    `Application.stored`) and by exactly what it stored there: no byte more, none other."""
    made = application()
    image, before = make_image(made.machine), make_image(aes_event.machine())
    assert (made.pd, made.pid, made.stub) == (SPARE_PD, APPLICATION_PID, STUB_AT)
    assert pd_name(image, SPARE_PD) == APPLICATION_NAME.ljust(aes.PD_NAME_BYTES) and pd_id(image, SPARE_PD) == APPLICATION_PID
    assert aes.list_of(image, aes.AES_DRL) == [SPARE_PD] and aes.list_of(image, aes.AES_RLR) == [SHELL]
    frame = case.long_in(image, SPARE_UDA + aes.UDA_SUPER_SP)
    assert frame == SPARE_STACK_TOP - PDPIPE["PSETUP_FRAME_BYTES"]
    assert (case.word_in(image, frame), case.long_in(image, frame + aes.WORD_BYTES)) == (addrs.SR_SUPERVISOR, STUB_AT)
    assert case.word_in(image, SPARE_UDA + aes.UDA_IN_SUPER) == 1 and case.word_in(image, aes.AES_STATIC_PIDS) == 3
    band = range(pp.BAND_AT, pp.BAND_AT + pp.BAND_BYTES)
    changed = {at: image[at] for at in aes_event._differing_addresses(before, image) if at not in band}
    stored = {at + offset: value for at, data in made.stored.items() for offset, value in enumerate(data)}
    assert changed == {at: value for at, value in stored.items() if before[at] != value and at not in band}
    # ...and where that is, by name: the PD's own fields pstart and its callees set, psetup's frame, the UDA's mark and
    # saved pointer, the woken list, the count of static PDs, psetup's SR word and the Line-F mask word.
    fields = [(SPARE_PD + aes.PD_LINK, aes.LONG_BYTES), (SPARE_PD + aes.PD_NAME, aes.PD_NAME_BYTES),
              (SPARE_PD + aes.PD_LDADDR, aes.LONG_BYTES), (SPARE_PD + aes.PD_PID, aes.WORD_BYTES),
              (SPARE_PD + aes.PD_STAT, aes.WORD_BYTES), (frame, PDPIPE["PSETUP_FRAME_BYTES"]),
              (SPARE_UDA + aes.UDA_IN_SUPER, aes.WORD_BYTES), (SPARE_UDA + aes.UDA_SUPER_SP, aes.LONG_BYTES),
              (aes.AES_DRL, aes.LONG_BYTES), (aes.AES_STATIC_PIDS, aes.WORD_BYTES),
              (aes.AES_SR_PSETUP, aes.WORD_BYTES), (aes.AES_LINEF_MASK_WORD, aes.WORD_BYTES)]
    assert set(stored) - set(band) == {at for field, size in fields for at in range(field, field + size)}


def test_the_dispatcher_enters_the_staged_application_at_its_stub():
    """`started`: PD0 parked on a key wait, the application alone on the ready list and running, the guard cleared."""
    image = make_image(pp.started(application()))
    assert aes_event.scheduler_state(image, SPARE_PD) == aes_event.running_as_switchto_leaves_it(SPARE_PD)
    assert aes.list_of(image, aes.AES_NRL) == [SHELL, MANAGER] and not aes.list_of(image, aes.AES_DRL)


def test_the_staged_application_s_own_call_parks_it():
    """`called`, then `resumed`: its stub's ev_mesag found nothing in its pipe, so its EVB waits on its own pipe's
    readers' list; PD0, woken by a key, runs again."""
    image = make_image(application_waiting())
    assert aes.list_of(image, aes.AES_RLR) == [SHELL] and SPARE_PD in aes.list_of(image, aes.AES_NRL)
    (waiting,) = wait_list(image, SPARE_PD + aes.PD_QUEUE_READERS)
    assert case.long_in(image, waiting + aes.EVB_PD) == SPARE_PD


def test_called_is_the_dispatcher_s_own_run_carried_on_not_the_stub_entered_again():
    """THE PRINCIPLE: `called` is the run `started` is a prefix of. The QPB the application's wait names is the one
    iasync hands aqueue when the DISPATCHER'S OWN loop is run from the machine before `started` until the
    application's program reaches aqueue (`at_aqueue_from_the_dispatcher`): on the application's stack just below
    where switchto's `rte` left SP — above anything a call re-entered from the harness could lay (`aes_event.parked`
    lowers SP by PARKED_FRAME_ROOM first) — and it holds what the stub asked for."""
    made = application()
    parked_maker = aes_event.parked(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT, made.machine)
    by_the_dispatcher = pp.at_aqueue_from_the_dispatcher(made, parked_maker)
    called = make_image(pp.called(made))
    (waiting,) = wait_list(called, SPARE_PD + aes.PD_QUEUE_READERS)
    qpb_at = case.long_in(called, waiting + aes.EVB_PARM)
    assert qpb_at == by_the_dispatcher.qpb and SPARE_STACK_TOP - aes_event.PARKED_FRAME_ROOM < qpb_at < SPARE_STACK_TOP
    assert bytes(called[qpb_at:qpb_at + PDPIPE["QPB_BYTES"]]) == struct.pack(">hhI", APPLICATION_PID, MESSAGE_BYTES, BUFFER_AT)
    assert aes.list_of(called, aes.AES_RLR) == [] and {SHELL, MANAGER, SPARE_PD} <= set(aes.list_of(called, aes.AES_NRL))


# ---- pd_match --------------------------------------------------------------------------------------------------------------------
BY_NAME = {     # (the name looked for, the PD, whether it is that PD's)
    "the screen manager's": (MANAGER_NAME, MANAGER, 1),
    "the screen manager's, of the shell": (MANAGER_NAME, SHELL, 0),
    "eight blanks, the shell's": (BLANK, SHELL, 1),
    "eight blanks, of the screen manager": (BLANK, MANAGER, 0),
    "one character short": (MANAGER_NAME[:-1], MANAGER, 0),
    "one character long": (MANAGER_NAME + b"X", MANAGER, 0),
    "its last character another": (MANAGER_NAME[:-1] + b"S", MANAGER, 0),
    "its first character another": (b"T" + MANAGER_NAME[1:], MANAGER, 0),
    "no character at all": (b"", SHELL, 0),
}


@pytest.mark.parametrize("name, pd, matched", BY_NAME.values(), ids=BY_NAME)
def test_pd_match_by_name(name, pd, matched):
    result = pp.run(PD_MATCH, (NAME_AT, SHELL_PID, pd), named(name))
    assert result.answer() == matched


BY_ID = {"the shell's": (SHELL_PID, SHELL, 1), "the shell's, of the screen manager": (SHELL_PID, MANAGER, 0),
         "the screen manager's": (SCREEN_MANAGER_PID, MANAGER, 1), "the screen manager's, of the shell": (SCREEN_MANAGER_PID, SHELL, 0),
         "the spare PD's, still 0": (SHELL_PID, SPARE_PD, 1), "no process's": (-1, SHELL, 0)}


@pytest.mark.parametrize("pid, pd, matched", BY_ID.values(), ids=BY_ID)
def test_pd_match_by_id(pid, pd, matched):
    result = pp.run(PD_MATCH, (PDPIPE["FPDNM_BY_PID"], pid, pd), named(MANAGER_NAME))
    assert result.answer() == matched


def test_pd_match_by_name_never_looks_at_the_id():
    """A name AND the PD's own id handed in: the name decides."""
    assert pp.run(PD_MATCH, (NAME_AT, SCREEN_MANAGER_PID, MANAGER), named(BLANK)).answer() == 0


def test_pd_match_puts_its_pointers_on_the_bus():
    assert pp.run(PD_MATCH, (NAME_AT | TAG, SHELL_PID, MANAGER | TAG), named(MANAGER_NAME)).answer() == 1
    assert pp.run(PD_MATCH, (PDPIPE["FPDNM_BY_PID"], SCREEN_MANAGER_PID, MANAGER | TAG), named(BLANK)).answer() == 1


def test_pd_match_of_a_pd_s_own_name_bytes():
    """The name handed in IS the PD's name field: eight bytes with no NUL of their own — ended by the top byte of the
    CDA pointer after them, a 0 on a 24-bit machine — against the frame's copy of the same eight."""
    assert pp.run(PD_MATCH, (MANAGER + aes.PD_NAME, SHELL_PID, MANAGER), named(BLANK)).answer() == 1


NINE_BEFORE_THE_DOT = b"ABCDEFGHI.PRG"


def test_pd_match_compares_its_own_copy_of_the_name_not_the_pd_s_bytes():
    """`STAGED_APPLICATION`, named by NINE characters before its dot: pd_nameit puts the ninth on the top byte of the
    PD's CDA pointer (`test_aes_mnlib`), so the PD's eight name bytes are followed by an `I`, not a NUL. pd_match
    copies eight and ends them itself: the eight-character name still matches."""
    made = pp.staged_application("AES_ROM_EV_MESAG", BUFFER_AT, name=NINE_BEFORE_THE_DOT)
    image = make_image(made.machine)
    assert image[SPARE_PD + aes.PD_CDA] == NINE_BEFORE_THE_DOT[aes.PD_NAME_BYTES]
    machine = named(NINE_BEFORE_THE_DOT[:aes.PD_NAME_BYTES], merge_pokes(made.machine, STALE_SLOTS))
    assert pp.run(PD_MATCH, (NAME_AT, SHELL_PID, SPARE_PD), machine).answer() == 1
    assert pp.run(AP_FIND, (NAME_AT,), machine).answer() == APPLICATION_PID


@THROUGH
def test_pd_match_through_its_callers_word(through_line_f):
    assert pp.run(PD_MATCH, (NAME_AT, SHELL_PID, MANAGER), named(MANAGER_NAME), through_line_f=through_line_f).answer() == 1


# ---- fpdnm -----------------------------------------------------------------------------------------------------------------------
FOUND = {       # (name or None, pid, the PD found over the snapshot's two processes)
    "the shell by its id": (None, SHELL_PID, SHELL),
    "the screen manager by its id": (None, SCREEN_MANAGER_PID, MANAGER),
    "id 2 before anything was started: none": (None, APPLICATION_PID, 0),
    "a negative id: none": (None, -1, 0),
    "the screen manager by its name": (MANAGER_NAME, SHELL_PID, MANAGER),
    "eight blanks: the shell, before the spare PD": (BLANK, SHELL_PID, SHELL),
    "a name no process has": (b"NOSUCH  ", SHELL_PID, 0),
}


def fpdnm(name, pid, machine=None, tag=0):
    staged = named(name or MANAGER_NAME, machine)
    return pp.run(FPDNM, ((NAME_AT | tag) if name is not None else PDPIPE["FPDNM_BY_PID"], pid), staged)


@pytest.mark.parametrize("name, pid, found", FOUND.values(), ids=FOUND)
def test_fpdnm(name, pid, found):
    assert fpdnm(name, pid).long_answer() == found


def test_fpdnm_puts_the_name_on_the_bus():
    assert fpdnm(MANAGER_NAME, SHELL_PID, tag=TAG).long_answer() == MANAGER


@THROUGH
def test_fpdnm_through_its_callers_word(through_line_f):
    result = pp.run(FPDNM, (PDPIPE["FPDNM_BY_PID"], SCREEN_MANAGER_PID), named(BLANK), through_line_f=through_line_f)
    assert result.long_answer() == MANAGER


THIRD = {"by its id": (None, APPLICATION_PID, SPARE_PD), "by its name": (APPLICATION_NAME.ljust(aes.PD_NAME_BYTES), 0, SPARE_PD),
         "by its name unpadded: none": (APPLICATION_NAME, 0, 0), "id 3: none": (None, APPLICATION_PID + 1, 0),
         "the shell still first by its id": (None, SHELL_PID, SHELL)}


@pytest.mark.parametrize("name, pid, found", THIRD.values(), ids=[f"{STAGED_APPLICATION}, {label}" for label in THIRD])
def test_fpdnm_finds_a_third_process(name, pid, found):
    """Past two PDs to the third (`STAGED_APPLICATION`): the walk crosses every static PD."""
    assert fpdnm(name, pid, with_the_application()).long_answer() == found


# ---- uda_insuper, getpd ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("uda", (SPARE_UDA, aes.AES_THEGLO, aes.AES_UDA1, SPARE_UDA | TAG),
                         ids=("the spare UDA", "the shell's", "the screen manager's, set already", "on the bus"))
def test_uda_insuper(uda):
    result = pp.run(UDA_INSUPER, (uda,), pp.running())
    assert result.word((uda & ~TAG) + aes.UDA_IN_SUPER) == 1


@THROUGH
def test_uda_insuper_through_its_callers_word(through_line_f):
    pp.run(UDA_INSUPER, (SPARE_UDA,), pp.running(), through_line_f=through_line_f)


@THROUGH
def test_getpd_hands_out_the_spare_static_pd(through_line_f):
    result = pp.run(GETPD, (), pp.running(), through_line_f=through_line_f)
    assert result.long_answer() == SPARE_PD and pd_id(result.final, SPARE_PD) == APPLICATION_PID
    assert result.word(aes.AES_STATIC_PIDS) == aes.AES_PD_COUNT and result.word(aes.AES_ACCESSORY_COUNT) == 0
    assert result.word(SPARE_UDA + aes.UDA_IN_SUPER) == 1


ABOVE_RAM = "a store at or above the top of RAM"
NO_PD = 0                              # what the accessories' table holds for an accessory never loaded


@pytest.mark.parametrize("name, arguments", ((GETPD, ()), (PSTART, (STUB_AT, NAME_AT, 0))), ids=("getpd", "pstart"))
def test_no_pd_is_left_after_the_three_static_ones_without_an_accessory(name, arguments):
    """`STAGED_APPLICATION`'s machine has handed out all three static PDs, and no accessory was loaded: the
    accessories' table holds no PD, and the ROM takes address 0 for one — its id (the first accessory's, 3) stored in
    the vector page, the accessories counted one more, its "UDA" the bus-error vector's ROM address, where
    uda_insuper's store is lost. The host refuses that store by name, having stored what the ROM stores before it
    (the accessories' arm proper is the loader's, not pinned here)."""
    machine = named(b"FOURTH", with_the_application())
    returncode, stderr, image = pp.refused_leaving(name, arguments, machine)
    assert returncode != 0 and ABOVE_RAM in stderr, stderr
    assert case.word_in(image, NO_PD + aes.PD_PID) == aes.AES_PD_COUNT and case.word_in(image, aes.AES_ACCESSORY_COUNT) == 1
    assert case.word_in(image, aes.AES_STATIC_PIDS) == aes.AES_PD_COUNT
    with pytest.raises(AssertionError, match="into the ROM window"):
        emu.run(make_image(aes.staged(name, arguments, machine)), getattr(addrs, name))


# ---- psetup, pstart ----------------------------------------------------------------------------------------------------------------
def frame_on(image, uda):
    """The frame on top of the stack `uda` saved: (where, its SR word, its PC)."""
    at = case.long_in(image, uda + aes.UDA_SUPER_SP)
    return at, case.word_in(image, at), case.long_in(image, at + aes.WORD_BYTES)


CODE = 0x00FE49D2                      # a first PC: the screen manager's own (PD1's ldaddr in the snapshot)


@pytest.mark.parametrize("pd, pc", ((SPARE_PD, CODE), (SPARE_PD | TAG, CODE), (SPARE_PD, CODE | TAG)),
                         ids=("the spare PD", "the PD on the bus", "a PC with a top byte, stored whole"))
def test_psetup_pushes_the_frame_switchto_pops(pd, pc):
    result = pp.run(PSETUP, (pd, pc), pp.running(), steered=pp.STEERS_THE_STACK)
    assert frame_on(result.final, SPARE_UDA) == (SPARE_STACK_TOP - PDPIPE["PSETUP_FRAME_BYTES"], addrs.SR_SUPERVISOR, pc)


def test_psetup_stores_the_stack_pointer_back_top_byte_and_all():
    """The saved pointer is loaded once and stored back as it is: the screen manager's, staged with a top byte the
    bus drops — a PD parked by the scheduler, so not a caller's own sequence, but the pointer's width is the
    routine's."""
    machine = merge_pokes(pp.running(), aes.field_pokes("UDA", aes.AES_UDA1, SUPER_SP=case.long_in(
        make_image(pp.running()), aes.AES_UDA1 + aes.UDA_SUPER_SP) | TAG))
    before = case.long_in(make_image(machine), aes.AES_UDA1 + aes.UDA_SUPER_SP)
    result = pp.run(PSETUP, (MANAGER, CODE), machine, steered=pp.STEERS_THE_STACK)
    assert result.long(aes.AES_UDA1 + aes.UDA_SUPER_SP) == before - PDPIPE["PSETUP_FRAME_BYTES"] and before & TAG


def test_psetup_pushes_a_second_frame_under_the_first():
    """Over `STAGED_APPLICATION`'s PD, which pstart's psetup already pushed one frame for."""
    first = frame_on(make_image(with_the_application()), SPARE_UDA)
    result = pp.run(PSETUP, (SPARE_PD, CODE), with_the_application(), steered=pp.STEERS_THE_STACK)
    assert frame_on(result.final, SPARE_UDA) == (first[0] - PDPIPE["PSETUP_FRAME_BYTES"], addrs.SR_SUPERVISOR, CODE)
    assert result.after(first[0], PDPIPE["PSETUP_FRAME_BYTES"]) == struct.pack(">HI", *first[1:])


def test_psetup_of_a_pd_on_the_bus_returns_in_a_child():
    """...in a child process too: a PD's top byte taken for an address is a read past the host's image, which ends a
    process rather than failing a case."""
    returncode, stderr = pp.refused(PSETUP, (SPARE_PD | TAG, CODE), pp.running())
    assert returncode == 0, stderr


@THROUGH
def test_psetup_through_its_callers_word(through_line_f):
    pp.run(PSETUP, (SPARE_PD, CODE), pp.running(), through_line_f=through_line_f, steered=pp.STEERS_THE_STACK)


DIFFERS_AT = re.compile(r"\(0x([0-9a-f]+)\): oracle=")     # a differential's refusal: one line per differing address


def test_psetup_s_sr_save_word_is_all_that_is_dropped():
    """The ROM parks its caller's SR in $8998 and the C stores nothing there: with the drop taken away the run differs
    at that word AND NOWHERE ELSE — every address the differential names lies in it."""
    with pytest.raises(AssertionError) as differed:
        pp.run(PSETUP, (SPARE_PD, CODE), pp.running(), dropped_windows=aes.LINE_F_MASK_WINDOW, steered=pp.STEERS_THE_STACK)
    named = {int(at, 16) for at in DIFFERS_AT.findall(str(differed.value))}
    assert named and named <= set(range(aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + aes.WORD_BYTES)), str(differed.value)


A_LOAD_ADDRESS = 0x000A1B2C            # any address of the machine's RAM: pstart stores it and reads nothing through it
STARTS = {      # (name, the PD's name after, its load address, the code's and the name's tags)
    "a program's file": (b"CONTROL.ACC", b"CONTROL ", 0, 0, 0),
    "no extension": (b"THIRD", b"THIRD   ", 0, 0, 0),
    "eight characters, a load address": (b"ABCDEFGH", b"ABCDEFGH", A_LOAD_ADDRESS, 0, 0),
    "the name on the bus": (b"TAGGED.PRG", b"TAGGED  ", 0, 0, TAG),
    "a PC with a top byte, pushed whole": (b"THIRD", b"THIRD   ", A_LOAD_ADDRESS | TAG, TAG, 0),
}


@pytest.mark.parametrize("name, after, load_address, code_tag, name_tag", STARTS.values(), ids=STARTS)
def test_pstart(name, after, load_address, code_tag, name_tag):
    result = pp.run(PSTART, (STUB_AT | code_tag, NAME_AT | name_tag, load_address), named(name), steered=STARTING_STEERS)
    image = result.final
    assert result.long_answer() == SPARE_PD and pd_name(image, SPARE_PD) == after and pd_id(image, SPARE_PD) == APPLICATION_PID
    assert case.long_in(image, SPARE_PD + aes.PD_LDADDR) == load_address
    assert case.word_in(image, SPARE_PD + aes.PD_STAT) == aes.PD_STAT_READY
    assert frame_on(image, SPARE_UDA) == (SPARE_STACK_TOP - PDPIPE["PSETUP_FRAME_BYTES"], addrs.SR_SUPERVISOR, STUB_AT | code_tag)
    assert aes.list_of(image, aes.AES_DRL) == [SPARE_PD] and aes.list_of(image, aes.AES_RLR) == [SHELL]


def woken_shell():
    """The screen manager running, PD0 already WOKEN and on the woken list: its message wait was handed a message."""
    return pp.sent(pp.screen_manager_running(), SHELL_PID, pp.numbered(1)[0])


def test_pstart_puts_the_new_process_before_the_ones_already_woken():
    assert aes.list_of(make_image(woken_shell()), aes.AES_DRL) == [SHELL]
    result = pp.run(PSTART, (STUB_AT, NAME_AT, 0), named(b"THIRD", woken_shell()), steered=STARTING_STEERS)
    assert aes.list_of(result.final, aes.AES_DRL) == [SPARE_PD, SHELL]


@THROUGH
def test_pstart_through_its_callers_word(through_line_f):
    pp.run(PSTART, (STUB_AT, NAME_AT, 0), named(b"THIRD"), through_line_f=through_line_f, steered=STARTING_STEERS)


# ---- doq: a write --------------------------------------------------------------------------------------------------------------
PLAIN_TYPE, LONG_TYPE = 0x33, 0x34      # two types no library sends: neither a redraw
PLAIN = pp.message(PLAIN_TYPE, 7, -7, 0x1234, 0x7FFF, -0x8000)


def qpb(count, buffer, pid=SHELL_PID):
    return pp.qpb_pokes(pid, count, buffer)


def to_write(machine, sending, buffer=MESSAGE_AT, pid=SHELL_PID):
    """`machine` with `sending` staged where a write hands it in, and the QPB writing it from `buffer`."""
    return merge_pokes(machine, {MESSAGE_AT: sending}, qpb(len(sending), buffer, pid))


def write(machine, sending, pd=SHELL, qpb_at=QPB_AT, buffer=MESSAGE_AT, writing=WRITE, pid=SHELL_PID, **kwargs):
    """The ROM's doq writing `sending` into `pd`'s pipe, against the C — poisoned unless the case says `steered=`."""
    return pp.run(DOQ, (writing, pd, qpb_at), to_write(machine, sending, buffer, pid), **kwargs)


@pytest.mark.parametrize("held", (0, 1, 3, PIPE_MESSAGES - 1))
def test_doq_writes_a_message_behind_those_held(held):
    before = pipe(make_image(pp.holding(held)), messages=held)
    result = write(pp.holding(held), PLAIN, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == (held + 1) * MESSAGE_BYTES
    assert pipe(result.final, messages=held + 1) == before + PLAIN


TAIL_FIRST_BYTE = 0x40                 # a long message's sixteen bytes past its header: a ramp from here


def test_doq_writes_as_many_bytes_as_the_qpb_counts():
    long_message = pp.message(LONG_TYPE, 1, 2, 3, 4, 5, extra=MESSAGE_BYTES) + bytes(range(TAIL_FIRST_BYTE, TAIL_FIRST_BYTE + MESSAGE_BYTES))
    result = write(pp.holding(1), long_message, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 3 * MESSAGE_BYTES and pipe(result.final, messages=3)[MESSAGE_BYTES:] == long_message


HIGH_BYTE_ALONE = 0x0100               # a writing word whose low byte is 0: the test is of the word


def test_doq_takes_any_nonzero_word_for_a_write():
    assert queue_index(write(pp.holding(1), PLAIN, writing=HIGH_BYTE_ALONE, steered=pp.STEERS_THE_INDEX).final) == 2 * MESSAGE_BYTES


def test_doq_puts_its_pointers_on_the_bus():
    result = write(pp.holding(1), PLAIN, pd=SHELL | TAG, qpb_at=QPB_AT | TAG, buffer=MESSAGE_AT | TAG, steered=pp.STEERS_THE_INDEX)
    assert pipe(result.final, messages=2)[MESSAGE_BYTES:] == PLAIN


WINDOW, OTHER_WINDOW = 3, 4
FIRST_RECT, SECOND_RECT, BOTH = (40, 50, 100, 60), (20, 80, 60, 90), (20, 50, 120, 120)


def redraws_held(*queued):
    """PD0 running, its pipe holding `queued` — each written by the ROM's own ap_rdwr."""
    return pp.sent(pp.running(), SHELL_PID, *queued)


def test_doq_merges_a_redraw_into_the_one_queued_for_its_window():
    """Two messages ahead of it, the first a redraw for ANOTHER window: the walk crosses both, the third's rectangle
    becomes the union and the pipe grows by nothing — the written bytes left beyond the index."""
    machine = redraws_held(pp.redraw(OTHER_WINDOW, *FIRST_RECT), PLAIN, pp.redraw(WINDOW, *FIRST_RECT))
    result = write(machine, pp.redraw(WINDOW, *SECOND_RECT), steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 3 * MESSAGE_BYTES
    held = pipe(result.final, messages=4)
    assert held[2 * MESSAGE_BYTES:3 * MESSAGE_BYTES] == pp.redraw(WINDOW, *BOTH)
    assert held[:MESSAGE_BYTES] == pp.redraw(OTHER_WINDOW, *FIRST_RECT) and held[3 * MESSAGE_BYTES:] == pp.redraw(WINDOW, *SECOND_RECT)


def test_doq_merges_into_the_first_of_two_queued_for_the_window():
    """Two for the window already queued (the second written while the first... was not there to merge with: a plain
    message between them of the same bytes cannot happen, so the pipe is made with another window's handle and then
    holds both by the walk's own rule): only the FIRST is widened."""
    machine = redraws_held(pp.redraw(WINDOW, *FIRST_RECT), pp.redraw(OTHER_WINDOW, *FIRST_RECT))
    result = write(machine, pp.redraw(WINDOW, *SECOND_RECT), steered=pp.STEERS_THE_INDEX)
    held = pipe(result.final, messages=2)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES
    assert held == pp.redraw(WINDOW, *BOTH) + pp.redraw(OTHER_WINDOW, *FIRST_RECT)


@pytest.mark.parametrize("queued", ((), (PLAIN,), (pp.redraw(OTHER_WINDOW, *FIRST_RECT),),
                                    (pp.message(PLAIN_TYPE, WINDOW, *FIRST_RECT),)),
                         ids=("an empty pipe", "none queued", "one for another window", "another message of its window"))
def test_doq_appends_a_redraw_with_none_to_merge_into(queued):
    result = write(redraws_held(*queued), pp.redraw(WINDOW, *SECOND_RECT), steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == (len(queued) + 1) * MESSAGE_BYTES
    assert pipe(result.final, messages=len(queued) + 1) == b"".join(queued) + pp.redraw(WINDOW, *SECOND_RECT)


def test_doq_s_walk_ends_at_the_merge_in_a_child():
    """FIRST of the merges, in a child under its alarm (a merge is a few hundred host instructions): the walk stops at
    the redraw it merges into (its count of bytes to add, zeroed there, is the loop's other condition) — a walk that
    went on would not move, and in process would hang the suite rather than fail a case."""
    machine = merge_pokes(redraws_held(pp.redraw(WINDOW, *FIRST_RECT), PLAIN), {MESSAGE_AT: pp.redraw(WINDOW, *SECOND_RECT)},
                          qpb(MESSAGE_BYTES, MESSAGE_AT))
    returncode, stderr = pp.refused(DOQ, (WRITE, SHELL, QPB_AT), machine)
    assert returncode == 0, stderr


def test_doq_merges_redraws_only():
    """A message of ANOTHER type whose fourth word is the handle of a redraw queued: appended."""
    other = pp.message(PLAIN_TYPE, WINDOW, *SECOND_RECT)
    result = write(redraws_held(pp.redraw(WINDOW, *FIRST_RECT)), other, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES
    assert pipe(result.final, messages=2) == pp.redraw(WINDOW, *FIRST_RECT) + other


def test_doq_steps_over_a_long_message_by_its_own_length():
    """A queued message of 32 bytes (its third word counts the 16 past the header) whose TAIL reads as a redraw for the
    window: the walk steps over all 32, so the merge is into the real one behind it, not into that tail."""
    decoy = pp.redraw(WINDOW, 1, 1, 2, 2)
    long_message = pp.message(LONG_TYPE, 1, 2, 3, 4, 5, extra=MESSAGE_BYTES) + decoy
    machine = redraws_held(long_message, pp.redraw(WINDOW, *FIRST_RECT))
    result = write(machine, pp.redraw(WINDOW, *SECOND_RECT), steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 3 * MESSAGE_BYTES
    assert pipe(result.final, messages=3) == long_message + pp.redraw(WINDOW, *BOTH)


def test_doq_reads_the_message_back_where_the_pd_holds_its_pipe():
    """THE ORDER, as an overlap: the QPB's buffer is the pipe's own head, so the bytes written are the first queued
    message again — a redraw for the window, which merges into the one it was copied from."""
    machine = redraws_held(pp.redraw(WINDOW, *FIRST_RECT), PLAIN)
    staged = merge_pokes(machine, qpb(MESSAGE_BYTES, SHELL + aes.PD_QUEUE))
    result = pp.run(DOQ, (WRITE, SHELL, QPB_AT), staged, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES and pipe(result.final, messages=1) == pp.redraw(WINDOW, *FIRST_RECT)


@THROUGH
def test_doq_through_its_callers_word(through_line_f):
    result = pp.run(DOQ, (WRITE, SHELL, QPB_AT), merge_pokes(redraws_held(pp.redraw(WINDOW, *FIRST_RECT)),
                                                         {MESSAGE_AT: pp.redraw(WINDOW, *SECOND_RECT)},
                                                         qpb(MESSAGE_BYTES, MESSAGE_AT)), through_line_f=through_line_f,
                    steered=pp.STEERS_THE_INDEX)
    assert pipe(result.final, messages=1) == pp.redraw(WINDOW, *BOTH)


# ---- doq: an ODD index ---------------------------------------------------------------------------------------------------------
def behind_one_byte():
    """PD0 running, ONE BYTE in its pipe (the ROM's own appl_write of one — aqueue's room edge above), and a QPB
    writing a message behind it: the index is odd."""
    one_byte = pp.sent(pp.running(), SHELL_PID, PLAIN[:1])
    assert queue_index(make_image(one_byte)) == 1
    return merge_pokes(one_byte, {MESSAGE_AT: PLAIN}, qpb(MESSAGE_BYTES, MESSAGE_AT))


ODD_ADDRESS = "a word or longword at an odd address"
ODD_TYPE_AT = SHELL + aes.PD_QUEUE + 1                  # the "message" doq reads back behind one byte: its type word
AES_ROM_DOQ_TYPE_READ = addrs.AES_ROM_DOQ + 0x46        # $fe5906 `cmpi.w #20,(a3)`: the message's type, a word read


def test_a_write_behind_a_one_byte_message_is_an_address_error_on_every_shore(monkeypatch):
    """ROM DEFECT: a message of ONE byte leaves the pipe's index odd, and the next write reads its message's type back
    as a WORD at an odd address ($fe5906) — the 68000's address error, on the machine: three bombs. THE SHORES AGREE
    BY NAME. The oracle takes no address error: the ROM's run goes on, and its ledger names the one odd access. The
    HOST C halts there by the accessors' name (a child). The TARGET build makes the SAME odd access — one, at the same
    address — and is the ROM's image and registers besides (the bench's second differential, whose odd-access surface
    is recorded here): on a 68000 it faults where the ROM faults.

    WHAT THIS CASE COSTS RUN ALONE, and why it is left so: the bench's second differential IS a Tier 3 measurement,
    and Tier 3's module reads every battery's rows — alone, this case pays that whole import (half a minute); in the
    suite nothing, every worker having collected `test_tier3.py`. A cheaper measurement would be another instrument
    than the one the row's claim is about."""
    arguments, machine = (WRITE, SHELL, QPB_AT), behind_one_byte()
    returncode, stderr = pp.refused(DOQ, arguments, machine)
    assert returncode != 0 and ODD_ADDRESS in stderr, stderr
    final, _writes, _regs = emu.run(make_image(aes.staged(DOQ, arguments, machine)), addrs.AES_ROM_DOQ)
    the_rom_s = emu.odd_accesses()
    assert queue_index(final) == 1 + MESSAGE_BYTES
    assert (the_rom_s["odd_accesses"], the_rom_s["odd_addresses"], the_rom_s["odd_first_pc"]) == (
        1, (ODD_TYPE_AT,), AES_ROM_DOQ_TYPE_READ)
    measured, vet = [], rom_bench._vet_no_odd_access

    def recorded(symbol, ours, original):
        measured.append((ours["odd_accesses"], ours["odd_addresses"], original["odd_accesses"], original["odd_addresses"]))
        return vet(symbol, ours, original)
    monkeypatch.setattr(rom_bench, "_vet_no_odd_access", recorded)
    aes_event.bench_differential(DOQ, arguments, machine, {})
    # A sweep of HOST mutants stubs the bench out (the blob is not the mutant's): nothing is measured there, by name.
    assert measured or aes_event.bench_differential.__name__ != "bench_differential", "the bench measured no run"
    assert all(one == (1, (ODD_TYPE_AT,), 1, (ODD_TYPE_AT,)) for one in measured), measured


# ---- doq: a read ---------------------------------------------------------------------------------------------------------------
def read(machine, count=MESSAGE_BYTES, pd=SHELL, qpb_at=QPB_AT, buffer=BUFFER_AT, **kwargs):
    """The ROM's doq reading `count` bytes out of `pd`'s pipe, against the C — poisoned unless the case says
    `steered=`."""
    return pp.run(DOQ, (READ, pd, qpb_at), merge_pokes(machine, qpb(count, buffer)), **kwargs)


@pytest.mark.parametrize("held, count", ((1, MESSAGE_BYTES), (3, MESSAGE_BYTES), (3, 2 * MESSAGE_BYTES),
                                         (PIPE_MESSAGES, MESSAGE_BYTES), (2, MESSAGE_BYTES // 2), (2, 0)),
                         ids=("the only message", "one of three", "two of three", "one of a full pipe", "half a message",
                              "no byte"))
def test_doq_reads_from_the_head_and_moves_the_rest_down(held, count):
    before = pipe(make_image(pp.holding(held)), messages=held)
    result = read(pp.holding(held), count, steered=pp.STEERS_THE_INDEX)
    assert result.after(BUFFER_AT, count) == before[:count] and result.after(BUFFER_AT + count, 1)[0] == case.SLACK_FILL
    assert queue_index(result.final) == len(before) - count
    assert pipe(result.final, messages=held)[:len(before) - count] == before[count:]


def whole_pipe_read():
    """PD0 running over its FULL pipe, a QPB reading all 128 bytes of it at once."""
    return merge_pokes(pp.holding(PIPE_MESSAGES), {pp.LONG_WRITE_AT: bytes([case.SLACK_FILL]) * pp.LONG_WRITE_BYTES},
                       qpb(aes.PD_QUEUE_BYTES, pp.LONG_WRITE_AT))


def test_doq_reads_a_whole_full_pipe_at_once():
    """All eight messages in one read: the longest copy doq makes, the index 0, nothing left to move — doq's dearest
    row against the ROM (Tier 3: the C's saving is a constant, so the longest run is the worst ratio)."""
    before = pipe(make_image(pp.holding(PIPE_MESSAGES)))
    result = pp.run(DOQ, (READ, SHELL, QPB_AT), whole_pipe_read(), steered=pp.STEERS_THE_INDEX)
    assert result.after(pp.LONG_WRITE_AT, aes.PD_QUEUE_BYTES) == before and queue_index(result.final) == 0
    assert result.after(pp.LONG_WRITE_AT + aes.PD_QUEUE_BYTES, 1)[0] == case.SLACK_FILL


def test_a_read_that_empties_the_pipe_is_served_in_a_child():
    """The whole of what the pipe holds read: served, the index 0 — the edge of the refusal below, in a child process
    so that a core refusing one byte early fails this case."""
    returncode, stderr, image = pp.refused_leaving(DOQ, (READ, SHELL, QPB_AT),
                                                   merge_pokes(pp.holding(1), qpb(MESSAGE_BYTES, BUFFER_AT)))
    assert returncode == 0 and queue_index(image) == 0, stderr


def test_doq_reads_through_pointers_on_the_bus():
    result = read(pp.holding(2), pd=SHELL | TAG, qpb_at=QPB_AT | TAG, buffer=BUFFER_AT | TAG, steered=pp.STEERS_THE_INDEX)
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == pp.numbered(1)[0]


@THROUGH
def test_doq_reads_through_its_callers_word(through_line_f):
    assert queue_index(read(pp.holding(3), through_line_f=through_line_f, steered=pp.STEERS_THE_INDEX).final) == 2 * MESSAGE_BYTES


READ_PAST_THE_PIPE = "a read of more bytes than the pipe holds"


def past_the_pipe(held, count):
    """PD0 running with `held` messages in its pipe and a QPB reading `count` bytes of it — more than it holds — into
    the read buffer, or where a longer read has room (a QPB may not lie over the stub's room: `aes_pdpipe.qpb_pokes`)."""
    assert count > held * MESSAGE_BYTES
    return merge_pokes(pp.holding(held), qpb(count, BUFFER_AT if count <= pp.BUFFER_BYTES else pp.LONG_WRITE_AT))


def rom_s_read(held, count):
    """The ROM's own doq over `past_the_pipe(held, count)`, under the oracle's own cap: `(final, regs)`."""
    staged = aes.staged(DOQ, (READ, SHELL, QPB_AT), past_the_pipe(held, count))
    final, _writes, regs = emu.run(make_image(staged), addrs.AES_ROM_DOQ)
    return final, regs


def test_a_read_of_more_than_the_pipe_holds_is_refused_by_name():
    """ROM DEFECT (reached through aqueue, below): the index goes negative and "what is left" is moved as that count
    read unsigned — 64 KB of the AES's own RAM moved down over itself, the Line-F handler's copy with it. The host
    refuses by name — AFTER the ROM's stores up to there: the bytes copied out and the index, which are the ROM's."""
    held, count = 1, 2 * MESSAGE_BYTES
    returncode, stderr, image = pp.refused_leaving(DOQ, (READ, SHELL, QPB_AT), past_the_pipe(held, count))
    assert returncode != 0 and READ_PAST_THE_PIPE in stderr, stderr
    final, _regs = rom_s_read(held, count)
    assert queue_index(image) == queue_index(final) == held * MESSAGE_BYTES - count
    assert bytes(image[BUFFER_AT:BUFFER_AT + count]) == bytes(final[BUFFER_AT:BUFFER_AT + count])


LINE_F_COPY = aes.AES_LINEF_COPY        # the Line-F handler's RAM copy, where the vector points (`test_aes_door`)
LINE_F_FIRST_WORD = bytes(BASE_IMAGE[addrs.AES_ROM_LINEF_HANDLER:addrs.AES_ROM_LINEF_HANDLER + aes.WORD_BYTES])
RETURNS_OVER_A_MOVED_HANDLER = ((1, 2 * MESSAGE_BYTES), (1, 2 * MESSAGE_BYTES + MESSAGE_BYTES // 2), (1, 3 * MESSAGE_BYTES),
                                (2, 3 * MESSAGE_BYTES))
NEVER_RETURNS = ((1, MESSAGE_BYTES + 1), (1, MESSAGE_BYTES + MESSAGE_BYTES // 2), (0, MESSAGE_BYTES), (1, 4 * MESSAGE_BYTES),
                 (PIPE_MESSAGES, (PIPE_MESSAGES + 1) * MESSAGE_BYTES))


@pytest.mark.parametrize("held, count", RETURNS_OVER_A_MOVED_HANDLER, ids=lambda value: str(value))
def test_the_rom_s_read_past_the_pipe_returns_on_a_few_counts_through_its_own_moved_line_f_handler(held, count):
    """ROM FINDING, as measured (why the refusal's words are what they are): on a read of 32, 40 or 48 bytes the ROM's
    doq COMES BACK, under the oracle's own cap — 64 KB moved down by the bytes read, the Line-F handler's RAM copy in
    it: where the vector points now lie the bytes from `count` further up (the middle of the handler, no longer its
    first instruction), and doq's own Line-F return went through them. No C follows that: see pdpipe.c."""
    assert bytes(BASE_IMAGE[LINE_F_COPY:LINE_F_COPY + aes.WORD_BYTES]) == LINE_F_FIRST_WORD
    final, regs = rom_s_read(held, count)
    assert queue_index(final) == held * MESSAGE_BYTES - count and regs["ninsns"] < aes_event.DIFFERENTIAL_INSNS
    moved = bytes(final[LINE_F_COPY:LINE_F_COPY + aes.WORD_BYTES])
    assert moved == bytes(BASE_IMAGE[LINE_F_COPY + count:LINE_F_COPY + count + aes.WORD_BYTES]) != LINE_F_FIRST_WORD


@pytest.mark.parametrize("held, count", NEVER_RETURNS, ids=lambda value: str(value))
def test_the_rom_s_read_past_the_pipe_never_returns_on_the_other_counts(held, count):
    """...and on any other count tried — one byte too many, half a message, a read of an empty pipe, a far longer
    one — its run does not reach its return under the oracle's cap."""
    with pytest.raises(RuntimeError, match="did not reach rts"):
        rom_s_read(held, count)


# ---- aqueue --------------------------------------------------------------------------------------------------------------------
def aqueue(handed, evb_tag=0, qpb_tag=0, **kwargs):
    """The ROM's aqueue over the machine iasync hands it (`aes_pdpipe.at_aqueue`), against the C — poisoned unless
    the case says `steered=`."""
    return pp.run(AQUEUE, (handed.writing, handed.evb | evb_tag, handed.qpb | qpb_tag), handed.machine, **kwargs)


def writing(machine, sending=PLAIN, to=SHELL_PID):
    return pp.at_aqueue(merge_pokes(machine, {MESSAGE_AT: sending}), AP_RDWR_WRITE, to, len(sending), MESSAGE_AT)


def reading(machine, count=MESSAGE_BYTES, pid=SHELL_PID):
    return pp.at_aqueue(machine, AP_RDWR_READ, pid, count, BUFFER_AT)


def completed(image, evb):
    """Whether `evb` is on the completed list with its flag saying so."""
    return evb in aes_evasync.completed(image) and flag(image, evb) & COMPLETE


@pytest.mark.parametrize("held", (0, 1, PIPE_MESSAGES - 1))
def test_aqueue_writes_while_the_pipe_has_room(held):
    handed = writing(pp.holding(held))
    result = aqueue(handed, steered=SERVING_STEERS)
    assert queue_index(result.final) == (held + 1) * MESSAGE_BYTES and completed(result.final, handed.evb)
    assert pipe(result.final, messages=held + 1)[held * MESSAGE_BYTES:] == PLAIN


def test_aqueue_queues_a_write_the_pipe_has_no_room_for():
    """A full pipe: nothing written, the QPB's address kept in the EVB, the EVB on the pipe's writers' list."""
    handed = writing(pp.holding(PIPE_MESSAGES))
    result = aqueue(handed, steered=QUEUED_STEERS)
    assert queue_index(result.final) == aes.PD_QUEUE_BYTES and not completed(result.final, handed.evb)
    assert wait_list(result.final, SHELL + aes.PD_QUEUE_WRITERS) == [handed.evb]
    assert result.long(handed.evb + aes.EVB_PARM) == QPB_AT and not wait_list(result.final, SHELL + aes.PD_QUEUE_READERS)


# (held, the bytes written, whether they fit, what steers the pass). ONE byte written leaves the index EVEN once
# inverted (113 -> -114): its type is read back at an even address, and only the lists steer.
ROOM = {"the last sixteen bytes": (PIPE_MESSAGES - 1, PLAIN, True, SERVING_STEERS),
        "sixteen bytes too many": (PIPE_MESSAGES - 1, PLAIN + PLAIN, False, QUEUED_STEERS),
        "the last thirty-two": (PIPE_MESSAGES - 2, PLAIN + PLAIN, True, SERVING_STEERS),
        "one byte": (PIPE_MESSAGES - 1, PLAIN[:1], True, pp.STEERS_THE_LISTS),
        "one byte too many": (PIPE_MESSAGES, PLAIN[:1], False, QUEUED_STEERS)}


@pytest.mark.parametrize("held, sending, fits, steers", ROOM.values(), ids=ROOM)
def test_aqueue_s_room_is_the_bytes_left_against_the_bytes_counted(held, sending, fits, steers):
    handed = writing(pp.holding(held), sending)
    result = aqueue(handed, steered=steers)
    assert bool(completed(result.final, handed.evb)) == fits
    assert queue_index(result.final) == held * MESSAGE_BYTES + (len(sending) if fits else 0)


def test_aqueue_reads_what_the_pipe_holds():
    handed = reading(pp.holding(2))
    result = aqueue(handed)
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == pp.numbered(1)[0] and queue_index(result.final) == MESSAGE_BYTES
    assert completed(result.final, handed.evb) and not wait_list(result.final, SHELL + aes.PD_QUEUE_READERS)


def test_aqueue_queues_a_read_of_an_empty_pipe():
    handed = reading(pp.running())
    result = aqueue(handed, qpb_tag=TAG, steered=QUEUED_STEERS)
    assert wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) == [handed.evb] and not completed(result.final, handed.evb)
    assert result.long(handed.evb + aes.EVB_PARM) == QPB_AT | TAG, "the QPB's address is kept as it was handed in"
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == bytes([case.SLACK_FILL]) * MESSAGE_BYTES


def test_aqueue_queues_a_read_of_an_empty_pipe_in_a_child():
    """...in a child process too: a read taken for ready on an empty pipe ends in doq's refusal, which in process
    would end the suite's worker rather than fail a case."""
    handed = reading(pp.running())
    returncode, stderr, image = pp.refused_leaving(AQUEUE, (handed.writing, handed.evb, handed.qpb), handed.machine)
    assert returncode == 0 and wait_list(image, SHELL + aes.PD_QUEUE_READERS) == [handed.evb], stderr


def test_aqueue_serves_the_reader_waiting_for_the_message_it_writes():
    """The screen manager writes to PD0, parked in the desk's evnt_multi with a wait on its pipe: the message goes
    into the pipe and straight out again into the DESK's buffer (that wait's QPB), the wait marked NOCANCEL, taken
    off the readers' list and completed — PD0 woken — and the writer's own EVB completed. (NOCANCEL does not outlive
    the call: azombie stores the flag word whole.)"""
    handed = writing(pp.screen_manager_running())
    before = make_image(handed.machine)
    (waiting,) = wait_list(before, SHELL + aes.PD_QUEUE_READERS)
    desk_buffer = case.long_in(before, case.long_in(before, waiting + aes.EVB_PARM) + PDPIPE["QPB_BUFFER"])
    result = aqueue(handed, steered=SERVING_STEERS)
    assert queue_index(result.final) == 0 and result.after(desk_buffer, MESSAGE_BYTES) == PLAIN
    assert not wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) and flag(result.final, waiting) == COMPLETE
    assert completed(result.final, handed.evb) and completed(result.final, waiting)
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_aqueue_serves_the_writer_waiting_for_the_room_it_reads():
    """PD0 reads a message out of its full pipe while the screen manager waits to write one: the read makes the room,
    the waiting write goes in at once — the pipe full again — and the screen manager is woken."""
    handed = reading(pp.writer_waiting())
    before = make_image(handed.machine)
    (waiting,) = wait_list(before, SHELL + aes.PD_QUEUE_WRITERS)
    result = aqueue(handed)
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == pipe(before, messages=1)
    assert queue_index(result.final) == aes.PD_QUEUE_BYTES
    assert pipe(result.final) == pipe(before)[MESSAGE_BYTES:] + pp.BLOCKED_WRITE
    assert not wait_list(result.final, SHELL + aes.PD_QUEUE_WRITERS) and flag(result.final, waiting) == COMPLETE
    assert aes.list_of(result.final, aes.AES_DRL) == [MANAGER]


def test_aqueue_serves_a_waiting_writer_without_asking_whether_it_fits():
    """ROM DEFECT, pinned as the ROM has it: the screen manager waits to write THIRTY-TWO bytes into PD0's full pipe,
    and PD0 reads sixteen. The waiting write is served with no test of the room: its second message lands past the
    pipe's end — on the next PD's first sixteen bytes, the screen manager's own link, UDA pointer and name — and the
    index reads 144 of 128."""
    handed = reading(pp.writer_waiting(2 * pp.BLOCKED_WRITE))
    before = make_image(handed.machine)
    result = aqueue(handed)
    assert queue_index(result.final) == aes.PD_QUEUE_BYTES + MESSAGE_BYTES
    over = (aes.LONG_BYTES, MESSAGE_BYTES - aes.LONG_BYTES)    # past the link, which waking the PD stores next
    assert result.after(MANAGER + over[0], over[1]) == pp.BLOCKED_WRITE[over[0]:] != bytes(before[MANAGER + over[0]:MANAGER + MESSAGE_BYTES])
    assert case.long_in(before, MANAGER + aes.PD_UDA) == aes.AES_UDA1 != result.long(MANAGER + aes.PD_UDA)


def test_aqueue_serving_a_reader_of_more_than_was_written_is_refused_by_name():
    """ROM DEFECT, the other way: PD0 waits for sixteen bytes and the screen manager writes EIGHT. The waiting read is
    served with no test of what the pipe holds — doq's read past the pipe (above): the host refuses by name, and the
    ROM's run does not return under the oracle's cap."""
    handed = writing(pp.screen_manager_running(), PLAIN[:MESSAGE_BYTES // 2])
    arguments = (handed.writing, handed.evb, handed.qpb)
    returncode, stderr = pp.refused(AQUEUE, arguments, handed.machine)
    assert returncode != 0 and READ_PAST_THE_PIPE in stderr, stderr
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(aes.staged(AQUEUE, arguments, handed.machine)), addrs.AES_ROM_AQUEUE)


def test_aqueue_reading_more_than_a_short_pipe_holds_is_refused_by_name():
    """The same defect with ONE process: eight bytes written to its own pipe, sixteen read. Data is all aqueue asks of
    a read — any, not as much as is counted."""
    handed = reading(pp.sent(pp.running(), SHELL_PID, PLAIN[:MESSAGE_BYTES // 2]))
    returncode, stderr = pp.refused(AQUEUE, (handed.writing, handed.evb, handed.qpb), handed.machine)
    assert returncode != 0 and READ_PAST_THE_PIPE in stderr, stderr


def test_aqueue_moves_the_bytes_before_it_completes_the_evb():
    """THE ORDER, as an overlap: the read's buffer IS the event block. The message lands on the EVB's first sixteen
    bytes — its links and its PD, which the message's last longword names again — and azombie then links the EVB it
    finds there: the completed list's links are the last stores."""
    carrying_the_pd = PLAIN[:MESSAGE_BYTES - aes.LONG_BYTES] + struct.pack(">I", SHELL)
    machine = pp.sent(pp.running(), SHELL_PID, carrying_the_pd)
    evb = case.long_in(make_image(machine), aes.AES_EUL)
    handed = pp.at_aqueue(machine, AP_RDWR_READ, SHELL_PID, MESSAGE_BYTES, evb)
    assert handed.evb == evb, "iasync takes the free list's head"
    result = aqueue(handed)
    assert completed(result.final, evb) and result.after(evb, aes.EVB_LINK) == carrying_the_pd[:aes.EVB_LINK]
    assert result.long(evb + aes.EVB_PD) == SHELL


def test_aqueue_picks_the_other_end_s_list_before_its_own_write_fills_the_pipe():
    """THE LIST IS CHOSEN BEFORE doq: the screen manager writes a WHOLE PIPE of bytes to PD0, whose reader waits. Ready
    when asked (room for 128), so the other end is the readers' — and stays so though the pipe is full once written:
    the waiting read is served (sixteen out, 112 left), PD0 woken. A choice made again after the write would look at
    the writers' list."""
    whole_pipe = PLAIN * PIPE_MESSAGES
    machine = merge_pokes(pp.screen_manager_running(), {pp.LONG_WRITE_AT: whole_pipe})
    handed = pp.at_aqueue(machine, AP_RDWR_WRITE, SHELL_PID, len(whole_pipe), pp.LONG_WRITE_AT)
    result = aqueue(handed, steered=SERVING_STEERS)
    assert queue_index(result.final) == len(whole_pipe) - MESSAGE_BYTES
    assert not wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) and aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_aqueue_picks_its_list_by_the_whole_writing_word():
    """`writing XOR ready` ON WORDS ($fe59da `eor.w`): a writing word of $100 — nonzero, so a write, and ready — picks
    the list by $100 ^ 1, not 0: the WRITERS' list (empty), so the reader waiting on this pipe is NOT served and the
    message stays in it. (iasync hands 0 or 1; the word is the routine's.)"""
    handed = writing(pp.screen_manager_running())
    (waiting,) = wait_list(make_image(handed.machine), SHELL + aes.PD_QUEUE_READERS)
    result = aqueue(handed._replace(writing=HIGH_BYTE_ALONE), steered=SERVING_STEERS)
    assert queue_index(result.final) == MESSAGE_BYTES and pipe(result.final, messages=1) == PLAIN
    assert wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) == [waiting] and completed(result.final, handed.evb)


ID_PAST_A_BYTE = 0x100                 # a process id whose low byte is the shell's


@pytest.mark.parametrize("pid", (APPLICATION_PID, ID_PAST_A_BYTE), ids=("id 2, never started", "$100: the shell's low byte"))
def test_aqueue_for_a_process_id_no_pd_has_is_refused_by_name(pid):
    """ROM DEFECT: id 2 before anything was started — or an id whose low byte is a process's (the QPB's id is a whole
    word). fpdnm answers none and the ROM takes the vector page for the process's descriptor — the pipe's index a
    vector's low word, its address another vector: its run does not return under the oracle's cap. The host refuses
    by name."""
    handed = writing(pp.running(), to=pid)
    arguments = (handed.writing, handed.evb, handed.qpb)
    returncode, stderr = pp.refused(AQUEUE, arguments, handed.machine)
    assert returncode != 0 and "a process id no PD has" in stderr, stderr
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(aes.staged(AQUEUE, arguments, handed.machine)), addrs.AES_ROM_AQUEUE)


def test_aqueue_puts_its_pointers_on_the_bus():
    handed = writing(pp.holding(1))
    result = aqueue(handed, evb_tag=TAG, qpb_tag=TAG, steered=SERVING_STEERS)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES and completed(result.final, handed.evb)


@THROUGH
def test_aqueue_through_its_callers_word(through_line_f):
    handed = writing(pp.screen_manager_running())
    assert aes.list_of(aqueue(handed, through_line_f=through_line_f, steered=SERVING_STEERS).final, aes.AES_DRL) == [SHELL]


def test_aqueue_writes_to_a_third_process_waiting_for_a_message():
    """`STAGED_APPLICATION`: its program waits for a message; PD0 writes one to process 2 — fpdnm walks past both
    other PDs — and it lands in the application's buffer, the application woken."""
    handed = writing(application_waiting(), to=APPLICATION_PID)
    result = aqueue(handed, steered=SERVING_STEERS)
    assert result.after(BUFFER_AT, MESSAGE_BYTES) == PLAIN and queue_index(result.final, SPARE_PD) == 0
    assert aes.list_of(result.final, aes.AES_DRL) == [SPARE_PD] and not wait_list(result.final, SPARE_PD + aes.PD_QUEUE_READERS)


def two_writers_waiting():
    """`STAGED_APPLICATION`, its pipe FULL and TWO processes parked writing to it: PD0 fills it and blocks on a ninth
    message; the screen manager, woken by the mouse, blocks on one of its own — queued at the HEAD of the writers'
    list. The dispatcher then enters the application, whose program reads its pipe: stopped at that aqueue."""
    made = application()
    blocked = pp.blocked_writing(pp.sent(made.machine, APPLICATION_PID, *pp.numbered(PIPE_MESSAGES)), APPLICATION_PID,
                                 SHELL_WRITES)
    both = pp.blocked_writing(pp.woken_screen_manager(blocked), APPLICATION_PID, MANAGER_WRITES)
    return pp.at_aqueue_from_the_dispatcher(made, both)


SHELL_WRITES, MANAGER_WRITES = pp.numbered(2, first=pp.BLOCKED_TYPE + 1)


def test_aqueue_serves_the_last_of_two_waiting_writers_first():
    """`STAGED_APPLICATION`. ROM FINDING: a wait list is LAST IN, FIRST OUT — evinsert queues at the head, and aqueue
    serves the head: the screen manager's write, queued after PD0's, goes in first and PD0's stays waiting, now the
    list's head with its back link moved to the list itself."""
    handed = two_writers_waiting()
    before = make_image(handed.machine)
    writers = SPARE_PD + aes.PD_QUEUE_WRITERS
    last, first = wait_list(before, writers)
    assert [case.long_in(before, evb + aes.EVB_PD) for evb in (last, first)] == [MANAGER, SHELL] and handed.writing == READ
    assert aes.list_of(before, aes.AES_RLR) == [SPARE_PD]
    result = aqueue(handed)
    assert wait_list(result.final, writers) == [first]
    assert result.long(first + aes.EVB_PRED) == case.long_in(before, last + aes.EVB_PRED) != last
    assert pipe(result.final, SPARE_PD) == pipe(before, SPARE_PD)[MESSAGE_BYTES:] + MANAGER_WRITES
    assert aes.list_of(result.final, aes.AES_DRL) == [MANAGER] and SHELL in aes.list_of(result.final, aes.AES_NRL)


# ---- MACHINES THE ROM MAKES PAST ITS OWN INVARIANTS ----------------------------------------------------------------------------
# "Every PD's queue pointer names its own pipe", "a spare PD's status is 0", "an index is 0..128 and even": true of
# every machine a well-behaved program leaves — and each UNDONE BY THE ROM ITSELF, by a call it serves and returns
# from. Two levers, both the ROM's own doq, so nothing here is poked:
#   * THE OVERRUN (aqueue's unchecked service of a waiting writer, above) taken further: the screen manager waits to
#     write a message AND THE NEXT PDs' OWN BYTES behind it; served at the last sixteen bytes of PD0's pipe, the
#     write runs on over PD1 and the head of PD2 — laying back exactly what they held, but for the fields a case
#     crafts (`overrun`);
#   * A NEGATIVE INDEX: a write of a negative count from a buffer BELOW the pipe — lbcopy's backward loop moves one
#     byte and stops, and doq adds the count to the index (`negative_index`).
# The spellings of pdpipe.c these tell apart are the 68000's: a signed word where a register holds one, a field read
# again after a callee's stores, a value kept in a register across them.
OVERRUN_INDEX = (PIPE_MESSAGES - 1) * MESSAGE_BYTES     # where the served write lands: the pipe's last message
SPARE_PD_HEAD = aes.PD_STAT + aes.WORD_BYTES            # the head of PD2 the write runs on over: up to its status
OVERRUN_BYTES = MESSAGE_BYTES + aes.PD_BYTES + SPARE_PD_HEAD
STALE_ELSEWHERE = {pp.ELSEWHERE_AT: bytes([case.SLACK_FILL]) * pp.ELSEWHERE_BYTES}


def overrun(craft):
    """THE ROM's OWN OVERRUN, in two passes so that the bytes it lays over the next PDs are THOSE PDs' OWN as they
    stand when the write is served, but for what `craft(pd1, pd2)` changes (two bytearrays: PD1 whole, PD2's head):
    the screen manager waits to write PLAIN and those bytes into PD0's full pipe, PD0 reads sixteen — the waiting
    write is served where the pipe's last message was. The C is held to the ROM over the overrun itself; the machine
    after it (`case.continued`)."""
    def served(tail):
        return reading(pp.writer_waiting(PLAIN + tail, pp.LONG_WRITE_AT))

    def next_pds(image):
        return bytes(image[MANAGER:MANAGER + aes.PD_BYTES]), bytes(image[SPARE_PD:SPARE_PD + SPARE_PD_HEAD])
    as_they_stand = next_pds(make_image(served(bytes(aes.PD_BYTES + SPARE_PD_HEAD)).machine))
    pd1, pd2 = map(bytearray, as_they_stand)
    craft(pd1, pd2)
    handed = served(bytes(pd1 + pd2))
    assert next_pds(make_image(handed.machine)) == as_they_stand, "the second pass's PDs are not the first's"
    result = aqueue(handed)
    assert queue_index(result.final) == OVERRUN_INDEX + OVERRUN_BYTES
    return case.continued(result)


def field_set(record, field, packed):
    """A PD's bytes (a bytearray) with `packed` laid at `field`."""
    record[field:field + len(packed)] = packed


def manager_s_pipe_moved(to, index, held=b""):
    """PD1 — the screen manager — as the overrun leaves it with its QUEUE POINTER naming `to`, its index `index` and
    the pipe the PD itself holds starting with `held`: a PD whose pointer no longer names its own pipe."""
    def craft(pd1, _pd2):
        field_set(pd1, aes.PD_QUEUE_ADDRESS, struct.pack(">I", to))
        field_set(pd1, aes.PD_QUEUE_INDEX, struct.pack(">h", index))
        field_set(pd1, aes.PD_QUEUE, held)
    machine = overrun(craft)
    image = make_image(machine)
    assert case.long_in(image, MANAGER + aes.PD_QUEUE_ADDRESS) == to != MANAGER + aes.PD_QUEUE
    assert pd_id(image, MANAGER) == SCREEN_MANAGER_PID and pd_name(image, MANAGER) == MANAGER_NAME
    return machine


def test_doq_writes_through_the_queue_pointer_and_reads_the_message_back_in_the_pd():
    """THE TWO SPELLINGS OF "THE PIPE", told apart: PD1's queue pointer names another buffer (the ROM's own overrun
    left it so), its index one message, the PD's own pipe holding two redraws for the window. A PLAIN message written
    to PD1 goes THROUGH THE POINTER (to the other buffer, at the index); what doq then reads back as "the message" is
    at pd + 56 + index — the stale second redraw — which it merges into the first, also read in the PD: the index
    does not move. A C that spelt any of the three reads the other way differs here."""
    two_redraws = pp.redraw(WINDOW, *FIRST_RECT) + pp.redraw(WINDOW, *SECOND_RECT)
    machine = merge_pokes(manager_s_pipe_moved(pp.ELSEWHERE_AT, MESSAGE_BYTES, two_redraws), STALE_ELSEWHERE)
    staged = merge_pokes(machine, {MESSAGE_AT: PLAIN}, qpb(MESSAGE_BYTES, MESSAGE_AT, SCREEN_MANAGER_PID))
    returncode, stderr = pp.refused(DOQ, (WRITE, MANAGER, QPB_AT), staged)      # a spelling that walks off halts: a child
    assert returncode == 0, stderr
    result = write(machine, PLAIN, pd=MANAGER, pid=SCREEN_MANAGER_PID, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final, MANAGER) == MESSAGE_BYTES
    assert result.after(pp.ELSEWHERE_AT + MESSAGE_BYTES, MESSAGE_BYTES) == PLAIN
    assert pipe(result.final, MANAGER, messages=2) == pp.redraw(WINDOW, *BOTH) + pp.redraw(WINDOW, *SECOND_RECT)


def test_doq_reads_the_count_once_whatever_its_write_lays_over_the_qpb():
    """A VALUE KEPT IN A REGISTER: PD1's queue pointer names the bytes just below the QPB itself, so the message
    lands ON THE QPB — its count now the message's second word, 0. The ROM read the count before the copy
    ($fe58d0 `move.w 2(a0),d7`) and adds THAT to the index."""
    machine = manager_s_pipe_moved(QPB_AT - MESSAGE_BYTES, MESSAGE_BYTES)
    result = write(machine, PLAIN, pd=MANAGER, pid=SCREEN_MANAGER_PID, steered=pp.STEERS_THE_INDEX)
    assert result.after(QPB_AT, MESSAGE_BYTES) == PLAIN and result.word(QPB_AT + PDPIPE["QPB_COUNT"]) == 0
    assert queue_index(result.final, MANAGER) == 2 * MESSAGE_BYTES


def test_doq_reads_the_count_once_whatever_its_read_lays_over_the_qpb():
    """...and reading: the buffer IS the QPB, so the first copy lays the message over the count (its second word, 0)
    — the index still drops by the sixteen the ROM read first, and that many are moved down."""
    before = pipe(make_image(pp.holding(2)), messages=2)
    result = read(pp.holding(2), buffer=QPB_AT, steered=(pp.STEERS_THE_QPB, pp.STEERS_THE_INDEX))
    assert result.after(QPB_AT, MESSAGE_BYTES) == before[:MESSAGE_BYTES] and result.word(QPB_AT + PDPIPE["QPB_COUNT"]) == 0
    assert queue_index(result.final) == MESSAGE_BYTES and pipe(result.final, messages=1) == before[MESSAGE_BYTES:]


def test_a_read_from_an_overrun_pipe_is_served_the_refusal_is_of_a_negative_index():
    """The index 344 of 128 after the overrun, and a read of sixteen: served — 328 bytes moved down through the next
    PDs, as the ROM moves them (in a child first: a C that refused an index past the pipe's size would halt). doq's
    one refusal is of an index BELOW 0."""
    machine = overrun(lambda _pd1, _pd2: None)
    returncode, stderr = pp.refused(DOQ, (READ, SHELL, QPB_AT), merge_pokes(machine, qpb(MESSAGE_BYTES, BUFFER_AT)))
    assert returncode == 0, stderr
    result = read(machine, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == OVERRUN_INDEX + OVERRUN_BYTES - MESSAGE_BYTES > aes.PD_QUEUE_BYTES


def test_pstart_clears_the_status_of_a_spare_pd_the_rom_left_waiting():
    """pstart's `clr.w p_stat` on a spare PD whose status is NOT 0: the same overrun reached it and left it waiting.
    Started, it is ready."""
    def craft(_pd1, pd2):
        field_set(pd2, aes.PD_STAT, struct.pack(">h", aes.PD_STAT_WAITING))
    machine = overrun(craft)
    assert case.word_in(make_image(machine), SPARE_PD + aes.PD_STAT) == aes.PD_STAT_WAITING
    result = pp.run(PSTART, (STUB_AT, NAME_AT, 0), named(b"THIRD", machine), steered=STARTING_STEERS)
    assert result.long_answer() == SPARE_PD and result.word(SPARE_PD + aes.PD_STAT) == aes.PD_STAT_READY


def test_aqueue_marks_the_served_wait_nocancel_before_it_serves_it():
    """THE NOCANCEL MARK IS NOT DEAD: the screen manager waits to write thirty-two bytes FROM THE EVENT BLOCK ITS WAIT
    IS (a caller's pointer like any other). Served, the pipe receives the EVB's bytes as they stand at the service —
    its flag word with NOCANCEL set, which azombie's store of the whole word only then replaces."""
    machine, evb = pp.writer_waiting_to_write_its_own_evb(2 * MESSAGE_BYTES)
    handed = pp.at_aqueue(machine, AP_RDWR_READ, SHELL_PID, 2 * MESSAGE_BYTES, BUFFER_AT)
    assert wait_list(make_image(handed.machine), SHELL + aes.PD_QUEUE_WRITERS) == [evb]
    result = aqueue(handed)
    served = pipe(result.final)[(PIPE_MESSAGES - 2) * MESSAGE_BYTES:]
    assert case.word_in(served, aes.EVB_FLAG) == NOCANCEL and flag(result.final, evb) == COMPLETE


# ---- a negative index ----------------------------------------------------------------------------------------------------------------
# The desk's own data lies BELOW the PDs (the AES's RAM is laid out so): any buffer of its own is a "buffer below the
# pipe". Its global[] stands for one.
BELOW_THE_PIPES = aes.AES_DESK_APP_GLOBAL
assert BELOW_THE_PIPES < aes.AES_PD_TABLE
# The sixteen bytes just below a PD's pipe, which a write at index -16 lands on: the low word of its event list, its
# two wait lists, its queue pointer and — last — its index.
BELOW_THE_PIPE = aes.PD_QUEUE - MESSAGE_BYTES
INDEX_IN_THE_MESSAGE = aes.PD_QUEUE_INDEX - BELOW_THE_PIPE


def negative_index(start=None):
    """PD0's pipe index at -16, MADE BY THE ROM's own doq: a write of count -16 from a buffer below the pipe — lbcopy
    runs backward, its signed count already negative: ONE byte moved — then `add.w d7,54(a5)`. The C held to the ROM
    on the way; the machine after (`case.continued`)."""
    machine = merge_pokes(pp.running() if start is None else start, qpb(-MESSAGE_BYTES, BELOW_THE_PIPES))
    result = pp.run(DOQ, (WRITE, SHELL, QPB_AT), machine, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == -MESSAGE_BYTES
    return case.continued(result)


def over_the_pd_s_own_index(image, new_index):
    """A REDRAW for WINDOW that, written at index -16, lays back the PD's wait lists and queue pointer as they are
    and sets its index to `new_index`: the message's last word IS the index."""
    kept = bytes(image[SHELL + BELOW_THE_PIPE:SHELL + aes.PD_QUEUE])
    sending = bytearray(kept)
    struct.pack_into(">h", sending, APMSG["AP_MSG_TYPE"], WM_REDRAW)
    struct.pack_into(">h", sending, REDRAW_HANDLE, WINDOW)
    struct.pack_into(">h", sending, INDEX_IN_THE_MESSAGE, new_index)
    return bytes(sending)


WM_REDRAW = pp.WM_REDRAW
APMSG = pp.APMSG
REDRAW_HANDLE = APMSG["AP_MSG_WORDS"]   # a redraw's first own word: its window


def a_stale_redraw_at_the_head():
    """PD0 running, its pipe EMPTY, the bytes at its head a redraw for WINDOW that was queued and read out again."""
    queued = pp.sent(pp.running(), SHELL_PID, pp.redraw(WINDOW, *FIRST_RECT))
    return case.continued(read(queued, steered=pp.STEERS_THE_INDEX))


def test_doq_adds_a_negative_index_as_a_signed_word_and_reads_the_index_again():
    """`ext.l` THEN `adda.l`, AND A FIELD READ AGAIN: at index -16 the write lands sixteen bytes BELOW the pipe — on
    the PD's own index, which the message sets to 16. The message is then read back at pd + 56 + THAT index: no
    redraw there, so it is appended (index 32) — where an index kept from before the copy would read the message
    itself, a redraw, and merge it into the stale one at the pipe's head."""
    machine = negative_index(a_stale_redraw_at_the_head())
    sending = over_the_pd_s_own_index(make_image(machine), MESSAGE_BYTES)
    result = write(machine, sending, steered=OVER_ITS_OWN_PD_STEERS)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES
    assert result.after(SHELL + BELOW_THE_PIPE, INDEX_IN_THE_MESSAGE) == sending[:INDEX_IN_THE_MESSAGE]
    assert pipe(result.final, messages=1) == pp.redraw(WINDOW, *FIRST_RECT), "nothing was merged into the stale redraw"


def test_doq_s_walk_is_bounded_by_the_index_as_a_signed_word():
    """`cmp.w 54(a5),d6 / bge`: the same write, the message leaving the index at -16 — read back at pd + 40, it is
    itself, a redraw; the walk from 0 does not run (0 >= -16), so the stale redraw at the head is not merged into and
    the write counts: the index ends 0."""
    machine = negative_index(a_stale_redraw_at_the_head())
    result = write(machine, over_the_pd_s_own_index(make_image(machine), -MESSAGE_BYTES), steered=pp.STEERS_THE_QUEUE_POINTER)
    assert queue_index(result.final) == 0 and pipe(result.final, messages=1) == pp.redraw(WINDOW, *FIRST_RECT)


def test_doq_reads_out_a_negative_count():
    """A read of count -16 with sixteen held, into a buffer ABOVE the pipe (as an application's is): lbcopy's
    backward loop again (one byte), and the index GROWS to 32 — `sub.w d7`; thirty-two bytes are then moved down
    from sixteen BELOW the head."""
    result = read(pp.holding(1), -MESSAGE_BYTES, steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 2 * MESSAGE_BYTES


def test_aqueue_serves_a_write_of_a_negative_count_its_room_compared_signed():
    """`cmp.w / blt` on the room: 128 - 0 >= -16 as SIGNED words — served, the index -16, the EVB completed."""
    handed = pp.at_aqueue(pp.running(), AP_RDWR_WRITE, SHELL_PID, -MESSAGE_BYTES, BELOW_THE_PIPES)
    result = aqueue(handed, steered=SERVING_STEERS)
    assert queue_index(result.final) == -MESSAGE_BYTES and completed(result.final, handed.evb)


def test_aqueue_queues_a_read_of_a_negative_index():
    """`tst.w / bgt`: a negative index is NO data — the read waits (in a child first: a core that took it for data
    would read past the pipe, doq's refusal)."""
    handed = pp.at_aqueue(negative_index(), AP_RDWR_READ, SHELL_PID, MESSAGE_BYTES, BUFFER_AT)
    returncode, stderr, image = pp.refused_leaving(AQUEUE, (handed.writing, handed.evb, handed.qpb), handed.machine)
    assert returncode == 0 and wait_list(image, SHELL + aes.PD_QUEUE_READERS) == [handed.evb], stderr
    result = aqueue(handed, steered=QUEUED_STEERS)
    assert wait_list(result.final, SHELL + aes.PD_QUEUE_READERS) == [handed.evb]


def test_doq_moves_what_is_left_through_the_queue_pointer_read_again():
    """A FIELD READ AGAIN after lbcopy's stores: the read's buffer is the PD's own wait lists, so the message lands on
    them, on the queue pointer (now another buffer) and on the index (48). What is left — 48 - 16 — is moved down
    THERE, through the pointer as it now stands ($fe5974 `move.l 50(a5),(sp)` after the copy)."""
    elsewhere = bytes(range(TAIL_FIRST_BYTE, TAIL_FIRST_BYTE + 3 * MESSAGE_BYTES))
    carried = struct.pack(">IIIhH", 0, 0, pp.ELSEWHERE_AT, len(elsewhere), 0)     # the lists, the pointer, the index
    machine = merge_pokes(pp.sent(pp.running(), SHELL_PID, carried), {pp.ELSEWHERE_AT: elsewhere})
    result = read(machine, buffer=SHELL + aes.PD_QUEUE_READERS, steered=pp.STEERS_THE_QUEUE_POINTER)
    assert queue_index(result.final) == len(elsewhere) - MESSAGE_BYTES
    assert result.after(pp.ELSEWHERE_AT, len(elsewhere) - MESSAGE_BYTES) == elsewhere[MESSAGE_BYTES:]


EXTRA_PAST_A_BYTE = 0x100              # a message's count of bytes past the sixteen whose low byte is 0
EXTRA_THAT_WRAPS = 0x7FF0              # ...and one that takes the walk's offset to $8000: negative, as a word
AES_ROM_DOQ_WALK_TYPE_READ = addrs.AES_ROM_DOQ + 0x5A   # $fe591a: the walk's read of a queued message's words


def test_doq_s_walk_offset_wraps_as_a_word():
    """`add.w d0,d6` on a WORD: behind a queued message whose third word is $7ff0 the walk's offset is $8000 —
    negative, so still below the index — and the walk goes on 32 KB BELOW the PD, through low memory, message by
    "message", until a step lands it at an odd address: a word read there, the address error. The oracle (no address
    errors) names the access in its ledger and runs on; the host C halts by the accessors' name where a C keeping
    the offset wider than a word would simply stop the walk and return."""
    far = pp.message(PLAIN_TYPE, 1, 2, 3, 4, 5, extra=EXTRA_THAT_WRAPS)
    machine = merge_pokes(redraws_held(far, pp.redraw(WINDOW, *FIRST_RECT)), {MESSAGE_AT: pp.redraw(WINDOW, *SECOND_RECT)},
                          qpb(MESSAGE_BYTES, MESSAGE_AT))
    returncode, stderr = pp.refused(DOQ, (WRITE, SHELL, QPB_AT), machine)
    assert returncode != 0 and ODD_ADDRESS in stderr, stderr
    emu.run(make_image(aes.staged(DOQ, (WRITE, SHELL, QPB_AT), machine)), addrs.AES_ROM_DOQ)
    the_rom_s = emu.odd_accesses()
    assert the_rom_s["odd_accesses"] and the_rom_s["odd_first_pc"] == AES_ROM_DOQ_WALK_TYPE_READ
    assert all(at < SHELL for at in the_rom_s["odd_addresses"]), "the walk's odd reads are below the PD"


def test_doq_s_walk_steps_by_the_whole_extra_word():
    """A queued message whose third word is $100: the walk steps 272 bytes — past the index — so the redraw queued
    behind it is never looked at, and the new one is appended. (A step by the word's low byte would merge.)"""
    far = pp.message(PLAIN_TYPE, 1, 2, 3, 4, 5, extra=EXTRA_PAST_A_BYTE)
    result = write(redraws_held(far, pp.redraw(WINDOW, *FIRST_RECT)), pp.redraw(WINDOW, *SECOND_RECT),
                   steered=pp.STEERS_THE_INDEX)
    assert queue_index(result.final) == 3 * MESSAGE_BYTES
    assert pipe(result.final, messages=3)[MESSAGE_BYTES:] == pp.redraw(WINDOW, *FIRST_RECT) + pp.redraw(WINDOW, *SECOND_RECT)


@pytest.mark.parametrize("pid, pd", ((ID_PAST_A_BYTE, SHELL), (ID_PAST_A_BYTE + SCREEN_MANAGER_PID, MANAGER),
                                     (SCREEN_MANAGER_PID - ID_PAST_A_BYTE, MANAGER)),
                         ids=("$100: not the shell", "$101: not the screen manager", "-$ff: not the screen manager"))
def test_a_process_id_is_compared_as_a_whole_word(pid, pd):
    """`cmp.w`: an id whose LOW BYTE is a process's finds none — by pd_match, and by fpdnm over it."""
    assert pp.run(PD_MATCH, (PDPIPE["FPDNM_BY_PID"], pid, pd), named(MANAGER_NAME)).answer() == 0
    assert fpdnm(None, pid).long_answer() == 0


# ---- ap_find ---------------------------------------------------------------------------------------------------------------------
ELEVEN = b"CONTROL.ACC"                # the obvious mistake: an accessory's FILE name, eleven characters
TWELVE = ELEVEN + b"X"
# ...the longest the ROM serves: its NUL on the last byte of the saved A6 a name may run over (`aes/pdpipe.h`).
assert len(TWELVE) == PDPIPE["AP_FIND_FRAME_BYTES"] + PDPIPE["AP_FIND_SAVED_A6_BYTES"]
NAMES = {       # (the name asked for, the answer)
    "the screen manager's": (MANAGER_NAME, SCREEN_MANAGER_PID),
    "eight blanks: the shell": (BLANK, SHELL_PID),
    "none of that name": (b"NOSUCH  ", PDPIPE["AP_FIND_NONE"]),
    "a name unpadded": (b"SCRENMG", PDPIPE["AP_FIND_NONE"]),
    "nine characters: the frame full": (MANAGER_NAME + b"X", PDPIPE["AP_FIND_NONE"]),
    "ten: the NUL on the saved A6's top byte": (MANAGER_NAME + b"XY", PDPIPE["AP_FIND_NONE"]),
    "eleven: the NUL on the saved A6's bits 16..23": (ELEVEN, PDPIPE["AP_FIND_NONE"]),
    "no character at all": (b"", PDPIPE["AP_FIND_NONE"]),
}


@pytest.mark.parametrize("name, found", NAMES.values(), ids=NAMES)
def test_ap_find(name, found):
    assert pp.run(AP_FIND, (NAME_AT,), named(name)).answer() == found


def test_ap_find_puts_the_name_on_the_bus():
    assert pp.run(AP_FIND, (NAME_AT | TAG,), named(MANAGER_NAME)).answer() == SCREEN_MANAGER_PID


@THROUGH
def test_ap_find_through_its_callers_word(through_line_f):
    assert pp.run(AP_FIND, (NAME_AT,), named(MANAGER_NAME), through_line_f=through_line_f).answer() == SCREEN_MANAGER_PID


def test_ap_find_finds_a_third_process():
    """`STAGED_APPLICATION`, by the name pstart gave it, blank-filled."""
    machine = named(APPLICATION_NAME.ljust(aes.PD_NAME_BYTES), with_the_application())
    assert pp.run(AP_FIND, (NAME_AT,), machine).answer() == APPLICATION_PID


STALE_FRAME = aes.stale_host_slot("AES_AP_FIND_NAME", fill=case.SLACK_FILL)


@pytest.mark.parametrize("name, found", ((MANAGER_NAME, SCREEN_MANAGER_PID), (MANAGER_NAME + b"X", PDPIPE["AP_FIND_NONE"]),
                                         (MANAGER_NAME + b"XY", PDPIPE["AP_FIND_NONE"]), (ELEVEN, PDPIPE["AP_FIND_NONE"])),
                         ids=("eight characters", "nine", "ten", "eleven"))
def test_ap_find_s_frame_is_ended_by_the_saved_a6_s_top_bytes_whatever_the_slot_held(name, found):
    """The two bytes past the frame are the top of the caller's saved A6 — 0 on a static process's stack, which the
    host's stand-in must SET: staged stale, a name the ROM serves is still served (in a child: a core that took a
    stale byte for the name's overrun would halt)."""
    returncode, stderr, answer = pp.answered(AP_FIND, (NAME_AT,), merge_pokes(named(name), STALE_FRAME))
    assert returncode == 0 and answer == found, stderr


LOW_64K = 1 << 16                      # below it an address's bits 16..23 are 0: THE PREMISE of ap_find's boundary


@pytest.mark.parametrize("name", (ELEVEN, MANAGER_NAME + b"XYZ"), ids=("an accessory's file name", "the screen manager's and three"))
def test_appl_find_of_eleven_characters_is_served_as_the_rom_serves_it(name):
    """THE ROM's BOUNDARY, through its own trap door (`aes_pdpipe.appl_find_by_trap`): the eleventh character lands on
    the top byte of aes_dispatch's saved A6 — off the 24-bit bus — and the NUL on its bits 16..23, a 0 already since
    the frame lies on the calling process's UDA stack, below 64 KB (asserted: the premise). The ROM answers -1 and
    returns to the trap handler; so does the C, in a child."""
    by_trap = pp.appl_find_by_trap(name)
    assert by_trap.answer == PDPIPE["AP_FIND_NONE"] and by_trap.callers_a6 < LOW_64K
    returncode, stderr, answer = pp.answered(AP_FIND, (NAME_AT,), named(name))
    assert returncode == 0 and answer == PDPIPE["AP_FIND_NONE"], stderr


def test_eleven_characters_cost_the_rom_one_dead_byte_and_nothing_else():
    """Ten characters against eleven through the trap door, the images after: they differ at the two bytes the names
    differ by and at ONE more — the top byte of the saved A6 (ten leaves a NUL there, eleven a character), which no
    access reads. Serving eleven loses nothing a C could not see."""
    ten, eleven = pp.appl_find_by_trap(ELEVEN[:-1]), pp.appl_find_by_trap(ELEVEN)
    differing = set(aes_event._differing_addresses(ten.final, eleven.final))
    the_names = {NAME_AT + len(ELEVEN) - 1, NAME_AT + len(ELEVEN)}
    (dead,) = differing - the_names
    assert differing >= the_names and ten.final[dead] == 0 and eleven.final[dead] == ELEVEN[-1]
    assert ten.callers_a6 == eleven.callers_a6 and dead < ten.callers_a6 < LOW_64K


@pytest.mark.parametrize("name", (TWELVE, b"ABCDEFGHIJKLMNOPQRST"), ids=("twelve characters", "twenty"))
def test_a_name_past_what_the_rom_serves_is_refused_by_name(name):
    """The copy stops at the name's NUL and nowhere else: from TWELVE characters it runs over a live byte of the
    caller's saved A6 (and from fourteen over ap_find's own return address), which no C can see — the ROM's own run
    through the trap door never comes back, and both builds halt by name. Exactly the ROM's boundary: one character
    fewer is served (above)."""
    with pytest.raises(RuntimeError, match="did not reach"):
        pp.appl_find_by_trap(name)
    returncode, stderr = pp.refused(AP_FIND, (NAME_AT,), named(name))
    assert returncode != 0 and "ap_find: a name of twelve characters or more" in stderr, stderr


# ---- the registry: Tier 3's rows ---------------------------------------------------------------------------------------------------
def _register_rows():
    register = pp.register
    register("by name, the screen manager's", PD_MATCH, (NAME_AT, SHELL_PID, MANAGER), named(MANAGER_NAME))
    register("by name, another's first character", PD_MATCH, (NAME_AT, SHELL_PID, SHELL), named(MANAGER_NAME))
    register("by id", PD_MATCH, (PDPIPE["FPDNM_BY_PID"], SCREEN_MANAGER_PID, MANAGER), named(BLANK))
    register("by id, the shell", FPDNM, (PDPIPE["FPDNM_BY_PID"], SHELL_PID), named(BLANK))
    register("by id, none", FPDNM, (PDPIPE["FPDNM_BY_PID"], APPLICATION_PID), named(BLANK))
    register("by name, the screen manager", FPDNM, (NAME_AT, SHELL_PID), named(MANAGER_NAME))
    register("by name, none", FPDNM, (NAME_AT, SHELL_PID), named(b"NOSUCH  "))
    register("the spare static PD", GETPD, (), pp.running())
    register("the spare UDA", UDA_INSUPER, (SPARE_UDA,), pp.running())
    register("the spare PD", PSETUP, (SPARE_PD, CODE), pp.running())
    register("a program's file", PSTART, (STUB_AT, NAME_AT, 0), named(b"CONTROL.ACC"))
    register("a write into an empty pipe", DOQ, (WRITE, SHELL, QPB_AT), to_write(pp.running(), PLAIN))
    register("a write behind seven", DOQ, (WRITE, SHELL, QPB_AT), to_write(pp.holding(PIPE_MESSAGES - 1), PLAIN))
    seven_redraws = redraws_held(*[pp.redraw(window, *FIRST_RECT) for window in range(1, PIPE_MESSAGES)])
    register("a redraw merged into the seventh queued", DOQ, (WRITE, SHELL, QPB_AT),
             to_write(seven_redraws, pp.redraw(PIPE_MESSAGES - 1, *SECOND_RECT)))
    register("a redraw none of seven merges with", DOQ, (WRITE, SHELL, QPB_AT),
             to_write(seven_redraws, pp.redraw(PIPE_MESSAGES, *SECOND_RECT)))
    register("a read of the only message", DOQ, (READ, SHELL, QPB_AT), merge_pokes(pp.holding(1), qpb(MESSAGE_BYTES, BUFFER_AT)))
    register("a read from a full pipe", DOQ, (READ, SHELL, QPB_AT),
             merge_pokes(pp.holding(PIPE_MESSAGES), qpb(MESSAGE_BYTES, BUFFER_AT)))
    register("a read of a whole full pipe", DOQ, (READ, SHELL, QPB_AT), whole_pipe_read())
    for label, handed in (("a write with room", writing(pp.running())),
                          ("a write queued on a full pipe", writing(pp.holding(PIPE_MESSAGES))),
                          ("a write served to the waiting reader", writing(pp.screen_manager_running())),
                          ("a read", reading(pp.holding(1))),
                          ("a read queued on an empty pipe", reading(pp.running())),
                          ("a read that frees the waiting writer", reading(pp.writer_waiting()))):
        register(label, AQUEUE, (handed.writing, handed.evb, handed.qpb), handed.machine)
    register("the screen manager", AP_FIND, (NAME_AT,), named(MANAGER_NAME))
    register("none of that name", AP_FIND, (NAME_AT,), named(b"NOSUCH  "))
    # ...and each through its call word: verified, unpriced.
    register("by name", PD_MATCH, (NAME_AT, SHELL_PID, MANAGER), named(MANAGER_NAME), through_line_f=True)
    register("by id", FPDNM, (PDPIPE["FPDNM_BY_PID"], SCREEN_MANAGER_PID), named(BLANK), through_line_f=True)
    register("the spare static PD", GETPD, (), pp.running(), through_line_f=True)
    register("the spare UDA", UDA_INSUPER, (SPARE_UDA,), pp.running(), through_line_f=True)
    register("a write behind one", DOQ, (WRITE, SHELL, QPB_AT), to_write(pp.holding(1), PLAIN), through_line_f=True)
    handed = writing(pp.screen_manager_running())
    register("a write served to the waiting reader", AQUEUE, (handed.writing, handed.evb, handed.qpb), handed.machine,
             through_line_f=True)
    register("the screen manager", AP_FIND, (NAME_AT,), named(MANAGER_NAME), through_line_f=True)


_register_rows()


# ---- THE ATTRIBUTION PASS NARROWED TO A CASE'S REASONS (`aes.run_function`'s `steered=`) ------------------------------------
def test_a_steered_case_makes_the_pass_but_for_the_words_its_reasons_name():
    """What a steered case's pass inverts: every byte the ROM's run stored — outside the stack band, the case's drops
    and the spans its reasons name — to the inverse of the value the run LEFT there."""
    index = SHELL + aes.PD_QUEUE_INDEX
    in_the_band, dropped_at, stored_at = case.STACK_BAND[0], aes.AES_LINEF_MASK_WORD, SHELL + aes.PD_QUEUE
    info = {"writes": {index: 0x00, index + 1: 0x10, in_the_band: 0x77, dropped_at: 0x3C, stored_at: 0x33, stored_at + 1: 0xFF}}
    inverted = aes._inverted_but_for(info, (pp.STEERS_THE_INDEX,), aes.LINE_F_MASK_WINDOW)
    assert inverted == {stored_at: bytes([0x33 ^ aes.BYTE_MASK, 0xFF ^ aes.BYTE_MASK])}
    assert index in aes._inverted_but_for(info, (), aes.LINE_F_MASK_WINDOW) and dropped_at in aes._inverted_but_for(info, (), ())


def test_a_reason_that_names_the_wrong_word_fails_the_narrowed_pass_by_name():
    """THE RED for a label: a write into the pipe said to be steered by the STACK (it is the index) fails its narrowed
    pass — the index, inverted with every other stored byte, sends the run astray — named as that pass's failure; and
    a reason is a reason (`aes.steers`), never a bare flag."""
    with pytest.raises(AssertionError, match="the attribution pass NARROWED to what the case says steers it"):
        write(pp.holding(1), PLAIN, steered=pp.STEERS_THE_STACK)
    with pytest.raises(AssertionError, match="opted out of by a reason"):
        write(pp.holding(1), PLAIN, steered=True)
    with pytest.raises(AssertionError, match="its reasons' to decide"):
        write(pp.holding(1), PLAIN, steered=pp.STEERS_THE_INDEX, poison=False)


def test_the_sweep_refuses_a_reason_the_case_survives_without(monkeypatch):
    """`STEERED_FOR_NOTHING_SWEEP`: every steered case makes its pass once more per reason, that reason's words inverted
    too — a write into the pipe really is steered by the index (it survives the sweep), and is not by the stack as
    well: named for nothing, refused by name."""
    monkeypatch.setenv(aes.STEERED_FOR_NOTHING_SWEEP, "1")
    write(pp.holding(1), PLAIN, steered=pp.STEERS_THE_INDEX)
    with pytest.raises(AssertionError, match="steered for nothing by .the stack pointer"):
        write(pp.holding(1), PLAIN, steered=(pp.STEERS_THE_INDEX, pp.STEERS_THE_STACK))
    monkeypatch.delenv(aes.STEERED_FOR_NOTHING_SWEEP)
    write(pp.holding(1), PLAIN, steered=(pp.STEERS_THE_INDEX, pp.STEERS_THE_STACK))     # ...which the suite's run does not ask


# ---- the class is held to its label, and out of the priced rows ----------------------------------------------------------------------
OVER_THE_APPLICATION = ("application(", "with_the_application(", "application_waiting(", "two_writers_waiting(",
                        "staged_application(")
OWN_ROWS = tuple(routines.core_symbol(name) for name in pp.SIGNATURES)


def test_every_case_over_the_staged_application_names_the_class():
    """A case of this battery that runs over a third process says so: `STAGED_APPLICATION` in its ids or its
    docstring (the tests OF the class's helpers name it in their own names)."""
    module = sys.modules[__name__]
    unlabelled = [name for name, function in vars(module).items()
                  if name.startswith("test_") and callable(function)
                  and any(machine in inspect.getsource(function) for machine in OVER_THE_APPLICATION)
                  and "STAGED_APPLICATION" not in inspect.getsource(function)
                  and "staged_application" not in name and "stub" not in name]
    assert not unlabelled, unlabelled


def static_pds_in(pokes):
    """The count of static PDs handed out (AES_STATIC_PIDS) in the machine `pokes` stage: the snapshot's word under
    whatever pokes cover it — read off the pokes, a row's whole image not built for one word."""
    word = bytearray(BASE_IMAGE[aes.AES_STATIC_PIDS:aes.AES_STATIC_PIDS + aes.WORD_BYTES])
    for at, data in pokes.items():
        for offset in range(aes.WORD_BYTES):
            if at <= aes.AES_STATIC_PIDS + offset < at + len(data):
                word[offset] = data[aes.AES_STATIC_PIDS + offset - at]
    return int.from_bytes(word, "big")


def rows_over_a_third_process():
    """EVERY REGISTERED ROW of this process whose machine has a third static PD handed out — which only a staged
    application's has: the priced and the unpriced rows of every component's registry (`case.ROW_REGISTRIES`) and
    the `.S` rows (`transcription.TRANSCRIPTIONS`, a list of its own that no `case.Rows` holds). "This process": in
    the suite every worker has imported every battery; a case run alone has this battery's rows and its `.S`
    battery's, imported here."""
    # ...imported HERE: the `.S` battery imports this module for its machines — at this module's top, a cycle.
    import test_aes_pdpipe_transcription        # noqa: F401  (its rows registered, for a case run alone)
    c_rows = [(name, pokes) for rows in case.ROW_REGISTRIES
              for name, _entry, _regs, pokes, *_seeds in (*rows.cases, *rows.unpriced)]
    s_rows = [(f"{symbol}, {label}", pokes)
              for label, symbol, _caller, _regs, pokes, _cost, _io_seed in transcription.TRANSCRIPTIONS]
    own = [name for name, _pokes in c_rows if name.split(",")[0] in OWN_ROWS]
    assert len(own) >= len(OWN_ROWS) and any(name.startswith(S_ROW_OF_PSETUP) for name, _pokes in s_rows)
    return [name for name, pokes in (*c_rows, *s_rows) if static_pds_in(pokes) != pp.SNAPSHOT_STATIC_PIDS]


S_ROW_OF_PSETUP = "aes_rom_psetup"


def test_no_registered_row_runs_over_a_staged_application():
    """TIER 1 ONLY: no row any battery registers — priced, through a call word, or a `.S` transcription's — starts
    from a machine with a third process: each has the snapshot's two, the spare PD not handed out."""
    assert static_pds_in(with_the_application()) == pp.SNAPSHOT_STATIC_PIDS + 1, "the probe does not see a staged application"
    assert rows_over_a_third_process() == []


def test_a_row_registered_over_a_staged_application_is_seen_whichever_list_it_is_in(monkeypatch):
    """...and it SEES one: a `.S` row and a C row — priced, then unpriced — registered over the staged application
    (into copies of the lists) are each named."""
    import test_aes_pdpipe_transcription as s_battery
    monkeypatch.setattr(transcription, "TRANSCRIPTIONS", list(transcription.TRANSCRIPTIONS))
    monkeypatch.setattr(transcription, "LABELS", dict(transcription.LABELS))
    monkeypatch.setattr(case, "ROW_REGISTRIES", list(case.ROW_REGISTRIES))
    s_battery.frames.register("over a staged application", PSETUP, (SPARE_PD, CODE), with_the_application())
    assert [name.split(",")[0] for name in rows_over_a_third_process()] == [S_ROW_OF_PSETUP]
    forged = case.Rows("a forged component")
    for priced in (True, False):
        forged.register(f"aes_fpdnm, over a staged application, priced {priced}", addrs.AES_ROM_FPDNM,
                        with_the_application(), priced=priced)
    assert len(rows_over_a_third_process()) == 3
