"""The GEMDOS PROCESS group's case shape: a whole second process, staged out of the ROM's own pool.

Three batteries share this — `test_gemdos_handles.py`, `test_gemdos_process.py` and
`test_gemdos_process_pexec.py`. What it owns is the four things all of them need:

  * the OPEN FILE DESCRIPTOR table at `$8092`, which the snapshot leaves entirely zero, so every
    descriptor a case reads is one the case put there;
  * a CHILD PROCESS — a basepage inside a TPA cut out of the snapshot's own free block, with the
    memory descriptor's `m_own` naming it, exactly as `Pexec` would have left it;
  * the TERMINATE VECTOR's staged routine, because `Pterm` calls whatever `$408` names before it
    does anything else;
  * and `run(..., stop_pc=)`, which is how a routine that DOES NOT RETURN is run at all.

WHY A ROUTINE HERE NEEDS A CHECKPOINT. `Pterm`, `Pterm0`, `Ptermres` and `Pexec`'s two "go" modes
all end in `jsr $fc4fe8` — the trap entry's epilogue, which unwinds the PARENT's process frame and
`rte`s. There is no `rts` for the oracle to stop at and no epilogue for the host candidate to call,
so the case stops the ORIGINAL at that `jsr` (`harness.differential(..., stop_pc=)`) and the host
build of the core returns the exit code it has just planted. The target build really does `jsr` it
(`src/gemdos/process.c`), which is why these rows are VERIFIED but UNPRICED: Tier 3 runs both
columns to an `rts` and there is none.

WHAT A STAGED PROCESS MAY BE is `test/gemdos_memory.py`'s rule, inherited whole: every state a case
starts from is one the ROM's own code could have produced. The child's TPA is a re-cut of the
snapshot's ONE free block, its descriptor comes from the record arena, and the two lists still tile
the machine. The one thing this module adds on top is the OWNER: `gemdos_memory.stage` charges every
allocated span to the snapshot's own `p_run`, and a child's blocks are charged to the child — which
is what makes "release the memory this process owns" a claim with two answers rather than one.
"""
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs

import case
import gemdos
import gemdos_memory
import isr
import staging
from opcodes import RTS

# ---- this group's own structure constants, out of the C header that defines them ----------------
# `include/gemdos/process.h` holds the OPEN FILE DESCRIPTOR's layout, parsed by the same
# `tools/addrs.py` that binds `addrs.h` — `test/gemdos_memory.py`'s arrangement, for its reason: a
# case and the core it proves cannot disagree about a field offset they read from one file. The
# ROUTINE addresses stay in `addrs.h`, where the registries key on them.
GEMDOS_PROCESS_HEADER = Path(__file__).resolve().parents[1] / "include" / "gemdos" / "process.h"
CONSTANTS = addrs.parse(GEMDOS_PROCESS_HEADER)
sys.modules[__name__].__dict__.update(CONSTANTS)

# ---- the band this module owns, between `trap.py`'s and `test/isr.py`'s -------------------------
PROCESS_BAND_BYTES = 0x100
PROCESS_BAND = staging.band(0xC00, PROCESS_BAND_BYTES, "test/gemdos_process.py")

TERMINATE_ROUTINE_AT = PROCESS_BAND         # what a case puts in the terminate vector
TERMINATE_WITNESS_AT = PROCESS_BAND + 0x40  # ...and the byte it leaves to say it ran
SLICE_TRAMPOLINE_AT = PROCESS_BAND + 0x80   # `Pexec`'s slice entry (see `slice_trampoline`)
SLICE_TRAMPOLINE_BYTES = 0x10
assert SLICE_TRAMPOLINE_AT + SLICE_TRAMPOLINE_BYTES <= PROCESS_BAND + PROCESS_BAND_BYTES

WITNESS = 0x5E                              # a byte nothing in this machine's low RAM holds

# ---- the open-file descriptors ------------------------------------------------------------------

Descriptor = namedtuple("Descriptor", "at named owner references")


VECTOR_BYTES = 4                            # `lsl.w #2` on the number Setexc takes
TERMINATE_VECTOR_AT = GEMDOS_TERM_VECTOR * VECTOR_BYTES


def descriptor_at(handle):
    """Where the descriptor for `handle` is — the ROM's own signed arithmetic, so a handle below 6
    addresses BEFORE the table (`src/gemdos/handles.c`, which reproduces it)."""
    return addrs.GEMDOS_HANDLE_TABLE \
        + (handle - addrs.GEMDOS_FIRST_FILE_HANDLE) * addrs.GEMDOS_HANDLE_STRIDE


