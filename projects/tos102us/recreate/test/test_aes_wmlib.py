"""The WINDOW LIBRARY's half that never waits on an event — `src/aes/wmlib.c` (`aes/wmlib.h`).

    w_nilit(n, o)           while (n--) o[n].tail = o[n].head = o[n].next = -1   (the count a word, `subq.w`)
    w_obadd(o, p, c)        ob_add's body over the array o
    w_setup(pd, w, kind)    win[w]: owner pd, flags |= IN_USE, kind, vslide = hslide = 0, vslsize = hslsize = -1
    w_setsize(which, w, r)  rc_copy(r, w_getxptr(which, w))
    w_adjust(p, o, x, y, w, h)       W_ACTIVE[o]: (x, y, w, h) (rc_copy of its own arguments), tail = head = -1;
                                     w_obadd(W_ACTIVE, p, o)
    w_hvassign(v, p, o, vx, vy, hx, hy, w, h)   v ? w_adjust(p, o, vx, vy, gl_wbox, h) : w_adjust(p, o, hx, hy, w, gl_hbox)
    w_clipdraw(w, tree, o, d, c)     gl_wfrozen || w == -1: 1;  c ? rc_intersect(&gl_rfull, c) : c = &gl_rfull;
                                     for each ORECT of win[w]'s list: t = its rect; rc_intersect(c, &t) ?
                                     gsx_sclip(&t), ob_draw(tree, o, d);  D0 0 (the list's end)
    w_drawdesk(r)           gl_newdesk ? (it, gl_newroot, 8) : (gl_wtree, 0, 0); r.w += 2, r.h += 2; w_clipdraw(0, ...)
    w_cpwalk(w, o, d, use)  w == gl_wtop || use ? w_getsize(TRUE, w, &c) : (gsx_gclip(&c), c.w += 2, c.h += 2);
                            w_bldactive(w); w_clipdraw(w, gl_awind, o, d, &c)
    w_strchg(w, o, s)       o == W_NAME ? win.name = gl_aname.ptext = s : win.info = gl_ainfo.ptext = s; w_cpwalk(w, o, 8, 1)
    w_barcalc(v, sp, val, sz, min, pv, ph)   sz = sz == -1 ? min : max(min, mul_div(sz, sp, 1000));
                            val = mul_div(sp - sz, val, 1000); v ? r_set(pv, 0, val, gl_wbox, sz) : r_set(ph, val, 0, sz, gl_hbox)
    w_bldbar                a scroll bar and (top window only) its arrows, track and elevator
    w_bldactive(w)          W_ACTIVE rebuilt for window w (nothing for -1)
    w_mvfix(s, d)           x = s.x; rc_intersect(&gl_rfull, s); x == -1 ? (d.x++, d.w--, 1) : 0
    w_move(w, &stop, r)     a moved window's image blitted, the strip at the left edge redrawn; r the rectangle to redraw
    w_owns(w, o, r, out)    the next of the list from o meeting r, into out; win.rnext moved; the end: out.w = out.h = 0
    w_union(o, r)           r := the bounding box of the list (0 for none)
    wm_start / wm_create / wm_delete / wm_get / wm_find / wm_calc    the records' life, wind_get, wind_find, wind_calc

THE MACHINES ARE DERIVED. The snapshot holds one window, the desktop's (window 0, its list one ORECT). Every other
window is the ROM's own, made over PD0 RUNNING as the ROM's scheduler makes it (`aes_event.machine`: the key the
desk's evnt_multi waits for delivered, the dispatcher's loop run until PD0 comes out of that evnt_multi, then the
cursor hidden as the running process hides it, the snapshot's font cached) — then the ROM's wm_create and wm_open
(`aes_event.window_chain`) and wm_set runs, each continued from. A window's kind and its slider words are what
wm_create and wm_set leave; nothing in a record is poked.

THE DRAWING ROUTINES run over that machine with `test_aes_ob_draw.py`'s doors — every VDI call served by the VDI's C
cores, ob_draw's just_draw by its C core — and the whole image is compared, the screen included.
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import aes
import aes_event
import aes_gsx as gsx
import aes_objdraw as od
import aes_rlist
import case
import test_aes_ob_draw as obdraw
import vdi
from test_aes_strings import mul_div_model
from aes_rlist import DESKTOP, list_head, rect_of, walk, window_record, window_rects
from case import merge_pokes
from test_aes_gsx import screen_changed

WM = aes.header_constants("wmlib.h")
WRECT = aes.header_constants("wrect.h")
WS_FULL, WS_CURR, WS_PREV, WS_WORK, WS_TRUE = (WRECT[name] for name in ("WS_FULL", "WS_CURR", "WS_PREV", "WS_WORK",
                                                                          "WS_TRUE"))
L, W, I = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
SIGNATURES = {
    "AES_ROM_W_NILIT": (None, (I, W, L)),
    "AES_ROM_W_OBADD": (None, (I, L, W, W)),
    "AES_ROM_W_SETUP": (None, (I, L, W, W)),
    "AES_ROM_W_SETSIZE": (None, (I, W, W, L)),
    "AES_ROM_W_ADJUST": (None, (I, W, W, W, W, W, W)),
    "AES_ROM_W_HVASSIGN": (None, (I, W, W, W, W, W, W, W, W, W)),
    "AES_ROM_W_CLIPDRAW": (aes.WORD_ANSWER, (I, W, L, W, W, L)),
    "AES_ROM_W_DRAWDESK": (None, (I, L)),
    "AES_ROM_W_CPWALK": (None, (I, W, W, W, W)),
    "AES_ROM_W_STRCHG": (None, (I, W, W, L)),
    "AES_ROM_W_BARCALC": (None, (I, W, W, W, W, W, L, L)),
    "AES_ROM_W_BLDBAR": (None, (I, W, W, W, W, W, W, W, W, W)),
    "AES_ROM_W_BLDACTIVE": (None, (I, W)),
    "AES_ROM_W_MVFIX": (aes.WORD_ANSWER, (I, L, L)),
    "AES_ROM_W_MOVE": (aes.WORD_ANSWER, (I, W, L, L)),
    "AES_ROM_W_OWNS": (aes.WORD_ANSWER, (I, W, L, L, L)),
    "AES_ROM_W_UNION": (aes.WORD_ANSWER, (I, L, L)),
    "AES_ROM_WM_START": (None, (I,)),
    "AES_ROM_WM_CREATE": (aes.WORD_ANSWER, (I, W, L)),
    "AES_ROM_WM_DELETE": (aes.WORD_ANSWER, (I, W)),
    "AES_ROM_WM_GET": (aes.WORD_ANSWER, (I, W, W, L)),
    "AES_ROM_WM_FIND": (aes.WORD_ANSWER, (I, W, W)),
    "AES_ROM_WM_CALC": (aes.WORD_ANSWER, (I, W, W, W, W, W, W, L, L, L, L)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
(W_NILIT, W_OBADD, W_SETUP, W_SETSIZE, W_ADJUST, W_HVASSIGN, W_CLIPDRAW, W_DRAWDESK, W_CPWALK, W_STRCHG, W_BARCALC,
 W_BLDBAR, W_BLDACTIVE, W_MVFIX, W_MOVE, W_OWNS, W_UNION, WM_START, WM_CREATE, WM_DELETE, WM_GET, WM_FIND,
 WM_CALC) = SIGNATURES

THROUGH = gsx.THROUGH
W_ACTIVE = aes.AES_W_ACTIVE
W_ACTIVE_OBJECTS = WM["W_ACTIVE_OBJECTS"]
WINDOW_TREE = aes.AES_WINDOW_TREE
NIL = aes.OB_NIL
WBOX = case.word_in(BASE_IMAGE, aes.AES_GL_WBOX)        # the snapshot's box: 12 x 11 (`test_the_snapshot_s_boxes`)
HBOX = case.word_in(BASE_IMAGE, aes.AES_GL_HBOX)
SCREEN = (0, 0, 320, 200)
DESKTOP_AREA = (0, 11, 320, 189)                        # gl_rfull: below the menu bar
DESKTOP_TRUE = (0, 0, 322, 202)                         # the desktop's WS_TRUE: what newrect rebuilds its list from

# The spans outside the AES's window the cases reach: the gadget tree, its two TEDINFOs and the library's globals.
aes.declare_case_field(W_ACTIVE, W_ACTIVE_OBJECTS * aes.OB_BYTES, "W_ACTIVE, the gadget tree a window is drawn with")
for _global in ("GL_ANAME", "GL_AINFO", "GL_WTOP", "GL_WTREE", "GL_AWIND", "GL_WFROZEN", "GL_NEWROOT", "AD_STDESK"):
    _field = aes.field("AES", _global)
    aes.declare_case_field(_field.at, _field.width * (_field.count or 1), f"the window library's {_global}")

# The GRECTs and answer words a case hands in: `aes.RECTS_AT`'s band, a GRECT each.
RECT_SLOTS = aes.RECTS_BYTES // aes.GRECT_BYTES


def rect_at(slot):
    assert 0 <= slot < RECT_SLOTS
    return aes.RECTS_AT + slot * aes.GRECT_BYTES


def rect_pokes(slot, rect):
    return {rect_at(slot): vdi.pack_words(*rect)}


def grect(result, at):
    """The GRECT at `at` after the run, signed."""
    return tuple(aes.signed(word) for word in result.words(at, 4))


STALE_RECTS = {aes.RECTS_AT: vdi.pack_words(*[aes.STALE_WORD] * (aes.RECTS_BYTES // aes.WORD_BYTES))}
STALE_GRECT = (aes.signed(aes.STALE_WORD),) * 4
SLIDER_SCALE = WM["W_SLIDER_SCALE"]
BORDER = WRECT["W_BORDER"]


# ---- the ROM's own runs, each a derivation (`test/aes_event.py`'s) -----------------------------------------------------
# A routine no C core stands for yet (wm_open, wm_set): its frame packed by `aes_event.frame_of`, the oracle run alone,
# and its WRITES laid over the machine it ran on (`aes_event.derived`, whose budget and margin cover the deepest here —
# a wm_set move). wind_set's fields are wind_get's numbers (`aes/wmlib.h`'s WF_*): wm_set's switch moves a window
# (WF_CURRXYWH), sets its sliders, a new desk (WF_NEWDESK) or holds window drawing (WF_RESVD, gl_wfrozen).
def rom_derived(entry, frame, pokes):
    """`pokes` continued by the ROM's run of `entry` over `frame`."""
    delta, _final, _regs = aes_event.derived(entry, pokes, frame=frame)
    return merge_pokes(pokes, delta)


