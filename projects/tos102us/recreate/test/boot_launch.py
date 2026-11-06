r"""THE BOOT'S LAST SLICE ON BOTH SHORES (boot B4, `test_boot_launch.py`): the ROM's own `[$fc047a, gem_entry)` — its
AUTO runner `$fc0c4a` and the process that runner launches `$fc0cae` among it — and OURS: THE .S THAT SHIPS
(`src/boot/launch/launch.S`, the ROM's own bytes: ruling R-B4-1) and ITS C TWIN (`launch.c`, entered by
`launch_entry.S`; the `src/bios/isr.S` precedent) — run from THE MID-BOOT MACHINE to the shell's first instruction and held
equal on every surface the C can be held on; and the machine both reach held to THE PRE-INIT CAPTURE of the same disk.

THE USER'S RULINGS THIS MODULE STANDS ON: D8 (the MID-BOOT machine, `boot.midboot_machine`: Hatari's capture at
`$fc047a`, A LABELLED STAGING); D9 "Stretch rows" (each row priced on each shore's own cycles, `bench/tier3.py`);
"ROM-window overlay" and "Own link rule" (each product laid over a copy of the ROM window at its own address and linked
there by the Makefile's own rule, `build/bootlaunch/`) — 2026-10-29; and 2026-10-31: R-B4-1 "Byte-transcribed .S" (the
launch and the runner ship as the ROM's own bytes; the C stays as their twin, held, priced by nothing); R-B4-2 "Answer it
at its entry" (the clock's probe, `THE_CLOCK`); R-B4-3 "Accept all three" (DRIVE A: NEVER LOGGED IN; the floppy lower
driver's state pinned exactly at the END; the two pieces on a case's own pokes). The orchestrator's standing calls:
GEMDOS's init and the GEM entry stay the ROM's on both shores; the ROM's strings the slice reads ("PATH=",
"COMMAND.PRG", "\AUTO\*.PRG", the empty string) are read where they lie (TABLE obligations, `test_boot_rom_data.py`).

WHERE OUR CODE LIES: NOT IN RAM. An AUTO program's Pexec(0) clears the whole TPA (`$ca00..$f8000`, measured — the
bench blob's span with it) while the runner that called it is still running. Laid in the ROM window (`boot/launch.h`
says where each, and why), over bytes nothing of the slice runs or reads (held: the ROM's own slice is the same run with
and without each overlay) and never over the AES's text, where Tier 3's guard holds our runs to spend no cycle.

THE DEVICES: THE FLOPPY THROUGH THE KIT'S FDC/DMA MODEL (D4 P5a, ruling R-P5-1: `aes_boot.Floppy` retired here — no
driver entry is answered). GEMDOS's Getbpb, Mediach and Rwabs run as the ROM's own upper driver on both shores; below
it the LOWER driver is the ROM's on its shore and OURS on ours (`our_pieces`: laid beside the launch, R-P4-2's jumps);
below that the model, carried in from B6 (R-D4-2: `carry_at_the_mid_boot`), its ledger, chip and port A held. The
blitter probe's bus error, and one horizontal blank held pending (the AUTO process runs at mask 0: each shore takes the
blanks its runs allow, held equal). DRIVE A: NEVER LOGGED IN (R-B4-3) — at `$fc047a` GEMDOS has not read the disk yet
(the driver's record for drive A: is zero, held), so the first Getbpb — the ROM's own now — logs in the disk in the
drive; which is also why a disk OTHER than the capture's can be in the drive at the stop — the blank disk's only trace
is its boot sector in `$16da`, which that Getbpb reads again (held: the DESKTOP.INF and files disks reach THEIR OWN
pre-init captures, to the byte). (`NeverLoggedIn`, the device model's class for that, stays for B6's Floprd cross-check
alone.) And THE CLOCK (R-B4-2, `THE_CLOCK`): a program that runs makes GEMDOS resync its clock, whose probe is answered
at its entry.

THE ROWS (`SLICES`): THE LAUNCH from `$fc047a` to gem_entry on the three disks a pre-init capture booted with — its END
SURFACE that capture — and on a disk with one program and one with a program Pexec cannot load; THE AUTO RUNNER as a
stretch (`bsr $fc0c4a` to its return, on the ROM's own machine there) on four arms: no `\AUTO` folder, a folder with no
program, one program, a program Pexec cannot load. THE `_cmdload` ARM IS NOT A ROW, UNPINNED BY NAME: the boot reaches
it only where something set `$482` — a boot sector, a reset-resident program (D12), or a poke of the capture (a
staging beyond the ruled machines).

WHAT IS HELD (`differences`): the stop; the register file (the twin's runner rows but `NOT_HELD`); the megabyte outside
`preinit_snapshot.MASK` with OUR LINKED ADDRESSES mapped back to the ROM's (`linked`) — unmapped, the megabyte differs
at exactly those longwords; the addresses stored outside the mask; the FDC model's ledger, its chip and port A; every ordered
ledger; THE GEMDOS TRAPS IN ORDER, each with its arguments (`GEMDOS_ARGUMENT_BYTES`); the blanks taken; the clock's
answers. Instructions and cycles are the price, not a surface — but OUR OWN COST IS PINNED EXACTLY (`OUR_OWN_COST`).
"""
import functools
import random
import struct
import tempfile
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu

import accessory_disk
from boot_snapshot import differing_fields
import preinit_snapshot
import st_build

import aes_boot
import boot
import derived
import case
import layouts
import stopped_cpu
import transcription

RECREATE = Path(__file__).resolve().parents[1]
LAUNCH_H = RECREATE / "include" / "boot" / "launch.h"
PRODUCT_DIRECTORY = RECREATE / "build" / "bootlaunch"
PROCESS_H = RECREATE / "include" / "gemdos" / "process.h"
CONSTANTS = layouts.parse_constants((LAUNCH_H,))
PEXEC_STACK_ZERO_LONGS = layouts.parse_constants((PROCESS_H,))["PEXEC_STACK_ZERO_LONGS"]
DTA_NAME = layouts.parse_constants((RECREATE / "include" / "gemdos" / "fs.h",))["DTA_NAME"]
LAID_AT = CONSTANTS["LAUNCH_LAID_AT"]
RAM_BYTES = boot.RAM_BYTES
LONG_BYTES, WORD_BYTES = boot.LONG_BYTES, boot.WORD_BYTES
BUS = boot.BUS
GEM_ENTRY = aes_boot.GEM_ENTRY

