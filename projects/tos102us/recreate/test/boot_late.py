r"""THE BOOT'S LATE SLICE ON BOTH SHORES (boot B6, `test_boot_late.py`): the ROM's own `[$fc0452, $fc047a)` — with the
routines it calls that this slice ports with it: GEMDOS's buffers `$fc4a9e`, the clock's date `$fc4be8`, the floppy's
boot `$fc053c`, the ACSI's `$fc0558` and the reset-resident scan `$fc0e56` — against OUR C (`src/boot/late/late.c`,
`boot_late_entry`), run from one machine and held equal on every surface the C can be held on, as B5's slice is
(`boot_display.py`); and the machine both reach held to THE MID-BOOT CAPTURE (`build/midboot.bin`) under its own MASK.

THE USER'S RULINGS THIS MODULE STANDS ON: D8 (the WARM and COLD machines, `boot.py`), D9 "Stretch rows" (each arm priced
on each shore's own cycles, `bench/tier3.py`), "ROM-window overlay" and "Own link rule" (where our code lies, below) —
2026-10-29; R-B4-2 "Answer it at its entry" (the clock's probe) — and D3 (2026-10-31): "NO kit interrupt source. The
waiting routines are ANSWERED AT THEIR ENTRIES on both shores, labelled". The slice opens the interrupts (`move
#$2300,sr`) and NONE IS DELIVERED inside a run (said on every label). And D4 (2026-11-01, R-D4-1..4): THE FLOPPY RUNS AS
THE ROM'S THROUGH THE KIT'S FDC/DMA MODEL (a zero-time WD1772 + DMA, TRAP_MODEL.md "Phase 17") — hdv_init's drive probe
`$fc173a` and hdv_boot's Floprd `$fc1782` are no longer answered; the capture's blank disk in drive A: (read-only), drive
B: connected and empty (the capture's), or one of three arms (`DRIVE_ARMS`); PSG port A and the FDC chip CARRIED from
the ROM's own runs, leg to leg (R-D4-2); GPIP's other bits B5's arm's, its bit 5 the model's; the model's ORDERED LEDGER
and the chip it leaves held exactly between the shores (R-D4-3). The orchestrator's standing calls: GEMDOS's init and its
Dsetdrv stay the ROM's on both shores (OS both run); so do the cartridge's hooks (D2: the port reads 0) and the floppy
driver's hdv_boot / hdv_init (the F-upper driver, unported) and its lower driver, each called in place.

THE ANSWERS, AT TWO ENTRIES, ON BOTH SHORES ALIKE (`answered`), each value pinned to the ROM's text or to the capture
(the ROM's own run on Hatari), each counted in the run's ANSWER LEDGER with what it was asked:
  * THE ACSI PROBE `$fc0586` (D3, "no device") — what the ROM's own probe leaves when the controller never answers: D0
    and D1 -1, A5/A6 the DMA's two registers, flock's byte cleared, Z clear (`ACSI_NO_DEVICE`).
  * THE CLOCK'S PROBE `$fc4c0c` (R-B4-2) — carry set: no RP5C15 on the capture's plain ST.
AND THREE ENTRIES OBSERVED, run as the ROM's: the cartridge's hooks (the init bit each arrival hands them: with no
cartridge — D2 — nothing else reads it), GEMDOS's init and its Dsetdrv (with the drive word) — each arrival in the
ledger, so the calls' order and Dsetdrv's argument are held. UNPINNED BY NAME: `_bootdev` other than 0 (a hard disk's
boot: the ACSI answers "no device"), so the drive Dsetdrv makes current is 0 in every run.
THE FLOPPY'S WAITS, ONCE ANSWERED (the drive probe, D3's; Floprd, D4's), NOW RUN: they are instruction-count loops on GPIP
bit 5, which the zero-time model ends at the first poll — or, on a drive with no disk or no drive at all, never: the
ROM's own count-down times out and forces the command (the arms). WHAT THE MID-BOOT CAPTURE HOLDS THAT NO SHORE DOES is
then D1 alone (`END_APART`).

WHERE OUR CODE LIES: over a copy of the image's ROM window at `LATE_LAID_AT` (`boot.overlaid`, A LABELLED STAGING),
linked there by its own rule (`build/bootlate/`) with every callee-saved register fixed. Held: the ROM's own runs are
the same with and without the overlay; a run of ours that spends a cycle in the ROM's slice or its ported callees is
REFUSED BY NAME (the false green).

WHAT IS HELD (`differences`): the stop; EVERY register; the megabyte and the addresses stored OUTSIDE THE BIOS STACK'S
DEAD FRAMES (the mid-boot capture's own MASK field, `[$745a, $755a)`: below the stack's top at the stop, where the two
shores' frames lie at different depths — our C calls GEMDOS's init from no frame, the ROM's from `$fc4a9e`'s `link`);
every ordered ledger (the hardware writes, the declared reads, the modelled reads, the PSG's accesses, the FDC model's
transactions); the chip the FDC model left; the faults; the answers in order with what each was asked. Instructions and cycles are the price, not a surface.
"""
import functools
import struct
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu

