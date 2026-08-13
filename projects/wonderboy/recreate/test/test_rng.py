"""Differential test for src/rng.c — the game's PRNG ($68c6) and the two draws over it ($e1f0, $e1c8).

THE REGISTERED FALSE GREEN IS RETIRED (batch 33), AND THE HISTORY MATTERS.
`rng_next`'s entropy term is `$ff8209 ^ $b39a` — the shifter's video-address counter (its low,
fastest byte) XOR the frame tick. Until batch 33 that address was merely OFF THE IMAGE: the oracle
answered a read past the image with zeros, the term collapsed to the frame tick alone ON BOTH SIDES,
and every case here was green about a generator with no randomness in it — a T3-DATA false green,
the shape ../PORTABILITY.md §4 names.

The kit's Phase 7 table MODELS the byte now (`OS_HW_SHIFTER_VCOUNT_LOW`). `src/rng.c` reads it
through `hw_read8`, the read lands on the ordered ledger both sides compare, an UNDECLARED read
refuses the differential, and every run below states what the counter held with `leaf.hw_declared()`.
`test_a_declared_video_counter_reaches_the_result` drives five different bytes against one seeded
state, so the term is observable at last — including AS AN OPERATOR, which the old degeneracy hid
(`0 ^ tick` is `0 + tick`, so a port that added here used to be green too).

WHAT THE HISTORY STILL TOUCHES. Any differential run, golden or capture artifact produced BEFORE
this commit embedded the zero-entropy generator; a stored expectation from then is a statement about
the fabrication and not about the machine. And a declared byte is still not a counter: the machine
changes these on its own, so the model calls the slot VOLATILE and allows ONE read per run —
`rng_next` reads it exactly once, which is why a per-run constant describes this routine faithfully.

What the cases pin, and did before:

  * the three counters' arithmetic, each seeded on both sides of its own wrap. They are cleared when
    they REACH their limit rather than modulo it, so a counter seeded ABOVE its limit runs on to
    $ffff and round — a case per counter says so, and that is the difference between this and
    `(n + 1) % limit`;
  * that the entropy term is the counter byte XOR WB_FRAME_TICK_B39A and nothing else. The XOR is
    swept over tick values whose bits reach the whole word, and the sum is compared as a WORD;
  * that d0's HIGH half is never written (`clr.w d0`, not `moveq #0,d0`) and comes back as the
    caller left it, and that d1 comes back holding the tick.
"""
import collections
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, addq_w_abs_l, branch, branch_w_to, bsr_w, clr_w_abs_l, clr_w_dn,
                  cmp_w_imm_dn, cmpi_w_abs_l, lea_abs_l, longword, lsl_w_imm_dn, merge_bands,
                  move_b_abs_l_dn, move_w_abs_l_dn, opcode, program_writes, s16, subq_w_dn, u16,
                  word)
from layout import wb

import emu      # noqa: E402  (harness puts the kit's oracle on sys.path)

# --- the globals, from the header both languages read ---------------------------------------------
COUNTER_A = wb("RNG_COUNTER_A")
COUNTER_B = wb("RNG_COUNTER_B")
COUNTER_C = wb("RNG_COUNTER_C")
COUNTER_LEN = wb("RNG_COUNTER_LEN")
LIMIT_A = wb("RNG_LIMIT_A")
LIMIT_B = wb("RNG_LIMIT_B")
LIMIT_C = wb("RNG_LIMIT_C")
VIDEO_COUNTER = leaf.VIDEO_COUNTER_LOW
FRAME_TICK = wb("FRAME_TICK_B39A")

STAGE_NUMBER = wb("STAGE_NUMBER")
KIND_TABLE = wb("STAGE_KIND_TABLE")
KIND_TABLE_ROWS = wb("STAGE_KIND_TABLE_ROWS")
KIND_ROW = wb("STAGE_KIND_ROW")
KIND_ROW_SHIFT = wb("STAGE_KIND_ROW_SHIFT")
KIND_DRAW_MASK = wb("STAGE_KIND_DRAW_MASK")
KIND_MASK = wb("STAGE_KIND_MASK")
KIND32_TABLE = wb("STAGE_KIND32_TABLE")
KIND32_TABLE_ROWS = wb("STAGE_KIND32_TABLE_ROWS")
KIND32_ROW = wb("STAGE_KIND32_ROW")
KIND32_ROW_SHIFT = wb("STAGE_KIND32_ROW_SHIFT")
KIND32_DRAW_MASK = wb("STAGE_KIND32_DRAW_MASK")
BCD_LIMIT = wb("STAGE_NUMBER_BCD_LIMIT")
BCD_CARRY = wb("STAGE_NUMBER_BCD_CARRY")
BUS_ADDR_MASK = wb("BUS_ADDR_MASK")

WORD_LEN = leaf.WORD_BYTES
WORD_MASK = leaf.WORD_MASK

# The counters, as one table: address, limit and a name — so every sweep below is per COUNTER rather
# than three copies of one case, and a counter that moved fails in one place.
COUNTERS = ((COUNTER_A, LIMIT_A, "a"), (COUNTER_B, LIMIT_B, "b"), (COUNTER_C, LIMIT_C, "c"))

# The bytes ../names.txt gives each routine, stated so an entry pin cannot pass on a body of any
# other length.
RNG_BODY_BYTES = 108        # $68c6..$6931, the three counter words immediately past it
KIND_BODY_BYTES = 50        # $e1f0..$e221
KIND32_BODY_BYTES = 40      # $e1c8..$e1ef — no tail of its own; it ends in the `bra.w` into $e1f0's

# The instruction caps, from the bodies. rng_next is three 4-instruction counter steps (one arm of
# each is skipped) plus the seven-instruction tail; the draw adds its own eight and the `bsr`.
# `leaf.RUNNER_SENTINEL_INSN` is the one instruction osh_run counts past the routine's own `rts`.
COUNTER_STEP_INSNS = 4
RNG_TAIL_INSNS = 8              # `clr.w / move.b / move.w / eor.w` + one `add.w` per counter + `rts`
KIND_BODY_INSNS = 13            # its own thirteen, of which the `bsr` is the generator's whole run
KIND32_BODY_INSNS = 14          # ...and the sibling's own ten plus the four it branches into
RNG_INSN_CAP = (COUNTER_STEP_INSNS * len(COUNTERS) + RNG_TAIL_INSNS
                + leaf.RUNNER_SENTINEL_INSN)
