"""THE EVENT DOOR itself (`aes/evdoor.h`, `test/aes_event.py`): what its entries are, what its nested run is held to,
what each call hands it, what differs by nature and why, its refusals RED in a child process, and the machines its
batteries are run over — each the state the ROM's own scheduler leaves, pinned here to the scheduler's invariants.

The routines that go through it are other batteries' (`test_aes_grwait.py`, `test_aes_apmsg.py`); this file is the
door's own surface.
"""
import bisect
import concurrent.futures
import collections
import ctypes
import functools
import importlib
import importlib.util
import os
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
import types
from collections import namedtuple
from pathlib import Path

import pytest

import aes
import abi
import aes_evasync
import aes_event
import aes_evinput
import aes_evlib
import aes_gsx
import aes_pdpipe
import case
import derived
import isr
import test_aes_apmsg as apmsg
import test_aes_evsync as evsync
import test_aes_fmalert as fmalert
import test_aes_fmdo as fmdo
import test_aes_fmlib as fmlib
import test_aes_grdrag as grdrag
import test_aes_grwait as grwait
import vdi
import vdi_entry
import vdi_helpers
import vdi_mouse
import zygote
import aes_fs_sessions as ss
import aes_fslib as fsl
import aes_strings
import routines
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
STILLDN_RISE = aes.EV_BUTTON_LEFT << aes.BUTTON_PARM_MASK_SHIFT | 1 << aes.BUTTON_PARM_CLICKS_SHIFT | aes.EV_BUTTON_UP
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


def test_the_cap_is_derived_from_the_deepest_block_a_shadow_runs(monkeypatch):
    """...and from the deepest nested run of all, which no call the layer answers makes: the SHADOW of a wait that
    blocks (`DEEPEST_BLOCKED`, further down: ev_multi asked for every event at once) — held NESTED_RUN_MARGIN times
    under the cap, and at its measured count. RED under the cap the answered calls alone justified (40,000): that
    shadow was refused by name, "raise the cap, from this run"."""
    arguments, machine = _ev_multi_waiting_for_a_message(DEEPEST_BLOCKED)
    shadow, _arrived_with = _shadow("AES_ROM_EV_MULTI", arguments, machine)
    assert shadow.nested.switched == aes_event.BLOCKS and shadow.nested.insns == DEEPEST_BLOCKED_INSNS
    assert DEEPEST_BLOCKED_INSNS > DEEPEST_NESTED_INSNS, "the premise: the deepest nested run is a block's"
    assert DEEPEST_BLOCKED_INSNS * aes_event.NESTED_RUN_MARGIN <= aes_event.NESTED_RUN_INSNS
    monkeypatch.setattr(aes_event, "NESTED_RUN_INSNS", CAP_THE_ANSWERED_CALLS_JUSTIFIED)
    with pytest.raises(AssertionError, match="inside NESTED_RUN_INSNS' margin"):
        _shadow("AES_ROM_EV_MULTI", arguments, machine)


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


A_MASK_NO_ROUTINE_LEAVES = 0            # the Line-F mask word staged stale: an empty mask, which no store makes ($fee8e6)


def test_the_door_leaves_the_line_f_mask_word_as_the_c_found_it():
    """The companion of a door row whose routine returns by a mask after the door passes (mn_bar) is green: a twin
    makes no masked return at all, and nothing lays the word into the C's image — where the ROM's own routine, run
    over the same machine with the word staged stale, rewrites it (the premise of the by-nature drop: tak_flag's
    masked return, in the shadow's nested run)."""
    bar_hidden_companion()
    stale = merge_pokes(aes_event.machine(), aes.field_pokes("AES", LINEF_MASK_WORD=A_MASK_NO_ROUTINE_LEAVES))
    nested = aes_event.nested_run(addrs.AES_ROM_TAK_FLAG, bytes(make_image(stale)), SPB)
    assert aes_event.LINE_F_MASK_BYTES <= nested.writes.keys() and any(nested.writes[at] for at in aes_event.LINE_F_MASK_BYTES), (
        "the premise: the routine's masked return rewrites the word")


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
    pass) making the same arrival hands nothing more."""
    _entry, call = DEEPEST_CALLS["ev_multi, one rectangle"]
    staged, frame = call()
    image = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer_copy(staged)
    frame_buffer = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)

    def arrive(_lib, _buf):             # each pass its own arrivals in flight: no twin of the last one is running
        aes_event._arrived(addrs.AES_ROM_EV_MULTI, None, aes_event._in_the_recorded_pass, [])(image, frame_buffer, len(frame))
    one_pass = aes_event.EVENT_DOOR.recording(arrive)
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
    for an answer (measured: a frame the door's table could not read let the child's core return 0). Any exception the
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


def _derivations_counted(monkeypatch):
    """The whole ROM derivations (`aes_event.deliveries`) made from here on, counted: the list they are noted in. The
    bench is loaded first: its import registers every battery's rows, each a derivation of its own."""
    aes_event._tier3()
    made, deliveries = [], aes_event.deliveries

    def counted(*case_of, **kwargs):
        made.append(case_of[0])
        return deliveries(*case_of, **kwargs)
    monkeypatch.setattr(aes_event, "deliveries", counted)
    return made


def test_a_case_over_a_settled_machine_is_derived_once_for_both_its_differentials(monkeypatch):
    """ONE DERIVATION PER CASE: over a machine that already keeps `savptr` in the band — a session's, a row's — the
    second differential takes what `interrupted` derived (`Derived`) and derives nothing again; over any other
    machine it runs its own, as it must (the settled machine is another)."""
    made = _derivations_counted(monkeypatch)
    settled = merge_pokes(grwait.button_down(), aes_event.savptr_in_the_band())
    aes_event.interrupted(*WATCHED_OUTSIDE, settled, entered_then_released(), objects=True)
    assert len(made) == 1
    aes_event.interrupted(*WATCHED_OUTSIDE, grwait.button_down(), entered_then_released(), objects=True)
    assert len(made) == 1 + 2


def test_what_a_case_derived_is_what_its_second_differential_would_derive():
    """...and it is the same row either way: the settled machine and the deliveries `_settled_interrupted` answers
    from what the case derived are those its own run derives."""
    name, arguments = WATCHED_OUTSIDE
    settled = merge_pokes(grwait.button_down(), aes_event.savptr_in_the_band())
    _calls, delivered, rom_memory, result = aes_event.rom_interrupted(name, arguments, settled, entered_then_released())
    assert result
    handed_on = aes_event._settled_interrupted(name, arguments, settled, entered_then_released(),
                                               derived=aes_event.Derived(delivered, rom_memory))
    assert handed_on == aes_event._settled_interrupted(name, arguments, settled, entered_then_released())


ONE_MACHINE = "one machine"            # what a session's rows share, as its memo is handed it: any value held equal


def _counting_memo():
    """A `OncePerSession` whose computation counts its own runs: `(memo, the rows it was run for)`."""
    computed = []

    def count(row_name):
        computed.append(row_name)
        return len(computed)
    return aes_event.OncePerSession(count), computed


def test_a_sliced_session_s_rows_are_computed_over_once_and_any_other_row_every_time():
    """`OncePerSession`: the five rows of fm_do's sliced session are ONE record (`session_of`), so a consumer's
    per-row computation runs for the first and is answered for the rest; a row that is a session of its own (a
    registered interrupted row, unsliced) and a name that is no interrupted row's are computed each time and NOT
    KEPT — nothing would ever be answered them; and a second memo, another computation's, holds nothing of the first."""
    sliced = [f"aes_fm_do, {label}" for label in fmdo.SESSION_SLICES]
    assert len({id(aes_event.session_of(row_name)) for row_name in sliced}) == 1
    lone, _row = next((row_name, row) for row_name, row in aes_event.INTERRUPTED_ROWS.items() if row.budget is None)
    assert aes_event.session_of(lone) is not aes_event.session_of(sliced[0]) and lone not in aes_event.SLICED_ROWS
    assert aes_event.session_of("no row at all") is None
    memo, computed = _counting_memo()
    assert [memo(row_name, ONE_MACHINE, row_name) for row_name in sliced] == [1] * len(sliced)
    assert [memo(lone, ONE_MACHINE, lone), memo(lone, ONE_MACHINE, lone)] == [2, 3]
    assert [memo("no row at all", ONE_MACHINE, "no row at all") for _twice in range(2)] == [4, 5]
    assert computed == [sliced[0], lone, lone, "no row at all", "no row at all"]
    assert list(memo._made) == [id(aes_event.session_of(sliced[0]))], "kept for the sliced session alone"
    assert aes_event.OncePerSession(lambda row_name: "another memo")(sliced[1], ONE_MACHINE, sliced[1]) == "another memo"


def test_a_session_s_row_over_another_machine_is_not_answered_its_session_s_run():
    """THE MEMO'S PREMISE, held by name (RED): a session's rows share a run because they are one machine — a later row
    of the session handed with another is refused, not answered the first's value."""
    first, second, *_rest = (f"aes_fm_do, {label}" for label in fmdo.SESSION_SLICES)
    memo, computed = _counting_memo()
    memo(first, ONE_MACHINE, first)
    with pytest.raises(AssertionError, match=f"{second}: the rows of its session are not one machine"):
        memo(second, "another machine", second)
    assert memo(second, ONE_MACHINE, second) == 1 and computed == [first]


UNREAD_BYTE = aes_event.UNREAD_BYTE     # a byte of the door's band no case here stages or reads
STALE_BYTE = 0x5A                      # ...and a value laid there


class _Measured(Exception):
    """`bench_differential` reached Tier 3's measurement."""


def _a_registered_fm_do_row():
    """One of fm_do's registered rows taken through interrupts (`aes_event.INTERRUPTED_ROWS`): `(row name, routine,
    arguments, settled machine, interrupts)` — the case a battery's twin of it hands `bench_differential`."""
    row_name, row = next((row_name, row) for row_name, row in aes_event.INTERRUPTED_ROWS.items()
                         if row.name == fmdo.DO and row.budget is None)
    return row_name, row.name, row.arguments, row.pokes, row.interrupts


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


THE_ALARM_SECONDS, FAR_PAST_THE_ALARM = 1, 30


def test_a_guard_is_remembered_by_what_the_call_is_not_by_which_object_stages_it(monkeypatch):
    """THE RED for a memo keyed by the machine's IDENTITY: a freed dict's address is the next dict's, so another
    machine could pass unguarded on the first one's word. By content: an equal machine in another object runs no
    second child (keyed by identity, it would), and a machine that differs by one byte does."""
    children = []
    monkeypatch.setattr(aes_event, "_RETURNED_IN_A_CHILD", set())
    monkeypatch.setattr(aes_event, "refusal", lambda *call, **named: children.append(call) or (0, "", None))
    machine = dict(grwait.running())
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, machine)
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, dict(machine))
    assert len(children) == 1
    other = merge_pokes(machine, {UNREAD_BYTE: bytes([~BASE_IMAGE[UNREAD_BYTE] & BYTE_MASK])})
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, other)
    assert len(children) == 2
    name, (tree, index, *states) = WATCHED_OUTSIDE
    aes_event.returns_in_a_child(name, (tree, index + 1, *states), machine)     # ...and another FRAME over the first
    assert len(children) == 3


def test_a_guard_is_remembered_by_the_image_its_pokes_make_not_by_the_pokes(monkeypatch):
    """THE RED for a memo keyed by the pokes SORTED: two pokes that overlap make another image laid in the other order
    (`make_image` lays them as the dict holds them, the later winning) — two machines, two children; and the same
    image staged as other pokes (one run for two) is the same call, with no second child."""
    children = []
    monkeypatch.setattr(aes_event, "_RETURNED_IN_A_CHILD", set())
    monkeypatch.setattr(aes_event, "refusal", lambda *call, **named: children.append(call) or (0, "", None))
    whole, inside = (UNREAD_BYTE - 1, b"\x01\x02"), (UNREAD_BYTE, b"\xee")
    one_way, the_other = dict([whole, inside]), dict([inside, whole])
    assert sorted(one_way.items()) == sorted(the_other.items()) and make_image(one_way) != make_image(the_other), "the premise"
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, one_way)
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, the_other)
    assert len(children) == 2
    aes_event.returns_in_a_child(*WATCHED_OUTSIDE, {UNREAD_BYTE - 1: b"\x01", UNREAD_BYTE: b"\xee"})      # `one_way`'s image
    assert len(children) == 2


# ---- THE FORK: the guard of a core that reaches no hook (`aes_event.guard_fork`, `run_core_guarded`, `core_in_a_fork`) -----
TAK_FLAG = evsync.TAK_FLAG
ODD = 1                                # a semaphore's address made odd: the host's accessors refuse it — an abort
# WHO MAKES A FORK: the session's zygote where it stands in for the worker (`aes_event.the_zygote_stands_in`), the
# worker itself everywhere else. Every property of the fork below is held under BOTH makers — the zygote's fork is the
# fork the worker would have made, or it is not a stand-in.
THE_ZYGOTE, THE_WORKER = "the zygote", "the worker itself"


class _Forks:
    """The forks `aes_event` makes while a test runs, by their maker."""

    def __init__(self, maker, monkeypatch):
        self.maker, self.by_the_zygote, self.by_the_worker = maker, [], []
        by_the_zygote, in_a_fork = aes_event._by_the_zygote, aes_event.in_a_fork
        monkeypatch.setattr(aes_event, "_by_the_zygote",
                            lambda made, *named: self.by_the_zygote.append(made) or by_the_zygote(made, *named))
        monkeypatch.setattr(aes_event, "in_a_fork",
                            lambda call, *limits: self.by_the_worker.append(call) or in_a_fork(call, *limits))

    def made(self):
        """How many forks were made — every one of them by this fixture's maker."""
        mine, the_other_s = ((self.by_the_zygote, self.by_the_worker) if self.maker == THE_ZYGOTE
                             else (self.by_the_worker, self.by_the_zygote))
        assert not the_other_s, f"{len(the_other_s)} fork(s) were not made by {self.maker}"
        return len(mine)


@pytest.fixture(params=(THE_ZYGOTE, THE_WORKER))
def forks(request, monkeypatch):
    """Each maker of a core's fork in turn: the session's zygote (skipped in a process that has none: AES_NO_ZYGOTE),
    and the worker itself. A test that takes `monkeypatch` has the zygote SIDELINED (`conftest.py`: a patch on the
    fork's side is never the zygote's) — which is the worker's turn as it stands; for the zygote's it is put back in
    use, these tests' patches being the worker's side's alone (who made a fork, counted; the door itself)."""
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", request.param == THE_WORKER or aes_event.MEANT_UNDER_PATCHES)
    if request.param == THE_ZYGOTE and not aes_event.the_zygote_runs():
        pytest.skip("this process has no zygote")
    return _Forks(request.param, monkeypatch)


def _an_odd_semaphore():
    return TAK_FLAG, (evsync.WIND_SPB | ODD,), aes_event.machine()


def test_a_core_that_halts_in_its_fork_fails_its_guard_by_name(forks):
    """The guard's RED: tak_flag handed an ODD semaphore — the host's refusal, an abort — fails the case by the call,
    the signal and the refusal's own words, in the differential's own run door: the abort is the fork's, the worker
    lives. The same call over an even one returns."""
    aborted = rf"{TAK_FLAG}\(\d+,\): the C did not return in a child \(-{int(signal.SIGABRT)}\): recreate: "
    with pytest.raises(AssertionError, match=aborted):
        aes_event.run_core_guarded(*_an_odd_semaphore())
    said = aes_event.core_in_a_fork(TAK_FLAG, (evsync.WIND_SPB,), aes_event.machine(), answered=True)
    assert (said.returncode, said.answer) == (0, evsync.TAKEN), said
    assert forks.made() == 2


def test_every_run_of_a_guarded_core_is_made_in_a_fork_first_the_attribution_pass_s_too(monkeypatch, forks):
    """`run_core_guarded` guards EVERY run of the C the kit makes, each over the image the kit hands that run: the
    plain pass and the attribution pass are two forks (tak_flag over the free lock runs the whole pass) — and the fork
    comes BEFORE the run in process, which a fork that does not return keeps from ever being made."""
    evsync.tak_flag(evsync.running())
    assert forks.made() == 2
    made_in_process = []
    monkeypatch.setattr(aes_event, "guard_fork", lambda call, made, **named: (-int(signal.SIGALRM), "", None))
    core = getattr(aes_event._lib, TAK_FLAG_TWIN)
    monkeypatch.setattr(aes_event._lib, TAK_FLAG_TWIN, lambda *call: made_in_process.append(call) or core(*call))
    with pytest.raises(AssertionError, match="did not return in a child"):
        evsync.tak_flag(evsync.running())
    assert not made_in_process


def test_the_image_a_guard_s_fork_runs_over_is_the_one_the_kit_handed_that_run(monkeypatch, forks):
    """The plain pass's fork and the attribution pass's run over TWO images — the second with every byte the ROM's
    run stored inverted — and each fork is handed its own: the zygote by a copy into the mapping it shares, the
    worker by its fork's own copy of the buffer."""
    handed, guard_fork = [], aes_event.guard_fork

    def noting(call, made, **named):
        handed.append(bytes(made.buf))
        verdict = guard_fork(call, made, **named)
        if forks.maker == THE_ZYGOTE:   # ...whose shared image now holds what the core leaves of the image handed
            ran_here = bytearray(handed[-1])
            made.core((ctypes.c_uint8 * len(ran_here)).from_buffer(ran_here), *made.typed)
            assert aes_event.GUARD_ZYGOTE[0].image() == bytes(ran_here), "the fork ran over another image"
            stored.append(bytes(ran_here) != handed[-1])
        return verdict
    stored = []
    monkeypatch.setattr(aes_event, "guard_fork", noting)
    evsync.tak_flag(evsync.running())
    plain, attributed = handed
    assert plain != attributed and evsync.spb_of(plain) == evsync.spb_of(make_image(evsync.running()))
    assert forks.maker == THE_WORKER or stored[0], "the premise: the plain run's core stores, so the image read back is its own"


def _arming_that_raises():
    raise RuntimeError(ARMED)


def test_a_fork_s_library_is_armed_as_a_differential_arms_it_before_the_core_runs(monkeypatch):
    """`core_in_a_fork` puts the candidate's models in the state a run may assume (`arm_candidate`: every ledger and
    seed reset) BEFORE the core is called — the fork inherits the worker's library as the last test left it, and its
    verdict may not depend on which test that was. Shown by an arming that raises: the fork ends there, the harness's
    error, and the image it shares shows the core never ran (the lock still free). BY THE WORKER — and by the
    function the zygote serves a fork with, which arms the same way (called here, where the arming can be made to
    raise: the zygote's own library no test ever touched).

    AND THE RED FOR A PATCH THE ZYGOTE NEVER SEES: this test patches the fork's side and does nothing about the
    zygote — the suite's rule does (`conftest.py`: a test that takes `monkeypatch` has the zygote sidelined). With
    the session's zygote left to make this fork, the arming that raises never ran: exit 0, where 8 is right."""
    monkeypatch.setattr(aes_event, "arm_candidate", _arming_that_raises)
    said = aes_event.core_in_a_fork(TAK_FLAG, (evsync.WIND_SPB,), aes_event.machine(), read_back=True)
    assert said.returncode == aes_event.FORK_RAISED and ARMED in said.stderr
    assert aes_event.ZYGOTE_SIDELINED and not aes_event.the_zygote_runs(), "the premise: the suite's rule did it"
    assert evsync.spb_of(said.image) == evsync.spb_of(make_image(aes_event.machine()))
    image = make_image(aes_event.machine())
    core = getattr(aes_event._lib, TAK_FLAG_TWIN)
    request = aes_event.ForkedCore(TAK_FLAG_TWIN, aes_event._ctype_name(core.restype),
                                   tuple(aes_event._ctype_name(each) for each in core.argtypes), (evsync.WIND_SPB,),
                                   takes_image=True, answered=False, seconds=aes_event.CORE_RETURN_SECONDS)
    returncode, stderr = aes_event._forked_in_the_zygote((ctypes.c_uint8 * len(image)).from_buffer(image), tuple(request))
    assert returncode == aes_event.FORK_RAISED and ARMED in stderr


ARMED = "the library's models armed"


def test_a_fork_shares_the_image_its_core_left_with_the_case(forks):
    """`core_in_a_fork(read_back=True)`: the image is the fork's own stores — the lock taken, by the fork."""
    said = aes_event.core_in_a_fork(TAK_FLAG, (evsync.WIND_SPB,), aes_event.machine(), read_back=True)
    assert said.returncode == 0 and evsync.spb_of(said.image) == (1, aes.SHELL_PD)
    assert evsync.spb_of(make_image(aes_event.machine()))[0] == 0, "the premise: the lock was free"
    assert forks.made() == 1


def test_a_call_still_running_in_its_fork_is_ended_by_its_alarm():
    """A core that does not come back is ended by SIGALRM after its `seconds` — a failed case, never a worker left
    spinning; and the alarm, the fork's first act, is what bounds a fork whose worker died."""
    exit_code, _stderr = aes_event.in_a_fork(lambda: time.sleep(FAR_PAST_THE_ALARM), THE_ALARM_SECONDS)
    assert exit_code == -int(signal.SIGALRM)


def _raising():
    raise RuntimeError("raised in the fork")


@pytest.mark.parametrize("raising", (_raising, sys.exit), ids=("an exception", "a SystemExit"))
def test_a_fork_whose_python_raises_says_so_and_never_returns_into_the_suite(raising):
    """Whatever the fork's own Python does, it `_exit`s — an exception there is an exit status of its own, not a
    second pytest running on in the worker's copy — and it is reported as THE HARNESS'S error, its traceback with
    it: never as a C that did not return."""
    exit_code, stderr = aes_event.in_a_fork(raising)
    assert exit_code == aes_event.FORK_RAISED and aes_event.FORK_S_PYTHON_RAISED in stderr and "Traceback" in stderr
    with pytest.raises(AssertionError, match="the guard itself failed, no verdict on the C") as failed:
        aes_event._vet_returned(TAK_FLAG, (), exit_code, stderr)
    assert "did not return" not in str(failed.value)


def test_a_fork_s_python_is_heard_under_any_capture():
    """A fork's stderr is the pipe for PYTHON too, not for descriptor 2 alone: what a hook prints (`sys.stderr` is
    pytest's capture object in a worker, and would die with the fork) reaches the guard's message — so a case may
    `match=` a hook's words with or without `-s`."""
    said = "a word a Python hook said"
    assert aes_event.in_a_fork(lambda: print(said, file=sys.stderr)) == (0, said + "\n")
    assert aes_event.in_a_fork(lambda: print(said)) == (0, said + "\n"), "its stdout too: a worker's is xdist's channel"


def test_the_dispatcher_s_refusal_is_told_by_name_from_a_fork(monkeypatch):
    """The dispatcher's hook is the one hook a fork serves, as it is served everywhere: REFUSED, by name — a twin
    that reaches dsptch behind the fork's guard fails its case by `would block`, the hook's own words."""
    image = bytearray(AT_DSPTCH["a wait nothing satisfies: it would block"][0]())
    buf = (ctypes.c_uint8 * len(image)).from_buffer(image)
    with pytest.raises(AssertionError, match=aes_event.BLOCKS):
        aes_event._vet_returned(DSPTCH_ENTERED, (), *aes_event.in_a_fork(lambda: getattr(aes_event._lib, DSPTCH_ENTERED)(buf)))


REACHES_A_VOID_HOOK = ("AES_ROM_GSX_MOFF", ())     # the cursor hidden: the VDI's own v_hide_c, through `recreate_call_vector`


def test_a_core_that_reaches_a_hook_in_a_fork_is_refused_by_name_not_passed(forks):
    """THE RED for a guard that passes vacuously: a `void` hook left as the worker's import bound it refuses SILENTLY
    (no pass is open), the core returns having skipped the effect, and the fork is green. Every hook is a refuser in
    a fork: gsx_moff, which draws through the VDI's hook, ends its fork by the hook's name — and a core that reaches
    the event door does, wind_update at the lock's tak_flag."""
    said = aes_event.core_in_a_fork(*REACHES_A_VOID_HOOK, aes_event.shown_machine())
    assert said.returncode == aes_event.FORK_REACHED_A_HOOK and isr.CALL_VECTOR_SYMBOL in said.stderr, said
    with pytest.raises(AssertionError, match=f"reached the hook {aes_event.HOOK_SYMBOL}.*`run_guarded`"):
        aes_event.run_core_guarded(*_lock_taken(), aes_event.machine())
    assert forks.made() == 2


def test_a_core_that_reaches_the_dispatcher_in_a_fork_halts_there_by_the_hook_s_own_words(forks):
    """...and the one hook a fork serves by refusing, under either maker: a wait nothing satisfies ends its fork at
    the dispatcher's hook as a call that would BLOCK, with every store it made before in the image read back."""
    blocked = aes_evlib.at("evnt_keybd, none", aes_evlib.MWAIT)
    said = aes_event.core_in_a_fork(blocked.name, blocked.arguments, blocked.machine, read_back=True)
    assert said.returncode not in (0, aes_event.FORK_RAISED, aes_event.FORK_REACHED_A_HOOK)
    assert aes_event.HALTED_AT_THE_DISPATCHER in said.stderr and aes_event.BLOCKS in said.stderr
    assert said.image != bytes(make_image(blocked.machine)), "the image read back is the staged one: no store of the fork's"
    assert forks.made() == 1


# ---- A DERIVATION ANSWERS ONE MACHINE, WHATEVER RAN BEFORE IT (the kit's entry state, held where it surfaced) ----------
def _saved_user_stacks(machine):
    image = make_image(machine)
    return tuple(case.long_in(image, uda + aes.UDA_USER_SP) for uda in aes_pdpipe.UDAS)


def test_a_derivation_answers_one_machine_whatever_ran_before_it():
    """A derived machine is the ROM's own run, and the ROM's dispatcher SAVES the CPU's user stack pointer in the
    process it parks (savestate: `move.l usp,a0` into the UDA). The kit begins every run with USP = 0 (`ENTRY_USP`,
    `tools/recreate_kit`'s own pin beside the entry CCR's); before it did, a run inherited the last run's, so the
    SAME derivation made twice in one process answered two machines — the screen manager's saved USP 0 the first
    time and $8988 the second — and twenty rows hashed differently under the bench's import order than in a worker's.
    Held on the derivation that showed it, made twice with a run that leaves a user stack pointer between them: one
    machine, and the saved pointers the snapshot's own."""
    first = aes_pdpipe.writer_waiting.__wrapped__()
    aes_evinput.LAYER.watched({}, addrs.AES_ROM_DISP_LOOP, stop_at=(aes_evinput.CHKKBD, 2))      # the dispatcher's own loop
    again = aes_pdpipe.writer_waiting.__wrapped__()
    assert again == first, "one derivation, two machines: it depends on the run before it"
    assert _saved_user_stacks(first) == _saved_user_stacks({}), "a derived machine's saved USP is not the snapshot's own"


# ---- THE LAYERS' FAMILY (`aes_event.Layer`, `Scenarios`, `run_core_steered`): what the three batteries share, held here ---
def _arrive(*names):
    return tuple(aes_event.LayerArrival(name, (), {}) for name in names)


SIGNAL, AZOMBIE, APRET = "AES_ROM_SIGNAL", "AES_ROM_AZOMBIE", "AES_ROM_APRET"


def test_a_scenario_s_run_is_held_to_what_it_declares_and_made_once_a_process():
    """`Scenarios`: a run that arrives anywhere but where its scenario DECLARES is refused by name, both sequences
    spelt — a missed arrival is a declared one that did not come — and a run is made once however often it is asked."""
    made = []
    scenarios = aes_event.Scenarios({"as declared": (SIGNAL, APRET), "one missed": (SIGNAL, AZOMBIE, APRET)},
                                    lambda name: made.append(name) or _arrive(SIGNAL, APRET))
    assert scenarios.scenario("as declared") is scenarios.scenario("as declared") and made == ["as declared"]
    with pytest.raises(AssertionError, match=r"one missed: the ROM's run arrives at \['signal', 'apret'\], "
                                             r"declared \['signal', 'azombie', 'apret'\]"):
        scenarios.scenario("one missed")
    assert scenarios.cases() == [("as declared", 0), ("as declared", 1), ("one missed", 0), ("one missed", 1), ("one missed", 2)]
    assert scenarios.cases(APRET, AZOMBIE) == [("as declared", 1), ("one missed", 1), ("one missed", 2)]
    assert scenarios.case_id(("one missed", 1)) == "one missed: 1 azombie"


def test_a_scenario_s_arrival_is_found_by_its_routine_and_which_of_them():
    """...`nth_of` / `at`: the `which`-th declared arrival at a routine, counted from the first — over a run that
    answers a `Watched` as over one that answers the arrivals themselves."""
    run = _arrive(SIGNAL, APRET, SIGNAL, SIGNAL)
    for scenarios in (aes_event.Scenarios({"twice": (SIGNAL, APRET, SIGNAL, SIGNAL)}, lambda _name: run),
                      aes_event.Scenarios({"twice": (SIGNAL, APRET, SIGNAL, SIGNAL)}, lambda _name: aes_event.Watched(run, {}),
                                          arrivals_of=lambda made: made.arrivals)):
        assert [scenarios.nth_of("twice", SIGNAL, which) for which in range(3)] == [0, 2, 3]
        assert scenarios.at("twice", SIGNAL, 1) is run[2] and scenarios.arrival("twice", 1) is run[1]
        assert scenarios.at("twice", APRET) is run[1]


def test_a_layer_s_run_that_returns_leaves_its_machine_and_may_return_only_before_the_ends_it_names():
    """`Layer.watched`: a run that RETURNS answers the memory it left as its machine (the stack band out) — and is
    refused by name if it was given an end to reach, but for the ends the layer says a run may return before (the
    waits': dsptch, a call made "to its return or to the dispatcher")."""
    asked = aes_evlib.frame_of(aes_evlib.EV_DCLICK, (1, 0))
    machine = aes_evlib.desk_running()
    returned = aes_evlib.LAYER.watched(machine, addrs.AES_ROM_EV_DCLICK, {addrs.AES_ROM_DSPTCH}, asked)
    assert [arrival.name for arrival in returned.arrivals] == [aes_evlib.EV_DCLICK]
    final, _writes, _regs = emu.run(make_image(merge_pokes(machine, {abi.FIRST_ARG: asked})), addrs.AES_ROM_EV_DCLICK)
    assert returned.machine == aes_event.as_pokes(final, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES)
    assert make_image(returned.machine)[:case.STACK_BAND.start] == final[:case.STACK_BAND.start]
    strict = aes_event.Layer(aes_evlib.ROUTINES)
    with pytest.raises(AssertionError, match=f"returned before it reached {addrs.AES_ROM_DSPTCH:#x}"):
        strict.watched(machine, addrs.AES_ROM_EV_DCLICK, {addrs.AES_ROM_DSPTCH}, asked)
    with pytest.raises(AssertionError, match=f"returned before it reached {addrs.AES_ROM_DISP_LOOP:#x}"):
        aes_evlib.LAYER.watched(machine, addrs.AES_ROM_EV_DCLICK, {addrs.AES_ROM_DSPTCH, addrs.AES_ROM_DISP_LOOP}, asked)


IDLE_POLLS = 3


def test_a_layer_s_run_stopped_at_an_arrival_keeps_the_ones_before_it_and_a_bound_reached_is_refused():
    """`stop_at`: an idle that would poll for ever is ended at its n-th arrival at a routine — the arrivals BEFORE
    it kept, that one not, the machine there the run's end — and with `must_end` the same arrival is only a bound:
    reaching it is refused by name, with what arrived on the way."""
    polled = aes_evinput.LAYER.watched({}, addrs.AES_ROM_DISP_LOOP, stop_at=(aes_evinput.CHKKBD, IDLE_POLLS))
    assert [arrival.name for arrival in polled.arrivals].count(aes_evinput.CHKKBD) == IDLE_POLLS - 1
    assert polled.machine is not None
    one_sooner = aes_evinput.LAYER.watched({}, addrs.AES_ROM_DISP_LOOP, stop_at=(aes_evinput.CHKKBD, IDLE_POLLS - 1))
    assert polled.arrivals[:len(one_sooner.arrivals)] == one_sooner.arrivals and len(one_sooner.arrivals) < len(polled.arrivals)
    with pytest.raises(AssertionError, match=rf"reached none of its ends before its {IDLE_POLLS}th arrival at "
                                             rf"{aes_evinput.CHKKBD}: after \['forker', 'chkkbd'"):
        aes_evinput.LAYER.watched({}, addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN},
                                  stop_at=(aes_evinput.CHKKBD, IDLE_POLLS), must_end=True)


def test_an_argument_that_points_into_its_caller_s_stack_is_restaged_in_the_layer_s_own_band():
    """`Layer`'s `restaged`: the stack band is no part of a machine (every case stages its own frame there), so an
    arrival handed a pointer INTO it — ev_block's QPB, which is ap_rdwr's own argument frame; ct_chgown's rectangle,
    w_setactive's local — keeps the bytes in its layer's band and the pointer re-aimed at them: the same bytes, another
    address, in the machine a case is run over."""
    blocked = aes_evlib.at("appl_read, none", aes_evlib.EV_BLOCK)
    assert blocked.arguments == (aes_evlib.READ, aes_evlib.QPB_AT)
    qpb = aes_pdpipe.QPB.unpack_from(make_image(blocked.machine), aes_evlib.QPB_AT)
    asked = aes_evlib.at("appl_read, none", aes_evlib.AP_RDWR).arguments
    assert qpb == (asked[1], asked[2], asked[3]), "the QPB restaged is not the one ap_rdwr was handed"
    handed_back = aes_evinput.at("the screen manager hands the mouse back", aes_evinput.CT_CHGOWN)
    assert handed_back.arguments[1] == aes_evinput.RECT_AT
    assert any(make_image(handed_back.machine)[aes_evinput.RECT_AT:aes_evinput.RECT_AT + aes_evinput.RECT_BYTES])
    taken = aes_evinput.at("the screen taken", aes_evinput.CT_CHGOWN)
    assert taken.arguments[1] != aes_evinput.RECT_AT and taken.arguments[1] not in case.STACK_BAND, (
        "...and a rectangle that is NOT in its caller's stack (wm_update's: a global) is handed as it was")


# ---- THE ONE VOCABULARY OF INTERRUPTS (`aes_event`'s sequences), under its two runners ---------------------------------
A_PRESS_WAKES_THE_DESK = "a press wakes the desk"
A_POINT, SOME_MOVES = (200, 120), ((5, 0), (0, -3), (-2, 2))
SEQUENCES = {"a press": aes_event.PRESSING, "a release": aes_event.RELEASING, "a click": aes_event.CLICKING,
             "a double click": aes_event.DOUBLE_CLICKING, "a right press": aes_event.RIGHT_PRESSING,
             "a move to a point": aes_event.moving_to(*A_POINT), "moves by deltas": aes_event.moving_by(*SOME_MOVES),
             "three ticks": aes_event.ticking(3), "a packet": aes_event.packets(aes_event.LEFT_DOWN_PACKET),
             "a press, then a move, then the count run out": aes_event.in_turn(
                 aes_event.packets(aes_event.LEFT_DOWN_PACKET), aes_event.moving_by((1, 1)), aes_event.click_counted)}


@pytest.mark.parametrize("sequence", SEQUENCES.values(), ids=SEQUENCES)
def test_a_sequence_of_interrupts_leaves_one_machine_under_either_runner(sequence):
    """EVERY sequence the vocabulary has, taken in place (`aes_event.taken_in_place`: what `interrupted` delivers) and
    taken watched at the input layer's entries (`aes_evinput.taken_watched`: what a scenario is made of): the same
    machine, byte for byte, outside what a machine leaves out — one spelling of each interrupt, two runners."""
    in_place = make_image({})
    wrote = aes_event.taken_in_place(in_place, sequence)
    watched = aes_evinput.taken_watched(sequence)({})
    ours, theirs = make_image(watched.machine), make_image(merge_pokes({}, wrote))
    differ = [at for at in aes_event._differing_addresses(ours, theirs, addrs.ST_RAM_BYTES) if at not in aes_evinput.NOT_THE_MACHINE_S]
    assert wrote and not differ, [f"{at:#x}" for at in differ[:8]]


def test_the_two_runners_take_the_same_interrupts_in_the_same_order(monkeypatch):
    """...and not only to the same end: each runner is handed the same `Interrupt`s, one for one (a double click: three
    packets, then the ticks of the count they opened)."""
    in_place, watched = [], []
    interrupt_over, interrupt = aes_event._interrupt_over, aes_evinput.interrupt
    monkeypatch.setattr(aes_event, "_interrupt_over", lambda image, *each: in_place.append(each) or interrupt_over(image, *each))
    monkeypatch.setattr(aes_evinput, "interrupt", lambda pokes, *each: watched.append(each) or interrupt(pokes, *each))
    aes_event.taken_in_place(make_image({}), aes_event.DOUBLE_CLICKING)
    aes_evinput.taken_watched(aes_event.DOUBLE_CLICKING)({})
    assert in_place == watched and len(in_place) > 3 and in_place[3] == tuple(aes_event.TICK)
    assert [each[0] for each in in_place[:3]] == [addrs.VDI_ROM_MOUSE_ISR] * 3


@pytest.mark.parametrize("step", (aes_evinput.tick, aes_evinput.mouse_packet(aes_evinput.LEFT_DOWN), aes_evinput.PRESS, aes_evinput.BAR),
                         ids=("a tick", "a packet", "a press", "a move"))
def test_the_image_a_step_hands_on_is_the_image_its_machine_makes(step):
    """A watched interrupt's own buffer is what the next step runs over, uncopied (`aes_evinput._kept`): it is, byte
    for byte and all sixteen megabytes of it, the image the machine the step answers makes over the snapshot — read
    without being taken (`seen_in`), taken once (`image_of`), and built from the pokes for anyone after."""
    made = step({})
    assert aes_evinput.seen_in(made.machine) == make_image(made.machine)
    taken = aes_evinput.image_of(made.machine)
    assert taken == make_image(made.machine) and aes_evinput._LAST_MADE == [None, None]
    again = aes_evinput.image_of(made.machine)
    assert again is not taken and again == taken
    assert aes_evinput.image_of(dict(made.machine)) == taken, "an equal machine that is not the one just made is built, not taken"


