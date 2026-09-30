"""What the ENTRY batteries share (`src/vdi/entry.c`, `src/vdi/entry.S`): the Line-A exception, the VDI's `trap #2`
entry and its dispatcher — each a door into a routine a TABLE names.

THE CALL OUT. The dispatcher `jsr`s the function its opcode tables name, and the Line-A exception the primitive
its own table names. On the oracle's side that is the ROM's code, run where it lies; on the candidate's the C
leaves through `staged_call.h`'s hooks (the bare shape for the dispatcher, `isr.staged_routines`; the register-
carrying one for the Line-A door, `isr.REGISTERS_HOOK`), which a case binds BY ADDRESS to the reconstruction of
what is there — `function()` / `primitive()` — or to nothing at all, so a call the ROM does not make is refused.
Most cases dispatch into the ROM's own `rts` the four unused opcodes share (`VDI_ROM_NOP`), which isolates the
door; a few go end to end into real functions, whose C runs inside the dispatcher's.

THE DISPATCHER'S STORES ARE STALE FIRST (`stale_dispatch`): contrl[2]/[4], VDI_RESULT, LINEA_CUR_WORK and every
copy's destination hold a value no workstation field does, so a store skipped or aimed wrong is a changed word.

THE LINE-A DOOR HAS TWO ENTRIES HERE. A DIRECT one, for its C twin: a trampoline puts SP on an exception frame
STAGED IN THIS BAND — so the stepped PC the handler writes back is compared image — and jumps to the handler; the
`rte` resumes past a staged $Axxx word at an `rts`, which returns through the sentinel laid above the frame. The
handler's own pushes land below the frame, which the case drops (`LINEA_STACK_WINDOW`: the ROM's frames, which the
C twin does not have). And a STAGED CALLER for the `.S`, one per opcode (`exception_caller`), which builds the
frame a real $Axxx exception would on the run's own stack and enters through `abi.FIRST_ARG`.
"""
import ctypes
import struct

from harness import _lib, addrs, emu, make_image

import abi
import case
import isr
import vdi
from case import merge_pokes
from opcodes import CLEAR_REGISTER, PUSH_RETURN_PC, PUSH_SR, PUSH_STACK_LONG, RTE, RTS

WORD = struct.Struct(">H")
LONG = struct.Struct(">I")

# ---- the band ---------------------------------------------------------------------------------------------------
BAND_OFFSET = 0x1400
BAND_BYTES = 0x400
BAND_AT = vdi.SPAN.band(BAND_OFFSET, BAND_BYTES, "test/vdi_entry.py: the Line-A frame and callers, a moved contrl")
TRAMPOLINE_AT = BAND_AT                         # `movea.l #frame,sp / jmp $fc9f0c`
OPCODE_WORD_AT = BAND_AT + 0x10                 # the $Axxx word, then the `rts` the handler resumes at
EXCEPTION_CALLERS_AT = BAND_AT + 0x20           # `exception_caller`'s, one per (opcode, cleared registers)
EXCEPTION_CALLER_STRIDE = 0x18
JSR_CALLERS_AT = BAND_AT + 0xE0                 # ...then a `vdi.CallerPool` of code-pointer callers entered by `jsr`
EXCEPTION_CALLERS_END = JSR_CALLERS_AT
JSR_CALLERS_END = BAND_AT + 0x100
MOVED_CONTRL_AT = BAND_AT + 0x100               # a contrl array a case places away from `vdi.CONTRL_AT`
LINEA_STACK_AT = BAND_AT + 0x200                # the handler's pushes, under the frame
FRAME_AT = BAND_AT + 0x3F0                      # the exception frame the trampoline points SP at
SENTINEL_AT = FRAME_AT + addrs.EXCEPTION_FRAME_BYTES     # ...and the return the resumed `rts` takes
assert SENTINEL_AT + LONG.size <= BAND_AT + BAND_BYTES
LINEA_STACK_WINDOW = ((LINEA_STACK_AT, FRAME_AT,
                       "the Line-A handler's own stack: its `movem`, the `jsr` and the primitive's frames, which the C "
                       "twin — calling out through a hook — does not have"),)
SUPERVISOR_SR = 0x2700                          # the SR the frame hands `rte`: supervisor, so SP stays this stack

