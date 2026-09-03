"""The ASM-TWIN differential for the frame loop's SPAWN AND MOVE stage: `../src/asm/frame_spawn.S`
must leave the image byte-for-byte where its C core in `../src/frame.c` leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_frame.py` pins the C core against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_frame.py)==  C core  ==(THIS FILE)==  asm twin

THE STAGING IS `test_frame.py`'S, IMPORTED RATHER THAN RESTATED — its worlds (which have the ORACLE
play a section for four frames before a case starts), its script-trigger arithmetic, its carried
registers and its fuzz generator. Importing it also installs this battery's `ctypes` signatures for
the five frame glues, which is why nothing here declares them again. The door table, the candidate
arming and the three source-reading pins are the FAMILY's, in `asm_frame_common.py`; that module's
header says why.

WHAT IS DIFFERENT ABOUT THIS TWIN, and what this file carries because of it.

**1. THE STAGE IS `void`, so the differential compares the IMAGE and nothing else.** Wave C's twin
answers with a `frame_exit` and its cases declare the arm they want; this one has no answer at all,
so `expect_ret=common.VOID_STAGE` and the whole of the comparison is 1 MiB of image plus the refusal counts.

**2. TWO REGISTER PARAMETERS.** `chance_index_register` (D1) and `ground_spawn_y_register` (D7) are
values no instruction of the loop wrote since the last `bsr` — `include/frame.h` says why — so the
twin takes both through the same C ABI the core does. Most cases take the pair the ORACLE holds at
those instructions (`test_frame.carried_registers`); the two that are ABOUT a register name their own
value, which is legitimate because this differential's shores are the C and the twin rather than the
original.

**3. TWENTY-FIVE DOOR CALLEES OVER FORTY CALL SITES**, which is more than any other frame twin, and
most of them behind an arm a played frame does not take. So a case DECLARES which doors it must
reach and the run asserts it (`door_traffic` below), and one test asserts that the cases between
them name every door the `.S` declares — a door added to the twin with no case is then a failure
rather than a hole.

**4. THE HIGH WORD OF `ground_spawn_y_register` IS WHERE THE C AND THE TWIN LEGITIMATELY DIFFER, and
it is unobservable.** `frame_wave_script` returns a value with a ZERO high word on its derived paths
(the C computes `trigger` and `opcode` as `uint16_t`), while the original — and so the twin — carries
whatever the `mulu.w` at 0x1174c and the callees left in D7's top half.
`test_frame.py::test_no_shipped_ground_script_can_make_the_spawner_read_its_carried_register` is the
measurement that closes it: `groundscript_spawn` reads that high word in exactly one guard, and no
shipped ground-script record can make the guard fire. STATUS.md carries it as a coverage limit; this
note is here so a reader of a green suite knows the equality is proved rather than assumed.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import collections
import functools
import random
import re

import pytest

# FIRST, and the order is load-bearing: test/harness.py is what puts tools/ on `sys.path` and binds
# the kit to this project, so every name below it is only importable once it has run.
import harness

import emu
import asm_twins
import asm_frame_common as common
import test_frame as frame

SPAWN_S = common.ASM_DIR / "frame_spawn.S"
SPAWN_OBJ = common.BUILD_ASM / "frame_spawn.o"

TWIN = "frame_spawn_and_move_stage_asm"
ORIGINAL_ENTRY = frame.ENTRY_SPAWN_AND_MOVE            # 0x1167c
ORIGINAL_END = frame.ENTRY_DRAW_AND_COLLIDE            # 0x11c00 — where both exits leave to


# ---- the globals and record offsets this file names that test_frame.py does not ----------------
#
# EVERY ONE IS PINNED TO ITS HEADER BY `test_the_addresses_this_file_names_are_the_headers` BELOW,
# and that test is the reason they may be restated here at all. `include/` is the canonical
# definition; this is a second copy in a place that cannot `#include` it, which CLAUDE.md §5 allows
# on exactly one condition — "pick one canonical definition and pin the other equal with a test".
# Unpinned, the failure is silent and specific: move `A_section_ground_target_flag` in
# include/init.h, and the C and the twin both follow it while this file goes on poking 0x19897 —
# a byte nothing reads, so the case never drives the ground-spawner arm it is named for and both
# shores agree on the untested path.
MIRRORED_ADDRESSES = {
    "A_section_ground_target_flag": 0x19897,   # init.h — which ground spawner the section uses
    "A_enemy_fire_chance_table": 0x19aaf,      # enemy.h — one signed byte per section
    "A_enemy_types_fire_seeker": 0x19180,      # enemy.h
    "A_enemy_types_can_fire": 0x19172,         # enemy.h
    "A_enemy_types_fire_homing": 0x19164,      # enemy.h
    "A_rng_lfsr_state": 0x195f4,               # rng.h
    "ACTOR_FIRE_FLAGS": 0x2a,                  # enemy.h
    "SHOT_TARGET_INDEX": 0x1a,                 # weapon.h
    "SHOT_TURN_COUNTDOWN": 0x1b,               # weapon.h
    "BULLET_STEP_X": 0x0c,                     # frame.h — one frame of a plain bullet
}
A_SECTION_GROUND_TARGET_FLAG = MIRRORED_ADDRESSES["A_section_ground_target_flag"]
A_ENEMY_FIRE_CHANCE_TABLE = MIRRORED_ADDRESSES["A_enemy_fire_chance_table"]
A_ENEMY_TYPES_FIRE_SEEKER = MIRRORED_ADDRESSES["A_enemy_types_fire_seeker"]
A_ENEMY_TYPES_CAN_FIRE = MIRRORED_ADDRESSES["A_enemy_types_can_fire"]
A_ENEMY_TYPES_FIRE_HOMING = MIRRORED_ADDRESSES["A_enemy_types_fire_homing"]
A_RNG_LFSR_STATE = MIRRORED_ADDRESSES["A_rng_lfsr_state"]
ACTOR_FIRE_FLAGS = MIRRORED_ADDRESSES["ACTOR_FIRE_FLAGS"]
SHOT_TARGET_INDEX = MIRRORED_ADDRESSES["SHOT_TARGET_INDEX"]
SHOT_TURN_COUNTDOWN = MIRRORED_ADDRESSES["SHOT_TURN_COUNTDOWN"]
BULLET_STEP_X = MIRRORED_ADDRESSES["BULLET_STEP_X"]

# NOT MIRRORED, because no header defines it: `src/enemy.c` spells the player's entity index inline.
PLAYER_ENTITY_INDEX = 0x11

# The types the shipped class maps do and do not list, taken from `test_enemy.py`, which asserts all
# four against the image in `test_the_fire_class_maps_this_battery_uses`. Restated rather than
# imported: importing a 4,000-line sibling battery for four numbers would make every run of this
# file pay for its module-level searches.
HOMING_CLASS_TYPE = 0x02                 # in A_enemy_types_fire_homing
CAN_FIRE_TYPE = 0x14                     # in A_enemy_types_can_fire, in neither other map
SEEKER_CLASS_TYPE = 0x10                 # in A_enemy_types_fire_seeker

# The three kinds an enemy shot slot can hold, and what each one's ticker does — src/enemy.c.
ENEMY_SHOT_TYPE_AIMED = 0x0c             # no ticker: it drifts and is retired off the edges
ENEMY_SHOT_TYPE_HOMING = 0x0a
ENEMY_SHOT_TYPE_SEEKER = 0x0b
ENEMY_SHOT_SLOTS = 3
ENEMY_FIRE_BIT_STEERED = 1               # `btst #1,42(a1)` — this enemy may launch a steered shot
ENEMY_FIRE_BIT_HALVED = 2                # ...but only ENEMY_HOMING_CHANCE often
ENEMY_FIRE_ROLL_MASK = 3                 # `and.w #$3,d0` — only one frame in four even tries

# A time-to-live a steered shot survives the frame with, and one that expires ON this frame.
SHOT_TTL_HEALTHY = 5
SHOT_TTL_LAST = 1

# Where the launch cases put the firing enemy and the ship. The seeker arm only launches while the
# ship is at or LEFT of the enemy (`cmp.w 0(a1),d1` + `ble`), so the two are placed either side of
# the playfield rather than left where the world had them.
LAUNCH_ENEMY_X = 0x140
LAUNCH_ENEMY_Y = 0x60
LAUNCH_PLAYER_X = 0x40


# ============================================================ the shared machinery

DOOR_TABLE = common.DOOR_TABLE
twins = common.twins


def _staged(world, extra):
    """The exact image the differential runs, so the register probe reads the world under test.

    `asm_frame_common.leaves_the_image_where_the_c_does` builds it the same way; recomputing it here
    is cheaper than threading it out of that function, and it is what makes `carried_registers`
    below answer for the image the two shores actually see rather than for the unpoked world.
    """
    return harness.make_image(frame.world_pokes(world, extra))


def _vet_door_names(names):
    """Every name a case names must be a door this family declares.

    `reaches` and `avoids` have OPPOSITE failure modes on the same typo, which is why this exists.
    `hits` is a Counter, so `hits[name]` is 0 for any key: a misspelt `reaches` name is always
    "missing" and fails loudly, while a misspelt `avoids` name is always "not taken" and passes
    forever — the case then reports that a door was skipped when the twin drove it on every run, and
    the arm can regress with nothing red. Checking both against the table makes them symmetric.
    """
    declared = {callback.name for callback in common.DOOR_TABLE.values()}
    unknown = sorted(set(names) - declared)
    assert not unknown, (
        f"{unknown} name no door in DOOR_TABLE, so a `reaches` entry would fail for the wrong "
        f"reason and an `avoids` entry would pass vacuously for ever")


def leaves_the_image_where_the_c_does(world, extra=None, reaches=(), avoids=(),
                                      registers=None, refusal_free=True):
    """This stage's arguments to the family's differential, plus the door assertions.

    `asm_frame_common` says what the three shared assertions are and what each one closes. What is
    this file's own is the pair of register parameters, `expect_ret=common.VOID_STAGE` (the stage is `void`), and
    `reaches` / `avoids` — the doors this case says it does and does not drive, which is the only
    check that the staging put the twin on the arm the case is named for.

    `registers` lets a case DECLARE the (chance_index, ground_spawn_y) pair instead of taking the
    one the oracle holds. Legitimate here and not in `test_frame.py`: this differential's two shores
    are the C core and the twin, and both are handed the same pair, so a case may choose a value the
    frame loop would not have produced in order to drive what the value selects.
    """
    _vet_door_names(reaches + avoids)
    chance, ground_y = registers or frame.carried_registers(_staged(world, extra), ORIGINAL_ENTRY)
    with common.door_traffic() as hits:
        run = common.leaves_the_image_where_the_c_does(
            TWIN, world, extra,
            c_call=lambda lib, buf: lib.g_frame_spawn_and_move_stage(buf, chance, ground_y),
            twin_args=(chance, ground_y), expect_ret=common.VOID_STAGE, refusal_free=refusal_free)
    missing = sorted(name for name in reaches if not hits[name])
    assert not missing, (
        f"the twin never called {missing} — this case is staged so that the arm it is named for is "
        f"not taken, so the image comparison above proves nothing about it. Doors it DID reach: "
        f"{sorted(hits)}")
    taken = sorted(name for name in avoids if hits[name])
    assert not taken, (
        f"the twin called {taken}, which this case says it must not reach — the gate that should "
        f"have skipped them did not")
    return run


# ---- the doors every frame of the game reaches, whatever else a case stages --------------------
EVERY_FRAME = ("explosion_animate_all", "anim_ground_objects", "enemies_animate_all",
               "enemies_move_all", "player_shot_update_all", "rand16")


def test_the_fire_class_maps_this_battery_uses():
    """The three types the launch cases pick with, against the shipped 14-byte maps.

    Read off the image every run, so a map that changed would fail HERE instead of quietly turning
    the three launch arms into one: which arm `spawn_enemy_shot` takes is decided entirely by these
    memberships, and a type that fell out of `can_fire` would make its case launch nothing at all
    while still comparing two identical images. `test_enemy.py` asserts the same three for the same
    reason; both files pick their types from this fact rather than remembering a number.
    """
    def listed(base, type_id):
        word = int.from_bytes(bytes(harness.BASE_IMAGE[base + ((type_id >> 3) & 0xfffe):][:2]),
                              "big")
        return (word >> (15 - (type_id & 0xf))) & 1

    assert listed(A_ENEMY_TYPES_FIRE_SEEKER, SEEKER_CLASS_TYPE)
    assert listed(A_ENEMY_TYPES_CAN_FIRE, CAN_FIRE_TYPE)
    assert not listed(A_ENEMY_TYPES_FIRE_HOMING, CAN_FIRE_TYPE), (
        "the aimed-shot case needs a type the homing map does NOT list, or it takes the homing arm")
    assert listed(A_ENEMY_TYPES_CAN_FIRE, HOMING_CLASS_TYPE)
    assert listed(A_ENEMY_TYPES_FIRE_HOMING, HOMING_CLASS_TYPE)
    assert not listed(A_ENEMY_TYPES_FIRE_SEEKER, HOMING_CLASS_TYPE), (
        "the homing case needs a type the seeker map does NOT list, or the caller picks the seeker")


# ============================================================ the game, played

@pytest.mark.parametrize("section", range(frame.SECTION_COUNT))
def test_the_twin_plays_the_game(section):
    """The stage, frame by frame, over each of the sixteen sections the game ships.

    THIS IS THE COMPOSITION TEST. Each frame runs the twin's 311 instructions and its door calls over
    the whole 512 KB the game owns, against the C that `test_frame.py` has already proved equal to
    the original on these exact worlds — so a pass that ran a loop once too often, took a branch the
    other way or reloaded a base inside a loop differs on real pixels.

    The sections are not interchangeable: four are asteroid fields with no map, and which alien bank
    and which ground target a section loads is the level designer's choice.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for _ in range(frame.WORLD_FRAMES):
        leaves_the_image_where_the_c_does(image, reaches=EVERY_FRAME)
        image = frame.advance_one_frame(image)


