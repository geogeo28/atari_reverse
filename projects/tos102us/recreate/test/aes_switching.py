"""THE ROWS THAT SWITCH — a call that BLOCKS, leaves by the dispatcher and is WOKEN through it, as ONE RETURNING RUN on
both shores: the ROM's routine through the ROM's dispatcher, our twin through OUR dsptch, disp, savestate and switchto
(`src/aes/switch.S`) round the C of forker and idle (`src/aes/evdisp.c`, `evfork.c`).

WHAT WAS THERE (`test/aes_switch.py`): the ROM's own run through its dispatcher with a case's interrupts delivered at
the n-th IDLE (`scheduled`), the host's model of the switch held to it (`modelled`: Tier 1), the context drops, and
the one switch a row could price — a yield, which takes no delivery. WHAT THIS MODULE ADDS is the one thing a row that
is WOKEN needs on the bench: A WATCH FOR BOTH SHORES that stops a run at the dispatcher (`Switching`), and the
registrar that makes a row of it (`register`).

  * AN IDLE is where the machine waits for an interrupt: idle's poll reached with no process ready, none woken and
    no fork queued — the ROM's at `AES_ROM_IDLE_LOOP`, ours where `aes_idle` calls `aes_chkkbd`. Each is numbered as
    the run makes it and the row's delivery of that ordinal is laid there, at no cost, CHECKED FIRST against the
    memory it lands on — as a door row's is laid at a door call. A run that idles ONCE MORE than the ROM's own did
    is refused there by name: the call would block for ever.
  * A POLL is every arrival at that same place, an idle or not: idle polls the keyboard each time round its loop,
    with a process ready or woken too. They are numbered as the run makes them, and a delivery the row names at a
    poll that is NO idle (`Switches.at_polls`) is laid there the same way — a key that arrives while a woken process
    has yet to run. A run that polls more or fewer times than the ROM's own did is refused by name.
  * EVERY PROCESS THE DISPATCHER ENTERS IS FOLLOWED, at switchto's `rte` (the ROM's bytes on both shores): the PD it
    enters and the PC that process resumes at, which becomes the next stop.
  * A FOREIGN WINDOW is the run of ANOTHER process than the row's: from its first instruction to the first
    instruction of the row's process when the dispatcher comes back to it. The snapshot's other process is the
    screen manager, parked BY THE ROM inside the ROM's ev_multi — its saved PC, its frames and the fork codes it
    then queues are the ROM's, and its program (ctlmgr) is not reconstructed: so a foreign window is THE ROM'S OWN
    CODE ON BOTH SHORES, and the dispatcher that hands the machine back is the ROM's too. That is DECLARED, never
    assumed: the watch tallies each window (`tally`: whatever running totals its holder counts), holds that no fork
    is queued where the dispatcher changes hands (a queued code would be run by the other build's forker), keeps
    the code slots the window stored (`foreign_codes`: the ROM's addresses, which no relocation of ours wrote) and
    arms NO door entry inside it (a door call there is another process's). Tier 3 then holds the two shores' windows
    equal to the cycle and takes them off both (`bench/tier3.py`).
  * A DELIVERY IS RELOCATED BY WHO TAKES IT. Laid at OUR idle a fork code it queues is our entry's (the queue is
    our forker's next); laid at the ROM's idle inside a foreign window it is the ROM's, as the ROM's own interrupt
    left it — relocated there, the ROM's forker would `jsr` our entry and the window would be priced on a mixture
    (measured: 5,112 cycles of our mchange inside the window, the image compare still green).

THE HOST CANNOT SWITCH STACKS, AND DOES NOT TRY: Tier 1 of a row here is `aes_switch.modelled` — the C scheduler,
self-resume a plain return, a foreign process a nested run of the ROM — held to the ROM's scheduled run with NOTHING
dropped over the row's settled machine (`companion`). The switch itself, and the target build's frame across it
(saved by savestate, loaded by switchto, on the process's own stack), are what the bench's second differential holds:
the image, the answer, and every callee-saved register back after the wake.
"""
import functools
from collections import namedtuple

from harness import addrs, bench_tier3, make_image
from recreate_kit import rom_bench

import abi
import aes
import aes_event
import aes_switch
import case
import derived
import routines
import transcription
import vdi
from case import merge_pokes

BUS = aes_event.OS_BUS_ADDR_MASK
ROM_POLL, ROM_POLLED = addrs.AES_ROM_IDLE_LOOP, addrs.AES_ROM_IDLE_POLLED
ROM_RTE = addrs.AES_ROM_SWITCHTO_RTE
RTE_OFFSET = addrs.AES_ROM_SWITCHTO_RTE - addrs.AES_ROM_SWITCHTO    # switchto is the ROM's bytes in our build: the same offset
OUR_POLL, OUR_IDLE, OUR_SWITCHTO = "aes_chkkbd", "aes_idle", "aes_rom_switchto"
OUR_OWN, THE_ROM_S = "our own", "the ROM's"         # whose dispatcher an idle is, in a refusal's words
# Every longword of the machine that can hold a relocated code address (`aes_event.CODE_RELOCATIONS`): what a
# foreign window is watched to have stored.
CODE_SLOTS = tuple(slot for relocation in aes_event.CODE_RELOCATIONS for slot in relocation.slots)
# ...and the ROM routines one of them names (the fork functions, the glue): any other value a window leaves in a slot
# is no code (the AES's contrl words are plain VDI arguments between two vex calls).
ROM_CODES = frozenset(routine for relocation in aes_event.CODE_RELOCATIONS for routine in relocation.symbols)
# Every EVB's parameter longword: where a pipe wait keeps its QPB's address (`aes_event.qpb_addresses_kept`).
EVB_PARMS = tuple(evb + aes.EVB_PARM for evb in aes_event.EVBS)
QPB_BYTES = aes_event.QPB.size

