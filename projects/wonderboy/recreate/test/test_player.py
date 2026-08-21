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
import emu          # noqa: E402  (harness.py is what puts oracle/ on sys.path)
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
                  tst_b_abs_l, tst_b_d16, tst_w_abs_l, tst_w_abs_w, word,
                  # ...and the forms batch 41 phase A's $151a pin adds to this battery's needs
                  WORD_MASK, add_w_dn_dn, addq_w_abs_l, asr_w_imm_dn, bcc_abs, cmpi_b_dn,
                  cmpi_w_d16, lea_indexed, lsl_w_imm_dn, move_b_abs_l_dn, move_b_dn_abs_l,
                  move_w_ind_dn, subi_w_dn, subq_w_abs_l, subq_w_dn,
                  # ...and the seven this battery spelt itself until each reached its third copy
                  clr_b_ind, cmpi_b_ind, cmpi_w_dn, jmp_abs_l, move_b_ind_dn, move_l_dn_dn,
                  move_w_postinc_d16,
                  movea_l_an_an, mulu_w_dn_dn,
                  # ...and the five hoisted to leaf.py by batch 41 phase B's spawn-tree pin
                  addq_l_an, cmpi_b_abs_l, move_w_imm_d16,
                  # ...and the three batch 41 phase C's $b1a pin adds, plus the five its review
                  # HOISTED here from this file and four others (each was a third or fourth copy)
                  clr_b_abs_l, clr_w_abs_w, jsr_abs_l,
                  add_w_dn_ind, clr_l_abs_w, clr_l_dn, move_b_imm_dn, tst_w_d16)
from layout import wb

# The record's geometry, the register ordinals and the three BIT opcodes come from the battery that
# owns the actor table — a second copy of "what a record looks like" could disagree with src/actor.c
# while both stayed green. Same rule test_behavior.py follows.
from leaf import A0, A1, A2, A3, A5, A6, A7, D0, D1, D3, D6, D7                          # noqa: E402
from test_actor import (BCLR_IMM, BEQ_W, BGT_W, BLE_W, BLT_W, BMI_W, BNE_W, BPL_W,  # noqa: E402
                        BRA_W, BSET_IMM, BTST_IMM,
                        RECORD_BYTES, TABLE_DEFAULT, _sfx_bytes, bit_op_d16, jsr_d16_an)
# ...and the sound module's, from the battery that owns snd_play_song.
from test_sound import (PLAY_SONG_INSN_CAP, PLAY_SONG_MIXER, PLAY_SONG_SEEDED_BANDS,   # noqa: E402
                        PSG_REG_MIXER, STOP_INSN_CAP, STOP_WRITES, STUB_INSN_CAP,
                        STUB_STOP_OFFSET, STUB_TABLE_BASE, STUB_TRIGGER_OFFSET, model_play_song)


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


def _assert_writes(info, expected, what, extra=frozenset()):
    """The oracle's write set, stated EXACTLY — every case here can say what it wrote.

    ``extra`` is passed straight to `leaf.assert_written_is`: the addresses a COMPOSED case leaves to
    the battery that owns the callee. It lives here rather than in a second copy of the int/bytes
    normalisation, which is the one rule this whole battery's models are shaped by."""
    leaf.assert_written_is(info, {addr: bytes([value]) if isinstance(value, int) else value
                                  for addr, value in expected.items()}, what, extra=extra)


def _flatten(model):
    """An imported battery's `{address: bytes}` write-set model, as this file's `{address: byte}`.

    THREE cases had these two lines inline before batch 41 phase A added a fourth — the death arm's
    song, the boss arm's stop chain and the flute's song — and a fourth copy is where a divergence
    would start. It is not in leaf.py because the SHAPE is this battery's, not the kit's:
    `_assert_writes` is what wants one byte per key."""
    return {addr + index: value[index] for addr, value in model.items() for index in range(len(value))}


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


def cmpa_l_imm(reg, value):
    """`cmpa.l #imm,An` — "did the allocator hand back a record"."""
    # ALSO IN test_actor.py, test_blit.py, test_behavior.py, test_scene.py — fifth copy, queued
    # for leaf.py.
    return opcode(0xb1fc | (reg << 9)) + longword(value)



def subq_l_abs_l(amount, addr):
    """`subq.l #n,addr.l` — the write pointer rewound by one record."""
    return opcode(0x5189 | quick_field(amount) | 0x30) + longword(addr)


def sbcd_predec(destination, source):
    """`sbcd -(Ad),-(As)` — the memory-to-memory form, which is the one this game executes."""
    return opcode(0x8108 | (destination << 9) | source)



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


# --- $151a: the collision cell, the six special tiles and the eight scene triggers ------------------
# The constants are the header's (wonderboy.h's `$151a` block), so the pin and the reconstruction
# cannot disagree about one; only the four addresses no header names are local, each with the
# ../names.txt line that does name them.
FIELD_12 = wb("ACTOR_FIELD_12")
SND_ENGINE_ENABLED = wb("SND_ENGINE_ENABLED")
STAGE_TUNE_LATCH = wb("STAGE_TUNE_LATCH")
CELL_Y_BIAS = wb("PLAYER_CELL_Y_BIAS")
MAP_CELL_SHIFT = wb("MAP_CELL_SHIFT")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
COLLISION_MAP_DEFAULT = wb("COLLISION_MAP_DEFAULT")
COLLISION_MAP_CELLS = wb("COLLISION_MAP_CELLS")
# $1536's `lea $23498.l,a6` is the map's base PLUS its four header bytes, i.e. cell 0 itself — so an
# operand scan keyed on the map's own address does not see this routine at all.
COLLISION_MAP_CELL_0 = COLLISION_MAP_DEFAULT + COLLISION_MAP_CELLS

TILE_33 = wb("MAP_TILE_33")
TILE_34 = wb("MAP_TILE_34")
TILE_35 = wb("MAP_TILE_35")
TILE_36 = wb("MAP_TILE_36")
TILE_37 = wb("MAP_TILE_37")
TILE_38 = wb("MAP_TILE_38")
TILE_39 = wb("MAP_TILE_39")
TILE_33_FLAG_RAISED_BYTE = wb("TILE_33_FLAG_RAISED_BYTE")
TILE_34_SPEED = wb("PLAYER_TILE_34_SPEED")
TILE_34_SPAWN_TYPE = wb("PLAYER_TILE_34_SPAWN_TYPE")
TILE_HURT_COST = wb("PLAYER_TILE_HURT_COST")
TILE_37_X_STEP = wb("PLAYER_TILE_37_X_STEP")
PANEL_FRAME_DELAY = wb("PANEL_FRAME_DELAY")
PANEL_FRAME_DELAY_EVEN = wb("PANEL_FRAME_DELAY_EVEN")
DAMAGE_FLICKER_FRAMES = wb("ACTOR_DAMAGE_FLICKER_FRAMES")
DAMAGE_FOLLOWED_SFX = wb("ACTOR_DAMAGE_FOLLOWED_SFX")
DAMAGE_KNOCKBACK_SPEED = wb("ACTOR_DAMAGE_KNOCKBACK_SPEED")

TRIGGER_TABLE = wb("SCENE_TRIGGER_TABLE")
TRIGGER_CODE_FIRST = wb("SCENE_TRIGGER_CODE_FIRST")
TRIGGER_CODE_LAST = wb("SCENE_TRIGGER_CODE_LAST")
TRIGGER_RECORD_SHIFT = wb("SCENE_TRIGGER_RECORD_SHIFT")
TRIGGER_RECORD_BYTES = 1 << TRIGGER_RECORD_SHIFT
TRIGGER_KIND = wb("SCENE_TRIGGER_KIND")
KIND_SPAWN_1 = wb("SCENE_TRIGGER_KIND_SPAWN_1")
KIND_SPAWN_2 = wb("SCENE_TRIGGER_KIND_SPAWN_2")
KIND_MESSAGE = wb("SCENE_TRIGGER_KIND_MESSAGE")
KIND_BOSS_DEFEAT = wb("SCENE_TRIGGER_KIND_BOSS_DEFEAT")
KIND_SPAWN_5 = wb("SCENE_TRIGGER_KIND_SPAWN_5")
KIND_SPAWN_6 = wb("SCENE_TRIGGER_KIND_SPAWN_6")
KIND_ALIGN = wb("SCENE_TRIGGER_KIND_ALIGN")
KIND_TUNE = wb("SCENE_TRIGGER_KIND_TUNE")
TRIGGER_X = wb("SCENE_TRIGGER_X")
TRIGGER_SPAWN_Y = wb("SCENE_TRIGGER_SPAWN_Y")
TRIGGER_SPAWN_TYPE = wb("SCENE_TRIGGER_SPAWN_TYPE")
TRIGGER_SPAWN_FIELD = wb("SCENE_TRIGGER_SPAWN_FIELD")
TRIGGER_VISITS = wb("SCENE_TRIGGER_VISITS")
TRIGGER_SPAWN_SLOT = wb("SCENE_TRIGGER_SPAWN_SLOT")
TRIGGER_SPRITE_1 = wb("SCENE_TRIGGER_SPRITE_1")
TRIGGER_SPRITE_2 = wb("SCENE_TRIGGER_SPRITE_2")
TRIGGER_SPRITE_5 = wb("SCENE_TRIGGER_SPRITE_5")
TRIGGER_SPRITE_6 = wb("SCENE_TRIGGER_SPRITE_6")
TRIGGER_SFX_1 = wb("SCENE_TRIGGER_SFX_1")
TRIGGER_SFX_2 = wb("SCENE_TRIGGER_SFX_2")
TRIGGER_SPAWN_1_FIELD_10 = wb("SCENE_TRIGGER_SPAWN_1_FIELD_10")
TRIGGER_SPAWN_SPEED = wb("SCENE_TRIGGER_SPAWN_SPEED")
TRIGGER_MESSAGE = wb("SCENE_TRIGGER_MESSAGE")
TEXT_REQUEST_PRIMED = wb("TEXT_REQUEST_PRIMED")
TRIGGER_BOSS_KEY = wb("SCENE_TRIGGER_BOSS_KEY")
TRIGGER_BOSS_SFX = wb("SCENE_TRIGGER_BOSS_SFX")
TRIGGER_ALIGN_SUBKIND = wb("SCENE_TRIGGER_ALIGN_SUBKIND")
TRIGGER_ALIGN_SECOND = wb("SCENE_TRIGGER_ALIGN_SECOND")
TRIGGER_ALIGN_REACH = wb("SCENE_TRIGGER_ALIGN_REACH")
HUD_SLOT_BBC4 = wb("HUD_SLOT_BBC4")
HUD_SLOT_BBC4_ARMED = wb("HUD_SLOT_BBC4_ARMED")
HUD_SLOT_BBC4_SPENT = wb("HUD_SLOT_BBC4_SPENT")
HUD_SLOT_BBC8 = wb("HUD_SLOT_BBC8")
HUD_SLOT_BBC8_FLUTE = wb("HUD_SLOT_BBC8_FLUTE")
LEVEL_SEQ_INDEX = wb("LEVEL_SEQ_INDEX")
LEVEL_SEQ_DOOR_A = wb("LEVEL_SEQ_DOOR_A")
LEVEL_SEQ_DOOR_B = wb("LEVEL_SEQ_DOOR_B")
LEVEL_SEQ_DOOR_STEP = wb("LEVEL_SEQ_DOOR_STEP")
FLUTE_PLAYED = wb("SCENE_FLUTE_PLAYED")
FLUTE_PLAYED_SET = wb("SCENE_FLUTE_PLAYED_SET")
STAGE_ADVANCE_REQUEST = wb("STAGE_ADVANCE_REQUEST")
STAGE_ADVANCE_REQUEST_SET = wb("STAGE_ADVANCE_REQUEST_SET")
ALIGN_REQUEST_B14 = wb("SCENE_ALIGN_REQUEST_B14")
TRIGGER_FLAG_SET = wb("SCENE_TRIGGER_FLAG_SET")
TRIGGER_TUNE_MAX_Y = wb("SCENE_TRIGGER_TUNE_MAX_Y")
MESSAGE_PLAYED_FLUTE = wb("TEXT_MESSAGE_PLAYED_FLUTE")
MESSAGE_NICE_VIEW = wb("TEXT_MESSAGE_NICE_VIEW")
TRIGGER_FLUTE_SONG = wb("SCENE_TRIGGER_FLUTE_SONG")
KEY_LAST_SCANCODE = wb("KEY_LAST_SCANCODE")
STAGE_ANIM_REQUEST_B0E = wb("STAGE_ANIM_REQUEST_B0E")
SCENE_MARKER_CELL_PTR = wb("SCENE_MARKER_CELL_PTR")
RECORD_PTR_10424 = wb("RECORD_PTR_10424")
FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
# NAMED OFF THE `COLLIDE_` PREFIX ON PURPOSE: the $b1a section below already binds
# COLLIDE_UNWIND to the two INSTRUCTIONS of the pop, which is a different fact about the
# same arm, and a battery holding both under one name reports the wrong one.
EXIT_RETURN = wb("PLAYER_COLLIDE_RETURN")
EXIT_SOUND_WAIT = wb("PLAYER_COLLIDE_SOUND_WAIT")
EXIT_UNWIND = wb("PLAYER_COLLIDE_UNWIND")

# The three addresses inside the ORIGINAL that no header names, because the reconstruction reaches
# none of them: two branch targets and the routine's own data words.
KNOCK_BACK_TAIL = leaf.entry_of("actor_knock_back_and_launch")   # $6ade, the `bra.w` at $15e8
UNWIND_TARGET = leaf.entry_of("stage_sequence_advance")          # $e5ba, after the triple pop
# THE CHECKPOINT IS THE `jmp` AND THE WITNESS IS THE `lea`, in that order and not the other way
# round. `emu.run` stops BEFORE marking the checkpoint's own PC, so a checkpoint at the `lea` can
# only be witnessed by something above it — and the `beq.w` at $161c EXECUTES ON EVERY PATH that
# reaches the tile-$39 test, taken or not, so it witnesses nothing. The `lea 12(a7),a7` is on the
# taken arm alone; stopping one instruction later is what makes it available as the witness, and it
# writes no memory (a7 is a register), so the image compared is still the one at the transfer.
UNWIND_SITE = 0x1626             # `jmp $e5ba.l` — where the checkpointed run stops
UNWIND_TAKEN_AT = 0x1622         # ...and the `lea 12(a7),a7` that must have executed to get there
SOUND_WAIT_SITE = 0x1932         # `tst.b 378(a5)` — WB_PLAYER_COLLIDE_SOUND_WAIT's checkpoint
SOUND_WAIT_TAKEN_AT = 0x192a     # ...and the `jsr (a5)` that starts the song the spin waits on
UNWIND_STACK_BYTES = 12          # `lea 12(a7),a7` — THREE return addresses
DESCRIPTOR_SUBKIND_FROM_A1 = TRIGGER_ALIGN_SUBKIND - WORD_BYTES  # a1 is past the kind word already


# --- the encodings this pin needs and neither leaf.py nor the block above had ----------------------
# A `move` names its DESTINATION at bits 11-9 (register) and 8-6 (mode) and its SOURCE at 5-3 (mode)
# and 2-0 (register) — the same two fields in the two orders. That one rule is behind four of the
# encoders here, so it is spelt once rather than folded into each of them. (It was seven until
# `move_l_dn_dn`, `movea_l_an_an`, `move_b_ind_dn` and `move_w_postinc_d16` reached their third copy
# and moved to leaf.py, taking the byte and d16 spellings of the rule with them.)
_MOVE_W, _MOVE_L = 0x3000, 0x2000
_EA_DN, _EA_AN, _EA_IND, _EA_POSTINC = 0, 1, 2, 3
_EA_OTHER, _EA_ABS_L = 7, 1


def _move_source(mode, reg):
    """A `move`'s SOURCE effective address, in bits 5-0."""
    return (mode << 3) | reg


def _move_destination(mode, reg):
    """...and its DESTINATION, in bits 11-6, which hold the same two fields in the other order."""
    return (reg << 9) | (mode << 6)


def move_l_an_abs_l(reg, addr):
    """`move.l An,<abs>.l` — a whole POINTER published to a global ($163a, $1964)."""
    # ALSO IN test_stage.py, as the bare opcode word `MOVE_L_AN_ABS_L` — second copy, which the rule
    # allows. A constant spelling an opcode IS a copy of the encoder; goes to leaf.py on its third.
    return (opcode(_MOVE_L | _move_destination(_EA_OTHER, _EA_ABS_L) | _move_source(_EA_AN, reg))
            + longword(addr))


def move_l_abs_l_abs_l(source, destination):
    """`move.l <abs>.l,<abs>.l` — the descriptor pointer copied to its neighbour. SIX arms make it
    ($1684, $170e, $1772, $17a4, $17f4, $18f6) and a whole-image sweep for the encoding finds
    exactly those six, all inside this routine."""
    return (opcode(_MOVE_L | _move_destination(_EA_OTHER, _EA_ABS_L)
                   | _move_source(_EA_OTHER, _EA_ABS_L))
            + longword(source) + longword(destination))


def move_w_dn_ind(reg, base):
    """`move.w Dn,(An)` — $188e, the door writing the player's snapped x back."""
    return opcode(_MOVE_W | _move_destination(_EA_IND, base) | _move_source(_EA_DN, reg))
    # ALSO IN test_map.py — second copy, which the rule allows.


def move_w_postinc_ind(source, destination):
    """`move.w (As)+,(Ad)` — the first of the four words a spawning kind copies."""
    return opcode(_MOVE_W | _move_destination(_EA_IND, destination)
                  | _move_source(_EA_POSTINC, source))



def cmpi_b_abs_w(value, addr):
    """...and the SHORT form, which is how the boss arm reads the scancode byte at $879."""
    return opcode(0x0c38) + word(value & 0xff) + word(addr)


def cmp_w_ind_dn(reg, base):
    """`cmp.w (An),Dn` — the SIGNED compare of the followed actor's x against the door's window."""
    return opcode(0xb050 | (reg << 9) | base)
    # ALSO IN test_behavior.py — second copy, which the rule allows.


def andi_w_abs_l(value, addr):
    """`andi.w #imm,<abs>.l` — the panel delay masked EVEN in memory, right after its decrement."""
    return opcode(0x0279) + word(value) + longword(addr)
    # ALSO IN test_scroll.py — second copy, which the rule allows.


def tst_w_ind(base):
    """`tst.w (An)` — "is the scene's own actor slot free", which is a SIGN test of its x."""
    return opcode(0x4a50 | base)
    # ALSO IN test_behavior.py — second copy, which the rule allows.


def clr_b_abs_w(addr):
    """`clr.b <abs>.w` — the tile flag's HIGH BYTE lowered, against the `st` that raises it."""
    return opcode(0x4238) + word(addr)


def st_abs_w(addr):
    """`st <abs>.w` — Scc's true byte into a destination below $8000, leaf.st_abs_l's short twin."""
    return opcode(0x50f8) + word(addr)


def subq_w_ind(amount, base):
    """`subq.w #n,(An)` — leaf.addq_w_ind's mirror, and $15fe's nudge."""
    return opcode(0x5150 | quick_field(amount) | base)
    # ALSO IN test_behavior.py — second copy, which the rule allows (and which now shares this body).


def subq_w_postinc(amount, base):
    """`subq.w #n,(An)+` — one visit spent AND the cursor stepped, in one instruction."""
    return opcode(0x5158 | quick_field(amount) | base)


def subq_l_dn(amount, reg):
    """`subq.l #n,Dn` — $162c's bias, a LONGWORD subtract where every other one here is a word."""
    return opcode(0x5180 | quick_field(amount) | reg)


def _trigger_slot_pieces(label, sfx):
    """The head kinds 1, 2 and 5 share: republish the descriptor pointer, refuse the scene's own
    actor slot unless its x is negative, and ask the sound module for the arrival effect."""
    return [
        move_l_abs_l_abs_l(RECORD_PTR_10420, RECORD_PTR_10424),
        lea_abs_l(A2, TRIGGER_SPAWN_SLOT),
        tst_w_ind(A2),
        bcc(BMI_W, f"{label}-free"),
        RTS,
        lab(f"{label}-free"),
        lea_abs_l(A5, STUB_TABLE_BASE),
        move_w_imm_dn(D0, sfx),
        clr_w_dn(D1),
        jsr_d16_an(A5, STUB_TRIGGER_OFFSET),
    ]


def _trigger_copy_pieces():
    """The four words every spawning kind copies out of the descriptor into the slot it took."""
    return [
        move_w_postinc_ind(A1, A2),
        move_w_postinc_d16(A1, A2, ACTOR_Y),
        move_w_postinc_d16(A1, A2, ACTOR_TYPE),
        move_w_postinc_d16(A1, A2, FIELD_12),
    ]


def _trigger_visit_pieces(label):
    """...and the tail all four share: one visit spent, and the cell consumed on the last one."""
    return [
        subq_w_postinc(1, A1),
        bcc(BNE_W, f"{label}-out"),
        clr_b_ind(A6),
        lab(f"{label}-out"),
        RTS,
    ]


def _run_map_cell_pieces():
    """$151a — one collision cell, six special tiles and eight scene kinds. 1,170 bytes, the largest
    single routine in the image, and the last of `actor_behavior_type01_player`'s nine calls to be
    reconstructed bar the gate."""
    return [
        # $151a — the record's x,y turned into ONE collision-map cell
        moveq(0, D0),
        move_l_dn_dn(D1, D0),
        move_w_ind_dn(D0, A0, ACTOR_X),
        move_w_ind_dn(D1, A0, ACTOR_Y),
        subi_w_dn(D1, CELL_Y_BIAS),
        asr_w_imm_dn(MAP_CELL_SHIFT, D0),
        asr_w_imm_dn(MAP_CELL_SHIFT, D1),
        move_w_abs_l_dn(D3, MAP_ROW_STRIDE),
        mulu_w_dn_dn(D3, D1),
        add_w_dn_dn(D3, D0),
        lea_abs_l(A6, COLLISION_MAP_CELL_0),
        lea_indexed(A6, D3),
        cmpi_b_ind(A6, TRIGGER_CODE_FIRST),
        bcc(BLT_W, "clear-tile-flag"),
        moveq(0, D0),
        move_b_ind_dn(D0, A6),
        cmp_b_imm_dn(D0, TRIGGER_CODE_LAST),
        bcc(BLE_W, "trigger"),
        # $1554 — tile $33 raises the flag the ladder tier reads
        cmpi_b_dn(D0, TILE_33),
        bcc(BNE_W, "tile-34"),
        st_abs_w(TILE_33_FLAG),
        RTS,
        # $1562 — tile $34: a SUPPORTED record is launched, and a record is spawned on its x,y
        lab("tile-34"),
        cmpi_b_dn(D0, TILE_34),
        bcc(BNE_W, "tile-35"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "tile-34-launch"),
        RTS,
        lab("tile-34-launch"),
        move_b_imm_d16(A0, TILE_34_SPEED, SPEED),
        bit_op_d16(BSET_IMM, MOVING_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A0, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bsr("actor_alloc_slot_high"),
        cmpa_l_imm(A1, ALLOC_NONE),
        bcc(BEQ_W, "shared-rts"),
        move_l_ind_ind(A0, A1),
        move_w_imm_d16(A1, TILE_34_SPAWN_TYPE, ACTOR_TYPE),
        RTS,
        # $15a6 — tiles $35 and $36 are ONE body reached by two paths
        lab("tile-35"),
        cmpi_b_dn(D0, TILE_35),
        bcc(BNE_W, "tile-36"),
        bcc(BRA_W, "hurt"),
        lab("tile-36"),
        cmpi_b_dn(D0, TILE_36),
        bcc(BNE_W, "tile-37"),
        lab("hurt"),
        bit_op_d16(BTST_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "tile-37"),
        bit_op_d16(BSET_IMM, FLAGS2_BIT_0, A0, FLAGS2),
        bit_op_d16(BSET_IMM, FLICKER_BIT, A0, ACTOR_FLAGS),
        move_b_imm_d16(A0, DAMAGE_FLICKER_FRAMES, FLICKER_COUNTDOWN),
        subq_w_abs_l(TILE_HURT_COST, HUD_METER_VALUE),
        bcc(BPL_W, "meter-floored"),
        clr_w_abs_l(HUD_METER_VALUE),
        lab("meter-floored"),
        movea_l_an_an(A1, A0),
        bcc_abs(BRA_W, KNOCK_BACK_TAIL),
        # $15ec — tile $37 nudges a SUPPORTED record back
        lab("tile-37"),
        cmpi_b_dn(D0, TILE_37),
        bcc(BNE_W, "tile-38"),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BEQ_W, "shared-rts"),
        subq_w_ind(TILE_37_X_STEP, A0),
        lab("shared-rts"),
        RTS,
        # $1602 — tile $38 steps the panel delay and FALLS THROUGH into tile $39's own test
        lab("tile-38"),
        cmpi_b_dn(D0, TILE_38),
        bcc(BNE_W, "tile-39"),
        subq_w_abs_l(1, PANEL_FRAME_DELAY),
        andi_w_abs_l(PANEL_FRAME_DELAY_EVEN, PANEL_FRAME_DELAY),
        # $1618 — tile $39 leaves through a TRIPLE POP: this routine, its caller and its caller's
        lab("tile-39"),
        cmpi_b_dn(D0, TILE_39),
        bcc(BEQ_W, "unwind"),
        RTS,
        lab("unwind"),
        lea_d16(A7, UNWIND_STACK_BYTES),
        jmp_abs_l(UNWIND_TARGET),
        # $162c — a cell of 3..$22 names a 32-byte SCENE DESCRIPTOR, dispatched on its own kind word
        lab("trigger"),
        subq_l_dn(TRIGGER_CODE_FIRST, D0),
        lsl_w_imm_dn(TRIGGER_RECORD_SHIFT, D0),
        lea_abs_l(A1, TRIGGER_TABLE),
        lea_indexed(A1, D0),
        move_l_an_abs_l(A1, RECORD_PTR_10420),
        move_w_postinc_dn(D0, A1),
        cmpi_w_dn(D0, KIND_SPAWN_1),
        bcc(BEQ_W, "kind-1"),
        cmpi_w_dn(D0, KIND_SPAWN_2),
        bcc(BEQ_W, "kind-2"),
        cmpi_w_dn(D0, KIND_MESSAGE),
        bcc(BEQ_W, "kind-3"),
        cmpi_w_dn(D0, KIND_BOSS_DEFEAT),
        bcc(BEQ_W, "kind-4"),
        cmpi_w_dn(D0, KIND_SPAWN_5),
        bcc(BEQ_W, "kind-5"),
        cmpi_w_dn(D0, KIND_SPAWN_6),
        bcc(BEQ_W, "kind-6"),
        cmpi_w_dn(D0, KIND_ALIGN),
        bcc(BEQ_W, "kind-7"),
        cmp_w_imm_dn(D0, KIND_TUNE),
        bcc(BEQ_W, "kind-8"),
        RTS,
        # $1684 — kind 1, the only arm that reads the FOLLOWED record, and it copies its side
        # bit INVERTED
        lab("kind-1"),
    ] + _trigger_slot_pieces("kind-1", TRIGGER_SFX_1) + _trigger_copy_pieces() + [
        lea_abs_l(A5, FOLLOWED_DEFAULT),
        bit_op_d16(BTST_IMM, SIDE_BIT, A5, ACTOR_FLAGS),
        bcc(BNE_W, "kind-1-face-left"),
        bit_op_d16(BSET_IMM, SIDE_BIT, A2, ACTOR_FLAGS),
        bcc(BRA_W, "kind-1-flags"),
        lab("kind-1-face-left"),
        bit_op_d16(BCLR_IMM, SIDE_BIT, A2, ACTOR_FLAGS),
        lab("kind-1-flags"),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A2, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, MOVING_BIT, A2, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A2, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A2, ACTOR_FLAGS),
        move_b_imm_d16(A2, TRIGGER_SPAWN_1_FIELD_10, FIELD_10),
        move_b_imm_d16(A2, TRIGGER_SPAWN_SPEED, SPEED),
        move_w_imm_d16(A2, TRIGGER_SPRITE_1, ACTOR_SPRITE),
    ] + _trigger_visit_pieces("kind-1") + [
        # $170e — kind 2: kind 1 without the side bit and without WB_ACTOR_FIELD_10
        lab("kind-2"),
    ] + _trigger_slot_pieces("kind-2", TRIGGER_SFX_2) + _trigger_copy_pieces() + [
        bit_op_d16(BSET_IMM, MOVING_BIT, A2, ACTOR_FLAGS),
        bit_op_d16(BSET_IMM, LAUNCHED_BIT, A2, ACTOR_FLAGS),
        bit_op_d16(BCLR_IMM, SUPPORTED_BIT, A2, ACTOR_FLAGS),
        move_b_imm_d16(A2, TRIGGER_SPAWN_SPEED, SPEED),
        move_w_imm_d16(A2, TRIGGER_SPRITE_2, ACTOR_SPRITE),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A2, ACTOR_FLAGS),
    ] + _trigger_visit_pieces("kind-2") + [
        # $1772 — kind 3 posts a MESSAGE and takes no actor slot at all
        lab("kind-3"),
        move_l_abs_l_abs_l(RECORD_PTR_10420, RECORD_PTR_10424),
        moveq(0, D0),
        move_b_imm_abs_l(TEXT_REQUEST_PRIMED, TEXT_REQUEST),
        move_w_postinc_dn(D0, A1),
        bcc(BEQ_W, "kind-3-out"),
        move_b_dn_abs_l(D0, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        lab("kind-3-out"),
        clr_b_ind(A6),
        RTS,
        # $179e — the cell below WB_SCENE_TRIGGER_CODE_FIRST, where the tile flag comes back down
        lab("clear-tile-flag"),
        clr_b_abs_w(TILE_33_FLAG),
        RTS,
        # $17a4 — kind 5, kind 2's quiet twin, which also clears the PLAYER's own 30(a0)
        lab("kind-5"),
    ] + _trigger_slot_pieces("kind-5", TRIGGER_SFX_2) + [
        clr_b_d16(A0, FIELD_30),
    ] + _trigger_copy_pieces() + [
        move_w_imm_d16(A2, TRIGGER_SPRITE_5, ACTOR_SPRITE),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A2, ACTOR_FLAGS),
    ] + _trigger_visit_pieces("kind-5") + [
        # $17f4 — kind 6, the same again with NO effect at all
        lab("kind-6"),
        move_l_abs_l_abs_l(RECORD_PTR_10420, RECORD_PTR_10424),
        lea_abs_l(A2, TRIGGER_SPAWN_SLOT),
        tst_w_ind(A2),
        bcc(BMI_W, "kind-6-free"),
        RTS,
        lab("kind-6-free"),
    ] + _trigger_copy_pieces() + [
        move_w_imm_d16(A2, TRIGGER_SPRITE_6, ACTOR_SPRITE),
        bit_op_d16(BCLR_IMM, FLICKER_BIT, A2, ACTOR_FLAGS),
    ] + _trigger_visit_pieces("kind-6") + [
        # $1830 — kind 7, the HIDDEN DOOR. Two gates in a lattice, with a `bra.s` back into the
        # other order's first question
        lab("kind-7"),
        cmpi_b_abs_l(HUD_SLOT_BBC4_ARMED, HUD_SLOT_BBC4),
        bcc(BEQ_W, "kind-7-armed"),
        lab("kind-7-flute"),
        cmpi_w_abs_l(FLUTE_PLAYED_SET, FLUTE_PLAYED),
        bcc(BEQ_W, "kind-7-second"),
        RTS,
        lab("kind-7-second"),
        cmpi_w_d16(A1, TRIGGER_ALIGN_SECOND, DESCRIPTOR_SUBKIND_FROM_A1),
        bcc(BEQ_W, "kind-7-reach"),
        RTS,
        lab("kind-7-armed"),
        cmpi_w_d16(A1, TRIGGER_ALIGN_SECOND, DESCRIPTOR_SUBKIND_FROM_A1),
        bcc(BNE_W, "kind-7-reach"),
        bra_s("kind-7-flute"),
        lab("kind-7-reach"),
        lea_abs_l(A2, FOLLOWED_DEFAULT),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A2, ACTOR_FLAGS),
        bcc(BEQ_W, "kind-7-out"),
        movea_l_abs_l(A3, RECORD_PTR_10420),
        move_w_ind_dn(D0, A3, TRIGGER_X),
        subq_w_dn(TRIGGER_ALIGN_REACH, D0),
        cmp_w_ind_dn(D0, A2),
        bcc(BGT_W, "kind-7-out"),
        addq_w_dn(2 * TRIGGER_ALIGN_REACH, D0),
        cmp_w_ind_dn(D0, A2),
        bcc(BLT_W, "kind-7-out"),
        subq_w_dn(TRIGGER_ALIGN_REACH, D0),
        move_w_dn_ind(D0, A0),
        move_w_imm_abs_l(0, FLUTE_PLAYED),
        move_w_imm_abs_l(HUD_SLOT_BBC4_SPENT, HUD_SLOT_BBC4),
        move_w_imm_abs_w(TRIGGER_FLAG_SET, SCROLL_FOLLOW_FROZEN),
        move_w_imm_abs_l(TRIGGER_FLAG_SET, PANEL_FRAME_HOLD),
        move_w_imm_abs_w(TRIGGER_FLAG_SET, ALIGN_REQUEST_B14),
        cmpi_w_abs_l(LEVEL_SEQ_DOOR_A, LEVEL_SEQ_INDEX),
        bcc(BEQ_W, "kind-7-advance"),
        cmpi_w_abs_l(LEVEL_SEQ_DOOR_B, LEVEL_SEQ_INDEX),
        bcc(BEQ_W, "kind-7-advance"),
        lab("kind-7-out"),
        RTS,
        lab("kind-7-advance"),
        cmpi_w_d16(A1, TRIGGER_ALIGN_SECOND, DESCRIPTOR_SUBKIND_FROM_A1),
        bcc(BEQ_W, "kind-7-request"),
        addq_w_abs_l(LEVEL_SEQ_DOOR_STEP, LEVEL_SEQ_INDEX),
        RTS,
        lab("kind-7-request"),
        move_w_imm_abs_l(STAGE_ADVANCE_REQUEST_SET, STAGE_ADVANCE_REQUEST),
        RTS,
        # $18ea — kind 8: the FLUTE, or the view. Its flute arm ends in the busy-wait at $1932
        lab("kind-8"),
        cmpi_w_d16(A0, TRIGGER_TUNE_MAX_Y, ACTOR_Y),
        bcc(BLT_W, "kind-8-body"),
        RTS,
        lab("kind-8-body"),
        move_l_abs_l_abs_l(RECORD_PTR_10420, RECORD_PTR_10424),
        clr_b_ind(A6),
        cmpi_b_abs_l(HUD_SLOT_BBC8_FLUTE, HUD_SLOT_BBC8),
        bcc(BNE_W, "kind-8-view"),
        move_b_imm_abs_l(MESSAGE_PLAYED_FLUTE, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        lea_abs_l(A5, STUB_TABLE_BASE),
        move_w_imm_dn(D0, TRIGGER_FLUTE_SONG),
        clr_w_dn(D1),
        jsr_ind(A5),
        lea_abs_l(A5, STUB_TABLE_BASE),
        lab("kind-8-wait"),
        tst_b_d16(A5, SND_ENGINE_ENABLED - STUB_TABLE_BASE),
        bcc_s(BNE_W, "kind-8-wait"),
        # ...and everything below the spin is unreached BY ANY CASE: the `jsr` above raises that very
        # byte as snd_play_song's LAST write, so no seed enters the spin with it clear.
        # src/player.c ports none of these SIX. (Since batch 42 phase A a declared store CAN clear
        # the byte mid-run — the kit's Phase 8 — so they are reachable and their port is queued.)
        move_w_imm_abs_l(FLUTE_PLAYED_SET, FLUTE_PLAYED),
        clr_w_dn(D1),
        moveq(0, D0),
        move_b_abs_l_dn(D0, STAGE_TUNE_LATCH),
        jsr_ind(A5),
        RTS,
        lab("kind-8-view"),
        move_b_imm_abs_l(MESSAGE_NICE_VIEW, TEXT_REQUEST),
        move_w_imm_abs_l(TEXT_LIFETIME_DEFAULT, TEXT_LIFETIME_REQUEST),
        RTS,
        # $1960 — DATA, inside the body: flute_played_latch and stage_advance_request, both zero
        word(0) + word(0),
        # $1964 — kind 4, the boss defeat, which the space bar arms
        lab("kind-4"),
        move_l_an_abs_l(A6, SCENE_MARKER_CELL_PTR),
        bit_op_d16(BTST_IMM, SUPPORTED_BIT, A0, ACTOR_FLAGS),
        bcc(BNE_W, "kind-4-supported"),
        RTS,
        lab("kind-4-supported"),
        cmpi_b_abs_w(TRIGGER_BOSS_KEY, KEY_LAST_SCANCODE),
        bcc(BEQ_W, "kind-4-fire"),
        RTS,
        lab("kind-4-fire"),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_STOP_OFFSET),
        move_w_imm_dn(D0, TRIGGER_BOSS_SFX),
        clr_w_dn(D1),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        move_w_imm_abs_w(TRIGGER_FLAG_SET, STATE_FLAG_A34),
        move_w_imm_abs_l(TRIGGER_FLAG_SET, PANEL_FRAME_HOLD),
        move_w_imm_abs_w(TRIGGER_FLAG_SET, STAGE_ANIM_REQUEST_B0E),
        RTS,
    ]


