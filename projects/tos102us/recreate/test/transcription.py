"""THE BYTE-EXACT `.S` MACHINERY — how ANY component's hand-68000 routine ships as the ROM's own instructions.

The user's rule for the hand-written 68000 is component-blind: port it to C first (Tier 1 proves the C), and where the
C measures over Tier 3's 1.10 bar, SHIP a byte-pinned `.S` transcription. This module is everything that rule needs,
for the VDI and Line-A (`src/vdi/*.S`) and the AES (`src/aes/*.S`) alike:

  * (a) the STAGED CALLERS a transcription is entered through, and the transcription relation's run and Tier 3 row;
  * (b) the BYTE PIN: the regions the batteries pin, and the one comparator (`assert_transcribed`);
  * (c) the TRANSCRIBED TABLE (`include/transcribed.h`), parsed, and the C that still calls a core it names;
  * (d) the m68k build's CALL GRAPH, which (T→) and the table's caller list are read out of.

A routine is named by the one naming rule (`test/routines.py`): the `.S` entry is its `addrs.h` name lower-cased
(`VDI_ROM_VS_COLOR` -> `vdi_rom_vs_color`, `AES_ROM_RC_INTERSECT` -> `aes_rom_rc_intersect`) and the C core that name
less its `rom_`. `bench/tier3.py`, `bench/shipped_glue.py` and `test_transcribed.py` read it all from here.
"""
import functools
import importlib
import re
import struct
import subprocess
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu, make_image

import abi
import routines
from case import merge_pokes
import isr
from isr import blob as bench     # the cross-compiled blob, loaded once per process (`isr.blob`)
from layouts import LONG_BYTES, WORD_BYTES
from opcodes import CLEAR_REGISTER, JSR_ABSOLUTE_LONG, PUSH_RETURN_PC, PUSH_STACK_LONG, RTE, RTS
# The plain caller and the stand-in routine a caller's cost is measured over sit in bands of the VDI's staged window
# (`vdi.SPAN`), where the first transcriptions were staged: one image serves every case, so any component's
# transcription is entered through them.
from vdi import STUB_AT, TRANSCRIPTION_CALLER_AT

_RECREATE = Path(__file__).resolve().parents[1]
# Tier 3's m68k blob (kit.mk's bench rule) — whose call graph the batteries read — and the SHIPPED CONFIGURATION's
# (the Makefile's shipped-blob rule): the build the (T→) rows are priced on.
BENCH_ELF = _RECREATE / "build" / "bench" / "bench.elf"
SHIPPED_ELF = isr.SHIPPED_BLOB_DIRECTORY / "bench.elf"


# ---- (a) a TRANSCRIPTION: a hand-68000 routine the target build ships as the ROM's own `.S` ---------
# The user's rule for the hand-written routines: C first (Tier 1 proves it), and where the C measures
# over the 1.10 bar, the ROM's own instructions in a `src/<component>/*.S`, byte-pinned and held by Tier 3's
# TRANSCRIPTION relation (`RomBench.measure_transcription`) to the same image, the WHOLE register file
# and the same chip traffic. The `.S` entry is the ROM routine's `addrs.h` name lower-cased
# (`VDI_ROM_VS_COLOR` -> `vdi_rom_vs_color`), which is how `bench/tier3.py` finds the address a row is
# about.
#
# ONE IMAGE SERVES BOTH SIDES (`test/trap.py`'s arrangement): both are entered at a staged CALLER that
# jumps through the longword at `abi.FIRST_ARG` — the ROM routine, as the case pokes it, or the blob's,
# which `run_bench` writes over that slot — with the sentinel still under it, so the routine sees the
# `jsr` frame the dispatcher leaves. The caller's own cost is in both columns and comes off both.
#
# A staged caller as a row carries it: where it is, its bytes, and what it costs (off both columns). A
# battery whose routine needs another shape stages its own in its own band through `staged_caller`, which
# REGISTERS it: `test_transcribed.py` measures every registered caller's cost against the one it
# declares (`assert_caller_cost`), so no caller's number is a literal nobody re-derives.
# A caller that enters a routine BELOW a frame the routine's front end would have built (a body whose own
# epilogue pops what that front end pushed) is measured over that epilogue instead of a bare `rts`: its
# `routine` stand-in and the stand-in's `routine_cost` (None: the bare `rts`, `RTS_COST`).
Caller = namedtuple("Caller", "at stub cost routine routine_cost", defaults=(RTS, None))
CALLERS = []


def staged_caller(at, stub, cost, *, routine=RTS, routine_cost=None):
    """A transcription caller at `at`, declared to cost `(instructions, cycles)` — and registered."""
    caller = Caller(at, stub, cost, routine, routine_cost)
    CALLERS.append(caller)
    return caller


def assert_caller_cost(caller, regs=None):
    """`caller` entered with a bare `rts` for the routine (or its declared stand-in) costs its declared `cost`
    and nothing else: the oracle's reset (`RomBench.overhead`, which `test_tier3.py` pins) and that `rts`
    (`RTS_COST`) are all the rest of the run. Answers the register file it left, for a caller that also
    promises what it does to one."""
    pokes = {caller.at: caller.stub, STUB_AT: caller.routine, abi.FIRST_ARG: struct.pack(">I", STUB_AT)}
    _final, _writes, left = emu.run(make_image(pokes), caller.at, {**DIRTY, **(regs or {})})
    reset, rts, cost = bench().overhead, caller.routine_cost or RTS_COST, caller.cost
    assert (left["ninsns"], left["cycles"]) == (reset[0] + cost[0] + rts[0], reset[1] + cost[1] + rts[1]), (
        f"the caller at {caller.at:#x} costs {left['ninsns']} / {left['cycles']} with the reset and its routine's "
        f"stand-in, not the declared {cost} over {reset} and {rts}")
    return left


RTS_COST = (1, 16)              # the bare `rts` a caller is measured over
# THE REGISTER FILE every transcription is entered with, under the case's own registers: every register
# different, so a register the `.S` left where the ROM changed it — or changed where the ROM left it —
# shows.
DIRTY = {name: 0x0D0D_0000 + index * 0x1111 for index, name in enumerate(emu.REPORTED_REGS)}


def changed_from_dirty(registers):
    """The names of a run's reported register file that no longer hold their `DIRTY` value."""
    return {name for name in emu.REPORTED_REGS if registers[name] != DIRTY[name]}


TRANSCRIPTION_CALLER = PUSH_STACK_LONG + struct.pack(">h", abi.FIRST_ARG - emu.STACK_TOP) + RTS
PLAIN_CALLER = staged_caller(TRANSCRIPTION_CALLER_AT, TRANSCRIPTION_CALLER, (2, 40))
TRANSCRIPTIONS = []
LABELS = {}


# A CODE-POINTER CALLER: for a `.S` that returns with an address INSIDE ITSELF in a register — a fragment
# it reached through `jsr (a5)`, a loop it left in A3 — which is the one thing a transcription linked
# anywhere else must differ in. The case is entered through a caller that returns through itself and
# zeroes exactly those registers on BOTH sides, so every other register is still compared:
#
#     pea     back(pc) / move.l 8(sp),-(sp) / rts / back: suba.l An,An ... / rts
#
# (`clr.l Dn` for a data register: a jump table's displacement left in D0 is the same kind of layout fact, and a
# register a thunk's C body left is not the transcription's at all — `test_vdi_escape_transcription.py`.)
# Which registers, per routine, is MEASURED by each battery and declared to its `CallerPool`.
_ROUTINE_SLOT = abi.FIRST_ARG - emu.STACK_TOP + LONG_BYTES     # FIRST_ARG, past the pushed return
_JUMP_BYTES = len(PUSH_STACK_LONG) + WORD_BYTES + len(RTS)
# pea + move.l + rts in and an rts out, and one suba.l/clr.l per register (6 cycles as Musashi counts either): the
# declared cost of each caller is their sum, and `test_transcribed.py` measures every one against it.
CODE_POINTER_CALLER_COST = (4, 72)
CLEAR_COST = (1, 6)


def code_pointer_stub(registers):
    """The bytes of a caller that clears `registers` on the way out, and the cost it declares — position
    independent, so each battery stages its own in its own band (`CallerPool`)."""
    clears = b"".join(CLEAR_REGISTER[register] for register in registers)
    stub = (PUSH_RETURN_PC + struct.pack(">h", _JUMP_BYTES + WORD_BYTES)
            + PUSH_STACK_LONG + struct.pack(">h", _ROUTINE_SLOT) + RTS + clears + RTS)
    cost = tuple(base + len(registers) * each for base, each in zip(CODE_POINTER_CALLER_COST, CLEAR_COST))
    return stub, cost


