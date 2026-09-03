"""Differential tests for the game's per-frame loop (src/frame.c).

EVERY CASE HERE IS A CHECKPOINT RUN over a WORLD-STAGED image, and both halves of that need saying.

*Checkpoint*, because the loop never returns: it runs from 0x10f4e to the `bra.w $10f4e` at 0x1296a
and there is not an `rts` between them. So each case names an entry PC and a stop PC and the
differential diffs the image THERE (`docs/agent-playbook.md` §5), exactly as `test_init.py` does for
the boot chain.

*World-staged*, because a frame of Zynaps reads almost everything the program owns — the entity
table, the eight backdrop pages, the map, the tile set, every sprite bank, the two framebuffers, the
panel, the scripts — and a hand-built image of that would be a fabrication with the shape of a test.
So the images here are the GAME'S OWN: `test_init.py`'s section staging is driven through the
ORIGINAL's `section_load_assets`, `section_restart_prologue` and `section_start_prefill`, then
through the section-start tail, and then stepped frame by frame BY THE ORACLE. Every case runs on a
state the real program produced (`docs/agent-playbook.md` §5, "World-staging").

WHAT THE CASES POKE, they poke over that world, and only three kinds of byte: the joystick byte the
IKBD interrupt publishes, the game-state bytes that select an arm the shipped level data does not
reach within the frames a case can afford (the selected weapon, the boss flag, the pause scancode),
and the two schedule entries below. Nothing here builds a record.

THE TWO BUSY-WAITS. A frame ends by spinning on `A_raster_phase` and then on `A_vbl_wait_flag`,
neither of which any instruction of the loop writes — they are the Timer B and vertical-blank
handlers' bytes. Both sides go through the kit's scheduled-write model (TRAP_MODEL.md, Phase 8) at
the PCs `FRAME_SCHED`/`WAIT_SITES` name, so the two loops turn the same number of times on both
shores and `harness.differential` compares those counts site by site.
"""
import ctypes
import functools
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

import test_init

# ---- the five slices, as (entry, stop). Each entry is pinned by name in ENTRY_PROLOGUES below ----
ENTRY_FRAME_HEAD = 0x10f4e            # frame_panel_scroll_and_ship_stage
ENTRY_DRONE_AND_FIRE = 0x113c0        # ...its fall-through exit, and the next slice's entry
ENTRY_SPAWN_AND_MOVE = 0x1167c        # ...its OTHER exit, and the next slice's entry
ENTRY_DRAW_AND_COLLIDE = 0x11c00
ENTRY_RESOLVE = 0x11d30
STOP_FRAME = 0x1296a                  # the `bra.w $10f4e` that closes the loop

# Inside the draw stage: where its sprite pass ends and its all-pairs collision walk begins — the
# `move.w #$14,d0` at 0x11c56 that starts the mask-table clear. PUBLIC and spelt once, because two
# instruments run the original to exactly here to read the pixel-hit flags the sprite pass set
# (`test_asm_frame_draw.py`'s positive control and `atari/bench_tier.py`'s stage breakdown), and a
# second spelling would let one of them stop mid-pass and count a different set of pairs.
SPRITE_PASS_END_PC = 0x11c56

# The four addresses the resolve stage leaves through instead, and the enum value src/frame.c
# answers with for each. STOP_FRAME is the fifth.
EXIT_TITLE = 0x10500
EXIT_RELOAD_SECTION = 0x1083a
EXIT_RESTART_SECTION = 0x10b6e
EXIT_ADVANCE_SECTION = 0x10814
FRAME_EXIT_CODE = {EXIT_TITLE: 0, EXIT_RELOAD_SECTION: 1, EXIT_RESTART_SECTION: 2,
                   EXIT_ADVANCE_SECTION: 3, STOP_FRAME: 4}
# ...and back, so a helper answers with the address the CANDIDATE named rather than with the one its
# caller asked for — an assertion on the latter compares a value to itself.
FRAME_EXIT_ADDRESS = {code: address for address, code in FRAME_EXIT_CODE.items()}

# Where the two registers `frame_spawn_and_move_stage` cannot derive are read — see its docstring.
PROBE_CHANCE_INDEX_PC = 0x118cc       # the `bsr` into enemy_fire_and_update_shots
PROBE_GROUND_SPAWN_PC = 0x11818       # ...and into groundscript_spawn_type10

# ---- mirrors of include/frame.h ----
A_JOYSTICK_STATE = 0x19681
A_STARFIELD_TABLE = 0x179fa
A_STARFIELD_PIXEL_MASKS = 0x17a42
A_STARFIELD_LAYER2_PHASE = 0x198a9
A_STARFIELD_LAYER3_COUNTDOWN = 0x198aa
A_EXPLOSION_PHASE_EVEN = 0x198ad
A_EXPLOSION_LARGE_FRAME_PTRS = 0x1922c
A_DYING_PLAYER_SECTION_INDEX = 0x19896
A_PLAYER_RECORDS = 0x19f02
A_SECTION_END_DELAY_COUNTER = 0x19ac0
A_ACTIVE_COUNT_TYPE34 = 0x19909
A_MOTHERSHIP_WAVE_CLEAR_COUNT = 0x19915
A_FIRE_BUTTON_HELD = 0x198b9
A_FIRE_CHARGE_COUNTER = 0x19901
A_CHARGE_FLASH_DIR = 0x19903
A_SHIP_POS_HISTORY = 0x19f86
A_SHIP_POS_HISTORY_INDEX = 0x198ff
A_PANEL_LOGO_COUNTDOWN = 0x19dce
A_BULLET_FIRE_TOGGLE = 0x198c7
A_UNUSED_SECTION_END_FLAG = 0x19ce5
A_SCROLL_BLIT_JUMP_TABLE = 0x179aa
A_SHIP_SPRITE_BANK = 0x577fe
A_WAVE_ALIEN_SPRITE_A = 0x54ffe
A_WAVE_ALIEN_SPRITE_B = 0x563fe
A_POWERUP_CAPSULE_SPRITE = 0x5f3be
A_EXPLOSION_LARGE_SPRITE = 0x61b5e
A_PLAYER_BULLET_SPRITE = 0x62a5e
A_TRAIL_DRONE_SPRITE = 0x6a61e
HW_MFP_IERA = 0xfffa09
KEY_SCANCODE_SPACE = 0x39
PANEL_LOGO_PERIOD = 0x1f4
MOTHERSHIP_TRIGGER_SCROLL_POS = 0xc80
SHIP_POS_HISTORY_ENTRIES = 0xa
SHIP_POS_HISTORY_ENTRY_BYTES = 4
EXPLOSION_CREDIT_TAG_OFFSET = 0x14
TRAIL_DRONE_OFFSET_PACKED = 0x800005
TYPE_TRAIL_DRONE = 0x35
FIRE_CHARGE_FULL = 8
CHARGE_FLASH_STEP = 0x111
CHARGE_FLASH_PEAK = 0x444
WEAPON_KIND_BOMB, WEAPON_KIND_MISSILE, WEAPON_BULLET, WEAPON_KIND_SEEKER = 1, 2, 3, 4
BULLET_TYPE = 0x34
BULLET_RETIRE_X = 0x180
BULLET_SOUND = 0xe
SHOT_X_MIN = 0x30
SHOT_X_MAX = 0x180
SHOT_Y_MIN = 0x15
SHOT_Y_MAX = 0xb0
ENTITY_SLOTS = 0x14
COLLISION_ROW_BYTES = 4                # include/collision.h
EXPLOSION_GROUP_MEMBERS = 6
SHIP_DEATH_EXPLOSION_GROUP = 1         # include/weapon.h
ENEMY_SLOT_COUNT = 8                   # include/enemy.h
SCRIPT_TRIGGER_LOOKAHEAD = 0x24
MOTHERSHIP_TURN_SPEED_OFF = 0x22
MOTHERSHIP_TURN_FLAG_OFF = 0x26
PLAYER_SAVE_LIVES = 4
PLAYER_SAVE_SECTION = 5
COLLISION_MASK_LONGS = ENTITY_SLOTS + 1
ENTITY_INDEX_TRAIL_DRONE = 0x13
ENTITY_INDEX_SHIP = 17
SHIP_SHADOW_SLOT = 18
ENEMY_SHOT_SLOT_FIRST = 6
ENEMY_SLOT_FIRST = 9
GUNSIGHT_ENEMY_MASK = 0x1fe00
SHIP_RECORD_MASK = 0x60000
EXPLOSION_PART_TYPE = 0x64
EXPLOSION_TYPE_LARGE = 0x65
EXPLOSION_LAST_FRAME = 0x0d
EXPLOSION_FRAME_PTR_BYTES = 4
EXPLOSION_DONE_FRAME = 0x0d
TYPE_POWERUP_CAPSULE = 0x11
POWERUP_CAPSULE_SOUND = 0x1c
ENEMY_HIT_SOUND = 0x2c
EXTRA_LIFE_SOUND = 0x10               # include/score.h
STARFIELD_LAYERS = 3
STARFIELD_STARS = 6
STARFIELD_ENTRY_BYTES = 4
STARFIELD_RESPAWN_X = 0x13f
STARFIELD_LAYER3_PERIOD = 3
POWERUP_DECAY_TICKS = 0x3e8
FRAME_RASTER_WAIT_PC = 0x126ee
FRAME_VBL_WAIT_PC = 0x1270c
FRAME_RASTER_PHASE_READY = 1
FRAME_VBL_WAIT_DONE = 0
IKBD_CMD_INTERROGATE_JOYSTICK = 0x16
PLAYER_RECORD_BYTES = 0xe
PLAYER_SWAP_ATTEMPTS = 3
MOTHERSHIP_TURN_FRAME = 0x5dc
MOTHERSHIP_LEAVE_FRAME = 0x640
MOTHERSHIP_WAVE_CLEARS_TO_END = 2
BUS_ERROR_VECTOR = 0x8

# ---- mirrors of the headers this subsystem borrows its state from ----
A_ENTITY_TABLE = 0x17a8e             # include/player.h
A_SHIP_RECORD_SHADOW = 0x17da6       # include/player.h
A_SHIP_TILT = 0x198b3                # include/player.h
A_SHIP_TILT_COUNTDOWN = 0x198b2      # include/player.h
A_SHIP_SPEED_LEVEL = 0x19907         # include/player.h
A_WEAPON_POWER_LEVEL = 0x19908       # include/player.h
A_PLAYER_RECORD = 0x17d7a            # include/enemy.h
A_ENEMY_SLOTS = 0x17c1a              # include/enemy.h
A_ENEMY_SHOT_SLOTS = 0x17b96         # include/enemy.h
A_ENTITY_GUNSIGHT = 0x17dd2          # include/weapon.h
A_SELECTED_WEAPON = 0x198b4          # include/weapon.h
A_SHIELD_LEVEL = 0x1990a             # include/weapon.h
A_ACTIVE_COUNT_TYPE32 = 0x1990b      # include/weapon.h
A_ACTIVE_COUNT_BOMBS = 0x1990c       # include/weapon.h
A_ACTIVE_COUNT_SEEKERS = 0x1990d     # include/weapon.h
A_SEEKER_LOCK_TARGET_INDEX = 0x19917  # include/weapon.h
A_SHIP_INVULNERABLE = 0x19912        # include/weapon.h
A_DEATH_EVENT_FLAGS = 0x198c4        # include/weapon.h
A_TRAIL_DRONE_ACTIVE = 0x19900       # include/weapon.h
SHOT_TYPE_MISSILE = 0x32             # include/weapon.h
SHOT_TYPE_BOMB = 0x33                # include/weapon.h
SHOT_TYPE_SEEKER = 0x36              # include/weapon.h
SHOT_TYPE_PUFF = 0x37                # include/weapon.h
A_EXPLOSION_GROUP_ACTIVE_BITS = 0x19670   # include/enemy.h
A_EXPLOSION_GROUP_MEMBERS = 0x19664       # include/enemy.h
A_EXPLOSION_PHASE_ODD = 0x198c5      # include/enemy.h
A_FIRE_CHARGED = 0x19902             # include/enemy.h
A_SCROLL_FROZEN = 0x198b1            # include/enemy.h
A_ENEMY_SEEKER_COOLDOWN = 0x19abf    # include/enemy.h
A_SQUADRON_KILL_COUNTERS = 0x198bb   # include/enemy.h
A_GROUND_SCRIPT_CURSOR = 0x1824a     # include/enemy.h
A_WAVE_SCRIPT_CURSOR = 0x1824e       # include/enemy.h
A_SQUADRON_SPAWN_ENABLED = 0x19aae   # include/enemy.h
A_BOSS_SEQUENCE_ACTIVE = 0x19aad     # include/sprite.h
A_MOTHERSHIP_READY = 0x198b0         # include/mothership.h
A_MOTHERSHIP_PREP_STAGE = 0x19911    # include/mothership.h
A_MOTHERSHIP_INDEX = 0x1987c         # include/init.h
A_MOTHERSHIP_PENDING = 0x198af       # include/init.h
A_MOTHERSHIP_PHASE_TIMER = 0x19efe   # include/mothership.h
A_MOTHERSHIP_OFFSCREEN = 0x19916     # include/mothership.h
A_BOSS_HITPOINTS = 0x19f44           # include/mothership.h
A_ENTITY_BOSS_PARTS = 0x18142        # include/mothership.h
A_ASTEROID_SECTION_FLAG = 0x198fd    # include/init.h
A_LEVEL_SECTION = 0x19895            # include/init.h
A_MAP_PAGE = 0x198a5                 # include/init.h
A_MAP_COLUMN = 0x198a6               # include/init.h
A_MAP_OFFSET = 0x1823e               # include/init.h
A_MAP_PTR = 0x18242                  # include/init.h
A_MAP_PAGE_TABLE = 0x1798a           # include/init.h
A_SCROLL_POS = 0x195cc               # include/init.h
A_KEY_SCANCODE = 0x19685             # include/init.h
A_PANEL_REDRAW_MASK = 0x19904        # include/hud.h
A_LIVES = 0x1991a                    # include/hud.h
A_CURRENT_PLAYER_INDEX = 0x1991b     # include/hud.h
A_POWERUP_CURSOR = 0x19905           # include/hud.h
A_POWER_GAUGE_DISPLAY = 0x198c3      # include/hud.h
A_PALETTE_HW_SHADOW = 0x18fc4        # include/irq.h
A_RASTER_PHASE = 0x198a8             # include/irq.h
A_VBL_WAIT_FLAG = 0x198a7            # include/irq.h
A_PALETTE_SWAP_COUNTDOWN = 0x19683   # include/irq.h
A_PALETTE_ROTATE_COUNTDOWN = 0x19684  # include/irq.h
A_SCREEN_BACK = 0x1797e              # include/video.h
A_ENTITY_COLLISION_MASKS = 0x18252   # include/collision.h
A_EXTRA_LIFE_THRESHOLD_BCD = 0x195d8  # include/score.h
A_PLAYER_SCORE_BCD = 0x195e0         # include/score.h
SCORE_BCD_BYTES = 4                  # include/score.h
A_ENEMY_PAIR_HITPOINTS = 0x19884     # include/enemy.h — one energy byte per boss PAIR
ENEMY_TYPE_BOSS_SEGMENT = 0x02       # include/frame.h
ENEMY_TYPE_BIG = 0x0e                # include/frame.h — explodes and pays SCORE_AWARD_ENEMY_BIG
A_SHIELD_DECAY_TIMER = 0x19dca       # include/weapon.h
A_SPEED_DECAY_TIMER = 0x19dc8        # include/weapon.h
A_WEAPON_DECAY_TIMER = 0x19dcc       # include/player.h
SCROLL_PHASES = 20                   # include/scroll.h
MAP_PAGES = 8                        # include/init.h
MAP_PAGE_PTR_BYTES = 4
SHIP_SPEED_ENTRY_BYTES = 8
SECTION_COUNT = 0x10                 # include/init.h
ENTITY_STRIDE = 0x2c                 # include/entity.h
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT = 0x00, 0x04, 0x08
ENTITY_SPRITE, ENTITY_ALIVE, ENTITY_PIXEL_HIT = 0x0a, 0x0e, 0x0f
ENTITY_TYPE, ENTITY_HP, ENTITY_ANIM_FRAME, ENTITY_SQUADRON = 0x11, 0x1a, 0x20, 0x21
EXPLOSION_PART_FRAME = 0x10               # include/enemy.h
PLAYER_SHOT_SLOTS = 6                # include/weapon.h
SHIP_SPRITE_GAP = 1600               # include/sprite.h
WEAPON_POWER_LEVEL_MIN = 2           # include/player.h
BOOT_SHIP_SOURCE = 0x577fe           # src/init.c

# The two scheduled stores that let a frame's two busy-waits end, and the PCs they trigger at.
FRAME_SCHED = ({"pc": FRAME_RASTER_WAIT_PC, "nth": 1, "addr": A_RASTER_PHASE, "width": 1,
                "value": FRAME_RASTER_PHASE_READY},
               {"pc": FRAME_VBL_WAIT_PC, "nth": 1, "addr": A_VBL_WAIT_FLAG, "width": 1,
                "value": FRAME_VBL_WAIT_DONE})
