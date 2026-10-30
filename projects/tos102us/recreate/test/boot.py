r"""THE BOOT HARNESS (boot B0) — the ROM's own boot run in slices, on named machines (`test_boot_harness.py`).

THE USER'S RULINGS (2026-10-29) THIS MODULE IS BUILT ON, quoted:
  * D8 "Approve all three": a WARM-reset machine built from the post-boot snapshot, a COLD machine, and a new Hatari
    capture stopped mid-boot at $fc047a — each a LABELLED STAGING (`warm_machine`, `cold_machine`, `midboot_machine`;
    the capture `tools/midboot_snapshot.py`, kept like the pre-init captures).
  * D5 "Harness-local": bus errors as a case facility in a test helper (`bus_error.py`), no kit edit.
  * D9 "Stretch rows": boot's slices priced as band 5's our-boot stretch kind, each [start, end) on its own cycles
    beside the ROM's own boot run. (B1's on; this module gives a slice its `cycles` and its instruction count.)
  * D7 "Byte-transcribed .S" for the head [$fc0030, $fc02cc): B1's — compared slice by slice on THIS runner.

A SLICE (`run`): the ROM's code run from where a machine stands (its PC) to its FIRST ARRIVAL at any of the stops
named — EVERY ARRIVAL IS A STOP, as `aes_boot._Run`'s (`stopped_cpu.stepped_off`, shared: a run that stands at a stop
leaves it by one instruction with that PC alone disarmed), a declared fault's handler among them (the fault taken, the
handler entered is an arrival like any other). It answers a `Slice`: the machine it left (RAM, the whole register
file, SR among it — a `BootMachine` that the next slice runs from), the stop arrived at, its instructions and cycles,
the RAM it stored to, the ordered I/O ledgers (the hardware writes, the declared I/O reads, the modelled hardware
reads, the PSG accesses) and the bus-error frames it took. REFUSED BY NAME: a run that does not arrive within its
budget (said with the PC it stands at — the boot's waits spin for ever in an oracle where no time passes), one that
leaves the machine, one that makes no progress at a stop it stands at, one whose write ledger saturated, and one the
kit's own vet refuses (an I/O read nothing declared
answered 0, a ledger overflowed — `rom_bench.vet_the_run_just_made`).

WHAT IS DELIVERED: NO INTERRUPT (decision D3, open — the boot opens them at `$fc0452`; on the machine VBL, Timer C,
the ACIAs and the FDC arrive between any two instructions from there on). NO TIME PASSES inside a run. `reset`
(`$fc0034`) is Musashi's no-op (built without M68K_EMULATE_RESET): its effect on the chips is on no surface
(decision D6, open). The cartridge port reads as the image holds it, zero: the no-cartridge arms alone (D2, open).
A declared fault (`bus_error.Fault`) is the one exception the harness takes for the CPU.

THE MACHINES, each a LABELLED STAGING whose docstring says what is real and what is laid:
  * WARM (`warm_machine`): the post-boot snapshot entered at the reset vector;
  * COLD (`cold_machine`): the same with the memory-valid magics broken;
  * MID-BOOT (`midboot_machine`): Hatari's capture at `$fc047a`.
"""
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu
from recreate_kit import rom_bench

import midboot_snapshot

import aes
import aes_boot
import bus_error
import case
import stopped_cpu

RAM_BYTES = addrs.ST_RAM_BYTES
ROM_BASE = emu.ROM_BASE
LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
BUS = aes.OS_BUS_ADDR_MASK
REGISTER_NAMES = stopped_cpu.REGISTER_NAMES
Refused = bus_error.Refused


class NeverArrived(Refused):
    """A run that spent its budget without arriving at a stop: `standing`, the PC it stands at — where the boot waits."""

    def __init__(self, message, standing):
        super().__init__(message)
        self.standing = standing

# ---- THE RESET, AS THE ROM SAYS IT ---------------------------------------------------------------------------------------
# A 68000's reset loads SSP and PC from $0..$7, which an ST maps to the ROM's first two longwords; SR becomes $2700
# (supervisor, trace off, mask 7). Every other register keeps what it held — on a power-on, nothing defined.
RESET_SSP, RESET_PC = struct.unpack_from(">2I", BASE_IMAGE, ROM_BASE)
RESET_SR = 0x2700

