r"""THE BOOT'S HEAD ON BOTH SHORES (boot B1, `test_boot_head.py`): the ROM's own `[$fc0030, $fc02cc)` and OUR byte-
transcribed head (`src/boot/head/head.S`, ruling D7) run from one machine, slice by slice, and held equal.

THE USER'S RULINGS (2026-10-29) THIS MODULE STANDS ON: D7 "Byte-transcribed .S"; D8 (the WARM and COLD machines,
`boot.py`); D9 "Stretch rows" (each slice priced on its own cycles, `bench/tier3.py`'s boot-slice rows); "ROM-window
overlay" (our head is laid inside the ROM window over a copy of the image — `boot.overlaid`, A LABELLED STAGING — and
a run of ours that executes the ROM's own head is refused by name); "Own link rule" (`build/boothead/`, the
Makefile's rule: no other blob holds the head).

THE PRODUCT (`product`): `build/boothead/head.bin`, the head linked at `HEAD_LAID_AT` (`include/boot/head.h`), and its
ELF's symbols — `boot_head` at the laid address and the slices' entries where the ROM has them, by offset.

A SLICE (`SLICES`): the ROM's head from one cut to the next, on one arm — H1 `[reset, $fc00da)` and H3
`[$fc0206, $fc02cc)` both arms alike, H2 `[$fc00da, $fc0206)` the warm arm's fourteen instructions or the cold arm's
sizing (D1 open: on the oracle's flat megabyte, not an ST's answer). Each is entered from THE ROM'S OWN MACHINE AT ITS
START (`start_of`: the machine the ROM's previous slice left, the reset's for H1), so a slice of ours answers for itself
alone. OUR SIDE is entered at our instruction where the ROM's lies (by offset: the head is byte-pinned), with every
return link the head holds mapped the same way (`ours_of`): THE PC AND A6 BY OFFSET, as the orchestrator's call has it.

WHAT IS HELD (`differences`): the whole register file (the PC and A6 by offset), the megabyte (our head lies in no
byte of it), the addresses STORED (a clear of a byte already zero is seen here and not in the RAM), every ordered
ledger (hardware writes, declared I/O reads, modelled hardware reads, PSG accesses), the bus-error frames, the
instruction count and the cycles. `reset` (D6) is held by the byte pin and the count alone.
"""
import functools
from collections import namedtuple
from pathlib import Path

from harness import emu

import boot
import layouts
import transcription

RECREATE = Path(__file__).resolve().parents[1]
HEAD_H = RECREATE / "include" / "boot" / "head.h"
PRODUCT_DIRECTORY = RECREATE / "build" / "boothead"
PRODUCT_BIN, PRODUCT_ELF = PRODUCT_DIRECTORY / "head.bin", PRODUCT_DIRECTORY / "head.elf"
CONSTANTS = layouts.parse_constants((HEAD_H,))
LAID_AT = CONSTANTS["HEAD_LAID_AT"]
HEAD_LO, HEAD_HI = boot.THE_ROM_S_HEAD
SYMBOL = "boot_head"
# The registers a head address may be held in when a slice ends: the PC, and A6 — the return link `lea <ret>(pc),a6`
# leaves (the orchestrator's call: compared by offset, like the PC).
LINKS = ("pc", "a6")


# ---- THE PRODUCT ----------------------------------------------------------------------------------------------------
@functools.cache
def product():
    """`(base, bytes)` of `build/boothead/` — refused by name unless `boot_head` lies at `HEAD_LAID_AT` and the flat
    file is the head's length (`make boothead`)."""
    assert PRODUCT_BIN.is_file() and PRODUCT_ELF.is_file(), f"{PRODUCT_DIRECTORY} is not built: `make boothead`"
    symbols = {symbol.name: symbol.start for symbol in transcription.symbol_table(PRODUCT_ELF)}
    held = PRODUCT_BIN.read_bytes()
    assert symbols.get(SYMBOL) == LAID_AT, (
        f"{PRODUCT_ELF}: `{SYMBOL}` lies at {symbols.get(SYMBOL)!r}, not HEAD_LAID_AT {LAID_AT:#x} — a stale build")
    assert len(held) == HEAD_HI - HEAD_LO, f"{PRODUCT_BIN} is {len(held)} bytes, the head {HEAD_HI - HEAD_LO}"
    return LAID_AT, held


def product_symbols():
    """`{name: address}` of every symbol the head's ELF defines."""
    return {symbol.name: symbol.start for symbol in transcription.symbol_table(PRODUCT_ELF)}


def overlay(code=None):
    """THE STAGING our side runs on: the product (or `code`, a case's own bytes) laid over the ROM window at
    HEAD_LAID_AT (`boot.overlaid`)."""
    return boot.overlaid(LAID_AT, product()[1] if code is None else code)


# ---- WHERE OUR INSTRUCTION LIES --------------------------------------------------------------------------------------
def in_the_head(address):
    """Is `address` the ROM's head's — its end included: the head's last slice stops there (`lea $755a,sp` done)?"""
    return HEAD_LO <= address <= HEAD_HI


def ours(rom_address):
    """Where our head holds the ROM's instruction at `rom_address` (the byte pin is what makes it so)."""
    assert in_the_head(rom_address), f"{rom_address:#x} is no address of the ROM's head"
    return LAID_AT + rom_address - HEAD_LO


def mapped(registers):
    """`registers` with each return link and the PC that lies in the ROM's head moved to ours, by offset."""
    return {name: ours(value) if name in LINKS and in_the_head(value) else value for name, value in registers.items()}