WAIT_SITES = (FRAME_RASTER_WAIT_PC, FRAME_VBL_WAIT_PC)

# The three pause spins, at the PCs the original re-reads the scancode at.
PAUSE_RELEASE_WAIT_PC = 0x10fe6
PAUSE_PRESS_WAIT_PC = 0x10ffe
PAUSE_SECOND_RELEASE_WAIT_PC = 0x11008

# A whole frame of Zynaps is around a million instructions with a full playfield behind it.
FRAME_MAX_INSNS = 40_000_000
# Everything the world image holds is below this: the program ends at 0x6e96e and the game's two
# hard-coded framebuffers end at 0x7fd00, which is also where test/abi.py's scratch map starts.
WORLD_BYTES = abi.STUB
DISK = harness.PRG.parent / "disk"

_u8p = ctypes.POINTER(ctypes.c_uint8)
for _sym, _args, _ret in (
        ("g_frame_panel_scroll_and_ship_stage", [_u8p], ctypes.c_uint32),
        ("g_frame_drone_and_fire_stage", [_u8p, ctypes.c_uint32, ctypes.c_uint32], None),
        ("g_frame_spawn_and_move_stage", [_u8p, ctypes.c_uint32, ctypes.c_uint32], None),
        ("g_frame_draw_objects_and_collide", [_u8p], None),
        ("g_frame_resolve_hits_and_game_state", [_u8p, ctypes.c_uint32], ctypes.c_uint32),
        ("g_frame_loop_once", [_u8p, ctypes.c_uint32, ctypes.c_uint32], ctypes.c_uint32)):
    getattr(harness._lib, _sym).argtypes = _args
    getattr(harness._lib, _sym).restype = _ret


# ============================================================ the world, and how it is built

def _stage_section(section):
    """The image the ORIGINAL leaves at the frame-loop head, for one level section.

    Four oracle runs, all of them slices `test_init.py` already verifies: the asset load, the
    per-life reset, the page pre-fill, and the section-start tail that ends at 0x10f4e. The tail
    polls the joystick until its fire bit is set, which is the one store scheduled here.
    """
    pokes, _handles = harness.stage_files(
        [(name, (DISK / name.upper()).read_bytes())
         for name in test_init._section_files(section)])
    pokes[A_LEVEL_SECTION] = bytes([section])
    image, _writes, _regs = emu.run(harness.make_image(pokes), test_init.ENTRY_SECTION_LOAD_ASSETS,
                                    {}, stop_pc=test_init.STOP_SECTION_LOAD_ASSETS,
                                    max_insns=test_init.SECTION_LOAD_MAX_INSNS)
    image = bytearray(image)
    for address, blob in test_init._front_end_pokes(seed=section).items():
        image[address:address + len(blob)] = blob
    image, _writes, _regs = emu.run(image, test_init.ENTRY_SECTION_RESTART_PROLOGUE, {},
                                    stop_pc=test_init.STOP_SECTION_START_PREFILL,
                                    max_insns=test_init.PREFILL_MAX_INSNS)
    image, _writes, _regs = emu.run(bytearray(image), test_init.STOP_SECTION_START_PREFILL, {},
                                    stop_pc=ENTRY_FRAME_HEAD, max_insns=FRAME_MAX_INSNS,
                                    schedule=[{"pc": SECTION_TAIL_FIRE_WAIT_PC, "nth": 2,
                                               "addr": A_JOYSTICK_STATE, "width": 1,
                                               "value": JOYSTICK_FIRE}],
                                    wait_sites=[SECTION_TAIL_FIRE_WAIT_PC])
    return bytearray(image)


SECTION_TAIL_FIRE_WAIT_PC = 0x10f2a   # `tst.b $19681` + `bpl` at the end of the section start
JOYSTICK_FIRE = 0x80

# The two names this battery borrows from test_init.py, checked at import so a rename over there
# fails HERE with a sentence instead of an AttributeError inside a case named for a frame slice.
# Both are underscore-private, which is exactly why nothing in test_init would otherwise signal the
# dependency — the same guard, for the same reason, as test_init.py's own over test_hud.
for _borrowed in ("_section_files", "_front_end_pokes"):
    assert hasattr(test_init, _borrowed), (
        f"test_frame.py's world staging reuses test_init.{_borrowed} to drive the section chain "
        f"over the real files; that name is gone, so either restore it or give this battery its "
        f"own staging")


def advance_one_frame(image):
    """One whole frame, run by the ORACLE, so the next case starts from a state the game produced.

    PUBLIC because `test_asm_frame.py` is a SECOND DRIVER of this battery's staging: the asm twin's
    differential compares the twin against the same C core, over the same worlds, and restating the
    staging there would be a second thing to keep true (src/asm/README.md, step 5).
    """
    final, _writes, _regs = emu.run(bytearray(image), ENTRY_FRAME_HEAD, {}, stop_pc=STOP_FRAME,
                                    max_insns=FRAME_MAX_INSNS, schedule=list(FRAME_SCHED),
                                    wait_sites=list(WAIT_SITES))
    return bytearray(final)


def world_rng(joystick_seed=0):
    """The joystick stream `world` plays a section with, for `joystick_seed`.

    PUBLIC, and the seed base lives HERE rather than at each caller, because `atari/census.py`
    replays the same sweep to find a section's busiest frame and then names that frame number to
    `test/test_asm_frame_draw.py`. Two spellings of the base would make "frame 141" mean two
    different worlds, and nothing would say so — the suite would simply be staging something other
    than the frame the bench priced.
    """
    return random.Random(0x27a3e + joystick_seed)


@functools.lru_cache(maxsize=None)
def world(section, frames, joystick_seed=0):
    """The section's world after `frames` frames of the ORACLE playing it.

    `joystick_seed` picks a repeatable stream of joystick bytes, poked before each frame exactly as
    the IKBD interrupt would publish them — which is what makes the ship move, fire and tilt over
    the run rather than sitting still.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    image = _stage_section(section)
    rng = world_rng(joystick_seed)
    for _frame in range(frames):
        image[A_JOYSTICK_STATE] = rng.choice(JOYSTICK_BYTES)
        image = advance_one_frame(image)
    return bytes(image)


# Up, down, left, right and fire, alone and in the pairs the stick can actually make.
JOYSTICK_BYTES = (0x00, 0x01, 0x02, 0x04, 0x08, 0x80, 0x81, 0x82, 0x84, 0x88)


def world_pokes(image, extra=None):
    """The staged world as one poke, plus whatever a case wants written over it.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    pokes = {0: bytes(image[:WORLD_BYTES])}
    pokes.update(extra or {})
    return pokes


def _poked(image, extra):
    """...and the same bytes as a mutable image, for a case that wants to read its own poke back."""
    poked = bytearray(image)
    for address, blob in (extra or {}).items():
        poked[address:address + len(blob)] = blob
    return poked


def collision_row(slot):
    """One entity's row of the all-pairs table, as `include/collision.h`'s two constants build it.

    Spelt once because ten cases seed a row, and `A_ENTITY_COLLISION_MASKS + 4 * slot` written ten
    times is ten places for the stride to drift away from the header that owns it.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    return A_ENTITY_COLLISION_MASKS + COLLISION_ROW_BYTES * slot


def entity_record(slot):
    """One entity's record in the table, as `include/entity.h`'s stride builds it.

    PUBLIC for the same reason `collision_row` is, one driver further out: `atari/bench_tier.py`
    and `atari/census.py` both walk these records, and `A_ENTITY_TABLE + 0x2c * slot` written in
    each is two more places for the stride to drift away from the header that owns it.
    """
    return A_ENTITY_TABLE + ENTITY_STRIDE * slot


def pixel_hit_pairs(image):
    """The ordered pairs `frame_draw_objects_and_collide`'s walk calls `object_pair_overlap_mark`
    for, over an image as it stands AFTER its sprite pass (which is what sets the flags below).

    The inner walk runs over the slots BELOW the outer one, so each unordered pair is visited once
    and slot 0 — whose inner range is empty — can only ever be a `right`, which is why the outer
    walk starts at 1 rather than 0. PUBLIC because two instruments ask
    the same question of the same image — `test_asm_frame_draw.py`'s positive control counts them
    and `atari/bench_tier.py` prices them — and a suite that agreed the twin's arm was reached while
    the bench priced a different set of calls would be two readings of two different frames.
    """
    return [(left, right)
            for left in range(1, ENTITY_SLOTS)
            if image[entity_record(left) + ENTITY_PIXEL_HIT]
            for right in range(left)
            if image[entity_record(right) + ENTITY_ALIVE]]


def _u16(image, at):
    return (image[at] << 8) | image[at + 1]


def _u32(image, at):
    return int.from_bytes(bytes(image[at:at + 4]), "big")


# ============================================================ the two registers the loop carries

def _register_at(image, entry, pc, name):
    """One register, as the ORACLE holds it at `pc`, run from `entry` over this exact image.

    `frame_spawn_and_move_stage` reads two registers that no instruction of the frame loop wrote
    since the last `bsr`, so its reconstruction takes them as parameters (include/frame.h). This is
    where a case gets them: the same deterministic machine, the same image, stopped at the
    instruction that consumes the register. STATUS.md's "## Coverage limits" records that these two
    values are TAKEN FROM the oracle rather than derived, and what would close it.
    """
    _final, _writes, regs = emu.run(bytearray(image), entry, {}, stop_pc=pc,
                                    max_insns=FRAME_MAX_INSNS)
    return regs[name]


def ground_script_fires(image):
    """Whether the ground script's `bsr` at 0x11818 / 0x11820 is reached this frame.

    Read out of the image rather than probed, because a probe of a PC the run never reaches costs a
    full 40-million-instruction refusal. The gate is the original's own: not an asteroid section,
    not frozen, page 0, and the map cursor's next column equal to the script's trigger word.

    PUBLIC because `test_asm_frame_spawn.py` is a second driver — see `advance_one_frame`.
    """
    if image[A_ASTEROID_SECTION_FLAG] or image[A_SCROLL_FROZEN] or image[A_MAP_PAGE]:
        return False
    cursor = _u32(image, A_GROUND_SCRIPT_CURSOR)
    return ((_u32(image, A_MAP_OFFSET) & 0xffff) + SCRIPT_TRIGGER_LOOKAHEAD) & 0xffff == _u16(image, cursor)


def carried_registers(image, entry):
    """(chance_index, ground_spawn_y) as the oracle holds them when this frame consumes them.

    PUBLIC because `test_asm_frame_spawn.py` is a SECOND DRIVER of this staging: the spawn twin
    takes both registers as C arguments, and its differential has to hand the twin and the C core
    the same pair this battery hands the glue — see `advance_one_frame`.

    NO PROBE NEEDS A SCHEDULE, and that is a property of where the two PCs sit rather than an
    omission: both are inside `frame_spawn_and_move_stage`, and the frame's own two busy-waits are
    in the stage after it. The pause's three ARE before them — and the pause is driven on the head
    slice alone (its case says why), so no probe here crosses a wait. One that did would end at
    `FRAME_MAX_INSNS` with the oracle's "did not reach checkpoint", not hang.
    """
    chance_index = _register_at(image, entry, PROBE_CHANCE_INDEX_PC, "d1")
    ground_y = (_register_at(image, entry, PROBE_GROUND_SPAWN_PC, "d7")
                if ground_script_fires(image) else 0)
    return chance_index, ground_y


# ============================================================ the case shapes

def _case(image, entry, stop, glue, label, regs=None, extra=None, schedule=None, wait_sites=None):
    """One slice of one frame, over `image` with `extra` poked on top."""
    inputs = {"_pokes": world_pokes(image, extra)}
    inputs.update(regs or {})
    diffs, info = differential(entry, inputs, glue, stop_pc=stop, max_insns=FRAME_MAX_INSNS,
                               schedule=list(schedule) if schedule else None,
                               wait_sites=list(wait_sites) if wait_sites else None)
    assert not diffs, f"{label} [{entry:#x}, {stop:#x})\n{report(diffs)}"
    return info


def _stage_head_falls_through(image):
    """Which of the head slice's two exits this image takes, by the original's own three gates."""
    if image[A_EXPLOSION_GROUP_ACTIVE_BITS] & (1 << 1):
        return False
    alive = image[A_PLAYER_RECORD + ENTITY_ALIVE]
    return alive != 0 and not (alive & 0x80)


def _check_head(image, extra=None, schedule=None, wait_sites=None):
    stop = ENTRY_DRONE_AND_FIRE if _stage_head_falls_through(_poked(image, extra)) \
        else ENTRY_SPAWN_AND_MOVE
    info = _case(image, ENTRY_FRAME_HEAD, stop,
                 lambda lib, buf: lib.g_frame_panel_scroll_and_ship_stage(buf), "head", extra=extra,
                 schedule=schedule, wait_sites=wait_sites)
    assert info["ret"] == (1 if stop == ENTRY_DRONE_AND_FIRE else 0), (
        f"the head slice answered {info['ret']} but the oracle stopped at {stop:#x}")
    return stop


def _check_drone_and_fire(image, extra=None):
    joystick = _poked(image, extra)[A_JOYSTICK_STATE]
    _case(image, ENTRY_DRONE_AND_FIRE, ENTRY_SPAWN_AND_MOVE,
          lambda lib, buf: lib.g_frame_drone_and_fire_stage(buf, A_PLAYER_RECORD, joystick),
          "drone/fire", regs={"d0": joystick, "a2": A_PLAYER_RECORD}, extra=extra)


def _check_spawn_and_move(image, extra=None):
    chance, ground_y = carried_registers(_poked(image, extra), ENTRY_SPAWN_AND_MOVE)
    _case(image, ENTRY_SPAWN_AND_MOVE, ENTRY_DRAW_AND_COLLIDE,
          lambda lib, buf: lib.g_frame_spawn_and_move_stage(buf, chance, ground_y),
          "spawn/move", extra=extra)


def _check_draw_and_collide(image, extra=None):
    _case(image, ENTRY_DRAW_AND_COLLIDE, ENTRY_RESOLVE,
          lambda lib, buf: lib.g_frame_draw_objects_and_collide(buf), "draw/collide", extra=extra)


def _check_resolve(image, extra=None, expect=STOP_FRAME):
    """`expect` is the address the case says the stage leaves through, and it is the oracle's stop
    PC — so a case that named the wrong one fails with "did not reach checkpoint" rather than with a
    quiet diff. It is DECLARED rather than searched for because the four non-ordinary exits fall
    into one another's code (0x10814 runs on into 0x1083a), so "the first of the five the run
    reaches" is not the same question as "the one it left through"."""
    info = _case(image, ENTRY_RESOLVE, expect,
                 lambda lib, buf: lib.g_frame_resolve_hits_and_game_state(buf, ENTITY_SLOTS),
                 "resolve", regs={"d0": ENTITY_SLOTS}, extra=extra,
                 schedule=FRAME_SCHED, wait_sites=WAIT_SITES)
    assert info["ret"] == FRAME_EXIT_CODE[expect], (
        f"the resolve stage answered {info['ret']} but the oracle left through {expect:#x}")
    return FRAME_EXIT_ADDRESS[info["ret"]]


def _check_loop_once(image, extra=None, schedule=FRAME_SCHED, wait_sites=WAIT_SITES,
                     expect=STOP_FRAME):
    poked = _poked(image, extra)
    chance, ground_y = carried_registers(poked, ENTRY_FRAME_HEAD)
    info = _case(image, ENTRY_FRAME_HEAD, expect,
                 lambda lib, buf: lib.g_frame_loop_once(buf, chance, ground_y), "loop once",
                 extra=extra, schedule=schedule, wait_sites=wait_sites)
    assert info["ret"] == FRAME_EXIT_CODE[expect], (
        f"frame_loop_once answered {info['ret']} but the oracle left through {expect:#x}")
    return FRAME_EXIT_ADDRESS[info["ret"]]


def _check_every_slice(image, extra=None, expect=STOP_FRAME):
    """All five slices and then the composition, over one frame of one world."""
    if _check_head(image, extra) == ENTRY_DRONE_AND_FIRE:
        _check_drone_and_fire(image, extra)
    _check_spawn_and_move(image, extra)
    _check_draw_and_collide(image, extra)
    _check_resolve(image, extra, expect)
    return _check_loop_once(image, extra, expect=expect)


def test_entity_record_lands_on_the_slot_addresses_the_headers_name():
    """THE PIN ON `entity_record`'s ARITHMETIC, which MIRRORS cannot reach.

    MIRRORS pins `A_ENTITY_TABLE` and `ENTITY_STRIDE` each against its header; it says nothing
    about the product, so a helper that multiplied by `ENTITY_STRIDE + 1` would keep both mirrors
    green. That is not hypothetical — it was MEASURED: with that mutation the busy world's pair
    count falls from 51 to 29, which still clears `test_asm_frame_draw.py`'s floor of 20, and the
    whole suite stays green while `atari/bench_tier.py` prices `%a2` pointing at bytes that are not
    a record and `atari/census.py` reads the wrong type byte for every slot.

    What closes it without restating the arithmetic: `include/enemy.h` names two records by
    ADDRESS, both already mirrored, and they are slots 6 and 9 of this same table. A stride or base
    that drifted by one moves the product off both.
    """
    assert entity_record(ENEMY_SHOT_SLOT_FIRST) == A_ENEMY_SHOT_SLOTS, (
        f"entity_record({ENEMY_SHOT_SLOT_FIRST}) is {entity_record(ENEMY_SHOT_SLOT_FIRST):#x}, but "
        f"include/enemy.h puts A_enemy_shot_slots at {A_ENEMY_SHOT_SLOTS:#x} — the table's base or "
        f"its stride is wrong, and every record address built from it is off by a multiple of that")
    assert entity_record(ENEMY_SLOT_FIRST) == A_ENEMY_SLOTS, (
        f"entity_record({ENEMY_SLOT_FIRST}) is {entity_record(ENEMY_SLOT_FIRST):#x}, but "
        f"include/enemy.h puts A_enemy_slots at {A_ENEMY_SLOTS:#x}")


