"""UNIT A, THE DESK'S APPLICATION LIST, AT ITS ARRIVALS — band 6 wave 1b, group G2 (`src/desk/deskapp.c`,
`test_desk_app.py`); and THE GROUP'S ARRIVALS, which units K and J (`aes_desktop.py`, `aes_desksupp.py`) take too.

HELD AT TIER 1, NOTHING BOUND: no routine here has a table entry, a registry row or a price. Each is its C core against
the ROM's own routine on the host library, over A MACHINE A ROM RUN MADE.

  * AN ARRIVAL (`arrival`) is a chain of the hands (`aes_desk.CHAINS`) — or the DESKTOP.INF machine's own boot —
    STOPPED AT THE ROUTINE'S FIRST INSTRUCTION, where the desk's own caller calls it: `aes_boot.continued(..., until=)`
    over each step whose profile says the routine was entered, and from that stop on to the next for the n-th. The
    arguments are READ OFF THE FRAME the caller pushed, by the routine's declared signature; nothing is poked.
  * A CASE of a routine that never reaches the dispatcher is the kit's differential over the arrival's megabyte
    (`plain`); of one that does (a binding's yield under it) the row that switches (`row_of`, `held`:
    `aes_switching.companion`, nothing dropped), as unit D's bindings are (`aes_deskbind`).
  * THE ROM'S OWN RUN IN PLACE (`returned_in_place`): the arrival continued to the address its caller's call returns
    to, on the desk's own stack — D0 and A0 as the routine leaves its ROM caller.
"""
import functools
import struct
from collections import namedtuple
from pathlib import Path

import aes
import aes_boot
import aes_desk
import aes_event
import aes_gemdosif as gd
import aes_shmain
import aes_switching as switching
import case
import gemdos
import layouts
import preinit_snapshot
import vdi
from harness import addrs

BUS = aes_boot.BUS
WORD, LONG, IMAGE = vdi.WORD_ARG, vdi.LONG_ARG, vdi.IMAGE_ARG
LONG_BYTES = aes.LONG_BYTES
# Unit A's header's constants (`include/desk/deskapp.h`, and the desk's globals' one home `deskglobals.h` and unit O's
# `deskleaf.h` it builds on), read as every AES header's are.
HEADER = Path(__file__).resolve().parents[1] / "include" / "desk" / "deskapp.h"
CONSTANTS = layouts.parse_constants((HEADER.parent / "deskglobals.h", HEADER.parent / "deskleaf.h", HEADER),
                                    known={**vdi.CONSTANTS, **aes.CONSTANTS})

# ---- THE SIGNATURES: `{routine: (the C core's answer, its frame's arguments in push order)}` ---------------------------------
SIGNATURES = {
    "AES_ROM_SCAN_STR": (aes.LONG_ANSWER, (LONG, LONG)),
    "AES_ROM_SAVE_STR": (aes.LONG_ANSWER, (LONG, LONG)),
    "AES_ROM_APP_PARSE": (aes.LONG_ANSWER, (LONG, LONG)),
    "AES_ROM_APP_TRAN": (aes.WORD_ANSWER, (WORD,)),
    "AES_ROM_APP_RDICON": (aes.WORD_ANSWER, ()),
    "AES_ROM_APP_GETFH": (aes.WORD_ANSWER, (WORD, LONG, WORD)),
    "AES_ROM_SNAP_DISK": (None, (WORD, WORD, LONG, LONG)),
    "AES_ROM_APP_REVIT": (None, ()),
    "AES_ROM_APP_PATH_SAVE": (aes.LONG_ANSWER, ()),
    "AES_ROM_APP_PATH_RESTORE": (aes.LONG_ANSWER, ()),
    "AES_ROM_APP_BLDDESK": (aes.WORD_ANSWER, ()),
}
for _name, (_restype, _frame) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, (IMAGE, *_frame))
UNIT_A = tuple(SIGNATURES)
# app_rdicon both TRAPS (two Mallocs) and SWITCHES (app_tran's binding): its C runs in a child under the scheduler's
# model, band 5's scripted trap's host twins bound there (`aes_gemdosif.CHILD_DOORS`: Malloc is one of its functions).
aes_event.declare_child_doors("AES_ROM_APP_RDICON", gd.CHILD_DOORS)
# app_blddesk asks GETREZ (the XBIOS door) and switches (obj_ialloc's objc_add): on the ROM's shore the XBIOS is
# answered by band 5's staged Getrez trap (`aes_shmain.getrez_pokes`), on ours Getrez's own C core over the same
# shifter byte declared in its child (`aes_shmain.getrez_in_a_child`) — THE ARRIVALS' OWN MODE (`getrez_layer` holds
# it to the machine's byte), a LABELLED STAGING said in the case's id (`GETREZ_STAGED`).
GETREZ_STAGED = "THE XBIOS'S GETREZ STAGED: the arrival's own shifter mode"
ARRIVALS_REZ = aes_shmain.MODES["low"]
SHIFTER_MODE_BITS = 0x03                # the resolution byte's mode (`addrs.h`: SHIFTER_RESOLUTION, bits 0-1)
aes_event.declare_child_doors("AES_ROM_APP_BLDDESK", f"import aes_shmain; aes_shmain.getrez_in_a_child({ARRIVALS_REZ}); ")