# ---- the dispatcher's stores, stale ------------------------------------------------------------------------------
_STALE_OF_WIDTH = {vdi.WORD_BYTES: vdi.STALE_WORD, vdi.LONG_BYTES: vdi.STALE_LONG}


def stale_dispatch():
    """Every word the dispatcher stores for a workstation (`vdi.DISPATCH_STEPS`), and VDI_RESULT, holding a value no
    field does."""
    stores = {step.destination: _STALE_OF_WIDTH[step.width].to_bytes(step.width, "big") for step in vdi.DISPATCH_STEPS}
    return merge_pokes(stores, {vdi.VDI_RESULT: WORD.pack(vdi.STALE_WORD)})


def contrl_words(opcode, handle, points=0):
    """contrl[0..6] as a CALLER hands them: the two counts the dispatcher clears stale."""
    return vdi.pack_words(opcode, points, vdi.STALE_WORD, 0, vdi.STALE_WORD, 0, handle)


def dispatch_pokes(opcode, handle=vdi.VDI_PHYS_HANDLE, machine=None, *, contrl_at=vdi.CONTRL_AT):
    """A call of `opcode` on `handle` over `machine`, entered at the dispatcher: the call's contrl at `contrl_at`
    (LINEA_CONTRL names it), the other pointers at `vdi`'s arrays, and every store the dispatcher makes stale."""
    return merge_pokes(machine, stale_dispatch(), vdi.pointer_pokes(), vdi.linea_pokes(CONTRL=contrl_at),
                       {contrl_at: contrl_words(opcode, handle)})


def over_a_call(staged):
    """A `vdi.call_pokes` staging (the machine AS THE DISPATCHER LEAVES IT) taken back to the machine it is CALLED
    over: the copies, CUR_WORK and VDI_RESULT stale again and contrl[2]/[4] stale — the dispatcher makes them."""
    return merge_pokes(staged, stale_dispatch(),
                       {vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT: WORD.pack(vdi.STALE_WORD),
                        vdi.CONTRL_AT + vdi.CONTRL_N_INTOUT: WORD.pack(vdi.STALE_WORD)})


# ---- what a dispatched call reaches, on the candidate's side -------------------------------------------------------
def _nothing(_buf, _argument):
    return None


NOP = {addrs.VDI_ROM_NOP: (b"", _nothing)}


def function(name):
    """`{address: routine}` for the VDI function `addrs.<name>`: its C core, run where the dispatcher's `jsr` lands."""
    core = getattr(_lib, vdi.core_symbol(name))
    core.restype = None
    return {getattr(addrs, name): (b"", lambda buf, _argument: core(buf))}


def called():
    """The calls the candidate made through the bare hook, as the routine addresses in order."""
    return [routine for routine, _argument in isr.CALLS]


def run_dispatch(pokes, routines=None, *, recording=None, **kwargs):
    """The dispatcher over `pokes`, the candidate's calls served by `routines` (none: any call is refused). Answers
    the `vdi.Result` and the routines the candidate called. `recording` wraps the glue in another door's pass (a
    function that takes a GEMDOS trap)."""
    core = _lib.vdi_dispatch
    core.restype = None
    glue = isr.recording(lambda _lib_, buf: core(buf))
    with isr.staged_routines(routines or {}):
        info = case.run(addrs.VDI_ROM_DISPATCH, {"_pokes": pokes}, vdi.recorded(glue, recording),
                        width=case.NO_RESULT, **kwargs)
        calls = called()
    return vdi.Result(info, pokes), calls


# ---- the `trap #2` entry ----------------------------------------------------------------------------------------
# D0 as `trap #2`'s VDI arm enters: the VDI's own selector ($fc4ec0 `cmp.w #$73,d0`). The entry writes only its low
# word, and the ROM's dispatch leaves the high one as it found it on the NOP's path — which is why a case enters
# with this: the C twin answers the WORD (`vdi/entry.h`), and a row compares D0.w (`bench/tier3.py`).
VDI_SELECTOR = 0x73
RESULT_BITS = 16
_lib.vdi_entry.restype = ctypes.c_uint16
_lib.vdi_entry.argtypes = [vdi.IMAGE_ARG, ctypes.c_uint32]


