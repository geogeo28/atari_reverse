#!/usr/bin/env python3
"""Capture the post-boot RAM snapshot every ROM-mode differential runs over.

A game function's inputs are the .PRG the loader placed; a TOS function's inputs are the MACHINE
the boot left behind — the system variables at $380..$8900, the vector table, the GEMDOS buffers,
the AES's and the desktop's allocations. So the image a `projects/tos102us` differential starts from
is a real 1 MB RAM image, dumped once out of a headless Hatari that booted the ORIGINAL ROM, with
the ROM itself mapped over it at $FC0000 (see `recreate/README.md`, "The image in ROM mode").

    python tools/boot_snapshot.py                 # capture build/boot_ram.bin
    python tools/boot_snapshot.py --twice         # capture twice and report what differs

THE STOP POINT IS THE ROM'S OWN VERTICAL-BLANK HANDLER, AT A FIXED VBL COUNT, with the desktop up
and idle. It is one exact instruction — `$fc06de`, the `addq.l #1,_frclock` the VBL vector points at
— reached at a fixed count of vertical blanks from power-on, which makes the whole capture a
function of the machine and the media and of nothing else. `capture()` proves it stopped there
rather than assuming: it reads the PC out of the register dump Hatari prints and checks it against
the VBL vector in the snapshot itself.

WHY NOT THE DESKTOP'S FIRST `evnt_multi`, the obvious anchor. Two things rule it out, and the second
is the decisive one:

  * Hatari's breakpoint expressions dereference memory only ONE level deep (`b help`:
    "value = [(] <register/symbol/variable name | number> [)]"), and an AES opcode lives two levels
    down — in `control[0]`, where `control` is `((d1))`. The trap itself is expressible
    (`(pc).w = $4e42 && d0 = $c8`); which AES call it is, is not.
  * MEASURED: once the desktop is up and nothing is typed or moved, it blocks inside `evnt_multi`
    and makes NO further AES calls at all. A breakpoint armed after any settling period therefore
    never fires — a 90-second idle run of exactly that shape timed out with the machine sitting at
    the desktop. The desktop's first `evnt_multi` is an instant DURING start-up, not after it, and
    anchoring on it would mean counting AES calls through the start-up sequence.

The VBL handler at an idle desktop is the better anchor for the same purpose: the machine is
quiescent, the instruction is exact, and the count is the only parameter.

WHAT IS NOT DETERMINISTIC, and is therefore the snapshot's documented MASK: not the clocks — those
are bit-identical, because the stop is at a fixed vertical-blank count and Hatari's timing is
cycle-driven — but the PHASE of the AES's and the desktop's idle work at the instant the vertical
blank interrupts it. Three independent boots stopped with different D0/D7/A0/A6/A7, and 1,929 bytes
of dead stack and idle scratch differed. `--twice` is what measures that set, `MASK` below records
it, and `test/test_boot_snapshot.py` is what stops any case depending on a byte inside it.

"""
import argparse
import struct
import sys
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
REVERSE = RECREATE.parents[2]
sys.path.insert(0, str(REVERSE / "tools"))

import st_build                                                   # noqa: E402
from hatari_headless import (HeadlessSession, action_file,        # noqa: E402
                             await_file, log_faults)

sys.path.insert(0, str(RECREATE / "tools"))
import addrs                                                      # noqa: E402

# --- the machine ---------------------------------------------------------------------------------
# FIXED, and spelled here rather than taken from a caller: the snapshot IS the machine, so a capture
# made on another one is a different set of inputs wearing the same file name. 1 MB because that is
# what `phystop` in the dump says and what every address in it was chosen against; `--monitor rgb`
# because the desktop's low-resolution palette and screen base are part of the state; sound off
# because nothing here listens and the mixer only costs wall-clock time.
ROM = REVERSE / "tools" / "hatari" / "TOS102US.img"
MACHINE_ARGUMENTS = ("--machine", "st", "--memsize", "1", "--monitor", "rgb", "--sound", "off")
# How much RAM the dump covers, and the vector slot the stop instruction belongs to: BOTH from
# include/addrs.h, which the reconstruction includes. A second copy here would let a snapshot
# captured from a machine of another size go on calling itself this project's machine.
ST_RAM_BYTES = addrs.ST_RAM_BYTES
VECTOR_VBL = addrs.VECTOR_VBL

