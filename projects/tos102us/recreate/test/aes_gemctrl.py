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
import ctypes
import functools
import mmap
import struct
from collections import namedtuple

import derived
from harness import _lib, addrs, make_image, project

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
# ...and THEIR CALLER (band 5 wave 2, `src/aes/ctlmgr.c`): ictlmgr, which returns; ctlmgr, which is entered by no call
# and never returns — off target its two parts, each a call of the candidate's (below: A TURN).
ICTLMGR = "AES_ROM_ICTLMGR"
aes.declare_alcyon(ICTLMGR, aes.LONG_ANSWER, (I, W))
CTLMGR_BEGINS, CTLMGR_TURN = "aes_ctlmgr_begins", "aes_ctlmgr_turn"
THE_LOOP_S_TOP = addrs.AES_ROM_CTLMGR_LOOP
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
# ...and TWO MORE PROCESSES IN A MULTI-CLICK BUTTON WAIT beside the desk (testacc.S's ACC_DOUBLE: its six-way wait asks
# for two clicks): the one way the AES's count of such waits (gl_bpend, which ctlmgr steps) stands above 1 where the
# screen manager wakes — 3 at the idle, 2 once its first turn has stepped it.
TWO_WAITERS = "two accessories with a window each, both in a six-way wait for two clicks"
A_TWO_CLICK_WAIT = aes_boot.MULTI | aes_boot.accessory_disk.DOUBLE
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
    TWO_WAITERS: (_window(EVERY_GADGET, A_TWO_CLICK_WAIT), _window(EVERY_GADGET, A_TWO_CLICK_WAIT)),
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
                frame = FRAMES.get(ENTRIES.get(pc))        # ...none where the stop is no routine's entry (the loop's top)
                at = sp + aes.LONG_BYTES
                self.arrived = (frame.unpack(bytes(memory[at:at + frame.size])) if frame else (), bytes(memory[:RAM_BYTES]))
                raise aes_event.Ended
            # An earlier arrival: the entry is a stop again from where this call comes back to (a watch may not arm
            # the PC it stands at, and a manager that calls the handler again at once passes no dispatcher's stop).
            # (The loop's top is no routine's entry and has no return address under it: it is passed at the word
            # after its call word — a spinning manager comes round again with no stop in between at all.)
            passed_at = THE_LOOP_S_TOP + aes.WORD_BYTES if pc == THE_LOOP_S_TOP else case.long_in(memory, sp) & aes_boot.BUS
            self._left, self._back = self._left - 1, passed_at
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
            f"called {ENTRIES.get(self._entry, f'at {self._entry:#x}')}: the chain does not arrive there")
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


# ---- A TURN OF THE SCREEN MANAGER'S LOOP ---------------------------------------------------------------------------------------
# ctlmgr never returns, so nothing of it is "a call and its return". What both shores can run is ONE TURN: from an
# arrival at the loop's top (`AES_ROM_CTLMGR_LOOP`: w_setactive's call word) to the NEXT arrival there.
#   * THE ROM'S is one run of its own dispatcher from a booted machine's idle (as an arrival's): `chain` / `chain_polls`
#     take it to its `which`-th arrival at the loop's top — where the machine is KEPT, every byte of RAM: the turn's
#     START — and the run goes on, ON THE SCREEN MANAGER'S OWN STACK, the turn's own deliveries taken at ITS idles
#     (`at_idle`), its polls that are no idle (`at_polls`) and its door calls (`at_calls`), each numbered from the
#     turn's start, until the screen manager stands at the loop's top again. Read as `aes_switch.scheduled` reads a
#     call's run (`_Idling`, a door watch: the one reading), and answered as one (`aes_switch.Scheduled`).
#   * THE C'S is `aes_ctlmgr_turn` over that start, through the host's model (`aes_switch.modelled`, the door bound):
#     the screen manager the run's ONE C process, every other process the ROM's own code.
# WHAT DIFFERS BY NATURE BESIDE THE MODEL'S OWN (`aes_switch.model_drops`): THE SCREEN MANAGER'S OWN STACK — the ROM's
# run lays its frames there, the host's C has none (its escaping locals are host slots, in the run's stack band) —
# named whole at the stops (`its_stack`), and at the end cut to the bytes the ROM's turn changed.
# `staged`: AN ARGUMENT-CLASS STAGING, LABELLED — `(label, {address: bytes})` laid over the machine WHERE THE TURN
# STARTS, on both shores: for a word no machine at hand brings to the value a case needs (the multi-click count at
# 0, 2 and 3; a key in the screen manager's own queue). Never a frame, never a list. `also_dropped`: `(lo, hi, why)`
# windows the turn names as its own by nature (`aes_switching.SwitchingRow.also_dropped`'s rule: each byte one the
# ROM's turn changed, the turn red without it).
Turn = namedtuple("Turn", "machine chain which at_idle at_polls at_calls chain_polls budget staged also_dropped",
                  defaults=(0, None, None, None, None, None, None, ()))