def test_the_rom_s_run_is_asked_what_it_stores_only_for_a_routine_some_reason_steers(monkeypatch):
    """`steered_by` learns what the ROM's run stores by making it — one run more per case — and makes none for a
    routine with no reason in either table (nq, downorup, inorout, mowner, b_click, b_delay, forkq, drawrat: the
    kit's whole pass is theirs whatever they store). The tables are the rule: a routine in one is still asked."""
    asked = []
    stored_by_the_rom = aes_evinput.stored_by_the_rom
    monkeypatch.setattr(aes_evinput, "stored_by_the_rom", lambda name, *case_: asked.append(name) or stored_by_the_rom(name, *case_))
    unsteered = [name for name in aes_evinput.ROUTINES if name not in aes_evinput.STEERS and name not in aes_evinput.STEERS_SOME]
    assert {aes_evinput.NQ, aes_evinput.DOWNORUP, aes_evinput.INOROUT, aes_evinput.MOWNER, aes_evinput.B_CLICK, aes_evinput.B_DELAY} <= set(unsteered)
    for name in unsteered:
        scenario, nth = aes_evinput.cases(name)[0]
        made = aes_evinput.arrival(scenario, nth)
        assert aes_evinput.steered_by(name, made.arguments, made.machine) == ((), ())
    assert not asked
    posted = aes_evinput.at(A_PRESS_WAKES_THE_DESK, aes_evinput.POST_BUTTON)
    assert aes_evinput.steered_by(aes_evinput.POST_BUTTON, posted.arguments, posted.machine) == ((aes_evinput.STEERS_THE_LISTS,), ())
    assert asked == [aes_evinput.POST_BUTTON]



def test_a_c_that_wrote_an_sr_save_word_the_rom_s_run_left_alone_differs_at_dsptch(monkeypatch):
    """The one rule at the THIRD place two shores are compared (`switches_where_the_rom_does`: a call held at the
    dispatcher's hook): a wait that blocks with no interrupt-mask bracket on its way stores no SR save word, so a C
    that wrote one there differs — and where the ROM's run DID store one (a delay queued under spl7), the C, which
    stores none off target, is not held to it."""
    def the_c_leaving_an_sr_word_written(name, values, pokes, **named):
        forked = core_in_a_fork(name, values, pokes, **named)
        image = bytearray(forked.image)
        image[aes.AES_SR_PSETUP] ^= BYTE_MASK
        return forked._replace(image=bytes(image))
    core_in_a_fork = aes_event.core_in_a_fork
    no_bracket = aes_evlib.at("evnt_keybd, none", aes_evlib.MWAIT)
    under_spl7 = aes_evlib.at("evnt_timer", aes_evlib.EV_BLOCK)
    aes_evlib.run(no_bracket), aes_evlib.run(under_spl7)
    stored = aes_event.rom_at_dsptch(under_spl7.name, under_spl7.arguments, under_spl7.machine).writes
    assert aes.AES_SR_SPL in stored and aes.AES_SR_PSETUP not in stored, "the premise: the delay is queued under spl7 alone"
    monkeypatch.setattr(aes_event, "core_in_a_fork", the_c_leaving_an_sr_word_written)
    for arrival in (no_bracket, under_spl7):
        with pytest.raises(AssertionError, match=f"at dsptch.*1 bytes differ from the ROM's run: {aes.AES_SR_PSETUP:#x}"):
            aes_evlib.run(arrival)


CERTAIN, NEEDED, FOR_NOTHING = (aes.steers(why) for why in ("steers every case", "steers this one", "steers another case"))


class _Passed:
    """What a stand-in pass answers: the reasons it was run with, and an `info` as a plain pass's result has."""

    def __init__(self, named):
        self.named, self.info = named, ("the plain pass's info",)


PLAIN = "the plain pass"                # a stand-in run's place in `ran` when it was asked for the plain pass alone


def _a_pass_that_needs(needed, ran):
    """A stand-in for `run_core_guarded`: THE PLAIN PASS (`poison=False`, no reason named) always passes — it compares
    nothing the reasons decide; a NARROWED pass fails unless the case names every reason of `needed`, and must be
    handed the plain pass's `info`; the kit's WHOLE pass (no keyword) fails where any reason is needed. Each run is
    noted: its reasons (or PLAIN) and whether the on-demand sweep was on."""
    def guarded(name, arguments, pokes, **kwargs):
        if kwargs == {"poison": False}:
            ran.append((PLAIN, os.environ.get(aes.STEERED_FOR_NOTHING_SWEEP)))
            return _Passed(())
        named = tuple(kwargs.get("steered", ()))
        ran.append((named, os.environ.get(aes.STEERED_FOR_NOTHING_SWEEP)))
        assert not named or kwargs.get("plain") == ("the plain pass's info",), "a narrowed pass is handed the plain one's"
        assert all(reason in named for reason in needed), "the pass fails: a word that steers the run was inverted"
        return _Passed(named)
    return guarded


def _steered(*case, **named):
    return aes_event.run_core_steered("a routine", (), {}, *case, **named).named


def test_a_reason_that_steers_only_some_cases_is_named_only_where_the_pass_fails_without_it(monkeypatch):
    """THE ONE LOOP (`steered_as_needed`, through `run_core_steered`): the `certain` reasons are always named; each
    `asked` one is tried WITHOUT first — kept where that fails, dropped where it passes — THE PLAIN PASS MADE ONCE
    for all the trials, and the run that returns is the last trial that passed, not made again."""
    ran = []
    monkeypatch.setattr(aes_event, "run_core_guarded", _a_pass_that_needs((CERTAIN, NEEDED), ran))
    assert _steered((CERTAIN,), (NEEDED, FOR_NOTHING)) == (CERTAIN, NEEDED)
    assert [named for named, _sweep in ran] == [PLAIN, (CERTAIN, FOR_NOTHING), (CERTAIN, NEEDED)]
    ran.clear()
    assert _steered((CERTAIN,), (FOR_NOTHING, NEEDED)) == (CERTAIN, NEEDED)
    assert [named for named, _sweep in ran] == [PLAIN, (CERTAIN, NEEDED), (CERTAIN,), (CERTAIN, NEEDED)], (
        "the last trial FAILED (without the needed one): the run that returns is made, with the reasons found")
    ran.clear()
    assert _steered((CERTAIN,), (NEEDED,)) == (CERTAIN, NEEDED)
    assert [named for named, _sweep in ran] == [PLAIN, (CERTAIN,), (CERTAIN, NEEDED)], "no trial passed: run with every reason"
    ran.clear()
    monkeypatch.setattr(aes_event, "run_core_guarded", _a_pass_that_needs((), ran))
    assert _steered() == () and ran == [((), None)], "no reason: the kit's whole pass, once — and no plain pass beside it"
    ran.clear()
    assert _steered((), (FOR_NOTHING,)) == ()
    assert [named for named, _sweep in ran] == [()], "every reason dropped: the last trial IS the whole pass, the run"


def test_steering_is_asked_to_a_fixpoint_where_the_layer_says(monkeypatch):
    """STEERING IS NOT MONOTONIC: a pass that fails without A while B is still named, and passes without A once B
    is gone. One round keeps A (tried first, against a set that held B) and ends on a reason named FOR NOTHING —
    which the sweep refuses; to a fixpoint, the reasons kept before the round's last drop are asked again, and A
    goes. (`run_layer_case` asks to a fixpoint; a layer's own table, proved by one round, asks one.)"""
    ran = []

    def guarded(name, arguments, pokes, **kwargs):
        if kwargs == {"poison": False}:
            return _Passed(())
        named = tuple(kwargs.get("steered", ()))
        ran.append(named)
        assert not (NEEDED in named and FOR_NOTHING not in named), "fails without A while B is named"
        return _Passed(named)
    monkeypatch.setattr(aes_event, "run_core_guarded", guarded)
    a, b = FOR_NOTHING, NEEDED
    assert _steered((), (a, b)) == (a,), "one round: A kept (B was still named), B dropped — A is named for nothing"
    ran.clear()
    assert _steered((), (a, b), fixpoint=True) == ()
    assert ran == [(b,), (a,), ()], "A tried against (A, B): kept; B dropped; then A asked AGAIN, against (A): dropped"


def test_under_the_on_demand_sweep_the_trials_are_made_without_it_and_the_returning_run_again_under_it(monkeypatch):
    """The sweep (`AES_STEERED_FOR_NOTHING`) refuses a reason a run survives without — which is what a TRIAL is: so
    the trials are made with it off, it is put back, and the run that returns is made again under it, where it
    re-asks every reason left."""
    ran = []
    monkeypatch.setenv(aes.STEERED_FOR_NOTHING_SWEEP, "1")
    monkeypatch.setattr(aes_event, "run_core_guarded", _a_pass_that_needs((CERTAIN, NEEDED), ran))
    assert _steered((CERTAIN,), (NEEDED, FOR_NOTHING)) == (CERTAIN, NEEDED)
    assert ran == [(PLAIN, None), ((CERTAIN, FOR_NOTHING), None), ((CERTAIN, NEEDED), None), ((CERTAIN, NEEDED), "1")], (
        "the plain pass is not made again: the sweep is the narrowed pass's")
    assert os.environ[aes.STEERED_FOR_NOTHING_SWEEP] == "1"


def test_a_case_nobody_can_read_by_value_is_asked_every_time_and_one_that_can_is_keyed_by_its_hook_s_name():
    """What the kept answer is keyed by (`_question_of`): the routine, the frame, the machine, the limits and the
    hook BY NAME — and for a hook that has none (a binding built per case) no key at all: such a case's reasons are
    asked every time."""
    named, unnamed = aes_event.EVENT_LAYER_HOOKS, aes.doors(aes_event.vdi_hook)
    question = aes_event._question_of("a routine", [1, 2], {}, {"hook": named, "serves": ("a hook",)})
    assert question == ("a routine", (1, 2), {}, (("serves", ("a hook",)),), "aes_event:EVENT_LAYER_HOOKS")
    assert aes_event._question_of("a routine", (), {}, {})[-1] is None
    assert aes_event._question_of("a routine", (), {}, {"hook": unnamed}) is None


# ---- THE ZYGOTE: which forks it may make for the worker (`aes_event.the_zygote_stands_in`) ---------------------------
def _tak_flag_run(**named):
    core = getattr(aes_event._lib, TAK_FLAG_TWIN)
    image = make_image(aes_event.machine())
    return aes.CoreRun(**{"core": core, "typed": (evsync.WIND_SPB,),
                          "buf": (ctypes.c_uint8 * len(image)).from_buffer(image), "seeded": False, **named})


@pytest.fixture
def a_zygote_runs(monkeypatch):
    """For a test that MEANS the session's zygote: in use for it (a test that takes `monkeypatch` — this fixture
    makes it one — has it sidelined otherwise, `conftest.py`), and skipped in a process that has none."""
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", aes_event.MEANT_UNDER_PATCHES)
    if not aes_event.the_zygote_runs():
        pytest.skip("this process has no zygote")


def test_the_zygote_stands_in_only_where_its_library_is_in_the_worker_s_state(a_zygote_runs, monkeypatch):
    """The rule, arm by arm: an unseeded run of a function of the library, no hook served, the dispatcher's hook the
    module's own refuser — the zygote's. A fork that serves a hook, a seeded run, a stand-in that is no function of
    the library, a worker whose dispatcher hook was rebound, a test that patches (the zygote sidelined), a process
    with no zygote: the worker's own."""
    assert aes_event.the_zygote_stands_in(_tak_flag_run())
    assert not aes_event.the_zygote_stands_in(_tak_flag_run(), serves=(isr.CALL_VECTOR_SYMBOL,))
    assert not aes_event.the_zygote_stands_in(_tak_flag_run(seeded=True))
    assert not aes_event.the_zygote_stands_in(_tak_flag_run(core=lambda *call: 0))
    another = aes_event.DISPATCH_PROTOTYPE(lambda buf: 0)
    aes_event.bind_pointer(aes_event.DISPATCH_SYMBOL, another)
    try:
        assert not aes_event.the_zygote_stands_in(_tak_flag_run())
    finally:
        aes_event.bind_pointer(aes_event.DISPATCH_SYMBOL, aes_event.DISPATCH_REFUSER)
    assert aes_event.the_zygote_stands_in(_tak_flag_run())
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", True)
    assert not aes_event.the_zygote_stands_in(_tak_flag_run())
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", aes_event.MEANT_UNDER_PATCHES)
    monkeypatch.setattr(aes_event, "GUARD_ZYGOTE", [])
    assert not aes_event.the_zygote_stands_in(_tak_flag_run())


SEEDS_THE_LIBRARY = {"io_seed": {}, "psg_seed": {}, "schedule": ()}


@pytest.mark.parametrize("seed", [{}, {"poison": False}, *({name: value} for name, value in SEEDS_THE_LIBRARY.items())],
                         ids=["no keyword", "poison alone", *SEEDS_THE_LIBRARY])
def test_a_run_is_seeded_when_its_case_arms_the_library_with_anything_of_its_own(seed):
    """`aes.run_function` tells its `first` whether the case SEEDED the library (`CoreRun.seeded`): any keyword of
    `case.run`'s but the two that decide the compare alone — a seed the zygote's arming would not hold."""
    runs = []
    aes.run_function(TAK_FLAG, (evsync.WIND_SPB,), evsync.running(), first=lambda call, made: runs.append(made), **seed)
    assert runs and {made.seeded for made in runs} == {bool(seed.keys() & SEEDS_THE_LIBRARY.keys())}
    assert all(made.core is getattr(aes_event._lib, TAK_FLAG_TWIN) and made.typed == (evsync.WIND_SPB,) for made in runs)


def test_a_seeded_run_s_fork_is_the_worker_s_own(a_zygote_runs, monkeypatch):
    forks = _Forks(THE_WORKER, monkeypatch)
    aes_event.run_core_guarded(TAK_FLAG, (evsync.WIND_SPB,), evsync.running(), io_seed={})
    assert forks.made() == 2


def test_every_declared_signature_crosses_to_the_zygote_as_the_types_it_is():
    """A core is called in the zygote with ITS DECLARED TYPES (a word sign-extended, a long whole, the image a
    pointer): each `restype` and `argtypes` of every Alcyon core this process declared goes down the pipe by name and
    comes back the same ctypes type."""
    # (...of the cores the host library HAS: a routine that ships as `.S` alone is declared for its rows and has none.)
    declared = [getattr(aes_event._lib, routines.core_symbol(name)) for name in vdi.ALCYON
                if hasattr(aes_event._lib, routines.core_symbol(name))]
    assert len(declared) > 200
    for core in declared:
        for ctype in (core.restype, *core.argtypes):
            assert aes_event._ctype_named(aes_event._ctype_name(ctype)) is ctype, (core.__name__, ctype)
    with pytest.raises(AssertionError, match="not a type `ctypes` names"):
        aes_event._ctype_name(type("c_mine", (ctypes.c_uint16,), {}))


def test_the_zygote_s_fork_calls_a_core_by_the_types_its_request_declares(monkeypatch):
    """The zygote's own library never saw a battery declare a core (`aes.declare_alcyon` runs in the worker): the
    request carries the declaration, and the function that serves it SETS it before the call. Shown where it can be
    read — this process, the core undeclared for the test as it is in the zygote."""
    core = getattr(aes_event._lib, TAK_FLAG_TWIN)
    declared = core.restype, list(core.argtypes)
    request = aes_event.ForkedCore(TAK_FLAG_TWIN, aes_event._ctype_name(core.restype),
                                   tuple(aes_event._ctype_name(each) for each in core.argtypes), (evsync.WIND_SPB,),
                                   takes_image=True, answered=True, seconds=aes_event.CORE_RETURN_SECONDS)
    monkeypatch.setattr(core, "restype", ctypes.c_int)
    monkeypatch.setattr(core, "argtypes", None)
    image = make_image(aes_event.machine())
    returncode, stderr = aes_event._forked_in_the_zygote((ctypes.c_uint8 * len(image)).from_buffer(image), tuple(request))
    assert (returncode, vdi_helpers.answer_in(stderr)) == (0, evsync.TAKEN)
    assert core.restype is ctypes.c_int and core.argtypes is None, (
        "...on a function object of the request's own: the library's is left as the request found it")
    assert declared[0] is not ctypes.c_int, "the premise: the declaration differs from what the library's object held"


def test_a_core_that_stores_past_its_image_fails_its_guard_by_name_on_any_run(a_zygote_runs):
    """The session's zygote runs every core over a GUARDED image, under the guarded-image plugin or not
    (`test_zygote.py` holds the guards themselves): a store one byte past the image's end — made here by the
    library's own byte store, handed the zygote's image as its base — ends the fork by the fault, where beside an
    unguarded image it would land wherever the fork's memory happened to be mapped."""
    its = aes_event.GUARD_ZYGOTE[0]
    assert its.image_bytes == aes_event.IMAGE_BYTES
    past_the_end = ctypes.cast(its.address + its.image_bytes - 1, ctypes.POINTER(ctypes.c_uint8))
    returncode, _stderr = aes_event.in_a_fork(lambda: ctypes.memset(past_the_end, 0, 2))
    assert returncode in (-int(signal.SIGSEGV), -int(signal.SIGBUS))
    assert aes_event.in_a_fork(lambda: ctypes.memset(past_the_end, 0, 1))[0] == 0, "the image's last byte is its own"


def test_a_zygote_that_died_leaves_the_guard_to_the_worker_and_says_so_once(a_zygote_runs, monkeypatch, capfd):
    """A dead zygote costs no verdict: the fork it could not make is made by the worker, the loss said on stderr —
    and every fork after it is the worker's, unasked. (A zygote of the test's own: the session's is left alone.)"""
    its = zygote.Zygote(aes_event.IMAGE_BYTES, aes_event.ZYGOTE_SERVED_BY)
    monkeypatch.setattr(aes_event, "GUARD_ZYGOTE", [its])
    os.kill(its.pid, signal.SIGKILL)
    for _again in range(2):
        said = aes_event.core_in_a_fork(TAK_FLAG, (evsync.WIND_SPB,), aes_event.machine(), read_back=True)
        assert said.returncode == 0 and evsync.spb_of(said.image) == (1, aes.SHELL_PD)
    assert capfd.readouterr().err.count("makes its own forks from here on") == 1 and not aes_event.GUARD_ZYGOTE


def _hooks_the_library_has():
    """Every hook the candidate exports: the function pointers a core leaves the image's world through."""
    exported = subprocess.run(["nm", "-g", str(vdi_helpers.LIB)], check=True, capture_output=True, text=True).stdout
    return {symbol.lstrip("_") for symbol in exported.split() if symbol.lstrip("_").startswith(HOOK_PREFIX)}


HOOK_PREFIX = "recreate_"


def test_the_fork_refuses_every_hook_the_library_has():
    """DERIVED, from the linked library: its exported hooks are the dispatcher's — served — and the ones a fork
    refuses, no more and no fewer. A hook added to the build and not to the list would be reached, unbound or silent,
    by a core guarded in a fork: this test is where it is named first."""
    assert _hooks_the_library_has() == {*aes_event.FORK_UNSERVED_HOOKS, aes_event.DISPATCH_SYMBOL}


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


def test_a_delivery_that_cannot_be_laid_ends_the_child_by_name_whatever_was_raised():
    """THE RED for the guard round the whole of it (`aes_event._laid_into` runs inside the door's callback, where
    nothing can be raised into C): the laying itself failing with anything but the check's own refusal — here a
    KeyError — used to be printed by ctypes and SWALLOWED, the delivery not laid, the twin run on over a machine no
    interrupt reached and the case reddened later, on bytes. The child now ends there, by name, with the harness's
    own status (FORK_RAISED: never booked to the C)."""
    name, arguments = WATCHED_OUTSIDE
    machine = grwait.button_down()
    delivered = aes_event.deliveries(name, arguments, machine, entered_then_released())
    unlayable = "aes_event._lay = lambda *laid, **how: {}['a delivery no one can lay']; "
    bind = aes_event.child_binding(objects=True, interrupts=delivered, before=unlayable)
    returncode, stderr, _image = aes_event.refusal(name, machine, arguments, bind=bind)
    assert returncode == aes_event.FORK_RAISED, stderr
    assert aes_event.DELIVERY_NOT_LAID in stderr and "KeyError('a delivery no one can lay')" in stderr


def test_a_delivery_lays_no_line_f_mask_word_into_the_c():
    """The C's image keeps the Line-F mask word as it found it at a delivery too (`aes_event.LINE_F_MASK_BYTES`):
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
        aes_event.taken_in_place(at_the_edge, aes_event.moving_to(x, y))
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


def test_the_dispatcher_s_loop_is_held_to_the_process_that_comes_out():
    """`dispatched`: the loop run until a process comes out — Return wakes the DESK, which comes out of its evnt_multi
    alone on the ready list; asked for the screen manager there, it is refused by name."""
    typed = aes_event.keys(aes_event.RETURN_KEY)
    delta, final, _regs = aes_event.dispatched(typed, aes.SHELL_PD)
    assert aes.list_of(final, aes.AES_RLR) == [aes.SHELL_PD] and delta == aes_event.woken_by_a_key()
    with pytest.raises(AssertionError, match=f"entered another process than the PD at {aes.SCREEN_MANAGER_PD:#x}"):
        aes_event.dispatched(typed, aes.SCREEN_MANAGER_PD)


def test_the_dispatcher_s_loop_is_held_to_a_process_alone_unless_the_case_says_another_is_ready():
    """...and ALONE on the ready list: with a staged application made and not yet entered, the mouse onto the bar brings
    the screen manager out FIRST of two ready — refused by name, unless the case says so (`alone=False`)."""
    made = aes_pdpipe.staged_application("AES_ROM_EV_MESAG", aes_pdpipe.BUFFER_AT)
    two_ready = aes_event.mouse_moved_to(*aes_event.MENU_BAR_POINT,
                                         aes_event.parked(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT, made.machine))
    with pytest.raises(AssertionError, match="or not it alone"):
        aes_event.dispatched(two_ready, aes.SCREEN_MANAGER_PD)
    _delta, final, _regs = aes_event.dispatched(two_ready, aes.SCREEN_MANAGER_PD, alone=False)
    assert aes.list_of(final, aes.AES_RLR)[0] == aes.SCREEN_MANAGER_PD and len(aes.list_of(final, aes.AES_RLR)) > 1


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
    """The run set aside at each delivery's entry and continued there (`aes_event.continued_at`) takes the same
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
    continuations at the ev_multi entries, one a key. (The runs are COUNTED, so they are made: nothing kept on disk
    answers for them here.)"""
    for text in ("\r", "abcdefgh\r"):
        entered = []
        run_bench = emu.run_bench
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(derived.DERIVED_OFF, "the runs are counted")
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


# ---- A ROW'S OWN DERIVATION BUDGET (`aes_event._budget_of`), declared and held both ways ---------------------------------
# fm_do's long typing session (`test_aes_fmdo.session`: 38 keys, 728,664 ROM instructions) is the case: past what
# DERIVATION_INSNS admits under its margin, so its rows DECLARE their budget.
SESSION_SPEND = 728_664                # the session's ROM run, measured: what the declarations below are derived from
# ...and the run that DERIVES its deliveries: re-entered at each delivery's door call (`aes_event.continued_at`), and
# an entry is charged an instruction — one more per key.
SESSION_DERIVING_SPEND = SESSION_SPEND + len(fmdo.SESSION_TEXT) + 1


def _session_deliveries(budget):
    name, arguments, machine, interrupts = fmdo.session()
    return aes_event.deliveries(name, arguments, machine, interrupts, budget)


def test_a_long_session_is_refused_under_the_default_budget_by_name():
    """The premise of a declared budget: under the default the session's derivation is refused — by the margin, the
    default's own words."""
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin of 5: raise the budget"):
        _session_deliveries(None)


def test_a_declared_budget_admits_the_session_and_measures_what_it_was_declared_from():
    name, arguments, machine, _interrupts = fmdo.session()
    delivered = _session_deliveries(fmdo.SESSION_INSNS)
    _calls, _memory, result = aes_event._watched_through(name, arguments, machine, delivered, budget=fmdo.SESSION_INSNS)
    assert result["ninsns"] == SESSION_SPEND and len(delivered) == len(fmdo.SESSION_TEXT) + 1


def test_a_declared_budget_the_run_overruns_is_refused_by_name():
    """RED from below: a budget the session fits, but not by the margin — one instruction under five times its spend
    — is refused in the declared budget's own words, naming the least to declare."""
    least = SESSION_DERIVING_SPEND * aes_event.DERIVATION_MARGIN
    with pytest.raises(AssertionError, match=rf"inside its declared budget's \({least - 1}\) margin of 5: raise the row's "
                                             rf"budget to at least {least}"):
        _session_deliveries(least - 1)
    _session_deliveries(least)


def test_a_declared_budget_far_above_the_spend_is_refused_as_stale():
    """RED from above: a budget more than DERIVATION_STALE times what admits the run is stale, by name; the most that
    is not passes."""
    most = SESSION_DERIVING_SPEND * aes_event.DERIVATION_MARGIN * aes_event.DERIVATION_STALE
    with pytest.raises(AssertionError, match=rf"declares a budget of {most + 1} instructions and spent {SESSION_DERIVING_SPEND}: "
                                             rf"the declaration is stale"):
        _session_deliveries(most + 1)
    _session_deliveries(most)


def test_a_declared_budget_is_the_run_s_cap_whatever_the_default(monkeypatch):
    """The declared budget is what the session's runs are CAPPED at, not only vetted against: under a default the
    session's spend is past (here, half of it), both of its runs still end."""
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", SESSION_SPEND // 2)
    name, arguments, machine, interrupts = fmdo.session()
    _calls, _delivered, _memory, result = aes_event.rom_interrupted(name, arguments, machine, interrupts,
                                                                    budget=fmdo.SESSION_INSNS)
    assert result["ninsns"] == SESSION_SPEND


def test_the_whole_session_is_held_to_the_rom_under_its_declared_budget():
    """The session as a Tier 1 case (`interrupted`): the C in a child typed into for 38 keys, held to the ROM's run
    byte for byte — its second differential the registered slices' own (`bench_differential` finds its twin, which
    takes the budget too)."""
    name, arguments, machine, interrupts = fmdo.session()
    taken = aes_event.interrupted(name, arguments, machine, interrupts, objects=True, budget=fmdo.SESSION_INSNS)
    assert taken.returned and taken.answer == fmdo.OK
    assert sum(call.routine == fmdo.WAIT for call in taken.calls) == len(fmdo.SESSION_TEXT) + 1
    assert fmdo.field_text(taken.image, fmdo.SELECTOR, fmdo.PATH_FIELD) == fmdo.SESSION_TEXT.upper().encode()


def test_a_declared_budget_the_default_covers_is_refused_as_stale():
    """A declaration no greater than DERIVATION_INSNS declares nothing: refused before the run, by name."""
    name, arguments = WATCHED_OUTSIDE
    with pytest.raises(AssertionError, match="no more than DERIVATION_INSNS .*the default already covers it"):
        aes_event.rom_watched(name, arguments, grwait.button_down(), budget=aes_event.DERIVATION_INSNS)


def test_a_run_that_blocks_is_held_to_its_declared_budget_both_ways_too():
    """The session with its Return never typed BLOCKS at its last wait, after nearly all of its run: held to the
    declared budget's margin, and from above — a run that ended says what its case needs, returned or not."""
    name, arguments, machine, _interrupts = fmdo.session()
    typed_no_return = aes_event.typed(fmdo.SESSION_TEXT)
    _calls, _delivered, _memory, result = aes_event.rom_interrupted(name, arguments, machine, typed_no_return,
                                                                    budget=fmdo.SESSION_INSNS)
    assert result is None
    with pytest.raises(AssertionError, match="the declaration is stale"):
        aes_event.rom_interrupted(name, arguments, machine, typed_no_return, budget=10 * fmdo.SESSION_INSNS)
    with pytest.raises(AssertionError, match="inside its declared budget's"):
        aes_event.rom_interrupted(name, arguments, machine, typed_no_return, budget=aes_event.DERIVATION_INSNS + 1)


def test_a_prefix_a_watch_stopped_at_an_entry_is_held_to_the_margin_alone(monkeypatch):
    """A run a watch ENDS at a door entry is a prefix: it says nothing of what the whole run needs, so the stale check
    is not made of it (a budget its few instructions are far under would otherwise be stale) — and the margin IS: the
    same prefix under a budget it fits less than five times over is refused in the declared budget's own words."""
    name, arguments, machine, _interrupts = fmdo.session()
    stale, held, vet_the_margin = [], [], aes_event._vet_the_margin
    monkeypatch.setattr(aes_event, "_vet_not_stale", lambda *run: stale.append(run))
    monkeypatch.setattr(aes_event, "_vet_the_margin", lambda *run: (held.append(run), vet_the_margin(*run)))
    with pytest.raises(aes_event._AtTheEntry):
        aes_event._watched_through(name, arguments, machine, {}, stop_at=0, budget=fmdo.SESSION_INSNS)
    (_entry, spent, declared), = held
    assert not stale and spent > 0 and declared == fmdo.SESSION_INSNS
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", spent)       # a default under which a tight budget is one
    tight = spent * aes_event.DERIVATION_MARGIN - 1
    with pytest.raises(AssertionError, match=rf"inside its declared budget's \({tight}\) margin of 5: raise the row's "
                                             rf"budget to at least {tight + 1}"):
        aes_event._watched_through(name, arguments, machine, {}, stop_at=0, budget=tight)
    assert not stale


# fm_alert's documented maximum with its Return queued BEFORE the call: 208,880 ROM instructions with the cursor
# shown. TWO RUNS, TWO LIMITS (`aes_event.run_event`): the in-process differential's is `emu.run`'s cap (200,000), which
# this run is past — so the case declares a `cap`; the watched run of its frames is a derivation, and five times its
# spend is inside DERIVATION_INSNS — so it declares NO budget, and one is refused.
MAXIMUM_ALERT_SPEND = 208_880
MAXIMUM_ALERT_CAP = 1_600_000


def _maximum_alert(**kwargs):
    machine = fmalert.answered(aes_event.RETURN_KEY, shown=True, onto={fmalert.STRING_AT: fmalert.MAXIMUM_ALERT + b"\0"})
    return fmalert.alert(len(fmalert.LONGEST_BUTTONS), fmalert.STRING_AT, machine, **kwargs)


def test_an_in_process_door_case_past_the_oracle_s_cap_declares_its_cap():
    """`run_event(cap=)`: the alert answers its DEFAULT under a declared cap, its original's spend the measure the
    declaration is from; undeclared, the differential's own run does not return under the oracle's cap."""
    result = _maximum_alert(cap=MAXIMUM_ALERT_CAP)
    assert result.answer() == len(fmalert.LONGEST_BUTTONS) and result.info["regs"]["ninsns"] == MAXIMUM_ALERT_SPEND
    assert aes_event.DIFFERENTIAL_INSNS < MAXIMUM_ALERT_SPEND
    with pytest.raises(RuntimeError, match=f"within {aes_event.DIFFERENTIAL_INSNS} instructions"):
        _maximum_alert()


def test_a_budget_the_default_would_have_served_the_run_under_is_refused_whatever_its_size():
    """THE NEED IS THE RUN'S (RED): the same alert under a `budget` — a declaration above DERIVATION_INSNS, inside the
    margin and not ten times the spend, which every rule about the declaration's SIZE passes — is refused, because
    five times this run's spend is inside the default."""
    declared = aes_event.DERIVATION_INSNS + 1
    least = MAXIMUM_ALERT_SPEND * aes_event.DERIVATION_MARGIN
    assert least <= declared <= least * aes_event.DERIVATION_STALE, "the premise: the size rules pass it"
    with pytest.raises(AssertionError, match=rf"declares a budget of {declared} instructions and spent "
                                             rf"{MAXIMUM_ALERT_SPEND}: the declaration is stale — DERIVATION_INSNS "
                                             rf".*the default already covers it"):
        _maximum_alert(budget=declared)


