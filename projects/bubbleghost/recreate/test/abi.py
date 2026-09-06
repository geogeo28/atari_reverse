"""Calling Bubble Ghost's routines under the oracle, in memory the differential can see.

THIS PROGRAM IS COMPILED C, NOT HAND-WRITTEN ASSEMBLY, and that decides the shape of everything
here. Alcyon/DRI C passes arguments ON THE STACK — every function opens `link a6,#-n` and reads its
arguments at `8(a6)`, `10(a6)`, … — and reaches every global through `a4`. So the two things a case
needs are a way to put arguments where the callee will look for them (`stack_args` below) and the
`a4` every run must carry (`A4_BASE`, from `include/globals.h` and mirrored by
`test/test_image_model.py`) — which is `run_with_a4`, the one spelling of a differential in this
project.

FOUR ROUTINES DO TAKE THEIR ARGUMENTS IN REGISTERS and are ported: the two OS trampolines @
0x15e3c/0x15e58 (entered through the wrappers that call them, so their inputs are the caller's a1/a2
in `regs`), the Timer C ISR @ 0x1459a (entered directly, its state read out of the image) and the
`trap #9` PSG gate @ 0x14950 (three argument WORDS on the stack, no `link`). None of them needed a
stub shape of its own: what did is a routine that answers on its caller's stack (`c_call_pokes`) and
one that must be driven many times inside one run (`call_n_times_stub`).

THE FILE IS APPEND-ONLY while several agents hold it at once (see README.md, "Adding a function"):
a new stub shape is a new function, never an edit to an existing one.
"""
import struct

import harness
import emu
from recreate_kit.stubs import seed_spans   # noqa: F401  (re-exported: `abi.seed_spans(...)`)

# The value of a4 in every function of this program — the BSS/DATA boundary the crt0 establishes.
# EVERY case passes it (`regs={"a4": abi.A4_BASE}`): a run without it reads the game's globals from
# address `n`, which is the 68000 vector page. It lives here rather than being spelt per battery,
# and `test_image_model.py` pins it equal to `include/globals.h`'s A4_BASE and to both .PRG headers.
A4_BASE = 0x24f1a

# ---- the scratch map ---------------------------------------------------------------------------
# Free image space is [BG_PROGRAM_END, OS_FS_TABLE) = [0x2520e, 0xbf000): unlike Zynaps, this game
# hard-codes no framebuffer — it asks XBIOS for one (`video_init` @ 0x10118 takes Logbase and its
# back buffer 0x7d00 below it), which the model answers with OS_SCREEN_BASE, well below load_base.
#
# THE MAP IS PARKED HIGH ON PURPOSE. The low half of that window is where the model's Malloc arena
# lives (`heap_base = 0x30000`, project.toml), and this game asks for ~245 KiB of it. STUB is
# therefore also the arena's CEILING: project.toml sets `heap_limit = 0x90000` so that a run which
# allocated up to here is refused rather than quietly handing out the address this file's stubs are
# poked at.
STUB = 0x90000        # where the oracle enters, for a case that needs a poked 68000 stub
RESULT = 0x90100      # where such a stub stores results the image diff could not otherwise see
SCRATCH = 0x91000     # a test's own source/destination buffers
SCRATCH_BYTES = 0x20000   # the largest span a case may build from SCRATCH; pinned below OS_FS_TABLE
                          # by test_image_model.py

# ---- the C calling convention -------------------------------------------------------------------
# `emu.run` forces A7 to emu.STACK_TOP and writes the sentinel return address there, which is
# exactly the frame a `jsr` leaves: the callee's first argument is at 4(A7), the next at 8(A7), and
# `link a6,#-n` then turns those into 8(a6), 12(a6)… So an argument list is a poke at STACK_TOP + 4.
FIRST_ARG = emu.STACK_TOP + 4

ARGUMENT_WIDTHS = (2, 4)          # an Alcyon C argument is a `short` or a `long`/pointer