Turned = namedtuple("Turned", "started reference handlers")
Turned.__doc__ = """A turn the ROM made: the megabyte of RAM where it STARTED (the loop's top), the run as an
`aes_switch.Scheduled` (its `memory` and `started` megabytes too), and THE HANDLERS ctlmgr CALLED in it, in order
(`addrs` names: hctl_button, hctl_rect) — read at their entries, which only the screen manager's loop reaches from
its own frame."""
THE_LOOP_S_HANDLERS = {getattr(addrs, name): name for name in (HCTL_BUTTON, HCTL_RECT)}
# ...told from a handler's call of another by where it returns to: the two words after ctlmgr's own call words.
CTLMGR_S_RETURNS = frozenset(at + aes.WORD_BYTES for name in (HCTL_BUTTON, HCTL_RECT)
                             for sites in aes.line_f_call_sites(name).values() for at in sites
                             if addrs.AES_ROM_CTLMGR <= at < addrs.AES_ROM_ICTLMGR)
assert len(CTLMGR_S_RETURNS) == len(THE_LOOP_S_HANDLERS), "ctlmgr calls each of its two handlers at one place"
ITS_STACK_WHY = ("the screen manager's own stack (its UDA's, from the lowest byte the UDA leaves it to its top): the "
                 "ROM's ctlmgr and everything under it lay their frames there; a host core's are the host's, its "
                 "escaping locals host slots")


def its_stack(ram):
    """THE SCREEN MANAGER'S USABLE STACK in the machine `ram`, a `(lo, hi, why)` window read off the machine's own
    pointers: from the first byte past its UDA's own fields up to the top psetup's frame was laid under — the
    1,196 bytes everything the process does is stacked in."""
    uda = aes_event.uda_of(SCREEN_MANAGER, ram)
    return (uda + aes.UDA_STATE_BYTES, aes.AES_UDA1_STACK_TOP, ITS_STACK_WHY)


# ---- THE BIOS'S REGISTER-SAVE FRAME UNDER A BOOTED MACHINE'S OWN `savptr` --------------------------------------------------------
# Every wait polls the keyboard through the BIOS, whose trap saves its caller's registers and return address in the
# frame under `savptr` — each build's own, and none at all for a host core: dead once the trap has returned, and left
# out of every comparison of the event layer's (`aes_event.TRAP_SAVE_AT`). THAT SPAN IS THE SNAPSHOT'S: it lies one
# frame under the savptr THE BOOT SNAPSHOT was captured with, and a capture lands at a phase of the desk's idle loop —
# `savptr` at the save area's top between polls, or one 46-byte frame lower inside a BIOS trap. A BOOTED MACHINE's
# savptr is its own (the top, where the ROM's boot first idles): over a snapshot captured between polls the two frames
# are one, and over one captured inside a trap this machine's frame is compared byte for byte — the ROM's saved
# registers against a host core's nothing (a third fresh capture set: 54 cases red in $90e..$933, 27 of them wave 1's
# at HEAD). So a comparison over a booted machine names ITS frame, read off ITS savptr — only where the tree's own
# exclusion is not already that frame, and then cut, as every drop is, to the bytes the ROM's run stored.
TRAP_SAVE_WHY = ("the BIOS's register-save frame under THIS machine's own savptr (the keyboard poll's trap: its caller's "
                 "registers and return address, dead once the trap returns; none of a host core's) — where it is not "
                 "the snapshot's, which the tree leaves out already")