# ============================================================ the game, played

WORLD_FRAMES = 12        # frames of each section a battery walks
WORLD_START = 4          # ...after this many, so the first case already has enemies in flight


@pytest.mark.parametrize("section", range(SECTION_COUNT))
def test_every_slice_over_the_real_game(section):
    """All five slices, frame by frame, over each of the sixteen sections the game ships.

    THIS IS THE COMPOSITION TEST AND IT IS THE POINT OF THE BATTERY. Each frame runs perhaps a
    million instructions through forty verified routines over the whole 512 KB the game owns — the
    entity table, the eight backdrop pages, the map, every sprite bank, both framebuffers — and the
    whole-image diff is what says the reconstruction composed them in the right ORDER, at the right
    ADDRESSES, behind the right GATES. A stage that ran a pass twice, skipped one, or ran them out
    of order differs on tens of thousands of bytes.

    The sections are not interchangeable: four of them are asteroid fields with no map at all, and
    which ground-target and which alien bank a section loads is the level designer's choice, so
    sweeping all sixteen is what reaches those arms with the game's own data.
    """
    image = bytearray(world(section, WORLD_START))
    rng = random.Random(0xf4a3e + section)
    for _frame in range(WORLD_FRAMES):
        image[A_JOYSTICK_STATE] = rng.choice(JOYSTICK_BYTES)
        _check_every_slice(image)
        image = advance_one_frame(image)


@pytest.mark.parametrize("gate,extra", (
    ("the ship's death explosion is running",
     {A_EXPLOSION_GROUP_ACTIVE_BITS: bytes([1 << 1])}),
    ("the ship's record is dead", {A_PLAYER_RECORD + ENTITY_ALIVE: b"\x00"}),
    ("the ship's record is exploding", {A_PLAYER_RECORD + ENTITY_ALIVE: b"\x80"}),
    ("the ship is alive and flying", {A_PLAYER_RECORD + ENTITY_ALIVE: b"\x01",
                                      A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"})))
def test_the_head_slice_takes_both_of_its_exits(gate, extra):
    """0x113c0 is a FALL-THROUGH, not a join, and each of the three gates that skips it is driven.

    `frame_panel_scroll_and_ship_stage` answers WHICH exit it took, and each case here asserts that
    answer against the address the oracle stopped at — so a reconstruction that took the wrong arm
    fails on the answer even where the two arms happen to leave the same bytes.

    THE WORLD SWEEP ABOVE ONLY REACHES THE FALL-THROUGH: a ship dies rarely and never in the dozen
    frames a section is played for there, which is why the diverting arm is poked here instead
    (measured — an earlier revision asserted the sweep drove both and it does not).
    """
    image = bytearray(world(0, WORLD_START))
    expected = ENTRY_DRONE_AND_FIRE if gate.endswith("flying") else ENTRY_SPAWN_AND_MOVE
    assert _check_head(image, extra) == expected, gate
    if expected == ENTRY_SPAWN_AND_MOVE:
        _check_loop_once(image, extra)


# ============================================================ the frame's own end

def test_the_frame_waits_for_the_raster_and_then_for_the_vertical_blank():
    """Both busy-waits, driven at an arrival the FIRST poll does not satisfy.

    With `nth` at 1 the scheduled byte is already there when either loop first looks, so a
    reconstruction that dropped a wait entirely would still agree. Pushing the arrival out makes the
    loop turn, and `harness.differential` then compares the candidate's poll count against the
    oracle's arrival count SITE BY SITE — so a port that spun on the wrong byte, or polled twice per
    pass, fails here rather than passing quietly.
    """
    image = bytearray(world(0, WORLD_START))
    schedule = ({"pc": FRAME_RASTER_WAIT_PC, "nth": 5, "addr": A_RASTER_PHASE, "width": 1,
                 "value": FRAME_RASTER_PHASE_READY},
                {"pc": FRAME_VBL_WAIT_PC, "nth": 3, "addr": A_VBL_WAIT_FLAG, "width": 1,
                 "value": FRAME_VBL_WAIT_DONE})
    extra = {A_RASTER_PHASE: b"\x5a", A_VBL_WAIT_FLAG: b"\x5a"}
    _check_loop_once(image, extra, schedule=schedule, wait_sites=WAIT_SITES)


def test_the_frame_tail_sends_the_joystick_interrogate_and_re_enables_the_acia():
    """The three off-image things the tail does, through the kit's two hardware ledgers.

    None of them writes a byte the diff could see: `screen_flip_buffers` publishes the new front
    buffer to the shifter, `ikbd_send_cmd` polls the ACIA's status and sends $16, and `bset
    #6,$fffa09` re-enables the keyboard interrupt. `harness.differential` compares both sides'
    ordered read and write streams on every case; this one reads them back and says WHAT they are,
    so a reconstruction that aimed a store at another register fails with a sentence.
    """
    image = bytearray(world(0, WORLD_START))
    info = _case(image, ENTRY_RESOLVE, STOP_FRAME,
                 lambda lib, buf: lib.g_frame_resolve_hits_and_game_state(buf, ENTITY_SLOTS),
                 "tail", regs={"d0": ENTITY_SLOTS}, schedule=FRAME_SCHED, wait_sites=WAIT_SITES)
    writes = info["regs"]["hw_writes"]
    assert (HW_MFP_IERA, 1, 1 << 6) in writes, (
        f"the frame tail did not `bset #6` the MFP's interrupt-enable A at {HW_MFP_IERA:#x}: "
        f"{[(hex(a), w, hex(v)) for a, w, v in writes]}")
    assert (0xfffc02, 1, IKBD_CMD_INTERROGATE_JOYSTICK) in writes, (
        "the frame tail did not send the IKBD's joystick interrogate command")


@pytest.mark.parametrize("release_nth,press_nth", ((1, 1), (2, 3), (4, 2)))
def test_the_pause_key_holds_the_frame_and_restarts_the_palette_counters(release_nth, press_nth):
    """Space bar: wait for the release, restart both palette-cycle counters, wait for the next press
    and for ITS release.

    FOUR SPINS ON A BYTE ONLY THE KEYBOARD INTERRUPT WRITES, and the middle two are one loop whose
    body rewrites the counters on every pass — so the arrival count decides how many times they are
    written, which is what the schedule below drives. The counters are seeded to a value neither the
    pause nor anything else produces, so a reconstruction that skipped the reload differs.

    This arm is unreachable from the world sweep above: nothing in a frame writes the scancode.

    IT IS DRIVEN ON THE HEAD SLICE ALONE, not on the whole frame, and that is a limit of the model
    rather than a choice: the pause holds three wait sites and the frame's own tail two more, and
    `os.h`'s OS_SCHED_SITE_MAX is four. The pause is entirely inside this slice, so nothing of it is
    left out.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_KEY_SCANCODE: bytes([KEY_SCANCODE_SPACE]),
             A_PALETTE_SWAP_COUNTDOWN: b"\x5a", A_PALETTE_ROTATE_COUNTDOWN: b"\x5a"}
    schedule = ({"pc": PAUSE_RELEASE_WAIT_PC, "nth": release_nth, "addr": A_KEY_SCANCODE,
                 "width": 1, "value": 0},
                {"pc": PAUSE_PRESS_WAIT_PC, "nth": press_nth, "addr": A_KEY_SCANCODE, "width": 1,
                 "value": KEY_SCANCODE_SPACE},
                {"pc": PAUSE_SECOND_RELEASE_WAIT_PC, "nth": release_nth, "addr": A_KEY_SCANCODE,
                 "width": 1, "value": 0})
    sites = (PAUSE_RELEASE_WAIT_PC, PAUSE_PRESS_WAIT_PC, PAUSE_SECOND_RELEASE_WAIT_PC)
    _check_head(image, extra, schedule=schedule, wait_sites=sites)


# ============================================================ the arms the shipped run does not reach

@pytest.mark.parametrize("weapon", (WEAPON_KIND_BOMB, WEAPON_KIND_MISSILE, WEAPON_BULLET, WEAPON_KIND_SEEKER))
@pytest.mark.parametrize("shield", (0, 1))
def test_every_weapon_launches_from_a_fresh_press(weapon, shield):
    """The four arms of the fire button, each at both shield levels.

    The section start selects weapon 3 and leaves the shield at 0, so three of the four launchers
    and the two-in-flight allowance are unreachable from the sweep above without saying which weapon
    the player picked. That is a game-state byte, not a fabricated record: the power-up screen writes
    it, and `A_selected_weapon` is what it writes.

    The button is presented as a FRESH PRESS — held clear, fire set — which is the one shape that
    reaches a launcher at all; the held and released shapes are the two cases below.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_SELECTED_WEAPON: bytes([weapon]), A_SHIELD_LEVEL: bytes([shield]),
             A_FIRE_BUTTON_HELD: b"\x00", A_JOYSTICK_STATE: bytes([JOYSTICK_FIRE])}
    _check_every_slice(image, extra)


@pytest.mark.parametrize("weapon", (WEAPON_KIND_BOMB, WEAPON_KIND_MISSILE, WEAPON_KIND_SEEKER))
def test_a_weapon_at_its_limit_falls_through_to_the_plain_bullet(weapon):
    """`bge 0x11600` — the three counted weapons do not simply refuse when they are at their limit,
    they fall THROUGH to the ordinary bullet's arm.

    A reconstruction that returned instead of falling through fires nothing here, and the bullet it
    should have launched is six stores and a tune. The counters are poked to the limit the shield
    level allows, which is game state the launcher itself writes.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_SELECTED_WEAPON: bytes([weapon]), A_SHIELD_LEVEL: b"\x00",
             A_ACTIVE_COUNT_BOMBS: b"\x05", A_ACTIVE_COUNT_TYPE32: b"\x05",
             A_ACTIVE_COUNT_SEEKERS: b"\x05", A_ACTIVE_COUNT_TYPE34: b"\x00",
             # ...and the bullet arm must be able to fire, or the fall-through is invisible: the
             # section start leaves the power level at 0, which is its own `bge` limit.
             A_WEAPON_POWER_LEVEL: b"\x03",
             # ...and the trail drone must already be flying: launching it is what CLEARS the
             # seeker count, and a cleared count is under its limit however this case seeds it.
             A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x01",
             A_FIRE_BUTTON_HELD: b"\x00", A_JOYSTICK_STATE: bytes([JOYSTICK_FIRE])}
    for slot in range(PLAYER_SHOT_SLOTS):
        extra[entity_record(slot) + ENTITY_ALIVE] = b"\x00"
    _check_every_slice(image, extra)


def test_an_unknown_selected_weapon_fires_nothing():
    """`cmpi.b #$3,$198b4` + `bne 0x1167c` — the fourth compare has no `bra` to the bullet arm, so a
    weapon byte that is none of the four leaves the press having launched nothing at all. It is the
    one arm of the dispatch that is not a fall-through, and a `switch` with a wrong default would
    fire a bullet here."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_SELECTED_WEAPON: b"\x07", A_FIRE_BUTTON_HELD: b"\x00",
             A_JOYSTICK_STATE: bytes([JOYSTICK_FIRE])}
    _check_every_slice(image, extra)


@pytest.mark.parametrize("charge", (0, 1, FIRE_CHARGE_FULL - 2, FIRE_CHARGE_FULL - 1, 0xff))
def test_the_fire_charge_counter_arms_at_eight(charge):
    """`addi.b #$1,$19901` + `cmpi.b #$8` — an EQUALITY test on the stepped byte, so 7 arms the
    charged weapon and 0xff wraps to 0 and keeps counting rather than arming. The button is HELD
    (held byte already set), which is the arm that runs the counter at all."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_FIRE_BUTTON_HELD: b"\x01", A_FIRE_CHARGED: b"\x00",
             A_FIRE_CHARGE_COUNTER: bytes([charge]),
             A_JOYSTICK_STATE: bytes([JOYSTICK_FIRE])}
    _check_every_slice(image, extra)


@pytest.mark.parametrize("shadow,direction", ((0, 0), (CHARGE_FLASH_PEAK - CHARGE_FLASH_STEP, 0),
                                              (CHARGE_FLASH_PEAK, 1), (CHARGE_FLASH_STEP, 1),
                                              (0x222, 0), (0x222, 1)))
def test_the_charged_flash_turns_round_at_both_ends(shadow, direction):
    """The palette shadow walks up in steps of 0x111 to 0x444 and back down to 0, turning with a
    `not.b` at each end. Both turning points are driven exactly, and two mid-walk values either way
    — the tests are EQUALITY compares, so a reconstruction using `>=` agrees everywhere but at the
    step that overshoots.

    The animation phase must be clear for the flash to run at all, which halves its rate.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_FIRE_CHARGED: b"\x01", A_EXPLOSION_PHASE_ODD: b"\x00",
             A_CHARGE_FLASH_DIR: bytes([direction]),
             A_PALETTE_HW_SHADOW: shadow.to_bytes(2, "big")}
    _check_spawn_and_move(image, extra)


def test_the_trail_drone_is_launched_and_then_follows_the_ship():
    """Weapon 4 with the drone's slot dead: the launch primes all ten history pairs with the ship's
    own position, clears the cursor and the seeker count, and only then reads the oldest pair back.

    A reconstruction that read the history before priming it would fly the drone to wherever the
    slot's previous occupant left, which the seeded history below makes a diff of tens of bytes.
    """
    image = bytearray(world(0, WORLD_START))
    history = bytes(random.Random(0x113c0).randbytes(
        SHIP_POS_HISTORY_ENTRIES * SHIP_POS_HISTORY_ENTRY_BYTES))
    extra = {A_SELECTED_WEAPON: bytes([WEAPON_KIND_SEEKER]),
             A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x00",
             A_SHIP_POS_HISTORY: history, A_SHIP_POS_HISTORY_INDEX: b"\x5a"}
    _check_drone_and_fire(image, extra)


@pytest.mark.parametrize("index", (0, 1, SHIP_POS_HISTORY_ENTRIES - 2,
                                   SHIP_POS_HISTORY_ENTRIES - 1, SHIP_POS_HISTORY_ENTRIES))
def test_the_trail_drone_history_cursor_wraps_at_ten(index):
    """`addi.b #$1,$198ff` + `cmpi.b #$a` — an EQUALITY test again, so an index already AT ten steps
    to eleven and is left there. The drone is alive, so the launch above is skipped and this is the
    per-frame half on its own."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x01",
             A_SHIP_POS_HISTORY_INDEX: bytes([index]),
             A_SHIP_POS_HISTORY: bytes(random.Random(0x19f86 + index).randbytes(
                 SHIP_POS_HISTORY_ENTRIES * SHIP_POS_HISTORY_ENTRY_BYTES))}
    _check_drone_and_fire(image, extra)


def test_the_trail_drone_offset_is_one_longword_add():
    """`add.l #$800005,d1` on the packed {x, y} pair, so a y that overflows its word CARRIES INTO X.

    The history pair is poked to a y one step below the wrap, which is the only input that tells the
    longword add apart from two word adds — and the pair is real program data (the ship's own
    position, as the drone stores it) rather than a fabricated record.
    """
    image = bytearray(world(0, WORLD_START))
    carry_pair = (0x0040).to_bytes(2, "big") + (0x10000 - (TRAIL_DRONE_OFFSET_PACKED & 0xffff) + 1) \
        .to_bytes(2, "big")
    extra = {A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x01",
             A_SHIP_POS_HISTORY_INDEX: b"\x00",
             A_SHIP_POS_HISTORY: carry_pair}
    _check_drone_and_fire(image, extra)


@pytest.mark.parametrize("tilt", (0, 1, 2, 3, 4, 5, 6))
def test_the_ship_tilt_recentres_from_every_frame(tilt):
    """With neither up nor down pressed the tilt bank rolls back towards its middle frame, and which
    way it rolls is a SIGNED compare against 3 — so the two arms move the ship in opposite
    directions and clamp against opposite bounds. The countdown is set to 1 so the roll is due on
    this very frame."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_JOYSTICK_STATE: b"\x00", A_SHIP_TILT: bytes([tilt]),
             A_SHIP_TILT_COUNTDOWN: b"\x01"}
    _check_every_slice(image, extra)


@pytest.mark.parametrize("joystick", JOYSTICK_BYTES)
def test_every_joystick_direction_moves_the_ship(joystick):
    """All ten stick shapes over one world frame, which is what drives the four movement arms, the
    two clamps and the sprite-bank selection together."""
    image = bytearray(world(0, WORLD_START))
    _check_every_slice(image, {A_JOYSTICK_STATE: bytes([joystick])})


