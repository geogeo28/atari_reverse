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
import aes_shell
import aes_switch
import aes_accessory_turns_pinned
import aes_desk_turns_pinned
import aes_takeover
import aes_turns_pinned
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
# WHOSE CODE A PROCESS IS RESUMED IN, read off the run (`Switching._whose`): the PC switchto's `rte` pops lies in the
# blob — OUR process, our build's own frames under it — or in the AES's ROM text: the ROM's.
OURS = "ours"
SCREEN_MANAGER = aes.SCREEN_MANAGER_PD
# WHOSE TURN A WINDOW IS, by WHO is entered (both shores alike: the ROM's shore reads no kind off its PCs): the screen
# manager's, a loaded program's — an accessory's: told apart from the rest ONLY BEHIND A DOOR (`Switching`'s `door`),
# where its turn is our build's code as the screen manager's is —, THE DESK'S (PD0's, on every run of ours since band
# 6's slice B0: the Line-F table is OURS at every Tier 3 run's entry and in the door, so the ROM's desk calls OUR AES
# through it and parks through our dispatcher — a turn OF OURS priced as an accessory's is, ruling W6-R7, the desk's
# own text in its `shared` as an accessory's is), or another process's (an accessory's, on a machine with no door).
THE_MANAGER_S, AN_ACCESSORY_S, ANOTHER_PROCESS_S = "the screen manager's", "an accessory's", "another process's"
THE_DESK_S = "the desk's"
# THE TURNS OF A PROCESS WHOSE OWN TEXT IS THE ROM'S AND RUNS OVER OUR AES ON OUR SHORE (band 6's binding): the desk's,
# and another process's resumed in the ROM's AES text on a machine with no door — priced net of what both shores ran
# of the ROM's text (`tier3.Turn`), their saved context and stack by nature (`foreign_windows_of`).
TEXT_OVER_OUR_AES = (THE_DESK_S, ANOTHER_PROCESS_S)
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
# ...and `text`, the blob's whole span: where a process of OUR build is resumed.
OurDispatcher = namedtuple("OurDispatcher", "poll idle rte text")


