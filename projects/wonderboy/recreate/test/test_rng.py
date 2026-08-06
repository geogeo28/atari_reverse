"""Differential test for src/rng.c — the game's PRNG ($68c6) and the per-stage draw over it ($e1f0).

THE REGISTERED FALSE GREEN, STATED HERE BECAUSE THIS IS WHERE A READER OF THE CASES MEETS IT.
`rng_next`'s entropy term is `$ff8209 ^ $b39a` — the shifter's video-address counter (its low, fastest
byte) XOR the frame tick. `$ff8209` is OFF THE IMAGE, and the oracle answers a read past the image
with zeros, so the term collapses to the frame tick alone ON BOTH SIDES and the generator degenerates
to a deterministic function of three counters and one frame counter. Every case below is therefore
green about a generator with no randomness in it. That is a T3-DATA false green — the shape
../PORTABILITY.md §4 names — and no differential can close it: there is no analogue of a video
counter on the candidate side, and inventing one would be verifying the reconstruction against
`shim.c`. What the cases CAN pin, and do, is everything else exactly:

  * the three counters' arithmetic, each seeded on both sides of its own wrap. They are cleared when
    they REACH their limit rather than modulo it, so a counter seeded ABOVE its limit runs on to
    $ffff and round — a case per counter says so, and that is the difference between this and
    `(n + 1) % limit`;
  * that the entropy term is the counter byte XOR WB_FRAME_TICK_B39A and nothing else. The XOR is
    swept over tick values whose bits reach the whole word, and the sum is compared as a WORD;
  * that d0's HIGH half is never written (`clr.w d0`, not `moveq #0,d0`) and comes back as the
    caller left it, and that d1 comes back holding the tick.

...and two things the degeneracy costs, both worth naming. With the video byte gone, two runs from
the same seeded state give the same answer, so nothing here can distinguish "reads the port" from
"reads nothing" — `src/rng.c` goes through `os_in_image` at the port's own address rather than
writing a 0, which is the honest form of the same instruction, but no case can tell the two apart.
And the XOR is unobservable AS AN OPERATOR: `0 ^ tick` is `0 + tick`, so a port that added where the
original XORs is green. That is the batch's one surviving mutant (../STATUS.md), and it is a
consequence rather than a missing case.

$e1f0 ON TOP OF IT. It is one of only two routines in the image whose whole body is "advance the
generator and index a table with the result" — so its cases are the generator's plus a table read:
WB_STAGE_NUMBER decoded from packed BCD (`cmp.w #9 / ble / subq.w #6` is one tens carry), scaled to a
row of WB_STAGE_KIND_ROW, and one of the eight drawn by the generator's low three bits. Both sides of
the BCD ladder AND its signedness (a stage number with its top bit set is BELOW the limit, where an
unsigned compare would carry it), the row that reads BELOW the table (stage 0), the entry d2 whose
high half the `add.l` folds into the INDEX — including one that pushes the index past the 68000's
24-BIT ADDRESS BUS, where it wraps back round into the image — and the shipped table's own extent.

KNOWINGLY NOT PINNED
  * THE SIBLING DRAW at $e1c8 (32 candidates, table $e222) is not reconstructed. It branches INTO
    $e1f0's tail, so a case here pins the shared fourteen bytes — that is all this battery says about
    it.
  * WHAT A KIND IS. $e1f0's one caller stores the result at offset 20 of an actor record and indexes
    a table at $1044c with it; that caller is the respawn continuation `actor_defeat_and_score`
    branches to, and it is not ported.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, addq_w_abs_l, branch, branch_w_to, bsr_w, clr_w_abs_l, clr_w_dn,
                  cmp_w_imm_dn, cmpi_w_abs_l, lea_abs_l, longword, lsl_w_imm_dn, merge_bands,
                  move_b_abs_l_dn, move_w_abs_l_dn, opcode, program_writes, s16, subq_w_dn, u16,
                  word)
from layout import wb

# --- the globals, from the header both languages read ---------------------------------------------
COUNTER_A = wb("RNG_COUNTER_A")
COUNTER_B = wb("RNG_COUNTER_B")
COUNTER_C = wb("RNG_COUNTER_C")
COUNTER_LEN = wb("RNG_COUNTER_LEN")
LIMIT_A = wb("RNG_LIMIT_A")
LIMIT_B = wb("RNG_LIMIT_B")
LIMIT_C = wb("RNG_LIMIT_C")
VIDEO_COUNTER = wb("SHIFTER_VIDEO_COUNTER_LOW")
FRAME_TICK = wb("FRAME_TICK_B39A")

STAGE_NUMBER = wb("STAGE_NUMBER")
KIND_TABLE = wb("STAGE_KIND_TABLE")
KIND_TABLE_ROWS = wb("STAGE_KIND_TABLE_ROWS")
KIND_ROW = wb("STAGE_KIND_ROW")
KIND_ROW_SHIFT = wb("STAGE_KIND_ROW_SHIFT")
KIND_DRAW_MASK = wb("STAGE_KIND_DRAW_MASK")
KIND_MASK = wb("STAGE_KIND_MASK")
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

# The instruction caps, from the bodies. rng_next is three 4-instruction counter steps (one arm of
# each is skipped) plus the seven-instruction tail; the draw adds its own eight and the `bsr`.
# `leaf.RUNNER_SENTINEL_INSN` is the one instruction osh_run counts past the routine's own `rts`.
COUNTER_STEP_INSNS = 4
RNG_TAIL_INSNS = 8              # `clr.w / move.b / move.w / eor.w` + one `add.w` per counter + `rts`
KIND_BODY_INSNS = 13            # its own thirteen, of which the `bsr` is the generator's whole run
RNG_INSN_CAP = (COUNTER_STEP_INSNS * len(COUNTERS) + RNG_TAIL_INSNS
                + leaf.RUNNER_SENTINEL_INSN)
KIND_INSN_CAP = KIND_BODY_INSNS + RNG_INSN_CAP


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


def _kind_entry():
    """$e1f0. Its `bsr.w` displacement comes out of ../names.txt's two addresses, so a pin aimed at
    anything but rng_next fails on the bytes."""
    base = leaf.entry_of("stage_random_kind8")
    carry = subq_w_dn(BCD_CARRY, D2)
    return leaf.assemble(base, [
        lea_abs_l(A2, KIND_TABLE), move_w_abs_l_dn(D2, STAGE_NUMBER),
        cmp_w_imm_dn(D2, BCD_LIMIT), branch(BLE_W, carry), carry,
        subq_w_dn(1, D2), lsl_w_imm_dn(KIND_ROW_SHIFT, D2),
        lambda at: bsr_w(at, leaf.entry_of("rng_next")),
        _andi_l_dn(D0, KIND_DRAW_MASK),
        opcode(ADD_L_DN_DN | (D0 << 9) | D2),
        opcode(MOVE_B_INDEXED_DN | (D0 << 9) | A2) + word((D0 << 12) | 0x800),
        _andi_l_dn(D0, KIND_MASK),
        RTS,
    ])


ENTRY_BYTES = {"rng_next": _rng_entry(), "stage_random_kind8": _kind_entry()}
RNG_ROUTINE_COUNT = 2

# --- the glue ---------------------------------------------------------------------------------------
_RNG = leaf.register_glue("rng_next", [ctypes.c_uint32], ctypes.c_uint32)
_KIND = leaf.register_glue("stage_random_kind8", [ctypes.c_uint32], ctypes.c_uint32)


# --- the model both runners compare against ---------------------------------------------------------
# The video byte is 0 on both sides (the module docstring says why), which is what makes a model
# possible at all — the term is stated as ENTROPY_OFF_IMAGE rather than dropped, so the case that
# stops being true fails here rather than nowhere.
ENTROPY_OFF_IMAGE = 0


def _stepped(value, limit):
    """One counter after `addq.w #1 / cmpi.w #N / bne / clr.w`."""
    raised = (value + 1) & WORD_MASK
    return 0 if raised == limit else raised


def _model_rng(image, entry_d0):
    """(the whole d0 it returns, {address: byte}). Only the low WORD of d0 is written — `clr.w`, not
    `moveq #0` — so the caller's high half is part of the result."""
    out = {}
    total = (ENTROPY_OFF_IMAGE ^ u16(image, FRAME_TICK)) & WORD_MASK
    for counter, limit, _name in COUNTERS:
        stepped = _stepped(u16(image, counter), limit)
        for offset, byte in enumerate(word(stepped)):
            out[counter + offset] = byte
        total = (total + stepped) & WORD_MASK
    return leaf.set_low_word(entry_d0, total), out


