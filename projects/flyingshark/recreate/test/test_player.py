"""Differential battery for the player subsystem — src/player.c.

WHERE THE CASES' WORLDS COME FROM. Three kinds, because the subsystem has three kinds of routine:

* a LEAF that takes the player record in A0 (`player_move_*`, `bomb_drop`, `player_frame_from_bank`)
  is driven over a 7-byte record poked into `abi.SCRATCH`, so a case can spell an x or a y the
  game's own clamps never produce — which is the only way to reach the gates' far side;
* a routine that reaches the REAL player record and its globals (`player_script_step`,
  `player_publish`, `read_player_input`, both collision passes) is driven over `A_player` itself
  with the state it reads poked around it;
* the level-flow pair (`level_progress_check`, `restart_level_at_checkpoint_setup`) runs on a
  STARTED LEVEL that the original built: `started_level_pokes` runs the game's own `start_level`
  @ 0x11440 under the oracle on top of `post_new_game_image`, so the level record, the spawn script
  pointer, the scroll globals and the plane's take-off state are the game's rather than a test's.

THE STAGED IMAGE REACHES A CASE AS POKES rather than as a base image, because `differential()` takes
its memory from `harness.set_base_image` and `conftest.py`'s autouse fixture owns that (README.md,
"Adding a function", step 4). `conftest.byte_run_pokes` is the conversion, and the two staged
worlds it converts — `new_game_pokes` and `staged_world_pokes` — are conftest's, built once a run.

FIVE SEAMS, and every one of them is a routine that never returns:

* `STOP_SCORE_ADD_200` — the collision pass's hit arm ends `bra.w score_add_200`, whose `abcd`
  chain adds the X FLAG the sound module's `sfx_start` left two instructions earlier. That X is not
  the collision routine's to know, so the hit is diffed at the branch;
* `STOP_RESTART_LEVEL` — the death sequence's "lives left" arm unwinds its caller into
  `restart_level_at_checkpoint`, of which only the head is reconstructed;
* `STOP_MAIN_REENTRY` — the death sequence's game-over arm and `read_player_input`'s ABORT key both
  reach `game_over_hiscore_check`, which IS verified and is therefore CALLED: the stop is that
  routine's own re-entry into `main`, so the two are diffed through the whole hall-of-fame walk;
* `STOP_FRAME_LOOP_REENTRY` — `level_progress_check`'s level-advance arm unwinds the same way;
* `STOP_CONSOLE_SHOW_MESSAGE` — `player_fire`'s debug-overlay arm calls `debug_show_counters`,
  which FALLS THROUGH into a console routine that spins on the fire button. The overlay flag is
  written nowhere in the image, so the arm is unreachable in the shipped game; the case drives it
  with the flag poked and stops at the fall-through.

THE PAUSE KEY IS A SCHEDULED WAIT. It spins on `joy1_state`, a byte only the ACIA interrupt writes,
so the reconstruction reads it through `sched_poll8` and the harness compares the candidate's polls
against the oracle's arrivals at the same PC. Without the schedule a case could only ever run the
loop zero times, on both sides, and would compare nothing about it.
"""
import ctypes
import random

import pytest

import abi
import conftest
import emu
import harness
from harness import differential, report

MIRROR_HEADER = "include/player.h"

# ---- entries -------------------------------------------------------------------------------------
ENTRY_PLAYER_VS_ENTITIES = 0x10f26
ENTRY_PLAYER_VS_ENTITIES_GROUP_A4 = 0x10f70
ENTRY_PLAYER_VS_ENTITIES_GROUP = 0x10f88
ENTRY_PLAYER_VS_ENTITY_GROUP_TEST = 0x10fa0
ENTRY_PLAYER_VS_ENEMY_BULLETS = 0x1101c
ENTRY_LEVEL_PROGRESS_CHECK = 0x124ae
ENTRY_TAKEOFF_SCRIPT_RESET = 0x139e4
ENTRY_LANDING_SCRIPT_RESET = 0x13a02
ENTRY_PLAYER_SCRIPT_STEP = 0x13a20
ENTRY_PLAYER_BANK_RECENTRE = 0x13baa
ENTRY_PLAYER_DEATH_SEQUENCE_STEP = 0x13bd6
ENTRY_PLAYER_PUBLISH = 0x13c96
ENTRY_PLAYER_FRAME_FROM_BANK = 0x13d12
ENTRY_PLAYER_RESET_TO_START = 0x13d24
ENTRY_BOMB_DROP = 0x13d5c
ENTRY_PLAYER_MOVE_UP = 0x13da0
ENTRY_PLAYER_MOVE_DOWN = 0x13db0
ENTRY_PLAYER_MOVE_LEFT = 0x13dc2
ENTRY_PLAYER_MOVE_RIGHT = 0x13de8
ENTRY_PLAYER_FIRE = 0x13e12
ENTRY_PLAYER_SHOT_SLOT_ALLOC = 0x13e4e
ENTRY_PLAYER_FIRE_BY_WEAPON_LEVEL = 0x13ebc
ENTRY_FIRE_PATTERN_LEVEL0 = 0x13ee0
ENTRY_FIRE_PATTERN_LEVEL1 = 0x13f20
ENTRY_FIRE_PATTERN_LEVEL2 = 0x13f72
ENTRY_FIRE_PATTERN_LEVEL3 = 0x13fda
ENTRY_FIRE_PATTERN_LEVEL4 = 0x1404c
ENTRY_READ_PLAYER_INPUT = 0x14354
ENTRY_RESTART_LEVEL_SETUP = 0x14aac   # the SLICE's start: `st level_just_started`

# ---- the seams -------------------------------------------------------------------------------------
STOP_SCORE_ADD_200 = 0x11018        # `bra.w score_add_200` — the hit arm's tail
STOP_FRAME_LOOP_REENTRY = 0x1251a   # `addq.l #4,a7` before `bra.w $15758`
STOP_CLEAR_ACTOR_ARRAYS = 0x14b22   # `bsr.w $115e2` — where the restart slice ends
STOP_RESTART_LEVEL = 0x14aa8        # `bra.w restart_level_at_checkpoint`
STOP_CONSOLE_SHOW_MESSAGE = 0x14996 # `debug_show_counters` falls through here, it does not return
STOP_MAIN_REENTRY = 0x15754         # `game_over_hiscore_check`'s own re-entry into main

# ---- mirrors of include/player.h and its neighbours ------------------------------------------------
A_player = 0x190a4
PLAYER_X, PLAYER_Y, PLAYER_FRAME = 0, 2, 4
PLAYER_SHADOW_FRAME, PLAYER_MODE, PLAYER_RECORD_BYTES = 5, 6, 7
PLAYER_MODE_JOYSTICK, PLAYER_MODE_LANDING, PLAYER_MODE_FLYOFF = 0, 1, 2
PLAYER_MODE_DYING, PLAYER_MODE_GAMEOVER, PLAYER_MODE_TAKEOFF = 3, 4, 0xff

A_player_start_template = 0x1909c
A_takeoff_start_pos, A_landing_start_pos = 0x190ac, 0x190b6
A_takeoff_script, A_takeoff_script_cursor = 0x17726, 0x17724
A_landing_script, A_landing_script_cursor = 0x17730, 0x1773a
SCRIPT_TEMPLATE_WORDS, SCRIPT_STEP_BYTES, SCRIPT_STEP_FRAME = 5, 4, 3

A_player_input_locked, A_player_turning = 0x1775e, 0x1775c
A_player_script_timer, A_player_script_fire_enable = 0x176c4, 0x1770c
A_shadow_offset = 0x1773c
A_takeoff_shadow_timer, A_landing_shadow_timer = 0x1773e, 0x17740
A_landing_bomb_cash_timer, A_level_complete = 0x176c0, 0x1775a
SHADOW_OFFSET_LANDED, SHADOW_OFFSET_AIRBORNE = 0, 0x20
TAKEOFF_SHADOW_PERIOD, LANDING_SHADOW_PERIOD, BOMB_CASH_PERIOD = 3, 2, 0xa
SHADOW_FRAME_AIRBORNE, SHADOW_FRAME_ON_DECK, SHADOW_FRAME_OFFSET = 0xff, 1, 7
FLYOFF_TARGET_X, FLYOFF_TARGET_Y, FLYOFF_HOVER_FRAMES = 0x8f, 0x7e, 0x16

A_player_bank, A_player_bank_frames, PLAYER_BANK_CENTRE = 0x17742, 0x17744, 7
PLAYER_STEP_PIXELS, PLAYER_Y_MIN, PLAYER_Y_MAX, PLAYER_X_MAX = 6, 0xc, 0xba, 0x120
PLAYER_BANK_STEPS = 13          # the table's twelve live bytes plus the sentinel above them

A_player_death_frames, A_death_anim_cursor = 0x19210, 0x176f6
DEATH_FRAME_BYTES, DEATH_SINK_PIXELS = 2, 2
DEATH_FRAMES_SHIPPED = 7        # 0x19210's words before its first negative one

A_dl_player, A_dl_player_shadow = 0x17d02, 0x17cfc
A_text_game_over, A_dl_bomb_icons = 0x1613a, 0x17c36
A_game_over_flag, A_game_over_delay = 0x1769a, 0x176aa
A_const_words_0123, CONST_WORD_BYTES = 0x176ac, 2
LIVES_AFTER_GAME_OVER, BOMBS_AFTER_GAME_OVER = 1, 0

A_bomb_falling, A_bomb_exploding, A_player_bomb = 0x176ee, 0x176f0, 0x5aed6
BOMB_X, BOMB_START_Y = 0, 2
BOMB_DROP_X_OFFSET, BOMBS_MIN_TO_DROP = 0xc, 1

A_fire_held, A_shot_slots_full = 0x17760, 0x17762
A_weapon_fire_tbl, WEAPON_FIRE_PTR_BYTES, WEAPON_LEVEL_MAX = 0x19232, 4, 4
A_debug_overlay_flag, SFX_PLAYER_FIRE = 0x177cd, 0xb
A_player_shot_slot_0, PLAYER_SHOT_SLOTS = 0x19422, 3
PLAYER_SHOT_BULLETS, PLAYER_SHOT_TABLE_STRIDE = 5, 0x14
A_shot_slot_busy_0, SHOT_SLOT_BUSY_BYTES = 0x17716, 2
PLAYER_BULLET_X, PLAYER_BULLET_Y, PLAYER_BULLET_DX = 0, 2, 4
PLAYER_BULLET_STATE, PLAYER_BULLET_BYTES = 6, 8
BULLET_MUZZLE_DY = 0xa

PLAYER_HIT_BOX_W, PLAYER_HIT_BOX_H = 0x1c, 0x18
ENTITY_BOX_DX, ENTITY_BOX_DY, ENTITY_BOX_H, ENTITY_BOX_W = 0x11, 0xc, 0x17, 0x1b
ENTITY_A_GROUP_SLOTS = 7
ENTITY_BOX_A4_DX, ENTITY_BOX_A4_DY, ENTITY_BOX_A4_H, ENTITY_BOX_A4_W = 4, 3, 0x1b, 0x39
ENTITY_A4_GROUP_SLOTS = 4
ENEMY_BULLET_HIT_OFFSET, ENEMY_BULLET_SLOTS = 0x10, 16
A_enemy_bullets, ENEMY_BULLET_BYTES = 0x1946e, 10
ENEMY_BULLET_X, ENEMY_BULLET_Y, ENEMY_BULLET_ACTIVE = 0, 2, 8

A_entity_group_a0, A_entity_group_a1 = 0x19246, 0x19262
A_entity_group_a2, A_entity_group_a3, A_entity_group_a4 = 0x1927e, 0x1929a, 0x1945e
ENTITY_GROUP_PTR_BYTES, ENTITY_STRIDE = 4, 58
ENTITY_X, ENTITY_Y, ENTITY_ACTIVE, ENTITY_DYING = 0, 2, 14, 16

A_sprite_bank, SPRITE_RECORD_BYTES = 0x1be36, 20
SPRITE_REC_DRAW_DX, SPRITE_REC_DRAW_DY = 8, 10
SPRITE_REC_HIT_W, SPRITE_REC_HIT_H = 16, 18

A_level_end_scroll_pos, A_boss_scroll_pos = 0x1771c, 0x1770a
A_level_number, LEVELS, LEVEL_CLEAR_TUNE = 0x1642a, 5, 0
A_level_loop_flag_1, A_level_loop_flag_2, A_level_loop_flag_3 = 0x1769c, 0x1769e, 0x176a0
LEVEL_LOOP_1_START, LEVEL_LOOP_2_START, LEVEL_LOOP_3_START = 1, 2, 3
A_scroll_pos, A_player_hit = 0x17758, 0x17706
A_level_just_started, A_joy0_state, A_joy1_state, A_key_bits = 0x17696, 0x1777e, 0x1777f, 0x17780
A_use_keyboard_flag, A_key_last_scancode = 0x1770e, 0x17781
A_invuln_flag, A_infinite_lives_flag, A_infinite_bombs_flag = 0x177c6, 0x177c7, 0x177c8
A_max_weapon_flag = 0x177ca
A_lives, A_bombs, A_weapon_level = 0x17712, 0x17710, 0x17714
A_music_suspend_flag = 0x176a4
A_sound_module, SND_SFX_ACTIVE = 0x58944, 0x1f

A_checkpoint_tables = 0x15ab0
A_checkpoint_map_offset, A_checkpoint_scroll_pos, A_checkpoint_scroll_fine = 0x176fc, 0x17704, 0x17702
CHECKPOINT_TABLE_PTR_BYTES, CHECKPOINT_REC_BYTES = 4, 6
CHECKPOINT_REC_MAP_OFFSET, CHECKPOINT_REC_SCROLL_POS, CHECKPOINT_REC_SCROLL_FINE = 0, 2, 4
CHECKPOINT_SCAN_FROM, CHECKPOINT_SCROLL_BACK = 0x26, 0xd8
CHECKPOINT_RECORDS = 7          # the seven six-byte records each shipped table holds

