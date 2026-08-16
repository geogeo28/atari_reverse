"""Differential test for src/player.c — the player's own frame, below behaviour slot 1.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and states (or bounds) the original's write set.

WHAT SHAPES THIS BATTERY, and it is not what shaped test_behavior.py's.

  * NOTHING HERE IS A DISPATCH ROW. These eight routines are reached by `bsr` from
    `actor_behavior_type01_player` ($a38) and from each other, so a case enters each at its own
    address with the record in a0 — the leaf convention, not the handler one. The census behind that
    claim is a case of its own: six of the eight are named by exactly ONE instruction in the whole
    image, and two by two each — `player_reset_ground_state` (both sites inside the walk) and
    `player_stage_transition` (the frame's own last `bsr`, and the gate's at $bb0).
  * THE MAP AND THE ACTOR TABLE ARE REACHED, and only since batch 40 phase B. The walk ($ec8) has
    SIX map-probe sites — a left/right pair in each of the three sections that move the record, of
    which up to THREE can fire in one frame — and the weapon ($1208) allocates out of the high pool.
    So the seeding below is in
    three parts: a record and a handful of globals for the five phase-A routines, `map_pokes` from
    the battery that owns the probes with the probed rows cleared, and a keyed high pool with its
    free markers. Everything above the walk's section still seeds none of it.
  * THE PROGRAM'S OWN DATA IS SEEDED TOO, and only since batch 40 phase C. `player_stage_transition`
    reads four cursors, four frame tables and three 88-byte posture records out of the 466 bytes
    above its own body, and the eight bytes of ladder frames INSIDE it — so those are one keyed band
    plus one, and the tripwire below says so, because the first draft of that seeding was silently
    dropped and the sweep caught it.
  * THE GLOBALS ARE THE OUTPUT. Five of the eight write more outside the record than in it: the two
    WB_TILE_33_* words, the two HUD slots, the message pair, the meter and the four words the death
    arm raises, plus the weapon's own record list, its fresh flag and WB_FLASH_TIMER. Every case
    states them exactly.
  * ONE ARM REACHES THE SOUND MODULE THROUGH STUB +0. The death arm starts a song, so its case
    declares the chip's mixer and takes `snd_play_song`'s whole write set from test_sound.py — the
    battery that owns it — exactly as test_stage.py and test_behavior.py's slot 61 do.

KNOWINGLY NOT PINNED
  * EVERY CURSOR HERE IS AN EVEN BYTE OFFSET, and no case drives an odd one. `lea 0(a1,d0.w),a1`
    sign-extends the index and the `move.w` then fetches an UNALIGNED word, which is an address
    error on a real 68000; the original's own masks keep its cursors even from any even start, so no
    shipped path reaches one. Same standing as the odd-cursor silence the behaviour tier carries.
  * THE REGISTERS EACH ROUTINE LEAVES BEHIND. None of the eight hands one back that a caller reads:
    $a4e overwrites `player_step_and_arm`'s d0 unread, $a52's `tst.w $6ef0.l` overwrites the
    weapon's, and the other five are entered for their memory alone. The reconstruction returns
    nothing and nothing compares one.
  * THE TWO WRITES `player_climb` MAKES TO ONE WORD. `andi.w #$fff1,(a0)` then `addq.w #8,(a0)` are
    two stores to the x, and `subq.w #2,2(a0)` then `andi.w #$fffe,2(a0)` two to the y; the write
    ledger records FINAL values, so a port that folds each pair into one expression is
    indistinguishable from one that does not. Reproduced as the arithmetic, stated here as the
    silence.
"""
import ctypes

import pytest

import harness
import leaf
import loader
from leaf import (LONGWORD_BYTES, RTS, WORD_BYTES, addi_w_dn, addq_b_d16, addq_b_dn, addq_w_d16,
                  addq_w_dn, andi_w_dn, cmp_w_imm_dn, cmpi_w_abs_l,
                  addq_w_ind, bcc, bcc_s, bra_s, bsr, case_salt, clr_b_d16, clr_w_abs_l, clr_w_d16,
                  clr_w_dn, jsr_ind, keyed_block, lab, lea_abs_l, lea_d16, longword, merge_bands,
                  move_b_d16_dn, move_b_dn_d16, move_b_imm_abs_l, move_b_imm_d16, move_w_abs_l_dn,
                  move_w_d16_d16, move_w_dn_abs_l,
                  move_w_imm_abs_l, move_w_imm_abs_w, move_w_imm_dn, move_w_postinc_dn,
                  movea_l_abs_l, moveq, opcode,
                  program_writes, quick_field, st_abs_l, sub_w_dn_d16, subq_b_d16, subq_w_d16,
                  tst_b_abs_l, tst_b_d16, tst_w_abs_l, tst_w_abs_w, word)
from layout import wb

# The record's geometry, the register ordinals and the three BIT opcodes come from the battery that
# owns the actor table — a second copy of "what a record looks like" could disagree with src/actor.c
# while both stayed green. Same rule test_behavior.py follows.
from leaf import A0, A1, A2, A3, A5, A6, D0, D1, D6, D7                          # noqa: E402
from test_actor import (BCLR_IMM, BEQ_W, BGT_W, BMI_W, BNE_W, BPL_W, BRA_W,  # noqa: E402
                        BSET_IMM, BTST_IMM,
                        RECORD_BYTES, TABLE_DEFAULT, _sfx_bytes, bit_op_d16, jsr_d16_an)
# ...and the sound module's, from the battery that owns snd_play_song.
from test_sound import (PLAY_SONG_INSN_CAP, PLAY_SONG_MIXER, PLAY_SONG_SEEDED_BANDS,   # noqa: E402
                        PSG_REG_MIXER, STUB_TABLE_BASE, STUB_TRIGGER_OFFSET, model_play_song)


# --- the globals, from the header both languages read ---------------------------------------------
ACTOR_X = wb("ACTOR_X")
ACTOR_Y = wb("ACTOR_Y")
ACTOR_FLAGS = wb("ACTOR_FLAGS")
FIELD_10 = wb("ACTOR_FIELD_10")
SPEED = wb("ACTOR_SPEED")
MOVING_BIT = wb("ACTOR_FLAG_MOVING_BIT")
LAUNCHED_BIT = wb("ACTOR_FLAG_LAUNCHED_BIT")
SUPPORTED_BIT = wb("ACTOR_FLAG_SUPPORTED_BIT")
FLICKER_BIT = wb("ACTOR_FLAG_FLICKER_BIT")

JOY1_PREV = wb("JOY1_PREV")
JOY1_CURRENT = wb("JOY1_CURRENT")
JOY1_UP_BIT = wb("JOY1_UP_BIT")
JOY1_DOWN_BIT = wb("JOY1_DOWN_BIT")

TILE_33_FLAG = wb("TILE_33_FLAG")
TILE_33_MODE = wb("TILE_33_MODE")
TILE_33_STEP = wb("TILE_33_STEP")
TILE_33_MODE_UP = wb("TILE_33_MODE_UP")
TILE_33_MODE_DOWN = wb("TILE_33_MODE_DOWN")
TILE_33_STEP_RAISED = wb("TILE_33_STEP_RAISED")
LADDER_STEP = wb("PLAYER_LADDER_STEP")
LADDER_X_MASK = wb("PLAYER_LADDER_X_MASK")
LADDER_X_BIAS = wb("PLAYER_LADDER_X_BIAS")
LADDER_Y_MASK = wb("PLAYER_LADDER_Y_MASK")

EFFECT_STATE_BD6A = wb("EFFECT_STATE_BD6A")
JUMP_STRENGTH_BIAS = wb("PLAYER_JUMP_STRENGTH_BIAS")
SPEED_AFTER_JUMP = wb("PLAYER_SPEED_AFTER_JUMP")
JUMP_SFX = wb("PLAYER_JUMP_SFX")
DEATH_SFX = wb("PLAYER_DEATH_SFX")
DEATH_SONG = wb("PLAYER_DEATH_SONG")
DEATH_FLAG_SET = wb("PLAYER_DEATH_FLAG_SET")
METER_REVIVE = wb("PLAYER_METER_REVIVE")

HUD_SLOT_BBC2 = wb("HUD_SLOT_BBC2")
HUD_SLOT_BBC6 = wb("HUD_SLOT_BBC6")
HUD_SLOT_REARM = wb("HUD_SLOT_REARM")
HUD_METER_VALUE = wb("HUD_METER_VALUE")
KEY_SEQUENCE_MATCHED = wb("KEY_SEQUENCE_MATCHED")
KEY_SEQUENCE_MATCHED_SET = wb("KEY_SEQUENCE_MATCHED_SET")

TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
TEXT_LIFETIME_DEFAULT = wb("TEXT_LIFETIME_DEFAULT")
MESSAGE_REVIVAL_USED = wb("TEXT_MESSAGE_REVIVAL_USED")
MESSAGE_WING_BOOTS_LOST = wb("TEXT_MESSAGE_WING_BOOTS_LOST")

STAGE_RESET_BLOCK = wb("STAGE_RESET_BLOCK")
STATE_FLAG_A34 = wb("STATE_FLAG_A34")
SCROLL_FOLLOW_FROZEN = wb("SCROLL_FOLLOW_FROZEN")
PANEL_FRAME_HOLD = wb("PANEL_FRAME_HOLD")
SND_CHANNEL_A = wb("SND_CHANNEL_A")

RECORD_PTR_10420 = wb("RECORD_PTR_10420")
SCENE_SPAWN_POSITION = wb("SCENE_SPAWN_POSITION")
SPAWN_TEMPLATE_UNREAD = wb("SPAWN_TEMPLATE_UNREAD")
TYPE35_TEMPLATE = wb("ACTOR_TYPE35_TEMPLATE")

# --- and the WALK's and the WEAPON's own (batch 40 phase B) ----------------------------------------
ACTOR_TYPE = wb("ACTOR_TYPE")
ACTOR_SPRITE = wb("ACTOR_SPRITE")
FLAGS2 = wb("ACTOR_FLAGS2")
HALF_WIDTH = wb("ACTOR_HALF_WIDTH")
SIZE_SECOND = wb("ACTOR_SIZE_SECOND")
SIDE_BIT = wb("ACTOR_FLAG_SIDE_BIT")
MOVED_BIT = wb("ACTOR_FLAG_MOVED_BIT")
FIRED_BIT = wb("ACTOR_FLAG_FIRED_BIT")
FLAGS2_BIT_0 = wb("ACTOR_FLAGS2_BIT_0")
INVULNERABLE_BIT = wb("ACTOR_FLAGS2_INVULNERABLE_BIT")
FLICKER_COUNTDOWN = wb("ACTOR_FLICKER_COUNTDOWN")
FIELD_22 = wb("ACTOR_FIELD_22")
FIELD_23 = wb("ACTOR_FIELD_23")
FIELD_24 = wb("ACTOR_FIELD_24")
FIELD_29 = wb("ACTOR_FIELD_29")
FIELD_30 = wb("ACTOR_FIELD_30")
FIELD_31 = wb("ACTOR_FIELD_31")
ST_BYTE = wb("ACTOR_ST_BYTE")
ALLOC_NONE = wb("ACTOR_ALLOC_NONE")

JOY1_LEFT_BIT = wb("JOY1_LEFT_BIT")
JOY1_RIGHT_BIT = wb("JOY1_RIGHT_BIT")
JOY1_FIRE_BIT = wb("JOY1_FIRE_BIT")

WALK_SUBFRAME_MASK = wb("PLAYER_WALK_SUBFRAME_MASK")
WALK_SPEED_BIAS = wb("PLAYER_WALK_SPEED_BIAS")
TURN_DECEL_RIGHT = wb("PLAYER_TURN_DECEL_RIGHT")
TURN_DECEL_LEFT = wb("PLAYER_TURN_DECEL_LEFT")
DRIFT_SPEND = wb("PLAYER_DRIFT_SPEND")

# --- ...and the STAGE TRANSITION's (batch 40 phase C) -----------------------------------------------
FIELD_18 = wb("ACTOR_FIELD_18")
FALLING_BIT = wb("ACTOR_FLAG_FALLING_BIT")
ANIM_FRAME_BYTES = wb("ACTOR_ANIM_FRAME_BYTES")
ANIM32_MASK = wb("ACTOR_ANIM32_MASK")
SPRITE_HIDDEN = wb("ACTOR_SPRITE_HIDDEN")

STAGE_ANIM_REQUEST_B0E = wb("STAGE_ANIM_REQUEST_B0E")
STAGE_ANIM_DONE_B10 = wb("STAGE_ANIM_DONE_B10")
STAGE_ANIM_DONE_B18 = wb("STAGE_ANIM_DONE_B18")
EVENT_ANIM_DONE_B16 = wb("EVENT_ANIM_DONE_B16")
EVENT_DONE_SET = wb("EVENT_DONE_SET")
EFFECT_STATE_21E4 = wb("EFFECT_STATE_21E4")

POSTURE_TABLE_0 = wb("PLAYER_POSTURE_TABLE_0")
POSTURE_TABLE_1 = wb("PLAYER_POSTURE_TABLE_1")
POSTURE_TABLE_2 = wb("PLAYER_POSTURE_TABLE_2")
POSTURE_BYTES = wb("PLAYER_POSTURE_BYTES")
POSTURE_IDLE_RIGHT = wb("PLAYER_POSTURE_IDLE_RIGHT")
POSTURE_IDLE_LEFT = wb("PLAYER_POSTURE_IDLE_LEFT")
POSTURE_JUMP_LEFT = wb("PLAYER_POSTURE_JUMP_LEFT")
POSTURE_JUMP_RIGHT = wb("PLAYER_POSTURE_JUMP_RIGHT")
POSTURE_FALL_LEFT = wb("PLAYER_POSTURE_FALL_LEFT")
POSTURE_FALL_RIGHT = wb("PLAYER_POSTURE_FALL_RIGHT")
POSTURE_WALK_RIGHT = wb("PLAYER_POSTURE_WALK_RIGHT")
POSTURE_WALK_LEFT = wb("PLAYER_POSTURE_WALK_LEFT")
POSTURE_STATE_ONE = wb("PLAYER_POSTURE_STATE_ONE")

TRANSITION_CURSOR = wb("PLAYER_TRANSITION_CURSOR")
TRANSITION_TABLE_BYTES = wb("PLAYER_TRANSITION_TABLE_BYTES")
EVENT_ANIM_CURSOR = wb("PLAYER_EVENT_ANIM_CURSOR")
DEATH_ANIM_CURSOR = wb("PLAYER_DEATH_ANIM_CURSOR")
ATTACK_CURSOR = wb("PLAYER_ATTACK_CURSOR")
ATTACK_TABLE_RIGHT = wb("PLAYER_ATTACK_TABLE_RIGHT")
ATTACK_TABLE_LEFT = wb("PLAYER_ATTACK_TABLE_LEFT")
ATTACK_MASK = wb("PLAYER_ATTACK_MASK")
ATTACK_SFX = wb("PLAYER_ATTACK_SFX")
LADDER_SPRITES = wb("PLAYER_LADDER_SPRITES")
LADDER_SPRITE_MASK = wb("PLAYER_LADDER_SPRITE_MASK")
HURT_SPRITE_RIGHT = wb("PLAYER_HURT_SPRITE_RIGHT")
HURT_SPRITE_LEFT = wb("PLAYER_HURT_SPRITE_LEFT")
HURT2_SPRITE_RIGHT = wb("PLAYER_HURT2_SPRITE_RIGHT")
HURT2_SPRITE_LEFT = wb("PLAYER_HURT2_SPRITE_LEFT")

# NOT header constants, for `WEAPON_SPEND_VALUE`'s reason: the reconstruction READS these four words
# out of the image (they are data inside $1f54's own body, at WB_PLAYER_LADDER_SPRITES) rather than
# spelling them, so they are the entry pin's claim and not something src/player.c could drift from.
LADDER_SPRITE_A = 0x14e
LADDER_SPRITE_B = 0x14f

EFFECT_RECORD_LIST = wb("EFFECT_RECORD_LIST")
EFFECT_RECORD_WRITE_PTR = wb("EFFECT_RECORD_WRITE_PTR")
EFFECT_RECORD_LEN = wb("EFFECT_RECORD_LEN")
RECORD_LOW_BYTE = wb("RECORD_LOW_BYTE")
RECORD_FRESH_FLAG = wb("RECORD_FRESH_FLAG")
FLASH_TIMER = wb("FLASH_TIMER")
FIRE_EDGE_EXACT = wb("PLAYER_FIRE_EDGE_EXACT")
WEAPON_LIGHTNING = wb("PLAYER_WEAPON_LIGHTNING")
WEAPON_WIND_SPOUTS = wb("PLAYER_WEAPON_WIND_SPOUTS")
WEAPON_FIRE_BALLS = wb("PLAYER_WEAPON_FIRE_BALLS")
LIGHTNING_FLASH = wb("PLAYER_LIGHTNING_FLASH")
SHOT_TYPE_WIND = wb("PLAYER_SHOT_TYPE_WIND")
SHOT_TYPE_BOMB = wb("PLAYER_SHOT_TYPE_BOMB")
SHOT_TYPE_FIREBALL = wb("PLAYER_SHOT_TYPE_FIREBALL")
SHOT_LIFETIME_WIND = wb("PLAYER_SHOT_LIFETIME_WIND")
SHOT_LIFETIME = wb("PLAYER_SHOT_LIFETIME")
SHOT_SPEED = wb("PLAYER_SHOT_SPEED")
SHOT_HALF_WIDTH = wb("PLAYER_SHOT_HALF_WIDTH")
SHOT_SIZE_SECOND = wb("PLAYER_SHOT_SIZE_SECOND")
FIREBALL_Y_RISE = wb("PLAYER_FIREBALL_Y_RISE")
WEAPON_SPEND_BCD = wb("PLAYER_WEAPON_SPEND_BCD")
# NOT a header constant: the reconstruction READS this byte out of the image (it is data inside
# player_weapon_fire's own 300), so the value is a claim the entry pin makes and the case below
# restates against the shipped bytes rather than a number src/player.c could drift from.
WEAPON_SPEND_VALUE = 1
# One byte — the two digits `sbcd -(a2),-(a6)` touches.
BCD_COUNT_BYTES = 1

# Where a case puts the player's record: an ordinary slot of the default table, with a record's
# margin either side seeded so that a write one field or one record out lands on bytes that are wrong
# FOR WHERE THEY WERE WRITTEN rather than on zeros.
ACTOR = TABLE_DEFAULT + 5 * RECORD_BYTES
SEEDED_LO = ACTOR - RECORD_BYTES
SEEDED_LEN = 3 * RECORD_BYTES

# A value no arm of any routine here writes, so a byte still holding it was not written.
MARKER = 0x5a


def _pokes(what, fields=None):
    """A seeded image: the record and its margin, address-keyed, plus whatever the case states.

    The GLOBALS are deliberately NOT keyed. Every one of them steers a branch, so a keyed byte would
    choose the arm instead of the case; each is seeded explicitly by the case that reads it, and the
    two the routines merely OVERWRITE (the message pair) are seeded to MARKER here so that writing
    them is a change the ledger can see."""
    base = {SEEDED_LO: keyed_block(SEEDED_LO, SEEDED_LEN, case_salt(what)),
            TEXT_REQUEST: bytes([MARKER]),
            TEXT_LIFETIME_REQUEST: word(MARKER),
            TILE_33_STEP: word(MARKER)}
    return leaf.overlay(base, fields or {})


def _assert_writes(info, expected, what):
    """The oracle's write set, stated EXACTLY — every case here can say what it wrote."""
    leaf.assert_written_is(info, {addr: bytes([value]) if isinstance(value, int) else value
                                  for addr, value in expected.items()}, what)


def _put_word(expected, addr, value):
    expected[addr] = (value >> 8) & 0xff
    expected[addr + 1] = value & 0xff


# --- the encodings this battery's entry pins need --------------------------------------------------
# Everything already in leaf.py is imported above; these are the forms no battery had. They are
# spelt from the 68000's own field layout rather than transcribed, so a wrong register or a wrong
# operand size fails on the image's bytes.

def btst_imm_abs_w(bit, addr):
    """`btst #n,addr.w` — how the player's tier reads the joystick's HELD state, against the
    `btst #n,Dn` its edge tests use."""
    return opcode(0x0838) + word(bit) + word(addr)


def andi_w_ind(base, value):
    """`andi.w #imm,(An)` — the ladder's x snap, applied IN MEMORY."""
    return opcode(0x0250 | base) + word(value)


def andi_w_d16(base, value, displacement):
    """...and the same over d16(An), for the y."""
    return opcode(0x0268 | base) + word(value) + word(displacement)







def subq_b_abs_l(amount, addr):
    return opcode(0x5139 | leaf.quick_field(amount)) + addr.to_bytes(LONGWORD_BYTES, "big")



def addi_b_dn(reg, value):
    """`addi.b #imm,Dn` — the jump strength's own add, and a BYTE one where the walk's is a word."""
    return opcode(0x0600 | reg) + word(value & 0xff)



def move_l_d16_postinc(source, destination, displacement):
    """`move.l d16(As),(Ad)+` — the scene descriptor's position longword."""
    return opcode(0x20c0 | (destination << 9) | (5 << 3) | source) + word(displacement)


def move_l_postinc_postinc(source, destination):
    """`move.l (As)+,(Ad)+` — the seven the template supplies."""
    return opcode(0x20d8 | (destination << 9) | source)


# ...and the forms the WALK and the WEAPON need. Spelt from the 68000's own field layout, same rule.

def tst_b_dn(reg):
    """`tst.b Dn` — the walk's fire test, which is a SIGN test of bit 7 (`bpl`) rather than a
    `btst`."""
    # ALSO IN test_behavior.py, test_actor.py — third copy, queued for leaf.py.
    return opcode(0x4a00 | reg)


def tst_b_ind(base):
    """`tst.b (An)` — the weapon re-reading the byte its `sbcd` has just written."""
    # ALSO IN test_stage.py — second copy.
    return opcode(0x4a10 | base)


def st_d16(base, displacement):
    """`st d16(An)` — the turn's direction byte set to WB_ACTOR_ST_BYTE."""
    # ALSO IN test_behavior.py — second copy.
    return opcode(0x50e8 | base) + word(displacement)


def andi_b_d16(base, value, displacement):
    """`andi.b #imm,d16(An)` — the sub-frame counter's own mask, applied IN MEMORY."""
    # ALSO IN test_behavior.py — second copy.
    return opcode(0x0228 | base) + word(value & 0xff) + word(displacement)


def cmp_b_d16_dn(reg, base, displacement):
    """`cmp.b d16(An),Dn` — the accelerator's ceiling test, a SIGNED byte comparison."""
    # ALSO IN test_scene.py (the marker pair's two neighbour compares) — SECOND copy, same argument
    # order, and it goes to leaf.py on the third.
    return opcode(0xb028 | (reg << 9) | base) + word(displacement)


def cmp_b_imm_dn(reg, value):
    """`cmp.b #imm,Dn` — the weapon's EQUALITY test on joy1_newly_pressed's whole byte."""
    # ALSO IN test_behavior.py, test_text.py, test_sound.py (`CMP_B_IMM_DN`) — fourth copy,
    # queued for leaf.py.
    return opcode(0xb03c | (reg << 9)) + word(value & 0xff)


def cmpi_l_abs_l(value, addr):
    """`cmpi.l #imm,addr.l` — the write pointer against the list's base."""
    return opcode(0x0cb9) + longword(value) + longword(addr)


def cmpi_b_ind(base, value):
    """`cmpi.b #imm,(An)` — the item byte of the record the pointer names."""
    # ALSO IN test_behavior.py, test_map.py, test_stage.py — fourth copy, queued for leaf.py, and
    # spelt in THEIR argument order (base first) rather than this battery's own reading order: the
    # `adda_w_dn_an` collision was two copies of one encoder that disagreed about exactly that.
    return opcode(0x0c10 | base) + word(value & 0xff)


def cmpa_l_imm(reg, value):
    """`cmpa.l #imm,An` — "did the allocator hand back a record"."""
    # ALSO IN test_actor.py, test_blit.py, test_behavior.py, test_scene.py — fifth copy, queued
    # for leaf.py.
    return opcode(0xb1fc | (reg << 9)) + longword(value)


def addq_l_an(amount, reg):
    """`addq.l #n,An` — a whole-register add that touches NO condition code, which is why it can sit
    between the arithmetic that sets X and the `sbcd` that reads it."""
    # ALSO IN test_map.py — second copy.
    return opcode(0x5088 | quick_field(amount) | reg)


def subq_l_abs_l(amount, addr):
    """`subq.l #n,addr.l` — the write pointer rewound by one record."""
    return opcode(0x5189 | quick_field(amount) | 0x30) + longword(addr)


