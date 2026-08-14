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
from leaf import (A1, BSET_IMM, MOVE_W_ABS_L_ABS_L, MOVE_W_ABS_L_D0, MOVE_W_D0_ABS_L,
                  MOVE_W_IMM_ABS_L, RTS, bit_op_d16, longword, word)
from layout import wb

# --- the globals, from the header both languages read (include/wonderboy.h) ---------------------
SLOT_CHANGED = wb("HUD_SLOT_CHANGED")     # include/effects.h; every other constant here is
SLOT_REARM = wb("HUD_SLOT_REARM")         # include/wonderboy.h's
BYTE_MASK = 0xff
SLOT_VALUE_SHIFT = 8                      # a slot is {value, changed}: the value in the HIGH byte
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
# test_hud.py also spells (RTS and the four `move.w` forms) are imported from leaf.py above, so the
# two batteries cannot disagree about them; these are the ones only this file needs.
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


def test_the_two_headers_spell_one_slot_byte():
    """WB_HUD_SLOT_CHANGED (include/effects.h) and the low byte of WB_HUD_SLOT_REARM
    (include/wonderboy.h) are the SAME byte of the same word: the "redraw me" flag every writer of a
    HUD slot stamps below the value. The setters here compose it (`value << 8 | changed`) and the
    two damage paths in src/actor.c write the whole word with a value of zero, so the two headers
    hold two spellings of it and C cannot derive either from the other — the scraper reads plain
    literals, and a `#define` built from another one would drop out of layout.py entirely. This is
    the pin that stands in for that derivation: change one and the other has to follow."""
    assert SLOT_REARM & BYTE_MASK == SLOT_CHANGED, (
        f"WB_HUD_SLOT_REARM is {SLOT_REARM:#06x}, whose low byte is not the "
        f"{SLOT_CHANGED:#04x} WB_HUD_SLOT_CHANGED gives")
    assert SLOT_REARM >> SLOT_VALUE_SHIFT == 0, (
        f"WB_HUD_SLOT_REARM is {SLOT_REARM:#06x}, so the rearm no longer puts the slot's VALUE "
        f"back to zero — which is what the damage paths' `move.w #$ff,slot.l` means")


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


# --- the PICKUP effects, $105e4..$10799 (batch 38) -----------------------------------------------
#
# FOURTEEN more leaves of the same kind, behind WB_PICKUP_EFFECT_TABLE rather than
# WB_EFFECT_HANDLER_TABLE. They are in THIS battery and not in test_behavior.py for the reason
# src/effects.c gives for holding them: they are straight-line leaves whose whole surface is a word
# or two of game state, four of them are the record pushes above with a message on the end, and the
# seeding they need is this file's (a destination to overwrite, a write pointer, a meter either side
# of its maximum) and not the behaviour tier's actor record. Slot 38's own frame — the dispatch that
# reaches them, and the refusal when its index leaves the table — is test_behavior.py's.
#
# WHAT IS NEW HERE IS THE TAIL, and it is what every case below asserts on top of the grant: a
# message id into TEXT_REQUEST and the VALUE TEXT_LIFETIME_DEFAULT into TEXT_LIFETIME_REQUEST
# beside it. Three handlers post
# TEXT_REQUEST_NONE, which is not "no write" — it is a write of zero, and it CANCELS whatever slot
# 38's score arm posted a moment earlier. The cases seed that byte nonzero so the zero is visible.
TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")
TEXT_REQUEST_NONE = wb("TEXT_REQUEST_NONE")
BYTE_LEN = 1
PANEL_FRAME_DELAY = wb("PANEL_FRAME_DELAY")
PANEL_FRAME_DELAY_INIT = wb("PANEL_FRAME_DELAY_INIT")
PICKUP_METER_STEP = wb("PICKUP_METER_STEP")
EFFECT_RECORD_LIST = wb("EFFECT_RECORD_LIST")
ATTACK_LEVEL_MAX = wb("ATTACK_LEVEL_MAX")
SCENE_EXIT_REQUEST = wb("SCENE_EXIT_REQUEST")
SCENE_EXIT_REQUESTED = wb("SCENE_EXIT_REQUESTED")
STATE_FLAG_A32 = wb("STATE_FLAG_A32")
FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
FOLLOWED_A32 = wb("ACTOR_FOLLOWED_A32")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
ACTOR_FLAGS2 = wb("ACTOR_FLAGS2")
FLICKER_COUNTDOWN = wb("ACTOR_FLICKER_COUNTDOWN")
FLICKER_BIT = wb("ACTOR_FLAG_FLICKER_BIT")
INVULNERABLE_BIT = wb("ACTOR_FLAGS2_INVULNERABLE_BIT")
VANISH_FLICKER = wb("PICKUP_VANISH_FLICKER")