def descriptor(image, handle):
    """The three fields of `handle`'s descriptor, as the image holds them."""
    at = descriptor_at(handle)
    return Descriptor(at, case.long_in(image, at + HANDLE_VALUE),
                      case.long_in(image, at + HANDLE_OWNER),
                      case.word_in(image, at + HANDLE_REFCOUNT))


def descriptor_poke(handle, named, owner, references=1):
    """One staged descriptor. `named` is what the handle NAMES — negative for a character device,
    positive for whatever the file system would have put there."""
    return {descriptor_at(handle): struct.pack(">IIH", named & 0xFFFF_FFFF, owner, references)}


# THE WHOLE TABLE IS ZERO IN THE SNAPSHOT, which is what makes a staged descriptor a claim: nothing
# else in it can answer. Asserted rather than assumed, because a later capture with a file open
# would silently give these cases a second descriptor to find.
assert not any(BASE_IMAGE[addrs.GEMDOS_HANDLE_TABLE:
                          addrs.GEMDOS_HANDLE_TABLE
                          + GEMDOS_HANDLE_COUNT * addrs.GEMDOS_HANDLE_STRIDE]), (
    "the captured machine has an open file — these batteries stage over a table they believe empty")


def full_table_poke(owner):
    """Every one of the 75 descriptors owned, which is the only state `Fdup` answers ENHNDL in."""
    return {addrs.GEMDOS_HANDLE_TABLE: struct.pack(">IIH", 0, owner, 1) * GEMDOS_HANDLE_COUNT}


# ---- the running process, and a second one beside it ---------------------------------------------

# The snapshot's own basepage is the PARENT in every case here: it is a real basepage the desktop is
# running out of, so a child that names it as `p_parent` is naming something that exists.
PARENT = gemdos.BASEPAGE

# What a fresh process's six standard handles hold — CON:, CON:, AUX:, PRN: and two unused slots,
# which is what `GEMDOS_CONSOLE_INIT` writes and what the captured machine really has.
DEVICE_HANDLES = (-1, -1, -2, -3, 0, 0)

# How big a child's TPA is cut. Big enough for the basepage, the 256 bytes the clear runs past it and
# a stack; small enough that the rest of the free block still holds the staging band.
CHILD_TPA_BYTES = 0x2000

Child = namedtuple("Child", "pokes basepage tpa staged")


def stage_child(handles=DEVICE_HANDLES, curdir=(2,), tpa_bytes=CHILD_TPA_BYTES, blocks=1,
                descriptors=(), pokes=None):
    """A second process, running, with `blocks` memory blocks of its own.

    The snapshot's one free block is re-cut into `blocks` USED spans and whatever is left, the first
    span's start IS the basepage, and every USED span is charged to it. `handles` and `curdir` fill
    `p_uft` and `p_curdir`; `descriptors` are `descriptor_poke`s laid on top.

    Returns the pokes, the basepage, the TPA's length and `gemdos_memory`'s own `Staged` — which is
    what a case reads to name the descriptors it expects to move.
    """
    staged = gemdos_memory.stage(gemdos_memory.fill(*((gemdos_memory.USED, tpa_bytes),) * blocks))
    basepage = staged.used[0].start
    basepage_image = bytearray(addrs.BASEPAGE_COMMAND_TAIL)

    struct.pack_into(">I", basepage_image, addrs.BASEPAGE_LOWTPA, basepage)
    struct.pack_into(">I", basepage_image, addrs.BASEPAGE_HITPA, basepage + tpa_bytes)
    struct.pack_into(">I", basepage_image, addrs.BASEPAGE_PARENT, PARENT)
    for index, handle in enumerate(handles):
        basepage_image[addrs.BASEPAGE_HANDLES + index] = handle & 0xFF
    for index, node in enumerate(curdir):
        basepage_image[addrs.BASEPAGE_CURDIR + index] = node & 0xFF

    staged_pokes = dict(staged.pokes)
    for span in staged.used:
        staged_pokes[span.md + addrs.MD_OWNER] = struct.pack(">I", basepage)
    staged_pokes[basepage] = bytes(basepage_image)
    staged_pokes[addrs.GEMDOS_P_RUN] = struct.pack(">I", basepage)
    for one in descriptors:
        staged_pokes.update(one)
    staged_pokes.update(pokes or {})
    return Child(staged_pokes, basepage, tpa_bytes, staged)


def owned_blocks(image, owner):
    """Every descriptor on the ALLOCATED list charged to `owner`, in list order."""
    return [block for block in gemdos_memory.allocated_list(image) if block.owner == owner]