SCORE_AWARD_3000, EXTEND_CLEAR = 6, 0
SCC_TRUE = 0xff

# Bit positions src/player.c names, restated so a case can spell a stick state.
JOY_UP_BIT, JOY_DOWN_BIT, JOY_LEFT_BIT, JOY_RIGHT_BIT, JOY_FIRE_BIT = 0, 1, 2, 3, 7
KEY_PAUSE_BIT, KEY_ABORT_BIT, KEY_BOMB_BIT = 1, 2, 5
PAUSE_WAIT_PC = 0x14394

# Where a case parks the things it invents.
SCRATCH_PLAYER = abi.SCRATCH
SCRATCH_SLOT_TABLE = abi.SCRATCH + 0x100      # five bullet POINTERS
SCRATCH_BULLETS = abi.SCRATCH + 0x200         # ...and the five 8-byte records they point at
SCRATCH_ENTITIES = abi.SCRATCH + 0x400        # seven entity records for a poked group
SCRATCH_GROUP = abi.SCRATCH + 0x800           # ...and the pointer array that names them

# ---- the glue's C signatures -----------------------------------------------------------------------
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
_GLUE_ARGS = {
    "g_takeoff_script_reset": 0, "g_landing_script_reset": 0, "g_player_script_step": 0,
    "g_player_bank_recentre": 0, "g_player_reset_to_start": 0, "g_player_shot_slot_alloc": 0,
    "g_player_fire": 0, "g_read_player_input": 0, "g_player_vs_entities": 0,
    "g_player_vs_enemy_bullets": 0, "g_level_progress_check": 0,
    "g_restart_level_at_checkpoint_setup": 0,
    "g_player_frame_from_bank": 1, "g_player_move_up": 1, "g_player_move_down": 1,
    "g_player_move_left": 1, "g_player_move_right": 1, "g_bomb_drop": 1,
    "g_fire_pattern_level0": 1, "g_fire_pattern_level1": 1, "g_fire_pattern_level2": 1,
    "g_fire_pattern_level3": 1, "g_fire_pattern_level4": 1, "g_player_fire_by_weapon_level": 1,
    "g_player_vs_entities_group": 1, "g_player_vs_entities_group_a4": 1,
    "g_player_publish": 2,
    "g_player_death_sequence_step": 3,
    "g_player_vs_entity_group_test": 6,
}
for _name, _extra in _GLUE_ARGS.items():
    _fn = getattr(harness._lib, _name)
    _fn.argtypes = [_IMAGE] + [ctypes.c_uint32] * _extra
    _fn.restype = None


def _case(entry, regs, glue, stop_pc=0, poison=False, note="", schedule=None):
    diffs, _info = differential(entry, regs, glue, stop_pc=stop_pc, poison=poison,
                                schedule=schedule)
    assert not diffs, f"{note}\n{report(diffs)}"


def word(value):
    return (value & 0xffff).to_bytes(2, "big")


def long_word(value):
    return (value & 0xffffffff).to_bytes(4, "big")


def player_record(x=0, y=0, frame=0, shadow=0, mode=PLAYER_MODE_JOYSTICK):
    return word(x) + word(y) + bytes([frame & 0xff, shadow & 0xff, mode & 0xff])


def entity_record(x=0, y=0, active=0, dying=0):
    record = bytearray(ENTITY_STRIDE)
    record[ENTITY_X:ENTITY_X + 2] = word(x)
    record[ENTITY_Y:ENTITY_Y + 2] = word(y)
    record[ENTITY_ACTIVE:ENTITY_ACTIVE + 2] = word(active)
    record[ENTITY_DYING:ENTITY_DYING + 2] = word(dying)
    return bytes(record)


def bullet_record(x=0, y=0, dx=0, state=0):
    """One of the PLAYER's 8-byte shot records — x, y, dx, state."""
    return word(x) + word(y) + word(dx) + word(state)


def enemy_bullet_record(x=0, y=0, dx=0, dy=0, active=0):
    """...and one of the ENEMY'S TEN-byte ones, whose active word is at +8 and NOT at +6.

    Spelt separately because the two records are nearly the same shape and are not: writing the
    active flag at the player bullet's offset left every enemy bullet in this battery INACTIVE, so
    `player_vs_enemy_bullets` was verified entirely on its skip path and both
    `ENEMY_BULLET_HIT_OFFSET 0x10 -> 0xf` and `ENEMY_BULLET_SLOTS 16 -> 15` survived it
    (measured 2026-09-07).
    """
    record = bytearray(ENEMY_BULLET_BYTES)
    record[ENEMY_BULLET_X:ENEMY_BULLET_X + 2] = word(x)
    record[ENEMY_BULLET_Y:ENEMY_BULLET_Y + 2] = word(y)
    record[4:6], record[6:8] = word(dx), word(dy)
    record[ENEMY_BULLET_ACTIVE:ENEMY_BULLET_ACTIVE + 2] = word(active)
    return bytes(record)


# ---- the staged worlds -----------------------------------------------------------------------------
ENTRY_START_LEVEL = 0x11440
START_LEVEL_MAX_INSNS = 200_000_000


@pytest.fixture(scope="session")
def started_level_pokes(post_load_image, post_new_game_image):
    """A STARTED LEVEL the original built, as pokes.

    `start_level` @ 0x11440 is what the front end runs between the title screen and the frame loop:
    it resets the plane on to its take-off script, installs level 0's record (the end-of-level and
    boss scroll positions, the tune, the spawn script), rewinds the map cursor and prescrolls the
    first screen. Everything the level-flow routines read is therefore the GAME'S, and a case that
    poked those globals by hand could only contain the numbers its author thought of.
    """
    final, _writes, _regs = emu.run(bytearray(post_new_game_image), ENTRY_START_LEVEL,
                                    max_insns=START_LEVEL_MAX_INSNS)
    image = bytearray(final)
    assert int.from_bytes(image[A_level_end_scroll_pos:A_level_end_scroll_pos + 2], "big") != 0, (
        "start_level left no end-of-level scroll position — the level record never loaded, and "
        "every level_progress_check case would run against a zero the game never has")
    return conftest.byte_run_pokes(post_load_image, image)


# ==================================================================================================
# takeoff_script_reset @ 0x139e4 and landing_script_reset @ 0x13a02
# ==================================================================================================
_SCRIPT_RESETS = {
    "takeoff": (ENTRY_TAKEOFF_SCRIPT_RESET, "g_takeoff_script_reset",
                A_takeoff_start_pos, A_takeoff_script, A_takeoff_script_cursor),
    "landing": (ENTRY_LANDING_SCRIPT_RESET, "g_landing_script_reset",
                A_landing_start_pos, A_landing_script, A_landing_script_cursor),
}


@pytest.mark.parametrize("which", sorted(_SCRIPT_RESETS))
def test_script_reset_copies_the_shipped_template(which):
    """Over the game's OWN template, with the live script and its cursor dirtied first — so a copy
    that stopped one word short leaves the dirt behind rather than agreeing with a zero."""
    entry, glue, _template, script, cursor = _SCRIPT_RESETS[which]
    pokes = {script: bytes([0xa5] * (2 * SCRIPT_TEMPLATE_WORDS)), cursor: word(0xbeef)}
    _case(entry, {"_pokes": pokes}, lambda lib, buf: getattr(lib, glue)(buf), poison=True,
          note=f"{which} over the shipped template")


@pytest.mark.parametrize("which", sorted(_SCRIPT_RESETS))
def test_script_reset_copies_five_words_and_no_sixth(which):
    """A seeded template with a SIXTH distinctive word behind it: a copy of six leaves it in the
    script, and one of four leaves the dirt in word five."""
    entry, glue, template, script, cursor = _SCRIPT_RESETS[which]
    seed = b"".join(word(0x1000 + step) for step in range(SCRIPT_TEMPLATE_WORDS + 1))
    pokes = {template: seed, script: bytes([0x5a] * (2 * (SCRIPT_TEMPLATE_WORDS + 1))),
             cursor: word(0x1234)}
    _case(entry, {"_pokes": pokes}, lambda lib, buf: getattr(lib, glue)(buf), poison=True,
          note=f"{which} over a seeded template")


# ==================================================================================================
# The four move routines @ 0x13da0 / 0x13db0 / 0x13dc2 / 0x13de8
# ==================================================================================================
def _move_case(entry, glue, record, extra_pokes=None, note=""):
    pokes = {SCRATCH_PLAYER: record}
    pokes.update(extra_pokes or {})
    _case(entry, {"a0": SCRATCH_PLAYER, "_pokes": pokes},
          lambda lib, buf: getattr(lib, glue)(buf, SCRATCH_PLAYER), note=note)


@pytest.mark.parametrize("y", (0, 1, PLAYER_Y_MIN - 1, PLAYER_Y_MIN, PLAYER_Y_MIN + 1,
                               PLAYER_Y_MAX, 0x7fff, 0x8000, 0xfffa, 0xffff))
def test_move_up_refuses_below_the_ceiling_rather_than_clamping(y):
    """`cmpi.w #$c,2(a0) / blt` is a SIGNED gate, so a NEGATIVE y is refused too — and a y one step
    above the limit is stepped past it rather than snapped to it."""
    _move_case(ENTRY_PLAYER_MOVE_UP, "g_player_move_up", player_record(x=0x40, y=y),
               note=f"y={y:#x}")


@pytest.mark.parametrize("y", (0, PLAYER_Y_MAX - 1, PLAYER_Y_MAX, PLAYER_Y_MAX + 1,
                               0x7ffa, 0x7fff, 0x8000, 0xffff))
def test_move_down_refuses_past_the_floor(y):
    """...and `bgt` at the other end, which lets every negative y through — 0xffff moves DOWN."""
    _move_case(ENTRY_PLAYER_MOVE_DOWN, "g_player_move_down", player_record(x=0x40, y=y),
               note=f"y={y:#x}")


@pytest.mark.parametrize("bank", range(PLAYER_BANK_STEPS))
@pytest.mark.parametrize("x", (0, 1, PLAYER_STEP_PIXELS, 0x8000, 0xffff))
def test_move_left_gates_on_x_and_on_the_bank_table_sentinel(bank, x):
    """Two gates, and neither is a clamp: x must be strictly positive (`beq` AND `bmi` both refuse),
    and the bank steps down only while the byte BEFORE it in `player_bank_frames` is positive."""
    _move_case(ENTRY_PLAYER_MOVE_LEFT, "g_player_move_left", player_record(x=x, y=0x40),
               {A_player_bank: word(bank)}, note=f"x={x:#x} bank={bank}")


@pytest.mark.parametrize("bank", range(PLAYER_BANK_STEPS))
@pytest.mark.parametrize("x", (0, PLAYER_X_MAX - 1, PLAYER_X_MAX, PLAYER_X_MAX + 1, 0x8000, 0xffff))
def test_move_right_gates_on_x_and_on_the_bank_table_sentinel(bank, x):
    _move_case(ENTRY_PLAYER_MOVE_RIGHT, "g_player_move_right", player_record(x=x, y=0x40),
               {A_player_bank: word(bank)}, note=f"x={x:#x} bank={bank}")


def _seeded_bank_table():
    """A bank table whose live bytes are all distinct and whose SENTINELS are where the shipped
    one's are — so a frame read one step off cannot agree by repetition."""
    table = bytearray(PLAYER_BANK_STEPS + 1)
    table[0] = 0x80
    for step in range(1, PLAYER_BANK_STEPS - 1):
        table[step] = 0x10 + step
    table[PLAYER_BANK_STEPS - 1] = 0xfe
    table[PLAYER_BANK_STEPS] = 0x33
    return bytes(table)


@pytest.mark.parametrize("bank", range(PLAYER_BANK_STEPS))
def test_move_left_and_right_over_a_seeded_bank_table(bank):
    """The shipped table repeats ids (1 1 1 2 2 2 ...), so a routine that stepped the bank the wrong
    way would still stamp the same frame from several of them. These bytes are all different."""
    pokes = {A_player_bank: word(bank), A_player_bank_frames: _seeded_bank_table()}
    _move_case(ENTRY_PLAYER_MOVE_LEFT, "g_player_move_left", player_record(x=0x40, y=0x40), pokes,
               note=f"left bank={bank}")
    _move_case(ENTRY_PLAYER_MOVE_RIGHT, "g_player_move_right", player_record(x=0x40, y=0x40), pokes,
               note=f"right bank={bank}")


# ==================================================================================================
# player_bank_recentre @ 0x13baa and player_frame_from_bank @ 0x13d12
# ==================================================================================================
@pytest.mark.parametrize("turning", (0, 1, 0xff00, 0xffff))
@pytest.mark.parametrize("bank", (0, PLAYER_BANK_CENTRE - 1, PLAYER_BANK_CENTRE,
                                  PLAYER_BANK_CENTRE + 1, PLAYER_BANK_STEPS, 0x8000, 0xffff))
def test_bank_recentre_drifts_one_step_toward_centre(turning, bank):
    """It moves ONE step and only while `player_turning` is clear; the compare is signed, so a bank
    of 0xffff climbs rather than falling."""
    _case(ENTRY_PLAYER_BANK_RECENTRE,
          {"_pokes": {A_player_turning: word(turning), A_player_bank: word(bank)}},
          lambda lib, buf: lib.g_player_bank_recentre(buf), poison=True,
          note=f"turning={turning:#x} bank={bank:#x}")