def block_pokes(at=vdi.PARAMETER_BLOCK_AT, *, contrl=vdi.CONTRL_AT, intin=vdi.INTIN_AT, ptsin=vdi.PTSIN_AT,
                intout=vdi.INTOUT_AT, ptsout=vdi.PTSOUT_AT):
    """The parameter block D1 names, at `at`: five longwords, any of which a case may point elsewhere."""
    data = LONG.pack(contrl) + LONG.pack(intin) + LONG.pack(ptsin) + LONG.pack(intout) + LONG.pack(ptsout)
    vdi.require_claimed(at, len(data))
    return {at: data}


def stale_entry():
    """What the entry stores, stale: the five Line-A pointers and the whole copy."""
    return merge_pokes(vdi.linea_pokes(**{name: vdi.STALE_LONG for name in vdi.POINTER_VARIABLES}),
                       {vdi.VDI_PTSIN_COPY: bytes([vdi.FILL]) * vdi.VDI_PTSIN_COPY_BYTES})


# The copy's room, which caps what the entry copies: 1024 words, 512 points.
CAP_WORDS = vdi.VDI_PTSIN_COPY_BYTES // vdi.WORD_BYTES
CAP_POINTS = vdi.VDI_PTSIN_COPY_BYTES // vdi.VDI_POINT_BYTES
PAST_THE_CAP = CAP_POINTS + 1                   # the least count the cap cuts


def ramp(words, seed=0x1234):
    """`words` words no two alike — a caller's points, so a word copied from the wrong place is a wrong word."""
    return vdi.pack_words(*((seed + index * 0x0101) for index in range(words)))


def entry_pokes(opcode, points=0, *, handle=vdi.VDI_PHYS_HANDLE, source=vdi.PTSIN_AT, source_words=None,
                machine=None, block=None, contrl_at=vdi.CONTRL_AT):
    """A `trap #2` call of `opcode` with `points` in contrl[1], its caller's ptsin at `source` holding a ramp of
    `source_words` words (enough for the count, capped, by default), over `machine`."""
    if source_words is None:
        source_words = min(2 * points & 0xFFFF, CAP_WORDS) + 2
    staged = merge_pokes(machine, stale_dispatch(), stale_entry(),
                         block if block is not None else block_pokes(contrl=contrl_at, ptsin=source),
                         {contrl_at: contrl_words(opcode, handle, points)})
    if source_words:
        if source != vdi.SCREEN.base:
            vdi.require_claimed(source, source_words * vdi.WORD_BYTES)
        staged = merge_pokes(staged, {source: ramp(source_words)})
    return staged


def run_entry(pokes, routines=None, *, d1=vdi.PARAMETER_BLOCK_AT, recording=None, **kwargs):
    """The `trap #2` entry with D1 = `d1` over `pokes`, answering D0.w; `routines` as `run_dispatch`'s."""
    glue = isr.recording(lambda _lib_, buf: _lib.vdi_entry(buf, d1))
    with isr.staged_routines(routines or {}):
        info = case.run(addrs.VDI_ROM_ENTRY, {"d0": VDI_SELECTOR, "d1": d1, "_pokes": pokes},
                        vdi.recorded(glue, recording), width=RESULT_BITS, **kwargs)
        calls = called()
    return vdi.Result(info, pokes), calls


# ---- the Line-A door, entered DIRECTLY: a staged frame, for the C twin ------------------------------------------------
def direct_pokes(opcode_word, pokes=None):
    """The trampoline, the frame (SR, the $Axxx word's address) and the sentinel above it, and the word itself
    with the `rts` the handler resumes at."""
    frame = WORD.pack(SUPERVISOR_SR) + LONG.pack(OPCODE_WORD_AT)
    return merge_pokes(pokes, {TRAMPOLINE_AT: isr.trampoline_bytes(FRAME_AT, addrs.LINEA_ROM_DISPATCH),
                               FRAME_AT: frame, SENTINEL_AT: LONG.pack(emu.SENTINEL),
                               OPCODE_WORD_AT: WORD.pack(opcode_word) + RTS})


# `registers` for the register-carrying hook, in `staged_call.h`'s order.
REGISTERS_ARRAY = ctypes.c_uint32 * len(isr.STAGED_REGISTERS)


