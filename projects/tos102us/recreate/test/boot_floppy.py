r"""THE FLOPPY'S LOWER DRIVER ON BOTH SHORES (D4 phase P4, `test_boot_floppy.py`): the ROM's `[$fc173a, $fc1f08)` against
OUR C (`src/boot/floppy/`), each ROM entry it ports reached through a 6-byte `jmp` laid over the ROM's own first
instruction there, so every caller — the XBIOS table, hdv_init's `jsr`, every harness answer keyed by the entry —
reaches ours unchanged. P4a ports the DRIVE PROBE (`$fc173a`) and the primitives it runs on; P4b FLOPRD (`$fc1782`) and
FLOPVER (`$fc1ae2`) with the recalibrate, the seek-verify, the error decode, the single-drive alert and the common entry's
unknown-track recovery (reached on drive A: absent and B: present alone, ruling R-P4b-1).

THE USER'S RULINGS IT STANDS ON: D4 (2026-11-01, R-D4-1..4: the kit's zero-time FDC/DMA model, armed per run; the chip
and PSG port A carried from the ROM's own runs; the model's ordered ledger held exactly); "ROM-window overlay" and "Own
link rule" (2026-10-29); and (2026-11-02, on the P4 design): R-P4-2 "Jump at ROM entries" — a 6-byte `jmp` laid at each
driver entry address in the test image, 12 cycles a call, priced; R-P4-3 "Both" — A NEW TIER-3 ROW KIND, A DRIVER CALL
PRICED AT ITS ARRIVAL (`ARRIVALS`, `priced`), and the chained boot runs our driver (`boot_chain`), B6's battery keeping
its rows with the ROM's driver beside the new ones (`boot_late.our_side(..., floppy=True)`). The orchestrator's calls
under standing policy: the settle an asm idiom inside the C (the SECTOR_SUM precedent), target-only C, the stack bound
held by making the C fit. And R-P4-1 "Yes, staged calls" (P4b): A STAGED CALL — B6's machine at its Floprd arrival, the
call's arguments laid on its stack, the entry named, a writable copy of the capture's blank disk per shore (`STAGED`).

A DRIVER CALL AT ITS ARRIVAL (`arrivals`, `the_rom_s` / `ours`): B6's ROM run from its machine at `$fc0452` through the
FDC model on one drive arm (`boot_late.DRIVE_ARMS`), stopped where hdv_init's `jsr` arrives at the probe — the machine
there, the carry (port A, the chip) — and from that one machine, BOTH SHORES run to the call's return: the ROM's own
probe, and ours entered at the same address (our jump laid there, our body over the VDI's GDP text). The ROM's run then
goes on from where its call returned, to the next arrival.

WHAT IS HELD (`differences`): the stop; EVERY register (D0 the result, D1 / D2 port A's bytes over the caller's upper
ones, A0 the stamp table, A1 the record, SR's flags, the caller's D3-D7 / A3-A6 restored); the megabyte and the addresses
stored OUTSIDE the call's own dead frames — `[FRAMES_APART_FROM, its entry SP)`, the floor the chain holds the BIOS
stack byte for byte below (`boot_chain.FRAMES_APART_FROM`): a store of ours below it is a difference, which is how the
29-byte bound is held — so the 36 bytes the glue saves at `$a28` are held exactly; every ordered ledger (the hardware
writes, the declared reads, the modelled reads, the PSG's accesses, the FDC model's transactions with the polls each
wait made, counted); the chip the model left; the disks each shore's drives hold after (a staged call's own copies).
Instructions and cycles are the price: each shore's OWN — ours every cycle in our jump and body, the ROM's every cycle in
its driver — and the REST beside them (the critical-error handler the single-drive alert calls) held equal.
"""
import functools
import struct
from collections import namedtuple
from pathlib import Path

from harness import addrs, emu

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

