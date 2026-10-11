r"""THE ACCESSORY LOADER AT ITS ARRIVALS (`src/aes/loader.c`: sndcli, ldaccs, free_accs, cre_aproc) — how a routine
that LOADS A PROGRAM is held to the ROM (`test_aes_loader.py`).

WHY NOT THE KIT'S DIFFERENTIAL. Every other AES battery runs the ROM's routine on the harness's own stack band, in
the free window of the machine — and sndcli's `Pexec(3)` hands the program THE LARGEST FREE BLOCK AND CLEARS IT: that
window, the run's stack with it (`aes_boot`, "WHY NOT A RAM DISK"). So the ROM's shore here is the ROM's own boot,
IN PLACE:

  * AN ARRIVAL (`Arrival`) is the ROM's boot stopped where ITS OWN CALLER calls the routine (`aes_boot.booted(until=)`,
    and from there `run_on` to a later arrival): every byte of RAM, the whole register file, the disk as the boot left
    it, the frame the caller pushed. No byte is poked.
  * THE ROM'S RUN (`returned`) is that boot CONTINUED from the arrival to the routine's own return, on the machine's
    own stack, through `aes_boot`'s device model (the floppy at the driver's entries) — and WATCHED AT `trap #1`: each
    GEMDOS call of the AES's glue is kept as a `Call` — its function, its frame's own bytes, D0 where the trap returns
    and EVERY BYTE OF RAM GEMDOS CHANGED (the program it loaded, its own records, the sectors the model laid) —
    with what the routine itself changed before it.
  * THE C'S RUN (`the_c_s`) is the host core over the arrival's megabyte with GEMDOS REPLAYED FROM THAT RUN: each
    `trap #1` of the C must be the ROM's next call (the function, the frame); the megabyte the C has made BY THEN must
    be the ROM's at that call; and it is answered with the ROM's D0, the bytes GEMDOS changed laid over the image.
    Where it returns, the answer and the megabyte are the ROM's. The run is made IN A FORK FIRST: a refusal cannot
    be raised through the C that made the call, and a C that parted from the ROM may store anywhere.
  * AN ARGUMENT CLASS, where no boot makes the machine a case needs, is an arrival WITH BYTES LAID OVER IT (`staged`),
    labelled where it is made — and the ROM's own run is then made from THAT machine, in place, as from any other.

WHAT THE TWO MEGABYTES DIFFER IN BY NATURE — three classes, each located from the machine's own pointers or the
header's table, each named per case and REFUSED where the two never differ in it (`Classes`):
  * THE ROM'S OWN FRAMES: the running process's stack below the stack pointer the routine was called at (its `link`
    frames, its Line-F calls' frames, GEMDOS's trap frames — dead where it returns);
  * THE HOST'S FRAMES: the host slots the routine's C keeps its frames in off target (`include/host_slot.h`), named
    by role;
  * THE LINE-F MASK WORD, which every masked Alcyon return rewrites and no C writes.

A STORE THE C SKIPPED THAT CHANGES NOTHING (the count cleared where it is already 0) is invisible to an end compare.
So each case is held TWICE (`held_twice`): as the boot made it, and over the same arrival with EVERY BYTE THE ROM'S
ROUTINE STORED WITHOUT CHANGING IT INVERTED (`silently_stored`, read off the first run's write ledger outside its
GEMDOS calls; the kit's attribution pass, made by hand) — the ROM's own run made again from that machine, the C
replayed from it. LEFT AS THEY ARE: what no C stores by nature (the ROM's frames, the Line-F mask word, the words
the ROM parks its status register in), and a word that STEERS the run — a count the routine indexes by before it
stores it back — by a reason (`aes.steers`), each HELD NEEDED on the ROM's own shore (`steers_the_rom`).

THIS MODULE REACHES `aes_boot`'s RUN (`_Run`, the CPU's accessors): the one run that serves the device model. A
public door there is owed (the hand-back says so).
"""
import ctypes
import functools
import os
import struct
import sys
from collections import namedtuple

import derived
from harness import BASE_IMAGE, _lib, addrs, emu
from recreate_kit import rom_bench

import aes
import aes_boot
import aes_event
import aes_switch
import case
import gemdos
import routines
import vdi

