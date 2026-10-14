"""THE DESK'S WINDOW OBJECTS AND PROGRAM LEAVES AT THEIR ARRIVALS — unit I's signatures (`src/desk/deskwin.c`;
band 6 wave 1b, group G1) and THE GROUP'S CASE MACHINERY, which unit L's battery (`aes_deskview.py`) shares.

HELD AT TIER 1, NOTHING BOUND. Each case is the C core against the ROM's own routine on the host library, over A
MACHINE A ROM RUN MADE:

  * THE ARRIVAL (`arrival`): a chain of the hands (`aes_desk.CHAINS`) walked to the first step whose profile says the
    routine's first instruction ran, that step's run stopped at its n-th arrival there (`aes_deskleaves.arrival`).
    The megabyte and the registers are what the ROM's own caller left; the arguments are read off the frame it
    pushed (the routine's declared signature), the return site off the stack. Nothing is poked.
  * THE ROM'S OWN RUN IN PLACE (`in_place`): that boot continued — over the machine's own GEMDOS where the routine
    reaches the DOS glue — to each place a `trap #1` of the glue returns to, then to the routine's return: what
    GEMDOS ANSWERED, and D0 and A0 where the routine returns to its caller.
  * THE DIFFERENTIAL (`ran`): a routine whose run reaches the dispatcher (it calls a binding of unit D's, every one
    of which yields) is A ROW THAT SWITCHES — `aes_event.woken_row`, held by `aes_switching.companion` with nothing
    dropped; a routine that never yields is the kit's plain differential (`aes.run_function`). A routine that traps
    through the DOS glue has its `trap #1` answered on both shores by `aes_gemdosif`'s recording, scripted trap WITH
    THE ANSWERS ITS RUN IN PLACE GOT — a labelled staging, said in the case's id (`SCRIPTED`).
"""
import functools
import sys
from collections import namedtuple
from pathlib import Path

from harness import addrs

import aes
import aes_boot
import aes_desk
import aes_deskbind as db
import aes_deskleaves as dl
import aes_event
import aes_gemdosif as gd
import aes_switching as switching
import routines
import transcription
import vdi

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
BUS = aes_boot.BUS
RECT = (WORD,) * 4