# ---- THE ROM'S DRIVER, AND WHAT P4a / P4b PORT OF IT -----------------------------------------------------------------------
LOWER_DRIVER = (CONSTANTS["ROM_FLOPPY_PROBE"], CONSTANTS["ROM_FLOPPY_LOWER_END"])
PROBE, FLOPRD, FLOPVER = CONSTANTS["ROM_FLOPPY_PROBE"], CONSTANTS["ROM_FLOPPY_FLOPRD"], CONSTANTS["ROM_FLOPPY_FLOPVER"]
FLOPWR, FLOPFMT = CONSTANTS["ROM_FLOPPY_FLOPWR"], CONSTANTS["ROM_FLOPPY_FLOPFMT"]
PROBE_SPAN = (PROBE, FLOPRD)
# EACH PORTED ENTRY: the ROM's address, where our jump is laid, and the glue's symbol it jumps to (P4a the probe; P4b
# Floprd and Flopver).
PORTED = {PROBE: "floppy_probe_entry", FLOPRD: "floppy_floprd_entry", FLOPVER: "floppy_flopver_entry",
          FLOPWR: "floppy_flopwr_entry", FLOPFMT: "floppy_flopfmt_entry"}
# ...AND EACH ONE'S OWN TEXT in the ROM: the probe to Floprd; Floprd with its error decode to Flopwr; Flopver with its verify
# core to the VBL service.
PORTED_SPANS = {PROBE: PROBE_SPAN, FLOPRD: (FLOPRD, FLOPWR), FLOPWR: (FLOPWR, FLOPFMT), FLOPFMT: (FLOPFMT, FLOPVER),
                FLOPVER: (FLOPVER, CONSTANTS["ROM_FLOPPY_VBL"])}
PRIMITIVES = (CONSTANTS["ROM_FLOPPY_PRIMITIVES"], CONSTANTS["ROM_FLOPPY_LOWER_END"])
STUB_BYTES = CONSTANTS["FLOPPY_ENTRY_JUMP_BYTES"]
# THE ROM'S TEXT OUR SHORE MUST NEVER RUN: each ported routine's own text past the jump laid over its first instruction,
# and — since P4b, when no routine of the ROM's that calls them runs on our shore (Flopwr and Flopfmt are called by no run
# that lays the driver) — the primitives.
NEVER_RUN = (*(tuple((entry + STUB_BYTES, PORTED_SPANS[entry][1]) for entry in sorted(PORTED))), PRIMITIVES)
# ...AND THE ROM'S DRIVER TEXT OURS STILL RUNS: all of it but the jumps laid over it (none of it on any run of ours since
# P4b; Flopwr's and Flopfmt's until P4c) — what a slice's price reads OFF the ROM's own driver cycles to leave the calls
# ours replaces (`boot_late.priced`, `boot_chain.priced`).
def _without_the_jumps(span):
    lo, hi, kept = *span, []
    for entry in sorted(PORTED):
        kept.append((lo, entry))
        lo = entry + STUB_BYTES
    return tuple((one, other) for one, other in (*kept, (lo, hi)) if one < other)


ROM_TEXT_STILL_RUN = _without_the_jumps(LOWER_DRIVER)

LABEL = ("THE FLOPPY'S LOWER DRIVER, OURS (R-P4-2 \"Jump at ROM entries\"): a 6-byte `jmp` laid at each ported ROM entry, "
         "our body over the VDI's GDP text [$fcc400, $fcd000)")
STAGED_LABEL = ("A STAGED CALL — A LABELLED STAGING (ruling R-P4-1 \"Yes, staged calls\"): B6's machine at its Floprd "
                "arrival, the call's arguments LAID on its stack and its entry the one named, a WRITABLE copy of the "
                "capture's blank disk in each shore's drive A:")


Product = namedtuple("Product", "base code symbols elf")


