"""THE EVENT DOOR itself (`aes/evdoor.h`, `test/aes_event.py`): what its entries are, what its nested run is held to,
what each call hands it, what differs by nature and why, its refusals RED in a child process, and the machines its
batteries are run over — each the state the ROM's own scheduler leaves, pinned here to the scheduler's invariants.

The routines that go through it are other batteries' (`test_aes_grwait.py`, `test_aes_apmsg.py`); this file is the
door's own surface.
"""
import ctypes
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

import aes
import aes_event
import case
import test_aes_apmsg as apmsg
import test_aes_grwait as grwait
import vdi
import vdi_helpers
import vdi_mouse
from case import merge_pokes
from harness import BASE_IMAGE, addrs, emu, make_image

# ---- the entries ---------------------------------------------------------------------------------------------------
DOOR_ROUTINES = {"AES_ROM_EV_MULTI": addrs.AES_ROM_EV_MULTI, "AES_ROM_AP_RDWR": addrs.AES_ROM_AP_RDWR}


def test_the_door_serves_its_entries_and_nothing_else():
    assert set(aes_event.ENTRIES) == set(DOOR_ROUTINES.values())


@pytest.mark.parametrize("name", DOOR_ROUTINES)
def test_each_entry_is_what_its_callers_call_word_names(name):
    """The door `jsr`s each entry where the ROM's callers reach it through the Line-F call table: every call word of the
    text naming the routine names exactly that address — so skipping the handler lands on the same instruction."""
    sites = aes.line_f_call_sites(name)
    assert sites, f"no Line-F word of the GEM text calls {name}"
    assert {aes.line_f_target(word) for word in sites} == {DOOR_ROUTINES[name]}


def brute_force_call_sites(routine):
    """`aes.line_f_call_sites`' answer by its definition: the GEM text scanned for that one routine's call words."""
    sites = {}
    for at in range(*aes.AES_TEXT, aes.WORD_BYTES):
        word = case.word_in(BASE_IMAGE, at)
        if aes.line_f_target(word) == routine:
            sites[word] = (*sites.get(word, ()), at)
    return sites


@pytest.mark.parametrize("name", (*DOOR_ROUTINES, "AES_ROM_OB_OFFSET", "AES_ROM_GR_STILLDN"))
def test_the_call_site_index_answers_as_a_scan_for_one_routine_would(name):
    """`aes.line_f_call_sites` answers out of ONE index of the text's call words: the door's entries, a routine the table
    names twice (ob_offset), and one only reached by `bsr` and one call word, each as a scan for it alone finds them."""
    assert aes.line_f_call_sites(name) == brute_force_call_sites(getattr(addrs, name))


# ---- the nested run --------------------------------------------------------------------------------------------------
STILLDN_EVENTS = aes.EV_MU_BUTTON | aes.EV_MU_M1
STILLDN_RISE = aes.EV_BUTTON_LEFT << aes.EV_BUTTON_MASK_SHIFT | 1 << aes.EV_BUTTON_CLICKS_SHIFT | aes.EV_BUTTON_UP
MOBLK_AT = aes_event.MESSAGE_AT
ANSWERS_AT = MOBLK_AT + aes_event.MOBLK_BYTES


def stilldn_frame(leave, rectangle):
    """ev_multi's frame and machine as gr_stilldn hands them (BUTTON | M1, one rise of the left button): `(pokes,
    frame)`, the MOBLK staged at MOBLK_AT."""
    return ({MOBLK_AT: struct.pack(">5h", leave, *rectangle)},
            aes_event.EV_MULTI_FRAME.pack(STILLDN_EVENTS, MOBLK_AT, 0, 0, STILLDN_RISE, 0, ANSWERS_AT))


def nested_insns(routine, machine, pokes, frame):
    return aes_event.nested_run(routine, make_image(merge_pokes(machine, pokes)), frame).insns


