"""THE SCREEN MANAGER MADE OURS ON A ROW'S MACHINE (FLIP 4, band 5 wave 2: ctlmgr bound in C).

A row that switches is ONE machine for both shores (`aes_switching`): the pokes its battery derived from the ROM's own
runs, the screen manager parked BY THE ROM in the ROM's frames. While ctlmgr was the ROM's, another process's turn
inside a row was therefore the ROM's own code on both shores — a foreign window, in neither column. With ctlmgr in C
that is no longer what a build of ours does: its screen manager is ITS OWN ctlmgr, parked in its own frames, woken
and parked by its own dispatcher. So a row whose run ENTERS THE SCREEN MANAGER (and is not the screen manager's own)
is run, on our shore, over THE SAME MACHINE WITH THE SCREEN MANAGER OURS:

  * WHAT DIFFERS, AND NOTHING ELSE (`aes_boot.by_nature`, measured on every takeover machine, both blobs): the screen
    manager's SAVED CONTEXT in its UDA and its OWN STACK (`spans_of`: located from the machine's own pointers), its
    p_ldaddr (a code address: MAPPED by the registry, `aes_event.SCREEN_MANAGER_ENTRY`, never laid here), the
    dispatcher's dead frames (dead: a row drops and puts back that stack already) and the blob.
  * WHERE OURS COME FROM — NEVER A POKE: FROM OUR BUILD'S OWN RUN THROUGH THE SAME HISTORY (`ours_over`).
      - THE BOOT. A machine whose screen manager stands exactly as the ROM's boot leaves it (`state_of`: its saved
        context and its live frames, byte for byte, those of `aes_boot.desk_machine()` — the boot snapshot's own
        are: held by `test_aes_takeover.py` on every capture) takes them from THE TAKEOVER MACHINE of that boot
        (`aes_boot.desk_machine(ours=blob)`: the ROM's boot, our ctlmgr entered at the screen manager's first entry
        through the registry's mapping — which ictlmgr's own row proves is what our ictlmgr + pstart store).
      - A MACHINE A ROM RUN LEFT THE SCREEN MANAGER ELSEWHERE IN (its menu holding the screen, queued on the lock:
        `aes_switching.left_by`, which notes each such run here — `note`) takes them from OUR BUILD'S RUN OF THAT
        SAME CALL, through the same interrupts, over the machine it started from made ours the same way: what our
        screen manager's own turn left of its context and its frames.
      - ANY OTHER STATE IS REFUSED BY NAME: no history of ours is known to reach it.
  * WHAT THE ROW THEN HOLDS: the screen manager's turn is OUR code (`aes_switching.Switching` reads it off the run:
    the PC switchto's `rte` resumes it at lies in the blob), priced as a line of its own (`bench/tier3.py`); the
    image at every stop of the dispatcher and where the run ends is the ROM's outside the two spans — which are
    DROPPED BY NAME where the ROM's run stored them (`drops`): the saved context WHOLE (the ROM's savestate stores
    every byte of it; held by name), the stack where the ROM's frames lay — and, on our shore, THE STACK PUT BACK as
    the machine came with it before the compare (`tier3.RomBench._call`: what then differs there is exactly what
    the ROM's run stored).
  * WHAT HOLDS THE 1,264 BYTES THE COMPARE LEAVES OUT (FLIP 4's review):
      - NOBODY BUT THE SCREEN MANAGER STORES THERE (`Switching.hold_the_manager_s_spans`): the two spans are held BY
        CONTENT on both shores wherever it does not run — from the run's entry to its first turn, between its turns,
        from its last to where the run ends — but the one word the dispatcher stores as it hands the machine back
        (the SR of the `rte` frame, at the parked stack pointer). A store there by the row's own process is refused
        by name at the stop that finds it.
      - THE SPANS' LIVE PART IS VETTED BY WHAT THE SCREEN MANAGER DOES WHEN WOKEN — the row's own run through it.
      - HOW THE RUN LEAVES IT PARKED (`tier3.how_the_screen_manager_is_left`): as it began on both shores or on
        neither; and, where the ROM's ends in a state our build's own run is known to reach (`left_as_ours`), ours
        exactly as that run left it. A park ELSEWHERE is compared with nothing where the run ends — it is vetted
        only by the runs that wake the screen manager again from a park of that kind (STATUS says which rows).
"""
import functools
import hashlib
from collections import namedtuple

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_boot
import aes_event
import aes_switch
import case
import derived

