"""THE SWITCH, COMPOSED: the host's model of disp over savestate and switchto (`src/aes/evdisp.c`)
against the ROM's own run THROUGH ITS DISPATCHER — and our whole dispatcher on target, where the switch is real.

WHAT A DIFFERENTIAL OF A REAL SWITCH COMPARES. The ROM's side is ONE RUN of a running process's call, through dsptch,
disp, savestate, the dispatcher's loop and switchto, back to the call's own return (`aes_switch.scheduled`: V3 — the
interrupts a case delivers laid at the n-th idle, where the machine waits for one). Ours is the event layer's C with
the dispatcher's hook bound to the C scheduler for this run alone (`aes_switch.modelled`), handed the same
deliveries at the same idles. Compared: that the call RETURNS, its answer, and the WHOLE IMAGE — every list, PD,
EVB, CDA, pipe and queue, the guard, `gl_cda`, disp's own argument slot — but, each only where the ROM's run stored
it (V4): the calling process's saved context in its UDA, the dispatcher's stack, the dispatcher's SR save word, and
what every event-layer case drops (the Line-F mask word, the keyboard poll's trap save).

THE MODEL IS SWITCHED ON PER CASE: every other run of the suite still refuses at dsptch (`aes_event`'s binding), so
no committed case or row moves.

  * SELF-RESUME — the process the scheduler comes back to is the caller: the C's call returns. A yield with nothing
    else ready; a wait blocked and then woken by a key, a press, ticks; the lock handed over, its waiter queued
    behind the caller.
  * A FOREIGN PROCESS — the scheduler enters another process first: it runs as THE ROM'S OWN CODE, a nested run from
    switchto until the ROM's disp is about to enter the caller again (the process hook), and the C's call returns.
    The process is the snapshot's own screen manager, woken by the mouse on the menu bar: its continuation is the
    ROM's, not a harness's call.
  * WHAT DOES NOT END — a wait nothing wakes — is refused BY NAME at the idle the ROM's run itself never leaves.

WHAT THE MODEL DOES NOT DO IS LOAD A CONTEXT: a host core has no CPU to load one into. switchto's load is held where
it is real — `switch.S`'s own bytes, entered with one register file on both shores (`test_aes_switch.py`).

AND ON TARGET the yield is a returning call of our own dispatcher — `switch.S`'s dsptch, disp, savestate and
switchto round the C of forker, idle and chkkbd — priced as a row, which is also where its use of the dispatcher's
640-byte stack is measured.
"""
import ctypes
import functools
import re
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, _lib, addrs, bench_tier3, emu, make_image
from recreate_kit import asm_twin
from recreate_kit.rom_bench import RomBench

import abi
import aes
import aes_event
import aes_evinput as evinput
import aes_evlib
import aes_stack
import aes_switch as switch
import aes_switching
import case
import derived
import isr
import routines
import test_aes_wm_update as wm_update
import transcription
import vdi
from case import merge_pokes

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
SHELL, SCREEN_MANAGER = switch.SHELL, switch.SCREEN_MANAGER
EVWAIT = aes.header_constants("evwait.h")
# dsptch off target is the header's inline, which the library exports under a name of its own (`src/aes/evdoor.c`).
DSPTCH, DSPTCH_ENTERED = switch.DSPTCH, "aes_dsptch_entered"
_lib.aes_dsptch_entered.restype, _lib.aes_dsptch_entered.argtypes = None, [ctypes.POINTER(ctypes.c_uint8)]
EV_BLOCK, EV_BUTTON, UNSYNC = aes_evlib.EV_BLOCK, aes_evlib.EV_BUTTON, aes_evlib.UNSYNC
WORD_ANSWER, NO_ANSWER = WORD_BYTES, 0
A_DELAY_TICKS = 5
RETURN = aes_event.key(aes_event.RETURN_KEY)
RETURN_KEY_CODE = evinput.RETURN_KEY_CODE
ONTO_THE_BAR = aes_event.move_to(*aes_event.MENU_BAR_POINT)
OFF_THE_BAR = aes_event.move_to(*aes_event.A_POINT_ON_THE_DESKTOP)    # below the menu bar, on no window


# ---- the cases: a running process's call, what is delivered at which idle, and what the dispatcher then enters --------------
# `entered`: the processes the ROM's dispatcher enters, in order — the case's PREMISE, held on the ROM's own run.
Call = namedtuple("Call", "name arguments machine at_idle entered answers foreign", defaults=(False,))


def _core_of(name):
    return DSPTCH_ENTERED if name == DSPTCH else routines.core_symbol(name)


def _frame_of(name, arguments):
    return b"" if name == DSPTCH else aes.alcyon_frame(name, *arguments)[abi.FIRST_ARG]


WOKEN_BY_A_KEY = "a wait for a key, blocked; woken by Return at the first idle"
WOKEN_BY_A_PRESS = "a wait for a press, blocked; woken by the press at the first idle"
A_DELAY_RUN_OUT = "a delay, blocked; run out by its ticks at the first idle"
THROUGH_THE_SCREEN_MANAGER = "a wait for a key; the mouse onto the bar wakes the screen manager, which runs and waits; then Return"
CASES = {
    "a yield, nothing else ready": Call(DSPTCH, (), aes_event.machine, {}, (SHELL,), NO_ANSWER),
    WOKEN_BY_A_KEY: Call(EV_BLOCK, (EVWAIT["IASYNC_KEYBOARD"], 0), aes_event.machine, {0: RETURN}, (SHELL,), WORD_ANSWER),
    WOKEN_BY_A_PRESS:
        Call(EV_BUTTON, (aes_evlib.SINGLE, aes_evlib.LEFT, aes_evlib.DOWN, aes_evlib.ANSWERS_AT), aes_evlib.desk_running,
             {0: aes_event.press}, (SHELL,), WORD_ANSWER),
    A_DELAY_RUN_OUT:
        Call(EV_BLOCK, (EVWAIT["IASYNC_DELAY"], A_DELAY_TICKS), aes_event.machine, {0: aes_event.ticks(A_DELAY_TICKS)},
             (SHELL,), WORD_ANSWER),
    "a delay, blocked; two ticks, an idle passed, then the rest":
        Call(EV_BLOCK, (EVWAIT["IASYNC_DELAY"], A_DELAY_TICKS), aes_event.machine,
             {0: aes_event.ticks(2), 2: aes_event.ticks(A_DELAY_TICKS - 2)}, (SHELL,), WORD_ANSWER),
    "the lock handed to the screen manager, which waits for it: a yield, the releaser resumed first":
        Call(UNSYNC, (wm_update.WIND_SPB,), wm_update.waited_on, {}, (SHELL,), NO_ANSWER),
    # ...the word AFTER the fork queue's count nonzero (`aes_switch.grabbed_while_shown`): disp's loop ends on the
    # count, a WORD — read wider, it would never end here.
    "a yield, nothing else ready; the control manager holds a mouse it found shown":
        Call(DSPTCH, (), lambda: switch.grabbed_while_shown(aes_event.machine()), {}, (SHELL,), NO_ANSWER),
    THROUGH_THE_SCREEN_MANAGER:
        Call(EV_BLOCK, (EVWAIT["IASYNC_KEYBOARD"], 0), aes_event.machine, {0: ONTO_THE_BAR, 1: RETURN},
             (SCREEN_MANAGER, SHELL), WORD_ANSWER, True),
    "a wait for a key; the mouse onto the bar and off it — the screen manager entered twice; then Return":
        Call(EV_BLOCK, (EVWAIT["IASYNC_KEYBOARD"], 0), aes_event.machine, {0: ONTO_THE_BAR, 1: OFF_THE_BAR, 2: RETURN},
             (SCREEN_MANAGER, SCREEN_MANAGER, SHELL), WORD_ANSWER, True),
}
FOREIGN = [name for name, call in CASES.items() if call.foreign]
# THE CASES A REGISTERED ROW HOLDS — the same call over the same machine through the same deliveries is a row that
# switches (three of the pilots below, `WOKEN_ROWS`; the press, the waits' own: `test_aes_evlib.py`). Its premise is
# its row's (`aes_switching.vet_the_premise`, in its battery) and the C through the host's scheduler its row's
# COMPANION (`aes_switching.companion`, run by `test_tier3.py` for every row: nothing left out but the run's stack,
# where the case's own compare left out the model's drops) — so neither is made a second time here. Their `Call`
# stays: the pilots are registered from it, and the REDs below are shown on it.
HELD_BY_A_REGISTERED_ROW = {
    WOKEN_BY_A_KEY: "aes_ev_block, a wait for a key, blocked; woken by Return at the first idle",
    WOKEN_BY_A_PRESS: "aes_ev_button, a press waited for, blocked; woken by it",
    A_DELAY_RUN_OUT: "aes_ev_block, a delay, blocked; run out by its ticks at the first idle",
    THROUGH_THE_SCREEN_MANAGER: "aes_ev_block, a wait for a key; the mouse onto the bar wakes the screen manager, which runs and "
                                "waits; then Return",
}
THE_MODEL_S_ALONE = [name for name in CASES if name not in HELD_BY_A_REGISTERED_ROW]


