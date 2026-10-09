#!/usr/bin/env python3
"""Capture THE PRE-INIT MACHINE: the machine at the AES's entry, before any GEM init has run.

    python tools/preinit_snapshot.py                 # capture build/preinit.bin
    python tools/preinit_snapshot.py --twice         # capture twice and report what differs

`tools/boot_snapshot.py`'s machine — the same ROM, the same Hatari arguments, the same blank floppy, read from that
module and not respelled — stopped ONE BOOT EARLIER: at `gem_entry` (`$fd9eca`), the instruction the BIOS hands the
machine to once GEMDOS is up and the AUTO folder has been searched (`exec_os`, `$4fe`, names it; the capture is
refused unless the dumped RAM's own `exec_os` is the PC it stopped at). Nothing of GEM has run: no AES variable is
written, no process exists, the AES's basepage owns the whole TPA. It is what the ROM's own `gem_main` is run FROM
(`test/aes_boot.py`) — and, later, ours.

WHY A HATARI CAPTURE AND NOT THE ORACLE RUN TO IT. The oracle has no earlier real state to start from: the only other
machine this project holds is the post-boot snapshot, which lies AFTER this point, and a run from reset would have to
serve the whole hardware bring-up (the memory sizing's bus errors, the floppy controller's transactions, the MFP's
timers under real interrupts) that `TRAP_MODEL.md` puts out of the model's reach. A PC breakpoint is one line of
Hatari's debugger, fires once per boot, and costs four seconds.

AN ARTIFACT OF ITS OWN (`build/preinit.bin`, `make preinit`): `build/boot_ram.bin`, its tool, its stop point and its
MASK are untouched — this module imports that one and changes nothing in it.

WHAT THE FILE HOLDS, because a machine at an instruction is more than its RAM:
  * the megabyte of RAM;
  * THE REGISTERS at the stop, as Hatari's `r` prints them — D0-D7, A0-A6, both stack pointers, SR, PC. `gem_entry`
    is entered in USER mode on the stack `Pexec` left at the top of the TPA, and its first instructions read the
    basepage's address off it;
  * THE SHIFTER'S PALETTE AND RESOLUTION as the debugger reads them out of the I/O page: the sixteen colour words and
    the resolution byte are the hardware reads GEM's start-up makes (`vq_color` over every pen, `Getrez`), and what
    they answer is the machine's, not RAM's.

WHAT TWO CAPTURES DISAGREE ABOUT — `MASK`, measured as `boot_snapshot.MASK` was (`--twice`). UNLIKE THE POST-BOOT
SNAPSHOT, THE CLOCKS MOVE: that one stops at a fixed count of vertical blanks, this one at an INSTRUCTION, and when
the boot reaches it depends on where the (emulated) disk stood in its rotation as each sector was asked for —
fourteen captures stopped with `_hz_200` between 396 and 450. So the mask is two things: every clock the tick
advances (GEMDOS's time of day among them), and what the floppy driver left behind (its scratch, its vertical-blank
service's words, the dead frames of the stack the OS ran it on). The registers, the palette and every byte outside
the mask are the same in every capture taken.
"""
import argparse
import re
import struct
import sys
from collections import namedtuple
from pathlib import Path

import boot_snapshot                                              # the MACHINE: its arguments, ROM and blank floppy
from boot_snapshot import RECREATE, ST_RAM_BYTES, differing_fields
from hatari_headless import HeadlessSession, action_file, await_file, log_faults   # (boot_snapshot put it on the path)

import addrs                                                      # noqa: E402

GEM_ENTRY = addrs.AES_ROM_GEM_ENTRY
EXEC_OS = 0x4fe                         # long: `exec_os`, the system variable that names the shell the BIOS enters

# ---- the registers --------------------------------------------------------------------------------------------------
# In the order the file keeps them. A7 is not among them: it is USP or ISP, whichever SR's supervisor bit names.
DATA_REGISTERS = tuple(f"d{n}" for n in range(8))
ADDRESS_REGISTERS = tuple(f"a{n}" for n in range(7))
REGISTER_NAMES = (*DATA_REGISTERS, *ADDRESS_REGISTERS, "usp", "isp", "sr", "pc")
SR_SUPERVISOR = addrs.SR_SUPERVISOR