POOLS = []


class CallerPool:
    """One battery's STAGED CALLERS, in its own band `[at, end)` one `stride` apart — no two pools' bands
    overlapping. A caller is built on first ask and registered (`staged_caller`): `staged` for any stub a
    battery builds, `caller` for the CODE-POINTER caller that clears a register set (the plain caller
    answering for an empty one). `code_pointers` is the battery's MEASURED `{routine: registers}` — what
    `caller_for` enters a routine through when a case names none. `grow` names the constant sizing the band,
    for the message when it is full."""

    def __init__(self, at, end, stride, code_pointers=None, *, built=(), grow="the pool's band"):
        overlapping = [(pool.at, pool.end) for pool in POOLS if at < pool.end and pool.at < end]
        assert not overlapping, f"callers at [{at:#x}, {end:#x}) overlap another pool's {overlapping}"
        POOLS.append(self)
        self.at, self.end, self.stride, self.grow = at, end, stride, grow
        self.code_pointers = dict(code_pointers or {})
        self._callers = {}
        # Built now, so each is registered — and its cost measured — before any case asks for it.
        for registers in (*self.code_pointers.values(), *built):
            self.caller(registers)

    def staged(self, key, build, *, routine=RTS, routine_cost=None):
        """The caller for `key`, from `build()` -> (stub, declared cost) on first ask, at the pool's next stride;
        `routine` / `routine_cost` are `staged_caller`'s."""
        if key not in self._callers:
            stub, cost = build()
            at = self.at + len(self._callers) * self.stride
            assert len(stub) <= self.stride, (
                f"the caller {key} is {len(stub)} bytes, over the pool's {self.stride:#x}-byte stride")
            assert at + self.stride <= self.end, (
                f"no room for the caller {key} in [{self.at:#x}, {self.end:#x}): its {len(self._callers)} "
                f"slots are taken — grow {self.grow}")
            self._callers[key] = staged_caller(at, stub, cost, routine=routine, routine_cost=routine_cost)
        return self._callers[key]

    def caller(self, registers):
        if not registers:
            return PLAIN_CALLER
        return self.staged(registers, lambda: code_pointer_stub(registers))

    def caller_for(self, name, code_pointers=None):
        """The caller `name`'s transcription is entered through: `code_pointers` cleared, or the routine's
        own declared set when the case names none."""
        return self.caller(self.code_pointers.get(name, ()) if code_pointers is None else code_pointers)

    def run_transcription(self, name, pokes, regs=None, *, code_pointers=None, **kwargs):
        return run_transcription(name, pokes, regs, caller=self.caller_for(name, code_pointers), **kwargs)

    def register_transcription(self, name, label, pokes, regs=None, *, code_pointers=None, **kwargs):
        return register_transcription(name, label, pokes, regs, caller=self.caller_for(name, code_pointers),
                                      **kwargs)


def transcription_symbol(name):
    """The `.S` entry an `addrs.h` routine of any component (`test/routines.py`) is transcribed as: its name
    lower-cased — or, for a routine of `src/bios/isr.S`, whose names carry no `ROM_`, what `isr.TRANSCRIBED_AS`
    says."""
    if name in isr.TRANSCRIBED_AS:
        return isr.TRANSCRIBED_AS[name]
    assert routines.prefix_of(name), (
        f"{name} is not a routine name of any component: {', '.join(prefix + '<X>' for prefix in routines.PREFIXES)}")
    return name.lower()


def transcription_routine(symbol):
    """...and back: the `addrs.h` name of the routine a `.S` entry transcribes."""
    name = symbol.upper()
    assert routines.prefix_of(name) and hasattr(addrs, name), f"{symbol} transcribes no routine `addrs.h` names"
    return name


# ---- (b) the BYTE PIN ---------------------------------------------------------------------------------
# THE BYTE PIN, one comparator for every `.S`. A transcription lays out a ROM REGION in the ROM's own
# order, so one entry in it (the `anchor` routine) places the whole region in the blob. The spelling
# policy (`include/m68k_encodings.h`) leaves exactly one kind of word that may differ: a reference that
# measures to where the `.S` itself is linked — a branch displacement from one region into another, or
# an absolute address of the transcription's own table. Each is RELOCATED: `width` says which (a word is
# a displacement from the extension word, a long an absolute address), and the comparator computes the
# EXACT value it must hold from the ROM's own reference and where `target_anchor`'s region is in the blob.
# Two further shapes: a JUMP TABLE's word is a displacement from the TABLE (`base`, the ROM address its
# `(pc,dn.w)` indexes from), not from the word itself; and a reference into code that ships as C rather than
# as a transcription names a THUNK (`thunk`, the blob symbol of the glue the `.S` carries to reach that C),
# whose place in the blob is then the exact value, with `target_anchor` None.
Relocated = namedtuple("Relocated", "width target_anchor why base thunk", defaults=(None, None))
PC_RELATIVE = WORD_BYTES
ABSOLUTE = LONG_BYTES


def transcribed_address(anchor, rom_address):
    """Where the blob holds `rom_address` of the region the `.S` entry of routine `anchor` lays out."""
    return bench().entry(transcription_symbol(anchor)) + rom_address - getattr(addrs, anchor)


def _blob_bytes(address, size):
    blob = bench()
    return bytes(blob.blob[address - blob.base:address - blob.base + size])


def _displaced_from(at, relocation):
    """What a PC-relative reference at `at` is a displacement from: its extension word, or its table."""
    return at if relocation.base is None else relocation.base


def _relocation_target(at, relocation):
    """The ROM address the ROM's own reference at `at` names: a displacement from its extension word (or
    its table), or an absolute address."""
    pc_relative = relocation.width == PC_RELATIVE
    rom = int.from_bytes(bytes(BASE_IMAGE[at:at + relocation.width]), "big", signed=pc_relative)
    return _displaced_from(at, relocation) + rom if pc_relative else rom


def _relocated_value(at, placed_at, relocation):
    """The exact bytes the reference at ROM address `at`, placed at blob address `placed_at`, must hold:
    the ROM's own reference followed to its target, and that target's place in the blob — or the thunk's."""
    if relocation.thunk:
        target = bench().entry(relocation.thunk)
    else:
        target = transcribed_address(relocation.target_anchor, _relocation_target(at, relocation))
    if relocation.width == PC_RELATIVE:
        origin = placed_at - (at - _displaced_from(at, relocation))
        return (target - origin).to_bytes(WORD_BYTES, "big", signed=True)
    return target.to_bytes(LONG_BYTES, "big")


# THE REGIONS THE BATTERIES PIN, declared where each battery lays its own out (`pinned_region`). A
# relocation's value is computed from where its TARGET routine's region sits in the blob — sound only if the
# target, and the routine it is measured from, lie in ONE region some battery byte-pins: the `.S` lays a
# region out contiguously and the pin proves it did. A reference into bytes nobody pins would be a value
# computed against a layout nobody checked (`text_raster.S`'s `lea` of raster.S's fringe table is the case
# that asks it).
Region = namedtuple("Region", "lo hi anchor entries", defaults=((),))
PINNED_REGIONS = []
# A battery that declares a region calls `pinned_region(` by that name, whatever it imported it as — the marker
# `every_pinned_region` imports a test module by (`every_pinned_region(` itself is not one).
_DECLARES_A_REGION = re.compile(r"\bpinned_region\(")


def pinned_region(lo, hi, anchor, entries=()):
    """Declare the ROM bytes `lo`..`hi`, laid out from the `.S` entry of `anchor` (and holding `entries`'),
    as a region this battery byte-pins — at import, so every region is known before any pin runs."""
    region = Region(lo, hi, anchor, tuple(entries))
    PINNED_REGIONS.append(region)
    return region


def every_pinned_region():
    """Every battery's regions, whichever batteries this process has imported: each test module that
    declares one is imported here first (a no-op for one already loaded)."""
    for path in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        if _DECLARES_A_REGION.search(path.read_text()):
            importlib.import_module(path.stem)
    return tuple(PINNED_REGIONS)


def anchor_of(rom_address, regions=None):
    """The anchor of the one byte-pinned region — of `regions`, or of every battery's — the ROM address lies in."""
    anchors = [region.anchor for region in (every_pinned_region() if regions is None else regions)
               if region.lo <= rom_address < region.hi]
    assert len(anchors) == 1, f"${rom_address:x} lies in {len(anchors)} pinned regions"
    return anchors[0]