# ---- THE ROM'S SPANS (each held to the ROM's own words by `test_boot_launch.py`) ------------------------------------------
LAUNCH_SPAN = (CONSTANTS["ROM_LAUNCH"], CONSTANTS["ROM_LAUNCH_END"])  # `tst.w _cmdload` .. past `jmp $fc0030`
AUTO_RUNNER = CONSTANTS["ROM_AUTO_RUNNER"]  # `lea <path>(pc),a0`: the runner, `bsr`'d from both arms
AUTO_PROCESS = 0xfc0cae                 # `clr.l -(sp)`: the process's first instruction, stored as its text
AUTO_RUNNER_SPAN = (AUTO_RUNNER, CONSTANTS["ROM_AUTO_RUNNER_END"])   # ...through the process's own `rts`
THE_ROM_S_SPANS = (LAUNCH_SPAN, AUTO_RUNNER_SPAN)
SHELL_ARM_CALLS_THE_RUNNER = 0xfc04a0   # `bsr $fc0c4a` in the GEM arm ($482 = 0)
SHELL_ARM_AUTO_RAN = 0xfc04a4           # ...and where it returns: `move.l #$fc0000,_sysbase`

# ---- OUR SIDE ----------------------------------------------------------------------------------------------------------
ENTRY_SYMBOL = "boot_launch_entry"
OUR_AUTO_RAN = "boot_launch_auto_ran"
OUR_AUTO_PROCESS = "boot_auto_process_entry"
OUR_RUNNER_CALL = "boot_launch_calls_the_runner"     # the GEM arm's call of the runner: the stretch's start
LAUNCH, AUTO_RUNNER_KIND = "launch", "AUTO runner"
# THE TWO PRODUCTS (ruling R-B4-1): THE .S, which ships and is priced, and its C TWIN, held on the same surfaces. Each
# defines the same symbols at its own laid address.
SHIPPED, TWIN = "the .S", "the C twin"
PRODUCTS = {SHIPPED: ("launch", "LAUNCH_LAID_AT"), TWIN: ("twin", "LAUNCH_TWIN_LAID_AT")}
Product = namedtuple("Product", "base code symbols elf")


@functools.cache
def product(which=SHIPPED):
    """`Product` of `build/bootlaunch/` — refused by name unless the entry lies at its laid address (`make bootlaunch`)."""
    stem, laid_at = PRODUCTS[which]
    binary, elf = PRODUCT_DIRECTORY / f"{stem}.bin", PRODUCT_DIRECTORY / f"{stem}.elf"
    assert binary.is_file() and elf.is_file(), f"{PRODUCT_DIRECTORY} is not built: `make bootlaunch`"
    symbols = {symbol.name: symbol.start for symbol in transcription.symbol_table(elf)}
    assert symbols.get(ENTRY_SYMBOL) == CONSTANTS[laid_at], (
        f"{elf}: `{ENTRY_SYMBOL}` lies at {symbols.get(ENTRY_SYMBOL)!r}, not {laid_at} {CONSTANTS[laid_at]:#x}")
    return Product(CONSTANTS[laid_at], binary.read_bytes(), symbols, elf)


def overlay(code=None, which=SHIPPED):
    """THE STAGING our side runs on: the product (or `code`, a case's own bytes) over the ROM window (`boot.overlaid`)."""
    return boot.overlaid(product(which).base, product(which).code if code is None else code)


def our_pieces(code=None, which=SHIPPED):
    """EVERYTHING OUR SIDE LAYS (D4 P5a, R-P5-1): the launch's overlay (`overlay`) and OUR LOWER FLOPPY DRIVER beside it —
    its body and the jump at each ROM entry it ports (`boot_floppy.pieces`, R-P4-2) — each its own labelled staging."""
    import boot_floppy
    return boot.overlays(overlay(code, which), *boot_floppy.pieces())


def never_run_on_ours():
    """THE ROM'S TEXT OUR SIDE MUST SPEND NO CYCLE IN: its launch and runner, and its lower driver's ported text past
    each jump (`boot_floppy.NEVER_RUN`) — ours that fell into it would be measured equal on the ROM's instructions."""
    import boot_floppy
    return (*THE_ROM_S_SPANS, *boot_floppy.NEVER_RUN)


def our_span(laid=None):
    laid = laid or overlay()
    return laid.at, laid.at + len(laid.code)


# OUR LINKED ADDRESSES, each where the ROM stores its own: `{name: (where, ours, the ROM's)}`, `where` a function of
# the machine the run left. THE AUTO BASEPAGE is p_run's where the runner returns (the process never terminated) and
# the shell's parent at gem_entry. Its initial stack (`gemdos/process.h`'s child stack, from its p_hitpa down) holds
# two more copies until the shell's launch builds its own over them: Pexec's copy of its text, and the return PC of
# the frame Super leaves on the process's own stack.
OUR_SUPER_RETURN = "boot_auto_process_supervisor"
AUTO_SUPER_RETURN = 0xfc0cb6            # the ROM's `addq.w #6,sp` after Super's `trap #1`
EXCEPTION_FRAME_BYTES = 6               # the status word and the return PC
ENTRY_STACK_LONGS = 2                   # a process Pexec enters stands two longwords under p_hitpa: its basepage at 4(sp)
TEXT_COPY_DEPTH = (ENTRY_STACK_LONGS + PEXEC_STACK_ZERO_LONGS + 1) * LONG_BYTES      # Pexec's copy of p_tbase
SUPER_RETURN_DEPTH = (ENTRY_STACK_LONGS * LONG_BYTES + CONSTANTS["SUPER_FRAME_BYTES"] + EXCEPTION_FRAME_BYTES
                      - WORD_BYTES)     # Super's frame under its two words: its PC past the status word


def _auto_basepage_at_gem_entry(ram):
    shell = case.long_in(ram, addrs.GEMDOS_P_RUN) & BUS
    return case.long_in(ram, shell + addrs.BASEPAGE_PARENT) & BUS


def _auto_basepage_at_its_return(ram):
    return case.long_in(ram, addrs.GEMDOS_P_RUN) & BUS


def _top_of(basepage_at):
    return lambda ram: case.long_in(ram, basepage_at(ram) + addrs.BASEPAGE_HITPA) & BUS


