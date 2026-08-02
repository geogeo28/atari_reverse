"""Differential test for the 29 effect/state leaves at $10200..$103e7 (src/effects.c).

Every case runs the ORIGINAL routine under the Musashi oracle and the reconstruction on the same
image, and requires the two to agree byte for byte over the whole image — plus that the original
wrote nothing outside the one or two words the case says it may touch. These routines return
nothing, so memory is the entire surface and the diff sees all of it.

They are also entered ONLY through a dispatch table, so nothing about them is exercised by running
the game up to them: the state they read is whatever the rest of the game left, and the seeds below
stand in for it. That makes the seeding the design of this file:

  * a plain setter is seeded with a DESTINATION it must overwrite — four pre-values, one of which
    ($ffff) is what exactly one of the setters itself writes, so on that case the plain diff proves
    nothing and the kit's attribution (poison) pass is what catches it;
  * the two clamped adds are seeded on BOTH sides of their boundary, and past the point where the
    16-bit add wraps negative, so the `bgt` is pinned as the SIGNED 16-bit compare it is — but NOT
    as a strict one, which no seeding can do (see BOUNDARY_OFFSETS). The two branch tables below say
    which branch each case takes, and a guard requires both to appear;
  * the four record pushes are seeded with a WRITE POINTER, including one that makes the record
    land on the pointer itself.

KNOWINGLY NOT PINNED
  * the clamp's STRICTNESS, which is not a coverage hole but an equivalence: at a raise landing
    exactly on the maximum both arms store the same word, so `>` and `>=` cannot be told apart from
    outside the routine at all. The C is faithful to the original `bgt`; nothing here holds it.
  * what any of this state MEANS. ../names.txt names these routines for their mechanism and
    include/wonderboy.h records the shape each global is written and read with; nothing here claims
    more, and a green suite would not make a meaning-level name true.
  * the dispatch that reaches them. Each case enters the routine directly, so the object field at
    offset 62 that selects a handler, and the message id / 50-frame timer both call sites set
    alongside it, are outside this battery.
"""
import pytest

import harness
import leaf
from leaf import (MOVE_W_ABS_L_ABS_L, MOVE_W_ABS_L_D0, MOVE_W_D0_ABS_L, RTS, longword, word)
from layout import wb

# --- the globals, from the header both languages read (include/wonderboy.h) ---------------------
HUD_SLOT_BBBE = wb("HUD_SLOT_BBBE")
HUD_SLOT_BBC0 = wb("HUD_SLOT_BBC0")
HUD_SLOT_BBC2 = wb("HUD_SLOT_BBC2")
HUD_SLOT_BBC6 = wb("HUD_SLOT_BBC6")
HUD_SLOT_BBC8 = wb("HUD_SLOT_BBC8")
METER_VALUE = wb("HUD_METER_VALUE")
METER_MAX = wb("HUD_METER_MAX")
STATE_BD66 = wb("EFFECT_STATE_BD66")
STATE_BD68 = wb("EFFECT_STATE_BD68")
STATE_BD6A = wb("EFFECT_STATE_BD6A")
STATE_21E4 = wb("EFFECT_STATE_21E4")
STATE_6F9C = wb("STATE_WORD_6F9C")
WORD_LEN = wb("STATE_WORD_LEN")
WRITE_PTR = wb("EFFECT_RECORD_WRITE_PTR")
WRITE_PTR_LEN = wb("EFFECT_RECORD_PTR_LEN")
RECORD_LEN = wb("EFFECT_RECORD_LEN")

WORD_MASK = leaf.WORD_MASK