def its_trap_save(ram):
    """`(lo, hi, why)`: the register-save frame the BIOS last used on the machine `ram` — the one under ITS savptr."""
    top = case.long_in(ram, addrs.SYSVAR_SAVPTR) & aes_boot.BUS
    return (top - addrs.TRAP_SAVE_FRAME_BYTES, top, TRAP_SAVE_WHY)


def its_trap_save_beside_the_snapshot_s(ram):
    """...as the windows a comparison over that machine names BESIDE the tree's own: `()` where the frame is the one
    the snapshot's savptr already leaves out of every comparison (nothing to name: a window there is refused as not
    needed, by being none), else the frame."""
    lo, hi, why = its_trap_save(ram)
    return () if (lo, hi) == aes_event.THE_POLL_S_TRAP_SAVE else ((lo, hi, why),)


class TurnEnded(aes_event.Ended):
    """The screen manager stands at the loop's top again."""


class _ThroughATurn:
    """The watch of one run that ARRIVES at the loop's top and then MAKES A TURN (above): `_ToAnArrival` until the
    arrival, where the machine is kept and the reading handed to `aes_switch._Idling` over a door watch — the
    loop's top a stop beside theirs, where the run ENDS (`TurnEnded`). What the turn takes is kept as the run takes
    it (`delivered`): a run a watch ends hands back no ledger of its own."""

    def __init__(self, memory, turn_of, chain, chain_polls, which, staged=None):
        self._memory, self._turn_of, self._staged = memory, turn_of, staged or {}
        self._arriving, self._turning = _ToAnArrival(memory, chain, chain_polls, THE_LOOP_S_TOP, which), None
        self.first = self._arriving.first
        self.started, self.delivered, self.calls, self.handlers, self._armed = None, {}, [], [], frozenset()

    @property
    def arriving(self):
        return self._arriving

    @property
    def turning(self):
        return self._turning

    def _kept(self, key, interrupt):
        """`interrupt`, taken as the loop takes it, what it found and wrote kept under `key`."""
        memory = self._memory

        def taken(image):
            wrote = {}
            for each in interrupt if isinstance(interrupt, tuple) else (interrupt,):
                wrote = case.merge_pokes(wrote, each(image))
            self.delivered[key] = ({at: bytes(memory[at:at + len(data)]) for at, data in wrote.items()}, wrote)
            return wrote
        return taken

    def due(self, watch, pc):
        if self._turning is None:
            return self._arriving.due(watch, pc)
        if pc == THE_LOOP_S_TOP:
            return None
        due = self._turning.due(watch, pc)
        return due and (due[0], self._kept(*due))

    def stopped(self, pc, sp, memory):
        if self._turning is None:
            try:
                return self._arriving.stopped(pc, sp, memory)
            except aes_event.Ended:
                for at, data in self._staged.items():      # the labelled staging (`Turn.staged`), and nothing else
                    memory[at:at + len(data)] = data
                self.started = bytes(memory[:RAM_BYTES])
                self._turning = self._turn_of(memory, self.calls)
                self._armed = self._turning.first - {pc}
                return self._armed | frozenset(THE_LOOP_S_HANDLERS)
        if pc == THE_LOOP_S_TOP:
            raise TurnEnded
        if pc in THE_LOOP_S_HANDLERS:       # a call noted, nothing read of it: the stops stand as they stood
            if case.long_in(memory, sp) & aes_boot.BUS in CTLMGR_S_RETURNS:
                self.handlers.append(THE_LOOP_S_HANDLERS[pc])
            return self._armed | (frozenset(THE_LOOP_S_HANDLERS) - {pc}) | {THE_LOOP_S_TOP}
        self._armed = self._turning.stopped(pc, sp, memory)
        return self._armed | frozenset(THE_LOOP_S_HANDLERS) | {THE_LOOP_S_TOP}


def _taken_where(delivered, where):
    return {ordinal: taken for (kind, ordinal), taken in delivered.items() if kind == where}