@pytest.mark.parametrize("bank", range(PLAYER_BANK_STEPS))
def test_frame_from_bank_indexes_the_byte_table(bank):
    _move_case(ENTRY_PLAYER_FRAME_FROM_BANK, "g_player_frame_from_bank",
               player_record(x=0x40, y=0x40, frame=0xa5),
               {A_player_bank: word(bank), A_player_bank_frames: _seeded_bank_table()},
               note=f"bank={bank}")


# ==================================================================================================
# player_reset_to_start @ 0x13d24
# ==================================================================================================
@pytest.mark.parametrize("bank", (0, 1, PLAYER_BANK_CENTRE, PLAYER_BANK_STEPS - 1))
def test_reset_to_start_writes_the_template_before_copying_it(bank):
    """The bank's frame is stamped into the TEMPLATE and only then copied out of it, so the template
    itself carries the last reset's bank. Both the template and the record are seeded away from what
    the routine writes."""
    pokes = {A_player_bank: word(bank), A_player_bank_frames: _seeded_bank_table(),
             A_player_start_template: player_record(x=0x111, y=0x222, frame=0x33, shadow=0x44,
                                                    mode=PLAYER_MODE_TAKEOFF),
             A_player: player_record(x=0xdead, y=0xbeef, frame=0x99, shadow=0x88, mode=0x77)}
    _case(ENTRY_PLAYER_RESET_TO_START, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_reset_to_start(buf), poison=True, note=f"bank={bank}")


def test_reset_to_start_over_the_shipped_template():
    """Nothing seeded: the game's own 0x1909c, which is x = 0x8f, y = 0x7e and mode 0xff."""
    _case(ENTRY_PLAYER_RESET_TO_START, {"_pokes": {}},
          lambda lib, buf: lib.g_player_reset_to_start(buf), note="shipped template")


# ==================================================================================================
# bomb_drop @ 0x13d5c
# ==================================================================================================
@pytest.mark.parametrize("bombs", (0, BOMBS_MIN_TO_DROP, 2, 0x8000, 0xffff))
@pytest.mark.parametrize("infinite", (0, 1))
def test_bomb_drop_spends_a_bomb_unless_the_cheat_is_on(bombs, infinite):
    """The count test is SIGNED (`cmpi.w #$1 / blt`), so 0xffff reads as -1 and refuses; the cheat
    arm skips the whole test AND the decrement, so it can drop with the counter at zero."""
    pokes = {SCRATCH_PLAYER: player_record(x=0x123, y=0x45),
             A_bombs: word(bombs), A_infinite_bombs_flag: bytes([infinite]),
             A_bomb_falling: word(0), A_bomb_exploding: word(0),
             A_player_bomb: bullet_record(x=0xa5a5, y=0x5a5a)}
    _case(ENTRY_BOMB_DROP, {"a0": SCRATCH_PLAYER, "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_drop(buf, SCRATCH_PLAYER), poison=True,
          note=f"bombs={bombs:#x} infinite={infinite}")


@pytest.mark.parametrize("falling,exploding", ((0, 0), (1, 0), (0, 1), (1, 1), (0xff00, 0)))
def test_bomb_drop_refuses_while_one_is_in_the_air(falling, exploding):
    pokes = {SCRATCH_PLAYER: player_record(x=0x60, y=0x70), A_bombs: word(4),
             A_infinite_bombs_flag: bytes([0]), A_bomb_falling: word(falling),
             A_bomb_exploding: word(exploding), A_player_bomb: bullet_record(x=1, y=2)}
    _case(ENTRY_BOMB_DROP, {"a0": SCRATCH_PLAYER, "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_drop(buf, SCRATCH_PLAYER),
          note=f"falling={falling:#x} exploding={exploding}")


@pytest.mark.parametrize("x", (0, 0xfff8, 0xffff, 0x7fff))
def test_bomb_drop_offsets_x_as_a_word(x):
    """`addi.w #$c,(a1)` wraps in sixteen bits — a bomb dropped at 0xfff8 starts at 4."""
    pokes = {SCRATCH_PLAYER: player_record(x=x, y=0x90), A_bombs: word(3),
             A_infinite_bombs_flag: bytes([0]), A_bomb_falling: word(0), A_bomb_exploding: word(0)}
    _case(ENTRY_BOMB_DROP, {"a0": SCRATCH_PLAYER, "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_drop(buf, SCRATCH_PLAYER), poison=True, note=f"x={x:#x}")


# ==================================================================================================
# The five fire patterns @ 0x13ee0 .. 0x1404c
# ==================================================================================================
_FIRE_PATTERNS = (
    (ENTRY_FIRE_PATTERN_LEVEL0, "g_fire_pattern_level0"),
    (ENTRY_FIRE_PATTERN_LEVEL1, "g_fire_pattern_level1"),
    (ENTRY_FIRE_PATTERN_LEVEL2, "g_fire_pattern_level2"),
    (ENTRY_FIRE_PATTERN_LEVEL3, "g_fire_pattern_level3"),
    (ENTRY_FIRE_PATTERN_LEVEL4, "g_fire_pattern_level4"),
)


def _scratch_slot_pokes(seed=0xa5):
    """A slot table in scratch whose five bullets are SEEDED, not zeroed.

    The seed is what makes the patterns' quirks visible: four of the five leave the fourth bullet's
    dx alone, so a case over zeroed records could not tell "wrote 0" from "wrote nothing".
    """
    pokes = {SCRATCH_SLOT_TABLE: b"".join(
        long_word(SCRATCH_BULLETS + index * PLAYER_BULLET_BYTES)
        for index in range(PLAYER_SHOT_BULLETS))}
    pokes[SCRATCH_BULLETS] = b"".join(
        bullet_record(x=seed * 0x100 + index, y=0x7000 + index, dx=0x1100 + index,
                      state=0x2200 + index)
        for index in range(PLAYER_SHOT_BULLETS))
    return pokes


def _pattern_case(entry, glue, player_x, player_y, note):
    pokes = _scratch_slot_pokes()
    pokes[A_player] = player_record(x=player_x, y=player_y)
    _case(entry, {"a6": SCRATCH_SLOT_TABLE, "a0": A_player, "_pokes": pokes},
          lambda lib, buf: getattr(lib, glue)(buf, SCRATCH_SLOT_TABLE), poison=True, note=note)


@pytest.mark.parametrize("entry,glue", _FIRE_PATTERNS)
@pytest.mark.parametrize("player_x,player_y", ((0, 0), (0x80, 0x60), (0xffff, 0xfff8),
                                               (0x7fff, 0x7ffa), (0xfff0, 0)))
def test_fire_pattern_places_its_bullets(entry, glue, player_x, player_y):
    """Every pattern at five player positions, three of which make the muzzle arithmetic WRAP: the
    x's are a running word sum in the original, so a version that recomputed each from the player
    would differ the first time one overflowed."""
    _pattern_case(entry, glue, player_x, player_y, f"{glue} at ({player_x:#x}, {player_y:#x})")


@pytest.mark.parametrize("entry,glue", _FIRE_PATTERNS[1:])
def test_fire_pattern_leaves_the_fourth_bullets_dx_alone(entry, glue):
    """REPRODUCES A QUIRK. Every pattern above level 0 clears the FOURTH bullet's state WORD before
    setting its high byte, where the other four bullets are only `st` — and patterns 1 and 3 never
    write that bullet's dx at all, so it flies with whatever the previous shot in the same slot
    left. Patterns 2 and 4 do write it. The seeded dx above is what makes either visible."""
    _pattern_case(entry, glue, 0x50, 0x40, f"{glue} fourth-bullet dx")


@pytest.mark.parametrize("chunk", range(4))
def test_fire_patterns_fuzz(chunk):
    """Random player positions over the whole word range, sharded so `-n auto` spreads them."""
    rng = random.Random(0xf12e + chunk)
    for _ in range(30):
        entry, glue = _FIRE_PATTERNS[rng.randrange(len(_FIRE_PATTERNS))]
        _pattern_case(entry, glue, rng.randrange(0x10000), rng.randrange(0x10000),
                      f"fuzz chunk={chunk}")


# ==================================================================================================
# player_fire_by_weapon_level @ 0x13ebc, player_shot_slot_alloc @ 0x13e4e, player_fire @ 0x13e12
# ==================================================================================================
@pytest.mark.parametrize("level", range(WEAPON_LEVEL_MAX + 1))
@pytest.mark.parametrize("cheat", (0, 1))
def test_fire_by_weapon_level_dispatches_through_the_shipped_table(level, cheat):
    """The cheat OVERWRITES `weapon_level` rather than only steering the dispatch, so a case that
    only checked which pattern ran would miss the store."""
    pokes = _scratch_slot_pokes()
    pokes[A_player] = player_record(x=0x70, y=0x50)
    pokes[A_weapon_level] = word(level)
    pokes[A_max_weapon_flag] = bytes([cheat])
    _case(ENTRY_PLAYER_FIRE_BY_WEAPON_LEVEL,
          {"a6": SCRATCH_SLOT_TABLE, "_pokes": pokes},
          lambda lib, buf: lib.g_player_fire_by_weapon_level(buf, SCRATCH_SLOT_TABLE),
          poison=True, note=f"level={level} cheat={cheat}")


@pytest.mark.parametrize("busy", range(8))
def test_shot_slot_alloc_takes_the_first_free_slot(busy):
    """All eight combinations of the three busy flags, including all three taken — which is the only
    arm that raises `shot_slots_full` instead of clearing it."""
    pokes = {A_player: player_record(x=0x60, y=0x48), A_weapon_level: word(2),
             A_max_weapon_flag: bytes([0]), A_shot_slots_full: word(0xa5a5)}
    for slot in range(PLAYER_SHOT_SLOTS):
        pokes[A_shot_slot_busy_0 + slot * SHOT_SLOT_BUSY_BYTES] = word((busy >> slot) & 1)
    _case(ENTRY_PLAYER_SHOT_SLOT_ALLOC, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_shot_slot_alloc(buf), poison=True, note=f"busy={busy:#03b}")


@pytest.mark.parametrize("held", (0, 1, 0xff00))
@pytest.mark.parametrize("busy", (0, 7))
@pytest.mark.parametrize("sfx_active", (0, 1, 0xff))
def test_player_fire_starts_one_shot_and_one_sound_per_press(held, busy, sfx_active):
    """The sound is the one effect in the game that YIELDS: unlike the six `sfx_play_*` wrappers,
    this call is gated on the module reporting no effect running, so `sfx_active` steers it."""
    pokes = {A_player: player_record(x=0x60, y=0x48), A_weapon_level: word(1),
             A_max_weapon_flag: bytes([0]), A_debug_overlay_flag: bytes([0]),
             A_fire_held: word(held), A_shot_slots_full: word(0),
             A_sound_module + SND_SFX_ACTIVE: bytes([sfx_active])}
    for slot in range(PLAYER_SHOT_SLOTS):
        pokes[A_shot_slot_busy_0 + slot * SHOT_SLOT_BUSY_BYTES] = word((busy >> slot) & 1)
    _case(ENTRY_PLAYER_FIRE, {"_pokes": pokes}, lambda lib, buf: lib.g_player_fire(buf),
          note=f"held={held:#x} busy={busy} sfx_active={sfx_active:#x}")


def test_player_fire_debug_overlay_arm():
    """UNREACHABLE IN THE SHIPPED GAME — `debug_overlay_flag` is written by no instruction in the
    image — and driven here anyway, because an arm no case executes is an arm no mutation can kill.

    The original's `bsr debug_show_counters` FALLS THROUGH into `console_show_message`, so the run
    stops at that fall-through; `fire_held` is set so that everything after the overlay call is a
    no-op on the candidate's side and the two end in the same place.
    """
    pokes = {A_debug_overlay_flag: bytes([1]), A_fire_held: word(1)}
    _case(ENTRY_PLAYER_FIRE, {"_pokes": pokes}, lambda lib, buf: lib.g_player_fire(buf),
          stop_pc=STOP_CONSOLE_SHOW_MESSAGE, note="debug overlay arm")


# ==================================================================================================
# player_script_step @ 0x13a20 — the take-off, fly-off and landing arms
# ==================================================================================================
def _script_state_pokes(mode, overrides=None):
    pokes = {
        A_player: player_record(x=0x8f, y=0x7e, frame=2, shadow=1, mode=mode),
        A_player_input_locked: word(0), A_player_turning: word(0),
        A_player_script_timer: word(0), A_player_script_fire_enable: word(0),
        A_shadow_offset: word(SHADOW_OFFSET_AIRBORNE),
        A_takeoff_shadow_timer: word(TAKEOFF_SHADOW_PERIOD),
        A_landing_shadow_timer: word(LANDING_SHADOW_PERIOD),
        A_landing_bomb_cash_timer: word(BOMB_CASH_PERIOD), A_level_complete: word(0),
        A_player_bank: word(PLAYER_BANK_CENTRE),
    }
    pokes.update(overrides or {})
    return pokes


@pytest.mark.parametrize("mode", (PLAYER_MODE_JOYSTICK, PLAYER_MODE_DYING, PLAYER_MODE_GAMEOVER,
                                  5, 0x7f))
def test_script_step_ignores_every_mode_but_its_three(mode):
    """`tst.b / bmi` then two `cmpi.b`s: modes 0, 3, 4 and anything else fall straight through."""
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": _script_state_pokes(mode)},
          lambda lib, buf: lib.g_player_script_step(buf), poison=True, note=f"mode={mode:#x}")


@pytest.mark.parametrize("cursor", (0, SCRIPT_STEP_BYTES, 2 * SCRIPT_STEP_BYTES))
@pytest.mark.parametrize("shadow_timer", (0, 1, 0x8000, 0xffff))
def test_script_step_takeoff_walks_its_script(cursor, shadow_timer):
    """Over the SHIPPED take-off script, freshly copied. The countdown is decremented IN the script,
    so a record that reaches -1 retires and the loop takes the next one in the same call; the third
    cursor lands on the 0xffff terminator, which ends the whole thing."""
    pokes = _script_state_pokes(PLAYER_MODE_TAKEOFF,
                                {A_takeoff_script_cursor: word(cursor),
                                 A_takeoff_shadow_timer: word(shadow_timer)})
    pokes[A_takeoff_script] = bytes(harness.BASE_IMAGE[A_takeoff_start_pos:
                                                       A_takeoff_start_pos
                                                       + 2 * SCRIPT_TEMPLATE_WORDS])
    # No poison pass: the cursor and the countdown this routine writes are the same words it reads
    # to decide where it is, so inverting them would send the second run off the end of the script.
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf),
          note=f"takeoff cursor={cursor} shadow_timer={shadow_timer:#x}")


def test_script_step_takeoff_retires_several_records_in_one_call():
    """A script whose first two countdowns are already 0: both retire and the third is the one that
    stamps a frame, so the cursor moves TWO records in a single frame."""
    script = word(0) + word(0x11) + word(0) + word(0x22) + word(3) + word(0x33) + word(0xffff) \
        + word(0x44) + word(0xffff)
    pokes = _script_state_pokes(PLAYER_MODE_TAKEOFF,
                                {A_takeoff_script_cursor: word(0)})
    pokes[A_takeoff_script] = script
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf), note="takeoff cascade")


