#!/usr/bin/env python3
"""Capture THE MID-BOOT MACHINE: the ROM's own boot stopped at `$fc047a`, the BIOS's `tst.w _cmdload` (boot B0).

    python tools/midboot_snapshot.py                 # capture build/midboot.bin
    python tools/midboot_snapshot.py --twice         # capture twice and report what differs

`tools/preinit_snapshot.py`'s method — the same machine, ROM, Hatari arguments and blank floppy (read from
`boot_snapshot`, not respelled), a PC breakpoint, the megabyte, the register file and the shifter bytes — stopped
EARLIER: at the first instruction after the boot's interrupt-driven stretch. By `$fc047a` the BIOS has opened the
interrupts (`$fc0452 move #$2300,sr`), brought GEMDOS up (`$fc4a9e`), read the clock (`$fc4be8`), tried the floppy's
boot sector (`$fc053c`), probed the ACSI bus (`$fc0558`) and scanned RAM for reset-resident programs (`$fc0e56`); the
AUTO folder has not been searched and no program has been launched. It is the START MACHINE of the boot's last slice,
`[$fc047a, gem_entry)`, whose end is the pre-init capture (the user's ruling D8, 2026-10-29: A LABELLED STAGING, the
capture held like the kept set).

WHY A CAPTURE AND NOT THE ORACLE RUN TO IT: the stretch before it waits on time — the floppy driver's and the ACSI
probe's waits poll `_hz_200` and the FDC's done line under live interrupts — and the oracle delivers no interrupt
inside a run (decisions D3 and D4 are open). `test/boot.py`'s smoke says how far the oracle gets on its own.

A BUILD PRODUCT OF ITS OWN (`build/midboot.bin`, `make midboot`). `preinit_snapshot.py` and `boot_snapshot.py` are
imported and NOT EDITED: they are prerequisites of the five pre-init captures' keys, and an edit would capture all
five again. That is why the file's trailer is spelt here (the pre-init file's layout, its own magic) rather than
taken from a parameter of theirs.

THE FILE: the megabyte; THE REGISTERS (`preinit_snapshot.REGISTER_NAMES`: the machine stops in SUPERVISOR mode, on
the BIOS's own stack at its top `$755a` — every `bsr` of the boot has returned); the shifter's palette and resolution.

WHAT TWO CAPTURES DISAGREE ABOUT — `MASK`, measured with `--twice` as `preinit_snapshot.MASK` was. The stop is an
INSTRUCTION, reached when the emulated floppy's rotation lets the boot reach it, so the clocks move; and the interrupts
the boot took between `$fc0452` and the stop left frames on the stacks they were taken on. Each region below is named
for what it is. The registers and the palette must agree outside it; `make midboot-twice` says whether they do.
"""
import argparse
import struct
import sys
from pathlib import Path

import boot_snapshot                                              # the MACHINE: its arguments, ROM and blank floppy
import preinit_snapshot                                           # the METHOD: registers read off Hatari's dump
from boot_snapshot import RECREATE, ST_RAM_BYTES, differing_fields
from hatari_headless import HeadlessSession, action_file, await_file, log_faults   # (boot_snapshot put it on the path)

import addrs                                                      # noqa: E402

STOP = 0xfc047a                         # the BIOS's `tst.w _cmdload`: the boot's tail, AUTO and the launch, begins here
STOP_INSTRUCTION = bytes.fromhex("4a7900000482")    # `tst.w $482.l`, read off the ROM image before a capture is taken
BIOS_STACK_TOP = preinit_snapshot.BIOS_STACK_TOP    # `$fc02c6 lea $755a,sp`: the ISP every `bsr` of the boot returns to
REGISTER_NAMES = preinit_snapshot.REGISTER_NAMES
SR_SUPERVISOR = addrs.SR_SUPERVISOR
IO_AT, IO_BYTES = preinit_snapshot.IO_AT, preinit_snapshot.IO_BYTES

MAGIC = b"TOS102US mid-boot machine 1\0"
_TRAILER = struct.Struct(f">{len(MAGIC)}s{len(REGISTER_NAMES)}I{IO_BYTES}s")
FILE_BYTES = ST_RAM_BYTES + _TRAILER.size
MidBoot = preinit_snapshot.PreInit      # (ram, registers, io): the same three parts as a pre-init machine's

