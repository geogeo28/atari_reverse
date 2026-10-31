r"""THE BIOS's HARDWARE INIT AND THE BOOT's STRETCH AROUND IT ON BOTH SHORES (boot B3, `test_boot_hwinit.py`): the ROM's
own `$fc2408` and `[$fc03b6, $fc03e0)` against OUR C (`src/boot/hwinit.c`, entered by `src/boot/hwinit_entry.S`), run
from one machine and held equal on every surface the C can be held on — as B2's slice is (`boot_sysvars.py`).

THE USER'S RULINGS (2026-10-29) THIS MODULE STANDS ON: D7 (C after `lea $755a,sp`); D8 (the WARM and COLD machines,
`boot.py`); D9 "Stretch rows" (the stretch priced on each shore's own cycles, `bench/tier3.py`). The orchestrator's
standing calls: a ROM table the code reads or copies — the IOREC templates, the RS232 handlers' table, the IKBD's reset
command — is read where it lies, listed in the boot census (`test_boot_rom_data.py`); D3 (interrupts inside a run) stays
open — nothing here needs one: the timer programmer's read-back of the timer C data register (`$fc260e`, where B0's
smoke spins with nothing declared) is answered by the DECLARED MFP of the Xbtimer / Rsconf precedent, the register
WRITE-THROUGH (`test/mfp.py`: a stopped timer's reload latch), and it is read ONCE on both shores.

WHERE OUR CODE LIES: in the bench blob laid in RAM at its link address over the ROM's own machine — B2's staging
(`boot_sysvars.laid`), held here as there: the ROM's own runs are the same with and without the blob; a run of ours that
spends a cycle in the ROM's window outside the one routine both shores run (the cartridge hooks, `$fc0646`) is REFUSED
BY NAME (the false green).

TWO ROWS' WORTH OF RUNS, each on each arm:
  * THE FUNCTION (`$fc2408`): from THE ROM'S OWN MACHINE AT ITS ENTRY — the ROM's `bsr` taken from its machine at
    `$fc03b6` — the ROM's routine, and our `bios_hardware_init_entry` (the ROM's calling convention: no argument,
    A5 = 0), both to the return `$fc03ba`;
  * THE STRETCH (`[$fc03b6, $fc03e0)`): from the ROM's machine at `$fc03b6`, the ROM's and our
    `boot_hardware_and_ikbd_reset_entry`, both to `$fc03e0` — the init, the IKBD reset, the pause, the hook.

WHAT IS HELD (`differences`, B2's comparator): the stop; every register but `NOT_HELD[kind]`, each with its reason; the
megabyte — `$114` / `$118` holding OUR linked entries mapped back (`LINKED`) — outside the STACK RESIDUE (`residue_class`:
the bytes under the stack top either shore's frames stored, DERIVED and proved dead by the ROM's own continuation) and the
blob's span; the addresses stored outside the residue; every ordered ledger (the MFP, ACIA and port writes, the declared
reads, the modelled reads, the PSG's accesses); the faults. Instructions and cycles are the price, not a surface.
"""
import ctypes
import functools
import random
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, arm_candidate, emu

import aes_boot
import boot
import boot_sysvars
import isr
import layouts
import mfp
import stopped_cpu

RECREATE = Path(__file__).resolve().parents[1]
HWINIT_H = RECREATE / "include" / "boot" / "hwinit.h"
CONSTANTS = layouts.parse_constants((HWINIT_H,))
LONG_BYTES, WORD_BYTES = boot.LONG_BYTES, boot.WORD_BYTES

# ---- THE ROM'S ADDRESSES ---------------------------------------------------------------------------------------------
STRETCH = (boot.HARDWARE_INIT_CALLED, boot.IKBD_RESET_DONE)        # [$fc03b6, $fc03e0)
CALLED, RETURNED = addrs.BIOS_HARDWARE_INIT, boot_sysvars.HARDWARE_INIT_RETURNS   # $fc2408, $fc03ba
# THE ONE ROUTINE OF THE ROM'S OUR STRETCH RUNS: the cartridge's application hooks, to its `rts` (D2: no cartridge).
HOOKS = boot_sysvars._routine_extent(CONSTANTS["ROM_CARTRIDGE_HOOKS"])
ROM_WINDOW = boot.ROM_WINDOW