import midboot_snapshot

import aes_boot
import boot
import boot_display
import boot_hwinit
import boot_launch
import case
import layouts
import stopped_cpu
import transcription

RECREATE = Path(__file__).resolve().parents[1]
INCLUDE_BOOT = RECREATE / "include" / "boot"
PRODUCT_DIRECTORY = RECREATE / "build" / "bootlate"
CONSTANTS = layouts.parse_constants(tuple(INCLUDE_BOOT / f"{name}.h" for name in ("late", "head", "sysvars", "hwinit",
                                                                                  "display", "launch")))
LONG_BYTES, WORD_BYTES = boot.LONG_BYTES, boot.WORD_BYTES
BUS = boot.BUS
RAM_BYTES = boot.RAM_BYTES

# ---- THE ROM'S SLICE AND THE ROUTINES IT PORTS WITH IT (each held to the ROM's text by `test_boot_late.py`) ------------
SPAN = (boot.INTERRUPTS_OPENED, boot.MIDBOOT)                       # [$fc0452, $fc047a)
GEMDOS_BUFFERS = (0xfc4a9e, 0xfc4b28)   # `link a6,#-4` .. its `rts`
CLOCK_DATE = (0xfc4be8, 0xfc4c0c)       # `bsr $fc4c0c` .. the `rts` after `moveq #-1,d0`
FLOPPY_BOOT = (0xfc053c, 0xfc0558)      # `moveq #3,d0` .. its `rts`
ACSI_BOOT = (0xfc0558, 0xfc0586)        # `moveq #0,d7` .. its `rts`
RESIDENT_SCAN = (0xfc0e56, 0xfc0e96)    # `movea.l phystop,a0` .. its `rts`
THE_ROM_S_SPANS = (SPAN, GEMDOS_BUFFERS, CLOCK_DATE, FLOPPY_BOOT, ACSI_BOOT, RESIDENT_SCAN)

# ---- THE FLOPPY'S LOWER DRIVER, NO LONGER ANSWERED (ruling D4, R-D4-3): run as the ROM's through the kit's model ---------
DRIVE_PROBE = 0xfc173a                  # hdv_init's `jsr` ($fc0f82): the drive's select, its restore, the FDC's waits
DRIVE_PROBE_CALL = 0xfc0f82
DRIVE_PROBE_DEVICE_AT = 12              # `tst.w 12(sp)` ($fc1740): the drive the probe asks after
DRIVE_STATUS_LOAD = 0xfc0f96            # hdv_init's `adda.l #<the drives' status words>,a0`, the drive * 2 in A0
FLOPRD_CALL = 0xfc15aa                  # hdv_boot's `jsr` of the driver's Floprd, the boot sector to `_dskbufp`
FLOPRD_ENTRY = 0xfc1782                 # held to the machine's own XBIOS table (`aes_boot._xbios_entry`) by the battery

# ---- THE FDC'S BYTES the batteries read the model's ledger in (WD1772 datasheet; the lower driver's own operands) -------
WD1772_RESTORE = 0x03                   # `$00 | 3`: restore, the step rate `seekrate` (3) or'd in ($fc1da0)
WD1772_SEEK = 0x13                      # `$10 | 3`: seek, no verify ($fc1d2e, and every exit's seek to the current track)
WD1772_SEEK_VERIFY = 0x17               # `$14 | 3`: seek with verify ($fc1d7a)
WD1772_READ_SECTOR = 0x80               # Floprd's `move.w #$80` command
WD1772_SEEK_ERROR = 0xb0                # type I status: motor on, spun up, seek error (no TR00)
FDC_DRIVE_SHIFT = 8                     # a ledger COMMAND's second word: drive << 8 | side
DMA_BLOCK = (0xff8600, 0xff8610)        # the DMA chip's decode (kit fdc.h FDC_BLOCK_LO / FDC_BLOCK_HI)
GPIP_INTRQ = 0x20                       # GPIP bit 5: the FDC's interrupt line, active low (kit fdc.h FDC_GPIP_INTRQ)