@functools.cache
def product():
    """`Product` of `build/bootfloppy/` — refused by name unless it lies at its laid address and ends inside its span
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
Arrival = namedtuple("Arrival", "machine carry returns_to drive_arm gpip writable protected", defaults=(False, False))
Arrival.__doc__ = """One call of a ported entry as the ROM's own B6 run makes it — or as a case stages it there (R-P4-1): the
`machine` standing at the entry, the `carry` (port A, the chip) the run hands it, the address it `returns_to` (the long at
its SP), the `drive_arm` and the `gpip` byte its run declares; `writable`: each shore lent its OWN WRITABLE COPY of the
drives' disks (a staged call's; R-P4-1), else the capture's disk read-only; `protected`: drive A:'s disk declared
write-protected (R-P4-1's WP arms)."""


def _bays(arrival):
    drives = boot_late.drives(arrival.drive_arm)
    bays = (drives.drive_a, drives.drive_b)
    if arrival.writable:
        bays = tuple(bay._replace(image=bytearray(bay.image)) if bay.image is not None else bay for bay in bays)
    if arrival.protected:
        bays = (bays[0]._replace(write_protected=True), bays[1])
    return bays


def _call(arrival, laid=None):
    """One shore's run of `arrival`'s call to its return (`laid`: our driver laid, our jump at the entry): `(Slice, the
    drives' images after it)`."""
    bays = _bays(arrival)
    done = boot.run(arrival.machine, {arrival.returns_to}, budget=boot_late.TIMEOUT_ARM_INSNS, laid=laid,
                    psg_seed={addrs.PSG_PORT_A: arrival.carry.port_a},
                    hw_seed={addrs.MFP_GPIP: arrival.gpip}, fdc=boot.Fdc(*bays, arrival.carry.chip))
    return done, tuple(None if bay.image is None else bytes(bay.image) for bay in bays)


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
        called, _images = _call(arrival)
        calls.append((arrival, called))
        standing, carry = called.machine, boot_late.carried(called, carry)


@functools.cache
def b6_calls(machine, drive_arm=boot_late.CAPTURE_DRIVES):
    """Every call of a ported entry B6's ROM run makes on `machine` (WARM / COLD) and `drive_arm`."""
    return rom_calls(boot_late.start_of(machine), boot_late.SPAN[1], drive_arm, boot_late.entry_carry(machine),
                     boot_late.gpip_of(machine))


# THE ROWS (R-P4-3, the new kind): each call B6 makes — both drives' probes and hdv_boot's Floprd of the boot sector (none
# with no drive at all: hdv_boot reads `_nflops` 0 and calls nothing) — on COLD with each drive arm, and on WARM with the
# capture's drives (the driver does not read WARM against COLD; the arms are P3's, run on COLD) ...
B6_FLOPRD_ARMS = (boot_late.CAPTURE_DRIVES, boot_late.B_ABSENT, boot_late.A_EMPTY, boot_late.A_ABSENT_B_PRESENT)
B6_FLOPRD_INDEX = 2
ARRIVALS = {
    **{f"the probe of drive {'AB'[index]}:, {arm}, COLD": (boot.COLD, arm, index) for arm in boot_late.DRIVE_ARMS
       for index in (0, 1)},
    **{f"the probe of drive {'AB'[index]}:, {boot_late.CAPTURE_DRIVES}, WARM": (boot.WARM, boot_late.CAPTURE_DRIVES, index)
       for index in (0, 1)},
    **{f"Floprd of the boot sector, {arm}, COLD": (boot.COLD, arm, B6_FLOPRD_INDEX) for arm in B6_FLOPRD_ARMS},
    f"Floprd of the boot sector, {boot_late.CAPTURE_DRIVES}, WARM": (boot.WARM, boot_late.CAPTURE_DRIVES, B6_FLOPRD_INDEX),
}
# ...AND THE STAGED CALLS (R-P4-1): from B6's machine at its Floprd arrival (COLD unless `boot` names WARM; the arm named), `entry` called with these
# arguments — buffer, filler, drive, sector, track, side, count (Floprd's and Flopver's shape) — the buffer above the boot's
# RAM in use, so its address's high byte is not 0 (it pins the DMA address's high byte).
STAGED_BUFFER = 0x30000
Staged = namedtuple("Staged", "drive_arm entry drive sector track side count protected boot", defaults=(False, boot.COLD))
# ...and Flopfmt's (its own arguments: buffer, the skew table, drive, sectors a track, track, side, interleave, the magic,
# the virgin word).
StagedFormat = namedtuple("StagedFormat", "drive_arm drive spt track side interleave magic virgin protected boot",
                          defaults=(False, boot.COLD))
StagedFormat.entry = FLOPFMT
FORMAT_ARGUMENTS = ">IIHHHHHIH"
FORMAT_VIRGIN = 0xe5e5                  # the virgin word the desk's Format hands it
FORMAT_VIRGIN_TWO_BYTES = 0x1234        # a caller's own word whose two bytes differ: the order they are laid in shows
BAD_MAGIC = 0x12345678
STAGED = {
    "Floprd, 9 sectors from track 5 side 1 sector 1": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 0, 1, 5, 1, 9),
    "Floprd, track 79 side 1 sector 9": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 0, 9, 79, 1, 1),
    "Floprd, sector 10 (record not found, the recalibrate)": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 0, 10, 0, 0, 1),
    "Floprd, sector 0 (record not found)": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 0, 0, 0, 0, 1),
    "Floprd, track 80 (the seek-verify fails)": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 0, 1, 80, 0, 1),
    "Floprd of drive B:, empty (the seek-verify's timeouts)": Staged(boot_late.CAPTURE_DRIVES, FLOPRD, 1, 1, 0, 0, 1),
    "Floprd of drive B: on one drive (the single-drive alert)": Staged(boot_late.B_ABSENT, FLOPRD, 1, 1, 0, 0, 1),
    "Flopver, track 0 side 0, 9 sectors": Staged(boot_late.CAPTURE_DRIVES, FLOPVER, 0, 1, 0, 0, 9),
    "Flopver, sectors 8 to 10 (one listed)": Staged(boot_late.CAPTURE_DRIVES, FLOPVER, 0, 8, 0, 0, 3),
    # ...and two sectors that both fail (10, 11: no such sector on a 9-sector track): the SECOND sector's retries reset
    # per sector — three reads and the recalibrate again, both listed (review RP4b's R2).
    "Flopver, sectors 10 and 11 (both listed)": Staged(boot_late.CAPTURE_DRIVES, FLOPVER, 0, 10, 0, 0, 2),
    "Flopver, track 5 side 1, 2 sectors": Staged(boot_late.CAPTURE_DRIVES, FLOPVER, 0, 1, 5, 1, 2),
    "Flopver of drive B:, empty (the seek-verify fails)": Staged(boot_late.CAPTURE_DRIVES, FLOPVER, 1, 1, 0, 0, 1),
    # P4c: the write side
    "Flopwr, track 3 side 0 sector 2": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 2, 3, 0, 1),
    "Flopwr, the boot sector (the media marked CHANGED)": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 1, 0, 0, 1),
    "Flopwr, sector 10 (record not found)": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 10, 3, 0, 1),
    "Flopwr, write-protected (no retry)": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 2, 3, 0, 1, True),
    "Flopwr, drive A: empty": Staged(boot_late.A_EMPTY, FLOPWR, 0, 2, 3, 0, 1),
    "Flopwr, 2 sectors from track 3 sector 2": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 2, 3, 0, 2),
    "Flopwr, track 0 side 1 sector 1 (not the boot sector)": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 1, 0, 1, 1),
    "Flopwr, track 1 side 0 sector 1 (not the boot sector)": Staged(boot_late.CAPTURE_DRIVES, FLOPWR, 0, 1, 1, 0, 1),
    "Flopfmt, track 5 side 0, interleave 1": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 5, 0, 1, None, FORMAT_VIRGIN),
    "Flopfmt, track 6 side 1, interleave 2": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 6, 1, 2, None, FORMAT_VIRGIN),
    "Flopfmt, write-protected": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 5, 0, 1, None, FORMAT_VIRGIN, True),
    "Flopfmt, interleave 2, write-protected": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 6, 1, 2, None, FORMAT_VIRGIN,
                                                           True),
    "Flopfmt, track 7 side 0, a virgin word of two bytes": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 7, 0, 1, None,
                                                                         FORMAT_VIRGIN_TWO_BYTES),
    "Flopfmt, interleave 10 over 9 sectors, write-protected": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 5, 0, 10, None,
                                                                           FORMAT_VIRGIN, True),
    "Flopfmt, drive A: empty (the write track's timeout)": StagedFormat(boot_late.A_EMPTY, 0, 9, 5, 0, 1, None,
                                                                        FORMAT_VIRGIN),
    "Flopfmt, a bad magic (the ROM's stale error exit, kept)": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 5, 0, 1,
                                                                            BAD_MAGIC, FORMAT_VIRGIN),
    # (and at WARM's arrival, where `_hz_200` is not 0: the tail's read of it through the caller's A5 then shows)
    "Flopfmt, a bad magic, WARM (the ROM's stale error exit, kept)": StagedFormat(boot_late.CAPTURE_DRIVES, 0, 9, 5, 0, 1,
                                                                                  BAD_MAGIC, FORMAT_VIRGIN, boot=boot.WARM),
}
ARRIVALS.update({f"STAGED (R-P4-1): {name}": staged for name, staged in STAGED.items()})
FLOPFMT_MAGIC = CONSTANTS["FLOPFMT_MAGIC"]
STAGED_ARGUMENTS = ">IIHHHHH"                # buffer, filler, drive, sector, track, side, count — past the return