# ---- the hardware state kept beside the RAM ---------------------------------------------------------------------------
SHIFTER_PALETTE = addrs.SHIFTER_PALETTE # sixteen colour words
PALETTE_BYTES = addrs.SHIFTER_PALETTE_ENTRIES * 2
SHIFTER_RESOLUTION = addrs.SHIFTER_RESOLUTION
IO_AT = SHIFTER_PALETTE                 # the span of the I/O page the capture dumps: the palette, the resolution byte
IO_BYTES = SHIFTER_RESOLUTION + 1 - IO_AT

# ---- the file -------------------------------------------------------------------------------------------------------
MAGIC = b"TOS102US pre-init machine 1\0"
_TRAILER = struct.Struct(f">{len(MAGIC)}s{len(REGISTER_NAMES)}I{IO_BYTES}s")
FILE_BYTES = ST_RAM_BYTES + _TRAILER.size

PreInit = namedtuple("PreInit", "ram registers io")
PreInit.__doc__ = """The pre-init machine: `ram` (the megabyte), `registers` (`{name: value}` over REGISTER_NAMES) and
`io` (the bytes of the I/O page from IO_AT: the palette, the resolution byte)."""

# ---- what two captures may legitimately differ in ---------------------------------------------------------------------
# MEASURED over eighteen independent boots (fourteen with the blank disk, four with the accessories'), each kind
# cross-compared: 283 distinct bytes with the blank disk, 12 to 172 a pair. The regions
# below are the union, each clock as the whole field it is and the driver's bytes coalesced across gaps of 0x100.
# Two of the driver's regions are `boot_snapshot.MASK`'s own, met a boot earlier ($1464 and $74c0 there; a few bytes
# wider here).
#
# THE RULE THIS BUYS is `boot_snapshot.MASK`'s: nothing derived from this machine may depend on a byte in here. And
# that is a surface: `test/test_aes_boot.py` boots the ROM from a pre-init machine whose masked bytes are NOISE and
# holds the machine it reaches equal, outside these regions, to the one the capture's own bytes reach — the same
# instruction count, the same registers. (MEASURED: the boot reads none of them. Between two captures the booted
# machines differ ONLY in bytes of this mask, carried through untouched.)
MASK = (
    (0x000462, 0x008, "_vbclock and _frclock: the vertical blanks counted"),
    (0x0004ba, 0x004, "_hz_200: the 200 Hz ticks counted"),
    (0x0009f8, 0x010, "the floppy's vertical-blank service's own words ($fc1bc4: the write-protect latches, the motor)"),
    (0x000e88, 0x002, "the timer-C divider: which of its four states the 200 Hz tick left it in"),
    (0x001455, 0x221, "dead frames of the OS's own stack, to its top at $1676 (boot_snapshot's $1464 region, wider)"),
    (0x0068fc, 0x002, "GEMDOS's 20 ms accumulator, advanced by the 50 Hz tick"),
    (0x0074b8, 0x05e, "the floppy driver's scratch (boot_snapshot's $74c0 region, wider at both ends)"),
    (0x0075b0, 0x002, "GEMDOS's time of day, in two-second steps"),
    (0x00879c, 0x004, "the milliseconds the 50 Hz tick has counted"),
)


def preinit_path(recreate=RECREATE):
    """Where a capture lands. `build/` is gitignored: the ROM is Atari's and so is its RAM image."""
    return recreate / "build" / "preinit.bin"


def accessory_path(recreate=RECREATE):
    """...and THE ACCESSORY PRE-INIT MACHINE's: the same stop of a boot with `tools/accessory_disk.py`'s floppy in
    drive A: FROM POWER-ON (`make preinit-acc`) — so GEMDOS's FAT and root cache, the driver's record and its
    serial are the ones a real machine has for that disk at `gem_entry`, and nothing is swapped in."""
    return recreate / "build" / "preinit_acc.bin"