def _immediate(width, value):
    """`value` as the unsigned `width`-byte immediate the compiler would have pushed.

    A value may be SIGNED: `-1` as a word is the two's-complement `0xffff`. The bound is the width's
    signed-OR-unsigned range, so a value that fits neither is refused by name here rather than
    raising a bare `OverflowError` out of `to_bytes` — which says nothing about which argument of
    which call was out of range.
    """
    assert width in ARGUMENT_WIDTHS, (
        f"an Alcyon C argument is a word or a longword, not {width} bytes")
    bits = 8 * width
    assert -(1 << (bits - 1)) <= value < (1 << bits), (
        f"{value} fits neither a signed nor an unsigned {width}-byte argument "
        f"[{-(1 << (bits - 1))}, {(1 << bits) - 1}]")
    return value & ((1 << bits) - 1)


def stack_args(*args):
    """Pokes placing `args` where an Alcyon/DRI C routine reads them: 4(A7) upward.

    Each argument is `(width_in_bytes, value)` — the compiler pushes a `short` as one word and a
    `long`/pointer as two, and the callee's offsets are built from the widths the CALLER used, so
    the width is required rather than guessed from the value's size.

        differential(entry, regs={"a4": abi.A4_BASE,
                                  "_pokes": abi.stack_args((2, screen), (4, buffer))}, glue)

    POKES TRAVEL IN `regs["_pokes"]`. `harness.differential` has no `pokes=` parameter — it pops
    that key out of `regs` and hands the rest to the oracle as input registers — and a call written
    with one fails on the spot, so this is a spelling to copy rather than a hazard.

    A value may be SIGNED, and out-of-range values are refused by name — see `_immediate`.

    The bytes land inside the stack-guard band the differential already drops, so they are inputs
    only: nothing here is compared, and the candidate's glue is handed the same values as C
    arguments by the case that wrote them.
    """
    pokes, offset = {}, FIRST_ARG
    for width, value in args:
        pokes[offset] = _immediate(width, value).to_bytes(width, "big")
        offset += width
    return pokes


# ---- big-endian encoders ------------------------------------------------------------------------
# One spelling per width, because a poke dict is bytes and every battery was building them: three
# copies of `value.to_bytes(4, "big")` under three names (`_long`, `long`, `struct.pack`) is three
# places for one of them to forget the mask on a negative value.


def word(value):
    """A 68000 word, big-endian. Negatives wrap, as `move.w #-1` does."""
    return (value & 0xffff).to_bytes(2, "big")


def long(value):
    """...and a longword."""
    return (value & 0xffffffff).to_bytes(4, "big")


def double(value):
    """An IEEE double, big-endian — the eight bytes the fp package reads and writes."""
    return struct.pack(">d", value)


# ---- ...and the big-endian DECODERS, for a case that reads a result back out of a finished image.
# Here beside the encoders for their reason: three batteries had grown a private `_long`/`_word`/
# `_word_in`, and the third of them read its word SIGNED under a name that did not say so.


def read_word(image, address, signed=False):
    """One big-endian word out of a run's image. `signed` reads it as the 68000's `move.w` + `ext.l`
    would — a game word is as often -1 as 0xffff, and a case that means one must say which."""
    return int.from_bytes(bytes(image[address:address + 2]), "big", signed=signed)


def read_long(image, address, signed=False):
    """...and one big-endian longword."""
    return int.from_bytes(bytes(image[address:address + 4]), "big", signed=signed)


# ---- combining pokes -----------------------------------------------------------------------------
def merge_pokes(*dicts, allow_overlap=False):
    """One poke dict from several, REFUSING an overlap unless the caller says it means one.

    `harness.make_image` applies a poke dict in insertion order and a later poke silently wins, so
    two pokes covering one byte read as "both regions were staged" when only one was — the trap
    `recreate_kit.stubs.seed_spans` documents. That silence is the default this refuses.

    `allow_overlap=True` is the deliberate case: a battery that seeds a whole span with noise and
    then writes the real contents of part of it is relying on the later poke winning, and says so at
    the site. It is a property of the CALL, not of the dicts, which is why it is a keyword here and
    not a second function.
    """
    merged, covered = {}, {}
    for source in dicts:
        for address, data in source.items():
            if not allow_overlap:
                for byte in range(len(data)):
                    assert address + byte not in covered, (
                        f"two pokes cover {address + byte:#x}; the later one would silently win — "
                        f"pass allow_overlap=True (and say which bytes win) if that is meant")
                    covered[address + byte] = True
            merged[address] = data
    return merged


