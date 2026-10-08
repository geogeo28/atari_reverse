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
    takes them (`tier3.deliveries_for_our_shore`). `tally()`: the holder's running totals, a tuple; `foreign` is then
    one tuple of differences per window. `observing`: `{PC: observe(memory)}` — further stops of the holder's own,
    in whichever process they are reached. `ledger()`: the addresses the run has stored so far (its write ledger),
    for a holder that must know WHO stored a byte (`stored_outside_the_windows`).

    A DELIVERY NAMED AT AN IDLE THE ROW'S RUN DOES NOT MAKE is refused where the watch is made: it would never be
    laid, and nothing else would say so.
    A DOOR CALL OPEN ACROSS A FOREIGN WINDOW is refused by name where the window would open: the call's cost on
    each shore (`DoorWindows.own_inside`, the twin's AES-ROM cycles) would hold the window, and no rule takes it
    off them yet. A call open across a SELF-RESUME is priced.

    AFTER THE RUN: `idles`, `entered` (the PD at each switchto, in order), `foreign`, `foreign_codes` (`{slot: the
    ROM routine's address a window stored there}`), and `vet_ended(who)`."""

    def __init__(self, switches, *, inner=None, ours=None, relocated=None, tally=_whole_cycles, observing=None,
                 ledger=None):
        assert not (ours is None and relocated), "the ROM's shore takes its deliveries as they are"
        never_made = sorted(idle for idle in switches.at_idles if not 0 <= idle < switches.idles)
        if never_made:
            raise Refused(f"a delivery is named at idle {never_made} of a run that makes {switches.idles} idle(s): it "
                          f"would never be laid")
        self.switches, self.inner, self._ours, self._tally = switches, inner, ours, tally
        self._observing, self._ledger = dict(observing or {}), ledger
        self._stored_outside, self._stores_seen = set(), frozenset()
        self._at_our_idle = switches.at_idles if relocated is None else relocated
        self._polls = frozenset({ROM_POLL} | ({ours.poll} if ours else set()))
        self._rtes = frozenset({ROM_RTE} | ({ours.rte} if ours else set()))
        self._inner_armed = frozenset(inner.first) if inner else frozenset()
        self._polled, self._resumes_at, self._entering = set(), None, None
        self._window, self._slots_found = None, None
        self.idles, self.entered, self.foreign, self.foreign_codes = 0, [], [], {}
        self.first = self._armed()

    def _armed(self):
        """The stops as the run stands: the dispatcher's, the pending re-arms, and — while the row's own process
        runs — its door watch's."""
        inner = frozenset() if self._window is not None else self._inner_armed
        return self._polls | self._rtes | frozenset(self._polled) | frozenset(self._observing) | inner

    def stopped(self, pc, sp, memory):
        if pc == self._resumes_at:
            self._resumed(memory)
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

    # ---- an idle: where the machine waits for an interrupt ----
    def _polling(self, pc, sp, memory):
        ours = self._ours is not None and pc == self._ours.poll
        back = case.long_in(memory, sp) & BUS if ours else ROM_POLLED
        self._polled.add(back)
        if ours and not self._ours.idle[0] <= back < self._ours.idle[1]:
            return                      # a poll of the event layer's own (ev_multi's), not the dispatcher's idle
        if not aes_switch.waits_for_an_interrupt(memory):
            return
        ordinal, self.idles = self.idles, self.idles + 1
        where = f"idle {ordinal} ({OUR_OWN if ours else THE_ROM_S} dispatcher, {pc:#x})"
        if ordinal >= self.switches.idles:
            raise Refused(
                f"{where}: the dispatcher idles once more than the ROM's own run did ({self.switches.idles}) — the "
                f"call would block, the machine waiting for an interrupt no case delivers")
        delivery = (self._at_our_idle if ours else self.switches.at_idles).get(ordinal)
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

    def _resumed(self, memory):
        self._resumes_at = None
        foreign = self._entering != self.switches.process
        if foreign and self._window is None:
            self._vet_no_fork_is_queued(memory, "entered")
            if self.inner is not None and not self.inner.between_calls:
                raise Refused(
                    f"a door call open across a foreign window (the dispatcher enters the PD at {self._entering:#x} "
                    f"inside door call {self.inner.calls - 1}): not priced yet — the window would be counted in the "
                    f"call's own cost on each shore (slice U)")
            self._stores_outside_so_far()
            self._window, self._slots_found = self._tally(), self._code_slots(memory)
        elif not foreign and self._window is not None:
            self._vet_no_fork_is_queued(memory, "left")
            self._stores_seen = self._stores_now()      # ...the window's own stores: seen, and nobody's of ours
            self.foreign.append(tuple(now - then for now, then in zip(self._tally(), self._window)))
            self.foreign_codes.update({slot: code for slot, code in self._code_slots(memory).items()
                                       if code != self._slots_found[slot] and code in ROM_CODES})
            self._window = self._slots_found = None

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
        idle of the ROM's run made — a run that made fewer never waited where the ROM did. (Every delivery was then
        laid: each is named at an idle the run makes — held where the watch is made — and laid where that idle is.)"""
        if self._resumes_at is not None or self._window is not None:
            raise Refused(f"{who}: the run ended inside another process than the one that made the call "
                          f"(the PD at {self._entering:#x})")
        if self.idles != self.switches.idles:
            raise Refused(f"{who}: the run made {self.idles} idle(s) where the ROM's own makes {self.switches.idles}")


def the_rom_s(switches, entered_at=None, tally=_whole_cycles, inner=None, observing=None):
    """THE ROM'S SHORE: the watch of the ROM's own run of a row that switches. `entered_at` and `inner`: its door
    watch — given, or made here where the row has door-call deliveries too (one that does not `block`)."""
    if inner is None and switches.at_calls:
        inner = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, delivered=switches.at_calls,
                                    entered_at=entered_at)
    return Switching(switches, inner=inner, tally=tally, observing=observing)


def ours(blob, switches, relocated, tally=_whole_cycles, inner=None, ledger=None):
    """OUR SHORE, on `blob`: `relocated` the row's idle deliveries as our own dispatcher takes them."""
    return Switching(switches, inner=inner, ours=our_dispatcher(blob), relocated=relocated, tally=tally, ledger=ledger)