RAM_BYTES = addrs.ST_RAM_BYTES
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes.OS_BUS_ADDR_MASK
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
LOADER = aes.header_constants("loader.h")

# ---- the routines, and how each is called -------------------------------------------------------------------------------
SNDCLI, LDACCS, FREE_ACCS, CRE_APROC = "AES_ROM_SNDCLI", "AES_ROM_LDACCS", "AES_ROM_FREE_ACCS", "AES_ROM_CRE_APROC"
aes.declare_alcyon(SNDCLI, aes.WORD_ANSWER, (IMAGE, LONG, WORD))
aes.declare_alcyon(LDACCS, None, (IMAGE,))
aes.declare_alcyon(FREE_ACCS, None, (IMAGE,))
aes.declare_alcyon(CRE_APROC, aes.WORD_ANSWER, (IMAGE,))

# ---- GEMDOS, as the AES's glue calls it ------------------------------------------------------------------------------------
# Each function the loader's calls reach, with HOW MANY BYTES OF ITS FRAME ARE ITS OWN (above them lies its caller's
# stack, which no C build reproduces): a call of any other function inside a watched run is refused by name.
FRAME_BYTES = {
    addrs.GEMDOS_DGETDRV_FN: 0, addrs.GEMDOS_FSNEXT_FN: 0,
    addrs.GEMDOS_DSETDRV_FN: WORD_BYTES, addrs.GEMDOS_FCLOSE_FN: WORD_BYTES,
    addrs.GEMDOS_MALLOC_FN: LONG_BYTES, addrs.GEMDOS_MFREE_FN: LONG_BYTES, addrs.GEMDOS_FSETDTA_FN: LONG_BYTES,
    addrs.GEMDOS_DSETPATH_FN: LONG_BYTES,
    addrs.GEMDOS_FSFIRST_FN: LONG_BYTES + WORD_BYTES, addrs.GEMDOS_FOPEN_FN: LONG_BYTES + WORD_BYTES,
    addrs.GEMDOS_MSHRINK_FN: WORD_BYTES + 2 * LONG_BYTES, addrs.GEMDOS_PEXEC_FN: WORD_BYTES + 3 * LONG_BYTES,
}
TRAP_1 = 0x4e41
EXCEPTION_FRAME_BYTES = aes_boot.FRAME_BYTES     # the status word, then the PC: a `trap`'s, from supervisor state too
DOS_ALLOC_END = 0xfe3be8                # dos_alloc's last `rts` + 2: its body ($fe3bba..), which holds its own trap
GEM_DOS_TRAP_END = addrs.AES_ROM_RESTORE_TRAP2      # `__DOS` ($fe3c3e..$fe3c61), which every other door of the glue takes


def _after_its_trap(lo, hi):
    """Where the one `trap #1` of the ROM's code `[lo, hi)` returns: the instruction behind it."""
    traps = [at for at in range(lo, hi, WORD_BYTES) if case.word_in(BASE_IMAGE, at) == TRAP_1]
    assert len(traps) == 1, f"the ROM's code [{lo:#x}, {hi:#x}) holds {len(traps)} `trap #1`, not one"
    return traps[0] + WORD_BYTES


# THE TWO PLACES THE AES'S GLUE TRAPS FROM, read off the ROM's own bytes: dos_alloc's own trap, and `__DOS`'s.
GLUE_TRAP_RETURNS = (_after_its_trap(addrs.AES_ROM_DOS_ALLOC, DOS_ALLOC_END),
                     _after_its_trap(addrs.AES_ROM_GEM_DOS_TRAP, GEM_DOS_TRAP_END))


class Refused(RuntimeError):
    """A watched run met what this module does not read, or a C run parted from the ROM's: said by name."""