def linked(kind, which=SHIPPED):
    """THE LINKED LONGWORDS where `kind`'s run ends (the module's docstring), of `which` product."""
    symbols = product(which).symbols
    process_entry, return_site = symbols[OUR_AUTO_PROCESS], symbols[OUR_AUTO_RAN]
    if kind == LAUNCH:
        basepage = _auto_basepage_at_gem_entry
        return {
            "the runner's return": (lambda ram: CONSTANTS["AUTO_RETURN"], return_site, SHELL_ARM_AUTO_RAN),
            "the AUTO process's text": (lambda ram: basepage(ram) + addrs.BASEPAGE_TBASE, process_entry, AUTO_PROCESS),
        }
    basepage, top = _auto_basepage_at_its_return, _top_of(_auto_basepage_at_its_return)
    return {
        "the runner's return": (lambda ram: CONSTANTS["AUTO_RETURN"], return_site, SHELL_ARM_AUTO_RAN),
        "the AUTO process's text": (lambda ram: basepage(ram) + addrs.BASEPAGE_TBASE, process_entry, AUTO_PROCESS),
        "Pexec's copy of its text on its stack": (lambda ram: top(ram) - TEXT_COPY_DEPTH, process_entry, AUTO_PROCESS),
        "Super's return on its stack": (lambda ram: top(ram) - SUPER_RETURN_DEPTH, symbols[OUR_SUPER_RETURN],
                                        AUTO_SUPER_RETURN),
    }


# THE TWO COPIES ON THE PROCESS'S STACK ARE GONE where a program ran: its Pexec(0) built the program's stack from the same
# p_hitpa over them (each shore's — the megabyte's compare holds what lies there instead).
ON_THE_PROCESS_STACK = ("Pexec's copy of its text on its stack", "Super's return on its stack")


def mapped_back(ram, links):
    """`ram` with each linked longword holding OUR address given the ROM's — refused by name where it holds neither,
    but a copy on the process's stack a program's own stack lies over (`ON_THE_PROCESS_STACK`)."""
    out = bytearray(ram)
    for name, (where, ours, the_rom_s) in links.items():
        at = where(ram)
        held = case.long_in(out, at)
        if name in ON_THE_PROCESS_STACK and held not in (ours, the_rom_s):
            continue
        assert held in (ours, the_rom_s), f"{name} ({at:#x}) holds {held:#x}: neither ours {ours:#x} nor the ROM's"
        struct.pack_into(">I", out, at, the_rom_s)
    return bytes(out)


# ---- THE DISKS -------------------------------------------------------------------------------------------------------
# Built by `tools/accessory_disk.py`'s own method (`st_build.build`, its `\AUTO` folder; a program assembled and wrapped
# by `accessory_disk.build`): the test AUTO program `test/acc/autoprg.S` (Pterm0), and a file named a program that
# Pexec cannot load (no `$601a` header: EPLFMT) before it.
AUTO_PROGRAM_SOURCE = RECREATE / "test" / "acc" / "autoprg.S"
AUTO_PROGRAM_NAME, NOT_A_PROGRAM_NAME = "X.PRG", "BAD.PRG"
NOT_A_PROGRAM = b"NOT A PROGRAM: NO $601A HEADER\r\n"
PRG_MAGIC = b"\x60\x1a"


@functools.cache
def auto_program():
    """The test AUTO program's file: `Pterm0` and nothing else."""
    return accessory_disk.build(AUTO_PROGRAM_SOURCE.read_text(), accessory_disk.LINK.read_text(),
                                accessory_disk.WRAPPER.read_text()).file


@functools.cache
def auto_disk(*names):
    """A blank disk with `names` in its `\\AUTO` folder, in that order (the program, or the file that is none)."""
    files = {AUTO_PROGRAM_NAME: auto_program(), NOT_A_PROGRAM_NAME: NOT_A_PROGRAM}
    with tempfile.TemporaryDirectory() as work:
        placed = []
        for name in names:
            (Path(work) / name).write_bytes(files[name])
            placed.append((name, Path(work) / name))
        return st_build.build(Path(work) / "disk.st", (), auto_files=placed).path.read_bytes()


Disk = namedtuple("Disk", "label image capture")
Disk.__doc__ = """A disk the slice is run with: its `label` (said in every case and row), the `image`, and the pre-init
capture made with it in the drive from power-on (a function), or None where none was made."""

BLANK, INF, FILES, NO_PROGRAM, ONE_PROGRAM, PEXEC_FAILS = (
    "BLANK", "DESKTOP.INF", "FILES", "NO PROGRAM", "ONE PROGRAM", "PEXEC FAILS")
DISKS = {
    BLANK: lambda: Disk("the blank disk, the capture's own (no \\AUTO)", aes_boot.blank_disk(), aes_boot.preinit),
    INF: lambda: Disk("the DESKTOP.INF disk (no \\AUTO)", aes_boot.inf_disk_of(), aes_boot.inf_preinit),
    FILES: lambda: Disk("the files disk (\\AUTO holds no program)", aes_boot.files_disk_of(), aes_boot.files_preinit),
    ONE_PROGRAM: lambda: Disk("a disk with \\AUTO\\X.PRG (Pterm0)", auto_disk(AUTO_PROGRAM_NAME), None),
    PEXEC_FAILS: lambda: Disk("a disk with \\AUTO\\BAD.PRG (named a program, no program: Pexec fails)",
                              auto_disk(NOT_A_PROGRAM_NAME), None),
}
DISKS[NO_PROGRAM] = DISKS[FILES]
DISK_LABEL = ("{label} in drive A: at the mid-boot stop — DRIVE A: NEVER LOGGED IN (its record zero there; the "
              "first Getbpb logs this disk in)")


@functools.cache
def disk(name):
    return DISKS[name]()


# ---- THE DEVICE CLASS: DRIVE A: NEVER LOGGED IN ---------------------------------------------------------------------------
class NeverLoggedIn(aes_boot.Floppy):
    """`aes_boot.Floppy` over a machine whose driver has NEVER LOGGED IN drive A: — its record ALL ZERO, or refused by
    name — so the disk in the drive is whatever the first Getbpb reads (the model's `_getbpb`, drive B:'s first log-in's
    arm). A machine whose record holds a disk is the parent's: the disk it logged in, vetted."""

    def _vet_it_is_the_disk_the_machine_logged_in(self):
        record = bytes(self._memory[self.record:self.record + aes_boot.FLOPPY_BPB_RECORD_BYTES])
        if any(record):
            super()._vet_it_is_the_disk_the_machine_logged_in()