# The encodings only the pickup handlers spell.
CMPI_B_ABS_L = b"\x0c\x39"          # cmpi.b #imm,<abs>.l
ADDQ_B_1_ABS_L = b"\x52\x39"        # addq.b #1,<abs>.l
JSR_ABS_W = b"\x4e\xb8"             # jsr <abs>.w — the SHORT form, batch 31's hiding place
ADDQ_W_4_D0 = b"\x58\x40"
# `bgt.w` over the one `move.w d0,meter` the raise would otherwise store (6 bytes), and over the
# bump plus the whole message post (6 + 8 + 8 = 22). Both are transcriptions of the displacement
# word in the image, which is what makes the entry pin a pin.
BGT_W_OVER_THE_RAISE = b"\x6e\x00\x00\x08"
BGT_W_OVER_THE_BUMP = b"\x6e\x00\x00\x18"

# (name, slot address, the VALUE byte, the message id). The five grants that write one HUD slot.
PICKUP_GRANTS = (
    ("pickup_effect_grant_bbc4", wb("HUD_SLOT_BBC4"), wb("PICKUP_SLOT_BBC4_VALUE"),
     TEXT_REQUEST_NONE),
    ("pickup_effect_grant_wing_boots", HUD_SLOT_BBC2, wb("PICKUP_SLOT_WING_BOOTS_VALUE"),
     wb("TEXT_MESSAGE_WING_BOOTS")),
    ("pickup_effect_grant_helmet", HUD_SLOT_BBBE, wb("PICKUP_SLOT_HELMET_VALUE"),
     wb("TEXT_MESSAGE_HELMET")),
    ("pickup_effect_grant_gauntlet", HUD_SLOT_BBC0, wb("PICKUP_SLOT_GAUNTLET_VALUE"),
     wb("TEXT_MESSAGE_GAUNTLET")),
    ("pickup_effect_grant_revival", HUD_SLOT_BBC6, wb("PICKUP_SLOT_REVIVAL_VALUE"),
     wb("TEXT_MESSAGE_REVIVAL")),
)

# ...and the four that push a record. The words are the SAME four `effect_push_record_*` pushes,
# which is what says the two dispatch tables grant the same four items; PUSH_RECORDS above holds
# them as literals and this table reads the header, so the two spellings are pinned against each
# other by `test_the_two_tables_push_the_same_four_records`.
PICKUP_APPENDS = (
    ("pickup_effect_grant_fire_balls", wb("PICKUP_RECORD_FIRE_BALLS"), wb("TEXT_MESSAGE_FIRE_BALLS")),
    ("pickup_effect_grant_bombs", wb("PICKUP_RECORD_BOMBS"), wb("TEXT_MESSAGE_BOMBS")),
    ("pickup_effect_grant_wind_spouts", wb("PICKUP_RECORD_WIND_SPOUTS"),
     wb("TEXT_MESSAGE_WIND_SPOUTS")),
    ("pickup_effect_grant_lightning", wb("PICKUP_RECORD_LIGHTNING"), wb("TEXT_MESSAGE_LIGHTNING")),
)

PICKUP_LEAF_COUNT = 14                 # the table's own entry count, checked against the header


def _post(message):
    """`move.b #id,$c030.l / move.w #$32,$c034.l` — the tail thirteen of the fourteen end with."""
    return (leaf.move_b_imm_abs_l(message, TEXT_REQUEST)
            + MOVE_W_IMM_ABS_L + word(TEXT_LIFETIME_DEFAULT) + longword(TEXT_LIFETIME_REQUEST))


PICKUP_ENTRY_BYTES = {"pickup_effect_none": RTS}
PICKUP_ENTRY_BYTES.update({
    name: (MOVE_W_IMM_ABS_L + word((value << SLOT_VALUE_SHIFT) | SLOT_CHANGED) + longword(slot)
           + _post(message) + RTS)
    for name, slot, value, message in PICKUP_GRANTS})
