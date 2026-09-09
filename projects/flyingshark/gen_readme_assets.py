#!/usr/bin/env python3
"""Render the Flying Shark README gallery out of the VERIFIED C reconstruction.

Every play picture below is *drawn by the reconstruction*, not screenshotted from the original
program. `../../tools/recreate_kit` loads and relocates your own `bin/FLYSHARK.PRG` into the flat
image the differential harness uses, and this script then calls the very same `g_*` entry points
`recreate/test/` calls through ctypes — `recreate/src/sprite.c`'s `render_frame` and its twelve
masked blitters, `entity.c`'s movers and publishers, `player.c`, `weapons.c`, `hud.c` — and
de-interleaves the Atari low-resolution framebuffer they paint into a PNG.

WHAT THE ORACLE IS USED FOR, AND WHAT IT IS NOT. Unlike Zynaps' twin of this script, this one does
run the original's machine code — but ONLY where `recreate/test/` does, and for the same reason.

  * STAGING. A frame-loop routine is not a leaf: it runs on a machine the boot chain and
    `start_level` built. `test/conftest.py` builds that machine by REPLAYING the original under the
    oracle rather than transcribing it, and `test_sprite.py` stages its `render_frame` worlds the
    same way. This file stages one step further along the same path — `conftest.started_level`,
    which runs `init_stage_state` @ 0x1139a through `start_level` and stops at 0x1156a, the
    instruction after the `bsr set_palette_game` that ends it and before the `bra` into the sound
    module. So the terrain, the scroll phase, the level's spawn script and the palette are all the
    ORIGINAL's own work, and nothing about a stage's opening state is a shape this script invented.

NOT ONE PIXEL COMES FROM THE ORACLE, and BY CONSTRUCTION rather than by inspection. `main`'s loop
@ 0x1575c is forty-five `bsr`s and a closing `clr.w`, and the whole of it is one verified core —
`frame_loop_once` @ 0x1575c, `recreate/src/init.c` — so a frame here is ONE call into the
reconstruction. There is no per-step table to keep in the loop's order, no register carry for this
file to restate, and no arm of the loop the pictures take that the differential does not.

THE FIVE STAGES ARE REACHED THE WAY THE GAME REACHES THEM, and with verified cores at every step
(`_started_stage`): `level_progress_check` @ 0x124ae advances `level_number` — its level-advance arm
is the one the landing script's end takes — and `load_level_assets_patch_filenames` @ 0x10332 writes
that stage's five filename digits into the game's own five file records, so the names the model is
then asked for are the reconstruction's answer and not a table typed here. `conftest.started_level`
stages exactly the files those patched records name and runs the original's `start_level` over them.

WHICH FRAME EACH PLAY PICTURE IS, IS SEARCHED FOR AND NOT TYPED, with two stated exceptions. Each
stage is played with one fixed input script (`input_script`) poked into `joy1_state` and `key_bits`
— the bytes the IKBD interrupt handler would leave, and the only input `read_player_input` @ 0x14354
reads in this build (`../notes/frontend.md` §4: `use_keyboard_flag` is read and written nowhere).
A picture is then the first frame at which a stated CENSUS PREDICATE holds — how many enemy bullets
are in flight, how many of the player's are, how many enemies are dying, whether an item has
dropped, what the score is. The exceptions are `level1-takeoff`, which is a picture of a MOMENT and
takes a stated frame number, and `level1-landing`, which is the LAST frame of the stage (below).
What the search buys is that a caption about the SHAPE of a frame cannot outlive a change that
shifts the run: the run refuses instead of publishing a picture that no longer matches its caption.

THE STAGE-1 RUN IS PLAYED TO THE END OF THE LEVEL, and stops one frame short of where the
reconstruction stops being the game. `level_progress_check`'s verified body reaches BOTH of the
level record's triggers: the boss trigger (`level_table` +2, `A_boss_scroll_pos`), which draws
nothing — it only raises `enemy_fire_inhibit`, which is what stops the enemies firing — and the end
of the level (+0), which starts the clear tune and puts the plane into fly-off and then on to the landing
script. When that script ends it sets `level_complete`, and the same frame's `level_progress_check`
takes its level-advance arm. In the ORIGINAL that arm never returns (`addq.l #4,a7 / bra.w $15758`,
unwinding into a fresh `init_stage_state`); the C core increments `level_number` and returns, which
`frame_loop_once` cannot help. So `play_to_the_end_of_the_stage` keeps the frame BEFORE the advance
and refuses to play on: that frame — the plane back on the strip, its shadow under it — is the last
one this reconstruction can honestly draw of stage 1.

STAGE 5 IS NOT IN THE GALLERY, and the reason is the game's own. `load_level_assets` @ 0x10332
dispatches on the level number, and level 4's arm alone falls into the block at 0x103cc: the
"insert disc B" prompt, followed by `btst #7,$1777f / beq.s $103d6` — a spin on the fire button that
only the IKBD can end. `init_stage_state` clears `joy1_state` at its second instruction (0x1139a),
so no byte poked before the run survives to that spin, and `conftest.started_level` runs the
original with no external agent to press it. Reaching stage 5 would need `emu.run`'s scheduled-write
model, which that builder does not expose — so the gallery stops at stage 4 and says so rather than
placing stage 5's bytes by hand.

The title picture is not drawn by anything: it is `A\\FLY_SHK.NEO` as the ORIGINAL's own
`init_load_assets` left it in the fixture — 32,000 bytes copied to `Physbase - 0x80`, so the NEO's
128-byte header lands just below the screen and its palette is readable at the same place the game
reads it. Photographing it is how the original's own load gets shown rather than described.

Output goes to `out/readme/` (gitignored) and is then copied into the tracked
`<workspace>/assets/flyingshark/`, which is where every other game in this workspace keeps its README
pictures; a PNG left there by an older run of this script is removed, so the tracked folder and the
gallery cannot drift apart. Re-run:

    cd recreate && make venv && make test   # once: the venv, libflyingshark.so AND liboracle.so
    ./.venv/bin/python ../gen_readme_assets.py
"""
import collections
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RECREATE = HERE / "recreate"
sys.path.insert(0, str(WORKSPACE / "tools"))     # st_pixels, write_png
sys.path.insert(0, str(RECREATE / "test"))       # harness.py — binds the kit and loads the .so