def _one_pinned_region_holds(*addresses):
    return any(all(region.lo <= address < region.hi for address in addresses) for region in every_pinned_region())


def assert_transcribed(region, *, relocated=None):
    """The ROM's bytes of `region` (a `pinned_region`) against the blob's, laid out from the `.S` entry of its
    anchor: every other routine in its `entries` where the ROM has it, and every word EQUAL but the references
    `relocated` names — `{ROM address: Relocated}`, the battery's WHOLE map, which this cuts to the region — each
    of which must hold exactly the value its target's place in the blob gives it. A relocation that happens to
    equal the ROM's word is refused too: it names a word that needs no excuse. So is one that lies in NO pinned
    region, or one inside this region the word walk never lands on: either would excuse nothing and say so."""
    relocated = relocated or {}
    assert region in every_pinned_region(), (
        f"${region.lo:x}..${region.hi:x} from {region.anchor} is pinned but no battery declares it (`pinned_region`)")
    stray = sorted(at for at in relocated if not any(pinned.lo <= at < pinned.hi for pinned in every_pinned_region()))
    assert not stray, f"relocation(s) at {', '.join(f'${at:x}' for at in stray)} lie in no pinned region"
    relocated = {at: relocation for at, relocation in relocated.items() if region.lo <= at < region.hi}
    for at, relocation in relocated.items():
        target = _relocation_target(at, relocation)
        assert relocation.base is None or region.lo <= relocation.base < region.hi, f"${at:x}'s table is outside the region"
        if relocation.thunk:
            assert not _one_pinned_region_holds(target), (
                f"${at:x} ({relocation.why}) names the thunk {relocation.thunk}, but ${target:x} is byte-pinned — "
                f"a reference into a transcription must reach the transcription")
            continue
        assert _one_pinned_region_holds(target, getattr(addrs, relocation.target_anchor)), (
            f"${at:x} ({relocation.why}) is relocated to ${target:x} as measured from {relocation.target_anchor}, "
            f"but no byte-pinned region holds both — its value would be computed against a layout nobody checks")
    start = transcribed_address(region.anchor, region.lo)
    for name in region.entries:
        assert transcribed_address(region.anchor, getattr(addrs, name)) == bench().entry(transcription_symbol(name)), (
            f"{name} is not where the ROM has it in the region {region.anchor} lays out")
    at, walked = region.lo, set()
    while at < region.hi:
        relocation = relocated.get(at)
        size = relocation.width if relocation else WORD_BYTES
        placed_at = start + at - region.lo
        ours, theirs = _blob_bytes(placed_at, size), bytes(BASE_IMAGE[at:at + size])
        if relocation:
            walked.add(at)
            expected = _relocated_value(at, placed_at, relocation)
            assert ours != theirs, f"${at:x} is relocated ({relocation.why}) and equals the ROM's — drop it"
            assert ours == expected, (f"${at:x} ({relocation.why}) holds {ours.hex()}, not the {expected.hex()} its "
                                      f"target's place in the blob gives")
        else:
            assert ours == theirs, f"the transcription of ${at:x} holds {ours.hex()} against the ROM's {theirs.hex()}"
        at += size
    missed = sorted(set(relocated) - walked)
    assert not missed, f"relocation(s) at {', '.join(f'${at:x}' for at in missed)} fall inside another word of the walk"


def assert_the_shipped_blob_holds_the_same(region):
    """...and the SHIPPED configuration's blob holds, for `region`, the very bytes the pin above read out of the bench
    blob. Sound for a `.S` whose every relocated word is a displacement INSIDE its own file (`src/bios/isr.S`): the
    two blobs link the file at different addresses and the bytes cannot differ. A region holding an ABSOLUTE operand
    is compared operand by operand instead (`test/test_aes_irq.py`)."""
    def held_by(blob):
        return bytes_of(blob, region.anchor, region.lo, region.hi - region.lo)

    assert held_by(isr.shipped_blob()) == held_by(bench()), (
        f"the shipped blob holds other bytes than the bench blob for ${region.lo:x}..${region.hi:x}")


def bytes_of(blob, anchor, rom_address, size):
    """The `size` bytes `blob` holds where the `.S` entry of `anchor` lays `rom_address` out — on EITHER blob, where
    `_blob_bytes` reads the bench blob's alone."""
    at = blob.entry(transcription_symbol(anchor)) + rom_address - getattr(addrs, anchor) - blob.base
    return bytes(blob.blob[at:at + size])


# THE STREAM KIND — "the ROM's instruction stream with its Line-F call words as `jsr`s": how a routine Alcyon COMPILED
# ships as assembly where no compiled function can keep its contract (the AES's disp, `src/aes/switch.S`: savestate
# reads its caller's frame through disp's own A6 and hands it back another stack). Such a routine cannot be a byte-
# exact transcription — its calls are one-word Line-F exceptions through the ROM's own table, which would run the
# ROM's code from inside our build — so it is held INSTRUCTION BY INSTRUCTION instead:
#   - a Line-F CALL word must be NAMED (`CallWord`): the ROM routine its table entry reaches, and the blob symbol our
#     stream `jsr`s in its place — an absolute `jsr`, six bytes for the ROM's two. A call word nobody named, a named
#     address that holds none, or a Line-F RETURN (an Alcyon exit: no `jsr` stands for it) is refused;
#   - a BRANCH's displacement is the ROM's own target followed to where OUR stream holds that instruction (a branch
#     across a call site is four bytes longer or shorter per site crossed), its opcode byte the ROM's;
#   - every other instruction is the ROM's bytes, equal — and may not address PC-relatively (a displacement no rule
#     here follows);
#   - the stream ends where the declaration says, and our symbol's SIZE is exactly what that gives.
CallWord = namedtuple("CallWord", "routine symbol")
Stream = namedtuple("Stream", "lo hi symbol calls")
STREAMS = []
JSR_OPCODE_BYTES = WORD_BYTES
JSR_BYTES = JSR_OPCODE_BYTES + LONG_BYTES
BRANCH_OPCODE_MASK = 0xF0               # Bcc / BRA / BSR: the opcode word's top nibble is 6
BRANCH_OPCODE = 0x60
BRANCH_WORD_DISPLACEMENT = 0x00         # the low byte that says "the displacement is the next word"
BRANCH_LONG_DISPLACEMENT = 0xFF         # ...and "the next longword" (68020: no 68000 stream holds one)


def stream(lo, hi, symbol, calls):
    """Declare the ROM instructions `lo`..`hi` as a STREAM the blob's `symbol` holds, its Line-F call words `calls`
    (`{ROM address: CallWord}`) — at import, as a `pinned_region` is declared."""
    declared = Stream(lo, hi, symbol, dict(calls))
    STREAMS.append(declared)
    return declared


def _branch_target(at, opcode, extension):
    """The ROM address a branch at `at` goes to, and how many bytes its displacement is — or None for an instruction
    that is no branch."""
    if opcode >> 8 & BRANCH_OPCODE_MASK != BRANCH_OPCODE:
        return None
    short = opcode & 0xFF
    assert short != BRANCH_LONG_DISPLACEMENT, f"${at:x} is a branch with a 32-bit displacement: no 68000 instruction"
    if short == BRANCH_WORD_DISPLACEMENT:
        return at + WORD_BYTES + int.from_bytes(extension, "big", signed=True), WORD_BYTES
    return at + WORD_BYTES + int.from_bytes(bytes([short]), "big", signed=True), 1


