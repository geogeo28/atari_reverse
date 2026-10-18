"""ctlmgr's OWN ROWS — THE SCREEN MANAGER WOKEN, FROM THE MACHINE'S IDLE TO ITS NEXT (FLIP 4: `src/aes/ctlmgr.c` bound).

ctlmgr (`$fe49d2`) is entered by no call and never returns: nothing of it is a call and its return. What it IS, on a
machine, is a process that sleeps in its main wait and is woken: by the button, by the mouse entering the bar's
rectangle, by both in one wake. So its row is that — ONE WAKE, WHOLE:

  * A MACHINE THE ROM BOOTED (`aes_gemctrl.machine`: the desk alone, or with the test accessories and their windows),
    standing at its idle; and, for our shore, THE SAME BOOT WITH THE SCREEN MANAGER OURS — the takeover machine
    (`aes_boot.desk_machine(ours=blob)` / `accessory_machine(..., ours=blob)`): our `aes_rom_ctlmgr` entered by the
    ROM's own switchto at the screen manager's first entry, parked in ITS OWN frames on the screen manager's REAL
    stack, by its own dispatcher. Nothing is laid over either machine.
  * WHAT A USER DOES, as the interrupts of each idle in turn (`chain`: the handlers' batteries' own vocabulary) —
    taken by the ROM's interrupt code on the ROM's run, and laid at the same idles of ours
    (`aes_switching.IdleToIdle`: relocated by who takes them).
  * BOTH SHORES RUN FROM THAT IDLE, through the ROM's dispatcher's loop where each machine stands, TO THE IDLE THE
    MACHINE REACHES WITH NOTHING LEFT TO DELIVER. Every turn of the screen manager on the way is OUR ctlmgr's on
    our shore — its loop, its handlers, its event layer, its dispatcher — and the ROM's on the ROM's; every turn of
    the desk or of an accessory is the ROM's own code on both (a window, equal to the cycle).

WHAT THE ROW HOLDS (`bench/tier3.py`, `idle_to_idle_on`): the same processes entered in the same order; the image at
every stop of the dispatcher's watch; the megabyte where both runs end, byte for byte outside the classes the row
NAMES (`Woken.differs`: each needed, or the row is refused) and with every code address of the registry mapped; the
streams; and WHO RAN — not one cycle of our run at a PC of the ROM's ctlmgr, nor anywhere in the AES's ROM outside
the windows of the ROM's processes. ITS PRICE is the screen manager's turns: our build's own cycles in them against
the ROM's ctlmgr's.

Tier 1 of ctlmgr is ONE TURN OF ITS LOOP on the host (`aes_gemctrl.Turn`, `test_aes_gemctrl.py`: every arm, the
labelled argument classes among them); these rows are what a blob adds — the real entry, the real stack, the real
switch.
"""
import functools
import re
from collections import namedtuple

import derived
from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_boot
import aes_desk
import aes_event
import aes_gemctrl as gc
import aes_switch
import case
import routines
import vdi_helpers

ENTRY, SYMBOL = addrs.AES_ROM_CTLMGR, aes_boot.ENTRY_SYMBOL
THE_ROM_S_BODY = (addrs.AES_ROM_CTLMGR, addrs.AES_ROM_ICTLMGR)     # the ROM's ctlmgr, `$fe49d2..$fe4a6a`
FUNCTION = f"AES ctlmgr (${ENTRY:x})"
# THE CLASSES A WOKEN ROW MAY NAME as differing by nature between the two machines where its two runs end — each
# located from the machines' own pointers by `bench/tier3.py`, each REQUIRED TO DIFFER on the row that names it:
THE_DISPATCHER_S_STACK = "the dispatcher's stack: two builds' frames (ours, where our screen manager parked last)"
ITS_SAVED_CONTEXT = "the screen manager's saved context in its UDA (each ctlmgr's own frames' addresses)"
ITS_STACK = "the screen manager's own stack (each ctlmgr's own frames)"
THE_MASK_WORD = "the Line-F mask word (rewritten by every masked return of the ROM's code, by no C)"
# (...ITS TEN SAVED REGISTERS ALONE — `tier3.the_trap_save_s_registers`: the saved PC and SR above them say which
# trap was taken last and from what mask, and are compared)
THE_TRAP_SAVE = "the BIOS's register-save frame under the machine's savptr (the keyboard poll's caller's registers)"
# ...and THE DECLARED DIVERGENCE (ruling W2-R2; `aes/gemctrl.h`'s HCTL_STALE_WORD): WM_TOPPED's words 4..7 are locals
# the ROM's hctl_window never sets — on the screen manager's real stack the residue of its last wait (the high half
# of an address of the AES's text, the low half of one inside its own stack) — and four zeroes in our C. Named BY THE
# ROW THAT SENDS THE MESSAGE: the eight bytes wherever the write carried them (the manager's own buffer, the owner's
# pipe, the buffer it reads into), and nothing else of the message.
THE_TOPPED_WORDS = "WM_TOPPED's words 4..7: locals the ROM's hctl_window never sets (its stack's residue), four zeroes in the C"
CLASSES = (THE_DISPATCHER_S_STACK, ITS_SAVED_CONTEXT, ITS_STACK, THE_MASK_WORD, THE_TRAP_SAVE, THE_TOPPED_WORDS)
STALE_WORDS_AT = (aes.AES_CT_MESSAGE + aes.AP_MSG_WORDS + aes.WORD_BYTES, aes.AES_CT_MESSAGE + aes.AP_MSG_BYTES)
WM_TOPPED = gc.MESSAGES["WM_TOPPED"]