def _stage_row(image, entry_d2):
    """The scaled 0-based row, IN THE LOW WORD of the caller's d2: the BCD ladder, `subq.w #1` and
    `lsl.w #3` are every one of them `.w` ops, so d2's high half comes through untouched."""
    stage = u16(image, STAGE_NUMBER)
    if s16(stage) > BCD_LIMIT:
        stage = (stage - BCD_CARRY) & WORD_MASK
    return leaf.set_low_word(entry_d2, ((stage - 1) << KIND_ROW_SHIFT) & WORD_MASK)


def _kind_read_address(image, drawn, entry_d2):
    """WHERE `move.b 0(a2,d0.l),d0` reads — table + masked draw + row, the last of which carries the
    caller's high half — and then masked to the 68000's 24-bit ADDRESS BUS, which is what brings a
    sum above $ffffff back round into the machine rather than off it. Shared with the guards below,
    so a case cannot assert about a different address from the one the model reads."""
    return (KIND_TABLE + (drawn & KIND_DRAW_MASK) + _stage_row(image, entry_d2)) & BUS_ADDR_MASK


def _model_kind(image, entry_d2):
    """(the byte it returns, {address: byte}) — the draw over `_model_rng`, on the same image."""
    drawn, out = _model_rng(image, 0)
    at = _kind_read_address(image, drawn, entry_d2)
    # The shim answers a read past the image with zeros, and src/rng.c goes through `os_in_image`
    # for exactly that; only an entry d2 with rubbish above its low word can get there.
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