# OUR BUILD'S DISPATCHER, as a blob places it: `poll`, the keyboard poll's first instruction (`aes_chkkbd`) — an idle's
# where it is called from `idle` (`aes_idle`'s text: ev_multi polls too) — and `rte`, switchto's last instruction.
OurDispatcher = namedtuple("OurDispatcher", "poll idle rte")


def our_dispatcher(blob):
    """`blob`'s own dispatcher (a `RomBench`'s): where its idle polls, and where its switchto enters a process."""
    sized = {symbol.name: symbol for symbol in transcription.symbol_table(blob.elf)}
    idle = sized[OUR_IDLE]
    return OurDispatcher(blob.entry(OUR_POLL), (idle.start, idle.start + idle.size), blob.entry(OUR_SWITCHTO) + RTE_OFFSET)


def _whole_cycles():
    """A watch's default tally: the run's cycles so far, alone."""
    return (aes_event.run_cost()["cycles"],)


class Refused(AssertionError):
    """A watched run of a row that switches is not the run its `Switches` describes."""


class Switching:
    """A WATCH (`rom_bench.watched`) OVER A RUN THAT SWITCHES (the module's docstring), for either shore.

    `switches` (`aes_event.Switches`): the deliveries, the idles the ROM's own run makes, the row's process.
    `inner`: the run's door watch (`aes_event.DoorStops`, made WITHOUT `blocks`: this run leaves by the dispatcher) or
    None — it is handed every stop of its own while the row's process runs, and none inside a foreign window.
    `ours` (an `OurDispatcher`): the run is OUR build's — its own idle and switchto are stops beside the ROM's (a
    foreign window's dispatcher is the ROM's on both shores), and `relocated` is `switches.at_idles` as OUR idle
    takes them (`tier3.deliveries_for_our_shore`), `relocated_polls` its `at_polls`. `tally()`: the holder's running totals, a tuple; `foreign` is then
    one tuple of differences per window. `observing`: `{PC: observe(memory)}` — further stops of the holder's own,
    in whichever process they are reached. `ledger()`: the addresses the run has stored so far (its write ledger),
    for a holder that must know WHO stored a byte (`stored_outside_the_windows`).

    A DELIVERY NAMED AT AN IDLE OR A POLL THE ROW'S RUN DOES NOT MAKE is refused where the watch is made: it would
    never be laid, and nothing else would say so. One named at a poll that turns out an IDLE is refused there.
    A DOOR CALL OPEN ACROSS A FOREIGN WINDOW is told where the window opens and closes
    (`inner.foreign_window_opened()` / `foreign_window_closed()`): its holder takes the window off the call's own
    cost on each shore (`tier3.DoorWindows`). A call open across a SELF-RESUME needs nothing: the switch is its cost.

    AFTER THE RUN: `idles`, `polls`, `entered` (the PD at each switchto, in order), `foreign`, `foreign_codes` (`{slot: the
    ROM routine's address a window stored there}`), `qpbs_seen` (`{an EVB_PARM's address: the QPB it named}`: every
    pipe wait's QPB in the run's own stack, read where the row's process stands parked or is resumed — at an idle,
    whoever's, and at its resume: its frames are live there, which they are not once the call has returned; what
    `vet_our_qpbs` holds a blob's run to), `qpbs_parked` (`{that address: (where the QPB lay, the row's process's
    stack pointer there)}`: a QPB is a local of a LIVE frame — at or above that pointer), and `vet_ended(who)`."""

    def __init__(self, switches, *, inner=None, ours=None, relocated=None, relocated_polls=None, tally=_whole_cycles,
                 observing=None, ledger=None):
        assert not (ours is None and (relocated or relocated_polls)), "the ROM's shore takes its deliveries as they are"
        _refuse_what_is_never_made("idle", switches.at_idles, switches.idles)
        if switches.at_polls:
            assert switches.polls is not None, "a delivery at a poll, and no count of the polls the ROM's run makes"
            _refuse_what_is_never_made("poll", switches.at_polls, switches.polls)
        self.switches, self.inner, self._ours, self._tally = switches, inner, ours, tally
        self._observing, self._ledger = dict(observing or {}), ledger
        self._stored_outside, self._stores_seen = set(), frozenset()
        self._at_our_idle = switches.at_idles if relocated is None else relocated
        self._at_our_poll = switches.at_polls if relocated_polls is None else relocated_polls
        self._polls = frozenset({ROM_POLL} | ({ours.poll} if ours else set()))
        self._rtes = frozenset({ROM_RTE} | ({ours.rte} if ours else set()))
        self._inner_armed = frozenset(inner.first) if inner else frozenset()
        self._polled, self._resumes_at, self._entering = set(), None, None
        self._window, self._slots_found = None, None
        self.idles, self.polls, self.entered, self.foreign, self.foreign_codes = 0, 0, [], [], {}
        self.qpbs_seen, self.qpbs_parked, self._qpbs_at = {}, {}, {}
        self.first = self._armed()

    def _armed(self):
        """The stops as the run stands: the dispatcher's, the pending re-arms, and — while the row's own process
        runs — its door watch's."""
        inner = frozenset() if self._window is not None else self._inner_armed
        return self._polls | self._rtes | frozenset(self._polled) | frozenset(self._observing) | inner

    def stopped(self, pc, sp, memory):
        if pc == self._resumes_at:
            self._resumed(sp, memory)
        elif pc in self._rtes:
            return self._entered(sp, memory)
        elif pc in self._polls:
            self._polling(pc, sp, memory)
        elif pc in self._polled:
            self._polled.discard(pc)    # past the poll: its entry is a stop again
        elif pc in self._observing:
            self._observing[pc](memory)
        else:
            assert self.inner is not None and pc in self._inner_armed and self._window is None, (
                f"a run that switches stopped at {pc:#x}: no stop of its dispatcher's, and none its door watch armed")
            self._inner_armed = frozenset(self.inner.stopped(pc, sp, memory))
        return self._armed() - {pc}

    # ---- a poll of the dispatcher's idle — and, among them, an idle: where the machine waits for an interrupt ----
    def _polling(self, pc, sp, memory):
        ours = self._ours is not None and pc == self._ours.poll
        back = case.long_in(memory, sp) & BUS if ours else ROM_POLLED
        self._polled.add(back)
        if ours and not self._ours.idle[0] <= back < self._ours.idle[1]:
            return                      # a poll of the event layer's own (ev_multi's), not the dispatcher's idle
        poll, self.polls = self.polls, self.polls + 1
        whose = f"{OUR_OWN if ours else THE_ROM_S} dispatcher, {pc:#x}"
        if not aes_switch.waits_for_an_interrupt(memory):
            self._lay((self._at_our_poll if ours else self.switches.at_polls).get(poll), memory, f"poll {poll} ({whose})")
            return
        self._see_the_qpbs(memory, self._parked_at(memory))
        ordinal, self.idles = self.idles, self.idles + 1
        where = f"idle {ordinal} ({whose})"
        if poll in self.switches.at_polls:
            raise Refused(f"{where}: a delivery is named at poll {poll}, which is this idle — an idle's delivery is "
                          f"named at the idle")
        if ordinal >= self.switches.idles:
            raise Refused(
                f"{where}: the dispatcher idles once more than the ROM's own run did ({self.switches.idles}) — the "
                f"call would block, the machine waiting for an interrupt no case delivers")
        self._lay((self._at_our_idle if ours else self.switches.at_idles).get(ordinal), memory, where)

    @staticmethod
    def _lay(delivery, memory, where):
        """`delivery` (`(found, wrote)`, or None: nothing is due) laid over `memory`, checked first against it."""
        if delivery:
            found, wrote = delivery
            aes_event.vet_found(memory, found, where)
            aes_event.lay(memory, wrote)

    # ---- a process entered: switchto's `rte`, and the instruction it resumes at ----
    def _entered(self, sp, memory):
        self._entering = case.long_in(memory, aes.AES_RLR) & BUS
        self.entered.append(self._entering)
        self._resumes_at = case.long_in(memory, sp + aes_event.EXCEPTION_FRAME_PC) & BUS
        return frozenset({self._resumes_at})    # the `rte` alone runs before it

    def _resumed(self, sp, memory):
        self._resumes_at = None
        foreign = self._entering != self.switches.process
        if foreign and self._window is None:
            self._vet_no_fork_is_queued(memory, "entered")
            self._stores_outside_so_far()
            self._window, self._slots_found = self._tally(), self._code_slots(memory)
            if self.inner is not None:
                self.inner.foreign_window_opened()
        elif not foreign and self._window is not None:
            self._vet_no_fork_is_queued(memory, "left")
            self._stores_seen = self._stores_now()      # ...the window's own stores: seen, and nobody's of ours
            self.foreign.append(tuple(now - then for now, then in zip(self._tally(), self._window)))
            self.foreign_codes.update({slot: code for slot, code in self._code_slots(memory).items()
                                       if code != self._slots_found[slot] and code in ROM_CODES})
            self._window = self._slots_found = None
            if self.inner is not None:
                self.inner.foreign_window_closed()
        if not foreign:
            self._see_the_qpbs(memory, sp)

    def _parked_at(self, memory):
        """The stack pointer the row's process stands PARKED at over `memory`: what savestate kept in its UDA."""
        return case.long_in(memory, aes_event.uda_of(self.switches.process, memory) + aes.UDA_SUPER_SP) & BUS

    def _see_the_qpbs(self, memory, sp):
        """Every QPB a pipe wait names IN THE RUN'S OWN STACK as the machine stands (the row's process blocked, or
        just resumed, its stack pointer `sp`: the frame that holds the QPB is live), by its EVB's parameter — READ
        THE FIRST TIME THAT ADDRESS IS SEEN THERE, and again only WHILE THE WAIT IS QUEUED on a pipe (a later wait
        of the same EVB whose QPB lies where the last one's did is another QPB): an EVB freed keeps the address, and
        the frame it names is gone at the next stop. WHERE it lay is kept with the stack pointer of that moment."""
        queued = aes_event.waiting_on_a_pipe(memory)
        for at in EVB_PARMS:
            qpb_at = case.long_in(memory, at) & BUS
            if self._qpbs_at.get(at) == qpb_at and at - aes.EVB_PARM not in queued:
                continue
            self._qpbs_at[at] = qpb_at
            if qpb_at in case.STACK_BAND and qpb_at + QPB_BYTES - 1 in case.STACK_BAND:
                self.qpbs_seen[at] = aes_event.QPB.unpack(bytes(memory[qpb_at:qpb_at + QPB_BYTES]))
                self.qpbs_parked[at] = (qpb_at, sp)

    @staticmethod
    def _code_slots(memory):
        return {slot: case.long_in(memory, slot) for slot in CODE_SLOTS}

    def _vet_no_fork_is_queued(self, memory, how):
        queued = case.word_in(memory, aes.AES_FORK_COUNT)
        if queued:
            raise Refused(
                f"a foreign process is {how} (the dispatcher enters the PD at {self._entering:#x}) with {queued} "
                f"fork(s) queued: the dispatcher changes hands there, and the code a queue entry holds would be run "
                f"by the other build's forker")

    # ---- who stored a byte: the row's own process's code, or a foreign window's ----
    def _stores_now(self):
        return frozenset(self._ledger()) if self._ledger else frozenset()

    def _stores_outside_so_far(self):
        now = self._stores_now()
        self._stored_outside |= now - self._stores_seen
        self._stores_seen = now

    def stored_outside_the_windows(self):
        """The addresses this run stored OUTSIDE every foreign window — first stored there, or before one (asked
        once the run has ended; `ledger` given). CONSERVATIVE: an address a window stored and the row's process
        stored only AFTER it is not among them (the ledger keeps no order) — a drop that stands on such a store is
        refused, never passed."""
        assert self._ledger, "a watch asked who stored a byte was given the run's ledger"
        self._stores_outside_so_far()
        return frozenset(self._stored_outside)

    def vet_ended(self, who):
        """THE RUN ENDED AS THE ROW SAYS: in the row's own process (none left entered and not resumed), and every
        idle and every poll of the ROM's run made — a run that made fewer never waited where the ROM did, and one
        that polled another number of times took a delivery at another point of its dispatch. (Every delivery was
        then laid: each is named at an idle or a poll the run makes — held where the watch is made — and laid where
        that idle or poll is.)"""
        if self._resumes_at is not None or self._window is not None:
            raise Refused(f"{who}: the run ended inside another process than the one that made the call "
                          f"(the PD at {self._entering:#x})")
        if self.idles != self.switches.idles:
            raise Refused(f"{who}: the run made {self.idles} idle(s) where the ROM's own makes {self.switches.idles}")
        if self.switches.polls is not None and self.polls != self.switches.polls:
            raise Refused(f"{who}: the run's dispatcher polled {self.polls} time(s) where the ROM's own run polls "
                          f"{self.switches.polls}")