@pytest.mark.parametrize("x", (0x30, 0x41, 0x42, 0x43, 0x14f, 0x150, 0x151))
def test_the_horizontal_arms_clamp_at_their_own_edges(x):
    """The left arm's `cmpi.w #$42` + `ble` parks the pair at its home column; the right arm's
    `cmpi.w #$150` + `bge` simply stops stepping, because the two stores that would clamp it are
    UNREACHABLE — `bge` jumps past them to the end of the slice. Both edges are driven one step
    either side, on both arms, over the ship's real record."""
    image = bytearray(world(0, WORLD_START))
    for joystick in (1 << 2, 1 << 3):
        extra = {A_JOYSTICK_STATE: bytes([joystick]),
                 A_PLAYER_RECORD + ENTITY_X: x.to_bytes(2, "big")}
        _check_every_slice(image, extra)


def test_the_right_hand_clamp_is_dead_code():
    """0x113b4 stores 0x150/0x160 into the ship pair and NOTHING BRANCHES TO IT: the `bge.s` at
    0x113a4 targets 0x113c0, past both stores, and the arm below it ends in a `bra.s` to the same
    place. src/frame.c does not transcribe them, and this is the assertion that says why rather
    than leaving the omission looking like an oversight."""
    assert bytes(harness.BASE_IMAGE[0x113a4:0x113a6]) == bytes.fromhex("6c1a"), "bge.s +0x1a"
    assert bytes(harness.BASE_IMAGE[0x113b2:0x113b4]) == bytes.fromhex("600c"), "bra.s +0x0c"
    assert 0x113a4 + 2 + 0x1a == 0x113c0 and 0x113b2 + 2 + 0x0c == 0x113c0


@pytest.mark.parametrize("countdown", (1, 2, PANEL_LOGO_PERIOD))
def test_the_panel_logo_animation_runs_only_on_an_idle_panel(countdown):
    """`tst.b $19904` on the WHOLE mask, then a 500-frame countdown: the animated logo is drawn only
    on a frame with no other repaint pending, and only when the countdown reaches zero — where it is
    reloaded with its own period.

    The section start leaves the mask at 7 and the countdown at 1, so the world sweep never reaches
    the arm; clearing the mask is what does. Both sides of the `bne` are driven, and the reload's
    own value is what the mutation sweep asked for.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_PANEL_REDRAW_MASK: b"\x00",
             A_PANEL_LOGO_COUNTDOWN: countdown.to_bytes(2, "big")}
    _check_head(image, extra)


# A steered shot's ENTITY_ANIM_FRAME is its time to live; anything but the last frame
# leaves the shot in flight, and 0x40 is well inside both kinds' own reloads.
SHOT_TIME_TO_LIVE_HEALTHY = 0x40
# THREE STEPS EITHER SIDE, and the three is measured rather than guessed: over the staged worlds the
# steering update moves a shot by at most one pixel before the box is tested (a poked 0x30 and a
# poked 0x31 both arrive at 0x30), so a band this wide contains each edge exactly whatever the steer
# did, with two steps of margin.
BOX_EDGE_STEER_MARGIN = 3
BOX_EDGE_SWEEP = tuple(
    (x, 0x50) for edge in (SHOT_X_MIN, SHOT_X_MAX)
    for x in range(edge - BOX_EDGE_STEER_MARGIN, edge + BOX_EDGE_STEER_MARGIN + 1)) \
    + tuple((0x80, y) for edge in (SHOT_Y_MIN, SHOT_Y_MAX)
            for y in range(edge - BOX_EDGE_STEER_MARGIN, edge + BOX_EDGE_STEER_MARGIN + 1))


@pytest.mark.parametrize("x,y", BOX_EDGE_SWEEP)
@pytest.mark.parametrize("shot_type", (SHOT_TYPE_SEEKER, SHOT_TYPE_MISSILE))
def test_a_steered_shot_is_retired_outside_its_box(x, y, shot_type):
    """Four `cmpi.w` + branch pairs, each swept BOX_EDGE_STEER_MARGIN steps either side of
    its own edge.

    IT IS A SWEEP RATHER THAN THREE POINTS because the box is tested AFTER the steering update has
    already moved the shot, so the coordinate a case pokes is not the one the compare sees; a band
    wide enough to contain the edge whatever the steer did is what puts a case exactly ON it.

    Only the two STEERED kinds reach this pass at all (`cmpi.b #$36` / `#$32`), and both are driven,
    because the steering update runs first and moves the shot — so a candidate testing the box
    against the position it had BEFORE the update differs at the edge.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENTITY_TABLE + ENTITY_TYPE: bytes([shot_type]),
             A_ENTITY_TABLE + ENTITY_ALIVE: b"\x01",
             # ...with time left to live, or the steering update turns it into an impact puff before
             # the box is ever tested and the retire below has nothing to retire (measured).
             A_ENTITY_TABLE + ENTITY_ANIM_FRAME: bytes([SHOT_TIME_TO_LIVE_HEALTHY]),
             A_ENTITY_TABLE + ENTITY_X: (x & 0xffff).to_bytes(2, "big"),
             A_ENTITY_TABLE + ENTITY_Y: (y & 0xffff).to_bytes(2, "big")}
    _check_spawn_and_move(image, extra)


@pytest.mark.parametrize("x", (0x81, 0x8f, 0xff))
def test_a_steered_shot_is_forced_to_an_even_column(x):
    """`bclr #0,1(a3)` — the LOW BYTE of ENTITY_X, so every player shot is aligned to two pixels
    after its steering update and before its box test. An odd x well inside the box is the only
    input that separates the clear from a no-op."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENTITY_TABLE + ENTITY_TYPE: bytes([SHOT_TYPE_SEEKER]),
             A_ENTITY_TABLE + ENTITY_ALIVE: b"\x01",
             A_ENTITY_TABLE + ENTITY_X: (x & 0xffff).to_bytes(2, "big"),
             A_ENTITY_TABLE + ENTITY_Y: (0x50).to_bytes(2, "big")}
    _check_spawn_and_move(image, extra)


def script_trigger_offset(image, cursor_global, round_to_column):
    """A map offset that makes the script at `cursor_global` fire on this frame.

    The trigger is the script record's own word, read out of the world rather than typed; the wave
    script rounds it DOWN to a whole column first and the ground script does not, which is the one
    difference between the two gates. Returns None when the arithmetic cannot be met.

    PUBLIC because `test_asm_frame_spawn.py` is a second driver — see `advance_one_frame`.
    """
    trigger = _u16(image, _u32(image, cursor_global))
    wanted = ((trigger // SCRIPT_TRIGGER_LOOKAHEAD) * SCRIPT_TRIGGER_LOOKAHEAD
              if round_to_column else trigger)
    return (wanted - SCRIPT_TRIGGER_LOOKAHEAD) & 0xffff


def test_the_wave_script_fires_when_the_map_cursor_reaches_its_column():
    """`divu.w #$24` / `mulu.w #$24` / `cmp.w`: the attack script fires when the cursor's own column
    plus one look-ahead column equals its trigger word ROUNDED DOWN to a column.

    The world sweep never reaches this — a script record fires once every few hundred frames — so
    the map offset is set to the value the script's own word asks for. That word is read out of the
    staged world, so a wrong look-ahead lands on a different column and the spawn does not happen.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_MAP_OFFSET: script_trigger_offset(image, A_WAVE_SCRIPT_CURSOR, True)
                           .to_bytes(4, "big"),
             A_MOTHERSHIP_PENDING: b"\x00"}
    _check_spawn_and_move(image, extra)


def test_the_ground_script_fires_on_an_exact_column_and_passes_its_carried_register():
    """The ground script's gate is the same look-ahead against an UNROUNDED trigger, behind three
    more tests — not an asteroid section, not frozen, page 0.

    THIS IS ALSO THE ONE CASE THAT DRIVES `ground_spawn_y_register`: the spawner's free-slot guard
    tests the whole longword D7, whose high word is the caller's, so a frame that never reaches the
    `bsr` never reads it. `ground_script_fires` is what tells the battery to probe for it, and this
    case is what makes that predicate answer yes.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_MAP_OFFSET: script_trigger_offset(image, A_GROUND_SCRIPT_CURSOR, False)
                           .to_bytes(4, "big"),
             A_ASTEROID_SECTION_FLAG: b"\x00", A_SCROLL_FROZEN: b"\x00", A_MAP_PAGE: b"\x00"}
    assert ground_script_fires(_poked(image, extra)), (
        "the ground script's gate is not met, so this case would not drive the spawner at all")
    _check_spawn_and_move(image, extra)


# ============================================================ the scroller and the mothership

@pytest.mark.parametrize("page", range(MAP_PAGES))
def test_the_scroller_emits_from_every_page_of_the_ring(page):
    """Page 0 decodes a fresh tile column and advances the map cursor; pages 1..7 re-emit the
    workspace two pixels further along. The page counter is game state the frame's own tail steps,
    and this drives all eight from one world."""
    image = bytearray(world(0, WORLD_START))
    _check_head(image, {A_MAP_PAGE: bytes([page])})


@pytest.mark.parametrize("column", (0, 1, 7, SCROLL_PHASES - 2, SCROLL_PHASES - 1))
def test_the_playfield_blit_runs_from_every_column_phase(column):
    """The jump table at 0x179aa has one specialised page-to-screen copy per 16-pixel phase, and the
    reconstruction spells it as an array of the twenty verified routines. A wrong index copies the
    playfield at the wrong offset, which is 23 KB of diff."""
    image = bytearray(world(0, WORLD_START))
    _check_head(image, {A_MAP_COLUMN: bytes([column])})


@pytest.mark.parametrize("scroll_pos", (0, 0x8, 0xfffff8, 0x7fff8, 0x80000, 0x80008, 0xabcdef8))
def test_the_asteroid_cursor_multiply_is_sixteen_bits(scroll_pos):
    """`lsr.l #3,d7` then `mulu.w #$24,d7` — a 16x16 multiply, so only the shifted longword's LOW
    WORD is a factor and a scroll position past 0x80000 folds rather than running away.

    The game reaches 0x80000 after about three hours in one section, so no world sweep can drive it;
    the byte is one the frame's own tail increments, and this pokes it forward. Below the fold the
    two readings agree, which is why the sweep is on both sides of it.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_SCROLL_POS: scroll_pos.to_bytes(4, "big"), A_ASTEROID_SECTION_FLAG: b"\x01",
             A_BOSS_SEQUENCE_ACTIVE: b"\x00",
             A_MAP_OFFSET: b"\x5a\xa5\x5a\xa5", A_MAP_PTR: b"\x5a\xa5\x5a\xa5"}
    _check_head(image, extra)


def test_the_frozen_scroller_takes_the_other_emitter():
    """`tst.b $198b1` picks `scroll_emit_column_shift0` over `_shift2` on pages 1..7, and steps the
    map cursor BACK a column instead of republishing the offset on page 0. Both arms of both halves
    are driven, and the freeze byte is what the mothership trigger sets."""
    image = bytearray(world(0, WORLD_START))
    for page in (0, 3):
        _check_head(image, {A_SCROLL_FROZEN: b"\x01", A_MAP_PAGE: bytes([page])})


@pytest.mark.parametrize("scroll_pos,index", ((MOTHERSHIP_TRIGGER_SCROLL_POS - 1, 0),
                                              (MOTHERSHIP_TRIGGER_SCROLL_POS, 0),
                                              (MOTHERSHIP_TRIGGER_SCROLL_POS + 1, 4),
                                              (MOTHERSHIP_TRIGGER_SCROLL_POS, 5),
                                              (MOTHERSHIP_TRIGGER_SCROLL_POS, 0x0f),
                                              (MOTHERSHIP_TRIGGER_SCROLL_POS, 0x80)))
def test_the_mothership_trigger_fires_at_its_own_scroll_position(scroll_pos, index):
    """`cmpi.l #$c80,$195cc` + `blt` one step either side, and both arms of the `cmp.w #$5` that
    picks between starting an encounter and respawning its segments.

    The index is driven at 0x80 as well, which is what holds the SIGN: the trigger compares it as a
    sign-extended WORD (`ext.w` then `cmp.w`), so 0x80 reads as -128 and takes the low arm, where an
    unsigned reading would take the other one.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_SCROLL_POS: scroll_pos.to_bytes(4, "big"), A_MOTHERSHIP_INDEX: bytes([index]),
             A_MOTHERSHIP_READY: b"\x00", A_BOSS_SEQUENCE_ACTIVE: b"\x00"}
    _check_head(image, extra)


@pytest.mark.parametrize("index", (0, 4, 5, 0x7f, 0x80, 0xff))
def test_the_mothership_build_step_reads_its_index_as_a_byte(index):
    """The build gate at 0x1116e is `cmp.b #$5` on a byte the instruction before SIGN-EXTENDED into a
    word — a byte compare of a sign-extended byte, which is not the word compare the trigger above
    makes of the same global. Driving 0x80 and 0xff is what separates the two."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MOTHERSHIP_PREP_STAGE: b"\x01", A_MOTHERSHIP_INDEX: bytes([index])}
    _check_head(image, extra)


def test_a_boss_encounter_paints_and_moves_instead_of_scrolling():
    """With the boss flag set the head slice skips the scroller entirely and CLEARS the playfield,
    and the spawn stage runs the mothership's own move/place/draw chain and steps its phase timer.
    Two whole passes appear and one disappears, which is what makes this arm worth its own case."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_BOSS_SEQUENCE_ACTIVE: b"\x01"}
    _check_head(image, extra)
    _check_spawn_and_move(image, extra)
    _check_draw_and_collide(image, extra)


@pytest.mark.parametrize("index", (4, 5))
def test_the_draw_stage_updates_the_boss_segments_only_above_the_index(index):
    """`cmp.w #$5` + `bge` again, and this one has a `bra` PAST its own arm on the other side — so a
    reconstruction reading it as `>` differs on the timer as well as on the segments."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MOTHERSHIP_READY: b"\x01", A_MOTHERSHIP_INDEX: bytes([index])}
    _check_draw_and_collide(image, extra)


# ============================================================ the resolve stage's own arms

def test_the_collision_table_is_cleared_one_longword_past_its_last_row():
    """`move.w #$14,d0` + `clr.l (a0)+` + `dbf` is TWENTY-ONE longwords over a twenty-entry table,
    and the extra one is real: the guard row above it is seeded here to a value the clear must
    reach. A reconstruction that cleared twenty leaves it standing."""
    image = bytearray(world(0, WORLD_START))
    guard = collision_row(ENTITY_SLOTS)
    _check_draw_and_collide(image, {guard: b"\x5a\xa5\x5a\xa5"})


