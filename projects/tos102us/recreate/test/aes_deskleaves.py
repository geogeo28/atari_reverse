r"""THE DESK'S LEAVES FILED IN AES MODULES — band 6 wave 1a, unit O (`src/desk/deskleaf.c`, `test_desk_leaves.py`):
how eighteen routines only the ROM's desk calls are held AT TIER 1 (flipped since band 6 slice F1: their rows at the
same arrivals, `row_pokes`).

A CASE IS TAKEN AT AN ARRIVAL wherever a hand's chain reaches the routine (`aes_desk.reach`: seventeen of the
eighteen — all but gsx_hardcopy, whose printer the model has not):

  * THE ARRIVAL (`arrival`): a chain of `aes_desk.CHAINS` walked to the step whose run enters the routine, and THAT
    step's run stopped at the routine's first instruction, at its n-th arrival there (`aes_boot.continued`'s `until`
    and `at`: the stop is named, an address of the ROM's own text). The megabyte and the registers there are what the
    ROM's own caller left; the arguments are read off the frame it pushed, the return site off the stack. No poke.
  * THE ROM'S OWN RUN IN PLACE (`in_place`): that boot continued — through `aes_boot`'s device model, the real
    GEMDOS, the real disk — to each place the routine's `trap` returns to and then to its return: what the OS
    ANSWERED (D0 at each trap's return), the frame the trap was taken over, and D0 and A0 where the routine returns.
  * THE DIFFERENTIAL (`held`): the ROM's routine against the host C core, both entered over the arrival's megabyte on
    the harness's own stack (`aes.run_function`). A `trap #1` is answered on both shores by the recording, scripted
    trap of `aes_gemdosif` WITH THE ANSWERS THE ROM'S OWN RUN IN PLACE GOT — A LABELLED STAGING, said in every such
    case's ID (`test_desk_leaves.SCRIPTED`): the vector, the handler, its ledger and its script are staged over the
    megabyte, and GEMDOS itself does not run. (Band 5's priced glue rows are scripted by `aes_shell.scripted_pokes`,
    a lighter handler: the price probes of this unit quote both, and a bare trap's figures beside them.) What the differential holds: the call list in order with each frame's own bytes, both parked
    returns as each trap found them, the glue's verdict, D0 at the declared width, and every other byte of the megabyte.

A FRAME THAT BEGINS WITH AN ADDRESS OF THE ROUTINE'S OWN STACK (dos_label's DTA and search path, dos_space's Dfree
answers, dos_setdt's stamp) differs between the shores BY NATURE — the ROM's frame is on the run's stack, the C's in
its host slot — so the ledger records nothing of such a frame, and the host twin KEEPS WHAT IT WAS POINTED AT instead
(`Seen.seen`: the text or the bytes behind the pointer, and the words after it), held to what the ROM's in-place run
handed its trap. And since the scripted trap stores nothing, WHAT GEMDOS WOULD HAVE LAID IN SUCH A FRAME IS LAID
BEFORE THE CALL on both shores (`frame_laid`): in the ROM's frame where the harness's stack will put it, in the C's
host slot — labelled in the case's ID (`test_desk_leaves.FRAME_LAID`).

WHERE NO CHAIN REACHES AN ARM the case is a labelled argument class over the leaf machine (`scripted`), as band 5's
glue entries are held (`test_aes_gemdosif_drives.py`).

THE HARNESS'S OWN FOOTPRINT ON AN ARRIVAL'S MEGABYTE: the run's stack band and this module's band lie in memory the
machine holds free — or, at the arrivals inside a file copy, in the copy's own buffer (the desk has Malloc'ed the
largest block): bytes no routine of this unit reads. Said, not vetted.
"""
import contextlib
import ctypes
import functools
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu

import aes
import aes_boot
import aes_desk
import aes_gemdosif as gd
import aes_shell as shell
import case
import gemdos
import routines
import vdi
from case import merge_pokes

WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
BUS = aes_boot.BUS
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ---------------------------------------------------------------------------------
GSX_PLINE, APP_ALLOC, APP_FREE = "AES_ROM_GSX_PLINE", "AES_ROM_APP_ALLOC", "AES_ROM_APP_FREE"
DOS_WRITE, DOS_GDIR, DOS_MKDIR, DOS_SETDT = "AES_ROM_DOS_WRITE", "AES_ROM_DOS_GDIR", "AES_ROM_DOS_MKDIR", "AES_ROM_DOS_SETDT"
DOS_LABEL, DOS_SPACE, DOS_RENAME, DOS_AVAIL = "AES_ROM_DOS_LABEL", "AES_ROM_DOS_SPACE", "AES_ROM_DOS_RENAME", "AES_ROM_DOS_AVAIL"
DOS_RAWCIO, DOS_CHMOD, DOS_DELETE = "AES_ROM_DOS_RAWCIO", "AES_ROM_DOS_CHMOD", "AES_ROM_DOS_DELETE"
DOS_RMDIR, DOS_CREATE = "AES_ROM_DOS_RMDIR", "AES_ROM_DOS_CREATE"
GSX_HARDCOPY, TRP13 = "AES_ROM_GSX_HARDCOPY", "AES_ROM_TRP13"
TRP13_ARGUMENT_WORDS = 6
# (the answer, the core's arguments, how many of them after the image no frame carries — the caller's return site)
SIGNATURES = {
    GSX_PLINE: (aes.WORD_ANSWER, (IMAGE, WORD, WORD, WORD, LONG), 0),
    APP_ALLOC: (aes.LONG_ANSWER, (IMAGE, WORD), 0),
    APP_FREE: (None, (IMAGE, LONG), 0),
    DOS_WRITE: (aes.LONG_ANSWER, (IMAGE, WORD, WORD, LONG), 0),
    DOS_GDIR: (aes.LONG_ANSWER, (IMAGE, WORD, LONG), 0),
    DOS_MKDIR: (aes.WORD_ANSWER, (IMAGE, LONG), 0),
    DOS_SETDT: (aes.LONG_ANSWER, (IMAGE, WORD, LONG), 0),
    DOS_LABEL: (aes.LONG_ANSWER, (IMAGE, WORD, LONG), 0),
    DOS_SPACE: (aes.LONG_ANSWER, (IMAGE, WORD, LONG, LONG), 0),
    DOS_RENAME: (aes.LONG_ANSWER, (IMAGE, LONG, LONG, LONG), 1),
    DOS_AVAIL: (aes.LONG_ANSWER, (IMAGE,), 0),
    DOS_RAWCIO: (aes.LONG_ANSWER, (IMAGE, LONG, WORD), 1),
    DOS_CHMOD: (aes.LONG_ANSWER, (IMAGE, LONG, LONG, WORD, WORD), 1),
    DOS_DELETE: (aes.LONG_ANSWER, (IMAGE, LONG, LONG), 1),
    DOS_RMDIR: (aes.LONG_ANSWER, (IMAGE, LONG, LONG), 1),
    DOS_CREATE: (aes.LONG_ANSWER, (IMAGE, LONG, LONG, WORD), 1),
    GSX_HARDCOPY: (None, (IMAGE,), 0),
    TRP13: (aes.LONG_ANSWER, (IMAGE, LONG, *[WORD] * (1 + TRP13_ARGUMENT_WORDS)), 1),
}
for _name, (_restype, _argtypes, _hosts) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes, host_arguments=_hosts)
UNIT_O = tuple(SIGNATURES)
PARKS_ITS_CALLER_S_RETURN = tuple(name for name, (_restype, _argtypes, hosts) in SIGNATURES.items() if hosts)

# ---- GEMDOS as these entries call it: each function's frame, and where each `trap #1` returns to -----------------------------
FWRITE, DGETPATH, DCREATE, FDATIME = addrs.GEMDOS_FWRITE_FN, addrs.GEMDOS_DGETPATH_FN, addrs.GEMDOS_DCREATE_FN, addrs.GEMDOS_FDATIME_FN
FSETDTA, FSFIRST, DFREE, FRENAME = addrs.GEMDOS_FSETDTA_FN, addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_DFREE_FN, addrs.GEMDOS_FRENAME_FN
MALLOC, CRAWIO, FATTRIB, FDELETE = addrs.GEMDOS_MALLOC_FN, addrs.GEMDOS_CRAWIO_FN, addrs.GEMDOS_FATTRIB_FN, addrs.GEMDOS_FDELETE_FN
DDELETE, FCREATE = addrs.GEMDOS_DDELETE_FN, addrs.GEMDOS_FCREATE_FN
# A frame whose first longword is an address of the routine's own stack (the module's docstring): `text` — what lies
# behind the pointer is a NUL-ended text — or `pointed` bytes of it; then `after` bytes of the frame past the pointer.
Pointed = namedtuple("Pointed", "text pointed after", defaults=(False, 0, 0))
POINTER_FIRST = {FSETDTA: Pointed(), FSFIRST: Pointed(text=True, after=WORD_BYTES), DFREE: Pointed(after=WORD_BYTES),
                 FDATIME: Pointed(pointed=LONG_BYTES, after=2 * WORD_BYTES)}