# --- the encodings this battery reconstructs its entries from ------------------------------------
# Named so the tables below read as instructions rather than as hex. Every one of these routines is
# a move and an rts, which is why the entry pin can be built from the same (address, immediate) the
# reconstruction uses: a wrong constant on either side fails at its own address. The opcodes
# test_hud.py also spells (RTS and the three `move.w` forms) are imported from leaf.py above, so the
# two batteries cannot disagree about them; these are the ones only this file needs.
MOVE_W_IMM_ABS_L = b"\x33\xfc"      # move.w #imm,<abs>.l
MOVE_W_IMM_ABS_W = b"\x31\xfc"      # move.w #imm,<abs>.w  (a 16-bit operand, so 2 bytes shorter)
CMP_W_ABS_L_D0 = b"\xb0\x79"        # cmp.w <abs>.l,d0
BGT_W_OVER_THE_STORE = b"\x6e\x00\x00\x0a"   # bgt.w +10 — past the `move.w d0,meter / rts` below
ADDQ_L_2_ABS_L = b"\x54\xb9"        # addq.l #2,<abs>.l
MOVEA_L_ABS_L_A1 = b"\x22\x79"      # movea.l <abs>.l,a1
MOVE_W_IMM_A1 = b"\x32\xbc"         # move.w #imm,(a1)


# --- the 19 plain word setters ------------------------------------------------------------------
# (function, destination, the immediate word, is the destination operand a LONG address?)
# The HUD-slot immediates are `value << 8 | changed`; they are written out rather than composed so
# that this table is a transcription of the disassembly and not a second copy of src/effects.c's
# arithmetic.
WORD_SETTERS = (
    ("set_state_bbc8_1ff", HUD_SLOT_BBC8, 0x01ff, True),
    ("set_state_bbc8_2ff", HUD_SLOT_BBC8, 0x02ff, True),
    ("set_state_bbc8_3ff", HUD_SLOT_BBC8, 0x03ff, True),
    ("set_state_bbc8_4ff", HUD_SLOT_BBC8, 0x04ff, True),
    ("set_state_bbc8_6ff", HUD_SLOT_BBC8, 0x06ff, True),
    # The odd one out: a SHORT absolute operand, so 8 bytes where its five neighbours are 10.
    ("set_state_6f9c_ffff", STATE_6F9C, 0xffff, False),
    ("effect_set_bd6a_1", STATE_BD6A, 0x0001, True),
    ("effect_set_bd6a_2", STATE_BD6A, 0x0002, True),
    ("effect_set_bd6a_3", STATE_BD6A, 0x0003, True),
    ("effect_set_bd6a_4", STATE_BD6A, 0x0004, True),
    ("effect_set_bbc2_80ff", HUD_SLOT_BBC2, 0x80ff, True),
    ("effect_set_bd66_1", STATE_BD66, 0x0001, True),
    ("effect_set_bd66_2", STATE_BD66, 0x0002, True),
    ("effect_set_bd66_3", STATE_BD66, 0x0003, True),
    ("effect_set_bd66_4", STATE_BD66, 0x0004, True),
    ("effect_set_bd66_5", STATE_BD66, 0x0005, True),
    ("effect_set_bbbe_05ff", HUD_SLOT_BBBE, 0x05ff, True),
    ("effect_set_bbc0_05ff", HUD_SLOT_BBC0, 0x05ff, True),
    ("effect_set_bbc6_01ff", HUD_SLOT_BBC6, 0x01ff, True),
)

# What the destination holds before the call. $ffff and $0000 are the interesting ends (one of the
# setters writes $ffff, so that case only passes on the attribution pass); the other two have both
# bytes distinct, which is what would catch a port that wrote one byte of the word.
SEED_WORDS = (0x0000, 0xffff, 0x1234, 0xa55a)

# --- the three that stamp a second word first ---------------------------------------------------
STATE_21E4_STAMP = 0x0002        # the same value all three write, whatever their own variant is
BD68_SETTERS = (("effect_set_bd68_1", 1), ("effect_set_bd68_2", 2), ("effect_set_bd68_3", 3))

# --- the two clamped adds -----------------------------------------------------------------------
CLAMPED_ADDS = (("effect_add4_clamped_b6fa", 4, b"\x58\x40"),    # addq.w #4,d0
                ("effect_add2_clamped_b6fa", 2, b"\x54\x40"))    # addq.w #2,d0

# The largest maximum the game sets itself ($b74a picks $18..$28 off the $bd70 thresholds), used as
# the fixed maximum the boundary sweep moves the RAISED value around.
METER_MAX_TYPICAL = 0x0028
# Where `value + amount` lands relative to that maximum. +1 is the first raise that must clamp, so a
# comparison LOOSENED by one (`> max+1`) reddens there and -1 catches one tightened by two. What no
# offset catches is the `bgt`'s strictness — `>= max` is `> max-1`, and at offset 0 that stores the
# maximum just as the strict compare does, so the two are indistinguishable from out here.
BOUNDARY_OFFSETS = (-4, -1, 0, 1, 4)