@pytest.mark.parametrize("invulnerable", (0, 1))
def test_the_ship_flying_into_the_landscape_explodes_unless_it_is_invulnerable(invulnerable):
    """A pixel hit with an EMPTY collision row is the landscape, and it kills — which is the one
    ship-collision arm the shipped sections do not reach in a dozen frames of level flight. The row
    is cleared and the record's own hit byte set, both of which the blitter and the pairwise sweep
    write for real one stage earlier."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_PLAYER_RECORD + ENTITY_PIXEL_HIT: b"\x01",
             collision_row(ENTITY_INDEX_SHIP): b"\x00\x00\x00\x00",
             A_SHIP_INVULNERABLE: bytes([invulnerable]),
             A_DEATH_EVENT_FLAGS: b"\x00",
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    _check_resolve(image, extra)


def test_the_second_ship_record_is_tested_when_the_first_explains_nothing():
    """`lea 4(a3),a3` advances only the ROW pointer, so the second pass reads record 18's hit byte
    against record 18's row and then hands record SEVENTEEN to the resolver. That asymmetry is the
    original's, and a reconstruction that advanced both pointers passes a different record."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_PLAYER_RECORD + ENTITY_PIXEL_HIT: b"\x00",
             A_SHIP_RECORD_SHADOW + ENTITY_PIXEL_HIT: b"\x01",
             collision_row(SHIP_SHADOW_SLOT): (1 << 9).to_bytes(4, "big"),
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("row", (1 << 5, 1 << 6, 1 << 7, (1 << 5) | (1 << 6)))
def test_the_ship_hit_mask_splits_at_entity_six(row):
    """`and.l #$ffffffc0` against `and.l #$3f`: a hit explained by an entity at index 6 or ABOVE is
    a real collision, one explained only by the player's own six shot slots is harmless, and the
    boundary between them is entity 6 exactly. Bit 5 and bit 6 are the two sides of it, and the pair
    together is what says the high test is made FIRST."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_PLAYER_RECORD + ENTITY_PIXEL_HIT: b"\x01",
             collision_row(ENTITY_INDEX_SHIP): row.to_bytes(4, "big"),
             A_ENEMY_SHOT_SLOTS + ENTITY_TYPE: b"\x0c",
             A_ENEMY_SHOT_SLOTS + ENTITY_ALIVE: b"\x01",
             A_SHIP_INVULNERABLE: b"\x00", A_DEATH_EVENT_FLAGS: b"\x00",
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    _check_resolve(image, extra)


def test_the_second_ship_record_hands_the_resolver_the_FIRST():
    """`lea 4(a3),a3` advances the ROW pointer and not A2, so record 18's hit is resolved with
    record SEVENTEEN — and the difference shows only on the lethal arm, where `explosion_spawn`
    reads the record's own position. The two records sit at different x (0x40 and 0x50 from the
    section restart), so the explosion lands in a different place under a candidate that passed the
    shadow. That is what the mutation sweep asked for, and the case above cannot see it."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_PLAYER_RECORD + ENTITY_PIXEL_HIT: b"\x00",
             A_SHIP_RECORD_SHADOW + ENTITY_PIXEL_HIT: b"\x01",
             collision_row(SHIP_SHADOW_SLOT): (1 << 6).to_bytes(4, "big"),
             A_ENEMY_SHOT_SLOTS + ENTITY_TYPE: b"\x0c",
             A_ENEMY_SHOT_SLOTS + ENTITY_ALIVE: b"\x01",
             A_PLAYER_RECORD + ENTITY_X: (0x40).to_bytes(2, "big"),
             A_SHIP_RECORD_SHADOW + ENTITY_X: (0x120).to_bytes(2, "big"),
             A_SHIP_INVULNERABLE: b"\x00", A_DEATH_EVENT_FLAGS: b"\x00",
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("row", (0, 1 << 5, 1 << 6, GUNSIGHT_ENEMY_MASK, (1 << 5) | (1 << 9)))
def test_the_seeker_lock_scans_the_eight_enemy_slots(row):
    """`and.l #$1fe00` — only bits 9..16 arm the search at all, so a row holding nothing but the
    player's own shots answers "no lock" without walking anything. Each case seeds the gunsight's
    own row, which the pairwise sweep fills for real one stage earlier."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x01",
             collision_row(ENTITY_INDEX_TRAIL_DRONE): row.to_bytes(4, "big"),
             A_SEEKER_LOCK_TARGET_INDEX: b"\x5a"}
    _check_resolve(image, extra)


def test_the_seeker_lock_is_forced_to_slot_nine_while_the_boss_is_up():
    """`moveq #$13,d0` + `bsr collision_chain_walk` + `move.b #$9`: with the boss in the playfield
    the gunsight's answer is not searched for at all. The other arm of that same `beq` is the
    ordinary scan, which the case above drives."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_BOSS_SEQUENCE_ACTIVE: b"\x01", A_ENTITY_GUNSIGHT + ENTITY_ALIVE: b"\x01",
             A_ENTITY_GUNSIGHT + ENTITY_PIXEL_HIT: b"\x01",
             A_SEEKER_LOCK_TARGET_INDEX: b"\x5a"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("frame", (0x80, 0x81, 0x80 | (EXPLOSION_LAST_FRAME - 2),
                                   0x80 | (EXPLOSION_LAST_FRAME - 1), 0xff))
@pytest.mark.parametrize("kind", (EXPLOSION_PART_TYPE, EXPLOSION_TYPE_LARGE))
def test_both_explosion_animations_step_and_retire(frame, kind):
    """The two animations differ in their gate, their type, their frame table and one extra pair of
    stores, and are one body here — so both must be driven from the same frames.

    0xff is the case that separates the step from a counter: `(alive & 0x7f) + 1` wraps 0x7f to 0,
    which is neither the last frame nor a table index the mask lets through unchanged.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENEMY_SLOTS + ENTITY_TYPE: bytes([kind]),
             A_ENEMY_SLOTS + ENTITY_ALIVE: bytes([frame]),
             A_EXPLOSION_PHASE_EVEN: b"\x01" if kind == EXPLOSION_PART_TYPE else b"\x00",
             A_EXPLOSION_PHASE_ODD: b"\x00" if kind == EXPLOSION_TYPE_LARGE else b"\x01"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("marks", (1, 2, 0))
@pytest.mark.parametrize("tag", (0xaa, 0x00))
def test_the_last_explosion_frame_credits_a_squadron_and_may_leave_a_capsule(marks, tag):
    """The last frame either kills the record or, when the squadron it belonged to runs out of
    marks, turns it into a power-up capsule worth a score and a tune.

    `cmpi.b #$aa,20(a2)` is the escape: an actor carrying the no-credit tag never touches a counter,
    which is what separates the two. A mark of 1 runs the squadron out on this very frame; 2 leaves
    one; 0 WRAPS to 0xff and leaves the squadron alive, which is what holds `subi.b` + `bne` against
    a `<= 0` test.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENEMY_SLOTS + ENTITY_TYPE: bytes([EXPLOSION_PART_TYPE]),
             A_ENEMY_SLOTS + ENTITY_ALIVE: bytes([0x80 | (EXPLOSION_LAST_FRAME - 1)]),
             A_ENEMY_SLOTS + EXPLOSION_CREDIT_TAG_OFFSET: bytes([tag]),
             A_ENEMY_SLOTS + ENTITY_SQUADRON: b"\x02",
             A_SQUADRON_KILL_COUNTERS: bytes([0x5a, 0x5a, marks, 0x5a, 0x5a, 0x5a]),
             A_EXPLOSION_PHASE_EVEN: b"\x01"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("kind", (EXPLOSION_PART_TYPE, EXPLOSION_TYPE_LARGE))
@pytest.mark.parametrize("on_terrain", (0, 1))
def test_a_capsule_that_lands_on_the_terrain_is_killed_instead_of_announced(kind, on_terrain):
    """`bne 0x12092` — the LAST thing the capsule arm does, and the two answers could not differ
    more: a capsule the chain walk explains as a terrain landing is CLEARED, and only the other one
    plays its tune.

    Reaching it needs the whole arm: an exploding record on its last frame, a credit tag that is not
    the no-credit one, and a squadron with exactly one mark left — and then the record's own
    pixel-hit byte set with an EMPTY collision row, which is what makes `collision_chain_walk`
    answer "the landscape". `on_terrain` is that byte; both explosion kinds share one body in
    src/frame.c, so both are driven.

    THIS CASE IS WHY THE ARM IS RECONSTRUCTED AT ALL: an earlier revision fell out of the `if` with
    the capsule still alive, and every other case in this battery stayed green because none of them
    let the walk answer yes (measured — that is the mutation this case now kills).
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENEMY_SLOTS + ENTITY_TYPE: bytes([kind]),
             A_ENEMY_SLOTS + ENTITY_ALIVE: bytes([0x80 | (EXPLOSION_LAST_FRAME - 1)]),
             A_ENEMY_SLOTS + EXPLOSION_CREDIT_TAG_OFFSET: b"\x00",
             A_ENEMY_SLOTS + ENTITY_SQUADRON: b"\x02",
             A_ENEMY_SLOTS + ENTITY_PIXEL_HIT: bytes([on_terrain]),
             collision_row(ENEMY_SLOT_FIRST): b"\x00\x00\x00\x00",
             A_SQUADRON_KILL_COUNTERS: bytes([0x5a, 0x5a, 1, 0x5a, 0x5a, 0x5a]),
             A_EXPLOSION_PHASE_EVEN: b"\x01" if kind == EXPLOSION_PART_TYPE else b"\x00",
             A_EXPLOSION_PHASE_ODD: b"\x00" if kind == EXPLOSION_TYPE_LARGE else b"\x01"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("enemy_type", (0x01, 0x02, 0x0e, 0x0f, 0x10, 0x14, 0x16, 0x11, 0x64, 0x20))
@pytest.mark.parametrize("hit_points", (1, 2))
def test_an_enemy_that_rams_the_ship_takes_its_own_arm(enemy_type, hit_points):
    """Ten enemy types against the ram dispatch, at both sides of the armoured arm's hit-point test.

    Type 1 is invulnerable and 0x11 / 0x64 are skipped before the dispatch is even reached, so the
    three that do nothing are driven beside the five that do — which is what says the gates are
    where they are. `0x20` is a type no arm names, and it must come back untouched.

    The overlap is seeded into the enemy's own collision row with the ship's two record bits, which
    is exactly the pattern `object_pair_overlap_mark` writes one stage earlier.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENEMY_SLOTS + ENTITY_TYPE: bytes([enemy_type]),
             A_ENEMY_SLOTS + ENTITY_ALIVE: b"\x01",
             A_ENEMY_SLOTS + ENTITY_HP: bytes([hit_points]),
             collision_row(ENEMY_SLOT_FIRST):
                 SHIP_RECORD_MASK.to_bytes(4, "big"),
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00",
             BUS_ERROR_VECTOR: b"\x5a\xa5"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("enemy_type", (0x01, 0x02, 0x0e, 0x0f, 0x10, 0x14, 0x16, 0x20))
@pytest.mark.parametrize("shot_type", (BULLET_TYPE, 0x32, 0x33, 0x36))
def test_a_player_shot_that_hits_an_enemy_takes_both_dispatches(enemy_type, shot_type):
    """The 6 x 8 sweep's two dispatches at once: what the ENEMY becomes and what the SHOT does.

    The two are not independent — a missile ends the inner walk from the boss-segment arm as well as
    from the ordinary one, and a bullet does not — so every (shot, enemy) pair below is a different
    path through the same block. The shot is put in slot 0, whose bit is the one `move.l #$1,d0`
    starts the sweep with.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENTITY_TABLE + ENTITY_TYPE: bytes([shot_type]),
             A_ENTITY_TABLE + ENTITY_ALIVE: b"\x01",
             A_ENEMY_SLOTS + ENTITY_TYPE: bytes([enemy_type]),
             A_ENEMY_SLOTS + ENTITY_ALIVE: b"\x01",
             A_ENEMY_SLOTS + ENTITY_HP: b"\x01",
             collision_row(ENEMY_SLOT_FIRST): (1).to_bytes(4, "big"),
             A_ACTIVE_COUNT_TYPE34: b"\x05",
             BUS_ERROR_VECTOR: b"\x5a\xa5"}
    _check_resolve(image, extra)


def test_the_shoot_pass_arms_a_voice_per_shot_slot():
    """`move.l #$1,d0` + `lsl.l #1,d0` — the sweep's D0 is the SHOT'S OWN BIT and it is also the
    channel every tune in the pass is armed on, so slots 0 and 1 reach voices 1 and 2 while the
    other four reach voice 3. A reconstruction that passed the stage's carried channel instead
    writes a different voice record, which the diff sees.

    Both of the two slots that select a named voice are driven, against the same enemy.

    THE ENEMY IS INVULNERABLE (type 1) FOR THE RETIRING KINDS, and that is load-bearing: an enemy
    that dies pays a score, and `score_add_bcd` REPLACES D0 with the extra-life threshold — so a
    case whose enemy explodes has already lost the shot bit by the time the retire's own tune is
    armed. Type 1 is the one arm that reaches the retire with the bit still in the register.
    """
    image = bytearray(world(0, WORLD_START))
    for slot in (0, 1, 2):
        shot = entity_record(slot)
        extra = {shot + ENTITY_TYPE: bytes([BULLET_TYPE]), shot + ENTITY_ALIVE: b"\x01",
                 A_ENEMY_SLOTS + ENTITY_TYPE: b"\x14", A_ENEMY_SLOTS + ENTITY_ALIVE: b"\x01",
                 collision_row(ENEMY_SLOT_FIRST): (1 << slot).to_bytes(4, "big"),
                 A_ACTIVE_COUNT_TYPE34: b"\x05", BUS_ERROR_VECTOR: b"\x5a\xa5"}
        _check_resolve(image, extra)
        for retiring in (SHOT_TYPE_BOMB, SHOT_TYPE_SEEKER):
            extra[shot + ENTITY_TYPE] = bytes([retiring])
            # ...and the projectile pass earlier in the stage must not have retired it already: a
            # pixel hit there would end this shot before the pairwise sweep ever sees it.
            extra[shot + ENTITY_PIXEL_HIT] = b"\x00"
            extra[A_ENEMY_SLOTS + ENTITY_TYPE] = b"\x01"
            _check_resolve(image, extra)


def test_the_bus_error_vector_really_is_written():
    """THE ORIGINAL'S OWN DEFECT, and it is transcribed rather than corrected: `33fc 0010 00000008`
    is `move.w #$10,$8.l` where `337c 0010 0008` would have been `move.w #$10,8(a1)`. Both encodings
    are asserted against the image so that a future reader can see the one-nibble difference, and
    the case above drives the store into a seeded vector word."""
    assert bytes(harness.BASE_IMAGE[0x122c2:0x122ca]) == bytes.fromhex("33fc001000000008")
    assert bytes(harness.BASE_IMAGE[0x123f4:0x123fc]) == bytes.fromhex("33fc001000000008")
    assert bytes(harness.BASE_IMAGE[0x1225c:0x12262]) == bytes.fromhex("337c00080008"), (
        "the sibling arm at 0x1225c is the instruction the two above meant to be")


@pytest.mark.parametrize("shot_type", (0x0b, 0x0c, 0x0a))
@pytest.mark.parametrize("row", (0, 1 << 9))
def test_an_enemy_shot_that_hits_the_landscape_morphs_or_vanishes(shot_type, row):
    """Slots 6..8 with a pixel hit and an EMPTY row: a seeker leaves a ground puff, an aimed shot
    just vanishes, and a homing missile is neither. A non-empty row means something else explains
    the hit, and the arm is skipped — which is the same `tst.l` the ship's own test makes."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_ENEMY_SHOT_SLOTS + ENTITY_TYPE: bytes([shot_type]),
             A_ENEMY_SHOT_SLOTS + ENTITY_ALIVE: b"\x01",
             A_ENEMY_SHOT_SLOTS + ENTITY_PIXEL_HIT: b"\x01",
             collision_row(ENEMY_SHOT_SLOT_FIRST): row.to_bytes(4, "big"),
             A_BOSS_SEQUENCE_ACTIVE: b"\x00"}
    _check_resolve(image, extra)


# ============================================================ the starfield and the timers

@pytest.mark.parametrize("layer2,layer3", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_the_starfield_layers_move_at_their_own_rates(layer2, layer3):
    """Layer 1 steps every frame, layer 2 only while its phase byte is clear and layer 3 only while
    its countdown is — so all four combinations are four different sets of stars moved."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_STARFIELD_LAYER2_PHASE: bytes([layer2]),
             A_STARFIELD_LAYER3_COUNTDOWN: bytes([layer3])}
    _check_resolve(image, extra)


def starfield_respawn_pokes():
    """One star of each layer at x = -1 and one at x = 0 — the boundary the `bmi` sign test is.

    The table is the binary's own, read out of `harness.BASE_IMAGE` and edited, so every star this
    case does not move keeps the value the game shipped.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`. No world sweep
    can reach this arm: layer 1 steps one pixel a frame from x = 0x13f, so a star takes three
    hundred frames to go negative and a case walks a dozen.
    """
    stars = bytearray(harness.BASE_IMAGE[A_STARFIELD_TABLE:
                                         A_STARFIELD_TABLE
                                         + STARFIELD_LAYERS * STARFIELD_STARS
                                         * STARFIELD_ENTRY_BYTES])
    for layer in range(STARFIELD_LAYERS):
        at = (layer * STARFIELD_STARS) * STARFIELD_ENTRY_BYTES
        stars[at + 2:at + 4] = (0xffff).to_bytes(2, "big")
        stars[at + STARFIELD_ENTRY_BYTES + 2:at + STARFIELD_ENTRY_BYTES + 4] = \
            (0).to_bytes(2, "big")
    return {A_STARFIELD_TABLE: bytes(stars), A_STARFIELD_LAYER2_PHASE: b"\x00",
            A_STARFIELD_LAYER3_COUNTDOWN: b"\x01"}


def test_a_star_whose_x_went_negative_respawns_at_the_right_edge():
    """`bmi` on the x word, then `move.w #$13f,(a1)+` — and the respawn does NOT consult the layer's
    speed divider, so it happens on a frozen layer too. One star of each layer is put at -1 and one
    at 0, which is the boundary the sign test is."""
    image = bytearray(world(0, WORLD_START))
    _check_resolve(image, starfield_respawn_pokes())


@pytest.mark.parametrize("countdown", (0, 1, 2, 0x80))
def test_the_far_starfield_divider_reloads_when_it_goes_negative(countdown):
    """`subq.b #1` + `bpl` — the reload happens on the step that makes the byte NEGATIVE, so 0 goes
    to -1 and reloads while 1 goes to 0 and does not. 0x80 steps to 0x7f and stays positive, which
    is what says the test is on the sign and not on zero."""
    image = bytearray(world(0, WORLD_START))
    _check_resolve(image, {A_STARFIELD_LAYER3_COUNTDOWN: bytes([countdown])})


@pytest.mark.parametrize("timer,level,floor", ((A_SHIELD_DECAY_TIMER, A_SHIELD_LEVEL, 0),
                                               (A_WEAPON_DECAY_TIMER, A_WEAPON_POWER_LEVEL,
                                                WEAPON_POWER_LEVEL_MIN),
                                               (A_SPEED_DECAY_TIMER, A_SHIP_SPEED_LEVEL, 0)))
@pytest.mark.parametrize("level_value", (0, 1, 2, 3))
def test_each_power_up_decays_to_its_own_floor(timer, level, floor, level_value):
    """Three 1000-frame timers, each stepping one level back down and each with its own floor: the
    weapon stops at 2 with an EQUALITY test, the other two at 0 with a `tst`. Only the shield's arm
    mirrors itself into the HUD and asks for a repaint, which is what separates the three.

    The timer is set to 1 so the step is due on this frame; the level is swept across and below its
    floor, because a level ALREADY under an equality floor keeps decaying.
    """
    image = bytearray(world(0, WORLD_START))
    extra = {timer: (1).to_bytes(2, "big"), level: bytes([level_value]),
             A_POWER_GAUGE_DISPLAY: b"\x5a", A_PANEL_REDRAW_MASK: b"\x00"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("page,column", ((0, 0), (MAP_PAGES - 1, 0),
                                         (MAP_PAGES - 1, SCROLL_PHASES - 1)))
def test_the_scroll_step_wraps_both_counters(page, column):
    """`addq.b #1` + `cmpi.b #$8` on the page and `#$14` on the column phase, the second only
    reached when the first wraps. Both wraps are driven from the step that reaches them."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MAP_PAGE: bytes([page]), A_MAP_COLUMN: bytes([column]),
             A_SCROLL_FROZEN: b"\x00"}
    _check_resolve(image, extra)


