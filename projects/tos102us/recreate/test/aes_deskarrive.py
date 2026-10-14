"""A DESK ROUTINE AT ITS ARRIVALS — the machinery band 6 wave 1b's group G4 holds its four units by (units C, H, E, F:
`aes_deskdir.py`, `aes_deskfun.py`, `aes_deskusr.py`, `aes_deskinf.py`), unit D's (`aes_deskbind.py`) for any routine of
the desk by its `addrs` name and declared Alcyon frame.

HELD AT TIER 1, NOTHING BOUND: the C core against the ROM's own routine on the host library, over A MACHINE A ROM RUN
MADE —

  * AN ARRIVAL (`arrival`): a chain of the hands (`aes_desk.CHAINS`) STOPPED AT THE ROUTINE'S FIRST INSTRUCTION, at its
    n-th arrival there — each step whose profile says the routine was entered stopped at its first arrival, and on from
    there to the next, to the step's end (`aes_deskbind.arrivals`' walk). The megabyte and the registers are what the
    ROM's own caller left; the arguments are read off the frame it pushed, by the routine's declared signature. No poke.
  * A CASE OF A ROUTINE THAT YIELDS (it reaches a binding of unit D: `dsptch()` runs before it returns) is A ROW THAT
    SWITCHES (`row_of`, `held`: `aes_switching.companion` — the C through the host's scheduler held to the ROM's
    scheduled run, nothing dropped), its wait ended by a WAKE where it waits for a hand; a case of one that does not
    is the kit's plain differential (`plain`).
  * THE ROM'S OWN RUN IN PLACE (`returned_in_place`): the machine continued from the arrival to the address the call
    returns to, on the desk's own stack — D0 and A0 as the routine leaves its ROM caller.
"""
import functools
from collections import namedtuple

from harness import addrs

import aes
import aes_boot
import aes_desk
import aes_deskbind as db
import aes_event
import aes_switching as switching
import case
import vdi

LONG_BYTES = aes.LONG_BYTES

Arrival = namedtuple("Arrival", "name chain nth boot arguments returns_to ends_at budget")
Arrival.__doc__ = """The chain `chain` of the hands stopped at its `nth` arrival (from 0) at the routine `name`'s entry
(an `addrs` name): the `Boot` there, the `arguments` its caller pushed (read off the frame by the declared signature,
words unsigned) and the address the call `returns_to`; `ends_at` the named stop the step it was met in ends at (None:
an idle), and that step's `budget`."""


def entry_of(name):
    return getattr(addrs, name)


def _frame_arguments(name, ram, sp):
    arguments, at = [], sp + LONG_BYTES
    for argtype in vdi.frame_argtypes(name):
        arguments.append(case.word_in(ram, at) if argtype is vdi.WORD_ARG else case.long_in(ram, at))
        at += vdi.ARG_BYTES[argtype]
    return tuple(arguments)


def _arrived(name, chain_name, nth, boot, ends_at, budget):
    sp = db.stack_pointer(boot)
    return Arrival(name, chain_name, nth, boot, _frame_arguments(name, boot.ram, sp), case.long_in(boot.ram, sp) & db.BUS,
                   ends_at, budget)


@functools.cache
def arrivals(name, chain_name, count=1):
    """THE FIRST `count` ARRIVALS OF THE CHAIN `chain_name` AT THE ROUTINE `name` (`aes_deskbind.arrivals`' walk, over
    any routine of the desk): fewer where the chain arrives fewer times."""
    entry, found = entry_of(name), []
    for boot, received, stands_at, ends_at, budget, done in db._steps_as_walked(chain_name):
        if len(found) >= count or entry not in aes_desk.cycles_at(done.profile):
            continue
        found.append(_arrived(name, chain_name, len(found), aes_boot.continued(boot, received, budget, entry, stands_at),
                              ends_at, budget))
        while len(found) < count and ends_at is None:
            try:
                following = aes_boot.continued(found[-1].boot, (), budget, entry, entry)
            except aes_boot.Refused:
                break
            found.append(_arrived(name, chain_name, len(found), following, ends_at, budget))
    return tuple(found)


def arrival(name, chain_name, nth=0):
    """The chain's `nth` arrival at the routine — refused by name where it arrives fewer times."""
    found = arrivals(name, chain_name, nth + 1)
    if len(found) <= nth:
        raise aes_boot.Refused(f"the chain {chain_name!r} arrives at {name} {len(found)} time(s): no arrival {nth}")
    return found[nth]


def returned_in_place(arrived):
    """THE ROM'S OWN RUN OF THE ROUTINE IN PLACE, from the arrival to the address its caller's call returns to, on the
    desk's own stack: the `Boot` there — None where the machine idles first (a routine that waits for a hand)."""
    try:
        boot = aes_boot.continued(arrived.boot, (), arrived.budget, arrived.returns_to, entry_of(arrived.name))
    except aes_boot.Refused:
        return None
    assert db.stack_pointer(boot) == db.stack_pointer(arrived.boot) + LONG_BYTES, (
        f"{label_of(arrived)}: the run reached {arrived.returns_to:#x} on another frame than the arrival's own return")
    return boot


def machine_of(arrived):
    """The arrival's megabyte as a case's pokes."""
    return {0: arrived.boot.ram}


def label_of(arrived):
    return f"arrival {arrived.nth} of {arrived.chain!r} at {arrived.name}"


def row_of(arrived, label, answered, at_idle=None, at_calls=None):
    """THE ROW THAT SWITCHES a case of a routine that yields is (`aes_event.woken_row`, its door bound, its C's tree
    walks served), over the arrival's machine — its wait ended by `at_idle` / `at_calls` — its answer compared where
    `answered`."""
    pokes = machine_of(arrived)
    return aes_event.woken_row(label, arrived.name, arrived.arguments, lambda: pokes, at_idle or {}, at_calls, objects=True,
                               answered=answered)