def directory_refcount(image, node):
    """One byte of the shared directory table's reference counts."""
    return image[addrs.GEMDOS_CURDIR_REFCOUNTS + node]


# ---- the terminate vector -------------------------------------------------------------------------

def terminate_routine(witness=WITNESS):
    """A routine for `$408`: leave a byte and `rts`. `isr.py`'s pair shape — the 68000 stub for the
    ORACLE and the host effect for the CANDIDATE — so that both shores really transfer control."""
    def effect(buf, _argument):
        buf[TERMINATE_WITNESS_AT] = witness
    return {TERMINATE_ROUTINE_AT: (isr.store_byte(witness, TERMINATE_WITNESS_AT) + RTS, effect)}


def rom_terminate_routine():
    """...and the one the captured machine really has, which is the bare `rts` at `$fc0670`. Staged
    with NO code (it is already in the ROM) and a host effect that does nothing, which is what it
    does: this is the arm every case that is not about the vector runs."""
    return {isr.long_in_snapshot(TERMINATE_VECTOR_AT): (b"", lambda _buf, _argument: None)}


def terminate_vector_poke(routine=TERMINATE_ROUTINE_AT):
    return {TERMINATE_VECTOR_AT: struct.pack(">I", routine)}


# ---- the Mega ST battery clock -----------------------------------------------------------------------
#
# `Pterm` probes for one on its way out ($fc5092 -> $fc4c0c), so EVERY case here has to declare what
# the chip's registers answer — and the declaration is the MACHINE THE CASE IS ABOUT.
#
# WHY EVERY CASE HERE IS A MEGA ST, which is this group's one real limit and is stated where the
# declaration is made rather than only in the ledger. The probe WRITES two registers and READS THEM
# BACK, and the kit's declared I/O map has exactly two forms for such an address
# (`tools/recreate_kit/include/os.h`, Phase 15): a CONSTANT, which says the byte is what the machine
# held on ENTRY — and a store to one makes it stale, which `harness._vet_io_reads_are_declared`
# refuses by design — and WRITE-THROUGH, which says the register LATCHES a store and reads it back.
# Write-through is exactly what an RP5C15 does and exactly what an ABSENT chip does not, so the
# declarable machine is the one with the clock fitted. A plain ST takes the `bcs` at $fc5096 and
# `gemdos_resync_clock` is a no-op there; that arm is driven by an ORACLE claim
# (`test_gemdos_process.py`) and recorded unpinned, and the kit door that would close it is a THIRD
# form — "a register a store does not reach".
# The chip's GEOMETRY is `include/gemdos/process.h`'s and is already bound above (`CONSTANTS`) —
# `RTC_BASE`, `RTC_RESET`, `RTC_PROBE_HIGH`/`_LOW`, `RTC_DIGITS`, `RTC_FIRST_DIGIT` and
# `RTC_REGISTER_STEP` — because the core reads the same registers and a second spelling here is how
# a case and the core it proves come to disagree about which address is which. The header's three
# register names are OFFSETS from `RTC_BASE`; what this module needs is their absolute addresses.
PROBE_HIGH_AT = RTC_BASE + RTC_PROBE_HIGH
PROBE_LOW_AT = RTC_BASE + RTC_PROBE_LOW
RESET_AT = RTC_BASE + RTC_RESET

# The registers the probe STORES to and then the clock read READS BACK: the two halves of its
# pattern, and the reset register its success arm writes. They have to be declared WRITE-THROUGH
# (the constant form goes stale, see above) — and a write-through declaration is what makes them
# read back the PROBE'S OWN BYTES rather than the digits a case asked for.
#
# THE REAL CHIP DOES NOT BEHAVE THAT WAY, and saying so is the point: the RP5C15's registers are
# BANKED, the probe writes its pattern with the mode register set to 9 and puts it back to 8 before
# the digits are read, so on a Mega ST the pattern lands in another bank and the clock is intact.
# The kit's map is one value per address with no bank selector, so under it three of the thirteen
# digits — the minutes' two and the seconds' units — are whatever the probe left. `served()` below
# is what the case computes its expectation from, so the claim a test makes is the true one ("these
# thirteen digits become these two words") rather than a false one about a real clock.
WRITE_THROUGH_REGISTERS = (PROBE_HIGH_AT, PROBE_LOW_AT, RESET_AT)
# ...and the bytes the probe leaves in them, which is what those three then read back — the halves
# of the header's own `movep.w` immediate, split here rather than written out again.
PROBE_PATTERN_HIGH = RTC_PROBE_PATTERN >> 8
PROBE_PATTERN_LOW = RTC_PROBE_PATTERN & 0xFF