def _stream_instruction(at, length, text, placed, declared, line_f, blob):
    """What `blob`'s stream must hold for the ROM instruction at `at` (`length` bytes, objdump's `text`; None: a
    Line-F word), given where every ROM instruction lies in it (`placed`)."""
    theirs = bytes(BASE_IMAGE[at:at + length])
    opcode = int.from_bytes(theirs[:WORD_BYTES], "big")
    if text is None:
        assert not opcode & line_f.LINE_F_RETURN_BIT, (
            f"${at:x} is a Line-F RETURN (${opcode:04x}) inside the stream ${declared.lo:x}..${declared.hi:x}: an "
            f"Alcyon exit, which no `jsr` stands for — end the stream before it, and prove it dead")
        call = declared.calls[at]
        entry_at = line_f.LINE_F_TABLE + (opcode & line_f.LINE_F_INDEX_MASK)
        reached = int.from_bytes(bytes(BASE_IMAGE[entry_at:entry_at + LONG_BYTES]), "big")
        assert reached == getattr(addrs, call.routine), (
            f"${at:x}'s call word ${opcode:04x} reaches ${reached:x} through the ROM's table, not {call.routine}")
        return JSR_ABSOLUTE_LONG + blob.entry(call.symbol).to_bytes(LONG_BYTES, "big")
    branch = _branch_target(at, opcode, theirs[WORD_BYTES:])
    if branch:
        target, displacement_bytes = branch
        assert target in placed, (
            f"${at:x} branches to ${target:x}, which is no instruction of the stream ${declared.lo:x}..${declared.hi:x}")
        displacement = placed[target] - (placed[at] + WORD_BYTES)
        if displacement_bytes == WORD_BYTES:
            return theirs[:WORD_BYTES] + displacement.to_bytes(WORD_BYTES, "big", signed=True)
        encoded = displacement.to_bytes(1, "big", signed=True)      # raises past a byte: the branch no longer fits
        assert encoded[0] not in (BRANCH_WORD_DISPLACEMENT, BRANCH_LONG_DISPLACEMENT), (
            f"${at:x}'s branch would need the displacement {displacement}, which a short branch cannot spell")
        return theirs[:1] + encoded
    assert "%pc@" not in text, f"${at:x} ({text}) addresses PC-relatively: a displacement the stream kind does not follow"
    return theirs


def assert_stream(declared, blob=None):
    """`declared.symbol` of `blob` (the bench blob, by default) against the ROM's instructions
    `declared.lo`..`declared.hi`, one by one: the rule above. Every named call word must be met, and every Line-F
    word met must be named."""
    import rom_data                     # here: `rom_data` imports this module

    blob = blob or bench()
    assert declared in STREAMS, f"${declared.lo:x}..${declared.hi:x} is held as a stream no battery declares (`stream`)"
    line_f = rom_data.linef_dis
    listed = line_f.sweep(declared.lo, declared.hi)
    undecoded = [f"${at:x}" for at, _length, text in listed if text == line_f.UNDECODED]
    assert not undecoded and sum(length for _at, length, _text in listed) == declared.hi - declared.lo, (
        f"the stream ${declared.lo:x}..${declared.hi:x} does not decode whole (undecoded at {undecoded})")
    words = {at for at, _length, text in listed if text is None}
    assert words == set(declared.calls), (
        f"the stream's Line-F words are at {sorted(map(hex, words))}, its named calls at "
        f"{sorted(map(hex, declared.calls))}: every one is named, and nothing else is")
    start = blob.entry(declared.symbol)
    placed, at_ours = {}, start
    for at, length, text in listed:
        placed[at] = at_ours
        at_ours += JSR_BYTES if text is None else length
    for at, length, text in listed:
        expected = _stream_instruction(at, length, text, placed, declared, line_f, blob)
        ours = bytes(blob.blob[placed[at] - blob.base:placed[at] - blob.base + len(expected)])
        assert ours == expected, (
            f"the stream of ${at:x} ({text or 'a Line-F call'}) holds {ours.hex()}, not {expected.hex()}")
    sized = {symbol.name: symbol.size for symbol in symbol_table(blob.elf)}[declared.symbol]
    assert sized == at_ours - start, (
        f"{declared.symbol} is {sized} bytes, the stream ${declared.lo:x}..${declared.hi:x} with its "
        f"{len(declared.calls)} calls as `jsr`s {at_ours - start}: an instruction more, or the stream cut short")


def transcription_pokes(name, pokes, caller=PLAIN_CALLER):
    """`pokes` with the staged caller and the ROM routine it enters on the ORIGINAL's side."""
    return merge_pokes(pokes, {caller.at: caller.stub, abi.FIRST_ARG: struct.pack(">I", getattr(addrs, name))})


def run_transcription(name, pokes, regs=None, *, io_seed=None, caller=PLAIN_CALLER):
    """The `.S` of `addrs.<name>` against the ROM routine over `pokes`, through the transcription
    relation, entered with `regs` laid over `DIRTY` — the WHOLE register file. Answers the `Measurement`."""
    return bench().measure_transcription(caller.at, transcription_symbol(name), {**DIRTY, **(regs or {})},
                                         pokes=transcription_pokes(name, pokes, caller), io_seed=io_seed,
                                         shared_entry=caller.cost)


def register_transcription(name, label, pokes, regs=None, *, io_seed=None, caller=PLAIN_CALLER):
    """One Tier 3 TRANSCRIPTION row (`bench/tier3.py` reads `TRANSCRIPTIONS`), entered as
    `run_transcription` enters it: `label` is the case, and the function's own label is its C rows' — the one
    labelling rule, `routines.role` — marked `(.S)`, so a Line-A `.S` row reads `Line-A linea_hline (.S)` beside
    its C rows' `Line-A linea_hline`."""
    symbol = transcription_symbol(name)
    LABELS[symbol] = f"{routines.role(name)} (.S)"
    row = (label, symbol, caller.at, {**DIRTY, **(regs or {})}, transcription_pokes(name, pokes, caller), caller.cost,
           io_seed)
    TRANSCRIPTIONS.append(row)
    return row


# ---- (c) the TRANSCRIBED table: which routines SHIP as their `.S` (`include/transcribed.h`) ------------
# `{`.S` entry: the GCC callee-saved registers it leaves changed}`, parsed out of the header's rows as
# `addrs.py` parses a `#define`: the one source Tier 3's (T) rule, the build contract and the C
# declarations all read. `test_transcribed.py` holds it to the `.S` sources, the makefile and the
# ROM's measured register file.
TRANSCRIBED_HEADER = _RECREATE / "include" / "transcribed.h"
_TRANSCRIBED_ROW = re.compile(r'^\s*ENTRY\((?P<entry>[a-z0-9_]+),\s*"(?P<destroys>[^"]*)"\)')
TRANSCRIBED = {match["entry"]: tuple(match["destroys"].split())
               for match in map(_TRANSCRIBED_ROW.match, TRANSCRIBED_HEADER.read_text().splitlines()) if match}
assert TRANSCRIBED, f"{TRANSCRIBED_HEADER} has no `ENTRY(...)` row this parser reads"


def transcribed_core(entry):
    """The C core a `.S` entry is the transcription of: `linea_rom_hline` -> `linea_hline`."""
    return routines.core_symbol(transcription_routine(entry))


TRANSCRIBED_CORES = {transcribed_core(entry): entry for entry in TRANSCRIBED}

# THE ALCYON ENTRIES: the `.globl`s of `atari/target.mk`'s ALCYON_ENTRY_SOURCES — target-only glue, no table row —
# read from the makefile's own line, so Tier 3 counts as glue exactly what the build links as it.
# `test_transcribed.py` holds this parse to make's own expansion of the list.
TARGET_MK = _RECREATE / "atari" / "target.mk"
GLOBL = re.compile(r"^\s*\.globl\s+(\w+)", re.MULTILINE)


def globl_entries(sources):
    """Every `.globl` the `.S` files `sources` define."""
    return {name for source in sources for name in GLOBL.findall(Path(source).read_text())}


def _listed_sources(variable):
    """The `.S` files `atari/target.mk` lists as `variable := ...` (each `$(RECREATE)` this tree)."""
    (sources,) = re.findall(rf"^{variable}\s*:=(?P<sources>.*)$", TARGET_MK.read_text(), re.MULTILINE)
    return [source.replace("$(RECREATE)", str(_RECREATE)) for source in sources.split()]


def alcyon_entry_sources():
    """ALCYON_ENTRY_SOURCES, as `atari/target.mk` writes it."""
    return _listed_sources("ALCYON_ENTRY_SOURCES")


ALCYON_ENTRIES = globl_entries(alcyon_entry_sources())
assert ALCYON_ENTRIES, f"{TARGET_MK}'s ALCYON_ENTRY_SOURCES define no `.globl` this parser reads"


# THE SWITCH's sources (`atari/target.mk`: SWITCH_SOURCES — the process switch's hand 68000, the ROM's bytes with no C
# twin and no table row) and the entries they define, under the names the C calls them by.
def switch_sources():
    """SWITCH_SOURCES, as `atari/target.mk` writes it."""
    return _listed_sources("SWITCH_SOURCES")