# (counter, maximum, does the clamp fire, why this case exists). These are the cases the meter's own
# range ($18..$28) cannot reach, and they are what makes the compare's SIGNEDNESS observable: an
# unsigned `bhi` would clamp in the first two and store in the third.
SIGNED_CLAMP_CASES = (
    (0x7ffe, 0x7fff, False, "the .w add wraps to a NEGATIVE raised value, which stores"),
    (0x8000, 0x7fff, False, "the most negative counter there is, raised"),
    (0xfff0, 0x0028, False, "a negative counter raised towards zero, still below the maximum"),
    (0x0010, 0xfff0, True, "a NEGATIVE maximum: the clamp fires and LOWERS the counter"),
    (0x0000, 0x0000, True, "a zero maximum: any raise is above it"),
)

# --- the record pushes --------------------------------------------------------------------------
PUSH_RECORDS = (("effect_push_record_0605", 0x0605), ("effect_push_record_0508", 0x0508),
                ("effect_push_record_0705", 0x0705), ("effect_push_record_0803", 0x0803))

# Write pointers to run each push from. The list the game itself uses starts at $b444 and runs up to
# the pointer at $b546 — including the value that makes the record land ON the pointer, which is a
# real reachable state (129 pushes with no intervening reset) and the one place the two stores of
# this routine interact.
# Taken from ../names.txt like every other address here (it is a `var`, not a function, but the same
# lookup applies) rather than restated, so a renamed or moved list fails at collection time.
RECORD_LIST_BASE = leaf.entry_of("effect_record_list")
PUSH_POINTERS = (
    RECORD_LIST_BASE,                        # the value the new-game reset ($fe4a) leaves
    RECORD_LIST_BASE + 0x40,                 # mid-list
    WRITE_PTR - RECORD_LEN,                  # the record lands on the pointer's own high word
    0x40000,                                 # nowhere near the list: nothing may be hardcoded
)

# --- the meter restore --------------------------------------------------------------------------
# (counter, maximum). It stores the maximum with no test at all, so a maximum BELOW the counter
# lowers it — the property that distinguishes this routine from the two clamped adds.
RESTORE_CASES = ((0x0010, 0x0028), (0x0028, 0x0010), (0xffff, 0x0000), (0x0000, 0xffff))


# --- entry-point pins ---------------------------------------------------------------------------

def _setter_entry(destination, immediate, abs_long):
    op = MOVE_W_IMM_ABS_L if abs_long else MOVE_W_IMM_ABS_W
    operand = longword(destination) if abs_long else word(destination)
    return op + word(immediate) + operand + RTS


def _clamped_entry(amount_opcode):
    """`move.w meter,d0 / addq.w #n,d0 / cmp.w max,d0 / bgt.w clamp / move.w d0,meter / rts` and
    then the clamp's own `move.w max,meter / rts` — all 38 bytes, since the branch target is part of
    what a reconstruction has to get right."""
    return (MOVE_W_ABS_L_D0 + longword(METER_VALUE)
            + amount_opcode
            + CMP_W_ABS_L_D0 + longword(METER_MAX)
            + BGT_W_OVER_THE_STORE
            + MOVE_W_D0_ABS_L + longword(METER_VALUE) + RTS
            + MOVE_W_ABS_L_ABS_L + longword(METER_MAX) + longword(METER_VALUE) + RTS)


ENTRY_BYTES = {}
ENTRY_BYTES.update({name: _setter_entry(dest, imm, abs_long)
                    for name, dest, imm, abs_long in WORD_SETTERS})
ENTRY_BYTES.update({
    name: (MOVE_W_IMM_ABS_W + word(STATE_21E4_STAMP) + word(STATE_21E4)
           + MOVE_W_IMM_ABS_L + word(variant) + longword(STATE_BD68) + RTS)
    for name, variant in BD68_SETTERS})