# A BLANK, MOUNTABLE floppy in drive A:. TOS 1.02 predates Hatari's GEMDOS directory emulation
# ("Please use at least TOS v1.04 for the HD directory emulation" — hatari_headless's own marker),
# so there is no way to give this machine a hard disk. An EMPTY drive is not the alternative: the
# boot's floppy probe then retries a drive that answers nothing, and how long that takes is exactly
# the kind of timing the snapshot must not depend on. A blank formatted disk answers immediately,
# has no AUTO folder to run and no executable boot sector, so the boot goes straight to the desktop.
BLANK_DISK = "BLANK.ST"

# --- the stop point ------------------------------------------------------------------------------
# How many vertical blanks from power-on the snapshot is taken at. The desktop is drawn and idle
# well before this — measured: it is on screen by VBL ~700 with a blank floppy in A: — and the
# margin is what makes the machine QUIESCENT at the stop rather than mid-redraw. Emulation is real
# time, so at 60 Hz this is also the ~15 s wall-clock cost of one capture.
SETTLE_VBLANKS = 900

# --- what two captures may legitimately differ in -------------------------------------------------
# MEASURED over three independent boots (`--twice`, plus a third capture cross-compared): 1,929
# bytes of a 1 MB machine, 0.18% of it, and NOT the clocks the obvious guess would name. `_hz_200`,
# `_vbclock` and `_frclock` are bit-identical — the stop is at a fixed vertical-blank count and
# Hatari's timing is cycle-driven — and so are the whole screen, the 256-entry vector table, every
# system variable, the GEMDOS buffers and the desktop's data.
#
# What DOES move is the phase of the AES/desktop idle work at the instant the vertical blank
# interrupts it: three boots stopped with different D0/D7/A0/A6/A7, and what differs is the dead
# stack below each stack pointer plus the scratch those idle routines churn. The regions below are
# the UNION over the three pairwise comparisons, coalesced across gaps of up to 0x100 bytes, so they
# are wider than any single pair's difference on purpose — a mask measured from one pair would be
# too narrow for the next capture.
#
# THE RULE THIS BUYS: no case may depend on a byte in here. That is not left to care —
# `test/test_boot_snapshot.py` re-runs every verified function's differential over a snapshot whose
# mask regions are filled with pseudo-random bytes, so a function that reads one fails loudly.
MASK = (
    (0x0009ff, 0x005, "OS scratch below the Line-A variables"),
    (0x001464, 0x1ce, "OS BSS scratch / a dead stack frame"),
    (0x0074c0, 0x054, "OS BSS scratch"),
    (0x008930, 0x2d0, "the supervisor stack, below ISP"),
    (0x009488, 0x0c4, "AES scratch"),
    (0x009fa5, 0x0cf, "AES scratch"),
    (0x00a19b, 0x079, "AES scratch"),
    (0x00a771, 0x06d, "AES scratch"),
    (0x00c7e1, 0x007, "the AES process structure A5 points at"),
    (0x0f7fa2, 0x012, "the desktop's stack, below _memtop"),
)


def snapshot_path(recreate=RECREATE):
    """Where a capture lands. `build/` is gitignored: the ROM is Atari's and so is its RAM image."""
    return recreate / "build" / "boot_ram.bin"


def blank_disk(work):
    """A freshly built 720 KB blank floppy image, so the boot's probe finds the same disk every run."""
    image = Path(work) / BLANK_DISK
    if not image.exists():
        st_build.build(image, [])
    return image


def _masked(ram):
    """`ram` with every MASK field zeroed — the part of a snapshot two captures must agree on."""
    out = bytearray(ram)
    for address, length, _ in MASK:
        out[address:address + length] = bytes(length)
    return bytes(out)


def differing_fields(first, second):
    """Every maximal (address, length) run of bytes two captures disagree on, in address order."""
    runs = []
    at = 0
    while at < len(first):
        if first[at] == second[at]:
            at += 1
            continue
        start = at
        while at < len(first) and first[at] != second[at]:
            at += 1
        runs.append((start, at - start))
    return runs


def _stopped_pc(log_text):
    """The PC at the stop, read out of the register dump the action file's `r` printed.

    Hatari prints `Next PC: <hex>` after the disassembled instruction, and the line above it opens
    with the address of the instruction ABOUT TO RUN — which is the one this wants. Taken from the
    last dump in the log so a re-armed capture reads its own.
    """
    marker = "Next PC:"
    lines = log_text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith(marker):
            return int(lines[index - 1].split()[0], 16)
    raise SystemExit("Hatari printed no register dump at the stop — the breakpoint never fired")