SWITCH_GLOBLS = globl_entries(switch_sources())
assert SWITCH_GLOBLS, f"{TARGET_MK}'s SWITCH_SOURCES define no `.globl` this parser reads"
# ...and THE TABLE OF THE KIND, one row per entry: the ROM routine it is, its length in the ROM, and its EXITS — the
# blob symbols its bytes name where the ROM's name the ROM's own code (a relocation of its region's pin, a call word
# of its stream). NO entry of the kind reaches the AES's ROM text: an exit is a symbol of our build, always.
# `test_aes_switch.py` / `test_aes_irq.py` hold each row to its pin, and the rows to the sources' `.globl`s.
SwitchEntry = namedtuple("SwitchEntry", "rom bytes exits", defaults=(frozenset(),))
# The glue's last routine ($fed426..$fed477: to its `rts`) — the one length of the kind no named address closes.
TICK_GLUE_BYTES = 82
SWITCH_REGION_END = addrs.AES_ROM_SWITCHTO_RTE + len(RTE)
GLUE_REGION_END = addrs.AES_ROM_TICK_GLUE + TICK_GLUE_BYTES


def _end_to_end(routines, end):
    """`{entry: SwitchEntry}` of `routines` (`(entry, ROM address, exits)`, in the ROM's order) LAID END TO END: each
    as long as the distance to the next, the last to `end` — a region's lengths are its routines' addresses."""
    starts = [rom for _entry, rom, _exits in routines] + [end]
    return {entry: SwitchEntry(rom, following - rom, frozenset(exits))
            for (entry, rom, exits), following in zip(routines, starts[1:])}


SWITCH_ENTRIES = {
    # gemdosif's switch, `src/aes/switch.S` ($fe387c..$fe395b): byte-exact but for dsptch's `jmp`, into our disp
    **_end_to_end((("aes_dsptch", addrs.AES_ROM_DSPTCH, {"aes_rom_disp"}),
                   ("aes_rom_spl7_save", addrs.AES_ROM_SPL7_SAVE, ()), ("aes_rom_spl_restore", addrs.AES_ROM_SPL_RESTORE, ()),
                   ("aes_rom_cli", addrs.AES_ROM_CLI, ()), ("aes_rom_sti", addrs.AES_ROM_STI, ()),
                   ("aes_rom_gotopgm", addrs.AES_ROM_GOTOPGM, ()), ("aes_rom_savestate", addrs.AES_ROM_SAVESTATE, ()),
                   ("aes_rom_switchto", addrs.AES_ROM_SWITCHTO, ())), SWITCH_REGION_END),
    # gemdisp's disp, the same file: the ROM's stream to its last call (`stream`), its six call words `jsr`s
    "aes_rom_disp": SwitchEntry(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_END - addrs.AES_ROM_DISP,
                                frozenset({"aes_rom_savestate", "aes_rom_switchto", "disp_to_aes_disp_act",
                                           "disp_to_aes_mwait_act", "disp_to_aes_forker", "disp_to_aes_idle"})),
    # the interrupts' glue, `src/aes/irq.S` ($fed3be..$fed477): byte-exact but for its calls of C and the two fork
    # functions it pushes by value
    **_end_to_end((("aes_rom_button_glue", addrs.AES_ROM_BUTTON_GLUE, {"aes_b_click_alcyon"}),
                   ("aes_rom_motion_glue", addrs.AES_ROM_MOTION_GLUE, {"aes_forkq_alcyon", "aes_mchange_fork"}),
                   ("aes_rom_drawrat", addrs.AES_ROM_DRAWRAT, ()), ("aes_rom_justretf", addrs.AES_ROM_JUSTRETF, ()),
                   ("aes_rom_tick_glue", addrs.AES_ROM_TICK_GLUE, {"aes_forkq_alcyon", "aes_tchange_fork", "aes_b_delay_alcyon"})),
                  GLUE_REGION_END),
}
assert set(SWITCH_ENTRIES) == SWITCH_GLOBLS, (
    f"the switch's table and its sources' `.globl`s disagree: {sorted(set(SWITCH_ENTRIES) ^ SWITCH_GLOBLS)}")