KIND_INSN_CAP = KIND_BODY_INSNS + RNG_INSN_CAP
KIND32_INSN_CAP = KIND32_BODY_INSNS + RNG_INSN_CAP


# --- the encodings the two entries are pinned against ----------------------------------------------
# Every one of these has ONE user in the suite; everything more than one battery spells comes from
# leaf.py above — including `cmp_w_imm_dn` and `addq_w_abs_l`, which this battery's arrival made the
# third and second user of and which moved there in the same change.
ADD_W_ABS_L_DN = 0xd079         # add.w <abs>.l,Dn
EOR_W_DN_DN = 0xb140            # eor.w Dn,Dn
ADD_L_DN_DN = 0xd080
MOVE_B_INDEXED_DN = 0x1030      # move.b 0(An,Dm.l),Dn
ANDI_L_DN = 0x0280              # andi.l #imm,Dn — the immediate is a LONGWORD in the stream
BNE_W, BLE_W, BRA_W = 0x6600, 0x6f00, 0x6000

D0, D1, D2 = 0, 1, 2
A2 = 2


def _andi_l_dn(reg, value):
    return opcode(ANDI_L_DN | reg) + longword(value)


def _counter_step(at, counter, limit):
    """`addq.w #1 / cmpi.w #N / bne / clr.w` — and the `bne` skips exactly the `clr.w`, which is
    what says the counter is cleared when it REACHES its limit rather than modulo it."""
    clear = clr_w_abs_l(counter)
    return leaf.assemble(at, [
        addq_w_abs_l(1, counter), cmpi_w_abs_l(limit, counter), branch(BNE_W, clear), clear,
    ])


def _rng_entry():
    base = leaf.entry_of("rng_next")
    steps = leaf.assemble(base, [lambda at, c=c, m=m: _counter_step(at, c, m)
                                 for c, m, _name in COUNTERS])
    tail = (clr_w_dn(D0) + move_b_abs_l_dn(D0, VIDEO_COUNTER) + move_w_abs_l_dn(D1, FRAME_TICK)
            + opcode(EOR_W_DN_DN | (D1 << 9) | D0)
            + b"".join(opcode(ADD_W_ABS_L_DN | (D0 << 9)) + longword(counter)
                       for counter, _limit, _name in COUNTERS)
            + RTS)
    return steps + tail


def _kind_head(base, table, row_shift, draw_mask):
    """The nine instructions BOTH draws are, and the three operands that are the whole difference
    between them. The `bsr.w` displacement comes out of ../names.txt's two addresses, so a pin aimed
    at anything but rng_next fails on the bytes."""
    carry = subq_w_dn(BCD_CARRY, D2)
    return leaf.assemble(base, [
        lea_abs_l(A2, table), move_w_abs_l_dn(D2, STAGE_NUMBER),
        cmp_w_imm_dn(D2, BCD_LIMIT), branch(BLE_W, carry), carry,
        subq_w_dn(1, D2), lsl_w_imm_dn(row_shift, D2),
        lambda at: bsr_w(at, leaf.entry_of("rng_next")),
        _andi_l_dn(D0, draw_mask),
    ])


# The tail the two draws share: `add.l d2,d0 / move.b 0(a2,d0.l),d0 / andi.l #$1f,d0 / rts` —
# 2 + 4 + 6 + 2, the last fourteen bytes of $e1f0's body and the whole of $e1c8's.
SHARED_TAIL_BYTES = 14
SHARED_TAIL = leaf.entry_of("stage_random_kind8") + KIND_BODY_BYTES - SHARED_TAIL_BYTES


def _kind_entry():
    """$e1f0: the shared head over the 8-wide table, and then the tail $e1c8 branches into."""
    base = leaf.entry_of("stage_random_kind8")
    return _kind_head(base, KIND_TABLE, KIND_ROW_SHIFT, KIND_DRAW_MASK) + leaf.assemble(
        SHARED_TAIL, [
            opcode(ADD_L_DN_DN | (D0 << 9) | D2),
            opcode(MOVE_B_INDEXED_DN | (D0 << 9) | A2) + word((D0 << 12) | 0x800),
            _andi_l_dn(D0, KIND_MASK),
            RTS,
        ])


def _kind32_entry():
    """$e1c8: the same head over the 32-wide table, and NO tail — a `bra.w` into $e1f0's."""
    base = leaf.entry_of("stage_random_kind32")
    head = _kind_head(base, KIND32_TABLE, KIND32_ROW_SHIFT, KIND32_DRAW_MASK)
    return head + branch_w_to(BRA_W, base + len(head), SHARED_TAIL)


ENTRY_BYTES = {"rng_next": _rng_entry(), "stage_random_kind8": _kind_entry(),
               "stage_random_kind32": _kind32_entry()}
RNG_ROUTINE_COUNT = 3

# --- the glue ---------------------------------------------------------------------------------------
_RNG = leaf.register_glue("rng_next", [ctypes.c_uint32], ctypes.c_uint32)
_KIND = leaf.register_glue("stage_random_kind8", [ctypes.c_uint32], ctypes.c_uint32)
_KIND32 = leaf.register_glue("stage_random_kind32", [ctypes.c_uint32], ctypes.c_uint32)

# --- the two draws, as the three operands that are the whole difference between them ---------------
# $e1f0 and $e1c8 are one routine over two tables, so they are one set of cases over two descriptors:
# a claim that held for only one of them would be a claim about an operand rather than about the
# routine. The per-case SEEDS differ (each table's own bytes decide which stage and draw make a
# reading observable) and live beside the test that chooses them, keyed by descriptor.
KindDraw = collections.namedtuple(
    "KindDraw", "short name table rows row row_shift draw_mask body_bytes insn_cap glue")

DRAW8 = KindDraw("kind8", "stage_random_kind8", KIND_TABLE, KIND_TABLE_ROWS, KIND_ROW,
                 KIND_ROW_SHIFT, KIND_DRAW_MASK, KIND_BODY_BYTES, KIND_INSN_CAP, _KIND)
DRAW32 = KindDraw("kind32", "stage_random_kind32", KIND32_TABLE, KIND32_TABLE_ROWS, KIND32_ROW,
                  KIND32_ROW_SHIFT, KIND32_DRAW_MASK, KIND32_BODY_BYTES, KIND32_INSN_CAP, _KIND32)
