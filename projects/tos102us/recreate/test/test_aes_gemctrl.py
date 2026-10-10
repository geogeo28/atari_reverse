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
import struct

import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

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
    return aes_event.run_guarded(arrived.name, arrived.arguments, arrived.pokes, drawing=True, objects=gc.JUST_DRAW, **kwargs)


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
    held = aes_event.interrupted(spinning.name, spinning.arguments, spinning.machine(), {}, objects=True, switches=BLOCKS)
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
        held = aes_event.interrupted(made.name, made.arguments, made.machine(), {}, objects=True, switches=BLOCKS)
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