def staged_arrival(staged):
    """THE STAGED CALL (R-P4-1): B6's machine standing at its Floprd arrival on `staged.drive_arm` (`staged.boot`), `staged`'s
    arguments laid where Floprd's stand and its entry the one named; each shore's disks its own writable copies."""
    floprd, _called = b6_calls(staged.boot, staged.drive_arm)[B6_FLOPRD_INDEX]
    ram = bytearray(floprd.machine.ram)
    if isinstance(staged, StagedFormat):
        magic = FLOPFMT_MAGIC if staged.magic is None else staged.magic
        struct.pack_into(FORMAT_ARGUMENTS, ram, floprd.machine.registers["isp"] + 4, STAGED_BUFFER, 0, staged.drive,
                         staged.spt, staged.track, staged.side, staged.interleave, magic, staged.virgin)
    else:
        struct.pack_into(STAGED_ARGUMENTS, ram, floprd.machine.registers["isp"] + 4, STAGED_BUFFER, 0, staged.drive,
                         staged.sector, staged.track, staged.side, staged.count)
    machine = floprd.machine._replace(ram=bytes(ram), registers={**floprd.machine.registers, "pc": staged.entry},
                                      label=f"{floprd.machine.label}; {STAGED_LABEL}")
    return floprd._replace(machine=machine, writable=True, protected=staged.protected)