# ---- ANSWERED ENTRIES ---------------------------------------------------------------------------------------------------
ACSI_PROBE = CONSTANTS["ROM_ACSI_READ_BOOT_SECTOR"]
CLOCK_PROBE = boot_launch.CLOCK_PROBE
# THE ACSI PROBE'S "NO DEVICE": its first command byte never acknowledged — `$fc062a` polls GPIP bit 5 until `_hz_200`
# passes its count, then `moveq #-1,d1`; `$fc0606` `moveq #-1,d0`; `move.w #$80,(a6)`; `tst.b d0` (Z clear, N set);
# `sf flock` ($fc060e: the byte `st` set at $fc0592). A5 and A6 the DMA's data and mode registers it `lea`s first.
ACSI_A6, ACSI_A5 = 0xffff8606, 0xffff8604
ACSI_NO_DEVICE = {"d0": 0xffffffff, "d1": 0xffffffff, "a5": ACSI_A5, "a6": ACSI_A6}
# THE FLAGS IT LEAVES: `tst.b d0` over -1 sets N and clears Z V C; X the last instruction that writes it leaves — the
# `add.l _hz_200,d1` at `$fc062a` (ACSI_WAIT_ADD), which carries out of no long (the tick plus ten), so X clear.
CCR_XNZVC, CCR_N = 0x001f, 0x0008
ACSI_WAIT_ADD = 0xfc062a
SR_CARRY = boot_launch.SR_CARRY
TARGET_MASK = 0xff                      # the ACSI's target: D7's low byte
ANSWER_LABEL = ("D3 THE WAITING ROUTINES ANSWERED AT THEIR ENTRIES on both shores (no interrupt is delivered: the slice "
                "opens them and none arrives): the ACSI probe ($fc0586) — no device; R-B4-2 THE CLOCK ($fc4c0c) — carry "
                "set. D4 (R-D4-1..3): THE FLOPPY RUN AS THE ROM'S THROUGH THE KIT'S FDC/DMA MODEL — hdv_init's drive "
                "probe and hdv_boot's Floprd unanswered; a zero-time WD1772 + DMA, the capture's blank disk lent "
                "read-only in drive A:; the chip and PSG port A carried from the ROM's own runs")

# ---- THE FDC/DMA MODEL'S DRIVES (R-D4-1, R-D4-3): the capture's own, and the three arms the ROM's lower driver takes ------
# THE CAPTURE'S (Hatari's default machine): the blank disk in drive A:, drive B: connected and EMPTY — its probe succeeds
# (a restore needs no index pulse once A:'s spin-up turned the motor on), so both drives count, as the capture's do.
Drives = namedtuple("Drives", "name drive_a drive_b")
CAPTURE_DRIVES = "the capture's drives"
B_ABSENT, A_ABSENT, A_EMPTY = "drive B: absent", "no drive at all", "drive A: empty"
DRIVE_ARMS = (CAPTURE_DRIVES, B_ABSENT, A_ABSENT, A_EMPTY)


@functools.cache
def drives(arm=CAPTURE_DRIVES):
    """The two bays of `arm` (`DRIVE_ARMS`): THE CAPTURE'S; DRIVE B: ABSENT (its restore steps 255 times and fails: one
    drive counted); NO DRIVE AT ALL (A:'s spin-up never ends — the ROM's own count-down times out, `$D0` forces it);
    DRIVE A: EMPTY, B: absent (A:'s spin-up and hdv_boot's seek-verify hang on no index pulse: the ROM's own timeouts).
    The disk is THE CAPTURE'S BLANK DISK, lent read-only (`bytes`): a write to it is refused by the model."""
    disk = bytes(the_disk())
    bays = {CAPTURE_DRIVES: (emu.FdcDrive(disk), emu.FdcDrive(None)),
            B_ABSENT: (emu.FdcDrive(disk), emu.FDC_ABSENT),
            A_ABSENT: (emu.FDC_ABSENT, emu.FDC_ABSENT),
            A_EMPTY: (emu.FdcDrive(None), emu.FDC_ABSENT)}
    return Drives(arm, *bays[arm])


# THE ARMS' BUDGETS: an arm whose waits time out spends the ROM's own count-down in instructions (measured: the drive A:
# empty arm ~5.8 M on the ROM's shore) — over a slice's default budget.
TIMEOUT_ARM_INSNS = 12_000_000

# ---- OUR SIDE --------------------------------------------------------------------------------------------------------------
ENTRY_SYMBOL = "boot_late_entry"
Product = namedtuple("Product", "base code symbols elf")