# ---- THE CASE's DECLARATIONS (the rows' own): the MFP as the Xbtimer / Rsconf cases declare it (`mfp.seed`), and the
# AER beside it — the init's `bset` re-reads the byte its own `movep` cleared, and the AER is a latch on the 68901:
# WRITE-THROUGH — and port A, its entry byte holding the bits the init changes the other way (DTR 4 and RTS 3 set, the
# strobe 5 clear), so a change skipped is a byte that differs. Distinct entry bytes, as `mfp.py`'s, so a clear skipped
# or a register mistaken reads as a byte that differs.
AER_ENTRY = 0xa5
PORT_A_ENTRY = 0x5e


def io_seed():
    return {**mfp.seed(), **mfp.aer_latched(AER_ENTRY)}


PSG_SEED = {addrs.PSG_PORT_A: PORT_A_ENTRY}

# ---- OUR SIDE --------------------------------------------------------------------------------------------------------
FUNCTION, STRETCH_KIND = "function", "stretch"
ENTRY_SYMBOL = {FUNCTION: "bios_hardware_init_entry", STRETCH_KIND: "boot_hardware_init_called_entry"}
RETURNED_SYMBOL = "boot_ikbd_reset_entry"       # our stretch's own `$fc03ba`: the init's call returned
# THE VECTORS THAT HOLD OUR LINKED ENTRIES ON TARGET, each mapped back to the ROM's handler (`src/bios/isr.S`'s entries,
# byte-pinned by their own batteries); off target the C stores the ROM's (`BOOT_LINKED_ENTRY`).
LINKED = {
    addrs.VECTOR_TIMER_C: (isr.stub_symbol("ISR_TIMER_C"), addrs.ISR_TIMER_C),
    addrs.VECTOR_ACIA: (isr.stub_symbol("ISR_ACIA"), addrs.ISR_ACIA),
}

ARMS = boot_sysvars.ARMS
KINDS = (FUNCTION, STRETCH_KIND)
SLICES = {f"boot hardware init B3 {kind}, {arm}": (arm, kind) for kind in KINDS for arm in ARMS}


def product():
    return isr.blob()


@functools.cache
def start_of(arm, kind):
    """THE ROM'S OWN MACHINE where `kind` starts on `arm`: at `$fc03b6` (B2's end) for the stretch, and one instruction on
    — the ROM's own `bsr` taken, its return address on the stack — at `$fc2408` for the function."""
    at_the_call = boot_sysvars.the_rom_s(arm).machine
    return at_the_call if kind == STRETCH_KIND else boot.run(at_the_call, {CALLED}).machine


def start_pc(kind):
    return CALLED if kind == FUNCTION else STRETCH[0]


def stop_of(kind):
    return RETURNED if kind == FUNCTION else STRETCH[1]


def declared():
    return dict(io_seed=io_seed(), psg_seed=dict(PSG_SEED))


# THE 6850's TWO REGISTERS AT ONE ADDRESS: the init WRITES the IKBD ACIA's CONTROL register at `$fffc00` and Ikbdws then
# READS its STATUS register there. The kit's modelled slot is one byte an address and refuses a read of a byte the run
# wrote; so THE STRETCH IS RUN AS TWO RUNS, cut at the init's return on each shore (`$fc03ba`, ours
# `boot_ikbd_reset_entry`), the second declaring the status as the slot's own default — TDRE set, which a 6850 just
# reset and configured holds. `joined` makes the two one slice: the second's machine, the sums, every ledger in order.
def joined(first, second):
    stored = {at for start, length in (*first.stored, *second.stored) for at in range(start, start + length)}
    return second._replace(instructions=first.instructions + second.instructions, cycles=first.cycles + second.cycles,
                           stored=stopped_cpu.address_runs(sorted(stored)),
                           **{ledger: (*getattr(first, ledger), *getattr(second, ledger)) for ledger in LEDGERS[:-1]},
                           faults={**first.faults, **second.faults})


