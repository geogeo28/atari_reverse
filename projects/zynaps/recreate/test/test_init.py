"""Differential tests for the boot prologue and the level-section flow (src/init.c).

EVERY CASE HERE IS A CHECKPOINT RUN, and it has to be: `_start` never returns and neither does the
section chain it ends in — there is not an `rts` between 0x10000 and the frame loop at 0x10f4e. So a
case names an entry PC and a stop PC and the differential diffs the image THERE
(`docs/agent-playbook.md` §5), and each of the seven slices below states in its own docstring which
address range that proves. What lies between the ranges is in STATUS.md, not papered over.

THE FILES ARE THE DISK'S OWN, AND WHICH ONES IS THE GAME'S CHOICE. The section flow patches a
variant letter or digit into a filename in the text segment and then opens whatever the string now
says, so this file works out each section's file list from the binary's own sixteen-byte tables
rather than from a list a test author typed — a wrong table index would then stage the wrong file
and the open would be refused rather than quietly passing.
"""
import ctypes
import functools
import pathlib
import random
import re

import pytest

import abi
import emu
import harness
from harness import differential, report

# The slices, as (entry, stop). EVERY ONE is pinned by name in ENTRY_PROLOGUES at the bottom of
# this file, which is what stops a boundary mistyped by two bytes from entering mid-instruction
# and quietly running a different routine.
ENTRY_BOOT_ENTER_SUPERVISOR = 0x10000
STOP_BOOT_ENTER_SUPERVISOR = 0x10010          # the Line-A opcode, which the oracle cannot execute
ENTRY_BOOT_SAVE_VBL_VECTOR = 0x10012
STOP_BOOT_SAVE_VBL_VECTOR = 0x1001c           # the first `ikbd_send_cmd`, which busy-waits
ENTRY_BOOT_LOAD_TITLE_ASSETS = 0x1002c
STOP_BOOT_LOAD_TITLE_ASSETS = 0x101ba         # where the NINTH staged file would be opened
ENTRY_SECTION_ADVANCE = 0x10814
ENTRY_SECTION_RELOAD_NEEDED = 0x1083a
STOP_SECTION_RELOAD = 0x1085a                 # the reload arm, at its first unported `bsr`
STOP_SECTION_NO_RELOAD = 0x10b6e              # the other arm's `beq` target
ENTRY_SECTION_RELOAD_INTRO_SCREENS = 0x1085a
ENTRY_SECTION_LOAD_ASSETS = 0x10862
STOP_SECTION_LOAD_ASSETS = 0x10b6e
ENTRY_SECTION_RESTART_PROLOGUE = 0x10b6e
ENTRY_SECTION_START_PREFILL = 0x10c4e
STOP_SECTION_START_PREFILL = 0x10d96
# The prologue runs straight on into the prefill, so its stop IS that slice's entry.
STOP_SECTION_RESTART_PROLOGUE = ENTRY_SECTION_START_PREFILL
# Not a slice of this subsystem — src/scroll.c's, and pinned there. This battery enters it to
# produce the unpacked map its prefill cases run on, exactly as test_scroll.py does.
ENTRY_MAP_RLE_DECOMPRESS = 0x15920

# The nine slices this wave adds, in the order the boot runs them. Four of them stop on a hardware
# STORE rather than at the end of a logical step, and that is the whole shape of what is left
# unverified: `move.b #$xx,$fffa21` then `cmpi.b #$xx,$fffa21 / bne` is a READ-BACK of a register the
# run itself has just written, which the kit's seeded read model refuses as a stale seed and cannot
# serve (TRAP_MODEL.md, Phase 7). So each slice ends on the write and the next begins after the spin
# — twenty bytes over the four spins, and every hardware store inside a verified range.
ENTRY_BOOT_CONFIGURE_IKBD = 0x1001c
ENTRY_BOOT_LOAD_GAMEPLAY_ASSETS = 0x101ba
STOP_BOOT_LOAD_GAMEPLAY_ASSETS = 0x104c8
ENTRY_BOOT_INSTALL_IKBD_ISR = 0x104c8
ENTRY_BOOT_FRONT_END_PROLOGUE = 0x10500
STOP_BOOT_FRONT_END_PROLOGUE = 0x10520     # the `bsr title_attract_loop` the prologue ends at
ENTRY_BOOT_STAGE_FRONTEND_SCREENS = 0x10524
ENTRY_BOOT_PROGRAM_TIMER_B = 0x105c6
STOP_BOOT_PROGRAM_TIMER_B = 0x1062e        # the first read-back spin's own `cmpi.b`
ENTRY_BOOT_PROGRAM_RASTER_TIMER = 0x10638
STOP_BOOT_PROGRAM_RASTER_TIMER = 0x1066c   # ...and the second's
ENTRY_BOOT_ENABLE_INTERRUPTS = 0x10676
ENTRY_BOOT_NEW_GAME_RECORDS = 0x10792      # ...which is also where 0x1069e's `bra.w` lands
ENTRY_SECTION_START_TAIL = 0x10d96
STOP_SECTION_START_TAIL = 0x10f4e           # the frame loop, which is another agent's
ENTRY_ATTRACT_PROGRAM_TIMER_B = 0x12ac2
STOP_ATTRACT_PROGRAM_TIMER_B = 0x12b0a
ENTRY_ATTRACT_PROGRAM_RASTERBAR_TIMER = 0x12b14
STOP_ATTRACT_PROGRAM_RASTERBAR_TIMER = 0x12b48
ENTRY_ATTRACT_BUILD_COLOUR_BARS = 0x12b52
ENTRY_ATTRACT_WAIT_FOR_START = 0x12bb4     # ...which is also that slice's stop
STOP_ATTRACT_BUILD_COLOUR_BARS = ENTRY_ATTRACT_WAIT_FOR_START

# ---- mirrors of include/init.h ----
A_VECTOR_VBL = 0x70
A_VECTOR_TIMER_B = 0x120
A_VBL_ISR = 0x10776
A_TIMER_B_ISR = 0x10782
A_SAVED_TOS_VBL_VECTOR = 0x195d0
SHIFTER_MODE_RESOLUTION_MASK = 0xfc
A_LEVEL_SECTION = 0x19895
A_LEVEL_SECTION_LOADED = 0x19913
A_SHOW_PREPARE_FOR_COMBAT = 0x19aac
A_ASTEROID_SECTION_FLAG = 0x198fd
A_MOTHERSHIP_INDEX = 0x1987c
A_SECTION_GROUND_TARGET_FLAG = 0x19897
A_PALETTE_ASTEROID = 0x19638
A_KEY_SCANCODE = 0x19685             # include/irq.h — borrowed, see its note there
A_MOTHERSHIP_PENDING = 0x198af
SECTION_RESTART_SHIP_X = 0x40
SECTION_RESTART_SHADOW_X = 0x50
SECTION_RESTART_SHIP_Y = 0x64
SECTION_RESTART_SHIP_ROWS = 0x14
SECTION_RESTART_KILL_SLOTS = 18
SECTION_RESTART_ASTEROID_RECORDS = 18
SQUADRON_MARKS = 6
SECTION_RESTART_LAUNCH_STOCK = 2
# --- mirrors of include/sprite.h and include/weapon.h, which own the other two figures ---
SHIP_SPRITE_GAP = 1600
PLAYER_SHOT_SLOTS = 6
# --- mirrors of the headers the prologue borrows its resets from ---
A_ENTITY_GUNSIGHT = 0x17dd2          # include/weapon.h
A_DEATH_EVENT_FLAGS = 0x198c4        # include/weapon.h
A_MISSILE_LAUNCH_COUNTER = 0x198b5   # include/weapon.h
A_BOMB_LAUNCH_COUNTER = 0x198b6      # include/weapon.h
A_ASTEROID_RECORDS = 0x17e2a         # include/enemy.h
A_SQUADRON_KILL_COUNTERS = 0x198bb   # include/enemy.h
A_EXPLOSION_GROUP_ACTIVE_BITS = 0x19670  # include/enemy.h
A_SCROLL_FROZEN = 0x198b1            # include/enemy.h
A_PLAYER_RECORD = 0x17d7a            # include/enemy.h
A_MOTHERSHIP_READY = 0x198b0         # include/mothership.h
A_ENTITY_TABLE = 0x17a8e             # include/player.h
A_SHIP_RECORD_SHADOW = 0x17da6       # include/player.h
ENTITY_STRIDE = 0x2c                 # include/entity.h
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT = 0x00, 0x04, 0x08
ENTITY_SPRITE, ENTITY_ALIVE, ENTITY_TYPE = 0x0a, 0x0e, 0x11
ENTITY_SLOTS = 20
A_PALETTE_NEXT = 0x19f66
A_PALETTE_PER_SECTION_TABLE = 0x18fe4
SECTION_COUNT = 0x10
SECTION_TYPE_ASTEROID = 0x71
SECTION_PALETTE_BYTES = 0x20
A_ALIEN_VARIANT_TABLE = 0x197fc
A_ALIEN2_VARIANT_TABLE = 0x1980c
A_MOTHERSHIP_VARIANT_TABLE = 0x1981c
A_MISSILE_VARIANT_TABLE = 0x197eb
A_SECTION_TYPE_TABLE = 0x1984c
A_ZYN_VARIANT_TABLE = 0x1985c
A_SECTION_PALETTE_INDEX_TABLE = 0x1986c
A_GROUND_TARGET_BY_PALETTE_TABLE = 0x19898
A_SECTION_RESTART_TABLE = 0x19e84
A_SCROLL_POS = 0x195cc
A_MAP_OFFSET = 0x1823e
A_MAP_PTR = 0x18242
A_MAP_PAGE = 0x198a5
A_MAP_PAGE_PTR = 0x17986
A_MAP_PAGE_TABLE = 0x1798a
A_MAP_COLUMN = 0x198a6
MAP_PAGES = 8
SECTION_PREFILL_COLUMNS = 0xa0
A_FILENAME_SMALLEXP_DAT = 0x1971a
A_FILENAME_NEWBULS2_DAT = 0x19727
A_FILENAME_SEEKER2_DAT = 0x19741
A_FILENAME_ALSEEK_DAT = 0x19763
A_FILENAME_ALTEXPL_DAT = 0x1976e
A_FILENAME_NEWBOMB_DAT = 0x1977a
A_FILENAME_GUNSIGHT_DAT = 0x19786
A_FILENAME_SWEAP_DAT = 0x19793
A_FILENAME_SSWEAP_DAT = 0x1979d
A_FILENAME_SMLOGOS_DAT = 0x197a8
A_FILENAME_EXTCHARS_DAT = 0x197b4
A_FILENAME_LIFEGRA_DAT = 0x197c1
A_FILENAME_ZYNLOGO_DAT = 0x19686
A_FILENAME_HEWLOGO_DAT = 0x197cd
A_EXPLOSION_LARGE_FRAME_PTRS = 0x1922c
EXPLOSION_FRAME_PTRS = 12
IKBD_CMD_DISABLE_MOUSE = 0x12
IKBD_CMD_JOYSTICK_INTERROGATE_MODE = 0x15
IKBD_CMD_INTERROGATE_JOYSTICKS = 0x16
SECTION_TAIL_SOUND_CHANNEL_FROM_D0 = IKBD_CMD_INTERROGATE_JOYSTICKS
A_VECTOR_ACIA = 0x118
A_IKBD_ACIA_ISR = 0x14456
A_GAME_INITIALISED = 0x1991c
A_PLAYER_COUNT = 0x1991d
A_PLAYER_RECORDS = 0x19f02
BOOT_SOUND_CHANNEL_FROM_DBF = 0xff
PLAYER_RECORD_BYTES = 0x0e
PLAYER_RECORD_SCORE, PLAYER_RECORD_LIVES, PLAYER_RECORD_SECTION = 0x00, 0x04, 0x05
PLAYER_RECORD_MAP_PTR, PLAYER_RECORD_POWERUP = 0x06, 0x0a
PLAYER_RECORD_WEAPON, PLAYER_RECORD_SPEED = 0x0b, 0x0c
PLAYER_RECORD_START_LIVES = 3
PLAYER_RECORD_START_SECTION = 0xff
PLAYER_RECORD_START_WEAPON = 2
BOOT_PREATTRACT_CLEAR_A = 0x0a
BOOT_PREATTRACT_CLEAR_B = 0x16
MFP_TIMER_B_PERIOD_PLAIN = 0xac
MFP_TIMER_B_PERIOD_RASTER = 0xc8
MFP_TIMER_B_PERIOD_ATTRACT_SETUP = 0x00
MFP_TIMER_B_PERIOD_ATTRACT_BARS = 0x02
MFP_IER_TIMER_B = 0x01
MFP_TIMER_B_STOPPED = 0x00
MFP_TIMER_B_EVENT_COUNT = 0x08
MFP_ACIA_CHANNEL_BIT = 6            # include/irq.h — one name for MFP channel 6
HW_MFP_IERA = 0xfffa07
HW_MFP_IMRA = 0xfffa13
HW_MFP_IERB = 0xfffa09
HW_MFP_IMRB = 0xfffa15
HW_MFP_TIMER_B_CONTROL = 0xfffa1b
HW_MFP_TIMER_B_DATA = 0xfffa21
A_VBL_MENU = 0x13c26
A_TIMER_B_RASTER_ISR = 0x106ae
A_STARFIELD_LAYER2_PHASE = 0x198a9
A_STARFIELD_LAYER3_COUNTDOWN = 0x198aa
STARFIELD_LAYER3_PERIOD = 3
A_EVENT_SCRIPT_A_TABLE = 0x182d2
A_EVENT_SCRIPT_B_TABLE = 0x18306
SCRIPT_TABLE_ENTRY_BYTES = 4
SCRIPT_ENTRY_BYTES = 4
SCRIPT_ENTRY_PAYLOAD = 2
SCRIPT_OP_SQUADRON_SPAWN_ON = 0x0c
SCRIPT_OP_SQUADRON_SPAWN_OFF = 0x0d
A_SLOT_DIR_FLAGS = 0x19673
SLOT_DIR_FLAGS_BYTES = 13
A_ACTIVE_BULLETS = 0x19909
A_MOTHERSHIP_WAVE_CLEAR_COUNT = 0x19915
A_PANEL_LOGO_COUNTDOWN = 0x19dce
A_POWERUP_FLASH_CURSOR = 0x19dd4
A_SECTION_END_DELAY_COUNTER = 0x19ac0
SECTION_TAIL_WEAPON_SLOTS = 3
SECTION_TAIL_POWERUP_SLOT = 1
SECTION_TAIL_PANEL_MASK = 7
SECTION_TAIL_LOGO_TICKS = 1
SECTION_TAIL_GROUND_RND = 0x0a
SECTION_TAIL_GRACE_TICKS = 0x14
SECTION_TAIL_END_DELAY = 0x32
SECTION_TAIL_SECTION_START_SFX = 0x27
A_ATTRACT_VBL_ISR = 0x12c9e
A_ATTRACT_RASTERBAR_ISR = 0x12cc0
A_ATTRACT_BAR_PATTERN = 0x19f28
ATTRACT_BAR_GROUPS = 7
ATTRACT_BAR_PAIR_BYTES = 4
ATTRACT_BAR_COLOUR = 2
ATTRACT_BAR_LIST_LONGS = 0x29
A_ATTRACT_BAR_HUE = 0x19f20
ATTRACT_HUE_STEP = 0x89
ATTRACT_HUE_MASK = 0x777
A_ATTRACT_BAR_SCROLL_TIMER = 0x198c6
ATTRACT_BAR_SCROLL_PERIOD = 2
ATTRACT_BAR_SCROLL_PAIRS = 16
A_ATTRACT_PAGE_TIMER = 0x19f1e
A_ATTRACT_PAGE_TOGGLE = 0x199ed
ATTRACT_PAGE_FRAMES = 0x2ee
KEY_SCANCODE_1 = 0x02
KEY_SCANCODE_2 = 0x03
ATTRACT_PLAYERS_DEFAULT = 2
ATTRACT_PLAYERS_ONE = 1
# --- mirrors of the headers the new slices borrow from ---
A_VSYNC_FLAG = 0x198ab               # include/irq.h
A_IKBD_PACKET_PTR = 0x195d4          # include/irq.h
A_IKBD_PACKET_REMAINING = 0x19671    # include/irq.h
A_IKBD_JOYSTICK_STATE = 0x19680      # include/irq.h
A_JOYSTICK_STATE = 0x19681           # include/irq.h
A_MENU_PALETTE = 0x19f46             # include/irq.h
A_ATTRACT_RASTER_LIST = 0x1a976      # include/irq.h
A_BACKDROP_PAGE0 = 0x1a8ae           # include/video.h
A_PALETTE_FRONTEND = 0x195f8         # include/hud.h
A_LIVES = 0x1991a                    # include/hud.h
A_CURRENT_PLAYER_INDEX = 0x1991b     # include/hud.h
A_POWERUP_CURSOR = 0x19905           # include/hud.h
A_POWERUP_ACTIVE_SLOT = 0x19906      # include/hud.h
A_PANEL_REDRAW_MASK = 0x19904        # include/hud.h
A_POWER_GAUGE_DISPLAY = 0x198c3      # include/hud.h
A_PLAYER_SCORE_BCD = 0x195e0         # include/score.h
A_WEAPON_POWER_LEVEL = 0x19908       # include/player.h
A_SHIP_SPEED_LEVEL = 0x19907         # include/player.h
A_WEAPON_DECAY_TIMER = 0x19dcc       # include/player.h
A_SHIELD_LEVEL = 0x1990a             # include/weapon.h
A_SPEED_DECAY_TIMER = 0x19dc8        # include/weapon.h
A_SHIELD_DECAY_TIMER = 0x19dca       # include/weapon.h
A_SELECTED_WEAPON = 0x198b4          # include/weapon.h
A_ACTIVE_COUNT_TYPE32 = 0x1990b      # include/weapon.h
A_ACTIVE_COUNT_BOMBS = 0x1990c       # include/weapon.h
A_ACTIVE_COUNT_SEEKERS = 0x1990d     # include/weapon.h
A_MISSILE_LOCK_A = 0x19918           # include/weapon.h
A_MISSILE_LOCK_B = 0x19919           # include/weapon.h
A_SEEKER_LOCK_TARGET_INDEX = 0x19917 # include/weapon.h
A_ENEMY_SEEKER_COOLDOWN = 0x19abf    # include/enemy.h
A_WAVE_SCRIPT_CURSOR = 0x1824e       # include/enemy.h
A_GROUND_SCRIPT_CURSOR = 0x1824a     # include/enemy.h
A_SQUADRON_SPAWN_ENABLED = 0x19aae   # include/enemy.h
A_GROUND_SPAWN_RND_PARAM = 0x198c1   # include/enemy.h
A_BOSS_SEQUENCE_ACTIVE = 0x19aad     # include/sprite.h
A_MOTHERSHIP_PHASE_TIMER = 0x19efe   # include/mothership.h
A_MOTHERSHIP_OFFSCREEN = 0x19916     # include/mothership.h
A_PANEL_MASTER = 0x41eae             # include/hud.h
PANEL_TOP_OFFSET = 0x5be0            # include/hud.h
PANEL_MASTER_LONGWORDS = 0x848       # include/hud.h
A_FILENAME_ALIEN_DAT = 0x196b0
A_FILENAME_MOTHER_DAT = 0x196e8
A_FILENAME_MISSILE_DAT = 0x1970d
A_FILENAME_LEV_MAP = 0x197d9
A_FILENAME_ZYN_DAT = 0x197e2
BOOT_POWER_GAUGE_DST = 0x607be
BOOT_SHIP_SOURCE = 0x577fe
FILENAME_ALIEN_VARIANT = 5
FILENAME_MOTHER_VARIANT = 6
FILENAME_MISSILE_VARIANT = 7
FILENAME_LEV_VARIANT = 3
FILENAME_ZYN_VARIANT = 3