@functools.cache
def running():
    """THE DOOR'S MACHINE: PD0 RUNNING, made by the ROM's scheduler, the cursor hidden after (`aes_event.machine`) —
    the snapshot's font cached, as `test_aes_ob_draw.py`'s draws have it."""
    return aes_event.machine(onto=od.SNAPSHOT_FONT)


def window_set(onto, window, field, *words):
    """The ROM's wm_set(window, field, words) over `onto`."""
    frame = aes_event.frame_of(("w", window), ("w", field), ("l", DERIVATION_AT))
    return rom_derived(addrs.AES_ROM_WM_SET, frame, merge_pokes(onto, {DERIVATION_AT: vdi.pack_words(*words)}))


# Where wm_create's and wm_set's GRECTs are staged: past the cases' own GRECTs.
DERIVATION_AT = aes.RECTS_AT + aes.RECTS_BYTES - aes.GRECT_BYTES
EVERY_GADGET = aes_event.EVERY_GADGET
WINDOW_AT = (20, 30, 200, 100)
MOVED_TO = (60, 50, 180, 90)


@functools.cache
def top_window():
    """`(pokes, handle)`: one window of every gadget created and opened at WINDOW_AT by the ROM over the desktop
    (`aes_event.window_chain`) — the top window, its list its rectangle, the windows below it cut."""
    return aes_event.window_chain(EVERY_GADGET, *WINDOW_AT, onto=running())


@functools.cache
def two_windows():
    """`(pokes, lower, upper)`: top_window's window, then a second over its corner — the first no longer on top."""
    pokes, lower = top_window()
    pokes, upper = aes_event.window_chain(EVERY_GADGET, 100, 80, 180, 100, onto=pokes)
    return pokes, lower, upper


@functools.cache
def moved():
    """`(pokes, handle)`: top_window's window moved by the ROM's wm_set to MOVED_TO — its previous rectangle where it
    was, its current where it is, as draw_change hands w_move its window."""
    pokes, window = top_window()
    return window_set(pokes, window, WM["WF_CURRXYWH"], *MOVED_TO), window


def test_the_snapshot_s_boxes():
    """The box the gadgets are sized by, and the one window the snapshot holds (the desktop, every other closed)."""
    assert (WBOX, HBOX) == (12, 11)
    assert [case.word_in(BASE_IMAGE, window_record(window) + aes.WIN_FLAGS) & aes.WIN_IN_USE
            for window in range(aes.AES_WINDOW_COUNT)] == [1] + [0] * 7


def test_the_chain_opens_a_top_window():
    pokes, window = top_window()
    image = make_image(pokes)
    assert window == 1
    assert aes.signed(case.word_in(image, aes.AES_GL_WTOP)) == window
    assert rect_of(image, WINDOW_TREE + window * aes.OB_BYTES + aes.OB_X - aes.ORECT_X) == WINDOW_AT
    assert case.word_in(image, window_record(window) + aes.WIN_KIND) == EVERY_GADGET
    assert len(window_rects(image, DESKTOP)) == 4, "the desktop cut round the window"


def test_the_window_machines_keep_pd0_running():
    """The derivations run with the dispatcher's guard as switchto left it (0), so a dsptch one reached would really
    switch processes: none did — every derivation is run with dsptch as its stop and refused had it reached it
    (`aes_event.derived`) — and after each window machine PD0 is still running exactly as switchto leaves it."""
    for pokes in (top_window()[0], two_windows()[0], moved()[0], held()[0], slid()[0], nested_desk(),
                  every_window_created()):
        assert (aes_event.scheduler_state(make_image(pokes), aes.SHELL_PD)
                == aes_event.running_as_switchto_leaves_it(aes.SHELL_PD))


# ---- the runs ---------------------------------------------------------------------------------------------------------
def _leaf(pokes=None):
    return merge_pokes(aes.leaf_machine(), pokes)


def run(name, arguments, pokes=None, *, onto=None, **kwargs):
    """`name` over the leaf machine (or `onto`), `pokes` laid on it."""
    return aes.run_function(name, arguments, _leaf(pokes) if onto is None else merge_pokes(onto, pokes), **kwargs)


def object_rect(result, tree, index):
    obj = result.object(tree, index)
    return tuple(aes.signed(obj[name]) for name in ("X", "Y", "WIDTH", "HEIGHT"))


def object_links(result, tree, index):
    obj = result.object(tree, index)
    return tuple(aes.signed(obj[name]) for name in ("NEXT", "HEAD", "TAIL"))


# ---- w_nilit ------------------------------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("count, objects", ((W_ACTIVE_OBJECTS, W_ACTIVE), (aes.AES_WINDOW_COUNT, WINDOW_TREE)),
                         ids=("W_ACTIVE, as w_bldactive and wm_start hand it", "the window tree, as wm_start hands it"))
def test_w_nilit_unlinks_every_object(count, objects, through_line_f):
    result = run(W_NILIT, (count, objects), through_line_f=through_line_f)
    assert [object_links(result, objects, index) for index in range(count)] == [(NIL, NIL, NIL)] * count
    assert result.object(objects, count) == aes.read_object(BASE_IMAGE, objects, count), "past the count: untouched"


def test_w_nilit_of_none_touches_nothing():
    assert aes.stored_nothing(run(W_NILIT, (0, W_ACTIVE)))


def test_w_nilit_puts_the_array_on_the_bus():
    result = run(W_NILIT, (W_ACTIVE_OBJECTS, W_ACTIVE | aes.BUS_TAG))
    assert object_links(result, W_ACTIVE, W_ACTIVE_OBJECTS - 1) == (NIL, NIL, NIL)


# ---- w_obadd -------------------------------------------------------------------------------------------------------------
@functools.cache
def unlinked():
    """W_ACTIVE as the ROM's own w_nilit(19) leaves it."""
    leaf = aes.leaf_machine()
    delta, _final, _regs = aes_event.derived(addrs.AES_ROM_W_NILIT, aes.staged(W_NILIT, (W_ACTIVE_OBJECTS, W_ACTIVE), leaf))
    return merge_pokes(leaf, delta)


@THROUGH
def test_w_obadd_makes_a_first_child(through_line_f):
    result = run(W_OBADD, (W_ACTIVE, WM["W_BOX"], WM["W_TITLE"]), onto=unlinked(), through_line_f=through_line_f)
    assert object_links(result, W_ACTIVE, WM["W_BOX"]) == (NIL, WM["W_TITLE"], WM["W_TITLE"])
    assert object_links(result, W_ACTIVE, WM["W_TITLE"]) == (WM["W_BOX"], NIL, NIL)


def test_w_obadd_appends_after_the_last_child():
    first = case.continued(run(W_OBADD, (W_ACTIVE, WM["W_BOX"], WM["W_TITLE"]), onto=unlinked()))
    result = run(W_OBADD, (W_ACTIVE | aes.BUS_TAG, WM["W_BOX"], WM["W_INFO"]), onto=first)
    assert object_links(result, W_ACTIVE, WM["W_BOX"]) == (NIL, WM["W_TITLE"], WM["W_INFO"])
    assert object_links(result, W_ACTIVE, WM["W_TITLE"]) == (WM["W_INFO"], NIL, NIL)
    assert object_links(result, W_ACTIVE, WM["W_INFO"]) == (WM["W_BOX"], NIL, NIL)


@pytest.mark.parametrize("parent, child", ((NIL, WM["W_TITLE"]), (WM["W_BOX"], NIL)), ids=("no parent", "no child"))
def test_w_obadd_of_nil_does_nothing(parent, child):
    assert aes.stored_nothing(run(W_OBADD, (W_ACTIVE, parent, child), onto=unlinked()))


# ---- w_setup / w_setsize ---------------------------------------------------------------------------------------------------
def record(result, window, name):
    return result.field("WIN", name, window_record(window))


@THROUGH
def test_w_setup_claims_a_closed_window(through_line_f):
    result = run(W_SETUP, (aes.SHELL_PD, 2, EVERY_GADGET), onto=running(), through_line_f=through_line_f)
    assert [record(result, 2, name) for name in ("FLAGS", "OWNER", "KIND", "HSLIDE", "VSLIDE", "HSLSIZE", "VSLSIZE")] \
        == [aes.WIN_IN_USE, aes.SHELL_PD, EVERY_GADGET, 0, 0, 0xFFFF, 0xFFFF]


def test_w_setup_keeps_the_other_flags_and_stores_the_owner_as_handed():
    """A window the ROM's newrect marked BROKEN (top_window's desktop) set up again: the flag kept, the owner a
    tagged longword stored whole (`move.l`: no bus between)."""
    pokes, _window = top_window()
    result = run(W_SETUP, (aes.SHELL_PD | aes.BUS_TAG, DESKTOP, 0), onto=pokes)
    assert record(result, DESKTOP, "FLAGS") == aes.WIN_IN_USE | aes.WIN_BROKEN
    assert record(result, DESKTOP, "OWNER") == aes.SHELL_PD | aes.BUS_TAG


@THROUGH
@pytest.mark.parametrize("which", (WS_FULL, WS_CURR, WS_PREV, WS_WORK))
def test_w_setsize_copies_each_rectangle_in(which, through_line_f):
    result = run(W_SETSIZE, (which, 1, rect_at(0) | aes.BUS_TAG), rect_pokes(0, (5, 6, 7, 8)),
                 through_line_f=through_line_f)
    at = {WS_FULL: window_record(1) + aes.WIN_FULL, WS_PREV: window_record(1) + aes.WIN_PREV,
          WS_WORK: window_record(1) + aes.WIN_WORK, WS_CURR: WINDOW_TREE + aes.OB_BYTES + aes.OB_X}[which]
    assert grect(result, at) == (5, 6, 7, 8)


