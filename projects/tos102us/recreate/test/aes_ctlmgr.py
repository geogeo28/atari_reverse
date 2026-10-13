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
from collections import namedtuple

import derived
from harness import addrs, make_image

import aes
import aes_boot
import aes_event
import aes_gemctrl as gc
import aes_switch
import case

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


@functools.cache
def _taken(key, blob):
    """THE MACHINE OUR SHORE'S RUNS START FROM (`our_machine`), as `aes_boot` made it: held where it is made to be
    the ROM-booted one outside the classes such a machine differs in by nature — `TWO_IDLES` named exactly where
    the two idle in two dispatchers (each REFUSED by `compared` where the machines do not differ in it)."""
    if key == gc.THE_DESK:
        taken = aes_boot.desk_machine(ours=blob, door=aes_event.THE_DOOR)
    else:
        taken = aes_boot.accessory_machine(*gc.ACCESSORY_MODES[key], ours=blob, door=aes_event.THE_DOOR)
    booted = gc.machine(key)
    beside = aes_boot.compared(booted, taken, also=TWO_IDLES if taken.idle != booted.idle else ())
    assert not beside.differing and booted.idle == aes_boot.THE_ROM_S, f"{key}: the takeover machine differs at {beside.differing[:4]}"
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
    """THE LOADED PROGRAMS OF THAT MACHINE, behind our door: `((pd, (lo, top)), ...)` — each one's stack span as the
    door's takeover found it; none for a machine that loads none (the desk's)."""
    taken = _taken(woken.machine, blob).takeover
    return tuple((program.pd, program.stack) for program in (taken.door.programs if taken.door else ()))


def register(woken):
    """ONE PRICED ROW OF ctlmgr, registered (`ROWS`: `bench/tier3.py` reads it): its ROM run derived as the registry is
    imported, as every battery's is."""
    assert set(woken.differs) <= set(CLASSES) and row_name(woken) not in ROWS
    made(woken)
    ROWS[row_name(woken)] = woken
    return woken