PICKUP_ENTRY_BYTES.update({
    name: (ADDQ_L_2_ABS_L + longword(WRITE_PTR) + MOVEA_L_ABS_L_A1 + longword(WRITE_PTR)
           + MOVE_W_IMM_A1 + word(record) + _post(message) + RTS)
    for name, record, message in PICKUP_APPENDS})
PICKUP_ENTRY_BYTES["pickup_effect_refill_meter"] = (
    MOVE_W_IMM_ABS_L + word(PANEL_FRAME_DELAY_INIT) + longword(PANEL_FRAME_DELAY)
    + MOVE_W_ABS_L_ABS_L + longword(METER_MAX) + longword(METER_VALUE)
    + _post(TEXT_REQUEST_NONE) + RTS)
PICKUP_ENTRY_BYTES["pickup_effect_add4_meter"] = (
    MOVE_W_IMM_ABS_L + word(PANEL_FRAME_DELAY_INIT) + longword(PANEL_FRAME_DELAY)
    + MOVE_W_ABS_L_D0 + longword(METER_VALUE) + ADDQ_W_4_D0
    + CMP_W_ABS_L_D0 + longword(METER_MAX) + BGT_W_OVER_THE_RAISE
    + MOVE_W_D0_ABS_L + longword(METER_VALUE)
    + _post(TEXT_REQUEST_NONE) + RTS)
PICKUP_ENTRY_BYTES["pickup_effect_bump_attack_level"] = (
    CMPI_B_ABS_L + word(ATTACK_LEVEL_MAX) + longword(EFFECT_RECORD_LIST) + BGT_W_OVER_THE_BUMP
    + ADDQ_B_1_ABS_L + longword(EFFECT_RECORD_LIST)
    + _post(wb("TEXT_MESSAGE_ATTACK_UP"))
    + MOVE_W_IMM_ABS_L + word(SCENE_EXIT_REQUESTED) + longword(SCENE_EXIT_REQUEST) + RTS)
PICKUP_ENTRY_BYTES["pickup_effect_vanish_followed"] = (
    JSR_ABS_W + word(leaf.entry_of("followed_actor_record"))
    + leaf.move_b_imm_d16(A1, VANISH_FLICKER, FLICKER_COUNTDOWN)
    + bit_op_d16(BSET_IMM, FLICKER_BIT, A1, ACTOR_FLAGS)
    + bit_op_d16(BSET_IMM, INVULNERABLE_BIT, A1, ACTOR_FLAGS2)
    + _post(wb("TEXT_MESSAGE_VANISHED")) + RTS)

PICKUP_GLUE = {name: leaf.image_glue(name) for name in PICKUP_ENTRY_BYTES}

# The image's own table, so the count and the entry addresses come from the bytes rather than from
# this file. wonderboy.h's fourteen WB_PICKUP_EFFECT_* addresses are checked against it below.
PICKUP_TABLE = wb("PICKUP_EFFECT_TABLE")
PICKUP_ENTRY = wb("PICKUP_EFFECT_ENTRY")
PICKUP_ENTRIES = wb("PICKUP_EFFECT_ENTRIES")

# The order the table holds them in — the same order the two tables above and the two singletons
# were written in, stated once so the table pin and the batch-completeness pin share it.
PICKUP_TABLE_ORDER = (("pickup_effect_none",)
                      + tuple(row[0] for row in PICKUP_GRANTS)
                      + tuple(row[0] for row in PICKUP_APPENDS)
                      + ("pickup_effect_refill_meter", "pickup_effect_add4_meter",
                         "pickup_effect_bump_attack_level", "pickup_effect_vanish_followed"))

# The seed every pickup case starts from: a TEXT_REQUEST and a lifetime that are not what any
# handler writes, so a handler that posted nothing would be caught by the byte it left behind.
POSTED_BEFORE = 0x7f
LIFETIME_BEFORE = 0x1234


def _pickup_pokes(extra=None):
    pokes = {TEXT_REQUEST: bytes([POSTED_BEFORE]), TEXT_LIFETIME_REQUEST: word(LIFETIME_BEFORE)}
    return leaf.overlay(pokes, extra or {})


