"""The SCREEN MANAGER's four handlers (`src/aes/gemctrl.c`, `aes/gemctrl.h`) against the ROM, each AT AN ARRIVAL OF
THE ROM'S OWN ctlmgr (`test/aes_gemctrl.py`: the machines, the chains, how an arrival is made).

    ct_msgup(message, owner, w3..w7)   message ? ap_sendmsg(ct_message, message, owner, w3..w7);  while (button & 1) dsptch()
    hctl_window(w, mx, my)             w != gl_wtop: ct_msgup(WM_TOPPED, owner, w, <four words never set>)
                                       else w_bldactive(w); the gadget ob_find finds under (mx, my):
                                         closer / fuller   gr_watchbox ? WM_CLOSED / WM_FULLED, the box drawn normal
                                         name (MOVER)      gr_dragbox inside the screen below the bar: WM_MOVED
                                         sizer (SIZER)     gr_rubwind, no smaller than a cell or seven boxes: WM_SIZED
                                         a track           the page before or after the elevator: WM_ARROWED
                                         an arrow          WM_ARROWED
                                         an elevator       gr_slidebox: WM_HSLID / WM_VSLID
                                       WM_ARROWED: wm_update(0); { sent ? : ap_sendmsg, sent = 1; dsptch() } while
                                       (button & 1); wm_update(1) — any other: ct_msgup(message, owner, w, x, y, w, h)
    hctl_button(mx, my)                gl_mnclicks ? gl_mnclicks-- : (w = wm_find(mx, my)) > 0 && hctl_window(w, mx, my)
    hctl_rect(mx, my)                  gl_mntree && inside(mx, my, the titles) : mn_do(&title, &item) ? an accessory's
                                       entry: AC_OPEN to it, the title drawn normal; else MN_SELECTED;  ct_msgup(...)

TWO KINDS OF CASE. A handler that RETURNS without a switch (a click: the button is up again where the screen manager
runs) is a door user's differential over the arrival's machine and a priced row. A handler that LEAVES BY THE
DISPATCHER — a press held on a gadget, a drag, an arrow (it yields once even for a click), the menu, the button
waited up — is A ROW THAT SWITCHES, the screen manager its process: the premise on the ROM's own run, the C at the
dispatcher, Tier 1 through the host's scheduler with the door bound, both blobs, the table's two counts.

ROM BEHAVIOURS PINNED HERE, none mended (each has its test below):
  * WM_TOPPED CARRIES FOUR WORDS OF THE STACK: x, y, w and h are locals hctl_window never sets on that path.
  * A SIZER DRAGGED BELOW THE SMALLEST SIZE SPINS: gr_rubwind waits for the mouse to leave the CLAMPED corner's pixel,
    which the mouse is not on — every wait returns at once, and the screen manager never sleeps until the button
    rises. (So that rise is delivered AT A DOOR CALL of the row, the one place the run can take it.)
  * A CLICK ON THE SIZER RESIZES THE WINDOW to the point clicked, and one on the title "moves" it to where it is.
  * MN_SELECTED GOES TO THE PROCESS WORD gl_mnppd's LONGWORD BEGINS WITH — its high word, 0 for every process id.
  * WITH NO MENU BAR, a click on the bar's place and a move along it leave ctlmgr CALLING hctl_rect FOR EVER: each
    call returns at once (no menu) and the manager's wait is satisfied again as it is made.
"""
import functools
import re
import struct
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image

import abi
import aes
import aes_event
import aes_gemctrl as gc
import aes_switch
import aes_switching as switching
import case
import test_aes_ct_mouse as ct_mouse
from aes_gemctrl import (CT_MSGUP, HCTL_BUTTON, HCTL_RECT, HCTL_WINDOW, HIDING, NO_MOVER, NO_SIZER, TALL, THE_DESK, TWO_WINDOWS, WIDE,
                         Arrival, Case, MESSAGES, PRESS, RELEASE, click, gadget_arrival, onto)

BENCH, SHIPPED = "bench", "bench_shipped"
Premise, Priced = switching.Premise, switching.Priced
NO_WINDOW = switching.NO_WINDOW
BLOCKS, YIELDS = aes_event.BLOCKS, aes_event.YIELDS
SM, FIRST, SECOND = gc.THE_SCREEN_MANAGER, gc.FIRST_ACCESSORY, gc.SECOND_ACCESSORY
A = TWO_WINDOWS
MESSAGE_WORDS = aes.AP_MSG_BYTES // aes.WORD_BYTES


# ---- THE CASES ---------------------------------------------------------------------------------------------------------------
def _top(key=A):
    return gc.top_window(key)


def _about_the_top(message, *words, key=A):
    """The message `message` about the top window of `key`: to its owner, its handle, then `words` — or, with none,
    where the window is."""
    top = _top(key)
    return (MESSAGES[message], top.owner, top.handle, *(words or (top.x, top.y, top.w, top.h)))


ARROW = {name: value for name, value in zip(
    ("the up arrow", "the down arrow", "the vertical track above its elevator", "the vertical track below its elevator",
     None, "the left arrow", "the right arrow", "the horizontal track left of its elevator",
     "the horizontal track right of its elevator"),
    struct.unpack(f">{gc.GEMCTRL['HCTL_ARROW_ACTIONS']}h",
                  bytes(BASE_IMAGE[gc.GEMCTRL["AES_ARROW_ACTIONS"]:][:gc.GEMCTRL["HCTL_ARROW_ACTIONS"] * aes.WORD_BYTES]))) if name}


def _arrowed(name, key=A):
    top = _top(key)
    return _about_the_top("WM_ARROWED", ARROW[name], top.y, top.w, top.h, key=key)


def _menu(title_point):
    return {0: (onto(title_point),)}


VIEW_DROPPED = _menu(aes_event.THE_VIEW_TITLE_S_POINT)
DESK_DROPPED = _menu(gc.THE_DESK_TITLE_S_POINT)
A_DRAG_TO, A_SIZE_TO, A_SHRINK_TO = (150, 60), (280, 180), (12, 30)
THE_TITLE_S_POINT, THE_SIZER_S_POINT = gc.gadget(A, "the title"), gc.gadget(A, "the sizer")
ELEVATOR_TO = {"the vertical elevator": (250, 110), "the horizontal elevator": (200, 157)}
THE_OTHER_WINDOW_S_TITLE = (gc.other_window(A).x + 12, gc.other_window(A).y + 4)
ON_THE_OTHER_WINDOW = {0: (onto(THE_OTHER_WINDOW_S_TITLE),)}
ACCESSORY_ENTRY = gc.accessory_entry_point(A)
ENTRY_CHOSEN = {**DESK_DROPPED, 1: (onto(ACCESSORY_ENTRY),)}
# THE BAR HIDDEN (the HIDING machine: its accessory's entry chosen, the accessory hides the bar), then a click on the
# bar's place and a move along it IN ONE IDLE — the press hands the screen manager the mouse, the move then satisfies
# its wait: the one way ctlmgr calls hctl_rect with no menu.
THE_BAR_HIDDEN = {**_menu(gc.THE_DESK_TITLE_S_POINT), 1: (onto(gc.accessory_entry_point(HIDING)),), 2: (click,)}
ALONG_THE_HIDDEN_BAR = {**THE_BAR_HIDDEN, 3: (onto((200, 5)),), 4: (click, onto((220, 5)))}
# The release that ends a spin of rubber-banding below the smallest size: at the row's fifth door call (the lock, the
# wait that blocks, then waits that return at once).
THE_RISE_INSIDE_THE_SPIN = {4: RELEASE}


def _top_arrival(name, button, routine=HCTL_WINDOW, key=A):
    return gadget_arrival(key, name, button, routine)


def _accessory_open():
    return (MESSAGES["AC_OPEN"], gc.pid_of(A, FIRST), gc.GEMCTRL["HCTL_DESK_TITLE"], 0, 0, 0, 0)


def _desk_s_own(key):
    return (MESSAGES["MN_SELECTED_MESSAGE"], 0, gc.GEMCTRL["HCTL_DESK_TITLE"], gc.desk_s_own_item(key)[0], 0, 0, 0)


def _moved_to(point):
    top = _top()
    dx, dy = point[0] - THE_TITLE_S_POINT[0], point[1] - THE_TITLE_S_POINT[1]
    return _about_the_top("WM_MOVED", top.x + dx, top.y + dy, top.w, top.h)


def _sized_to(width, height, key=A):
    top = _top(key)
    return _about_the_top("WM_SIZED", top.x, top.y, width, height, key=key)


def _to_the_mouse(point):
    top = _top()
    return _sized_to(point[0] - top.x + 1, point[1] - top.y + 1)


def _globals(key, *names):
    return tuple(aes.signed(case.word_in(gc.machine(key).ram, getattr(aes, name))) for name in names)


def _bar_minimum(key, box, cell, bar):
    """The smallest side the ROM rubber-bands a window to: seven boxes where the side carries a scroll bar, a cell
    where it does not — read off the machine's own metrics."""
    box, cell = _globals(key, box, cell)
    return box * gc.GEMCTRL["HCTL_BAR_BOXES"] if bar else cell


def _smallest(key, horizontal_bar, vertical_bar):
    return _sized_to(_bar_minimum(key, "AES_GL_WBOX", "AES_GL_WCHAR", horizontal_bar),
                     _bar_minimum(key, "AES_GL_HBOX", "AES_GL_HCHAR", vertical_bar), key=key)


