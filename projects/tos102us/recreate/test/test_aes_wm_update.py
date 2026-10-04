"""The WINDOW LIBRARY's half that reaches the event layer — `src/aes/wmupdate.c` (`aes/wmupdate.h`), through the event
door (`test/aes_event.py`) — and the control manager's three leaves it uses.

    set_ctrl(r) / get_ctrl(r)   rc_copy(r, &ctrl) / rc_copy(&ctrl, r)
    get_mown(pm, pk)            *pm = gl_mowner; *pk = gl_kowner
    wm_update(code)             code >= 2: fm_own(code - 2); 0: unsync(&wind_spb); else tak_flag(&wind_spb) ||
                                ev_block(MU_SDMUTEX, ad_windspb) — D0 the last door call's
    fm_own(take)                take: wm_update(1); on the first, gl_mntree put aside, get_ctrl, get_mown, ct_chgown(rlr,
                                &gl_rscreen); count++.  else: count--; on the last, ct_chgown(pkown, &ctrl), gl_mntree put
                                back; wm_update(0)
    w_setactive()               w = gl_wtop == -1 ? 0 : gl_wtop; w_getsize(WS_WORK, w, &t); ct_chgown(win[w].owner, &t)
    w_redraw(w, r)              t = *r; c = WS_WORK; rc_intersect(t, c) && w_union(list, c) && rc_intersect(c, t) &&
                                ap_sendmsg(gl_rmsg, WM_REDRAW, owner's pid, w, t)
    w_update(bot, r, top, mv)   frozen: nothing. rc_intersect(&gl_rfull, r); moff; windows top..bot: w_cpwalk + w_redraw
                                (the top one skipped when it moved); mon
    draw_change(w, r)           the window's rectangles and work area set, every list rebuilt (everyobj, newrect), the top
                                made the tree's last, w_setactive; then (not frozen) the change: MOVED / SIZED / TOPPED
    wm_opcl(w, r, add)          lock; w_obadd or ob_delete; draw_change(w, copy of r); add: WS_PREV = r; unlock
    wm_open / wm_close          wm_opcl(w, r, 1) / wm_opcl(w, &gl_rzero, 0)
    wm_set(w, field, words)     lock; NAME/INFO w_strchg, CURRXYWH draw_change, TOP, 13 hold/release drawing, NEWDESK,
                                the four sliders clamped in place; unlock

THE MACHINES ARE DERIVED (`test_aes_wmlib.py`'s, `aes_event`'s): PD0 running as the scheduler makes it, every window the
ROM's own wm_create / wm_open / wm_set made, the lock held by the ROM's own wm_update, the screen manager running woken
by the mouse onto the menu bar. Nothing of the scheduler, the lock or a record is poked.

THE DRAWS run with every door their C reaches: the VDI's cores, the event door, and the routines the window tree's
walks are handed by value — ob_draw's just_draw, draw_change's newrect and newrect's mkrect, each served by its C core.

THE LOCK'S SWITCHING ARMS are reached by derived states, each refused by the door by name in a child process, the C
up to it the ROM's own run: its BLOCK — a ROM finding: after an unbalanced END_UPDATE (the count -1) the next
BEG_UPDATE is refused and waits for good (ev_block) — and unsync's HAND-OVER to a process waiting for the lock, which
yields (`waited_on`: the waiter queued by the scheduler's own runs). UNPINNED, equivalent over every reachable state:
wind_update reads the lock it waits on through `ad_windspb`, which start-up sets once to the lock itself ($fda032) and
nothing changes — a C handing the lock's address directly is indistinguishable.
"""
import functools

import pytest

import abi
import aes
import aes_event
import aes_gsx as gsx
import aes_objdraw as od
import case
import test_aes_wmlib as wm
import vdi
from aes_rlist import DESKTOP, window_record
from case import merge_pokes
from harness import BASE_IMAGE, addrs, emu, make_image
from test_aes_gsx import screen_changed as gsx_screen_changed