# ---- mirrors of include/scroll.h and include/video.h ----
A_TILE_SET_BASE = 0x4b3be
A_MAP_UNPACKED = 0x478ae
MAP_ROWS = 18
MAP_COLUMNS = 400
MAP_COLUMN_BYTES = 0x24
SCROLL_PHASES = 20
SCROLL_PHASE_STEP = 8
A_SCROLL_PREFILL_HIDE_SCREEN = 0x19ac1
A_SCROLL_COL_WORKSPACE = 0x19fae
SCROLL_COLUMN_PASSES = 72
SCROLL_COLUMN_CELL_LONGS = 8
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
SCREEN_ROW_BYTES = 160
PLAYFIELD_BYTES = 0x5a00

# The two hard-coded framebuffer addresses `_start` fixes. They already have a home in test/abi.py,
# which the scratch map is laid out around, so the mirrors below take THEM as the Python side rather
# than restating the numbers — which makes the MIRRORS entries a pin between abi.py and src/init.c.
BOOT_SCREEN_BACK = abi.SCREEN_BACK
BOOT_SCREEN_FRONT = abi.SCREEN_FRONT

MAP_UNPACKED_BYTES = MAP_COLUMNS * MAP_COLUMN_BYTES
WORKSPACE_BYTES = SCROLL_COLUMN_PASSES * SCROLL_COLUMN_CELL_LONGS * 4
DISK = harness.PRG.parent / "disk"

# The ACIA's data port and the ledger's own byte-width tag, imported from the batteries that own
# them: the port is the KIT's constant (`OS_HW_ACIA_DATA`) and the width tag is the harness's, so
# neither can be pinned to an include/ header by `test_constants.py`'s MIRRORS.
from test_input import BYTE, HW_ACIA_DATA                                # noqa: E402

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_boot_enter_supervisor.argtypes = [_u8p]
harness._lib.g_boot_enter_supervisor.restype = ctypes.c_uint32
harness._lib.g_section_reload_needed.argtypes = [_u8p]
harness._lib.g_section_reload_needed.restype = ctypes.c_uint32
harness._lib.init_shifter_mode_mask_written.argtypes = []
harness._lib.init_shifter_mode_mask_written.restype = ctypes.c_uint8
harness._lib.g_section_load_assets.argtypes = [_u8p]
harness._lib.g_section_load_assets.restype = ctypes.c_uint32
harness._lib.g_boot_front_end_prologue.argtypes = [_u8p]
harness._lib.g_boot_front_end_prologue.restype = ctypes.c_uint32
for _sym in ("g_boot_save_vbl_vector", "g_boot_load_title_assets", "g_section_advance",
             "g_section_reload_intro_screens", "g_section_restart_prologue",
             "g_section_start_prefill", "g_boot_configure_ikbd", "g_boot_load_gameplay_assets",
             "g_boot_install_ikbd_isr", "g_boot_stage_frontend_screens", "g_boot_program_timer_b",
             "g_boot_program_raster_timer", "g_boot_enable_interrupts", "g_boot_new_game_records",
             "g_section_start_tail", "g_attract_program_timer_b",
             "g_attract_program_rasterbar_timer", "g_attract_build_colour_bars",
             "g_attract_wait_for_start"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None


def _table_byte(table, section):
    """One per-section table byte, read out of the loaded image."""
    return harness.BASE_IMAGE[table + section]


def _section_files(section):
    """The files this section's own tables name, in the order the flow opens them.

    Derived from the binary rather than transcribed: the flow patches each variant character into
    the filename and opens the patched string, so this is the same lookup the code does — and an
    index this test got wrong would stage a file the routine never opens, whose own open would then
    be refused by the trap model instead of passing quietly.
    """
    names = [f"alien{chr(_table_byte(A_ALIEN_VARIANT_TABLE, section))}.dat",
             f"alien{chr(_table_byte(A_ALIEN2_VARIANT_TABLE, section))}.dat",
             f"mother{chr(_table_byte(A_MOTHERSHIP_VARIANT_TABLE, section))}.dat",
             f"missile{chr(_table_byte(A_MISSILE_VARIANT_TABLE, section))}.dat"]
    kind = chr(_table_byte(A_SECTION_TYPE_TABLE, section))
    if ord(kind) == SECTION_TYPE_ASTEROID:
        return names + ["bigast.dat"]
    names.append(f"lev{kind}.map")
    names.append(f"zyn{chr(_table_byte(A_ZYN_VARIANT_TABLE, section))}.dat")
    palette_index = _table_byte(A_SECTION_PALETTE_INDEX_TABLE, section)
    names.append("gndtarg1.dat"
                 if _table_byte(A_GROUND_TARGET_BY_PALETTE_TABLE, palette_index) else "rocket.dat")
    return names


def _is_asteroid_section(section):
    return _table_byte(A_SECTION_TYPE_TABLE, section) == SECTION_TYPE_ASTEROID


MAP_SECTIONS = tuple(s for s in range(SECTION_COUNT) if not _is_asteroid_section(s))
ASTEROID_SECTIONS = tuple(s for s in range(SECTION_COUNT) if _is_asteroid_section(s))


def _stage(names):
    """Stage the named disk files, which is what lets the routine's Fopen/Fread/Fclose be served."""
    pokes, _handles = harness.stage_files([(n, (DISK / n.upper()).read_bytes()) for n in names])
    return pokes


def _slice_case(entry, stop, pokes, glue, label, poison=False, max_insns=200_000):
    diffs, info = differential(entry, {"_pokes": pokes}, glue, stop_pc=stop, poison=poison,
                               max_insns=max_insns)
    assert not diffs, f"{label} [{entry:#x}, {stop:#x})\n{report(diffs)}"
    return info


# ============================================================ boot_enter_supervisor @ 0x10000

def test_boot_enter_supervisor():
    """GEMDOS Super(0), and then the program takes the old supervisor stack as its own.

    THE SLICE WRITES NO IMAGE BYTE — the three pushes are stack and the trap is served from the
    model — so the empty diff is not the assertion here; the token in D0 is, and it is compared
    against the ORACLE's own D0. What no image differential can reach is that A7 then becomes that
    token: `emu.REPORTED_REGS` does not carry A7, and the reconstruction has no machine stack of its
    own. STATUS.md records that residual rather than this case pretending to hold it.
    """
    info = _slice_case(ENTRY_BOOT_ENTER_SUPERVISOR, STOP_BOOT_ENTER_SUPERVISOR, {},
                       lambda lib, buf: lib.g_boot_enter_supervisor(buf), "super")
    assert info["ret"] == info["regs"]["d0"], (
        f"Super(0) token cand={info['ret']:#x} oracle={info['regs']['d0']:#x}")
    assert info["ret"] == harness.OS_SUPER_TOKEN


# ============================================================ boot_save_vbl_vector @ 0x10012

@pytest.mark.parametrize("vector", (0x00fc1234, 0, 0xffffffff))
def test_boot_save_vbl_vector(vector):
    """`move.l $70.l,$195d0.l`, over three values of the vector TOS left there.

    Both addresses are inside the image, so this is the one part of the boot prologue that is
    ordinary diffable memory. The destination is seeded with a value that is neither of them, which
    is what makes a candidate that copied nothing differ (both addresses are otherwise zero in the
    loaded image, and zero over zero differs nowhere).
    """
    pokes = {A_VECTOR_VBL: vector.to_bytes(4, "big"), A_SAVED_TOS_VBL_VECTOR: b"\x5a\xa5\x5a\xa5"}
    _slice_case(ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR, pokes,
                lambda lib, buf: lib.g_boot_save_vbl_vector(buf), f"vbl={vector:#x}")


def test_boot_save_vbl_vector_attribution():
    """Poison: a candidate that wrote nothing stays canary at the destination."""
    pokes = {A_VECTOR_VBL: (0x00fc1234).to_bytes(4, "big")}
    _slice_case(ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR, pokes,
                lambda lib, buf: lib.g_boot_save_vbl_vector(buf), "poison", poison=True)


# ========================================================= boot_load_title_assets @ 0x1002c

# The eight files `_start` reads before the slice's end, in the order it reads them. Unlike the
# section flow's, these filenames are constants in the table and are never patched — so the list is
# read off the `lea`s in the disassembly and the assertion below is what ties it to them.
BOOT_FILES = ("zynpic.pic", "power.dat", "myship.dat", "status.pi1", "bullet.dat", "explode.dat",
              "gemgraf.dat", "spinners.dat")
BOOT_MAX_INSNS = 4_000_000


def test_boot_files_are_the_names_the_table_holds():
    """Each name in BOOT_FILES is the nul-terminated string at the address `_start` passes.

    Cheap, and it is what stops the list above from drifting into a list of files that happen to be
    on the disk: a `lea` this battery misread would stage a file the slice never opens.
    """
    for address, name in ((0x19692, "zynpic.pic"), (0x1969d, "power.dat"), (0x196bb, "myship.dat"),
                          (0x196c6, "status.pi1"), (0x196d1, "bullet.dat"),
                          (0x196dc, "explode.dat"), (0x196f4, "gemgraf.dat"),
                          (0x19700, "spinners.dat")):
        end = harness.BASE_IMAGE.index(0, address)
        assert bytes(harness.BASE_IMAGE[address:end]).decode("ascii") == name


def test_boot_load_title_assets():
    """The longest stretch of `_start` the harness can run end to end: 0x1002c to 0x101ba.

    Eight files read straight off the disk into the addresses the game gives them, the two
    framebuffer pointers fixed at their hard-coded values, the game's own VBL and Timer B vectors
    installed over TOS's, the title tune started, the picture published, its palette uploaded, seven
    ship frames de-interleaved and one four-frame preshift bank built. Every one of those is a leaf
    another battery already verified; what THIS case proves is the composition — the order and the
    addresses — over the whole image at once.

    THE SLICE'S OFF-IMAGE HALF IS THE KIT'S NOW. Every hardware store this stretch makes — the
    resolution byte at $ff8260, the screen base the flip publishes, the sixteen colour registers
    `set_palette_title` uploads — is compared by `harness.differential` itself, address, width, value
    and order (tools/recreate_kit/TRAP_MODEL.md, "Phase 10"). Deleting the palette upload from the
    slice, or aiming the resolution store at another register, is a red without anything here.

    ONE RESIDUAL SURVIVES THAT, and the assertion below is what holds it. `andi.b #$fc,$ff8260` is a
    read-modify-write, and the oracle's read of a register the seeded READ model does not name
    answers a fabricated 0 — so `0 & mask` is 0 for every mask and the ledger cannot tell $fc from
    $ff. The sink records the mask itself; it rides on the run the differential has just made, so it
    needs no second 4-million-instruction pass. On target that read decides the other six bits of the
    mode register (`docs/on-target-execution.md`).
    """
    _slice_case(ENTRY_BOOT_LOAD_TITLE_ASSETS, STOP_BOOT_LOAD_TITLE_ASSETS, _stage(BOOT_FILES),
                lambda lib, buf: lib.g_boot_load_title_assets(buf), "boot assets",
                max_insns=BOOT_MAX_INSNS)
    assert harness._lib.init_shifter_mode_mask_written() == SHIFTER_MODE_RESOLUTION_MASK


# ================================================================ section_advance @ 0x10814

@pytest.mark.parametrize("section", tuple(range(SECTION_COUNT)) + (0xff,))
def test_section_advance(section):
    """Every section number, plus 0xff.

    The wrap is a `cmpi.b #$10` against the INCREMENTED byte, so 15 wraps to 0 and 0xff — which the
    flow never produces, but which the byte can hold — increments to 0 and is left there rather than
    wrapping again. The map cursor is reset to the level's first column whichever way it goes, and
    it is seeded elsewhere so a candidate that skipped the reset differs.
    """
    pokes = {A_LEVEL_SECTION: bytes([section]), A_MAP_PTR: b"\x00\x0d\xea\xdc"}
    _slice_case(ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED, pokes,
                lambda lib, buf: lib.g_section_advance(buf), f"section={section:#x}")


def test_section_advance_attribution():
    """Poison: the map cursor reset and the section byte are both attributable."""
    _slice_case(ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED, {A_LEVEL_SECTION: b"\x07"},
                lambda lib, buf: lib.g_section_advance(buf), "poison", poison=True)


# =========================================================== section_reload_needed @ 0x1083a

@pytest.mark.parametrize("loaded,section,reload_needed",
                         ((0, 0, False), (3, 3, False), (0xff, 0xff, False),
                          (0, 1, True), (3, 4, True), (0xff, 0, True)))
def test_section_reload_needed(loaded, section, reload_needed):
    """The gate's two arms, which END AT DIFFERENT ADDRESSES — so each is its own checkpoint.

    Equal, the flow branches straight to the section start and this slice writes nothing at all;
    different, it records the section as loaded and clears the PREPARE FOR COMBAT banner. Both
    destination bytes are seeded to values neither arm produces, so the no-write arm is a real
    assertion rather than an empty one.
    """
    pokes = {A_LEVEL_SECTION: bytes([section]), A_LEVEL_SECTION_LOADED: bytes([loaded]),
             A_SHOW_PREPARE_FOR_COMBAT: b"\x5a"}
    stop = STOP_SECTION_RELOAD if reload_needed else STOP_SECTION_NO_RELOAD
    info = _slice_case(ENTRY_SECTION_RELOAD_NEEDED, stop, pokes,
                       lambda lib, buf: lib.g_section_reload_needed(buf),
                       f"loaded={loaded:#x} section={section:#x}")
    assert bool(info["ret"]) == reload_needed


# ============================================================ section_load_assets @ 0x10862

SECTION_LOAD_MAX_INSNS = 20_000_000


@pytest.mark.parametrize("section", MAP_SECTIONS)
def test_section_load_assets(section):
    """Every non-asteroid section, over the files its own tables name.

    THE FILENAMES ARE PATCHED IN THE TEXT SEGMENT and the diff covers them, so this case holds the
    nine table lookups as well as the loads they steer: a wrong index writes a different letter into
    `alien_.dat` and the open is then refused by the trap model rather than passing. Downstream of
    the loads it also composes the map unpacker, four preshift builders, five block copies and the
    per-section palette row — every one of them verified elsewhere, with the ORDER and the addresses
    proved here.
    """
    pokes = _stage(_section_files(section))
    pokes[A_LEVEL_SECTION] = bytes([section])
    info = _slice_case(ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS, pokes,
                       lambda lib, buf: lib.g_section_load_assets(buf), f"section={section}",
                       max_insns=SECTION_LOAD_MAX_INSNS)
    assert info["ret"] == 1, f"section {section} is a map section but the map arm did not run"


@pytest.mark.parametrize("section", ASTEROID_SECTIONS)
def test_section_load_assets_of_an_asteroid_section(section):
    """Each of the four asteroid sections in full, over BIGAST.DAT and its own four other files.

    This case covers the prefix as well as the arm. An earlier revision stopped the oracle at the
    `beq` itself (0x109e2) so the shared prefix could be verified while the arm was unported; that
    checkpoint is gone with the arm's landing, because the candidate has no prefix to stop at.

    The arm is short and every one of its effects is in the diff: the six sprite banks built and
    preshifted into `A_backdrop_page0` (46 KB of them), the flag the map arm CLEARS and this one
    SETS, and the fixed 32-byte palette row it takes instead of a per-section one. It also proves
    the arm SKIPS the map: the tile-set buffer holds BIGAST.DAT's bytes and nothing else, where the
    map arm would have overwritten them with a level file twice over.
    """
    pokes = _stage(_section_files(section))
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes[A_ASTEROID_SECTION_FLAG] = b"\x5a"      # neither arm's answer, so the store is visible
    # ...and a palette row unlike anything in the per-section table, which is what makes the SOURCE
    # ADDRESS observable — see test_the_asteroid_palette_row_is_only_pinned_by_a_poke below.
    pokes[A_PALETTE_ASTEROID] = ASTEROID_PALETTE_PROBE
    info = _slice_case(ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS, pokes,
                       lambda lib, buf: lib.g_section_load_assets(buf), f"asteroid section={section}",
                       max_insns=SECTION_LOAD_MAX_INSNS)
    assert info["ret"] == 0, f"section {section} is an asteroid section but the map arm ran"


# A colour row no shipped table holds. The shifter ignores the top nibble of each pen and the game
# never writes one, so the probe stays inside the 0x0777 range a real palette uses — it is a palette
# the level designer did not choose, not a nonsense value.
ASTEROID_PALETTE_PROBE = bytes.fromhex(
    "0111022203330444055506660777011302240335044604570560067107120123")


def test_the_asteroid_palette_row_is_only_pinned_by_a_poke():
    """THE SHIPPED 0x19638 ROW IS BYTE-IDENTICAL TO ROW 0 OF THE TABLE AT 0x18fe4. Measured.

    So on the shipped image a candidate that took the asteroid palette from the per-section table's
    first row would copy exactly the same 32 bytes, and no case over the game's own data could tell
    the two sources apart — a mutation swapping them survived the whole suite until the case above
    started poking `ASTEROID_PALETTE_PROBE` over 0x19638. The poke is real program data given to
    BOTH sides, not a fabricated record; this assertion is what stops it looking arbitrary, and it
    fails loudly if a future image ever makes the two rows differ on their own.
    """
    shipped = bytes(harness.BASE_IMAGE[A_PALETTE_ASTEROID:
                                       A_PALETTE_ASTEROID + SECTION_PALETTE_BYTES])
    row_zero = bytes(harness.BASE_IMAGE[A_PALETTE_PER_SECTION_TABLE:
                                        A_PALETTE_PER_SECTION_TABLE + SECTION_PALETTE_BYTES])
    assert shipped == row_zero, (
        "0x19638 and the per-section table's row 0 no longer agree — the poke in "
        "test_section_load_assets_of_an_asteroid_section is no longer the only thing pinning the "
        "asteroid arm's palette source, and this note can be simplified")
    assert ASTEROID_PALETTE_PROBE != shipped
    assert len(ASTEROID_PALETTE_PROBE) == SECTION_PALETTE_BYTES


def test_the_asteroid_palette_row_is_not_one_of_the_per_section_rows():
    """The asteroid arm's `movem.l $19638` reads a row OUTSIDE the sixteen-row table at 0x18fe4.

    Without this the two arms' palette work would look like one lookup with a different index, and a
    candidate that reached the asteroid row by indexing the table would pass every case above.
    """
    assert not (A_PALETTE_PER_SECTION_TABLE <= A_PALETTE_ASTEROID
                < A_PALETTE_PER_SECTION_TABLE + SECTION_COUNT * SECTION_PALETTE_BYTES)


def test_section_load_assets_covers_both_ground_targets():
    """The two arms of `tst.b $19897` are both reached by the shipped sections.

    The ground-target graphic is chosen by a flag that is itself a table byte, so which arm a
    section takes is the level designer's and not this battery's; this is where the claim that both
    are exercised is held against the tables rather than assumed.
    """
    chosen = {_section_files(section)[-1] for section in MAP_SECTIONS}
    assert chosen == {"gndtarg1.dat", "rocket.dat"}, chosen


ASTEROID_SECTION_COUNT = 4       # measured: the section-type table's four 'q' entries


def test_both_arms_are_driven_and_every_section_is_one_or_the_other():
    """Four of the sixteen sections branch at 0x109e2, and BOTH arms now have cases above.

    This used to say the asteroid arm was unported. It is not: `test_section_load_assets_of_an_
    asteroid_section` drives all four. What the count still buys is that neither list can quietly
    empty — if a table changed and every section became a map section, MAP_SECTIONS would claim
    coverage of an arm nothing exercised.
    """
    assert len(ASTEROID_SECTIONS) == ASTEROID_SECTION_COUNT
    assert len(MAP_SECTIONS) == SECTION_COUNT - ASTEROID_SECTION_COUNT
    assert ASTEROID_SECTIONS and MAP_SECTIONS


# ================================================ section_reload_intro_screens @ 0x1085a
# ...and section_restart_prologue @ 0x10b6e.
#
# BOTH SLICES CALL TWO WHOLE FRONT-END SCREENS (`player_intro_screen` @ 0x13426 and
# `status_panel_redraw_all` @ 0x135bc), so they need every graphic those two read staged at the
# address `_start` loads it to. test_hud.py already derives that set from the .PRG and the disk —
# the eight .DAT files and the three panel strips CUT OUT OF STATUS.PI1 rather than staged from
# anywhere else — and rebuilding it here would be a second source of truth for panel graphics.
# It is imported instead, which is also what test_constants.py does to every battery.
#
# NEITHER SLICE TAKES A POISON PASS, for test_hud.py's own two reasons: `player_intro_screen` ends
# in `screen_flip_buffers`, which writes the very longwords it read its draw buffer from, and
# `draw_power_gauge` inside the panel repaint writes a clamped level back and then indexes a frame
# table with it. Both are recorded there; nothing is added here.
import test_hud                                                          # noqa: E402

# The four names this battery borrows from it, checked at import so a rename over there fails HERE
# with a sentence instead of an AttributeError inside an unrelated case. `_buffer_pokes` is still
# underscore-private, which is exactly why nothing in test_hud would otherwise signal the dependency;
# `panel_pokes` was made public when the asm-twin suites started driving it too, and its docstring
# now names both borrowers — the guard stays because a public name can be renamed as easily.
for _borrowed in ("panel_pokes", "_buffer_pokes", "A_SCREEN_BACK_BUFFER", "A_SCREEN_FRONT_BUFFER"):
    assert hasattr(test_hud, _borrowed), (
        f"test_init.py's two front-end slices reuse test_hud.{_borrowed} for its panel staging; "
        f"that name is gone, so either restore it or give this battery its own staging")

RESET_SEED = 0x5a               # neither arm's answer for any byte the prologue clears or sets


def _front_end_pokes(seed, extra=None):
    """test_hud.py's panel staging plus the two buffer pointers, which its cases pass separately."""
    return test_hud.panel_pokes(seed, {
        **test_hud._buffer_pokes(test_hud.A_SCREEN_BACK_BUFFER, test_hud.A_SCREEN_FRONT_BUFFER),
        **(extra or {})})


def test_section_reload_intro_screens():
    """Two `bsr`s: the PLAYER n screen, then the whole status panel.

    THE ORDER IS *NOT* THE ASSERTION, and saying so is the point of this docstring. Swapping the two
    calls was mutation-tested and SURVIVED: `status_panel_redraw_all` writes every panel piece to
    BOTH framebuffers, and `player_intro_screen`'s `playfield_clear` touches only rows 0..143 while
    the panel starts at row 147 — so the `screen_flip_buffers` between them exchanges two pointers
    whose buffers end up holding the same bytes either way. STATUS.md's mutation ledger carries the
    argument and names the surface that WOULD catch it (a rendered-pixel or on-target one).

    What this case does assert is that both calls happen, over the real graphics, at the addresses
    `_start` gives them — a slice that dropped one of them differs on tens of thousands of bytes.
    """
    _slice_case(ENTRY_SECTION_RELOAD_INTRO_SCREENS, ENTRY_SECTION_LOAD_ASSETS,
                _front_end_pokes(seed=0x1085a & 0xff),
                lambda lib, buf: lib.g_section_reload_intro_screens(buf), "reload intro")


def _restart_pokes(seed, alive, extra=None):
    """The prologue's whole input set: a live-or-dead entity table, live asteroid records, and every
    byte it clears or sets seeded to a value it does not produce.

    `alive` seeds BOTH record arrays' alive bytes and the six shot slots' type bytes, so a sweep one
    record short leaves a set byte standing where the original cleared it. The banner byte is seeded
    to neither 0 nor 1 for the same reason.
    """
    table = bytearray()
    for index in range(ENTITY_SLOTS):
        record = bytearray(random.Random(0x10b6e + seed + index).randbytes(ENTITY_STRIDE))
        record[ENTITY_ALIVE] = alive
        record[ENTITY_TYPE] = alive
        table += record
    asteroids = bytearray()
    for index in range(SECTION_RESTART_ASTEROID_RECORDS):
        record = bytearray(random.Random(0x17e2a + seed + index).randbytes(ENTITY_STRIDE))
        record[ENTITY_ALIVE] = alive
        asteroids += record
    # ...and one record past the ASTEROID array, at 0x18142, which nothing else in this poke set
    # touches: that is what pins its count of eighteen. The entity array gets NO such guard, because
    # the record after its twentieth IS `A_asteroid_records` — its own count is pinned instead by
    # the ship's shadow at slot 18 (`test_the_restart_prologue_leaves_the_ship_shadow_alive`), which
    # is the only slot an overrun of one could touch observably.
    asteroids += random.Random(0x2001 + seed).randbytes(ENTITY_STRIDE)

    pokes = {
        A_ENTITY_TABLE: bytes(table),
        A_ASTEROID_RECORDS: bytes(asteroids),
        A_SHOW_PREPARE_FOR_COMBAT: bytes([RESET_SEED]),
        A_DEATH_EVENT_FLAGS: bytes([RESET_SEED]),
        A_MISSILE_LAUNCH_COUNTER: bytes([RESET_SEED, RESET_SEED]),   # ...and the bomb counter beside it
        A_SQUADRON_KILL_COUNTERS: bytes([RESET_SEED] * (SQUADRON_MARKS + 1)),  # +1: a guard byte
        A_KEY_SCANCODE: bytes([RESET_SEED]),
        A_EXPLOSION_GROUP_ACTIVE_BITS: bytes([RESET_SEED]),
        A_SCROLL_FROZEN: bytes([RESET_SEED]),
        A_MOTHERSHIP_READY: bytes([RESET_SEED]),
        A_MOTHERSHIP_PENDING: bytes([RESET_SEED]),
    }
    pokes.update(extra or {})
    return _front_end_pokes(seed, pokes)


@pytest.mark.parametrize("alive", (0x00, 0x01, 0x80, 0xff))
def test_section_restart_prologue(alive):
    """0xd0 bytes of resets reaching five subsystems, plus the two front-end screens.

    The alive byte is swept because every clear is a `clr.b` on a byte whose entry value the sweeps
    must not depend on — and 0x00 going in is the case that would hide a missing clear, which is why
    it is driven beside three non-zero ones rather than instead of them.
    """
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=alive, alive=alive),
                lambda lib, buf: lib.g_section_restart_prologue(buf), f"alive={alive:#04x}")