@functools.cache
def product():
    """`Product` of `build/bootlate/` — refused by name unless the entry lies at its laid address (`make bootlate`)."""
    binary, elf = PRODUCT_DIRECTORY / "late.bin", PRODUCT_DIRECTORY / "late.elf"
    assert binary.is_file() and elf.is_file(), f"{PRODUCT_DIRECTORY} is not built: `make bootlate`"
    symbols = {symbol.name: symbol.start for symbol in transcription.symbol_table(elf)}
    assert symbols.get(ENTRY_SYMBOL) == CONSTANTS["LATE_LAID_AT"], (
        f"{elf}: `{ENTRY_SYMBOL}` lies at {symbols.get(ENTRY_SYMBOL)!r}, not LATE_LAID_AT {CONSTANTS['LATE_LAID_AT']:#x}")
    return Product(CONSTANTS["LATE_LAID_AT"], binary.read_bytes(), symbols, elf)


def overlay(code=None):
    """THE STAGING our side runs on: the product (or `code`, a case's own bytes) over the ROM window (`boot.overlaid`)."""
    return boot.overlaid(product().base, product().code if code is None else code)


def our_span(laid=None):
    laid = laid or overlay()
    return laid.at, laid.at + len(laid.code)


def _spans_of(laid):
    return tuple((piece.at, piece.at + len(piece.code)) for piece in boot.pieces_of(laid))


# ---- THE MACHINES ------------------------------------------------------------------------------------------------------
MACHINES = boot_display.MACHINES                                    # WARM, COLD
# WHERE EACH STARTS: the ROM's own machine at $fc0452, where the ROM's B5 slice leaves it on the capture's display — a
# colour monitor, ST low, no blitter (the capture's plain ST). The slice reads none of the display's state.
DISPLAY_ARM = {machine: boot_display.Arm(machine, addrs.SHIFTER_MODE_LOW, boot_display.COLOUR, boot_display.ABSENT)
               for machine in MACHINES}
SLICES = {f"boot late B6, {machine}": machine for machine in MACHINES}


@functools.cache
def start_of(machine):
    """THE ROM'S OWN MACHINE AT `$fc0452` on `machine` (WARM or COLD): where the ROM's B5 slice leaves it."""
    arm = DISPLAY_ARM[machine]
    started = boot_display.the_rom_s(arm).slice.machine
    return started._replace(label=f"{started.label}; {boot_display.label_of(arm)}; {ANSWER_LABEL}")


@functools.cache
def the_disk():
    """THE CAPTURE'S OWN DISK: the blank one, in drive A: from power-on (`boot.MIDBOOT_LABEL`)."""
    return aes_boot.blank_disk()


def gpip_of(machine):
    """GPIP's byte as the slice's machine declares it (B5's arm's: the monitor socket's bit 7 and the other bits'
    mix) — its bit 5 the FDC model's while armed (R-D4-3)."""
    return boot_display.GPIP_OF[DISPLAY_ARM[machine].monitor]


@functools.cache
def port_a_at_start(machine):
    """PSG PORT A AT `$fc0452` on `machine`, FROM THE ROM'S OWN RUNS (R-D4-2): the head's store, carried through B3's own
    read-modify-writes (`boot_chain`'s chained ROM boot) — not B3's declared seed, which is B3's battery's alone."""
    import boot_chain                   # (it imports this module: the carry is read off its ROM chain, lazily)
    return boot_chain.rom_port_a_entering_b6(boot_chain.Chain(machine, DISPLAY_ARM[machine]))


# ---- THE ANSWERS -------------------------------------------------------------------------------------------------------
def _returned(registers, ram, sp):
    """The answered routine's `rts`: the PC its caller's call pushed, the stack above it."""
    return {**registers, "pc": case.long_in(ram, sp) & BUS, "isp": sp + LONG_BYTES}


def answered(machine):
    """`machine` standing at an answered entry, ANSWERED: `(the machine past the routine's return, the ledger entry, the
    RAM runs the answer laid)`."""
    registers, ram = dict(machine.registers), bytearray(machine.ram)
    pc, sp = registers["pc"], registers["isp"]
    laid = ()
    if pc == ACSI_PROBE:
        registers.update(ACSI_NO_DEVICE, sr=registers["sr"] & ~CCR_XNZVC | CCR_N)
        ram[addrs.SYSVAR_FLOCK] = 0
        laid = ((addrs.SYSVAR_FLOCK, b"\0"),)
        asked = ("the ACSI probe", registers["d7"] & TARGET_MASK)
    elif pc == CLOCK_PROBE:
        registers["sr"] |= SR_CARRY
        asked = ("the clock's probe",)
    else:
        raise boot.Refused(f"{machine.label}: {pc:#x} is no answered entry of this slice")
    left = machine._replace(ram=bytes(ram), registers=_returned(registers, ram, sp))
    return left, asked, tuple((at, len(data)) for at, data in laid)