# ---- WHAT THE BOOT TESTS, READ OFF ITS OWN OPERANDS ----------------------------------------------------------------------
CMPI_L_D16_A5, BNE_S, JMP_A6 = 0x0cad, 0x66, 0x4ed6         # `cmpi.l #imm,d16(a5)`, `bne.s`, `jmp (a6)`
BEQ_W = 0x6700
MEMVALID_CHECK = 0xfc0688               # `suba.l a5,a5`, then a cmpi.l + bne.s per magic, then `jmp (a6)`: Z set = valid
RESVALID_CHECK = 0xfc0062               # `cmpi.l #$31415926,$426(a5)`: a reset-resident hook to jump through
MEMVALID_BRANCH = 0xfc00ec              # the second check's return: `beq.w` past the sizing to where both arms join
CMPI_BYTES = 8                          # opcode, the immediate long, the displacement
STEP_OVER_SUBA = WORD_BYTES             # MEMVALID_CHECK's first instruction, `suba.l a5,a5`
BNE_S_BYTES = WORD_BYTES
CARTRIDGE = 0xfa0000                    # the cartridge port: a diagnostic cartridge's magic or an application chain's
DIAGNOSTIC_CARTRIDGE_MAGIC, APPLICATION_CARTRIDGE_MAGIC = 0xfa52235f, 0xabcdef42   # `$fc0036`, `$fc064c`


def _cmpi_at(at):
    """`(address, magic)` of the `cmpi.l #magic,address(a5)` at `at` (A5 = 0 there) — refused by name if it is not one."""
    opcode, magic, displacement = struct.unpack_from(">HIH", BASE_IMAGE, at)
    if opcode != CMPI_L_D16_A5:
        raise Refused(f"the ROM holds {opcode:#06x} at {at:#x}, not the boot's `cmpi.l #imm,d16(a5)`")
    return displacement, magic


def memvalid_magics():
    """THE MEMORY-VALID MAGICS the boot tests (`$fc0688`), `((address, magic), ...)` in its order — each read off its
    `cmpi.l`, a `bne.s` between two, the last followed by `jmp (a6)`."""
    magics, at = [], MEMVALID_CHECK + STEP_OVER_SUBA
    while True:
        magics.append(_cmpi_at(at))
        at += CMPI_BYTES
        if case.word_in(BASE_IMAGE, at) == JMP_A6:
            return tuple(magics)
        if BASE_IMAGE[at] != BNE_S:
            raise Refused(f"the memory-valid check's compare at {at - CMPI_BYTES:#x} is followed by neither a `bne.s` "
                          f"nor its `jmp (a6)`")
        at += BNE_S_BYTES


def resvalid_magic():
    """`(address, magic)`: the reset-resident hook's validity long (`$fc0062`) — the hook is jumped through if it holds."""
    return _cmpi_at(RESVALID_CHECK)


def _beq_w_target(at):
    opcode, displacement = struct.unpack_from(">Hh", BASE_IMAGE, at)
    if opcode != BEQ_W:
        raise Refused(f"the ROM holds {opcode:#06x} at {at:#x}, not the boot's `beq.w`")
    return at + WORD_BYTES + displacement


WARM_ARM = _beq_w_target(MEMVALID_BRANCH)               # memory valid: the sizing skipped, both arms join here
COLD_ARM = MEMVALID_BRANCH + WORD_BYTES + WORD_BYTES    # ...and the fall-through: the cold arm's first instruction