def test_the_restart_prologue_leaves_the_ship_shadow_alive():
    """The one record the sweep does NOT kill, and it is not the last one.

    `move.w #$11,d0` + dbf covers slots 0..17; the `clr.b $17de0` after it is the GUNSIGHT's alive
    byte at slot 19, so slot 18 — the ship's shadow — keeps whatever it had. A candidate that read
    the count as nineteen, or the stray clear as "one more slot", agrees with the original on every
    other byte and differs on exactly this one. The arithmetic is asserted here as well as driven,
    because the address 0x17de0 appears in the original as a bare literal.
    """
    assert A_ENTITY_GUNSIGHT + ENTITY_ALIVE == 0x17de0
    assert A_SHIP_RECORD_SHADOW == A_ENTITY_TABLE + 18 * ENTITY_STRIDE
    assert A_ENTITY_GUNSIGHT == A_ENTITY_TABLE + 19 * ENTITY_STRIDE
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=7, alive=0xff),
                lambda lib, buf: lib.g_section_restart_prologue(buf), "shadow survives")


def test_the_restart_prologue_rewrites_the_ship_pair_last():
    """The pair's positions, sprites and heights, over records seeded to none of them.

    The two sprite longwords are ONE FRAME APART (names.txt's 0x640 stride on 0x111f4), which is
    what this holds against them being two unrelated literals — and the height pair is written from
    a SECOND `lea` of the same record after the position pair, so a candidate that folded the two
    blocks into one still has to put the same bytes at the same four offsets.
    """
    seeded = bytes([RESET_SEED]) * ENTITY_STRIDE
    _slice_case(ENTRY_SECTION_RESTART_PROLOGUE, STOP_SECTION_RESTART_PROLOGUE,
                _restart_pokes(seed=9, alive=1,
                               extra={A_PLAYER_RECORD: seeded + seeded}),
                lambda lib, buf: lib.g_section_restart_prologue(buf), "ship pair")


# ========================================================= section_start_prefill @ 0x10c4e

PREFILL_MAX_INSNS = 20_000_000


@functools.lru_cache(maxsize=None)
def _unpacked_map(level):
    """The map the game gets, produced by the ORIGINAL'S OWN unpacker (as test_scroll.py does).

    Cached because every prefill case wants the same level, and each miss is a full oracle run of
    `map_rle_decompress` plus a 39 KB read off the disk.
    """
    image = harness.make_image({A_TILE_SET_BASE: (DISK / level).read_bytes()})
    final, _writes, _regs = emu.run(image, ENTRY_MAP_RLE_DECOMPRESS, {})
    return bytes(final[A_MAP_UNPACKED:A_MAP_UNPACKED + MAP_UNPACKED_BYTES])