def the_topped_words_places(memory):
    """WHERE WM_TOPPED'S FOUR STALE WORDS LIE over the ROM's `memory` once its ct_msgup has built the message: its own
    buffer's last eight bytes and every other run of those eight bytes outside the screen manager's stack (the
    owner's pipe, the buffer it read them into) — `[(lo, hi)]`; none while the buffer holds no WM_TOPPED, or holds
    four zeroes there. FOUND BY THE BYTES, not by a pointer: the buffer the owner read into is named by nothing on
    the machine once its read has returned (its QPB was a local of a frame long popped) — the battery holds that the
    places are THREE on the row that sends the message, one of them inside the owner's pipe by the machine's own
    pointer."""
    lo, hi = STALE_WORDS_AT
    residue = bytes(memory[lo:hi])
    if case.word_in(memory, aes.AES_CT_MESSAGE) != WM_TOPPED or not any(residue):
        return []
    stack_lo, stack_hi, _why = gc.its_stack(memory)
    ram, places, at = bytes(memory[:addrs.ST_RAM_BYTES]), [], -1
    while (at := ram.find(residue, at + 1)) >= 0:
        if not stack_lo <= at < stack_hi:
            places.append((at, at + len(residue)))
    return places
# `label`: the row's case; `machine`: a key of `aes_gemctrl.MACHINES`; `chain`: `{idle: (interrupt, ...)}` from the
# machine's own idle on; `at_polls`: `{poll: (interrupt, ...)}`; `differs`: the classes the two machines differ in
# where the runs end; `budget`: the ROM run's own, declared, for one past a derivation's default.
Woken = namedtuple("Woken", "label machine chain differs at_polls budget", defaults=(None, None))
Made = namedtuple("Made", "switches entered handlers")
Made.__doc__ = """A woken row's ROM run, derived: what it is taken through (`aes_event.Switches`, no process its own),
the processes its dispatcher enters in order, and the handlers the ROM's ctlmgr called in it, with their frames."""
ROWS = {}                               # `{the row's registered name: its Woken}` — what `bench/tier3.py` prices


class _KeepsItsDeliveries:
    """What a watch of the ROM's dispatcher's run keeps of each delivery it takes (a run a watch ends hands back no
    ledger of its own): what it FOUND and what it WROTE, by where it was due (`delivered`), and at a poll what the
    idle's own tests read there (`stood`). `taken()`: the two as `aes_event.Switches` holds them."""

    def _keeping(self):
        self.delivered, self.stood = {}, {}

    def _taking(self, key, interrupt):
        memory = self._memory
        if key[0] == aes_switch.AT_A_POLL:
            self.stood[key[1]] = aes_switch.what_idle_tests(memory)

        def taken(image):
            wrote = {}
            for each in interrupt if isinstance(interrupt, tuple) else (interrupt,):
                wrote = case.merge_pokes(wrote, each(image))
            self.delivered[key] = ({at: bytes(memory[at:at + len(data)]) for at, data in wrote.items()}, wrote)
            return wrote
        return key, taken

    def taken(self):
        return aes_switch.taken_at_the_idles(self.delivered), aes_switch.taken_at_the_polls(self.delivered, self.stood)


class _IdleToIdle(_KeepsItsDeliveries):
    """The watch of the ROM's dispatcher run from an idle machine through a chain (`aes_event.interrupting`'s) to
    THE IDLE IT REACHES WITH NOTHING LEFT TO DELIVER, where the run ENDS (`aes_event.Ended`): the polls and idles
    counted as `aes_switch.scheduled` counts them, what each delivery found and wrote kept (a run a watch ends hands
    back no ledger of its own), the processes entered, the screen manager's handlers called."""

    def __init__(self, memory, at_idle, at_polls):
        self._memory, self.at_idle, self.at_polls = memory, dict(at_idle), dict(at_polls or {})
        self.first = aes_switch.EVERY_STOP | frozenset(gc.THE_LOOP_S_HANDLERS)
        self.polls, self.idles, self.entered, self.handlers = 0, 0, [], []
        self._due = False
        self._keeping()

    def due(self, _watch, pc):
        if pc != addrs.AES_ROM_IDLE_LOOP:
            return None
        if not aes_switch.waits_for_an_interrupt(self._memory):
            interrupt = self.at_polls.pop(self.polls, None)
            return self._taking((aes_switch.AT_A_POLL, self.polls), interrupt) if interrupt is not None else None
        interrupt = self.at_idle.pop(self.idles, None)
        self._due = interrupt is not None
        return self._taking((aes_switch.AT_AN_IDLE, self.idles), interrupt) if self._due else None

    def stopped(self, pc, sp, memory):
        if pc in gc.THE_LOOP_S_HANDLERS:
            if case.long_in(memory, sp) & aes_boot.BUS in gc.CTLMGR_S_RETURNS:
                frame, at = gc.FRAMES[gc.THE_LOOP_S_HANDLERS[pc]], sp + aes.LONG_BYTES
                self.handlers.append((gc.THE_LOOP_S_HANDLERS[pc], frame.unpack(bytes(memory[at:at + frame.size]))))
            return (self.first - {pc}) | aes_switch.EVERY_STOP
        stops = aes_switch.dispatcher_stop(pc, memory, self.entered.append, self._an_idle, delivered=self._due,
                                           polls=self._a_poll)
        return stops | (frozenset(gc.THE_LOOP_S_HANDLERS) - {pc})

    def _a_poll(self):
        self.polls += 1

    def _an_idle(self):
        if not self._due:
            assert not self.at_idle, (
                f"the machine idles (idle {self.idles}) with nothing due there and deliveries named at the later idles "
                f"{sorted(self.at_idle)}: a chain's idles are numbered as the run makes them")
            raise aes_event.Ended
        self._due, self.idles = False, self.idles + 1