# ---- A MACHINE WHERE A ROM RUN STANDS STOPPED, AND THE ROM'S RUN ON FROM IT ------------------------------------------------
Stood = namedtuple("Stood", "ram registers disk io")
Stood.__doc__ = """A machine where the ROM's boot stands stopped: its megabyte, the CPU's whole register file there
(`aes_boot.REGISTER_NAMES`: the PC is the stop), the `disk` in drive A: as the boot has left it, and the shifter
bytes the pre-init machine carried (`io`: what a run continued from it is served)."""
Call = namedtuple("Call", "function frame own answer stored")
Call.__doc__ = """ONE GEMDOS CALL of a watched run: its `function`, its `frame`'s own bytes (FRAME_BYTES), `own` — what
THE ROUTINE ITSELF changed in RAM since the call before (or the run's start), as `((address, bytes), ...)` — the
`answer` (D0 where the trap returns) and `stored`: what GEMDOS changed, the same way."""
Ran = namedtuple("Ran", "stood calls silent instructions")
Ran.__doc__ = """The ROM's own run from one stop to the next (`run_on`): the machine where it `stood` at the end, the
GEMDOS `calls` it made, in order, and `silent` — the `(address, length)` runs of RAM the run's own code (outside
its GEMDOS calls) STORED AT and left holding what they held when it began; None where the run's write ledger
SATURATED (a `Pexec` clears the largest free block, a store a byte: six loads are more stores than the kit's ledger
holds), so that nobody knows — and the `instructions` it took."""
RUN_INSNS = 1_000_000                   # a whole ldaccs with two accessories is some 131,000, with six 400,000
COMPARED_BLOCK_BYTES = 0x1000


def stood_at(boot):
    """A `Boot` stopped at `until` as a `Stood`."""
    return Stood(boot.ram, boot.registers, boot.disk, boot.io)


def _changed(before, after):
    """What `after` holds where it differs from `before` (two megabytes): `((address, bytes), ...)`, maximal runs."""
    runs = []
    for block in range(0, RAM_BYTES, COMPARED_BLOCK_BYTES):
        if before[block:block + COMPARED_BLOCK_BYTES] == after[block:block + COMPARED_BLOCK_BYTES]:
            continue
        for at in range(block, block + COMPARED_BLOCK_BYTES):
            if before[at] != after[at]:
                if runs and runs[-1][0] + runs[-1][1] == at:
                    runs[-1][1] += 1
                else:
                    runs.append([at, 1])
    return tuple((at, bytes(after[at:at + length])) for at, length in runs)


def laid(memory, runs):
    """`runs` (`((address, bytes), ...)`) laid into the megabyte `memory`, in place."""
    for at, data in runs:
        memory[at:at + len(data)] = data


class _GemdosWatched:
    """THE WATCH OF ONE RUN AT `trap #1` (the module's docstring): the stops it asks `aes_boot`'s run for — GEMDOS's
    own entry, as the machine's vector holds it, and the two places the AES's glue traps from — and at each what it
    keeps. A trap from anywhere else, a function FRAME_BYTES does not name, or a stop out of turn (the run's stops
    are re-armed at the next stop: two entries with no return between them would be one) is refused by name."""

    def __init__(self, memory):
        self._memory, self._entry = memory, case.long_in(memory, addrs.VECTOR_TRAP_GEMDOS) & BUS
        self._last, self._open, self._mark = bytes(memory[:RAM_BYTES]), None, 0
        self.calls, self.own_stores = [], set()

    def stops(self):
        return {self._entry: ("trap #1", self._entered),
                **{at: ("the glue's trap returns", self._returned) for at in GLUE_TRAP_RETURNS}}

    def _ledger(self, since):
        """The addresses of RAM the run's write ledger names from its entry `since` on, and where the ledger stands."""
        count = aes_boot._CPU.osh_num_writes()
        return {at for at in aes_boot._CPU.osh_write_addrs()[since:count] if at < RAM_BYTES}, count

    def _entered(self, memory, sp):
        if self._open is not None:
            raise Refused("a `trap #1` taken inside a GEMDOS call of the watched run: a nested call is not read")
        status, back = case.word_in(memory, sp), case.long_in(memory, sp + WORD_BYTES) & BUS
        if not status & aes_boot.SR_SUPERVISOR or back not in GLUE_TRAP_RETURNS:
            raise Refused(f"a `trap #1` from {back - WORD_BYTES:#x} (status {status:#06x}) inside the watched run: not one "
                          f"of the AES's glue ({', '.join(f'{at - WORD_BYTES:#x}' for at in GLUE_TRAP_RETURNS)})")
        words_at = sp + EXCEPTION_FRAME_BYTES
        function = case.word_in(memory, words_at)
        if function not in FRAME_BYTES:
            raise Refused(f"the watched run calls GEMDOS function {function:#x}, whose frame this module does not name")
        frame = bytes(memory[words_at + WORD_BYTES:words_at + WORD_BYTES + FRAME_BYTES[function]])
        now = bytes(memory[:RAM_BYTES])
        stored, self._mark = self._ledger(self._mark)
        self.own_stores |= stored
        self._open, self._last = (function, frame, _changed(self._last, now)), now

    def _returned(self, memory, _sp):
        if self._open is None:
            raise Refused("the glue's trap returns and no `trap #1` was seen entered: the watch missed a stop")
        function, frame, own = self._open
        now = bytes(memory[:RAM_BYTES])
        _stored, self._mark = self._ledger(self._mark)
        self.calls.append(Call(function, frame, own, aes_boot.registers_at_the_stop(("d0",))["d0"], _changed(self._last, now)))
        self._open, self._last = None, now

    def ended(self):
        """The run is over: every call returned — and the routine's own stores since the last are counted."""
        if self._open is not None:
            raise Refused(f"the watched run ended inside its GEMDOS call {self._open[0]:#x}")
        stored, self._mark = self._ledger(self._mark)
        self.own_stores |= stored