WU = aes.header_constants("wmupdate.h")
WMH = wm.WM
L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
SIGNATURES = {
    "AES_ROM_SET_CTRL": (None, (I, L)),
    "AES_ROM_GET_CTRL": (None, (I, L)),
    "AES_ROM_GET_MOWN": (None, (I, L, L)),
    "AES_ROM_FM_OWN": (aes.WORD_ANSWER, (I, W)),
    "AES_ROM_W_SETACTIVE": (None, (I,)),
    "AES_ROM_W_REDRAW": (None, (I, W, L)),
    "AES_ROM_W_UPDATE": (None, (I, W, L, W, W)),
    "AES_ROM_DRAW_CHANGE": (None, (I, W, L)),
    "AES_ROM_WM_OPCL": (aes.WORD_ANSWER, (I, W, L, W)),
    "AES_ROM_WM_OPEN": (aes.WORD_ANSWER, (I, W, L)),
    "AES_ROM_WM_CLOSE": (aes.WORD_ANSWER, (I, W)),
    "AES_ROM_WM_SET": (aes.WORD_ANSWER, (I, W, W, L)),
    "AES_ROM_WM_UPDATE": (aes.WORD_ANSWER, (I, W)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
(SET_CTRL, GET_CTRL, GET_MOWN, FM_OWN, W_SETACTIVE, W_REDRAW, W_UPDATE, DRAW_CHANGE, WM_OPCL, WM_OPEN, WM_CLOSE, WM_SET,
 WM_UPDATE) = SIGNATURES

THROUGH = gsx.THROUGH
NIL = aes.OB_NIL
WIND_SPB, SPB_COUNT, SPB_OWNER = WU["AES_WIND_SPB"], WU["SPB_COUNT"], WU["SPB_OWNER"]
BEG_UPDATE, END_UPDATE, BEG_MCTRL, END_MCTRL = (WU[name] for name in ("WM_BEG_UPDATE", "WM_END_UPDATE", "WM_BEG_MCTRL",
                                                                      "WM_END_MCTRL"))
FM_OWN_COUNT = WU["AES_FM_OWN_COUNT"]
CTRL_RECT, GL_MOWNER, GL_KOWNER = WU["AES_CTRL_RECT"], WU["AES_GL_MOWNER"], WU["AES_GL_KOWNER"]
GL_RMSG, GL_WASCLR = WU["AES_GL_RMSG"], WU["AES_GL_WASCLR"]
MESSAGE_BYTES = aes.AP_MSG_BYTES
# A redraw message's rectangle: its words after the window's (`apmsg.h`'s AP_MSG_WORDS, word 0 the window).
MESSAGE_RECT = aes.AP_MSG_WORDS + aes.WORD_BYTES
SLIDER_SCALE = WMH["W_SLIDER_SCALE"]
rect_at, rect_pokes, grect = wm.rect_at, wm.rect_pokes, wm.grect
RECT = rect_at(0)                      # the GRECT a case hands in
OUT = rect_at(1)                       # ...and an answer's
WORDS = wm.DERIVATION_AT               # wind_set's words, where the window machines' own wind_set staged theirs

# The staged band: a window's title and information line, wind_set's NAME / INFO strings.
BAND_OFFSET = 0x3F00                   # the window's last 256 bytes, apart from the menu layer's bands
BAND_BYTES = 0x40
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/test_aes_wm_update.py: wind_set's strings")
TITLE_AT = BAND_AT
TITLE = b" A WINDOW \0"


# ---- the doors ---------------------------------------------------------------------------------------------------------
# The routines the window tree's walks are handed BY VALUE, each served by its C core: ob_draw's just_draw (w_cpwalk's
# gadgets, w_drawdesk's desktop), draw_change's newrect, and newrect's mkrect.
WALKERS = aes.walkers()
# Every frame GRECT the C hands on is a host slot: staged STALE, beside the window library's own and ob_draw's, so a
# store the C skipped reads STALE where the ROM read its own.
SLOTS = merge_pokes(wm.DRAW_SLOTS, *(aes.stale_host_slot(role) for role in (
    "AES_W_SETACTIVE_RECT", "AES_W_REDRAW_RECTS", "AES_DRAW_CHANGE_FRAME", "AES_WM_OPCL_RECT", "AES_WM_SET_RECT")))
# gl_rmsg staged stale: every word of a WM_REDRAW the C skipped shows.
STALE_MESSAGE = aes.field_pokes("AES", GL_RMSG=bytes([case.SLACK_FILL]) * MESSAGE_BYTES)
STALE_WORD = int.from_bytes(bytes([case.SLACK_FILL]) * aes.WORD_BYTES, "big")    # a word of it: nothing posted there
# THE CAP: measured, the longest ROM run here is draw_change's of a lower window moved and resized,
# DEEPEST_ROM_RUN_INSNS (`test_the_longest_run_fits_the_cap`) — past the oracle's default 200,000. So the BATTERY
# declares one cap from it on the event door's one mechanism (`aes_event.battery_cap`: that run needs it and fits it
# by the derivations' margin, the least that does), and every case's ROM run is held that far under it at the door
# (`aes_event.run_event`'s `cap`): one inside the margin, or past the cap, is refused by name, the cap to be raised
# from that run.
DEEPEST_ROM_RUN_INSNS = 244_097
CASE_CAP = aes_event.battery_cap(DEEPEST_ROM_RUN_INSNS * aes_event.DERIVATION_MARGIN, deepest=DEEPEST_ROM_RUN_INSNS)


def with_stale_slots(pokes, *over):
    """`pokes` (a derived machine) with the slots and gl_rmsg staged stale, `over`'s layers laid last over even those
    — in ONE merge: a cleared screen is 32,000 bytes, and the registry stages one per drawing row."""
    return merge_pokes(pokes, SLOTS, STALE_MESSAGE, *over)


def run(name, arguments, pokes, *, over=None, **kwargs):
    """`name` through the event door over `with_stale_slots(pokes, over)`, every door its C reaches bound, its C first in
    a child (`aes_event.run_guarded`) — the ROM's run held under the battery's cap by its margin (CASE_CAP)."""
    return aes_event.run_guarded(name, arguments, with_stale_slots(pokes, over), drawing=True, objects=WALKERS,
                                 cap=CASE_CAP, **kwargs)


def leaf(name, arguments, pokes=None, **kwargs):
    """A control-manager leaf over the leaf machine (no door: none of the three calls out but rc_copy)."""
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)


# ---- the machines --------------------------------------------------------------------------------------------------------
running = wm.running                   # PD0 running, the cursor hidden, the snapshot's font cached
top_window = wm.top_window             # `(pokes, 1)`: window 1 of every gadget at WINDOW_AT, open, on top
two_windows = wm.two_windows           # `(pokes, 1, 2)`: window 2 over window 1's corner, on top
WINDOW_AT = wm.WINDOW_AT
SIDE_BY_SIDE_AT = (230, 140, 80, 40)   # a second window clear of WINDOW_AT and its border: neither cuts the other


def rom_derived(name, frame, pokes):
    """`pokes` continued by the ROM's own run of `addrs.<name>` over `frame` (`aes_event.derived`)."""
    return wm.rom_derived(getattr(addrs, name), frame, pokes)


def locked(onto=None, times=1):
    """The screen lock taken `times` by the running process — the ROM's own wm_update(1)."""
    pokes = running() if onto is None else onto
    for _ in range(times):
        pokes = rom_derived("AES_ROM_WM_UPDATE", aes_event.frame_of(("w", BEG_UPDATE)), pokes)
    return pokes


def owned(onto=None, times=1):
    """The screen taken by the form manager `times` — the ROM's own wm_update(3)."""
    pokes = running() if onto is None else onto
    for _ in range(times):
        pokes = rom_derived("AES_ROM_WM_UPDATE", aes_event.frame_of(("w", BEG_MCTRL)), pokes)
    return pokes


@functools.cache
def screen_manager_running():
    """PD1 RUNNING — the screen manager, woken by the mouse onto the menu bar — PD0 still parked (`aes_event`), the
    snapshot's font cached as `running`'s is."""
    return aes_event.machine(aes_event.screen_manager_running, onto=od.SNAPSHOT_FONT)


@functools.cache
def side_by_side():
    """`(pokes, first, second)`: top_window's window, then a second clear of it — neither cut by the other."""
    pokes, first = top_window()
    pokes, second = aes_event.window_chain(aes_event.EVERY_GADGET, *SIDE_BY_SIDE_AT, onto=pokes)
    return pokes, first, second


# THE USUAL APPLICATION WINDOW: a title bar alone — its title, closer, fuller and GEM's mover — no slider, arrow or
# sizer to redraw. A change of two overlapping windows of this kind costs the ROM less than half what two of every
# gadget cost (measured: 104,972 instructions for wind_set(WF_TOP) of the covered one, against 233,112), which brings
# the arms only two overlapping windows reach under the bench's cap: they are priced over these (`_registered`).
TITLE_BAR_KIND = WMH["WK_TITLE_BAR"] | aes_event.WK_MOVER


def current_of(image, window):
    return wm.rect_of(image, aes.AES_WINDOW_TREE + window * aes.OB_BYTES + aes.OB_X - aes.ORECT_X)


@functools.cache
def title_bar_windows():
    """`(pokes, lower, upper)`: two_windows' pair at the same rectangles, each a title bar alone (TITLE_BAR_KIND)."""
    every, every_lower, every_upper = two_windows()
    pokes = running()
    handles = []
    for window in (every_lower, every_upper):
        pokes, handle = aes_event.window_chain(TITLE_BAR_KIND, *current_of(make_image(every), window), onto=pokes)
        handles.append(handle)
    return pokes, *handles


window_set = wm.window_set


def spb(result):
    """The lock after the run: its count and its owner."""
    return spb_of(result.final)


def spb_of(image):
    return aes.signed(case.word_in(image, WIND_SPB + SPB_COUNT)), case.long_in(image, WIND_SPB + SPB_OWNER)


def the_rect(rect):
    return rect_pokes(0, rect)


# ---- the control manager's leaves ------------------------------------------------------------------------------------------
SNAPSHOT_CTRL = tuple(aes.signed(case.word_in(BASE_IMAGE, CTRL_RECT + offset))
                      for offset in range(0, aes.GRECT_BYTES, aes.WORD_BYTES))
A_RECT = (12, -34, 0x7FFF, -0x8000)


@THROUGH
def test_set_ctrl_copies_the_rectangle_in(through_line_f):
    result = leaf(SET_CTRL, (RECT,), the_rect(A_RECT), through_line_f=through_line_f)
    assert grect(result, CTRL_RECT) == A_RECT


@THROUGH
def test_get_ctrl_copies_it_out(through_line_f):
    result = leaf(GET_CTRL, (RECT,), wm.STALE_RECTS, through_line_f=through_line_f)
    assert grect(result, RECT) == SNAPSHOT_CTRL == (0, 11, 320, 189)


@pytest.mark.parametrize("name", (SET_CTRL, GET_CTRL))
def test_the_rectangle_is_put_on_the_bus(name):
    result = leaf(name, (RECT | aes.BUS_TAG,), merge_pokes(wm.STALE_RECTS, the_rect(A_RECT)))
    assert grect(result, CTRL_RECT) == grect(result, RECT)


@pytest.mark.parametrize("shift", (2, -2), ids=("into its second half", "over its first"))
def test_get_ctrl_copied_over_itself(shift):
    """rc_copy's order, as an overlap: the answer laid over the control rectangle itself, a word off either way."""
    result = leaf(GET_CTRL, (CTRL_RECT + shift,))
    assert result.word(CTRL_RECT + shift) == case.word_in(BASE_IMAGE, CTRL_RECT)


@THROUGH
def test_get_mown_answers_both_owners(through_line_f):
    result = leaf(GET_MOWN, (OUT, OUT + aes.LONG_BYTES), wm.STALE_RECTS, through_line_f=through_line_f)
    assert result.long(OUT) == case.long_in(BASE_IMAGE, GL_MOWNER)
    assert result.long(OUT + aes.LONG_BYTES) == case.long_in(BASE_IMAGE, GL_KOWNER)


def test_get_mown_stores_the_mouse_s_first():
    """THE ORDER, as an overlap: the mouse's answer laid over the keyboard's owner itself — what the second store reads
    is the first's — on the screen manager's machine, where the two owners differ."""
    pokes = screen_manager_running()
    assert case.long_in(make_image(pokes), GL_MOWNER) != case.long_in(make_image(pokes), GL_KOWNER)
    result = aes.run_function(GET_MOWN, (GL_KOWNER, OUT), merge_pokes(pokes, wm.STALE_RECTS))
    assert result.long(OUT) == result.long(GL_MOWNER)


def test_get_mown_s_pointers_are_put_on_the_bus():
    result = leaf(GET_MOWN, (OUT | aes.BUS_TAG, (OUT + aes.LONG_BYTES) | aes.BUS_TAG), wm.STALE_RECTS)
    assert result.long(OUT) == case.long_in(BASE_IMAGE, GL_MOWNER)


# ---- the lock: wm_update and fm_own ------------------------------------------------------------------------------------------
def _top():
    return top_window()[0]


CHILD_CALLS = {
    "wm_update(1)": (WM_UPDATE, (BEG_UPDATE,), running),
    "wm_update(0) unbalanced": (WM_UPDATE, (END_UPDATE,), running),
    "wm_update(2) unbalanced": (WM_UPDATE, (END_MCTRL,), running),
    "fm_own(1)": (FM_OWN, (1,), running),
    "fm_own(0) unbalanced": (FM_OWN, (0,), running),
    "w_setactive": (W_SETACTIVE, (), running),
    "w_setactive of the top window": (W_SETACTIVE, (), _top),
    "w_redraw": (W_REDRAW, (1, WORDS), lambda: merge_pokes(_top(), {WORDS: vdi.pack_words(60, 70, 40, 30)})),
}


@pytest.mark.parametrize("name, values, machine", CHILD_CALLS.values(), ids=CHILD_CALLS)
def test_each_returns_through_the_door_in_a_child(name, values, machine):
    """A door call the nested run refuses halts the core (`aes/evdoor.h`); in-process that ends the whole run, so each
    door user that does not draw is first run in a child process, where it must return — the unbalanced releases too,
    whose arms a miscounting C turns into a door call the event layer refuses."""
    aes_event.returns_in_a_child(name, values, machine())


@THROUGH
def test_wm_update_takes_the_free_lock(through_line_f):
    result = run(WM_UPDATE, (BEG_UPDATE,), running(), through_line_f=through_line_f)
    assert result.answer() == 1
    assert spb(result) == (1, aes.SHELL_PD)


@pytest.mark.parametrize("code", (-1, -0x8000), ids=("-1", "the lowest word"))
def test_wm_update_below_its_codes_takes_the_lock(code):
    """Any word below WM_END_MCTRL but 0 takes the lock — the compare is signed."""
    result = run(WM_UPDATE, (code,), running())
    assert spb(result) == (1, aes.SHELL_PD)


def test_wm_update_takes_the_lock_its_process_holds_again():
    result = run(WM_UPDATE, (BEG_UPDATE,), locked())
    assert result.answer() == 1
    assert spb(result) == (2, aes.SHELL_PD)


def test_the_screen_manager_takes_the_lock_for_itself():
    result = run(WM_UPDATE, (BEG_UPDATE,), screen_manager_running())
    assert spb(result) == (1, aes.SCREEN_MANAGER_PD)


def test_wm_update_releases_the_lock():
    result = run(WM_UPDATE, (END_UPDATE,), locked())
    assert result.answer() == 0
    assert spb(result) == (0, 0)


def test_wm_update_releases_a_lock_never_taken():
    """An application's END_UPDATE with no BEG_UPDATE: unsync counts below 0 and gives nothing up."""
    result = run(WM_UPDATE, (END_UPDATE,), running())
    assert spb(result)[0] == -1


# unsync's D0 when the lock is still held afterwards is the D0 it was ENTERED with — the ROM's caller's (`aes/wmupdate.h`):
# the case enters with a D0 of its own to show it, and the answer is not compared.
CALLERS_D0 = 0x5A5A1234


def test_wm_update_releases_one_level_of_a_nested_lock():
    result = run(WM_UPDATE, (END_UPDATE,), locked(times=2), regs={"d0": CALLERS_D0}, answer_compared=False)
    assert spb(result) == (1, aes.SHELL_PD)
    assert result.info["regs"]["d0"] == CALLERS_D0


@THROUGH
def test_wm_update_3_is_fm_own_taking_the_screen(through_line_f):
    result = run(WM_UPDATE, (BEG_MCTRL,), running(), through_line_f=through_line_f)
    assert result.word(FM_OWN_COUNT) == 1
    assert result.long(aes.AES_GL_MNTREE) == 0
    assert result.long(WU["AES_FM_OWN_MENU"]) == case.long_in(BASE_IMAGE, aes.AES_GL_MNTREE)
    assert grect(result, WU["AES_FM_OWN_CTRL"]) == SNAPSHOT_CTRL
    assert grect(result, CTRL_RECT) == (0, 0, 320, 200)
    assert spb(result) == (1, aes.SHELL_PD)


def test_wm_update_2_is_fm_own_giving_it_back():
    result = run(WM_UPDATE, (END_MCTRL,), owned())
    assert result.word(FM_OWN_COUNT) == 0
    assert result.long(aes.AES_GL_MNTREE) == case.long_in(BASE_IMAGE, aes.AES_GL_MNTREE)
    assert grect(result, CTRL_RECT) == SNAPSHOT_CTRL
    assert spb(result) == (0, 0)


@pytest.mark.parametrize("code", (0x7FFF, 4), ids=("the highest word", "4"))
def test_wm_update_past_its_codes_is_fm_own_taking(code):
    result = run(WM_UPDATE, (code,), running())
    assert result.word(FM_OWN_COUNT) == 1


@THROUGH
def test_fm_own_takes_the_screen(through_line_f):
    result = run(FM_OWN, (1,), running(), through_line_f=through_line_f)
    assert result.word(FM_OWN_COUNT) == 1


def test_fm_own_takes_it_again():
    """Nested: the lock taken again and counted, nothing saved over what the first take saved."""
    result = run(FM_OWN, (1,), owned())
    assert result.answer() == 1
    assert result.word(FM_OWN_COUNT) == 2
    assert spb(result) == (2, aes.SHELL_PD)


def test_fm_own_gives_back_one_level():
    result = run(FM_OWN, (0,), owned(times=2), regs={"d0": CALLERS_D0}, answer_compared=False)
    assert result.word(FM_OWN_COUNT) == 1
    assert result.long(aes.AES_GL_MNTREE) == 0


def test_fm_own_gives_back_the_last():
    result = run(FM_OWN, (0,), owned())
    assert result.word(FM_OWN_COUNT) == 0
    assert spb(result) == (0, 0)


def test_fm_own_given_back_when_never_taken():
    """An unbalanced give-back: the count goes below 0, the lock too — nothing restored."""
    result = run(FM_OWN, (0,), running())
    assert aes.signed(result.word(FM_OWN_COUNT)) == -1


def test_fm_own_by_the_screen_manager_hands_the_screen_to_it():
    """Taken by PD1 running while the mouse belongs to PD0: the screen handed to PD1, PD0 saved as the owner to give
    it back to."""
    result = run(FM_OWN, (1,), screen_manager_running())
    assert result.long(GL_MOWNER) == aes.SCREEN_MANAGER_PD
    assert result.long(WU["AES_FM_OWN_KEYBOARD"]) == aes.SHELL_PD


def test_fm_own_given_back_by_the_screen_manager_returns_the_keyboard_s_owner():
    """Taken by PD1 running (the mouse PD1's, the keyboard PD0's), then given back: the screen handed to the KEYBOARD's
    saved owner, PD0 — not the mouse's."""
    result = run(FM_OWN, (0,), owned(screen_manager_running()))
    assert result.long(GL_MOWNER) == aes.SHELL_PD


def test_fm_own_saves_before_it_hands_over():
    """THE ORDER: the saved control rectangle is the one BEFORE ct_chgown made it the screen's."""
    result = run(FM_OWN, (1,), running())
    assert grect(result, WU["AES_FM_OWN_CTRL"]) == SNAPSHOT_CTRL


def test_fm_own_reads_the_running_process_through_the_bus():
    tagged = merge_pokes(running(), aes.field_pokes("AES", RLR=aes.SHELL_PD | aes.BUS_TAG))
    result = run(FM_OWN, (1,), tagged)
    assert result.word(FM_OWN_COUNT) == 1


@functools.cache
def released_unbalanced():
    """The lock released by the ROM's own wm_update(0) with nobody holding it: its count -1, no owner."""
    return rom_derived("AES_ROM_WM_UPDATE", aes_event.frame_of(("w", END_UPDATE)), running())


@pytest.mark.parametrize("name, values", ((WM_UPDATE, (BEG_UPDATE,)), (FM_OWN, (1,))), ids=("wm_update(1)", "fm_own(1)"))
def test_the_lock_after_an_unbalanced_release_blocks(name, values):
    """A ROM FINDING, and the ev_block arm's one derived state: after an END_UPDATE with no BEG_UPDATE (the count -1, no
    owner), the next BEG_UPDATE finds tak_flag's count 0 after its increment — not 1, and the owner not the running
    process — so the lock is refused (tak_flag answers 0) and the caller WAITS for it (ev_block's mutex wait, which
    amutex's own tak_flag refuses again): the process blocks for good. The door refuses that wait by name (a child
    process), and the C up to that wait — the frames it handed the door, tak_flag's then ev_block's, and the whole
    image — is the ROM's own run stopped where it blocks."""
    taken = aes_event.refused_where_the_rom_blocks(name, values, released_unbalanced())
    assert [call.routine for call in taken.calls][-2:] == [addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_EV_BLOCK]


MU_KEYBD = 0x0001                      # ev_multi's keyboard event ($fe69cc btst #0,d7)
# PD0's evnt_multi for a key alone: its answers where the derivations keep a message buffer.
KEY_WAIT = aes_event.EV_MULTI_FRAME.pack(MU_KEYBD, 0, 0, 0, 0, 0, aes_event.MESSAGE_AT)


@functools.cache
def waited_on():
    """THE LOCK WITH A PROCESS WAITING FOR IT, every step the ROM's own run and the scheduler's: PD0 takes the lock
    (wind_update(BEG_UPDATE)) and parks in an evnt_multi for a key (`aes_event.parked` — an application holding the
    screen while it waits); the mouse onto the menu bar wakes the screen manager, whose own BEG_UPDATE tak_flag refuses
    — it parks, queued on the lock (ev_block); Return wakes PD0, the lock still its own."""
    pokes = aes_event.parked(addrs.AES_ROM_EV_MULTI, KEY_WAIT, locked())
    pokes = aes_event.parked(addrs.AES_ROM_WM_UPDATE, aes_event.frame_of(("w", BEG_UPDATE)),
                             aes_event.woken_onto_the_menu_bar(pokes))
    return aes_event.woken_by_a_key(pokes)


def lock_waiter(image):
    """The process at the head of the lock's wait list (its EVB's PD), or None."""
    evb = case.long_in(image, WIND_SPB + WU["SPB_WAIT"])
    return evb and case.long_in(image, evb + aes.EVB_PD)


def test_the_lock_released_to_a_process_waiting_for_it_yields():
    """unsync's HAND-OVER: PD0's END_UPDATE over the lock the screen manager waits for (`waited_on`) — the count reaches
    0 with a waiter, so the ROM hands it the lock, wakes it and calls dsptch with PD0 still ready: the machine would run
    the screen manager first. The door refuses that yield by name (a child process), and up to it the C is the ROM's
    run stopped at unsync — the frame handed and the whole image."""
    pokes = waited_on()
    image = make_image(pokes)
    assert spb_of(image) == (1, aes.SHELL_PD) and lock_waiter(image) == aes.SCREEN_MANAGER_PD
    assert aes.list_of(image, aes.AES_RLR) == [aes.SHELL_PD]
    taken = aes_event.refused_where_the_rom_blocks(WM_UPDATE, (END_UPDATE,), pokes, switches=aes_event.YIELDS)
    assert [call.routine for call in taken.calls] == [addrs.AES_ROM_UNSYNC]
    at_the_call, frame = bytearray(taken.rom_memory), aes_event.SEMAPHORE_FRAME.pack(WIND_SPB)
    at_the_call[abi.FIRST_ARG:abi.FIRST_ARG + len(frame)] = frame
    final, _writes, regs = emu.run(at_the_call, addrs.AES_ROM_UNSYNC, stop_pc=addrs.AES_ROM_DSPTCH)
    assert regs["checkpoint"] and spb_of(final) == (1, aes.SCREEN_MANAGER_PD), "the premise: the lock handed over"


# ---- w_setactive -------------------------------------------------------------------------------------------------------------
def work_area(image, window):
    return wm.rect_of(image, window_record(window) + aes.WIN_WORK - aes.ORECT_X)


@THROUGH
def test_w_setactive_with_no_window_is_the_desktop_s(through_line_f):
    """No window open (gl_wtop -1): the desktop's owner given the mouse, its work area the control rectangle."""
    result = run(W_SETACTIVE, (), running(), through_line_f=through_line_f)
    assert grect(result, CTRL_RECT) == work_area(result.final, DESKTOP)
    assert result.long(GL_MOWNER) == case.long_in(BASE_IMAGE, window_record(DESKTOP) + aes.WIN_OWNER)


def test_w_setactive_with_no_window_while_the_screen_manager_runs():
    """No window open, PD1 running: the DESKTOP's owner (PD0, the window record's — not the running process) given the
    mouse."""
    result = run(W_SETACTIVE, (), screen_manager_running())
    assert result.long(GL_MOWNER) == case.long_in(BASE_IMAGE, window_record(DESKTOP) + aes.WIN_OWNER) == aes.SHELL_PD


def test_w_setactive_hands_on_the_owner_as_the_record_holds_it():
    """A window created while `rlr` held a top byte: its owner — that longword, top byte and all — handed to ct_chgown
    as it stands (the event layer stores it as the mouse's owner)."""
    tagged = merge_pokes(running(), aes.field_pokes("AES", RLR=aes.SHELL_PD | aes.BUS_TAG))
    pokes, _window = aes_event.window_chain(aes_event.EVERY_GADGET, *WINDOW_AT, onto=tagged)
    result = run(W_SETACTIVE, (), pokes)
    assert result.long(GL_MOWNER) == aes.SHELL_PD | aes.BUS_TAG


def test_w_setactive_is_the_top_window_s():
    pokes, window = top_window()
    result = run(W_SETACTIVE, (), pokes)
    assert grect(result, CTRL_RECT) == work_area(result.final, window)


def test_w_setactive_of_the_screen_manager_s_window():
    """A window the screen manager opened (its own wm_create and wm_open, PD1 running), set active: its owner's work
    area the control rectangle."""
    pokes, window = aes_event.window_chain(aes_event.EVERY_GADGET, *WINDOW_AT, onto=screen_manager_running())
    result = run(W_SETACTIVE, (), pokes)
    assert result.long(GL_MOWNER) == aes.SCREEN_MANAGER_PD
    assert grect(result, CTRL_RECT) == work_area(result.final, window)


# ---- w_redraw -------------------------------------------------------------------------------------------------------------------
def posted(result):
    """The message w_redraw built in gl_rmsg (eight signed words): what ap_rdwr was handed — the pipe itself MERGES a
    redraw for a window already queued (wm_open queued one for every window here) into that one."""
    return tuple(aes.signed(word) for word in result.words(GL_RMSG, MESSAGE_BYTES // aes.WORD_BYTES))


def redraw_message(window, rect, sender=0):
    return (WU["WM_REDRAW"], sender, 0, window, *rect)


@functools.cache
def covered_right():
    """`(pokes, lower)`: top_window's window with a second over its whole right side — the lower one's visible
    rectangles its left part alone."""
    pokes, lower = top_window()
    pokes, _upper = aes_event.window_chain(aes_event.EVERY_GADGET, 100, 20, 200, 130, onto=pokes)
    return pokes, lower


@functools.cache
def created_only():
    """`(pokes, window)`: a window the ROM created and never opened — a work area, no visible rectangles."""
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=running())
    return rom_derived("AES_ROM_WM_CALC", aes_event.frame_of(("w", 1), ("w", aes_event.EVERY_GADGET),
                                                            *(("w", v) for v in WINDOW_AT),
                                                            *(("l", window_record(window) + aes.WIN_WORK + 2 * k)
                                                              for k in range(4))), pokes), window


INSIDE = (60, 70, 40, 30)              # inside top_window's work area
ACROSS = (0, 50, 100, 30)              # ...across its left edge: cut by it


@THROUGH
def test_w_redraw_posts_the_owner_a_redraw(through_line_f):
    pokes, window = top_window()
    result = run(W_REDRAW, (window, RECT), merge_pokes(pokes, the_rect(INSIDE)), through_line_f=through_line_f)
    assert posted(result) == redraw_message(window, INSIDE)


def test_w_redraw_cuts_the_rectangle_to_what_the_window_shows():
    """The first cut, by the work area, only decides whether to go on: the bounding box of the window's visible
    rectangles — its whole rectangle, border and all — replaces it, and the rectangle is cut by that."""
    pokes, window = top_window()
    result = run(W_REDRAW, (window, RECT | aes.BUS_TAG), merge_pokes(pokes, the_rect(ACROSS)))
    assert posted(result) == redraw_message(window, (WINDOW_AT[0], 50, ACROSS[2] - WINDOW_AT[0], 30))


@pytest.mark.parametrize("rect", ((0, 0, 10, 10), (60, 70, 0, 30), (40, 31, 50, 8)),
                         ids=("outside the window", "empty", "on the title bar: in the window, outside its work area"))
def test_w_redraw_of_nothing_it_shows_posts_nothing(rect):
    pokes, window = top_window()
    result = run(W_REDRAW, (window, RECT), merge_pokes(pokes, the_rect(rect)))
    assert result.word(GL_RMSG) == STALE_WORD


def test_w_redraw_of_a_window_never_opened_posts_nothing():
    """Its work area holds the rectangle, but it has no visible rectangles (w_union answers 0)."""
    pokes, window = created_only()
    result = run(W_REDRAW, (window, RECT), merge_pokes(pokes, the_rect(INSIDE)))
    assert result.word(GL_RMSG) == STALE_WORD


def test_w_redraw_of_a_covered_part_posts_nothing():
    """In the work area, but outside the bounding box of what the window shows: the second cut is empty."""
    pokes, lower = covered_right()
    result = run(W_REDRAW, (lower, RECT), merge_pokes(pokes, the_rect((150, 60, 20, 20))))
    assert result.word(GL_RMSG) == STALE_WORD


def test_w_redraw_cuts_to_what_the_window_shows():
    pokes, lower = covered_right()
    result = run(W_REDRAW, (lower, RECT), merge_pokes(pokes, the_rect((40, 60, 100, 20))))
    assert result.word(GL_RMSG) == WU["WM_REDRAW"]


def test_w_redraw_to_the_screen_manager_s_window():
    """A window PD1 opened: the message goes to PD1 (pid 1), read through the record's owner."""
    pokes, window = aes_event.window_chain(aes_event.EVERY_GADGET, *WINDOW_AT, onto=screen_manager_running())
    result = run(W_REDRAW, (window, RECT), merge_pokes(pokes, the_rect(INSIDE)))
    assert aes.signed(result.word(GL_RMSG + 2)) == 1


def test_w_redraw_reads_the_owner_through_the_bus():
    """A window created while `rlr` held a top byte (the 68000's bus drops it): its owner is that longword."""
    tagged = merge_pokes(running(), aes.field_pokes("AES", RLR=aes.SHELL_PD | aes.BUS_TAG))
    pokes, window = aes_event.window_chain(aes_event.EVERY_GADGET, *WINDOW_AT, onto=tagged)
    assert case.long_in(make_image(pokes), window_record(window) + aes.WIN_OWNER) == aes.SHELL_PD | aes.BUS_TAG
    result = run(W_REDRAW, (window, RECT), merge_pokes(pokes, the_rect(INSIDE)))
    assert result.word(GL_RMSG) == WU["WM_REDRAW"]


def test_w_redraw_s_message_buffer_over_its_rectangle():
    """THE ORDER: the rectangle handed in is gl_rmsg itself, which ap_sendmsg overwrites — w_redraw copied it first."""
    pokes, window = top_window()
    rect = (40, 60, 50, 20)
    staged = bytes([case.SLACK_FILL]) * MESSAGE_RECT + vdi.pack_words(*rect)
    result = run(W_REDRAW, (window, GL_RMSG + MESSAGE_RECT), pokes, over=aes.field_pokes("AES", GL_RMSG=staged))
    assert posted(result) == redraw_message(window, rect)


# ---- w_update -----------------------------------------------------------------------------------------------------------------
CLEARED = wm.CLEARED                    # the screen at colour 0: every draw shows
held = wm.held                          # `(pokes, 1)`: top_window's machine with window drawing held (wind_set 13)


def test_w_update_while_drawing_is_held_stores_nothing():
    pokes, _window = held()
    result = run(W_UPDATE, (0, RECT, 0, 0), merge_pokes(pokes, the_rect(wm.SCREEN)))
    assert aes.stored_nothing(result)


@THROUGH
def test_w_update_with_no_window_cuts_the_rectangle_and_draws_nothing(through_line_f):
    """No window in the tree (its root has no child: bottom -1): the rectangle cut to gl_rfull in place, the cursor
    hidden and shown."""
    result = run(W_UPDATE, (0, RECT, 0, 0), merge_pokes(running(), the_rect(wm.SCREEN)), through_line_f=through_line_f)
    assert grect(result, RECT) == wm.DESKTOP_AREA


def test_w_update_draws_the_one_window():
    pokes, window = top_window()
    result = run(W_UPDATE, (0, RECT, 0, 0), merge_pokes(pokes, CLEARED, the_rect(wm.SCREEN)))
    assert posted(result) == redraw_message(window, (*WINDOW_AT[:2], WINDOW_AT[2] + wm.BORDER, WINDOW_AT[3] + wm.BORDER))


@pytest.mark.parametrize("bottom, top", ((0, 0), (1, 2), (2, 2), (1, 1)),
                         ids=("the whole tree", "named", "the top one alone", "the lower one alone"))
def test_w_update_draws_top_down(bottom, top):
    """Two windows: each from `top` down to `bottom` drawn — the last message posted is the bottom one's."""
    pokes, lower, upper = two_windows()
    result = run(W_UPDATE, (bottom, RECT | aes.BUS_TAG, top, 0), merge_pokes(pokes, CLEARED, the_rect(wm.SCREEN)))
    assert aes.signed(result.word(GL_RMSG + 6)) == (bottom or lower)


def test_w_update_skips_the_moved_top_window():
    """`moved`: the top window was blitted into place, so it alone is not redrawn — the one message is the lower one's."""
    pokes, lower, _upper = two_windows()
    result = run(W_UPDATE, (0, RECT, 0, 1), merge_pokes(pokes, CLEARED, the_rect(wm.SCREEN)))
    assert aes.signed(result.word(GL_RMSG + 6)) == lower


def test_w_update_of_a_moved_window_not_on_top_redraws_it():
    pokes, lower, _upper = two_windows()
    result = run(W_UPDATE, (lower, RECT, lower, 1), merge_pokes(pokes, CLEARED, the_rect(wm.SCREEN)))
    assert aes.signed(result.word(GL_RMSG + 6)) == lower


# ---- draw_change -------------------------------------------------------------------------------------------------------------
def change(pokes, window, rect, **kwargs):
    return run(DRAW_CHANGE, (window, RECT), merge_pokes(pokes, CLEARED, the_rect(rect)), **kwargs)


def current(result, window):
    return current_of(result.final, window)


# The changes of top_window's window, each one arm: (the rectangle, the arm).
CHANGES = {
    "moved, the same size: blitted": (60, 50, 200, 100),
    "moved over where it was: the old inside the new": (10, 20, 250, 150),
    "moved and resized away": (150, 100, 100, 60),
    "moved to nothing": (60, 50, 0, 0),
    "moved, a width of 0": (60, 50, 0, 100),
    "shrunk in place": (20, 30, 150, 80),
    "grown in place": (20, 30, 250, 150),
    "wider and lower in place": (20, 30, 250, 60),
    "unchanged on top": WINDOW_AT,
}


@pytest.mark.parametrize("rect", CHANGES.values(), ids=CHANGES)
def test_draw_change_of_the_top_window(rect):
    pokes, window = top_window()
    result = change(pokes, window, rect)
    assert current(result, window) == rect
    assert grect(result, window_record(window) + aes.WIN_PREV) == WINDOW_AT


@THROUGH
def test_draw_change_through_its_word(through_line_f):
    pokes, window = top_window()
    change(pokes, window, CHANGES["shrunk in place"], through_line_f=through_line_f)


def test_draw_change_while_drawing_is_held_draws_nothing():
    """The rectangles, the lists and the active window set; then nothing drawn — the screen as it was."""
    pokes, window = held()
    result = change(pokes, window, (60, 50, 200, 100))
    assert current(result, window) == (60, 50, 200, 100)
    assert not gsx_screen_changed(result)


def test_draw_change_of_a_lower_window_unchanged_draws_nothing_more():
    pokes, lower, _upper = two_windows()
    change(pokes, lower, WINDOW_AT)


LOWER_MOVES = {"the same size": (60, 50, 200, 100), "resized": (60, 50, 150, 80)}
# Two overlapping windows, of every gadget and of a title bar alone (the latter's changes priced, `_registered`).
TWO_OVERLAPPING = {"every gadget": two_windows, "a title bar": title_bar_windows}


@pytest.mark.parametrize("machine", TWO_OVERLAPPING.values(), ids=TWO_OVERLAPPING)
@pytest.mark.parametrize("rect", LOWER_MOVES.values(), ids=LOWER_MOVES)
def test_draw_change_of_a_lower_window_moved(rect, machine):
    """Not on top: never blitted — the old rectangle redrawn."""
    pokes, lower, _upper = machine()
    result = change(pokes, lower, rect)
    assert current(result, lower) == rect


def reordered(pokes, window):
    """`pokes` with `window` made the window tree's last child by the ROM's ob_order — what wind_set(WF_TOP) does
    before it hands draw_change the window's unchanged rectangle."""
    frame = aes_event.frame_of(("l", aes.AES_WINDOW_TREE), ("w", window), ("w", NIL))
    return rom_derived("AES_ROM_OB_ORDER", frame, pokes)


@pytest.mark.parametrize("machine", TWO_OVERLAPPING.values(), ids=TWO_OVERLAPPING)
def test_draw_change_of_a_window_brought_to_the_top(machine):
    """The lower window made the tree's last: the old top's gadgets redrawn as no longer on top, its rectangle added
    to what is redrawn — gl_wasclr is the snapshot's 0, so the whole change is redrawn."""
    pokes, lower, _upper = machine()
    result = change(reordered(pokes, lower), lower, WINDOW_AT)
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == lower
    assert grect(result, RECT) == WINDOW_AT, "the caller's rectangle overwritten by the new top's"


# ---- wm_opcl / wm_open / wm_close -------------------------------------------------------------------------------------------------
@THROUGH
def test_wm_open_opens_a_created_window(through_line_f):
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=running())
    result = run(WM_OPEN, (window, RECT), merge_pokes(pokes, CLEARED, the_rect(WINDOW_AT)), through_line_f=through_line_f)
    assert result.answer() == 0
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == window
    assert grect(result, window_record(window) + aes.WIN_PREV) == WINDOW_AT


def test_wm_open_at_the_screen_s_corner():
    """Opened at (0, 0): the same corner as its empty current rectangle — the change is a resize in place."""
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, 0, 0, 200, 100, onto=running())
    result = run(WM_OPEN, (window, RECT), merge_pokes(pokes, CLEARED, the_rect((0, 0, 200, 100))))
    assert current(result, window) == (0, 0, 200, 100)