import harness                     # noqa: E402  loads FLYSHARK.PRG into the image, opens the .so
import emu                         # noqa: E402  the oracle (harness put it on sys.path)
import abi                         # noqa: E402  the glue declarations the batteries use
import conftest                    # noqa: E402  the three image builders, replayed from the original
import test_sprite as frame        # noqa: E402  render_frame's entries, the screen and display list
import test_player as player       # noqa: E402  the input bytes read_player_input reads
import test_weapons as weapons     # noqa: E402  the bullet arenas and the smart bomb's blast
import test_entity as entity       # noqa: E402  the entity arena and the four item records
import test_hud as hud             # noqa: E402  the score, and the hall-of-fame text script
import test_frontend as frontend   # noqa: E402  the scenery band's counters
import st_pixels                   # noqa: E402  the workspace's ONE ST plane/palette model
from extract_graphics import write_png                  # noqa: E402

OUT = HERE / "out" / "readme"
TRACKED = WORKSPACE / "assets" / "flyingshark"
LIB = harness._lib

# ---- the ST low-resolution framebuffer -----------------------------------------------------------
#
# The plane model, the `$0RGB` expansion and the row stride are `../../tools/st_pixels.py`'s — the
# workspace's one decoder — so nothing about the ST's pixels is spelt again here. Only the SHAPE of
# this game's screen is local, and both figures come out of `test_sprite`'s own pins.
SCREEN_WIDTH = frame.SCREEN_ROW_BYTES // st_pixels.group_bytes() * st_pixels.PIXELS_PER_WORD
SCREEN_HEIGHT = frame.SCREEN_ROWS

# ---- the machine a picture is taken on -----------------------------------------------------------
#
# `init_stage_state` @ 0x1139a resets the per-stage state and falls into `start_level` @ 0x11440,
# which loads the level's five files, re-derives the map cursor, blacks the palette, prescrolls a
# whole screen of terrain and installs the in-play palette. The stop is the instruction AFTER that
# palette call and BEFORE `start_level`'s `bra` into the sound module: a picture wants the started
# level, not the tune.
STOP_AFTER_SET_PALETTE_GAME = 0x1156a  # `bra.w $12588`, the tail-call into sound_cmd

# `set_palette_game` @ 0x111be, run on its own so the ORIGINAL names the colour table rather than
# this script nominating one. Three instructions and an XBIOS call; its final image is discarded.
ENTRY_SET_PALETTE_GAME = 0x111be
A_palette_game = 0x16294             # ../names.txt: the in-play palette, installed at every level start
PALETTE_CALL_MAX_INSNS = 100_000     # three instructions and an XBIOS call

# The five files a stage loads — every BOOT_LOADS row except the two the boot chain loads outside a
# level (the sound module and the sprite bank), which are already in the fixture. Named by exclusion
# rather than sliced by index so a reordered BOOT_LOADS still works.
_NOT_LEVEL_ASSETS = ("MODULE.BAK", "SPRITES.CRU")
LEVEL_ASSET_RECORDS = tuple(record for record, name in conftest.BOOT_LOADS
                            if name not in _NOT_LEVEL_ASSETS)
# A record's DOS path is `A\<name>`, and for these five the DOS spelling IS the name on disc — which
# is what lets the file to stage be read out of the record the reconstruction just patched instead
# of being listed here per level. (`A\SPRITES.cru` is the one record where the two differ, and it is
# not one of these.)
DOS_PATH_SEPARATOR = "\\"

# ---- the frame loop ------------------------------------------------------------------------------
#
# `main` @ 0x15750 is three init calls and then its endless loop, `bra.w $1575c`
# (../notes/gameplay.md §2). ONE PASS OF THAT LOOP IS ONE VERIFIED CORE — `frame_loop_once`
# @ 0x1575c, which makes the forty-five `bsr`s in the original's own order, carries the three
# registers two of them read from their predecessors, and ends with the loop's own
# `clr.w level_just_started`. So this file names the loop once and states none of its internals;
# `recreate/test/test_init.py` is where the order and the carries are pinned.
GLUE_FRAME_LOOP = "g_frame_loop_once"

# The level-4 VBL handler's counter. Nothing this script runs is that handler, so the budget it
# would have counted is installed before each frame — which is exactly what `test_sprite.py`'s own
# render_frame cases do (`_frame_pokes`, `A_VBL_TICK`): without it `render_frame` spins on the kit's
# scheduled-write model instead of publishing.
FRAME_VBL_BUDGET = frame.RENDER_FRAME_VBL_BUDGET

# ---- the input script ----------------------------------------------------------------------------
#
# Two bytes a frame, both of them ones the ACIA handler owns and `read_player_input` reads:
# `joy1_state` (`test_player`'s JOY_*_BIT — 0 up, 1 down, 2 left, 3 right, 7 fire) and `key_bits`,
# whose bit 5 is the space bar the smart bomb is dropped with. The pause and abort keys beside it
# are never set: one of them spins on the kit's scheduled-write model and the other ends the game.
JOY_UP, JOY_DOWN = 1 << player.JOY_UP_BIT, 1 << player.JOY_DOWN_BIT
JOY_LEFT, JOY_RIGHT = 1 << player.JOY_LEFT_BIT, 1 << player.JOY_RIGHT_BIT
JOY_FIRE = 1 << player.JOY_FIRE_BIT
KEY_BOMB = 1 << player.KEY_BOMB_BIT