def _run_rng(case, pokes, entry_d0=RNG_ENTRY_D0):
    what = f"rng_next {case}"
    image = harness.make_image(pokes)
    expected_d0, expected = _model_rng(image, entry_d0)
    info = leaf.run("rng_next", _RNG(entry_d0), merge_bands(expected), what,
                    regs={"d0": entry_d0, "d1": RNG_ENTRY_D1, "_pokes": pokes},
                    max_insns=RNG_INSN_CAP)
    _assert_writes(info, expected, what)
    assert info["regs"]["d0"] == expected_d0, (
        f"{what}: the original left d0={info['regs']['d0']:#010x}, not {expected_d0:#010x}")
    assert info["ret"] == expected_d0, (
        f"{what}: the reconstruction returned {info['ret']:#010x}, not {expected_d0:#010x}")
    return info, expected_d0


def _run_kind(case, pokes, entry_d2=KIND_ENTRY_D2):
    what = f"stage_random_kind8 {case}"
    image = harness.make_image(pokes)
    expected_kind, expected = _model_kind(image, entry_d2)
    info = leaf.run("stage_random_kind8", _KIND(entry_d2), merge_bands(expected), what,
                    regs={"d2": entry_d2, "_pokes": pokes}, max_insns=KIND_INSN_CAP)
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
    assert len(ENTRY_BYTES["stage_random_kind8"]) == KIND_BODY_BYTES
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
    exactly the half the (vanished) video byte occupies."""
    assert any(tick > 0xff for tick in TICK_SEEDS), "the XOR above the low byte is unpinned"
    assert any((tick + 0x11 + 0x07 + 0x03) > WORD_MASK for tick in TICK_SEEDS), (
        "no case makes the three word adds wrap")


def test_the_video_counter_read_is_zero_on_both_sides_and_the_generator_degenerates():
    """THE FALSE GREEN, AS A CASE. Two identical seeded states give the same answer, which on real
    hardware they would not: `$ff8209` changes every 512 ns. This asserts the degenerate form the
    whole battery rests on — the result with the port's contribution taken as ENTROPY_OFF_IMAGE —
    so that a harness which one day DID serve that byte reddens here, where the explanation is,
    rather than in nine other cases at once."""
    assert not (0 <= VIDEO_COUNTER < harness.IMAGE_SIZE), (
        f"{VIDEO_COUNTER:#x} is inside the image, so it is no longer an off-image read and this "
        f"battery's model of the entropy term is wrong")
    pokes = _rng_pokes(tick=0x00ff, counters=(1, 2, 3))
    first, _expected = _run_rng("the degenerate generator, first run", pokes)
    second, _expected = _run_rng("the degenerate generator, again", pokes)
    assert first["regs"]["d0"] == second["regs"]["d0"] == leaf.set_low_word(
        RNG_ENTRY_D0, (ENTROPY_OFF_IMAGE ^ 0x00ff) + 2 + 3 + 4), (
        "the generator is a pure function of the seeded state, which is the false green")


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


# --- $e1f0: the per-stage draw -----------------------------------------------------------------------
# Both sides of the BCD ladder, and the row that reads below the table. A stage number is packed BCD,
# so $10 is stage ten and `subq.w #6` is the tens carry that decodes it.
#
# NEGATIVE_STAGE is the far side of the ladder, and it is what says `cmp.w #$9,d2 / ble` is a SIGNED
# compare: a number with its top bit set is BELOW the limit and keeps its own value, where an
# unsigned compare would send it through the tens carry to a row 48 bytes away. $8001 rather than the
# $8000 that "the most negative" would suggest, because at $8000 BOTH candidate rows lie in a run of
# zero bytes and the two readings are indistinguishable — the guard below computes that rather than
# trusting it.
NEGATIVE_STAGE = 0x8001

STAGE_CASES = (
    (0x0001, "stage 1 — row 0, the first row of the table"),
    (0x0009, "stage 9, the last number the `ble` takes as its own decimal value"),
    (0x0010, "stage 10 in BCD: the first number the tens carry decodes"),
    (0x0019, "stage 19, the last of the tens"),
    (0x0022, "stage 22 — the LAST row the table has"),
    (0x0000, "stage 0, which indexes row -1 and reads BELOW the table"),
    (NEGATIVE_STAGE, "the sign bit set, which only a SIGNED `ble` takes as its own value"),
)


@pytest.mark.parametrize("stage,why", STAGE_CASES, ids=[f"stage_{c[0]:04x}" for c in STAGE_CASES])
def test_the_draw_decodes_a_bcd_stage_number_into_a_row_of_the_table(stage, why):
    _run_kind(f"{why}", _rng_pokes(stage=stage, tick=0x0005, counters=(1, 2, 3)))


# The BCD ladder's own boundary, and the two rows that tell a `>` from a `>=` apart: stage 9 takes
# its own value (row 8) where a non-strict compare would carry it (row 2). Those two rows agree on
# SIX of their eight bytes, so the case has to land on one of the two that differ — which is what
# the tick below is for, and what the guard beneath it computes rather than assumes.
BCD_LIMIT_STAGE = 0x0009
BCD_LIMIT_COUNTERS = (0, 0, 0)      # stepped to (1, 1, 1), so the draw is (tick + 3) & 7
BCD_LIMIT_TICK = 0x0007             # ...which puts it on 2, a draw the two rows disagree about


def test_the_bcd_ladder_takes_its_own_limit_as_a_decimal_value():
    """`cmp.w #9 / ble` — 9 is the LAST number that is already its own decimal value, so a `>=`
    written for the `>` would send it through the tens carry to a different row entirely."""
    _run_kind(f"stage {BCD_LIMIT_STAGE:#06x}, the ladder's own limit, on a draw the two candidate "
              f"rows disagree about",
              _rng_pokes(stage=BCD_LIMIT_STAGE, tick=BCD_LIMIT_TICK, counters=BCD_LIMIT_COUNTERS))


def test_the_ladder_limit_case_lands_where_its_two_candidate_rows_differ():
    """The guard, and the reason that case has a tick of its own: the strict reading puts stage 9 on
    row 8 and the non-strict on row 2, and those rows hold the same byte at six of eight draws — so
    over the wrong draw the case would pass either way and pin nothing."""
    image = harness.make_image(_rng_pokes(stage=BCD_LIMIT_STAGE, tick=BCD_LIMIT_TICK,
                                          counters=BCD_LIMIT_COUNTERS))
    drawn, _writes = _model_rng(image, 0)
    draw = drawn & KIND_DRAW_MASK
    strict = KIND_TABLE + (BCD_LIMIT_STAGE - 1) * KIND_ROW + draw
    carried = KIND_TABLE + (BCD_LIMIT_STAGE - BCD_CARRY - 1) * KIND_ROW + draw
    assert image[strict] != image[carried], (
        f"draw {draw} reads {image[strict]:#04x} from both candidate rows, so the ladder's "
        f"strictness is unobservable in that case")


def test_the_negative_stage_separates_a_signed_compare_from_an_unsigned_one_at_every_draw():
    """The guard on NEGATIVE_STAGE, and the reason it is $8001. The signed reading keeps the number
    (row 0, the table's own first row) and the unsigned one carries it (a row 48 bytes below the
    table); ALL EIGHT draws disagree there, so the case pins the compare whichever one the degenerate
    generator lands on."""
    assert NEGATIVE_STAGE > BCD_LIMIT and s16(NEGATIVE_STAGE) <= BCD_LIMIT, (
        "this stage must be above the limit unsigned and below it signed, or it pins no signedness")
    signed_row = ((NEGATIVE_STAGE - 1) << KIND_ROW_SHIFT) & WORD_MASK
    carried_row = ((NEGATIVE_STAGE - BCD_CARRY - 1) << KIND_ROW_SHIFT) & WORD_MASK
    agree = [draw for draw in range(KIND_ROW)
             if (harness.BASE_IMAGE[KIND_TABLE + signed_row + draw] & KIND_MASK)
             == (harness.BASE_IMAGE[KIND_TABLE + carried_row + draw] & KIND_MASK)]
    assert not agree, (
        f"draws {agree} read the same byte from rows {signed_row:#x} and {carried_row:#x}, so this "
        f"case is silent about the compare whenever the generator lands on one of them")


# WHERE THE CLOSING MASK IS OBSERVABLE AT ALL. Every byte of the table's own 176 is at or below
# WB_STAGE_KIND_MASK (a case above asserts it), so over the table the `andi.l #$1f` is a no-op and a
# port that dropped it agrees everywhere — a mutation sweep found exactly that. It becomes observable
# only where the UNBOUNDED index leaves the table, which the instruction does freely: this stage
# number puts the row on the game's own code at $e6a2, whose eight bytes are all above the mask, so
# whichever draw the (degenerate) generator lands on the mask has something to do.
ABOVE_MASK_STAGE = 0x006b


def test_the_closing_mask_is_observable_only_where_the_index_leaves_the_table():
    _run_kind(f"stage {ABOVE_MASK_STAGE:#06x}, whose row is code rather than table",
              _rng_pokes(stage=ABOVE_MASK_STAGE, tick=0x0004, counters=(2, 3, 5)))


def test_the_above_mask_row_really_is_above_the_mask_at_every_draw():
    """The guard: if that row ever stopped holding bytes the mask changes, the case above would
    quietly become one more ordinary out-of-table read."""
    row = KIND_TABLE + (ABOVE_MASK_STAGE - BCD_CARRY - 1) * KIND_ROW
    band = bytes(harness.BASE_IMAGE[row:row + KIND_ROW])
    assert all(byte > KIND_MASK for byte in band), (
        f"the row at {row:#x} is {band.hex()} — the mask must change every byte in it")
    table_end = KIND_TABLE + KIND_TABLE_ROWS * KIND_ROW
    assert not KIND_TABLE <= row < table_end, "this row must lie OUTSIDE the table's own extent"


def test_the_stage_sweep_reaches_both_sides_of_the_bcd_ladder():
    """A sweep confined to stages 1..9 would pass a port that dropped the `subq.w #6` outright."""
    stages = [stage for stage, _why in STAGE_CASES]
    assert any(s16(s) > BCD_LIMIT for s in stages) and any(s16(s) <= BCD_LIMIT for s in stages)
    assert 0 in stages, "the row that reads below the table is what says the row is not clamped"


# The eight draws a row holds. The generator is degenerate, so a case picks its draw by choosing the
# counters and tick that make the sum land on it — which is the only way to reach all eight.
DRAW_SEEDS = tuple((0x0000, (draw, 0, 0)) for draw in range(KIND_ROW))


@pytest.mark.parametrize("tick,counters", DRAW_SEEDS, ids=[f"draw_{d}" for d in range(KIND_ROW)])
def test_every_candidate_of_a_row_is_reachable(tick, counters):
    """`andi.l #$7,d0 / add.l d2,d0` picks one of WB_STAGE_KIND_ROW bytes; a sweep that only ever hit
    one of them would agree with a port that ignored the draw."""
    pokes = _rng_pokes(stage=0x0005, tick=tick, counters=counters)
    _run_kind(f"draw {counters[0]} of stage 5's row", pokes)


def test_the_draw_sweep_really_reaches_all_eight_offsets():
    """The guard on the sweep above, and it has to compute the draws rather than trust the seeds:
    the counters are STEPPED before they are summed, so the offset a case reaches is not the number
    it seeded."""
    reached = set()
    for tick, counters in DRAW_SEEDS:
        image = harness.make_image(_rng_pokes(stage=0x0005, tick=tick, counters=counters))
        drawn, _writes = _model_rng(image, 0)
        reached.add(drawn & KIND_DRAW_MASK)
    assert reached == set(range(KIND_ROW)), f"the sweep reaches {sorted(reached)}"


# What the caller passes (0) and what the instruction would let it: every step on the row is a `.w`,
# so d2's high half is untouched, and `add.l d2,d0` then folds it into the INDEX.
KIND_ENTRY_D2_CASES = (
    (0x00000000, "what the one caller reaches here with"),
    (0x00010000, "a high half that pushes the read 64 KiB past the table"),
    (0x000f0000, "...and one that pushes it almost to the top of the image"),
)
D2_OFF_IMAGE = 0xffff0000       # a high half whose read leaves the image entirely


@pytest.mark.parametrize("entry_d2,why", KIND_ENTRY_D2_CASES,
                         ids=[f"d2_{c[0]:08x}" for c in KIND_ENTRY_D2_CASES])
def test_the_draws_table_index_carries_the_high_half_of_the_caller_s_d2(entry_d2, why):
    """`add.l d2,d0` is a LONGWORD add over a register only ever written a word at a time, so the
    caller's high half addresses the read as much as the stage does. Every one of these still lands
    inside the image; src/rng.c guards the read the way src/blit.c guards its off-image words, for
    the ones that would not."""
    _run_kind(f"an entry d2 of {entry_d2:#010x} ({why})",
              _rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1)), entry_d2=entry_d2)


def test_a_high_half_that_sends_the_read_off_the_image_is_served_zero_on_both_sides():
    """The OTHER side of the cases above, and the one that pins src/rng.c's guard: with a negative
    high half the indexed read leaves the image altogether, where the shim answers zeros — so the
    draw comes back 0 and the C must reach the same answer without indexing outside its buffer."""
    _info, kind = _run_kind(f"an entry d2 of {D2_OFF_IMAGE:#010x}, whose read is off-image",
                            _rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1)),
                            entry_d2=D2_OFF_IMAGE)
    assert kind == 0, "an off-image read is served zeros, so the masked draw is 0"


def test_every_high_half_case_still_reads_inside_the_image():
    """The guard: a case whose read left the image would be measuring the off-image guard rather
    than the index arithmetic — that one is the case immediately above, and stated as such."""
    image = harness.make_image(_rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1)))
    drawn, _writes = _model_rng(image, 0)
    for entry_d2, _why in KIND_ENTRY_D2_CASES:
        at = _kind_read_address(image, drawn, entry_d2)
        assert at < harness.IMAGE_SIZE, f"d2 = {entry_d2:#010x} reads {at:#x}, outside the image"


# ...and one high half that leaves the 68000's 24-BIT ADDRESS BUS. The top byte of an effective
# address is not wired to anything, so the sum comes back ROUND INTO the image — onto the very byte a
# d2 of 0 reads. src/rng.c masks with WB_BUS_ADDR_MASK for exactly this; without the mask the C falls
# through its off-image guard and answers 0 where the oracle answers the table's own byte.
D2_ABOVE_THE_BUS = 0x01000000


def test_a_high_half_past_the_24_bit_address_bus_wraps_back_onto_the_table():
    pokes = _rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1))
    _info, kind = _run_kind(f"an entry d2 of {D2_ABOVE_THE_BUS:#010x}, one bit past the address bus",
                            pokes, entry_d2=D2_ABOVE_THE_BUS)
    unwrapped, _writes = _model_kind(harness.make_image(pokes), 0)
    assert kind == unwrapped, (
        f"the wrapped read gave {kind:#04x} where a d2 of 0 gives {unwrapped:#04x} — bit 24 must "
        f"make no difference at all")
    assert kind != 0, (
        "this case has to land on a NONZERO table byte, or it agrees with the off-image guard the "
        "unmasked reading falls through to and pins nothing")


def test_the_bus_wrap_case_really_leaves_the_bus():
    """The guard: without the mask the same sum is far outside the image, which is what makes the
    two readings disagree — and what the 24-bit mask in src/rng.c is there to reconcile."""
    image = harness.make_image(_rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1)))
    drawn, _writes = _model_rng(image, 0)
    unmasked = KIND_TABLE + (drawn & KIND_DRAW_MASK) + _stage_row(image, D2_ABOVE_THE_BUS)
    assert unmasked > BUS_ADDR_MASK, f"{unmasked:#x} is on the bus, so nothing here wraps"
    assert _kind_read_address(image, drawn, D2_ABOVE_THE_BUS) < harness.IMAGE_SIZE, (
        "the wrapped address must land back inside the image, or this case is the off-image one")


# ...and the WIDTH of that mask, which "present or absent" does not pin: a bus a bit too narrow
# reproduces every case above. This d2 is what separates 24 from 23 — masked to 24 the sum is off the
# image and served 0, masked to 23 it would come back round ONTO the table and read a real byte.
# (Found by the batch's mutation sweep: `& WB_BUS_ADDR_MASK >> 1` survived everything else.)
D2_ONE_BIT_NARROWER = 0x00800000


def test_the_address_bus_is_twenty_four_bits_wide_and_not_twenty_three():
    pokes = _rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1))
    _info, kind = _run_kind(f"an entry d2 of {D2_ONE_BIT_NARROWER:#010x}, on the bus's top bit",
                            pokes, entry_d2=D2_ONE_BIT_NARROWER)
    assert kind == 0, "masked to 24 bits this read is off the image, where the shim answers zeros"


def test_the_bus_width_case_would_read_a_nonzero_byte_through_a_narrower_mask():
    """The guard, and the whole point of that case: if a 23-bit mask landed on a zero byte too, the
    two widths would agree and the case would pin nothing."""
    image = harness.make_image(_rng_pokes(stage=0x0005, tick=0x0003, counters=(1, 1, 1)))
    drawn, _writes = _model_rng(image, 0)
    unmasked = KIND_TABLE + (drawn & KIND_DRAW_MASK) + _stage_row(image, D2_ONE_BIT_NARROWER)
    narrower = unmasked & (BUS_ADDR_MASK >> 1)
    assert narrower < harness.IMAGE_SIZE, "a narrower mask has to land back INSIDE the image"
    assert image[narrower] & KIND_MASK != 0, (
        f"a 23-bit mask reads {image[narrower]:#04x} at {narrower:#x}, which the 5-bit mask turns "
        f"into the same 0 the correct width gives — the two widths must disagree here")
    assert unmasked & BUS_ADDR_MASK >= harness.IMAGE_SIZE, (
        "...while the CORRECT width must stay off the image, or this is the wrap case again")


# --- the table, read off the image --------------------------------------------------------------------

def test_the_kind_table_is_self_bounding_and_holds_only_values_the_mask_passes():
    """Nothing in the image declares the table's length. It is bounded by its neighbours — the
    sibling draw's 32-wide table ends on its base, and the three longword handler pointers at $e432
    begin where it ends — and by the mask: every byte in it survives `andi.l #$1f` unchanged, which
    a run of bytes that did not would not."""
    end = KIND_TABLE + KIND_TABLE_ROWS * KIND_ROW
    table = bytes(harness.BASE_IMAGE[KIND_TABLE:end])
    assert all(byte == byte & KIND_MASK for byte in table), (
        f"a table byte is above the mask: {sorted(set(table))}")
    following = int.from_bytes(bytes(harness.BASE_IMAGE[end:end + leaf.LONGWORD_BYTES]), "big")
    assert end < following < harness.IMAGE_SIZE, (
        f"the longword at the table's end is {following:#x}, which is not the handler pointer this "
        f"extent rests on")


# The tail the two draws share: `add.l d2,d0 / move.b 0(a2,d0.l),d0 / andi.l #$1f,d0 / rts` —
# 2 + 4 + 6 + 2, the last fourteen bytes of $e1f0's body.
SHARED_TAIL_BYTES = 14
SHARED_TAIL = leaf.entry_of("stage_random_kind8") + KIND_BODY_BYTES - SHARED_TAIL_BYTES


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


def test_the_sibling_draw_ends_in_a_branch_into_this_ones_tail():
    """$e1c8 is not reconstructed, and this is the whole of what this battery says about it: it ENDS
    in a `bra.w` into the middle of $e1f0, so the fourteen bytes from that target on belong to BOTH
    routines and porting the sibling later must not move them."""
    transfer = branch_w_to(BRA_W, SIBLING_TRANSFER, SHARED_TAIL)
    assert SIBLING_TRANSFER + len(transfer) == leaf.entry_of("stage_random_kind8"), (
        f"the `bra.w` at {SIBLING_TRANSFER:#x} is not $e1c8's LAST instruction, so the sibling's "
        f"body does not end where this routine's begins")
    shared = bytes(harness.BASE_IMAGE[SHARED_TAIL:SHARED_TAIL + SHARED_TAIL_BYTES])
    assert shared == ENTRY_BYTES["stage_random_kind8"][-SHARED_TAIL_BYTES:], (
        f"the shared tail at {SHARED_TAIL:#x} is {shared.hex()}, not the bytes this battery's own "
        f"entry pin assembles for it")
