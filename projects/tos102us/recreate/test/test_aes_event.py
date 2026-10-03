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
import aes_gsx
import case
import test_aes_apmsg as apmsg
import test_aes_fmalert as fmalert
import test_aes_fmdo as fmdo
import test_aes_fmlib as fmlib
import test_aes_grwait as grwait
import vdi
import vdi_helpers
import vdi_mouse
from case import merge_pokes
from harness import BASE_IMAGE, addrs, emu, make_image

# ---- the entries ---------------------------------------------------------------------------------------------------
DOOR_ROUTINES = {"AES_ROM_EV_MULTI": addrs.AES_ROM_EV_MULTI, "AES_ROM_AP_RDWR": addrs.AES_ROM_AP_RDWR,
                 "AES_ROM_TAK_FLAG": addrs.AES_ROM_TAK_FLAG, "AES_ROM_UNSYNC": addrs.AES_ROM_UNSYNC,
                 "AES_ROM_EV_BLOCK": addrs.AES_ROM_EV_BLOCK, "AES_ROM_CT_CHGOWN": addrs.AES_ROM_CT_CHGOWN,
                 "AES_ROM_POST_BUTTON": addrs.AES_ROM_POST_BUTTON, "AES_ROM_EV_BUTTON": addrs.AES_ROM_EV_BUTTON}


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


WU = aes.header_constants("wmupdate.h")


def _wm_update():
    """The window library's battery, imported where a case uses it rather than at this module's import, which would
    register its rows (and pay its derivations) in every worker that collects the door's own tests."""
    import test_aes_wm_update
    return test_aes_wm_update


def _mnlib():
    """...and the menu library's, the same way."""
    import test_aes_mnlib
    return test_aes_mnlib


def _locked():
    return _wm_update().locked()


def _mn_do_pressed_off_the_bar():
    mnlib = _mnlib()
    return merge_pokes(mnlib.screen_manager(mnlib.OFF_THE_BAR, True), mnlib.STALE_TRACK, mnlib.STALE_SR_RECT)


SECOND_MOBLK_AT = ANSWERS_AT          # a second MOBLK, where one-rectangle calls keep their answers...
TWO_RECTANGLE_ANSWERS_AT = SECOND_MOBLK_AT + aes_event.MOBLK_BYTES     # ...and the answers after it
assert TWO_RECTANGLE_ANSWERS_AT + aes.EV_MULTI_ANSWER_WORDS * aes.WORD_BYTES <= aes_event.BAND_AT + aes_event.BAND_BYTES


def rom_s_first_call(name, arguments, machine, interrupt=None):
    """The ROM's own `addrs.<name>` run over `machine` to the entry of its FIRST door call (`aes_event.rom_entered`):
    `(memory, call)` — the memory as the call finds it, and what it is handed; with `interrupt` delivered there first
    (`aes_event.deliveries`, at ordinal 0)."""
    delivered = aes_event.deliveries(name, arguments, machine, {0: interrupt} if interrupt else {})
    memory, call = aes_event.rom_entered(name, arguments, machine, delivered, 0)
    return bytearray(memory), call


def _mn_do_s_first_call(machine, interrupt=None):
    """mn_do's first ev_multi over `machine` (and `interrupt` delivered at its entry): the memory at its entry in the
    ROM's own run, and the call it makes there re-staged with its MOBLKs in the door's band — the ROM's lie in its own
    stack frame, which a nested run's stack would overwrite."""
    mnlib = _mnlib()
    image, call = rom_s_first_call(mnlib.MN_DO, (mnlib.TITLE_OUT, mnlib.ITEM_OUT), machine, interrupt)
    flags, first, second, timer, button, message, answers = call.arguments
    assert call.routine == addrs.AES_ROM_EV_MULTI and not message and answers
    image[MOBLK_AT:MOBLK_AT + len(first)] = first
    image[SECOND_MOBLK_AT:SECOND_MOBLK_AT + len(second)] = second
    return bytes(image), aes_event.EV_MULTI_FRAME.pack(flags, MOBLK_AT, SECOND_MOBLK_AT, timer, button, 0,
                                                       TWO_RECTANGLE_ANSWERS_AT)


def _mn_do_s_call():
    """...with the button pressed off the bar."""
    return _mn_do_s_first_call(_mn_do_pressed_off_the_bar())


def _mn_do_s_call_interrupted():
    """...with the mouse on the bar past the titles, moved onto "View" by an interrupt while pass 1 waits to enter
    them: the deepest nested run the batteries make."""
    mnlib = _mnlib()
    machine = merge_pokes(mnlib.screen_manager(mnlib.RIGHT_OF_THE_TITLES), mnlib.STALE_TRACK, mnlib.STALE_SR_RECT)
    return _mn_do_s_first_call(machine, aes_event.move_to(*mnlib.DROPPED["View"]))


def _a_call(machine, pokes, frame):
    return lambda: (make_image(merge_pokes(machine(), pokes)), frame)