@pytest.mark.parametrize("cooldown", (0, 1, 2, 0x80))
def test_the_post_restart_grace_counter_stops_at_zero(cooldown):
    """`subi.b #$1` + `bpl` + `clr.b` — the counter is clamped at 0 rather than wrapping, and 0x80
    steps to 0x7f and is left alone, which is what says the test is on the sign."""
    image = bytearray(world(0, WORLD_START))
    _check_resolve(image, {A_ENEMY_SEEKER_COOLDOWN: bytes([cooldown])})


# ============================================================ the five exits

def explosion_group_done(image, group):
    """Poke every member of one explosion group to its finished frame, over the real member list.

    The list is the binary's own (`A_explosion_group_members`), read out of the image rather than
    typed, so a wrong index would mark a record the state machine does not look at.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    extra = {}
    members = A_EXPLOSION_GROUP_MEMBERS + EXPLOSION_GROUP_MEMBERS * group
    for member in range(EXPLOSION_GROUP_MEMBERS):
        record = entity_record(harness.BASE_IMAGE[members + member])
        extra[record + EXPLOSION_PART_FRAME] = bytes([EXPLOSION_DONE_FRAME])
    extra[A_EXPLOSION_GROUP_ACTIVE_BITS] = bytes([1 << group])
    return extra


def ship_death_pokes(image, lives, other_lives, other_section):
    """The ship-death swap's world, as one poke set: explosion group 1 finished, this player down to
    `lives`, and the OTHER player's saved record seeded and resumable in `other_section`.

    Both fourteen-byte records are seeded from a fixed generator, so the swap's two copies are
    diffed rather than assumed. The dying player's section index is seeded to a value the swap must
    overwrite.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`. It reaches all
    THREE of the arms this shape can take, the title exit included: `lives=1` decrements to zero,
    which is the one entry state under which the third swap can find nobody alive.
    """
    other = bytearray(random.Random(0x19f02 + other_section).randbytes(PLAYER_RECORD_BYTES))
    other[PLAYER_SAVE_LIVES] = other_lives
    other[PLAYER_SAVE_SECTION] = other_section
    extra = explosion_group_done(image, SHIP_DEATH_EXPLOSION_GROUP)
    extra.update({A_LIVES: bytes([lives]), A_CURRENT_PLAYER_INDEX: b"\x00",
                  A_LEVEL_SECTION: b"\x00", A_DYING_PLAYER_SECTION_INDEX: b"\x5a",
                  A_PLAYER_RECORDS: bytes(random.Random(0x11).randbytes(PLAYER_RECORD_BYTES))
                                    + bytes(other)})
    return extra


@pytest.mark.parametrize("lives,other_lives,other_section,exit_pc",
                         ((3, 2, 0, EXIT_RESTART_SECTION),
                          (3, 2, 5, EXIT_RELOAD_SECTION),
                          (2, 4, 0, EXIT_RESTART_SECTION),
                          (0xff, 1, 0x0f, EXIT_RELOAD_SECTION)))
def test_the_ship_death_state_machine_leaves_through_its_two_reachable_addresses(
        lives, other_lives, other_section, exit_pc):
    """The player-death arm: drop a power-up level, spend a life, save this player's state, swap to
    the other and read theirs back — then leave through whichever of three addresses the swap
    decided.

    The resumed player's level section decides between restarting in place (0x10b6e) and reloading
    (0x1083a). Both player records are seeded, so the swap's fourteen bytes each way are diffed
    rather than assumed.

    THE THIRD EXIT, 0x10500, IS NOT DRIVEN AND CANNOT BE — see
    `test_the_title_exit_is_unreachable_while_game_over_screen_is_unported` just below for the
    argument. The `game_over_screen` call on the last life is likewise out of reach here: every case
    above leaves at least one life, which is what `subi.b #$1,$1991a` + `bne` needs.
    """
    image = bytearray(world(0, WORLD_START))
    extra = ship_death_pokes(image, lives, other_lives, other_section)
    assert _check_resolve(image, extra, exit_pc) == exit_pc


def test_the_title_exit_is_unreachable_while_game_over_screen_is_unported():
    """0x10500 needs THREE swaps with nobody alive, and the third of them needs the FIRST player's
    saved lives byte to be zero — which the swap wrote from the byte `subi.b #$1,$1991a` had just
    decremented. So a run that reaches the third swap is a run whose life count hit zero, and that
    is exactly the run `beq 0x12786` sends into `game_over_screen` (0x12e66).

    That routine is only half ported: `game_over_screen_prologue` covers `[0x12e66, 0x12e94)` and
    the rest is another agent's, so src/frame.c calls it through a TEMPORARY stub and the arm cannot
    be verified. This case states the reachability argument instead of leaving the exit looking
    merely untested, and asserts the one thing that could change it — the `beq` is on the life
    count, not on something a case could pose independently.
    """
    assert bytes(harness.BASE_IMAGE[0x1277a:0x12782]) == bytes.fromhex("043900010001991a"), (
        "0x1277a is no longer `subi.b #$1,$1991a`")
    assert bytes(harness.BASE_IMAGE[0x12782:0x12784]) == bytes.fromhex("6600"), "…followed by `bne`"
    assert bytes(harness.BASE_IMAGE[0x12786:0x12788]) == bytes.fromhex("6100"), (
        "…whose fall-through is the `bsr` into game_over_screen")
    assert 0x12786 + 4 + _u16(harness.BASE_IMAGE, 0x12788) - 2 == 0x12e66


def test_the_end_of_section_explosion_advances_when_its_delay_runs_out():
    """Group 0 finished, and then `subi.b #$1,$19ac0` + `beq 0x10814`: the section advances only on
    the frame the delay reaches zero, and every other frame goes on to the loop head. Both are
    driven from the two counter values either side of the edge."""
    image = bytearray(world(0, WORLD_START))
    for counter, expected in ((1, EXIT_ADVANCE_SECTION), (2, STOP_FRAME)):
        extra = explosion_group_done(image, 0)
        extra[A_SECTION_END_DELAY_COUNTER] = bytes([counter])
        assert _check_resolve(image, extra, expected) == expected


@pytest.mark.parametrize("timer,offscreen,exit_pc",
                         ((MOTHERSHIP_LEAVE_FRAME, 0, EXIT_ADVANCE_SECTION),
                          (MOTHERSHIP_LEAVE_FRAME - 1, 1, EXIT_ADVANCE_SECTION),
                          (MOTHERSHIP_LEAVE_FRAME - 1, 0, STOP_FRAME)))
def test_the_hard_section_end_advances_on_the_timer_or_on_the_escape(timer, offscreen, exit_pc):
    """Two independent ways a section ends once the mothership is done with it, and the frame that
    ends neither way. `st`/`sf` on 0x19ce5 bracket the pair and the byte is never read anywhere in
    the image, so the two stores are transcribed for the diff and for nothing else — which is why
    the middle case leaves it SET and the last leaves it clear."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MOTHERSHIP_PHASE_TIMER: timer.to_bytes(4, "big"),
             A_MOTHERSHIP_OFFSCREEN: bytes([offscreen]),
             A_MOTHERSHIP_READY: b"\x00", A_UNUSED_SECTION_END_FLAG: b"\x5a",
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    assert _check_resolve(image, extra, exit_pc) == exit_pc


@pytest.mark.parametrize("clears,exit_pc", ((MOTHERSHIP_WAVE_CLEARS_TO_END - 1,
                                             EXIT_ADVANCE_SECTION),
                                            (0, STOP_FRAME)))
def test_clearing_the_enemy_slots_twice_ends_a_late_section(clears, exit_pc):
    """The eight enemy slots all empty, twice over, ends a section whose mothership index is 5 or
    more. Every slot is killed here — the sweep's own worlds always have something alive — and the
    counter is driven one step below its bound as well as at it."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MOTHERSHIP_READY: b"\x01", A_MOTHERSHIP_INDEX: b"\x05",
             A_MOTHERSHIP_WAVE_CLEAR_COUNT: bytes([clears]),
             A_MOTHERSHIP_PHASE_TIMER: b"\x00\x00\x00\x00",
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    for slot in range(ENEMY_SLOT_COUNT):
        extra[A_ENEMY_SLOTS + ENTITY_STRIDE * slot + ENTITY_ALIVE] = b"\x00"
    assert _check_resolve(image, extra, exit_pc) == exit_pc


@pytest.mark.parametrize("index", (4, 5))
def test_the_mothership_turns_in_one_of_two_shapes(index):
    """At MOTHERSHIP_TURN_FRAME the encounter turns and leaves. Motherships below the index own two
    ADJACENT enemy records and are turned unconditionally; the rest own four records two apart, and
    only the live ones are turned. Every record's four turn bytes are seeded, so a shape that
    touched the wrong ones differs."""
    image = bytearray(world(0, WORLD_START))
    extra = {A_MOTHERSHIP_READY: b"\x01", A_MOTHERSHIP_INDEX: bytes([index]),
             A_MOTHERSHIP_PHASE_TIMER: MOTHERSHIP_TURN_FRAME.to_bytes(4, "big"),
             A_EXPLOSION_GROUP_ACTIVE_BITS: b"\x00"}
    for slot in range(ENEMY_SLOT_COUNT):
        record = A_ENEMY_SLOTS + ENTITY_STRIDE * slot
        extra[record + ENTITY_ALIVE] = bytes([slot % 2])
        extra[record + MOTHERSHIP_TURN_SPEED_OFF] = b"\x5a\xa5"
        # +0x26, +0x27 and +0x28 in one poke: the flag, the byte it clears and the heading.
        extra[record + MOTHERSHIP_TURN_FLAG_OFF] = b"\x5a\x5a\x5a"
    _check_resolve(image, extra)


# ============================================================ fuzz

# SHARDED BY SECTION rather than by case index, which is `test_scroll.py`'s stated house rule for
# the same reason: a case's cost is dominated by BUILDING ITS WORLD (three staging oracle runs and
# four whole frames), which `world` caches per worker — so splitting by `case % chunks` would have
# every worker build all four.
FUZZ_SECTIONS = (0, 3, 7, 12)
FUZZ_CASES = 96
# Every enemy type the two pairwise dispatches name, the boss segment INCLUDED. It was kept out
# while `src/score.c` fabricated a 0 carry into `abcd`: a segment hit sharing a pass with a kill
# scored one BCD unit high, which the fuzz would have found. The flag is threaded now
# (`test_a_boss_segment_hit_carries_its_borrow_into_the_next_award`), so the type is back.
FUZZ_ENEMY_TYPES = (0x01, 0x02, 0x0e, 0x0f, 0x10, 0x11, 0x14, 0x16, 0x64, 0x65)


def fuzz_pokes(rng, image):
    """One pseudorandom set of GAME-STATE bytes, poked over a world the oracle produced.

    Every address here is a byte the game itself writes, and the values are inside the ranges its
    own code produces: an alive byte, a type from the dispatch's own list, a collision row of real
    entity bits. What is random is the COMBINATION, which is what a dozen frames of one section
    cannot reach on its own.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    extra = {A_JOYSTICK_STATE: bytes([rng.choice(JOYSTICK_BYTES)]),
             A_SELECTED_WEAPON: bytes([rng.randrange(1, 5)]),
             A_SHIELD_LEVEL: bytes([rng.randrange(3)]),
             A_FIRE_BUTTON_HELD: bytes([rng.randrange(2)]),
             A_FIRE_CHARGED: bytes([rng.randrange(2)]),
             A_FIRE_CHARGE_COUNTER: bytes([rng.randrange(FIRE_CHARGE_FULL + 1)]),
             A_EXPLOSION_PHASE_ODD: bytes([rng.randrange(2)]),
             A_EXPLOSION_PHASE_EVEN: bytes([rng.randrange(2)]),
             A_SCROLL_FROZEN: bytes([rng.randrange(2)]),
             A_MAP_PAGE: bytes([rng.randrange(MAP_PAGES)]),
             A_MAP_COLUMN: bytes([rng.randrange(SCROLL_PHASES)]),
             A_STARFIELD_LAYER2_PHASE: bytes([rng.randrange(2)]),
             A_STARFIELD_LAYER3_COUNTDOWN: bytes([rng.randrange(4)]),
             A_SHIP_TILT: bytes([rng.randrange(7)]),
             A_SHIP_TILT_COUNTDOWN: bytes([rng.randrange(1, 5)]),
             A_SHIP_SPEED_LEVEL: bytes([rng.randrange(4)])}
    for slot in range(PLAYER_SHOT_SLOTS):
        shot = entity_record(slot)
        extra[shot + ENTITY_ALIVE] = bytes([rng.choice((0, 1))])
        extra[shot + ENTITY_TYPE] = bytes([rng.choice((BULLET_TYPE, 0x32, 0x33, 0x36, 0x37))])
    for slot in range(ENEMY_SLOT_COUNT):
        enemy = A_ENEMY_SLOTS + ENTITY_STRIDE * slot
        extra[enemy + ENTITY_ALIVE] = bytes([rng.choice((0, 1, 0x80, 0x8c))])
        extra[enemy + ENTITY_TYPE] = bytes([rng.choice(FUZZ_ENEMY_TYPES)])
        extra[enemy + ENTITY_HP] = bytes([rng.randrange(1, 3)])
        extra[collision_row(ENEMY_SLOT_FIRST + slot)] = \
            rng.randrange(1 << 20).to_bytes(4, "big")
    extra[BUS_ERROR_VECTOR] = b"\x5a\xa5"
    return extra


def fuzz_cases_for(section):
    """The case indexes this section's shard owns — the same 96 cases, split four ways.

    PUBLIC because `test_asm_frame.py` is a second driver — see `advance_one_frame`.
    """
    return range(FUZZ_SECTIONS.index(section), FUZZ_CASES, len(FUZZ_SECTIONS))


@pytest.mark.parametrize("section", FUZZ_SECTIONS)
def test_frame_fuzz(section):
    """Pseudorandom combinations of the game's own state bytes, over four sections' worlds.

    Sharded by section so `-n auto` spreads it one world at a time; the generator is seeded per
    case, so a failure names the case that produced it.
    """
    image = bytearray(world(section, WORLD_START))
    for case in fuzz_cases_for(section):
        _check_resolve(image, fuzz_pokes(random.Random(0x11d30 + case), image))


@pytest.mark.parametrize("section", FUZZ_SECTIONS)
def test_frame_head_and_spawn_fuzz(section):
    """The same generator against the loop's first two stages, which read a different half of the
    state — the scroller's counters, the ship's tilt and the weapon dispatch."""
    image = bytearray(world(section, WORLD_START))
    for case in fuzz_cases_for(section):
        extra = fuzz_pokes(random.Random(0x10f4e + case), image)
        if _check_head(image, extra) == ENTRY_DRONE_AND_FIRE:
            _check_drone_and_fire(image, extra)
        _check_spawn_and_move(image, extra)


# The sound subsystem's own two tables, as include/sound.h names them.
A_TUNE_INDEX = 0x17058
A_TUNE_DATA = 0x171e8
SOUND_CMD_SET_CHANNEL = 0xfa    # `cmpi.b #$fa,(a1)` at the head of sound_start


def test_every_tune_the_frame_starts_names_its_own_voice():
    """WHY THE SOUND CHANNEL IS UNOBSERVABLE HERE, and it is a measurement rather than an excuse.

    `sound_start` takes its voice in D0, and src/frame.c transcribes which register each call site
    holds — the projectile pass's loop counter, the shoot pass's shot bit, the value
    `score_add_bcd` leaves behind. NONE OF IT REACHES THE CHIP: every one of the four tunes the
    frame loop starts opens with the stream command 0xfa, which `sound_start` reads as "use THIS
    voice" and which overwrites D0 before the voice record is chosen (src/sound.c says the same of
    the extra-life jingle).

    So a mutation that hands `sound_start` a different channel survives the suite, and this case is
    what says why rather than leaving it looking like a coverage hole. The register is transcribed
    anyway because a target build must carry it — and because in the shoot pass the SAME register is
    the collision mask, where it is very observable indeed.
    """
    for tune in (BULLET_SOUND, POWERUP_CAPSULE_SOUND, ENEMY_HIT_SOUND, EXTRA_LIFE_SOUND):
        at = A_TUNE_INDEX + 2 * tune
        # The index is a LITTLE-endian word pair, as sound_start's `move.b 1(a1),d1` + `lsl.w #8`
        # + `move.b (a1),d1` reads it.
        stream = A_TUNE_DATA + ((harness.BASE_IMAGE[at + 1] << 8) | harness.BASE_IMAGE[at])
        assert harness.BASE_IMAGE[stream] == SOUND_CMD_SET_CHANNEL, (
            f"tune {tune:#04x} no longer opens with its own channel command, so the D0 every "
            f"`sound_start` in this stage is given has become observable — the mutation that hands "
            f"it a different one should now be caught, and this case can go")