# ---- w_adjust / w_hvassign -----------------------------------------------------------------------------------------------
@THROUGH
def test_w_adjust_places_a_gadget_and_adds_it(through_line_f):
    result = run(W_ADJUST, (WM["W_BOX"], WM["W_TITLE"], 0, 0, 200, HBOX), onto=unlinked(), through_line_f=through_line_f)
    assert object_rect(result, W_ACTIVE, WM["W_TITLE"]) == (0, 0, 200, HBOX)
    assert object_links(result, W_ACTIVE, WM["W_TITLE"]) == (WM["W_BOX"], NIL, NIL)
    assert object_links(result, W_ACTIVE, WM["W_BOX"]) == (NIL, WM["W_TITLE"], WM["W_TITLE"])


def test_w_adjust_clears_the_gadget_s_old_children():
    """Over the gadget tree a top window's draw left (top_window): the title's children (closer, name, fuller) are
    dropped and the title made the root's last child again."""
    pokes, _window = top_window()
    result = run(W_ADJUST, (WM["W_BOX"], WM["W_TITLE"], -3, 4, -5, 6), onto=pokes)
    assert object_rect(result, W_ACTIVE, WM["W_TITLE"]) == (-3, 4, -5, 6)
    assert object_links(result, W_ACTIVE, WM["W_TITLE"])[1:] == (NIL, NIL)


@THROUGH
@pytest.mark.parametrize("vertical", (0, 1), ids=("horizontal", "vertical"))
def test_w_hvassign_sizes_the_gadget_the_bar_s_way(vertical, through_line_f):
    result = run(W_HVASSIGN, (vertical, WM["W_VBAR"], WM["W_UPARROW"], 1, 2, 3, 4, 50, 60), onto=unlinked(),
                 through_line_f=through_line_f)
    expected = (1, 2, WBOX, 60) if vertical else (3, 4, 50, HBOX)
    assert object_rect(result, W_ACTIVE, WM["W_UPARROW"]) == expected


# ---- w_barcalc ------------------------------------------------------------------------------------------------------------
V_ELEVATOR, H_ELEVATOR = rect_at(0), rect_at(1)
# (space, value, size, minimum): the default size, the size per mille, the minimum winning, the ends of the track, a size
# bigger than the track (what is left negative, the position with it), and mul_div's rounding.
BARCALC = {
    "the default size": (100, 500, -1, 11),
    "half the track, half way": (100, 500, 500, 11),
    "the minimum wins": (100, 0, 50, 11),
    "the track's end": (177, 1000, 333, 8),
    "larger than the track": (40, 1000, 1000, 50),
    "rounding": (99, 333, 7, 1),
}


def elevator(vertical, space, value, size, minimum):
    """Where w_barcalc puts the elevator, by mul_div's own rounding (`test_aes_strings.mul_div_model`)."""
    size = minimum if size == -1 else max(minimum, mul_div_model(size, space, SLIDER_SCALE))
    position = mul_div_model(aes.signed(space - size), value, SLIDER_SCALE)
    return (0, position, WBOX, size) if vertical else (position, 0, size, HBOX)


@pytest.mark.parametrize("vertical", (0, 1), ids=("horizontal", "vertical"))
@pytest.mark.parametrize("space, value, size, minimum", BARCALC.values(), ids=BARCALC)
def test_w_barcalc(space, value, size, minimum, vertical):
    result = run(W_BARCALC, (vertical, space, value, size, minimum, V_ELEVATOR, H_ELEVATOR), STALE_RECTS)
    answered, untouched = (V_ELEVATOR, H_ELEVATOR) if vertical else (H_ELEVATOR, V_ELEVATOR)
    assert grect(result, answered) == elevator(vertical, space, value, size, minimum)
    assert grect(result, untouched) == STALE_GRECT


@THROUGH
def test_w_barcalc_through_its_word_with_tagged_pointers(through_line_f):
    result = run(W_BARCALC, (1, 100, 500, 500, 11, V_ELEVATOR | aes.BUS_TAG, H_ELEVATOR | aes.BUS_TAG), STALE_RECTS,
                 through_line_f=through_line_f)
    assert grect(result, V_ELEVATOR) == elevator(1, 100, 500, 500, 11)


# ---- w_bldbar -------------------------------------------------------------------------------------------------------------
UP, DOWN, SLIDE = WM["WK_UPARROW"], WM["WK_DNARROW"], WM["WK_VSLIDE"]
LEFT, RIGHT, HSLIDE = WM["WK_LFARROW"], WM["WK_RTARROW"], WM["WK_HSLIDE"]
BAR_KINDS = {"no gadgets": (0, 0), "the first arrow": (UP, LEFT), "the second arrow": (DOWN, RIGHT),
             "the slider": (SLIDE, HSLIDE), "both arrows": (UP | DOWN, LEFT | RIGHT),
             "an arrow and the slider": (UP | SLIDE, RIGHT | HSLIDE), "all three": (UP | DOWN | SLIDE,
                                                                             LEFT | RIGHT | HSLIDE)}
BAR_PLACE = (191, 0, 10, 80)                            # where a window of 200 x 100 puts its vertical bar


@pytest.mark.parametrize("is_top", (1, 0), ids=("the top window", "a window below"))
@pytest.mark.parametrize("bar", (WM["W_VBAR"], WM["W_HBAR"]), ids=("vertical", "horizontal"))
@pytest.mark.parametrize("kinds", BAR_KINDS.values(), ids=BAR_KINDS)
def test_w_bldbar(kinds, bar, is_top):
    kind = kinds[0] if bar == WM["W_VBAR"] else kinds[1]
    result = run(W_BLDBAR, (kind, is_top, bar, 333, 250, *BAR_PLACE), onto=unlinked())
    assert object_links(result, W_ACTIVE, bar)[0] == WM["W_DATA"]
    children = [index for index in range(W_ACTIVE_OBJECTS) if object_links(result, W_ACTIVE, index)[0] == bar]
    assert bool(children) == bool(is_top and kind)


@THROUGH
def test_w_bldbar_through_its_word(through_line_f):
    result = run(W_BLDBAR, (UP | DOWN | SLIDE, 1, WM["W_VBAR"], 500, 500, *BAR_PLACE), onto=unlinked(),
                 through_line_f=through_line_f)
    assert object_links(result, W_ACTIVE, WM["W_VELEV"])[0] == WM["W_VSLIDE"]


# ---- w_bldactive ------------------------------------------------------------------------------------------------------------
def tree_shape(result):
    """W_ACTIVE as built: each object's links and rectangle."""
    return [(object_links(result, W_ACTIVE, index), object_rect(result, W_ACTIVE, index))
            for index in range(W_ACTIVE_OBJECTS)]


@THROUGH
def test_w_bldactive_of_the_top_window_with_every_gadget(through_line_f):
    pokes, window = top_window()
    result = run(W_BLDACTIVE, (window,), onto=pokes, through_line_f=through_line_f)
    built = [index for index in range(1, W_ACTIVE_OBJECTS) if object_links(result, W_ACTIVE, index)[0] != NIL]
    assert built == list(range(1, W_ACTIVE_OBJECTS)), "every gadget linked in"
    assert object_rect(result, W_ACTIVE, WM["W_BOX"]) == WINDOW_AT
    assert result.word(aes.AES_GL_ANAME + aes.TE_COLOR) == WM["W_NAME_COLOUR_TOP"]
    assert result.long(W_ACTIVE + WM["W_SIZER"] * aes.OB_BYTES + aes.OB_SPEC) == WM["W_SIZER_SPEC_TOP"]


def test_w_bldactive_lays_the_elevators_by_the_window_s_sliders():
    """The sliders as wm_set left them (slid): each elevator sized and placed from its own two words."""
    pokes, window = slid()
    result = run(W_BLDACTIVE, (window,), onto=pokes)
    vertical, horizontal = object_rect(result, W_ACTIVE, WM["W_VELEV"]), object_rect(result, W_ACTIVE, WM["W_HELEV"])
    assert vertical[1] > 0 and horizontal[0] > 0 and vertical[3] != horizontal[2]


def test_w_bldactive_of_a_window_below_the_top():
    """The lower of two: no closer, no fuller, no arrows or slider — the bars and the name alone, the title's colour
    and the sizer the plain ones."""
    pokes, lower, _upper = two_windows()
    result = run(W_BLDACTIVE, (lower,), onto=pokes)
    for gadget in ("W_CLOSER", "W_FULLER", "W_UPARROW", "W_VSLIDE", "W_LFARROW", "W_HSLIDE"):
        assert object_links(result, W_ACTIVE, WM[gadget])[0] == NIL, gadget
    assert result.word(aes.AES_GL_ANAME + aes.TE_COLOR) == WM["W_NAME_COLOUR"]
    assert result.long(W_ACTIVE + WM["W_SIZER"] * aes.OB_BYTES + aes.OB_SPEC) == WM["W_SIZER_SPEC"]


# Kinds, each the ROM's own wm_create + wm_open: every arm of the title bar, the information line and the two bars.
KINDS = {
    "the name alone": WM["WK_NAME"],
    "a closer and a fuller, no name": WM["WK_CLOSER"] | WM["WK_FULLER"],
    "an information line alone": WM["WK_INFO"],
    "a vertical bar alone": WM["WK_UPARROW"] | WM["WK_VSLIDE"],
    "a horizontal bar alone": WM["WK_RTARROW"],
    "the sizer alone: both bars": WM["WK_SIZER"],
    "both bars, no sizer": WM["WK_UPARROW"] | WM["WK_RTARROW"],
    "a name and a fuller, no closer": WM["WK_NAME"] | WM["WK_FULLER"],
    "nothing": 0,
}
SIZER_SPECS = {WM["WK_SIZER"]: WM["W_SIZER_SPEC_TOP"], WM["WK_UPARROW"] | WM["WK_RTARROW"]: WM["W_SIZER_SPEC"]}


@functools.cache
def window_of_kind(kind):
    return aes_event.window_chain(kind, *WINDOW_AT, onto=running())


