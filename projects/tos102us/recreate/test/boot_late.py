r"""THE BOOT'S LATE SLICE ON BOTH SHORES (boot B6, `test_boot_late.py`): the ROM's own `[$fc0452, $fc047a)` — with the
routines it calls that this slice ports with it: GEMDOS's buffers `$fc4a9e`, the clock's date `$fc4be8`, the floppy's
boot `$fc053c`, the ACSI's `$fc0558` and the reset-resident scan `$fc0e56` — against OUR C (`src/boot/late/late.c`,
`boot_late_entry`), run from one machine and held equal on every surface the C can be held on, as B5's slice is
(`boot_display.py`); and the machine both reach held to THE MID-BOOT CAPTURE (`build/midboot.bin`) under its own MASK.

THE USER'S RULINGS THIS MODULE STANDS ON: D8 (the WARM and COLD machines, `boot.py`), D9 "Stretch rows" (each arm priced
on each shore's own cycles, `bench/tier3.py`), "ROM-window overlay" and "Own link rule" (where our code lies, below) —
2026-10-29; R-B4-2 "Answer it at its entry" (the clock's probe) — and D3 (2026-10-31): "NO kit interrupt source. The
waiting routines are ANSWERED AT THEIR ENTRIES on both shores, labelled". The slice opens the interrupts (`move
#$2300,sr`) and NONE IS DELIVERED inside a run (said on every label). And D4 (2026-10-31): an FDC/DMA model is a later,
separate project — the floppy stays answered at its entries. The orchestrator's standing calls: GEMDOS's init and its
Dsetdrv stay the ROM's on both shores (OS both run); so do the cartridge's hooks (D2: the port reads 0) and the floppy
driver's hdv_boot / hdv_init (the F-upper driver, unported), each called in place.

THE ANSWERS, AT FOUR ENTRIES, ON BOTH SHORES ALIKE (`answered`), each value pinned to the ROM's text or to the capture
(the ROM's own run on Hatari), each counted in the run's ANSWER LEDGER with what it was asked:
  * THE DRIVE PROBE `$fc173a` (D3: hdv_init's, the FDC's restore and its waits below it) — D0 the drive's status as the
    capture's own hdv_init stored it: 0, a drive answered, for both drives (`DRIVE_PRESENT`). THE CAPTURE'S CLASS (the
    ROM's own two-drive path, `aes_boot`'s DRIVE B: note); a drive ABSENT is no class of ours — what the probe answers
    there is the WD1772's (D4), unpinned by name.
  * FLOPRD `$fc1782` (D4: the existing device model's fourth entry, `aes_boot.Floppy`) — hdv_boot's read of the boot
    sector, served off THE CAPTURE'S BLANK DISK by `boot_launch.NeverLoggedIn` (R-B4-3: drive A:'s record zero here).
  * THE ACSI PROBE `$fc0586` (D3, "no device") — what the ROM's own probe leaves when the controller never answers: D0
    and D1 -1, A5/A6 the DMA's two registers, flock's byte cleared, Z clear (`ACSI_NO_DEVICE`).
  * THE CLOCK'S PROBE `$fc4c0c` (R-B4-2) — carry set: no RP5C15 on the capture's plain ST.
AND THREE ENTRIES OBSERVED, run as the ROM's: the cartridge's hooks (the init bit each arrival hands them: with no
cartridge — D2 — nothing else reads it), GEMDOS's init and its Dsetdrv (with the drive word) — each arrival in the
ledger, so the calls' order and Dsetdrv's argument are held. UNPINNED BY NAME: `_bootdev` other than 0 (a hard disk's
boot: the ACSI answers "no device"), so the drive Dsetdrv makes current is 0 in every run.
THE ORCHESTRATOR'S READING OF D3 (the user may override): D3 names "hdv_boot"; hdv_boot and hdv_init are the floppy's
upper driver — C that waits on nothing itself — so they run as the ROM's, and the two waits below them are what is
answered at their entries (the drive probe, D3's own; Floprd, D4's) — the narrower answer, R-B5-1's precedent.
WHAT NO ANSWER LAYS (named): the lower floppy driver's own state and scratch — its register save area, its records, its
retry count ([$9f6, $a54), and D2 / A1) — which the capture holds and neither shore does (D4); the DMA's and the FDC's
writes the probes make before they wait (on no shore's ledger); the stack the answered routines would have used.

WHERE OUR CODE LIES: over a copy of the image's ROM window at `LATE_LAID_AT` (`boot.overlaid`, A LABELLED STAGING),
linked there by its own rule (`build/bootlate/`) with every callee-saved register fixed. Held: the ROM's own runs are
the same with and without the overlay; a run of ours that spends a cycle in the ROM's slice or its ported callees is
REFUSED BY NAME (the false green).

WHAT IS HELD (`differences`): the stop; EVERY register; the megabyte and the addresses stored OUTSIDE THE BIOS STACK'S
DEAD FRAMES (the mid-boot capture's own MASK field, `[$745a, $755a)`: below the stack's top at the stop, where the two
shores' frames lie at different depths — our C calls GEMDOS's init from no frame, the ROM's from `$fc4a9e`'s `link`);
every ordered ledger (the hardware writes, the declared reads, the modelled reads, the PSG's accesses); the faults; the
answers in order with what each was asked; the floppy's calls. Instructions and cycles are the price, not a surface.
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

# ---- THE ANSWERED ENTRIES -------------------------------------------------------------------------------------------------
DRIVE_PROBE = 0xfc173a                  # hdv_init's `jsr` ($fc0f82): the drive's select, its restore, the FDC's waits
DRIVE_PROBE_CALL = 0xfc0f82
DRIVE_PROBE_DEVICE_AT = 12              # `tst.w 12(sp)` ($fc1740): the drive the probe asks after
DRIVE_STATUS_LOAD = 0xfc0f96            # hdv_init's `adda.l #<the drives' status words>,a0`, the drive * 2 in A0
DRIVE_PRESENT = 0                       # the probe's success exit ($fc1cda `clr.l d0`), what the capture holds for both
FLOPRD_CALL = 0xfc15aa                  # hdv_boot's `jsr` of the driver's Floprd, the boot sector to `_dskbufp`
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
                "opens them and none arrives): the drive probe ($fc173a) — a drive answered, the capture's, for both "
                "drives; the ACSI probe ($fc0586) — no device; D4 FLOPRD ($fc1782) off the capture's blank disk, drive "
                "A: never logged in (R-B4-3); R-B4-2 THE CLOCK ($fc4c0c) — carry set. NOT LAID: the lower floppy "
                "driver's own state and scratch, the probes' DMA/FDC writes. THE ORCHESTRATOR'S READING OF D3 (the user may "
                "override): hdv_boot and hdv_init run as the ROM's, the waits below them answered")

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


# ---- THE ANSWERS -------------------------------------------------------------------------------------------------------
def _returned(registers, ram, sp):
    """The answered routine's `rts`: the PC its caller's call pushed, the stack above it."""
    return {**registers, "pc": case.long_in(ram, sp) & BUS, "isp": sp + LONG_BYTES}


def answered(machine, floppy_memory=None):
    """`machine` standing at an answered entry, ANSWERED: `(the machine past the routine's return, the ledger entry, the
    RAM runs the answer laid)`. The floppy's answer reads and lays through `aes_boot.Floppy`'s own model."""
    registers, ram = dict(machine.registers), bytearray(machine.ram)
    pc, sp = registers["pc"], registers["isp"]
    laid = ()
    if pc == DRIVE_PROBE:
        drive = case.word_in(ram, sp + DRIVE_PROBE_DEVICE_AT)
        registers["d0"] = DRIVE_PRESENT
        asked = ("the drive probe", drive)
    elif pc == FLOPRD_ENTRY:
        memory = bytearray(BASE_IMAGE)
        memory[:RAM_BYTES] = ram
        floppy = boot_launch.NeverLoggedIn(memory, the_disk())
        answer, _to = floppy.served(FLOPRD_ENTRY, sp)
        laid = floppy.laid_by_the_last_call()
        for at, data in laid:
            ram[at:at + len(data)] = data
        registers["d0"] = answer & aes_boot.LONG_MASK
        asked = ("Floprd", *floppy.calls[-1]) if floppy.calls else ("Floprd",)
    elif pc == ACSI_PROBE:
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


FLOPRD_ENTRY = 0xfc1782                 # held to the machine's own XBIOS table (`aes_boot._xbios_entry`) by the battery
ANSWERED = frozenset({DRIVE_PROBE, FLOPRD_ENTRY, ACSI_PROBE, CLOCK_PROBE})
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

# ---- THE TWO SHORES --------------------------------------------------------------------------------------------------------
Shore = namedtuple("Shore", "slice own answers")
Shore.__doc__ = """One shore's run: the `boot.Slice` (its legs joined where an entry was answered, the answers' own stores
among `stored`), its OWN cycles (the ROM's in its slice's and its ported callees' spans; ours in the overlay's) and the
ANSWER LEDGER: each answered entry in order, with what it was asked (the cartridge's hooks among them, observed)."""


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


def _legs(machine, until, laid, own, not_ran, observing):
    """`machine` run to `until`, leg by leg — a leg stopped at an answered entry continues from its answer, one stopped at
    an observed entry (where `observing`) from where it stands — each leg profiled: `(Shore of the legs joined, its own
    cycles `own`'s summed)`."""
    legs, spent, answers, laid_runs = [], 0, [], []
    stops = {until} | ANSWERED | (OBSERVED if observing else frozenset())
    while True:
        if laid:
            done = boot.run(machine, stops, laid=laid)
            spent += _vet_who_ran(machine.label, own, not_ran)
        else:
            emu.prof_enable(True)
            emu.prof_reset()
            try:
                done = boot.run(machine, stops)
                spent += _spans_cycles(own)
            finally:
                emu.prof_enable(False)
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
    return Shore(_with_stores(joined, laid_runs), spent, tuple(answers))


def _run(machine, until, laid, own, not_ran):
    """THE SHORE: run once with every observed entry a stop — for the LEDGER — and once without — for the PRICE: a leg
    resumed where it stopped counts its step-off segment again (measured: +1 instruction, +40 cycles an arrival, on both
    shores alike), so the price and the machine are the plain run's. The two are held to leave the same machine and
    the same answers (refused by name otherwise)."""
    watched = _legs(machine, until, laid, own, not_ran, observing=True)
    plain = _legs(machine, until, laid, own, not_ran, observing=False)
    if (watched.slice.machine, watched.slice.stored) != (plain.slice.machine, plain.slice.stored) \
            or [asked for asked in watched.answers if asked[0] not in OBSERVED_NAMES] != list(plain.answers):
        raise boot.Refused(f"{machine.label}: the run watched at its observed entries is not the run unwatched")
    return plain._replace(answers=watched.answers)


def the_rom_s(machine, laid=None):
    """The ROM's own slice on `machine` from its machine at `$fc0452` to `$fc047a` (`laid`: with an overlay it must not
    reach — the ROM's shore with and without it)."""
    return _run(start_of(machine), SPAN[1], laid, THE_ROM_S_SPANS, (our_span(laid),) if laid else ())


def our_side(machine, code=None):
    """OUR slice on `machine` from the same machine, on its overlay (the product, or `code`), entered at our entry where
    the ROM's stands; refused by name if it ran a cycle of the ROM's slice or of the routines it ports."""
    laid = overlay(code)
    entered = boot.entered_at(start_of(machine), product().base)
    entered = entered._replace(label=f"{entered.label}; {laid.label}")
    shore = _run(entered, SPAN[1], laid, (our_span(laid),), THE_ROM_S_SPANS)
    assert shore.own, f"{entered.label}: the run never executed our code"
    return shore


# ---- WHAT IS HELD ------------------------------------------------------------------------------------------------------------
SURFACES, LEDGERS = boot_hwinit.SURFACES, boot_hwinit.LEDGERS
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
    if ours.answers != the_rom_s.answers:
        found.append(f"answers: the ROM's {the_rom_s.answers}, ours {ours.answers}")
    return found


# ---- THE END SURFACE: the mid-boot capture ------------------------------------------------------------------------------------
# WHAT THE CAPTURE HOLDS THAT NO SHORE DOES, by class (measured on COLD — the capture is a power-on's boot): D1's flat
# megabyte (the cold arm's own memctrl, `$08` where the capture's ST holds `$05`: in D6 and its two stores) and D4's lower
# floppy driver (its scratch D2 and A1, and its own state in [$9f6, $a54): the retry count, the request, the error codes,
# the register save area, the drives' records — the bytes no answer lays).
END_REGISTERS_OWED = {"d6": "D1: the cold arm's memctrl on the flat megabyte", "d2": "D4: the lower floppy driver's scratch",
                      "a1": "D4: the lower floppy driver's record of the drive"}
# ...memctrl itself and its copy in D6's low byte where the BIOS framed D6 below savptr ($93a) on a call GEMDOS made.
MEMCTRL_COPIES = (CONSTANTS["SYSVAR_MEMCTRL"], 0x91b)
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


def priced(machine):
    """`machine`'s slice PRICED: both shores run, every held surface equal (refused by name otherwise)."""
    rom, ours = the_rom_s(machine), our_side(machine)
    found = differences(rom, ours)
    assert not found, f"{name_of(machine)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (ours.slice.cycles - ours.own, rom.slice.cycles - rom.own)
    assert rest[0] == rest[1], f"{name_of(machine)}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(rom.slice, ours.slice, (ours.own, rom.own), rest[0])


def name_of(machine):
    return next(name for name, each in SLICES.items() if each == machine)