def _vet_stopped_in_the_vbl_handler(ram, pc):
    """Refuse a capture that stopped anywhere but the ROM's vertical-blank handler.

    The breakpoint's own condition can only say "a vertical blank past N"; this is what turns that
    into the exact instruction the snapshot claims (see the module docstring). The expected address
    is read from the snapshot's OWN vector table rather than spelled here, so the check is against
    the machine that was captured and not against a number that could go stale.
    """
    handler = struct.unpack_from(">I", ram, VECTOR_VBL)[0]
    if pc != handler:
        raise SystemExit(f"the capture stopped at PC {pc:#x}, but this machine's vertical-blank "
                         f"vector (${VECTOR_VBL:x}) points at {handler:#x}. The snapshot would be "
                         f"an arbitrary instant rather than the stop point it documents.")
    return handler


def capture(destination, work, settle_vblanks=SETTLE_VBLANKS):
    """Boot the original ROM headless, stop in its VBL handler at `settle_vblanks`, dump RAM.

    Returns the RAM image as `bytes`, and writes it to `destination`.
    """
    # ABSOLUTE, both of them: Hatari CHANGES ITS WORKING DIRECTORY to an action file's directory
    # while it runs it, so a relative `savebin` path inside one resolves somewhere the caller did
    # not mean — measured, as "Cannot open file" on a run that was otherwise perfect.
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    dump = work / "boot_ram.dump"
    dump.unlink(missing_ok=True)
    log = work / "boot_snapshot.log"

    # `r` first, so the stop's PC is in the log and the dump can be checked against it; then the
    # dump itself. `:trace` on the breakpoint is NOT cosmetic: without it Hatari runs the action
    # file AND THEN drops into the interactive debugger, where a headless run sits for ever (the
    # file's own `cont` ends the file, not the debugger entry). Measured on 2.6.1.
    clause = action_file(work, "dump.txt", "r", f"savebin {dump} $0 ${ST_RAM_BYTES:x}")

    argv = ["hatari", *MACHINE_ARGUMENTS, "--tos", str(ROM),
            "--disk-a", str(blank_disk(work)), "--confirm-quit", "false"]
    session = HeadlessSession(argv, log, work / "boot_snapshot.fifo", work)
    try:
        session.arm(f"b VBL > {settle_vblanks} :once :trace {clause}")
        if await_file(session, dump, "booting to the desktop", minimum_bytes=ST_RAM_BYTES) is None:
            raise SystemExit(f"the machine never reached the stop point — see {log}")
        ram = dump.read_bytes()
    finally:
        session.close()

    faults = log_faults(log)
    if faults:
        raise SystemExit(f"Hatari reported a fault during the boot: {faults}")
    _vet_stopped_in_the_vbl_handler(ram, _stopped_pc(log.read_text(errors="replace")))
    destination.write_bytes(ram)
    return ram


def _report(ram):
    """The handful of system variables a reader wants to see to believe a snapshot booted."""
    def long_at(address):
        return struct.unpack_from(">I", ram, address)[0]
    for name in ("SYSVAR_PHYSTOP", "SYSVAR_MEMBOT", "SYSVAR_MEMTOP", "SYSVAR_V_BAS_AD",
                 "SYSVAR_SYSBASE", "VECTOR_TRAP_BIOS", "VECTOR_TRAP_XBIOS"):
        address = getattr(addrs, name)
        print(f"  {name:20s} ${address:03x} = ${long_at(address):08x}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=snapshot_path(),
                        help="where the snapshot is written (default: build/boot_ram.bin)")
    parser.add_argument("--work", type=Path, default=RECREATE / "build" / "boot_snapshot",
                        help="scratch directory for the emulator's log, FIFO and action files")
    parser.add_argument("--settle", type=int, default=SETTLE_VBLANKS,
                        help="vertical blanks to let the machine settle before the stop is armed")
    parser.add_argument("--twice", action="store_true",
                        help="capture a second time and report exactly which bytes differ")
    args = parser.parse_args(argv)

    ram = capture(args.out, args.work, args.settle)
    print(f"captured {len(ram)} bytes -> {args.out}")
    _report(ram)

    if not args.twice:
        return 0
    second = args.out.with_suffix(".second.bin")
    again = capture(second, Path(args.work).with_name("boot_snapshot2"), args.settle)
    runs = differing_fields(ram, again)
    print(f"\ntwo captures differ in {sum(length for _, length in runs)} byte(s), "
          f"{len(runs)} run(s):")
    for address, length in runs:
        named = [name for base, size, name in MASK if base <= address < base + size]
        print(f"  ${address:06x} +{length:<3d} {named[0] if named else 'UNMASKED'}")
    unmasked = _masked(ram) != _masked(again)
    print("outside the recorded MASK: " + ("BYTES DIFFER" if unmasked else "identical"))
    return 1 if unmasked else 0


if __name__ == "__main__":
    raise SystemExit(main())