@pytest.mark.parametrize("section", frame.FUZZ_SECTIONS)
def test_the_twin_fuzz(section):
    """`test_frame.py`'s own 96-case generator, replayed against the twin.

    What it reaches that the sweep above does not is the COMBINATION: six player shot slots each
    alive or dead and of five kinds, eight enemy slots each of ten types, the scroll counters and
    the two animation phases — which is the six-slot maintenance loop, the enemy fire pass and both
    script gates at once, and no dozen frames of one section can walk it.

    Sharded by section for `test_frame.py`'s reason: a case's cost is dominated by building its
    world, which `frame.world` caches per worker.
    """
    image = bytearray(frame.world(section, frame.WORLD_START))
    for case in frame.fuzz_cases_for(section):
        leaves_the_image_where_the_c_does(
            image, frame.fuzz_pokes(random.Random(0x1167c + case), image))


# ============================================================ the arms, one case each
#
# Each entry is a poke builder over the staged world and the doors that arm must and must not reach.
# They are a table rather than sixteen near-identical functions because
# `test_the_cases_between_them_reach_every_door_this_twin_names` has to be able to ask what the set
# of them covers — a door added to the `.S` with nobody driving it then fails here rather than
# sitting in the table looking like coverage.

Case = collections.namedtuple("Case", "extra reaches avoids registers",
                              defaults=((), (), None))