# ---- what two captures may legitimately differ in --------------------------------------------------------------------------
# MEASURED 2026-10-29 over THIRTY independent boots (fifteen `--twice` pairs, the last `make midboot-twice`'s; the first
# fourteen pairs also cross-compared pairwise): ALL the bytes that differ lie inside the regions below (85 distinct
# bytes over the cross-compared ones), and the registers (SR $2314, ISP $755a) and the palette agree in every one;
# `_hz_200` stood between 320 and 358. By region: the clocks (2 + 1 bytes), the floppy's VBL words (5), the
# timer-C divider (2), GEMDOS's accumulator (1), the milliseconds (1) — and the BIOS's own stack (73 bytes, `$74b5` to
# `$7555`: the frames of the interrupts the boot took on it, the deepest 165 bytes under its top).
# THE STACKS ARE MASKED AS WHAT THEY ARE, TO THEIR TOPS, as `preinit_snapshot.MASK`'s are — not as the bytes these boots
# showed: GEMDOS's own (every `trap #1` reloads SP at `$16ce`; no capture here differed in it) and the BIOS's own, from
# STACK_DEAD_BYTES under its top. GEMDOS's time of day is masked by nature too (two-second steps; none moved here).
# `test/test_boot_harness.py` holds the capture to the BIOS stack's top (read off the ROM's `lea`) and holds that
# nothing was stored for as far again below its floor; and that a run of the ROM from a capture whose masked bytes
# are NOISE takes the same instructions to the same registers and the same machine outside the mask.
STACK_DEAD_BYTES = preinit_snapshot.STACK_DEAD_BYTES
MASK = (
    (0x000462, 0x008, "_vbclock and _frclock: the vertical blanks counted"),
    (0x0004ba, 0x004, "_hz_200: the 200 Hz ticks counted"),
    (0x0009f8, 0x010, "the floppy's vertical-blank service's own words ($fc1bc4: the write-protect latches, the motor)"),
    (0x000e88, 0x002, "the timer-C divider: which of its four states the 200 Hz tick left it in"),
    (preinit_snapshot.GEMDOS_STACK_FLOOR, preinit_snapshot.GEMDOS_STACK_TOP - preinit_snapshot.GEMDOS_STACK_FLOOR,
     "dead frames of GEMDOS's own stack, to its top at $16ce (`movea.l #$16ce,sp` at every `trap #1`)"),
    (0x0068fc, 0x002, "GEMDOS's 20 ms accumulator, advanced by the 50 Hz tick"),
    (BIOS_STACK_TOP - STACK_DEAD_BYTES, STACK_DEAD_BYTES,
     "dead frames of the BIOS's own stack, below its top at $755a — the ISP at the stop"),
    (0x0075b0, 0x002, "GEMDOS's time of day, in two-second steps"),
    (0x00879c, 0x004, "the milliseconds the 50 Hz tick has counted"),
)


def midboot_path(recreate=RECREATE):
    """Where a capture lands. `build/` is gitignored: the ROM is Atari's and so is its RAM image."""
    return recreate / "build" / "midboot.bin"


def packed(machine):
    """`machine` as the file's bytes."""
    assert len(machine.ram) == ST_RAM_BYTES and len(machine.io) == IO_BYTES
    return bytes(machine.ram) + _TRAILER.pack(MAGIC, *(machine.registers[name] for name in REGISTER_NAMES), machine.io)


def unpacked(data):
    """The `MidBoot` a file's bytes hold; refused by name where they are not one."""
    if len(data) != FILE_BYTES or data[ST_RAM_BYTES:ST_RAM_BYTES + len(MAGIC)] != MAGIC:
        raise ValueError(f"not a mid-boot machine: {len(data)} bytes where one is {FILE_BYTES}, or another magic — "
                         f"capture it again (`make midboot`)")
    _magic, *registers, io = _TRAILER.unpack_from(data, ST_RAM_BYTES)
    return MidBoot(bytes(data[:ST_RAM_BYTES]), dict(zip(REGISTER_NAMES, registers)), io)


def load(path=None):
    """The mid-boot machine `make midboot` captured."""
    path = midboot_path() if path is None else Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is not there: the mid-boot machine is a build product — `make midboot` "
                                f"captures it (a few seconds of headless Hatari)")
    return unpacked(path.read_bytes())


def masked(ram):
    """`ram` with every MASK field zeroed — the part of a mid-boot machine two captures must agree on."""
    out = bytearray(ram)
    for address, length, _ in MASK:
        out[address:address + length] = bytes(length)
    return bytes(out)


def disagreements(one, other):
    """What two captures disagree about that the MASK does not excuse: `("the RAM outside the mask", "the register
    <name>", ..., "the shifter bytes")`, empty where they agree."""
    differing = ["the RAM outside the mask"] if masked(one.ram) != masked(other.ram) else []
    differing += [f"the register {name}" for name in REGISTER_NAMES if one.registers[name] != other.registers[name]]
    return tuple(differing + (["the shifter bytes"] if one.io != other.io else []))