DRAWS = (DRAW8, DRAW32)
DRAW_IDS = [draw.short for draw in DRAWS]


# --- the model both runners compare against ---------------------------------------------------------
# The video byte is an INPUT the model is HANDED, not one it may drop: the case declares it, the same
# byte reaches the model, and the term is carried as a parameter rather than folded away — so the
# case that stops being true fails here rather than nowhere.
ENTROPY_DEFAULT = 0
# THE TERM IS DECLARED NOW (batch 33). $ff8209 is a modeled hardware byte, so every run below states
# what the counter held and the oracle serves that rather than a fabricated 0; ENTROPY_DEFAULT
# stays as the DEFAULT declaration so the numbers the cases carry are unchanged, and
# `test_a_declared_video_counter_reaches_the_result` is what proves the term is finally live.



def _stepped(value, limit):
    """One counter after `addq.w #1 / cmpi.w #N / bne / clr.w`."""
    raised = (value + 1) & WORD_MASK
    return 0 if raised == limit else raised


def model_rng(image, entry_d0, video=ENTROPY_DEFAULT):
    """(the whole d0 it returns, {address: byte}). PUBLIC because test_behavior.py's $2f86 reaches
    the generator and needs both halves of this — the bit it branches on AND the three counter words
    in its own write set. Only the low WORD of d0 is written — `clr.w`, not
    `moveq #0` — so the caller's high half is part of the result."""
    out = {}
    total = (video ^ u16(image, FRAME_TICK)) & WORD_MASK
    for counter, limit, _name in COUNTERS:
        stepped = _stepped(u16(image, counter), limit)
        for offset, byte in enumerate(word(stepped)):
            out[counter + offset] = byte
        total = (total + stepped) & WORD_MASK
    return leaf.set_low_word(entry_d0, total), out


def _stage_row(draw, image, entry_d2):
    """The scaled 0-based row, IN THE LOW WORD of the caller's d2: the BCD ladder, `subq.w #1` and
    `lsl.w #3` (`#5` for the sibling) are every one of them `.w` ops, so d2's high half comes through
    untouched."""
    stage = u16(image, STAGE_NUMBER)
    if s16(stage) > BCD_LIMIT:
        stage = (stage - BCD_CARRY) & WORD_MASK
    return leaf.set_low_word(entry_d2, ((stage - 1) << draw.row_shift) & WORD_MASK)


def _kind_read_address(draw, image, drawn, entry_d2):
    """WHERE `move.b 0(a2,d0.l),d0` reads — table + masked draw + row, the last of which carries the
    caller's high half — and then masked to the 68000's 24-bit ADDRESS BUS, which is what brings a
    sum above $ffffff back round into the machine rather than off it. Shared with the guards below,
    so a case cannot assert about a different address from the one the model reads."""
    return (draw.table + (drawn & draw.draw_mask) + _stage_row(draw, image, entry_d2)) & BUS_ADDR_MASK


def model_kind(draw, image, entry_d2, video=ENTROPY_DEFAULT):
    """(the byte it returns, {address: byte}) — the draw over `model_rng`, on the same image.

    PUBLIC because test_actor.py's respawn continuation calls both draws: its model composes this one
    over the same memory, the way it composes test_hud.py's BCD accumulator."""
    drawn, out = model_rng(image, 0, video)
    at = _kind_read_address(draw, image, drawn, entry_d2)
    # The shim answers a read past the image with zeros, and src/rng.c goes through `bus_read_byte`
    # for exactly that — it folds the address onto the 24-bit bus and then guards the image bound;
    # only an entry d2 with rubbish above its low word can get there.
    drawn_byte = image[at] if at < harness.IMAGE_SIZE else 0
    return drawn_byte & KIND_MASK, out


def _assert_writes(info, expected, what):
    """The write set stated EXACTLY: three counter words and nothing else, whichever arms ran."""
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {sorted(hex(a) for a in written)} against the model's "
        f"{sorted(hex(a) for a in expected)}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")


# The state every case seeds. Nothing here may be entered on a byte a case did not choose: the three
# counters and the tick are the whole of the generator's input, and the stage number the draw's.
RNG_STATE = dict(counters=(0x0000, 0x0000, 0x0000), tick=0x0000, stage=0x0001)
RNG_ENTRY_D0 = 0xdead0000       # a high half the `clr.w` must leave alone
RNG_ENTRY_D1 = 0xbeef5678       # ...and one the `move.w` must leave alone
KIND_ENTRY_D2 = 0               # what the one caller reaches here with (`moveq #0,d2`)


def _rng_pokes(**overrides):
    state = {**RNG_STATE, **overrides}
    pokes = {FRAME_TICK: word(state["tick"]), STAGE_NUMBER: word(state["stage"])}
    for (counter, _limit, _name), value in zip(COUNTERS, state["counters"]):
        pokes[counter] = word(value)
    return pokes


def _run_rng(case, pokes, entry_d0=RNG_ENTRY_D0, video=ENTROPY_DEFAULT):
    what = f"rng_next {case}"
    image = harness.make_image(pokes)
    expected_d0, expected = model_rng(image, entry_d0, video)
    info = leaf.run("rng_next", _RNG(entry_d0), merge_bands(expected), what,
                    regs={"d0": entry_d0, "d1": RNG_ENTRY_D1, "_pokes": pokes},
                    max_insns=RNG_INSN_CAP, hw_seed=leaf.hw_declared(video))
    _assert_writes(info, expected, what)
    assert info["regs"]["d0"] == expected_d0, (
        f"{what}: the original left d0={info['regs']['d0']:#010x}, not {expected_d0:#010x}")
    assert info["ret"] == expected_d0, (
        f"{what}: the reconstruction returned {info['ret']:#010x}, not {expected_d0:#010x}")
    return info, expected_d0


def _run_kind(draw, case, pokes, entry_d2=KIND_ENTRY_D2):
    what = f"{draw.name} {case}"
    image = harness.make_image(pokes)
    expected_kind, expected = model_kind(draw, image, entry_d2)
    info = leaf.run(draw.name, draw.glue(entry_d2), merge_bands(expected), what,
                    regs={"d2": entry_d2, "_pokes": pokes}, max_insns=draw.insn_cap,
                    hw_seed=leaf.hw_declared())
    _assert_writes(info, expected, what)
    assert info["regs"]["d0"] == expected_kind, (
        f"{what}: the original left d0={info['regs']['d0']:#010x}, not {expected_kind:#04x} — the "
        f"closing `andi.l #$1f` masks the WHOLE longword")
    assert info["ret"] == expected_kind, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not {expected_kind:#04x}")
    return info, expected_kind


# --- the pins ----------------------------------------------------------------------------------------

def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RNG_ROUTINE_COUNT)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_an_entry_is_the_instruction_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