# THE C THAT CALLS A TRANSCRIBED C CORE from outside the table, as `(caller, core)`: the one list of the
# calls a shipped build makes through glue (`bench/shipped_glue.py` generates a thunk per core named here).
# `test_transcribed.py` holds it to the calls the m68k build really makes (`call_graph`).
C_CALLERS_OF_TRANSCRIBED_CORES = {
    # the object library's C (`src/aes/objects.c`): ob_find's and ob_center's rectangles
    ("aes_ob_find", "aes_r_set"), ("aes_ob_center", "aes_r_set"),
    # ...and its word copies of an object's rectangle (`optimize.S`'s wcopy)
    ("aes_ob_find", "aes_wcopy"), ("aes_ob_setxywh", "aes_wcopy"), ("aes_ob_relxywh", "aes_wcopy"),
    # the rectangle lists (`src/aes/rlist.c`): mkpiece's edges; the resource fix-ups (`src/aes/resource.c`)
    ("aes_mkpiece", "aes_min"), ("aes_mkpiece", "aes_max"), ("aes_fix_tedinfo", "aes_lstrlen"),
    # a window's rectangles (`src/aes/wrect.c`): w_getsize's copy, and newrect's (w_getsize inlined into it)
    ("aes_w_getsize", "aes_rc_copy"), ("aes_newrect", "aes_rc_copy"),
    # the window library (`src/aes/wmlib.c`, w_getsize/w_setsize inlined into its callers): the rectangles copied and
    # cut, the slider's sums, the clip read back, the save buffer, wm_start's clears
    ("aes_w_setsize", "aes_rc_copy"), ("aes_w_clipdraw", "aes_rc_copy"), ("aes_w_move", "aes_rc_copy"),
    ("aes_w_owns", "aes_rc_copy"), ("aes_w_union", "aes_rc_copy"), ("aes_wm_create", "aes_rc_copy"),
    ("aes_wm_start", "aes_rc_copy"), ("build_active", "aes_rc_copy"), ("aes_w_move", "aes_rc_union"),
    ("aes_w_union", "aes_rc_union"), ("aes_w_barcalc", "aes_max"), ("aes_w_barcalc", "aes_mul_div"),
    ("aes_w_barcalc", "aes_r_set"), ("aes_w_cpwalk", "aes_gsx_gclip"), ("aes_wm_get", "aes_gsx_mret"),
    ("aes_wm_start", "aes_bfill"),
    # ...and its half that reaches the event layer (`src/aes/wmupdate.c`): the control rectangle copied, the change's
    # rectangles copied, joined and compared (draw_change's helpers inlined into it), the sliders clamped, the cursor
    # shown again
    ("aes_set_ctrl", "aes_rc_copy"), ("aes_get_ctrl", "aes_rc_copy"), ("aes_fm_own", "aes_rc_copy"),
    ("aes_w_redraw", "aes_rc_copy"), ("aes_wm_opcl", "aes_rc_copy"), ("aes_draw_change", "aes_rc_copy"),
    ("aes_wm_close", "aes_rc_copy"),    # wm_opcl inlined into wm_close, the lock's tak_flag now an ordinary call
    ("aes_draw_change", "aes_rc_union"), ("aes_draw_change", "aes_rc_equal"), ("aes_draw_change", "aes_max"),
    ("aes_wm_set", "aes_max"), ("aes_wm_set", "aes_min"), ("aes_w_update", "aes_gsx_mon"),
    # the drag loops (`src/aes/grdrag.c`, gr_clamp inlined into gr_rubwind, gr_draw/gr_xdraw folded): the mouse read,
    # the box kept in its bound, the offset compared with gl_rzero, the slider's thousandths, the cursor shown again
    ("aes_gr_clamp", "aes_gsx_mxmy"), ("aes_gr_rubwind", "aes_gsx_mxmy"), ("aes_gr_dragbox", "aes_gsx_mxmy"),
    ("aes_gr_dragbox", "aes_rc_constrain"), ("aes_gr_wait", "aes_rc_equal"), ("aes_gr_slidebox", "aes_mul_div"),
    ("gr_xdraw", "aes_gsx_mon"),
    # the menu library (`src/aes/mnlib.c`, pd_nameit inlined into mn_register): the screen manager's rectangle, the
    # button read on an item, a name copied, blank-filled and scanned
    ("aes_mn_bar", "aes_rc_copy"), ("aes_mn_do", "aes_gsx_button"), ("aes_mn_register", "aes_lstcpy"),
    ("aes_mn_register", "aes_bfill"), ("aes_mn_register", "aes_strscn"), ("aes_pd_nameit", "aes_bfill"),
    ("aes_pd_nameit", "aes_strscn"),
    ("aes_rs_str", "aes_lstcpy"), ("resource_part", "aes_wcopy"), ("aes_rom_ram", "aes_lbcopy"),
    ("aes_sc_read", "aes_lstcpy"), ("aes_sc_write", "aes_lstcpy"), ("aes_sh_read", "aes_lbcopy"),
    ("aes_sh_write", "aes_lbcopy"), ("aes_sh_get", "aes_lbcopy"), ("aes_sh_put", "aes_lbcopy"),
    ("aes_rom_rsc_init", "aes_lbcopy"),
    # the object-text helpers (`src/aes/objtext.c`): every text in or out of a TEDINFO through lstcpy
    ("aes_fs_sset", "aes_lstcpy"), ("aes_inf_sset", "aes_lstcpy"), ("aes_fs_sget", "aes_lstcpy"),
    # the shell's find (`src/aes/shell_find.c`: sh_name inlined into sh_find) and the resource load's spec copy
    ("aes_sh_name", "aes_strlen"), ("aes_sh_find", "aes_strlen"), ("aes_sh_find", "aes_lstcpy"),
    ("aes_sh_find", "aes_strcpy"), ("aes_sh_find", "aes_strcat"), ("aes_sh_path", "aes_lstcpy"),
    ("envrn_search", "aes_lstcpy"), ("envrn_search", "aes_lbcopy"), ("envrn_search", "aes_streq"),
    ("aes_rs_readit", "aes_lstcpy"),
    # the VDI binding's C (`src/aes/gsx.c`): every wrapper's call, and gsx_moff's v_hide_c (its static `gsx_moff_hide`),
    # through gsx_ncode
    ("gsx_moff_hide", "aes_gsx_ncode"), ("aes_v_pline", "aes_gsx_ncode"), ("aes_vs_clip", "aes_gsx_ncode"),
    ("aes_vst_height", "aes_gsx_ncode"), ("aes_vr_recfl", "aes_gsx_ncode"), ("aes_vro_cpyfm", "aes_gsx_ncode"),
    ("aes_vrt_cpyfm", "aes_gsx_ncode"), ("aes_vrn_trnfm", "aes_gsx_ncode"), ("aes_vsl_width", "aes_gsx_ncode"),
    # ...and the rest of gemgsxif (`src/aes/gsxif.c`): its calls through gsx_ncode (`gsx_call`, inlined), gsx_1code
    # and gsx_mon, gsx_fix's MFDBs, and the mouse form's copies
    ("aes_gsx_escapes", "aes_gsx_ncode"), ("graphic_mode_change", "aes_gsx_ncode"), ("aes_gsx_init", "aes_gsx_ncode"),
    ("aes_gsx_resetmb", "aes_gsx_ncode"), ("aes_gsx_setmb", "aes_gsx_ncode"), ("aes_gsx_setmb_aes", "aes_gsx_ncode"),
    ("aes_gsx_start", "aes_gsx_ncode"), ("aes_gsx_tick", "aes_gsx_ncode"), ("aes_gsx_wsclose", "aes_gsx_ncode"),
    ("aes_gsx_wsopen", "aes_gsx_ncode"), ("aes_v_opnwk", "aes_gsx_ncode"), ("aes_gsx_mfset", "aes_gsx_ncode"),
    ("aes_gsx_mfset", "aes_gsx_mon"), ("aes_bb_set", "aes_gsx_mon"), ("aes_gsx_start", "aes_gsx_1code"),
    ("aes_bb_set", "aes_gsx_fix"), ("aes_gsx_malloc", "aes_gsx_fix"),
    ("aes_gsx_mfsave", "aes_lbcopy"), ("aes_gsx_mfrestore", "aes_lbcopy"), ("aes_bb_save", "aes_gsx_fix"),
    ("aes_bb_save", "aes_gsx_mon"), ("aes_bb_restore", "aes_gsx_fix"), ("aes_bb_restore", "aes_gsx_mon"),
    # the graphics library (`src/aes/gemgraf.c`, `grlib.c`): gsx2's hand-built calls, the one-word calls, the MFDBs, the
    # cursor shown again, gsx_tcalc's string, and its own leaves (gr_box's through gsx_box, inlined into it)
    ("aes_gsx_attr", "aes_gsx2"), ("aes_gsx_tblt", "aes_gsx2"),
    ("aes_gr_box", "aes_gr_inside"), ("aes_gr_box", "aes_gsx_bxpts"), ("aes_gsx_box", "aes_gsx_bxpts"),
    ("aes_gsx_xbox", "aes_gsx_bxpts"),
    ("aes_bb_fill", "aes_gsx_1code"), ("aes_gr_rect", "aes_gsx_1code"), ("aes_gsx_xline", "aes_gsx_1code"),
    ("aes_gsx_xbox", "aes_gsx_1code"), ("aes_gsx_xcbox", "aes_gsx_1code"),
    ("aes_bb_fill", "aes_gsx_fix"), ("aes_gsx_blt", "aes_gsx_fix"), ("aes_gsx_trans", "aes_gsx_fix"),
    ("aes_gsx_blt", "aes_gsx_mon"), ("aes_gsx_cline", "aes_gsx_mon"), ("aes_gr_box", "aes_gsx_mon"),
    ("aes_gr_movebox", "aes_gsx_mon"), ("aes_gr_growbox", "aes_gsx_mon"), ("aes_gr_shrinkbox", "aes_gsx_mon"),
    ("aes_gsx_tcalc", "aes_xstrpix"),
    # the object draw path (`src/aes/objdraw.c`): just_draw's copies, the clip test, the colours and its marks
    ("aes_just_draw", "aes_gr_crack"), ("aes_just_draw", "aes_gr_inside"), ("aes_just_draw", "aes_gsx_1code"),
    ("aes_just_draw", "aes_gsx_chkclip"), ("aes_just_draw", "aes_lbcopy"), ("aes_just_draw", "aes_lstcpy"),
    ("aes_just_draw", "aes_rc_copy"), ("aes_just_draw", "aes_xstrpix"),
    # the object draw path's leaves (`src/aes/obuser.c`): ob_format's two lengths, ob_user's PARMBLK rectangles
    ("aes_ob_format", "aes_strlen"), ("aes_ob_user", "aes_rc_copy"), ("aes_ob_user", "aes_gsx_gclip"),
    # ...and just_draw's two callers (`src/aes/obdraw.c`): the cursor shown again after the walk and after a change
    ("aes_ob_draw", "aes_gsx_mon"), ("aes_ob_change", "aes_gsx_mon"),
    # ...and the control manager's mouse grab (`src/aes/ctrl.c`): the arrow shown, the cursor hidden and shown again
    ("aes_ct_mouse", "aes_gsx_1code"), ("aes_ct_mouse", "aes_gsx_ncode"),
    # the object editor (`src/aes/obedit.c`): its copies and lengths (ob_getsp and ob_delit inlined into ob_edit too),
    # check's upcase, the redraw's bounds, and the cursor's clip saved
    ("aes_ob_getsp", "aes_lbcopy"), ("aes_ins_char", "aes_strlen"), ("aes_ob_stfn", "aes_strlen"),
    ("aes_ob_delit", "aes_strcpy"), ("aes_check", "aes_toupper"), ("aes_curfld", "aes_gsx_gclip"),
    ("aes_ob_edit", "aes_lbcopy"), ("aes_ob_edit", "aes_lstcpy"), ("aes_ob_edit", "aes_strlen"),
    ("aes_ob_edit", "aes_strcpy"), ("aes_ob_edit", "aes_bfill"), ("aes_ob_edit", "aes_min"), ("aes_ob_edit", "aes_max"),
    # the form library (`src/aes/fmlib.c`): a section's longest line, and the alert box's layout; its half that waits
    # (`src/aes/fmdo.c`, fm_show inlined into eralert and fm_error): an AES string merged, the alert's clip saved
    ("aes_fm_strbrk", "aes_max"), ("aes_fm_build", "aes_r_set"), ("aes_fm_build", "aes_max"),
    ("aes_fm_show", "aes_merge_str"), ("aes_eralert", "aes_merge_str"), ("aes_fm_error", "aes_merge_str"),
    ("aes_fm_alert", "aes_gsx_gclip"),
    # the event blocks' lists (`src/aes/evasync.c`): a free EVB cleared
    ("aes_get_evb", "aes_bfill"),
    # processes and their pipes (`src/aes/pdpipe.c`): a PD's name copied out and compared (pd_match, inlined into fpdnm
    # too), a message moved and a redraw merged, the name ap_find is asked for copied — and gemdosif's two leaves, which
    # ship as the ROM's own instructions (`pdpipe.S`)
    ("aes_pd_match", "aes_movs"), ("aes_pd_match", "aes_streq"), ("aes_fpdnm", "aes_movs"), ("aes_fpdnm", "aes_streq"),
    ("aes_doq", "aes_lbcopy"), ("aes_doq", "aes_rc_union"), ("aes_ap_find", "aes_lstcpy"),
    ("aes_getpd", "aes_uda_insuper"), ("aes_pstart", "aes_psetup"),
    # the waits (`src/aes/evwait.c`, `evlib.c`, `evmulti.c`): amouse's copy of its MOBLK, ev_timer's and ev_multi's
    # milliseconds into ticks
    ("aes_amouse", "aes_lbcopy"), ("aes_ev_timer", "aes_ldiv"), ("aes_ev_multi", "aes_ldiv"),
    # the fork queue (`src/aes/evfork.c`): the keyboard's and the mouse's polls through the VDI binding, the recorder's
    # copy of an entry
    ("aes_chkkbd", "aes_gsx_ncode"), ("aes_mchange", "aes_gsx_ncode"), ("aes_forker", "aes_lbcopy"),
    # the event tape (`src/aes/aptape.c`): a timer record's ticks into milliseconds at the playback's scale, and the
    # VDI's cursor and motion routines exchanged through the VDI binding
    ("aes_ap_tplay", "aes_lmul"), ("aes_ap_tplay", "aes_ldiv"), ("aes_ap_tplay", "aes_set_contrl_ptr"),
    ("aes_ap_tplay", "aes_gsx_ncode"), ("aes_ap_tplay", "aes_get_contrl_ptr2"),
    # the file selector (`src/aes/fslib.c`): the default path copied, a directory's names copied, matched and compared,
    # a row's name formatted and the elevator's share, the list's clip saved, and the title's text
    ("aes_fs_pspec", "aes_strcpy"), ("aes_fs_active", "aes_lstcpy"), ("aes_fs_active", "aes_strchk"),
    ("aes_fs_active", "aes_wildcmp"), ("aes_fs_format", "aes_fmt_str"), ("aes_fs_format", "aes_lstcpy"),
    ("aes_fs_format", "aes_max"), ("aes_fs_format", "aes_min"), ("aes_fs_format", "aes_mul_div"),
    ("aes_fs_nscroll", "aes_gsx_gclip"), ("aes_fs_newdir", "aes_lstcpy"), ("aes_fs_newdir", "aes_strcat"),
    ("aes_fs_newdir", "aes_strcpy"),
    # ...and the selector itself: its fields' texts copied in and out, a name formatted and unformatted, the path
    # compared with the one last read, the mouse asked, the elevator's place scaled to a row
    ("aes_fs_input", "aes_fmt_str"), ("aes_fs_input", "aes_gsx_mxmy"), ("aes_fs_input", "aes_lstcpy"),
    ("aes_fs_input", "aes_mul_div"), ("aes_fs_input", "aes_strcat"), ("aes_fs_input", "aes_strcpy"),
    ("aes_fs_input", "aes_streq"), ("aes_fs_input", "aes_unfmt_str"),
    ("vdi_vq_key_s", "vdi_get_kbshift"),
    # the polygon and contour-fill layer (`src/vdi/fill.c`)
    ("vdi_clip_line", "vdi_smul_div"), ("vdi_polyline", "linea_line"), ("vdi_plygn", "linea_filled_poly"),
    ("vdi_v_get_pixel", "linea_get_pixel"),
    ("linea_get_seed", "linea_end_pts"), ("linea_get_seed", "linea_fill_span"),
    ("linea_contour_fill", "linea_end_pts"), ("linea_contour_fill", "linea_get_pixel"),
    ("linea_contour_fill", "linea_fill_span"),
    # the raster functions (`src/vdi/blit.c`)
    ("vdi_vro_cpyfm", "linea_copy_raster"), ("vdi_vrt_cpyfm", "linea_copy_raster"), ("vdi_vr_recfl", "linea_filled_rect"),
    # the mouse and input functions (`src/vdi/mouse.c`)
    ("vdi_v_show_c", "vdi_show_cursor"), ("vdi_v_hide_c", "linea_hide_mouse"),
    ("vdi_locator", "vdi_show_cursor"), ("vdi_locator", "vdi_poll_locator"), ("vdi_locator", "linea_hide_mouse"),
    ("vdi_choice", "vdi_poll_choice"), ("vdi_mouse_init", "vdi_vsc_form"),
    # the wide lines and arrowheads (`src/vdi/lines.c`): the aspect scaling and the discs' rows
    ("vdi_wline", "vdi_smul_div"), ("vdi_do_arrow", "vdi_smul_div"), ("draw_arrowhead", "vdi_smul_div"),
    ("vdi_do_circ", "linea_line"),
    # the arcs and rounded boxes (`src/vdi/arcs.c`): a point's projection, the sweep's steps, the aspect
    ("vdi_clc_pts", "vdi_smul_div"), ("draw_arc", "vdi_smul_div"), ("vdi_gdp_arc", "vdi_smul_div"),
    ("vdi_gdp_rbox", "vdi_smul_div"),
    # the GDP's circle arm (`src/vdi/gdp.c`): its y radius in the aspect
    ("vdi_gdp", "vdi_smul_div"),
    # the screen clear (`src/vdi/screen.c`), which GCC inlines into the two routines that end in it — and the
    # BIOS span clear's other caller, GEMDOS's program loader (`src/gemdos/pexec_load.c`)
    ("vdi_v_clrwk", "vdi_clear_span"), ("vdi_init_timer_mouse", "vdi_clear_span"),
    ("vdi_restore_timer_mouse", "vdi_clear_span"), ("gemdos_pexec_load", "vdi_clear_span"),
    # the text layer's C (`src/vdi/text.c`): the scaler's two helpers
    ("vdi_vst_height", "vdi_clc_dda"), ("vdi_make_header", "vdi_act_siz"), ("vdi_vqt_extent", "vdi_act_siz"),
    ("vdi_vqt_width", "vdi_act_siz"),
    # graphic text (`src/vdi/gtext.c`, v_gtext's body past its count test): each glyph through TextBlt, a plain
    # string through the fast path, the underline's rows through $a003
    ("place_and_draw", "linea_textblt"), ("place_and_draw", "linea_fast_text"), ("place_and_draw", "linea_line"),
    # the workstations (`src/vdi/workstation.c`): the open's realized palette, and the GEMDOS door
    ("vdi_v_opnwk", "vdi_vq_color"), ("vdi_v_opnvwk", "vdi_gemdos_call"), ("vdi_v_clsvwk", "vdi_gemdos_call"),
    ("vdi_v_clswk", "vdi_gemdos_call"),
}