def _run_on(stood, until, budget):
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = stood.ram
    floppy = aes_boot.Floppy(memory, stood.disk)
    watch = _GemdosWatched(memory)
    run = aes_boot._Run(memory, floppy, budget, until=until, observing=watch.stops())
    try:
        result = run.to_an_idle(stood.registers, aes_boot._io_seed(stood.io))
        registers = aes_boot._registers_now()
        watch.ended()
        _writes, truncated = emu.bench_writes(memory)
    finally:
        aes_boot._CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"the ROM's boot continued to {until:#x}")
    ram = bytes(memory[:RAM_BYTES])
    silent = None if truncated else aes_boot._runs(sorted(at for at in watch.own_stores if ram[at] == stood.ram[at]))
    return Ran(Stood(ram, registers, bytes(floppy.disk), stood.io), tuple(watch.calls), silent, result["ninsns"])


@derived.kept
def run_on(stood, until, budget=RUN_INSNS):
    """THE ROM'S OWN RUN from the machine `stood` (a `Stood`: where a boot was stopped) to its NEXT ARRIVAL at the ROM
    address `until`, through `aes_boot`'s device model, watched at `trap #1`: a `Ran`. An idle met first, or the
    budget run out, is refused by `aes_boot`'s own name for it — and so is a run ENTERED AT `until` (whether the stop
    it stands at counts as the arrival is the run loop's to say, and has been both)."""
    if stood.registers["pc"] == until:
        raise Refused(f"a run entered at {until:#x} to stop at {until:#x}: run it on past that stop first")
    return _run_on(stood, until, budget)


# ---- AN ARRIVAL: a routine met where the ROM's own caller calls it ---------------------------------------------------------
Arrival = namedtuple("Arrival", "routine stood arguments")
Arrival.__doc__ = """`routine` (an `addrs` name) where the ROM's boot calls it: the machine `stood` there — the PC its
entry, the stack pointer at the return address its caller's Line-F call left — and the `arguments` its caller pushed,
read off that frame."""


def arrival(routine, stood):
    """`stood` — a machine stopped at `routine`'s entry — as its `Arrival`."""
    registers = stood.registers
    if registers["pc"] != getattr(addrs, routine) or not registers["sr"] & aes_boot.SR_SUPERVISOR:
        raise Refused(f"the machine stands at {registers['pc']:#x} (status {registers['sr']:#06x}), not at {routine}'s entry "
                      f"in supervisor state")
    formats = "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(routine))
    frame = struct.Struct(">" + formats)
    at = registers["isp"] + LONG_BYTES
    return Arrival(routine, stood, frame.unpack(stood.ram[at:at + frame.size]))


def return_site(arrived):
    """Where the routine an `Arrival` stands at returns to: the longword under its stack pointer."""
    return case.long_in(arrived.stood.ram, arrived.stood.registers["isp"]) & BUS