@pytest.mark.parametrize("kind", KINDS.values(), ids=KINDS)
def test_w_bldactive_of_each_kind(kind):
    pokes, window = window_of_kind(kind)
    result = run(W_BLDACTIVE, (window,), onto=pokes)
    assert object_rect(result, W_ACTIVE, WM["W_BOX"]) == WINDOW_AT
    if kind in SIZER_SPECS:
        assert result.long(W_ACTIVE + WM["W_SIZER"] * aes.OB_BYTES + aes.OB_SPEC) == SIZER_SPECS[kind]


def test_w_bldactive_of_nil_touches_nothing():
    assert aes.stored_nothing(run(W_BLDACTIVE, (NIL,), onto=top_window()[0]))


def test_w_bldactive_of_the_desktop():
    """The snapshot's own window 0: no gadgets (kind 0), the root the whole screen."""
    result = run(W_BLDACTIVE, (DESKTOP,))
    assert object_rect(result, W_ACTIVE, WM["W_BOX"]) == SCREEN


# ---- w_mvfix -------------------------------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("source, fixed", (((-1, 30, 100, 50), 1), ((0, 30, 100, 50), 0), ((-2, 30, 100, 50), 0)),
                         ids=("one pixel off the left edge", "on it", "two off"))
def test_w_mvfix(source, fixed, through_line_f):
    result = run(W_MVFIX, (rect_at(0) | aes.BUS_TAG, rect_at(1) | aes.BUS_TAG),
                 merge_pokes(rect_pokes(0, source), rect_pokes(1, (40, 50, 60, 70))), through_line_f=through_line_f)
    assert result.answer() == fixed
    assert grect(result, rect_at(1)) == ((41, 50, 59, 70) if fixed else (40, 50, 60, 70))
    x, y, w, h = source
    assert grect(result, rect_at(0))[:2] == (max(x, 0), max(y, DESKTOP_AREA[1]))


def test_w_mvfix_reads_x_before_the_cut():
    """The destination IS the source: the cut moves x to 0 first, and the fix then adds to the cut's x."""
    result = run(W_MVFIX, (rect_at(0), rect_at(0)), rect_pokes(0, (-1, 30, 100, 50)))
    assert grect(result, rect_at(0)) == (1, 30, 98, 50)


# ---- the drawing routines ------------------------------------------------------------------------------------------------
# Their host slots staged STALE, beside ob_draw's: every GRECT the ROM keeps in its frame is stored before it is read,
# so a C that skipped a store reads STALE where the ROM read its own.
DRAW_SLOTS = merge_pokes(obdraw.STALE_SLOTS, *(aes.stale_host_slot(role) for role in (
    "AES_W_CLIPDRAW_RECT", "AES_W_CPWALK_RECT", "AES_W_MOVE_RECTS")))
# THE BUDGET: measured, the longest ROM run of these draws is the top window's gadgets drawn whole, DRAW_MEASURED_INSNS
# (`test_the_longest_draw_fits_the_default_budget`) — inside the oracle's default cap with 48% to spare (entered through
# its Line-F word, 108,022: 46%).
DRAW_MEASURED_INSNS = 103_934
DEFAULT_INSNS = 200_000                 # `emu.run`'s and the differential's default cap


def draw(name, arguments, pokes=None, *, onto, **kwargs):
    """`name` over `onto` (a derived machine, the door's) with ob_draw's doors."""
    return aes.run_function(name, arguments, merge_pokes(onto, DRAW_SLOTS, pokes), hook=obdraw.doors(), **kwargs)


# A KNOWN CANVAS: a redraw over the pixels the window's own open left changes nothing, so a clip one border too narrow
# or a gadget not rebuilt would draw the same screen. The draws below that must SHOW what they draw start from the
# screen at colour 0 (`vdi.clear_screen_pokes`) — pixels, not machine state.
CLEARED = vdi.clear_screen_pokes()


def gadget_tree():
    return case.long_in(BASE_IMAGE, aes.AES_GL_AWIND)


def test_the_longest_draw_fits_the_default_budget():
    pokes, window = top_window()
    frame = aes.staged(W_CLIPDRAW, (window, gadget_tree(), aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0), pokes)
    _final, _writes, regs = emu.run(make_image(frame), addrs.AES_ROM_W_CLIPDRAW)
    assert regs["ninsns"] == DRAW_MEASURED_INSNS < DEFAULT_INSNS


# ---- w_clipdraw -------------------------------------------------------------------------------------------------------------
@THROUGH
def test_w_clipdraw_draws_the_top_window_s_gadgets_whole(through_line_f):
    """top_window's window: its gadgets (W_ACTIVE as its open left them) drawn under its one visible rectangle,
    no clip handed in (gl_rfull) — over the screen its own open drew, so the pixels come back the same. The tree
    handed on the bus (`aes.BUS_TAG`): ob_draw takes it as handed."""
    pokes, window = top_window()
    result = draw(W_CLIPDRAW, (window, gadget_tree() | aes.BUS_TAG, aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0), CLEARED,
                  onto=pokes, through_line_f=through_line_f)
    assert result.answer() == 0
    assert screen_changed(result)


def test_w_clipdraw_with_no_clip_spares_the_menu_bar():
    """No clip handed in: gl_rfull, below the menu bar — the desktop's top piece (0, 0, 322, 30) drawn from y 11 on,
    the window tree's root (the desktop pattern) under it, the bar's rows left at colour 0."""
    pokes, _window = top_window()
    tree = case.long_in(BASE_IMAGE, aes.AES_GL_WTREE)
    result = draw(W_CLIPDRAW, (DESKTOP, tree, aes.OB_ROOT, 0, 0), CLEARED, onto=pokes)
    assert screen_changed(result)
    assert not any(vdi.read_pixel(result.final, x, y) for x in range(0, 320, 7) for y in range(DESKTOP_AREA[1]))


def test_w_clipdraw_draws_the_desktop_piece_by_piece():
    """The desktop cut in four round the window: the desk's icons drawn under every piece the clip meets — the clip
    (handed in, the screen and more) cut to gl_rfull IN PLACE first."""
    pokes, _window = top_window()
    tree, root = case.long_in(BASE_IMAGE, aes.AES_GL_NEWDESK), case.word_in(BASE_IMAGE, aes.AES_GL_NEWROOT)
    result = draw(W_CLIPDRAW, (DESKTOP, tree, root, WM["WM_MAX_DEPTH"], rect_at(0) | aes.BUS_TAG),
                  rect_pokes(0, (-10, -10, 400, 300)), onto=pokes)
    assert grect(result, rect_at(0)) == DESKTOP_AREA


def test_w_clipdraw_skips_the_pieces_the_clip_misses():
    """A clip inside the desktop's last piece alone: three pieces cut to nothing, one drawn."""
    pokes, _window = top_window()
    tree, root = case.long_in(BASE_IMAGE, aes.AES_GL_NEWDESK), case.word_in(BASE_IMAGE, aes.AES_GL_NEWROOT)
    result = draw(W_CLIPDRAW, (DESKTOP, tree, root, WM["WM_MAX_DEPTH"], rect_at(0)), rect_pokes(0, (0, 150, 320, 40)),
                  onto=pokes)
    assert result.answer() == 0


@functools.cache
def held():
    """top_window's machine with window drawing HELD: the ROM's own wind_set(window, 13)."""
    pokes, window = top_window()
    return window_set(pokes, window, WM["WF_RESVD"], 0), window


@pytest.mark.parametrize("window", (DESKTOP, NIL), ids=("drawing held", "window -1"))
def test_w_clipdraw_draws_nothing(window):
    pokes = held()[0] if window == DESKTOP else top_window()[0]
    result = draw(W_CLIPDRAW, (window, gadget_tree(), aes.OB_ROOT, WM["WM_MAX_DEPTH"], rect_at(0)),
                  rect_pokes(0, SCREEN), onto=pokes)
    assert result.answer() == 1
    assert aes.stored_nothing(result)


def test_drawing_is_held_by_wind_set():
    assert case.word_in(make_image(held()[0]), aes.AES_GL_WFROZEN) == 1


# ---- w_drawdesk -------------------------------------------------------------------------------------------------------------
@functools.cache
def no_desk_tree():
    """top_window's machine with no desk tree: the ROM's own wind_set(0, WF_NEWDESK, 0, 0)."""
    pokes, window = top_window()
    return window_set(pokes, DESKTOP, WM["WF_NEWDESK"], 0, 0, 0), window


# AN APPLICATION'S DESK TREE (wind_set(0, WF_NEWDESK, tree, root) takes any): boxes each inside the last, each a
# different fill, set by the ROM's own wind_set from object 1 — so the root handed is not the tree's, which the
# snapshot's own desk tree (an invisible root over its pattern box) cannot show. THE DEPTH: everyobj draws object 1 at
# level 1 and descends while the level is within the depth handed, so the innermost of DEEPEST_BOXES (six levels below
# object 1) is drawn only at a depth of 6 or more — any depth up to 5 differs. Six below is the deepest a tree goes and
# still returns (`test_a_seven_level_tree_runs_ob_draw_away`), so no tree tells WM_MAX_DEPTH from 6 or 7. The SHALLOW
# tree beside it is the one a draw from the wrong root (object 0, a level more) still returns from, so that C fails a
# compare rather than running into the host's named halt for a walk too deep.
DEEPEST_BOXES = 8
SHALLOW_BOXES = 6
NESTED_ROOT = 1
NESTED_INSET = 6
SOLID = 7                               # the fill pattern of every pixel: the innermost box's, the outer ones' less
# A rectangle of the desktop's right-hand piece (beside top_window's window) the innermost box reaches into, and a
# pixel of the box there: the whole screen's draw runs past the oracle's cap.
NESTED_RECT = (240, 100, 80, 30)
INNERMOST = (250, 110)
OUTERMOST = (SCREEN[2] - NESTED_INSET // 2, 110)       # inside object 0 alone: drawn only from the wrong root


def nested_tree(boxes):
    def box(level):
        size = (SCREEN[2] - 2 * NESTED_INSET * level, SCREEN[3] - 2 * NESTED_INSET * level)
        at = (0, 0) if level == 0 else (NESTED_INSET, NESTED_INSET)
        colour = (level % 15 + 1) | (8 | SOLID - (boxes - 1 - level) % SOLID) << 4 | 1 << 8 | 1 << 12
        return aes.node(None if level == 0 else level - 1, TYPE=aes.G_BOX, SPEC=colour, X=at[0], Y=at[1],
                        WIDTH=size[0], HEIGHT=size[1])
    return aes.tree_pokes([box(level) for level in range(boxes)])


@functools.cache
def nested_desk(boxes=DEEPEST_BOXES):
    pokes, _window = top_window()
    pokes = merge_pokes(pokes, nested_tree(boxes))
    return window_set(pokes, DESKTOP, WM["WF_NEWDESK"], aes.TREE_AT >> 16, aes.TREE_AT & 0xFFFF, NESTED_ROOT)


SEVEN_LEVELS = 9                        # objects 0..8: seven levels below object 1
WALK_CAP_INSNS = 1_000_000              # six times the six-level draw's measured 162,470


def test_a_seven_level_tree_runs_ob_draw_away():
    """The ROM's ob_draw of a chain of boxes seven levels below its start runs past WALK_CAP_INSNS (six levels: 162,470
    instructions; measured once in a scratch run, not within 30,000,000 either). MEASURED, the mechanism: everyobj's
    level-8 store lands on its own saved A6 (the object-walk's documented frame divergence); everyobj still returns to
    ob_draw, the whole tree drawn, and ob_draw's return then unlinks through the corrupt A6 and runs away. So
    w_drawdesk's whole depth is never reached by a tree that returns."""
    staged = merge_pokes(top_window()[0], aes.tree_pokes([aes.node(None if level == 0 else level - 1, TYPE=aes.G_BOX,
                                                                   WIDTH=SCREEN[2], HEIGHT=SCREEN[3])
                                                          for level in range(SEVEN_LEVELS)]),
                         aes.staged("AES_ROM_OB_DRAW", (aes.TREE_AT, NESTED_ROOT, WM["WM_MAX_DEPTH"]), {}))
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(staged), addrs.AES_ROM_OB_DRAW, max_insns=WALK_CAP_INSNS)