def primitive(name):
    """`{address: effect}` for the Line-A primitive `addrs.<name>`, its C core called as the hook's effect: the
    registers its declaration answers in, of the three the hook carries, written back."""
    contract = vdi.PRIMITIVES[name]
    core = getattr(_lib, vdi.core_symbol(name))
    several = len(contract.results) > 1
    core.restype = ctypes.c_uint32 if "d0" in contract.results else None

    def effect(buf, registers):
        values = [registers[isr.STAGED_REGISTERS.index(register)] for register in contract.arguments]
        out = vdi.RESULTS_ARRAY()
        returned = core(buf, *values, out) if several else core(buf, *values)
        answered = dict(zip(contract.results, out)) if several else {"d0": returned} if "d0" in contract.results else {}
        for register, value in answered.items():
            if register in isr.STAGED_REGISTERS:
                registers[isr.STAGED_REGISTERS.index(register)] = value
    return {getattr(addrs, name): effect}


def answered(name):
    """The registers of the three the hook carries that the primitive `addrs.<name>` answers in — the ones its C core
    models, so the ones a case through it compares (the rest are the ROM routine's scratch)."""
    return tuple(register for register in isr.STAGED_REGISTERS if register in vdi.PRIMITIVES[name].results)


def run_direct(opcode_word, registers=None, pokes=None, effects=None, compared=isr.STAGED_REGISTERS, **kwargs):
    """The Line-A exception's C twin against `$fc9f0c` entered at the trampoline, the frame in this band; `effects`
    serve the primitives the candidate calls (none: any call is refused). The `compared` registers of D0/D1/A0 —
    all three by default, which is what an opcode that calls nothing leaves — are held to the hook's hand-back;
    `vdi.Result.info["regs"]` has the ROM's whole file."""
    registers = {**vdi.DIRTY, **(registers or {})}
    staged = direct_pokes(opcode_word, pokes)
    handed = []
    core = _lib.linea_dispatch
    core.restype = None

    def glue(_lib_, buf):
        file = REGISTERS_ARRAY(*(registers[name] for name in isr.STAGED_REGISTERS))
        core(buf, FRAME_AT, file)
        handed.append(list(file))
    with isr.REGISTERS_HOOK.staged(effects or {}, _refused):
        info = case.run(TRAMPOLINE_AT, {**registers, "_pokes": staged}, isr.REGISTERS_HOOK.recording(glue),
                        width=case.NO_RESULT, dropped_windows=LINEA_STACK_WINDOW, **kwargs)
        calls = [routine for routine, *_rest in isr.REGISTERS_HOOK.calls]
    ours = {name: handed[0][isr.STAGED_REGISTERS.index(name)] for name in compared}
    theirs = {name: info["regs"][name] for name in compared}
    assert ours == theirs, f"the C twin handed back {ours} where the ROM left {theirs}"
    return vdi.Result(info, staged), calls


def _refused(refused):
    return f"the Line-A C twin called {[hex(routine) for routine in refused]}, which this case staged no effect for"


# ---- the Line-A door through a staged EXCEPTION CALLER, for the `.S` -------------------------------------------------
# What a real $Axxx does, built by a caller both sides share: the frame (the PC of an $Axxx word inside the caller,
# then the SR on top), then the handler entered through the longword at `abi.FIRST_ARG` — the ROM's or the blob's —
# and back at the `rts` after the word, which returns through the run's own sentinel. Registers a transcription
# measurably leaves holding an address of ITS OWN region (an $a000 answer) are cleared on the way out, on both sides:
#
#     pea word(pc) / move.w sr,-(sp) / move.l ROUTINE(sp),-(sp) / rts / word: dc.w $A00n / clears / rts
_ROUTINE_SLOT = abi.FIRST_ARG - emu.STACK_TOP + LONG.size + WORD.size     # past the pushed PC and SR
_TO_WORD = len(PUSH_SR) + len(PUSH_STACK_LONG) + WORD.size + len(RTS) + WORD.size    # from the `pea`'s extension
# The caller's own cost, as the stand-in `routine` below lets `vdi.assert_caller_cost` measure it: the four
# instructions in and the `rts` out, and one `suba.l` per cleared register.
EXCEPTION_CALLER_COST = (5, 86)
# The stand-in the cost is measured over — the handler's own shape at its smallest: step the stacked PC past the
# word and return through it (`addq.l #2,2(sp) / rte`).
STEP_PAST_THE_WORD = b"\x54\xaf" + WORD.pack(addrs.EXCEPTION_FRAME_PC) + RTE
STEP_PAST_THE_WORD_COST = (2, 44)
EXCEPTION_CALLERS = vdi.CallerPool(EXCEPTION_CALLERS_AT, EXCEPTION_CALLERS_END, EXCEPTION_CALLER_STRIDE)