# The deepest call of each entry the batteries make, each one the event layer ANSWERS: `label: (entry, () -> (image,
# frame))`. ev_multi's shapes — gr_stilldn's one mouse rectangle under the button down; mn_do's two rectangles with the
# button pressed off the bar, read off the ROM's own call; and the deepest of all, mn_do's first wait with the mouse
# moved onto a title by an interrupt at its entry — and ap_rdwr handing a message to PD0's parked wait.
SPB = aes_event.SEMAPHORE_FRAME.pack(WU["AES_WIND_SPB"])
FM_RISE = aes.header_constants("fmdo.h")     # fm_button's ev_button: one click, the left button, up
DEEPEST_CALLS = {
    "ev_multi, one rectangle": (addrs.AES_ROM_EV_MULTI,
                                _a_call(grwait.button_down, *stilldn_frame(grwait.ENTER, grwait.AROUND_THE_MOUSE))),
    "ev_multi, two rectangles": (addrs.AES_ROM_EV_MULTI, _mn_do_s_call),
    "ev_multi, two rectangles, the mouse moved onto a title": (addrs.AES_ROM_EV_MULTI, _mn_do_s_call_interrupted),
    "ap_rdwr": (addrs.AES_ROM_AP_RDWR,
                _a_call(apmsg.screen_manager_running,
                        {apmsg.BUFFER: struct.pack(">8h", apmsg.WM_REDRAW, apmsg.SCREEN_MANAGER, 0, *apmsg.WORDS)},
                        aes_event.AP_RDWR_FRAME.pack(aes.AP_RDWR_WRITE, apmsg.SHELL, apmsg.APMSG["AP_MSG_BYTES"],
                                                     apmsg.BUFFER))),
    # The screen lock: taken again by the process holding it, released by it; ct_chgown handing the screen to PD1 from
    # PD0 running (set_mown's mouse rectangle and post_button over another process).
    "tak_flag": (addrs.AES_ROM_TAK_FLAG, _a_call(_locked, {}, SPB)),
    "unsync": (addrs.AES_ROM_UNSYNC, _a_call(_locked, {}, SPB)),
    "ct_chgown": (addrs.AES_ROM_CT_CHGOWN, _a_call(aes_event.machine, {}, aes_event.CT_CHGOWN_FRAME.pack(
        aes.SCREEN_MANAGER_PD, aes.AES_GL_RSCREEN))),
    # mn_bar's fake click to the screen manager, parked in its button wait: it is woken (251 instructions).
    "post_button": (addrs.AES_ROM_POST_BUTTON, _a_call(aes_event.machine, {}, aes_event.POST_BUTTON_FRAME.pack(
        aes.SCREEN_MANAGER_PD, aes.MN_BAR_BUTTON, aes.MN_BAR_CLICKS))),
    # fm_button's wait for the rise after an object is taken, the button already up: answered at once (its four answer
    # words into the band's message buffer, which has the room).
    "ev_button": (addrs.AES_ROM_EV_BUTTON, _a_call(aes_event.machine, {}, aes_event.EV_BUTTON_FRAME.pack(
        FM_RISE["FM_RISE_CLICKS"], FM_RISE["FM_RISE_BUTTON"], FM_RISE["FM_RISE_UP"], aes_event.MESSAGE_AT))),
}
# The deepest of them, measured (`test_the_deepest_call_is_the_one_the_cap_is_derived_from`).
DEEPEST = "ev_multi, two rectangles, the mouse moved onto a title"
DEEPEST_NESTED_INSNS = 1_697


# The entries NO call answers: ev_block's one door user, wind_update(BEG_UPDATE) ($feca94), waits on the lock only after
# tak_flag REFUSED it, and amutex's own tak_flag then refuses the same state again — the wait is always queued and
# dsptch always reached (the call blocks: `test_aes_wm_update.test_the_lock_after_an_unbalanced_release_blocks`). An
# answered ev_block would be a call no program makes.
NEVER_ANSWERED = {addrs.AES_ROM_EV_BLOCK}


def test_every_entry_has_its_deepest_call_measured():
    """Every entry a call of which the event layer answers — every one but NEVER_ANSWERED's."""
    assert {entry for entry, _call in DEEPEST_CALLS.values()} == set(aes_event.ENTRIES) - NEVER_ANSWERED


def deepest_insns():
    """Each deepest call's nested-run instruction count, by label."""
    return {label: aes_event.nested_run(entry, *call()).insns for label, (entry, call) in DEEPEST_CALLS.items()}


def test_the_deepest_call_is_the_one_the_cap_is_derived_from():
    """mn_do's interrupted first ev_multi is the deepest nested run the batteries make, at the count
    NESTED_RUN_INSNS' comment derives the cap from — held NESTED_RUN_MARGIN times under it."""
    counts = deepest_insns()
    assert max(counts, key=counts.get) == DEEPEST and max(counts.values()) == DEEPEST_NESTED_INSNS
    assert DEEPEST_NESTED_INSNS * aes_event.NESTED_RUN_MARGIN <= aes_event.NESTED_RUN_INSNS


def test_a_nested_run_inside_the_cap_s_margin_is_refused_by_name(monkeypatch):
    """THE RED for the margin `nested_run` checks on every run: under a cap the deepest call fits, but not by
    NESTED_RUN_MARGIN, that call is refused by name — no hand-kept table has to notice a deeper caller."""
    entry, call = DEEPEST_CALLS[DEEPEST]
    monkeypatch.setattr(aes_event, "NESTED_RUN_INSNS", DEEPEST_NESTED_INSNS * aes_event.NESTED_RUN_MARGIN - 1)
    with pytest.raises(AssertionError, match="inside NESTED_RUN_INSNS' margin"):
        aes_event.nested_run(entry, *call())


@pytest.mark.parametrize("label", DEEPEST_CALLS)
def test_an_answered_call_of_each_entry_reaches_no_dispatcher(label):
    """MEASURED per entry: the path on which the event layer ANSWERS a call returns without ever reaching dsptch — no
    yield on the way — so the door's refusal of any dsptch it reaches refuses no call the event layer answers."""
    entry, call = DEEPEST_CALLS[label]
    image, frame = call()
    image = bytearray(image)
    image[aes_event.abi.FIRST_ARG:aes_event.abi.FIRST_ARG + len(frame)] = frame
    _final, _writes, regs = emu.run(image, entry, max_insns=aes_event.NESTED_RUN_INSNS, stop_pc=addrs.AES_ROM_DSPTCH)
    assert not regs["checkpoint"]


def test_a_call_that_would_yield_is_refused_by_its_own_name():
    """A process still READY at dsptch would YIELD, not block: the dispatcher itself, called by PD0 running (what a
    process yielding does), is refused as that — the refusal tells a yield from a block by the process's status."""
    with pytest.raises(AssertionError, match=aes_event.YIELDS):
        aes_event.nested_run(addrs.AES_ROM_DSPTCH, make_image(aes_event.machine()), b"")