def sbcd_predec(destination, source):
    """`sbcd -(Ad),-(As)` — the memory-to-memory form, which is the one this game executes."""
    return opcode(0x8108 | (destination << 9) | source)


def move_w_imm_d16(base, value, displacement):
    """`move.w #imm,d16(An)` — the shot's type word."""
    # ALSO IN test_actor.py, test_behavior.py — third copy, queued for leaf.py.
    return opcode(0x317c | (base << 9)) + word(value) + word(displacement)


def move_l_imm_d16(base, value, displacement):
    """`move.l #imm,d16(An)` — the shot's footprint, both words in ONE store."""
    # ALSO IN test_actor.py, test_behavior.py — third copy, queued for leaf.py.
    return opcode(0x217c | (base << 9)) + longword(value) + word(displacement)


def move_b_d16_d16(source, destination, source_displacement, destination_displacement):
    """`move.b d16(As),d16(Ad)` — the player's WHOLE flags byte copied onto the shot."""
    # ALSO IN test_behavior.py — second copy, and in the OPPOSITE argument order, which is the
    # collision `adda_w_dn_an` already made once: whichever hoist takes these has to pick one.
    return (opcode(0x1028 | (destination << 9) | (5 << 6) | source)
            + word(source_displacement) + word(destination_displacement))


def move_l_ind_ind(source, destination):
    """`move.l (As),(Ad)` — the shot's x,y taken from the player's."""
    # ALSO IN test_behavior.py — second copy, which the rule allows.
    return opcode(0x2090 | (destination << 9) | source)


# ...and the forms the STAGE TRANSITION needs. Its whole vocabulary is `move.w <something>,6(a0)` in
# four addressing modes, which is what a sprite selector is; the three below are that instruction's
# source modes, spelt from the 68000's own field layout like every encoder above.
# ...and the two BELOW are leaf.py's now, hoisted by this batch: `move_w_d16_d16` on its third copy
# (test_actor.py's and test_behavior.py's remain) and `move_w_dn_abs_l` on its fourth
# (test_behavior.py, test_scroll.py, test_stage.py). This file imports both rather than spelling a
# fourth and a fifth.
MOVE_W_TO_D16 = 0x3000 | (5 << 6)     # size + destination mode `d16(An)`, shared by the two here


def move_w_indexed_d16(source, index, destination, displacement, source_displacement=0):
    """`move.w d8(As,Dn.w),d16(Ad)` — a frame fetched out of a table the cursor has just indexed and
    published straight into the record. FOUR of the five animations here are this one instruction."""
    # ALSO IN test_behavior.py — SECOND copy, and that one takes the same four arguments in the same
    # order without this file's optional fifth (a displacement the behaviour tier's sites never use).
    return (opcode(MOVE_W_TO_D16 | (destination << 9) | (6 << 3) | source)
            + leaf.brief_extension_word(index, source_displacement) + word(displacement))


def move_w_ind_d16(source, destination, displacement):
    """`move.w (As),d16(Ad)` — the same publish where a `lea` has already added the index."""
    # ALSO IN test_behavior.py — SECOND copy, same argument order.
    return opcode(MOVE_W_TO_D16 | (destination << 9) | (2 << 3) | source) + word(displacement)


def andi_b_dn(reg, value):
    """`andi.b #imm,Dn` — the ladder's cursor masked in a REGISTER, where the step below it masks the
    record's field in memory."""
    # ALSO IN test_behavior.py — SECOND copy, same argument order.
    return opcode(0x0200 | reg) + word(value & 0xff)


def bsr_label(target):
    """`bsr.w` aimed at a LABEL in this body. `leaf.bsr` takes a ROUTINE NAME, and $2010's call is
    the one `bsr` in this battery whose target has no name of its own: it is the bare `rts` at
    $205c, i.e. a call that does nothing at all."""
    return leaf.Ref(4, lambda at, labels: leaf.bsr_w(at, labels[target]))


# --- the entry pins ---------------------------------------------------------------------------------
JOY1_NEWLY_PRESSED = "joy1_newly_pressed"