@pytest.mark.parametrize("cursor", (0, SCRIPT_STEP_BYTES, 2 * SCRIPT_STEP_BYTES))
@pytest.mark.parametrize("shadow_timer", (LANDING_SHADOW_PERIOD, 0))
@pytest.mark.parametrize("cash_timer,bombs", ((BOMB_CASH_PERIOD, 3), (0, 3), (0, 0), (0, 1),
                                              (0, 0xffff), (0x8000, 5)))
def test_script_step_landing_walks_its_script_and_cashes_bombs(cursor, cash_timer, bombs,
                                                               shadow_timer):
    """The landing script's second job: every time the bomb timer expires it spends one bomb for
    3000 points and a sound. `bombs = 0xffff` is what pins the SIGNED test that guards it."""
    pokes = _script_state_pokes(PLAYER_MODE_LANDING,
                                {A_landing_script_cursor: word(cursor),
                                 A_landing_bomb_cash_timer: word(cash_timer), A_bombs: word(bombs),
                                 A_landing_shadow_timer: word(shadow_timer)})
    pokes[A_landing_script] = bytes(harness.BASE_IMAGE[A_landing_start_pos:
                                                       A_landing_start_pos
                                                       + 2 * SCRIPT_TEMPLATE_WORDS])
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf),
          note=f"landing cursor={cursor} cash={cash_timer:#x} bombs={bombs:#x} "
               f"shadow={shadow_timer}")


def test_script_step_landing_ends_the_level():
    """The terminator arm: the shadow snaps home and `level_complete` goes up, which is what
    `level_progress_check` reads as "advance"."""
    pokes = _script_state_pokes(PLAYER_MODE_LANDING,
                                {A_landing_script_cursor: word(2 * SCRIPT_STEP_BYTES)})
    pokes[A_landing_script] = word(1) + word(2) + word(3) + word(4) + word(0xffff)
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf), note="landing terminator")


@pytest.mark.parametrize("x", (FLYOFF_TARGET_X - 6, FLYOFF_TARGET_X, FLYOFF_TARGET_X + 6, 0, 0x120))
@pytest.mark.parametrize("y", (FLYOFF_TARGET_Y - 6, FLYOFF_TARGET_Y, FLYOFF_TARGET_Y + 6))
@pytest.mark.parametrize("timer", (0, FLYOFF_HOVER_FRAMES - 2, FLYOFF_HOVER_FRAMES - 1))
def test_script_step_flyoff_steers_to_the_landing_point(x, y, timer):
    """The x leg and the y leg drift independently through the ordinary move routines, so the plane
    arrives on a diagonal; only x ON the target arms the hand-over, and only then does the hover
    timer get read. The timer is the count BEFORE this call's own increment."""
    pokes = _script_state_pokes(PLAYER_MODE_FLYOFF,
                                {A_player_script_timer: word(timer)})
    pokes[A_player] = player_record(x=x, y=y, frame=2, shadow=1, mode=PLAYER_MODE_FLYOFF)
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf), poison=True,
          note=f"flyoff ({x:#x}, {y:#x}) timer={timer}")


def test_script_step_flyoff_needs_the_fire_enable_latch():
    """On the target in BOTH axes with the latch clear — which the x leg cannot leave behind, but a
    reconstruction that dropped the latch and tested x again would pass without this case."""
    pokes = _script_state_pokes(PLAYER_MODE_FLYOFF,
                                {A_player_script_timer: word(FLYOFF_HOVER_FRAMES),
                                 A_player_script_fire_enable: word(0)})
    pokes[A_player] = player_record(x=FLYOFF_TARGET_X, y=FLYOFF_TARGET_Y, frame=2, shadow=1,
                                    mode=PLAYER_MODE_FLYOFF)
    _case(ENTRY_PLAYER_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_script_step(buf), poison=True, note="flyoff latch clear")


# ==================================================================================================
# player_death_sequence_step @ 0x13bd6 and player_publish @ 0x13c96
# ==================================================================================================
TEXT_CURSOR_X, TEXT_CURSOR_Y = 0xdead_0000, 0xbeef_0000


def _death_pokes(cursor, lives=3, infinite=0, delay=2, overrides=None):
    pokes = {
        A_player: player_record(x=0x60, y=0x40, frame=9, shadow=1, mode=PLAYER_MODE_DYING),
        A_death_anim_cursor: word(cursor), A_lives: word(lives),
        A_infinite_lives_flag: bytes([infinite]), A_game_over_delay: word(delay),
        A_game_over_flag: word(0), A_player_input_locked: word(0),
        A_dl_player: bullet_record(x=0xa1a1, y=0xa2a2, dx=0xa3a3),
        A_dl_player_shadow: bullet_record(x=0xb1b1, y=0xb2b2, dx=0xb3b3),
    }
    pokes.update(overrides or {})
    return pokes