# FIRE IS PULSED, NOT HELD, and that is a mechanism rather than a flourish: `player_fire` @ 0x13e12
# takes ONE shot per press (`A_fire_held` is set on the shot and cleared only on a frame the button
# is seen up), so a script that holds the button fires a single burst and every later picture is of
# an empty sky. Two frames down, two up is the fastest a stick can be read.
FIRE_PERIOD, FIRE_HELD_FRAMES = 4, 2
# The stick flies a CLOSED SQUARE — down, left, up, right — so the plane stays over the middle of
# the screen for the whole run instead of drifting into a corner and out of its own pictures. The
# side is short enough that no leg ever reaches one of `player_move_*`'s clamps: a clamped leg is
# shorter than its opposite, and the square then walks off across the map (measured — a 14-frame
# side leaves the plane pinned to the left edge from frame 300 on).
FLIGHT_LEGS = (JOY_DOWN, JOY_LEFT, JOY_UP, JOY_RIGHT)
FLIGHT_LEG_FRAMES = 10               # * PLAYER_STEP_PIXELS = a 60-pixel side
# ...and the bomb key is held over one window. It is not held for the whole run because a stage
# starts with three bombs and `bomb_drop` @ 0x13d5c spends one per drop: after the window there is
# nothing left to drop, and the window is where `level1-smart-bomb` is found. It opens after the
# take-off script has let go of the controls (measured: frame 140), because `read_player_input`
# returns at its `player_input_locked` guard until then.
BOMB_KEY_FIRST_FRAME, BOMB_KEY_LAST_FRAME = 200, 380
# ...and the box the square keeps the plane inside while the stick is being read, which every
# caption below quietly claims by having a plane in it. Measured over all four stages, where the
# plane covers x 143..203 and y 66..126; this is that with a margin, and it is checked every frame
# so a path that started drifting fails by name instead of publishing pictures with no plane in them.
PLANE_IN_VIEW_X = (SCREEN_WIDTH // 4, SCREEN_WIDTH * 3 // 4)
PLANE_IN_VIEW_Y = (SCREEN_HEIGHT // 4, SCREEN_HEIGHT * 3 // 4)


def input_script(frame_number):
    """The (`joy1_state`, `key_bits`) bytes the script above holds at this frame."""
    fire = JOY_FIRE if frame_number % FIRE_PERIOD < FIRE_HELD_FRAMES else 0
    leg = FLIGHT_LEGS[frame_number // FLIGHT_LEG_FRAMES % len(FLIGHT_LEGS)]
    bombing = BOMB_KEY_FIRST_FRAME <= frame_number <= BOMB_KEY_LAST_FRAME
    return leg | fire, KEY_BOMB if bombing else 0


# THE PICTURES ARE FLOWN WITH THE GAME'S OWN INVULNERABILITY CHEAT ARMED, and that is a seam rather
# than a preference. MEASURED, not assumed: with the cheat off an earlier version of this script's
# joystick lost the plane on frame 194, before the second picture's own frame (2026-09-07).
#
# The death path is `player_publish` -> `player_death_sequence_step` -> the original's
# `bra restart_level_at_checkpoint` @ 0x14aac, and TWO THINGS make it unplayable here — neither of
# them "the init subsystem is unported" any more, since `init_new_game` and `start_level` both are.
# First, only that routine's HEAD is reconstructed: `src/player.c` carries [0x14aac, 0x14b22), up to
# the `bsr clear_actor_arrays`, and the tail after it has no core (STATUS.md's "Not reconstructed").
# Second, and structurally, the original never RETURNS from it — it ends `bra.w $1575c`, back to the
# frame loop's own top, unwinding the stack — which a C `frame_loop_once` that returns to this
# script cannot express. So a run that lets the plane die keeps playing frames the original never
# plays, and the pictures drift somewhere no machine goes. `HSC` — the first of the six developer
# cheats, and `hud.c`'s own verified core — makes both collision routines return immediately, so the
# run stays inside the arm the reconstruction covers. ARMED ONCE, and never twice: the handler's
# second use takes the arm its own flag chooses and raises `enemy_fire_inhibit` as well, which stops
# the enemies firing at all — the gallery would then be pictures of an emptier game than the one the
# player plays. (It does NOT kill the plane; that reading came from the word's old name, and
# ../notes/frontend.md §6 is where it was corrected.)
ARM_THE_CHEAT = "g_cheat_hsc_invulnerable"
# ...and the modes that are still that arm. The run refuses the moment the plane leaves them, so the
# guard above cannot silently stop working. Fly-off and landing are in the set because stage 1 is
# played to the end of the level, where the plane goes through both.
FLYING_MODES = (player.PLAYER_MODE_TAKEOFF, player.PLAYER_MODE_JOYSTICK,
                player.PLAYER_MODE_LANDING, player.PLAYER_MODE_FLYOFF)

# The two verified cores a stage is reached with, and the glue for the pieces of an attract page.
GLUE_ADVANCE_LEVEL = "g_level_progress_check"          # its level-advance arm, `level_complete` set
GLUE_PATCH_FILENAMES = "g_load_level_assets_patch_filenames"
GLUE_ATTRACT_PRESCROLL = "g_title_attract_prescroll"
GLUE_CLEAR_DISPLAY_LIST = "g_clear_display_list"
GLUE_BUILD_TEXT = "g_build_text_display_list"
GLUE_RENDER_FRAME = "g_render_frame"

PLAY_FRAMES = 3200                   # a bound on the search, not a length: every picture stops earlier
# The frame `level1-takeoff` is taken at: far enough in that the terrain has scrolled and the plane
# has climbed out of the sea, early enough that the first squadron has not arrived. A stated number
# because "the take-off" is what the picture is OF.
TAKEOFF_FRAME = 48

# ---- the sprite sheet ----------------------------------------------------------------------------
#
# Drawn by the four unclipped masked blitters onto a screen this script cleared, ONE BAND PER WIDTH
# CLASS, so the picture exercises `g_sprite_blit_w16`, `_w32`, `_w48` and `_w64` rather than one of
# them four times — and so each band's cell is only as wide as its own class needs, which is what
# fits eighteen records on a 320x200 screen instead of twelve.
#
# `sprite_blit_w<n>` writes width-class + 2 groups a row (src/sprite.c: class 0 is a 32-pixel
# sprite), which is what turns a width class into a cell width; a cell adds one group of gutter.
# The band HEIGHTS are the classes' own, measured off the directory in the loaded image: classes 0
# and 1 run to 32 rows and classes 2 and 3 to 64, and the four bands sum to 196 of the 200. A class
# with too few records to fill its band fails the assertion in `_sheet_selection` rather than
# leaving a gap.
SPRITE_GROUPS_OVER_CLASS = 2
SHEET_GUTTER_GROUPS = 1
SHEET_BANDS = (
    # (blitter, cell rows) — in width-class order, which is also the order they are laid out in.
    ("g_sprite_blit_w16", 34),
    ("g_sprite_blit_w32", 34),
    ("g_sprite_blit_w48", 62),
    ("g_sprite_blit_w64", 66),
)
SHEET_SHIFT = 0                      # every cell starts on a group boundary, so no sub-word rotate

# `SPRITES.cru`'s 20-byte directory record (../notes/gameplay.md §3.2). The pointer is ABSOLUTE in
# the post-load image: `init_load_assets` @ 0x112c2 relocated all 256 of them.
SPRITE_REC_DATA = 0
SPRITE_REC_CLASS = 4
# WORD: the height MINUS ONE — a `dbf` count, which `render_frame` hands the blitter unchanged
# (`move.w 6(a4),d7` @ 0x144b8; include/sprite.h). A record with 0xffff here carries no bitmap at
# all: those twelve exist only to give `sprite_hit_test` a box (../notes/assets_survey.md).
SPRITE_REC_LAST_ROW = 6
SPRITE_REC_NO_BITMAP = 0xffff

# ---- the attract screen's text pages -------------------------------------------------------------
#
# `title_attract_loop` @ 0x104f2 prescrolls the level-1 map and then cycles three text pages on a
# timer, each of them ONE call into `build_text_display_list` @ 0x10698 followed by the loop's own
# `bsr render_frame` @ 0x10594. The WHOLE loop is verified now — `title_attract_prescroll` (the
# slice [0x104f2, 0x1054a)), `title_attract_poll` and `title_frame_step` — but a page is still
# composed here out of the three calls the loop makes for one, because the loop does not take a page
# as an argument: it picks one off a countdown timer, advances the scroll under it, and spins on the
# fire button and the module's "still playing" byte. Driving it to the page this script wants would
# mean seeding that timer and photographing whatever terrain the poll had scrolled to, which is more
# machinery for a different picture.
A_text_credits = 0x16146             # `lea $16146,a0` @ 0x10670 — the second page of the three
TEXT_PAGE_ORIGIN_X, TEXT_PAGE_ORIGIN_Y = 0, 0  # `clr.l d1 / clr.l d2` @ 0x105a8, before every page

# ---- the title picture ---------------------------------------------------------------------------
#
# `init_load_assets` copies TITLE_COPY_BYTES from the START of A\FLY_SHK.NEO to Physbase - 0x80, so
# the NEOchrome header lands just below the screen and the pixels land on it (../names.txt @
# 0x11212). The palette is at the header's own +4 — the address the game hands XBIOS Setpalette.
NEO_HEADER_PALETTE = 4

_LONG = 4
_WORD = 2


def _u32(image, at):
    return int.from_bytes(image[at:at + _LONG], "big")


def _u16(image, at):
    return int.from_bytes(image[at:at + _WORD], "big")


def _put_word(image, at, value):
    image[at:at + _WORD] = value.to_bytes(_WORD, "big")


# ==================================================================================================
# The candidate: binding its glue, and running one verified core over an image
# ==================================================================================================

def _bind_glue():
    """Declare every glue this file calls, so ctypes cannot pass a 64-bit pointer as an `int`.

    `abi.declare_glue` is the batteries' own declaration, used here for the same reason: an image
    pointer truncated to 32 bits would be a segmentation fault at best and a picture of the wrong
    megabyte at worst.
    """
    abi.declare_glue(GLUE_FRAME_LOOP, ARM_THE_CHEAT, GLUE_ADVANCE_LEVEL, GLUE_ATTRACT_PRESCROLL,
                     GLUE_CLEAR_DISPLAY_LIST, GLUE_RENDER_FRAME)
    abi.declare_glue(GLUE_PATCH_FILENAMES, args=1)                    # d0 = the level number
    # a0 = the script, a1 = the display slots, d1 = x, d2 = y (src/hud.c's glue comment)
    abi.declare_glue(GLUE_BUILD_TEXT, args=4)
    # a0 = sprite data, a1 = screen, d6 = x & 0xf, d7 = rows - 1 (src/sprite.c's glue comment)
    abi.declare_glue(*(blitter for blitter, _rows in SHEET_BANDS), args=4)


def _core(image, glue, *args):
    """Run one verified core over `image` in the armed candidate buffer, and hand back what it left.

    The arm-then-call is `recreate/test/`'s own shape: `harness.candidate_image` puts the bytes
    where the `.so` will read them and `harness.arm_candidate` resets the kit's ledgers, so an OS
    call this core makes is counted against this core rather than the last one.
    """
    buf = harness.candidate_image(image)
    harness.arm_candidate()
    getattr(LIB, glue)(buf, *args)
    return bytearray(buf)


def _setscreen_publications():
    """How many times the armed candidate run has handed XBIOS Setscreen a base.

    The kit's off-image OS event ledger, read the way `harness._vet_os_event_state` reads it. The
    ledger carries Setscreen's LOGICAL base only (`tools/recreate_kit/include/os.h`), which is the
    -1 this game passes — so this counts publications and the base itself comes from the pointer
    `publish_and_wait` read, below.
    """
    count = LIB.g_os_event_count()
    assert count < harness.OS_EVENT_LOG_MAX, (
        f"the run logged {count} OS events and the ledger caps at {harness.OS_EVENT_LOG_MAX} — what "
        f"it holds is a truncated prefix, so nothing read out of it here means what it says")
    kinds = LIB.g_os_event_kinds()
    return sum(1 for event in range(count) if kinds[event] == harness.OS_EVENT_SETSCREEN)


def _setpalette_table(out_regs):
    """The colour table the ORACLE run handed XBIOS Setpalette, out of its own event stream."""
    tables = [value for kind, value in out_regs["events"] if kind == harness.OS_EVENT_SETPALETTE]
    assert len(tables) == 1, (
        f"the run made {len(tables)} Setpalette calls and this reads the one — either the entry is "
        f"no longer the palette wrapper, or something else on the path installed a palette too")
    return tables[0]


# ==================================================================================================
# Staging: the boot chain, a new game, and a started stage — all of it the original's own code
# ==================================================================================================

def _level_asset_loads(image):
    """The (record, file-on-disc) rows `conftest.started_level` should stage, for THIS image.

    The five records have already been patched for the stage by `load_level_assets_patch_filenames`,
    so the name to stage is read back out of each record rather than listed per level here: the
    reconstruction decides which HSC banks and which LEVELn.MAP a stage wants, and a bank that moved
    would show up as a missing file rather than as a picture of the previous level's tiles.
    """
    loads = []
    for record in LEVEL_ASSET_RECORDS:
        _dest, _length, dos_path = conftest.file_record(image, record)
        on_disc = dos_path.rsplit(DOS_PATH_SEPARATOR, 1)[-1]
        assert (conftest.DISK_DIR / on_disc).is_file(), (
            f"the patched record at {record:#x} names {dos_path!r}, and {on_disc} is not in "
            f"{conftest.DISK_DIR} — the extracted disc is missing a file this stage loads")
        loads.append((record, on_disc))
    return tuple(loads)


def _advanced_to_level(post_new_game, level):
    """`level_number` walked up to `level` by the reconstruction's own level-advance arm.

    `level_progress_check` @ 0x124ae advances the stage when `level_complete` is set, which is what
    the landing script's end does — so the flag is set once per step and the verified core is asked
    for the next level number, rather than this script poking one in. The core clears the flag on
    its way out, which is why it is re-set inside the loop.
    """
    image = bytearray(post_new_game)
    for _step in range(level):
        _put_word(image, player.A_level_complete, 1)
        image = _core(image, GLUE_ADVANCE_LEVEL)
    assert _u16(image, player.A_level_number) == level, (
        f"{level} steps of the level-advance arm left level_number "
        f"{_u16(image, player.A_level_number)} — either the arm no longer counts up by one or "
        f"level_complete is no longer what arms it")
    return image


def _started_stage(post_new_game, level):
    """A STAGE the original started, for any of the levels this gallery reaches.

    Three steps, and the first two are the reconstruction's: the level number is advanced by
    `level_progress_check`, the five filename digits are patched by `load_level_assets_patch_
    filenames`, and only then does `conftest.started_level` — the builder `recreate/test/`'s own
    frame cases stage on — run `init_stage_state` @ 0x1139a through `start_level` under the oracle
    with exactly the files those records name. Stopping at 0x1156a is what leaves the tune out: a
    picture wants the started level, not the music.
    """
    image = _core(_advanced_to_level(post_new_game, level), GLUE_PATCH_FILENAMES, level)
    loads = _level_asset_loads(image)
    print(f"  stage {level + 1}: {', '.join(name for _record, name in loads)}")
    return bytearray(conftest.started_level(bytes(image), loads=loads,
                                            stop_pc=STOP_AFTER_SET_PALETTE_GAME))


def _in_play_palette(started):
    """The sixteen colour words `set_palette_game` itself points XBIOS at, as RGB triples.

    WHY THE ORIGINAL AND NOT A ROW THIS SCRIPT NAMED. The image carries four sixteen-pen rows
    (../names.txt: palette_title 0x16274, palette_game 0x16294, palette_black 0x162b4, and the
    NEO's own), and picking the wrong one produces a picture that is plausible and wrong — a level
    under `palette_title` renders green on green, which is exactly what the title palette's own
    comment records. So the table is taken from the address the ORIGINAL's palette wrapper hands
    the OS, and only then checked against the name ../names.txt gives it.
    """
    _final, _writes, out_regs = emu.run(bytearray(started), ENTRY_SET_PALETTE_GAME,
                                        max_insns=PALETTE_CALL_MAX_INSNS)
    table = _setpalette_table(out_regs)
    assert table == A_palette_game, (
        f"set_palette_game handed XBIOS the table at {table:#x}, and ../names.txt calls "
        f"{A_palette_game:#x} the in-play palette — one of the two has moved")
    return st_pixels.palette_rgb(st_pixels.read_palette_words(started, table))


# ==================================================================================================
# The census a picture is chosen by
# ==================================================================================================

# `A_player_shot_slot_0`'s three tables point at five bullets each, and those fifteen records are
# `A_player_bullet_arena` (include/weapons.h) — so the arena's length is the product, not a literal.
PLAYER_BULLETS = weapons.PLAYER_SHOT_SLOTS * weapons.PLAYER_SHOT_BULLETS
SCORE_BCD_BYTES = 3                  # `lea $15a2a,a0` + three `abcd`s — six digits (include/hud.h)


class Census:
    """What is on screen and in the air, read out of the arrays the frame loop keeps.

    A picture's predicate is written against these fields, so a caption that says "enemy fire in the
    air and an enemy going up" is the same claim the run refuses on. Every address and stride is a
    `recreate/test/` mirror of the header that owns it — nothing about a record layout is respelt.
    """

    def __init__(self, image):
        self.display_records = sum(
            1 for record in range(frame.A_DISPLAY_LIST, frame.A_DISPLAY_LIST_END,
                                  frame.DISPLAY_REC_BYTES)
            if image[record + frame.DISPLAY_REC_ACTIVE] != frame.DISPLAY_ACTIVE_HIDDEN)
        self.player_bullets = sum(
            1 for slot in self._player_bullet_slots()
            if _u16(image, slot + weapons.PLAYER_BULLET_STATE) != weapons.PLAYER_BULLET_FREE)
        self.enemy_bullets = sum(1 for slot in self._enemy_bullet_slots(image)
                                 if _u16(image, slot + weapons.ENEMY_BULLET_ACTIVE))
        live = [slot for slot in self._entity_slots()
                if _u16(image, slot + entity.ENTITY_ACTIVE)]
        self.entities = len(live)
        self.dying = sum(1 for slot in live if _u16(image, slot + entity.ENTITY_DYING))
        self.items = sum(1 for item in (entity.A_item_weapon, entity.A_item_life,
                                        entity.A_item_bomb, entity.A_item_extra)
                         if _u16(image, item + entity.ITEM_ACTIVE))
        self.blast_step = (_u16(image, weapons.A_blast_step)
                           if _u16(image, weapons.A_bomb_exploding) else 0)
        self.score = image[hud.A_score_bcd:hud.A_score_bcd + SCORE_BCD_BYTES]
        self.scenery_band_rows = _u16(image, frontend.A_scenery_band_rows)
        self.level = _u16(image, player.A_level_number)
        self.mode = image[player.A_player + player.PLAYER_MODE]
        self.plane_x = _u16(image, player.A_player + player.PLAYER_X)
        self.plane_y = _u16(image, player.A_player + player.PLAYER_Y)

    @staticmethod
    def _player_bullet_slots():
        """The fifteen 8-byte records the three shot slots between them point at."""
        return range(weapons.A_player_bullet_arena,
                     weapons.A_player_bullet_arena + PLAYER_BULLETS * weapons.PLAYER_BULLET_BYTES,
                     weapons.PLAYER_BULLET_BYTES)

    @staticmethod
    def _enemy_bullet_slots(image):
        """The 10-byte records up to the array's own 999 sentinel, which every walk tests first."""
        slot = weapons.A_enemy_bullets
        while _u16(image, slot + weapons.ENEMY_BULLET_ACTIVE) != weapons.ENEMY_BULLET_END:
            yield slot
            slot += weapons.ENEMY_BULLET_BYTES

    @staticmethod
    def _entity_slots():
        return range(entity.A_entity_arena,
                     entity.A_entity_arena + entity.ENTITY_SLOTS * entity.ENTITY_STRIDE,
                     entity.ENTITY_STRIDE)

    def scoring(self):
        """True once the score has moved off the zero `score_reset` left — three packed-BCD bytes."""
        return any(self.score)

    def plane_in_view(self):
        """True while the plane is inside the middle half of the screen in both axes."""
        return (PLANE_IN_VIEW_X[0] <= self.plane_x <= PLANE_IN_VIEW_X[1]
                and PLANE_IN_VIEW_Y[0] <= self.plane_y <= PLANE_IN_VIEW_Y[1])

    def __str__(self):
        return (f"{self.display_records} records, {self.entities} enemies ({self.dying} dying), "
                f"{self.player_bullets}+{self.enemy_bullets} bullets, {self.items} items, "
                f"score {self.score.hex()}")


# ==================================================================================================
# Playing a stage with the verified cores
# ==================================================================================================

class Playthrough:
    """One run of one stage, played forward by the verified cores and photographed as it goes.

    Frames are only ever played FORWARD, so the pictures of a stage come out of one continuous game
    rather than out of several independent runs that each replayed the staging.
    """

    def __init__(self, started, level):
        self.level = level
        self.frame_number = 0
        self.published = None
        self.image = _core(started, ARM_THE_CHEAT)
        self.previous = None
        self.finished = False
        self._census = Census(self.image)
        assert self.image[player.A_invuln_flag] != 0, (
            f"{ARM_THE_CHEAT} did not leave the invulnerability flag set, so this run would play on "
            f"past the plane's death")

    def census(self):
        """The census of the frame just played — taken once and shared by the vet and the search."""
        return self._census

    def step(self):
        """One whole pass of `main`'s loop, and the screen base `render_frame` published.

        The base is read out of `A_screen_draw` BEFORE the call, which is where `render_frame` finds
        it: that routine's LAST act is `advance_scroll`, moving the pointer on to the next frame's
        screen and leaving the published one in `A_screen_prev1` — so the two are checked against
        each other afterwards rather than either being trusted. Nothing else in the loop writes
        `A_screen_draw`.
        """
        assert not self.finished, (
            f"stage {self.level + 1} ended at frame {self.frame_number} and this asked for another "
            f"frame — past the level advance the reconstruction is no longer playing the game")
        self.previous = (self.image, self.published)

        image = bytearray(self.image)
        stick, keys = input_script(self.frame_number)
        image[player.A_joy1_state] = stick
        image[player.A_key_bits] = keys
        image[frame.A_VBL_TICK:frame.A_VBL_TICK + _LONG] = FRAME_VBL_BUDGET.to_bytes(_LONG, "big")

        published = _u32(image, frame.A_SCREEN_DRAW)
        self.image = _core(image, GLUE_FRAME_LOOP)
        self.published = published
        self.frame_number += 1
        self._census = Census(self.image)
        self._vet(published)
        return self._census.level == self.level

    def _vet(self, published):
        publications = _setscreen_publications()
        assert publications == 1, (
            f"frame {self.frame_number}: the loop published {publications} screen bases and a frame "
            f"publishes exactly one — either render_frame took its prescroll arm, or something else "
            f"flipped")
        census = self._census
        assert census.mode in FLYING_MODES, (
            f"frame {self.frame_number}: the plane left the modes this run can play — mode "
            f"{census.mode:#x}, and the death and game-over arms both end in a routine no subsystem "
            f"has ported (ARM_THE_CHEAT is what is meant to keep them out of reach)")
        assert census.mode != player.PLAYER_MODE_JOYSTICK or census.plane_in_view(), (
            f"frame {self.frame_number}: the stick left the plane at ({census.plane_x}, "
            f"{census.plane_y}), outside the middle half of the screen — FLIGHT_LEGS has started "
            f"walking the plane off its square, and the pictures below would stop having one in them")
        assert _u32(self.image, frame.A_SCREEN_PREV1) == published, (
            f"frame {self.frame_number}: render_frame published {published:#x} and left "
            f"{_u32(self.image, frame.A_SCREEN_PREV1):#x} in A_screen_prev1 — this picture would be "
            f"of a buffer the frame did not put on screen")

    def play_to(self, target_frame):
        """Play forward to a STATED frame — for a picture that is of a moment, not of a shape."""
        assert target_frame >= self.frame_number, (
            f"frame {target_frame} is behind this playthrough's frame {self.frame_number} — the "
            f"pictures are taken in the order they are played")
        while self.frame_number < target_frame:
            assert self.step(), (
                f"stage {self.level + 1} ended before frame {target_frame}")
        return self

    def play_until(self, holds, description):
        """Play on until `holds(census)`, and refuse a predicate the stage's start already meets.

        The refusal is the point: a picture captioned "enemy fire everywhere" over a frame that had
        it before the search began would be a lie no reader of the README could catch.
        """
        assert not holds(self.census()), (
            f"frame {self.frame_number} already satisfies \"{description}\" ({self.census()}), so "
            f"searching for it says nothing about the picture it selects")
        while self.frame_number < PLAY_FRAMES:
            if not self.step():
                break
            if holds(self.census()):
                return self
        raise AssertionError(
            f"stage {self.level + 1} never reached \"{description}\" in {self.frame_number} frames "
            f"(it ended at {self.census()}) — either the predicate is out of this run's reach or "
            f"the input script no longer flies the same game")

    def play_to_the_end_of_the_stage(self):
        """Play to the LAST frame of the level, which is one before the reconstruction runs out.

        `level_progress_check`'s level-advance arm ends `addq.l #4,a7 / bra.w $15758` — it unwinds
        its caller and re-enters `main` at a fresh `init_stage_state`. The verified C core cannot
        express that: it bumps `level_number` and returns into a `frame_loop_once` that carries on
        over the stage that has just ended. So the frame the advance happened on is thrown away and
        the one before it — the plane back on the strip with its shadow under it, the last frame of
        the stage that is still the game — is what the picture is taken from.
        """
        while self.frame_number < PLAY_FRAMES:
            if not self.step():
                self.image, self.published = self.previous
                self.frame_number -= 1
                self.finished = True
                return self
        raise AssertionError(
            f"stage {self.level + 1} did not reach its level-end trigger in {PLAY_FRAMES} frames "
            f"({self.census()}) — `level_table` +0 is the scroll position it is waiting for")


# ==================================================================================================
# The sprite sheet
# ==================================================================================================

# One directory entry, in the four fields a blitter call needs it in.
SpriteRecord = collections.namedtuple("SpriteRecord", "index width_class last_row data")


def _sprite_records(image):
    """Every SPRITES.cru record that has pixels, in the game's own record order.

    The directory is read out of the RELOCATED image, so a record's pointer is the absolute address
    `render_frame` would hand a blitter, and the row word is the `dbf` count the blitter wants —
    both of them exactly as `render_frame` reads them.
    """
    records = []
    for index in range(conftest.SPRITE_RECORDS):
        record = conftest.A_sprite_bank + index * conftest.SPRITE_RECORD_BYTES
        last_row = _u16(image, record + SPRITE_REC_LAST_ROW)
        if last_row != SPRITE_REC_NO_BITMAP:
            records.append(SpriteRecord(index, _u16(image, record + SPRITE_REC_CLASS), last_row,
                                        _u32(image, record + SPRITE_REC_DATA)))
    return records


def _sheet_band_layout(width_class, cell_rows):
    """(cell bytes, columns) for one band: a class-`c` sprite's groups plus a group of gutter."""
    cell_groups = width_class + SPRITE_GROUPS_OVER_CLASS + SHEET_GUTTER_GROUPS
    cell_bytes = cell_groups * frame.SCREEN_GROUP_BYTES
    columns = frame.SCREEN_ROW_BYTES // cell_bytes
    assert columns and cell_rows <= SCREEN_HEIGHT, (
        f"width class {width_class} wants a {cell_bytes}-byte, {cell_rows}-row cell, which does not "
        f"fit a {frame.SCREEN_ROW_BYTES}-byte, {SCREEN_HEIGHT}-row screen")
    return cell_bytes, columns


def _sheet_selection(image):
    """One band's worth of records for each width class, in the game's own record order.

    The first of each class that fits its band, rather than a hand-picked list, so the sheet cannot
    quietly become a picture of records this script preferred.
    """
    records = _sprite_records(image)
    bands = []
    for width_class, (_blitter, cell_rows) in enumerate(SHEET_BANDS):
        _cell_bytes, columns = _sheet_band_layout(width_class, cell_rows)
        of_class = [record for record in records if record.width_class == width_class
                    and record.last_row + 1 <= cell_rows]
        assert len(of_class) >= columns, (
            f"width class {width_class} has only {len(of_class)} records that fit a {cell_rows}-row "
            f"cell and its band holds {columns}")
        bands.append(of_class[:columns])
    return bands


def _sprite_sheet(started, base):
    """Every cell drawn by the reconstruction's own masked blitter, onto a screen cleared here.

    The clearing is this script's — a sheet is a canvas, not a frame the game ever drew — and it is
    the only thing on this picture that the reconstruction did not put there.
    """
    image = bytearray(started)
    image[base:base + frame.SCREEN_ROW_BYTES * SCREEN_HEIGHT] = bytes(
        frame.SCREEN_ROW_BYTES * SCREEN_HEIGHT)
    bands = _sheet_selection(image)

    buf = harness.candidate_image(image)
    harness.arm_candidate()
    top_row = 0
    for width_class, band in enumerate(bands):
        blitter, cell_rows = SHEET_BANDS[width_class]
        cell_bytes, _columns = _sheet_band_layout(width_class, cell_rows)
        for column, record in enumerate(band):
            destination = base + top_row * frame.SCREEN_ROW_BYTES + column * cell_bytes
            getattr(LIB, blitter)(buf, record.data, destination, SHEET_SHIFT, record.last_row)
        print(f"  class {width_class}: {', '.join(f'#{r.index}' for r in band)}")
        top_row += cell_rows
    return bytearray(buf)


# ==================================================================================================
# The attract screen's text pages
# ==================================================================================================

def _attract_page(prescrolled, script):
    """One attract page: the display list cleared, the script compiled, the frame rendered.

    Exactly the three calls `title_attract_loop` makes for a page — `bsr clear_display_list`
    @ 0x10552, `bsr build_text_display_list` @ 0x10690 with A0 on the script and A1 on the display
    list, and the loop's own `bsr render_frame` @ 0x10594 — over the terrain the attract prescroll
    left. Returns (image, published base).
    """
    image = _core(prescrolled, GLUE_CLEAR_DISPLAY_LIST)
    image = _core(image, GLUE_BUILD_TEXT, script, frame.A_DISPLAY_LIST,
                  TEXT_PAGE_ORIGIN_X, TEXT_PAGE_ORIGIN_Y)
    image[frame.A_VBL_TICK:frame.A_VBL_TICK + _LONG] = FRAME_VBL_BUDGET.to_bytes(_LONG, "big")
    published = _u32(image, frame.A_SCREEN_DRAW)
    image = _core(image, GLUE_RENDER_FRAME)
    assert _u32(image, frame.A_SCREEN_PREV1) == published, (
        f"the attract page's render_frame published {_u32(image, frame.A_SCREEN_PREV1):#x} and this "
        f"would photograph {published:#x}")
    live = Census(image).display_records
    assert live, "the compiled text script left no live display record, so the page would be blank"
    print(f"  {live} glyph records")
    return image, published


# ==================================================================================================
# Writing the pictures
# ==================================================================================================

def _screen(name, image, base, palette):
    """Decode the framebuffer at `base` into `out/readme/<name>.png` and hand back its bytes.

    `st_pixels.decode_planar` REFUSES a slice that would run off the end of the image — a wrong base
    would otherwise decode as pen 0 everywhere, which is a blank, plausible PNG and the one failure
    a picture never shows.
    """
    path = OUT / f"{name}.png"
    write_png(str(path), SCREEN_WIDTH, SCREEN_HEIGHT,
              st_pixels.decode_planar(image, SCREEN_WIDTH, SCREEN_HEIGHT, offset=base), palette)
    print(f"  wrote {path.relative_to(WORKSPACE)} ({path.stat().st_size:,} B)")
    return name, path.read_bytes()


def _title(post_load):
    """A\\FLY_SHK.NEO where the ORIGINAL's own `init_load_assets` put it, in its own header palette."""
    header = harness.OS_SCREEN_BASE - conftest.TITLE_COPY_OFFSET
    palette = st_pixels.palette_rgb(
        st_pixels.read_palette_words(post_load, header + NEO_HEADER_PALETTE))
    return _screen("title", post_load, harness.OS_SCREEN_BASE, palette)


# ---- what each stage is photographed for ---------------------------------------------------------
#
# One row per picture: the file name, and either a stated frame or a census predicate with the
# sentence the run refuses on. The predicates are floors that this run's stages really cross —
# every one of them was measured before it was written down — and a stage that stops crossing one
# fails by name rather than publishing a picture the caption no longer describes.
BLAST_PICTURE_STEP = 6               # of the fourteen `blast_offset_tbl` steps: the blast at its widest
FIREFIGHT_ENEMY_BULLETS, FIREFIGHT_DYING = 5, 1
FLEET_ENEMY_BULLETS, FLEET_ENEMIES = 8, 24
CARRIER_ENEMY_BULLETS, CARRIER_ENEMIES, CARRIER_DYING = 10, 16, 2
AIRFIELD_ENEMY_BULLETS, AIRFIELD_ENEMIES = 8, 18
JUNGLE_ENEMY_BULLETS, JUNGLE_DYING = 8, 2
SCENERY_BAND_PICTURE_ROWS = 6        # whole 32-pixel tile rows of the hand-blitted band


def _stage_pictures():
    """(level number, ((file name, how to reach it), ...)) for every stage in the gallery.

    A `reach` is called with the stage's `Playthrough`; the pictures of a stage are listed in the
    order they are played, because the run only ever goes forward.
    """
    return (
        (0, (
            ("level1-takeoff", lambda play: play.play_to(TAKEOFF_FRAME)),
            ("level1-smart-bomb", lambda play: play.play_until(
                lambda c: c.blast_step == BLAST_PICTURE_STEP,
                f"the smart bomb's blast on step {BLAST_PICTURE_STEP} of fourteen")),
            ("level1-firefight", lambda play: play.play_until(
                lambda c: (c.enemy_bullets >= FIREFIGHT_ENEMY_BULLETS and c.player_bullets
                           and c.dying >= FIREFIGHT_DYING and c.items and c.scoring()),
                f"{FIREFIGHT_ENEMY_BULLETS} enemy bullets in the air, the player's own on screen, "
                f"an enemy going up, a dropped item falling and a score on the board")),
            ("level1-landing", lambda play: play.play_to_the_end_of_the_stage()),
        )),
        (1, (
            ("level2-fleet", lambda play: play.play_until(
                lambda c: (c.enemy_bullets >= FLEET_ENEMY_BULLETS
                           and c.entities >= FLEET_ENEMIES and c.scoring()),
                f"{FLEET_ENEMIES} of the fleet alive and {FLEET_ENEMY_BULLETS} bullets in the "
                f"air")),
            ("level2-carrier", lambda play: play.play_until(
                lambda c: (c.dying >= CARRIER_DYING and c.entities >= CARRIER_ENEMIES
                           and c.enemy_bullets >= CARRIER_ENEMY_BULLETS),
                f"{CARRIER_DYING} of the ship's guns going up under "
                f"{CARRIER_ENEMY_BULLETS} bullets of return fire")),
        )),
        (2, (
            ("level3-airfield", lambda play: play.play_until(
                lambda c: (c.enemy_bullets >= AIRFIELD_ENEMY_BULLETS
                           and c.entities >= AIRFIELD_ENEMIES and c.scoring()),
                f"{AIRFIELD_ENEMIES} defenders alive and {AIRFIELD_ENEMY_BULLETS} bullets in the "
                f"air")),
            ("level3-scenery-band", lambda play: play.play_until(
                lambda c: c.scenery_band_rows >= SCENERY_BAND_PICTURE_ROWS,
                f"level2_scenery_effect's hand-blitted band grown to "
                f"{SCENERY_BAND_PICTURE_ROWS} whole tile rows")),
        )),
        (3, (
            ("level4-jungle", lambda play: play.play_until(
                lambda c: (c.enemy_bullets >= JUNGLE_ENEMY_BULLETS and c.dying >= JUNGLE_DYING
                           and c.scoring()),
                f"{JUNGLE_ENEMY_BULLETS} bullets in the air and {JUNGLE_DYING} enemies going up")),
        )),
    )


def render_everything():
    """Every picture, each stage in one continuous playthrough. Returns {name: PNG bytes}."""
    OUT.mkdir(parents=True, exist_ok=True)
    print("staging: boot chain -> new game (the original, under the oracle)")
    post_load = conftest.post_load()
    post_new_game = conftest.post_new_game(post_load)
    pictures = [_title(post_load)]

    machines = []
    for level, shots in _stage_pictures():
        started = _started_stage(post_new_game, level)
        palette = _in_play_palette(started)
        machines.append((started, palette))
        play = Playthrough(started, level)
        for name, reach in shots:
            reach(play)
            print(f"  frame {play.frame_number}: {play.census()}")
            pictures.append(_screen(name, play.image, play.published, palette))

    # The attract pages and the sheet are drawn on the FIRST stage's machine, in the palette
    # `set_palette_game` installs. That is one table for the whole game (`A_palette_game`), and the
    # loop above has just had the ORIGINAL name it once per stage.
    started, palette = machines[0]

    print("composing the attract screen's text pages with the frontend and hud cores")
    prescrolled = _core(post_new_game, GLUE_ATTRACT_PRESCROLL)
    for name, script in (("attract-credits", A_text_credits),
                         ("attract-hall-of-fame", hud.A_text_hall_of_fame)):
        image, published = _attract_page(prescrolled, script)
        pictures.append(_screen(name, image, published, palette))

    print("drawing the sprite sheet with the four masked blitters")
    ring_slot_0 = _u32(started, frame.A_SCREEN_RING)
    pictures.append(_screen("sprites", _sprite_sheet(started, ring_slot_0), ring_slot_0, palette))
    return dict(pictures)


def main():
    first = render_everything()
    print("re-rendering the whole set to prove it is a function of the game files alone")
    second = render_everything()
    for name, png in first.items():
        assert second[name] == png, (
            f"{name}.png differs between two runs of this script, so something on the path reads a "
            f"clock, a random source or leftover state — the set is not reproducible")

    TRACKED.mkdir(parents=True, exist_ok=True)
    for name in first:
        shutil.copyfile(OUT / f"{name}.png", TRACKED / f"{name}.png")
        print(f"  tracked {(TRACKED / f'{name}.png').relative_to(WORKSPACE)}")
    # A picture this run no longer makes is a picture the READMEs no longer show, and leaving it in
    # the tracked folder is how a renamed gallery keeps a stale frame alive. The folder holds this
    # script's output and nothing else.
    for stale in sorted(TRACKED.glob("*.png")):
        if stale.stem not in first:
            stale.unlink()
            print(f"  removed stale {stale.relative_to(WORKSPACE)}")


_bind_glue()

if __name__ == "__main__":
    main()