@derived.kept
def _turned(pokes, chain, chain_polls, which, at_idle, at_polls, at_calls, staged=None, also_dropped=(), budget=None):
    """THE DERIVATION (ROM-only, kept by content): the ROM's dispatcher run over the idle machine `pokes` to the
    `which`-th arrival of its ctlmgr at the loop's top, and on through ONE TURN (above): `(the megabyte the turn
    started from, the megabyte it left, and the turn as `aes_switch.Scheduled`'s fields)`. REFUSED BY NAME: a chain
    that never arrives, a turn that never ends (the machine idles with nothing more to deliver), a delivery named
    where the turn makes no such idle, poll or door call."""
    memory = make_image(pokes)
    left_out = (aes_switch.left_out_under_the_model(SCREEN_MANAGER) + (its_stack(memory),)
                + its_trap_save_beside_the_snapshot_s(memory) + tuple(also_dropped))

    def turn_of(over, calls):
        door = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS,
                                   lambda pc, sp, at: calls.append(aes_event.handed_at(pc, sp, at)))
        door.images = left_out
        return aes_switch._Idling(over, at_idle, door, SCREEN_MANAGER, at_calls, at_polls)

    watch = _ThroughATurn(memory, turn_of, chain, chain_polls, which, staged)
    aes_event.begin_a_schedule(at_calls)
    try:
        aes_event.interrupting(memory, addrs.AES_ROM_DISP_LOOP, watch, watch.due, budget)
    except TurnEnded:
        pass
    except aes_event.Ended:
        raise AssertionError(
            "the machine idles with nothing more to deliver and the screen manager has not come back to its loop's "
            "top: the turn does not end" if watch.turning else
            "the dispatcher's loop ended before the screen manager arrived at its loop's top") from None
    else:
        raise AssertionError("the dispatcher's loop returned: no turn was made")
    turning = watch.turning
    assert not watch.arriving.at_idle and not watch.arriving.at_polls, "the chain's deliveries were not all taken before the arrival"
    assert not turning.at_idle and not turning.at_polls, (
        f"the turn made {turning.idles} idle(s) and {turning.polls} poll(s): nothing was delivered at the idles "
        f"{sorted(turning.at_idle)} / the polls {sorted(turning.at_polls)}")
    at_door_calls = _taken_where(watch.delivered, aes_switch.AT_A_DOOR_CALL)
    never_made = aes_event.undelivered(at_calls, at_door_calls)
    assert not never_made, f"the turn made {len(watch.calls)} door call(s): nothing was delivered at {never_made}"
    assert case.long_in(memory, aes.AES_RLR) & aes_boot.BUS == SCREEN_MANAGER, "the turn ended in another process"
    at_the_polls = {poll: (case.merge_pokes(turning.stood[poll], found), wrote)
                    for poll, (found, wrote) in _taken_where(watch.delivered, aes_switch.AT_A_POLL).items()}
    door = turning._door
    return (watch.started, bytes(memory[:RAM_BYTES]), _taken_where(watch.delivered, aes_switch.AT_AN_IDLE), turning.idles,
            tuple(turning.entered), tuple(watch.calls), at_door_calls, turning.polls, at_the_polls, tuple(door.answers),
            tuple(turning.dispatches), tuple(watch.handlers))


@functools.cache
def _turn_made(machine_key, chain, chain_polls, which, at_idle, at_polls, at_calls, budget, staged, also_dropped):
    (started, left, delivered, idles, entered, calls, at_door_calls, polls, at_the_polls, answers, dispatches,
     handlers) = _turned(machine(machine_key).pokes, dict(chain), dict(chain_polls or {}), which, dict(at_idle or {}),
                           dict(at_polls or {}), at_calls and dict(at_calls), staged and dict(staged[1]), also_dropped,
                           *((budget,) if budget else ()))
    assert case.long_in(started, aes.AES_RLR) & aes_boot.BUS == SCREEN_MANAGER
    reference = aes_switch.Scheduled(left, None, delivered, idles, entered, aes_switch.RETURNED, started, calls,
                                     at_door_calls, polls, at_the_polls, answers, dispatches)
    return Turned(started, reference, handlers)


def turned(turn):
    """`turn` MADE BY THE ROM (once a process; the derivation kept): its `Turned`."""
    chain = turn.chain() if callable(turn.chain) else turn.chain
    staged = turn.staged and (turn.staged[0], _frozen(turn.staged[1]))
    return _turn_made(turn.machine, _frozen(chain), _frozen(turn.chain_polls), turn.which, _frozen(turn.at_idle),
                      _frozen(turn.at_polls), _frozen(turn.at_calls), turn.budget, staged, tuple(turn.also_dropped))


