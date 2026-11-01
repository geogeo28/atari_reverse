r"""THE BOOT'S DISPLAY SLICE ON BOTH SHORES (boot B5, `test_boot_display.py`): the ROM's own `[$fc03e0, $fc0452)` against
OUR C (`src/boot/display/display.c`, `boot_display_entry`), run from one machine and held equal on every surface the C
can be held on — as B3's stretch is (`boot_hwinit.py`).

THE USER'S RULINGS THIS MODULE STANDS ON (2026-10-29, and R-B5-1 of 2026-10-31): D8 (the WARM and COLD machines, `boot.py`); D5 "Harness-local"
(the probe's bus error, `bus_error.Fault`: `aes_boot.THE_BLITTER_PROBE`); D9 "Stretch rows" (each arm priced on each
shore's own cycles, `bench/tier3.py`); "ROM-window overlay" and "Own link rule" (where our code lies, below). The blitter
itself stays DEFERRED: only the probe's answer is modelled — its access faulting (ABSENT) or a declared word read
(PRESENT); nothing the blitter would do beyond it. The orchestrator's standing calls: the sync wait, the probe, the
Line-A's set-up, the console's re-init and the cartridge's hooks are the ROM's on both shores, priced as the OS both
run (in neither column); the ROM addresses the C names are census obligations (`test_boot_rom_data.py`).

WHERE OUR CODE LIES: over a copy of the image's ROM window at `DISPLAY_LAID_AT` (`boot.overlaid`, A LABELLED STAGING),
linked there by its own rule (`build/bootdisplay/`) with every callee-saved register fixed. Held: the ROM's own runs are
the same with and without the overlay; a run of ours that spends a cycle in the ROM's slice is REFUSED BY NAME (the
false green).

THE ARMS (each A CASE'S DECLARATION, said in its label): the shifter's resolution byte (each of the mode bits' four
values), the monitor socket (GPIP bit 7 HIGH: colour; LOW: mono), the blitter ABSENT or PRESENT.

THE MONO ARM'S SYNC WAIT, ANSWERED (the user's ruling R-B5-1, 2026-10-31: "Answer it at entry", the R-B4-2 precedent; no
kit change). The wait (`$fc0e1a`) stores timer B's data register and then reads it back as a running count — 618 reads,
1 and then 617 equal — which no declaration of the kit's serves (measured: a list reads as STALE after the run's own
store, and is past the sequence pool's 256 bytes; a write-through byte reads the 240 stored for ever). ONLY THE POLL IS
ANSWERED, at ITS entry (`SYNC_POLL`, the first `move.b (a0),d0`), on both shores alike (`answered_poll`): the ROM runs
the wait's own head (A0, A1, timer B reset and stopped, its data register 240, event-count mode, D4 := 1 — each store
in the ordered ledger, every register its own) and its own tail (timer B reset, `jmp (a6)`); the answer writes only
what the 618 reads would: D0's low byte and D4's low byte the count the first poll waits for (D4's own, which the ROM's
`moveq #1,d4` laid), D3's low word $ffff (the `dbf` run out). UNPINNED BY NAME: the poll loop itself — its 618 reads
are on no ledger and its cycles on no shore.

WHAT IS HELD (`differences`): the stop; EVERY register (none differs: the C holds nothing in the callee-saved
registers, and the ROM's routines it calls leave the scratch as they leave the ROM's) — but A6 on the mono arm, each
shore's own link to the sync wait, MAPPED BACK EXACTLY (ours past our one `jmp $fc0e1a` for the ROM's `$fc0408`); the
megabyte — the one stack
longword our last call leaves under the entry's stack pointer, the return of the hooks' `jsr`, mapped back (`mapped_back`:
our `jmp $fc0452` for the ROM's `$fc0452`); the addresses stored; every ordered ledger (the hardware writes, the declared
reads, the modelled reads, the PSG's accesses); the faults. Instructions and cycles are the price, not a surface.
"""
import functools
import struct
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu

import aes_boot
import boot
import boot_hwinit
import layouts
import transcription