ENTRY_BYTES.update({name: _clamped_entry(opcode) for name, _amount, opcode in CLAMPED_ADDS})
ENTRY_BYTES.update({
    name: (ADDQ_L_2_ABS_L + longword(WRITE_PTR) + MOVEA_L_ABS_L_A1 + longword(WRITE_PTR)
           + MOVE_W_IMM_A1 + word(record) + RTS)
    for name, record in PUSH_RECORDS})
ENTRY_BYTES["effect_restore_b6fa_to_max"] = (MOVE_W_ABS_L_ABS_L + longword(METER_MAX)
                                             + longword(METER_VALUE) + RTS)

# The batch this file was written for. Recorded rather than derived from ENTRY_BYTES, so that a
# routine dropped from a table shrinks the battery loudly instead of silently.
EFFECT_LEAF_COUNT = 29

GLUE = {name: leaf.image_glue(name) for name in ENTRY_BYTES}


def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, EFFECT_LEAF_COUNT)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_an_entry_is_the_instruction_this_battery_reconstructs(name):
    """One assert per routine covering four things at once: the address ../names.txt gives it, the
    global include/wonderboy.h gives that address, the immediate, and the operand size."""
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


# --- the setters --------------------------------------------------------------------------------

# Each case below asserts on the word the original left as well as on the diff, which is what makes
# it say WHICH value it expects rather than only "both sides agree" — a table whose immediate
# drifted would otherwise stay green while testing something else. `leaf.read_int` takes that word
# out of the oracle's write set (and fails if the original never wrote it).

@pytest.mark.parametrize("seed", SEED_WORDS, ids=[f"was_{s:04x}" for s in SEED_WORDS])
@pytest.mark.parametrize("name,dest,imm,_abs_long", WORD_SETTERS, ids=[s[0] for s in WORD_SETTERS])
def test_a_word_setter_writes_its_word_and_nothing_else(name, dest, imm, _abs_long, seed):
    what = f"{name} over a destination holding {seed:#06x}"
    info = leaf.run(name, GLUE[name], [(dest, WORD_LEN)], what, regs={"_pokes": {dest: word(seed)}})
    assert leaf.read_int(info, dest, WORD_LEN, what) == imm, f"{what}: not the {imm:#06x} it is named for"


@pytest.mark.parametrize("seed", SEED_WORDS, ids=[f"was_{s:04x}" for s in SEED_WORDS])
@pytest.mark.parametrize("name,variant", BD68_SETTERS, ids=[s[0] for s in BD68_SETTERS])
def test_the_bd68_trio_stamps_both_words(name, variant, seed):
    """Both destinations are seeded, and independently: a port that wrote only the variant, or
    stamped $21e4 with the variant instead of with its own constant, differs on one of them."""
    pokes = {STATE_21E4: word(seed), STATE_BD68: word(seed ^ WORD_MASK)}
    what = f"{name} (variant {variant}) over destinations holding {seed:#06x}"
    info = leaf.run(name, GLUE[name], [(STATE_21E4, WORD_LEN), (STATE_BD68, WORD_LEN)], what,
                    regs={"_pokes": pokes})
    assert leaf.read_int(info, STATE_21E4, WORD_LEN, what) == STATE_21E4_STAMP, f"{what}: wrong stamp"
    assert leaf.read_int(info, STATE_BD68, WORD_LEN, what) == variant, f"{what}: wrong variant"


# --- the clamps ---------------------------------------------------------------------------------

def _run_meter_case(name, value, maximum, what, expected):
    pokes = {METER_VALUE: word(value), METER_MAX: word(maximum)}
    info = leaf.run(name, GLUE[name], [(METER_VALUE, WORD_LEN)], what, regs={"_pokes": pokes})
    ended_at = leaf.read_int(info, METER_VALUE, WORD_LEN, what)
    assert ended_at == expected & WORD_MASK, (
        f"{what}: the meter ended at {ended_at:#06x}, not the {expected & WORD_MASK:#06x} this case "
        f"was written to reach")