# `test_frame.carried_registers` probes D7 at the WALKER spawner's `bsr` (0x11818), so it cannot
# answer for a frame that takes the DIVER's at 0x11820 instead — the probe run never reaches its
# checkpoint and raises. The diver case therefore DECLARES its pair, which is what the parameters
# are for: both shores are handed the same values, and neither register is what that case is about.
# Its D7 is not even read — the attack script's own trigger is not met on this frame, so the C
# derives the y from the block and the parameter is the fallback nobody uses (include/frame.h).
DECLARED_REGISTERS_FOR_THE_DIVER = (0, 0)


def _enemy_slots(fields):
    """The same {record offset: bytes} over all eight wave slots.

    ALL EIGHT, because `enemy_fire_and_update_shots` picks ONE of them with `rand16 & 7` and the
    draw belongs to the world; eight identical records make the arm the case wants the arm every
    pick takes, without the case having to own the generator.
    """
    return {frame.A_ENEMY_SLOTS + frame.ENTITY_STRIDE * slot + at: blob
            for slot in range(frame.ENEMY_SLOT_COUNT) for at, blob in fields.items()}


def _firing_enemy(enemy_type, fire_flags):
    """Eight live enemies of one type, placed where the seeker arm's position test can pass, with
    the ship put to their left and the seeker's global cooldown spent."""
    pokes = _enemy_slots({frame.ENTITY_ALIVE: b"\x01",
                          frame.ENTITY_TYPE: bytes([enemy_type]),
                          ACTOR_FIRE_FLAGS: bytes([fire_flags]),
                          frame.ENTITY_X: LAUNCH_ENEMY_X.to_bytes(2, "big"),
                          frame.ENTITY_Y: LAUNCH_ENEMY_Y.to_bytes(2, "big")})
    pokes[frame.A_PLAYER_RECORD + frame.ENTITY_X] = LAUNCH_PLAYER_X.to_bytes(2, "big")
    pokes[frame.A_ENEMY_SEEKER_COOLDOWN] = b"\x00"
    # The boss flag bypasses the fire flags and the per-section chance entirely, so the launch is
    # the case's own decision rather than a draw's — src/enemy.c's `enemy_wants_to_fire`.
    pokes[frame.A_MOTHERSHIP_READY] = b"\x01"
    pokes.update(_enemy_shot_slots(alive=0))
    return pokes


def _enemy_shot_slots(alive, shot_type=ENEMY_SHOT_TYPE_AIMED, ttl=SHOT_TTL_HEALTHY):
    """All three enemy shot slots in one state — free for a launch case, or live for a tick case."""
    return {frame.A_ENEMY_SHOT_SLOTS + frame.ENTITY_STRIDE * slot + at: blob
            for slot in range(ENEMY_SHOT_SLOTS)
            for at, blob in ((frame.ENTITY_ALIVE, bytes([alive])),
                             (frame.ENTITY_TYPE, bytes([shot_type])),
                             (frame.ENTITY_ANIM_FRAME, bytes([ttl])),
                             (SHOT_TARGET_INDEX, bytes([PLAYER_ENTITY_INDEX])),
                             (SHOT_TURN_COUNTDOWN, b"\x02"),
                             (frame.ENTITY_X, LAUNCH_ENEMY_X.to_bytes(2, "big")),
                             (frame.ENTITY_Y, LAUNCH_ENEMY_Y.to_bytes(2, "big")))}


def _player_shot(shot_type, x=0x80, y=0x50):
    """Player shot slot 0 alive and of one steered kind, at a position of the case's choosing."""
    return {frame.A_ENTITY_TABLE + frame.ENTITY_TYPE: bytes([shot_type]),
            frame.A_ENTITY_TABLE + frame.ENTITY_ALIVE: b"\x01",
            frame.A_ENTITY_TABLE + frame.ENTITY_ANIM_FRAME: bytes([frame.SHOT_TIME_TO_LIVE_HEALTHY]),
            frame.A_ENTITY_TABLE + frame.ENTITY_X: (x & 0xffff).to_bytes(2, "big"),
            frame.A_ENTITY_TABLE + frame.ENTITY_Y: (y & 0xffff).to_bytes(2, "big")}