RECREATE = Path(__file__).resolve().parents[1]
DISPLAY_H = RECREATE / "include" / "boot" / "display.h"
HWINIT_H = RECREATE / "include" / "boot" / "hwinit.h"
HEAD_H = RECREATE / "include" / "boot" / "head.h"
LAUNCH_H = RECREATE / "include" / "boot" / "launch.h"
PRODUCT_DIRECTORY = RECREATE / "build" / "bootdisplay"
CONSTANTS = layouts.parse_constants((DISPLAY_H, HWINIT_H, HEAD_H))
RESET_ENTRY = layouts.parse_constants((LAUNCH_H,))["ROM_RESET_ENTRY"]     # what swv_vec is given
LONG_BYTES, WORD_BYTES = boot.LONG_BYTES, boot.WORD_BYTES

# ---- THE ROM'S SLICE -------------------------------------------------------------------------------------------------
SPAN = (boot.IKBD_RESET_DONE, boot.INTERRUPTS_OPENED)              # [$fc03e0, $fc0452)
SYNC_WAIT = CONSTANTS["ROM_SYNC_WAIT"]
LEA_PC_A6 = 0x4dfa                      # `lea d16(pc),a6`: the mono switch's link before `bra.w $fc0e1a`
MONO_LINK = 0xfc0400                    # ...where it lies


def _lea_pc_target(at):
    opcode, displacement = struct.unpack_from(">Hh", BASE_IMAGE, at)
    assert opcode == LEA_PC_A6, f"the ROM holds {opcode:#06x} at {at:#x}, not the mono switch's `lea d16(pc),a6`"
    return at + WORD_BYTES + displacement


SYNC_WAIT_RETURNS = _lea_pc_target(MONO_LINK)      # $fc0408: the ROM's own link, `move.b #2,$ffff8260`
# THE WAIT'S POLL (`test_boot_display.py` holds each to the ROM's text): the first `move.b (a0),d0` ...
SYNC_POLL = 0xfc0e3c
# ...to the `move.b #$10,(a1)` past its `dbf`: the 618 reads between, which the answer stands for (R-B5-1).
SYNC_POLL_END = 0xfc0e50
SYNC_WAIT_END = 0xfc0e56                # past its `jmp (a6)`
BYTE_MASK, WORD_MASK = 0xff, 0xffff
DBF_RUN_OUT = WORD_MASK                 # `dbf` ends with its counter's low word at -1
ANSWER_LABEL = ("R-B5-1 THE SYNC WAIT ($fc0e1a): ITS POLL ANSWERED AT {poll:#x} on both shores — D0.b and D4.b the "
                "count the first poll waits for (D4's, laid by the ROM's `moveq #1,d4`), D3.w $ffff (the `dbf` run "
                "out); the wait's own head and tail run")

# ---- OUR SIDE --------------------------------------------------------------------------------------------------------
ENTRY_SYMBOL = "boot_display_entry"
Product = namedtuple("Product", "base code symbols elf")


@functools.cache
def product():
    """`Product` of `build/bootdisplay/` — refused by name unless the entry lies at its laid address (`make bootdisplay`)."""
    binary, elf = PRODUCT_DIRECTORY / "display.bin", PRODUCT_DIRECTORY / "display.elf"
    assert binary.is_file() and elf.is_file(), f"{PRODUCT_DIRECTORY} is not built: `make bootdisplay`"
    symbols = {symbol.name: symbol.start for symbol in transcription.symbol_table(elf)}
    assert symbols.get(ENTRY_SYMBOL) == CONSTANTS["DISPLAY_LAID_AT"], (
        f"{elf}: `{ENTRY_SYMBOL}` lies at {symbols.get(ENTRY_SYMBOL)!r}, not DISPLAY_LAID_AT {CONSTANTS['DISPLAY_LAID_AT']:#x}")
    return Product(CONSTANTS["DISPLAY_LAID_AT"], binary.read_bytes(), symbols, elf)


def overlay(code=None):
    """THE STAGING our side runs on: the product (or `code`, a case's own bytes) over the ROM window (`boot.overlaid`)."""
    return boot.overlaid(product().base, product().code if code is None else code)


def our_span(laid=None):
    laid = laid or overlay()
    return laid.at, laid.at + len(laid.code)