# ...and every other function's own frame bytes, which the ledger records.
FRAME_BYTES = {
    FWRITE: WORD_BYTES + 2 * LONG_BYTES, DGETPATH: LONG_BYTES + WORD_BYTES, DCREATE: LONG_BYTES,
    FRENAME: WORD_BYTES + 2 * LONG_BYTES, MALLOC: LONG_BYTES, CRAWIO: WORD_BYTES, FATTRIB: LONG_BYTES + 2 * WORD_BYTES,
    FDELETE: LONG_BYTES, DDELETE: LONG_BYTES, FCREATE: LONG_BYTES + WORD_BYTES, **{function: 0 for function in POINTER_FIRST}}
TRAP_1, TRAP_13 = 0x4e41, 0x4e4d


def _after_its_trap(lo, hi, trap=TRAP_1):
    """Where the one `trap` of the ROM's code `[lo, hi)` returns: the instruction behind it."""
    traps = [at for at in range(lo, hi, WORD_BYTES) if case.word_in(BASE_IMAGE, at) == trap]
    assert len(traps) == 1, f"the ROM's code [{lo:#x}, {hi:#x}) holds {len(traps)} such traps, not one"
    return traps[0] + WORD_BYTES


GEM_DOS_BACK = _after_its_trap(addrs.AES_ROM_GEM_DOS_TRAP, addrs.AES_ROM_RESTORE_TRAP2)        # `__DOS`'s own trap
LABEL_SETDTA_BACK = _after_its_trap(addrs.AES_ROM_DOS_LABEL, addrs.AES_DOS_LABEL_TRAP_RETURN)   # dos_label's Fsetdta
SPACE_DFREE_BACK = _after_its_trap(addrs.AES_ROM_DOS_SPACE, addrs.AES_ROM_DOS_RENAME)
AVAIL_MALLOC_BACK = _after_its_trap(addrs.AES_ROM_DOS_AVAIL, addrs.AES_ROM_DOS_CCONOUT)   # ...to the next entry
TRP13_BACK = _after_its_trap(addrs.AES_ROM_TRP13, addrs.AES_ROM_TRP14, TRAP_13)
# THE PLACES EACH ROUTINE'S TRAPS RETURN TO, in the order its run reaches them.
TRAP_RETURNS = {
    **{name: (GEM_DOS_BACK,) for name in (DOS_WRITE, DOS_GDIR, DOS_MKDIR, DOS_SETDT, DOS_RENAME, DOS_RAWCIO, DOS_CHMOD,
                                          DOS_DELETE, DOS_RMDIR, DOS_CREATE)},
    DOS_LABEL: (LABEL_SETDTA_BACK, GEM_DOS_BACK), DOS_SPACE: (SPACE_DFREE_BACK,), DOS_AVAIL: (AVAIL_MALLOC_BACK,),
    TRP13: (TRP13_BACK,), GSX_PLINE: (), APP_ALLOC: (), APP_FREE: (), GSX_HARDCOPY: ()}

# ---- this module's band ----------------------------------------------------------------------------------------------------
BAND_OFFSET, BAND_BYTES = 0x3200, 0x200         # the gap between aes_gemsuper.py's band (+$3000) and aes_pdpipe.py's (+$3400)
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/aes_deskleaves.py: texts, answers, a recording trap")
TEXT_AT, TEXT_BYTES = BAND_AT, 0x40             # a name or a path a case hands an entry
OTHER_TEXT_AT = TEXT_AT + TEXT_BYTES            # ...and a second (dos_rename's new name)
OUT_AT, OUT_BYTES = OTHER_TEXT_AT + TEXT_BYTES, 0x20       # what an entry answers through a pointer (a label, two sizes)
HANDLER_AT, HANDLER_ROOM = OUT_AT + OUT_BYTES, 0xE8