SCREEN_MANAGER = aes.SCREEN_MANAGER_PD
BUS = aes.OS_BUS_ADDR_MASK
CONTEXT_WHY = ("THE SCREEN MANAGER'S saved context in its UDA, on a row whose screen manager is OURS (savestate's: the "
               "CPU state of whichever ctlmgr called dsptch — the ROM's frames' addresses on its shore, our build's on "
               "ours); dropped WHOLE — the ROM's savestate stores every byte of it — and held by content, on both shores, "
               "wherever the screen manager does not run")
STACK_WHY = ("THE SCREEN MANAGER'S own stack, on a row whose screen manager is OURS: each build's own frames (the ROM's "
             "ctlmgr's on its shore, our ctlmgr's on ours — deeper, and elsewhere); put back on our shore as the "
             "machine came with it")
WHYS = (CONTEXT_WHY, STACK_WHY)
Spans = namedtuple("Spans", "context stack parked")
Spans.__doc__ = """Where the screen manager's by-nature bytes lie over a machine, off its own pointers: its saved
`context` `(lo, hi)` in its UDA, its `stack` `(lo, top)` — from the end of the UDA's state block to the top psetup's
frame was laid under — and the stack pointer it stands `parked` at (what savestate kept)."""
State = namedtuple("State", "context live")
State.__doc__ = """HOW THE SCREEN MANAGER STANDS PARKED over a machine: the bytes of its saved context and of its LIVE
frames (from its parked stack pointer to its stack's top). Two machines of one state resume it alike."""
Recipe = namedtuple("Recipe", "name arguments machine at_idle row", defaults=(None,))
Recipe.__doc__ = """A ROM run that left the screen manager in another state than it found it (`aes_switching.left_by`'s
arguments): the call, the machine it started from (pokes), the interrupts taken at its idles — and, for A REGISTERED
ROW's run (`note_a_registered_row`, band 6 W3b), the row itself, run again as it is registered (its budget, its own
drops, its stagings in its machine)."""


class Refused(AssertionError):
    """A row's machine cannot be given a screen manager of ours: said by name."""


def spans_of(image):
    """THE SCREEN MANAGER'S BY-NATURE SPANS over `image` (`Spans`), read through the machine's own pointers."""
    uda = aes_event.uda_of(SCREEN_MANAGER, image)
    (lo, hi, _why), = aes_switch.uda_context_drop(uda)
    stack = (uda + aes.UDA_STATE_BYTES, aes.AES_UDA1_STACK_TOP)
    parked = case.long_in(image, uda + aes.UDA_SUPER_SP) & BUS
    if not hi <= stack[0] < stack[1]:
        raise Refused(f"the screen manager's UDA at {uda:#x} does not lie under the stack top {stack[1]:#x} the ROM gives it")
    return Spans((lo, hi), stack, parked)


def state_of(image):
    """...and how it stands parked there (`State`). REFUSED where its saved stack pointer is not in its own stack."""
    at = spans_of(image)
    if not at.stack[0] <= at.parked <= at.stack[1]:
        raise Refused(f"the screen manager's saved stack pointer {at.parked:#x} lies outside its own stack "
                      f"[{at.stack[0]:#x}, {at.stack[1]:#x}): it is not parked on this machine")
    return State(bytes(image[at.context[0]:at.context[1]]), bytes(image[at.parked:at.stack[1]]))


def windows_of(image):
    """The two spans as `(lo, hi, why)` windows: what a row whose screen manager is ours names at Tier 3."""
    at = spans_of(image)
    return ((*at.context, CONTEXT_WHY), (*at.stack, STACK_WHY))


def drops(image, stored):
    """THE TIER 3 DROPS of a row whose screen manager is ours, over the machine `image` its ROM run left: the two
    windows, each cut to the bytes that run STORED (`stored`: its write ledger) — a drop is of what the original
    wrote (`rom_bench.vet_dropped`); of the stack, what it did not store our shore puts back."""
    return tuple(span for window in windows_of(image) for span in aes_event.stored_spans(window, stored))


def named_in(dropped):
    """Does a row that drops `dropped` run with the screen manager OURS? (It names one of the two windows.)"""
    return any(why in WHYS for _lo, _hi, why in dropped)


def the_stack_s(dropped):
    """...and the drops among them that are the screen manager's STACK's: each build's own frames, a byte of which
    one build may store and the other not (`tier3.EACH_BUILD_S_OWN_FRAMES`)."""
    return tuple((lo, hi, why) for lo, hi, why in dropped if why == STACK_WHY)


# ---- WHAT A ROM RUN LEFT THE SCREEN MANAGER IN, AND THE RUN THAT DID IT ---------------------------------------------------------
PROVENANCE = {}                         # `{State: Recipe}`: each state a noted ROM run left, by the first run that did