# ---- THE GEMDOS TRAP LEDGER ----------------------------------------------------------------------------------------------
# Every `trap #1` arrival, in order, as `(function, its argument bytes)`: read at GEMDOS's entry (the machine's own
# vector) off the caller's stack — the supervisor's past the exception frame, else the user's. The bytes each function
# takes are named; a trap of any other is refused by name (the ledger would hold the caller's stack beyond its frame).
GEMDOS_ARGUMENT_BYTES = {
    addrs.GEMDOS_SUPER_FN: 4, CONSTANTS["GEMDOS_MSHRINK_FN"]: 10, addrs.GEMDOS_FSETDTA_FN: 4, addrs.GEMDOS_FSFIRST_FN: 6,
    addrs.GEMDOS_FSNEXT_FN: 0, addrs.GEMDOS_PEXEC_FN: 14, addrs.GEM_SELECTOR_PTERM: 0,
}


def gemdos_entry(ram):
    return case.long_in(ram, addrs.VECTOR_TRAP_GEMDOS) & BUS


def _trap_read(memory, sp):
    """The trap the run stands at GEMDOS's entry of: `(function, argument bytes)`."""
    status = case.word_in(memory, sp)
    words = sp + EXCEPTION_FRAME_BYTES if status & stopped_cpu.SR_SUPERVISOR else stopped_cpu.register("usp")
    function = case.word_in(memory, words)
    if function not in GEMDOS_ARGUMENT_BYTES:
        raise boot.Refused(f"a GEMDOS call {function:#x} this ledger names no arguments for")
    at = words + WORD_BYTES
    return function, bytes(memory[at:at + GEMDOS_ARGUMENT_BYTES[function]])


# ---- THE CLOCK, ANSWERED AT ITS PROBE'S ENTRY (the user's ruling R-B4-2, 2026-10-31: "Answer it at its entry") ------------
# A program that RUNS (Pterm0's after a load that succeeds) makes GEMDOS resync its clock ($fc5092), which probes the
# Mega ST's RP5C15 ($fc4c0c): stores to two of its registers, then reads them back — a read of a register the run itself
# stored to, the one form the kit's I/O map has not got ("a register a store does not reach", `test/gemdos_process.py`).
# So the probe is ANSWERED AT ITS ENTRY on both shores, as the floppy is at its driver's (labelled: `THE_CLOCK`), with
# what the ROM's own probe returns on THE CAPTURE MACHINE: a plain ST (`boot_snapshot.MACHINE_ARGUMENTS`, `--machine
# st`), no RP5C15 — its read-back misses the pattern and it returns CARRY SET ($fc4c3e `ori #1,ccr` / `rts`). Its
# scratch (D0, D1, A0) is not laid: neither caller reads it past its `bcs` ($fc5096 to an `rts`, $fc4c46 to `moveq
# #-1,d0`), and the read-back D1 would hold is the bus's, unknown on the capture machine.
CLOCK_PROBE = addrs.BIOS_RTC_PROBE
THE_CLOCK = ("R-B4-2 THE CLOCK: the RP5C15's probe ($fc4c0c) answered at its entry — carry set, no clock, what the "
             "ROM's own probe returns on the capture's plain ST")
SR_CARRY = 0x0001


class AnsweringTheClock(aes_boot._Run):
    """`aes_boot`'s run with ONE MORE ENTRY ANSWERED: the clock's probe (above) — its return taken, carry set. Each answer
    counted (`clock_answers`), and `carry` the flag it hands back (the negative's lever)."""

    def __init__(self, *arguments, carry, **named):
        super().__init__(*arguments, **named)
        self.clock_answers, self._carry = 0, carry

    def _stops(self):
        return super()._stops() | {CLOCK_PROBE}

    def _stopped(self, pc, sp):
        if pc != CLOCK_PROBE:
            return super()._stopped(pc, sp)
        self.clock_answers += 1
        status = stopped_cpu.register("sr")
        stopped_cpu.set_register("sr", status | SR_CARRY if self._carry else status & ~SR_CARRY)
        stopped_cpu.set_register("pc", case.long_in(self._memory, sp) & BUS)
        stopped_cpu.set_register("a7", sp + LONG_BYTES)
        return False


# ---- THE FLOPPY THROUGH THE FDC MODEL (D4 P5a, ruling R-P5-1 "Sliced P5a->P5c") -----------------------------------------
# THE UPPER DRIVER IS NO LONGER ANSWERED HERE: GEMDOS's Getbpb, Mediach and Rwabs run as the ROM's own code, on both shores,
# down to the LOWER driver — the ROM's on its shore, OURS on ours (laid beside the launch: `our_pieces`) — and below it the
# kit's FDC/DMA model (R-D4-1), armed for the run with the capture's bays: the disk in drive A: lent READ-ONLY (B4 writes
# nothing: a write would be refused by the model, by name), drive B: present and empty. THE CARRY INTO `$fc047a` (R-D4-2,
# "derived, never declared"): PSG port A and the chip as the ROM's own B6 leaves them on the COLD chain's capture arm — one
# value on all eight chains (measured, `test_boot_chain.py`). The chain hands its own B6's carry instead (`carry=`).
class NoFloppyAnswer:
    """No driver entry answered: every floppy call of the run reaches the FDC model (`aes_boot._Run`'s device seat)."""
    served_at = {}


NO_ANSWER = NoFloppyAnswer()


@functools.cache
def carry_at_the_mid_boot():
    """THE CARRY INTO `$fc047a` (R-D4-2): `boot_late.Carry` (port A, the chip) the ROM's own B6 leaves on the COLD chain."""
    import boot_chain                   # (it imports this module: the carry is read off its ROM chain, lazily)
    chain = boot_chain.Chain(boot.COLD, boot_chain.CAPTURE_ARM[boot.COLD])
    return boot_chain.the_rom_s(chain)[-2].carry


def bays(disk_image):
    """The FDC model's two bays for a run of the slice: `disk_image` in drive A: (read-only), drive B: as the capture's."""
    import boot_late
    return emu.FdcDrive(bytes(disk_image)), boot_late.drives(boot_late.CAPTURE_DRIVES).drive_b