JMP_ABSOLUTE_LONG = 0x4ef9
JMP_ABSOLUTE_LONG_BYTES = 6


def jumps_to(target, code=None):
    """Every address in our code holding `jmp (target).l` — read off the bytes, word-aligned."""
    code = product().code if code is None else code
    words = struct.pack(">HI", JMP_ABSOLUTE_LONG, target)
    return tuple(product().base + at for at in range(0, len(code) - len(words) + 1, WORD_BYTES)
                 if code[at:at + len(words)] == words)


# ---- THE MACHINES AND THE ARMS ---------------------------------------------------------------------------------------
MACHINES = boot_hwinit.ARMS                                         # WARM, COLD
COLOUR, MONO = "colour", "mono"
ABSENT, PRESENT = "blitter ABSENT", "blitter PRESENT"
RESOLUTIONS = {addrs.SHIFTER_MODE_LOW: "ST low", addrs.SHIFTER_MODE_MEDIUM: "ST medium",
               addrs.SHIFTER_MODE_HIGH: "ST high", CONSTANTS["SHIFTER_MODE_RESERVED"]: "the reserved mode 3"}
# THE SHIFTER'S RESOLUTION BYTE as declared: the mode bits under bits that are not the mode's (the `and.b #3` keeps the
# two), so a reconstruction that skipped the mask stores a byte that differs.
RESOLUTION_HIGH_BITS = 0xa4
# THE MONITOR SOCKET: GPIP's other bits a mix, bit 7 the arm's.
GPIP_OTHER_BITS = 0x35
GPIP_OF = {COLOUR: GPIP_OTHER_BITS | 1 << addrs.MFP_GPIP_MONOCHROME_BIT, MONO: GPIP_OTHER_BITS}
# ST MEDIUM's palette fix reads pen 15 and writes pen 3: pen 15's colour declared, distinct bytes.
PEN_15 = addrs.SHIFTER_PALETTE + CONSTANTS["LOW_FOREGROUND_PEN"] * addrs.PALETTE_ENTRY_BYTES
PEN_3 = addrs.SHIFTER_PALETTE + CONSTANTS["MEDIUM_FOREGROUND_PEN"] * addrs.PALETTE_ENTRY_BYTES
PEN_15_COLOUR = (0x05, 0x73)
# THE BLITTER PRESENT: the probe's `tst.w $ffff8a00` answered by the word declared there (its first halftone word).
BLITTER_WORD = aes_boot.BLITTER_REGISTERS & boot.BUS
BLITTER_WORD_BYTES = (0x5a, 0xc3)

Arm = namedtuple("Arm", "machine resolution monitor blitter")
ARM_LABEL = ("{machine}; A CASE'S DECLARATIONS: the shifter's resolution byte {byte:#04x} ({mode}), GPIP {gpip:#04x} "
             "(bit 7 {bit7}: a {monitor} monitor), {blitter}")
ARMS = tuple(Arm(machine, mode, monitor, blitter) for monitor in (COLOUR, MONO) for machine in MACHINES
             for mode in RESOLUTIONS for blitter in (ABSENT, PRESENT))
SLICES = {f"boot display B5, {arm.machine}, {arm.monitor}, {RESOLUTIONS[arm.resolution]}, {arm.blitter}": arm
          for arm in ARMS}


def resolution_byte(arm):
    return RESOLUTION_HIGH_BITS | arm.resolution


def declared(arm):
    """The arm's declarations: `boot.run`'s keywords."""
    io_seed = {addrs.SHIFTER_RESOLUTION: resolution_byte(arm), PEN_15: PEN_15_COLOUR[0], PEN_15 + 1: PEN_15_COLOUR[1]}
    if arm.blitter == PRESENT:
        io_seed.update({BLITTER_WORD: BLITTER_WORD_BYTES[0], BLITTER_WORD + 1: BLITTER_WORD_BYTES[1]})
    faults = (aes_boot.THE_BLITTER_PROBE,) if arm.blitter == ABSENT else ()
    return dict(io_seed=io_seed, hw_seed={addrs.MFP_GPIP: GPIP_OF[arm.monitor]}, faults=faults)