# ---- THE REGISTRAR: a row that blocks and is woken ------------------------------------------------------------------------
# `name`, `arguments`, `machine` (a zero-argument builder: the scheduler's own, a running process), `at_idle` (`{idle:
# interrupt}`, as `aes_switch.scheduled` takes them). Everything else is DERIVED from the ROM's own runs.
# `answered` False for a routine that sets no D0 on the row's arm (it leaves its caller's, which no C is handed).
SwitchingRow = namedtuple("SwitchingRow", "label name arguments machine at_idle answered", defaults=(True,))
NO_FRAME = b""                          # a routine of no argument: nothing at the first argument's place
# What a registered row keeps (`aes_event.SWITCHING_ROWS`): the row, its settled machine, its Tier 3 drops, what its
# run is taken through, the processes the ROM's dispatcher enters, and its deliveries derived again.
Registered = namedtuple("Registered", "row pokes drops switches entered rederived")
Settled = namedtuple("Settled", "pokes drops switches entered")


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
    return aes_switch.scheduled(_entry(row), pokes.get(abi.FIRST_ARG, NO_FRAME), pokes, row.at_idle)


def switches_of(reference):
    """What a run is taken through, read off the ROM's scheduled run `reference` of it."""
    return aes_event.Switches(reference.delivered, reference.idles, case.long_in(reference.started, aes.AES_RLR) & BUS)


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