def test_a_nested_run_the_oracle_refuses_is_named_as_that(monkeypatch):
    """Only the cap's own refusal is "did not return within": any other the oracle makes keeps its cause."""
    def refused(*_args, **_kwargs):
        raise RuntimeError("unmodeled OS behaviour")
    monkeypatch.setattr(aes_event.emu, "run", refused)
    with pytest.raises(AssertionError, match="the oracle refused the nested run .*: unmodeled OS behaviour"):
        aes_event.nested_run(addrs.AES_ROM_EV_MULTI, BASE_IMAGE, b"")


def bar_hidden_companion():
    """mn_bar hiding the bar: a routine that makes its own masked return AFTER its last door call (post_button) — its
    row's undropped companion, the mask word staged where the ROM's run leaves it."""
    mnlib = _mnlib()
    pokes = merge_pokes(mnlib.running(), aes_event.savptr_in_the_band())
    pokes = merge_pokes(pokes, aes.field_pokes("AES", LINEF_MASK_WORD=aes.settled_mask_word(mnlib.MN_BAR, (mnlib.MENU, 0),
                                                                                         pokes)))
    return aes.undropped(mnlib.MN_BAR, (mnlib.MENU, 0), pokes, aes_event.door_hook(True, objects=mnlib.JUST_DRAW))


def test_the_door_leaves_the_line_f_mask_word_as_the_c_found_it(monkeypatch):
    """The companion of a door row whose routine returns by a mask after the door passes — and is RED with the nested
    run's mask word laid back: the C would end on the door's last mask where the ROM ends on its own."""
    bar_hidden_companion()
    monkeypatch.setattr(aes_event, "LINE_F_MASK_BYTES", frozenset())
    with pytest.raises(AssertionError, match=f"{aes.AES_LINEF_MASK_WORD:#x}"):
        bar_hidden_companion()


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
    _entry, call = DEEPEST_CALLS["ev_multi, one rectangle"]
    staged, frame = call()
    image = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer_copy(staged)
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
    bind = aes_event.child_binding(entries=(addrs.AES_ROM_AP_RDWR,))
    returncode, stderr, _image = aes_event.refusal(*STILLDN[:1], grwait.running(), STILLDN[1], bind=bind)
    assert returncode != 0 and "does not serve" in stderr and "hook refused" in stderr, stderr


def test_the_snapshot_s_dispatcher_guard_does_not_turn_a_block_into_no_event():
    """THE RED the refusal exists for: the same wait over the dispatcher's guard set (the snapshot's AES_INDISP 1, which
    makes dsptch a bare `rts`) would come back as "no event" — an outcome no running process can have. It is refused
    the same way."""
    guarded = merge_pokes(grwait.button_down(), aes.field_pokes("AES", INDISP=aes.AES_INDISP_SET))
    returncode, stderr, _image = aes_event.refusal(*WOULD_BLOCK[:1], guarded, WOULD_BLOCK[1])
    assert returncode != 0 and aes_event.BLOCKS in stderr, stderr


def test_a_door_effect_that_raises_in_a_child_is_refused_not_served():
    """A ctypes callback cannot raise into C: an exception escaping one answers an undefined word, which the core took
    for SERVED (measured: a frame the door's table could not read let the child's core return 0). Any exception the
    effect raises is a refusal, by name."""
    bind = CHILD_BINDING_UNREADABLE_FRAMES
    returncode, stderr, _image = aes_event.refusal(*STILLDN[:1], grwait.button_down(), STILLDN[1], bind=bind)
    assert returncode != 0 and "raised" in stderr and "hook refused" in stderr, stderr


CHILD_BINDING_UNREADABLE_FRAMES = aes_event.child_binding(before="aes_event.handed = None; ")


def test_a_nested_run_past_its_cap_is_refused_by_name():
    bind = aes_event.child_binding(before=f"aes_event.NESTED_RUN_INSNS = {SHORT_CAP}; ")
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


# ---- the child's register-carrying hook: the walked routines served, or refused BY NAME -------------------------------
def _newrect():
    """newrect over a window above the desktop: its C hands everyobj mkrect by value (`test_aes_newrect.py`)."""
    import test_aes_newrect as newrect
    return "AES_ROM_NEWRECT", (newrect.WINDOW_TREE, newrect.WINDOW), newrect._NEWRECT_MACHINE


def test_a_child_bound_without_objects_refuses_a_walked_routine_by_name():
    """THE RED the always-bound hook exists for: a child whose core hands a walk a routine it was not bound to serve
    ENDS by name (CHILD_OBJECT_REFUSED) — the hook its `isr` import leaves would refuse the call silently, and the walk
    do nothing."""
    name, arguments, machine = _newrect()
    returncode, stderr, _image = aes_event.refusal(name, machine, arguments)
    assert returncode == aes_event.CHILD_OBJECT_REFUSED and f"{addrs.AES_ROM_MKRECT:#x}" in stderr, stderr


def test_the_object_exit_status_is_apart_from_the_orphan_s():
    assert aes_event.CHILD_OBJECT_REFUSED not in (vdi_helpers.CHILD_ORPHANED, aes_event.CHILD_VDI_REFUSED)


def test_a_child_bound_with_objects_serves_every_walked_routine_as_the_rom_runs_them():
    """`objects` serves the walked routines by the CHILD's own cores: newrect's walk of mkrect ends, in the child, where
    the ROM's own run of newrect ends — the whole image (`aes_event.interrupted`, no interrupt)."""
    aes_event.interrupted(*_newrect(), {}, objects=True)


def test_the_child_binding_names_its_arguments():
    """`child_binding` hands `bind_in_a_child` exactly what it is asked: the defaults name nothing."""
    assert aes_event.CHILD_BINDING.endswith("aes_event.bind_in_a_child(lib)")
    assert aes_event.child_binding(objects=True, entries=(1,), before="x = 1; ").endswith(
        "x = 1; aes_event.bind_in_a_child(lib, entries=(1,), objects=True)")