# ---- running one differential ---------------------------------------------------------------------
def run_with_a4(entry, glue, pokes=None, regs=None, **kwargs):
    """One `harness.differential`, entered with the `a4` every function of this program carries.

    A run without it reads the game's globals from address `n`, which is the 68000 vector page — so
    every case passes it and none should have to remember to. `pokes` travels in `regs["_pokes"]`
    (see `stack_args`); everything else — `poison`, `psg_seed`, `stop_pc`, `max_insns` — is handed
    to the differential unchanged.

    THE MODELED MALLOC ARENA NEEDS NOTHING HERE: `src/clib.c`'s wrappers allocate through the kit's
    own `os_malloc`, and `harness.arm_candidate` rewinds that bump pointer before EVERY candidate run
    — the attribution pass's re-run included — exactly where `osh_run` rewinds the oracle's. This
    helper used to reset a private mirror of the arena that lived in clib.c; both are gone.
    """
    entry_regs = {"a4": A4_BASE}
    entry_regs.update(regs or {})
    entry_regs["_pokes"] = dict(pokes or {})
    return harness.differential(entry, entry_regs, glue, **kwargs)


def shard(cases, chunk, chunks):
    """The slice of `cases` this `chunk` owns — a PARTITION, so the shards together are the list.

    The two shard shapes in this project are worth telling apart, because they answer different
    questions and only one of them is this:

      * CHUNK-PARTITIONED (here): one list, built once from a fixed seed, split N ways. Every case
        runs exactly once per suite run and `-n auto` spreads them. Use it when the list IS the
        coverage — the 47 shipped sound definitions, a fixed fuzz corpus.
      * CHUNK-SEEDED: each chunk seeds its OWN generator (`random.Random(base + chunk)`) and draws
        its own cases, so the suite runs N times as many as one chunk does and no chunk repeats
        another's. Use it when more samples are simply better. It needs no helper — the shard is
        the seed — and a docstring for one must not claim every chunk walks the same list.
    """
    return list(cases)[chunk::chunks]


# ---- seeding ------------------------------------------------------------------------------------
# The default noise margin either side of a seeded span. IT IS NOT TIDINESS: most of what these
# routines write is bss, which the loaded image already holds as zeroes, so a candidate clearing or
# copying sixteen bytes too far would write zeroes over zeroes and the diff would stay empty. The
# margin is what turns "wrote past the end" into a difference.
GUARD_BYTES = 16


# `seed_spans` is the kit's (tools/recreate_kit/stubs.py), imported at the top and re-exported under
# this module's name so every battery keeps writing `abi.seed_spans(...)`. It used to be a verbatim
# copy of Zynaps' — which is how the merge step went missing from one of three copies there — and
# `tools/recreate_kit/test/test_stubs.py` is what now pins it.


# ---- staging the world a case runs in --------------------------------------------------------------
def stage_world(seed, spans, *layers):
    """Noise over `spans`, then each of `layers` written over it, later layers winning.

    THE ONE SHAPE EVERY BATTERY'S WORLD HAS, spelt once: seed the regions the routine writes into so
    that a store one word too far has something to differ against (`GUARD_BYTES` either side), then
    put the staging that must survive it on top — the pointers a routine reads its addresses out of,
    then the case's own content.

    The overlap is the point, which is why `allow_overlap=True` is here and not at each call site:
    `harness.make_image` applies a poke dict in insertion order, so the LAST layer covering a byte
    wins. A battery that does NOT mean an overlap calls `merge_pokes` directly and gets the refusal.

    WHAT EACH BATTERY STILL OWNS is its LAYERS, and they really are different worlds: `test_blit.py`
    stages two screen pointers and seven bank pointers, `test_frontend.py` two parameter blocks and
    an open workstation on top of those, `test_gameplay.py` one screen pointer. This helper is the
    seeding and the ordering, not the contents.
    """
    return merge_pokes(seed_spans(seed, spans, guard=GUARD_BYTES), *layers, allow_overlap=True)