# ---- THE CUT (the survey's §3): where the boot's slices begin and end ------------------------------------------------------
HEAD_FIRST_ENDS = 0xfc00da              # `suba.l a5,a5` before the second memory-valid check: [reset, here) is warm or cold alike
LEA_STACK = 0xfc02c6                    # `lea $755a,sp`: the BIOS's stack, the first point C can stand on
LEA_STACK_WORDS = (0x4ff9, 0x0000, 0x755a)
HEAD_ENDS = LEA_STACK + WORD_BYTES * len(LEA_STACK_WORDS)   # the transcribed head [reset, here) ends (ruling D7)
HARDWARE_INIT_CALLED = 0xfc03b6         # `bsr $fc2408`: the vectors and system variables are laid
IKBD_RESET_DONE = 0xfc03e0              # the IKBD reset sent, the delay spent, the cartridge's hook 2 called
INTERRUPTS_OPENED = 0xfc0452            # `move #$2300,sr`: from here the machine is interrupt-driven (D3)
MOVE_SR_2300 = (0x46fc, 0x2300)
MIDBOOT = midboot_snapshot.STOP         # `tst.w _cmdload`: the capture's stop, the AUTO-and-launch slice's start
THE_CUT = (HEAD_FIRST_ENDS, WARM_ARM, HEAD_ENDS, HARDWARE_INIT_CALLED, IKBD_RESET_DONE, INTERRUPTS_OPENED, MIDBOOT)

# ---- THE MACHINES ------------------------------------------------------------------------------------------------------
BootMachine = namedtuple("BootMachine", "name ram registers io label")
BootMachine.__doc__ = """A machine a boot slice runs from: its `name`, the megabyte of `ram`, the whole register file
(`stopped_cpu.REGISTER_NAMES`: the PC is where the run starts), the shifter bytes a capture read (`io`; empty where
nothing was captured) and its `label` — what is real and what is laid, said in every refusal and test id that uses it."""

WARM = "WARM"
WARM_LABEL = ("BOOT WARM — A LABELLED STAGING (ruling D8): the post-boot snapshot, entered at the reset vector with "
              "memory valid")
COLD = "COLD"
COLD_LABEL = ("BOOT COLD — A LABELLED STAGING (ruling D8): the post-boot snapshot, its memory-valid magics zeroed, entered "
              "at the reset vector; sized on the oracle's FLAT memory (D1 open)")
MIDBOOT_NAME = "MID-BOOT"
MIDBOOT_LABEL = ("BOOT MID-BOOT — A LABELLED STAGING (ruling D8): Hatari's capture at $fc047a, the blank floppy in "
                 "the drive from power-on")


def reset_registers():
    """THE REGISTER FILE A RESET LEAVES, as this harness enters it: PC and SSP read off the ROM's first two longwords,
    SR $2700. LAID: every data and address register and the USP zero (a reset leaves them as they were; the boot
    reads none of them before it writes it — held by the head's own runs)."""
    registers = dict.fromkeys(REGISTER_NAMES, 0)
    registers.update(pc=RESET_PC, isp=RESET_SSP, sr=RESET_SR)
    return registers


def _vet_warm(ram):
    """The premises of a WARM machine, each refused by name: memory valid as the boot tests it; no reset-resident
    hook; no cartridge at the port (the image's zero)."""
    for address, magic in memvalid_magics():
        held = case.long_in(ram, address)
        if held != magic:
            raise Refused(f"{WARM_LABEL}: memory is not valid — {address:#x} holds {held:#x}, the boot tests {magic:#x}")
    address, magic = resvalid_magic()
    if case.long_in(ram, address) == magic:
        raise Refused(f"{WARM_LABEL}: {address:#x} holds the reset-resident magic {magic:#x}: the boot would jump "
                      f"through the hook, an arm of foreign code (D12 open)")
    held = case.long_in(BASE_IMAGE, CARTRIDGE)
    if held in (DIAGNOSTIC_CARTRIDGE_MAGIC, APPLICATION_CARTRIDGE_MAGIC):
        raise Refused(f"the cartridge port reads {held:#x}: a cartridge is no machine of this model's (D2 open)")


def warm_machine():
    """THE WARM MACHINE — A LABELLED STAGING (ruling D8). REAL: the megabyte is the post-boot snapshot's, the machine
    a reset button finds on an ST that booted to the desktop — its memory-valid magics as the boot tests them (read
    off `$fc0688`'s operands), no reset-resident hook; the ROM is the image's. LAID: the register file (`reset_registers`);
    the chips' state, which the oracle has none of (the shifter, MFP, ACIA, PSG answer only what a case declares)."""
    ram = bytes(BASE_IMAGE[:RAM_BYTES])
    _vet_warm(ram)
    return BootMachine(WARM, ram, reset_registers(), b"", WARM_LABEL)