# A case's tests run back to back on one worker (`conftest.py`, `collected_with`): the ROM's scheduled run of a case —
# seventeen megabytes, its whole memory — is kept while its tests run and one case longer, not for the process's life
# (nine of them kept were 700 MB of one worker).
pytestmark = pytest.mark.collected_with(by=lambda params: params.get("name") if params.get("name") in CASES else None)
CASES_KEPT = 2


@functools.lru_cache(maxsize=CASES_KEPT)
def reference(name):
    """The ROM's own scheduled run of the case `name`: made once for the case's tests."""
    call = CASES[name]
    return switch.scheduled(getattr(addrs, call.name), _frame_of(call.name, call.arguments), call.machine(), call.at_idle)


def _typed(call):
    return () if call.name == DSPTCH else vdi.as_signed(call.name, call.arguments)


def _modelled(name, **kwargs):
    call = CASES[name]
    settings = {"answered": bool(call.answers), "foreign": call.foreign, **kwargs}
    return switch.modelled(_core_of(call.name), _typed(call), call.machine(), reference(name), **settings)


@pytest.mark.parametrize("name", THE_MODEL_S_ALONE)
def test_the_rom_s_run_is_the_case_its_name_says(name):
    """THE PREMISE of each case, on the ROM's own run: it RETURNS to the process that made the call, every interrupt
    delivered at an idle, the dispatcher having entered exactly the processes the case names."""
    call, the_rom_s = CASES[name], reference(name)
    assert the_rom_s.ended == switch.RETURNED and the_rom_s.entered == call.entered
    assert sorted(the_rom_s.delivered) == sorted(call.at_idle) and the_rom_s.idles > max(call.at_idle, default=-1)
    image = the_rom_s.memory
    assert aes.list_of(image, aes.AES_RLR)[0] == SHELL and image[aes.AES_INDISP] == 0


@pytest.mark.parametrize("name", THE_MODEL_S_ALONE)
def test_the_c_through_its_own_scheduler_leaves_the_machine_the_rom_s_dispatcher_leaves(name):
    call = CASES[name]
    left_out = switch.held_to_the_scheduled_run(name, reference(name), _modelled(name), switch.model_drops(SHELL),
                                                width=call.answers)
    uda = switch.uda_of(SHELL, BASE_IMAGE)
    context = set(range(uda + aes.UDA_REGS, uda + aes.UDA_TRAP_SSP))
    by_nature = left_out - set(case.STACK_BAND)
    assert by_nature & context, "the caller's saved context: what the ROM's savestate stored and no host core does"
    elsewhere = by_nature - context - set(range(*switch.DISPATCHER_STACK)) - aes_event.LINE_F_MASK_BYTES - {
        at for lo, hi, _why in aes_event.EVENT_LAYER_DROPS for at in range(lo, hi)}
    assert not elsewhere, f"left out of the compare, and no named drop: {sorted(map(hex, elsewhere))}"


def test_a_case_a_registered_row_holds_is_that_row_s_call_over_its_machine_through_its_deliveries():
    """THE PREMISE OF NOT MAKING THOSE CASES TWICE (`HELD_BY_A_REGISTERED_ROW`): each IS its row — the same entry and
    arguments, and, settled as the registrar settles a row, the same machine taken through the same deliveries. A
    row re-registered over another machine, or dropped, reds here: its case then belongs in the two tests above
    again."""
    import test_aes_evlib  # noqa: F401  (the press's row is the waits' battery's)
    for name, row_name in HELD_BY_A_REGISTERED_ROW.items():
        call, held = CASES[name], aes_event.SWITCHING_ROWS[row_name]
        assert (held.row.name, tuple(held.row.arguments)) == (call.name, tuple(call.arguments)), name
        made = aes_switching.settled(aes_switching.SwitchingRow("", call.name, tuple(call.arguments), call.machine,
                                                                dict(call.at_idle)))
        assert made.switches == held.switches and make_image(made.pokes) == make_image(held.pokes), name
        assert row_name in case.tier3_undropped(), f"{row_name}: no companion is registered for it"


def test_what_is_dropped_is_the_caller_s_context_and_the_dispatcher_s_own_and_nothing_of_the_lists():
    """WHAT THE DROPS HIDE, counted on the plainest case: of the image outside the run's stack the yield leaves out
    the 68 bytes of the desk's saved context the ROM stored, the dispatcher's stack as far as the ROM used it, its SR
    save word and the mask word — and every byte of every PD, EVB, CDA and list is compared."""
    name = "a yield, nothing else ready"
    left_out = switch.held_to_the_scheduled_run(name, reference(name), _modelled(name), switch.model_drops(SHELL))
    uda = switch.uda_of(SHELL, BASE_IMAGE)
    by_nature = left_out - set(case.STACK_BAND)
    assert not by_nature & set(range(aes.AES_PD_TABLE, aes.AES_PD_TABLE + aes.AES_PD_COUNT * aes.PD_BYTES))
    assert len(by_nature & set(range(uda, uda + aes.UDA_STATE_BYTES))) <= aes.UDA_TRAP_SSP - aes.UDA_REGS
    lowest = min(at for at in by_nature if switch.DISPATCHER_STACK[0] <= at < switch.DISPATCHER_STACK[1])
    assert aes.AES_DISPATCHER_STACK_TOP - lowest == THE_ROM_S_DEPTH


@pytest.mark.parametrize("name", FOREIGN)
def test_a_foreign_process_the_case_does_not_run_is_refused_by_name(name):
    """THE PROCESS HOOK'S REFUSAL: the same call with the model's foreign half off — the scheduler would enter the
    screen manager, and the C halts saying which process and that the call would switch away."""
    ran = _modelled(name, foreign=False)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    uda = switch.uda_of(SCREEN_MANAGER, BASE_IMAGE)
    assert f"would enter the process whose UDA is {uda:#x}" in ran.stderr and "the call would switch away" in ran.stderr


def test_an_idle_with_nothing_delivered_inside_a_foreign_process_is_refused_there():
    """...and the IDLE hook's refusal INSIDE THE PROCESS THE ROM'S OWN CODE RUNS: the first foreign case held to its
    run less the LAST delivery — the Return the ROM's dispatcher took while the screen manager's turn ended. The
    nested run idles past the ROM's count and is refused BY NAME there, once, and ended there."""
    name = FOREIGN[0]
    call, the_rom_s = CASES[name], reference(name)
    last = max(the_rom_s.delivered)
    less_the_last = the_rom_s._replace(delivered={idle: taken for idle, taken in the_rom_s.delivered.items() if idle != last})
    ran = switch.modelled(_core_of(call.name), _typed(call), call.machine(), less_the_last, answered=False, foreign=True)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert ran.stderr.count("(a process the ROM's own code runs)") == 1 and "the call would block" in ran.stderr, (
        "refused ONCE, at the idle: a run that went on idling says so again and again until its fork is ended")
    assert "the scheduler's hook raised" not in ran.stderr


def test_a_wait_nothing_wakes_is_refused_at_the_idle_the_rom_never_leaves():
    """A wait for a key and NOTHING delivered: the ROM's own run idles for ever (the driver ends it there, after the
    one idle it may pass); the C, held to that run, is refused by name at its second idle — the call would block."""
    arguments = (EVWAIT["IASYNC_KEYBOARD"], 0)
    the_rom_s = switch.scheduled(addrs.AES_ROM_EV_BLOCK, _frame_of(EV_BLOCK, arguments), aes_event.machine())
    assert the_rom_s.ended == switch.IDLES and the_rom_s.entered == () and the_rom_s.idles == 1
    ran = switch.modelled(_core_of(EV_BLOCK), vdi.as_signed(EV_BLOCK, arguments), aes_event.machine(), the_rom_s)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert "the idle hook: idle 1 (the C scheduler's)" in ran.stderr, "refused at its SECOND idle, not a later one"
    assert "idles once more than the ROM's own run did (1)" in ran.stderr and "the call would block" in ran.stderr
    assert ran.answer is None