# ---- calling a C routine from a poked 68000 stub -------------------------------------------------
# WHY A STUB AT ALL, when `stack_args` already puts arguments where a routine reads them. Two of the
# C library's routines answer through THEIR CALLER'S OWN ARGUMENT SLOTS rather than through D0 —
# `c_ldiv` @ 0x158fe writes the quotient over the divisor and the remainder over the dividend, and
# `c_lmul` @ 0x15970 writes the product over its second argument and then shifts its return address
# up over the first — and those slots lie above `emu.STACK_TOP`, inside the band the differential
# drops as stack. An oracle run entered at the routine itself therefore produces no evidence at all.
#
# So the oracle is entered at a stub instead: it pushes the arguments, calls, and files what the
# routine left on the stack into RESULT, which is ordinary image memory the byte diff compares. The
# same stub shape also serves a SEQUENCE of calls — random malloc/free traffic against one free list
# — where the interesting thing is the state the whole run leaves rather than any one answer.
#
# The encodings, each an opcode word and then its extension, all from the 68000 PRM:
_PUSH_LONG_IMMEDIATE = 0x2f3c   # move.l #imm32,-(a7)
_PUSH_WORD_IMMEDIATE = 0x3f3c   # move.w #imm16,-(a7)
_PUSH_LONG_ABSOLUTE = 0x2f39    # move.l (addr).l,-(a7)   — re-push an answer filed earlier
_JSR_ABSOLUTE = 0x4eb9          # jsr (addr).l
_POP_LONG_TO_ABSOLUTE = 0x23df  # move.l (a7)+,(addr).l   — take one longword the callee left behind
_STORE_D0_TO_ABSOLUTE = 0x23c0  # move.l d0,(addr).l
_ADD_WORD_TO_A7 = 0xdefc        # adda.w #imm16,a7        — drop the arguments
_RTS = 0x4e75

RESULT_SLOT_BYTES = 4


def result_slot(index):
    """Where the nth answer a stub files ends up. Longword-wide, in the order the case names them."""
    return RESULT + index * RESULT_SLOT_BYTES


def _encode(opcode, *extensions):
    out = opcode.to_bytes(2, "big")
    for width, value in extensions:
        out += value.to_bytes(width, "big")
    return out


def c_call_pokes(calls):
    """Pokes placing a stub at STUB that makes each C call in turn and files its answers at RESULT.

    Each call is a dict:

        {"routine": 0x158fe,                       # what to jsr
         "args": [(4, 10), ("slot", 0)],           # (width, value) as stack_args takes them, or
                                                   #   ("slot", n) to re-push answer n as a longword
         "answers": [("stack", 0), ("stack", 1)],  # ("d0", n) files D0; ("stack", n) pops one
                                                   #   longword the callee left on the stack
         "pop": 0}                                 # bytes of argument to drop afterwards

    `pop` is explicit rather than derived from the argument widths because it is not always the same
    number: `c_lmul` consumes four of its own eight bytes before returning, so a stub that dropped
    what it pushed would unbalance the stack. State it per call and the arithmetic is visible.

    Arguments are pushed LAST FIRST, so the first one ends up at the lowest address — which is where
    `link a6,#…` then makes it 8(a6), exactly as `stack_args` lays it out for a direct entry.
    """
    code = b""
    for call in calls:
        for width, value in reversed(call["args"]):
            if width == "slot":
                code += _encode(_PUSH_LONG_ABSOLUTE, (4, result_slot(value)))
            elif width in (2, 4):
                opcode = _PUSH_WORD_IMMEDIATE if width == 2 else _PUSH_LONG_IMMEDIATE
                code += _encode(opcode, (width, _immediate(width, value)))
            else:
                raise AssertionError(f"an Alcyon C argument is a word or a longword, not {width}")
        code += _encode(_JSR_ABSOLUTE, (4, call["routine"]))
        for kind, slot in call.get("answers", ()):
            if kind == "stack":
                code += _encode(_POP_LONG_TO_ABSOLUTE, (4, result_slot(slot)))
            elif kind == "d0":
                code += _encode(_STORE_D0_TO_ABSOLUTE, (4, result_slot(slot)))
            else:
                raise AssertionError(f"an answer comes from the stack or from D0, not {kind!r}")
        if call["pop"]:
            code += _encode(_ADD_WORD_TO_A7, (2, call["pop"]))
    code += _RTS.to_bytes(2, "big")
    # ...and it must stay clear of the NOISE the case seeds AROUND the result slots, not merely of
    # the slots themselves: `noise_around` writes GUARD_BYTES below RESULT, so a stub 0xf0 bytes or
    # longer would be half-overwritten by the seed and the run would execute the noise.
    assert STUB + len(code) < RESULT - GUARD_BYTES, (
        f"the {len(code)}-byte stub at {STUB:#x} reaches the guard band below the RESULT slots "
        f"({RESULT - GUARD_BYTES:#x}); it would be overwritten by the noise a case seeds there")
    return {STUB: code}