# The deepest call of each entry the batteries make, each one the event layer ANSWERS: ev_multi answering gr_stilldn's
# mouse rectangle under the button down, and ap_rdwr handing a message to PD0's parked wait. `(machine, pokes, frame)`.
DEEPEST_CALLS = {
    addrs.AES_ROM_EV_MULTI: (grwait.button_down, *stilldn_frame(grwait.ENTER, grwait.AROUND_THE_MOUSE)),
    addrs.AES_ROM_AP_RDWR: (apmsg.screen_manager_running,
                            {apmsg.BUFFER: struct.pack(">8h", apmsg.WM_REDRAW, apmsg.SCREEN_MANAGER, 0, *apmsg.WORDS)},
                            aes_event.AP_RDWR_FRAME.pack(aes.AP_RDWR_WRITE, apmsg.SHELL, apmsg.APMSG["AP_MSG_BYTES"],
                                                         apmsg.BUFFER)),
}


def test_every_entry_has_its_deepest_call_measured():
    assert set(DEEPEST_CALLS) == set(aes_event.ENTRIES)


def test_the_nested_run_s_cap_is_far_above_the_deepest_run_the_batteries_make():
    """The cap holds NESTED_RUN_MARGIN times the deeper of the deepest calls."""
    deepest = max(nested_insns(entry, machine(), pokes, frame) for entry, (machine, pokes, frame) in DEEPEST_CALLS.items())
    assert deepest * aes_event.NESTED_RUN_MARGIN <= aes_event.NESTED_RUN_INSNS


@pytest.mark.parametrize("entry", DEEPEST_CALLS, ids=dict(zip(aes_event.ENTRIES, aes_event.ENTRY_NAMES)).get)
def test_an_answered_call_of_each_entry_reaches_no_dispatcher(entry):
    """MEASURED per entry: the path on which the event layer ANSWERS a call returns without ever reaching dsptch — no
    yield on the way — so the door's refusal of any dsptch it reaches refuses no call the event layer answers."""
    machine, pokes, frame = DEEPEST_CALLS[entry]
    image = bytearray(make_image(merge_pokes(machine(), pokes)))
    image[aes_event.abi.FIRST_ARG:aes_event.abi.FIRST_ARG + len(frame)] = frame
    _final, _writes, regs = emu.run(image, entry, max_insns=aes_event.NESTED_RUN_INSNS, stop_pc=addrs.AES_ROM_DSPTCH)
    assert not regs["checkpoint"]


def test_a_call_that_would_yield_is_refused_by_its_own_name():
    """A process still READY at dsptch would YIELD, not block: the dispatcher itself, called by PD0 running (what a
    process yielding does), is refused as that — the refusal tells a yield from a block by the process's status."""
    with pytest.raises(AssertionError, match="would yield"):
        aes_event.nested_run(addrs.AES_ROM_DSPTCH, make_image(aes_event.machine()), b"")


def test_a_nested_run_the_oracle_refuses_is_named_as_that(monkeypatch):
    """Only the cap's own refusal is "did not return within": any other the oracle makes keeps its cause."""
    def refused(*_args, **_kwargs):
        raise RuntimeError("unmodeled OS behaviour")
    monkeypatch.setattr(aes_event.emu, "run", refused)
    with pytest.raises(AssertionError, match="the oracle refused the nested run .*: unmodeled OS behaviour"):
        aes_event.nested_run(addrs.AES_ROM_EV_MULTI, BASE_IMAGE, b"")


def test_the_door_s_writes_are_compared(monkeypatch):
    """LOAD-BEARING: a door that answered the nested run's D0 but laid none of its writes back is red — the event layer's
    cancelled waits are compared memory, which the C reaches only through the door."""
    def answered_only(routine, io_seed):
        def serve(buf, frame, frame_bytes, answer):
            nested = aes_event.nested_run(routine, aes_event.ctypes.string_at(buf, aes_event.IMAGE_BYTES),
                                          aes_event.ctypes.string_at(frame, frame_bytes), io_seed)
            answer[0] = nested.answer
            return aes_event.SERVED
        return serve
    monkeypatch.setattr(aes_event, "_served", answered_only)
    with pytest.raises(AssertionError, match="oracle="):
        aes_event.run_event("AES_ROM_GR_STILLDN", (grwait.ENTER, *grwait.AROUND_THE_MOUSE), grwait.button_down())