def _wave_script_fires(world, opcode=None):
    """The map offset that makes the attack script fire this frame, and optionally the opcode it
    fires with — poked over the record's own high byte, which is where the script keeps it."""
    pokes = {frame.A_MAP_OFFSET: frame.script_trigger_offset(
                 world, frame.A_WAVE_SCRIPT_CURSOR, True).to_bytes(4, "big"),
             frame.A_MOTHERSHIP_PENDING: b"\x00"}
    if opcode is not None:
        cursor = int.from_bytes(bytes(world[frame.A_WAVE_SCRIPT_CURSOR:][:4]), "big")
        pokes[cursor + 2] = bytes([opcode])
    return pokes


def _ground_script_fires(world, ground_target, mothership_pending=0):
    """The four gates the ground script is behind, all opened, and which of the two spawners runs."""
    return {frame.A_MAP_OFFSET: frame.script_trigger_offset(
                world, frame.A_GROUND_SCRIPT_CURSOR, False).to_bytes(4, "big"),
            frame.A_ASTEROID_SECTION_FLAG: b"\x00", frame.A_SCROLL_FROZEN: b"\x00",
            frame.A_MAP_PAGE: b"\x00",
            A_SECTION_GROUND_TARGET_FLAG: bytes([ground_target]),
            frame.A_MOTHERSHIP_PENDING: bytes([mothership_pending])}