@pytest.mark.parametrize("boxes", (DEEPEST_BOXES, SHALLOW_BOXES), ids=("six levels below its root", "four below"))
def test_w_drawdesk_of_an_application_s_tree_draws_from_its_root(boxes):
    pokes = nested_desk(boxes)
    assert case.word_in(make_image(pokes), aes.AES_GL_NEWROOT) == NESTED_ROOT
    result = draw(W_DRAWDESK, (rect_at(0),), merge_pokes(CLEARED, rect_pokes(0, NESTED_RECT)), onto=pokes)
    assert vdi.read_pixel(result.final, *INNERMOST) != 0
    assert vdi.read_pixel(result.final, *OUTERMOST) == 0


@THROUGH
@pytest.mark.parametrize("desk", ("icons", "none"), ids=("the desk's icon tree", "the window tree's root"))
def test_w_drawdesk_grows_the_rectangle_and_redraws_the_desktop(desk, through_line_f):
    pokes = top_window()[0] if desk == "icons" else no_desk_tree()[0]
    result = draw(W_DRAWDESK, (rect_at(0) | aes.BUS_TAG,), merge_pokes(CLEARED, rect_pokes(0, (10, 20, 30, 40))),
                  onto=pokes, through_line_f=through_line_f)
    assert screen_changed(result)
    assert grect(result, rect_at(0)) == (10, 20, 30 + BORDER, 40 + BORDER)


# ---- w_cpwalk / w_strchg ----------------------------------------------------------------------------------------------------
def test_w_cpwalk_rebuilds_the_gadgets_for_its_window():
    """The lower of two windows, W_ACTIVE as the upper one's open left it: drawn only after it is rebuilt for the
    lower one. UNPOISONED, a stand-in for the poisoned cases below: the attribution pass inverts W_ACTIVE, which a C that
    skipped the rebuild then walks into an odd pointer the host refuses — a crash, not a failing compare."""
    pokes, lower, _upper = two_windows()
    result = draw(W_CPWALK, (lower, aes.OB_ROOT, WM["WM_MAX_DEPTH"], 1), CLEARED, onto=pokes, poison=False)
    assert object_links(result, W_ACTIVE, WM["W_CLOSER"])[0] == NIL


@THROUGH
def test_w_cpwalk_of_the_top_window_draws_under_its_whole_rectangle(through_line_f):
    pokes, window = top_window()
    result = draw(W_CPWALK, (window, aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0), CLEARED, onto=pokes,
                  through_line_f=through_line_f)
    assert screen_changed(result)


@pytest.mark.parametrize("use_true", (1, 0), ids=("asked to", "under the clip as it stands"))
def test_w_cpwalk_of_a_lower_window(use_true):
    """The lower of two windows: its gadgets rebuilt as a lower window's and drawn under its whole rectangle when
    asked, else under the clip as it stands — set to the window's own rectangle by the ROM's gsx_sclip — grown by the
    border."""
    pokes, lower, _upper = two_windows()
    clip = rect_at(7)
    pokes = od.clip_set_by_the_rom(clip, merge_pokes(pokes, rect_pokes(7, WINDOW_AT)))
    result = draw(W_CPWALK, (lower, aes.OB_ROOT, WM["WM_MAX_DEPTH"], use_true), CLEARED, onto=pokes)
    assert screen_changed(result)
    assert result.word(aes.AES_GL_ANAME + aes.TE_COLOR) == WM["W_NAME_COLOUR"]


TITLE = b" A title "
TEXT_AT = rect_at(4)


@THROUGH
@pytest.mark.parametrize("gadget", ("W_NAME", "W_INFO"))
def test_w_strchg_sets_the_text_and_draws_the_gadget(gadget, through_line_f):
    pokes, window = top_window()
    result = draw(W_STRCHG, (window, WM[gadget], TEXT_AT | aes.BUS_TAG), merge_pokes(CLEARED, {TEXT_AT: TITLE + b"\0"}),
                  onto=pokes, through_line_f=through_line_f)
    field, tedinfo = ("NAME", aes.AES_GL_ANAME) if gadget == "W_NAME" else ("INFO", aes.AES_GL_AINFO)
    assert record(result, window, field) == TEXT_AT | aes.BUS_TAG
    assert result.long(tedinfo + aes.TE_PTEXT) == TEXT_AT | aes.BUS_TAG
    assert screen_changed(result)


def test_w_strchg_of_a_lower_window_draws_under_its_whole_rectangle():
    """w_cpwalk's use_true: a lower window's gadget drawn under its own rectangle, not the clip as it stands."""
    pokes, lower, _upper = two_windows()
    result = draw(W_STRCHG, (lower, WM["W_NAME"], TEXT_AT), merge_pokes(CLEARED, {TEXT_AT: TITLE + b"\0"}), onto=pokes)
    assert screen_changed(result)


@pytest.mark.parametrize("gadget", ("W_NAME", "W_INFO"))
def test_w_strchg_of_window_minus_one_leaves_the_text_in_the_tedinfo(gadget):
    """Window -1 (below the table; no top window, so the record's and the tree's -1): w_bldactive builds nothing, so
    the TEDINFO's text is w_strchg's own store — every other window's is rebuilt from the record by w_bldactive."""
    result = draw(W_STRCHG, (NIL, WM[gadget], TEXT_AT), {TEXT_AT: TITLE + b"\0"},
                  onto=case.continued(run(WM_START, (), onto=running())))
    tedinfo = aes.AES_GL_ANAME if gadget == "W_NAME" else aes.AES_GL_AINFO
    assert result.long(tedinfo + aes.TE_PTEXT) == TEXT_AT


# ---- w_move -----------------------------------------------------------------------------------------------------------------
STOP_AT = rect_at(5)
REDRAW_AT = rect_at(6)


def move(pokes, window, stop=STOP_AT, rect=REDRAW_AT, **kwargs):
    return draw(W_MOVE, (window, stop, rect), STALE_RECTS, onto=pokes, **kwargs)


@THROUGH
def test_w_move_blits_the_window_and_answers_the_old_rectangle(through_line_f):
    """top_window's window moved by wind_set from WINDOW_AT to MOVED_TO: the image blitted, the old rectangle grown
    by the border to be redrawn. Both pointers on the bus (`aes.BUS_TAG`)."""
    pokes, window = moved()
    result = move(pokes, window, stop=STOP_AT | aes.BUS_TAG, rect=REDRAW_AT | aes.BUS_TAG, through_line_f=through_line_f)
    assert result.answer() == 1
    assert aes.signed(result.word(STOP_AT)) == window
    assert grect(result, REDRAW_AT) == (*WINDOW_AT[:2], WINDOW_AT[2] + BORDER, WINDOW_AT[3] + BORDER)


# A D0 the caller holds: what w_move leaves while drawing is held.
CALLERS_D0 = 0x1234


def test_w_move_while_drawing_is_held_does_nothing():
    """It stores nothing, and sets no D0: the ROM leaves its caller's (entered with CALLERS_D0, it answers it), which
    the C is never handed — so the answer is not compared. Its one caller, draw_change, returns before calling it
    while drawing is held ($fec172)."""
    pokes, window = held()
    result = move(pokes, window, regs={"d0": CALLERS_D0}, answer_compared=False)
    assert aes.stored_nothing(result)
    assert result.info["regs"]["d0"] == CALLERS_D0


@functools.cache
def moved_between(start, end):
    """A window of every gadget opened at `start` and moved to `end`, both by the ROM."""
    pokes, window = aes_event.window_chain(EVERY_GADGET, *start, onto=running())
    return window_set(pokes, window, WM["WF_CURRXYWH"], *end), window


# (where it was, where it is): off the right edge moving left, off the bottom moving up — the union redrawn, no blit —
# and each moving away from the edge it ran off (blitted); one pixel off the left edge moving right, and back — the
# strip drawn by the top window's root, or the old rectangle's left edge moved.
MOVES = {
    "off the right edge, moved left": ((250, 30, 200, 100), (100, 30, 200, 100)),
    "off the right edge, moved down: blitted": ((250, 30, 200, 100), (250, 60, 200, 100)),
    "off the bottom, moved up": ((20, 150, 200, 100), (20, 40, 200, 100)),
    "off the bottom, moved down: blitted": ((20, 150, 200, 100), (20, 160, 200, 100)),
    "from x -1, moved right": ((-1, 30, 200, 100), (50, 30, 200, 100)),
    "to x -1, moved left": ((50, 30, 200, 100), (-1, 30, 200, 100)),
    "from x -1 to x -2: both fixed": ((-1, 30, 200, 100), (-2, 30, 200, 100)),
    "touching the right edge, moved left: blitted": ((118, 30, 200, 100), (50, 30, 200, 100)),
}


