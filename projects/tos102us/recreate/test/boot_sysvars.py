r"""THE SYSTEM VARIABLES AND THE VECTOR TABLE ON BOTH SHORES (boot B2, `test_boot_sysvars.py`): the ROM's own
`[$fc02cc, $fc03b6)` — with `$fc0eba`, which it calls — and OUR C (`src/boot/sysvars.c`, entered by
`src/boot/sysvars_entry.S`) run from one machine and held equal on every surface the C can be held on.

THE USER'S RULINGS (2026-10-29) THIS MODULE STANDS ON: D7 (the head `.S`, C after `lea $755a,sp`: the C begins where
the head ends); D8 (the WARM and COLD machines, `boot.py`); D9 "Stretch rows" (the slice priced on each shore's own
cycles, `bench/tier3.py`'s boot C rows). The orchestrator's standing call on D11: a ROM table the code reads or copies
is read where it lies, listed in the boot census (`test_boot_rom_data.py`).

WHERE OUR CODE LIES: IN THE BENCH BLOB, LAID IN RAM AT ITS LINK ADDRESS (`bench_base`, A LABELLED STAGING, `laid`) —
the ordinary sweep, not the head's own link rule: the C stores the handlers THIS BUILD links (the HBL and VBL entries
of `src/bios/isr.S`, the trap entries of `src/bios/trap.S`, the Line-A dispatcher of `src/vdi/entry.S`), so it is
linked where they are. Laid at the slice's start, on the ROM's own machine there: the clears that would erase it (the
cold arm's `$400..phystop`, both arms' `$980..$10000`) are the head's and lie behind; held, the ROM's own slice neither
reads nor stores the blob's span (the same run with and without it) and our run never executes the ROM's own span.

A SLICE (`SLICES`): B2 on each arm, entered from THE ROM'S OWN MACHINE AT `$fc02cc` (the head's own run from the
reset, `boot_head`), stopped at the ROM's `$fc03b6` on both shores — our glue's `jmp` arrives there.

WHAT IS HELD (`differences`), and what is NOT, by name — C cannot keep the ROM's instruction count, so the OBSERVABLE
surfaces are compared, as band 5's our-boot stretches do:
  * the stop; the whole register file but `NOT_HELD` (each with its reason: what the ROM's slice leaves as scratch and
    the C as GCC's ABI does); the megabyte, every vector holding one of OUR linked entries mapped back to the ROM's
    (`LINKED`), outside THE STACK RESIDUE — the bytes under the BIOS's stack top each shore's frames left, A DEAD CLASS
    proved dead by noise: the ROM's own continuation stores every one of them before it returns (`residue_class`);
  * the addresses stored outside it (a frame of ours deeper than the residue is seen there); every ordered ledger; the
    faults.
"""
import ctypes
import functools
import random
import struct
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu

import boot
import boot_head
import isr
import layouts
import mfp

RECREATE = Path(__file__).resolve().parents[1]
SYSVARS_H = RECREATE / "include" / "boot" / "sysvars.h"
ENCODINGS_H = RECREATE / "include" / "m68k_encodings.h"
CONSTANTS = layouts.parse_constants((ENCODINGS_H, SYSVARS_H))
LONG_BYTES = boot.LONG_BYTES
RAM_BYTES = boot.RAM_BYTES

# ---- THE ROM'S SPANS --------------------------------------------------------------------------------------------------
SPAN = (boot.HEAD_ENDS, boot.HARDWARE_INIT_CALLED)          # [$fc02cc, $fc03b6): from `lea $755a,sp` to `bsr $fc2408`
RTS = 0x4e75
BSR_W, BSR_W_BYTES = CONSTANTS["M68K_BSR_W"], 4     # `bsr.w <d16>`: the opcode word and its displacement


def _routine_extent(entry):
    """`(entry, end)`: a routine of straight-line code and its first `rts`, end past it (where its own cycles lie)."""
    at = entry
    while struct.unpack_from(">H", BASE_IMAGE, at)[0] != RTS:
        at += boot.WORD_BYTES
    return entry, at + boot.WORD_BYTES


HEADER_ROUTINE = _routine_extent(addrs.BOOT_OS_HEADER_TO_RAM)     # $fc0eba: the OS header in RAM
THE_ROM_S_SPANS = (SPAN, HEADER_ROUTINE)