def test_the_bodies_are_the_lengths_names_txt_claims_and_the_counters_follow_the_generator():
    """The generator's three counter WORDS sit immediately past its own `rts`, which is what bounds
    the body — there is no other statement of where it ends."""
    assert len(ENTRY_BYTES["rng_next"]) == RNG_BODY_BYTES
    for draw in DRAWS:
        assert len(ENTRY_BYTES[draw.name]) == draw.body_bytes
    assert leaf.entry_of("stage_random_kind32") + KIND32_BODY_BYTES == leaf.entry_of(
        "stage_random_kind8"), "the sibling's body must end exactly where this one's begins"
    assert leaf.entry_of("rng_next") + RNG_BODY_BYTES == COUNTER_A, (
        "the counters must abut the body they belong to")
    for index, (counter, _limit, _name) in enumerate(COUNTERS):
        assert counter == COUNTER_A + index * COUNTER_LEN, "the three counters are consecutive words"


# --- the three counters ------------------------------------------------------------------------------
# Per counter, the values either side of its own wrap plus the two a "modulo" reading would get wrong.
# `limit - 1` is the one that wraps; `limit` itself is the one that does NOT, because the compare is
# an EQUALITY against the raised value and a counter already past its limit never meets it again.

def _counter_cases(limit):
    return ((0, "from rest"),
            (limit - 2, "one step short of the wrap"),
            (limit - 1, "the step that wraps"),
            (limit, "already AT the limit — it does not wrap, it runs on"),
            (limit + 1, "past it"),
            (0xffff, "the 16-bit wrap, which lands on 0 rather than on the limit"))


@pytest.mark.parametrize("index", range(len(COUNTERS)), ids=[c[2] for c in COUNTERS])
def test_each_counter_wraps_at_its_own_limit_and_only_there(index):
    counter, limit, name = COUNTERS[index]
    for seed, why in _counter_cases(limit):
        counters = [0, 0, 0]
        counters[index] = seed
        case = f"counter {name} at {seed:#06x} ({why})"
        info, _d0 = _run_rng(case, _rng_pokes(counters=tuple(counters)))
        ended = leaf.read_int(info, counter, WORD_LEN, case)
        assert ended == _stepped(seed, limit), (
            f"{case}: counter {name} ended {ended:#06x}, not {_stepped(seed, limit):#06x}")


def test_the_counter_sweep_tells_a_clear_at_the_limit_from_a_modulo():
    """The guard: `(n + 1) % limit` and this routine agree everywhere EXCEPT at or above the limit,
    where the modulo keeps wrapping and the equality test never fires again. Both are in the sweep,
    for every counter."""
    for _counter, limit, name in COUNTERS:
        seeds = [seed for seed, _why in _counter_cases(limit)]
        assert limit - 1 in seeds and limit in seeds, f"counter {name}'s sweep misses its boundary"
        assert _stepped(limit, limit) != (limit + 1) % limit, "the two readings must disagree here"


def test_the_three_counters_step_independently_in_one_run():
    """All three advance on every call — there is no carry chain between them — so a run whose three
    seeds are all one short of their own wraps clears all three at once."""
    case = "all three one step from their wraps"
    seeds = tuple(limit - 1 for _counter, limit, _name in COUNTERS)
    info, _d0 = _run_rng(case, _rng_pokes(counters=seeds))
    for counter, _limit, name in COUNTERS:
        assert leaf.read_int(info, counter, WORD_LEN, case) == 0, f"counter {name} did not clear"


# --- the entropy term ---------------------------------------------------------------------------------
# The tick is the only entropy left (the docstring says why), and these are the values that make the
# XOR observable: bits above the byte the video counter would have supplied, and the full word.
TICK_SEEDS = (0x0000, 0x0001, 0x00ff, 0x1234, 0x8000, 0xffff)


@pytest.mark.parametrize("tick", TICK_SEEDS, ids=[f"tick_{t:04x}" for t in TICK_SEEDS])
def test_the_result_is_the_frame_tick_xor_the_video_byte_plus_the_three_counters(tick):
    """The sum is a WORD add three times over, so a tick near $ffff wraps into it."""
    counters = (0x0011, 0x0007, 0x0003)
    case = f"a frame tick of {tick:#06x}"
    _info, ended = _run_rng(case, _rng_pokes(tick=tick, counters=counters))
    stepped = [_stepped(value, limit)
               for value, (_counter, limit, _name) in zip(counters, COUNTERS)]
    assert ended & WORD_MASK == (tick + sum(stepped)) & WORD_MASK, (
        f"{case}: the low word is {ended & WORD_MASK:#06x}")


def test_the_tick_sweep_reaches_the_whole_word_and_the_sums_wrap():
    """A sweep confined to a byte would agree with a port that XORed only the low half — which is
    exactly the half the video byte occupies (these cases declare it as 0; the sweep below drives
    it off 0)."""
    assert any(tick > 0xff for tick in TICK_SEEDS), "the XOR above the low byte is unpinned"
    assert any((tick + 0x11 + 0x07 + 0x03) > WORD_MASK for tick in TICK_SEEDS), (
        "no case makes the three word adds wrap")


def test_the_video_counter_is_a_declared_read_and_no_longer_an_off_image_zero():
    """THE FALSE GREEN, RETIRED. Until batch 33 `$ff8209` was merely off the image: both cores were
    served a fabricated 0, the entropy term vanished, and every green run here was green about a
    generator with no randomness in it. The kit's Phase 7 table models the byte now, so the address
    must still be OUTSIDE the image (or the read would not be a hardware read at all) and it must be
    one the model NAMES (or the declaration below would install nothing)."""
    assert not (0 <= VIDEO_COUNTER < harness.IMAGE_SIZE), (
        f"{VIDEO_COUNTER:#x} is inside the image, so it is no longer an off-image read and this "
        f"battery's model of the entropy term is wrong")
    assert VIDEO_COUNTER in emu.HW_ADDRS, (
        f"{VIDEO_COUNTER:#x} is not in the modeled set {[hex(a) for a in emu.HW_ADDRS]}, so every "
        f"hw_declared() below declares nothing and the term is fabricated again")