def test_wm_open_with_the_lock_held_answers_its_caller_s_d0():
    """The application holds the lock (wind_update(BEG_UPDATE), the ROM's own): wm_opcl's release leaves it held, and
    D0 is the caller's (`aes/wmupdate.h`) — not compared."""
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=locked())
    result = run(WM_OPEN, (window, RECT), merge_pokes(pokes, the_rect(WINDOW_AT)), regs={"d0": CALLERS_D0},
                 answer_compared=False)
    assert spb(result) == (1, aes.SHELL_PD)


def test_wm_opcl_copies_the_rectangle_before_it_draws():
    """THE ORDER, as an overlap: the rectangle handed in is the window tree object's own (WS_CURR, which draw_change
    rewrites) — wm_opcl hands draw_change its frame's copy, and WS_PREV the caller's, read after."""
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=running())
    at = aes.AES_WINDOW_TREE + window * aes.OB_BYTES + aes.OB_X
    result = run(WM_OPCL, (window, at, 1), pokes)
    assert result.answer() == 0


@THROUGH
def test_wm_close_closes_the_top_window(through_line_f):
    pokes, window = top_window()
    result = run(WM_CLOSE, (window,), merge_pokes(pokes, CLEARED), through_line_f=through_line_f)
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == NIL
    assert gsx_screen_changed(result)