# ---- what each call hands the door ---------------------------------------------------------------------------------------
def test_the_frames_handed_are_compared_with_the_rom_s():
    """LOAD-BEARING: the event layer answers gr_watchbox the same whatever rectangle its MOBLK holds (the button is up:
    the rise is satisfied first), so only the frame shows one. The frame the C handed over OK, held to the ROM's own
    call over Cancel — another rectangle — is red."""
    arguments = (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.NORMAL)
    aes_event.run_event("AES_ROM_GR_WATCHBOX", arguments, grwait.running(), drawing=True)
    (ours,) = aes_event.HANDED
    assert ours.arguments[1] is not None, "the premise: the MOBLK is read through its pointer"
    with pytest.raises(AssertionError, match="handed"):
        aes_event._vet_the_frames_handed("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.CANCEL, *arguments[2:]),
                                         grwait.running(), None)


def test_the_rom_s_frames_are_read_where_its_line_f_word_leaves_them():
    """The ROM's gr_stilldn hands ev_multi its OWN frame as the MOBLK (`pea 36(sp)`): read through the pointer it is
    the leave flag and the rectangle, as the call's arguments say."""
    (call,) = aes_event.rom_handed("AES_ROM_GR_STILLDN", (grwait.ENTER, *grwait.AROUND_THE_MOUSE), grwait.button_down())
    flags, moblk, second, timer, button, message, answers = call.arguments
    assert (call.routine, flags, button) == (addrs.AES_ROM_EV_MULTI, STILLDN_EVENTS, STILLDN_RISE)
    assert moblk == struct.pack(">5h", grwait.ENTER, *grwait.AROUND_THE_MOUSE)
    assert (second, timer, message, answers) == (None, 0, False, True)


def test_the_rom_s_watch_stops_at_the_entries_alone_and_refuses_one_entered_but_by_a_door_call():
    """The watch stops at the entries THEMSELVES — a set of exact PCs, so the event layer's routines between them run
    unwatched — then at the return address the call left; an entry reached from a return address no Line-F call of an
    entry leaves is refused."""
    back = min(aes_event.ROM_RETURNS)
    stack = 0x100
    memory = bytearray(stack) + back.to_bytes(aes.LONG_BYTES, "big")
    watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, lambda *_stop: None)
    assert watch.first == frozenset(aes_event.ENTRIES)
    assert watch.stopped(min(aes_event.ENTRIES), stack, memory) == frozenset({back})
    assert watch.stopped(back, stack, memory) == watch.first
    memory[stack:] = (back + aes.WORD_BYTES).to_bytes(aes.LONG_BYTES, "big")
    with pytest.raises(AssertionError, match="not a door call"):
        watch.stopped(min(aes_event.ENTRIES), stack, memory)


def test_only_the_recorded_pass_s_frames_are_kept():
    """`HANDED` is the hook's RECORDED pass alone, as its `calls` are: a second pass of the same case (an attribution
    pass) serving the same call hands nothing more."""
    machine, pokes, frame = DEEPEST_CALLS[addrs.AES_ROM_EV_MULTI]
    image = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer_copy(make_image(merge_pokes(machine(), pokes)))
    frame_buffer, answer = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame), (ctypes.c_uint32 * 1)()
    serve = aes_event._served(addrs.AES_ROM_EV_MULTI, None)
    one_pass = aes_event.EVENT_DOOR.recording(lambda _lib, _buf: serve(image, frame_buffer, len(frame), answer))
    aes_event.HANDED.clear()
    with aes_event.EVENT_DOOR.staged({}, aes_event._describe_refusals):
        one_pass(None, None)
        one_pass(None, None)
    assert len(aes_event.HANDED) == 1


# ---- what differs by nature: the BIOS trap's saved registers ----------------------------------------------------------
def test_the_drop_is_the_trap_save_s_registers_below_the_snapshot_s_savptr():
    """The event layer's keyboard poll takes ONE BIOS trap, whose save frame lies under the snapshot's `savptr`: the drop
    is its D3-D7/A3-A7 and leaves the return PC and SR after them compared."""
    (lo, hi, _why), = aes_event.TRAP_SAVE_DROP
    assert (lo, hi) == (aes_event.SNAPSHOT_SAVPTR - addrs.TRAP_SAVE_FRAME_BYTES,
                        aes_event.SNAPSHOT_SAVPTR - addrs.TRAP_SAVE_FRAME_BYTES + addrs.TRAP_SAVED_REGISTERS * aes.LONG_BYTES)
    _final, writes, _regs = emu.run(make_image(aes.staged("AES_ROM_GR_STILLDN", (grwait.LEAVE, *grwait.AROUND_THE_MOUSE),
                                                          grwait.running())), addrs.AES_ROM_GR_STILLDN)
    frame = range(lo, aes_event.SNAPSHOT_SAVPTR)
    assert all(at in writes for at in frame), "the ROM's run stores the whole save frame"