# ---- interrupts at a door entry, both shores (`aes_event.interrupted`) --------------------------------------------------
# gr_watchbox over the button down, OK outside the mouse: pass 1's wait answered at once, pass 2's (to enter) blocks.
WATCHED_OUTSIDE = ("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.CROSSED))
ENTERED_THEN_RELEASED = 3              # the passes: out, entered (the mouse moved in), the rise


def entered_then_released():
    return {1: aes_event.move_to(*grwait.the_middle_of(grwait.OK)), 2: aes_event.release}


def test_interrupts_take_both_shores_through_the_same_sequence():
    """The mouse moved onto OK at gr_watchbox's second wait, the button released at its third: the ROM's run and the C
    both return, inside (1), after three passes — the C's image the ROM's, every frame handed the same."""
    taken = aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)
    assert taken.returned and taken.answer == grwait.LEAVE and len(taken.calls) == ENTERED_THEN_RELEASED


def test_a_returning_case_is_taken_through_the_bench_s_second_differential_and_a_blocking_one_is_not(monkeypatch):
    """`interrupted` measures EVERY case whose ROM run returns as a row (`bench_differential`) — so no list of them can
    fall behind the batteries — and no case that blocks, which no row could price."""
    measured = []
    monkeypatch.setattr(aes_event, "bench_differential", lambda name, *_case: measured.append(name))
    aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)
    aes_event.refused_where_the_rom_blocks(*WATCHED_OUTSIDE, grwait.button_down(), objects=True)
    assert measured == [WATCHED_OUTSIDE[0]]


UNREAD_BYTE = aes_event.BAND_AT + aes_event.BAND_BYTES - 1     # a byte of the door's band no case here stages or reads
STALE_BYTE = 0x5A                      # ...and a value laid there


class _Measured(Exception):
    """`bench_differential` reached Tier 3's measurement."""


def _a_registered_fm_do_row():
    """One of fm_do's registered rows taken through interrupts (`aes_event.INTERRUPTED_ROWS`): `(row name, routine,
    arguments, settled machine, interrupts)` — the case a battery's twin of it hands `bench_differential`."""
    row_name, (name, arguments, pokes, interrupts, _delivered) = next(
        (row_name, row) for row_name, row in aes_event.INTERRUPTED_ROWS.items() if row[0] == fmdo.DO)
    return row_name, name, arguments, pokes, interrupts


def _measuring_refused(monkeypatch):
    def measuring():
        raise _Measured
    monkeypatch.setattr(aes_event, "_tier3", measuring)


def test_a_case_whose_row_is_registered_is_not_measured_a_third_time(monkeypatch):
    """A case that IS a registered row — the same routine, staged image and deliveries — is priced by Tier 3's own
    row test and table: its second differential does not measure it again..."""
    _row_name, *case_of_the_row = _a_registered_fm_do_row()
    _measuring_refused(monkeypatch)
    aes_event.bench_differential(*case_of_the_row)


def test_a_case_whose_row_is_not_registered_is_measured(monkeypatch):
    """...while the same case with no such row registered is."""
    _row_name, *case_of_the_row = _a_registered_fm_do_row()
    monkeypatch.setattr(aes_event, "INTERRUPTED_ROWS", {})
    _measuring_refused(monkeypatch)
    with pytest.raises(_Measured):
        aes_event.bench_differential(*case_of_the_row)


def test_a_case_unlike_every_registered_row_is_measured(monkeypatch):
    """...and so is a case of the same routine whose staged image, or whose deliveries, are no registered row's: a
    byte of the machine changed that nothing reads, or the same machine taken through Return alone."""
    _row_name, name, arguments, pokes, interrupts = _a_registered_fm_do_row()
    _measuring_refused(monkeypatch)
    for unlike in ((name, arguments, merge_pokes(pokes, {UNREAD_BYTE: bytes([STALE_BYTE])}), interrupts),
                   (name, arguments, pokes, aes_event.typed(aes_event.RETURN_KEY))):
        with pytest.raises(_Measured):
            aes_event.bench_differential(*unlike)


def test_a_twin_of_a_row_nobody_prices_is_refused_by_name(monkeypatch):
    """...and a skip is only for a PRICED row: deliveries recorded under a name no registry prices are refused."""
    row_name, *case_of_the_row = _a_registered_fm_do_row()
    monkeypatch.setattr(aes.ROWS, "cases", [row for row in aes.ROWS.cases if row[0] != row_name])
    with pytest.raises(AssertionError, match="no priced row"):
        aes_event.bench_differential(*case_of_the_row)


ODD_ACCESS_AT = aes_event.BAND_AT + 1  # an odd address our build alone is made to report


def test_the_second_differential_s_refusal_fails_the_interrupted_case(monkeypatch):
    """THE RED: our build answered an odd access the original's run was not — what no Tier 1 child reports — fails the
    interrupted case itself, through its second differential."""
    measure = aes_event.bench_differential

    def with_an_odd_access_of_ours(*case):
        none = {"odd_accesses": 0, "odd_addresses": (), "odd_first_pc": 0}
        answers = iter((none, dict(none, odd_accesses=1, odd_addresses=(ODD_ACCESS_AT,))))
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(emu, "odd_accesses", lambda: next(answers))
            measure(*case)
    monkeypatch.setattr(aes_event, "bench_differential", with_an_odd_access_of_ours)
    with pytest.raises(AssertionError, match="address error on a 68000"):
        aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)


def test_an_interrupt_the_c_is_not_handed_is_red(monkeypatch):
    """THE RED for the C's half: the same interrupts delivered to the ROM's run alone — the C's child blocks where the
    ROM's run, handed them, returns."""
    binding = aes_event.child_binding
    monkeypatch.setattr(aes_event, "child_binding", lambda interrupts=None, **kwargs: binding(**kwargs))
    with pytest.raises(AssertionError, match="the C's child did not"):
        aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)


def test_an_interrupt_the_rom_is_not_handed_is_red(monkeypatch):
    """...and for the ROM's: the interrupts computed, but not laid into the ROM's run — it blocks where the C, handed
    them, returns."""
    watched_through = aes_event._watched_through
    monkeypatch.setattr(aes_event, "_watched_through",
                        lambda name, arguments, pokes, delivered, stop_at=None, **kwargs: watched_through(
                            name, arguments, pokes, delivered if stop_at is not None else {}, stop_at, **kwargs))
    with pytest.raises(AssertionError, match="the C's did not"):
        aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)


