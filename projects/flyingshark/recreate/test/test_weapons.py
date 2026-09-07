"""Differential battery for the weapons subsystem — src/weapons.c.

WHERE THE CASES' WORLDS COME FROM. Three shapes, and each routine needs one of them:

* a LEAF that takes its records in registers — the two collision group passes, the muzzle-flash
  publishers, `enemy_bullet_spawn_aimed`, `turret_aim_step` and the five spawn bodies — is driven
  over records poked into `abi.SCRATCH` and into the arena slots the GAME'S OWN tables name, read
  out of `harness.BASE_IMAGE` rather than assumed. That is what lets a case spell an edge the game's
  own data never reaches: a hit-handler index the shipped descriptors never carry, a hit box a
  sprite record never has, a formation slot the level scripts never retire;
* a whole-array pass — the bomb, the blast, the three shot slots, the enemy bullets — is driven over
  the real arrays with their records poked, because their addresses are the routine's own `lea`s;
* and the four frame-loop passes (`bomb_blast_vs_entities`, `player_bullets_vs_entities`,
  `enemies_fire_all`, `turrets_publish_all`) are ALSO driven over a POPULATED WORLD the original
  built itself: `conftest.py`'s `staged_world_pokes` runs the game's own `spawn_script_step`
  @ 0x12fc4 under the oracle against level 1's script. A hand-poked world contains only the shapes
  its author thought of; that one contains what the game spawns. It is this file's own routine doing
  the spawning, which makes the fixture a second reading of it as well as a world — and it is
  `test_entity.py`'s world too, built once a run rather than once per battery per core.

WHAT THE HIT HANDLERS ARE DRIVEN THROUGH, and why not directly. Both dispatchers read a handler
ADDRESS out of a constant table indexed by the descriptor's ENEMY_DESC_KIND, so poking that one word
selects any of the nineteen entries — which is how every one of the twenty-three handlers is
reached here, dispatch included, without twenty-three more entry addresses. The X flag those
handlers inherit is `lsl.w #2`'s last bit out, provably zero for every index either table can serve
(src/weapons.c, HIT_DISPATCH_EXTEND), so no case drives it: `abi.extend_call_pokes` has no use here.

THE THREE SPAWN BODIES SHARE A PROLOGUE. `spawn_formation_common` @ 0x130aa,
`spawn_bigobj_parts_common` @ 0x132dc and `spawn_turret_common` @ 0x1343e are byte-identical for
their first 0x94 bytes — the whole of pass one — so their ENTRY_PROLOGUES rows pin that an address
still holds THAT SHAPE and cannot tell the three apart. What tells them apart is pass two, and the
cases below drive all three over the same formation and diff the fields each writes.
"""
import ctypes
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

MIRROR_HEADER = "include/weapons.h"

# ---- entries -------------------------------------------------------------------------------------
ENTRY_BOMB_BLAST_STEP = 0x10c8c
ENTRY_BOMB_BLAST_PUBLISH = 0x10d20
ENTRY_BOMB_FALL_STEP = 0x10e7c
ENTRY_BOMB_PUBLISH = 0x10ee2
ENTRY_CLEAR_OBJECT_LIST = 0x115fc
ENTRY_BOMB_BLAST_VS_ENTITIES = 0x11a82
ENTRY_BOMB_BLAST_VS_ENTITIES_IF_ACTIVE = 0x11b90
ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS = 0x11bb6
ENTRY_PLAYER_BULLETS_VS_ENTITIES = 0x11de6
ENTRY_PLAYER_BULLETS_VS_ENTITIES_GROUP = 0x11e04
ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS = 0x11f0c
ENTRY_MUZZLE_FLASH_PUBLISH_ALL = 0x1227c
ENTRY_MUZZLE_FLASH_PUBLISH_PAIR = 0x122c0
ENTRY_MUZZLE_FLASH_PUBLISH_GROUP = 0x12348
ENTRY_ENEMY_BULLETS_PUBLISH = 0x125bc
ENTRY_ENEMIES_FIRE_ALL = 0x12602
ENTRY_ENEMY_BULLET_SPAWN_AIMED = 0x128ce
ENTRY_ENEMY_BULLETS_MOVE = 0x12964
ENTRY_TURRETS_AIM_ALL = 0x129b2
ENTRY_TURRETS_AIM_GROUP_ACTIVE = 0x12a34
ENTRY_TURRETS_AIM_GROUP = 0x12a50
ENTRY_TURRETS_PUBLISH_ALL = 0x12a60
ENTRY_TURRET_PUBLISH_GROUP = 0x12b40
ENTRY_TURRET_AIM_STEP = 0x12c04
ENTRY_SPAWN_SCRIPT_STEP = 0x12fc4
ENTRY_SPAWN_ITEM_BOMB = 0x13044
ENTRY_SPAWN_FORMATION_COMMON = 0x130aa
ENTRY_SPAWN_SINGLE_COMMON = 0x131a4
ENTRY_SPAWN_BIGOBJ_PARTS_COMMON = 0x132dc
ENTRY_SPAWN_TURRET_COMMON = 0x1343e
ENTRY_SPAWN_SQUADRON_COMMON = 0x13544
ENTRY_PLAYER_BULLETS_MOVE_ALL = 0x140cc
ENTRY_PLAYER_BULLETS_MOVE_GROUP = 0x140ea
ENTRY_PLAYER_BULLETS_PUBLISH_ALL = 0x14118
ENTRY_PLAYER_BULLETS_PUBLISH_GROUP = 0x14148
ENTRY_PLAYER_SHOT_SLOTS_RELEASE = 0x141b4
ENTRY_PLAYER_SHOT_SLOT_RELEASE_IF_EMPTY = 0x141e4

# ---- mirrors of include/weapons.h ----------------------------------------------------------------
A_player_bullet_arena, PLAYER_BULLET_BYTES = 0x5ae22, 8
PLAYER_BULLET_X, PLAYER_BULLET_Y, PLAYER_BULLET_DX, PLAYER_BULLET_STATE = 0, 2, 4, 6
PLAYER_BULLET_FREE, PLAYER_BULLET_IN_FLIGHT, PLAYER_BULLET_HIT = 0, 1, 2
A_player_shot_slot_0, PLAYER_SHOT_SLOTS, PLAYER_SHOT_BULLETS = 0x19422, 3, 5
PLAYER_SHOT_TABLE_STRIDE = 0x14
A_shot_slot_busy_0, SHOT_SLOT_BUSY_BYTES = 0x17716, 2
A_dl_player_bullets_0, DL_SHOT_STRIDE = 0x17b6a, 0x1e
PLAYER_BULLET_DY, PLAYER_BULLET_RETIRE_Y = 0x13, 0xfff8
PLAYER_BULLET_GLYPH, PLAYER_BULLET_GLYPH_ALT = 0x7f, 0xe4
PLAYER_BULLET_IMPACT_GLYPH = 0xe5

A_player_bomb = 0x5aed6
BOMB_X, BOMB_START_Y, BOMB_Y, BOMB_FRAME = 0, 2, 4, 6
A_bomb_fall_path, BOMB_PATH_DY, BOMB_PATH_FRAME, BOMB_PATH_STEP_BYTES = 0x15ce6, 0, 2, 4
A_blast_state, BLAST_X, BLAST_Y = 0x5aec2, 0, 2
BLAST_POINTS, BLAST_POINT_BYTES, BLAST_POINTS_COUNT = 4, 4, 4
A_blast_offset_tbl, BLAST_OFFSET_STEP_BYTES, BLAST_LAST_STEP = 0x1606e, 8, 0x0e
BLAST_GLYPH, BLAST_HIT_BOX = 0xd2, 0x20
A_blast_step, A_bomb_falling, A_bomb_exploding, A_bomb_path_cursor = 0x176ec, 0x176ee, 0x176f0, 0x176f2
A_dl_blast, A_dl_bomb = 0x17c8a, 0x17ca2

A_enemy_bullets, ENEMY_BULLET_BYTES = 0x1946e, 10
ENEMY_BULLET_X, ENEMY_BULLET_Y, ENEMY_BULLET_DX = 0, 2, 4
ENEMY_BULLET_DY, ENEMY_BULLET_ACTIVE = 6, 8
ENEMY_BULLET_END, ENEMY_BULLET_LIVE = 0x3e7, 1
A_dl_enemy_bullets, ENEMY_BULLET_GLYPH = 0x17bc4, 0x80
ENEMY_BULLET_CLIP_LEFT, ENEMY_BULLET_CLIP_RIGHT = 0xffda, 0x166
ENEMY_BULLET_CLIP_TOP, ENEMY_BULLET_CLIP_BOTTOM = 0xffda, 0xec
A_enemy_aim_dir_lut, AIM_LUT_ROW_STRIDE, AIM_CELL_SHIFT = 0x15f3a, 0x15, 5
A_enemy_bullet_velocity_tbl, AIM_VELOCITY_BYTES = 0x15fee, 4
ENEMY_DESC_MUZZLE_DX, ENEMY_DESC_MUZZLE_DY = 10, 12
ENEMY_FIRE_SPREAD, ENEMY_FIRE_RECOIL = 0x20, 0x19
ENEMY_FIRE_X_MAX, ENEMY_FIRE_Y_MAX, ENEMY_FIRE_Y_MIN_B = 0x13f, 0xa8, 0xfff0
ENEMY_AIM_PLAYER_OFFSET = 4

A_dl_turret_ptrs_t0, TURRET_FACINGS, TURRET_HALF_TURN = 0x192c6, 12, 6
A_turret_facing_lut, TURRET_LUT_ROW_STRIDE, TURRET_AIM_PLAYER_DX = 0x15dc3, 0x17, 4
A_turret_barrel_tbl_lo, A_turret_barrel_tbl_hi = 0x15b96, 0x15c56
TURRET_BARREL_STRIDE, TURRET_BARREL_ENTRY_BYTES = 0x18, 2
A_turret_hit_tbl_lo, A_turret_hit_tbl_hi, TURRET_HIT_ENTRY_BYTES = 0x15cb6, 0x15cd6, 4
A_turret_barrel_base_frame, TURRET_BARREL_BASE_FRAME_BYTE = 0x197f8, 1
TURRET_STATE_AIMING, TURRET_STATE_HIT = 0, 1

A_dl_muzzle_group, A_dl_muzzle_pair_0, DL_FLASH_PAIR = 0x17b3a, 0x179c6, 0x0c
MUZZLE_FLASH_GLYPH_BUMP = 3
MUZZLE_FLASH_GROUP_DX, MUZZLE_FLASH_GROUP_DY = 0x1a, 6
ENEMY_DESC_FLASH_DX, ENEMY_DESC_FLASH_DY = 28, 30
ENEMY_DESC_FLASH2_DX, ENEMY_DESC_FLASH2_DY = 32, 34

A_bullet_hit_handler_tbl, A_blast_hit_handler_tbl = 0x19134, 0x19180
HIT_HANDLER_PTR_BYTES, HIT_GROUPS, PLAYER_BULLET_HIT_DX = 4, 22, 5
ENEMY_DESC_FIRING_HP, ENEMY_HIT_DROP_OFFSET = 26, 0x11
BLAST_DAMAGE_4, BLAST_DAMAGE_5, BLAST_DAMAGE_6, BULLET_DAMAGE = 4, 5, 6, 1
BULLET_KILL_AT_HIT_POINTS, ENEMY_INDESTRUCTIBLE, ENEMY_FRAME_HURT_BUMP = 1, 0x3e7, 0x0c

A_spawn_script_ptr, A_spawn_script_cursor, A_item_bomb_spawned = 0x17770, 0x17754, 0x176a6
SPAWN_REC_TRIGGER, SPAWN_REC_TYPE, SPAWN_REC_X = 0, 2, 4
SPAWN_REC_Y, SPAWN_REC_FORMATION, SPAWN_REC_BYTES = 6, 8, 10
SPAWN_SCRIPT_END = 0xa3a1
A_spawn_handler_tbl, SPAWN_HANDLER_PTR_BYTES = 0x190c0, 4
SPAWN_TYPE_WEAPON_ITEM, SPAWN_TYPE_BOMB_ITEM, SPAWN_TYPE_FALLBACK = 1, 3, 2
FORMATION_POS_DX, FORMATION_POS_DY, FORMATION_POS_BYTES = 0, 2, 4
FORMATION_SLOT_UNUSED, FORMATION_SCRIPT_PTR_BYTES = 0x63, 4
FORMATION_TBL_ENTRY_BYTES, SPAWN_FACING_START = 4, 6
SPAWN_FIRE_COUNTDOWN_15, SPAWN_FIRE_COUNTDOWN_10 = 15, 10
SPAWN_DRAW_LAYER_TOP, SPAWN_DRAW_LAYER_UNDER = 1, 0xffff
A_formation_tbl_a, A_formation_tbl_b, A_formation_tbl_single = 0x1ae0c, 0x1af80, 0x19a54
A_formation_tbl_parts, A_formation_tbl_parts_b = 0x197fa, 0x198a4
A_formation_tbl_parts_c, A_formation_tbl_turret_a = 0x198f6, 0x1ac80
A_formation_tbl_turret_b, A_formation_tbl_squadron = 0x1a58c, 0x19b54
A_enemy_desc_0c, A_enemy_desc_0d, A_enemy_desc_0e, A_enemy_desc_0f = 0x19674, 0x1968e, 0x196a8, 0x196c2