# THE PAUSE COUNTED (its only surface is time): each shore's `dbf` loop of a `bsr` to an `rts`, read off its profile.
# A pass is the `bsr` (18 cycles, `.s` or `.w` alike), the `rts` (16) and the `dbf` taken (10); the last `dbf` expires
# (14: +4); ours also runs its one `bra.s` over its `rts` (10). Cycles in the loop -> passes, exactly or refused.
PASS_CYCLES, DBF_EXPIRY_EXTRA, BRA_S_CYCLES = 18 + 16 + 10, 4, 10
ROM_PAUSE_LOOP = (0xfc03d2, 0xfc03da)   # `bsr.w $fc0556` / `dbf d0`: held to the ROM's text by `test_boot_hwinit.py`
ROM_PAUSE_RTS = 0xfc0556                # the `rts` it calls ($fc0556..$fc0558)
# `rts_delay`'s loop as GCC emits it (`m68k_idioms.h`): `bsr.s 1f`, `dbf Dn,0b`, `bra.s 2f`, `1: rts` — Dn masked out.
OUR_PAUSE_SHAPE = (0x6106, 0x51c8, 0xfffc, 0x6002, 0x4e75)
DBF_REGISTER_MASK = 0xfff8


def passes(cycles, extra):
    """The passes `cycles` of a pause loop make (`extra`: what runs once beside them) — refused if they are not whole."""
    count, left = divmod(cycles - DBF_EXPIRY_EXTRA - extra, PASS_CYCLES)
    assert not left, f"{cycles} cycles in a pause loop are not whole passes ({left} over)"
    return count


def the_rom_s_pause():
    """The passes the run just profiled made in the ROM's pause."""
    return passes(emu.prof_cycles(*ROM_PAUSE_LOOP) + emu.prof_cycles(ROM_PAUSE_RTS, ROM_PAUSE_RTS + WORD_BYTES), 0)


def our_pause_loop(blob):
    """`(lo, hi)`: our pause's loop inside `boot_ikbd_reset`, found by its shape — refused unless there is exactly one."""
    lo = blob.symbols["boot_ikbd_reset"]
    hi = min(at for at in blob.symbols.values() if at > lo)
    words = [int.from_bytes(blob.blob[at - blob.base:at - blob.base + WORD_BYTES], "big") for at in range(lo, hi, WORD_BYTES)]
    shape = len(OUR_PAUSE_SHAPE)
    found = [lo + index * WORD_BYTES for index in range(len(words) - shape + 1)
             if [word & (DBF_REGISTER_MASK if position == 1 else 0xffff)
                 for position, word in enumerate(words[index:index + shape])] == list(OUR_PAUSE_SHAPE)]
    assert len(found) == 1, f"boot_ikbd_reset holds {len(found)} pause loops of rts_delay's shape"
    return found[0], found[0] + shape * WORD_BYTES


def our_pause(blob):
    """...and in ours."""
    return passes(emu.prof_cycles(*our_pause_loop(blob)), BRA_S_CYCLES)


def legs(machine, returned):
    """The stretch's two runs from `machine`: to `returned` (the init's call returned), and on to `$fc03e0`."""
    first = boot.run(machine, {returned}, **declared())
    return first, boot.run(first.machine, {STRETCH[1]}, **declared())


def _run(machine, kind, returned):
    """`kind` run from `machine`: the function to its return; the stretch's two legs, joined."""
    return boot.run(machine, {RETURNED}, **declared()) if kind == FUNCTION else joined(*legs(machine, returned))


def the_rom_s(arm, kind, with_the_blob=False, profiled=False):
    """The ROM's own run of `kind` from its machine — the blob's room as the machine holds it, or `with_the_blob` laid."""
    machine = start_of(arm, kind)
    machine = boot_sysvars.laid(machine) if with_the_blob else machine
    run = lambda: _run(machine, kind, RETURNED)          # noqa: E731
    return boot_sysvars._profiled(run) if profiled else run()


def rom_cycles_outside_the_hooks():
    """The cycles the run just profiled spent in the ROM's window, the hooks routine both shores run left out."""
    return emu.prof_cycles(*ROM_WINDOW) - emu.prof_cycles(*HOOKS)


def our_side(arm, kind, blob=None, symbol=None):
    """OUR run of `kind` from the same machine (the blob laid), entered at its symbol and stopped where the ROM's stops.
    PROFILED, and REFUSED BY NAME if it spent a cycle in the ROM's window outside the hooks — code of ours that fell into
    the ROM's would be measured equal on the ROM's instructions. The profile is left for the caller."""
    blob = blob or product()
    machine = boot.entered_at(boot_sysvars.laid(start_of(arm, kind), blob), blob.entry(symbol or ENTRY_SYMBOL[kind]))
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        done = _run(machine, kind, blob.entry(RETURNED_SYMBOL))
        spent = rom_cycles_outside_the_hooks()
    finally:
        emu.prof_enable(False)
    if spent:
        raise boot.Refused(f"{machine.label}: our run executed the ROM's own code outside the hooks "
                           f"[{HOOKS[0]:#x}, {HOOKS[1]:#x}) — {spent} cycles of it")
    return done


