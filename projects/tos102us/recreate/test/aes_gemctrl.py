"""THE SCREEN MANAGER'S HANDLERS AT THE ROM'S OWN ARRIVALS — the machines and the cases of `test_aes_gemctrl.py`
(`src/aes/gemctrl.c`: ct_msgup, hctl_window, hctl_button, hctl_rect).

The four run in the screen manager's process, called by its main loop (ctlmgr `$fe49d2`, the ROM's own) when its
wait comes back. So a case is never a frame somebody wrote: it is AN ARRIVAL —

  * A MACHINE THE ROM BOOTED (`aes_boot`): the desk alone, or the desk with the two test accessories
    (`test/acc/testacc.S`), each a real process the ROM's loader loaded, which opened a window of some kind and/or
    registered an entry of the desk menu by its own AES calls before it went to sleep;
  * THE ROM'S OWN DISPATCHER RUN FROM THAT MACHINE'S IDLE, real mouse packets taken through the ROM's interrupt
    handlers at its idles and at the polls between two processes' turns (`chain`, `at_polls`: what a user does) —
    until THE ROM'S ctlmgr CALLS THE HANDLER: the run is stopped at the handler's first instruction;
  * the arguments are the frame ctlmgr (or the handler above it) pushed, the machine every byte of RAM as it stands
    there. Nothing is poked.

The differential starts there: the ROM's routine and its C twin, each from that entry. A case whose handler LEAVES BY
THE DISPATCHER — a gadget watched or dragged while the button is down, an arrow repeated, the menu worked, the button
waited up — is a row that switches (`aes_switching`), its own deliveries taken at the idles and polls of ITS run;
the screen manager is the row's process, and the accessory's and the desk's turns inside it are foreign windows.

ONE ARRIVAL IS NOT A DISPATCHER'S: the boot's own. The desk's menu_bar posts the screen manager a click of its own
(mn_bar counts it in gl_mnclicks), and the ROM's boot arrives at hctl_button with it before its first idle —
`aes_boot.booted(..., until=)` stops the boot there.

WHAT A MACHINE'S POKES LEAVE OUT: the harness's own window of free RAM — from Tier 3's blob to the top of the run's
stack band — which every machine here leaves zero below the band (held where an arrival is made).
"""
import functools
import struct
from collections import namedtuple

import derived
from harness import addrs, make_image, project

import aes
import aes_boot
import aes_event
import aes_objdraw as od
import aes_switch
import case
import vdi

RAM_BYTES = aes_boot.RAM_BYTES
I, W = vdi.IMAGE_ARG, vdi.WORD_ARG
CT_MSGUP, HCTL_WINDOW = "AES_ROM_CT_MSGUP", "AES_ROM_HCTL_WINDOW"
HCTL_BUTTON, HCTL_RECT = "AES_ROM_HCTL_BUTTON", "AES_ROM_HCTL_RECT"
SIGNATURES = {CT_MSGUP: (None, (I, W, W, W, W, W, W, W)), HCTL_WINDOW: (None, (I, W, W, W)),
              HCTL_BUTTON: (None, (I, W, W)), HCTL_RECT: (None, (I, W, W))}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
ROUTINES = tuple(SIGNATURES)
FRAMES = {name: struct.Struct(f">{len(argtypes) - 1}h") for name, (_restype, argtypes) in SIGNATURES.items()}
ENTRIES = {getattr(addrs, name): name for name in ROUTINES}
GEMCTRL = aes.header_constants("gemctrl.h")
JUST_DRAW = aes.walkers(od.JUST_DRAW)
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD

# ---- THE MACHINES ----------------------------------------------------------------------------------------------------------
# Each the ROM's own boot (`aes_boot`), by what its two accessories do before they wait. A window's kind is GEM's
# gadget bits (`aes/wmlib.h`'s WK_*, and MOVER).
WK = {name: value for name, value in aes.header_constants("wmlib.h").items() if name.startswith("WK_")}
MOVER = GEMCTRL["WK_MOVER"]
EVERY_GADGET = aes_event.EVERY_GADGET
NEVER_MOVED, NEVER_SIZED = EVERY_GADGET & ~MOVER, EVERY_GADGET & ~WK["WK_SIZER"]     # each still has the other's bit
SIZED_WITH_A_VERTICAL_BAR = (WK["WK_NAME"] | MOVER | WK["WK_SIZER"] | WK["WK_UPARROW"] | WK["WK_DNARROW"] | WK["WK_VSLIDE"])
SIZED_WITH_A_HORIZONTAL_BAR = (WK["WK_NAME"] | MOVER | WK["WK_SIZER"] | WK["WK_LFARROW"] | WK["WK_RTARROW"] | WK["WK_HSLIDE"])
# ...and A SIZER WITH ONE GADGET ALONE ON EACH BAR — a slider with no arrow, an arrow with no slider: every bit of
# the two masks hctl_window reads for the smallest size decides one machine's clamp by itself.
SIZED = WK["WK_NAME"] | MOVER | WK["WK_SIZER"]
REGISTER, HIDE, QUIET = aes_boot.REGISTER, aes_boot.HIDE, aes_boot.QUIET
_window = aes_boot.with_a_window
THE_DESK = "the desk alone"
TWO_WINDOWS = "two accessories, a window of every gadget each, the first's entry in the desk menu"
NO_MOVER = "one accessory's window of every gadget but the MOVER"
NO_SIZER = "one accessory's window of every gadget but the SIZER"
TALL = "one accessory's window with a sizer and the vertical bar alone"
WIDE = "one accessory's window with a sizer and the horizontal bar alone"
HIDING = "an accessory with a window that hides the menu bar when its entry is chosen"
ONE_GADGET_A_BAR = {
    "a sizer, the horizontal slider alone and the up arrow alone": SIZED | WK["WK_HSLIDE"] | WK["WK_UPARROW"],
    "a sizer, the left arrow alone and the down arrow alone": SIZED | WK["WK_LFARROW"] | WK["WK_DNARROW"],
    "a sizer, the right arrow alone and the vertical slider alone": SIZED | WK["WK_RTARROW"] | WK["WK_VSLIDE"],
}
ACCESSORY_MODES = {
    TWO_WINDOWS: (_window(EVERY_GADGET, REGISTER), _window(EVERY_GADGET)),
    NO_MOVER: (_window(NEVER_MOVED), QUIET),
    NO_SIZER: (_window(NEVER_SIZED), QUIET),
    TALL: (_window(SIZED_WITH_A_VERTICAL_BAR), QUIET),
    WIDE: (_window(SIZED_WITH_A_HORIZONTAL_BAR), QUIET),
    HIDING: (_window(EVERY_GADGET, REGISTER | HIDE), QUIET),
    **{key: (_window(kind), QUIET) for key, kind in ONE_GADGET_A_BAR.items()},
}
MACHINES = (THE_DESK, *ACCESSORY_MODES)
FIRST_ACCESSORY, SECOND_ACCESSORY = aes_boot.ACCESSORY_NAMES
THE_SCREEN_MANAGER, THE_DESK_S_PROCESS = "SCRENMGR", "the desk"


@functools.cache
def machine(key):
    """The booted machine `key` names (an `aes_boot.Machine`), waiting at its first idle."""
    return aes_boot.desk_machine() if key == THE_DESK else aes_boot.accessory_machine(*ACCESSORY_MODES[key])


def pd_of(key, who):
    """The PD of the process `who` of the machine `key`: the two static ones by their place, an accessory by its
    name — read off the machine (an allocated accessory's PD lies where GEMDOS put its block)."""
    if who == THE_SCREEN_MANAGER:
        return SCREEN_MANAGER
    return SHELL if who == THE_DESK_S_PROCESS else machine(key).named(who).pd


def pid_of(key, who):
    return case.word_in(machine(key).ram, pd_of(key, who) + aes.PD_PID)


# ---- WHERE A MACHINE'S WINDOWS AND GADGETS ARE -----------------------------------------------------------------------------
# A window's rectangle is read off the machine (its object in the window tree); a gadget's point is that corner
# plus an offset — measured once on a 152 x 90 window in low resolution (testacc.S's WINDOW_W / WINDOW_H; a box is
# 16 x 11 there), and HELD by every case that uses one: the message its handler sends says which gadget the ROM's
# own ob_find found.
Window = namedtuple("Window", "handle owner x y w h")
WINDOW_TREE = aes.AES_WINDOW_TREE
GADGET_AT = {
    "the closer": (6, 4), "the title": (66, 4), "the title's left end": (15, 4), "the fuller": (146, 4),
    "the information line": (66, 16),
    "the up arrow": (146, 26), "the vertical track above its elevator": (146, 36), "the vertical elevator": (146, 52),
    "the vertical track below its elevator": (146, 65), "the down arrow": (146, 75), "the sizer": (146, 85),
    "the left arrow": (6, 85), "the horizontal track left of its elevator": (26, 85),
    "the horizontal elevator": (61, 85), "the horizontal track right of its elevator": (106, 85),
    "the right arrow": (134, 85),
}