# --- $b1a: the pending-event gate's own constants and forms (batch 41 phase C) ----------------------
SPAWN_GATE_SLOT = wb("SCENE_SPAWN_GATE_SLOT")
ACTOR_FREE_MARKER = wb("ACTOR_FREE_MARKER")
EVENT_ANIM_DONE_B12 = wb("EVENT_ANIM_DONE_B12")
SCROLL_FOLLOW_Y = wb("SCROLL_FOLLOW_Y")
STATE_FLAG_SET = wb("STATE_FLAG_SET")
LIVES = wb("LIVES")
TEXT_BOX_ACTIVE = wb("TEXT_BOX_ACTIVE")
JOY1_STATE = wb("JOY1_STATE")
TYPE30_DRIFT = wb("ACTOR_TYPE30_DRIFT")
TYPE30_DRIFT_STRIDE = wb("ACTOR_TYPE30_DRIFT_STRIDE")
TYPE30_DRIFT_MASK = wb("ACTOR_TYPE30_DRIFT_MASK")

GATE_FLAG_SET = wb("EVENT_GATE_FLAG_SET")
EVENT_SPAWN_SFX = wb("EVENT_SPAWN_SFX")
DEATH_MESSAGE_POSTED_B0A = wb("DEATH_MESSAGE_POSTED_B0A")
DEATH_BOX_EXPIRED_B0C = wb("DEATH_BOX_EXPIRED_B0C")
DEATH_ASCENT_TOP_Y = wb("DEATH_ASCENT_TOP_Y")
DEATH_ASCENT_RISE = wb("DEATH_ASCENT_RISE")
DEATH_DRIFT_CURSOR = wb("DEATH_DRIFT_CURSOR")
DEATH_MESSAGE_LIFETIME = wb("DEATH_MESSAGE_LIFETIME")
LIFE_RESTART_ENTRY_C26 = wb("LIFE_RESTART_ENTRY_C26")
EVENT_FINISHED_E1BE = wb("EVENT_FINISHED_E1BE")
EVENT_PAIR_POSITION = wb("EVENT_PAIR_POSITION")
EVENT_PAIR_SPRITE_INERT = wb("EVENT_PAIR_SPRITE_INERT")
EVENT_PAIR_TYPE_RISER = wb("EVENT_PAIR_TYPE_RISER")
EVENT_PAIR_SPRITE_RISER = wb("EVENT_PAIR_SPRITE_RISER")
EVENT_PAIR_TYPE_ANIMATOR = wb("EVENT_PAIR_TYPE_ANIMATOR")
EVENT_PAIR_SPRITE_ANIMATOR = wb("EVENT_PAIR_SPRITE_ANIMATOR")
MESSAGE_GAME_OVER = wb("TEXT_MESSAGE_GAME_OVER")
MESSAGE_CONTINUE = wb("TEXT_MESSAGE_CONTINUE")

# The three transfers this routine ends on, keyed on the instruction the report stands for.
GATE_DATADISK_TARGET = leaf.entry_of("show_data_disk_prompt")
UNWIND_ONE_BYTES = LONGWORD_BYTES  # `lea 4(a7),a7` — ONE return address, where $1622 discards three
# The restart unwind and the triple pop land on the SAME routine, which is why the second one is
# spelt as UNWIND_TARGET above rather than as an address of its own.

# NOT header constants, because the reconstruction never spells them: both are DATA WORDS INSIDE the
# body, which is why a linear sweep of this routine desyncs twice. The `word()`s in the pin below are
# what claims their shipped values.
LIVES_SHIPPED = 3                  # $be2, and WB_LIVES_ON_RESTART is what puts it back
LIFE_RESTART_ENTRY_SHIPPED = 0     # $c26


def move_b_abs_w_dn(reg, addr):
    """`move.b <abs>.w,Dn` — `move_b_abs_l_dn`'s short form, for the joystick byte at $877."""
    return opcode(0x1038 | (reg << 9)) + word(addr)


def subq_w_abs_w(amount, addr):
    """`subq.w #n,<abs>.w` — `leaf.subq_w_abs_l`'s short form, for WB_LIVES below $8000."""
    return opcode(0x5178 | quick_field(amount)) + word(addr)


def move_l_d16_ind(source, source_displacement, destination):
    """`move.l d16(As),(Ad)` — the descriptor's position longword straight into a record's x,y.
    SOURCE PAIR FIRST, as `leaf.move_w_d16_d16` orders its four."""
    return opcode(0x2000 | (destination << 9) | (2 << 6) | (5 << 3) | source) + word(
        source_displacement)


def _pending_event_gate_pieces():
    """$b1a..$d27, 526 bytes. THE LISTING IS NOT THE SOURCE for this one: `../out/wonderboy_dis.txt`
    runs out of phase across the data word at $b18 and again at $be2 and $c26, both of which are
    DATA INSIDE THE BODY, so every instruction below was decoded from the raw image bytes instead.
    That is the whole reason this routine was never listing-readable.

    FOUR BYTES OF IT ARE UNREACHABLE — the `clr.w d7 / rts` at $bba, which no instruction in the
    image names (the case below asserts that). It is spelt here because the pin covers the BODY, not
    the reachable part of it, exactly as $1f34's dead `rts` is counted in the partition.
    """
    return [
        # $b1a — the three flags, in the order WB_STAGE_RESET_BLOCK holds them
        tst_w_abs_w(STAGE_RESET_BLOCK),
        bcc(BNE_W, "death"),
        tst_w_abs_w(STAGE_ANIM_REQUEST_B0E),
        bcc(BNE_W, "stage-anim"),
        tst_w_abs_w(ALIGN_REQUEST_B14),
        bcc(BNE_W, "scene-align"),
        clr_l_dn(D7),
        RTS,
        # $b36 — the DEATH arm: rise until the camera tops out, then post the message once
        lab("death"),
        tst_w_abs_w(DEATH_MESSAGE_POSTED_B0A),
        bcc(BNE_W, "prompt"),
        cmpi_w_abs_l(DEATH_ASCENT_TOP_Y, SCROLL_FOLLOW_Y),
        bcc(BNE_W, "rise"),
        move_b_imm_dn(D0, MESSAGE_GAME_OVER),
        tst_w_abs_l(LIVES),
        bcc(BEQ_W, "post"),
        move_b_imm_dn(D0, MESSAGE_CONTINUE),
        lab("post"),
        move_w_imm_abs_w(STATE_FLAG_SET, STATE_FLAG_A34),
        move_w_imm_abs_w(GATE_FLAG_SET, DEATH_MESSAGE_POSTED_B0A),
        move_b_dn_abs_l(D0, TEXT_REQUEST),
        move_w_imm_abs_l(DEATH_MESSAGE_LIFETIME, TEXT_LIFETIME_REQUEST),
        bcc(BRA_W, "tail"),
        # $b7a — a pixel up and one step of WB_ACTOR_TYPE30_DRIFT, then the camera tested AGAIN
        lab("rise"),
        subq_w_d16(DEATH_ASCENT_RISE, A0, ACTOR_Y),
        move_w_abs_l_dn(D0, DEATH_DRIFT_CURSOR),
        lea_abs_l(A1, TYPE30_DRIFT),
        lea_indexed(A1, D0),
        move_w_ind_dn(D1, A1),
        add_w_dn_ind(D1, A0),
        addq_w_dn(TYPE30_DRIFT_STRIDE, D0),
        andi_w_dn(D0, TYPE30_DRIFT_MASK),
        move_w_dn_abs_l(D0, DEATH_DRIFT_CURSOR),
        cmpi_w_abs_l(DEATH_ASCENT_TOP_Y, SCROLL_FOLLOW_Y),
        bcc(BNE_W, "tail"),
        move_w_imm_abs_w(DEATH_FLAG_SET, STAGE_RESET_BLOCK),
        # $bb0 — THE SHARED TAIL, which twelve branches reach
        lab("tail"),
        bsr("player_stage_transition"),
        move_w_imm_dn(D7, GATE_FLAG_SET),
        RTS,
        # $bba — DEAD: no instruction in the image aims here
        clr_w_dn(D7),
        RTS,
        # $bbe — the frames after the message: wait on the box, then leave for the disk prompt
        lab("prompt"),
        tst_w_abs_w(DEATH_BOX_EXPIRED_B0C),
        bcc(BNE_W, "datadisk"),
        tst_b_abs_l(TEXT_BOX_ACTIVE),
        bcc(BNE_W, "continue"),
        move_w_imm_abs_w(GATE_FLAG_SET, DEATH_BOX_EXPIRED_B0C),
        bra_s("tail"),
        lab("datadisk"),
        lea_d16(A7, UNWIND_ONE_BYTES),
        jmp_abs_l(GATE_DATADISK_TARGET),
        # $be2 — DATA inside the body: WB_LIVES itself
        word(LIVES_SHIPPED),
        # $be4 — FIRE with a life left spends one and restarts the level
        lab("continue"),
        tst_w_abs_w(LIVES),
        bcc_s(BEQ_W, "tail"),
        move_b_abs_w_dn(D0, JOY1_STATE),
        andi_b_dn(D0, 1 << JOY1_FIRE_BIT),
        bcc_s(BEQ_W, "tail"),
        move_b_imm_abs_l(TEXT_REQUEST_PRIMED, TEXT_REQUEST),
        subq_w_abs_w(1, LIVES),
        jsr_abs_l(leaf.entry_of("game_life_restart_reset")),
        move_w_imm_abs_l(POSTURE_STATE_ONE, EFFECT_STATE_21E4),
        subq_w_abs_l(1, LEVEL_SEQ_INDEX),
        move_w_imm_abs_l(GATE_FLAG_SET, LIFE_RESTART_ENTRY_C26),
        lea_d16(A7, UNWIND_ONE_BYTES),
        jmp_abs_l(UNWIND_TARGET),
        # $c26 — DATA inside the body again, and the word the `move.w` four instructions up raises
        word(LIFE_RESTART_ENTRY_SHIPPED),
        # $c28 — the STAGE-ANIMATION arm
        lab("stage-anim"),
        tst_w_abs_w(STAGE_ANIM_DONE_B10),
        bcc_s(BEQ_W, "tail"),
        tst_w_abs_w(EVENT_ANIM_DONE_B12),
        bcc(BNE_W, "spawn-from-script"),
        cmpi_w_abs_l(ACTOR_FREE_MARKER, SPAWN_GATE_SLOT),
        bcc(BNE_W, "tail"),
        lea_abs_l(A1, STUB_TABLE_BASE),
        move_w_imm_dn(D0, EVENT_SPAWN_SFX),
        clr_w_dn(D1),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        lea_abs_l(A2, SPAWN_GATE_SLOT),
        lea_abs_l(A1, TYPE35_TEMPLATE),
        bsr("scene_copy_record_fields"),
        bcc(BRA_W, "tail"),
        lab("spawn-from-script"),
        bsr("scene_spawn_from_script"),
        clr_l_abs_w(STAGE_ANIM_REQUEST_B0E),
        clr_w_abs_w(EVENT_ANIM_DONE_B12),
        bcc(BRA_W, "tail"),
        # $c76 — the SCENE-ALIGN arm, whose refusal goes to $d22 and not to the shared tail
        lab("scene-align"),
        tst_w_abs_w(EVENT_ANIM_DONE_B16),
        bcc(BNE_W, "event-finished"),
        cmpi_w_abs_l(ACTOR_FREE_MARKER, SPAWN_GATE_SLOT),
        bcc(BNE_W, "skip"),
        move_w_imm_abs_w(STATE_FLAG_SET, STATE_FLAG_A34),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_STOP_OFFSET),
        move_w_imm_dn(D0, EVENT_SPAWN_SFX),
        clr_w_dn(D1),
        lea_abs_l(A1, STUB_TABLE_BASE),
        jsr_d16_an(A1, STUB_TRIGGER_OFFSET),
        lea_abs_l(A2, TABLE_DEFAULT),
        movea_l_abs_l(A1, RECORD_PTR_10420),
        move_l_d16_ind(A1, EVENT_PAIR_POSITION, A2),
        clr_w_d16(A2, ACTOR_TYPE),
        move_w_imm_d16(A2, EVENT_PAIR_SPRITE_INERT, ACTOR_SPRITE),
        lea_d16(A2, RECORD_BYTES),
        move_l_d16_ind(A1, EVENT_PAIR_POSITION, A2),
        move_w_imm_d16(A2, EVENT_PAIR_TYPE_RISER, ACTOR_TYPE),
        move_w_imm_d16(A2, EVENT_PAIR_SPRITE_RISER, ACTOR_SPRITE),
        tst_w_d16(A1, TRIGGER_SPAWN_TYPE),
        bcc(BEQ_W, "tail"),
        move_w_imm_d16(A2, EVENT_PAIR_TYPE_ANIMATOR, ACTOR_TYPE),
        move_w_imm_d16(A2, EVENT_PAIR_SPRITE_ANIMATOR, ACTOR_SPRITE),
        bcc(BRA_W, "tail"),
        # $cf0 — the event is over: everything comes down, and the stage advances or does not
        lab("event-finished"),
        tst_w_abs_w(STAGE_ANIM_DONE_B18),
        bcc(BEQ_W, "tail"),
        clr_b_abs_l(TEXT_BOX_ACTIVE),
        clr_l_abs_w(ALIGN_REQUEST_B14),
        clr_w_abs_w(STAGE_ANIM_DONE_B18),
        tst_w_abs_l(STAGE_ADVANCE_REQUEST),
        bcc(BEQ_W, "no-advance"),
        clr_w_abs_l(STAGE_ADVANCE_REQUEST),
        bcc_abs(BRA_W, UNWIND_TAKEN_AT),
        lab("no-advance"),
        move_w_imm_abs_l(GATE_FLAG_SET, EVENT_FINISHED_E1BE),
        # $d22 — `move.w #$ffff,d7 / rts` WITHOUT the shared tail's call above it
        lab("skip"),
        move_w_imm_dn(D7, GATE_FLAG_SET),
        RTS,
    ]


ENTRY_PIECES = {
    "player_meter_empty_check": _meter_empty_pieces(),
    "player_jump_step": _jump_step_pieces(),
    "player_apply_joystick": _apply_joystick_pieces(),
    "player_reset_ground_state": _reset_ground_pieces(),
    "scene_copy_record_fields": _copy_record_pieces(),
    "player_step_and_arm": _step_and_arm_pieces(),
    "player_weapon_fire": _weapon_fire_pieces(),
    "player_stage_transition": _stage_transition_pieces(),
    "player_run_map_cell": _run_map_cell_pieces(),
    "player_pending_event_gate": _pending_event_gate_pieces(),
}
RECONSTRUCTED_ROUTINES = 10

ENTRY_BYTES = {name: leaf.asm(leaf.entry_of(name), pieces)
               for name, pieces in ENTRY_PIECES.items()}
INSN_COUNT = {name: leaf.instruction_count(pieces) for name, pieces in ENTRY_PIECES.items()}

# The two callees this file's bodies reach, as upper bounds on one call. Both belong to other
# batteries; `joy1_newly_pressed`'s body is five instructions and test_input.py pins it, and the SFX
# stub's cap comes from the battery that owns the sound module.
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
    "player_run_map_cell": 1170,        # $151a..$19ab, bounded by scene_spawn_from_script's entry —
                                        # and FOUR of those are data as well, the two handshake
                                        # words at $1960 the flute and the door talk through
    "player_pending_event_gate": 526,   # $b1a..$d27, bounded by bg_scroll_raise_requests' entry —
                                        # FOUR of those are data (WB_LIVES at $be2 and
                                        # WB_LIFE_RESTART_ENTRY_C26 at $c26) and FOUR more are the
                                        # dead `clr.w d7 / rts` at $bba
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
    # ...and the collision cell has ONE, the frame's eighth `bsr`.
    "player_run_map_cell": (0xa6c,),
    # ...and the gate has ONE, the frame's SECOND — which is what makes its d7 the frame's own
    # question and nobody else's.
    "player_pending_event_gate": (0xa3c,),
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
_JUMP_STEP_FN = leaf.bind("player_jump_step",
                          leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint)])


def _JUMP_STEP(actor):
    """The jump machine with its exit X DROPPED, which is the shape every case in this section
    wants: they pin the MEMORY each arm writes, and `emu.REPORTED_REGS` has no CCR, so a flag they
    could not compare would only be a value they had to invent. NULL is also what the five
    behaviour-tier `bsr $d78` callers pass in src/behavior.c.

    The model of the flag is pinned where the flag is CONSUMED — the frame's own battery below,
    which composes $a46/$a4a/$a4e and diffs the shot count the `sbcd` leaves."""
    return lambda _lib, image: _JUMP_STEP_FN(image, actor, None)
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


# The longest sentence any of these cases matches inside, plus room for the two leading control
# bytes of a WB_TEXT_MESSAGE_TABLE record. One window for all four, rather than a fresh number each.
MESSAGE_TEXT_WINDOW = 64


def _shipped_message_text(message_id):
    """The bytes WB_TEXT_MESSAGE_TABLE's ``message_id`` entry points at, so a case can check WHAT a
    posted id says against the image rather than against this battery's reading of it.

    FOUR cases wanted these six lines with four different window lengths before the fourth one made
    it a helper; the id is 1-based, which is the part worth having in one place."""
    at = (wb("TEXT_MESSAGE_TABLE")
          + (message_id - wb("TEXT_MESSAGE_FIRST_ID")) * (1 << wb("TEXT_MESSAGE_PTR_SHIFT")))
    where = int.from_bytes(harness.BASE_IMAGE[at:at + LONGWORD_BYTES], "big")
    return bytes(harness.BASE_IMAGE[where:where + MESSAGE_TEXT_WINDOW])


def test_the_message_the_wing_boots_post_is_the_one_the_shipped_string_names():
    """The id is 1-based into WB_TEXT_MESSAGE_TABLE, so the claim above is checkable against the
    image's own bytes rather than against this battery's reading of them."""
    text = _shipped_message_text(MESSAGE_WING_BOOTS_LOST)
    assert b"wing boots" in text.lower(), f"message {MESSAGE_WING_BOOTS_LOST:#x} reads {text!r}"


# --- $a76: the death check --------------------------------------------------------------------------
_METER_EMPTY_FN = leaf.bind("player_meter_empty_check",
                            leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint)])


def _METER_EMPTY(actor):
    """$a76 with its exit X DROPPED. This battery pins the MEMORY each arm writes; the flag it can
    also destroy is pinned where it is consumed, by the frame battery's refusal rows below."""
    return lambda _lib, image: _METER_EMPTY_FN(image, actor, None)


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


# --- THE CHEAT ARM, drivable since batch 42 phase A ------------------------------------------------
#
# WB_KEY_SEQUENCE_MATCHED steers both of the death check's tests — a raised word takes the revival
# arm with an EMPTY medicine slot and then SKIPS the rearm, so a cheating player revives for ever.
# The word lives at $604, inside the kit's harness-poked input block ($600..$61f), which for this
# project lies inside the game's own program because it loads at $3f8; `harness.make_image` refuses
# every poke into that block, since nothing in the kit can tell a poke staging model state from one
# seeding a game variable at the same address.
#
# ../project.toml now supplies the fact the kit could not have: `poked_input_program_data` declares
# $604..$607 to be this program's own data, so the seeding is served while the real hazard — a TRAP
# reading one of those bytes back as model state — stays refused per run by
# emu._vet_no_poked_input_read. Two cases below drive the arm; the third is the tripwire that fails
# if the declaration is dropped.


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


def test_the_cheat_word_is_seedable_only_because_the_project_declares_it_program_data():
    """The tripwire, in the direction the declaration made possible.

    Seeding $604 is served, and the address ONE BYTE PAST the declared span is not — so this fails
    the day `poked_input_program_data` is dropped or narrowed, which is exactly when the two cases
    below stop testing what they say.
    """
    image = harness.make_image({KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET)})
    at = KEY_SEQUENCE_MATCHED
    assert int.from_bytes(image[at:at + WORD_BYTES], "big") == KEY_SEQUENCE_MATCHED_SET
    with pytest.raises(RuntimeError, match="harness-poked input block"):
        harness.make_image({harness.OS_RANDOM_VALUE: word(0)})


@pytest.mark.parametrize("cheat", [KEY_SEQUENCE_MATCHED_SET, 1, 0x8000],
                         ids=lambda v: f"cheat{v:#06x}")
def test_the_cheat_word_revives_a_player_with_NO_medicine_and_skips_the_rearm(cheat):
    """THE GAME'S OWN CHEAT, as the death check sees it: `tst.w` twice on the same word, so any
    non-zero value takes the revival arm although the medicine slot is EMPTY, and then leaves the
    slot alone — the meter refills every death, for ever, off a slot that was never charged.

    The rearm is what separates this from the medicine's own arm above: `_revive_expected(rearm=...)`
    is the same model with that one store removed, and the case asserts the slot is untouched rather
    than only that the write set matched.
    """
    what = f"player_meter_empty_check with the cheat word {cheat:#06x} and an empty slot"
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: bytes([0]), KEY_SEQUENCE_MATCHED: word(cheat)})
    image = harness.make_image(pokes)

    expected = _revive_expected(image, rearm=False)
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)
    assert HUD_SLOT_BBC6 not in info["writes"], f"{what}: the empty slot was rearmed"