def entry_of(name):
    """The ROM entry `name`'s call enters — read off its row, running nothing (the tier-3 table names its rows by it)."""
    spec = ARRIVALS[name]
    if isinstance(spec, (Staged, StagedFormat)):
        return spec.entry
    return FLOPRD if spec[2] == B6_FLOPRD_INDEX else PROBE


@functools.cache
def arrival_of(name):
    """`name`'s arrival: a call B6's run makes (`Arrival`), or a staged one."""
    spec = ARRIVALS[name]
    if isinstance(spec, (Staged, StagedFormat)):
        return staged_arrival(spec)
    machine, drive_arm, index = spec
    return b6_calls(machine, drive_arm)[index][0]


Shore = namedtuple("Shore", "slice own images")


def the_rom_s(name):
    """The ROM's own call at `name`'s arrival: its own cycles every cycle in its lower driver (the critical-error handler the
    single-drive alert calls — the OS both run — in neither column)."""
    arrival = arrival_of(name)          # (made before the profile opens: B6's run to it is no part of the call)
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        called, images = _call(arrival)
        own = emu.prof_cycles(*LOWER_DRIVER)
    finally:
        emu.prof_enable(False)
    return Shore(called, own, images)


def ours(name, code=None):
    """OUR call from the same machine, our driver laid (or `code` as its body), entered at the same ROM address — refused
    by name if it ran a cycle of the ROM's ported text; its own cycles every cycle in our spans."""
    arrival = arrival_of(name)
    laid = pieces(code)
    called, images = _call(arrival, laid=boot.overlays(*laid))
    ran = [f"[{lo:#x}, {hi:#x}) — {emu.prof_cycles(lo, hi)} cycles of it" for lo, hi in sorted({*NEVER_RUN, *ROM_TEXT_STILL_RUN})
           if emu.prof_cycles(lo, hi)]
    if ran:
        raise boot.Refused(f"{name}: our call executed the ROM's driver text {'; '.join(ran)}")
    return Shore(called, sum(emu.prof_cycles(lo, hi) for lo, hi in our_spans(laid)), images)


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
    span = frames(arrival_of(name).machine.registers["isp"])
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
    if rom.images != mine.images:
        found.append("images: the disks the two shores left differ")
    return found


Priced = namedtuple("Priced", "the_rom_s ours own rest")


def priced(name):
    """The call at `name`'s arrival PRICED: both shores run, every held surface equal (refused by name otherwise); each
    shore's own cycles — ours every cycle in our jump and our body, the ROM's every cycle in its lower driver — and THE
    REST, each call's other cycles (the critical-error handler the single-drive alert calls: the OS both run), held equal.
    With `ours` refused by name where it spent a cycle in the ROM's driver text, that is what keeps the slices' price in
    place honest (review RP4a's N6)."""
    rom, mine = the_rom_s(name), ours(name)
    found = differences(name, rom, mine)
    assert not found, f"{name}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (mine.slice.cycles - mine.own, rom.slice.cycles - rom.own)
    assert rest[0] == rest[1], f"{name}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(rom.slice, mine.slice, (mine.own, rom.own), rest[0])