def window(key, handle):
    """Window `handle` of the machine `key`: who owns it and where its object lies."""
    ram = machine(key).ram
    owner = case.long_in(ram, aes.AES_WINDOWS + handle * aes.WIN_BYTES + aes.WIN_OWNER) & aes_boot.BUS
    x, y, w, h = (od.object_word(ram, WINDOW_TREE, handle, field) for field in ("X", "Y", "WIDTH", "HEIGHT"))
    return Window(handle, case.word_in(ram, owner + aes.PD_PID), x, y, w, h)


def top_window(key):
    return window(key, aes.signed(case.word_in(machine(key).ram, aes.AES_GL_WTOP)))


def other_window(key):
    """The window of `key` that is NOT the top one (a machine of two)."""
    top = top_window(key).handle
    handle, = (each for each in (1, 2) if each != top)
    return window(key, handle)


def gadget(key, name):
    """The point of the top window's gadget `name` in the machine `key`."""
    top, (dx, dy) = top_window(key), GADGET_AT[name]
    return top.x + dx, top.y + dy


# ---- WHAT A USER DOES, AS THE INTERRUPTS OF ONE IDLE (or of one poll) ---------------------------------------------------------
PRESS, RELEASE = aes_event.press, aes_event.release


def click(image):
    """A CLICK over `image` in place: the button down and up again inside the click's delay (`aes_event.CLICKING`) —
    the screen manager is woken with the button already up."""
    return aes_event.taken_in_place(image, aes_event.CLICKING)


def onto(point):
    return aes_event.move_to(*point)


def right_for_left(image):
    """THE RIGHT BUTTON DOWN AND THE LEFT ONE UP, in one packet (`aes_event.RIGHT_PRESSING`: the IKBD names both
    buttons in every packet) — over a machine whose left button is held, the left button's rise with the right one
    left down."""
    return aes_event.taken_in_place(image, aes_event.RIGHT_PRESSING)


# ---- AN ARRIVAL --------------------------------------------------------------------------------------------------------------
# `machine`: a key of MACHINES. `chain`: `{idle: (interrupt, ...)}` from the machine's own idle on; `at_polls`:
# `{poll: (interrupt, ...)}` at a poll of the dispatcher that is no idle (both as `aes_switch.scheduled` numbers
# them). `routine`, `which`: the run is stopped at its `which`-th arrival at that handler's entry. `budget`: the
# run's own, declared, for one past a derivation's default.
Arrival = namedtuple("Arrival", "machine chain routine which at_polls budget", defaults=(0, None, None))
Arrived = namedtuple("Arrived", "name arguments pokes")
Arrived.__doc__ = """An arrival made: the handler's `addrs` name, the arguments its caller pushed, and the machine there
as pokes (the module's docstring: every byte of RAM outside the harness's own free window)."""
FREE_FROM = project.current().bench_base    # the harness's window of free RAM: Tier 3's blob, the staging band, ...
FREE_UNTIL = case.STACK_BAND[-1] + 1        # ...up to the top of the run's stack band
BOOT_ARRIVAL = Arrival(THE_DESK, None, HCTL_BUTTON)     # the boot's own (the module's docstring): no chain at all


class _ToAnArrival:
    """The watch of one run of the ROM's dispatcher from an idle machine (`aes_event.interrupting`'s): stopped at
    idle's poll, the instruction after it and disp's call of switchto — the polls and the idles counted as
    `aes_switch.scheduled` counts them, each delivery due at its own — and at the handlers' entries: the run ENDS
    (`aes_event.Ended`) at the `which`-th arrival at `entry`, the frame there and the RAM kept."""

    def __init__(self, memory, at_idle, at_polls, entry, which):
        self._memory, self.at_idle, self.at_polls = memory, dict(at_idle), dict(at_polls or {})
        self._entry, self._left, self._due, self._back = entry, which, False, None
        self.first = aes_switch.EVERY_STOP | {entry}
        self.polls, self.idles, self.arrived = 0, 0, None

    def due(self, _watch, pc):
        if pc != addrs.AES_ROM_IDLE_LOOP:
            return None
        if not aes_switch.waits_for_an_interrupt(self._memory):
            interrupt = self.at_polls.pop(self.polls, None)
            return ((aes_switch.AT_A_POLL, self.polls), interrupt) if interrupt is not None else None
        interrupt = self.at_idle.pop(self.idles, None)
        self._due = interrupt is not None
        return ((aes_switch.AT_AN_IDLE, self.idles), interrupt) if self._due else None

    def stopped(self, pc, sp, memory):
        if pc == self._entry:
            if not self._left:
                frame = FRAMES[ENTRIES[pc]]
                at = sp + aes.LONG_BYTES
                self.arrived = (frame.unpack(bytes(memory[at:at + frame.size])), bytes(memory[:RAM_BYTES]))
                raise aes_event.Ended
            # An earlier arrival: the entry is a stop again from where this call comes back to (a watch may not arm
            # the PC it stands at, and a manager that calls the handler again at once passes no dispatcher's stop).
            self._left, self._back = self._left - 1, case.long_in(memory, sp) & aes_boot.BUS
            return (self.first - {pc}) | {self._back}
        if pc == self._back:
            self._back = None
        else:
            aes_switch.dispatcher_stop(pc, memory, lambda _pd: None, self._an_idle, delivered=self._due, polls=self._a_poll)
        return (self.first - {pc}) | ({self._back} if self._back else frozenset())

    def _a_poll(self):
        self.polls += 1

    def _an_idle(self):
        assert self._due or self.at_idle, (
            f"the dispatcher idles (idle {self.idles}) with nothing left to deliver, and the ROM's ctlmgr has not "
            f"called {ENTRIES[self._entry]}: the chain does not arrive there")
        self._due, self.idles = False, self.idles + 1