def test_wm_close_of_the_lower_window():
    pokes, lower, upper = two_windows()
    result = run(WM_CLOSE, (lower,), merge_pokes(pokes, CLEARED))
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == upper


# ---- wm_set -------------------------------------------------------------------------------------------------------------------
def window_set_case(pokes, window, field, *words, **kwargs):
    return run(WM_SET, (window, field, WORDS), merge_pokes(pokes, CLEARED, {WORDS: vdi.pack_words(*words)}), **kwargs)


@THROUGH
def test_wm_set_moves_the_window(through_line_f):
    pokes, window = top_window()
    result = window_set_case(pokes, window, WMH["WF_CURRXYWH"], *wm.MOVED_TO, through_line_f=through_line_f)
    assert result.answer() == 0
    assert current(result, window) == wm.MOVED_TO


def _deepest_case():
    """The battery's deepest ROM run, staged: draw_change of the lower of two windows moved and resized — `(arguments,
    pokes)`."""
    pokes, lower, _upper = two_windows()
    return (lower, RECT), merge_pokes(pokes, SLOTS, CLEARED, the_rect(LOWER_MOVES["resized"]))


def deepest_derivation():
    """The deepest ROM run of the battery (`_deepest_case`) watched at the door's entries as every case's ROM run is
    (`aes_event.rom_watched`): `(calls, memory, returned)`."""
    return aes_event.rom_watched(DRAW_CHANGE, *_deepest_case())