def test_a_delivery_at_another_idle_than_the_rom_s_is_red():
    """THE HOOK LAYS WHAT THE ROM'S RUN TOOK, WHERE IT TOOK IT — and the comparison holds WHERE. Handed its key one
    idle LATER than the ROM's run took it, the C polls once more for nothing and ends in the very same machine: what
    reds is the count of idles, which is the surface an ordinal has."""
    name = WOKEN_BY_A_KEY
    call, the_rom_s = CASES[name], reference(name)
    late = the_rom_s._replace(delivered={1: the_rom_s.delivered[0]}, idles=the_rom_s.idles + 1)
    ran = switch.modelled(_core_of(call.name), _typed(call), call.machine(), late)
    assert ran.returncode == 0 and ran.idles == the_rom_s.idles + 1
    with pytest.raises(AssertionError, match="a wait more, or one fewer"):
        switch.held_to_the_scheduled_run(name, the_rom_s, ran, switch.model_drops(SHELL), width=call.answers)


def test_a_run_that_returns_in_another_process_is_refused_by_name():
    """THE DRIVER'S OWN REFUSAL. The machine the lock's case leaves — the screen manager READY, its wait for the lock
    one the HARNESS's call parked — and the desk waits for a key: the scheduler enters the screen manager, whose
    continuation is the harness's sentinel. The run "returns" there, in a process that never made the call."""
    handed = reference("the lock handed to the screen manager, which waits for it: a yield, the releaser resumed first")
    machine = aes_event.as_pokes(handed.memory, upto=addrs.ST_RAM_BYTES)
    arguments = (EVWAIT["IASYNC_KEYBOARD"], 0)
    with pytest.raises(AssertionError, match="reached its return in ANOTHER process"):
        switch.scheduled(addrs.AES_ROM_EV_BLOCK, _frame_of(EV_BLOCK, arguments), machine)


def test_another_answer_than_the_rom_s_is_red():
    """THE ANSWER IS HELD: the same C run, held to a ROM run that answered otherwise, is refused by name."""
    name = WOKEN_BY_A_KEY
    call, the_rom_s = CASES[name], reference(name)
    assert call.answers, "the case answers: the premise"
    with pytest.raises(AssertionError, match="answers .*, the ROM's run"):
        switch.held_to_the_scheduled_run(name, the_rom_s._replace(d0=the_rom_s.d0 ^ 1), _modelled(name),
                                         switch.model_drops(SHELL), width=call.answers)