@pytest.mark.parametrize("video", [0x00, 0x01, 0x5a, 0x80, 0xff], ids=lambda v: f"video{v:#04x}")
def test_a_declared_video_counter_reaches_the_result(video):
    """...and the term is LIVE: the same seeded state answers differently for each declared byte,
    which is exactly what the fabricated 0 made impossible. `clr.w d0 / move.b $ff8209.l,d0`
    zero-extends the byte before the `eor.w`, so it XORs the tick's LOW half alone — a tick of
    $ff00 would hide the whole term, which is why this one has low bits."""
    pokes = _rng_pokes(tick=0x00ff, counters=(1, 2, 3))
    info, ended = _run_rng(f"declared video {video:#04x}", pokes, video=video)
    assert ended == leaf.set_low_word(RNG_ENTRY_D0, (video ^ 0x00ff) + 2 + 3 + 4), (
        f"the declared counter byte {video:#04x} did not reach the result")
    assert info["regs"]["d0"] == ended


def test_the_generator_is_still_a_pure_function_of_what_the_case_declares():
    """What a per-run constant does NOT buy: on the machine `$ff8209` changes every 512 ns, so two
    reads a few instructions apart differ. A declared byte cannot express that, and this states the
    limit rather than leaving a reader to infer that the randomness is back. The generator reads it
    ONCE per call, so the constant is faithful per CALL and not across a frame."""
    pokes = _rng_pokes(tick=0x00ff, counters=(1, 2, 3))
    first, _ = _run_rng("declared, first run", pokes, video=0x5a)
    second, _ = _run_rng("declared, again", pokes, video=0x5a)
    assert first["regs"]["d0"] == second["regs"]["d0"]


# --- the registers ---------------------------------------------------------------------------------

def test_the_generator_writes_only_the_low_word_of_d0_and_leaves_the_tick_in_d1():
    """`clr.w d0` (not `moveq #0,d0`) is what makes the caller's high half part of the result — and
    $e1f0's `andi.l #$7` two instructions later is what makes that harmless THERE and nowhere else.
    d1 takes the tick through a `move.w`, so its high half survives too."""
    case = "the outgoing registers"
    pokes = _rng_pokes(tick=0x4321, counters=(5, 6, 7))
    info, ended = _run_rng(case, pokes, entry_d0=RNG_ENTRY_D0)
    assert ended >> 16 == RNG_ENTRY_D0 >> 16, f"{case}: the high half was written"
    assert info["regs"]["d1"] == leaf.set_low_word(RNG_ENTRY_D1, 0x4321), (
        f"{case}: d1 is {info['regs']['d1']:#010x}, not the tick in the caller's own high half")


HIGH_HALVES = (0x00000000, 0xffff0000, 0x0bad0000)


@pytest.mark.parametrize("high", HIGH_HALVES, ids=[f"d0_{h:08x}" for h in HIGH_HALVES])
def test_the_generators_result_carries_whatever_high_half_it_was_entered_with(high):
    _run_rng(f"an entry d0 of {high:#010x}", _rng_pokes(counters=(2, 4, 6)), entry_d0=high)



# --- $e1f0 / $e1c8: the two per-stage draws ----------------------------------------------------------
# ONE SET OF CASES OVER TWO DESCRIPTORS. The routines are the same instructions over two tables, so a
# claim proved for only one of them would be a claim about an operand rather than about the routine.
# What cannot be shared is the SEEDS: which stage number and which draw make a reading observable is
# decided by each table's own bytes, so every seed below is keyed by descriptor and every one of them
# carries a guard that COMPUTES why it was chosen.
#
# Both sides of the BCD ladder, and the row that reads below the table. A stage number is packed BCD,
# so $10 is stage ten and `subq.w #6` is the tens carry that decodes it.

# (stage, why) per draw. The 32-wide table has ELEVEN rows where the 8-wide has twenty-two, so its
# sweep walks off the end onto its neighbour rather than to a last row of its own.
STAGE_CASES = {
    DRAW8: (
        (0x0001, "stage 1 — row 0, the first row of the table"),
        (0x0009, "stage 9, the last number the `ble` takes as its own decimal value"),
        (0x0010, "stage 10 in BCD: the first number the tens carry decodes"),
        (0x0019, "stage 19, the last of the tens"),
        (0x0022, "stage 22 — the LAST row the table has"),
        (0x0000, "stage 0, which indexes row -1 and reads BELOW the table"),
    ),
    DRAW32: (
        (0x0001, "stage 1 — row 0, the first row of the table"),
        (0x0009, "stage 9, the last number the `ble` takes as its own decimal value"),
        (0x0010, "stage 10 in BCD: the first number the tens carry decodes"),
        (0x0011, "stage 11 — the LAST row this table has, where the 8-wide one has eleven more"),
        (0x0012, "stage 12: one row PAST the end, onto stage_kind_table's own first row"),
        (0x0000, "stage 0, which indexes row -1 and reads BELOW the table"),
    ),
}
STAGE_SWEEP_SEED = dict(tick=0x0005, counters=(1, 2, 3))

# The far side of the ladder, and what says `cmp.w #$9,d2 / ble` is a SIGNED compare: a number with
# its top bit set is BELOW the limit and keeps its own value, where an unsigned compare would send it
# through the tens carry to a different row. Neither value is "the most negative" — at $8000 the
# 8-wide table's two candidate rows both lie in a run of zeros, and for the 32-wide one only a few
# negative stages put EVERY draw on a pair of bytes that differ. The guard below computes that rather
# than trusting it.
NEGATIVE_STAGE = {DRAW8: 0x8001, DRAW32: 0x800c}

STAGE_PARAMS = [(draw, stage, why) for draw in DRAWS for stage, why in STAGE_CASES[draw]]


@pytest.mark.parametrize("draw,stage,why", STAGE_PARAMS,
                         ids=[f"{d.short}-stage_{s:04x}" for d, s, _w in STAGE_PARAMS])