def note(name, arguments, machine, at_idle, left):
    """A ROM RUN OF A CALL THAT SWITCHES (`aes_switching.left_by`) HAS LEFT THE MACHINE `left` (pokes) from `machine`:
    where it left the screen manager in ANOTHER STATE than it found it, the run is the state's provenance — what our
    build runs again to stand its own screen manager there (`ours_over`). The FIRST run that reaches a state is kept:
    a later one from a machine already in that state would name itself."""
    before, after = state_of(make_image(machine)), state_of(make_image(left))
    if after != before:
        PROVENANCE.setdefault(after, Recipe(name, tuple(arguments), machine, dict(at_idle)))


def note_a_registered_row(row, settled):
    """A REGISTERED ROW THAT SWITCHES (`row`, an `aes_switching.SwitchingRow`, and its `Settled`) AS A STATE'S PROVENANCE
    (band 6 W3b: deskmain's re-entries after a built-in stand the screen manager where the built-in's own registered row
    leaves it — measured, not assumed): where its ROM run leaves the screen manager in another state than its machine
    holds, that state's provenance is the row ITSELF, run again on a blob as it is registered (`_from_our_run_of`).
    The state it leaves, or None."""
    before = state_of(make_image(settled.pokes))
    after = _the_state_a_run_leaves(row.name, tuple(row.arguments), settled.pokes, dict(row.at_idle or {}), row.at_calls,
                                    row.at_polls, row.budget)
    if after == before:
        return None
    PROVENANCE.setdefault(after, Recipe(row.name, tuple(row.arguments), settled.pokes, dict(row.at_idle or {}), row))
    return after


@derived.kept
def _the_state_a_run_leaves(name, arguments, staged, at_idle, at_calls, at_polls, budget):
    """The state the ROM's run of a row that switches (its fields, its settled machine `staged`) leaves the screen manager
    in (`aes_switching._replayed`'s memory) — a derivation, kept by content."""
    import aes_switching                # (it imports this module)
    row = aes_switching.SwitchingRow("", name, arguments, lambda: staged, at_idle, at_calls=at_calls, at_polls=at_polls,
                                     budget=budget)
    return state_of(aes_switching._replayed(row, staged)[2])


# ...AND A BOOT STOPPED EARLIER THAN ITS FIRST IDLE (band 6 W3b: deskmain's FIRST entry on each boot machine — the boot
# `until` deskmain's entry). `{State: (the ROM's stopped Machine, a maker of the TAKEOVER machine stopped there, of a blob)}`,
# the boot's own provenance at an earlier stop (`note_a_stopped_boot`): the same comparison makes it (`_from_a_takeover_boot`).
STOPPED_BOOTS = {}


def note_a_stopped_boot(rom_stopped, taken_over):
    """The ROM's boot STOPPED EARLIER (`rom_stopped`, an `aes_boot.Machine` of `booted(..., until=)`) as the provenance of
    the state it leaves the screen manager in: `taken_over(blob)` makes THE TAKEOVER MACHINE of the same boot, stopped
    at the same address (`booted(..., until=, ours=)`). The state."""
    state = state_of(rom_stopped.image())
    STOPPED_BOOTS.setdefault(state, (rom_stopped, taken_over))
    return state


@functools.cache
def the_boot_s():
    """`{State: the ROM-booted machine that leaves the screen manager so}`: the desk's boot (`aes_boot.desk_machine`:
    the boot snapshot's own boot, at its first idle) — the screen manager parked at its main wait, having run its
    once-only part and one turn's head."""
    booted = aes_boot.desk_machine()
    return {state_of(booted.image()): booted}


def _bytes_of(image):
    at = spans_of(image)
    return {lo: bytes(image[lo:hi]) for lo, hi in (at.context, at.stack)}


def _key(blob):
    return str(blob.elf), hashlib.sha256(blob.blob).digest()


_OURS = {}                              # `{(State, a blob's key): the two spans as our build leaves them}`