def test_the_cheat_word_and_a_CHARGED_slot_still_skip_the_rearm():
    """The two tests are on the same word and only the SECOND gates the rearm, so a cheating player
    who also holds a medicine keeps it: the slot is spent by nothing. Without this case a port that
    read the cheat once and reused the answer for both tests would pass."""
    what = "player_meter_empty_check with the cheat word and a charged slot"
    pokes = _death_pokes(what, {HUD_SLOT_BBC6: bytes([1]),
                                KEY_SEQUENCE_MATCHED: word(KEY_SEQUENCE_MATCHED_SET)})
    image = harness.make_image(pokes)

    expected = _revive_expected(image, rearm=False)
    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP)
    _assert_writes(info, expected, what)
    assert HUD_SLOT_BBC6 not in info["writes"], f"{what}: the charged slot was rearmed"


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

    expected = _flatten(model_play_song(image, DEATH_SONG))
    expected[ACTOR + ACTOR_FLAGS] = flags & ~(1 << FLICKER_BIT)
    for global_word in (STATE_FLAG_A34, STAGE_RESET_BLOCK, SCROLL_FOLLOW_FROZEN, PANEL_FRAME_HOLD):
        _put_word(expected, global_word, DEATH_FLAG_SET)

    info = leaf.run("player_meter_empty_check", _METER_EMPTY(ACTOR), merge_bands(expected), what,
                    regs={"a0": ACTOR, "_pokes": pokes}, max_insns=METER_EMPTY_CAP,
                    psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    _assert_writes(info, expected, what)


def test_the_message_the_revival_arm_posts_is_the_one_the_shipped_string_names():
    """The other half of the pair above, read off the image."""
    text = _shipped_message_text(MESSAGE_REVIVAL_USED)
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

    expected = _record_copy_writes(image, DESTINATION, SCENE, template)

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


def _record_copy_writes(image, destination, descriptor, template, into=None):
    """`scene_copy_record_fields`' whole write set: EIGHT longwords into ``destination``.

    The FIRST is the scene descriptor's own position longword, written over the record's x and y;
    the other seven are the template's bytes 4..31, because `lea 4(a1),a1` skips its first longword
    once the position has taken that place. FOUR cases spelt these five lines — the two that enter
    $539e directly and the two that reach it through the gate's composition — and a fifth would
    have been where the arithmetic drifted, which is the one divergence a per-battery write-set
    compare cannot catch, because each case supplies its own expectation.

    ``into`` merges into an existing model (the gate's arms have the SFX trigger's writes first)."""
    expected = {} if into is None else into
    _put_long(expected, destination, _image_long(image, descriptor + SCENE_SPAWN_POSITION))
    for i in range(TEMPLATE_LONGWORDS):
        _put_long(expected, destination + (i + 1) * LONGWORD_BYTES,
                  _image_long(image, template + SPAWN_TEMPLATE_UNREAD + i * LONGWORD_BYTES))
    return expected


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


def _map_row(row, stride=DEFAULT_STRIDE):
    return MAP_DEFAULT + MAP_CELLS + row * stride


def _clear_map_rows(pokes, row=None, stride=DEFAULT_STRIDE):
    """The probed cells zeroed. `map_pokes` keys every cell off its ADDRESS, which is right for the
    map battery's own cases and wrong here: a keyed cell would block a step at random and the arm a
    case is about would not be the thing moving.

    The band starts ONE ROW ABOVE the probed one because a probe that walks off the map's left edge
    names a NEGATIVE column, and `lea d16(An,Dn.w)` sign-extends it back into the previous row.

    `row` and `stride` are parameters because the frame-composition battery stands its record one
    cell lower and drives one case at a stride of its own; a second copy of this band is how a
    window ends up seeded off the wrong row while every case still passes."""
    row = PROBE_ROW if row is None else row
    pokes[_map_row(row - 1, stride)] = bytes(CLEARED_MAP_ROWS * stride)
    return pokes


def _fill_probe_row(pokes, row=None, stride=DEFAULT_STRIDE):
    """...and the same window with the probed row SOLID, for the cases about a blocked step."""
    row = PROBE_ROW if row is None else row
    pokes[_map_row(row, stride)] = bytes([TILE_BLOCK]) * stride
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


# THE WALK TAKES AND RETURNS THE X FLAG (include/player.h), and every case in THIS battery enters
# with the zero `emu.run`'s SR = $2700 gives the oracle — so the entry bit is 0 here, not a choice.
# What the routine RETURNS is invisible to a memory differential; the frame-composition battery
# further down is where the chain is pinned, at the one instruction that consumes it.
_STEP_AND_ARM = leaf.register_glue("player_step_and_arm", [ctypes.c_uint32, ctypes.c_uint],
                                   ctypes.c_uint)
WALK_ENTRY_EXTEND = 0
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
    info = leaf.run("player_step_and_arm", _STEP_AND_ARM(ACTOR, WALK_ENTRY_EXTEND),
                    merge_bands(expected), what,
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
    rows have.

    AND THE LIMIT IS THIS BATTERY'S ENTRY, NOT THE KIT'S — the first draft of this docstring said an
    entry-CCR parameter was what these rows waited on, and that is RETRACTED. A run that starts one
    instruction EARLIER, at the frame's `bsr.w $ec8`, produces the bit itself: the pair of cases
    below this section measure exactly that, on the original's own code.
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


# --- WHO SUPPLIES THAT PARAMETER, measured on the ORIGINAL -----------------------------------------
#
# `entry_extend` is a parameter because the bit is the CALLER's, and the caller is `$a38`'s pair of
# adjacent `bsr`s at `$a4a` (the walk) and `$a4e` (the weapon). So the frame top is the site that has
# to SUPPLY it, and the two cases below are what say — against the original's own 68000 code, with no
# reconstruction consulted — that it cannot supply a constant and cannot re-derive one afterwards.
#
# They are a PREMISE for `../STATUS.md`'s batch 41 phase D section, in the shape
# `test_the_busy_wait_can_NEVER_be_entered_with_its_byte_clear` established: the reading that blocks
# the row is a run, not a paragraph, and the day it stops holding is the day the block lifts.

# $a4a and $a4e, DERIVED from the frame's entry rather than transcribed: `bsr.w` x2, `tst.w d7`,
# `bmi.w`, `bsr.w` stand above the walk's call. The widths alone would be a transcription, so the
# case below PINS the bytes at both addresses against the two calls they must be — a width read
# wrong lands the pin on something that is not a `bsr.w` to the routine named.
BSR_W_BYTES = len(leaf.BSR_W) + WORD_BYTES
FRAME_ENTRY = leaf.entry_of("actor_behavior_type01_player")
FRAME_PREFIX_WIDTHS = (BSR_W_BYTES, BSR_W_BYTES, WORD_BYTES, 2 * WORD_BYTES, BSR_W_BYTES)
WALK_CALL_AT = FRAME_ENTRY + sum(FRAME_PREFIX_WIDTHS)
WEAPON_CALL_AT = WALK_CALL_AT + BSR_W_BYTES
AFTER_WEAPON_AT = WEAPON_CALL_AT + BSR_W_BYTES
PLATFORM_RIDDEN = wb("ACTOR_PLATFORM_RIDDEN")

# The cap for a run that crosses BOTH routines: each one's own, since the run is one of each.
WALK_THEN_WEAPON_CAP = STEP_AND_ARM_CAP + WEAPON_CAP

# The two seeds differ in the walk's DIRECTION byte and its SUB-FRAME counter, and in nothing else.
# WB_ACTOR_FIELD_23 is what picks the arm — the right-hand walk turns when the byte says LEFT and
# accelerates when it already says RIGHT — and the counter is chosen so that the two arms leave the
# record in the SAME state (see the second case).
#   * TURN: `subq.b #2,22(a0)` on the speed the fire edge has just cleared to zero borrows, so the
#     walk returns with X SET. The counter is left at the value the accelerator would have produced.
#   * ACCELERATE: `addq.b #1,24(a0)` on a counter of zero carries nothing, and `andi.b #$3` leaves it
#     nonzero, so the accelerator returns before its own `addq.w #4,d0` — the walk returns with X
#     CLEAR.
# Neither arm reaches a map probe, because both tails RE-READ the speed and find the fire edge's
# zero. That is what keeps the two runs' MEMORY identical while their X differs.
WALK_X_SET_SEED = {FIELD_23: 0, FIELD_24: 1}
WALK_X_CLEAR_SEED = {FIELD_23: ST_BYTE, FIELD_24: 0}
WALK_SPEND_COUNT = 0x05

# ONE SALT FOR BOTH RUNS, which is the opposite of this battery's usual rule and is the point here:
# `case_salt` keys the record's block by CASE NAME so that two cases cannot share a byte, and these
# two runs must differ in the two seeded fields above and in NOTHING else. A per-case salt makes the
# keyed record differ as well, and then "the walk left the same image" fails on bytes neither arm
# wrote — which is exactly how the first draft of these cases failed.
FRAME_COMPOSITION_SALT = "the frame's walk-then-weapon composition"


# The map window the composition's PROBING cases run on. `_weapon_pokes` stands the record at
# PLAYER_Y, one cell below where the walk battery puts it, so the probed row is re-derived here
# rather than borrowed: a band seeded off the wrong row leaves the probed cells keyed and the arm a
# case is about is not the thing that moved.
COMPOSITION_PROBE_ROW = (PLAYER_Y - 1) >> CELL_SHIFT


def _frame_composition_pokes(record_fields, direction=1 << JOY1_RIGHT_BIT, cells=None,
                             strength=WALK_STRENGTH, actor_x=None, stride=DEFAULT_STRIDE,
                             solid_probe_row=False):
    """`_weapon_pokes`' four open gates, plus everything the WALK reads on the way to them.

    THE DIRECTION IS HELD IN BOTH JOYSTICK BYTES, which is the seeding this composition needs and
    the weapon battery's own does not: the walk's head reads the CURRENT byte, and the weapon's
    third gate wants `joy1_newly_pressed` to be exactly WB_PLAYER_FIRE_EDGE_EXACT — so the
    direction has to be down ALREADY, or the edge byte is $88 and nothing fires. `direction` of 0
    is a frame with fire and DOWN alone, which is the walk's COASTING arm.

    `record_fields` are BYTE fields off `_WALK_QUIET_RECORD` — the same "takes no arm" record the
    walk battery seeds, reused rather than restated so that a new byte the walk reads is added in
    one place. The two WORD-wide inputs a case may move are named parameters instead (`actor_x`,
    `strength`), because a width decided by set membership is a width a case cannot see.

    THE MAP IS `map_pokes` PLUS THE WALK BATTERY'S OWN TWO WINDOW HELPERS, at this battery's row
    and stride. The stride layer is the one `_weapon_pokes` has no reason to carry and the one that
    matters most: the .PRG ships WB_COLLISION_MAP_DEFAULT's own word as ZERO, so without it every
    cell index collapses to its column, the stamped rows are never read, and BOTH of the tail's
    arithmetic arms leave X clear whatever a case seeds. That is how the first draft of the probing
    rows below read as "this arm gives 0" — a seeding fault wearing a finding's clothes.

    `cells` is {(row offset, column): tile} relative to COMPOSITION_PROBE_ROW, applied as a LATER
    overlay layer than the window: a cell poke and the four-row block share bytes, and
    `leaf.overlay` is what merges those byte by byte."""
    held = (1 << JOY1_DOWN_BIT) | direction
    fields = {
        JOY1_PREV: bytes([held]),
        JOY1_CURRENT: bytes([FIRE_EDGE_EXACT | held]),
        TILE_33_MODE: word(0),              # ...so the walk arm does not leave a ladder
        STATE_FLAG_A32: word(0),            # ...so a probe reads the DEFAULT collision map
        SCROLL_LIMIT_X: word(WIDE_LEVEL),   # ...and the right probe's clamp does not fire
        EFFECT_STATE_BD6A: word(strength),
        ACTOR + ACTOR_TYPE: word(TYPE_PLAYER),
        ACTOR + HALF_WIDTH: word(WALK_HALF_WIDTH),
    }
    fields.update({ACTOR + offset: bytes([value])
                   for offset, value in _WALK_QUIET_RECORD.items()})
    fields.update({ACTOR + offset: bytes([value]) for offset, value in record_fields.items()})
    if actor_x is not None:
        fields[ACTOR + ACTOR_X] = word(actor_x)

    # AT A ZERO STRIDE THERE ARE NO ROWS TO SEED: both helpers write `stride`-sized bands, so both
    # are empty, and a row that asked for them would run on `map_pokes`' keyed bytes and pass by
    # luck. The mutation sweep caught exactly that — two stride-0 rows agreeing with the model while
    # driving an arm nobody chose. Such a row names its cells by INDEX instead (see `cells`).
    window = {}
    if stride:
        _clear_map_rows(window, COMPOSITION_PROBE_ROW, stride)
        if solid_probe_row:
            _fill_probe_row(window, COMPOSITION_PROBE_ROW, stride)
    else:
        assert not solid_probe_row, "a solid ROW is meaningless at a stride of zero"
        assert cells, "a zero-stride row must name the cell the probe lands on, by index"
    stamped = {_map_row(COMPOSITION_PROBE_ROW + row, stride) + column: bytes([tile])
               for (row, column), tile in (cells or {}).items()}
    return leaf.overlay(map_pokes(case_salt(FRAME_COMPOSITION_SALT), default_stride=stride),
                        _weapon_pokes(FRAME_COMPOSITION_SALT, WEAPON_LIGHTNING,
                                      count=WALK_SPEND_COUNT, fields=fields),
                        window, stamped)



def _run_walk_then_weapon(record_fields, stop_pc):
    """The ORIGINAL's own `$a4a`/`$a4e` pair, run under the oracle with no reconstruction involved."""
    image = harness.make_image(_frame_composition_pokes(record_fields))
    after, _, _ = emu.run(image, WALK_CALL_AT, {"a0": ACTOR},
                          max_insns=WALK_THEN_WEAPON_CAP, stop_pc=stop_pc)
    return after


def test_the_frames_two_adjacent_bsrs_are_the_walk_and_the_weapon():
    """The pin under both cases below: the addresses they run from are the two calls they claim, and
    the instruction after them is the fall guard — which is what says the pair is ADJACENT, with
    nothing between the walk's `rts` and the weapon's entry to write the X flag."""
    assert bytes(harness.BASE_IMAGE[WALK_CALL_AT:WEAPON_CALL_AT]) \
        == leaf.asm(WALK_CALL_AT, [bsr("player_step_and_arm")])
    assert bytes(harness.BASE_IMAGE[WEAPON_CALL_AT:AFTER_WEAPON_AT]) \
        == leaf.asm(WEAPON_CALL_AT, [bsr("player_weapon_fire")])
    assert bytes(harness.BASE_IMAGE[AFTER_WEAPON_AT:AFTER_WEAPON_AT + len(
        tst_w_abs_l(PLATFORM_RIDDEN))]) == tst_w_abs_l(PLATFORM_RIDDEN)


def test_the_walks_two_arms_leave_the_image_IDENTICAL():
    """HALF ONE OF THE MEASUREMENT, and the half that makes the other half mean something.

    Both seeds are run as far as the weapon's entry — i.e. `player_step_and_arm` alone — and the two
    images are required to be equal byte for byte. So whatever separates the two runs below is NOT in
    memory, and no function of the image can recover it. That is what rules out the
    `overlap_mask_exit_extend` treatment, where the exit bit is re-computed from the words the last
    arithmetic instruction read: here the two arms write the same words with the same values."""
    turn = _run_walk_then_weapon(WALK_X_SET_SEED, WEAPON_CALL_AT)
    accelerate = _run_walk_then_weapon(WALK_X_CLEAR_SEED, WEAPON_CALL_AT)
    assert bytes(turn) == bytes(accelerate), (
        "the two walk arms no longer leave the same image, so the pair below is no longer a claim "
        "about a CPU flag — re-derive the two seeds before reading its result")

    # AND NEITHER ARM TOOK A PROBE, which is the premise UNDER the premise and the one the shared
    # pokes builder can silently move: both tails re-read the speed the fire edge cleared, so the
    # record's x must be exactly where it was seeded. A seed change that lets a probe run makes the
    # probe zero the speed mid-loop for a player record, and the equality above would fail here
    # instead of in the row that moved it.
    at = ACTOR + ACTOR_X
    assert bytes(turn[at:at + WORD_BYTES]) == word(PLAYER_X), (
        "a walk arm moved the record, so one of these seeds now reaches a map probe and this pair "
        "is no longer the flag-only comparison it claims to be")


def test_the_SAME_image_then_spends_a_DIFFERENT_shot_count():
    """HALF TWO: identical memory in, different memory out — so the difference travelled in a
    condition-code bit, and the only one `sbcd -(a2),-(a6)` reads is X.

    WHAT THIS BLOCKS. `actor_behavior_type01_player` cannot hand `player_weapon_fire` a constant
    `entry_extend` (either constant is wrong on one of these two runs) and cannot compute one from
    the image (the case above says the image is the same). It has to THREAD the walk's exit X —
    which batch 41 phase E then did, through the walk's five sections and the two map probes, with
    the battery below this pair as the pin. ../STATUS.md's phase D section prices what was left.

    The two counts are stated from `leaf.bcd_expected`'s decimal model rather than from each other,
    so a run that spent nothing at all fails here instead of looking like agreement."""
    turn = _run_walk_then_weapon(WALK_X_SET_SEED, AFTER_WEAPON_AT)
    accelerate = _run_walk_then_weapon(WALK_X_CLEAR_SEED, AFTER_WEAPON_AT)

    at = WEAPON_RECORD + RECORD_LOW_BYTE
    assert turn[at] == _spend_bytes(WALK_SPEND_COUNT, borrow=1)[at], (
        f"the TURN arm left {turn[at]:#04x} in the count — it no longer reaches the weapon with X "
        f"set, so the reading this premise rests on has moved")
    assert accelerate[at] == _spend_bytes(WALK_SPEND_COUNT, borrow=0)[at], (
        f"the ACCELERATE arm left {accelerate[at]:#04x} in the count, not the X-clear spend")

    # AND EXACTLY ONE ADDRESS DIFFERS, which is the half four documents attribute to this case and
    # the half phase E's pricing rests on. Without it the two rows above would still pass while the
    # weapon diverged somewhere else as well — and then "the difference is one BCD byte the X flag
    # decided" would be a claim about the two bytes the case happens to read, not about the run.
    diverged = {addr for addr in range(len(turn)) if turn[addr] != accelerate[addr]}
    assert diverged == {at}, (
        f"the two runs differ at {sorted(hex(a) for a in diverged)}, not at the single "
        f"{at:#x} — the walk's two arms now separate somewhere besides the shot count, so this "
        f"pair no longer isolates the X flag")


# --- THE CHAIN ITSELF: the walk's exit X, composed into the weapon and diffed against the original -
#
# BATCH 41 PHASE E. The two cases above say the bit exists and travels in a flag; these say the
# reconstruction carries THE SAME ONE, on every path a firing frame can reach. Each row runs the
# ORIGINAL's `$a4a`/`$a4e` pair under the oracle and the two C routines composed the way those two
# adjacent `bsr`s compose them, and requires the whole image to agree.
#
# WHY THE COMPOSITION LIVES IN THE GLUE HERE. When these rows were written
# `actor_behavior_type01_player` ($a38) had no reconstruction, so no C function spelt
# `bsr $ec8 / bsr $1208`. Batch 41 phase F ported it and the frame battery at the foot of this file
# drives the WHOLE row; these rows keep the two-call glue on purpose, because a pair is the smallest
# thing that can carry a flag between two routines and a failure here names which of the two moved.
# The glue adds no arithmetic of its own, and the entry bit it hands the walk is the zero `emu.run`
# gives the oracle (SR = $2700), not a value the case chose.
#
# WHAT EACH ROW CLAIMS, BEYOND THE DIFFERENTIAL. `expected_extend` is the X the row says the WALK
# leaves, and it is checked against the ORACLE's own shot count through `leaf.bcd_expected`'s decimal
# model — so a row states which path it drove instead of asserting that two runs agree. Without it a
# case whose seeding quietly stopped reaching the `sbcd` would still pass: both sides would spend
# nothing, agree perfectly, and pin no flag at all.
def _compose_walk_then_weapon(entry_extend):
    """`$a4a` and `$a4e`, in C. The walk's returned X is the weapon's `entry_extend` and nothing
    between them touches the flag — which is the whole of what this battery pins.

    THE TWO SYMBOLS ARE THE BATTERY'S EXISTING BINDINGS and not fresh ones, which is not tidiness:
    `leaf.bind` is `getattr` on a `ctypes.CDLL`, and ctypes CACHES the function object on the
    library — so a second `bind` of a name already bound hands back the SAME object and its
    `argtypes`/`restype` are whatever the last call set. Two spellings of one prototype in one file
    is a signature change silently applied to both, or silently discarded from one."""
    def glue(lib, image):
        exit_extend = _STEP_AND_ARM(ACTOR, entry_extend)(lib, image)
        _WEAPON_FIRE(ACTOR, exit_extend)(lib, image)
        return exit_extend
    return glue


def _run_frame_composition(what, pokes, expected_extend, probe=None):
    """One composition row. `probe` is the map probe the row claims to drive, and it is checked as
    an EXECUTED PC rather than inferred.

    WHY THAT WITNESS EXISTS: a row picks its probe with one joystick bit, and a seeding change that
    stops the direction reaching the walk turns the row into a coasting frame that still agrees with
    the model — the bit it then pins is a pass-through, not the arm the row's name claims. That is
    the shape the review flagged when two rows here were found driving nothing, and the shape a
    duplicated direction constant invites."""
    with leaf.pc_coverage():
        diffs, info = leaf.differential(WALK_CALL_AT, {"a0": ACTOR, "_pokes": pokes},
                                        _compose_walk_then_weapon(WALK_ENTRY_EXTEND),
                                        max_insns=WALK_THEN_WEAPON_CAP,
                                        stop_pc=AFTER_WEAPON_AT, poison=True)
        entered = probe is None or emu.cov_visited(leaf.entry_of(probe))
    assert not diffs, f"{what}\n{leaf.report(diffs)}"
    assert entered, (
        f"{what}: the run never executed {probe}, so this row drove a walk that took no map step "
        f"at all — whatever it pins is not the arm it names")

    at = WEAPON_RECORD + RECORD_LOW_BYTE
    spent = info["writes"].get(at)
    assert spent == _spend_bytes(WALK_SPEND_COUNT, borrow=expected_extend)[at], (
        f"{what}: the ORIGINAL left {spent!r} in the shot count, not the "
        f"X={expected_extend} spend the row claims — either the run never reached the `sbcd` or "
        f"the walk leaves a different bit than this row says")
    return info


# The walk's exit-X model, one row per path a frame that also FIRES can reach, with the seed that
# drives it and the bit it must leave. The four sections' plates in src/player.c are what these
# rows check; ../STATUS.md names the paths no firing frame can reach at all.
FLICKER_FLAG = 1 << FLICKER_BIT
# The speed the accelerator leaves when it ticks its counter over: one pixel, so a probing row's
# step is the smallest that still takes a probe.
COMPOSITION_STEP_SPEED = 1


def _right_step_column(actor_x):
    """The map column an ordinary RIGHT step lands in: `(x + 14(a0) + d7) asr #4`, wrapped to a word
    first because the probe is computed in one. One derivation, because two rows below want it at
    two different x values and a second spelling is how they would drift apart."""
    probe = (actor_x + WALK_HALF_WIDTH + COMPOSITION_STEP_SPEED) & WORD_MASK
    return probe >> CELL_SHIFT


def _left_step_column(actor_x):
    """...and the column a LEFT step lands in: `(x - 14(a0) - d7) asr #4`, the same shape with both
    signs flipped. A negative result is a real column here — `lea d16(An,Dn.w)` sign-extends it back
    into the row above — which is what the edge rows below use."""
    # Python's `>>` on a negative int IS an arithmetic shift, which is what `asr.w` does, so the
    # probe stays signed here rather than being wrapped to a word first.
    return (actor_x - WALK_HALF_WIDTH - COMPOSITION_STEP_SPEED) >> CELL_SHIFT


# The cell one row UNDER the one a right step lands in. A BLOCK there takes the tail's MIDDLE arm —
# the only one that writes no flag of its own and hands the probe body's bit out (the arm accepts a
# ledge too, and the rows below stamp a block because either reaches it).
BLOCK_UNDER_STEP = _right_step_column(PLAYER_X)
BLOCK_UNDER_LEFT_STEP = _left_step_column(PLAYER_X)
WRAPPING_X = 0xffff             # ...so the commit's `add.w d7,(a0)` carries out of the word
BLOCK_UNDER_WRAPPED_STEP = _right_step_column(WRAPPING_X)
# The LEFT probe's edge arm: an x this close to the map's origin makes `x - half_width - speed`
# NEGATIVE, which parks the record and leaves `cell_pointer`'s `add.w` as the last arithmetic.
EDGE_X = 2
# ...and the cell that arm lands on is the row ABOVE the probed one, last column, because the
# negative column is sign-extended back into it.
EDGE_CELL_COLUMN = DEFAULT_STRIDE - 1
# The strength word whose `addq.w #4,d0` CARRIES, and its twin that does not. Both leave a ceiling
# BYTE of zero, which is what stops the accelerator's own tail taking a probe and overwriting the
# bit — the pair differs in the high half alone, so only the WORD add can separate them.
STRENGTH_WORD_CARRY = 0xfffc
STRENGTH_WORD_NO_CARRY = 0x00fc
ACCELERATE_SUBFRAME = WALK_SUBFRAME_MASK        # ...so the next tick wraps the counter to zero

ACCELERATING_RIGHT = {FIELD_23: ST_BYTE, FIELD_24: ACCELERATE_SUBFRAME}
ACCELERATING_LEFT = {FIELD_23: 0, FIELD_24: ACCELERATE_SUBFRAME}
# A stride of ZERO is what the .PRG itself ships in WB_COLLISION_MAP_DEFAULT's word, and it is the
# ONE input that separates the tail's two arithmetic arms from constants: `neg.w d7` on a zero
# leaves X CLEAR where every ordinary stride sets it, and `add.w d7,d7` is then a zero doubled.
# With no rows to speak of, the cell one row down IS the cell, so the middle arm wants a LEDGE
# there — the one tile that arm accepts and the first arm does not.
COLLAPSED_STRIDE = 0
TILE_LEDGE = wb("MAP_TILE_LEDGE")

FRAME_X_PATHS = (
    ("turn borrows out of a zeroed speed", dict(record_fields=WALK_X_SET_SEED), 1),
    ("the accelerator's counter does not carry", dict(record_fields=WALK_X_CLEAR_SEED), 0),
    ("no section writes X at all — the caller's bit passes through",
     dict(record_fields={}, direction=0), 0),
    ("the flicker countdown borrows",
     dict(record_fields={FLICKER_COUNTDOWN: 0, ACTOR_FLAGS: FLICKER_FLAG}, direction=0), 1),
    ("the knock-back's own `subq.b` overwrites the probe's bit",
     dict(record_fields={FIELD_29: 1}, direction=0, solid_probe_row=True, probe=STEP_LEFT), 0),
    ("the accelerator's `addq.w #4` carries out of the WORD",
     dict(record_fields=ACCELERATING_RIGHT, strength=STRENGTH_WORD_CARRY), 1),
    ("...and does not, on the same path, off the same ceiling byte",
     dict(record_fields=ACCELERATING_RIGHT, strength=STRENGTH_WORD_NO_CARRY), 0),
    ("the probe's tail stops on a BLOCK, so `neg.w d7` decides",
     dict(record_fields=ACCELERATING_RIGHT, solid_probe_row=True, probe=STEP_RIGHT), 1),
    ("...and `neg.w d7` on a ZERO stride leaves it CLEAR, which is what makes that arm a reading",
     dict(record_fields=ACCELERATING_RIGHT, stride=COLLAPSED_STRIDE,
          cells={(0, BLOCK_UNDER_STEP): TILE_BLOCK}, probe=STEP_RIGHT), 0),
    ("the probe's tail finds nothing under it, so `add.w d7,d7` does",
     dict(record_fields=ACCELERATING_RIGHT, probe=STEP_RIGHT), 0),
    ("the probe's tail finds a block under it and passes the commit's carry through",
     dict(record_fields=ACCELERATING_RIGHT, cells={(1, BLOCK_UNDER_STEP): TILE_BLOCK},
          probe=STEP_RIGHT), 0),
    ("...and the same arm with an x whose commit CARRIES",
     dict(record_fields=ACCELERATING_RIGHT, actor_x=WRAPPING_X,
          cells={(1, BLOCK_UNDER_WRAPPED_STEP): TILE_BLOCK}, probe=STEP_RIGHT), 1),
    ("the LEFT probe's edge arm, where `cell_pointer`'s `add.w` is the last arithmetic",
     dict(record_fields=ACCELERATING_LEFT, actor_x=EDGE_X, direction=HELD_LEFT,
          cells={(0, EDGE_CELL_COLUMN): TILE_BLOCK}, probe=STEP_LEFT), 1),
    # ...and the same edge arm with the row product COLLAPSED to zero, where `add.w d0,d1` adds a
    # $ffff column to nothing and does NOT carry. Without it `cell_pointer`'s bit is pinned at one
    # value and a port that hard-coded a set bit answered the row above.
    ("...and the same edge arm where that `add.w` does not carry",
     dict(record_fields=ACCELERATING_LEFT, actor_x=EDGE_X, direction=HELD_LEFT,
          stride=COLLAPSED_STRIDE,
          cells={(0, _left_step_column(EDGE_X)): TILE_LEDGE}, probe=STEP_LEFT), 0),
    # The LEFT probe committing a move and then finding a block under it — the only combination
    # that carries `step_left_commit`'s borrow out of the routine, and one the edge and solid rows
    # above both miss (the first takes no commit, the second is overwritten by the tail's `neg.w`).
    ("the LEFT probe's commit borrow, carried out through the tail's middle arm",
     dict(record_fields=ACCELERATING_LEFT, direction=HELD_LEFT,
          cells={(1, BLOCK_UNDER_LEFT_STEP): TILE_BLOCK}, probe=STEP_LEFT), 0),
    # ...and the LEFT probe into the tail's FIRST arm, which the edge rows cannot reach: an edge arm
    # is a middle-arm case, so without this one every left-hand path in the battery passes the
    # body's own bit through and a port that reported BEFORE the tail answered them all. The
    # mutation sweep is what found that — it was the round's one real hole.
    ("the LEFT probe's tail stops on a BLOCK, so the body's bit does not escape it either",
     dict(record_fields=ACCELERATING_LEFT, direction=HELD_LEFT, solid_probe_row=True,
          probe=STEP_LEFT), 1),
)


@pytest.mark.parametrize("case,seed,expected_extend", FRAME_X_PATHS,
                         ids=[row[0] for row in FRAME_X_PATHS])
def test_the_walks_exit_X_reaches_the_weapons_sbcd(case, seed, expected_extend):
    """ONE ROW PER X-WRITER THE WALK CAN LEAVE ITS LAST, and the composition diffed whole.

    A row's `expected_extend` is not a second statement of the C: it is read off the ORIGINAL's shot
    count, so it says which of the model's paths the seed really drove. The differential above it is
    what says the reconstruction agrees — and because the only thing separating an X of 0 from an X
    of 1 here is ONE packed-BCD unit in one byte, a port that dropped the bit anywhere along the
    chain fails on the rows whose true bit is set, and one that invented it fails on the rest."""
    what = f"the frame's walk-then-weapon composition: {case}"
    probe = seed.pop("probe", None)
    _run_frame_composition(what, _frame_composition_pokes(**seed), expected_extend, probe)


def test_the_walk_hands_a_SET_caller_bit_STRAIGHT_THROUGH_to_the_sbcd():
    """THE OTHER HALF OF `entry_extend`, and the only half no row above can reach.

    Every case in this file enters the oracle with X clear (`emu.run` forces SR = $2700), so
    "returns the caller's bit" and "returns zero" are the same claim there — and the pass-through is
    the load-bearing one, because a frame that FIRES is exactly a frame on the walk's coasting arm:
    the weapon's third gate wants the newly-pressed byte to be $80, so the walk's fire edge runs, so
    the speed is cleared at $f06 and the drift's gate lowered at $f00. That is the arm `$a38` will
    have to supply a bit to.

    C-ONLY, and the file already owns the shape — `leaf.run_candidate_only`, as
    `test_the_three_OTHER_arms_carry_the_callers_extend_and_no_case_here_can_set_it` uses it for the
    weapon's own entry bit. What it pins is the C against `leaf.bcd_expected`'s independent decimal
    model, which is weaker than the oracle and much stronger than nothing: the run must carry the
    bit through four sections that write no flag and spend it in the `sbcd`.

    AND IT ASSERTS THE PAIR, not one value: the same seed with a CLEAR entry bit must spend the
    other count. A port that hard-coded either constant answers one of the two rows and fails the
    other, which is what makes the parameter an input rather than a formality."""
    pokes = _frame_composition_pokes({}, direction=0)
    at = WEAPON_RECORD + RECORD_LOW_BYTE

    for entry_extend in (0, 1):
        returned, image = leaf.run_candidate_only(_compose_walk_then_weapon(entry_extend), pokes)
        assert returned == entry_extend, (
            f"the walk was entered with X={entry_extend} on its pass-through arm and returned "
            f"{returned} — no section on that path writes the flag, so the two must be equal")
        assert image[at] == _spend_bytes(WALK_SPEND_COUNT, borrow=entry_extend)[at], (
            f"the weapon spent {image[at]:#04x} off the count with an entry X of {entry_extend}, "
            f"not the decimal model's — the bit did not survive the walk into the `sbcd`")


# --- WB_ACTOR_PLATFORM_RIDDEN's operand census, as a case ------------------------------------------
#
# Every instruction in the image that names the word the frame's fall guard reads, and WHAT each one
# is: EIGHT sites in seven routines, FIVE of them abs.LONG and THREE abs.w. The frame's own guard is
# one of the LONG ones.
#
# WHAT THE EARLIER CENSUS IN ../names.txt MISSED IS FIVE SITES, AND THE AXIS IS NOT THE ENCODING.
# That plate listed three, and they are exactly one per routine its own first sentence already names
# — the raise in `actor_platform_carry_followed`, the clear in `actor_platform_release_check`, the
# read in slot 56. So it enumerated what it met while reading THREE BODIES and stated the total as an
# image-wide one. Two of its three are abs.LONG and two of the five it missed are abs.w, so an
# encoding blind spot cannot be the mechanism; three of the missed five sit in the same platform band
# as the three it had, so a band cut cannot be either. The axis is ROUTINE COVERAGE.
#
# `$a52` is the costly omission — the fall guard of `actor_behavior_type01_player`, which was the
# last unported dispatch row when this census was taken and is a reconstruction as of batch 41
# phase F. `$e5ba` is
# the sharpest: it is the instruction BOTH of the player frame's `jmp $e5ba.l` unwinds land on, so the
# word the fall guard reads is taken down by the very transfer that abandons the frame.
PLATFORM_RIDDEN_READERS = (0xa52, 0x6e36, 0x6f0a, 0x6f42)
PLATFORM_RIDDEN_INSNS = {
    0xa52: tst_w_abs_l(PLATFORM_RIDDEN),                       # $a38's own fall guard
    0x6da2: move_w_imm_abs_l(1, PLATFORM_RIDDEN),              # the word's one raise
    0x6e14: clr_w_abs_l(PLATFORM_RIDDEN),
    0x6e36: tst_w_abs_l(PLATFORM_RIDDEN),
    0x6eca: clr_w_abs_l(PLATFORM_RIDDEN),
    0x6f0a: tst_w_abs_w(PLATFORM_RIDDEN),
    0x6f42: tst_w_abs_w(PLATFORM_RIDDEN),
    0xe5ba: clr_w_abs_w(PLATFORM_RIDDEN),                      # where both unwinds land
}


def test_the_platform_word_is_named_in_BOTH_absolute_encodings():
    """THE CORRECTION ../names.txt's `cmt 0x6ef0` carries. The earlier plate's site count and its
    reader count are both low — the image holds eight and four — and the block above says why, which
    is not the reason a first reading of the two lists suggests.

    The census is run BOTH ways round, which is what makes it a census rather than a list: every
    instruction above is required to be in the image, and the raw two-byte scan is required to find
    nothing the table does not name."""
    for at, encoding in PLATFORM_RIDDEN_INSNS.items():
        assert bytes(harness.BASE_IMAGE[at:at + len(encoding)]) == encoding, (
            f"{at:#x} does not hold the instruction the census claims for {PLATFORM_RIDDEN:#x}")

    # A word address appears whole in a short operand and as the LOW HALF of a long one, so the
    # scan's offsets are the encodings' own operand words rather than the instruction addresses.
    found = set(_operand_sites(PLATFORM_RIDDEN.to_bytes(WORD_BYTES, "big")))
    expected = {at + len(encoding) - WORD_BYTES
                for at, encoding in PLATFORM_RIDDEN_INSNS.items()}
    assert found == expected, (
        f"the scan finds {sorted(hex(a) for a in found)} against the census's "
        f"{sorted(hex(a) for a in expected)}")
    readers = tuple(sorted(at for at, encoding in PLATFORM_RIDDEN_INSNS.items()
                           if encoding in (tst_w_abs_w(PLATFORM_RIDDEN),
                                           tst_w_abs_l(PLATFORM_RIDDEN))))
    assert readers == tuple(sorted(PLATFORM_RIDDEN_READERS)), (
        f"the census's readers are {[hex(at) for at in readers]}, not the four the plate names")


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
    # ...and the three batch 41 phase C's censuses needed. THE LIST IS OPCODE-EXACT, which is what
    # keeps it honest and what bounds it: `subq.w #n` and the two register forms below encode their
    # count and their register INTO the opcode word, so these three entries cover `#1`, `d1` and
    # `a0` and nothing else. A site with another count or register is not silently dropped — it
    # lands in the `other` dict with the word in front of it, which is where a census goes wrong.
    (0x5378, 2, False),      # subq.w  #1,<abs>.w
    (0x3238, 2, False),      # move.w  <abs>.w,D1 — a SHORT operand, so two bytes after the opcode
    (0x41f8, 2, False),      # lea     <abs>.w,A0 — a POINTER, not an operand of the word itself
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
    # --- and batch 41 phase C's four, three of which are one routine's whole private state --------
    "STAGE_RESET_BLOCK": ({0xad2: 0x4a79,               # tst.w  $b08.l  \ player_meter_empty_check's
                           0xaee: 0x33fc,               # move.w #$ffff  / death arm, guard and raise
                           0xb1a: 0x4a78,               # tst.w  $b08.w  — the gate's FIRST test
                           0xbaa: 0x31fc,               # move.w #$ffff  — its ascent's re-raise
                           0x1fd6: 0x4a78,             # tst.w  $b08.w  — the death ANIMATION arm
                           # ...and the SIXTH, which names the word as a POINTER rather than reading
                           # it: the `lea $b08.w,a0` the block reset walks its eighteen bytes with.
                           # It is why the name reads oddly at the five above — one address, two
                           # jobs — and it DOES write $b08, as the run's first `clr.l`.
                           0xfed2: 0x41f8},
                          {}),
    "DEATH_MESSAGE_POSTED_B0A": ({0xb36: 0x4a78,        # tst.w  $b0a.w
                                  0xb62: 0x31fc},       # move.w #$ffff,$b0a.w
                                 # ...and eight coincidences inside the SOUND MODULE's pattern data,
                                 # none of them with an instruction in front. A word this small has
                                 # them; the near-miss list is what keeps the count of two honest.
                                 {0x1aa58: 0x0d0c, 0x1ab3a: 0x0a09, 0x1ab4c: 0x0a09,
                                  0x1ab84: 0x0d0c, 0x1ab8e: 0x0d0c, 0x1ab98: 0x0d0c,
                                  0x1aba2: 0x0d0c, 0x1abb2: 0x0d0c}),
    "DEATH_BOX_EXPIRED_B0C": ({0xbbe: 0x4a78,           # tst.w  $b0c.w
                               0xbd0: 0x31fc},          # move.w #$ffff,$b0c.w
                              {0x1a9f6: 0x080a}),
    # ...and WB_LIVES, whose plate said FOUR until this phase ported the fifth site's routine.
    "LIVES": ({0xb4e: 0x4a79,                           # tst.w  $be2.l  — which message goes up
               0xbe4: 0x4a78,                           # tst.w  $be2.w  — the prompt's own guard
               0xbfc: 0x5378,                           # subq.w #1,$be2.w
               0xe80c: 0x3238,                          # move.w $be2.w,d1 — the icon redraw
               0xfe50: 0x31fc},                         # move.w #$3,$be2.w — the new-game reset
              {}),
    "EVENT_FINISHED_E1BE": ({0xd1a: 0x33fc,             # move.w #$ffff,$e1be.l — the gate's raise
                             0xe032: 0x4a79},           # tst.w  $e1be.l — the ONE reader, and the
                                                        # first instruction of the routine it gates
                            {0xe096: 0x0000}),
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
# What the gate's THREE STACK UNWINDS are, read off the bytes
# ==================================================================================================
#
# `player_pending_event_gate` ($b1a) is RECONSTRUCTED as of batch 41 phase C and its differential is
# at the foot of this file; what stays here is the structural pair that came first, when the routine
# was measured rather than ported. THREE of its exits leave through a stack unwind instead of
# returning — `lea 4(a7),a7 / jmp` at $bd8 and $c1c, and `bra.w $1622` at $d16, which lands in
# `player_run_map_cell`'s own `lea 12(a7),a7 / jmp $e5ba.l` and so pops THREE return addresses
# in ANOTHER routine's body. That third one is why the count was two until batch 40 phase C: a census
# of this routine's own instructions cannot see a pop that happens somewhere else. Both claims below
# were live failure modes, and both are what the exit reports now stand on.

GATE_SPAWN_SITE = 0xc52            # `lea $998c.l,a2 / lea $537e.l,a1 / bsr.w $539e`
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


# Keyed on the `lea`, which is where the pop IS. The `jmp` is four bytes on ($bdc, $c20) and the two
# addresses being different is worth keeping straight in a case that is about counting them — and in
# a checkpointed run, where the `lea` is the WITNESS and the `jmp` is the stop. ../names.txt's
# `cmt 0xb1a` keys on the `lea` too, as of batch 41 phase C; it named the `jmp` before that.
GATE_UNWIND_EXITS = {
    0xbd8: (0x4fef0004, 0xe494),     # lea 4(a7),a7 / jmp $e494.l — one return address
    0xc1c: (0x4fef0004, 0xe5ba),     # lea 4(a7),a7 / jmp $e5ba.l — one
}
# ...and the THIRD, which is not the gate's own instruction at all: it branches into
# `player_run_map_cell` and unwinds there. `UNWIND_TAKEN_AT` above is that address; a second name for
# it here is what the review found, and one name is the repair.
COLLIDE_UNWIND = (0x4fef000c, 0xe5ba)   # lea 12(a7),a7 / jmp $e5ba.l — THREE return addresses


def _unwind_at(addr):
    """(the `lea n(a7),a7` longword, the address its `jmp` names) decoded out of the image."""
    return (int.from_bytes(harness.BASE_IMAGE[addr:addr + LONGWORD_BYTES], "big"),
            int.from_bytes(harness.BASE_IMAGE[addr + LONGWORD_BYTES + WORD_BYTES:
                                              addr + 2 * LONGWORD_BYTES + WORD_BYTES], "big"))


def test_the_gate_leaves_through_THREE_stack_unwinds_and_one_of_them_is_not_its_own():
    """WHAT THE THREE EXIT REPORTS STAND FOR, counted. Two of the three are its own `lea 4(a7),a7 / jmp` pairs. The
    third is the one every surface in this project said did not exist until batch 40 phase C:
    `bra.w $1622` at $d16 lands inside `player_run_map_cell`, whose `lea 12(a7),a7 / jmp
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
    assert _unwind_at(UNWIND_TAKEN_AT) == COLLIDE_UNWIND, (
        f"$1622 is {[hex(v) for v in _unwind_at(UNWIND_TAKEN_AT)]}, not the triple pop")
    assert 0xd16 in CONTROL_FLOW_TARGETS[UNWIND_TAKEN_AT], (
        "the gate does not branch to $1622, so the third exit is not the gate's")
    entry = leaf.entry_of("player_run_map_cell")
    assert entry < UNWIND_TAKEN_AT < 0x19ac, (
        "$1622 is not inside player_run_map_cell, so the pop is not in another routine")
    # The pop's DEPTH is the claim that matters, and it is read off each `lea`'s displacement rather
    # than written down: 12 bytes of return addresses is three of them, 4 is one.
    assert (COLLIDE_UNWIND[0] & WORD_MASK) // LONGWORD_BYTES == 3
    for at, (pop, _target) in GATE_UNWIND_EXITS.items():
        assert (pop & WORD_MASK) // LONGWORD_BYTES == 1, (
            f"the unwind at {at:#x} does not discard exactly one return address")


def test_the_gates_spawn_site_loads_the_TEMPLATE_in_a1_and_the_DESTINATION_in_a2():
    """THE LIVE FAILURE MODE batch 40 phase A registered and could not exercise: `scene_copy_record_
    fields` takes two record addresses and a port that swapped them would copy the record OVER the
    template and stay green in every case above, because each supplies both registers itself.

    So the operands come out of the image here. `lea $998c.l,a2` is the DESTINATION — slot 1 of
    WB_ACTOR_TABLE_DEFAULT, which the `cmpi.w #$ffbe,$998c.l` at $c36 has just checked is free — and
    `lea $537e.l,a1` is WB_ACTOR_TYPE35_TEMPLATE."""
    assert _image_operands_at(GATE_SPAWN_SITE) == [(A2, SPAWN_GATE_SLOT), (A1, TYPE35_TEMPLATE)], (
        f"the two `lea`s at {GATE_SPAWN_SITE:#x} are not the a2=destination / a1=template pair")
    assert SPAWN_GATE_SLOT == TABLE_DEFAULT + RECORD_BYTES, (
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

    expected = _record_copy_writes(image, destination, SCENE, template)

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


# --- $151a: the player's own map cell ---------------------------------------------------------------
#
# WHAT SHAPES THIS PART OF THE BATTERY. Every case here seeds a COLLISION MAP, which nothing above it
# in this file does: the cell the routine reads is computed from the record's x,y and a stride word
# that lies past the program's last byte, so both are zero in the shipped image and a case that
# seeded neither would read cell 0 of a map of zero-length rows. The band around the cell is
# address-keyed for the usual reason — a lookup one cell out reads a byte that is wrong FOR WHERE IT
# WAS READ rather than a plausible zero.
#
# THE DESCRIPTOR TABLE IS SEEDED THE SAME WAY and for a sharper reason: it is loaded from disk, so
# there is no shipped datum to run against at all, and every one of the eight kinds is a branch on a
# word out of it.
_RUN_MAP_CELL = leaf.register_glue("player_run_map_cell", [ctypes.c_uint32], ctypes.c_uint32)

# A stride wide enough that the row term dominates the column one (so a case that lost the multiply
# would not land on the same cell by accident) and — the half the first draft got wrong — with a
# NONZERO LOW NIBBLE. `asr.w #4` and `lsr.w #4` on a negative row differ by exactly $f000, and
# $f000 * any multiple of 16 is 0 in the low word, so a stride of $20 made the row shift's
# SIGNEDNESS invisible to every case at once. $1e leaves $2000 of difference.
MAP_STRIDE = 0x1e

# THE GATE BYTES ARE SEEDED NONZERO, and that is the attribution pass rather than tidiness: the
# poison re-run inverts every byte the ORACLE wrote, and on the three arms that clear the map cell
# the inverted cell code is $ff — which `cmpi.b #$3 / blt` sends to the tile-flag arm, so the
# poisoned run exercises a DIFFERENT path and stops catching a write whose value already equals the
# seed. Bits 4 and 7 of WB_ACTOR_FLAGS and bit 7 of WB_ACTOR_FLAGS2 are read by nothing in $151a and
# written by nothing in it either, so a record carrying them takes exactly the same arms.
QUIET_FLAGS = (1 << 4) | (1 << 7)
QUIET_FLAGS2 = 1 << 7


def _cell_for(x, y):
    """The address $1536's `lea` reaches for a record at (x, y) — the whole lookup, restated from the
    68000's own widths so a case cannot inherit the port's arithmetic: `asr.w` on both coordinates,
    an UNSIGNED `mulu.w`, a word-wide `add.w` and a SIGN-EXTENDED index."""
    row = leaf.s16((y - CELL_Y_BIAS) & WORD_MASK) >> MAP_CELL_SHIFT
    column = leaf.s16(x) >> MAP_CELL_SHIFT
    return COLLISION_MAP_CELL_0 + leaf.s16((MAP_STRIDE * (row & WORD_MASK) + column) & WORD_MASK)


CELL = _cell_for(PLAYER_X, PLAYER_Y)
# ...and the band around it, as a LENGTH only: its base is per-case, because a case that moves
# the record moves the cell, so a module-level `CELL - MAP_STRIDE` would be right for the
# default position and quietly wrong for every other.
CELL_BAND_LEN = 2 * MAP_STRIDE + 1

# The scene's own actor slot and the followed record, each with a whole record of margin, so a write
# one field out is a write to a keyed byte.
SPAWN_SLOT_BAND = (TRIGGER_SPAWN_SLOT, RECORD_BYTES)
FOLLOWED_BAND = (FOLLOWED_DEFAULT, RECORD_BYTES)

# A cell code for each band, chosen so that no two cases share one: the scene cases take
# TRIGGER_CELL and the tile cases their own tile code.
TRIGGER_CELL_CODE = TRIGGER_CODE_FIRST + 5
DESCRIPTOR = TRIGGER_TABLE + ((TRIGGER_CELL_CODE - TRIGGER_CODE_FIRST) << TRIGGER_RECORD_SHIFT)
DESCRIPTOR_BAND = (DESCRIPTOR, TRIGGER_RECORD_BYTES)

# Four descriptor words a spawn copies, chosen so none of them is a plausible neighbour of another.
SPAWN_WORDS = {TRIGGER_X: 0x0123, TRIGGER_SPAWN_Y: 0x0456,
               TRIGGER_SPAWN_TYPE: 0x0789, TRIGGER_SPAWN_FIELD: 0x0abc}
VISITS_LEFT = 3            # ...and a visit counter that does NOT reach zero on the case's own frame
METER_SEED = 0x100         # a meter high enough that WB_PLAYER_TILE_HURT_COST leaves it positive

# The widest single path this routine has, as an upper bound: its own body once, the runner's
# sentinel, and every callee it can reach on any ONE of its arms — the high-pool walk (tile $34), the
# SFX trigger (four kinds), the stop chain (kind 4) and a song start (kind 8). No path needs all
# four, which is what makes it a cap rather than a measurement.
MAP_CELL_CAP = _cap("player_run_map_cell",
                    extra=ALLOC_STRAIGHT_LINE_INSNS + ALLOC_HIGH_SLOTS * ALLOC_INSN_PER_SLOT
                    + STUB_INSN_CAP + STOP_INSN_CAP + PLAY_SONG_INSN_CAP)


def _cell_pokes(what, code, fields=None, slot_free=True, pool_full=False,
                x=PLAYER_X, y=PLAYER_Y, record=None):
    """A frame in which the player stands on cell `code`, with everything the eight kinds read.

    THE KEYED BANDS ARE THEIR OWN LAYER, which is `leaf.overlay`'s documented hazard and the one this
    battery would hit first: the cell, the spawn slot's x and the four descriptor words all lie
    INSIDE a keyed block, so a single dict literal holding both would drop the block entirely and
    every case would run on the .PRG's zeros."""
    salt = case_salt(what)
    # THE RECORD IS A PARAMETER because a0 is the CALLER's, not this battery's ACTOR: one case aims
    # it at a descriptor word on purpose, to drive the alias the `move.w d0,(a0)` snap creates.
    record = ACTOR if record is None else record
    cell = _cell_for(x, y)
    keyed = {lo: keyed_block(lo, length, salt)
             for lo, length in ((cell - MAP_STRIDE, CELL_BAND_LEN), SPAWN_SLOT_BAND, FOLLOWED_BAND,
                                DESCRIPTOR_BAND, *PLAY_SONG_SEEDED_BANDS)}
    # THE POOL IS TWO LAYERS AND NOT ONE DICT, which is `_weapon_pokes`' hard-won lesson repeated:
    # WB_ACTOR_X is 0, so the FIRST record's marker key IS `POOL_LO` — in one literal it replaces the
    # whole 192-byte keyed block with a two-byte word and every other byte of the pool runs on the
    # .PRG's zeros, where a spurious clear the port makes is invisible.
    pool = {POOL_LO: keyed_block(POOL_LO, POOL_LEN, salt)}
    markers = {TABLE_DEFAULT + slot * RECORD_BYTES + ACTOR_X: word(0 if pool_full else FREE_MARKER)
               for slot in range(ALLOC_HIGH_FIRST, ALLOC_HIGH_FIRST + ALLOC_HIGH_SLOTS)}

    base = {cell: bytes([code]),
            MAP_ROW_STRIDE: word(MAP_STRIDE),
            TABLE_SELECTED: longword(TABLE_DEFAULT),
            record + ACTOR_X: word(x), record + ACTOR_Y: word(y),
            record + ACTOR_FLAGS: bytes([QUIET_FLAGS]), record + FLAGS2: bytes([QUIET_FLAGS2]),
            # the scene slot is FREE by default, which is what the four spawning kinds require
            TRIGGER_SPAWN_SLOT + ACTOR_X: word(FREE_MARKER if slot_free else PLAYER_X),
            FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0]),
            FOLLOWED_DEFAULT + ACTOR_X: word(PLAYER_X),
            # ...and every global the routine can write, seeded to a value no arm produces
            TILE_33_FLAG: bytes([MARKER, MARKER]),
            RECORD_PTR_10420: longword(MARKER), RECORD_PTR_10424: longword(MARKER),
            SCENE_MARKER_CELL_PTR: longword(MARKER),
            ALIGN_REQUEST_B14: word(MARKER), STAGE_ADVANCE_REQUEST: word(MARKER),
            SCROLL_FOLLOW_FROZEN: word(MARKER), PANEL_FRAME_HOLD: word(MARKER),
            STATE_FLAG_A34: word(MARKER), STAGE_ANIM_REQUEST_B0E: word(MARKER),
            PANEL_FRAME_DELAY: word(MARKER), HUD_METER_VALUE: word(METER_SEED),
            # ...and the gates, each seeded CLOSED so a case that wants an arm opens it itself
            FLUTE_PLAYED: word(MARKER), LEVEL_SEQ_INDEX: word(MARKER),
            HUD_SLOT_BBC4: word(MARKER), HUD_SLOT_BBC8: bytes([MARKER]),
            KEY_LAST_SCANCODE: bytes([MARKER])}
    for offset, value in SPAWN_WORDS.items():
        base[DESCRIPTOR + offset] = word(value)
    base[DESCRIPTOR + TRIGGER_VISITS] = word(VISITS_LEFT)
    seeded = _pokes(what, leaf.overlay(keyed, pool, markers, base, fields or {}))
    leaf.assert_bands_are_seeded(seeded, [(POOL_LO, POOL_LEN), (cell - MAP_STRIDE, CELL_BAND_LEN),
                                          SPAWN_SLOT_BAND, FOLLOWED_BAND, DESCRIPTOR_BAND],
                                 f"{what}: a keyed band was dropped")
    return seeded