def test_a_delivery_laid_over_another_machine_than_the_rom_s_is_refused_at_the_idle():
    """THE IDLE HOOK VETS BEFORE IT LAYS: handed a delivery the ROM's run took over a machine that is NOT the C's at
    that idle (one byte of what the ROM found there, changed), the hook refuses at the idle — the delivery would
    erase the difference, and the compare after it would never see it."""
    name = WOKEN_BY_A_KEY
    call, the_rom_s = CASES[name], reference(name)
    found, wrote = the_rom_s.delivered[0]
    first = min(found)                                          # the keyboard ring's own words: what a key overwrites
    other = {**found, first: bytes([found[first][0] ^ 1]) + found[first][1:]}
    ran = switch.modelled(_core_of(call.name), _typed(call), call.machine(), the_rom_s._replace(delivered={0: (other, wrote)}))
    assert ran.returncode not in (0, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert "differs from the ROM's where an interrupt is delivered at idle 0" in ran.stderr
    assert "idle 1" not in ran.stderr, "refused AT the idle: what a callback raises is not an idle served"


def test_a_delivery_the_c_is_never_handed_is_red():
    """...and held to a run whose delivery it is NOT handed, the C idles past the ROM's count and is refused."""
    name = WOKEN_BY_A_KEY
    call, the_rom_s = CASES[name], reference(name)
    ran = switch.modelled(_core_of(call.name), _typed(call), call.machine(), the_rom_s._replace(delivered={}))
    assert ran.returncode not in (0, aes_event.FORK_RAISED) and "the call would block" in ran.stderr


def test_the_model_refuses_a_dispatch_under_the_dispatcher_s_own_guard():
    """THE LEVER'S STATE, refused: over `aes.leaf_machine()` — the shell's PD running with the guard the snapshot
    holds — the ROM's dsptch is a bare `rts` (`test_aes_switch`); the model does not answer "nothing happened" for a
    state no process runs in: it halts by name, before it stores anything."""
    machine = aes.leaf_machine()
    ran = switch.modelled(DSPTCH_ENTERED, (), machine, None, answered=False)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert "dsptch reached with the dispatcher's guard set" in ran.stderr
    assert ran.image[:addrs.ST_RAM_BYTES] == bytes(make_image(machine)[:addrs.ST_RAM_BYTES])


def test_the_model_is_off_wherever_no_case_switches_it_on():
    """THE PER-CASE SWITCH: outside `aes_switch.scheduling` the dispatcher's hook is `aes_event`'s refuser — the same
    yield, run as every other battery's run is, halts at dsptch by name."""
    assert aes_event._the_dispatcher_s_hook_is_the_refuser()
    with switch.scheduling()():
        assert not aes_event._the_dispatcher_s_hook_is_the_refuser()
    assert aes_event._the_dispatcher_s_hook_is_the_refuser()
    over = make_image(aes_event.machine())
    buf = (ctypes.c_uint8 * len(over)).from_buffer(over)
    returncode, stderr = aes_event.in_a_fork(lambda: _lib.aes_dsptch_entered(buf))
    assert returncode not in (0, aes_event.FORK_RAISED) and aes_event.HALTED_AT_THE_DISPATCHER in stderr
    assert aes_event.YIELDS in stderr


# ---- WHAT A PARKED PROCESS'S CONTEXT IS ------------------------------------------------------------------------------------
def test_the_parked_screen_manager_resumes_inside_its_own_wait():
    """The snapshot's screen manager, as the machine's own scheduler parked it: the frame its UDA names, on its own
    supervisor stack, resumes at mwait's instruction after its dsptch — the PC every parked process of this ROM
    holds, and what a foreign process's nested run starts from."""
    frame = case.long_in(BASE_IMAGE, switch.uda_of(SCREEN_MANAGER, BASE_IMAGE) + aes.UDA_SUPER_SP)
    assert case.long_in(BASE_IMAGE, frame + aes_event.EXCEPTION_FRAME_PC) == addrs.AES_ROM_EV_MWAIT_RESUMED


# ---- A PROCESS NEITHER READY NOR WAITING, LABELLED -------------------------------------------------------------------------
# PD_STAT is 0 (ready) or 1 (waiting) wherever the AES stores it. This one is neither AS A WORD and "ready" as a byte:
# disp tests the word (`tst.w d0`, `cmp.w #1,d0`).
A_STATUS_NO_ROUTINE_SETS = 0x0100


def test_a_process_neither_ready_nor_waiting_is_put_on_no_list():
    """LABELLED — NO ROM CALLER MAKES THE MACHINE: the desk's PD_STAT POKED to a value no routine stores, and the
    desk calls the dispatcher. The ROM's disp tests the status for 0 and for 1 and FALLS THROUGH ($fe4dd8): the
    process is taken off the ready list and put on NEITHER — nothing can ever wake it, and the machine idles for
    ever. The C is held to that run where it stops: refused at the idle the ROM never leaves, the three lists the
    ROM's — the desk on none of them."""
    machine = merge_pokes(aes_event.machine(), aes.field_pokes("PD", SHELL, STAT=A_STATUS_NO_ROUTINE_SETS))
    the_rom_s = switch.scheduled(addrs.AES_ROM_DSPTCH, b"", machine)
    assert the_rom_s.ended == switch.IDLES and the_rom_s.entered == ()
    lists = (aes.AES_RLR, aes.AES_NRL, aes.AES_DRL)
    assert not any(SHELL in aes.list_of(the_rom_s.memory, head) for head in lists), "the premise: the ROM's desk is on no list"
    ran = switch.modelled(DSPTCH_ENTERED, (), machine, the_rom_s, answered=False)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert "the idle hook: idle 1 (the C scheduler's)" in ran.stderr and "the call would block" in ran.stderr
    assert [aes.list_of(ran.image, head) for head in lists] == [aes.list_of(the_rom_s.memory, head) for head in lists]
    assert case.long_in(ran.image, SHELL + aes.PD_LINK) == case.long_in(the_rom_s.memory, SHELL + aes.PD_LINK)


def test_the_ready_list_s_next_is_taken_as_the_long_it_is():
    """LABELLED — NO CALLER QUEUES A PROCESS BY ITS ADDRESS ON THE BUS: the screen manager queued behind the desk with
    a top byte in the pointer (the ROM's own disp_act, handed it so), and the desk yields. disp takes the ready
    list's next as the LONG it is (`move.l (a5),$9c16`), top byte and all, and would enter that process. The C is
    held where it stops — its process hook refuses: the case runs no other process — with the ready list's head the
    ROM's own at its call of switchto."""
    tagged = SCREEN_MANAGER | aes.BUS_TAG
    running = aes_event.machine()
    queued, _final, _regs = aes_event.derived(addrs.AES_ROM_DISP_ACT, running, frame=tagged.to_bytes(LONG_BYTES, "big"))
    machine = merge_pokes(running, queued)
    the_rom_s, _writes, regs = emu.run(make_image(machine), addrs.AES_ROM_DSPTCH, stop_pc=addrs.AES_ROM_DISP_SWITCHTO)
    assert regs["checkpoint"] and case.long_in(the_rom_s, aes.AES_RLR) == tagged, "the premise: the ROM's disp, at its switchto"
    ran = switch.modelled(DSPTCH_ENTERED, (), machine, None, answered=False)
    assert ran.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert f"would enter the process whose UDA is {switch.uda_of(SCREEN_MANAGER, BASE_IMAGE):#x}" in ran.stderr
    assert case.long_in(ran.image, aes.AES_RLR) == tagged
    assert case.long_in(ran.image, SCREEN_MANAGER + aes.PD_LINK) == case.long_in(the_rom_s, SCREEN_MANAGER + aes.PD_LINK) == SHELL


# ---- WHAT A HOOK RAISES ---------------------------------------------------------------------------------------------------
def _a_vet_that_fails(*_arguments):
    pytest.fail("a vet of the hook's own")


def test_what_a_hook_raises_is_refused_by_name_whatever_it_is(monkeypatch):
    """A `pytest.fail` INSIDE THE IDLE HOOK — no `Exception`, which ctypes would swallow and answer for — is refused
    BY NAME in the fork that serves the C, as an assertion's failure is: the case fails saying what was raised."""
    monkeypatch.setattr(switch.Scheduling, "_idle_over", _a_vet_that_fails)
    ran = _modelled("a wait for a key, blocked; woken by Return at the first idle")
    assert ran.returncode not in (0, aes_event.FORK_REACHED_A_HOOK), ran.stderr
    assert "the scheduler's hook raised Failed: a vet of the hook's own" in ran.stderr


def test_what_a_hook_raised_is_raised_again_as_its_binding_closes(monkeypatch):
    """...and in the process that holds the binding it is not lost with the refusal: the hook ANSWERS (refused — the C
    is never handed Python's exception), and the binding gives it its outcome as it closes: the case's failure,
    by the exception's type and words, chained to it (`address_hook.as_the_case_s_outcome`)."""
    monkeypatch.setattr(switch.Scheduling, "_idle_over", _a_vet_that_fails)
    over = make_image(aes_event.machine())
    buf = ctypes.cast((ctypes.c_uint8 * len(over)).from_buffer(over), ctypes.POINTER(ctypes.c_uint8))
    answered = []
    with pytest.raises(AssertionError, match="raised Failed: a vet of the hook's own") as failed:
        with switch.scheduling()() as bound:
            answered.append(bound._idle(buf))
    assert answered == [switch.REFUSED] and isinstance(failed.value.__cause__, pytest.fail.Exception)
    assert aes_event._the_dispatcher_s_hook_is_the_refuser(), "the binding closed: the pointers are back"


PYTEST_S_OWN = {"a skip": pytest.skip.Exception, "an xfail": pytest.xfail.Exception, "pytest.exit": pytest.exit.Exception}


@pytest.mark.parametrize("outcome", PYTEST_S_OWN.values(), ids=PYTEST_S_OWN)
def test_an_outcome_pytest_is_asked_for_inside_a_hook_is_that_outcome_as_its_binding_closes(monkeypatch, outcome):
    """...but what a hook asks OF PYTEST — a skip, an xfail, an exit of the session — is raised again ITSELF as the
    binding closes, never turned into a failure (the one mechanism's rule, `address_hook`)."""
    asked = outcome("asked of pytest inside the idle hook")

    def asking(*_arguments):
        raise asked
    monkeypatch.setattr(switch.Scheduling, "_idle_over", asking)
    over = make_image(aes_event.machine())
    buf = ctypes.cast((ctypes.c_uint8 * len(over)).from_buffer(over), ctypes.POINTER(ctypes.c_uint8))
    with pytest.raises(outcome) as raised:
        with switch.scheduling()() as bound:
            assert bound._idle(buf) == switch.REFUSED
    assert raised.value is asked


# ---- ON TARGET: THE YIELD THROUGH OUR OWN DISPATCHER ----------------------------------------------------------------------
# dsptch from a running process with nothing else ready is a RETURNING call — the one switch a row can price: our
# `switch.S` (dsptch, disp, savestate, switchto) round the C of disp_act, forker, idle and chkkbd, against the ROM's.
# Entered on BOTH shores with the bench's own register file (the callee-saved seeds), so the two saved contexts are
# one register file's — and differ in exactly the two longwords the Line-F handler leaves its own values in.
YIELD_LABEL = "a yield, nothing else ready"
YIELD_REGS = dict(asm_twin.CALLEE_SAVED_SEEDS)
THE_ROM_S_DEPTH = 188                   # the dispatcher's stack as the ROM's own yield uses it, in bytes
# ...and what the yield costs, the ROM's cycles and ours net of the entry both shores share, by blob (the shipped
# configuration's reaches the VDI binding's `.S` through its thunks): 0.91 and 0.92 of the ROM's on the whole run —
# the keyboard poll's VDI calls, which both shores run from the same ROM bytes, are four fifths of it.
YIELD_CYCLES = {"bench": (11582, 10468), "bench_shipped": (11582, 10588)}
# ...and the wait that blocks and is woken (a key typed ahead): 0.84 and 0.83 on the whole run.
WAIT_CYCLES = {"bench": (31690, 26416), "bench_shipped": (31690, 26102)}
BLOBS = switch.BLOBS


def _by_nature(uda):
    """The windows of a switching row that differ by nature between the ROM's run and any other build's: the Line-F
    mask word, the caller's saved context, the dispatcher's stack and its SR save word, an SR save word a bracket
    parks."""
    return (*aes.LINE_F_MASK_WINDOW, *switch.uda_context_drop(uda), *switch.DISPATCHER_STACK_DROP, *aes_event.sr_drops())


# A ROW THAT SWITCHES: the routine, its frame, the machine, and how much of the caller's saved context differs on
# target — D1 and D2 alone where both shores reach dsptch with one register file (the bare yield), the whole block
# where the caller is compiled code (a wait: Alcyon's registers inside mwait, GCC's inside ours).
# `regs`: the ROM's entry registers — the bench's own callee-saved seeds for the yield (so the two contexts are one
# register file's); none for a row that arrives at a door entry (Tier 3 re-runs such an original watched, with the
# case's image alone), whose context is dropped whole anyway.
SwitchingRow = namedtuple("SwitchingRow", "label name arguments machine context regs")
YIELD = SwitchingRow(YIELD_LABEL, DSPTCH, (), aes_event.machine, switch.line_f_scratch_drop, tuple(YIELD_REGS.items()))
SWITCHING_ROWS = (YIELD,)


def _typed_ahead():
    return aes_event.typed_ahead(aes_event.machine(), aes_event.RETURN_KEY)


# THE ROWS THAT BLOCK AND ARE WOKEN (`aes_switching.register`: watched at the dispatcher on both shores, priced) — the
# PILOTS of the rows that switch, one of each kind a run through the dispatcher can be:
#   * no delivery at all — the key is in the keyboard's own ring before the call, and the dispatcher's own idle polls it;
#   * AN INTERRUPT DELIVERED AT AN IDLE of our own dispatcher (the key; the ticks — whose wait and whose fork function
#     both raise the interrupt mask in C, so the bracket's save word is a drop held on both shores);
#   * ANOTHER PROCESS ENTERED: the mouse onto the menu bar wakes the snapshot's own screen manager, which our switchto
#     enters — the ROM's code, parked by the ROM — and which runs, takes the screen, and waits again; Return is then
#     delivered at the ROM's idle, and the ROM's dispatcher hands the machine back to OUR mwait (a FOREIGN WINDOW);
#   * AN INTERRUPT DELIVERED AT A POLL THAT IS NO IDLE, of our own dispatcher: the same move wakes the screen manager,
#     forker has run it, and idle polls the keyboard ONCE MORE — the manager woken, not yet ready — before it is
#     entered. Return arrives THERE: the key is polled ahead of the manager's turn and the desk answers it after it.
#     It is what holds WHERE in its loop our idle polls (`aes_switch.what_idle_tests`: a delivery there is checked
#     against which process stands woken and which ready).
A_KEY_TYPED_AHEAD_LABEL = "a wait for a key, blocked and woken: the key typed ahead, polled by the dispatcher's own idle"
POLLED_WHILE_THE_MANAGER_STANDS_WOKEN = ("a wait for a key; the mouse onto the bar wakes the screen manager; Return polled "
                                         "while it stands woken, before its turn")
THE_POLL_AFTER_THE_FIRST_IDLE = 1       # poll 0 is idle 0 (the move); forker runs mchange; idle polls again: this one
A_KEY_TYPED_AHEAD = aes_switching.register(A_KEY_TYPED_AHEAD_LABEL, EV_BLOCK, (EVWAIT["IASYNC_KEYBOARD"], 0), _typed_ahead)
WOKEN_ROWS = (A_KEY_TYPED_AHEAD,) + tuple(
    aes_switching.register(name, CASES[name].name, CASES[name].arguments, CASES[name].machine, CASES[name].at_idle)
    for name in (WOKEN_BY_A_KEY, A_DELAY_RUN_OUT, THROUGH_THE_SCREEN_MANAGER)) + (
    aes_switching.register(POLLED_WHILE_THE_MANAGER_STANDS_WOKEN, EV_BLOCK, (EVWAIT["IASYNC_KEYBOARD"], 0), aes_event.machine,
                           {0: ONTO_THE_BAR}, at_polls={THE_POLL_AFTER_THE_FIRST_IDLE: RETURN}),)


def _staged(row, pokes):
    return pokes if row.name == DSPTCH else aes.staged(row.name, row.arguments, pokes)


@functools.cache
@derived.kept
def _settled(row):
    """`(pokes, drops, the ROM's stores)` of a switching row, SETTLED from ONE run of the ROM's routine by the one
    settling every priced row's words are (`aes_event.settled_in_windows`): the keyboard poll's trap save in the
    stack band, and every byte that run stores in a WINDOW that differs by nature staged at the value it leaves —
    the mask word, the caller's saved context, the dispatcher's stack, the SR save words. What Tier 3 drops of
    them, each cut to the bytes that run stored: the mask word, the row's share of the context (our build saves its
    caller's own registers there), and the dispatcher's stack (which our image is then given back over: our frames
    go deeper than the ROM's). The SR save words are staged and NOT dropped: our build stores them as the ROM does."""
    machine = _staged(row, merge_pokes(row.machine(), aes_event.savptr_in_the_band()))
    final, writes, _regs = emu.run(make_image(machine), getattr(addrs, row.name), dict(row.regs))
    stored = {at: value for at, value in writes.items() if at not in case.STACK_BAND}
    uda = switch.uda_of(SHELL, final)
    pokes, drops = aes_event.settled_in_windows(
        machine, stored, _by_nature(uda),
        dropped=(*aes.LINE_F_MASK_WINDOW, *row.context(uda), *switch.DISPATCHER_STACK_DROP))
    return pokes, drops, frozenset(stored)


def _the_yield_row_s_machine():
    return _settled(YIELD)


def _answer_width(row):
    return case.NO_RESULT if row.name == DSPTCH else aes.RESULT_WIDTHS[vdi.ALCYON[row.name].restype]


def _companion(row):
    """A SWITCHING ROW'S COMPANION — the differential of the row's own machine with NOTHING dropped: the ROM's routine
    against the C through its own scheduler (the model switched on for the run; a leaf's one free idle is the poll
    that finds the key), child first. Every byte the row drops at Tier 3 is compared here: the ROM's run rewrites it
    with the value the machine stages, and the C must not store it."""
    pokes, _drops, _stored = _settled(row)
    typed = () if row.name == DSPTCH else vdi.as_signed(row.name, row.arguments)
    core = getattr(_lib, _core_of(row.name))
    forked = switch.modelled(_core_of(row.name), typed, pokes, None, answered=False)
    assert forked.returncode == 0, f"{row.label}: the C did not return in a fork ({forked.returncode}): {forked.stderr}"
    with switch.hooks()() as bound:
        info = case.run(getattr(addrs, row.name), {**dict(row.regs), "_pokes": pokes},
                        bound.recording(lambda _lib_, buf: core(buf, *typed)), width=_answer_width(row),
                        **aes.COMPANION_UNPOISONED)
    return aes.Result(info, pokes)


def _row_name(row):
    return f"{routines.core_symbol(row.name)}, {row.label}"


# THE YIELD IS PRICED HERE, with the bench's own entry registers (so its two saved contexts are one register file's);
# the rows that block and are woken are priced by `aes_switching.register`, above.
for _row in SWITCHING_ROWS:
    _pokes, _drops, _ = _settled(_row)
    aes.ROWS.register(_row_name(_row), getattr(addrs, _row.name), _pokes, regs=dict(_row.regs), dropped=_drops,
                      undropped=functools.partial(_companion, _row))


def _measured(blob):
    pokes, drops, _stored = _the_yield_row_s_machine()
    return blob.measure(addrs.AES_ROM_DSPTCH, "aes_dsptch", (0,), dict(YIELD_REGS), pokes, returns=NO_ANSWER,
                        dropped=drops)


THE_FIRST_DIFFERENCE = re.compile(r"first (0x[0-9a-f]+)")      # the kit's refusal: the lowest address the two images differ at


def test_without_its_stack_put_back_the_yield_differs_below_the_rom_s_deepest_store():
    """THE PREMISE of the row's one special arrangement, on the kit's own bench: our run's image differs from the
    ROM's on the dispatcher's stack BELOW everything the ROM's run stored — bytes no drop may name."""
    pokes, drops, stored = _the_yield_row_s_machine()
    with pytest.raises(AssertionError, match="left different memory") as refused:
        RomBench().measure(addrs.AES_ROM_DSPTCH, "aes_dsptch", (0,), dict(YIELD_REGS), pokes, returns=NO_ANSWER,
                           dropped=drops)
    first = int(THE_FIRST_DIFFERENCE.search(str(refused.value)).group(1), 16)
    assert switch.DISPATCHER_STACK[0] <= first < min(at for at in stored if at >= switch.DISPATCHER_STACK[0])


def test_our_dispatcher_yields_and_resumes_as_the_rom_s_on_both_blobs(blob):
    """THE SECOND DIFFERENTIAL of the whole switch, on target: our dsptch, disp, savestate and switchto round our C —
    the image the ROM's but for the row's named drops, every callee-saved register back (the kit's own vet: the
    switch keeps D2-D7/A2-A6 for a C caller, where the ROM's hands its caller back the Line-F handler's D2)."""
    measured = _measured(blob)
    assert measured.ratio <= bench_tier3().TIER3_FUNCTION_BAR, (
        f"the yield through our dispatcher costs {measured.ratio:.2f} of the ROM's: Tier 3's bar, held on the WHOLE run")
    assert (measured.original_net, measured.recreate_net) == YIELD_CYCLES[blob.elf.parent.name], (
        f"the yield measures {measured.original_net} / {measured.recreate_net} cycles: say why it moved")


def test_the_settling_changes_nothing_of_the_rom_s_run():
    """The bytes a switching row's machine stages beforehand change nothing of the ROM's run: over the unsettled
    machine it stores the same bytes at the same addresses, in as many instructions."""
    for row in SWITCHING_ROWS:
        pokes, _drops, stored = _settled(row)
        plain = _staged(row, merge_pokes(row.machine(), aes_event.savptr_in_the_band()))
        settled_run = emu.run(make_image(pokes), getattr(addrs, row.name), dict(row.regs))
        plain_run = emu.run(make_image(plain), getattr(addrs, row.name), dict(row.regs))
        assert settled_run[1] == plain_run[1] and frozenset(case.written_by(plain_run[1])) == stored, row.label
        assert bytes(settled_run[0][:addrs.ST_RAM_BYTES]) == bytes(plain_run[0][:addrs.ST_RAM_BYTES]), row.label
        assert settled_run[2]["ninsns"] == plain_run[2]["ninsns"], row.label


def test_a_wait_blocks_and_is_woken_through_our_own_dispatcher_on_both_blobs(blob):
    """THE FIRST ROW IN WHICH A PROCESS BLOCKS AND IS WOKEN ON TARGET, and it needs no delivery: the key is in the
    keyboard's own ring before the call. ev_block queues the wait and finds no key in the desk's queue; mwait marks
    the desk waiting and calls dsptch; our disp queues it NOT READY (mwait_act, through its thunk); forker finds
    nothing; our idle's poll takes the key from the BIOS and queues kchange — OUR entry; forker posts it and wakes
    the desk; idle moves it; switchto resumes it inside mwait, and ev_block answers the key. The image the ROM's but
    for the row's drops, every callee-saved register back."""
    measured, watch, _foreign = aes_switching.measured_on(blob, A_KEY_TYPED_AHEAD)
    assert measured.ratio <= bench_tier3().TIER3_FUNCTION_BAR, (
        f"the wait through our dispatcher costs {measured.ratio:.2f} of the ROM's")
    assert (measured.original_net, measured.recreate_net) == WAIT_CYCLES[blob.elf.parent.name], (
        f"the wait measures {measured.original_net} / {measured.recreate_net} cycles: say why it moved")
    assert (watch.idles, watch.entered, watch.foreign) == (1, [SHELL], [])


def test_the_typed_ahead_wait_really_blocks_and_is_woken_by_the_dispatcher():
    """The row's premise, on the ROM's own run: the call reaches dsptch WAITING (it blocks), the dispatcher's
    first idle finds the machine waiting for an interrupt — and its poll finds the key; the desk is entered again,
    and the call answers Return."""
    made = aes_switching.settled(A_KEY_TYPED_AHEAD)
    at_dsptch = aes_event.rom_at_dsptch(EV_BLOCK, A_KEY_TYPED_AHEAD.arguments, A_KEY_TYPED_AHEAD.machine())
    assert at_dsptch.switches == aes_event.BLOCKS
    the_rom_s = aes_switching.scheduled(A_KEY_TYPED_AHEAD, made.pokes)
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (switch.RETURNED, 1, (SHELL,))
    assert the_rom_s.d0 & aes.WORD_MASK == RETURN_KEY_CODE and not the_rom_s.delivered
    assert made.switches == aes_event.Switches({}, 1, SHELL, polls=the_rom_s.polls) and made.entered == (SHELL,)
    assert the_rom_s.polls == 2, "the idle, where its poll finds the key; and one more once forker has woken the desk"


@pytest.mark.parametrize("row", SWITCHING_ROWS, ids=lambda row: row.label)
def test_a_switching_row_s_companion_drops_nothing(row):
    assert _companion(row).staged == _settled(row)[0]


def test_the_yield_s_drops_are_what_they_say():
    """The row drops: the mask word; EIGHT bytes of the desk's UDA at most — D1 and D2, of which the ROM's run stores
    what differs from the machine's; and the dispatcher's stack, 188 bytes deep in the ROM's run. Nothing else."""
    _pokes, drops, stored = _the_yield_row_s_machine()
    uda = switch.uda_of(SHELL, BASE_IMAGE)
    named = {at for lo, hi, _why in drops for at in range(lo, hi)}
    assert named <= stored
    assert named - set(range(*switch.DISPATCHER_STACK)) - aes_event.LINE_F_MASK_BYTES <= set(
        range(uda + switch.D1_SLOT, uda + switch.D1_SLOT + 2 * LONG_BYTES))
    assert aes.AES_DISPATCHER_STACK_TOP - min(named & set(range(*switch.DISPATCHER_STACK))) == THE_ROM_S_DEPTH


# ---- THE DISPATCHER'S STACK: 640 BYTES, AND WHAT OUR BUILD AND AN INTERRUPT TAKE OF THEM -----------------------------------
# THE BOUND IS READ OFF THE BUILD (`aes_switch.StackReading`): the deepest SP our own code can reach under disp's
# four `jsr`s into C, down EVERY path of the blob's listing — and the deepest SP it can take a `trap #2` at, under
# which the OS goes on by as much as the deepest trap of the measured runs: the ROM's VDI (what the machine has), and
# THE BUILD'S OWN VDI linked under the trap as a ROM that ships links it (`aes_switch.our_loop_run(our_vdi=True)`),
# whose handlers are its own (`aes_switch.vdi_table_mapping`). So a recompile that deepens ANY frame under disp moves it, on a path no case runs
# as on the others.
# WHAT AN INTERRUPT NEEDS ON TOP is measured twice (`aes_switch`): the ROM's own handlers from their vectors, and
# OUR OWN ENTRIES (`src/bios/isr.S`) — which are the ROM's instructions and need exactly what the ROM's do; while
# each was a bracket round a C body they needed 192 / 188 / 152, and the worst nesting overran this stack by 60.
# The worst nesting the interrupt mask allows is a vertical blank with an MFP interrupt inside it.
# WHAT THE BOUND IS HELD TO: runs from disp's loop over the machines below, on both blobs — never deeper than the
# bound; their deepest trap EXACTLY the reading's (the recording played back reaches it), which is what says the
# reading counts the frames the build really pushes.
# WHAT THE BOUND COUNTS THAT NO MACHINE REACHES: forker -> bchange -> mowner -> wm_find -> ob_find -> ob_actxywh ->
# ob_offset. ob_find takes that arm for a start BELOW THE ROOT, and wm_find — its one caller under disp — starts at
# the root: a press on a window (below) goes as deep as ob_find's own frame and no further. The bound keeps the arm:
# it is what the listing can reach.
FORKER = evinput.FORKER
LOOP_MACHINES = {
    "a key typed ahead: the keyboard's poll": lambda: aes_event.typed_ahead(None, aes_event.RETURN_KEY),
    "a delay run out and the mouse on the bar: mchange and tchange": switch.a_delay_run_out_and_the_mouse_on_the_bar,
    "a press on a window's title: bchange looks for the window under it":
        lambda: evinput.at("a press on a window's title", FORKER, 1).machine,
    "a recording played back: mchange samples the locator": lambda: evinput.at("the desk plays a move back", FORKER, 1).machine,
}
# (The frame diet, 2026-10-10: bchange's frames under forker are 20 bytes flatter than they were, and the deepest run
# is now the one that takes the deepest trap — mchange's locator, with the VDI under it.)
THE_DEEPEST = THE_DEEPEST_TRAP = "a recording played back: mchange samples the locator"
DISPATCHER_STACK_BYTES = switch.DISPATCHER_STACK[1] - switch.DISPATCHER_STACK[0]
# MEASURED, by blob — the ROM's own beside them, which never moves off its keyboard poll: (the bound read off the
# build, the deepest a run of LOOP_MACHINES goes over the ROM's VDI, the deepest it takes a trap at, the deepest a
# run goes over OUR VDI). An entry that moves says a frame under disp changed: re-read the numbers, and the 640
# bytes less the interrupt's need.
# THE FRAME DIET, 2026-10-10 (`include/stack_diet.h`: forker, bchange, mchange, mowner, ob_find, post_button and
# post_mouse are marked for the screen manager's stack, and the dispatcher's loop runs the same routines): the bound
# was 356 on both blobs, the runs (300, 168, 328) and (312, 178, 338). ITS THIRD PASS, the same day: "over our VDI"
# had been the ROM's handlers behind our dispatcher; with the blob's OWN handlers bound (`aes_switch.vdi_table_mapping`)
# and the dispatcher's call keeping no register (44 bytes under every VDI function) the bound is the build's own
# frames under forker, 292 on both blobs — its deepest trap and our VDI under it are 274 / 284.
OUR_STACK = {"bench": (292, 260, 132, 274), "bench_shipped": (292, 270, 142, 272)}
# ...each the worst of every arm measured (`aes_switch._needs_measured`): timer C's 144 is the tick whose auto-repeat
# injects Alternate + an arrow — a mouse packet built by the keyboard, under the tick; every other tick needs 140.
THE_ROM_S_INTERRUPTS_NEEDS = switch.InterruptNeeds(acia=140, timer_c=144, vbl=100)
# OUR OWN ENTRIES', the same on both blobs — and the ROM's own, to the byte: `src/bios/isr.S` is the three handlers
# as the ROM has them. (With a C body under each entry they were 192 / 188 / 152: the pushed image pointer and the
# `jsr`, and the 40 to 52 bytes of callee-saved registers GCC saves under a call that keeps to nothing.)
OUR_INTERRUPTS_NEEDS = THE_ROM_S_INTERRUPTS_NEEDS
# The most the OS uses below a `trap #2` taken under disp — the AES's trap handler, the BIOS's door, the VDI's entry
# and the function called: through the ROM's VDI (the poll's vsm_string is the deepest), and through OUR OWN — the
# blob's entry, dispatcher AND handlers (the bench blob's vsm_locator under mchange is the deepest, 142; the shipped
# blob's vsm_string, 138). Lowest STORES, as `aes_stack.os_needs` are; the BIOS under their `trap #13` is the ROM's.
THE_ROM_S_OS_UNDER_A_TRAP, OUR_VDI_UNDER_A_TRAP = 130, 142
# ...AND THE UNSTORED TERM (the third pass's review asked whether this stack's bound carries one: it does now). A need
# is a lowest store; SP can have stood below it by the largest allocation nothing was stored under that a run reaches
# under the call (`aes_stack.unstored_under`, by opcode, on the blob's own VDI). THE CALLS THE DISPATCHER'S RUNS MAKE
# are the keyboard poll's and the locator's — five opcodes, none a raster call — and under those the blob's code
# reaches NO such allocation: the term is 0 on both blobs, charged in `_bound` and pinned, so that a call added under
# disp, or a frame of locals in one of these five handlers, moves a number here.
THE_DISPATCHER_S_VDI_CALLS = (addrs.VDI_ROM_LOCATOR_OPCODE, addrs.VDI_ROM_STRING_OPCODE, addrs.VDI_ROM_VSIN_MODE_OPCODE,
                              addrs.VDI_ROM_VQ_MOUSE_OPCODE, addrs.VDI_ROM_VQ_KEY_S_OPCODE)
UNSTORED_UNDER_ITS_TRAPS = 0
# WHAT IS LEFT of the dispatcher's 640 bytes under the build's deepest path with the worst nest on top, by blob —
# THE NEST AS THE SCREEN MANAGER'S STACK IS CHARGED IT (`aes_stack.nest`: a horizontal blank's 8 bytes under the
# vertical blank and the MFP interrupt inside it; band 4 charged the two alone, 244): 640 - (292 + 252). Before the
# frame diet (2026-10-10) it was 640 - (356 + 244) = 40, 32 with the horizontal blank. STATUS.md quotes it.
THE_SLACK = {"bench": 96, "bench_shipped": 96}


@functools.cache
def _loop_runs(directory, our_vdi=False):
    """Each machine's run from disp's loop on the blob of `directory` (None: the bench blob's)."""
    blob = RomBench(directory)
    return {name: switch.our_loop_run(blob, made(), our_vdi) for name, made in LOOP_MACHINES.items()}


def _directory_of(blob):
    return next(directory for directory in BLOBS.values() if RomBench(directory).elf == blob.elf)


def _runs_on(blob, our_vdi=False):
    return _loop_runs(_directory_of(blob), our_vdi)


def _under_a_trap(our_vdi=False):
    """The most the OS's own code used below a `trap #2`, over every trap of every run on both blobs — and, for the
    ROM's VDI, the ROM's own runs."""
    runs = [run for directory in BLOBS.values() for run in _loop_runs(directory, our_vdi).values()]
    if not our_vdi:
        runs += [switch.the_rom_s_loop_run(made()) for made in LOOP_MACHINES.values()]
    return max(under for run in runs for _taken_at, under in run.traps)


def _calls_under_disp(blob):
    """The VDI opcodes the runs from disp's loop on `blob` ask for, its own VDI under the trap."""
    return {opcode for run in _runs_on(blob, our_vdi=True).values() for opcode in run.opcodes}


def _unstored_under_its_traps(blob):
    """How far SP can have stood below the lowest store under a trap taken on the dispatcher's stack: the largest
    unstored allocation `aes_stack` finds reached under any call these runs make, on the blob's own VDI."""
    under, asked = aes_stack.unstored_under(aes_stack.shore_of(blob)), _calls_under_disp(blob)
    assert asked <= set(under), f"disp's runs ask the VDI for {sorted(asked - set(under))}, which `aes_stack` measures no need for"
    return max(under[opcode] for opcode in asked)


def _bound(blob):
    """The deepest `blob`'s build can take the dispatcher's stack: its own code's deepest, or its deepest trap and
    the OS under it — the ROM's VDI or the build's own with its unstored term, whichever goes deeper."""
    deepest, trapped, _use, _trap_use = switch.dispatcher_stack_reading(blob)
    return max(deepest, trapped + max(_under_a_trap(), _under_a_trap(our_vdi=True) + _unstored_under_its_traps(blob)))


def _refusal(blob, need, whose):
    deepest, _trapped, use, _trap_use = switch.dispatcher_stack_reading(blob)
    return (f"our dispatcher can go {_bound(blob)} bytes down its {DISPATCHER_STACK_BYTES}-byte stack ({deepest} by "
            f"{' -> '.join(use.path)}): with {whose} {need} on top it runs {_bound(blob) + need - DISPATCHER_STACK_BYTES} "
            f"bytes into what lies below it — the three SR save words first")


def test_our_frames_fit_the_dispatcher_s_stack_under_the_rom_s_own_handlers(blob):
    """THE DERIVED CHECK, the BIOS under our AES the ROM's: the deepest any path of this build's listing takes the
    dispatcher's stack, with the worst the ROM's own handlers need on top, is inside its 640 bytes — a store below
    $899a would land on the three SR save words."""
    need = aes_stack.nest()
    assert _bound(blob) + need <= DISPATCHER_STACK_BYTES, _refusal(blob, need, "the ROM's interrupt handlers'")


def test_our_frames_fit_the_dispatcher_s_stack_under_our_own_handlers(blob):
    """THE DERIVED CHECK ON A BUILD THAT SHIPS ITS OWN BIOS: the same bound with OUR entries' worst nesting on top.
    (A strict xfail while each entry was a bracket round a C body: 700 of 640.)"""
    need = aes_stack.nest(aes_stack.shore_of(blob))
    assert _bound(blob) + need <= DISPATCHER_STACK_BYTES, _refusal(blob, need, "our own interrupt entries'")


def test_our_own_handlers_need_what_the_rom_s_do_and_leave_what_status_says(blob):
    """...and the numbers STATUS.md quotes, MEASURED: our three entries' needs — the ROM's own — and what the worst
    nesting leaves of the stack."""
    needs = switch.our_interrupt_needs(blob)
    assert needs == OUR_INTERRUPTS_NEEDS == switch.interrupt_needs(), f"our interrupt entries need {needs}: say which frame moved"
    assert aes_stack.nest(aes_stack.shore_of(blob)) == aes_stack.hbl_need() + switch.worst_interrupt_need(needs)
    slack = DISPATCHER_STACK_BYTES - _bound(blob) - aes_stack.nest(aes_stack.shore_of(blob))
    assert slack == THE_SLACK[blob.elf.parent.name], f"{slack} bytes are left: re-quote STATUS.md"


def test_our_vertical_blank_returns_after_the_vdi_redrew_the_cursor(blob):
    """Our isr_vbl_entry over a machine whose shown cursor has just moved, run to its `rte`: the VDI's cursor routine
    in slot 0 returns with A6 = $fd00fe, and the whole run needs what the entry needs where that routine returns."""
    assert switch.our_vertical_blank_redrawing_the_cursor(blob) == OUR_INTERRUPTS_NEEDS.vbl


def test_our_vertical_blank_walks_on_past_a_slot_that_keeps_no_register(blob):
    """...and over the same machine with a slot routine behind the VDI's that leaves ALL ONES in D0-D7/A0-A6 — every
    register the ROM's handler tolerates a slot to change, its own `movem.l d7/a0` round each one and the bracket's
    `movem.l d0-a6` round the lot — and a marker behind that: our entry leaves the machine the ROM's handler leaves,
    and gives the interrupted program the same whole file back."""
    theirs, ours = switch.vertical_blanks_over_a_slot_that_keeps_nothing(blob)
    marks = bytes(theirs.final[switch.SLOT_MARKS_AT:switch.SLOT_MARKS_AT + 2])
    assert marks == bytes([isr.MARK] * 2), "the premise: the ROM's walk ran the slot that keeps nothing and the one behind it"
    assert not theirs.final[switch.CUR_FLAG], "the premise: the ROM's blank redrew the cursor"
    assert theirs.registers == isr.DIRTY_REGISTERS, "the premise: the ROM's handler gives every register back"
    differ = [at for at in aes_event._differing_addresses(ours.final, theirs.final, addrs.ST_RAM_BYTES)
              if at not in case.STACK_BAND and at not in switch.THE_ENTRY_NAMED]
    assert not differ, f"our blank leaves another machine than the ROM's at {[f'{at:#x}' for at in differ[:8]]}"
    assert ours.registers == theirs.registers


def test_the_stack_reading_is_what_was_measured(blob):
    """...and the numbers, held: the bound, the deepest measured run and the deepest trap, by blob — and the reading's
    deepest trap is EXACTLY the deepest trap a run takes, over the ROM's VDI and over ours."""
    deepest, trapped, _use, trap_use = switch.dispatcher_stack_reading(blob)
    runs, on_our_vdi = _runs_on(blob), _runs_on(blob, our_vdi=True)
    measured = max(run.deepest for run in runs.values())
    for made in (runs, on_our_vdi):
        taken_at = max(at for run in made.values() for at, _under in run.traps)
        assert taken_at == trapped, f"the deepest trap of the runs is at {taken_at}; the listing's ({' -> '.join(trap_use.path)}) at {trapped}"
        assert taken_at in [at for at, _under in made[THE_DEEPEST_TRAP].traps]
    assert runs[THE_DEEPEST].deepest == measured
    deepest_on_ours = max(run.deepest for run in on_our_vdi.values())
    assert max(measured, deepest_on_ours) <= _bound(blob), f"a run goes deeper than the listing's bound, {_bound(blob)}"
    assert (_under_a_trap(), _under_a_trap(our_vdi=True)) == (THE_ROM_S_OS_UNDER_A_TRAP, OUR_VDI_UNDER_A_TRAP), (
        f"the OS uses {_under_a_trap()} bytes under a trap, our VDI {_under_a_trap(our_vdi=True)}: say which call moved")
    assert (_calls_under_disp(blob), _unstored_under_its_traps(blob)) == (set(THE_DISPATCHER_S_VDI_CALLS), UNSTORED_UNDER_ITS_TRAPS), (
        f"disp's runs ask the VDI for {sorted(_calls_under_disp(blob))}, {_unstored_under_its_traps(blob)} bytes unstored under them")
    assert (_bound(blob), measured, trapped, deepest_on_ours) == OUR_STACK[blob.elf.parent.name], (
        f"the dispatcher's stack measures {(_bound(blob), measured, trapped, deepest_on_ours)}: say which frame moved")


def test_the_rom_s_own_dispatcher_never_goes_deeper_than_its_keyboard_poll():
    """THE ROM BESIDE IT: over the same machines its loop uses 188 bytes whatever is queued — Alcyon's frames under
    forker are shallower than the VDI call the poll makes — where ours goes deeper under forker than under the poll."""
    depths = {name: switch.the_rom_s_loop_run(made()).deepest for name, made in LOOP_MACHINES.items()}
    assert set(depths.values()) == {THE_ROM_S_DEPTH}, depths
    for directory in BLOBS.values():
        ours = _loop_runs(directory)
        assert ours[THE_DEEPEST].deepest > ours["a key typed ahead: the keyboard's poll"].deepest >= THE_ROM_S_DEPTH


def test_an_interrupt_s_need_is_the_rom_s_own_handlers_from_their_vectors():
    """WHAT AN INTERRUPT TAKES of the stack it lands on, measured: for an MFP interrupt at its worst 140 bytes by the
    ACIA's (the mouse packet's last byte) and 144 by timer C's (the tick that injects Alternate + an arrow's repeat;
    140 the tick that reaches the VDI's and the AES's), 100 for a vertical blank that redraws the cursor; the worst,
    the deeper MFP handler inside the blank."""
    needs = switch.interrupt_needs()
    assert needs == THE_ROM_S_INTERRUPTS_NEEDS
    assert switch.worst_interrupt_need() == needs.vbl + max(needs.acia, needs.timer_c) == 244


# THE READING'S OWN REDS, each over a listing of its own (`StackReading.of_listing`): the four shapes it used to pass
# in silence, and the two it follows.
A_LEAF = [(0x200, "rts")]


def _reading(body, **kwargs):
    return switch.StackReading.of_listing({"caller": body, "leaf": A_LEAF}, {0x200: "leaf"}, **kwargs)


@pytest.mark.parametrize("body, refused", [
    ([(0x100, "moveal %a2@(8),%a1"), (0x104, "jsr %a1@"), (0x106, "rts")], "a pointer read out of memory"),
    ([(0x100, "moveal %sp@(8),%a0"), (0x104, "jsr %a0@"), (0x106, "rts")], "a pointer read out of memory"),
    ([(0x100, "jsr %a3@"), (0x102, "rts")], "nothing it loads there names a function"),
    ([(0x100, "moveq #1,%d0"), (0x102, "trap #13"), (0x104, "rts")], "no frame of the OS under a trap"),
    ([(0x100, "trap #1"), (0x102, "rts")], "no frame of the OS under a trap"),
    ([(0x100, "subql #8,%sp"), (0x102, "addql #8,%sp")], "runs off the listed body's last instruction"),
    ([(0x100, "jmp %pc@(2,%d0:w)"), (0x104, "rts")], "does not follow the transfer"),
], ids=["a pointer of the machine", "a pointer handed in as an argument", "a register nothing loads", "a BIOS trap",
        "a GEMDOS trap", "a path off the body's end", "a jump through a table"])
def test_the_stack_reading_refuses_each_shape_it_cannot_follow_by_name(body, refused):
    with pytest.raises(AssertionError, match=refused):
        _reading(body).of("caller")


def test_the_stack_reading_follows_a_declared_pointer_and_a_function_loaded_by_value():
    """...and what it DOES follow: the pointer its caller declares (the callee four bytes deeper, whatever a function
    names by value elsewhere), a function GCC loaded into a register or spilt to a frame slot, and — at the call —
    the load that reaches it, whatever else the register holds elsewhere in the body."""
    deep = [(0x300, "lea %sp@(-40),%sp"), (0x304, "lea %sp@(40),%sp"), (0x308, "rts")]
    through_memory = [(0x100, "moveal %a2@(8),%a1"), (0x104, "jsr %a1@"), (0x106, "rts")]
    declared = switch.StackReading.of_listing({"caller": through_memory, "deep": deep}, {0x300: "deep"},
                                              through_a_pointer={"caller": ("deep",)})
    assert declared.of("caller").deepest == LONG_BYTES + 40
    by_value = [(0x100, "lea 300 <deep>,%a2"), (0x106, "moveal %a5@,%a0"), (0x108, "jsr %a2@"), (0x10a, "rts")]
    spilt = [(0x100, "movel #768,%sp@(4)"), (0x108, "moveal %sp@(4),%a0"), (0x10c, "jsr %a0@"), (0x10e, "rts")]
    reused = [(0x100, "moveal %a5@(4),%a0"), (0x104, "lea 300 <deep>,%a0"), (0x10a, "jsr %a0@"), (0x10c, "rts")]
    for body in (by_value, spilt, reused):
        read = switch.StackReading.of_listing({"caller": body, "deep": deep}, {0x300: "deep"})
        assert read.of("caller") == switch.StackUse(LONG_BYTES + 40, ("caller", "deep"), None, ("caller",)), body
    # ...and THE LOAD THAT REACHES A CALL IS READ NO FURTHER BACK THAN THE CALL'S OWN BLOCK: where another path joins
    # at the call (a branch lands on it), the load just above is one of two — every load of the function counts.
    joined = [(0x100, "beqs 108 <caller+0x8>"), (0x102, "lea 300 <deep>,%a0"), (0x106, "bras 10e <caller+0xe>"),
              (0x108, "lea 200 <leaf>,%a0"), (0x10e, "jsr %a0@"), (0x110, "rts")]
    read = switch.StackReading.of_listing({"caller": joined, "deep": deep, "leaf": A_LEAF}, {0x300: "deep", 0x200: "leaf"})
    assert read.of("caller").deepest == LONG_BYTES + 40, "the deeper of the two functions the register can hold there"


def test_the_pointers_the_reading_is_told_of_are_what_the_machine_s_hold():
    """THE DECLARATIONS, held to the machine: AES_DRWADDR holds the AES's bare `rts` in the snapshot (and the VDI's
    default cursor routine is what vex_curv hands back: the other routine declared), and a queue entry's code is one
    of the four fork functions."""
    drawn_by = case.long_in(BASE_IMAGE, aes.header_constants("gsxif.h")["AES_DRWADDR"])
    assert drawn_by == addrs.AES_ROM_JUSTRETF and switch.DRAWRAT_S_ROUTINES == ("aes_rom_justretf", "vdi_rom_default_user_cur")
    assert case.long_in(BASE_IMAGE, vdi.field("LINEA", "USER_CUR").at) == addrs.VDI_ROM_DEFAULT_USER_CUR
    assert switch.THROUGH_A_POINTER["aes_forker"] == sorted(switch.FORK_ENTRY_SYMBOLS.values())


def test_the_build_s_own_interrupt_entries_call_through_the_machine_s_vectors(blob):
    """...and why OUR handlers' needs are MEASURED, not read: each entry calls through a vector of the machine
    (KBDVECS, etv_timer, the vertical blank's queue) — a pointer the reading refuses by name."""
    for entry in switch.OUR_ENTRIES.values():
        with pytest.raises(AssertionError, match="a pointer read out of memory"):
            switch.StackReading(blob.elf, switch.THROUGH_A_POINTER).of(entry)


def test_the_stack_reading_refuses_an_instruction_that_sets_sp_it_does_not_know():
    """...an instruction that sets SP it does not know, and a frame pointer's `unlk`."""
    for text in ("unlk %fp", "moveal %a0@,%sp", "movel %d0,%sp"):
        with pytest.raises(AssertionError, match="does not follow"):
            switch._stack_effect(text)
    assert [switch._stack_effect(text) for text in (
        "moveml %d2-%d7/%a2-%fp,%sp@-", "moveml %sp@+,%d2/%a2-%a3", "lea %sp@(-12),%sp", "addql #8,%sp", "pea 0 <x>",
        "movew %sp@(18),%sp@-", "clrl %sp@-", "subql #8,%sp", "movel %sp@(48),%a3@(0,%d0:l)", "linkw %fp,#-4")] == [
        44, -12, 12, -8, 4, 2, 4, 8, 0, 8]