def label_of(arm):
    gpip = GPIP_OF[arm.monitor]
    label = ARM_LABEL.format(machine=arm.machine, byte=resolution_byte(arm), mode=RESOLUTIONS[arm.resolution],
                             gpip=gpip, bit7="HIGH" if gpip >> addrs.MFP_GPIP_MONOCHROME_BIT else "LOW",
                             monitor=arm.monitor, blitter=arm.blitter)
    return f"{label}; {ANSWER_LABEL.format(poll=SYNC_POLL)}" if arm.monitor == MONO else label


@functools.cache
def start_of(machine):
    """THE ROM'S OWN MACHINE AT `$fc03e0` on `machine` (WARM or COLD): where the ROM's B3 stretch leaves it."""
    return boot_hwinit.the_rom_s(machine, boot_hwinit.STRETCH_KIND).machine


def labelled(arm):
    machine = start_of(arm.machine)
    return machine._replace(label=f"{machine.label}; {label_of(arm)}")


# ---- THE TWO SHORES --------------------------------------------------------------------------------------------------
Shore = namedtuple("Shore", "slice own")
Shore.__doc__ = """One shore's run: the `boot.Slice` (its legs joined where the sync wait's poll was answered), and its OWN
cycles (the ROM's in its slice's span; ours in the overlay's) — read off each leg's profile."""


def _profiled(run):
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        return run()
    finally:
        emu.prof_enable(False)


def _vet_who_ran(label, ran, not_ran):
    """WHO RAN, off the profile just taken: no cycle in `not_ran` (ours that ran the ROM's slice would be measured equal
    on the ROM's instructions — the false green); `ran` the cycles in the span that should run, returned."""
    spent = emu.prof_cycles(*not_ran)
    if spent:
        raise boot.Refused(f"{label}: the run executed [{not_ran[0]:#x}, {not_ran[1]:#x}) — {spent} cycles of it")
    return emu.prof_cycles(*ran)


def answered_poll(machine):
    """R-B5-1: `machine` standing at the sync wait's poll, the poll ANSWERED — the registers its 618 reads leave (D0.b and
    D4.b the count D4 holds, D3.w the `dbf` run out), the run on at the `move.b #$10,(a1)` past it."""
    registers = dict(machine.registers)
    assert registers["pc"] == SYNC_POLL, f"the poll is answered at {SYNC_POLL:#x}, not {registers['pc']:#x}"
    count = registers["d4"] & BYTE_MASK
    registers.update(d0=registers["d0"] & ~BYTE_MASK | count,
                     d3=registers["d3"] & ~WORD_MASK | DBF_RUN_OUT, pc=SYNC_POLL_END)
    return machine._replace(registers=registers)


def _run(machine, until, arm, laid, own, not_ran):
    """`arm` run from `machine` to `until`, leg by leg — a leg stopped at the sync wait's poll continues from
    `answered_poll` — each leg profiled: `Shore` of the legs joined, its own cycles `own`'s summed."""
    legs, spent = [], 0
    while True:
        def leg():
            done = boot.run(machine, {until, SYNC_POLL}, laid=laid, **declared(arm))
            return done, _vet_who_ran(machine.label, own, not_ran) if not_ran else emu.prof_cycles(*own)
        done, cycles = leg() if laid else _profiled(leg)
        legs.append(done)
        spent += cycles
        if done.stop != SYNC_POLL or until == SYNC_POLL:
            break
        machine = answered_poll(done.machine)
    joined = legs[0]
    for later in legs[1:]:
        joined = boot_hwinit.joined(joined, later)
    return Shore(joined, spent)


def the_rom_s(arm, until=SPAN[1], laid=None):
    """The ROM's own slice of `arm` from its machine at `$fc03e0` to `until` (`laid`: with an overlay it must not reach —
    the ROM's shore with and without it)."""
    return _run(labelled(arm), until, arm, laid, SPAN, our_span(laid) if laid else None)


def our_side(arm, until=SPAN[1], code=None):
    """OUR slice of `arm` from the same machine, on its overlay (the product, or `code`), entered at our entry where the
    ROM's stands; refused by name if it ran a cycle of the ROM's slice."""
    laid = overlay(code)
    machine = boot.entered_at(labelled(arm), product().base)
    machine = machine._replace(label=f"{machine.label}; {laid.label}")
    shore = _run(machine, until, arm, laid, our_span(laid), SPAN)
    assert shore.own, f"{machine.label}: the run never executed our code"
    return shore