# The ground script's records, as `src/enemy.c` reads them.
A_GROUND_SCRIPT_PTRS = 0x182d2       # `lea $182d2,a0` at 0x10dda, indexed by the palette byte
A_SECTION_PALETTE_INDEX_TABLE = 0x1986c   # include/init.h
GROUND_SCRIPT_Y_OFFSET = 2           # src/enemy.c
GROUND_SPAWN_Y_BIAS = 0x20           # src/enemy.c
GROUND_SCRIPT_RECORD_BYTES = 4


def test_no_shipped_ground_script_can_make_the_spawner_read_its_carried_register():
    """WHY `ground_spawn_y_register`'s DERIVATION CANNOT BE PINNED, measured over the game's data.

    `frame_wave_script` returns the D7 the wave block leaves so that `frame_ground_script` gets the
    register the original would — a change that matters on target and cannot be tested here, and
    this case is the argument rather than an omission.

    `groundscript_spawn` (src/enemy.c) uses that register in ONE place: `set_low_word(y_register,
    scripted_y + 0x20)` and then `if (spawn_y == 0) return`. The low word is overwritten, so only the
    HIGH word can matter, and it can only matter when the low word comes out zero — which needs a
    scripted y of exactly 0xffe0. The sweep below walks every record of all thirteen distinct
    shipped ground scripts and finds none, so the guard is unreachable from the game's own data and
    a mutation that forwarded the parameter instead of deriving it survives the suite.

    If a future image ever ships such a record this case fails, and the mutation becomes catchable.
    """
    checked = 0
    for section in range(SECTION_COUNT):
        palette = harness.BASE_IMAGE[A_SECTION_PALETTE_INDEX_TABLE + section]
        at = _u32(harness.BASE_IMAGE, A_GROUND_SCRIPT_PTRS + 4 * palette)
        for _record in range(400):
            trigger = _u16(harness.BASE_IMAGE, at)
            scripted_y = _u16(harness.BASE_IMAGE, at + GROUND_SCRIPT_Y_OFFSET)
            assert (scripted_y + GROUND_SPAWN_Y_BIAS) & 0xffff != 0, (
                f"section {section}'s ground script has a record at {at:#x} whose y makes the "
                f"spawner's whole-longword guard fire — D7's high word is observable now, so the "
                f"derivation in frame_wave_script can and should be pinned by a case")
            checked += 1
            if trigger in (0, 0xffff):
                break
            at += GROUND_SCRIPT_RECORD_BYTES
    assert checked > SECTION_COUNT, "the ground scripts were not walked at all"


# include/enemy.h — one byte of energy per boss PAIR, indexed by the pair's own entity index.
# The two enemy slots the case below puts under shot 0, and the score it starts from. The pair the
# segment folds onto is `((index - 1) & ~1) + 1` over its ENTITY index, so slot 2 (entity 11) folds
# onto entity 11 — one byte of A_ENEMY_PAIR_HITPOINTS, and the case seeds the whole array anyway.
SEGMENT_SLOT, KILL_SLOT = 2, 3
CARRY_CASE_SCORE = 0x00000100
SEGMENT_ENERGY_THAT_BORROWS = 0x00
# The whole energy array is seeded, not one byte: the fold reaches four of them and a stray
# decrement elsewhere would otherwise hide. Same width test_mothership.py drives it at.
ENEMY_PAIR_HITPOINT_BYTES = 0x20


def segment_borrow_pokes():
    """Shot 0 alive as a PUFF, enemy slot 2 a boss segment whose pair energy is 0, enemy slot 3 a big
    enemy — both under shot 0's collision bit.

    The shape the carry defect below lands on, spelt once. PUBLIC because `test_asm_frame.py` is a
    second driver — see `advance_one_frame`; the twin's stub for `mothership_segment_hit` marshals
    that same borrow by hand, so this is the case that judges it.
    """
    shot = A_ENTITY_TABLE
    segment = A_ENEMY_SLOTS + ENTITY_STRIDE * SEGMENT_SLOT
    kill = A_ENEMY_SLOTS + ENTITY_STRIDE * KILL_SLOT
    shot_bit = (1 << 0).to_bytes(COLLISION_ROW_BYTES, "big")
    return {
        A_PLAYER_SCORE_BCD: CARRY_CASE_SCORE.to_bytes(SCORE_BCD_BYTES, "big"),
        A_ENEMY_PAIR_HITPOINTS: bytes([SEGMENT_ENERGY_THAT_BORROWS]) * ENEMY_PAIR_HITPOINT_BYTES,
        shot + ENTITY_ALIVE: b"\x01",
        shot + ENTITY_TYPE: bytes([SHOT_TYPE_PUFF]),
        segment + ENTITY_ALIVE: b"\x01",
        segment + ENTITY_TYPE: bytes([ENEMY_TYPE_BOSS_SEGMENT]),
        kill + ENTITY_ALIVE: b"\x01",
        kill + ENTITY_TYPE: bytes([ENEMY_TYPE_BIG]),
        collision_row(ENEMY_SLOT_FIRST + SEGMENT_SLOT): shot_bit,
        collision_row(ENEMY_SLOT_FIRST + KILL_SLOT): shot_bit,
    }


def test_a_boss_segment_hit_carries_its_borrow_into_the_next_award():
    """THE MEASURED CROSS-SUBSYSTEM DEFECT THIS STAGE ONCE CARRIED, now a case that holds the fix.

    `score_add_bcd` (0x12df6) opens with four `abcd -(a1),-(a0)`, and `abcd` ADDS the 68000's X. The
    two instructions before every one of its `bsr`s are a `movem.l` and a `lea`, neither of which
    touches the condition codes — but X SURVIVES them, so the flag reaching the first `abcd` is
    whatever arithmetic ran earlier in the pass. `src/score.c` used to start its chain at 0 on the
    argument that no caller sets it; that was true of the two instructions and false of the register.

    THE SHAPE THIS CASE LANDS ON. `mothership_segment_hit` (0x15222) ends its non-fatal arm on
    `subi.b #$1,(a5)` at 0x15254, which BORROWS when the pair's energy byte was already 0 — and the
    shoot sweep then explodes the next enemy and awards its score. Measured on the fuzz generator's
    own case 1 as 0x151 against 0x150: one BCD unit, on every kill that follows a segment hit.

    So the case is built to be exactly that: shot 0 alive as a PUFF (the one kind the pass neither
    retires nor breaks the walk on), enemy slot 2 a boss segment whose energy is 0, enemy slot 3 a
    big enemy, both under shot 0's collision bit. The award is compared by the ordinary whole-image
    diff — the score is four image bytes — so a reconstruction that fabricates the carry differs
    here and nowhere else.
    """
    _check_resolve(world(0, WORLD_START), extra=segment_borrow_pokes())


def test_the_two_instructions_the_score_carry_rests_on():
    """The carry model above is read off two instruction encodings; pin both, so a change to either
    fails HERE with a sentence rather than as a puzzling score diff.

    `score_add_bcd` must still open with four `abcd -(a1),-(a0)` (the carry chain), and
    `mothership_segment_hit` must still end its non-fatal arm on `subi.b #$1,(a5)` (the borrow).
    """
    assert bytes(harness.BASE_IMAGE[0x12dfc:0x12e04]) == bytes.fromhex("c109c109c109c109"), (
        "score_add_bcd no longer opens with four `abcd -(a1),-(a0)`")
    assert bytes(harness.BASE_IMAGE[0x15254:0x15258]) == bytes.fromhex("04150001"), (
        "mothership_segment_hit no longer ends its non-fatal arm on `subi.b #$1,(a5)`")
    assert ENEMY_TYPE_BOSS_SEGMENT in FUZZ_ENEMY_TYPES, (
        "the boss segment belongs in the fuzz now that the X flag is threaded; if it had to come "
        "back out, say why here rather than dropping the type silently")


# ============================================================ what the world staging rests on

def test_the_staged_world_is_the_game_and_not_a_seed():
    """The world images are the ORIGINAL's own output, and this is what says so.

    Four properties the boot chain leaves behind and nothing here writes: the map cursor inside the
    unpacked map, the eight page pointers naming the eight backdrop pages, a framebuffer pointer at
    one of the two hard-coded addresses, and a tile set that is not all zero. If a future change
    broke the staging into an empty image every case above would still pass — on nothing.
    """
    image = world(0, WORLD_START)
    cursor = _u32(image, A_MAP_PTR)
    assert test_init.A_MAP_UNPACKED <= cursor < test_init.A_MAP_UNPACKED + 0x3840, (
        f"the staged map cursor {cursor:#x} is not inside the unpacked map")
    pages = {_u32(image, A_MAP_PAGE_TABLE + 4 * page) for page in range(MAP_PAGES)}
    assert len(pages) == MAP_PAGES and all(p >= test_init.A_MAP_UNPACKED - 0x2d000 for p in pages)
    assert _u32(image, A_SCREEN_BACK) in (abi.SCREEN_BACK, abi.SCREEN_FRONT)
    assert any(image[test_init.A_TILE_SET_BASE:test_init.A_TILE_SET_BASE + 0x1000])


def test_the_two_carried_registers_are_read_where_the_original_reads_them():
    """The two probe PCs are the `bsr` instructions that consume the registers, not addresses near
    them: 0x118cc is `bsr.w enemy_fire_and_update_shots` and 0x11818 `bsr.w groundscript_spawn_type10`.

    A probe two bytes out would read the register one instruction early and the whole residual the
    parameters describe would be silently wrong, so the opcodes are pinned here.
    """
    assert bytes(harness.BASE_IMAGE[PROBE_CHANCE_INDEX_PC:PROBE_CHANCE_INDEX_PC + 2]) \
        == bytes.fromhex("6100")
    assert PROBE_CHANCE_INDEX_PC + 4 + _u16(harness.BASE_IMAGE, PROBE_CHANCE_INDEX_PC + 2) - 2 \
        == 0x11906
    assert bytes(harness.BASE_IMAGE[PROBE_GROUND_SPAWN_PC:PROBE_GROUND_SPAWN_PC + 2]) \
        == bytes.fromhex("6100")
    assert PROBE_GROUND_SPAWN_PC + 4 + _u16(harness.BASE_IMAGE, PROBE_GROUND_SPAWN_PC + 2) - 2 \
        == 0x13958


def test_the_slices_tile_the_loop():
    """The five ranges cover [0x10f4e, 0x1296e) exactly, in order, with no hole.

    A wrong stop mostly fails loudly on its own, so what this closes is the TILING: nothing else
    says the five slices account for every byte of the loop. Unlike `test_init.py`'s version there
    are no gaps to declare — every instruction between the head and the `bra` is inside a slice.
    """
    slices = ((ENTRY_FRAME_HEAD, ENTRY_DRONE_AND_FIRE),
              (ENTRY_DRONE_AND_FIRE, ENTRY_SPAWN_AND_MOVE),
              (ENTRY_SPAWN_AND_MOVE, ENTRY_DRAW_AND_COLLIDE),
              (ENTRY_DRAW_AND_COLLIDE, ENTRY_RESOLVE),
              (ENTRY_RESOLVE, STOP_FRAME + 4))
    at = ENTRY_FRAME_HEAD
    for lo, hi in slices:
        assert lo == at, f"the loop is not covered at {at:#x}: the next slice starts at {lo:#x}"
        assert lo < hi
        at = hi
    assert at == 0x1296e, "the last slice does not end at the loop's own last instruction"


def test_the_loop_really_is_closed_by_a_bra_to_its_head():
    """`bra.w $10f4e` at 0x1296a — the instruction that makes this a loop at all, and the stop PC
    every ordinary case uses."""
    assert bytes(harness.BASE_IMAGE[STOP_FRAME:STOP_FRAME + 2]) == bytes.fromhex("6000")
    displacement = (_u16(harness.BASE_IMAGE, STOP_FRAME + 2) ^ 0x8000) - 0x8000
    assert STOP_FRAME + 2 + displacement == ENTRY_FRAME_HEAD


