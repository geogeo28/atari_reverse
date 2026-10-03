"""AES gemgrlib's box loops that FOLLOW THE MOUSE until the button rises — `src/aes/grdrag.c` (`aes/grdrag.h`), their
wait gr_stilldn's through the event door (`test/aes_event.py`), the screen lock round them wm_update's.

    gr_wait(po, poff, mx, my)    two = !rc_equal(&gl_rzero, poff); gr_xdraw (gsx_moff; gsx_xbox(po); two ?
                                 gsx_xbox(po + poff, word by word); gsx_mon); r = gr_stilldn(1, mx, my, 1, 1);
                                 gr_xdraw again; r
    gr_clamp(x, y, mw, mh, &w, &h)   gsx_mxmy into its frame; *w = max(mx - x + 1, mw); *h = max(my - y + 1, mh)
    gr_rubwind(x, y, mw, mh, poff, &w, &h)   wm_update(1); gr_setup(1); r = (x, y, 0, 0); until gr_wait(&r, poff,
                                 x + w - 1, y + h - 1) is 0: gr_clamp(x, y, mw, mh, &r.w, &r.h); *w, *h = r.w, r.h;
                                 wm_update(0)
    gr_rubbox(x, y, mw, mh, &w, &h)  gr_rubwind(..., &gl_rzero, ...) — gr_wait's immediate read as data
    gr_dragbox(w, h, x, y, b, &x, &y)  wm_update(1); gr_setup(1); r = (x, y, w, h); gr_clamp(x + 1, y + 1, 0, 0,
                                 &dx, &dy); until gr_wait(&r, &gl_rzero, mx, my) is 0: gsx_mxmy(&mx, &my);
                                 r.x = mx - dx, r.y = my - dy; rc_constrain(b, &r); *x, *y = r.x, r.y; wm_update(0)
    gr_slidebox(t, p, o, v)      ob_actxywh(t, p, &pr); ob_relxywh(t, o, &or); gr_dragbox(or.w, or.h, or.x + pr.x,
                                 or.y + pr.y, &pr, &or.x, &or.y); room = pr.size - or.size along v's axis;
                                 room ? mul_div(or.pos - pr.pos, 1000, room) : 0

THE MACHINES, each the ROM scheduler's own (`aes_event.machine`): PD0 running, woken by a key — the button UP — with
the mouse where the snapshot holds it (159, 99), or moved first (`aes_event.mouse_moved_to`, the dispatcher's forker
taking the motion as it wakes PD0); and PD0 woken by the left button's press — the button DOWN. Each with the cursor
hidden (an application's graf_mouse(M_OFF)) or SHOWN (`aes_event.shown_machine`: what an application's graf_dragbox /
graf_rubberbox usually runs over, gr_xdraw hiding it round each box). Real data: the file selector's slider (the AES
resource's tree 0, track 10, elevator 11), and a window's sliders in W_ACTIVE as the ROM's own w_bldactive builds them
(`test_aes_wmlib`'s window with its sliders set by the ROM's wm_set).

WHAT ONE RUN REACHES, AND WHAT INTERRUPTS DO. With the button up every loop ends after one step (gr_stilldn answers
the rise first). With the button down and the mouse still, a step waits for the mouse to LEAVE the pixel it is on: a
wait nothing satisfies, REFUSED by the door (would block), the C held to the ROM's own run stopped where it blocks
(`aes_event.refused_where_the_rom_blocks`, the whole image). Every later step is reached as the machine reaches it —
the mouse moved and the button released by the ROM's own interrupt code at the entry of a step's wait, on both shores
(`aes_event.interrupted`): a drag the mouse really moved, a box stretched, gr_rubwind's busy loop (its corner held at
its minimum away from the mouse, each wait satisfied at once) ended when the button rises.
"""
import functools
import struct

import pytest

from harness import addrs, make_image

import aes
import aes_event
import aes_gsx as gsx
import case
import test_aes_wmlib as wmlib
import vdi
from case import merge_pokes
from test_aes_gsx import screen_changed
from test_aes_strings import mul_div_model