# ---- WHAT IS NOT HELD, BY NAME — each set the registers that differ on both arms, exactly (`test_boot_hwinit.py`) ------
NOT_HELD = {
    FUNCTION: {
        "d1": "the ROM's RS232 loop counter ($ffff, `dbf`'s end); GCC's scratch",
        "a0": "the ROM's IOREC cursor; GCC's scratch",
        "a1": "the ROM's template cursor; GCC's scratch",
        "a2": "the ROM's handler argument (CTS's, the last installed); GCC keeps the caller's (callee-saved)",
        "a3": "the ROM's handle on the RS232 handlers' table; GCC keeps the caller's (callee-saved)",
        "sr": "its CONDITION CODES alone (`CCR_SET_AT_THE_RETURN`): the rest of SR held",
    },
    STRETCH_KIND: {
        "d1": "the ROM's Ikbdws byte (its low byte only, over the init's $ffff); GCC's scratch",
        "a1": "the ROM's Ikbdws ACIA; GCC's scratch",
        "d2": "the ROM's settle counter (its low word, over the init's 0); GCC keeps the caller's (callee-saved)",
        "d3": "the ROM's Ikbdws byte count; GCC keeps the caller's (callee-saved)",
        "a2": "the ROM's Ikbdws cursor; GCC keeps the caller's (callee-saved)",
        "a3": "the ROM's handle on the RS232 handlers' table; GCC keeps the caller's (callee-saved)",
    },
}
# The function's return site, `$fc03ba`, is `move.l #imm,-(sp)`: it SETS N, Z, V and C and reads none — the flags our
# return leaves are dead there, X and the system byte are not (held).
CCR_SET_AT_THE_RETURN = 0x0f
MOVE_L_IMMEDIATE_TO_PREDECREMENT_SP = 0x2f3c


# ---- THE STACK RESIDUE: A DEAD CLASS, proved by the ROM's own continuation ---------------------------------------------
def stack_frames(slice_, top):
    """`(lo, top)`: the run of bytes `slice_` stored that ends at the stack top, or None."""
    frames = [(start, start + length) for start, length in slice_.stored if start + length == top]
    return frames[0] if frames else None


@functools.cache
def residue_class(arm, kind):
    """`(lo, hi)`: THE STACK RESIDUE — the run of bytes under the stack top at `kind`'s start that EITHER shore's frames
    stored, derived from both runs, never typed (ours are the deeper: GCC's frames and argument slots)."""
    the_rom_s_slice, ours = the_rom_s(arm, kind), our_side(arm, kind)
    top = start_of(arm, kind).registers["isp"]
    frames = [stack_frames(the_rom_s_slice, top), stack_frames(ours, top)]
    assert all(frames), f"a shore stores no run of bytes ending at the stack top {top:#x}: {frames}"
    return min(lo for lo, _hi in frames), top


# THE PROOF'S HORIZON: the ROM's own boot from where `kind` ends to `move #$2300,sr` (`boot.INTERRUPTS_OPENED`), past
# which the machine is interrupt-driven (D3) and no run reaches. Its DECLARATIONS are the proof's own, LABELLED and no
# row's (B5 owns the display slice): this rows' MFP and port A; the shifter's resolution read as ST low and GPIP 7 high
# (the capture's colour monitor: the mono arm not taken); the blitter probe's bus error (`aes_boot.THE_BLITTER_PROBE`).
PROOF_RESOLUTION = 0                    # ST low


def proof_declared():
    return dict(io_seed={**io_seed(), addrs.SHIFTER_RESOLUTION: PROOF_RESOLUTION}, psg_seed=dict(PSG_SEED),
                hw_seed={addrs.MFP_GPIP: 1 << addrs.MFP_GPIP_MONOCHROME_BIT}, faults=(aes_boot.THE_BLITTER_PROBE,))


def continued(machine):
    """The ROM's own boot from `machine` (at `$fc03ba` or `$fc03e0`) to the horizon, as one slice."""
    if machine.registers["pc"] == RETURNED:
        first = boot.run(machine, {STRETCH[1]}, **declared())
        return joined(first, boot.run(first.machine, {boot.INTERRUPTS_OPENED}, **proof_declared()))
    return boot.run(machine, {boot.INTERRUPTS_OPENED}, **proof_declared())