ANSWERED = frozenset({ACSI_PROBE, CLOCK_PROBE})
# ...AND ONE ENTRY OBSERVED, NOT ANSWERED: the cartridge's hooks, run as the ROM's, their init bit (D0's low word) put
# in the ledger at each arrival — with no cartridge (D2: the port reads 0) the bit is read by nothing, so the ledger is
# the one surface that holds it (measured: a hook bit mutated survived every other surface).
CARTRIDGE_HOOKS = CONSTANTS["ROM_CARTRIDGE_HOOKS"]
# ...AND GEMDOS's TWO ENTRIES THE SLICE CALLS, observed the same way (review RB6's F2: moved before the hooks or after the
# clock, or Dsetdrv handed another word, the calls survived every other surface): its init, and Dsetdrv with the drive
# word Alcyon's call hands it at 4(sp).
GEMDOS_INIT = CONSTANTS["ROM_GEMDOS_INIT"]
DSETDRV = addrs.GEMDOS_DSETDRV
DSETDRV_DRIVE_AT = 4
OBSERVED = frozenset({CARTRIDGE_HOOKS, GEMDOS_INIT, DSETDRV})
OBSERVED_NAMES = ("the cartridge's hooks", "GEMDOS's init", "Dsetdrv")
WORD_MASK = 0xffff


def observed(machine):
    """The ledger entry of `machine` standing at an observed entry: what it hands the routine."""
    registers = machine.registers
    if registers["pc"] == CARTRIDGE_HOOKS:
        return ("the cartridge's hooks", registers["d0"] & WORD_MASK)
    if registers["pc"] == DSETDRV:
        return ("Dsetdrv", case.word_in(machine.ram, registers["isp"] + DSETDRV_DRIVE_AT))
    return ("GEMDOS's init",)

# ---- THE FLOPRD CROSS-CHECK: the model's read of the blank disk against `aes_boot.Floppy`'s, one machine ---------------
FloprdCheck = namedtuple("FloprdCheck", "asked laid served model_d0 served_d0")
FloprdCheck.__doc__ = """hdv_boot's Floprd on the ROM's shore, at its entry: what it `asked` (`aes_boot.Floppy`'s call record), the
RAM runs the device model `laid` and what it `served` (D0); and what the ROM's own Floprd, run on through the FDC model to
its return, left at those same runs (`model_d0`, and `laid` read back off the machine: `FloprdCheck.model_bytes`)."""


def floprd_cross_check(machine, drive_arm=CAPTURE_DRIVES):
    """THE ROM'S OWN FLOPRD THROUGH THE FDC MODEL against `aes_boot.Floppy`'s answer (the one B6 retired, R-D4-3), from
    the one machine standing at Floprd's entry (`$fc1782`, the boot sector to `_dskbufp`): `(FloprdCheck, the bytes the
    model's run left at each laid run, the machine the ROM's Floprd returned — so a caller reads its D0 off the run
    itself)`. One call at CHS 0/0/1 (image offset 0): it does not exercise the track / side mapping."""
    carry, drive_arm, gpip = entry_carry(machine), drives(drive_arm), gpip_of(machine)
    budget = _budget(drive_arm.name)
    standing = start_of(machine)
    while True:
        done = boot.run(standing, {FLOPRD_ENTRY} | ANSWERED, budget=budget, **floppy_declared(drive_arm, carry, gpip))
        carry = carried(done, carry)
        if done.stop == FLOPRD_ENTRY:
            break
        standing, _asked, _runs = answered(done.machine)
    at_entry = done.machine
    memory = bytearray(BASE_IMAGE)
    memory[:RAM_BYTES] = at_entry.ram
    floppy = boot_launch.NeverLoggedIn(memory, the_disk())
    served, returns_to = floppy.served(FLOPRD_ENTRY, at_entry.registers["isp"])
    laid = floppy.laid_by_the_last_call()
    returned = boot.run(at_entry, {returns_to}, budget=budget, **floppy_declared(drive_arm, carry, gpip))
    ram = returned.machine.ram
    check = FloprdCheck(floppy.calls[-1], tuple((at, len(data)) for at, data in laid), dict(laid),
                        returned.machine.registers["d0"], served & aes_boot.LONG_MASK)
    return check, {at: ram[at:at + length] for at, length in check.laid}, returned.machine


# ---- THE TWO SHORES --------------------------------------------------------------------------------------------------------
Shore = namedtuple("Shore", "slice own answers also", defaults=(0,))
Shore.__doc__ = """One shore's run: the `boot.Slice` (its legs joined where an entry was answered, the answers' own stores
among `stored`), its OWN cycles (the ROM's in its slice's and its ported callees' spans; ours in the overlay's), the
ANSWER LEDGER: each answered entry in order, with what it was asked (the cartridge's hooks among them, observed) — and
`also`, the same run's cycles in any further spans a price asks for (`priced(..., floppy=True)`: the ROM's driver text
ours still runs), read off the same profile."""