def test_the_longest_run_fits_the_cap():
    """The battery's cap is declared from this run (`aes_event.battery_cap` holds the declaration to it both ways):
    re-measured here."""
    staged = aes.staged(DRAW_CHANGE, *_deepest_case())
    _final, _writes, regs = emu.run(make_image(staged), addrs.AES_ROM_DRAW_CHANGE, max_insns=CASE_CAP.insns)
    assert regs["ninsns"] == DEEPEST_ROM_RUN_INSNS == CASE_CAP.deepest
    assert deepest_derivation()[2]


# A cap as a battery holds one whose deepest run was measured SHORTER than the run that now comes: built as declared
# (`aes_event.BatteryCap`), past `battery_cap`'s own vet of the declaration — which is the state these two refuse.
def test_a_run_inside_the_battery_s_cap_s_margin_is_refused_by_name(monkeypatch):
    """THE RED for the margin `run` holds every case to: under a cap the deepest run fits, but not by the margin, that
    case is refused by name — no hand-kept count has to notice a deeper case."""
    short = DEEPEST_ROM_RUN_INSNS * aes_event.DERIVATION_MARGIN - 1
    monkeypatch.setitem(globals(), "CASE_CAP", aes_event.BatteryCap(short, DEEPEST_ROM_RUN_INSNS))
    with pytest.raises(AssertionError, match=rf"inside its battery's declared cap's \({short}\) margin of 5"):
        run(DRAW_CHANGE, *_deepest_case())


