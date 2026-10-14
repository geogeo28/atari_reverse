"""THE DESK'S HIT TESTS AND ICON DRAGS AT THEIR ARRIVALS — unit B (`src/desk/deskact.c`, `test_desk_act.py`; band 6
wave 1b, group G3) — and THE ARRIVAL LAYER both of group G3's units take their cases by (unit G's `aes_deskfpd.py`).

HELD AT TIER 1, NOTHING BOUND: each routine is its C core against the ROM's own routine on the host library, over A
MACHINE A ROM RUN MADE. No table entry, no registry row, no price.

  * AN ARRIVAL (`arrival`) is a chain of the hands (`aes_desk.CHAINS`) STOPPED AT THE ROUTINE'S FIRST INSTRUCTION, at
    its n-th arrival over the chain's own steps: every step whose profile says the routine was entered is stopped
    there (`aes_boot.continued`'s `until`), and on from that stop to the next. Every byte of RAM there, the registers,
    the arguments READ OFF THE FRAME the desk's own caller pushed (the routine's declared Alcyon signature) and the
    address the call returns to. Nothing is poked.
  * A CASE of a routine that never reaches the dispatcher is the kit's plain differential over the arrival's megabyte
    (`plain`: `aes.run_function`, the answer at the declared width, every byte); one whose callee yields (a binding of
    unit D's) is A ROW THAT SWITCHES (`row_of`, `held`: `aes_switching.companion`, nothing dropped), unit D's shape.
  * THE ROM'S OWN RUN IN PLACE (`returned_in_place`): the machine continued from the arrival to the address the call
    returns to, on the desk's own stack — what the routine leaves its ROM caller in D0 and A0 there.
"""
import functools
from collections import namedtuple

import aes
import aes_boot
import aes_desk
import aes_event
import aes_switching as switching
import case
import vdi
from harness import addrs

BUS = aes_boot.BUS
WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES

# ---- THE SIGNATURES: `{routine: (the C core's answer, its frame's arguments in push order)}` ------------------------------
SIGNATURES = {
    "AES_ROM_APP_AFIND": (aes.LONG_ANSWER, (WORD, WORD, WORD, LONG, LONG)),
    "AES_ROM_GR_OBFIND": (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD)),
    "AES_ROM_GR_ISDOWN": (aes.WORD_ANSWER, (WORD, WORD, WORD, WORD, WORD, LONG, LONG, LONG, LONG)),
    "AES_ROM_GR_ACCOBS": (None, (LONG, WORD, LONG, LONG)),
    "AES_ROM_GR_EXTENT": (None, (WORD, LONG, LONG)),
    "AES_ROM_GR_OBALIGN": (None, (WORD, WORD, WORD, LONG)),
    "AES_ROM_GR_PLNS": (None, (WORD, WORD, WORD, LONG, WORD, LONG)),
    "AES_ROM_GR_BWAIT": (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD, LONG, WORD, LONG)),
    "AES_ROM_ACT_CHKOBJ": (aes.WORD_ANSWER, (LONG, WORD, WORD, WORD, WORD, WORD, WORD)),
    # ...and the three that call unit I's do_wredraw (and A's snap_disk): group G1's and G2's exports
    "AES_ROM_MOVE_DRVICON": (None, (LONG, WORD, WORD, WORD, LONG)),
    "AES_ROM_ACT_CHG": (aes.WORD_ANSWER, (WORD, LONG, WORD, WORD, LONG, WORD, WORD, WORD, WORD)),
    "AES_ROM_ACT_ALLCHG": (None, (WORD, LONG, WORD, WORD, LONG, LONG, WORD, WORD, WORD)),
}
UNIT_B = tuple(SIGNATURES)
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
# THE ROUTINES WHOSE CALLEES REACH THE DISPATCHER (a binding of unit D's): their cases are rows that switch.
YIELDING = ("AES_ROM_GR_OBFIND", "AES_ROM_GR_ISDOWN", "AES_ROM_GR_PLNS", "AES_ROM_GR_BWAIT", "AES_ROM_MOVE_DRVICON",
            "AES_ROM_ACT_CHG", "AES_ROM_ACT_ALLCHG")


# THE GROUP'S BAND, for what a labelled class lays: texts, points.
BAND_OFFSET, BAND_BYTES = 0x5E00, 0x200     # the window's last 512 bytes, past aes_switch.py's VDI thunks (+$5a00..+$5e00)
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_deskact.py: group G3's laid texts and points")
# ...and A TREE BAND OF ITS OWN, the window's last 1.5 KB: gr_accobs's cap is seen only past 60 selected children, and
# 62 objects (24 bytes each) fit no band of aes.py's staged tree (40 objects) — laid there, they ran over its blocks band
# and its rectangles band (reviewer B, wave 1b).
TREE_BAND_OFFSET, TREE_BAND_BYTES = 0x6000, 0x600
TREE_BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + TREE_BAND_OFFSET, TREE_BAND_BYTES, "test/aes_deskact.py: group G3's laid wide tree")