@derived.kept
def _woken(pokes, chain, at_polls, budget=None):
    """THE DERIVATION (ROM-only, kept by content): the ROM's dispatcher run over the idle machine `pokes`, the
    interrupts of `chain` taken at its idles and of `at_polls` at its polls, to the idle it reaches with nothing left
    to deliver: `(the deliveries at the idles, how many, the polls made, the deliveries at polls, the processes
    entered, the handlers ctlmgr called)`. REFUSED BY NAME: a chain the run does not take whole."""
    memory = make_image(pokes)
    watch = _IdleToIdle(memory, chain, at_polls)
    try:
        aes_event.interrupting(memory, addrs.AES_ROM_DISP_LOOP, watch, watch.due, budget)
    except aes_event.Ended:
        pass
    else:
        raise AssertionError("the dispatcher's loop returned: the machine never idled")
    assert not watch.at_polls, f"the run made {watch.polls} poll(s): nothing was delivered at {sorted(watch.at_polls)}"
    at_idles, at_the_polls = watch.taken()
    return at_idles, watch.idles, watch.polls, at_the_polls, tuple(watch.entered), tuple(watch.handlers)


# ---- THE HANDLERS' OWN CASES, EACH SHORE'S OWN ctlmgr ARRIVING AT ITS OWN HANDLER (slice E, wave 2's close) -------------------
# A case of the screen manager's handlers is AN ARRIVAL (`aes_gemctrl.Arrival`): a dispatcher's run from a booted
# machine's idle through a chain to the handler's first instruction. ITS TIER 1 starts there on the ROM's run's
# machine (`test_aes_gemctrl.py`: the host's C against the ROM's routine). ITS TIER 3 — the row the table prices and
# both blobs are pinned at — IS MEASURED WHERE EACH BUILD REALLY RUNS THE HANDLER: the ROM's ctlmgr arriving at the
# ROM's handler on the ROM-booted machine, OUR ctlmgr (and our handlers above the one arrived at) arriving at OUR
# core of it on the takeover machine of the same boot — each ON THE SCREEN MANAGER'S REAL STACK — and each run taken
# ON THROUGH THE HANDLER TO ITS RETURN: the row is that slice (`tier3.at_its_arrival_on`, which holds the frame, the
# image at every stop and where the handler returns, and who ran). `arriving` derives the ROM's run to the arrival
# with what each delivery found and wrote (`aes_gemctrl.at` keeps the frame and the machine alone).
Arriving = namedtuple("Arriving", "routine which switches entered words")
Arriving.__doc__ = """An arrival's ROM run, derived: the handler (its `addrs` name) and which of its arrivals, what the
run is taken through up to there (`aes_event.Switches`, no process its own), the processes entered, and the words of
the frame its caller pushed."""


class _ToItsArrival(_KeepsItsDeliveries, gc.ToAnArrival):
    """THE HANDLERS' OWN WATCH OF AN ARRIVAL (`aes_gemctrl.ToAnArrival`: the same run, ended at the same arrival, an
    earlier one passed the same way), KEEPING what each delivery found and wrote."""

    def __init__(self, memory, at_idle, at_polls, entry, which):
        super().__init__(memory, at_idle, at_polls, entry, which)
        self._keeping()


@derived.kept
def _arriving(pokes, chain, at_polls, routine, which, budget=None):
    """THE DERIVATION (ROM-only, kept by content): `_woken`'s run, ended at the `which`-th arrival at `addrs.<routine>`:
    `(the deliveries at the idles, the idles made, the polls made, the deliveries at polls, the processes entered,
    the frame's words)`. REFUSED BY NAME: an arrival made with a delivery still due."""
    memory = make_image(pokes)
    watch = _ToItsArrival(memory, chain, at_polls, getattr(addrs, routine), which)
    try:
        aes_event.interrupting(memory, addrs.AES_ROM_DISP_LOOP, watch, watch.due, budget)
    except aes_event.Ended:
        pass
    assert watch.arrived is not None, f"the dispatcher's loop returned before any arrival at {routine}"
    assert not watch.at_idle and not watch.at_polls, f"the ROM's ctlmgr called {routine} with deliveries still due"
    at_idles, at_the_polls = watch.taken()
    words, _ram = watch.arrived
    return at_idles, watch.idles, watch.polls, at_the_polls, tuple(watch.entered), words


def arriving(arrival):
    """`arrival` (an `aes_gemctrl.Arrival` made by a dispatcher's run: its chain is one), DERIVED WITH ITS DELIVERIES:
    its `Arriving` — the frame HELD to be the one `aes_gemctrl.at` keeps."""
    chain = arrival.chain() if callable(arrival.chain) else arrival.chain
    pokes = gc.at_its_idle(arrival.machine)
    at_idles, idles, polls, at_the_polls, entered, words = _arriving(
        pokes, dict(chain), dict(arrival.at_polls or {}), arrival.routine, arrival.which, *((arrival.budget,) if arrival.budget else ()))
    assert words == gc.at(arrival).arguments, f"{arrival.routine}: the frame at the arrival is not the one its case is run over"
    return Arriving(arrival.routine, arrival.which, aes_event.Switches(at_idles, idles, None, {}, at_the_polls, polls), entered, words)