def test_without_the_drop_only_the_saved_registers_differ():
    """THE DROP'S EVIDENCE, red: gr_watchbox through the door with the trap save compared — the bytes that differ are all
    saved registers (its D4 reaches the trap untouched through ev_multi, the nested run's is 0)."""
    with pytest.raises(AssertionError) as raised:
        aes_event.run_event("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.NORMAL),
                            grwait.running(), drawing=True, dropped_windows=aes.LINE_F_MASK_WINDOW)
    (lo, hi, _why), = aes_event.TRAP_SAVE_DROP
    differing = [int(line.split("(0x")[1].split(")")[0], 16) for line in str(raised.value).splitlines() if "(0x" in line]
    assert differing and all(lo <= at < hi for at in differing), differing


def test_with_savptr_in_the_stack_band_nothing_but_the_mask_word_is_dropped():
    """The priced rows' machine (`aes_event.register`): `savptr` moved into the stack band, the save lands where nothing
    compares it — the same run compared with the mask word alone let go."""
    aes_event.run_event("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.NORMAL),
                        merge_pokes(grwait.running(), aes_event.savptr_in_the_band()), drawing=True,
                        dropped_windows=aes.LINE_F_MASK_WINDOW)


# ---- the door's refusals, RED in a child process ------------------------------------------------------------------------
STILLDN = ("AES_ROM_GR_STILLDN", (grwait.ENTER, *grwait.AROUND_THE_MOUSE))
WOULD_BLOCK = ("AES_ROM_GR_STILLDN", (grwait.LEAVE, *grwait.AROUND_THE_MOUSE))   # under the button down
ELSEWHERE = 0x00DEAD00                 # a vector or a table pointer that is not the snapshot's
SHORT_CAP = 100                        # a nested-run cap below any call the event layer answers


def test_a_moved_line_f_vector_halts_the_door_by_name():
    returncode, stderr, _image = aes_event.refusal(STILLDN[0], merge_pokes(grwait.running(), {
        addrs.VECTOR_LINE_F: struct.pack(">I", ELSEWHERE)}), STILLDN[1])
    assert returncode != 0 and "vector $2c" in stderr, stderr


def test_a_handler_copy_naming_another_table_halts_the_door_by_name():
    returncode, stderr, _image = aes_event.refusal(STILLDN[0], merge_pokes(grwait.running(), {
        aes.AES_LINEF_COPY + aes.LINEF_TABLE_OPERAND: struct.pack(">I", ELSEWHERE)}), STILLDN[1])
    assert returncode != 0 and "call table" in stderr, stderr


def test_an_entry_the_case_does_not_serve_is_refused_by_name():
    bind = aes_event.CHILD_BINDING.replace("bind_in_a_child(lib)", f"bind_in_a_child(lib, ({addrs.AES_ROM_AP_RDWR},))")
    returncode, stderr, _image = aes_event.refusal(*STILLDN[:1], grwait.running(), STILLDN[1], bind=bind)
    assert returncode != 0 and "does not serve" in stderr and "hook refused" in stderr, stderr


def test_the_snapshot_s_dispatcher_guard_does_not_turn_a_block_into_no_event():
    """THE RED the refusal exists for: the same wait over the dispatcher's guard set (the snapshot's AES_INDISP 1, which
    makes dsptch a bare `rts`) would come back as "no event" — an outcome no running process can have. It is refused
    the same way."""
    guarded = merge_pokes(grwait.button_down(), aes.field_pokes("AES", INDISP=aes.AES_INDISP_SET))
    returncode, stderr, _image = aes_event.refusal(*WOULD_BLOCK[:1], guarded, WOULD_BLOCK[1])
    assert returncode != 0 and "would block" in stderr, stderr