def held(row):
    """TIER 1 of a yielding routine's case: `aes_switching.companion`, nothing dropped. Its `CompanionRun`."""
    return switching.companion(row)


def the_rom_s_run(row):
    """THE ROM'S OWN SCHEDULED RUN of the row over its settled machine (`.d0`, `.idles`, `.entered`)."""
    return switching.scheduled(row, switching.settled(row).pokes)


def plain(arrived, **kwargs):
    """...and of a routine that never yields: the kit's differential over the arrival's megabyte. Its `aes.Result`."""
    return aes.run_function(arrived.name, arrived.arguments, machine_of(arrived), **kwargs)


# ---- A CASE --------------------------------------------------------------------------------------------------------------
RETURN_TYPED = "Return at the first idle"
WAKES = {RETURN_TYPED: dict(at_idle={0: aes_event.key(aes_event.RETURN_KEY)})}

Case = namedtuple("Case", "name chain nth wake arm over arguments why yields laid",
                  defaults=(0, None, None, None, None, None, True, None))
Case.__doc__ = """One case: the routine `name` at the `nth` arrival of `chain`, its wait ended by `wake` (a key of WAKES).
`arm`: what the arrival's own arguments must be for the case to be the arm it was chosen for (`arguments -> bool`). AN
ARGUMENT CLASS has a `why` — said in its name — and runs over the arrival of `over` (another routine; None: its own)
with `arguments` (a tuple, or `arrival -> tuple`). `yields`: the case reaches a binding (a row that switches) — else a
plain differential. `laid`: `(what, arrival -> pokes)`, A LABELLED STAGING of machine state laid over the arrival's
megabyte (its `what` in the id, `LAID`)."""
LAID = "LAID"


def label(each):
    where = f"arrival {each.nth} of {each.chain}" + (f" (at {each.over})" if each.over else "")
    said = (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + where
    said += f" [{LAID}: {each.laid[0]}]" if each.laid else ""
    return said + (f"; {each.wake}" if each.wake else "")


def _laid_over(arrived, pokes):
    """The arrival with `pokes` laid into its megabyte (both shores run over it)."""
    ram = bytearray(arrived.boot.ram)
    for at, data in pokes.items():
        ram[at:at + len(data)] = data
    return arrived._replace(boot=arrived.boot._replace(ram=bytes(ram)))


def by_label(cases):
    """`{the case's name: the case}`, two of one name refused."""
    named = {f"{each.name} — {label(each)}": each for each in cases}
    assert len(named) == len(cases), "two cases of one name"
    return named


@functools.cache
def _arrival_of(each):
    arrived = arrival(each.over or each.name, each.chain, each.nth)
    assert each.arm is None or each.arm(arrived.arguments), f"{each}: the arrival's arguments {arrived.arguments} are not the arm it names"
    if not each.why:
        return arrived
    arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
    laid = _laid_over(arrived, each.laid[1](arrived)) if each.laid else arrived
    return laid._replace(name=each.name, arguments=tuple(arguments))


def arrival_of(each):
    """The case's `Arrival`: the chain's own — or, for an argument class, that machine under the case's routine and
    arguments. The arm the case was chosen for is held here."""
    return _arrival_of(each)


def case_row(each, answered=True):
    """The case's row that switches, its answer compared where `answered` (and the core answers one)."""
    arrived = arrival_of(each)
    answered = answered and vdi.ALCYON[each.name].restype is not None
    return row_of(arrived, label(each), answered, **WAKES.get(each.wake, {}))


def tier_1(each, answered=True, **plain_kwargs):
    """THE CASE AT TIER 1: a row that switches through the companion — the ROM's run idles where the case's wake says
    — or the plain differential. `answered` False where the ROM's D0 is a NAMED divergence the C has no word of."""
    if not each.yields:
        return plain(arrival_of(each), answer_compared=answered, **plain_kwargs)
    row = case_row(each, answered)
    ran, the_rom_s = held(row), the_rom_s_run(row)
    assert bool(the_rom_s.idles) == (each.wake is not None), f"{label(each)}: the ROM's run idles {the_rom_s.idles} time(s)"
    assert ran.entered and ran.entered[-1] == aes.SHELL_PD, f"{label(each)}: the run does not end in the desk's own process"
    return ran


# ---- LINKED AND UNBOUND -----------------------------------------------------------------------------------------------------
def _linef_table():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


def unbound(blob, names):
    """THE UNBOUND PIN of the routines `names`, on `blob` (`aes_deskbind.bound_referrers`, one for every unit of the
    desk): each core LINKED, and no function outside the unbound desk refers to ANY held core; each one's Line-F table
    entries THE ROM'S (a routine of `LINKED_HELD_NO_TABLE_ENTRY` has none: R-W2-4); and no registered row names one."""
    import routines
    linef_table = _linef_table()
    cores = {routines.core_symbol(name) for name in names}
    bound = db.bound_referrers(blob, names)
    assert not bound, f"bound: {bound}"
    ours = {entry_of(name): name for name in names}
    verdicts = {ours[entry.target]: entry.verdict for entry in linef_table.entries() if entry.target in ours}
    no_table_entry = set(linef_table.LINKED_HELD_NO_TABLE_ENTRY)       # R-W2-4: held, and no verdict to hold
    assert verdicts == {name: linef_table.THE_ROM_S for name in names if name not in no_table_entry}
    assert set(names) <= set(linef_table.LINKED_AND_NOT_FLIPPED) | no_table_entry
    registered = [row for row in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS) if row.split(",")[0] in cores]
    assert not registered, f"registered: {registered}"