def _post_band():
    return [(TEXT_REQUEST, BYTE_LEN), (TEXT_LIFETIME_REQUEST, WORD_LEN)]


def _assert_posted(info, message, what):
    assert leaf.read_int(info, TEXT_REQUEST, BYTE_LEN, what) == message, (
        f"{what}: the message posted is not the {message:#04x} this handler is named for")
    assert leaf.read_int(info, TEXT_LIFETIME_REQUEST, WORD_LEN, what) == TEXT_LIFETIME_DEFAULT, (
        f"{what}: the lifetime posted is not WB_TEXT_LIFETIME_DEFAULT")


def test_this_file_covers_the_whole_pickup_table():
    leaf.assert_batch_is_complete(PICKUP_ENTRY_BYTES, PICKUP_LEAF_COUNT)
    assert PICKUP_LEAF_COUNT == PICKUP_ENTRIES, (
        f"the header says the table has {PICKUP_ENTRIES} entries and this battery covers "
        f"{PICKUP_LEAF_COUNT}")


@pytest.mark.parametrize("name", sorted(PICKUP_ENTRY_BYTES), ids=sorted(PICKUP_ENTRY_BYTES))
def test_a_pickup_entry_is_the_instructions_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, PICKUP_ENTRY_BYTES[name])


def test_the_table_holds_these_fourteen_addresses_in_this_order():
    """The pin that ties the whole batch together: the image's own fourteen longwords are the
    fourteen addresses ../names.txt gives these routines, in the order this file lists them — and
    the entry immediately past the last is the byte the table's own slot 0 names, which is what
    BOUNDS it (WB_EFFECT_HANDLER_TABLE's own rule, one table over)."""
    image = bytes(harness.BASE_IMAGE)
    held = [int.from_bytes(image[PICKUP_TABLE + row * PICKUP_ENTRY:
                                 PICKUP_TABLE + (row + 1) * PICKUP_ENTRY], "big")
            for row in range(PICKUP_ENTRIES)]
    assert held == [leaf.entry_of(name) for name in PICKUP_TABLE_ORDER], (
        f"the table holds {[hex(a) for a in held]}")
    assert held[0] == PICKUP_TABLE + PICKUP_ENTRIES * PICKUP_ENTRY, (
        "slot 0 no longer holds the byte past the table, so nothing bounds it")


def test_the_two_tables_push_the_same_four_records():
    """PUSH_RECORDS transcribes the four words out of $10394..$103db and PICKUP_APPENDS reads them
    from include/wonderboy.h, where src/effects.c's two spellings now share one #define. That the
    two dispatch tables grant the SAME four items is a claim about the image, so it is checked
    against both sets of bytes rather than asserted in prose."""
    assert [record for _n, record in PUSH_RECORDS] == [record for _n, record, _m in PICKUP_APPENDS]


def test_the_bare_rts_writes_nothing_at_all():
    """Slot 0's handler, and the byte that bounds the table. It is the one entry whose ANSWER to a
    legal index is "nothing happened", which is what makes it different from the refusal
    test_behavior.py drives for an index outside the table."""
    leaf.run("pickup_effect_none", PICKUP_GLUE["pickup_effect_none"], [], "pickup_effect_none",
             regs={"_pokes": _pickup_pokes()})


@pytest.mark.parametrize("seed", SEED_WORDS, ids=[f"was_{s:04x}" for s in SEED_WORDS])
@pytest.mark.parametrize("name,slot,value,message", PICKUP_GRANTS, ids=[g[0] for g in PICKUP_GRANTS])
def test_a_pickup_grant_writes_its_slot_and_posts_its_message(name, slot, value, message, seed):
    what = f"{name} over a slot holding {seed:#06x}"
    info = leaf.run(name, PICKUP_GLUE[name], [(slot, WORD_LEN)] + _post_band(), what,
                    regs={"_pokes": _pickup_pokes({slot: word(seed)})})
    assert leaf.read_int(info, slot, WORD_LEN, what) == (value << SLOT_VALUE_SHIFT) | SLOT_CHANGED, (
        f"{what}: the slot is not the {value:#04x} with WB_HUD_SLOT_CHANGED below it")
    _assert_posted(info, message, what)