def test_a_door_effect_that_raises_in_a_child_is_refused_not_served():
    """A ctypes callback cannot raise into C: an exception escaping one answers an undefined word, which the core took
    for SERVED (measured: a frame the door's table could not read let the child's core return 0). Any exception the
    effect raises is a refusal, by name."""
    bind = CHILD_BINDING_UNREADABLE_FRAMES
    returncode, stderr, _image = aes_event.refusal(*STILLDN[:1], grwait.button_down(), STILLDN[1], bind=bind)
    assert returncode != 0 and "raised" in stderr and "hook refused" in stderr, stderr


CHILD_BINDING_UNREADABLE_FRAMES = aes_event.CHILD_BINDING.replace(
    "aes_event.bind_in_a_child(lib)", "aes_event.handed = None; aes_event.bind_in_a_child(lib)")


def test_a_nested_run_past_its_cap_is_refused_by_name():
    bind = aes_event.CHILD_BINDING.replace("aes_event.bind_in_a_child(lib)",
                                           f"aes_event.NESTED_RUN_INSNS = {SHORT_CAP}; aes_event.bind_in_a_child(lib)")
    returncode, stderr, _image = aes_event.refusal(*STILLDN[:1], grwait.button_down(), STILLDN[1], bind=bind)
    assert returncode != 0 and f"did not return within {SHORT_CAP}" in stderr, stderr


# A door user that draws as well (its VDI calls through `recreate_call_vector`), and one that does not.
CHILD_CALLS = {"gr_stilldn": (*STILLDN, grwait.button_down),
               "gr_watchbox": ("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.NORMAL),
                               grwait.running)}


@pytest.mark.parametrize("name, values, machine", CHILD_CALLS.values(), ids=CHILD_CALLS)
def test_the_child_binds_every_hook_into_the_candidate_it_calls(name, values, machine, monkeypatch, tmp_path):
    """The child calls the core out of the candidate `.so` it loaded, which need not be the one its `harness` import
    loads (a private build under a mutation sweep): a COPY of the candidate, a distinct library to the loader, is the
    one every hook the core reaches must be bound in — the door, and the VDI's cores for one that draws — or the core
    calls a NULL pointer. Over a machine the event layer answers, it returns."""
    copy = tmp_path / "candidate_copy.so"
    shutil.copyfile(vdi_helpers.LIB, copy)
    monkeypatch.setattr(vdi_helpers, "LIB", copy)
    returncode, stderr, _image = aes_event.refusal(name, machine(), values)
    assert returncode == 0, (returncode, stderr)


# ---- a child outlives neither its timeout nor its parent (`vdi_helpers.refusal`) ---------------------------------------
# A mutant core that spins in its child used to be ORPHANED, spinning for hours, whenever the parent died first — the
# watchdog's `_exit` of a worker blocked in the wait, a sweep killing pytest. Each child here spins on purpose and writes
# its PID to a file, so the case can name the process it then expects gone. Spinning in BYTECODE lets the child's
# parent-death watch run; spinning in one C call (`any` over an endless C iterator) holds the GIL and starves it, which
# leaves the alarm to end the child.
SPIN_IN_BYTECODE = "exec('while True: pass')"
SPIN_HOLDING_THE_GIL = "any(iter(int, 1))"
GONE_WITHIN_SECONDS = 5                # how long a child given to die is polled for, on a loaded machine
POLL_SECONDS = 0.05


def _spinning_prelude(pid_file, spin):
    return f"import os; open({str(pid_file)!r}, 'w').write(str(os.getpid())); {spin}"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _awaited(predicate, seconds):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > deadline:
            return False
        time.sleep(POLL_SECONDS)
    return True


def _pid_written(pid_file):
    return _awaited(lambda: pid_file.exists() and pid_file.read_text(), GONE_WITHIN_SECONDS) and int(pid_file.read_text())


def _reap(pid):
    """Ends `pid` if it is still alive — a RED run must not leave the very orphan it proves."""
    if _alive(pid):
        os.kill(pid, signal.SIGKILL)


def test_a_child_past_its_timeout_is_gone_when_the_helper_raises(tmp_path):
    pid_file = tmp_path / "child.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        vdi_helpers.refusal("aes_mul_div", [], "", prelude=_spinning_prelude(pid_file, SPIN_IN_BYTECODE), seconds=1)
    pid = int(pid_file.read_text())
    alive = _alive(pid)
    _reap(pid)
    assert not alive, f"the child {pid} outlived the helper's timeout"