# A HANDLER'S CASE AS IT IS MEASURED AT ITS ARRIVAL (`tier3.at_its_arrival_on`). `arrival`: the case's own (its
# `routine` the handler); `row`: the handler's own run as the row that switches it is (`aes_switching.SwitchingRow`:
# what is delivered at ITS idles, polls and door calls, numbered from the handler's entry) — None for a handler that
# returns without a switch; `differs`: THE CLASSES the two machines differ in where the handler returns (`CLASSES`,
# as a woken row's: each must differ, and nothing differs outside them and the row's own named windows — its
# `also_dropped`); `at_stops_only`: `(lo, hi, why)` windows that differ at a stop on the way and are equal again
# where the handler returns (`aes_switching.companion`'s kind).
Handled = namedtuple("Handled", "arrival differs row at_stops_only", defaults=(None, ()))
# ...AND WHAT A HANDLER THAT RETURNS WITHOUT A SWITCH IS TAKEN THROUGH from its entry on: nothing, in its own process.
NO_SWITCH = aes_event.Switches({}, 0, gc.SCREEN_MANAGER, {}, {}, 0)
THE_HANDLERS = (gc.CT_MSGUP, gc.HCTL_WINDOW, gc.HCTL_BUTTON, gc.HCTL_RECT)      # in the ROM's order: each body ends at the next
THE_HANDLERS_END = addrs.AES_ROM_CT_CHGOWN      # ...and the last at the routine after it (ct_chgown, before ctlmgr): `names.txt`
HANDLED = {}                            # `{a registered row's name: its Handled}` — the rows `bench/tier3.py` measures so


def the_rom_s_body_of(routine):
    """`(lo, hi)`: the ROM's own text of the handler `routine` (its `addrs` name) — from its entry to the next's."""
    entries = sorted(getattr(addrs, name) for name in THE_HANDLERS) + [THE_HANDLERS_END]
    lo = getattr(addrs, routine)
    return lo, entries[entries.index(lo) + 1]


def taken_through(handled):
    """What the handler's own run is taken through from its entry on (`aes_event.Switches`): the row's, or nothing."""
    import aes_switching                # (the registrar: it imports the batteries' vocabulary, as `aes_event` says)
    return aes_switching.settled(handled.row).switches if handled.row else NO_SWITCH


def register_handled(name, handled):
    """ONE REGISTERED ROW OF A HANDLER — `name`, as its battery registered it — DECLARED MEASURED AT ITS ARRIVAL:
    `bench/tier3.py` reads `HANDLED` for the table, `aes_switching.measured_on` for a named blob. Refused by name: an
    arrival that is no dispatcher's (the boot's own: no chain to run from an idle), a class that is none."""
    assert handled.arrival.chain is not None, f"{name}: the boot's own arrival is made by no run from a machine's idle"
    assert set(handled.differs) <= set(CLASSES) and name not in HANDLED, name
    HANDLED[name] = handled
    return handled


def _frozen(schedule):
    return {} if schedule is None else dict(schedule)


@functools.cache
def _made(machine, chain, at_polls, budget):
    pokes = gc.at_its_idle(machine)
    at_idles, idles, polls, at_the_polls, entered, handlers = _woken(pokes, dict(chain), dict(at_polls),
                                                                     *((budget,) if budget else ()))
    return Made(aes_event.Switches(at_idles, idles, None, {}, at_the_polls, polls), entered, handlers)


def made(woken):
    """`woken`'s ROM run, DERIVED (once a process; kept): its `Made`."""
    return _made(woken.machine, tuple(sorted(_frozen(woken.chain).items())), tuple(sorted(_frozen(woken.at_polls).items())),
                 woken.budget)


def row_name(woken):
    return f"{SYMBOL}, {woken.label}"


def the_rom_s_machine(woken):
    """The megabyte both shores' runs start from on the ROM's shore: the booted machine, at its idle."""
    return gc.machine(woken.machine).ram


# WHICH DISPATCHER A MACHINE IDLES IN: the one its LAST process parked through. The ROM's boot and a takeover boot
# with no door end in the ROM's (the desk parks last through it, or an accessory the ROM's trap handler parked);
# BEHIND OUR DOOR an accessory that parks last parks through OURS — the door machine then stands in our idle where
# the ROM-booted one stands in the ROM's, and the two differ besides in the two classes `aes_boot.by_nature` names
# for that (the Line-F mask word; the BIOS's last register-save frame, the idle's own keyboard poll's). THE DESK'S
# OWN MACHINE BEHIND THE DOOR idles in the ROM's all the same: it loads no program, and the desk parks last.
TWO_IDLES = (aes_boot.TRAP_SAVE_FRAME, aes_boot.LINE_F_MASK)

# THE BOUND DESK (band 6 slice B0, N2; the orchestrator's ruling R5: classes BY NATURE). Since the door's ninth part
# (`aes_event.LINEF_TABLE_SLOT`) the ROM's desk on a takeover machine calls OUR AES through our table from the
# takeover on, and PARKS THROUGH OUR DISPATCHER (its machine, the desk's own among them, idles in OURS: both
# `TWO_IDLES` apply). So PD0 is a process of our event layer as a program the door took is, and differs from the
# ROM-booted machine in THAT PROCESS'S OWN CLASSES (`aes_boot`'s per-program three: its saved context, its stack from its
# UDA's state block to its top — two builds' frames under the desk's —, a wait's parameter that is an address in that
# stack) — and in TWO OF GEMDOS'S, where the desk's last `trap #1` left OUR build's state:
#   * GEMDOS'S OWN STACK below where its entry parks A7: dead between two traps, it holds the return address of the
#     trap's caller — the ROM's glue on its shore, OUR build's (`aes_dos_alloc`) on ours;
#   * p_run's REGISTER-SAVE AREA (the AES's basepage): the trapping caller's registers and the address of its frame —
#     a place in PD0's stack, two builds' depths.
# Each located from the machine's own pointers, and the two of GEMDOS's as `vdi_helpers.GEMDOS_DOOR_WINDOWS` names
# them. Named PER COMPARISON beside `aes_boot.compared`'s (a takeover machine's comparison is made there), and each
# REFUSED where the machines do not differ in it — a class nobody needs is none.
THE_DESK_S_NAME = b"the desk"
THE_GEMDOS_STACK = "GEMDOS's own stack: the desk's last trap's caller, a return into the blob"
THE_GEMDOS_SAVE_AREA = "p_run's register-save area: the desk's last trap's registers and frame, in PD0's stack"
_Process = namedtuple("_Process", "name pd stack")