CASES = {
    # ---- the two section arms, each with the other's doors forbidden -------------------------
    "an asteroid section": Case(
        lambda world: {frame.A_ASTEROID_SECTION_FLAG: b"\x01"},
        EVERY_FRAME + ("squadron_spawn_tick", "asteroids_move", "asteroids_animate"),
        ("groundscript_spawn_type10", "groundscript_spawn_type0f")),
    "a map section": Case(
        lambda world: {frame.A_ASTEROID_SECTION_FLAG: b"\x00"},
        EVERY_FRAME,
        ("squadron_spawn_tick", "asteroids_move", "asteroids_animate")),

    # ---- the boss tail, and the early return that skips all three of it ----------------------
    "a boss encounter": Case(
        lambda world: {frame.A_BOSS_SEQUENCE_ACTIVE: b"\x01",
                       frame.A_MOTHERSHIP_PHASE_TIMER: (0x1234).to_bytes(4, "big")},
        EVERY_FRAME + ("mothership_move_and_place", "mothership_draw")),
    "no boss encounter": Case(
        lambda world: {frame.A_BOSS_SEQUENCE_ACTIVE: b"\x00"},
        EVERY_FRAME, ("mothership_move_and_place", "mothership_draw")),

    # ---- the attack script's four opcodes ------------------------------------------------------
    "the attack script spawning a formation": Case(
        lambda world: _wave_script_fires(world),
        EVERY_FRAME + ("wavescript_spawn_wave",), ("wavescript_spawn_trio_type0e",)),
    "the attack script spawning a trio": Case(
        lambda world: _wave_script_fires(world, opcode=0x0b),
        EVERY_FRAME + ("wavescript_spawn_trio_type0e",), ("wavescript_spawn_wave",)),
    "the attack script turning the asteroid squadrons on": Case(
        lambda world: _wave_script_fires(world, opcode=0x0c),
        EVERY_FRAME, ("wavescript_spawn_wave", "wavescript_spawn_trio_type0e")),
    "the attack script turning the asteroid squadrons off": Case(
        lambda world: _wave_script_fires(world, opcode=0x0d),
        EVERY_FRAME, ("wavescript_spawn_wave", "wavescript_spawn_trio_type0e")),

    # ---- the ground script's two spawners, and the path where D7 is the parameter -------------
    "the ground script spawning a walker": Case(
        lambda world: _ground_script_fires(world, ground_target=1),
        EVERY_FRAME + ("groundscript_spawn_type10",), ("groundscript_spawn_type0f",)),
    "the ground script spawning a diver": Case(
        lambda world: _ground_script_fires(world, ground_target=0),
        EVERY_FRAME + ("groundscript_spawn_type0f",), ("groundscript_spawn_type10",),
        DECLARED_REGISTERS_FOR_THE_DIVER),
    "the ground script with a mothership pending": Case(
        lambda world: _ground_script_fires(world, ground_target=1, mothership_pending=1),
        EVERY_FRAME + ("groundscript_spawn_type10",),
        ("wavescript_spawn_wave", "wavescript_spawn_trio_type0e")),

    # ---- the player's six shot slots ----------------------------------------------------------
    "a player seeker steered and kept": Case(
        lambda world: _player_shot(frame.SHOT_TYPE_SEEKER),
        EVERY_FRAME + ("seeker_update",), ("homing_missile_update", "shot_retire_kind32")),
    "a player missile steered and kept": Case(
        lambda world: _player_shot(frame.SHOT_TYPE_MISSILE),
        EVERY_FRAME + ("homing_missile_update",), ("seeker_update", "shot_retire_kind32")),
    "a player seeker retired outside its box": Case(
        lambda world: _player_shot(frame.SHOT_TYPE_SEEKER, x=0x10),
        EVERY_FRAME + ("seeker_update", "shot_retire_kind32")),

    # ---- the three launch arms of spawn_enemy_shot ---------------------------------------------
    "an enemy launching an aimed shot": Case(
        lambda world: _firing_enemy(CAN_FIRE_TYPE, fire_flags=0),
        EVERY_FRAME + ("entity_type_in_mask", "angle_to_target",
                       "entity_set_velocity_from_angle")),
    "an enemy launching a homing shot": Case(
        lambda world: _firing_enemy(HOMING_CLASS_TYPE, fire_flags=1 << ENEMY_FIRE_BIT_STEERED),
        EVERY_FRAME + ("entity_type_in_mask", "angle_to_target",
                       "entity_set_velocity_from_angle")),
    "an enemy drawing for a halved homing chance": Case(
        lambda world: _firing_enemy(HOMING_CLASS_TYPE,
                                    fire_flags=(1 << ENEMY_FIRE_BIT_STEERED)
                                               | (1 << ENEMY_FIRE_BIT_HALVED)),
        EVERY_FRAME + ("entity_type_in_mask", "angle_to_target",
                       "entity_set_velocity_from_angle")),
    "an enemy launching a seeker": Case(
        lambda world: _firing_enemy(SEEKER_CLASS_TYPE, fire_flags=0),
        EVERY_FRAME + ("entity_type_in_mask", "entity_set_velocity_from_angle"),
        ("angle_to_target",)),

    # ---- the tick pass over the three enemy shot slots -----------------------------------------
    "an enemy seeker steered": Case(
        lambda world: _enemy_shot_slots(alive=1, shot_type=ENEMY_SHOT_TYPE_SEEKER,
                                        ttl=SHOT_TTL_HEALTHY),
        EVERY_FRAME + ("entity_steer_toward_target", "entity_kill_if_offscreen"),
        ("enemy_morph_to_type6",)),
    "an enemy seeker expiring into a puff": Case(
        lambda world: _enemy_shot_slots(alive=1, shot_type=ENEMY_SHOT_TYPE_SEEKER,
                                        ttl=SHOT_TTL_LAST),
        EVERY_FRAME + ("enemy_morph_to_type6",), ("entity_steer_toward_target",)),
    "an enemy homing shot steered": Case(
        lambda world: _enemy_shot_slots(alive=1, shot_type=ENEMY_SHOT_TYPE_HOMING,
                                        ttl=SHOT_TTL_HEALTHY),
        EVERY_FRAME + ("entity_steer_toward_target", "entity_kill_if_offscreen"),
        ("enemy_morph_to_type6",)),
    "an enemy homing shot expiring": Case(
        lambda world: _enemy_shot_slots(alive=1, shot_type=ENEMY_SHOT_TYPE_HOMING,
                                        ttl=SHOT_TTL_LAST),
        EVERY_FRAME, ("entity_steer_toward_target", "enemy_morph_to_type6")),
    "an enemy aimed shot drifting": Case(
        lambda world: _enemy_shot_slots(alive=1, shot_type=ENEMY_SHOT_TYPE_AIMED),
        EVERY_FRAME + ("entity_apply_velocity", "entity_kill_if_offscreen"),
        ("entity_steer_toward_target", "enemy_morph_to_type6")),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_twin_takes_every_arm_the_c_does(name):
    """One staged arm of the stage, compared whole, with the doors it names asserted reached.

    The arms here are the ones a dozen played frames of one section cannot walk: a script record
    fires once every few hundred frames, a boss encounter is the end of a section, and an enemy
    launch needs a live enemy of the right class with a free shot slot. Each case's `reaches` is
    what turns "the two images agree" into "the two images agree ON THIS ARM".
    """
    case = CASES[name]
    world = frame.world(0, frame.WORLD_START)
    leaves_the_image_where_the_c_does(world, case.extra(world), reaches=case.reaches,
                                      avoids=case.avoids, registers=case.registers)


def test_the_cases_between_them_reach_every_door_this_twin_names():
    """...and the other direction: no door of the twin's is left undriven.

    The `.S` is the source of truth — its `.equ ZY_DOOR_*` lines are what the stubs jump to — so a
    door added to the twin with no case behind it fails HERE, where the omission is, rather than
    silently widening the untested surface. The `EVERY_FRAME` names count because the played sweep
    and every case above assert them.
    """
    declared = set(common.door_equates_by_file()[SPAWN_S])
    assert declared, f"{SPAWN_S.name} declares no `.equ ZY_DOOR_*` — the scan found nothing"
    driven = set(EVERY_FRAME).union(*(set(case.reaches) for case in CASES.values()))
    assert declared <= driven, (
        f"frame_spawn.S reaches {sorted(declared - driven)} through the door and no case in this "
        f"file names them, so nothing here proves the stub marshals its arguments")


# ============================================================ the two register parameters

# Two values of `ground_spawn_y_register` a whole high word apart. Nothing the shipped game can do
# tells them apart — see the case below — so they are the CONTROL for that, not a sweep.
GROUND_Y_REGISTERS = (0x00000000, 0xffe00000)


def test_the_carried_y_register_reaches_the_spawner_and_no_value_of_it_is_observable():
    """`ground_spawn_y_register` on the one path where the wave-script block writes no D7 — and the
    honest statement of what that pins, which is LESS than the name would suggest.

    `include/frame.h` names three paths on which the parameter is the answer, and this is the one a
    case can hold still: a mothership pending skips the whole attack script, so the D7 that reaches
    `groundscript_spawn_type10` is the stage's own argument. The `reaches` assertion is what proves
    the case gets there at all.

    **AND THE TWO VALUES LEAVE THE SAME IMAGE — MEASURED, not assumed.** `groundscript_spawn`
    (src/enemy.c) reads the register in ONE place, `set_low_word(y_register, scripted_y + 0x20)`
    followed by `if (spawn_y == 0) return`: the low word is overwritten, so only the HIGH word can
    matter, and it can only matter when the low word comes out zero — which needs a scripted y of
    exactly 0xffe0. `test_frame.py::test_no_shipped_ground_script_can_make_the_spawner_read_its_
    carried_register` walks every record of all thirteen shipped ground scripts and finds none, so
    the guard is UNREACHABLE from the game's own data. Fabricating a record to reach it is what this
    workspace's rules forbid; STATUS.md carries the residual instead.

    So the equality below is asserted rather than lamented: it is the positive control that says the
    twin's handling of this register and the C's are indistinguishable ON THE DATA THAT SHIPS, and
    that a mutation to either would have to be caught somewhere else. What the case DOES pin is the
    whole rest of a mothership-pending frame that fires the ground script — the twin's image against
    the C's, byte for byte, at two different arguments.
    """
    world = frame.world(0, frame.WORLD_START)
    extra = _ground_script_fires(world, ground_target=1, mothership_pending=1)
    chance, _oracle_y = frame.carried_registers(_staged(world, extra), ORIGINAL_ENTRY)
    images = [leaves_the_image_where_the_c_does(
                  world, extra, reaches=("groundscript_spawn_type10",),
                  avoids=("wavescript_spawn_wave", "wavescript_spawn_trio_type0e"),
                  registers=(chance, ground_y)).image
              for ground_y in GROUND_Y_REGISTERS]
    assert images[0] == images[1], (
        "two ground_spawn_y_register values a high word apart left DIFFERENT images, so the "
        "spawner's whole-longword guard is reachable after all — which is the day this residual "
        "closes. Turn this into a sweep that pins the register, and update STATUS.md")


# The generator state a fire case starts from has to satisfy TWO draws before the chance compare is
# reached at all — the slot pick and then `rand16 & 3 == 0` — so it is searched for rather than
# seeded. The mirror below is `src/rng.c`'s loop, and `test_enemy.py::_rand16_step` is its sibling;
# like that one it is used ONLY to CHOOSE a starting state and never to assert an answer. If it were
# wrong the search would return a state that does not reach the compare, and the case's own "the two
# chance bytes must differ" assertion would fail rather than pass vacuously.
RNG_TAP_MASK = 0x1d872b41                # src/rng.c
RNG_STEP_BITS = 16


def _rand16_step(state):
    result = 0
    for _ in range(RNG_STEP_BITS):
        bit = state >> 31
        state = (state << 1) & 0xffffffff
        if bit:
            state ^= RNG_TAP_MASK
        result = ((result << 1) | bit) & 0xffff
    return result, state


def _state_reaching_the_chance_compare():
    """A generator state whose second draw passes the one-frame-in-four roll.

    Walked RANDOMLY for `test_enemy.py`'s reason: the generator hands back the bits that leave the
    TOP of the state, so every state below 0x8000 draws zero and a sequential scan would only ever
    find the smallest few.
    """
    rng = random.Random(0x1167c)
    for _try in range(1 << 16):
        state = rng.randrange(1, 1 << 32)
        _pick, after_pick = _rand16_step(state)
        roll, _after_roll = _rand16_step(after_pick)
        if roll & ENEMY_FIRE_ROLL_MASK == 0:
            return state
    raise AssertionError("no generator state reaches the chance compare — the mirror is wrong")


STATE_REACHING_THE_CHANCE_COMPARE = _state_reaching_the_chance_compare()
# The chance byte is SIGNED and compared `>=` against a draw of 0..0x1f, so 0x7f always fires and
# 0x80 (-128) never does. Poked at two indexes a whole high byte apart, so the case's two register
# values read two different bytes.
CHANCE_ALWAYS, CHANCE_NEVER = 0x7f, 0x80
CHANCE_INDEX_HIGH_BYTES = (0x0000, 0x0100)


def test_the_chance_index_register_keeps_the_callers_high_byte():
    """`chance_index_register` DRIVEN: the section is loaded with `move.b` into D1's low byte and
    the table is indexed with `d1.w` on the very next instruction, so the word offset really is
    (caller's D1 & 0xff00) | section.

    The two runs poke the chance byte at the two indexes the two high bytes name — one that always
    fires and one that never does — so a twin that had spelt the index as an `ext.w`, or as the bare
    section, would read the SAME byte both times and leave the same image. The images must differ.

    The boss flag is DOWN here, unlike the launch cases above, because it is what the chance gate is
    behind; the generator state is chosen so the roll in front of the compare passes.
    """
    world = frame.world(0, frame.WORLD_START)
    section = world[frame.A_LEVEL_SECTION]
    extra = _firing_enemy(CAN_FIRE_TYPE, fire_flags=1)
    extra[frame.A_MOTHERSHIP_READY] = b"\x00"
    extra[A_RNG_LFSR_STATE] = STATE_REACHING_THE_CHANCE_COMPARE.to_bytes(4, "big")
    for high, chance in zip(CHANCE_INDEX_HIGH_BYTES, (CHANCE_ALWAYS, CHANCE_NEVER)):
        extra[A_ENEMY_FIRE_CHANCE_TABLE + high + section] = bytes([chance])

    images = [leaves_the_image_where_the_c_does(world, extra, registers=(high | section, 0)).image
              for high in CHANCE_INDEX_HIGH_BYTES]
    assert images[0] != images[1], (
        "both chance-index high bytes left the same image, so the case never reached the compare "
        "and a twin that dropped D1's high byte would pass. The roll in front of it is the likely "
        "gate — check STATE_REACHING_THE_CHANCE_COMPARE")


# ============================================================ arms no played frame reaches

# Stepping up from rest, one step short of the peak (so this frame turns round), stepping down from
# well above zero, and one step short of zero (so this frame turns back).
CHARGE_FLASH_SWEEP = ((0, 0), (0, frame.CHARGE_FLASH_PEAK - frame.CHARGE_FLASH_STEP),
                      (1, 2 * frame.CHARGE_FLASH_STEP), (1, frame.CHARGE_FLASH_STEP))


@pytest.mark.parametrize("direction,shadow", CHARGE_FLASH_SWEEP)
def test_the_twin_walks_the_charged_flash_both_ways_and_turns_at_both_ends(direction, shadow):
    """The palette flash's four arms: stepping up, reaching the peak and turning, stepping down, and
    reaching zero and turning back. A played frame never reaches any of them — the ship has to be
    holding a charged shot, and `test_frame.py`'s own charge case is what proves the C.

    The pass is gated on the odd animation phase being CLEAR, so that byte is poked too; otherwise
    every one of the four would take the same early return.
    """
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_FIRE_CHARGED: b"\x01", frame.A_EXPLOSION_PHASE_ODD: b"\x00",
         frame.A_CHARGE_FLASH_DIR: bytes([direction]),
         frame.A_PALETTE_HW_SHADOW: shadow.to_bytes(2, "big")},
        reaches=EVERY_FRAME)