# ---- UNIT I's SIGNATURES: `{routine: (the C core's answer, its frame's arguments in push order)}` --------------------
SIGNATURES = {
    "AES_ROM_OBJ_INIT": (None, ()),
    "AES_ROM_OBJ_WALLOC": (aes.WORD_ANSWER, RECT),
    "AES_ROM_OBJ_WFREE": (None, (WORD, *RECT)),
    "AES_ROM_OBJ_IALLOC": (aes.WORD_ANSWER, (WORD, *RECT)),
    "AES_ROM_PRO_CHDIR": (aes.WORD_ANSWER, (WORD, LONG)),
    "AES_ROM_PRO_CMD": (aes.WORD_ANSWER, (LONG, LONG, WORD, WORD)),
    "AES_ROM_PRO_EXEC": (aes.WORD_ANSWER, (WORD, WORD, LONG, LONG)),
    "AES_ROM_DESK_RSRC_LOAD": (aes.WORD_ANSWER, ()),
    "AES_ROM_INI_TREE": (aes.WORD_ANSWER, (LONG, WORD)),
    "AES_ROM_INI_STR": (aes.LONG_ANSWER, (WORD,)),
    "AES_ROM_DO_WREDRAW": (None, (WORD, *RECT)),
    "AES_ROM_GET_XYWH": (None, (LONG, WORD, *(LONG,) * 4)),
    "AES_ROM_GET_SPEC": (aes.LONG_ANSWER, (LONG, WORD)),
    "AES_ROM_DO_XYFIX": (None, (LONG, LONG)),
    "AES_ROM_ZOOM_CLOSED": (None, (WORD,) * 4),
    "AES_ROM_DO_WFULL": (None, (WORD,)),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_I = tuple(SIGNATURES)
# The routines whose run reaches the dispatcher — through a binding of unit D's — on every arm a case takes: rows that
# switch.
YIELDS_I = frozenset({"AES_ROM_OBJ_INIT", "AES_ROM_OBJ_IALLOC", "AES_ROM_PRO_EXEC", "AES_ROM_INI_TREE", "AES_ROM_INI_STR",
                      "AES_ROM_DO_WREDRAW", "AES_ROM_DO_XYFIX", "AES_ROM_ZOOM_CLOSED", "AES_ROM_DO_WFULL"})
# ...and the routines whose run traps through the DOS glue (pro_chdir's Dsetdrv and Dsetpath).
TRAPS_I = frozenset({"AES_ROM_PRO_CHDIR"})


# ---- THE GROUP'S CASE MACHINERY ---------------------------------------------------------------------------------------
def declare_trapping_rows(names):
    """A routine that both TRAPS and SWITCHES runs its C in a child under the scheduler's model: the scripted trap's
    host twins bound there (`aes_gemdosif.CHILD_DOORS`)."""
    for name in names:
        aes_event.declare_child_doors(name, gd.CHILD_DOORS)


@functools.cache
def step_entering(routine, chain):
    """The first step of the chain `chain` whose run entered `routine` (read off its profile) — refused by name."""
    entry = getattr(addrs, routine)
    for step, done in enumerate(aes_desk.walked(chain).steps):
        if entry in aes_desk.cycles_at(done.profile):
            return step
    raise aes_boot.Refused(f"the chain {chain!r} never enters {routine} ({entry:#x})")


def arrival(routine, chain, nth=1):
    """`routine`'s `nth` arrival (from 1) in the first step of `chain` that enters it: an `aes_deskleaves.Arrival`."""
    return dl.arrival(dl.At(routine, chain, step_entering(routine, chain), nth))


InPlace = namedtuple("InPlace", "answers returned")
InPlace.__doc__ = """The ROM's run of an arrival's routine IN PLACE: what each `trap #1` of the glue `answers` (D0 where
`__DOS`'s trap returns), and the `Boot` where the routine `returned` to its caller."""


@functools.cache
def _in_place(routine, chain, nth, traps):
    arrived = arrival(routine, chain, nth)
    boot, stands_at, answers = arrived.boot, getattr(addrs, routine), []
    for _trap in range(traps):
        boot = aes_boot.continued.derive(boot, (), dl.ARRIVAL_INSNS, dl.GEM_DOS_BACK, stands_at)
        stands_at = dl.GEM_DOS_BACK
        answers.append(boot.registers["d0"])
    boot = aes_boot.continued.derive(boot, (), dl.ARRIVAL_INSNS, arrived.return_site, stands_at)
    called_at = db.stack_pointer(arrived.boot)
    if db.stack_pointer(boot) != called_at + aes.LONG_BYTES:
        raise aes_boot.Refused(f"{routine}: the run reached {arrived.return_site:#x} on another frame than its own return")
    return InPlace(tuple(answers), boot)


def in_place(routine, chain, nth=1, traps=0):
    """THE ROM'S OWN RUN of the arrival IN PLACE (the module's docstring), through `traps` traps of the glue."""
    return _in_place(routine, chain, nth, traps)


def megabyte(arrived, answers=None):
    """The arrival's megabyte as a case's pokes; with `answers`, the glue's `trap #1` scripted to answer them."""
    pokes = {0: arrived.boot.ram}
    return pokes if answers is None else gd.scripted_over(pokes, answers)


def plain(name, arguments, pokes, answers=None, **kwargs):
    """A routine that never yields: the kit's differential over `pokes` — scripted where `answers` are given."""
    if answers is None:
        return aes.run_function(name, arguments, pokes, **kwargs)
    return aes.run_function(name, arguments, pokes, hook=gd.scripted_hook, poison=False, **kwargs)


def row(label, name, arguments, pokes, answered, budget=None):
    """A routine that yields: THE ROW THAT SWITCHES (`aes_event.woken_row`, its C's tree walks served), nothing
    woken — every binding it reaches yields and none waits. `answered` False where its answer is a named divergence."""
    return aes_event.woken_row(label, name, arguments, lambda: pokes, {}, None, objects=True, answered=answered,
                               budget=budget)


def held(the_row):
    """TIER 1 of a row: `aes_switching.companion`, nothing dropped. Its `CompanionRun`."""
    return switching.companion(the_row)


def the_rom_s_run(the_row):
    """THE ROM'S OWN SCHEDULED RUN of the row: `.d0`, `.memory`, `.entered`, `.idles`."""
    return switching.scheduled(the_row, switching.settled(the_row).pokes)


# ---- A CASE, and what it holds -----------------------------------------------------------------------------------------
Case = namedtuple("Case", "name chain nth arm arguments why traps budget", defaults=(1, None, None, None, 0, None))
# A CASE OVER THE LEAF MACHINE (`aes.leaf_machine`: the dispatcher's bare `rts` for dsptch) where the C cannot run at
# its arrivals at all — its `chain`. NO ARGUMENT CLASS (arrivals exist; the HARNESS cannot run the C there): its id
# says UNPINNED AT ITS ARRIVALS, and its `why` why.
LEAF_MACHINE = "the leaf machine"
UNPINNED_AT_ARRIVAL = "UNPINNED AT ITS ARRIVALS"
Case.__doc__ = """One case: the routine `name` (an `addrs` name) at the `nth` arrival (from 1) of `chain`. `arm`: what the
arrival's own arguments must be for the case to be the arm it was chosen for (`arguments -> bool`). AN ARGUMENT CLASS
has a `why` (its label): the same machine with `arguments` (a tuple, or `arrival -> tuple`). `traps`: how many
`trap #1`s of the glue its run makes, each answered as the run in place was (SCRIPTED). `budget`: a row's own derivation budget, declared from its measured run
(`aes_event`'s rule: DERIVATION_INSNS < 5 x the run <= the budget <= 10 x the run)."""
# WHAT IS STAGED OVER AN ARRIVAL'S MEGABYTE, SAID IN THE ID OF EVERY CASE THAT STAGES IT (`aes_deskleaves`' words):
SCRIPTED = "GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers"


def label(each):
    """The case's id: the routine, the class it is (if one), the arrival, and what is staged."""
    said = f"{each.name[len('AES_ROM_'):].lower()} — "
    if each.chain == LEAF_MACHINE:
        return said + f"{UNPINNED_AT_ARRIVAL} ({each.why}): its C held over {LEAF_MACHINE}"
    said += (f"ARGUMENT CLASS ({each.why}), over " if each.why else "") + f"arrival {each.nth} of {each.chain}"
    return said + (f"; {SCRIPTED}" if each.traps else "")


@functools.cache
def _arrived(name, chain, nth):
    return arrival(name, chain, nth)


def arrival_of(each):
    """The case's `Arrival` — its own arguments, or the class's over the same machine; the arm held here."""
    arrived = _arrived(each.name, each.chain, each.nth)
    assert each.arm is None or each.arm(arrived.arguments), \
        f"{label(each)}: the arrival's arguments {arrived.arguments} are not the arm it names"
    if not each.why:
        return arrived
    arguments = each.arguments(arrived) if callable(each.arguments) else each.arguments
    return arrived._replace(arguments=tuple(arguments))


def answers_of(each):
    """What the glue's traps answered in the ROM's own run in place (none for a routine that traps nothing)."""
    return in_place(each.name, each.chain, each.nth, each.traps).answers if each.traps else None


def machine_of(each):
    """`(the case's pokes, its arguments)`: the arrival's megabyte (scripted where it traps), or the leaf machine."""
    if each.chain == LEAF_MACHINE:
        return aes.leaf_machine(), tuple(each.arguments)
    arrived = arrival_of(each)
    return megabyte(arrived, answers_of(each)), arrived.arguments


def ran(each, yields):
    """THE CASE'S TIER 1: a row that switches (`held`) where the routine `yields`, else the plain differential.
    Answers `(the C's answer or None, the ROM's D0 there, how often the ROM's run idled)`."""
    pokes, arguments = machine_of(each)
    signature = vdi.ALCYON[each.name]
    if yields:
        the_row = row(label(each), each.name, arguments, pokes, signature.restype is not None, each.budget)
        companion, the_rom_s = held(the_row), the_rom_s_run(the_row)
        return companion.answer, the_rom_s.d0, the_rom_s.idles
    result = plain(each.name, arguments, pokes, answers_of(each))
    answer = {None: None, aes.WORD_ANSWER: result.answer, aes.LONG_ANSWER: result.long_answer}[signature.restype]
    return (answer() if answer else None), result.info["regs"]["d0"], 0


# ---- LINKED AND UNBOUND: what both units' batteries hold of their cores ------------------------------------------------
BENCH = Path(__file__).resolve().parents[1] / "bench"


def _linef_table():
    sys.path.insert(0, str(BENCH))
    import linef_table                  # HERE, not at the module's top: the generator imports every battery's registry
    return linef_table


def verdicts_not_the_rom_s(names):
    """The table entries naming a routine of `names` whose verdict is NOT the ROM's (`linef_table.entries()`), and the
    registered rows that are one of theirs: both empty while nothing is bound."""
    table = _linef_table()
    ours = {getattr(addrs, name): name for name in names}
    flipped = {ours[entry.target] for entry in table.entries() if entry.target in ours and entry.verdict != table.THE_ROM_S}
    cores = {routines.core_symbol(name) for name in names}
    rows = [name for name in (*(row[0] for row in (*aes.CASES, *aes.UNPRICED)), *aes_event.SWITCHING_ROWS)
            if name.split(",")[0] in cores]
    return flipped, rows