@pytest.mark.parametrize("cursor", [step * DEATH_FRAME_BYTES for step in range(DEATH_FRAMES_SHIPPED)])
def test_death_sequence_walks_every_frame_of_the_shipped_table(cursor):
    """Each frame of `player_death_frames`, over display records seeded away from what it writes:
    the plane's record is published as ON TOP and its shadow's is CLEARED, which is what stops the
    wreck casting one."""
    _case(ENTRY_PLAYER_DEATH_SEQUENCE_STEP,
          {"a0": A_player, "d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y, "_pokes": _death_pokes(cursor)},
          # No poison pass: the cursor it steps IS what it reads to find the frame.
          lambda lib, buf: lib.g_player_death_sequence_step(buf, A_player, TEXT_CURSOR_X,
                                                            TEXT_CURSOR_Y),
          note=f"cursor={cursor}")


@pytest.mark.parametrize("lives,infinite", ((3, 0), (2, 0), (1, 1), (0, 0), (0x8000, 0)))
def test_death_sequence_restarts_the_stage_while_a_life_is_left(lives, infinite):
    """The terminator arm's first half. Both "the cheat is on" and "a life remains" unwind the
    caller into `restart_level_at_checkpoint`, so the run stops at that routine's entry — and the
    decrement that happened on the way there is still compared. `lives = 0x8000` steps to 0x7fff,
    which is non-zero: the test is `bne`, not a sign test."""
    cursor = DEATH_FRAMES_SHIPPED * DEATH_FRAME_BYTES
    _case(ENTRY_PLAYER_DEATH_SEQUENCE_STEP,
          {"a0": A_player, "d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y,
           "_pokes": _death_pokes(cursor, lives=lives, infinite=infinite)},
          lambda lib, buf: lib.g_player_death_sequence_step(buf, A_player, TEXT_CURSOR_X,
                                                            TEXT_CURSOR_Y),
          stop_pc=STOP_RESTART_LEVEL, note=f"lives={lives:#x} infinite={infinite}")


@pytest.mark.parametrize("delay", (5, 1))
def test_death_sequence_last_life_shows_the_game_over_banner(delay):
    """The last life: mode 4, the counters reloaded out of `const_words_0123`, the banner compiled
    and the dwell counted down. The text cursor is the CALLER's D1/D2 with junk high bytes, which
    `build_text_display_list` keeps — so the banner's display records carry them."""
    cursor = DEATH_FRAMES_SHIPPED * DEATH_FRAME_BYTES
    _case(ENTRY_PLAYER_DEATH_SEQUENCE_STEP,
          {"a0": A_player, "d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y,
           "_pokes": _death_pokes(cursor, lives=1, delay=delay)},
          lambda lib, buf: lib.g_player_death_sequence_step(buf, A_player, TEXT_CURSOR_X,
                                                            TEXT_CURSOR_Y),
          note=f"delay={delay}")


def test_death_sequence_expired_banner_reaches_the_hall_of_fame(new_game_pokes):
    """...and when the dwell reaches -1 the routine unwinds into `game_over_hiscore_check`, which is
    the hud slice's and IS reconstructed — so the case is diffed through the whole rank walk, to
    that routine's own re-entry into `main`. Run on a started game so the score it places is one the
    game itself reset."""
    cursor = DEATH_FRAMES_SHIPPED * DEATH_FRAME_BYTES
    pokes = dict(new_game_pokes)
    pokes.update(_death_pokes(cursor, lives=1, delay=0))
    _case(ENTRY_PLAYER_DEATH_SEQUENCE_STEP,
          {"a0": A_player, "d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y, "_pokes": pokes},
          lambda lib, buf: lib.g_player_death_sequence_step(buf, A_player, TEXT_CURSOR_X,
                                                            TEXT_CURSOR_Y),
          stop_pc=STOP_MAIN_REENTRY, note="banner expired")


@pytest.mark.parametrize("mode", (PLAYER_MODE_JOYSTICK, PLAYER_MODE_LANDING, PLAYER_MODE_FLYOFF,
                                  PLAYER_MODE_TAKEOFF, 5))
@pytest.mark.parametrize("shadow_offset", (0, SHADOW_OFFSET_AIRBORNE, 0xffff))
def test_publish_stamps_the_plane_and_its_shadow(mode, shadow_offset):
    """The shadow is the plane offset in BOTH axes with its sprite id seven higher, added as a BYTE
    — so a frame of 0xfd wraps to 4 rather than climbing out of the bank. The frame comes from the
    bank only in the modes that are not running a script of their own."""
    pokes = _death_pokes(0)
    pokes[A_player] = player_record(x=0x111, y=0x222, frame=0xfd, shadow=0x5a, mode=mode)
    pokes[A_shadow_offset] = word(shadow_offset)
    pokes[A_player_bank] = word(PLAYER_BANK_CENTRE)
    pokes[A_player_bank_frames] = _seeded_bank_table()
    _case(ENTRY_PLAYER_PUBLISH,
          {"d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y, "_pokes": pokes},
          lambda lib, buf: lib.g_player_publish(buf, TEXT_CURSOR_X, TEXT_CURSOR_Y),
          poison=True, note=f"mode={mode:#x} shadow_offset={shadow_offset:#x}")


def test_publish_hands_a_dying_plane_to_the_death_sequence():
    pokes = _death_pokes(2 * DEATH_FRAME_BYTES)
    _case(ENTRY_PLAYER_PUBLISH,
          {"d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y, "_pokes": pokes},
          lambda lib, buf: lib.g_player_publish(buf, TEXT_CURSOR_X, TEXT_CURSOR_Y),
          note="mode 3")


def test_publish_in_game_over_mode_shows_the_banner():
    pokes = _death_pokes(0, delay=4)
    pokes[A_player] = player_record(x=0x60, y=0x40, frame=9, shadow=1, mode=PLAYER_MODE_GAMEOVER)
    _case(ENTRY_PLAYER_PUBLISH,
          {"d1": TEXT_CURSOR_X, "d2": TEXT_CURSOR_Y, "_pokes": pokes},
          lambda lib, buf: lib.g_player_publish(buf, TEXT_CURSOR_X, TEXT_CURSOR_Y),
          note="mode 4")


# ==================================================================================================
# read_player_input @ 0x14354
# ==================================================================================================
def _input_pokes(stick=0, keys=0, joy0=0, locked=0, just_started=0, overrides=None):
    pokes = {
        A_player: player_record(x=0x60, y=0x60, frame=2, shadow=1, mode=PLAYER_MODE_JOYSTICK),
        A_joy1_state: bytes([stick]), A_key_bits: bytes([keys]), A_joy0_state: bytes([joy0]),
        A_player_input_locked: word(locked), A_level_just_started: word(just_started),
        A_use_keyboard_flag: word(0), A_player_turning: word(0xa5a5),
        A_player_bank: word(PLAYER_BANK_CENTRE), A_fire_held: word(0),
        A_shot_slots_full: word(0), A_weapon_level: word(0), A_max_weapon_flag: bytes([0]),
        A_debug_overlay_flag: bytes([0]), A_bombs: word(2), A_infinite_bombs_flag: bytes([0]),
        A_bomb_falling: word(0), A_bomb_exploding: word(0),
        A_sound_module + SND_SFX_ACTIVE: bytes([0]),
    }
    for slot in range(PLAYER_SHOT_SLOTS):
        pokes[A_shot_slot_busy_0 + slot * SHOT_SLOT_BUSY_BYTES] = word(0)
    pokes.update(overrides or {})
    return pokes


@pytest.mark.parametrize("stick", range(16))
@pytest.mark.parametrize("fire", (0, 1 << JOY_FIRE_BIT))
def test_read_input_drives_all_sixteen_stick_states(stick, fire):
    """Every direction combination with and without the button, which is where the four move
    routines, the turning latch and the one-shot-per-press flag all meet."""
    _case(ENTRY_READ_PLAYER_INPUT, {"_pokes": _input_pokes(stick=stick | fire)},
          lambda lib, buf: lib.g_read_player_input(buf), note=f"stick={stick:#06b} fire={fire:#x}")


@pytest.mark.parametrize("weapon_level", range(WEAPON_LEVEL_MAX + 1))
def test_read_input_fires_at_every_weapon_level(weapon_level):
    """The button all the way through to the bullets, so the weapon progression is exercised from
    the stick rather than only from the pattern's own entry."""
    _case(ENTRY_READ_PLAYER_INPUT,
          {"_pokes": _input_pokes(stick=1 << JOY_FIRE_BIT,
                                  overrides={A_weapon_level: word(weapon_level)})},
          lambda lib, buf: lib.g_read_player_input(buf), note=f"weapon_level={weapon_level}")


@pytest.mark.parametrize("locked", (1, 0xff00))
def test_read_input_does_nothing_while_a_script_owns_the_plane(locked):
    _case(ENTRY_READ_PLAYER_INPUT,
          {"_pokes": _input_pokes(stick=0xff, keys=0xff, joy0=0xff, locked=locked)},
          lambda lib, buf: lib.g_read_player_input(buf), poison=True, note=f"locked={locked:#x}")


@pytest.mark.parametrize("keys,joy0", ((1 << KEY_BOMB_BIT, 0), (0, 1 << JOY_FIRE_BIT),
                                       (1 << KEY_BOMB_BIT, 1 << JOY_FIRE_BIT), (0, 0)))
def test_read_input_drops_a_bomb_from_either_button(keys, joy0):
    """Space on the keyboard OR joystick 0's fire, and the arm is shared — so the bomb goes at most
    once even with both down."""
    _case(ENTRY_READ_PLAYER_INPUT, {"_pokes": _input_pokes(stick=0, keys=keys, joy0=joy0)},
          lambda lib, buf: lib.g_read_player_input(buf), note=f"keys={keys:#x} joy0={joy0:#x}")


@pytest.mark.parametrize("use_keyboard", (0, 1))
@pytest.mark.parametrize("keys", (0, 1 << 0, 1 << KEY_BOMB_BIT))
def test_read_input_keyboard_flag_only_moves_the_idle_test(use_keyboard, keys):
    """`use_keyboard_flag` chooses `key_bits` over `joy1_state` for ONE test — the "nothing held at
    all" short-circuit — because the direction tests below re-read `joy1_state` regardless. The
    flag is written nowhere in the image; both settings are driven anyway."""
    _case(ENTRY_READ_PLAYER_INPUT,
          {"_pokes": _input_pokes(stick=0, keys=keys,
                                  overrides={A_use_keyboard_flag: word(use_keyboard)})},
          lambda lib, buf: lib.g_read_player_input(buf),
          note=f"use_keyboard={use_keyboard} keys={keys:#x}")


@pytest.mark.parametrize("released_at", (1, 2, 5, 40))
def test_read_input_pause_spins_until_the_stick_moves(released_at):
    """The pause key holds the frame loop still by spinning on `joy1_state`, a byte only the ACIA
    interrupt writes. The schedule is what makes the wait runnable and what compares the ITERATION
    COUNT: the memory is identical however many times either side went round."""
    pokes = _input_pokes(stick=0, keys=1 << KEY_PAUSE_BIT)
    _case(ENTRY_READ_PLAYER_INPUT, {"_pokes": pokes},
          lambda lib, buf: lib.g_read_player_input(buf),
          schedule=[{"pc": PAUSE_WAIT_PC, "nth": released_at, "addr": A_joy1_state,
                     "width": 1, "value": 1 << JOY_UP_BIT}],
          note=f"released at poll {released_at}")


def test_read_input_pause_is_skipped_while_the_level_is_just_starting():
    """`level_just_started` gates BOTH system keys off, which is what stops a held key surviving a
    stage restart into the first frame of the new one."""
    _case(ENTRY_READ_PLAYER_INPUT,
          {"_pokes": _input_pokes(stick=0, keys=(1 << KEY_PAUSE_BIT) | (1 << KEY_ABORT_BIT),
                                  just_started=1)},
          lambda lib, buf: lib.g_read_player_input(buf), note="just started")


def test_read_input_abort_key_reaches_the_hall_of_fame(new_game_pokes):
    """F10 does not return: it throws away this routine's register save AND its caller's return
    address, then branches into `game_over_hiscore_check`. That routine is the hud slice's and is
    reconstructed, so the case is diffed through it to its own re-entry into `main`."""
    pokes = dict(new_game_pokes)
    pokes.update(_input_pokes(stick=0, keys=1 << KEY_ABORT_BIT))
    _case(ENTRY_READ_PLAYER_INPUT, {"_pokes": pokes},
          lambda lib, buf: lib.g_read_player_input(buf), stop_pc=STOP_MAIN_REENTRY, note="abort")


@pytest.mark.parametrize("chunk", range(4))
def test_read_input_fuzz(chunk):
    """Random stick, key and joystick-0 bytes over a plane at random positions and banks, sharded so
    `-n auto` spreads them. The two system keys are masked out: one spins and one never returns."""
    rng = random.Random(0x14354 + chunk)
    system_keys = (1 << KEY_PAUSE_BIT) | (1 << KEY_ABORT_BIT)
    for _ in range(25):
        pokes = _input_pokes(stick=rng.randrange(256), keys=rng.randrange(256) & ~system_keys,
                             joy0=rng.randrange(256))
        pokes[A_player] = player_record(x=rng.randrange(0x10000), y=rng.randrange(0x10000),
                                        frame=rng.randrange(256), shadow=1,
                                        mode=PLAYER_MODE_JOYSTICK)
        pokes[A_player_bank] = word(rng.randrange(1, PLAYER_BANK_STEPS - 1))
        pokes[A_weapon_level] = word(rng.randrange(WEAPON_LEVEL_MAX + 1))
        pokes[A_bombs] = word(rng.randrange(4))
        _case(ENTRY_READ_PLAYER_INPUT, {"_pokes": pokes},
              lambda lib, buf: lib.g_read_player_input(buf), note=f"fuzz chunk={chunk}")


# ==================================================================================================
# player_vs_entities @ 0x10f26 and its two group variants
# ==================================================================================================
def _poked_group(records):
    """A pointer array in scratch naming `len(records)` entity records, also in scratch."""
    pokes = {SCRATCH_GROUP: b"".join(long_word(SCRATCH_ENTITIES + index * ENTITY_STRIDE)
                                     for index in range(len(records)))}
    pokes[SCRATCH_ENTITIES] = b"".join(records)
    return pokes


def _group_variant_case(entry, glue, records, note, stop_pc=0, player_x=None, player_y=None):
    """Through the variant's OWN entry, which is where the box constants are loaded — the shared
    loop takes them in registers, so a case that entered there would drive the test's copy of a
    constant rather than the reconstruction's."""
    pokes = _poked_group(records)
    pokes[A_player] = player_record(x=_PROBE_PLAYER_X if player_x is None else player_x,
                                    y=_PROBE_PLAYER_Y if player_y is None else player_y,
                                    frame=2, shadow=1, mode=PLAYER_MODE_JOYSTICK)
    pokes[A_sound_module + SND_SFX_ACTIVE] = bytes([0])
    _case(entry, {"a3": SCRATCH_GROUP, "_pokes": pokes},
          lambda lib, buf: getattr(lib, glue)(buf, SCRATCH_GROUP), stop_pc=stop_pc, note=note)


def _group_test_case(records, player_x, player_y, box, note, stop_pc=0, poison=False):
    slots, box_dx, box_dy, box_h, box_w = box
    pokes = _poked_group(records)
    pokes[A_player] = player_record(x=player_x, y=player_y, frame=2, shadow=1,
                                    mode=PLAYER_MODE_JOYSTICK)
    pokes[A_sound_module + SND_SFX_ACTIVE] = bytes([0])
    _case(ENTRY_PLAYER_VS_ENTITY_GROUP_TEST,
          {"a3": SCRATCH_GROUP, "d7": slots - 1, "d3": box_dx, "d4": box_dy, "d6": box_h,
           "d1": box_w, "_pokes": pokes},
          lambda lib, buf: lib.g_player_vs_entity_group_test(buf, SCRATCH_GROUP, slots - 1, box_dx,
                                                             box_dy, box_h, box_w),
          stop_pc=stop_pc, poison=poison, note=note)


STANDARD_BOX = (ENTITY_A_GROUP_SLOTS, ENTITY_BOX_DX, ENTITY_BOX_DY, ENTITY_BOX_H, ENTITY_BOX_W)
A4_BOX = (ENTITY_A4_GROUP_SLOTS, ENTITY_BOX_A4_DX, ENTITY_BOX_A4_DY, ENTITY_BOX_A4_H,
          ENTITY_BOX_A4_W)

# One step either side of every edge of the standard box, in each axis, around a player at (0x80,
# 0x60). The x span the entity must meet runs from player_x - box_dx - box_w to player_x - box_dx +
# PLAYER_HIT_BOX_W; the y span likewise. The probes below bracket both ends of both.
_PROBE_PLAYER_X, _PROBE_PLAYER_Y = 0x80, 0x60


def _edge_probes(player, box_offset, box_size, player_size):
    near = player - box_offset - box_size
    far = player - box_offset + player_size
    return [near - 1, near, near + 1, far - 1, far, far + 1, player]


@pytest.mark.parametrize("entity_x", _edge_probes(_PROBE_PLAYER_X, ENTITY_BOX_DX, ENTITY_BOX_W,
                                                  PLAYER_HIT_BOX_W))
@pytest.mark.parametrize("entity_y", _edge_probes(_PROBE_PLAYER_Y, ENTITY_BOX_DY, ENTITY_BOX_H,
                                                  PLAYER_HIT_BOX_H))
def test_group_test_box_edges(entity_x, entity_y):
    """One live entity, stepped one pixel either side of every edge of the box in both axes — the
    only way to pin `bgt` against `bge` on four separate compares. The hit arm ends in the score
    subsystem, so it is diffed at that branch."""
    records = [entity_record(x=entity_x, y=entity_y, active=1)]
    records += [entity_record() for _ in range(ENTITY_A_GROUP_SLOTS - 1)]
    _group_test_case(records, _PROBE_PLAYER_X, _PROBE_PLAYER_Y, STANDARD_BOX,
                     f"entity=({entity_x:#x}, {entity_y:#x})", stop_pc=STOP_SCORE_ADD_200)


# ABSOLUTE probes, spelt as literals and derived from NOTHING. The parametrised edge cases above
# compute their positions FROM the box constants, so widening a constant moves the probe with it and
# the case agrees with the mutant — `ENTITY_BOX_W 0x1b -> 0x1c` SURVIVED the whole battery until
# these three cases were added (measured 2026-09-07). Every number below was worked out by hand
# against the disassembly at a player parked on (0x80, 0x60), and must stay hand-written.
_ABS_PLAYER_X, _ABS_PLAYER_Y = 0x80, 0x60


@pytest.mark.parametrize("entity_x,entity_y", ((0x54, 0x60), (0x55, 0x60),   # the near x edge
                                               (0x8a, 0x60), (0x8b, 0x60),   # ...and the far one
                                               (0x80, 0x3d), (0x80, 0x3e),   # the near y edge
                                               (0x80, 0x78), (0x80, 0x79)))  # ...and the far one
def test_group_test_box_edges_at_absolute_coordinates(entity_x, entity_y):
    """The standard box's four edges as HAND-WORKED literals: with the player on (0x80, 0x60) the
    box catches an entity from x = 0x55 to x = 0x8a and from y = 0x3e to y = 0x78, and one pixel
    outside each of those is a miss. Widening any of the four constants moves an edge and reddens
    this, which the derived probes above cannot do."""
    records = [entity_record(x=entity_x, y=entity_y, active=1)]
    records += [entity_record() for _ in range(ENTITY_A_GROUP_SLOTS - 1)]
    _group_variant_case(ENTRY_PLAYER_VS_ENTITIES_GROUP, "g_player_vs_entities_group", records,
                        f"absolute ({entity_x:#x}, {entity_y:#x})", stop_pc=STOP_SCORE_ADD_200,
                        player_x=_ABS_PLAYER_X, player_y=_ABS_PLAYER_Y)


@pytest.mark.parametrize("entity_x,entity_y", ((0x43, 0x60), (0x44, 0x60),
                                               (0x97, 0x60), (0x98, 0x60),
                                               (0x80, 0x42), (0x80, 0x43)))
def test_a4_box_edges_at_absolute_coordinates(entity_x, entity_y):
    """...and the a4 group's, whose four constants are all different: from x = 0x44 to x = 0x97 and
    from y = 0x43 down, against the same player."""
    records = [entity_record(x=entity_x, y=entity_y, active=1)]
    records += [entity_record() for _ in range(ENTITY_A4_GROUP_SLOTS - 1)]
    _group_variant_case(ENTRY_PLAYER_VS_ENTITIES_GROUP_A4, "g_player_vs_entities_group_a4", records,
                        f"a4 absolute ({entity_x:#x}, {entity_y:#x})", stop_pc=STOP_SCORE_ADD_200,
                        player_x=_ABS_PLAYER_X, player_y=_ABS_PLAYER_Y)


@pytest.mark.parametrize("active,dying", ((0, 0), (1, 1), (0, 1), (1, 0), (0xff00, 0)))
def test_group_test_skips_inactive_and_dying_slots(active, dying):
    """`tst.w 14(a0) / beq` and `tst.w 16(a0) / bne`, both WORD tests, over an entity squarely on
    the player."""
    records = [entity_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, active=active, dying=dying)]
    records += [entity_record() for _ in range(ENTITY_A_GROUP_SLOTS - 1)]
    _group_test_case(records, _PROBE_PLAYER_X, _PROBE_PLAYER_Y, STANDARD_BOX,
                     f"active={active:#x} dying={dying}", stop_pc=STOP_SCORE_ADD_200)


def test_group_test_narrows_the_box_after_the_first_x_overlap():
    """REPRODUCES A BUG, and this is the case that pins it.

    The box WIDTH lives in D1 and the y test overwrites D1 with the box HEIGHT out of D6 before it
    uses it, so the first slot whose x span meets the player's narrows the box for every slot after
    it in the same group: 0x1b becomes 0x17. Slot 0 here overlaps in x and misses in y; slot 1 then
    sits in the four-pixel band that the WIDE box would catch and the narrowed one does not. A
    version that kept the width kills the player and is red.
    """
    x_only = _PROBE_PLAYER_X - ENTITY_BOX_DX - ENTITY_BOX_W + 1   # the wide box's near edge
    records = [entity_record(x=x_only, y=0, active=1),
               entity_record(x=x_only, y=_PROBE_PLAYER_Y, active=1)]
    records += [entity_record() for _ in range(ENTITY_A_GROUP_SLOTS - 2)]
    _group_test_case(records, _PROBE_PLAYER_X, _PROBE_PLAYER_Y, STANDARD_BOX,
                     "the D1 clobber", stop_pc=STOP_SCORE_ADD_200)


def test_group_test_stops_once_the_player_is_dying():
    """The mode is re-read at the top of EVERY iteration — `lea $190a4,a1` is the `dbf`'s own target
    — so a second entity in the same group cannot kill an already-dying plane twice."""
    records = [entity_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, active=1)
               for _ in range(ENTITY_A_GROUP_SLOTS)]
    pokes = _poked_group(records)
    pokes[A_player] = player_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, frame=2, shadow=1,
                                    mode=PLAYER_MODE_DYING)
    slots, box_dx, box_dy, box_h, box_w = STANDARD_BOX
    _case(ENTRY_PLAYER_VS_ENTITY_GROUP_TEST,
          {"a3": SCRATCH_GROUP, "d7": slots - 1, "d3": box_dx, "d4": box_dy, "d6": box_h,
           "d1": box_w, "_pokes": pokes},
          lambda lib, buf: lib.g_player_vs_entity_group_test(buf, SCRATCH_GROUP, slots - 1, box_dx,
                                                             box_dy, box_h, box_w),
          poison=True, note="already dying")


@pytest.mark.parametrize("entity_x", _edge_probes(_PROBE_PLAYER_X, ENTITY_BOX_A4_DX,
                                                  ENTITY_BOX_A4_W, PLAYER_HIT_BOX_W))
def test_a4_group_uses_a_box_twice_as_wide(entity_x):
    """The a4 variant's own five constants, which differ from the standard group's in every one."""
    records = [entity_record(x=entity_x, y=_PROBE_PLAYER_Y, active=1)]
    records += [entity_record() for _ in range(ENTITY_A4_GROUP_SLOTS - 1)]
    _group_test_case(records, _PROBE_PLAYER_X, _PROBE_PLAYER_Y, A4_BOX,
                     f"a4 entity_x={entity_x:#x}", stop_pc=STOP_SCORE_ADD_200)


@pytest.mark.parametrize("hit_slot", list(range(ENTITY_A_GROUP_SLOTS)) + [None])
def test_group_variant_loads_seven_slots_and_the_standard_box(hit_slot):
    """`player_vs_entities_group` is five `move.w`s and a `bra` into the shared loop; the only thing
    that can be wrong about it is which slot count and which box it loads, so the case puts the one
    live entity in each slot in turn — including none, which must walk all seven."""
    records = []
    for slot in range(ENTITY_A_GROUP_SLOTS):
        on_player = slot == hit_slot
        records.append(entity_record(x=_PROBE_PLAYER_X if on_player else 0x300,
                                     y=_PROBE_PLAYER_Y if on_player else 0x300, active=1))
    _group_variant_case(ENTRY_PLAYER_VS_ENTITIES_GROUP, "g_player_vs_entities_group", records,
                        f"hit_slot={hit_slot}", stop_pc=STOP_SCORE_ADD_200)


@pytest.mark.parametrize("hit_slot", list(range(ENTITY_A4_GROUP_SLOTS)) + [None])
def test_a4_variant_loads_four_slots(hit_slot):
    records = []
    for slot in range(ENTITY_A4_GROUP_SLOTS):
        on_player = slot == hit_slot
        records.append(entity_record(x=_PROBE_PLAYER_X if on_player else 0x300,
                                     y=_PROBE_PLAYER_Y if on_player else 0x300, active=1))
    _group_variant_case(ENTRY_PLAYER_VS_ENTITIES_GROUP_A4, "g_player_vs_entities_group_a4", records,
                        f"a4 hit_slot={hit_slot}", stop_pc=STOP_SCORE_ADD_200)


def _real_group_pokes(group, records):
    """Poke `records` into the arena slots the GAME'S OWN table names, read out of the image."""
    pokes = {}
    for index, record in enumerate(records):
        slot = int.from_bytes(harness.BASE_IMAGE[group + index * ENTITY_GROUP_PTR_BYTES:
                                                 group + (index + 1) * ENTITY_GROUP_PTR_BYTES],
                              "big")
        pokes[slot] = record
    return pokes


_PLAYER_VS_ENTITY_GROUPS = (
    (A_entity_group_a0, ENTITY_A_GROUP_SLOTS), (A_entity_group_a1, ENTITY_A_GROUP_SLOTS),
    (A_entity_group_a2, ENTITY_A_GROUP_SLOTS), (A_entity_group_a3, ENTITY_A_GROUP_SLOTS),
    (A_entity_group_a4, ENTITY_A4_GROUP_SLOTS),
)


@pytest.mark.parametrize("hit_group", list(range(len(_PLAYER_VS_ENTITY_GROUPS))) + [None])
def test_player_vs_entities_walks_five_groups_in_order(hit_group):
    """Over the GAME'S own slot tables, with the one live entity in each group in turn: the a4 group
    is reached by a `bra` after the four `bsr`s, so a pass that stopped at four is red on the last
    case and a pass that used the a4 box for all five is red on the first four."""
    pokes = {A_player: player_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, frame=2, shadow=1,
                                     mode=PLAYER_MODE_JOYSTICK),
             A_invuln_flag: bytes([0]), A_sound_module + SND_SFX_ACTIVE: bytes([0])}
    for index, (group, slots) in enumerate(_PLAYER_VS_ENTITY_GROUPS):
        records = [entity_record(x=_PROBE_PLAYER_X if index == hit_group and slot == 0 else 0x300,
                                 y=_PROBE_PLAYER_Y if index == hit_group and slot == 0 else 0x300,
                                 active=1)
                   for slot in range(slots)]
        pokes.update(_real_group_pokes(group, records))
    _case(ENTRY_PLAYER_VS_ENTITIES, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_vs_entities(buf),
          stop_pc=STOP_SCORE_ADD_200, note=f"hit_group={hit_group}")