# ---- driving one routine many times inside ONE oracle run ----------------------------------------
# WHY: some state only exists after several calls — a decay that runs into its sustain, an LFO that
# folds, a duration that counts down to key-off. Each `differential()` is one run, so "N ticks" has
# to be N calls the ORACLE makes, not N runs the case makes; the candidate side simply loops in C.
#
# The chain target is part of the shape rather than a caller's problem: `timer_c_sound_isr` does not
# `rte` — it ends by pushing TOS's saved `$114` vector and `rts`ing through it — so a run that calls
# it repeatedly needs somewhere for that chain to land, and a bare `rts` immediately after the loop
# is it. `CALL_N_TIMES_CHAIN` is where the case stages that vector.
_MOVE_W_IMMEDIATE_TO_D = 0x303c   # move.w #imm16,Dn — the register number goes in bits 9..11
_DBF = 0x51c8                     # dbf Dn,disp16 — the register number goes in bits 0..2
_DATA_REGISTER_FIELD = 9          # ...where a `move`'s destination register sits

# The loop's own bytes: `jsr (addr).l` then `dbf`. The `dbf`'s displacement is measured from the
# address of its EXTENSION word, i.e. two bytes past the opcode.
_CALL_N_TIMES_BODY_BYTES = 6 + 4
_DBF_DISPLACEMENT_ORIGIN = 2

CALL_N_TIMES_CHAIN = 0x10         # offset of the trailing `rts` inside the blob below


def call_n_times_stub(entry, times, counter_register=7):
    """68000 for `for (i = 0; i < times; i++) entry();`, plus a bare `rts` for a chained return.

        move.w  #times-1,Dn        ; Dn = the loop counter
    loop:
        jsr     entry
        dbf     Dn,loop
        rts                        ; back to the harness's sentinel
    chain:
        rts                        ; where a handler that returns THROUGH a vector lands

    `counter_register` defaults to D7 because the routine this drives saves and restores D0-D3/A0-A2
    and leaves D4-D7 alone; a case driving something else has to pick a register that routine does
    not write, and saying so at the call site is the point of the argument.

    The `dbf` displacement is COMPUTED from the encoded length rather than written down, so a fourth
    instruction added above the loop cannot leave a hand-copied `fff8` branching into the middle of
    the `jsr`'s address.
    """
    assert 1 <= times <= 0x8000, f"a `dbf` loop runs 1..0x8000 times, not {times}"
    assert 0 <= counter_register <= 7, f"D{counter_register} is not a data register"
    code = _encode(_MOVE_W_IMMEDIATE_TO_D | (counter_register << _DATA_REGISTER_FIELD),
                   (2, times - 1))
    body = _encode(_JSR_ABSOLUTE, (4, entry))
    displacement = -(_CALL_N_TIMES_BODY_BYTES - _DBF_DISPLACEMENT_ORIGIN) & 0xffff
    body += _encode(_DBF | counter_register, (2, displacement))
    assert len(body) == _CALL_N_TIMES_BODY_BYTES, (
        f"the loop body encoded to {len(body)} bytes, not the {_CALL_N_TIMES_BODY_BYTES} the "
        f"displacement above was computed from — the `dbf` would branch into an instruction")
    code += body + _RTS.to_bytes(2, "big") + _RTS.to_bytes(2, "big")
    assert code[CALL_N_TIMES_CHAIN:] == _RTS.to_bytes(2, "big"), (
        f"the chain `rts` is not at +{CALL_N_TIMES_CHAIN:#x} — a case staging the vector there "
        f"would send the handler's return into the middle of an instruction")
    assert STUB + len(code) < RESULT - GUARD_BYTES, (
        f"the {len(code)}-byte stub at {STUB:#x} reaches the guard band below the RESULT slots")
    return {STUB: code}