@pytest.mark.parametrize("insns, refused", ((aes_event.DERIVATION_INSNS // aes_event.DERIVATION_MARGIN, True),
                                             (aes_event.DERIVATION_INSNS // aes_event.DERIVATION_MARGIN + 1, False)),
                         ids=("the last run the default admits", "the first it does not"))
def test_a_declared_budget_is_needed_from_the_first_run_the_default_does_not_admit(insns, refused):
    """...to the instruction: a run of DERIVATION_INSNS / DERIVATION_MARGIN is the default's, one more is not."""
    declared = insns * aes_event.DERIVATION_MARGIN + aes_event.DERIVATION_MARGIN
    if not refused:
        return aes_event._vet_not_stale(FS_INPUT, insns, declared)
    with pytest.raises(AssertionError, match="the default already covers it"):
        aes_event._vet_not_stale(FS_INPUT, insns, declared)


def test_an_in_process_door_case_s_declared_cap_is_held_both_ways_and_must_be_needed():
    """...and the cap is held as a budget is, in its own words: one instruction short of five times the spend, one
    past ten times it, and — over a run the oracle's own cap covers — any at all."""
    least = MAXIMUM_ALERT_SPEND * aes_event.DERIVATION_MARGIN
    with pytest.raises(AssertionError, match=rf"inside its declared cap's \({least - 1}\) margin of 5: raise the case's "
                                             rf"cap to at least {least}"):
        _maximum_alert(cap=least - 1)
    most = least * aes_event.DERIVATION_STALE
    with pytest.raises(AssertionError, match=rf"declares a cap of {most + 1} instructions .*the declaration is stale"):
        _maximum_alert(cap=most + 1)
    with pytest.raises(AssertionError, match="the oracle's own cap .*already covers it"):
        fmdo.door_run(fmdo.DO, FM_DO_ARGUMENTS, fmdo.in_the_ring(aes_event.RETURN_KEY), cap=MAXIMUM_ALERT_CAP)


CAP_SPEND = aes_event.DIFFERENTIAL_INSNS + 1          # the first run past the oracle's own cap
CAP_LEAST = CAP_SPEND * aes_event.DERIVATION_MARGIN
CAP_BOUNDS = {"the last run the oracle's own cap covers": (aes_event.DIFFERENTIAL_INSNS, CAP_LEAST, "already covers it"),
              "the first run past it, at five times its spend": (CAP_SPEND, CAP_LEAST, None),
              "one instruction inside the margin": (CAP_SPEND, CAP_LEAST - 1, "margin of 5: raise the case's cap"),
              "ten times its spend": (CAP_SPEND, CAP_LEAST * aes_event.DERIVATION_STALE, None),
              "one past ten times": (CAP_SPEND, CAP_LEAST * aes_event.DERIVATION_STALE + 1, "the declaration is stale")}


@pytest.mark.parametrize("insns, cap, refusal", CAP_BOUNDS.values(), ids=CAP_BOUNDS)
def test_a_declared_cap_is_held_to_the_instruction(insns, cap, refusal):
    """`vet_the_cap`'s three rules for a case's own number, each at its boundary."""
    if refusal is None:
        return aes_event.vet_the_cap(FS_INPUT, insns, cap)
    with pytest.raises(AssertionError, match=refusal):
        aes_event.vet_the_cap(FS_INPUT, insns, cap)


@pytest.mark.parametrize("insns, cap, refusal", CAP_BOUNDS.values(), ids=CAP_BOUNDS)
def test_a_battery_s_cap_is_declared_from_its_deepest_run_by_the_same_three_rules(insns, cap, refusal):
    """`battery_cap`: the declaration is held to the battery's deepest run as a case's cap is to its own."""
    if refusal is None:
        assert aes_event.battery_cap(cap, deepest=insns) == (cap, insns)
        return
    with pytest.raises(AssertionError, match=f"a battery's deepest run .*{refusal}"):
        aes_event.battery_cap(cap, deepest=insns)


def test_a_battery_s_cap_holds_each_of_its_runs_to_the_margin_by_name():
    """A cap one declaration makes for a whole battery's runs (`aes_fslib.RUN_CAP`): a run that fits it five times
    over passes however short — it is not asked whether it needed it — and one inside the margin is refused in the
    battery's cap's own words."""
    cap = aes_event.battery_cap(CAP_LEAST, deepest=CAP_SPEND)
    aes_event.vet_the_cap(FS_INPUT, 1, cap)
    aes_event.vet_the_cap(FS_INPUT, CAP_SPEND, cap)
    with pytest.raises(AssertionError, match=rf"inside its battery's declared cap's \({CAP_LEAST}\) margin of 5: raise "
                                             rf"the battery's cap to at least {CAP_LEAST + aes_event.DERIVATION_MARGIN}"):
        aes_event.vet_the_cap(FS_INPUT, CAP_SPEND + 1, cap)


def test_a_raw_instruction_cap_handed_to_a_door_case_is_refused_by_name():
    """`run_event` OWNS THE CAP (RED): `max_insns` — the spelling every other battery hands `emu.run` — would cap the
    run past every rule, alone or over a declared `cap`: refused before the run, by name, either way."""
    for declared in ({}, {"cap": MAXIMUM_ALERT_CAP}):
        with pytest.raises(AssertionError, match=rf"a raw max_insns \({MAXIMUM_ALERT_CAP}\) was handed past the cap's door"):
            aes_event.run_event(fmdo.DO, FM_DO_ARGUMENTS, fmdo.in_the_ring(aes_event.RETURN_KEY), drawing=True,
                                objects=fmdo.JUST_DRAW, max_insns=MAXIMUM_ALERT_CAP, **declared)


def test_a_door_case_that_overruns_its_declared_cap_is_refused_by_the_cap_s_name():
    """...and a run that does not return under its declared cap is refused as that, not as the oracle's bare overrun."""
    short = MAXIMUM_ALERT_SPEND - 1
    with pytest.raises(AssertionError, match=rf"did not return within its declared cap \({short}\): raise the cap"):
        _maximum_alert(cap=short)


def test_a_routine_s_child_doors_are_declared_once(monkeypatch):
    """`declare_child_doors`: a second declaration for a routine is refused by name (the first would be lost). Over a
    registry of the test's own: the suite's is filled by whichever batteries the process has imported."""
    monkeypatch.setattr(aes_event, "CHILD_DOORS", {})
    aes_event.declare_child_doors(fmdo.DO, "")
    with pytest.raises(AssertionError, match=f"{fmdo.DO}: its child's doors are declared twice"):
        aes_event.declare_child_doors(fmdo.DO, "")


# fm_do's long session with its 38 keys typed BEFORE the call: no interrupt, so ONE run of the oracle makes it in process —
# a door case past BOTH defaults (the session's 728,664 instructions), which declares one number for both its runs.
def _session_in_the_ring(**kwargs):
    codes = aes_event.scancodes_of(fmdo.SESSION_TEXT + "\r")
    return fmdo.door_run(fmdo.DO, FM_DO_ARGUMENTS, fmdo.in_the_ring(*codes), **kwargs)


def test_an_in_process_door_case_past_both_defaults_declares_one_budget_for_both_its_runs():
    """`run_event(budget=)` with no cap (GREEN): the one number is the differential's cap and the budget of the
    watched run of its frames, and each run holds it both ways — the run is the declaration's measure."""
    result = _session_in_the_ring(budget=fmdo.SESSION_INSNS)
    assert result.answer() == fmdo.OK and result.info["regs"]["ninsns"] == SESSION_SPEND
    assert SESSION_SPEND * aes_event.DERIVATION_MARGIN > aes_event.DERIVATION_INSNS, "the premise: it needs a budget"


def test_an_in_process_door_case_s_declared_budget_is_held_from_above_too():
    """...and a budget reaches the watched run of the frames, which holds it both ways IN THE DERIVATION'S WORDS: under
    a cap that fits, a budget one past ten times the frames' run is stale. A budget over a run the oracle's own cap
    covers never gets that far: with no cap of its own it is the cap, refused in the cap's words."""
    most = SESSION_SPEND * aes_event.DERIVATION_MARGIN * aes_event.DERIVATION_STALE
    with pytest.raises(AssertionError, match=rf"the derivation's run of .* declares a budget of {most + 1} instructions "
                                             rf"and spent {SESSION_SPEND}: the declaration is stale — .* a declared "
                                             rf"budget may be at most"):
        _session_in_the_ring(cap=fmdo.SESSION_INSNS, budget=most + 1)
    with pytest.raises(AssertionError, match=rf"the differential of .* declares a cap of {fmdo.SESSION_INSNS} "
                                             rf"instructions .*the oracle's own cap .*already covers it"):
        fmdo.door_run(fmdo.DO, FM_DO_ARGUMENTS, fmdo.in_the_ring(aes_event.RETURN_KEY), budget=fmdo.SESSION_INSNS)


def test_a_registered_row_keeps_its_declared_budget_for_every_later_derivation():
    """A sliced row's deliveries are derived again (`rederived`, the snapshot's noise sweep) under the budget its
    registration declared — recorded with the row; every other registered row declares none. (The sliced rows are
    fm_do's long typing session's and the file selector's sessions', each session with its own budget — the sessions
    that SWITCH among them, whose record is the registrar's: `SwitchingRow.budget`.)"""
    declared = {row_name: row.budget for row_name, row in aes_event.INTERRUPTED_ROWS.items() if row.budget}
    declared.update({row_name: held.row.budget for row_name, held in aes_event.SWITCHING_ROWS.items() if held.row.budget})
    assert set(declared) == set(aes_event.SLICED_ROWS)
    switching = {name for name in declared if name in aes_event.SWITCHING_ROWS}
    assert switching and all(aes_event.session_of(name) is aes_event.SWITCHING_ROWS[name] for name in switching)
    fm_do_s = {row_name: budget for row_name, budget in declared.items() if row_name.startswith("aes_fm_do, ")}
    assert fm_do_s and set(fm_do_s.values()) == {fmdo.SESSION_INSNS}
    row_name = next(iter(fm_do_s))
    assert aes_event.rederived(row_name) == aes_event.INTERRUPTED_ROWS[row_name].delivered


# ---- A SESSION PRICED BY ITS SLICES: the ROM's own fs_input, the oracle on both shores ------------------------------------
# THE MECHANISM, shown on the ROM alone: the file selector's session over its own machine (`aes_fslib.fs_input_machine`:
# the scheduler's PD0, the staged RAM disk under REAL GEMDOS) is cut into its SHAPES, each under the cap, the cuts
# partitioning it; two runs of it agree at every cut; and each refusal is RED. The ROM on both shores, because these
# cuts are at the ROM's own GEMDOS trap handler, which only the ROM's run reaches — the C's GEMDOS is its own
# dispatcher, so what prices the C is the same session over GEMDOS REPLAYED (`test_aes_fs_input_rows.py`).
# The directory holds ten names (`aes_fslib.FOLDERS`' TEN): one past the nine rows, so the list scrolls.
FS_INPUT = addrs.AES_ROM_FS_INPUT
FS_SECOND_ROW = fsl.FIRST_NAME + 1      # the object of the list's second row: what the click selects
FS_SELECTED = "F001.DAT"                # ...the name in it, the sorted list's second
# A wait at a time: a key typed; the second row clicked (TOUCHEXIT: fm_do ends, the name is selected, fm_do begins
# again); the button released and the down arrow clicked (the list scrolls); released, and Return.
FS_SESSION = ss.Session(ss.folder("TEN"), "", ss.schedule([ss.typed("a"), ss.click(FS_SECOND_ROW),
                                                           (ss.release, ss.click(ss.DOWN_ARROW)), (ss.release, ss.RETURN)]),
                        ss.MIDDLE, shown=True)
FS_SESSION_SPEND = 631_480             # the session's ROM run, measured: what its declared budget (ss.MIDDLE) is from
FS_SESSION_DOOR_CALLS = 16             # fm_do entered four times: the lock taken and given back, the mouse's owner, a wait


def _fs_machine():
    """What the session starts from: `aes_fslib.fs_input_machine` over its path, the cursor shown."""
    return fsl.fs_input_machine(FS_SESSION.path, FS_SESSION.selection, shown=FS_SESSION.shown)


def _fs_session_over(machine, session=FS_SESSION):
    """`(machine, delivered)`: `session` over `machine`, and its deliveries — ONE run of the ROM's fs_input under its
    declared budget (`aes_event.deliveries`)."""
    return machine, aes_event.deliveries(fsl.INPUT, fsl.ARGUMENTS, machine, ss.interrupts_of(session, machine), session.budget)


@functools.cache
def _fs_session():
    """...over the machine as it is staged (`_fs_machine`), derived once per worker."""
    return _fs_session_over(_fs_machine())


GEMDOS_TRAP = fsl.GEMDOS_TRAP
ENTRY, RETURN, door_call, trap_taken = aes_event.ENTRY, aes_event.RETURN, aes_event.door_call, aes_event.trap_taken
WAIT, LOCK = addrs.AES_ROM_EV_MULTI, addrs.AES_ROM_TAK_FLAG
# GEMDOS calls, by their arrival: three Mallocs, then Fsetdta (3) — the dialog is drawn by then — Fsfirst and an Fsnext
# per entry (the folder's two dots, its ten files), the last (16) answering no more.
FS_MALLOCS = FS_MFREES = 3
FS_SETDTA, FS_LAST_SNEXT = FS_MALLOCS, 16
# THE SESSION'S SHAPES, in order, each cut where both shores arrive at one PC: the dialog drawn; the directory read; the
# list sorted, formatted and drawn (up to fm_do's own first door call, the screen's lock taken); the dialog taken; a key
# typed; a slot clicked and its name selected; a scroll; Return and the dialog put away.
FS_CUTS = (ENTRY, trap_taken(GEMDOS_TRAP, FS_SETDTA), trap_taken(GEMDOS_TRAP, FS_LAST_SNEXT), door_call(LOCK, 0),
           door_call(WAIT, 0), door_call(WAIT, 1), door_call(WAIT, 2), door_call(WAIT, 3), RETURN)
FS_SHAPES = dict(zip(("the dialog drawn", "the directory read", "the list sorted, formatted and drawn",
                      "the dialog taken, to its first wait", "a key typed", "a slot clicked, its name selected",
                      "the list scrolled", "Return: the dialog put away"),
                     (aes_event.Slice(*ends) for ends in zip(FS_CUTS, FS_CUTS[1:]))))
# What the ROM's run spends in each (instructions), measured.
FS_SHAPE_INSNS = {"the dialog drawn": 184_760, "the directory read": 24_634,
                  "the list sorted, formatted and drawn": 155_170, "the dialog taken, to its first wait": 5_309,
                  "a key typed": 18_912, "a slot clicked, its name selected": 29_251, "the list scrolled": 86_287,
                  "Return: the dialog put away": 127_157}


def _fs_marks(slice_, session=None, **marked):
    """The ROM's run of the session (`session`: `(machine, delivered)`), marked at `slice_`'s ends (`rom_sliced`)."""
    machine, delivered = session or _fs_session()
    marks, _memory = aes_event.rom_sliced(fsl.INPUT, fsl.ARGUMENTS, machine, delivered, slice_, budget=FS_SESSION.budget,
                                          **marked)
    return marks


def _fs_timeline(*traps):
    machine, delivered = _fs_session()
    return aes_event.rom_timeline(fsl.INPUT, fsl.ARGUMENTS, machine, delivered, traps, budget=FS_SESSION.budget)


def _fs_image(machine=None):
    """The session staged: the machine with fs_input's frame (`aes.staged`), as an image a run starts on."""
    return make_image(aes.staged(fsl.INPUT, fsl.ARGUMENTS, _fs_machine() if machine is None else machine))


def _everywhere(ours, the_rom_s):
    """Two ROM runs' memories compared whole: nothing differs by nature between a run and itself."""
    return aes_event.differing(ours, the_rom_s, frozenset())


def test_the_file_selector_s_session_is_refused_under_the_default_budget_by_name():
    with pytest.raises(AssertionError, match="inside DERIVATION_INSNS' margin"):
        _fs_session_over(_fs_machine(), FS_SESSION._replace(budget=None))


# The prefix of that session up to fm_do's first wait: no interrupt is delivered before it, so `emu.run` makes it —
# under the budget the selector's battery declares for its prefixes (`aes_fslib.PREFIX_BUDGET`).
def test_a_prefix_s_declared_budget_is_its_run_s_cap_whatever_the_default(monkeypatch):
    """`stopped_at`'s declared budget is what its run is CAPPED at, not only vetted against (THE RED: capped at the
    default, this prefix — past the default as patched here — would end before its stop): under a default the
    prefix's spend is past, the run still reaches the wait."""
    monkeypatch.setattr(aes_event, "DERIVATION_INSNS", aes_event.DIFFERENTIAL_INSNS)
    _final, _writes, regs = aes_event.stopped_at(_fs_image(), FS_INPUT, WAIT, fsl.PREFIX_BUDGET)
    assert regs["checkpoint"] and regs["ninsns"] > aes_event.DERIVATION_INSNS


def test_a_prefix_inside_its_declared_budget_s_margin_is_refused_by_name():
    """...and it is held to that budget's margin, by name: one the prefix fits less than five times over."""
    with pytest.raises(AssertionError, match=r"inside its declared budget's \(\d+\) margin of 5: raise the row's budget"):
        aes_event.stopped_at(_fs_image(), FS_INPUT, WAIT, aes_event.DERIVATION_INSNS + 1)


def test_the_file_selector_s_session_is_the_one_its_shapes_describe():
    """The ROM's fs_input over the session: OK answered, the row clicked the selection, the path as it was."""
    machine, delivered = _fs_session()
    timeline = _fs_timeline(GEMDOS_TRAP)
    assert timeline[-1].at == RETURN and timeline[-1].spent["insns"] == FS_SESSION_SPEND
    waits = [arrival for arrival in timeline if arrival.at != RETURN and arrival.at.pc == WAIT]
    assert [arrival.calls for arrival in waits] == sorted(delivered), "the premise: each wait takes a schedule's row"
    assert [arrival.at for arrival in waits] == [door_call(WAIT, nth) for nth in range(len(waits))]
    _calls, _delivered, memory, result = aes_event.rom_interrupted(fsl.INPUT, fsl.ARGUMENTS, machine, None, delivered,
                                                                   FS_SESSION.budget)
    assert aes.signed(result["d0"]) == 1 and case.word_in(memory, fsl.BUTTON_AT) == 1
    assert (aes_strings.string_in(memory, fsl.FILE_AT), aes_strings.string_in(memory, fsl.PATH_AT)) == (
        FS_SELECTED.encode(), FS_SESSION.path.encode())


@pytest.mark.parametrize("shape", FS_SHAPES)
def test_each_shape_of_the_file_selector_s_session_is_a_slice_under_the_cap(shape):
    """Each shape is a slice of the ROM's run, under the cap, costing what was measured — and two runs of the session
    agree at both its ends (`vet_the_marks_agree`: the oracle on both shores)."""
    slice_ = FS_SHAPES[shape]
    the_rom_s, ours = _fs_marks(slice_), _fs_marks(slice_)
    aes_event.vet_the_marks_agree(shape, ours, the_rom_s, _everywhere)
    spent = the_rom_s.spent(shape)
    aes_event.vet_under_the_slice_cap(shape, slice_, spent["insns"])
    assert spent["insns"] == FS_SHAPE_INSNS[shape] and ours.spent(shape) == spent


def test_the_shapes_partition_the_session():
    """The cuts leave nothing out and count nothing twice: the shapes' costs sum to the whole run's."""
    assert sum(FS_SHAPE_INSNS.values()) == FS_SESSION_SPEND
    session = _fs_marks(aes_event.Slice(ENTRY, RETURN))
    assert session.at(RETURN, "the session").calls == FS_SESSION_DOOR_CALLS
    whole = session.spent("the session")
    spent = [_fs_marks(slice_).spent(shape) for shape, slice_ in FS_SHAPES.items()]
    assert {name: sum(each[name] for each in spent) for name in whole} == whole


def _fs_session_marked(slices, **marked):
    """ONE run of the session, marked at the ends of ALL of `slices` (`Marks`' `others`): its marks."""
    first, *others = slices
    return _fs_marks(first, others=tuple(others), **marked)


def test_one_run_marked_at_every_shape_s_ends_prices_each_as_its_own_run_does():
    """ONE RUN MARKS EVERY SLICE OF ITS SESSION: the eight shapes read off one run (`Marks.cut_to`) are each what a
    run marked for that shape alone measures — its cost, and the door calls and the memory at both its ends."""
    shared = _fs_session_marked(tuple(FS_SHAPES.values()))
    for shape, slice_ in FS_SHAPES.items():
        cut, alone = shared.cut_to(slice_), _fs_marks(slice_)
        assert cut.slice == slice_ and cut.spent(shape) == alone.spent(shape), shape
        assert cut.ends(shape) == alone.ends(shape), shape
        assert cut.spent(shape)["insns"] == FS_SHAPE_INSNS[shape]


def test_a_run_s_marks_are_read_only_for_a_slice_it_was_marked_at():
    """RED: marks cut to a slice the run was not marked at are refused by name — and so is a slice that is none."""
    marks = _fs_marks(FS_SHAPES["a key typed"])
    with pytest.raises(AssertionError, match="the run was not marked at"):
        marks.cut_to(FS_SHAPES["the list scrolled"])
    with pytest.raises(AssertionError, match="no run is between"):
        aes_event.Marks(FS_SHAPES["a key typed"], aes_event.run_cost, others=(aes_event.Slice(RETURN, ENTRY),))


def test_a_run_marked_at_every_door_call_keeps_its_timeline():
    """`every_door_call`: an arrival for each door call the run makes — in order, numbered per entry, after as many
    calls — and for each end it is marked at (here two GEMDOS calls, where no door call falls), the return last; and
    the marks are what they are without it. Without it no timeline is kept."""
    slice_ = FS_SHAPES["the directory read"]
    marks = _fs_session_marked((slice_,), every_door_call=True)
    arrivals = [arrival.at for arrival in marks.timeline]
    assert arrivals[:2] == list(slice_) and arrivals[-1] == RETURN and len(arrivals) == 2 + FS_SESSION_DOOR_CALLS + 1
    doors = marks.timeline[2:-1]
    assert [arrival.calls for arrival in doors] == list(range(FS_SESSION_DOOR_CALLS))
    assert [arrival.at for arrival in doors if arrival.at.pc == WAIT] == [door_call(WAIT, nth) for nth in range(4)]
    spent = [arrival.spent["insns"] for arrival in marks.timeline]
    assert spent == sorted(spent) and spent[-1] == FS_SESSION_SPEND
    assert marks.spent("the read") == _fs_marks(slice_).spent("the read")
    assert _fs_marks(slice_).timeline is None


def test_a_slice_over_the_cap_is_refused_by_name():
    """RED: the listing uncut — entry to fm_do's first door call, no door call inside it — is past the cap: refused,
    to be cut at a trap it takes (as the shapes above cut it, at GEMDOS's)."""
    listing = aes_event.Slice(ENTRY, door_call(LOCK, 0))
    spent = _fs_marks(listing).spent("the listing")
    assert spent["insns"] == sum(FS_SHAPE_INSNS[shape] for shape in list(FS_SHAPES)[:3])
    with pytest.raises(AssertionError, match=rf"runs {spent['insns']} ROM instructions, past SLICE_INSNS \(200000\): "
                                             rf"cut it finer"):
        aes_event.vet_under_the_slice_cap("the listing", listing, spent["insns"])


def test_the_cap_is_the_most_a_slice_may_run():
    slice_ = FS_SHAPES["a key typed"]
    aes_event.vet_under_the_slice_cap("a key typed", slice_, aes_event.SLICE_INSNS)
    with pytest.raises(AssertionError, match="past SLICE_INSNS"):
        aes_event.vet_under_the_slice_cap("a key typed", slice_, aes_event.SLICE_INSNS + 1)


def test_a_slice_started_one_door_late_is_refused_by_name():
    """RED: one shore marked a door call late — the next wait, where the ROM's slice starts at this one."""
    scroll = FS_SHAPES["the list scrolled"]
    late = aes_event.Slice(door_call(WAIT, scroll.start.nth + 1), RETURN)
    the_rom_s, ours = _fs_marks(aes_event.Slice(scroll.start, RETURN)), _fs_marks(late)
    with pytest.raises(AssertionError, match="our slice starts at door call 13 .* where the ROM's starts at door call "
                                             "8 .* another slice of the session"):
        aes_event.vet_the_marks_agree("the list scrolled", ours, the_rom_s, _everywhere)


def test_a_slice_whose_run_took_another_road_to_its_start_is_refused_by_name():
    """RED: the same slice by name — the session's third wait — reached after another number of door calls: a session
    whose first click is a key instead never leaves fm_do before it."""
    other = _fs_session_over(_fs_machine(), FS_SESSION._replace(waits=ss.schedule([ss.typed("a"), ss.typed("b"), ss.RETURN])))
    slice_ = aes_event.Slice(door_call(WAIT, 2), RETURN)
    with pytest.raises(AssertionError, match="our slice starts at door call 4 .* where the ROM's starts at door call 8"):
        aes_event.vet_the_marks_agree("from the third wait", _fs_marks(slice_, other), _fs_marks(slice_), _everywhere)


def test_a_run_that_diverged_before_the_slice_s_start_is_refused_by_name():
    """RED: one shore's machine differs in a byte nothing reads or writes — every count agrees, and the slice is
    still refused: its start is not the ROM's machine."""
    diverged = _fs_session_over(merge_pokes(_fs_machine(), {UNREAD_BYTE: bytes([STALE_BYTE])}))
    slice_ = FS_SHAPES["a key typed"]
    with pytest.raises(AssertionError, match=rf"our run diverged before the slice's start — at arrival 0 at "
                                             rf"{WAIT:#x} \(door call 2\) 1 bytes differ.*{UNREAD_BYTE:#x}"):
        aes_event.vet_the_marks_agree("a key typed", _fs_marks(slice_, diverged), _fs_marks(slice_), _everywhere)


def test_a_run_that_diverged_inside_a_slice_from_the_entry_is_refused_at_its_end():
    """...and for a slice from the ENTRY (no memory to compare there: both shores start from one image) the same
    divergence is refused at the slice's end."""
    diverged = _fs_session_over(merge_pokes(_fs_machine(), {UNREAD_BYTE: bytes([STALE_BYTE])}))
    slice_ = FS_SHAPES["the dialog drawn"]
    with pytest.raises(AssertionError, match="our run diverged inside the slice"):
        aes_event.vet_the_marks_agree("the dialog drawn", _fs_marks(slice_, diverged), _fs_marks(slice_), _everywhere)


def test_a_slice_end_the_run_never_reaches_is_refused_by_name():
    with pytest.raises(AssertionError, match="never reached arrival 4 at .*its arrivals at that PC: 4"):
        _fs_marks(aes_event.Slice(door_call(WAIT, 3), door_call(WAIT, 4))).ends("the ROM's run")


def test_a_slice_that_runs_backwards_is_refused_by_name():
    with pytest.raises(AssertionError, match="no slice runs backwards"):
        _fs_marks(aes_event.Slice(door_call(WAIT, 1), door_call(LOCK, 0))).ends("the ROM's run")


@pytest.mark.parametrize("ends", ((RETURN, door_call(WAIT, 0)), (door_call(WAIT, 0), ENTRY), (ENTRY, ENTRY),
                                  (door_call(WAIT, 0), door_call(WAIT, 0))),
                         ids=("from the return", "to the entry", "entry to entry", "a call to itself"))
def test_a_slice_between_no_two_points_is_refused(ends):
    with pytest.raises(AssertionError, match="no run is between"):
        aes_event.Marks(aes_event.Slice(*ends), aes_event.run_cost)


def test_a_slice_end_names_a_door_call_or_a_trap_never_the_other():
    with pytest.raises(AssertionError, match="is no entry of the event door"):
        door_call(GEMDOS_TRAP, 0)
    with pytest.raises(AssertionError, match="is a door entry: name its call with `door_call`"):
        trap_taken(WAIT, 0)


class _EveryTrap:
    """A watch that counts EVERY arrival at `trap`'s handler — inside door calls too — round another watch (`inner`,
    which lays the session's deliveries): the count `Timeline`'s is held against."""

    def __init__(self, inner, trap):
        self._inner, self._trap = inner, trap
        self.first = self._armed = inner.first | {trap}
        self.arrivals, self._back = 0, None

    def stopped(self, pc, sp, memory):
        if pc == self._back:
            self._back = None
            return self._armed
        if pc == self._trap:
            self.arrivals += 1
            self._back = case.long_in(memory, sp + aes_event.EXCEPTION_FRAME_PC)
            return frozenset({self._back})
        self._armed = frozenset(self._inner.stopped(pc, sp, memory)) | {self._trap}
        return self._armed


VDI_CALLS_OF_A_KEYBOARD_POLL = 3        # chkkbd's, at the head of every ev_multi: vq_key_s, vsin_mode, vsm_string


# ---- THE FILE SELECTOR'S VDI LEDGER IS THE WHOLE SESSION'S (`aes_fslib.VdiCalls`) ---------------------------------------
def _fs_ledger(whole):
    """The ROM's VDI ledger over FS_SESSION, the traps inside the door calls of the entries `whole` kept too."""
    machine, delivered = _fs_session_over(_fs_machine())
    watch = fsl.VdiCalls(delivered, whole=whole)
    assert fsl._watched(watch, machine, FS_SESSION.budget)[0], "the premise: the session returns"
    return watch


def test_the_rom_s_vdi_ledger_keeps_the_traps_inside_a_rebound_entry_s_calls():
    """RED before the ledger was the whole session's ("fs_input made 215 VDI calls where the
    ROM's own run makes 214" — mchange's vq_mouse, made by our C under ev_multi's twin, against a ROM list that left
    out every trap taken inside a door call). The ROM's watch, told ev_multi is rebound, keeps the traps its ev_multi
    takes — chkkbd's three polls a call, in order, and the fork functions' — BESIDE the same calls outside as ever;
    told no entry is, it keeps none of them. Which entries: the rebound ones, by derivation."""
    outside, whole = _fs_ledger(whole=()), _fs_ledger(whole={addrs.AES_ROM_EV_MULTI})
    assert not outside.inside and whole.inside
    inside = set(whole.inside)
    assert [call for nth, call in enumerate(whole.made) if nth not in inside] == outside.made
    polls = [aes_gsx.opcode_of(name) for name in aes_event.POLLED_FUNCTIONS[:VDI_CALLS_OF_A_KEYBOARD_POLL]]
    opcodes = [whole.made[nth].opcode for nth in whole.inside]
    counts = {opcode: opcodes.count(opcode) for opcode in polls}
    assert len(set(counts.values())) == 1 and counts[polls[0]] > 1, f"a keyboard poll is three calls, each ev_multi: {counts}"
    assert len(opcodes) > sum(counts.values()), "the premise: a fork function's VDI call (the mouse moved) is kept too"
    assert fsl.VdiCalls()._whole == aes_event.REBOUND


def test_our_vdi_ledger_notes_every_function_a_door_binding_serves(monkeypatch):
    """...and OUR ledger notes every VDI function the door's binding serves — the polled ones with the graphics'
    where the poll runs in C (they were served UN-NOTED: held by no ledger) — in process and in a child."""
    assert set(fsl._noting_vdi_calls([])) == set(aes_event.door_vdi_functions())
    polled = {routine for name in aes_event.POLLED_FUNCTIONS for routine in vdi_entry_of(name)}
    assert polled and (polled <= set(aes_event.door_vdi_functions())) == aes_event.polls_in_c()
    monkeypatch.setattr(aes_event, "polls_in_c", lambda rebound=None: True)
    assert polled <= set(fsl._noting_vdi_calls([])) and set(aes_event.door_objects()) == set(aes_event.handed_routines())
    made, ran = [], []
    noted = fsl._noted({1: (b"", lambda buf, argument: ran.append(argument))}, made)
    noted[1][1](BASE_IMAGE, 7)
    assert ran == [7] and len(made) == 1 and made[0] == fsl.vdi_call_in(BASE_IMAGE)
    # ...a child's two tables (the graphics', and with the polled functions) are both noting ones, into ONE list.
    registered = []
    monkeypatch.setattr(fsl.atexit, "register", registered.append)
    graphics, every = aes_gsx.vdi_functions, aes_event.vdi_functions
    monkeypatch.setattr(aes_gsx, "vdi_functions", graphics)
    monkeypatch.setattr(aes_event, "vdi_functions", every)
    fsl.note_vdi_calls_in_a_child()
    assert set(aes_gsx.vdi_functions()) == set(graphics()) and set(aes_event.vdi_functions()) == set(every()) >= polled
    assert all(aes_event.vdi_functions()[routine][1] is not every()[routine][1] for routine in polled) and len(registered) == 1


def vdi_entry_of(name):
    """The ROM addresses the VDI function `addrs.<name>` is served at (`vdi_entry.function`'s keys)."""
    return vdi_entry.function(name)


def test_a_real_gemdos_session_s_core_that_halts_fails_its_case_by_name_not_its_worker(monkeypatch):
    """RED before `run_session` ran its C first in a fork ("worker crashed", no word
    said — the C event layer met a binding built past `door_hook`): a session whose binding serves one door entry
    too few, so the door refuses the selector's first wait and the core HALTS. In process that is the worker's
    abort; in the fork made inside the session's own pass it is the case's failure, the door's words in it."""
    event_hook = aes_event.event_hook
    but_the_wait = tuple(entry for entry in aes_event.ENTRIES if entry != addrs.AES_ROM_EV_MULTI)
    monkeypatch.setattr(aes_event, "event_hook", lambda io_seed=None: event_hook(io_seed, but_the_wait))
    machine = aes_event.typed_ahead(fsl.fs_input_machine(ss.MIXED, ""), aes_event.RETURN_KEY)
    made = aes_event.FORKS_MADE[aes_event.BY_THIS_PROCESS]
    with pytest.raises(AssertionError, match=rf"AES_ROM_FS_INPUT\(.*: the C did not return in a child \(-?\d+\): .*"
                                             rf"the event door: the case's hook refused the call"):
        fsl.run_session(machine, ss.SHORT)
    assert aes_event.FORKS_MADE[aes_event.BY_THIS_PROCESS] == made + 1


class _NoException(BaseException):
    """Something an effect might raise that is no `Exception` (as `pytest.fail`'s and `pytest.skip`'s are not)."""


WHAT_AN_EFFECT_MAY_RAISE = {"an assertion": AssertionError("a vet inside the effect"),
                            "pytest.fail": pytest.fail.Exception("a vet inside the effect"),
                            "a BaseException": _NoException("a vet inside the effect")}


def _an_image_buffer():
    return (ctypes.c_ubyte * aes_event.IMAGE_BYTES)()


def _through_its_c_callback(hook, *arguments):
    """One call of `hook` (an `AddressHook`) AS THE C MAKES IT: through its ctypes trampoline, inside a recorded pass —
    where an exception cannot cross back."""
    return hook.recording(lambda _lib, _buf: hook._trampoline(*arguments))(None, None)


@pytest.mark.parametrize("raised", WHAT_AN_EFFECT_MAY_RAISE.values(), ids=WHAT_AN_EFFECT_MAY_RAISE)
def test_what_an_effect_of_the_event_layer_s_hooks_raises_fails_its_case_whatever_it_is(raised, monkeypatch):
    """RED while a hook recorded an `Exception` alone (`address_hook.AddressHook._dispatch`): an effect that did its
    work and then raised `pytest.fail` — or any BaseException that is no Exception — was printed by ctypes and the
    case passed GREEN; an AssertionError was recorded and failed it, as ever. Shown on the two hooks the event
    layer's own C calls out through: the VDI's (the keyboard poll) and the register hook (a fork function), each
    called as the C calls it."""
    done = []

    def effect(_buf, *_arguments):
        done.append("the effect's own work")
        raise raised
    polled = next(iter(vdi_entry_of(aes_event.POLLED_FUNCTIONS[0])))
    monkeypatch.setattr(aes_event, "vdi_functions", lambda: {polled: (b"", effect)})
    monkeypatch.setattr(aes_event, "handed_routines", lambda: {addrs.AES_ROM_KCHANGE: (b"", effect)})
    registers = (ctypes.c_uint32 * len(isr.REGISTER))()
    for hook, arguments in ((isr._HOOK, (_an_image_buffer(), polled, 0)),
                            (isr.REGISTERS_HOOK, (_an_image_buffer(), addrs.AES_ROM_KCHANGE, registers))):
        done.clear()
        with pytest.raises(AssertionError, match=f"raised {type(raised).__name__}: .*a vet inside the effect"):
            with aes_event.event_layer_hooks():
                _through_its_c_callback(hook, *arguments)
        assert done == ["the effect's own work"], "the premise: the effect ran, and raised after its work"


def test_the_seam_keeps_the_words_of_an_effect_that_raised_no_assertion_when_the_run_fails_too():
    """RED while the seam's `finally` kept AssertionErrors alone: a `pytest.fail` (or a KeyError) raised inside the
    effect that awaits a twin's return, in a run that THEN failed by its image — the common shape: a twin that
    diverged — lost the effect's own words, the one diagnosis that names the call the twin went wrong at. Whatever
    the effect raised is the case's failure there, typed."""
    with pytest.raises(AssertionError, match="raised Failed: the twin handed another frame than the ROM's call") as failed:
        with aes_event.event_hook()():
            aes_event.DOOR_RETURNS.raised.append(
                (addrs.AES_ROM_TAK_FLAG, pytest.fail.Exception("the twin handed another frame than the ROM's call")))
            raise AssertionError("what the run then failed by: the final image differs")
    assert "the final image differs" not in str(failed.value)


def test_a_marked_trap_taken_inside_another_marked_trap_is_refused_by_name():
    """A `trap_taken` ordinal is of the run's MARKS (RED, on the watch itself — no session nests one today): a run
    marked at two handlers that takes one INSIDE the other would count that arrival in no run marked at both and in
    every run marked at the inner one alone, so the watch keeps the other handler armed inside a marked trap and
    refuses the nesting by name. Marked at the outer one alone, the same run is as it ever was: only the trap's
    return is watched."""
    outer, inner, sp, back = GEMDOS_TRAP, fsl.VDI_TRAP, aes_event.BAND_AT, FS_INPUT
    memory = bytearray(make_image({sp + aes_event.EXCEPTION_FRAME_PC: struct.pack(">I", back)}))

    def watch_marked_at(*handlers):
        watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS)
        return watch.marked_with(aes_event.Timeline(handlers))
    both = watch_marked_at(outer, inner)
    assert both.stopped(outer, sp, memory) == {back, inner}
    with pytest.raises(AssertionError, match=rf"took the trap at {inner:#x} INSIDE the trap at {outer:#x}, and is "
                                             rf"marked at both"):
        both.stopped(inner, sp, memory)
    alone = watch_marked_at(outer)
    assert alone.stopped(outer, sp, memory) == {back}
    assert alone.stopped(back, sp, memory) == alone.first == {*aes_event.ENTRIES, outer}


def test_a_trap_taken_inside_a_door_call_is_no_arrival():
    """The arrivals at a trap's handler are those the ROUTINE makes, outside its door calls: the event layer's own —
    the keyboard poll at the head of every ev_multi, through the VDI's `trap #2` — are not counted, on either shore,
    so the count is one both make. Held against a watch that counts them all: more, by at least each wait's poll."""
    machine, delivered = _fs_session()
    vdi_trap = fsl.VDI_TRAP
    arrivals = [arrival.at.pc for arrival in _fs_timeline(GEMDOS_TRAP, vdi_trap)[:-1]]
    assert arrivals.count(GEMDOS_TRAP) == FS_LAST_SNEXT + 1 + FS_MFREES
    every = _EveryTrap(aes_event.delivering(delivered), vdi_trap)
    assert aes_event.run_watched(_fs_image(machine), FS_INPUT, every, budget=FS_SESSION.budget)
    waits = arrivals.count(WAIT)
    assert every.arrivals - arrivals.count(vdi_trap) >= waits * VDI_CALLS_OF_A_KEYBOARD_POLL > 0


# ---- ...and fm_do's long typing session, the C against the ROM: its registered slices (`test_aes_fmdo.SESSION_SLICES`) ---
def test_the_first_key_is_cut_at_a_vdi_call_inside_it():
    """The cut `VDI_CALL_IN_THE_FIRST_KEY` is where its label says: taken after the first wait and before the second."""
    name, arguments, machine, _interrupts = fmdo.session()
    delivered = _session_deliveries(fmdo.SESSION_INSNS)
    timeline = aes_event.rom_timeline(name, arguments, machine, delivered, (fmdo.VDI_TRAP,), budget=fmdo.SESSION_INSNS)
    waits = [arrival.calls for arrival in timeline[:-1] if arrival.at.pc == fmdo.WAIT]
    inside = [arrival.at.nth for arrival in timeline[:-1]
              if arrival.at.pc == fmdo.VDI_TRAP and waits[0] < arrival.calls <= waits[1]]
    assert fmdo.VDI_CALL_IN_THE_FIRST_KEY in inside[1:-1], inside


@pytest.mark.parametrize("label", fmdo.SESSION_SLICES)
def test_each_registered_slice_of_the_typing_session_is_under_the_cap_on_the_rom_s_run(label):
    name, arguments, machine, _interrupts = fmdo.session()
    spent = aes_event.slice_cost(name, arguments, machine, _session_deliveries(fmdo.SESSION_INSNS),
                                 aes_event.Slice(*fmdo.SESSION_SLICES[label]), budget=fmdo.SESSION_INSNS)
    assert 0 < spent["insns"] < aes_event.SLICE_INSNS


def test_a_session_that_never_returns_has_no_slices():
    """The typing session with its Return never typed blocks at its last wait: marked, it is refused by name — a
    slice is of a run that ends."""
    name, arguments, machine, _interrupts = fmdo.session()
    delivered = aes_event.deliveries(name, arguments, machine, aes_event.typed(fmdo.SESSION_TEXT), fmdo.SESSION_INSNS)
    with pytest.raises(AssertionError, match="a session priced by its slices returns"):
        aes_event.rom_sliced(name, arguments, machine, delivered, aes_event.Slice(ENTRY, door_call(WAIT, 0)),
                             budget=fmdo.SESSION_INSNS)


def test_a_slice_measured_before_it_is_registered_is_held_under_the_cap():
    """`slice_cost` — what a battery cuts its session by — refuses the session whole: 728,664 instructions."""
    name, arguments, machine, _interrupts = fmdo.session()
    with pytest.raises(AssertionError, match=rf"runs {SESSION_SPEND} ROM instructions, past SLICE_INSNS"):
        aes_event.slice_cost(name, arguments, machine, _session_deliveries(fmdo.SESSION_INSNS),
                             aes_event.Slice(ENTRY, RETURN), budget=fmdo.SESSION_INSNS)


def test_a_session_nothing_is_delivered_to_registers_no_slices():
    """A session with its keys in the ring before the call has no delivery: its original would be an unwatched run,
    which nothing marks — refused by name."""
    with pytest.raises(AssertionError, match="a session priced by its slices is taken through interrupts"):
        aes_event.register_slices(fmdo.DO, FM_DO_ARGUMENTS, fmdo.in_the_ring(aes_event.RETURN_KEY), aes_event.Waits({}),
                                  {"the whole of it": (ENTRY, RETURN)}, objects=True)


# ---- A REBOUND ENTRY: an arrival, its twin run, the shadow (`aes_event.REBOUND`, `SHADOWED`) -----------------------------
# wind_update(BEG_UPDATE) over the free lock: ONE door call, tak_flag's — rebound (`src/aes/evsync.c`).
TAK_FLAG_TWIN = "aes_tak_flag"
BYTE_MASK = 0xFF


def _lock_taken():
    """`(name, arguments)` of that call — its battery imported where a case uses it (`_wm_update`)."""
    return _wm_update().WM_UPDATE, (WU["WM_BEG_UPDATE"],)


def test_the_rebound_entries_are_the_ones_whose_wrapper_the_library_marks():
    """Derived from the candidate, as the hook derives its answers: tak_flag's wrapper is spelt through EVDOOR_REBOUND
    (its marker in the library, naming its address, its twin exported) — and so, entry by entry, is every wrapper
    the header spells that way and no other: the library's markers against the source's own spelling."""
    assert hasattr(aes_event._lib, TAK_FLAG_TWIN) and addrs.AES_ROM_TAK_FLAG in aes_event.REBOUND
    header = (RECREATE / "include" / "aes" / "evdoor.h").read_text()
    spelt_rebound = {getattr(addrs, name) for name in aes_event.ENTRY_NAMES
                     if re.search(rf"EVDOOR_REBOUND(_VOID)?\({name.removeprefix(aes_event.ENTRY_PREFIX).lower()},", header)}
    assert aes_event.REBOUND == spelt_rebound
    assert aes_event.REBOUND == aes_event.rebound_in(aes_event._lib) <= aes_event.twins_in(aes_event._lib)
    assert aes_event.twins_in(aes_event._lib) <= set(aes_event.ENTRIES)
    assert aes_event.PENDING == aes_event.twins_in(aes_event._lib) - aes_event.REBOUND


class _Exporting:
    """A library that exports `symbols` (`{name: value}`) and nothing else, as `rebound_in` asks one."""

    def __init__(self, symbols):
        self.__dict__.update(symbols)


def test_a_twin_the_library_exports_with_no_marker_is_pending_not_rebound(monkeypatch):
    """THE RED for a door rebound by what the library EXPORTS — A TWIN THAT MERELY EXISTS FLIPS NOTHING (an entry is
    rebound by its wrapper's marker, so a twin can be built, and held by its leaf battery, before its flip): a
    library exporting ev_block's twin beside tak_flag's, with tak_flag's marker alone, is rebound at tak_flag only. (By the exports, as REBOUND was derived
    before, ev_block would be answered ARRIVED and its wrapper — still the nested run — halt.) And the two refusals of
    a marker: one naming another address than its entry's, and one with no twin exported."""
    marker, twin = aes_event.marker_of("AES_ROM_TAK_FLAG"), TAK_FLAG_TWIN
    monkeypatch.setattr(aes_event, "_marked_entry", getattr)
    both = _Exporting({marker: addrs.AES_ROM_TAK_FLAG, twin: None, "aes_ev_block": None})
    assert aes_event.rebound_in(both) == {addrs.AES_ROM_TAK_FLAG}
    assert aes_event.twins_in(both) - aes_event.rebound_in(both) == {addrs.AES_ROM_EV_BLOCK}
    with pytest.raises(AssertionError, match="which is not AES_ROM_TAK_FLAG"):
        aes_event.rebound_in(_Exporting({marker: addrs.AES_ROM_EV_BLOCK, twin: None}))
    with pytest.raises(AssertionError, match="spelt rebound and the library exports no aes_tak_flag"):
        aes_event.rebound_in(_Exporting({marker: addrs.AES_ROM_TAK_FLAG}))


def _lock_taken_in_process():
    """That call's differential — its C FIRST IN A CHILD (`run_guarded`): a wrapper and a hook that disagree about the
    entry halt the core, which in a child is a failure by name and in process a dead worker."""
    return aes_event.run_guarded(*_lock_taken(), aes_event.machine())


def _no_nested_run(*_run, **_named):
    raise AssertionError("a nested run was made")


def test_a_rebound_entry_s_call_is_its_twin_s_run_and_no_nested_run_s(monkeypatch):
    """With the shadow off and every nested run refused, the lock's differential still holds: the image the C leaves
    is its twin's own — and the frame the arrival noted is the ROM's call's."""
    monkeypatch.setattr(aes_event, "SHADOWED", frozenset())
    monkeypatch.setattr(aes_event, "nested_run", _no_nested_run)
    result = _lock_taken_in_process()
    assert result.answer() == 1 and [call.routine for call in aes_event.HANDED] == [addrs.AES_ROM_TAK_FLAG]


def test_an_arrival_s_frame_is_compared_with_the_rom_s_call_s(monkeypatch):
    """LOAD-BEARING: an arrival that noted nothing is red — the frames handed are compared for a rebound entry too."""
    arrived = aes_event._arrived
    monkeypatch.setattr(aes_event, "_arrived", lambda routine, io_seed, _noted, shadows, **binding: arrived(
        routine, io_seed, lambda _call: None, shadows, **binding))
    with pytest.raises(AssertionError, match="the door was handed"):
        _lock_taken_in_process()


def _shadow_other_than_the_rom_s(monkeypatch, changed):
    """Every shadow's nested run `changed(nested)`: as the ROM's routine would be to a twin that is not it."""
    nested_run = aes_event.nested_run
    monkeypatch.setattr(aes_event, "nested_run", lambda *run, **named: changed(nested_run(*run, **named)))


def test_a_twin_that_answers_other_than_the_rom_s_routine_is_red_at_its_call(monkeypatch):
    """THE RED the shadow exists for: the twin's answer held, at its own call, to the ROM routine's over the image the
    call arrived with — named by the entry and the call, whatever the routine's own differential then says."""
    _shadow_other_than_the_rom_s(monkeypatch, lambda nested: nested._replace(answer=nested.answer ^ 1))
    with pytest.raises(AssertionError, match=f"the shadow: the twin of {addrs.AES_ROM_TAK_FLAG:#x} answered 0x1 where"):
        _lock_taken_in_process()


def test_a_twin_that_leaves_other_bytes_than_the_rom_s_routine_is_red_at_its_call(monkeypatch):
    """...and its image: one byte the ROM's routine wrote and the twin did not (a byte nothing else reads)."""
    other = ~BASE_IMAGE[UNREAD_BYTE] & BYTE_MASK
    _shadow_other_than_the_rom_s(monkeypatch,
                                 lambda nested: nested._replace(writes={**nested.writes, UNREAD_BYTE: other}))
    with pytest.raises(AssertionError, match=f"the twin of {addrs.AES_ROM_TAK_FLAG:#x} left another image.*{UNREAD_BYTE:#x}"):
        _lock_taken_in_process()


def test_the_shadow_s_one_compare_passes_what_the_address_by_address_compare_passes():
    """The shadow's passing case is ONE compare — the image the call arrived with, the nested run's COMPARED writes laid
    in — and anything else is compared address by address. Held at the three places the two could part: a twin that
    stored NOTHING where the ROM's routine stored a compared byte is refused; one that stored nothing where the routine
    wrote only what neither shore compares (its own frames, in the stack band) passes; and so does one that wrote
    there itself."""
    arrived, call = bytes(BASE_IMAGE), aes_event.Handed(addrs.AES_ROM_TAK_FLAG, ())
    in_the_band = case.STACK_BAND[0]

    def shadow(writes):
        return aes_event.Shadow(call, arrived, aes_event.Nested(writes, 0, 0))
    with pytest.raises(AssertionError, match=f"left another image.*{UNREAD_BYTE:#x}"):
        aes_event.vet_the_shadow(shadow({UNREAD_BYTE: ~BASE_IMAGE[UNREAD_BYTE] & BYTE_MASK}), arrived, 0)
    aes_event.vet_the_shadow(shadow({in_the_band: ~BASE_IMAGE[in_the_band] & BYTE_MASK}), arrived, 0)
    wrote_its_own_frame = bytearray(arrived)
    wrote_its_own_frame[in_the_band] ^= BYTE_MASK
    aes_event.vet_the_shadow(shadow({}), bytes(wrote_its_own_frame), 0)


def test_the_shadow_s_refusal_is_the_case_s_failure_whatever_its_differential_then_says(monkeypatch):
    """A twin wrong at its call usually leaves a final image that differs too: the case then fails by the SHADOW's
    words, which name the call — not by the differential's, which would name the session's end."""
    run = case.run

    def differing_at_its_end(*call, **named):
        run(*call, **named)
        raise AssertionError("the differential's own failure")
    monkeypatch.setattr(case, "run", differing_at_its_end)
    with pytest.raises(AssertionError, match="the differential's own failure"):
        _lock_taken_in_process()         # the premise: with the twin its shadow, the case fails by the differential
    _shadow_other_than_the_rom_s(monkeypatch, lambda nested: nested._replace(answer=nested.answer ^ 1))
    with pytest.raises(AssertionError, match="the shadow: the twin of"):
        _lock_taken_in_process()


SHADOW_ANSWERS_ANOTHER_WORD = ("run = aes_event.nested_run; aes_event.nested_run = lambda *call, **named: "
                               "(lambda nested: nested._replace(answer=nested.answer ^ 1))(run(*call, **named)); ")


def test_a_twin_that_is_not_its_shadow_ends_the_child_by_name():
    """In a child the twin's return is reported to a `void` hook: a twin that is not its shadow ENDS the child there
    (CHILD_SHADOW_REFUSED), by the shadow's words — never carried on over the image it left."""
    bind = aes_event.child_binding(before=SHADOW_ANSWERS_ANOTHER_WORD)
    returncode, stderr, _image = aes_event.refusal(_lock_taken()[0], aes_event.machine(), _lock_taken()[1], bind=bind)
    assert returncode == aes_event.CHILD_SHADOW_REFUSED and "the shadow: the twin of" in stderr, stderr


def test_the_shadow_holds_the_twin_s_answer_as_the_word_its_wrapper_hands_on():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the lock's owner, staged with a top byte: no ROM run stores one —
    `test_aes_evsync.py`'s labelled case, through the door). tak_flag's refusal leaves the owner's high word in D0
    over its zero: the shadow compares the WORD a wrapper hands on. The screen manager asking for PD0's lock: the
    twin's 0 is the ROM routine's — the call goes on to its wait, which blocks, and no shadow refuses."""
    wm_update = _wm_update()
    tagged = merge_pokes(evsync.held_by_another(), {wm_update.WIND_SPB + wm_update.SPB_OWNER:
                                                    struct.pack(">I", aes.SHELL_PD | aes.BUS_TAG)})
    returncode, stderr, _image = aes_event.refusal(wm_update.WM_UPDATE, tagged, (wm_update.BEG_UPDATE,))
    assert returncode not in (0, aes_event.CHILD_SHADOW_REFUSED) and aes_event.BLOCKS in stderr, (returncode, stderr)
    assert "the shadow" not in stderr
    assert [call.routine for call in aes_event.handed_in(stderr)] == [addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_EV_BLOCK]




def _a_call_arriving():
    """What the hook hands an arrival's effect: the image, tak_flag's frame and its size."""
    image = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer(make_image(aes_event.machine()))
    frame = aes_event.SEMAPHORE_FRAME.pack(_wm_update().WIND_SPB)
    return image, ctypes.create_string_buffer(frame, len(frame)), len(frame)


def test_a_refused_shadow_leaves_its_call_s_place_empty_and_the_return_is_refused_over_it(monkeypatch):
    """A shadow whose making RAISES (its nested run refused) has taken its call's place all the same: the twin's
    return — should the core carry on — is refused by name over ITS OWN place, which it gives up; and a return with
    no arrival in flight is refused too."""
    def refused(*_call):
        raise AssertionError("the event door: the nested run was refused")
    shadows = []
    monkeypatch.setattr(aes_event, "shadow_of", refused)
    with pytest.raises(AssertionError, match="the nested run was refused"):
        aes_event._arrived(addrs.AES_ROM_TAK_FLAG, None, lambda _call: None, shadows)(*_a_call_arriving())
    assert shadows == [aes_event.SHADOW_NOT_MADE]
    with pytest.raises(AssertionError, match="the arrival it answers has no shadow of its own"):
        aes_event._returned(addrs.AES_ROM_TAK_FLAG, shadows)(_a_call_arriving()[0], 1)
    assert shadows == []
    with pytest.raises(AssertionError, match="no arrival of this binding is in flight"):
        aes_event._returned(addrs.AES_ROM_TAK_FLAG, [])(_a_call_arriving()[0], 1)


def test_an_arrival_at_an_entry_no_shadow_is_made_for_still_takes_its_place(monkeypatch):
    """EVERY arrival takes a place until its twin's return — the shadow off, too: the place is what says a twin is
    running (below). Its return gives it up and vets nothing."""
    shadows = []
    monkeypatch.setattr(aes_event, "SHADOWED", frozenset())
    monkeypatch.setattr(aes_event, "nested_run", _no_nested_run)
    aes_event._arrived(addrs.AES_ROM_TAK_FLAG, None, lambda _call: None, shadows)(*_a_call_arriving())
    assert shadows == [aes_event.NOT_SHADOWED]
    aes_event._returned(addrs.AES_ROM_TAK_FLAG, shadows)(_a_call_arriving()[0], 0)
    assert shadows == []


# ---- (g) A NESTED ARRIVAL IS REFUSED BY NAME -------------------------------------------------------------------------------
@pytest.mark.parametrize("shadowed", (True, False), ids=("its entry shadowed", "the shadow off"))
def test_a_door_call_from_inside_a_twin_is_refused_by_name(monkeypatch, shadowed):
    """THE RUNTIME GUARD of "a twin calls another entry's core, never its wrapper": while a twin runs — its arrival
    made, its return not reported — any call of the hook is refused by name, an arrival at the same entry and at
    another alike, BEFORE anything is noted or run. (Counted, the inner call would shift every ordinal after it on
    the host alone: G3's C1.) Once the twin has returned, the door takes arrivals again."""
    if not shadowed:
        monkeypatch.setattr(aes_event, "SHADOWED", frozenset())
    shadows, noted = [], []
    arrive = aes_event._arrived(addrs.AES_ROM_TAK_FLAG, None, noted.append, shadows)
    arrive(*_a_call_arriving())
    with pytest.raises(AssertionError, match="called through its wrapper INSIDE the twin of .* a nested arrival"):
        arrive(*_a_call_arriving())
    with pytest.raises(AssertionError, match=f"{addrs.AES_ROM_EV_BLOCK:#x} was called through its wrapper INSIDE the twin"):
        aes_event._arrived(addrs.AES_ROM_EV_BLOCK, None, noted.append, shadows)(*_a_call_arriving())
    assert len(noted) == 1 and len(shadows) == 1, "the refused calls noted nothing and took no place"
    image = _a_call_arriving()[0]
    taken = getattr(aes_event._lib, TAK_FLAG_TWIN)(image, WU["AES_WIND_SPB"])      # the twin itself, as the wrapper runs it
    aes_event._returned(addrs.AES_ROM_TAK_FLAG, shadows)(image, taken)
    arrive(*_a_call_arriving())
    assert len(noted) == 2


def test_in_process_a_nested_arrival_fails_the_case_by_name_and_halts_no_core():
    """IN PROCESS (`event_hook`, every `run_event`) the same guard, and its words SURVIVE: a hook that refused there
    would halt the core — an abort inside the worker, pytest's captured output lost with it (a serial run of the
    battery reported NOTHING at all). So the binding in process KEEPS the refusal and answers the call as the
    door would — the arrival noted — and the case fails by the guard's words when its pass closes.
    Shown through the hook's own trampoline, as the C calls it: tak_flag's arrival, then — no return between — a
    second arrival and one at unsync."""
    image, frame, frame_bytes = _a_call_arriving()
    bytes_at = ctypes.POINTER(ctypes.c_uint8)
    verdicts = []

    def a_twin_that_calls_two_wrappers(_lib, buf):
        for entry in (addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_UNSYNC):
            verdicts.append(aes_event.EVENT_DOOR._trampoline(buf, entry, ctypes.cast(frame, bytes_at), frame_bytes))
    hook = aes_event.event_hook()
    with pytest.raises(AssertionError, match=f"{addrs.AES_ROM_TAK_FLAG:#x} was called through its wrapper INSIDE the twin of "
                                             f"{addrs.AES_ROM_TAK_FLAG:#x} — a nested arrival"):
        with hook():
            aes_event.EVENT_DOOR.recording(a_twin_that_calls_two_wrappers)(None, ctypes.cast(image, bytes_at))
    assert verdicts == [aes_event.ARRIVED] * 3, "answered, never REFUSED: no core halts in the worker"
    with hook():                        # ...and the same binding's next pass closes clean: the refusals were that run's
        pass


def test_the_child_s_door_refuses_a_nested_arrival_too():
    """...and in a child (`bind_in_a_child`, where a door user's blocking and interrupted cases run): the refusal is
    the hook's answer, and the core halts by name with the guard's words in its stderr. Shown by a child whose hook is
    told a twin is already running when wind_update's own tak_flag arrives."""
    a_twin_running = ("arrived = aes_event._arrived; aes_event._arrived = lambda routine, io_seed, noted, shadows, rebound: "
                      "(shadows.append(aes_event.NOT_SHADOWED), arrived(routine, io_seed, noted, shadows, rebound))[1]; ")
    bind = aes_event.child_binding(before=a_twin_running)
    returncode, stderr, _image = aes_event.refusal(_lock_taken()[0], aes_event.machine(), _lock_taken()[1], bind=bind)
    assert returncode != 0 and "INSIDE the twin of a rebound entry — a nested arrival" in stderr, stderr
    assert "the event door: the case's hook refused the call" in stderr


def test_a_binding_s_shadows_are_its_own_and_empty_when_a_case_opens_it(monkeypatch):
    """The arrivals in flight are a list of the BINDING's, emptied each time a case opens it: a run that ended inside
    a twin's call (a refusal, an exception) leaves nothing for the next run's first return to pop — and two bindings
    share none."""
    handed_to, arrived = [], aes_event._arrived
    monkeypatch.setattr(aes_event, "_arrived", lambda routine, io_seed, noted, shadows, **binding: (
        handed_to.append(shadows) or arrived(routine, io_seed, noted, shadows, **binding)))
    hook, _another = aes_event.event_hook(), aes_event.event_hook()
    its_own, the_other_s = handed_to[0], handed_to[-1]
    assert its_own is not the_other_s
    # ...every entry of each binding (an arrival each) handed that binding's list.
    arrivals = len(aes_event.ENTRIES)
    assert [each is its_own for each in handed_to] == [True] * arrivals + [False] * arrivals
    assert all(each is the_other_s for each in handed_to[arrivals:])
    its_own.append("an arrival a dead run left")
    with hook():
        assert its_own == []


# THE WRAPPER AND THE HOOK MUST AGREE which entries are rebound: every wrapper runs a twin, so a hook that knows no
# twin of an entry — or answers its arrival with any word but ARRIVED — halts the core by name.
HOOK_KNOWS_NO_TWIN = "aes_event.rebound_in = lambda lib: frozenset(); "
A_WORD_NO_HOOK_ANSWERS = 7
HOOK_ANSWERS_ANOTHER_WORD = f"aes_event.ARRIVED = {A_WORD_NO_HOOK_ANSWERS}; "
assert A_WORD_NO_HOOK_ANSWERS not in (aes_event.ARRIVED, aes_event.REFUSED_ANSWER)


def test_an_entry_the_hook_knows_no_twin_of_is_refused_and_the_core_halts_by_name():
    """A hook that reads no marker off the library — tak_flag no rebound entry of its — where the wrapper runs the
    twin: the arrival is refused (the hook notes nothing, shadows nothing), and the core halts by name before the twin
    runs unwatched."""
    bind = aes_event.child_binding(before=HOOK_KNOWS_NO_TWIN)
    returncode, stderr, _image = aes_event.refusal(_lock_taken()[0], aes_event.machine(), _lock_taken()[1], bind=bind)
    assert returncode != 0 and "does not serve" in stderr and "the event door: the case's hook refused the call" in stderr, stderr


def test_a_hook_that_answers_another_word_than_arrived_halts_by_name():
    """...and an answer that is neither ARRIVED nor a refusal (what a callback that raised leaves in D0, a stale
    protocol) is no licence to run the twin: halted by name."""
    bind = aes_event.child_binding(before=HOOK_ANSWERS_ANOTHER_WORD)
    returncode, stderr, _image = aes_event.refusal(_lock_taken()[0], aes_event.machine(), _lock_taken()[1], bind=bind)
    assert returncode != 0 and "the hook answered neither ARRIVED nor REFUSED" in stderr, stderr


# ---- A TWIN CALLS ANOTHER ENTRY'S CORE, NEVER ITS WRAPPER (`aes/evdoor.h`) -------------------------------------------------
# Derived from the build: the wrappers are inline, so a function that calls one REFERENCES THE DOOR'S HOOKS — and so
# does any function that calls it, in whatever file. THE HOST BUILD'S OWN CALL GRAPH: every source of the candidate
# compiled as kit.mk compiles it (`$(CC) $(CFLAGS)`, as make itself expands them: one statement of the flags), each
# object's functions (`nm`) and what the instructions of each refer to (its relocations) — a call, or a hook's pointer
# loaded — closed over every translation unit.
RECREATE = Path(__file__).resolve().parents[1]
DOOR_HOOKS = frozenset({aes_event.HOOK_SYMBOL, aes_event.RETURNED_SYMBOL})
ALL_HOOKS = frozenset({*aes_event.FORK_UNSERVED_HOOKS, aes_event.DISPATCH_SYMBOL})
COMPILERS_AT_ONCE = 8
_A_RELOCATION = re.compile(r"^([0-9a-f]{8,16})\s+\S+\s+(\S+)$", re.MULTILINE)
_A_FUNCTION = re.compile(r"^([0-9a-f]{8,16}) [Tt] (\S+)$", re.MULTILINE)
_TEXT_RELOCATIONS = re.compile(r"RELOCATION RECORDS FOR \[[^\]]*text[^\]]*\]:\n(.*?)(?:\n\n|\Z)", re.DOTALL)
ASSEMBLER_TEMPORARY = "ltmp"           # Mach-O's section-start labels: they name no function


def _host_compiler():
    """kit.mk's compile of one candidate source, as make expands it: `$(CC) $(CFLAGS)` (its `-I`s relative to here)."""
    probe = "include Makefile\nprint-compile:\n\t@echo $(CC) $(CFLAGS)\n"
    return subprocess.run(["make", "-s", "-f", "-", "print-compile"], input=probe, cwd=RECREATE, capture_output=True,
                          text=True, check=True).stdout.split()


def _tool(*command):
    return subprocess.run(command, cwd=RECREATE, check=True, capture_output=True, text=True).stdout


def _object_s_references(source, scratch, compiler):
    """`{function: the symbols its instructions refer to}` for the host object of `source` — each function the span
    from its symbol to the next, each relocation of the text booked to the function it lies in."""
    built = scratch / (source.relative_to(RECREATE).as_posix().replace("/", "_") + ".o")
    _tool(*compiler, "-c", str(source), "-o", str(built))
    functions = sorted((int(at, 16), name.lstrip("_")) for at, name in _A_FUNCTION.findall(_tool("nm", "-n", str(built)))
                       if not name.startswith(ASSEMBLER_TEMPORARY))
    starts = [at for at, _name in functions]
    referred = {name: set() for _at, name in functions}
    for text in _TEXT_RELOCATIONS.findall(_tool("objdump", "-r", str(built))):
        for at, symbol in _A_RELOCATION.findall(text):
            holder = bisect.bisect_right(starts, int(at, 16)) - 1
            if holder >= 0:
                referred[functions[holder][1]].add(symbol.lstrip("_"))
    return referred


@pytest.fixture(scope="module")
def host_graph(tmp_path_factory):
    """`{(file, function): the symbols it refers to}` over every source of the candidate, and `{function: its file}`
    for the functions other files may call: the host build's call graph, a static's node its own file's."""
    scratch, compiler = tmp_path_factory.mktemp("host_objects"), _host_compiler()
    sources = sorted((RECREATE / "src").glob("**/*.c"))
    with concurrent.futures.ThreadPoolExecutor(COMPILERS_AT_ONCE) as pool:
        objects = list(pool.map(lambda source: _object_s_references(source, scratch, compiler), sources))
    graph = {(source, function): referred for source, functions in zip(sources, objects)
             for function, referred in functions.items()}
    return graph, {function: source for source, function in graph}


def _hooks_reached_from(core, host_graph, hooks=ALL_HOOKS):
    """The `hooks` any function reachable from the C function `core` refers to, over the host build's call graph."""
    graph, defined_in = host_graph
    reached, frontier, found = set(), [(defined_in[core], core)], set()
    while frontier:
        node = frontier.pop()
        if node in reached:
            continue
        reached.add(node)
        for symbol in graph[node]:
            found |= {symbol} & hooks
            callee = (node[0], symbol) if (node[0], symbol) in graph else (defined_in.get(symbol), symbol)
            if callee in graph:
                frontier.append(callee)
    return found


ONE_GRAPH = pytest.mark.collected_with("the host build's call graph")     # back to back: one worker compiles it once


@ONE_GRAPH
def test_no_twin_reaches_a_door_wrapper(host_graph):
    """A twin reaches neither of the door's hooks, by whatever calls: it calls no `evdoor_*` wrapper, nor a helper
    that does, IN ANY FILE — another entry is reached by its core. THE PREMISES the derivation rests on, held beside
    it: a door USER does reach both hooks (wind_update, which takes the lock through `evdoor_tak_flag` — the hook
    asked, and the twin's return reported), and the graph crosses translation units (gr_rubbox's own file refers to
    neither: it reaches them through the files of the lock and of the wait it calls)."""
    graph, defined_in = host_graph
    assert _hooks_reached_from("aes_wm_update", host_graph, DOOR_HOOKS) == DOOR_HOOKS, "the premise"
    in_its_own_file = set().union(*(referred for (source, _name), referred in graph.items()
                                    if source == defined_in[ACROSS_FILES]))
    assert not in_its_own_file & DOOR_HOOKS and _hooks_reached_from(ACROSS_FILES, host_graph, DOOR_HOOKS) == DOOR_HOOKS, (
        "the premise: a door user reached across files")
    linked = aes_event.twins_in(aes_event._lib)        # rebound AND pending: the rule is a twin's from the day it exists
    twins = {name: routines.core_symbol(name) for name in aes_event.ENTRY_NAMES if getattr(addrs, name) in linked}
    assert aes_event.REBOUND and aes_event.REBOUND <= linked, "the premise: an entry is rebound"
    for name, core in twins.items():
        reached = _hooks_reached_from(core, host_graph, DOOR_HOOKS)
        assert not reached, (
            f"{core} (the twin of {name}) reaches a door wrapper — it, or a function it calls, refers to "
            f"{sorted(reached)}: a twin calls another entry's CORE — through the wrapper the host counts an arrival "
            f"neither watched run makes (`aes/evdoor.h`)")


ACROSS_FILES = "aes_gr_rubbox"         # a door user none of whose own file's functions calls a wrapper
# The routines guarded in a fork, each with the hooks its fork SERVES (`run_core_guarded`'s `serves`; none, for most):
# the lock's, the lists' and the processes' — and every layer's whose helper module names its own (`FORK_GUARDED`:
# names, or `{name: serves}`). WHICH MODULES is read off the test directory — every `aes_*.py` that ASSIGNS the name
# at its top level — never typed: a typed pair left two declarations (ev_multi's, the dispatcher's) read by nothing.
# Imported when the test asks: a helper module's import makes its machines, which every worker collecting this file
# would pay.
_DECLARES_ITS_OWN = re.compile(r"^FORK_GUARDED\s*=", re.M)


def batteries_naming_their_own():
    """The helper modules of this directory that declare `FORK_GUARDED`, by name."""
    return tuple(sorted(path.stem for path in Path(__file__).resolve().parent.glob("aes_*.py")
                        if _DECLARES_ITS_OWN.search(path.read_text())))


def _named_by(module):
    """`{routine: the hooks its fork serves}` as the helper module `module` names them."""
    guarded = getattr(importlib.import_module(module), "FORK_GUARDED")
    return dict(guarded) if isinstance(guarded, dict) else dict.fromkeys(guarded, ())


def _guarded_in_a_fork():
    return {**dict.fromkeys((evsync.TAK_FLAG, *aes_evasync.ROUTINES, *aes_pdpipe.SIGNATURES), ()),
            **{name: serves for module in batteries_naming_their_own() for name, serves in _named_by(module).items()}}


def test_every_module_that_declares_fork_guarded_is_read_by_the_census():
    """RED while the census named two modules by hand: `aes_evmulti.FORK_GUARDED` (ev_multi) and
    `aes_switch.FORK_GUARDED` (disp_act, mwait_act, idle) were declared and held to no call graph. Every declaring
    module is read, whole — the four layers at least."""
    declaring = batteries_naming_their_own()
    assert {"aes_evinput", "aes_evlib", "aes_evmulti", "aes_switch"} <= set(declaring)
    census = _guarded_in_a_fork()
    for module in declaring:
        assert set(_named_by(module)) <= set(census), module
        assert all(census[name] == serves for name, serves in _named_by(module).items()), module


@ONE_GRAPH
def test_a_core_guarded_in_a_fork_reaches_no_hook_but_the_dispatcher_s(host_graph):
    """THE PREMISE OF THE FORK'S ROAD, held at the build: the cores the lists', the processes' and the lock's batteries
    run behind a fork (`run_core_guarded`) reach no hook a fork refuses, on any path — not only on the paths their
    cases take, where the fork itself would refuse one by name. (A door user does: the same derivation's RED.)"""
    unserved = frozenset(aes_event.FORK_UNSERVED_HOOKS)
    guarded = _guarded_in_a_fork()
    assert all(frozenset(serves) <= aes_event.FORK_SERVABLE_HOOKS for serves in guarded.values())
    reaching = {name: sorted(_hooks_reached_from(routines.core_symbol(name), host_graph, unserved - frozenset(serves)))
                for name, serves in guarded.items()}
    assert not any(reaching.values()), (
        f"guarded in a fork, and reaching a hook no fork serves: { {name: hooks for name, hooks in reaching.items() if hooks} }"
        f" — such a core's guard is a fresh interpreter's (`run_guarded`)")
    assert _hooks_reached_from("aes_wm_update", host_graph, unserved) >= DOOR_HOOKS


# ---- interrupts at a REBOUND entry's arrival -----------------------------------------------------------------------------
def _rubber_box_released_as_the_lock_is_taken():
    """gr_rubbox under the button down, the button RELEASED at its door call 0 — the screen lock's tak_flag, a rebound
    entry: its first wait (call 1) then finds the rise."""
    box = grdrag.RUBBER["stretched to the mouse"][:4]
    return (grdrag.GR_RUBBOX, (*box, grdrag.FIRST_OUT, grdrag.SECOND_OUT), grdrag.button_down(), {0: aes_event.release})


def test_an_interrupt_is_delivered_at_a_rebound_entry_s_arrival_on_both_shores():
    """A delivery hangs on an arrival as on any door call: laid into the ROM's run at tak_flag's entry and into the C's
    image before its twin runs (and, by the bench's second differential, into our blob's run at the twin's first
    instruction). Both return, the image the ROM's."""
    taken = aes_event.interrupted(*_rubber_box_released_as_the_lock_is_taken())
    assert taken.returned and [call.routine for call in taken.calls][:2] == [addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_EV_MULTI]
    assert set(taken.delivered) == {0}


ARRIVALS_NOT_COUNTED = ("arrived = aes_event._arrived; aes_event._arrived = lambda routine, io_seed, noted, *binding: "
                        "arrived(routine, io_seed, lambda call: None, *binding); ")


DIES_BEFORE_ANY_DOOR_CALL = "raise SystemExit('the child died before any door call'); "
# What the C's child says when a wait of its gets nothing where the ROM's run returns: its ev_multi — the C twin —
# reached the dispatcher's hook.
WHO_REACHED_THE_DISPATCHER = "the dispatcher's hook: the C reached the dispatcher"
THE_WAIT_BLOCKED_IN_THE_CHILD = (rf"the C's child did not:[\s\S]*{re.escape(WHO_REACHED_THE_DISPATCHER)}[\s\S]*"
                                 rf"{aes_event.BLOCKS}")


def _stretched_then_released_by_a_child_that_first_runs(monkeypatch, before):
    """gr_rubbox stretched, then released — interrupts at its door calls 1 and 2 — its C's child running the source
    `before` ahead of its binding."""
    name, arguments, machine, interrupts, _answer, _out = grdrag.INTERRUPTED["gr_rubbox: stretched, then released"]
    binding = aes_event.child_binding
    monkeypatch.setattr(aes_event, "child_binding",
                        lambda **named: binding(**{**named, "before": before + named.get("before", "")}))
    return aes_event.interrupted(name, arguments, machine(), interrupts)


def test_an_arrival_not_counted_among_the_door_calls_lays_every_delivery_a_call_late(monkeypatch):
    """THE RED for the ordinals: a C side that did not count a rebound entry's arrival as a door call would lay each
    delivery one call late — gr_rubbox's stretch at call 1 and its release at call 2 (call 0 the lock's tak_flag): the
    wait owed the move gets nothing, and the child blocks where the ROM's run returns."""
    with pytest.raises(AssertionError, match=THE_WAIT_BLOCKED_IN_THE_CHILD):
        _stretched_then_released_by_a_child_that_first_runs(monkeypatch, ARRIVALS_NOT_COUNTED)


def test_a_child_that_died_of_anything_else_is_not_taken_for_a_delivery_laid_late(monkeypatch):
    """...and THE REASON is what that RED matches — the wait blocked at the dispatcher — not the child's death alone:
    a child that dies before any door call (here: its binding raises) fails the case by other words."""
    with pytest.raises(AssertionError, match="the C's child did not") as died:
        _stretched_then_released_by_a_child_that_first_runs(monkeypatch, DIES_BEFORE_ANY_DOOR_CALL)
    assert not re.search(THE_WAIT_BLOCKED_IN_THE_CHILD, str(died.value))


# ---- THE DISPATCHER'S HOOK (`aes/switch.h`): refused by name, the image the ROM's at dsptch -------------------------------
DSPTCH_ENTERED = "aes_dsptch_entered"  # the host's dsptch as a case calls it (`src/aes/evdoor.c`)


def _rom_at_dsptch(entry, frame, machine):
    """The ROM's `entry` over `machine` with `frame`, run until it reaches dsptch: the image there."""
    image = make_image(merge_pokes(machine, {aes_event.abi.FIRST_ARG: frame}))
    final, _writes, regs = emu.run(image, entry, stop_pc=addrs.AES_ROM_DSPTCH)
    assert regs["checkpoint"], "the premise: the call reaches the dispatcher"
    return bytes(final)


def _c_at_dsptch(image):
    """The host's dsptch entered over `image` in a child, the dispatcher's hook bound: `(returncode, stderr, image)`."""
    pokes = aes_event.as_pokes(image)
    return vdi_helpers.refusal_over(DSPTCH_ENTERED, pokes, bind=aes_event.CHILD_BINDING)


AT_DSPTCH = {
    # ev_multi for a key with none typed: mwait leaves the process WAITING and calls dsptch.
    "a wait nothing satisfies: it would block": (
        lambda: _rom_at_dsptch(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT, aes_event.machine()), aes_event.BLOCKS),
    # unsync handing the lock to the process waiting for it: the releaser calls dsptch still READY.
    "the lock handed to its waiter: it would yield": (
        lambda: _rom_at_dsptch(addrs.AES_ROM_UNSYNC, SPB, _wm_update().waited_on()), aes_event.YIELDS),
}


@pytest.mark.parametrize("at_dsptch, switches", AT_DSPTCH.values(), ids=AT_DSPTCH)
def test_the_dispatcher_reached_is_refused_by_name_over_the_rom_s_image_at_dsptch(at_dsptch, switches):
    """THE REFUSING DISPATCH HOOK: the C's dsptch entered over the image the ROM's own run holds AT DSPTCH — every list,
    EVB and PD as its wait or its hand-over left them — is refused, told a block from a yield by the process's status
    as the door tells them, the core halted by name.

    WHAT `left == image` COMPARES TODAY: the image the child was HANDED (the ROM's at dsptch) with the image it left —
    it shows that the hook and the halt STORE NOTHING, and no more: no C runs between an entry and dsptch yet
    (tak_flag is a leaf), so no C is held to the ROM at dsptch by this test. The mechanism that will hold one —
    a blocked rebound entry compared where its twin stops (`_watched_through`'s `rebound`) — is pinned on the ROM's
    side below; THE COMPOSED PATH, a twin running into this hook under `refused_where_the_rom_blocks`, first runs
    in wave 1 (unsync, ev_block)."""
    image = at_dsptch()
    returncode, stderr, left = _c_at_dsptch(image)
    assert returncode != 0 and switches in stderr and "the dispatcher: the case's hook refused the call" in stderr, stderr
    assert left == image
    assert aes_event.handed_in(stderr) == [], "the door calls made before it are reported with the refusal: none here"


def test_the_snapshot_s_guard_does_not_turn_the_dispatcher_s_refusal_into_a_return():
    """Under the snapshot's guard (AES_INDISP 1) the ROM's dsptch is a bare `rts`: the hook is asked before any guard,
    and refuses the same — no process runs with it set."""
    image = bytearray(AT_DSPTCH["a wait nothing satisfies: it would block"][0]())
    image[aes.AES_INDISP] = aes.AES_INDISP_SET
    returncode, stderr, _left = _c_at_dsptch(bytes(image))
    assert returncode != 0 and aes_event.BLOCKS in stderr, stderr


def test_the_child_binds_the_dispatcher_s_hook_into_the_candidate_it_calls(monkeypatch, tmp_path):
    """...into the library the CHILD loaded, as every hook is (a COPY of the candidate is another library to the loader:
    left as this module's import binds it, the copy's pointer is NULL — a crash, not a refusal)."""
    copy = tmp_path / "candidate_copy.so"
    shutil.copyfile(vdi_helpers.LIB, copy)
    monkeypatch.setattr(vdi_helpers, "LIB", copy)
    returncode, stderr, _left = _c_at_dsptch(AT_DSPTCH["a wait nothing satisfies: it would block"][0]())
    assert returncode != 0 and aes_event.BLOCKS in stderr, (returncode, stderr)


DISPATCHER_ANSWERS = ("served = aes_event.DISPATCH_PROTOTYPE(lambda buf: 1); aes_event._CHILD_TRAMPOLINES.append(served); "
                      "aes_event.bind_pointer(aes_event.DISPATCH_SYMBOL, served, lib)")


def test_only_the_hook_s_refusal_halts_the_dispatcher_s_caller():
    """THE RED for the refusal: with a hook that answers "returned", the same call comes back to its caller as if the
    machine had switched away and back — the outcome the refusing hook exists to keep from every case."""
    image = AT_DSPTCH["a wait nothing satisfies: it would block"][0]()
    pokes = aes_event.as_pokes(image)
    returncode, stderr, _left = vdi_helpers.refusal_over(DSPTCH_ENTERED, pokes,
                                                         bind=aes_event.CHILD_BINDING + "; " + DISPATCHER_ANSWERS)
    assert returncode == 0, stderr


def test_a_blocked_rebound_entry_is_compared_where_its_twin_stops_at_dsptch():
    """Where a call that blocks is compared: AT DSPTCH, where the entry's twin reaches the dispatcher's hook. The
    watched run of gr_stilldn's blocking wait answers the ROM's memory at dsptch — the unwatched run's, stopped
    there — and not its memory at the call's entry: the wait wrote before it asked for the switch."""
    name, arguments = WOULD_BLOCK
    machine = grwait.button_down()
    calls, at_dsptch, blocked = aes_event._watched_through(name, arguments, machine, {})
    assert blocked is None and [call.routine for call in calls] == [addrs.AES_ROM_EV_MULTI]
    final, _writes, regs = emu.run(make_image(aes.staged(name, arguments, machine)), getattr(addrs, name),
                                   stop_pc=addrs.AES_ROM_DSPTCH)
    assert regs["checkpoint"] and not aes_event.differing(at_dsptch, final, not_compared=frozenset())
    at_the_entry, _call = aes_event.rom_entered(name, arguments, machine, {}, 0)
    assert aes_event.differing(at_the_entry, at_dsptch), "the premise: the wait wrote something before dsptch"


# ---- (a) A RUN ENTERED AT A DOOR ENTRY: no arrival at its own entry (`DoorStops.entered_at`) -------------------------------
THE_LOCK = (WU["AES_WIND_SPB"],)
A_PRESS = (1, aes.EV_BUTTON_LEFT, 1, ANSWERS_AT)       # ev_button(one click, the left button, down, answers)


def test_a_watched_run_entered_at_an_entry_makes_no_door_call_of_it():
    """tak_flag's own run, watched as its callers' are: it is ENTERED, not called — no door call, and it returns.
    RED (G3's probe, the run every twin's own frames case and row needs): without `entered_at` the bench stops at the
    run's first instruction, a listed PC, whose return address is the run's sentinel — "not a door call"."""
    calls, _memory, result = aes_event._watched_through("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine(), {})
    assert calls == [] and result


def test_without_it_the_run_s_own_entry_is_refused_as_no_door_call(monkeypatch):
    monkeypatch.setattr(aes_event.DoorStops, "entered_at", lambda self, _pc: self)
    with pytest.raises(AssertionError, match=f"reached the door's entry {addrs.AES_ROM_TAK_FLAG:#x} from .* not a door call"):
        aes_event._watched_through("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine(), {})


def test_the_outermost_entry_reached_inside_an_entered_entry_is_door_call_0():
    """ev_button waiting for a press nobody makes, entered at the entry: its own entry is no arrival, the ev_block it
    waits through is DOOR CALL 0 — the frame the ROM's ev_button hands it — and the run blocks inside that call:
    compared AT DSPTCH — the unwatched run's memory there (`rom_at_dsptch`)."""
    calls, at_dsptch, result = aes_event._watched_through("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine(), {})
    assert result is None and [call.routine for call in calls] == [addrs.AES_ROM_EV_BLOCK]
    the_rom_s = aes_event.rom_at_dsptch("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine())
    assert the_rom_s.switches == aes_event.BLOCKS and at_dsptch == the_rom_s.memory


def _interrupts_asked_for(monkeypatch):
    """Every `(ordinal, pc)` an interrupted derivation asks its interrupts at, kept as it asks."""
    asked, interrupt_at = [], aes_event._interrupt_at
    monkeypatch.setattr(aes_event, "_interrupt_at", lambda interrupts, ordinal, entry: (
        asked.append((ordinal, entry)), interrupt_at(interrupts, ordinal, entry))[1])
    return asked


A_PRESS_AT_THE_WAIT = {"at door call 0": lambda: {0: aes_event.press},
                       "by a schedule at ev_block": lambda: aes_event.Waits({0: aes_event.press}, at=addrs.AES_ROM_EV_BLOCK)}


@pytest.mark.parametrize("interrupts", A_PRESS_AT_THE_WAIT.values(), ids=A_PRESS_AT_THE_WAIT)
def test_a_run_entered_at_an_entry_takes_its_interrupt_at_door_call_0_not_at_its_own_entry(monkeypatch, interrupts):
    """ev_button entered at the entry, the button pressed AT ITS ev_block (door call 0): the interrupt is asked for
    and taken THERE, once — the run's own entry, its first stop, is no door call. (The press queues a fork the
    dispatcher's forker has yet to run, so the wait still blocks: the machine at its dsptch is what a leaf battery
    derives from it.) The replay lays the one delivery over the memory it was derived over."""
    asked = _interrupts_asked_for(monkeypatch)
    calls, delivered, memory, result = aes_event.rom_interrupted("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine(), interrupts())
    assert [call.routine for call in calls] == [addrs.AES_ROM_EV_BLOCK] and set(delivered) == {0} and result is None
    assert asked == [(0, addrs.AES_ROM_EV_BLOCK)], "asked at the arrival alone"
    _calls, undelivered, _result = aes_event._watched_through("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine(), {})
    assert aes_event.differing(memory, undelivered), "the press is in the memory the run blocks with"


def test_an_interrupt_asked_for_at_the_run_s_own_entry_is_delivered_twice(monkeypatch):
    """THE RED for a delivery asked for by "the run is between two calls" alone: asked wherever the run is between
    calls — its own entry among them — door call 0's press is taken at ev_button's entry AND at its ev_block, and the
    replay refuses the delivery over a memory it was not derived over."""
    monkeypatch.setattr(aes_event.DoorStops, "opens_a_call_at", lambda self, _pc: self.between_calls)
    asked = _interrupts_asked_for(monkeypatch)
    with pytest.raises(AssertionError, match="the delivery would erase it"):
        aes_event.rom_interrupted("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine(), {0: aes_event.press})
    assert asked[0] == (0, addrs.AES_ROM_EV_BUTTON)


def test_a_stop_opens_a_door_call_only_at_an_entry_outside_every_call_and_past_the_run_s_own():
    back, stack = min(aes_event.ROM_RETURNS), 0x100
    memory = bytearray(stack) + back.to_bytes(aes.LONG_BYTES, "big") + bytes(max(aes_event.FRAME_BYTES.values()))
    watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, entered_at=addrs.AES_ROM_EV_BUTTON)
    assert not watch.opens_a_call_at(addrs.AES_ROM_EV_BUTTON), "the run's own entry: entered, not called"
    watch.stopped(addrs.AES_ROM_EV_BUTTON, stack, memory)
    assert watch.opens_a_call_at(addrs.AES_ROM_EV_BLOCK) and watch.opens_a_call_at(addrs.AES_ROM_EV_BUTTON)
    assert not watch.opens_a_call_at(addrs.AES_ROM_DSPTCH), "the dispatcher outside a call ends the run: no arrival"
    watch.stopped(addrs.AES_ROM_EV_BLOCK, stack, memory)
    assert not watch.opens_a_call_at(addrs.AES_ROM_EV_BLOCK) and not watch.opens_a_call_at(back), "inside a call"
    marked = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS).marked_with(aes_event.Timeline((aes_event.GEMDOS_TRAP,)))
    assert not marked.opens_a_call_at(aes_event.GEMDOS_TRAP), "a marked trap's handler is an arrival, and no door call"
    marked.stopped(aes_event.GEMDOS_TRAP, stack, bytes(stack + aes_event.EXCEPTION_FRAME_PC) + back.to_bytes(aes.LONG_BYTES, "big"))
    assert not marked.opens_a_call_at(addrs.AES_ROM_EV_BLOCK), "...nor is anything inside the trap"


def test_a_replay_and_a_marked_run_entered_at_an_entry_make_no_door_call_of_it(monkeypatch):
    """`delivering` / `replayed` (the snapshot's sweeps, Tier 3's original of an interrupted row) and `_marked_run` (a
    session's slices and timeline) over a run ENTERED AT an entry: watched as `_watched_through` watches it — the
    entry no arrival, the entry inside it door call 0, its delivery laid there. RED: `delivering` told nothing of
    where its run starts is refused at the run's first instruction."""
    lock = bytes(make_image(aes_event._staged("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine())))
    _final, _writes, regs = aes_event.replayed(lock, addrs.AES_ROM_TAK_FLAG, {})
    assert regs["d0"] & aes.WORD_MASK == 1, "tak_flag over the free lock: taken"
    timeline = aes_event.Timeline()
    assert aes_event._marked_run(addrs.AES_ROM_TAK_FLAG, bytearray(lock), {}, timeline, None) == 0 and not timeline.arrivals
    wait = bytes(make_image(aes_event._staged("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine())))
    delivered = aes_event.deliveries("AES_ROM_EV_BUTTON", A_PRESS, aes_event.machine(), {0: aes_event.press})
    with pytest.raises(aes_event.Blocked, match="inside door call 0"):       # the wait's own end, past its one delivery
        aes_event.replayed(wait, addrs.AES_ROM_EV_BUTTON, delivered)
    with pytest.raises(AssertionError, match=f"reached the door's entry {addrs.AES_ROM_TAK_FLAG:#x} from .* not a door call"):
        aes_event.rom_bench.watched_original(bytearray(lock), addrs.AES_ROM_TAK_FLAG, aes_event.delivering({}))


A_POINT_ON_THE_DESK = (200, 120)


def test_an_interrupted_row_entered_at_an_entry_is_priced_on_both_shores():
    """...and THE BENCH's second differential of one: ev_button asked for the state the button is in, entered at the
    entry, the mouse MOVED at its ev_block (door call 0 — the wait returns all the same: the move is a fork queued).
    The ROM's original is watched by `delivering` told where the run starts, ours at the twin's first instruction;
    the one delivery is laid at the same arrival on both, and the row priced. (Refused before: "reached the door's
    entry … from 0x2 — not a door call", at the original's first instruction.)"""
    waits = _waits()
    arrival = waits.at("evnt_button for the button up, which is up", waits.EV_BUTTON)
    interrupts = {0: aes_event.move_to(*A_POINT_ON_THE_DESK)}
    delivered = aes_event.deliveries(arrival.name, arrival.arguments, arrival.machine, interrupts)
    assert set(delivered) == {0} and delivered[0][1], "the premise: the move is delivered at the wait, and writes"
    aes_event.bench_differential(arrival.name, arrival.arguments, arrival.machine, interrupts)


def test_an_entered_entry_that_reaches_the_dispatcher_itself_blocks_outside_any_door_call():
    """unsync handing the lock to its waiter, entered at the entry: it calls dsptch ITSELF — no door call made — and
    the run ends there, its memory the ROM's at dsptch (what the C, which runs on to the dispatcher's hook, is
    compared with). A run entered at a routine OUTSIDE the door's entries keeps the old rule: a dispatcher reached
    outside a door call is not watched for (wind_update's releasing call reaches it INSIDE its unsync)."""
    waited_on = _wm_update().waited_on()
    calls, memory, result = aes_event._watched_through("AES_ROM_UNSYNC", THE_LOCK, waited_on, {})
    the_rom_s = aes_event.rom_at_dsptch("AES_ROM_UNSYNC", THE_LOCK, waited_on)
    assert (calls, result) == ([], None) and memory == the_rom_s.memory and the_rom_s.switches == aes_event.YIELDS
    watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, entered_at=addrs.AES_ROM_WM_UPDATE)
    assert watch.first == frozenset(aes_event.ENTRIES) and not watch.entered_at_an_entry
    entered = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, entered_at=addrs.AES_ROM_UNSYNC)
    assert entered.first == frozenset(aes_event.ENTRIES) | {addrs.AES_ROM_DSPTCH}
    assert entered.stopped(addrs.AES_ROM_UNSYNC, 0, b"") == entered.first - {addrs.AES_ROM_UNSYNC}, "its first stop"
    unblocking = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, entered_at=addrs.AES_ROM_UNSYNC)
    assert unblocking.first == frozenset(aes_event.ENTRIES), "a watch that does not end at the dispatcher"
    marked = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, blocks=True, entered_at=addrs.AES_ROM_UNSYNC)
    marked.marked_with(aes_event.Timeline((aes_event.GEMDOS_TRAP,)))
    assert marked.first == entered.first | {aes_event.GEMDOS_TRAP}, "a marked run keeps the dispatcher among its stops"
    with pytest.raises(AssertionError, match="first stopped at .*: it was entered elsewhere"):
        unblocking.stopped(addrs.AES_ROM_EV_BLOCK, 0, b"")


def test_an_entered_entry_is_watched_again_once_a_door_call_has_returned():
    """The run's own entry is left out of the stops armed at ITS OWN STOP, no longer: after the first door call
    inside it has returned, the entry is a stop again — a call of it from inside its own routine would be a door
    call."""
    back, stack = min(aes_event.ROM_RETURNS), 0x100
    memory = bytearray(stack) + back.to_bytes(aes.LONG_BYTES, "big") + bytes(max(aes_event.FRAME_BYTES.values()))
    watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, entered_at=addrs.AES_ROM_EV_BUTTON)
    assert addrs.AES_ROM_EV_BUTTON not in watch.stopped(addrs.AES_ROM_EV_BUTTON, stack, memory) and watch.calls == 0
    assert watch.stopped(addrs.AES_ROM_EV_BLOCK, stack, memory) == frozenset({back}) and watch.calls == 1
    assert watch.stopped(back, stack, memory) == frozenset(aes_event.ENTRIES)


def test_rom_at_dsptch_refuses_a_run_that_returns():
    with pytest.raises(AssertionError, match="never reached"):
        aes_event.rom_at_dsptch("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine())


# ---- (b) THE SHADOW, keyed on how the ROM routine's nested run ENDS ---------------------------------------------------------
def _shadow(name, arguments, machine):
    """The shadow of a call of the entry `name` arriving over `machine` — and the image it arrives with."""
    image, frame = bytes(make_image(machine)), aes_event.entry_frame(name, *arguments)
    return aes_event.shadow_of(aes_event.handed(getattr(addrs, name), frame, image), image, frame), image


SWITCHING_CALLS = {
    "ev_multi for a key nobody typed: it blocks": ("AES_ROM_EV_MULTI", aes_event.EV_MULTI_FRAME.unpack(aes_event.KEY_WAIT),
                                                   aes_event.machine, aes_event.BLOCKS),
    "unsync with a waiter queued: it yields": ("AES_ROM_UNSYNC", THE_LOCK, lambda: _wm_update().waited_on(), aes_event.YIELDS),
}


@pytest.mark.parametrize("name, arguments, machine, switches", SWITCHING_CALLS.values(), ids=SWITCHING_CALLS)
def test_the_shadow_of_a_call_that_switches_is_the_rom_s_image_at_dsptch(name, arguments, machine, switches):
    """RED (G3's probe, C2): the shadow of a call that reaches the dispatcher was REFUSED at the arrival — its twin
    never ran. Now it is the nested run AS FAR AS DSPTCH: the kind of switch, and the image there — which a twin
    holding the ROM's own image at dsptch satisfies, at the dispatcher's hook; a twin that wrote nothing before it (the
    image it arrived with), one whose process is in the other state, and one that RETURNED are each refused by name."""
    shadow, arrived_with = _shadow(name, arguments, machine())
    assert shadow.nested.switched == switches
    at_dsptch = _less_the_staged_frame(aes_event.rom_at_dsptch(name, arguments, machine()).memory, arrived_with, name)
    aes_event.vet_the_shadow_at_dsptch(shadow, at_dsptch)
    aes_event._vet_the_twin_at_the_dispatcher([shadow], at_dsptch)
    with pytest.raises(AssertionError, match="holds at the dispatcher another image than the ROM's routine"):
        aes_event.vet_the_shadow_at_dsptch(shadow, arrived_with if switches == aes_event.YIELDS else _one_byte_off(at_dsptch))
    with pytest.raises(AssertionError, match="returned where the ROM's routine.*reaches the dispatcher"):
        aes_event.vet_the_shadow(shadow, at_dsptch, 0)
    other = bytearray(at_dsptch)
    running = case.long_in(other, aes.AES_RLR)
    other[running + aes.PD_STAT + 1] ^= aes.PD_STAT_WAITING ^ aes.PD_STAT_READY
    with pytest.raises(AssertionError, match="at the dispatcher the twin of .* has its process where"):
        aes_event.vet_the_shadow_at_dsptch(shadow, bytes(other))


def _less_the_staged_frame(memory, arrived_with, name):
    """`memory` — a run of the entry `name` entered directly, its frame staged at `abi.FIRST_ARG` — as a TWIN's image
    would be: no frame staged (a twin's arguments are C's), those bytes the ones the call arrived with."""
    frame = slice(aes_event.abi.FIRST_ARG, aes_event.abi.FIRST_ARG + aes_event.ENTRY_FRAMES[name].frame.size)
    twin_s = bytearray(memory)
    twin_s[frame] = arrived_with[frame]
    return bytes(twin_s)


def _one_byte_off(image, at=aes_event.MESSAGE_AT):
    """`image` with one compared byte another's."""
    changed = bytearray(image)
    changed[at] ^= BYTE_MASK
    return bytes(changed)


def test_a_twin_at_the_dispatcher_whose_rom_routine_returns_is_refused_by_name():
    """...and the other way round: tak_flag's ROM routine RETURNS — a twin of it that reached the dispatcher's hook is
    refused there. A twin whose arrival has no shadow (its nested run was refused) too; outside any twin, and at an
    entry no shadow is made for, the hook holds the image to nothing here."""
    shadow, arrived_with = _shadow("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine())
    assert shadow.nested.switched is None
    with pytest.raises(AssertionError, match="reached the dispatcher where the ROM's routine.*returns"):
        aes_event._vet_the_twin_at_the_dispatcher([shadow], arrived_with)
    with pytest.raises(AssertionError, match="its arrival has no shadow"):
        aes_event._vet_the_twin_at_the_dispatcher([aes_event.SHADOW_NOT_MADE], arrived_with)
    aes_event._vet_the_twin_at_the_dispatcher([], arrived_with)
    aes_event._vet_the_twin_at_the_dispatcher([aes_event.NOT_SHADOWED], arrived_with)


def test_the_shadowed_entries_are_derived_every_rebound_one_of_the_library_a_binding_serves(monkeypatch):
    """No list to edit at a flip — and no set frozen at this module's import: a CHILD's library may carry other
    markers than the worker's (a private build, a mutant's), and its binding shadows ITS rebound entries. (Found by
    rehearsing unsync's flip on a private library: read off the worker's REBOUND, the child made no shadow for it.)"""
    assert aes_event.SHADOWED is aes_event.EVERY_REBOUND_ENTRY
    assert aes_event.shadowed_among(aes_event.REBOUND) == aes_event.REBOUND
    another_library_s = frozenset({addrs.AES_ROM_UNSYNC})
    assert aes_event.shadowed_among(another_library_s) == another_library_s
    made, shadows = [], []
    monkeypatch.setattr(aes_event, "shadow_of", lambda call, *_arrival: made.append(call.routine) or "a shadow")
    aes_event._arrived(addrs.AES_ROM_TAK_FLAG, None, lambda _call: None, shadows, another_library_s)(*_a_call_arriving())
    assert (made, shadows) == ([], [aes_event.NOT_SHADOWED]), "tak_flag is not rebound in that library"
    del shadows[:]
    aes_event._arrived(addrs.AES_ROM_TAK_FLAG, None, lambda _call: None, shadows)(*_a_call_arriving())
    assert made == [addrs.AES_ROM_TAK_FLAG], "...and is in the worker's"
    monkeypatch.setattr(aes_event, "SHADOWED", frozenset())
    assert aes_event.shadowed_among(aes_event.REBOUND) == frozenset(), "a case narrows it"


SHADOW_PLANTED = "the shadow: planted by the case"
A_SHADOW_THAT_REFUSES = ("aes_event._vet_the_twin_at_the_dispatcher = lambda shadows, image: "
                         f"(_ for _ in ()).throw(AssertionError({SHADOW_PLANTED!r})); ")


def test_a_twin_its_shadow_refuses_at_the_dispatcher_ends_the_child_by_the_shadow_s_words():
    """THE COMPOSED PATH's last link, in a child (where every call that switches runs): the dispatcher's hook asks the
    shadow BEFORE it refuses, and a shadow's refusal ENDS the child with its own status and words — never the
    dispatcher's "would block", which a case comparing a blocked call would take for the ROM's own outcome. (The whole
    path — unsync rebound on a private library, its twin mutated — is F1's `red/flip_unsync.py`; the twin that
    returned where the ROM yields passed `refused_where_the_rom_blocks` there until `interrupted` held the status.)"""
    pokes = aes_event.as_pokes(AT_DSPTCH["a wait nothing satisfies: it would block"][0]())
    returncode, stderr, _left = vdi_helpers.refusal_over(DSPTCH_ENTERED, pokes,
                                                         bind=aes_event.child_binding(before=A_SHADOW_THAT_REFUSES))
    assert returncode == aes_event.CHILD_SHADOW_REFUSED and SHADOW_PLANTED in stderr, (returncode, stderr)
    assert aes_event.BLOCKS not in stderr and aes_event.HALTED_AT_THE_DISPATCHER not in stderr


def test_interrupted_takes_no_shadow_s_refusal_for_the_switch_it_waits_for(monkeypatch):
    """...and `interrupted` — every blocked door case's comparison — fails by the shadow's refusal whatever the ROM's
    run did: the refusal of a twin that RETURNED where the ROM's routine yields names the yield, and its image may be
    the ROM's at dsptch byte for byte."""
    monkeypatch.setattr(aes_event, "refusal", lambda *_run, **_named: (
        aes_event.CHILD_SHADOW_REFUSED, f"the shadow: the twin returned where the ROM's routine reaches the dispatcher — "
                                        f"{aes_event.YIELDS}\n{aes_event.HANDED_LINE}[]", b""))
    wm_update = _wm_update()
    with pytest.raises(AssertionError, match="a rebound entry's twin is not its shadow"):
        aes_event.refused_where_the_rom_blocks(wm_update.WM_UPDATE, (wm_update.END_UPDATE,), wm_update.waited_on(),
                                               switches=aes_event.YIELDS)


WORKER_KNOWS_NO_REBOUND_ENTRY = ("aes_event.REBOUND = frozenset(); shadow_of = aes_event.shadow_of; "
                                 "aes_event.shadow_of = lambda call, *arrival: "
                                 "(print('a shadow was made for', hex(call.routine), file=sys.stderr), shadow_of(call, *arrival))[1]; ")


def test_a_child_shadows_the_rebound_entries_of_the_library_it_calls():
    """In a child the shadowed entries are read off THE LIBRARY IT BINDS, as its answers are — not off the set this
    module derived at its import for the library `harness` loads (emptied here, in the child: the lock's tak_flag is
    shadowed all the same, and the call returns through its shadow)."""
    bind = aes_event.child_binding(before=WORKER_KNOWS_NO_REBOUND_ENTRY)
    returncode, stderr, _image = aes_event.refusal(_lock_taken()[0], aes_event.machine(), _lock_taken()[1], bind=bind)
    assert returncode == 0 and f"a shadow was made for {addrs.AES_ROM_TAK_FLAG:#x}" in stderr, (returncode, stderr)


# ---- A CALL THAT SWITCHES, at the event layer's own level (`switches_where_the_rom_does`) ---------------------------------
def _waits():
    """The waits' helper module (`aes_evlib`: unsync's signature and its states), imported where a case uses it."""
    return importlib.import_module("aes_evlib")


def _unsync_yielding(**named):
    waits = _waits()
    return aes_event.switches_where_the_rom_does(waits.UNSYNC, THE_LOCK, _wm_update().waited_on(),
                                                 switches=aes_event.YIELDS, **named)


def test_a_core_that_switches_is_held_to_the_rom_at_dsptch():
    """unsync's C handing the lock to its waiter: halted at the dispatcher's hook as a call that YIELDS, its image
    there the ROM's own run's at dsptch — the lock the screen manager's, its EVB completed — everywhere compared."""
    switched = _unsync_yielding()
    wm_update = _wm_update()
    assert wm_update.spb_of(switched.image) == (1, aes.SCREEN_MANAGER_PD) == wm_update.spb_of(switched.rom_memory)
    assert aes_event.YIELDS in switched.stderr and aes_event.HALTED_AT_THE_DISPATCHER in switched.stderr


def test_a_switch_of_the_other_kind_is_refused_by_the_premise():
    with pytest.raises(AssertionError, match="the premise — at dsptch the ROM's run is one where the call would block"):
        _waits() and aes_event.switches_where_the_rom_does(_waits().UNSYNC, THE_LOCK, _wm_update().waited_on())


def test_a_core_whose_image_at_the_dispatcher_is_not_the_rom_s_is_red(monkeypatch):
    """RED: the ROM's memory at dsptch one compared byte another's — the C's image differs, by name and address."""
    rom_at_dsptch = aes_event.rom_at_dsptch

    def another(*run, **named):
        the_rom_s = rom_at_dsptch(*run, **named)
        return the_rom_s._replace(memory=_one_byte_off(the_rom_s.memory))
    monkeypatch.setattr(aes_event, "rom_at_dsptch", another)
    with pytest.raises(AssertionError, match=f"at dsptch, .*1 bytes differ.*{aes_event.MESSAGE_AT:#x}"):
        _unsync_yielding()


def test_a_core_that_returns_where_the_rom_switches_is_red(monkeypatch):
    """RED: the ROM's run reaches dsptch; a C that came back — tak_flag's, standing in for unsync's — is refused by
    its fork's own end, never compared as if it had halted there."""
    waits = _waits()
    the_rom_s = aes_event.rom_at_dsptch(waits.UNSYNC, THE_LOCK, _wm_update().waited_on())
    monkeypatch.setattr(aes_event, "rom_at_dsptch", lambda *_run, **_named: the_rom_s)
    with pytest.raises(AssertionError, match="the C's fork ended 0"):
        aes_event.switches_where_the_rom_does(TAK_FLAG, THE_LOCK, _wm_update().waited_on(), switches=aes_event.YIELDS)


def test_a_core_that_halts_elsewhere_than_at_the_dispatcher_is_red(monkeypatch):
    """RED: the ROM's run reaches dsptch; a C that HALTED — but by another refusal than the dispatcher's hook (an odd
    semaphore: the host's address error) — is not taken for one that reached it."""
    waits = _waits()
    the_rom_s = aes_event.rom_at_dsptch(waits.UNSYNC, THE_LOCK, _wm_update().waited_on())
    monkeypatch.setattr(aes_event, "rom_at_dsptch", lambda *_run, **_named: the_rom_s)
    with pytest.raises(AssertionError, match="did not halt at the dispatcher's hook"):
        aes_event.switches_where_the_rom_does(*_an_odd_semaphore(), switches=aes_event.YIELDS)


def test_a_drop_at_dsptch_names_only_what_the_rom_s_run_stored(monkeypatch):
    """`dropped=`: a case's difference by nature (a pointer into its caller's stack, parked in a record) — the bytes
    the ROM's run WROTE. Over the lock's own count, which it stored, the case still holds; over a byte it never
    touched, refused by name."""
    count = (WU["AES_WIND_SPB"], WU["AES_WIND_SPB"] + aes.WORD_BYTES, "the count, for the test")
    _unsync_yielding(dropped=(count,))
    with pytest.raises(AssertionError, match=f"dropped at dsptch, and not stored by the ROM's run: .'{aes_event.UNREAD_BYTE:#x}'"):
        _unsync_yielding(dropped=((aes_event.UNREAD_BYTE, aes_event.UNREAD_BYTE + 1, "a byte no run stores"),))
    rom_at_dsptch = aes_event.rom_at_dsptch

    def another_count(*run, **named):
        the_rom_s = rom_at_dsptch(*run, **named)
        return the_rom_s._replace(memory=_one_byte_off(the_rom_s.memory, at=WU["AES_WIND_SPB"]))
    monkeypatch.setattr(aes_event, "rom_at_dsptch", another_count)
    _unsync_yielding(dropped=(count,))                 # ...and what is dropped IS left out: a count that differs
    with pytest.raises(AssertionError, match="at dsptch, .*1 bytes differ"):
        _unsync_yielding()


# ---- A PARKED PIPE WAIT'S QPB ADDRESS: dropped by name, vetted (`aes_event.parked_qpb_drop`) ---------------------------------
def _a_write_parked_on_a_full_pipe():
    """ap_rdwr's write to a full pipe, entered at the entry (the waits' own case): `(arguments, Switched)` — the C's
    image at the dispatcher's hook and the ROM's memory at dsptch, the wait parked on the pipe's writers on both."""
    waits = _waits()
    arrival = waits.at("appl_write to a full pipe", waits.AP_RDWR)
    return arrival, waits.run(arrival)


def _with_long(image, at, value):
    changed = bytearray(image)
    changed[at:at + aes.LONG_BYTES] = value.to_bytes(aes.LONG_BYTES, "big")
    return bytes(changed)


def test_a_parked_pipe_wait_s_qpb_address_is_dropped_by_name_and_vetted():
    """THE ONE LONGWORD a wait parked on a pipe differs in on its two shores: its EVB's parameter, the address of its
    QPB — a place in the ROM routine's frame, the twin's own slot. The drop is exactly those four bytes, and ONLY
    where the same EVB names, on each shore, the same QPB in that shore's stack band; each way it could hide a real
    difference is refused by name."""
    arrival, parked = _a_write_parked_on_a_full_pipe()
    ours, the_rom_s = parked.image, parked.rom_memory
    (its,), (mine,) = aes_event.parked_qpbs(the_rom_s), aes_event.parked_qpbs(ours)
    parm = its.evb + aes.EVB_PARM
    assert mine.evb == its.evb and mine.qpb_at != its.qpb_at
    drop = aes_event.parked_qpb_drop("the case", ours, the_rom_s)
    assert drop == frozenset(range(parm, parm + aes.LONG_BYTES))
    differ = set(aes_event.differing(ours, the_rom_s))
    assert differ and differ <= drop, "the premise: the two images differ there, and nowhere else compared"
    assert its.qpb_at == aes_event.abi.FIRST_ARG + aes.WORD_BYTES, "entered at the entry: the frame past its code word"
    assert parked.parked == (arrival.arguments[1:],), "...and it is the QPB the call was handed, found for the case"
    one_byte_fewer = bytearray(ours)
    one_byte_fewer[mine.qpb_at + aes.WORD_BYTES + 1] ^= 1       # our QPB's count: inside the stack band, compared nowhere else
    with pytest.raises(AssertionError, match="the QPB the parked wait names .* is not the ROM's"):
        aes_event.parked_qpb_drop("the case", bytes(one_byte_fewer), the_rom_s)
    # OUR parameter outside every stack: no wait of ours parked a QPB in one — another list of EVBs than the ROM's.
    with pytest.raises(AssertionError, match=r"the pipe waits parked with a QPB in a stack are the EVBs \[\], the ROM's"):
        aes_event.parked_qpb_drop("the case", _with_long(ours, parm, aes_event.MESSAGE_AT), the_rom_s)
    with pytest.raises(AssertionError, match=r"are the EVBs \['0x[0-9a-f]+'\], the ROM's \[\]"):
        aes_event.parked_qpb_drop("the case", ours, _with_long(the_rom_s, parm, aes_event.MESSAGE_AT))
    at_the_band_s_end = case.STACK_BAND.stop - aes.WORD_BYTES   # a parameter whose QPB would run out of the band
    with pytest.raises(AssertionError, match="no place in the stack band — not a QPB's address parked"):
        aes_event.parked_qpb_drop("the case", _with_long(ours, parm, at_the_band_s_end), the_rom_s)
    with pytest.raises(AssertionError, match=r"the case \(the ROM's run\): .* no place in the stack band"):
        aes_event.parked_qpb_drop("the case", ours, _with_long(the_rom_s, parm, at_the_band_s_end))
    running = case.long_in(ours, aes.AES_RLR)
    with pytest.raises(AssertionError, match="the pipe waits parked with a QPB in a stack are the EVBs"):
        aes_event.parked_qpb_drop("the case", _with_long(ours, running + aes.PD_EVLIST, 0), the_rom_s)


def test_our_parked_qpb_s_place_is_its_slot_not_any_address_holding_the_right_bytes():
    """RED before the vet asked WHERE (two mutants of ev_multi's twin held under the shadow and the door's rule: the
    QPB built in ANOTHER process's frame, and in ap_rdwr's role — the address differed, the eight bytes did not):
    ap_rdwr's parked write, its QPB moved — bytes and all — to the slot of another process, and to ev_multi's role,
    is refused by name each way; told the entry, the role is the entry's own."""
    arrival, parked = _a_write_parked_on_a_full_pipe()
    ours, the_rom_s = parked.image, parked.rom_memory
    (mine,) = aes_event.parked_qpbs(ours)
    process = case.word_in(ours, case.long_in(ours, aes.AES_RLR) + aes.PD_PID)
    assert mine.qpb_at == aes_event.host_qpb_slot("HOST_SLOT_AES_AP_RDWR_QPB", process)
    assert aes_event.our_qpb_slots(ours, addrs.AES_ROM_AP_RDWR) == {mine.qpb_at}
    assert len(aes_event.our_qpb_slots(ours)) == len(aes_event.QPB_SLOT_OF_AN_ENTRY) and mine.qpb_at in aes_event.our_qpb_slots(ours)

    def moved_to(slot):
        elsewhere = bytearray(ours)
        elsewhere[slot:slot + aes_event.QPB.size] = ours[mine.qpb_at:mine.qpb_at + aes_event.QPB.size]
        return _with_long(elsewhere, mine.evb + aes.EVB_PARM, slot)
    another_process_s = moved_to(aes_event.host_qpb_slot("HOST_SLOT_AES_AP_RDWR_QPB", process ^ 1))
    with pytest.raises(AssertionError, match="is no QPB slot of the running process"):
        aes_event.parked_qpb_drop("the case", another_process_s, the_rom_s)
    another_routine_s = moved_to(aes_event.host_qpb_slot("HOST_SLOT_AES_EV_MULTI_QPB", process))
    assert aes_event.parked_qpb_drop("the case", another_routine_s, the_rom_s), "untold the entry: any role's slot of the process"
    with pytest.raises(AssertionError, match=f"no QPB slot of the running process under {addrs.AES_ROM_AP_RDWR:#x}'s role"):
        aes_event.parked_qpb_drop("the case", another_routine_s, the_rom_s, routine=addrs.AES_ROM_AP_RDWR)
    assert aes_event.parked_qpb_drop("the case", ours, the_rom_s, routine=addrs.AES_ROM_AP_RDWR)
    # ...and the same of an address LEFT IN A FREED EVB at a return (`vetted_qpb_addresses`): a slot of the running
    # process's, whichever routine's — never another process's.
    parm = mine.evb + aes.EVB_PARM
    kept = {parm: aes_event.QPB.unpack_from(ours, mine.qpb_at)}
    assert aes_event.vetted_qpb_addresses("the case", ours, kept) == ((parm, parm + aes.LONG_BYTES, aes_event.QPB_ADDRESS_WHY),)
    assert aes_event.vetted_qpb_addresses("the case", another_routine_s, kept), "untold the entry: any role's slot"
    assert aes_event.vetted_qpb_addresses("the case", ours, kept, addrs.AES_ROM_AP_RDWR)
    with pytest.raises(AssertionError, match=f"no QPB slot of the running process under {addrs.AES_ROM_AP_RDWR:#x}'s role"):
        aes_event.vetted_qpb_addresses("the case", another_routine_s, kept, addrs.AES_ROM_AP_RDWR)
    with pytest.raises(AssertionError, match="is no QPB slot of the running process"):
        aes_event.vetted_qpb_addresses("the case", another_process_s, kept)


def test_a_wait_the_machine_came_with_is_one_address_and_its_qpb_s_bytes_are_no_part_of_a_staged_machine():
    """THE EQUAL-ADDRESS ARM, and why it holds no bytes (MEASURED: it cannot vet them): a
    wait both shores were staged with names ONE address — nothing dropped, the longword compared — and that address
    is in the frame of the routine that parked it, which a staged machine does not carry (no stack band). Shown on
    the waits' own case: ev_mwait entered under ev_mesag's parked wait — the ROM's memory holds eight bytes there,
    the C's image none of them, and the case is held all the same; a vet of those bytes would refuse it."""
    waits = _waits()
    arrival = waits.at("evnt_mesag, none", waits.MWAIT)
    parked = waits.run(arrival)
    (its,), (mine,) = aes_event.parked_qpbs(parked.rom_memory), aes_event.parked_qpbs(parked.image)
    assert its == mine and its.qpb_at in case.STACK_BAND, "one address, on both shores"
    assert aes_event.parked_qpb_drop("the case", parked.image, parked.rom_memory) == frozenset()
    assert parked.image[its.qpb_at:its.qpb_at + aes_event.QPB.size] != parked.rom_memory[its.qpb_at:its.qpb_at + aes_event.QPB.size], (
        "the premise: the stack band is no part of the machine the C was staged with")


def test_a_wait_queued_on_no_pipe_parks_no_qpb_whatever_its_parameter_holds():
    """`parked_qpbs` reads the PIPES' wait lists: an EVB of the running process whose parameter is a stack address
    but which is on NO pipe's end (a timer's count, a rectangle's — a parameter is whatever its wait kind makes of
    it) is no parked QPB. Shown by ap_rdwr's parked write taken off the pipe's writers."""
    _arrival, parked = _a_write_parked_on_a_full_pipe()
    (its,) = aes_event.parked_qpbs(parked.rom_memory)
    off_every_pipe = bytearray(parked.rom_memory)
    for process in range(aes.AES_PD_COUNT):
        for which in (aes.PD_QUEUE_READERS, aes.PD_QUEUE_WRITERS):
            at = aes.AES_PD_TABLE + process * aes.PD_BYTES + which
            off_every_pipe[at:at + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    running = case.long_in(off_every_pipe, aes.AES_RLR)
    assert its.evb in aes_event._evbs_linked_from(off_every_pipe, running + aes.PD_EVLIST, aes.EVB_NEXT), "still the process's wait"
    assert aes_event.parked_qpbs(off_every_pipe) == ()


def test_a_list_of_evbs_that_does_not_end_is_refused_by_name():
    """...and the walk of a list is bounded by the EVBs there are: one linked back to itself is refused, never walked
    for ever (nor cut short without a word)."""
    head_at, evb = aes_event.BAND_AT, aes.AES_EVB_TABLE
    cyclic = bytearray(make_image({head_at: struct.pack(">I", evb)}))
    cyclic[evb + aes.EVB_LINK:evb + aes.EVB_LINK + aes.LONG_BYTES] = struct.pack(">I", evb)
    with pytest.raises(AssertionError, match=f"the list of EVBs at {head_at:#x} does not end"):
        aes_event._evbs_linked_from(cyclic, head_at, aes.EVB_LINK)
    ended = bytearray(cyclic)
    ended[evb + aes.EVB_LINK:evb + aes.EVB_LINK + aes.LONG_BYTES] = bytes(aes.LONG_BYTES)
    assert aes_event._evbs_linked_from(ended, head_at, aes.EVB_LINK) == [evb]


def test_a_qpb_outside_every_stack_is_one_address_on_both_shores_and_nothing_is_dropped():
    """A wait parked with a QPB its case staged OUTSIDE the stack band (ev_block handed the pipes' band's): no
    difference by nature — the same address on both shores — so nothing is found, nothing dropped, and a C that
    kept another address there differs."""
    waits = _waits()
    arrival = waits.at("appl_read, none", waits.EV_BLOCK)
    assert arrival.arguments[1] == waits.QPB_AT and waits.QPB_AT not in case.STACK_BAND
    parked = waits.run(arrival)
    assert parked.parked == () and aes_event.parked_qpbs(parked.rom_memory) == ()
    assert aes_event.parked_qpb_drop("the case", parked.image, parked.rom_memory) == frozenset()


def test_what_a_blocked_call_parks_is_its_entry_s_row_s_and_a_door_user_s_drop_is_a_rebound_call_s():
    """WHAT a blocked call must be found to have parked is its ENTRY's ROW's to say (`Entry.parks`), no routine
    named where it is vetted: ap_rdwr's own arguments with a pipe's code (not its other waits: the same address
    handed on, kept by no routine), the QPB ev_block's parameter names, ev_multi's own for a MESSAGE. For a door
    USER's blocked run (compared at dsptch) the drop is its last call's — and the QPB parked is the one the row
    says."""
    arrival, parked = _a_write_parked_on_a_full_pipe()
    write, process, count, buffer = arrival.arguments
    a_send = aes_event.Handed(addrs.AES_ROM_AP_RDWR, (write, process, count, b"a message's bytes"))
    ours, the_rom_s = parked.image, parked.rom_memory
    assert write == aes_event.EVWAIT["IASYNC_WRITE"] and aes_event.parked_by(a_send, ours) == (process, count)
    a_read = a_send._replace(arguments=(aes_event.EVWAIT["IASYNC_READ"], process, count, True))
    assert aes_event.parked_by(a_read, ours) == (process, count)
    assert aes_event.parked_by(a_send._replace(arguments=(aes_event.EVWAIT["IASYNC_MUTEX"], process, count, True)), ours) is None
    assert aes_event.parked_by(aes_event.Handed(addrs.AES_ROM_EV_BLOCK, (write, (process, count, b""))), ours) == (process, count)
    assert aes_event.parked_by(aes_event.Handed(addrs.AES_ROM_EV_BLOCK, (aes_event.EVWAIT["IASYNC_MUTEX"], 0)), ours) is None
    assert aes_event.parked_by(aes_event.Handed(addrs.AES_ROM_TAK_FLAG, (b"",)), ours) is None
    running_pid = aes.signed(case.word_in(ours, case.long_in(ours, aes.AES_RLR) + aes.PD_PID))
    for_a_message = aes_event.Handed(addrs.AES_ROM_EV_MULTI, (aes.EV_MU_MESAG | aes.EV_MU_KEYBD, None, None, 0, 0, True, True))
    assert aes_event.parked_by(for_a_message, ours) == (running_pid, aes_event.MESSAGE_BYTES)
    assert aes_event.parked_by(for_a_message._replace(arguments=(aes.EV_MU_KEYBD, None, None, 0, 0, True, True)), ours) is None
    drop = aes_event.parked_qpb_drop("the case", ours, the_rom_s)
    assert aes_event._a_door_user_s_parked_qpb("a user", [a_send], ours, the_rom_s) == drop
    assert aes_event._a_door_user_s_parked_qpb("a user", [], ours, the_rom_s) == frozenset()
    with pytest.raises(AssertionError, match=r"parked the QPBs \[\(.*\)\] \(process, bytes\) — it was handed .* which parks"):
        aes_event._a_door_user_s_parked_qpb("a user", [a_send._replace(arguments=(write, process, count + 1, b""))],
                                            ours, the_rom_s)
    # ...and a rebound call that queues NO pipe wait, blocked over a machine where one is parked all the same: by name.
    a_lock = aes_event.Handed(addrs.AES_ROM_TAK_FLAG, (b"",))
    with pytest.raises(AssertionError, match=r"it was handed .* which parks None"):
        aes_event._a_door_user_s_parked_qpb("a user", [a_send, a_lock], ours, the_rom_s)


def test_interrupted_leaves_out_what_a_blocked_call_differs_in_by_nature_and_nothing_of_a_run_that_returned(monkeypatch):
    """WHERE `interrupted` applies it: to a run that did NOT return (the C stopped at a twin's dispatcher hook) — never
    to one that returned, where nothing is parked. Shown with a byte nothing reads taken for the difference by nature
    and written by the C's child: left out of the blocked case's compare, red in the returned one's."""
    monkeypatch.setattr(aes_event, "_a_door_user_s_parked_qpb", lambda *_case: frozenset({UNREAD_BYTE}))

    def wrote_the_byte(image):
        image[UNREAD_BYTE] ^= BYTE_MASK
        return image
    _the_c_s_child_leaving(monkeypatch, wrote_the_byte)
    aes_event.refused_where_the_rom_blocks(*WOULD_BLOCK, grwait.button_down())
    with pytest.raises(AssertionError, match=f"1 bytes differ from the ROM's run: {UNREAD_BYTE:#x}"):
        aes_event.interrupted(*_rubber_box_released_as_the_lock_is_taken(), second_differential=False)


def test_the_shadow_of_a_parked_ap_rdwr_is_held_at_dsptch_but_for_the_qpb_s_address(monkeypatch):
    """THE SHADOW's side (what a REBOUND ap_rdwr meets where ap_sendmsg's pipe is full): the twin's image at
    the dispatcher's hook is the ROM routine's at dsptch but for that longword — the nested run's QPB is its frame at
    `abi.FIRST_ARG`, past the code word, read through that run's own memory. RED without the named drop: "another
    image", on that longword's bytes; and a twin whose QPB holds another count is refused by the vet, though its QPB
    lies wholly in the stack band, where no compare looks."""
    arrival, parked = _a_write_parked_on_a_full_pipe()
    shadow, _arrived_with = _shadow(arrival.name, arrival.arguments, arrival.machine)
    assert shadow.nested.switched == aes_event.BLOCKS and aes_event.parked_by(shadow.call, parked.image)
    aes_event.vet_the_shadow_at_dsptch(shadow, parked.image)
    parm = aes_event.parked_qpbs(parked.image)[0].evb + aes.EVB_PARM
    another_count = bytearray(parked.image)
    another_count[case.long_in(parked.image, parm) + aes.WORD_BYTES + 1] ^= 1
    with pytest.raises(AssertionError, match=f"the shadow of {addrs.AES_ROM_AP_RDWR:#x}: the QPB the parked wait names"):
        aes_event.vet_the_shadow_at_dsptch(shadow, bytes(another_count))
    monkeypatch.setattr(aes_event, "_a_shadow_s_parked_qpb", aes_event._nothing_by_nature)
    with pytest.raises(AssertionError, match=f"holds at the dispatcher another image.* bytes differ.*{parm + 1:#x}"):
        aes_event.vet_the_shadow_at_dsptch(shadow, parked.image)        # the longword's bytes that differ, and no other


# ---- ...and ev_multi's: the QPB of a MESSAGE wait is a local of ITS OWN frame ($fe6b40..$fe6b52) ---------------------------
# What a twin of ev_multi leaves at the dispatcher's hook is shown WITHOUT one (the mechanism is the door's, whatever
# twin is linked): the ROM's own memory at dsptch, AS A TWIN PARKS IT — no frame staged (a twin's arguments are C's),
# the QPB's eight bytes where a C twin keeps its own (the per-process host slot, `host_slot.h`) and the wait's
# parameter aimed there. An ARGUMENT-CLASS image, labelled: every byte but that address and the QPB's place is the
# ROM run's own.
EV_MULTI_QPB_BELOW_THE_FRAME = 16       # ev_multi's `-8(a6)`: A6 is the entry SP less 4, the first argument that SP plus 4
MESSAGE_WAITS = {
    "a message alone": aes.EV_MU_MESAG,
    "a message and a key": aes.EV_MU_MESAG | aes.EV_MU_KEYBD,
    "a message and a timer (the timer's wait is queued AFTER the message's)": aes.EV_MU_MESAG | aes.EV_MU_TIMER,
    "a message and a rectangle": aes.EV_MU_MESAG | aes.EV_MU_M1,
}
# EVERY event asked at once is the deepest nested run there is — 2,970 instructions to dsptch, every wait queued before
# the call gives up: what `aes_event.NESTED_RUN_INSNS` is derived from
# (`test_the_cap_is_derived_from_the_deepest_block_a_shadow_runs`).
DEEPEST_BLOCKED = (aes.EV_MU_KEYBD | aes.EV_MU_BUTTON | aes.EV_MU_M1 | aes.EV_MU_M2 | aes.EV_MU_MESAG | aes.EV_MU_TIMER)
DEEPEST_BLOCKED_INSNS = 2_970
CAP_THE_ANSWERED_CALLS_JUSTIFIED = 40_000   # the cap before a blocked shadow was measured: 20 times mn_do's 1,697, rounded
MESSAGE_WAITS["every event at once (the deepest block)"] = DEEPEST_BLOCKED
A_SECOND_MS = 1000


def _ev_multi_waiting_for_a_message(flags):
    """`(arguments, machine)` of an evnt_multi that asks for `flags` — a message among them — over a machine where
    none of it has come: the desk running, its pipe empty, a double click awaited and two rectangles the mouse is
    where neither asks."""
    frame, pokes = aes_evasync.ev_multi_frame(
        flags, first=aes_evasync.moblk(aes_evasync.LEAVE, *aes_evasync.ROUND_THE_MOUSE),
        second=aes_evasync.moblk(aes_evasync.ENTER, *aes_evasync.ELSEWHERE), timer=A_SECOND_MS,
        button=aes_evasync.button_wait(aes_evasync.DOUBLE))
    return aes_event.EV_MULTI_FRAME.unpack(frame), merge_pokes(aes_event.machine(), pokes)


def _as_a_twin_parks_it(the_rom_s, arrived_with):
    """The ROM's memory at dsptch (ev_multi entered at the entry) as a C twin would hold it (above)."""
    (its,) = aes_event.parked_qpbs(the_rom_s)
    pid = case.word_in(the_rom_s, case.long_in(the_rom_s, aes.AES_RLR) + aes.PD_PID)
    slots = aes.HOST_SLOTS
    our_qpb_at = slots["HOST_SLOT_AES_EV_MULTI_QPB"] + pid * (slots["HOST_SLOT_AES_EV_MULTI_QPB_BYTES"] // slots["HOST_PROCESSES"])
    twin_s = bytearray(_less_the_staged_frame(the_rom_s, arrived_with, "AES_ROM_EV_MULTI"))
    twin_s[our_qpb_at:our_qpb_at + aes_event.QPB.size] = the_rom_s[its.qpb_at:its.qpb_at + aes_event.QPB.size]
    return _with_long(twin_s, its.evb + aes.EVB_PARM, our_qpb_at), its


@pytest.mark.parametrize("flags", MESSAGE_WAITS.values(), ids=MESSAGE_WAITS)
def test_a_blocked_ev_multi_s_message_wait_parks_a_qpb_of_its_own_frame_and_its_shadow_holds(flags, monkeypatch):
    """RED before the rule read the machine: who parks a QPB was `call.routine == ap_rdwr`, the ROM's QPB "the frame
    past its code word", the EVB "the newest" — so the shadow of a blocked ev_multi(MU_MESAG) was refused on the EVB's
    parameter (`_nothing_by_nature` below IS that rule's answer for ev_multi), and with a timer asked too the newest
    EVB is the DELAY's. Now: the wait on the pipe's readers is found among the running process's EVBs, its QPB read
    through the nested run's own memory (a local the run stored, sixteen bytes below its first argument), and the
    twin's is vetted against it — the process, sixteen bytes, the caller's buffer."""
    arguments, machine = _ev_multi_waiting_for_a_message(flags)
    shadow, arrived_with = _shadow("AES_ROM_EV_MULTI", arguments, machine)
    assert shadow.nested.switched == aes_event.BLOCKS
    the_rom_s = aes_event.rom_at_dsptch("AES_ROM_EV_MULTI", arguments, machine).memory
    twin_s, its = _as_a_twin_parks_it(the_rom_s, arrived_with)
    assert its.qpb_at == aes_event.abi.FIRST_ARG - EV_MULTI_QPB_BELOW_THE_FRAME
    running = case.long_in(the_rom_s, aes.AES_RLR)
    newest = case.long_in(the_rom_s, running + aes.PD_EVLIST)
    assert (newest != its.evb) == bool(flags & aes.EV_MU_TIMER), "a timer's wait is queued after the message's"
    message = arguments[5]
    pid = aes.signed(case.word_in(the_rom_s, running + aes.PD_PID))
    assert aes_event.QPB.unpack_from(the_rom_s, its.qpb_at) == (pid, aes_event.MESSAGE_BYTES, message)
    aes_event.vet_the_shadow_at_dsptch(shadow, twin_s)
    # ...a door user blocked inside the rebound entry: the same drop, held to what the entry's row says it parks.
    call = aes_event.handed(addrs.AES_ROM_EV_MULTI, aes_event.entry_frame("AES_ROM_EV_MULTI", *arguments), arrived_with)
    drop = frozenset(range(its.evb + aes.EVB_PARM, its.evb + aes.EVB_PARM + aes.LONG_BYTES))
    assert aes_event._a_door_user_s_parked_qpb("a user", [call], twin_s, the_rom_s) == drop
    without_a_message = call._replace(arguments=(flags & ~aes.EV_MU_MESAG, *call.arguments[1:]))
    with pytest.raises(AssertionError, match="which parks None"):
        aes_event._a_door_user_s_parked_qpb("a user", [without_a_message], twin_s, the_rom_s)
    # ...a twin whose QPB names another buffer: wholly inside the stack band, seen by the vet alone.
    our_qpb_at = case.long_in(twin_s, its.evb + aes.EVB_PARM)
    another_buffer = _one_byte_off(twin_s, at=our_qpb_at + aes_event.QPB.size - 1)
    with pytest.raises(AssertionError, match=f"the shadow of {addrs.AES_ROM_EV_MULTI:#x}: the QPB the parked wait names"):
        aes_event.vet_the_shadow_at_dsptch(shadow, another_buffer)
    # ...and THE RED: the rule that named ap_rdwr dropped nothing here.
    monkeypatch.setattr(aes_event, "_a_shadow_s_parked_qpb", aes_event._nothing_by_nature)
    with pytest.raises(AssertionError, match=f"holds at the dispatcher another image.* 2 bytes differ.*{its.evb + aes.EVB_PARM + aes.WORD_BYTES:#x}"):
        aes_event.vet_the_shadow_at_dsptch(shadow, twin_s)      # the two stacks' addresses share their high word


@pytest.mark.parametrize("flags", MESSAGE_WAITS.values(), ids=MESSAGE_WAITS)
def test_the_real_twin_s_blocked_message_wait_holds_under_the_shadow_and_the_door_s_rule(flags):
    """THE REAL TWIN THROUGH THE SHADOW (the case above feeds it an image built by hand "as a twin parks it"): the C
    `aes_ev_multi`, run in a fork to its halt at the dispatcher's hook, hands the shadow and the door's parked-QPB
    rule the image IT holds there — held, on every message-wait shape. And the twin's QPB mutants, as images of that
    very run, are each refused BY THE SHADOW AND BY THE DOOR'S RULE (they were killed by ev_multi's leaf battery
    alone): parked a word off, another process left in it, another buffer, ANOTHER PROCESS'S SLOT, ap_rdwr's ROLE."""
    importlib.import_module("aes_evmulti")          # ev_multi's declared signature: its battery's
    arguments, machine = _ev_multi_waiting_for_a_message(flags)
    shadow, arrived_with = _shadow("AES_ROM_EV_MULTI", arguments, machine)
    forked = aes_event.core_in_a_fork("AES_ROM_EV_MULTI", arguments, machine, read_back=True, hook=aes_event.EVENT_LAYER_HOOKS)
    assert aes_event.HALTED_AT_THE_DISPATCHER in forked.stderr and aes_event.BLOCKS in forked.stderr, forked.stderr
    the_rom_s = aes_event.rom_at_dsptch("AES_ROM_EV_MULTI", arguments, machine).memory
    call = aes_event.handed(addrs.AES_ROM_EV_MULTI, aes_event.entry_frame("AES_ROM_EV_MULTI", *arguments), arrived_with)

    def held_by_both(image):
        aes_event.vet_the_shadow_at_dsptch(shadow, image)
        return aes_event._a_door_user_s_parked_qpb("a user", [call], image, the_rom_s)
    (mine,) = aes_event.parked_qpbs(forked.image)
    parm = mine.evb + aes.EVB_PARM
    assert held_by_both(forked.image) == frozenset(range(parm, parm + aes.LONG_BYTES))
    process = case.word_in(forked.image, case.long_in(forked.image, aes.AES_RLR) + aes.PD_PID)
    assert mine.qpb_at == aes_event.host_qpb_slot("HOST_SLOT_AES_EV_MULTI_QPB", process)

    def moved_to(slot):
        elsewhere = bytearray(forked.image)
        elsewhere[slot:slot + aes_event.QPB.size] = forked.image[mine.qpb_at:mine.qpb_at + aes_event.QPB.size]
        return _with_long(elsewhere, parm, slot)
    mutants = {
        "parked one word off": (_with_long(forked.image, parm, mine.qpb_at + aes.WORD_BYTES), "the QPB the parked wait names"),
        "another process left in the QPB": (_one_byte_off(forked.image, at=mine.qpb_at + 1), "the QPB the parked wait names"),
        "another buffer left in it": (_one_byte_off(forked.image, at=mine.qpb_at + aes_event.QPB.size - 1),
                                      "the QPB the parked wait names"),
        "another process's slot": (moved_to(aes_event.host_qpb_slot("HOST_SLOT_AES_EV_MULTI_QPB", process ^ 1)),
                                   "no QPB slot of the running process"),
        "ap_rdwr's role": (moved_to(aes_event.host_qpb_slot("HOST_SLOT_AES_AP_RDWR_QPB", process)),
                           "no QPB slot of the running process"),
    }
    for label, (image, refused_by) in mutants.items():
        with pytest.raises(AssertionError, match=refused_by):
            aes_event.vet_the_shadow_at_dsptch(shadow, image)
        with pytest.raises(AssertionError, match=refused_by):
            aes_event._a_door_user_s_parked_qpb("a user", [call], image, the_rom_s)


# ---- (c) ONE ROW PER ENTRY: its frame, its inputs, what it answers ----------------------------------------------------------
_A_WRAPPER = r"(?:static inline (void|uint16_t) evdoor_{entry}\(|EVDOOR_REBOUND(_VOID)?\({entry},)"
RETURN_TYPES = {"uint16_t": aes_event.ANSWERS_A_WORD, "void": aes_event.ANSWERS_NOTHING}


# THE ONE ENTRY whose wrapper hands a word on that no shadow compares, and why (`aes_event.ENTRY_FRAMES`' note): held
# here so the exception is this entry's and no other's.
A_WORD_NO_SHADOW_COMPARES = {
    "AES_ROM_UNSYNC": "D0 is unsync's own on one path of three (nobody waiting: 0); still holding the lock it is the "
                      "D0 it was entered with — wm_update's rows on that arm compare no answer",
}


def _wrapper_answers(name):
    """What `evdoor_<entry>` returns, read off the header that spells it — by its own return type, or by which of the
    two rebound spellings it is."""
    header = (RECREATE / "include" / "aes" / "evdoor.h").read_text()
    (returned, void), = re.findall(_A_WRAPPER.format(entry=name.removeprefix(aes_event.ENTRY_PREFIX).lower()), header)
    return RETURN_TYPES[returned] if returned else (aes_event.ANSWERS_NOTHING if void else aes_event.ANSWERS_A_WORD)


@pytest.mark.parametrize("name", aes_event.ENTRY_NAMES)
def test_an_entry_s_row_answers_what_its_wrapper_returns(name):
    """The row decides what the shadow compares (`answers`); the wrapper is what a caller can read. Held equal, and —
    where a battery has declared the routine — to the signature its twin is called by."""
    row = aes_event.ENTRY_FRAMES[name]
    if name in A_WORD_NO_SHADOW_COMPARES:
        assert row.answers is aes_event.ANSWERS_NOTHING and _wrapper_answers(name) == aes_event.ANSWERS_A_WORD
        return
    assert row.answers == _wrapper_answers(name)
    if name in vdi.ALCYON:
        assert vdi.ALCYON[name].restype == row.answers


def test_the_shadow_compares_no_answer_of_an_entry_that_answers_nothing():
    """RED (G3's probe, C3): post_button's ROM routine leaves D0 its EVB walk's end; its wrapper is `void` and reports
    no answer — a correct twin was red on the leftover. An entry that answers IS compared, at the word."""
    image = bytes(BASE_IMAGE)
    void = aes_event.Shadow(aes_event.Handed(addrs.AES_ROM_POST_BUTTON, ()), image, aes_event.Nested({}, 0x1234, 10))
    aes_event.vet_the_shadow(void, image, aes.EVDOOR_NO_ANSWER)
    assert not aes_event.answers(addrs.AES_ROM_POST_BUTTON) and aes_event.answers(addrs.AES_ROM_TAK_FLAG)
    word = aes_event.Shadow(aes_event.Handed(addrs.AES_ROM_TAK_FLAG, ()), image, aes_event.Nested({}, 0x1234, 10))
    aes_event.vet_the_shadow(word, image, 0xFFFF1234)
    with pytest.raises(AssertionError, match="answered 0x0 where the ROM's routine"):
        aes_event.vet_the_shadow(word, image, 0)


def test_a_pipe_s_wait_is_handed_what_its_qpb_names_not_where_its_caller_keeps_it():
    """ev_block for a pipe's read or write is handed the address of a QPB on ITS CALLER's stack — ap_rdwr's own
    arguments in the ROM, a local of the twin's frame in our build: two addresses by nature. Two calls whose QPBs hold
    the same fields at different addresses are handed THE SAME — and differ once a field does, or a write's bytes;
    any other code's parameter is compared as the value it is. (Found pricing ap_rdwr's own rows, the first runs
    watched INSIDE an entered entry: all nine were refused on the address alone.)"""
    read, write, mutex = (aes_event.EVWAIT[name] for name in ("IASYNC_READ", "IASYNC_WRITE", "IASYNC_MUTEX"))
    here, there, message = aes_event.BAND_AT, aes_event.BAND_AT + aes_event.QPB.size, aes_event.MESSAGE_AT
    image = bytearray(BASE_IMAGE)
    image[message:message + 4] = b"abcd"
    for at in (here, there):
        image[at:at + aes_event.QPB.size] = aes_event.QPB.pack(1, 4, message)

    def handed(code, parameter):
        return aes_event.handed(addrs.AES_ROM_EV_BLOCK, aes_event.EV_BLOCK_FRAME.pack(code, parameter), image)
    assert handed(write, here) == handed(write, there) and handed(write, here).arguments == (write, (1, 4, b"abcd"))
    assert handed(read, here) == handed(read, there) and handed(read, here).arguments == (read, (1, 4, True))
    assert handed(mutex, here) != handed(mutex, there), "a semaphore's address is compared as it is"
    image[there + 2:there + 4] = (3).to_bytes(2, "big")
    assert handed(write, here) != handed(write, there), "another count"
    image[there + 2:there + 4] = (4).to_bytes(2, "big")
    image[there + 4:there + 8] = (message + 1).to_bytes(4, "big")
    assert handed(write, here) != handed(write, there) and handed(read, here) == handed(read, there), (
        "a write's bytes are read through its buffer; a read's buffer only as handed or not")


# ---- (f) THE SR SAVE WORDS: one table ------------------------------------------------------------------------------------
SR_SAVE_WORD_PREFIX = "AES_SR_"


def test_the_sr_drop_table_is_the_header_s_save_words():
    """Every SR save word the header names — the dispatcher's with the others, since the switch has a host model
    that stores none — and each dropped only where the ROM's run stored it: over a run that stops AT dsptch (every
    wait's, before savestate) the dispatcher's word is not stored, and stays compared."""
    save_words = {name: value for name, value in aes.CONSTANTS.items() if name.startswith(SR_SAVE_WORD_PREFIX)}
    assert set(aes_event.SR_DROPS) == set(save_words.values()) and len(save_words) == 3
    assert aes_event.sr_drops() == aes_event.sr_drops(*aes_event.SR_DROPS)
    at_dsptch = aes_event.rom_at_dsptch("AES_ROM_EV_MULTI", aes_event.EV_MULTI_FRAME.unpack(aes_event.KEY_WAIT), aes_event.machine())
    assert aes.AES_SR_DISPATCH not in at_dsptch.writes
    assert aes.AES_SR_DISPATCH not in aes_event.not_compared_where_the_rom_stored(at_dsptch.memory, make_image(aes_event.machine()))
    (lo, hi, why), = aes_event.SR_PSETUP_DROP
    assert (lo, hi) == (aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + aes.WORD_BYTES) and "psetup" in why


def test_an_sr_save_word_is_dropped_only_where_the_rom_s_run_stored_it():
    """What neither shore compares after a ROM run: an SR save word the run STORED — and not one it left alone, where
    a C that wrote the word differs. ONE RULE, wherever two shores are compared (`not_compared_where_the_rom_stored`):
    by what the ROM's memory AS COMPARED no longer holds of what its run started with — the pokes it was staged with,
    or the image it ran over (a shadow's nested run: that image and the run's ledger). No SR byte is left out
    unconditionally; and a store of the very byte the run started with leaves nothing out."""
    rule = aes_event.not_compared_where_the_rom_stored
    assert not aes_event.SR_SAVE_BYTES & aes_event._NOT_COMPARED
    high, low = (~byte & BYTE_MASK for byte in BASE_IMAGE[aes.AES_SR_PSETUP:aes.AES_SR_PSETUP + aes.WORD_BYTES])
    staged = {aes.AES_SR_PSETUP: bytes((high, low))}            # staged other than the base image holds
    memory = bytearray(BASE_IMAGE)
    memory[aes.AES_SR_PSETUP:aes.AES_SR_PSETUP + aes.WORD_BYTES] = bytes((high, low ^ 4))    # stored: the low byte another's
    assert rule(memory, staged) == aes_event._NOT_COMPARED | {aes.AES_SR_PSETUP + 1}
    assert rule(BASE_IMAGE, {}) == aes_event._NOT_COMPARED, "a run that stored no SR word: every SR byte compared"
    assert (aes_event._started_with(staged, aes.AES_SR_PSETUP), aes_event._started_with(staged, aes.AES_SR_PSETUP + 1)) == (high, low)
    assert aes_event._started_with(staged, aes.AES_SR_SPL) == BASE_IMAGE[aes.AES_SR_SPL], "under no poke: the base image's"
    # ...the same rule with the run's start as an IMAGE and its memory read through its ledger (a shadow's):
    before = bytes(make_image(staged))
    left_by = aes_event._LeftBy(before, {aes.AES_SR_SPL: BASE_IMAGE[aes.AES_SR_SPL] ^ 1, aes.AES_SR_SPL + 1: BASE_IMAGE[aes.AES_SR_SPL + 1],
                                         aes.AES_SR_PSETUP: high ^ 2})
    assert rule(left_by, before) == aes_event._NOT_COMPARED | {aes.AES_SR_SPL, aes.AES_SR_PSETUP}, (
        "a byte stored with the value the run started with (SR_SPL's low byte) was left out")
    assert rule(aes_event._LeftBy(before, {}), before) == aes_event._NOT_COMPARED


def test_the_shadow_leaves_out_an_sr_save_word_only_where_its_nested_run_stored_it():
    """...and the SHADOW's compare, by the nested run's own ledger: a twin that stored nothing where the ROM's routine
    parked the status register is its shadow (off target a twin stores none), and so is one that parked ITS OWN there
    (the word is its caller's on either shore); one that wrote a save word the routine left alone is not."""
    arrived, call = bytes(BASE_IMAGE), aes_event.Handed(addrs.AES_ROM_TAK_FLAG, ())
    parked = {aes.AES_SR_SPL: ~BASE_IMAGE[aes.AES_SR_SPL] & BYTE_MASK}
    shadow = aes_event.Shadow(call, arrived, aes_event.Nested(parked, 0, 0))
    aes_event.vet_the_shadow(shadow, arrived, 0)
    parked_its_own = bytearray(arrived)
    parked_its_own[aes.AES_SR_SPL] ^= 1
    aes_event.vet_the_shadow(shadow, bytes(parked_its_own), 0)
    wrote_the_other = bytearray(arrived)
    wrote_the_other[aes.AES_SR_PSETUP] ^= BYTE_MASK
    with pytest.raises(AssertionError, match=f"left another image.*1 bytes differ.*{aes.AES_SR_PSETUP:#x}"):
        aes_event.vet_the_shadow(shadow, bytes(wrote_the_other), 0)


def _released_at_the_lock():
    """gr_rubbox released at its lock: a door user's case whose ROM run stores NEITHER save word (asserted)."""
    name, arguments, machine, interrupts = _rubber_box_released_as_the_lock_is_taken()
    _calls, _delivered, rom_memory, _result = aes_event.rom_interrupted(name, arguments, machine, interrupts)
    staged = make_image(aes.staged(name, arguments, machine))
    assert all(staged[at] == rom_memory[at] for at in aes_event.SR_SAVE_BYTES), "the premise: the run left both words alone"
    return name, arguments, machine, interrupts


def _the_c_s_child_leaving(monkeypatch, changed):
    """Every child of the case answers the image `changed(image)` makes of the one the C left."""
    refusal = aes_event.refusal

    def left_otherwise(*run, **named):
        returncode, stderr, image = refusal(*run, **named)
        return returncode, stderr, bytes(changed(bytearray(image)))
    monkeypatch.setattr(aes_event, "refusal", left_otherwise)


def _an_sr_save_word_written(image):
    image[aes.AES_SR_PSETUP] ^= BYTE_MASK
    image[aes.AES_SR_SPL + 1] ^= BYTE_MASK
    return image


def test_a_door_user_s_c_that_wrote_an_sr_save_word_the_rom_s_run_left_alone_differs(monkeypatch):
    """THE CALLER (`interrupted`: every interrupted and every blocked door case). THE RED: with the four SR
    save bytes left out unconditionally, a C that wrote psetup's and spl7's save words where the ROM's run stored
    neither compared equal."""
    case_ = _released_at_the_lock()
    _the_c_s_child_leaving(monkeypatch, _an_sr_save_word_written)
    with pytest.raises(AssertionError, match=f"2 bytes differ from the ROM's run: {aes.AES_SR_SPL + 1:#x} .*{aes.AES_SR_PSETUP:#x}"):
        aes_event.interrupted(*case_, second_differential=False)


def test_a_door_user_s_c_is_not_held_to_an_sr_save_word_the_rom_s_run_stored(monkeypatch):
    """...and the drop itself, at the same caller: the ROM's run taken to have STORED spl7's save word (its memory no
    longer holds what was staged there), the C — which stores none off target — is not red on it; psetup's word,
    which that run left alone, stays compared."""
    case_ = _released_at_the_lock()
    rom_interrupted = aes_event.rom_interrupted

    def stored_spl7_s_word(*run, **named):
        calls, delivered, memory, result = rom_interrupted(*run, **named)
        memory = bytearray(memory)
        memory[aes.AES_SR_SPL + 1] ^= BYTE_MASK
        return calls, delivered, bytes(memory), result
    monkeypatch.setattr(aes_event, "rom_interrupted", stored_spl7_s_word)
    aes_event.interrupted(*case_, second_differential=False)
    _the_c_s_child_leaving(monkeypatch, _an_sr_save_word_written)
    with pytest.raises(AssertionError, match=f"1 bytes differ from the ROM's run: {aes.AES_SR_PSETUP:#x}"):
        aes_event.interrupted(*case_, second_differential=False)


def test_a_delivered_interrupt_s_own_store_of_an_sr_save_word_is_not_the_run_s(monkeypatch):
    """THE RED for the rule asked of the staged machine alone, in the one caller whose ROM memory is not one run's:
    an interrupt DELIVERED at a door call that itself stores spl7's save word leaves the byte other than it was
    staged ON BOTH SHORES — the C's child is laid the same delivery — so it read as "the ROM's run stored it" and was
    left out, and a C that wrote the word afterwards went unseen. Asked of the machine WITH ITS DELIVERIES LAID: the
    byte is compared (both shores hold the delivery's), and a C that wrote it differs."""
    case_ = _released_at_the_lock()
    rom_interrupted, at = aes_event.rom_interrupted, aes.AES_SR_SPL + 1

    def its_first_interrupt_stores_spl7_s_word(*run, **named):
        calls, delivered, memory, result = rom_interrupted(*run, **named)
        first = min(delivered)
        found, wrote = delivered[first]
        assert at not in found, "the premise: no delivery of the case stores the word by itself"
        stored = bytes([memory[at] ^ BYTE_MASK])
        delivered = {**delivered, first: ({**found, at: bytes([memory[at]])}, {**wrote, at: stored})}
        return calls, delivered, memory[:at] + stored + memory[at + 1:], result
    monkeypatch.setattr(aes_event, "rom_interrupted", its_first_interrupt_stores_spl7_s_word)
    aes_event.interrupted(*case_, second_differential=False)

    def the_word_written_after(image):
        image[at] ^= 1
        return image
    _the_c_s_child_leaving(monkeypatch, the_word_written_after)
    with pytest.raises(AssertionError, match=f"1 bytes differ from the ROM's run: {at:#x}"):
        aes_event.interrupted(*case_, second_differential=False)


# ---- (h) THE FORK AND THE DISPATCHER'S HOOK ------------------------------------------------------------------------------
def _dsptch_in_a_fork(image):
    """The host's dsptch entered over `image` in a FORK, as a guarded core that reaches it is."""
    buf = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer(bytearray(image))
    entered = getattr(aes_event._lib, DSPTCH_ENTERED)
    entered.restype, entered.argtypes = None, [ctypes.POINTER(ctypes.c_uint8)]
    return aes_event.in_a_fork(lambda: entered(buf))


@pytest.mark.parametrize("at_dsptch, switches", AT_DSPTCH.values(), ids=AT_DSPTCH)
def test_a_guarded_core_that_reaches_the_dispatcher_fails_by_the_hook_s_own_words(at_dsptch, switches):
    """A core guarded in a fork that reaches dsptch — a wait's own arm, or a twin gone astray — ends its fork at the
    dispatcher's hook, and THE HOOK'S WORDS REACH THE GUARD'S MESSAGE: a block told from a yield, beside the C's halt
    line. (The hook is a Python callback printing to `sys.stderr`: in a fork that is the worker's captured stream —
    lost — unless the fork points it at the guard's pipe; then only the C's halt line, which names neither, arrived.)"""
    returncode, stderr = _dsptch_in_a_fork(at_dsptch())
    assert returncode == -int(signal.SIGABRT), (returncode, stderr)
    assert switches in stderr and aes_event.HALTED_AT_THE_DISPATCHER in stderr
    with pytest.raises(AssertionError, match=f"did not return in a child.*{switches}"):
        aes_event._vet_returned("a core", (), returncode, stderr)


def test_a_fork_serves_only_the_hooks_a_core_draws_and_calls_through_and_only_in_a_case_s_pass():
    """`serves`: the VDI's cores and the register hook, left as the case's pass bound them — never the event door's
    (a door user's child is a fresh interpreter), and not without a `hook=` to have bound them."""
    assert aes_event.FORK_SERVABLE_HOOKS < set(aes_event.FORK_UNSERVED_HOOKS)
    assert not aes_event.FORK_SERVABLE_HOOKS & DOOR_HOOKS
    with pytest.raises(AssertionError, match="a fork serves .* at most"):
        aes_event.in_a_fork(lambda: None, serves=(aes_event.HOOK_SYMBOL,))
    with pytest.raises(AssertionError, match="it binds none"):
        aes_event.run_core_guarded(TAK_FLAG, THE_LOCK, aes_event.machine(), serves=(isr.CALL_VECTOR_SYMBOL,))


def test_a_fork_left_serving_the_vdi_s_hook_draws_through_the_case_s_pass():
    """gsx_moff draws through the VDI's hook: guarded in a plain fork it ends there by the hook's name (above); with
    the hook SERVED — the fork made inside the case's own pass — its fork returns, and the differential holds."""
    name, arguments = REACHES_A_VOID_HOOK
    with pytest.raises(AssertionError, match=f"reached the hook {isr.CALL_VECTOR_SYMBOL}"):
        aes_event.run_core_guarded(name, arguments, aes_event.shown_machine(), hook=aes_gsx.vdi_hook)
    aes_event.run_core_guarded(name, arguments, aes_event.shown_machine(), hook=aes_gsx.vdi_hook,
                               serves=(isr.CALL_VECTOR_SYMBOL,))


# ---- a watch at arbitrary ROM entries (`aes_event.EntryStops`) -------------------------------------------------------------
def test_a_watch_at_arbitrary_entries_keeps_the_rom_s_own_calls_in_order():
    """Return wakes the desk; the dispatcher's loop WATCHED at acancel, takeoff and apret arrives at ev_multi's tail's
    calls in the ROM's order — takeoff INSIDE acancel, twice running (an entry is watched again once its call has
    returned, and not before) — each with the frame its caller pushed; and it ENDS where the desk comes out of its
    evnt_multi, its memory there the unwatched run's (`woken_by_a_key`), the stack band aside."""
    arrivals, at_the_end = [], []
    waited_for = case.word_in(BASE_IMAGE, aes.SHELL_PD + aes.PD_EVWAIT)
    entries = (addrs.AES_ROM_ACANCEL, addrs.AES_ROM_TAKEOFF, addrs.AES_ROM_APRET)
    watch = aes_event.EntryStops(
        entries, lambda pc, sp, memory: arrivals.append((pc, bytes(memory[sp + aes.LONG_BYTES:sp + 2 * aes.LONG_BYTES]))),
        ends={addrs.AES_ROM_EV_MULTI_RETURN}, ended=lambda memory: at_the_end.append(bytes(memory)))
    with pytest.raises(aes_event.Ended):
        aes_event.run_watched(make_image(aes_event.keys(aes_event.RETURN_KEY)), addrs.AES_ROM_DISP_LOOP, watch)
    assert [pc for pc, _frame in arrivals] == [addrs.AES_ROM_ACANCEL, addrs.AES_ROM_TAKEOFF, addrs.AES_ROM_TAKEOFF,
                                              addrs.AES_ROM_APRET]
    (_acancel, masks), (_takeoff, first), (_again, second), (_apret, _mask) = arrivals
    assert struct.unpack(">H", masks[:aes.WORD_BYTES]) == (waited_for,), "acancel: every event the desk waited for"
    cancelled = {struct.unpack(">I", frame)[0] for frame in (first, second)}
    assert len(cancelled) == 2 and all(aes.AES_EVB_TABLE <= evb < aes.AES_EVB_TABLE + aes.AES_EVB_COUNT * aes.EVB_BYTES
                                       for evb in cancelled), "takeoff: two of the desk's EVBs"
    woken, = at_the_end
    assert not aes_event.differing(woken, make_image(aes_event.woken_by_a_key()), not_compared=frozenset(case.STACK_BAND))


def test_a_watch_with_no_end_named_lets_its_run_return():
    """...and with no end named the run returns, the watch having seen its arrivals: wind_update taking the free lock
    arrives at tak_flag once."""
    arrivals = []
    wm_update = _wm_update()
    memory = make_image(aes.staged(wm_update.WM_UPDATE, (wm_update.BEG_UPDATE,), aes_event.machine()))
    watch = aes_event.EntryStops((addrs.AES_ROM_TAK_FLAG,), lambda pc, _sp, _memory: arrivals.append(pc))
    assert aes_event.run_watched(memory, addrs.AES_ROM_WM_UPDATE, watch)
    assert arrivals == [addrs.AES_ROM_TAK_FLAG]


def test_a_watch_that_would_end_its_run_having_run_nothing_is_refused_by_name():
    """A machine a watched run hands on is one the ROM MADE: a run "ended" at its own entry — the dispatcher's loop
    watched to end at the dispatcher's loop, no gate before it — has executed nothing, and the memory `ended` would
    be handed is the staged one. Refused by name, as is a gate that is itself an end (the first stop opens it, the
    second ends the run, nothing between); with a gate that is a REAL stop past the entry, the same end is the
    scheduler's own state after a whole pass."""
    loop, staged, handed_on = addrs.AES_ROM_DISP_LOOP, aes_event.keys(aes_event.RETURN_KEY), []
    with pytest.raises(AssertionError, match="having executed nothing"):
        aes_event.run_watched(make_image(staged), loop, aes_event.EntryStops((), None, ends={loop}, ended=handed_on.append))
    with pytest.raises(AssertionError, match="ends at its gate"):
        aes_event.EntryStops((), None, ends={loop}, once_past=loop)
    assert not handed_on


def test_a_watch_never_arms_the_pc_it_is_stopped_at():
    """THE KIT'S WATCH LOOP SPINS FOR EVER on a stop armed at its own PC (no instruction runs, so its budget is never
    spent — `rom_bench.watched`; the kit's own fix is deferred, STATUS). `EntryStops` makes it impossible on this
    side: every set it answers is held clear of the PC it answers at — an entry whose call returns into itself is
    refused by name."""
    entry, sp = addrs.AES_ROM_TAK_FLAG, A_STACK
    memory = bytearray(sp) + entry.to_bytes(aes.LONG_BYTES, "big")      # a return address that IS the entry
    watch = aes_event.EntryStops((entry,), lambda *_stop: None)
    with pytest.raises(AssertionError, match=f"may not arm {entry:#x}"):
        watch.stopped(entry, sp, memory)
    memory[sp:sp + aes.LONG_BYTES] = (entry + aes.WORD_BYTES).to_bytes(aes.LONG_BYTES, "big")
    assert entry not in watch.stopped(entry, sp, memory)


A_STACK = 0x100                        # where a watch's unit test lays a return address: any address of a scratch memory


# ---- an image as pokes, and where two images differ (`aes_event.as_pokes`, `_differing_addresses`) ------------------------
BLOCK, LINE = aes_event.COMPARED_BLOCK_BYTES, aes_event.COMPARED_LINE_BYTES
# Bytes at every edge the block-then-line compare has: an image's first and last, a block's and a line's last and first.
AT_EVERY_EDGE = (0, LINE - 1, LINE, BLOCK - 1, BLOCK, BLOCK + LINE, 3 * BLOCK - 1, addrs.ST_RAM_BYTES - 1, addrs.ST_RAM_BYTES,
                 aes_event.IMAGE_BYTES - 1)


def _changed_at(addresses):
    image = bytearray(BASE_IMAGE)
    for at in addresses:
        image[at] ^= BYTE_MASK
    return image


def test_two_images_differ_where_a_bytewise_scan_says():
    """The compare by blocks, then lines, answers what a scan of every byte does — at every edge of either, in order;
    and below `upto` alone when one is named."""
    image = _changed_at(AT_EVERY_EDGE)
    assert aes_event._differing_addresses(BASE_IMAGE, image) == sorted(AT_EVERY_EDGE)
    assert aes_event._differing_addresses(BASE_IMAGE, BASE_IMAGE) == []
    below = aes_event._differing_addresses(BASE_IMAGE, image, addrs.ST_RAM_BYTES)
    assert below == [at for at in sorted(AT_EVERY_EDGE) if at < addrs.ST_RAM_BYTES]


def test_an_image_as_pokes_is_that_image_again_laid_over_the_snapshot():
    """`as_pokes`: every byte that differs, in runs — laid over what it was taken against it is the image again; with
    the stack band left out and RAM alone kept, it is the image but for those."""
    in_the_band = case.STACK_BAND[0]
    image = _changed_at((*AT_EVERY_EDGE, BLOCK + LINE + 1, in_the_band))
    pokes = aes_event.as_pokes(image)
    assert make_image(pokes) == image and pokes[BLOCK + LINE] == bytes(image[BLOCK + LINE:BLOCK + LINE + 2])
    kept = aes_event.as_pokes(image, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES)
    left_out = {in_the_band, *(at for at in AT_EVERY_EDGE if at >= addrs.ST_RAM_BYTES)}
    assert aes_event._differing_addresses(make_image(kept), image) == sorted(left_out)
    over_another = aes_event.as_pokes(image, _changed_at((0,)))
    assert 0 not in over_another and make_image(merge_pokes({0: bytes([image[0]])}, over_another)) == image


def _as_pokes_per_byte(memory, over, without, upto):
    """THE DEFINITION `as_pokes` is held to: a poke per differing byte below `upto`, `without`'s left out, merged."""
    size = len(memory) if upto is None else upto
    return merge_pokes({at: bytes([memory[at]]) for at in range(size) if memory[at] != over[at] and at not in without})


A_SMALL_IMAGE = 5 * aes_event.COMPARED_BLOCK_BYTES + 0x123      # five blocks and a ragged one: every edge, cheaply
RANDOM_IMAGES = 60


@pytest.mark.parametrize("seed", range(4))
def test_an_image_as_pokes_is_the_per_byte_definition_s_over_random_images(seed):
    """The block-wise spelling against the definition: random runs of changed bytes — short, long, across block
    edges, up to the image's last byte — random spans left out (as a set and as a range), a random `upto`, and
    another image than the snapshot to differ from."""
    rng = random.Random(seed)
    block = aes_event.COMPARED_BLOCK_BYTES
    for _image in range(RANDOM_IMAGES):
        over = bytes(rng.randrange(256) for _byte in range(64)) * (A_SMALL_IMAGE // 64 + 1)
        over = over[:A_SMALL_IMAGE]
        memory = bytearray(over)
        for _run in range(rng.randrange(12)):
            start = rng.choice((rng.randrange(A_SMALL_IMAGE), rng.randrange(1, 6) * block - rng.randrange(4)))
            for at in range(start, min(A_SMALL_IMAGE, start + rng.choice((1, 2, 7, block, block + 3)))):
                memory[at] ^= rng.randrange(1, 256)
        lo = rng.randrange(A_SMALL_IMAGE)
        band = range(lo, min(A_SMALL_IMAGE, lo + rng.choice((1, 5, block, 2 * block))))
        scattered = frozenset(rng.randrange(A_SMALL_IMAGE) for _at in range(rng.randrange(40))) | frozenset(band)
        upto = rng.choice((None, A_SMALL_IMAGE, rng.randrange(A_SMALL_IMAGE), 3 * block))
        for without in (frozenset(), band, scattered):
            assert aes_event.as_pokes(memory, over, without=without, upto=upto) \
                == _as_pokes_per_byte(memory, over, frozenset(without), upto), (seed, _image, without, upto)


# ---- the tick as an interrupt (`aes_event.tick`, `ticks`) -----------------------------------------------------------------
def test_ticks_are_the_tick_glue_run_once_each():
    """`ticks(n)` is n runs of the AES's tick glue over the image in place, each over what the last left: with a press
    just taken (b_click's click delay running), the delay counts down a tick at a time, and the last one resolves the
    click — the fork a press queues (`click_counted`'s own ending)."""
    image = make_image(aes_event.machine())
    aes_event._interrupt_over(image, addrs.VDI_ROM_MOUSE_ISR, {"a0": aes_event.PACKET_AT},
                              aes_event._packet(aes_event.MOUSE_PACKET_HEADER | aes_event.MOUSE_PACKET_LEFT_BUTTON))
    delay = case.word_in(image, aes.AES_GL_CLICK_TICKS)
    assert delay > 1, "the premise: a press starts a click delay of several ticks"
    one_by_one = bytearray(image)
    wrote = aes_event.ticks(delay - 1)(image)
    for _tick in range(delay - 1):
        aes_event.tick(one_by_one)
    assert wrote and image == one_by_one and case.word_in(image, aes.AES_GL_CLICK_TICKS) == 1
    assert case.word_in(image, aes.AES_FORK_COUNT) == 0
    aes_event.tick(image)
    assert case.word_in(image, aes.AES_GL_CLICK_TICKS) == 0 and case.word_in(image, aes.AES_FORK_COUNT) == 1


# ---- THE ZYGOTE MAKES THE FORKS THAT SERVE A NAMED HOOK, AND THE DOOR USERS' CHILDREN ------------------------------------
def _left_by(forked):
    """What a fork's verdict is made of: how it ended, and the image it left."""
    return forked.returncode, forked.image


def test_a_fork_that_serves_a_named_hook_is_the_zygote_s_and_ends_as_the_worker_s_own(a_zygote_runs, monkeypatch):
    """A hook NAMED "module:attribute" is a binding the zygote can open itself: its fork of a core that polls the VDI
    and queues a fork function (chkkbd, a key in the ring) ends as the worker's own fork of the same run does — the
    same exit, the same image, the key queued — where a fork with NO pass opened fails by name (the core reached a
    hook nothing served): so the zygote's fork did open the pass. A builder with no name — a case's own — stays the
    worker's."""
    serves, named = aes_event.SERVED_IN_A_FORK, aes_event.EVENT_LAYER_HOOKS
    assert aes_event.name_of_a_hook(named) == "aes_event:EVENT_LAYER_HOOKS"
    assert aes_event.hook_named("aes_event:EVENT_LAYER_HOOKS") is named
    assert aes_evinput.HOOKS is named, "the input's battery binds the shared, named hook"
    unnamed = aes.doors(aes_event.vdi_hook)
    assert aes_event.name_of_a_hook(unnamed) is None
    assert aes_event.the_zygote_stands_in(_tak_flag_run(), serves, named)
    assert not aes_event.the_zygote_stands_in(_tak_flag_run(), serves, unnamed)
    assert not aes_event.the_zygote_stands_in(_tak_flag_run(seeded=True), serves, named)
    with pytest.raises(AssertionError, match="is no hook declared under that name"):
        aes_event.hook_named("aes_event:vdi_hook")
    arrival = aes_evinput.at("a key wakes the desk", aes_evinput.CHKKBD)
    machine = merge_pokes(arrival.machine, aes_event.savptr_in_the_band())
    made = aes_event.FORKS_MADE[aes_event.BY_THE_ZYGOTE]
    by_the_zygote = aes_event.core_in_a_fork(arrival.name, arrival.arguments, machine, read_back=True, hook=named)
    assert aes_event.FORKS_MADE[aes_event.BY_THE_ZYGOTE] == made + 1 and by_the_zygote.returncode == 0, by_the_zygote.stderr
    assert aes_event.fork_queue(by_the_zygote.image)[-1][0] == addrs.AES_ROM_KCHANGE, "the poll's key, queued"
    unserved = aes_event.core_in_a_fork(arrival.name, arrival.arguments, machine, read_back=True)
    assert unserved.returncode == aes_event.FORK_REACHED_A_HOOK, "the premise: the core reaches a hook"
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", True)
    made = aes_event.FORKS_MADE[aes_event.BY_THE_ZYGOTE]
    by_the_worker = aes_event.core_in_a_fork(arrival.name, arrival.arguments, machine, read_back=True, hook=named)
    assert aes_event.FORKS_MADE[aes_event.BY_THE_ZYGOTE] == made, "sidelined: the worker's own fork"
    assert _left_by(by_the_worker) == _left_by(by_the_zygote)


def _door_children(monkeypatch, name, arguments, machine, **named):
    """The same door user's child made both ways: `(the zygote's fork, a fresh interpreter)`."""
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", aes_event.MEANT_UNDER_PATCHES)
    made = dict(aes_event.FORKS_MADE)
    forked = aes_event.door_child(name, arguments, machine, **named)
    assert aes_event.FORKS_MADE[aes_event.BY_THE_ZYGOTE] == made.get(aes_event.BY_THE_ZYGOTE, 0) + 1
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", True)
    fresh = aes_event.door_child(name, arguments, machine, **named)
    assert aes_event.FORKS_MADE[aes_event.A_FRESH_INTERPRETER] == made.get(aes_event.A_FRESH_INTERPRETER, 0) + 1
    return forked, fresh


def test_a_door_user_s_child_is_the_zygote_s_fork_and_says_what_a_fresh_interpreter_says(a_zygote_runs, monkeypatch):
    """A DOOR USER'S CHILD by the zygote against the fresh interpreter it stands in for, over the three ends a child
    has: a call that BLOCKS (refused at the dispatcher by name: the same exit, the same lines, the same frames
    handed, the same image), one that RETURNS through an interrupt (its answer, the frames it printed AS IT EXITED,
    the image), and one that returns with nothing asked of it. And a routine whose child binds doors of its own first
    (`before`) is a fresh interpreter still."""
    blocked, fresh = _door_children(monkeypatch, *WOULD_BLOCK, grwait.button_down())
    assert blocked[0] == fresh[0] != 0 and blocked[2] == fresh[2]
    assert blocked[1].splitlines() == fresh[1].splitlines()
    assert aes_event.BLOCKS in blocked[1] and aes_event.handed_in(blocked[1])
    name, arguments, machine, interrupts = _rubber_box_released_as_the_lock_is_taken()
    delivered = aes_event.deliveries(name, arguments, machine, interrupts)
    returned, fresh = _door_children(monkeypatch, name, arguments, machine, interrupts=delivered, answered=True)
    assert returned[0] == fresh[0] == 0 and returned[2] == fresh[2]
    assert vdi_helpers.answer_in(returned[1]) == vdi_helpers.answer_in(fresh[1])
    assert returned[1].splitlines() == fresh[1].splitlines()
    assert aes_event.handed_in(returned[1]) == aes_event.handed_in(fresh[1]) != []
    plain, fresh = _door_children(monkeypatch, name, arguments, machine, read_back=False)
    assert plain == fresh and plain[2] is None
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", aes_event.MEANT_UNDER_PATCHES)
    made = aes_event.FORKS_MADE[aes_event.A_FRESH_INTERPRETER]
    aes_event.door_child(name, arguments, machine, before="pass; ", read_back=False)
    assert aes_event.FORKS_MADE[aes_event.A_FRESH_INTERPRETER] == made + 1


def test_a_routine_s_declared_child_doors_are_run_by_the_zygote_s_fork_as_by_a_fresh_interpreter(a_zygote_runs, monkeypatch):
    """A CHILD THAT BINDS ITS ROUTINE'S OWN DOORS FIRST — the file selector's GEMDOS replay, declared once by the
    module that owns its machines (`declare_child_doors`) — is the zygote's too (the door refused the zygote for ANY
    `before`: 117 fresh interpreters a suite run for one constant): the fork runs the declared source first and says
    what the interpreter says — the same exit, the same lines (the battery's own digest among them, printed as the
    child exits), the same image. A CASE's own source (anything else) is a fresh interpreter still."""
    machine = fsl.fs_input_machine("", "")
    script, _passes = fsl.looping(machine, 0)
    replayed, doors = fsl.replay_machine(machine, script), aes_event.CHILD_DOORS[fsl.INPUT]
    assert "aes_fslib" in doors and "aes_fslib" not in aes_event.ZYGOTE_HOLDS, "the premise: doors the zygote holds no module of"
    forked, fresh = _door_children(monkeypatch, fsl.INPUT, fsl.ARGUMENTS, replayed, objects=True, before=doors)
    assert forked[0] == fresh[0] != 0 and forked[1].splitlines() == fresh[1].splitlines() and forked[2] == fresh[2]
    assert len(fsl.replay_calls(forked[2])) == len(script) > 0, "the replay's handlers were bound: the calls were served"
    monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", aes_event.MEANT_UNDER_PATCHES)
    made = aes_event.FORKS_MADE[aes_event.A_FRESH_INTERPRETER]
    aes_event.door_child(fsl.INPUT, fsl.ARGUMENTS, replayed, objects=True, before=doors + "pass; ", read_back=False)
    assert aes_event.FORKS_MADE[aes_event.A_FRESH_INTERPRETER] == made + 1


def test_a_door_user_s_child_still_running_is_a_timeout_whoever_made_it(a_zygote_runs, monkeypatch):
    """A child that outlives its seconds raises `subprocess.TimeoutExpired` from the zygote's fork as from a fresh
    interpreter: the fork's alarm ends it, and the door says so by the same exception."""
    monkeypatch.setattr(aes_event.GUARD_ZYGOTE[0], "ask", lambda _request, _image=None: (-signal.SIGALRM, "still running"))
    with pytest.raises(subprocess.TimeoutExpired):
        aes_event.door_child(*WOULD_BLOCK, grwait.button_down(), seconds=1)


def test_a_door_user_s_child_that_answers_prints_its_answer_whoever_made_it(a_zygote_runs, monkeypatch):
    """...and a routine that ANSWERS: the word the core returned, printed by the zygote's fork as by a fresh
    interpreter — and not at all where the case did not ask."""
    answered, fresh = _door_children(monkeypatch, *STILLDN, grwait.button_down(), answered=True, read_back=False)
    assert vdi_helpers.answer_in(answered[1]) == vdi_helpers.answer_in(fresh[1]) is not None
    unasked, fresh = _door_children(monkeypatch, *STILLDN, grwait.button_down(), read_back=False)
    assert vdi_helpers.answer_in(unasked[1]) is None and unasked == fresh


# ---- ONE SETTLING OF A LEAF ROW (`aes_event.settled`), and EVERY ROW the event layer's three batteries register ------------
def _every_returning_arrival(layer):
    """Every arrival of `layer`'s scenarios whose ROM run RETURNS (a row's run does): `(routine, arrival)` each."""
    arrivals = [layer.arrival(name, nth) for name, nth in layer.cases(*layer.ROUTINES)]
    return [arrival for arrival in arrivals if not aes_evlib.switches(arrival.name, arrival.arguments, arrival.machine)]


# What a layer knows BY NAME that the one settling is TOLD (`polls`): the routines that poll the keyboard, whose
# `savptr` is in the band for every row whether a given run takes the trap or not.
THE_ROUTINES_THAT_POLL = (aes_evinput.CHKKBD, aes_evinput.FORKER, "AES_ROM_EV_MULTI")
# At least: each layer registers rows of more routines than this — but ev_multi's, which is one routine's battery.
ROUTINES_A_LAYER_SETTLES = collections.defaultdict(lambda: 5, {"ev_multi": 1})
Registered = namedtuple("Registered", "label name arguments machine")


def _rows_of_arrivals(layer, *batteries):
    """What `aes_evasync.register_rows` hands `layer`'s registrar for each priced row of `batteries` (their ROWS)."""
    rows = []
    for battery in batteries:
        for label, scenario, routine, which in battery.ROWS:
            arrival = layer.at(scenario, routine, which)
            rows.append(Registered(label, routine, arrival.arguments, arrival.machine))
    return rows


def _rows_of_the_pipes(monkeypatch):
    """...and what the processes' and pipes' battery hands its own, read off its registration made again."""
    import test_aes_pdpipe
    rows = []

    def noted(label, name, arguments, machine, *, through_line_f=False):
        if not through_line_f:
            rows.append(Registered(label, name, arguments, machine))
    monkeypatch.setattr(aes_pdpipe, "register", noted)
    test_aes_pdpipe._register_rows()
    return rows


def _rows_of_the_waits(_monkeypatch):
    import test_aes_evlib
    import test_aes_evwait
    return _rows_of_arrivals(aes_evlib, test_aes_evlib, test_aes_evwait)


def _rows_of_the_input(_monkeypatch):
    import test_aes_evfork
    import test_aes_evinput
    return _rows_of_arrivals(aes_evinput, test_aes_evinput, test_aes_evfork)


def _rows_of_ev_multi(_monkeypatch):
    """...and ev_multi's own (`aes_evmulti.register`: one routine's rows, every one told to poll)."""
    import aes_evmulti
    import test_aes_evmulti
    return [Registered(label, aes_evmulti.EV_MULTI, made.arguments, aes_evmulti.machine_of(made))
            for label, made in ((label, aes_evmulti.RETURNING[name]) for label, name in test_aes_evmulti.ROWS)]


SETTLED_ROWS = {"the waits": _rows_of_the_waits, "the input": _rows_of_the_input, "the processes and pipes": _rows_of_the_pipes,
                "ev_multi": _rows_of_ev_multi}


def _settled_by_the_rom_s_own_run(row):
    """WHAT THE ONE SETTLING OWES A ROW, SPELT A SECOND TIME — nothing here is the registrar's: the ROM's routine run
    whole over the row's machine by the oracle itself, `savptr` in the band where the layer says the routine polls
    or where that run is seen to take the trap (then run again over the moved machine), and of the words that
    differ by nature each one that run stored WHOLE: `(the machine with those words at the values the run left, the
    words' addresses in the table's order, whether the run moved savptr by itself)`."""
    band = aes_event.savptr_in_the_band()

    def stored_by_a_run_over(machine):
        image = make_image(aes.staged(row.name, vdi.as_signed(row.name, row.arguments), machine))
        final, writes, _regs = emu.run(image, getattr(addrs, row.name), max_insns=aes_event.DERIVATION_INSNS)
        return final, writes
    told = row.name in THE_ROUTINES_THAT_POLL
    machine = merge_pokes(dict(row.machine), band) if told else dict(row.machine)
    final, writes = stored_by_a_run_over(machine)
    by_itself = not told and addrs.SYSVAR_SAVPTR in writes
    if by_itself:
        machine = merge_pokes(machine, band)
        final, writes = stored_by_a_run_over(machine)
    words = [word for word, _drop in aes_event.WORDS_BY_NATURE
             if all(word + offset in writes for offset in range(aes.WORD_BYTES))]
    staged = {word: bytes(final[word:word + aes.WORD_BYTES]) for word in words}
    return merge_pokes(machine, staged), words, by_itself


# THE CENSUS OF WHAT DIFFERS BY NATURE, by layer and by kind: `{the routine's core: its rows}` that settle each word
# beyond the two every layer always had (the Line-F mask word, spl7_save's SR word), that leave a QPB's address in a
# freed EVB, or whose run moved `savptr` WITHOUT its layer saying the routine polls. The one registrar settles
# whatever a row's ROM run stores, with no ruling — so a row that NEWLY reaches psetup's or the dispatcher's bracket,
# takes a BIOS trap or leaves a QPB's address is staged and dropped in silence unless something says so: this
# table. A new member reds here until it is written in, with the reason it is right.
A_QPB_S_ADDRESS, SAVPTR_MOVED_BY_THE_RUN = "a QPB's address left in a freed EVB", "savptr moved by the run alone"
THE_ROWS_THAT_SWITCH = "the rows that switch"
THE_CALLER_S_CONTEXT, THE_DISPATCHER_S_STACK = "the caller's saved context", "the dispatcher's stack"
THE_BRACKET_S_SAVE_WORD = "spl7_save's SR save word"
# The registered rows that switch, by routine: the waits' leaf entries (the pilots among them), ev_multi's 45 (29
# woken by an interrupt, 13 through the menu chain, 1 a key before the writer writes, 2 a key at a poll that is no
# idle) and THE DOOR USERS' — each routine's wait that blocks, woken through the dispatcher (mn_do's three shapes,
# fm_do's, gr_watchbox's and fm_alert's two each; fs_input's five are the SLICES of its two sessions the user is
# waited for in, each slice a row).
ROWS_THAT_SWITCH = {
    "aes_ap_rdwr": 2, "aes_ev_block": 12, "aes_ev_button": 2, "aes_ev_keybd": 1, "aes_ev_mesag": 1, "aes_ev_mouse": 1,
    "aes_ev_multi": 45, "aes_ev_mwait": 3, "aes_ev_timer": 4, "aes_unsync": 1,
    "aes_ap_sendmsg": 1, "aes_fm_button": 1, "aes_fm_do": 2, "aes_gr_dragbox": 1, "aes_gr_rubbox": 1, "aes_gr_slidebox": 1,
    "aes_gr_stilldn": 1, "aes_gr_wait": 1, "aes_gr_watchbox": 2, "aes_mn_do": 3, "aes_wm_update": 1,
    "aes_fm_alert": 2, "aes_fs_input": 5,
    "aes_ap_tplay": 8, "aes_ap_trecd": 6,
}
BY_NATURE_CENSUS = {
    # No wait's row reaches psetup's or the dispatcher's bracket, takes a trap or leaves a QPB's address.
    "the waits": {},
    # mchange's one row over a recording played back: drawrat's cursor routine samples the locator (vq_mouse, a
    # `trap #2` whose BIOS save moves savptr) — the layer names chkkbd and forker as the routines that poll, not it.
    "the input": {SAVPTR_MOVED_BY_THE_RUN: {"aes_mchange": 1}},
    # psetup's own row and pstart's (which calls it): the bracket is the routine under test.
    "the processes and pipes": {"psetup's SR save word": {"aes_psetup": 1, "aes_pstart": 1}},
    # The two rows whose message wait is queued and cancelled: the only runs of the wait path's QPB, a local of the
    # routine's own frame handed on by its address (`test_aes_evmulti.ROWS`).
    "ev_multi": {A_QPB_S_ADDRESS: {"aes_ev_multi": 2}},
    # THE ROWS THAT SWITCH (`aes_switching.register`; a layer of its own: its rows are settled from a run through the
    # dispatcher, which no unwatched run of the oracle makes — `test_every_row_that_switches_…`, below). Every one
    # drops the caller's saved context and the dispatcher's stack (that is what a switch is: `ROWS_THAT_SWITCH`, by
    # routine). The wider kinds:
    #   * THE MASK BRACKET'S SAVE WORD — a call that waits on a time, whose wait (adelay) and whose fork function
    #     (tchange) bracket in C: ev_block's delay, ev_timer's four, every ev_multi that asks MU_TIMER (19 of its 45);
    #   * A QPB'S ADDRESS LEFT IN A FREED EVB — a wait on a pipe, woken or cancelled: ap_rdwr's read and write (the
    #     QPB its own arguments), ev_mesag's, ap_sendmsg's write to a full pipe (ap_rdwr's twin under a door user),
    #     and every ev_multi that asks MU_MESAG (27: a local of its own frame), each vetted on every shore.
    # No DOOR USER's row drops a bracket's word: none of them waits on a time, and no tick reaches tchange's
    # bracket on a path that does not wait.
    THE_ROWS_THAT_SWITCH: {THE_CALLER_S_CONTEXT: ROWS_THAT_SWITCH, THE_DISPATCHER_S_STACK: ROWS_THAT_SWITCH,
                           THE_BRACKET_S_SAVE_WORD: {"aes_ap_tplay": 4, "aes_ap_trecd": 6, "aes_ev_block": 1, "aes_ev_multi": 19,
                                                     "aes_ev_timer": 4},
                           A_QPB_S_ADDRESS: {"aes_ap_rdwr": 2, "aes_ap_sendmsg": 1, "aes_ev_mesag": 1, "aes_ev_multi": 27}},
}


@pytest.mark.parametrize("layer", SETTLED_ROWS)
def test_every_row_a_layer_registers_is_staged_and_dropped_as_the_rom_s_own_run_says(layer, monkeypatch):
    """ONE SETTLING, for the waits', the input's, the processes-and-pipes' and ev_multi's rows alike (each layer had a spelling of
    its own: five of the waits' and the input's 111 arrivals differed between two of them, and the pipes' asked
    after psetup's SR word alone): EVERY priced direct row a layer registers holds, IN THE REGISTRY, the machine the
    ROM's own run of it settles — HELD TO AN INDEPENDENT SPELLING (`_settled_by_the_rom_s_own_run`: the oracle's run,
    not the kept derivation the registrar reads; the registry was compared with the very function the registrar
    calls, which held "no layer bypasses it" and nothing of what it stages) — and drops exactly those words, whole
    (a QPB's address a returning wait leaves apart: `register_row`'s own, vetted). No code address is among the drops
    (a queued or a recorded fork function's is relocated at Tier 3, never dropped). AND THE CENSUS: which routines'
    rows use each of the wider kinds is the table above, exactly."""
    rows = SETTLED_ROWS[layer](monkeypatch)
    assert len({row.name for row in rows}) >= ROUTINES_A_LAYER_SETTLES[layer], "the premise: the layer's rows, not a few"
    registered, reasons, census = case.tier3_dropped(), set(), {}

    def counted(kind, row):
        census.setdefault(kind, collections.Counter())[routines.core_symbol(row.name)] += 1
    for row in rows:
        name = f"{routines.core_symbol(row.name)}, {row.label}"
        pokes, words, moved_by_itself = _settled_by_the_rom_s_own_run(row)
        in_the_registry = case.registered_case(name)
        assert make_image(in_the_registry[3]) == make_image(aes.staged(row.name, row.arguments, pokes)), name
        drops = registered.get(name, ())
        but_a_qpb_s_address = tuple(drop for drop in drops if drop[2] != aes_event.QPB_ADDRESS_WHY)
        expected = tuple(window for word, drop in aes_event.WORDS_BY_NATURE if word in words for window in drop)
        assert but_a_qpb_s_address == expected, name
        reasons |= {why for _lo, _hi, why in but_a_qpb_s_address}
        for word in words:
            if word not in ALWAYS_SETTLED:
                counted(aes_event.SR_DROPS[word].split(":")[0], row)
        if len(but_a_qpb_s_address) != len(drops):
            counted(A_QPB_S_ADDRESS, row)
        if moved_by_itself:
            counted(SAVPTR_MOVED_BY_THE_RUN, row)
    assert reasons & set(aes_event.SR_DROPS.values()), "each layer has a row under a status-register bracket"
    assert not [why for why in reasons if "fork" in why or "record" in why], "a code address is relocated, never dropped"
    census = {kind: dict(sorted(counts.items())) for kind, counts in census.items()}
    assert census == BY_NATURE_CENSUS[layer], (
        f"{layer}: the rows that settle a wider kind are {census} — a row NEWLY under a bracket, a trap or a QPB is "
        f"settled with no ruling: write it into BY_NATURE_CENSUS with the reason it is right")


# THE ONE DROP OF A KIND ITS RUN DOES NOT CHANGE: the timer behind three delays pending is queued over a machine the
# ROM's own iasync made — three delays queued, each under spl7's bracket, which left its save word as this row's own
# bracket stores it again: stored (so dropped: our build parks GCC's condition codes there), and equal.
# ...AND EVERY PLAYBACK OF A TIMER RECORD (appl_tplay: `aes_aptape`): its machine is the one the ROM's own appl_trecord
# left, whose last bracket (ap_trecd's own, disarming the recorder) parked the word the playback's adelay and tchange
# park again.
STORED_WITH_THE_VALUE_THE_MACHINE_HOLDS = {
    ("aes_ev_timer, behind three delays pending, blocked; run out a delay at a time", THE_BRACKET_S_SAVE_WORD),
    ("aes_ap_tplay, four records played: two moves, a wait, a press", THE_BRACKET_S_SAVE_WORD),
    ("aes_ap_tplay, four records played slowly: the wait is twenty-five ticks", THE_BRACKET_S_SAVE_WORD),
    ("aes_ap_tplay, a wait and a press played: no mouse record", THE_BRACKET_S_SAVE_WORD),
    ("aes_ap_tplay, four records played, the cursor shown: the VDI's cursor routine queues each point", THE_BRACKET_S_SAVE_WORD),
}


def test_every_row_that_switches_drops_what_its_own_scheduled_run_changes_and_the_census_says_which():
    """THE SWITCHING ROWS' LAYER OF THE ONE CENSUS, held to AN INDEPENDENT SPELLING of its own kind: the ROM's
    scheduled run of each registered row over its UNSETTLED machine (`aes_switch.scheduled` — not the registrar's
    kept derivation, nor its replay's ledger) and what that run CHANGED in the windows that differ by nature. Every
    such byte lies in a drop the registry holds for the row — but the dispatcher's own save word, which both builds
    park alike and the row compares — every drop holds one, and which routines' rows drop which kind is the table's.
    A QPB'S ADDRESS LEFT IN A FREED EVB is a kind of its own (`aes_switching.settled(row).qpbs`: a wait on a pipe
    that blocked and was woken, or was cancelled): no window but ONE LONGWORD, an EVB's parameter that holds a
    stack-band address when that run ends — and every such longword the run CHANGED is dropped."""
    import aes_switch
    import aes_switching
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    registered, census = case.tier3_dropped(), {}
    assert aes_event.SWITCHING_ROWS, "the premise: the batteries register rows that switch"
    for name, held in aes_event.SWITCHING_ROWS.items():
        row = held.row
        staged = aes.staged(row.name, row.arguments, merge_pokes(row.machine(), aes_event.savptr_in_the_band()))
        the_rom_s = aes_switching.scheduled(row, staged)
        uda = aes_event.uda_of(held.switches.process, the_rom_s.memory)
        kinds = {THE_CALLER_S_CONTEXT: aes_switch.uda_context_drop(uda), THE_DISPATCHER_S_STACK: aes_switch.DISPATCHER_STACK_DROP,
                 THE_BRACKET_S_SAVE_WORD: aes_event.sr_drops(aes.AES_SR_SPL), "psetup's SR save word": aes_event.SR_PSETUP_DROP}
        qpb_addresses = _the_qpb_addresses_dropped(name, registered[name], the_rom_s)
        drops = [(lo, hi) for lo, hi, why in registered[name]
                 if (lo, hi, why) not in aes.LINE_F_MASK_WINDOW and lo not in qpb_addresses]
        if qpb_addresses:
            census.setdefault(A_QPB_S_ADDRESS, collections.Counter())[routines.core_symbol(row.name)] += 1
        of_a_kind = []
        for kind, ((lo, hi, _why),) in kinds.items():
            changed = [at for at in range(lo, hi) if the_rom_s.memory[at] != the_rom_s.started[at]]
            inside = [(low, high) for low, high in drops if lo <= low and high <= hi]
            assert all(any(low <= at < high for low, high in inside) for at in changed), f"{name}: {kind} changed and not dropped"
            # ...AND THE OTHER WAY: a kind is dropped only where the run CHANGES something of it — on every row and
            # every kind but ONE NAMED PAIR, which the run STORES with the value its ROM-made machine already holds
            # (held as that: dropped, and changed nowhere). A row drops what the run STORED — the kit's own rule, on
            # every measurement (`rom_bench.vet_dropped`) — so a second such pair is a finding to name here, not a
            # reason to stop asking.
            if (name, kind) in STORED_WITH_THE_VALUE_THE_MACHINE_HOLDS:
                assert inside and not changed, f"{name}: {kind} is no longer stored unchanged — the exemption is stale"
            else:
                assert bool(inside) == bool(changed), f"{name}: a drop of {kind}, of which the ROM's run changes nothing"
            of_a_kind += inside
            if inside:
                census.setdefault(kind, collections.Counter())[routines.core_symbol(row.name)] += 1
        assert sorted(of_a_kind) == sorted(drops), f"{name}: a drop of no kind this census knows"
    census = {kind: dict(sorted(counts.items())) for kind, counts in census.items()}
    assert census == BY_NATURE_CENSUS[THE_ROWS_THAT_SWITCH], (
        f"the rows that switch drop {census} — a row NEWLY under a bracket is dropped with no ruling: write it into "
        f"BY_NATURE_CENSUS with the reason it is right")


def _the_qpb_addresses_dropped(name, drops, the_rom_s):
    """Where the switching row `name` drops A QPB'S ADDRESS (`aes_event.QPB_ADDRESS_WHY`), held to its own kind over
    the ROM's scheduled run `the_rom_s`: each drop one EVB's parameter, whole, holding a stack-band address as the
    run ends — and no parameter the run CHANGED to such an address left undropped."""
    dropped = {lo: hi for lo, hi, why in drops if why == aes_event.QPB_ADDRESS_WHY}
    parameters = {evb + aes.EVB_PARM for evb in aes_event.EVBS}

    def names_the_stack(at):
        return case.long_in(the_rom_s.memory, at) & aes.OS_BUS_ADDR_MASK in case.STACK_BAND
    assert all(at in parameters and hi - at == aes.LONG_BYTES and names_the_stack(at) for at, hi in dropped.items()), (
        f"{name}: a QPB's address dropped where no EVB's parameter holds a stack address")
    changed = {at for at in parameters if names_the_stack(at)
               and the_rom_s.memory[at:at + aes.LONG_BYTES] != the_rom_s.started[at:at + aes.LONG_BYTES]}
    assert changed <= dropped.keys(), f"{name}: a QPB's address left in an EVB and not dropped: {sorted(map(hex, changed))}"
    return frozenset(dropped)


ALWAYS_SETTLED = (aes.AES_LINEF_MASK_WORD, aes.AES_SR_SPL)


def test_a_routine_that_polls_has_savptr_in_the_band_whether_its_run_polls_or_not():
    """...and what `polls` says: the machine is the row's with `savptr` in the stack band, for a run that takes the
    trap and for one that does not — the five rows the two spellings differed on."""
    quiet = [arrival for arrival in _every_returning_arrival(aes_evinput) if arrival.name in THE_ROUTINES_THAT_POLL
             and addrs.SYSVAR_SAVPTR not in aes_event._stored_where_a_row_settles(
                 arrival.name, tuple(arrival.arguments), merge_pokes(arrival.machine, aes_event.savptr_in_the_band()))]
    assert quiet, "the premise: a row of chkkbd's or forker's whose run takes no trap"
    for arrival in quiet:
        told, _drops = aes_event.settled(arrival.name, arrival.arguments, arrival.machine, polls=True)
        untold, _drops = aes_event.settled(arrival.name, arrival.arguments, arrival.machine)
        band = aes_event.savptr_in_the_band()[addrs.SYSVAR_SAVPTR]
        assert bytes(make_image(told)[addrs.SYSVAR_SAVPTR:addrs.SYSVAR_SAVPTR + aes.LONG_BYTES]) == band
        assert make_image(untold) != make_image(told), "untold, the run alone decides: `savptr` stays the snapshot's"


# ---- THE ZYGOTE'S LATENT DEFECTS, each shown RED on the mechanism before any case met it -----------------------------------
A_FRACTION_OF_A_SECOND = 2.5


def test_a_fork_given_a_fraction_of_a_second_is_bounded_by_it_and_says_why_it_ends():
    """RED: `signal.alarm` takes whole seconds — a fork given 2.5 raised a TypeError as its first act, before its
    stderr was its pipe: FORK_RAISED with NO REASON (a door user's child asked of the zygote with `seconds=2.5`). The
    interval timer takes the fraction: the fork runs, and one that outlives it is ended by SIGALRM."""
    assert aes_event.in_a_fork(lambda: None, seconds=A_FRACTION_OF_A_SECOND) == (0, "")
    returncode, _stderr = aes_event.in_a_fork(lambda: time.sleep(A_FRACTION_OF_A_SECOND), seconds=A_FRACTION_OF_A_SECOND / 10)
    assert returncode == -signal.SIGALRM


def test_a_hook_takes_one_name_and_a_second_declaration_of_it_is_refused():
    """RED: a second `named_hook` of one object silently took the name — the zygote then resolved "module:attribute"
    of a module that never bound the hook. One name per hook; the same name again is no second declaration."""
    named = aes_event.EVENT_LAYER_HOOKS
    assert aes_event.named_hook("aes_event", "EVENT_LAYER_HOOKS", named) is named
    with pytest.raises(AssertionError, match="declared already, as aes_event:EVENT_LAYER_HOOKS — one name per hook"):
        aes_event.named_hook(__name__, "ANOTHER_NAME_FOR_IT", named)
    assert aes_event.name_of_a_hook(named) == "aes_event:EVENT_LAYER_HOOKS"


A_MODULE_NO_ZYGOTE_HOLDS = "a_battery_s_helper_module_nobody_wrote"


def test_the_zygote_imports_nothing_for_a_hook_and_one_named_in_a_battery_is_the_worker_s_own(a_zygote_runs):
    """RED: a hook NAMED in a battery's helper module made the zygote IMPORT the battery (10 MB to 214 MB, measured —
    every later fork of it paying the copy). A named hook's module must be one the zygote holds ALREADY: its side
    refuses by name and imports nothing; the worker's side never asks it — the hook is served by the worker's own
    forks, as an unnamed one is."""
    assert "aes_event" in aes_event.ZYGOTE_HOLDS and __name__ not in aes_event.ZYGOTE_HOLDS
    assert A_MODULE_NO_ZYGOTE_HOLDS not in sys.modules, "the premise"
    with pytest.raises(AssertionError, match="the zygote imports nothing for a hook"):
        aes_event.hook_named(f"{A_MODULE_NO_ZYGOTE_HOLDS}:whatever")
    assert A_MODULE_NO_ZYGOTE_HOLDS not in sys.modules, "...and nothing was imported to find that out"
    a_battery_s_own = aes_event.named_hook(__name__, "A_BATTERY_S_OWN_HOOK", aes.doors(aes_event.vdi_hook))
    try:
        assert aes_event.name_of_a_hook(a_battery_s_own) == f"{__name__}:A_BATTERY_S_OWN_HOOK"
        assert not aes_event.the_zygote_stands_in(_tak_flag_run(), aes_event.SERVED_IN_A_FORK, a_battery_s_own)
        assert aes_event.the_zygote_stands_in(_tak_flag_run(), aes_event.SERVED_IN_A_FORK, aes_event.EVENT_LAYER_HOOKS)
    finally:
        del aes_event._NAMED_HOOKS[id(a_battery_s_own)]


def test_a_request_s_types_are_its_own_and_leave_the_library_s_function_as_it_was():
    """RED: the zygote typed `_lib.<symbol>` ITSELF for each request — the one function object the library keeps —
    so a request's restype and argtypes were every later fork's. Each request types a function object of its own."""
    symbol = routines.core_symbol("AES_ROM_TAK_FLAG")
    kept = getattr(aes_event._lib, symbol)
    before = (kept.restype, None if kept.argtypes is None else tuple(kept.argtypes))
    typed = aes_event._typed_core(symbol, "c_uint32", ("POINTER:c_uint8", "c_uint16"))
    assert typed is not kept and typed.restype is ctypes.c_uint32 and len(typed.argtypes) == 2
    assert (kept.restype, None if kept.argtypes is None else tuple(kept.argtypes)) == before
    assert ctypes.cast(typed, ctypes.c_void_p).value == ctypes.cast(kept, ctypes.c_void_p).value, "the same function"


def test_a_value_rebound_without_the_monkeypatch_fixture_sidelines_the_zygote_too(a_zygote_runs):
    """RED: the suite sidelines the zygote for a test that takes `monkeypatch` — and a value rebound ANY OTHER WAY (a
    mock's patch, an assignment and a `finally`) split the two makers silently: the worker's fork ran under the
    patch (FORK_RAISED), the zygote's without it (0). The zygote stands in only while the modules it froze hold the
    very values it was forked with."""
    aes_event.ZYGOTE_SIDELINED = False      # the module's own value, as a test with no `monkeypatch` finds it (the
    #                                         fixture's own patch of it is undone when this test ends)
    assert aes_event.the_zygote_runs() and aes_event.the_zygote_stands_in(_tak_flag_run())
    made, real = aes_event.FORKS_MADE[aes_event.BY_THIS_PROCESS], aes_event.one_run_of

    def raising(*_run):
        raise RuntimeError("patched, with no fixture")
    aes_event.one_run_of = raising
    try:
        assert not aes_event.the_zygote_runs() and not aes_event.the_zygote_stands_in(_tak_flag_run())
        with pytest.raises(RuntimeError, match="patched, with no fixture"):
            aes_event.core_in_a_fork("AES_ROM_TAK_FLAG", THE_LOCK, aes_event.machine())
        assert aes_event.FORKS_MADE[aes_event.BY_THIS_PROCESS] == made, "the patched code ran HERE: no fork of another maker's"
    finally:
        aes_event.one_run_of = real
    assert aes_event.the_zygote_runs(), "...and put back, the zygote stands in again"
    another, real_value = aes.signed, aes.signed
    aes.signed = lambda value: another(value)
    try:
        assert not aes_event.the_zygote_runs(), "a value of ANY module a fork's behaviour is read off"
    finally:
        aes.signed = real_value


A_FROZEN_MODULE = "a_module_the_zygote_froze"


def test_a_lazy_cache_is_frozen_by_its_shape_none_to_its_first_value_and_no_further(monkeypatch):
    """THE EXEMPTION IS BY SHAPE, and held WITHOUT a zygote (its only pin skipped with the zygote off: the fix
    reverted was invisible there). RED while the cache was exempt BY NAME: a lazy cache bound from None is what the
    zygote froze; the SAME name bound AGAIN to another object (`mock.patch` of the blob, a sweep's own bench put
    back in a `finally`) is a value rebound — the worker's fork would run one bench and the zygote's another."""
    module = types.ModuleType(A_FROZEN_MODULE)
    module._CACHE, module.A_VALUE = None, object()
    monkeypatch.setitem(sys.modules, A_FROZEN_MODULE, module)
    monkeypatch.setattr(aes_event, "LAZY_CACHES", {A_FROZEN_MODULE: frozenset({"_CACHE"})})
    monkeypatch.setattr(aes_event, "_FROZEN", {A_FROZEN_MODULE: aes_event._values_of(A_FROZEN_MODULE)})
    monkeypatch.setattr(aes_event, "_FIRST_BOUND", {})
    assert aes_event._as_the_zygote_froze_them()
    first, second = object(), object()
    module._CACHE = first
    assert aes_event._as_the_zygote_froze_them(), "bound from None by its first asker: the cache's own transition"
    assert aes_event._as_the_zygote_froze_them() and aes_event._FIRST_BOUND == {(A_FROZEN_MODULE, "_CACHE"): first}
    module._CACHE = second
    assert not aes_event._as_the_zygote_froze_them(), "bound AGAIN: a value rebound, as any other"
    module._CACHE = first
    assert aes_event._as_the_zygote_froze_them()
    module._CACHE = None
    assert aes_event._as_the_zygote_froze_them(), "back at what the zygote froze"
    module._CACHE, module.A_VALUE = first, object()
    assert not aes_event._as_the_zygote_froze_them(), "...and a value that is no lazy cache, rebound"
    monkeypatch.undo()
    assert aes_event.LAZY_CACHES == {"isr": frozenset({"_BENCH"})}, "the one lazy cache of the frozen modules today"


def test_a_lazy_cache_bound_since_the_zygote_was_forked_does_not_sideline_it(a_zygote_runs):
    """RED: `isr.blob()` binds the module's lazy `_BENCH` (None when the zygote was forked) — a "value rebound" by
    the rule above, so the first test of a process that loaded the cross-compiled blob (every transcription pin
    does) put its zygote out of use FOR THE REST OF ITS LIFE: measured, one battery's 1,066 forks the worker's own
    again after one test of another's. A lazy cache is frozen by its shape (`LAZY_CACHES`): with the blob loaded, the
    frozen modules hold what the zygote froze, and it stands in."""
    aes_event.ZYGOTE_SIDELINED = False      # the module's own value (the fixture's patch of it is undone as this ends)
    isr.blob()
    assert isr._BENCH is not None and "_BENCH" in aes_event.LAZY_CACHES["isr"]
    assert aes_event._as_the_zygote_froze_them(), "a name of a frozen module is bound to another object than the zygote froze"
    assert aes_event.the_zygote_runs() and aes_event.the_zygote_stands_in(_tak_flag_run())


# ---- A DOOR USER'S CALL THAT BLOCKS, TAKEN ON THROUGH THE WAKE (`aes_event.woken_row`, `aes_switch`) ------------------------
# The machinery, each piece on the smallest case that shows it: gr_stilldn waiting (the button down) for the mouse
# to leave the rectangle it is in — one door call, which blocks — and gr_watchbox, whose loop takes an interrupt at a
# wait's ENTRY before the wait that blocks.
def _switch():
    """`aes_switch` and the registrar, asked for where a case needs them (the door's own tests import no battery's
    helper at this module's import)."""
    import aes_switch
    import aes_switching
    return aes_switch, aes_switching


THE_WAIT_TO_LEAVE = ("AES_ROM_GR_STILLDN", (grwait.LEAVE, *grwait.AROUND_THE_MOUSE))
A_WATCHED_OBJECT = ("AES_ROM_GR_WATCHBOX", (grwait.SELECTOR, grwait.OK, grwait.SELECTED, grwait.CROSSED))


def _scheduled(call, at_idle, at_calls=None, machine=None):
    """The ROM's own run of `call` (`(name, arguments)`) through its dispatcher, over the button down."""
    aes_switch, _switching = _switch()
    name, arguments = call
    staged = aes.staged(name, arguments, merge_pokes(machine or grwait.button_down(), aes_event.savptr_in_the_band()))
    return aes_switch.scheduled(getattr(addrs, name), staged[abi.FIRST_ARG], staged, at_idle, at_calls=at_calls), staged


def _modelled(call, the_rom_s, staged, *, door=True, objects=False):
    """The C of `call` through the host's model over `staged`, held to `the_rom_s` — a door user's child (the walked
    routines served with `objects`), or with `door` False a leaf's, which binds no door."""
    aes_switch, _switching = _switch()
    name, arguments = call
    return aes_switch.modelled(routines.core_symbol(name), vdi.as_signed(name, arguments), staged, the_rom_s,
                               door=aes_switch.DoorUser(objects) if door else None)


def test_one_derivation_takes_interrupts_at_door_calls_and_at_idles():
    """`aes_switch.scheduled` WITH A DOOR WATCH INSIDE: gr_watchbox's second wait takes the mouse's move AT ITS ENTRY
    (a door call's delivery), its third BLOCKS and the button's rise is taken AT THE IDLE — one run of the ROM, which
    returns. What it took at the door call is what the door's own derivation takes there (`aes_event.deliveries`:
    the same bytes found, the same written), and the calls it was handed are the replay's."""
    aes_switch, _switching = _switch()
    inside = aes_event.move_to(*grwait.the_middle_of(grwait.OK))
    the_rom_s, staged = _scheduled(A_WATCHED_OBJECT, {0: aes_event.release}, {1: inside})
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (aes_switch.RETURNED, 1, (aes.SHELL_PD,))
    assert sorted(the_rom_s.delivered) == [0] and sorted(the_rom_s.at_calls) == [1] and len(the_rom_s.calls) == 3
    name, arguments = A_WATCHED_OBJECT
    assert the_rom_s.at_calls == aes_event.deliveries(name, arguments, merge_pokes(grwait.button_down(), aes_event.savptr_in_the_band()),
                                                      {1: inside})
    calls, _delivered, _memory, result = aes_event.rom_interrupted(name, arguments, staged, {1: inside})
    assert result is None and tuple(calls) == the_rom_s.calls, "up to the block, the door's own watched run of it"


def test_a_delivery_named_at_a_door_call_the_scheduled_run_never_makes_is_refused_by_name():
    """...and one named at a door call the run never reaches — never laid, and nothing else would say so."""
    with pytest.raises(AssertionError, match=r"made 2 door call\(s\): nothing was delivered at \[7\]"):
        _scheduled(A_WATCHED_OBJECT, {0: aes_event.release}, {7: aes_event.release})
    with pytest.raises(AssertionError, match="idles for ever AFTER its deliveries"):
        _scheduled(A_WATCHED_OBJECT, {}, {1: aes_event.move_to(*grwait.the_middle_of(grwait.OK))})


def test_the_door_watch_of_a_scheduled_run_is_the_caller_s_process_s_alone(monkeypatch):
    """THE DOOR CALLS OF ANOTHER PROCESS ARE NOT THE ROW'S: the desk's wait for a key during which THE SCREEN MANAGER
    runs (the mouse onto the bar, then Return) — entered at ev_block, the desk makes no door call. RED: the watch
    left armed while the screen manager runs counts ITS evnt_multi and its screen lock, made from the very return
    addresses a caller's calls come from, as door calls of the run."""
    aes_switch, _switching = _switch()
    frame = aes_event.frame_of(("w", aes_event.EVWAIT["IASYNC_KEYBOARD"]), ("l", 0))
    through_the_manager = {0: aes_event.move_to(*aes_event.MENU_BAR_POINT), 1: aes_event.key(aes_event.RETURN_KEY)}
    the_rom_s = aes_switch.scheduled(addrs.AES_ROM_EV_BLOCK, frame, aes_event.machine(), through_the_manager)
    assert the_rom_s.entered == (aes.SCREEN_MANAGER_PD, aes.SHELL_PD) and the_rom_s.calls == ()
    monkeypatch.setattr(aes_switch._Idling, "_entered", lambda self, pd: self.entered.append(pd))
    armed_throughout = aes_switch.scheduled(addrs.AES_ROM_EV_BLOCK, frame, aes_event.machine(), through_the_manager)
    assert {call.routine for call in armed_throughout.calls} >= {addrs.AES_ROM_EV_MULTI}


def test_a_door_user_under_the_model_binds_the_door_and_the_scheduler_in_one_child():
    """THE DOOR CHILD UNDER THE MODEL (`aes_switch.modelled`'s `door`): the user's wrapper call is an ARRIVAL (noted,
    shadowed), its twin blocks, the dispatcher's hook holds it to its shadow and THEN RUNS THE C SCHEDULER — the
    rise is laid at the idle, the call comes back and the user returns: 0 (it rose), one frame handed, the ROM's.
    WITHOUT the door (a leaf's binding) the same C ends at the wrapper's hook, refused by name: that is what the
    companion of a door user could not be."""
    the_rom_s, staged = _scheduled(THE_WAIT_TO_LEAVE, {0: aes_event.release})
    ran = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert (ran.returncode, ran.answer, ran.idles) == (0, grwait.RISEN, 1), ran.stderr
    assert tuple(ran.handed) == the_rom_s.calls and len(ran.handed) == 1
    aes_switch, _switching = _switch()
    assert not aes_event.differing(ran.image, the_rom_s.memory,
                                   aes_switch.not_compared(the_rom_s, aes_switch.model_drops(aes.SHELL_PD)))
    unbound = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged, door=False)
    assert unbound.returncode == aes_event.FORK_REACHED_A_HOOK and aes_event.HOOK_SYMBOL in unbound.stderr


def test_a_twin_that_is_not_its_shadow_at_dsptch_ends_the_child_before_the_model_runs_on(monkeypatch):
    """THE SHADOW IS STILL HELD AT DSPTCH UNDER THE MODEL — before the scheduler runs, so a twin that went wrong up to
    the block is named THERE, not at the end of a run that carried on over its image. RED: the shadow's own image one
    byte off where the call arrives (as a twin that stored a byte the ROM's routine does not): the child ends with
    the shadow's status and its words, and the model never ran (no idle counted)."""
    the_rom_s, staged = _scheduled(THE_WAIT_TO_LEAVE, {0: aes_event.release})
    shadow_of = aes_event.shadow_of

    def one_byte_off(call, image, frame, io_seed=None):
        astray = bytearray(image)
        astray[aes_event.UNREAD_BYTE] ^= 1
        return shadow_of(call, bytes(astray), frame, io_seed)
    monkeypatch.setattr(aes_event, "shadow_of", one_byte_off)
    ran = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert ran.returncode == aes_event.CHILD_SHADOW_REFUSED and ran.idles is None
    assert "the shadow: the twin of" in ran.stderr and "holds at the dispatcher another image" in ran.stderr


def test_a_shadow_held_at_dsptch_says_nothing_of_the_twin_s_return_nor_of_a_second_dispatch():
    """...AND ONCE HELD THERE THE SHADOW HAS SAID ALL IT CAN (`HELD_AT_THE_DISPATCHER`): its nested run ended at
    dsptch, so neither the twin's RETURN after the wake nor a second dispatch of the same call is asked of it. RED,
    on the two effects themselves: the place left as the shadow, the return is refused "returned where the ROM's
    routine … reaches the dispatcher" — every woken door user would end there."""
    routine, image = addrs.AES_ROM_EV_MULTI, _an_image_buffer()
    blocked = aes_event.Shadow(aes_event.Handed(routine, ()), bytes(aes_event.IMAGE_BYTES),
                               aes_event.Nested({}, 0, 1, aes_event.BLOCKS))
    with pytest.raises(AssertionError, match="returned where the ROM's routine, run over the image the call arrived with, "
                                             "reaches the dispatcher"):
        aes_event._returned(routine, [blocked])(image, 0)
    assert aes_event.HELD_AT_THE_DISPATCHER != aes_event.NOT_SHADOWED, "two places, told apart by value"
    assert blocked not in aes_event._NOT_COMPARED_AGAIN
    held = [aes_event.HELD_AT_THE_DISPATCHER]
    aes_event._vet_the_twin_at_the_dispatcher(held, bytes(aes_event.IMAGE_BYTES))
    aes_event._returned(routine, held)(image, 0)
    assert held == [], "the arrival's place given up, as any twin's return gives it up"


def test_a_door_user_s_companion_holds_the_frames_it_handed_the_door(monkeypatch):
    """THE FRAMES ARE COMPARED ON THE WOKEN ROAD TOO (`aes_switching.companion`): the C's run handed back as one that
    made a door call fewer, over the very image and answer the ROM's run leaves, is refused by name."""
    aes_switch, _switching = _switch()
    modelled = aes_switch.modelled
    monkeypatch.setattr(aes_switch, "modelled",
                        lambda *run, **named: (lambda ran: ran._replace(handed=ran.handed[:-1]))(modelled(*run, **named)))
    with pytest.raises(AssertionError, match="the door was handed .*, the ROM's run hands"):
        aes_event.held_through_its_wake(grwait.watched(grwait.OK, "a frame fewer", {0: aes_event.release}))


def test_a_call_whose_wait_blocks_for_nothing_delivered_is_what_blocked_then_woken_holds_first():
    """`blocked_then_woken`'s PREMISE: the same call with nothing delivered at an idle BLOCKS. A row whose call
    returns by itself (the button up: the rise is answered at once) is refused by name — it has no blocked half."""
    returns = aes_event.woken_row("the button up", "AES_ROM_GR_STILLDN", (grwait.LEAVE, *grwait.AROUND_THE_MOUSE),
                                  grwait.running, {})
    with pytest.raises(AssertionError, match="the premise — with nothing delivered at an idle the call switches"):
        aes_event.blocked_then_woken(returns)


# ---- THE HOST'S MODEL, WHERE ANOTHER PROCESS RUNS INSIDE A DOOR USER'S WAIT -------------------------------------------------
def _mn_do_across_the_desk_s_turn():
    mnlib = _mnlib()
    return mnlib.mn_do_woken_row(mnlib.THE_DESK_S_TURN)


def test_a_foreign_turn_is_not_laid_back_over_the_bytes_no_c_of_ours_stores(monkeypatch):
    """`aes_switch.STORED_BY_NO_C`: mn_do blocked on the bar, THE DESK'S TURN, and then mn_do blocks twice more. The
    ROM's own dispatcher goes on overwriting its stack in every later dispatch of the screen manager; the host's C
    stores nothing there. RED: the desk's nested ROM run laid back whole (as it was), the image holds in the
    dispatcher's stack what that turn left and differs from the ROM's run — on no fault of the C."""
    row = _mn_do_across_the_desk_s_turn()
    ran = aes_event.held_through_its_wake(row)
    assert aes.SHELL_PD in ran.entered and ran.entered.count(aes.SCREEN_MANAGER_PD) >= 2, "the premise: blocked again after the turn"
    aes_switch, _switching = _switch()
    monkeypatch.setattr(aes_switch, "STORED_BY_NO_C", ())
    lo, hi = aes_switch.DISPATCHER_STACK
    with pytest.raises(AssertionError, match="bytes differ from the ROM's run") as differs:
        aes_event.held_through_its_wake(row)
    addresses = [int(at, 16) for at in re.findall(r"(0x[0-9a-f]+) oracle=", str(differs.value))]
    assert addresses and all(lo <= at < hi for at in addresses), "...and nowhere but in the dispatcher's own stack"


# ---- THE HOST SLOTS A DOOR USER HOLDS ACROSS A WAIT (`aes_switch.host_slots_held`) -----------------------------------------
# THE AUDIT, read off the runs: for each door user's registered row that switches, the host slots its routines held
# WHERE THE PROCESS WAS PARKED. Every one is a frame local whose address the routine handed the event layer (its
# answer words, a MOBLK) or goes on with after the wait (a GRECT, its frame). ONE is a slot per process today —
# ap_rdwr's QPB, which another process's read serves through its address. THE OTHERS ARE ONE FRAME FOR EVERY
# PROCESS, AND THAT IS SOUND ONLY WHILE ONE C PROCESS CAN BE INSIDE THE ROUTINE: in wave 3 the caller is the run's
# only C process (every other is the ROM's own code, which claims no slot). The day a second process is C (band 5:
# the screen manager's ctlmgr) each of these owes a frame per process, as the two QPBs have — a new slot held across
# a wait reds here until it is written in.
STILLDN_S = ("AES_GR_STILLDN_RECTANGLE", "AES_GR_STILLDN_ANSWERS")
# fm_alert parks under fm_do's wait and, a button pressed, under fm_button's watch of it; fs_input under fm_do's.
FM_ALERT_S = ("AES_FM_DO_FRAME", "AES_FM_ALERT_FRAME", *STILLDN_S, "AES_GR_WATCHBOX_RECT", "AES_FM_BUTTON_FRAME")
FS_INPUT_S = ("AES_FM_DO_FRAME", "AES_FS_INPUT_FRAME")
SLOTS_HELD_WHERE_PARKED = {
    "aes_gr_stilldn": STILLDN_S,
    "aes_gr_watchbox": (*STILLDN_S, "AES_GR_WATCHBOX_RECT"),
    "aes_gr_wait": STILLDN_S,
    "aes_gr_rubbox": (*STILLDN_S, "AES_GR_RUBWIND_RECT"),
    "aes_gr_dragbox": (*STILLDN_S, "AES_GR_DRAGBOX_FRAME"),
    "aes_gr_slidebox": (*STILLDN_S, "AES_GR_DRAGBOX_FRAME", "AES_GR_SLIDEBOX_RECTS"),
    "aes_mn_do": ("AES_MN_DO_FRAME",),
    "aes_fm_do": ("AES_FM_DO_FRAME", "AES_FM_BUTTON_FRAME"),       # ...the second under a radio button held: fm_button's
    "aes_fm_button": (*STILLDN_S, "AES_GR_WATCHBOX_RECT", "AES_FM_BUTTON_FRAME"),
    "aes_ap_sendmsg": ("AES_AP_RDWR_QPB, process 1",),             # the screen manager's own frame of it: per process
    "aes_wm_update": (),                                           # the lock's hand-over: nothing of a frame is live
    "aes_fm_alert": FM_ALERT_S,                                    # fm_alert's own frame, fm_do's under it, the watch's
    "aes_fs_input": FS_INPUT_S,                                    # fs_input's own frame, and fm_do's under it
}
A_SLOT_PER_PROCESS = ", process "


def _door_users_that_switch():
    """Every door user's registered row that switches, A SLICED SESSION ONCE (its slices are one record, one run)."""
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    sessions = {}
    for name, held in aes_event.SWITCHING_ROWS.items():
        if held.row.door:
            sessions.setdefault(id(held), (name, held))
    return dict(sessions.values())


def _modelled_again(held):
    """A registered door user's row through the model once more (its companion's own run): the `Modelled`."""
    aes_switch, switching = _switch()
    row, made = held.row, switching.settled(held.row)
    the_rom_s = switching.scheduled(row, made.pokes)
    foreign = any(pd != made.switches.process for pd in the_rom_s.entered)
    return aes_switch.modelled(routines.core_symbol(row.name), vdi.as_signed(row.name, row.arguments), made.pokes,
                               the_rom_s, answered=row.answered and vdi.ALCYON[row.name].restype is not None,
                               foreign=foreign, door=row.door)


def test_the_host_slots_held_across_a_wait_are_the_audit_s_and_every_one_is_given_back():
    """READ OFF EVERY DOOR USER'S ROW THAT SWITCHES: the slots held where its process was parked are the table's, by
    routine (the union over its rows) — and each run RETURNED with none held (the fork refuses otherwise, by name:
    the give-back after a wait, which no host run reached before a call could come back from one)."""
    held_by = {}
    for name, held in _door_users_that_switch().items():
        ran = _modelled_again(held)
        assert ran.returncode == 0, f"{name}: {ran.stderr}"
        assert ran.parked, f"{name}: the run read its host slots at no dispatch ({ran.parked}): nothing was audited"
        slots = held_by.setdefault(routines.core_symbol(held.row.name), [])
        slots.extend(slot for slot in ran.slots_held if slot not in slots)
    assert {core: tuple(slots) for core, slots in held_by.items()} == SLOTS_HELD_WHERE_PARKED
    per_process = {slot for slots in SLOTS_HELD_WHERE_PARKED.values() for slot in slots if A_SLOT_PER_PROCESS in slot}
    assert per_process == {"AES_AP_RDWR_QPB, process 1"}, "the one slot per process a door user parks under, today"


def test_a_call_that_returns_holding_a_host_slot_is_refused_by_name(monkeypatch):
    """RED: a routine that came back from its wait with a slot still claimed (here the flags read as one held) —
    the model's fork refuses the run by name; the next call of the routine in that process would abort on it."""
    aes_switch, _switching = _switch()
    monkeypatch.setattr(aes_switch, "host_slots_held", lambda: ["AES_GR_STILLDN_ANSWERS"])
    the_rom_s, staged = _scheduled(THE_WAIT_TO_LEAVE, {0: aes_event.release})
    ran = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert ran.returncode == aes_event.FORK_RAISED
    assert "the call RETURNED holding the host slot(s) ['AES_GR_STILLDN_ANSWERS']" in ran.stderr


def test_what_the_door_child_s_own_python_raises_at_the_dispatcher_ends_the_run_by_name(monkeypatch):
    """A CALLBACK CANNOT RAISE INTO C: ctypes prints what it raised, answers an undefined word, and THE TWIN RUNS ON —
    the child then exits 0 with a run nobody audited (measured in review: the slots' reading raising at the first
    dispatch, the call "returned" and the audit's table still held for a routine that holds none). So the child ends
    there, by name, with the harness's own status: the reading of the host slots at a dispatch, and a shadow's vet
    that could not be made (anything but its own refusal, which is the shadow's)."""
    aes_switch, _switching = _switch()
    the_rom_s, staged = _scheduled(THE_WAIT_TO_LEAVE, {0: aes_event.release})
    held = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert (held.returncode, held.parked) == (0, 1), held.stderr

    def unreadable():
        raise RuntimeError("the flags could not be read")
    with monkeypatch.context() as patched:
        patched.setattr(aes_switch, "host_slots_held", unreadable)
        ran = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert (ran.returncode, ran.parked, ran.answer) == (aes_event.FORK_RAISED, None, None)
    assert "the dispatcher's hook under the model raised RuntimeError('the flags could not be read')" in ran.stderr

    def no_vet(shadows, image):
        raise KeyError("a harness error inside the shadow's vet")
    monkeypatch.setattr(aes_event, "_vet_the_twin_at_the_dispatcher", no_vet)
    ran = _modelled(THE_WAIT_TO_LEAVE, the_rom_s, staged)
    assert ran.returncode == aes_event.FORK_RAISED and ran.idles is None
    assert "the shadow's vet at the dispatcher raised KeyError" in ran.stderr


def test_the_host_slots_roles_are_read_off_the_header_s_own_enum():
    """`aes_switch.host_slot_ids`: one role per held flag, in the enum's order — a slot per process one name per
    process's frame — as many as the library's array holds (`HOST_SLOT_ID_COUNT`: the symbol's own size)."""
    aes_switch, _switching = _switch()
    roles = aes_switch.host_slot_ids()
    per_process = aes.HOST_SLOTS["HOST_PROCESSES"]
    assert len(set(roles)) == len(roles) and roles[0] == "SEARCH_PATTERN" and roles[-1] == "AES_INOROUT_RECT"
    for role in ("AES_AP_RDWR_QPB", "AES_EV_MULTI_QPB"):
        frames = [each for each in roles if each.startswith(role + A_SLOT_PER_PROCESS)]
        assert len(frames) == per_process and roles.index(frames[-1]) - roles.index(frames[0]) == per_process - 1
    plain = {role for role in roles if A_SLOT_PER_PROCESS not in role}
    declared = {name.removeprefix("HOST_SLOT_") for name in aes.HOST_SLOTS
                if name.startswith("HOST_SLOT_") and not name.endswith("_BYTES")}
    assert plain == declared - {"AES_AP_RDWR_QPB", "AES_EV_MULTI_QPB"}
    assert aes_switch.host_slots_held() == [], "no slot is held between two runs of this process"


# ---- WHAT THE DOOR'S OWN BINDINGS SERVE OF THE ROUTINES THE EVENT LAYER IS HANDED ---------------------------------------------
A_CURSOR_POINT = (200, 120)


def test_the_door_serves_the_vdi_s_cursor_routine_on_the_register_hook_in_process_and_in_a_child():
    """`$fcff0a`, THE VDI'S default_user_cur — what `$947a` holds while a recording plays, and drawrat calls through
    the register hook — is among the routines the DOOR's bindings serve wherever the poll runs in C, beside the four
    fork functions and justretf: in process (`door_objects`) and in a child (`_child_walkers`), each by the
    candidate's own core. Held on the child's trampoline against the ROM's routine over one machine and (D0, D1)."""
    handed = {getattr(addrs, name) for name in aes_event.FORK_FUNCTIONS} | {addrs.AES_ROM_JUSTRETF, addrs.VDI_ROM_DEFAULT_USER_CUR}
    assert aes_event.polls_in_c() and set(aes_event.door_objects()) == set(aes_event.handed_routines()) == handed
    machine = aes_event.shown_machine()
    x, y = A_CURSOR_POINT
    final, _writes, _regs = emu.run(make_image(machine), addrs.VDI_ROM_DEFAULT_USER_CUR, {"d0": x, "d1": y})
    image = make_image(machine)
    buf = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer(image)
    registers = (ctypes.c_uint32 * len(isr.REGISTER))()
    registers[isr.REGISTER["d0"]], registers[isr.REGISTER["d1"]] = x, y
    serve = aes_event._child_walkers(aes_event._lib, objects=False, polls=True)
    serve(ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8)), addrs.VDI_ROM_DEFAULT_USER_CUR, registers)
    assert final[:addrs.ST_RAM_BYTES] != make_image(machine)[:addrs.ST_RAM_BYTES], "the premise: the routine moves the cursor"
    assert not aes_event.differing(image, final), "the child's register hook ran the candidate's default_user_cur"


# ---- A SLICE'S MARKS ARE ONE PROCESS'S — THE ROW'S (`aes_event.Marks`, a session that switches) ---------------------------
A_WAIT = addrs.AES_ROM_EV_MULTI


def _marks_over(totals, **marked):
    """Marks at a session's waits 0 and 1, reading the running `totals` (a dict a case moves on by hand)."""
    a_slice = aes_event.Slice(aes_event.door_call(A_WAIT, 0), aes_event.door_call(A_WAIT, 1))
    return aes_event.Marks(a_slice, lambda: dict(totals), **marked)


def _through_a_window(marks, totals, before=(10, 100), until=(15, 150), window=(100, 1000), then=(5, 50)):
    """`marks` taken through: the slice's start, a stretch of the row's own, A FOREIGN WINDOW, another stretch."""
    memory = bytes(1)
    totals.update(insns=before[0], cycles=before[1])
    marks.arrived(A_WAIT, 0, memory)
    totals.update(insns=until[0], cycles=until[1])
    marks.foreign_window_opened()
    totals.update(insns=until[0] + window[0], cycles=until[1] + window[1])
    return memory, (until[0] + window[0] + then[0], until[1] + window[1] + then[1])


def test_a_mark_s_totals_are_the_row_s_own_process_s_net_of_every_foreign_window_before_it():
    """What a slice SPENT is its two marks' difference in what THE ROW'S PROCESS spent: 10 instructions and 100
    cycles here, whatever the screen manager's turn between them cost (100 and 1,000) — which is kept BESIDE the
    slice (`foreign_inside`: one window, its totals), in no figure of it. The run's return is marked the same way."""
    totals = {}
    marks = _marks_over(totals, every_door_call=True)
    memory, after = _through_a_window(marks, totals)
    marks.foreign_window_closed()
    totals.update(insns=after[0], cycles=after[1])
    marks.arrived(A_WAIT, 1, memory)
    assert marks.spent("the run") == {"insns": 10, "cycles": 100}
    assert marks.foreign_inside("the run") == (1, {"insns": 100, "cycles": 1000})
    marks.returned(2)
    at_the_start, at_the_stop = {"insns": 10, "cycles": 100}, {"insns": 20, "cycles": 200}
    assert [arrival.spent for arrival in marks.timeline] == [at_the_start, at_the_stop, at_the_stop], (
        "the timeline's arrivals too: what a stretch between two of them cost is the row's own")
    unswitched = _marks_over(totals)
    assert unswitched.at(aes_event.ENTRY, "a run").windows == 0 and unswitched.at(aes_event.ENTRY, "a run").foreign is None


def test_a_mark_after_two_foreign_windows_is_net_of_both_and_a_later_slice_holds_the_second_alone():
    """...AND THE WINDOWS ADD UP: a second turn of another process (50 instructions, 500 cycles) after the first
    slice's end comes off every later total with the first — the run's return is marked after TWO windows, at what
    the row's process spent in all — and the slice from the second wait to the return holds that second window
    alone (`cut_to`: one run's marks read for another of its slices)."""
    totals = {}
    first, second = aes_event.door_call(A_WAIT, 0), aes_event.door_call(A_WAIT, 1)
    marks = aes_event.Marks(aes_event.Slice(first, second), lambda: dict(totals), others=(aes_event.Slice(second, aes_event.RETURN),))
    memory, after = _through_a_window(marks, totals)
    marks.foreign_window_closed()
    totals.update(insns=after[0], cycles=after[1])
    marks.arrived(A_WAIT, 1, memory)
    marks.foreign_window_opened()
    totals.update(insns=after[0] + 50, cycles=after[1] + 500)
    marks.foreign_window_closed()
    totals.update(insns=after[0] + 50 + 7, cycles=after[1] + 500 + 70)
    marks.returned(2)
    at_the_return = marks.at(aes_event.RETURN, "the run")
    assert (at_the_return.windows, at_the_return.spent) == (2, {"insns": 27, "cycles": 270})
    assert at_the_return.foreign == {"insns": 150, "cycles": 1500}
    to_the_return = marks.cut_to(aes_event.Slice(second, aes_event.RETURN))
    assert to_the_return.spent("the run") == {"insns": 7, "cycles": 70}
    assert to_the_return.foreign_inside("the run") == (1, {"insns": 50, "cycles": 500})
    assert marks.foreign_inside("the run") == (1, {"insns": 100, "cycles": 1000}), "the first slice's own, still"


def test_an_arrival_inside_a_foreign_window_is_no_mark_and_is_refused_by_name():
    """THE RED: an arrival handed to the marks between a window's opening and its close — the screen manager's own
    evnt_multi, at the very PC the slice is cut at — is ANOTHER PROCESS's, and is refused by name, uncounted: the
    row's own next arrival there is still its wait of ordinal 1. So is a return marked inside one."""
    totals = {}
    marks = _marks_over(totals)
    memory, after = _through_a_window(marks, totals)
    for another_process_s in (lambda: marks.arrived(A_WAIT, 1, memory), lambda: marks.returned(1)):
        with pytest.raises(AssertionError, match="a mark is an arrival of the ROW's process.*inside a foreign window"):
            another_process_s()
    marks.foreign_window_closed()
    totals.update(insns=after[0], cycles=after[1])
    marks.arrived(A_WAIT, 1, memory)
    assert marks.at(aes_event.door_call(A_WAIT, 1), "the run").windows == 1
    with pytest.raises(AssertionError, match="a foreign window closed that never opened"):
        marks.foreign_window_closed()


def test_a_door_watch_tells_its_marks_of_a_foreign_window_and_a_timeline_refuses_one():
    """WHO TELLS THE MARKS: the run's door watch, told by the watch that follows the run through the dispatcher
    (`DoorStops.foreign_window_opened` / `_closed`) — whatever else the watch counts. A `Timeline` (a run that
    switches nowhere: the ROM-only derivations a battery cuts its session by) refuses one by name."""
    totals = {"insns": 0, "cycles": 0}
    marks = _marks_over(totals)
    watch = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS).marked_with(marks)
    watch.foreign_window_opened()
    with pytest.raises(AssertionError, match="inside a foreign window"):
        marks.arrived(A_WAIT, 0, bytes(1))
    watch.foreign_window_closed()
    marks.arrived(A_WAIT, 0, bytes(1))
    unmarked = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS)
    unmarked.foreign_window_opened(), unmarked.foreign_window_closed()
    timed = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS).marked_with(aes_event.Timeline())
    with pytest.raises(AssertionError, match="a Timeline is of a run that switches nowhere"):
        timed.foreign_window_opened()


def test_two_shores_marks_on_either_side_of_a_window_are_two_slices_and_are_refused_by_name():
    """`vet_the_marks_agree`: an end our run reaches BEFORE another process's turn and the ROM's AFTER it (the same
    door call, the same memory) is priced net of the window on one shore alone — refused by name."""
    def taken(window_before_the_end):
        totals = {}
        marks = _marks_over(totals)
        memory, after = _through_a_window(marks, totals)
        if not window_before_the_end:
            totals.update(insns=after[0], cycles=after[1])
            marks.arrived(A_WAIT, 1, memory)
        marks.foreign_window_closed()
        if window_before_the_end:
            totals.update(insns=after[0], cycles=after[1])
            marks.arrived(A_WAIT, 1, memory)
        return marks
    with pytest.raises(AssertionError, match="inside a foreign window"):
        taken(window_before_the_end=False)
    the_rom_s, ours = taken(True), taken(True)
    aes_event.vet_the_marks_agree("a case", ours, the_rom_s, lambda _mine, _its: [])
    ours._taken[aes_event.door_call(A_WAIT, 1)] = ours._taken[aes_event.door_call(A_WAIT, 1)]._replace(windows=0)
    with pytest.raises(AssertionError, match=r"our slice ends .* after 0 foreign window\(s\) where the ROM's ends after 1"):
        aes_event.vet_the_marks_agree("a case", ours, the_rom_s, lambda _mine, _its: [])