def packed(machine):
    """`machine` as the file's bytes."""
    assert len(machine.ram) == ST_RAM_BYTES and len(machine.io) == IO_BYTES
    return bytes(machine.ram) + _TRAILER.pack(MAGIC, *(machine.registers[name] for name in REGISTER_NAMES), machine.io)


def unpacked(data):
    """The `PreInit` a file's bytes hold; refused by name where they are not one."""
    if len(data) != FILE_BYTES or data[ST_RAM_BYTES:ST_RAM_BYTES + len(MAGIC)] != MAGIC:
        raise ValueError(f"not a pre-init machine: {len(data)} bytes where one is {FILE_BYTES}, or another magic — "
                         f"capture it again (`make preinit`)")
    _magic, *registers, io = _TRAILER.unpack_from(data, ST_RAM_BYTES)
    return PreInit(bytes(data[:ST_RAM_BYTES]), dict(zip(REGISTER_NAMES, registers)), io)


def load(path=None):
    """The pre-init machine `make preinit` captured."""
    path = preinit_path() if path is None else Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} is not there: the pre-init machine is a build product — `make preinit` "
                                f"captures it (four seconds of headless Hatari)")
    return unpacked(path.read_bytes())


def masked(ram):
    """`ram` with every MASK field zeroed — the part of a pre-init machine two captures must agree on."""
    out = bytearray(ram)
    for address, length, _ in MASK:
        out[address:address + length] = bytes(length)
    return bytes(out)


# ---- reading Hatari's register dump -------------------------------------------------------------------------------------
_NAMED_HEX = re.compile(r"\b(D[0-7]|A[0-7]|USP|ISP)\s+([0-9A-Fa-f]{8})\b")
_STATUS = re.compile(r"\bSR=([0-9A-Fa-f]{4})\b")


def registers_in(log_text):
    """The register file of the LAST dump in a Hatari log (`r`): `{name: value}` over REGISTER_NAMES, the PC the
    address of the instruction ABOUT TO RUN (the line above `Next PC:` opens with it)."""
    lines = log_text.splitlines()
    ends = [index for index, line in enumerate(lines) if line.startswith("Next PC:")]
    if not ends:
        raise SystemExit("Hatari printed no register dump at the stop — the breakpoint never fired")
    end = ends[-1]
    starts = [index for index in range(end) if lines[index].lstrip().startswith("D0 ")]
    dump = "\n".join(lines[starts[-1]:end])
    found = {name.lower(): int(value, 16) for name, value in _NAMED_HEX.findall(dump)}
    found["sr"] = int(_STATUS.search(dump).group(1), 16)
    found["pc"] = int(lines[end - 1].split()[0], 16)
    active = "isp" if found["sr"] & SR_SUPERVISOR else "usp"
    if found.pop("a7") != found[active]:
        raise SystemExit(f"the register dump's A7 is not its {active.upper()}: the dump is not read as it is printed")
    missing = [name for name in REGISTER_NAMES if name not in found]
    if missing:
        raise SystemExit(f"the register dump names no {missing}")
    return {name: found[name] for name in REGISTER_NAMES}


def _vet_stopped_at_the_shell_s_entry(machine):
    """Refuse a capture that is not the machine about to run `gem_entry`'s first instruction, in user mode, as the
    machine's OWN `exec_os` names it."""
    named = struct.unpack_from(">I", machine.ram, EXEC_OS)[0]
    pc, sr = machine.registers["pc"], machine.registers["sr"]
    if not pc == named == GEM_ENTRY:
        raise SystemExit(f"the capture stopped at PC {pc:#x}; this machine's exec_os (${EXEC_OS:x}) names {named:#x} "
                         f"and gem_entry is {GEM_ENTRY:#x}. It would be an arbitrary instant, not the AES's entry")
    if sr & SR_SUPERVISOR:
        raise SystemExit(f"the capture stopped in supervisor mode (SR {sr:#06x}): gem_entry is entered as a program")