def _meter_empty_pieces():
    """$a76 — the death check. Two arms and one shared `rts`."""
    return [
        tst_w_abs_l(HUD_METER_VALUE),
        bcc(BNE_W, "out"),
        tst_b_abs_l(HUD_SLOT_BBC6),
        bcc(BNE_W, "revive"),
        tst_w_abs_w(KEY_SEQUENCE_MATCHED),
        bcc(BEQ_W, "die"),
        lab("revive"),
        move_w_imm_dn(D0, DEATH_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        tst_w_abs_w(KEY_SEQUENCE_MATCHED),
        bcc(BNE_W, "post"),
        move_w_imm_abs_l(HUD_SLOT_REARM, HUD_SLOT_BBC6),
        lab("post"),
        move_b_imm_abs_l(MESSAGE_REVIVAL_USED, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        move_w_imm_abs_l(METER_REVIVE, HUD_METER_VALUE),
        RTS,
        lab("die"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        tst_w_abs_l(STAGE_RESET_BLOCK),
        bcc(BMI_W, "out"),
        move_w_imm_abs_w(DEATH_FLAG_SET, STATE_FLAG_A34),
        lea_abs_l(A1, STUB_TABLE_BASE),
        move_w_imm_dn(D0, DEATH_SONG),
        jsr_ind(A1),
        move_w_imm_abs_l(DEATH_FLAG_SET, STAGE_RESET_BLOCK),
        move_w_imm_abs_l(DEATH_FLAG_SET, SCROLL_FOLLOW_FROZEN),
        move_w_imm_abs_l(DEATH_FLAG_SET, PANEL_FRAME_HOLD),
        lab("out"),
        RTS,
    ]


def _jump_step_pieces():
    """$e06 — the jump machine. Three exclusive arms over WB_ACTOR_FLAGS, and a head that runs on
    every one of them."""
    return [
        clr_w_abs_l(TILE_33_STEP),
        move_w_abs_l_dn(D0, EFFECT_STATE_BD6A),
        addi_b_dn(D0, JUMP_STRENGTH_BIAS),
        move_b_dn_d16(D0, A0, FIELD_10),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "ascend"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "launch"),
        # the wing boots
        tst_b_abs_l(HUD_SLOT_BBC2),
        bcc(BEQ_W, "out"),
        btst_imm_abs_w(JOY1_UP_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "out"),
        move_b_imm_d16(A0, SPEED_AFTER_JUMP, SPEED),
        subq_b_abs_l(1, HUD_SLOT_BBC2),
        bcc(BNE_W, "out"),
        move_w_imm_abs_l(HUD_SLOT_REARM, HUD_SLOT_BBC2),
        move_b_imm_abs_l(MESSAGE_WING_BOOTS_LOST, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        lab("out"),
        RTS,
        lab("launch"),
        bsr(JOY1_NEWLY_PRESSED),
        leaf.btst_imm_dn(JOY1_UP_BIT, D0),
        bcc(BNE_W, "fire"),
        RTS,
        lab("fire"),
        move_w_imm_dn(D0, JUMP_SFX),
        move_w_imm_dn(D1, SND_CHANNEL_A),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        move_b_d16_dn(D0, A0, FIELD_10),
        move_b_dn_d16(D0, A0, SPEED),
        RTS,
        lab("ascend"),
        moveq(0, D0),
        move_b_d16_dn(D0, A0, SPEED),
        sub_w_dn_d16(D0, A0, ACTOR_Y),
        subq_b_d16(1, A0, SPEED),
        bcc(BNE_W, "done"),
        bit_op_d16(BCLR_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, SPEED_AFTER_JUMP, SPEED),
        lab("done"),
        RTS,
    ]


def _climb_arm(mode, step_op):
    """The ladder's two arms, which are one body with the mode word and the y step exchanged."""
    return [
        bit_op_d16(BCLR_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_w_imm_abs_l(TILE_33_STEP_RAISED, TILE_33_STEP),
        andi_w_ind(A0, LADDER_X_MASK),
        addq_w_ind(LADDER_X_BIAS, A0),
        move_w_imm_abs_l(mode, TILE_33_MODE),
        step_op,
        andi_w_d16(A0, LADDER_Y_MASK, ACTOR_Y),
        RTS,
    ]


def _apply_joystick_pieces():
    """$d84 — the ladder. Its LAST instruction is an `rts` at $e04, which is what says it does not
    fall into the jump machine at $e06 below it."""
    return ([
        tst_w_abs_l(TILE_33_FLAG),
        bcc(BEQ_W, "none"),
        btst_imm_abs_w(JOY1_UP_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "down"),
    ] + _climb_arm(TILE_33_MODE_UP, subq_w_d16(LADDER_STEP, A0, ACTOR_Y)) + [
        lab("down"),
        btst_imm_abs_w(JOY1_DOWN_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "none"),
    ] + _climb_arm(TILE_33_MODE_DOWN, addq_w_d16(LADDER_STEP, A0, ACTOR_Y)) + [
        lab("none"),
        clr_w_abs_l(TILE_33_STEP),
        RTS,
    ])


def _reset_ground_pieces():
    """$107c — leaving the ladder. The one instruction that separates it from the jump machine's own
    head is the operand size: `addq.b #8,d0` where $e12 spells `addi.b #$8,d0`."""
    return [
        clr_w_abs_l(TILE_33_MODE),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        move_w_abs_l_dn(D0, EFFECT_STATE_BD6A),
        addq_b_dn(JUMP_STRENGTH_BIAS, D0),
        move_b_dn_d16(D0, A0, SPEED),
        RTS,
    ]


def _copy_record_pieces():
    """$539e — eight longwords, and the first is not the template's."""
    return ([
        movea_l_abs_l(A3, RECORD_PTR_10420),
        move_l_d16_postinc(A3, A2, SCENE_SPAWN_POSITION),
        lea_d16(A1, SPAWN_TEMPLATE_UNREAD, A1),
    ] + [move_l_postinc_postinc(A1, A2)] * TEMPLATE_LONGWORDS + [RTS])


TEMPLATE_LONGWORDS = (RECORD_BYTES - LONGWORD_BYTES) // LONGWORD_BYTES

STEP_LEFT = "actor_step_left_against_map"
STEP_RIGHT = "actor_step_right_against_map"
ALLOC_HIGH = "actor_alloc_slot_high"


def _walk_direction_arm(rightward):
    """$fa8 / $1014 — the arm a held direction takes, and the two are one body with the side flag's
    op, the turn's polarity and the two tail labels exchanged. Spelt as ONE function because a
    transcribed pair could differ where the original does not — the asymmetry that IS real is the
    turn's decrement, and it lives in the two turn blocks below."""
    side, turn, straight = ((BCLR_IMM, "turn-right", "step-right") if rightward else
                            (BSET_IMM, "turn-left", "step-left"))
    return [
        lab("arm-right" if rightward else "arm-left"),
        tst_w_abs_l(TILE_33_MODE),
        bcc(BEQ_W, f"walk-{straight}"),
        bsr("player_reset_ground_state"),
        lab(f"walk-{straight}"),
        bit_op_d16(side, SIDE_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVED_BIT, A0, ACTOR_FLAGS),
        clr_w_dn(D6),
        move_b_d16_dn(D6, A0, FIELD_23),
        # The LEFT arm branches away on a NONZERO direction byte and the RIGHT arm on a zero one:
        # the same question, opposite polarity.
        (bcc(BNE_W, turn) if not rightward else bcc_s(BEQ_W, turn)),
        addq_b_d16(1, A0, FIELD_24),
        andi_b_d16(A0, WALK_SUBFRAME_MASK, FIELD_24),
        bcc(BNE_W, straight),
        addq_b_d16(1, A0, FIELD_22),
        move_w_abs_l_dn(D0, EFFECT_STATE_BD6A),
        addq_w_dn(WALK_SPEED_BIAS, D0),
        cmp_b_d16_dn(D0, A0, FIELD_22),
        bcc(BGT_W, straight),
        move_b_dn_d16(D0, A0, FIELD_22),
        lab(straight),
        clr_w_dn(D7),
        move_b_d16_dn(D7, A0, FIELD_22),
        (bcc(BEQ_W, "out") if not rightward else bcc_s(BEQ_W, "out")),
        bsr(STEP_LEFT if not rightward else STEP_RIGHT),
    ]


def _step_and_arm_pieces():
    """$ec8 — the walk. FIVE sections in a row and then the accelerator's own six exits, which is
    why the pin is a label assembler rather than a list of spanned byte counts."""
    return [
        # the knock-back
        tst_b_d16(A0, FIELD_29),
        bcc(BEQ_W, "fire-edge"),
        moveq(0, D7),
        move_b_d16_dn(D7, A0, FIELD_29),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "knock-right"),
        bsr(STEP_LEFT),
        bcc(BRA_W, "knock-done"),
        lab("knock-right"),
        bsr(STEP_RIGHT),
        lab("knock-done"),
        subq_b_d16(1, A0, FIELD_29),
        # the fire edge
        lab("fire-edge"),
        bsr(JOY1_NEWLY_PRESSED),
        tst_b_dn(D0),
        bcc(BPL_W, "flicker"),
        bit_op_d16(BSET_IMM, FIRED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        clr_b_d16(A0, FIELD_22),
        # the flicker countdown
        lab("flicker"),
        bit_op_d16(BTST_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "drift"),
        subq_b_d16(1, A0, FLICKER_COUNTDOWN),
        bcc(BNE_W, "drift"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, INVULNERABLE_BIT, A0, FLAGS2),
        # the hurt drift
        lab("drift"),
        bit_op_d16(BTST_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bcc(BEQ_W, "walk"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "drift-step"),
        bit_op_d16(BCLR_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bcc(BRA_W, "walk"),
        lab("drift-step"),
        moveq(0, D7),
        move_b_d16_dn(D7, A0, FIELD_31),
        tst_b_dn(D7),
        bcc(BEQ_W, "drift-probe"),
        subq_b_d16(DRIFT_SPEND, A0, FIELD_31),
        lab("drift-probe"),
        tst_b_d16(A0, FIELD_30),
        bcc(BEQ_W, "drift-left"),
        bsr(STEP_RIGHT),
        bcc(BRA_W, "walk"),
        lab("drift-left"),
        bsr(STEP_LEFT),
        # the accelerator
        lab("walk"),
        btst_imm_abs_w(JOY1_RIGHT_BIT, JOY1_CURRENT),
        bcc(BNE_W, "arm-right"),
        btst_imm_abs_w(JOY1_LEFT_BIT, JOY1_CURRENT),
        bcc(BNE_W, "arm-left"),
        # ...and the arm neither direction takes
        bit_op_d16(BCLR_IMM, MOVED_BIT, A0, ACTOR_FLAGS),
        moveq(0, D7),
        move_b_d16_dn(D7, A0, FIELD_22),
        bcc(BEQ_W, "coast-out"),
        subq_b_d16(1, A0, FIELD_22),
        bcc(BPL_W, "coast-step"),
        clr_b_d16(A0, FIELD_22),
        lab("coast-out"),
        RTS,
        lab("coast-step"),
        move_b_d16_dn(D0, A0, FIELD_23),
        bcc(BEQ_W, "step-left"),
        bcc(BRA_W, "step-right"),
    ] + _walk_direction_arm(rightward=False) + [
        lab("out"),
        RTS,
        # $1002 — turning to face RIGHT, entered from the RIGHT arm on a direction byte of zero
        lab("turn-right"),
        subq_b_d16(TURN_DECEL_RIGHT, A0, FIELD_22),
        bcc_s(BPL_W, "step-left"),
        clr_b_d16(A0, FIELD_22),
        st_d16(A0, FIELD_23),
        bcc(BRA_W, "step-right"),
    ] + _walk_direction_arm(rightward=True) + [
        # $1068 — the right tail's OWN `rts`; its `beq` above aims BACKWARD at $1000's instead,
        # which is what makes the two tails share one early exit and not this one.
        RTS,
        # $106a — and turning to face LEFT, entered from the LEFT arm on a nonzero direction byte
        lab("turn-left"),
        subq_b_d16(TURN_DECEL_LEFT, A0, FIELD_22),
        bcc_s(BPL_W, "step-right"),
        clr_b_d16(A0, FIELD_22),
        clr_b_d16(A0, FIELD_23),
        bcc(BRA_W, "step-left"),
    ]


def _weapon_spawn_pieces(item, type_word, lifetime, type_first):
    """$1276 / $1308 — the two arms that end in the SHARED arming block at $1292. `item` keys the
    labels; `type_first` is the ONE thing that really differs below the allocation, and it is a
    parameter rather than a test on the label so a third caller cannot inherit the wrong order."""
    stores = [move_w_imm_d16(A1, type_word, ACTOR_TYPE), move_b_imm_d16(A1, lifetime, FIELD_30)]
    return [
        lab(f"spawn-{item}"),
        bsr(ALLOC_HIGH),
        cmpa_l_imm(A1, ALLOC_NONE),
        bcc(BNE_W, f"fill-{item}"),
        RTS,
        lab(f"fill-{item}"),
    ] + (stores if type_first else stores[::-1])


def _weapon_fire_pieces():
    """$1208 — the weapon. Four gates, a four-way dispatch on the record's item byte, and one shared
    `sbcd` tail; the last two bytes are the packed-BCD 1 that tail subtracts."""
    return [
        tst_w_abs_l(TILE_33_FLAG),
        bcc(BNE_W, "out"),
        cmpi_l_abs_l(EFFECT_RECORD_LIST, EFFECT_RECORD_WRITE_PTR),
        bcc(BEQ_W, "out"),
        bsr(JOY1_NEWLY_PRESSED),
        cmp_b_imm_dn(D0, FIRE_EDGE_EXACT),
        bcc(BNE_W, "out"),
        btst_imm_abs_w(JOY1_DOWN_BIT, JOY1_CURRENT),
        bcc(BEQ_W, "out"),
        movea_l_abs_l(A6, EFFECT_RECORD_WRITE_PTR),
        cmpi_b_ind(A6, WEAPON_LIGHTNING),
        bcc(BEQ_W, "lightning"),
        cmpi_b_ind(A6, WEAPON_WIND_SPOUTS),
        bcc(BEQ_W, "spawn-wind"),
        cmpi_b_ind(A6, WEAPON_FIRE_BALLS),
        bcc(BEQ_W, "spawn-fireball"),
        bcc(BRA_W, "spawn-bomb"),
        # $1258 — the shared spend
        lab("spend"),
        addq_l_an(WORD_BYTES, A6),
        lea_abs_l(A2, WEAPON_SPEND_BCD + 1),
        sbcd_predec(A6, A2),
        st_abs_l(RECORD_FRESH_FLAG),
        tst_b_ind(A6),
        bcc(BNE_W, "out"),
        subq_l_abs_l(WORD_BYTES, EFFECT_RECORD_WRITE_PTR),
        lab("out"),
        RTS,
    ] + _weapon_spawn_pieces("wind", SHOT_TYPE_WIND, SHOT_LIFETIME_WIND, type_first=True) + [
        # $1292 — the arming block the BOMB arm branches into
        lab("arm-shot"),
        clr_w_d16(A1, ACTOR_SPRITE),
        move_b_d16_d16(A0, A1, ACTOR_FLAGS, ACTOR_FLAGS),
        clr_b_d16(A1, FLAGS2),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVING_BIT, A1, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A1, ACTOR_FLAGS),
        move_b_imm_d16(A1, SHOT_SPEED, SPEED),
        move_l_ind_ind(A0, A1),
        move_l_imm_d16(A1, (SHOT_HALF_WIDTH << 16) | SHOT_SIZE_SECOND, HALF_WIDTH),
        bra_s("spend"),
        # $12c4 — the fireball, which shares nothing below its own allocation
        lab("spawn-fireball"),
        bsr(ALLOC_HIGH),
        cmpa_l_imm(A1, ALLOC_NONE),
        bcc(BNE_W, "fill-fireball"),
        RTS,
        lab("fill-fireball"),
        move_w_imm_d16(A1, SHOT_TYPE_FIREBALL, ACTOR_TYPE),
        move_b_imm_d16(A1, SHOT_LIFETIME, FIELD_30),
        move_l_ind_ind(A0, A1),
        subq_w_d16(FIREBALL_Y_RISE, A1, ACTOR_Y),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "fireball-left"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A1, ACTOR_FLAGS),
        bcc(BRA_W, "fireball-sprite"),
        lab("fireball-left"),
        bit_op_d16(BSET_IMM, SIDE_BIT, A1, ACTOR_FLAGS),
        lab("fireball-sprite"),
        clr_b_d16(A1, ACTOR_SPRITE),
        bcc(BRA_W, "spend"),
    ] + _weapon_spawn_pieces("bomb", SHOT_TYPE_BOMB, SHOT_LIFETIME, type_first=False) + [
        bcc(BRA_W, "arm-shot"),
        # $1328 — the lightning, whose whole arm is one store
        lab("lightning"),
        move_w_imm_abs_w(LIGHTNING_FLASH, FLASH_TIMER),
        bcc(BRA_W, "spend"),
        # ...and the two bytes at $1332: the packed-BCD 1 the `sbcd` above reads, and one unread
        # byte of padding to the routine's end. DATA, inside the routine's own extent.
        word(WEAPON_SPEND_VALUE << 8),
    ]


def _walk_cycle_pieces(cursor_field):
    """$21b0 / $21ca — the two facings' walk cycles, one body with the POSTURE RECORD's own cursor
    field exchanged. The frame is published from the cursor as it WAS and the field stepped
    afterwards, in memory, by an `addq.w` and an `andi.w` — two stores to one word."""
    return [
        lea_d16(A5, cursor_field, A6),
        move_w_postinc_dn(D0, A5),
        leaf.lea_indexed(A5, D0),
        move_w_ind_d16(A5, A0, ACTOR_SPRITE),
        addq_w_d16(ANIM_FRAME_BYTES, A6, cursor_field),
        andi_w_d16(A6, ANIM32_MASK, cursor_field),
        RTS,
    ]


def _anim32_pieces(cursor, done_flag):
    """$1faa / $1fde — arms 2 and 3, one body with the cursor exchanged and the completion arm
    present or absent. Sixteen words wrapped by WB_ACTOR_ANIM32_MASK, and the `bne` reads the Z that
    `move.w d0,<cursor>` itself set."""
    label = f"anim32-{cursor:#x}"
    stepped = [
        lea_abs_l(A1, cursor),
        move_w_postinc_dn(D0, A1),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        addq_w_dn(ANIM_FRAME_BYTES, D0),
        andi_w_dn(D0, ANIM32_MASK),
        move_w_dn_abs_l(D0, cursor),
    ]
    if done_flag is None:                       # $1fde falls to the shared `rts` instead
        return stepped + [bcc(BRA_W, "tail-rts")]
    return stepped + [
        bcc(BNE_W, label),
        move_w_imm_abs_w(EVENT_DONE_SET, done_flag),
        move_w_imm_d16(A0, SPRITE_HIDDEN, ACTOR_SPRITE),
        lab(label),
        RTS,
    ]


def _hurt_pair_pieces(label, left, right, fall_through):
    """$2024 / $2042 — the two fixed hurt sprites, chosen by WB_ACTOR_FLAG_SIDE_BIT. The LAST of the
    two blocks falls into the shared `rts` where the first branches to it, which is the one thing
    that is not symmetric between them."""
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, f"{label}-right"),
        move_w_imm_d16(A0, left, ACTOR_SPRITE),
        bcc(BRA_W, "tail-rts"),
        lab(f"{label}-right"),
        move_w_imm_d16(A0, right, ACTOR_SPRITE),
    ] + ([] if fall_through else [bcc(BRA_W, "tail-rts")])


def _posture_pair_pieces(label, left_field, right_field, right_is_indirect=False):
    """$2146 / $2160 / $218e — one question already answered, and the pair of posture-record fields
    WB_ACTOR_FLAG_SIDE_BIT then chooses between. `right_is_indirect` is the idle pair's own quirk:
    its RIGHT field is offset zero, so the original spells `move.w (a6),6(a0)`."""
    return [
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, f"{label}-right"),
        move_w_d16_d16(A6, left_field, A0, ACTOR_SPRITE),
        RTS,
        lab(f"{label}-right"),
        (move_w_ind_d16(A6, A0, ACTOR_SPRITE) if right_is_indirect
         else move_w_d16_d16(A6, right_field, A0, ACTOR_SPRITE)),
        RTS,
    ]


def _stage_transition_pieces():
    """$1f54 — FOUR flag arms in one chain, two shared tails ($205c's bare `rts` and the posture
    selector at $205e), and EIGHT BYTES OF DATA in the middle of the body: the ladder's own frame
    table at $20c2, which the `rts` above it and the `btst` below it bound exactly."""
    return [
        tst_w_abs_w(STAGE_ANIM_DONE_B10),
        bcc(BEQ_W, "live"),
        RTS,
        lab("live"),
        tst_w_abs_w(STAGE_ANIM_REQUEST_B0E),
        bcc(BEQ_W, "arm-event"),
        # $1f66 — THE TRANSITION, the one animation here with two tables and an EQUALITY wrap
        lea_abs_l(A1, TRANSITION_CURSOR),
        move_w_postinc_dn(D0, A1),
        tst_w_abs_l(EFFECT_STATE_21E4),
        bcc(BEQ_W, "transition-frame"),
        lea_d16(A1, TRANSITION_TABLE_BYTES, A1),
        lab("transition-frame"),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        cmp_w_imm_dn(D0, TRANSITION_TABLE_BYTES),
        bcc(BNE_W, "transition-store"),
        clr_w_dn(D0),
        lab("transition-store"),
        move_w_dn_abs_l(D0, TRANSITION_CURSOR),
        bcc(BNE_W, "transition-out"),
        move_w_imm_abs_w(EVENT_DONE_SET, STAGE_ANIM_DONE_B10),
        lab("transition-out"),
        RTS,
        # $1fa2 — the arm WB_EVENT_ANIM_DONE_B16 gates
        lab("arm-event"),
        tst_w_abs_w(EVENT_ANIM_DONE_B16),
        bcc(BEQ_W, "arm-death"),
    ] + _anim32_pieces(EVENT_ANIM_CURSOR, STAGE_ANIM_DONE_B18) + [
        # $1fd6 — the death animation, which has no completion flag of its own
        lab("arm-death"),
        tst_w_abs_w(STAGE_RESET_BLOCK),
        bcc(BEQ_W, "arm-hurt"),
    ] + _anim32_pieces(DEATH_ANIM_CURSOR, None) + [
        # $1ffc — the HURT arm, whose SUPPORTED path falls through to the selector by way of a
        # `bsr` into a bare `rts`
        lab("arm-hurt"),
        bit_op_d16(BTST_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bcc(BEQ_W, "select"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "hurt"),
        bsr_label("tail-rts"),
        bcc(BRA_W, "select"),
        lab("hurt"),
        cmpi_w_abs_l(POSTURE_STATE_ONE, EFFECT_STATE_21E4),
        bcc(BNE_W, "hurt2"),
    ] + _hurt_pair_pieces("hurt", HURT_SPRITE_LEFT, HURT_SPRITE_RIGHT, fall_through=False) + [
        lab("hurt2"),
    ] + _hurt_pair_pieces("hurt2", HURT2_SPRITE_LEFT, HURT2_SPRITE_RIGHT, fall_through=True) + [
        lab("tail-rts"),
        RTS,
        # $205e — pick the posture record WB_EFFECT_STATE_21E4 names
        lab("select"),
        tst_w_abs_l(EFFECT_STATE_21E4),
        bcc(BNE_W, "state-nonzero"),
        lea_abs_l(A6, POSTURE_TABLE_0),
        bcc(BRA_W, "picked"),
        lab("state-nonzero"),
        cmpi_w_abs_l(POSTURE_STATE_ONE, EFFECT_STATE_21E4),
        bcc(BNE_W, "state-other"),
        lea_abs_l(A6, POSTURE_TABLE_1),
        bcc(BRA_W, "picked"),
        lab("state-other"),
        lea_abs_l(A6, POSTURE_TABLE_2),
        lab("picked"),
        tst_w_abs_w(TILE_33_MODE),
        bcc(BEQ_W, "swing"),
        # $2096 — THE LADDER, whose table is the eight bytes below
        lea_abs_l(A1, LADDER_SPRITES),
        moveq(0, D0),
        move_b_d16_dn(D0, A0, FIELD_18),
        andi_b_dn(D0, LADDER_SPRITE_MASK),
        leaf.lea_indexed(A1, D0),
        move_w_ind_d16(A1, A0, ACTOR_SPRITE),
        tst_w_abs_w(TILE_33_STEP),
        bcc(BEQ_W, "ladder-out"),
        addq_b_d16(ANIM_FRAME_BYTES, A0, FIELD_18),
        andi_b_d16(A0, LADDER_SPRITE_MASK, FIELD_18),
        lab("ladder-out"),
        RTS,
        # $20c2 — DATA: four climbing frames, two sprite ids held twice each
        word(LADDER_SPRITE_A) + word(LADDER_SPRITE_A)
        + word(LADDER_SPRITE_B) + word(LADDER_SPRITE_B),
        # $20ca — THE SWING, and the SFX id that becomes the frame index
        lab("swing"),
        bit_op_d16(BTST_IMM, FIRED_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "posture"),
        tst_w_abs_l(EFFECT_STATE_21E4),
        bcc(BEQ_W, "posture"),
        move_w_abs_l_dn(D0, ATTACK_CURSOR),
        bcc(BNE_W, "swing-table"),
        move_w_imm_dn(D0, ATTACK_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        lab("swing-table"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "swing-left"),
        lea_abs_l(A1, ATTACK_TABLE_RIGHT),
        bcc(BRA_W, "swing-frame"),
        lab("swing-left"),
        lea_abs_l(A1, ATTACK_TABLE_LEFT),
        lab("swing-frame"),
        move_w_indexed_d16(A1, D0, A0, ACTOR_SPRITE),
        addi_w_dn(D0, ANIM_FRAME_BYTES),
        andi_w_dn(D0, ATTACK_MASK),
        move_w_dn_abs_l(D0, ATTACK_CURSOR),
        bcc(BNE_W, "swing-out"),
        bit_op_d16(BCLR_IMM, FIRED_BIT, A0, ACTOR_FLAGS),
        lab("swing-out"),
        RTS,
        # $2132 — THE POSTURE SELECTOR. MOVING and LAUNCHED are ONE question
        lab("posture"),
        bit_op_d16(BTST_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "jump"),
        bit_op_d16(BTST_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "fall-test"),
        lab("jump"),
    ] + _posture_pair_pieces("jump", POSTURE_JUMP_LEFT, POSTURE_JUMP_RIGHT) + [
        lab("fall-test"),
        bit_op_d16(BTST_IMM, FALLING_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "walk-test"),
    ] + _posture_pair_pieces("fall", POSTURE_FALL_LEFT, POSTURE_FALL_RIGHT) + [
        lab("walk-test"),
        bit_op_d16(BTST_IMM, MOVED_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "walk"),
    ] + _posture_pair_pieces("idle", POSTURE_IDLE_LEFT, POSTURE_IDLE_RIGHT,
                             right_is_indirect=True) + [
        lab("walk"),
        bit_op_d16(BTST_IMM, SIDE_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "walk-right"),
    ] + _walk_cycle_pieces(POSTURE_WALK_LEFT) + [
        lab("walk-right"),
    ] + _walk_cycle_pieces(POSTURE_WALK_RIGHT)


ENTRY_PIECES = {
    "player_meter_empty_check": _meter_empty_pieces(),
    "player_jump_step": _jump_step_pieces(),
    "player_apply_joystick": _apply_joystick_pieces(),
    "player_reset_ground_state": _reset_ground_pieces(),
    "scene_copy_record_fields": _copy_record_pieces(),
    "player_step_and_arm": _step_and_arm_pieces(),
    "player_weapon_fire": _weapon_fire_pieces(),
    "player_stage_transition": _stage_transition_pieces(),
}
RECONSTRUCTED_ROUTINES = 8

ENTRY_BYTES = {name: leaf.asm(leaf.entry_of(name), pieces)
               for name, pieces in ENTRY_PIECES.items()}
INSN_COUNT = {name: leaf.instruction_count(pieces) for name, pieces in ENTRY_PIECES.items()}

# The two callees this file's bodies reach, as upper bounds on one call. Both belong to other
# batteries; `joy1_newly_pressed`'s body is five instructions and test_input.py pins it, and the SFX
# stub's cap comes from the battery that owns the sound module.
from test_sound import STUB_INSN_CAP    # noqa: E402
JOY_EDGE_INSNS = 8


def _cap(name, extra=0):
    """A run's instruction cap, DERIVED from the pin: every instruction of the body once, plus the
    runner's sentinel, plus whatever a callee adds. Nothing here states a round number."""
    return INSN_COUNT[name] + leaf.RUNNER_SENTINEL_INSN + extra


JUMP_STEP_CAP = _cap("player_jump_step", extra=JOY_EDGE_INSNS + STUB_INSN_CAP)
# The death arm's is the widest here: the trigger's stub on one arm, stub +0 and the whole song start
# on the other, so the cap carries both rather than being split per arm.
METER_EMPTY_CAP = _cap("player_meter_empty_check", extra=STUB_INSN_CAP + PLAY_SONG_INSN_CAP)


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


# The extents, so a pin that stopped one instruction short fails here rather than leaving the tail
# unpinned. Each is bounded by the next routine's own entry or by the data that follows it.
BODY_SIZES = {
    "player_meter_empty_check": 146,    # $a76..$b07, bounded by WB_STAGE_RESET_BLOCK's 18 bytes
    "player_apply_joystick": 130,       # $d84..$e05 — and NOT on to $e06: the `rts` at $e04 is its
                                        # own, which is the plate correction batch 40 phase A made
    "player_jump_step": 194,            # $e06..$ec7, bounded by player_step_and_arm's entry
    "player_step_and_arm": 436,         # $ec8..$107b, bounded by player_reset_ground_state's entry
    "player_reset_ground_state": 38,    # $107c..$10a1, bounded by actor_step_left_against_map
    "player_weapon_fire": 300,          # $1208..$1333, bounded by actor_fall_and_settle's entry —
                                        # and the last TWO of those bytes are the packed-BCD 1 the
                                        # routine's own `sbcd` reads, not code
    "scene_copy_record_fields": 30,     # $539e..$53bb, bounded by actor_behavior_type36's entry
    "player_stage_transition": 656,     # $1f54..$21e3, bounded by the 466 bytes of DATA above it —
                                        # and EIGHT of those 656 are data too, the ladder's own
                                        # frame table at $20c2
}


@pytest.mark.parametrize("name", sorted(BODY_SIZES), ids=sorted(BODY_SIZES))
def test_the_pin_is_the_whole_body(name):
    assert len(ENTRY_BYTES[name]) == BODY_SIZES[name], (
        f"{name}'s pin covers {len(ENTRY_BYTES[name])} bytes of a {BODY_SIZES[name]}-byte body")


# --- the census: how each of these routines is reached ----------------------------------------------
# "Reached only from the player's frame" is what ../names.txt's plates say, and batch 31's hidden
# `jsr $6f9e.w` is why it is measured rather than assumed. The scan is test_behavior.py's — every way
# an instruction can name an address, keyed by target — and it is imported rather than restated so
# the two censuses cannot disagree about the same instruction.
from test_behavior import (CONTROL_FLOW_TARGETS, PC_RELATIVE_SOURCE_TARGETS,   # noqa: E402
                           _operand_sites)

CALLERS = {
    # the frame's own `bsr`s, at $a38..$a73
    "player_meter_empty_check": (0xa38,),
    "player_step_and_arm": (0xa4a,),
    "player_weapon_fire": (0xa4e,),
    "player_apply_joystick": (0xa60,),
    # $e06 has exactly ONE entrance and it is the gate's `beq.w`, which is what retires the plate's
    # claim that player_apply_joystick "also falls into" it.
    "player_jump_step": (0xd7e,),
    # ...and $107c has TWO, both inside player_step_and_arm's walk arms.
    "player_reset_ground_state": (0xfb2, 0x101e),
    "scene_copy_record_fields": (0xc5e,),
    # ...and the LAST call has TWO callers: the frame's own `bsr` and the one on nearly every arm of
    # `player_pending_event_gate`.
    "player_stage_transition": (0xa70, 0xbb0),
}


@pytest.mark.parametrize("name", sorted(CALLERS), ids=sorted(CALLERS))
def test_each_routine_is_named_by_exactly_the_instructions_the_plate_says(name):
    entry = leaf.entry_of(name)
    assert tuple(sorted(CONTROL_FLOW_TARGETS.get(entry, []))) == CALLERS[name], (
        f"{name} @ {entry:#x} is named by "
        f"{[hex(at) for at in CONTROL_FLOW_TARGETS.get(entry, [])]}, not {CALLERS[name]}")


@pytest.mark.parametrize("name", sorted(CALLERS), ids=sorted(CALLERS))
def test_no_pc_relative_read_anywhere_in_the_program_names_one_of_these_entries(name):
    """The NEGATIVE half, and the one the mode-shaped sweep exists for: not even a scan that decodes
    every word in the program as a PC-relative read finds one aimed here."""
    entry = leaf.entry_of(name)
    assert entry not in PC_RELATIVE_SOURCE_TARGETS, (
        f"{name} @ {entry:#x} is read PC-relatively by "
        f"{[hex(at) for at, _op in PC_RELATIVE_SOURCE_TARGETS[entry]]}")


# --- $107c: leaving the ladder ------------------------------------------------------------------
_RESET_GROUND = leaf.register_glue("player_reset_ground_state", [ctypes.c_uint32])


@pytest.mark.parametrize("strength,flags", [(0x0000, 0x00), (0x0021, 0xff), (0x00f8, 1 << MOVING_BIT),
                                            (0xff7f, 0x00)],
                         ids=["zero", "all-flags", "byte-wrap", "high-half"])
def test_leaving_the_ladder_puts_the_record_back_into_a_fall(strength, flags):
    """`byte-wrap` is the row the operand size turns on: `addq.b #8,d0` over a state word of $f8
    leaves ZERO in the byte and does NOT carry into the high half, so the speed stamped is 0 and not
    $100. `high-half` says the same from the other side — only the low byte is read."""
    what = f"player_reset_ground_state strength={strength:#06x} flags={flags:#04x}"
    pokes = _pokes(what, {TILE_33_MODE: word(TILE_33_MODE_DOWN),
                          EFFECT_STATE_BD6A: word(strength),
                          ACTOR + ACTOR_FLAGS: bytes([flags]),
                          ACTOR + SPEED: bytes([MARKER])})

    expected = {}
    _put_word(expected, TILE_33_MODE, 0)
    expected[ACTOR + ACTOR_FLAGS] = (flags & ~(1 << SUPPORTED_BIT)) | (1 << MOVING_BIT) \
        | (1 << LAUNCHED_BIT)
    expected[ACTOR + SPEED] = (strength + JUMP_STRENGTH_BIAS) & 0xff

    info = leaf.run("player_reset_ground_state", _RESET_GROUND(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=_cap("player_reset_ground_state"))
    _assert_writes(info, expected, what)


# --- $d84: the ladder -------------------------------------------------------------------------------
_APPLY_JOYSTICK = leaf.register_glue("player_apply_joystick", [ctypes.c_uint32])


def _run_ladder(what, pokes, expected):
    info = leaf.run("player_apply_joystick", _APPLY_JOYSTICK(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=_cap("player_apply_joystick"))
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("held", [0x00, 1 << JOY1_UP_BIT, 1 << JOY1_DOWN_BIT, 0xff],
                         ids=["idle", "up", "down", "everything"])
def test_the_ladder_does_nothing_but_lower_the_step_flag_while_the_tile_flag_is_down(held):
    """The gate is WB_TILE_33_FLAG and not the joystick: with the flag down, every direction —
    including both at once — clears WB_TILE_33_STEP and returns."""
    what = f"player_apply_joystick flag down held={held:#04x}"
    pokes = _pokes(what, {TILE_33_FLAG: word(0), JOY1_CURRENT: bytes([held])})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    _run_ladder(what, pokes, expected)


def test_neither_direction_held_on_a_ladder_clears_the_step_flag_too():
    """The third path to the same two bytes, and the one that says the arms are exclusive rather
    than the flag being the only test."""
    what = "player_apply_joystick on a ladder, idle"
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff), JOY1_CURRENT: bytes([0])})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    _run_ladder(what, pokes, expected)


@pytest.mark.parametrize("x", [0x0100, 0x0101, 0x010f, 0x0108],
                         ids=["even-aligned", "odd", "cell-top", "already-centred"])
@pytest.mark.parametrize("held,mode,step", [(1 << JOY1_UP_BIT, TILE_33_MODE_UP, -1),
                                            (1 << JOY1_DOWN_BIT, TILE_33_MODE_DOWN, +1)],
                         ids=["up", "down"])
def test_climbing_snaps_the_x_to_the_ladders_centre_and_keeps_its_low_bit(x, held, mode, step):
    """`andi.w #$fff1,(a0)` KEEPS BIT 0 — the mask is not $fff0 — so an odd x is still odd after the
    snap; the `odd` row is what a port that rounded to the cell would fail. The two arms differ in
    the mode word they publish and in the direction of the y step, and in nothing else."""
    what = f"player_apply_joystick climb mode={mode:#06x} x={x:#06x}"
    y, flags = 0x0141, 0xff
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff), JOY1_CURRENT: bytes([held]),
                          ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                          ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {}
    expected[ACTOR + ACTOR_FLAGS] = flags & ~((1 << MOVING_BIT) | (1 << LAUNCHED_BIT))
    _put_word(expected, TILE_33_STEP, TILE_33_STEP_RAISED)
    _put_word(expected, ACTOR + ACTOR_X, (x & LADDER_X_MASK) + LADDER_X_BIAS)
    _put_word(expected, TILE_33_MODE, mode)
    _put_word(expected, ACTOR + ACTOR_Y, (y + step * LADDER_STEP) & LADDER_Y_MASK)
    _run_ladder(what, pokes, expected)


def test_holding_both_directions_climbs_UP_because_bit_0_is_tested_first():
    """The order of the two `btst`s, as a case: nothing else in the routine separates them."""
    what = "player_apply_joystick both directions"
    x, y = 0x0100, 0x0140
    pokes = _pokes(what, {TILE_33_FLAG: word(0xffff),
                          JOY1_CURRENT: bytes([(1 << JOY1_UP_BIT) | (1 << JOY1_DOWN_BIT)]),
                          ACTOR + ACTOR_X: word(x), ACTOR + ACTOR_Y: word(y),
                          ACTOR + ACTOR_FLAGS: bytes([0])})

    expected = {}
    expected[ACTOR + ACTOR_FLAGS] = 0
    _put_word(expected, TILE_33_STEP, TILE_33_STEP_RAISED)
    _put_word(expected, ACTOR + ACTOR_X, (x & LADDER_X_MASK) + LADDER_X_BIAS)
    _put_word(expected, TILE_33_MODE, TILE_33_MODE_UP)
    _put_word(expected, ACTOR + ACTOR_Y, (y - LADDER_STEP) & LADDER_Y_MASK)
    _run_ladder(what, pokes, expected)


def test_the_two_ladder_modes_are_different_words_and_the_case_above_can_tell_them_apart():
    """A guard on the seeding, not on the game: if the two mode constants were equal the parametrised
    case above would pin neither arm's publish."""
    assert TILE_33_MODE_UP != TILE_33_MODE_DOWN
    assert TILE_33_MODE_UP != 0 and TILE_33_MODE_DOWN != 0


# --- $e06: the jump machine ---------------------------------------------------------------------
_JUMP_STEP = leaf.register_glue("player_jump_step", [ctypes.c_uint32])
STRENGTH = 0x0021          # a state word whose low byte + the bias is neither 0 nor the seed


def _jump_pokes(what, flags, fields=None):
    base = {ACTOR + ACTOR_FLAGS: bytes([flags]),
            ACTOR + FIELD_10: bytes([MARKER]),
            ACTOR + SPEED: bytes([MARKER]),
            EFFECT_STATE_BD6A: word(STRENGTH),
            HUD_SLOT_BBC2: bytes([0]),
            JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([0])}
    return _pokes(what, leaf.overlay(base, fields or {}))


def _jump_head(expected):
    """The two bytes every arm writes before the three-way test."""
    _put_word(expected, TILE_33_STEP, 0)
    expected[ACTOR + FIELD_10] = (STRENGTH + JUMP_STRENGTH_BIAS) & 0xff
    return expected


def _run_jump(what, pokes, expected, extra_band=()):
    info = leaf.run("player_jump_step", _JUMP_STEP(ACTOR),
                    merge_bands(expected) + list(extra_band), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=JUMP_STEP_CAP)
    _assert_writes(info, expected, what)
    return info


@pytest.mark.parametrize("strength", [0x0000, 0x0021, 0x00f8, 0xff01],
                         ids=["zero", "ordinary", "byte-wrap", "high-half"])
def test_every_frame_restamps_the_jump_strength_from_the_state_word(strength):
    """`addi.b #$8,d0` on the LOW BYTE of WB_EFFECT_STATE_BD6A — the same number
    player_reset_ground_state adds with `addq.b`, and the same wrap. The record is seeded AIRBORNE
    with no wing-boot charge, so the head is the whole of the frame."""
    what = f"player_jump_step head strength={strength:#06x}"
    pokes = _jump_pokes(what, flags=0, fields={EFFECT_STATE_BD6A: word(strength)})

    expected = {}
    _put_word(expected, TILE_33_STEP, 0)
    expected[ACTOR + FIELD_10] = (strength + JUMP_STRENGTH_BIAS) & 0xff
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("speed", [2, 8, 0xff], ids=lambda v: f"speed{v:#04x}")
def test_an_ascending_record_rises_by_its_own_speed_and_spends_one(speed):
    """`sub.w d0,2(a0)` on a ZERO-EXTENDED byte, so the record always rises — a speed of $ff lifts it
    255 pixels rather than dropping it one."""
    what = f"player_jump_step ascending speed={speed:#04x}"
    y = 0x0140
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={ACTOR + SPEED: bytes([speed]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, (y - speed) & 0xffff)
    expected[ACTOR + SPEED] = speed - 1
    _run_jump(what, pokes, expected)


def test_the_ascent_ends_on_the_frame_the_speed_reaches_zero():
    """...and what it leaves behind is a speed of 1, which is what makes the record start falling at
    one pixel a frame rather than at none."""
    what = "player_jump_step ascent ending"
    y, flags = 0x0140, (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)
    pokes = _jump_pokes(what, flags=flags,
                        fields={ACTOR + SPEED: bytes([1]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - 1)
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << MOVING_BIT)
    _run_jump(what, pokes, expected)


def test_an_ascent_entered_on_a_zero_speed_wraps_the_byte_instead_of_ending():
    """`subq.b #1` on $00 is $ff, and the `bne` reads THAT — so the climb does not end, it runs for
    another 255 frames. The row a port that tested the byte BEFORE the decrement would fail."""
    what = "player_jump_step ascent on a zero speed"
    y = 0x0140
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={ACTOR + SPEED: bytes([0]), ACTOR + ACTOR_Y: word(y)})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = 0xff
    # The y IS in the expected set even though it does not change: `sub.w d0,2(a0)` with d0 = 0
    # STORES the value already there, and the oracle's ledger records the store rather than the
    # difference — so a port that skipped the subtraction on a zero speed would redden here.
    _put_word(expected, ACTOR + ACTOR_Y, y)
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("prev,current", [(0, 0), (1 << JOY1_UP_BIT, 1 << JOY1_UP_BIT), (0xff, 0xff),
                                          (0, 1 << JOY1_DOWN_BIT)],
                         ids=["idle", "held", "everything-held", "wrong-direction"])
def test_a_standing_record_needs_a_RISING_up_edge_to_launch(prev, current):
    """`bsr $682 / btst #0,d0` — the EDGE, not the level: a stick already up when the frame begins
    launches nothing. The `everything-held` row is what separates the edge test from a level one."""
    what = f"player_jump_step standing prev={prev:#04x} current={current:#04x}"
    pokes = _jump_pokes(what, flags=1 << SUPPORTED_BIT,
                        fields={JOY1_PREV: bytes([prev]), JOY1_CURRENT: bytes([current])})

    _run_jump(what, pokes, _jump_head({}))


def test_the_launch_fires_its_effect_and_loads_the_speed_from_the_strength_byte():
    """The whole of the launch: the SFX through stub +56 (whose write set comes from the battery that
    owns the trigger), the two motion bits up, the supported bit down, and WB_ACTOR_SPEED loaded from
    the byte the HEAD of this same frame has just written — so the height is this frame's."""
    what = "player_jump_step launching"
    flags = 1 << SUPPORTED_BIT
    pokes = _jump_pokes(what, flags=flags,
                        fields={JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})
    image = harness.make_image(pokes)

    expected = _jump_head({})
    expected.update(_sfx_bytes(image, JUMP_SFX, SND_CHANNEL_A))
    expected[ACTOR + ACTOR_FLAGS] = (flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) \
        & ~(1 << SUPPORTED_BIT)
    expected[ACTOR + SPEED] = (STRENGTH + JUMP_STRENGTH_BIAS) & 0xff
    _run_jump(what, pokes, expected)


def test_a_STANDING_record_with_wing_boots_burns_NONE_of_them():
    """THE THREE ARMS ARE EXCLUSIVE, which no case here said until the independent gate asked. Every
    hover case seeds the record airborne and every launch case seeds an empty slot, so a port that
    ran the hover BELOW the launch instead of instead of it answered the same on all of them — and
    the state it gets wrong is ordinary: the frame after landing with boots still on, where the
    charge would burn away while the player stands still.

    The seed is SUPPORTED with a full slot and UP HELD but not newly pressed, so the launch arm is
    entered and declines, and the whole frame must be the head."""
    what = "player_jump_step standing on wing boots"
    charge = 4
    pokes = _jump_pokes(what, flags=1 << SUPPORTED_BIT,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    _run_jump(what, pokes, _jump_head({}))


def test_an_ASCENDING_record_with_wing_boots_burns_none_of_them_either():
    """...and the same for the first arm, which the same mutant also reaches: a rising record with a
    full slot spends its own speed and none of the charge."""
    what = "player_jump_step ascending on wing boots"
    y, charge, speed = 0x0140, 4, 3
    pokes = _jump_pokes(what, flags=1 << MOVING_BIT,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                ACTOR + SPEED: bytes([speed]), ACTOR + ACTOR_Y: word(y),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - speed)
    expected[ACTOR + SPEED] = speed - 1
    _run_jump(what, pokes, expected)


def test_the_ascending_bit_is_tested_before_the_supported_one():
    """A record carrying BOTH takes the ascent, which is what says the three arms are ordered rather
    than exclusive by construction — and a launch would have been visible, because this seed also
    supplies the rising edge the launch needs."""
    what = "player_jump_step ascending and supported"
    y = 0x0140
    flags = (1 << MOVING_BIT) | (1 << SUPPORTED_BIT)
    pokes = _jump_pokes(what, flags=flags,
                        fields={ACTOR + SPEED: bytes([4]), ACTOR + ACTOR_Y: word(y),
                                JOY1_PREV: bytes([0]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    _put_word(expected, ACTOR + ACTOR_Y, y - 4)
    expected[ACTOR + SPEED] = 3
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("charge,held", [(0, 1 << JOY1_UP_BIT), (3, 0), (0, 0)],
                         ids=["no-charge", "not-held", "neither"])
def test_the_wing_boots_need_a_charge_AND_the_stick_held(charge, held):
    """Two tests in series, and this is both of their negatives."""
    what = f"player_jump_step hover charge={charge} held={held:#04x}"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]), JOY1_CURRENT: bytes([held])})

    _run_jump(what, pokes, _jump_head({}))


def test_the_wing_boots_read_the_stick_HELD_and_not_its_rising_edge():
    """The row that separates `btst #0,$8cf.w` from the `bsr $682 / btst #0,d0` one instruction
    arm up: the stick was ALREADY up last frame, so there is no edge — and the boots still burn. Every
    other hover case seeds a clear previous frame, where the two readings answer the same."""
    what = "player_jump_step hovering with the stick already up"
    charge = 4
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_PREV: bytes([1 << JOY1_UP_BIT]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[HUD_SLOT_BBC2] = charge - 1
    _run_jump(what, pokes, expected)


@pytest.mark.parametrize("charge", [2, 0x80, 0xff], ids=lambda v: f"charge{v:#04x}")
def test_the_wing_boots_hold_the_fall_at_one_pixel_and_spend_a_charge(charge):
    """Every frame the stick is held: the fall speed forced to 1 and one charge off the slot's VALUE
    byte, which is a BYTE write into the low half of a slot whose other half is the redraw request."""
    what = f"player_jump_step hovering charge={charge:#04x}"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([charge]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    expected[HUD_SLOT_BBC2] = charge - 1
    _run_jump(what, pokes, expected)


def test_the_last_charge_rearms_the_slot_and_posts_the_message_that_names_it():
    """WHAT THE SLOT IS, as a case: message WB_TEXT_MESSAGE_WING_BOOTS_LOST is "You lost wing boots."
    and this is the only routine that posts it. The rearm is a WORD, so the value goes back to zero
    and the request byte beside it comes up — WB_HUD_SLOT_REARM, the same word both damage paths
    write."""
    what = "player_jump_step spending the last wing-boot charge"
    pokes = _jump_pokes(what, flags=0,
                        fields={HUD_SLOT_BBC2: bytes([1]),
                                JOY1_CURRENT: bytes([1 << JOY1_UP_BIT])})

    expected = _jump_head({})
    expected[ACTOR + SPEED] = SPEED_AFTER_JUMP
    _put_word(expected, HUD_SLOT_BBC2, HUD_SLOT_REARM)
    expected[TEXT_REQUEST] = MESSAGE_WING_BOOTS_LOST
    _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    _run_jump(what, pokes, expected)


def test_the_message_the_wing_boots_post_is_the_one_the_shipped_string_names():
    """The id is 1-based into WB_TEXT_MESSAGE_TABLE, so the claim above is checkable against the
    image's own bytes rather than against this battery's reading of them."""
    table = wb("TEXT_MESSAGE_TABLE")
    first = wb("TEXT_MESSAGE_FIRST_ID")
    shift = wb("TEXT_MESSAGE_PTR_SHIFT")
    at = table + (MESSAGE_WING_BOOTS_LOST - first) * (1 << shift)
    where = int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")
    text = bytes(harness.BASE_IMAGE[where:where + 32])
    assert b"wing boots" in text.lower(), f"message {MESSAGE_WING_BOOTS_LOST:#x} reads {text!r}"


# --- $a76: the death check --------------------------------------------------------------------------
_METER_EMPTY = leaf.register_glue("player_meter_empty_check", [ctypes.c_uint32])


def _death_pokes(what, fields=None):
    """The death check's own inputs, and the sound module's state seeded AWAY from what a song start
    writes so that each of its stores is a change rather than a coincidence."""
    base = {ACTOR + ACTOR_FLAGS: bytes([0xff]),
            HUD_METER_VALUE: word(0),
            HUD_SLOT_BBC6: bytes([0]),
            STAGE_RESET_BLOCK: word(0),
            STATE_FLAG_A34: word(MARKER),
            SCROLL_FOLLOW_FROZEN: word(MARKER),
            PANEL_FRAME_HOLD: word(MARKER)}
    salt = case_salt(what)
    base.update({lo: keyed_block(lo, length, salt) for lo, length in PLAY_SONG_SEEDED_BANDS})
    return _pokes(what, leaf.overlay(base, fields or {}))


@pytest.mark.parametrize("meter", [1, 0x14, 0xffff], ids=lambda v: f"meter{v:#06x}")
def test_a_meter_with_anything_left_in_it_makes_the_whole_routine_a_no_op(meter):
    """`tst.w $b6fa / bne` — the routine's first instruction, and on all but one frame of a life the
    whole of it."""
    what = f"player_meter_empty_check meter={meter:#06x}"
    pokes = _death_pokes(what, {HUD_METER_VALUE: word(meter)})

    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    assert not program_writes(info), f"{what}: the check wrote memory on a live meter"


def _revive_expected(image, rearm):
    expected = _sfx_bytes(image, DEATH_SFX, SND_CHANNEL_A)
    if rearm:
        _put_word(expected, HUD_SLOT_BBC6, HUD_SLOT_REARM)
    expected[TEXT_REQUEST] = MESSAGE_REVIVAL_USED
    _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    _put_word(expected, HUD_METER_VALUE, METER_REVIVE)
    return expected


@pytest.mark.parametrize("charge", [1, 0x80, 0xff], ids=lambda v: f"charge{v:#04x}")
def test_an_empty_meter_with_a_revival_medicine_spends_it_and_refills(charge):
    """WHAT THE SLOT IS: message WB_TEXT_MESSAGE_REVIVAL_USED is "Used the revival medicine." and
    this is its only writer. Note the meter comes back on WB_PLAYER_METER_REVIVE and not on
    WB_HUD_METER_MAX — a revived player gets twenty units whatever the maximum is."""
    what = f"player_meter_empty_check reviving charge={charge:#04x}"
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: bytes([charge])})
    image = harness.make_image(pokes)

    expected = _revive_expected(image, rearm=True)
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


# --- THE ONE ARM NO CASE HERE CAN DRIVE, and why -------------------------------------------------
#
# WB_KEY_SEQUENCE_MATCHED steers both of the death check's tests — a raised word takes the revival
# arm with an EMPTY medicine slot and then SKIPS the rearm, so a cheating player revives for ever —
# and no case in this file can put a value there. The word lives at $604, inside the kit's
# harness-poked input block ($600..$61f), which for this project lies inside the game's own program
# because it loads at $3f8. `harness.make_image` REFUSES any poke landing in that block, and it is
# right to: nothing can tell a poke staging kit model state from one patching the program at the
# same address (test_poked_input_guard.py owns the waiver and its three guards).
#
# So the two cases below state the limitation instead of hiding it. What the differential DOES cover
# is the ordinary machine: the shipped word is zero, every case above runs on that, and the arm they
# drive is the medicine slot's own. The cheat arm is reproduced in src/player.c and is UNPINNED.


def test_a_REARMED_medicine_slot_is_an_empty_one_to_this_test():
    """`tst.b $bbc6.l` reads the slot's VALUE byte, not the word: a slot holding WB_HUD_SLOT_REARM —
    value zero with the redraw request beside it up — is EMPTY here and the frame dies. The row that
    separates the byte test from a word one, and the only seed in this file that puts anything in a
    slot's second byte."""
    what = "player_meter_empty_check on a rearmed medicine slot"
    flags = 0xff
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: word(HUD_SLOT_REARM),
                                STAGE_RESET_BLOCK: word(0xffff),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {ACTOR + ACTOR_FLAGS: flags & ~(1 << FLICKER_BIT)}
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


def test_the_cheat_word_is_zero_in_the_shipped_image_so_every_case_here_runs_without_it():
    """Which is what makes the revival cases above the SLOT's arm rather than the cheat's."""
    at = KEY_SEQUENCE_MATCHED
    assert int.from_bytes(harness.BASE_IMAGE[at:at + WORD_BYTES], "big") == 0


def test_the_cheat_word_cannot_be_SEEDED_because_it_shares_the_poked_input_block():
    """The limitation, as a tripwire. If the kit's block ever moves clear of this program — or the
    project's load base rises — this case fails and the arm above becomes drivable, which is exactly
    when someone should come back and write the differential this comment stands in for."""
    with pytest.raises(RuntimeError, match="harness-poked input block"):
        harness.make_image({KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET)})


def test_a_death_already_in_progress_only_lowers_the_flicker_bit():
    """`tst.w $b08 / bmi` is a SIGN test and not a zero one: the word this arm raises is $ffff, so a
    second death on a later frame stops at the test. Everything below it — the song, the three
    words — is therefore missing from the write set."""
    what = "player_meter_empty_check on a death already in progress"
    flags = 0xff
    pokes = _death_pokes(what, {STAGE_RESET_BLOCK: word(0xffff),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {ACTOR + ACTOR_FLAGS: flags & ~(1 << FLICKER_BIT)}
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)


@pytest.mark.parametrize("block", [0, 1, 0x7fff], ids=["zero", "one", "largest-positive"])
def test_the_death_arm_starts_the_song_and_raises_the_four_words(block):
    """THE ARM THAT REACHES THE SOUND MODULE, through stub +0 with d0 = WB_PLAYER_DEATH_SONG. What
    the frame writes is snd_play_song's whole write set — taken from the battery that OWNS it — plus
    the flicker bit and the four words. `largest-positive` is the row that says the guard above is a
    SIGN test: $7fff is not negative, so the death runs."""
    what = f"player_meter_empty_check dying block={block:#06x}"
    flags = 0xff
    pokes = _death_pokes(what, {STAGE_RESET_BLOCK: word(block),
                                ACTOR + ACTOR_FLAGS: bytes([flags])})
    image = harness.make_image(pokes)

    song = model_play_song(image, DEATH_SONG)
    expected = {addr + index: value[index]
                for addr, value in song.items() for index in range(len(value))}
    expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << FLICKER_BIT)
    for global_word in (STATE_FLAG_A34, STAGE_RESET_BLOCK, SCROLL_FOLLOW_FROZEN, PANEL_FRAME_HOLD):
        _put_word(expected, global_word, DEATH_FLAG_SET)

    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP,
                    psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    _assert_writes(info, expected, what)


def test_the_message_the_revival_arm_posts_is_the_one_the_shipped_string_names():
    """The other half of the pair above, read off the image."""
    table = wb("TEXT_MESSAGE_TABLE")
    first = wb("TEXT_MESSAGE_FIRST_ID")
    shift = wb("TEXT_MESSAGE_PTR_SHIFT")
    at = table + (MESSAGE_REVIVAL_USED - first) * (1 << shift)
    where = int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")
    text = bytes(harness.BASE_IMAGE[where:where + 40])
    assert b"revival" in text.lower(), f"message {MESSAGE_REVIVAL_USED:#x} reads {text!r}"


# --- $539e: the event actor's spawn -----------------------------------------------------------------
_COPY_RECORD = leaf.register_glue("scene_copy_record_fields", [ctypes.c_uint32] * 2)

# Where a case puts the scene descriptor and the record being filled. Both are ordinary table slots,
# so the copy's destination has a seeded margin either side exactly as every other case's record has.
SCENE = TABLE_DEFAULT + 1 * RECORD_BYTES
DESTINATION = TABLE_DEFAULT + 8 * RECORD_BYTES
COPY_SEEDED_LO = TABLE_DEFAULT
COPY_SEEDED_LEN = 10 * RECORD_BYTES


def _copy_pokes(what, template):
    salt = case_salt(what)
    return {COPY_SEEDED_LO: keyed_block(COPY_SEEDED_LO, COPY_SEEDED_LEN, salt),
            RECORD_PTR_10420: SCENE.to_bytes(LONGWORD_BYTES, "big"),
            template: keyed_block(template, RECORD_BYTES, salt ^ 1)}


def _image_long(image, at):
    return int.from_bytes(image[at:at + LONGWORD_BYTES], "big")


@pytest.mark.parametrize("template", [TYPE35_TEMPLATE, TABLE_DEFAULT + 15 * RECORD_BYTES],
                         ids=["shipped", "seeded"])
def test_the_copy_is_eight_longwords_and_the_first_is_the_SCENES(template):
    """The plate said "20(record_ptr) and four following longwords"; it is SEVEN following, and the
    `lea 4(a1),a1` between them means the template's own first longword is never read. Both halves
    are asserted: the destination's x,y is the scene descriptor's, and its remaining 28 bytes are the
    template's bytes 4..31.

    The `shipped` row runs it on the real WB_ACTOR_TYPE35_TEMPLATE, which is what
    player_pending_event_gate hands it; the `seeded` row proves the routine reads a1 rather than that
    address."""
    what = f"scene_copy_record_fields template={template:#x}"
    pokes = _copy_pokes(what, template)
    image = harness.make_image(pokes)

    expected = {}
    _put_long(expected, DESTINATION, _image_long(image, SCENE + SCENE_SPAWN_POSITION))
    for i in range(TEMPLATE_LONGWORDS):
        _put_long(expected, DESTINATION + (i + 1) * LONGWORD_BYTES,
                  _image_long(image, template + SPAWN_TEMPLATE_UNREAD + i * LONGWORD_BYTES))

    info = leaf.run("scene_copy_record_fields", _COPY_RECORD(template, DESTINATION),
                    merge_bands(expected), what,
                    regs={"a1": template, "a2": DESTINATION, "_pokes": pokes},
                    max_insns=_cap("scene_copy_record_fields"))
    _assert_writes(info, expected, what)


def test_the_template_the_gate_hands_it_carries_the_slot_number_of_the_event_actor():
    """WHY THE FIRST LONGWORD IS UNREAD, from the shipped bytes: WB_ACTOR_TYPE35_TEMPLATE's first four
    bytes are where the record's x and y would be, and the scene's position takes their place. What
    the template really supplies begins at +4 with the TYPE word, which is the only shipped datum in
    the image that names a behaviour slot by number."""
    at = TYPE35_TEMPLATE + SPAWN_TEMPLATE_UNREAD
    assert int.from_bytes(harness.BASE_IMAGE[at:at + WORD_BYTES], "big") == 35, (
        "the template's type word is not slot 35's")


def _put_long(expected, addr, value):
    for index in range(LONGWORD_BYTES):
        expected[addr + index] = (value >> (8 * (LONGWORD_BYTES - 1 - index))) & 0xff


# ==================================================================================================
# $ec8: the walk — batch 40 phase B
# ==================================================================================================
#
# THE FIRST CASES IN THIS FILE THAT REACH THE COLLISION MAP, which is why the seeding below is wider
# than every case above it: four of the walk's five sections end in `bsr $10a2` or `bsr $1170`, and a
# probe reads a map cell, a stride word, a scroll limit and the mode flag that picks between the two
# maps. `map_pokes` comes from the battery that OWNS those probes — a second statement of "what a
# collision map looks like" could disagree with src/map.c while both stayed green.
#
# THE WRITE SETS ARE STILL STATED EXACTLY. A probe writes at most two things, WB_ACTOR_X and (for a
# WB_ACTOR_TYPE_PLAYER record only) WB_ACTOR_FIELD_22, and both are inside the record — so a case
# that seeds a CLEAR cell under the probe knows the whole of it without modelling $10a2's loop. The
# one case that seeds a BLOCKED row states the loop's own two writes instead, and says so.
from test_map import DEFAULT_STRIDE, MAP_CELLS, MAP_DEFAULT, map_pokes    # noqa: E402

CELL_SHIFT = wb("MAP_CELL_SHIFT")
TILE_BLOCK = wb("MAP_TILE_BLOCK")
STATE_FLAG_A32 = wb("STATE_FLAG_A32")
SCROLL_LIMIT_X = wb("BG_SCROLL_LIMIT_X")
TYPE_PLAYER = wb("ACTOR_TYPE_PLAYER")

# Where the walking cases put the record. The x sits well inside the map and the level, so neither
# probe's own edge arm fires and the whole of a step is the x it commits.
WALK_X = 0x0100
WALK_Y = 0x0080
WALK_HALF_WIDTH = 4
WIDE_LEVEL = 0x0800
# The row both probes read is `(y - 1) asr.w #4`, one above the record's own when the y is a cell
# boundary — so the cleared band starts there.
PROBE_ROW = (WALK_Y - 1) >> CELL_SHIFT
# The probed row, the one ABOVE it (see below) and the two under it — every cell any case here can
# reach. Seeded as ONE band rather than a poke per cell, which is how test_behavior.py's own map
# window is built and what keeps a forty-five-case battery's seeding out of the profile.
CLEARED_MAP_ROWS = 4


def _map_row(row):
    return MAP_DEFAULT + MAP_CELLS + row * DEFAULT_STRIDE


def _clear_map_rows(pokes):
    """The probed cells zeroed. `map_pokes` keys every cell off its ADDRESS, which is right for the
    map battery's own cases and wrong here: a keyed cell would block a step at random and the arm a
    case is about would not be the thing moving.

    The band starts ONE ROW ABOVE the probed one because a probe that walks off the map's left edge
    names a NEGATIVE column, and `lea d16(An,Dn.w)` sign-extends it back into the previous row."""
    pokes[_map_row(PROBE_ROW - 1)] = bytes(CLEARED_MAP_ROWS * DEFAULT_STRIDE)
    return pokes


def _fill_probe_row(pokes):
    """...and the same window with the probed row SOLID, for the one case about a blocked step."""
    pokes[_map_row(PROBE_ROW)] = bytes([TILE_BLOCK]) * DEFAULT_STRIDE
    return pokes


# Every record byte the walk reads, seeded to a value that takes NO arm — so a case names only the
# state it is about and a field it forgets cannot quietly choose a branch. The record is
# WB_ACTOR_TYPE_PLAYER because it is the player's, and because that type is what makes the probes'
# own WB_ACTOR_FIELD_22 clear reachable at all.
_WALK_QUIET_RECORD = {ACTOR_FLAGS: 0, FLAGS2: 0, FIELD_22: 0, FIELD_23: 0, FIELD_24: 0,
                      FIELD_29: 0, FIELD_30: 0, FIELD_31: 0, FLICKER_COUNTDOWN: MARKER}
WALK_STRENGTH = 0x0020        # a run-speed state word whose ceiling byte is well above any speed


def _walk_pokes(what, fields=None, blocked=False):
    salt = case_salt(what)
    base = map_pokes(salt)
    _clear_map_rows(base)
    if blocked:
        _fill_probe_row(base)
    base.update({SEEDED_LO: keyed_block(SEEDED_LO, SEEDED_LEN, salt),
                 STATE_FLAG_A32: word(0),
                 SCROLL_LIMIT_X: word(WIDE_LEVEL),
                 EFFECT_STATE_BD6A: word(WALK_STRENGTH),
                 TILE_33_MODE: word(0),
                 JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([0]),
                 ACTOR + ACTOR_X: word(WALK_X), ACTOR + ACTOR_Y: word(WALK_Y),
                 ACTOR + ACTOR_TYPE: word(TYPE_PLAYER),
                 ACTOR + HALF_WIDTH: word(WALK_HALF_WIDTH)})
    base.update({ACTOR + offset: bytes([value]) for offset, value in _WALK_QUIET_RECORD.items()})
    return leaf.overlay(base, fields or {})


_STEP_AND_ARM = leaf.register_glue("player_step_and_arm", [ctypes.c_uint32])
# The map probes LOOP once per pixel of a blocked step, so the cap has to carry the widest step any
# case here takes rather than a round number: a probe is BLOCKED_PROBE_INSNS instructions of
# straight-line body plus PROBE_LOOP_INSNS per pixel it backs off, and no case seeds a step above
# WIDEST_SEEDED_STEP. THREE probes can fire in one frame, not two — the knock-back's, the hurt
# drift's and the accelerator's tail, and nothing makes those three sections exclusive.
BLOCKED_PROBE_INSNS = 20
PROBE_LOOP_INSNS = 10
WIDEST_SEEDED_STEP = 6                  # the hurt drift's WB_ACTOR_FIELD_31 seed, the largest here
PROBES_PER_FRAME = 3
PROBE_INSNS = BLOCKED_PROBE_INSNS + PROBE_LOOP_INSNS * WIDEST_SEEDED_STEP
STEP_AND_ARM_CAP = _cap("player_step_and_arm",
                        extra=JOY_EDGE_INSNS + PROBES_PER_FRAME * PROBE_INSNS
                        + INSN_COUNT["player_reset_ground_state"])


def _run_walk(what, pokes, expected):
    info = leaf.run("player_step_and_arm", _STEP_AND_ARM(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=STEP_AND_ARM_CAP)
    _assert_writes(info, expected, what)
    return info


def _coast_flags(flags=0):
    """The one byte EVERY frame of this routine writes: the coast arm's `bclr #5,8(a0)`, which runs
    whenever no direction is held. Stated as a helper because it is the whole write set of the
    quietest case here and a term in most of the others."""
    return {ACTOR + ACTOR_FLAGS: flags & ~(1 << MOVED_BIT)}


def test_an_idle_frame_writes_exactly_one_byte():
    """Every section declines and the coast arm lowers WB_ACTOR_FLAG_MOVED_BIT — the `bclr` stores
    whether or not the bit was up, so this is a write and not a no-op."""
    what = "player_step_and_arm idle"
    _run_walk(what, _walk_pokes(what), _coast_flags())


@pytest.mark.parametrize("facing,step_sign", [(0, -1), (1 << SIDE_BIT, +1)],
                         ids=["facing-right", "facing-left"])
def test_the_knock_back_pushes_the_record_AWAY_from_the_side_it_faces(facing, step_sign):
    """WB_ACTOR_FLAG_SIDE_BIT set means the followed record is to the LEFT (actor.h), and this steps
    RIGHT — which is what makes the section a knock-back rather than a walk. The count is spent from
    memory afterwards, so the step is the count as it was."""
    steps = 5
    what = f"player_step_and_arm knock-back facing={facing:#04x}"
    pokes = _walk_pokes(what, {ACTOR + FIELD_29: bytes([steps]),
                               ACTOR + ACTOR_FLAGS: bytes([facing])})

    expected = _coast_flags(facing)
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + step_sign * steps)
    expected[ACTOR + FIELD_29] = steps - 1
    _run_walk(what, pokes, expected)


def test_a_zero_knock_back_count_takes_no_step_and_spends_nothing():
    """`tst.b 29(a0) / beq` — the section's own gate, and the negative that says the probe below it
    is not run unconditionally."""
    what = "player_step_and_arm knock-back with a zero count"
    _run_walk(what, _walk_pokes(what), _coast_flags())


@pytest.mark.parametrize("previous,current,fires",
                         [(0x00, 1 << JOY1_FIRE_BIT, True),
                          (1 << JOY1_FIRE_BIT, 1 << JOY1_FIRE_BIT, False),
                          (0x00, 1 << JOY1_UP_BIT, False)],
                         ids=["edge", "held", "wrong-button"])
def test_the_fire_edge_arms_the_record_and_zeroes_the_walk_speed(previous, current, fires):
    """Three writes on the arm: WB_ACTOR_FLAG_FIRED_BIT up, WB_ACTOR_FLAGS2_BIT_0 down and
    WB_ACTOR_FIELD_22 cleared. `held` is what separates the EDGE from the level."""
    what = f"player_step_and_arm fire prev={previous:#04x} current={current:#04x}"
    flags2 = 1 << FLAGS2_BIT_0
    pokes = _walk_pokes(what, {JOY1_PREV: bytes([previous]), JOY1_CURRENT: bytes([current]),
                               ACTOR + FLAGS2: bytes([flags2]),
                               ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])})

    # The drift's gate is up on both rows; what differs is that the fire arm LOWERS it, so the
    # supported record's `bclr` below never runs. Two arms of one frame, in one write set.
    expected = _coast_flags((1 << SUPPORTED_BIT) | ((1 << FIRED_BIT) if fires else 0))
    expected[ACTOR + FLAGS2] = flags2 & ~(1 << FLAGS2_BIT_0)
    if fires:
        expected[ACTOR + FIELD_22] = 0
    _run_walk(what, pokes, expected)


