"""Differential battery for the entity subsystem — src/entity.c.

WHERE THE CASES' WORLDS COME FROM, because this subsystem has three kinds of routine and they need
three different machines:

* a LEAF that takes its record in a register (`entity_move`, the three item steps, `enemy_bomb_drop`,
  every `entity_publish_*`) is driven over a record poked into `abi.SCRATCH`, so a case can spell an
  edge the game's own data never reaches;
* a routine that walks the GAME'S OWN slot-pointer tables (`entities_move_all`,
  `entities_publish_all`, the hide and depth passes) is driven over records poked into the real arena
  slots those tables name, read out of `harness.BASE_IMAGE` rather than assumed;
* and the two whole-frame passes are ALSO driven over a POPULATED WORLD that the original built
  itself: `conftest.py`'s `staged_world_pokes` runs the game's own `spawn_script_step` @ 0x12fc4
  under the oracle 6,000 times against level 1's script, which fills 28 slots across the a-,
  turret-, big-object, pair and x-groups with records no test wrote. A hand-poked world can only
  contain the shapes its author thought of; this one contains what the game spawns.

The staged image reaches a case as POKES rather than as a base image, because `differential()` takes
its memory from `harness.set_base_image` and `conftest.py`'s autouse fixture owns that
(README.md, "Adding a function", step 4). `conftest.byte_run_pokes` is the conversion, and the world
itself is built ONCE PER RUN and cached across the xdist workers rather than per battery per core.

NO CASE HERE STOPS AT A SEAM. Both of this subsystem's calls into another subsystem are ported and
made for real, so every routine is diffed to its own `rts`: `sfx_play_2` @ 0x121e6 (the sound slice)
out of `sprite_hitbox_test`, and `score_add_1000` @ 0x10b8c (the hud slice) out of
`item_drop_if_formation_cleared`'s bonus arm — the score digits and the sound module's state
included in the difference.

That bonus arm is the one place in this battery where the 68000 X FLAG is an argument: the score
chain opens with an `abcd` that ADDS X, and the routine's exit restores registers and no condition
code, so X goes in through `abi.extend_call_pokes` and the X it leaves comes back through
`abi.oracle_extend`.
"""
import ctypes
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

MIRROR_HEADER = "include/entity.h"

# ---- entries, and the two seams ------------------------------------------------------------------
ENTRY_BIGOBJ_EXTRA_PARTS_PUBLISH = 0x102de
ENTRY_COUNT_GAME_FRAME = 0x11654
ENTRY_ITEMS_PICKUP_CHECK = 0x1165c
ENTRY_SPRITE_HITBOX_TEST = 0x11698
ENTRY_ITEM_PICKUP_AWARD = 0x11714
ENTRY_ENTITY_HIDE_UNDER_BIGOBJ = 0x1175c
ENTRY_ENTITY_HIDE_UNDER_BIGOBJ_GROUP = 0x11784
ENTRY_ENTITY_HIDE_TEST = 0x1179a
ENTRY_BIGOBJ_OVERLAP_DEPTH_UPDATE = 0x117f4
ENTRY_BIGOBJ_DEPTH_TEST = 0x11820
ENTRY_ENEMY_BOMBS_MOVE = 0x1184e
ENTRY_ITEMS_MOVE_ALL = 0x1187a
ENTRY_ITEM_DROP_STEP = 0x118a2
ENTRY_ITEM_FALL_STEP = 0x118bc
ENTRY_ITEM_PATH_STEP = 0x118da
ENTRY_ITEMS_PUBLISH = 0x1191c
ENTRY_ANIM_FRAME_IDS_UPDATE = 0x119fc
ENTRY_ITEM_DROP_IF_FORMATION_CLEARED = 0x121fe
ENTRY_DIFFICULTY_APPLY_FIRE_RATES = 0x12cc8
ENTRY_ENTITIES_MOVE_ALL = 0x12d5c
ENTRY_ENTITIES_MOVE_GROUPS_EXTRA = 0x12e22
ENTRY_ENTITIES_MOVE_GROUP4 = 0x12e54
ENTRY_ENTITIES_MOVE_BIGOBJ = 0x12e64
ENTRY_ENTITIES_MOVE_ONE_GROUP = 0x12e82
ENTRY_ENTITIES_MOVE_BIGOBJ_PARTS = 0x12e88
ENTRY_ENTITY_MOVE = 0x12e9e
ENTRY_ENEMY_BOMB_DROP = 0x12f2e
ENTRY_ENTITIES_PUBLISH_ALL = 0x1361c
ENTRY_ENTITIES_PUBLISH_FACING_GROUPS = 0x13634
ENTRY_ENTITY_PUBLISH_GROUP_FACING = 0x136a2
ENTRY_ENTITY_PUBLISH_GROUP_A4 = 0x13702
ENTRY_ENTITIES_PUBLISH_BIGOBJ_GROUP = 0x13764
ENTRY_ENTITIES_PUBLISH_PLAIN_GROUPS = 0x13774
ENTRY_ENTITY_PUBLISH_GROUP_PLAIN = 0x137f4
ENTRY_ENTITIES_PUBLISH_ANIM_GROUPS = 0x13838
ENTRY_ENTITY_PUBLISH_ANIM = 0x1387a
ENTRY_ENTITY_PUBLISH_GROUP_OFFSET = 0x138e8
ENTRY_ENTITIES_PUBLISH_LAST_GROUPS = 0x1393a
ENTRY_ENTITY_PUBLISH_GROUP_LAST = 0x13992

STOP_DIFFICULTY_TAIL = 0x12d58  # `bra.w start_level` — difficulty_apply_fire_rates has no rts

# ---- mirrors of include/entity.h and its neighbours ---------------------------------------------
A_entity_arena = 0x59984
ENTITY_STRIDE = 58
ENTITY_SLOTS = 91

ENTITY_X, ENTITY_Y, ENTITY_FRAME_OFFSET = 0, 2, 4
ENTITY_DRAW_LAYER, ENTITY_DRAW_LAYER_BYTE = 6, 7
ENTITY_DX, ENTITY_DY, ENTITY_STEP_COUNTDOWN = 8, 10, 12
ENTITY_ACTIVE, ENTITY_DYING = 14, 16
ENTITY_BASE_FRAME, ENTITY_HIT_POINTS = 20, 22
ENTITY_AIM_CHANGED, ENTITY_FACING, ENTITY_DEPTH_SELECT = 24, 26, 28
ENTITY_FIRE_RELOAD, ENTITY_PATH_SELECT, ENTITY_PATH_CURSOR = 32, 34, 36
ENTITY_FIRING, ENTITY_FRAME_BUMP, ENTITY_ANIM_TIMER = 38, 40, 42
ENTITY_KIND, ENTITY_HAS_DROPPED, ENTITY_HIDDEN_UNDER_BIGOBJ = 44, 46, 48
ENTITY_SCRIPT_BASE, ENTITY_SCRIPT_CURSOR = 50, 54
ENTITY_KIND_BOMBER = 4

MOVE_SCRIPT_BYTES = 8
SCRIPT_TERMINATOR = 0x3e7

A_entity_group_a0, A_entity_group_a1 = 0x19246, 0x19262
A_entity_group_a2, A_entity_group_a3 = 0x1927e, 0x1929a
ENTITY_GROUP_A_SLOTS = 7
A_entity_group_t0, ENTITY_GROUP_T_STRIDE, ENTITY_GROUP_T_COUNT = 0x192b6, 0x20, 8
A_entity_group_bigobj = 0x193b6
A_entity_group_x0, ENTITY_GROUP_X_STRIDE, ENTITY_GROUP_X_COUNT = 0x193c6, 0x10, 5
A_entity_group_pair = 0x19416
ENTITY_GROUP_PAIR_STRIDE, ENTITY_GROUP_PAIR_COUNT = 4, 3
A_entity_pair_slot_2 = 0x5a960
A_entity_group_a4 = 0x1945e
ENTITY_GROUP_SLOTS, ENTITY_GROUP_PTR_BYTES = 4, 4

ENEMY_DESC_FIRE_RELOAD, ENEMY_DESC_DEATH_DX = 8, 18
ENEMY_DESC_DEATH_DY, ENEMY_DESC_HIT_POINTS = 20, 24
A_enemy_desc_00, A_enemy_desc_12, A_enemy_desc_14 = 0x19534, 0x19726, 0x1975e

A_entity_path_tbl_ptrs, ENTITY_PATH_TABLES, ENTITY_PATH_PTR_BYTES = 0x19128, 3, 4
A_anim_frame_a, A_anim_frame_b = 0x19518, 0x1951c
A_anim_frame_item0, A_anim_frame_item1 = 0x19520, 0x19525
A_anim_frame_item3, A_anim_frame_bomb = 0x1952a, 0x1952f
ANIM_FRAME_TABLE_OFFSET, ANIM_PHASE_MASK_2, ANIM_PHASE_MASK_3 = 1, 2, 3

A_item_weapon, A_item_life, A_item_bomb, A_item_extra = 0x5ae9a, 0x5aea4, 0x5aeae, 0x5aeb8
ITEM_X, ITEM_Y, ITEM_CURSOR, ITEM_ACTIVE, ITEM_BYTES = 0, 2, 4, 8, 10
A_item_flight_path, ITEM_PATH_STEP_BYTES = 0x1b02a, 4
ITEM_KIND_WEAPON, ITEM_KIND_BOMB, ITEM_KIND_LIFE = 0, 1, 2
WEAPON_LEVEL_FULL, BOMBS_FULL, LIVES_NO_AWARD_ABOVE = 4, 6, 6

A_dl_entity_t0, A_dl_entity_t4, DL_GROUP4_STRIDE, DL_TURRET_RUN_GROUPS = 0x17834, 0x178f4, 0x18, 4
A_dl_entity_pair, A_dl_entity_bigobj, A_dl_entity_x0 = 0x179b4, 0x179ea, 0x17a02
A_dl_entity_a0, DL_GROUP7_STRIDE, A_dl_entity_a4 = 0x17a7a, 0x2a, 0x17b22
A_dl_item_0, A_dl_item_1, A_dl_item_2, A_dl_item_3 = 0x17c24, 0x17c2a, 0x17c30, 0x1782e
BIGOBJ_EXTRA_PART_FRAME_0, BIGOBJ_EXTRA_PART_FRAME_1 = 0x4f, 0x4a
BIGOBJ_EXTRA_PART_FRAME_2, BIGOBJ_EXTRA_PARTS, BIGOBJ_EXTRA_MARKER = 0x4b, 3, 0x3e7
BIGOBJ_BOX_SIZE, BIGOBJ_PROBE_OFFSET = 0x40, 0x0e

A_frame_counter, A_item_pickup_pending = 0x17764, 0x176c2
A_enemy_bomb_slot_scan, ENEMY_BOMB_SLOTS = 0x1776c, 16
ENEMY_BOMB_DY, ENTITY_RETIRE_Y = 2, 0xc8

A_display_list, DISPLAY_REC_BYTES = 0x177ce, 6
DISPLAY_REC_X, DISPLAY_REC_Y, DISPLAY_REC_FRAME, DISPLAY_REC_ACTIVE = 0, 2, 4, 5
DISPLAY_ACTIVE_UNDER_SCENERY, DISPLAY_ACTIVE_ON_TOP = 0xff, 0x01

A_player, PLAYER_X, PLAYER_Y, PLAYER_FRAME = 0x190a4, 0, 2, 4
A_bombs, A_lives, A_weapon_level = 0x17710, 0x17712, 0x17714
A_score_bcd = 0x15a2a
A_sprite_bank, SPRITE_RECORD_BYTES = 0x1be36, 20
SPRITE_REC_DRAW_DX, SPRITE_REC_DRAW_DY = 8, 10
SPRITE_REC_HIT_DX, SPRITE_REC_HIT_DY, SPRITE_REC_HIT_W, SPRITE_REC_HIT_H = 12, 14, 16, 18

ITEM_EXTRA_FRAME = 0xa1
ITEM_EXTRA_FALL_FRAMES = 0x32
ITEM_PICKUP_BOX = 0x10
FIRE_RELOAD_COMMON, HIT_POINTS_TURRET, FIRE_RELOAD_TURRET, HIT_POINTS_A4 = 10, 12, 7, 18
HIDE_TEST_GROUPS = 4
SCC_TRUE = 0xff

# Where a case parks the things it invents. The scratch map's own clearance is test_constants.py's.
SCRATCH_ENTITY = abi.SCRATCH
SCRATCH_SCRIPT = abi.SCRATCH + 0x100
SCRATCH_ITEM = abi.SCRATCH + 0x200

