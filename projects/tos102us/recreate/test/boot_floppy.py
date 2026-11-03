r"""THE FLOPPY'S LOWER DRIVER ON BOTH SHORES (D4 phase P4, `test_boot_floppy.py`): the ROM's `[$fc173a, $fc1f08)` against
OUR C (`src/boot/floppy/`), each ROM entry it ports reached through a 6-byte `jmp` laid over the ROM's own first
instruction there, so every caller — the XBIOS table, hdv_init's `jsr`, every harness answer keyed by the entry —
reaches ours unchanged. P4a ports the DRIVE PROBE (`$fc173a`) and the primitives it runs on.

THE USER'S RULINGS IT STANDS ON: D4 (2026-11-01, R-D4-1..4: the kit's zero-time FDC/DMA model, armed per run; the chip
and PSG port A carried from the ROM's own runs; the model's ordered ledger held exactly); "ROM-window overlay" and "Own
link rule" (2026-10-29); and (2026-11-02, on the P4 design): R-P4-2 "Jump at ROM entries" — a 6-byte `jmp` laid at each
driver entry address in the test image, 12 cycles a call, priced; R-P4-3 "Both" — A NEW TIER-3 ROW KIND, A DRIVER CALL
PRICED AT ITS ARRIVAL (`ARRIVALS`, `priced`), and the chained boot runs our driver (`boot_chain`), B6's battery keeping
its rows with the ROM's driver beside the new ones (`boot_late.our_side(..., floppy=True)`). The orchestrator's calls
under standing policy: the settle an asm idiom inside the C (the SECTOR_SUM precedent), target-only C, the stack bound
held by making the C fit.

A DRIVER CALL AT ITS ARRIVAL (`arrivals`, `the_rom_s` / `ours`): B6's ROM run from its machine at `$fc0452` through the
FDC model on one drive arm (`boot_late.DRIVE_ARMS`), stopped where hdv_init's `jsr` arrives at the probe — the machine
there, the carry (port A, the chip) — and from that one machine, BOTH SHORES run to the call's return: the ROM's own
probe, and ours entered at the same address (our jump laid there, our body laid in Prtblk's text). The ROM's run then
goes on from where its call returned, to the next arrival.

WHAT IS HELD (`differences`): the stop; EVERY register (D0 the result, D1 / D2 port A's bytes over the caller's upper
ones, A0 the stamp table, A1 the record, SR's flags, the caller's D3-D7 / A3-A6 restored); the megabyte and the addresses
stored OUTSIDE the call's own dead frames — `[FRAMES_APART_FROM, its entry SP)`, the floor the chain holds the BIOS
stack byte for byte below (`boot_chain.FRAMES_APART_FROM`): a store of ours below it is a difference, which is how the
29-byte bound is held — so the 36 bytes the glue saves at `$a28` are held exactly; every ordered ledger (the hardware
writes, the declared reads, the modelled reads, the PSG's accesses, the FDC model's transactions with the polls each
wait made, counted); the chip the model left. Instructions and cycles are the price: each shore's whole call.
"""
import functools
import struct
from collections import namedtuple
from pathlib import Path

from harness import emu

import boot
import boot_late
import layouts
import transcription

RECREATE = Path(__file__).resolve().parents[1]
PRODUCT_DIRECTORY = RECREATE / "build" / "bootfloppy"
CONSTANTS = layouts.parse_constants((RECREATE / "include" / "boot" / "floppy.h",))
JMP_ABSOLUTE_LONG = 0x4ef9
JMP_CYCLES = 12                         # `jmp abs.l` on a 68000: the stub's price, a call (R-P4-2)
ROM_PROBE_FRAME_BYTES = 20              # the ROM's probe stores this far under its entry SP (measured; ours the same)
ROM_TIMEOUT_FRAME_BYTES = 24            # ...and its force-interrupt one call deeper, where a wait times out (ours 20)

# ---- THE ROM'S DRIVER, AND WHAT P4a PORTS OF IT ------------------------------------------------------------------------------
LOWER_DRIVER = (CONSTANTS["ROM_FLOPPY_PROBE"], CONSTANTS["ROM_FLOPPY_LOWER_END"])
PROBE = CONSTANTS["ROM_FLOPPY_PROBE"]
PROBE_SPAN = (PROBE, CONSTANTS["ROM_FLOPPY_FLOPRD"])
# EACH PORTED ENTRY: the ROM's address, where our jump is laid, and the glue's symbol it jumps to.
PORTED = {PROBE: "floppy_probe_entry"}
STUB_BYTES = CONSTANTS["FLOPPY_ENTRY_JUMP_BYTES"]
# THE ROM'S TEXT OUR SHORE MUST NEVER RUN: each ported routine's own text past the jump laid over its first instruction
# (the primitives it shares with the routines still the ROM's — Floprd's — are theirs to run).
NEVER_RUN = tuple((entry + STUB_BYTES, PROBE_SPAN[1]) for entry in PORTED)
# ...AND THE ROM'S DRIVER TEXT OURS STILL RUNS: all of it but the jumps laid over it (Floprd and the primitives it calls are
# the ROM's on both shores until P4b) — what a slice's price reads OFF the ROM's own driver cycles to leave the calls ours
# replaces (`boot_late.priced`, `boot_chain.priced`).
def _without_the_jumps(span):
    lo, hi, kept = *span, []
    for entry in sorted(PORTED):
        kept.append((lo, entry))
        lo = entry + STUB_BYTES
    return tuple((one, other) for one, other in (*kept, (lo, hi)) if one < other)