def ours_of(machine):
    """`machine` entered on OUR side: its links mapped (`mapped`) — everything else as it holds it."""
    return machine._replace(registers=mapped(machine.registers))


# ---- THE SLICES ---------------------------------------------------------------------------------------------------
Cut = namedtuple("Cut", "name start stop")
H1 = Cut("H1", boot.RESET_PC, boot.HEAD_FIRST_ENDS)
H2 = Cut("H2", boot.HEAD_FIRST_ENDS, boot.WARM_ARM)
H3 = Cut("H3", boot.WARM_ARM, boot.HEAD_ENDS)
CUTS = (H1, H2, H3)
ARMS = {boot.WARM: boot.warm_machine, boot.COLD: boot.cold_machine}
HeadSlice = namedtuple("HeadSlice", "cut arm")
SLICES = {f"boot head {cut.name}, {arm}": HeadSlice(cut, arm) for arm in ARMS for cut in CUTS}


@functools.cache
def _the_rom_s_run_to(arm, stop):
    """The ROM's own head run on `arm` from the reset to `stop`, cut at every cut on the way: the machine at `stop`."""
    machine = ARMS[arm]()
    for cut in CUTS:
        if cut.start == stop:
            return machine
        machine = boot.run(machine, {cut.stop}).machine
    raise AssertionError(f"{stop:#x} is no cut of the head")


def start_of(head_slice):
    """THE ROM'S OWN MACHINE where `head_slice` begins: the reset's on its arm for H1, else the one the ROM's previous
    slice left (refused by the runner if that slice did not arrive)."""
    return _the_rom_s_run_to(head_slice.arm, head_slice.cut.start)


def the_rom_s(head_slice, machine=None, profiled=False):
    """The ROM's own slice from `machine` (its start, by default) — profiled on request (`own_cycles`)."""
    machine = start_of(head_slice) if machine is None else machine
    if not profiled:
        return boot.run(machine, {head_slice.cut.stop})
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        return boot.run(machine, {head_slice.cut.stop})
    finally:
        emu.prof_enable(False)


def our_side(head_slice, machine=None, code=None):
    """OUR slice from the same machine: entered at our instruction where the ROM's lies, its links mapped, on the
    overlay (the product, or `code`), stopped at our instruction where the ROM's slice stops. The run is profiled
    (`boot.run`'s `laid`): its profile is left for the caller."""
    machine = start_of(head_slice) if machine is None else machine
    return boot.run(ours_of(machine), {ours(head_slice.cut.stop)}, laid=overlay(code))


# ---- WHAT IS HELD ---------------------------------------------------------------------------------------------------
SURFACES = ("stop", "registers", "ram", "stored", "hardware_writes", "io_reads", "hardware_reads", "psg_events", "faults",
            "instructions", "cycles")


def differences(the_rom_s_slice, our_slice):
    """Every surface `our_slice` differs from `the_rom_s_slice` on, by name (none: held equal) — the stop and the
    registers compared with the ROM's mapped to ours (`mapped`)."""
    expected = {"stop": ours(the_rom_s_slice.stop), "registers": mapped(the_rom_s_slice.machine.registers),
                "ram": the_rom_s_slice.machine.ram}
    held = {"stop": our_slice.stop, "registers": our_slice.machine.registers, "ram": our_slice.machine.ram}
    found = []
    for surface in SURFACES:
        theirs = expected.get(surface, getattr(the_rom_s_slice, surface, None))
        mine = held.get(surface, getattr(our_slice, surface, None))
        if theirs != mine:
            found.append(_described(surface, theirs, mine))
    return found


def _described(surface, theirs, mine):
    if surface == "registers":
        named = {name: (f"{theirs[name]:#x}", f"{mine[name]:#x}") for name in theirs if theirs[name] != mine[name]}
        return f"registers {named} (the ROM's mapped, ours)"
    if surface == "ram":
        first = next(at for at, (one, other) in enumerate(zip(theirs, mine)) if one != other)
        return f"ram, first at {first:#x}"
    if isinstance(theirs, int):
        return f"{surface}: the ROM's {theirs:#x}, ours {mine:#x}" if surface == "stop" else f"{surface}: the ROM's {theirs}, ours {mine}"
    return f"{surface}: {len(theirs or ())} against ours {len(mine or ())}"


# ---- ITS PRICE (ruling D9: each slice on its own cycles, `bench/tier3.py`) ----------------------------------------------------
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """One slice measured on both shores: the two `boot.Slice`s, `own` (the ROM's cycles at its head's PCs,
ours at our head's — each shore's own) and `rest` (the run's other cycles on each: the ROM's code both run in place —
the memory-valid check, the bank test — and the entry's segment), held equal."""


def priced(head_slice):
    """THE SLICE PRICED (above): both shores run, every surface held equal (refused by name otherwise), each shore's
    own cycles read off its run's profile. Our run is the last made: its profile is the one left."""
    the_rom_s_slice = the_rom_s(head_slice, profiled=True)
    the_rom_s_own = emu.prof_cycles(HEAD_LO, HEAD_HI)
    our_slice = our_side(head_slice)
    our_own = emu.prof_cycles(LAID_AT, LAID_AT + HEAD_HI - HEAD_LO)
    found = differences(the_rom_s_slice, our_slice)
    assert not found, f"{name_of(head_slice)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (our_slice.cycles - our_own, the_rom_s_slice.cycles - the_rom_s_own)
    assert rest[0] == rest[1], f"{name_of(head_slice)}: the code both run cost ours {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(the_rom_s_slice, our_slice, (our_own, the_rom_s_own), rest[0])


def name_of(head_slice):
    return next(name for name, each in SLICES.items() if each == head_slice)