def _refuse_what_is_never_made(kind, named, made):
    """A delivery named at an idle / a poll (`kind`) outside the `made` ones the ROM's own run counts: `Refused`."""
    never_made = sorted(ordinal for ordinal in named if not 0 <= ordinal < made)
    if never_made:
        raise Refused(f"a delivery is named at {kind} {never_made} of a run that makes {made} {kind}(s): it would never "
                      f"be laid")


def the_rom_s(switches, entered_at=None, tally=_whole_cycles, inner=None, observing=None):
    """THE ROM'S SHORE: the watch of the ROM's own run of a row that switches. `entered_at` and `inner`: its door
    watch — given, or made here where the row has door-call deliveries too (one that does not `block`)."""
    if inner is None and switches.at_calls:
        inner = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, delivered=switches.at_calls,
                                    entered_at=entered_at)
    return Switching(switches, inner=inner, tally=tally, observing=observing)


def ours(blob, switches, relocated, tally=_whole_cycles, inner=None, ledger=None, relocated_polls=None):
    """OUR SHORE, on `blob`: `relocated` the row's idle deliveries as our own dispatcher takes them,
    `relocated_polls` those it takes at a poll that is no idle."""
    return Switching(switches, inner=inner, ours=our_dispatcher(blob), relocated=relocated,
                     relocated_polls=relocated_polls, tally=tally, ledger=ledger)