@pytest.mark.parametrize("invuln,mode", ((1, PLAYER_MODE_JOYSTICK), (0xff, PLAYER_MODE_JOYSTICK),
                                         (0, PLAYER_MODE_GAMEOVER)))
def test_player_vs_entities_two_early_exits(invuln, mode):
    """The "HSC" cheat and game-over mode both skip the whole pass, over a world that would
    otherwise kill the plane on slot 0 of the first group."""
    pokes = {A_player: player_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, frame=2, shadow=1,
                                     mode=mode),
             A_invuln_flag: bytes([invuln])}
    pokes.update(_real_group_pokes(A_entity_group_a0,
                                   [entity_record(x=_PROBE_PLAYER_X, y=_PROBE_PLAYER_Y, active=1)]))
    _case(ENTRY_PLAYER_VS_ENTITIES, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_vs_entities(buf), poison=True,
          note=f"invuln={invuln:#x} mode={mode}")


@pytest.mark.parametrize("chunk", range(4))
def test_group_test_fuzz(chunk):
    """Unrestricted words in both the entity positions and the player's, sharded. The box arithmetic
    is `add.w` throughout, so a position near 0x8000 turns "in front of" into "behind"."""
    rng = random.Random(0x10fa0 + chunk)
    for _ in range(20):
        records = [entity_record(x=rng.randrange(0x10000), y=rng.randrange(0x10000),
                                 active=rng.randrange(2), dying=rng.randrange(2))
                   for _ in range(ENTITY_A_GROUP_SLOTS)]
        _group_test_case(records, rng.randrange(0x10000), rng.randrange(0x10000), STANDARD_BOX,
                         f"fuzz chunk={chunk}", stop_pc=STOP_SCORE_ADD_200)


# ==================================================================================================
# player_vs_enemy_bullets @ 0x1101c
# ==================================================================================================
def _sprite_box(post_load_image, frame):
    """The four box words of `frame`'s sprite record.

    Out of `post_load_image` and NOT out of `harness.BASE_IMAGE`: the sprite bank is a FILE, read
    over the bss by the boot chain, so the bare .PRG holds zeros there. A case that took its probe
    positions from those zeros would drive a degenerate box that nothing can be inside — which is
    what let `ENEMY_BULLET_HIT_OFFSET 0x10 -> 0xf` and `ENEMY_BULLET_SLOTS 16 -> 15` survive the
    whole battery (measured 2026-09-07).
    """
    record = A_sprite_bank + frame * SPRITE_RECORD_BYTES
    def at(offset):
        return int.from_bytes(post_load_image[record + offset:record + offset + 2], "big")
    return at(SPRITE_REC_DRAW_DX), at(SPRITE_REC_DRAW_DY), at(SPRITE_REC_HIT_W), at(SPRITE_REC_HIT_H)


def _bullet_case(bullets, player_x, player_y, frame, note, mode=PLAYER_MODE_JOYSTICK,
                 invuln=0, poison=False):
    pokes = {A_player: player_record(x=player_x, y=player_y, frame=frame, shadow=1, mode=mode),
             A_invuln_flag: bytes([invuln]), A_music_suspend_flag: word(0),
             A_player_hit: word(0), A_sound_module + SND_SFX_ACTIVE: bytes([0]),
             A_enemy_bullets: b"".join(bullets)}
    _case(ENTRY_PLAYER_VS_ENEMY_BULLETS, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_vs_enemy_bullets(buf), poison=poison, note=note)


_BULLET_PLAYER_FRAME = 2


@pytest.mark.parametrize("axis", ("x", "y"))
@pytest.mark.parametrize("step", (-1, 0, 1))
@pytest.mark.parametrize("edge", ("near", "far"))
def test_enemy_bullet_box_edges(post_load_image, axis, step, edge):
    """One live bullet stepped one pixel either side of each of the four edges the test compares —
    two `blt` and two `bgt`, which is four separate chances to be off by one."""
    draw_dx, draw_dy, hit_w, hit_h = _sprite_box(post_load_image, _BULLET_PLAYER_FRAME)
    player_x, player_y = 0x80, 0x60
    assert (hit_w, hit_h) != (0, 0), "the sprite bank is not loaded — every probe would be degenerate"
    if axis == "x":
        base = player_x + (draw_dx if edge == "near" else hit_w)
        x, y = base - ENEMY_BULLET_HIT_OFFSET + step, player_y + draw_dy - ENEMY_BULLET_HIT_OFFSET
    else:
        base = player_y + (draw_dy if edge == "near" else hit_h)
        x, y = player_x + draw_dx - ENEMY_BULLET_HIT_OFFSET, base - ENEMY_BULLET_HIT_OFFSET + step
    bullets = [enemy_bullet_record(x=x, y=y, active=1)]
    bullets += [enemy_bullet_record() for _ in range(ENEMY_BULLET_SLOTS - 1)]
    _bullet_case(bullets, player_x, player_y, _BULLET_PLAYER_FRAME,
                 f"{axis} {edge} step={step}")


@pytest.mark.parametrize("frame", (0, 1, 2, 3, 0x7f, 0x80, 0xff))
def test_enemy_bullet_box_comes_from_the_players_sprite_record(frame):
    """The frame byte is an UNSIGNED index into the 256-record bank, so 0x80 reads record 128 and
    not record -128; every one of these has a different box."""
    player_x, player_y = 0x80, 0x60
    bullets = [enemy_bullet_record(x=player_x, y=player_y, active=1)]
    bullets += [enemy_bullet_record() for _ in range(ENEMY_BULLET_SLOTS - 1)]
    _bullet_case(bullets, player_x, player_y, frame, f"frame={frame:#x}")


@pytest.mark.parametrize("hit_slot", list(range(0, ENEMY_BULLET_SLOTS, 3)) + [ENEMY_BULLET_SLOTS - 1,
                                                                             None])
def test_enemy_bullet_walk_covers_sixteen_slots(hit_slot):
    """`move.w #$f,d7` is a dbf count, so the walk is sixteen records — including the LAST, which a
    fifteen-slot version never reaches."""
    player_x, player_y = 0x80, 0x60
    bullets = []
    for slot in range(ENEMY_BULLET_SLOTS):
        on_player = slot == hit_slot
        bullets.append(enemy_bullet_record(x=player_x if on_player else 0x300,
                                           y=player_y if on_player else 0x300, active=1))
    _bullet_case(bullets, player_x, player_y, _BULLET_PLAYER_FRAME, f"hit_slot={hit_slot}")