@derived.kept
def _settled(name, arguments, machine, at_idle):
    """A switching row SETTLED FROM THE ROM'S OWN RUNS (a derivation, kept by content): the scheduled run takes the
    interrupts (`aes_switch.scheduled`: what is delivered at which idle, how many idles, who is entered); its replay
    — one watched run laying them at no cost — is the run every shore is compared with, and its write ledger says
    which bytes of the windows that differ by nature it stored: each staged at the value it leaves, and the row's
    Tier 3 drops cut to them (`aes_event.settled_in_windows`: the one settling)."""
    row = SwitchingRow("", name, arguments, lambda: machine, at_idle)
    staged = _staged(row)
    reference = scheduled(row, staged)
    assert reference.ended == aes_switch.RETURNED, f"{name}: the ROM's scheduled run does not return ({reference.ended})"
    switches = switches_of(reference)
    watch = the_rom_s(switches, _entry(row))
    final, writes, _regs = rom_bench.watched_original(make_image(staged), _entry(row), watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {name} through its dispatcher")
    watch.vet_ended(f"the ROM's replay of {name}")
    assert bytes(final[:addrs.ST_RAM_BYTES]) == bytes(reference.memory[:addrs.ST_RAM_BYTES]), (
        f"{name}: the replay that lays the deliveries is not the run that took them")
    stored = {at: value for at, value in writes.items() if at not in case.STACK_BAND}
    uda = aes_event.uda_of(switches.process, final)
    pokes, drops = aes_event.settled_in_windows(staged, stored, by_nature(uda), dropped=dropped_at_tier3(uda))
    return Settled(pokes, drops, switches, tuple(reference.entered))


def settled(row):
    """`row`'s `Settled`: its machine, its Tier 3 drops, what its run is taken through, who the dispatcher enters."""
    return _settled(row.name, tuple(row.arguments), row.machine(), dict(row.at_idle or {}))


def rederived(row):
    """`row`'s `Switches` DERIVED AGAIN over its settled machine as the snapshot stands now: the interrupts' own
    code run afresh (the noise sweep's, and what holds that the settling changed nothing of them)."""
    return switches_of(scheduled(row, settled(row).pokes))


CompanionRun = namedtuple("CompanionRun", "staged delivered answer")
# THE TWO WINDOWS A FOREIGN PROCESS'S OWN CODE WRITES IN THE HOST'S RUN TOO: the model runs another process as the
# ROM's code (`aes_switch.Scheduling`: a nested run from switchto until the ROM's disp is about to enter the caller
# again), and that code runs on the dispatcher's stack and returns by Line-F — where no C of ours stores a byte.
WRITTEN_BY_A_FOREIGN_TURN = (aes_switch.DISPATCHER_STACK, *((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW))


def _where_the_dispatcher_hands_back(row, made):
    """`{lo: bytes}` of WRITTEN_BY_A_FOREIGN_TURN as the ROM's own run of `row` holds them at its disp's LAST call of
    switchto (`AES_ROM_DISP_SWITCHTO`) — the one that enters the row's process again: the run returns in it — which
    is the very instruction the model's nested run of a foreign process ends at."""
    held = {}

    def about_to_enter_a_process(memory):
        held.update({lo: bytes(memory[lo:hi]) for lo, hi in WRITTEN_BY_A_FOREIGN_TURN})     # ...the last one stands
    watch = the_rom_s(made.switches, _entry(row), observing={addrs.AES_ROM_DISP_SWITCHTO: about_to_enter_a_process})
    rom_bench.watched_original(make_image(made.pokes), _entry(row), watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {row.name}, observed where its dispatcher hands back")
    watch.vet_ended(f"the ROM's replay of {row.name}")
    return held


def companion(row):
    """A SWITCHING ROW'S COMPANION — its Tier 1 differential with NOTHING dropped: the C through its own scheduler
    (`aes_switch.modelled`: self-resume a return, a foreign process the ROM's own code) held to the ROM's scheduled
    run over the row's settled machine — the same idles, the same answer, and every byte outside the run's own stack
    equal: each byte the row drops at Tier 3 is one the ROM's run rewrites with the value the machine stages, and
    the C must not store.
    WHERE ANOTHER PROCESS RUNS, two windows are held to an EARLIER moment of the same ROM run, and still byte for
    byte: the dispatcher's stack and the Line-F mask word are written, in the host's run too, by the foreign
    process's own ROM code — up to where the ROM's disp is about to enter the caller again, which is where the
    model's nested run ends — so the C's image holds there what the ROM's run holds AT THAT INSTRUCTION
    (`_where_the_dispatcher_hands_back`), not what its own switchto and the caller's tail then make of it."""
    made = settled(row)
    reference = scheduled(row, made.pokes)
    signature = vdi.ALCYON[row.name]
    foreign = any(pd != made.switches.process for pd in reference.entered)
    expected = reference.memory
    if foreign:
        expected = bytearray(expected)
        for lo, held in _where_the_dispatcher_hands_back(row, made).items():
            expected[lo:lo + len(held)] = held
    ran = aes_switch.modelled(_core(row), vdi.as_signed(row.name, row.arguments), made.pokes, reference,
                              answered=row.answered and signature.restype is not None, foreign=foreign)
    who = row_name(row)
    assert reference.ended == aes_switch.RETURNED and ran.returncode == 0, (
        f"{who}: the ROM's run returned; the C's fork ended {ran.returncode}:\n{ran.stderr}")
    assert ran.idles == reference.idles, f"{who}: the C's run idled {ran.idles} times, the ROM's {reference.idles}"
    answer_bits = aes.RESULT_WIDTHS[signature.restype] if row.answered else case.NO_RESULT
    if answer_bits:
        mask = (1 << answer_bits) - 1
        assert ran.answer & mask == reference.d0 & mask, f"{who}: answers {ran.answer & mask:#x}, the ROM's run {reference.d0 & mask:#x}"
    differ = aes_event.differing(ran.image, expected, frozenset(case.STACK_BAND))
    assert not differ, f"{who}: " + aes_event.describe_differences(who, ran.image, expected, differ)
    return CompanionRun(made.pokes, switches_of(reference), ran.answer)


def register(label, name, arguments, machine, at_idle=None, *, answered=True):
    """ONE PRICED ROW THAT SWITCHES, registered (`aes.ROWS`, `aes_event.SWITCHING_ROWS`): settled from the ROM's own
    runs, its `Switches` the ninth field every run of it is taken through, its by-nature windows dropped at Tier 3
    with the companion a drop needs. `arguments` `()` for a routine of none; `answered` False for an arm that sets
    no D0. The `SwitchingRow`."""
    row = SwitchingRow(label, name, tuple(arguments), machine, dict(at_idle or {}), answered)
    made = settled(row)
    aes_event.SWITCHING_ROWS[row_name(row)] = Registered(row, made.pokes, made.drops, made.switches, made.entered,
                                                         functools.partial(rederived, row))
    aes.ROWS.register(row_name(row), _entry(row), made.pokes, dropped=made.drops,
                      undropped=functools.partial(companion, row), delivered=made.switches, answered=answered)
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
    return tier3.switching_run_on(blob, row_name(row), _entry(row), _core(row), (0, *row.arguments), made.pokes,
                                  made.switches, returns=returns, dropped=made.drops)