def test_FIRE_TOGETHER_WITH_A_DIRECTION_still_arms_the_record():
    """WHERE THIS ROUTINE AND `player_weapon_fire` PART, and the only place either behaviour is
    visible: `tst.b d0 / bpl` here reads bit 7 alone, while the weapon's `cmp.b #$80,d0` one call
    later wants the WHOLE byte. So this frame arms and the next call declines to fire — the same
    joystick frame, two different readings, and `test_the_weapon_needs_the_fire_edge_ALONE` is the
    other half."""
    what = "player_step_and_arm fire together with right"
    current = (1 << JOY1_FIRE_BIT) | (1 << JOY1_RIGHT_BIT)
    pokes = _walk_pokes(what, {JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([current])})

    # The frame's own tail is the RIGHT arm on a direction byte that says LEFT, so it TURNS: the
    # speed the fire arm has just zeroed goes negative, is zeroed again and the direction flips.
    expected = {ACTOR + ACTOR_FLAGS: (1 << FIRED_BIT) | (1 << MOVED_BIT),
                ACTOR + FLAGS2: 0,
                ACTOR + FIELD_22: 0,
                ACTOR + FIELD_23: ST_BYTE}
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("countdown", [3, 1, 0], ids=lambda v: f"countdown{v}")
def test_the_flicker_countdown_is_spent_and_ENDS_the_invulnerability_with_itself(countdown):
    """$f14's `subq.b #1,21(a0)` is WB_ACTOR_FLICKER_COUNTDOWN's ONE reader in the image, and the
    frame it reaches zero lowers BOTH the flicker bit and the WB_ACTOR_FLAGS2_INVULNERABLE_BIT the
    damage path raised beside it. `countdown0` is the byte-wrap row: $00 - 1 is $ff, and the `bne`
    reads THAT, so a zero countdown runs 255 more frames of flicker rather than ending."""
    what = f"player_step_and_arm flicker countdown={countdown}"
    flags = (1 << FLICKER_BIT)
    flags2 = 1 << INVULNERABLE_BIT
    pokes = _walk_pokes(what, {ACTOR + ACTOR_FLAGS: bytes([flags]),
                               ACTOR + FLAGS2: bytes([flags2]),
                               ACTOR + FLICKER_COUNTDOWN: bytes([countdown])})

    expected = {ACTOR + FLICKER_COUNTDOWN: (countdown - 1) & 0xff}
    ends = countdown == 1
    expected.update(_coast_flags(flags & ~((1 << FLICKER_BIT) if ends else 0)))
    if ends:
        expected[ACTOR + FLAGS2] = flags2 & ~(1 << INVULNERABLE_BIT)
    _run_walk(what, pokes, expected)