def test_an_interrupt_at_a_call_the_rom_never_makes_is_refused():
    with pytest.raises(AssertionError, match=r"no door call to deliver \[5\] at"):
        aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), {5: aes_event.release}, objects=True)




def test_a_blocked_case_compares_the_whole_image_at_the_blocking_entry(monkeypatch):
    """`refused_where_the_rom_blocks` holds the C's child, refused at the call that blocks, to the ROM's memory at that
    call's ENTRY, byte for byte — RED with one byte of the child's image changed that neither the C nor the ROM reads,
    which a compare of the screen alone would pass."""
    aes_event.refused_where_the_rom_blocks(*WATCHED_OUTSIDE, grwait.button_down(), objects=True)
    dirty = aes_event.child_binding(objects=True, before=f"buf[{UNREAD_BYTE}] ^= 1; ")
    monkeypatch.setattr(aes_event, "child_binding", lambda **_binding: dirty)
    with pytest.raises(AssertionError, match=f"{UNREAD_BYTE:#x} oracle="):
        aes_event.refused_where_the_rom_blocks(*WATCHED_OUTSIDE, grwait.button_down(), objects=True)


def test_returns_in_a_child_fails_a_child_that_does_not_return():
    with pytest.raises(AssertionError, match=aes_event.BLOCKS):
        aes_event.returns_in_a_child(*WATCHED_OUTSIDE, grwait.button_down(), objects=True)


def test_a_guarded_run_runs_its_c_in_a_child_first(monkeypatch):
    """`run_guarded`'s guard is a PRECONDITION: a core that does not return in its child fails the case there, and the
    in-process differential — where a core that never returns would hang the worker — is never reached."""
    reached = []
    monkeypatch.setattr(aes_event, "run_event", lambda *call, **named: reached.append(call))
    with pytest.raises(AssertionError, match=aes_event.BLOCKS):
        aes_event.run_guarded(*WATCHED_OUTSIDE, grwait.button_down(), objects=aes.walkers())
    assert not reached


def test_a_guard_runs_one_child_per_distinct_call(monkeypatch):
    """The guard's child is run once per (routine, frame, machine, objects) in a worker: the same C call again — a
    case run directly and through its Line-F word — is not run again; another machine, or the walked routines served,
    is."""
    children = []
    monkeypatch.setattr(aes_event, "_RETURNED_IN_A_CHILD", set())
    monkeypatch.setattr(aes_event, "refusal", lambda *call, **named: children.append(call) or (0, "", None))
    for machine, objects in ((grwait.running(), False), (grwait.running(), False), (grwait.button_down(), False),
                             (grwait.running(), True)):
        aes_event.returns_in_a_child(*WATCHED_OUTSIDE, machine, objects=objects)
    assert len(children) == 3


# ---- what a delivery is checked against, and what it lays (`aes_event._laid_into`) -------------------------------------
def test_a_c_that_differs_where_an_interrupt_is_delivered_is_refused_by_name():
    """THE RED for the delivery's check: a delivery is the ROM's interrupt code run over the ROM's memory, so laid over
    a C whose image differs at an address it writes it would ERASE the divergence (measured before the check: GCURX
    corrupted in the child before the delivery, every compare green). One such byte changed in the C's image just
    before the delivery at ordinal 1, as a C that diverged there would hold it: the child ends by name."""
    name, arguments = WATCHED_OUTSIDE
    machine = grwait.button_down()
    delivered = aes_event.deliveries(name, arguments, machine, entered_then_released())
    found, _wrote = delivered[1]
    target = min(at for at in found if at not in aes_event._NOT_COMPARED)
    diverged = ("laid = aes_event._laid_into; aes_event._laid_into = lambda buf, delivery: "
                f"(buf.__setitem__({target}, buf[{target}] ^ 1), laid(buf, delivery)); ")
    bind = aes_event.child_binding(objects=True, interrupts=delivered, before=diverged)
    returncode, stderr, _image = aes_event.refusal(name, machine, arguments, bind=bind)
    assert returncode == aes_event.CHILD_DELIVERY_REFUSED and f"{target:#x}" in stderr, stderr


def test_a_delivery_lays_no_line_f_mask_word_into_the_c():
    """The C's image keeps the Line-F mask word as it found it at a delivery too, as at every nested run (`_served`):
    the AES's interrupt glue makes masked returns, so the ROM's deliveries write the word (the premise) — the C's final
    image holds the machine's own value there all the same."""
    machine = grwait.button_down()
    taken = aes_event.interrupted(*WATCHED_OUTSIDE, machine, entered_then_released(), objects=True)
    mask = sorted(aes_event.LINE_F_MASK_BYTES)
    staged = make_image(machine)
    delivered_mask = {at + offset: value for _found, wrote in taken.delivered.values() for at, data in wrote.items()
                      for offset, value in enumerate(data) if at + offset in aes_event.LINE_F_MASK_BYTES}
    assert delivered_mask and any(staged[at] != value for at, value in delivered_mask.items())
    assert [taken.image[at] for at in mask] == [staged[at] for at in mask]


# ---- the mouse moved: only where a packet can take it (`aes_event.move_to`) ----------------------------------------------
SCREEN_RIGHT = case.word_in(BASE_IMAGE, vdi.LINEA_DEV_TAB)     # DEV_TAB[0]: the screen's last column
PAST_THE_RIGHT_EDGE = (400, 10)        # measured: before the refusal, packets toward it forever, the cursor at x 319


def test_a_point_past_the_screen_s_edge_is_refused_by_name():
    """The mouse interrupt clamps the cursor to the screen: from the right edge, a packet toward a point past it leaves
    the cursor where it was — refused by name, where `move_to` would otherwise send packets forever."""
    x, y = PAST_THE_RIGHT_EDGE
    at_the_edge = bytearray(make_image(aes_event.mouse_moved_to(SCREEN_RIGHT, y, {})))
    assert (case.word_in(at_the_edge, vdi.LINEA_GCURX), case.word_in(at_the_edge, vdi.LINEA_GCURY)) == (SCREEN_RIGHT, y)
    with pytest.raises(AssertionError, match="cannot be moved to"):
        aes_event._step_toward(at_the_edge, x, y)
    with pytest.raises(AssertionError, match="cannot be moved to"):
        aes_event.move_to(x, y)(bytearray(make_image({})))