def the_desk_s_stack(machine):
    """`(lo, top)`: PD0's stack on `machine` — from its UDA's state block (through the PD's own pointer) to UDA0's top,
    where gem_entry starts it (`AES_UDA1`: the screen manager's UDA follows)."""
    return (machine.long(aes.SHELL_PD + aes.PD_UDA) & aes_boot.BUS) + aes.UDA_STATE_BYTES, aes.AES_UDA1


# THE DESK'S LIVE FRAMES (the fix pass of slice B0, reviewer A's F1). The stack class above is PD0's WHOLE stack: it
# cannot be narrowed to the frames under the desk's lowest ROM frame, by a measured reason. On all four machines 56
# bytes ABOVE that frame differ at the takeover — dead trap frames of each build's AES (SR `$2300` and a return into
# the ROM's GEMDOS glue, `$fe3bce` / `$fe3bba`, against our `aes_dos_alloc`'s) in locals the desk's frames allocate and
# do not write: deskmain's (`link a6,#-72`) and desk_evnt_multi's six answer words (`$fdded8`). And they TRAVEL: ev_multi
# writes only the words of the events that occurred, and desk_evnt_multi copies all six out to deskmain's locals after
# the yield, so a row's run carries each build's dead bytes into deskmain's frame (measured: the menu rows, `$a34e..`).
# So the live frames are held otherwise: OUR SHORE'S RUN of a row is entered with them laid as THE ROM'S
# (`lay_the_desk_s_live_frames`, a labelled staging: the dead bytes of the takeover the ROM's, every frame link and
# return held equal first), and where the two runs END they are compared byte for byte (`tier3.vet_the_desk_s_live_frames`)
# — what our AES writes into the desk's frames (an answer through a pointer the desk hands it) is compared there.
# THE DESK'S TEXT IS ITS ROM TEXT LESS ITS FLIPPED ROUTINES' (band 6 slice H2): a desk routine whose Line-F entry is
# ours runs OUR code on our shore, and its frame there is our build's (GCC's, no `link a6`), as the AES's under it is.
# So the desk's own frames begin at the first frame whose return lies in desk text STILL THE ROM'S on the blob measured:
# under a flipped binding (evnt_multi's, where the desk parks) they begin at the binding's caller's call — the
# binding's own frame, the ROM's on its shore and ours on ours, is below them and differs by nature.
def the_desk_s_text(blob=None):
    """`((lo, hi), ...)`: THE DESK'S ROM TEXT STILL THE ROM'S on a machine of `blob` (ours by default) — units A-L and
    the utility text, less every flipped routine's (`aes_desk.less_the_flipped`)."""
    return aes_desk.less_the_flipped((aes_desk.DESK_TEXT, aes_desk.UTILITY_TEXT), blob)


def _the_desk_s_frames(memory, blob=None):
    """The A6 of every frame of THE DESK'S OWN, lowest first, in PD0's stack over a ROM-shore `memory` where the desk
    is parked, and UDA0's top. Walked up the ROM's frame chain (Alcyon's `link a6`: the caller's A6 at `0(a6)`, the
    return at `4(a6)`) from the A6 savestate keeps in PD0's UDA: the desk's frames begin at the first whose return
    lies in the desk's ROM text still the ROM's on `blob` (`the_desk_s_text`). REFUSED BY NAME where the chain leaves
    the stack before it reaches one: no ROM frame of the desk's is parked there."""
    lo, top = (case.long_in(memory, aes.SHELL_PD + aes.PD_UDA) & aes_boot.BUS) + aes.UDA_STATE_BYTES, aes.AES_UDA1
    frame, frames = case.long_in(memory, lo - aes.UDA_STATE_BYTES + aes.UDA_A6) & aes_boot.BUS, []
    its_text = the_desk_s_text(blob)
    while lo <= frame < top - aes.LONG_BYTES:
        returns_to = case.long_in(memory, frame + aes.LONG_BYTES) & aes_boot.BUS
        if frames or any(text_lo <= returns_to < text_hi for text_lo, text_hi in its_text):
            frames.append(frame)
        frame = case.long_in(memory, frame) & aes_boot.BUS
    if not frames:
        raise aes_boot.Refused(f"PD0's frame chain leaves its stack [{lo:#x}, {top:#x}) at {frame:#x} before a return "
                               f"into the desk's text: the desk is not parked in a ROM frame of its own")
    return frames, top


def the_desk_s_live_frames(memory, blob=None):
    """`(lo, top)`: THE DESK'S OWN FRAMES on a machine of `blob` (`_the_desk_s_frames`) — from the return slot of the
    call it is parked under to UDA0's top."""
    frames, top = _the_desk_s_frames(memory, blob)
    return frames[0] + aes.LONG_BYTES, top