def gpip_at_the_mid_boot():
    """GPIP's other bits as the COLD capture arm declares them (its bit 5 the model's while armed, R-D4-3)."""
    import boot_late
    return boot_late.gpip_of(boot.COLD)


def driver_spans(laid=None):
    """Where the lower floppy driver runs on a shore: the ROM's own text (on ours only the jumps laid at its entries may
    spend a cycle there) and, where laid, our body."""
    import boot_floppy
    body = boot_floppy.product()
    return (boot_floppy.LOWER_DRIVER, (body.base, body.base + len(body.code))) if laid else (boot_floppy.LOWER_DRIVER,)


# ---- THE RUN -------------------------------------------------------------------------------------------------------------
Launch = namedtuple("Launch", "ram registers stop instructions cycles own driver fdc_events fdc_chip port_a blanks gemdos "
                              "io_reads hardware_reads hardware_writes stored clock")
Launch.__doc__ = """One run of the slice: the megabyte it left, the CPU's `registers` there, the `stop` arrived at, its
`instructions` and `cycles` (the run's whole), `own` (its cycles in `spans`: the shore's own code), `driver` (its cycles in
the lower floppy driver: the ROM's text, and our body where laid), the FDC model's ordered ledger `fdc_events`, the chip it
left (`fdc_chip`) and PSG port A after the run (`port_a`), the horizontal `blanks` taken, the `gemdos` ledger, the ordered
ledgers and the RAM `stored` (runs), and how many times the CLOCK's probe was answered at its entry (`clock`)."""
LAUNCH_INSNS = 400_000                  # the budget: the longest arm (two programs) is ~77,000 instructions


def carry_of(launch):
    """The carry `launch` hands the run after it (R-D4-2): `boot_late.Carry(port A, the chip)`."""
    import boot_late
    return boot_late.Carry(launch.port_a, launch.fdc_chip)


def _port_a_after(before):
    for kind, register, value in emu.psg_events():
        if kind == emu.os_map.OS_PSG_EVENT_WRITE and register == addrs.PSG_PORT_A:
            before = value
    return before


def fdc_seeds(carry, gpip):
    """`aes_boot._Run`'s declarations for a run through the FDC model: port A as `carry` holds it, GPIP's other bits."""
    return {"psg_seed": {addrs.PSG_PORT_A: carry.port_a}, "hw_seed": {addrs.MFP_GPIP: gpip}}


def fdc_left(carry):
    """WHAT THE RUN JUST MADE LEFT OF THE FLOPPY, read while the model is armed: `(its ordered ledger, the model's refusals,
    the chip — None where refused — and PSG port A after it, from `carry`'s)`."""
    events, causes = tuple(emu.fdc_events()), emu.fdc_causes()
    return events, causes, None if causes else emu.fdc_state(), _port_a_after(carry.port_a)


def run(machine, disk_image, until, spans, laid=None, budget=LAUNCH_INSNS, clock_carry=True, carry=None, gpip=None):
    """THE SLICE RUN from `machine` (its PC, its whole register file) with `disk_image` in drive A: — THE FLOPPY THROUGH THE
    FDC MODEL, no driver entry answered (`carry`: port A and the chip it starts from, `carry_at_the_mid_boot()` by default;
    `gpip`: GPIP's other bits, the COLD arm's by default) — to its first arrival at `until`, profiled: `own` its cycles in
    `spans`. `laid`: an `Overlay`, or several (`boot.overlays`), laid over a copy of the image for this run. Refused by
    name: a store at `$0..$7`, a saturated write ledger, anything the kit's vet or the FDC model refuses. THE CLOCK's probe
    is answered at its entry (`clock_carry`: the flag it hands back). Returns the `Launch` and `elsewhere`: the run's
    cycles in every span the who-ran checks read (`never_run_on_ours`, and each piece laid), read inside the run."""
    carry = carry_at_the_mid_boot() if carry is None else carry
    gpip = gpip_at_the_mid_boot() if gpip is None else gpip
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = machine.ram
    for piece in boot.pieces_of(laid) if laid else ():
        memory[piece.at:piece.at + len(piece.code)] = piece.code
    trap = gemdos_entry(machine.ram)
    the_run = AnsweringTheClock(memory, NO_ANSWER, budget, until=until, observing={trap: ("gemdos", _trap_read)},
                                carry=clock_carry, seeds=fdc_seeds(carry, gpip))
    drive_a, drive_b = bays(disk_image)
    driver = driver_spans(laid)
    aes_boot.aes_event.vet_the_profile_is_free("a boot launch run")
    emu.fdc_arm(drive_a, drive_b, chip=carry.chip)
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        result = the_run.to_an_idle(machine.registers, aes_boot.io_seed_of(machine))
        registers = stopped_cpu.registers_now()
        writes, truncated = emu.bench_writes(memory)
        ledgers = (tuple(emu.io_events()), tuple(emu.hw_events()), tuple(emu.hw_writes()))
        fdc_events, causes, chip, port_a = fdc_left(carry)
        own = sum(emu.prof_cycles(lo, hi) for lo, hi in spans)
        driver_cycles = sum(emu.prof_cycles(lo, hi) for lo, hi in driver)
        elsewhere = {span: emu.prof_cycles(*span) for span in (*never_run_on_ours(), *_spans_of(laid))}
    finally:
        emu.prof_enable(False)
        emu.fdc_disarm()
        stopped_cpu.CPU.m68k_set_irq(aes_boot.NO_INTERRUPT)
        emu.bench_abort()
    if causes:
        raise boot.Refused(f"{machine.label}: " + "; ".join(causes))
    aes_boot._vet_nothing_stored_under_the_rom_s_shadow(machine.ram, memory, writes, machine.label)
    if truncated:
        raise boot.Refused(f"{machine.label}: the run's write ledger saturated — what it stored is not known")
    boot._vetted(machine, {until})
    launch = Launch(bytes(memory[:RAM_BYTES]), registers, registers["pc"], result["ninsns"], result["cycles"], own,
                    driver_cycles, fdc_events, chip, port_a, the_run.blanks,
                    tuple(read for _name, read in the_run.observed), *ledgers, the_run.stored(writes),
                    the_run.clock_answers)
    return launch, elsewhere