def our_dispatcher(blob):
    """`blob`'s own dispatcher (a `RomBench`'s): where its idle polls, and where its switchto enters a process."""
    sized = {symbol.name: symbol for symbol in transcription.symbol_table(blob.elf)}
    idle = sized[OUR_IDLE]
    return OurDispatcher(blob.entry(OUR_POLL), (idle.start, idle.start + idle.size), blob.entry(OUR_SWITCHTO) + RTE_OFFSET,
                         (blob.base, blob.end))


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
    one tuple of differences per window. `observing`: `{PC: observe(memory, sp)}` — further stops of the holder's own,
    in whichever process they are reached. `ledger()`: the addresses the run has stored so far (its write ledger),
    for a holder that must know WHO stored a byte (`stored_outside_the_windows`).

    `takeover`: OUR run is over a machine WHOSE SCREEN MANAGER IS OURS (`aes_takeover`: a row that names its two
    spans). WHOSE EVERY PROCESS ENTERED IS, IS READ OFF THE RUN (`resumed_in`, `window_classes`): the PC switchto's
    `rte` resumes it at lies in the blob (OURS) or in the AES's ROM text (THE_ROM_S) — and a window is OURS (a turn
    of our screen manager: our code, priced by itself) or the ROM's (another process's run, the ROM's own code on
    both shores). REFUSED BY NAME: a PC that is neither's; on a takeover machine, a screen manager resumed in the
    ROM's text (the machine's screen manager is not ours after all); on any other, a foreign process resumed in the
    blob. A window is ONE KIND'S: where the turn passes between the screen manager and another process it closes and
    another opens.
    `door` (band 5 wave 3, the narrow door flip): THE RUN IS OF A ROW MEASURED BEHIND OUR TRAP DOOR — our shore's
    machine a DOOR machine (`aes_boot.ours_of` handed a door: every loaded program entered through our gotopgm,
    trapping into our handler, parked by our dispatcher), the ROM's shore's the ROM-booted one. Said to BOTH shores'
    watches, because it is by WHO is entered that windows are split: AN ACCESSORY'S TURN IS A WINDOW OF ITS OWN
    (`window_whose`: AN_ACCESSORY_S), apart from the desk's — on our shore OUR code (its AES calls our door, marshal,
    switch and routines; its own text the same bytes on both shores), priced by itself as the screen manager's is —
    AND, SINCE BAND 6's SLICE B0, ON EVERY MACHINE, THE DESK'S TURN (`window_whose`: THE_DESK_S; ruling W6-R7): our
    shore's Line-F table is ours at every run's entry, so the ROM's desk calls our AES; its window is A TURN OF OURS on
    our shore wherever the desk resumes (`_class_of`), priced the same way, its own text (the ROM's, on both shores) in
    `shared`. REFUSED BY NAME behind a door: an accessory resumed in the ROM's text (the door did not take it). `programs`: `((pd, (lo, top)), ...)` — each loaded
    program's stack span, as the door's takeover found it: ITS SAVED CONTEXT AND ITS STACK ARE HELD BY CONTENT
    WHEREVER IT DOES NOT RUN, on both shores (below: they are out of every compare of the two, as the screen
    manager's are). `images`: `pages(memory)` — the image's digest, what differs
    by nature left out — taken at every poll and at every resume (`taken`: `(the stop, its ordinal, the pages)`), for
    the holder to compare the two shores stop by stop.

    A DELIVERY NAMED AT AN IDLE OR A POLL THE ROW'S RUN DOES NOT MAKE is refused where the watch is made: it would
    never be laid, and nothing else would say so. One named at a poll that turns out an IDLE is refused there.
    A DOOR CALL OPEN ACROSS A FOREIGN WINDOW is told where the window opens and closes
    (`inner.foreign_window_opened()` / `foreign_window_closed()`): its holder takes the window off the call's own
    cost on each shore (`tier3.DoorWindows`). A call open across a SELF-RESUME needs nothing: the switch is its cost.

    AFTER THE RUN: `idles`, `polls`, `entered` (the PD at each switchto, in order), `resumed_in` (whose code each
    resumed in), `foreign` and `window_classes` (each window's tally, and whose it is), `foreign_codes` (`{slot: the
    ROM routine's address a window stored there}`), `qpbs_seen` (`{an EVB_PARM's address: the QPB it named}`: every
    pipe wait's QPB in the run's own stack, read where the row's process stands parked or is resumed — at an idle,
    whoever's, and at its resume: its frames are live there, which they are not once the call has returned; what
    `vet_our_qpbs` holds a blob's run to), `qpbs_parked` (`{that address: (where the QPB lay, the row's process's
    stack pointer there)}`: a QPB is a local of a LIVE frame — at or above that pointer), and `vet_ended(who)`."""

    def __init__(self, switches, *, inner=None, ours=None, relocated=None, relocated_polls=None, tally=_whole_cycles,
                 observing=None, ledger=None, takeover=False, images=None, door=False, programs=()):
        assert not (ours is None and (relocated or relocated_polls)), "the ROM's shore takes its deliveries as they are"
        assert ours is not None or not takeover, "a machine whose screen manager is ours is OUR shore's"
        assert takeover or ours is None or not door, "a machine behind our door is a takeover machine"
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
        self._window, self._slots_found, self._window_class, self._window_whose = None, None, None, None
        self._takeover, self._images, self.taken = takeover, images, []
        self._door, self._programs = door, dict(programs)
        self._programs_stood, self._program_running = None, None
        self.idles, self.polls, self.entered, self.foreign, self.foreign_codes = 0, 0, [], [], {}
        self.resumed_in, self.window_classes, self.window_whose = [], [], []
        self._manager_stood, self._holding_the_manager_s = None, switches.process != SCREEN_MANAGER
        self.manager_s_states, self._manager_s_stores_seen = [], frozenset()
        self.qpbs_seen, self.qpbs_parked, self._qpbs_at = {}, {}, {}
        self.first = self._armed()

    def _armed(self):
        """The stops as the run stands: the dispatcher's, the pending re-arms, and — while the row's own process
        runs — its door watch's."""
        inner = frozenset() if self._window is not None else self._inner_armed
        return self._polls | self._rtes | frozenset(self._polled) | frozenset(self._observing) | inner

    def stopped(self, pc, sp, memory):
        if self._manager_stood is None and self._window is None and not self.entered:
            self.hold_the_manager_s_spans(memory)       # (a watch nobody handed its run's entry image: from its first stop)
        if self._programs_stood is None:                # ...and every loaded program's, behind a door (all but the one running)
            self._hold_the_programs_spans(memory)
        if pc in self._observing:       # (first: an observed PC may be a stop of the dispatcher's too — a resume's)
            self._observing[pc](memory, sp)
        if pc == self._resumes_at:
            self._resumed(pc, sp, memory)
        elif pc in self._rtes:
            return self._entered(sp, memory)
        elif pc in self._polls:
            self._polling(pc, sp, memory)
        elif pc in self._polled:
            self._polled.discard(pc)    # past the poll: its entry is a stop again
        elif pc not in self._observing:
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
        self._image_taken(A_POLL, poll, memory)
        whose = f"{OUR_OWN if ours else THE_ROM_S} dispatcher, {pc:#x}"
        if not aes_switch.waits_for_an_interrupt(memory):
            if ours or self._ours is None or self._window is not None:
                self._lay((self._at_our_poll if ours else self.switches.at_polls).get(poll), memory, f"poll {poll} ({whose})")
            else:                       # (...as an idle's, below: the ROM's dispatcher's own poll, outside every window)
                self._lay_for_the_rom_s_forker(self.switches.at_polls.get(poll), memory, f"poll {poll} ({whose})")
            return
        self._see_the_qpbs(memory, self._parked_at(memory))
        ordinal, self.idles = self.idles, self.idles + 1
        where = f"idle {ordinal} ({whose})"
        if poll in self.switches.at_polls:
            raise Refused(f"{where}: a delivery is named at poll {poll}, which is this idle — an idle's delivery is "
                          f"named at the idle")
        if ordinal >= self.switches.idles:
            self._past_its_last_idle(where, memory)
        if ours or self._ours is None or self._window is not None:
            self._lay((self._at_our_idle if ours else self.switches.at_idles).get(ordinal), memory, where)
        else:
            self._lay_for_the_rom_s_forker(self.switches.at_idles.get(ordinal), memory, where)

    def _lay_for_the_rom_s_forker(self, delivery, memory, where):
        """ON OUR SHORE, AT THE ROM'S DISPATCHER'S OWN POLL, OUTSIDE EVERY WINDOW (a run from a machine's idle: what
        comes before the first process is entered is taken where the machine stands — in the ROM's dispatcher, at
        its idle or at a poll of that same dispatch): the fork codes `delivery` queues are the ROM's, for the ROM's
        forker, and no relocation of ours wrote them — kept as a window's are (`foreign_codes`)."""
        found = self._code_slots(memory)
        self._lay(delivery, memory, where)
        self.foreign_codes.update({slot: code for slot, code in self._code_slots(memory).items()
                                   if code != found[slot] and code in ROM_CODES})

    def _past_its_last_idle(self, where, memory):
        """The machine idles with every idle of the ROM's run made: a CALL's run would block for ever — refused."""
        raise Refused(
            f"{where}: the dispatcher idles once more than the ROM's own run did ({self.switches.idles}) — the "
            f"call would block, the machine waiting for an interrupt no case delivers")

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

    def _whose(self, pc):
        """WHOSE CODE the process just entered resumes in, READ OFF THE RUN: OURS inside the blob, THE_ROM_S inside
        the AES's ROM text — None anywhere else."""
        text = self._ours.text if self._ours is not None else None
        if text is not None and text[0] <= pc < text[1]:
            return OURS
        return THE_ROM_S if aes.AES_TEXT[0] <= pc < aes.AES_TEXT[1] else None

    def _vet_whose(self, whose, pc):
        """A FOREIGN PROCESS RESUMED IN CODE THE MACHINE DOES NOT SAY IT RUNS IS REFUSED BY NAME (the class's
        docstring): the classification is read off the run, and held to what the machine is."""
        entered = f"the process at {self._entering:#x}"
        if whose is None:
            raise Refused(f"{entered} is resumed at {pc:#x}: neither in the blob nor in the AES's ROM text "
                          f"[{aes.AES_TEXT[0]:#x}, {aes.AES_TEXT[1]:#x}) — nobody's code that a window is priced as")
        if self._takeover and self._entering == SCREEN_MANAGER and whose != OURS:
            raise Refused(f"A ROW ON A TAKEOVER MACHINE WHOSE SCREEN MANAGER RESUMES IN THE ROM'S TEXT ({pc:#x}): the "
                          f"machine's screen manager was to be ours (`aes_takeover`), and it stands parked in the "
                          f"ROM's frames — its turn would be the ROM's code, priced as a window of ours")
        its = self._whose_turn(self._entering)
        if not self._takeover and whose == OURS and its != THE_DESK_S:
            raise Refused(f"{entered}, ANOTHER PROCESS than the row's, is resumed IN OUR BUILD'S TEXT ({pc:#x}) on a "
                          f"machine whose screen manager is not ours: a foreign window is the ROM's own code")
        if whose == OURS and its not in (THE_MANAGER_S, AN_ACCESSORY_S, THE_DESK_S):
            raise Refused(f"{entered}, A PROCESS THAT IS NOT THE SCREEN MANAGER, is resumed IN OUR BUILD'S TEXT ({pc:#x}) "
                          f"on a machine with no door of ours: the one process of a machine that is ours is its screen "
                          f"manager — this window would be priced as a turn of ours")
        if self._door and self._takeover and its == AN_ACCESSORY_S and whose != OURS:
            raise Refused(f"A ROW BEHIND OUR DOOR WHOSE ACCESSORY RESUMES IN THE ROM'S TEXT ({pc:#x}; {entered}): the "
                          f"door was to have taken every loaded program (`aes_boot.ours_of`, handed a door), and this one "
                          f"stands parked by the ROM's trap handler — its turn would be the ROM's code, priced as ours")

    def _whose_turn(self, pd):
        """WHOSE TURN the process `pd`'s is (THE_MANAGER_S, THE_DESK_S, AN_ACCESSORY_S, ANOTHER_PROCESS_S), by who it
        is — an accessory's told from another process's only behind a door (the module's note)."""
        if pd == SCREEN_MANAGER:
            return THE_MANAGER_S
        if pd == aes.SHELL_PD:
            return THE_DESK_S
        return AN_ACCESSORY_S if self._door else ANOTHER_PROCESS_S

    def _class_of(self, whose, its):
        """THE KIND OF A WINDOW: whose code the process resumed in — but, ON OUR SHORE, A TURN OF A PROCESS WHOSE TEXT
        IS THE ROM'S (the desk's; another process's on a machine with no door, resumed in the ROM's AES where the ROM's
        dispatcher parked it), which is a turn OF OURS whatever it resumes in: our Line-F table is under every Line-F
        call its text makes (`TEXT_OVER_OUR_AES`)."""
        return OURS if its in TEXT_OVER_OUR_AES and self._ours is not None else whose

    def _resumed(self, pc, sp, memory):
        self._resumes_at = None
        foreign = self._entering != self.switches.process
        whose = self._whose(pc)
        self.resumed_in.append(whose)
        self._image_taken(A_RESUME, len(self.resumed_in) - 1, memory)
        if foreign:
            self._vet_whose(whose, pc)
        self._a_program_resumed(memory)
        # A WINDOW IS ONE KIND'S: it closes where the row's own process is resumed — and where the turn passes
        # BETWEEN THE SCREEN MANAGER AND ANOTHER PROCESS (its turn, then the desk's or an accessory's: two windows,
        # each priced as what it is). Split by WHO is entered, on both shores alike — the ROM's shore reads no kind
        # off its PCs — and so by kind on ours (`_vet_whose` holds the two to agree).
        its = self._whose_turn(self._entering)
        klass = self._class_of(whose, its)
        if its == THE_MANAGER_S:        # ...its own turn begins: what it stood parked in must be as it left it
            self.vet_the_manager_s_spans_stood(memory, f"where the screen manager is resumed at {pc:#x}", handed_back=True)
            self._manager_stood = None
        if self._window is not None and (not foreign or klass != self._window_class or its != self._window_whose):
            self._close_the_window(memory)
        if foreign and self._window is None:
            if klass != OURS:           # ...the dispatcher changes hands at a window of the ROM's code alone
                self._vet_no_fork_is_queued(memory, "entered")
            self._stores_outside_so_far()
            self._window, self._slots_found, self._window_class = self._tally(), self._code_slots(memory), klass
            self._window_whose = its
            if self.inner is not None:
                self.inner.window_class = klass
                self.inner.foreign_window_opened()
        if not foreign:
            self._see_the_qpbs(memory, sp)

    def _close_the_window(self, memory):
        """The open window closed where the machine stands: its tally kept under its kind."""
        if self._window_whose == THE_MANAGER_S:
            self.hold_the_manager_s_spans(memory, its_turn_ended=True)
        if self._window_class == OURS:  # ...a turn of OUR screen manager: its stores are our build's own
            self._stores_outside_so_far()
        else:
            self._vet_no_fork_is_queued(memory, "left")
            self._stores_seen = self._stores_now()          # ...the window's own stores: seen, and nobody's of ours
            self.foreign_codes.update({slot: code for slot, code in self._code_slots(memory).items()
                                       if code != self._slots_found[slot] and code in ROM_CODES})
        self.foreign.append(tuple(now - then for now, then in zip(self._tally(), self._window)))
        self.window_classes.append(self._window_class)
        self.window_whose.append(self._window_whose)
        self._window = self._slots_found = self._window_class = self._window_whose = None
        if self.inner is not None:
            self.inner.foreign_window_closed()

    # ---- THE SCREEN MANAGER'S SAVED CONTEXT AND ITS STACK ARE ITS OWN: nobody else stores there ----
    # Its two spans (`aes_takeover.spans_of`) are, on a row whose screen manager is ours, left out of every compare of
    # the two shores — two builds' frames. What that may not hide is A STORE THERE BY ANYBODY BUT THE SCREEN MANAGER:
    # the row's own process, another process, the dispatcher outside its turn. So the spans are HELD BY CONTENT from
    # where its turn ends (the next process resumed: its savestate is done) to where its next begins (it is resumed:
    # switchto has read them), from the run's entry to its first turn, and from its last to where the run ends — on
    # BOTH shores, whoever's the screen manager is: not one byte may change (REFUSED BY NAME where one has, with the
    # bytes, at the stop that finds it: the run goes no further on a screen manager somebody else wrote into) — BUT THE ONE WORD THE DISPATCHER STORES AS IT HANDS THE MACHINE BACK: the SR
    # of the exception frame switchto's `rte` pops, AT THE STACK POINTER THE SCREEN MANAGER STOOD PARKED AT (measured
    # on every row that switches, both shores, both blobs: `$2304 -> $2700` there and nothing else, ever). Excepted
    # where it is resumed alone, by its address; it is dead by nature — rewritten at every resume. (A row whose own
    # process IS the screen manager — a handler at an arrival of ctlmgr's — holds nothing here: its own dispatches
    # store its context.)
    # BY CONTENT — AND, WHERE THE RUN HAS A LEDGER (our shore's), BY THE LEDGER TOO: a store that leaves the byte it
    # found (the same constant, twice) changes no content, so the addresses of the two spans FIRST STORED OUTSIDE THE
    # SCREEN MANAGER'S TURNS must be none either, the dispatcher's word aside. (The C mutant that showed it: a stray
    # store our screen manager's own boot had already made — the overlay carried the byte, and the row's process
    # storing it again changed nothing.) WHAT NEITHER SEES: an address the screen manager itself stored IN THIS RUN,
    # stored again by another process with the value it holds.
    def hold_the_manager_s_spans(self, memory, its_turn_ended=False):
        """The screen manager stands parked over `memory` — `its_turn_ended`: its own turn has just ended, and what the
        run has stored in the two spans so far is its turns' — or the run begins (nothing stored there is anybody's
        yet): its two spans kept as they are."""
        if self._holding_the_manager_s:
            at = aes_takeover.spans_of(memory)
            self._manager_stood = tuple((lo, bytes(memory[lo:hi])) for lo, hi in (at.context, at.stack))
            self._manager_parked_at = at.parked
            self.manager_s_states.append(aes_takeover.state_of(memory))
            self._manager_s_stores_seen = self._stores_in_the_manager_s_spans() if its_turn_ended else frozenset()

    def _stores_in_the_manager_s_spans(self):
        """The addresses of the two spans the run has stored so far (its ledger) — none, for a run with no ledger."""
        if not self._ledger or self._manager_stood is None:
            return frozenset()
        spans = [(lo, lo + len(held)) for lo, held in self._manager_stood]
        return frozenset(at for at in self._ledger() if any(lo <= at < hi for lo, hi in spans))

    def vet_the_manager_s_spans_stood(self, memory, where, handed_back=False):
        """...and are they as they were kept, `where` the run now stands? REFUSED BY NAME where they are not, with the
        bytes. `handed_back`: the dispatcher has just resumed the screen manager — the SR word of its `rte`'s frame
        is the dispatcher's."""
        if self._manager_stood is None:
            return
        its_rte_s_sr = range(self._manager_parked_at, self._manager_parked_at + aes.WORD_BYTES) if handed_back else ()
        moved = {lo + offset: (kept, memory[lo + offset]) for lo, held in self._manager_stood
                 for offset, kept in enumerate(held) if memory[lo + offset] != kept and lo + offset not in its_rte_s_sr}
        # ...and what the ledger says was stored there since, whatever value it left (the same byte, stored again)
        moved.update({at: (memory[at], memory[at]) for at in self._stores_in_the_manager_s_spans() - self._manager_s_stores_seen
                      if at not in its_rte_s_sr and at not in moved})
        if moved:
            whose = "OUR" if self._ours is not None else "THE ROM'S"
            raise Refused(
                f"IN {whose} RUN, {where}, THE SCREEN MANAGER'S SAVED CONTEXT OR ITS "
                f"STACK HOLDS OTHER BYTES THAN ITS OWN LAST TURN LEFT — stored by another process's code, or by the "
                f"dispatcher outside its turn (on a row whose screen manager is ours these bytes are out of every "
                f"compare of the two shores: a stray store there crashes it at its next wake): "
                + ", ".join(f"{at:#x} ({kept:#04x} -> {found:#04x})" for at, (kept, found) in sorted(moved.items())[:8])
                + (f" and {len(moved) - 8} more" if len(moved) > 8 else "")
                + " (a byte shown unchanged was STORED, by the run's ledger, with the value it held)")

    # ---- EVERY LOADED PROGRAM'S SAVED CONTEXT AND STACK ARE ITS OWN, behind a door: nobody else stores there ----
    # Behind our door each accessory's two spans (its UDA's saved context; its stack, from the UDA's state block to
    # the top psetup's frame was laid under) are two builds' frames, out of every compare of the two shores as the
    # screen manager's are. What that may not hide is A STORE THERE BY ANYBODY ELSE: so each program's spans are HELD
    # BY CONTENT, on both shores, from where the run's watch first stops (every program but the one running) and from
    # where each program's turn ENDS (the next process resumed: its savestate is done) to where it is next RESUMED —
    # and where the run ends (`vet_the_programs_spans_stood`). Excepted, as the screen manager's: the SR word of the
    # `rte` frame at the stack pointer it stood parked at, where it is resumed. BY CONTENT ALONE (no ledger half: a
    # store that leaves the byte it found is not seen here).
    def _program_s_spans(self, pd, memory):
        uda = aes_event.uda_of(pd, memory)
        (lo, hi, _why), = aes_switch.uda_context_drop(uda)
        return (lo, hi), self._programs[pd]

    def _hold_a_program_s_spans(self, pd, memory):
        parked = case.long_in(memory, aes_event.uda_of(pd, memory) + aes.UDA_SUPER_SP) & BUS
        self._programs_stood[pd] = (parked, tuple((lo, bytes(memory[lo:hi])) for lo, hi in self._program_s_spans(pd, memory)))

    def _hold_the_programs_spans(self, memory):
        """The run's first stop: every loaded program but the one running stands parked — its spans kept."""
        self._programs_stood = {}
        running = case.long_in(memory, aes.AES_RLR) & BUS
        self._program_running = running if running in self._programs else None
        for pd in self._programs:
            if pd != running:
                self._hold_a_program_s_spans(pd, memory)

    def _vet_a_program_s_spans_stood(self, pd, memory, where, handed_back=False):
        parked, stood = self._programs_stood[pd]
        its_rte_s_sr = range(parked, parked + aes.WORD_BYTES) if handed_back else ()
        moved = {lo + offset: (kept, memory[lo + offset]) for lo, held in stood
                 for offset, kept in enumerate(held) if memory[lo + offset] != kept and lo + offset not in its_rte_s_sr}
        if moved:
            whose = "OUR" if self._ours is not None else "THE ROM'S"
            raise Refused(
                f"IN {whose} RUN, {where}, THE SAVED CONTEXT OR THE STACK OF THE PROGRAM AT {pd:#x} HOLDS OTHER BYTES THAN "
                f"ITS OWN LAST TURN LEFT — stored by another process's code, or by the dispatcher outside its turn "
                f"(behind our door these bytes are out of every compare of the two shores): "
                + ", ".join(f"{at:#x} ({kept:#04x} -> {found:#04x})" for at, (kept, found) in sorted(moved.items())[:8])
                + (f" and {len(moved) - 8} more" if len(moved) > 8 else ""))

    def _a_program_resumed(self, memory):
        """A process is resumed: the program that ran until now (if one did) stands parked — its spans kept from
        here; and the one resumed (if it is one) must stand as its last turn left it."""
        if not self._programs:
            return
        if self._programs_stood is None:
            self._hold_the_programs_spans(memory)
        before, self._program_running = self._program_running, self._entering if self._entering in self._programs else None
        if before is not None and before != self._entering:
            self._hold_a_program_s_spans(before, memory)
        if self._entering in self._programs_stood:
            self._vet_a_program_s_spans_stood(self._entering, memory, f"where the program at {self._entering:#x} is resumed",
                                              handed_back=True)
            del self._programs_stood[self._entering]

    def vet_the_programs_spans_stood(self, memory, where):
        """...and where the run ends (`memory`): every program that does not run stands as its last turn left it."""
        for pd in self._programs_stood or ():
            self._vet_a_program_s_spans_stood(pd, memory, where)

    def _image_taken(self, stop, ordinal, memory):
        if self._images is not None:
            self.taken.append((stop, ordinal, self._images(memory)))

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
        """The addresses this run stored OUTSIDE every window OF THE ROM'S CODE — first stored there, or before one
        (asked once the run has ended; `ledger` given): OUR BUILD'S OWN STORES, a turn of our own screen manager's
        among them. CONSERVATIVE: an address a ROM window stored and our code stored only AFTER it is not among
        them (the ledger keeps no order) — a drop that stands on such a store is refused, never passed."""
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


A_POLL, A_RESUME = "poll", "resume"     # the stops an image is taken at (`Switching.taken`)
AN_ARRIVAL = "arrival"                  # ...and, of a run ended at one, the arrival itself (`ToAnArrival`)


class IdleToIdle(Switching):
    """A WATCH OVER A RUN FROM A MACHINE'S IDLE TO ITS NEXT (ctlmgr's own rows: `aes_ctlmgr`), for either shore: the
    dispatcher's loop entered where the booted machine stands idle, the row's deliveries laid at its idles (and its
    polls) as `Switching` lays them, EVERY process entered followed — and THE RUN HAS NO PROCESS OF ITS OWN
    (`switches.process` is None): every turn is a window, of the kind read off the run — our screen manager's (on a
    machine whose screen manager is ours) or the ROM's process's. IT ENDS (`aes_event.Ended`) where the machine idles
    with every delivery taken: the window open there is closed (the dispatch that brings the machine to its idle is
    the last turn's), and `ended` is the holder's tally at that instant — the whole run's totals."""

    def __init__(self, switches, **watching):
        assert switches.process is None, "a run from idle to idle is no process's own: every turn is a window"
        super().__init__(switches, **watching)
        self.ended = None

    def _past_its_last_idle(self, where, memory):
        if self._window is not None:
            self._close_the_window(memory)
        self.ended = self._tally()
        raise aes_event.Ended

    def _parked_at(self, memory):
        return 0

    def _see_the_qpbs(self, memory, sp):
        """(No process of the run's own: no QPB of its own stack to follow.)"""

    def vet_ended(self, who):
        """THE RUN ENDED AT THE IDLE AFTER ITS LAST DELIVERY, every idle and every poll of the ROM's run made."""
        if self.ended is None or self._resumes_at is not None or self._window is not None:
            raise Refused(f"{who}: the run did not end at the machine's idle")
        if (self.idles, self.polls) != (self.switches.idles + 1, self.switches.polls):
            raise Refused(f"{who}: the run made {self.idles - 1} idle(s) with a delivery and {self.polls} poll(s) where "
                          f"the ROM's own makes {self.switches.idles} and {self.switches.polls}")


class ToAnArrival(IdleToIdle):
    """`IdleToIdle`, ENDED AT THE `which`-TH ARRIVAL AT `entry` — a handler of the screen manager's met where its
    caller calls it: the ROM's routine on the ROM's shore, its C core's first instruction on ours — `arrived` what
    `read(memory, sp)` reads of the frame there, the image taken at that stop too. An earlier arrival is passed (the
    entry is a stop again from where that call comes back to). A machine that idles with every delivery taken and
    no such arrival made is refused by name."""

    def __init__(self, switches, entry, which, read, **watching):
        super().__init__(switches, **watching)
        self._entry, self._left, self._read, self._back, self.arrived = entry, which, read, None, None
        self._observing[entry] = None
        self.first = self._armed()

    def stopped(self, pc, sp, memory):
        if pc == self._entry:
            if not self._left:
                self._image_taken(AN_ARRIVAL, 0, memory)
                self.arrived, self.ended = self._read(memory, sp), self._tally()
                raise aes_event.Ended
            self._left, self._back = self._left - 1, case.long_in(memory, sp) & BUS
            del self._observing[pc]
            self._observing[self._back] = None
            return self._armed() - {pc}
        if pc == self._back:
            del self._observing[pc]
            self._observing[self._entry], self._back = None, None
            return self._armed() - {pc}
        return super().stopped(pc, sp, memory)

    def _past_its_last_idle(self, where, memory):
        raise Refused(f"{where}: the machine idles with every delivery taken and the handler at {self._entry:#x} was "
                      f"never called: the screen manager did not arrive there")

    def vet_ended(self, who):
        """THE RUN ENDED AT THE ARRIVAL, every idle and every poll of the ROM's run up to it made."""
        if self.arrived is None or (self.idles, self.polls) != (self.switches.idles, self.switches.polls):
            raise Refused(f"{who}: the run made {self.idles} idle(s) and {self.polls} poll(s) and "
                          f"{'arrived' if self.arrived is not None else 'never arrived'}, where the ROM's own arrives after "
                          f"{self.switches.idles} and {self.switches.polls}")


class ThroughAHandler:
    """A WATCH OVER A RUN FROM A MACHINE'S IDLE THAT ARRIVES AT A HANDLER OF THE SCREEN MANAGER'S AND GOES ON THROUGH
    IT, TO ITS RETURN — for either shore: the row of a handler MEASURED WHERE ITS OWN ctlmgr CALLS IT, on the screen
    manager's real stack (`bench/tier3.py`'s `at_its_arrival_on`). Two watches of this module in turn, neither changed:

      * `arriving` (a `ToAnArrival`) until the arrival: the chain's deliveries, every process followed, the frame read;
      * `handling(memory, sp)` — made AT the arrival, the machine as it stands there — from the arrival on: the
        `Switching` of the handler's own run (the screen manager its process; its door watch inside), exactly the
        watch a kit call of the handler is followed by, so its idles, polls and door calls are numbered from the
        handler's entry and the row's own deliveries are laid where a call's are.

    THE RETURN is the address the handler's caller left at the stack pointer of the arrival, REACHED WITH THAT FRAME
    POPPED (the stack pointer one longword above the arrival's: the same address reached deeper is no return of this
    call): the run ENDS there (`aes_event.Ended`). `mark()`: the holder's running totals — taken at the arrival
    (`arrived_at`) and at the return (`returned_at`): the row is the difference. NOTHING ELSE ENDS THE RUN: one whose
    handler never comes back is refused by its handling watch (an idle the row's own run does not make) or by the
    run's budget, one that idles before the arrival by `arriving`; and what each watch saw is its own to vet
    (`arriving.vet_ended`, `handling.vet_ended`)."""

    def __init__(self, arriving, handling, mark):
        self.arriving, self._handling_of, self._mark = arriving, handling, mark
        self.handling, self.arrived_at, self.returned_at = None, None, None
        self._returns_to, self._returned_sp = None, None
        self.first = arriving.first

    def stopped(self, pc, sp, memory):
        if self.handling is None:
            try:
                return self.arriving.stopped(pc, sp, memory)
            except aes_event.Ended:     # ...the arrival: the handler's own run begins where the chain's ends
                self._returns_to, self._returned_sp = case.long_in(memory, sp) & BUS, sp + aes.LONG_BYTES
                self.arrived_at = self._mark()
                self.handling = self._handling_of(memory, sp)
                return (frozenset(self.handling.first) | {self._returns_to}) - {pc}
        if pc == self._returns_to and sp == self._returned_sp:
            self.returned_at = self._mark()
            raise aes_event.Ended
        return (frozenset(self.handling.stopped(pc, sp, memory)) | {self._returns_to}) - {pc}


def _refuse_what_is_never_made(kind, named, made):
    """A delivery named at an idle / a poll (`kind`) outside the `made` ones the ROM's own run counts: `Refused`."""
    never_made = sorted(ordinal for ordinal in named if not 0 <= ordinal < made)
    if never_made:
        raise Refused(f"a delivery is named at {kind} {never_made} of a run that makes {made} {kind}(s): it would never "
                      f"be laid")


def the_rom_s(switches, entered_at=None, tally=_whole_cycles, inner=None, observing=None, images=None, door=False,
              programs=()):
    """THE ROM'S SHORE: the watch of the ROM's own run of a row that switches. `entered_at` and `inner`: its door
    watch — given, or made here where the row has door-call deliveries too (one that does not `block`). `door`,
    `programs`: the row is measured behind our door (`Switching`'s)."""
    if inner is None and switches.at_calls:
        inner = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS, delivered=switches.at_calls,
                                    entered_at=entered_at)
    return Switching(switches, inner=inner, tally=tally, observing=observing, images=images, door=door, programs=programs)


def ours(blob, switches, relocated, tally=_whole_cycles, inner=None, ledger=None, relocated_polls=None, takeover=False,
         images=None, door=False, programs=(), observing=None):
    """OUR SHORE, on `blob`: `relocated` the row's idle deliveries as our own dispatcher takes them,
    `relocated_polls` those it takes at a poll that is no idle; `takeover`: over a machine whose screen manager is
    ours (`aes_takeover`); `door`, `programs`: and whose trap door is (`Switching`'s); `observing` its further stops."""
    return Switching(switches, inner=inner, ours=our_dispatcher(blob), relocated=relocated,
                     relocated_polls=relocated_polls, tally=tally, ledger=ledger, takeover=takeover, images=images,
                     door=door, programs=programs, observing=observing)


# ---- THE REGISTRAR: a row that blocks and is woken ------------------------------------------------------------------------
# `name`, `arguments`, `machine` (a zero-argument builder: the scheduler's own, a running process), `at_idle` (`{idle:
# interrupt}`, as `aes_switch.scheduled` takes them). Everything else is DERIVED from the ROM's own runs.
# `answered` False for a routine that sets no D0 on the row's arm (it leaves its caller's, which no C is handed).
# `at_polls`: `{poll: interrupt}` — what arrives at a poll of the dispatcher that is no idle (`aes_switch.scheduled`).
# `budget`: the row's own derivation budget, DECLARED from its measured run (`aes_event._budget_of`: a session too long
# for the default's margin — the file selector's); every ROM run that derives the row is held to it, both ways.
# `child_doors`: source the row's Tier 1 fork runs first (`aes_event.CHILD_DOORS`' kind: `lib` the candidate it
# loaded) — for a routine that SWITCHES AND REACHES A DOOR OF ITS OWN (a `trap #1` under a scripted GEMDOS) but makes
# NO DOOR CALL of the event layer: it is no door user (`door` stays None — a door user's row is held to arrive at a
# door entry), and its companion binds that door all the same.
# `x_flag_differs`: the row DECLARES that the X flag its yield parks in the dispatcher's save word differs between
# the two builds by nature (`THE_X_FLAG_ALONE`, below: what that excuses, and how a declaration no row needs is
# refused).
# `also_dropped`: `((lo, hi, why), ...)` THE ROW'S OWN by-nature bytes beside the windows every switching row has —
# bytes BOTH builds store, each its own by nature (ct_mouse's re-show under a menu worked with the mouse shown:
# contrl[3] is the ROM's stack word and the C's named one). Dropped at Tier 3 by name, held to OUR run's ledger as
# every drop is; LEFT OUT OF THE COMPANION'S COMPARE TOO — the one place a companion leaves a stored byte out beside
# a QPB's address — each byte required to be one the ROM's run stored (`_its_own_by_nature`), and the battery that
# declares it holds what the C stores there.
# `the_rom_s_screen_manager`: WHY A ROW WHOSE RUN ENTERS THE SCREEN MANAGER STAYS ON THE ROM'S (`settled`: every other
# such row is run, on our shore, with the screen manager OURS — `aes_takeover`): a reason, said in the row's battery
# and counted by `test_aes_takeover.py`; "" for every other row.
SwitchingRow = namedtuple("SwitchingRow", "label name arguments machine at_idle answered at_calls door at_polls budget "
                                          "child_doors x_flag_differs also_dropped the_rom_s_screen_manager",
                          defaults=(True, None, None, None, None, "", False, (), ""))
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


def scheduled(row, pokes, at_stops_only=()):
    """The ROM's own run of `row` through its dispatcher over `pokes` (its machine, staged): `aes_switch.scheduled`.
    `at_stops_only`: windows left out of the images taken at its stops beside the row's own (`companion`'s)."""
    return aes_switch.scheduled(_entry(row), pokes.get(abi.FIRST_ARG, NO_FRAME), pokes, row.at_idle,
                                at_calls=row.at_calls, at_polls=row.at_polls, budget=row.budget,
                                left_out_beside=(*row.also_dropped, *at_stops_only))


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
    are the ROM's instructions in both builds, and park the same word — but for ONE BIT of it on a row that
    DECLARES so (`THE_X_FLAG_ALONE`, below: `settled` adds it)."""
    return (*aes.LINE_F_MASK_WINDOW, *aes_switch.uda_context_drop(uda), *aes_switch.DISPATCHER_STACK_DROP,
            *aes_event.sr_drops(aes.AES_SR_SPL))


# THE X FLAG IN THE DISPATCHER'S SAVE WORD, ON A ROW THAT DECLARES IT (`SwitchingRow.x_flag_differs`) — AND ON NO
# OTHER. dsptch pushes its caller's status register, nothing on a yield's path through disp changes X, and switchto
# parks the SR it is entered under: where a yield comes AFTER arithmetic of the caller's own, X there is Alcyon's in
# the ROM and GCC's in ours (measured: the desk's rsrc_free binding where GEMDOS frees the block — GCC's `seq` /
# `neg` over rs_free's answer: `$8995` holds `$00` on the ROM's shore and `$10` on ours). MEASURED OVER THE WHOLE
# REGISTRY: 294 of 298 switching runs hold the byte EQUAL; only those two rows, on both blobs, differ — so this is no
# kind of every row's (a blanket drop hid a byte that was compared and equal on 147 rows, and "held to both ledgers"
# proved nothing of it: both stores are the same transcribed instructions).
#   * A ROW DECLARES IT, and names it in its drops (the table prints the line under that row alone);
#   * ONE BIT is excused, `$10` of `$8995`: N, Z, V and C and the SYSTEM byte `$8994` stay compared;
#   * NO SPAN IS DROPPED from the compare. Tier 3 FLIPS that bit in the image our run leaves and compares the byte
#     WHOLE (`tier3.RomBench.measure`): equal exactly when the two shores differ in X and in nothing else. So a
#     declaring row whose bytes are equal WITHOUT the flip — a drop it does not need — is refused, as is a wrong C
#     bit beside a differing X, and a non-declaring row whose X differs is refused as any byte is.
CONDITION_CODE_BYTE = 1                 # of a status-register word: its low byte
X_FLAG = 0x10                           # the 68000's extend flag in the condition-code byte
X_FLAG_AT = aes.AES_SR_DISPATCH + CONDITION_CODE_BYTE
THE_X_FLAG_ALONE = ((X_FLAG_AT, X_FLAG_AT + 1,
                     "the X flag ($10) ALONE of the dispatcher's SR save word's condition codes: the caller's last "
                     "arithmetic's — Alcyon's in the ROM, GCC's in a build; the other seven bits compared"),)


def _replayed(row, staged):
    """THE ROM'S RUN OF `row` over `staged`, TWICE AND HELD ONE: the scheduled run, which takes the interrupts, and
    its replay — one watched run laying them at no cost — which has a ledger: `(the scheduled run, the replay's
    watch, its memory, its write ledger)`."""
    reference = scheduled(row, staged)
    assert reference.ended == aes_switch.RETURNED, f"{row.name}: the ROM's scheduled run does not return ({reference.ended})"
    return (reference, *_replay_of(row, staged, reference))


def _replay_of(row, staged, reference):
    """THE REPLAY of `reference`, the ROM's scheduled run of `row` over `staged` — one watched run laying its
    deliveries at no cost, held to have left the memory the scheduled run left: `(its watch, its memory, its write
    ledger)`."""
    watch = the_rom_s(switches_of(reference), _entry(row))
    final, writes, _regs = rom_bench.watched_original(make_image(staged), _entry(row), watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {row.name} through its dispatcher")
    watch.vet_ended(f"the ROM's replay of {row.name}")
    assert bytes(final[:addrs.ST_RAM_BYTES]) == bytes(reference.memory[:addrs.ST_RAM_BYTES]), (
        f"{row.name}: the replay that lays the deliveries is not the run that took them")
    return watch, final, writes


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
    left = {at: data for at, data in _left(name, tuple(arguments), machine, dict(at_idle)).items()
            if at not in case.STACK_BAND}
    aes_takeover.note(name, arguments, machine, at_idle, left)     # ...where it left the screen manager another state
    return left


# THE DESK'S TWO SPANS BY NATURE (band 6 slice B0, ruling W6-R7): on our shore the ROM's desk calls our AES through
# our table and parks through our dispatcher, so — as for a screen manager of ours (`aes_takeover`) — PD0's SAVED
# CONTEXT in its UDA (savestate's: the CPU state of the AES routine that called dsptch, the ROM's on its shore, ours on
# ours) and ITS STACK below the desk's own frames (each build's AES frames under them, other depths) differ by nature.
DESK_CONTEXT_WHY = ("THE DESK'S saved context in PD0's UDA, its turn ours (band 6's binding: savestate's — the CPU state of "
                    "the AES routine that called dsptch, the ROM's on its shore, our build's on ours); dropped WHOLE")
DESK_STACK_WHY = ("THE DESK'S own stack, its turn ours (band 6's binding): each build's AES frames under the desk's own "
                  "(the ROM's routines' on its shore, our build's on ours — other depths)")
# ...and A WAIT OF THE DESK'S WHOSE PARAMETER NAMES A PLACE IN ITS OWN STACK (a message wait keeps its QPB's address:
# a local of the AES's frame under the desk's — two builds' frames, two addresses), the doors' own class for PD0.
DESK_PARKED_WHY = "a wait's parameter in an EVB: an address in THE DESK'S own stack, two builds' AES frames under it"
DESK_WHYS = (DESK_CONTEXT_WHY, DESK_STACK_WHY, DESK_PARKED_WHY)


# ...AND THE SAME TWO SPANS OF THE SPARE STATIC PD (`AES_PD_TABLE`'s third: the first accessory's, where one is
# loaded) when a run resumes it in the ROM's AES text on a machine with no door: its turn runs over our AES too.
SPARE_PD = aes.AES_PD_TABLE + 2 * aes.PD_BYTES
OTHER_CONTEXT_WHY = ("ANOTHER PROCESS'S saved context in its UDA, its turn over our AES (band 6's binding: savestate's — the "
                     "ROM's on its shore, our build's on ours); dropped WHOLE")
OTHER_STACK_WHY = ("ANOTHER PROCESS'S own stack, its turn over our AES (band 6's binding): each build's AES frames under the "
                   "ROM's text it resumed in")
STACK_TOPS = {aes.SHELL_PD: aes.AES_UDA1, SPARE_PD: aes.AES_UDA2_STACK_TOP}     # each static UDA's top: the next's, or its own
WHYS_OF = {aes.SHELL_PD: (DESK_CONTEXT_WHY, DESK_STACK_WHY), SPARE_PD: (OTHER_CONTEXT_WHY, OTHER_STACK_WHY)}


def foreign_windows_of(pd, image):
    """THE TWO SPANS of the static process `pd` (the desk, or the spare PD) over `image`, as `(lo, hi, why)` windows,
    through its own pointer to its UDA: its saved context, and its stack from the UDA's state block to its top.
    REFUSED BY NAME for any other process: a run that resumes one in the ROM's text over our AES is not measured."""
    assert pd in STACK_TOPS, f"a run resumes the process {pd:#x} in the ROM's text over our AES: no static stack of it is known"
    uda = aes_event.uda_of(pd, image)
    (lo, hi, _why), = aes_switch.uda_context_drop(uda)
    context_why, stack_why = WHYS_OF[pd]
    return (lo, hi, context_why), (uda + aes.UDA_STATE_BYTES, STACK_TOPS[pd], stack_why)


def desk_windows_of(image):
    """The desk's two spans over `image` (`foreign_windows_of`): its saved context, its stack to UDA0's top."""
    return foreign_windows_of(aes.SHELL_PD, image)


def desk_parked_windows(image):
    """`(lo, hi, why)` of every EVB parameter longword over `image` that names a place inside the desk's stack."""
    _context, (lo, top, _why) = desk_windows_of(image)
    return tuple((at, at + aes.LONG_BYTES, DESK_PARKED_WHY) for at in (evb + aes.EVB_PARM for evb in aes_event.EVBS)
                 if lo <= case.long_in(image, at) & BUS < top)


def desk_drops(image, stored):
    """THE TIER 3 DROPS of a run that enters the desk as another process than its own: the desk's windows and its
    parked addresses, each cut to the bytes the ROM's run STORED (`aes_event.stored_spans`)."""
    windows = (*desk_windows_of(image), *desk_parked_windows(image))
    return tuple(span for window in windows for span in aes_event.stored_spans(window, stored))


FOREIGN_STACK_WHYS = (DESK_STACK_WHY, OTHER_STACK_WHY)


def names_the_desk(dropped):
    """Does a row that drops `dropped` run with a turn of the ROM's text over our AES? (It names such a stack.)"""
    return any(why in FOREIGN_STACK_WHYS for _lo, _hi, why in dropped)


def foreign_stacks_named(dropped, image):
    """...and the windows of each process whose stack it names (`foreign_windows_of`), over `image`."""
    named = {why for _lo, _hi, why in dropped}
    return tuple(window for pd, (_context, stack_why) in WHYS_OF.items() if stack_why in named
                 for window in foreign_windows_of(pd, image))


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
    # ...AND A FRAME ADDRESS HANDED TO GEMDOS (`frame_addresses_handed`): dropped where the run stored it, never staged
    handed = tuple(span for window in frame_addresses_handed(final) for span in aes_event.stored_spans(window, stored))
    # ...AND, FOR A RUN THAT ENTERS THE SCREEN MANAGER AS ANOTHER PROCESS THAN ITS OWN: the screen manager's two
    # by-nature spans (`aes_takeover`), DROPPED where this run stored them and NEVER STAGED — they are LIVE at the
    # run's entry (its parked context, its frames), where the caller's own saved context is dead.
    enters_the_manager = switches.process != SCREEN_MANAGER and SCREEN_MANAGER in reference.entered
    its_spans = aes_takeover.drops(final, stored) if enters_the_manager else ()
    # ...AND THE DESK'S, FOR A RUN THAT ENTERS IT AS ANOTHER PROCESS THAN ITS OWN (`desk_drops`): its turn is ours —
    # and the spare PD's, entered on a machine with no door (`foreign_windows_of`: its turn over our AES).
    enters_the_desk = switches.process != aes.SHELL_PD and aes.SHELL_PD in reference.entered
    the_desk_s = desk_drops(final, stored) if enters_the_desk else ()
    # (an allocated accessory's stack is a Malloc's and no static span: entered so, it is compared exactly — a red
    # where its turn left our build's frames, not a drop guessed)
    others = sorted({pd for pd in reference.entered if pd in STACK_TOPS} - {switches.process, aes.SHELL_PD})
    of_others = tuple(span for pd in others for window in foreign_windows_of(pd, final)
                      for span in aes_event.stored_spans(window, stored))
    return Settled(pokes, drops + qpb_address_drops(qpbs) + handed + its_spans + the_desk_s + of_others, switches,
                   tuple(reference.entered), qpbs)


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


# A FRAME ADDRESS HANDED TO GEMDOS (band 6 W3a stage 1's fix pass; the user's ruling of 2026-10-25: "a by-nature window"
# of its own, derived from the ROM run's own trap ledger, BY ADDRESS — no ⚠️, no recorder that zeroes such pointers). A
# routine that hands a `trap #1` the address of a place in ITS OWN FRAME (inf_disk's dos_label: the DTA and the search's
# path; its dos_space: Dfree's DISKINFO) hands the ROM routine's stack on one shore and the C's on the other — and a
# recording trap KEEPS it: its ledger records the frame's own bytes, its DTA cell the pointer an Fsetdta named. The
# windows: of the run's recorder (`aes_shell.gemdos_ledger_of`: known by its handler's bytes at the vector), every
# POINTER ARGUMENT of a recorded call — at its own offset in the frame, as the GEMDOS binding the recorder records
# lays it (`GemdosLedger.pointer_offsets`), and within THE FRAME'S OWN BYTES — whose value lies in THE RUN'S STACK
# BAND, and the recorder's DTA cell where it holds one of those very values. Never a longword at any other offset: one
# that straddles two arguments (an attribute and the pad behind it, a date and a handle, a handle and a count's high
# word) can read as a band address (review RS1F's G1); a function with no pointer argument yields none. Dropped cut to
# the bytes the run stored (`_settled`), never staged (no machine holds beforehand an address in a frame its run has
# yet to push), and held again by the switching census off the ROM's scheduled run
# (`test_aes_event._the_switching_census`).
FRAME_ADDRESS_WHY = ("a frame address handed to GEMDOS: a trap's argument naming a place in the caller's own stack "
                     "frame — the ROM routine's on its shore, the C's on ours — as the run's recorder keeps it (an "
                     "argument longword of its ledger, its DTA cell)")


def frame_addresses_handed(image):
    """THE CLASS (above) over `image` (a run's memory): `(lo, hi, FRAME_ADDRESS_WHY)` windows, in the ledger's order
    then the DTA cell — none where no recorder of the tree's stands behind the GEMDOS vector."""
    ledger = aes_shell.gemdos_ledger_of(image)
    if ledger is None:
        return ()
    windows, handed = [], set()
    for nth, (function, frame) in enumerate(ledger.ledger.recorded(image)):
        arguments_at = ledger.ledger.first + nth * ledger.ledger.stride + aes.WORD_BYTES
        own = ledger.frame_bytes.get(function, ledger.recorded_bytes)
        for offset in (at for at in ledger.pointer_offsets.get(function, ()) if at + aes.LONG_BYTES <= own):
            value = int.from_bytes(frame[offset:offset + aes.LONG_BYTES], "big") & BUS
            if value in case.STACK_BAND:
                windows.append((arguments_at + offset, arguments_at + offset + aes.LONG_BYTES, FRAME_ADDRESS_WHY))
                handed.add(value)
    cell = ledger.dta_cell
    if cell is not None and case.long_in(image, cell) & BUS in handed:
        windows.append((cell, cell + aes.LONG_BYTES, FRAME_ADDRESS_WHY))
    return tuple(windows)


def own_drops(row):
    """THE DROPS `row` NAMES BY ITS OWN HAND, as `(lo, hi, why)`: its declared X flag (`THE_X_FLAG_ALONE`, where
    `x_flag_differs`) and its own spans (`also_dropped`) — none of them derived off the ROM's run."""
    return (THE_X_FLAG_ALONE if row.x_flag_differs else ()) + tuple(row.also_dropped)


def settled(row):
    """`row`'s `Settled`: its machine, its Tier 3 drops, what its run is taken through, who the dispatcher enters."""
    made = _settled(row.name, tuple(row.arguments), row.machine(), dict(row.at_idle or {}), row.at_calls, row.at_polls,
                    *((row.budget,) if row.budget else ()))
    drops = tuple(made.drops) + own_drops(row)
    if row.the_rom_s_screen_manager:    # ...a row left on the ROM's screen manager names neither of its spans
        drops = tuple(drop for drop in drops if drop[2] not in aes_takeover.WHYS)
    return made._replace(drops=drops) if drops != tuple(made.drops) else made


def rederived(row):
    """`row`'s `Switches` DERIVED AGAIN over its settled machine as the snapshot stands now: the interrupts' own
    code run afresh (the noise sweep's, and what holds that the settling changed nothing of them)."""
    return switches_of(scheduled(row, settled(row).pokes))


# What a companion answers, for its caller's own assertions on a woken case: the machine it ran, what its run was
# taken through, the C's answer and the image it returned with — and, of the ROM's run, what each door call was
# handed (a door user's: the C's are held equal) and the processes its dispatcher entered.
CompanionRun = namedtuple("CompanionRun", "staged delivered answer calls image entered")


def _door_of(row):
    """What a row's Tier 1 fork binds: its door user's door — or, for a row that reaches A DOOR OF ITS OWN and makes
    no door call (`child_doors`), a door that serves no entry and runs that source first, THE WALKED ROUTINES SERVED
    as a row with no door at all is served them (`aes_switch._served_with_no_door`, slice H2; since band 6 slice F3:
    d_doop's rows over the copy engine's replay draw its fields by objc_draw). Either way the fork notes the image at
    every dispatch, and the companion holds each to the ROM's."""
    return row.door or (aes_switch.DoorUser(objects=True, doors=row.child_doors) if row.child_doors else None)


def companion(row, at_stops_only=()):
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
    A DOOR USER's row (`row.door`) binds the door in the same fork, and is held to the frames the ROM's run hands.
    `at_stops_only` (`(lo, hi, why)` each): bytes that differ by nature IN THE MIDDLE of the run and are equal again
    where it ends — left out of the images taken at a door call's return and at a dispatch, and COMPARED at the end
    like every other byte (a by-nature word a later call of both builds overwrites: ct_mouse's stale count, where a
    VDI call follows the menu before the run returns). No registered row's companion is asked with one."""
    if at_stops_only:                   # ...NEEDED, or refused: a leave-out the row passes without hides a page for nothing
        try:
            companion(row)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"{row_name(row)}: `at_stops_only` names bytes to leave out of the images at its stops, "
                                 f"and its companion passes without leaving any out")
    made = settled(row)
    reference = scheduled(row, made.pokes, at_stops_only)
    signature = vdi.ALCYON[row.name]
    foreign = any(pd != made.switches.process for pd in reference.entered)
    ran = aes_switch.modelled(_core(row), vdi.as_signed(row.name, row.arguments), made.pokes, reference,
                              answered=row.answered and signature.restype is not None, foreign=foreign, door=_door_of(row),
                              left_out_beside=(*row.also_dropped, *at_stops_only))
    who = row_name(row)
    assert reference.ended == aes_switch.RETURNED and ran.returncode == 0, (
        f"{who}: the ROM's run returned; the C's fork ended {ran.returncode}:\n{ran.stderr}")
    assert ran.idles == reference.idles, f"{who}: the C's run idled {ran.idles} times, the ROM's {reference.idles}"
    assert ran.polls == reference.polls, f"{who}: the C's run polled {ran.polls} times, the ROM's {reference.polls}"
    assert not _door_of(row) or ran.handed == list(reference.calls), (
        f"{who}: the door was handed {ran.handed}, the ROM's run hands {list(reference.calls)}")
    answer_bits = aes.RESULT_WIDTHS[signature.restype] if row.answered else case.NO_RESULT
    if answer_bits:
        mask = (1 << answer_bits) - 1
        assert ran.answer & mask == reference.d0 & mask, f"{who}: answers {ran.answer & mask:#x}, the ROM's run {reference.d0 & mask:#x}"
    expected = reference.memory
    left_out = frozenset(case.STACK_BAND) | _vetted_qpbs(row, made, ran.image) | _its_own_by_nature(row, made.pokes, reference)
    differ = aes_event.differing(ran.image, expected, left_out)
    assert not differ, f"{who}: " + aes_event.describe_differences(who, ran.image, expected, differ)
    if _door_of(row):                   # ...and, the END the ROM's: what each call answered and left, and every dispatch
        aes_event.vet_the_answers_handed_back(who, ran.answered, reference.answers)
        aes_event.vet_the_images_at_the_dispatcher(who, ran.dispatched, reference.dispatches)
    return CompanionRun(made.pokes, switches_of(reference), ran.answer, tuple(reference.calls), ran.image,
                        tuple(reference.entered))


def _its_own_by_nature(row, staged, reference):
    """The bytes a row names as its own by nature (`SwitchingRow.also_dropped`) — each REQUIRED to be one the ROM's
    run STORED, read off the write ledger of its replay over `staged` (`_replay_of`): a drop over a byte the run never
    stores excuses a store of the C's alone. A store of the value the byte already held is the ROM's store all the
    same (the orchestrator's ruling at band 6 slice F3 stage 2's third fix pass: the BIOS door's park, `$fe1bb2` over
    the viewer's `$fed7de`, stores `$95af`'s `$fe` again) — so the census asks the ledger, never whether the value
    changed."""
    named = _its_own_bytes(row)
    if not named:
        return named
    unstored = its_own_unstored(row, staged, reference)
    assert not unstored, (
        f"{row_name(row)}: named by nature, and never stored by the ROM's run: {[f'{at:#x}' for at in unstored]}")
    return named


def _its_own_bytes(row):
    return frozenset(at for lo, hi, _why in row.also_dropped for at in range(lo, hi))


def its_own_unstored(row, staged, reference):
    """The bytes `row` names as its own by nature that the ROM's run `reference` over `staged` NEVER STORES, in order —
    read off the write ledger of its replay (`_replay_of`), never off whether a value changed. The one spelling of a
    store for both censuses: the companion's (`_its_own_by_nature`) and the switching rows' (`test_aes_event`)."""
    _watch, _final, writes = _replay_of(row, staged, reference)
    return sorted(at for at in _its_own_bytes(row) if at not in writes)


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
    row, held = held_of(row)
    undropped = functools.partial(companion, row)
    for name in under or (row_name(row),):
        aes_event.SWITCHING_ROWS[name] = held
        aes.ROWS.register(name, _entry(row), held.pokes, dropped=held.drops, undropped=undropped, delivered=held.switches,
                          answered=row.answered)
    return row


def held_of(row):
    """`row` SETTLED FOR ITS REGISTRAR (`register_row`'s, and band 6 W3a's target-only one —
    `aes_desk_w3a.register_target_only_switching`): `(the row, its arguments a tuple and its wakes a dict; its
    `Registered`)`."""
    row = row._replace(arguments=tuple(row.arguments), at_idle=dict(row.at_idle or {}))
    made = settled(row)
    # (F2 stage 2's fix pass, reviewer B's F2: a "switching" row whose ROM run dispatches nothing is a plain row, priced
    # alike — refused here, where no census could see it)
    assert made.entered, (f"{row_name(row)}: registered as a row that switches, and the ROM's run through its "
                          f"dispatcher enters no process — a plain row")
    return row, Registered(row, made.pokes, made.drops, made.switches, made.entered, functools.partial(rederived, row),
                           made.qpbs)


def measured_on(blob, row):
    """THE SECOND DIFFERENTIAL OF A ROW THAT SWITCHES ON ONE BLOB (`tier3.RomBench`), whichever blob the table prices
    it on: the ROM's routine and `blob`'s twin, each watched at its dispatcher, over the row's settled machine with
    its Tier 3 drops — HELD TO EVERYTHING THE TABLE'S OWN MEASUREMENT HOLDS A SWITCHING ROW TO
    (`tier3.switching_run_on`: the two runs one schedule, the foreign windows equal to the cycle with no cycle of
    our build inside, our run in the AES's ROM nowhere else). The kit's `Measurement` of the WHOLE run, our run's
    watch, and the windows' `tier3.Foreign`.
    A HANDLER OF THE SCREEN MANAGER'S (`aes_ctlmgr.HANDLED`) IS MEASURED WHERE ITS OWN ctlmgr ARRIVES AT IT — on a
    named blob as in the table (`tier3.at_its_arrival_on`): the same three, of the handler's own run."""
    import aes_ctlmgr                   # (its registry is read where a row is measured: it imports the handlers' machines)
    tier3, made = bench_tier3(), settled(row)
    if row_name(row) in aes_ctlmgr.HANDLED:
        measured, watch = tier3.through_its_handler_on(blob, row_name(row), aes_ctlmgr.HANDLED[row_name(row)])
        return measured, watch, measured.foreign
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
    vet_the_whole_run(who, blob, measured, whole)
    vet_its_turns(who, blob, measured)
    return measured, watch, foreign


def vet_the_whole_run(who, blob, measured, whole):
    """THE WHOLE RUN'S CYCLES on `blob` — the ROM's, ours, each net of the entry both share — ARE THE PINNED PAIR
    (`whole`: `{the blob's directory: (the ROM's, ours)}`). A run that moves says why."""
    directory = blob.elf.parent.name
    assert (measured.original_net, measured.recreate_net) == whole[directory], (
        f"{who} measures {measured.original_net} / {measured.recreate_net} cycles on {directory}: say why it moved")


def _as_pinned(turns):
    return tuple((turn.ours, turn.the_rom_s, turn.glue) for turn in turns)


def turns_measured(measured):
    """The turns of our screen manager inside a measured run, as a pin spells them: `(ours, the ROM's, our thunks')`
    cycles each, in order (`tier3.Turn`) — of a row of ctlmgr's own (`its_turns`: the run IS its turns) as of a row
    with a turn inside it."""
    turns = getattr(measured, "its_turns", None) or getattr(measured, "turns", ())
    return _as_pinned(turn for turn in turns if turn.whose == THE_MANAGER_S)


def accessory_turns_measured(measured):
    """...and THE ACCESSORIES' TURNS inside it (behind our door: `tier3.Turn.whose`), spelt the same way — a turn of
    ours inside ANY row measured there: a row of ctlmgr's own, a handler's."""
    return _as_pinned(turn for turn in getattr(measured, "turns", ()) if turn.whose == AN_ACCESSORY_S)


def turns_pinned(who, directory):
    """...and the ones PINNED for the row `who` on the blob of `directory` — none, for a row with no line."""
    return tuple(tuple(turn) for turn in aes_turns_pinned.PINNED.get(who, {}).get(directory, ()))


def accessory_turns_pinned(who, directory):
    """...and the accessories' (`aes_accessory_turns_pinned`: a data file of its own, the same shape)."""
    return tuple(tuple(turn) for turn in aes_accessory_turns_pinned.PINNED.get(who, {}).get(directory, ()))


def desk_turns_measured(measured):
    """...and THE TURNS OF A PROCESS WHOSE TEXT IS THE ROM'S, over our AES (the desk's: band 6's binding; `TEXT_OVER_OUR_AES`),
    spelt the same way."""
    return _as_pinned(turn for turn in getattr(measured, "turns", ()) if turn.whose in TEXT_OVER_OUR_AES)


def desk_turns_pinned(who, directory):
    """...and the ones pinned (`aes_desk_turns_pinned`: a data file of its own, the same shape)."""
    return tuple(tuple(turn) for turn in aes_desk_turns_pinned.PINNED.get(who, {}).get(directory, ()))


def vet_its_turns(who, blob, measured):
    """THE TURNS OF OURS INSIDE THE RUN ARE THE PINNED ONES — the screen manager's (`aes_turns_pinned`), behind our
    door the accessories' (`aes_accessory_turns_pinned`), and since band 6's binding the desk's — the ROM's text over
    our AES (`aes_desk_turns_pinned`) —, each by the row's name and the blob's directory; none for a
    row with no line there — each the turn's whole AES subtree, ours against the ROM's (the table's convention), in
    the same window — AND EACH IS AT OR UNDER THE BAR BY ITSELF, its thunks counted. A turn that moves says why."""
    directory = blob.elf.parent.name
    tier3 = bench_tier3()
    for whose, measures, held in (("the screen manager's", turns_measured(measured), turns_pinned(who, directory)),
                                  ("the accessories'", accessory_turns_measured(measured), accessory_turns_pinned(who, directory)),
                                  ("the desk's (the ROM's text over our AES)", desk_turns_measured(measured),
                                   desk_turns_pinned(who, directory))):
        assert measures == held, (
            f"{who}: on {directory} {whose} turns inside the run measure {measures} (ours, the ROM's, thunks) where "
            f"{held} is pinned: say why they moved")
        assert all(tier3.turn_ratio_with_glue(tier3.Turn(*turn, 0)) <= tier3.TIER3_FUNCTION_BAR for turn in held), (
            f"{who}: a turn of ours ({whose}) is over the bar by itself on {directory}")


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