# ---- the glue's C signatures ---------------------------------------------------------------------
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
_GLUE_ARGS = {
    "g_count_game_frame": 0, "g_anim_frame_ids_update": 0, "g_entities_move_all": 0,
    "g_entities_move_groups_extra": 0, "g_entities_move_bigobj": 0,
    "g_entities_move_bigobj_parts": 0, "g_enemy_bombs_move": 0, "g_entities_publish_all": 0,
    "g_entities_publish_facing_groups": 0, "g_entities_publish_bigobj_group": 0,
    "g_entities_publish_plain_groups": 0, "g_entities_publish_anim_groups": 0,
    "g_entities_publish_last_groups": 0, "g_entity_publish_group_a4": 0,
    "g_bigobj_extra_parts_publish": 0, "g_entity_hide_under_bigobj": 0,
    "g_bigobj_overlap_depth_update": 0, "g_items_move_all": 0, "g_items_publish": 0,
    "g_difficulty_apply_fire_rates": 0, "g_items_pickup_check": 0,
    "g_entity_move": 1, "g_entities_move_group4": 1, "g_entities_move_one_group": 1,
    "g_entity_hide_test": 1, "g_entity_hide_under_bigobj_group": 1, "g_item_fall_step": 1,
    "g_item_drop_step": 1, "g_item_path_step": 1, "g_item_pickup_award": 1,
    "g_entity_publish_group_plain": 2, "g_entity_publish_group_offset": 2,
    "g_sprite_hitbox_test": 2,
    "g_bigobj_depth_test": 2,
    "g_enemy_bomb_drop": 3, "g_entity_publish_group_facing": 3, "g_entity_publish_anim": 3,
    "g_entity_publish_group_last": 3,
    "g_item_drop_if_formation_cleared": 5,   # ...the fifth being the X flag its score chain adds
}
for _name, _extra in _GLUE_ARGS.items():
    _fn = getattr(harness._lib, _name)
    _fn.argtypes = [_IMAGE] + [ctypes.c_uint32] * _extra
    _fn.restype = None
# The one glue here with an answer of its own: the X flag the bonus arm's score chain leaves.
harness._lib.g_item_drop_if_formation_cleared.restype = ctypes.c_uint