class Seen(gd.Recorder):
    """`aes_gemdosif`'s recording, scripted trap — and, for a frame that begins with an address of the routine's own
    stack (POINTER_FIRST), WHAT THE HOST TWIN WAS POINTED AT (`seen`, the module's docstring): `(function, the text
    or the bytes behind the pointer, the frame's bytes after it)` for each such call of the C, in order."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen = []

    def twin(self, function):
        answering = super().twin(function)
        if function not in POINTER_FIRST:
            return answering
        shape = POINTER_FIRST[function]

        def handler(buf, arguments, argument_bytes):
            frame = ctypes.string_at(ctypes.addressof(buf.contents) + arguments, LONG_BYTES + shape.after)
            self.seen.append(pointed_at(lambda at, length: ctypes.string_at(ctypes.addressof(buf.contents) + at, length),
                                        function, frame))
            return answering(buf, arguments, argument_bytes)
        return handler


TEXT_AT_MOST = 0x20


def pointed_at(read, function, frame):
    """A POINTER_FIRST call as `Seen.seen` keeps it, out of its `frame` (the pointer, then the words after it) and
    `read(at, length)`, the memory of the shore that made it."""
    shape, pointer = POINTER_FIRST[function], int.from_bytes(frame[:LONG_BYTES], "big") & BUS
    behind = read(pointer, TEXT_AT_MOST).split(b"\0")[0] if shape.text else read(pointer, shape.pointed)
    return function, behind, frame[LONG_BYTES:LONG_BYTES + shape.after]


GEMDOS = Seen(addrs.VECTOR_TRAP_GEMDOS, HANDLER_AT, HANDLER_ROOM, FRAME_BYTES, entries=4,
              parked=(aes.AES_DOS_RETURN, aes.AES_TRAP1_RETURN))
assert GEMDOS.end <= BAND_AT + BAND_BYTES
HANDLERS = {gemdos.rom_handler(function): GEMDOS.twin(function) for function in FRAME_BYTES}
assert len(HANDLERS) == len(FRAME_BYTES), "two of the entries' GEMDOS functions share a handler"
calls, call, sites_parked_at = GEMDOS.calls, GEMDOS.call, GEMDOS.parked_at
DOS_FIELDS, STALE_DOS = shell.DOS_FIELDS, shell.STALE_DOS


@contextlib.contextmanager
def scripted_hook():
    """The host twins bound as `aes.run_function`'s `hook`, what they were pointed at forgotten first."""
    GEMDOS.seen.clear()
    with gemdos.bound_handlers(HANDLERS) as hook:
        yield hook


def verdict(result):
    """`[AES_DOS_RETURN, AES_TRAP1_RETURN, AES_DOS_ERR, AES_DOS_AX]` as a run left them."""
    return [result.field("AES", name) for name in DOS_FIELDS]


def scripted(name, arguments, answers, pokes=None, **kwargs):
    """A LABELLED ARGUMENT CLASS: `name` over the leaf machine, the glue's four words stale, every `trap #1` answered
    by the script of `answers` — unpoisoned (`aes_gemdosif` says why)."""
    machine = aes.leaf_machine(onto=merge_pokes(STALE_DOS, GEMDOS.pokes(answers), pokes))
    return aes.run_function(name, arguments, machine, hook=scripted_hook, poison=False, **kwargs)


# ---- WHERE THE ROM'S FRAME OF A ROUTINE LIES ON THE HARNESS'S STACK, and its host slot --------------------------------------
# dos_label and dos_space open a `link`: entered directly, the saved A6 lies under the return address and the frame
# under that.
LINKED_FRAME_TOP = emu.STACK_TOP - LONG_BYTES
FRAME_SLOT = {DOS_LABEL: "AES_DOS_LABEL_FRAME", DOS_SPACE: "AES_DOS_SPACE_DFREE"}


def frame_laid(name, content):
    """`content` — a routine's whole `link` frame as GEMDOS would leave it — LAID BEFORE THE CALL on both shores: in
    the ROM's frame on the harness's stack (the routine entered directly) and in the C's host slot."""
    slot = FRAME_SLOT[name]
    assert len(content) == aes.HOST_SLOTS[f"HOST_SLOT_{slot}_BYTES"], f"{name}'s frame is not {len(content)} bytes"
    return {LINKED_FRAME_TOP - len(content): content, aes.HOST_SLOTS[f"HOST_SLOT_{slot}"]: content}


# ---- AN ARRIVAL -------------------------------------------------------------------------------------------------------------
Arrival = namedtuple("Arrival", "routine boot arguments return_site")
Arrival.__doc__ = """`routine` (an `addrs` name) where a chain of the ROM's machine calls it: the `Boot` stopped at its
first instruction, the `arguments` its caller pushed (read off the frame) and the `return_site` under them."""
At = namedtuple("At", "routine chain step nth", defaults=(1,))
At.__doc__ = """Where an arrival is taken: `routine`'s `nth` arrival (from 1) in the run of step `step` (from 0) of
the chain `chain` of `aes_desk.CHAINS`."""
ARRIVAL_INSNS = 2_000_000


def _stack_pointer(boot):
    registers = boot.registers
    if not registers["sr"] & aes_boot.SR_SUPERVISOR:
        raise aes_boot.Refused(f"the machine stands at {registers['pc']:#x} in user state: no routine of the desk is entered there")
    return registers["isp"]