def test_the_draw_decodes_a_bcd_stage_number_into_a_row_of_the_table(draw, stage, why):
    _run_kind(draw, f"{why}", _rng_pokes(stage=stage, **STAGE_SWEEP_SEED))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_sign_bit_of_a_stage_number_is_taken_as_a_value_and_not_as_a_carry(draw):
    stage = NEGATIVE_STAGE[draw]
    _run_kind(draw, f"stage {stage:#06x}, whose sign bit only a SIGNED `ble` takes as its own value",
              _rng_pokes(stage=stage, **STAGE_SWEEP_SEED))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_negative_stage_separates_a_signed_compare_from_an_unsigned_one_at_every_draw(draw):
    """The guard on NEGATIVE_STAGE. The signed reading keeps the number and the unsigned one carries
    it to a row a whole tens-carry away; ALL of that row's draws must disagree, so the case pins the
    compare whichever one the degenerate generator lands on."""
    stage = NEGATIVE_STAGE[draw]
    assert stage > BCD_LIMIT and s16(stage) <= BCD_LIMIT, (
        "this stage must be above the limit unsigned and below it signed, or it pins no signedness")
    signed_row = ((stage - 1) << draw.row_shift) & WORD_MASK
    carried_row = ((stage - BCD_CARRY - 1) << draw.row_shift) & WORD_MASK
    agree = [index for index in range(draw.row)
             if (harness.BASE_IMAGE[draw.table + signed_row + index] & KIND_MASK)
             == (harness.BASE_IMAGE[draw.table + carried_row + index] & KIND_MASK)]
    assert not agree, (
        f"draws {agree} read the same byte from rows {signed_row:#x} and {carried_row:#x}, so this "
        f"case is silent about the compare whenever the generator lands on one of them")


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_stage_sweep_reaches_both_sides_of_the_bcd_ladder(draw):
    """A sweep confined to stages 1..9 would pass a port that dropped the `subq.w #6` outright."""
    stages = [stage for stage, _why in STAGE_CASES[draw]]
    assert any(s16(s) > BCD_LIMIT for s in stages) and any(s16(s) <= BCD_LIMIT for s in stages)
    assert 0 in stages, "the row that reads below the table is what says the row is not clamped"


# The BCD ladder's own boundary, and the two rows that tell a `>` from a `>=` apart: stage 9 takes its
# own value where a non-strict compare would carry it. Those two rows agree on most of their bytes, so
# the case has to land on one of the few that differ — which is what each draw's own tick is for, and
# what the guard beneath computes rather than assumes.
BCD_LIMIT_STAGE = 0x0009
BCD_LIMIT_SEED = {
    DRAW8: dict(tick=0x0007, counters=(0, 0, 0)),        # stepped to (1,1,1): draw (7+3) & 7 == 2
    DRAW32: dict(tick=0x001e, counters=(0, 0, 0)),       # ...and (30+3) & $1f == 1
}


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_bcd_ladder_takes_its_own_limit_as_a_decimal_value(draw):
    """`cmp.w #9 / ble` — 9 is the LAST number that is already its own decimal value, so a `>=`
    written for the `>` would send it through the tens carry to a different row entirely."""
    _run_kind(draw,
              f"stage {BCD_LIMIT_STAGE:#06x}, the ladder's own limit, on a draw the two candidate "
              f"rows disagree about",
              _rng_pokes(stage=BCD_LIMIT_STAGE, **BCD_LIMIT_SEED[draw]))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_ladder_limit_case_lands_where_its_two_candidate_rows_differ(draw):
    """The guard, and the reason that case has a tick of its own: over the wrong draw the two rows
    hold the same byte and the case would pass either way, pinning nothing."""
    pokes = _rng_pokes(stage=BCD_LIMIT_STAGE, **BCD_LIMIT_SEED[draw])
    image = harness.make_image(pokes)
    drawn, _writes = model_rng(image, 0)
    index = drawn & draw.draw_mask
    strict = draw.table + (BCD_LIMIT_STAGE - 1) * draw.row + index
    carried = draw.table + (BCD_LIMIT_STAGE - BCD_CARRY - 1) * draw.row + index
    assert image[strict] != image[carried], (
        f"draw {index} reads {image[strict]:#04x} from both candidate rows, so the ladder's "
        f"strictness is unobservable in that case")


# WHERE THE CLOSING MASK IS OBSERVABLE AT ALL. Every byte of either table is at or below
# WB_STAGE_KIND_MASK (a case below asserts it), so over the tables the `andi.l #$1f` is a no-op and a
# port that dropped it agrees everywhere — a mutation sweep found exactly that. It becomes observable
# only where the UNBOUNDED index leaves the table, which the instruction does freely: these stage
# numbers put the row on the game's own code, whose bytes are all above the mask, so whichever draw
# the (degenerate) generator lands on the mask has something to do.
ABOVE_MASK_STAGE = {DRAW8: 0x006b, DRAW32: 0x0040}
ABOVE_MASK_SEED = dict(tick=0x0004, counters=(2, 3, 5))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_closing_mask_is_observable_only_where_the_index_leaves_the_table(draw):
    stage = ABOVE_MASK_STAGE[draw]
    _run_kind(draw, f"stage {stage:#06x}, whose row is code rather than table",
              _rng_pokes(stage=stage, **ABOVE_MASK_SEED))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_above_mask_row_really_is_above_the_mask_at_every_draw(draw):
    """The guard: if that row ever stopped holding bytes the mask changes, the case above would
    quietly become one more ordinary out-of-table read."""
    row = draw.table + (ABOVE_MASK_STAGE[draw] - BCD_CARRY - 1) * draw.row
    band = bytes(harness.BASE_IMAGE[row:row + draw.row])
    assert all(byte > KIND_MASK for byte in band), (
        f"the row at {row:#x} is {band.hex()} — the mask must change every byte in it")
    table_end = draw.table + draw.rows * draw.row
    assert not draw.table <= row < table_end, "this row must lie OUTSIDE the table's own extent"


# The candidates a row holds. The generator is degenerate, so a case picks its draw by choosing the
# frame tick that makes the sum land on it — which is the only way to reach every one of them.
DRAW_SWEEP_STAGE = 0x0005
DRAW_PARAMS = [(draw, tick) for draw in DRAWS for tick in range(draw.row)]


@pytest.mark.parametrize("draw,tick", DRAW_PARAMS,
                         ids=[f"{d.short}-tick_{t}" for d, t in DRAW_PARAMS])