# ---- the ROM's watched runs, vetted however they end (`aes_event.run_watched`) -------------------------------------------
def test_a_watched_run_stopped_at_an_entry_is_held_to_the_margin(monkeypatch):
    """A run a watch ENDS at a door entry (`rom_entered`) leaves a prefix a case builds on (`rom_s_first_call`): it is
    held to DERIVATION_MARGIN as a whole run is — RED under a budget the prefix fits, but not by the margin."""
    name, arguments = WATCHED_OUTSIDE
    aes_event.rom_entered(name, arguments, grwait.button_down(), {}, 1)
    spent = aes_event._instructions_run()
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", spent * aes_event.DERIVATION_MARGIN - 1)
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        aes_event.rom_entered(name, arguments, grwait.button_down(), {}, 1)


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


def test_a_process_woken_again_after_it_parked_is_running_as_switchto_leaves_it():
    """`aes_event.parked` then a wake: PD0 parked in an evnt_multi of its own (holding the screen lock, the screen
    manager then queued on it — `test_aes_wm_update.waited_on`) and woken by Return runs as switchto leaves a process."""
    image = make_image(_wm_update().waited_on())
    assert aes_event.scheduler_state(image, aes.SHELL_PD) == aes_event.running_as_switchto_leaves_it(aes.SHELL_PD)


STALE_REGISTER = 0xA5A5A5A5            # what a run before leaves in every register the next run does not set
SECOND_STALE_REGISTER = 0x5A5A5A5A


def _parked_after_registers_left(value):
    """`parked` PD0 in its evnt_multi for a key, the screen lock held — right after a run that left every register
    `value` (the frame and the machine derived first: their own runs would leave registers of their own)."""
    frame, locked = _wm_update().KEY_WAIT, _locked()
    _final, _writes, left = emu.run(make_image({}), addrs.AES_ROM_RC_INTERSECT, {name: value for name in emu.REPORTED_REGS})
    assert value in left.values(), "the premise: the run before leaves a register stale"
    return aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, locked)


def test_a_parked_machine_is_the_same_whatever_ran_before_it():
    """`parked` enters with `emu.run`'s register file (`rom_bench.entry_registers`), not with what the oracle's previous
    run left in the CPU: the trap save and the dispatcher's context save store the caller's registers, so an unseeded
    parking left two different machines after two different stale files (94 bytes apart, measured)."""
    assert _parked_after_registers_left(STALE_REGISTER) == _parked_after_registers_left(SECOND_STALE_REGISTER)


def test_a_call_that_returns_does_not_park():
    """THE RED for `parked`: a call the event layer answers (the free lock taken) returns — refused by name."""
    with pytest.raises(AssertionError, match="did not park"):
        aes_event.parked(addrs.AES_ROM_WM_UPDATE, aes_event.frame_of(("w", WU["WM_BEG_UPDATE"])), aes_event.machine())


def test_a_yield_is_not_taken_for_a_block():
    """THE RED for `switches`: the lock handed to its waiter YIELDS (`test_aes_wm_update.waited_on`) — held to a block,
    the case fails by name."""
    wm_update = _wm_update()
    with pytest.raises(AssertionError, match=aes_event.BLOCKS):
        aes_event.refused_where_the_rom_blocks(wm_update.WM_UPDATE, (wm_update.END_UPDATE,), wm_update.waited_on())


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
    state = aes_event.typed_ahead(aes_event.pd0_running(), aes_event.RETURN_KEY)
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
    image = bytearray(make_image({}))
    aes_event._interrupt_over(image, addrs.AES_ROM_BUTTON_GLUE, {"d0": aes_event.LEFT_BUTTON})
    assert button_records(image) != LEFT_DOWN


def vdi_button_records(image):
    """The left button as the VDI's two records hold it (MOUSE_BT, CUR_MS_STAT) — what an interrupt changes at once;
    the AES's own follows when forker runs."""
    return button_records(image)[1:]


AWAY = (40, 40)                        # a point the mouse is moved to from the snapshot's (159, 99)


def test_the_mouse_moved_with_the_button_held_keeps_it_held():
    """The IKBD reports the buttons in every packet: moved over the button down, the packets carry it, and the VDI's
    records still say down — RED with packets that carry no button (they would RELEASE it): `released`."""
    held = make_image(aes_event.mouse_moved_to(*AWAY, aes_event.button_down()))
    assert (case.word_in(held, vdi.LINEA_GCURX), case.word_in(held, vdi.LINEA_GCURY)) == AWAY
    assert vdi_button_records(held) == LEFT_DOWN[1:]
    let_go = make_image(merge_pokes(aes_event.button_down(), aes_event.released(aes_event.button_down())))
    assert vdi_button_records(let_go) == (0, 0)


def test_the_cursor_shown_machine_is_the_hidden_one_but_for_the_cursor():
    """`shown_machine`: the same process running (the scheduler's invariants), the cursor as the snapshot shows it
    (gl_moff `aes_gsx.NEST_SHOWN`) where `machine` has hidden it."""
    shown, hidden = make_image(aes_event.shown_machine()), make_image(aes_event.machine())
    assert aes_event.scheduler_state(shown, aes.SHELL_PD) == aes_event.running_as_switchto_leaves_it(aes.SHELL_PD)
    assert aes.read_field(shown, "AES", "GL_MOFF") == aes_gsx.NEST_SHOWN != aes.read_field(hidden, "AES", "GL_MOFF")