def digit_index_of(register):
    """Which buffer slot a register's digit lands in: `read_clock_digits` walks registers 1, 3 ... 25
    and files them at buffer[12] down to buffer[0]."""
    return RTC_DIGITS - 1 - (register - RTC_BASE - RTC_FIRST_DIGIT) // RTC_REGISTER_STEP


def served(digits):
    """The thirteen digits the MODEL really serves for a case that asked for `digits` — `digits`
    with the three write-through registers' own bytes in place of what the case wanted there."""
    out = list(digits)
    for register, byte in ((PROBE_HIGH_AT, PROBE_PATTERN_HIGH), (PROBE_LOW_AT, PROBE_PATTERN_LOW),
                           (RESET_AT, RTC_RESET_VALUE)):
        out[digit_index_of(register)] = byte
    return tuple(out)


# Two clock readings, as the thirteen digits registers 25..1 hold — which is buffer[0..12], running
# year-tens first. Three of each are overwritten by the probe; `served()` says which.
A_TIME = (8, 7, 0, 4, 2, 2, 0, 1, 2, 0, 0, 0, 0)         # 1987-04-22 12:00:00
ANOTHER_TIME = (9, 9, 1, 1, 1, 9, 3, 2, 3, 5, 9, 5, 9)   # 2099-11-19 23:xx:5x


def battery_clock(digits=A_TIME):
    """`io_seed` for a Mega ST whose thirteen digit registers hold `digits`."""
    from harness import emu

    seed = {}
    for index in range(RTC_DIGITS):
        at = RTC_BASE + RTC_FIRST_DIGIT + index * RTC_REGISTER_STEP
        byte = digits[digit_index_of(at)]
        seed[at] = emu.write_through(byte) if at in WRITE_THROUGH_REGISTERS else byte
    return seed


A_BATTERY_CLOCK = battery_clock()


# ---- entering a routine that does not return ---------------------------------------------------------

# Where the ORIGINAL is stopped: the `jsr` into the trap entry's epilogue, in each of the two
# routines that has one. Everything before it has happened; nothing after it is a routine at all.
PTERM_EPILOGUE_CALL = 0xFC8076
PEXEC_EPILOGUE_CALL = 0xFC85C8


def run(entry, glue, pokes, *, stop_pc=0, routines=None, io_seed=None, width=case.FULL_D0):
    """One differential over this group's machine: the staged routines armed, the vector calls
    recorded, and no poisoning.

    `stop_pc` is what makes it a CHECKPOINT — the ORIGINAL stopped at a PC instead of at an `rts`,
    which the four terminators need because they have no `rts`. 0 is the kit's own "run to the
    `rts`" (`emu.run`), and is every other routine here. It was a second function with its
    own defaults until this wave, and the defaults were the whole difference: the checkpoint half
    silently declared a battery clock where this one declared nothing, so which machine a case ran
    on depended on which helper it happened to call. Both are ARGUMENTS now, named at the call site.

    NOTHING HERE POISONS, for `gemdos_memory.py`'s reason and one of its own: these routines walk
    the allocated list, and an inverted link is followed into the I/O page on the oracle's side and
    refused. What stands in for it is that every case names the fields it expects to move and reads
    them out of the ORACLE's own write ledger.
    """
    with isr.staged_routines(routines or {}):
        return case.run(entry, {**gemdos_memory.ENTRY_REGS, "_pokes": pokes},
                        isr.recording(glue), width=width, poison=False, stop_pc=stop_pc,
                        io_seed=io_seed)


# ---- entering `Pexec` past the record it arms ---------------------------------------------------------
# `$fc8242` is inside the frame `Pexec`'s own prologue opened, so nothing can enter it directly —
# `test/gemdos.py`'s dispatcher slice, one routine along, and built by the same builder. Two
# instructions here rather than three: the mode is an ARGUMENT and not a local, so the trampoline
# has only the frame to open.
#
#     link    a6,#-48                 `Pexec`'s own frame, from the harness's stack top
#     jmp     $fc8242
PEXEC_FRAME_BYTES = 48

_STUB, SLICE_ENTRY_COST = gemdos.slice_trampoline(addrs.GEMDOS_PEXEC_CREATE, PEXEC_FRAME_BYTES)
assert len(_STUB) <= SLICE_TRAMPOLINE_BYTES, "the slice trampoline outgrew its band"