def capture(destination, work, disk=None):
    """Boot the original ROM headless — `disk` in drive A: (a floppy image's path), or the snapshot's blank one —
    stop at `gem_entry`, dump the machine. Answers the `PreInit`, and writes it."""
    # ABSOLUTE paths, and `:trace` on the breakpoint: `boot_snapshot.capture` says why, for both.
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ram_dump, io_dump, log = work / "preinit_ram.dump", work / "preinit_io.dump", work / "preinit.log"
    for stale in (ram_dump, io_dump):
        stale.unlink(missing_ok=True)

    # The I/O dump FIRST and the megabyte last: the file awaited is the one written last.
    clause = action_file(work, "preinit_dump.txt", "r", f"savebin {io_dump} ${IO_AT:x} ${IO_BYTES:x}",
                         f"savebin {ram_dump} $0 ${ST_RAM_BYTES:x}")
    argv = ["hatari", *boot_snapshot.MACHINE_ARGUMENTS, "--tos", str(boot_snapshot.ROM),
            "--disk-a", str(Path(disk).resolve() if disk else boot_snapshot.blank_disk(work)), "--confirm-quit", "false"]
    session = HeadlessSession(argv, log, work / "preinit.fifo", work)
    try:
        session.arm(f"b pc = ${GEM_ENTRY:x} :once :trace {clause}")
        if await_file(session, ram_dump, "booting to the AES's entry", minimum_bytes=ST_RAM_BYTES) is None:
            raise SystemExit(f"the machine never reached gem_entry — see {log}")
        machine = PreInit(ram_dump.read_bytes(), registers_in(log.read_text(errors="replace")), io_dump.read_bytes())
    finally:
        session.close()

    faults = log_faults(log)
    if faults:
        raise SystemExit(f"Hatari reported a fault during the boot: {faults}")
    _vet_stopped_at_the_shell_s_entry(machine)
    destination.write_bytes(packed(machine))
    return machine


# ---- THE CROSS-CHECK: the accessory machine against a real boot of the same disk (opt-in; no suite runs it) ---------------
# Where a differing byte lies, for the report: `(start, what)`, in address order — each region runs to the next one's.
REGIONS = (
    (0x000000, "exception vectors"),
    (0x000400, "system variables"),
    (0x000800, "BIOS, XBIOS, Line-A and VDI variables; the OS's own stack and pool"),
    (0x007000, "the floppy driver's and GEMDOS's variables, records and sector buffers"),
    (0x008900, "AES variables, gem_entry's first stack, the dispatcher's stack"),
    (0x009c58, "the static UDAs (the desk's, the screen manager's, the first accessory's)"),
    (0x00ae5e, "the PD table, CDAs, EVBs, the AES's and the desktop's BSS"),
    (0x00ca00, "the TPA: the AES's basepage, its Malloc'd blocks, the accessories"),
    (0x0f8000, "the screen"),
)
COALESCED_ACROSS = 8                    # bytes of agreement inside one reported run


def _region_of(address):
    return [what for start, what in REGIONS if start <= address][-1]