def _run_cell(what, pokes, expected, exit_code=None, stop_pc=0, via=None, psg_seed=None,
              extra_band=(), record=ACTOR):
    """Every case's runner. `via` is the transfer instruction a checkpointed run must have executed,
    which is what stops a `stop_pc` case passing on a run that simply returned. `record` is a0."""
    exit_code = EXIT_RETURN if exit_code is None else exit_code
    how = dict(regs={"a0": record, "_pokes": pokes}, max_insns=MAP_CELL_CAP, stop_pc=stop_pc,
               psg_seed=psg_seed)
    bands = merge_bands(expected) + list(extra_band)
    if via is None:
        info = leaf.run("player_run_map_cell", _RUN_MAP_CELL(record), bands, what, **how)
    else:
        info = leaf.run_reaching("player_run_map_cell", _RUN_MAP_CELL(record), bands, what, via,
                                 **how)
    _assert_writes(info, expected, what)
    assert info["ret"] == exit_code, (
        f"{what}: the reconstruction reported {info['ret']}, not the {exit_code} this case expects")
    return info


# --- the cell lookup itself -------------------------------------------------------------------------

@pytest.mark.parametrize("code", [0, 1, 2, 0x80, 0xff],
                         ids=["zero", "block", "ledge", "sign-bit", "all-ones"])
def test_a_cell_below_the_first_trigger_code_only_lowers_the_tile_flags_BYTE(code):
    """`cmpi.b #$3,(a6) / blt` is a SIGNED byte test, so $80 and $ff take this arm as surely as 0
    does — which is what bounds the trigger band at 3..$22 rather than 3..$ff, since the `ble`
    below it would otherwise admit every negative code twice over. And the write is `clr.b`: the
    flag's HIGH byte alone, so the seeded low byte survives."""
    what = f"player_run_map_cell cell={code:#04x}"
    pokes = _cell_pokes(what, code)

    _run_cell(what, pokes, {TILE_33_FLAG: 0})


def test_tile_33_raises_the_same_byte_the_arm_above_lowers():
    """`st $1514.w` — Scc's true BYTE, against the `move.w #$ffff` actor_fall_and_settle writes to
    the same word. The two halves of the word are what tells them apart."""
    what = "player_run_map_cell tile 33"
    pokes = _cell_pokes(what, TILE_33)

    _run_cell(what, pokes, {TILE_33_FLAG: TILE_33_FLAG_RAISED_BYTE})


@pytest.mark.parametrize("code", [TRIGGER_CODE_LAST + 1, TILE_33 - 1, TILE_39 + 1, 0x7f],
                         ids=["one-past-the-triggers", "one-below-33", "one-past-39", "largest"])
def test_a_cell_above_the_trigger_band_that_names_NO_tile_writes_nothing_at_all(code):
    """The tile ladder's own default, which is the third band's silent majority: seven `cmpi.b`s
    against distinct codes and an `rts` under them. `one-past-the-triggers` is the boundary from the
    OTHER side — $23 is the first code the `ble` refuses — and `one-past-39` says the ladder ends
    where it does rather than running on into the unwind."""
    what = f"player_run_map_cell unknown tile {code:#04x}"
    pokes = _cell_pokes(what, code)

    _run_cell(what, pokes, {})


@pytest.mark.parametrize("x,y", [(0x0000, 0x0010), (0x0140, 0x0088), (0x03f0, 0x0230),
                                 (0x0010, 0x0000), (0xfff0, 0x0088), (0xff00, 0x0000)],
                         ids=["origin", "ordinary", "far", "above-the-bias", "left-of-the-map",
                              "both-negative"])
def test_the_cell_is_the_row_stride_times_the_row_plus_the_column(x, y):
    """The lookup, driven at four positions with tile $33 planted at the cell each one SHOULD reach
    and nothing planted anywhere else — so a port that dropped the `mulu`, the bias or either shift
    lands on a keyed byte and raises no flag.

    THREE of the six rows are about SIGNEDNESS, and each pins a different half of it.
    `above-the-bias` says the `subi.w #$10` happens BEFORE the `asr.w`: a y of 0 gives -16, and
    bias-after lands on a different cell. `left-of-the-map` drives a NEGATIVE x, which is the only
    thing that separates the column's `asr.w #4` from a logical shift — the column is ADDED, so the
    two readings differ by $f000 in the index. `both-negative` drives a negative ROW as well, which
    the stride's low nibble is what makes visible (see MAP_STRIDE)."""
    what = f"player_run_map_cell lookup x={x:#06x} y={y:#06x}"
    pokes = _cell_pokes(what, TILE_33, x=x, y=y)

    _run_cell(what, pokes, {TILE_33_FLAG: TILE_33_FLAG_RAISED_BYTE})


# --- the six special tiles ----------------------------------------------------------------------------

def _launch_flags(flags):
    """`bset #0 / bset #1 / bclr #2` over one byte, whatever order they are spelt in."""
    return (flags | (1 << MOVING_BIT) | (1 << LAUNCHED_BIT)) & ~(1 << SUPPORTED_BIT) & 0xff


@pytest.mark.parametrize("flags", [0, 1 << MOVING_BIT, 0xff & ~(1 << SUPPORTED_BIT)],
                         ids=["clear", "moving", "everything-but-supported"])
def test_tile_34_does_nothing_at_all_to_an_UNSUPPORTED_record(flags):
    """`btst #2,8(a0) / bne` guards the whole arm, allocator included."""
    what = f"player_run_map_cell tile 34 unsupported flags={flags:#04x}"
    pokes = _cell_pokes(what, TILE_34, fields={ACTOR + ACTOR_FLAGS: bytes([flags])})

    _run_cell(what, pokes, {})


def test_tile_34_launches_the_record_and_spawns_one_on_its_own_x_and_y():
    """The whole arm: the speed literal, the three motion bits, and `move.l (a0),(a1)` — the x AND
    the y as ONE operand into the record the high pool hands back."""
    what = "player_run_map_cell tile 34"
    flags = 1 << SUPPORTED_BIT
    pokes = _cell_pokes(what, TILE_34, fields={ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {ACTOR + SPEED: TILE_34_SPEED, ACTOR + ACTOR_FLAGS: _launch_flags(flags)}
    _put_word(expected, SHOT + ACTOR_X, PLAYER_X)
    _put_word(expected, SHOT + ACTOR_Y, PLAYER_Y)
    _put_word(expected, SHOT + ACTOR_TYPE, TILE_34_SPAWN_TYPE)
    _run_cell(what, pokes, expected)


def test_tile_34_still_launches_when_the_high_pool_is_FULL():
    """`cmpa.l #$0,a1 / beq` — the allocation is tested and the record is not written, but the three
    bits and the speed above it have already landed. So a full pool costs the arm nothing."""
    what = "player_run_map_cell tile 34 pool full"
    flags = 1 << SUPPORTED_BIT
    pokes = _cell_pokes(what, TILE_34, fields={ACTOR + ACTOR_FLAGS: bytes([flags])},
                        pool_full=True)

    _run_cell(what, pokes, {ACTOR + SPEED: TILE_34_SPEED, ACTOR + ACTOR_FLAGS: _launch_flags(flags)})


@pytest.mark.parametrize("code", [TILE_35, TILE_36], ids=["tile-35", "tile-36"])
def test_a_record_already_FLICKERING_pays_the_hurt_tiles_nothing(code):
    """`btst #6,8(a0) / bne` leaves through the tile ladder's own tail, so neither the meter nor the
    knock-back happens — and the two codes reach that test by two different paths."""
    what = f"player_run_map_cell tile {code:#04x} flickering"
    pokes = _cell_pokes(what, code,
                        fields={ACTOR + ACTOR_FLAGS: bytes([1 << FLICKER_BIT])})

    _run_cell(what, pokes, {})


def _hurt_expected(meter_left, flags=QUIET_FLAGS, flags2=QUIET_FLAGS2):
    """What the hurt arm leaves on the record and on the meter, given what they were SEEDED with.

    Both hurt cases state the same six writes, which is why they are here rather than spelt twice.
    ONLY THE SFX HALF COMES FROM THE OWNING BATTERY — `_sfx_bytes`, which each case adds itself; the
    four writes of `$6ade`'s tail are restated here from the ORIGINAL's four instructions
    (`bset #0 / bset #1 / bclr #2 / move.b #$5,11(a1)`) rather than imported, because test_actor.py
    models that tail only as part of `actor_damage_followed`'s own arms and has no exported model of
    it alone. So this is a second statement of four writes, and what keeps it honest is that it
    starts from the SEEDED bytes: every one of them is a `bset`/`bclr` on a byte the case chose, so
    a model that started from zero would agree with a port that STORED the byte instead of masking
    it."""
    expected = {ACTOR + FLAGS2: flags2 | (1 << FLAGS2_BIT_0),
                ACTOR + ACTOR_FLAGS: _launch_flags(flags | (1 << FLICKER_BIT)),
                ACTOR + FLICKER_COUNTDOWN: DAMAGE_FLICKER_FRAMES,
                ACTOR + SPEED: DAMAGE_KNOCKBACK_SPEED}
    _put_word(expected, HUD_METER_VALUE, meter_left)
    return expected


@pytest.mark.parametrize("code", [TILE_35, TILE_36], ids=["tile-35", "tile-36"])
def test_the_hurt_tiles_are_ONE_arm_reached_by_two_paths(code):
    """Everything the pair does: WB_ACTOR_FLAGS2_BIT_0 and the flicker raised, the countdown stamped,
    WB_PLAYER_TILE_HURT_COST off the meter, and then the SHARED TAIL at $6ade — the SFX, whose write
    set comes from the battery that owns the trigger, and the four writes `_hurt_expected` states."""
    what = f"player_run_map_cell tile {code:#04x}"
    pokes = _cell_pokes(what, code)
    image = harness.make_image(pokes)

    expected = dict(_sfx_bytes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A))
    expected.update(_hurt_expected(METER_SEED - TILE_HURT_COST))
    _run_cell(what, pokes, expected)


@pytest.mark.parametrize("meter,left", [(TILE_HURT_COST, 0), (TILE_HURT_COST - 1, 0), (0, 0),
                                        (0x8001, 0x8001 - TILE_HURT_COST)],
                         ids=["exact", "one-short", "empty", "already-negative"])
def test_the_hurt_tiles_meter_floor_reads_the_RESULT_and_not_the_value(meter, left):
    """`subq.w #4,$b6fa.l / bpl / clr.w` — the branch reads what the subtraction LEFT, so a meter
    already negative that the borrow carries back into the positive half is stored rather than
    floored. `already-negative` is that row and it is the one a `max(0, …)` port fails."""
    what = f"player_run_map_cell hurt meter={meter:#06x}"
    pokes = _cell_pokes(what, TILE_35, fields={HUD_METER_VALUE: word(meter)})
    image = harness.make_image(pokes)

    expected = dict(_sfx_bytes(image, DAMAGE_FOLLOWED_SFX, SND_CHANNEL_A))
    expected.update(_hurt_expected(left))
    _run_cell(what, pokes, expected)


@pytest.mark.parametrize("supported", [False, True], ids=["airborne", "supported"])
def test_tile_37_nudges_only_a_SUPPORTED_record(supported):
    """`subq.w #6,(a0)` behind a `btst #2,8(a0) / beq`, and the step is IN MEMORY on the x."""
    what = f"player_run_map_cell tile 37 supported={supported}"
    flags = (1 << SUPPORTED_BIT) if supported else 0
    pokes = _cell_pokes(what, TILE_37, fields={ACTOR + ACTOR_FLAGS: bytes([flags])})

    expected = {}
    if supported:
        _put_word(expected, ACTOR + ACTOR_X, PLAYER_X - TILE_37_X_STEP)
    _run_cell(what, pokes, expected)


@pytest.mark.parametrize("delay", [0x0011, 0x0010, 0x0000, 0xffff],
                         ids=["odd", "even", "zero-wraps", "all-ones"])
def test_tile_38_steps_the_panel_delay_and_then_masks_it_EVEN(delay):
    """TWO stores to one word. The ledger records final values, so what this pins is the
    composition: a `subq.w` that wraps $0000 to $ffff and then a mask that makes it $fffe."""
    what = f"player_run_map_cell tile 38 delay={delay:#06x}"
    pokes = _cell_pokes(what, TILE_38, fields={PANEL_FRAME_DELAY: word(delay)})

    expected = {}
    _put_word(expected, PANEL_FRAME_DELAY, (delay - 1) & PANEL_FRAME_DELAY_EVEN)
    _run_cell(what, pokes, expected)


def test_tile_39_leaves_through_the_TRIPLE_POP_having_written_nothing():
    """WB_PLAYER_COLLIDE_UNWIND. The oracle is stopped at the `jmp $e5ba.l` at $1626, so what this
    compares is the whole image one instruction into the arm — the `lea 12(a7),a7` above it has run,
    and it moves a REGISTER, so the image is still the one at the transfer.

    THE WITNESS IS THAT `lea`, and the checkpoint sits below it for exactly that reason: `emu.run`
    stops BEFORE marking the checkpoint's own PC, so a witness has to lie ABOVE it, and the `lea` is
    the only instruction on this arm that no other path executes. The obvious choice — the `beq.w`
    at $161c — witnesses NOTHING: it runs on every path that reaches the tile-$39 test, taken or
    not."""
    what = "player_run_map_cell tile 39"
    pokes = _cell_pokes(what, TILE_39)

    _run_cell(what, pokes, {}, exit_code=EXIT_UNWIND, stop_pc=UNWIND_SITE,
              via=UNWIND_TAKEN_AT)


def test_the_unwind_discards_THREE_return_addresses_and_jumps_to_the_sequence_advance():
    """What WB_PLAYER_COLLIDE_UNWIND stands in for, read off the image rather than claimed: the two
    instructions at the checkpoint. A port that reported the exit for a `rts` would still pass the
    case above; this is what says the original does not return."""
    at = UNWIND_TAKEN_AT
    assert bytes(harness.BASE_IMAGE[at:at + 4]) == lea_d16(A7, UNWIND_STACK_BYTES), \
        f"{at:#x} is not `lea {UNWIND_STACK_BYTES}(a7),a7`"
    assert at + 4 == UNWIND_SITE, "the checkpoint is not the instruction after the pop"
    assert bytes(harness.BASE_IMAGE[UNWIND_SITE:UNWIND_SITE + 6]) == jmp_abs_l(UNWIND_TARGET)
    assert UNWIND_STACK_BYTES == 3 * LONGWORD_BYTES, (
        "the pop is not three return addresses, which is what makes this arm abandon its caller's "
        "caller as well as its caller")


# --- the eight scene triggers -------------------------------------------------------------------------

def _published(expected, descriptor=DESCRIPTOR, republished=True):
    """The descriptor pointer, which every path through the trigger band writes — and its copy,
    which SIX of the eight arms make — kinds 4 and 7 are the two that do not."""
    _put_long(expected, RECORD_PTR_10420, descriptor)
    if republished:
        _put_long(expected, RECORD_PTR_10424, descriptor)
    return expected


def _spawn_expected(image, sprite, sfx=None, speed=None, field_10=None, launched=False,
                    side_bit=None, visits=VISITS_LEFT, cell=CELL):
    """What the four spawning kinds have in common, and the four ways they differ. `side_bit` is
    kind 1's alone; `visits` is what the counter held on entry.

    THE FLAG BYTE STARTS FROM WHAT THE SLOT WAS SEEDED WITH, which is the whole reason that byte is
    keyed: every one of these arms reaches it with `bset`/`bclr` alone, so the five bits none of them
    names come back unchanged and a model that started from zero would agree with a port that
    STORED the byte instead of masking it."""
    slot = TRIGGER_SPAWN_SLOT
    flags = image[slot + ACTOR_FLAGS]
    expected = _published({})
    if sfx is not None:
        expected.update(_sfx_bytes(image, sfx, SND_CHANNEL_A))
    _put_word(expected, slot + ACTOR_X, SPAWN_WORDS[TRIGGER_X])
    _put_word(expected, slot + ACTOR_Y, SPAWN_WORDS[TRIGGER_SPAWN_Y])
    _put_word(expected, slot + ACTOR_TYPE, SPAWN_WORDS[TRIGGER_SPAWN_TYPE])
    _put_word(expected, slot + FIELD_12, SPAWN_WORDS[TRIGGER_SPAWN_FIELD])
    if side_bit is not None:
        flags = ((flags | (1 << SIDE_BIT)) if side_bit else (flags & ~(1 << SIDE_BIT))) & 0xff
    if launched:
        flags = _launch_flags(flags)
    expected[slot + ACTOR_FLAGS] = flags & ~(1 << FLICKER_BIT)
    if field_10 is not None:
        expected[slot + FIELD_10] = field_10
    if speed is not None:
        expected[slot + SPEED] = speed
    _put_word(expected, slot + ACTOR_SPRITE, sprite)
    _put_word(expected, DESCRIPTOR + TRIGGER_VISITS, (visits - 1) & WORD_MASK)
    if visits - 1 == 0:
        # THE CELL IS A PARAMETER because `_cell_pokes` computes it from the record's x,y: a spawn
        # case that moved the player would seed one cell and expect the clear at another, and the
        # write set would be wrong in a way that reads as a port bug. Every spawning case today
        # stands at the battery's default position, so the default is right — and stating it as an
        # argument is what stops the next one being silently wrong.
        expected[cell] = 0
    return expected


def _trigger_pokes(what, kind, fields=None, **kwargs):
    """A frame standing on TRIGGER_CELL_CODE, with the descriptor's kind word set."""
    seeds = {DESCRIPTOR + TRIGGER_KIND: word(kind)}
    seeds.update(fields or {})
    return _cell_pokes(what, TRIGGER_CELL_CODE, fields=seeds, **kwargs)


@pytest.mark.parametrize("kind", [0, KIND_TUNE + 1, 0x8000, WORD_MASK],
                         ids=["zero", "one-past-the-last", "sign-bit", "all-ones"])
def test_a_kind_word_outside_the_ladder_PUBLISHES_THE_DESCRIPTOR_AND_NOTHING_ELSE(kind):
    """THE DEFAULT ARM IS NOT INERT, and this is the case that says so. `move.l a1,$10420.l` runs
    BEFORE the kind word is even read, so a cell whose descriptor none of the eight arms claims
    still hands scene_run_frame ($dbc0) a descriptor to branch on — which is how that routine is
    ever given one, since this instruction is the image's ONLY writer of that pointer."""
    what = f"player_run_map_cell trigger kind={kind:#06x}"
    pokes = _trigger_pokes(what, kind)

    _run_cell(what, pokes, _published({}, republished=False))


@pytest.mark.parametrize("code", [TRIGGER_CODE_FIRST, TRIGGER_CODE_FIRST + 1,
                                  TRIGGER_CODE_LAST - 1, TRIGGER_CODE_LAST],
                         ids=["first", "second", "penultimate", "last"])
def test_the_cell_code_indexes_the_descriptor_table_from_its_FIRST_code(code):
    """`subq.l #3,d0 / lsl.w #5,d0` — cell 3 is descriptor 0, and the band's last code is $22, so the
    table this routine can reach is exactly WB_SCENE_TRIGGER_CODE_LAST - FIRST + 1 records long."""
    what = f"player_run_map_cell trigger code={code:#04x}"
    descriptor = TRIGGER_TABLE + ((code - TRIGGER_CODE_FIRST) << TRIGGER_RECORD_SHIFT)
    pokes = _cell_pokes(what, code, fields={descriptor + TRIGGER_KIND: word(0)})

    _run_cell(what, pokes, _published({}, descriptor=descriptor, republished=False),
              extra_band=[(descriptor, WORD_BYTES)])


@pytest.mark.parametrize("kind", [KIND_SPAWN_1, KIND_SPAWN_2, KIND_SPAWN_5, KIND_SPAWN_6],
                         ids=["kind-1", "kind-2", "kind-5", "kind-6"])
def test_a_spawning_kind_gives_up_on_a_slot_that_is_not_FREE(kind):
    """`tst.w (a2) / bmi` on the scene slot's x — and the copy to WB_RECORD_PTR_10424 above it has
    already happened, so "gives up" is not "does nothing"."""
    what = f"player_run_map_cell kind {kind} busy slot"
    pokes = _trigger_pokes(what, kind, slot_free=False)

    _run_cell(what, pokes, _published({}))


@pytest.mark.parametrize("slot_x,free", [(0x0000, False), (0x0001, False), (0x7fff, False),
                                         (0x8000, True), (FREE_MARKER, True), (0xffff, True)],
                         ids=["zero", "one", "largest-positive", "sign-bit", "free-marker",
                              "all-ones"])
def test_the_free_slot_test_is_a_SIGN_test_and_not_a_marker_comparison(slot_x, free):
    """`tst.w (a2) / bmi` — the arms take the slot on a NEGATIVE x, not on WB_ACTOR_FREE_MARKER
    specifically. The two readings agree on every x the game produces (map positions are positive
    and the free marker is $ffbe) and part company on $8000 and $ffff, which no shipped frame
    reaches; `zero` is the boundary itself, where `bmi` and a `beq`-style test disagree.

    A port that compared against the marker word instead refuses `sign-bit` and `all-ones`; one that
    used `<= 0` takes `zero`. Both are green on every other case in this file."""
    what = f"player_run_map_cell slot x={slot_x:#06x}"
    pokes = _trigger_pokes(what, KIND_SPAWN_6,
                           fields={TRIGGER_SPAWN_SLOT + ACTOR_X: word(slot_x)})
    image = harness.make_image(pokes)

    expected = (_spawn_expected(image, TRIGGER_SPRITE_6) if free
                else _published({}))
    _run_cell(what, pokes, expected)


@pytest.mark.parametrize("side", [False, True], ids=["followed-faces-right", "followed-faces-left"])
def test_kind_1_copies_the_followed_records_side_bit_INVERTED(side):
    """`btst #3,8(a5) / bne` jumps to the `bclr`, so the record this arm spawns faces the way the
    player is NOT facing. It is the one arm of the eight that reads the followed record at all."""
    what = f"player_run_map_cell kind 1 followed-side={side}"
    followed = (1 << SIDE_BIT) if side else 0
    pokes = _trigger_pokes(what, KIND_SPAWN_1,
                           fields={FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([followed])})
    image = harness.make_image(pokes)

    _run_cell(what, pokes,
              _spawn_expected(image, TRIGGER_SPRITE_1, sfx=TRIGGER_SFX_1,
                              speed=TRIGGER_SPAWN_SPEED, field_10=TRIGGER_SPAWN_1_FIELD_10,
                              launched=True, side_bit=not side))


def test_kind_2_is_kind_1_without_the_side_bit_and_without_the_countdown_byte():
    """The two arms differ in exactly three writes, which is why they are separate here rather than
    one parametrized case: kind 2 writes no WB_ACTOR_FIELD_10, reads no followed record, and plays
    WB_SCENE_TRIGGER_SFX_2 where kind 1 plays its own."""
    what = "player_run_map_cell kind 2"
    pokes = _trigger_pokes(what, KIND_SPAWN_2)
    image = harness.make_image(pokes)

    _run_cell(what, pokes,
              _spawn_expected(image, TRIGGER_SPRITE_2, sfx=TRIGGER_SFX_2,
                              speed=TRIGGER_SPAWN_SPEED, launched=True))


def test_kind_5_plays_an_effect_clears_the_PLAYERS_field_30_and_launches_nothing():
    """`clr.b 30(a0)` — on the record the CALLER handed in, not on the one being spawned, which is
    the one write in this routine that crosses from the scene's record back to the player's."""
    what = "player_run_map_cell kind 5"
    pokes = _trigger_pokes(what, KIND_SPAWN_5, fields={ACTOR + FIELD_30: bytes([MARKER])})
    image = harness.make_image(pokes)

    expected = _spawn_expected(image, TRIGGER_SPRITE_5, sfx=TRIGGER_SFX_2)
    expected[ACTOR + FIELD_30] = 0
    _run_cell(what, pokes, expected)


def test_kind_6_is_kind_5_with_NO_effect_and_no_write_to_the_player():
    """The quietest of the eight: four words, a sprite, a flicker bit and a visit."""
    what = "player_run_map_cell kind 6"
    pokes = _trigger_pokes(what, KIND_SPAWN_6, fields={ACTOR + FIELD_30: bytes([MARKER])})
    image = harness.make_image(pokes)

    _run_cell(what, pokes, _spawn_expected(image, TRIGGER_SPRITE_6))


@pytest.mark.parametrize("visits", [1, 2], ids=["last-visit", "one-to-spare"])
def test_the_visit_that_empties_the_counter_CLEARS_THE_MAP_CELL(visits):
    """`subq.w #1,(a1)+ / bne / clr.b (a6)` — the trigger fires a fixed number of times and then is
    not there any more, because the cell that selected it is gone. The `bne` reads what the
    subtraction left, so this is the counter's own value and not a separate flag."""
    what = f"player_run_map_cell kind 6 visits={visits}"
    pokes = _trigger_pokes(what, KIND_SPAWN_6,
                           fields={DESCRIPTOR + TRIGGER_VISITS: word(visits)})
    image = harness.make_image(pokes)

    _run_cell(what, pokes, _spawn_expected(image, TRIGGER_SPRITE_6, visits=visits))


@pytest.mark.parametrize("message,posted", [(0x0041, 0x41), (0x0000, None), (0x0100, 0x00),
                                            (0x1234, 0x34)],
                         ids=["ordinary", "zero", "high-byte-only", "both-bytes"])
def test_kind_3_primes_the_request_byte_and_then_posts_the_descriptors_LOW_byte(message, posted):
    """TWO defects reproduced rather than tidied. WB_TEXT_REQUEST is stamped
    WB_TEXT_REQUEST_PRIMED before the id is read, so a descriptor holding zero leaves that $ff
    standing and posts no lifetime at all; and the id is TESTED as a word and WRITTEN as its low
    byte, so $100 is "nonzero" and posts message 0. The cell is cleared on every path, which makes
    this the one arm that spends no visit and still fires exactly once."""
    what = f"player_run_map_cell kind 3 message={message:#06x}"
    pokes = _trigger_pokes(what, KIND_MESSAGE,
                           fields={DESCRIPTOR + TRIGGER_MESSAGE: word(message)})

    expected = _published({})
    expected[TEXT_REQUEST] = TEXT_REQUEST_PRIMED if posted is None else posted
    if posted is not None:
        _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    expected[CELL] = 0
    _run_cell(what, pokes, expected)


@pytest.mark.parametrize("supported,scancode", [(False, TRIGGER_BOSS_KEY), (True, 0),
                                                (True, TRIGGER_BOSS_KEY - 1)],
                         ids=["airborne", "no-key", "wrong-key"])
def test_kind_4_publishes_the_marker_cell_BEFORE_either_of_its_gates(supported, scancode):
    """`move.l a6,$e02e.l` is the arm's first instruction, so the scene tier is handed the cell
    address on every frame the player stands on one of these — whatever the two gates say."""
    what = f"player_run_map_cell kind 4 supported={supported} key={scancode:#04x}"
    flags = (1 << SUPPORTED_BIT) if supported else 0
    pokes = _trigger_pokes(what, KIND_BOSS_DEFEAT,
                           fields={ACTOR + ACTOR_FLAGS: bytes([flags]),
                                   KEY_LAST_SCANCODE: bytes([scancode])})

    expected = _published({}, republished=False)
    _put_long(expected, SCENE_MARKER_CELL_PTR, CELL)
    _run_cell(what, pokes, expected)


def test_kind_4_stops_the_music_and_raises_the_three_boss_handshake_words():
    """The whole arm, and it reaches the sound module TWICE — stub +28 to stop and stub +56 for the
    effect — so its write set is those two batteries' models plus the three words. The scancode it
    wants is WB_SCENE_TRIGGER_BOSS_KEY, which is the same $39 the tile ladder's last code is and a
    different thing entirely."""
    what = "player_run_map_cell kind 4 firing"
    pokes = _trigger_pokes(what, KIND_BOSS_DEFEAT,
                           fields={ACTOR + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                   KEY_LAST_SCANCODE: bytes([TRIGGER_BOSS_KEY])})
    image = harness.make_image(pokes)

    expected = _published({}, republished=False)
    _put_long(expected, SCENE_MARKER_CELL_PTR, CELL)
    expected.update(_flatten(STOP_WRITES))
    expected.update(_sfx_bytes(image, TRIGGER_BOSS_SFX, SND_CHANNEL_A))
    for flag_word in (STATE_FLAG_A34, PANEL_FRAME_HOLD, STAGE_ANIM_REQUEST_B0E):
        _put_word(expected, flag_word, TRIGGER_FLAG_SET)
    _run_cell(what, pokes, expected, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})