def _bsr_w_return(at):
    opcode = struct.unpack_from(">H", BASE_IMAGE, at)[0]
    assert opcode == BSR_W, f"the ROM holds {opcode:#06x} at {at:#x}, not the boot's `bsr.w`"
    return at + BSR_W_BYTES


HARDWARE_INIT_RETURNS = _bsr_w_return(boot.HARDWARE_INIT_CALLED)    # $fc03ba: `bsr $fc2408` returned (B3's)

# ---- OUR SIDE -------------------------------------------------------------------------------------------------------
ENTRY_SYMBOL = "boot_sysvars_entry"
BLOB_LABEL = ("LABELLED STAGING (the bench blob laid in RAM at its link address ${base:x}, over the ROM's own machine "
              "at ${start:x})")
# THE VECTORS THAT HOLD OUR LINKED ENTRIES ON TARGET, each mapped back to the ROM's routine (the symbol is the ROM's
# instructions, byte-pinned by its own battery: `test_bios_hbl.py`/`test_bios_vbl.py`, `test_bios_trap.py`,
# `test_vdi_entry_transcription.py`). Off target the C stores the ROM's address itself (`BOOT_LINKED_ENTRY`).
LINKED = {
    addrs.VECTOR_HBL: (isr.stub_symbol("ISR_HBL"), addrs.ISR_HBL),
    addrs.VECTOR_VBL: (isr.stub_symbol("ISR_VBL"), addrs.ISR_VBL),
    addrs.VECTOR_TRAP_BIOS: ("bios_trap13", addrs.BIOS_TRAP13),
    addrs.VECTOR_TRAP_XBIOS: ("xbios_trap14", addrs.XBIOS_TRAP14),
    addrs.VECTOR_LINE_A: ("linea_rom_dispatch", addrs.LINEA_ROM_DISPATCH),
}

# ---- THE SLICES -------------------------------------------------------------------------------------------------------
ARMS = boot_head.ARMS
SLICES = {f"boot sysvars B2, {arm}": arm for arm in ARMS}


def product():
    """The bench blob (`isr.blob()`: `RomBench`, `make test` builds it) — its bytes, base, span end and symbols."""
    return isr.blob()


@functools.cache
def start_of(arm):
    """THE ROM'S OWN MACHINE AT `$fc02cc` on `arm`: the head's run from the reset, cut where B1 cuts it."""
    at_the_warm_arm = boot_head.start_of(boot_head.HeadSlice(boot_head.H3, arm))
    return boot.run(at_the_warm_arm, {SPAN[0]}).machine


def laid(machine, blob=None):
    """`machine` with the bench blob laid in its RAM at its link address — A LABELLED STAGING (the module's docstring)."""
    blob = blob or product()
    assert blob.end <= RAM_BYTES, f"the blob's span [{blob.base:#x}, {blob.end:#x}) runs past RAM"
    ram = bytearray(machine.ram)
    ram[blob.base:blob.end] = blob.blob + bytes(blob.end - blob.base - len(blob.blob))
    label = BLOB_LABEL.format(base=blob.base, start=machine.registers["pc"])
    return machine._replace(ram=bytes(ram), label=f"{machine.label}; {label}")


def _profiled(run):
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        return run()
    finally:
        emu.prof_enable(False)


def the_rom_s(arm, with_the_blob=False, profiled=False):
    """The ROM's own slice from its machine at `$fc02cc` — the blob's room as the machine holds it (free RAM: the
    ROM's shore is the one `room_poison` poisons), or `with_the_blob` laid there, as ours runs."""
    machine = laid(start_of(arm)) if with_the_blob else start_of(arm)
    run = lambda: boot.run(machine, {SPAN[1]})          # noqa: E731
    return _profiled(run) if profiled else run()


def own_cycles_of_the_rom():
    """The cycles the run just profiled spent in the ROM's own B2 spans."""
    return sum(emu.prof_cycles(lo, hi) for lo, hi in THE_ROM_S_SPANS)