def cold_machine():
    """THE COLD MACHINE — A LABELLED STAGING (ruling D8). The WARM machine with every memory-valid magic ZEROED — a
    power-on's RAM holds none, and zero is one RAM a power-on can hold. LAID, BEYOND THE WARM MACHINE'S: every other
    byte of the megabyte is the post-boot snapshot's (a power-on's is undefined): what survives the cold arm's own
    clears — the vectors below `$400` it does not rewrite, the bytes between its pattern at `$8..$200` and `$400` — is
    the snapshot's. WHERE D1 BITES (open): the cold arm sizes the memory by ALIASES (`$fc0672`) and probes its end
    with a bus-error vector; the oracle's memory is FLAT (a megabyte of RAM, zeros above it, stores there dropped,
    no fault), so the arm runs deterministically and answers its own `memctrl` — not an ST's."""
    ram = bytearray(warm_machine().ram)
    for address, _magic in memvalid_magics():
        ram[address:address + LONG_BYTES] = bytes(LONG_BYTES)
    return BootMachine(COLD, bytes(ram), reset_registers(), b"", COLD_LABEL)


def midboot_machine(path=None):
    """THE MID-BOOT MACHINE — A LABELLED STAGING (ruling D8). REAL: Hatari's boot of the original ROM with the blank
    floppy, stopped at `$fc047a` (`tools/midboot_snapshot.py`, `make midboot`) — the megabyte, the whole register file
    and the shifter bytes as the capture read them. NOT HELD: the chips' state at the stop (the MFP's timers running,
    the ACIAs, the FDC), and the interrupts that would arrive from there (D3) — no run delivers them. Its `MASK`
    bytes are a capture's phase: nothing derived from it may depend on one."""
    machine = midboot_snapshot.load(path)
    return BootMachine(MIDBOOT_NAME, machine.ram, dict(machine.registers), machine.io, MIDBOOT_LABEL)


def entered_at(machine, pc, **registers):
    """`machine` with its run starting at `pc` — and any register named given — the rest as it holds them."""
    return machine._replace(registers={**machine.registers, "pc": pc, **registers})


# ---- THE RUNNER ------------------------------------------------------------------------------------------------------------
SLICE_INSNS = 4_000_000                 # a slice's default budget: the warm head is ~105,000; the cold arm's ~209,000
Slice = namedtuple("Slice", "machine stop instructions cycles stored hardware_writes io_reads hardware_reads psg_events "
                            "faults")
Slice.__doc__ = """One run of a slice: the `machine` it left (a `BootMachine` standing at the stop, the next slice's
start), the `stop` it arrived at, its `instructions` and `cycles` (the oracle's running totals, the entry's segment
included), the RAM it `stored` to as `(start, length)` runs (the write ledger and the frames the harness pushed), the
ledgers `hardware_writes` `(address, width, value)`, `io_reads` (declared I/O, `(address, width, value)`),
`hardware_reads` `(address, value)` and `psg_events`, in order, and the bus-error `faults` taken (`{SP: frame}`)."""