def noised(machine, lo, hi, registers, seed=0):
    """`machine` with noise in `[lo, hi)` and in `registers` — SR in its condition codes alone."""
    rng = random.Random(seed)
    ram = bytearray(machine.ram)
    ram[lo:hi] = bytes(rng.getrandbits(8) for _ in range(hi - lo))
    regs = dict(machine.registers)
    for name in registers:
        regs[name] = ((regs[name] & ~CCR_SET_AT_THE_RETURN) | (rng.getrandbits(32) & CCR_SET_AT_THE_RETURN)
                      if name == "sr" else rng.getrandbits(32))
    return machine._replace(ram=bytes(ram), registers=regs)


# ---- THE COMPARISON (B2's comparator, this rows' mapping and scratch) --------------------------------------------------
SURFACES, LEDGERS = boot_sysvars.SURFACES, boot_sysvars.LEDGERS


def differences(the_rom_s_slice, our_slice, kind, symbols, residue, blob_span, linked=None, not_held=None):
    """`boot_sysvars.differences` with this rows' mapping (`LINKED`) and scratch (`NOT_HELD[kind]`) — and SR, where it
    is named, held outside its condition codes."""
    not_held = NOT_HELD[kind] if not_held is None else not_held
    found = boot_sysvars.differences(the_rom_s_slice, our_slice, symbols, residue, blob_span,
                                     linked=LINKED if linked is None else linked, not_held=not_held)
    theirs, mine = the_rom_s_slice.machine.registers["sr"], our_slice.machine.registers["sr"]
    if "sr" in not_held and (theirs ^ mine) & ~CCR_SET_AT_THE_RETURN:
        found.append(f"registers: sr outside its condition codes, the ROM's {theirs:#x}, ours {mine:#x}")
    return found


# ---- THE HOST C (the second differential: the stretch's C on the host, every vector the ROM's address) -----------------
for _symbol in ("bios_hardware_init", "boot_ikbd_reset"):
    getattr(_lib, _symbol).argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    getattr(_lib, _symbol).restype = None


def host_run(machine, steps=("bios_hardware_init", "boot_ikbd_reset")):
    """The host build's C over `machine`'s RAM in a copy of the image, armed with the rows' declarations (each step its
    own run, as the oracle's two are): the megabyte it leaves. Refused where the candidate refused a read. (The host's
    chip ledgers are the function row's differential's.)"""
    image = bytearray(BASE_IMAGE)
    image[:boot.RAM_BYTES] = machine.ram
    buffer = (ctypes.c_ubyte * len(image)).from_buffer(image)
    for step in steps:
        arm_candidate(**declared())
        getattr(_lib, step)(buffer)
        assert _lib.g_os_refusal_count() == 0, f"the host's {step} made {_lib.g_os_refusal_count()} refused read(s)"
    return bytes(image[:boot.RAM_BYTES])


# ---- ITS PRICE (ruling D9: each shore's own cycles) ---------------------------------------------------------------------
Priced = boot_sysvars.Priced


def priced(arm, kind=STRETCH_KIND):
    """`kind` PRICED on `arm`: both shores run, every held surface equal (refused by name otherwise); `own` ours the
    blob's cycles, the ROM's its run's but the hooks routine's; `rest` (the hooks both shores run) held equal."""
    blob = product()
    the_rom_s_slice = the_rom_s(arm, kind, profiled=True)
    the_rom_s_own = the_rom_s_slice.cycles - emu.prof_cycles(*HOOKS)
    ours = our_side(arm, kind, blob=blob)
    our_own = emu.prof_cycles(blob.base, blob.end)
    found = differences(the_rom_s_slice, ours, kind, blob.symbols, residue_class(arm, kind), (blob.base, blob.end))
    assert not found, f"{kind} on {arm}: ours differs from the ROM's — {'; '.join(found)}"
    rest = (ours.cycles - our_own, the_rom_s_slice.cycles - the_rom_s_own)
    assert rest[0] == rest[1], f"{kind} on {arm}: beside its own, ours spent {rest[0]} cycles, the ROM's {rest[1]}"
    return Priced(the_rom_s_slice, ours, (our_own, the_rom_s_own), rest[0])


def name_of(arm, kind):
    return next(name for name, each in SLICES.items() if each == (arm, kind))