@pytest.mark.parametrize("start, end", MOVES.values(), ids=MOVES)
def test_w_move(start, end):
    """Each move's arm, both pointers on the bus (`aes.BUS_TAG`): the stop word and the redraw rectangle stored and
    read back through them."""
    pokes, window = moved_between(start, end)
    result = draw(W_MOVE, (window, STOP_AT | aes.BUS_TAG, REDRAW_AT | aes.BUS_TAG), merge_pokes(STALE_RECTS, CLEARED),
                  onto=pokes)
    blitted = result.answer()
    assert aes.signed(result.word(STOP_AT)) == (window if blitted else 0)


def test_w_move_reads_the_stop_word_back_after_the_copy():
    """The stop word inside the rectangle the redraw is copied to: the copy overwrites it, and the answer is the
    word as the copy left it — the old rectangle's x (20), not the window."""
    pokes, window = moved()
    result = move(pokes, window, stop=REDRAW_AT)
    assert result.answer() == 0


# ---- w_owns / w_union -----------------------------------------------------------------------------------------------------
def desktop_list(pokes):
    return walk(make_image(pokes), list_head(DESKTOP))


def intersection(first, second):
    """rc_intersect's cut of two GRECTs, or None when it is empty."""
    x, y = max(first[0], second[0]), max(first[1], second[1])
    w = min(first[0] + first[2], second[0] + second[2]) - x
    h = min(first[1] + first[3], second[1] + second[3]) - y
    return (x, y, w, h) if w > 0 and h > 0 else None


OFF_THE_DESKTOP = (330, 210, 1, 1)                      # right of and below every piece of the desktop's list


@THROUGH
def test_w_owns_answers_the_first_piece_over_the_rectangle(through_line_f):
    pokes, _window = top_window()
    head = desktop_list(pokes)[0]
    result = run(W_OWNS, (DESKTOP, head, rect_at(0), rect_at(1)), merge_pokes(STALE_RECTS, rect_pokes(0, SCREEN)),
                 onto=pokes, through_line_f=through_line_f)
    assert result.answer() == 1
    assert grect(result, rect_at(1)) == intersection(rect_of(make_image(pokes), head), SCREEN)
    assert result.long(window_record(DESKTOP) + aes.WIN_RNEXT) == case.long_in(make_image(pokes), head)


def test_w_owns_walks_past_pieces_that_miss():
    """A rectangle only the LAST piece meets: every link crossed, the cursor left past it (the list's end, 0)."""
    pokes, _window = top_window()
    pieces = desktop_list(pokes)
    last = rect_of(make_image(pokes), pieces[-1])
    corner = (last[0] + last[2] - 1, last[1] + last[3] - 1, 1, 1)
    result = run(W_OWNS, (DESKTOP, pieces[0] | aes.BUS_TAG, rect_at(0) | aes.BUS_TAG, rect_at(1) | aes.BUS_TAG),
                 merge_pokes(STALE_RECTS, rect_pokes(0, corner)), onto=pokes)
    assert result.answer() == 1
    assert grect(result, rect_at(1)) == corner
    assert result.long(window_record(DESKTOP) + aes.WIN_RNEXT) == 0


def test_w_owns_at_the_end_empties_the_answer():
    pokes, _window = top_window()
    pieces = desktop_list(pokes)
    result = run(W_OWNS, (DESKTOP, pieces[0], rect_at(0), rect_at(1)),
                 merge_pokes(STALE_RECTS, rect_pokes(0, OFF_THE_DESKTOP)), onto=pokes)
    assert result.answer() == 0
    assert grect(result, rect_at(1))[2:] == (0, 0)
    assert result.long(window_record(DESKTOP) + aes.WIN_RNEXT) == 0


def test_w_owns_of_an_empty_list():
    result = run(W_OWNS, (DESKTOP, 0, rect_at(0), rect_at(1)), STALE_RECTS)
    assert result.answer() == 0
    assert grect(result, rect_at(1)) == STALE_GRECT[:2] + (0, 0)


def test_w_owns_reads_the_link_after_the_copy():
    """`out` laid over the first piece's own link and x: the copy overwrites the link with the piece's (x, y), which
    is then followed — as the ROM's `movea.l (a5),a5` after rc_copy follows it — as an address: the cursor left is the
    piece's (x, y) as a longword, not the link the list held. Unpoisoned: the link read is the one the copy wrote,
    which the attribution pass inverts into an odd pointer the host refuses (`vdi.READS_A_POINTER_IT_WRITES`)."""
    pokes, _window = top_window()
    head = desktop_list(pokes)[0]
    x, y, _w, _h = rect_of(make_image(pokes), head)
    result = run(W_OWNS, (DESKTOP, head, rect_at(0), head), merge_pokes(STALE_RECTS, rect_pokes(0, SCREEN)),
                 onto=pokes, **vdi.READS_A_POINTER_IT_WRITES)
    assert result.long(window_record(DESKTOP) + aes.WIN_RNEXT) == (x & 0xFFFF) << 16 | (y & 0xFFFF)
    assert result.long(window_record(DESKTOP) + aes.WIN_RNEXT) != case.long_in(make_image(pokes), head)


@THROUGH
def test_w_union_of_the_desktop_s_pieces_is_their_bounding_box(through_line_f):
    """The desktop cut in four round top_window's window: their union is the rectangle newrect cut them from."""
    pokes, _window = top_window()
    result = run(W_UNION, (desktop_list(pokes)[0] | aes.BUS_TAG, rect_at(0) | aes.BUS_TAG), STALE_RECTS, onto=pokes,
                 through_line_f=through_line_f)
    assert result.answer() == 1
    assert grect(result, rect_at(0)) == DESKTOP_TRUE


@pytest.mark.parametrize("pieces", (0, 1), ids=("an empty list", "one piece"))
def test_w_union_of_a_short_list(pieces):
    head = aes_rlist.DESKTOP_ORECT if pieces else 0
    result = run(W_UNION, (head, rect_at(0)), STALE_RECTS)
    assert result.answer() == pieces
    assert grect(result, rect_at(0)) == (DESKTOP_AREA if pieces else STALE_GRECT)


# ---- wm_start --------------------------------------------------------------------------------------------------------------
@THROUGH
def test_wm_start_sets_the_library_up_again(through_line_f):
    """Over a machine with a window open (top_window): every window but the desktop closed, the desktop's list one
    piece again, the gadget tree retyped, the globals back."""
    pokes, _window = top_window()
    result = run(WM_START, (), onto=pokes, through_line_f=through_line_f)
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]
    assert aes.signed(result.word(aes.AES_GL_WTOP)) == NIL
    assert result.long(aes.AES_GL_NEWDESK) == 0
    assert result.long(W_ACTIVE + WM["W_NAME"] * aes.OB_BYTES + aes.OB_SPEC) == aes.AES_GL_ANAME


def test_wm_start_over_the_snapshot():
    result = run(WM_START, ())
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]


# ---- wm_create / wm_delete -------------------------------------------------------------------------------------------------
@THROUGH
def test_wm_create_claims_the_first_free_window(through_line_f):
    result = run(WM_CREATE, (EVERY_GADGET, rect_at(0) | aes.BUS_TAG), rect_pokes(0, WINDOW_AT), onto=running(),
                 through_line_f=through_line_f)
    assert result.answer() == 1
    assert grect(result, window_record(1) + aes.WIN_FULL) == WINDOW_AT


@functools.cache
def every_window_created():
    """All eight in use: seven windows created by the ROM's wm_create over the running machine."""
    pokes = running()
    for _ in range(aes.AES_WINDOW_COUNT - 1):
        pokes, _window = aes_event.window_created(EVERY_GADGET, *WINDOW_AT, onto=pokes)
    return pokes


def test_wm_create_with_every_window_in_use_answers_nil():
    result = run(WM_CREATE, (EVERY_GADGET, rect_at(0)), rect_pokes(0, WINDOW_AT), onto=every_window_created())
    assert result.answer() == NIL


def test_wm_create_takes_a_window_freed_between_two_in_use():
    """Window 3 deleted (the ROM's wm_delete) of the eight: it is the one claimed."""
    freed = rom_derived(addrs.AES_ROM_WM_DELETE, aes_event.frame_of(("w", 3)), every_window_created())
    result = run(WM_CREATE, (0, rect_at(0)), rect_pokes(0, WINDOW_AT), onto=freed)
    assert result.answer() == 3


@THROUGH
@pytest.mark.parametrize("window", (1, 7, -1), ids=("window 1", "the last", "-1: below the table"))
def test_wm_delete_frees_the_record_and_leaves_its_index_in_d0(window, through_line_f):
    result = run(WM_DELETE, (window,), onto=every_window_created(), through_line_f=through_line_f)
    assert record(result, window, "FLAGS") & aes.WIN_IN_USE == 0
    assert result.info["regs"]["d0"] & 0xFFFF == (aes.AES_THEGLO + window * aes.WIN_BYTES) & 0xFFFF


# ---- wm_get ---------------------------------------------------------------------------------------------------------------
OUT = rect_at(2)
SLIDERS = {WM["WF_HSLIDE"]: 250, WM["WF_VSLIDE"]: 750, WM["WF_HSLSIZE"]: 400, WM["WF_VSLSIZE"]: 600}


@functools.cache
def slid():
    """top_window's window with its sliders set by the ROM's wm_set: positions 250 and 750, sizes 400 and 600 — four
    different words, so a slider read from the wrong field shows."""
    pokes, window = top_window()
    for field, value in SLIDERS.items():
        pokes = window_set(pokes, window, field, value)
    return pokes, window


def switch_offset(field):
    """The D0 wm_get's jump leaves: the field's row in the table, times four."""
    return (field - WM["WF_FIRST"]) * 4