# ---- AN ARRIVAL (the group's: units K and J take theirs here too) -------------------------------------------------------------
Arrival = namedtuple("Arrival", "routine chain nth boot arguments returns_to ends_at budget")
Arrival.__doc__ = """The chain `chain` of the hands (or THE_BOOT) stopped at its `nth` arrival (from 0) at `routine`'s
entry (an `addrs` name): the `Boot` there, the `arguments` the desk's caller pushed — read off the frame by the
routine's declared signature, words unsigned — and the address the call `returns_to`; `ends_at`: the named stop the
step it was met in ends at (None: an idle), and that step's `budget`."""
THE_BOOT = "the boot of the DESKTOP.INF machine"


def entry_of(routine):
    return getattr(addrs, routine)


def stack_pointer(boot):
    """The supervisor stack pointer the stopped CPU runs on (the desk runs in supervisor state)."""
    assert boot.registers["sr"] & aes_boot.SR_SUPERVISOR, "the desk's code is reached in supervisor state"
    return boot.registers["isp"] & BUS


def _frame_arguments(routine, ram, sp):
    """The arguments of `routine` off the frame above the return address at `sp`."""
    frame = struct.Struct(">" + "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(routine)))
    return tuple(value & aes.WORD_MASK if argtype is WORD else value for argtype, value in
                 zip(vdi.frame_argtypes(routine), frame.unpack(bytes(ram[sp + LONG_BYTES:sp + LONG_BYTES + frame.size]))))


def _arrived(routine, chain, nth, boot, ends_at, budget):
    sp = stack_pointer(boot)
    return Arrival(routine, chain, nth, boot, _frame_arguments(routine, boot.ram, sp), case.long_in(boot.ram, sp) & BUS,
                   ends_at, budget)


def _steps(chain_name):
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


@functools.cache
def arrivals(routine, chain_name, count=1):
    """THE FIRST `count` ARRIVALS OF THE CHAIN `chain_name` AT `routine`, over its steps in order — each step whose
    profile says the routine's first instruction ran is stopped at its first arrival, then on from there to the next,
    to the step's end (a step that ends at a named stop gives its first alone). THE_BOOT: the DESKTOP.INF machine's
    own boot stopped at its first arrival (`aes_boot.booted(until=)`)."""
    entry, found = entry_of(routine), []
    if chain_name == THE_BOOT:
        boot = aes_boot.booted(aes_boot.inf_preinit(), aes_boot.inf_disk_of(), until=entry)
        return (_arrived(routine, chain_name, 0, boot, None, aes_boot.BOOT_INSNS),)
    for boot, received, stands_at, ends_at, budget, done in _steps(chain_name):
        if len(found) >= count or entry not in aes_desk.cycles_at(done.profile):
            continue
        found.append(_arrived(routine, chain_name, len(found), aes_boot.continued(boot, received, budget, entry, stands_at),
                              ends_at, budget))
        while len(found) < count and ends_at is None:
            try:
                following = aes_boot.continued(found[-1].boot, (), budget, entry, entry)
            except aes_boot.Refused:
                break
            found.append(_arrived(routine, chain_name, len(found), following, ends_at, budget))
    return tuple(found)


def arrival(routine, chain_name, nth=0):
    """The chain's `nth` arrival at `routine` — refused by name where it arrives fewer times."""
    found = arrivals(routine, chain_name, nth + 1)
    if len(found) <= nth:
        raise aes_boot.Refused(f"the chain {chain_name!r} arrives at {routine} {len(found)} time(s): no arrival {nth}")
    return found[nth]


def returned_in_place(arrived):
    """THE ROM'S OWN RUN IN PLACE from the arrival to the address its caller's call returns to, on the desk's own
    stack: the `Boot` there — None where the machine idles first."""
    try:
        boot = aes_boot.continued(arrived.boot, (), arrived.budget, arrived.returns_to, entry_of(arrived.routine))
    except aes_boot.Refused:
        return None
    assert stack_pointer(boot) == stack_pointer(arrived.boot) + LONG_BYTES, (
        f"{arrived.routine}: the run reached {arrived.returns_to:#x} on another frame than the arrival's own return")
    return boot


def with_arguments(arrived, *arguments, routine=None):
    """A LABELLED ARGUMENT CLASS over an arrival's machine: the same megabyte, other arguments than its caller pushed —
    and, where said, ANOTHER routine of the group entered over it."""
    return arrived._replace(arguments=tuple(arguments), routine=routine or arrived.routine)


# ---- A CASE ------------------------------------------------------------------------------------------------------------------------
def machine_of(arrived, *layers):
    """The arrival's megabyte as a case's pokes, `layers` laid over it (each a labelled staging of its case)."""
    return case.merge_pokes({0: arrived.boot.ram}, *layers)


def plain(arrived, *layers, **kwargs):
    """A ROUTINE THAT NEVER YIELDS: the kit's differential over the arrival's megabyte. Its `aes.Result`."""
    return aes.run_function(arrived.routine, arrived.arguments, machine_of(arrived, *layers), **kwargs)


def shifter_of(arrived):
    """THE ARRIVAL'S OWN SHIFTER BYTES as the kit's declared I/O map (`io_seed`): Getrez reads the resolution there —
    the machine's, as the boot's model holds it."""
    return {preinit_snapshot.IO_AT + offset: byte for offset, byte in enumerate(arrived.boot.io)}


def getrez_layer(arrived):
    """The staged Getrez trap answering THE ARRIVAL'S OWN MODE — refused by name where its shifter holds another."""
    mode = arrived.boot.io[addrs.SHIFTER_RESOLUTION - preinit_snapshot.IO_AT] & SHIFTER_MODE_BITS
    assert mode == ARRIVALS_REZ, f"{label_of(arrived)}: its shifter's mode is {mode}, not the one its child declares"
    return aes_shmain.getrez_pokes(mode)


def label_of(arrived):
    return f"arrival {arrived.nth} of {arrived.chain!r} at {arrived.routine}"


def row_of(arrived, at_idle=None, at_calls=None, label=None, answered=None, layers=()):
    """...AND ONE THAT DOES (a binding's yield under it): the row that switches (`aes_event.woken_row`, its C's tree
    walks served) over the arrival's machine — `layers` laid over it —, its waits ended by `at_idle` / `at_calls`.
    `answered`: whether the answer is compared (by default whether the core answers a word at all)."""
    pokes = machine_of(arrived, *layers)
    if answered is None:
        answered = vdi.ALCYON[arrived.routine].restype is not None
    return aes_event.woken_row(label or label_of(arrived), arrived.routine, arrived.arguments, lambda: pokes, at_idle or {},
                               at_calls, objects=True, answered=answered)


def held(row):
    """TIER 1 of a yielding routine's case: `aes_switching.companion`, nothing dropped. Its `CompanionRun`."""
    return switching.companion(row)


def the_rom_s_run(row):
    """THE ROM'S OWN SCHEDULED RUN of the row over its settled machine (`.d0`, `.memory`, `.idles`)."""
    return switching.scheduled(row, switching.settled(row).pokes)


# ---- GEMDOS UNDER THE GROUP'S ROUTINES: A RECORDING, SCRIPTED TRAP WITH THE ROM'S OWN ANSWERS ----------------------------------
# A routine of the group that calls the DOS glue traps through `__DOS`'s (or dos_alloc's own) `trap #1`. On both shores
# of a case that trap is `aes_gemdosif.Recorder`'s — the ledger of every call (the function, its frame's own bytes, and
# the two returns the glue parks AT THAT CALL) held equal by the megabyte, each call answered by the script — and THE
# SCRIPT IS WHAT THE ROM'S OWN RUN IN PLACE GOT (`dos_answers_in_place`): A LABELLED STAGING, said in every such case's
# id (`SCRIPTED`). GEMDOS itself does not run: what it would have written (Dgetpath's path) is written on neither shore.
SCRIPTED = "GEMDOS SCRIPTED: the recording trap answers the ROM's own run's answers"
BAND_OFFSET, BAND_BYTES = 0x2600, 0x200         # the gap between aes_switch.py's band (+$2500) and aes_gemdosif.py's (+$2800)
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_deskapp.py: group G2's recording GEMDOS trap")
DOS_FRAME_BYTES = {addrs.GEMDOS_DGETDRV_FN: 0, addrs.GEMDOS_DSETDRV_FN: aes.WORD_BYTES, addrs.GEMDOS_DSETPATH_FN: LONG_BYTES,
                   addrs.GEMDOS_DGETPATH_FN: LONG_BYTES + aes.WORD_BYTES, addrs.GEMDOS_FOPEN_FN: LONG_BYTES + aes.WORD_BYTES,
                   addrs.GEMDOS_FCREATE_FN: LONG_BYTES + aes.WORD_BYTES, addrs.GEMDOS_MALLOC_FN: LONG_BYTES,
                   addrs.GEMDOS_MFREE_FN: LONG_BYTES}
GEMDOS = gd.Recorder(addrs.VECTOR_TRAP_GEMDOS, BAND_AT, 0xB0, DOS_FRAME_BYTES, entries=10,
                     parked=(aes.AES_DOS_RETURN, aes.AES_TRAP1_RETURN))
assert GEMDOS.end <= BAND_AT + BAND_BYTES
DOS_HANDLERS = {gemdos.rom_handler(function): GEMDOS.twin(function) for function in DOS_FRAME_BYTES}


def scripted_hook():
    """The host twins bound as `aes.run_function`'s `hook`."""
    return gemdos.bound_handlers(DOS_HANDLERS)


def dos_answers_in_place(arrived, traps):
    """WHAT GEMDOS ANSWERED THE ROM'S OWN RUN IN PLACE: from the arrival, `traps` times to the GEMDOS handler's entry
    and on to the address its exception frame returns to — D0 there — then to the routine's own return. Each trap is
    held to be TAKEN INSIDE THE ROUTINE (the stack deeper than the arrival's: a count too high meets a trap of its
    caller's and is refused by name; one too low leaves the C's script short, which its trap refuses). `(the answers,
    the Boot at the return)`."""
    boot, stands_at, answers = arrived.boot, entry_of(arrived.routine), []
    handler = case.long_in(boot.ram, addrs.VECTOR_TRAP_GEMDOS) & BUS
    for nth in range(traps):
        boot = aes_boot.continued(boot, (), arrived.budget, handler, stands_at)
        sp = stack_pointer(boot)
        assert sp < stack_pointer(arrived.boot), f"{label_of(arrived)}: its trap {nth} is its caller's, not its own"
        back = case.long_in(boot.ram, sp + aes.WORD_BYTES) & BUS
        boot = aes_boot.continued(boot, (), arrived.budget, back, handler)
        answers.append(boot.registers["d0"])
        stands_at = back
    boot = aes_boot.continued(boot, (), arrived.budget, arrived.returns_to, stands_at)
    assert stack_pointer(boot) == stack_pointer(arrived.boot) + LONG_BYTES, f"{label_of(arrived)}: not its own return"
    return tuple(answers), boot


def scripted(arrived, answers, *layers, **kwargs):
    """A ROUTINE THAT TRAPS, at its arrival: the plain differential with the recording trap staged over the megabyte
    and bound on the host, scripted with `answers` (`dos_answers_in_place`'s)."""
    return plain(arrived, GEMDOS.pokes(answers), *layers, hook=scripted_hook, poison=False, **kwargs)


def scripted_row(arrived, answers, **kwargs):
    """A ROUTINE THAT BOTH TRAPS AND SWITCHES, at its arrival: the row over the megabyte with BAND 5's recording trap
    (`aes_gemdosif.GEMDOS`, whose host twins its child binds: `aes_event.declare_child_doors`) scripted with
    `answers` — `SCRIPTED`."""
    return row_of(arrived, layers=(gd.GEMDOS.pokes(answers),), **kwargs)


def dos_calls(image):
    """The recording trap's ledger in `image`: `[(function, frame bytes and the two parked returns)]`, in order."""
    return GEMDOS.ledger.recorded(image)