def test_a_run_past_the_battery_s_cap_is_refused_by_name(monkeypatch):
    """...and a ROM run past the cap itself is refused by the cap's name, not the oracle's bare overrun."""
    short = DEEPEST_ROM_RUN_INSNS - 1
    monkeypatch.setitem(globals(), "CASE_CAP", aes_event.BatteryCap(short, DEEPEST_ROM_RUN_INSNS))
    with pytest.raises(AssertionError, match=rf"did not return within its declared cap \({short}\)"):
        run(DRAW_CHANGE, *_deepest_case())


def test_a_raw_instruction_cap_is_no_way_round_the_battery_s(monkeypatch):
    """...and `max_insns`, the spelling this battery's cases used before the cap had one door, is refused by name."""
    with pytest.raises(AssertionError, match="a raw max_insns .* was handed past the cap's door"):
        run(DRAW_CHANGE, *_deepest_case(), max_insns=CASE_CAP.insns)


@pytest.mark.parametrize("field, gadget", (("WF_NAME", "NAME"), ("WF_INFO", "INFO")))
def test_wm_set_a_string(field, gadget):
    pokes, window = top_window()
    result = window_set_case(merge_pokes(pokes, {TITLE_AT: TITLE}), window, WU[field], TITLE_AT >> 16, TITLE_AT & 0xFFFF)
    assert result.long(window_record(window) + getattr(aes, f"WIN_{gadget}")) == TITLE_AT


def test_wm_set_a_string_of_a_lower_window():
    pokes, lower, _upper = two_windows()
    result = window_set_case(merge_pokes(pokes, {TITLE_AT: TITLE}), lower, WU["WF_NAME"], TITLE_AT >> 16,
                             TITLE_AT & 0xFFFF)
    assert result.long(window_record(lower) + aes.WIN_NAME) == TITLE_AT


@pytest.mark.parametrize("machine", TWO_OVERLAPPING.values(), ids=TWO_OVERLAPPING)
def test_wm_set_top_brings_up_a_covered_window(machine):
    """Overlapping: the lower window was broken (gl_wasclr 0), so the change is redrawn whole."""
    pokes, lower, _upper = machine()
    result = window_set_case(pokes, lower, WMH["WF_TOP"], 0)
    assert result.word(GL_WASCLR) == 0
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == lower


def test_wm_set_top_brings_up_a_whole_window():
    """Side by side: neither window is cut, so only the gadgets of the two are redrawn (draw_change's early return)."""
    pokes, first, _second = side_by_side()
    result = window_set_case(pokes, first, WMH["WF_TOP"], 0)
    assert result.word(GL_WASCLR) == 1
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == first


def test_wm_set_top_of_the_top_window_does_nothing():
    pokes, window = top_window()
    window_set_case(pokes, window, WMH["WF_TOP"], 0)


@functools.cache
def all_closed_after_a_whole_top():
    """gl_wasclr left 1 by the ROM's wind_set(WF_TOP) of a whole window, then both windows closed by the ROM's
    wm_close: no window open, gl_wtop -1 — and a window created, to be opened."""
    pokes, first, second = side_by_side()
    pokes = window_set(pokes, first, WMH["WF_TOP"], 0)
    for window in (first, second):
        pokes = rom_derived("AES_ROM_WM_CLOSE", aes_event.frame_of(("w", window)), pokes)
    return aes_event.window_created(aes_event.EVERY_GADGET, 0, 0, 0, 0, onto=pokes)


def test_wm_open_after_a_whole_top_left_gl_wasclr_set():
    """A window opened empty at (0, 0) — its rectangle unchanged — with no window before it (the old top -1) and
    gl_wasclr still 1 from the last WF_TOP: draw_change takes the change as a whole window brought up."""
    pokes, window = all_closed_after_a_whole_top()
    assert case.word_in(make_image(pokes), GL_WASCLR) == 1
    result = run(WM_OPEN, (window, RECT), merge_pokes(pokes, the_rect((0, 0, 0, 0))))
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == window


@pytest.mark.parametrize("window", (1, 0), ids=("held", "released"))
def test_wm_set_13(window):
    pokes = held()[0] if window == 0 else top_window()[0]
    result = window_set_case(pokes, window, WMH["WF_RESVD"], *wm.SCREEN)
    assert result.word(aes.AES_GL_WFROZEN) == (1 if window else 0)


RELEASED_AREA = (40, 40, 100, 60)      # inside top_window's window: the desk and the window redrawn under it alone


def test_wm_set_13_releases_drawing_over_an_area():
    """Released (window 0) with an area of the window rather than the whole screen: the desk and the window redrawn
    under that area alone (w_drawdesk, w_update)."""
    pokes, _window = held()
    result = window_set_case(pokes, DESKTOP, WMH["WF_RESVD"], *RELEASED_AREA)
    assert result.word(aes.AES_GL_WFROZEN) == 0
    assert gsx_screen_changed(result)


def test_wm_set_newdesk():
    pokes, _window = top_window()
    result = window_set_case(pokes, DESKTOP, WMH["WF_NEWDESK"], 0x1234, 0x5678, 3)
    assert result.long(aes.AES_GL_NEWDESK) == 0x12345678
    assert result.word(aes.AES_GL_NEWROOT) == 3


SLIDER_VALUES = {"below -1": (-5, -1), "-1": (-1, -1), "inside": (500, 500), "past the scale": (2000, SLIDER_SCALE)}
SLIDER_FIELDS = {"WF_HSLIDE": "HSLIDE", "WF_VSLIDE": "VSLIDE", "WF_HSLSIZE": "HSLSIZE", "WF_VSLSIZE": "VSLSIZE"}


@pytest.mark.parametrize("field", SLIDER_FIELDS)
@pytest.mark.parametrize("value, stored", SLIDER_VALUES.values(), ids=SLIDER_VALUES)
def test_wm_set_a_slider(field, value, stored):
    """The caller's word clamped IN PLACE, then stored in the record; the top window's slider redrawn."""
    pokes, window = top_window()
    result = window_set_case(pokes, window, WMH[field], value)
    assert aes.signed(result.word(WORDS)) == stored
    assert aes.signed(result.word(window_record(window) + getattr(aes, f"WIN_{SLIDER_FIELDS[field]}"))) == stored


def test_wm_set_a_slider_of_a_lower_window_draws_nothing():
    pokes, lower, _upper = two_windows()
    result = window_set_case(pokes, lower, WMH["WF_VSLIDE"], 300)
    assert aes.signed(result.word(window_record(lower) + aes.WIN_VSLIDE)) == 300