@pytest.mark.parametrize("x", (0x100, frame.BULLET_RETIRE_X - BULLET_STEP_X - 1,
                               frame.BULLET_RETIRE_X - BULLET_STEP_X))
def test_the_twin_retires_a_bullet_at_the_screens_edge(x):
    """`addi.w #$c,0(a3)` then `cmpi.w #$180` + `blt`: a bullet is stepped right every frame and
    retired on the frame the step carries it to or past BULLET_RETIRE_X — which is also where its
    live count is given back. The x either side of that edge is what separates the two arms."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START),
        {frame.A_ENTITY_TABLE + frame.ENTITY_TYPE: bytes([frame.BULLET_TYPE]),
         frame.A_ENTITY_TABLE + frame.ENTITY_ALIVE: b"\x01",
         frame.A_ENTITY_TABLE + frame.ENTITY_X: x.to_bytes(2, "big"),
         frame.A_ACTIVE_COUNT_TYPE34: b"\x05"},
        reaches=EVERY_FRAME)


# The four `cmpi.w` + branch pairs of the player-shot box, swept either side of each edge. The steer
# runs BEFORE the compare and moves the shot, so a band is what puts a case exactly on an edge —
# `test_frame.py::test_a_steered_shot_is_retired_outside_its_box` says so at length and this is the
# same sweep, narrowed to the two points that matter most per edge because each case here costs a
# whole-image comparison.
BOX_EDGE_MARGIN = 2
BOX_EDGE_SWEEP = tuple((x, 0x50) for edge in (frame.SHOT_X_MIN, frame.SHOT_X_MAX)
                       for x in (edge - BOX_EDGE_MARGIN, edge + BOX_EDGE_MARGIN)) \
    + tuple((0x80, y) for edge in (frame.SHOT_Y_MIN, frame.SHOT_Y_MAX)
            for y in (edge - BOX_EDGE_MARGIN, edge + BOX_EDGE_MARGIN))


@pytest.mark.parametrize("x,y", BOX_EDGE_SWEEP)
def test_the_twin_retires_a_steered_shot_outside_its_box(x, y):
    """All four edges of the box the six player shot slots are held inside, from both sides."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START), _player_shot(frame.SHOT_TYPE_SEEKER, x=x, y=y),
        reaches=EVERY_FRAME + ("seeker_update",))