ROM_TEXT_STILL_RUN = _without_the_jumps(LOWER_DRIVER)

LABEL = ("THE FLOPPY'S LOWER DRIVER, OURS (R-P4-2 \"Jump at ROM entries\"): a 6-byte `jmp` laid at each ported ROM entry, "
         "our body over Prtblk's text")


Product = namedtuple("Product", "base code symbols elf")


@functools.cache
def product():
    """`Product` of `build/bootfloppy/` — refused by name unless it lies at its laid address and ends inside Prtblk's text
    (`make bootfloppy`)."""
    binary, elf = PRODUCT_DIRECTORY / "floppy.bin", PRODUCT_DIRECTORY / "floppy.elf"
    assert binary.is_file() and elf.is_file(), f"{PRODUCT_DIRECTORY} is not built: `make bootfloppy`"
    symbols = {symbol.name: symbol.start for symbol in transcription.symbol_table(elf)}
    base, code = CONSTANTS["FLOPPY_LAID_AT"], binary.read_bytes()
    assert min(symbols[name] for name in PORTED.values()) >= base, f"{elf}: an entry lies below FLOPPY_LAID_AT"
    assert base + len(code) <= CONSTANTS["FLOPPY_LAID_LIMIT"], (
        f"{elf}: {len(code)} bytes from {base:#x} run past FLOPPY_LAID_LIMIT {CONSTANTS['FLOPPY_LAID_LIMIT']:#x}")
    return Product(base, code, symbols, elf)


def stub(entry, symbols=None):
    """The 6 bytes laid at ROM entry `entry`: `jmp <its glue>.l`."""
    symbols = product().symbols if symbols is None else symbols
    return struct.pack(">HI", JMP_ABSOLUTE_LONG, symbols[PORTED[entry]])


def pieces(code=None):
    """OUR DRIVER AS LAID: the body (or `code`, a case's own bytes at its address) and the jump at each ported entry —
    `boot.Overlay`s, each its own LABELLED STAGING ("ROM-window overlay")."""
    body = boot.overlaid(product().base, product().code if code is None else code)
    return (body, *(boot.overlaid(entry, stub(entry)) for entry in PORTED))


def our_spans(laid=None):
    """Every span our driver is laid over: its body and its jumps."""
    return tuple((piece.at, piece.at + len(piece.code)) for piece in (laid or pieces()))


# ---- THE ARRIVALS: B6's ROM run, stopped at each call of a ported entry ---------------------------------------------------
Arrival = namedtuple("Arrival", "machine carry returns_to drive_arm gpip")
Arrival.__doc__ = """One call of a ported entry as the ROM's own B6 run makes it: the `machine` standing at the entry, the
`carry` (port A, the chip) the run hands it, the address it `returns_to` (the long at its SP), the `drive_arm` and the
`gpip` byte its run declares."""


def _declared(arrival):
    return boot_late.floppy_declared(boot_late.drives(arrival.drive_arm), arrival.carry, arrival.gpip)


def _call(arrival, laid=None):
    """One shore's run of `arrival`'s call to its return (`laid`: our driver laid, our jump at the entry)."""
    return boot.run(arrival.machine, {arrival.returns_to}, budget=boot_late.TIMEOUT_ARM_INSNS, laid=laid,
                    **_declared(arrival))


def rom_calls(standing, until, drive_arm, carry, gpip):
    """THE ROM'S RUN from `standing` to `until` through the FDC model on `drive_arm` (B6's answered entries answered),
    STOPPED AT EACH PORTED ENTRY: `((Arrival, the ROM's call Slice), ...)` — every call the run makes, each run to its
    return and the run gone on from there."""
    calls = []
    while True:
        done = boot.run(standing, {until, *PORTED} | boot_late.ANSWERED, budget=boot_late.TIMEOUT_ARM_INSNS,
                        **boot_late.floppy_declared(boot_late.drives(drive_arm), carry, gpip))
        carry = boot_late.carried(done, carry)
        if done.stop == until:
            return tuple(calls)
        if done.stop in boot_late.ANSWERED:
            standing, _asked, _runs = boot_late.answered(done.machine)
            continue
        machine = done.machine
        returns_to = struct.unpack_from(">I", machine.ram, machine.registers["isp"])[0] & boot.BUS
        arrival = Arrival(machine, carry, returns_to, drive_arm, gpip)
        called = _call(arrival)
        calls.append((arrival, called))
        standing, carry = called.machine, boot_late.carried(called, carry)