def test_wm_set_s_slider_clamp_reads_its_word_back():
    """THE ORDER, as an overlap: the words laid over gl_wtop — the clamp's store to it moves the top window before the
    redraw's test reads it."""
    pokes, window = top_window()
    result = run(WM_SET, (window, WMH["WF_HSLIDE"], aes.AES_GL_WTOP), merge_pokes(pokes, CLEARED),
                 over={aes.AES_GL_WTOP: vdi.pack_words(2000)})
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == SLIDER_SCALE


@pytest.mark.parametrize("field", (1, 4, 6, 7, 11, 12, 17, -1), ids=lambda field: f"field {field}")
def test_wm_set_of_a_field_with_no_arm_sets_nothing(field):
    """Only the lock taken and released."""
    pokes, window = top_window()
    window_set_case(pokes, window, field, 1, 2, 3, 4)


# ---- draw_change: every arm's own distinction ---------------------------------------------------------------------------
# Each case below separates two arms the cases above treat alike: a move in one direction only, a resize of one extent
# only, a window whose rectangles differ, a third window between the changed one and the top.
ONE_WAY = {
    "moved across only": (60, 30, 200, 100),
    "moved down only": (20, 60, 200, 100),
    "wider only": (20, 30, 250, 100),
    "taller only": (20, 30, 200, 150),
    "lower only": (20, 30, 200, 80),
    "narrower and taller": (20, 30, 150, 150),
    "moved, the same width, lower": (60, 50, 200, 80),
    "moved, a height of 0": (60, 50, 150, 0),
    # ...and an empty rectangle OUTSIDE the old one: the zero test skips rc_union, which writes its union INTO the old
    # rectangle — a test of one extent alone would redraw the two's union, larger than the old one.
    "moved far away, a height of 0": (250, 170, 50, 0),
    "moved far away, a width of 0": (250, 170, 0, 20),
    "moved over it but for its top": (10, 40, 250, 150),
    "moved off the right edge: not blitted": (250, 30, 200, 100),
}


@pytest.mark.parametrize("rect", ONE_WAY.values(), ids=ONE_WAY)
def test_draw_change_one_way(rect):
    pokes, window = top_window()
    result = change(pokes, window, rect)
    assert current(result, window) == rect


def test_draw_change_of_a_moved_window_keeps_where_it_was_as_its_previous():
    """Moved already (its previous rectangle WINDOW_AT, its current MOVED_TO): changed again, the previous one is
    MOVED_TO — w_setsize(WS_PREV) of the current before the current is set."""
    pokes, window = wm.moved()
    result = change(pokes, window, (40, 40, 200, 100))
    assert grect(result, window_record(window) + aes.WIN_PREV) == wm.MOVED_TO


@pytest.mark.parametrize("empty", ((60, 50, 0, 100), (60, 50, 150, 0)), ids=("no width", "no height"))
def test_draw_change_of_a_window_with_an_empty_rectangle(empty):
    """Its current rectangle empty in one extent (the ROM's own wind_set made it so): moved elsewhere, the old one is
    simply replaced by the new."""
    pokes, window = top_window()
    pokes = window_set(pokes, window, WMH["WF_CURRXYWH"], *empty)
    result = change(pokes, window, (100, 80, 120, 60))
    assert current(result, window) == (100, 80, 120, 60)


@functools.cache
def three_windows():
    """`(pokes, bottom, middle, top)`: two_windows' pair and a third over both, every one of them overlapping."""
    pokes, lower, middle = two_windows()
    pokes, top = aes_event.window_chain(aes_event.EVERY_GADGET, 60, 60, 120, 80, onto=pokes)
    return pokes, lower, middle, top


def test_draw_change_shrinking_a_window_two_below_the_top():
    """Shrunk in place, the bottom of three: the redraw stops at it (w_update from it down), so the middle window —
    between it and the top — is not redrawn."""
    pokes, bottom, _middle, _top = three_windows()
    result = change(pokes, bottom, (20, 30, 150, 80))
    assert aes.signed(result.word(GL_RMSG + 6)) == bottom


@functools.cache
def held_and_reordered():
    """two_windows' machine with window drawing held (the ROM's wind_set(13)) and the lower window then made the tree's
    last by the ROM's ob_order — a WF_TOP's change while drawing is held."""
    pokes, lower, _upper = two_windows()
    return reordered(window_set(pokes, lower, WMH["WF_RESVD"], 0), lower), lower


def test_draw_change_while_drawing_is_held_leaves_the_caller_s_rectangle():
    """Held, the top changed: the ROM returns before the change is drawn — the caller's rectangle, which the redraw
    would overwrite with the new top's, left as it was, and no gadget tree built."""
    pokes, lower = held_and_reordered()
    result = change(pokes, lower, WINDOW_AT)
    assert grect(result, RECT) == WINDOW_AT
    assert not gsx_screen_changed(result)


def test_draw_change_of_a_window_brought_to_the_top_under_a_small_clip():
    """The old top's gadgets redrawn under its whole rectangle (w_cpwalk's `use_true`), not the clip as it stands: the
    clip left small by the ROM's own gsx_sclip first."""
    pokes, lower, _upper = two_windows()
    clipped = merge_pokes(od.clip_set_by_the_rom(RECT, merge_pokes(reordered(pokes, lower), the_rect((0, 0, 16, 16)))),
                          gsx.CONTRL_STALE)
    change(clipped, lower, WINDOW_AT)


def test_w_update_under_a_small_rectangle():
    """Each window's gadgets drawn under the clip — the rectangle cut — the lower one's not under its whole rectangle."""
    pokes, lower, _upper = two_windows()
    result = run(W_UPDATE, (0, RECT, 0, 0), merge_pokes(pokes, CLEARED, the_rect((40, 60, 50, 20))))
    assert aes.signed(result.word(GL_RMSG + 6)) == lower


def test_wm_close_of_the_top_of_two():
    """The top window closed: the new top's rectangle (copied over the frame's) joined to the closed one's, and the
    closed window's gadgets NOT redrawn (it was the old top)."""
    pokes, lower, upper = two_windows()
    result = run(WM_CLOSE, (upper,), merge_pokes(pokes, CLEARED))
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == lower


def test_wm_open_of_its_own_previous_rectangle_sets_it_from_the_caller_s():
    """THE ORDER, as an overlap: a closed window reopened at the address of its own previous rectangle (WIN_PREV, which
    its close left WINDOW_AT). draw_change rewrites WIN_PREV with the current one (empty after the close); then
    wm_opcl's w_setsize(WS_PREV) copies from the CALLER's pointer — the word draw_change just stored — not its copy."""
    pokes, window = top_window()
    closed = rom_derived("AES_ROM_WM_CLOSE", aes_event.frame_of(("w", window)), pokes)
    prev = window_record(window) + aes.WIN_PREV
    assert wm.rect_of(make_image(closed), prev - aes.ORECT_X) == WINDOW_AT
    result = run(WM_OPEN, (window, prev), merge_pokes(closed, CLEARED))
    assert grect(result, prev) == (0, 0, 0, 0)


def test_wm_set_13_with_a_negative_handle_holds_drawing():
    """Any non-zero handle holds drawing — -1 too (`tst.w`)."""
    pokes, window = top_window()
    result = window_set_case(pokes, NIL, WMH["WF_RESVD"], *wm.SCREEN)
    assert result.word(aes.AES_GL_WFROZEN) == 1


def test_wm_set_top_of_a_whole_window_under_a_small_clip():
    """Side by side, the clip left small by the ROM's own gsx_sclip: brought up whole, only the two windows' gadgets
    are drawn and nothing redraws over them — the old top's under ITS whole rectangle (`use_true`), not the clip."""
    pokes, first, _second = side_by_side()
    clipped = merge_pokes(od.clip_set_by_the_rom(RECT, merge_pokes(pokes, the_rect((0, 0, 16, 16)))), gsx.CONTRL_STALE)
    result = window_set_case(clipped, first, WMH["WF_TOP"], 0)
    assert result.word(GL_WASCLR) == 1


def test_draw_change_of_a_window_off_the_right_edge_moved_back():
    """Off the right edge and moved left, the same size, on top: w_move cannot blit it (it answers 0, the redraw the
    two rectangles' union), so the top window is NOT skipped by the redraw — the answer, not the call, decides."""
    pokes, window = aes_event.window_chain(aes_event.EVERY_GADGET, 250, 30, 200, 100, onto=running())
    result = change(pokes, window, (100, 30, 200, 100))
    assert current(result, window) == (100, 30, 200, 100)


# ---- the drawing door users in a child ---------------------------------------------------------------------------
def _drawn(pokes, over=None):
    """The layers of `pokes` with the screen cleared (every draw shows) and `over` laid last (`with_stale_slots`)."""
    return pokes, CLEARED, over


def _opened_created():
    pokes, window = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=running())
    return (window, RECT), _drawn(pokes, the_rect(WINDOW_AT))


def _screen_updated(machine, values):
    return values, _drawn(machine()[0], the_rect(wm.SCREEN))


def _changed_to(machine, rect):
    """draw_change of `machine`'s second element (its window) to `rect`."""
    pokes, window = machine()[:2]
    return (window, RECT), _drawn(pokes, the_rect(rect))


def _lower_of(machine, rect):
    pokes, lower, _upper = machine()
    return (lower, RECT), _drawn(pokes, the_rect(rect))