def test_window_chain_opens_a_window_that_posts_pd0_its_redraw():
    state, handle = aes_event.window_chain(aes_event.EVERY_GADGET, *CHAIN_RECT)
    final = machine_after(state)
    assert handle > 0
    assert case.word_in(final, aes.SHELL_PD + aes.PD_QUEUE_INDEX) > 0, "wm_open posted nothing"


CHAIN_RECT = (20, 30, 200, 100)
# A budget the wake by a key fits under, but not by DERIVATION_MARGIN (measured: 1,972 instructions).
TIGHT_BUDGET = 5_000


def test_every_derivation_is_held_far_under_its_budget(monkeypatch):
    """`aes_event._rom_run` and the ROM's watched runs hold EVERY derivation DERIVATION_MARGIN times under
    DERIVATION_INSNS: the deepest one — the ROM's draw_change of a lower window moved and resized, watched at the door's
    entries (`test_aes_wm_update.deepest_derivation`) — is run through it here, afresh; and the margin is a real bound:
    under a budget the wake by a key fits, but not by the margin, the derivation is refused by name."""
    assert _wm_update().deepest_derivation()[2]
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", TIGHT_BUDGET)
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        aes_event._woken(aes_event.keys(aes_event.RETURN_KEY))


# ---- ONE RUN delivers every interrupt (`aes_event.deliveries`) -----------------------------------------------------------
def _one_run_per_ordinal(name, arguments, machine, interrupts):
    """The scheme `deliveries` replaced, kept as its reference: the ROM's run started afresh and stopped at the entry of
    each delivery's call (`rom_entered`, the earlier deliveries laid in), the interrupt run over its memory there — a
    run per ordinal, each as long as the calls before it."""
    delivered = {}
    for ordinal in sorted(interrupts):
        memory, _call = aes_event.rom_entered(name, arguments, machine, delivered, ordinal)
        delivered[ordinal] = aes_event._taken(memory, interrupts[ordinal])
    return delivered


def _mn_do_interrupted(label):
    mnlib = _mnlib()
    at, pokes, interrupts, *_outcome = mnlib.MN_DO_INTERRUPTED[label]
    return mnlib.MN_DO, (mnlib.TITLE_OUT, mnlib.ITEM_OUT), mnlib.interrupted_machine(at, pokes), interrupts


# Cases delivering at several calls, each interrupt a sequence of its own (move_to: a packet per step).
SEVERAL_DELIVERIES = {
    "gr_watchbox: in, out again, then the rise": lambda: (*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released()),
    "mn_do: the menu left, then a click off it": lambda: _mn_do_interrupted("the menu left, then a click off it"),
    "mn_do: pressed on the title, dragged to an item, released": lambda: _mn_do_interrupted(
        "pressed on the title, dragged to an item, released: chosen"),
}


@pytest.mark.parametrize("case_of", SEVERAL_DELIVERIES.values(), ids=SEVERAL_DELIVERIES)
def test_one_run_delivers_what_a_run_per_ordinal_delivers(case_of, monkeypatch):
    """The run set aside at each delivery's entry and continued there (`aes_event._continued_at`) takes the same
    interrupts over the same memory as the reference that starts the ROM's run afresh for each: byte for byte. And it
    IS one run: the routine is entered once, every other entry a continuation at a door entry, one per delivery."""
    name, arguments, machine, interrupts = case_of()
    reference = _one_run_per_ordinal(name, arguments, machine, interrupts)
    entered, run_bench = [], emu.run_bench
    monkeypatch.setattr(emu, "run_bench", lambda memory, entry, *rest, **named: entered.append(entry) or run_bench(
        memory, entry, *rest, **named))
    assert aes_event.deliveries(name, arguments, machine, interrupts) == reference
    assert entered.count(getattr(addrs, name)) == 1
    assert len(entered) == 1 + len(reference) and set(entered[1:]) <= set(aes_event.ENTRIES)


# ---- KEYS delivered at the door's calls (`aes_event.key`, `typed`): fm_do, the ROM's own, as the oracle ---------------------
FM_DO_ARGUMENTS = (fmdo.SELECTOR, 0)   # fm_do(the file selector, no start field)
FM_DO_DEFAULT = fmdo.OK                # what fm_do answers for Return: the selector's DEFAULT button


def _fm_do_typed(text):
    return aes_event.rom_interrupted(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), aes_event.typed(text))


def _path_text(image):
    """The selector's path field's text (its first editable, which its validation upper-cases)."""
    return fmdo.field_text(image, fmdo.SELECTOR, fmdo.PATH_FIELD)


@pytest.mark.parametrize("text", ("\r", "abc\r", "abcdefgh\r"))
def test_keys_typed_one_per_wait_end_fm_do_where_the_ring_holding_them_all_does(text):
    """`typed`: each key delivered by the keyboard handler at the entry of the next ev_multi, the ROM's own fm_do
    taking one per wait — it answers its DEFAULT, the path field holds the text it typed, and its memory is the memory
    of the same fm_do run over the IKBD ring holding every key before it starts (`keys`): the ROM agreeing with itself
    on what the keys are. One delivery per key, at as many ev_multi calls; Return alone leaves the path as it was."""
    calls, delivered, memory, result = _fm_do_typed(text)
    assert result and result["d0"] == FM_DO_DEFAULT
    assert len(delivered) == len(text) and all(calls[ordinal].routine == addrs.AES_ROM_EV_MULTI for ordinal in delivered)
    typed_into_the_path = text[:-1].upper().encode()
    assert _path_text(memory) == (typed_into_the_path or _path_text(make_image(aes_event.machine())))
    machine = aes_event.machine()
    ahead = aes_event.typed_ahead(machine, *aes_event.scancodes_of(text))
    _calls, _none, typed_ahead, _result = aes_event.rom_interrupted(fmdo.DO, FM_DO_ARGUMENTS, ahead, {})
    assert not aes_event.differing(memory, typed_ahead, frozenset(case.STACK_BAND))