def our_sync_wait_return(code=None):
    """Where our C's link to the sync wait leads: past its one `jmp $fc0e1a` (the `lea 1f(pc),a6` before it)."""
    sites = jumps_to(SYNC_WAIT, code)
    assert len(sites) == 1, f"our code jumps to the sync wait from {len(sites)} sites"
    return sites[0] + JMP_ABSOLUTE_LONG_BYTES


# ---- WHAT IS HELD ------------------------------------------------------------------------------------------------------
SURFACES, LEDGERS = boot_hwinit.SURFACES, boot_hwinit.LEDGERS


def hooks_return_slot(arm):
    """`(lo, hi)`: the stack longword under the entry's stack pointer — every call of the slice's leaves its return there,
    the cartridge's hooks' the last."""
    top = start_of(arm.machine).registers["isp"]
    return top - LONG_BYTES, top


def mapped_back(ram, arm, code=None):
    """Our megabyte with the hooks' return mapped back: where it holds one of our `jmp $fc0452` (the C's tail, one per
    path), the ROM's `$fc0452` (its `bsr`'s return falls into it)."""
    lo, _hi = hooks_return_slot(arm)
    held = struct.unpack_from(">I", ram, lo)[0]
    if held not in jumps_to(SPAN[1], code):
        return ram
    mapped = bytearray(ram)
    struct.pack_into(">I", mapped, lo, SPAN[1])
    return bytes(mapped)


def mapped_registers(registers, code=None):
    """Our register file with A6 mapped back where it holds our link to the sync wait: the ROM's `$fc0408`."""
    if registers["a6"] != our_sync_wait_return(code):
        return registers
    return {**registers, "a6": SYNC_WAIT_RETURNS}


def differences(the_rom_s, ours, arm, code=None):
    """Every surface `ours` (a `boot.Slice`) differs from `the_rom_s` on, by name (none: held equal)."""
    found = []
    if ours.stop != the_rom_s.stop:
        found.append(f"stop: the ROM's {the_rom_s.stop:#x}, ours {ours.stop:#x}")
    theirs, mine = the_rom_s.machine.registers, mapped_registers(ours.machine.registers, code)
    registers = {name: (f"{theirs[name]:#x}", f"{mine[name]:#x}") for name in theirs if theirs[name] != mine[name]}
    if registers:
        found.append(f"registers {registers} (the ROM's, ours)")
    rom_ram, our_ram = the_rom_s.machine.ram, mapped_back(ours.machine.ram, arm, code)
    if our_ram != rom_ram:
        first = next(at for at, (one, other) in enumerate(zip(rom_ram, our_ram)) if one != other)
        found.append(f"ram, first at {first:#x}")
    if the_rom_s.stored != ours.stored:
        found.append("stored: the addresses stored differ")
    for surface in LEDGERS:
        if getattr(the_rom_s, surface) != getattr(ours, surface):
            found.append(f"{surface}: {len(getattr(the_rom_s, surface) or ())} against ours "
                         f"{len(getattr(ours, surface) or ())}")
    return found


# ---- ITS PRICE (ruling D9: each shore's own cycles) ---------------------------------------------------------------------
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """B5 measured on both shores: the two `boot.Slice`s, `own` (ours the overlay's cycles, the ROM's its
slice's) and `rest` (each run's other cycles: the ROM's routines both run), held equal."""


def priced(arm):
    """`arm` PRICED: both shores run, every held surface equal (refused by name otherwise)."""
    rom, ours = the_rom_s(arm), our_side(arm)
    found = differences(rom.slice, ours.slice, arm)
    assert not found, f"{name_of(arm)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (ours.slice.cycles - ours.own, rom.slice.cycles - rom.own)
    assert rest[0] == rest[1], f"{name_of(arm)}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(rom.slice, ours.slice, (ours.own, rom.own), rest[0])


def name_of(arm):
    return next(name for name, each in SLICES.items() if each == arm)