@pytest.mark.parametrize("pointer", PUSH_POINTERS, ids=[f"ptr_{p:05x}" for p in PUSH_POINTERS])
@pytest.mark.parametrize("name,record,message", PICKUP_APPENDS, ids=[a[0] for a in PICKUP_APPENDS])
def test_a_pickup_append_pushes_its_record_and_posts_its_message(name, record, message, pointer):
    """The push half is `effect_push_record`'s own three instructions, so the same four pointers
    drive it — including the one that makes the record land ON the pointer. `poison=False` for that
    battery's reason: the output includes the pointer the run then stores through."""
    destination = pointer + RECORD_LEN
    pokes = {WRITE_PTR: longword(pointer)}
    if not WRITE_PTR <= destination < WRITE_PTR + WRITE_PTR_LEN:
        pokes[destination] = word(record ^ WORD_MASK)
    what = f"{name} with the write pointer at {pointer:#x}"
    assert _word_after_pokes(_pickup_pokes(pokes), destination) != record, (
        f"{what}: the destination already holds the record before the call")

    info = leaf.run(name, PICKUP_GLUE[name],
                    [(WRITE_PTR, WRITE_PTR_LEN), (destination, RECORD_LEN)] + _post_band(), what,
                    regs={"_pokes": _pickup_pokes(pokes)}, poison=False)
    _assert_posted(info, message, what)


@pytest.mark.parametrize("value,maximum", RESTORE_CASES,
                         ids=[f"{v:04x}_max{m:04x}" for v, m in RESTORE_CASES])
def test_the_pickup_refill_stores_the_maximum_and_restarts_the_panel(value, maximum):
    """`effect_restore_b6fa_to_max`'s one instruction with WB_PANEL_FRAME_DELAY restarted above it —
    so the same four cases drive it, and the panel word is asserted on top."""
    what = f"pickup_effect_refill_meter with the meter at {value:#06x} and the maximum {maximum:#06x}"
    pokes = {METER_VALUE: word(value), METER_MAX: word(maximum),
             PANEL_FRAME_DELAY: word(PANEL_FRAME_DELAY_INIT ^ WORD_MASK)}
    info = leaf.run("pickup_effect_refill_meter", PICKUP_GLUE["pickup_effect_refill_meter"],
                    [(METER_VALUE, WORD_LEN), (PANEL_FRAME_DELAY, WORD_LEN)] + _post_band(), what,
                    regs={"_pokes": _pickup_pokes(pokes)})
    assert leaf.read_int(info, METER_VALUE, WORD_LEN, what) == maximum, f"{what}: not the maximum"
    assert leaf.read_int(info, PANEL_FRAME_DELAY, WORD_LEN, what) == PANEL_FRAME_DELAY_INIT, (
        f"{what}: the panel countdown was not restarted")
    _assert_posted(info, TEXT_REQUEST_NONE, what)


# Where `meter + 4` lands relative to the maximum, and what the meter ends at. THIS IS THE HANDLER'S
# WHOLE POINT: above the maximum it stores NOTHING, where `effect_add4_clamped_b6fa` stores the
# maximum — so the two routines part exactly on the offsets that clamp, and a case that only swept
# below the boundary would pass for either of them.
ADD4_OFFSETS = (-4, -1, 0, 1, 4)


@pytest.mark.parametrize("offset", ADD4_OFFSETS)
def test_the_pickup_add4_SKIPS_the_store_instead_of_clamping(offset):
    value = METER_MAX_TYPICAL + offset - PICKUP_METER_STEP
    raised = offset <= 0
    what = (f"pickup_effect_add4_meter with the raise landing {offset:+d} from the maximum "
            f"({'stores' if raised else 'skips'})")
    pokes = {METER_VALUE: word(value), METER_MAX: word(METER_MAX_TYPICAL),
             PANEL_FRAME_DELAY: word(PANEL_FRAME_DELAY_INIT ^ WORD_MASK)}
    info = leaf.run("pickup_effect_add4_meter", PICKUP_GLUE["pickup_effect_add4_meter"],
                    [(METER_VALUE, WORD_LEN), (PANEL_FRAME_DELAY, WORD_LEN)] + _post_band(), what,
                    regs={"_pokes": _pickup_pokes(pokes)})
    if raised:
        assert leaf.read_int(info, METER_VALUE, WORD_LEN, what) == METER_MAX_TYPICAL + offset, what
    else:
        # THE WHOLE POINT, and it has to be an ABSENCE: the sibling would have written the maximum
        # here, so a case that only compared the meter's final value against the image would pass
        # for either routine. What separates them is that this one does not write the word at all.
        assert METER_VALUE not in info["writes"], (
            f"{what}: the meter was written — a CLAMP, not the skip this handler ships")
    _assert_posted(info, TEXT_REQUEST_NONE, what)