def test_typing_is_one_run_however_long_the_text():
    """NOT QUADRATIC: the ROM's fm_do is entered once for the deliveries however many keys are typed — the rest are
    continuations at the ev_multi entries, one a key."""
    for text in ("\r", "abcdefgh\r"):
        entered = []
        run_bench = emu.run_bench
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(emu, "run_bench", lambda memory, entry, *rest, **named: entered.append(entry) or run_bench(
                memory, entry, *rest, **named))
            aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), aes_event.typed(text))
        assert entered == [addrs.AES_ROM_FM_DO] + [addrs.AES_ROM_EV_MULTI] * len(text)


def test_a_key_typed_past_the_routine_s_last_wait_is_refused_by_name():
    """A key no wait takes — Return ends fm_do, so the key after it — is refused, not dropped."""
    with pytest.raises(AssertionError, match="no door call to deliver"):
        aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), aes_event.typed("\ra"))


def test_a_character_no_unshifted_key_types_is_refused_by_name():
    assert aes_event.scancode_of("\r") == aes_event.RETURN_KEY
    with pytest.raises(AssertionError, match="no unshifted key types 'A'"):
        aes_event.scancode_of("A")


OTHER_ENTRY = addrs.AES_ROM_WM_UPDATE   # a door call that is no wait of a key schedule's


def test_a_schedule_counts_each_run_s_waits_afresh_and_answers_at_its_own_entry_alone():
    """`Waits`, asked over two runs whose door calls come in different orders: each run's waits numbered from its own
    call 0, and a call of another entry answered nothing — never the wait an earlier run made at that ordinal."""
    first, second = object(), object()
    waits = aes_event.Waits({0: first, 1: second})
    runs = ([OTHER_ENTRY, addrs.AES_ROM_EV_MULTI, addrs.AES_ROM_EV_MULTI],
            [addrs.AES_ROM_EV_MULTI, OTHER_ENTRY, addrs.AES_ROM_EV_MULTI])
    answered = []
    for calls in runs:
        waits.begin_run()
        answered.append([waits(ordinal, entry) for ordinal, entry in enumerate(calls)])
    assert answered == [[None, first, second], [first, None, second]]
    assert waits.pending == ()


def test_a_schedule_reused_over_a_run_that_makes_no_door_call_is_refused_by_name():
    """Each run begins the schedule afresh (`Waits.begin_run`), so a run that makes NO door call leaves every row
    pending — not the last run's count: Return typed into fm_do, then the same schedule handed to fm_error past its last
    code (it shows nothing, so it waits for nothing) is refused, not answered with no delivery."""
    waits = aes_event.typed(aes_event.RETURN_KEY)
    aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), waits)
    assert waits.pending == ()
    with pytest.raises(AssertionError, match="no door call to deliver"):
        aes_event.deliveries(fmalert.ERROR, (fmalert.PAST_THE_LAST,), aes_event.machine(), waits)


def test_an_interrupt_s_own_failure_is_reported_not_the_routine_s_budget(monkeypatch):
    """An interrupt whose run fails (its ROM code did not return — the tick glue chained through a garbage pointer)
    surfaces AS ITSELF: the run's vets are made on a run that ended, never over the oracle's counters the failed run
    left (here, a whole budget's), which would name the routine and the wrong remedy instead."""
    def failing(_image):
        raise RuntimeError("the interrupt's run did not reach rts")
    monkeypatch.setattr(aes_event, "_instructions_run", lambda: aes_event.DERIVATION_INSNS)
    with pytest.raises(RuntimeError, match="the interrupt's run did not reach rts"):
        aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), {0: failing})


def test_a_schedule_asked_out_of_order_is_refused_by_name():
    waits = aes_event.Waits({0: object()})
    with pytest.raises(AssertionError, match="it counts the waits of a run asked at every call, in order"):
        waits(1, addrs.AES_ROM_EV_MULTI)


def test_a_schedule_handed_to_another_routine_delivers_at_that_routine_s_own_waits():
    """The same Return schedule run over fm_do, then over fm_alert — whose first door calls are its wm_update's, not
    ev_multi: the key is laid at fm_alert's own first ev_multi, not at the ordinal fm_do's wait had."""
    waits = aes_event.typed(aes_event.RETURN_KEY)
    aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), waits)
    alert = (1, fmlib.ALERTS["AES string 19"])   # fm_alert(default 1, the string)
    delivered = aes_event.deliveries(fmalert.ALERT, alert, aes_event.machine(), waits)
    calls, _memory, _result = aes_event._watched_through(fmalert.ALERT, alert, aes_event.machine(), delivered)
    assert [calls[ordinal].routine for ordinal in delivered] == [addrs.AES_ROM_EV_MULTI]


def test_a_schedule_answers_the_same_deliveries_over_a_second_run():
    """A schedule (`Waits`) is asked again by every run of the same routine — the replay, a row's registration over its
    settled machine — and must answer the ordinals it answered the first time."""
    keys = aes_event.typed("ab\r")
    first = aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), keys)
    assert aes_event.deliveries(fmdo.DO, FM_DO_ARGUMENTS, aes_event.machine(), keys) == first


def test_a_watched_run_is_the_unwatched_run_whatever_ran_before_it():
    """A watched run of the ROM enters with `emu.run`'s register file (`rom_bench.original_entered`), not with what the oracle's
    previous run left in the CPU: the BIOS trap under the keyboard poll saves the caller's registers, so its memory —
    the save area included — is `emu.run`'s, here right after a run that left every register a stale pattern."""
    machine = aes_event.machine()
    ahead = aes_event.typed_ahead(machine, aes_event.RETURN_KEY)
    image = make_image(aes.staged(fmdo.DO, FM_DO_ARGUMENTS, ahead))
    unwatched, _writes, _regs = emu.run(image, addrs.AES_ROM_FM_DO)
    _stale, _writes, regs = emu.run(image, addrs.AES_ROM_FM_DO, {name: STALE_REGISTER for name in emu.REPORTED_REGS})
    assert STALE_REGISTER in regs.values(), "the premise: the run before leaves a register stale"
    _calls, memory, result = aes_event._watched_through(fmdo.DO, FM_DO_ARGUMENTS, ahead, {})
    assert result and not aes_event.differing(memory, unwatched, frozenset(case.STACK_BAND))