def run(machine, until, budget=SLICE_INSNS, io_seed=None, hw_seed=None, psg_seed=None, faults=()):
    """THE ROM'S CODE RUN FROM `machine` (from its PC, with its whole register file) TO ITS FIRST ARRIVAL AT ANY ADDRESS
    OF `until` — a `Slice`, or REFUSED BY NAME (the module's docstring). `io_seed`, `hw_seed`, `psg_seed`: what the case
    declares the hardware held (the kit's own declarations, refused by the kit where read and undeclared); `faults`:
    the `bus_error.Fault`s the case declares."""
    stops, declared = frozenset(until), bus_error.stops_of(faults)
    if not stops:
        raise Refused("a slice names no stop: it would run for its whole budget")
    armed, entry = stops | set(declared), machine.registers["pc"]
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = machine.ram
    pushed = {}
    emu.install_chip_seeds(psg_seed=psg_seed, hw_seed=hw_seed)
    try:
        result = emu.run_bench(memory, entry, 0, aes_boot.OFF_THE_MACHINE, emu.SENTINEL, max_insns=budget,
                               door={entry}, seed_regs=None, io_seed=io_seed or {})
        assert result["status"] == emu.BENCH_DOOR and not result["ninsns"], "the run began before its registers were laid"
        stopped_cpu.enter(machine.registers)
        at = entry
        while True:
            if at in declared:          # a fault arrived at — or stood at on entry — is taken before anything runs
                pushed.update(bus_error.taken(memory, declared[at]))
                at = stopped_cpu.register("pc")
                if at in stops:         # ...and the handler it enters is an arrival like any other
                    break
                continue
            _left_the_stop(machine, armed)
            result = _resumed(machine, stops, budget)
            at = emu.bench_door_pc()
            if at in stops:
                break
        registers = stopped_cpu.registers_now()
        writes, truncated = emu.bench_writes(memory)
        ledgers = (tuple(emu.hw_writes()), tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.psg_events()))
    finally:
        emu.bench_abort()
    _vetted(machine, stops)
    if truncated:
        raise Refused(f"{machine.label}: the run's write ledger saturated — what it stored is not known")
    stored = set(writes)                # (the kit's ledger holds RAM alone: a store off the machine is dropped)
    for frame_at, frame in pushed.items():
        stored.update(range(frame_at, frame_at + len(frame)))
    left = machine._replace(ram=bytes(memory[:RAM_BYTES]), registers=registers)
    return Slice(left, at, result["ninsns"], result["cycles"], stopped_cpu.address_runs(sorted(stored)), *ledgers, pushed)


def instructions():
    """The run in flight's instruction count so far (the oracle's running total)."""
    return stopped_cpu.CPU.osh_num_insns()


def _left_the_stop(machine, armed):
    """`stopped_cpu.stepped_off`, and REFUSED BY NAME where the run, standing at a stop it must leave, did not leave
    it: no instruction run, the PC where it stood — a resume that makes no progress would stop there for ever."""
    standing, before = stopped_cpu.register("pc"), instructions()
    stopped_cpu.stepped_off(armed)
    if standing in armed and stopped_cpu.register("pc") == standing and instructions() == before:
        raise Refused(f"{machine.label}: the run made no progress at {standing:#x} — it stands at a stop it never left")


def _resumed(machine, stops, budget):
    """The run continued to its next stop — REFUSED BY NAME where its budget does not reach one, or where it leaves
    the machine."""
    left = budget - instructions()
    where = ", ".join(f"{stop:#x}" for stop in sorted(stops))
    if left <= 0:
        raise NeverArrived(f"{machine.label}: the run never arrived at {where} within {budget} instructions",
                           stopped_cpu.register("pc"))
    try:
        result = emu.bench_resume(machine.registers["pc"], max_insns=left)
    except RuntimeError as spun:
        if "did not return to the sentinel" not in str(spun):
            raise
        standing = emu.bench_resume_pc()
        raise NeverArrived(f"{machine.label}: the run never arrived at {where} within {budget} instructions: it stands "
                           f"at {standing:#x}", standing) from spun
    if result["status"] != emu.BENCH_DOOR:
        raise Refused(f"{machine.label}: the run left the machine — status {result['status']} at "
                      f"{emu.bench_resume_pc():#x}")
    return result


def _vetted(machine, stops):
    """The kit's own vet of the run just ended (an I/O read nothing declared, a ledger overflowed), as a refusal."""
    try:
        rom_bench.vet_the_run_just_made(f"{machine.label}: the run to {sorted(hex(stop) for stop in stops)}")
    except AssertionError as refused:
        raise Refused(str(refused)) from refused


def run_through(machine, stops, budget=SLICE_INSNS, final=None, **declared):
    """The machine run slice by slice to each arrival at `stops` in turn (each slice to the first arrival at any of
    them), until one is refused or the machine stands at a `final` stop (by default the last of `stops`): `(the
    slices, the refusal or None)`. What a smoke reports: how far the boot gets, and where and why it stops."""
    slices, standing, stops = [], machine, tuple(stops)
    final = frozenset(final or stops[-1:])
    while True:
        try:
            done = run(standing, stops, budget, **declared)
        except Refused as refusal:
            return tuple(slices), refusal
        slices.append(done)
        if done.stop in final:
            return tuple(slices), None
        standing = done.machine