@pytest.mark.parametrize("mode,invuln", ((PLAYER_MODE_DYING, 0), (PLAYER_MODE_JOYSTICK, 1),
                                         (PLAYER_MODE_JOYSTICK, 0xff)))
def test_enemy_bullet_hit_is_refused_when_already_dying_or_invulnerable(mode, invuln):
    """The cheat returns before the walk; an already-dying plane runs the whole walk and then
    refuses at the hit itself, WITHOUT clearing the bullet — so the two arms differ in memory."""
    player_x, player_y = 0x80, 0x60
    bullets = [enemy_bullet_record(x=player_x, y=player_y, active=1)]
    bullets += [enemy_bullet_record() for _ in range(ENEMY_BULLET_SLOTS - 1)]
    _bullet_case(bullets, player_x, player_y, _BULLET_PLAYER_FRAME,
                 f"mode={mode} invuln={invuln:#x}", mode=mode, invuln=invuln)


# The bullet's own point offset, spelt again and DELIBERATELY not mirrored from include/player.h:
# the parametrised edge cases above subtract ENEMY_BULLET_HIT_OFFSET from a box they also derive
# from it, so shrinking the constant moves both and `0x10 -> 0xf` SURVIVED the battery until this
# was written by hand (measured 2026-09-07). It is a second, independent statement of the number,
# and pinning the two equal would put the hole straight back.
_BULLET_POINT_OFFSET_BY_HAND = 0x10
_ENEMY_BULLET_LAST_SLOT_BY_HAND = 15   # ...and the sixteenth record, for the same reason


@pytest.mark.parametrize("step", (-1, 0, 1))
def test_enemy_bullet_near_edge_at_an_absolute_offset(post_load_image, step):
    """The near corner of the box with the point offset written out by hand rather than taken from
    the header, so a shrunk offset moves the bullet and not the edge."""
    draw_dx, draw_dy, _hit_w, _hit_h = _sprite_box(post_load_image, _BULLET_PLAYER_FRAME)
    player_x, player_y = 0x80, 0x60
    x = player_x + draw_dx - _BULLET_POINT_OFFSET_BY_HAND + step
    y = player_y + draw_dy - _BULLET_POINT_OFFSET_BY_HAND + step
    bullets = [enemy_bullet_record(x=x, y=y, active=1)]
    bullets += [enemy_bullet_record() for _ in range(ENEMY_BULLET_SLOTS - 1)]
    _bullet_case(bullets, player_x, player_y, _BULLET_PLAYER_FRAME, f"absolute offset step={step}")


def test_enemy_bullet_walk_reaches_the_sixteenth_record():
    """`move.w #$f,d7` is a dbf count, so the walk covers SIXTEEN records. The slot index is written
    out here rather than derived from the slot count, which is what makes a fifteen-slot walk red."""
    player_x, player_y = 0x80, 0x60
    bullets = [enemy_bullet_record(x=0x300, y=0x300, active=1)
               for _ in range(_ENEMY_BULLET_LAST_SLOT_BY_HAND)]
    bullets.append(enemy_bullet_record(x=player_x, y=player_y, active=1))
    _bullet_case(bullets, player_x, player_y, _BULLET_PLAYER_FRAME, "the sixteenth record")


@pytest.mark.parametrize("chunk", range(4))
def test_enemy_bullet_fuzz(chunk):
    """Random bullets over the whole word range against random player positions and frames."""
    rng = random.Random(0x1101c + chunk)
    for _ in range(20):
        bullets = [enemy_bullet_record(x=rng.randrange(0x10000), y=rng.randrange(0x10000),
                                       active=rng.randrange(2))
                   for _ in range(ENEMY_BULLET_SLOTS)]
        _bullet_case(bullets, rng.randrange(0x10000), rng.randrange(0x10000), rng.randrange(256),
                     f"fuzz chunk={chunk}")


# ==================================================================================================
# level_progress_check @ 0x124ae
# ==================================================================================================
def _progress_pokes(started_level_pokes, overrides=None):
    pokes = dict(started_level_pokes)
    pokes.update({A_level_complete: word(0), A_game_over_flag: word(0),
                  A_player: player_record(x=0x8f, y=0x7e, frame=2, shadow=1,
                                          mode=PLAYER_MODE_JOYSTICK),
                  A_player_hit: word(0)})
    pokes.update(overrides or {})
    return pokes


@pytest.mark.parametrize("offset", (-1, 0, 1))
@pytest.mark.parametrize("which", ("end", "boss"))
def test_progress_triggers_at_the_level_end_and_at_the_boss(started_level_pokes, offset, which):
    """Both thresholds are `cmp.w <trigger>,d0` with the SCROLL position, one `ble` and one `bgt`,
    so each needs its own one-either-side probe. The level record is the game's own: the end is at
    0x12f2 and the boss at 0x128e on level 0."""
    trigger = A_level_end_scroll_pos if which == "end" else A_boss_scroll_pos
    base = started_level_pokes[trigger] if trigger in started_level_pokes else None
    value = int.from_bytes(harness.BASE_IMAGE[trigger:trigger + 2], "big") if base is None \
        else int.from_bytes(base[:2], "big")
    _case(ENTRY_LEVEL_PROGRESS_CHECK,
          {"_pokes": _progress_pokes(started_level_pokes,
                                     {A_scroll_pos: word(value + offset)})},
          lambda lib, buf: lib.g_level_progress_check(buf), note=f"{which} offset={offset}")


@pytest.mark.parametrize("mode", (PLAYER_MODE_JOYSTICK, PLAYER_MODE_LANDING, PLAYER_MODE_FLYOFF,
                                  PLAYER_MODE_DYING))
@pytest.mark.parametrize("game_over", (0, 1))
def test_progress_two_gates(started_level_pokes, mode, game_over):
    """A plane on the landing script leaves through a bare `rts` shared with the two turn routines,
    and `game_over_flag` gates the rest off — over a scroll position past BOTH triggers."""
    _case(ENTRY_LEVEL_PROGRESS_CHECK,
          {"_pokes": _progress_pokes(started_level_pokes,
                                     {A_scroll_pos: word(0x2000),
                                      A_game_over_flag: word(game_over),
                                      A_player: player_record(x=0x8f, y=0x7e, frame=2, shadow=1,
                                                              mode=mode)})},
          lambda lib, buf: lib.g_level_progress_check(buf), note=f"mode={mode} over={game_over}")


@pytest.mark.parametrize("level", range(LEVELS))
def test_progress_advances_the_level(started_level_pokes, level):
    """The advance arm, which unwinds its caller into the frame loop rather than returning."""
    _case(ENTRY_LEVEL_PROGRESS_CHECK,
          {"_pokes": _progress_pokes(started_level_pokes,
                                     {A_level_complete: word(1), A_level_number: word(level)})},
          lambda lib, buf: lib.g_level_progress_check(buf),
          stop_pc=STOP_FRAME_LOOP_REENTRY, note=f"level={level}")


@pytest.mark.parametrize("flags", range(8))
def test_progress_wraps_the_fifth_level_through_the_three_loop_flags(started_level_pokes, flags):
    """Past level 4 the game LOOPS, and where it restarts is the first of three one-shot flags that
    is still clear: 1, then 2, then 3, and on the fourth pass all three are cleared and it starts at
    0 again. All eight flag combinations, so each arm is reached from a state the game can be in and
    from three it cannot."""
    pokes = _progress_pokes(started_level_pokes,
                            {A_level_complete: word(1), A_level_number: word(LEVELS - 1)})
    for index, flag in enumerate((A_level_loop_flag_1, A_level_loop_flag_2, A_level_loop_flag_3)):
        pokes[flag] = word((flags >> index) & 1)
    _case(ENTRY_LEVEL_PROGRESS_CHECK, {"_pokes": pokes},
          lambda lib, buf: lib.g_level_progress_check(buf),
          stop_pc=STOP_FRAME_LOOP_REENTRY, note=f"flags={flags:#05b}")


# ==================================================================================================
# restart_level_at_checkpoint @ 0x14aa8, SLICE [0x14aac, 0x14b22)
# ==================================================================================================
def _checkpoint_record(level, index):
    """One six-byte record of the shipped table for `level`, read out of the loaded image."""
    table = int.from_bytes(harness.BASE_IMAGE[A_checkpoint_tables
                                              + level * CHECKPOINT_TABLE_PTR_BYTES:
                                              A_checkpoint_tables
                                              + (level + 1) * CHECKPOINT_TABLE_PTR_BYTES], "big")
    start = table + index * CHECKPOINT_REC_BYTES
    return harness.BASE_IMAGE[start:start + CHECKPOINT_REC_BYTES]


def _restart_case(level, scroll_pos, note):
    pokes = {A_level_number: word(level), A_scroll_pos: word(scroll_pos),
             A_level_just_started: word(0), A_player_hit: word(0xa5a5),
             A_key_bits: bytes([0xff]), A_key_last_scancode: bytes([0xff]),
             A_joy1_state: bytes([0xff]), A_joy0_state: bytes([0xff]),
             A_checkpoint_map_offset: word(0xdead), A_checkpoint_scroll_pos: word(0xbeef),
             A_checkpoint_scroll_fine: word(0xcafe)}
    # No poison pass: the scan reads `scroll_pos` AFTER subtracting from it, so inverting that word
    # would send the second run's walk somewhere else entirely.
    _case(ENTRY_RESTART_LEVEL_SETUP, {"_pokes": pokes},
          lambda lib, buf: lib.g_restart_level_at_checkpoint_setup(buf),
          stop_pc=STOP_CLEAR_ACTOR_ARRAYS, note=note)


@pytest.mark.parametrize("level", range(LEVELS))
@pytest.mark.parametrize("record", range(1, CHECKPOINT_RECORDS))
def test_restart_finds_the_checkpoint_behind_the_plane(level, record):
    """The scan walks BACKWARDS from the seventh record's scroll word and stops at the first record
    behind the plane, so a scroll position just past record n's own scroll must land on record n.
    Every level's table, every record but the first — driven at the record's own scroll position,
    which is where the `blt` either takes this record or steps past it."""
    scroll = int.from_bytes(_checkpoint_record(level, record - 1)[CHECKPOINT_REC_SCROLL_POS:
                                                                  CHECKPOINT_REC_SCROLL_POS + 2],
                            "big")
    _restart_case(level, scroll + CHECKPOINT_SCROLL_BACK, f"level={level} record={record}")


@pytest.mark.parametrize("level", range(LEVELS))
@pytest.mark.parametrize("step", (-1, 0, 1))
def test_restart_scan_edge_at_the_first_record(level, step):
    """One step either side of record 0's own scroll word, which is where the scan either stops on
    the level's first checkpoint or walks off the FRONT of the table — the walk has no floor, and
    the arithmetic is the original's whichever side it lands on."""
    scroll = int.from_bytes(_checkpoint_record(level, 0)[CHECKPOINT_REC_SCROLL_POS:
                                                         CHECKPOINT_REC_SCROLL_POS + 2], "big")
    _restart_case(level, scroll + CHECKPOINT_SCROLL_BACK + step, f"level={level} step={step}")


@pytest.mark.parametrize("level", range(LEVELS))
def test_restart_scan_starts_on_the_seventh_records_scroll_word(level):
    """A scroll position past every checkpoint INCLUDING the tables' 0x2710 sentinel, which is the
    only thing that says where the scan starts: below the sentinel every start point from record 5
    upwards finds the same record, so `CHECKPOINT_SCAN_FROM 0x26 -> 0x20` SURVIVED the battery until
    this case was added (measured 2026-09-07). Here the scan stops on the sentinel record itself."""
    _restart_case(level, 0x3000, f"past the sentinel, level={level}")


def test_restart_on_a_started_level(started_level_pokes):
    """The same slice over the machine `start_level` itself left, rather than over poked globals."""
    pokes = dict(started_level_pokes)
    pokes[A_scroll_pos] = word(0x800)
    _case(ENTRY_RESTART_LEVEL_SETUP, {"_pokes": pokes},
          lambda lib, buf: lib.g_restart_level_at_checkpoint_setup(buf),
          stop_pc=STOP_CLEAR_ACTOR_ARRAYS, note="started level")