@pytest.mark.parametrize("value,maximum,clamps,why", SIGNED_CLAMP_CASES,
                         ids=[f"{c[0]:04x}_max{c[1]:04x}" for c in SIGNED_CLAMP_CASES])
def test_the_pickup_add4_compares_signed_and_adds_in_16_bits(value, maximum, clamps, why):
    """The same five seeds SIGNED_CLAMP_CASES drives its sibling with, and the answers differ on
    exactly the two rows the `clamps` column marks: there the sibling STORES the maximum and this
    handler stores nothing at all, so the meter is left where the case seeded it."""
    what = f"pickup_effect_add4_meter: {why}"
    pokes = {METER_VALUE: word(value), METER_MAX: word(maximum),
             PANEL_FRAME_DELAY: word(PANEL_FRAME_DELAY_INIT ^ WORD_MASK)}
    info = leaf.run("pickup_effect_add4_meter", PICKUP_GLUE["pickup_effect_add4_meter"],
                    [(METER_VALUE, WORD_LEN), (PANEL_FRAME_DELAY, WORD_LEN)] + _post_band(), what,
                    regs={"_pokes": _pickup_pokes(pokes)})
    if clamps:
        assert METER_VALUE not in info["writes"], f"{what}: the meter was written"
    else:
        assert leaf.read_int(info, METER_VALUE, WORD_LEN, what) == (
            (value + PICKUP_METER_STEP) & WORD_MASK), what
    _assert_posted(info, TEXT_REQUEST_NONE, what)


# The attack level, on both sides of its own boundary and past the SIGN. $ff is what the new-game
# reset leaves in this byte (the high half of WB_EFFECT_RECORD_EMPTY), and it is NEGATIVE — so it
# bumps, and one bump turns the list's "empty" word from $ffff into $00ff.
ATTACK_LEVELS = (0x00, ATTACK_LEVEL_MAX - 1, ATTACK_LEVEL_MAX, ATTACK_LEVEL_MAX + 1, 0x7f, 0xff)


@pytest.mark.parametrize("level", ATTACK_LEVELS, ids=[f"level_{v:02x}" for v in ATTACK_LEVELS])
def test_the_attack_bump_is_signed_and_raises_the_exit_request_either_way(level):
    """Two properties in one sweep. The compare is SIGNED, so $7f refuses and $ff bumps; and
    WB_SCENE_EXIT_REQUEST is raised BELOW the join, so the refused arm raises it too."""
    bumps = level <= ATTACK_LEVEL_MAX or level >= 0x80
    what = f"pickup_effect_bump_attack_level at {level:#04x} ({'bumps' if bumps else 'refuses'})"
    pokes = {EFFECT_RECORD_LIST: bytes([level]),
             SCENE_EXIT_REQUEST: word(SCENE_EXIT_REQUESTED ^ WORD_MASK)}
    allowed = [(EFFECT_RECORD_LIST, BYTE_LEN), (SCENE_EXIT_REQUEST, WORD_LEN)] + _post_band()
    info = leaf.run("pickup_effect_bump_attack_level",
                    PICKUP_GLUE["pickup_effect_bump_attack_level"], allowed, what,
                    regs={"_pokes": _pickup_pokes(pokes)})

    assert leaf.read_int(info, SCENE_EXIT_REQUEST, WORD_LEN, what) == SCENE_EXIT_REQUESTED, (
        f"{what}: the exit request was not raised")
    if bumps:
        assert leaf.read_int(info, EFFECT_RECORD_LIST, BYTE_LEN, what) == (level + 1) & BYTE_MASK
        _assert_posted(info, wb("TEXT_MESSAGE_ATTACK_UP"), what)
    else:
        assert EFFECT_RECORD_LIST not in info["writes"], (
            f"{what}: the level was bumped past WB_ATTACK_LEVEL_MAX")
        assert TEXT_REQUEST not in info["writes"] and TEXT_LIFETIME_REQUEST not in info["writes"], (
            f"{what}: a message was posted on the refused arm")