def _spans_cycles(spans):
    return sum(emu.prof_cycles(lo, hi) for lo, hi in spans)


def _vet_who_ran(label, ran, not_ran):
    """WHO RAN, off the profile just taken: no cycle in any span of `not_ran` (ours that ran the ROM's own code would be
    measured equal on the ROM's instructions — the false green); the cycles in `ran` returned."""
    for lo, hi in not_ran:
        spent = emu.prof_cycles(lo, hi)
        if spent:
            raise boot.Refused(f"{label}: the run executed [{lo:#x}, {hi:#x}) — {spent} cycles of it")
    return _spans_cycles(ran)


def _with_stores(slice_, runs):
    stored = {at for start, length in (*slice_.stored, *runs) for at in range(start, start + length)}
    return slice_._replace(stored=stopped_cpu.address_runs(sorted(stored)))


Carry = namedtuple("Carry", "port_a chip")
Carry.__doc__ = """WHAT A RUN HANDS THE NEXT (R-D4-2), from the ROM's own runs: PSG port A (its last store) and the FDC/DMA model's
chip (`emu.fdc_state()` bytes; None = MR's power-on chip, the reset's — no slice before B6 touches the FDC)."""


def floppy_declared(drive_arm, carry, gpip):
    """`boot.run`'s keywords for one leg through the FDC model: port A and the chip carried in, GPIP's other bits."""
    return dict(psg_seed={addrs.PSG_PORT_A: carry.port_a}, hw_seed={addrs.MFP_GPIP: gpip},
                fdc=boot.Fdc(drive_arm.drive_a, drive_arm.drive_b, carry.chip))


def carried(done, carry):
    """The carry `done` (a leg's `Slice`) hands the next leg: port A after it, the chip it left."""
    return Carry(boot.port_a_after(done, carry.port_a), done.fdc_chip)


def _legs(machine, until, laid, own, not_ran, observing, drive_arm, carry, gpip, budget=boot.SLICE_INSNS, also=()):
    """`machine` run to `until`, leg by leg — a leg stopped at an answered entry continues from its answer, one stopped at
    an observed entry (where `observing`) from where it stands — each leg profiled and run THROUGH THE FDC MODEL, port A
    and the chip carried leg to leg (every leg is a run): `(Shore of the legs joined, its own cycles `own`'s summed, the
    carry it leaves)`."""
    legs, spent, extra, answers, laid_runs = [], 0, 0, [], []
    stops = {until} | ANSWERED | (OBSERVED if observing else frozenset())
    while True:
        declared = floppy_declared(drive_arm, carry, gpip)
        if laid:
            done = boot.run(machine, stops, budget=budget, laid=laid, **declared)
            spent += _vet_who_ran(machine.label, own, not_ran)
            extra += _spans_cycles(also)
        else:
            emu.prof_enable(True)
            emu.prof_reset()
            try:
                done = boot.run(machine, stops, budget=budget, **declared)
                spent += _spans_cycles(own)
                extra += _spans_cycles(also)
            finally:
                emu.prof_enable(False)
        carry = carried(done, carry)
        legs.append(done)
        if done.stop == until:
            break
        if done.stop in OBSERVED:
            machine = done.machine
            answers.append(observed(machine))
            continue
        machine, asked, runs = answered(done.machine)
        answers.append(asked)
        laid_runs.extend(runs)
    joined = legs[0]
    for later in legs[1:]:
        joined = boot_hwinit.joined(joined, later)
    return Shore(_with_stores(joined, laid_runs), spent, tuple(answers), extra), carry


def _run(machine, until, laid, own, not_ran, drive_arm, carry, gpip, budget=boot.SLICE_INSNS, also=()):
    """THE SHORE: run once with every observed entry a stop — for the LEDGER — and once without — for the PRICE: a leg
    resumed where it stopped counts its step-off segment again (measured: +1 instruction, +40 cycles an arrival, on both
    shores alike), so the price and the machine are the plain run's. The two are held to leave the same machine and
    the same answers (refused by name otherwise)."""
    args = (machine, until, laid, own, not_ran)
    watched, _carry = _legs(*args, observing=True, drive_arm=drive_arm, carry=carry, gpip=gpip, budget=budget)
    plain, left = _legs(*args, observing=False, drive_arm=drive_arm, carry=carry, gpip=gpip, budget=budget, also=also)
    if (watched.slice.machine, watched.slice.stored, watched.slice.fdc_events, watched.slice.fdc_chip) \
            != (plain.slice.machine, plain.slice.stored, plain.slice.fdc_events, plain.slice.fdc_chip) \
            or [asked for asked in watched.answers if asked[0] not in OBSERVED_NAMES] != list(plain.answers):
        raise boot.Refused(f"{machine.label}: the run watched at its observed entries is not the run unwatched")
    return plain._replace(answers=watched.answers), left