def _prefill_pokes(section, map_ptr, page, column, asteroid, seed):
    """All eight pages, the framebuffer and the column workspace seeded, then the real map and tile
    set poked over regions no seed covers.

    THE WORKSPACE IS AN OUTPUT TOO — the tile decoder fills it and the emitter drains it — and it
    abuts page 0 (`A_scroll_col_workspace` + its length is `A_backdrop_page0`), so its upper guard
    band and that page's span overlap. `abi.seed_spans` merges them rather than letting the later
    poke silently win, which is the whole reason the seeding goes through it.

    THE LAST PAGE HAS NO UPPER GUARD BAND, and it cannot: page 7 ends at exactly `A_map_unpacked`,
    so the map poked in below wins those sixteen bytes. The map's own bytes are a distinguishable
    non-zero neighbour, so an over-run past page 7 still differs — but it differs against real data
    rather than against a seed, and the assertion below is what stops that adjacency changing
    silently.
    """
    assert PREFILL_PAGES[-1] + PLAYFIELD_BYTES == A_MAP_UNPACKED, (
        "the last page no longer abuts the unpacked map — re-check this case's guard bands")
    pokes = abi.seed_spans(seed, tuple((base, base + PLAYFIELD_BYTES) for base in PREFILL_PAGES)
                           + ((abi.SCREEN_BACK, abi.SCREEN_BACK + PLAYFIELD_BYTES),
                              (A_SCROLL_COL_WORKSPACE, A_SCROLL_COL_WORKSPACE + WORKSPACE_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[A_MAP_UNPACKED] = _unpacked_map("LEV1.MAP")
    pokes[A_TILE_SET_BASE] = (DISK / "ZYN1.DAT").read_bytes()
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    pokes[A_MAP_PTR] = map_ptr.to_bytes(4, "big")
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes[A_MAP_PAGE] = bytes([page])
    pokes[A_MAP_COLUMN] = bytes([column])
    pokes[A_ASTEROID_SECTION_FLAG] = bytes([asteroid])
    return pokes


# The eight off-screen pages `map_page_table` names, read out of the image so a table that moved
# fails here rather than leaving eight seeded spans pointing at nothing.
PREFILL_PAGES = tuple(
    int.from_bytes(bytes(harness.BASE_IMAGE[A_MAP_PAGE_TABLE + 4 * page:
                                            A_MAP_PAGE_TABLE + 4 * page + 4]), "big")
    for page in range(MAP_PAGES))


@pytest.mark.parametrize("section", (0, 1, 7, 15))
def test_section_start_prefill_every_restart_entry(section):
    """The restart search at four sections, then 160 columns of backdrop pre-rendered.

    The search walks the word table BACKWARDS from the section's own eight-byte slot, so the section
    number decides where it starts and the map cursor decides where it stops — and the three globals
    it publishes (`map_ptr`, `map_offset`, `scroll_pos`) are all diffed. The pre-fill then drives
    160 columns through `scroll_emit_tile_column` and `scroll_emit_column_shift2` into all eight
    pages, which is the composition test for the whole scroller: every page is seeded over a full
    playfield, so a candidate that filled the wrong page, or stopped a column short, differs.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(section, A_MAP_UNPACKED, 0, 0, 0, seed=0x100 + section),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"section={section}",
                max_insns=PREFILL_MAX_INSNS)


# The rewind cases, as (map cursor, does the pre-render run?). THE PRE-RENDER IS OFF FOR THREE OF
# THEM, and that is a measurement rather than a shortcut: the rewind is decided BEFORE the pre-fill
# loop and the asteroid guard returns straight after the search publishes its three globals, so an
# asteroid run tests exactly the arithmetic these cases are about at a thousandth of the cost (~1 ms
# against ~500 ms). Two are kept full so that "the pre-fill starts from the REWOUND cursor" — which
# no other case covers, since every other one starts below the floor — still has a witness.
REWIND_CASES = ((A_MAP_UNPACKED, True),
                (A_MAP_UNPACKED + 20 * MAP_COLUMN_BYTES, False),
                (0x47b7e, True),
                (0x47b7e + 0x2d0, False),
                (A_MAP_UNPACKED + 300 * MAP_COLUMN_BYTES, False))


@pytest.mark.parametrize("map_ptr,prerender", REWIND_CASES)
def test_section_start_prefill_rewinds_past_the_floor(map_ptr, prerender):
    """The `cmp.l #$47b7e` / `sub.l #$2d0` rewind, at and either side of its edge.

    A cursor at or past the floor is pulled back twenty columns before the restart search runs, so
    the two cases at 0x47b7e and 0x47b7e + 0x2d0 are what say the comparison is `>=` and that the
    subtraction is twenty columns and not some other distance.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(4, map_ptr, 0, 0, 0 if prerender else 1, seed=map_ptr),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"map_ptr={map_ptr:#x}",
                max_insns=PREFILL_MAX_INSNS)


@pytest.mark.parametrize("page,column", ((0, 0), (1, 0), (7, 3), (7, SCROLL_PHASES - 1)))
def test_section_start_prefill_starts_mid_ring(page, column):
    """The pre-fill picks up wherever the page and column counters already are.

    Page 0 is the one that decodes a fresh tile column and advances the map; pages 1..7 re-emit the
    same workspace two pixels further along. Starting at page 7 and at the last column phase is what
    exercises both wraps — the page counter's at eight and the column's at twenty.
    """
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(0, A_MAP_UNPACKED, page, column, 0, seed=0x200 + page * 32 + column),
                lambda lib, buf: lib.g_section_start_prefill(buf), f"page={page} column={column}",
                max_insns=PREFILL_MAX_INSNS)


def test_section_start_prefill_asteroid_section_renders_nothing():
    """`tst.b $198fd` before the loop: an asteroid section has no backdrop, so the search publishes
    its three globals and the routine returns without touching a page. The eight seeded pages coming
    back untouched is the assertion."""
    _slice_case(ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL,
                _prefill_pokes(1, A_MAP_UNPACKED, 0, 0, 1, seed=0x300),
                lambda lib, buf: lib.g_section_start_prefill(buf), "asteroid",
                max_insns=PREFILL_MAX_INSNS)


def test_section_start_prefill_publishes_the_search_result():
    """The three globals the restart search publishes, read back out of the ORACLE's final image.

    NO POISON PASS, and it is measured rather than an omission: `map_ptr` is both an input to the
    search and its output, and `map_page` / `map_column` are both the pre-fill's cursors and its
    results, so an attribution run poisons the routine's own control flow and the oracle diverges
    (`docs/agent-playbook.md` §8). This case is what stands in its place — the two derived longwords
    are checked against the cursor the search settled on, so a candidate that published the cursor
    and left the other two alone fails here even though both are otherwise diffed against a
    destination that happens to hold the right bytes.
    """
    pokes = _prefill_pokes(4, A_MAP_UNPACKED + 300 * MAP_COLUMN_BYTES, 0, 0, 1, seed=0x400)
    final, _writes, _regs = emu.run(harness.make_image(pokes), ENTRY_SECTION_START_PREFILL, {},
                                    stop_pc=STOP_SECTION_START_PREFILL,
                                    max_insns=PREFILL_MAX_INSNS)
    cursor = int.from_bytes(bytes(final[A_MAP_PTR:A_MAP_PTR + 4]), "big")
    offset = int.from_bytes(bytes(final[A_MAP_OFFSET:A_MAP_OFFSET + 4]), "big")
    scroll_pos = int.from_bytes(bytes(final[A_SCROLL_POS:A_SCROLL_POS + 4]), "big")
    assert offset == cursor - A_MAP_UNPACKED, "map_offset is not the cursor's offset into the map"
    assert scroll_pos == (offset // MAP_COLUMN_BYTES) * SCROLL_PHASE_STEP, (
        "scroll_pos is not the column index times one cell's bytes")


# ============================================================ the slices, and the gaps between them

# Every slice's range, and every GAP between them with the reason it is a gap. The seven slices are
# checkpoint runs and STATUS.md explains each gap in prose; this table is the same claim in a form a
# test can walk, so a slice cannot be silently narrowed and a gap cannot silently grow.
SLICES = (
    (ENTRY_BOOT_ENTER_SUPERVISOR, STOP_BOOT_ENTER_SUPERVISOR),
    (ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR),
    (ENTRY_BOOT_LOAD_TITLE_ASSETS, STOP_BOOT_LOAD_TITLE_ASSETS),
    (ENTRY_SECTION_ADVANCE, ENTRY_SECTION_RELOAD_NEEDED),
    (ENTRY_SECTION_RELOAD_NEEDED, STOP_SECTION_RELOAD),
    (ENTRY_SECTION_LOAD_ASSETS, STOP_SECTION_LOAD_ASSETS),
    (ENTRY_SECTION_START_PREFILL, STOP_SECTION_START_PREFILL),
)
GAPS = (
    (0x10010, 0x10012, "the Line-A opcode, which the oracle takes as an exception"),
    (0x1001c, 0x1002c, "the two ikbd_send_cmd calls, which spin on the unmodelled ACIA at $fffc00"),
    (0x101ba, 0x10814, "the rest of _start: more than the model's eight staged-file slots"),
    (0x1085a, 0x10862, "player_intro_screen and status_panel_redraw_all, neither ported"),
    (0x10b6e, 0x10c4e, "the same two, plus resets of globals five other subsystems own"),
)

# The two bytes the "modelled as a no-op" claim rests on, and the two `bsr`s the ACIA gap is made of.
LINE_A_HIDE_MOUSE = bytes.fromhex("a00a")
IKBD_SEND_CMD_CALLS = bytes.fromhex("103c00126100442210 3c00156100441a".replace(" ", ""))


def test_the_slices_and_their_gaps_tile_the_flow():
    """The seven ranges and the five gaps cover [0x10000, 0x10d96) exactly, in order, with no hole.

    A wrong STOP mostly fails loudly on its own (a divergent diff, or `max_insns`), so the exposure
    this closes is the TILING: nothing else says the ranges plus the declared gaps account for every
    byte between the entry and the last checkpoint. A slice narrowed by an edit, or a gap that grew
    because a stop moved, shows up here with the address rather than only in STATUS.md's prose.
    """
    spans = sorted(SLICES + tuple((lo, hi) for lo, hi, _why in GAPS))
    at = ENTRY_BOOT_ENTER_SUPERVISOR
    for lo, hi in spans:
        assert lo == at, f"the flow is not covered at {at:#x}: the next span starts at {lo:#x}"
        assert lo < hi, f"span [{lo:#x}, {hi:#x}) is empty or backwards"
        at = hi
    assert at == STOP_SECTION_START_PREFILL


def test_the_line_a_gap_really_is_the_line_a_opcode():
    """The Line-A is modelled as a no-op, and nothing but these two bytes says it is one.

    `ENTRY_PROLOGUES` below pins what each slice STANDS ON; this pins what the gaps stand on. If
    0x10010 held some other instruction the seven slices would all still pass and the no-op model
    would be wrong with no witness at all.
    """
    at = 0x10010
    assert bytes(harness.BASE_IMAGE[at:at + len(LINE_A_HIDE_MOUSE)]) == LINE_A_HIDE_MOUSE


def test_the_acia_gap_really_is_the_two_ikbd_sends():
    """...and the same for the other gap the harness cannot run: `move.b #$12,d0 / bsr ikbd_send_cmd`
    twice over, with 0x15 the second time. Sixteen bytes, so a gap that grew to swallow a real
    instruction fails here."""
    at = 0x1001c
    assert bytes(harness.BASE_IMAGE[at:at + len(IKBD_SEND_CMD_CALLS)]) == IKBD_SEND_CMD_CALLS


# ================================================== boot_configure_ikbd @ 0x1001c

def test_boot_configure_ikbd():
    """Two IKBD commands, and the slice's whole effect is the pair of ledgered stores they make.

    IT WRITES NO IMAGE BYTE — `ikbd_send_cmd` polls the ACIA status and stores the command, and
    neither address is in the image — so the empty diff is not the assertion here. The hardware WRITE
    ledger is: two byte stores to $fffc02, in that ORDER, which is what says 0x12 goes first and what
    a candidate sending only one of them fails. The two status polls are in the READ ledger beside
    them, so "it waited for the transmitter" is compared too.

    The second command is the load-bearing one: 0x15 takes the joysticks out of auto-reporting, which
    is why every later wait on the stick has to ASK for it with 0x16.
    """
    info = _slice_case(ENTRY_BOOT_CONFIGURE_IKBD, ENTRY_BOOT_LOAD_TITLE_ASSETS, {},
                       lambda lib, buf: lib.g_boot_configure_ikbd(buf), "ikbd setup")
    assert info["regs"]["hw_writes"] == [
        (HW_ACIA_DATA, BYTE, IKBD_CMD_DISABLE_MOUSE),
        (HW_ACIA_DATA, BYTE, IKBD_CMD_JOYSTICK_INTERROGATE_MODE)], (
        "the two IKBD commands did not reach the ACIA's data port in the original's order")


def test_the_boot_prologue_is_covered_end_to_end_but_for_the_line_a_opcode():
    """The four slices from 0x10000 to 0x101ba join up, and this states the one gap between them.

    `boot_enter_supervisor` [0x10000, 0x10010), the Line-A opcode at 0x10010 (two bytes, modelled as
    a no-op — the oracle takes it as an exception and no case can run through it),
    `boot_save_vbl_vector` [0x10012, 0x1001c), `boot_configure_ikbd` [0x1001c, 0x1002c) and
    `boot_load_title_assets` [0x1002c, 0x101ba). Cheap, and it is what stops a later slice edit from
    quietly opening a hole that no failing case would name.
    """
    ranges = [(ENTRY_BOOT_ENTER_SUPERVISOR, STOP_BOOT_ENTER_SUPERVISOR),
              (ENTRY_BOOT_SAVE_VBL_VECTOR, STOP_BOOT_SAVE_VBL_VECTOR),
              (ENTRY_BOOT_CONFIGURE_IKBD, ENTRY_BOOT_LOAD_TITLE_ASSETS),
              (ENTRY_BOOT_LOAD_TITLE_ASSETS, STOP_BOOT_LOAD_TITLE_ASSETS)]
    for (_lo, hi), (next_lo, _next_hi) in zip(ranges, ranges[1:]):
        gap = next_lo - hi
        assert gap in (0, LINE_A_OPCODE_BYTES), (
            f"[{hi:#x}, {next_lo:#x}) is neither joined nor the Line-A opcode")


LINE_A_OPCODE_BYTES = 2


# ========================================== boot_load_gameplay_assets @ 0x101ba

# The fourteen files this slice reads, in the order the `lea`s name them. Like BOOT_FILES above, none
# of these is patched — they are constants in the table at 0x19686 — so the list is read off the
# disassembly and the assertion below is what ties it to the strings the image really holds.
GAMEPLAY_FILES = ("smallexp.dat", "newbuls2.dat", "seeker2.dat", "alseek.dat", "altexpl.dat",
                  "newbomb.dat", "gunsight.dat", "sweap.dat", "ssweap.dat", "smlogos.dat",
                  "extchars.dat", "lifegra.dat", "zynlogo.dat", "hewlogo.dat")
GAMEPLAY_FILE_NAMES = (A_FILENAME_SMALLEXP_DAT, A_FILENAME_NEWBULS2_DAT, A_FILENAME_SEEKER2_DAT,
                       A_FILENAME_ALSEEK_DAT, A_FILENAME_ALTEXPL_DAT, A_FILENAME_NEWBOMB_DAT,
                       A_FILENAME_GUNSIGHT_DAT, A_FILENAME_SWEAP_DAT, A_FILENAME_SSWEAP_DAT,
                       A_FILENAME_SMLOGOS_DAT, A_FILENAME_EXTCHARS_DAT, A_FILENAME_LIFEGRA_DAT,
                       A_FILENAME_ZYNLOGO_DAT, A_FILENAME_HEWLOGO_DAT)
GAMEPLAY_MAX_INSNS = 12_000_000


def test_gameplay_files_are_the_names_the_table_holds():
    """Each name in GAMEPLAY_FILES is the nul-terminated string at the address the slice passes."""
    for address, name in zip(GAMEPLAY_FILE_NAMES, GAMEPLAY_FILES):
        end = harness.BASE_IMAGE.index(0, address)
        assert bytes(harness.BASE_IMAGE[address:end]).decode("ascii") == name


# THE TWO BANKS THE SHIPPED IMAGE LEAVES EMPTY, and they have to be seeded or two of this slice's
# counts are untestable. Both are bss the loads only partly fill: the ship's fourteen frames run to
# 0x5cf7e and only the first seven were written by the slice before this one, and NEWBULS2.DAT is
# four frames of a bank eight would fit. A build one frame too long therefore writes ZEROES OVER
# ZEROES and the diff stays empty — measured, as two surviving mutants, before these two spans were
# seeded. The guard band past each is what turns "one frame too many" into a difference.
SHIP_PRESHIFT_FRAMES = 14
SHIP_PRESHIFT_SPAN = (BOOT_SHIP_SOURCE, BOOT_SHIP_SOURCE + SHIP_PRESHIFT_FRAMES * SHIP_SPRITE_GAP)
BULLET_BANK = 0x62a5e
BULLET_BANK_FRAME_BYTES = 0x1e
PRESHIFT_BANK_SLOTS = 8
# ...seeded ONE WHOLE BANK wider than the four frames the file fills, which is the width a build of
# eight frames would reach.
BULLET_BANK_SPAN = (BULLET_BANK,
                    BULLET_BANK + PRESHIFT_BANK_SLOTS * PRESHIFT_BANK_SLOTS
                    * BULLET_BANK_FRAME_BYTES)


def test_the_two_seeded_banks_really_are_empty_in_the_shipped_image():
    """...and this is why the two spans above are seeded rather than left alone.

    If a future image ever ships those bytes non-zero the seeds stop being load-bearing, and a reader
    would have no way to tell that from the pokes. Cheap, and it names the reason.
    """
    for lo, hi in (SHIP_PRESHIFT_SPAN, BULLET_BANK_SPAN):
        tail = bytes(harness.BASE_IMAGE[lo + (hi - lo) // 2:hi])
        assert not any(tail), (
            f"[{lo:#x}, {hi:#x}) is no longer empty in the shipped image, so the seed over it is "
            f"covering real data rather than making an empty bank observable")


def test_boot_load_gameplay_assets():
    """0x101ba to 0x104c8: fourteen files and every bank built out of them.

    The longest slice in the boot, and it is pure composition — the loads, two in-place preshifts,
    four eight-slot banks, two five-call frame spreads, twenty-four table-driven preshifts, one more
    bank, the ship's fourteen frames and the homing shot's. Every leaf is verified in `fileio`,
    `sprite` and `util`; what this holds is the ORDER and the addresses, over 100 KB of image.

    THE TWO FRAME SPREADS ARE ORDER-DEPENDENT and that is what makes this more than a checklist: each
    one's fifth copy writes over its second copy's SOURCE, so a candidate that ran them in any other
    order gets four of the ten wrong. `test_the_frame_spreads_overlap_as_the_strides_say` states the
    overlap from the strides rather than leaving it to the diff to discover.
    """
    pokes = abi.seed_spans(0x101ba, (SHIP_PRESHIFT_SPAN, BULLET_BANK_SPAN),
                           guard=abi.GUARD_BYTES)
    pokes.update(_stage(GAMEPLAY_FILES))
    _slice_case(ENTRY_BOOT_LOAD_GAMEPLAY_ASSETS, STOP_BOOT_LOAD_GAMEPLAY_ASSETS, pokes,
                lambda lib, buf: lib.g_boot_load_gameplay_assets(buf), "gameplay assets",
                max_insns=GAMEPLAY_MAX_INSNS)


BOOT_SPREAD_FRAMES = 5
BOOT_BANK_FRAMES = 4
BOOT_EXPLOSION_SMALL_TOP = 0x61e7e
BOOT_EXPLOSION_SMALL_BANK_TOP = 0x627de
BOOT_EXPLOSION_SMALL_FRAME_BYTES = 0xa0
BOOT_EXPLOSION_LARGE_TOP = 0x5d5be
BOOT_EXPLOSION_LARGE_BANK_TOP = 0x5e87e
BOOT_EXPLOSION_LARGE_FRAME_BYTES = 0x140


@pytest.mark.parametrize("top,bank_top,frame_bytes",
                         ((BOOT_EXPLOSION_SMALL_TOP, BOOT_EXPLOSION_SMALL_BANK_TOP,
                           BOOT_EXPLOSION_SMALL_FRAME_BYTES),
                          (BOOT_EXPLOSION_LARGE_TOP, BOOT_EXPLOSION_LARGE_BANK_TOP,
                           BOOT_EXPLOSION_LARGE_FRAME_BYTES)))
def test_the_frame_spreads_overlap_as_the_strides_say(top, bank_top, frame_bytes):
    """THE LAST COPY'S DESTINATION IS THE SECOND COPY'S SOURCE, in both spreads.

    `src/init.c` writes each spread as five calls stepping down by one frame and by four, which reads
    as a tidy loop until you notice that the two runs MEET: the destination four banks down is the
    source one frame down. That is not a coincidence to be discovered from a red diff — it is
    arithmetic, it is why the call order is load-bearing, and this is the assertion that says so if
    a future edit ever moves either stride.
    """
    last_destination = bank_top - (BOOT_SPREAD_FRAMES - 1) * frame_bytes * BOOT_BANK_FRAMES
    second_source = top - frame_bytes
    assert last_destination == second_source, (
        f"the spread from {top:#x} no longer meets its own bank run at {second_source:#x}")


# ============================================== boot_install_ikbd_isr @ 0x104c8

# Values none of the four bytes this slice writes can produce, so a candidate that skipped one
# leaves a canary standing. The vector page and the three ACIA globals are all zero in the loaded
# image, which is exactly what makes the seeds necessary.
ISR_INSTALL_CANARY = 0x5a
ISR_INSTALL_CURSOR_CANARY = b"\x5a\xa5\x5a\xa5"


def test_boot_install_ikbd_isr():
    """The keyboard vector, with the handler's three globals cleared around it.

    All four stores are seeded away from their answers first: the packet cursor to a longword the
    slice cannot produce, the countdown and the scancode to 0x5a, and the $118 vector likewise. The
    screen flip at the end publishes a base through the hardware WRITE ledger, so the pointer swap
    and the two shifter stores are both compared.

    Poison, because nothing here is a scheduled byte — the run makes no wait at all.
    """
    pokes = {A_IKBD_PACKET_PTR: ISR_INSTALL_CURSOR_CANARY,
             A_IKBD_PACKET_REMAINING: bytes([ISR_INSTALL_CANARY]),
             A_KEY_SCANCODE: bytes([ISR_INSTALL_CANARY]),
             A_VECTOR_ACIA: ISR_INSTALL_CURSOR_CANARY,
             A_SCREEN_BACK: BOOT_SCREEN_BACK.to_bytes(4, "big"),
             A_SCREEN_FRONT: BOOT_SCREEN_FRONT.to_bytes(4, "big")}
    _slice_case(ENTRY_BOOT_INSTALL_IKBD_ISR, ENTRY_BOOT_FRONT_END_PROLOGUE, pokes,
                lambda lib, buf: lib.g_boot_install_ikbd_isr(buf), "ikbd isr", poison=True)


# ============================================ boot_front_end_prologue @ 0x10500

@pytest.mark.parametrize("initialised", (0, 1, 2, 0x80, 0xff))
def test_boot_front_end_prologue(initialised):
    """`tst.b $1991c` — the session's FIRST pass skips the panel rebuild, every later one does it.

    Five values of the flag, not two: `tst.b` is a test against zero, so 2, 0x80 and 0xff all take
    the rebuild arm and a candidate spelling the gate as `== 1` fails on three of the five. Both arms
    leave through the same address, so the answer is what says which ran.

    The rebuild arm runs `status_panel_build_master` over the real panel graphics and then restarts
    the title tune, so the case reaches the sound driver as well as 8480 bytes of master.
    """
    pokes = _front_end_pokes(seed=0x10500 + initialised,
                             extra={A_GAME_INITIALISED: bytes([initialised])})
    info = _slice_case(ENTRY_BOOT_FRONT_END_PROLOGUE, STOP_BOOT_FRONT_END_PROLOGUE, pokes,
                       lambda lib, buf: lib.g_boot_front_end_prologue(buf),
                       f"initialised={initialised:#x}", max_insns=BOOT_MAX_INSNS)
    assert bool(info["ret"]) == (initialised != 0)


# The three channel codes `voice_for_channel` (src/sound.c) tells apart: 1 and 2 name their own
# voice and EVERY other byte names voice 3.
SOUND_CHANNEL_VOICE1 = 1
SOUND_CHANNEL_VOICE2 = 2


def test_the_boot_sound_channels_are_neither_of_the_two_that_name_a_voice():
    """WHY NO CASE CAN PIN EITHER DERIVED CHANNEL BYTE, said once rather than left as a hole.

    Two call sites in this file hand `sound_start` a D0 nobody chose: the front-end prologue's is
    0xff (a `dbf` counter that fell through inside `status_panel_build_master`) and the section
    tail's is 0x16 (the IKBD command still sitting in the register). `voice_for_channel` maps 1 to
    voice 1, 2 to voice 2 and EVERYTHING ELSE to voice 3 — so both bytes pick voice 3, and so would
    any other value outside {1, 2}. A mutation changing either constant is therefore invisible to
    every differential, measured, and this assertion is what says so rather than a case pretending
    otherwise. What the two constants really claim is only that they are neither 1 nor 2.
    """
    for channel in (BOOT_SOUND_CHANNEL_FROM_DBF, SECTION_TAIL_SOUND_CHANNEL_FROM_D0):
        assert channel not in (SOUND_CHANNEL_VOICE1, SOUND_CHANNEL_VOICE2), (
            f"channel {channel:#x} now names a voice of its own, so the two call sites' derived "
            f"bytes have become observable and want a case rather than this assertion")


def test_the_section_tails_sound_channel_is_still_written_as_the_derivation():
    """The C define must still say `IKBD_CMD_INTERROGATE_JOYSTICKS`, not a number.

    A MIRRORS row cannot hold this one: `test_constants.py`'s collector reads integer literals and
    single-bit shifts, and a define whose value is another MACRO is invisible to it. So the pin is
    over the SOURCE, the way that file pins the things it cannot evaluate — and it is what catches a
    rewrite to a bare byte, which the assertion above cannot, because the Python mirror would be
    compared against itself. Measured: without this the rewrite was a mutation nothing caught.

    What it protects is the DERIVATION and not the value. Any byte outside {1, 2} behaves the same
    (the case above says why), so this is tamper-evidence for a fact about where the byte comes from.
    """
    # This file's own directory, not `harness.PRG`'s: the .PRG is reached through a symlink into the
    # shared tree, so its parents are the wrong checkout. `test_constants.py` locates headers the
    # same way, for the same reason.
    source = (pathlib.Path(__file__).resolve().parents[1] / "include" / "init.h").read_text()
    assert re.search(r"^#define\s+SECTION_TAIL_SOUND_CHANNEL_FROM_D0\s+"
                     r"IKBD_CMD_INTERROGATE_JOYSTICKS\s*$", source, re.M), (
        "include/init.h no longer derives the section tail's sound channel from the IKBD command "
        "D0 was left holding, which is the only thing that made it a derivation rather than a number")


def test_the_two_preattract_clears_land_inside_the_player_records():
    """The two `clr.w`s the prologue opens with are at `A_player_records` + 0x0a and + 0x16.

    Stated because `src/init.c` spells them as offsets from the record base rather than as two bare
    addresses, and a reader is owed the check that the arithmetic really names 0x19f0c and 0x19f18.
    What the two words are FOR is not recovered — the boot's own tail overwrites all four bytes
    before anything reads them — and STATUS.md carries that as the residual it is.
    """
    assert A_PLAYER_RECORDS + BOOT_PREATTRACT_CLEAR_A == 0x19f0c
    assert A_PLAYER_RECORDS + BOOT_PREATTRACT_CLEAR_B == 0x19f18


# ======================================= boot_stage_frontend_screens @ 0x10524

def test_boot_stage_frontend_screens():
    """Both buffers wiped, the panel stamped into each, and three strips carved back out.

    THE WIPE READS THE POINTERS AND THE STAMP DOES NOT, which is the one thing a reader would get
    wrong: `movea.l $1797e.l,a0` for the clear, `lea $70300,a0` for the panel. Both reach the same
    memory here — the boot fixed the pointers to those literals long ago — so the case also runs with
    the two pointers SWAPPED, where the two spellings disagree and a candidate that used one for both
    differs on 32000 bytes.
    """
    for back, front in ((BOOT_SCREEN_BACK, BOOT_SCREEN_FRONT),
                        (BOOT_SCREEN_FRONT, BOOT_SCREEN_BACK)):
        # THE MASTER IS SEEDED, and without it half this slice is untestable: the shipped image
        # leaves 0x41eae all zero (STATUS.PI1 is unpacked into it by the slice BEFORE this one),
        # both buffers are cleared to zero here, and stamping zeroes over zeroes differs nowhere.
        # Measured: the mutant that stamped the panel into one buffer only survived until this poke.
        pokes = _front_end_pokes(seed=0x10524 + back,
                                 extra={A_SCREEN_BACK: back.to_bytes(4, "big"),
                                        A_SCREEN_FRONT: front.to_bytes(4, "big"),
                                        A_GAME_INITIALISED: b"\x5a",
                                        **abi.seed_spans(
                                            0x41eae,
                                            ((A_PANEL_MASTER,
                                              A_PANEL_MASTER + PANEL_MASTER_LONGWORDS * 4),))})
        _slice_case(ENTRY_BOOT_STAGE_FRONTEND_SCREENS, ENTRY_BOOT_PROGRAM_TIMER_B, pokes,
                    lambda lib, buf: lib.g_boot_stage_frontend_screens(buf),
                    f"back={back:#x}", max_insns=BOOT_MAX_INSNS)


# ============ boot_program_timer_b @ 0x105c6 / boot_program_raster_timer @ 0x10638

# The two waits' sites — the `tst.b $198ab` each spin re-reads the flag at, which is both the
# schedule's trigger PC and the site the candidate's `sched_wait8` names.
BOOT_VSYNC_WAIT_SITE = 0x1061e
BOOT_VSYNC_WAIT_SITE_RASTER = 0x10648
# A vsync flag value the slice cannot produce, so the store it makes before the wait is visible.
VSYNC_CANARY = 0x5a


def _vsync_release(site, nth):
    """The VBL handler's own `clr.b $198ab`, as the scheduled store it is off target.

    Nothing an off-target run executes clears this byte: the slice sets it to 1 and then spins, and
    the interrupt that would end the spin never fires. So the store is a declared INPUT of the case
    (kit TRAP_MODEL.md, Phase 8) and the harness compares the oracle's arrivals at `site` against the
    candidate's polls there.
    """
    return [{"pc": site, "nth": nth, "addr": A_VSYNC_FLAG, "width": 1, "value": 0}]


@pytest.mark.parametrize("nth", (1, 2, 3))
def test_boot_program_timer_b(nth):
    """The MFP's first programming step, with the frame wait driven at three different lengths.

    Three, not one, because at a single `nth` a port that polled twice per iteration would land on
    the same arrival as a faithful one (kit TRAP_MODEL.md, "the aliasing hole"). `nth = 1` releases
    the wait before its very first read, so the loop runs once; 2 and 3 make it spin.

    NO POISON PASS: the attribution pass is refused over a byte the schedule also stores, because the
    agent's store lands on both sides and overwrites the canary. The flag is seeded to a value
    neither the slice nor the schedule produces instead, so the `move.b #$1` before the wait is still
    an assertion.
    """
    pokes = {A_VSYNC_FLAG: bytes([VSYNC_CANARY]),
             A_VECTOR_VBL: b"\x5a\xa5\x5a\xa5", A_VECTOR_TIMER_B: b"\x5a\xa5\x5a\xa5",
             A_STARFIELD_LAYER2_PHASE: bytes([VSYNC_CANARY, VSYNC_CANARY])}
    diffs, info = differential(ENTRY_BOOT_PROGRAM_TIMER_B, {"_pokes": pokes},
                               lambda lib, buf: lib.g_boot_program_timer_b(buf),
                               stop_pc=STOP_BOOT_PROGRAM_TIMER_B,
                               schedule=_vsync_release(BOOT_VSYNC_WAIT_SITE, nth))
    assert not diffs, f"program timer b nth={nth}\n{report(diffs)}"
    assert (HW_MFP_TIMER_B_DATA, BYTE, MFP_TIMER_B_PERIOD_PLAIN) in info["regs"]["hw_writes"]


@pytest.mark.parametrize("nth", (1, 2, 3))
def test_boot_program_raster_timer(nth):
    """Step two, which REPLACES step one: Timer B started, a frame waited for, and then the raster
    pair installed over the plain one with the other period.

    The two vectors are seeded to values neither pair holds, so "installed the raster handlers" is a
    difference rather than two stores of what was already there. The period is the case's last
    assertion: 0xc8 here against 0xac above, from two slices that are otherwise the same shape.
    """
    pokes = {A_VSYNC_FLAG: bytes([VSYNC_CANARY]),
             A_VECTOR_VBL: b"\x5a\xa5\x5a\xa5", A_VECTOR_TIMER_B: b"\x5a\xa5\x5a\xa5"}
    diffs, info = differential(ENTRY_BOOT_PROGRAM_RASTER_TIMER, {"_pokes": pokes},
                               lambda lib, buf: lib.g_boot_program_raster_timer(buf),
                               stop_pc=STOP_BOOT_PROGRAM_RASTER_TIMER,
                               schedule=_vsync_release(BOOT_VSYNC_WAIT_SITE_RASTER, nth))
    assert not diffs, f"program raster timer nth={nth}\n{report(diffs)}"
    assert (HW_MFP_TIMER_B_DATA, BYTE, MFP_TIMER_B_PERIOD_RASTER) in info["regs"]["hw_writes"]


def test_the_read_back_spins_are_the_gap_between_the_three_mfp_slices():
    """WHY THE TWO SLICES ABOVE STOP WHERE THEY DO, as a check rather than only as a comment.

    Between them sit `cmpi.b #$ac,$fffa21 / bne` and `cmpi.b #$c8,$fffa21 / bne` — ten bytes each,
    reading back a register the run itself wrote two instructions earlier. The kit's seeded read
    model refuses that combination as a STALE seed (its declaration describes the byte the chip held
    on ENTRY), and unmodelled the read answers 0 so the spin never ends. Neither half can serve it,
    so the slices stop on the write and resume after the spin.

    This asserts the two gaps are exactly those twenty bytes and nothing more has slipped between
    them; the argument itself is in STATUS.md and in the kit's "Still unmodeled".
    """
    assert ENTRY_BOOT_PROGRAM_RASTER_TIMER - STOP_BOOT_PROGRAM_TIMER_B == READ_BACK_SPIN_BYTES
    assert ENTRY_BOOT_ENABLE_INTERRUPTS - STOP_BOOT_PROGRAM_RASTER_TIMER == READ_BACK_SPIN_BYTES
    assert (ENTRY_ATTRACT_PROGRAM_RASTERBAR_TIMER - STOP_ATTRACT_PROGRAM_TIMER_B
            == READ_BACK_SPIN_BYTES)
    assert (ENTRY_ATTRACT_BUILD_COLOUR_BARS - STOP_ATTRACT_PROGRAM_RASTERBAR_TIMER
            == READ_BACK_SPIN_BYTES)


READ_BACK_SPIN_BYTES = 10   # `cmpi.b #$xx,$fffa21` (8) + `bne.s` (2)


# ========================================== boot_enable_interrupts @ 0x10676

def test_boot_enable_interrupts():
    """Five hardware stores and NOT ONE IMAGE BYTE, which is why the ledger is the whole assertion.

    Timer B restarted, then Timer B enabled and unmasked in the MFP's A registers and the keyboard
    ACIA in its B ones. Before the write ledger this slice would have been unverifiable in principle:
    a candidate with an empty body has exactly the same memory. The list below is compared in ORDER,
    so aiming one store at its neighbour register — IERA for IMRA — is a red.

    The `bset`s carry `mfp_ack_timer_b`'s residual: their read half answers a fabricated 0, so what
    lands is the bare bit rather than the bit on top of what the MFP held. include/irq.h says so.
    """
    diffs, info = differential(ENTRY_BOOT_ENABLE_INTERRUPTS, {},
                               lambda lib, buf: lib.g_boot_enable_interrupts(buf),
                               stop_pc=ENTRY_BOOT_NEW_GAME_RECORDS)
    assert not diffs, f"enable interrupts\n{report(diffs)}"
    assert info["regs"]["hw_writes"] == [
        (HW_MFP_TIMER_B_CONTROL, BYTE, MFP_TIMER_B_EVENT_COUNT),
        (HW_MFP_IERA, BYTE, MFP_IER_TIMER_B),
        (HW_MFP_IMRA, BYTE, MFP_IER_TIMER_B),
        (HW_MFP_IERB, BYTE, 1 << MFP_ACIA_CHANNEL_BIT),
        (HW_MFP_IMRB, BYTE, 1 << MFP_ACIA_CHANNEL_BIT)]


# ========================================== boot_new_game_records @ 0x10792

RECORD_CANARY = 0x5a


@pytest.mark.parametrize("players", (0, 1, 2, 0xff))
def test_boot_new_game_records(players):
    """Two fresh records, one of them killed off when the menu chose a single player.

    Four player counts, because the cut is `cmpi.b #$1` and only ONE of them takes it — 0, 2 and 0xff
    all leave player 2 with three lives, and a candidate spelling the gate as "not two" fails on
    0 and 0xff. Every byte both records occupy is seeded to a canary first, plus a guard record
    past the second, so a build one field long differs.
    """
    span = 2 * PLAYER_RECORD_BYTES + PLAYER_RECORD_BYTES        # ...and one record of guard
    pokes = {A_PLAYER_RECORDS: bytes([RECORD_CANARY]) * span,
             A_PLAYER_COUNT: bytes([players]),
             A_CURRENT_PLAYER_INDEX: bytes([RECORD_CANARY]),
             A_PLAYER_SCORE_BCD: bytes([RECORD_CANARY]) * 4,
             A_LIVES: bytes([RECORD_CANARY]),
             A_LEVEL_SECTION: bytes([RECORD_CANARY]),
             A_POWERUP_CURSOR: bytes([RECORD_CANARY]),
             A_WEAPON_POWER_LEVEL: bytes([RECORD_CANARY, RECORD_CANARY])}   # ...and the speed byte
    _slice_case(ENTRY_BOOT_NEW_GAME_RECORDS, ENTRY_SECTION_ADVANCE, pokes,
                lambda lib, buf: lib.g_boot_new_game_records(buf), f"players={players:#x}",
                poison=True)


def test_the_first_records_section_byte_is_what_starts_the_game_at_section_zero():
    """0xff, and it is `section_advance`'s input two instructions later.

    The two records differ in exactly one field and this is it: player 1's section byte is 0xff and
    player 2's is 0. `section_advance` increments BEFORE it compares, so the copied 0xff becomes
    section 0 — the case `test_section_advance[0xff]` above already drives — and the game starts at
    the first section without the boot writing a 0 the reload gate could read as "already loaded".
    """
    assert PLAYER_RECORD_START_SECTION == 0xff
    assert (PLAYER_RECORD_START_SECTION + 1) & 0xff == 0


# ============================================== section_start_tail @ 0x10d96

SECTION_TAIL_FIRE_WAIT_SITE = 0x10f2a   # the `tst.b $19681` the fire wait re-reads the byte at
SECTION_TAIL_MAX_INSNS = 4_000_000
JOYSTICK_FIRE = 0x80                    # bit 7 of the stick's state byte
TAIL_CANARY = 0x5a


def _fire_release(nth):
    """The joystick reply's fire bit, as the scheduled store it is off target.

    `ikbd_acia_isr` is what writes 0x19681, from a packet the keyboard controller sends after the
    0x16 the loop keeps asking with — and no off-target run executes that handler. So the byte is a
    declared input and the harness compares the oracle's arrivals at the `tst.b` against this side's
    `sched_poll8` calls there (kit TRAP_MODEL.md, Phase 8).
    """
    return [{"pc": SECTION_TAIL_FIRE_WAIT_SITE, "nth": nth, "addr": A_JOYSTICK_STATE,
             "width": 1, "value": JOYSTICK_FIRE}]


def _tail_pokes(section, cursor, seed):
    """The tail's whole input set: a map cursor, a section, and every shelf byte seeded off."""
    shelf = (A_SLOT_DIR_FLAGS, A_ACTIVE_BULLETS, A_MOTHERSHIP_WAVE_CLEAR_COUNT,
             A_POWERUP_FLASH_CURSOR, A_SECTION_END_DELAY_COUNTER, A_SHIELD_LEVEL,
             A_SELECTED_WEAPON, A_ACTIVE_COUNT_TYPE32, A_ACTIVE_COUNT_BOMBS,
             A_ACTIVE_COUNT_SEEKERS, A_MISSILE_LOCK_A, A_MISSILE_LOCK_B,
             A_SEEKER_LOCK_TARGET_INDEX, A_ENEMY_SEEKER_COOLDOWN, A_GROUND_SPAWN_RND_PARAM,
             A_BOSS_SEQUENCE_ACTIVE, A_MOTHERSHIP_OFFSCREEN, A_POWER_GAUGE_DISPLAY,
             A_PANEL_REDRAW_MASK, A_POWERUP_ACTIVE_SLOT, A_SCROLL_PREFILL_HIDE_SCREEN,
             A_SQUADRON_SPAWN_ENABLED)
    extra = {address: bytes([TAIL_CANARY]) for address in shelf}
    extra[A_SLOT_DIR_FLAGS] = bytes([TAIL_CANARY]) * (SLOT_DIR_FLAGS_BYTES + 1)  # +1: a guard byte
    extra.update({
        A_LEVEL_SECTION: bytes([section]),
        A_MAP_PTR: cursor.to_bytes(4, "big"),
        A_GROUND_SCRIPT_CURSOR: b"\x5a\xa5\x5a\xa5",
        A_WAVE_SCRIPT_CURSOR: b"\x5a\xa5\x5a\xa5",
        A_MOTHERSHIP_PHASE_TIMER: b"\x5a\xa5\x5a\xa5",
        A_SHIELD_DECAY_TIMER: b"\x5a\xa5\x5a\xa5",   # ...and A_weapon_decay_timer beside it
        A_SPEED_DECAY_TIMER: b"\x5a\xa5",
        A_PANEL_LOGO_COUNTDOWN: b"\x5a\xa5",
        A_JOYSTICK_STATE: bytes([TAIL_CANARY]),
        # THE SHIP AND ITS SHADOW ARE SEEDED DEAD, and without that half the pair is untestable:
        # the tail brings both back to life, and in the loaded image the two alive bytes are
        # already what it writes — so deleting either store was a mutation that SURVIVED until this
        # poke. `A_player_record` is the ship and the record ENTITY_STRIDE after it is its shadow.
        A_PLAYER_RECORD + ENTITY_ALIVE: bytes([TAIL_CANARY]),
        A_PLAYER_RECORD + ENTITY_STRIDE + ENTITY_ALIVE: bytes([TAIL_CANARY]),
        # The palette copy's two ends: a source unlike anything the shifter shadow holds, and a
        # destination that is neither, so a candidate that skipped the copy differs.
        A_PALETTE_NEXT: bytes(range(0x20, 0x40)),
        A_MENU_PALETTE: bytes([TAIL_CANARY]) * SECTION_PALETTE_BYTES,
    })
    return _front_end_pokes(seed, extra)


# Four map cursors: the level's own first column (what `section_advance` leaves), and three further
# in. The scans walk forward until an entry's offset passes the cursor, so a cursor deep in the level
# walks past more entries — and the wave script's payload opcodes act on every one it passes.
TAIL_CURSORS = (A_MAP_UNPACKED, A_MAP_UNPACKED + 0x400, A_MAP_UNPACKED + 0x1800,
                A_MAP_UNPACKED + 0x3000)


@pytest.mark.parametrize("cursor", TAIL_CURSORS)
@pytest.mark.parametrize("section", (0, 1, 7, 0x0f))
def test_section_start_tail(section, cursor):
    """0x10d96 to 0x10f4e, over four sections and four map cursors.

    THE TWO SCRIPT SCANS TAKE TWO DIFFERENT INDICES and that is what these sixteen cases hold: the
    ground script's table is indexed by the section's PALETTE byte and the wave script's by the
    section number, so a candidate using one index for both lands on the wrong pointer for every
    section whose two differ. Both published cursors are seeded to a longword neither scan produces.

    The wave scan also ACTS as it walks: 0x0c and 0x0d in an entry's payload turn squadron spawning
    on and off, so the flag ends as the last such entry before the restart point left it — which the
    four cursors drive, since each walks past a different run of entries.

    Then the per-life shelf, every byte of it seeded to a value the tail does not write, the panel
    repainted, and the fire wait. NO POISON PASS: the attribution pass is refused over a byte the
    schedule stores, and `hud`'s two routines cannot take one anyway.
    """
    diffs, _ = differential(ENTRY_SECTION_START_TAIL,
                            {"_pokes": _tail_pokes(section, cursor, seed=section * 4 + 1)},
                            lambda lib, buf: lib.g_section_start_tail(buf),
                            stop_pc=STOP_SECTION_START_TAIL, max_insns=SECTION_TAIL_MAX_INSNS,
                            schedule=_fire_release(nth=1))
    assert not diffs, f"section tail section={section} cursor={cursor:#x}\n{report(diffs)}"


@pytest.mark.parametrize("nth", (1, 2, 3))
def test_the_section_tail_fire_wait_runs_the_players_own_number_of_frames(nth):
    """The wait driven at three lengths, and the generator is what makes the count visible.

    `rand16` runs once per pass BEFORE the interrogate, so a port that spun a different number of
    times leaves a different generator state — a difference in the image, on top of the poll count
    the harness already compares site by site. Three `nth` values because at a single one a port
    polling twice per iteration lands on the same arrival as a faithful one (kit TRAP_MODEL.md,
    "the aliasing hole").
    """
    diffs, _ = differential(ENTRY_SECTION_START_TAIL,
                            {"_pokes": _tail_pokes(0, A_MAP_UNPACKED, seed=0x10f2a + nth)},
                            lambda lib, buf: lib.g_section_start_tail(buf),
                            stop_pc=STOP_SECTION_START_TAIL, max_insns=SECTION_TAIL_MAX_INSNS,
                            schedule=_fire_release(nth))
    assert not diffs, f"fire wait nth={nth}\n{report(diffs)}"


def _wave_script_entry_offsets(section):
    """The word offsets of the section's own wave-script entries, read out of the image."""
    script = int.from_bytes(bytes(harness.BASE_IMAGE[
        A_EVENT_SCRIPT_B_TABLE + section * SCRIPT_TABLE_ENTRY_BYTES:][:4]), "big")
    return [int.from_bytes(bytes(harness.BASE_IMAGE[script + n * SCRIPT_ENTRY_BYTES:][:2]), "big")
            for n in range(8)]


def _cursor_one_column_before(section):
    """A map cursor exactly one COLUMN short of a real entry in this section's wave script.

    That is the only place the `add.l #$24,d7` before the scans can be observed: with the bias the
    entry counts as behind the cursor and is walked past, without it the scan stops one entry
    earlier. Any other cursor gives both readings the same answer — measured, as a surviving mutant
    over the four ordinary cursors this battery drives.
    """
    for offset in _wave_script_entry_offsets(section):
        if offset >= MAP_COLUMN_BYTES and offset != 0xffff:
            return A_MAP_UNPACKED + offset - MAP_COLUMN_BYTES
    return None


@pytest.mark.parametrize("section", (0, 1, 7, 0x0f))
def test_the_script_scans_compare_one_column_ahead(section):
    """`add.l #$24,d7` — the scans compare against the cursor ONE COLUMN ON, not against the cursor.

    Driven at the one cursor where the bias changes the answer: a column short of a real entry, so
    the biased comparison walks past it and the unbiased one stops. The wave script's payload acts as
    it walks, so the extra entry can also move `A_squadron_spawn_enabled` — which is a second way the
    same difference shows.
    """
    cursor = _cursor_one_column_before(section)
    assert cursor is not None, f"section {section}'s wave script has no entry a column past its base"
    diffs, _ = differential(ENTRY_SECTION_START_TAIL,
                            {"_pokes": _tail_pokes(section, cursor, seed=0x10dbe + section)},
                            lambda lib, buf: lib.g_section_start_tail(buf),
                            stop_pc=STOP_SECTION_START_TAIL, max_insns=SECTION_TAIL_MAX_INSNS,
                            schedule=_fire_release(nth=1))
    assert not diffs, f"one-column bias section={section}\n{report(diffs)}"


def test_the_two_script_tables_really_take_two_different_indices():
    """At least one shipped section's palette index differs from its section number.

    Without that, the sixteen cases above would drive both scans through the same pointer on every
    section and the mutation that swaps the two indices would survive — measured, and this is the
    assertion that says the shipped tables do separate them.
    """
    differing = [s for s in range(SECTION_COUNT)
                 if _table_byte(A_SECTION_PALETTE_INDEX_TABLE, s) != s]
    assert differing, ("every section's palette index equals its number, so no case here can tell "
                       "the ground script's table index from the wave script's")


# ========================================= title_attract_loop @ 0x12ac2, in four slices

ATTRACT_VSYNC_WAIT_SITE_SETUP = 0x12afa
ATTRACT_VSYNC_WAIT_SITE_ARMED = 0x12b24
ATTRACT_VSYNC_WAIT_SITE_FRAME = 0x12bbc
ATTRACT_KEY_1_WAIT_SITE = 0x12c36
ATTRACT_KEY_2_WAIT_SITE = 0x12c42
ATTRACT_FIRE_WAIT_SITE = 0x12c5e
ATTRACT_WAIT_SITES = (ATTRACT_VSYNC_WAIT_SITE_FRAME, ATTRACT_KEY_1_WAIT_SITE,
                      ATTRACT_KEY_2_WAIT_SITE, ATTRACT_FIRE_WAIT_SITE)
ATTRACT_MAX_INSNS = 8_000_000


@pytest.mark.parametrize("nth", (1, 2, 3))
def test_attract_program_timer_b(nth):
    """0x12ac2 to 0x12b0a — the in-game handler pair back on their vectors and Timer B stopped.

    The same shape as the boot's own two MFP slices and the same stopping point: the slice ends on
    `move.b #$0,$fffa21` and the read-back spin below it is the gap. Its period is 0, which is what
    makes it distinguishable from the 0x02 the next slice writes.
    """
    pokes = {A_VSYNC_FLAG: bytes([VSYNC_CANARY]),
             A_VECTOR_VBL: b"\x5a\xa5\x5a\xa5", A_VECTOR_TIMER_B: b"\x5a\xa5\x5a\xa5"}
    diffs, info = differential(ENTRY_ATTRACT_PROGRAM_TIMER_B, {"_pokes": pokes},
                               lambda lib, buf: lib.g_attract_program_timer_b(buf),
                               stop_pc=STOP_ATTRACT_PROGRAM_TIMER_B,
                               schedule=_vsync_release(ATTRACT_VSYNC_WAIT_SITE_SETUP, nth))
    assert not diffs, f"attract timer b nth={nth}\n{report(diffs)}"
    assert (HW_MFP_TIMER_B_DATA, BYTE, MFP_TIMER_B_PERIOD_ATTRACT_SETUP) in info["regs"]["hw_writes"]


@pytest.mark.parametrize("nth", (1, 2, 3))
def test_attract_program_rasterbar_timer(nth):
    """0x12b14 to 0x12b48 — attract mode's OWN handler pair, and the period the bars run at.

    The two vectors are seeded to values neither pair holds, so installing 0x12c9e and 0x12cc0 over
    the in-game pair the slice above put there is a difference in both longwords.
    """
    pokes = {A_VSYNC_FLAG: bytes([VSYNC_CANARY]),
             A_VECTOR_VBL: b"\x5a\xa5\x5a\xa5", A_VECTOR_TIMER_B: b"\x5a\xa5\x5a\xa5"}
    diffs, info = differential(ENTRY_ATTRACT_PROGRAM_RASTERBAR_TIMER, {"_pokes": pokes},
                               lambda lib, buf: lib.g_attract_program_rasterbar_timer(buf),
                               stop_pc=STOP_ATTRACT_PROGRAM_RASTERBAR_TIMER,
                               schedule=_vsync_release(ATTRACT_VSYNC_WAIT_SITE_ARMED, nth))
    assert not diffs, f"attract rasterbar timer nth={nth}\n{report(diffs)}"
    assert (HW_MFP_TIMER_B_DATA, BYTE, MFP_TIMER_B_PERIOD_ATTRACT_BARS) in info["regs"]["hw_writes"]


# The bar list is built in the backdrop's page 0, so the whole span it can reach is seeded — a
# candidate that emitted one pair too many or started the hue ramp elsewhere leaves noise standing.
ATTRACT_BAR_LIST_BYTES = ATTRACT_BAR_LIST_LONGS * 4


def _attract_pokes(seed, extra=None):
    """The front end's graphics plus the two bar-list buffers, both seeded with noise."""
    spans = [(A_BACKDROP_PAGE0, A_BACKDROP_PAGE0 + ATTRACT_BAR_LIST_BYTES),
             (A_ATTRACT_RASTER_LIST, A_ATTRACT_RASTER_LIST + ATTRACT_BAR_LIST_BYTES)]
    pokes = abi.seed_spans(seed, spans, guard=abi.GUARD_BYTES)
    pokes.update({A_ATTRACT_BAR_HUE: b"\x5a\xa5", A_ATTRACT_PAGE_TOGGLE: bytes([TAIL_CANARY])})
    pokes.update(extra or {})
    return _front_end_pokes(seed, pokes)


def _attract_loop_pokes(seed, overrides=None):
    """`_attract_pokes` plus every byte the LOOP itself reads, each seeded off its own answers.

    One block rather than one per case: the three loop batteries below differ in two values at most,
    and pasting six keys into each of them is how a seventh byte gets added to two sites out of
    three — where the case that missed it goes on passing with nothing seeded.
    """
    block = {A_ATTRACT_PAGE_TIMER: (ATTRACT_PAGE_FRAMES).to_bytes(2, "big"),
             A_ATTRACT_BAR_SCROLL_TIMER: bytes([ATTRACT_BAR_SCROLL_PERIOD]),
             A_KEY_SCANCODE: b"\x00",
             A_JOYSTICK_STATE: b"\x00",
             A_VSYNC_FLAG: bytes([VSYNC_CANARY]),
             A_PLAYER_COUNT: bytes([TAIL_CANARY])}
    block.update(overrides or {})
    return _attract_pokes(seed, extra=block)


def test_attract_build_colour_bars():
    """0x12b52 to 0x12bb4 — the bar list built out of the pattern the .PRG ships.

    The pattern is the game's own seven groups, read where it lies; what the case seeds is the two
    buffers the build writes into, plus a hue the ramp cannot leave behind. THE RAMP CARRIES ACROSS
    THE GROUPS — `d3` is cleared once, before the outer loop, not per group — so a candidate that
    restarted it each time differs on every bar after the first group, and the hue it parks for the
    scroll to continue from would be wrong too.

    NO POISON PASS, and it is not for the schedule's reason — this slice makes no wait at all. It is
    `title_screen_draw`'s, which test_hud.py already records: the routine ends up reading the draw
    buffer POINTER it was given, and an attribution pass that inverts that longword sends the blit
    off the image. Measured here as a bus error before the pass was dropped. What holds the slice
    instead is that every byte it writes is seeded to a value it cannot produce.
    """
    _slice_case(ENTRY_ATTRACT_BUILD_COLOUR_BARS, STOP_ATTRACT_BUILD_COLOUR_BARS,
                _attract_pokes(seed=0x12b52),
                lambda lib, buf: lib.g_attract_build_colour_bars(buf), "colour bars",
                max_insns=ATTRACT_MAX_INSNS)


def test_the_bar_pattern_emits_more_pairs_than_the_scroll_moves():
    """The list the build fills is longer than the sixteen pairs the scroll walks.

    Read off the shipped pattern rather than assumed, because the two counts come from different
    places — the pattern's own seven groups and a `move.w #$f,d0` — and the scroll only makes sense
    while it is the shorter of the two. It also pins the copy: the 0x29 longwords carried to the
    handler's list every frame must cover every pair the build emitted.
    """
    pairs = 0
    for group in range(ATTRACT_BAR_GROUPS):
        entry = A_ATTRACT_BAR_PATTERN + group * 2 * 2
        pairs += int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + 2]), "big") + 1
    assert pairs > ATTRACT_BAR_SCROLL_PAIRS, (
        f"the pattern emits {pairs} pairs, which the {ATTRACT_BAR_SCROLL_PAIRS}-pair scroll would "
        f"run off the end of")
    assert pairs * ATTRACT_BAR_PAIR_BYTES <= ATTRACT_BAR_LIST_BYTES, (
        f"the pattern emits {pairs} pairs but only {ATTRACT_BAR_LIST_BYTES} bytes are copied to the "
        f"handler's list each frame")