def laid_text(text, at=BAND_AT):
    """A NUL-ended text laid in the group's band: a labelled staging's pokes."""
    data = text.encode("latin1") + b"\0"
    assert at + len(data) <= BAND_AT + BAND_BYTES
    return {at: data}


def entry_of(name):
    return getattr(addrs, name)


# ---- AN ARRIVAL ---------------------------------------------------------------------------------------------------------------
Arrival = namedtuple("Arrival", "name chain nth boot arguments returns_to ends_at budget")
Arrival.__doc__ = """The chain `chain` of the hands stopped at its `nth` arrival (from 0) at routine `name`'s entry: the
`Boot` there, the `arguments` the desk's caller pushed (read off the frame by the declared signature, words unsigned)
and the address the call `returns_to`; `ends_at`: the named stop the step it was met in ends at (None: an idle), and
that step's `budget`."""


def _steps_as_walked(chain_name):
    """`[(the boot a step began from, what it received, the stop it began at, the stop it ends at, its budget, its
    Stepped)]` for the chain's own steps, as `aes_desk.walked` took them."""
    chain = aes_desk.CHAINS[chain_name]
    machine = aes_desk.MACHINES[chain.after]() if chain.after in aes_desk.MACHINES else aes_desk.walked(chain.after).machine
    taken, stands_at = [], None
    for step, done in zip(chain.steps, aes_desk.walked(chain_name).steps):
        ends_at = aes_desk.STOPS[step.until] if step.until else None
        taken.append((machine.boot, tuple(step.hand(machine)), stands_at, ends_at, step.budget, done))
        machine, stands_at = aes_boot.Machine(done.boot), ends_at
    return taken


def stack_pointer(boot):
    """The supervisor stack pointer the stopped CPU runs on (the desk runs in supervisor state)."""
    assert boot.registers["sr"] & aes_boot.SR_SUPERVISOR, "the desk's code is reached in supervisor state"
    return boot.registers["isp"] & BUS


def _frame_arguments(name, ram, sp):
    arguments, at = [], sp + LONG_BYTES
    for argtype in vdi.frame_argtypes(name):
        arguments.append(case.word_in(ram, at) if argtype is WORD else case.long_in(ram, at))
        at += vdi.ARG_BYTES[argtype]
    return tuple(arguments)


def _arrived(name, chain_name, nth, boot, ends_at, budget):
    sp = stack_pointer(boot)
    return Arrival(name, chain_name, nth, boot, _frame_arguments(name, boot.ram, sp), case.long_in(boot.ram, sp) & BUS,
                   ends_at, budget)


@functools.cache
def arrivals(name, chain_name, count=1):
    """THE FIRST `count` ARRIVALS OF THE CHAIN AT THE ROUTINE `name` (an `addrs` name), over its steps in order: each
    step whose profile says the routine's first instruction ran, stopped at its first arrival there and on from that
    stop to the next, to the step's end. Fewer where the chain arrives fewer times."""
    entry, found = entry_of(name), []
    for boot, received, stands_at, ends_at, budget, done in _steps_as_walked(chain_name):
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
    assert stack_pointer(boot) == stack_pointer(arrived.boot) + LONG_BYTES, (
        f"{label_of(arrived)}: the run reached {arrived.returns_to:#x} on another frame than the arrival's own return")
    return boot


def with_arguments(arrived, arguments, name=None):
    """AN ARGUMENT CLASS over an arrival's machine: the same megabyte, other arguments — and, where said, ANOTHER
    ROUTINE of the group entered over it."""
    return arrived._replace(arguments=tuple(arguments), name=name or arrived.name)


# ---- A CASE ---------------------------------------------------------------------------------------------------------------------
def label_of(arrived):
    return f"arrival {arrived.nth} of {arrived.chain!r} at {arrived.name}"


def machine_of(arrived, *layers):
    """The arrival's megabyte as a case's pokes, `layers` (labelled stagings) laid over it — every laid poke INTO THE
    AES'S WINDOW inside one claimed band (`aes.SPAN.require_claimed`; what is laid outside it is machine state, said in
    the case's id)."""
    for layer in layers:
        for at, data in layer.items():
            aes.SPAN.require_claimed(at, len(data))
    return case.merge_pokes({0: arrived.boot.ram}, *layers)


def plain(arrived, *layers, **kwargs):
    """A routine that never yields: the kit's differential over the arrival's megabyte. Its `aes.Result`."""
    return aes.run_function(arrived.name, arrived.arguments, machine_of(arrived, *layers), **kwargs)