# ---- THE REGISTRAR: a row that blocks and is woken ------------------------------------------------------------------------
# `name`, `arguments`, `machine` (a zero-argument builder: the scheduler's own, a running process), `at_idle` (`{idle:
# interrupt}`, as `aes_switch.scheduled` takes them). Everything else is DERIVED from the ROM's own runs.
# `answered` False for a routine that sets no D0 on the row's arm (it leaves its caller's, which no C is handed).
# `at_polls`: `{poll: interrupt}` — what arrives at a poll of the dispatcher that is no idle (`aes_switch.scheduled`).
# `budget`: the row's own derivation budget, DECLARED from its measured run (`aes_event._budget_of`: a session too long
# for the default's margin — the file selector's); every ROM run that derives the row is held to it, both ways.
SwitchingRow = namedtuple("SwitchingRow", "label name arguments machine at_idle answered at_calls door at_polls budget",
                          defaults=(True, None, None, None, None))
NO_FRAME = b""                          # a routine of no argument: nothing at the first argument's place
# What a registered row keeps (`aes_event.SWITCHING_ROWS`): the row, its settled machine, its Tier 3 drops, what its
# run is taken through, the processes the ROM's dispatcher enters, its deliveries derived again, and the QPB
# addresses its ROM run leaves in EVBs (`Settled.qpbs`, below: what `vet_our_qpbs` holds a blob's run of it to).
Registered = namedtuple("Registered", "row pokes drops switches entered rederived qpbs")
# ...and what its derivation answers: `qpbs` — `{an EVB_PARM's address: the QPB it names}` — THE QPB ADDRESSES THE
# ROM'S RUN LEAVES IN FREED EVBs (`aes_event.qpb_addresses_kept`): a wait on a pipe that blocked and was woken, or
# was cancelled, gives its EVB back with the QPB's address still in its parameter — a place in the waiting routine's
# own frame, another on every shore. Each is among `drops` by name, and vetted wherever a shore's image is at hand
# (`_vetted_qpbs`: the companion's; `vet_our_qpbs`: a blob's).
Settled = namedtuple("Settled", "pokes drops switches entered qpbs")


def _entry(row):
    return getattr(addrs, row.name)


def _core(row):
    return routines.core_symbol(row.name)


def row_name(row):
    return f"{_core(row)}, {row.label}"


def _staged(row):
    """The row's machine with its frame, the keyboard poll's trap save moved into the stack band (a priced row's)."""
    return aes.staged(row.name, row.arguments, merge_pokes(row.machine(), aes_event.savptr_in_the_band()))


def scheduled(row, pokes):
    """The ROM's own run of `row` through its dispatcher over `pokes` (its machine, staged): `aes_switch.scheduled`."""
    return aes_switch.scheduled(_entry(row), pokes.get(abi.FIRST_ARG, NO_FRAME), pokes, row.at_idle,
                                at_calls=row.at_calls, at_polls=row.at_polls, budget=row.budget)