def _attract_exit(kind, nth):
    """The schedule for one of the loop's three exits, plus a vsync release per iteration.

    Each iteration re-arms the frame flag and waits, so iteration k needs its own release at the
    frame site's kth arrival; the exit's own store lands on the pass that is to be the last.
    """
    schedule = [{"pc": ATTRACT_VSYNC_WAIT_SITE_FRAME, "nth": frame, "addr": A_VSYNC_FLAG,
                 "width": 1, "value": 0} for frame in range(1, nth + 1)]
    exits = {
        "key 1": (ATTRACT_KEY_1_WAIT_SITE, A_KEY_SCANCODE, KEY_SCANCODE_1),
        "key 2": (ATTRACT_KEY_2_WAIT_SITE, A_KEY_SCANCODE, KEY_SCANCODE_2),
        "fire":  (ATTRACT_FIRE_WAIT_SITE, A_JOYSTICK_STATE, JOYSTICK_FIRE),
    }
    site, address, value = exits[kind]
    return schedule + [{"pc": site, "nth": nth, "addr": address, "width": 1, "value": value}]


ATTRACT_EXIT_PLAYERS = {"key 1": ATTRACT_PLAYERS_ONE, "key 2": ATTRACT_PLAYERS_DEFAULT,
                        "fire": ATTRACT_PLAYERS_ONE}