# The parent the case kills: a process blocked in `refusal`, as an xdist worker is when the watchdog ends it. Its
# `seconds` is the child's wall budget; the GIL-held spin's is short, so its alarm (that budget and the grace) ends it
# within the case — and the parent must still be waiting when killed, or its own timeout ended the child instead.
PARENT = ("import sys; sys.path.insert(0, {test_dir!r}); import vdi_helpers; "
          "vdi_helpers.refusal('aes_mul_div', [], '', prelude={prelude!r}, seconds={seconds})")
GIL_HELD_SECONDS = 3
CHILD_SPINS = {"spinning in bytecode, the parent's death seen at once": (SPIN_IN_BYTECODE, vdi_helpers.CHILD_SECONDS, 0),
               "spinning with the GIL held, ended by its alarm": (SPIN_HOLDING_THE_GIL, GIL_HELD_SECONDS,
                                                                  GIL_HELD_SECONDS + vdi_helpers.CHILD_GRACE_SECONDS)}


@pytest.mark.parametrize("spin, seconds, alarm_seconds", CHILD_SPINS.values(), ids=CHILD_SPINS)
def test_a_child_whose_parent_dies_is_gone(spin, seconds, alarm_seconds, tmp_path):
    pid_file = tmp_path / "child.pid"
    source = PARENT.format(test_dir=str(Path(__file__).parent), prelude=_spinning_prelude(pid_file, spin), seconds=seconds)
    parent = subprocess.Popen([sys.executable, "-c", source])
    try:
        pid = _pid_written(pid_file)
        assert pid, "the child never started"
        assert parent.poll() is None, "the parent stopped waiting before it was killed: nothing was proved"
    finally:
        parent.kill()
        parent.wait()
    gone = _awaited(lambda: not _alive(pid), GONE_WITHIN_SECONDS + alarm_seconds)
    _reap(pid)
    assert gone, f"the child {pid} outlived its parent"


# ---- the machines ----------------------------------------------------------------------------------------------------
def machine_after(pokes):
    return make_image(merge_pokes(aes.leaf_machine(), pokes))


MACHINES = {"pd0_running": (aes_event.pd0_running, aes.SHELL_PD),
            "button_down": (aes_event.button_down, aes.SHELL_PD),
            "screen_manager_running": (aes_event.screen_manager_running, aes.SCREEN_MANAGER_PD)}


@pytest.mark.parametrize("woken, pd", MACHINES.values(), ids=MACHINES)
def test_each_machine_is_a_running_process_the_scheduler_made(woken, pd):
    """Over the snapshot itself (`make_image`, no lever under it) and as the door's machine (the cursor hidden after):
    the process the event woke is running exactly as switchto leaves one."""
    for image in (make_image(woken()), make_image(aes_event.machine(woken))):
        assert aes_event.scheduler_state(image, pd) == aes_event.running_as_switchto_leaves_it(pd)


def test_the_invariants_refuse_the_poked_running_process():
    """THE RED those invariants exist for: the lever's poked `rlr` over PD0's waits cancelled alone (the ROM's acancel)
    is no state the scheduler makes — PD0 still waiting and on the not-ready list, PD1 chained into the 'ready' list
    through its link, the guard set."""
    waiting = case.word_in(BASE_IMAGE, aes.SHELL_PD + aes.PD_EVWAIT)
    cancelled, _final, _regs = aes_event.derived(addrs.AES_ROM_ACANCEL, {}, frame=struct.pack(">H", waiting))
    assert (aes_event.scheduler_state(machine_after(cancelled), aes.SHELL_PD)
            != aes_event.running_as_switchto_leaves_it(aes.SHELL_PD))


def test_a_derivation_that_reaches_the_dispatcher_is_refused():
    """THE RED for `aes_event.derived`'s stop at dsptch: ev_multi asked to wait for the mouse to leave a rectangle it is
    inside, under the button down, BLOCKS — a derivation keeping that run's writes would carry a process switched away."""
    pokes, frame = stilldn_frame(grwait.LEAVE, grwait.AROUND_THE_MOUSE)
    with pytest.raises(AssertionError, match="reached the dispatcher"):
        aes_event.derived(addrs.AES_ROM_EV_MULTI, merge_pokes(grwait.button_down(), pokes), frame=frame)