def _brought_up(machine):
    pokes, lower, _upper = machine()
    return (lower, RECT), _drawn(reordered(pokes, lower), the_rect(WINDOW_AT))


def _released_over_an_area():
    return (DESKTOP, WMH["WF_RESVD"], WORDS), _drawn(held()[0], {WORDS: vdi.pack_words(*RELEASED_AREA)})


def _covered_topped(machine):
    pokes, lower, _upper = machine()
    return (lower, WMH["WF_TOP"], WORDS), _drawn(pokes, {WORDS: vdi.pack_words(0)})


# `label: (core, () -> (values, machine))` — every arm that walks the window tree (just_draw, newrect, mkrect handed
# by value), each run first in a child with those routines served by the child's own cores (`aes_event.child_binding`).
DRAWING_CHILD_CALLS = {
    "w_update, two windows": (W_UPDATE, lambda: _screen_updated(two_windows, (0, RECT, 0, 0))),
    "w_update, three windows": (W_UPDATE, lambda: _screen_updated(three_windows, (0, RECT, 0, 0))),
    "w_update, the lower one alone": (W_UPDATE, lambda: _screen_updated(two_windows, (1, RECT, 1, 0))),
    "w_update, the moved top skipped": (W_UPDATE, lambda: _screen_updated(two_windows, (0, RECT, 0, 1))),
    "draw_change, shrunk in place": (DRAW_CHANGE, lambda: _changed_to(top_window, CHANGES["shrunk in place"])),
    "draw_change, moved: blitted": (DRAW_CHANGE, lambda: _changed_to(top_window, CHANGES["moved, the same size: blitted"])),
    "draw_change of the bottom of three": (DRAW_CHANGE, lambda: _changed_to(three_windows, (20, 30, 150, 80))),
    "draw_change of a lower window moved": (DRAW_CHANGE, lambda: _lower_of(title_bar_windows, LOWER_MOVES["resized"])),
    "draw_change of a window brought to the top": (DRAW_CHANGE, lambda: _brought_up(title_bar_windows)),
    "wm_open of a created window": (WM_OPEN, _opened_created),
    "wm_close of the top of two": (WM_CLOSE, lambda: ((two_windows()[2],), _drawn(two_windows()[0]))),
    "wm_close of the lower of two": (WM_CLOSE, lambda: ((two_windows()[1],), _drawn(two_windows()[0]))),
    "wm_set, top: a covered window": (WM_SET, lambda: _covered_topped(title_bar_windows)),
    "wm_set, drawing released over an area": (WM_SET, _released_over_an_area),
}


@pytest.mark.parametrize("name, call", DRAWING_CHILD_CALLS.values(), ids=DRAWING_CHILD_CALLS)
def test_each_drawing_call_returns_in_a_child(name, call):
    """Each arm that walks the window tree returns in a child, the walked routines served by the CHILD's own cores —
    the child binding's own pin (every in-process case is guarded the same way first, `run`)."""
    values, layers = call()
    aes_event.returns_in_a_child(name, values, with_stale_slots(*layers), objects=True)


# ---- the registry ---------------------------------------------------------------------------------------------------------
# Priced rows, each over the machine its Tier 1 case runs on. Two overlapping windows' changes are priced over windows
# of a title bar alone (TITLE_BAR_KIND): of every gadget they are past the bench's cap (the oracle's default 200,000
# instructions, which Tier 3 runs both sides at) — draw_change of a lower window moved (240,198 / 244,097), of a window
# brought to the top (232,502), wind_set(WF_TOP) of a covered window (233,112) — and verified at Tier 1 alone. So is
# wind_set(13, 0) releasing held drawing over the whole screen (217,989): it is priced over an area of the window.
# Measured (a coverage build over every priced row's companion), what no row prices: ev_block's wait (it blocks — no
# run returns from it), and arms that are no routine's worst — window_below's walk past one sibling, wind_set of
# WF_HSLSIZE / WF_VSLSIZE / WF_INFO, wind_set(WF_TOP) of the window already on top. Each is verified at Tier 1 above.
def _row(label, name, arguments, machine, *over, **kwargs):
    aes_event.register(label, name, arguments, with_stale_slots(machine, *over), drawing=True, objects=WALKERS,
                       **kwargs)


def _drawn_row(label, name, call):
    values, layers = call
    _row(label, name, values, *layers)


def _registered():
    tw, window = top_window()
    two, lower, _upper = two_windows()
    sides, first, _second = side_by_side()
    created, new = aes_event.window_created(aes_event.EVERY_GADGET, *WINDOW_AT, onto=running())
    leaf_machine = aes.leaf_machine()
    aes.register("a rectangle", SET_CTRL, (RECT,), merge_pokes(leaf_machine, the_rect(A_RECT)))
    aes.register("the control rectangle", GET_CTRL, (RECT,), merge_pokes(leaf_machine, wm.STALE_RECTS))
    aes.register("both owners", GET_MOWN, (OUT, OUT + aes.LONG_BYTES), merge_pokes(leaf_machine, wm.STALE_RECTS))
    _row("the lock taken", WM_UPDATE, (BEG_UPDATE,), running())
    _row("the lock taken again", WM_UPDATE, (BEG_UPDATE,), locked())
    _row("the lock released", WM_UPDATE, (END_UPDATE,), locked())
    _row("one level of the lock released", WM_UPDATE, (END_UPDATE,), locked(times=2), answer_compared=False)
    _row("3: the screen taken", WM_UPDATE, (BEG_MCTRL,), running())
    _row("2: the screen given back", WM_UPDATE, (END_MCTRL,), owned())
    _row("taken", FM_OWN, (1,), running())
    _row("taken again", FM_OWN, (1,), owned())
    _row("given back", FM_OWN, (0,), owned())
    _row("taken by the screen manager", FM_OWN, (1,), screen_manager_running())
    _row("the top window's", W_SETACTIVE, (), tw)
    _row("no window: the desktop's", W_SETACTIVE, (), running())
    _row("a redraw posted", W_REDRAW, (window, RECT), tw, the_rect(INSIDE))
    _row("outside the work area", W_REDRAW, (window, RECT), tw, the_rect((0, 0, 10, 10)))
    _row("a covered part", W_REDRAW, (covered_right()[1], RECT), covered_right()[0], the_rect((150, 60, 20, 20)))
    _row("two windows", W_UPDATE, (0, RECT, 0, 0), two, CLEARED, the_rect(wm.SCREEN))
    _row("one window", W_UPDATE, (0, RECT, 0, 0), tw, CLEARED, the_rect(wm.SCREEN))
    _row("no window", W_UPDATE, (0, RECT, 0, 0), running(), the_rect(wm.SCREEN))
    _row("drawing held", W_UPDATE, (0, RECT, 0, 0), held()[0], the_rect(wm.SCREEN))
    for label in ("moved, the same size: blitted", "moved and resized away", "moved over where it was: the old inside "
                  "the new", "shrunk in place", "unchanged on top"):
        _row(label, DRAW_CHANGE, (window, RECT), tw, CLEARED, the_rect(CHANGES[label]))
    for label, rect in LOWER_MOVES.items():
        _drawn_row(f"a lower window moved, {label} (a title bar)", DRAW_CHANGE, _lower_of(title_bar_windows, rect))
    _drawn_row("a window brought to the top (a title bar)", DRAW_CHANGE, _brought_up(title_bar_windows))
    _drawn_row("top: a covered window (a title bar)", WM_SET, _covered_topped(title_bar_windows))
    _drawn_row("drawing released over an area", WM_SET, _released_over_an_area())
    _row("drawing held", DRAW_CHANGE, (window, RECT), held()[0], CLEARED, the_rect((60, 50, 200, 100)))
    _row("a created window added", WM_OPCL, (new, RECT, 1), created, CLEARED, the_rect(WINDOW_AT))
    _row("a created window", WM_OPEN, (new, RECT), created, CLEARED, the_rect(WINDOW_AT))
    _row("the top window", WM_CLOSE, (window,), tw, CLEARED)
    _row("the lower window", WM_CLOSE, (lower,), two, CLEARED)
    for label, (pokes, target, field, words) in {
            "moved": (tw, window, WMH["WF_CURRXYWH"], wm.MOVED_TO),
            "a slider of the top window": (tw, window, WMH["WF_HSLIDE"], (2000,)),
            "a slider of a lower window": (two, lower, WMH["WF_VSLIDE"], (300,)),
            "a title": (merge_pokes(tw, {TITLE_AT: TITLE}), window, WU["WF_NAME"], (TITLE_AT >> 16, TITLE_AT & 0xFFFF)),
            "drawing held": (tw, window, WMH["WF_RESVD"], wm.SCREEN),
            "a new desk": (tw, DESKTOP, WMH["WF_NEWDESK"], (0x1234, 0x5678, 3)),
            "a field with no arm": (tw, window, WMH["WF_WORKXYWH"], (1, 2, 3, 4)),     # wind_get's alone
            "top: a whole window": (sides, first, WMH["WF_TOP"], (0,))}.items():
        _row(label, WM_SET, (target, field, WORDS), pokes, CLEARED, {WORDS: vdi.pack_words(*words)})


_registered()