def lay_the_desk_s_live_frames(ours, rom, blob=None):
    """OUR SHORE'S MACHINE `ours` (an image, in place) GIVEN THE ROM'S BYTES OVER THE DESK'S LIVE FRAMES of the ROM's
    machine `rom` it starts beside (the note above), on `blob` — A LABELLED STAGING, laid where a row's two runs are
    entered. What it may lay is DEAD BYTES alone: REFUSED BY NAME where a frame link or a return of the desk's chain
    differs (the desk would stand in other frames). The count of bytes laid."""
    frames, top = _the_desk_s_frames(rom, blob)
    lo = frames[0] + aes.LONG_BYTES     # (the lowest frame's own link is its callee's: the AES's, under the desk's)
    links = [(f"{at:#x}", case.long_in(rom, at), case.long_in(ours, at)) for frame in frames
             for at in (frame, frame + aes.LONG_BYTES) if lo <= at < top and case.long_in(rom, at) != case.long_in(ours, at)]
    assert not links, f"the desk's frame chain on our machine is not the ROM's: {links[:4]} (the ROM's, ours)"
    laid = sum(1 for at in range(lo, top) if rom[at] != ours[at])
    ours[lo:top] = bytes(rom[lo:top])
    return laid


# THE ROM'S evnt_multi BINDING'S RESIDUE (band 6 slice H2) — A CLASS BY NATURE of the desk's live frames, read off the
# ROM's run. desk_evnt_multi (`$fdded8`) hands ev_multi six answer words in its own frame and copies ALL SIX out through
# its caller's six pointers after its yield; before it parks it stores nothing of them (by reading: its packed button
# and timer longwords and the argument slot alone, `the_binding_s_copies`), and ev_multi answers only the words of the
# events that came (the key's under MU_KEYBD, the clicks' under MU_BUTTON). A word no store of the run reached before
# the copy is its frame's RESIDUE — whatever the last frame at that depth left there — and it travels into deskmain's
# frame. Under a FLIPPED binding the residue is each build's own (the ROM's binding's frame on its shore, our C's on
# ours): such a word may differ where the runs end, and nothing else may. Each word is READ OFF EACH RUN where its
# binding copies it out (`ResidueCopies`: the run's write ledger at that instant) — the ROM's binding's copy-out on
# either shore while it is the ROM's, OUR C binding's (`our_copying`) on ours once flipped — never a listed range; and
# a word is excused only where BOTH runs copied residue there and each run's end still holds the word it copied
# (`residue_where_the_runs_end`, the RH2 review's narrowing): a word our C copies from an answer, or another word than
# the one the ROM's copies there, is compared by memory.
EVNT_MULTI_BINDING_NAME = "AES_ROM_DESK_EVNT_MULTI"
EVNT_MULTI_BINDING = getattr(addrs, EVNT_MULTI_BINDING_NAME)
_LINK = re.compile(r"^linkw %fp,#-(\d+)$")
_OUT_POINTER = re.compile(r"^moveal %fp@\((\d+)\),%a0$")
_ANSWER_COPIED = re.compile(r"^movew %fp@\((-\d+)\),%a0@$")
BindingCopies = namedtuple("BindingCopies", "frame_bytes at copies")
BindingCopies.__doc__ = """The ROM's evnt_multi binding's copy-out, BY READING its text: its frame's bytes (its `link`),
`at` — the instruction after its yield (`dsptch`), where the copy-out begins — and `copies`: `((the answer word's
offset from A6, the out pointer's), ...)` in the order it copies them."""


def the_binding_s_listing():
    """`((address, length, text, the routine a Line-F call names or None), ...)`: the ROM's evnt_multi binding, from
    its entry to the next routine of the inventory."""
    import aes_deskbind                 # (the GEM text's listing; that module imports the switching registrar)
    starts = aes_desk.inventoried()
    end, listing, at = starts[starts.index(EVNT_MULTI_BINDING) + 1], [], EVNT_MULTI_BINDING
    while at < end:
        length, text = aes_deskbind.listed_at(at)
        listing.append((at, length, text, None if text else aes.line_f_target(case.word_in(BASE_IMAGE, at))))
        at += length
    return tuple(listing)


@functools.cache
def the_binding_s_copies():
    """The binding's `BindingCopies`, read off `the_binding_s_listing` — REFUSED BY NAME where its text is not the
    shape read: a `link`, one yield, then out-pointer / answer-word pairs."""
    listing = the_binding_s_listing()
    linked = _LINK.match(listing[0][2])
    assert linked, f"${EVNT_MULTI_BINDING:x}: the binding does not open with a `link`: {listing[0][2]!r}"
    yielding = [index for index, (_at, _length, _text, called) in enumerate(listing) if called == addrs.AES_ROM_DSPTCH]
    assert len(yielding) == 1, f"${EVNT_MULTI_BINDING:x}: the binding yields {len(yielding)} times"
    after = listing[yielding[0] + 1:]
    copies = []
    for (_at, _length, out, _called), (_at2, _length2, answer, _called2) in zip(after[0::2], after[1::2]):
        pointer, word = _OUT_POINTER.match(out), _ANSWER_COPIED.match(answer)
        if not (pointer and word):
            break
        copies.append((int(word.group(1)), int(pointer.group(1))))
    return BindingCopies(int(linked.group(1)), after[0][0], tuple(copies))


def the_rom_s_copying():
    """`(at, ((the answer word's offset from SP at `at`, the out pointer's), ...))`: the ROM's binding's copy-out
    (`the_binding_s_copies`), offset from its yield's stack pointer — the `link`'s, every argument popped."""
    reading = the_binding_s_copies()
    return reading.at, tuple((reading.frame_bytes + answer, reading.frame_bytes + out) for answer, out in reading.copies)