def exception_stub(opcode_word, cleared):
    """The bytes of the caller that enters the handler as the $Axxx `opcode_word` does, clearing `cleared` after, and
    the cost it declares."""
    stub = (PUSH_RETURN_PC + WORD.pack(_TO_WORD) + PUSH_SR + PUSH_STACK_LONG + WORD.pack(_ROUTINE_SLOT) + RTS
            + WORD.pack(opcode_word) + b"".join(CLEAR_REGISTER[register] for register in cleared) + RTS)
    cost = tuple(base + len(cleared) * each for base, each in zip(EXCEPTION_CALLER_COST, vdi.CLEAR_COST))
    return stub, cost


def exception_caller(opcode_word, cleared=()):
    """The staged caller that enters the handler as the $Axxx `opcode_word` does, clearing `cleared` after — built on
    first ask in EXCEPTION_CALLERS and registered, so its cost is measured over the handler's stand-in."""
    return EXCEPTION_CALLERS.staged((opcode_word, tuple(cleared)), lambda: exception_stub(opcode_word, cleared),
                                    routine=STEP_PAST_THE_WORD, routine_cost=STEP_PAST_THE_WORD_COST)


# ---- a record laid over what the dispatcher STORES: the order of its copies, made visible -------------------------
# No open makes such a record; it is staged because the copies commute over every record GEMDOS hands out, so their
# ORDER — which field is read after which store — shows only where a later-read field IS an earlier destination. A
# model of the ROM's sequence ($fcaa40..$fcab14, `vdi.DISPATCH_STEPS` folded by `simulate`) picks the
# placements that tell every adjacent pair of steps apart, and steers the one pointer the copies then FOLLOW — the
# font the monospace flag is read from — to the staged font, through whichever staged words it is made of.


def simulate(memory, at, steps=vdi.DISPATCH_STEPS):
    """`steps` (`vdi.DISPATCH_STEPS`, or an order of them) folded over a copy of `memory` (a dict of the bytes that
    matter) for the record at `at`. Answers the memory after, and each byte's ORIGIN — the address its value was first
    staged at, or None for a computed one."""
    memory = dict(memory)
    origin = {address: address for address in memory}
    for step, _value, offset in vdi.dispatch_stores(memory, at, steps):
        sources = [None if offset is None else origin.get(at + offset + index) for index in range(step.width)]
        origin.update((step.destination + index, source) for index, source in enumerate(sources))
    return memory, origin


OVERLAY_HANDLE = 7


def modelled(image, at):
    """The bytes the model reads and writes for a record at `at`: from the lowest of the record and the destinations
    to the record's end or the Line-A block's, and the staged font's header."""
    spans = (range(min(at, vdi.VDI_TEXT_H_ALIGN), max(at + vdi.WS_BYTES, vdi.LINEA_BLOCK_END)),
             range(vdi.FONT_AT, vdi.FONT_AT + vdi.FONT_HEADER_BYTES))
    return {address: image[address] for span in spans for address in span}


OVERLAY_LO, OVERLAY_HI = 0x1640, 0x2A10          # records reaching a destination, clear of the capture MASK below