def _before(chain_name, nth):
    """`(the machine before step `nth` of the chain, the named stop it stands at or None, the step)`."""
    chain = aes_desk.CHAINS[chain_name]
    machine = aes_desk.MACHINES[chain.after]() if chain.after in aes_desk.MACHINES else aes_desk.walked(chain.after).machine
    stands_at = None
    for step in chain.steps[:nth]:
        until = aes_desk.STOPS[step.until] if step.until else None
        machine = aes_boot.Machine(aes_desk.stepped(machine.boot, tuple(step.hand(machine)), until, stands_at, step.budget).boot)
        stands_at = until
    return machine, stands_at, chain.steps[nth]


def as_arrival(routine, boot):
    """`boot` — stopped at `routine`'s entry — as its `Arrival`: the frame read as the routine's declared one."""
    entry, sp = getattr(addrs, routine), _stack_pointer(boot)
    if boot.registers["pc"] & BUS != entry:
        raise aes_boot.Refused(f"the machine stands at {boot.registers['pc']:#x}, not at {routine}'s entry {entry:#x}")
    frame = struct.Struct(">" + "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(routine)))
    arguments = frame.unpack(boot.ram[sp + LONG_BYTES:sp + LONG_BYTES + frame.size])
    return Arrival(routine, boot, arguments, case.long_in(boot.ram, sp) & BUS)


@functools.cache
def arrival(at):
    """THE ARRIVAL `at` (an `At`): the chain's step run from the machine the steps before it left, stopped at the
    routine's entry — at its first arrival, then on from there to the next, `at.nth` times."""
    machine, stands_at, step = _before(at.chain, at.step)
    entry = getattr(addrs, at.routine)
    boot = aes_boot.continued.derive(machine.boot, tuple(step.hand(machine)), step.budget, entry, stands_at)
    for _again in range(at.nth - 1):
        boot = aes_boot.continued.derive(boot, (), ARRIVAL_INSNS, entry, entry)
    return as_arrival(at.routine, boot)


# ---- THE ROM'S OWN RUN IN PLACE ----------------------------------------------------------------------------------------------
Trap = namedtuple("Trap", "function frame answer boot")
Trap.__doc__ = """One trap of a routine's run in place, where it RETURNS: the `function` word it was taken over, the
`frame` bytes after it (TRAP_FRAME_SHOWN of them: the caller's stack runs on above the function's own), the OS's
`answer` (D0 there) and the `Boot` stopped there."""
InPlace = namedtuple("InPlace", "traps returned")
InPlace.__doc__ = """A routine's run in place from its `Arrival`: its `traps` in order and the `Boot` where it `returned`."""
TRAP_FRAME_SHOWN = 14


def in_place(arrived):
    """THE ROM'S OWN RUN of `arrived`'s routine, IN PLACE (the module's docstring): an `InPlace`. Held to have returned
    TO ITS CALLER — the stack pointer one return address above the one it was called at."""
    boot, stands_at, traps = arrived.boot, arrived.boot.registers["pc"] & BUS, []
    for back in TRAP_RETURNS[arrived.routine]:
        boot = aes_boot.continued.derive(boot, (), ARRIVAL_INSNS, back, stands_at)
        sp, stands_at = _stack_pointer(boot), back
        traps.append(Trap(case.word_in(boot.ram, sp), bytes(boot.ram[sp + WORD_BYTES:sp + WORD_BYTES + TRAP_FRAME_SHOWN]),
                          boot.registers["d0"], boot))
    boot = aes_boot.continued.derive(boot, (), ARRIVAL_INSNS, arrived.return_site, stands_at)
    called_at = _stack_pointer(arrived.boot)
    if _stack_pointer(boot) != called_at + LONG_BYTES:
        raise aes_boot.Refused(f"the run arrived at {arrived.return_site:#x} with the stack pointer at {_stack_pointer(boot):#x}: "
                               f"not {arrived.routine}'s return to its caller, called at {called_at:#x}")
    return InPlace(tuple(traps), boot)


@functools.cache
def ran_at(at):
    """...of the arrival `at` (an `At`), made once."""
    return in_place(arrival(at))


def megabyte(arrived, *layers):
    """The arrival's megabyte as a case's pokes, `layers` laid over it (each a labelled staging of its case)."""
    return merge_pokes({0: arrived.boot.ram}, *layers)


def held(arrived, *layers, answers=None, **kwargs):
    """THE DIFFERENTIAL AT AN ARRIVAL (the module's docstring): the routine's ROM body against its C core over the
    arrival's megabyte, with the arguments its caller pushed and — a host argument — the return site the ROM's run
    parks entered directly (the harness's sentinel). `answers`: what the scripted `trap #1` answers, in order (None:
    the routine traps nothing through GEMDOS, and nothing is staged)."""
    name = arrived.routine
    hosts = (emu.SENTINEL,) * vdi.ALCYON[name].host_arguments
    if answers is None:
        return aes.run_function(name, arrived.arguments, megabyte(arrived, *layers), host_arguments=hosts, **kwargs)
    return aes.run_function(name, arrived.arguments, megabyte(arrived, GEMDOS.pokes(answers), *layers), hook=scripted_hook,
                            poison=False, host_arguments=hosts, **kwargs)


def the_rom_s_pointed_at(trap, ram=None):
    """A POINTER_FIRST trap of a run in place as `Seen.seen` keeps the C's: what lay behind its pointer where the trap
    RETURNED — or in the megabyte `ram` (the arrival's, for what the routine's CALLER laid: the ROM's GEMDOS leaves
    Fdatime's two words byte-swapped where it found them)."""
    ram = trap.boot.ram if ram is None else ram
    return pointed_at(lambda at, length: bytes(ram[at:at + length]), trap.function, trap.frame)


# ---- THE BLOBS' OWN CORES OVER THE SAME MACHINES: the kit's second differential, UNBOUND AND UNPRICED ------------------------
# Tier 1 runs the host library; the cores' TARGET arms (a `trap` taken over a frame the C pushes, the door's seven
# words laid again, dos_setdt's own argument slot handed by address) run nowhere in it. So one case a routine is also
# run ON EACH BLOB — `RomBench.measure`, the relation every Tier 3 row is held by: the ROM's routine, then the blob's
# core, over one machine; D0 at the declared width, the megabyte, the streams. NOT A ROW: nothing is registered, no
# table line is made, and the figure it also answers is the scratch price probe's, not a priced claim.
#   * THE MACHINE is an arrival's megabyte LESS THE BLOB'S SPAN — refused by name where the arrival does not hold the
#     snapshot's bytes there (the blob lies in memory GEMDOS believes free: the standing limit) — or the leaf machine.
#   * A `trap #1` IS ANSWERED BY A TRAP THAT KEEPS ITS LAST CALL (`last_call_trap`): behind the GEMDOS vector, a
#     handler that stores the function word and the frame's own words into cells of this module's band — for a
#     POINTER_FIRST frame the words AFTER the pointer and the longword BEHIND it, never the pointer (an address of
#     each shore's own stack) — and answers the LAST of the case's answers to every call. The cells are compared
#     with the megabyte: a target arm that pushes its frame in another order differs there. (The scratch price probe
#     uses `bare_trap` instead: `move.l #answer,d0 / rte` alone.)
RETURNS_BYTES = {aes.LONG_ANSWER: LONG_BYTES, aes.WORD_ANSWER: WORD_BYTES, None: 0}
MOVE_L_IMMEDIATE_D0, RTE = b"\x20\x3c", b"\x4e\x73"
BARE_TRAP_CYCLES = 34 + 12 + 20         # the exception, `move.l #,d0`, `rte`: in both columns of a probe, a trap each
SNAPSHOT_RUN_BYTES = 16                 # two changed bytes nearer than this are one poke


def bare_trap(answer):
    """The GEMDOS vector at `move.l #answer,d0 / rte`, staged in this module's band."""
    return {addrs.VECTOR_TRAP_GEMDOS: struct.pack(">I", HANDLER_AT),
            HANDLER_AT: MOVE_L_IMMEDIATE_D0 + struct.pack(">I", answer & aes.LONG_MASK) + RTE}


# THE LAST GEMDOS CALL EACH ENTRY MAKES (dos_label's second; every other's one).
LAST_FUNCTION = {DOS_WRITE: FWRITE, DOS_GDIR: DGETPATH, DOS_MKDIR: DCREATE, DOS_SETDT: FDATIME, DOS_LABEL: FSFIRST,
                 DOS_SPACE: DFREE, DOS_RENAME: FRENAME, DOS_AVAIL: MALLOC, DOS_RAWCIO: CRAWIO, DOS_CHMOD: FATTRIB,
                 DOS_DELETE: FDELETE, DOS_RMDIR: DDELETE, DOS_CREATE: FCREATE}
CELLS_AT = HANDLER_AT + 0x80            # the last call's cells: the function word, the frame's words, the longword pointed at
CELL_WORDS = 5                          # Fwrite's and Frename's frames, the widest
POINTED_CELL_AT = CELLS_AT + WORD_BYTES * (1 + CELL_WORDS)
CELLS_BYTES = POINTED_CELL_AT + LONG_BYTES - CELLS_AT
assert CELLS_AT + CELLS_BYTES <= BAND_AT + BAND_BYTES
PUSH_A0, POP_A0 = b"\x2f\x08", b"\x20\x5f"
MOVE_W_STACK_TO_ABSOLUTE = b"\x33\xef"   # move.w  d16(sp),<xxx>.l
MOVEA_L_STACK_TO_A0 = b"\x20\x6f"        # movea.l d16(sp),a0
MOVE_L_A0_INDIRECT_TO_ABSOLUTE = b"\x23\xd0"     # move.l  (a0),<xxx>.l
FUNCTION_UNDER_THE_PUSH = LONG_BYTES + aes_boot.FRAME_BYTES    # the function word, past the pushed A0 and the exception's frame


def last_call_trap(function, answer):
    """A GEMDOS trap that KEEPS ITS LAST CALL (above) for an entry whose last call is `function`: A0 kept; the
    function word and the frame's own words (a POINTER_FIRST frame's AFTER its pointer) into the cells; for a frame
    that points at bytes or a text, the first longword behind the pointer; A0 back; D0 the answer; `rte`. The cells
    start STALE."""
    shape = POINTER_FIRST.get(function)
    skipped, words = (LONG_BYTES, shape.after // WORD_BYTES) if shape else (0, FRAME_BYTES[function] // WORD_BYTES)
    code = PUSH_A0 + MOVE_W_STACK_TO_ABSOLUTE + struct.pack(">HI", FUNCTION_UNDER_THE_PUSH, CELLS_AT)
    for nth in range(words):
        code += MOVE_W_STACK_TO_ABSOLUTE + struct.pack(">HI", FUNCTION_UNDER_THE_PUSH + WORD_BYTES + skipped + nth * WORD_BYTES,
                                                       CELLS_AT + (1 + nth) * WORD_BYTES)
    if shape and (shape.text or shape.pointed):
        code += (MOVEA_L_STACK_TO_A0 + struct.pack(">H", FUNCTION_UNDER_THE_PUSH + WORD_BYTES)
                 + MOVE_L_A0_INDIRECT_TO_ABSOLUTE + struct.pack(">I", POINTED_CELL_AT))
    code += POP_A0 + MOVE_L_IMMEDIATE_D0 + struct.pack(">I", answer & aes.LONG_MASK) + RTE
    assert HANDLER_AT + len(code) <= CELLS_AT
    return {addrs.VECTOR_TRAP_GEMDOS: struct.pack(">I", HANDLER_AT), HANDLER_AT: code,
            CELLS_AT: vdi.pack_words(*[aes.STALE_WORD] * (CELLS_BYTES // WORD_BYTES))}


def last_call_kept(image, function):
    """`(the function word, the frame's words kept, the longword behind its pointer or None)` out of the cells in `image`."""
    shape = POINTER_FIRST.get(function)
    words = (shape.after if shape else FRAME_BYTES[function]) // WORD_BYTES
    kept = struct.unpack(f">{1 + words}H", image[CELLS_AT:CELLS_AT + WORD_BYTES * (1 + words)])
    behind = case.long_in(image, POINTED_CELL_AT) if shape and (shape.text or shape.pointed) else None
    return kept[0], kept[1:], behind


def less_the_blob(ram, bench):
    """An arrival's megabyte as pokes over the snapshot, THE BLOB'S SPAN LEFT OUT — refused by name where the
    megabyte is not the snapshot's there."""
    lo, hi = bench.base, bench.end
    if bytes(ram[lo:hi]) != bytes(BASE_IMAGE[lo:hi]):
        raise aes_boot.Refused(f"the arrival's megabyte is not the snapshot's inside the blob's span [{lo:#x}, {hi:#x}): "
                               f"a case over it would run the two shores over different machines")
    pokes, at = {}, 0
    while at < len(ram):
        if lo <= at < hi:
            at = hi
        elif ram[at] == BASE_IMAGE[at]:
            at += 1
        else:
            end = at + 1
            while end < len(ram) and not lo <= end < hi and ram[end:end + SNAPSHOT_RUN_BYTES] != BASE_IMAGE[end:end + SNAPSHOT_RUN_BYTES]:
                end += 1
            pokes[at], at = bytes(ram[at:end]), end
    return pokes


def blob_pokes(bench, name, arguments, ram=None, layers=(), answers=None, settles_the_mask=False, trap=last_call_trap):
    """The machine of one case on the blob `bench` (above), `name`'s frame of `arguments` staged: `ram` (an arrival's
    megabyte; None: the leaf machine) less the blob's span, `layers` laid. `answers`: GEMDOS's — the trap (`trap`:
    `last_call_trap`, or the probe's `bare_trap`) answers the last of them. `settles_the_mask`: an Alcyon routine's
    Line-F mask word staged at the value its own return leaves (a C core stores none: the one-sided kind Tier 3 names)."""
    machine = aes.leaf_machine() if ram is None else less_the_blob(ram, bench)
    return _staged_over(machine, name, arguments, layers, answers, settles_the_mask, trap)


def _staged_over(machine, name, arguments, layers, answers, settles_the_mask, trap):
    """`blob_pokes`' and `row_pokes`' common part: over `machine`, the trap, the layers, the frame and the mask word."""
    staged_trap = None
    if answers:
        staged_trap = bare_trap(answers[-1]) if trap is bare_trap else trap(LAST_FUNCTION[name], answers[-1])
    machine = merge_pokes(machine, staged_trap, *layers)
    signed = vdi.as_signed(name, arguments)
    pokes = aes.staged(name, signed, machine)
    if settles_the_mask:
        pokes = merge_pokes(pokes, {aes.AES_LINEF_MASK_WORD: struct.pack(">H", aes.settled_mask_word(name, signed, machine))})
    return pokes


# ---- band 6 slice F1: A ROW'S MACHINE — one for both blobs -------------------------------------------------------------------
# A FLIPPED ROUTINE'S ROW (the unit's rows, `test_desk_leaves.py`) is ITS BLOB CASE REGISTERED: the same frame and mask word
# over the same arrival, priced by Tier 3's own relation on whichever blob the table prices it on — GEMDOS answered by
# THE UNIT'S OWN RECORDING TRAP (`GEMDOS`, the one its Tier 1 cases take), scripted with the ROM's run in place's
# answers, in place of the blob cases' trap that keeps its last call: the price of a glue entry turns on the trap it is
# taken over (the bare-trap question, the user's), and this is the convention the unit is held at Tier 1 by. Its
# machine is THE ARRIVAL'S MEGABYTE WHOLE BUT THE HARNESS'S WINDOW (`aes_desk.arrival_s_machine`, units O's and D's).
arrival_s_machine = aes_desk.arrival_s_machine


# What the recording trap answers a trap of the routine the row's answers do not name (dos_label's Fsetdta, when a case
# gives its Fsfirst's alone): read by no instruction of the glue (Fsetdta's answer is dropped).
UNREAD_ANSWER = 0xFD0001


def row_pokes(name, arguments, ram=None, layers=(), answers=None, settles_the_mask=False):
    """The pokes of ONE ROW of `name` (above): over `arrival_s_machine(ram)` (None: the leaf machine), every `trap #1`
    answered by the recording trap, the LAST of its traps by the last of `answers`; `layers`, the frame, the mask word."""
    machine = aes.leaf_machine() if ram is None else arrival_s_machine(ram)
    if answers:
        traps = len(TRAP_RETURNS[name])
        layers = (GEMDOS.pokes([UNREAD_ANSWER] * (traps - len(answers)) + list(answers)), *layers)
    return _staged_over(machine, name, arguments, layers, None, settles_the_mask, last_call_trap)


def on_a_blob(bench, name, arguments, dropped=(), **machine_s):
    """ONE CASE ON THE BLOB `bench` (above): `name`'s ROM routine, then the blob's core, over `blob_pokes` — a
    `Measurement`, the kit's second differential made on the way."""
    signed = vdi.as_signed(name, arguments)
    hosts = (emu.SENTINEL,) * vdi.ALCYON[name].host_arguments
    return bench.measure(getattr(addrs, name), routines.core_symbol(name), args=(0, *hosts, *signed),
                         pokes=blob_pokes(bench, name, arguments, **machine_s),
                         returns=RETURNS_BYTES[vdi.ALCYON[name].restype], dropped=dropped)


def the_rom_s_last_call(bench, name, arguments, dropped=(), **machine_s):
    """WHAT THE ROM'S ROUTINE TRAPPED WITH LAST over that case's machine (`last_call_kept`, off the ROM's own run): what
    the blob's core was held equal to, said."""
    final, _writes, _regs = emu.run(vdi.make_image(blob_pokes(bench, name, arguments, **machine_s)), getattr(addrs, name), {})
    return last_call_kept(final, LAST_FUNCTION[name])


# THE BIOS'S REGISTER-SAVE FRAME a case drops (trp13's door cases; the show engine's, whose Bconout is the BIOS's own
# on both shores — band 6 wave 4).
SAVE_FRAME_BYTES = addrs.TRAP_SAVE_FRAME_BYTES


def savptr_frame(ram):
    """`(lo, hi, why)`: the BIOS's register-save frame under the machine's `savptr` — the ROM's trap stores the
    registers and the return of ITS run there, a C core none."""
    savptr = case.long_in(ram, addrs.SYSVAR_SAVPTR) & BUS
    return ((savptr - SAVE_FRAME_BYTES, savptr, "the BIOS's register-save frame under savptr: the ROM's trap #13 stores its own "
             "registers and return there; the host's BIOS core is called, and saves none"),)