@functools.cache
def b6_calls(machine, drive_arm=boot_late.CAPTURE_DRIVES):
    """Every call of a ported entry B6's ROM run makes on `machine` (WARM / COLD) and `drive_arm`."""
    return rom_calls(boot_late.start_of(machine), boot_late.SPAN[1], drive_arm, boot_late.entry_carry(machine),
                     boot_late.gpip_of(machine))


# THE ROWS (R-P4-3, the new kind): each probe call B6 makes — both drives — on COLD with each drive arm, and on WARM with
# the capture's drives (the driver does not read WARM against COLD; the arms are P3's, run on COLD).
ARRIVALS = {
    **{f"the probe of drive {'AB'[index]}:, {arm}, COLD": (boot.COLD, arm, index) for arm in boot_late.DRIVE_ARMS
       for index in (0, 1)},
    **{f"the probe of drive {'AB'[index]}:, {boot_late.CAPTURE_DRIVES}, WARM": (boot.WARM, boot_late.CAPTURE_DRIVES, index)
       for index in (0, 1)},
}


def arrival_of(name):
    machine, drive_arm, index = ARRIVALS[name]
    return b6_calls(machine, drive_arm)[index]


Shore = namedtuple("Shore", "slice own")


def the_rom_s(name):
    """The ROM's own call at `name`'s arrival: its whole run its own."""
    _arrival, called = arrival_of(name)
    return Shore(called, called.cycles)


def ours(name, code=None):
    """OUR call from the same machine, our driver laid (or `code` as its body), entered at the same ROM address — refused
    by name if it ran a cycle of the ROM's ported text; its own cycles every cycle in our spans."""
    arrival, _called = arrival_of(name)
    laid = pieces(code)
    called = _call(arrival, laid=boot.overlays(*laid))
    for lo, hi in NEVER_RUN:
        spent = emu.prof_cycles(lo, hi)
        if spent:
            raise boot.Refused(f"{name}: our call executed the ROM's ported text [{lo:#x}, {hi:#x}) — {spent} cycles of it")
    return Shore(called, sum(emu.prof_cycles(lo, hi) for lo, hi in our_spans(laid)))


# ---- WHAT IS HELD -------------------------------------------------------------------------------------------------------------
def frames(entry_sp):
    """The call's own dead frames: from the chain's floor (`boot_chain.FRAMES_APART_FROM`) to the SP it was entered at."""
    import boot_chain                   # (it imports this module)
    return boot_chain.FRAMES_APART_FROM, entry_sp


def _outside(ram, span):
    lo, hi = span
    return ram[:lo] + bytes(hi - lo) + ram[hi:]


def _stored_outside(runs, span):
    lo, hi = span
    return {at for start, length in runs for at in range(start, start + length) if not lo <= at < hi}


def differences(name, rom, mine):
    """Every surface our call `mine` differs from the ROM's `rom` on, by name (none: held equal)."""
    found = []
    one, other = rom.slice, mine.slice
    span = frames(arrival_of(name)[0].machine.registers["isp"])
    if other.stop != one.stop:
        found.append(f"stop: the ROM's {one.stop:#x}, ours {other.stop:#x}")
    theirs, yours = one.machine.registers, other.machine.registers
    registers = {register: (f"{theirs[register]:#x}", f"{yours[register]:#x}") for register in theirs
                 if theirs[register] != yours[register]}
    if registers:
        found.append(f"registers {registers} (the ROM's, ours)")
    rom_ram, our_ram = _outside(one.machine.ram, span), _outside(other.machine.ram, span)
    if rom_ram != our_ram:
        first = next(at for at, (a, b) in enumerate(zip(rom_ram, our_ram)) if a != b)
        found.append(f"ram, first at {first:#x}")
    if _stored_outside(one.stored, span) != _stored_outside(other.stored, span):
        apart = _stored_outside(one.stored, span) ^ _stored_outside(other.stored, span)
        found.append(f"stored: the addresses stored differ, first at {min(apart):#x}")
    for ledger in boot_late.LEDGERS:
        if getattr(one, ledger) != getattr(other, ledger):
            found.append(f"{ledger}: the ROM's and ours differ")
    if one.fdc_chip != other.fdc_chip:
        found.append("fdc_chip: the FDC/DMA chip the two shores left differs")
    return found


Priced = namedtuple("Priced", "the_rom_s ours own")


def priced(name):
    """The call at `name`'s arrival PRICED: both shores run, every held surface equal (refused by name otherwise); each
    shore's own cycles its whole call (ours: every cycle in our jump and our body, held to be the whole call)."""
    rom, mine = the_rom_s(name), ours(name)
    found = differences(name, rom, mine)
    assert not found, f"{name}: ours differs from the ROM's — {'; '.join(found)}"
    assert mine.own == mine.slice.cycles, f"{name}: ours spent {mine.slice.cycles - mine.own} cycles outside our driver"
    return Priced(rom.slice, mine.slice, (mine.own, rom.own))