def overlay_pokes(at, user_interior=False):
    """The machine for a record at `at` laid over the dispatcher's destinations — a ramp, OVERLAY_HANDLE, linked from
    the physical record, the user interior if asked (so MULTIFILL is a COPY) — dispatched a NOP; or None where the
    font pointer cannot be steered to a staged font."""
    record = {at: ramp(vdi.WS_BYTES // vdi.WORD_BYTES, seed=0x0311)}
    link = vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, NEXT=at)
    interior = vdi.field_pokes("WS", at, FILL_STYLE=vdi.VDI_INTERIOR_USER) if user_interior else {}
    fixed = merge_pokes(interior, vdi.field_pokes("WS", at, HANDLE=OVERLAY_HANDLE),
                        vdi.font_pokes(FLAGS=vdi.FONT_FLAG_MONOSPACE_MASK))
    # The record's ramp over the stale destinations: a copy that lands where it reads is a changed word both ways.
    # ...and LINEA_CONTRL over the ramp in turn, for the records that reach it: the call must still be the NOP's.
    pokes = merge_pokes(dispatch_pokes(addrs.VDI_ROM_NOP_OPCODE, OVERLAY_HANDLE), record, link, fixed,
                        vdi.linea_pokes(CONTRL=vdi.CONTRL_AT))
    held = ((vdi.LINEA_CONTRL, vdi.LONG_BYTES), (at + vdi.WS_HANDLE, vdi.WORD_BYTES),
            (at + vdi.field("WS", "FILL_STYLE").at, vdi.WORD_BYTES))
    protected = {address for start, size in held for address in range(start, start + size)}
    image = make_image(pokes)
    memory = modelled(image, at)
    font_at = vdi.field("WS", "CUR_FONT").at
    steps = vdi.DISPATCH_STEPS
    before_font = steps[:next(i for i, step in enumerate(steps) if step.destination == vdi.LINEA_CUR_FONT)]
    _after, origin = simulate(memory, at, before_font)
    origins = [origin.get(at + font_at + i) for i in range(vdi.LONG_BYTES)]
    if None in origins or protected & set(origins):
        return None
    steered = merge_pokes(pokes, {address: bytes([byte]) for address, byte in zip(origins, vdi.FONT_AT.to_bytes(4, "big"))})
    image = make_image(steered)
    memory = modelled(image, at)
    try:
        final, _origin = simulate(memory, at, steps)
    except KeyError:                    # a font pointer off the modelled span: not steered after all
        return None
    interior = vdi.memory_value(image, at + vdi.field("WS", "FILL_STYLE").at, vdi.WORD_BYTES)
    interior_kept = interior == vdi.VDI_INTERIOR_USER or not user_interior
    if vdi.memory_value(final, vdi.LINEA_CUR_FONT, vdi.LONG_BYTES) != vdi.FONT_AT \
            or vdi.memory_value(image, at + vdi.WS_HANDLE, vdi.WORD_BYTES) != OVERLAY_HANDLE or not interior_kept:
        return None
    return steered


def swapped(steps, index):
    """`steps` with the step at `index` and the one after it exchanged."""
    return steps[:index] + [steps[index + 1], steps[index]] + steps[index + 2:]


def tells_apart(at, memory, in_order, index):
    """Whether the record at `at` over `memory` (`modelled`), which the ROM's order leaves `in_order`, ends differently
    with steps `index` and `index + 1` exchanged."""
    try:
        other = simulate(memory, at, swapped(list(vdi.DISPATCH_STEPS), index))[0]
    except KeyError:                    # the exchanged order follows a font pointer off the modelled span
        return True
    return in_order != other


def pairs_told_apart(at, user_interior):
    """The adjacent pairs of steps (by the first's index) a record at `at` tells apart — none where it cannot be
    staged. The machine and its in-order fold are built once, for every pair."""
    pokes = overlay_pokes(at, user_interior)
    if pokes is None:
        return set()
    memory = modelled(make_image(pokes), at)
    in_order = simulate(memory, at)[0]
    return {index for index in range(len(vdi.DISPATCH_STEPS) - 1) if tells_apart(at, memory, in_order, index)}


def search_order_placements():
    """THE SEARCH the placements `test_vdi_entry.py` stages were found by — every even address in the range, both
    interiors, under a minute, so it is run on request (`test_the_placements_are_what_the_search_finds`, RUN_SLOW=1): `({(record address, user interior):
    pairs}, [pairs none tells apart])`,
    a few placements that between them tell every adjacent pair of steps apart, chosen greedily."""
    candidates = {(at, user): pairs_told_apart(at, user) for at in range(OVERLAY_LO, OVERLAY_HI, vdi.WORD_BYTES)
                  for user in (False, True)}
    wanted = set(range(len(vdi.DISPATCH_STEPS) - 1))
    covered, chosen = set(), {}
    while True:
        at, pairs = max(candidates.items(), key=lambda item: len(item[1] - covered))
        if not pairs - covered:
            break
        chosen[at] = pairs
        covered |= pairs
    return chosen, sorted(wanted - covered)