def test_every_candidate_of_a_row_is_reachable(draw, tick):
    """`andi.l #$7,d0 / add.l d2,d0` (`#$1f` for the sibling) picks one of the row's bytes; a sweep
    that only ever hit one of them would agree with a port that ignored the draw."""
    _run_kind(draw, f"the draw a tick of {tick} lands on",
              _rng_pokes(stage=DRAW_SWEEP_STAGE, tick=tick, counters=(0, 0, 0)))


@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_the_draw_sweep_really_reaches_every_offset(draw):
    """The guard on the sweep above, and it has to compute the draws rather than trust the ticks: the
    counters are STEPPED before they are summed, so the offset a case reaches is not the tick it
    seeded."""
    reached = set()
    for _draw, tick in (param for param in DRAW_PARAMS if param[0] == draw):
        image = harness.make_image(_rng_pokes(stage=DRAW_SWEEP_STAGE, tick=tick, counters=(0, 0, 0)))
        drawn, _writes = model_rng(image, 0)
        reached.add(drawn & draw.draw_mask)
    assert reached == set(range(draw.row)), f"the sweep reaches {sorted(reached)}"


# --- the entry d2 whose high half addresses the read -------------------------------------------------
# What the caller passes (an effective 0) and what the instruction would let it: every step on the row
# is a `.w`, so d2's high half is untouched, and `add.l d2,d0` then folds it into the INDEX.
#
# ONE DESCRIPTOR ONLY, and DRAW8 is the one, because the whole of what these cases exercise lives in
# the FOURTEEN BYTES THE TWO ROUTINES SHARE: `add.l d2,d0 / move.b 0(a2,d0.l),d0` at $e214 is $e1f0's
# own tail, and $e1c8 reaches it by `bra.w` rather than carrying a copy. The candidate side is one
# static body too. So the sibling's six runs execute the same instruction on the same operand and
# certify nothing the ones below do not — measured in both directions before they were dropped — and
# these are batch 21b's own seeds for the wrap and the width, which is one reason not to move them.
BUS_DRAW = DRAW8
BUS_SEED = dict(stage=0x0005, tick=0x0003, counters=(1, 1, 1))
KIND_ENTRY_D2_CASES = (
    (0x00000000, "what the one caller reaches here with"),
    (0x00010000, "a high half that pushes the read 64 KiB past the table"),
    (0x000f0000, "...and one that pushes it almost to the top of the image"),
)
D2_OFF_IMAGE = 0xffff0000       # a high half whose read leaves the image entirely


@pytest.mark.parametrize("entry_d2,why", KIND_ENTRY_D2_CASES,
                         ids=[f"d2_{v:08x}" for v, _w in KIND_ENTRY_D2_CASES])
def test_the_draws_table_index_carries_the_high_half_of_the_caller_s_d2(entry_d2, why):
    """`add.l d2,d0` is a LONGWORD add over a register only ever written a word at a time, so the
    caller's high half addresses the read as much as the stage does. Every one of these still lands
    inside the image; src/rng.c guards the read the way src/blit.c guards its off-image words, for
    the ones that would not."""
    _run_kind(BUS_DRAW, f"an entry d2 of {entry_d2:#010x} ({why})", _rng_pokes(**BUS_SEED),
              entry_d2=entry_d2)


def test_a_high_half_that_sends_the_read_off_the_image_is_served_zero_on_both_sides():
    """The OTHER side of the cases above, and the one that pins src/rng.c's guard: with a negative
    high half the indexed read leaves the image altogether, where the shim answers zeros — so the
    draw comes back 0 and the C must reach the same answer without indexing outside its buffer."""
    _info, kind = _run_kind(BUS_DRAW,
                            f"an entry d2 of {D2_OFF_IMAGE:#010x}, whose read is off-image",
                            _rng_pokes(**BUS_SEED), entry_d2=D2_OFF_IMAGE)
    assert kind == 0, "an off-image read is served zeros, so the masked draw is 0"


def test_every_high_half_case_still_reads_inside_the_image():
    """The guard: a case whose read left the image would be measuring the off-image guard rather
    than the index arithmetic — that one is the case immediately above, and stated as such."""
    image = harness.make_image(_rng_pokes(**BUS_SEED))
    drawn, _writes = model_rng(image, 0)
    for entry_d2, _why in KIND_ENTRY_D2_CASES:
        at = _kind_read_address(BUS_DRAW, image, drawn, entry_d2)
        assert at < harness.IMAGE_SIZE, f"d2 = {entry_d2:#010x} reads {at:#x}, outside the image"


# ...and one high half that leaves the 68000's 24-BIT ADDRESS BUS. The top byte of an effective
# address is not wired to anything, so the sum comes back ROUND INTO the image — onto the very byte a
# d2 of 0 reads. src/rng.c masks with WB_BUS_ADDR_MASK for exactly this; without the mask the C falls
# through its off-image guard and answers 0 where the oracle answers the table's own byte.
D2_ABOVE_THE_BUS = 0x01000000


def test_a_high_half_past_the_24_bit_address_bus_wraps_back_onto_the_table():
    pokes = _rng_pokes(**BUS_SEED)
    _info, kind = _run_kind(BUS_DRAW,
                            f"an entry d2 of {D2_ABOVE_THE_BUS:#010x}, one bit past the address bus",
                            pokes, entry_d2=D2_ABOVE_THE_BUS)
    unwrapped, _writes = model_kind(BUS_DRAW, harness.make_image(pokes), 0)
    assert kind == unwrapped, (
        f"the wrapped read gave {kind:#04x} where a d2 of 0 gives {unwrapped:#04x} — bit 24 must "
        f"make no difference at all")
    assert kind != 0, (
        "this case has to land on a NONZERO table byte, or it agrees with the off-image guard the "
        "unmasked reading falls through to and pins nothing")


def test_the_bus_wrap_case_really_leaves_the_bus():
    """The guard: without the mask the same sum is far outside the image, which is what makes the
    two readings disagree — and what the 24-bit mask in src/rng.c is there to reconcile."""
    image = harness.make_image(_rng_pokes(**BUS_SEED))
    drawn, _writes = model_rng(image, 0)
    unmasked = (BUS_DRAW.table + (drawn & BUS_DRAW.draw_mask)
                + _stage_row(BUS_DRAW, image, D2_ABOVE_THE_BUS))
    assert unmasked > BUS_ADDR_MASK, f"{unmasked:#x} is on the bus, so nothing here wraps"
    assert _kind_read_address(BUS_DRAW, image, drawn, D2_ABOVE_THE_BUS) < harness.IMAGE_SIZE, (
        "the wrapped address must land back inside the image, or this case is the off-image one")