@derived.kept
def _arrived_through(pokes, chain, at_polls, routine, which, budget=None):
    """THE DERIVATION (ROM-only, kept by content): the ROM's dispatcher run over the idle machine `pokes`, the
    interrupts of `chain` taken at its idles and of `at_polls` at its polls, to the `which`-th arrival at
    `addrs.<routine>`: `(the arguments, the megabyte of RAM there)`. REFUSED BY NAME: a chain that idles with
    nothing left before the arrival, and one that arrives with a delivery still undelivered."""
    memory = make_image(pokes)
    watch = _ToAnArrival(memory, chain, at_polls, getattr(addrs, routine), which)
    try:
        aes_event.interrupting(memory, addrs.AES_ROM_DISP_LOOP, watch, watch.due, budget)
    except aes_event.Ended:
        pass
    assert watch.arrived is not None, f"the dispatcher's loop returned before any arrival at {routine}"
    assert not watch.at_idle and not watch.at_polls, (
        f"the ROM's ctlmgr called {routine} before the deliveries at the idles {sorted(watch.at_idle)} and the polls "
        f"{sorted(watch.at_polls)} were due: they belong to the handler's own run, not to the chain that arrives at it")
    return watch.arrived


@functools.cache
def _boot_arrived():
    """The desk's boot stopped at its first call of hctl_button (`aes_boot.booted`'s `until`)."""
    boot = aes_boot.booted(aes_boot.preinit(), aes_boot.blank_disk(), until=addrs.AES_ROM_HCTL_BUTTON)
    frame, at = FRAMES[HCTL_BUTTON], boot.registers["isp"] + aes.LONG_BYTES
    assert boot.registers["sr"] & aes_boot.SR_SUPERVISOR and boot.registers["pc"] == addrs.AES_ROM_HCTL_BUTTON
    return frame.unpack(boot.ram[at:at + frame.size]), boot.ram


def _as_pokes(ram, where):
    """`ram` as a machine's pokes (the module's docstring), the free window held empty below the run's own band."""
    in_the_window = [at for at in range(FREE_FROM, case.STACK_BAND[0]) if ram[at]]
    assert not in_the_window, (
        f"{where}: the machine holds something in the harness's free window, from {in_the_window[0]:#x} — the "
        f"blob, the staging band and the staged disk would lie over it")
    return {0: bytes(ram[:FREE_FROM]), FREE_UNTIL: bytes(ram[FREE_UNTIL:])}


@functools.cache
def _made(machine_key, chain, routine, which, at_polls, budget):
    if chain is None:
        arguments, ram = _boot_arrived()
    else:
        arguments, ram = _arrived_through(machine(machine_key).pokes, dict(chain), dict(at_polls or {}), routine, which,
                                          *((budget,) if budget else ()))
    return Arrived(routine, arguments, _as_pokes(ram, f"{routine}, arrived at over {machine_key}"))


def _frozen(schedule):
    return None if schedule is None else tuple(sorted(schedule.items()))


def at(arrival):
    """`arrival` MADE (once a process; the derivation kept): its `Arrived`."""
    chain = arrival.chain() if callable(arrival.chain) else arrival.chain      # `gadget_arrival_later`
    return _made(arrival.machine, _frozen(chain), arrival.routine, arrival.which, _frozen(arrival.at_polls),
                 arrival.budget)