def rectangle_field(at):
    """A rectangle arm: the GRECT at `at(window)` out, D0 its address's low word."""
    return lambda image, window: (rect_of(image, at(window) - aes.ORECT_X), at(window) & 0xFFFF)


def word_field(field, value):
    """A word arm: `value(image, window)` out, D0 the switch's offset."""
    return lambda image, window: (value(image, window), switch_offset(field))


def record_word(name):
    return lambda image, window: case.word_in(image, window_record(window) + aes.field("WIN", name).at)


def first_piece(image, window):
    work = rect_of(image, window_record(window) + aes.WIN_WORK - aes.ORECT_X)
    for piece in walk(image, list_head(window)):
        cut = intersection(rect_of(image, piece), work)
        if cut:
            return cut, 1
    return None, 0


# field: what it answers through `out` and in D0, over the machine it runs on.
GET_FIELDS = {
    "WF_WORKXYWH": rectangle_field(lambda window: window_record(window) + aes.WIN_WORK),
    "WF_CURRXYWH": rectangle_field(lambda window: WINDOW_TREE + window * aes.OB_BYTES + aes.OB_X),
    "WF_PREVXYWH": rectangle_field(lambda window: window_record(window) + aes.WIN_PREV),
    "WF_FULLXYWH": rectangle_field(lambda window: window_record(window) + aes.WIN_FULL),
    "WF_HSLIDE": word_field(WM["WF_HSLIDE"], record_word("HSLIDE")),
    "WF_VSLIDE": word_field(WM["WF_VSLIDE"], record_word("VSLIDE")),
    "WF_TOP": lambda image, window: (window, window),
    "WF_FIRSTXYWH": first_piece,
    "WF_HSLSIZE": word_field(WM["WF_HSLSIZE"], record_word("HSLSIZE")),
    "WF_VSLSIZE": word_field(WM["WF_VSLSIZE"], record_word("VSLSIZE")),
    "WF_SCREEN": word_field(WM["WF_SCREEN"], lambda image, window: (case.long_in(image, aes.AES_GL_TMP + vdi.MFDB_ADDR),
                                                                    case.long_in(image, aes.AES_GL_MLEN))),
}
WORD_FIELDS = {"WF_HSLIDE", "WF_VSLIDE", "WF_TOP", "WF_HSLSIZE", "WF_VSLSIZE"}


def out_of(result, name):
    if name == "WF_SCREEN":
        return result.long(OUT), result.long(OUT + aes.LONG_BYTES)
    if name in WORD_FIELDS:
        return result.word(OUT)
    return grect(result, OUT)


@pytest.mark.parametrize("name", GET_FIELDS)
def test_wm_get_each_field(name):
    """`out` on the bus (`aes.BUS_TAG`) for every arm: the rectangles' rc_copy, the words' stores, w_owns' copy and
    gsx_mret's two longwords each take it as handed."""
    pokes, window = slid()
    result = run(WM_GET, (window, WM[name], OUT | aes.BUS_TAG), STALE_RECTS, onto=pokes)
    out, answer = GET_FIELDS[name](make_image(pokes), window)
    assert out_of(result, name) == out
    assert result.info["regs"]["d0"] & 0xFFFF == answer


def test_wm_get_s_sliders_are_the_ones_wm_set_left():
    pokes, window = slid()
    image = make_image(pokes)
    assert [record_word(name)(image, window) for name in ("HSLIDE", "VSLIDE", "HSLSIZE", "VSLSIZE")] == \
        [250, 750, 400, 600]


def test_wm_get_s_top_of_none_is_0():
    """wm_start's machine: no top window (-1) answers 0, in `out` and D0."""
    result = run(WM_GET, (DESKTOP, WM["WF_TOP"], OUT), STALE_RECTS, onto=case.continued(run(WM_START, ())))
    assert result.word(OUT) == 0 and result.info["regs"]["d0"] & 0xFFFF == 0


@pytest.mark.parametrize("field", (WM["WF_RESVD"], WM["WF_NEWDESK"], WM["WF_FIRST"] - 1, WM["WF_SCREEN"] + 1, -1),
                         ids=("13: a row with no arm", "14: wind_set's alone", "3", "18", "-1"))
def test_wm_get_of_no_field_stores_nothing(field):
    """D0: the table's offset for a row inside it, the field less WF_FIRST for one past it (`bhi`, unsigned)."""
    pokes, window = slid()
    result = run(WM_GET, (window, field, OUT), STALE_RECTS, onto=pokes)
    assert grect(result, OUT) == STALE_GRECT
    inside = 0 <= field - WM["WF_FIRST"] <= WM["WF_SCREEN"] - WM["WF_FIRST"]
    assert result.info["regs"]["d0"] & 0xFFFF == (switch_offset(field) if inside else field - WM["WF_FIRST"]) & 0xFFFF


@THROUGH
def test_wm_get_through_its_word(through_line_f):
    pokes, window = slid()
    result = run(WM_GET, (window, WM["WF_WORKXYWH"], OUT | aes.BUS_TAG), STALE_RECTS, onto=pokes,
                 through_line_f=through_line_f)
    assert grect(result, OUT) == GET_FIELDS["WF_WORKXYWH"](make_image(pokes), window)[0]


# WF_NEXTXYWH READS the cursor w_owns then WRITES: the attribution pass, inverting the cursor before its read, would
# follow a poisoned pointer into the I/O page (measured) — so the walk's NEXT runs go unpoisoned
# (`vdi.READS_A_POINTER_IT_WRITES`), each starting from the cursor the oracle's previous run left, and every piece is
# compared whole (`out`'s four words staged STALE).
def test_wm_get_walks_the_desktop_s_pieces_first_then_next():
    """The desk's own redraw loop: WF_FIRSTXYWH, then WF_NEXTXYWH until an empty answer — every piece of the desktop
    over its work area, each run continued from the one before; the pieces tile the work area round the window."""
    pokes, window = top_window()
    pieces, field, unpoisoned = [], WM["WF_FIRSTXYWH"], {}
    while True:
        result = run(WM_GET, (DESKTOP, field, OUT | aes.BUS_TAG), STALE_RECTS, onto=pokes, **unpoisoned)
        rect = grect(result, OUT)
        if not rect[2] or not rect[3]:
            break
        pieces.append(rect)
        pokes, field, unpoisoned = case.continued(result), WM["WF_NEXTXYWH"], vdi.READS_A_POINTER_IT_WRITES
    window_true = (*WINDOW_AT[:2], WINDOW_AT[2] + BORDER, WINDOW_AT[3] + BORDER)
    assert len(pieces) > 1
    assert aes_rlist.pieces_tile(pieces, DESKTOP_AREA, window_true)


# ---- wm_find ---------------------------------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("x, y, found", ((100, 60, 1), (5, 150, 0), (400, 300, NIL), (210, 40, 1)),
                         ids=("over the window", "over the desktop", "off the screen",
                              "over the window, (y, x) off the screen"))
def test_wm_find(x, y, found, through_line_f):
    pokes, _window = top_window()
    result = run(WM_FIND, (x, y), onto=pokes, through_line_f=through_line_f)
    assert result.answer() == found


# ---- wm_calc ---------------------------------------------------------------------------------------------------------------
CALC_OUT = tuple(rect_at(3) + index * aes.WORD_BYTES for index in range(4))


def calc_model(calc_type, kind, x, y, w, h):
    """wind_calc's rectangle: a pixel each side, a bar (less its shared line) for a title, an information line and
    each scroll bar — added round the work area, or for WC_BORDER taken off the border's."""
    left = right = top = bottom = WM["W_EDGE"]
    top += (HBOX - 1) * (bool(kind & WM["WK_TITLE_BAR"]) + bool(kind & WM["WK_INFO"]))
    right += (WBOX - 1) * bool(kind & WM["WK_VERTICAL_BAR"])
    bottom += (HBOX - 1) * bool(kind & WM["WK_HORIZONTAL_BAR"])
    sign = -1 if calc_type == WM["WC_BORDER"] else 1
    left, top, right, bottom = (sign * edge for edge in (left, top, right, bottom))
    return x + left, y + top, w - left - right, h - top - bottom


CALC_KINDS = {"no gadgets": 0, "every gadget": EVERY_GADGET, "a title and an information line": WM["WK_NAME"] | WM["WK_INFO"],
              "a vertical bar": WM["WK_UPARROW"], "a horizontal bar": WM["WK_RTARROW"], "the sizer": WM["WK_SIZER"]}


@THROUGH
@pytest.mark.parametrize("calc_type", (WM["WC_BORDER"], 1), ids=("WC_BORDER", "WC_WORK"))
@pytest.mark.parametrize("kind", CALC_KINDS.values(), ids=CALC_KINDS)
def test_wm_calc(kind, calc_type, through_line_f):
    result = run(WM_CALC, (calc_type, kind, *WINDOW_AT, *(at | aes.BUS_TAG for at in CALC_OUT)), STALE_RECTS,
                 through_line_f=through_line_f)
    assert grect(result, CALC_OUT[0]) == calc_model(calc_type, kind, *WINDOW_AT)
    assert result.answer() == calc_model(calc_type, kind, *WINDOW_AT)[3]


def test_wm_calc_stores_in_order():
    """All four pointers on one word: the height, stored last, is what is left."""
    result = run(WM_CALC, (1, EVERY_GADGET, *WINDOW_AT, *(CALC_OUT[0],) * 4), STALE_RECTS)
    assert aes.signed(result.word(CALC_OUT[0])) == calc_model(1, EVERY_GADGET, *WINDOW_AT)[3]


def test_wm_calc_stores_x_before_y():
    """x's and y's pointers on one word: y, stored second, is left."""
    result = run(WM_CALC, (1, EVERY_GADGET, *WINDOW_AT, CALC_OUT[0], CALC_OUT[0], *CALC_OUT[2:]), STALE_RECTS)
    assert aes.signed(result.word(CALC_OUT[0])) == calc_model(1, EVERY_GADGET, *WINDOW_AT)[1]


def test_wm_calc_s_words_wrap():
    """Every sum a word: a work area at the coordinates' top edge wraps negative."""
    result = run(WM_CALC, (1, EVERY_GADGET, 0x7FFF, 0x7FFF, -0x8000, -0x8000, *CALC_OUT), STALE_RECTS)
    assert grect(result, CALC_OUT[0]) == tuple(aes.signed(value) for value in
                                               calc_model(1, EVERY_GADGET, 0x7FFF, 0x7FFF, -0x8000, -0x8000))