def test_a_record_that_is_not_flickering_does_not_touch_the_countdown():
    """The section's gate, and the negative that says the `subq.b` is not unconditional."""
    what = "player_step_and_arm not flickering"
    pokes = _walk_pokes(what, {ACTOR + FLICKER_COUNTDOWN: bytes([4])})
    _run_walk(what, pokes, _coast_flags())


@pytest.mark.parametrize("way,step_sign", [(0, -1), (1, +1)], ids=["field-30-zero", "field-30-set"])
def test_the_hurt_drift_pushes_the_record_the_way_FIELD_30_names_and_spends_TWO(way, step_sign):
    """`actor_damage_followed` writes the pair this reads: WB_ACTOR_FIELD_31 is how far the
    knock-back has left to run and WB_ACTOR_FIELD_30 which side. The step is the count BEFORE the
    spend — d7 is loaded above the `subq.b` — which is what separates six pixels from four."""
    steps = 6
    what = f"player_step_and_arm drift field30={way}"
    pokes = _walk_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                               ACTOR + FIELD_31: bytes([steps]),
                               ACTOR + FIELD_30: bytes([way])})

    expected = _coast_flags()
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + step_sign * steps)
    expected[ACTOR + FIELD_31] = steps - DRIFT_SPEND
    _run_walk(what, pokes, expected)


def test_a_drift_with_a_zero_count_still_takes_a_probe_of_ZERO_pixels():
    """`tst.b d7 / beq` skips the SPEND, not the probe — so the x is stored (unchanged) and
    WB_ACTOR_FIELD_31 is not. The row a port that made the probe conditional would fail, and the
    reason the x appears in a write set that changes nothing."""
    what = "player_step_and_arm drift with a zero count"
    pokes = _walk_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                               ACTOR + FIELD_31: bytes([0])})

    expected = _coast_flags()
    _put_word(expected, ACTOR + ACTOR_X, WALK_X)
    _run_walk(what, pokes, expected)


def test_a_zero_count_drift_off_the_maps_LEFT_EDGE_still_parks_the_record():
    """THE ROW THE MUTATION SWEEP DEMANDED, and the reason it had to be built this way. A probe of
    zero pixels normally stores the x UNCHANGED, and a memory differential cannot see a store of the
    value already there — so `drift/zero-count-takes-no-probe` survived every other case here as an
    argued equivalence rather than a hole.

    `actor_step_left_against_map`'s own edge arm is what makes it observable: a probe left of the
    map's origin is NEGATIVE, and the routine parks the record at its own WB_ACTOR_HALF_WIDTH
    instead. So an x below the half width moves even on a zero step, and a port that skipped the
    probe leaves it where it was."""
    what = "player_step_and_arm drift, zero count, off the left edge"
    pokes = _walk_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                               ACTOR + FIELD_31: bytes([0]),
                               ACTOR + ACTOR_X: word(WALK_HALF_WIDTH - 2)})

    expected = _coast_flags()
    _put_word(expected, ACTOR + ACTOR_X, WALK_HALF_WIDTH)
    _run_walk(what, pokes, expected)


def test_LANDING_ends_the_drift_instead_of_taking_a_step():
    """WB_ACTOR_FLAG_SUPPORTED_BIT lowers the gate bit and returns to the walk, so nothing moves and
    WB_ACTOR_FIELD_31 keeps whatever the damage left in it."""
    what = "player_step_and_arm drift, landed"
    flags = 1 << SUPPORTED_BIT
    pokes = _walk_pokes(what, {ACTOR + FLAGS2: bytes([1 << FLAGS2_BIT_0]),
                               ACTOR + ACTOR_FLAGS: bytes([flags]),
                               ACTOR + FIELD_31: bytes([6])})

    expected = _coast_flags(flags)
    expected[ACTOR + FLAGS2] = 0
    _run_walk(what, pokes, expected)


# --- the accelerator ------------------------------------------------------------------------------
HELD_RIGHT = 1 << JOY1_RIGHT_BIT
HELD_LEFT = 1 << JOY1_LEFT_BIT


def _travelling(rightward):
    """WB_ACTOR_FIELD_23 as the arm reads it: zero is LEFT and anything else is RIGHT."""
    return bytes([ST_BYTE if rightward else 0])


@pytest.mark.parametrize("rightward", [False, True], ids=["left", "right"])
@pytest.mark.parametrize("subframe", [0, 1, 2, 3], ids=lambda v: f"subframe{v}")
def test_the_walk_raises_its_speed_on_ONE_FRAME_IN_FOUR(rightward, subframe):
    """`addq.b #1,24(a0) / andi.b #$3,24(a0) / bne` — the counter is stepped every frame and the
    speed rises only when it wraps. Both arms are the same four instructions, which is why the row
    runs on each."""
    speed = 3
    what = f"player_step_and_arm accelerate right={rightward} subframe={subframe}"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT if rightward else HELD_LEFT]),
                               ACTOR + FIELD_23: _travelling(rightward),
                               ACTOR + FIELD_24: bytes([subframe]),
                               ACTOR + FIELD_22: bytes([speed])})

    stepped = (subframe + 1) & WALK_SUBFRAME_MASK
    raised = speed + (1 if stepped == 0 else 0)
    expected = {ACTOR + ACTOR_FLAGS: (1 << MOVED_BIT) | (0 if rightward else (1 << SIDE_BIT)),
                ACTOR + FIELD_24: stepped}
    if stepped == 0:
        expected[ACTOR + FIELD_22] = raised
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + (raised if rightward else -raised))
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("strength,ceiling", [(0x0020, 0x24), (0x00fc, 0x00), (0xff02, 0x06),
                                             (0x0080, 0x84)],
                         ids=["ordinary", "byte-wrap", "high-half", "negative-ceiling"])
def test_the_walk_ceiling_is_the_state_words_LOW_BYTE_plus_four(strength, ceiling):
    """`move.w $bd6a.l,d0 / addq.w #4,d0 / cmp.b 22(a0),d0` — a WORD add whose LOW BYTE is compared,
    where the jump machine's `addi.b #$8,d0` is a BYTE add on the same state word. `byte-wrap` is the
    row that separates them: a state word of $00fc leaves the WALK's ceiling at zero (and so clamps
    the speed to a standstill) where it leaves the JUMP's strength at 4.

    The seed puts the speed ABOVE the ceiling, so the clamp is what the case sees — and
    `negative-ceiling` is the row that says `bgt` is SIGNED: a ceiling byte of $84 is -124, which is
    below the seeded speed of $40, so the clamp fires where an unsigned reading (132 > 64) would
    have left the raised value."""
    what = f"player_step_and_arm ceiling strength={strength:#06x}"
    speed = 0x40
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               EFFECT_STATE_BD6A: word(strength),
                               ACTOR + FIELD_23: _travelling(True),
                               ACTOR + FIELD_24: bytes([WALK_SUBFRAME_MASK]),
                               ACTOR + FIELD_22: bytes([speed])})

    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_24: 0,
                ACTOR + FIELD_22: ceiling}
    # A ceiling of zero is a standstill and the tail's own `beq` then takes NO probe at all, so the
    # x is absent from the write set rather than stored unchanged — which is the sharpest form the
    # `byte-wrap` row can take.
    if ceiling != 0:
        _put_word(expected, ACTOR + ACTOR_X, WALK_X + ceiling)
    _run_walk(what, pokes, expected)


def test_a_speed_UNDER_the_ceiling_keeps_the_raised_value():
    """The other side of `bgt`, so the clamp is a clamp and not an assignment."""
    what = "player_step_and_arm under the ceiling"
    speed = 2
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(True),
                               ACTOR + FIELD_24: bytes([WALK_SUBFRAME_MASK]),
                               ACTOR + FIELD_22: bytes([speed])})

    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_24: 0,
                ACTOR + FIELD_22: speed + 1}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + speed + 1)
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("rightward,decel", [(True, TURN_DECEL_RIGHT), (False, TURN_DECEL_LEFT)],
                         ids=["turning-right", "turning-left"])
def test_THE_TURN_IS_NOT_SYMMETRIC(rightward, decel):
    """The walk's one asymmetry, and it is two different `subq.b` immediates one arm apart: a player
    who is running left and pushes RIGHT sheds WB_PLAYER_TURN_DECEL_RIGHT a frame, and one running
    right who pushes LEFT sheds WB_PLAYER_TURN_DECEL_LEFT. A port that shared one constant between
    the two arms answers the same on every OTHER row in this battery.

    The record keeps travelling the OLD way while the speed lasts — which is the second claim here,
    and the sign of the x step is what carries it."""
    speed = 6
    what = f"player_step_and_arm turning right={rightward}"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT if rightward else HELD_LEFT]),
                               ACTOR + FIELD_23: _travelling(not rightward),
                               ACTOR + FIELD_22: bytes([speed])})

    left_over = speed - decel
    expected = {ACTOR + ACTOR_FLAGS: (1 << MOVED_BIT) | (0 if rightward else (1 << SIDE_BIT)),
                ACTOR + FIELD_22: left_over}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + (-left_over if rightward else left_over))
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("rightward,speed", [(True, 1), (False, 0)],
                         ids=["right-from-one", "left-from-zero"])
def test_the_frame_the_turn_goes_NEGATIVE_flips_the_direction_byte(rightward, speed):
    """`bpl` reads what the `subq.b` LEFT, so the flip is on a negative result and not on zero — and
    `left-from-zero` is the byte-wrap row: $00 - 1 is $ff, which IS negative, so a standing player
    who pushes left flips on the spot rather than turning for 255 frames.

    What lands is a zeroed speed, the new WB_ACTOR_FIELD_23, and a step the NEW way that a zero
    speed then declines to take."""
    what = f"player_step_and_arm turn flipping right={rightward}"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT if rightward else HELD_LEFT]),
                               ACTOR + FIELD_23: _travelling(not rightward),
                               ACTOR + FIELD_22: bytes([speed])})

    expected = {ACTOR + ACTOR_FLAGS: (1 << MOVED_BIT) | (0 if rightward else (1 << SIDE_BIT)),
                ACTOR + FIELD_22: 0,
                ACTOR + FIELD_23: ST_BYTE if rightward else 0}
    _run_walk(what, pokes, expected)


def test_a_turning_frame_does_NOT_step_the_sub_frame_counter():
    """The turn branch sits ABOVE `addq.b #1,24(a0)`, so a frame spent turning does not bring the
    next acceleration any closer. Asserted as an absence, which the exact write set already carries
    — this case says so by seeding the counter one short of its wrap and requiring it to stay."""
    what = "player_step_and_arm turning does not tick the counter"
    speed = 6
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(False),
                               ACTOR + FIELD_24: bytes([WALK_SUBFRAME_MASK]),
                               ACTOR + FIELD_22: bytes([speed])})

    left_over = speed - TURN_DECEL_RIGHT
    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_22: left_over}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X - left_over)
    _run_walk(what, pokes, expected)


def test_a_turn_that_lands_EXACTLY_on_zero_keeps_travelling_the_OLD_way():
    """`bpl` is a SIGN test, and zero is not negative — so the frame the speed reaches exactly zero
    still steps the old way (with a zero speed, i.e. not at all) and does NOT flip
    WB_ACTOR_FIELD_23. The flip is one frame later. A port that flipped on `<= 0` writes a direction
    byte here that the original does not."""
    what = "player_step_and_arm turning to exactly zero"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(False),
                               ACTOR + FIELD_22: bytes([TURN_DECEL_RIGHT])})

    _run_walk(what, pokes, {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_22: 0})


def test_holding_BOTH_directions_walks_RIGHT_because_bit_3_is_tested_first():
    """The order of the two `btst`s against WB_JOY1_CURRENT, as a case — nothing else separates
    them."""
    what = "player_step_and_arm both directions"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_LEFT | HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(True),
                               ACTOR + FIELD_22: bytes([2])})

    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_24: 1}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + 2)
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("speed,rightward", [(3, False), (3, True), (1, False)],
                         ids=["coasting-left", "coasting-right", "last-pixel"])
def test_letting_go_sheds_ONE_a_frame_and_keeps_travelling(speed, rightward):
    """The arm neither direction takes: the moved bit down, one off the speed, and a step in
    whichever direction WB_ACTOR_FIELD_23 still names. `last-pixel` is the frame the speed reaches
    zero, where the tail RE-READS the byte and declines to probe — which is what makes the tail a
    re-read rather than a carried value."""
    what = f"player_step_and_arm coasting speed={speed} right={rightward}"
    pokes = _walk_pokes(what, {ACTOR + FIELD_23: _travelling(rightward),
                               ACTOR + FIELD_22: bytes([speed])})

    left_over = speed - 1
    expected = _coast_flags()
    expected[ACTOR + FIELD_22] = left_over
    if left_over:
        _put_word(expected, ACTOR + ACTOR_X, WALK_X + (left_over if rightward else -left_over))
    _run_walk(what, pokes, expected)


def test_a_NEGATIVE_coasting_speed_is_zeroed_rather_than_stepped():
    """`subq.b #1,22(a0) / bpl` — a byte already past $80 decelerates into the negative half and the
    arm clears it instead of handing a huge step to a map probe. The write set is one byte, because
    the `subq.b`'s own store and the `clr.b` land on the same address."""
    what = "player_step_and_arm coasting on a negative speed"
    pokes = _walk_pokes(what, {ACTOR + FIELD_22: bytes([0x81])})

    expected = _coast_flags()
    expected[ACTOR + FIELD_22] = 0
    _run_walk(what, pokes, expected)


@pytest.mark.parametrize("rightward", [False, True], ids=["left", "right"])
def test_pushing_a_direction_off_a_LADDER_calls_player_reset_ground_state(rightward):
    """THE COMPOSITION batch 40 phase A could not exercise: $107c had no caller in this port at all,
    and its TWO call sites are the `bsr $107c` at $fb2 and $101e inside these two arms, each guarded
    by `tst.w WB_TILE_33_MODE`. So this case is what turns that routine's entry pin into a run.

    What it adds to the frame is the mode word cleared, the record put back into a fall and
    WB_ACTOR_SPEED reloaded from WB_EFFECT_STATE_BD6A + WB_PLAYER_JUMP_STRENGTH_BIAS — the same byte
    the jump machine stamps into WB_ACTOR_FIELD_10, and a different bias from the walk's own."""
    what = f"player_step_and_arm leaving a ladder right={rightward}"
    pokes = _walk_pokes(what, {TILE_33_MODE: word(TILE_33_MODE_UP),
                               JOY1_CURRENT: bytes([HELD_RIGHT if rightward else HELD_LEFT]),
                               ACTOR + FIELD_23: _travelling(rightward),
                               ACTOR + SPEED: bytes([MARKER]),
                               ACTOR + FIELD_22: bytes([2])})

    expected = {}
    _put_word(expected, TILE_33_MODE, 0)
    expected[ACTOR + ACTOR_FLAGS] = ((1 << MOVING_BIT) | (1 << LAUNCHED_BIT) | (1 << MOVED_BIT)
                                     | (0 if rightward else (1 << SIDE_BIT)))
    expected[ACTOR + SPEED] = (WALK_STRENGTH + JUMP_STRENGTH_BIAS) & 0xff
    expected[ACTOR + FIELD_24] = 1
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + (2 if rightward else -2))
    _run_walk(what, pokes, expected)


def test_a_walking_frame_with_the_ladder_mode_DOWN_leaves_the_ground_state_alone():
    """`tst.w $1516 / beq` — the guard, and the negative that says the call is not unconditional."""
    what = "player_step_and_arm walking with no ladder mode"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(True),
                               ACTOR + SPEED: bytes([MARKER]),
                               ACTOR + FIELD_22: bytes([2])})

    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_24: 1}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X + 2)
    _run_walk(what, pokes, expected)


def test_a_BLOCKED_walk_step_clears_the_speed_through_the_probes_own_player_arm():
    """The one case here that seeds a solid row. `actor_step_left_against_map` runs its step down a
    pixel at a time and, for a WB_ACTOR_TYPE_PLAYER record only, zeroes WB_ACTOR_FIELD_22 on every
    turn of that loop — so the walk's own speed is undone by the routine it calls, and the x is
    STORED (unchanged) rather than left alone. That behaviour is src/map.c's and test_map.py pins it;
    what this case adds is that the player's record really is the type that reaches it."""
    what = "player_step_and_arm walking into a wall"
    pokes = _walk_pokes(what, {JOY1_CURRENT: bytes([HELD_RIGHT]),
                               ACTOR + FIELD_23: _travelling(True),
                               ACTOR + FIELD_22: bytes([3])}, blocked=True)

    expected = {ACTOR + ACTOR_FLAGS: 1 << MOVED_BIT, ACTOR + FIELD_24: 1, ACTOR + FIELD_22: 0}
    _put_word(expected, ACTOR + ACTOR_X, WALK_X)
    _run_walk(what, pokes, expected)


# ==================================================================================================
# $1208: the weapon — batch 40 phase B
# ==================================================================================================
from test_actor import (ALLOC_HIGH_FIRST, ALLOC_HIGH_SLOTS, ALLOC_INSN_PER_SLOT,   # noqa: E402
                        FREE_MARKER)

_WEAPON_FIRE = leaf.register_glue("player_weapon_fire",
                                  [ctypes.c_uint32, ctypes.c_uint])

# The record the write pointer names. TWO records above the list's base, so the pop at the end of the
# spend is a change the ledger can see and the "nothing is held" gate is a different state.
WEAPON_RECORD = EFFECT_RECORD_LIST + 2 * EFFECT_RECORD_LEN
SHOT_SLOT = ALLOC_HIGH_FIRST                 # the first record actor_alloc_slot_high looks at
SHOT = TABLE_DEFAULT + SHOT_SLOT * RECORD_BYTES
POOL_LO = TABLE_DEFAULT + ALLOC_HIGH_FIRST * RECORD_BYTES
POOL_LEN = ALLOC_HIGH_SLOTS * RECORD_BYTES

PLAYER_X, PLAYER_Y = 0x0140, 0x0088
SHOT_FLAGS_SEED = 0x5c                       # the byte the fireball's `bset`/`bclr #3` reads back
TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
# The weapon's cap is its own body plus the joystick edge plus ONE WHOLE POOL WALK. The per-slot
# figure is `ALLOC_INSN_PER_SLOT`, imported from the battery that OWNS `actor_alloc_slot_high` rather
# than restated — a second reading of one routine's loop is exactly the drift `leaf.py` and the
# imported models exist to stop, and this file's first draft got it wrong by one (`cmpi.w / beq.w /
# lea / dbf` is four, not three). Its three instructions above the loop and two below are the
# straight-line remainder.
ALLOC_STRAIGHT_LINE_INSNS = 5
WEAPON_CAP = _cap("player_weapon_fire",
                  extra=JOY_EDGE_INSNS + ALLOC_STRAIGHT_LINE_INSNS
                  + ALLOC_HIGH_SLOTS * ALLOC_INSN_PER_SLOT)


def _weapon_pokes(what, item, count=0x05, fields=None, pool_full=False):
    """A frame in which everything but the arm under test is set to fire: no ladder tile, a held
    record, a FIRE-only edge and DOWN held.

    THE POOL IS ITS OWN LAYER, and that is not tidiness: the first record of the high pool starts AT
    `POOL_LO`, so the free marker below would share a dict KEY with the keyed block and `dict` keeps
    the last — which is `leaf.overlay`'s own documented hazard, and it fired here. The mutation sweep
    is what found it: `weapon/fireball-clears-the-sprite-WORD` survived because the shot record was
    running on the .PRG's zeros, where a byte the port clears and the original does not reads the
    same either way."""
    salt = case_salt(what)
    pool = {POOL_LO: keyed_block(POOL_LO, POOL_LEN, salt)}
    markers = {}
    for slot in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS):
        record = TABLE_DEFAULT + slot * RECORD_BYTES
        markers[record + ACTOR_X] = word(FREE_MARKER if not pool_full else 0)
        markers[record + ACTOR_FLAGS] = bytes([SHOT_FLAGS_SEED])
    base = {SEEDED_LO: keyed_block(SEEDED_LO, SEEDED_LEN, salt),
            TABLE_SELECTED: longword(TABLE_DEFAULT),
            TILE_33_FLAG: word(0),
            EFFECT_RECORD_WRITE_PTR: longword(WEAPON_RECORD),
            WEAPON_RECORD: bytes([item, count]),
            RECORD_FRESH_FLAG: bytes([MARKER]),
            FLASH_TIMER: word(MARKER),
            # DOWN IS HELD FROM THE PREVIOUS FRAME, which is not a convenience: the edge test wants
            # `joy1_newly_pressed` to be EXACTLY WB_PLAYER_FIRE_EDGE_EXACT, and that byte is
            # `current & ~prev` — so a frame in which DOWN goes down TOGETHER with fire produces
            # $82 and fires nothing. Pushing down first and then fire is the only way in.
            JOY1_PREV: bytes([1 << JOY1_DOWN_BIT]),
            JOY1_CURRENT: bytes([FIRE_EDGE_EXACT | (1 << JOY1_DOWN_BIT)]),
            ACTOR + ACTOR_X: word(PLAYER_X), ACTOR + ACTOR_Y: word(PLAYER_Y),
            ACTOR + ACTOR_FLAGS: bytes([0])}
    return leaf.overlay(pool, markers, base, fields or {})