# ---- THE CARRY INTO A PRE-INIT CAPTURE (D4 P5b, ruling R-P5-2 "Launch on its own disk") ----------------------------------------
# A capture stands at gem_entry with no FDC or PSG state of Hatari's in it, so what an AES boot through the model starts from is
# DERIVED, never declared (R-D4-2): the ROM's own B4 launch ON THE CAPTURE'S OWN DISK, from the mid-boot capture with B6's
# carry, to gem_entry. One carry for every capture would not do: the blank chain's chip on the files capture (whose driver
# record says track 1) sends the boot's first read through the recalibrate arm, which Hatari never took (measured, P5 e7).
# KEPT (review RP5b's REQ-4), by the mid-boot machine's content and the disk's: a booted machine already kept is then served
# with its carry and RUNS NOTHING — the launch this makes is profiled, and a caller holding the profile is never refused
# (nor its tallies reset) by a boot it asked beforehand.
@derived.kept
def carry_at_gem_entry(midboot, disk_image):
    """THE CARRY AT gem_entry of a capture booted with `disk_image` (bytes), from the mid-boot machine `midboot`
    (`boot.midboot_machine()`): `boot_late.Carry` the ROM's launch on that disk leaves."""
    aes_boot.aes_event.vet_the_profile_is_free("the carry into a pre-init capture")
    launch, _elsewhere = run(midboot, disk_image, GEM_ENTRY, ())
    return carry_of(launch)


def _vet_who_ran(label, elsewhere, ran, not_ran):
    """WHO RAN, off the run's profile: every span of `not_ran` zero cycles (OURS that ran the ROM's own text would be
    measured equal on the ROM's instructions — the false green), and some cycles in `ran`."""
    for span in not_ran:
        assert not elsewhere.get(span), f"{label}: the run executed [{span[0]:#x}, {span[1]:#x}) — {elsewhere[span]} cycles"
    assert all(elsewhere.get(span) for span in ran), f"{label}: the run never executed {ran}"


# ---- THE MACHINES -----------------------------------------------------------------------------------------------------
SliceOf = namedtuple("SliceOf", "kind disk")
CAPTURED = (BLANK, INF, FILES)         # the disks a pre-init capture booted with: the launch's END SURFACE is it
AUTO_ARMS = (BLANK, NO_PROGRAM, ONE_PROGRAM, PEXEC_FAILS)
SLICES = {**{f"boot launch B4, {name}": SliceOf(LAUNCH, name) for name in (*CAPTURED, ONE_PROGRAM, PEXEC_FAILS)},
          **{f"boot AUTO runner B4, {name}": SliceOf(AUTO_RUNNER_KIND, name) for name in AUTO_ARMS}}


def labelled(machine, disk_name):
    return machine._replace(label=f"{machine.label}; " + DISK_LABEL.format(label=disk(disk_name).label))


def start_pc(the_slice):
    """Where `the_slice` begins on the ROM's shore: the capture's stop for the launch, the `bsr` for the runner."""
    return boot.MIDBOOT if the_slice.kind == LAUNCH else SHELL_ARM_CALLS_THE_RUNNER


@functools.cache
def start_of(the_slice):
    """THE ROM'S OWN MACHINE where `the_slice` begins: the MID-BOOT capture for the launch; for the runner, the ROM's
    own slice from it to its `bsr $fc0c4a` (the `_cmdload` test, two instructions)."""
    machine = labelled(boot.midboot_machine(), the_slice.disk)
    if the_slice.kind == LAUNCH:
        return machine
    return boot.run(machine, {start_pc(the_slice)}).machine


def stop_of(the_slice, ours, which=SHIPPED):
    if the_slice.kind == LAUNCH:
        return GEM_ENTRY
    return product(which).symbols[OUR_AUTO_RAN] if ours else SHELL_ARM_AUTO_RAN


def the_rom_s(the_slice, laid=None):
    """The ROM's own slice (`laid`: overlays it must not reach — the ROM's shore with and without them)."""
    machine = start_of(the_slice)
    launch, elsewhere = run(machine, disk(the_slice.disk).image, stop_of(the_slice, False), THE_ROM_S_SPANS, laid=laid)
    _vet_who_ran(machine.label, elsewhere, ran=THE_ROM_S_SPANS, not_ran=_spans_of(laid))
    return launch


def _spans_of(laid):
    return tuple((piece.at, piece.at + len(piece.code)) for piece in boot.pieces_of(laid)) if laid else ()


def our_entry(the_slice, which=SHIPPED):
    symbols = product(which).symbols
    return symbols[ENTRY_SYMBOL] if the_slice.kind == LAUNCH else symbols[OUR_RUNNER_CALL]


def our_side(the_slice, code=None, which=SHIPPED):
    """OUR slice — of `which` product — from the same machine, on its overlay (the product, or `code`), entered at our
    instruction where the ROM's stands; refused by name if it ran a cycle of the ROM's own spans."""
    laid = our_pieces(code, which)
    machine = boot.entered_at(start_of(the_slice), our_entry(the_slice, which))
    machine = machine._replace(label=f"{machine.label}; {which}; {boot.label_of(laid)}")
    launch, elsewhere = run(machine, disk(the_slice.disk).image, stop_of(the_slice, True, which), (our_span(laid[0]),),
                            laid=laid)
    _vet_who_ran(machine.label, elsewhere, ran=(our_span(laid[0]),), not_ran=never_run_on_ours())
    return launch


# ---- WHAT IS HELD -------------------------------------------------------------------------------------------------------
# THE .S IS THE ROM'S INSTRUCTIONS: every register held, its frames the ROM's depth. THE C TWIN: at gem_entry GEMDOS has
# laid every register for the shell — all held; AT THE RUNNER'S RETURN, EXACTLY the registers that differ, each dead by
# gem_entry (`continued`: noise in them changes nothing of the ROM's run on to it): D1, A0
# and A1, GCC's scratch against the ROM's leftovers; D7, the ROM's count for its own stack trick ($fc0ce6 `moveq
# #8,d7` / `moveq #2,d7` then `adda.w d7,sp` after two traps), which the C has no use for; and A2, where a program
# was found — the ROM's copy loop's end ($fc0d04 `movea.l $988,a2`), which our C keeps as its caller's.
NOT_HELD = {SHIPPED: {LAUNCH: (), AUTO_RUNNER_KIND: ()},
            TWIN: {LAUNCH: (), AUTO_RUNNER_KIND: ("d1", "d7", "a0", "a1", "a2")}}