# --- kind 7, the hidden door, and kind 8, the flute that opens it -------------------------------------
# The two are ONE mechanism and the two words at $1960 are how they talk, which is why they are read
# together here: kind 8 raises WB_SCENE_FLUTE_PLAYED past a busy-wait no run reaches, and kind 7 is
# the only thing that ever reads it.

DOOR_X = 0x0200               # the descriptor's x, and where an aligned player is put
DOOR_OPEN_SEEDS = {DESCRIPTOR + TRIGGER_X: word(DOOR_X),
                   FOLLOWED_DEFAULT + ACTOR_X: word(DOOR_X),
                   FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT])}


def _door_pokes(what, *, armed, second, fields=None):
    """A frame at the door, with the two gate answers chosen and everything below them open."""
    seeds = dict(DOOR_OPEN_SEEDS)
    # THE GATE READS A BYTE AND THE ARM WRITES A WORD, so the armed value goes in the HIGH
    # half: `cmpi.b #$1,$bbc4.l` looks at $bbc4 itself, which `move.w #$ff,$bbc4.l` then
    # CLEARS — so opening the door disarms it, and the low byte is seeded apart from both.
    seeds[HUD_SLOT_BBC4] = bytes([HUD_SLOT_BBC4_ARMED if armed else MARKER, MARKER])
    seeds[DESCRIPTOR + TRIGGER_ALIGN_SUBKIND] = word(TRIGGER_ALIGN_SECOND if second else MARKER)
    seeds.update(fields or {})
    return _trigger_pokes(what, KIND_ALIGN, fields=seeds)


def _door_expected(x=DOOR_X):
    """The five words the door writes once it is through both gates, and the x it snaps."""
    expected = _published({}, republished=False)
    _put_word(expected, ACTOR + ACTOR_X, x)
    _put_word(expected, FLUTE_PLAYED, 0)
    _put_word(expected, HUD_SLOT_BBC4, HUD_SLOT_BBC4_SPENT)
    for flag_word in (SCROLL_FOLLOW_FROZEN, PANEL_FRAME_HOLD, ALIGN_REQUEST_B14):
        _put_word(expected, flag_word, TRIGGER_FLAG_SET)
    return expected


@pytest.mark.parametrize("armed,second,flute,opens", [
    (True, False, False, True),      # an armed slot admits a first-kind descriptor outright
    (True, False, True, True),       # ...flute or no flute, which is the `bne` at $1856
    (True, True, False, False),      # ...but a second-kind one still wants the flute
    (True, True, True, True),
    (False, False, False, False),    # ...and without the slot, a first-kind one never opens
    (False, False, True, False),     # — not even with the flute, which is the `bne` at $184a
    (False, True, True, True),
    (False, True, False, False),
], ids=["armed-first", "armed-first-flute", "armed-second-no-flute", "armed-second-flute",
        "unarmed-first", "unarmed-first-flute", "unarmed-second-flute", "unarmed-second-no-flute"])
def test_the_doors_two_gates_are_a_LATTICE_and_all_EIGHT_answers_agree(armed, second,
                                                                       flute, opens):
    """`cmpi.b #$1,$bbc4.l / beq` picks which pair of questions is asked and in which ORDER, and the
    `bra.s $183c` at $1860 sends the armed-second answer back into the other order's first question.
    So the predicate is (armed AND NOT second) OR (flute AND second) — all EIGHT combinations of the
    three inputs, because the two ways of reaching each answer are driven separately and a case that
    drove seven of eight would be naming a total it had not covered.

    A port that spelt the two orders as a CHAIN rather than as this disjunction passes four of these
    and fails `unarmed-first-flute`."""
    what = f"player_run_map_cell door armed={armed} second={second} flute={flute}"
    pokes = _door_pokes(what, armed=armed, second=second,
                        fields={FLUTE_PLAYED: word(FLUTE_PLAYED_SET if flute else 0)})

    _run_cell(what, pokes, _door_expected() if opens else _published({}, republished=False))


def test_an_AIRBORNE_followed_record_gets_no_door():
    """`btst #2,8(a2) / beq` — and the record tested is the FOLLOWED one, not the caller's a0."""
    what = "player_run_map_cell door airborne"
    pokes = _door_pokes(what, armed=True, second=False,
                        fields={FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([0])})

    _run_cell(what, pokes, _published({}, republished=False))


@pytest.mark.parametrize("offset", [-TRIGGER_ALIGN_REACH - 1, -TRIGGER_ALIGN_REACH, 0,
                                    TRIGGER_ALIGN_REACH, TRIGGER_ALIGN_REACH + 1],
                         ids=["short", "near-edge", "centre", "far-edge", "past"])
def test_the_doors_reach_window_is_INCLUSIVE_at_both_ends(offset):
    """`subq.w #4 / cmp.w (a2),d0 / bgt` then `addq.w #8 / cmp.w (a2),d0 / blt` — both branches are
    STRICT, so the followed record exactly WB_SCENE_TRIGGER_ALIGN_REACH either side is inside. The x
    written back is the descriptor's own, recovered by the third `subq.w`, so an aligned player is
    SNAPPED rather than left where he stood."""
    what = f"player_run_map_cell door offset={offset}"
    followed_x = (DOOR_X + offset) & WORD_MASK
    pokes = _door_pokes(what, armed=True, second=False,
                        fields={FOLLOWED_DEFAULT + ACTOR_X: word(followed_x)})

    inside = abs(offset) <= TRIGGER_ALIGN_REACH
    _run_cell(what, pokes, _door_expected() if inside else _published({}, republished=False))


@pytest.mark.parametrize("door_x", [0x8001, 0x7ffe], ids=["just-negative", "just-positive"])
def test_the_doors_window_arithmetic_WRAPS_in_sixteen_bits(door_x):
    """`subq.w #4` / `addq.w #8` / `subq.w #4` are WORD operations on a word register, and both
    compares under them read N^V. Drive the descriptor's x either side of the sign boundary with the
    followed record standing exactly ON it, and the two answers are opposite:

      * $8001 — `subq.w #4` wraps to $7ffd, and $7ffd > $8001 SIGNED, so `bgt` refuses a player who
        is standing on the very pixel the door names;
      * $7ffe — `subq.w #4` gives $7ffa, which is not greater than $7ffe, so the first compare
        passes; `addq.w #8` then wraps the probe to $8002, and $8002 < $7ffe SIGNED, so `blt`
        refuses him at the other end.

    A port that did the same arithmetic in `int32_t` opens the door on both rows. Every other case
    here keeps the window in the positive half, where the two readings agree."""
    what = f"player_run_map_cell door wrap x={door_x:#06x}"
    pokes = _door_pokes(what, armed=True, second=False,
                        fields={DESCRIPTOR + TRIGGER_X: word(door_x),
                                FOLLOWED_DEFAULT + ACTOR_X: word(door_x)})

    _run_cell(what, pokes, _published({}, republished=False))


def test_the_door_reads_the_FOLLOWED_records_x_and_writes_the_CALLERS():
    """The two records are the same one in the game and NOTHING HERE PROVES IT: the compare is
    `cmp.w (a2),d0` on WB_ACTOR_FOLLOWED_DEFAULT and the store is `move.w d0,(a0)` on the caller's.

    THE THREE X VALUES ARE ALL DIFFERENT, which is what makes the case non-vacuous: the followed
    record stands OFF-CENTRE but inside the window, the caller's record is somewhere else entirely,
    and the x that lands is the DESCRIPTOR's. A port that compared the caller's x refuses (his is
    far outside the window); one that wrote the followed record's x writes the off-centre value; one
    that wrote back to the followed record leaves the caller's untouched. Every other case here
    seeds the two records the same distance from the door, where all four ports agree.

    THE CALLER'S x IS THE BATTERY'S DEFAULT and is not moved, because moving it moves the CELL —
    the lookup at the top of the routine reads that same word, so a case that put the caller
    somewhere else would be standing on a different map byte and never reach this arm at all.
    PLAYER_X is already 0xc0 pixels outside the window, which is all this row needs."""
    what = "player_run_map_cell door two records"
    off_centre = DOOR_X + TRIGGER_ALIGN_REACH - 1
    pokes = _door_pokes(what, armed=True, second=False,
                        fields={FOLLOWED_DEFAULT + ACTOR_X: word(off_centre)})

    assert len({DOOR_X, off_centre, PLAYER_X}) == 3, "the three x values must differ"
    assert abs(PLAYER_X - DOOR_X) > TRIGGER_ALIGN_REACH, (
        "the caller's x must be OUTSIDE the window, or a port that measured it would still pass")
    _run_cell(what, pokes, _door_expected())


@pytest.mark.parametrize("sequence,second", [(LEVEL_SEQ_DOOR_A, False), (LEVEL_SEQ_DOOR_B, False),
                                             (LEVEL_SEQ_DOOR_A, True), (LEVEL_SEQ_DOOR_B, True),
                                             (LEVEL_SEQ_DOOR_A + 1, False),
                                             (LEVEL_SEQ_DOOR_A - 1, True)],
                         ids=["A-step", "B-step", "A-request", "B-request", "between", "below"])
def test_the_door_moves_the_level_sequence_on_from_exactly_TWO_points(sequence, second):
    """Two `cmpi.w`s, both EQUALITIES, so a sequence index one either side of either value gets a
    frozen scroll and a raised flag and nothing more. Past them the descriptor's sub-kind chooses:
    WB_SCENE_TRIGGER_ALIGN_SECOND raises WB_STAGE_ADVANCE_REQUEST, which player_pending_event_gate
    reads at $d06 and answers with THIS routine's own triple pop; anything else steps the index."""
    what = f"player_run_map_cell door sequence={sequence:#06x} second={second}"
    flute = second
    pokes = _door_pokes(what, armed=not second, second=second,
                        fields={LEVEL_SEQ_INDEX: word(sequence),
                                FLUTE_PLAYED: word(FLUTE_PLAYED_SET if flute else 0)})

    expected = _door_expected()
    if sequence in (LEVEL_SEQ_DOOR_A, LEVEL_SEQ_DOOR_B):
        if second:
            _put_word(expected, STAGE_ADVANCE_REQUEST, STAGE_ADVANCE_REQUEST_SET)
        else:
            _put_word(expected, LEVEL_SEQ_INDEX, sequence + LEVEL_SEQ_DOOR_STEP)
    _run_cell(what, pokes, expected)


def test_the_doors_LAST_question_is_re_read_AFTER_the_snap_store():
    """`cmpi.w #$2,6(a1)` is asked THREE times — at $184a, at $1856 and again at $18ce — and the
    third is BELOW the `move.w d0,(a0)` that snaps the player's x. So a port that reads the
    descriptor's sub-kind once and caches it answers the third question with a word the store may
    already have replaced. It is the read-after-store class batch 32 found at `snd_channel_step`'s
    $18036, one routine over.

    THE ALIAS IS SEEDABLE, which is what makes this a differential and not a note: a0 is the
    CALLER's record and nothing bounds it, so a case that aims it at the descriptor's own +8 word
    makes the snap store overwrite the very word $18ce re-reads. Here the record's x IS the
    sub-kind: seeded WB_SCENE_TRIGGER_ALIGN_SECOND on entry, so the door opens through the flute
    arm — and overwritten with the door's x by the snap, so the re-read finds something else and the
    original STEPS WB_LEVEL_SEQ_INDEX where a cached port raises WB_STAGE_ADVANCE_REQUEST. Two
    different words, so the write sets part.

    No shipped frame does this — the player's record is in the actor table and the descriptors are
    loaded from disk above $21828 — which is why the arm is driven rather than argued about."""
    what = "player_run_map_cell door re-read after the snap"
    record = DESCRIPTOR + TRIGGER_ALIGN_SUBKIND        # a0, aimed at the word $18ce re-reads
    entry_x = TRIGGER_ALIGN_SECOND                     # ...which is therefore the record's x, too
    entry_y = 0x0088
    door_x = 0x0200

    pokes = _cell_pokes(what, TRIGGER_CELL_CODE, record=record, x=entry_x, y=entry_y,
                        # THE ALIAS MEANS THE RECORD'S x AND THE SUB-KIND ARE ONE ADDRESS, and
                        # `_cell_pokes` writes the descriptor's own words AFTER the record's — so
                        # the entry value has to come from the LAST layer or the spawn seed wins.
                        # It failed exactly that way TWICE: the record's x aliases the sub-kind and
                        # its y aliases the VISIT COUNTER, and the first draft seeded neither from
                        # the last layer, so the cell lookup landed elsewhere and the run took the
                        # tile-flag arm. Kind 7 spends no visit, so that word is free to be a y.
                        fields={DESCRIPTOR + TRIGGER_ALIGN_SUBKIND: word(entry_x),
                                DESCRIPTOR + TRIGGER_VISITS: word(entry_y),
                                DESCRIPTOR + TRIGGER_KIND: word(KIND_ALIGN),
                                DESCRIPTOR + TRIGGER_X: word(door_x),
                                FOLLOWED_DEFAULT + ACTOR_X: word(door_x),
                                FOLLOWED_DEFAULT + ACTOR_FLAGS: bytes([1 << SUPPORTED_BIT]),
                                FLUTE_PLAYED: word(FLUTE_PLAYED_SET),
                                LEVEL_SEQ_INDEX: word(LEVEL_SEQ_DOOR_A)})

    assert door_x != TRIGGER_ALIGN_SECOND, "the snap must CHANGE the word the third question reads"
    expected = _published({}, republished=False)
    _put_word(expected, record + ACTOR_X, door_x)      # the snap, onto the descriptor's own +8
    _put_word(expected, FLUTE_PLAYED, 0)
    _put_word(expected, HUD_SLOT_BBC4, HUD_SLOT_BBC4_SPENT)
    for flag_word in (SCROLL_FOLLOW_FROZEN, PANEL_FRAME_HOLD, ALIGN_REQUEST_B14):
        _put_word(expected, flag_word, TRIGGER_FLAG_SET)
    # the RE-READ answers "not the second sub-kind" now, so the sequence STEPS
    _put_word(expected, LEVEL_SEQ_INDEX, LEVEL_SEQ_DOOR_A + LEVEL_SEQ_DOOR_STEP)
    _run_cell(what, pokes, expected, record=record)


@pytest.mark.parametrize("y", [TRIGGER_TUNE_MAX_Y, TRIGGER_TUNE_MAX_Y + 1, 0x7fff],
                         ids=["exact", "one-below", "largest-positive"])
def test_kind_8_is_the_one_arm_that_reads_the_players_own_position(y):
    """`cmpi.w #$64,2(a0) / blt` — a STRICT compare, so a record exactly at
    WB_SCENE_TRIGGER_TUNE_MAX_Y is already too low. Nothing is written, not even the pointer copy.
    That it is also a SIGNED one is the case below; these three rows cannot tell."""
    what = f"player_run_map_cell kind 8 y={y:#06x}"
    pokes = _trigger_pokes(what, KIND_TUNE, y=y)

    _run_cell(what, pokes, _published({}, republished=False))


def _tune_expected(y, message):
    """What every arm of kind 8 that gets past the y gate writes: the pointer republished, the cell
    at the record's OWN position consumed, and a message posted. The `y` is a parameter because the
    cell follows the record — three cases spelt these four lines with two different y's before this
    helper, and the one that got it wrong would have looked like a port bug."""
    expected = _published({})
    expected[_cell_for(PLAYER_X, y)] = 0
    expected[TEXT_REQUEST] = message
    _put_word(expected, TEXT_LIFETIME_REQUEST, TEXT_LIFETIME_DEFAULT)
    return expected


def test_kind_8s_y_gate_is_SIGNED_and_only_a_negative_y_says_so():
    """`blt` reads N^V, so a record ABOVE the top of the screen runs the arm. Every y the case above
    drives is positive, where a `bcs` would answer identically; this one is $ff9c, and an unsigned
    port returns having written nothing where the original republishes the pointer, consumes the
    cell and posts a message."""
    what = "player_run_map_cell kind 8 negative y"
    above_the_screen = 0xff9c
    pokes = _trigger_pokes(what, KIND_TUNE, y=above_the_screen,
                           fields={HUD_SLOT_BBC8: bytes([MARKER])})

    _run_cell(what, pokes, _tune_expected(above_the_screen, MESSAGE_NICE_VIEW))


@pytest.mark.parametrize("held", [0, HUD_SLOT_BBC8_FLUTE + 1, 0xff],
                         ids=["nothing", "wrong-item", "all-ones"])
def test_kind_8_without_the_flute_reads_the_view(held):
    """`cmpi.b #$2,$bbc8.l / bne` — the item the player is holding, as a BYTE. Message
    WB_TEXT_MESSAGE_NICE_VIEW, and the cell is consumed either way, so the view is read once."""
    what = f"player_run_map_cell kind 8 holding={held:#04x}"
    pokes = _trigger_pokes(what, KIND_TUNE, y=TRIGGER_TUNE_MAX_Y - 1,
                           fields={HUD_SLOT_BBC8: bytes([held])})

    _run_cell(what, pokes, _tune_expected(TRIGGER_TUNE_MAX_Y - 1, MESSAGE_NICE_VIEW))


def test_kind_8_with_the_flute_plays_the_song_and_STOPS_AT_THE_BUSY_WAIT():
    """WB_PLAYER_COLLIDE_SOUND_WAIT, and this is the case the whole convention exists for. The
    oracle is stopped at the `tst.b 378(a5)` itself, so what is compared is the whole image at the
    instant the spin is entered: the message, the lifetime, the consumed cell and snd_play_song's
    entire write set. The witness is the `jsr (a5)` at $192a, without which the case would pass on a
    run that took the view arm instead."""
    what = "player_run_map_cell kind 8 flute"
    pokes = _trigger_pokes(what, KIND_TUNE, y=TRIGGER_TUNE_MAX_Y - 1,
                           fields={HUD_SLOT_BBC8: bytes([HUD_SLOT_BBC8_FLUTE])})
    image = harness.make_image(pokes)

    expected = _tune_expected(TRIGGER_TUNE_MAX_Y - 1, MESSAGE_PLAYED_FLUTE)
    expected.update(_flatten(model_play_song(image, TRIGGER_FLUTE_SONG)))
    _run_cell(what, pokes, expected, exit_code=EXIT_SOUND_WAIT, stop_pc=SOUND_WAIT_SITE,
              via=SOUND_WAIT_TAKEN_AT, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})