def _case(entry, regs, glue, stop_pc=0, poison=False, note=""):
    diffs, _info = differential(entry, regs, glue, stop_pc=stop_pc, poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


# ---- record builders -----------------------------------------------------------------------------
_ENTITY_FIELDS = {
    "x": (ENTITY_X, 2), "y": (ENTITY_Y, 2), "frame_offset": (ENTITY_FRAME_OFFSET, 2),
    "draw_layer": (ENTITY_DRAW_LAYER, 2), "dx": (ENTITY_DX, 2), "dy": (ENTITY_DY, 2),
    "countdown": (ENTITY_STEP_COUNTDOWN, 2), "active": (ENTITY_ACTIVE, 2),
    "dying": (ENTITY_DYING, 2), "base_frame": (ENTITY_BASE_FRAME, 2),
    "hit_points": (ENTITY_HIT_POINTS, 2), "aim_changed": (ENTITY_AIM_CHANGED, 2),
    "facing": (ENTITY_FACING, 2), "depth_select": (ENTITY_DEPTH_SELECT, 2),
    "path_select": (ENTITY_PATH_SELECT, 2), "path_cursor": (ENTITY_PATH_CURSOR, 2),
    "firing": (ENTITY_FIRING, 2), "frame_bump": (ENTITY_FRAME_BUMP, 2),
    "anim_timer": (ENTITY_ANIM_TIMER, 2), "kind": (ENTITY_KIND, 2),
    "has_dropped": (ENTITY_HAS_DROPPED, 2), "hidden": (ENTITY_HIDDEN_UNDER_BIGOBJ, 2),
    "script_base": (ENTITY_SCRIPT_BASE, 4), "script_cursor": (ENTITY_SCRIPT_CURSOR, 4),
}


def entity_record(**fields):
    """A whole 58-byte entity record. Everything not named is zero, as `clear_actor_arrays` leaves it."""
    record = bytearray(ENTITY_STRIDE)
    for name, value in fields.items():
        offset, width = _ENTITY_FIELDS[name]
        record[offset:offset + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, "big")
    return bytes(record)


def move_script(*steps, terminate=True):
    """8-byte {dx, dy, duration, frame} records, optionally closed with the 999 terminator."""
    out = bytearray()
    for dx, dy, duration, frame in steps:
        for value in (dx, dy, duration, frame):
            out += (value & 0xffff).to_bytes(2, "big")
    if terminate:
        out += SCRIPT_TERMINATOR.to_bytes(2, "big") + bytes(MOVE_SCRIPT_BYTES - 2)
    return bytes(out)


def display_record(x=0, y=0, frame=0, active=0):
    return ((x & 0xffff).to_bytes(2, "big") + (y & 0xffff).to_bytes(2, "big")
            + bytes([frame & 0xff, active & 0xff]))


def item_record(x=0, y=0, cursor=0, active=0):
    return ((x & 0xffff).to_bytes(2, "big") + (y & 0xffff).to_bytes(2, "big")
            + (cursor & 0xffffffff).to_bytes(4, "big") + (active & 0xffff).to_bytes(2, "big"))


def word(value):
    return (value & 0xffff).to_bytes(2, "big")


def group_slot(group, index=0):
    """The arena address the GAME'S OWN table holds — read out of the loaded image, not assumed."""
    base = group + index * ENTITY_GROUP_PTR_BYTES
    return int.from_bytes(harness.BASE_IMAGE[base:base + ENTITY_GROUP_PTR_BYTES], "big")


def group_pokes(group, records, count=ENTITY_GROUP_SLOTS):
    """Poke `records` into the arena slots `group` names. A short list leaves the rest zeroed."""
    pokes = {}
    for index in range(count):
        pokes[group_slot(group, index)] = (records[index] if index < len(records)
                                           else entity_record())
    return pokes


# ---- the staged worlds ---------------------------------------------------------------------------
A_spawn_script_ptr, A_spawn_script_cursor, A_scroll_pos = 0x17770, 0x17754, 0x17758
A_level1_script = 0x1b350
ENTRY_SPAWN_SCRIPT_STEP = 0x12fc4
SPAWN_STEPS = 6000            # scroll_pos 0..0x2ee0, which is 60 of level 1's spawn records
SPAWN_MAX_INSNS = 200_000


# ==================================================================================================
# count_game_frame @ 0x11654 and anim_frame_ids_update @ 0x119fc
# ==================================================================================================
@pytest.mark.parametrize("counter", (0, 1, 0xffff, 0x10000, 0xfffffffe, 0xffffffff))
def test_count_game_frame_is_a_longword_increment(counter):
    """Including the wrap: the counter is a LONG, so 0xffffffff goes to 0 and not to 0x10000."""
    _case(ENTRY_COUNT_GAME_FRAME,
          {"_pokes": {A_frame_counter: counter.to_bytes(4, "big")}},
          lambda lib, buf: lib.g_count_game_frame(buf), note=f"counter={counter:#x}")


_ANIM_IDS = (A_anim_frame_a, A_anim_frame_b, A_anim_frame_item0,
             A_anim_frame_item1, A_anim_frame_item3, A_anim_frame_bomb)


def _anim_table_pokes(rng):
    """Distinctive bytes over each id AND the little table behind it, so a wrong phase shows.

    The shipped tables carry real sprite ids, several of which repeat — two phases of one id can hold
    the same byte, and a case run only over the shipped data would agree with a mask that read the
    wrong bit. Seeding all five bytes of each with distinct values is what separates them.
    """
    pokes = {}
    for identifier in _ANIM_IDS:
        pokes[identifier] = bytes(rng.randrange(256) for _ in range(1 + ANIM_PHASE_MASK_3 + 1))
    return pokes


@pytest.mark.parametrize("counter", (0, 1, 2, 3, 4, 5, 6, 7, 0xfffffffd, 0xffffffff))
def test_anim_frame_ids_take_their_phase_from_the_frame_counter(counter):
    rng = random.Random(counter)
    pokes = _anim_table_pokes(rng)
    pokes[A_frame_counter] = counter.to_bytes(4, "big")
    _case(ENTRY_ANIM_FRAME_IDS_UPDATE, {"_pokes": pokes},
          lambda lib, buf: lib.g_anim_frame_ids_update(buf), note=f"counter={counter:#x}")


def test_anim_frame_ids_over_the_shipped_tables():
    """The same routine over the game's OWN five-byte tables, with nothing seeded."""
    for counter in range(8):
        _case(ENTRY_ANIM_FRAME_IDS_UPDATE,
              {"_pokes": {A_frame_counter: counter.to_bytes(4, "big")}},
              lambda lib, buf: lib.g_anim_frame_ids_update(buf), note=f"counter={counter}")


# ==================================================================================================
# entity_move @ 0x12e9e — the script interpreter and the death path
# ==================================================================================================
def _move_case(record, extra_pokes=None, poison=False, note=""):
    pokes = {SCRATCH_ENTITY: record}
    pokes.update(extra_pokes or {})
    _case(ENTRY_ENTITY_MOVE, {"a0": SCRATCH_ENTITY, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_move(buf, SCRATCH_ENTITY), poison=poison, note=note)


def test_move_skips_an_inactive_slot():
    """`tst.w 14(a0) / beq` returns before anything is read, whatever the rest of the record says."""
    _move_case(entity_record(active=0, dx=5, dy=7, countdown=1, dying=1), note="inactive")


@pytest.mark.parametrize("dx,dy", ((0, 0), (1, 1), (-1, -1), (0x7fff, 0x7fff), (0x8000, 0x8000)))
def test_move_script_mode_steps_x_and_y(dx, dy):
    """x += dx and y += dy, as WORD adds that wrap rather than as arithmetic that saturates."""
    _move_case(entity_record(active=1, x=0xfff0, y=0x0010, dx=dx, dy=dy, countdown=5),
               note=f"dx={dx:#x} dy={dy:#x}")


@pytest.mark.parametrize("countdown", (0, 1, 2, 0x8000, 0xffff))
def test_move_steps_the_script_at_zero(countdown):
    """The countdown is decremented every frame and the script steps only when it reaches EXACTLY 0.

    A countdown of 0 therefore wraps to 0xffff and runs for another 65,535 frames, which is the
    behaviour a `subq`-and-test-for-negative reading would get wrong.
    """
    script = move_script((3, -4, 9, 0x22), (5, 6, 7, 0x33))
    _move_case(entity_record(active=1, x=100, y=50, dx=1, dy=1, countdown=countdown,
                             script_base=SCRATCH_SCRIPT, script_cursor=0),
               {SCRATCH_SCRIPT: script}, note=f"countdown={countdown}")


def test_move_deactivates_at_the_script_terminator():
    """999 in the record's dx word ends the script and clears ENTITY_ACTIVE."""
    _move_case(entity_record(active=1, countdown=1,
                             script_base=SCRATCH_SCRIPT, script_cursor=0),
               {SCRATCH_SCRIPT: move_script((1, 2, 3, 4))}, poison=True, note="terminator")


@pytest.mark.parametrize("cursor", (0, MOVE_SCRIPT_BYTES, 2 * MOVE_SCRIPT_BYTES))
def test_move_advances_the_cursor_by_one_record(cursor):
    script = move_script((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16))
    _move_case(entity_record(active=1, countdown=1, script_base=SCRATCH_SCRIPT,
                             script_cursor=cursor),
               {SCRATCH_SCRIPT: script}, note=f"cursor={cursor}")


@pytest.mark.parametrize("path_select", range(ENTITY_PATH_TABLES))
@pytest.mark.parametrize("path_cursor", (0, 1, 2, 5))
def test_move_dying_walks_the_death_path(path_select, path_cursor):
    """All three tables `entity_path_tbl_ptrs` names, over the game's OWN frame words."""
    _move_case(entity_record(active=1, dying=1, x=80, y=60, base_frame=0x40,
                             path_select=path_select, path_cursor=path_cursor),
               note=f"select={path_select} cursor={path_cursor}")


# Cursors whose `cursor * 2` has bit 15 set, so `adda.w d0,a1` SIGN-EXTENDS and the step address
# lands BELOW the table. 0x4000 is the first such cursor and 0x7fff the last before the doubled word
# wraps back to a small positive one; 0x6000 sits between them. The game's own cursor starts at 0
# and is bumped once a frame until the table's negative word retires the entity, so none of these is
# reachable — they exist to separate the sign-extension from a zero-extension.
DEATH_CURSORS_THAT_WALK_BACKWARDS = (0x4000, 0x6000, 0x7fff)


@pytest.mark.parametrize("path_select", range(ENTITY_PATH_TABLES))
@pytest.mark.parametrize("path_cursor", DEATH_CURSORS_THAT_WALK_BACKWARDS)
def test_a_death_cursor_past_0x3fff_walks_BACKWARDS_off_the_table(path_select, path_cursor):
    """CONTRACT COVERAGE, NOT GAME COVERAGE, and ../STATUS.md says so.

    `move.w 36(a0),d0 / add.w d0,d0 / adda.w d0,a1` @ 0x12ec8: the index is doubled AS A WORD and
    then added to the table pointer through `adda.w`, which SIGN-EXTENDS. A cursor of 0x4000 doubles
    to 0x8000 and therefore subtracts 0x8000 from the table — the step is read 32 KB below it, out
    of the program's own code, and whatever word is there decides the arm. All three tables land
    inside the image, so both sides read the same bytes and the difference is real behaviour.

    A candidate that zero-extended the index would read 32 KB ABOVE the table instead, which for
    these three tables is off the end of the program.
    """
    _move_case(entity_record(active=1, dying=1, x=80, y=60, base_frame=0x40,
                             path_select=path_select, path_cursor=path_cursor),
               poison=True, note=f"select={path_select} cursor={path_cursor:#x}")


@pytest.mark.parametrize("kind", (0, ENTITY_KIND_BOMBER))
def test_move_dying_ends_at_the_negative_word(kind):
    """The tables end on a NEGATIVE word, not on a sentinel; a bomber also has its drop flag reset.

    Cursor 0x7f is past the end of all three shipped tables, so the walk lands on a negative word
    however long the table is.
    """
    _move_case(entity_record(active=1, dying=1, kind=kind, has_dropped=SCC_TRUE << 8,
                             path_select=1, path_cursor=0x7f),
               poison=True, note=f"kind={kind}")


@pytest.mark.parametrize("has_dropped", (0, 1, SCC_TRUE << 8))
def test_a_bomber_drops_exactly_once(has_dropped):
    """Kind 4 drops a bomb on its way down, and ENTITY_HAS_DROPPED is what stops the second."""
    _move_case(entity_record(active=1, dying=1, x=0x50, y=0x30, base_frame=0x40,
                             kind=ENTITY_KIND_BOMBER, has_dropped=has_dropped,
                             path_select=1, path_cursor=0),
               poison=True, note=f"has_dropped={has_dropped:#x}")


@pytest.mark.parametrize("kind", (0, 3, ENTITY_KIND_BOMBER, 5, 0xffff))
def test_only_kind_4_drops_a_bomb(kind):
    _move_case(entity_record(active=1, dying=1, x=0x50, y=0x30, kind=kind,
                             path_select=2, path_cursor=0),
               note=f"kind={kind:#x}")


# ==================================================================================================
# enemy_bomb_drop @ 0x12f2e
# ==================================================================================================
def _bomb_slot_pokes(occupied):
    """The first ENEMY_BOMB_SLOTS display records, `occupied` of them already in use."""
    records = b"".join(display_record(x=slot, y=slot, frame=slot,
                                      active=DISPLAY_ACTIVE_ON_TOP if slot in occupied else 0)
                       for slot in range(ENEMY_BOMB_SLOTS))
    return {A_display_list: records}


@pytest.mark.parametrize("first_free", range(ENEMY_BOMB_SLOTS + 1))
def test_bomb_takes_the_first_free_display_record(first_free):
    """Every position of the first free slot, INCLUDING the last one and none at all.

    `first_free == ENEMY_BOMB_SLOTS - 1` is the bug src/entity.c reproduces: the cursor reaches the
    slot count on the same iteration that finds the record, and the routine leaves without writing
    it. `first_free == ENEMY_BOMB_SLOTS` is a full list.
    """
    occupied = set(range(ENEMY_BOMB_SLOTS)) - {first_free}
    pokes = _bomb_slot_pokes(occupied)
    pokes[SCRATCH_ENTITY] = entity_record(active=1)
    _case(ENTRY_ENEMY_BOMB_DROP,
          {"a0": SCRATCH_ENTITY, "d0": 0x0123, "d1": 0x0045, "_pokes": pokes},
          lambda lib, buf: lib.g_enemy_bomb_drop(buf, SCRATCH_ENTITY, 0x0123, 0x0045),
          poison=True, note=f"first_free={first_free}")


@pytest.mark.parametrize("x,y", ((0, 0), (0xffff, 0xffff), (0x1234, 0x00c8), (0x100, 0x50)))
def test_bomb_position_comes_from_the_registers(x, y):
    pokes = _bomb_slot_pokes(set())
    pokes[SCRATCH_ENTITY] = entity_record(active=1)
    pokes[A_anim_frame_bomb] = bytes([0x5a])
    _case(ENTRY_ENEMY_BOMB_DROP,
          {"a0": SCRATCH_ENTITY, "d0": x, "d1": y, "_pokes": pokes},
          lambda lib, buf: lib.g_enemy_bomb_drop(buf, SCRATCH_ENTITY, x, y),
          note=f"x={x:#x} y={y:#x}")


def test_the_drop_flag_is_set_as_a_BYTE():
    """`st 46(a0)` writes 0xff into the HIGH byte of a word whose low byte survives — so a record
    whose +47 already holds a value keeps it, which a word store would destroy."""
    pokes = _bomb_slot_pokes(set())
    record = bytearray(entity_record(active=1))
    record[ENTITY_HAS_DROPPED + 1] = 0x5c
    pokes[SCRATCH_ENTITY] = bytes(record)
    _case(ENTRY_ENEMY_BOMB_DROP,
          {"a0": SCRATCH_ENTITY, "d0": 1, "d1": 2, "_pokes": pokes},
          lambda lib, buf: lib.g_enemy_bomb_drop(buf, SCRATCH_ENTITY, 1, 2), poison=True)


# ==================================================================================================
# enemy_bombs_move @ 0x1184e
# ==================================================================================================
@pytest.mark.parametrize("y", (0, 1, ENTITY_RETIRE_Y - ENEMY_BOMB_DY - 1,
                               ENTITY_RETIRE_Y - ENEMY_BOMB_DY, ENTITY_RETIRE_Y - 1,
                               ENTITY_RETIRE_Y, 0x8000, 0xffff))
def test_enemy_bombs_fall_and_retire_at_the_bottom(y):
    """The retire test is SIGNED, so a wrapped y is above the screen rather than past the bottom."""
    records = b"".join(display_record(x=0x10 * slot, y=y + slot, frame=slot,
                                      active=DISPLAY_ACTIVE_UNDER_SCENERY if slot % 2 else 0)
                       for slot in range(ENEMY_BOMB_SLOTS))
    _case(ENTRY_ENEMY_BOMBS_MOVE,
          {"_pokes": {A_display_list: records, A_anim_frame_bomb: bytes([0x77])}},
          lambda lib, buf: lib.g_enemy_bombs_move(buf), poison=True, note=f"y={y:#x}")


def test_the_bomb_frame_is_written_to_every_record_active_or_not():
    """The `move.b anim_frame_bomb,4(a0)` is outside the retire branch and outside any active test,
    so all sixteen records take the frame even when none of them holds a bomb."""
    records = b"".join(display_record(active=0) for _ in range(ENEMY_BOMB_SLOTS))
    _case(ENTRY_ENEMY_BOMBS_MOVE,
          {"_pokes": {A_display_list: records, A_anim_frame_bomb: bytes([0xbe])}},
          lambda lib, buf: lib.g_enemy_bombs_move(buf), poison=True)


# ==================================================================================================
# The power-up items
# ==================================================================================================
def _item_case(entry, glue_name, record, extra_pokes=None, poison=False, note=""):
    pokes = {SCRATCH_ITEM: record}
    pokes.update(extra_pokes or {})
    _case(entry, {"a0": SCRATCH_ITEM, "_pokes": pokes},
          lambda lib, buf: getattr(lib, glue_name)(buf, SCRATCH_ITEM), poison=poison, note=note)


@pytest.mark.parametrize("y", (0, ENTITY_RETIRE_Y - ENEMY_BOMB_DY - 1,
                               ENTITY_RETIRE_Y - ENEMY_BOMB_DY, ENTITY_RETIRE_Y, 0xffff))
@pytest.mark.parametrize("active", (0, 1, SCC_TRUE << 8))
def test_item_drop_step(y, active):
    _item_case(ENTRY_ITEM_DROP_STEP, "g_item_drop_step",
               item_record(x=0x40, y=y, active=active), poison=True,
               note=f"y={y:#x} active={active:#x}")


@pytest.mark.parametrize("cursor", (0, 1, 2, 0x32, 0x80000000, 0xffffffff))
@pytest.mark.parametrize("active", (0, 1))
def test_item_fall_step_counts_a_longword_down_to_its_sign(cursor, active):
    """The lifetime is a LONG and the retire test is its sign after the decrement: 0 goes to -1 and
    retires, 0x80000000 is already negative and retires at once."""
    _item_case(ENTRY_ITEM_FALL_STEP, "g_item_fall_step",
               item_record(x=0x40, y=0x40, cursor=cursor, active=active), poison=True,
               note=f"cursor={cursor:#x} active={active}")


@pytest.mark.parametrize("cursor", (0, ITEM_PATH_STEP_BYTES, 8 * ITEM_PATH_STEP_BYTES, 0x40, 0x80))
@pytest.mark.parametrize("y", (0, ENTITY_RETIRE_Y - 4, ENTITY_RETIRE_Y))
def test_item_path_step_walks_the_flight_path(cursor, y):
    """Over the game's OWN A_item_flight_path, whose terminator REWINDS the cursor rather than
    retiring the item — the one item motion that never ends by itself."""
    _item_case(ENTRY_ITEM_PATH_STEP, "g_item_path_step",
               item_record(x=0x60, y=y, cursor=cursor, active=1), poison=True,
               note=f"cursor={cursor:#x} y={y:#x}")


def test_item_path_step_is_skipped_when_inactive():
    _item_case(ENTRY_ITEM_PATH_STEP, "g_item_path_step",
               item_record(x=0x60, y=0x60, cursor=0x1000, active=0))


def _items_pokes(weapon, life, extra, bomb):
    return {A_item_weapon: weapon, A_item_life: life, A_item_extra: extra, A_item_bomb: bomb}


@pytest.mark.parametrize("live", range(1 << 4))
def test_items_move_all_drives_the_four_records(live):
    """Every combination of the four items being live, so the routine's four different step
    routines are each exercised alone and together."""
    pokes = _items_pokes(item_record(x=0x30, y=0x40, cursor=0x10, active=live & 1),
                         item_record(x=0x50, y=0x60, cursor=0x20, active=(live >> 1) & 1),
                         item_record(x=0x70, y=0x80, cursor=3, active=(live >> 2) & 1),
                         item_record(x=0x90, y=0xc4, active=(live >> 3) & 1))
    _case(ENTRY_ITEMS_MOVE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_items_move_all(buf), poison=True, note=f"live={live:#x}")


@pytest.mark.parametrize("live", range(1 << 4))
def test_items_publish_pairs_each_item_with_its_own_record(live):
    """The order is weapon, extra, life, bomb — neither the items' address order nor the display
    records'. Each frame comes from a different cycling id but the bonus item's, which is a literal,
    and the bomb is the one item published into render pass A."""
    pokes = _items_pokes(item_record(x=0x31, y=0x41, active=live & 1),
                         item_record(x=0x51, y=0x61, active=(live >> 1) & 1),
                         item_record(x=0x71, y=0x81, active=(live >> 2) & 1),
                         item_record(x=0x91, y=0xa1, active=(live >> 3) & 1))
    pokes[A_anim_frame_item0] = bytes([0x11])
    pokes[A_anim_frame_item1] = bytes([0x22])
    pokes[A_anim_frame_item3] = bytes([0x33])
    for record in (A_dl_item_0, A_dl_item_1, A_dl_item_2, A_dl_item_3):
        pokes[record] = display_record(x=0xdead, y=0xbeef, frame=0x99, active=0x77)
    _case(ENTRY_ITEMS_PUBLISH, {"_pokes": pokes},
          lambda lib, buf: lib.g_items_publish(buf), poison=True, note=f"live={live:#x}")


# ==================================================================================================
# The pickup: sprite_hitbox_test / items_pickup_check / item_pickup_award
# ==================================================================================================
PICKUP_FRAME = 0x10          # the sprite-bank record a case seeds its player box into


def _hitbox_pokes(player_x, player_y, draw_dx=0, draw_dy=0, hit_dx=0, hit_dy=0, w=0x20, h=0x18):
    record = A_sprite_bank + PICKUP_FRAME * SPRITE_RECORD_BYTES
    pokes = {
        A_player: word(player_x) + word(player_y) + bytes([PICKUP_FRAME]),
        record + SPRITE_REC_DRAW_DX: word(draw_dx) + word(draw_dy),
        record + SPRITE_REC_HIT_DX: word(hit_dx) + word(hit_dy) + word(w) + word(h),
    }
    return pokes


# 0x31 by x and 0x21 by y are the ITEM_PICKUP_BOX edge itself: the item span's far end landing
# exactly one pixel past the player box's near corner. Without them the box SIZE is unpinned —
# a 0x0f box agrees with a 0x10 one on every other value here (measured: the ITEM_PICKUP_BOX
# 0x10 -> 0x0f mutant survived the whole battery until these two were added).
@pytest.mark.parametrize("item_x", (0, 0x30, 0x31, 0x32, 0x3f, 0x40, 0x41, 0x50, 0x5f, 0x60,
                                    0x61, 0x100))
@pytest.mark.parametrize("item_y", (0, 0x20, 0x21, 0x22, 0x2f, 0x30, 0x31, 0x40, 0x47, 0x48,
                                    0x49, 0x100))
def test_hitbox_edges_on_both_axes(item_x, item_y):
    """The player's box is [0x40, 0x60) by x and [0x30, 0x48) by y; the item's is a fixed 0x10
    square at its own corner. One step either side of every edge of both."""
    pokes = _hitbox_pokes(player_x=0x30, player_y=0x20, draw_dx=0x08, draw_dy=0x04,
                          hit_dx=0x08, hit_dy=0x0c, w=0x20, h=0x18)
    pokes[SCRATCH_ITEM] = item_record(x=item_x, y=item_y, active=1)
    _case(ENTRY_SPRITE_HITBOX_TEST,
          {"a0": SCRATCH_ITEM, "d6": ITEM_KIND_WEAPON, "_pokes": pokes},
          lambda lib, buf: lib.g_sprite_hitbox_test(buf, SCRATCH_ITEM, ITEM_KIND_WEAPON),
          poison=True, note=f"item=({item_x:#x},{item_y:#x})")


def test_the_hitbox_adds_the_draw_offset_and_the_box_offset_separately():
    """`add.w 8(a4),d2 / add.w 12(a4),d2` — two fields, not one. A case that put the whole offset in
    either field alone would agree with a candidate that read only that one."""
    for draw, hit in ((0x20, 0), (0, 0x20), (0x10, 0x10), (-0x10, 0x30)):
        pokes = _hitbox_pokes(player_x=0x40, player_y=0x40, draw_dx=draw, draw_dy=draw,
                              hit_dx=hit, hit_dy=hit, w=4, h=4)
        pokes[SCRATCH_ITEM] = item_record(x=0x58, y=0x58, active=1)
        _case(ENTRY_SPRITE_HITBOX_TEST,
              {"a0": SCRATCH_ITEM, "d6": ITEM_KIND_LIFE, "_pokes": pokes},
              lambda lib, buf: lib.g_sprite_hitbox_test(buf, SCRATCH_ITEM, ITEM_KIND_LIFE),
              poison=True, note=f"draw={draw:#x} hit={hit:#x}")


@pytest.mark.parametrize("frame", (0, 1, 0x7f, 0x80, 0xff))
def test_the_player_frame_indexes_the_sprite_bank_as_an_unsigned_byte(frame):
    """`clr.l d0 / move.b 4(a1),d0 / muls.w #$14,d0` — frame 0x80 is record 128, not record -128."""
    pokes = {A_player: word(0x40) + word(0x40) + bytes([frame]),
             SCRATCH_ITEM: item_record(x=0x44, y=0x44, active=1)}
    _case(ENTRY_SPRITE_HITBOX_TEST,
          {"a0": SCRATCH_ITEM, "d6": ITEM_KIND_BOMB, "_pokes": pokes},
          lambda lib, buf: lib.g_sprite_hitbox_test(buf, SCRATCH_ITEM, ITEM_KIND_BOMB),
          poison=True, note=f"frame={frame:#x}")


@pytest.mark.parametrize("live", range(1 << 3))
@pytest.mark.parametrize("hit", (False, True))
def test_items_pickup_check_walks_weapon_then_bomb_then_life(live, hit):
    """The three items in the order the routine tests them, each present or not, and the whole grid
    run once with the player over them and once well away."""
    pokes = _hitbox_pokes(player_x=0x40, player_y=0x40, w=0x20, h=0x20)
    away = 0 if hit else 0x180
    pokes[A_item_weapon] = item_record(x=0x44 + away, y=0x44, active=live & 1)
    pokes[A_item_bomb] = item_record(x=0x46 + away, y=0x46, active=(live >> 1) & 1)
    pokes[A_item_life] = item_record(x=0x48 + away, y=0x48, active=(live >> 2) & 1)
    _case(ENTRY_ITEMS_PICKUP_CHECK, {"_pokes": pokes},
          lambda lib, buf: lib.g_items_pickup_check(buf),
          poison=True, note=f"live={live:#x} hit={hit}")


@pytest.mark.parametrize("kind", (ITEM_KIND_WEAPON, ITEM_KIND_BOMB, ITEM_KIND_LIFE, 3, 0xffff))
@pytest.mark.parametrize("counter", (0, 1, 3, 4, 5, 6, 7, 8, 0xffff))
def test_item_pickup_award_caps_each_counter_its_own_way(kind, counter):
    """Weapon and bomb stop on `beq` — exactly at the limit — while lives stop on a signed `bgt`, so
    lives settle one HIGHER than the number in the instruction and a counter already above the limit
    behaves differently in the two families."""
    pokes = {A_bombs: word(counter), A_lives: word(counter), A_weapon_level: word(counter)}
    _case(ENTRY_ITEM_PICKUP_AWARD, {"d6": kind, "_pokes": pokes},
          lambda lib, buf: lib.g_item_pickup_award(buf, kind), poison=True,
          note=f"kind={kind:#x} counter={counter:#x}")


# ==================================================================================================
# item_drop_if_formation_cleared @ 0x121fe
# ==================================================================================================
# The score every case below starts from. Its middle BCD byte is 0x99, so adding 1000 carries into
# the top byte and an incoming X of 1 carries again — the digits the bonus arm writes therefore
# differ from the ones it was handed, and the chain's outgoing X depends on the incoming one.
_DROP_CASE_SCORE = bytes((0x00, 0x99, 0x00))


def _drop_pokes(group, survivor=None):
    """A cleared seven-slot formation, optionally with one live survivor at `survivor`, plus every
    destination the routine can write: the three item records, the pickup flag and the score."""
    records = [entity_record(active=1, dying=1) for _ in range(ENTITY_GROUP_A_SLOTS)]
    if survivor is not None:
        records[survivor] = entity_record(active=1, dying=0)
    pokes = group_pokes(group, records, ENTITY_GROUP_A_SLOTS)
    pokes[A_item_weapon] = item_record()
    pokes[A_item_life] = item_record()
    pokes[A_item_extra] = item_record()
    pokes[A_item_pickup_pending] = word(0)
    pokes[A_score_bcd] = _DROP_CASE_SCORE
    return pokes


@pytest.mark.parametrize("kind", (ITEM_KIND_WEAPON, ITEM_KIND_BOMB, ITEM_KIND_LIFE, 7))
@pytest.mark.parametrize("survivor", (None,) + tuple(range(ENTITY_GROUP_A_SLOTS)))
def test_item_drop_needs_every_slot_of_the_formation_gone(kind, survivor):
    """One survivor at each of the seven positions aborts the drop; a survivor that is already DYING
    does not, which is what lets the last kill of a squadron reward it.

    Diffed to the routine's own `rts`, the bonus arm's `bsr score_add_1000` included — so the BOMB
    column of this sweep is also what pins that the award fires on exactly the cleared formations."""
    pokes = _drop_pokes(A_entity_group_a0, survivor)
    _case(ENTRY_ITEM_DROP_IF_FORMATION_CLEARED,
          {"a0": A_entity_group_a0, "d0": 0x0064, "d1": 0x0032, "d2": kind, "_pokes": pokes},
          lambda lib, buf: lib.g_item_drop_if_formation_cleared(buf, A_entity_group_a0,
                                                                0x0064, 0x0032, kind,
                                                                abi.EXTEND_CLEAR),
          poison=True, note=f"kind={kind} survivor={survivor}")


# The routine takes its x in D0, so the X setter borrows a register the routine never reads: it
# writes D7 as its own loop counter (`move.w #$6,d7` @ 0x12202) before reading anything.
_DROP_EXTEND_SCRATCH = "d7"


@pytest.mark.parametrize("kind", (ITEM_KIND_WEAPON, ITEM_KIND_BOMB, ITEM_KIND_LIFE))
@pytest.mark.parametrize("extend_in", abi.BOTH_EXTENDS)
def test_the_bonus_arm_threads_the_X_flag_through_the_score_chain(kind, extend_in):
    """The seam this routine used to stop at, driven from both sides.

    `item_drop_if_formation_cleared` ends its BOMB arm in `score_add_1000`, whose first `abcd` adds
    the caller's X, and its own exit (`movem.l (a7)+` then `rts`) writes no condition code — so the
    flag is an argument on that arm and an answer on every arm. The two arms that never reach the
    chain must hand back the flag unchanged, which is the other half of what this compares."""
    group = A_entity_group_a0
    pokes = _drop_pokes(group)
    pokes.update(abi.extend_call_pokes(ENTRY_ITEM_DROP_IF_FORMATION_CLEARED, extend_in,
                                       scratch=_DROP_EXTEND_SCRATCH))
    reported = {}
    diffs, info = differential(
        abi.STUB, {"a0": group, "d0": 0x0064, "d1": 0x0032, "d2": kind, "_pokes": pokes},
        lambda lib, buf: reported.setdefault(
            "x", lib.g_item_drop_if_formation_cleared(buf, group, 0x0064, 0x0032, kind, extend_in)))
    assert not diffs, f"kind={kind} X_in={extend_in}\n{report(diffs)}"
    assert reported["x"] == abi.oracle_extend(info), (
        f"kind={kind} X_in={extend_in}: the oracle left X={abi.oracle_extend(info)} and the "
        f"reconstruction {reported['x']}")


def test_the_drop_sets_its_flags_as_BYTES():
    """`st 8(a0)` and `st $176c2` write the high byte of a word, so a low byte already set survives.
    A word store would wipe it, and the whole arena being zero is what would hide that."""
    records = [entity_record(active=0) for _ in range(ENTITY_GROUP_A_SLOTS)]
    pokes = group_pokes(A_entity_group_a1, records, ENTITY_GROUP_A_SLOTS)
    pokes[A_item_weapon] = item_record(active=0x0055)
    pokes[A_item_pickup_pending] = word(0x0066)
    _case(ENTRY_ITEM_DROP_IF_FORMATION_CLEARED,
          {"a0": A_entity_group_a1, "d0": 1, "d1": 2, "d2": ITEM_KIND_WEAPON, "_pokes": pokes},
          lambda lib, buf: lib.g_item_drop_if_formation_cleared(buf, A_entity_group_a1, 1, 2,
                                                                ITEM_KIND_WEAPON,
                                                                abi.EXTEND_CLEAR), poison=True)


# ==================================================================================================
# difficulty_apply_fire_rates @ 0x12cc8 — a SLICE, since the routine falls into start_level
# ==================================================================================================
def test_difficulty_writes_every_descriptor():
    """Diffed at the `bra.w start_level` the routine ends on. The descriptors are seeded away from
    the values it writes, so a descriptor the reconstruction skipped shows as a difference rather
    than as the number the shipped table already held."""
    seeded = {}
    for descriptor in (A_enemy_desc_00, 0x195a4, 0x195be, 0x195d8, 0x195f2, 0x1960c, 0x19626,
                       0x19640, 0x1965a, A_enemy_desc_12, 0x19742, A_enemy_desc_14):
        seeded[descriptor + ENEMY_DESC_FIRE_RELOAD] = word(0xa5a5)
        seeded[descriptor + ENEMY_DESC_HIT_POINTS] = word(0x5a5a)
    _case(ENTRY_DIFFICULTY_APPLY_FIRE_RATES, {"_pokes": seeded},
          lambda lib, buf: lib.g_difficulty_apply_fire_rates(buf),
          stop_pc=STOP_DIFFICULTY_TAIL, poison=True)


# ==================================================================================================
# The publishers
# ==================================================================================================
def _publish_records_poke(base, count):
    """Seed the display run with a pattern nothing writes, so a record left alone is visible."""
    return {base: b"".join(display_record(x=0x1111, y=0x2222, frame=0x33, active=0x44)
                           for _ in range(count))}


def _publish_entities(rng, count, dying_mask=0):
    return [entity_record(active=index != 0 or rng.random() < 0.9,
                          dying=1 if dying_mask & (1 << index) else 0,
                          x=0x40 + 0x10 * index, y=0x30 + 8 * index,
                          frame_offset=index, base_frame=0x20 + index,
                          facing=index % 12, draw_layer=(0xff00 | (index + 1)),
                          hidden=0, aim_changed=0x0100 * index, firing=0,
                          anim_timer=3, hit_points=5)
            for index in range(count)]


@pytest.mark.parametrize("dying_mask", range(1 << ENTITY_GROUP_SLOTS))
def test_publish_facing_frame_is_base_plus_facing(dying_mask):
    """Live: base + ENTITY_FACING. Dying: base + ENTITY_FRAME_OFFSET, at the descriptor's death
    offset. Every combination of the four slots being in either state."""
    rng = random.Random(dying_mask)
    pokes = group_pokes(A_entity_group_x0, _publish_entities(rng, ENTITY_GROUP_SLOTS, dying_mask))
    pokes.update(_publish_records_poke(A_dl_entity_x0, ENTITY_GROUP_SLOTS))
    pokes[A_enemy_desc_12 + ENEMY_DESC_DEATH_DX] = word(-6) + word(0x0c)
    _case(ENTRY_ENTITY_PUBLISH_GROUP_FACING,
          {"a0": A_entity_group_x0, "a1": A_dl_entity_x0, "a5": A_enemy_desc_12, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_facing(buf, A_entity_group_x0,
                                                             A_dl_entity_x0, A_enemy_desc_12),
          poison=True, note=f"dying_mask={dying_mask:#x}")


def test_publish_facing_dying_takes_the_death_offset():
    """The descriptor's +18/+20 are added to the RECORD's x and y, so a candidate that added them to
    the entity's own coordinates would leave the arena wrong as well as the record."""
    for dx, dy in ((0, 0), (1, 2), (-1, -2), (0x7fff, 0x8000)):
        records = [entity_record(active=1, dying=1, x=0x8000, y=0x7fff, base_frame=3,
                                 frame_offset=4, draw_layer=1)
                   for _ in range(ENTITY_GROUP_SLOTS)]
        pokes = group_pokes(A_entity_group_x0, records)
        pokes.update(_publish_records_poke(A_dl_entity_x0, ENTITY_GROUP_SLOTS))
        pokes[A_enemy_desc_12 + ENEMY_DESC_DEATH_DX] = word(dx) + word(dy)
        _case(ENTRY_ENTITY_PUBLISH_GROUP_FACING,
              {"a0": A_entity_group_x0, "a1": A_dl_entity_x0, "a5": A_enemy_desc_12,
               "_pokes": pokes},
              lambda lib, buf: lib.g_entity_publish_group_facing(buf, A_entity_group_x0,
                                                                 A_dl_entity_x0, A_enemy_desc_12),
              poison=True, note=f"death=({dx:#x},{dy:#x})")


@pytest.mark.parametrize("hidden_mask", range(1 << ENTITY_GROUP_SLOTS))
def test_publish_plain_frame_is_base_plus_offset(hidden_mask):
    """The only publisher that consults ENTITY_HIDDEN_UNDER_BIGOBJ, and it clears the record rather
    than skipping it — so a hidden entity leaves a ZEROED record, not the previous frame's."""
    rng = random.Random(hidden_mask)
    records = _publish_entities(rng, ENTITY_GROUP_SLOTS)
    records = [bytes(bytearray(record)[:ENTITY_HIDDEN_UNDER_BIGOBJ]
                     + bytearray(word(SCC_TRUE << 8 if hidden_mask & (1 << index) else 0))
                     + bytearray(record)[ENTITY_HIDDEN_UNDER_BIGOBJ + 2:])
               for index, record in enumerate(records)]
    pokes = group_pokes(A_entity_group_t0, records)
    pokes.update(_publish_records_poke(A_dl_entity_t0, ENTITY_GROUP_SLOTS))
    _case(ENTRY_ENTITY_PUBLISH_GROUP_PLAIN,
          {"a0": A_entity_group_t0, "a1": A_dl_entity_t0, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_plain(buf, A_entity_group_t0,
                                                            A_dl_entity_t0),
          poison=True, note=f"hidden_mask={hidden_mask:#x}")


@pytest.mark.parametrize("draw_layer", (0x0000, 0x0001, 0x00ff, 0xff00, 0xff01, 0xffff, 0x1234))
def test_publish_copies_the_low_byte_of_the_draw_layer(draw_layer):
    """`move.b 7(a2),5(a1)` — the LOW byte of ENTITY_DRAW_LAYER, which is the field ../names.txt's
    comment on 0x59984 has backwards. 0xff00 and 0x00ff separate the two readings."""
    records = [entity_record(active=1, draw_layer=draw_layer, x=0x20, y=0x20, base_frame=1)
               for _ in range(ENTITY_GROUP_SLOTS)]
    pokes = group_pokes(A_entity_group_t0, records)
    pokes.update(_publish_records_poke(A_dl_entity_t0, ENTITY_GROUP_SLOTS))
    _case(ENTRY_ENTITY_PUBLISH_GROUP_PLAIN,
          {"a0": A_entity_group_t0, "a1": A_dl_entity_t0, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_plain(buf, A_entity_group_t0,
                                                            A_dl_entity_t0),
          poison=True, note=f"draw_layer={draw_layer:#x}")


@pytest.mark.parametrize("frame_offset,base_frame",
                         ((0, 0), (1, 2), (0xff, 1), (0x100, 0x20), (0xffff, 1), (0x80, 0x80)))
def test_publish_frame_is_truncated_to_a_byte(frame_offset, base_frame):
    """The sum is a WORD add and only its low byte is stored, so 0x100 + 0x20 publishes 0x20."""
    records = [entity_record(active=1, draw_layer=1, frame_offset=frame_offset,
                             base_frame=base_frame) for _ in range(ENTITY_GROUP_SLOTS)]
    pokes = group_pokes(A_entity_group_t0, records)
    pokes.update(_publish_records_poke(A_dl_entity_t0, ENTITY_GROUP_SLOTS))
    _case(ENTRY_ENTITY_PUBLISH_GROUP_PLAIN,
          {"a0": A_entity_group_t0, "a1": A_dl_entity_t0, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_plain(buf, A_entity_group_t0,
                                                            A_dl_entity_t0),
          note=f"{frame_offset:#x}+{base_frame:#x}")


def _anim_case(record, desc_death=(0, 0), note="", poison=True):
    pokes = {group_slot(A_entity_group_pair): record}
    pokes.update(_publish_records_poke(A_dl_entity_pair, 1))
    pokes[A_enemy_desc_12 + ENEMY_DESC_DEATH_DX] = word(desc_death[0]) + word(desc_death[1])
    _case(ENTRY_ENTITY_PUBLISH_ANIM,
          {"a0": A_entity_group_pair, "a1": A_dl_entity_pair, "a5": A_enemy_desc_12,
           "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_anim(buf, A_entity_group_pair, A_dl_entity_pair,
                                                     A_enemy_desc_12),
          poison=poison, note=note)


@pytest.mark.parametrize("frame_bump", (0, 1, SCC_TRUE << 8))
@pytest.mark.parametrize("firing", (0, 1))
@pytest.mark.parametrize("anim_timer", (0, 1, 2))
def test_anim_frame_bump_is_one_shot(frame_bump, firing, anim_timer):
    """The latch wins over the firing timer, and BOTH arms clear it — so a hit flash shows for one
    published frame however the timer stands."""
    _anim_case(entity_record(active=1, draw_layer=1, x=0x30, y=0x30, base_frame=0x10,
                             frame_offset=2, frame_bump=frame_bump, firing=firing,
                             anim_timer=anim_timer, hit_points=5),
               note=f"bump={frame_bump:#x} firing={firing} timer={anim_timer}")


@pytest.mark.parametrize("period", (0, 1, 5, 0xffff))
def test_anim_timer_reloads_from_the_period(period):
    """ENTITY_ANIM_TIMER is reloaded from ENTITY_HIT_POINTS — the dual role include/entity.h names.
    A timer of 1 hits zero this frame and takes the period; a timer of 0 wraps to 0xffff instead."""
    for timer in (0, 1, 2):
        _anim_case(entity_record(active=1, draw_layer=1, base_frame=0x10, frame_offset=1,
                                 firing=1, anim_timer=timer, hit_points=period),
                   note=f"period={period:#x} timer={timer}")


def test_anim_dying_skips_the_animation_entirely():
    """A dying pair object takes the descriptor's death offset and NO frame bump, whatever its latch
    and timer say — so the timer is left standing rather than counted down."""
    for frame_bump, firing in ((0, 0), (SCC_TRUE << 8, 1), (0, 1)):
        _anim_case(entity_record(active=1, dying=1, draw_layer=1, x=0x30, y=0x30, base_frame=0x10,
                                 frame_offset=3, frame_bump=frame_bump, firing=firing,
                                 anim_timer=1, hit_points=9),
                   desc_death=(0x10, -0x10), note=f"bump={frame_bump:#x} firing={firing}")


def test_anim_inactive_clears_the_record():
    _anim_case(entity_record(active=0, x=0x30, y=0x30), poison=False, note="inactive")


@pytest.mark.parametrize("dying_mask", range(1 << ENTITY_GROUP_SLOTS))
def test_publish_group_offset_takes_the_entitys_own_death_offset(dying_mask):
    """The big object's parts offset by ENTITY +24/+26 — the two words `spawn_single_common` fills
    with an `st` and a facing — and not by any descriptor field."""
    rng = random.Random(dying_mask + 0x100)
    records = _publish_entities(rng, ENTITY_GROUP_SLOTS, dying_mask)
    pokes = group_pokes(A_entity_group_bigobj, records)
    pokes.update(_publish_records_poke(A_dl_entity_bigobj, ENTITY_GROUP_SLOTS))
    _case(ENTRY_ENTITY_PUBLISH_GROUP_OFFSET,
          {"a0": A_entity_group_bigobj, "a1": A_dl_entity_bigobj, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_offset(buf, A_entity_group_bigobj,
                                                             A_dl_entity_bigobj),
          poison=True, note=f"dying_mask={dying_mask:#x}")


@pytest.mark.parametrize("dying_mask", (0, 1, 0x40, 0x2a, 0x7f))
def test_publish_group_last_walks_seven_slots(dying_mask):
    """ENTITY_GROUP_A_SLOTS, not four: a count of four would leave the last three records untouched
    and the seeded pattern is what shows that."""
    rng = random.Random(dying_mask + 0x200)
    records = _publish_entities(rng, ENTITY_GROUP_A_SLOTS, dying_mask)
    pokes = group_pokes(A_entity_group_a0, records, ENTITY_GROUP_A_SLOTS)
    pokes.update(_publish_records_poke(A_dl_entity_a0, ENTITY_GROUP_A_SLOTS))
    pokes[A_enemy_desc_00 + ENEMY_DESC_DEATH_DX] = word(0x0a) + word(0x0c)
    _case(ENTRY_ENTITY_PUBLISH_GROUP_LAST,
          {"a0": A_entity_group_a0, "a1": A_dl_entity_a0, "a5": A_enemy_desc_00, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_last(buf, A_entity_group_a0, A_dl_entity_a0,
                                                           A_enemy_desc_00),
          poison=True, note=f"dying_mask={dying_mask:#x}")


@pytest.mark.parametrize("dying_mask", range(1 << ENTITY_GROUP_SLOTS))
def test_publish_group_bigobj_is_the_a4_group(dying_mask):
    """../names.txt's name says big object; the `lea`s say A_entity_group_a4 under A_enemy_desc_14.
    The case drives the group the code names, so a port that believed the name fails."""
    rng = random.Random(dying_mask + 0x300)
    pokes = group_pokes(A_entity_group_a4, _publish_entities(rng, ENTITY_GROUP_SLOTS, dying_mask))
    pokes.update(_publish_records_poke(A_dl_entity_a4, ENTITY_GROUP_SLOTS))
    pokes[A_enemy_desc_14 + ENEMY_DESC_DEATH_DX] = word(-3) + word(7)
    _case(ENTRY_ENTITY_PUBLISH_GROUP_A4, {"_pokes": pokes},
          lambda lib, buf: lib.g_entity_publish_group_a4(buf),
          poison=True, note=f"dying_mask={dying_mask:#x}")


@pytest.mark.parametrize("marker", (0, 1, BIGOBJ_EXTRA_MARKER - 1, BIGOBJ_EXTRA_MARKER,
                                    BIGOBJ_EXTRA_MARKER + 1))
@pytest.mark.parametrize("active", (0, 1))
def test_bigobj_extra_parts_need_the_999_marker(marker, active):
    """Part 0's ENTITY_HIT_POINTS must be exactly 999, and the part must be live. The three stamps
    land on the FRAME bytes of records 1..3 and touch nothing else in them."""
    records = [entity_record(active=active, hit_points=marker)] + \
              [entity_record(active=1) for _ in range(ENTITY_GROUP_SLOTS - 1)]
    pokes = group_pokes(A_entity_group_bigobj, records)
    pokes.update(_publish_records_poke(A_dl_entity_bigobj, ENTITY_GROUP_SLOTS))
    _case(ENTRY_BIGOBJ_EXTRA_PARTS_PUBLISH, {"_pokes": pokes},
          lambda lib, buf: lib.g_bigobj_extra_parts_publish(buf),
          poison=True, note=f"marker={marker} active={active}")


# ==================================================================================================
# The hide and depth passes
# ==================================================================================================
def _bigobj_pokes(parts):
    return group_pokes(A_entity_group_bigobj, parts)


@pytest.mark.parametrize("dx", (-BIGOBJ_PROBE_OFFSET - 1, -BIGOBJ_PROBE_OFFSET,
                                -BIGOBJ_PROBE_OFFSET + 1, 0,
                                BIGOBJ_BOX_SIZE - BIGOBJ_PROBE_OFFSET - 1,
                                BIGOBJ_BOX_SIZE - BIGOBJ_PROBE_OFFSET,
                                BIGOBJ_BOX_SIZE - BIGOBJ_PROBE_OFFSET + 1))
@pytest.mark.parametrize("dy", (-BIGOBJ_PROBE_OFFSET - 1, -BIGOBJ_PROBE_OFFSET, 0,
                                BIGOBJ_BOX_SIZE - BIGOBJ_PROBE_OFFSET,
                                BIGOBJ_BOX_SIZE - BIGOBJ_PROBE_OFFSET + 1))
def test_hide_test_box_edges(dx, dy):
    """One step either side of each edge of the 0x40 box, with the 0x0e probe offset in place."""
    box_x, box_y = 0x80, 0x60
    parts = [entity_record(active=1, x=box_x, y=box_y)] + \
            [entity_record(active=0) for _ in range(ENTITY_GROUP_SLOTS - 1)]
    pokes = _bigobj_pokes(parts)
    pokes[SCRATCH_ENTITY] = entity_record(active=1, x=box_x + dx, y=box_y + dy,
                                          hidden=SCC_TRUE << 8)
    _case(ENTRY_ENTITY_HIDE_TEST, {"a1": SCRATCH_ENTITY, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_hide_test(buf, SCRATCH_ENTITY),
          poison=True, note=f"d=({dx},{dy})")


@pytest.mark.parametrize("overlapping", range(1 << ENTITY_GROUP_SLOTS))
def test_hide_test_clears_inside_the_loop(overlapping):
    """THE CLEAR IS INSIDE THE WALK. A part that does not overlap clears the flag and the walk goes
    on, so the settled value belongs to the LAST part tested — every subset of the four parts
    overlapping is driven, which is what separates that from a clear-once-at-the-end reading."""
    box_x, box_y = 0x40, 0x40
    parts = []
    for index in range(ENTITY_GROUP_SLOTS):
        inside = overlapping & (1 << index)
        parts.append(entity_record(active=1, x=box_x if inside else 0x300, y=box_y))
    pokes = _bigobj_pokes(parts)
    pokes[SCRATCH_ENTITY] = entity_record(active=1, x=box_x, y=box_y, hidden=0)
    _case(ENTRY_ENTITY_HIDE_TEST, {"a1": SCRATCH_ENTITY, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_hide_test(buf, SCRATCH_ENTITY),
          poison=True, note=f"overlapping={overlapping:#x}")


@pytest.mark.parametrize("dying", (0, 1, SCC_TRUE << 8))
def test_hide_test_reveals_under_a_dying_part(dying):
    """A part that is exploding takes the OTHER exit: the flag is cleared as a WORD and the routine
    returns, so nothing stays hidden behind a big object that is being destroyed."""
    parts = [entity_record(active=1, x=0x40, y=0x40, dying=dying)] + \
            [entity_record(active=0) for _ in range(ENTITY_GROUP_SLOTS - 1)]
    pokes = _bigobj_pokes(parts)
    pokes[SCRATCH_ENTITY] = entity_record(active=1, x=0x40, y=0x40, hidden=0x00ff)
    _case(ENTRY_ENTITY_HIDE_TEST, {"a1": SCRATCH_ENTITY, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_hide_test(buf, SCRATCH_ENTITY),
          poison=True, note=f"dying={dying:#x}")


@pytest.mark.parametrize("live_mask", (0, 1, 0b0101, 0b1111))
def test_hide_group_and_the_whole_pass(live_mask):
    """entity_hide_under_bigobj_group over one turret group, then the pass over the FIRST FOUR turret
    groups — groups t4..t7 are never tested, and the seeded flags in them are what shows that."""
    parts = [entity_record(active=1, x=0x50, y=0x50)] + \
            [entity_record(active=0) for _ in range(ENTITY_GROUP_SLOTS - 1)]
    pokes = _bigobj_pokes(parts)
    for group_index in range(ENTITY_GROUP_T_COUNT):
        group = A_entity_group_t0 + group_index * ENTITY_GROUP_T_STRIDE
        # The seed is NOT 0xff00: groups t4..t7 sit inside the box, so a pass that walked eight
        # groups would `st` a 0xff over a high byte that already held one and leave the image
        # identical. A high byte of 0x12 is what makes the extra write visible (measured: with
        # 0xff00 the HIDE_TEST_GROUPS 4 -> 8 mutant survived the whole battery).
        records = [entity_record(active=bool(live_mask & (1 << slot)),
                                 x=0x50 + 0x8 * slot, y=0x50, hidden=0x1234)
                   for slot in range(ENTITY_GROUP_SLOTS)]
        pokes.update(group_pokes(group, records))
    _case(ENTRY_ENTITY_HIDE_UNDER_BIGOBJ_GROUP,
          {"a0": A_entity_group_t0, "_pokes": pokes},
          lambda lib, buf: lib.g_entity_hide_under_bigobj_group(buf, A_entity_group_t0),
          poison=True, note=f"group live_mask={live_mask:#b}")
    _case(ENTRY_ENTITY_HIDE_UNDER_BIGOBJ, {"_pokes": pokes},
          lambda lib, buf: lib.g_entity_hide_under_bigobj(buf),
          poison=True, note=f"pass live_mask={live_mask:#b}")


@pytest.mark.parametrize("dy", (-BIGOBJ_PROBE_OFFSET - 1, -BIGOBJ_PROBE_OFFSET,
                                -BIGOBJ_PROBE_OFFSET + 1, 0, 1))
@pytest.mark.parametrize("live_mask", range(1 << ENTITY_GROUP_SLOTS))
def test_depth_flag_follows_the_big_objects_y(dy, live_mask):
    """`bigobj_depth_test` returns on the FIRST match and clears only after a full walk, which is the
    opposite of entity_hide_test — the two are driven by separate cases for that reason."""
    part_y = 0x70
    pokes = _bigobj_pokes([entity_record(active=1, x=0x40, y=part_y),
                           entity_record(active=1, x=0x40, y=part_y)]
                          + [entity_record(active=0) for _ in range(ENTITY_GROUP_SLOTS - 2)])
    records = [entity_record(active=bool(live_mask & (1 << slot)), y=part_y + dy + slot)
               for slot in range(ENTITY_GROUP_SLOTS)]
    pokes.update(group_pokes(A_entity_group_x0, records))
    part = group_slot(A_entity_group_bigobj)
    _case(ENTRY_BIGOBJ_DEPTH_TEST,
          {"a1": part, "a2": A_entity_group_x0, "_pokes": pokes},
          lambda lib, buf: lib.g_bigobj_depth_test(buf, part, A_entity_group_x0),
          poison=True, note=f"dy={dy} live_mask={live_mask:#x}")


@pytest.mark.parametrize("parts_live", (0b00, 0b01, 0b10, 0b11))
def test_bigobj_overlap_depth_update_tests_only_the_first_two_parts(parts_live):
    """Part 0 against group x0 and part 1 against x1; parts 2 and 3 are never tested, and the depth
    flags seeded into them are what would show a fourth call."""
    parts = [entity_record(active=bool(parts_live & 1), x=0x40, y=0x70,
                           depth_select=SCC_TRUE << 8),
             entity_record(active=bool(parts_live & 2), x=0x40, y=0x70,
                           depth_select=SCC_TRUE << 8)] + \
            [entity_record(active=1, y=0x70, depth_select=SCC_TRUE << 8)
             for _ in range(ENTITY_GROUP_SLOTS - 2)]
    pokes = _bigobj_pokes(parts)
    for group_index in range(ENTITY_GROUP_X_COUNT):
        group = A_entity_group_x0 + group_index * ENTITY_GROUP_X_STRIDE
        pokes.update(group_pokes(group, [entity_record(active=1, y=0x80 - 0x20 * group_index)
                                         for _ in range(ENTITY_GROUP_SLOTS)]))
    _case(ENTRY_BIGOBJ_OVERLAP_DEPTH_UPDATE, {"_pokes": pokes},
          lambda lib, buf: lib.g_bigobj_overlap_depth_update(buf),
          poison=True, note=f"parts_live={parts_live:#b}")


# ==================================================================================================
# The whole-frame passes, over the world the ORIGINAL spawned
# ==================================================================================================
def test_entities_move_all_over_the_staged_world(staged_world_pokes):
    """Call 10 of the frame loop over 28 slots the game's own spawn script filled — the movement
    scripts, the base frames and the kinds are all the original's data, not this file's."""
    _case(ENTRY_ENTITIES_MOVE_ALL, {"_pokes": staged_world_pokes},
          lambda lib, buf: lib.g_entities_move_all(buf), poison=True)


def test_entities_publish_all_over_the_staged_world(staged_world_pokes):
    """Call 25, likewise: every publisher, every descriptor pairing and every display run at once."""
    _case(ENTRY_ENTITIES_PUBLISH_ALL, {"_pokes": staged_world_pokes},
          lambda lib, buf: lib.g_entities_publish_all(buf), poison=True)


@pytest.mark.parametrize("entry,glue", (
    (ENTRY_ENTITIES_PUBLISH_FACING_GROUPS, "g_entities_publish_facing_groups"),
    (ENTRY_ENTITIES_PUBLISH_BIGOBJ_GROUP, "g_entities_publish_bigobj_group"),
    (ENTRY_ENTITIES_PUBLISH_PLAIN_GROUPS, "g_entities_publish_plain_groups"),
    (ENTRY_ENTITIES_PUBLISH_ANIM_GROUPS, "g_entities_publish_anim_groups"),
    (ENTRY_ENTITIES_PUBLISH_LAST_GROUPS, "g_entities_publish_last_groups"),
))
def test_each_publish_pass_over_the_staged_world(entry, glue, staged_world_pokes):
    """Each pass on its own, so a pass that wrote another's display run is not masked by the pass
    that writes it correctly a moment later."""
    _case(entry, {"_pokes": staged_world_pokes},
          lambda lib, buf: getattr(lib, glue)(buf), poison=True, note=glue)


@pytest.mark.parametrize("entry,glue", (
    (ENTRY_ENTITIES_MOVE_GROUPS_EXTRA, "g_entities_move_groups_extra"),
    (ENTRY_ENTITIES_MOVE_BIGOBJ, "g_entities_move_bigobj"),
    (ENTRY_ENTITIES_MOVE_BIGOBJ_PARTS, "g_entities_move_bigobj_parts"),
))
def test_each_move_pass_over_the_staged_world(entry, glue, staged_world_pokes):
    _case(entry, {"_pokes": staged_world_pokes},
          lambda lib, buf: getattr(lib, glue)(buf), poison=True, note=glue)


@pytest.mark.parametrize("group_index", range(ENTITY_GROUP_T_COUNT))
def test_entities_move_group4_walks_four_slots(group_index, staged_world_pokes):
    group = A_entity_group_t0 + group_index * ENTITY_GROUP_T_STRIDE
    _case(ENTRY_ENTITIES_MOVE_GROUP4, {"a6": group, "_pokes": staged_world_pokes},
          lambda lib, buf: lib.g_entities_move_group4(buf, group),
          poison=True, note=f"group={group:#x}")


@pytest.mark.parametrize("index", range(ENTITY_GROUP_PAIR_COUNT))
def test_entities_move_one_group_takes_a_single_slot(index, staged_world_pokes):
    """`movea.l (a6),a0` with NO post-increment: the pair entries hold one pointer each."""
    group = A_entity_group_pair + index * ENTITY_GROUP_PAIR_STRIDE
    _case(ENTRY_ENTITIES_MOVE_ONE_GROUP, {"a6": group, "_pokes": staged_world_pokes},
          lambda lib, buf: lib.g_entities_move_one_group(buf, group),
          poison=True, note=f"group={group:#x}")


def whole_arena(records_by_slot):
    """The WHOLE 91-record arena as one poke: zeroed, with the named slot addresses filled.

    A case that pokes only the slots it cares about leaves the rest holding whatever the post-load
    image has, which for slot 0 is the nine bytes the sound module's load leaves over it
    (include/globals.h, "THE SOUND MODULE OVERLAPS THE ARENA"). Zeroing the arena outright is what
    lets a whole-pass case say exactly which entities exist.
    """
    arena = bytearray(ENTITY_SLOTS * ENTITY_STRIDE)
    for address, record in records_by_slot.items():
        offset = address - A_entity_arena
        arena[offset:offset + ENTITY_STRIDE] = record
    return {A_entity_arena: bytes(arena)}


def _dying_bomber(x, y):
    """A kind-4 entity on its death path with its bomb still to drop."""
    return entity_record(active=1, dying=1, kind=ENTITY_KIND_BOMBER, has_dropped=0,
                         x=x, y=y, base_frame=0x10, path_select=1, path_cursor=0)


def test_entities_move_all_walks_the_a_groups_in_the_originals_order():
    """a0, a1, a3, a2 — NOT address order, and the order is observable rather than cosmetic.

    Two dying bombers, one in a2 and one in a3, each drop into the first free display record: the
    one the walk reaches first takes record 0 and the other record 1, and their positions differ, so
    an address-order walk swaps them. Nothing else in this battery separates the two orders — the
    staged world has no live slot in either group (measured: the mutation survived until this case).
    """
    pokes = whole_arena({group_slot(A_entity_group_a2): _dying_bomber(0x0011, 0x0022),
                         group_slot(A_entity_group_a3): _dying_bomber(0x0033, 0x0044)})
    pokes.update(_bomb_slot_pokes(set()))
    _case(ENTRY_ENTITIES_MOVE_ALL, {"_pokes": pokes},
          lambda lib, buf: lib.g_entities_move_all(buf), poison=True)


def test_entities_move_bigobj_moves_all_three_pair_slots():
    """The three single-slot pair objects, each with its own velocity — including the third, which
    the original reaches as a hard-coded address rather than through the table. A mover that named
    the wrong slot for it leaves one record unstepped and steps another twice."""
    slots = [group_slot(A_entity_group_pair, index) for index in range(ENTITY_GROUP_PAIR_COUNT)]
    pokes = whole_arena({slot: entity_record(active=1, x=0x100 * (index + 1),
                                             y=0x10 * (index + 1), dx=index + 1, dy=-(index + 1),
                                             countdown=9)
                         for index, slot in enumerate(slots)})
    _case(ENTRY_ENTITIES_MOVE_BIGOBJ, {"_pokes": pokes},
          lambda lib, buf: lib.g_entities_move_bigobj(buf), poison=True)


def test_entities_publish_last_groups_pairs_each_group_with_its_own_descriptor():
    """Each of the four 7-slot groups goes into its OWN display run under its OWN descriptor.

    The shipped descriptors 00..03 all carry the same (10, 12) death offset, so a swapped pairing is
    invisible over the game's own data; the four are seeded to distinct offsets here and every
    entity is dying, which is the only state that reads them. Measured: without this, swapping a2's
    and a3's descriptors survived the whole battery.
    """
    descriptors = (A_enemy_desc_00, 0x19550, 0x19588, 0x1956c)
    groups = (A_entity_group_a0, A_entity_group_a1, A_entity_group_a3, A_entity_group_a2)
    filled = {}
    for index, group in enumerate(groups):
        for slot in range(ENTITY_GROUP_A_SLOTS):
            filled[group_slot(group, slot)] = entity_record(
                active=1, dying=1, draw_layer=index + 1, x=0x100 * index + slot,
                y=0x200 * index + slot, frame_offset=index, base_frame=0x10 * index + slot)
    pokes = whole_arena(filled)
    for index, descriptor in enumerate(descriptors):
        pokes[descriptor + ENEMY_DESC_DEATH_DX] = word(1 << index) + word(0x100 << index)
    for index in range(len(groups)):
        pokes.update(_publish_records_poke(A_dl_entity_a0 + index * DL_GROUP7_STRIDE,
                                           ENTITY_GROUP_A_SLOTS))
    _case(ENTRY_ENTITIES_PUBLISH_LAST_GROUPS, {"_pokes": pokes},
          lambda lib, buf: lib.g_entities_publish_last_groups(buf), poison=True)


def test_the_third_pair_slot_is_the_address_the_mover_hard_codes():
    """`entities_move_bigobj` reaches the third pair object as `lea $5a960,a0` rather than through
    the table. The two must be the same record, and this reads the table to say so — a fact about
    the SHIPPED image, so it is asserted rather than differenced."""
    assert group_slot(A_entity_group_pair, 2) == A_entity_pair_slot_2
    assert (A_entity_pair_slot_2 - A_entity_arena) % ENTITY_STRIDE == 0, "and it is a whole slot"


def test_the_group_tables_cover_every_arena_slot_exactly_once():
    """91 slots, 91 pointers, no repeats — which is why a pass that walks every table walks the
    whole arena, and why `entities_move_all` needs no bound of its own."""
    covered = []
    for group, count in ([(A_entity_group_a0, ENTITY_GROUP_A_SLOTS),
                          (A_entity_group_a1, ENTITY_GROUP_A_SLOTS),
                          (A_entity_group_a2, ENTITY_GROUP_A_SLOTS),
                          (A_entity_group_a3, ENTITY_GROUP_A_SLOTS)]
                         + [(A_entity_group_t0 + i * ENTITY_GROUP_T_STRIDE, ENTITY_GROUP_SLOTS)
                            for i in range(ENTITY_GROUP_T_COUNT)]
                         + [(A_entity_group_bigobj, ENTITY_GROUP_SLOTS)]
                         + [(A_entity_group_x0 + i * ENTITY_GROUP_X_STRIDE, ENTITY_GROUP_SLOTS)
                            for i in range(ENTITY_GROUP_X_COUNT)]
                         + [(A_entity_group_pair + i * ENTITY_GROUP_PAIR_STRIDE, 1)
                            for i in range(ENTITY_GROUP_PAIR_COUNT)]
                         + [(A_entity_group_a4, ENTITY_GROUP_SLOTS)]):
        for index in range(count):
            address = group_slot(group, index)
            assert (address - A_entity_arena) % ENTITY_STRIDE == 0, f"{address:#x} is not a slot"
            covered.append((address - A_entity_arena) // ENTITY_STRIDE)
    assert sorted(covered) == list(range(ENTITY_SLOTS))


# ==================================================================================================
# Fuzz — sharded by `chunk` so `-n auto` spreads it
# ==================================================================================================
FUZZ_CHUNKS = 8
FUZZ_MOVE_CASES = 640
FUZZ_PUBLISH_CASES = 320
FUZZ_ITEM_CASES = 320

# EACH SHARD GENERATES ONLY ITS OWN CASES. The generators below used to build the whole sweep and
# then skip seven records in eight, in every one of the eight workers — eight times the record
# building for one sweep's worth of runs. Seeding on `BASE ^ chunk` makes the shards independent
# streams instead, so the totals above are still what the sweep covers and nothing is discarded.
FUZZ_MOVE_PER_CHUNK = FUZZ_MOVE_CASES // FUZZ_CHUNKS
FUZZ_PUBLISH_PER_CHUNK = FUZZ_PUBLISH_CASES // FUZZ_CHUNKS
FUZZ_ITEM_PER_CHUNK = FUZZ_ITEM_CASES // FUZZ_CHUNKS


def _fuzz_move_cases(chunk):
    """Random entity records for entity_move, over both modes and both signs of every delta.

    The script base is pinned to SCRATCH_SCRIPT and the cursor bounded to the script the case pokes,
    because a wild pointer is a test of the harness rather than of the routine: the oracle bounds an
    address to the image and a C core indexing `image + n` does not, which is what `make guarded`
    exists to fault on.
    """
    rng = random.Random(0x12E9E ^ chunk)
    for index in range(FUZZ_MOVE_PER_CHUNK):
        script = move_script(*[(rng.randrange(-8, 9), rng.randrange(-8, 9),
                                rng.randrange(0, 4), rng.randrange(0x100))
                               for _ in range(4)])
        record = entity_record(
            active=rng.choice((0, 1, 0xffff)),
            dying=rng.choice((0, 0, 1, SCC_TRUE << 8)),
            x=rng.randrange(1 << 16), y=rng.randrange(1 << 16),
            dx=rng.randrange(1 << 16), dy=rng.randrange(1 << 16),
            countdown=rng.choice((0, 1, 2, rng.randrange(1 << 16))),
            base_frame=rng.randrange(1 << 16),
            kind=rng.choice((0, ENTITY_KIND_BOMBER, rng.randrange(1 << 16))),
            has_dropped=rng.choice((0, SCC_TRUE << 8)),
            path_select=rng.randrange(ENTITY_PATH_TABLES),
            path_cursor=rng.randrange(0x40),
            script_base=SCRATCH_SCRIPT,
            script_cursor=rng.choice((0, MOVE_SCRIPT_BYTES, 2 * MOVE_SCRIPT_BYTES)))
        occupied = {slot for slot in range(ENEMY_BOMB_SLOTS) if rng.random() < 0.5}
        yield index, record, script, occupied


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_entity_move(chunk):
    for index, record, script, occupied in _fuzz_move_cases(chunk):
        pokes = _bomb_slot_pokes(occupied)
        pokes[SCRATCH_SCRIPT] = script
        _move_case(record, pokes, note=f"fuzz #{chunk}.{index}")


def _fuzz_publish_cases(chunk):
    rng = random.Random(0x136A2 ^ chunk)
    for index in range(FUZZ_PUBLISH_PER_CHUNK):
        records = [entity_record(
            active=rng.choice((0, 1, 0xffff)), dying=rng.choice((0, 1)),
            x=rng.randrange(1 << 16), y=rng.randrange(1 << 16),
            frame_offset=rng.randrange(1 << 16), base_frame=rng.randrange(1 << 16),
            facing=rng.randrange(1 << 16), draw_layer=rng.randrange(1 << 16),
            hidden=rng.choice((0, SCC_TRUE << 8)), aim_changed=rng.randrange(1 << 16),
            firing=rng.choice((0, 1)), frame_bump=rng.choice((0, SCC_TRUE << 8)),
            anim_timer=rng.randrange(4), hit_points=rng.randrange(1 << 16))
            for _ in range(ENTITY_GROUP_SLOTS)]
        death = (rng.randrange(1 << 16), rng.randrange(1 << 16))
        yield index, records, death


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_publish_facing_and_offset(chunk):
    """Both frame rules and both death-offset sources, over unrestricted words."""
    for index, records, death in _fuzz_publish_cases(chunk):
        pokes = group_pokes(A_entity_group_x0, records)
        pokes.update(_publish_records_poke(A_dl_entity_x0, ENTITY_GROUP_SLOTS))
        pokes[A_enemy_desc_12 + ENEMY_DESC_DEATH_DX] = word(death[0]) + word(death[1])
        _case(ENTRY_ENTITY_PUBLISH_GROUP_FACING,
              {"a0": A_entity_group_x0, "a1": A_dl_entity_x0, "a5": A_enemy_desc_12,
               "_pokes": pokes},
              lambda lib, buf: lib.g_entity_publish_group_facing(buf, A_entity_group_x0,
                                                                 A_dl_entity_x0, A_enemy_desc_12),
              note=f"fuzz facing #{chunk}.{index}")

        pokes = group_pokes(A_entity_group_bigobj, records)
        pokes.update(_publish_records_poke(A_dl_entity_bigobj, ENTITY_GROUP_SLOTS))
        _case(ENTRY_ENTITY_PUBLISH_GROUP_OFFSET,
              {"a0": A_entity_group_bigobj, "a1": A_dl_entity_bigobj, "_pokes": pokes},
              lambda lib, buf: lib.g_entity_publish_group_offset(buf, A_entity_group_bigobj,
                                                                 A_dl_entity_bigobj),
              note=f"fuzz offset #{chunk}.{index}")


def _fuzz_item_cases(chunk):
    rng = random.Random(0x1187A ^ chunk)
    for index in range(FUZZ_ITEM_PER_CHUNK):
        yield index, {
            A_item_weapon: item_record(rng.randrange(1 << 16), rng.randrange(1 << 16),
                                       rng.randrange(0x100), rng.choice((0, 1))),
            A_item_life: item_record(rng.randrange(1 << 16), rng.randrange(1 << 16),
                                     rng.randrange(0x100), rng.choice((0, 1))),
            A_item_extra: item_record(rng.randrange(1 << 16), rng.randrange(1 << 16),
                                      rng.choice((0, 1, 2, rng.randrange(1 << 32))),
                                      rng.choice((0, 1))),
            A_item_bomb: item_record(rng.randrange(1 << 16), rng.randrange(1 << 16),
                                     rng.randrange(0x100), rng.choice((0, 1))),
            A_anim_frame_item0: bytes([rng.randrange(256)]),
            A_anim_frame_item1: bytes([rng.randrange(256)]),
            A_anim_frame_item3: bytes([rng.randrange(256)]),
        }


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_items_move_and_publish(chunk):
    """The four items over unrestricted coordinates and cursors, moved and then published.

    The path cursors are bounded to 0x100 for `_fuzz_move_cases`' reason: `item_path_step` indexes
    A_item_flight_path with the raw longword and a wild one leaves the image.
    """
    for index, pokes in _fuzz_item_cases(chunk):
        _case(ENTRY_ITEMS_MOVE_ALL, {"_pokes": pokes},
              lambda lib, buf: lib.g_items_move_all(buf), note=f"fuzz move #{chunk}.{index}")
        _case(ENTRY_ITEMS_PUBLISH, {"_pokes": pokes},
              lambda lib, buf: lib.g_items_publish(buf), note=f"fuzz publish #{chunk}.{index}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_pickup(chunk):
    """The hit box over unrestricted player, sprite-record and item words."""
    rng = random.Random(0x11698 ^ chunk)
    for index in range(FUZZ_ITEM_PER_CHUNK):
        pokes = _hitbox_pokes(rng.randrange(1 << 16), rng.randrange(1 << 16),
                              draw_dx=rng.randrange(1 << 16), draw_dy=rng.randrange(1 << 16),
                              hit_dx=rng.randrange(1 << 16), hit_dy=rng.randrange(1 << 16),
                              w=rng.randrange(1 << 16), h=rng.randrange(1 << 16))
        pokes[SCRATCH_ITEM] = item_record(rng.randrange(1 << 16), rng.randrange(1 << 16),
                                          active=1)
        kind = rng.randrange(4)
        _case(ENTRY_SPRITE_HITBOX_TEST,
              {"a0": SCRATCH_ITEM, "d6": kind, "_pokes": pokes},
              lambda lib, buf: lib.g_sprite_hitbox_test(buf, SCRATCH_ITEM, kind),
              note=f"fuzz pickup #{chunk}.{index}")


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz_hide_and_depth(chunk):
    """Overlapping boxes at unrestricted coordinates, through both spatial passes."""
    rng = random.Random(0x1179A ^ chunk)
    for index in range(FUZZ_PUBLISH_PER_CHUNK):
        parts = [entity_record(active=rng.choice((0, 1)), dying=rng.choice((0, 0, 1)),
                               x=rng.randrange(1 << 16), y=rng.randrange(1 << 16),
                               depth_select=rng.choice((0, SCC_TRUE << 8)))
                 for _ in range(ENTITY_GROUP_SLOTS)]
        pokes = _bigobj_pokes(parts)
        pokes[SCRATCH_ENTITY] = entity_record(active=1, x=rng.randrange(1 << 16),
                                              y=rng.randrange(1 << 16),
                                              hidden=rng.choice((0, SCC_TRUE << 8)))
        _case(ENTRY_ENTITY_HIDE_TEST, {"a1": SCRATCH_ENTITY, "_pokes": pokes},
              lambda lib, buf: lib.g_entity_hide_test(buf, SCRATCH_ENTITY),
              note=f"fuzz hide #{chunk}.{index}")

        pokes.update(group_pokes(A_entity_group_x0,
                                 [entity_record(active=rng.choice((0, 1)),
                                                y=rng.randrange(1 << 16))
                                  for _ in range(ENTITY_GROUP_SLOTS)]))
        part = group_slot(A_entity_group_bigobj)
        _case(ENTRY_BIGOBJ_DEPTH_TEST, {"a1": part, "a2": A_entity_group_x0, "_pokes": pokes},
              lambda lib, buf: lib.g_bigobj_depth_test(buf, part, A_entity_group_x0),
              note=f"fuzz depth #{chunk}.{index}")


# --- test_constants.py collects these; see README.md, "Adding a function" -------------------------
MIRRORS = (
    ("A_entity_arena", "include/globals.h", "A_entity_arena"),
    ("ENTITY_STRIDE", "include/globals.h", "ENTITY_STRIDE"),
    ("ENTITY_SLOTS", "include/globals.h", "ENTITY_SLOTS"),
    ("A_sprite_bank", "include/globals.h", "A_sprite_bank"),
    ("SPRITE_RECORD_BYTES", "include/globals.h", "SPRITE_RECORD_BYTES"),
    ("A_display_list", "include/display_list.h", "A_display_list"),
    ("DISPLAY_REC_BYTES", "include/display_list.h", "DISPLAY_REC_BYTES"),
    ("DISPLAY_REC_X", "include/display_list.h", "DISPLAY_REC_X"),
    ("DISPLAY_REC_Y", "include/display_list.h", "DISPLAY_REC_Y"),
    ("DISPLAY_REC_FRAME", "include/display_list.h", "DISPLAY_REC_FRAME"),
    ("DISPLAY_REC_ACTIVE", "include/display_list.h", "DISPLAY_REC_ACTIVE"),
    ("DISPLAY_ACTIVE_UNDER_SCENERY", "include/display_list.h", "DISPLAY_ACTIVE_UNDER_SCENERY"),
    ("DISPLAY_ACTIVE_ON_TOP", "include/display_list.h", "DISPLAY_ACTIVE_ON_TOP"),
    ("SPRITE_REC_DRAW_DX", "include/sprite.h", "SPRITE_REC_DRAW_DX"),
    ("SPRITE_REC_DRAW_DY", "include/sprite.h", "SPRITE_REC_DRAW_DY"),
    ("SPRITE_REC_HIT_DX", "include/sprite.h", "SPRITE_REC_HIT_DX"),
    ("SPRITE_REC_HIT_DY", "include/sprite.h", "SPRITE_REC_HIT_DY"),
    ("SPRITE_REC_HIT_W", "include/sprite.h", "SPRITE_REC_HIT_W"),
    ("SPRITE_REC_HIT_H", "include/sprite.h", "SPRITE_REC_HIT_H"),
    ("A_player", "include/player.h", "A_player"),
    ("A_lives", "include/player.h", "A_lives"),
    ("A_bombs", "include/player.h", "A_bombs"),
    ("A_score_bcd", "include/hud.h", "A_score_bcd"),   # the bonus arm's score chain adds to it
    ("ITEM_EXTRA_FRAME", "src/entity.c", "ITEM_EXTRA_FRAME"),
    ("ITEM_EXTRA_FALL_FRAMES", "src/entity.c", "ITEM_EXTRA_FALL_FRAMES"),
    ("ITEM_PICKUP_BOX", "src/entity.c", "ITEM_PICKUP_BOX"),
    ("FIRE_RELOAD_COMMON", "src/entity.c", "FIRE_RELOAD_COMMON"),
    ("HIT_POINTS_TURRET", "src/entity.c", "HIT_POINTS_TURRET"),
    ("FIRE_RELOAD_TURRET", "src/entity.c", "FIRE_RELOAD_TURRET"),
    ("HIT_POINTS_A4", "src/entity.c", "HIT_POINTS_A4"),
    ("HIDE_TEST_GROUPS", "src/entity.c", "HIDE_TEST_GROUPS"),
    ("SCC_TRUE", "include/common.h", "SCC_TRUE"),
    # ...and everything else this battery pokes, which is include/entity.h's.
    "ENTITY_X", "ENTITY_Y", "ENTITY_FRAME_OFFSET", "ENTITY_DRAW_LAYER", "ENTITY_DRAW_LAYER_BYTE",
    "ENTITY_DX", "ENTITY_DY", "ENTITY_STEP_COUNTDOWN", "ENTITY_ACTIVE", "ENTITY_DYING",
    "ENTITY_BASE_FRAME", "ENTITY_HIT_POINTS", "ENTITY_AIM_CHANGED", "ENTITY_FACING",
    "ENTITY_DEPTH_SELECT", "ENTITY_FIRE_RELOAD", "ENTITY_PATH_SELECT", "ENTITY_PATH_CURSOR",
    "ENTITY_FIRING", "ENTITY_FRAME_BUMP", "ENTITY_ANIM_TIMER", "ENTITY_KIND",
    "ENTITY_HAS_DROPPED", "ENTITY_HIDDEN_UNDER_BIGOBJ", "ENTITY_SCRIPT_BASE",
    "ENTITY_SCRIPT_CURSOR", "ENTITY_KIND_BOMBER",
    "MOVE_SCRIPT_BYTES", "SCRIPT_TERMINATOR",
    "A_entity_group_a0", "A_entity_group_a1", "A_entity_group_a2", "A_entity_group_a3",
    "ENTITY_GROUP_A_SLOTS", "A_entity_group_t0", "ENTITY_GROUP_T_STRIDE", "ENTITY_GROUP_T_COUNT",
    "A_entity_group_bigobj", "A_entity_group_x0", "ENTITY_GROUP_X_STRIDE", "ENTITY_GROUP_X_COUNT",
    "A_entity_group_pair", "ENTITY_GROUP_PAIR_STRIDE", "ENTITY_GROUP_PAIR_COUNT",
    "A_entity_pair_slot_2", "A_entity_group_a4", "ENTITY_GROUP_SLOTS", "ENTITY_GROUP_PTR_BYTES",
    "ENEMY_DESC_FIRE_RELOAD", "ENEMY_DESC_DEATH_DX", "ENEMY_DESC_DEATH_DY",
    "ENEMY_DESC_HIT_POINTS", "A_enemy_desc_00", "A_enemy_desc_12", "A_enemy_desc_14",
    "A_entity_path_tbl_ptrs", "ENTITY_PATH_TABLES", "ENTITY_PATH_PTR_BYTES",
    "A_anim_frame_a", "A_anim_frame_b", "A_anim_frame_item0", "A_anim_frame_item1",
    "A_anim_frame_item3", "A_anim_frame_bomb", "ANIM_FRAME_TABLE_OFFSET",
    "ANIM_PHASE_MASK_2", "ANIM_PHASE_MASK_3",
    "A_item_weapon", "A_item_life", "A_item_bomb", "A_item_extra",
    "ITEM_X", "ITEM_Y", "ITEM_CURSOR", "ITEM_ACTIVE", "ITEM_BYTES",
    "A_item_flight_path", "ITEM_PATH_STEP_BYTES",
    "ITEM_KIND_WEAPON", "ITEM_KIND_BOMB", "ITEM_KIND_LIFE",
    "WEAPON_LEVEL_FULL", "BOMBS_FULL", "LIVES_NO_AWARD_ABOVE",
    "A_dl_entity_t0", "A_dl_entity_t4", "DL_GROUP4_STRIDE", "DL_TURRET_RUN_GROUPS",
    "A_dl_entity_pair", "A_dl_entity_bigobj", "A_dl_entity_x0", "A_dl_entity_a0",
    "DL_GROUP7_STRIDE", "A_dl_entity_a4",
    "A_dl_item_0", "A_dl_item_1", "A_dl_item_2", "A_dl_item_3",
    "BIGOBJ_EXTRA_PART_FRAME_0", "BIGOBJ_EXTRA_PART_FRAME_1", "BIGOBJ_EXTRA_PART_FRAME_2",
    "BIGOBJ_EXTRA_PARTS", "BIGOBJ_EXTRA_MARKER", "BIGOBJ_BOX_SIZE", "BIGOBJ_PROBE_OFFSET",
    "A_frame_counter", "A_item_pickup_pending", "A_enemy_bomb_slot_scan", "ENEMY_BOMB_SLOTS",
    "ENEMY_BOMB_DY", "ENTITY_RETIRE_Y",
    ("PLAYER_X", "include/player.h", "PLAYER_X"),
    ("PLAYER_Y", "include/player.h", "PLAYER_Y"),
    ("PLAYER_FRAME", "include/player.h", "PLAYER_FRAME"),
    ("A_weapon_level", "include/weapons.h", "A_weapon_level"),
)

ENTRY_PROLOGUES = {
    "ENTRY_BIGOBJ_EXTRA_PARTS_PUBLISH": "41f9000193b622584a69000e67200c69",
    "ENTRY_COUNT_GAME_FRAME": "52b9000177644e7541f90005ae9a4a68",
    "ENTRY_ITEMS_PICKUP_CHECK": "41f90005ae9a4a680008670642466100",
    "ENTRY_SPRITE_HITBOX_TEST": "43f9000190a442801029000449f90001",
    "ENTRY_ITEM_PICKUP_AWARD": "4a46671cbc7c0001672a0c7900060001",
    "ENTRY_ENTITY_HIDE_UNDER_BIGOBJ": "41f9000192b66100002041f9000192d6",
    "ENTRY_ENTITY_HIDE_UNDER_BIGOBJ_GROUP": "3e3c000322584a69000e670461000008",
    "ENTRY_ENTITY_HIDE_TEST": "3c3c000345f9000193b6265a4a6b000e",
    "ENTRY_BIGOBJ_OVERLAP_DEPTH_UPDATE": "41f9000193b622584a69000e670a45f9",
    "ENTRY_BIGOBJ_DEPTH_TEST": "3c3c0003265a4a6b000e671230290002",
    "ENTRY_ENEMY_BOMBS_MOVE": "41f9000177ce3e3c000f066800020002",
    "ENTRY_ITEMS_MOVE_ALL": "41f90005ae9a6100005841f90005aea4",
    "ENTRY_ITEM_DROP_STEP": "4a68000867120668000200020c6800c8",
    "ENTRY_ITEM_FALL_STEP": "4a680008671604a80000000100046b08",
    "ENTRY_ITEM_PATH_STEP": "4a680008673a43f90001b02ad3e80004",
    "ENTRY_ITEMS_PUBLISH": "41f90005ae9a43f900017c244a680008",
    "ENTRY_ANIM_FRAME_IDS_UPDATE": "20390001776402800000000241f90001",
    "ENTRY_ITEM_DROP_IF_FORMATION_CLEARED": "48e7fffe3e3c000622584a69000e6708",
    "ENTRY_DIFFICULTY_APPLY_FIRE_RATES": "303c000a323c000c343c0007363c0012",
    "ENTRY_ENTITIES_MOVE_ALL": "4df9000192463e3c0006205e61000134",
    "ENTRY_ENTITIES_MOVE_GROUPS_EXTRA": "4df9000193c66100002a4df9000193d6",
    "ENTRY_ENTITIES_MOVE_GROUP4": "3e3c0003205e6100004251cffff84e75",
    "ENTRY_ENTITIES_MOVE_BIGOBJ": "4df900019416610000164df90001941a",
    "ENTRY_ENTITIES_MOVE_ONE_GROUP": "2056600000184df9000193b63e3c0003",
    "ENTRY_ENTITIES_MOVE_BIGOBJ_PARTS": "4df9000193b63e3c0003205e61000008",
    "ENTRY_ENTITY_MOVE": "48e7fffe4a68000e671e4a680010661e",
    "ENTRY_ENEMY_BOMB_DROP": "48e7fffe42790001776c43f9000177ce",
    "ENTRY_ENTITIES_PUBLISH_ALL": "61000156610002166100013e6100000a",
    "ENTRY_ENTITIES_PUBLISH_FACING_GROUPS": "4bf90001972641f9000193c643f90001",
    "ENTRY_ENTITY_PUBLISH_GROUP_FACING": "3e3c000324584a6a000e67463292336a",
    "ENTRY_ENTITY_PUBLISH_GROUP_A4": "41f90001945e43f900017b224bf90001",
    "ENTRY_ENTITIES_PUBLISH_BIGOBJ_GROUP": "41f9000193b643f9000179ea60000176",
    "ENTRY_ENTITIES_PUBLISH_PLAIN_GROUPS": "41f9000192b643f90001783461000072",
    "ENTRY_ENTITY_PUBLISH_GROUP_PLAIN": "3e3c000324584a6a000e672a4a6a0030",
    "ENTRY_ENTITIES_PUBLISH_ANIM_GROUPS": "41f90001941643f9000179b44bf90001",
    "ENTRY_ENTITY_PUBLISH_ANIM": "24584a6a000e675c3292336a00020002",
    "ENTRY_ENTITY_PUBLISH_GROUP_OFFSET": "3e3c000324584a6a000e67383292336a",
    "ENTRY_ENTITIES_PUBLISH_LAST_GROUPS": "4bf90001953441f90001924643f90001",
    "ENTRY_ENTITY_PUBLISH_GROUP_LAST": "3e3c000624584a6a000e67383292336a",
    "ENTRY_SPAWN_SCRIPT_STEP": "207900017770d1f9000177540c50a3a1",
}

STOP_PROLOGUES = {
    "STOP_DIFFICULTY_TAIL": "6000e6e64df9000192463e3c0006205e",
}