def _run_weapon(what, pokes, expected, entry_extend=0):
    info = leaf.run("player_weapon_fire", _WEAPON_FIRE(ACTOR, entry_extend),
                    merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=WEAPON_CAP)
    _assert_writes(info, expected, what)
    return info


def _spend_bytes(count, borrow=0):
    """The `sbcd` and the two writes around it: the count in packed BCD less one (and less the entry
    X), the fresh flag raised, and the record POPPED when the count reaches zero.

    The BCD comes from `leaf.bcd_expected`, which states the arithmetic in DECIMAL and so is
    independent of src/hud.c's nibble spelling — which is why batch 33 hoisted it there. A fourth
    statement of packed BCD here would be the copy that drifts, and it would also answer confidently
    outside the digit range, where `bcd_expected` declines to predict."""
    left = leaf.bcd_expected(count, WEAPON_SPEND_VALUE, BCD_COUNT_BYTES, subtract=True,
                             extend=borrow).value
    assert left is not None, f"{count:#04x} is not a packed-BCD count"
    expected = {WEAPON_RECORD + RECORD_LOW_BYTE: left, RECORD_FRESH_FLAG: ST_BYTE}
    if left == 0:
        _put_long(expected, EFFECT_RECORD_WRITE_PTR, WEAPON_RECORD - EFFECT_RECORD_LEN)
    return expected


def test_the_byte_the_sbcd_subtracts_is_a_packed_BCD_ONE_inside_the_routines_own_bytes():
    """`lea $1333.l,a2 / sbcd -(a2),-(a6)` reads BELOW that address, and what is there is data the
    routine carries with it — the last two bytes of its own 300. Read off the shipped image, so the
    entry pin's claim about them is checkable independently of the pin."""
    at = WEAPON_SPEND_BCD
    assert harness.BASE_IMAGE[at] == WEAPON_SPEND_VALUE
    assert WEAPON_SPEND_BCD + WORD_BYTES == leaf.entry_of("actor_fall_and_settle"), (
        "the spend byte is not in player_weapon_fire's last word")


def test_the_three_item_codes_are_the_high_bytes_of_the_records_the_grants_push():
    """WHAT THE `cmpi.b`s COMPARE, pinned against the four WB_PICKUP_RECORD_* words src/effects.c
    pushes: the item byte is that word's high half. The fourth item, the BOMB, has no `cmpi` of its
    own — it is what the `bra.w` falls to — so its code is asserted to be DIFFERENT from the three
    that do, which is what makes the default arm reachable at all."""
    named = {WEAPON_LIGHTNING: "PICKUP_RECORD_LIGHTNING",
             WEAPON_WIND_SPOUTS: "PICKUP_RECORD_WIND_SPOUTS",
             WEAPON_FIRE_BALLS: "PICKUP_RECORD_FIRE_BALLS"}
    for code, record in named.items():
        assert wb(record) >> 8 == code, f"{record} does not open with item {code}"
    assert wb("PICKUP_RECORD_BOMBS") >> 8 not in named, (
        "the bombs' item byte is one of the three the dispatch names, so nothing reaches the "
        "default arm")


BOMB_ITEM = wb("PICKUP_RECORD_BOMBS") >> 8


# WHERE EACH GATE REFUSES, and the instruction that must NOT then run. "The frame wrote nothing" is
# true of every refusal in this routine, so on its own it says only that SOMETHING declined — and
# the full-pool rows below are the ones that makes load-bearing, because four gates and a whole
# dispatch sit above the allocator they are about. Each row names both halves instead.
GATE_BRANCH = {"TILE_33_FLAG": 0x120e,   # `bne.w $1274` under `tst.w $1514.l`
               "WRITE_PTR": 0x121c,      # `beq.w $1274` under `cmpi.l #$b444,$b546.l`
               "EDGE": 0x1228,           # `bne.w $1274` under `cmp.b #$80,d0`
               "DOWN": 0x1232}           # `beq.w $1274` under `btst #1,$8cf.w`
GATE_NEXT = {"TILE_33_FLAG": 0x1212, "WRITE_PTR": 0x1220, "EDGE": 0x122c, "DOWN": 0x1236}
# ...and the allocator's own "the pool is full" store, plus the shared spend the three spawn arms
# `rts` above. Both are OUTSIDE this routine, which is the point: a refusal that never reached
# $1b8e is a different refusal from the one those rows claim.
ALLOC_REFUSED = 0x1bac                   # `movea.l #$0,a1` inside actor_alloc_slot_high
WEAPON_SPEND = 0x1258                    # `addq.l #2,a6`, the head of the shared `sbcd` tail


def _run_refused(what, pokes, reached, not_reached):
    """A refusal row: the frame writes nothing, the named instruction RAN, and the one below it did
    not. `leaf.run_reaching` is the same witness for a checkpointed run; this is its shape for a run
    that returns normally, so the two claims are separated the way that helper separates them.

    WHAT THE WITNESS IS AND IS NOT. `emu`'s bitset marks the ORACLE's PCs, so this is a claim about
    the ORIGINAL's path and NO reconstruction mutant can red it — it is a premise guard on the SEED,
    of the kind `test_the_two_ladder_modes_are_different_words` is. What it buys is exactly what
    "the frame wrote nothing" does not say: every gate in this routine refuses by writing nothing,
    so without it a full-pool row would keep passing after its seed stopped reaching the allocator
    at all. Measured: dropping DOWN from the full-pool seed leaves the write set identical and reds
    all three rows here."""
    with leaf.pc_coverage():
        info = leaf.run("player_weapon_fire", _WEAPON_FIRE(ACTOR, 0), [], what,
                        regs={"a0": ACTOR, "_pokes": pokes}, max_insns=WEAPON_CAP)
    assert not program_writes(info), f"{what}: a refused frame wrote memory"
    assert leaf.emu.cov_visited(reached), (
        f"{what}: the frame refused without executing {reached:#x}, so some OTHER gate declined")
    assert not leaf.emu.cov_visited(not_reached), (
        f"{what}: the frame ran on to {not_reached:#x}, so the gate above it did not refuse")


@pytest.mark.parametrize("field,value", [("TILE_33_FLAG", 0xffff), ("WRITE_PTR", None),
                                         ("EDGE", 0x00), ("DOWN", 0x00)],
                         ids=["on-a-ladder-tile", "nothing-held", "no-fire-edge", "down-not-held"])
def test_each_of_the_four_gates_ends_the_frame_without_writing_anything(field, value):
    """Four tests in series and this is each of their negatives. `nothing-held` is the one that is
    not a flag: the write pointer still AT the list's base means no record was ever pushed. Each row
    witnesses ITS OWN gate, so a port that refused one test earlier still reds here."""
    what = f"player_weapon_fire refused by {field}"
    overrides = {}
    if field == "TILE_33_FLAG":
        overrides[TILE_33_FLAG] = word(value)
    elif field == "WRITE_PTR":
        overrides[EFFECT_RECORD_WRITE_PTR] = longword(EFFECT_RECORD_LIST)
    elif field == "EDGE":
        overrides[JOY1_PREV] = bytes([FIRE_EDGE_EXACT | (1 << JOY1_DOWN_BIT)])
    else:
        overrides[JOY1_PREV] = bytes([0])
        overrides[JOY1_CURRENT] = bytes([FIRE_EDGE_EXACT])

    pokes = _weapon_pokes(what, WEAPON_LIGHTNING, fields=overrides)
    _run_refused(what, pokes, GATE_BRANCH[field], GATE_NEXT[field])


@pytest.mark.parametrize("current", [FIRE_EDGE_EXACT | (1 << JOY1_DOWN_BIT) | (1 << JOY1_RIGHT_BIT),
                                     FIRE_EDGE_EXACT | (1 << JOY1_DOWN_BIT) | (1 << JOY1_LEFT_BIT)],
                         ids=["with-right", "with-left"])
def test_the_weapon_needs_the_fire_edge_ALONE(current):
    """`cmp.b #$80,d0` is an EQUALITY over the WHOLE byte `joy1_newly_pressed` returns, so a frame
    in which FIRE and a direction both go down fires nothing — while `player_step_and_arm`, one call
    EARLIER in the same frame, arms the record on the same byte with `tst.b d0 / bpl`. The pair is
    `test_FIRE_TOGETHER_WITH_A_DIRECTION_still_arms_the_record`.

    Note DOWN is HELD rather than newly pressed on every firing row, which is what makes that
    equality satisfiable at all: the two tests read different bytes."""
    what = f"player_weapon_fire edge {current:#04x}"
    # ...and the direction is NEWLY pressed, which is the whole of what this row changes.
    pokes = _weapon_pokes(what, WEAPON_LIGHTNING, fields={JOY1_CURRENT: bytes([current])})
    _run_refused(what, pokes, GATE_BRANCH["EDGE"], GATE_NEXT["EDGE"])


def test_the_LIGHTNING_arm_spawns_nothing_and_only_winds_the_flash_timer():
    """Its whole body is one `move.w #$2,$714.w`, which is what makes it the only item that costs no
    actor slot — and it still spends a shot, because the spend is below the dispatch."""
    what = "player_weapon_fire lightning"
    pokes = _weapon_pokes(what, WEAPON_LIGHTNING)

    expected = _spend_bytes(0x05)
    _put_word(expected, FLASH_TIMER, LIGHTNING_FLASH)
    _run_weapon(what, pokes, expected)


def _thrown_shot_bytes(expected, player_flags, type_word, lifetime):
    """The block $1276 runs and $1308 branches INTO, as a write set: everything from `clr.w 6(a1)`
    down, plus the two fields each arm writes above it. The flags byte is the PLAYER's, with the
    flicker bit knocked down and the two motion bits raised — so a shot inherits which way he
    faces."""
    _put_word(expected, SHOT + ACTOR_TYPE, type_word)
    expected[SHOT + FIELD_30] = lifetime
    _put_word(expected, SHOT + ACTOR_SPRITE, 0)
    expected[SHOT + ACTOR_FLAGS] = ((player_flags & ~(1 << FLICKER_BIT))
                                    | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT))
    expected[SHOT + FLAGS2] = 0
    expected[SHOT + SPEED] = SHOT_SPEED
    _put_word(expected, SHOT + ACTOR_X, PLAYER_X)
    _put_word(expected, SHOT + ACTOR_Y, PLAYER_Y)
    _put_word(expected, SHOT + HALF_WIDTH, SHOT_HALF_WIDTH)
    _put_word(expected, SHOT + SIZE_SECOND, SHOT_SIZE_SECOND)
    return expected


@pytest.mark.parametrize("item,type_word,lifetime",
                         [(WEAPON_WIND_SPOUTS, SHOT_TYPE_WIND, SHOT_LIFETIME_WIND),
                          (BOMB_ITEM, SHOT_TYPE_BOMB, SHOT_LIFETIME)],
                         ids=["wind-spout", "bomb"])
@pytest.mark.parametrize("player_flags", [0x00, 0xff], ids=["plain", "all-flags"])
def test_the_two_THROWN_weapons_share_one_arming_block(item, type_word, lifetime, player_flags):
    """$1308 writes its own type and lifetime and then `bra.w $1292` INTO the wind spout's body, so
    the two arms differ in exactly three things: the type, the lifetime, and the order of those two
    stores. `all-flags` is what shows the block copies the player's WHOLE byte and then edits three
    bits of it rather than composing one."""
    what = f"player_weapon_fire item={item:#04x} flags={player_flags:#04x}"
    pokes = _weapon_pokes(what, item, fields={ACTOR + ACTOR_FLAGS: bytes([player_flags])})

    expected = _spend_bytes(0x05)
    _thrown_shot_bytes(expected, player_flags, type_word, lifetime)
    _run_weapon(what, pokes, expected)


@pytest.mark.parametrize("facing", [0x00, 1 << SIDE_BIT], ids=["facing-right", "facing-left"])
def test_the_FIREBALL_copies_only_the_side_bit_and_leaves_eight_pixels_high(facing):
    """The one arm that shares nothing below its own allocation. It reads the shot record's OWN flags
    byte back and edits bit 3 of it — where the block above copies the player's whole byte — and it
    clears the sprite word's HIGH BYTE alone (`clr.b 6(a1)` against a `clr.w`), so the seeded low
    half survives. Both are asserted here rather than described."""
    what = f"player_weapon_fire fireball facing={facing:#04x}"
    pokes = _weapon_pokes(what, WEAPON_FIRE_BALLS,
                          fields={ACTOR + ACTOR_FLAGS: bytes([facing])})

    expected = _spend_bytes(0x05)
    _put_word(expected, SHOT + ACTOR_TYPE, SHOT_TYPE_FIREBALL)
    expected[SHOT + FIELD_30] = SHOT_LIFETIME
    _put_word(expected, SHOT + ACTOR_X, PLAYER_X)
    _put_word(expected, SHOT + ACTOR_Y, PLAYER_Y - FIREBALL_Y_RISE)
    expected[SHOT + ACTOR_FLAGS] = ((SHOT_FLAGS_SEED | (1 << SIDE_BIT)) if facing
                                    else (SHOT_FLAGS_SEED & ~(1 << SIDE_BIT)))
    expected[SHOT + ACTOR_SPRITE] = 0
    _run_weapon(what, pokes, expected)


@pytest.mark.parametrize("item", [WEAPON_WIND_SPOUTS, WEAPON_FIRE_BALLS, BOMB_ITEM],
                         ids=["wind-spout", "fireball", "bomb"])
def test_a_FULL_POOL_ends_the_frame_without_spending_a_shot(item):
    """All three spawn arms `rts` on a null a1, and that `rts` is ABOVE the shared `sbcd` — so a
    player firing into a full actor table loses nothing. The lightning has no such arm, which is
    what makes it the only item that always costs one."""
    what = f"player_weapon_fire full pool item={item:#04x}"
    pokes = _weapon_pokes(what, item, pool_full=True)
    # THE WITNESS IS WHAT MAKES THIS ROW ABOUT THE ALLOCATOR: four gates and a four-way dispatch sit
    # above it, and every one of them also refuses by writing nothing. So the run has to have
    # reached `actor_alloc_slot_high`'s own "pool is full" store and NOT the shared spend.
    _run_refused(what, pokes, ALLOC_REFUSED, WEAPON_SPEND)


@pytest.mark.parametrize("count", [0x05, 0x10, 0x01, 0x20],
                         ids=["ordinary", "bcd-borrow", "last-one", "bcd-borrow-high"])
def test_the_shot_is_spent_in_PACKED_BCD_and_the_record_is_POPPED_at_zero(count):
    """`sbcd` and not `subq`: a count of $10 goes to $09, not to $0f. `last-one` is the frame the
    count reaches zero, on which `tst.b (a6)` — which RE-READS the byte just written — rewinds
    WB_EFFECT_RECORD_WRITE_PTR by one record, i.e. drops the weapon."""
    what = f"player_weapon_fire spend count={count:#04x}"
    pokes = _weapon_pokes(what, WEAPON_LIGHTNING, count=count)

    expected = _spend_bytes(count)
    _put_word(expected, FLASH_TIMER, LIGHTNING_FLASH)
    _run_weapon(what, pokes, expected)


# --- THE ENTRY X, and why this site is not like the SIX hud.h tabulates ----------------------------
#
# `sbcd -(a2),-(a6)` folds the X flag in as a second unit of subtrahend, and on THREE of the four
# arms that bit is the CALLER's: nothing between $1208's entry and the instruction writes it (the
# complete enumeration is include/player.h's, and it has to include `joy1_newly_pressed`'s `eor.b`
# and `and.b`, which run on every path and leave X alone), and `emu.run` forces the CCR clear — so
# those three are the same unpinnable class as the SHOP's subtract, which is the one entry in that
# header's table nothing can drive. They are NOT the class of $6c26, which produces its own bit, or
# of $4e5a/$522e, which are pinned over the paths their seeds take. The FIREBALL arm is different
# again — `subq.w #8,2(a1)` produces the bit INSIDE the routine, out of the shot's own y — so it is
# drivable by an ordinary differential row, which is what the two cases below are. One site, both
# classes.

def test_a_fireball_launched_off_a_LOW_y_borrows_and_spends_TWO(): 
    """`subq.w #8,2(a1)` on a y below WB_PLAYER_FIREBALL_Y_RISE borrows, and the X that borrow
    leaves is the `sbcd`'s entry X twelve instructions later — so the shot costs two units instead
    of one. THE FIRST SITE IN THIS PROJECT WHERE A THREADED EXTEND IS ALSO LOCALLY PRODUCED, and the
    only one a case can drive at all."""
    what = "player_weapon_fire fireball off a low y"
    low_y = FIREBALL_Y_RISE - 1
    pokes = _weapon_pokes(what, WEAPON_FIRE_BALLS, count=0x09,
                          fields={ACTOR + ACTOR_Y: word(low_y)})

    expected = _spend_bytes(0x09, borrow=1)
    _put_word(expected, SHOT + ACTOR_TYPE, SHOT_TYPE_FIREBALL)
    expected[SHOT + FIELD_30] = SHOT_LIFETIME
    _put_word(expected, SHOT + ACTOR_X, PLAYER_X)
    _put_word(expected, SHOT + ACTOR_Y, (low_y - FIREBALL_Y_RISE) & 0xffff)
    expected[SHOT + ACTOR_FLAGS] = SHOT_FLAGS_SEED & ~(1 << SIDE_BIT)
    expected[SHOT + ACTOR_SPRITE] = 0
    _run_weapon(what, pokes, expected)


def test_the_SAME_fireball_off_a_high_y_spends_one():
    """The other side of the borrow, on a seed identical but for the y — which is what makes the row
    above a claim about the X flag rather than about the count."""
    what = "player_weapon_fire fireball off a high y"
    pokes = _weapon_pokes(what, WEAPON_FIRE_BALLS, count=0x09)

    expected = _spend_bytes(0x09, borrow=0)
    _put_word(expected, SHOT + ACTOR_TYPE, SHOT_TYPE_FIREBALL)
    expected[SHOT + FIELD_30] = SHOT_LIFETIME
    _put_word(expected, SHOT + ACTOR_X, PLAYER_X)
    _put_word(expected, SHOT + ACTOR_Y, PLAYER_Y - FIREBALL_Y_RISE)
    expected[SHOT + ACTOR_FLAGS] = SHOT_FLAGS_SEED & ~(1 << SIDE_BIT)
    expected[SHOT + ACTOR_SPRITE] = 0
    _run_weapon(what, pokes, expected)


def test_the_two_fireball_rows_really_do_differ_in_the_bit_they_are_about():
    """A guard on the pair above, not on the game: if WB_PLAYER_FIREBALL_Y_RISE were zero neither
    seed could borrow and both rows would pass on the same arithmetic."""
    assert FIREBALL_Y_RISE > 0
    assert _spend_bytes(0x09, borrow=1) != _spend_bytes(0x09, borrow=0)


@pytest.mark.parametrize("item", [WEAPON_LIGHTNING, WEAPON_WIND_SPOUTS, BOMB_ITEM],
                         ids=["lightning", "wind-spout", "bomb"])
def test_the_three_OTHER_arms_carry_the_callers_extend_and_no_case_here_can_set_it(item):
    """THE LIMITATION, as a tripwire rather than as prose. `emu.run` forces SR = $2700 after its
    reset and there is no entry-CCR parameter, so every differential row above enters with X clear —
    which is why the wind spout, the bomb and the lightning are pinned only for X = 0.

    The reconstruction still THREADS the bit (it is a parameter), and this case is what says the
    parameter is live: run alone, the same seed with entry_extend = 1 spends two rather than one. It
    is a `run_candidate_only` claim against an independent model of the arithmetic, which is weaker
    than the oracle and stronger than nothing — the same standing test_hud.py's model-only `sbcd`
    rows have. If the kit ever gains an entry-CCR parameter, these become differential rows.
    ("The sites include/hud.h tabulates" is the scoped claim, not "all of them are unpinnable": that
    header's own table has one site a row DOES drive and two more pinned over their exercised
    paths.)

    ONE ROW PER CARRIER ARM, because the three do not reach the spend the same way: the lightning
    falls to it directly, and the other two go through the allocator and `player_arm_thrown_shot`
    first. A port that dropped the bit on ONE of those paths — the shape a `switch` arm invites —
    answered a single-arm row identically."""
    what = f"player_weapon_fire item={item:#04x} with the caller's X set"
    pokes = _weapon_pokes(what, item, count=0x09)

    _, image = leaf.run_candidate_only(_WEAPON_FIRE(ACTOR, 1), pokes)
    left = image[WEAPON_RECORD + RECORD_LOW_BYTE]
    assert left == _spend_bytes(0x09, borrow=1)[WEAPON_RECORD + RECORD_LOW_BYTE], (
        f"an entry X of 1 left {left:#04x} in the count, not the model's")


# ==================================================================================================
# $1f54 — THE STAGE TRANSITION, the frame's LAST call
# ==================================================================================================
#
# Four flag arms and a posture selector, and what the cases below have to seed that nothing above
# them did is the FOUR CURSORS and the THREE POSTURE RECORDS, all of which live in the program's own
# data at $21e4..$23b5. They are seeded as keyed blocks so that a frame published from the wrong
# table, or a cursor stepped by the wrong amount, lands on a byte that is wrong for WHERE IT CAME
# FROM rather than on a plausible sprite id.

_STAGE_TRANSITION = leaf.register_glue("player_stage_transition", [ctypes.c_uint32])


# --- the operand censuses, as CASES ------------------------------------------------------------
#
# Four of this section's plates rest on a count of how many instructions in the whole image name an
# address, and the sharpest of them — "entries 0, 2 and 4 of both attack tables are unreachable" —
# rests on WB_PLAYER_ATTACK_CURSOR having exactly TWO. A count in prose is a count nothing checks,
# and this batch has two reasons to distrust one: the $21e4 census that said "no reader at all"
# missed a whole ENCODING for three batches, and a naive scan for $b10 finds a `bsr.w`
# DISPLACEMENT that happens to equal the address. So the hand-filtering is recorded here.
#
# The scan starts from the SUPERSET — every aligned position in the program holding the address as a
# word, which is a short operand whole AND a long one's low half — and then classifies each against
# the absolute-addressing forms below. Anything that matches none is reported with the word in front
# of it, which is what makes the two near-misses visible rather than quietly dropped.

# (opcode word, byte offset of the operand word within the instruction, is the operand a LONGWORD).
# Every form the four addresses below are actually named by; a fifth form would show up as an
# unclassified candidate rather than being silently missed.
ABSOLUTE_FORMS = (
    (0x4a78, 2, False),      # tst.w   <abs>.w
    (0x4a79, 4, True),       # tst.w   <abs>.l
    (0x4278, 2, False),      # clr.w   <abs>.w
    (0x42b8, 2, False),      # clr.l   <abs>.w   — clears the NEXT word too, without naming it
    (0x31fc, 4, False),      # move.w  #imm,<abs>.w
    (0x33fc, 6, True),       # move.w  #imm,<abs>.l
    (0x0c79, 6, True),       # cmpi.w  #imm,<abs>.l
    (0x3039, 4, True),       # move.w  <abs>.l,Dn
    (0x33c0, 4, True),       # move.w  Dn,<abs>.l
)


def _image_word_at(addr):
    return int.from_bytes(harness.BASE_IMAGE[addr:addr + WORD_BYTES], "big")


def _absolute_operand_census(addr):
    """({instruction address: opcode word}, {unclassified word position: the word before it}).

    A candidate is a real operand when the bytes that would have to precede it for one of the forms
    above really do; a `.l` form additionally needs the operand's HIGH half to be zero, which is what
    separates `$000021e4` from a coincidence."""
    named, other = {}, {}
    for at in _operand_sites(word(addr)):
        if at % WORD_BYTES or at + WORD_BYTES > loader.PROGRAM_END:
            continue
        hits = [(at - offset, opcode_word) for opcode_word, offset, is_long in ABSOLUTE_FORMS
                if _image_word_at(at - offset) == opcode_word
                and (not is_long or _image_word_at(at - WORD_BYTES) == 0)]
        assert len(hits) <= 1, f"{at:#x} classifies as {len(hits)} different instructions"
        if hits:
            named[hits[0][0]] = hits[0][1]
        else:
            other[at] = _image_word_at(at - WORD_BYTES)
    return named, other