# ---- THE CASES ---------------------------------------------------------------------------------------------------------------
# A handler at an arrival. `switches`: how its run first leaves by the dispatcher (`aes_event.BLOCKS` / `YIELDS`), or
# None for one that returns without a switch — a switching run's `at_idle` / `at_polls` / `at_calls` are what is
# delivered at the idles, the polls and the door calls OF THAT RUN (numbered from its entry). `message`: the message
# the run sends LAST — `(type, to, five words)`, a zero-argument builder of it, or a type's name alone where the words
# are the run's to say — or None for a run that sends none.
Case = namedtuple("Case", "arrival switches at_idle at_polls at_calls message", defaults=(None, None, None, None, None))
MESSAGES = {name: GEMCTRL[name] for name in ("MN_SELECTED_MESSAGE", "WM_TOPPED", "WM_CLOSED", "WM_FULLED", "WM_ARROWED",
                                             "WM_HSLID", "WM_VSLID", "WM_SIZED", "WM_MOVED", "AC_OPEN")}


def name_of(routine):
    return aes_event.short_name(routine)


def _on_the_top_window(key, name, button, *then):
    """The chain that brings the mouse onto the top window's gadget `name` of the machine `key`, then `button` (a
    click, or a press held), then each of `then` at the idle after."""
    return {0: (onto(gadget(key, name)),), 1: (button,), **{2 + nth: (each,) for nth, each in enumerate(then)}}


def gadget_arrival(key, name, button, routine=HCTL_WINDOW, *then, **more):
    return Arrival(key, _on_the_top_window(key, name, button, *then), routine, **more)


def gadget_arrival_later(key, name, button, routine=HCTL_WINDOW):
    """`gadget_arrival` WITH ITS CHAIN LEFT UNMADE until the arrival is (`at`): a gadget's point is read off the booted
    machine, and a machine only cases that are NO REGISTERED ROW use must not be booted by the registry's import —
    every xdist worker and every bench process pays that import."""
    return Arrival(key, functools.partial(_on_the_top_window, key, name, button), routine)


# POINTS OF THE SCREEN no window decides: on the menu bar past its titles (the screen manager's, and nobody's
# window); the desk menu's title and the accessory's entry under it; a place below the bar, off every menu and
# window (`aes_event`'s own points of the menu chain beside them).
ON_THE_BAR_PAST_THE_TITLES = (280, 5)
THE_DESK_TITLE_S_POINT = (30, 5)
OFF_EVERY_MENU = (300, 150)
BELOW_THE_VIEW_TITLE = (aes_event.THE_VIEW_TITLE_S_POINT[0], 60)
ONTO_THE_VIEW_TITLE, ONTO_ITS_PLAIN_ITEM = aes_event.ONTO_THE_VIEW_TITLE, aes_event.ONTO_ITS_PLAIN_ITEM
THE_VIEW_TITLE, VIEW_S_PLAIN_ITEM = 5, 30           # the desk's menu, as `test_aes_mnlib.py` holds it
INTO_AN_ITEM = (24, 4)                  # a point of a menu item, from its corner: on its text, inside its eight rows
ROOT_OF_THE_DROP_DOWNS = 7              # the desk's menu: the root's last child, the drop-downs' parent


def _desk_menu_item_s_point(key, item):
    ram = machine(key).ram
    tree, box = case.long_in(ram, aes.AES_GL_MNTREE), case.word_in(ram, aes.AES_GL_DABOX)
    x = sum(od.object_word(ram, tree, each, "X") for each in (ROOT_OF_THE_DROP_DOWNS, box, item))
    y = sum(od.object_word(ram, tree, each, "Y") for each in (ROOT_OF_THE_DROP_DOWNS, box, item))
    return x + INTO_AN_ITEM[0], y + INTO_AN_ITEM[1]


def accessory_entry_point(key):
    """A point of THE FIRST ACCESSORY ENTRY of the desk menu of the machine `key`, once the menu is dropped: the item
    gl_dafirst names, in the box gl_dabox names — read off the machine's own tree."""
    ram = machine(key).ram
    assert case.word_in(ram, aes.AES_GL_DACNT), f"{key}: no accessory is registered"
    return _desk_menu_item_s_point(key, case.word_in(ram, aes.AES_GL_DAFIRST))


def desk_s_own_item(key):
    """THE DESK MENU'S OWN FIRST ITEM in the machine `key` (the object after its box: "Desktop info..."), and a
    point of it once the menu is dropped: `(the item, the point)`."""
    item = case.word_in(machine(key).ram, aes.AES_GL_DABOX) + 1
    return item, _desk_menu_item_s_point(key, item)