def test_the_busy_wait_can_NEVER_be_entered_with_its_byte_clear():
    """WHY THE SIX INSTRUCTIONS BELOW THE SPIN ARE NOT PORTED, and it is a MEASUREMENT OF THE
    ORIGINAL rather than a claim in a comment or a reading of this port's model.

    The `jsr (a5)` three instructions above the `tst.b` is snd_play_song. This runs THAT ROUTINE'S
    OWN 68000 CODE under the oracle, on an image whose WB_SND_ENGINE_ENABLED byte is seeded CLEAR,
    and requires the byte to come back set — which is the whole of the argument that the spin at
    $1932 is entered on every run whatever a case seeds. Nothing in `src/` is consulted, so a port
    that stopped raising the byte would not hide this.

    The day it fails is the day $1938..$194d becomes reachable and has to be ported."""
    seeded = harness.make_image(_cell_pokes("busy-wait premise", TRIGGER_CELL_CODE,
                                            fields={SND_ENGINE_ENABLED: bytes([0])}))
    assert seeded[SND_ENGINE_ENABLED] == 0, "the premise needs the byte seeded CLEAR to be a test"

    after, _, _ = emu.run(seeded, leaf.entry_of("snd_play_song"), {"d0": TRIGGER_FLUTE_SONG},
                          max_insns=PLAY_SONG_INSN_CAP,
                          psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    assert after[SND_ENGINE_ENABLED] != 0, (
        "the ORIGINAL snd_play_song no longer leaves WB_SND_ENGINE_ENABLED set, so the busy-wait at "
        f"{SOUND_WAIT_SITE:#x} is now enterable with it clear and the six instructions below it "
        "have become reachable — port them, and retire WB_PLAYER_COLLIDE_SOUND_WAIT's reasoning")

    # ...and the instruction that does it is the LAST one the routine executes, which is what makes
    # the raise unconditional rather than one arm's. Read off the image, not off the model.
    assert bytes(harness.BASE_IMAGE[SOUND_WAIT_SITE:SOUND_WAIT_SITE + WORD_BYTES]) \
        == tst_b_d16(A5, SND_ENGINE_ENABLED - STUB_TABLE_BASE)[:WORD_BYTES], (
            f"{SOUND_WAIT_SITE:#x} is not the `tst.b` this convention is about")


def test_the_two_handshake_words_are_DATA_INSIDE_this_routines_own_body():
    """$1960 and $1962 lie between the `rts` at $195e and kind 4's entry at $1964, which is why a
    linear sweep renders them as an instruction. Both are zero in the shipped image, and both lie
    inside the extent BODY_SIZES pins — so the pin covering 1,170 bytes is what says they are the
    routine's own and not a neighbour's."""
    entry = leaf.entry_of("player_run_map_cell")
    assert entry < FLUTE_PLAYED < STAGE_ADVANCE_REQUEST < entry + BODY_SIZES["player_run_map_cell"]
    assert STAGE_ADVANCE_REQUEST == FLUTE_PLAYED + WORD_BYTES
    assert bytes(harness.BASE_IMAGE[FLUTE_PLAYED:FLUTE_PLAYED + 2 * WORD_BYTES]) == bytes(4)


@pytest.mark.parametrize("name,text", [("TEXT_MESSAGE_PLAYED_FLUTE", b"flute"),
                                       ("TEXT_MESSAGE_NICE_VIEW", b"nice view")])
def test_the_messages_kind_8_posts_are_the_ones_the_shipped_strings_name(name, text):
    """What NAMES the flute and the view: the two ids are read out of the image's own message table,
    exactly as the wing boots' and the revival medicine's are above."""
    assert text in _shipped_message_text(wb(name)).lower()


# Every descriptor offset this project has more than one NAME for, and what each name reads it as.
# include/wonderboy.h's own rule is that a second name for one offset is only safe if a case PINS the
# two against each other — the scraper reads plain literals and cannot derive one #define from
# another — and until batch 41 phase A only the +2 pair was pinned. These are the three groups.
DESCRIPTOR_OFFSET_ALIASES = {
    2: ("SCENE_KIND", "SCENE_TRIGGER_X", "SCENE_TRIGGER_MESSAGE", "EVENT_PAIR_POSITION"),
    4: ("SCENE_VARIANT", "SCENE_TRIGGER_SPAWN_Y"),
    8: ("SCENE_TRIGGER_SPAWN_FIELD", "SCENE_TRIGGER_ALIGN_SUBKIND"),
}


@pytest.mark.parametrize("offset,names", sorted(DESCRIPTOR_OFFSET_ALIASES.items()),
                         ids=lambda v: str(v))
def test_every_descriptor_offset_with_more_than_one_NAME_is_pinned_to_one_number(offset, names):
    """ONE offset, several readings, pinned against each other rather than left as numbers that
    could drift apart. +2 is the scene driver's KIND word, the spawning kinds' x and kind 3's
    message id — and, since batch 41 phase C, the gate's event pair, which takes +2 and +4 as ONE
    longword; +4 is the fragment selector and the spawn's y; +8 is the spawning kinds' fourth
    copied word and the door's sub-kind. A later batch that re-derives the descriptor's layout and
    moves one name leaves the others behind, and both `src/scene.c` and `src/player.c` then read
    different words off one record with every battery green — which is exactly what this case is
    for."""
    for name in names:
        assert wb(name) == offset, (
            f"{name} is {wb(name):#x}, not the {offset:#x} the other names for this descriptor word "
            f"use ({', '.join(names)})")


# ==================================================================================================
# $b1a — THE PENDING-EVENT GATE, and the frame it decides
# ==================================================================================================
#
# WHAT SHAPES THIS PART OF THE BATTERY, and it is not what shaped the eight above it.
#
#   * THE OUTPUT IS A REGISTER. Every other routine here is entered for its memory; this one is
#     entered so that $a38 can read `tst.w d7`. The reconstruction returns an EXIT CODE instead
#     (include/player.h), so every case below enters with a known d7 and `_assert_d7` says what the
#     ORIGINAL's whole 32 bits should be given the code — which is how the difference between
#     `clr.l d7` and `move.w #$ffff,d7` gets pinned at all.
#   * THE SHARED TAIL IS A CALL, and twelve of the routine's branches reach it. Every case that does
#     not want `player_stage_transition`'s writes in its model seeds WB_STAGE_ANIM_DONE_B10 —
#     that routine's own FIRST instruction is `tst.w $b10.w`, so a raised latch makes all 656 bytes
#     of it an `rts`. The one case that must run it with the latch DOWN models what it writes.
#   * THREE ENDINGS ARE STACK UNWINDS and a fourth is a callee that never comes back, so four of the
#     cases are checkpointed runs with a witness above the checkpoint (README.md's convention).
#   * THE DRIFT TABLE IS SEEDED, keyed, with a margin on both sides: the ascent indexes
#     WB_ACTOR_TYPE30_DRIFT with the RAW cursor word, so a case can drive an index outside the 32
#     entries and the byte it lands on has to be wrong FOR WHERE IT CAME FROM.

_GATE = leaf.register_glue("player_pending_event_gate", [ctypes.c_uint32], ctypes.c_uint32)

# The restart unwind CALLS `game_life_restart_reset`, so its seeding and its write-set model come
# from the battery that owns that routine — a second model here could drift from src/stage.c while
# both stayed green.
from test_stage import GAME_RESET_INSN_CAP, _life_reset_writes, _reset_pokes   # noqa: E402

GATE_EXIT_RUNS = wb("PLAYER_GATE_FRAME_RUNS")
GATE_EXIT_SKIPPED = wb("PLAYER_GATE_FRAME_SKIPPED")
GATE_EXIT_DATADISK = wb("PLAYER_GATE_DATADISK_UNWIND")
GATE_EXIT_RESTART = wb("PLAYER_GATE_RESTART_UNWIND")
GATE_EXIT_SCENE_LEFT = wb("PLAYER_GATE_SCENE_LEFT")

# The four checkpoints and the instruction each one needs to have seen. THE WITNESS LIES ABOVE THE
# CHECKPOINT in every case, because `emu.run` stops BEFORE marking the checkpoint's own PC.
GATE_DATADISK_SITE = 0xbdc         # `jmp $e494.l`
GATE_DATADISK_TAKEN_AT = 0xbd8     # ...witnessed by the `lea 4(a7),a7`, which no other path runs
GATE_RESTART_SITE = 0xc20          # `jmp $e5ba.l`
GATE_RESTART_TAKEN_AT = 0xc1c      # ...and its own `lea 4(a7),a7`
GATE_COLLIDE_TAKEN_AT = 0xd16      # `bra.w $1622` — the checkpoint is $151a's own UNWIND_SITE
GATE_SCENE_LEFT_SITE = 0x19e0      # `scene_spawn_from_script`'s wild-return `rts`
GATE_SCENE_CALL_AT = 0xc66         # ...witnessed by the `bsr.w $19ac` only this arm executes
GATE_TAIL_CALL_AT = 0xbb0          # `bsr.w $1f54` — what the two arms that end at $d22 do NOT run

# d7 on entry: a value with BOTH halves nonzero, so `clr.l` and `move.w` are distinguishable and the
# high half a preserved write leaves behind is not a zero that anything else could have produced.
D7_ENTRY = 0x1234abcd
# ...and the endings whose d7 the case may state. The two that call something on the way out may not:
# `game_life_restart_reset` and `scene_spawn_from_script` are free to clobber a scratch register and
# nothing reads d7 on those paths anyway, since the frame they belong to is abandoned.
GATE_D7_STATED = frozenset({GATE_EXIT_RUNS, GATE_EXIT_SKIPPED, GATE_EXIT_DATADISK, EXIT_UNWIND})

# The drift table with a margin either side, so an index outside its 32 words lands on a keyed byte.
# THE MARGIN IS DERIVED FROM THE CURSORS THE CASES DRIVE, not chosen: the largest positive index any
# row uses must still be inside the band, or that row's "it lands on a keyed byte" is decoration and
# the expected value is read from the same unseeded bytes the run reads. `leaf.assert_bands_are_
# seeded` cannot catch that — it only checks the bands a case DECLARES — so the bound is asserted
# below instead.
# It is STATED and not derived from `DRIFT_CURSORS`: a tripwire that measured the band with the very
# constant it seeds from cannot fail, which is the lesson batch 40 phase C's dropped keyed band left.
DRIFT_MARGIN = 0x48
DRIFT_BAND_LO = TYPE30_DRIFT - DRIFT_MARGIN
DRIFT_BAND_LEN = 2 * DRIFT_MARGIN + (TYPE30_DRIFT_MASK + 1)
# Where a case puts the scene descriptor the third arm's pair is positioned from: an ordinary slot,
# well clear of the two the arm fills AND of the FOLLOWED record. Slot 12 is `WB_ACTOR_FOLLOWED_
# DEFAULT`, which the shared tail and half the behaviour tier read, so a descriptor placed there
# would double as that record and the isolation this constant is for would be gone; the assertion
# below is what keeps the two apart as either address moves.
GATE_DESCRIPTOR_SLOT = 9
GATE_DESCRIPTOR = TABLE_DEFAULT + GATE_DESCRIPTOR_SLOT * RECORD_BYTES
GATE_DESCRIPTOR_BAND = (GATE_DESCRIPTOR - RECORD_BYTES, 3 * RECORD_BYTES)
# ...and the two records it fills, with a margin, so a store one field out is visible.
EVENT_PAIR_BAND = (TABLE_DEFAULT - RECORD_BYTES, 3 * RECORD_BYTES)

# Where the dying player starts: both coordinates well away from zero, so a drift of zero and a
# rise of one are still changes the ledger can see.
ASCENT_X, ASCENT_Y = 0x0140, 0x0070

PENDING_GATE_CAP = _cap("player_pending_event_gate",
                        extra=INSN_COUNT["player_stage_transition"]
                        + INSN_COUNT["scene_copy_record_fields"]
                        + STUB_INSN_CAP + STOP_INSN_CAP)


def _gate_pokes(what, fields=None, descriptor=GATE_DESCRIPTOR):
    """A frame in which nothing is pending, so a case raises exactly the flag its arm is about.

    THE KEYED BANDS ARE THEIR OWN LAYER, `leaf.overlay`'s documented hazard: WB_DEATH_DRIFT_CURSOR
    and the two records the third arm fills all lie INSIDE one, so a single dict literal holding both
    would drop the block and every case would run on the .PRG's own bytes."""
    salt = case_salt(what)
    keyed = {lo: keyed_block(lo, length, salt)
             for lo, length in ((DRIFT_BAND_LO, DRIFT_BAND_LEN), GATE_DESCRIPTOR_BAND,
                                EVENT_PAIR_BAND)}
    base = {
        # the three flags the head tests, and the five latches the arms read, all DOWN
        STAGE_RESET_BLOCK: word(0), DEATH_MESSAGE_POSTED_B0A: word(0),
        DEATH_BOX_EXPIRED_B0C: word(0), STAGE_ANIM_REQUEST_B0E: word(0),
        EVENT_ANIM_DONE_B12: word(0), ALIGN_REQUEST_B14: word(0),
        EVENT_ANIM_DONE_B16: word(0), STAGE_ANIM_DONE_B18: word(0),
        # ...and the ONE latch raised by default, which is what makes the shared tail an `rts`
        STAGE_ANIM_DONE_B10: word(MARKER),
        # the inputs each arm reads
        SCROLL_FOLLOW_Y: word(0), LIVES: word(0), TEXT_BOX_ACTIVE: bytes([0]),
        JOY1_STATE: bytes([0]), DEATH_DRIFT_CURSOR: word(0),
        STAGE_ADVANCE_REQUEST: word(0),
        SPAWN_GATE_SLOT + ACTOR_X: word(ACTOR_FREE_MARKER),
        RECORD_PTR_10420: longword(descriptor),
        # ...and every global an arm can WRITE, seeded to a value no arm produces
        STATE_FLAG_A34: word(MARKER), LIFE_RESTART_ENTRY_C26: word(MARKER),
        EVENT_FINISHED_E1BE: word(MARKER), LEVEL_SEQ_INDEX: word(MARKER),
        EFFECT_STATE_21E4: word(MARKER),
    }
    seeded = _pokes(what, leaf.overlay(keyed, base, fields or {}))
    leaf.assert_bands_are_seeded(seeded, [(DRIFT_BAND_LO, DRIFT_BAND_LEN), GATE_DESCRIPTOR_BAND,
                                          EVENT_PAIR_BAND],
                                 f"{what}: a keyed band was dropped")
    return seeded


def _gate_body_layer():
    """The gate's own 526 bytes, put back from the shipped image.

    A COMPOSED CASE HAS TO RE-PLANT THEM, and this cost a debugging session: WB_LIVES is DATA INSIDE
    THIS ROUTINE'S CODE ($be2, between the data-disk `jmp` and the `tst.w` at $be4), and
    test_stage.py's reset seeding keys a BAND AROUND every word it resets — so overlaying that
    battery's seeds writes keyed bytes over the instructions at $be4 and the run walks off into them.
    The layer goes between the imported seeds and the case's own words, so both still land."""
    lo = leaf.entry_of("player_pending_event_gate")
    hi = lo + BODY_SIZES["player_pending_event_gate"]
    return {lo: bytes(harness.BASE_IMAGE[lo:hi])}


def _assert_the_tail_would_be_visible(pokes, what, after=None, record=ACTOR):
    """A PREMISE GUARD ON THE SEED for the two cases whose claim is "the shared tail did NOT run".

    `emu.cov_visited` watches the ORACLE's executed PCs, so "$bb0 was not reached" is a statement
    about the original and can never see a C-side change. What makes those cases pin the PORT is that
    the tail WRITES SOMETHING under their seeding — then a reconstruction that called it anyway
    reddens on the write set. That is a property of the seed, and it is decided by keyed bytes
    (`case_salt`), so renaming a case could silently take it away: the mutation sweep's
    `align-refusal-gets-the-tail` survivor was exactly that hole with `WB_STAGE_ANIM_DONE_B10` up.

    So the premise is a run, not a comment: `player_stage_transition` is entered on THIS case's own
    image and required to write. ``after`` is what the arm has already written by the point the tail
    WOULD have been called — the no-advance ending takes two flag words down first, and the premise
    has to be asked about the state at the call site rather than at the entry."""
    seeds = leaf.overlay(pokes, after or {})
    info = leaf.run("player_stage_transition", _STAGE_TRANSITION(record), [(0, loader.PROGRAM_END)],
                    f"{what}: the tail's own run",
                    regs={"a0": record, "_pokes": seeds}, max_insns=STAGE_TRANSITION_CAP)
    assert program_writes(info), (
        f"{what}: `player_stage_transition` writes NOTHING under this case's seeding, so \"the arm "
        f"did not call it\" is a claim about the original's control flow and not about this port")


def _assert_d7(info, exit_code, what, d7_high=D7_ENTRY & ~WORD_MASK):
    """What the ORIGINAL leaves in d7 — the only output $a38 reads, and the one the exit code stands
    in for. The two returning endings differ in the HALF THE CALLER DOES NOT LOOK AT, which is why
    the whole 32 bits are compared and not `& 0xffff`.

    `d7_high` is what the entry half is worth BY THE TIME the answer is written. It is the entry
    value on every arm that calls nothing but `player_stage_transition`, and a case whose arm calls
    something that CLOBBERS a scratch register says so: `scene_spawn_from_script` leaves the high
    half zero, which the gate cannot help and the caller never notices, since `tst.w d7` reads the
    low word alone."""
    if exit_code not in GATE_D7_STATED:
        return
    if exit_code == GATE_EXIT_RUNS:
        expected = 0                                              # `clr.l d7` at $b32
    elif exit_code == GATE_EXIT_SKIPPED:
        expected = d7_high | GATE_FLAG_SET                        # `move.w #$ffff,d7`
    else:
        expected = D7_ENTRY                                       # an unwind writes no register
    assert info["regs"]["d7"] == expected, (
        f"{what}: the ORIGINAL left d7={info['regs']['d7']:#010x}, not the {expected:#010x} exit "
        f"code {exit_code} says it should")


def _run_gate(what, pokes, expected, exit_code=GATE_EXIT_SKIPPED, stop_pc=0, via=None,
              psg_seed=None, extra_band=(), record=ACTOR, cap=None, poison=True,
              self_checked=frozenset(), d7_high=D7_ENTRY & ~WORD_MASK):
    """Every gate case's runner. `via` is the transfer a checkpointed run must have executed, which
    is what stops a `stop_pc` case passing on a run that simply returned. `self_checked` is the band
    a COMPOSED case leaves to the battery that owns the callee — the two arms that run the spawn tree
    are its only users, and the byte-for-byte diff still covers every byte of it."""
    how = dict(regs={"a0": record, "d7": D7_ENTRY, "_pokes": pokes},
               max_insns=PENDING_GATE_CAP if cap is None else cap,
               stop_pc=stop_pc, psg_seed=psg_seed, poison=poison)
    bands = merge_bands(expected) + list(extra_band)
    if via is None:
        info = leaf.run("player_pending_event_gate", _GATE(record), bands, what, **how)
    else:
        info = leaf.run_reaching("player_pending_event_gate", _GATE(record), bands, what, via, **how)
    _assert_writes(info, expected, what, extra=self_checked)
    assert info["ret"] == exit_code, (
        f"{what}: the reconstruction reported {info['ret']}, not the {exit_code} this case expects")
    _assert_d7(info, exit_code, what, d7_high)
    return info


def _run_gate_claiming_tail_not_reached(what, pokes, expected, after=None, **how):
    """`_run_gate`, for the two cases whose claim is that the shared tail did NOT run — PREMISE AND
    CLAIM IN ONE CALL, so that a case cannot carry one without the other.

    `emu.cov_visited` watches the ORACLE's executed PCs, so "$bb0 was not reached" is a statement
    about the original and can never see a C-side change. What makes these cases pin the PORT is that
    the tail WRITES SOMETHING under their seeding — then a reconstruction that called it anyway
    reddens on the write set. That is a property of the SEED, decided by `case_salt` keyed bytes, and
    the mutation sweep's `align-refusal-gets-the-tail` survivor was exactly that premise going
    missing with `WB_STAGE_ANIM_DONE_B10` up. Splitting the two into a helper call plus a
    `pc_coverage` block is what let it go missing, so they are one entry point now.

    ``after`` is what the arm has already written by the point the tail WOULD be called — the
    no-advance ending takes two flag words down first, so the premise has to be asked about the state
    at the call site rather than at the entry."""
    _assert_the_tail_would_be_visible(pokes, what, after=after)
    with leaf.pc_coverage():
        info = _run_gate(what, pokes, expected, **how)
        assert not emu.cov_visited(GATE_TAIL_CALL_AT), (
            f"{what}: the arm reached the shared tail at {GATE_TAIL_CALL_AT:#x}, which it does not "
            f"have — and the premise above says the tail would have written if it had")
    return info


# --- the head: three flags, in one order --------------------------------------------------------

def test_no_pending_event_clears_the_WHOLE_of_d7_and_writes_nothing():
    """`clr.l d7 / rts` at $b32, which is the answer that lets the other seven calls of the frame
    run. It is the only ending that touches d7's high half, and the only one that writes no byte at
    all — the shared tail is not even reached, so `player_stage_transition` does not run."""
    what = "player_pending_event_gate idle"
    _run_gate(what, _gate_pokes(what), {}, exit_code=GATE_EXIT_RUNS)


GATE_HEAD_FLAGS = [("death", STAGE_RESET_BLOCK), ("stage-anim", STAGE_ANIM_REQUEST_B0E),
                   ("align", ALIGN_REQUEST_B14)]


@pytest.mark.parametrize("name,flag", GATE_HEAD_FLAGS, ids=[c[0] for c in GATE_HEAD_FLAGS])
def test_any_one_of_the_three_flags_ends_the_frame_for_everything_below_the_gate(name, flag):
    """Each raised ALONE, with every latch below it seeded so its arm does nothing: the answer is
    WB_PLAYER_GATE_FRAME_SKIPPED either way, and $a38's `bmi.w $a74` then skips seven calls.

    The align arm is the one that writes nothing on this row for a different reason from the other
    two — its slot-not-free refusal goes to $d22, which has no `bsr.w $1f54` above it."""
    what = f"player_pending_event_gate head {name}"
    # Both spawning arms are closed by a slot that is not free, which is the cheapest way to make
    # each arm do nothing — and the two refusals are NOT the same ending, which the align arm's own
    # case below is about.
    fields = {flag: word(MARKER), SPAWN_GATE_SLOT + ACTOR_X: word(MARKER)}
    if flag == STAGE_RESET_BLOCK:
        # The death arm needs its ascent already topped out to do nothing else, which is the state
        # `_prompt_pokes` below builds — spelt here rather than called because that helper seeds the
        # THREE flags itself and this row is about raising exactly ONE of them. The three keys are
        # the same three, and this is the box-down frame, so the box-expired latch is the one write.
        fields[DEATH_MESSAGE_POSTED_B0A] = word(MARKER)
        fields[DEATH_BOX_EXPIRED_B0C] = word(0)
        fields[TEXT_BOX_ACTIVE] = bytes([0])
    pokes = _gate_pokes(what, fields)
    expected = {}
    if flag == STAGE_RESET_BLOCK:
        _put_word(expected, DEATH_BOX_EXPIRED_B0C, GATE_FLAG_SET)
    _run_gate(what, pokes, expected)


def test_the_three_flags_are_tested_in_the_order_the_block_holds_them():
    """All three raised at once: the DEATH arm runs and the other two do not, which is what the
    order at $b1a..$b2e says. Read off the write set — only the death arm posts a message."""
    what = "player_pending_event_gate all three raised"
    pokes = _gate_pokes(what, {STAGE_RESET_BLOCK: word(MARKER),
                               STAGE_ANIM_REQUEST_B0E: word(MARKER),
                               ALIGN_REQUEST_B14: word(MARKER),
                               SCROLL_FOLLOW_Y: word(DEATH_ASCENT_TOP_Y)})
    expected = {}
    _put_word(expected, STATE_FLAG_A34, STATE_FLAG_SET)
    _put_word(expected, DEATH_MESSAGE_POSTED_B0A, GATE_FLAG_SET)
    expected[TEXT_REQUEST] = MESSAGE_GAME_OVER
    _put_word(expected, TEXT_LIFETIME_REQUEST, DEATH_MESSAGE_LIFETIME)
    _run_gate(what, pokes, expected)


def test_the_SECOND_flag_is_tested_before_the_THIRD():
    """The case above pins only that $b08 comes first, because the death arm is unmistakable. This
    one separates the other two, whose arms are otherwise easy to confuse: both spawn into
    WB_SCENE_SPAWN_GATE_SLOT off WB_RECORD_PTR_10420 and both refuse a slot that is not free. With
    both flags raised the STAGE arm runs, and what says so is that the slot is filled from
    WB_ACTOR_TYPE35_TEMPLATE rather than with the align arm's hard-coded pair."""
    what = "player_pending_event_gate stage before align"
    pokes = _gate_pokes(what, {STAGE_ANIM_REQUEST_B0E: word(MARKER),
                               ALIGN_REQUEST_B14: word(MARKER)})
    image = harness.make_image(pokes)

    expected = _record_copy_writes(image, SPAWN_GATE_SLOT, GATE_DESCRIPTOR, TYPE35_TEMPLATE,
                                   into=_sfx_bytes(image, EVENT_SPAWN_SFX, SND_CHANNEL_A))
    _run_gate(what, pokes, expected, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})


# --- $b36: the death arm's ascent ---------------------------------------------------------------

def _drift_at(image, cursor):
    """The word the ascent reads, indexed the way the original does: the RAW cursor, sign-extended,
    off WB_ACTOR_TYPE30_DRIFT and NOT masked first."""
    at = (TYPE30_DRIFT + leaf.s16(cursor)) & wb("BUS_ADDR_MASK")
    return int.from_bytes(image[at:at + WORD_BYTES], "big")


# 0 and the last in-table index, the one that wraps, one PAST the table and one BELOW it.
DRIFT_CURSORS = [0, 2, TYPE30_DRIFT_MASK - 1, TYPE30_DRIFT_MASK + 1, 0x80, 0xfffe]


@pytest.mark.parametrize("cursor", DRIFT_CURSORS, ids=lambda v: f"cursor{v:#06x}")
def test_the_dying_player_rises_one_pixel_and_sways_by_the_RAW_cursors_word(cursor):
    """$b7a: `subq.w #1,2(a0)` then the drift added to (a0), and the cursor stepped and masked ONLY
    on the way back to memory. The last three rows are what says the mask is on the STORE: an index
    of $40, $80 or $fffe reads outside the 32 words the table has, and lands on a keyed byte that is
    wrong for anywhere else it could have come from."""
    what = f"player_pending_event_gate ascent cursor={cursor:#06x}"
    pokes = _gate_pokes(what, {STAGE_RESET_BLOCK: word(MARKER),
                               DEATH_DRIFT_CURSOR: word(cursor),
                               ACTOR + ACTOR_X: word(ASCENT_X), ACTOR + ACTOR_Y: word(ASCENT_Y)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, ACTOR + ACTOR_Y, ASCENT_Y - DEATH_ASCENT_RISE)
    _put_word(expected, ACTOR + ACTOR_X, (ASCENT_X + _drift_at(image, cursor)) & WORD_MASK)
    _put_word(expected, DEATH_DRIFT_CURSOR,
              (cursor + TYPE30_DRIFT_STRIDE) & TYPE30_DRIFT_MASK)
    _run_gate(what, pokes, expected)


def test_the_seeding_this_section_rests_on_covers_what_its_cases_actually_READ():
    """TWO PREMISES, both of which a case can silently lose and neither of which
    `leaf.assert_bands_are_seeded` can see, because it only checks the bands a case DECLARES.

    The FIRST is the drift band's reach: `DRIFT_CURSORS` drives indexes outside the table on purpose,
    and the largest of them must still land inside the keyed band — otherwise that row reads the
    .PRG's own shipped word, the expected value is computed from the same unseeded byte, and a port
    that mis-indexed into the gap would match. It cost exactly that: the band was 0x20 either side
    and the $80 row read 0x20 bytes past its end.

    The SECOND is that the scene descriptor is not the FOLLOWED record. Slot 12 of the default table
    IS `WB_ACTOR_FOLLOWED_DEFAULT`, which the shared tail and much of the behaviour tier read."""
    reach = TYPE30_DRIFT + max(leaf.s16(cursor) for cursor in DRIFT_CURSORS) + WORD_BYTES
    assert DRIFT_BAND_LO <= TYPE30_DRIFT + min(leaf.s16(c) for c in DRIFT_CURSORS), (
        "a case drives a NEGATIVE index that reaches below the keyed band")
    assert reach <= DRIFT_BAND_LO + DRIFT_BAND_LEN, (
        f"a case reads up to {reach:#x}, past the keyed band's end at "
        f"{DRIFT_BAND_LO + DRIFT_BAND_LEN:#x} — that row's keying is decoration")
    assert GATE_DESCRIPTOR != FOLLOWED_DEFAULT, (
        "the case's scene descriptor sits on the followed record")
    lo, length = GATE_DESCRIPTOR_BAND
    assert not lo <= FOLLOWED_DEFAULT < lo + length, (
        "the descriptor's keyed band covers the followed record")


def test_the_ascents_own_table_is_the_one_slot_30_drifts_on_and_its_cursor_is_not():
    """WB_DEATH_DRIFT_CURSOR is a SECOND phase over one table, which is the claim the row above
    rests on. Both halves off the image: the two words are adjacent, and only these two instructions
    name the gate's one."""
    assert DEATH_DRIFT_CURSOR + WORD_BYTES == wb("ACTOR_TYPE30_CURSOR"), (
        "the gate's cursor is not the word below slot 30's own")
    named, _ = _absolute_operand_census(DEATH_DRIFT_CURSOR)
    assert sorted(named) == [0xb7e, 0xb98], (
        f"the gate's drift cursor is named by {[hex(at) for at in sorted(named)]}")


def test_the_ascent_re_reads_the_camera_AFTER_its_own_two_stores():
    """THE READ-AFTER-STORE, driven. `cmpi.w #$ffc0,$9936.l` is spelt twice — once at $b3e before
    the rise and once at $b9e after it — and a port that kept the first answer would be
    indistinguishable on every ordinary frame, because nothing the rise writes is the camera.

    So the record is placed ON the camera pair: a0 = WB_SCROLL_FOLLOW_X, which makes `subq.w #1,2(a0)`
    a decrement of WB_SCROLL_FOLLOW_Y itself. Seeded one above the top, the rise puts it EXACTLY at
    WB_DEATH_ASCENT_TOP_Y and the second read then re-raises WB_STAGE_RESET_BLOCK — a write the
    single-read port never makes.

    RED FIRST: with `gate_death`'s second `be16` replaced by the first read's value, this case fails
    on the missing $b08 write."""
    what = "player_pending_event_gate ascent onto the camera"
    camera = wb("SCROLL_FOLLOW_X")
    pokes = _gate_pokes(what, {STAGE_RESET_BLOCK: word(MARKER),
                               DEATH_DRIFT_CURSOR: word(0),
                               camera: word(ASCENT_X), SCROLL_FOLLOW_Y: word(DEATH_ASCENT_TOP_Y + 1)})
    image = harness.make_image(pokes)

    expected = {}
    _put_word(expected, SCROLL_FOLLOW_Y, DEATH_ASCENT_TOP_Y)          # `subq.w #1,2(a0)`
    _put_word(expected, camera, (ASCENT_X + _drift_at(image, 0)) & WORD_MASK)
    _put_word(expected, DEATH_DRIFT_CURSOR, TYPE30_DRIFT_STRIDE)
    _put_word(expected, STAGE_RESET_BLOCK, DEATH_FLAG_SET)            # ...and the SECOND read's
    _run_gate(what, pokes, expected, record=camera)


def test_the_rise_spends_the_y_BEFORE_it_reads_the_drift_cursor():
    """THE ORDER INSIDE THE RISE, driven the same way. `subq.w #1,2(a0)` runs first and
    `move.w $4f58.l,d0` second, so a record placed two bytes BELOW the cursor makes the rise's own
    decrement the thing the cursor read then sees.

    Seeded at WB_DEATH_DRIFT_CURSOR + 1 step, the frame indexes the table at the step below and
    stores back the step above THAT — a sequence the other order cannot produce.

    THE STATE IT PROVES THIS ON IS ONE THE HARDWARE CANNOT REACH, and that is worth saying: the
    `subq.w #1` always flips the cursor's parity, so `move.w 0(a1,d0.w)` fetches an ODD word, which
    is an address error on a real 68000. Musashi and the port agree about it and the ORDER the case
    pins is real, but the placement is a differential's, not a frame's — the same standing as this
    battery's odd-cursor silence."""
    what = "player_pending_event_gate ascent onto its own cursor"
    record = DEATH_DRIFT_CURSOR - WORD_BYTES
    seeded = 2 * TYPE30_DRIFT_STRIDE
    pokes = _gate_pokes(what, {STAGE_RESET_BLOCK: word(MARKER),
                               DEATH_DRIFT_CURSOR: word(seeded),
                               record: word(ASCENT_X)})
    image = harness.make_image(pokes)
    spent = seeded - DEATH_ASCENT_RISE

    expected = {}
    _put_word(expected, record, (ASCENT_X + _drift_at(image, spent)) & WORD_MASK)
    _put_word(expected, DEATH_DRIFT_CURSOR,
              (spent + TYPE30_DRIFT_STRIDE) & TYPE30_DRIFT_MASK)
    _run_gate(what, pokes, expected, record=record)


@pytest.mark.parametrize("lives,message", [(0, "MESSAGE_GAME_OVER"), (1, "MESSAGE_CONTINUE"),
                                           (0xffff, "MESSAGE_CONTINUE")],
                         ids=["no-lives", "one-life", "all-ones"])
def test_the_frame_the_ascent_tops_out_posts_the_message_WB_LIVES_chooses(lives, message):
    """$b4a..$b76. The default is the one with no continue in it and only a NONZERO count replaces
    it, which is why $ffff takes the same arm as 1: `tst.w` is a test against zero, not a sign."""
    what = f"player_pending_event_gate top-out lives={lives:#06x}"
    pokes = _gate_pokes(what, {STAGE_RESET_BLOCK: word(MARKER),
                               SCROLL_FOLLOW_Y: word(DEATH_ASCENT_TOP_Y), LIVES: word(lives)})
    expected = {}
    _put_word(expected, STATE_FLAG_A34, STATE_FLAG_SET)
    _put_word(expected, DEATH_MESSAGE_POSTED_B0A, GATE_FLAG_SET)
    expected[TEXT_REQUEST] = globals()[message]
    _put_word(expected, TEXT_LIFETIME_REQUEST, DEATH_MESSAGE_LIFETIME)
    _run_gate(what, pokes, expected)


@pytest.mark.parametrize("name,message", [("game-over", "MESSAGE_GAME_OVER"),
                                          ("continue", "MESSAGE_CONTINUE")])
def test_the_two_messages_the_gate_posts_are_the_ones_the_shipped_strings_name(name, message):
    """The ids are 1-based into WB_TEXT_MESSAGE_TABLE, so which sentence each one is can be read off
    the image rather than claimed. They are the SAME sentence with and without a way out of it, which
    is what makes getting them the wrong way round invisible in a write-set compare."""
    text = _shipped_message_text(globals()[message])
    assert b"game over" in text.lower(), f"message {globals()[message]:#x} reads {text!r}"
    assert (b"continue" in text.lower()) == (name == "continue"), (
        f"message {globals()[message]:#x} is the wrong one of the pair: {text!r}")


# --- $bbe: the prompt, and two of the three unwinds ----------------------------------------------

def _prompt_pokes(what, *, box, expired=0, lives=0, fire=False, fields=None):
    """A frame with the ascent already topped out, so the gate is in its prompt."""
    seeds = {STAGE_RESET_BLOCK: word(MARKER),
             DEATH_MESSAGE_POSTED_B0A: word(MARKER),
             DEATH_BOX_EXPIRED_B0C: word(expired),
             TEXT_BOX_ACTIVE: bytes([1 if box else 0]),
             LIVES: word(lives),
             JOY1_STATE: bytes([(1 << JOY1_FIRE_BIT) if fire else 0])}
    seeds.update(fields or {})
    return _gate_pokes(what, seeds)


def test_the_frame_the_box_comes_down_latches_the_word_that_ends_the_game():
    """$bd0. Nothing else happens on it — the box is down, WB_DEATH_BOX_EXPIRED_B0C goes up, and the
    frame after this one is the data-disk prompt."""
    what = "player_pending_event_gate prompt box down"
    pokes = _prompt_pokes(what, box=False)
    expected = {}
    _put_word(expected, DEATH_BOX_EXPIRED_B0C, GATE_FLAG_SET)
    _run_gate(what, pokes, expected)


@pytest.mark.parametrize("box", [False, True], ids=["box-down", "box-up"])
def test_the_latched_frame_leaves_through_the_data_disk_unwind(box):
    """WB_PLAYER_GATE_DATADISK_UNWIND: `lea 4(a7),a7 / jmp $e494.l` at $bd8, ONE return address
    discarded. The oracle is stopped at the `jmp` and witnessed by the `lea`, which no other path
    executes — and the `lea` writes no memory, so the image compared is the one at the transfer.

    THE ARM WRITES NOTHING AT ALL, which is what makes the witness load-bearing here rather than
    decorative: without it the case would pass on a run that simply returned.

    THE `box-up` ROW IS WHAT ORDERS THE TWO TESTS. `tst.w $b0c.w` at $bbe runs BEFORE
    `tst.b $c031.l` at $bc6, so a latched word leaves for the disk prompt even while a box is on
    screen — where the other order would ask the continue prompt instead."""
    what = f"player_pending_event_gate prompt expired box={box}"
    pokes = _prompt_pokes(what, box=box, expired=MARKER, lives=2, fire=True)
    _run_gate(what, pokes, {}, exit_code=GATE_EXIT_DATADISK,
              stop_pc=GATE_DATADISK_SITE, via=GATE_DATADISK_TAKEN_AT)


@pytest.mark.parametrize("lives,fire", [(0, True), (0, False), (2, False)],
                         ids=["no-lives-firing", "no-lives-idle", "lives-not-firing"])
def test_the_prompt_waits_while_either_half_of_its_question_is_unanswered(lives, fire):
    """$be4's two gates: a life LEFT and FIRE HELD, and the frame does nothing at all until both are
    true. The first row is the one that matters — fire on a spent game is refused."""
    what = f"player_pending_event_gate prompt lives={lives} fire={fire}"
    _run_gate(what, _prompt_pokes(what, box=True, lives=lives, fire=fire), {})


def test_fire_on_the_prompt_spends_a_life_costs_the_armour_and_unwinds():
    """WB_PLAYER_GATE_RESTART_UNWIND, and the whole of what the frame does on the way out: the
    message primer, WB_LIVES spent, `game_life_restart_reset`'s own write set, the form word forced
    to WB_PLAYER_POSTURE_STATE_ONE, WB_LEVEL_SEQ_INDEX stepped BACK and
    WB_LIFE_RESTART_ENTRY_C26 raised for the level entry to read.

    THE FORM WORD IS THE POINT. `move.w #$1,$21e4.l` at $c06 is the image's only absolute-LONG write
    of it, which is the site an encoding-blind census missed for three batches — and it lands between
    the restart call and the unwind, so LOSING A LIFE COSTS THE ARMOUR.

    `game_life_restart_reset` is modelled against the image AS THE GATE LEAVES IT, because the
    `subq.w #1,$be2.w` above the call is what decides how many life icons get drawn."""
    what = "player_pending_event_gate prompt firing"
    lives, sequence = 3, 7
    pokes = _prompt_pokes(what, box=True, lives=lives, fire=True,
                          fields={LEVEL_SEQ_INDEX: word(sequence)})
    pokes = leaf.overlay(_reset_pokes(case_salt(what), lives), _gate_body_layer(), pokes)
    image = bytearray(harness.make_image(pokes))
    image[LIVES:LIVES + WORD_BYTES] = word(lives - 1)          # the gate's own `subq.w`

    expected = dict(_life_reset_writes(bytes(image)))
    expected[TEXT_REQUEST] = TEXT_REQUEST_PRIMED
    _put_word(expected, LIVES, lives - 1)
    _put_word(expected, EFFECT_STATE_21E4, POSTURE_STATE_ONE)
    _put_word(expected, LEVEL_SEQ_INDEX, sequence - 1)
    _put_word(expected, LIFE_RESTART_ENTRY_C26, GATE_FLAG_SET)
    _run_gate(what, pokes, expected, exit_code=GATE_EXIT_RESTART,
              stop_pc=GATE_RESTART_SITE, via=GATE_RESTART_TAKEN_AT,
              cap=PENDING_GATE_CAP + GAME_RESET_INSN_CAP, poison=False)


def test_the_word_the_restart_raises_is_read_where_the_unwind_lands():
    """WB_LIFE_RESTART_ENTRY_C26 is DATA INSIDE THE GATE'S OWN CODE, and its readers are in the band
    the unwind jumps into: `tst.w $c26.w` at $e5e4 skips one byte of level setup while it is raised,
    and `clr.w $c26.w` at $e6ec puts it back down. Three sites, no fourth."""
    named, other = _absolute_operand_census(LIFE_RESTART_ENTRY_C26)
    assert named == {0xc14: 0x33fc, 0xe5e4: 0x4a78, 0xe6ec: 0x4278}, (
        f"the restart word is named by { {hex(a): hex(o) for a, o in sorted(named.items())} }")
    assert not other, f"unclassified candidates: {[hex(a) for a in sorted(other)]}"
    assert leaf.entry_of("show_data_disk_prompt") < 0xe5e4 < leaf.entry_of("load_resource_by_index")


# --- $c28: the stage-animation arm ---------------------------------------------------------------

def test_the_stage_arm_does_nothing_but_the_tail_until_its_animation_finishes():
    """`tst.w $b10.w / beq.s $bb0` — and this is the ONE case here that runs
    `player_stage_transition` for real, because the latch it would return on is the very word this
    arm is waiting for. So the write set is that routine's arm-1 model and nothing of the gate's."""
    what = "player_pending_event_gate stage arm waiting"
    cursor = 2 * ANIM_FRAME_BYTES
    pokes = _gate_pokes(what, {STAGE_ANIM_REQUEST_B0E: word(MARKER),
                               STAGE_ANIM_DONE_B10: word(0),
                               EFFECT_STATE_21E4: word(0),
                               TRANSITION_CURSOR: word(cursor)})
    image = harness.make_image(pokes)

    expected = {}
    frame_at = TRANSITION_CURSOR + WORD_BYTES + cursor
    _put_word(expected, ACTOR + ACTOR_SPRITE,
              int.from_bytes(image[frame_at:frame_at + WORD_BYTES], "big"))
    _put_word(expected, TRANSITION_CURSOR, cursor + ANIM_FRAME_BYTES)
    _run_gate(what, pokes, expected)


def test_the_stage_arm_refuses_a_slot_that_is_not_free_and_writes_nothing():
    """`cmpi.w #$ffbe,$998c.l / bne.w $bb0` — a TEST of the free marker and never a raise.

    THE TAIL IS UNOBSERVABLE ON THIS ARM, which is why the case does not claim it. Reaching the
    refusal at all requires WB_STAGE_ANIM_DONE_B10 nonzero (`tst.w $b10.w / beq.s $bb0` at $c28 is
    above it), and that latch is `player_stage_transition`'s own first test — so the tail is an `rts`
    here whatever calls it, and `return WB_PLAYER_GATE_FRAME_SKIPPED` in place of the tail call is an
    EQUIVALENT mutant. That is a property of the original, not a gap in the port: the align arm's
    identical refusal, where the tail IS observable, is the case that pins the difference between the
    two endings. ../STATUS.md records the silence."""
    what = "player_pending_event_gate stage arm slot taken"
    pokes = _gate_pokes(what, {STAGE_ANIM_REQUEST_B0E: word(MARKER),
                               SPAWN_GATE_SLOT + ACTOR_X: word(MARKER)})
    _run_gate(what, pokes, {})


def test_the_stage_arm_spawns_the_event_actor_through_the_composition_it_names():
    """$c42..$c62: effect WB_EVENT_SPAWN_SFX on channel A, then `lea $998c.l,a2 / lea $537e.l,a1 /
    bsr.w $539e` — a2 the DESTINATION and a1 the TEMPLATE, in that order. The copy's own model comes
    from the rows above, so a port that swapped the two reddens on the destination's bytes."""
    what = "player_pending_event_gate stage arm spawning"
    pokes = _gate_pokes(what, {STAGE_ANIM_REQUEST_B0E: word(MARKER)})
    image = harness.make_image(pokes)

    expected = _record_copy_writes(image, SPAWN_GATE_SLOT, GATE_DESCRIPTOR, TYPE35_TEMPLATE,
                                   into=_sfx_bytes(image, EVENT_SPAWN_SFX, SND_CHANNEL_A))
    _run_gate(what, pokes, expected, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})