@pytest.mark.parametrize("nth", (1, 2, 3))
@pytest.mark.parametrize("kind", ("key 1", "key 2", "fire"))
def test_attract_wait_for_start(kind, nth):
    """THE LOOP, over its three exits and three lengths.

    Four wait sites, which is the kit's whole allowance and exactly what the loop has: the frame
    flag, the key byte at BOTH of its compares — two reads at two addresses, so two sites — and the
    joystick. Every one is a byte only an interrupt writes, so each is a declared store and the
    harness compares this side's polls against the oracle's arrivals site by site rather than as one
    total that two waits could make up between them.

    The three exits differ in what they leave in `A_player_count`, and the assertion below is what
    holds that: key '2' leaves the two the loop writes on every pass, and the other two cut it to
    one. The count is written INSIDE the loop, so a candidate that only wrote it on the way out
    would still agree — which is why the page timer is seeded high here and driven low separately.

    NO POISON PASS — refused over the four scheduled bytes.
    """
    pokes = _attract_loop_pokes(seed=0x12bb4 + nth)
    diffs, _ = differential(ENTRY_ATTRACT_WAIT_FOR_START, {"_pokes": pokes},
                            lambda lib, buf: lib.g_attract_wait_for_start(buf),
                            max_insns=ATTRACT_MAX_INSNS, schedule=_attract_exit(kind, nth),
                            wait_sites=list(ATTRACT_WAIT_SITES))
    assert not diffs, f"attract loop {kind} nth={nth}\n{report(diffs)}"