# ---- borrowed from the neighbours' headers, spelt as full triples in MIRRORS -------------------
A_entity_arena, ENTITY_STRIDE, ENTITY_SLOTS = 0x59984, 58, 91
ENTITY_X, ENTITY_Y, ENTITY_FRAME_OFFSET, ENTITY_DRAW_LAYER = 0, 2, 4, 6
ENTITY_DX, ENTITY_DY, ENTITY_STEP_COUNTDOWN = 8, 10, 12
ENTITY_ACTIVE, ENTITY_DYING, ENTITY_ITEM_KIND, ENTITY_BASE_FRAME = 14, 16, 18, 20
ENTITY_HIT_POINTS, ENTITY_AIM_CHANGED, ENTITY_FACING, ENTITY_DEPTH_SELECT = 22, 24, 26, 28
ENTITY_FIRE_COUNTDOWN, ENTITY_FIRE_RELOAD, ENTITY_PATH_SELECT = 30, 32, 34
ENTITY_PATH_CURSOR, ENTITY_FIRING, ENTITY_FRAME_BUMP = 36, 38, 40
ENTITY_ANIM_TIMER, ENTITY_KIND, ENTITY_HIDDEN_UNDER_BIGOBJ = 42, 44, 48
ENTITY_SCRIPT_BASE, ENTITY_SCRIPT_CURSOR = 50, 54
ENTITY_GROUP_SLOTS, ENTITY_GROUP_A_SLOTS, ENTITY_GROUP_PTR_BYTES = 4, 7, 4
A_entity_group_a0, A_entity_group_t0, ENTITY_GROUP_T_STRIDE, ENTITY_GROUP_T_COUNT = 0x19246, 0x192b6, 0x20, 8
A_entity_group_x0, ENTITY_GROUP_X_STRIDE, ENTITY_GROUP_X_COUNT = 0x193c6, 0x10, 5
A_entity_group_bigobj, A_entity_group_a4 = 0x193b6, 0x1945e
DL_TURRET_RUN_GROUPS = 4
ENEMY_DESC_GROUP, ENEMY_DESC_BASE_FRAME, ENEMY_DESC_ITEM_KIND = 0, 4, 6
ENEMY_DESC_FIRE_RELOAD, ENEMY_DESC_COUNT_MINUS_1, ENEMY_DESC_HANDLER = 8, 14, 16
ENEMY_DESC_DEATH_DX, ENEMY_DESC_DEATH_DY, ENEMY_DESC_KIND, ENEMY_DESC_HIT_POINTS = 18, 20, 22, 24
A_enemy_desc_00, A_enemy_desc_04, A_enemy_desc_10 = 0x19534, 0x195a4, 0x196de
A_enemy_desc_14, A_enemy_desc_18 = 0x1975e, 0x197d2
A_anim_frame_a, A_anim_frame_b = 0x19518, 0x1951c
A_item_bomb, ITEM_X, ITEM_Y, ITEM_ACTIVE = 0x5aeae, 0, 2, 8
A_item_pickup_pending, A_weapon_level, WEAPON_LEVEL_FULL = 0x176c2, 0x17714, 4
MOVE_SCRIPT_BYTES, SCRIPT_TERMINATOR = 8, 0x3e7
A_display_list, DISPLAY_REC_BYTES = 0x177ce, 6
DISPLAY_REC_X, DISPLAY_REC_Y, DISPLAY_REC_FRAME, DISPLAY_REC_ACTIVE = 0, 2, 4, 5
DISPLAY_ACTIVE_ON_TOP, DISPLAY_ACTIVE_UNDER_SCENERY = 0x01, 0xff
A_player, PLAYER_X, PLAYER_Y = 0x190a4, 0, 2
A_player_hit, A_alt_bullet_glyph_flag, A_scroll_pos = 0x17706, 0x177c9, 0x17758
A_sprite_bank, SPRITE_RECORD_BYTES = 0x1be36, 20
SPRITE_REC_DRAW_DX, SPRITE_REC_DRAW_DY = 8, 10
SPRITE_REC_HIT_DX, SPRITE_REC_HIT_DY, SPRITE_REC_HIT_W, SPRITE_REC_HIT_H = 12, 14, 16, 18
A_sound_module, SND_SFX_ACTIVE = 0x58944, 0x1f

# The nineteen entries of each hit-handler table: poking a descriptor's ENEMY_DESC_KIND to one of
# these is how every handler in src/weapons.c is reached.
HIT_HANDLER_ENTRIES = 19

# Where a case parks the things it invents.
SCRATCH_DESC = abi.SCRATCH
SCRATCH_FORMATION = abi.SCRATCH + 0x100
SCRATCH_SCRIPT = abi.SCRATCH + 0x300
SCRATCH_RECORD = abi.SCRATCH + 0x400
SCRATCH_BLAST = abi.SCRATCH + 0x500

# ---- the glue's C signatures ---------------------------------------------------------------------
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
_GLUE_ARGS = {
    "g_clear_object_list": 0, "g_bomb_fall_step": 0, "g_bomb_publish": 0,
     "g_bomb_blast_publish": 0,
    "g_player_bullets_move_all": 0, "g_player_bullets_publish_all": 0,
    "g_player_shot_slots_release": 0, "g_bomb_blast_vs_entities": 0,
    "g_player_bullets_vs_entities": 0, "g_muzzle_flash_publish_all": 0,
    "g_enemy_bullets_move": 0, "g_enemy_bullets_publish": 0, "g_enemies_fire_all": 0,
    "g_turrets_aim_all": 0, "g_turrets_publish_all": 0, "g_spawn_script_step": 0,
    "g_bomb_blast_step": 1, "g_player_bullets_move_group": 1, "g_player_bullets_vs_entities_group": 1,
    "g_turret_aim_step": 1, "g_turrets_aim_group": 1, "g_turrets_aim_group_active": 1,
    "g_spawn_item_bomb": 1,
    "g_player_bullets_publish_group": 2, "g_player_shot_slot_release_if_empty": 2,
    "g_bomb_blast_vs_entity_groups": 2, "g_bomb_blast_vs_entities_if_active": 2,
    "g_player_bullet_vs_entity_groups": 2, "g_muzzle_flash_publish_pair": 2,
    "g_spawn_single_common": 2, "g_spawn_squadron_common": 2,
    "g_muzzle_flash_publish_group": 3, "g_spawn_formation_common": 3,
    "g_spawn_bigobj_parts_common": 3, "g_spawn_turret_common": 3,
    "g_turret_publish_group": 4,
    "g_enemy_bullet_spawn_aimed": 6,
}
for _name, _extra in _GLUE_ARGS.items():
    _fn = getattr(harness._lib, _name)
    _fn.argtypes = [_IMAGE] + [ctypes.c_uint32] * _extra
    _fn.restype = None


# `bomb_blast_vs_entity_groups` @ 0x11bb6 is entered mid-routine: its D7 point counter is set by
# `bomb_blast_vs_entities_if_active` @ 0x11b90, the only thing that reaches it, so every case that
# starts AT 0x11bb6 has to supply the count the guard would have.