# The two sub-arms below run the WHOLE spawn tree, so their seeding, their allowed band and their
# models come from the battery that owns it rather than from `_gate_pokes`. What these cases are
# about is the three instructions BELOW the `bsr.w $19ac`.
from test_scene import (DESCRIPTOR as SCENE_DESCRIPTOR,   # noqa: E402
                        SPAWN_CAP, SPAWN_OWN_BYTES, START_RECORD_SPEECH,
                        load_window_bytes, spawn_pokes, spawn_start_record, speech_seeds)

SCENE_KIND = wb("SCENE_KIND")
SPAWN_UNNAMED_KIND = 3          # not 1, 2 or 4 — the kind ladder's fall-through


def _gate_over(seeds):
    """Another battery's seeds with the gate's own words on top and its BODY re-planted between —
    the second arm raised, the other two flags down, and the animation reported finished."""
    gate = {STAGE_RESET_BLOCK: word(0), STAGE_ANIM_REQUEST_B0E: word(MARKER),
            STAGE_ANIM_DONE_B10: word(MARKER), EVENT_ANIM_DONE_B12: word(MARKER),
            ALIGN_REQUEST_B14: word(0)}
    return leaf.overlay(seeds, _gate_body_layer(), gate)


def test_the_finished_event_disarms_BOTH_words_of_one_longword_clear():
    """`clr.l $b0e.w` at $c6a takes WB_STAGE_ANIM_DONE_B10 down WITH WB_STAGE_ANIM_REQUEST_B0E and
    names neither the second word nor the fact that it is a clear at all — the class this routine
    spells twice. Both halves are in the model and both are seeded NONZERO, so a port that cleared
    only the word the instruction names reddens on the other.

    Everything `scene_spawn_from_script` writes is declared SELF-CHECKED: test_scene.py is what pins
    the tree's own write set, and the byte-for-byte diff every case here makes still covers it."""
    what = "player_pending_event_gate stage arm finishing"
    seeds, start = speech_seeds(what)
    pokes = _gate_over(seeds)

    expected = {}
    _put_long(expected, STAGE_ANIM_REQUEST_B0E, 0)     # ...which is $b0e AND $b10
    _put_word(expected, EVENT_ANIM_DONE_B12, 0)
    # THE CLEAR TAKES THE LATCH DOWN UNDER THE SHARED TAIL, which is a real property of this arm and
    # not an artefact of the seeding: `player_stage_transition` returns at once while
    # WB_STAGE_ANIM_DONE_B10 is up, and this is the one path in the routine that lowers it BEFORE
    # calling. So the tail runs for real and publishes a sprite, which the assertion below requires.
    sprite = {ACTOR + ACTOR_SPRITE, ACTOR + ACTOR_SPRITE + 1}
    tree = SPAWN_OWN_BYTES | load_window_bytes(start) | sprite
    info = _run_gate(what, pokes, expected, cap=PENDING_GATE_CAP + SPAWN_CAP, poison=False,
                     psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER},
                     extra_band=merge_bands(tree), self_checked=tree, d7_high=0)
    assert sprite <= set(program_writes(info)), (
        f"{what}: the tail did not publish a sprite, so it returned on a latch this arm had already "
        f"cleared")


def test_a_spawn_tree_that_never_returns_leaves_everything_below_the_call_unrun():
    """WB_PLAYER_GATE_SCENE_LEFT. `scene_spawn_from_script` pushes a0 at its first instruction and
    only its three arms pop it, so a descriptor whose kind the ladder does not name returns THROUGH
    that saved a0 — an original defect test_scene.py found and pins. The gate cannot follow it, so it
    reports that the call left and says nothing about WHICH of the callee's three endings it was:
    the checkpoint is the callee's own `rts` at $19e0 and the witness is the `bsr.w $19ac` at $c66,
    which no other path in this routine executes.

    THE THREE INSTRUCTIONS BELOW THE CALL MUST NOT HAVE RUN, and that is what the write set says: the
    only byte written is the free marker the tree's own head plants, so neither longword clear
    happened."""
    what = "player_pending_event_gate stage arm scene left"
    start = spawn_start_record(START_RECORD_SPEECH)
    pokes = _gate_over(spawn_pokes(what, start,
                                   words=((SCENE_DESCRIPTOR + SCENE_KIND, SPAWN_UNNAMED_KIND),)))

    expected = {}
    _put_word(expected, SPAWN_GATE_SLOT, ACTOR_FREE_MARKER)
    _run_gate(what, pokes, expected, exit_code=GATE_EXIT_SCENE_LEFT,
              cap=PENDING_GATE_CAP + SPAWN_CAP, poison=False,
              psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER},
              stop_pc=GATE_SCENE_LEFT_SITE, via=GATE_SCENE_CALL_AT)


# --- $c76: the scene-align arm, the event pair and the last unwind -------------------------------

def test_the_align_arms_refusal_skips_the_frame_WITHOUT_the_shared_tail():
    """THE ASYMMETRY between the two arms that test the same word. `cmpi.w #$ffbe,$998c.l / bne.w
    $d22` at $c7e sends a taken slot to `move.w #$ffff,d7 / rts` with NO `bsr.w $1f54` above it,
    where the stage arm's identical refusal at $c3e goes to the shared tail and does get one.

    Nothing is written either way, so the write set cannot tell them apart: the claim is the
    NEGATIVE coverage one, that $bb0 did not execute."""
    what = "player_pending_event_gate align arm slot taken"
    # WB_STAGE_ANIM_DONE_B10 IS SEEDED DOWN HERE, where every other case raises it: with the latch up
    # `player_stage_transition` is an `rts` and calling it or not is invisible on both sides, so the
    # negative coverage claim below would pin the ORIGINAL and nothing about the port. Down, the tail
    # publishes a sprite — so a port that reached it writes a byte the original does not.
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               STAGE_ANIM_DONE_B10: word(0),
                               SPAWN_GATE_SLOT + ACTOR_X: word(MARKER)})
    _run_gate_claiming_tail_not_reached(what, pokes, {})


def _event_pair_first_record_writes(image, position):
    """Everything the align arm writes BEFORE it reads the position longword a second time: the two
    sound models, WB_STATE_FLAG_A34, and slot 0's three fields.

    STOP FIRST, THEN THE TRIGGER, in the order the arm calls them — `snd_stop_all_sfx` clears the
    three active flags as ONE longword and the trigger then raises channel A's again, so a model
    that applied the two sets the other way round would expect a zero the arm never leaves behind.
    That ordering rule lives here once rather than in a comment above each copy of the block."""
    expected = _flatten(STOP_WRITES)
    expected.update(_sfx_bytes(image, EVENT_SPAWN_SFX, SND_CHANNEL_A))
    _put_word(expected, STATE_FLAG_A34, STATE_FLAG_SET)
    _put_long(expected, TABLE_DEFAULT, position)
    _put_word(expected, TABLE_DEFAULT + ACTOR_TYPE, 0)
    _put_word(expected, TABLE_DEFAULT + ACTOR_SPRITE, EVENT_PAIR_SPRITE_INERT)
    return expected


@pytest.mark.parametrize("spawn_type,type_word,sprite",
                         [(0, "EVENT_PAIR_TYPE_RISER", "EVENT_PAIR_SPRITE_RISER"),
                          (1, "EVENT_PAIR_TYPE_ANIMATOR", "EVENT_PAIR_SPRITE_ANIMATOR"),
                          (0xffff, "EVENT_PAIR_TYPE_ANIMATOR", "EVENT_PAIR_SPRITE_ANIMATOR")],
                         ids=["riser", "animator", "animator-all-ones"])
def test_the_align_arm_fills_a_PAIR_of_records_out_of_the_descriptor(spawn_type, type_word, sprite):
    """$c8a..$cec, and there is no template anywhere in it: slot 0 gets a type-0 record showing
    WB_EVENT_PAIR_SPRITE_INERT and slot 1 gets the riser or the animator, both positioned from the
    descriptor's own WB_SCENE_TRIGGER_X and _SPAWN_Y as one longword.

    THE SECOND RECORD'S TWO WORDS ARE STORED TWICE when the descriptor asks for the animator — the
    riser's pair first and overwritten in place — which the ledger records as one final value. The
    rows say which pair survives; `test_the_align_arm_re_reads_the_position` below is what says the
    LONGWORD is re-read rather than kept."""
    what = f"player_pending_event_gate align spawn type={spawn_type:#06x}"
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               GATE_DESCRIPTOR + TRIGGER_SPAWN_TYPE: word(spawn_type)})
    image = harness.make_image(pokes)
    position = _image_long(image, GATE_DESCRIPTOR + EVENT_PAIR_POSITION)

    expected = _event_pair_first_record_writes(image, position)
    _put_long(expected, SPAWN_GATE_SLOT, position)
    _put_word(expected, SPAWN_GATE_SLOT + ACTOR_TYPE, globals()[type_word])
    _put_word(expected, SPAWN_GATE_SLOT + ACTOR_SPRITE, globals()[sprite])
    _run_gate(what, pokes, expected, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})


def test_the_align_arm_re_reads_the_position_longword_for_the_second_record():
    """THE SECOND READ-AFTER-STORE. `move.l 2(a1),(a2)` is spelt twice with the FIRST record's three
    stores between them, and a1 is the descriptor pointer the image supplies — so the descriptor
    lying ON slot 0 is the arrangement in which the two reads differ. Here it does: the first copy
    lands on the descriptor's own +2 longword, so the second read takes back what the first wrote.

    RED FIRST: with the longword hoisted into a local, slot 1 gets the ORIGINAL position and this
    case reddens on four bytes.

    AND IT CATCHES A SECOND ONE FOR FREE. WB_SCENE_TRIGGER_SPAWN_TYPE is offset 6, which is
    WB_ACTOR_SPRITE — so `tst.w 6(a1)` reads the very word `move.w #$1a9,6(a2)` has just stored.
    The case seeds it ZERO and still gets the ANIMATOR, because the arm's own store is what the
    branch then reads."""
    what = "player_pending_event_gate align descriptor on slot 0"
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               TABLE_DEFAULT + TRIGGER_SPAWN_TYPE: word(0)},
                        descriptor=TABLE_DEFAULT)
    image = harness.make_image(pokes)
    first = _image_long(image, TABLE_DEFAULT + EVENT_PAIR_POSITION)

    expected = _event_pair_first_record_writes(image, first)
    # ...and the SECOND read, off the record the three writes above have just changed: +2 of it is
    # now the low half of the position longword and the type word the `clr.w` zeroed.
    after = bytearray(image)
    after[TABLE_DEFAULT:TABLE_DEFAULT + LONGWORD_BYTES] = first.to_bytes(LONGWORD_BYTES, "big")
    after[TABLE_DEFAULT + ACTOR_TYPE:TABLE_DEFAULT + ACTOR_TYPE + WORD_BYTES] = word(0)
    after[TABLE_DEFAULT + ACTOR_SPRITE:TABLE_DEFAULT + ACTOR_SPRITE + WORD_BYTES] = word(
        EVENT_PAIR_SPRITE_INERT)
    second = _image_long(bytes(after), TABLE_DEFAULT + EVENT_PAIR_POSITION)
    assert second != first, "the case's placement does not make the two reads differ"

    _put_long(expected, SPAWN_GATE_SLOT, second)
    # ...and the ANIMATOR's pair, from a descriptor whose spawn-type word was seeded ZERO: the arm's
    # own `move.w #$1a9,6(a2)` is what the `tst.w 6(a1)` below it reads.
    assert _image_long(image, TABLE_DEFAULT + TRIGGER_SPAWN_TYPE - WORD_BYTES) & WORD_MASK == 0, (
        "the case did not seed the descriptor's spawn-type word to zero, so the second store is "
        "not what flips the branch")
    _put_word(expected, SPAWN_GATE_SLOT + ACTOR_TYPE, EVENT_PAIR_TYPE_ANIMATOR)
    _put_word(expected, SPAWN_GATE_SLOT + ACTOR_SPRITE, EVENT_PAIR_SPRITE_ANIMATOR)
    # POISON OFF, and for this case's own reason rather than the composed cases': the descriptor IS
    # the modelled destination, so pre-poisoning the bytes the oracle wrote changes the very longword
    # the SECOND read is supposed to pick up and the attribution pass would be re-deriving `second`
    # from bytes no run produced.
    _run_gate(what, pokes, expected, psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER}, poison=False)


def test_the_align_arm_waits_for_the_animation_it_started():
    """`tst.w $b18.w / beq.w $bb0` at $cf0: WB_EVENT_ANIM_DONE_B16 is up, so the spawn is behind it,
    and until `player_stage_transition` raises WB_STAGE_ANIM_DONE_B18 the arm is the tail alone."""
    what = "player_pending_event_gate align waiting on the animation"
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               EVENT_ANIM_DONE_B16: word(MARKER)})
    _run_gate(what, pokes, {})


def test_the_event_ending_without_a_stage_advance_raises_the_word_only_e032_reads():
    """$cf8..$d1a. The box comes down, `clr.l $b14.w` takes WB_EVENT_ANIM_DONE_B16 with
    WB_SCENE_ALIGN_REQUEST_B14 as the longword's low half, WB_STAGE_ANIM_DONE_B18 is cleared on its
    own, and with no advance pending WB_EVENT_FINISHED_E1BE goes up.

    AND THE ANSWER IS $d22's, NOT $bb0's — this ending has no `bsr.w $1f54` above it either, which
    the negative coverage claim below is what says."""
    what = "player_pending_event_gate event finished, no advance"
    # ...and the latch DOWN again, for the reason the refusal case above spells out: with it up the
    # shared tail writes nothing and "did not call it" is not a claim about this port at all.
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               STAGE_ANIM_DONE_B10: word(0),
                               EVENT_ANIM_DONE_B16: word(MARKER),
                               STAGE_ANIM_DONE_B18: word(MARKER),
                               TEXT_BOX_ACTIVE: bytes([MARKER]),
                               STAGE_ADVANCE_REQUEST: word(0)})
    expected = {TEXT_BOX_ACTIVE: 0}
    _put_long(expected, ALIGN_REQUEST_B14, 0)          # ...which is $b14 AND $b16
    _put_word(expected, STAGE_ANIM_DONE_B18, 0)
    _put_word(expected, EVENT_FINISHED_E1BE, GATE_FLAG_SET)
    # ...and the premise is asked about the state at the point the tail WOULD be called, which is
    # after this arm's own three clears rather than at the gate's entry.
    _run_gate_claiming_tail_not_reached(what, pokes, expected,
                                        after={ALIGN_REQUEST_B14: word(0) + word(0),
                                               STAGE_ANIM_DONE_B18: word(0)})


def test_the_event_ending_WITH_a_stage_advance_takes_the_collision_maps_triple_pop():
    """THE THIRD UNWIND, and it is not a second exit but the SAME instruction: `bra.w $1622` at $d16
    branches into `player_run_map_cell`'s own `lea 12(a7),a7 / jmp $e5ba.l` — no call, no code of
    that routine run — so this arm reaches the identical triple pop and reports the identical
    WB_PLAYER_COLLIDE_UNWIND. The checkpoint is therefore $151a's own UNWIND_SITE and the witness is
    the `bra.w`, which is the one instruction on this path that no tile-$39 frame executes."""
    what = "player_pending_event_gate event finished, advancing"
    pokes = _gate_pokes(what, {ALIGN_REQUEST_B14: word(MARKER),
                               EVENT_ANIM_DONE_B16: word(MARKER),
                               STAGE_ANIM_DONE_B18: word(MARKER),
                               TEXT_BOX_ACTIVE: bytes([MARKER]),
                               STAGE_ADVANCE_REQUEST: word(MARKER)})
    expected = {TEXT_BOX_ACTIVE: 0}
    _put_long(expected, ALIGN_REQUEST_B14, 0)
    _put_word(expected, STAGE_ANIM_DONE_B18, 0)
    _put_word(expected, STAGE_ADVANCE_REQUEST, 0)
    _run_gate(what, pokes, expected, exit_code=EXIT_UNWIND,
              stop_pc=UNWIND_SITE, via=GATE_COLLIDE_TAKEN_AT)


# --- what the body is, beyond what any run reaches -----------------------------------------------

GATE_DEAD_PAIR = 0xbba          # `clr.w d7 / rts`
GATE_DEAD_PAIR_BYTES = 4


def test_the_gates_own_dead_pair_is_reached_by_nothing_in_the_image():
    """FOUR BYTES OF THE 526 ARE UNREACHABLE, and they are counted in the partition rather than
    trimmed off it — the same standing as $1f34's dead `rts`. Both halves: the bytes really are
    `clr.w d7 / rts`, and no instruction of ANY form aims at them.

    They are also the only place in the image that answers the gate's question with a WORD clear
    where every live path uses `clr.l` or `move.w #$ffff` — so what was cut is a THIRD answer."""
    assert bytes(harness.BASE_IMAGE[GATE_DEAD_PAIR:GATE_DEAD_PAIR + GATE_DEAD_PAIR_BYTES]) == (
        clr_w_dn(D7) + RTS)
    assert GATE_DEAD_PAIR not in CONTROL_FLOW_TARGETS, (
        f"$bba is named by {[hex(at) for at in CONTROL_FLOW_TARGETS[GATE_DEAD_PAIR]]}")
    assert GATE_DEAD_PAIR not in PC_RELATIVE_SOURCE_TARGETS, "$bba is read PC-relatively"


GATE_LONGWORD_DISARMS = [("stage", STAGE_ANIM_REQUEST_B0E, STAGE_ANIM_DONE_B10, 0xc6a),
                         ("event", ALIGN_REQUEST_B14, EVENT_ANIM_DONE_B16, 0xcfe)]


@pytest.mark.parametrize("name,named,unnamed,at", GATE_LONGWORD_DISARMS,
                         ids=[c[0] for c in GATE_LONGWORD_DISARMS])
def test_each_longword_clear_takes_the_word_its_instruction_does_not_name(name, named, unnamed, at):
    """The structural half of the two cases above: the second word really is the longword's low half,
    and the instruction at that address really is a `clr.l <abs>.w`. Without this the pair could
    drift apart in the header and both differential cases would keep passing on the new addresses."""
    assert unnamed == named + WORD_BYTES, (
        f"{unnamed:#x} is not the low half of the longword at {named:#x}")
    assert bytes(harness.BASE_IMAGE[at:at + len(clr_l_abs_w(named))]) == clr_l_abs_w(named), (
        f"{at:#x} is not `clr.l {named:#x}.w`")


def test_the_two_checkpointed_unwinds_are_the_two_the_pin_table_above_holds():
    """The gate's two DIRECT unwinds are the two `GATE_UNWIND_EXITS` keys, so the case that decodes
    the pops and the cases that stop the oracle at them are about the same two instructions.

    Whether each pops exactly one return address, and whether the third is $151a's triple pop, is
    `test_the_gate_leaves_through_THREE_stack_unwinds_and_one_of_them_is_not_its_own`'s — one owner
    for `GATE_UNWIND_EXITS` rather than two loops that can drift."""
    assert sorted(GATE_UNWIND_EXITS) == [GATE_DATADISK_TAKEN_AT, GATE_RESTART_TAKEN_AT]
    for taken_at, site in ((GATE_DATADISK_TAKEN_AT, GATE_DATADISK_SITE),
                           (GATE_RESTART_TAKEN_AT, GATE_RESTART_SITE)):
        assert site == taken_at + len(lea_d16(A7, UNWIND_ONE_BYTES)), (
            f"the checkpoint at {site:#x} is not the instruction after the pop at {taken_at:#x}")


# ===================================================================================================
# --- $a38: THE FRAME, WHOLE — batch 41 phase F -----------------------------------------------------
#
# The sixty-second dispatch row, and the only one whose body is nine calls into this file. What the
# cases below add to the nine batteries above them is the COMPOSITION: the order, the caller-side d7
# test, the two guards, the exit report, and the one thing no callee's battery can hold — the X flag
# travelling from `player_gate_on_1516`'s chain, through the walk's coasting arm, into the `sbcd`.
#
# EVERY CASE HERE ENTERS AT $a38 AND DIFFS THE WHOLE IMAGE against the original run from the same
# address. The two `bsr`-pair cases above are this battery's ancestors and are kept: they measured
# that the bit exists before there was a frame to carry it.
_FRAME = leaf.register_glue("actor_behavior_type01_player",
                            [ctypes.c_uint32, ctypes.c_uint], ctypes.c_uint32)

# The bound on one frame: each of the nine calls' own cap, plus the frame's sixteen instructions. It
# is the sum of the caps the nine batteries above already derive, which is what stops it becoming a
# round number that hides a runaway.
# `actor_fall_and_settle`'s bound: its player head, then two settles, each of which is a probe's
# worth of scan. PROBE_INSNS is this file's own derivation, from the walk's battery above.
FALL_AND_SETTLE_SCANS = 3
FALL_AND_SETTLE_CAP = FALL_AND_SETTLE_SCANS * PROBE_INSNS
# THE ROW'S OWN TWELVE INSTRUCTIONS come from the pin that owns them, which is
# test_behavior.py's: the frame is a dispatch row, so its entry pin sits beside the other
# sixty-one rather than here, and importing it is what stops this file holding a second count.
from test_behavior import (DISPATCH_RAN,                       # noqa: E402
                           INSN_COUNT as BEHAVIOR_INSN_COUNT)

FRAME_CAP = (BEHAVIOR_INSN_COUNT["actor_behavior_type01_player"] + leaf.RUNNER_SENTINEL_INSN
             + METER_EMPTY_CAP + PENDING_GATE_CAP + JUMP_STEP_CAP + STEP_AND_ARM_CAP
             + WEAPON_CAP + FALL_AND_SETTLE_CAP + _cap("player_apply_joystick")
             + MAP_CELL_CAP + STAGE_TRANSITION_CAP)

FRAME_ENTRY_EXTEND = 0          # what `emu.run`'s SR = $2700 gives the oracle at $a38
FRAME_SALT = "the whole player frame"

# The frame's own five gate words, all set so that the routine each guards writes NOTHING. Every one
# is a word `_frame_pokes` states rather than inherits, because a frame case is about the eight OTHER
# calls and a keyed byte in any of these turns the case into a different frame.
#   * a meter that is not empty ends `player_meter_empty_check` at its first instruction;
#   * the three WB_STAGE_RESET_BLOCK words clear make `player_pending_event_gate` `clr.l d7 / rts`;
#   * WB_ACTOR_PLATFORM_RIDDEN raised skips `actor_fall_and_settle` — which is the frame's OWN
#     abs.LONG guard at $a52, and the one instruction of the two that reads a LONG operand;
#   * WB_STATE_FLAG_A32 raised skips `player_run_map_cell` — the abs.w guard at $a64;
#   * WB_STAGE_ANIM_DONE_B10 raised makes `player_stage_transition` its own latch, i.e. an `rts`.
FRAME_QUIET_GLOBALS = {
    HUD_METER_VALUE: word(1),
    STAGE_RESET_BLOCK: word(0), STAGE_ANIM_REQUEST_B0E: word(0), ALIGN_REQUEST_B14: word(0),
    PLATFORM_RIDDEN: word(1), STATE_FLAG_A32: word(1), STAGE_ANIM_DONE_B10: word(MARKER),
}

# The strength word whose `addi.b #$8,d0` at $e12 CARRIES, and its twin that does not. The jump
# machine stamps that byte into WB_ACTOR_FIELD_10 every frame and three of its six exits still carry
# the flag when they `rts`, so this pair is what drives them apart.
JUMP_STRENGTH_CARRY = 0x00f8         # $f8 + 8 = $100
JUMP_STRENGTH_NO_CARRY = WALK_STRENGTH


def _frame_pokes(record_fields=None, *, strength=WALK_STRENGTH, up_held=False, charge=0,
                 globals_=None, ladder=False):
    """A frame that FIRES, entered at $a38, with the gate's chain the only thing that moves.

    IT IS `_frame_composition_pokes`' SEED PLUS THE FRAME'S OWN FIVE GATE WORDS. The walk-and-weapon
    layer is reused rather than restated so that a byte either battery needs is added in one place;
    what this adds is the four calls that composition never ran and the words that shut them.

    THE FIRING FRAME IS ALSO THE COASTING FRAME, which is why the gate's bit reaches the `sbcd` at
    all: the weapon's third gate wants `joy1_newly_pressed` to be exactly WB_PLAYER_FIRE_EDGE_EXACT,
    so the walk's fire edge runs, so the speed is cleared at $f06 and the drift's gate lowered at
    $f00 — and with no knock-back and no flicker, not one instruction of the walk writes X.

    `up_held` holds UP in BOTH joystick bytes, which is the wing boots' own question and costs the
    weapon nothing: `joy1_newly_pressed` is `current & ~prev`, so a bit held on both frames is not a
    new press and the edge byte stays $80. Holding UP is therefore compatible with firing; pressing
    it is not, which is exactly why the LAUNCH exit is unreachable from the `sbcd`.

    `ladder` raises WB_TILE_33_MODE, which sends $d78 down the arm that runs nothing. It leaves
    WB_TILE_33_FLAG clear, and whether the game can reach THAT pair is the case beside the row that
    uses it."""
    fields = {HUD_SLOT_BBC2: bytes([charge])}
    if ladder:
        fields[TILE_33_MODE] = word(TILE_33_MODE_UP)
    if up_held:
        fields[JOY1_PREV] = bytes([(1 << JOY1_DOWN_BIT) | (1 << JOY1_UP_BIT)])
        fields[JOY1_CURRENT] = bytes([FIRE_EDGE_EXACT | (1 << JOY1_DOWN_BIT) | (1 << JOY1_UP_BIT)])
    return leaf.overlay(_frame_composition_pokes(record_fields or {}, direction=0,
                                                 strength=strength),
                        FRAME_QUIET_GLOBALS, fields, globals_ or {})


def _run_frame(what, pokes, expected_extend, entry_extend=FRAME_ENTRY_EXTEND,
               expected_report=DISPATCH_RAN):
    """One whole-frame row: the ORIGINAL from $a38 to its own `rts`, the C's frame beside it, the
    whole image compared, and the ORACLE's shot count read back as the row's statement of WHICH X
    the gate's chain left.

    `expected_extend` is not a second copy of the C. It is checked against
    `leaf.bcd_expected`'s decimal model of what the `sbcd` spends, so a row whose seeding quietly
    stopped firing fails here rather than agreeing about nothing — the lesson the walk battery above
    was built on."""
    diffs, info = leaf.differential(FRAME_ENTRY, {"a0": ACTOR, "_pokes": pokes},
                                    _FRAME(ACTOR, entry_extend), max_insns=FRAME_CAP, poison=True)
    assert not diffs, f"{what}\n{leaf.report(diffs)}"
    assert info["ret"] == expected_report, (
        f"{what}: the frame reported {info['ret']:#x}, not the {expected_report:#x} this ending "
        f"leaves at")

    at = WEAPON_RECORD + RECORD_LOW_BYTE
    spent = info["writes"].get(at)
    assert spent == _spend_bytes(WALK_SPEND_COUNT, borrow=expected_extend)[at], (
        f"{what}: the ORIGINAL left {spent!r} in the shot count, not the X={expected_extend} spend "
        f"this row claims — either the frame never reached the `sbcd` or the gate's chain leaves a "
        f"different bit")
    return info


# THE $d78 CHAIN, one row per exit, with the seed that drives it and the bit it must leave at the
# `sbcd`. Five of the six exits are here; the sixth is the LAUNCH, and the case below this table is
# what says no firing frame can take it.
#
# THE FLAGS PICK THE ARM: WB_ACTOR_FLAG_MOVING_BIT is the ASCENT, WB_ACTOR_FLAG_SUPPORTED_BIT the
# stand, neither the wing boots. Only the ascent and the wing-boot SPEND write an X of their own; the
# other three arms hand on the `addi.b #$8,d0` the routine's head stamped, which is why the strength
# pair appears on three rows and the two overwriting arms appear with it deliberately set to CARRY.
MOVING_FLAG = 1 << MOVING_BIT
SUPPORTED_FLAG = 1 << SUPPORTED_BIT
ASCENT_SPEED_BORROWS = 0        # `subq.b #1,11(a0)` borrows exactly when the byte was already zero
ASCENT_SPEED_NO_BORROW = 1
WING_BOOT_CHARGES = 3           # more than one, so the spend is not also the rearm
WING_BOOT_LAST_CHARGE = 1

GATE_X_PATHS = (
    # $ec6 — the ASCENT, whose `subq.b #1,11(a0)` is the exit's own X.
    ("the ascent's speed byte borrows",
     dict(record_fields={ACTOR_FLAGS: MOVING_FLAG, SPEED: ASCENT_SPEED_BORROWS},
          strength=JUMP_STRENGTH_NO_CARRY), 1),
    ("...and the same arm one frame earlier, where it does not",
     dict(record_fields={ACTOR_FLAGS: MOVING_FLAG, SPEED: ASCENT_SPEED_NO_BORROW},
          strength=JUMP_STRENGTH_CARRY), 0),
    # $e78 — SUPPORTED with UP not newly pressed, which is every firing frame that stands.
    ("the stand carries the head's `addi.b` out",
     dict(record_fields={ACTOR_FLAGS: SUPPORTED_FLAG}, strength=JUMP_STRENGTH_CARRY), 1),
    ("...and the same arm off a strength byte that does not carry",
     dict(record_fields={ACTOR_FLAGS: SUPPORTED_FLAG}, strength=JUMP_STRENGTH_NO_CARRY), 0),
    # $e6a via the `beq.w` at $e34 — airborne with an EMPTY slot, so the spend never runs.
    ("airborne with no wing-boot charge, so the head's carry stands",
     dict(record_fields={ACTOR_FLAGS: 0}, charge=0, strength=JUMP_STRENGTH_CARRY), 1),
    # $e6a via the `beq.w` at $e3e — a charge held but UP not held, which is the same bit by a
    # different branch, and the row that separates the two `beq`s from each other.
    ("airborne with a charge but UP not held, which is the OTHER branch to the same `rts`",
     dict(record_fields={ACTOR_FLAGS: 0}, charge=WING_BOOT_CHARGES,
          strength=JUMP_STRENGTH_CARRY), 1),
    # $e6a via the `bne.w` at $e4e — the SPEND, and the row that matters most: the strength byte is
    # the CARRYING one, so a model that forgot the `subq.b` overwrites it answers 1 here.
    ("the wing boots spend a charge, and that `subq.b` overwrites the head's carry",
     dict(record_fields={ACTOR_FLAGS: 0}, charge=WING_BOOT_CHARGES, up_held=True,
          strength=JUMP_STRENGTH_CARRY), 0),
    # ...and the same instruction on the frame the LAST charge goes, which falls through $e52's
    # rearm to the same `rts` instead of branching to it.
    ("...and on the frame the last charge goes, where the arm falls through the rearm",
     dict(record_fields={ACTOR_FLAGS: 0}, charge=WING_BOOT_LAST_CHARGE, up_held=True,
          strength=JUMP_STRENGTH_CARRY), 0),
)


@pytest.mark.parametrize("case,seed,expected_extend", GATE_X_PATHS,
                         ids=[row[0] for row in GATE_X_PATHS])
def test_the_gates_chain_reaches_the_weapons_sbcd(case, seed, expected_extend):
    """ONE ROW PER EXIT OF `$d78`'s CHAIN, diffed as a whole frame.

    `player_gate_on_1516` is the instruction before the walk and the walk's coasting arm passes what
    it is given straight through, so the bit the `sbcd` folds in on a firing frame is this routine's.
    Five exits are computable from three bytes — the low byte of WB_EFFECT_STATE_BD6A, WB_ACTOR_SPEED
    and WB_HUD_SLOT_BBC2 — and each row drives one of them and states which.

    The differential is over the WHOLE frame, so a row also pins the eight other calls' composition;
    what makes it a statement about the FLAG is the shot count, which no memory the two runs share
    can produce."""
    _run_frame(f"the frame's $d78 chain: {case}", _frame_pokes(**seed), expected_extend)