# ...and the WIDTH of that mask, which "present or absent" does not pin: a bus a bit too narrow
# reproduces every case above. This d2 is what separates 24 from 23 — masked to 24 the sum is off the
# image and served 0, masked to 23 it would come back round ONTO the table and read a real byte.
# (Found by batch 21b's mutation sweep: `& WB_BUS_ADDR_MASK >> 1` survived everything else.)
D2_ONE_BIT_NARROWER = 0x00800000


def test_the_address_bus_is_twenty_four_bits_wide_and_not_twenty_three():
    _info, kind = _run_kind(BUS_DRAW,
                            f"an entry d2 of {D2_ONE_BIT_NARROWER:#010x}, on the bus's top bit",
                            _rng_pokes(**BUS_SEED), entry_d2=D2_ONE_BIT_NARROWER)
    assert kind == 0, "masked to 24 bits this read is off the image, where the shim answers zeros"


def test_the_bus_width_case_would_read_a_nonzero_byte_through_a_narrower_mask():
    """The guard, and the whole point of that case: if a 23-bit mask landed on a zero byte too, the
    two widths would agree and the case would pin nothing."""
    image = harness.make_image(_rng_pokes(**BUS_SEED))
    drawn, _writes = model_rng(image, 0)
    unmasked = (BUS_DRAW.table + (drawn & BUS_DRAW.draw_mask)
                + _stage_row(BUS_DRAW, image, D2_ONE_BIT_NARROWER))
    narrower = unmasked & (BUS_ADDR_MASK >> 1)
    assert narrower < harness.IMAGE_SIZE, "a narrower mask has to land back INSIDE the image"
    assert image[narrower] & KIND_MASK != 0, (
        f"a 23-bit mask reads {image[narrower]:#04x} at {narrower:#x}, which the 5-bit mask turns "
        f"into the same 0 the correct width gives — the two widths must disagree here")
    assert unmasked & BUS_ADDR_MASK >= harness.IMAGE_SIZE, (
        "...while the CORRECT width must stay off the image, or this is the wrap case again")


# --- the two tables, read off the image ---------------------------------------------------------------

@pytest.mark.parametrize("draw", DRAWS, ids=DRAW_IDS)
def test_a_kind_table_holds_only_values_the_closing_mask_passes(draw):
    """Which is half of what bounds them: a run of bytes above the mask would not be candidates."""
    end = draw.table + draw.rows * draw.row
    table = bytes(harness.BASE_IMAGE[draw.table:end])
    assert all(byte == byte & KIND_MASK for byte in table), (
        f"a table byte is above the mask: {sorted(set(table))}")


def test_the_two_kind_tables_bound_each_other_and_their_neighbours():
    """Nothing in the image declares either length. They are bounded by their neighbours: the 32-wide
    table begins where stage_random_kind8's BODY ends, the 8-wide one begins where the 32-wide one
    ends, and the three longword handler pointers at $e432 begin where THAT ends."""
    assert leaf.entry_of("stage_random_kind8") + KIND_BODY_BYTES == KIND32_TABLE, (
        "the 32-wide table must begin on the byte after $e1f0's `rts`")
    assert KIND32_TABLE + KIND32_TABLE_ROWS * KIND32_ROW == KIND_TABLE, (
        "...and end exactly on the 8-wide table's base")
    end = KIND_TABLE + KIND_TABLE_ROWS * KIND_ROW
    following = int.from_bytes(bytes(harness.BASE_IMAGE[end:end + leaf.LONGWORD_BYTES]), "big")
    assert end < following < harness.IMAGE_SIZE, (
        f"the longword at the table's end is {following:#x}, which is not the handler pointer this "
        f"extent rests on")


# --- the fourteen bytes that belong to both -----------------------------------------------------------

def _sibling_transfer_site():
    """SEARCHED for in the image rather than transcribed, the way test_actor.py's `_transfer_site`
    is: the one address in $e1c8's own bytes at which four bytes are a `bra.w` aimed at SHARED_TAIL.
    A `bra.w`'s displacement depends on where it sits, so a wrong address cannot match — and a second
    match would mean the sibling has two ways into the tail, which is the thing worth failing on.
    Its extent is bounded by ../names.txt alone: $e1c8 runs up to where $e1f0 begins."""
    sibling = leaf.entry_of("stage_random_kind32")
    sites = [at for at in range(sibling, leaf.entry_of("stage_random_kind8"), WORD_LEN)
             if bytes(harness.BASE_IMAGE[at:at + len(branch_w_to(BRA_W, at, SHARED_TAIL))])
             == branch_w_to(BRA_W, at, SHARED_TAIL)]
    assert len(sites) == 1, (
        f"$e1c8 holds {len(sites)} `bra.w {SHARED_TAIL:#x}` site(s), not the one that joins it to "
        f"this routine's tail")
    return sites[0]


SIBLING_TRANSFER = _sibling_transfer_site()


def test_the_sibling_draw_ends_in_a_branch_into_the_other_ones_tail():
    """The fourteen bytes from SHARED_TAIL on belong to BOTH routines, so neither port may move them
    — which is why both entry pins above are assembled out of the same four instructions."""
    transfer = branch_w_to(BRA_W, SIBLING_TRANSFER, SHARED_TAIL)
    assert SIBLING_TRANSFER + len(transfer) == leaf.entry_of("stage_random_kind8"), (
        f"the `bra.w` at {SIBLING_TRANSFER:#x} is not $e1c8's LAST instruction, so the sibling's "
        f"body does not end where this routine's begins")
    assert ENTRY_BYTES["stage_random_kind32"][-len(transfer):] == transfer, (
        "the sibling's own entry pin must end in that same `bra.w`")
    shared = bytes(harness.BASE_IMAGE[SHARED_TAIL:SHARED_TAIL + SHARED_TAIL_BYTES])
    assert shared == ENTRY_BYTES["stage_random_kind8"][-SHARED_TAIL_BYTES:], (
        f"the shared tail at {SHARED_TAIL:#x} is {shared.hex()}, not the bytes this battery's own "
        f"entry pin assembles for it")