@pytest.mark.parametrize("x", (0x81, 0x8f, 0xff))
def test_the_twin_forces_a_steered_shot_to_an_even_column(x):
    """`bclr #0,1(a3)` — the LOW BYTE of ENTITY_X, so a shot is aligned to two pixels after its
    steering update and before its box test. An odd x well inside the box is the only input that
    separates the clear from a no-op."""
    leaves_the_image_where_the_c_does(
        frame.world(0, frame.WORLD_START), _player_shot(frame.SHOT_TYPE_SEEKER, x=x),
        reaches=EVERY_FRAME + ("seeker_update",), avoids=("shot_retire_kind32",))


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
def test_the_twin_fires_only_from_a_live_unexploding_enemy(alive):
    """`tst.b 14(a1)` then `btst #7,d2`: a dead record launches nothing, and neither does one already
    exploding — which is what 0x80 and 0xff separate from "any non-zero byte"."""
    extra = _firing_enemy(CAN_FIRE_TYPE, fire_flags=0)
    extra.update(_enemy_slots({frame.ENTITY_ALIVE: bytes([alive])}))
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra,
                                      reaches=EVERY_FRAME)


@pytest.mark.parametrize("taken", (0, 1, 2, 3))
def test_the_twin_launches_into_the_first_free_enemy_shot_slot(taken):
    """The launch scan walks the three slots and takes the first whose alive byte is zero; with all
    three taken it launches nothing, while the tick pass below still runs on every one of them."""
    extra = _firing_enemy(CAN_FIRE_TYPE, fire_flags=0)
    for slot in range(taken):
        extra[frame.A_ENEMY_SHOT_SLOTS + frame.ENTITY_STRIDE * slot + frame.ENTITY_ALIVE] = b"\x01"
    leaves_the_image_where_the_c_does(frame.world(0, frame.WORLD_START), extra,
                                      reaches=EVERY_FRAME)


def test_the_twin_ticks_the_three_shot_kinds_in_every_rotation():
    """A seeker, a homing shot and one of neither kind in a single call, and the same set rotated —
    which is what separates "ticked by type" from "ticked by position"."""
    world = frame.world(0, frame.WORLD_START)
    kinds = (ENEMY_SHOT_TYPE_AIMED, ENEMY_SHOT_TYPE_HOMING, ENEMY_SHOT_TYPE_SEEKER)
    for rotation in range(len(kinds)):
        extra = _enemy_shot_slots(alive=1)
        for slot in range(ENEMY_SHOT_SLOTS):
            at = frame.A_ENEMY_SHOT_SLOTS + frame.ENTITY_STRIDE * slot
            extra[at + frame.ENTITY_TYPE] = bytes([kinds[(slot + rotation) % len(kinds)]])
        leaves_the_image_where_the_c_does(
            world, extra,
            reaches=EVERY_FRAME + ("entity_steer_toward_target", "entity_apply_velocity",
                                   "entity_kill_if_offscreen"))


# ============================================================ reading frame_spawn.S back

# The scrapers are the family's (`asm_frame_common`): four twins ask the same three questions of
# their own `.S` and `.o`, and four copies of the parsing would be four ways to disagree about what
# an `.equ` or an `| 0xxxxx` comment is. What stays here is what is THIS file's: which object, which
# span of the original, and the count below.
def _spawn_equates():
    return common.equates(SPAWN_OBJ)


# THE %a5 GLOBAL WINDOW. Both checks are `asm_frame_common`'s — one phrasing, because all four
# frame suites ask the same question of their own `.S`, and the four hand-copies this replaced had
# already started to drift in their failure text. What stays here is what is THIS twin's: which
# file, and how many globals it reaches.
# The base register this twin reserves for `image + FGB`. DECLARED rather than defaulted:
# `asm_frame_common` has no default, because a suite that named the wrong register would find no
# operands and pass the window pin over an empty list.
WINDOW_REGISTER = "%a5"


WINDOWED_OPERAND_COUNT = 27


def test_the_window_scan_reads_every_global_this_twin_names():
    """The scan's positive control. `window_pin_failures` is vacuous over an empty operand list, so
    a twin whose operand shape stopped matching — a different window register, a differently named
    origin — would pass the pin below by reaching no globals at all."""
    failure = common.window_scan_failure(SPAWN_S, WINDOWED_OPERAND_COUNT,
                                       WINDOW_REGISTER)
    assert failure is None, failure


def test_every_windowed_global_is_inside_the_signed_displacement():
    """THE WHOLE OF WHAT MAKES `%a5 = image + FGB` LEGAL for this twin: gas assembles a global
    outside the signed 16-bit window into a TRUNCATED displacement with no diagnostic, and the twin
    then reads or writes a wild address that the differential reports as a pixel diff a long way
    from its cause."""
    failures = common.window_pin_failures(SPAWN_S, WINDOW_REGISTER)
    assert not failures, "\n".join(failures)


def test_the_twin_transcribes_the_original_instruction_for_instruction():
    """EVERY INSTRUCTION OF THE ORIGINAL, ONCE, IN ORDER — and this stands where the byte pin stands
    for the leaf twins.

    A byte pin is not available here (frame_spawn.S's header says why: almost every instruction of
    the stage names a global, position-independence re-encodes all of them, and gas re-spells the
    immediate-to-Dn forms and folds a zero displacement). What survives that translation untouched is
    the SEQUENCE, so this compares the two address lists whole: the original's, scraped out of
    ../../out/prg_dis.txt, against frame_spawn.S's own `| address` comments.

    It catches what a differential cannot: an instruction dropped on a path the game's own data never
    takes — the seven DEAD ones at 0x119ba..0x119d8 are exactly that — one transcribed twice, a pass
    moved in front of another, or a comment left naming an address the line no longer transcribes.
    """
    failure = common.transcription_failure(SPAWN_S, ORIGINAL_ENTRY, ORIGINAL_END)
    assert failure is None, failure