def our_side(arm, symbol=ENTRY_SYMBOL, blob=None):
    """OUR slice from the same machine (the blob laid): entered at `symbol`, stopped where the ROM's stops. PROFILED,
    and REFUSED BY NAME if it executed any of the ROM's own B2 spans — code of ours that fell into them would be
    measured equal on the ROM's instructions. The profile is left for the caller (`emu.prof_cycles`)."""
    blob = blob or product()
    machine = boot.entered_at(laid(start_of(arm), blob), blob.entry(symbol))
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        done = boot.run(machine, {SPAN[1]})
        spent = own_cycles_of_the_rom()
    finally:
        emu.prof_enable(False)
    if spent:
        raise boot.Refused(f"{machine.label}: our run executed the ROM's own B2 spans "
                           f"{[(f'{lo:#x}', f'{hi:#x}') for lo, hi in THE_ROM_S_SPANS]} — {spent} cycles of them")
    return done


# ---- WHAT IS NOT HELD, BY NAME ----------------------------------------------------------------------------------------
NOT_HELD = {
    "d0": "the ROM's loop counter (`dbf`); GCC's scratch",
    "d1": "the head's screen-clear counter the ROM leaves; GCC's scratch",
    "a0": "the ROM's walking pointer; GCC's scratch",
    "a1": "the ROM's walking pointer; GCC's scratch",
    "a3": "the ROM's handle on the bare `rte` for its vector loop; GCC keeps the caller's (callee-saved)",
    "a4": "the ROM's handle on the bare `rts`; GCC keeps the caller's (callee-saved) — CARRIED PAST $fc2408 "
          "(`test_boot_sysvars.py`: dead through the hardware init, never named by the boot's own text after it)",
}

# ---- THE STACK RESIDUE: A DEAD CLASS, proved by the ROM's own continuation ---------------------------------------------
# THE PROOF'S DECLARATIONS — labelled, the proof's own and no row's (B3 owns the hardware init): the MFP as the
# Xbtimer/Rsconf cases declare it, its active-edge register written back, the PSG's mixer and port A.
PROOF_PSG = {addrs.PSG_MIXER_REGISTER: addrs.PSG_MIXER_PORT_MASK, addrs.PSG_PORT_A: 0}


def proof_io():
    declared = mfp.seed()
    declared.update(mfp.aer_latched(0))
    return declared


def continued(machine):
    """The ROM's own hardware init from `machine` at `$fc03b6` to its return (`$fc03ba`), under the proof's
    declarations."""
    return boot.run(machine, {HARDWARE_INIT_RETURNS}, io_seed=proof_io(), psg_seed=PROOF_PSG)


@functools.cache
def residue_class(arm):
    """`(lo, hi)`: THE STACK RESIDUE — the run of bytes the ROM's own hardware init stores that ENDS AT THE BIOS'S STACK
    TOP (its frames), run from the ROM's machine at `$fc03b6` to its return: derived, never typed. Refused where no
    stored run ends there."""
    the_rom_s_end = the_rom_s(arm).machine
    top = the_rom_s_end.registers["isp"]
    frames = [(start, start + length) for start, length in continued(the_rom_s_end).stored if start + length == top]
    assert frames, f"the ROM's hardware init stores no run of bytes ending at the stack top {top:#x}"
    return frames[0]


def noised(machine, lo, hi, registers=tuple(NOT_HELD), seed=0):
    """`machine` with noise in `[lo, hi)` and in `registers` — what a dead class may hold."""
    rng = random.Random(seed)
    ram = bytearray(machine.ram)
    ram[lo:hi] = bytes(rng.getrandbits(8) for _ in range(hi - lo))
    regs = {**machine.registers, **{name: rng.getrandbits(32) for name in registers}}
    return machine._replace(ram=bytes(ram), registers=regs)


# ---- THE COMPARISON ---------------------------------------------------------------------------------------------------
def mapped_back(ram, symbols, linked=None):
    """`ram` with each vector of `linked` that holds OUR entry given the ROM's routine's address instead."""
    ram = bytearray(ram)
    for vector, (symbol, rom) in (LINKED if linked is None else linked).items():
        if struct.unpack_from(">I", ram, vector)[0] == symbols[symbol]:
            struct.pack_into(">I", ram, vector, rom)
    return bytes(ram)


SURFACES = ("stop", "registers", "ram", "stored", "hardware_writes", "io_reads", "hardware_reads", "psg_events", "faults")
LEDGERS = ("hardware_writes", "io_reads", "hardware_reads", "psg_events", "faults")