def _vet_it_returned(arrived, ran):
    """`ran` ended where `arrived`'s routine returns TO ITS CALLER: the stack pointer one return address above the one
    it was called at — or it is refused by name (an arrival at that address from somewhere else)."""
    there, called_at = ran.stood.registers, arrived.stood.registers["isp"]
    if there["isp"] != called_at + LONG_BYTES:
        raise Refused(f"the run arrived at {return_site(arrived):#x} with the stack pointer at {there['isp']:#x}: not "
                      f"{arrived.routine}'s return to its caller, called at {called_at:#x}")
    return ran


def returned(arrived, budget=RUN_INSNS):
    """THE ROM'S OWN RUN OF THE ROUTINE, from its `Arrival` to its return (the module's docstring): a `Ran` — HELD to
    have returned to its caller, the frame popped."""
    return _vet_it_returned(arrived, run_on(arrived.stood, return_site(arrived), budget))


def answered(ran):
    """The word of D0 where a ROM run ended: what an Alcyon caller reads of an `int` answer."""
    return ran.stood.registers["d0"] & aes.WORD_MASK


# ---- WHAT THE TWO SHORES' MEGABYTES DIFFER IN BY NATURE ------------------------------------------------------------------
ROM_FRAMES = "the ROM's own frames: the running process's stack below the stack pointer the routine was called at"
HOST_FRAMES = "the host's frames: the host slots the routine's C keeps its frames in off target"
LINE_F_MASK = "the Line-F mask word"
# The host slots each routine's C claims, by role (`include/host_slot.h`): its own and its callees'.
HOST_SLOT_ROLES = {
    CRE_APROC: ("GEMDOS_WORDS",),
    FREE_ACCS: ("GEMDOS_WORDS",),
    SNDCLI: ("GEMDOS_WORDS", "AES_PGMLD_WORDS", "AES_SNDCLI_BASEPAGE"),
    LDACCS: ("GEMDOS_WORDS", "AES_PGMLD_WORDS", "AES_SNDCLI_BASEPAGE"),
}


def host_slot_spans(roles):
    return tuple((aes.HOST_SLOTS[f"HOST_SLOT_{role}"], aes.HOST_SLOTS[f"HOST_SLOT_{role}"] + aes.HOST_SLOTS[f"HOST_SLOT_{role}_BYTES"])
                 for role in roles)


def rom_frames(stood):
    """`(lo, hi)`: the running process's stack below the stack pointer `stood` stands at — from the end of its UDA's
    state block, read through the machine's own pointers. Refused where the stack pointer is not on that stack."""
    running = case.long_in(stood.ram, aes.AES_RLR) & BUS
    uda = case.long_in(stood.ram, running + aes.PD_UDA) & BUS
    lo, sp = uda + aes.UDA_STATE_BYTES, stood.registers["isp"]
    top = case.long_in(stood.ram, uda + aes.UDA_SUPER_SP) & BUS
    if not running or not lo < sp <= top:
        raise Refused(f"the routine is called at SP {sp:#x}, not on the stack of the running process at {running:#x} "
                      f"([{lo:#x}, {top:#x}] by its UDA)")
    return lo, sp


class Classes:
    """THE CLASSES ONE CASE NAMES (`{class: ((lo, hi), ...)}`), and which of them the two megabytes were SEEN to
    differ in at any compare of the case: one never needed is refused (`vet_each_was_needed`)."""

    def __init__(self, spans):
        self.spans, self.needed = dict(spans), set()

    def outside(self, at, length):
        return not any(lo < at + length and at < hi for each in self.spans.values() for lo, hi in each)

    def differing(self, theirs, ours):
        """Where the megabytes `theirs` (the ROM's) and `ours` differ OUTSIDE every class: `[(address, length), ...]`."""
        left = bytearray(ours)
        for name, spans in self.spans.items():
            for lo, hi in spans:
                if theirs[lo:hi] != left[lo:hi]:
                    self.needed.add(name)
                left[lo:hi] = theirs[lo:hi]
        return aes_boot._differing_runs(theirs, bytes(left))

    def vet_each_was_needed(self, who):
        unneeded = sorted(set(self.spans) - self.needed)
        if unneeded:
            raise Refused(f"{who}: the two shores never differ in {unneeded} — a class named and not needed")