# ============================================================ what the twin COSTS

# READ THIS BEFORE READING A RATIO HERE, because it is not the reading the leaf twin suites take.
#
# THE DOOR CHARGES NOTHING FOR A C BODY. `bench_loop` stops at the door address, the harness calls
# the host function and resumes: the stub's `jsr` and `rts` really execute and are charged, the
# core's body does not exist on this side and costs nothing. The ORIGINAL, clocked over the same
# span, executes its twenty-five callees in full — and this stage's callees are the whole of the
# enemy animate and move passes, which is most of its work. So `twin / original` here is NOT a
# like-for-like fidelity ratio and must not be read as one:
#
#   the twin's number   = the twin's OWN instructions, C-ABI frame and twenty-three trampolines
#                         included
#   the original's      = its own instructions AND everything its forty `bsr`s reach
#
# WHICH IS WHY EVERY BAR BELOW IS FAR UNDER 1.00x, and why the number to watch is the SLACK rather
# than the ratio. Both sides are Musashi cycle counts over one fixed staged world, so each reading is
# exact and repeatable, and the margins are a handful of CYCLES: one extra register in the prologue's
# `movem` is 16 cycles round trip and reddens every band.
#
#   band                  original     twin     delta   measured       bar   slack
#   an ordinary frame        4,688    2,626    -2,062    0.56015   0.56156  6.6 cyc
#   an asteroid section      5,670    3,058    -2,612    0.53933   0.54056  7.0 cyc
#   a boss encounter        25,594    2,986   -22,608    0.11667   0.11694  6.9 cyc
#
# The boss band's original is five times the ordinary one's for the same reason its ratio is a fifth:
# `mothership_move_and_place` and `mothership_draw` are twenty thousand cycles the ORIGINAL pays and
# the door does not. Nothing about the twin changed between the three rows.
#
# The table is filled in from the run rather than predicted: frame_spawn.S's header names two
# effects pulling in opposite directions (base-relative globals and gas's folded zero displacements
# are CHEAPER than the original's absolute-long and d16 forms; every trampoline is dearer than the
# `bsr` it stands in for) and only the measurement settles where they land.
#
# THE SLACK IS SEVEN CYCLES, which is what makes these bars a gate rather than a restatement of
# today's number: one more register in the prologue's `movem` pair is 16 cycles and reddens all
# three. The measurement is deterministic — Musashi counts cycles and `frame.world` is the oracle's
# own output — so the margin is for a legitimate re-translation, not for noise.
COST_BARS = {"ordinary": 0.56156, "asteroid": 0.54056, "boss": 0.11694}


def _cost_case(extra, band):
    """Clock the ORIGINAL and the twin over one staged world, and hold the twin to that band's bar.

    The twin goes through the differential on the way, so a cost reading can never be taken from a
    call that computed the wrong thing. The original is entered with the SAME two registers the twin
    is given, because they are what the stage's own `bsr`s pass on.
    """
    world = frame.world(0, frame.WORLD_START)
    staged = _staged(world, extra)
    chance, ground_y = frame.carried_registers(staged, ORIGINAL_ENTRY)
    run = leaves_the_image_where_the_c_does(world, extra, registers=(chance, ground_y))
    _final, _writes, regs = emu.run(bytearray(staged), ORIGINAL_ENTRY,
                                    {"d1": chance, "d7": ground_y}, stop_pc=ORIGINAL_END,
                                    max_insns=frame.FRAME_MAX_INSNS)
    asm_twins.assert_within_the_bar(f"{TWIN} ({band})", regs["cycles"], run.cycles,
                                    COST_BARS[band])


def test_the_twin_costs_what_it_costs_on_an_ordinary_frame():
    """The band every frame of the game takes: the whole stage, its six unconditional door calls,
    out at 0x11902."""
    _cost_case(None, "ordinary")


def test_the_twin_costs_what_it_costs_in_an_asteroid_section():
    """Its own bar, because the asteroid arm adds three whole callees and the trampolines for
    them — a shared bar would have to be the loosest of the two."""
    _cost_case({frame.A_ASTEROID_SECTION_FLAG: b"\x01"}, "asteroid")


def test_the_twin_costs_what_it_costs_in_a_boss_encounter():
    """The boss tail — two more door calls and the phase timer's `addi.l` — which is the one band
    that does NOT take the early return at 0x118ec."""
    _cost_case({frame.A_BOSS_SEQUENCE_ACTIVE: b"\x01"}, "boss")


# ============================================================ the restated constants

_HEADER_DEFINE = re.compile(r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)u?\b", re.M)


@functools.lru_cache(maxsize=None)
def _header_defines():
    """{name: value} for every `#define <NAME> <literal>` in include/*.h."""
    found = {}
    for header in sorted((common.REC / "include").glob("*.h")):
        for name, literal in _HEADER_DEFINE.findall(header.read_text()):
            found.setdefault(name, (int(literal, 0), header.name))
    return found


@pytest.mark.parametrize("name", sorted(MIRRORED_ADDRESSES))
def test_the_addresses_this_file_names_are_the_headers(name):
    """Every literal MIRRORED_ADDRESSES restates, against the header that defines it.

    This suite pokes addresses `include/` owns, and it cannot `#include` them. CLAUDE.md §5's rule
    for that case is one canonical definition plus a test pinning the copy equal — this is the test.
    Without it a header move leaves this file poking a byte nothing reads, the case stops driving
    the arm it is named for, and both shores agree on the untested path with nothing red.
    """
    headers = _header_defines()
    assert name in headers, (
        f"no include/*.h defines {name}, so this file's copy of it is pinned to nothing. Either the "
        f"header renamed it — in which case follow the rename — or the value never had a canonical "
        f"home and should not be in MIRRORED_ADDRESSES")
    expected, header = headers[name]
    assert MIRRORED_ADDRESSES[name] == expected, (
        f"this file restates {name} as {MIRRORED_ADDRESSES[name]:#x}; include/{header} defines it "
        f"as {expected:#x}")