def cross_check(work, modes):
    """Boot `tools/accessory_disk.py`'s floppy (each accessory in its mode) in Hatari FROM POWER-ON to the desktop —
    `boot_snapshot.capture`, the post-boot snapshot's own procedure, its blank disk replaced — and print what
    `test/aes_boot.py`'s accessory machine for the same modes differs from it in, outside both masks, by region.
    Answers the number of differing bytes.

    NOT A TEST AND NOT PART OF ANY GATE: fifteen seconds of real-time emulation, and a comparison of a machine at
    its FIRST idle with one nine hundred vertical blanks on — what differs is to be READ. MEASURED 2026-10-09, the
    quiet pair: 109 bytes in 14 runs, every one time or interrupts — `colorptr` still pending; `savptr`'s last frame;
    the real driver's own scratch from the sectors it read ($a4a, $1696-$16bf); dead frames on gem_entry's first
    stack, the dispatcher's and the tick glue's; interrupt frames left in the three UDAs' stacks (the second
    accessory's among them); the Line-F handler's mask word. No process, list, basepage, record or buffer of GEMDOS
    differs. (With the disk SWAPPED IN at `gem_entry`, as this harness first did it, 821 bytes differed: GEMDOS's
    two sector buffers, its directory records and each basepage's current-directory byte.)"""
    sys.path.insert(0, str(RECREATE / "test"))
    import derived                                                # noqa: F401  (first: it stamps the tree)
    import aes_boot

    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # `boot_snapshot.capture` boots whatever image stands where it would build its blank one.
    (work / boot_snapshot.BLANK_DISK).write_bytes(aes_boot.accessory_disk_of(*modes))
    real = boot_snapshot.capture(work / "real_boot.bin", work)
    ours, theirs = bytearray(aes_boot.accessory_machine(*modes).ram), bytearray(real)
    for address, length, _ in (*boot_snapshot.MASK, *MASK):
        ours[address:address + length] = theirs[address:address + length] = bytes(length)
    runs = []
    for address, length in differing_fields(bytes(ours), bytes(theirs)):
        if runs and address - sum(runs[-1]) <= COALESCED_ACROSS:
            runs[-1][1] = address + length - runs[-1][0]
        else:
            runs.append([address, length])
    differing = sum(1 for at in range(ST_RAM_BYTES) if ours[at] != theirs[at])
    print(f"the accessory machine (modes {modes}) and a real boot of its disk differ in {differing} byte(s) outside "
          f"both masks, {len(runs)} run(s):")
    for address, length in runs:
        shown = slice(address, address + min(length, 12))
        print(f"  ${address:06x} +{length:<4d} ours {bytes(ours[shown]).hex():24s} real {bytes(theirs[shown]).hex():24s} "
              f"{_region_of(address)}")
    return differing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=preinit_path(), help="where it is written (build/preinit.bin)")
    parser.add_argument("--work", type=Path, default=RECREATE / "build" / "preinit_snapshot",
                        help="scratch directory for the emulator's log, FIFO and action files")
    parser.add_argument("--disk", type=Path, help="the floppy in drive A: from power-on (default: the blank one)")
    parser.add_argument("--twice", action="store_true", help="capture a second time and report which bytes differ")
    parser.add_argument("--cross-check", nargs="*", type=int, metavar="MODE", default=None,
                        help="instead of capturing: boot the accessory disk (each accessory's mode; quiet by default) "
                             "in Hatari to the desktop and report what test/aes_boot.py's machine differs from it in")
    args = parser.parse_args(argv)
    if args.cross_check is not None:
        cross_check(RECREATE / "build" / "preinit_cross_check", tuple(args.cross_check) or (0, 0))
        return 0

    machine = capture(args.out, args.work, args.disk)
    print(f"captured the pre-init machine -> {args.out}")
    print("  " + "  ".join(f"{name}={machine.registers[name]:x}" for name in ("pc", "sr", "usp", "isp", "d0", "a6")))
    if not args.twice:
        return 0
    again = capture(args.out.with_suffix(".second.bin"), Path(args.work).with_name(args.work.name + "2"), args.disk)
    runs = differing_fields(machine.ram, again.ram)
    print(f"\ntwo captures' RAM differs in {sum(length for _, length in runs)} byte(s), {len(runs)} run(s):")
    for address, length in runs:
        named = [name for base, size, name in MASK if base <= address < base + size]
        print(f"  ${address:06x} +{length:<3d} {named[0] if named else 'UNMASKED'}")
    same_elsewhere = (masked(machine.ram) == masked(again.ram) and machine.registers == again.registers
                      and machine.io == again.io)
    print("outside the recorded MASK, the registers and the palette: " + ("identical" if same_elsewhere else "THEY DIFFER"))
    return 0 if same_elsewhere else 1


if __name__ == "__main__":
    raise SystemExit(main())