# {address: (what its operand sites are, what the candidates that are NOT operands are)}. Every
# figure a plate in this section quotes is one of these lengths.
OPERAND_CENSUS = {
    "PLAYER_ATTACK_CURSOR": ({0x20de: 0x3039,           # move.w $2372.l,d0
                              0x2120: 0x33c0},          # move.w d0,$2372.l
                             # ...and a word of DATA past the program's code, inside the sound
                             # module's tables — no instruction in front of it.
                             {0x1002e: 0x009a}),
    "STAGE_ANIM_REQUEST_B0E": ({0xb22: 0x4a78,          # tst.w $b0e.w   (the gate)
                                0xc6a: 0x42b8,          # clr.l $b0e.w   (takes $b10 with it)
                                0x19a4: 0x31fc,         # move.w #$ffff,$b0e.w (the boss-defeat arm)
                                0x1f5e: 0x4a78},        # tst.w $b0e.w   (this routine)
                               {}),
    "STAGE_ANIM_DONE_B10": ({0xc28: 0x4a78,             # tst.w $b10.w   (the gate)
                             0x1f54: 0x4a78,            # tst.w $b10.w   (this routine's first insn)
                             0x1f9a: 0x31fc},           # move.w #$ffff,$b10.w
                            # THE NEAR-MISS, and the reason this census is a case: the word in front
                            # is a `bsr.w` opcode, so $450a is that call's DISPLACEMENT and not an
                            # operand at all. A scan that only matched the address would count four.
                            {0x450a: 0x6100}),
    "STAGE_ANIM_DONE_B18": ({0xcf0: 0x4a78,             # tst.w $b18.w   (the gate)
                             0xd02: 0x4278,             # clr.w $b18.w   (the gate)
                             0x1fc8: 0x31fc},           # move.w #$ffff,$b18.w
                            {}),
    "EFFECT_STATE_21E4": ({0xc06: 0x33fc,               # move.w #$1,$21e4.l  — the ONLY abs.L site
                           0x1f6e: 0x4a79,              # tst.w  $21e4.l      \
                           0x2018: 0x0c79,              # cmpi.w #$1,$21e4.l   | the five READERS,
                           0x205e: 0x4a79,              # tst.w  $21e4.l       | all in $1f54
                           0x2072: 0x0c79,              # cmpi.w #$1,$21e4.l   |
                           0x20d4: 0x4a79,              # tst.w  $21e4.l      /
                           0xfe56: 0x4278,              # clr.w  $21e4.w  — the new-game reset
                           0x101c6: 0x31fc,             # move.w #$1,$21e4.w  — the scene exit action
                           0x10350: 0x31fc,             # move.w #$2,$21e4.w  \  the three $bd68
                           0x10360: 0x31fc,             #                      | effect handlers
                           0x10370: 0x31fc},            #                     /
                          # ...and a `bra.w` displacement, the second near-miss.
                          {0x4962: 0x6000}),
}


@pytest.mark.parametrize("name", sorted(OPERAND_CENSUS), ids=sorted(OPERAND_CENSUS))
def test_each_plates_operand_census_is_the_one_the_image_holds(name):
    """The counts four plates in ../names.txt and include/wonderboy.h quote, rebuilt from the bytes.

    BOTH HALVES ARE ASSERTED. The positive one is the map of instruction address to opcode — so a
    site claimed at the wrong address, or claimed as the wrong instruction, fails here. The negative
    one is the list of candidates that are NOT operands, WITH the word in front of each: that is
    where a census goes wrong, and two of these five addresses have such a candidate."""
    named, other = _absolute_operand_census(wb(name))
    expected_named, expected_other = OPERAND_CENSUS[name]
    assert named == expected_named, (
        f"{name} is named by "
        f"{ {hex(at): hex(op) for at, op in sorted(named.items())} }, not the plate's "
        f"{ {hex(at): hex(op) for at, op in sorted(expected_named.items())} }")
    assert other == expected_other, (
        f"{name} has unclassified candidates "
        f"{ {hex(at): hex(op) for at, op in sorted(other.items())} }, not "
        f"{ {hex(at): hex(op) for at, op in sorted(expected_other.items())} }")


def test_the_attack_cursor_is_written_by_NOTHING_outside_the_swing():
    """THE HEADLINE CLAIM's other half. Two sites is only half of "every swing starts at zero": the
    other half is that BOTH of them are inside `player_stage_transition`, so no reset, no
    new-game path and no other handler ever puts the cursor anywhere else — and the .PRG ships it
    zero, which is what makes the claim true from boot rather than only after the first swing."""
    named, _ = _absolute_operand_census(ATTACK_CURSOR)
    entry = leaf.entry_of("player_stage_transition")
    assert all(entry <= at < entry + BODY_SIZES["player_stage_transition"] for at in named), (
        f"the attack cursor is named from outside $1f54: {[hex(at) for at in sorted(named)]}")
    assert _image_word_at(ATTACK_CURSOR) == 0, (
        "the .PRG does not ship the attack cursor at zero, so a swing can start elsewhere")


def test_the_only_absolute_LONG_writer_of_the_form_word_is_the_gates_unwinding_arm():
    """THE ENCODING-BLIND CLASS, pinned. `$21e4 has no reader at all` stood for three batches because
    the census behind it looked at one encoding; the SAME address has exactly one writer in the OTHER
    encoding, and it is not incidental — `move.w #$1,$21e4.l` at $c06 sits between
    `jsr $fe8c.l` (the life restart) and `lea 4(a7),a7 / jmp $e5ba.l`, so THE GATE FORCES THE
    PLAYER'S FORM BACK TO 1 ON A STACK-UNWINDING EXIT."""
    named, _ = _absolute_operand_census(EFFECT_STATE_21E4)
    long_form = {at for at, op in named.items() if op == 0x33fc}
    assert long_form == {0xc06}, f"the abs.l writers are {[hex(at) for at in sorted(long_form)]}"
    assert CONTROL_FLOW_TARGETS.get(0xe5ba) and 0xc20 in CONTROL_FLOW_TARGETS[0xe5ba], (
        "the arm holding that write does not end in the `jmp $e5ba.l` this case is about")

# The whole data block above the routine, as ONE keyed band: the three posture records and the four
# cursor-plus-table animations. Bounded at both ends by code — WB_EFFECT_STATE_21E4's word is the
# first byte and `actor_hit_by_player_shot`'s entry the byte past the last.
TRANSITION_DATA_LO = EFFECT_STATE_21E4
# ...and its END is NOT a number: it is the entry ../names.txt gives the next routine, which is what
# bounds the block at the top. A hard-coded length is the failure mode this batch has to guard —
# one that fell short would leave the attack tables on the .PRG's shipped bytes, where entries 0 and
# 2 hold the same sprite id and the headline unreachable-frames case passes vacuously.
TRANSITION_DATA_HI = leaf.entry_of("actor_hit_by_player_shot")
TRANSITION_DATA_LEN = TRANSITION_DATA_HI - TRANSITION_DATA_LO

# ...and the SAME length again, out of the block's own composition — the six spans this section's
# table claims it divides into. TWO INDEPENDENT STATEMENTS ARE THE POINT: a tripwire that measured
# the band with the very constant it seeds from cannot fail, because trimming that constant shrinks
# the check with the seed. The structural case below requires these two to agree, and the tripwire
# measures with THIS one.
TRANSITION_DATA_DIVIDED = (WORD_BYTES                                  # WB_EFFECT_STATE_21E4
                           + 3 * POSTURE_BYTES                         # the three posture records
                           + WORD_BYTES + (ANIM32_MASK + 1)            # the DEATH animation
                           + WORD_BYTES + 2 * TRANSITION_TABLE_BYTES   # the TRANSITION animation
                           + WORD_BYTES + 2 * (ATTACK_MASK + 1)        # the SWING animation
                           + WORD_BYTES + (ANIM32_MASK + 1))           # the EVENT animation

# The ladder's frames are the one table NOT in that block: DATA inside the routine's own body, and
# as many bytes as its cursor mask spans. Keyed for the block's reason — the shipped four are two
# ids held twice each, so a cursor stepped by the wrong amount lands on the same word.
LADDER_FRAME_BYTES = LADDER_SPRITE_MASK + 1
LADDER_FRAMES = LADDER_FRAME_BYTES // WORD_BYTES
# The bands every case in this section reads out of the image, and NEITHER length is the one the
# seeding uses: the block is measured by its own division and the ladder's frames by the CURSOR MASK
# that bounds them. Route either through the seeding's own constant and the guard stops guarding.
TRANSITION_SEEDED_BANDS = ((TRANSITION_DATA_LO, TRANSITION_DATA_DIVIDED),
                           (LADDER_SPRITES, LADDER_SPRITE_MASK + 1))

# The four words WB_EFFECT_STATE_21E4 can hold that this routine reads differently. `2` is what
# src/effects.c's own stub writes, so the "anything else" arm is reachable from shipped code.
TRANSITION_STATES = (0, POSTURE_STATE_ONE, 2)
POSTURE_FOR_STATE = {0: POSTURE_TABLE_0, POSTURE_STATE_ONE: POSTURE_TABLE_1, 2: POSTURE_TABLE_2}

STAGE_TRANSITION_CAP = _cap("player_stage_transition", extra=STUB_INSN_CAP)


def _transition_pokes(what, flags=0, flags2=0, fields=None):
    """A seeded image for $1f54: the record, the whole $21e4 data block, the eight bytes of frame
    table INSIDE the body, and the four flag words this routine's chain tests — all four seeded
    CLEAR here, so a case raises exactly the one whose arm it is about.

    THE DATA AND THE STATE ARE TWO LAYERS, and that is not style. WB_EFFECT_STATE_21E4 IS the data
    block's first address, so a single dict LITERAL holding both keys drops the keyed band
    entirely — `leaf.overlay`'s documented hazard in its dict-literal spelling, and the fifth time
    it has fired in this project. The first draft of this battery did exactly that and every case
    below ran on the .PRG's SHIPPED tables, where posture record 0's jump pair and its fall pair are
    the same two sprite ids; the mutation sweep's `posture/falling-asked-before-jumping` survived on
    that and is caught here."""
    salt = case_salt(what) ^ 3
    data = {TRANSITION_DATA_LO: keyed_block(TRANSITION_DATA_LO, TRANSITION_DATA_LEN, salt),
            LADDER_SPRITES: keyed_block(LADDER_SPRITES, LADDER_FRAME_BYTES, salt)}
    state = {STAGE_ANIM_DONE_B10: word(0),
             STAGE_ANIM_REQUEST_B0E: word(0),
             EVENT_ANIM_DONE_B16: word(0),
             STAGE_RESET_BLOCK: word(0),
             STAGE_ANIM_DONE_B18: word(MARKER),
             EFFECT_STATE_21E4: word(0),
             TILE_33_MODE: word(0),
             TILE_33_STEP: word(0),
             ACTOR + ACTOR_FLAGS: bytes([flags]),
             ACTOR + FLAGS2: bytes([flags2]),
             ACTOR + ACTOR_SPRITE: word(MARKER)}
    return _pokes(what, leaf.overlay(data, state, fields or {}))


def _run_transition(what, pokes, expected):
    info = leaf.run("player_stage_transition", _STAGE_TRANSITION(ACTOR), merge_bands(expected),
                    what, regs={"a0": ACTOR, "_pokes": pokes}, max_insns=STAGE_TRANSITION_CAP)
    _assert_writes(info, expected, what)
    return info


def _image_word(image, addr):
    return int.from_bytes(image[addr:addr + WORD_BYTES], "big")


def test_the_seeding_really_reaches_every_band_this_section_reads():
    """THE TRIPWIRE for `leaf.overlay`'s hazard in its dict-LITERAL spelling, and it is here because
    the hazard FIRED: WB_EFFECT_STATE_21E4 is the data block's own first address, so a poke dict
    holding both keys drops the keyed band and every case below then runs on the .PRG's shipped
    tables. That is not merely weaker — posture record 0's jump pair and fall pair are the SAME two
    sprite ids there, so a port that swapped them answered identically, and the mutation sweep said
    so.

    THE ASSERTION IS `leaf.assert_bands_are_seeded`, not "some byte differs": the property wanted is
    that EVERY byte of each band was poked, and that helper names the first address that was not.
    "Some byte differs" passes on a band seeded one word short — which is the failure mode a derived
    TRANSITION_DATA_LEN could still produce, and which would leave the attack tables shipped.

    The pairs below are the second half, and about the DATA rather than the seeding: a keyed band is
    only useful if the fields a mutant can swap now hold different words."""
    pokes = _transition_pokes("player_stage_transition seeding guard")
    leaf.assert_bands_are_seeded(pokes, TRANSITION_SEEDED_BANDS, "the transition's own data")

    image = harness.make_image(pokes)
    distinguishable = ((POSTURE_JUMP_LEFT, POSTURE_FALL_LEFT),
                       (POSTURE_JUMP_RIGHT, POSTURE_FALL_RIGHT),
                       (POSTURE_IDLE_RIGHT, POSTURE_IDLE_LEFT))
    for one, other in distinguishable:
        assert (_image_word(image, POSTURE_TABLE_0 + one)
                != _image_word(image, POSTURE_TABLE_0 + other)), (
            f"offsets {one} and {other} hold the same word, so a swap between them is invisible")
    for table in (ATTACK_TABLE_RIGHT, ATTACK_TABLE_LEFT):
        frames = [_image_word(image, table + i * WORD_BYTES) for i in range(ATTACK_MASK // 2 + 1)]
        assert len(set(frames)) == len(frames), (
            f"the attack table at {table:#x} repeats a frame, so a mis-stepped cursor is invisible")


@pytest.mark.parametrize("latch", [1, 0x8000, 0xffff], ids=lambda v: f"latch{v:#06x}")
def test_the_routine_is_an_rts_once_its_own_DONE_latch_is_up(latch):
    """`tst.w $b10.w / beq` — a plain nonzero test, and the whole routine is behind it. Nothing in
    this port clears the word: only the gate's `clr.l $b0e.w` at $c6a does, as a longword's low
    half."""
    what = f"player_stage_transition latched {latch:#06x}"
    pokes = _transition_pokes(what, fields={STAGE_ANIM_DONE_B10: word(latch)})

    info = leaf.run("player_stage_transition", _STAGE_TRANSITION(ACTOR), [], what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=STAGE_TRANSITION_CAP)
    assert not program_writes(info), f"{what}: a latched transition wrote memory"


@pytest.mark.parametrize("state", [0, 1], ids=["table-a", "table-b"])
@pytest.mark.parametrize("cursor", [0, 2, 0x2c], ids=lambda v: f"cursor{v:#04x}")
def test_the_transition_arm_walks_its_own_table_and_WB_EFFECT_STATE_21E4_picks_which(state, cursor):
    """The arm WB_STAGE_ANIM_REQUEST_B0E gates. Two tables, one cursor: `lea 48(a1),a1` steps over
    the first table to reach the second while the state word is nonzero, so the SAME cursor value
    publishes a different frame — which is what the two ids of this row separate."""
    what = f"player_stage_transition arm b0e state={state} cursor={cursor:#04x}"
    pokes = _transition_pokes(what, fields={STAGE_ANIM_REQUEST_B0E: word(EVENT_DONE_SET),
                                            EFFECT_STATE_21E4: word(state),
                                            TRANSITION_CURSOR: word(cursor)})
    image = harness.make_image(pokes)

    table = TRANSITION_CURSOR + WORD_BYTES + (TRANSITION_TABLE_BYTES if state else 0)
    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, table + cursor))
    _put_word(expected, TRANSITION_CURSOR, cursor + ANIM_FRAME_BYTES)
    _run_transition(what, pokes, expected)


def test_the_transition_arms_LAST_frame_wraps_the_cursor_and_raises_its_own_latch():
    """The cursor is stepped to WB_PLAYER_TRANSITION_TABLE_BYTES, cleared, and the zero it stores is
    what the `bne` below reads — so the completion flag goes up on the frame the animation ends,
    which then makes every later frame the `rts` the row above pins."""
    cursor = TRANSITION_TABLE_BYTES - ANIM_FRAME_BYTES
    what = "player_stage_transition arm b0e wrapping"
    pokes = _transition_pokes(what, fields={STAGE_ANIM_REQUEST_B0E: word(EVENT_DONE_SET),
                                            TRANSITION_CURSOR: word(cursor)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, TRANSITION_CURSOR + WORD_BYTES + cursor))
    _put_word(expected, TRANSITION_CURSOR, 0)
    _put_word(expected, STAGE_ANIM_DONE_B10, EVENT_DONE_SET)
    _run_transition(what, pokes, expected)


def test_the_transition_wrap_is_an_EQUALITY_so_an_odd_cursor_runs_past_the_table():
    """`cmp.w #$30,d0 / bne` and not a mask, which the row above cannot separate from
    `andi.w #$2f`. A cursor of $2f steps to $31, misses the compare, and is stored — so the next
    frame reads a word one byte into the SECOND table."""
    cursor = TRANSITION_TABLE_BYTES - 1
    what = "player_stage_transition arm b0e on an odd cursor"
    pokes = _transition_pokes(what, fields={STAGE_ANIM_REQUEST_B0E: word(EVENT_DONE_SET),
                                            TRANSITION_CURSOR: word(cursor)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, TRANSITION_CURSOR + WORD_BYTES + cursor))
    _put_word(expected, TRANSITION_CURSOR, cursor + ANIM_FRAME_BYTES)
    _run_transition(what, pokes, expected)


@pytest.mark.parametrize("cursor", [0, 4, ANIM32_MASK - 1], ids=lambda v: f"cursor{v:#04x}")
def test_the_two_sixteen_word_arms_step_their_own_cursor(cursor):
    """Arms 2 and 3 are one body with the cursor exchanged, so they are driven as one row. What
    differs is the ENDING, and the next case is that."""
    for flag, cursor_at in ((EVENT_ANIM_DONE_B16, EVENT_ANIM_CURSOR),
                            (STAGE_RESET_BLOCK, DEATH_ANIM_CURSOR)):
        what = f"player_stage_transition arm {flag:#x} cursor={cursor:#04x}"
        pokes = _transition_pokes(what, fields={flag: word(EVENT_DONE_SET),
                                                cursor_at: word(cursor)})
        image = harness.make_image(pokes)

        stepped = (cursor + ANIM_FRAME_BYTES) & ANIM32_MASK
        expected = {}
        _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, cursor_at + WORD_BYTES
                                                              + cursor))
        _put_word(expected, cursor_at, stepped)
        if stepped == 0 and flag == EVENT_ANIM_DONE_B16:
            _put_word(expected, STAGE_ANIM_DONE_B18, EVENT_DONE_SET)
            _put_word(expected, ACTOR + ACTOR_SPRITE, SPRITE_HIDDEN)
        _run_transition(what, pokes, expected)


def test_the_EVENT_arms_wrap_raises_the_gates_handshake_and_BLANKS_the_sprite_it_just_published():
    """The one arm here that publishes twice in one frame: the frame word goes into the record and
    is then overwritten with zero. The ledger records FINAL values, so what makes this a claim about
    the ORDER rather than about the last store is the write set — the sprite is written once, and to
    WB_ACTOR_SPRITE_HIDDEN.

    The DEATH arm at the same cursor is the control: it has no completion flag of its own and
    `bra.w`s to the shared `rts` instead, so it leaves the wrapped frame published."""
    cursor = ANIM32_MASK - 1
    ids = {}
    for flag, cursor_at in ((EVENT_ANIM_DONE_B16, EVENT_ANIM_CURSOR),
                            (STAGE_RESET_BLOCK, DEATH_ANIM_CURSOR)):
        what = f"player_stage_transition wrap of {flag:#x}"
        pokes = _transition_pokes(what, fields={flag: word(EVENT_DONE_SET),
                                                cursor_at: word(cursor)})
        image = harness.make_image(pokes)
        ids[flag] = _image_word(image, cursor_at + WORD_BYTES + cursor)

        expected = {}
        _put_word(expected, cursor_at, 0)
        if flag == EVENT_ANIM_DONE_B16:
            _put_word(expected, ACTOR + ACTOR_SPRITE, SPRITE_HIDDEN)
            _put_word(expected, STAGE_ANIM_DONE_B18, EVENT_DONE_SET)
        else:
            _put_word(expected, ACTOR + ACTOR_SPRITE, ids[flag])
        _run_transition(what, pokes, expected)

    assert ids[EVENT_ANIM_DONE_B16] != SPRITE_HIDDEN, (
        "the event arm's last frame IS the blank, so the row above passes vacuously")


def test_the_chain_is_tested_in_order_so_an_earlier_flag_hides_a_later_one():
    """All four flags up at once: only the FIRST arm runs. This is what says the three `beq`s are a
    chain and not three independent tests — a port that ran the arms in any other order writes a
    different cursor."""
    what = "player_stage_transition with every flag raised"
    pokes = _transition_pokes(what, fields={STAGE_ANIM_REQUEST_B0E: word(EVENT_DONE_SET),
                                            EVENT_ANIM_DONE_B16: word(EVENT_DONE_SET),
                                            STAGE_RESET_BLOCK: word(EVENT_DONE_SET),
                                            TRANSITION_CURSOR: word(4)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, TRANSITION_CURSOR + WORD_BYTES + 4))
    _put_word(expected, TRANSITION_CURSOR, 4 + ANIM_FRAME_BYTES)
    _run_transition(what, pokes, expected)


# --- $1ffc: the hurt arm ----------------------------------------------------------------------------

@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
@pytest.mark.parametrize("state", [0, POSTURE_STATE_ONE, 2], ids=lambda v: f"state{v}")
def test_a_hurt_AIRBORNE_record_shows_one_of_four_fixed_sprites(state, facing_left):
    """WB_ACTOR_FLAGS2_BIT_0 set and WB_ACTOR_FLAG_SUPPORTED_BIT clear. TWO pairs, and only
    WB_PLAYER_POSTURE_STATE_ONE reaches the first — states 0 and 2 both take the second, which is
    what makes the `cmpi.w #$1` an equality rather than a "nonzero" test."""
    what = f"player_stage_transition hurt state={state} left={facing_left}"
    flags = (1 << SIDE_BIT) if facing_left else 0
    pokes = _transition_pokes(what, flags=flags, flags2=1 << FLAGS2_BIT_0,
                              fields={EFFECT_STATE_21E4: word(state)})

    first = state == POSTURE_STATE_ONE
    sprite = ((HURT_SPRITE_LEFT if facing_left else HURT_SPRITE_RIGHT) if first
              else (HURT2_SPRITE_LEFT if facing_left else HURT2_SPRITE_RIGHT))
    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, sprite)
    _run_transition(what, pokes, expected)


def test_a_hurt_record_that_is_STANDING_falls_through_to_the_ordinary_selector():
    """The `bsr $205c / bra $205e` path — a call into a bare `rts` and then the selector, so a hurt
    record on the ground shows an ordinary posture.

    Run TWICE on one seed differing in exactly the hurt bit, and the two ORACLE write sets compared:
    the salt comes from the SEED's name rather than the run's, so the two images are identical bar
    that byte and an equal write set is a claim about the routine and not about this file's own
    arithmetic. (The first draft compared two `expected` dicts it had built the same way, which is
    the vacuous form of this case.)"""
    seed = "player_stage_transition standing"
    flags = (1 << SUPPORTED_BIT) | (1 << MOVED_BIT)
    cursor_at, cursor = POSTURE_TABLE_0 + POSTURE_WALK_RIGHT, 4
    observed = []
    for flags2 in (1 << FLAGS2_BIT_0, 0):
        what = f"{seed} hurt={flags2 != 0}"
        pokes = _transition_pokes(seed, flags=flags, flags2=flags2,
                                  fields={cursor_at: word(cursor)})
        image = harness.make_image(pokes)

        expected = {}
        _put_word(expected, ACTOR + ACTOR_SPRITE,
                  _image_word(image, cursor_at + WORD_BYTES + cursor))
        _put_word(expected, cursor_at, cursor + ANIM_FRAME_BYTES)
        observed.append(program_writes(_run_transition(what, pokes, expected)))
    assert observed[0] == observed[1], (
        "the hurt-but-standing frame differs from the ordinary one, so the `bsr $205c` arm is not "
        "the fall-through this case claims")


# --- $205e: the posture selector ---------------------------------------------------------------------