def _case(entry, regs, glue, stop_pc=0, poison=False, note=""):
    diffs, _info = differential(entry, regs, glue, stop_pc=stop_pc, poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


# ---- record builders -----------------------------------------------------------------------------
def word(value):
    return (value & 0xffff).to_bytes(2, "big")


def long_word(value):
    return (value & 0xffffffff).to_bytes(4, "big")


_ENTITY_FIELDS = {
    "x": ENTITY_X, "y": ENTITY_Y, "frame_offset": ENTITY_FRAME_OFFSET,
    "draw_layer": ENTITY_DRAW_LAYER, "dx": ENTITY_DX, "dy": ENTITY_DY,
    "countdown": ENTITY_STEP_COUNTDOWN, "active": ENTITY_ACTIVE, "dying": ENTITY_DYING,
    "item_kind": ENTITY_ITEM_KIND, "base_frame": ENTITY_BASE_FRAME,
    "hit_points": ENTITY_HIT_POINTS, "aim_changed": ENTITY_AIM_CHANGED,
    "facing": ENTITY_FACING, "depth_select": ENTITY_DEPTH_SELECT,
    "fire_countdown": ENTITY_FIRE_COUNTDOWN, "fire_reload": ENTITY_FIRE_RELOAD,
    "path_select": ENTITY_PATH_SELECT, "path_cursor": ENTITY_PATH_CURSOR,
    "firing": ENTITY_FIRING, "frame_bump": ENTITY_FRAME_BUMP, "anim_timer": ENTITY_ANIM_TIMER,
    "kind": ENTITY_KIND, "hidden": ENTITY_HIDDEN_UNDER_BIGOBJ,
}


def entity_record(**fields):
    """A whole 58-byte entity record; everything unnamed is the zero `clear_actor_arrays` leaves."""
    record = bytearray(ENTITY_STRIDE)
    for name, value in fields.items():
        offset = _ENTITY_FIELDS[name]
        record[offset:offset + 2] = word(value)
    return bytes(record)


def bullet_record(x=0, y=0, dx=0, state=PLAYER_BULLET_FREE):
    return word(x) + word(y) + word(dx) + word(state)


def enemy_bullet_record(x=0, y=0, dx=0, dy=0, active=0):
    return word(x) + word(y) + word(dx) + word(dy) + word(active)


def display_record(x=0, y=0, frame=0, active=0):
    return word(x) + word(y) + bytes([frame & 0xff, active & 0xff])


def sprite_record(data=0, width=0, rows=0, draw_dx=0, draw_dy=0,
                  hit_dx=0, hit_dy=0, hit_w=0, hit_h=0):
    return (long_word(data) + word(width) + word(rows) + word(draw_dx) + word(draw_dy)
            + word(hit_dx) + word(hit_dy) + word(hit_w) + word(hit_h))


def descriptor(group=A_entity_group_a0, base_frame=0, item_kind=0, fire_reload=0,
               count_minus_1=ENTITY_GROUP_SLOTS - 1, handler=0, death_dx=0, death_dy=0,
               kind=0, hit_points=0, firing_hp=0, flash_dx=0, flash_dy=0,
               flash2_dx=0, flash2_dy=0, muzzle_dx=0, muzzle_dy=0):
    """A whole 36-byte enemy descriptor, long enough for every field any routine here reads."""
    record = bytearray(36)
    record[ENEMY_DESC_GROUP:ENEMY_DESC_GROUP + 4] = long_word(group)
    for offset, value in ((ENEMY_DESC_BASE_FRAME, base_frame), (ENEMY_DESC_ITEM_KIND, item_kind),
                          (ENEMY_DESC_FIRE_RELOAD, fire_reload), (ENEMY_DESC_MUZZLE_DX, muzzle_dx),
                          (ENEMY_DESC_MUZZLE_DY, muzzle_dy),
                          (ENEMY_DESC_COUNT_MINUS_1, count_minus_1),
                          (ENEMY_DESC_HANDLER, handler), (ENEMY_DESC_DEATH_DX, death_dx),
                          (ENEMY_DESC_DEATH_DY, death_dy), (ENEMY_DESC_KIND, kind),
                          (ENEMY_DESC_HIT_POINTS, hit_points), (ENEMY_DESC_FIRING_HP, firing_hp),
                          (ENEMY_DESC_FLASH_DX, flash_dx), (ENEMY_DESC_FLASH_DY, flash_dy),
                          (ENEMY_DESC_FLASH2_DX, flash2_dx), (ENEMY_DESC_FLASH2_DY, flash2_dy)):
        record[offset:offset + 2] = word(value)
    return bytes(record)


def formation(positions, script_offsets, script_base):
    """A formation record: `positions` (dx, dy) pairs, one script offset each, then the base."""
    out = bytearray()
    for dx, dy in positions:
        out += word(dx) + word(dy)
    for offset in script_offsets:
        out += long_word(offset)
    out += long_word(script_base)
    return bytes(out)


def script_record(trigger=0, kind=0, x=0, y=0, formation_index=0):
    return word(trigger) + word(kind) + word(x) + word(y) + word(formation_index)


def move_script(*steps):
    """8-byte {dx, dy, duration, frame} records — the spawn reads one, never the terminator."""
    out = bytearray()
    for dx, dy, duration, frame in steps:
        out += word(dx) + word(dy) + word(duration) + word(frame)
    return bytes(out)


def table_pointer(base, index=0):
    """The longword the GAME'S OWN table holds — read out of the loaded image, not assumed."""
    address = base + index * ENTITY_GROUP_PTR_BYTES
    return int.from_bytes(harness.BASE_IMAGE[address:address + 4], "big")


def group_pokes(group, records, count=ENTITY_GROUP_SLOTS):
    """Poke `records` into the arena slots `group` names; a short list leaves the rest zeroed."""
    return {table_pointer(group, index): (records[index] if index < len(records)
                                          else entity_record())
            for index in range(count)}


def shot_pokes(shot, records):
    """The same for one of the three player-shot slot tables."""
    table = A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE
    return {table_pointer(table, index): (records[index] if index < len(records)
                                          else bullet_record())
            for index in range(PLAYER_SHOT_BULLETS)}


def sprite_bank_pokes(frame, **fields):
    return {A_sprite_bank + frame * SPRITE_RECORD_BYTES: sprite_record(**fields)}


def enemy_bullet_array(records):
    """The 999-terminated array as one blob: `records`, then the sentinel every walk stops at."""
    return b"".join(records) + enemy_bullet_record(active=ENEMY_BULLET_END)




# ==================================================================================================
# clear_object_list @ 0x115fc — the enemy-bullet array's wholesale wipe
# ==================================================================================================
@pytest.mark.parametrize("live", (0, 1, 4, 16))
def test_clear_object_list_stops_at_its_own_sentinel(live):
    """Every WORD up to the 999 is cleared, and the sentinel and everything past it survives."""
    records = [enemy_bullet_record(x=0x100 + n, y=0x40 + n, dx=-2, dy=3, active=ENEMY_BULLET_LIVE)
               for n in range(live)]
    tail = enemy_bullet_record(x=0x777, y=0x888, dx=0x999, dy=0xaaa, active=0xbbb)
    _case(ENTRY_CLEAR_OBJECT_LIST,
          {"_pokes": {A_enemy_bullets: enemy_bullet_array(records) + tail}},
          lambda lib, buf: lib.g_clear_object_list(buf), poison=True, note=f"live={live}")


def test_clear_object_list_over_a_slot_whose_x_is_the_sentinel_value():
    """The walk tests EVERY word, not the active word of every record, so a coordinate that happens
    to be 999 ends the clear early. That is the routine, and it is why nothing may put 999 in an x."""
    _case(ENTRY_CLEAR_OBJECT_LIST,
          {"_pokes": {A_enemy_bullets:
                      enemy_bullet_record(x=1, y=2, dx=3, dy=4, active=ENEMY_BULLET_LIVE)
                      + enemy_bullet_record(x=ENEMY_BULLET_END, y=5, active=ENEMY_BULLET_LIVE)
                      + enemy_bullet_array([])}},
          lambda lib, buf: lib.g_clear_object_list(buf), note="x == 999")


# ==================================================================================================
# The smart bomb: bomb_fall_step @ 0x10e7c and bomb_publish @ 0x10ee2
# ==================================================================================================
_FALL_PATH = bytes().join(word(dy) + word(frame) for dy, frame in
                          ((0, 0x30), (4, 0x31), (12, 0x32), (0x7fff, 0x33))) \
             + word(SCRIPT_TERMINATOR) + word(0)


def _bomb_pokes(falling=1, exploding=0, cursor=0, x=0x50, start_y=0x60, y=0x60, frame=0):
    return {A_bomb_falling: word(falling), A_bomb_exploding: word(exploding),
            A_bomb_path_cursor: long_word(cursor),
            A_player_bomb: word(x) + word(start_y) + word(y) + word(frame),
            A_bomb_fall_path: _FALL_PATH}


@pytest.mark.parametrize("cursor", (0, 4, 8, 12, 16))
def test_bomb_fall_walks_the_path(cursor):
    """Each step sets the frame and re-derives y from BOMB_START_Y, and the 999 ends the fall."""
    _case(ENTRY_BOMB_FALL_STEP, {"_pokes": _bomb_pokes(cursor=cursor)},
          lambda lib, buf: lib.g_bomb_fall_step(buf), poison=True, note=f"cursor={cursor}")


@pytest.mark.parametrize("start_y", (0, 1, 0x7ffd, 0x8000, 0xfffc))
def test_bomb_fall_y_is_a_word_add_that_wraps(start_y):
    """y = BOMB_START_Y + path dy as a WORD, so 0x7ffd + 4 is negative and not 0x8001."""
    _case(ENTRY_BOMB_FALL_STEP, {"_pokes": _bomb_pokes(cursor=4, start_y=start_y)},
          lambda lib, buf: lib.g_bomb_fall_step(buf), note=f"start_y={start_y:#x}")


def test_bomb_fall_does_nothing_while_the_bomb_is_not_falling():
    _case(ENTRY_BOMB_FALL_STEP, {"_pokes": _bomb_pokes(falling=0, cursor=4)},
          lambda lib, buf: lib.g_bomb_fall_step(buf), note="not falling")


def test_bomb_impact_arms_the_blast():
    """Reached two ways — the path's 999, and `bomb_exploding` already set — and both copy the
    bomb's LIVE y into the blast, never its start row."""
    for note, pokes in (("terminator", _bomb_pokes(cursor=16, y=0xa4)),
                        ("already exploding", _bomb_pokes(exploding=1, cursor=4, y=0xa4))):
        _case(ENTRY_BOMB_FALL_STEP, {"_pokes": pokes},
              lambda lib, buf: lib.g_bomb_fall_step(buf), note=note)


@pytest.mark.parametrize("falling,exploding", ((1, 0), (0, 0), (1, 1), (0, 1)))
def test_bomb_publish_while_falling(falling, exploding):
    """The frame is a WORD in the record and a BYTE in the display list, so 0x1234 publishes 0x34."""
    pokes = _bomb_pokes(falling=falling, exploding=exploding, x=0x123, y=0x45, frame=0x1234)
    pokes[A_dl_bomb] = display_record(x=0x7777, y=0x8888, frame=0x99, active=0xaa)
    _case(ENTRY_BOMB_PUBLISH, {"_pokes": pokes},
          lambda lib, buf: lib.g_bomb_publish(buf), poison=True,
          note=f"falling={falling} exploding={exploding}")


# ==================================================================================================
# The blast: bomb_blast_step @ 0x10c8c and bomb_blast_publish @ 0x10d20
# ==================================================================================================
_BLAST_OFFSETS = bytes(range(0x80 - 8 * 4, 0x80 + 8 * (BLAST_LAST_STEP + 1) - 8 * 4))


def _blast_pokes(exploding=1, step=0, x=0x80, y=0x60):
    return {A_bomb_exploding: word(exploding), A_blast_step: word(step),
            A_bomb_falling: word(1), A_bomb_path_cursor: long_word(0x10),
            A_blast_state: word(x) + word(y) + bytes(BLAST_POINTS_COUNT * BLAST_POINT_BYTES),
            A_blast_offset_tbl: _BLAST_OFFSETS,
            A_enemy_bullets: enemy_bullet_array(
                [enemy_bullet_record(x=1, y=2, active=ENEMY_BULLET_LIVE)])}


@pytest.mark.parametrize("step", tuple(range(BLAST_LAST_STEP + 2)))
def test_blast_step_walks_the_offsets(step):
    """Every step of the table, plus the one past its end: at BLAST_LAST_STEP the blast retires and
    clears all four of its flags instead of placing sprites."""
    _case(ENTRY_BOMB_BLAST_STEP, {"_pokes": _blast_pokes(step=step)},
          lambda lib, buf: lib.g_bomb_blast_step(buf, 0), note=f"step={step}")


@pytest.mark.parametrize("x,y", ((0, 0), (0x140, 0xc8), (0x7ffc, 0x7ffc), (0x8000, 0x8000)))
def test_blast_step_offsets_are_signed_bytes_added_as_words(x, y):
    """`ext.w` on each table byte, then a word add that wraps — the sign is the table's, not the
    coordinate's."""
    _case(ENTRY_BOMB_BLAST_STEP, {"_pokes": _blast_pokes(step=3, x=x, y=y)},
          lambda lib, buf: lib.g_bomb_blast_step(buf, 0), note=f"({x:#x},{y:#x})")


@pytest.mark.parametrize("high_word", (0x0000, 0x0001, 0xffff))
def test_blast_step_indexes_the_table_with_the_WHOLE_of_d0(high_word):
    """`move.w $176ec,d0 / lsl.w #3,d0 / adda.l d0,a0` — the ADD IS LONG and the routine never
    writes d0's high word, so the offset row it reads depends on what its caller left there.

    Every call site in the game reaches it through the frame loop, which the harness does not model,
    so the C takes the high word to be zero and this case is what says so out loud: if the oracle
    diverges here, the reconstruction has a register input it is not taking.
    """
    scratch = (high_word << 16) | 0x1234
    _case(ENTRY_BOMB_BLAST_STEP, {"d0": scratch, "_pokes": _blast_pokes(step=3)},
          lambda lib, buf: lib.g_bomb_blast_step(buf, scratch), note=f"d0 high={high_word:#x}")


def test_blast_step_does_nothing_while_the_bomb_is_not_exploding():
    _case(ENTRY_BOMB_BLAST_STEP, {"_pokes": _blast_pokes(exploding=0, step=3)},
          lambda lib, buf: lib.g_bomb_blast_step(buf, 0), note="not exploding")


@pytest.mark.parametrize("exploding", (0, 1))
def test_blast_publish_four_records(exploding):
    pokes = _blast_pokes(exploding=exploding)
    pokes[A_blast_state] = word(0x80) + word(0x60) + bytes().join(
        word(0x100 + n) + word(0x200 + n) for n in range(BLAST_POINTS_COUNT))
    pokes[A_dl_blast] = bytes().join(display_record(x=0x11, y=0x22, frame=0x33, active=0x44)
                                     for _ in range(BLAST_POINTS_COUNT))
    _case(ENTRY_BOMB_BLAST_PUBLISH, {"_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_publish(buf), poison=True,
          note=f"exploding={exploding}")


# ==================================================================================================
# The player's bullets @ 0x140cc, 0x140ea, 0x14118, 0x14148, 0x141b4, 0x141e4
# ==================================================================================================
def _shot_table(shot=0):
    return A_player_shot_slot_0 + shot * PLAYER_SHOT_TABLE_STRIDE


@pytest.mark.parametrize("state", (PLAYER_BULLET_FREE, PLAYER_BULLET_IN_FLIGHT, PLAYER_BULLET_HIT))
@pytest.mark.parametrize("y", (0, 1, PLAYER_BULLET_DY, PLAYER_BULLET_DY - 8, 0x10, 0xff8f, 0x8000))
def test_player_bullet_step(state, y):
    """x += dx and y -= 19 as WORD arithmetic, and the retire test is `> -8` and not `>= -8`.

    THE FREE STATE IS STEPPED TOO — only PLAYER_BULLET_HIT short-circuits — so a free slot's dead
    coordinates drift, which is what the y sweep here is really pinning."""
    records = [bullet_record(x=0x40 + 7 * n, y=y, dx=(-3 + n), state=state)
               for n in range(PLAYER_SHOT_BULLETS)]
    _case(ENTRY_PLAYER_BULLETS_MOVE_GROUP,
          {"a0": _shot_table(), "_pokes": shot_pokes(0, records)},
          lambda lib, buf: lib.g_player_bullets_move_group(buf, _shot_table()),
          note=f"state={state} y={y:#x}")


@pytest.mark.parametrize("chunk", range(4))
def test_player_bullet_step_fuzz(chunk):
    rng = random.Random(0xb01 + chunk)
    for _ in range(24):
        records = [bullet_record(x=rng.randrange(0x10000), y=rng.randrange(0x10000),
                                 dx=rng.randrange(0x10000), state=rng.randrange(4))
                   for _ in range(PLAYER_SHOT_BULLETS)]
        _case(ENTRY_PLAYER_BULLETS_MOVE_GROUP,
              {"a0": _shot_table(), "_pokes": shot_pokes(0, records)},
              lambda lib, buf: lib.g_player_bullets_move_group(buf, _shot_table()),
              note=f"chunk={chunk}")


def test_player_bullets_move_all_walks_the_three_shots():
    pokes = {}
    for shot in range(PLAYER_SHOT_SLOTS):
        pokes.update(shot_pokes(shot, [bullet_record(x=0x30 * shot + 9 * n, y=0x50 + n,
                                                     dx=n - 2, state=1 + (n & 1))
                                       for n in range(PLAYER_SHOT_BULLETS)]))
    _case(ENTRY_PLAYER_BULLETS_MOVE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_bullets_move_all(buf), note="three shots")


@pytest.mark.parametrize("alt_glyph", (0, 1))
@pytest.mark.parametrize("state", (PLAYER_BULLET_FREE, PLAYER_BULLET_IN_FLIGHT, PLAYER_BULLET_HIT,
                                   3, 0xffff))
def test_player_bullet_publish_states(state, alt_glyph):
    """Free clears the record, hit draws the impact glyph AND frees the slot, and anything else is
    an ordinary bullet whose glyph the "GCC" cheat flag swaps."""
    records = [bullet_record(x=0x60 + n, y=0x70 + n, dx=n, state=state)
               for n in range(PLAYER_SHOT_BULLETS)]
    pokes = shot_pokes(0, records)
    pokes[A_alt_bullet_glyph_flag] = bytes([alt_glyph])
    pokes[A_dl_player_bullets_0] = bytes().join(
        display_record(x=0xaa, y=0xbb, frame=0xcc, active=0xdd)
        for _ in range(PLAYER_SHOT_BULLETS))
    _case(ENTRY_PLAYER_BULLETS_PUBLISH_GROUP,
          {"a0": _shot_table(), "a1": A_dl_player_bullets_0,
           "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullets_publish_group(buf, _shot_table(),
                                                              A_dl_player_bullets_0),
          poison=True, note=f"state={state} alt={alt_glyph}")


def test_player_bullets_publish_all_walks_the_three_runs():
    pokes = {}
    for shot in range(PLAYER_SHOT_SLOTS):
        pokes.update(shot_pokes(shot, [bullet_record(x=0x100 * shot + n, y=0x20 + n,
                                                     state=n % 3)
                                       for n in range(PLAYER_SHOT_BULLETS)]))
    _case(ENTRY_PLAYER_BULLETS_PUBLISH_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_bullets_publish_all(buf), note="three runs")


@pytest.mark.parametrize("busy_index", (-1, 0, 1, 2, 3, 4))
def test_player_shot_slot_release_needs_every_bullet_free(busy_index):
    """One live bullet anywhere in the five keeps the shot busy; only all five free clears it."""
    records = [bullet_record(state=PLAYER_BULLET_FREE) for _ in range(PLAYER_SHOT_BULLETS)]
    if busy_index >= 0:
        records[busy_index] = bullet_record(state=PLAYER_BULLET_IN_FLIGHT)
    pokes = shot_pokes(0, records)
    pokes[A_shot_slot_busy_0] = word(0xffff)
    _case(ENTRY_PLAYER_SHOT_SLOT_RELEASE_IF_EMPTY,
          {"a0": _shot_table(), "a4": A_shot_slot_busy_0, "_pokes": pokes},
          lambda lib, buf: lib.g_player_shot_slot_release_if_empty(buf, _shot_table(),
                                                                   A_shot_slot_busy_0),
          poison=True, note=f"busy_index={busy_index}")


def test_player_shot_slots_release_walks_the_three_flags():
    pokes = {}
    for shot in range(PLAYER_SHOT_SLOTS):
        records = [bullet_record(state=PLAYER_BULLET_FREE) for _ in range(PLAYER_SHOT_BULLETS)]
        if shot == 1:
            records[2] = bullet_record(state=PLAYER_BULLET_HIT)
        pokes.update(shot_pokes(shot, records))
        pokes[A_shot_slot_busy_0 + shot * SHOT_SLOT_BUSY_BYTES] = word(1)
    _case(ENTRY_PLAYER_SHOT_SLOTS_RELEASE, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_shot_slots_release(buf), note="three flags")


# ==================================================================================================
# The two collision passes and the twenty-three hit handlers
# ==================================================================================================
HIT_FRAME = 0x40           # the sprite-bank record every collision case measures its entity by
HIT_GROUP = A_entity_group_a0


def _collision_pokes(kind, entities, hit_box=(0, 0, 0, 0, 0x20, 0x20), item_kind=0, firing_hp=0,
                     count_minus_1=None):
    """One descriptor in scratch, its group filled, and one sprite record for the hit box.

    `hit_box` is (draw_dx, draw_dy, hit_dx, hit_dy, hit_w, hit_h) — SIX numbers because the blast's
    box and the bullet's read the record differently, and the difference is only visible when the
    two corner pairs disagree: the bullet spans [+8, +16] and [+10, +18] while the blast's near
    corner is +12 - +8 and its width is +16 minus THAT. A case with hit_dx == draw_dx makes the
    subtraction invisible, which is how a mutation of it survived until this parameter existed.
    """
    draw_dx, draw_dy, hit_dx, hit_dy, hit_w, hit_h = hit_box
    slots = ENTITY_GROUP_A_SLOTS if count_minus_1 is None else count_minus_1 + 1
    pokes = {SCRATCH_DESC: descriptor(group=HIT_GROUP, kind=kind, item_kind=item_kind,
                                      firing_hp=firing_hp,
                                      count_minus_1=(slots - 1), base_frame=0)}
    pokes.update(group_pokes(HIT_GROUP, entities, count=ENTITY_GROUP_A_SLOTS))
    pokes.update(sprite_bank_pokes(HIT_FRAME, draw_dx=draw_dx, draw_dy=draw_dy,
                                   hit_dx=hit_dx, hit_dy=hit_dy, hit_w=hit_w, hit_h=hit_h))
    return pokes


def _hit_entity(x=0x40, y=0x40, **fields):
    fields.setdefault("active", 1)
    fields.setdefault("frame_offset", HIT_FRAME)
    return entity_record(x=x, y=y, **fields)


@pytest.mark.parametrize("kind", range(HIT_HANDLER_ENTRIES))
@pytest.mark.parametrize("hit_points", (0, 1, 2, 4, 5, 6, 7, ENEMY_INDESTRUCTIBLE, 0xffff))
def test_every_bullet_hit_handler_over_every_hit_point_edge(kind, hit_points):
    """Nineteen table entries x nine hit-point values: every handler, every kill boundary, and the
    score each awards — which is what makes the X flag the handlers thread observable at all."""
    entities = [_hit_entity(hit_points=hit_points, firing=(kind & 1), depth_select=(kind & 2) >> 1,
                            hidden=0)]
    pokes = _collision_pokes(kind, entities, firing_hp=3)
    pokes.update(shot_pokes(0, [bullet_record(x=0x40, y=0x40, state=PLAYER_BULLET_IN_FLIGHT)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note=f"kind={kind} hp={hit_points:#x}")


@pytest.mark.parametrize("kind", range(HIT_HANDLER_ENTRIES))
@pytest.mark.parametrize("hit_points", (0, 1, 4, 5, 6, 7, ENEMY_INDESTRUCTIBLE, 0xffff))
def test_every_blast_hit_handler_over_every_hit_point_edge(kind, hit_points):
    """The same sweep through the blast's table, whose damage handlers subtract 4, 5 and 6."""
    entities = [_hit_entity(hit_points=hit_points, firing=(kind & 1), depth_select=(kind & 2) >> 1)]
    pokes = _collision_pokes(kind, entities, firing_hp=3)
    pokes[SCRATCH_BLAST] = (word(0) + word(0)
                            + bytes().join(word(0x48) + word(0x48)
                                           for _ in range(BLAST_POINTS_COUNT)))
    _case(ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS,
          {"a1": SCRATCH_BLAST, "a5": SCRATCH_DESC, "d7": BLAST_POINTS_COUNT - 1,
           "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_vs_entity_groups(buf, SCRATCH_BLAST, SCRATCH_DESC),
          note=f"kind={kind} hp={hit_points:#x}")


@pytest.mark.parametrize("kind", (1, 2, 3))
@pytest.mark.parametrize("item_kind", (0, 1, 2, 3))
@pytest.mark.parametrize("cleared", (True, False))
def test_the_drop_item_handlers_over_every_item_kind(kind, item_kind, cleared):
    """The six handlers that call `item_drop_if_formation_cleared`, over the three items it can
    drop and the one arm that also awards 1000 — the seam src/weapons.c completes."""
    entities = [_hit_entity(hit_points=8)]
    if not cleared:
        entities += [entity_record(active=1, dying=0)]
    pokes = _collision_pokes(kind, entities, item_kind=item_kind)
    pokes.update(shot_pokes(0, [bullet_record(x=0x40, y=0x40, state=PLAYER_BULLET_IN_FLIGHT)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note=f"kind={kind} item={item_kind} cleared={cleared}")


@pytest.mark.parametrize("drop_y", (0, 0xffee, 0xffef, 0xfff0, 0x7fff))
def test_the_drop_position_is_a_word_add_whose_carry_reaches_the_score(drop_y):
    """`addi.w #$11,d1` is the LAST instruction to touch X before the award, so a kill at a y that
    carries adds one more point than a kill that does not. This is the case that pins that."""
    pokes = _collision_pokes(1, [_hit_entity(y=drop_y, hit_points=8)], item_kind=1,
                             hit_box=(0, -0x40, 0, -0x40, 0x20, 0x7fff))
    pokes.update(shot_pokes(0, [bullet_record(x=0x40, y=drop_y, state=PLAYER_BULLET_IN_FLIGHT)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note=f"drop_y={drop_y:#x}")


@pytest.mark.parametrize("bullet_x,bullet_y", tuple(
    (x, y) for x in (0x1f, 0x20, 0x21, 0x3a, 0x3b, 0x3c) for y in (0x1f, 0x20, 0x3b, 0x3c)))
def test_the_bullet_box_edges(bullet_x, bullet_y):
    """The bullet is a POINT five pixels inside its record, and the entity box runs from
    record[+8] to record[+16] INCLUSIVE on both axes (`blt`/`bgt`, not `ble`/`bge`)."""
    pokes = _collision_pokes(5, [_hit_entity(x=0x20, y=0x20)],
                             hit_box=(0, 0, 0, 0, 0x1a, 0x1a))
    pokes.update(shot_pokes(0, [bullet_record(x=bullet_x, y=bullet_y,
                                              state=PLAYER_BULLET_IN_FLIGHT)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note=f"bullet=({bullet_x:#x},{bullet_y:#x})")


@pytest.mark.parametrize("blast_x", (0x00, 0x10, 0x1f, 0x20, 0x21, 0x40, 0x50, 0x60))
@pytest.mark.parametrize("blast_y", (0x00, 0x1f, 0x20, 0x22, 0x25, 0x28, 0x40, 0x5e, 0x60))
def test_the_blast_box_edges(blast_x, blast_y):
    """A blast point is a BLAST_HIT_BOX square, and its overlap with the entity's box is the
    two-armed `bgt` pair — the arm taken depends on which box starts first."""
    pokes = _collision_pokes(5, [_hit_entity(x=0x20, y=0x20)], hit_box=(2, 3, 9, 0xd, 0x1a, 0x1c))
    pokes[SCRATCH_BLAST] = (word(0) + word(0)
                            + bytes().join(word(blast_x) + word(blast_y)
                                           for _ in range(BLAST_POINTS_COUNT)))
    _case(ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS,
          {"a1": SCRATCH_BLAST, "a5": SCRATCH_DESC, "d7": BLAST_POINTS_COUNT - 1,
           "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_vs_entity_groups(buf, SCRATCH_BLAST, SCRATCH_DESC),
          note=f"blast=({blast_x:#x},{blast_y:#x})")


@pytest.mark.parametrize("active,dying,hidden", tuple(
    (a, d, h) for a in (0, 1) for d in (0, 1) for h in (0, 1)))
def test_a_collision_skips_a_slot_that_is_not_live(active, dying, hidden):
    """Inactive and dying are the walk's own gates; hidden is one HANDLER's, so a hidden entity is
    still dispatched to and only the handlers that test +48 refuse it."""
    pokes = _collision_pokes(4, [_hit_entity(active=active, dying=dying, hidden=hidden,
                                             hit_points=8)])
    pokes.update(shot_pokes(0, [bullet_record(x=0x40, y=0x40, state=PLAYER_BULLET_IN_FLIGHT)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note=f"active={active} dying={dying} hidden={hidden}")


def test_one_bullet_stops_at_the_first_entity_it_hits():
    """The `dbf d7` after the handler takes the pass to the next BULLET, so four stacked entities
    take one hit between them and not four."""
    pokes = _collision_pokes(0, [_hit_entity(x=0x40, y=0x40) for _ in range(4)])
    pokes.update(shot_pokes(0, [bullet_record(x=0x40, y=0x40, state=PLAYER_BULLET_IN_FLIGHT)
                                for _ in range(PLAYER_SHOT_BULLETS)]))
    _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
          {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(), SCRATCH_DESC),
          note="four stacked")


def test_one_blast_point_does_not_stop_the_group_walk():
    """...and the blast is the other way round: its handler returns into the ENTITY loop, so one
    point can hit every entity of a group in one call."""
    pokes = _collision_pokes(0, [_hit_entity(x=0x40, y=0x40) for _ in range(4)])
    pokes[SCRATCH_BLAST] = (word(0) + word(0)
                            + bytes().join(word(0x48) + word(0x48)
                                           for _ in range(BLAST_POINTS_COUNT)))
    _case(ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS,
          {"a1": SCRATCH_BLAST, "a5": SCRATCH_DESC, "d7": BLAST_POINTS_COUNT - 1,
           "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_vs_entity_groups(buf, SCRATCH_BLAST, SCRATCH_DESC),
          note="four stacked")


@pytest.mark.parametrize("chunk", range(6))
def test_collision_box_fuzz(chunk):
    """Random entity positions, random hit boxes and random bullet positions.

    OVER A HANDLER THAT WRITES (table entry 0, the plain 200-point kill), and it has to be: driven
    over the immune entry the fuzz produced no store at all, so a mis-computed box was invisible and
    a mutation of the near-corner arithmetic survived every one of these cases.
    """
    rng = random.Random(0xc011 + chunk)
    for _ in range(20):
        box = (rng.randrange(-0x40, 0x40), rng.randrange(-0x40, 0x40),
               rng.randrange(-0x40, 0x40), rng.randrange(-0x40, 0x40),
               rng.randrange(-0x40, 0x80), rng.randrange(-0x40, 0x80))
        pokes = _collision_pokes(0, [_hit_entity(x=rng.randrange(-0x80, 0x200),
                                                  y=rng.randrange(-0x80, 0x100))
                                      for _ in range(3)], hit_box=box)
        pokes.update(shot_pokes(0, [bullet_record(x=rng.randrange(-0x80, 0x200),
                                                  y=rng.randrange(-0x80, 0x100),
                                                  state=PLAYER_BULLET_IN_FLIGHT)
                                    for _ in range(PLAYER_SHOT_BULLETS)]))
        _case(ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS,
              {"a0": _shot_table(), "a5": SCRATCH_DESC, "_pokes": pokes},
              lambda lib, buf: lib.g_player_bullet_vs_entity_groups(buf, _shot_table(),
                                                                    SCRATCH_DESC),
              note=f"chunk={chunk} box={box}")


@pytest.mark.parametrize("chunk", range(6))
def test_blast_box_fuzz(chunk):
    rng = random.Random(0xb1a5 + chunk)
    for _ in range(20):
        box = (rng.randrange(-0x40, 0x40), rng.randrange(-0x40, 0x40),
               rng.randrange(-0x40, 0x40), rng.randrange(-0x40, 0x40),
               rng.randrange(-0x40, 0x80), rng.randrange(-0x40, 0x80))
        pokes = _collision_pokes(0, [_hit_entity(x=rng.randrange(-0x80, 0x200),
                                                  y=rng.randrange(-0x80, 0x100))
                                      for _ in range(3)], hit_box=box)
        pokes[SCRATCH_BLAST] = (word(0) + word(0) + bytes().join(
            word(rng.randrange(-0x80, 0x200)) + word(rng.randrange(-0x80, 0x100))
            for _ in range(BLAST_POINTS_COUNT)))
        _case(ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS,
              {"a1": SCRATCH_BLAST, "a5": SCRATCH_DESC, "d7": BLAST_POINTS_COUNT - 1,
           "_pokes": pokes},
              lambda lib, buf: lib.g_bomb_blast_vs_entity_groups(buf, SCRATCH_BLAST, SCRATCH_DESC),
              note=f"chunk={chunk} box={box}")


@pytest.mark.parametrize("exploding", (0, 1))
def test_the_blast_guard_gates_the_whole_group_pass(exploding):
    pokes = _collision_pokes(0, [_hit_entity(x=0x40, y=0x40)])
    pokes[A_bomb_exploding] = word(exploding)
    pokes[SCRATCH_BLAST] = (word(0) + word(0)
                            + bytes().join(word(0x48) + word(0x48)
                                           for _ in range(BLAST_POINTS_COUNT)))
    _case(ENTRY_BOMB_BLAST_VS_ENTITIES_IF_ACTIVE,
          {"a0": SCRATCH_BLAST, "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_vs_entities_if_active(buf, SCRATCH_BLAST, SCRATCH_DESC),
          note=f"exploding={exploding}")


def test_player_bullets_vs_entities_group_walks_all_twenty_two_descriptors(staged_world_pokes):
    """One shot against the whole descriptor list, over the world the original spawned."""
    pokes = dict(staged_world_pokes)
    pokes.update(shot_pokes(0, [bullet_record(x=0x50 + 0x18 * n, y=0x30 + 0x11 * n,
                                              state=PLAYER_BULLET_IN_FLIGHT)
                                for n in range(PLAYER_SHOT_BULLETS)]))
    _case(ENTRY_PLAYER_BULLETS_VS_ENTITIES_GROUP,
          {"a0": _shot_table(), "_pokes": pokes},
          lambda lib, buf: lib.g_player_bullets_vs_entities_group(buf, _shot_table()),
          note="staged world")


def test_the_two_whole_frame_collision_passes(staged_world_pokes):
    """The frame loop's own two calls, over the staged world: three shots x 22 groups, and the
    blast's four points x 22 groups."""
    pokes = dict(staged_world_pokes)
    for shot in range(PLAYER_SHOT_SLOTS):
        pokes.update(shot_pokes(shot, [bullet_record(x=0x30 + 0x21 * n + 0x40 * shot,
                                                     y=0x20 + 0x13 * n,
                                                     state=PLAYER_BULLET_IN_FLIGHT)
                                       for n in range(PLAYER_SHOT_BULLETS)]))
    _case(ENTRY_PLAYER_BULLETS_VS_ENTITIES, {"_pokes": pokes},
          lambda lib, buf: lib.g_player_bullets_vs_entities(buf), note="bullets, staged world")

    pokes = dict(staged_world_pokes)
    pokes[A_bomb_exploding] = word(1)
    pokes[A_blast_state] = word(0x80) + word(0x60) + bytes().join(
        word(0x40 + 0x30 * n) + word(0x30 + 0x20 * n) for n in range(BLAST_POINTS_COUNT))
    _case(ENTRY_BOMB_BLAST_VS_ENTITIES, {"_pokes": pokes},
          lambda lib, buf: lib.g_bomb_blast_vs_entities(buf), note="blast, staged world")


# ==================================================================================================
# The muzzle flash @ 0x1227c, 0x122c0, 0x12348
# ==================================================================================================
MUZZLE_GROUP = A_entity_group_bigobj


def _muzzle_pokes(entities, **desc_fields):
    desc_fields.setdefault("flash_dx", 7)
    desc_fields.setdefault("flash_dy", -5)
    desc_fields.setdefault("flash2_dx", 0x11)
    desc_fields.setdefault("flash2_dy", 0x13)
    pokes = {SCRATCH_DESC: descriptor(group=MUZZLE_GROUP, **desc_fields),
             A_anim_frame_a: bytes([0x91])}
    pokes.update(group_pokes(MUZZLE_GROUP, entities))
    pokes[A_dl_muzzle_pair_0] = bytes().join(
        display_record(x=0x55, y=0x66, frame=0x77, active=0x88)
        for _ in range(2 * ENTITY_GROUP_SLOTS))
    return pokes


@pytest.mark.parametrize("active,dying,firing", tuple(
    (a, d, f) for a in (0, 1) for d in (0, 1) for f in (0, 1)))
def test_muzzle_flash_pair_is_gated_on_three_fields(active, dying, firing):
    entity = entity_record(x=0x60, y=0x50, active=active, dying=dying, firing=firing)
    _case(ENTRY_MUZZLE_FLASH_PUBLISH_PAIR,
          {"a5": SCRATCH_DESC, "a1": A_dl_muzzle_pair_0, "_pokes": _muzzle_pokes([entity])},
          lambda lib, buf: lib.g_muzzle_flash_publish_pair(buf, SCRATCH_DESC, A_dl_muzzle_pair_0),
          poison=True, note=f"active={active} dying={dying} firing={firing}")


@pytest.mark.parametrize("x,y", ((0, 0), (0x7ff8, 0x7ff8), (0xfff0, 0xfff0), (0x140, 0xc8)))
def test_muzzle_flash_pair_offsets_are_word_adds(x, y):
    """The second sprite is the FIRST plus the descriptor's +32/+34, not the entity plus them."""
    entity = entity_record(x=x, y=y, active=1, firing=1)
    _case(ENTRY_MUZZLE_FLASH_PUBLISH_PAIR,
          {"a5": SCRATCH_DESC, "a1": A_dl_muzzle_pair_0, "_pokes": _muzzle_pokes([entity])},
          lambda lib, buf: lib.g_muzzle_flash_publish_pair(buf, SCRATCH_DESC, A_dl_muzzle_pair_0),
          note=f"({x:#x},{y:#x})")


@pytest.mark.parametrize("frame_offset", (0, 1, 0xffff))
def test_muzzle_flash_group_frame_offset_picks_the_look(frame_offset):
    """Frame offset zero takes the bumped glyph and no drop; anything else the plain glyph six rows
    down — the `subi.w #$6` / `addi.w #$6` pair the original spells as one branch writing zero."""
    entities = [entity_record(x=0x40 + 0x20 * n, y=0x50, active=1, firing=1,
                              frame_offset=frame_offset)
                for n in range(ENTITY_GROUP_SLOTS)]
    pokes = _muzzle_pokes(entities)
    pokes[A_dl_muzzle_group] = bytes().join(
        display_record(x=0x12, y=0x34, frame=0x56, active=0x78)
        for _ in range(2 * ENTITY_GROUP_SLOTS))
    _case(ENTRY_MUZZLE_FLASH_PUBLISH_GROUP,
          {"a5": SCRATCH_DESC, "a1": A_dl_muzzle_group, "d7": ENTITY_GROUP_SLOTS - 1,
           "_pokes": pokes},
          lambda lib, buf: lib.g_muzzle_flash_publish_group(buf, SCRATCH_DESC, A_dl_muzzle_group,
                                                            ENTITY_GROUP_SLOTS - 1),
          poison=True, note=f"frame_offset={frame_offset:#x}")


def test_muzzle_flash_publish_all_over_the_staged_world(staged_world_pokes):
    pokes = dict(staged_world_pokes)
    pokes[A_anim_frame_a] = bytes([0x91])
    _case(ENTRY_MUZZLE_FLASH_PUBLISH_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_muzzle_flash_publish_all(buf), note="staged world")


def test_muzzle_flash_publish_all_with_every_group_firing(staged_world_pokes):
    """The staged world's entities are not firing, so the interesting arm needs the flag set: this
    turns ENTITY_FIRING on in every slot of the four groups the routine walks."""
    pokes = dict(staged_world_pokes)
    pokes[A_anim_frame_a] = bytes([0x91])
    image = bytearray(harness.BASE_IMAGE)
    for address, blob in staged_world_pokes.items():
        image[address:address + len(blob)] = blob
    for group, count in ((A_entity_group_a4, ENTITY_GROUP_SLOTS),
                         (0x19416, 3)):
        for index in range(count):
            slot = int.from_bytes(image[group + 4 * index:group + 4 * index + 4], "big")
            record = bytearray(image[slot:slot + ENTITY_STRIDE])
            record[ENTITY_ACTIVE:ENTITY_ACTIVE + 2] = word(1)
            record[ENTITY_DYING:ENTITY_DYING + 2] = word(0)
            record[ENTITY_FIRING:ENTITY_FIRING + 2] = word(1)
            record[ENTITY_X:ENTITY_X + 2] = word(0x50 + 0x10 * index)
            record[ENTITY_Y:ENTITY_Y + 2] = word(0x40 + 8 * index)
            pokes[slot] = bytes(record)
    _case(ENTRY_MUZZLE_FLASH_PUBLISH_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_muzzle_flash_publish_all(buf), note="every group firing")


# ==================================================================================================
# The enemy bullets @ 0x125bc, 0x128ce, 0x12964
# ==================================================================================================
def _aim_pokes(desc_fields=None, records=None):
    pokes = {SCRATCH_DESC: descriptor(**(desc_fields or {"muzzle_dx": 3, "muzzle_dy": -4}))}
    pokes[A_enemy_bullets] = enemy_bullet_array(records if records is not None else [])
    return pokes


@pytest.mark.parametrize("free_slot", (0, 1, 4, None))
def test_enemy_bullet_spawn_takes_the_first_free_slot(free_slot):
    """...and does nothing at all when the walk reaches the array's own 999 first."""
    live = enemy_bullet_record(x=1, y=2, dx=3, dy=4, active=ENEMY_BULLET_LIVE)
    count = 5
    records = [live] * count
    if free_slot is not None:
        records[free_slot] = enemy_bullet_record(active=0)
    _case(ENTRY_ENEMY_BULLET_SPAWN_AIMED,
          {"a5": SCRATCH_DESC, "a6": A_enemy_bullets, "d2": 0x80, "d3": 0x60,
           "d4": 0xa0, "d5": 0x40, "_pokes": _aim_pokes(records=records)},
          lambda lib, buf: lib.g_enemy_bullet_spawn_aimed(buf, SCRATCH_DESC, A_enemy_bullets,
                                                          0x80, 0x60, 0xa0, 0x40),
          note=f"free_slot={free_slot}")


@pytest.mark.parametrize("busy", (0, 1, 0xff))
def test_enemy_bullet_spawn_skips_the_effect_while_the_module_is_busy(busy):
    """The one site in the game that reads the module's own busy byte before triggering."""
    pokes = _aim_pokes()
    pokes[A_sound_module + SND_SFX_ACTIVE] = bytes([busy])
    _case(ENTRY_ENEMY_BULLET_SPAWN_AIMED,
          {"a5": SCRATCH_DESC, "a6": A_enemy_bullets, "d2": 0x80, "d3": 0x60,
           "d4": 0x90, "d5": 0x50, "_pokes": pokes},
          lambda lib, buf: lib.g_enemy_bullet_spawn_aimed(buf, SCRATCH_DESC, A_enemy_bullets,
                                                          0x80, 0x60, 0x90, 0x50),
          note=f"busy={busy}")


@pytest.mark.parametrize("chunk", range(8))
def test_enemy_bullet_spawn_aim_arithmetic_fuzz(chunk):
    """The direction is `((y - aim_y) >> 5) * 21 + ((x - aim_x) >> 5)` — an ARITHMETIC shift, so the
    sign of a negative difference survives it, and a word product that indexes the grid backwards.

    The sweep is bounded to the window the four firing groups guard (`ENEMY_FIRE_X_MAX` and its
    siblings) widened by a screen on every side: an unbounded one would index the lookup outside
    the program, which `make guarded` faults on rather than reading as data.
    """
    rng = random.Random(0xa1 + chunk)
    for _ in range(24):
        aim_x, aim_y = rng.randrange(0, 0x140), rng.randrange(0, 0xc8)
        x, y = rng.randrange(-0x40, 0x180), rng.randrange(-0x40, 0x100)
        pokes = _aim_pokes({"muzzle_dx": rng.randrange(-0x20, 0x20),
                            "muzzle_dy": rng.randrange(-0x20, 0x20)})
        _case(ENTRY_ENEMY_BULLET_SPAWN_AIMED,
              {"a5": SCRATCH_DESC, "a6": A_enemy_bullets, "d2": aim_x & 0xffff,
               "d3": aim_y & 0xffff, "d4": x & 0xffff, "d5": y & 0xffff, "_pokes": pokes},
              lambda lib, buf: lib.g_enemy_bullet_spawn_aimed(buf, SCRATCH_DESC, A_enemy_bullets,
                                                              aim_x & 0xffff, aim_y & 0xffff,
                                                              x & 0xffff, y & 0xffff),
              note=f"chunk={chunk} aim=({aim_x},{aim_y}) at=({x},{y})")


@pytest.mark.parametrize("x,y", ((0, 0), (ENEMY_BULLET_CLIP_LEFT, 0x40), (0xffd9, 0x40),
                                 (0x166, 0x40), (0x167, 0x40), (0x40, 0xec), (0x40, 0xed),
                                 (0x40, 0xffda), (0x40, 0xffd9)))
def test_enemy_bullets_move_clip_edges(x, y):
    """The clip box is tested AFTER the step, and every edge is inclusive on the inside."""
    records = [enemy_bullet_record(x=x, y=y, dx=0, dy=0, active=ENEMY_BULLET_LIVE),
               enemy_bullet_record(x=0x40, y=0x40, dx=3, dy=-2, active=ENEMY_BULLET_LIVE),
               enemy_bullet_record(x=0x50, y=0x50, dx=1, dy=1, active=0)]
    _case(ENTRY_ENEMY_BULLETS_MOVE,
          {"_pokes": {A_enemy_bullets: enemy_bullet_array(records)}},
          lambda lib, buf: lib.g_enemy_bullets_move(buf), poison=True,
          note=f"({x:#x},{y:#x})")


@pytest.mark.parametrize("chunk", range(4))
def test_enemy_bullets_move_fuzz(chunk):
    rng = random.Random(0xeb + chunk)
    for _ in range(20):
        records = [enemy_bullet_record(x=rng.randrange(0x10000), y=rng.randrange(0x10000),
                                       dx=rng.randrange(0x10000), dy=rng.randrange(0x10000),
                                       active=rng.choice((0, 1, 2)))
                   for _ in range(8)]
        _case(ENTRY_ENEMY_BULLETS_MOVE,
              {"_pokes": {A_enemy_bullets: enemy_bullet_array(records)}},
              lambda lib, buf: lib.g_enemy_bullets_move(buf), note=f"chunk={chunk}")


@pytest.mark.parametrize("live", (0, 1, 3, 12))
def test_enemy_bullets_publish_stops_at_the_sentinel(live):
    records = [enemy_bullet_record(x=0x30 + n, y=0x40 + n,
                                   active=(ENEMY_BULLET_LIVE if n % 2 else 0))
               for n in range(live)]
    pokes = {A_enemy_bullets: enemy_bullet_array(records),
             A_dl_enemy_bullets: bytes().join(
                 display_record(x=0xa, y=0xb, frame=0xc, active=0xd) for _ in range(live + 2))}
    _case(ENTRY_ENEMY_BULLETS_PUBLISH, {"_pokes": pokes},
          lambda lib, buf: lib.g_enemy_bullets_publish(buf), poison=True, note=f"live={live}")


# ==================================================================================================
# enemies_fire_all @ 0x12602 and its four groups
# ==================================================================================================
@pytest.mark.parametrize("player_hit", (0, 1, 0xffff))
def test_enemies_fire_aborts_when_the_player_has_been_hit(player_hit, staged_world_pokes):
    """`enemies_fire_abort_if_player_hit` @ 0x12856 is not the nop its old name claimed: it drops
    its own return address so that a non-zero `player_hit` returns out of `enemies_fire_all`
    before anything fires."""
    pokes = dict(staged_world_pokes)
    pokes[A_player_hit] = word(player_hit)
    pokes[A_player] = word(0x80) + word(0x90)
    _case(ENTRY_ENEMIES_FIRE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_enemies_fire_all(buf), note=f"player_hit={player_hit}")


@pytest.mark.parametrize("countdown", (0, 1, 2, 0xffff))
def test_enemies_fire_over_the_staged_world(countdown, staged_world_pokes):
    """Every group, over the world the original spawned, at the four reload boundaries — the frame
    a countdown REACHES zero is the one that fires, and a countdown already at zero fires at once."""
    pokes = dict(staged_world_pokes)
    pokes[A_player_hit] = word(0)
    pokes[A_player] = word(0x80) + word(0x60)
    image = bytearray(harness.BASE_IMAGE)
    for address, blob in staged_world_pokes.items():
        image[address:address + len(blob)] = blob
    for slot in range(ENTITY_SLOTS):
        base = A_entity_arena + slot * ENTITY_STRIDE
        record = bytearray(image[base:base + ENTITY_STRIDE])
        record[ENTITY_FIRE_COUNTDOWN:ENTITY_FIRE_COUNTDOWN + 2] = word(countdown)
        record[ENTITY_FIRE_RELOAD:ENTITY_FIRE_RELOAD + 2] = word(8)
        pokes[base] = bytes(record)
    _case(ENTRY_ENEMIES_FIRE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_enemies_fire_all(buf), note=f"countdown={countdown}")


@pytest.mark.parametrize("x,y", ((-1, 0x40), (0, 0x40), (0x13f, 0x40), (0x140, 0x40),
                                 (0x40, -1), (0x40, 0), (0x40, 0xa8), (0x40, 0xa9),
                                 (0x40, -0x10), (0x40, -0x11)))
def test_the_firing_window_edges(x, y, staged_world_pokes):
    """Every group but B refuses an entity above row 0; B lets one down to -16 fire. Driving the
    whole pass over one position at a time is what separates the two windows."""
    pokes = dict(staged_world_pokes)
    pokes[A_player_hit] = word(0)
    pokes[A_player] = word(0x80) + word(0x60)
    image = bytearray(harness.BASE_IMAGE)
    for address, blob in staged_world_pokes.items():
        image[address:address + len(blob)] = blob
    for slot in range(ENTITY_SLOTS):
        base = A_entity_arena + slot * ENTITY_STRIDE
        record = bytearray(image[base:base + ENTITY_STRIDE])
        record[ENTITY_X:ENTITY_X + 2] = word(x)
        record[ENTITY_Y:ENTITY_Y + 2] = word(y)
        record[ENTITY_ACTIVE:ENTITY_ACTIVE + 2] = word(1)
        record[ENTITY_DYING:ENTITY_DYING + 2] = word(0)
        record[ENTITY_FIRE_COUNTDOWN:ENTITY_FIRE_COUNTDOWN + 2] = word(0)
        record[ENTITY_FIRE_RELOAD:ENTITY_FIRE_RELOAD + 2] = word(5)
        pokes[base] = bytes(record)
    _case(ENTRY_ENEMIES_FIRE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_enemies_fire_all(buf), note=f"({x},{y})")


# ==================================================================================================
# The turrets @ 0x129b2, 0x12a34, 0x12a50, 0x12a60, 0x12b40, 0x12c04
# ==================================================================================================
@pytest.mark.parametrize("facing", tuple(range(TURRET_FACINGS)) + (TURRET_FACINGS, 0xffff))
@pytest.mark.parametrize("wanted", (0, 1, 5, 6, 7, 11, 0xfa, 0xff))
def test_turret_aim_step_rotates_one_step(facing, wanted):
    """Every facing against every desired bearing, INCLUDING the two that are already aimed: the
    byte difference is compared against +6 and -6, and only an exact match clears +24."""
    pokes = {abi.SCRATCH: entity_record(x=0x80, y=0x60, facing=facing, aim_changed=0xffff),
             A_player: word(0x80) + word(0x60),
             A_turret_facing_lut: bytes([wanted])}
    _case(ENTRY_TURRET_AIM_STEP, {"a0": abi.SCRATCH, "_pokes": pokes},
          lambda lib, buf: lib.g_turret_aim_step(buf, abi.SCRATCH), poison=True,
          note=f"facing={facing} wanted={wanted:#x}")


@pytest.mark.parametrize("chunk", range(6))
def test_turret_aim_step_lookup_fuzz(chunk):
    """The 23-column grid index over random relative positions, bounded to the playfield widened by
    a screen: `asr.w #5` on each axis, `muls.w #$17` on the row, and a signed `adda.w`."""
    rng = random.Random(0x7011 + chunk)
    for _ in range(24):
        player = (rng.randrange(0, 0x140), rng.randrange(0, 0xc8))
        turret = (rng.randrange(-0x40, 0x180), rng.randrange(-0x40, 0x100))
        pokes = {abi.SCRATCH: entity_record(x=turret[0], y=turret[1],
                                            facing=rng.randrange(TURRET_FACINGS)),
                 A_player: word(player[0]) + word(player[1])}
        _case(ENTRY_TURRET_AIM_STEP, {"a0": abi.SCRATCH, "_pokes": pokes},
              lambda lib, buf: lib.g_turret_aim_step(buf, abi.SCRATCH),
              note=f"chunk={chunk} player={player} turret={turret}")


@pytest.mark.parametrize("active,dying", ((0, 0), (1, 0), (1, 1), (0, 1)))
def test_the_two_aim_group_forms_differ_on_the_dead(active, dying):
    """The eight turret groups aim unconditionally; the five facing groups skip a dead slot."""
    group = A_entity_group_t0
    entities = [entity_record(x=0x40 + 0x20 * n, y=0x50, facing=n % TURRET_FACINGS,
                              active=active, dying=dying)
                for n in range(ENTITY_GROUP_SLOTS)]
    pokes = group_pokes(group, entities)
    pokes[A_player] = word(0x80) + word(0x60)
    _case(ENTRY_TURRETS_AIM_GROUP, {"a1": group, "_pokes": pokes},
          lambda lib, buf: lib.g_turrets_aim_group(buf, group),
          note=f"unconditional active={active} dying={dying}")
    _case(ENTRY_TURRETS_AIM_GROUP_ACTIVE, {"a1": group, "_pokes": pokes},
          lambda lib, buf: lib.g_turrets_aim_group_active(buf, group),
          note=f"active-only active={active} dying={dying}")


def test_turrets_aim_all_over_the_staged_world(staged_world_pokes):
    pokes = dict(staged_world_pokes)
    pokes[A_player] = word(0x90) + word(0x70)
    _case(ENTRY_TURRETS_AIM_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_turrets_aim_all(buf), note="staged world")


@pytest.mark.parametrize("state", (TURRET_STATE_AIMING, TURRET_STATE_HIT, 2, 0xffff))
@pytest.mark.parametrize("hidden", (0, 1))
def test_turret_publish_group_states(state, hidden):
    """Aiming draws the barrel from the facing table, hit draws the wreck from the other one, and
    anything else publishes NOTHING — the record keeps whatever the last frame left."""
    group, records = A_entity_group_t0, A_dl_turret_ptrs_t0
    entities = [entity_record(x=0x40 + 0x20 * n, y=0x50 + n, active=1, dying=0,
                              hidden=hidden, depth_select=state,
                              facing=n % TURRET_FACINGS, frame_offset=n)
                for n in range(ENTITY_GROUP_SLOTS)]
    pokes = group_pokes(group, entities)
    pokes[A_anim_frame_b] = bytes([0x63])
    for index in range(ENTITY_GROUP_SLOTS):
        pokes[table_pointer(records, index)] = display_record(x=0x1, y=0x2, frame=0x3, active=0x4)
    _case(ENTRY_TURRET_PUBLISH_GROUP,
          {"a0": group, "a3": records, "a4": A_turret_barrel_tbl_lo, "a6": A_turret_hit_tbl_lo,
           "_pokes": pokes},
          lambda lib, buf: lib.g_turret_publish_group(buf, group, records,
                                                      A_turret_barrel_tbl_lo,
                                                      A_turret_hit_tbl_lo),
          note=f"state={state:#x} hidden={hidden}")


@pytest.mark.parametrize("frame_offset", (0, 1, 2, 3))
@pytest.mark.parametrize("facing", tuple(range(TURRET_FACINGS)))
def test_the_barrel_offset_tables_are_indexed_by_frame_and_facing(frame_offset, facing):
    """0x18 bytes a body frame and two signed bytes a facing, over the game's OWN tables."""
    group, records = A_entity_group_t0, A_dl_turret_ptrs_t0
    entities = [entity_record(x=0x60, y=0x50, active=1, facing=facing,
                              frame_offset=frame_offset, depth_select=TURRET_STATE_AIMING)]
    pokes = group_pokes(group, entities)
    pokes[A_turret_barrel_base_frame] = bytes([0x00, 0x88])
    for index in range(ENTITY_GROUP_SLOTS):
        pokes[table_pointer(records, index)] = display_record()
    _case(ENTRY_TURRET_PUBLISH_GROUP,
          {"a0": group, "a3": records, "a4": A_turret_barrel_tbl_hi, "a6": A_turret_hit_tbl_hi,
           "_pokes": pokes},
          lambda lib, buf: lib.g_turret_publish_group(buf, group, records,
                                                      A_turret_barrel_tbl_hi,
                                                      A_turret_hit_tbl_hi),
          note=f"frame={frame_offset} facing={facing}")


def test_turrets_publish_all_over_the_staged_world(staged_world_pokes):
    pokes = dict(staged_world_pokes)
    pokes[A_anim_frame_b] = bytes([0x63])
    _case(ENTRY_TURRETS_PUBLISH_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_turrets_publish_all(buf), note="staged world")


# ==================================================================================================
# The spawn: the script step, the item, and the five common bodies
# ==================================================================================================
_SPAWN_SCRIPT_BASE = SCRATCH_FORMATION + 0x80
_SPAWN_MOVE_SCRIPT = move_script((3, -2, 0x20, 0x11), (0, 5, 0x10, 0x12))


def _formation_pokes(slots, table, unused=(), script_offsets=None):
    """One formation record, its table entry, and the movement script both point at."""
    positions = [(0x10 * n, 8 * n) for n in range(slots)]
    for index in unused:
        positions[index] = (FORMATION_SLOT_UNUSED, 0)
    offsets = script_offsets or [MOVE_SCRIPT_BYTES * (n % 2) for n in range(slots)]
    return {SCRATCH_FORMATION: formation(positions, offsets, _SPAWN_SCRIPT_BASE),
            _SPAWN_SCRIPT_BASE: _SPAWN_MOVE_SCRIPT,
            table: long_word(SCRATCH_FORMATION),
            SCRATCH_RECORD: script_record(x=0x30, y=0x20, formation_index=0)}


_SPAWN_BODIES = (
    ("formation", ENTRY_SPAWN_FORMATION_COMMON, "g_spawn_formation_common",
     ENTITY_GROUP_SLOTS, A_formation_tbl_a),
    ("parts", ENTRY_SPAWN_BIGOBJ_PARTS_COMMON, "g_spawn_bigobj_parts_common",
     ENTITY_GROUP_SLOTS, A_formation_tbl_parts),
    ("turret", ENTRY_SPAWN_TURRET_COMMON, "g_spawn_turret_common",
     ENTITY_GROUP_SLOTS, A_formation_tbl_turret_a),
)


@pytest.mark.parametrize("name,entry,glue,slots,table", _SPAWN_BODIES)
@pytest.mark.parametrize("unused", ((), (0,), (1, 3), (0, 1, 2, 3)))
def test_the_three_four_slot_spawn_bodies(name, entry, glue, slots, table, unused):
    """The three bodies that share a prologue, over the same formation: what tells them apart is
    the draw layer, the fire countdown, the aim-changed byte and the per-body extras."""
    group = A_entity_group_bigobj
    pokes = _formation_pokes(slots, table, unused=unused)
    pokes[SCRATCH_DESC] = descriptor(group=group, base_frame=0x21, item_kind=2, fire_reload=9,
                                     handler=1, death_dx=-6, death_dy=7, kind=5, hit_points=0x18)
    pokes.update(group_pokes(group, [], count=slots))
    _case(entry, {"a0": SCRATCH_RECORD, "a5": SCRATCH_DESC, "a1": table, "_pokes": pokes},
          lambda lib, buf: getattr(lib, glue)(buf, SCRATCH_RECORD, SCRATCH_DESC, table),
          note=f"{name} unused={unused}")


@pytest.mark.parametrize("unused", ((), (0,)))
def test_spawn_single_common(unused):
    group = 0x19416   # A_entity_group_pair — three single-slot entries, not an array of four
    pokes = _formation_pokes(1, A_formation_tbl_single, unused=unused)
    pokes[SCRATCH_DESC] = descriptor(group=group, base_frame=0x42, item_kind=1, fire_reload=7,
                                     handler=2, kind=15, hit_points=0x4b)
    pokes[table_pointer(group)] = entity_record()
    _case(ENTRY_SPAWN_SINGLE_COMMON,
          {"a0": SCRATCH_RECORD, "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_spawn_single_common(buf, SCRATCH_RECORD, SCRATCH_DESC),
          note=f"unused={unused}")


@pytest.mark.parametrize("unused", ((), (0, 6), (0, 1, 2, 3, 4, 5, 6)))
def test_spawn_squadron_common(unused):
    group = A_entity_group_a0
    pokes = _formation_pokes(ENTITY_GROUP_A_SLOTS, A_formation_tbl_squadron, unused=unused)
    pokes[SCRATCH_DESC] = descriptor(group=group, base_frame=0x0e, item_kind=0, fire_reload=10,
                                     handler=0, kind=0, hit_points=12,
                                     count_minus_1=ENTITY_GROUP_A_SLOTS - 1)
    pokes.update(group_pokes(group, [], count=ENTITY_GROUP_A_SLOTS))
    _case(ENTRY_SPAWN_SQUADRON_COMMON,
          {"a0": SCRATCH_RECORD, "a5": SCRATCH_DESC, "_pokes": pokes},
          lambda lib, buf: lib.g_spawn_squadron_common(buf, SCRATCH_RECORD, SCRATCH_DESC),
          note=f"unused={unused}")


def test_a_spawn_over_a_dirty_arena_shows_which_fields_it_leaves():
    """Every slot pre-filled with 0xff bytes: a field the body does NOT write stays 0xff, which is
    how `spawn_turret_common` writing no hit points and the `st`/`clr.w` split on +24 are visible."""
    group = A_entity_group_bigobj
    dirty = bytes([0xff]) * ENTITY_STRIDE
    for name, entry, glue, slots, table in _SPAWN_BODIES:
        pokes = _formation_pokes(slots, table)
        pokes[SCRATCH_DESC] = descriptor(group=group, base_frame=0x21, fire_reload=9,
                                         handler=1, death_dx=-6, death_dy=7, kind=5,
                                         hit_points=0x18)
        pokes.update(group_pokes(group, [dirty] * slots, count=slots))
        _case(entry, {"a0": SCRATCH_RECORD, "a5": SCRATCH_DESC, "a1": table, "_pokes": pokes},
              lambda lib, buf: getattr(lib, glue)(buf, SCRATCH_RECORD, SCRATCH_DESC, table),
              note=f"{name} over a dirty arena")


@pytest.mark.parametrize("x,y", ((0, 0), (0x30, 0x20), (0xfff0, 0xfff0), (0x7fff, 0x7fff)))
def test_spawn_item_bomb(x, y):
    pokes = {SCRATCH_RECORD: script_record(x=x, y=y),
             A_item_bomb: word(0x11) + word(0x22) + long_word(0x33) + word(0x44)}
    _case(ENTRY_SPAWN_ITEM_BOMB, {"a0": SCRATCH_RECORD, "_pokes": pokes},
          lambda lib, buf: lib.g_spawn_item_bomb(buf, SCRATCH_RECORD), poison=True,
          note=f"({x:#x},{y:#x})")


def _script_step_pokes(kind, trigger=0, scroll=0x40, weapon_level=0, pickup_pending=0,
                       bomb_spawned=0, formation_index=0):
    return {A_spawn_script_ptr: long_word(SCRATCH_SCRIPT),
            A_spawn_script_cursor: long_word(0),
            SCRATCH_SCRIPT: script_record(trigger=trigger, kind=kind, x=0x40, y=0x30,
                                          formation_index=formation_index)
                            + script_record(trigger=SPAWN_SCRIPT_END),
            A_scroll_pos: word(scroll),
            A_weapon_level: word(weapon_level),
            A_item_pickup_pending: word(pickup_pending),
            A_item_bomb_spawned: word(bomb_spawned)}


@pytest.mark.parametrize("kind", range(26))
def test_spawn_script_step_dispatches_every_type(kind):
    """All twenty-six stubs, each through the table the original reads — which is the only place
    the stub-to-descriptor-and-table mapping in src/weapons.c is checked."""
    _case(ENTRY_SPAWN_SCRIPT_STEP, {"_pokes": _script_step_pokes(kind)},
          lambda lib, buf: lib.g_spawn_script_step(buf), note=f"kind={kind}")


@pytest.mark.parametrize("formation_index", (0, 1, 2, 5))
@pytest.mark.parametrize("kind", (0, 4, 12, 17, 23))
def test_spawn_script_step_over_the_shipped_formation_tables(kind, formation_index):
    """One stub of each body, over the game's OWN formation records rather than a poked one."""
    _case(ENTRY_SPAWN_SCRIPT_STEP,
          {"_pokes": _script_step_pokes(kind, formation_index=formation_index)},
          lambda lib, buf: lib.g_spawn_script_step(buf),
          note=f"kind={kind} formation={formation_index}")


@pytest.mark.parametrize("scroll,trigger", ((0, 1), (1, 1), (2, 1), (0x7fff, 0x8000),
                                            (0x8000, 0x7fff)))
def test_the_script_trigger_is_a_signed_word_compare(scroll, trigger):
    _case(ENTRY_SPAWN_SCRIPT_STEP,
          {"_pokes": _script_step_pokes(0, trigger=trigger, scroll=scroll)},
          lambda lib, buf: lib.g_spawn_script_step(buf),
          note=f"scroll={scroll:#x} trigger={trigger:#x}")


def test_the_script_ends_at_its_own_sentinel():
    pokes = _script_step_pokes(0)
    pokes[SCRATCH_SCRIPT] = script_record(trigger=SPAWN_SCRIPT_END, kind=0)
    _case(ENTRY_SPAWN_SCRIPT_STEP, {"_pokes": pokes},
          lambda lib, buf: lib.g_spawn_script_step(buf), note="sentinel")


@pytest.mark.parametrize("weapon_level", (0, 3, WEAPON_LEVEL_FULL, 5))
@pytest.mark.parametrize("pickup_pending", (0, 1, 0xff00))
def test_the_weapon_item_offer_falls_back(weapon_level, pickup_pending):
    """A weapon power-up the player cannot use becomes an ordinary enemy AND clears the pending
    flag, so declining once re-arms the next offer."""
    _case(ENTRY_SPAWN_SCRIPT_STEP,
          {"_pokes": _script_step_pokes(SPAWN_TYPE_WEAPON_ITEM, weapon_level=weapon_level,
                                        pickup_pending=pickup_pending)},
          lambda lib, buf: lib.g_spawn_script_step(buf),
          note=f"level={weapon_level} pending={pickup_pending:#x}")


@pytest.mark.parametrize("bomb_spawned", (0, 1, 0x00ff, 0xff00))
def test_the_bomb_item_offer_happens_once(bomb_spawned):
    """The flag is set with `st`, so only its HIGH byte is written — a low byte already set makes
    the word non-zero and the second offer falls back."""
    _case(ENTRY_SPAWN_SCRIPT_STEP,
          {"_pokes": _script_step_pokes(SPAWN_TYPE_BOMB_ITEM, bomb_spawned=bomb_spawned)},
          lambda lib, buf: lib.g_spawn_script_step(buf), note=f"spawned={bomb_spawned:#x}")


def test_spawn_script_step_over_the_shipped_level_scripts():
    """The five levels' own scripts, from their first record — the data the game really runs."""
    for level, script in enumerate((0x1b350, 0x1b5aa, 0x1b7e6, 0x1b9d2, 0x1bbd2)):
        for cursor in range(0, 5 * SPAWN_REC_BYTES, SPAWN_REC_BYTES):
            _case(ENTRY_SPAWN_SCRIPT_STEP,
                  {"_pokes": {A_spawn_script_ptr: long_word(script),
                              A_spawn_script_cursor: long_word(cursor),
                              A_scroll_pos: word(0x7fff)}},
                  lambda lib, buf: lib.g_spawn_script_step(buf),
                  note=f"level {level + 1} cursor {cursor}")


# ==================================================================================================
# The pins
# ==================================================================================================
MIRRORS = (
    "A_player_bullet_arena", "PLAYER_BULLET_BYTES", "PLAYER_BULLET_X", "PLAYER_BULLET_Y",
    "PLAYER_BULLET_DX", "PLAYER_BULLET_STATE", "PLAYER_BULLET_FREE", "PLAYER_BULLET_IN_FLIGHT",
    "PLAYER_BULLET_HIT", "A_player_shot_slot_0", "PLAYER_SHOT_SLOTS", "PLAYER_SHOT_BULLETS",
    "PLAYER_SHOT_TABLE_STRIDE", "A_shot_slot_busy_0", "SHOT_SLOT_BUSY_BYTES",
    "A_dl_player_bullets_0", "DL_SHOT_STRIDE", "PLAYER_BULLET_DY", "PLAYER_BULLET_RETIRE_Y",
    "PLAYER_BULLET_GLYPH", "PLAYER_BULLET_GLYPH_ALT", "PLAYER_BULLET_IMPACT_GLYPH",
    "A_player_bomb", "BOMB_X", "BOMB_START_Y", "BOMB_Y", "BOMB_FRAME",
    "A_bomb_fall_path", "BOMB_PATH_DY", "BOMB_PATH_FRAME", "BOMB_PATH_STEP_BYTES",
    "A_blast_state", "BLAST_X", "BLAST_Y", "BLAST_POINTS", "BLAST_POINT_BYTES",
    "BLAST_POINTS_COUNT", "A_blast_offset_tbl", "BLAST_OFFSET_STEP_BYTES", "BLAST_LAST_STEP",
    "BLAST_GLYPH", "BLAST_HIT_BOX", "A_blast_step", "A_bomb_falling", "A_bomb_exploding",
    "A_bomb_path_cursor", "A_dl_blast", "A_dl_bomb",
    "A_enemy_bullets", "ENEMY_BULLET_BYTES", "ENEMY_BULLET_X", "ENEMY_BULLET_Y",
    "ENEMY_BULLET_DX", "ENEMY_BULLET_DY", "ENEMY_BULLET_ACTIVE", "ENEMY_BULLET_END",
    "ENEMY_BULLET_LIVE", "A_dl_enemy_bullets", "ENEMY_BULLET_GLYPH",
    "ENEMY_BULLET_CLIP_LEFT", "ENEMY_BULLET_CLIP_RIGHT", "ENEMY_BULLET_CLIP_TOP",
    "ENEMY_BULLET_CLIP_BOTTOM", "A_enemy_aim_dir_lut", "AIM_LUT_ROW_STRIDE", "AIM_CELL_SHIFT",
    "A_enemy_bullet_velocity_tbl", "AIM_VELOCITY_BYTES",
    "ENEMY_DESC_MUZZLE_DX", "ENEMY_DESC_MUZZLE_DY", "ENEMY_FIRE_SPREAD", "ENEMY_FIRE_RECOIL",
    "ENEMY_FIRE_X_MAX", "ENEMY_FIRE_Y_MAX", "ENEMY_FIRE_Y_MIN_B", "ENEMY_AIM_PLAYER_OFFSET",
    "A_dl_turret_ptrs_t0", "TURRET_FACINGS", "TURRET_HALF_TURN", "A_turret_facing_lut",
    "TURRET_LUT_ROW_STRIDE", "TURRET_AIM_PLAYER_DX", "A_turret_barrel_tbl_lo",
    "A_turret_barrel_tbl_hi", "TURRET_BARREL_STRIDE", "TURRET_BARREL_ENTRY_BYTES",
    "A_turret_hit_tbl_lo", "A_turret_hit_tbl_hi", "TURRET_HIT_ENTRY_BYTES",
    "A_turret_barrel_base_frame", "TURRET_BARREL_BASE_FRAME_BYTE",
    "TURRET_STATE_AIMING", "TURRET_STATE_HIT",
    "A_dl_muzzle_group", "A_dl_muzzle_pair_0", "DL_FLASH_PAIR", "MUZZLE_FLASH_GLYPH_BUMP",
    "MUZZLE_FLASH_GROUP_DX", "MUZZLE_FLASH_GROUP_DY", "ENEMY_DESC_FLASH_DX",
    "ENEMY_DESC_FLASH_DY", "ENEMY_DESC_FLASH2_DX", "ENEMY_DESC_FLASH2_DY",
    "A_bullet_hit_handler_tbl", "A_blast_hit_handler_tbl", "HIT_HANDLER_PTR_BYTES", "HIT_GROUPS",
    "PLAYER_BULLET_HIT_DX", "ENEMY_DESC_FIRING_HP", "ENEMY_HIT_DROP_OFFSET",
    "BLAST_DAMAGE_4", "BLAST_DAMAGE_5", "BLAST_DAMAGE_6", "BULLET_DAMAGE",
    "BULLET_KILL_AT_HIT_POINTS", "ENEMY_INDESTRUCTIBLE", "ENEMY_FRAME_HURT_BUMP",
    "A_spawn_script_ptr", "A_spawn_script_cursor", "A_item_bomb_spawned",
    "SPAWN_REC_TRIGGER", "SPAWN_REC_TYPE", "SPAWN_REC_X", "SPAWN_REC_Y", "SPAWN_REC_FORMATION",
    "SPAWN_REC_BYTES", "SPAWN_SCRIPT_END", "A_spawn_handler_tbl", "SPAWN_HANDLER_PTR_BYTES",
    "SPAWN_TYPE_WEAPON_ITEM", "SPAWN_TYPE_BOMB_ITEM", "SPAWN_TYPE_FALLBACK",
    "FORMATION_POS_DX", "FORMATION_POS_DY", "FORMATION_POS_BYTES", "FORMATION_SLOT_UNUSED",
    "FORMATION_SCRIPT_PTR_BYTES", "FORMATION_TBL_ENTRY_BYTES", "SPAWN_FACING_START",
    "SPAWN_FIRE_COUNTDOWN_15", "SPAWN_FIRE_COUNTDOWN_10",
    "SPAWN_DRAW_LAYER_TOP", "SPAWN_DRAW_LAYER_UNDER",
    "A_formation_tbl_a", "A_formation_tbl_b", "A_formation_tbl_single", "A_formation_tbl_parts",
    "A_formation_tbl_parts_b", "A_formation_tbl_parts_c", "A_formation_tbl_turret_a",
    "A_formation_tbl_turret_b", "A_formation_tbl_squadron",
    "A_enemy_desc_0c", "A_enemy_desc_0d", "A_enemy_desc_0e", "A_enemy_desc_0f",
    # ...and the neighbours' headers, which this battery reads and never defines.
    ("A_entity_arena", "include/globals.h", "A_entity_arena"),
    ("ENTITY_STRIDE", "include/globals.h", "ENTITY_STRIDE"),
    ("ENTITY_SLOTS", "include/globals.h", "ENTITY_SLOTS"),
    ("A_sprite_bank", "include/globals.h", "A_sprite_bank"),
    ("SPRITE_RECORD_BYTES", "include/globals.h", "SPRITE_RECORD_BYTES"),
    ("A_sound_module", "include/globals.h", "A_sound_module"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_FRAME_OFFSET", "include/entity.h", "ENTITY_FRAME_OFFSET"),
    ("ENTITY_DRAW_LAYER", "include/entity.h", "ENTITY_DRAW_LAYER"),
    ("ENTITY_DX", "include/entity.h", "ENTITY_DX"),
    ("ENTITY_DY", "include/entity.h", "ENTITY_DY"),
    ("ENTITY_STEP_COUNTDOWN", "include/entity.h", "ENTITY_STEP_COUNTDOWN"),
    ("ENTITY_ACTIVE", "include/entity.h", "ENTITY_ACTIVE"),
    ("ENTITY_DYING", "include/entity.h", "ENTITY_DYING"),
    ("ENTITY_ITEM_KIND", "include/entity.h", "ENTITY_ITEM_KIND"),
    ("ENTITY_BASE_FRAME", "include/entity.h", "ENTITY_BASE_FRAME"),
    ("ENTITY_HIT_POINTS", "include/entity.h", "ENTITY_HIT_POINTS"),
    ("ENTITY_AIM_CHANGED", "include/entity.h", "ENTITY_AIM_CHANGED"),
    ("ENTITY_FACING", "include/entity.h", "ENTITY_FACING"),
    ("ENTITY_DEPTH_SELECT", "include/entity.h", "ENTITY_DEPTH_SELECT"),
    ("ENTITY_FIRE_COUNTDOWN", "include/entity.h", "ENTITY_FIRE_COUNTDOWN"),
    ("ENTITY_FIRE_RELOAD", "include/entity.h", "ENTITY_FIRE_RELOAD"),
    ("ENTITY_PATH_SELECT", "include/entity.h", "ENTITY_PATH_SELECT"),
    ("ENTITY_PATH_CURSOR", "include/entity.h", "ENTITY_PATH_CURSOR"),
    ("ENTITY_FIRING", "include/entity.h", "ENTITY_FIRING"),
    ("ENTITY_FRAME_BUMP", "include/entity.h", "ENTITY_FRAME_BUMP"),
    ("ENTITY_ANIM_TIMER", "include/entity.h", "ENTITY_ANIM_TIMER"),
    ("ENTITY_KIND", "include/entity.h", "ENTITY_KIND"),
    ("ENTITY_HIDDEN_UNDER_BIGOBJ", "include/entity.h", "ENTITY_HIDDEN_UNDER_BIGOBJ"),
    ("ENTITY_SCRIPT_BASE", "include/entity.h", "ENTITY_SCRIPT_BASE"),
    ("ENTITY_SCRIPT_CURSOR", "include/entity.h", "ENTITY_SCRIPT_CURSOR"),
    ("ENTITY_GROUP_SLOTS", "include/entity.h", "ENTITY_GROUP_SLOTS"),
    ("ENTITY_GROUP_A_SLOTS", "include/entity.h", "ENTITY_GROUP_A_SLOTS"),
    ("ENTITY_GROUP_PTR_BYTES", "include/entity.h", "ENTITY_GROUP_PTR_BYTES"),
    ("A_entity_group_a0", "include/entity.h", "A_entity_group_a0"),
    ("A_entity_group_t0", "include/entity.h", "A_entity_group_t0"),
    ("ENTITY_GROUP_T_STRIDE", "include/entity.h", "ENTITY_GROUP_T_STRIDE"),
    ("ENTITY_GROUP_T_COUNT", "include/entity.h", "ENTITY_GROUP_T_COUNT"),
    ("A_entity_group_x0", "include/entity.h", "A_entity_group_x0"),
    ("ENTITY_GROUP_X_STRIDE", "include/entity.h", "ENTITY_GROUP_X_STRIDE"),
    ("ENTITY_GROUP_X_COUNT", "include/entity.h", "ENTITY_GROUP_X_COUNT"),
    ("A_entity_group_bigobj", "include/entity.h", "A_entity_group_bigobj"),
    ("A_entity_group_a4", "include/entity.h", "A_entity_group_a4"),
    ("DL_TURRET_RUN_GROUPS", "include/entity.h", "DL_TURRET_RUN_GROUPS"),
    ("ENEMY_DESC_GROUP", "include/entity.h", "ENEMY_DESC_GROUP"),
    ("ENEMY_DESC_BASE_FRAME", "include/entity.h", "ENEMY_DESC_BASE_FRAME"),
    ("ENEMY_DESC_ITEM_KIND", "include/entity.h", "ENEMY_DESC_ITEM_KIND"),
    ("ENEMY_DESC_FIRE_RELOAD", "include/entity.h", "ENEMY_DESC_FIRE_RELOAD"),
    ("ENEMY_DESC_COUNT_MINUS_1", "include/entity.h", "ENEMY_DESC_COUNT_MINUS_1"),
    ("ENEMY_DESC_HANDLER", "include/entity.h", "ENEMY_DESC_HANDLER"),
    ("ENEMY_DESC_DEATH_DX", "include/entity.h", "ENEMY_DESC_DEATH_DX"),
    ("ENEMY_DESC_DEATH_DY", "include/entity.h", "ENEMY_DESC_DEATH_DY"),
    ("ENEMY_DESC_KIND", "include/entity.h", "ENEMY_DESC_KIND"),
    ("ENEMY_DESC_HIT_POINTS", "include/entity.h", "ENEMY_DESC_HIT_POINTS"),
    ("A_enemy_desc_00", "include/entity.h", "A_enemy_desc_00"),
    ("A_enemy_desc_04", "include/entity.h", "A_enemy_desc_04"),
    ("A_enemy_desc_10", "include/entity.h", "A_enemy_desc_10"),
    ("A_enemy_desc_14", "include/entity.h", "A_enemy_desc_14"),
    ("A_enemy_desc_18", "include/entity.h", "A_enemy_desc_18"),
    ("A_anim_frame_a", "include/entity.h", "A_anim_frame_a"),
    ("A_anim_frame_b", "include/entity.h", "A_anim_frame_b"),
    ("A_item_bomb", "include/entity.h", "A_item_bomb"),
    ("ITEM_X", "include/entity.h", "ITEM_X"),
    ("ITEM_Y", "include/entity.h", "ITEM_Y"),
    ("ITEM_ACTIVE", "include/entity.h", "ITEM_ACTIVE"),
    ("A_item_pickup_pending", "include/entity.h", "A_item_pickup_pending"),
    ("A_weapon_level", "include/weapons.h", "A_weapon_level"),
    ("WEAPON_LEVEL_FULL", "include/entity.h", "WEAPON_LEVEL_FULL"),
    ("MOVE_SCRIPT_BYTES", "include/entity.h", "MOVE_SCRIPT_BYTES"),
    ("SCRIPT_TERMINATOR", "include/entity.h", "SCRIPT_TERMINATOR"),
    ("PLAYER_X", "include/player.h", "PLAYER_X"),
    ("PLAYER_Y", "include/player.h", "PLAYER_Y"),
    ("A_display_list", "include/display_list.h", "A_display_list"),
    ("DISPLAY_REC_BYTES", "include/display_list.h", "DISPLAY_REC_BYTES"),
    ("DISPLAY_REC_X", "include/display_list.h", "DISPLAY_REC_X"),
    ("DISPLAY_REC_Y", "include/display_list.h", "DISPLAY_REC_Y"),
    ("DISPLAY_REC_FRAME", "include/display_list.h", "DISPLAY_REC_FRAME"),
    ("DISPLAY_REC_ACTIVE", "include/display_list.h", "DISPLAY_REC_ACTIVE"),
    ("DISPLAY_ACTIVE_ON_TOP", "include/display_list.h", "DISPLAY_ACTIVE_ON_TOP"),
    ("DISPLAY_ACTIVE_UNDER_SCENERY", "include/display_list.h", "DISPLAY_ACTIVE_UNDER_SCENERY"),
    ("SPRITE_REC_DRAW_DX", "include/sprite.h", "SPRITE_REC_DRAW_DX"),
    ("SPRITE_REC_DRAW_DY", "include/sprite.h", "SPRITE_REC_DRAW_DY"),
    ("SPRITE_REC_HIT_DX", "include/sprite.h", "SPRITE_REC_HIT_DX"),
    ("SPRITE_REC_HIT_DY", "include/sprite.h", "SPRITE_REC_HIT_DY"),
    ("SPRITE_REC_HIT_W", "include/sprite.h", "SPRITE_REC_HIT_W"),
    ("SPRITE_REC_HIT_H", "include/sprite.h", "SPRITE_REC_HIT_H"),
    ("A_player", "include/player.h", "A_player"),
    ("A_player_hit", "include/player.h", "A_player_hit"),
    ("A_alt_bullet_glyph_flag", "include/hud.h", "A_alt_bullet_glyph_flag"),
    ("A_scroll_pos", "include/scroll.h", "A_scroll_pos"),
    ("SND_SFX_ACTIVE", "include/sound.h", "SND_SFX_ACTIVE"),
)

ENTRY_PROLOGUES = {
    "ENTRY_BOMB_BLAST_STEP": "4a79000176f0672c610009666100151c",
    "ENTRY_BOMB_BLAST_PUBLISH": "4a79000176f0674243f900017c8a41f9",
    "ENTRY_BOMB_FALL_STEP": "4a79000176ee673a4a79000176f06634",
    "ENTRY_BOMB_PUBLISH": "4a79000176ee672c4a79000176f06624",
    "ENTRY_CLEAR_OBJECT_LIST": "48e7fffe41f90001946e0c5003e76704",
    "ENTRY_BOMB_BLAST_VS_ENTITIES": "41f90005aec22c484bf9000197d26100",
    "ENTRY_BOMB_BLAST_VS_ENTITIES_IF_ACTIVE": "3e3c00034a79000176f0670422486016",
    "ENTRY_BOMB_BLAST_VS_ENTITY_GROUPS": "43e9000424553a2d000e265a4a6b000e",
    "ENTRY_PLAYER_BULLETS_VS_ENTITIES":
        "41f9000194226100001641f9000194366100000c41f90001944a6000",
    "ENTRY_PLAYER_BULLETS_VS_ENTITIES_GROUP": "2c484bf9000197d2610000fe204e4bf9",
    "ENTRY_PLAYER_BULLET_VS_ENTITY_GROUPS": "3e3c000422584a6900066700008a0c69",
    "ENTRY_MUZZLE_FLASH_PUBLISH_ALL": "4bf90001975e43f900017b3a3e3c0003",
    "ENTRY_MUZZLE_FLASH_PUBLISH_PAIR": "205526584a6b000e67584a6b00106652",
    "ENTRY_MUZZLE_FLASH_PUBLISH_GROUP": "205526584a6b000e67704a6b0010666a",
    "ENTRY_ENEMY_BULLETS_PUBLISH": "41f90001946e43f900017bc40c6803e7",
    "ENTRY_ENEMIES_FIRE_ALL": "6100025241f9000190a44df90001946e",
    "ENTRY_ENEMY_BULLET_SPAWN_AIMED": "0c6e03e700086700008c4a6e0008667a",
    "ENTRY_ENEMY_BULLETS_MOVE": "41f90001946e0c6803e70008673e4a68",
    "ENTRY_TURRETS_AIM_ALL": "43f9000192b66100009643f9000192d6",
    "ENTRY_TURRETS_AIM_GROUP_ACTIVE": "3e3c000320594a68000e670a4a680010",
    "ENTRY_TURRETS_AIM_GROUP": "3e3c00032059610001ac51cffff84e75",
    "ENTRY_TURRETS_PUBLISH_ALL": "41f9000192b647f9000192c649f90001",
    "ENTRY_TURRET_PUBLISH_GROUP": "3e3c0003245b22584a69000e67204a69",
    "ENTRY_TURRET_AIM_STEP": "2f074280428442854286428745f90001",
    "ENTRY_SPAWN_SCRIPT_STEP": "207900017770d1f9000177540c50a3a1",
    "ENTRY_SPAWN_ITEM_BOMB": "43f90005aeae32a80004336800060002",
    # The three four-slot bodies are byte-identical for their whole first pass; see this file's
    # docstring. The pin holds the SHAPE at each address, and pass two is what the cases separate.
    "ENTRY_SPAWN_FORMATION_COMMON":
        "32280008e549d3c122512c49302800043228000624553e3c0003265a",
    "ENTRY_SPAWN_BIGOBJ_PARTS_COMMON":
        "32280008e549d3c122512c49302800043228000624553e3c0003265a",
    "ENTRY_SPAWN_TURRET_COMMON":
        "32280008e549d3c122512c49302800043228000624553e3c0003265a",
    "ENTRY_SPAWN_SINGLE_COMMON": "43f900019a5432280008e549d3c12251",
    "ENTRY_SPAWN_SQUADRON_COMMON": "43f900019b5432280008e549d3c12251",
    "ENTRY_PLAYER_BULLETS_MOVE_ALL":
        "41f9000194226100001641f9000194366100000c41f90001944a6000",
    "ENTRY_PLAYER_BULLETS_MOVE_GROUP": "3e3c000422580c690002000667163029",
    "ENTRY_PLAYER_BULLETS_PUBLISH_ALL": "41f90001942243f900017b6a61000022",
    "ENTRY_PLAYER_BULLETS_PUBLISH_GROUP": "3e3c000424584a6a000667520c6a0002",
    "ENTRY_PLAYER_SHOT_SLOTS_RELEASE": "41f90001942249f90001771661000022",
    "ENTRY_PLAYER_SHOT_SLOT_RELEASE_IF_EMPTY": "3e3c000422584a690006660651cffff6",
}