# ---- (d) the m68k build's CALL GRAPH -------------------------------------------------------------------
# A function's name as `m68k-elf-objdump` labels it, the one GCC split off it (`name.part.0`, `.constprop.0`,
# `.isra.0`) folded back into it, and an offset into it (`name+0x12`) dropped.
LISTED_FUNCTION = re.compile(r"^([0-9a-f]+) <([\w.]+)>:$")
_LISTED_INSTRUCTION = re.compile(r"^\s+([0-9a-f]+):")
_LISTED_REFERENCE = re.compile(r"(?:\b([0-9a-f]+) )?<([\w.]+)(?:\+0x([0-9a-f]+))?>")
# ...and a function's address loaded as an IMMEDIATE, which objdump prints in decimal without its name:
# GCC's way of calling one function several times through a register (`move.l #243526,d2`) or a frame slot
# it spills to (`move.l #212346,84(sp)`). ONLY that shape — a `move.l`/`movea.l` of the immediate into a
# register or a stack slot: a constant compared (`cmp.l #N,d0`), added or stored into the image that merely
# EQUALS a function's start is data, and read as a call it would forge an edge into (T→).
_LISTED_IMMEDIATE = re.compile(r"\tmovea?l #(\d+),(?:%[ad]\d|%(?:sp|fp)@\(-?\d+\))$")


def _unsplit(name):
    return name.split(".")[0]


# One line of `m68k-elf-nm -S --defined-only`: `size` is None for a symbol the table does not size.
Symbol = namedtuple("Symbol", "start size kind name")


@functools.cache
def _symbol_table_at(path):
    table = subprocess.run(["m68k-elf-nm", "-S", "--defined-only", path], capture_output=True, text=True,
                           check=True).stdout
    symbols = []
    for fields in (line.split() for line in table.splitlines()):
        if len(fields) == 4:
            symbols.append(Symbol(int(fields[0], 16), int(fields[1], 16), fields[2], fields[3]))
        elif len(fields) == 3:
            symbols.append(Symbol(int(fields[0], 16), None, fields[1], fields[2]))
    return tuple(symbols)