def test_keys_are_what_the_keyboard_poll_takes():
    """Return queued by the BIOS's keyboard handler: the ROM's chkkbd, run over PD0 running, queues the keyboard's fork
    function, and forker running it moves the key into PD0's key queue."""
    state = merge_pokes(aes_event.pd0_running(), aes_event.keys(aes_event.RETURN_KEY, onto=aes_event.pd0_running()))
    delta, _final, _regs = aes_event.derived(addrs.AES_ROM_CHKKBD, state)
    delta, final, _regs = aes_event.derived(addrs.AES_ROM_FORKER, merge_pokes(state, delta))
    cda = case.long_in(final, aes.SHELL_PD + aes.PD_CDA)
    assert case.word_in(final, cda + aes.CDA_KEY_COUNT) == 1


def test_pd0_running_took_the_key_that_woke_it():
    """The key the desk's evnt_multi waited for is its answer, not a key left queued: nothing in PD0's queue."""
    final = make_image(aes_event.pd0_running())
    assert case.word_in(final, case.long_in(final, aes.SHELL_PD + aes.PD_CDA) + aes.CDA_KEY_COUNT) == 0


def button_records(image):
    """The left button as each layer records it: the AES's (AES_BUTTON), the VDI's (MOUSE_BT) and the VDI interrupt's
    own (CUR_MS_STAT, the buttons in its low bits) — on the machine all three move together, in the one interrupt."""
    return (case.word_in(image, aes.AES_BUTTON), case.word_in(image, vdi.LINEA_MOUSE_BT),
            image[vdi.LINEA_CUR_MS_STAT] & MOUSE_STAT_BUTTONS_MASK)


MOUSE_STAT_BUTTONS_MASK = vdi_mouse.MOUSE_H["MOUSE_STAT_BUTTONS_MASK"]
LEFT_DOWN = (aes_event.LEFT_BUTTON,) * 3


def test_button_down_is_the_aes_s_and_the_vdi_s_record():
    """The press came through the VDI's mouse interrupt: the AES, the VDI and the interrupt's state all say the left
    button is down, and the click is resolved."""
    final = make_image(aes_event.button_down())
    assert button_records(final) == LEFT_DOWN
    assert case.word_in(final, aes.AES_GL_CLICK_TICKS) == 0


def test_a_press_handed_to_the_aes_s_glue_alone_is_no_state_the_machine_holds():
    """THE RED the agreement exists for: the AES's button glue called directly (vex_butv's routine, skipping the VDI's
    interrupt that calls it) leaves the AES saying down and the VDI saying up — a state no interrupt leaves."""
    _pressed, final = aes_event._interrupt(addrs.AES_ROM_BUTTON_GLUE, {}, {"d0": aes_event.LEFT_BUTTON})
    assert button_records(final) != LEFT_DOWN


def test_window_chain_opens_a_window_that_posts_pd0_its_redraw():
    state, handle = aes_event.window_chain(aes_event.EVERY_GADGET, *CHAIN_RECT)
    final = machine_after(state)
    assert handle > 0
    assert case.word_in(final, aes.SHELL_PD + aes.PD_QUEUE_INDEX) > 0, "wm_open posted nothing"


CHAIN_RECT = (20, 30, 200, 100)
# A budget the wake by a key fits under, but not by DERIVATION_MARGIN (measured: 1,972 instructions).
TIGHT_BUDGET = 5_000


def test_every_derivation_is_held_far_under_its_budget(monkeypatch):
    """`aes_event._rom_run` holds EVERY derivation DERIVATION_MARGIN times under DERIVATION_INSNS: the deepest one — the
    window library's window moved by wm_set (`test_aes_wmlib.moved`, imported here rather than at the module's import,
    which would register its rows) — is run through it here, afresh; and the margin is a real bound: under a budget the
    wake by a key fits, but not by the margin, the derivation is refused by name."""
    import test_aes_wmlib as wmlib
    wmlib.moved.__wrapped__()
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", TIGHT_BUDGET)
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        aes_event._woken(aes_event.keys(aes_event.RETURN_KEY))