# ...AND ONE LONGWORD OF THE AUTO BASEPAGE: the address of the frame GEMDOS keeps for the process's last trap (+$7c),
# which lies in the process's own stack (the pre-init mask's span). The twin stands deeper there by the C's frame, as
# much as the arm's last trap says — pinned, not masked; the launch's Pexec(4) writes its own over it (equal at
# gem_entry). The .S stands where the ROM's does.
OUR_AUTO_FRAME_DEEPER = {SHIPPED: {addrs.GEMDOS_FSFIRST_FN: 0, addrs.GEMDOS_FSNEXT_FN: 0},
                         TWIN: {addrs.GEMDOS_FSFIRST_FN: 14, addrs.GEMDOS_FSNEXT_FN: 18}}


def last_search_of(launch):
    """The process's last search: Fsfirst where it found nothing, else Fsnext — off the GEMDOS ledger."""
    return [function for function, _arguments in launch.gemdos
            if function in (addrs.GEMDOS_FSFIRST_FN, addrs.GEMDOS_FSNEXT_FN)][-1]


def frame_pointer_at(ram):
    return _auto_basepage_at_its_return(ram) + addrs.BASEPAGE_SAVED_FRAME


def masked(ram):
    return preinit_snapshot.masked(ram)


def _outside_the_mask(runs):
    masked_spans = [(lo, lo + size) for lo, size, _why in preinit_snapshot.MASK]
    return tuple(sorted({at for start, length in runs for at in range(start, start + length)
                         if not any(lo <= at < hi for lo, hi in masked_spans)}))


def _frame_pointer_held(rom, ours, found, which=SHIPPED):
    """The AUTO process's last frame pointer: ours exactly OUR_AUTO_FRAME_DEEPER below the ROM's — then laid as the
    ROM's in a copy of ours, for the megabyte's compare."""
    at, deeper = frame_pointer_at(rom.ram), OUR_AUTO_FRAME_DEEPER[which][last_search_of(rom)]
    held, theirs = case.long_in(ours.ram, at), case.long_in(rom.ram, at)
    if held != theirs - deeper:
        found.append(f"the AUTO process's frame pointer ({at:#x}): ours {held:#x}, the ROM's {theirs:#x} - {deeper}")
    ram = bytearray(ours.ram)
    struct.pack_into(">I", ram, at, theirs)
    return bytes(ram)


def differences(rom, ours, kind, links=None, which=SHIPPED):
    """What `ours` — of `which` product — differs from `rom` in, by surface: `[]` where every held surface is equal (the
    module's docstring). `links`: the linked longwords to map back (`linked`) — None maps none (the negative)."""
    found = []
    stops = (GEM_ENTRY, GEM_ENTRY) if kind == LAUNCH else (product(which).symbols[OUR_AUTO_RAN], SHELL_ARM_AUTO_RAN)
    if (ours.stop, rom.stop) != stops:
        found.append(f"the stop: ours {ours.stop:#x}, the ROM's {rom.stop:#x}")
    for name in boot.REGISTER_NAMES:
        if name != "pc" and name not in NOT_HELD[which][kind] and ours.registers[name] != rom.registers[name]:
            found.append(f"the register {name}: ours {ours.registers[name]:#x}, the ROM's {rom.registers[name]:#x}")
    ram = _frame_pointer_held(rom, ours, found, which) if kind == AUTO_RUNNER_KIND else ours.ram
    ram = mapped_back(ram, links) if links else ram
    differing = differing_fields(masked(ram), masked(rom.ram))
    if differing:
        found.append("the megabyte outside the pre-init mask at " + ", ".join(f"{at:#x}+{n}" for at, n in differing[:8]))
    if _outside_the_mask(ours.stored) != _outside_the_mask(rom.stored):
        found.append("the addresses stored outside the mask")
    for surface in ("fdc_events", "fdc_chip", "port_a", "blanks", "gemdos", "io_reads", "hardware_reads", "hardware_writes",
                    "clock"):
        if getattr(ours, surface) != getattr(rom, surface):
            found.append(f"the {surface}")
    return found


# ---- THE DEAD CLASSES AT THE RUNNER'S RETURN, PROVED: the ROM's own run on to gem_entry ------------------------------------
NOISE_SEED = 0xb4


def machine_of(launch, start):
    """The `BootMachine` a run left: `start`'s name, io and label, the run's megabyte and registers."""
    return start._replace(ram=launch.ram, registers=dict(launch.registers))


def dead_at_the_runner_s_return(machine):
    """THE SPANS OF THE RAM the runner's row does not hold as they lie: its frame pointer, and the two copies on the
    process's stack (held mapped, and dead: the shell's launch builds its own stack over them)."""
    top = _top_of(_auto_basepage_at_its_return)(machine.ram)
    return tuple((at, at + LONG_BYTES) for at in (frame_pointer_at(machine.ram), top - TEXT_COPY_DEPTH,
                                                   top - SUPER_RETURN_DEPTH))


def noised(machine, registers, spans, seed=NOISE_SEED):
    """`machine` with NOISE in `registers` and in the RAM's `spans`."""
    generator = random.Random(seed)
    noisy = {name: value ^ generator.randrange(1, 1 << 32) if name in registers else value
             for name, value in machine.registers.items()}
    return machine._replace(ram=aes_boot.noise_over(machine.ram, spans, seed), registers=noisy)


def continued(machine, disk_name, carry=None):
    """The ROM's own launch from `machine` (standing where the runner returned) to gem_entry — `carry` the FDC model's
    (`carry_of` the run that left `machine`; the mid-boot's by default)."""
    return run(machine, disk(disk_name).image, GEM_ENTRY, THE_ROM_S_SPANS, carry=carry)[0]


# ---- THE END SURFACE: THE PRE-INIT CAPTURE OF THE SAME DISK -----------------------------------------------------------------
# What the oracle's run of the launch reaches against what Hatari's boot reached: EQUAL in every register and EVERY BYTE
# outside the pre-init mask (D4 P5a). Until P5a the device model answered at the driver's entries and did not advance the
# lower driver's own state below them — its transaction record, the registers it saves, its two drives' records
# ($fc1c48 `movem.l d3-d7/a3-a6,$a28`, `st $a04`, `lea $a4c/$a50,a1`) — and the run differed from the capture in 22-23 of
# those bytes, pinned exactly. With the upper driver run and the lower one through the FDC model, they are the capture's.
FLOPPY_LOWER_DRIVER_STATE = (0xa04, 0xa54)