# ---- the registry ----------------------------------------------------------------------------------------------------------
def register_rows(rows, line_f=(), hook=None):
    """`{label: (name, arguments, pokes)}`, each a DIRECT row, then those labelled in `line_f` through the Line-F word."""
    for label, (name, arguments, pokes) in rows.items():
        aes.register(label, name, arguments, pokes, hook=hook)
    for label in line_f:
        name, arguments, pokes = rows[label]
        aes.register(label, name, arguments, pokes, through_line_f=True, hook=hook)


def _registered_rows():
    chain, top = top_window()
    pair, lower, _upper = two_windows()
    pieces = desktop_list(chain)
    slid_pokes, slid_window = slid()
    rows = {
        "W_ACTIVE": (W_NILIT, (W_ACTIVE_OBJECTS, W_ACTIVE), _leaf()),
        "the window tree": (W_NILIT, (aes.AES_WINDOW_COUNT, WINDOW_TREE), _leaf()),
        "a first child": (W_OBADD, (W_ACTIVE, WM["W_BOX"], WM["W_TITLE"]), unlinked()),
        "after a last child": (W_OBADD, (W_ACTIVE, WM["W_BOX"], WM["W_INFO"]), chain),
        "a closed window": (W_SETUP, (aes.SHELL_PD, 2, EVERY_GADGET), running()),
        "the full rectangle": (W_SETSIZE, (WS_FULL, 1, rect_at(0)), _leaf(rect_pokes(0, WINDOW_AT))),
        "the current rectangle": (W_SETSIZE, (WS_CURR, 1, rect_at(0)), _leaf(rect_pokes(0, WINDOW_AT))),
        "the title bar": (W_ADJUST, (WM["W_BOX"], WM["W_TITLE"], 0, 0, 200, HBOX), chain),
        "a vertical arrow": (W_HVASSIGN, (1, WM["W_VBAR"], WM["W_UPARROW"], 1, 2, 3, 4, 50, 60), chain),
        "a horizontal arrow": (W_HVASSIGN, (0, WM["W_HBAR"], WM["W_LFARROW"], 1, 2, 3, 4, 50, 60), chain),
        "the default size": (W_BARCALC, (1, 100, 500, -1, HBOX, V_ELEVATOR, H_ELEVATOR), _leaf(STALE_RECTS)),
        "a size per mille": (W_BARCALC, (0, 177, 1000, 333, WBOX, V_ELEVATOR, H_ELEVATOR), _leaf(STALE_RECTS)),
        "every vertical gadget": (W_BLDBAR, (EVERY_GADGET, 1, WM["W_VBAR"], 333, 250, *BAR_PLACE), chain),
        "every horizontal gadget": (W_BLDBAR, (EVERY_GADGET, 1, WM["W_HBAR"], 333, 250, *BAR_PLACE), chain),
        "a window below": (W_BLDBAR, (EVERY_GADGET, 0, WM["W_VBAR"], 333, 250, *BAR_PLACE), chain),
        "the top window, every gadget": (W_BLDACTIVE, (top,), chain),
        "a lower window, every gadget": (W_BLDACTIVE, (lower,), pair),
        "a window of no gadgets": (W_BLDACTIVE, (window_of_kind(0)[1],), window_of_kind(0)[0]),
        "window -1": (W_BLDACTIVE, (NIL,), chain),
        "one pixel off the left edge": (W_MVFIX, (rect_at(0), rect_at(1)),
                                        _leaf(merge_pokes(rect_pokes(0, (-1, 30, 100, 50)),
                                                          rect_pokes(1, (40, 50, 60, 70))))),
        "on the screen": (W_MVFIX, (rect_at(0), rect_at(1)),
                          _leaf(merge_pokes(rect_pokes(0, WINDOW_AT), rect_pokes(1, (40, 50, 60, 70))))),
        "the first piece": (W_OWNS, (DESKTOP, pieces[0], rect_at(0), rect_at(1)),
                            merge_pokes(chain, STALE_RECTS, rect_pokes(0, SCREEN))),
        "past every piece": (W_OWNS, (DESKTOP, pieces[0], rect_at(0), rect_at(1)),
                             merge_pokes(chain, STALE_RECTS, rect_pokes(0, OFF_THE_DESKTOP))),
        "an empty list": (W_OWNS, (DESKTOP, 0, rect_at(0), rect_at(1)), _leaf(STALE_RECTS)),
        "four pieces": (W_UNION, (pieces[0], rect_at(0)), merge_pokes(chain, STALE_RECTS)),
        "one piece": (W_UNION, (aes_rlist.DESKTOP_ORECT, rect_at(0)), _leaf(STALE_RECTS)),
        "no list": (W_UNION, (0, rect_at(0)), _leaf(STALE_RECTS)),
        "over the snapshot": (WM_START, (), _leaf()),
        "the first free window": (WM_CREATE, (EVERY_GADGET, rect_at(0)), merge_pokes(running(), rect_pokes(0, WINDOW_AT))),
        "every window in use": (WM_CREATE, (EVERY_GADGET, rect_at(0)),
                                merge_pokes(every_window_created(), rect_pokes(0, WINDOW_AT))),
        "a window": (WM_DELETE, (1,), every_window_created()),
        "of nothing": (WM_FIND, (5, 150), chain),
        "a window's": (WM_FIND, (100, 60), chain),
        "every gadget's border": (WM_CALC, (WM["WC_BORDER"], EVERY_GADGET, *WINDOW_AT, *CALC_OUT), _leaf(STALE_RECTS)),
        "no gadget's work area": (WM_CALC, (1, 0, *WINDOW_AT, *CALC_OUT), _leaf(STALE_RECTS)),
    }
    rows.update({f"{name}": (WM_GET, (slid_window, WM[name], OUT), merge_pokes(slid_pokes, STALE_RECTS))
                 for name in ("WF_WORKXYWH", "WF_HSLIDE", "WF_TOP", "WF_FIRSTXYWH", "WF_SCREEN", "WF_RESVD")})
    rows["past the last field"] = (WM_GET, (slid_window, WM["WF_SCREEN"] + 1, OUT), merge_pokes(slid_pokes, STALE_RECTS))
    return rows


def _registered_draws():
    chain, top = top_window()
    pair, lower, _upper = two_windows()
    held_pokes, held_window = held()
    desk_tree, desk_root = case.long_in(BASE_IMAGE, aes.AES_GL_NEWDESK), case.word_in(BASE_IMAGE, aes.AES_GL_NEWROOT)
    moved_pokes, moved_window = moved()
    union_pokes, union_window = moved_between(*MOVES["off the right edge, moved left"])
    strip_pokes, strip_window = moved_between(*MOVES["from x -1, moved right"])
    return {
        "the top window's gadgets": (W_CLIPDRAW, (top, gadget_tree(), aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0),
                                     merge_pokes(chain, DRAW_SLOTS)),
        "the desktop in four pieces": (W_CLIPDRAW, (DESKTOP, desk_tree, desk_root, WM["WM_MAX_DEPTH"], rect_at(0)),
                                       merge_pokes(chain, DRAW_SLOTS, rect_pokes(0, SCREEN))),
        "drawing held": (W_CLIPDRAW, (held_window, gadget_tree(), aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0),
                         merge_pokes(held_pokes, DRAW_SLOTS)),
        "the desk's icons": (W_DRAWDESK, (rect_at(0),), merge_pokes(chain, DRAW_SLOTS, rect_pokes(0, MOVED_TO))),
        "the window tree's root": (W_DRAWDESK, (rect_at(0),),
                                   merge_pokes(no_desk_tree()[0], DRAW_SLOTS, rect_pokes(0, MOVED_TO))),
        "the top window": (W_CPWALK, (top, aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0), merge_pokes(chain, DRAW_SLOTS)),
        "a lower window under the clip": (W_CPWALK, (lower, aes.OB_ROOT, WM["WM_MAX_DEPTH"], 0),
                                          merge_pokes(pair, DRAW_SLOTS)),
        "a title": (W_STRCHG, (top, WM["W_NAME"], TEXT_AT), merge_pokes(chain, DRAW_SLOTS, {TEXT_AT: TITLE + b"\0"})),
        "an information line": (W_STRCHG, (top, WM["W_INFO"], TEXT_AT),
                                merge_pokes(chain, DRAW_SLOTS, {TEXT_AT: TITLE + b"\0"})),
        "a window moved": (W_MOVE, (moved_window, STOP_AT, REDRAW_AT), merge_pokes(moved_pokes, DRAW_SLOTS, STALE_RECTS)),
        "off the right edge": (W_MOVE, (union_window, STOP_AT, REDRAW_AT),
                               merge_pokes(union_pokes, DRAW_SLOTS, STALE_RECTS)),
        "the strip at the left edge": (W_MOVE, (strip_window, STOP_AT, REDRAW_AT),
                                       merge_pokes(strip_pokes, DRAW_SLOTS, STALE_RECTS)),
    }


register_rows(_registered_rows(), line_f=("W_ACTIVE", "a first child", "a closed window", "the full rectangle",
                                          "the title bar", "a vertical arrow", "the default size",
                                          "every vertical gadget", "the top window, every gadget",
                                          "one pixel off the left edge", "the first piece", "four pieces",
                                          "over the snapshot", "the first free window", "a window", "a window's",
                                          "every gadget's border", "WF_WORKXYWH"))
register_rows(_registered_draws(), line_f=("the top window's gadgets", "the desk's icons", "the top window", "a title",
                                           "a window moved"), hook=obdraw.doors())
# w_move while drawing is held: the ROM leaves its caller's D0 (`test_w_move_while_drawing_is_held_does_nothing`), so the
# row compares no answer.
_held_pokes, _held_window = held()
aes.register("drawing held, moved", W_MOVE, (_held_window, STOP_AT, REDRAW_AT),
             merge_pokes(_held_pokes, DRAW_SLOTS, STALE_RECTS), hook=obdraw.doors(), answer_compared=False)