def slice_trampoline():
    return {SLICE_TRAMPOLINE_AT: _STUB}


# `bench/tier3.py` looks a row up by the ROM routine its ENTRY belongs to, and a slice case's entry
# is a stub in this band. The map it reads is `test/gemdos.py`'s, so this group's one slice is
# ADDED to it here rather than kept beside it — the arrangement `gemdos.register` already has for
# the case list, and for the same reason: one registry, so a row cannot be in a map nothing reads.
gemdos.ROUTINE_OF_TRAMPOLINE[SLICE_TRAMPOLINE_AT] = addrs.GEMDOS_PEXEC_CREATE

# ...and what that trampoline COSTS sits in the ORIGINAL's column alone — `link` and `jmp <long>.l`,
# which `test_gemdos_process_pexec.py::test_the_slice_trampoline_costs_what_its_rows_are_net_of`
# measures. It is NOT `gemdos.SLICE_ENTRY_COST`, and that is the one thing `bench/tier3.py` has to
# be told: the dispatcher's trampoline is THREE instructions (it stands a local in the frame as
# well) and this one is two, so one shared constant cannot net both. `SLICE_ENTRY_COST` above comes
# back from the builder with the stub, so the two can no longer describe different shapes.


# Where a `Pexec` case stages the two blocks it hands over. `test/gemdos.py`'s BUFFER half is
# exactly this — "a buffer a GEMDOS call points at" — and both of these are read and never written,
# so they need no band of their own.
ENVIRONMENT_AT = gemdos.BUFFER_AT
COMMAND_TAIL_AT = gemdos.BUFFER_AT + 0x40
assert COMMAND_TAIL_AT + PEXEC_COMMAND_TAIL_MAX + 1 <= gemdos.BUFFER_AT + gemdos.BUFFER_BYTES


def pexec_args(mode, name=0, tail=0, env=0):
    """`Pexec`'s own frame: the mode WORD and then three longwords, which is the widest argument
    class the dispatcher has (`GEMDOS_ARGUMENT_BYTES_3` = 14 bytes)."""
    return case.args(">HIII", mode & 0xFFFF, name, tail, env)


# ---- the rows the registry cannot take yet -----------------------------------------------------------
#
# `gemdos.register` builds a `test_boot_snapshot.VERIFIED_CASES` row of SEVEN OR EIGHT fields — the
# eighth is `stop_pc`, 0 for a routine that reaches its own `rts` — and that file's sweeps run every
# `stop_pc`-less row to that `rts`. The three terminators have none, which is the whole point of
# them, so a row for one would overrun the oracle's instruction cap and the sweep would fail with
# `did not reach rts`: a fact about the REGISTRY rather than about the case.
#
# So they are collected here instead, in the same shape with the CHECKPOINT the case stops at, and
# `test_gemdos_process.py::test_every_checkpoint_case_is_one_this_battery_drives` is what keeps the
# list from describing runs nobody makes. `bench/tier3.py` takes a `stop_pc` row as UNPRICED — Tier
# 3 runs both columns to an `rts` there is still none of.
CHECKPOINT_CASES = []


def register_checkpoint(name, entry, regs, pokes, stop_pc, io_seed=None):
    row = (name, entry, dict(regs), dict(pokes), None, io_seed, (), stop_pc)
    CHECKPOINT_CASES.append(row)
    return row


# ---- what the orchestrator needs from this group ------------------------------------------------------
# Every field these batteries READ or POKE, for `test_boot_snapshot.py`'s `CASE_FIELDS`. The
# basepage's own spans and `p_run` are `test/gemdos.py`'s and the pool's are `test/gemdos_memory.py`'s;
# what is here is what neither declares.
CASE_SPANS = (
    (addrs.GEMDOS_HANDLE_TABLE, GEMDOS_HANDLE_COUNT * addrs.GEMDOS_HANDLE_STRIDE,
     "the open file descriptors Fdup cuts, Fforce counts and a process's release closes"),
    (addrs.GEMDOS_CURDIR_REFCOUNTS, addrs.BASEPAGE_CURDIR_ENTRIES,
     "the directory reference counts Pexec bumps and a process's release drops"),
    # One byte BELOW the table as well: a negative `p_curdir` entry decrements before it, which is
    # the ROM's own unbounded signed index (`src/gemdos/process.c`).
    (addrs.GEMDOS_CURDIR_REFCOUNTS - 1, 1, "...and the byte a NEGATIVE directory entry reaches"),
    (TERMINATE_VECTOR_AT, 4, "etv_term, the vector Pterm reads through Setexc and then calls"),
)