L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
SIGNATURES = {
    "AES_ROM_GR_WAIT": (aes.WORD_ANSWER, (I, L, L, W, W)),
    "AES_ROM_GR_CLAMP": (None, (I, W, W, W, W, L, L)),
    "AES_ROM_GR_RUBWIND": (None, (I, W, W, W, W, L, L, L)),
    "AES_ROM_GR_RUBBOX": (None, (I, W, W, W, W, L, L)),
    "AES_ROM_GR_DRAGBOX": (None, (I, W, W, W, W, L, L, L)),
    "AES_ROM_GR_SLIDEBOX": (aes.WORD_ANSWER, (I, L, W, W, W)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
GR_WAIT, GR_CLAMP, GR_RUBWIND, GR_RUBBOX, GR_DRAGBOX, GR_SLIDEBOX = SIGNATURES
GRDRAG = aes.header_constants("grdrag.h")

THROUGH = gsx.THROUGH
SNAPSHOT_MOUSE = (159, 99)
SELECTOR = aes.resource_tree(0)
TRACK, ELEVATOR = 10, 11                # the selector's slider: its track and its elevator (vertical)
SCREEN = aes.AES_GL_RSCREEN
ZERO = aes.AES_GL_RZERO

# The band: a GRECT a case hands in (a bound, a box), an offset GRECT, and two answer words.
BAND_OFFSET = 0x3900                    # just past test_aes_mnlib.py's
BAND_BYTES = 0x40
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/test_aes_grdrag.py: GRECTs and answers")
RECT_AT = BAND_AT
OFFSET_AT = BAND_AT + aes.GRECT_BYTES
ANSWERS_AT = BAND_AT + 2 * aes.GRECT_BYTES
FIRST_OUT, SECOND_OUT = ANSWERS_AT, ANSWERS_AT + aes.WORD_BYTES
STALE_BAND = {BAND_AT: vdi.pack_words(*[aes.STALE_WORD] * (BAND_BYTES // aes.WORD_BYTES))}
STALE_SLOTS = merge_pokes(*(aes.stale_host_slot(role) for role in ("AES_GR_DRAW_RECT", "AES_GR_CLAMP_MOUSE",
                                                                   "AES_GR_RUBWIND_RECT", "AES_GR_DRAGBOX_FRAME",
                                                                   "AES_GR_SLIDEBOX_RECTS")))


def rect_pokes(x, y, w, h, at=RECT_AT):
    return {at: struct.pack(">4h", x, y, w, h)}


# ---- the machines -----------------------------------------------------------------------------------------------------
def _stale(machine):
    return merge_pokes(machine, STALE_BAND, STALE_SLOTS)


@functools.cache
def running():
    """PD0 running, the button UP, the mouse the snapshot's."""
    return _stale(aes_event.machine())


@functools.cache
def button_down():
    """PD0 running, woken by the left button's press: the button DOWN, the mouse the snapshot's."""
    return _stale(aes_event.machine(aes_event.button_down))


@functools.cache
def shown_running():
    """`running()` with the cursor SHOWN — nothing hid it (`aes_event.shown_machine`)."""
    return _stale(aes_event.shown_machine())


@functools.cache
def shown_button_down():
    """`button_down()` with the cursor SHOWN."""
    return _stale(aes_event.shown_machine(aes_event.button_down))


@functools.cache
def _key_with_the_mouse_at(x, y):
    moved = aes_event.mouse_moved_to(x, y, {})
    return aes_event.woken_by_a_key(moved)


@functools.cache
def mouse_at(x, y):
    """PD0 running, the button up, the mouse MOVED to (x, y) before the key woke it: the dispatcher's forker takes the
    motion and the key alike."""
    return _stale(aes_event.machine(functools.partial(_key_with_the_mouse_at, x, y)))


def test_the_machines_hold_the_mouse_the_button_and_the_cursor_they_say():
    for machine, mouse, button, cursor in ((running(), SNAPSHOT_MOUSE, 0, gsx.NEST_HIDDEN),
                                           (button_down(), SNAPSHOT_MOUSE, 1, gsx.NEST_HIDDEN),
                                           (mouse_at(188, 110), (188, 110), 0, gsx.NEST_HIDDEN),
                                           (shown_running(), SNAPSHOT_MOUSE, 0, gsx.NEST_SHOWN),
                                           (shown_button_down(), SNAPSHOT_MOUSE, 1, gsx.NEST_SHOWN)):
        image = make_image(machine)
        assert (case.word_in(image, aes.AES_XRAT), case.word_in(image, aes.AES_YRAT)) == mouse
        assert case.word_in(image, aes.AES_BUTTON) == button
        assert aes.read_field(image, "AES", "GL_MOFF") == cursor
        assert aes_event.scheduler_state(image, aes.SHELL_PD) == aes_event.running_as_switchto_leaves_it(aes.SHELL_PD)


def run(name, arguments, machine, **kwargs):
    """A door user's run, its C first in a child (`aes_event.run_guarded`)."""
    return aes_event.run_guarded(name, arguments, machine, drawing=True, **kwargs)


# The door calls a loop's first step makes: the screen lock taken (wm_update's tak_flag), then gr_stilldn's wait.
LOCKED_THEN_WAITING = [addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_EV_MULTI]


def blocked_calls(name, arguments, machine):
    """The routines of the door calls a call that BLOCKS made, the C held to the ROM up to the blocking one
    (`aes_event.refused_where_the_rom_blocks`)."""
    return [call.routine for call in aes_event.refused_where_the_rom_blocks(name, arguments, machine).calls]


# ---- gr_wait ---------------------------------------------------------------------------------------------------------------
# (machine, the box, the offset box or gl_rzero, the pixel, answer): the button up — it rose, one box or two; the button
# down and the pixel away from the mouse — it left, still down.
BOX = (100, 50, 40, 20)
TWIN_OFFSET = (-1, -12, 2, 13)          # a window's outline: the current rectangle to its border (`ctx`)
GR_WAIT_CASES = {
    "the button up, one box: it rose": (running, ZERO, SNAPSHOT_MOUSE, 0),
    "the button up, two boxes": (running, OFFSET_AT, SNAPSHOT_MOUSE, 0),
    "the button down, the pixel away from the mouse: it left": (button_down, ZERO, (139, 69), 1),
    "the button down, two boxes, the pixel away": (button_down, OFFSET_AT, (10, 20), 1),
}


@functools.cache
def set_up(machine):
    """`machine()` continued from the ROM's own gr_setup(1) — the screen clip and XOR, as every loop sets them before its
    first gr_wait."""
    return wmlib.rom_derived(addrs.AES_ROM_GR_SETUP, aes_event.frame_of(("w", GRDRAG["GR_DRAG_COLOUR"])), machine())


@functools.cache
def waiting_over(machine):
    """`set_up(machine)` with gr_wait's box and its offset twin staged (BOX, TWIN_OFFSET)."""
    return merge_pokes(set_up(machine), gsx.CONTRL_STALE, rect_pokes(*BOX), rect_pokes(*TWIN_OFFSET, at=OFFSET_AT))


def gr_wait(machine, offset, pixel, box=RECT_AT, pokes=None, **kwargs):
    return run(GR_WAIT, (box, offset, *pixel), merge_pokes(waiting_over(machine), pokes), **kwargs)


@pytest.mark.parametrize("machine, offset, pixel, answer", GR_WAIT_CASES.values(), ids=GR_WAIT_CASES)
def test_gr_wait(machine, offset, pixel, answer):
    result = gr_wait(machine, offset, pixel)
    assert result.answer() == answer
    assert not screen_changed(result), "the box drawn and drawn away"


def test_gr_wait_waits_for_the_pixel_the_mouse_is_on_to_be_left():
    """The button down and the pixel the mouse's own: nothing satisfies the wait — refused where the ROM's blocks, the
    box left drawn."""
    assert blocked_calls(GR_WAIT, (RECT_AT, OFFSET_AT, *SNAPSHOT_MOUSE), waiting_over(button_down)) == \
        [addrs.AES_ROM_EV_MULTI]


def test_gr_wait_s_offset_equal_to_gl_rzero_by_value_draws_one_box():
    """rc_equal compares the offset's WORDS: an empty GRECT elsewhere is gl_rzero's twin, and one box is drawn."""
    result = gr_wait(running, OFFSET_AT, SNAPSHOT_MOUSE, pokes=rect_pokes(0, 0, 0, 0, at=OFFSET_AT))
    assert result.answer() == 0


def test_gr_wait_reads_both_boxes_again_after_the_wait():
    """THE ORDER: the second drawing re-reads the box and its offset — the box laid over ptsin, which every box drawn
    rewrites, so the second XOR draws what the first left there (and the screen does not come back)."""
    over_ptsin = aes.AES_GSX_PTSIN
    result = gr_wait(running, ZERO, SNAPSHOT_MOUSE, box=over_ptsin, pokes=rect_pokes(*BOX, at=over_ptsin))
    assert result.answer() == 0


@THROUGH
def test_gr_wait_through_its_callers_word(through_line_f):
    gr_wait(running, OFFSET_AT, SNAPSHOT_MOUSE, through_line_f=through_line_f)


def test_gr_wait_puts_both_boxes_on_the_bus():
    gr_wait(running, OFFSET_AT | aes.BUS_TAG, SNAPSHOT_MOUSE, box=RECT_AT | aes.BUS_TAG)


def test_gr_wait_s_sum_wraps_word_by_word():
    """The twin's words are word sums: an offset that carries out of a word does not reach the next."""
    gr_wait(running, OFFSET_AT, SNAPSHOT_MOUSE, pokes=rect_pokes(0x7FFF, -1, -0x8000, 1, at=OFFSET_AT))


# ---- gr_clamp ---------------------------------------------------------------------------------------------------------------
# (x, y, min w, min h, w, h): the mouse right of and below the corner, at it, left of and above it (the minimums), and
# a negative distance against a negative minimum (compared signed).
CLAMP_CASES = {
    "the mouse inside: its distance + 1": (100, 50, 16, 16, 60, 50),
    "at the corner: one pixel": (159, 99, 0, 0, 1, 1),
    "left of and above it: the minimums": (200, 150, 16, 8, 16, 8),
    "a negative minimum: the negative distance": (200, 150, -100, -100, -40, -50),
    "a distance past the word: negative, so the minimum": (-0x8000, -0x8000, 0, 0, 0, 0),
}


def gr_clamp(x, y, min_w, min_h, width_out=FIRST_OUT, height_out=SECOND_OUT, machine=running, **kwargs):
    return aes.run_function(GR_CLAMP, (x, y, min_w, min_h, width_out, height_out), machine(), **kwargs)


@pytest.mark.parametrize("x, y, min_w, min_h, w, h", CLAMP_CASES.values(), ids=CLAMP_CASES)
def test_gr_clamp(x, y, min_w, min_h, w, h):
    result = gr_clamp(x, y, min_w, min_h)
    assert [aes.signed(word) for word in result.words(FIRST_OUT, 2)] == [w, h]


def test_gr_clamp_stores_the_width_first():
    """THE ORDER: both answers through one word — the height, stored last, is left."""
    result = gr_clamp(100, 50, 16, 16, width_out=FIRST_OUT, height_out=FIRST_OUT)
    assert result.word(FIRST_OUT) == 50


@THROUGH
def test_gr_clamp_through_its_callers_word(through_line_f):
    gr_clamp(100, 50, 16, 16, through_line_f=through_line_f)


def test_gr_clamp_puts_its_answers_on_the_bus():
    assert gr_clamp(100, 50, 16, 16, FIRST_OUT | aes.BUS_TAG, SECOND_OUT | aes.BUS_TAG).words(FIRST_OUT, 2) == [60, 50]


# ---- gr_rubwind, gr_rubbox ----------------------------------------------------------------------------------------------------
# (x, y, min w, min h, w, h): the mouse past the minimum (the corner AT the mouse), short of it (the minimum held).
RUBBER = {
    "stretched to the mouse": (100, 50, 16, 16, 60, 50),
    "held at the minimum": (150, 95, 16, 16, 16, 16),
    "the mouse left of the box": (170, 50, 32, 8, 32, 50),
}


def rubbox(arguments, machine=running, **kwargs):
    return run(GR_RUBBOX, (*arguments, FIRST_OUT, SECOND_OUT), machine(), **kwargs)


@pytest.mark.parametrize("x, y, min_w, min_h, w, h", RUBBER.values(), ids=RUBBER)
def test_gr_rubbox(x, y, min_w, min_h, w, h):
    result = rubbox((x, y, min_w, min_h))
    assert result.words(FIRST_OUT, 2) == [w, h]
    assert not screen_changed(result)


def test_gr_rubbox_with_the_cursor_shown():
    """gr_xdraw hides the cursor round each box: the boxes XORed under no sprite, the sprite drawn back after."""
    result = rubbox(RUBBER["stretched to the mouse"][:4], machine=shown_running)
    assert result.words(FIRST_OUT, 2) == list(RUBBER["stretched to the mouse"][4:])


@THROUGH
def test_gr_rubbox_through_its_callers_word(through_line_f):
    rubbox(RUBBER["stretched to the mouse"][:4], through_line_f=through_line_f)


def test_gr_rubbox_puts_its_answers_on_the_bus():
    run(GR_RUBBOX, (100, 50, 16, 16, FIRST_OUT | aes.BUS_TAG, SECOND_OUT | aes.BUS_TAG), running())


def test_gr_rubbox_stores_the_width_first():
    result = run(GR_RUBBOX, (100, 50, 16, 16, FIRST_OUT, FIRST_OUT), running())
    assert result.word(FIRST_OUT) == 50


def test_gr_rubbox_s_wait_at_the_mouse_is_refused_where_the_rom_s_blocks():
    """The button down, the corner AT the mouse: the box drawn, the wait for the mouse to leave the corner refused."""
    assert blocked_calls(GR_RUBBOX, (100, 50, 16, 16, FIRST_OUT, SECOND_OUT), button_down()) == LOCKED_THEN_WAITING


@functools.cache
def twin_over(machine):
    """`machine()` with a window's outline offset staged (TWIN_OFFSET)."""
    return merge_pokes(machine(), rect_pokes(*TWIN_OFFSET, at=OFFSET_AT))


def rubwind(offset, machine=running, **kwargs):
    return run(GR_RUBWIND, (100, 50, 36, 37, offset, FIRST_OUT, SECOND_OUT), twin_over(machine), **kwargs)


@THROUGH
@pytest.mark.parametrize("offset", (OFFSET_AT, ZERO), ids=("a window's outline twin", "no twin"))
def test_gr_rubwind(offset, through_line_f):
    """The control manager's sizing: the window's border box drawn as the twin of its work area's."""
    result = rubwind(offset, through_line_f=through_line_f)
    assert result.words(FIRST_OUT, 2) == [60, 50]


def test_gr_rubwind_puts_its_offset_on_the_bus():
    rubwind(OFFSET_AT | aes.BUS_TAG)


# ---- gr_dragbox ---------------------------------------------------------------------------------------------------------------
# (w, h, x, y, bound, x', y'): the box where the mouse leaves it (above and left of the mouse, inside or not: the
# offset is the distance, and a still mouse leaves the box where it was), below and right of the mouse (the offset
# clamped to 0: it jumps to the mouse), pulled into its bound by rc_constrain — and wider than the bound, past its left
# edge (rc_constrain's right-edge pull comes last).
DRAG = {
    "the mouse inside: it stays": (40, 20, 140, 90, SCREEN, 140, 90),
    "below and right of the mouse: it jumps to it": (40, 20, 200, 150, SCREEN, 159, 99),
    "outside the bound: pulled in": (40, 20, 10, 10, RECT_AT, 20, 30),
    "wider than the bound: past its left edge": (300, 20, 200, 150, RECT_AT, -80, 99),
}
BOUND = (20, 30, 200, 100)
DRAG_FROM_INSIDE = (40, 20, 140, 90)    # the box under the mouse: its offset (19, 9)


@functools.cache
def bound_over(machine):
    """`machine()` with gr_dragbox's bound staged (BOUND)."""
    return merge_pokes(machine(), rect_pokes(*BOUND))


def dragbox(w, h, x, y, bound, machine=running, x_out=FIRST_OUT, y_out=SECOND_OUT, **kwargs):
    return run(GR_DRAGBOX, (w, h, x, y, bound, x_out, y_out), bound_over(machine), **kwargs)


@pytest.mark.parametrize("w, h, x, y, bound, new_x, new_y", DRAG.values(), ids=DRAG)
def test_gr_dragbox(w, h, x, y, bound, new_x, new_y):
    result = dragbox(w, h, x, y, bound)
    assert [aes.signed(word) for word in result.words(FIRST_OUT, 2)] == [new_x, new_y]
    assert not screen_changed(result)


def test_gr_dragbox_with_the_cursor_shown():
    w, h, x, y, bound, new_x, new_y = DRAG["outside the bound: pulled in"]
    result = dragbox(w, h, x, y, bound, machine=shown_running)
    assert result.words(FIRST_OUT, 2) == [new_x, new_y]


@THROUGH
def test_gr_dragbox_through_its_callers_word(through_line_f):
    dragbox(*DRAG["outside the bound: pulled in"][:5], through_line_f=through_line_f)


def test_gr_dragbox_puts_its_pointers_on_the_bus():
    dragbox(40, 20, 10, 10, RECT_AT | aes.BUS_TAG, x_out=FIRST_OUT | aes.BUS_TAG, y_out=SECOND_OUT | aes.BUS_TAG)


def test_gr_dragbox_s_corner_step_is_a_word_sum():
    """The corner one further on, word by word (`add.w`, then `add.l` of the high word alone): a corner at the word's
    edge wraps to -32768 and the offset gr_clamp makes is counted from there."""
    dragbox(40, 20, 0x7FFF, 0x7FFF, SCREEN)


def test_gr_dragbox_stores_x_first():
    assert dragbox(40, 20, 200, 150, SCREEN, x_out=FIRST_OUT, y_out=FIRST_OUT).word(FIRST_OUT) == 99


def test_gr_dragbox_s_wait_at_the_mouse_is_refused_where_the_rom_s_blocks():
    assert blocked_calls(GR_DRAGBOX, (*DRAG_FROM_INSIDE, SCREEN, FIRST_OUT, SECOND_OUT), bound_over(button_down)) == \
        LOCKED_THEN_WAITING


# ---- gr_slidebox ---------------------------------------------------------------------------------------------------------------
@functools.cache
def window_sliders():
    """`(machine, W_ACTIVE)`: test_aes_wmlib's window with its sliders set by the ROM's wm_set (`slid`), its gadgets built
    into W_ACTIVE by the ROM's own w_bldactive — the tree the control manager drags a window's elevators in."""
    pokes, window = wmlib.slid()
    return _stale(wmlib.rom_derived(addrs.AES_ROM_W_BLDACTIVE, aes_event.frame_of(("w", window)), pokes)), aes.AES_W_ACTIVE


ELEVATOR_LOW = aes.object_pokes(SELECTOR, ELEVATOR, Y=40)       # as fs_format leaves it, its list scrolled down
ELEVATOR_FULL = aes.object_pokes(SELECTOR, ELEVATOR, HEIGHT=56)  # ...and for nine names or fewer: the whole track


def selector_slide(vertical, machine=running, pokes=None, tree=SELECTOR, **kwargs):
    return run(GR_SLIDEBOX, (tree, TRACK, ELEVATOR, vertical), merge_pokes(machine(), pokes), **kwargs)


# (vertical, machine, pokes, answer): the elevator where the snapshot holds it (the top), lower and the mouse above it
# in the track (it jumps up to the mouse), the whole track (no room: 0 without a divide), and across, where it has one
# pixel of room.
SELECTOR_SLIDES = {
    "at the top, the mouse outside: 0": (1, running, None, 0),
    "low, the mouse above it in the track: it jumps up": (1, functools.partial(mouse_at, 188, 110), ELEVATOR_LOW,
                                                          mul_div_model(9, 1000, 48)),
    "the whole track: no room": (1, running, ELEVATOR_FULL, 0),
    "across, one pixel of room": (0, functools.partial(mouse_at, 177, 110), None, 1000),
}


@pytest.mark.parametrize("vertical, machine, pokes, answer", SELECTOR_SLIDES.values(), ids=SELECTOR_SLIDES)
def test_gr_slidebox_over_the_selector_s_slider(vertical, machine, pokes, answer):
    assert selector_slide(vertical, machine, pokes).answer() == answer


WINDOW_SLIDES = {"the vertical elevator": ("W_VSLIDE", "W_VELEV", 1), "the horizontal": ("W_HSLIDE", "W_HELEV", 0)}


@pytest.mark.parametrize("track, elevator, vertical", WINDOW_SLIDES.values(), ids=WINDOW_SLIDES)
def test_gr_slidebox_over_a_window_s_slider(track, elevator, vertical):
    machine, tree = window_sliders()
    run(GR_SLIDEBOX, (tree, wmlib.WM[track], wmlib.WM[elevator], vertical), machine)


@THROUGH
def test_gr_slidebox_through_its_callers_word(through_line_f):
    selector_slide(1, through_line_f=through_line_f)


def test_gr_slidebox_puts_the_tree_on_the_bus():
    selector_slide(1, tree=SELECTOR | aes.BUS_TAG)


def test_gr_slidebox_s_wait_at_the_mouse_is_refused_where_the_rom_s_blocks():
    assert blocked_calls(GR_SLIDEBOX, (SELECTOR, TRACK, ELEVATOR, 1), button_down()) == LOCKED_THEN_WAITING


# ---- the loops TAKEN THROUGH INTERRUPTS ----------------------------------------------------------------------------------
# The button down, then the mouse MOVED and the button RELEASED by the ROM's own interrupt code at the entry of a step's
# wait, on both shores (`aes_event.interrupted`). A loop's door call 0 is the screen lock's tak_flag, call k its k-th
# step's wait; gr_wait's call 0 its one wait. (routine, arguments, machine, {door call: interrupts}, the answer, the two
# words out or None)
move_to, release = aes_event.move_to, aes_event.release


def over(staging, machine):
    """A case's machine as a callable: `staging(machine)`."""
    return functools.partial(staging, machine)


INTERRUPTED = {
    "gr_dragbox: moved with the button held, then released": (
        GR_DRAGBOX, (*DRAG_FROM_INSIDE, SCREEN, FIRST_OUT, SECOND_OUT), over(bound_over, button_down),
        {1: move_to(200, 150), 2: release}, None, (181, 141)),
    "gr_dragbox: moved twice, the second time out of its bound": (
        GR_DRAGBOX, (*DRAG_FROM_INSIDE, RECT_AT, FIRST_OUT, SECOND_OUT), over(bound_over, button_down),
        {1: move_to(200, 150), 2: move_to(10, 10), 3: release}, None, (20, 30)),
    "gr_dragbox: moved, the cursor shown": (
        GR_DRAGBOX, (*DRAG_FROM_INSIDE, SCREEN, FIRST_OUT, SECOND_OUT), over(bound_over, shown_button_down),
        {1: move_to(200, 150), 2: release}, None, (181, 141)),
    "gr_rubbox: stretched, then released": (
        GR_RUBBOX, (100, 50, 16, 16, FIRST_OUT, SECOND_OUT), button_down, {1: move_to(180, 120), 2: release}, None,
        (81, 71)),
    "gr_rubbox: the busy loop at its minimum, left when the button rises": (
        GR_RUBBOX, (150, 95, 16, 16, FIRST_OUT, SECOND_OUT), button_down, {3: release}, None, (16, 16)),
    "gr_rubwind: a window's outline stretched": (
        GR_RUBWIND, (100, 50, 36, 37, OFFSET_AT, FIRST_OUT, SECOND_OUT), over(twin_over, button_down),
        {1: move_to(180, 120), 2: release}, None, (81, 71)),
    "gr_slidebox: the elevator dragged down": (
        GR_SLIDEBOX, (SELECTOR, TRACK, ELEVATOR, 1), button_down, {1: move_to(188, 140), 2: release},
        mul_div_model(39, 1000, 48), None),
    "gr_wait: the button released while it waits": (
        GR_WAIT, (RECT_AT, OFFSET_AT, *SNAPSHOT_MOUSE), over(waiting_over, button_down), {0: release}, 0, None),
    "gr_wait: the mouse moved while it waits": (
        GR_WAIT, (RECT_AT, OFFSET_AT, *SNAPSHOT_MOUSE), over(waiting_over, button_down), {0: move_to(170, 110)}, 1, None),
}


@pytest.mark.parametrize("name, arguments, machine, interrupts, answer, out", INTERRUPTED.values(), ids=INTERRUPTED)
def test_taken_through_interrupts(name, arguments, machine, interrupts, answer, out):
    """The C and the ROM taken through the same interrupts at the same steps (`aes_event.interrupted`): both return,
    with the same answer, every frame handed the door, the whole image."""
    taken = aes_event.interrupted(name, arguments, machine(), interrupts)
    assert taken.returned and taken.answer == answer
    if out:
        assert tuple(aes.signed(case.word_in(taken.image, at)) for at in (FIRST_OUT, SECOND_OUT)) == out


# ---- the registry --------------------------------------------------------------------------------------------------------------
for _label, (_machine, _offset, _pixel, _answer) in GR_WAIT_CASES.items():
    aes_event.register(_label, GR_WAIT, (RECT_AT, _offset, *_pixel), waiting_over(_machine), drawing=True)
for _label in ("the mouse inside: its distance + 1", "left of and above it: the minimums"):
    aes.register(_label, GR_CLAMP, (*CLAMP_CASES[_label][:4], FIRST_OUT, SECOND_OUT), running())
for _label, _arguments in RUBBER.items():
    aes_event.register(_label, GR_RUBBOX, (*_arguments[:4], FIRST_OUT, SECOND_OUT), running(), drawing=True)
aes_event.register("a window's outline twin", GR_RUBWIND, (100, 50, 36, 37, OFFSET_AT, FIRST_OUT, SECOND_OUT),
                   twin_over(running), drawing=True)
for _label, (_w, _h, _x, _y, _bound, _new_x, _new_y) in DRAG.items():
    aes_event.register(_label, GR_DRAGBOX, (_w, _h, _x, _y, _bound, FIRST_OUT, SECOND_OUT), bound_over(running),
                       drawing=True)
for _label, (_vertical, _machine, _pokes, _answer) in SELECTOR_SLIDES.items():
    aes_event.register(_label, GR_SLIDEBOX, (SELECTOR, TRACK, ELEVATOR, _vertical), merge_pokes(_machine(), _pokes),
                       drawing=True)
# ...and the shapes TAKEN THROUGH INTERRUPTS (`aes_event.register_interrupted`) each dearer than its routine's dearest row
# above, measured by `make bench` over every returning case of INTERRUPTED: the drag with the cursor shown (its xdraws
# hide and show it), the window's outline stretched, the elevator dragged.
WORST_INTERRUPTED = ("gr_dragbox: moved, the cursor shown", "gr_rubwind: a window's outline stretched",
                     "gr_slidebox: the elevator dragged down")
for _label in WORST_INTERRUPTED:
    _name, _arguments, _machine, _interrupts, _answer, _out = INTERRUPTED[_label]
    aes_event.register_interrupted(_label.partition(": ")[2], _name, _arguments, _machine(), _interrupts)