def stored_set(slice_):
    """Every address `slice_` stored to."""
    return {at for start, length in slice_.stored for at in range(start, start + length)}


def differences(the_rom_s_slice, our_slice, symbols, residue, blob_span, linked=None, not_held=None):
    """Every surface `our_slice` differs from `the_rom_s_slice` on, by name (none: held equal) — the module's
    docstring. The megabyte is compared outside the residue and outside `blob_span` (the blob laid on ours, the
    room's own bytes on the ROM's); a store of ours into either span is seen as `stored`, as is a frame of ours
    deeper than the residue."""
    lo, hi = residue
    not_held = NOT_HELD if not_held is None else not_held
    found = []
    if our_slice.stop != the_rom_s_slice.stop:
        found.append(f"stop: the ROM's {the_rom_s_slice.stop:#x}, ours {our_slice.stop:#x}")
    theirs, mine = the_rom_s_slice.machine.registers, our_slice.machine.registers
    registers = {name: (f"{theirs[name]:#x}", f"{mine[name]:#x}") for name in theirs
                 if name not in not_held and theirs[name] != mine[name]}
    if registers:
        found.append(f"registers {registers} (the ROM's, ours)")
    rom_ram = the_rom_s_slice.machine.ram
    our_ram = bytearray(mapped_back(our_slice.machine.ram, symbols, linked))
    for left_out_lo, left_out_hi in (residue, blob_span):
        our_ram[left_out_lo:left_out_hi] = rom_ram[left_out_lo:left_out_hi]
    if our_ram != rom_ram:
        first = next(at for at, (one, other) in enumerate(zip(rom_ram, our_ram)) if one != other)
        found.append(f"ram, first at {first:#x} (outside the residue and the blob)")
    outside = lambda stored: {at for at in stored if not lo <= at < hi}      # noqa: E731
    if outside(stored_set(the_rom_s_slice)) != outside(stored_set(our_slice)):
        found.append("stored: the addresses stored outside the residue differ")
    for surface in LEDGERS:
        if getattr(the_rom_s_slice, surface) != getattr(our_slice, surface):
            found.append(f"{surface}: {len(getattr(the_rom_s_slice, surface) or ())} against ours "
                         f"{len(getattr(our_slice, surface) or ())}")
    return found


# ---- THE HOST C (the second differential: `boot_sysvars_and_vectors` on the host, every vector the ROM's address) -----
_lib.boot_sysvars_and_vectors.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.boot_sysvars_and_vectors.restype = None


def host_run(machine):
    """The host build's C over `machine`'s RAM in a copy of the image: the image it leaves."""
    image = bytearray(BASE_IMAGE)
    image[:RAM_BYTES] = machine.ram
    _lib.boot_sysvars_and_vectors((ctypes.c_ubyte * len(image)).from_buffer(image))
    return bytes(image[:RAM_BYTES])


# ---- ITS PRICE (ruling D9: on each shore's own cycles, `bench/tier3.py`) ------------------------------------------------
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """B2 measured on both shores: the two `boot.Slice`s, `own` (ours the blob's cycles, the ROM's its
B2 spans' — each shore's own) and `rest` (each run's other cycles: the entry's segment), held equal."""


def priced(arm):
    """B2 PRICED on `arm`: both shores run, every held surface equal (refused by name otherwise), each shore's own
    cycles read off its run's profile. Our run is the last made: its profile is the one left."""
    blob = product()
    the_rom_s_slice = the_rom_s(arm, profiled=True)
    the_rom_s_own = own_cycles_of_the_rom()
    our_slice = our_side(arm, blob=blob)
    our_own = emu.prof_cycles(blob.base, blob.end)
    found = differences(the_rom_s_slice, our_slice, blob.symbols, residue_class(arm), (blob.base, blob.end))
    assert not found, f"{name_of(arm)}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (our_slice.cycles - our_own, the_rom_s_slice.cycles - the_rom_s_own)
    assert rest[0] == rest[1], f"{name_of(arm)}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(the_rom_s_slice, our_slice, (our_own, the_rom_s_own), rest[0])


def name_of(arm):
    return next(name for name, each in SLICES.items() if each == arm)