def test_the_ship_sprite_bank_is_the_one_the_boot_loaded():
    """src/frame.c reaches the ship's tilt frames at the address `src/init.c`'s boot slice wrote
    them to, and that file has no header to include — so the two spellings are pinned equal here
    rather than being two numbers that happen to agree."""
    assert A_SHIP_SPRITE_BANK == BOOT_SHIP_SOURCE == test_init.BOOT_SHIP_SOURCE


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_JOYSTICK_STATE", "include/irq.h", "A_joystick_state"),
    ("A_STARFIELD_TABLE", "include/frame.h", "A_starfield_table"),
    ("A_STARFIELD_PIXEL_MASKS", "include/frame.h", "A_starfield_pixel_masks"),
    ("A_STARFIELD_LAYER2_PHASE", "include/init.h", "A_starfield_layer2_phase"),
    ("A_STARFIELD_LAYER3_COUNTDOWN", "include/init.h", "A_starfield_layer3_countdown"),
    ("A_EXPLOSION_PHASE_EVEN", "include/frame.h", "A_explosion_phase_even"),
    ("A_EXPLOSION_LARGE_FRAME_PTRS", "include/init.h", "A_explosion_large_frame_ptrs"),
    ("A_DYING_PLAYER_SECTION_INDEX", "include/frame.h", "A_dying_player_section_index"),
    ("A_PLAYER_RECORDS", "include/init.h", "A_player_records"),
    ("A_SECTION_END_DELAY_COUNTER", "include/init.h", "A_section_end_delay_counter"),
    ("A_ACTIVE_COUNT_TYPE34", "include/init.h", "A_active_bullets"),
    ("A_MOTHERSHIP_WAVE_CLEAR_COUNT", "include/init.h", "A_mothership_wave_clear_count"),
    ("A_FIRE_BUTTON_HELD", "include/frame.h", "A_fire_button_held"),
    ("A_FIRE_CHARGE_COUNTER", "include/frame.h", "A_fire_charge_counter"),
    ("A_CHARGE_FLASH_DIR", "include/frame.h", "A_charge_flash_dir"),
    ("A_SHIP_POS_HISTORY", "include/frame.h", "A_ship_pos_history"),
    ("A_SHIP_POS_HISTORY_INDEX", "include/frame.h", "A_ship_pos_history_index"),
    ("A_PANEL_LOGO_COUNTDOWN", "include/init.h", "A_panel_logo_countdown"),
    ("A_BULLET_FIRE_TOGGLE", "include/frame.h", "A_bullet_fire_toggle"),
    ("A_UNUSED_SECTION_END_FLAG", "include/frame.h", "A_unused_section_end_flag"),
    ("A_SCROLL_BLIT_JUMP_TABLE", "include/frame.h", "A_scroll_blit_jump_table"),
    ("A_SHIP_SPRITE_BANK", "include/frame.h", "A_ship_sprite_bank"),
    ("A_WAVE_ALIEN_SPRITE_A", "include/frame.h", "A_wave_alien_sprite_a"),
    ("A_WAVE_ALIEN_SPRITE_B", "include/frame.h", "A_wave_alien_sprite_b"),
    ("A_POWERUP_CAPSULE_SPRITE", "include/frame.h", "A_powerup_capsule_sprite"),
    ("A_EXPLOSION_LARGE_SPRITE", "include/frame.h", "A_explosion_large_sprite"),
    ("A_PLAYER_BULLET_SPRITE", "include/frame.h", "A_player_bullet_sprite"),
    ("A_TRAIL_DRONE_SPRITE", "include/highscore.h", "A_gunsight_sprite"),
    ("HW_MFP_IERA", "include/init.h", "HW_MFP_IERB"),
    ("KEY_SCANCODE_SPACE", "include/frame.h", "KEY_SCANCODE_SPACE"),
    ("PANEL_LOGO_PERIOD", "include/frame.h", "PANEL_LOGO_PERIOD"),
    ("MOTHERSHIP_TRIGGER_SCROLL_POS", "include/frame.h", "MOTHERSHIP_TRIGGER_SCROLL_POS"),
    ("SHIP_POS_HISTORY_ENTRIES", "include/frame.h", "SHIP_POS_HISTORY_ENTRIES"),
    ("SHIP_POS_HISTORY_ENTRY_BYTES", "include/frame.h", "SHIP_POS_HISTORY_ENTRY_BYTES"),
    ("EXPLOSION_CREDIT_TAG_OFFSET", "include/frame.h", "EXPLOSION_CREDIT_TAG_OFFSET"),
    ("TRAIL_DRONE_OFFSET_PACKED", "include/frame.h", "TRAIL_DRONE_OFFSET_PACKED"),
    ("TYPE_TRAIL_DRONE", "include/weapon.h", "TYPE_TRAIL_DRONE"),
    ("FIRE_CHARGE_FULL", "include/frame.h", "FIRE_CHARGE_FULL"),
    ("CHARGE_FLASH_STEP", "include/frame.h", "CHARGE_FLASH_STEP"),
    ("CHARGE_FLASH_PEAK", "include/frame.h", "CHARGE_FLASH_PEAK"),
    ("WEAPON_KIND_BOMB", "include/weapon.h", "WEAPON_KIND_BOMB"),
    ("WEAPON_KIND_MISSILE", "include/weapon.h", "WEAPON_KIND_MISSILE"),
    ("WEAPON_BULLET", "include/frame.h", "WEAPON_BULLET"),
    ("WEAPON_KIND_SEEKER", "include/weapon.h", "WEAPON_KIND_SEEKER"),
    ("BULLET_TYPE", "include/frame.h", "BULLET_TYPE"),
    ("BULLET_RETIRE_X", "include/frame.h", "BULLET_RETIRE_X"),
    ("BULLET_SOUND", "include/frame.h", "BULLET_SOUND"),
    ("POWERUP_CAPSULE_SOUND", "include/frame.h", "POWERUP_CAPSULE_SOUND"),
    ("ENEMY_HIT_SOUND", "include/frame.h", "ENEMY_HIT_SOUND"),
    ("EXTRA_LIFE_SOUND", "include/score.h", "EXTRA_LIFE_SOUND"),
    ("A_TUNE_INDEX", "include/sound.h", "A_tune_index"),
    ("A_TUNE_DATA", "include/sound.h", "A_tune_data"),
    ("SHOT_X_MIN", "include/frame.h", "SHOT_X_MIN"),
    ("SHOT_X_MAX", "include/frame.h", "SHOT_X_MAX"),
    ("SHOT_Y_MIN", "include/frame.h", "SHOT_Y_MIN"),
    ("SHOT_Y_MAX", "include/frame.h", "SHOT_Y_MAX"),
    ("SHOT_TYPE_MISSILE", "include/weapon.h", "SHOT_TYPE_MISSILE"),
    ("SHOT_TYPE_BOMB", "include/weapon.h", "SHOT_TYPE_BOMB"),
    ("SHOT_TYPE_SEEKER", "include/weapon.h", "SHOT_TYPE_SEEKER"),
    ("SHOT_TYPE_PUFF", "include/weapon.h", "SHOT_TYPE_PUFF"),
    ("ENTITY_SLOTS", "include/frame.h", "ENTITY_SLOTS"),
    ("COLLISION_ROW_BYTES", "include/collision.h", "COLLISION_ROW_BYTES"),
    ("EXPLOSION_GROUP_MEMBERS", "include/frame.h", "EXPLOSION_GROUP_MEMBERS"),
    ("ENEMY_SLOT_COUNT", "include/enemy.h", "ENEMY_SLOT_COUNT"),
    ("SHIP_DEATH_EXPLOSION_GROUP", "include/weapon.h", "SHIP_DEATH_EXPLOSION_GROUP"),
    ("SCRIPT_TRIGGER_LOOKAHEAD", "include/frame.h", "SCRIPT_TRIGGER_LOOKAHEAD"),
    ("GROUND_SCRIPT_Y_OFFSET", "src/enemy.c", "GROUND_SCRIPT_Y_OFFSET"),
    ("GROUND_SPAWN_Y_BIAS", "src/enemy.c", "GROUND_SPAWN_Y_BIAS"),
    ("A_SECTION_PALETTE_INDEX_TABLE", "include/init.h", "A_section_palette_index_table"),
    ("MOTHERSHIP_TURN_SPEED_OFF", "include/frame.h", "MOTHERSHIP_TURN_SPEED_OFF"),
    ("MOTHERSHIP_TURN_FLAG_OFF", "include/frame.h", "MOTHERSHIP_TURN_FLAG_OFF"),
    ("PLAYER_SAVE_LIVES", "include/frame.h", "PLAYER_SAVE_LIVES"),
    ("PLAYER_SAVE_SECTION", "include/frame.h", "PLAYER_SAVE_SECTION"),
    ("MAP_PAGE_PTR_BYTES", "include/frame.h", "MAP_PAGE_PTR_BYTES"),
    ("SHIP_SPEED_ENTRY_BYTES", "include/frame.h", "SHIP_SPEED_ENTRY_BYTES"),
    ("ENTITY_INDEX_TRAIL_DRONE", "include/weapon.h", "ENTITY_INDEX_TRAIL_DRONE"),
    ("ENTITY_INDEX_SHIP", "include/weapon.h", "ENTITY_INDEX_SHIP"),
    ("SHIP_SHADOW_SLOT", "include/frame.h", "SHIP_SHADOW_SLOT"),
    ("ENEMY_SHOT_SLOT_FIRST", "include/frame.h", "ENEMY_SHOT_SLOT_FIRST"),
    ("ENEMY_SLOT_FIRST", "include/frame.h", "ENEMY_SLOT_FIRST"),
    ("GUNSIGHT_ENEMY_MASK", "include/frame.h", "GUNSIGHT_ENEMY_MASK"),
    ("SHIP_RECORD_MASK", "include/frame.h", "SHIP_RECORD_MASK"),
    ("EXPLOSION_PART_TYPE", "include/enemy.h", "EXPLOSION_PART_TYPE"),
    ("EXPLOSION_TYPE_LARGE", "include/frame.h", "EXPLOSION_TYPE_LARGE"),
    ("EXPLOSION_LAST_FRAME", "include/frame.h", "EXPLOSION_LAST_FRAME"),
    ("EXPLOSION_FRAME_PTR_BYTES", "include/frame.h", "EXPLOSION_FRAME_PTR_BYTES"),
    ("EXPLOSION_DONE_FRAME", "include/frame.h", "EXPLOSION_DONE_FRAME"),
    ("TYPE_POWERUP_CAPSULE", "include/weapon.h", "TYPE_POWERUP_CAPSULE"),
    ("STARFIELD_LAYERS", "include/frame.h", "STARFIELD_LAYERS"),
    ("STARFIELD_STARS", "include/frame.h", "STARFIELD_STARS"),
    ("STARFIELD_ENTRY_BYTES", "include/frame.h", "STARFIELD_ENTRY_BYTES"),
    ("STARFIELD_RESPAWN_X", "include/frame.h", "STARFIELD_RESPAWN_X"),
    ("STARFIELD_LAYER3_PERIOD", "include/init.h", "STARFIELD_LAYER3_PERIOD"),
    ("POWERUP_DECAY_TICKS", "include/player.h", "POWERUP_DECAY_TICKS"),
    ("FRAME_RASTER_WAIT_PC", "include/frame.h", "FRAME_RASTER_WAIT_PC"),
    ("FRAME_VBL_WAIT_PC", "include/frame.h", "FRAME_VBL_WAIT_PC"),
    ("FRAME_RASTER_PHASE_READY", "include/frame.h", "FRAME_RASTER_PHASE_READY"),
    ("FRAME_VBL_WAIT_DONE", "include/frame.h", "FRAME_VBL_WAIT_DONE"),
    ("IKBD_CMD_INTERROGATE_JOYSTICK", "include/frame.h", "IKBD_CMD_INTERROGATE_JOYSTICK"),
    ("PLAYER_RECORD_BYTES", "include/init.h", "PLAYER_RECORD_BYTES"),
    ("PLAYER_SWAP_ATTEMPTS", "include/frame.h", "PLAYER_SWAP_ATTEMPTS"),
    ("MOTHERSHIP_TURN_FRAME", "include/frame.h", "MOTHERSHIP_TURN_FRAME"),
    ("MOTHERSHIP_LEAVE_FRAME", "include/frame.h", "MOTHERSHIP_LEAVE_FRAME"),
    ("MOTHERSHIP_WAVE_CLEARS_TO_END", "include/frame.h", "MOTHERSHIP_WAVE_CLEARS_TO_END"),
    ("BUS_ERROR_VECTOR", "include/frame.h", "BUS_ERROR_VECTOR"),
    # ...and the state this subsystem borrows from the headers that own it.
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_SHIP_RECORD_SHADOW", "include/player.h", "A_ship_record_shadow"),
    ("A_SHIP_TILT", "include/player.h", "A_ship_tilt"),
    ("A_SHIP_TILT_COUNTDOWN", "include/player.h", "A_ship_tilt_countdown"),
    ("A_SHIP_SPEED_LEVEL", "include/player.h", "A_ship_speed_level"),
    ("A_WEAPON_POWER_LEVEL", "include/player.h", "A_weapon_power_level"),
    ("A_PLAYER_RECORD", "include/enemy.h", "A_player_record"),
    ("A_ENEMY_SLOTS", "include/enemy.h", "A_enemy_slots"),
    ("A_ENEMY_SHOT_SLOTS", "include/enemy.h", "A_enemy_shot_slots"),
    ("A_ENTITY_GUNSIGHT", "include/weapon.h", "A_entity_gunsight"),
    ("A_SELECTED_WEAPON", "include/weapon.h", "A_selected_weapon"),
    ("A_SHIELD_LEVEL", "include/weapon.h", "A_shield_level"),
    ("A_ACTIVE_COUNT_TYPE32", "include/weapon.h", "A_active_count_type32"),
    ("A_ACTIVE_COUNT_BOMBS", "include/weapon.h", "A_active_count_bombs"),
    ("A_ACTIVE_COUNT_SEEKERS", "include/weapon.h", "A_active_count_seekers"),
    ("A_SEEKER_LOCK_TARGET_INDEX", "include/weapon.h", "A_seeker_lock_target_index"),
    ("A_SHIP_INVULNERABLE", "include/weapon.h", "A_ship_invulnerable"),
    ("A_DEATH_EVENT_FLAGS", "include/weapon.h", "A_death_event_flags"),
    ("A_TRAIL_DRONE_ACTIVE", "include/weapon.h", "A_trail_drone_active"),
    ("A_EXPLOSION_GROUP_ACTIVE_BITS", "include/enemy.h", "A_explosion_group_active_bits"),
    ("A_EXPLOSION_GROUP_MEMBERS", "include/enemy.h", "A_explosion_group_members"),
    ("A_EXPLOSION_PHASE_ODD", "include/enemy.h", "A_explosion_phase_odd"),
    ("A_FIRE_CHARGED", "include/enemy.h", "A_fire_charged"),
    ("A_SCROLL_FROZEN", "include/enemy.h", "A_scroll_frozen"),
    ("A_ENEMY_SEEKER_COOLDOWN", "include/enemy.h", "A_enemy_seeker_cooldown"),
    ("A_SQUADRON_KILL_COUNTERS", "include/enemy.h", "A_squadron_kill_counters"),
    ("A_GROUND_SCRIPT_CURSOR", "include/enemy.h", "A_ground_script_cursor"),
    ("A_WAVE_SCRIPT_CURSOR", "include/enemy.h", "A_wave_script_cursor"),
    ("A_SQUADRON_SPAWN_ENABLED", "include/enemy.h", "A_squadron_spawn_enabled"),
    ("A_BOSS_SEQUENCE_ACTIVE", "include/sprite.h", "A_boss_sequence_active"),
    ("A_MOTHERSHIP_READY", "include/mothership.h", "A_mothership_ready"),
    ("A_MOTHERSHIP_PREP_STAGE", "include/mothership.h", "A_mothership_prep_stage"),
    ("A_MOTHERSHIP_INDEX", "include/init.h", "A_mothership_index"),
    ("A_MOTHERSHIP_PENDING", "include/init.h", "A_mothership_pending"),
    ("A_MOTHERSHIP_PHASE_TIMER", "include/mothership.h", "A_mothership_phase_timer"),
    ("A_MOTHERSHIP_OFFSCREEN", "include/mothership.h", "A_mothership_offscreen"),
    ("A_BOSS_HITPOINTS", "include/mothership.h", "A_boss_hitpoints"),
    ("A_ENTITY_BOSS_PARTS", "include/mothership.h", "A_entity_boss_parts"),
    ("A_ASTEROID_SECTION_FLAG", "include/init.h", "A_asteroid_section_flag"),
    ("A_LEVEL_SECTION", "include/init.h", "A_level_section"),
    ("A_MAP_PAGE", "include/init.h", "A_map_page"),
    ("A_MAP_COLUMN", "include/init.h", "A_map_column"),
    ("A_MAP_OFFSET", "include/init.h", "A_map_offset"),
    ("A_MAP_PTR", "include/init.h", "A_map_ptr"),
    ("A_MAP_PAGE_TABLE", "include/init.h", "A_map_page_table"),
    ("A_SCROLL_POS", "include/init.h", "A_scroll_pos"),
    ("A_KEY_SCANCODE", "include/irq.h", "A_key_scancode"),
    ("A_PANEL_REDRAW_MASK", "include/hud.h", "A_panel_redraw_mask"),
    ("A_LIVES", "include/hud.h", "A_lives"),
    ("A_CURRENT_PLAYER_INDEX", "include/hud.h", "A_current_player_index"),
    ("A_POWERUP_CURSOR", "include/hud.h", "A_powerup_cursor"),
    ("A_POWER_GAUGE_DISPLAY", "include/hud.h", "A_power_gauge_display"),
    ("A_PALETTE_HW_SHADOW", "include/irq.h", "A_palette_hw_shadow"),
    ("A_RASTER_PHASE", "include/irq.h", "A_raster_phase"),
    ("A_VBL_WAIT_FLAG", "include/irq.h", "A_vbl_wait_flag"),
    ("A_PALETTE_SWAP_COUNTDOWN", "include/irq.h", "A_palette_swap_countdown"),
    ("A_PALETTE_ROTATE_COUNTDOWN", "include/irq.h", "A_palette_rotate_countdown"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_ENTITY_COLLISION_MASKS", "include/collision.h", "A_entity_collision_masks"),
    ("A_EXTRA_LIFE_THRESHOLD_BCD", "include/score.h", "A_extra_life_threshold_bcd"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("SCORE_BCD_BYTES", "include/score.h", "SCORE_BCD_BYTES"),
    ("A_ENEMY_PAIR_HITPOINTS", "include/enemy.h", "A_enemy_pair_hitpoints"),
    ("ENEMY_TYPE_BOSS_SEGMENT", "include/frame.h", "ENEMY_TYPE_BOSS_SEGMENT"),
    ("ENEMY_TYPE_BIG", "include/frame.h", "ENEMY_TYPE_BIG"),
    ("A_SHIELD_DECAY_TIMER", "include/weapon.h", "A_shield_decay_timer"),
    ("A_SPEED_DECAY_TIMER", "include/weapon.h", "A_speed_decay_timer"),
    ("A_WEAPON_DECAY_TIMER", "include/player.h", "A_weapon_decay_timer"),
    ("SCROLL_PHASES", "include/scroll.h", "SCROLL_PHASES"),
    ("MAP_PAGES", "include/init.h", "MAP_PAGES"),
    ("SECTION_COUNT", "include/init.h", "SECTION_COUNT"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_PIXEL_HIT", "include/entity.h", "ENTITY_PIXEL_HIT"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("ENTITY_HP", "include/entity.h", "ENTITY_HP"),
    ("ENTITY_ANIM_FRAME", "include/entity.h", "ENTITY_ANIM_FRAME"),
    ("ENTITY_SQUADRON", "include/entity.h", "ENTITY_SQUADRON"),
    ("EXPLOSION_PART_FRAME", "include/enemy.h", "EXPLOSION_PART_FRAME"),
    ("PLAYER_SHOT_SLOTS", "include/weapon.h", "PLAYER_SHOT_SLOTS"),
    ("SHIP_SPRITE_GAP", "include/sprite.h", "SHIP_SPRITE_GAP"),
    ("WEAPON_POWER_LEVEL_MIN", "include/player.h", "WEAPON_POWER_LEVEL_MIN"),
    ("BOOT_SHIP_SOURCE", "src/init.c", "BOOT_SHIP_SOURCE"),
)
# Every entry here is a MID-ROUTINE address: ../../names.txt gives three of the five an `fn` line
# and the loop head only a `cmt`, and none of them is called — they are `bra` targets. So each
# prologue is the bytes the slice's own first instructions occupy rather than a function's opening,
# and a boundary mistyped by two bytes would enter mid-instruction and decode rubbish.
ENTRY_PROLOGUES = {
    "ENTRY_FRAME_HEAD": "2c790001798261002772",
    "ENTRY_DRONE_AND_FIRE": "2f0047f900017dd24a2b",
    "ENTRY_SPAWN_AND_MOVE": "4a39000199026700004c",
    "ENTRY_DRAW_AND_COLLIDE": "61003dbc4a39000198b0",
    "ENTRY_RESOLVE": "4a3900019aad66000032",
    # NOT an entry, and pinned here for exactly that reason: it is the only address in that block
    # that two instruments STOP the original at rather than start it at, so a mistyped digit does
    # not fail to run — it runs to `max_insns`, or it halts mid-sprite-pass and hands back an image
    # whose pixel-hit flags are half set. `pixel_hit_pairs` then counts fewer pairs, and both
    # readers report the smaller number as a fact. These ten bytes are `move.w #$14,d0` +
    # `lea $18252.l,a0`, the first two instructions of the mask-table clear.
    "SPRITE_PASS_END_PC": "303c001441f900018252",
}