def symbol_table(elf):
    """Every symbol `elf` defines, as `Symbol`s — one `nm` run per ELF per process, whoever asks (the call
    graph's ends and starts, `bench/tier3.py`'s glue ranges)."""
    return _symbol_table_at(str(Path(elf).resolve()))


def _function_ends(elf):
    """`{address: end}` of every function the symbol table SIZES. A disassembly runs a function on to the
    next label, and in the shipped blob the next label is not always the next function: a weak C core the
    glue displaced keeps its body but loses its name, so its instructions would be read as its neighbour's."""
    return {symbol.start: symbol.start + symbol.size for symbol in symbol_table(elf) if symbol.size is not None}


def _function_starts(elf):
    """`{address: name}` of every function the symbol table places, for an immediate that names one."""
    return {symbol.start: symbol.name for symbol in symbol_table(elf) if symbol.kind in "Tt"}


# Where a symbol is DEFINED, as `readelf -s` groups it: a LOCAL symbol under the FILE symbol before it (a file name
# two objects share, `palette.c`, numbered on its second use: `palette.c#2`), every GLOBAL one in the one namespace
# a link has — `GLOBAL_ORIGIN`. Link-stable, where an address moves with every edit before it.
GLOBAL_ORIGIN = None
_CODE_SYMBOL_TYPES = ("FUNC", "NOTYPE")
_READELF_SYMBOL_FIELDS = 8          # Num: Value Size Type Bind Vis Ndx Name
_NO_SECTION = ("UND", "ABS")


@functools.cache
def _symbol_origins_at(path):
    table = subprocess.run(["m68k-elf-readelf", "-sW", path], capture_output=True, text=True, check=True).stdout
    origins, seen_files, current = {}, {}, None
    for fields in (line.split() for line in table.splitlines()):
        if len(fields) != _READELF_SYMBOL_FIELDS or not fields[0].endswith(":"):
            continue
        _index, value, _size, kind, bind, _visibility, section, name = fields
        if kind == "FILE":
            seen_files[name] = seen_files.get(name, 0) + 1
            current = name if seen_files[name] == 1 else f"{name}#{seen_files[name]}"
        elif kind in _CODE_SYMBOL_TYPES and section not in _NO_SECTION:
            origins[(int(value, 16), name)] = current if bind == "LOCAL" else GLOBAL_ORIGIN
    return origins


def symbol_origins(elf):
    """`{(address, name): origin}` of every code symbol `elf` defines — its defining file, or `GLOBAL_ORIGIN`."""
    return _symbol_origins_at(str(Path(elf).resolve()))


@functools.cache
def _listing_at(path):
    return subprocess.run(["m68k-elf-objdump", "-d", path], capture_output=True, text=True, check=True).stdout


def listing(elf):
    """`elf`'s `objdump -d` listing — one disassembly per ELF per process, whoever asks (the call graph, the
    functions `bench/tier3.py` finds a `trap #2` in)."""
    return _listing_at(str(Path(elf).resolve()))


def call_graph(elf):
    """`{function: every function its code references}` out of the m68k build at `elf` — a `jsr`, a
    branch, or a `lea` or `move.l #` of an address GCC then calls through a register or a frame slot, which
    is how it calls one it names more than once. A function the symbol table sizes is read to its end and no
    further; one whose name another definition shares is QUALIFIED by its defining file (`nodes_of_labels`)."""
    return graph_of_listing(listing(elf), _function_ends(elf), _function_starts(elf), symbol_origins(elf))


def _is_clone(name):
    return name != _unsplit(name)


def _qualifies(defined):
    """Whether the definitions `[(address, name, origin)]` of ONE base name are more than one function. They are one
    when they share an origin — a static and the pieces GCC split off it in its own file — or when they are a global
    and nothing but CLONES in one file, which GCC only makes of a function its own file defines: the global's."""
    origins = {origin for _address, _name, origin in defined}
    if len(origins) == 1:
        return False
    local_origins = origins - {GLOBAL_ORIGIN}
    clones_of_the_global = (GLOBAL_ORIGIN in origins and len(local_origins) == 1
                            and all(_is_clone(name) for _address, name, origin in defined if origin is not GLOBAL_ORIGIN))
    return not clones_of_the_global


def _qualified(base, origin):
    """A qualified node: the global keeps the bare name — the one a Tier 3 row names — and a local takes its origin's."""
    if origin is GLOBAL_ORIGIN:
        return base
    return f"{base}@{origin:x}" if isinstance(origin, int) else f"{base}@{origin}"


def nodes_of_labels(labels, origins=None):
    """`{(address, name): node}` for every listed function label `(address, name)`: its base name (`_unsplit`),
    QUALIFIED by its origin when that base names more than one function — so their bodies never merge into one node,
    and a lookup of the bare name finds the global's (or none) rather than a static's. `origins` is `symbol_origins`'
    table; without one (a synthetic listing) each label is its own origin, and a shared base is qualified by address."""
    by_base = {}
    for address, name in labels:
        origin = address if origins is None else origins.get((address, name), address)
        by_base.setdefault(_unsplit(name), []).append((address, name, origin))
    nodes = {}
    for base, defined in by_base.items():
        qualify = _qualifies(defined)
        nodes.update({(address, name): _qualified(base, origin) if qualify else base
                      for address, name, origin in defined})
    return nodes


def _references(line, starts, nodes, nodes_of_base):
    """The functions one listed instruction names: by label (`<name+0x12>`, its start = address - offset) or
    as an immediate address (`starts`). A label that is no listed function's start — no address printed, or a
    name several functions share referenced mid-way — names EVERY node of its base: an edge too many only prices a
    row on the shipped blob, where an edge too few would price it on the C twin."""
    named = set()
    for address, name, offset in _LISTED_REFERENCE.findall(line):
        start = int(address, 16) - int(offset or "0", 16) if address else None
        node = nodes.get((start, name))
        named |= {node} if node else nodes_of_base.get(_unsplit(name), {_unsplit(name)})
    named |= {nodes.get((value, starts[value]), _unsplit(starts[value]))
              for value in map(int, _LISTED_IMMEDIATE.findall(line)) if value in starts}
    return named


def graph_of_listing(listing, ends, starts, origins=None):
    """`call_graph`'s reading of one `objdump -d` listing, given the symbol table's `{address: end}` sizes,
    `{address: name}` starts and `symbol_origins` — apart from the ELF so a synthetic listing can pin each rule."""
    labels = [(int(match.group(1), 16), match.group(2))
              for match in map(LISTED_FUNCTION.match, listing.splitlines()) if match]
    nodes = nodes_of_labels(labels, origins)
    nodes_of_base = {}
    for (_address, name), node in nodes.items():
        nodes_of_base.setdefault(_unsplit(name), set()).add(node)
    graph, function, end = {}, None, None
    for line in listing.splitlines():
        start = LISTED_FUNCTION.match(line)
        if start:
            address = int(start.group(1), 16)
            function, end = nodes[(address, start.group(2))], ends.get(address)
            graph.setdefault(function, set())
            continue
        instruction = _LISTED_INSTRUCTION.match(line)
        if function and instruction and (end is None or int(instruction.group(1), 16) < end):
            graph[function] |= _references(line, starts, nodes, nodes_of_base) - {function}
    return graph


def qualified_bases(graph):
    """The base names the graph QUALIFIED — each names more than one function, so a lookup by it is ambiguous."""
    return {node.split("@")[0] for node in graph if "@" in node}


def callers_of_transcribed_cores(graph):
    """The `(caller, core)` references to a transcribed C core from a function outside the table."""
    return {(function, target) for function, targets in graph.items() if function not in TRANSCRIBED_CORES
            for target in targets if target in TRANSCRIBED_CORES}


def reaching_transcribed_cores(graph):
    """Every function outside the table from which a transcribed C core is reachable: its direct callers
    and whatever calls them — the C whose cost, as shipped, includes a `.S`."""
    direct = {function for function, _core in callers_of_transcribed_cores(graph)}
    return callers_closure(graph, direct, excluded=TRANSCRIBED_CORES)


def callers_closure(graph, seeds, excluded=frozenset()):
    """`seeds` and every function outside `excluded` from which one of them is reachable over `graph`."""
    reaching = set(seeds)
    grown = True
    while grown:
        more = {function for function, targets in graph.items()
                if function not in excluded and function not in reaching and targets & reaching}
        reaching |= more
        grown = bool(more)
    return reaching