@pytest.mark.parametrize("toggle", (0, 1))
def test_the_attract_page_swap_alternates_the_two_screens(toggle):
    """The page timer driven to zero, which is the arm that redraws the screen behind the bars.

    `eori.b #$1` on the toggle, so entering at 0 draws the ROLE OF HONOUR and entering at 1 draws the
    TITLE — the flip happens BEFORE the branch, which is what a candidate reading the byte first
    would get backwards on both cases. The swap also re-enters the loop BELOW the frame wait, so the
    frame it happens on makes no vsync poll of its own; that is why this case's schedule releases one
    fewer frame than its two iterations would otherwise need.
    """
    pokes = _attract_loop_pokes(seed=0x12c76 + toggle, overrides={
        A_ATTRACT_PAGE_TIMER: (1).to_bytes(2, "big"),      # ...so it expires on this very frame
        A_ATTRACT_PAGE_TOGGLE: bytes([toggle])})
    diffs, _ = differential(ENTRY_ATTRACT_WAIT_FOR_START, {"_pokes": pokes},
                            lambda lib, buf: lib.g_attract_wait_for_start(buf),
                            max_insns=ATTRACT_MAX_INSNS, schedule=_attract_exit("fire", nth=1),
                            wait_sites=list(ATTRACT_WAIT_SITES))
    assert not diffs, f"attract page swap toggle={toggle}\n{report(diffs)}"


@pytest.mark.parametrize("timer", (1, 2, 3, 0xff))
def test_the_bar_scroll_runs_on_its_own_countdown(timer):
    """`subi.b #$1,$198c6 / bne` — only a timer of 1 scrolls the colours this frame.

    Four values including 0xff, which steps down like any other and does NOT scroll, so a candidate
    testing the byte before the decrement (or spelling the gate as `<= 0`) differs on three of the
    four. The hue the scroll writes at the top comes from `A_attract_bar_hue`, seeded to a value the
    ramp cannot produce, so "scrolled" and "left alone" are both visible in the list.
    """
    pokes = _attract_loop_pokes(
        seed=0x198c6 + timer, overrides={A_ATTRACT_BAR_SCROLL_TIMER: bytes([timer])})
    diffs, _ = differential(ENTRY_ATTRACT_WAIT_FOR_START, {"_pokes": pokes},
                            lambda lib, buf: lib.g_attract_wait_for_start(buf),
                            max_insns=ATTRACT_MAX_INSNS, schedule=_attract_exit("fire", nth=1),
                            wait_sites=list(ATTRACT_WAIT_SITES))
    assert not diffs, f"bar scroll timer={timer}\n{report(diffs)}"


def test_the_attract_loop_leaves_through_the_boots_own_continuation():
    """`title_attract_loop`'s `rts` lands at 0x10524, which is `boot_stage_frontend_screens`.

    The loop is `bsr`ed from 0x10520, so the four bytes between that call and this battery's next
    slice are the whole of what joins the front end to the rest of the boot. Cheap, and it is what
    says the two chains really do meet where STATUS.md claims.
    """
    assert STOP_BOOT_FRONT_END_PROLOGUE + BSR_W_BYTES == ENTRY_BOOT_STAGE_FRONTEND_SCREENS