def against_the_capture(launch, capture, links=None):
    """`(registers differing, RAM runs differing outside the mask)` of `launch` against the pre-init `capture`."""
    ram = mapped_back(launch.ram, links) if links else launch.ram
    registers = tuple(name for name in boot.REGISTER_NAMES if launch.registers[name] != capture.registers[name])
    return registers, tuple(differing_fields(masked(ram), masked(capture.ram)))


# ---- THE PRICE (D9: each shore on its own cycles) ----------------------------------------------------------------------------
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """One row measured on both shores: the two `Launch`es, `own` (ours the overlay's cycles, the ROM's its
spans' — each shore's own) and `rest` (each run's other cycles but the lower floppy driver's: GEMDOS, the BIOS and the
upper floppy driver both run), held equal. THE LOWER DRIVER (D4 P5a) is each shore's own — ours laid beside the launch,
the ROM's its text — and is priced in NEITHER column here (ruling R-P5-4: its natural calls are no rows of their own; its
cost shows in the chain rows): `Launch.driver` on each shore, taken out of the rest."""


def name_of(the_slice):
    return next(name for name, each in SLICES.items() if each == the_slice)


def priced(the_slice):
    """`the_slice` PRICED: both shores run, every held surface equal (refused by name otherwise)."""
    return priced_pair(the_slice, the_rom_s(the_slice), our_side(the_slice))


def priced_pair(the_slice, rom, ours, which=SHIPPED):
    """...the two shores' runs of `the_slice` (ours of `which` product) PRICED — the one place a row's price is made, the
    battery's and tier 3's: every held surface equal and the rest equal (refused by name otherwise)."""
    found = differences(rom, ours, the_slice.kind, linked(the_slice.kind, which), which)
    assert not found, f"{name_of(the_slice)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (ours.cycles - ours.own - ours.driver, rom.cycles - rom.own - rom.driver)
    assert rest[0] == rest[1], f"{name_of(the_slice)}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(rom, ours, (ours.own, rom.own), rest[0])


# ---- TWO PIECES HELD AS FUNCTION ROWS ARE: ON A CASE'S OWN INPUTS -------------------------------------------------------------
# Inputs the mid-boot machine holds one value of (`_bootdev` 0, the boot drive mounted), poked as any function row's
# case pokes its inputs — A CASE'S POKES, said in the label, not a machine of the boot's.
ENVIRONMENT_SPAN = (0xfc04ae, 0xfc04d0)  # `lea <template>(pc),a0` .. the letter stored: the environment laid
STACK_SPAN_BYTES = 0x40                 # below the call's frame: what the callee pushes (its own saves), not a store
CASE_POKES = "A CASE'S POKES: {what} (the mid-boot machine's own value is {held})"


def poked(machine, at, data, what):
    ram = bytearray(machine.ram)
    ram[at:at + len(data)] = data
    label = CASE_POKES.format(what=what, held=bytes(machine.ram[at:at + len(data)]).hex())
    return machine._replace(ram=bytes(ram), label=f"{machine.label}; {label}")


def environment_of(bootdev, which=SHIPPED):
    """`(the ROM's, ours)`: the environment each lays at BOOT_ENVIRONMENT from the mid-boot machine with `_bootdev`
    the word `bootdev` — the ROM's span run in place; the .S's the same span where it lays it; the twin's
    `environment_laid` called with the image base 0, returning to where the ROM's span ends. Each the RAM over the
    environment, and the stores outside the stack."""
    machine = poked(start_of(SliceOf(LAUNCH, BLANK)), CONSTANTS["SYSVAR_BOOTDEV"], struct.pack(">H", bootdev),
                    f"_bootdev {bootdev:#06x}")
    the_rom_s = boot.run(boot.entered_at(machine, ENVIRONMENT_SPAN[0]), {ENVIRONMENT_SPAN[1]})
    sp = machine.registers["isp"] - 2 * LONG_BYTES
    if which == SHIPPED:
        laid_at = product(which).base - boot.MIDBOOT
        ours = boot.run(boot.entered_at(machine, ENVIRONMENT_SPAN[0] + laid_at), {ENVIRONMENT_SPAN[1] + laid_at},
                        laid=overlay(which=which))
    else:
        framed = poked(machine, sp, struct.pack(">II", ENVIRONMENT_SPAN[1], 0), "the call's frame")
        ours = boot.run(boot.entered_at(framed, product(which).symbols["environment_laid"], isp=sp),
                        {ENVIRONMENT_SPAN[1]}, laid=overlay(which=which))
    _vet_who_ran(machine.label, {span: emu.prof_cycles(*span) for span in (*THE_ROM_S_SPANS, our_span(overlay(which=which)))},
                 ran=(our_span(overlay(which=which)),), not_ran=THE_ROM_S_SPANS)     # (`boot.run` leaves its profile)
    lo = CONSTANTS["BOOT_ENVIRONMENT"]
    hi = lo + CONSTANTS["ROM_COMMAND_PRG"] - CONSTANTS["ROM_ENVIRONMENT_TEMPLATE"]
    stack = (sp - STACK_SPAN_BYTES, machine.registers["isp"])
    return tuple((bytes(each.machine.ram[lo:hi]), [run for run in each.stored if not stack[0] <= run[0] < stack[1]])
                 for each in (the_rom_s, ours))


def runner_without_its_drive(which=SHIPPED):
    """`(the ROM's, ours)`: the AUTO runner from the ROM's machine at its `bsr` with `_drvbits` 0 — no drive mounted —
    to its return: each `Launch`."""
    the_slice = SliceOf(AUTO_RUNNER_KIND, BLANK)
    machine = poked(start_of(the_slice), addrs.SYSVAR_DRVBITS, bytes(LONG_BYTES), "_drvbits 0 — no drive mounted")
    image = disk(BLANK).image
    the_rom_s = run(machine, image, SHELL_ARM_AUTO_RAN, THE_ROM_S_SPANS)[0]
    laid, symbols = our_pieces(which=which), product(which).symbols
    ours, elsewhere = run(boot.entered_at(machine, symbols[OUR_RUNNER_CALL]), image, symbols[OUR_AUTO_RAN],
                          (our_span(laid[0]),), laid=laid)
    _vet_who_ran(machine.label, elsewhere, ran=(our_span(laid[0]),), not_ran=never_run_on_ours())
    return the_rom_s, ours