# OUR C BINDING'S COPY-OUT, BY READING OUR BUILD'S LISTING: after its call of aes_dsptch it loads each out pointer off
# SP (`movel %sp@(N),%dX`) and copies an answer word of its frame through it (`movew %fp@(X,%sp:l),…` — `%fp` holds
# `image`, the machine's base). Only the FIRST pointer and the FIRST answer word are read; the rest follow BY ITS
# SIGNATURE (`aes_deskbind.SIGNATURES`: six consecutive long pointer arguments; six consecutive answer words, the ROM's).
# Read off every copy, a C that copies another word than the i-th through the i-th pointer would be refused by its
# codegen; read so, it is caught BY MEMORY — its end does not hold the word observed copied there.
OUR_BINDING = routines.core_symbol(EVNT_MULTI_BINDING_NAME)
OUR_DSPTCH = routines.core_symbol("AES_ROM_DSPTCH")
_OUR_OUT_POINTER = re.compile(r"^movea?l %sp@\((\d+)\),%[ad]\d$")
_OUR_ANSWER_COPIED = re.compile(r"^movew %fp@\(([0-9a-f]+),%sp:l\),")


def _first_read(after, pattern, base):
    """The first operand `pattern` reads in `after` (`[(address, text)]`), in `base` — REFUSED BY NAME where none does."""
    read = next((found for _at, text in after if (found := pattern.match(text))), None)
    assert read, f"{OUR_BINDING}: no `{pattern.pattern}` after its call of {OUR_DSPTCH}: its copy-out is not the shape read"
    return int(read.group(1), base)


@functools.cache
def our_copying(elf):
    """`(at, pairs)` as `the_rom_s_copying`, for OUR C binding on the blob `elf` (the note above): `at` the instruction
    after its call of aes_dsptch — REFUSED BY NAME where it calls it other than once."""
    body = aes_switch.listed_functions(elf)[OUR_BINDING]
    yielding = [index for index, (_at, text) in enumerate(body) if text.endswith(f"<{OUR_DSPTCH}>")]
    assert len(yielding) == 1, f"{OUR_BINDING}: it calls {OUR_DSPTCH} {len(yielding)} times"
    after = body[yielding[0] + 1:]
    pointer, answer = _first_read(after, _OUR_OUT_POINTER, 10), _first_read(after, _OUR_ANSWER_COPIED, 16)
    return after[0][0], tuple((answer + index * aes.WORD_BYTES, pointer + index * aes.LONG_BYTES)
                              for index in range(len(the_binding_s_copies().copies)))


class ResidueCopies:
    """WHAT ONE RUN'S COPIES-OUT OF AN evnt_multi BINDING CARRIED, at each of `copyings` (`(at, pairs)` each: the ROM's
    binding's, `the_rom_s_copying`, by default; on our shore ours too, `our_copying` — whichever its run reaches):
    `observing` — the stops to give its watch (`aes_switching.Switching`'s) — and `copied`: `{an out word's address:
    (the word copied there, was it RESIDUE)}`, RESIDUE where no store of the run so far (`ledger()`: the emulator's
    write ledger, `({address: byte}, saturated)`) reached ANY byte of the answer word. A saturated ledger is refused by
    name: what the run stored is then not known."""

    def __init__(self, ledger, *copyings):
        self._ledger, self.copied = ledger, {}
        self.observing = {at: functools.partial(self._copied_out, pairs) for at, pairs in (copyings or (the_rom_s_copying(),))}

    def _copied_out(self, pairs, memory, sp):
        stored, saturated = self._ledger()
        assert not saturated, "the run's write ledger saturated before an evnt_multi binding's copy-out: its residue is not known"
        for answer, out in pairs:
            word = range(sp + answer, sp + answer + aes.WORD_BYTES)
            self.copied[case.long_in(memory, sp + out) & aes_boot.BUS] = (bytes(memory[word.start:word.stop]),
                                                                        not any(at in stored for at in word))


def residue_where_the_runs_end(its_memory, the_rom_s, ours, our_memory):
    """THE BYTES OF THE DESK'S LIVE FRAMES THAT MAY DIFFER BY NATURE where a row's two runs end (`ResidueCopies` of each
    shore): each out word BOTH runs copied out of their binding's RESIDUE, where each run's end still holds the word it
    copied (`its_memory`, `our_memory`). A frozenset of addresses."""
    excused = set()
    for to, (word, residue) in the_rom_s.copied.items():
        our_word, our_residue = ours.copied.get(to, (None, False))
        if (residue and our_residue and bytes(its_memory[to:to + aes.WORD_BYTES]) == word
                and bytes(our_memory[to:to + aes.WORD_BYTES]) == our_word):
            excused.update(range(to, to + aes.WORD_BYTES))
    return frozenset(excused)


def the_bound_desk_s_gemdos_windows(memory):
    """GEMDOS's two windows of the bound desk (above) over `memory`, as `(lo, hi, why)`: its own stack, and p_run's
    register-save area (through the machine's own p_run)."""
    basepage = case.long_in(memory, addrs.GEMDOS_P_RUN) & aes_boot.BUS
    (stack_lo, stack_hi, _why), = (window for window in vdi_helpers.GEMDOS_DOOR_WINDOWS
                                   if window[1] == addrs.GEMDOS_SUPERVISOR_STACK)
    return ((stack_lo, stack_hi, THE_GEMDOS_STACK),
            (basepage + addrs.BASEPAGE_SAVED_D0, basepage + addrs.BASEPAGE_SAVED_FRAME + aes.LONG_BYTES, THE_GEMDOS_SAVE_AREA))


def the_bound_desk_s_classes(rom, ours):
    """`{class: (lo, hi)}` the takeover machine `ours` differs from the ROM-booted `rom` in BECAUSE ITS DESK IS BOUND."""
    desk = _Process(THE_DESK_S_NAME, aes.SHELL_PD, the_desk_s_stack(ours))
    assert ours.long(addrs.GEMDOS_P_RUN) == rom.long(addrs.GEMDOS_P_RUN), "the two machines run two GEMDOS processes"
    return {**aes_boot._of_a_program(rom, ours, desk),
            **{why: (lo, hi) for lo, hi, why in the_bound_desk_s_gemdos_windows(ours.ram)}}