def test_the_attack_bump_reaches_both_arms():
    """A sweep that only ever bumped would pin neither the compare nor the join below it."""
    assert {level <= ATTACK_LEVEL_MAX or level >= 0x80 for level in ATTACK_LEVELS} == {False, True}


@pytest.mark.parametrize("a32", [0, 1], ids=["followed_default", "followed_a32"])
def test_the_vanish_grant_writes_the_followed_record_whichever_table_is_live(a32):
    """The one handler here with a CALLEE, and its `jsr $67e0.w` is the SHORT absolute form. What it
    writes is $69fe's damage-flicker state at its maximum — the countdown full, the flicker bit that
    makes the projection publish no sprite, and the invulnerable bit that makes $69fe decline to
    damage the record at all. The message the same routine posts is "Vanished !".

    Driving both values of WB_STATE_FLAG_A32 is what says the record's address comes out of
    `followed_actor_record` and is not the constant one table would make it look like."""
    followed = FOLLOWED_A32 if a32 else FOLLOWED_DEFAULT
    what = f"pickup_effect_vanish_followed with the A32 table {'live' if a32 else 'idle'}"
    pokes = {STATE_FLAG_A32: word(a32),
             followed + FLICKER_COUNTDOWN: bytes([VANISH_FLICKER ^ BYTE_MASK]),
             followed + ACTOR_FLAGS: bytes([0]), followed + ACTOR_FLAGS2: bytes([0])}
    allowed = [(followed + FLICKER_COUNTDOWN, BYTE_LEN), (followed + ACTOR_FLAGS, BYTE_LEN),
               (followed + ACTOR_FLAGS2, BYTE_LEN)] + _post_band()
    info = leaf.run("pickup_effect_vanish_followed", PICKUP_GLUE["pickup_effect_vanish_followed"],
                    allowed, what, regs={"_pokes": _pickup_pokes(pokes)})

    assert leaf.read_int(info, followed + FLICKER_COUNTDOWN, BYTE_LEN, what) == VANISH_FLICKER
    assert leaf.read_int(info, followed + ACTOR_FLAGS, BYTE_LEN, what) == 1 << FLICKER_BIT
    assert leaf.read_int(info, followed + ACTOR_FLAGS2, BYTE_LEN, what) == 1 << INVULNERABLE_BIT
    _assert_posted(info, wb("TEXT_MESSAGE_VANISHED"), what)


def test_the_vanish_grant_ORs_its_two_bits_into_whatever_the_record_carried():
    """`bset` is a read-modify-write, so a record that was already carrying other flags keeps them —
    which a port that stored the bit alone would not. Seeded with the complement of each bit."""
    what = "pickup_effect_vanish_followed over a record carrying every other flag"
    flags, flags2 = 0xff ^ (1 << FLICKER_BIT), 0xff ^ (1 << INVULNERABLE_BIT)
    pokes = {STATE_FLAG_A32: word(0),
             FOLLOWED_DEFAULT + FLICKER_COUNTDOWN: bytes([0]),
             FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([flags]),
             FOLLOWED_DEFAULT + ACTOR_FLAGS2: bytes([flags2])}
    allowed = [(FOLLOWED_DEFAULT + FLICKER_COUNTDOWN, BYTE_LEN),
               (FOLLOWED_DEFAULT + ACTOR_FLAGS, BYTE_LEN),
               (FOLLOWED_DEFAULT + ACTOR_FLAGS2, BYTE_LEN)] + _post_band()
    info = leaf.run("pickup_effect_vanish_followed", PICKUP_GLUE["pickup_effect_vanish_followed"],
                    allowed, what, regs={"_pokes": _pickup_pokes(pokes)})
    assert leaf.read_int(info, FOLLOWED_DEFAULT + ACTOR_FLAGS, BYTE_LEN, what) == 0xff
    assert leaf.read_int(info, FOLLOWED_DEFAULT + ACTOR_FLAGS2, BYTE_LEN, what) == 0xff