# ==================================================================================================
# Pins — see README.md, "Adding a function", step 4
# ==================================================================================================
MIRRORS = (
    ("A_player", "include/player.h", "A_player"),
    ("PLAYER_MODE", "include/player.h", "PLAYER_MODE"),
    ("PLAYER_MODE_GAMEOVER", "include/player.h", "PLAYER_MODE_GAMEOVER"),
    ("A_lives", "include/player.h", "A_lives"),
    ("A_bombs", "include/player.h", "A_bombs"),
    ("A_player_hit", "include/player.h", "A_player_hit"),
    ("A_dl_player_shadow", "include/player.h", "A_dl_player_shadow"),
    ("A_dl_bomb_icons", "include/hud.h", "A_dl_bomb_icons"),
    ("A_const_words_0123", "include/hud.h", "A_const_words_0123"),
    ("A_key_bits", "include/irq.h", "A_key_bits"),
    ("A_joy1_state", "include/irq.h", "A_joy1_state"),
    ("JOY_FIRE_BIT", "include/hud.h", "JOY_FIRE_BIT"),
    ("A_invuln_flag", "include/hud.h", "A_invuln_flag"),
    ("A_infinite_lives_flag", "include/hud.h", "A_infinite_lives_flag"),
    ("A_infinite_bombs_flag", "include/hud.h", "A_infinite_bombs_flag"),
    ("A_max_weapon_flag", "include/hud.h", "A_max_weapon_flag"),
    ("A_scroll_pos", "include/scroll.h", "A_scroll_pos"),
    ("PLAYER_X", "include/player.h", "PLAYER_X"),
    ("PLAYER_Y", "include/player.h", "PLAYER_Y"),
    ("PLAYER_FRAME", "include/player.h", "PLAYER_FRAME"),
    ("A_weapon_level", "include/weapons.h", "A_weapon_level"),
    ("A_entity_group_a0", "include/entity.h", "A_entity_group_a0"),
    ("A_entity_group_a1", "include/entity.h", "A_entity_group_a1"),
    ("A_entity_group_a2", "include/entity.h", "A_entity_group_a2"),
    ("A_entity_group_a3", "include/entity.h", "A_entity_group_a3"),
    ("A_entity_group_a4", "include/entity.h", "A_entity_group_a4"),
    ("ENTITY_GROUP_PTR_BYTES", "include/entity.h", "ENTITY_GROUP_PTR_BYTES"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_ACTIVE", "include/entity.h", "ENTITY_ACTIVE"),
    ("ENTITY_DYING", "include/entity.h", "ENTITY_DYING"),
    ("A_bomb_falling", "include/weapons.h", "A_bomb_falling"),
    ("A_bomb_exploding", "include/weapons.h", "A_bomb_exploding"),
    ("A_player_bomb", "include/weapons.h", "A_player_bomb"),
    ("BOMB_X", "include/weapons.h", "BOMB_X"),
    ("BOMB_START_Y", "include/weapons.h", "BOMB_START_Y"),
    ("A_player_shot_slot_0", "include/weapons.h", "A_player_shot_slot_0"),
    ("PLAYER_SHOT_SLOTS", "include/weapons.h", "PLAYER_SHOT_SLOTS"),
    ("PLAYER_SHOT_BULLETS", "include/weapons.h", "PLAYER_SHOT_BULLETS"),
    ("PLAYER_SHOT_TABLE_STRIDE", "include/weapons.h", "PLAYER_SHOT_TABLE_STRIDE"),
    ("A_shot_slot_busy_0", "include/weapons.h", "A_shot_slot_busy_0"),
    ("SHOT_SLOT_BUSY_BYTES", "include/weapons.h", "SHOT_SLOT_BUSY_BYTES"),
    ("PLAYER_BULLET_X", "include/weapons.h", "PLAYER_BULLET_X"),
    ("PLAYER_BULLET_Y", "include/weapons.h", "PLAYER_BULLET_Y"),
    ("PLAYER_BULLET_DX", "include/weapons.h", "PLAYER_BULLET_DX"),
    ("PLAYER_BULLET_STATE", "include/weapons.h", "PLAYER_BULLET_STATE"),
    ("PLAYER_BULLET_BYTES", "include/weapons.h", "PLAYER_BULLET_BYTES"),
    ("A_enemy_bullets", "include/weapons.h", "A_enemy_bullets"),
    ("ENEMY_BULLET_BYTES", "include/weapons.h", "ENEMY_BULLET_BYTES"),
    ("ENEMY_BULLET_X", "include/weapons.h", "ENEMY_BULLET_X"),
    ("ENEMY_BULLET_Y", "include/weapons.h", "ENEMY_BULLET_Y"),
    ("ENEMY_BULLET_ACTIVE", "include/weapons.h", "ENEMY_BULLET_ACTIVE"),
    ("A_sound_module", "include/globals.h", "A_sound_module"),
    ("SND_SFX_ACTIVE", "include/sound.h", "SND_SFX_ACTIVE"),
    ("A_music_suspend_flag", "include/sound.h", "A_music_suspend_flag"),
    ("A_sprite_bank", "include/globals.h", "A_sprite_bank"),
    ("SPRITE_RECORD_BYTES", "include/globals.h", "SPRITE_RECORD_BYTES"),
    ("ENTITY_STRIDE", "include/globals.h", "ENTITY_STRIDE"),
    ("SPRITE_REC_DRAW_DX", "include/sprite.h", "SPRITE_REC_DRAW_DX"),
    ("SPRITE_REC_DRAW_DY", "include/sprite.h", "SPRITE_REC_DRAW_DY"),
    ("SPRITE_REC_HIT_W", "include/sprite.h", "SPRITE_REC_HIT_W"),
    ("SPRITE_REC_HIT_H", "include/sprite.h", "SPRITE_REC_HIT_H"),
    ("SCC_TRUE", "include/common.h", "SCC_TRUE"),
    ("JOY_UP_BIT", "src/player.c", "JOY_UP_BIT"),
    ("JOY_DOWN_BIT", "src/player.c", "JOY_DOWN_BIT"),
    ("JOY_LEFT_BIT", "src/player.c", "JOY_LEFT_BIT"),
    ("JOY_RIGHT_BIT", "src/player.c", "JOY_RIGHT_BIT"),
    ("KEY_PAUSE_BIT", "src/player.c", "KEY_PAUSE_BIT"),
    ("KEY_ABORT_BIT", "src/player.c", "KEY_ABORT_BIT"),
    ("KEY_BOMB_BIT", "src/player.c", "KEY_BOMB_BIT"),
    ("PAUSE_WAIT_PC", "src/player.c", "PAUSE_WAIT_PC"),
    # ...and everything else this battery pokes, which is include/player.h's.
    "PLAYER_SHADOW_FRAME", "PLAYER_RECORD_BYTES",
    "PLAYER_MODE_JOYSTICK", "PLAYER_MODE_LANDING", "PLAYER_MODE_FLYOFF", "PLAYER_MODE_DYING",
    "PLAYER_MODE_TAKEOFF",
    "A_player_start_template", "A_takeoff_start_pos", "A_landing_start_pos",
    "A_takeoff_script", "A_takeoff_script_cursor", "A_landing_script", "A_landing_script_cursor",
    "SCRIPT_TEMPLATE_WORDS", "SCRIPT_STEP_BYTES", "SCRIPT_STEP_FRAME",
    "A_player_input_locked", "A_player_turning", "A_player_script_timer",
    "A_player_script_fire_enable", "A_shadow_offset", "A_takeoff_shadow_timer",
    "A_landing_shadow_timer", "A_landing_bomb_cash_timer", "A_level_complete",
    "SHADOW_OFFSET_LANDED", "SHADOW_OFFSET_AIRBORNE", "TAKEOFF_SHADOW_PERIOD",
    "LANDING_SHADOW_PERIOD", "BOMB_CASH_PERIOD", "SHADOW_FRAME_AIRBORNE", "SHADOW_FRAME_ON_DECK",
    "SHADOW_FRAME_OFFSET", "FLYOFF_TARGET_X", "FLYOFF_TARGET_Y", "FLYOFF_HOVER_FRAMES",
    "A_player_bank", "A_player_bank_frames", "PLAYER_BANK_CENTRE",
    "PLAYER_STEP_PIXELS", "PLAYER_Y_MIN", "PLAYER_Y_MAX", "PLAYER_X_MAX",
    "A_player_death_frames", "A_death_anim_cursor", "DEATH_FRAME_BYTES", "DEATH_SINK_PIXELS",
    "A_dl_player", "A_text_game_over", "A_game_over_flag", "A_game_over_delay",
    ("CONST_WORD_BYTES", "include/hud.h", "CONST_WORD_BYTES"),
    "LIVES_AFTER_GAME_OVER", "BOMBS_AFTER_GAME_OVER",
    "BOMB_DROP_X_OFFSET", "BOMBS_MIN_TO_DROP",
    "A_fire_held", "A_shot_slots_full", "A_weapon_fire_tbl", "WEAPON_FIRE_PTR_BYTES",
    "WEAPON_LEVEL_MAX", "A_debug_overlay_flag", "SFX_PLAYER_FIRE", "BULLET_MUZZLE_DY",
    "PLAYER_HIT_BOX_W", "PLAYER_HIT_BOX_H",
    "ENTITY_BOX_DX", "ENTITY_BOX_DY", "ENTITY_BOX_H", "ENTITY_BOX_W", "ENTITY_A_GROUP_SLOTS",
    "ENTITY_BOX_A4_DX", "ENTITY_BOX_A4_DY", "ENTITY_BOX_A4_H", "ENTITY_BOX_A4_W",
    "ENTITY_A4_GROUP_SLOTS", "ENEMY_BULLET_HIT_OFFSET", "ENEMY_BULLET_SLOTS",
    "A_level_end_scroll_pos", "A_boss_scroll_pos", "A_level_number", "LEVELS", "LEVEL_CLEAR_TUNE",
    "A_level_loop_flag_1", "A_level_loop_flag_2", "A_level_loop_flag_3",
    "LEVEL_LOOP_1_START", "LEVEL_LOOP_2_START", "LEVEL_LOOP_3_START",
    "A_level_just_started", "A_use_keyboard_flag",
    ("A_joy0_state", "include/irq.h", "A_joy0_state"),
    ("A_key_last_scancode", "include/irq.h", "A_key_last_scancode"),
    "A_checkpoint_tables", "A_checkpoint_map_offset", "A_checkpoint_scroll_pos",
    "A_checkpoint_scroll_fine", "CHECKPOINT_TABLE_PTR_BYTES", "CHECKPOINT_REC_BYTES",
    "CHECKPOINT_REC_MAP_OFFSET", "CHECKPOINT_REC_SCROLL_POS", "CHECKPOINT_REC_SCROLL_FINE",
    "CHECKPOINT_SCAN_FROM", "CHECKPOINT_SCROLL_BACK",
    "EXTEND_CLEAR",
    ("SCORE_AWARD_3000", "include/hud.h", "SCORE_AWARD_3000"),   # beside the values it indexes
)

ENTRY_PROLOGUES = {
    "ENTRY_PLAYER_VS_ENTITIES": "4a39000177c6664041f9000190a40c28",
    "ENTRY_PLAYER_VS_ENTITIES_GROUP_A4": "3e3c0003363c0004383c00033c3c001b",
    "ENTRY_PLAYER_VS_ENTITIES_GROUP": "3e3c0006363c0011383c000c3c3c0017",
    "ENTRY_PLAYER_VS_ENTITY_GROUP_TEST": "43f9000190a40c29000300066756205b",
    "ENTRY_PLAYER_VS_ENEMY_BULLETS": "4a39000177c6661041f90001946e45f9",
    "ENTRY_LEVEL_PROGRESS_CHECK": "4a790001775a664e41f9000190a40c28",
    "ENTRY_TAKEOFF_SCRIPT_RESET": "41f9000190ac43f9000177263e3c0004",
    "ENTRY_LANDING_SCRIPT_RESET": "41f9000190b643f9000177303e3c0004",
    "ENTRY_PLAYER_SCRIPT_STEP": "41f9000190a44a2800066b0000860c28",
    "ENTRY_PLAYER_BANK_RECENTRE": "4a790001775c67024e750c7900070001",
    "ENTRY_PLAYER_DEATH_SEQUENCE_STEP": "43f900019210d2f9000176f64a516b4e",
    "ENTRY_PLAYER_PUBLISH": "41f9000190a44a2800066b1e0c280001",
    "ENTRY_PLAYER_FRAME_FROM_BANK": "45f900017744d4f90001774211520004",
    "ENTRY_PLAYER_RESET_TO_START": "41f90001909c45f900017744d4f90001",
    "ENTRY_BOMB_DROP": "4a79000176f0663a4a79000176ee6632",
    "ENTRY_PLAYER_MOVE_UP": "0c68000c00026d060468000600024e75",
    "ENTRY_PLAYER_MOVE_DOWN": "0c6800ba00026e000008066800060002",
    "ENTRY_PLAYER_MOVE_LEFT": "4a5067206b1e0450000645f900017744",
    "ENTRY_PLAYER_MOVE_RIGHT": "0c5001206e0000220650000645f90001",
    "ENTRY_PLAYER_FIRE": "4a39000177cd670461000b444a790001",
    "ENTRY_PLAYER_SHOT_SLOT_ALLOC": "4a7900017716661a33fc000100017716",
    "ENTRY_PLAYER_FIRE_BY_WEAPON_LEVEL": "41f9000192324a39000177ca670833fc",
    "ENTRY_FIRE_PATTERN_LEVEL0": "41f9000190a43010322800020641000a",
    "ENTRY_FIRE_PATTERN_LEVEL1": "41f9000190a43010322800020641000a",
    "ENTRY_FIRE_PATTERN_LEVEL2": "41f9000190a43010322800020641000a",
    "ENTRY_FIRE_PATTERN_LEVEL3": "41f9000190a43010322800020641000a",
    "ENTRY_FIRE_PATTERN_LEVEL4": "41f9000190a43010322800020641000a",
    "ENTRY_READ_PLAYER_INPUT": "4a790001770e670a1039000177806000",
    "ENTRY_RESTART_LEVEL_SETUP": "50f90001769642390001778142390001",
    "ENTRY_START_LEVEL": "33f9000176b200017710610028d86100",
}

STOP_PROLOGUES = {
    # The same address as `test_hud.py`'s ENTRY_CONSOLE_SHOW_MESSAGE, and named again here for the
    # same reason it is named there: it is where `debug_show_counters`' slice STOPS.
    "STOP_CONSOLE_SHOW_MESSAGE": "20790001641a3f3cffff2f3cffffffff",
    "STOP_SCORE_ADD_200": "6000fb364a39000177c6661041f90001",
    "STOP_FRAME_LOOP_REENTRY": "588f6000323a4a790001769c661250f9",
    "STOP_CLEAR_ACTOR_ARRAYS": "6100cabe6100cad46100f1f842b90001",
    "STOP_RESTART_LEVEL": "6100c6fc50f900017696423900017781",
    "STOP_MAIN_REENTRY": "6100bba46100bc406100bef66100c29a",
}