@pytest.mark.parametrize("state", TRANSITION_STATES, ids=lambda v: f"state{v}")
def test_WB_EFFECT_STATE_21E4_picks_which_of_the_three_posture_records_is_read(state):
    """Zero, exactly one, anything else — three `lea`s, and the record they name is where every
    fixed posture below comes from. The row is driven on the IDLE field because that is the one
    reached by the shortest path."""
    what = f"player_stage_transition idle state={state}"
    pokes = _transition_pokes(what, fields={EFFECT_STATE_21E4: word(state)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, POSTURE_FOR_STATE[state] + POSTURE_IDLE_RIGHT))
    _run_transition(what, pokes, expected)


@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
@pytest.mark.parametrize("flags,left_field,right_field", [
    (1 << MOVING_BIT, POSTURE_JUMP_LEFT, POSTURE_JUMP_RIGHT),
    (1 << LAUNCHED_BIT, POSTURE_JUMP_LEFT, POSTURE_JUMP_RIGHT),
    (1 << FALLING_BIT, POSTURE_FALL_LEFT, POSTURE_FALL_RIGHT),
    (0, POSTURE_IDLE_LEFT, POSTURE_IDLE_RIGHT),
], ids=["moving", "launched", "falling", "idle"])
def test_each_posture_reads_the_pair_of_fields_its_own_flag_bit_names(flags, left_field,
                                                                      right_field, facing_left):
    """FOUR questions in order, each answered by a pair WB_ACTOR_FLAG_SIDE_BIT chooses between —
    and `moving` and `launched` are separate rows because the original asks them as ONE question
    (`bne` past the second) where a port could easily ask them as two.

    THE FIELD ORDER FLIPS: idle is (right, left) at offsets 0 and 6 where jump and fall are
    (left, right). Every row here reads its field out of the seeded record, so a pair swapped in
    src/player.c reads a byte that is wrong for where it came from."""
    what = f"player_stage_transition posture flags={flags:#04x} left={facing_left}"
    if facing_left:
        flags |= 1 << SIDE_BIT
    pokes = _transition_pokes(what, flags=flags)
    image = harness.make_image(pokes)

    field = left_field if facing_left else right_field
    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, POSTURE_TABLE_0 + field))
    _run_transition(what, pokes, expected)


@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
@pytest.mark.parametrize("flags,field", [
    ((1 << MOVING_BIT) | (1 << FALLING_BIT) | (1 << MOVED_BIT), "jump"),
    ((1 << LAUNCHED_BIT) | (1 << FALLING_BIT) | (1 << MOVED_BIT), "jump"),
    ((1 << FALLING_BIT) | (1 << MOVED_BIT), "fall"),
], ids=["moving+falling+moved", "launched+falling+moved", "falling+moved"])
def test_the_FOUR_POSTURE_QUESTIONS_ARE_ASKED_IN_ORDER(flags, field, facing_left):
    """THE MUTATION SWEEP'S FINDING, and the row above cannot make it: each of those seeds ONE flag,
    so a port that asked the four questions in any order answered them all identically. The
    mutant that reorders `falling` above `moving`/`launched` survived TWO sweeps on that.

    What separates the orders is a record carrying MORE THAN ONE of the bits, which is ordinary —
    `player_reset_ground_state` leaves a record MOVING and LAUNCHED, the settle raises FALLING, and
    the walk raises MOVED every frame a direction is held. The original asks MOVING-or-LAUNCHED
    first, so all three of those show the JUMP pair or the FALL pair and never the walk cycle: the
    third row is the control that keeps the assertion from passing on "always jump".

    IT ALSO NEEDS THE KEYED DATA BLOCK. On the .PRG's shipped bytes posture record 0's jump pair and
    fall pair are the same two sprite ids, so even this seed would not separate them — which is the
    other half of why that mutant survived, and why the tripwire above exists."""
    what = f"player_stage_transition order flags={flags:#04x} left={facing_left}"
    if facing_left:
        flags |= 1 << SIDE_BIT
    pokes = _transition_pokes(what, flags=flags)
    image = harness.make_image(pokes)

    offsets = {"jump": (POSTURE_JUMP_LEFT, POSTURE_JUMP_RIGHT),
               "fall": (POSTURE_FALL_LEFT, POSTURE_FALL_RIGHT)}[field]
    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, POSTURE_TABLE_0 + offsets[0 if facing_left else 1]))
    _run_transition(what, pokes, expected)


@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
@pytest.mark.parametrize("cursor", [0, 4, ANIM32_MASK - 1], ids=lambda v: f"cursor{v:#04x}")
def test_a_record_that_MOVED_this_frame_runs_the_walk_cycle_out_of_the_posture_record(cursor,
                                                                                      facing_left):
    """WB_ACTOR_FLAG_MOVED_BIT is what `player_step_and_arm`'s three `bset`/`bclr` sites BUY, and
    this is its one reader in the image. The cursor is not a global: each posture record carries its
    own, one per facing, at WB_PLAYER_POSTURE_WALK_LEFT / _RIGHT — so the two facings step DIFFERENT
    words and a port that shared one would red the second id of this row."""
    what = f"player_stage_transition walk cursor={cursor:#04x} left={facing_left}"
    flags = (1 << MOVED_BIT) | ((1 << SIDE_BIT) if facing_left else 0)
    field = POSTURE_WALK_LEFT if facing_left else POSTURE_WALK_RIGHT
    cursor_at = POSTURE_TABLE_0 + field
    pokes = _transition_pokes(what, flags=flags, fields={cursor_at: word(cursor)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, cursor_at + WORD_BYTES + cursor))
    _put_word(expected, cursor_at, (cursor + ANIM_FRAME_BYTES) & ANIM32_MASK)
    _run_transition(what, pokes, expected)


def test_the_466_byte_data_block_divides_exactly():
    """THE ARITHMETIC THE SECTION RESTS ON, as a case. WB_PLAYER_POSTURE_WALK_LEFT's cursor plus its
    sixteen words ends EXACTLY on WB_PLAYER_POSTURE_BYTES — the third independent reading of that
    length, the other two being the two gaps between the three records — and the six spans together
    run from WB_EFFECT_STATE_21E4 to `actor_hit_by_player_shot`'s own entry with nothing over.

    IT IS ALSO THE TRIPWIRE'S SECOND STATEMENT: the seeding measures the block with
    TRANSITION_DATA_DIVIDED and the seed uses TRANSITION_DATA_LEN, so a wrong length fails HERE
    rather than shrinking the guard along with the band."""
    assert POSTURE_WALK_LEFT + WORD_BYTES + (ANIM32_MASK + 1) == POSTURE_BYTES
    assert POSTURE_TABLE_1 - POSTURE_TABLE_0 == POSTURE_BYTES
    assert POSTURE_TABLE_2 - POSTURE_TABLE_1 == POSTURE_BYTES
    assert POSTURE_TABLE_2 + POSTURE_BYTES == DEATH_ANIM_CURSOR
    assert TRANSITION_DATA_DIVIDED == TRANSITION_DATA_LEN, (
        f"the block's six spans sum to {TRANSITION_DATA_DIVIDED}, not the "
        f"{TRANSITION_DATA_LEN} between $21e4 and the next routine's entry")
    assert TRANSITION_DATA_LO + TRANSITION_DATA_DIVIDED == TRANSITION_DATA_HI


# --- $2096: the ladder, whose frame table is data inside the body -------------------------------------

@pytest.mark.parametrize("stepping", [False, True], ids=["held", "stepping"])
@pytest.mark.parametrize("cursor", [0, 2, 4, 6], ids=lambda v: f"cursor{v}")
def test_the_ladder_frame_comes_out_of_the_eight_bytes_inside_the_body(cursor, stepping):
    """WB_TILE_33_MODE nonzero takes this arm before the swing and before every posture. The frames
    are the four words at WB_PLAYER_LADDER_SPRITES, i.e. DATA INSIDE $1f54's own 656 bytes, and the
    cursor is WB_ACTOR_FIELD_18 masked to a byte offset within them.

    WB_TILE_33_STEP is what advances it — `player_apply_joystick` raises that word only on the frames
    the climb actually moved — so a player holding still on a ladder holds one frame."""
    what = f"player_stage_transition ladder cursor={cursor} stepping={stepping}"
    pokes = _transition_pokes(what, fields={TILE_33_MODE: word(TILE_33_MODE_UP),
                                            TILE_33_STEP: word(TILE_33_STEP_RAISED if stepping
                                                               else 0),
                                            ACTOR + FIELD_18: bytes([cursor])})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, LADDER_SPRITES + cursor))
    if stepping:
        expected[ACTOR + FIELD_18] = (cursor + ANIM_FRAME_BYTES) & LADDER_SPRITE_MASK
    _run_transition(what, pokes, expected)


def test_the_ladder_masks_the_cursor_it_READS_as_well_as_the_one_it_writes():
    """`andi.b #$7,d0` on the copy, above the `andi.b #$7,18(a0)` on the field. A field of $fe reads
    frame 6 and is stepped to 0 — so the read mask and the write mask are two instructions and a
    port that dropped the first would index eight bytes past the table."""
    what = "player_stage_transition ladder on an out-of-range cursor"
    pokes = _transition_pokes(what, fields={TILE_33_MODE: word(TILE_33_MODE_DOWN),
                                            TILE_33_STEP: word(TILE_33_STEP_RAISED),
                                            ACTOR + FIELD_18: bytes([0xfe])})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, LADDER_SPRITES + (0xfe & LADDER_SPRITE_MASK)))
    expected[ACTOR + FIELD_18] = (0xfe + ANIM_FRAME_BYTES) & LADDER_SPRITE_MASK
    _run_transition(what, pokes, expected)


def test_the_ladders_four_frames_are_the_two_sprite_ids_the_pin_claims():
    """The shipped bytes, read back — so the entry pin's transcription of them is checked against
    the image rather than only against itself."""
    frames = [_image_word(harness.BASE_IMAGE, LADDER_SPRITES + i * WORD_BYTES) for i in range(4)]
    assert frames == [LADDER_SPRITE_A, LADDER_SPRITE_A, LADDER_SPRITE_B, LADDER_SPRITE_B]


# --- $20ca: the swing -------------------------------------------------------------------------------

@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
def test_the_swings_FIRST_frame_is_indexed_by_the_SFX_ID_and_not_by_the_cursor(facing_left):
    """THE DEFECT, driven. On the frame the cursor is found at zero the original loads d0 with the
    effect id for the trigger call — and `snd_call_trigger_effect` is `movem.l d0-a6` either side of
    its `bsr`, so d0 comes back holding SIX. The very next instruction indexes the frame table with
    it.

    So the published frame is table entry WB_PLAYER_ATTACK_SFX and the cursor is stored as that plus
    one frame, NOT as one frame. Entries 0, 2 and 4 of both attack tables are therefore unreachable
    from a swing that starts at zero — and every swing does, because the wrap that ends one leaves
    the cursor there."""
    what = f"player_stage_transition swing opening left={facing_left}"
    flags = (1 << FIRED_BIT) | ((1 << SIDE_BIT) if facing_left else 0)
    pokes = _transition_pokes(what, flags=flags,
                              fields={EFFECT_STATE_21E4: word(POSTURE_STATE_ONE),
                                      ATTACK_CURSOR: word(0)})
    image = harness.make_image(pokes)

    table = ATTACK_TABLE_LEFT if facing_left else ATTACK_TABLE_RIGHT
    expected = _sfx_bytes(image, ATTACK_SFX, SND_CHANNEL_A)
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, table + ATTACK_SFX))
    _put_word(expected, ATTACK_CURSOR, (ATTACK_SFX + ANIM_FRAME_BYTES) & ATTACK_MASK)
    _run_transition(what, pokes, expected)


@pytest.mark.parametrize("facing_left", [False, True], ids=["facing-right", "facing-left"])
@pytest.mark.parametrize("cursor", [8, ATTACK_MASK - 1], ids=lambda v: f"cursor{v:#04x}")
def test_the_swing_walks_its_table_from_there_and_lowers_the_FIRED_bit_on_the_wrap(cursor,
                                                                                   facing_left):
    """The frames after the first: no SFX, the cursor stepped by one frame and masked to eight
    words, and — on the frame it comes back to zero — WB_ACTOR_FLAG_FIRED_BIT lowered, which is what
    ends the swing and hands the record back to the posture selector."""
    what = f"player_stage_transition swing cursor={cursor:#04x} left={facing_left}"
    flags = (1 << FIRED_BIT) | ((1 << SIDE_BIT) if facing_left else 0)
    pokes = _transition_pokes(what, flags=flags,
                              fields={EFFECT_STATE_21E4: word(POSTURE_STATE_ONE),
                                      ATTACK_CURSOR: word(cursor)})
    image = harness.make_image(pokes)

    table = ATTACK_TABLE_LEFT if facing_left else ATTACK_TABLE_RIGHT
    stepped = (cursor + ANIM_FRAME_BYTES) & ATTACK_MASK
    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, table + cursor))
    _put_word(expected, ATTACK_CURSOR, stepped)
    if stepped == 0:
        expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << FIRED_BIT)
    _run_transition(what, pokes, expected)


def test_an_armed_record_in_STATE_ZERO_swings_nothing_and_keeps_the_bit():
    """`tst.w $21e4.l / beq $2132` sits BETWEEN the `btst #7` and the cursor read, so the swing is
    gated on the state word as well as on the bit — and the bit survives, because the `bclr` is on
    the far side of the gate. The record shows an ordinary posture instead."""
    what = "player_stage_transition armed in state 0"
    flags = 1 << FIRED_BIT
    pokes = _transition_pokes(what, flags=flags, fields={ATTACK_CURSOR: word(0)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              _image_word(image, POSTURE_TABLE_0 + POSTURE_IDLE_RIGHT))
    _run_transition(what, pokes, expected)


def test_the_LADDER_is_asked_before_the_swing_and_the_swing_before_every_posture():
    """The three arms of $205e's tail, in order, on ONE seed that satisfies all of them: climbing,
    armed, and moving. Only the ladder runs. A port that asked them in any other order writes a
    different sprite AND a different cursor."""
    what = "player_stage_transition climbing, armed and moving at once"
    flags = (1 << FIRED_BIT) | (1 << MOVED_BIT)
    pokes = _transition_pokes(what, flags=flags,
                              fields={EFFECT_STATE_21E4: word(POSTURE_STATE_ONE),
                                      TILE_33_MODE: word(TILE_33_MODE_UP),
                                      TILE_33_STEP: word(0),
                                      ATTACK_CURSOR: word(4),
                                      ACTOR + FIELD_18: bytes([2])})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, LADDER_SPRITES + 2))
    _run_transition(what, pokes, expected)


def test_the_swing_is_asked_before_the_posture_on_a_seed_that_would_answer_both():
    """...and the second half of the order above, without the ladder: armed AND moving publishes the
    swing's frame and steps the ATTACK cursor, leaving the posture record's walk cursor alone."""
    what = "player_stage_transition armed and moving"
    flags = (1 << FIRED_BIT) | (1 << MOVED_BIT)
    pokes = _transition_pokes(what, flags=flags,
                              fields={EFFECT_STATE_21E4: word(POSTURE_STATE_ONE),
                                      ATTACK_CURSOR: word(4)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_SPRITE, _image_word(image, ATTACK_TABLE_RIGHT + 4))
    _put_word(expected, ATTACK_CURSOR, 4 + ANIM_FRAME_BYTES)
    _run_transition(what, pokes, expected)


# ==================================================================================================
# The ONE routine of the frame this port MEASURES rather than reconstructs
# ==================================================================================================
#
# `player_pending_event_gate` ($b1a) is the frame's second call and the only one still missing. It is
# UNPORTABLE rather than merely unported: THREE of its exits leave through a stack unwind instead of
# returning — `lea 4(a7),a7 / jmp` at $bdc and $c20, and `bra.w $1622` at $d16, which lands in
# `player_collide_and_scroll`'s own `lea 12(a7),a7 / jmp $e5ba.l` and so pops THREE return addresses
# in ANOTHER routine's body. That third one is why the count was two until batch 40 phase C: a census
# of this routine's own instructions cannot see a pop that happens somewhere else. What CAN be
# pinned about it from here is structural, and both claims below were live failure modes.

GATE_SPAWN_SITE = 0xc52            # `lea $998c.l,a2 / lea $537e.l,a1 / bsr.w $539e`
GATE_DESTINATION = 0x998c          # slot 1 of WB_ACTOR_TABLE_DEFAULT
STAGE_TRANSITION_ARM = 0x1fa2


def _image_operands_at(site):
    """The two `lea`s at ``site`` decoded back into (register, address) pairs, so a case can drive a
    composition with the operands the CALL SITE really carries instead of ones it chose."""
    pairs = []
    for at in (site, site + len(lea_abs_l(A2, 0))):
        opcode_word = int.from_bytes(harness.BASE_IMAGE[at:at + WORD_BYTES], "big")
        address = int.from_bytes(harness.BASE_IMAGE[at + WORD_BYTES:at + WORD_BYTES
                                                    + LONGWORD_BYTES], "big")
        pairs.append(((opcode_word >> 9) & 7, address))
    return pairs


# Keyed on the `lea`, which is where the pop IS; ../names.txt's plates name the `jmp` four bytes on
# ($bdc, $c20), and the two addresses being different is worth keeping straight in a case that is
# about counting them.
GATE_UNWIND_EXITS = {
    0xbd8: (0x4fef0004, 0xe494),     # lea 4(a7),a7 / jmp $e494.l — one return address
    0xc1c: (0x4fef0004, 0xe5ba),     # lea 4(a7),a7 / jmp $e5ba.l — one
}
# ...and the THIRD, which is not the gate's own instruction at all: it branches into
# `player_collide_and_scroll` and unwinds there.
GATE_UNWIND_VIA = 0x1622
COLLIDE_UNWIND = (0x4fef000c, 0xe5ba)   # lea 12(a7),a7 / jmp $e5ba.l — THREE return addresses


def _unwind_at(addr):
    """(the `lea n(a7),a7` longword, the address its `jmp` names) decoded out of the image."""
    return (int.from_bytes(harness.BASE_IMAGE[addr:addr + LONGWORD_BYTES], "big"),
            int.from_bytes(harness.BASE_IMAGE[addr + LONGWORD_BYTES + WORD_BYTES:
                                              addr + 2 * LONGWORD_BYTES + WORD_BYTES], "big"))


def test_the_gate_leaves_through_THREE_stack_unwinds_and_one_of_them_is_not_its_own():
    """WHY $b1a IS UNPORTABLE, counted. Two of the three are its own `lea 4(a7),a7 / jmp` pairs. The
    third is the one every surface in this project said did not exist until batch 40 phase C:
    `bra.w $1622` at $d16 lands inside `player_collide_and_scroll`, whose `lea 12(a7),a7 / jmp
    $e5ba.l` discards THREE return addresses — so the gate can unwind past its caller AND its
    caller's caller, through a pop written in another routine's body.

    That is the shape a census of one routine's own instructions cannot see, which is the same
    reason `$21e4` read as unread for three batches. Both halves are asserted: the pops are decoded
    out of the image, and the branch that reaches the third is required to be one of $1622's own
    two namers."""
    for at, expected in GATE_UNWIND_EXITS.items():
        assert _unwind_at(at) == expected, (
            f"the unwind at {at:#x} is {[hex(v) for v in _unwind_at(at)]}, not "
            f"{[hex(v) for v in expected]}")
    assert _unwind_at(GATE_UNWIND_VIA) == COLLIDE_UNWIND, (
        f"$1622 is {[hex(v) for v in _unwind_at(GATE_UNWIND_VIA)]}, not the triple pop")
    assert 0xd16 in CONTROL_FLOW_TARGETS[GATE_UNWIND_VIA], (
        "the gate does not branch to $1622, so the third exit is not the gate's")
    entry = leaf.entry_of("player_collide_and_scroll")
    assert entry < GATE_UNWIND_VIA < 0x19ac, (
        "$1622 is not inside player_collide_and_scroll, so the pop is not in another routine")
    # The pop's DEPTH is the claim that matters, and it is read off the `lea`'s displacement rather
    # than written down: 12 bytes of return addresses is three of them.
    assert (COLLIDE_UNWIND[0] & 0xffff) // LONGWORD_BYTES == 3


def test_the_gates_spawn_site_loads_the_TEMPLATE_in_a1_and_the_DESTINATION_in_a2():
    """THE LIVE FAILURE MODE batch 40 phase A registered and could not exercise: `scene_copy_record_
    fields` takes two record addresses and a port that swapped them would copy the record OVER the
    template and stay green in every case above, because each supplies both registers itself.

    So the operands come out of the image here. `lea $998c.l,a2` is the DESTINATION — slot 1 of
    WB_ACTOR_TABLE_DEFAULT, which the `cmpi.w #$ffbe,$998c.l` at $c36 has just checked is free — and
    `lea $537e.l,a1` is WB_ACTOR_TYPE35_TEMPLATE."""
    assert _image_operands_at(GATE_SPAWN_SITE) == [(A2, GATE_DESTINATION), (A1, TYPE35_TEMPLATE)], (
        f"the two `lea`s at {GATE_SPAWN_SITE:#x} are not the a2=destination / a1=template pair")
    assert GATE_DESTINATION == TABLE_DEFAULT + RECORD_BYTES, (
        "the gate's destination is not slot 1 of the default actor table")


def test_the_composition_the_gate_spells_fills_the_records_the_gate_names():
    """...and the differential run of it, entered with exactly those two registers. This is the
    composition case `player_reset_ground_state`'s ladder rows are for $107c: what every other
    `scene_copy_record_fields` row leaves unexercised is the CALL, and the call is a register
    convention."""
    what = "scene_copy_record_fields as player_pending_event_gate composes it"
    (_, destination), (_, template) = _image_operands_at(GATE_SPAWN_SITE)
    pokes = _copy_pokes(what, template)
    pokes[destination - RECORD_BYTES] = keyed_block(destination - RECORD_BYTES,
                                                    3 * RECORD_BYTES, case_salt(what) ^ 2)
    pokes = leaf.overlay(pokes, {RECORD_PTR_10420: SCENE.to_bytes(LONGWORD_BYTES, "big")})
    image = harness.make_image(pokes)

    expected = {}
    _put_long(expected, destination, _image_long(image, SCENE + SCENE_SPAWN_POSITION))
    for i in range(TEMPLATE_LONGWORDS):
        _put_long(expected, destination + (i + 1) * LONGWORD_BYTES,
                  _image_long(image, template + SPAWN_TEMPLATE_UNREAD + i * LONGWORD_BYTES))

    info = leaf.run("scene_copy_record_fields", _COPY_RECORD(template, destination),
                    merge_bands(expected), what,
                    regs={"a1": template, "a2": destination, "_pokes": pokes},
                    max_insns=_cap("scene_copy_record_fields"))
    _assert_writes(info, expected, what)


def test_1fa2_is_an_ARM_of_player_stage_transition_and_not_a_routine():
    """THE EXTENT CONFLICT batch 40 phase A registered, measured. ../names.txt used to give $1fa2 a
    routine of its own with a 186-byte body INSIDE `player_stage_transition`'s stated $1f54..$21e3;
    one of the two had to be wrong, and it is that one.

    Exactly ONE instruction in the whole image names $1fa2 — the `beq.w` at $1f62, twenty-two bytes
    into $1f54 itself — so the address is a continuation, not an entry. THREE halves are asserted,
    not two: the instruction census, the mode-shaped PC-relative sweep (a superset, so a negative
    proved with it covers the narrower one), and the DATA one — no aligned longword or word anywhere
    in the program holds the address either, which is what would make it a dispatch-table row like
    the sixty-two `actor_behavior_table` entries. An instruction census alone would not have seen
    that, and it is exactly how this tier's rows ARE reached."""
    assert (tuple(sorted(CONTROL_FLOW_TARGETS.get(STAGE_TRANSITION_ARM, [])))
            == (0x1f62,)), (
        f"{STAGE_TRANSITION_ARM:#x} is named by "
        f"{[hex(at) for at in CONTROL_FLOW_TARGETS.get(STAGE_TRANSITION_ARM, [])]}")
    assert STAGE_TRANSITION_ARM not in PC_RELATIVE_SOURCE_TARGETS
    image = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    for width in (WORD_BYTES, LONGWORD_BYTES):
        operand = STAGE_TRANSITION_ARM.to_bytes(width, "big")
        holders = [at for at in range(0, len(image) - width, WORD_BYTES)
                   if image[at:at + width] == operand]
        assert not holders, (
            f"{STAGE_TRANSITION_ARM:#x} is held as an aligned {width}-byte operand at "
            f"{[hex(at) for at in holders]}, so something may reach it by dereference")
    entry = leaf.entry_of("player_stage_transition")
    assert entry < 0x1f62 < STAGE_TRANSITION_ARM, (
        "the branch that names the arm is not inside player_stage_transition's own body")
    assert STAGE_TRANSITION_ARM < entry + BODY_SIZES["player_stage_transition"], (
        "the arm is not inside the body the pin covers")