def _budget(drive_arm):
    return boot.SLICE_INSNS if drive_arm == CAPTURE_DRIVES or drive_arm == B_ABSENT else TIMEOUT_ARM_INSNS


def entry_carry(machine):
    """THE CARRY INTO `$fc0452` on `machine`: port A from the ROM's chained boot, MR's chip (`Carry`)."""
    return Carry(port_a_at_start(machine), None)


def the_rom_s(machine, laid=None, drive_arm=CAPTURE_DRIVES):
    """The ROM's own slice on `machine` from its machine at `$fc0452` to `$fc047a` (`laid`: with an overlay — or several,
    `boot.overlays` — it must not reach: the ROM's shore with and without it), the floppy through the FDC model on
    `drive_arm`'s drives."""
    shore, _left = _run(start_of(machine), SPAN[1], laid, THE_ROM_S_SPANS, _spans_of(laid) if laid else (),
                        drives(drive_arm), entry_carry(machine), gpip_of(machine), _budget(drive_arm))
    return shore


def laid_with(code=None, floppy=False):
    """What our side lays: the product (or `code`) — and, with `floppy`, OUR LOWER FLOPPY DRIVER beside it (D4 P4, R-P4-3:
    its body and the jump at each ROM entry it ports, `boot_floppy.pieces`)."""
    import boot_floppy                  # (it imports this module)
    return boot.overlays(overlay(code), *boot_floppy.pieces()) if floppy else overlay(code)


def our_side(machine, code=None, drive_arm=CAPTURE_DRIVES, floppy=False, also=()):
    """OUR slice on `machine` from the same machine, on its overlay (the product, or `code`; with `floppy`, our lower
    floppy driver too — R-P4-3's new rows, beside these with the ROM's driver), entered at our entry where the ROM's
    stands; refused by name if it ran a cycle of the ROM's slice or of the routines it ports (with `floppy`, of the
    driver's ported text too). `also`: further spans whose cycles the same run reads (`Shore.also`)."""
    import boot_floppy                  # (it imports this module)
    laid = laid_with(code, floppy)
    entered = boot.entered_at(start_of(machine), product().base)
    entered = entered._replace(label=f"{entered.label}; {boot.label_of(laid)}")
    not_ran = (*THE_ROM_S_SPANS, *boot_floppy.NEVER_RUN) if floppy else THE_ROM_S_SPANS
    shore, _left = _run(entered, SPAN[1], laid, _spans_of(laid), not_ran, drives(drive_arm), entry_carry(machine),
                        gpip_of(machine), _budget(drive_arm), also=also)
    assert shore.own, f"{entered.label}: the run never executed our code"
    return shore


# ---- WHAT IS HELD ------------------------------------------------------------------------------------------------------------
SURFACES, LEDGERS = (*boot_hwinit.SURFACES, "fdc_chip"), boot_hwinit.LEDGERS
STACK_RESIDUE = next((base, base + size) for base, size, _name in midboot_snapshot.MASK
                     if base + size == midboot_snapshot.BIOS_STACK_TOP)


def outside_the_residue(ram):
    lo, hi = STACK_RESIDUE
    return ram[:lo] + bytes(hi - lo) + ram[hi:]


def _stored_outside(runs):
    lo, hi = STACK_RESIDUE
    return {at for start, length in runs for at in range(start, start + length) if not lo <= at < hi}


def differences(the_rom_s, ours):
    """Every surface `ours` (a `Shore`) differs from `the_rom_s` on, by name (none: held equal)."""
    found = []
    rom, mine = the_rom_s.slice, ours.slice
    if mine.stop != rom.stop:
        found.append(f"stop: the ROM's {rom.stop:#x}, ours {mine.stop:#x}")
    theirs, yours = rom.machine.registers, mine.machine.registers
    registers = {name: (f"{theirs[name]:#x}", f"{yours[name]:#x}") for name in theirs if theirs[name] != yours[name]}
    if registers:
        found.append(f"registers {registers} (the ROM's, ours)")
    rom_ram, our_ram = outside_the_residue(rom.machine.ram), outside_the_residue(mine.machine.ram)
    if our_ram != rom_ram:
        first = next(at for at, (one, other) in enumerate(zip(rom_ram, our_ram)) if one != other)
        found.append(f"ram, first at {first:#x}")
    if _stored_outside(rom.stored) != _stored_outside(mine.stored):
        found.append("stored: the addresses stored differ")
    for surface in LEDGERS:
        if getattr(rom, surface) != getattr(mine, surface):
            found.append(f"{surface}: {len(getattr(rom, surface) or ())} against ours {len(getattr(mine, surface) or ())}")
    if rom.fdc_chip != mine.fdc_chip:
        found.append("fdc_chip: the FDC/DMA chip the two shores left differs")
    if ours.answers != the_rom_s.answers:
        found.append(f"answers: the ROM's {the_rom_s.answers}, ours {ours.answers}")
    return found