def start_of(turn):
    """THE MACHINE WHERE `turn` STARTS, before anything is staged over it — the megabyte at its arrival at the loop's
    top (the arrival's own derivation): what a staging is derived from."""
    chain = turn.chain() if callable(turn.chain) else turn.chain
    _no_frame, ram = _arrived_through(machine(turn.machine).pokes, dict(chain), dict(turn.chain_polls or {}),
                                      "AES_ROM_CTLMGR_LOOP", turn.which)
    return ram


def the_c_s_turn(turn):
    """...and THE CANDIDATE'S, from the same start, through the host's model with the door bound: its
    `aes_switch.Modelled`."""
    made = turned(turn)
    foreign = any(pd != SCREEN_MANAGER for pd in made.reference.entered)
    return aes_switch.modelled(CTLMGR_TURN, (), _as_pokes(made.started, "a turn's start"), made.reference, answered=False,
                               foreign=foreign, door=aes_switch.DoorUser(True),
                               left_out_beside=(its_stack(made.started), *its_trap_save_beside_the_snapshot_s(made.started),
                                                *turn.also_dropped))


# ---- THE STAGINGS A TURN MAY NAME (`Turn.staged`), each an ARGUMENT CLASS and said so ------------------------------------------
AES_GL_BPEND = aes.header_constants("evasync.h")["AES_GL_BPEND"]
FM = aes.header_constants("fmlib.h")
NQ_FRAME = struct.Struct(">hI")         # nq(key, queue): a word, a pointer


def the_click_count_staged_at(count):
    """THE MULTI-CLICK COUNT (gl_bpend) AT `count`. The machines at hand hold 1 where a turn starts (the desk's one
    double-click wait) or 2 (TWO_WAITERS: 3 at its idle, stepped once by the first turn — the ROM's own, and the
    turns over it need no staging); ctlmgr's step reads the word at 0, at 3 and above and as a signed word too, and
    under a menu and with no bar, where no machine brings it above 1: those are staged."""
    return (f"ARGUMENT CLASS: the multi-click count (gl_bpend) staged at {count}", {AES_GL_BPEND: struct.pack(">h", count)})


def a_key_in_its_own_queue(turn, key):
    """`key` IN THE SCREEN MANAGER'S OWN KEY QUEUE where `turn` starts — every byte the ROM's own nq stores, run over
    that machine. No machine AT ITS IDLE routes a key there: w_setactive hands the keyboard to the top window's
    owner at the head of every turn, and the desktop's is the desk.
    THE ONE ROM ROAD, TRIED AND NOT TAKEN: gem_main makes the screen manager the keyboard's first owner ($fda1e4),
    so a key typed between that store and the boot's first dispatch is nq'd to it and eaten in its first turn —
    SEEN (a key laid at the boot's stop at $fda1f0, the run continued: one key in PD1's queue at its first entry,
    none after its first turn), but only on a continuation WITHOUT the boot's device model, which the 95,000
    instructions between the two (six floppy calls) need. A faithful one is `aes_boot.booted` taking an interrupt
    at a stop: owed there. Until then this is the labelled staging."""
    start = _as_pokes(start_of(turn), "a turn's start")
    queue = case.long_in(make_image(start), SCREEN_MANAGER + aes.PD_CDA) + FM["CDA_KEY_QUEUE"]
    written, _image, _registers = aes_event.derived(addrs.AES_ROM_NQ, start, frame=NQ_FRAME.pack(key, queue))
    stored = {at: data for at, data in written.items() if at < RAM_BYTES}
    assert stored, "the ROM's nq stored nothing: the queue is full"
    return (f"ARGUMENT CLASS: the key {key:#06x} in the screen manager's own queue (the ROM's nq, run over the start)", stored)


# ---- THE ONCE-ONLY PART, at the screen manager's own first entry ---------------------------------------------------------------
FORK_SECONDS = 10


@functools.cache
def the_first_entry(accessories=False):
    """THE BOOT STOPPED WHERE THE SCREEN MANAGER FIRST RUNS — switchto's `rte` has just popped psetup's frame and the
    PC is ctlmgr's first instruction (`aes_boot.booted`'s `until`): the `Boot`, of the desk's capture or of the
    accessories'."""
    preinit, disk = ((aes_boot.accessory_preinit(), aes_boot.accessory_disk_of(QUIET, QUIET)) if accessories
                     else (aes_boot.preinit(), aes_boot.blank_disk()))
    boot = aes_boot.booted(preinit, disk, until=addrs.AES_ROM_CTLMGR)
    assert boot.registers["pc"] == addrs.AES_ROM_CTLMGR and boot.registers["sr"] & aes_boot.SR_SUPERVISOR
    return boot