BSR_W_BYTES = 4   # `bsr.w` is one opcode word and one displacement word


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_VECTOR_VBL", "include/init.h", "A_vector_vbl"),
    ("A_VECTOR_TIMER_B", "include/init.h", "A_vector_timer_b"),
    ("A_VBL_ISR", "include/init.h", "A_vbl_isr"),
    ("A_TIMER_B_ISR", "include/init.h", "A_timer_b_isr"),
    ("A_SAVED_TOS_VBL_VECTOR", "include/init.h", "A_saved_tos_vbl_vector"),
    ("SHIFTER_MODE_RESOLUTION_MASK", "include/init.h", "SHIFTER_MODE_RESOLUTION_MASK"),
    ("A_LEVEL_SECTION", "include/init.h", "A_level_section"),
    ("A_LEVEL_SECTION_LOADED", "include/init.h", "A_level_section_loaded"),
    ("A_SHOW_PREPARE_FOR_COMBAT", "include/hud.h", "A_show_prepare_for_combat"),
    ("A_ASTEROID_SECTION_FLAG", "include/init.h", "A_asteroid_section_flag"),
    ("A_MOTHERSHIP_INDEX", "include/init.h", "A_mothership_index"),
    ("A_SECTION_GROUND_TARGET_FLAG", "include/init.h", "A_section_ground_target_flag"),
    ("A_PALETTE_ASTEROID", "include/init.h", "A_palette_asteroid"),
    ("A_KEY_SCANCODE", "include/irq.h", "A_key_scancode"),
    ("A_MOTHERSHIP_PENDING", "include/init.h", "A_mothership_pending"),
    ("SECTION_RESTART_SHIP_X", "include/init.h", "SECTION_RESTART_SHIP_X"),
    ("SECTION_RESTART_SHADOW_X", "include/init.h", "SECTION_RESTART_SHADOW_X"),
    ("SECTION_RESTART_SHIP_Y", "include/init.h", "SECTION_RESTART_SHIP_Y"),
    ("SECTION_RESTART_SHIP_ROWS", "include/init.h", "SECTION_RESTART_SHIP_ROWS"),
    ("SECTION_RESTART_KILL_SLOTS", "include/init.h", "SECTION_RESTART_KILL_SLOTS"),
    ("SECTION_RESTART_ASTEROID_RECORDS", "include/init.h",
     "SECTION_RESTART_ASTEROID_RECORDS"),
    ("SQUADRON_MARKS", "include/init.h", "SQUADRON_MARKS"),
    ("SECTION_RESTART_LAUNCH_STOCK", "include/init.h", "SECTION_RESTART_LAUNCH_STOCK"),
    ("SHIP_SPRITE_GAP", "include/sprite.h", "SHIP_SPRITE_GAP"),
    ("PLAYER_SHOT_SLOTS", "include/weapon.h", "PLAYER_SHOT_SLOTS"),
    ("A_ENTITY_GUNSIGHT", "include/weapon.h", "A_entity_gunsight"),
    ("A_DEATH_EVENT_FLAGS", "include/weapon.h", "A_death_event_flags"),
    ("A_MISSILE_LAUNCH_COUNTER", "include/weapon.h", "A_missile_launch_counter"),
    ("A_BOMB_LAUNCH_COUNTER", "include/weapon.h", "A_bomb_launch_counter"),
    ("A_ASTEROID_RECORDS", "include/enemy.h", "A_asteroid_records"),
    ("A_SQUADRON_KILL_COUNTERS", "include/enemy.h", "A_squadron_kill_counters"),
    ("A_EXPLOSION_GROUP_ACTIVE_BITS", "include/enemy.h", "A_explosion_group_active_bits"),
    ("A_SCROLL_FROZEN", "include/enemy.h", "A_scroll_frozen"),
    ("A_PLAYER_RECORD", "include/enemy.h", "A_player_record"),
    ("A_MOTHERSHIP_READY", "include/mothership.h", "A_mothership_ready"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_SHIP_RECORD_SHADOW", "include/player.h", "A_ship_record_shadow"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("A_PALETTE_NEXT", "include/init.h", "A_palette_next"),
    ("A_PALETTE_PER_SECTION_TABLE", "include/init.h", "A_palette_per_section_table"),
    ("SECTION_COUNT", "include/init.h", "SECTION_COUNT"),
    ("SECTION_TYPE_ASTEROID", "include/init.h", "SECTION_TYPE_ASTEROID"),
    ("SECTION_PALETTE_BYTES", "include/init.h", "SECTION_PALETTE_BYTES"),
    ("A_ALIEN_VARIANT_TABLE", "include/init.h", "A_alien_variant_table"),
    ("A_ALIEN2_VARIANT_TABLE", "include/init.h", "A_alien2_variant_table"),
    ("A_MOTHERSHIP_VARIANT_TABLE", "include/init.h", "A_mothership_variant_table"),
    ("A_MISSILE_VARIANT_TABLE", "include/init.h", "A_missile_variant_table"),
    ("A_SECTION_TYPE_TABLE", "include/init.h", "A_section_type_table"),
    ("A_ZYN_VARIANT_TABLE", "include/init.h", "A_zyn_variant_table"),
    ("A_SECTION_PALETTE_INDEX_TABLE", "include/init.h", "A_section_palette_index_table"),
    ("A_GROUND_TARGET_BY_PALETTE_TABLE", "include/init.h", "A_ground_target_by_palette_table"),
    ("A_SECTION_RESTART_TABLE", "include/init.h", "A_section_restart_table"),
    ("A_SCROLL_POS", "include/init.h", "A_scroll_pos"),
    ("A_MAP_OFFSET", "include/init.h", "A_map_offset"),
    ("A_MAP_PTR", "include/init.h", "A_map_ptr"),
    ("A_MAP_PAGE", "include/init.h", "A_map_page"),
    ("A_MAP_PAGE_PTR", "include/init.h", "A_map_page_ptr"),
    ("A_MAP_PAGE_TABLE", "include/init.h", "A_map_page_table"),
    ("A_MAP_COLUMN", "include/init.h", "A_map_column"),
    ("MAP_PAGES", "include/init.h", "MAP_PAGES"),
    ("SECTION_PREFILL_COLUMNS", "include/init.h", "SECTION_PREFILL_COLUMNS"),
    ("A_FILENAME_ALIEN_DAT", "include/init.h", "A_filename_alien_dat"),
    ("A_FILENAME_MOTHER_DAT", "include/init.h", "A_filename_mother_dat"),
    ("A_FILENAME_MISSILE_DAT", "include/init.h", "A_filename_missile_dat"),
    ("A_FILENAME_LEV_MAP", "include/init.h", "A_filename_lev_map"),
    ("A_FILENAME_ZYN_DAT", "include/init.h", "A_filename_zyn_dat"),
    ("FILENAME_ALIEN_VARIANT", "include/init.h", "FILENAME_ALIEN_VARIANT"),
    ("FILENAME_MOTHER_VARIANT", "include/init.h", "FILENAME_MOTHER_VARIANT"),
    ("FILENAME_MISSILE_VARIANT", "include/init.h", "FILENAME_MISSILE_VARIANT"),
    ("FILENAME_LEV_VARIANT", "include/init.h", "FILENAME_LEV_VARIANT"),
    ("FILENAME_ZYN_VARIANT", "include/init.h", "FILENAME_ZYN_VARIANT"),
    ("A_TILE_SET_BASE", "include/scroll.h", "A_tile_set_base"),
    ("A_MAP_UNPACKED", "include/scroll.h", "A_map_unpacked"),
    ("MAP_ROWS", "include/scroll.h", "MAP_ROWS"),
    ("MAP_COLUMNS", "include/scroll.h", "MAP_COLUMNS"),
    ("MAP_COLUMN_BYTES", "include/scroll.h", "MAP_COLUMN_BYTES"),
    ("SCROLL_PHASES", "include/scroll.h", "SCROLL_PHASES"),
    ("SCROLL_PHASE_STEP", "include/scroll.h", "SCROLL_PHASE_STEP"),
    ("A_SCROLL_PREFILL_HIDE_SCREEN", "include/scroll.h", "A_scroll_prefill_hide_screen"),
    ("A_SCROLL_COL_WORKSPACE", "include/scroll.h", "A_scroll_col_workspace"),
    ("SCROLL_COLUMN_PASSES", "include/scroll.h", "SCROLL_COLUMN_PASSES"),
    ("SCROLL_COLUMN_CELL_LONGS", "include/scroll.h", "SCROLL_COLUMN_CELL_LONGS"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("PLAYFIELD_BYTES", "include/video.h", "PLAYFIELD_BYTES"),
    ("BOOT_SCREEN_BACK", "src/init.c", "BOOT_SCREEN_BACK"),
    ("BOOT_SCREEN_FRONT", "src/init.c", "BOOT_SCREEN_FRONT"),
    ("BOOT_POWER_GAUGE_DST", "src/init.c", "BOOT_POWER_GAUGE_DST"),
    ("BOOT_SHIP_SOURCE", "src/init.c", "BOOT_SHIP_SOURCE"),
    ("ATTRACT_BAR_COLOUR", "include/init.h", "ATTRACT_BAR_COLOUR"),
    ("ATTRACT_BAR_GROUPS", "include/init.h", "ATTRACT_BAR_GROUPS"),
    ("ATTRACT_BAR_LIST_LONGS", "include/init.h", "ATTRACT_BAR_LIST_LONGS"),
    ("ATTRACT_BAR_PAIR_BYTES", "include/init.h", "ATTRACT_BAR_PAIR_BYTES"),
    ("ATTRACT_BAR_SCROLL_PAIRS", "include/init.h", "ATTRACT_BAR_SCROLL_PAIRS"),
    ("ATTRACT_BAR_SCROLL_PERIOD", "include/init.h", "ATTRACT_BAR_SCROLL_PERIOD"),
    ("ATTRACT_HUE_MASK", "include/init.h", "ATTRACT_HUE_MASK"),
    ("ATTRACT_HUE_STEP", "include/init.h", "ATTRACT_HUE_STEP"),
    ("ATTRACT_PAGE_FRAMES", "include/init.h", "ATTRACT_PAGE_FRAMES"),
    ("ATTRACT_PLAYERS_DEFAULT", "include/init.h", "ATTRACT_PLAYERS_DEFAULT"),
    ("ATTRACT_PLAYERS_ONE", "include/init.h", "ATTRACT_PLAYERS_ONE"),
    ("A_ACTIVE_BULLETS", "include/init.h", "A_active_bullets"),
    ("A_ACTIVE_COUNT_BOMBS", "include/weapon.h", "A_active_count_bombs"),
    ("A_ACTIVE_COUNT_SEEKERS", "include/weapon.h", "A_active_count_seekers"),
    ("A_ACTIVE_COUNT_TYPE32", "include/weapon.h", "A_active_count_type32"),
    ("A_ATTRACT_BAR_HUE", "include/init.h", "A_attract_bar_hue"),
    ("A_ATTRACT_BAR_PATTERN", "include/init.h", "A_attract_bar_pattern"),
    ("A_ATTRACT_BAR_SCROLL_TIMER", "include/init.h", "A_attract_bar_scroll_timer"),
    ("A_ATTRACT_PAGE_TIMER", "include/init.h", "A_attract_page_timer"),
    ("A_ATTRACT_PAGE_TOGGLE", "include/init.h", "A_attract_page_toggle"),
    ("A_ATTRACT_RASTERBAR_ISR", "include/init.h", "A_attract_rasterbar_isr"),
    ("A_ATTRACT_RASTER_LIST", "include/irq.h", "A_attract_raster_list"),
    ("A_ATTRACT_VBL_ISR", "include/init.h", "A_attract_vbl_isr"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
    ("A_BOSS_SEQUENCE_ACTIVE", "include/sprite.h", "A_boss_sequence_active"),
    ("A_CURRENT_PLAYER_INDEX", "include/hud.h", "A_current_player_index"),
    ("A_ENEMY_SEEKER_COOLDOWN", "include/enemy.h", "A_enemy_seeker_cooldown"),
    ("A_EVENT_SCRIPT_A_TABLE", "include/init.h", "A_event_script_a_table"),
    ("A_EVENT_SCRIPT_B_TABLE", "include/init.h", "A_event_script_b_table"),
    ("A_EXPLOSION_LARGE_FRAME_PTRS", "include/init.h", "A_explosion_large_frame_ptrs"),
    ("A_FILENAME_ALSEEK_DAT", "include/init.h", "A_filename_alseek_dat"),
    ("A_FILENAME_ALTEXPL_DAT", "include/init.h", "A_filename_altexpl_dat"),
    ("A_FILENAME_EXTCHARS_DAT", "include/init.h", "A_filename_extchars_dat"),
    ("A_FILENAME_GUNSIGHT_DAT", "include/init.h", "A_filename_gunsight_dat"),
    ("A_FILENAME_HEWLOGO_DAT", "include/init.h", "A_filename_hewlogo_dat"),
    ("A_FILENAME_LIFEGRA_DAT", "include/init.h", "A_filename_lifegra_dat"),
    ("A_FILENAME_NEWBOMB_DAT", "include/init.h", "A_filename_newbomb_dat"),
    ("A_FILENAME_NEWBULS2_DAT", "include/init.h", "A_filename_newbuls2_dat"),
    ("A_FILENAME_SEEKER2_DAT", "include/init.h", "A_filename_seeker2_dat"),
    ("A_FILENAME_SMALLEXP_DAT", "include/init.h", "A_filename_smallexp_dat"),
    ("A_FILENAME_SMLOGOS_DAT", "include/init.h", "A_filename_smlogos_dat"),
    ("A_FILENAME_SSWEAP_DAT", "include/init.h", "A_filename_ssweap_dat"),
    ("A_FILENAME_SWEAP_DAT", "include/init.h", "A_filename_sweap_dat"),
    ("A_FILENAME_ZYNLOGO_DAT", "include/init.h", "A_filename_zynlogo_dat"),
    ("A_GAME_INITIALISED", "include/init.h", "A_game_initialised"),
    ("A_GROUND_SCRIPT_CURSOR", "include/enemy.h", "A_ground_script_cursor"),
    ("A_GROUND_SPAWN_RND_PARAM", "include/enemy.h", "A_ground_spawn_rnd_param"),
    ("A_IKBD_ACIA_ISR", "include/init.h", "A_ikbd_acia_isr"),
    ("A_IKBD_JOYSTICK_STATE", "include/irq.h", "A_ikbd_joystick_state"),
    ("A_IKBD_PACKET_PTR", "include/irq.h", "A_ikbd_packet_ptr"),
    ("A_IKBD_PACKET_REMAINING", "include/irq.h", "A_ikbd_packet_remaining"),
    ("A_JOYSTICK_STATE", "include/irq.h", "A_joystick_state"),
    ("A_LIVES", "include/hud.h", "A_lives"),
    ("A_MENU_PALETTE", "include/irq.h", "A_menu_palette"),
    ("A_MISSILE_LOCK_A", "include/weapon.h", "A_missile_lock_a"),
    ("A_MISSILE_LOCK_B", "include/weapon.h", "A_missile_lock_b"),
    ("A_MOTHERSHIP_OFFSCREEN", "include/mothership.h", "A_mothership_offscreen"),
    ("A_MOTHERSHIP_PHASE_TIMER", "include/mothership.h", "A_mothership_phase_timer"),
    ("A_MOTHERSHIP_WAVE_CLEAR_COUNT", "include/init.h", "A_mothership_wave_clear_count"),
    ("A_PALETTE_FRONTEND", "include/hud.h", "A_palette_frontend"),
    ("A_PANEL_LOGO_COUNTDOWN", "include/init.h", "A_panel_logo_countdown"),
    ("A_PANEL_MASTER", "include/hud.h", "A_panel_master"),
    ("A_PANEL_REDRAW_MASK", "include/hud.h", "A_panel_redraw_mask"),
    ("A_PLAYER_COUNT", "include/init.h", "A_player_count"),
    ("A_PLAYER_RECORDS", "include/init.h", "A_player_records"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("A_POWERUP_ACTIVE_SLOT", "include/hud.h", "A_powerup_active_slot"),
    ("A_POWERUP_CURSOR", "include/hud.h", "A_powerup_cursor"),
    ("A_POWERUP_FLASH_CURSOR", "include/init.h", "A_powerup_flash_cursor"),
    ("A_POWER_GAUGE_DISPLAY", "include/hud.h", "A_power_gauge_display"),
    ("A_SECTION_END_DELAY_COUNTER", "include/init.h", "A_section_end_delay_counter"),
    ("A_SEEKER_LOCK_TARGET_INDEX", "include/weapon.h", "A_seeker_lock_target_index"),
    ("A_SELECTED_WEAPON", "include/weapon.h", "A_selected_weapon"),
    ("A_SHIELD_DECAY_TIMER", "include/weapon.h", "A_shield_decay_timer"),
    ("A_SHIELD_LEVEL", "include/weapon.h", "A_shield_level"),
    ("A_SHIP_SPEED_LEVEL", "include/player.h", "A_ship_speed_level"),
    ("A_SLOT_DIR_FLAGS", "include/init.h", "A_slot_dir_flags"),
    ("A_SPEED_DECAY_TIMER", "include/weapon.h", "A_speed_decay_timer"),
    ("A_SQUADRON_SPAWN_ENABLED", "include/enemy.h", "A_squadron_spawn_enabled"),
    ("A_STARFIELD_LAYER2_PHASE", "include/init.h", "A_starfield_layer2_phase"),
    ("A_STARFIELD_LAYER3_COUNTDOWN", "include/init.h", "A_starfield_layer3_countdown"),
    ("A_TIMER_B_RASTER_ISR", "include/init.h", "A_timer_b_raster_isr"),
    ("A_VBL_MENU", "include/init.h", "A_vbl_menu"),
    ("A_VECTOR_ACIA", "include/init.h", "A_vector_acia"),
    ("A_VSYNC_FLAG", "include/irq.h", "A_vsync_flag"),
    ("A_WAVE_SCRIPT_CURSOR", "include/enemy.h", "A_wave_script_cursor"),
    ("A_WEAPON_DECAY_TIMER", "include/player.h", "A_weapon_decay_timer"),
    ("A_WEAPON_POWER_LEVEL", "include/player.h", "A_weapon_power_level"),
    ("BOOT_PREATTRACT_CLEAR_A", "include/init.h", "BOOT_PREATTRACT_CLEAR_A"),
    ("BOOT_PREATTRACT_CLEAR_B", "include/init.h", "BOOT_PREATTRACT_CLEAR_B"),
    ("BOOT_SOUND_CHANNEL_FROM_DBF", "include/init.h", "BOOT_SOUND_CHANNEL_FROM_DBF"),
    ("EXPLOSION_FRAME_PTRS", "include/init.h", "EXPLOSION_FRAME_PTRS"),
    ("HW_MFP_IERA", "include/init.h", "HW_MFP_IERA"),
    ("HW_MFP_IERB", "include/init.h", "HW_MFP_IERB"),
    ("HW_MFP_IMRA", "include/init.h", "HW_MFP_IMRA"),
    ("HW_MFP_IMRB", "include/init.h", "HW_MFP_IMRB"),
    ("HW_MFP_TIMER_B_CONTROL", "include/init.h", "HW_MFP_TIMER_B_CONTROL"),
    ("HW_MFP_TIMER_B_DATA", "include/init.h", "HW_MFP_TIMER_B_DATA"),
    ("IKBD_CMD_DISABLE_MOUSE", "include/init.h", "IKBD_CMD_DISABLE_MOUSE"),
    ("IKBD_CMD_INTERROGATE_JOYSTICKS", "include/init.h", "IKBD_CMD_INTERROGATE_JOYSTICKS"),
    ("IKBD_CMD_JOYSTICK_INTERROGATE_MODE", "include/init.h", "IKBD_CMD_JOYSTICK_INTERROGATE_MODE"),
    ("KEY_SCANCODE_1", "include/init.h", "KEY_SCANCODE_1"),
    ("KEY_SCANCODE_2", "include/init.h", "KEY_SCANCODE_2"),
    ("MFP_ACIA_CHANNEL_BIT", "include/irq.h", "MFP_ACIA_CHANNEL_BIT"),
    ("MFP_IER_TIMER_B", "include/init.h", "MFP_IER_TIMER_B"),
    ("MFP_TIMER_B_EVENT_COUNT", "include/init.h", "MFP_TIMER_B_EVENT_COUNT"),
    ("MFP_TIMER_B_PERIOD_ATTRACT_BARS", "include/init.h", "MFP_TIMER_B_PERIOD_ATTRACT_BARS"),
    ("MFP_TIMER_B_PERIOD_ATTRACT_SETUP", "include/init.h", "MFP_TIMER_B_PERIOD_ATTRACT_SETUP"),
    ("MFP_TIMER_B_PERIOD_PLAIN", "include/init.h", "MFP_TIMER_B_PERIOD_PLAIN"),
    ("MFP_TIMER_B_PERIOD_RASTER", "include/init.h", "MFP_TIMER_B_PERIOD_RASTER"),
    ("MFP_TIMER_B_STOPPED", "include/init.h", "MFP_TIMER_B_STOPPED"),
    ("PANEL_MASTER_LONGWORDS", "include/hud.h", "PANEL_MASTER_LONGWORDS"),
    ("PANEL_TOP_OFFSET", "include/hud.h", "PANEL_TOP_OFFSET"),
    ("PLAYER_RECORD_BYTES", "include/init.h", "PLAYER_RECORD_BYTES"),
    ("PLAYER_RECORD_START_LIVES", "include/init.h", "PLAYER_RECORD_START_LIVES"),
    ("PLAYER_RECORD_START_SECTION", "include/init.h", "PLAYER_RECORD_START_SECTION"),
    ("PLAYER_RECORD_START_WEAPON", "include/init.h", "PLAYER_RECORD_START_WEAPON"),
    ("SCRIPT_ENTRY_BYTES", "include/init.h", "SCRIPT_ENTRY_BYTES"),
    ("SCRIPT_ENTRY_PAYLOAD", "include/init.h", "SCRIPT_ENTRY_PAYLOAD"),
    ("SCRIPT_OP_SQUADRON_SPAWN_OFF", "include/init.h", "SCRIPT_OP_SQUADRON_SPAWN_OFF"),
    ("SCRIPT_OP_SQUADRON_SPAWN_ON", "include/init.h", "SCRIPT_OP_SQUADRON_SPAWN_ON"),
    ("SCRIPT_TABLE_ENTRY_BYTES", "include/init.h", "SCRIPT_TABLE_ENTRY_BYTES"),
    ("SECTION_TAIL_END_DELAY", "include/init.h", "SECTION_TAIL_END_DELAY"),
    ("SECTION_TAIL_GRACE_TICKS", "include/init.h", "SECTION_TAIL_GRACE_TICKS"),
    ("SECTION_TAIL_GROUND_RND", "include/init.h", "SECTION_TAIL_GROUND_RND"),
    ("SECTION_TAIL_LOGO_TICKS", "include/init.h", "SECTION_TAIL_LOGO_TICKS"),
    ("SECTION_TAIL_PANEL_MASK", "include/init.h", "SECTION_TAIL_PANEL_MASK"),
    ("SECTION_TAIL_POWERUP_SLOT", "include/init.h", "SECTION_TAIL_POWERUP_SLOT"),
    ("SECTION_TAIL_SECTION_START_SFX", "include/init.h", "SECTION_TAIL_SECTION_START_SFX"),
    ("SECTION_TAIL_WEAPON_SLOTS", "include/init.h", "SECTION_TAIL_WEAPON_SLOTS"),
    ("SLOT_DIR_FLAGS_BYTES", "include/init.h", "SLOT_DIR_FLAGS_BYTES"),
    ("SOUND_CHANNEL_VOICE1", "include/sound.h", "SOUND_CHANNEL_VOICE1"),
    ("SOUND_CHANNEL_VOICE2", "include/sound.h", "SOUND_CHANNEL_VOICE2"),
    ("STARFIELD_LAYER3_PERIOD", "include/init.h", "STARFIELD_LAYER3_PERIOD"),
)
# Every entry here is a MID-ROUTINE address except the first — `_start` is the only one of the seven
# ../../names.txt gives an `fn` line — so the prologue is the ten bytes the slice's own first
# instructions occupy rather than a function's opening. That is what makes the pin worth having: a
# slice boundary mistyped by two bytes would enter mid-instruction and the oracle would decode
# rubbish, and this is the check that says which bytes each entry stands on.
ENTRY_PROLOGUES = {
    "ENTRY_BOOT_ENTER_SUPERVISOR": "42a73f3c00204e41dffc",
    "ENTRY_BOOT_SAVE_VBL_VECTOR": "23f900000070000195d0",
    "ENTRY_BOOT_LOAD_TITLE_ASSETS": "23fc000703000001797e",
    "ENTRY_SECTION_ADVANCE": "23fc000478ae00018242",
    "ENTRY_SECTION_RELOAD_NEEDED": "103900019913b0390001",
    "ENTRY_SECTION_LOAD_ASSETS": "103900019895488041f9",
    "ENTRY_SECTION_RELOAD_INTRO_SCREENS": "61002bca61002d5c103900019895",
    "ENTRY_SECTION_RESTART_PROLOGUE": "13fc000100019aac610028ae",
    "ENTRY_SECTION_START_PREFILL": "2a3900018242babc0004",
    "ENTRY_ATTRACT_BUILD_COLOUR_BARS": "13fc000800fffa1b13fc",
    "ENTRY_ATTRACT_PROGRAM_RASTERBAR_TIMER": "13fc000800fffa1b13fc",
    "ENTRY_ATTRACT_PROGRAM_TIMER_B": "423900fffa0746fc2700",
    "ENTRY_ATTRACT_WAIT_FOR_START": "13fc0001000198ab4a39",
    "ENTRY_BOOT_CONFIGURE_IKBD": "103c001261004422103c",
    "ENTRY_BOOT_ENABLE_INTERRUPTS": "13fc000800fffa1b13fc",
    "ENTRY_BOOT_FRONT_END_PROLOGUE": "427900019f0c42790001",
    "ENTRY_BOOT_INSTALL_IKBD_ISR": "46fc270023fc00019680",
    "ENTRY_BOOT_LOAD_GAMEPLAY_ASSETS": "41f90001971a43f90006",
    "ENTRY_BOOT_NEW_GAME_RECORDS": "41f900019f02429810fc",
    "ENTRY_BOOT_PROGRAM_RASTER_TIMER": "13fc000800fffa1b13fc",
    "ENTRY_BOOT_PROGRAM_TIMER_B": "46fc270023fc00013c26",
    "ENTRY_BOOT_STAGE_FRONTEND_SCREENS": "13fc00010001991c2079",
    "ENTRY_SECTION_START_TAIL": "423900019ac142390001",
}