def _from_the_takeover_boot(rom_booted, blob, taken_over=None):
    """The two spans as THE TAKEOVER MACHINE of `rom_booted`'s boot holds them on `blob` — the machine held first to be
    the ROM-booted one outside the classes a takeover differs in by nature, its screen manager parked in OUR text.
    `taken_over`: the maker of that machine for a boot STOPPED EARLIER (`STOPPED_BOOTS`) — its stop inside a BIOS
    trap of the boot's (the frame its save area holds is each build's: `aes_boot.TRAP_SAVE_FRAME`, named beside)."""
    taken = aes_boot.desk_machine(ours=blob) if taken_over is None else taken_over(blob)
    beside = aes_boot.compared(rom_booted, taken, also=(aes_boot.TRAP_SAVE_FRAME,) if taken_over else ())
    if beside.differing or taken.resumed_in(taken.screen_manager()) != aes_boot.OURS:
        raise Refused(f"the takeover machine of {blob.elf} is not the ROM-booted one with the screen manager ours: it "
                      f"differs at {[(hex(at), length) for at, length in beside.differing[:4]]}")
    return _bytes_of(taken.image())


def _from_our_run_of(recipe, blob):
    """...and as OUR BUILD'S OWN RUN of `recipe` leaves them: the call that switches, on `blob`, through the same
    interrupts, over the machine the ROM's run started from — its screen manager made ours the same way (the
    recursion ends at the boot) — held to the ROM's run as any row that switches is (`aes_switching.measured_on`)."""
    import aes_switching                # (it imports this module)

    row = recipe.row or aes_switching.SwitchingRow(f"(the run that leaves the screen manager so: {recipe.name})", recipe.name,
                                                   recipe.arguments, lambda: recipe.machine, recipe.at_idle)
    made = aes_switching.settled(row)
    if not named_in(made.drops):
        raise Refused(f"the ROM's run of {recipe.name} noted as leaving the screen manager in another state does not "
                      f"enter the screen manager")
    blob.screen_manager_left = None
    aes_switching.measured_on(blob, row)
    left = blob.screen_manager_left
    if left is None:
        raise Refused(f"our run of {recipe.name} on {blob.elf} was not made with the screen manager ours")
    return left


def made_for(state, blob):
    """`state` — one a noted ROM run left — MADE on `blob` (our build's run of that call) and kept: what `prepared`
    does for a machine that stands so, asked by the state itself (a run that ENDS there is held to it:
    `tier3.how_the_screen_manager_is_left`)."""
    _OURS[state, _key(blob)] = _from_our_run_of(PROVENANCE[state], blob)
    return _OURS[state, _key(blob)]


def prepared(blob, pokes):
    """THE SCREEN MANAGER'S TWO SPANS AS OUR BUILD LEAVES THEM over the machine `pokes`, on `blob` — MADE NOW IF NO
    RUN OF THIS PROCESS HAS MADE THEM (a boot, or a run of our build: oracle runs of their own, which is why a
    measurement asks BEFORE its own two runs begin and `ours_over` then only reads). `{span's lo: bytes}`."""
    state = state_of(make_image(pokes))
    key = state, _key(blob)
    if key not in _OURS:
        if state in the_boot_s():
            _OURS[key] = _from_the_takeover_boot(the_boot_s()[state], blob)
        elif state in STOPPED_BOOTS:
            rom_stopped, taken_over = STOPPED_BOOTS[state]
            _OURS[key] = _from_the_takeover_boot(rom_stopped, blob, taken_over)
        elif state in PROVENANCE:
            made_for(state, blob)
        else:
            raise Refused(
                "THE SCREEN MANAGER OF THIS MACHINE STANDS PARKED WHERE NO HISTORY OF OURS IS KNOWN TO LEAVE IT: its "
                "saved context and live frames are neither the ROM's boot's nor those any noted ROM run "
                "(`aes_switching.left_by`) left — our build cannot be run to stand its own screen manager there")
    return _OURS[key]


def left_as_ours(blob, state):
    """HOW OUR BUILD'S OWN SCREEN MANAGER STANDS PARKED where the ROM's stands in `state` (a `State`) — its own
    `State`, off the two spans `prepared` made for that state on `blob`; None where none was made (READ, never made
    here: this is asked where a measurement's runs have just ended)."""
    made = _OURS.get((state, _key(blob)))
    if made is None:
        return None
    over = bytearray(BASE_IMAGE[:addrs.ST_RAM_BYTES])      # (the screen manager's UDA is the AES's own BSS: one place)
    for lo, held in made.items():
        over[lo:lo + len(held)] = held
    return state_of(over)


def ours_over(blob, image):
    """`prepared`'s answer for the machine `image` (a run's memory at its entry), READ — refused by name where no
    measurement asked beforehand: making it here would run the oracle inside another run's measurement."""
    made = _OURS.get((state_of(image), _key(blob)))
    if made is None:
        raise Refused("a run with the screen manager ours was entered over a machine nobody prepared it for "
                      "(`aes_takeover.prepared`, asked before a measurement's own runs)")
    return made