def the_rom_begins(pokes):
    """The ROM's ctlmgr entered over `pokes` and STOPPED AT ITS LOOP'S TOP — the once-only part and no more:
    `(the image there, every byte it wrote)`."""
    final, writes, _registers = aes_event.stopped_at(make_image(pokes), addrs.AES_ROM_CTLMGR, THE_LOOP_S_TOP)
    return final, writes


def the_c_begins(pokes):
    """...and the candidate's (`aes_ctlmgr_begins`) in a fork over the same: `(its exit code, its stderr, its image)`."""
    over = mmap.mmap(-1, aes_switch.IMAGE_BYTES)
    over[:] = make_image(pokes)
    buf = (ctypes.c_uint8 * aes_switch.IMAGE_BYTES).from_buffer(over)
    returncode, stderr = aes_event.in_a_fork(aes_event.one_run_of(getattr(_lib, CTLMGR_BEGINS), (), buf, False), FORK_SECONDS)
    return returncode, stderr, bytes(over)


TurnHeld = namedtuple("TurnHeld", "made ran left_out")


def held_to_the_rom_s_turn(who, turn, handed_as=lambda calls: calls):
    """ONE TURN, BOTH SHORES, HELD (the Tier 1 of ctlmgr's loop): the C's turn ended where the ROM's did — as many
    idles and polls, every door call handed what the ROM's own call hands (in the ROM's order: the lock before the
    handlers and let go after them), each call answering and leaving what the ROM routine's does, the image the
    ROM's at every dispatch — and THE WHOLE IMAGE the ROM's where the turn ends, outside the model's own drops, the
    screen manager's stack and the machine's own trap save (each byte dropped only where the ROM's turn changed
    it; the second named only where the tree's own exclusion is not that frame) and the turn's own named
    windows (each byte REQUIRED to be one the ROM's turn changed). `handed_as`: what the C is expected to hand, as a
    reading of the ROM's calls — the identity, but for a turn whose C hands a declared divergence."""
    if turn.also_dropped:               # ...NEEDED, or refused: a window the turn passes without excuses a store for nothing
        try:
            held_to_the_rom_s_turn(who, turn._replace(also_dropped=()), handed_as)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"{who}: names windows of its own by nature, and is held without leaving any out")
    made, ran = turned(turn), the_c_s_turn(turn)
    reference = made.reference
    assert ran.returncode == 0, f"{who}: the ROM's turn ended at the loop's top; the C's fork ended {ran.returncode}:\n{ran.stderr}"
    assert (ran.idles, ran.polls) == (reference.idles, reference.polls), (
        f"{who}: the C's turn made {ran.idles} idle(s) and {ran.polls} poll(s), the ROM's {reference.idles} and {reference.polls}")
    assert ran.handed == list(handed_as(reference.calls)), (
        f"{who}: the door was handed {ran.handed}, the ROM's turn hands {list(reference.calls)}")
    named = frozenset(at for lo, hi, _why in turn.also_dropped for at in range(lo, hi))
    untouched = [f"{lo:#x}" for lo, hi, _why in turn.also_dropped if reference.memory[lo:hi] == reference.started[lo:hi]]
    assert not untouched, f"{who}: named by nature, and left as they were by the ROM's turn: the windows at {untouched}"
    by_nature = (its_stack(made.started), *its_trap_save_beside_the_snapshot_s(made.started))
    left_out = aes_switch.not_compared(reference, aes_switch.model_drops(SCREEN_MANAGER) + by_nature) | named
    differ = aes_event.differing(ran.image, make_image({0: reference.memory}), left_out)
    assert not differ, f"{who}: " + aes_event.describe_differences(who, ran.image, make_image({0: reference.memory}), differ)
    aes_event.vet_the_answers_handed_back(who, ran.answered, reference.answers)
    aes_event.vet_the_images_at_the_dispatcher(who, ran.dispatched, reference.dispatches)
    return TurnHeld(made, ran, left_out)


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