def switches_of(reference):
    """What a run is taken through, read off the ROM's scheduled run `reference` of it."""
    return aes_event.Switches(reference.delivered, reference.idles, case.long_in(reference.started, aes.AES_RLR) & BUS,
                              dict(reference.at_calls), dict(reference.at_polls), reference.polls)


def by_nature(uda):
    """The windows of a switching row that differ by nature between the ROM's run and any other build's: the Line-F
    mask word, the caller's saved context, the dispatcher's stack and its SR save word, an SR save word a bracket
    parks."""
    return (*aes.LINE_F_MASK_WINDOW, *aes_switch.uda_context_drop(uda), *aes_switch.DISPATCHER_STACK_DROP,
            *aes_event.sr_drops())


def dropped_at_tier3(uda):
    """...and the ones a Tier 3 row DROPS, each cut to the bytes the ROM's run stored: the mask word (no C writes
    it), the whole saved context (our build saves its own caller's registers and frame addresses there), the
    dispatcher's stack (our frames, put back) and THE MASK BRACKET'S SAVE WORD — the status register of whoever
    raised the mask, its condition codes those of the instruction before: Alcyon's in the ROM, GCC's in ours
    (adelay's and tchange's bracket: `aes/switch.h`) — a drop held to OUR run's ledger too (`tier3`: a build that
    lost the bracket stores no word). The dispatcher's own save word is staged and COMPARED: savestate and switchto
    are the ROM's instructions in both builds, and park the same word."""
    return (*aes.LINE_F_MASK_WINDOW, *aes_switch.uda_context_drop(uda), *aes_switch.DISPATCHER_STACK_DROP,
            *aes_event.sr_drops(aes.AES_SR_SPL))