def _vet_the_rom_stops_there(rom):
    """Refuse a ROM whose instruction at STOP is not `tst.w _cmdload`: the stop would be another instant of the boot."""
    at = STOP - addrs.ROM_BASE
    if rom[at:at + len(STOP_INSTRUCTION)] != STOP_INSTRUCTION:
        raise SystemExit(f"the ROM holds {rom[at:at + len(STOP_INSTRUCTION)].hex()} at {STOP:#x}, not `tst.w $482` "
                         f"({STOP_INSTRUCTION.hex()}): this is not the boot's tail")


def _vet_stopped_at_the_boot_s_tail(machine):
    """Refuse a capture that is not the boot standing at STOP in supervisor mode on the BIOS's stack, at its top."""
    registers = machine.registers
    if registers["pc"] != STOP:
        raise SystemExit(f"the capture stopped at PC {registers['pc']:#x}, not {STOP:#x}")
    if not registers["sr"] & SR_SUPERVISOR or registers["isp"] != BIOS_STACK_TOP:
        raise SystemExit(f"the capture stopped with SR {registers['sr']:#06x} and ISP {registers['isp']:#x}: the boot "
                         f"stands there in supervisor mode with every `bsr` returned, on {BIOS_STACK_TOP:#x}")


def capture(destination, work):
    """Boot the original ROM headless with the snapshot's blank floppy, stop at STOP, dump the machine. Answers the
    `MidBoot`, and writes it."""
    _vet_the_rom_stops_there(boot_snapshot.ROM.read_bytes())
    # ABSOLUTE paths, and `:trace` on the breakpoint: `boot_snapshot.capture` says why, for both.
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ram_dump, io_dump, log = work / "midboot_ram.dump", work / "midboot_io.dump", work / "midboot.log"
    for stale in (ram_dump, io_dump):
        stale.unlink(missing_ok=True)

    # The I/O dump FIRST and the megabyte last: the file awaited is the one written last.
    clause = action_file(work, "midboot_dump.txt", "r", f"savebin {io_dump} ${IO_AT:x} ${IO_BYTES:x}",
                         f"savebin {ram_dump} $0 ${ST_RAM_BYTES:x}")
    argv = ["hatari", *boot_snapshot.MACHINE_ARGUMENTS, "--tos", str(boot_snapshot.ROM),
            "--disk-a", str(boot_snapshot.blank_disk(work)), "--confirm-quit", "false"]
    session = HeadlessSession(argv, log, work / "midboot.fifo", work)
    try:
        session.arm(f"b pc = ${STOP:x} :once :trace {clause}")
        if await_file(session, ram_dump, "booting to the BIOS's _cmdload test", minimum_bytes=ST_RAM_BYTES) is None:
            raise SystemExit(f"the machine never reached {STOP:#x} — see {log}")
        machine = MidBoot(ram_dump.read_bytes(), preinit_snapshot.registers_in(log.read_text(errors="replace")),
                          io_dump.read_bytes())
    finally:
        session.close()

    faults = log_faults(log)
    if faults:
        raise SystemExit(f"Hatari reported a fault during the boot: {faults}")
    _vet_stopped_at_the_boot_s_tail(machine)
    destination.write_bytes(packed(machine))
    return machine


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=midboot_path(), help="where it is written (build/midboot.bin)")
    parser.add_argument("--work", type=Path, default=RECREATE / "build" / "midboot_snapshot",
                        help="scratch directory for the emulator's log, FIFO and action files")
    parser.add_argument("--twice", action="store_true", help="capture a second time and report which bytes differ")
    args = parser.parse_args(argv)

    machine = capture(args.out, args.work)
    print(f"captured the mid-boot machine -> {args.out}")
    print("  " + "  ".join(f"{name}={machine.registers[name]:x}" for name in ("pc", "sr", "usp", "isp", "d0", "a6")))
    if not args.twice:
        return 0
    again = capture(args.out.with_suffix(".second.bin"), Path(args.work).with_name(args.work.name + "2"))
    runs = differing_fields(machine.ram, again.ram)
    print(f"\ntwo captures' RAM differs in {sum(length for _, length in runs)} byte(s), {len(runs)} run(s):")
    for address, length in runs:
        named = [name for base, size, name in MASK if base <= address < base + size]
        print(f"  ${address:06x} +{length:<3d} {named[0] if named else 'UNMASKED'}")
    differing = disagreements(machine, again)
    for what in differing:
        print(f"  DIFFERS: {what}")
    print("outside the recorded MASK, the registers and the palette: " + ("THEY DIFFER" if differing else "identical"))
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