NONE = None                             # a run that sends nothing
RETURNS = {
    HCTL_BUTTON: {
        "a click the menu bar posted for itself (the boot's own): counted off": Case(gc.BOOT_ARRIVAL),
        "the hidden bar's two clicks, counted twice and posted once: counted down to one":
            Case(Arrival(HIDING, THE_BAR_HIDDEN, HCTL_BUTTON)),
        "a real click on a window's closer after them: the count still one, the click swallowed":
            Case(Arrival(HIDING, {**THE_BAR_HIDDEN, 3: (onto(gc.gadget(HIDING, "the closer")),), 4: (click,)}, HCTL_BUTTON, 1)),
        "a click on the bar past the titles: the desktop's place, nothing":
            Case(Arrival(A, {0: (onto(gc.ON_THE_BAR_PAST_THE_TITLES),), 1: (click,)}, HCTL_BUTTON)),
        "the top window's closer clicked: the window found and worked":
            Case(_top_arrival("the closer", click, HCTL_BUTTON), message=lambda: _about_the_top("WM_CLOSED")),
    },
    HCTL_WINDOW: {
        "the closer clicked: WM_CLOSED": Case(_top_arrival("the closer", click), message=lambda: _about_the_top("WM_CLOSED")),
        "the fuller clicked: WM_FULLED": Case(_top_arrival("the fuller", click), message=lambda: _about_the_top("WM_FULLED")),
        "the title clicked: WM_MOVED to where it is":
            Case(_top_arrival("the title", click), message=lambda: _moved_to(THE_TITLE_S_POINT)),
        "the sizer clicked: WM_SIZED to the point clicked":
            Case(_top_arrival("the sizer", click), message=lambda: _to_the_mouse(THE_SIZER_S_POINT)),
        "the information line clicked: no gadget's, nothing sent": Case(_top_arrival("the information line", click)),
        "a window that is not the top one: WM_TOPPED":
            Case(Arrival(A, {**ON_THE_OTHER_WINDOW, 1: (click,)}, HCTL_WINDOW),
                 message=lambda: (MESSAGES["WM_TOPPED"], gc.other_window(A).owner, gc.other_window(A).handle,
                                  *[gc.GEMCTRL["HCTL_STALE_WORD"]] * 4)),
        "the title of a window with a SIZER and no MOVER clicked: nothing sent":
            Case(_top_arrival("the title", click, key=NO_MOVER)),
        "the corner of a window with a MOVER and no SIZER clicked: nothing sent":
            Case(_top_arrival("the sizer", click, key=NO_SIZER)),
    },
    CT_MSGUP: {
        "WM_CLOSED, the button up: sent": Case(_top_arrival("the closer", click, CT_MSGUP), message=lambda: _about_the_top("WM_CLOSED")),
        "no message, the button up: nothing": Case(_top_arrival("the information line", click, CT_MSGUP)),
    },
    HCTL_RECT: {
        "the mouse off the titles again, along the bar, before the manager ran: nothing":
            Case(Arrival(A, VIEW_DROPPED, HCTL_RECT, at_polls={1: (onto(gc.ON_THE_BAR_PAST_THE_TITLES),)})),
        "no menu bar: nothing": Case(Arrival(HIDING, ALONG_THE_HIDDEN_BAR, HCTL_RECT, 1)),
    },
}
# THE ROWS THAT SWITCH. `switches`: how the handler FIRST leaves (BLOCKS in a wait, YIELDS with its process ready).
# `priced` False: Tier 1 only — another word of one table of a priced row's arm (the arrows), said beside it.
Switching = functools.partial(Case, switches=BLOCKS)
Yielding = functools.partial(Case, switches=YIELDS)
SWITCHES = {
    HCTL_BUTTON: {
        "the top window's up arrow clicked: found, the arrow sent, one yield":
            Yielding(_top_arrival("the up arrow", click, HCTL_BUTTON), message=lambda: _arrowed("the up arrow")),
    },
    HCTL_WINDOW: {
        "the closer held; released inside it: WM_CLOSED":
            Switching(_top_arrival("the closer", PRESS), at_idle={0: RELEASE}, message=lambda: _about_the_top("WM_CLOSED")),
        "the fuller held; the mouse taken off it, then released: nothing sent":
            Switching(_top_arrival("the fuller", PRESS), at_idle={0: onto(gc.OFF_EVERY_MENU), 1: RELEASE}),
        "the title held; dragged, then released: WM_MOVED":
            Switching(_top_arrival("the title", PRESS), at_idle={0: onto(A_DRAG_TO), 1: RELEASE},
                      message=lambda: _moved_to(A_DRAG_TO)),
        "the sizer held; stretched, then released: WM_SIZED":
            Switching(_top_arrival("the sizer", PRESS), at_idle={0: onto(A_SIZE_TO), 1: RELEASE},
                      message=lambda: _to_the_mouse(A_SIZE_TO)),
        "the sizer held; shrunk past the smallest size, both bars: seven boxes each way":
            Switching(_top_arrival("the sizer", PRESS), at_idle={0: onto(A_SHRINK_TO)}, at_calls=THE_RISE_INSIDE_THE_SPIN,
                      message=lambda: _smallest(A, True, True)),
        "the sizer held; shrunk, a vertical bar alone: a cell wide, seven boxes high":
            Switching(_top_arrival("the sizer", PRESS, key=TALL), at_idle={0: onto(A_SHRINK_TO)},
                      at_calls=THE_RISE_INSIDE_THE_SPIN, message=lambda: _smallest(TALL, False, True)),
        "the sizer held; shrunk, a horizontal bar alone: seven boxes wide, a cell high":
            Switching(_top_arrival("the sizer", PRESS, key=WIDE), at_idle={0: onto(A_SHRINK_TO)},
                      at_calls=THE_RISE_INSIDE_THE_SPIN, message=lambda: _smallest(WIDE, True, False)),
        "the vertical elevator held; dragged up, then released: WM_VSLID":
            Switching(_top_arrival("the vertical elevator", PRESS),
                      at_idle={0: onto(ELEVATOR_TO["the vertical elevator"]), 1: RELEASE}, message="WM_VSLID"),
        "the horizontal elevator held; dragged right, then released: WM_HSLID":
            Switching(_top_arrival("the horizontal elevator", PRESS),
                      at_idle={0: onto(ELEVATOR_TO["the horizontal elevator"]), 1: RELEASE}, message="WM_HSLID"),
        "the up arrow clicked: the lock let go, the arrow sent, one yield, the lock taken again":
            Yielding(_top_arrival("the up arrow", click), message=lambda: _arrowed("the up arrow")),
        "the track right of the horizontal elevator clicked: the page after":
            Yielding(_top_arrival("the horizontal track right of its elevator", click),
                     message=lambda: _arrowed("the horizontal track right of its elevator")),
        "the up arrow held: sent, read by its owner, sent again; released":
            Yielding(_top_arrival("the up arrow", PRESS), at_polls={1: RELEASE},
                     message=lambda: _arrowed("the up arrow")),
        "the information line held: nothing sent, a yield until the button rises":
            Yielding(_top_arrival("the information line", PRESS), at_polls={0: RELEASE}),
        "a window that is not the top one, held: WM_TOPPED, then the button waited up":
            Yielding(Arrival(A, {**ON_THE_OTHER_WINDOW, 1: (PRESS,)}, HCTL_WINDOW), at_polls={0: RELEASE},
                     message=lambda: (MESSAGES["WM_TOPPED"], gc.other_window(A).owner, gc.other_window(A).handle,
                                      *[gc.GEMCTRL["HCTL_STALE_WORD"]] * 4)),
    },
    CT_MSGUP: {
        "no message, the button down: two yields until it rises":
            Yielding(_top_arrival("the information line", PRESS, CT_MSGUP), at_polls={1: RELEASE}),
        "AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise":
            Yielding(Arrival(A, {**ENTRY_CHOSEN, 2: (PRESS,)}, CT_MSGUP), at_polls={1: RELEASE}, message=_accessory_open),
    },
    HCTL_RECT: {
        "on View; an item reached, then clicked: MN_SELECTED to process 0":
            Switching(Arrival(A, VIEW_DROPPED, HCTL_RECT), at_idle={0: aes_event.ONTO_ITS_PLAIN_ITEM, 1: click},
                      message=lambda: (MESSAGES["MN_SELECTED_MESSAGE"], 0, gc.THE_VIEW_TITLE, gc.VIEW_S_PLAIN_ITEM, 0, 0, 0)),
        "on Desk; the accessory's entry reached, then clicked: AC_OPEN to the accessory":
            Switching(Arrival(A, DESK_DROPPED, HCTL_RECT), at_idle={0: onto(ACCESSORY_ENTRY), 1: click}, message=_accessory_open),
        "on View; the menu left, a click off it: nothing chosen, nothing sent":
            Switching(Arrival(A, VIEW_DROPPED, HCTL_RECT), at_idle={0: onto(gc.OFF_EVERY_MENU), 1: click}),
        "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds":
            Switching(Arrival(THE_DESK, DESK_DROPPED, HCTL_RECT),
                      at_idle={0: onto(gc.desk_s_own_item(THE_DESK)[1]), 1: click}, message=lambda: _desk_s_own(THE_DESK)),
    },
}
# ...AND THE REST OF THE ARROWS' TABLE, Tier 1 only: each the arm a priced row above runs, with another word of
# `AES_ARROW_ACTIONS` (the down, left and right arrows; the three other pages).
# ...AND TWO MORE SHAPES OF THE MENU'S END, Tier 1 only (hctl_rect's priced rows run the same arms): the desk's own
# item chosen WITH an accessory registered (an item below gl_dafirst is no accessory's), and the menu left by a
# press HELD — nothing chosen, nothing sent, and the button still waited up.
MORE_OF_THE_MENU = {
    "on Desk; the desk's own item clicked, an accessory registered: MN_SELECTED":
        Switching(Arrival(A, DESK_DROPPED, HCTL_RECT), at_idle={0: onto(gc.desk_s_own_item(A)[1]), 1: click},
                  message=lambda: _desk_s_own(A)),
    "on View; the menu left, the button pressed off it and HELD: nothing sent, the button waited up":
        Switching(Arrival(A, VIEW_DROPPED, HCTL_RECT), at_idle={0: onto(gc.OFF_EVERY_MENU), 1: PRESS}, at_polls={5: RELEASE}),
}
OTHER_ARROWS = {f"{name} clicked": Yielding(_top_arrival(name, click), message=functools.partial(_arrowed, name))
                for name in ARROW if name not in ("the up arrow", "the horizontal track right of its elevator")}
# ...AND THE DRAG'S BOUND, Tier 1 only (the arm the dragged row prices; the bound is kept by gr_dragbox's own
# rc_constrain): the title taken by its left end and dragged as far right as the mouse goes — the window stops with a
# box and six pixels of its title on the screen — and to the screen's top left corner: stopped at the left edge,
# below the menu bar.
THE_TITLE_S_LEFT_END = gc.gadget(A, "the title's left end")
FAR_RIGHT, THE_TOP_LEFT_CORNER = (319, THE_TITLE_S_LEFT_END[1]), (0, 0)


def _kept_at(x=None, y=None):
    top = _top()
    return _about_the_top("WM_MOVED", top.x if x is None else x, top.y if y is None else y, top.w, top.h)


def _rightmost():
    (screen_width, box_width), top = _globals(A, "AES_GL_WIDTH", "AES_GL_WBOX"), _top()
    return _kept_at(x=screen_width - box_width - gc.GEMCTRL["HCTL_DRAG_TITLE_KEPT"], y=top.y)


THE_BOUND = {
    "the title held by its left end; dragged to the right edge: a box and six pixels of it kept on the screen":
        Switching(_top_arrival("the title's left end", PRESS), at_idle={0: onto(FAR_RIGHT), 1: RELEASE}, message=_rightmost),
    "the title held; dragged to the screen's top left corner: kept at the left edge, below the bar":
        Switching(_top_arrival("the title's left end", PRESS), at_idle={0: onto(THE_TOP_LEFT_CORNER), 1: RELEASE},
                  message=lambda: _kept_at(x=gc.GEMCTRL["HCTL_DRAG_LEFT"], y=_globals(A, "AES_GL_HBOX")[0])),
}
# ...AND THREE MORE SHAPES, Tier 1 only. EVERY BIT OF THE TWO MASKS THE SMALLEST SIZE IS READ BY: a window whose
# bars carry ONE gadget each — a slider with no arrow, an arrow with no slider — shrunk past it: seven boxes each
# way on all three, each by a bit no other machine's clamp rests on. THE ELEVATOR DRAGGED TO ITS TRACK'S END: the
# whole thousand. And ct_msgup's wait is for THE LEFT BUTTON ALONE: the left one let go as the right one goes down
# ends it with a button still held.
ONE_BIT_A_BAR = {
    f"the sizer held; shrunk, {key.removeprefix('a sizer, ')}: seven boxes each way":
        Switching(gc.gadget_arrival_later(key, "the sizer", PRESS), at_idle={0: onto(A_SHRINK_TO)}, at_calls=THE_RISE_INSIDE_THE_SPIN,
                  message=functools.partial(lambda key: _smallest(key, True, True), key))
    for key in gc.ONE_GADGET_A_BAR}
THE_TRACK_S_END = (gc.gadget(A, "the vertical elevator")[0], 199)
THE_WHOLE_THOUSAND = WHOLE = aes.header_constants("wmlib.h")["W_SLIDER_SCALE"]
TO_THE_END = {
    "the vertical elevator held; dragged past its track's end, then released: WM_VSLID, the whole thousand":
        Switching(_top_arrival("the vertical elevator", PRESS), at_idle={0: onto(THE_TRACK_S_END), 1: RELEASE},
                  message=lambda: _about_the_top("WM_VSLID", WHOLE, _top().y, _top().w, _top().h)),
}
THE_LEFT_BUTTON_ALONE = {
    "no message, the button down; the left one let go as the RIGHT one goes down: the wait ends, a button held":
        Yielding(_top_arrival("the information line", PRESS, CT_MSGUP), at_polls={0: gc.right_for_left}),
}
TIER_1_ONLY = {HCTL_WINDOW: {**OTHER_ARROWS, **THE_BOUND, **ONE_BIT_A_BAR, **TO_THE_END}, HCTL_RECT: MORE_OF_THE_MENU,
               CT_MSGUP: THE_LEFT_BUTTON_ALONE}


# THE MENU'S LAST VDI CALL IS ct_mouse's RE-SHOW, where the mouse was shown when mn_do took it (as it is at every real
# arrival): contrl[3] is then the ROM's stack word and the C's CT_MOUSE_STALE_COUNT (`ctrl.c`'s MISSING ARGUMENT,
# `test_aes_ct_mouse.py`) — by nature, in the rows whose run makes no VDI call after the menu (AC_OPEN's redraws the
# title, and a button held past the menu is followed by its rise's own: their last VDI call is another).
THE_STALE_COUNT = ct_mouse.CONTRL_COUNT_DROP


def _flat(table):
    return {(routine, label): each for routine, cases in table.items() for label, each in cases.items()}


RETURNING, SWITCHING, UNPRICED = _flat(RETURNS), _flat(SWITCHES), _flat(TIER_1_ONLY)
# ...and where the button is still down past the menu, the stale count stands only UNTIL the rise's own VDI call:
# it differs at the dispatches in between and is equal again at the end — left out of the images at the stops alone.
THE_STALE_COUNT_IS_OVERWRITTEN = frozenset({
    (HCTL_RECT, "on View; the menu left, the button pressed off it and HELD: nothing sent, the button waited up"),
})
THE_MOUSE_SHOWN_AGAIN_LAST = frozenset({
    (HCTL_RECT, "on View; an item reached, then clicked: MN_SELECTED to process 0"),
    (HCTL_RECT, "on View; the menu left, a click off it: nothing chosen, nothing sent"),
    (HCTL_RECT, "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds"),
    (HCTL_RECT, "on Desk; the desk's own item clicked, an accessory registered: MN_SELECTED"),
})


def _id(key):
    routine, label = key
    return f"{gc.name_of(routine)}: {label}"


def run(key, **kwargs):
    """A handler that returns, at its arrival: a door user's run, its C first in a child (`aes_event.run_guarded`),
    the VDI's cores and just_draw served — the whole image the ROM's, every frame the door is handed the ROM's."""
    routine, _label = key
    arrived = gc.at(RETURNING[key].arrival)
    assert arrived.name == routine
    # (...the keyboard poll's trap save moved into the run's stack band, as the case's registered row stages it and
    # for `at_its_first_switch`'s reason: the door's images at its calls' returns leave out the SNAPSHOT's frame.)
    staged = case.merge_pokes(arrived.pokes, aes_event.savptr_in_the_band())
    return aes_event.run_guarded(arrived.name, arrived.arguments, staged, drawing=True, objects=gc.JUST_DRAW, **kwargs)


def at_its_first_switch(made):
    """A HANDLER THAT SWITCHES, taken to its first switch on both shores with nothing delivered (`aes_event.interrupted`:
    the C refused at the dispatcher's hook, its whole image the ROM's at dsptch, and at every door call's return on
    the way) — OVER THE ROW'S OWN STAGED MACHINE (`aes_switching._staged`: the one its companion and its Tier 3 row
    run over), the keyboard poll's trap save moved into the run's stack band. NOT the arrival's machine as it
    stands: `interrupted` takes its images at the door calls' returns with the tree's own exclusions and names no
    window beside, and the tree's trap-save exclusion is the SNAPSHOT's frame, which is this booted machine's only
    over a snapshot captured between two polls (`aes_gemctrl.its_trap_save`) — over one captured inside a BIOS
    trap these cases were red in the frame under the machine's own savptr, at HEAD too."""
    return aes_event.interrupted(made.name, made.arguments, switching._staged(made), {}, objects=True, switches=BLOCKS)


@functools.cache
def row(key):
    """A handler that switches, at its arrival, as the row it is (`aes_event.woken_row`): the screen manager's."""
    routine, label = key
    each = {**SWITCHING, **UNPRICED}[key]
    arrived = gc.at(each.arrival)
    assert arrived.name == routine
    made = aes_event.woken_row(label, arrived.name, arrived.arguments, lambda: arrived.pokes, each.at_idle or {},
                               each.at_calls, objects=True, answered=False)
    return made._replace(at_polls=each.at_polls, also_dropped=THE_STALE_COUNT if key in THE_MOUSE_SHOWN_AGAIN_LAST else ())


def message_of(memory):
    """The message the screen manager's own buffer holds in `memory`: its eight words."""
    return struct.unpack(f">{MESSAGE_WORDS}h", bytes(memory[aes.AES_CT_MESSAGE:aes.AES_CT_MESSAGE + aes.AP_MSG_BYTES]))