def _replayed(row, staged):
    """THE ROM'S RUN OF `row` over `staged`, TWICE AND HELD ONE: the scheduled run, which takes the interrupts, and
    its replay — one watched run laying them at no cost — which has a ledger: `(the scheduled run, the replay's
    watch, its memory, its write ledger)`."""
    reference = scheduled(row, staged)
    assert reference.ended == aes_switch.RETURNED, f"{row.name}: the ROM's scheduled run does not return ({reference.ended})"
    watch = the_rom_s(switches_of(reference), _entry(row))
    final, writes, _regs = rom_bench.watched_original(make_image(staged), _entry(row), watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {row.name} through its dispatcher")
    watch.vet_ended(f"the ROM's replay of {row.name}")
    assert bytes(final[:addrs.ST_RAM_BYTES]) == bytes(reference.memory[:addrs.ST_RAM_BYTES]), (
        f"{row.name}: the replay that lays the deliveries is not the run that took them")
    return reference, watch, final, writes


@derived.kept
def _left(name, arguments, machine, at_idle):
    row = SwitchingRow("", name, arguments, lambda: machine, at_idle)
    staged = _staged(row)
    reference, _watch, final, writes = _replayed(row, staged)
    stored = set(writes) | {at + offset for _found, wrote in reference.delivered.values()
                            for at, data in wrote.items() for offset in range(len(data))}
    return merge_pokes(staged, {at: bytes([final[at]]) for at in stored if at not in case.STACK_BAND and at < addrs.ST_RAM_BYTES})


def left_by(name, arguments, machine, at_idle):
    """THE MACHINE THE ROM'S OWN RUN OF A CALL THAT SWITCHES LEAVES, as pokes: `machine` (a running process's, as
    pokes) after its process's call of `addrs.<name>` blocked and was woken through the ROM's dispatcher, the
    interrupts `at_idle` taken at its idles — EVERY BYTE THE RUN OR AN INTERRUPT STORED, at the value it holds
    where the run ends, the run's own stack aside. By the LEDGER, not by what differs from the snapshot: a byte the
    run stored with the value the snapshot happened to hold is the run's all the same, and over another capture of
    the boot it must not turn back into that capture's (the lock's row over such a machine never returned over a
    snapshot whose masked bytes held noise). A derivation, kept by content."""
    return {at: data for at, data in _left(name, tuple(arguments), machine, dict(at_idle)).items()
            if at not in case.STACK_BAND}


@derived.kept
def _settled(name, arguments, machine, at_idle, at_calls=None, at_polls=None, budget=None):
    """A switching row SETTLED FROM THE ROM'S OWN RUNS (a derivation, kept by content): the scheduled run takes the
    interrupts (`aes_switch.scheduled`: what is delivered at which idle, how many idles, who is entered); its replay
    — one watched run laying them at no cost — is the run every shore is compared with, and its write ledger says
    which bytes of the windows that differ by nature it stored: each staged at the value it leaves, and the row's
    Tier 3 drops cut to them (`aes_event.settled_in_windows`: the one settling)."""
    row = SwitchingRow("", name, arguments, lambda: machine, at_idle, at_calls=at_calls, at_polls=at_polls, budget=budget)
    staged = _staged(row)
    reference, watch, final, writes = _replayed(row, staged)
    switches = watch.switches
    stored = {at: value for at, value in writes.items() if at not in case.STACK_BAND}
    uda = aes_event.uda_of(switches.process, final)
    pokes, drops = aes_event.settled_in_windows(staged, stored, by_nature(uda), dropped=dropped_at_tier3(uda))
    qpbs = _qpbs_left(name, final, writes, watch)
    return Settled(pokes, drops + qpb_address_drops(qpbs), switches, tuple(reference.entered), qpbs)


def _qpbs_left(name, final, writes, watch):
    """`{an EVB_PARM's address: the QPB it named}` for every QPB address the ROM's run (its memory `final`, its
    ledger `writes`, its `watch`) LEAVES in an EVB — the longwords `aes_event.qpb_addresses_kept` finds: an EVB's
    parameter the run stored, holding an address in the stack band — EACH QPB AS THE WATCH SAW IT WHILE ITS FRAME
    WAS LIVE (`Switching.qpbs_seen`), never as the run's end holds it: ev_mesag's QPB is the arguments it pushed for
    ap_rdwr, and the trap frame of its own Line-F return lands on them (measured: the "QPB" read where the run ends
    is `(254, 26932, …)` — `$00fe6934`, the address after ev_mesag's return word)."""
    left = aes_event.qpb_addresses_kept(lambda at, size: bytes(final[at:at + size]), writes)
    unseen = sorted(at for at in left if at not in watch.qpbs_seen)
    assert not unseen, (
        f"{name}: the ROM's run leaves a QPB's address in the EVB(s) at {[f'{at - aes.EVB_PARM:#x}' for at in unseen]} "
        f"that no stop of its dispatcher saw live (a wait queued and freed between two stops): its QPB is not known")
    vet_the_qpbs_lay_in_live_frames(f"{name} (the ROM's run)", left, watch)
    return {at: watch.qpbs_seen[at] for at in left}


def vet_the_qpbs_lay_in_live_frames(who, qpbs, watch):
    """THE PLACE OF A PARKED QPB, held on a watched run (`watch`: its `Switching`): each QPB of `qpbs` (by its EVB's
    parameter) lay, where the run was seen to hold it, AT OR ABOVE THE STACK POINTER OF THE ROW'S PROCESS — in a
    frame that process still has. Below it is a frame already popped: an address that names the right eight bytes
    only until the next call lays its own frame over them, and through which another process's write would land in
    whatever that is."""
    for at in qpbs:
        qpb_at, sp = watch.qpbs_parked[at]
        assert qpb_at >= sp, (
            f"{who}: the QPB the wait of the EVB at {at - aes.EVB_PARM:#x} names lies at {qpb_at:#x}, BELOW its process's "
            f"stack pointer ({sp:#x}) where it stood parked — a frame the process no longer has: a dead frame's address")


def qpb_address_drops(qpbs):
    """The Tier 3 drops of the QPB addresses `qpbs` (a `Settled`'s): one longword each, by name. NOT STAGED, as the
    windows are: no machine can hold beforehand an address in a frame its run has yet to push."""
    return tuple((at, at + aes.LONG_BYTES, aes_event.QPB_ADDRESS_WHY) for at in qpbs)


def settled(row):
    """`row`'s `Settled`: its machine, its Tier 3 drops, what its run is taken through, who the dispatcher enters."""
    return _settled(row.name, tuple(row.arguments), row.machine(), dict(row.at_idle or {}), row.at_calls, row.at_polls,
                    *((row.budget,) if row.budget else ()))


def rederived(row):
    """`row`'s `Switches` DERIVED AGAIN over its settled machine as the snapshot stands now: the interrupts' own
    code run afresh (the noise sweep's, and what holds that the settling changed nothing of them)."""
    return switches_of(scheduled(row, settled(row).pokes))


# What a companion answers, for its caller's own assertions on a woken case: the machine it ran, what its run was
# taken through, the C's answer and the image it returned with — and, of the ROM's run, what each door call was
# handed (a door user's: the C's are held equal) and the processes its dispatcher entered.
CompanionRun = namedtuple("CompanionRun", "staged delivered answer calls image entered")


def companion(row):
    """A SWITCHING ROW'S COMPANION — its Tier 1 differential with NOTHING dropped: the C through its own scheduler
    (`aes_switch.modelled`: self-resume a return, a foreign process the ROM's own code) held to the ROM's scheduled
    run over the row's settled machine — the same idles, the same answer, and every byte outside the run's own stack
    equal: each byte the row drops at Tier 3 is one the ROM's run rewrites with the value the machine stages, and
    the C must not store — BUT A QPB'S ADDRESS LEFT IN A FREED EVB, which no machine can stage and every shore holds
    its own of: vetted, then left out (`_vetted_qpbs`).
    WHERE ANOTHER PROCESS RUNS it is the ROM's own code in the host's run too (the model's nested run), and what
    that code stores where no C ever does — the dispatcher's stack and the Line-F mask word — is NOT laid back
    over the C's image (`aes_switch.STORED_BY_NO_C`): the image keeps there what the machine stages,
    which is what the ROM's whole run leaves, however often the row's process is dispatched again afterwards.
    A DOOR USER's row (`row.door`) binds the door in the same fork, and is held to the frames the ROM's run hands."""
    made = settled(row)
    reference = scheduled(row, made.pokes)
    signature = vdi.ALCYON[row.name]
    foreign = any(pd != made.switches.process for pd in reference.entered)
    ran = aes_switch.modelled(_core(row), vdi.as_signed(row.name, row.arguments), made.pokes, reference,
                              answered=row.answered and signature.restype is not None, foreign=foreign, door=row.door)
    who = row_name(row)
    assert reference.ended == aes_switch.RETURNED and ran.returncode == 0, (
        f"{who}: the ROM's run returned; the C's fork ended {ran.returncode}:\n{ran.stderr}")
    assert ran.idles == reference.idles, f"{who}: the C's run idled {ran.idles} times, the ROM's {reference.idles}"
    assert ran.polls == reference.polls, f"{who}: the C's run polled {ran.polls} times, the ROM's {reference.polls}"
    assert not row.door or ran.handed == list(reference.calls), (
        f"{who}: the door was handed {ran.handed}, the ROM's run hands {list(reference.calls)}")
    answer_bits = aes.RESULT_WIDTHS[signature.restype] if row.answered else case.NO_RESULT
    if answer_bits:
        mask = (1 << answer_bits) - 1
        assert ran.answer & mask == reference.d0 & mask, f"{who}: answers {ran.answer & mask:#x}, the ROM's run {reference.d0 & mask:#x}"
    expected = reference.memory
    differ = aes_event.differing(ran.image, expected, frozenset(case.STACK_BAND) | _vetted_qpbs(row, made, ran.image))
    assert not differ, f"{who}: " + aes_event.describe_differences(who, ran.image, expected, differ)
    if row.door:                        # ...and, the END the ROM's: what each call answered and left, and every dispatch
        aes_event.vet_the_answers_handed_back(who, ran.answered, reference.answers)
        aes_event.vet_the_images_at_the_dispatcher(who, ran.dispatched, reference.dispatches)
    return CompanionRun(made.pokes, switches_of(reference), ran.answer, tuple(reference.calls), ran.image,
                        tuple(reference.entered))


def _vetted_qpbs(row, made, image):
    """THE ONE THING A COMPANION LEAVES OUT BESIDE THE RUN'S OWN STACK, and only VETTED: the bytes of each QPB address
    the ROM's run leaves in a freed EVB (`made.qpbs`) — held first, against the C's own `image`, to be the address
    of the running process's own QPB slot (the row's entry's role, where it is an entry that parks one) naming the
    same eight bytes (`aes_event.vetted_qpb_addresses`: refused by name otherwise). Nothing, for a row that leaves
    none: the vet is then not asked."""
    if not made.qpbs:
        return frozenset()
    vetted = aes_event.vetted_qpb_addresses(row_name(row), image, made.qpbs, _entry(row))
    return frozenset(at for lo, hi, _why in vetted for at in range(lo, hi))


def register(label, name, arguments, machine, at_idle=None, *, answered=True, at_calls=None, door=None, at_polls=None):
    """ONE PRICED ROW THAT SWITCHES, registered (`register_row`). `arguments` `()` for a routine of none; `answered`
    False for an arm that sets no D0; `at_polls` what arrives at a poll that is no idle. The `SwitchingRow`."""
    return register_row(SwitchingRow(label, name, arguments, machine, at_idle, answered, at_calls, door, at_polls))


def register_row(row, under=None):
    """`row` (a `SwitchingRow`) REGISTERED (`aes.ROWS`, `aes_event.SWITCHING_ROWS`) — THE ONE REGISTRAR every
    battery's own ends on (the pilots', the waits', ev_multi's, the door users', the sliced sessions'): settled from
    the ROM's own runs, its `Switches` the ninth field every run of it is taken through, its by-nature windows
    dropped at Tier 3 with the companion a drop needs. `under`: THE NAMES it is registered under where they are not
    its one own (`row_name`) — a session cut into slices (`aes_event.register_woken_slices`): one settling, ONE
    `Registered` and one companion under every name. The row as registered."""
    row = row._replace(arguments=tuple(row.arguments), at_idle=dict(row.at_idle or {}))
    made = settled(row)
    held = Registered(row, made.pokes, made.drops, made.switches, made.entered, functools.partial(rederived, row), made.qpbs)
    undropped = functools.partial(companion, row)
    for name in under or (row_name(row),):
        aes_event.SWITCHING_ROWS[name] = held
        aes.ROWS.register(name, _entry(row), made.pokes, dropped=made.drops, undropped=undropped, delivered=made.switches,
                          answered=row.answered)
    return row


def measured_on(blob, row):
    """THE SECOND DIFFERENTIAL OF A ROW THAT SWITCHES ON ONE BLOB (`tier3.RomBench`), whichever blob the table prices
    it on: the ROM's routine and `blob`'s twin, each watched at its dispatcher, over the row's settled machine with
    its Tier 3 drops — HELD TO EVERYTHING THE TABLE'S OWN MEASUREMENT HOLDS A SWITCHING ROW TO
    (`tier3.switching_run_on`: the two runs one schedule, the foreign windows equal to the cycle with no cycle of
    our build inside, our run in the AES's ROM nowhere else). The kit's `Measurement` of the WHOLE run, our run's
    watch, and the windows' `tier3.Foreign`."""
    tier3, made = bench_tier3(), settled(row)
    returns = tier3.CALL[row.name].returns if row.answered else tier3.RETURNS_NOTHING
    measured, watch, foreign = tier3.switching_run_on(blob, row_name(row), _entry(row), _core(row), (0, *row.arguments),
                                                      made.pokes, made.switches, returns=returns, dropped=made.drops)
    vet_our_qpbs(row_name(row), made.qpbs, watch)
    return measured, watch, foreign


def vet_our_qpbs(who, qpbs, watch):
    """THE DROPPED QPB ADDRESSES, VETTED ON A BLOB (`watch`: our run's `Switching`): where the ROM's run leaves a
    QPB's address in an EVB (`qpbs`, a `Settled`'s), our run held there — while its process stood blocked or was
    resumed — an address in ITS OWN stack naming THE SAME QPB: the process, the count, the buffer. A drop of that
    longword excuses the two addresses, never a twin that queued its wait with another QPB or with none (the bytes
    a writer copies by are read through it in another process's turn: a foreign window's, where no compare looks) —
    AND IN A FRAME ITS PROCESS STILL HAS (`vet_the_qpbs_lay_in_live_frames`: the right eight bytes in a popped frame
    are right until the next call)."""
    for at, the_rom_s in qpbs.items():
        seen = watch.qpbs_seen.get(at)
        assert seen is not None, (
            f"{who}: the ROM's run leaves a QPB's address in the EVB at {at - aes.EVB_PARM:#x} and OUR run was never "
            f"seen to hold one there (at no idle, at no resume of its process): the drop of "
            f"that longword would stand unvetted")
        assert seen == the_rom_s, (
            f"{who}: the QPB our parked wait names ({seen}) is not the ROM's ({the_rom_s}) — the EVB at "
            f"{at - aes.EVB_PARM:#x}")
    vet_the_qpbs_lay_in_live_frames(who, qpbs, watch)


# ---- WHAT EVERY BATTERY HOLDS OF A ROW IT REGISTERS — ONE SPELLING ----------------------------------------------------------
# The pilots', the waits', ev_multi's and the door users' batteries each pin their own rows; WHAT a pin holds is said
# here once, so no battery holds less of a row than another does (a battery that pinned a row's own cycles and not
# its caller's own passed a second count net of a foreign window twice — measured in review).
#   `Premise`: what the ROM's own run of the row IS — the idles it takes a delivery at, the idles it makes, the
#              process that makes the call, the processes its dispatcher enters, the word the call answers (None: an
#              arm that sets no D0), and the polls that are no idle it takes a delivery at.
#   `Priced`:  what the table prices — each shore's OWN cycles (ours, the ROM's); THE CALLER'S OWN, net of the calls
#              of rebound entries, and how many such calls the run closes (None each: the row calls none, and has one
#              count); and its foreign windows (how many, their whole cycles, their cycles in the AES's text).
Premise = namedtuple("Premise", "at_idles idles process entered answer at_polls", defaults=((),))
Priced = namedtuple("Priced", "own callers_own calls windows")
NO_WINDOW = (0, 0, 0)


def table_row(row):
    """The registered row `row` as the table holds it."""
    name, tier3 = row_name(row), bench_tier3()
    return next(each for each in tier3.ROWS if each.registered == name)


def vet_the_premise(row, premise):
    """THE PREMISE of a registered row, on the ROM's run through its own dispatcher over the row's settled machine:
    it returns to the process that made the call (its PD the ready list's head where the run ENDS, the dispatcher's
    guard clear), each interrupt taken at the idle — or the poll — the row names,
    the dispatcher entering exactly the processes `premise` names, the call answering its word — and THE ROW CARRIES
    THAT RUN'S DELIVERIES (the settling changed nothing an interrupt reads or writes), derived again equal. The
    ROM's `Scheduled` run."""
    who, made = row_name(row), settled(row)
    the_rom_s = scheduled(row, made.pokes)
    assert (the_rom_s.ended, the_rom_s.idles, the_rom_s.entered) == (aes_switch.RETURNED, premise.idles, tuple(premise.entered)), (
        f"{who}: the ROM's run {the_rom_s.ended}, {the_rom_s.idles} idle(s), entered {[f'{pd:#x}' for pd in the_rom_s.entered]}")
    assert (tuple(sorted(the_rom_s.delivered)), tuple(sorted(the_rom_s.at_polls))) == (tuple(premise.at_idles), tuple(premise.at_polls)), (
        f"{who}: the ROM's run took deliveries at the idles {sorted(the_rom_s.delivered)} and the polls {sorted(the_rom_s.at_polls)}")
    assert made.switches == aes_event.Switches(the_rom_s.delivered, premise.idles, premise.process, dict(the_rom_s.at_calls),
                                               the_rom_s.at_polls, the_rom_s.polls) == rederived(row), who
    at_its_end = the_rom_s.memory
    assert aes.list_of(at_its_end, aes.AES_RLR)[0] == premise.process and at_its_end[aes.AES_INDISP] == 0, (
        f"{who}: the ROM's run does not END in the process that made the call, out of the dispatcher")
    assert (premise.answer is None) == (not row.answered), f"{who}: a row that answers nothing says so (`answered`)"
    assert premise.answer is None or the_rom_s.d0 & aes.WORD_MASK == premise.answer, f"{who}: answers {the_rom_s.d0 & aes.WORD_MASK:#x}"
    return the_rom_s


def vet_on_a_blob(blob, row, premise, windows, whole):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH on `blob` (`measured_on`: every rule the table's own measurement
    holds), and beside it: our run made the idles and polls and entered the processes of `premise`, its foreign
    windows are `windows` (the ROM's own run of the other process: no blob's), and THE WHOLE RUN'S CYCLES — the
    ROM's, ours, net of the entry both share — are `whole` (`{the blob's directory: (the ROM's, ours)}`). A row that
    moves says why: a frame, a path, the dispatcher itself. `(measured, our run's watch, the windows)`."""
    who = row_name(row)
    measured, watch, foreign = measured_on(blob, row)
    assert (watch.idles, watch.polls, tuple(watch.entered)) == (premise.idles, settled(row).switches.polls, tuple(premise.entered)), who
    assert tuple(foreign) == tuple(windows), f"{who}: foreign {tuple(foreign)}: the windows are the ROM's own run of the other process"
    assert watch.inner is None or watch.inner.closed == watch.inner.calls, f"{who}: every door call opened is closed"
    assert (measured.original_net, measured.recreate_net) == whole[blob.elf.parent.name], (
        f"{who} measures {measured.original_net} / {measured.recreate_net} cycles on {blob.elf.parent.name}: say why it moved")
    return measured, watch, foreign


def priced_by_the_table(row):
    """`(the table's measurement of the registered row, its Priced)` (`tier3.measure`)."""
    tier3 = bench_tier3()
    measured = tier3.measure(table_row(row), tier3.RomBench())
    second = tier3.has_a_second_count(measured)
    return measured, Priced(measured.own_cycles, tier3.caller_own_cycles(measured) if second else None,
                            measured.rebound_calls if second else None, tuple(tier3.foreign_of(measured)))


def vet_the_table_s_price(row, priced):
    """WHAT THE TABLE READS of a registered row is `priced` — its OWN cycles on each shore, THE CALLER'S OWN and the
    calls it is net of where the run calls a rebound entry (pinned, never only "under the bar": a second count net
    of the wrong thing stays under it), its foreign windows in neither column — AND BOTH COUNTS ARE UNDER THE BAR
    with their thunks. The table's measurement."""
    measured, read = priced_by_the_table(row)
    assert read == priced, f"{row_name(row)}: the table prices {read}: say why it moved"
    assert bench_tier3().counts_within_bar_with_glue(measured), f"{row_name(row)}: over the bar on one of its counts"
    return measured