# --- the frame's ENTRY bit, which is the DISPATCHER's --------------------------------------------
#
# `player_gate_on_1516`'s ladder arm is `tst.w $1516.l / rts` — two X-silent instructions — so on a
# frame whose WB_TILE_33_MODE is raised the `sbcd` folds in the bit the frame was ENTERED with. That
# bit is not a caller's to invent: $a38's only reference in the whole image is the table longword at
# $93c, so the frame is entered by `jmp (a1)` and by nothing else, and three instructions above that
# jump is `lsl.w #2,d1` at $92e — a WORD shift of two, which leaves X holding bit 14 of the type word
# `move.w 4(a0),d1` at $92a read.
#
# WHICH MAKES THE SET DIRECTION DRIVABLE FROM THE ORIGINAL, and by the original's own aliasing rather
# than by a fabricated record: `lsl.w` wraps in sixteen bits, so $4001 and $c001 scale to slot 1's
# offset exactly as $0001 does and the ORACLE really dispatches all three to $a38 — with X set on the
# two whose bit 14 is up. The rows below run the DISPATCHER, not the frame, for that reason: entered
# at $a38 the oracle's CCR is `emu.run`'s SR = $2700 whatever the type says.
#
# THE GLUE IS test_behavior.py's BINDING and not a second one. `leaf.bind` is `getattr` on a
# `ctypes.CDLL`, which CACHES the function object, so two spellings of one prototype in one process
# are one object with whichever `argtypes` was set last.
from test_behavior import _DISPATCH as _BEHAVIOR_DISPATCH   # noqa: E402

from test_behavior import (BEHAVIOR_SCALE_BITS,                # noqa: E402
                           BODY_SIZES as BEHAVIOR_BODY_SIZES)

DISPATCH_ENTRY = leaf.entry_of("actor_dispatch_behavior")
WORD_BITS = WORD_BYTES * 8      # `lsl.w` shifts a WORD, so the bit it leaves in X is counted in one
# The four instructions the ladder-honesty case below reads, each named by the address it sits at.
FALL_FLAG_RAISE_AT = 0x1350     # `move.w #$ffff,$1514.l` — the fall pass's own raise
FALL_CLEARS_AT = 0x1364         # `clr.w $1516 / clr.w $1518 / clr.w $1514`, in that order
CELL_FLAG_SET_AT = 0x155c       # `st $1514.w` — the collision map's tile-$33 arm
CELL_FLAG_CLEAR_AT = 0x179e     # `clr.b $1514.w` — its ordinary-cell arm
LEVEL_RESET_FLAGS_AT = 0xff00   # `clr.l $1514.w` — the level-entry reset, and the one writer
                                # besides the fall pass that takes BOTH words down
TILE_33_FLAG_RAISED = wb("TILE_33_FLAG_RAISED")
FRAME_BODY_BYTES = BEHAVIOR_BODY_SIZES["actor_behavior_type01_player"]
GATE_SKIP_WITHOUT_TAIL_AT = 0xd22   # the align arm's `move.w #$ffff,d7`, with no tail
# The bound on a dispatched frame: the dispatcher's own four instructions on top of the frame's.
DISPATCH_INSNS = BEHAVIOR_INSN_COUNT["actor_dispatch_behavior"]
TYPE_PLAYER_ALIASES = (0x0001, 0x4001, 0x8001, 0xc001)


@pytest.mark.parametrize("type_word", TYPE_PLAYER_ALIASES, ids=lambda v: f"type-{v:04x}")
def test_the_dispatchers_own_shift_hands_the_ladder_frame_its_entry_X(type_word):
    """THE FRAME'S ENTRY BIT, driven end to end through the `jmp (a1)`.

    Every row seeds a LADDER frame that also fires, so `$d78` writes no X and the walk's coasting arm
    passes what it was given to the `sbcd`. The type word is the only thing that moves, and what it
    moves is a CONDITION CODE: bit 14 of it is what `lsl.w #2` shifts out last.

    ON THE GAME'S OWN DATA THE BIT IS ZERO, because the player's record holds type 1. The two rows
    that set it are the dispatcher's documented aliasing, which this file's neighbour pins against
    the oracle for its own reasons (`test_an_aliased_type_dispatches_the_ordinary_slot`) — so what
    they drive is the ORIGINAL's behaviour, not a record the game could not hold.

    IT IS ALSO THE ROW FLIP PROVEN END TO END: the run enters at `actor_dispatch_behavior`, so the
    reconstruction has to read the type, scale it, fetch the longword, recognise $a38 as a row it
    has, and run the whole frame behind it."""
    expected_extend = (type_word >> (WORD_BITS - BEHAVIOR_SCALE_BITS)) & 1
    what = f"the dispatched ladder frame, type {type_word:#06x}"
    pokes = leaf.overlay(_frame_pokes(ladder=True), {ACTOR + ACTOR_TYPE: word(type_word)})

    diffs, info = leaf.differential(DISPATCH_ENTRY, {"a0": ACTOR, "_pokes": pokes},
                                    _BEHAVIOR_DISPATCH(ACTOR),
                                    max_insns=FRAME_CAP + DISPATCH_INSNS, poison=True)
    assert not diffs, f"{what}\n{leaf.report(diffs)}"
    assert info["ret"] == DISPATCH_RAN, (
        f"{what}: the dispatcher reported {info['ret']:#x} — it did not run slot 1's frame")

    at = WEAPON_RECORD + RECORD_LOW_BYTE
    spent = info["writes"].get(at)
    assert spent == _spend_bytes(WALK_SPEND_COUNT, borrow=expected_extend)[at], (
        f"{what}: the ORIGINAL left {spent!r} in the shot count, not the X={expected_extend} spend "
        f"bit 14 of the type says the `lsl.w #2` shifted out")


def test_the_ladder_arm_the_row_above_drives_is_a_state_the_game_can_REACH():
    """THE HONESTY CASE UNDER THE FOUR ROWS ABOVE, and the question batch 41 phase E left open: can a
    frame whose WB_TILE_33_MODE is raised also FIRE? The weapon's first gate reads WB_TILE_33_FLAG
    and `$d78` reads WB_TILE_33_MODE, and the two words are $1514 and $1516 — adjacent, and written
    together often enough that "mode up, flag down" looks impossible.

    IT IS NOT, AND THE CONSTRUCTION IS THE FALL GUARD. What ties the two words is
    `actor_fall_and_settle`'s player head: `move.w #$ffff,$1514.l` at $1350 on a tile-$33 cell, and
    `clr.w $1516.l / clr.w $1518.l / clr.w $1514.l` at $1364..$1370 on any other — three clears in a
    row with no branch between them, so the pass NEVER leaves the mode up with the flag word down.
    But the frame's own `tst.w $6ef0.l / bne.w $a60` at $a52 can SKIP that pass, and the two other
    writers of $1514 are BYTE-wide: `st $1514.w` at $155c and `clr.b $1514.w` at $179e, both inside
    `player_run_map_cell` and both touching the HIGH half only. So a player riding a platform can
    have $1514 raised to $ff00 by a tile-$33 cell, climb (which needs only a nonzero $1514), and then
    have the same word cleared to $0000 by an ordinary cell one frame later — with $1516 still up,
    because nothing on that path writes it.

    THE WRITER CENSUS BEHIND THAT IS THREE AND NOT TWO. Besides the fall pass, `$1514` is written by
    `st $1514.w` at $155c and `clr.b $1514.w` at $179e — byte-wide, both inside
    `player_run_map_cell`, and the only two that can move it WITHOUT `$1516` — and by
    `clr.l $1514.w` at $ff00, which is LONG-wide, sits outside that routine, and is the one other
    instruction in the image that takes both words down together. All four are pinned below.

    WHAT THIS CASE CHECKS is the half of that argument a case can check: the four instructions the
    argument rests on are the instructions the image holds, at the addresses named. The reachability
    itself is an argument over frames and lives in ../STATUS.md's batch 41 phase F section."""
    assert bytes(harness.BASE_IMAGE[FALL_FLAG_RAISE_AT:FALL_FLAG_RAISE_AT + len(
        move_w_imm_abs_l(TILE_33_FLAG_RAISED, TILE_33_FLAG))]) \
        == move_w_imm_abs_l(TILE_33_FLAG_RAISED, TILE_33_FLAG), (
        f"{FALL_FLAG_RAISE_AT:#x} is not the fall pass's `move.w #$ffff,$1514.l`")

    # ...and the three clears, back to back and in this order, which is what says the pass cannot
    # separate the two words.
    clears = clr_w_abs_l(TILE_33_MODE) + clr_w_abs_l(TILE_33_STEP) + clr_w_abs_l(TILE_33_FLAG)
    assert bytes(harness.BASE_IMAGE[FALL_CLEARS_AT:FALL_CLEARS_AT + len(clears)]) == clears, (
        f"{FALL_CLEARS_AT:#x} is not the fall pass's three back-to-back clears")

    # ...and the two BYTE writers inside the collision map, which are what can move $1514 alone.
    assert bytes(harness.BASE_IMAGE[CELL_FLAG_SET_AT:CELL_FLAG_SET_AT + len(
        st_abs_w(TILE_33_FLAG))]) == st_abs_w(TILE_33_FLAG), (
        f"{CELL_FLAG_SET_AT:#x} is not `st $1514.w`")
    assert bytes(harness.BASE_IMAGE[CELL_FLAG_CLEAR_AT:CELL_FLAG_CLEAR_AT + len(
        clr_b_abs_w(TILE_33_FLAG))]) == clr_b_abs_w(TILE_33_FLAG), (
        f"{CELL_FLAG_CLEAR_AT:#x} is not `clr.b $1514.w`")

    # ...and the FIFTH instruction, which the first draft of this case and of `cmt 0xa38` both
    # missed: a LONG-wide clear outside `player_run_map_cell` that takes WB_TILE_33_MODE down with
    # WB_TILE_33_FLAG. It is what stops the construction above being "any clear of $1514 will do" —
    # this one cannot produce the state, because it lowers both words at once.
    assert bytes(harness.BASE_IMAGE[LEVEL_RESET_FLAGS_AT:LEVEL_RESET_FLAGS_AT + len(
        clr_l_abs_w(TILE_33_FLAG))]) == clr_l_abs_w(TILE_33_FLAG), (
        f"{LEVEL_RESET_FLAGS_AT:#x} is not `clr.l $1514.w`")
    assert TILE_33_MODE == TILE_33_FLAG + WORD_BYTES, (
        "WB_TILE_33_MODE is no longer the low half of the longword that `clr.l` takes down, so the "
        "census above no longer says the two words fall together")


# --- the composition: nine calls, the d7 test, and the two guards ---------------------------------
FRAME_CALLS = ("player_meter_empty_check", "player_pending_event_gate", "player_gate_on_1516",
               "player_step_and_arm", "player_weapon_fire", "actor_fall_and_settle",
               "player_apply_joystick", "player_run_map_cell", "player_stage_transition")


def test_the_nine_names_this_battery_iterates_are_the_nine_the_bytes_CALL():
    """FRAME_CALLS is what the coverage rows below iterate, so it has to BE the frame's calls rather
    than a list standing beside them. The entry pin already says the 62 bytes are byte-exact
    (test_behavior.py's `_type01_pieces`); this says the nine names are the nine `bsr` targets those
    bytes hold, IN ORDER — each search starts where the last call ended."""
    body = bytes(harness.BASE_IMAGE[FRAME_ENTRY:FRAME_ENTRY + FRAME_BODY_BYTES])
    at = 0
    for name in FRAME_CALLS:
        # `bsr.w`'s displacement is PC-RELATIVE, so the encoding to look for depends on where the
        # call sits — which is why this walks the body word by word re-encoding rather than
        # searching for one constant.
        while at < len(body) and body[at:at + BSR_W_BYTES] != leaf.asm(FRAME_ENTRY + at,
                                                                       [bsr(name)]):
            at += WORD_BYTES
        assert at < len(body), (
            f"the frame holds no `bsr.w {name}` after the call before it — FRAME_CALLS is not the "
            f"frame's own call order")
        at += BSR_W_BYTES


@pytest.mark.parametrize("guarded,ridden,in_a32", [
    ("both guards raised, so neither call runs", 1, 1),
    ("the fall guard down, so `actor_fall_and_settle` runs", 0, 1),
    ("the collision guard down, so `player_run_map_cell` runs", 1, 0),
    ("both guards down, so all NINE calls run", 0, 0),
], ids=["neither", "fall-only", "cell-only", "all-nine"])
def test_each_guard_clears_EXACTLY_the_one_call_below_it(guarded, ridden, in_a32):
    """THE TWO `tst.w`/`bne.w` PAIRS, as a lattice, with the ORACLE's executed PCs as the witness.

    Each guard skips exactly one `bsr` and nothing else — the fall guard at $a52 reads
    WB_ACTOR_PLATFORM_RIDDEN abs.LONG over `actor_fall_and_settle` alone, and the collision guard at
    $a64 reads WB_STATE_FLAG_A32 abs.w over `player_run_map_cell` alone. A port that let either
    `bne.w` skip the rest of the frame passes the two rows that raise it and fails the other two, and
    one that read either word at the wrong WIDTH fails on the seeded value.

    The `all-nine` row is also this battery's end-to-end case: every one of the nine routines
    executes in one run, and the two cores agree over the whole image."""
    what = f"the whole player frame: {guarded}"
    pokes = _frame_pokes(globals_={PLATFORM_RIDDEN: word(ridden), STATE_FLAG_A32: word(in_a32)})

    with leaf.pc_coverage():
        _run_frame(what, pokes, expected_extend=0)
        ran = {name: emu.cov_visited(leaf.entry_of(name)) for name in FRAME_CALLS}

    expected = {name: True for name in FRAME_CALLS}
    expected["actor_fall_and_settle"] = ridden == 0
    expected["player_run_map_cell"] = in_a32 == 0
    assert ran == expected, (
        f"{what}: the calls the ORIGINAL executed were {sorted(k for k, v in ran.items() if v)}, "
        f"not the ones the two guards name")


def test_a_NEGATIVE_gate_answer_skips_the_seven_calls_below_it():
    """`tst.w d7 / bmi.w $a74` at $a40, with its PREMISE and its CLAIM in ONE run.

    THE PREMISE is that the gate really did leave a negative low word: the seed takes the align
    arm's slot refusal, whose ending is the `move.w #$ffff,d7 / rts` at $d22 — and the witness is
    that instruction's own address, executed. Without it a seed that quietly stopped reaching the
    refusal would leave the claim below true for the wrong reason, since a gate that never ran also
    never reaches the seven calls.

    THE CLAIM is that the `bmi.w` clears SEVEN calls and not one: none of the routines below the
    gate executes, and the frame reports its own `rts`. The gate's two returning endings are one bit
    to this caller, so what the frame propagates on BOTH of them is WB_ACTOR_DISPATCH_RAN — the
    skipped frame is still a frame that returned."""
    what = "the whole player frame: a negative gate answer"
    pokes = _frame_pokes(globals_={ALIGN_REQUEST_B14: word(MARKER), EVENT_ANIM_DONE_B16: word(0),
                                   SPAWN_GATE_SLOT + ACTOR_X: word(PLAYER_X)})

    with leaf.pc_coverage():
        diffs, info = leaf.differential(FRAME_ENTRY, {"a0": ACTOR, "_pokes": pokes},
                                        _FRAME(ACTOR, FRAME_ENTRY_EXTEND), max_insns=FRAME_CAP,
                                        poison=True)
        reached_refusal = emu.cov_visited(GATE_SKIP_WITHOUT_TAIL_AT)
        ran = {name for name in FRAME_CALLS if emu.cov_visited(leaf.entry_of(name))}

    assert not diffs, f"{what}\n{leaf.report(diffs)}"
    assert reached_refusal, (
        f"{what}: the ORIGINAL never executed the align arm's refusal at "
        f"{GATE_SKIP_WITHOUT_TAIL_AT:#x}, so this seed does not make d7 negative and the claim "
        f"below is about a gate that did something else")
    assert ran == {"player_meter_empty_check", "player_pending_event_gate"}, (
        f"{what}: the frame executed {sorted(ran)} — the `bmi.w` at $a40 must clear the SEVEN calls "
        f"below the gate and nothing above it")
    assert info["ret"] == DISPATCH_RAN, (
        f"{what}: the frame reported {info['ret']:#x}, not its own `rts` — a gate that RETURNED is "
        f"not an abandoned frame however negative its d7")


def _frame_over(inner, globals_=None):
    """A CALLEE's own seeding with the frame's five gate words laid over it.

    The nine batteries above each seed the routine they own, and every one of them leaves at least
    one of the frame's gates in a state the frame is not about — the cell battery raises
    WB_SCENE_ALIGN_REQUEST_B14 to a marker, the gate battery seeds no map. So a frame case that
    reuses a callee's seed states the frame's own words LAST, and quiets the walk's record with the
    walk battery's own quiet row so the coast (rather than a keyed byte's map probe) is what runs
    before the call the case is about."""
    quiet = {ACTOR + offset: bytes([value]) for offset, value in _WALK_QUIET_RECORD.items()}
    quiet.update({JOY1_PREV: bytes([0]), JOY1_CURRENT: bytes([0])})
    # FRAME_QUIET_GLOBALS IS OVERLAID RATHER THAN RESTATED: it is the same five gate words
    # `_frame_pokes` uses, and a second copy here is how the two would come to disagree about which
    # arm "quiet" means. (test_behavior.py's `_quiet_record` is the cross-file sibling of this idea —
    # one seed per handler that shuts every arm but the one under test. It is NOT shared: that one is
    # keyed by handler NAME for the dispatch battery's 62 rows and this one composes a callee's own
    # seeding, so they have different shapes and hoisting would fit neither.)
    return leaf.overlay(inner, FRAME_QUIET_GLOBALS, quiet, globals_ or {})


def _run_frame_abandoned(what, pokes, exit_code, stop_pc, via, band=(), cap=None):
    """A frame whose callee never came back. The oracle is stopped at the transfer, the witness above
    it says the arm was really taken, and the frame's report is the CALLEE's own code VERBATIM —
    which is the whole of what the composition does with an ending it cannot follow. A frame that
    renamed the report would be a second spelling of one ending, which is the mistake the shared
    number space at the head of include/player.h's WB_PLAYER_COLLIDE_* block exists to make
    impossible."""
    info = leaf.run_reaching("actor_behavior_type01_player", _FRAME(ACTOR, FRAME_ENTRY_EXTEND),
                             list(band), what, via, regs={"a0": ACTOR, "_pokes": pokes},
                             max_insns=FRAME_CAP if cap is None else cap, stop_pc=stop_pc)
    assert info["ret"] == exit_code, (
        f"{what}: the frame reported {info['ret']:#x}, not the callee's own {exit_code:#x}")
    return info


def test_the_collision_maps_TRIPLE_POP_abandons_the_frame_and_is_reported_as_its_own():
    """WB_PLAYER_COLLIDE_UNWIND, through the frame. `player_run_map_cell`'s tile-$39 arm reaches
    `lea 12(a7),a7 / jmp $e5ba.l`, which discards THREE return addresses — this frame's among them —
    so the frame cannot return and does not pretend to. The seed is the cell battery's own tile-$39
    one with the frame's five gate words laid over it, and the collision guard taken DOWN so the
    call happens at all."""
    what = "the whole player frame: the collision map's triple pop"
    pokes = _frame_over(_cell_pokes(what, TILE_39),
                        {STATE_FLAG_A32: word(0)})

    # What the five calls ABOVE $151a leave: the coast's flag bit inside the record, and the
    # ladder pass's WB_TILE_33_STEP clear. The tile-$39 arm itself writes nothing at all — that is
    # its own battery's claim, and this band is what says the frame added no more.
    _run_frame_abandoned(what, pokes, EXIT_UNWIND, UNWIND_SITE, UNWIND_TAKEN_AT,
                         band=[(ACTOR, RECORD_BYTES), (TILE_33_STEP, WORD_BYTES)])


def test_the_gates_DATA_DISK_unwind_abandons_the_frame_before_any_call_below_it():
    """WB_PLAYER_GATE_DATADISK_UNWIND, through the frame: `lea 4(a7),a7 / jmp $e494.l` at $bd8, ONE
    return address discarded, and it is this frame's. It fires from the SECOND call, so the seven
    below it never run — which is a DIFFERENT fact from the `bmi.w` skip above, where the same seven
    do not run and the frame still returns with a report of its own.

    THE ARM WRITES NOTHING AT ALL and neither do the two calls above it under this seed, so the band
    is empty and the whole image is compared. That is also what makes the witness load-bearing: with
    no writes anywhere, a run that simply returned would agree just as well.

    The gate's own battery drives this ending from `$b1a`; what this adds is that the frame does not
    RENAME the report on its way up. The life-restart unwind is the same shape one arm along, and it
    is left to the gate's battery deliberately — `game_life_restart_reset` redraws the panel, so a
    frame case would have to restate that routine's whole write set to say nothing new."""
    what = "the whole player frame: the gate's data-disk unwind"
    inner = _prompt_pokes(what, box=True, expired=MARKER, lives=2, fire=True)
    pokes = _frame_over(inner, {STAGE_RESET_BLOCK: word(MARKER)})

    _run_frame_abandoned(what, pokes, GATE_EXIT_DATADISK, GATE_DATADISK_SITE,
                         GATE_DATADISK_TAKEN_AT)


# --- the four calls the quiet frame does NOT exercise ---------------------------------------------
#
# EVERY CASE ABOVE PUTS THE FRAME'S FIRST AND LAST CALLS ON THEIR SILENT ARM, which is what a quiet
# seed is for and what the mutation sweep then charged for: `frame/drop-the-death-check` and
# `frame/drop-the-stage-transition` both SURVIVED round one, because a call that writes nothing
# whether or not it happens is a call no differential can see. The two rows below open those arms.
DEATH_CHECK_SLOT_CHARGE = 1     # WB_HUD_SLOT_BBC6's value byte, so the REVIVAL arm runs


def test_the_frame_really_CALLS_the_death_check_when_the_meter_is_empty():
    """`player_meter_empty_check` is the frame's first call and it writes nothing at all while
    WB_HUD_METER_VALUE is nonzero — which every other case here seeds, so that every other case is
    about the eight calls below it. This one empties the meter and arms WB_HUD_SLOT_BBC6, so the
    REVIVAL arm runs: an effect, the slot rearmed, a message posted and the meter refilled. The
    frame's other eight calls run behind it exactly as before, and the whole image is compared."""
    what = "the whole player frame: an EMPTY meter, so the death check's revival arm runs"
    # WB_KEY_SEQUENCE_MATCHED IS NOT SEEDED AND CANNOT BE: it is $604, inside the kit's poked-input
    # block, which lies within this program (project.toml's second waiver) and which
    # `harness.make_image` refuses outright. The shipped image holds ZERO there, which is the arm
    # this case wants — the cheat word down, so the revival SPENDS the slot — and that is a fact
    # about the .PRG rather than a choice, so it is stated here instead of poked.
    pokes = _frame_pokes(globals_={HUD_METER_VALUE: word(0),
                                   HUD_SLOT_BBC6: bytes([DEATH_CHECK_SLOT_CHARGE])})
    assert int.from_bytes(harness.BASE_IMAGE[KEY_SEQUENCE_MATCHED:KEY_SEQUENCE_MATCHED
                                              + WORD_BYTES], "big") == 0, (
        "the shipped cheat word is no longer zero, so this case's revival arm skips the rearm")

    with leaf.pc_coverage():
        _run_frame(what, pokes, expected_extend=0)
        ran = emu.cov_visited(leaf.entry_of("player_meter_empty_check"))
    assert ran, f"{what}: the ORIGINAL never entered the death check"


def test_the_frame_really_CALLS_the_stage_transition_when_nothing_is_latched():
    """...and the mirror at the other end. `player_stage_transition` is an `rts` while its own
    WB_STAGE_ANIM_DONE_B10 latch is up, which every case above raises so that the frame's middle is
    what they measure. With it DOWN the POSTURE SELECTOR runs and publishes the player's sprite,
    which is the arm that runs on every ordinary frame of the game."""
    what = "the whole player frame: nothing latched, so the posture selector runs"
    pokes = _frame_pokes(globals_={STAGE_ANIM_DONE_B10: word(0),
                                   STAGE_ANIM_REQUEST_B0E: word(0), EVENT_ANIM_DONE_B16: word(0),
                                   STAGE_RESET_BLOCK: word(0)})

    with leaf.pc_coverage():
        _run_frame(what, pokes, expected_extend=0)
        ran = emu.cov_visited(leaf.entry_of("player_stage_transition"))
    assert ran, f"{what}: the ORIGINAL never entered the stage transition"


# The word ABOVE the fall guard's: two shipped ZERO bytes between WB_ACTOR_PLATFORM_RIDDEN and slot
# 55's entry at $6ef4. Nothing in the image names it, which is exactly what makes it the right place
# to put a value: a LONGWORD read of the guard's address sees it and a WORD read does not.
PLATFORM_RIDDEN_NEIGHBOUR = PLATFORM_RIDDEN + WORD_BYTES


def test_the_fall_guard_reads_a_WORD_and_not_the_LONGWORD_below_it():
    """`tst.w $6ef0.l` — and the `.w` is the half a write-set case cannot see, because both widths
    agree on every value the game itself puts there. The sweep charged for that too
    (`frame/the-fall-guard-read-as-a-LONGWORD` survived round one).

    So this row seeds the guard's own word CLEAR and the word above it SET. A word read says "run the
    fall"; a longword read says "skip it". The witness is the ORACLE's executed PCs, and the
    differential behind it is what makes the reconstruction answer the same question."""
    what = "the whole player frame: a WORD-wide fall guard over a nonzero neighbour"
    pokes = _frame_pokes(globals_={PLATFORM_RIDDEN: word(0),
                                   PLATFORM_RIDDEN_NEIGHBOUR: word(MARKER)})

    with leaf.pc_coverage():
        _run_frame(what, pokes, expected_extend=0)
        ran = emu.cov_visited(leaf.entry_of("actor_fall_and_settle"))
    assert ran, (
        f"{what}: the fall did not run, so the guard was read wider than the WORD its `tst.w` names")


def test_a_dispatched_frame_that_ABANDONS_reports_it_all_the_way_up():
    """THE OTHER HALF OF THE ROW FLIP, and the sweep is what asked for it: with only the quiet
    dispatch rows above, an adapter that threw the frame's report away and answered
    WB_ACTOR_DISPATCH_RAN survived, because a quiet frame answers RAN anyway.

    This one enters at `actor_dispatch_behavior` with a type-1 record whose collision cell is
    WB_MAP_TILE_39, so the frame's eighth call reaches the `lea 12(a7),a7 / jmp $e5ba.l` at $1622 and
    never comes back. The dispatcher has to hand WB_PLAYER_COLLIDE_UNWIND up unchanged — which is the
    whole reason the three exit-code families share one number space."""
    what = "the dispatched player frame: the collision map's triple pop, reported through $928"
    pokes = _frame_over(_cell_pokes(what, TILE_39), {STATE_FLAG_A32: word(0),
                                                     ACTOR + ACTOR_TYPE: word(TYPE_PLAYER)})

    info = leaf.run_reaching("actor_dispatch_behavior", _BEHAVIOR_DISPATCH(ACTOR),
                             [(ACTOR, RECORD_BYTES), (TILE_33_STEP, WORD_BYTES)], what,
                             UNWIND_TAKEN_AT, regs={"a0": ACTOR, "_pokes": pokes},
                             max_insns=FRAME_CAP + DISPATCH_INSNS, stop_pc=UNWIND_SITE)
    assert info["ret"] == EXIT_UNWIND, (
        f"{what}: the dispatcher reported {info['ret']:#x}, not the frame's own {EXIT_UNWIND:#x} — "
        f"a row's answer is the dispatcher's answer")


# --- the arm that DESTROYS the entry bit, and the one place the frame refuses ----------------------
#
# THE GATE FOUND THIS AND THE BYTES CONFIRM IT: `player_meter_empty_check`'s two sound-calling arms
# end on a `jsr` into the sound module — the revival's `jsr 56(a1)` at $a9e and the death's
# `jsr (a1)` at $aec — and every instruction below either call, plus the whole of
# `player_pending_event_gate`'s no-event path, is X-silent. So on those two paths the bit arriving at
# `$a46` is `snd_trigger_effect`'s or `snd_play_song`'s and NOT the dispatcher's, and the four rows
# above that call the entry bit "the dispatcher's" are true only of the arms where `$a76` is silent.
#
# WHICH IS A MEASUREMENT AND NOT A READING. Driven under the ORACLE, a revival + ladder + fire frame
# leaves the borrow-0 spend for BOTH type $0001 and type $4001 — so the sound routine really does
# overwrite the dispatcher's bit, and a port that handed the walk `entry_extend` there would answer
# the aliased row with the wrong count. The port refuses instead: see WB_PLAYER_FRAME_SOUND_EXTEND.
REVIVAL_GLOBALS = {HUD_METER_VALUE: word(0), HUD_SLOT_BBC6: bytes([DEATH_CHECK_SLOT_CHARGE])}
FRAME_SOUND_EXTEND = wb("PLAYER_FRAME_SOUND_EXTEND")


@pytest.mark.parametrize("type_word", TYPE_PLAYER_ALIASES, ids=lambda v: f"type-{v:04x}")
def test_a_revival_on_a_LADDER_frame_refuses_instead_of_guessing_the_sounds_bit(type_word):
    """THE REFUSAL, one row per alias, and the aliased rows are the point: whatever the dispatcher
    shifted out, the death check has overwritten it by `$a46`, so a port that still trusted
    `entry_extend` would spend a different count on two of these four and the same count by luck on
    the other two.

    The oracle is stopped at `$a4a` — the walk's own `bsr`, which is exactly where the port stops —
    so what the differential compares is the image at the instant the bit would have been consumed.
    Everything above it (the death check's whole revival arm and the gate's ladder `rts`) has run in
    both cores."""
    what = f"the frame's revival + ladder refusal, type {type_word:#06x}"
    pokes = leaf.overlay(_frame_pokes(ladder=True),
                         REVIVAL_GLOBALS, {ACTOR + ACTOR_TYPE: word(type_word)})

    # POISON IS OFF HERE AND THE REASON IS THIS ARM'S OWN. The revival WRITES the two words that
    # SELECT it — WB_HUD_METER_VALUE refilled and WB_HUD_SLOT_BBC6 rearmed — so the attribution pass,
    # which re-runs both cores over an image whose oracle-written bytes are poisoned, hands the
    # second run a meter that is no longer empty. The ORACLE still stops at the fixed `$a4a`; the
    # PORT's stopping point is arm-dependent and it no longer refuses, so it runs the weapon and the
    # two disagree about a frame neither case is about. Every other frame row keeps poison on.
    info = leaf.run("actor_behavior_type01_player", _FRAME(ACTOR, FRAME_ENTRY_EXTEND),
                    [(0, loader.PROGRAM_END)], what, regs={"a0": ACTOR, "_pokes": pokes},
                    max_insns=FRAME_CAP, stop_pc=WALK_CALL_AT, poison=False)
    assert info["ret"] == FRAME_SOUND_EXTEND, (
        f"{what}: the frame reported {info['ret']:#x} — a revival frame on the ladder arm carries "
        f"an X no reader of this port has, and guessing it is what this code refuses to do")


def test_a_revival_on_a_JUMPING_frame_runs_WHOLE_because_the_gate_overwrites_the_bit():
    """THE OTHER SIDE OF THE REFUSAL, and what keeps it from being a blanket one. With
    WB_TILE_33_MODE clear the gate runs `player_jump_step`, whose head stamps `addi.b #$8,d0` into X
    before any arm is chosen — so the sound routine's bit is gone and nothing is unknown. The frame
    runs to its own `rts` and spends the count that head's carry says.

    This is what makes the refusal SCOPED rather than "any frame that revives", and it is the row a
    port that refused on the death check alone would fail."""
    what = "the whole player frame: a revival on a JUMPING frame, which is not a refusal"
    pokes = leaf.overlay(_frame_pokes(strength=JUMP_STRENGTH_CARRY), REVIVAL_GLOBALS)

    _run_frame(what, pokes, expected_extend=1)


def test_a_DEATH_frame_never_reaches_the_refusal_because_the_gate_eats_it_first():
    """THE DEATH ARM'S SENTINEL IS UNREACHABLE AT THE CHECK, and this is the proof rather than the
    assertion. The sweep flagged `refusal/the-death-arm-does-not-mark-the-bit` as a survivor; it is
    EQUIVALENT, and the mechanism is the frame's own ordering.

    `player_die` raises WB_STAGE_RESET_BLOCK ($b08) at $aee — and that is the FIRST word
    `player_pending_event_gate` tests, three instructions into its own body. So any frame on which
    the death arm runs hands the gate a raised block, the gate takes its DEATH arm, and no death arm
    of the gate returns WB_PLAYER_GATE_FRAME_RUNS — which means `$a40`'s `bmi.w` or an unwind ends
    the frame before `$a46` is ever reached. The sentinel is written and then thrown away with the
    frame.

    THE OTHER HALF, and why the C still writes it: the early return in `player_die` (a block already
    negative) makes no sound call and marks nothing, so "the death check marked the bit" and "the
    gate will eat the frame" are the same condition. Removing the mark would leave the model of the
    flag wrong for a reader, which is what the plate is for; keeping it costs one store.

    The two words are pinned against each other from the image, and the run is the CANDIDATE's
    because the oracle needs a PSG declaration the death song makes unpredictable here — what is
    being pinned is a control-flow fact about the port, and the gate's own battery pins the arm."""
    what = "the whole player frame: a death frame is eaten by the gate before the refusal"
    pokes = leaf.overlay(_frame_pokes(ladder=True),
                         {HUD_METER_VALUE: word(0), HUD_SLOT_BBC6: bytes([0]),
                          STAGE_RESET_BLOCK: word(0)})

    report, image = leaf.run_candidate_only(_FRAME(ACTOR, FRAME_ENTRY_EXTEND), pokes)
    assert report != FRAME_SOUND_EXTEND, (
        f"{what}: the frame reported the sound refusal, so the death arm's sentinel DID reach "
        f"$a46 — the ordering this case rests on has moved and the arm needs a row of its own")
    assert int.from_bytes(image[STAGE_RESET_BLOCK:STAGE_RESET_BLOCK + WORD_BYTES], "big") \
        == DEATH_FLAG_SET, (
        f"{what}: the death arm did not raise WB_STAGE_RESET_BLOCK, so this seed never drove it")