def outside_the_bound_desk_s_classes(rom, ours, differing):
    """The `(address, length)` runs of `differing` (a `compared`'s) left OUTSIDE `the_bound_desk_s_classes` — and
    `{class: bytes it excused}`, each REFUSED where it excused none."""
    classes, left, within = the_bound_desk_s_classes(rom, ours), [], {}
    for at, length in differing:
        for byte in range(at, at + length):
            excused = [name for name, (lo, hi) in classes.items() if lo <= byte < hi]
            if excused:
                within[excused[0]] = within.get(excused[0], 0) + 1
            elif left and left[-1][0] + left[-1][1] == byte:
                left[-1] = (left[-1][0], left[-1][1] + 1)
            else:
                left.append((byte, 1))
    needed = (THE_GEMDOS_STACK, THE_GEMDOS_SAVE_AREA, aes_boot.PROGRAM_CONTEXT.format(THE_DESK_S_NAME.decode()))
    assert all(within.get(name) for name in needed), f"a class of the bound desk excused nothing: {within}"
    return left, within


@functools.cache
def _taken(key, blob):
    """THE MACHINE OUR SHORE'S RUNS START FROM (`our_machine`), as `aes_boot` made it: held where it is made to be
    the ROM-booted one outside the classes such a machine differs in by nature — `TWO_IDLES` named exactly where
    the two idle in two dispatchers (each REFUSED by `compared` where the machines do not differ in it), and THE BOUND
    DESK'S (`the_bound_desk_s_classes`)."""
    if key == gc.THE_DESK:
        taken = aes_boot.desk_machine(ours=blob, door=aes_event.THE_DOOR)
    else:
        taken = aes_boot.accessory_machine(*gc.ACCESSORY_MODES[key], ours=blob, door=aes_event.THE_DOOR)
    booted = gc.machine(key)
    beside = aes_boot.compared(booted, taken, also=TWO_IDLES if taken.idle != booted.idle else ())
    left, _within = outside_the_bound_desk_s_classes(booted, taken, beside.differing)
    assert not left and booted.idle == aes_boot.THE_ROM_S, f"{key}: the takeover machine differs at {left[:4]}"
    assert taken.resumed_in(taken.screen_manager()) == aes_boot.OURS
    return taken


def our_machine(woken, blob):
    """...and on ours: THE SAME BOOT WITH THE SCREEN MANAGER `blob`'s (the takeover machine) — AND ITS DOOR
    (`aes_boot.<machine>(..., door=aes_event.THE_DOOR)`: the narrow door flip, band 5 wave 3, for a boot that loads
    accessories — every accessory entered through the blob's gotopgm, trapping into the blob's handler, parked by
    our dispatcher; `$88` and `$404` the blob's — and, SINCE THE FULL FLIP (wave 4, slice F), THE WHOLE DOOR ON EVERY
    SUCH MACHINE, THE DESK'S OWN AMONG THEM: `$88` is the build's at every row's entry, so the machine a row from an
    idle runs over holds it as the machine stands — with `$404`, justretf's slot, the tick glue's two, the VDI's
    button and motion vectors and the desk's trampoline slot: EIGHT LONGWORDS LAID BY THE HARNESS over what the ROM's
    own start-up stored — A DOOR TAKEOVER, A LABELLED STAGING (ruling W4-R2; the table's legend says it for these rows)
    — so that at the idle no longword holds, by value, the ROM's copy of a routine the registry declares). THE DESK'S
    MACHINE IS WAVE 2's TAKEOVER STILL (ruling W4-R10: not re-based on the our-boot machine) — it loads no program,
    so its door maps vectors alone, and outside those longwords it is wave 2's byte for byte (`test_aes_ctlmgr.py`).
    Held, where it is made, to be the ROM-booted one outside the classes such a machine differs in by nature
    (`aes_boot.by_nature`: per process behind a door), its screen manager parked in our text. ITS IDLE is the
    ROM's dispatcher's on the desk's machine and OURS where an accessory parks last (`_taken`): a row's run is entered at the ROM's
    dispatcher's loop on both shores all the same (`tier3._run_to_its_next_idle`) — the dispatch that brings the
    first process in is the ROM's code on both, outside every window and held equal. `woken`: a row, or anything
    that names its `machine`."""
    return _taken(woken.machine, blob).ram


def our_machine_s_programs(woken, blob):
    """THE PROCESSES OF THAT MACHINE OUR EVENT LAYER PARKS BESIDE THE SCREEN MANAGER, behind our door: `((pd, (lo,
    top)), ...)` — each loaded program's stack span as the door's takeover found it, and, THE DOOR BINDING THE LINE-F
    TABLE (band 6 slice B0), THE DESK's: PD0, its stack from its UDA's state block to its top (`the_bound_desk_s_classes`)."""
    taken = _taken(woken.machine, blob)
    loaded = tuple((program.pd, program.stack) for program in (taken.takeover.door.programs if taken.takeover.door else ()))
    return (*loaded, (aes.SHELL_PD, the_desk_s_stack(taken)))


def register(woken):
    """ONE PRICED ROW OF ctlmgr, registered (`ROWS`: `bench/tier3.py` reads it): its ROM run derived as the registry is
    imported, as every battery's is."""
    assert set(woken.differs) <= set(CLASSES) and row_name(woken) not in ROWS
    made(woken)
    ROWS[row_name(woken)] = woken
    return woken