def row_of(arrived, label, at_idle=None, at_calls=None, answered=True, layers=()):
    """THE ROW THAT SWITCHES a yielding routine's case is (`aes_event.woken_row`, its C's tree walks served): over the
    arrival's machine, its wait ended by `at_idle` / `at_calls`; `answered` False where the core answers no word."""
    pokes = machine_of(arrived, *layers)
    return aes_event.woken_row(label, arrived.name, arrived.arguments, lambda: pokes, at_idle or {}, at_calls, objects=True,
                               answered=answered)


def held(row):
    """TIER 1 of a yielding routine's case: `aes_switching.companion`, nothing dropped. Its `CompanionRun`."""
    return switching.companion(row)


def the_rom_s_run(row):
    """THE ROM'S OWN SCHEDULED RUN of the row: `.d0` what the routine leaves its caller, `.idles`."""
    return switching.scheduled(row, switching.settled(row).pokes)


# ---- THE CASES OF BOTH UNITS' BATTERIES (`test_desk_act.py`, `test_desk_fpd.py`) ----------------------------------------------
Case = namedtuple("Case", "name chain nth arm why over arguments laid steered wake", defaults=(0,) + (None,) * 7)
Case.__doc__ = """One case: routine `name` at the `nth` arrival of `chain`. `arm(arguments) -> bool`: what the arrival's own
arguments must be for the case to be the arm it was chosen for. AN ARGUMENT CLASS has a `why` (its label, in its id):
it runs over the arrival of routine `over` (None: its own) with `arguments` — a tuple, or `arrival -> tuple`. `laid`:
`(what, arrival -> pokes)`, a LABELLED STAGING laid over the megabyte (its `what` in the id). `steered`: the plain
differential's own keywords as pairs (UNPOISONED: a routine that follows the links it stores). `wake`: the
wake of a yielding routine's row (a key of its battery's WAKES)."""
ARGUMENT_CLASS = "__an_argument_class"
# THE ATTRIBUTION PASS INVERTS EVERY BYTE THE ROM'S RUN STORES and runs both shores again: a routine that stores a list's
# head or a node's link and then follows it (the free lists, the open paths, a list relinked) is steered by it into
# memory that is no list's. Its cases run unpoisoned — unit O's app_alloc / app_free precedent.
UNPOISONED = tuple(aes.STEERED_UNPOISONED.items())
LAID = "LAID"


def short_of(name):
    return name.removeprefix("AES_ROM_").lower()


def label(each):
    """THE CASE'S ID: the routine, what it runs over, what is laid, and the class's own label."""
    where = f"arrival {each.nth} of {each.chain}" + (f" (at {short_of(each.over)})" if each.over else "")
    said = f"{short_of(each.name)} — " + (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + where
    if each.laid:
        said += f" [{LAID}: {each.laid[0]}]"
    if each.wake:
        said += f"; {each.wake}"
    return said + (ARGUMENT_CLASS if each.why else "")


def by_label(cases):
    """`{id: case}` — refused where two cases have one id."""
    table = {label(each): each for each in cases}
    assert len(table) == len(cases), "two cases of one id"
    return table


@functools.cache
def _arrival_of(each):
    arrived = arrival(each.over or each.name, each.chain, each.nth)
    assert each.arm is None or each.arm(arrived.arguments), (
        f"{label(each)}: the arrival's arguments {arrived.arguments} are not the arm it names")
    if not each.why:
        return arrived
    arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
    return with_arguments(arrived, arguments, each.name)


def arrival_of(each):
    """The case's `Arrival`: the chain's own, or — an argument class — that machine under the case's routine and
    arguments. The arm the case was chosen for is held here."""
    return _arrival_of(each)


def layers_of(each):
    return (each.laid[1](arrival_of(each)),) if each.laid else ()


ANSWER_WIDTH = {aes.WORD_ANSWER: aes.WORD_MASK, aes.LONG_ANSWER: aes.LONG_MASK}


def answered_at_its_width(name, d0):
    return d0 & ANSWER_WIDTH[vdi.ALCYON[name].restype]


def held_plain(each):
    """A PLAIN CASE: the differential over the arrival's megabyte (and what is laid). Its `aes.Result`."""
    return plain(arrival_of(each), *layers_of(each), **dict(each.steered or ()))


# ---- LINKED AND UNBOUND -------------------------------------------------------------------------------------------------------
def table_verdicts(names):
    """`{name: the Line-F table generator's verdict for its entry}` (`bench/linef_table.py`)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    ours = {entry_of(name): name for name in names}
    return {ours[entry.target]: entry.verdict for entry in linef_table.entries() if entry.target in ours}, linef_table


def group():
    """GROUP G3's routines: units B and G."""
    import aes_deskfpd
    return (*UNIT_B, *aes_deskfpd.UNIT_G)


def registered(names):
    """The registered rows (the registries' own, the switching rows) that are a routine's of `names`: none, unbound."""
    import routines
    cores = {routines.core_symbol(name) for name in names}
    rows = (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS)
    return [row for row in rows if row.split(",")[0] in cores]