@pytest.mark.parametrize("offset", BOUNDARY_OFFSETS)
@pytest.mark.parametrize("name,amount,_opcode", CLAMPED_ADDS, ids=[c[0] for c in CLAMPED_ADDS])
def test_a_clamped_add_stops_exactly_at_the_maximum(name, amount, _opcode, offset):
    """`offset` is where `counter + amount` lands relative to the maximum. +1 is the first raise
    that clamps, so the sweep pins the comparison against a shifted one rather than only its
    neighbourhood — but not against a non-strict one, which stores the same word here (see
    BOUNDARY_OFFSETS)."""
    clamps = offset > 0
    _run_meter_case(name, METER_MAX_TYPICAL + offset - amount, METER_MAX_TYPICAL,
                    f"{name} with the raise landing {offset:+d} from the maximum "
                    f"({'clamps' if clamps else 'stores'})",
                    METER_MAX_TYPICAL if clamps else METER_MAX_TYPICAL + offset)


@pytest.mark.parametrize("value,maximum,clamps,why", SIGNED_CLAMP_CASES,
                         ids=[f"{c[0]:04x}_max{c[1]:04x}" for c in SIGNED_CLAMP_CASES])
@pytest.mark.parametrize("name,amount,_opcode", CLAMPED_ADDS, ids=[c[0] for c in CLAMPED_ADDS])
def test_a_clamped_add_compares_signed_and_adds_in_16_bits(name, amount, _opcode,
                                                           value, maximum, clamps, why):
    _run_meter_case(name, value, maximum, f"{name}: {why}",
                    maximum if clamps else value + amount)


def test_the_clamp_battery_reaches_both_branches():
    """A sweep that only ever clamped would still be green, and would pin half the routine."""
    branches = {offset > 0 for offset in BOUNDARY_OFFSETS} | {c[2] for c in SIGNED_CLAMP_CASES}
    assert branches == {False, True}, (
        f"the clamp cases take only the {'clamp' if True in branches else 'store'} branch")


@pytest.mark.parametrize("value,maximum", RESTORE_CASES,
                         ids=[f"{v:04x}_max{m:04x}" for v, m in RESTORE_CASES])
def test_the_restore_stores_the_maximum_whichever_way_it_moves_the_meter(value, maximum):
    _run_meter_case("effect_restore_b6fa_to_max", value, maximum,
                    f"restore with the meter at {value:#06x} and the maximum {maximum:#06x}",
                    maximum)


# --- the record pushes --------------------------------------------------------------------------

def _word_after_pokes(pokes, addr):
    """The word at `addr` in the image the case will run on — built by the same call the run makes,
    so it cannot disagree with what the oracle and the reconstruction actually see."""
    return int.from_bytes(harness.make_image(pokes)[addr:addr + RECORD_LEN], "big")


@pytest.mark.parametrize("pointer", PUSH_POINTERS, ids=[f"ptr_{p:05x}" for p in PUSH_POINTERS])
@pytest.mark.parametrize("name,record", PUSH_RECORDS, ids=[p[0] for p in PUSH_RECORDS])
def test_a_push_advances_the_pointer_then_stores_at_it(name, record, pointer):
    """These are the one battery here that runs WITHOUT the kit's poison pass: the output includes
    the write pointer itself, and inverting an address the run then stores through would send the
    oracle at an odd (or off-image) destination and take an address error instead of a case. The
    attribution it buys is done by hand instead — the destination word is seeded to the record's own
    complement, so a reconstruction that advanced the pointer without storing still diverges.
    """
    destination = pointer + RECORD_LEN
    pokes = {WRITE_PTR: longword(pointer)}
    # The pointer's seed may BE the destination (the `WRITE_PTR - RECORD_LEN` case), in which case
    # it is already the complement's job: two pokes at one address would silently drop one.
    if not WRITE_PTR <= destination < WRITE_PTR + WRITE_PTR_LEN:
        pokes[destination] = word(record ^ WORD_MASK)
    assert _word_after_pokes(pokes, destination) != record, (
        f"{name}'s destination {destination:#x} already holds {record:#06x} before the call — the "
        f"case could pass without the store happening at all")
    leaf.run(name, GLUE[name], [(WRITE_PTR, WRITE_PTR_LEN), (destination, RECORD_LEN)],
             f"{name} with the write pointer at {pointer:#x}",
             regs={"_pokes": pokes}, poison=False)