# ---- THE END SURFACE: the mid-boot capture ------------------------------------------------------------------------------------
# WHAT THE CAPTURE HOLDS THAT NO SHORE DOES (measured on COLD — the capture is a power-on's boot): D1's flat megabyte
# ALONE — the cold arm's own memctrl, `$08` where the capture's ST holds `$05`: in D6, memctrl itself, D6's copy where the
# BIOS framed D6 below savptr ($93a) on a call GEMDOS made, and D6's low byte in the LOWER FLOPPY DRIVER'S register save
# area (`$a28`: its `movem.l d3-d7/a3-a6` keeps the caller's D6 at `$a34`). D4's class — the lower driver's own state in
# [$9f6, $a54) and its scratch D2 / A1 — is GONE since the driver runs as the ROM's through the kit's FDC model (R-D4-3),
# PSG port A carried from the ROM's own stores (R-D4-2: D2 is port A's value before the driver's last select).
END_REGISTERS_OWED = {"d6": "D1: the cold arm's memctrl on the flat megabyte"}
MEMCTRL_COPIES = (CONSTANTS["SYSVAR_MEMCTRL"], 0x91b)
LOWER_DRIVER_SAVED_D6_LOW = 0xa37       # $a28 + 3 longs (d3, d4, d5) + 3: D6's low byte in the driver's save area
END_APART = (*MEMCTRL_COPIES, LOWER_DRIVER_SAVED_D6_LOW)
LOWER_DRIVER_STATE = (0x9f6, 0xa54)


def against_the_capture(shore, capture):
    """`(registers, bytes)`: every register and every RAM address outside the capture's MASK where `shore`'s machine at
    `$fc047a` differs from the capture's."""
    machine = shore.slice.machine
    registers = {name for name in capture.registers if capture.registers[name] != machine.registers[name]}
    ours, theirs = midboot_snapshot.masked(machine.ram), midboot_snapshot.masked(capture.ram)
    return registers, {at for at, (one, other) in enumerate(zip(ours, theirs)) if one != other}


# ---- ITS PRICE (ruling D9: each shore's own cycles) ---------------------------------------------------------------------------
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """B6 measured on both shores: the two `boot.Slice`s, `own` (ours the overlay's cycles, the ROM's its
slice's and its ported callees') and `rest` (each run's other cycles: the ROM's routines both run), held equal."""


def priced(machine, floppy=False):
    """`machine`'s slice PRICED: both shores run, every held surface equal (refused by name otherwise). With `floppy`
    (R-P4-3: our lower floppy driver laid too) the ROM's own takes the driver's text it runs BEYOND what ours still runs
    of it (Floprd's, unported: the ROM's on both shores), read off each plain run's profile — the calls ours replaces.
    WHAT IT DEPENDS ON (review RP4a's N6): our C never runs the ROM's driver text on its own behalf — such cycles would
    leave our column for the ROM's discount unseen. Every ported entry has arrival rows holding the WHOLE call in our
    spans (`boot_floppy.priced`: own == the call's cycles)."""
    import boot_floppy                  # (it imports this module)
    if floppy:
        rom = _run(start_of(machine), SPAN[1], None, (*THE_ROM_S_SPANS, boot_floppy.LOWER_DRIVER), (), drives(),
                   entry_carry(machine), gpip_of(machine))[0]
        ours = our_side(machine, floppy=True, also=boot_floppy.ROM_TEXT_STILL_RUN)      # ONE run: both sums
        rom = rom._replace(own=rom.own - ours.also)
    else:
        rom, ours = the_rom_s(machine), our_side(machine)
    found = differences(rom, ours)
    assert not found, f"{name_of(machine)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (ours.slice.cycles - ours.own, rom.slice.cycles - rom.own)
    assert rest[0] == rest[1], f"{name_of(machine)}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(rom.slice, ours.slice, (ours.own, rom.own), rest[0])


def name_of(machine):
    return next(name for name, each in SLICES.items() if each == machine)