def classes_of(arrived, *named):
    """The classes `named` (ROM_FRAMES, HOST_FRAMES, LINE_F_MASK) as `arrived`'s case locates them: a `Classes`."""
    located = {ROM_FRAMES: lambda: (rom_frames(arrived.stood),),
               HOST_FRAMES: lambda: host_slot_spans(HOST_SLOT_ROLES[arrived.routine]),
               LINE_F_MASK: lambda: tuple((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW)}
    unknown = [name for name in named if name not in located]
    if unknown:
        raise Refused(f"no class a case of the loader may name: {unknown}")
    return Classes({name: located[name]() for name in named})


def _said(runs, theirs, ours, most=6):
    return "; ".join(f"{at:#x}+{length}: the ROM's {bytes(theirs[at:at + min(length, 8)]).hex()}, ours "
                     f"{bytes(ours[at:at + min(length, 8)]).hex()}" for at, length in runs[:most]) + (
                         f" … and {len(runs) - most} more runs" if len(runs) > most else "")


# ---- THE C'S RUN, GEMDOS REPLAYED FROM THE ROM'S -----------------------------------------------------------------------------
FUNCTION_OF_HANDLER = {gemdos.rom_handler(function): function for function in FRAME_BYTES}
assert len(FUNCTION_OF_HANDLER) == len(FRAME_BYTES), "two of the loader's GEMDOS functions share a handler"
C_Ran = namedtuple("C_Ran", "answer ram calls")


def _megabyte(buf):
    return ctypes.string_at(ctypes.addressof(buf.contents), RAM_BYTES)


REFUSED_IN_ITS_FORK = 7                 # a fork's exit status where the replay refused its C's call (FORK_RAISED is 8)


class _Replayed:
    """GEMDOS REPLAYED TO ONE C RUN from the ROM's `calls` (the module's docstring) over the megabyte `started`:
    `handlers()` is what the candidate's GEMDOS dispatcher is bound to. `made`: how many calls the C has made.
    A REFUSAL CANNOT BE RAISED THROUGH THE C THAT MADE THE CALL — the hook would answer it a fabricated 0 and the C
    would run on over it — so the run is made IN A FORK FIRST (`the_c_s`), where a refusal says its words and ENDS
    THE FORK (`ends_its_fork`); the run in process is made only once that fork came back clean."""

    def __init__(self, who, started, calls, classes):
        self._who, self._rom, self._calls, self._classes, self.made = who, bytearray(started), calls, classes, 0
        self.ends_its_fork = False

    def handlers(self):
        return {handler: functools.partial(self._call, function) for handler, function in FUNCTION_OF_HANDLER.items()}

    def _refuse(self, said):
        if self.ends_its_fork:
            print(said, file=sys.stderr, flush=True)
            os._exit(REFUSED_IN_ITS_FORK)
        raise Refused(said)

    def _call(self, function, buf, arguments, _argument_bytes):
        nth = self.made
        if nth >= len(self._calls):
            self._refuse(f"{self._who}: the C makes a GEMDOS call more than the ROM's {len(self._calls)} — function {function:#x}")
        expected = self._calls[nth]
        frame = ctypes.string_at(ctypes.addressof(buf.contents) + arguments, FRAME_BYTES[function])
        if (function, frame) != (expected.function, expected.frame):
            self._refuse(f"{self._who}: GEMDOS call {nth} of the C is {function:#x} over {frame.hex()}, the ROM's "
                         f"{expected.function:#x} over {expected.frame.hex()}")
        laid(self._rom, expected.own)
        ours = _megabyte(buf)
        differing = self._classes.differing(self._rom, ours)
        if differing:
            self._refuse(f"{self._who}: where it makes GEMDOS call {nth} ({function:#x}) the C's megabyte is not the "
                         f"ROM's — {_said(differing, self._rom, ours)}")
        laid(self._rom, expected.stored)
        for at, data in expected.stored:
            for offset in range(len(data)):
                if self._classes.outside(at + offset, 1):
                    buf[at + offset] = data[offset]
        self.made = nth + 1
        return aes.signed(expected.answer, bits=32)


def the_c_s(arrived, ran, classes):
    """THE C'S RUN of an `Arrival`'s routine over its megabyte, GEMDOS replayed from the ROM's run `ran` (the module's
    docstring): a `C_Ran` — its answer (None for a routine that answers nothing), the megabyte where it returned, how
    many GEMDOS calls it made. MADE IN A FORK FIRST (`aes_event.in_a_fork`, every hook as this pass bound it), then
    in process: refused by name at the first call that is not the ROM's or is made over another megabyte than the
    ROM's, and where the C does not come back (the host's own refusal of a store through a pointer that is none)."""
    name = arrived.routine
    who, core = routines.core_symbol(name), getattr(_lib, routines.core_symbol(name))
    arguments = vdi.as_signed(name, arrived.arguments)
    replayed = _Replayed(who, arrived.stood.ram, ran.calls, classes)

    def fork_first(_lib_, buf):
        def in_the_fork():
            replayed.ends_its_fork = True
            core(buf, *arguments)
        returncode, stderr = aes_event.in_a_fork(in_the_fork, aes_event.CORE_RETURN_SECONDS, aes_event.EVERY_HOOK_OF_THE_PASS)
        if returncode == REFUSED_IN_ITS_FORK:
            raise Refused(stderr.strip())
        if returncode:
            raise Refused(f"{who}: the C did not return in a fork ({returncode}): {stderr.strip()}")
        return core(buf, *arguments)
    answer, image = gemdos.run_candidate_only(fork_first, {0: arrived.stood.ram}, replayed.handlers())
    held_still = aes_switch.host_slots_held()
    if held_still:
        raise Refused(f"{who}: the C returned with its host slot(s) {held_still} still claimed")
    return C_Ran(answer, image[:RAM_BYTES], replayed.made)


def held(arrived, *named, ran=None):
    """ONE PASS OF A CASE: the C's run of `arrived`'s routine HELD to the ROM's own (`returned`, or the run `ran`
    handed in) — the same GEMDOS calls over the same megabyte at each, the same answer, the same megabyte where it
    returns, outside the classes `named`, each of which must have been needed. Answers `(the ROM's Ran, the C's)`."""
    ran = ran or returned(arrived)
    who, classes = routines.core_symbol(arrived.routine), classes_of(arrived, *named)
    ours = the_c_s(arrived, ran, classes)
    if ours.calls != len(ran.calls):
        raise Refused(f"{who}: the C made {ours.calls} GEMDOS calls, the ROM's run {len(ran.calls)}")
    if vdi.ALCYON[arrived.routine].restype is not None and ours.answer != answered(ran):
        raise Refused(f"{who}: the C answers {ours.answer:#x}, the ROM {answered(ran):#x}")
    differing = classes.differing(ran.stood.ram, ours.ram)
    if differing:
        raise Refused(f"{who}: where it returns the C's megabyte is not the ROM's — {_said(differing, ran.stood.ram, ours.ram)}")
    classes.vet_each_was_needed(who)
    return ran, ours


# ---- THE SECOND PASS: every store that changes nothing, made to show --------------------------------------------------------
# The two counts getpd and cre_aproc index by before they are stored back, one reason each (a case names the one its
# run reads first): inverted, the high byte makes the count NEGATIVE and the table's entry lies below the table.
STEERS_THE_STATIC_COUNT = aes.steers(
    "the count of static PDs handed out, which getpd indexes the PD table by and stores back counted on",
    (aes.AES_STATIC_PIDS, aes.AES_STATIC_PIDS + WORD_BYTES))
STEERS_THE_ACCESSORY_COUNT = aes.steers(
    "the count of accessories allocated, which cre_aproc, sndcli and getpd index their tables by before getpd stores it "
    "back counted on",
    (aes.AES_ACCESSORY_COUNT, aes.AES_ACCESSORY_COUNT + WORD_BYTES))


def no_c_stores(stood):
    """THE SPANS OF `stood`'s MEGABYTE NO C STORES BY NATURE, `[(lo, hi), ...]`: the ROM's own frames, the Line-F mask
    word, and the words the ROM parks its status register in (a host core has none to park)."""
    lo, hi = rom_frames(stood)
    mask = tuple((left, right) for left, right, _why in aes.LINE_F_MASK_WINDOW)
    parked = tuple((at, at + 1) for at in sorted(aes_event.SR_SAVE_BYTES))
    return [(lo, hi), *mask, *parked]


def silently_stored(arrived, ran, steers=()):
    """`arrived` with EVERY BYTE THE ROM'S ROUTINE STORED AND LEFT AS IT FOUND IT INVERTED (`Ran.silent`, the run's
    own write ledger outside its GEMDOS calls) — but what no C stores (`no_c_stores`) and the words of `steers`
    (`aes.steers`): the machine of the second pass, an `Arrival`. REFUSED BY NAME for a run whose write ledger
    saturated: what it stored silently is not known, and a second pass made of a guess would hold nothing."""
    if ran.silent is None:
        raise Refused(f"{arrived.routine}: the ROM's run saturated the kit's write ledger — what its own code stored "
                      f"without changing it is not known, and no second pass can be made of it")
    kept = [*no_c_stores(arrived.stood), *(span for reason in steers for span in reason.spans)]
    ram = bytearray(arrived.stood.ram)
    for start, length in ran.silent:
        for at in range(start, start + length):
            if not any(left <= at < right for left, right in kept):
                ram[at] ^= aes.BYTE_MASK
    return arrived._replace(stood=arrived.stood._replace(ram=bytes(ram)))


def held_twice(arrived, *named, steers=()):
    """A CASE, WHOLE (the module's docstring): `held` as the boot made the arrival, then again over the machine
    `silently_stored` makes of it — the ROM's own run made again from there. Answers the first pass's `(Ran, C_Ran)`."""
    first = held(arrived, *named)
    held(silently_stored(arrived, first[0], steers), *named)
    return first


def _as_run(started, ran):
    """What two ROM runs are told apart by: each call's function, frame and answer, and WHERE the machine `started`
    was changed by the time the run ended."""
    return (tuple((call.function, call.frame, call.answer) for call in ran.calls),
            tuple((at, len(data)) for at, data in _changed(started.stood.ram, ran.stood.ram)))


def steers_the_rom(arrived, reason, steers):
    """WHETHER `reason` — one of a case's `steers` — IS NEEDED, asked of the ROM alone: its own run from the second
    pass's machine with THAT reason's words inverted too parts from the run with them left (it is refused, or makes
    other calls, or changes the machine elsewhere). No C is run: a steered C may store anywhere."""
    assert reason in steers
    first = returned(arrived)
    kept = silently_stored(arrived, first, steers)
    inverted = silently_stored(arrived, first, [each for each in steers if each is not reason])
    try:
        astray = returned(inverted)
    except (Refused, aes_boot.Refused, RuntimeError, AssertionError):    # ...the kit's own refusal of a run gone astray too
        return True
    return _as_run(inverted, astray) != _as_run(kept, returned(kept))


# ---- THE ARRIVALS THE ROM'S BOOTS REACH -------------------------------------------------------------------------------------
def boot_arrival(routine, preinit, disk):
    """The boot of `preinit` over `disk` stopped at its FIRST call of `routine`: an `Arrival`."""
    return arrival(routine, stood_at(aes_boot.booted(preinit, disk, until=getattr(addrs, routine))))


def next_arrival(routine, arrived):
    """...and the boot continued from the `Arrival` `arrived` to its NEXT call of `routine` — past `arrived`'s own
    return first where it stands at that very routine: a run is never entered at the address it is to stop at."""
    stood = returned(arrived).stood if arrived.routine == routine else arrived.stood
    return arrival(routine, run_on(stood, getattr(addrs, routine)).stood)


def staged(arrived, pokes):
    """AN ARGUMENT CLASS, to be labelled by whoever makes it: `arrived` with `pokes` (`{address: bytes}`) laid over its
    megabyte — the ROM's own run is then made from THAT machine, in place, as from any arrival (its arguments read off
    the frame again: a staging may be of the frame itself)."""
    ram = bytearray(arrived.stood.ram)
    laid(ram, tuple(pokes.items()))
    return arrival(arrived.routine, arrived.stood._replace(ram=bytes(ram)))