def the_message(each):
    """What a case says its run sends last: `(type, to, five words)`, a type alone (`(type,)`), or None."""
    said = each.message
    if said is None:
        return None
    return (MESSAGES[said],) if isinstance(said, str) else said()


def vet_the_message(key, each, started, ended, written_to=None):
    """THE MESSAGE A RUN LEAVES in the screen manager's buffer is what the case says: its type, the sender (the
    screen manager), no extra bytes, the five words — or, for a run that sends none, the buffer as it was found."""
    expected = the_message(each)
    if expected is None:
        assert message_of(ended) == message_of(started), f"{_id(key)}: a message was built"
        return
    kind, *rest = expected
    found = message_of(ended)
    assert (found[aes.AP_MSG_TYPE // 2], found[aes.AP_MSG_SENDER // 2], found[aes.AP_MSG_EXTRA // 2]) == (
        kind, gc.pid_of(each.arrival.machine, SM), 0), f"{_id(key)}: sends {found}"
    if rest:
        to, *words = rest
        assert found[aes.AP_MSG_WORDS // 2:] == tuple(words), f"{_id(key)}: sends {found}, expected the words {words}"
        assert written_to is None or written_to == to, f"{_id(key)}: written to process {written_to}, expected {to}"


def last_written_to(calls):
    """The process the LAST message of a run was written to: its last ap_rdwr's (`aes_event.Handed`)."""
    writes = [call for call in calls if call.routine == addrs.AES_ROM_AP_RDWR]
    return aes.signed(writes[-1].arguments[1]) if writes else None


# ---- REGISTERED: every returning case a priced row; every switching case but the arrows' other words -----------------------
for _key, _each in RETURNING.items():
    _arrived = gc.at(_each.arrival)
    aes_event.register(_key[1], _arrived.name, _arrived.arguments, _arrived.pokes, drawing=True, objects=gc.JUST_DRAW,
                       answer_compared=False)
ROWS = {_key[1]: row(_key) for _key in SWITCHING}
REGISTERED = {switching.row_name(each): each for each in map(aes_event.register_woken, ROWS.values())}
KEY_OF = {label: key for key in SWITCHING for label in (key[1],)}
assert len(ROWS) == len(SWITCHING) == len(REGISTERED), "two rows of one label"

# WHAT THE ROM'S OWN RUN OF EACH REGISTERED ROW IS: the idles it takes a delivery at, the idles it makes, every
# process its dispatcher enters (by name: an accessory's PD lies where GEMDOS put its block), and the polls that are
# no idle it takes a delivery at. THE WHOLE RUN'S CYCLES on each blob (the ROM's, ours) and WHAT THE TABLE PRICES
# (each shore's own, the caller's own, the calls it is net of, its foreign windows).
# @PINS-BEGIN (measured: scratch `b5/C/pins.py`)
PREMISES = {
    "the top window's up arrow clicked: found, the arrow sent, one yield":
        ((), 0, (SM,), ()),
    'the closer held; released inside it: WM_CLOSED':
        ((0,), 1, (SM,), ()),
    'the fuller held; the mouse taken off it, then released: nothing sent':
        ((0, 1), 2, (SM, SM), ()),
    'the title held; dragged, then released: WM_MOVED':
        ((0, 1), 2, (SM, SM), ()),
    'the sizer held; stretched, then released: WM_SIZED':
        ((0, 1), 2, (SM, SM), ()),
    'the sizer held; shrunk past the smallest size, both bars: seven boxes each way':
        ((0,), 1, (SM,), ()),
    'the sizer held; shrunk, a vertical bar alone: a cell wide, seven boxes high':
        ((0,), 1, (SM,), ()),
    'the sizer held; shrunk, a horizontal bar alone: seven boxes wide, a cell high':
        ((0,), 1, (SM,), ()),
    'the vertical elevator held; dragged up, then released: WM_VSLID':
        ((0, 1), 2, (SM, SM), ()),
    'the horizontal elevator held; dragged right, then released: WM_HSLID':
        ((0, 1), 2, (SM, SM), ()),
    'the up arrow clicked: the lock let go, the arrow sent, one yield, the lock taken again':
        ((), 0, (SM,), ()),
    'the track right of the horizontal elevator clicked: the page after':
        ((), 0, (SM,), ()),
    'the up arrow held: sent, read by its owner, sent again; released':
        ((), 0, (SM, SECOND, SM), (1,)),
    'the information line held: nothing sent, a yield until the button rises':
        ((), 0, (SM,), (0,)),
    'a window that is not the top one, held: WM_TOPPED, then the button waited up':
        ((), 0, (SM,), (0,)),
    'no message, the button down: two yields until it rises':
        ((), 0, (SM, SM), (1,)),
    "AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise":
        ((), 0, (SM, FIRST, SM), (1,)),
    'on View; an item reached, then clicked: MN_SELECTED to process 0':
        ((0, 1), 2, (SM, SM), ()),
    "on Desk; the accessory's entry reached, then clicked: AC_OPEN to the accessory":
        ((0, 1), 2, (SM, SM), ()),
    'on View; the menu left, a click off it: nothing chosen, nothing sent':
        ((0, 1), 2, (SM, SM), ()),
    "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds":
        ((0, 1), 2, (SM, SM), ()),
}
WHOLE_RUN = {
    "the top window's up arrow clicked: found, the arrow sent, one yield":
        {BENCH: (106462, 59086), SHIPPED: (106462, 57356)},
    'the closer held; released inside it: WM_CLOSED':
        {BENCH: (226780, 167674), SHIPPED: (226780, 164708)},
    'the fuller held; the mouse taken off it, then released: nothing sent':
        {BENCH: (261404, 200470), SHIPPED: (261404, 197926)},
    'the title held; dragged, then released: WM_MOVED':
        {BENCH: (481298, 421920), SHIPPED: (481298, 417754)},
    'the sizer held; stretched, then released: WM_SIZED':
        {BENCH: (666140, 606948), SHIPPED: (666140, 602204)},
    'the sizer held; shrunk past the smallest size, both bars: seven boxes each way':
        {BENCH: (1072748, 1014592), SHIPPED: (1072748, 1009602)},
    'the sizer held; shrunk, a vertical bar alone: a cell wide, seven boxes high':
        {BENCH: (1051350, 1002914), SHIPPED: (1051350, 997778)},
    'the sizer held; shrunk, a horizontal bar alone: seven boxes wide, a cell high':
        {BENCH: (983866, 935512), SHIPPED: (983866, 930376)},
    'the vertical elevator held; dragged up, then released: WM_VSLID':
        {BENCH: (441652, 377750), SHIPPED: (441652, 373048)},
    'the horizontal elevator held; dragged right, then released: WM_HSLID':
        {BENCH: (442638, 379628), SHIPPED: (442638, 375058)},
    'the up arrow clicked: the lock let go, the arrow sent, one yield, the lock taken again':
        {BENCH: (101422, 55756), SHIPPED: (101422, 54186)},
    'the track right of the horizontal elevator clicked: the page after':
        {BENCH: (102158, 54780), SHIPPED: (102158, 53474)},
    'the up arrow held: sent, read by its owner, sent again; released':
        {BENCH: (138364, 91102), SHIPPED: (138364, 89774)},
    'the information line held: nothing sent, a yield until the button rises':
        {BENCH: (85152, 48748), SHIPPED: (85152, 49288)},
    'a window that is not the top one, held: WM_TOPPED, then the button waited up':
        {BENCH: (38612, 31388), SHIPPED: (38612, 30306)},
    'no message, the button down: two yields until it rises':
        {BENCH: (34674, 31840), SHIPPED: (34674, 32202)},
    "AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise":
        {BENCH: (63868, 56032), SHIPPED: (63868, 55070)},
    'on View; an item reached, then clicked: MN_SELECTED to process 0':
        {BENCH: (1132286, 1058738), SHIPPED: (1132286, 1046392)},
    "on Desk; the accessory's entry reached, then clicked: AC_OPEN to the accessory":
        {BENCH: (861836, 787282), SHIPPED: (861836, 776372)},
    'on View; the menu left, a click off it: nothing chosen, nothing sent':
        {BENCH: (1107912, 1040730), SHIPPED: (1107912, 1029640)},
    "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds":
        {BENCH: (600452, 531308), SHIPPED: (600452, 521696)},
}
PRICED = {
    "the top window's up arrow clicked: found, the arrow sent, one yield":
        Priced((47346, 99700), (39232, 84954), 3, (0, 0, 0)),   # 0.47 / 0.46
    'the closer held; released inside it: WM_CLOSED':
        Priced((75072, 141812), (47166, 97586), 2, (0, 0, 0)),   # 0.53 / 0.48
    'the fuller held; the mouse taken off it, then released: nothing sent':
        Priced((86522, 155472), (45428, 94522), 2, (0, 0, 0)),   # 0.56 / 0.48
    'the title held; dragged, then released: WM_MOVED':
        Priced((111718, 185074), (62592, 109410), 5, (0, 0, 0)),   # 0.60 / 0.57
    'the sizer held; stretched, then released: WM_SIZED':
        Priced((132602, 209494), (83420, 133770), 5, (0, 0, 0)),   # 0.63 / 0.62
    'the sizer held; shrunk past the smallest size, both bars: seven boxes each way':
        Priced((178998, 263204), (136376, 198962), 7, (0, 0, 0)),   # 0.68 / 0.69
    'the sizer held; shrunk, a vertical bar alone: a cell wide, seven boxes high':
        Priced((171746, 245950), (129312, 182380), 7, (0, 0, 0)),   # 0.70 / 0.71
    'the sizer held; shrunk, a horizontal bar alone: seven boxes wide, a cell high':
        Priced((171784, 245906), (129350, 182336), 7, (0, 0, 0)),   # 0.70 / 0.71
    'the vertical elevator held; dragged up, then released: WM_VSLID':
        Priced((116210, 194874), (67052, 119186), 5, (0, 0, 0)),   # 0.60 / 0.56
    'the horizontal elevator held; dragged right, then released: WM_HSLID':
        Priced((115010, 192542), (65828, 116818), 5, (0, 0, 0)),   # 0.60 / 0.56
    'the up arrow clicked: the lock let go, the arrow sent, one yield, the lock taken again':
        Priced((44560, 94660), (36446, 79914), 3, (0, 0, 0)),   # 0.47 / 0.46
    'the track right of the horizontal elevator clicked: the page after':
        Priced((44064, 95396), (35950, 80650), 3, (0, 0, 0)),   # 0.46 / 0.45
    'the up arrow held: sent, read by its owner, sent again; released':
        Priced((51882, 103888), (43502, 88744), 4, (1, 14190, 7428)),   # 0.50 / 0.49
    'the information line held: nothing sent, a yield until the button rises':
        Priced((33480, 71628), (33214, 71230), 1, (0, 0, 0)),   # 0.47 / 0.47
    'a window that is not the top one, held: WM_TOPPED, then the button waited up':
        Priced((15914, 25088), (8094, 11322), 2, (0, 0, 0)),   # 0.63 / 0.71
    'no message, the button down: two yields until it rises':
        Priced((11088, 14388), (10822, 13990), 1, (0, 0, 0)),   # 0.77 / 0.77
    "AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise":
        Priced((19450, 29392), (11630, 15626), 2, (1, 14190, 7428)),   # 0.66 / 0.74
    'on View; an item reached, then clicked: MN_SELECTED to process 0':
        Priced((166286, 263904), (111606, 182790), 4, (0, 0, 0)),   # 0.63 / 0.61
    "on Desk; the accessory's entry reached, then clicked: AC_OPEN to the accessory":
        Priced((152086, 248130), (97364, 165608), 4, (0, 0, 0)),   # 0.61 / 0.59
    'on View; the menu left, a click off it: nothing chosen, nothing sent':
        Priced((155292, 244584), (102076, 167080), 3, (0, 0, 0)),   # 0.63 / 0.61
    "on Desk, the desk alone; its own item clicked: MN_SELECTED, no accessory's whatever gl_dafirst holds":
        Priced((133436, 221188), (78968, 140250), 4, (0, 0, 0)),   # 0.60 / 0.56
}
# @PINS-END
WINDOWS = {label: priced.windows for label, priced in PRICED.items() if priced.windows != NO_WINDOW}
# ...and as `test_tier3`'s census of the door users that switch reads them, by the registry's name.
DOOR_USERS_PRICED = {switching.row_name(ROWS[label]): tuple(PRICED[label]) for label in PRICED}
DOOR_USERS_WHOLE_RUN = {switching.row_name(ROWS[label]): WHOLE_RUN[label] for label in WHOLE_RUN}


def premise(label):
    """`label`'s `aes_switching.Premise`, the processes read off its machine by their names."""
    at_idles, idles, entered, at_polls = PREMISES[label]
    key = SWITCHING[KEY_OF[label]].arrival.machine
    return Premise(at_idles, idles, gc.SCREEN_MANAGER, tuple(gc.pd_of(key, who) for who in entered), None, at_polls)


# ---- the machines and the arrivals ---------------------------------------------------------------------------------------------
def test_the_machines_are_what_the_cases_say():
    """Two windows of every gadget, the second accessory's on top and each its own accessory's; one window of each
    narrower kind; the first accessory's entry in the desk menu; and the desk alone has no window but its own."""
    top, other = gc.top_window(A), gc.other_window(A)
    assert {top.owner, other.owner} == {gc.pid_of(A, FIRST), gc.pid_of(A, SECOND)}
    assert all(kind_of(A, each.handle) == gc.EVERY_GADGET for each in (top, other))
    kinds = {NO_MOVER: gc.NEVER_MOVED, NO_SIZER: gc.NEVER_SIZED, TALL: gc.SIZED_WITH_A_VERTICAL_BAR,
             WIDE: gc.SIZED_WITH_A_HORIZONTAL_BAR}
    for key, kind in kinds.items():
        assert (gc.top_window(key).owner, kind_of(key, gc.top_window(key).handle)) == (gc.pid_of(key, FIRST), kind)
    for key in (A, HIDING):
        ram = gc.machine(key).ram
        assert case.word_in(ram, aes.AES_GL_DACNT) == 1 and case.word_in(ram, aes.AES_DESK_PID) == gc.pid_of(key, FIRST)
    assert aes.signed(case.word_in(gc.machine(THE_DESK).ram, aes.AES_GL_WTOP)) < 0 or gc.top_window(THE_DESK).handle == 0


def kind_of(key, handle):
    return case.word_in(gc.machine(key).ram, aes.AES_WINDOWS + handle * aes.WIN_BYTES + aes.WIN_KIND)


def test_the_harness_s_free_window_is_empty_in_the_snapshot_too():
    """A machine's pokes leave the harness's own window out (`aes_gemctrl._as_pokes`), so the base image shows
    through there: it must hold what the machine holds — nothing — below the run's stack band."""
    assert not any(BASE_IMAGE[gc.FREE_FROM:case.STACK_BAND[0]])


@pytest.mark.parametrize("key", [*RETURNING, *SWITCHING, *UNPRICED], ids=_id)
def test_an_arrival_is_the_rom_s_own_call_of_the_handler_in_the_screen_manager_s_process(key):
    """THE ARRIVAL: the ROM's dispatcher run from a booted machine's idle — or the boot itself — reached the
    handler's entry with the screen manager RUNNING: at the ready list's head, out of the dispatcher, the screen's
    lock its own (ctlmgr takes it before it calls a handler)."""
    each = {**RETURNING, **SWITCHING, **UNPRICED}[key]
    arrived = gc.at(each.arrival)
    image = make_image(arrived.pokes)
    assert arrived.name == key[0] and len(arrived.arguments) == gc.FRAMES[key[0]].size // aes.WORD_BYTES
    assert aes.list_of(image, aes.AES_RLR)[0] == gc.SCREEN_MANAGER and image[aes.AES_INDISP] == 0
    import test_aes_wm_update as wm_update
    assert wm_update.spb_of(image)[1] == gc.SCREEN_MANAGER, "ctlmgr holds the screen's lock where it calls a handler"


# ---- a handler that returns ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("key", RETURNING, ids=_id)
def test_a_handler_that_returns_is_the_rom_s_at_its_arrival(key):
    each = RETURNING[key]
    result = run(key)
    written = last_written_to(aes_event.HANDED)
    vet_the_message(key, each, make_image(gc.at(each.arrival).pokes), result.final, written)
    assert (written is None) == (the_message(each) is None), f"{_id(key)}: a message is written exactly where one is built"


COUNTED_OFF = {      # gl_mnclicks where each arrival is made, and where hctl_button leaves it
    "a click the menu bar posted for itself (the boot's own): counted off": (1, 0),
    "the hidden bar's two clicks, counted twice and posted once: counted down to one": (2, 1),
    "a real click on a window's closer after them: the count still one, the click swallowed": (1, 0),
}


@pytest.mark.parametrize("label", COUNTED_OFF)
def test_a_click_the_bar_counted_is_counted_off_one_at_a_time_and_nothing_else_is_done(label):
    """hctl_button's first arm: gl_mnclicks ONE lower — from 2 as from 1 — and not a byte beside it (the
    differential holds the rest). A ROM BEHAVIOUR in the three: the accessory's two menu_bar calls count two clicks
    and the screen manager, woken once, takes ONE; the count stays 1, and the next REAL click — on a window's closer
    here — is swallowed in its place: the closer is not worked."""
    key = (HCTL_BUTTON, label)
    found, left = COUNTED_OFF[label]
    arrived = gc.at(RETURNING[key].arrival)
    assert case.word_in(make_image(arrived.pokes), aes.AES_GL_MNCLICKS) == found
    assert run(key).word(aes.AES_GL_MNCLICKS) == left


def test_the_swallowed_click_was_a_real_one_on_the_top_window_s_closer():
    arrived = gc.at(RETURNING[HCTL_BUTTON, "a real click on a window's closer after them: the count still one, the click swallowed"].arrival)
    assert arrived.arguments == gc.gadget(HIDING, "the closer")


# ---- ROM BEHAVIOURS, pinned on the ROM ---------------------------------------------------------------------------------------
STALE_WORDS = (0x1234, 0x5678, 0x7abc, 0x0def)
# hctl_window's x, y, w and h in the frame of a run entered at the stack band's top: `link a6,#-36` leaves A6 one
# longword under the return address, and the four words lie at -18, -20, -22 and -24(a6).
ENTRY_A6 = emu.STACK_TOP - aes.LONG_BYTES
STALE_FRAME_AT = ENTRY_A6 - 24


def _topped_at(chain, which=0):
    """ct_msgup's arguments at the arrival of `chain` (its `which`-th) that tells the other window's owner."""
    kind, owner, handle, *words = gc.at(Arrival(A, chain, CT_MSGUP, which)).arguments
    assert (kind, owner, handle) == (MESSAGES["WM_TOPPED"], gc.other_window(A).owner, gc.other_window(A).handle)
    return tuple(words)


def test_wm_topped_carries_four_words_of_the_rom_s_stack():
    """THE DECLARED DIVERGENCE, MEASURED (`aes/gemctrl.h`'s HCTL_STALE_WORD). (1) THE ROM SENDS WHAT ITS FRAME HOLDS:
    with four words staged where hctl_window's x, y, w and h lie, its own run sends them (h lowest in the frame, x
    highest). (2) AT THE REAL ARRIVAL THEY ARE NOT ARBITRARY: the words ct_msgup is handed are THE SAME at four
    different arrivals on one machine — another point of the window, and after a click on the top window's
    information line or on its title, whose own handler runs first — the residue ctlmgr's preceding wait leaves
    at that depth of the screen manager's stack; never the C's four zeroes. Held as that property, not as numbers:
    two of the four are halves of addresses a capture or a layout may move."""
    arrived = gc.at(RETURNING[HCTL_WINDOW, "a window that is not the top one: WM_TOPPED"].arrival)
    staged = aes.staged(arrived.name, arrived.arguments, case.merge_pokes(
        arrived.pokes, {STALE_FRAME_AT: struct.pack(">4H", *reversed(STALE_WORDS))}))
    final, _writes, _regs = aes_event._rom_run(make_image(staged), addrs.AES_ROM_HCTL_WINDOW)
    assert message_of(final)[aes.AP_MSG_WORDS // 2 + 1:] == STALE_WORDS
    elsewhere = (THE_OTHER_WINDOW_S_TITLE[0] + 20, THE_OTHER_WINDOW_S_TITLE[1] + 30)
    after = {name: {0: (onto(gc.gadget(A, name)),), 1: (click,), 2: (onto(THE_OTHER_WINDOW_S_TITLE),), 3: (click,)}
             for name in ("the information line", "the title")}
    carried = {"its title": _topped_at({**ON_THE_OTHER_WINDOW, 1: (click,)}),
               "another point of it": _topped_at({0: (onto(elsewhere),), 1: (click,)}),
               **{f"after {name} clicked": _topped_at(chain, 1) for name, chain in after.items()}}
    assert len(set(carried.values())) == 1, f"the residue differs between arrivals: {carried}"
    assert carried["its title"] != (gc.GEMCTRL["HCTL_STALE_WORD"],) * 4, "the real stack held the C's four zeroes"


def test_with_no_menu_bar_ctlmgr_calls_hctl_rect_again_and_again():
    """THE ROM'S ctlmgr SPINS: the bar hidden, a click on its place and a move along it — the handler returns at
    once and is called again with nothing delivered in between: the same chain arrives a second, a third, a sixth
    time (the first of them at the click's own point, every later one where the mouse is)."""
    arrivals = [gc.at(Arrival(HIDING, ALONG_THE_HIDDEN_BAR, HCTL_RECT, which)) for which in (1, 2, 3, 6)]
    assert len({each.arguments for each in arrivals[1:]}) == 1 and arrivals[0].arguments != arrivals[1].arguments
    assert all(case.long_in(make_image(each.pokes), aes.AES_GL_MNTREE) == 0 for each in arrivals)


def test_a_sizer_held_below_the_smallest_size_never_sleeps():
    """THE SPIN: with the corner dragged past the smallest size and the button still down, every wait of the rubber
    band returns at once — the ROM's run makes door call after door call and no second idle; the rise delivered at
    the only idle there is (the move's) leaves the run where it was: it does not return."""
    each = SWITCHING[HCTL_WINDOW, "the sizer held; shrunk past the smallest size, both bars: seven boxes each way"]
    spinning = row((HCTL_WINDOW, "the sizer held; shrunk past the smallest size, both bars: seven boxes each way"))
    held = at_its_first_switch(spinning)
    assert not held.returned
    the_rom_s = switching.scheduled(spinning, switching._staged(spinning))
    waits = [call for call in the_rom_s.calls if call.routine == addrs.AES_ROM_EV_MULTI]
    assert (the_rom_s.idles, len(waits)) == (1, max(each.at_calls)), "one wait blocks; the rest return at once"


# ---- a handler that switches ----------------------------------------------------------------------------------------------------
def test_every_row_is_registered_and_pinned():
    assert set(REGISTERED) <= set(aes_event.SWITCHING_ROWS)
    assert PREMISES.keys() == ROWS.keys() == WHOLE_RUN.keys() == PRICED.keys()


@pytest.mark.parametrize("label", ROWS)
def test_the_rom_s_own_run_of_a_row_is_what_its_name_says(label):
    """THE PREMISE (`aes_switching.vet_the_premise`): the ROM's run through its own dispatcher returns in the screen
    manager, each delivery taken at the idle or the poll the row names, the dispatcher entering exactly the
    processes the premise names — and the message it leaves is the case's, written to the process it names."""
    key = KEY_OF[label]
    the_rom_s = switching.vet_the_premise(ROWS[label], premise(label))
    vet_the_message(key, SWITCHING[key], the_rom_s.started, the_rom_s.memory, last_written_to(the_rom_s.calls))


@pytest.mark.parametrize("key", [*SWITCHING, *UNPRICED], ids=_id)
def test_a_handler_that_switches_is_the_rom_s_at_the_dispatcher_and_through_the_host_s_scheduler(key):
    """BOTH HALVES. AT THE DISPATCHER: with nothing delivered at an idle the handler reaches its first switch as the
    ROM does. THROUGH THE HOST'S SCHEDULER, the door bound (`aes_switching.companion`): the ROM's door calls, each
    handed the ROM's frame; the ROM's image at every dispatch and where the call returns; the case's message.

    A handler that first BLOCKS does so inside a wait of the event layer — a door call — and is held there byte for
    byte (`aes_event.blocked_then_woken`'s first half). One that first YIELDS does so by ITS OWN dsptch, after door
    calls of its own (the lock let go, the message written): no road stops a door user's child at a dispatcher it
    reaches outside a door call, so its first switch is held by the companion's own compare of the image at every
    dispatch — a page named, not a byte — and the premise, that the ROM's run yields there, on the ROM."""
    each = {**SWITCHING, **UNPRICED}[key]
    made = row(key)
    if each.switches == BLOCKS:
        # (The first half takes NO delivery: a rise named at a later door call belongs to the run past the block.)
        held = at_its_first_switch(made)
        assert not held.returned
        ran = switching.companion(made, THE_STALE_COUNT if key in THE_STALE_COUNT_IS_OVERWRITTEN else ())
    else:
        assert aes_event.rom_at_dsptch(made.name, made.arguments, made.machine()).switches == YIELDS
        ran = switching.companion(made)
    vet_the_message(key, each, make_image(ran.staged), ran.image, last_written_to(ran.calls))


# ON BOTH BLOBS, AND IN THE TABLE: every row above is a door user's that switches, so `test_tier3.py` holds each — by
# its registered name, off the two tables below — to the second differential of the real switch on each blob
# (`aes_switching.vet_on_a_blob`: the handler parked by OUR dispatcher on the screen manager's stack and woken through
# it, GCC's frames of the handler and of every core under it across savestate and switchto, an accessory's turn
# inside the run the ROM's own code on both shores, to the cycle) and to the table's price on both counts
# (`vet_the_table_s_price`). Not run a second time here: sixty bench runs.
def test_every_row_is_pinned_for_the_blobs_and_the_table():
    assert DOOR_USERS_PRICED.keys() == DOOR_USERS_WHOLE_RUN.keys() == REGISTERED.keys()
    assert all(blobs.keys() == {BENCH, SHIPPED} for blobs in DOOR_USERS_WHOLE_RUN.values())
    assert set(WINDOWS) == {"the up arrow held: sent, read by its owner, sent again; released",
                            "AC_OPEN, the button still down: sent, the accessory's turn inside the wait for the rise"}, (
        "two rows have another process's turn in them: the accessory reading what it was sent")


# ---- the harness this battery added to ---------------------------------------------------------------------------------------
def test_a_button_delivered_while_the_handler_yields_is_posted_by_the_dispatcher_and_is_no_door_call_of_the_row(monkeypatch):
    """THE DISPATCHER'S OWN DOOR CALLS ARE NOT THE CALLER'S (`aes_switch._Idling`): the rise delivered at a poll,
    while ct_msgup yields by its own dsptch, is posted by the DISPATCHER's forker — bchange's post_button — and the
    row's run makes no door call at all. RED: the watch left armed inside the caller's dispatch counts that
    post_button as the run's own, which the C's forker (it calls the entry's core) hands to no door."""
    made = row((CT_MSGUP, "no message, the button down: two yields until it rises"))
    staged = switching._staged(made)
    assert switching.scheduled(made, staged).calls == ()
    monkeypatch.setattr(aes_switch._Idling, "KEEPS_THE_DISPATCHER_S_CALLS_OUT", False)
    assert [call.routine for call in switching.scheduled(made, staged).calls] == [addrs.AES_ROM_POST_BUTTON]


@pytest.mark.parametrize("key", sorted(THE_MOUSE_SHOWN_AGAIN_LAST), ids=_id)
def test_a_row_that_names_the_stale_count_needs_it_and_holds_the_c_s_value_there(key):
    """A ROW'S OWN BY NATURE (`SwitchingRow.also_dropped`), held where it is declared — on each of the four rows whose
    run makes no VDI call after the menu (three priced, one at Tier 1 only): contrl[3] is, on the ROM, a word of
    its stack no C can know, and in the C's image CT_MOUSE_STALE_COUNT; and THE DROP IS NEEDED — without it the
    row's companion is red in exactly that word."""
    made = row(key)
    assert made.also_dropped == THE_STALE_COUNT
    ran = switching.companion(made)
    the_rom_s = switching.scheduled(made, switching.settled(made).pokes)
    assert case.word_in(ran.image, aes.AES_GSX_N_INTIN) == ct_mouse.CT_MOUSE_STALE_COUNT
    assert case.word_in(the_rom_s.memory, aes.AES_GSX_N_INTIN) != ct_mouse.CT_MOUSE_STALE_COUNT
    with pytest.raises(AssertionError, match=f"{aes.AES_GSX_N_INTIN:#x}|c000"):
        switching.companion(made._replace(also_dropped=()))


def test_no_other_row_names_a_drop_of_its_own():
    assert {key for key in (*SWITCHING, *UNPRICED) if row(key).also_dropped} == THE_MOUSE_SHOWN_AGAIN_LAST


def test_a_leave_out_at_the_stops_a_row_passes_without_is_refused():
    """`companion(at_stops_only=)` IS REFUSED WHERE IT IS NOT NEEDED (RED): the one case that needs it is red without
    it (a page at a dispatch), and a row whose companion passes with nothing left out is refused the leave-out."""
    needs, = THE_STALE_COUNT_IS_OVERWRITTEN
    with pytest.raises(AssertionError, match="the image the C holds at the dispatcher is not the ROM's"):
        switching.companion(row(needs))
    with pytest.raises(AssertionError, match="passes without leaving any out"):
        switching.companion(row((HCTL_WINDOW, "the closer held; released inside it: WM_CLOSED")), THE_STALE_COUNT)


# ---- the three refusals of the machinery, each shown ---------------------------------------------------------------------------
def test_a_boot_that_never_arrives_where_it_is_told_to_stop_is_refused():
    """`aes_boot.booted(until=)`: the desk's boot calls hctl_rect nowhere before its first idle."""
    import aes_boot
    with pytest.raises(aes_boot.Refused, match="reached its first idle and never arrived"):
        aes_boot.booted.derive(aes_boot.preinit(), aes_boot.blank_disk(), until=addrs.AES_ROM_HCTL_RECT)


def test_a_chain_that_idles_before_its_arrival_is_refused():
    """The mouse moved off every window and menu wakes nobody: the dispatcher idles again, nothing left to deliver."""
    with pytest.raises(AssertionError, match="the chain does not arrive there"):
        gc._arrived_through.derive(gc.machine(A).pokes, {0: (onto(gc.OFF_EVERY_MENU),)}, {}, HCTL_BUTTON, 0)


def test_an_arrival_made_with_a_delivery_still_due_is_refused():
    """A rise named at a third idle the ROM's ctlmgr calls the handler before: it is the handler's own run's."""
    chain = {**_top_arrival("the closer", PRESS).chain, 2: (RELEASE,)}
    with pytest.raises(AssertionError, match="belong to the handler's own run"):
        gc._arrived_through.derive(gc.machine(A).pokes, chain, {}, HCTL_WINDOW, 0)


def test_every_machine_s_pokes_are_its_boot_s_own_ram_and_nothing_else():
    """NOTHING IS POKED INTO A MACHINE: its pokes are one run, the megabyte the ROM's boot left — the very object."""
    for key in gc.MACHINES:
        booted = gc.machine(key)
        assert list(booted.pokes) == [0] and booted.pokes[0] is booted.boot.ram and len(booted.boot.ram) == gc.RAM_BYTES


# ==== THE SCREEN MANAGER'S PROCESS ITSELF: ictlmgr AND ctlmgr (`src/aes/ctlmgr.c`; band 5 wave 2, PENDING) =================
# PENDING: the twins are built and held here, and BOUND NOWHERE — every machine's screen manager is still the ROM's
# ctlmgr (psetup's frame names $fe49d2), every row above is the ROM's ctlmgr calling a handler. What is held:
#   ictlmgr   at its own arrival in the ROM's boot, Tier 1 (the two code longwords the ROM's own address: the host's);
#   ctlmgr    ONCE: its first entry in the ROM's boot, run to the loop's top; A TURN: `aes_gemctrl`'s (both shores from
#             one arrival at the loop's top to the next), a case per kind of wake;
#   the entry on both blobs: its frame, and the order of the once-only part's two stores.
# The turns on a blob need a machine whose screen manager is OURS (the takeover, `aes_boot`): the flip's (slice D).
import aes_boot                                                             # noqa: E402
import aes_pdpipe as pp                                                     # noqa: E402
import isr                                                                  # noqa: E402
import transcription                                                        # noqa: E402
from aes_gemctrl import Turn                                                # noqa: E402

CAPTURES = {"the desk's boot": False, "the accessories' boot": True}
BUS = aes_boot.BUS
PSETUP_FRAME_BYTES = pp.PDPIPE["PSETUP_FRAME_BYTES"]
EVINPUT = aes.header_constants("evinput.h")
CTWAIT_LEAVE = EVINPUT["AES_GL_CTWAIT_LEAVE"]
USABLE_STACK_BYTES = 1196               # the screen manager's: its UDA less the saved state (ruling W2-R3's number)
SUPERVISOR_AT_MASK_3 = 0x2300           # the SR psetup's frame holds, as the boot's one HBL left the mask


def _capture(accessories):
    return ((aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(gc.QUIET, gc.QUIET)) if accessories
            else (aes_boot.preinit(), aes_boot.blank_disk()))


# ---- ictlmgr -----------------------------------------------------------------------------------------------------------------
STALE_ENTRIES = {aes.AES_GL_DACNT: struct.pack(">h", 2), aes.AES_GL_DAFIRST: struct.pack(">h", 9)}
GSX = aes.header_constants("gsx.h")
# ...and WHAT ictlmgr MUST NOT WRITE, staged NONZERO (an argument class: the boot holds each zero at the arrival, where
# a clear too many shows nowhere) — the words its neighbour in the source writes or steps (ctlmgr's: the leave word,
# the active rectangle, the multi-click count) and the menu's own beside the two it clears.
NOT_ICTLMGR_S = {EVINPUT_LEAVE: struct.pack(">h", 1) for EVINPUT_LEAVE in (aes.header_constants("evinput.h")["AES_GL_CTWAIT_LEAVE"],)}
NOT_ICTLMGR_S.update({aes.AES_GL_RMNACTV: bytes([0x5a]) * aes.GRECT_BYTES, aes.header_constants("evasync.h")["AES_GL_BPEND"]: struct.pack(">h", 3),
                      aes.AES_GL_MNCLICKS: struct.pack(">h", 2), aes.AES_GL_DABOX: struct.pack(">h", 7)})
ICTLMGR_STAGINGS = {
    "as the boot holds them": {},
    "ARGUMENT CLASS: the two counts staged stale": STALE_ENTRIES,
    "ARGUMENT CLASS: the words it must not write staged nonzero": NOT_ICTLMGR_S,
}
ICTLMGR_STEERS = (pp.STEERS_THE_PD_COUNT, pp.STEERS_THE_STACK)      # pstart's own (getpd counts a PD out; psetup's push)


@functools.cache
def _ictlmgr_arrived(accessories):
    """THE BOOT STOPPED AT ITS CALL OF ictlmgr (gem_main's, $fda1dc): the word it pushed — the running process's id,
    which ictlmgr never reads — and the machine there."""
    boot = aes_boot.booted(*_capture(accessories), until=addrs.AES_ROM_ICTLMGR)
    assert boot.registers["pc"] == addrs.AES_ROM_ICTLMGR and boot.registers["sr"] & aes_boot.SR_SUPERVISOR
    at = boot.registers["isp"] + aes.LONG_BYTES
    return struct.unpack(">h", boot.ram[at:at + aes.WORD_BYTES]), gc._as_pokes(boot.ram, "ictlmgr's arrival")


@pytest.mark.parametrize("accessories", CAPTURES.values(), ids=CAPTURES)
@pytest.mark.parametrize("staging", ICTLMGR_STAGINGS)
def test_ictlmgr_at_its_own_arrival_in_the_boot_is_the_rom_s(accessories, staging):
    """THE ROM'S BOOT'S OWN CALL: no accessory entry counted, and the screen manager's process made — PD1, named
    SCRENMGR, ready and woken, its first frame (psetup's) and its load address BOTH ctlmgr's own address, which is
    the ROM's on the host; the PD answered. The two counts are zero where the boot calls it (cleared RAM), so the
    stores are held over them STAGED STALE too (an argument class: no machine reaches ictlmgr twice) — and WHAT IT
    DOES NOT WRITE over words staged nonzero where a clear too many would otherwise leave the zero it found."""
    arguments, pokes = _ictlmgr_arrived(accessories)
    staged = case.merge_pokes(pokes, ICTLMGR_STAGINGS[staging])
    result = pp.run(gc.ICTLMGR, arguments, staged, steered=ICTLMGR_STEERS)
    final = result.final
    assert result.long_answer() == gc.SCREEN_MANAGER
    assert (case.word_in(final, aes.AES_GL_DACNT), case.word_in(final, aes.AES_GL_DAFIRST)) == (0, 0)
    assert [case.long_in(final, slot) for slot in aes_event.SCREEN_MANAGER_ENTRY_SLOTS] == [addrs.AES_ROM_CTLMGR] * 2
    assert bytes(final[gc.SCREEN_MANAGER + aes.PD_NAME:][:8]) == b"SCRENMGR"
    assert aes.list_of(final, aes.AES_DRL)[0] == gc.SCREEN_MANAGER


def test_the_name_ictlmgr_hands_is_the_rom_s_own_string():
    name_at = gc.GEMCTRL["AES_SCRENMGR_NAME"]
    assert bytes(BASE_IMAGE[name_at:name_at + 13]) == b"SCRENMGR.LOC\0"


# ---- ctlmgr, ONCE -----------------------------------------------------------------------------------------------------------
LEAVE_WORD_STALE = {CTWAIT_LEAVE: struct.pack(">h", 1)}
RMNACTV = slice(aes.AES_GL_RMNACTV, aes.AES_GL_RMNACTV + aes.GRECT_BYTES)
RMENU = slice(aes.AES_GL_RMENU, aes.AES_GL_RMENU + aes.GRECT_BYTES)


@pytest.mark.parametrize("accessories", CAPTURES.values(), ids=CAPTURES)
def test_the_screen_manager_s_first_entry_is_what_the_entry_s_contract_says(accessories):
    """WHERE switchto's `rte` ENTERS ctlmgr, in the ROM's own boot: supervisor state, the mask at 3, the stack EMPTY —
    A7 the top psetup's frame was laid under, that frame just below it (its SR word, ctlmgr's address) — every
    usable byte of the stack zero, A6 zero, the screen manager running. What `aes_rom_ctlmgr` is entered with."""
    boot = gc.the_first_entry(accessories)
    registers, ram = boot.registers, boot.ram
    lo, top, _why = gc.its_stack(ram)
    assert (registers["sr"] & ~aes.BYTE_MASK, registers["isp"], registers["a6"]) == (SUPERVISOR_AT_MASK_3, top, 0)
    assert struct.unpack(">HI", ram[top - PSETUP_FRAME_BYTES:top]) == (registers["sr"], addrs.AES_ROM_CTLMGR)
    assert not any(ram[lo:top - PSETUP_FRAME_BYTES]) and top - lo == USABLE_STACK_BYTES
    assert case.long_in(ram, aes.AES_RLR) & BUS == gc.SCREEN_MANAGER


@pytest.mark.parametrize("accessories", CAPTURES.values(), ids=CAPTURES)
def test_ctlmgr_s_once_only_part_is_the_rom_s_at_the_screen_manager_s_first_entry(accessories):
    """FROM THE FIRST ENTRY TO THE LOOP'S TOP: the menu bar's rectangle copied into the active one — which the boot
    holds EMPTY there — and the leave word cleared; held over that word STAGED STALE (an argument class: nothing
    else ever writes it), and not a byte beside them, the Line-F mask word aside where the ROM's run stored it."""
    pokes = case.merge_pokes(gc._as_pokes(gc.the_first_entry(accessories).ram, "the first entry"), LEAVE_WORD_STALE)
    started = make_image(pokes)
    assert any(started[RMENU]) and bytes(started[RMNACTV]) != bytes(started[RMENU])
    the_rom_s, writes = gc.the_rom_begins(pokes)
    returncode, stderr, ours = gc.the_c_begins(pokes)
    assert returncode == 0, stderr
    left_out = frozenset(case.STACK_BAND) | (aes_event.LINE_F_MASK_BYTES & frozenset(writes))
    assert not aes_event.differing(ours, the_rom_s, left_out)
    assert bytes(ours[RMNACTV]) == bytes(started[RMENU]) and case.word_in(ours, CTWAIT_LEAVE) == 0


# ---- ctlmgr, A TURN ---------------------------------------------------------------------------------------------------------
# WHERE EVERY TURN STARTS: the screen manager back at its loop's top after a first turn of the ROM's own — a click on
# the bar past the titles (its own place: nobody's window, no menu title), which its hctl_button drops.
A_FIRST_TURN = {0: (onto(gc.ON_THE_BAR_PAST_THE_TITLES),), 1: (click,)}
VIEW = aes_event.THE_VIEW_TITLE_S_POINT
THE_MENU_WORKED = {1: aes_event.ONTO_ITS_PLAIN_ITEM, 2: click}        # ...from the title: an item reached, clicked
SELECTED = lambda: (MESSAGES["MN_SELECTED_MESSAGE"], 0, gc.THE_VIEW_TITLE, gc.VIEW_S_PLAIN_ITEM, 0, 0, 0)   # noqa: E731
A_KEY = 0x1e61                          # 'a': the scan code over the character, as nq is handed a key
# A turn's case: the turn, the message it sends last (`Case.message`'s shapes), the multi-click count (before, after).
TurnCase = namedtuple("TurnCase", "turn message bpend", defaults=(None, None))


def _on_a_gadget(name, *does, key=A):
    """A turn of `key`'s machine from the first turn's end: the mouse onto the top window's gadget `name`, then each
    of `does` at the idle after."""
    return Turn(key, A_FIRST_TURN, at_idle={0: onto(gc.gadget(key, name)), **{1 + nth: each for nth, each in enumerate(does)}})


def _staged_at(turn, count):
    return turn._replace(staged=gc.the_click_count_staged_at(count))


THE_CLOSER_CLICKED = _on_a_gadget("the closer", click)
# THE BUTTON AND THE BAR IN ONE WAKE: the mouse onto a title and a click there, in one idle — the wait comes back with
# both, and the button's handler (which finds the desktop under the mouse: nothing) runs before the bar's.
BOTH_IN_ONE_WAKE = Turn(A, A_FIRST_TURN, at_idle={0: (onto(VIEW), click), **THE_MENU_WORKED})
ON_THE_BAR = Turn(A, A_FIRST_TURN, at_idle={0: onto(VIEW), **THE_MENU_WORKED})
# (...with no menu: `ALONG_THE_HIDDEN_BAR`'s last two idles, taken by the turn itself — the mouse onto the bar's place,
# which wakes nobody, then a click there and a move along it.)
ONTO_THE_BAR_S_PLACE, CLICKED_AND_MOVED_ALONG = (ALONG_THE_HIDDEN_BAR[idle] for idle in sorted(ALONG_THE_HIDDEN_BAR)[-2:])
BOTH_WITH_NO_MENU = Turn(HIDING, THE_BAR_HIDDEN, 1, at_idle={0: ONTO_THE_BAR_S_PLACE, 1: CLICKED_AND_MOVED_ALONG})
THE_OTHER_WINDOW_CLICKED = Turn(A, A_FIRST_TURN, at_idle={0: onto(THE_OTHER_WINDOW_S_TITLE), 1: click})
# THE BAR HIDDEN AND THE MOUSE ON ITS PLACE (the HIDING machine, `ALONG_THE_HIDDEN_BAR`): the ROM's ctlmgr spins — its
# third and its sixth arrival at the loop's top start the same turn, which no idle interrupts.
SPINS = {which: Turn(HIDING, ALONG_THE_HIDDEN_BAR, which) for which in (2, 5)}
# THE COUNT THE ROM'S OWN (the TWO_WAITERS machine: two accessories in a two-click wait beside the desk's — 3 at its
# idle, 2 where the turn after its first starts): nothing staged.
W = gc.TWO_WAITERS
THE_CLOSER_CLICKED_AT_2 = _on_a_gadget("the closer", click, key=W)
TURNS = {
    "the top window's closer clicked: WM_CLOSED": TurnCase(THE_CLOSER_CLICKED, lambda: _about_the_top("WM_CLOSED"), (1, 1)),
    "two more processes in a two-click wait (the count the ROM's own, 2); the closer clicked: 1":
        TurnCase(THE_CLOSER_CLICKED_AT_2, lambda: _about_the_top("WM_CLOSED", key=W), (2, 1)),
    "two more processes in a two-click wait (the count 2); a button and the bar in one wake: 1, and no lower":
        TurnCase(BOTH_IN_ONE_WAKE._replace(machine=W), SELECTED, (2, 1)),
    "the closer held, then released inside it (a box watched): WM_CLOSED":
        TurnCase(_on_a_gadget("the closer", PRESS, RELEASE), lambda: _about_the_top("WM_CLOSED")),
    "the title held, dragged, released (a drag): WM_MOVED":
        TurnCase(_on_a_gadget("the title", PRESS, onto(A_DRAG_TO), RELEASE), lambda: _moved_to(A_DRAG_TO)),
    "the sizer held, stretched, released (a rubber band): WM_SIZED":
        TurnCase(_on_a_gadget("the sizer", PRESS, onto(A_SIZE_TO), RELEASE), lambda: _to_the_mouse(A_SIZE_TO)),
    "the vertical elevator held, dragged, released (a slider): WM_VSLID":
        TurnCase(_on_a_gadget("the vertical elevator", PRESS, onto(ELEVATOR_TO["the vertical elevator"]), RELEASE), "WM_VSLID"),
    "the up arrow clicked (an arrow: the lock let go for a yield and taken again): WM_ARROWED":
        TurnCase(_on_a_gadget("the up arrow", click), lambda: _arrowed("the up arrow")),
    "the mouse onto a title, an item chosen (the bar): MN_SELECTED": TurnCase(ON_THE_BAR, SELECTED, (1, 1)),
    "the desk alone; the mouse onto a title, an item chosen: MN_SELECTED":
        TurnCase(ON_THE_BAR._replace(machine=THE_DESK), SELECTED),
    "a button and the bar in one wake: the button's handler, then the menu": TurnCase(BOTH_IN_ONE_WAKE, SELECTED, (1, 1)),
    # THE MULTI-CLICK COUNT, stepped once a handler: never below one, and read as a SIGNED word.
    "ARGUMENT CLASS, the count at 0; a button: left at 0": TurnCase(_staged_at(THE_CLOSER_CLICKED, 0), None, (0, 0)),
    "ARGUMENT CLASS, the count at 2; a button: 1": TurnCase(_staged_at(THE_CLOSER_CLICKED, 2), None, (2, 1)),
    "ARGUMENT CLASS, the count at 3; a button: 2": TurnCase(_staged_at(THE_CLOSER_CLICKED, 3), None, (3, 2)),
    "ARGUMENT CLASS, the count at -1; a button: left (a signed compare)": TurnCase(_staged_at(THE_CLOSER_CLICKED, -1), None, (-1, -1)),
    "ARGUMENT CLASS, the count at 2; the bar alone: 1": TurnCase(_staged_at(ON_THE_BAR, 2), None, (2, 1)),
    "ARGUMENT CLASS, the count at 2; a button and the bar: 1, and no lower": TurnCase(_staged_at(BOTH_IN_ONE_WAKE, 2), None, (2, 1)),
    # ...and BOTH STEPS WHERE NOTHING ELSE COUNTS: the bar hidden, a click on its place and a move along it in one idle
    # (`ALONG_THE_HIDDEN_BAR`'s last idle, taken by the turn itself) — the button's handler counts the bar's own click
    # off, the bar's finds no menu, and the count goes down by two.
    **{f"ARGUMENT CLASS, the count at {before}; no menu bar, a button and the bar: {after}":
       TurnCase(_staged_at(BOTH_WITH_NO_MENU, before), None, (before, after)) for before, after in ((4, 2), (3, 1), (2, 1), (1, 1))},
    # (Under the menu the count is no witness: the menu's own waits count it down to 1 as they are removed —
    # evremove's step, $fe5150 — whatever ctlmgr's steps left. The image holds it all the same.)
    "ARGUMENT CLASS, the count at 4; a button and the bar: counted down by the menu's waits too": TurnCase(_staged_at(BOTH_IN_ONE_WAKE, 4), None, (4, 1)),
    **{f"no menu bar, the mouse on its place (arrival {which + 1}): hctl_rect called, nothing done, no sleep": TurnCase(turn)
       for which, turn in SPINS.items()},
}
# ...whose last VDI call is the menu's re-show of the mouse (THE_STALE_COUNT, above: contrl[3] the ROM's stack word) —
# named on each, and each held to NEED it (`held_to_the_rom_s_turn` refuses a window a turn passes without).
ENDS_ON_THE_RE_SHOW = frozenset(label for label, each in TURNS.items()
                                if each.turn._replace(machine=A, staged=None) in (ON_THE_BAR, BOTH_IN_ONE_WAKE))
# WHAT NO MACHINE HERE REACHES, AND NO TURN PINS (UNPINNED, by name): A MOUSE AT y >= 256. Every machine is the 320 x
# 200 screen the captures boot (`test_every_machine_is_the_low_resolution_screen`), so no turn tells a handler handed
# the answer's y whole from one handed its low byte (the reviewer's R22 / R23: `(uint8_t)` on hctl_button's or
# hctl_rect's y survive every test). It takes a 400-row machine — a monochrome pre-init capture, the captures' tool's
# to make — and one press on a gadget in its lower half. What holds the word meanwhile is each build's own text, read
# (`test_on_the_blobs_the_button_s_handler_runs_before_the_bar_s...`): the answer's two words moved whole, a word each.


def _turn(label):
    each = TURNS[label].turn
    return each._replace(also_dropped=THE_STALE_COUNT) if label in ENDS_ON_THE_RE_SHOW else each


class _Sent(namedtuple("_Sent", "message arrival")):
    """A turn's case as `vet_the_message` reads one."""


@pytest.mark.parametrize("label", TURNS)
def test_a_turn_of_ctlmgr_s_loop_is_the_rom_s_from_one_arrival_at_its_top_to_the_next(label):
    """ONE TURN, BOTH SHORES (`aes_gemctrl.held_to_the_rom_s_turn`): w_setactive, the main wait — the screen manager
    parked in it, its answer words the one frame it holds there — the lock, the handlers the wake asks for, the
    lock let go; every door call handed what the ROM's is, the whole image the ROM's where the turn ends. And what
    the case says of it: the message sent last, the multi-click count before and after."""
    each = TURNS[label]
    held = gc.held_to_the_rom_s_turn(label, _turn(label))
    started, ended = held.made.started, held.ran.image
    if each.message:
        vet_the_message((gc.CTLMGR_TURN, label), _Sent(each.message, Arrival(each.turn.machine, None, None)), started, ended,
                        last_written_to(held.made.reference.calls))
    if each.bpend:
        assert (aes.signed(case.word_in(started, gc.AES_GL_BPEND)), aes.signed(case.word_in(ended, gc.AES_GL_BPEND))) == each.bpend
    if held.made.reference.idles:
        assert held.ran.parked and "AES_CTLMGR_ANSWERS" in held.ran.slots_held, (
            f"the turn slept in its main wait holding {held.ran.slots_held}: the answers' slot is live across it")


def _routines_called(turn):
    return [call.routine for call in gc.turned(turn).reference.calls]


TAK_FLAG, UNSYNC, EV_MULTI, CT_CHGOWN = (addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_UNSYNC, addrs.AES_ROM_EV_MULTI,
                                         addrs.AES_ROM_CT_CHGOWN)


def test_the_lock_is_taken_after_the_wait_and_let_go_after_the_handlers():
    """THE ORDER, on the ROM's own turn (and the C's is held to hand the door the same calls in the same order):
    w_setactive's ct_chgown, THE WAIT, the lock — then whatever the handlers call — and the lock let go LAST. An
    arrow's handler lets it go and takes it again in between."""
    for turn in (_turn("the top window's closer clicked: WM_CLOSED"), _turn("the mouse onto a title, an item chosen (the bar): MN_SELECTED")):
        called = _routines_called(turn)
        assert called[:3] == [CT_CHGOWN, EV_MULTI, TAK_FLAG] and called[-1] == UNSYNC
        assert TAK_FLAG not in called[3:] and UNSYNC not in called[:-1]
    arrowed = _routines_called(_turn("the up arrow clicked (an arrow: the lock let go for a yield and taken again): WM_ARROWED"))
    assert [each for each in arrowed if each in (TAK_FLAG, UNSYNC)] == [TAK_FLAG, UNSYNC, TAK_FLAG, UNSYNC]


BUTTON_THEN_RECT = (HCTL_BUTTON, HCTL_RECT)


@pytest.mark.parametrize("label, called", {
    "the top window's closer clicked: WM_CLOSED": (HCTL_BUTTON,),
    "the mouse onto a title, an item chosen (the bar): MN_SELECTED": (HCTL_RECT,),
    "a button and the bar in one wake: the button's handler, then the menu": BUTTON_THEN_RECT,
    "ARGUMENT CLASS, the count at 4; no menu bar, a button and the bar: 2": BUTTON_THEN_RECT,
}.items())
def test_the_handlers_the_rom_s_ctlmgr_calls_in_a_turn_are_what_the_case_says(label, called):
    """THE PREMISE OF EACH KIND OF WAKE, read off the ROM's own turn at the handlers' entries: a button calls
    hctl_button, the bar hctl_rect — and ONE WAKE THAT BRINGS BOTH calls both IN ONE TURN, the button's first."""
    assert gc.turned(_turn(label)).handlers == called


def test_a_key_calls_no_handler_and_a_spin_calls_hctl_rect_every_turn():
    assert {gc.turned(_a_key_eaten(start)).handlers for start in KEY_STARTS} == {()}
    assert [gc.turned(turn).handlers for turn in SPINS.values()] == [(HCTL_RECT,)] * len(SPINS)


def test_with_no_menu_bar_a_turn_ends_at_once_and_the_next_is_the_same_turn_again():
    """THE SPIN, as the ROM does it and as the C's turn is held to it (above, both arrivals): no idle, no poll,
    nobody entered — the wait answers as it is made (the mouse is inside the rectangle it waits for it to enter),
    hctl_rect finds no menu, the lock is taken and let go — and the screen manager is at its loop's top again, to
    make the same four door calls: the sixth turn as the third."""
    for made in map(gc.turned, SPINS.values()):
        assert (made.reference.idles, made.reference.polls, made.reference.entered) == (0, 0, ())
        assert [call.routine for call in made.reference.calls] == [CT_CHGOWN, EV_MULTI, TAK_FLAG, UNSYNC]
        assert case.long_in(made.started, aes.AES_GL_MNTREE) == 0


# ---- a key is eaten ----------------------------------------------------------------------------------------------------------
# TWO STARTS. ON THE BAR PAST THE TITLES, the count at 1: where a handler or a step run on a key would do NOTHING (no
# window, no title under the mouse; a count of 1 is never stepped) — so that turn alone holds only the wait and the
# lock. ON THE TOP WINDOW'S CLOSER, THE COUNT AT 2 (the TWO_WAITERS machine after a first turn of the ROM's that
# clicked that closer — the count the ROM's own): there the button's handler would watch the box and send WM_CLOSED
# again, and a step on either bit would take the count to 1.
A_CLOSER_CLICKED_FIRST = {0: (onto(gc.gadget(W, "the closer")),), 1: (click,)}
KEY_STARTS = {
    "on the bar past the titles, the count at 1": THE_CLOSER_CLICKED._replace(at_idle=None),
    "on the top window's closer, the count at 2 (the ROM's own)": Turn(W, A_CLOSER_CLICKED_FIRST),
}


def _a_key_eaten(start="on the bar past the titles, the count at 1"):
    turn = KEY_STARTS[start]
    return turn._replace(staged=gc.a_key_in_its_own_queue(turn, A_KEY))


@pytest.mark.parametrize("start", KEY_STARTS)
def test_a_key_is_eaten_the_lock_taken_and_let_go_round_nothing(start):
    """THE MAIN WAIT ASKS FOR KEYS AND ctlmgr READS NONE: with a key in the screen manager's own queue (an ARGUMENT
    CLASS — the ROM's nq run over the turn's start, `aes_gemctrl.a_key_in_its_own_queue`) the wait answers at once,
    NO HANDLER RUNS AND THE COUNT IS NOT STEPPED — held where each would show (the mouse on a gadget, the count at
    2: on the ROM no handler is called, and the C's image is the ROM's: no box watched, no message, the count
    left) — the lock is taken and let go, and THE KEY IS GONE, on both shores."""
    turn = _a_key_eaten(start)
    held = gc.held_to_the_rom_s_turn(f"a key eaten, {start}", turn)
    made, reference = held.made, held.made.reference
    assert (reference.idles, [call.routine for call in reference.calls]) == (0, [CT_CHGOWN, EV_MULTI, TAK_FLAG, UNSYNC])
    assert made.handlers == ()
    queue = case.long_in(made.started, gc.SCREEN_MANAGER + aes.PD_CDA) + gc.FM["CDA_KEY_QUEUE"]
    count_at = queue + gc.FM["CQUEUE_COUNT"]
    assert (case.word_in(made.started, count_at), case.word_in(held.ran.image, count_at)) == (1, 0)
    assert message_of(held.ran.image) == message_of(made.started), "a key eaten sends nothing"
    assert case.word_in(held.ran.image, gc.AES_GL_BPEND) == case.word_in(made.started, gc.AES_GL_BPEND)


def test_the_key_turn_on_a_gadget_starts_where_a_handler_and_a_step_would_show():
    """THE PREMISE of the second start, on the ROM's own machine: the mouse is on the top window's closer (the first
    turn's own click was there: its WM_CLOSED is in the buffer), the count stands at 2 with nothing staged but the
    key — and with NO key the same start's next button there is handed to hctl_button."""
    turn = KEY_STARTS["on the top window's closer, the count at 2 (the ROM's own)"]
    started = gc.start_of(turn)
    assert case.word_in(started, gc.AES_GL_BPEND) == 2 and message_of(started)[0] == MESSAGES["WM_CLOSED"]
    assert (aes.signed(case.word_in(started, GSX["AES_XRAT"])), aes.signed(case.word_in(started, GSX["AES_YRAT"]))) == gc.gadget(W, "the closer")
    clicked = gc.turned(turn._replace(at_idle={0: click}))
    assert clicked.handlers == (HCTL_BUTTON,)


def test_every_machine_is_the_low_resolution_screen():
    """(What UNPINS a mouse at y >= 256, above: 200 rows on every machine a turn or an arrival is made over.)"""
    screens = {struct.unpack(">4h", gc.machine(key).ram[aes.AES_GL_RSCREEN:aes.AES_GL_RSCREEN + aes.GRECT_BYTES]) for key in gc.MACHINES}
    assert screens == {(0, 0, 320, 200)}


# ---- WM_TOPPED on the screen manager's own stack: the declared divergence, by name ----------------------------------------------
STALE_WORDS_AT = slice(aes.AES_CT_MESSAGE + aes.AP_MSG_WORDS + aes.WORD_BYTES, aes.AES_CT_MESSAGE + aes.AP_MSG_BYTES)
THE_STALE_WORDS_WHY = ("WM_TOPPED's words 4..7 (`aes/gemctrl.h`'s HCTL_STALE_WORD, ruling W2-R2): locals hctl_window never "
                       "set — on the screen manager's own stack the residue of ctlmgr's last wait, in the C four zeroes")


def _the_residue_s_places(made):
    """WHERE THE FOUR WORDS LIE after the ROM's turn: in the screen manager's message buffer, and wherever its write
    carried them — every run of the eight bytes the turn STORED, outside its own stack: `(lo, hi, why)` each."""
    started, left = made.started, made.reference.memory
    residue = bytes(left[STALE_WORDS_AT])
    lo, hi, _why = gc.its_stack(started)
    places, at = [], left.find(residue)
    while at >= 0:
        if not lo <= at < hi and started[at:at + len(residue)] != residue:
            places.append((at, at + len(residue), THE_STALE_WORDS_WHY))
        at = left.find(residue, at + 1)
    return residue, tuple(places)


def _with_zeroes_for_the_residue(residue):
    """The ROM's door calls as the C is expected to make them: the message ap_rdwr is handed with the four stale
    words the C's own (`HCTL_STALE_WORD`)."""
    ours = struct.pack(">4h", *[gc.GEMCTRL["HCTL_STALE_WORD"]] * 4)

    def handed_as(calls):
        return [call._replace(arguments=tuple(each[:-len(residue)] + ours if isinstance(each, bytes) and each.endswith(residue)
                                              else each for each in call.arguments))
                if call.routine == addrs.AES_ROM_AP_RDWR else call for call in calls]
    return handed_as


def test_wm_topped_on_the_screen_manager_s_own_stack_differs_in_its_four_stale_words_and_nowhere_else():
    """THE DECLARED DIVERGENCE WHERE IT IS REAL (ruling W2-R2). On the screen manager's OWN stack the ROM's
    hctl_window sends, as WM_TOPPED's words 4..7, what its frame holds there — VETTED AS WHAT THEY ARE: the high
    half of an address of the AES's own text, then the low half of an address inside the screen manager's stack —
    and the C sends four zeroes. The turn is held with exactly those eight bytes left out BY NAME, wherever the
    write carried them (the manager's buffer; the owner's pipe or the buffer it reads into), the message handed
    to ap_rdwr compared with the C's four words in their place — and IS RED WITHOUT (the compare below refuses a
    window the turn passes without)."""
    residue, places = _the_residue_s_places(gc.turned(THE_OTHER_WINDOW_CLICKED))
    text_half, stack_half, *_rest = struct.unpack(">4H", residue)
    lo, hi, _why = gc.its_stack(gc.turned(THE_OTHER_WINDOW_CLICKED).started)
    text_lo, text_hi = aes.AES_TEXT
    assert text_lo >> 16 <= text_half <= (text_hi - 1) >> 16 and lo <= stack_half < hi, f"the residue is {residue.hex()}"
    assert places and places[0][:2] == (STALE_WORDS_AT.start, STALE_WORDS_AT.stop) and len(places) <= 3
    held = gc.held_to_the_rom_s_turn("the other window clicked: WM_TOPPED", THE_OTHER_WINDOW_CLICKED._replace(also_dropped=places),
                                     _with_zeroes_for_the_residue(residue))
    assert all(not any(held.ran.image[at:end]) for at, end, _why in places), "the C's four words are HCTL_STALE_WORD"
    other = gc.other_window(A)
    assert message_of(held.ran.image)[:4] == (MESSAGES["WM_TOPPED"], gc.pid_of(A, SM), 0, other.handle)
    assert last_written_to(held.made.reference.calls) == other.owner


def test_the_stale_words_are_left_out_of_no_turn_that_passes_without_them():
    """...AND ONLY THERE: a turn that sends another message — the closer's WM_CLOSED, whose four words are the
    window's rectangle on both shores — is refused the same windows by name."""
    places = ((STALE_WORDS_AT.start, STALE_WORDS_AT.stop, THE_STALE_WORDS_WHY),)
    with pytest.raises(AssertionError, match="is held without leaving any out"):
        gc.held_to_the_rom_s_turn("the closer clicked", THE_CLOSER_CLICKED._replace(also_dropped=places))


# ---- the booted machine's own trap save: named where it is not the snapshot's, and DEAD -------------------------------------------
A_NOISE = bytes(range(0x61, 0x61 + addrs.TRAP_SAVE_FRAME_BYTES))


def test_a_booted_machine_s_savptr_is_the_save_area_s_top_whatever_phase_the_snapshot_was_captured_in():
    """THE FACT THE NAMING STANDS ON: every booted machine first idles with `savptr` at the save area's top (the
    ROM's boot sets it there and no trap is open at an idle), so its trap-save frame is the area's last — while the
    SNAPSHOT's lies there or one frame lower, by where its capture landed. `its_trap_save_beside_the_snapshot_s`
    names the machine's frame exactly where the two are not one, and nothing where they are."""
    for key in gc.MACHINES:
        ram = gc.machine(key).ram
        lo, hi, _why = gc.its_trap_save(ram)
        assert hi == aes_event.SAVE_AREA_TOP and hi - lo == addrs.TRAP_SAVE_FRAME_BYTES
        beside = gc.its_trap_save_beside_the_snapshot_s(ram)
        assert beside == (() if aes_event.SNAPSHOT_SAVPTR == aes_event.SAVE_AREA_TOP else ((lo, hi, gc.TRAP_SAVE_WHY),))


@pytest.mark.parametrize("label", ("the top window's closer clicked: WM_CLOSED",
                                   "the mouse onto a title, an item chosen (the bar): MN_SELECTED"))
def test_the_trap_save_frame_a_turn_leaves_out_is_dead_noise_in_it_changes_nothing(label):
    """THE FRAME IS DEAD WHERE A TURN STARTS (no trap is open at the loop's top): with every byte of it NOISE the
    ROM's own turn makes the same door calls, the same idles, calls the same handlers, STORES THE SAME BYTES THERE
    (the polls' traps overwrite what they use) and leaves the same machine everywhere else — and the C's turn is
    still the ROM's from that start."""
    turn = _turn(label)
    lo, hi, _why = gc.its_trap_save(gc.start_of(turn))
    noisy = turn._replace(staged=("NOISE in the dead trap-save frame", {lo: A_NOISE}))
    quiet, made = gc.turned(turn), gc.turned(noisy)
    assert made.started[lo:hi] == A_NOISE and quiet.started[lo:hi] != A_NOISE
    assert (made.reference.calls, made.reference.idles, made.handlers) == (quiet.reference.calls, quiet.reference.idles, quiet.handlers)
    assert made.reference.memory[:lo] + made.reference.memory[hi:] == quiet.reference.memory[:lo] + quiet.reference.memory[hi:]
    stored = [at for at in range(lo, hi) if made.reference.memory[at] != A_NOISE[at - lo]]
    assert stored and all(made.reference.memory[at] == quiet.reference.memory[at] for at in stored)
    gc.held_to_the_rom_s_turn(f"{label}, noise in the trap save", noisy)


# ---- the machinery's own refusals ---------------------------------------------------------------------------------------------
def test_a_turn_that_never_comes_back_to_the_loop_s_top_is_refused():
    """A key typed where the keyboard is the top window's owner's wakes no screen manager: the machine idles."""
    with pytest.raises(AssertionError, match="the turn does not end"):
        gc.turned(THE_CLOSER_CLICKED._replace(at_idle={0: aes_event.key(A_KEY >> 8)}))


def test_a_delivery_the_turn_never_takes_is_refused():
    with pytest.raises(AssertionError, match="nothing was delivered at the idles"):
        gc.turned(THE_CLOSER_CLICKED._replace(at_idle={**THE_CLOSER_CLICKED.at_idle, 5: RELEASE}))


def test_a_turn_starts_with_the_screen_manager_running_at_its_loop_s_top_its_lock_free():
    made = gc.turned(THE_CLOSER_CLICKED)
    import test_aes_wm_update as wm_update
    assert case.long_in(made.started, aes.AES_RLR) & BUS == gc.SCREEN_MANAGER and made.started[aes.AES_INDISP] == 0
    assert wm_update.spb_of(make_image({0: made.started}))[1] != gc.SCREEN_MANAGER, "ctlmgr holds no lock at its loop's top"
    assert bytes(made.started) == bytes(gc.start_of(THE_CLOSER_CLICKED)), "the turn's start is its arrival's machine"


# ---- THE ENTRY ON BOTH BLOBS: what the process pays for ever --------------------------------------------------------------------
THE_ROM_S_FRAME = 24                    # `link a6,#-12` (4 + 12) and `movem.l d6-d7,-(sp)` (8): $fe49d2, $fe49d6
ENTRY = "aes_rom_ctlmgr"
# How much deeper than the ROM's ctlmgr ours may stand where its main wait reaches the dispatcher: 14 bytes the
# call's ABI (36 argument bytes against the ROM's 22, whose last lies in the frame's scratch longword) and 14 below
# ev_multi's entry (GCC's frames of the event layer: not ctlmgr's). Measured 28 on both blobs; the prototype's was 76.
THE_ABI_S_AND_EV_MULTI_S_OWN = 28
ELFS = {"the bench blob": lambda: isr.blob().elf, "the shipped blob": lambda: transcription.SHIPPED_ELF}
_LEA_SP = re.compile(r"^lea %sp@\((-\d+)\),%sp$")
_MOVEM_PUSH = re.compile(r"^moveml ([%\w/-]+),%sp@-$")
_PUSH_ONE = re.compile(r"^movel %(?:[ad]\d|fp),%sp@-$")


def _registers_in(listed):
    """How many registers a `movem` list names (`%d2/%a2/%fp`, `%d3-%d5`)."""
    order = [f"%d{n}" for n in range(8)] + [f"%a{n}" for n in range(6)] + ["%fp"]
    count = 0
    for part in listed.split("/"):
        first, _dash, last = part.partition("-")
        count += order.index(last or first) - order.index(first) + 1
    return count


def frame_of_the_entry(elf):
    """THE BYTES `aes_rom_ctlmgr`'s OWN PROLOGUE TAKES below the stack it is entered on, read off its listing: the
    locals' `lea` and the saved registers, up to its first instruction that is neither."""
    frame = 0
    for _at, text in aes_switch._listed_functions(elf)[ENTRY]:
        lea, movem = _LEA_SP.match(text), _MOVEM_PUSH.match(text)
        if lea:
            frame -= int(lea.group(1))
        elif movem:
            frame += aes.LONG_BYTES * _registers_in(movem.group(1))
        elif _PUSH_ONE.match(text):
            frame += aes.LONG_BYTES
        else:
            return frame
    raise AssertionError(f"{ENTRY} is all prologue")


@pytest.mark.parametrize("elf", ELFS.values(), ids=ELFS)
def test_the_entry_s_own_frame_is_no_more_than_the_rom_s(elf):
    """RULING W2-R3's FIRST LEVER, HELD: the screen manager's every frame is stacked under ctlmgr's, on 1,196 bytes,
    so the entry and its loop cost the stack no more than the ROM's 24 — the six answer words and the registers
    GCC saves (a function that never returns saves what it uses all the same). The design pass's prototype was 72."""
    assert gc.GEMCTRL["CTL_WAIT_EVENTS"] and frame_of_the_entry(elf()) <= THE_ROM_S_FRAME


_A_WORD_OF_THE_FRAME = re.compile(r"^moveaw %sp@\(\d+\),%a\d$")
_PUSHED_WHOLE = re.compile(r"^movel %a\d,%sp@-$")
_ALWAYS = re.compile(r"^(?:bra[swl]?|jra) ([0-9a-f]+) ")
_A_TEST_OR_A_CALL = re.compile(r"^(?:btst #(\d+),|jsr .*<(\w+)>)")


def _next_test_or_call(body, index):
    """What `aes_rom_ctlmgr` does next after `body[index]`, an unconditional branch followed: the bit its next
    `btst` reads, or the routine its next `jsr` calls."""
    at_index = {at: nth for nth, (at, _text) in enumerate(body)}
    while True:
        index += 1
        text = body[index][1]
        always, found = _ALWAYS.match(text), _A_TEST_OR_A_CALL.match(text)
        if always:
            index = at_index[int(always.group(1), 16)] - 1
        elif found:
            return int(found.group(1)) if found.group(1) else found.group(2)


@pytest.mark.parametrize("elf", ELFS.values(), ids=ELFS)
def test_on_the_blobs_the_button_s_handler_runs_before_the_bar_s_and_the_lock_is_let_go_after_both(elf):
    """THE LOOP'S OWN ORDER, READ OFF EACH BUILD (the host's turns hold it by what it does — a button and the bar in
    one wake, the menu worked: the images at the menu's door calls differ with the handlers swapped; this holds it
    where the blobs' text is, which no turn runs on yet): after the wait the lock; after the lock's taking the test
    of bit 1; after hctl_button the test of bit 2, never the lock's release; after hctl_rect the lock's release,
    never a test; the count's step before each handler."""
    body = aes_switch._listed_functions(elf())[ENTRY]
    after = {}
    for index, (_at, text) in enumerate(body):
        called = re.match(r"^jsr .*<(\w+)>", text)
        if called:
            after.setdefault(called.group(1), set()).add(_next_test_or_call(body, index))
    button_bit, bar_bit = 1, 2                               # EV_MU_BUTTON, EV_MU_M1: `btst #1`, `btst #2`
    assert after["aes_hctl_button"] == {bar_bit} and after["aes_hctl_rect"] == {"aes_wm_update"}
    assert after["aes_ev_multi"] == {"aes_wm_update"} and after["aes_wm_update"] == {button_bit, "aes_w_setactive"}
    assert after["a_pending_click_wait_counted_off"] == {"aes_hctl_button", "aes_hctl_rect"}
    # ...and EACH HANDLER IS HANDED THE ANSWER'S TWO WORDS WHOLE (a word each, sign-extended into its slot by the move
    # into an address register) under the image: what no turn can hold of y, on a 200-row screen (UNPINNED, above).
    for index, (_at, text) in enumerate(body):
        if re.match(r"^jsr .*<aes_hctl_(?:button|rect)>", text):
            pushed = [each for _at, each in body[index - 5:index]]
            assert [bool(_A_WORD_OF_THE_FRAME.match(each)) for each in pushed] == [True, False, True, False, False], pushed
            assert all(_PUSHED_WHOLE.match(each) for each in (pushed[1], pushed[3])), pushed


def test_the_reading_of_a_prologue_counts_a_lea_and_every_saved_register():
    assert (_registers_in("%d2/%a2/%fp"), _registers_in("%d3-%d5/%a2-%a3"), _registers_in("%d2")) == (3, 5, 1)


@pytest.mark.parametrize("elf", ELFS.values(), ids=ELFS)
def test_the_entry_is_entered_by_no_call_reads_nothing_above_its_stack_and_never_returns(elf):
    """THE CONTRACT, read off the build: no `rts` / `rte` / `unlk` in it (it never returns, and has no frame pointer
    to unlink — A6 is its image base); no operand reaches above the stack it was entered on (no return address, no
    argument: `%sp@(d)` stays inside its own frame and the arguments it pushed); every callee by name (no `jsr` through
    a register: `no-function-cse`), and of the once-only part THE COPY BEFORE THE CLEAR — the first call is
    rc_copy's, and the leave word's `clrw` comes after it."""
    body = [text for _at, text in aes_switch._listed_functions(elf())[ENTRY]]
    assert not [text for text in body if text.split()[0] in ("rts", "rte", "rtr", "unlk")]
    assert not [text for text in body if re.match(r"^jsr %(?:a\d|fp)@", text)]
    calls = [index for index, text in enumerate(body) if text.startswith("jsr ")]
    clears = [index for index, text in enumerate(body) if text.startswith("clrw ") and "%sp" not in text]
    assert "aes_rc_copy" in body[calls[0]] and len(clears) == 1 and calls[0] < clears[0] < calls[1]
    assert "aes_w_setactive" in body[calls[1]]
    deepest_argument_bytes = 36                         # ev_multi's: the image and seven longword slots
    reach = [int(found) for text in body for found in re.findall(r"%sp@\((\d+)", text)]
    assert max(reach) < frame_of_the_entry(elf()) + deepest_argument_bytes


# ---- THE TWINS ON BOTH BLOBS, as far as a pending build can be run there --------------------------------------------------------
# No machine's screen manager is ours yet (the takeover is the flip's), so no TURN runs on a blob here. What does:
#   ictlmgr     whole, over the boot's own arrival — the two code longwords it stores OUR ENTRY's address, mapped back
#               to the ROM's through the registry's entry (`aes_event.SCREEN_MANAGER_ENTRY`: the mapping the takeover
#               applies) and nothing dropped there;
#   the entry   from the screen manager's first entry in the ROM's boot — the stack empty, the bytes above it POISONED —
#               through the once-only part and into its main wait, as far as its first dispatch: where the ROM's own
#               ctlmgr, run from the same machine, stands with the same machine outside the two stacks.
BENCHES = {"the bench blob": isr.blob, "the shipped blob": isr.shipped_blob}
OUR_ENTRY_S_MAPPING = aes_event.SCREEN_MANAGER_ENTRY
PSETUP_S_SR_WORD = range(aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + aes.WORD_BYTES)
BLOB_RUN_INSNS = 2_000_000              # a boot's stretch from the screen manager's first entry to its first wait: 6,500


def _in_ram(blob):
    return frozenset(range(blob.base, blob.end)) | frozenset(case.STACK_BAND) | aes_event.LINE_F_MASK_BYTES


@pytest.mark.parametrize("bench", BENCHES.values(), ids=BENCHES)
@pytest.mark.parametrize("accessories", CAPTURES.values(), ids=CAPTURES)
def test_ictlmgr_on_a_blob_stores_our_entry_where_the_rom_stores_its_ctlmgr_and_is_the_rom_s_beside(bench, accessories):
    """THE SECOND DIFFERENTIAL OF ictlmgr, on each blob, at the boot's own arrival: our build's run leaves the ROM's
    machine — outside the blob, the run's stack, the Line-F mask word and psetup's SR save word (each build's own
    condition codes) — ONCE THE TWO CODE LONGWORDS ARE MAPPED: each holds `aes_rom_ctlmgr`'s address in THIS blob,
    where the ROM's run stores $fe49d2, and they are the registry's two slots and no other longword. (Measured:
    2,598 cycles on the bench blob and 2,560 on the shipped one against the ROM's 3,614 — 0.71 / 0.70.)"""
    blob, (arguments, pokes) = bench(), _ictlmgr_arrived(accessories)
    the_rom_s, the_rom_s_writes, registers = aes_event._rom_run(make_image(aes.staged(gc.ICTLMGR, arguments, pokes)), addrs.AES_ROM_ICTLMGR)
    ours = blob._call(make_image(pokes), "aes_ictlmgr", (0, *arguments))
    entry = blob.entry(OUR_ENTRY_S_MAPPING.symbols[addrs.AES_ROM_CTLMGR])
    assert [case.long_in(ours.image, slot) for slot in OUR_ENTRY_S_MAPPING.slots] == [entry] * 2, "our entry, at both sites"
    mapped = bytearray(ours.image)
    for slot in OUR_ENTRY_S_MAPPING.slots:
        mapped[slot:slot + aes.LONG_BYTES] = addrs.AES_ROM_CTLMGR.to_bytes(aes.LONG_BYTES, "big")
    left_out = _in_ram(blob) | frozenset(PSETUP_S_SR_WORD)
    assert not aes_event.differing(mapped, the_rom_s, left_out)
    assert ours.d0 == registers["d0"] == gc.SCREEN_MANAGER
    # ...AND IT WRITES WHAT THE ROM'S WRITES, NO BYTE MORE (the two ledgers: a store of the value a byte already held
    # is in no image) — outside each build's own stack, the blob, the mask word and psetup's save word.
    our_writes, truncated = emu.bench_writes(ours.image)
    assert not truncated
    stored_by = [frozenset(at for at in writes if at < gc.RAM_BYTES and at not in left_out) for writes in (our_writes, the_rom_s_writes)]
    assert stored_by[0] == stored_by[1], f"ours alone stores at {sorted(map(hex, stored_by[0] - stored_by[1]))}, the ROM's alone at {sorted(map(hex, stored_by[1] - stored_by[0]))}"
    # ...AND ITS PRICE, held here while no table line can be (the registry maps no row's slots through that entry
    # until the flip): our cycles, net of the bench's entry, against the ROM routine's own — under Tier 3's bar.
    _entry_insns, entry_cycles = blob.overhead
    assert (ours.cycles - entry_cycles) / registers["cycles"] <= bench_tier3().TIER3_FUNCTION_BAR


def _run_to_its_first_dispatch(memory, entry, dsptch, registers, top):
    """A run ENTERED AS switchto's `rte` ENTERS THE SCREEN MANAGER — at `entry`, A7 the stack's top `top`, the register
    file `registers`, nothing staged at or above the top (the two longwords the oracle's entry lays there put back
    as they were) — and stopped at its first arrival at `dsptch`: the stack pointer there."""
    held = bytes(memory[top:top + 2 * aes.LONG_BYTES])
    emu.run_bench(memory, entry, case.long_in(memory, top + aes.LONG_BYTES), top, emu.SENTINEL, max_insns=BLOB_RUN_INSNS,
                  door=frozenset({entry}), seed_regs=[registers[name] for name in emu.REPORTED_REGS])
    memory[top:top + len(held)] = held
    try:
        emu.bench_door_arm(frozenset({dsptch}))
        result = emu.bench_resume(entry, max_insns=BLOB_RUN_INSNS)
        assert (result["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, dsptch), "the run never reached its dispatcher"
        return emu.bench_door_sp()
    finally:
        emu.bench_abort()


A_POISON = 0xa5                         # no address, no word of any frame


@pytest.mark.parametrize("bench", BENCHES.values(), ids=BENCHES)
@pytest.mark.parametrize("accessories", CAPTURES.values(), ids=CAPTURES)
def test_on_a_blob_the_entry_runs_from_the_first_entry_into_its_main_wait_as_the_rom_s_ctlmgr_does(bench, accessories):
    """THE ENTRY'S CONTRACT, RUN (and the loop's head with it): entered where the ROM's boot enters ctlmgr, with the
    eight bytes at and above its stack's top POISONED on our shore — it has no return address and no argument, and
    reads none — our build reaches its dispatcher (the main wait blocks: nothing is ready) with THE ROM'S MACHINE
    outside the screen manager's stack and the blob: the once-only part, w_setactive and the wait queued, its three
    events and its button among them. And it stands no deeper there than the ROM's ctlmgr by more than the 28 bytes
    measured (14 the call's ABI, 14 below ev_multi's entry): a bound, read off nothing a layout decides."""
    blob, boot = bench(), gc.the_first_entry(accessories)
    lo, top, _why = gc.its_stack(boot.ram)
    the_rom_s = make_image({0: boot.ram})
    its_depth = top - _run_to_its_first_dispatch(the_rom_s, addrs.AES_ROM_CTLMGR, addrs.AES_ROM_DSPTCH, boot.registers, top)
    ours = make_image({0: boot.ram})
    ours[blob.base:blob.base + len(blob.blob)] = blob.blob
    poisoned = slice(top, top + 2 * aes.LONG_BYTES)
    kept, ours[poisoned] = bytes(ours[poisoned]), bytes([A_POISON]) * (poisoned.stop - poisoned.start)
    registers = {**boot.registers, "pc": blob.entry(ENTRY)}
    our_depth = top - _run_to_its_first_dispatch(ours, blob.entry(ENTRY), blob.entry("aes_dsptch"), registers, top)
    assert set(ours[poisoned]) == {A_POISON}, "our run stored at or above the top of the stack it was entered on"
    ours[poisoned] = kept
    # ...and the frame the keyboard poll's BIOS trap saves under this machine's own `savptr` (w_setactive's wait
    # polls the keyboard): the caller's registers and return address, each build's own — as every page leaves it out.
    savptr = case.long_in(boot.ram, addrs.SYSVAR_SAVPTR)
    left_out = _in_ram(blob) | frozenset(range(lo, top)) | frozenset(range(savptr - addrs.TRAP_SAVE_FRAME_BYTES, savptr))
    assert not aes_event.differing(ours, the_rom_s, left_out)
    assert 0 < our_depth - its_depth <= THE_ABI_S_AND_EV_MULTI_S_OWN, f"ours stands {our_depth} deep at its dispatch, the ROM's {its_depth}"
