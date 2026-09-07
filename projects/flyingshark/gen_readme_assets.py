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
    same way. This file stages one step further along the same path — `init_stage_state` @ 0x1139a,
    which tail-calls `start_level` — and stops at 0x1156a, the instruction after the
    `bsr set_palette_game` that ends it and before the `bra` into the sound module. So the terrain,
    the scroll phase, the level-1 spawn script and the palette are all the ORIGINAL's own work, and
    nothing about the level's opening state is a shape this script invented.

NOT ONE PIXEL COMES FROM THE ORACLE, and now BY CONSTRUCTION rather than by inspection. `main`'s
loop @ 0x1575c is forty-five `bsr`s and a closing `clr.w`, and the whole of it is one verified
core — `frame_loop_once` @ 0x1575c, `recreate/src/init.c` — so a frame here is ONE call into the
reconstruction. There is no per-step table to keep in the loop's order, no register carry for this
file to restate, and no arm of the loop the pictures take that the differential does not.

WHICH FRAME EACH PLAY PICTURE IS, IS SEARCHED FOR AND NOT TYPED, with one stated exception. The
level is played with one fixed joystick script (`JOYSTICK_SCRIPT`) poked into `joy1_state` — the
byte the IKBD interrupt handler would leave, and the only input `read_player_input` @ 0x14354 reads
in this build (`../notes/frontend.md` §4: `use_keyboard_flag` is read and written nowhere). A
picture is then the first frame whose DISPLAY LIST census reaches a floor. The exception is
`level1-takeoff`, which is a picture of a MOMENT — the plane still climbing out of its take-off
script — and takes a stated frame number. What the search buys is that a caption about the SHAPE of
a frame cannot outlive a change that shifts the run: the run refuses instead of publishing a
picture that no longer matches its caption.

The title picture is not drawn by anything: it is `A\FLY_SHK.NEO` as the ORIGINAL's own
`init_load_assets` left it in the fixture — 32,000 bytes copied to `Physbase - 0x80`, so the NEO's
128-byte header lands just below the screen and its palette is readable at the same place the game
reads it. Photographing it is how the original's own load gets shown rather than described.

Output goes to `out/readme/` (gitignored), and the handful the READMEs embed is copied into the
tracked `<workspace>/assets/flyingshark/`, which is where every other game in this workspace keeps
its README pictures. Re-run:

    cd recreate && make venv && make test   # once: the venv, libflyingshark.so AND liboracle.so
    ./.venv/bin/python ../gen_readme_assets.py
"""
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
import test_player as player       # noqa: E402  the joystick byte read_player_input reads
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

# The five files `load_level_assets` opens for level 0 — every BOOT_LOADS row except the two the
# boot chain loads outside a level (the sound module and the sprite bank), which are already in the
# fixture. Named by exclusion rather than sliced by index so a reordered BOOT_LOADS still works.
_NOT_LEVEL_ASSETS = ("MODULE.BAK", "SPRITES.CRU")
LEVEL_ASSET_LOADS = tuple(load for load in conftest.BOOT_LOADS if load[1] not in _NOT_LEVEL_ASSETS)

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

# ---- the joystick script -------------------------------------------------------------------------
#
# `joy1_state`'s bits, from ../names.txt's comment on read_player_input: 0 up, 1 down, 2 left,
# 3 right, 7 fire. One byte per frame, the last row repeating for the rest of the run — the plane
# climbs, drifts across the map and holds fire, which is what fills a picture with bullets and
# muzzle flashes without needing a player.
JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_FIRE = 0x01, 0x02, 0x04, 0x08, 0x80
JOYSTICK_SCRIPT = (
    (60, 0),                          # the take-off script flies the plane in; the stick is ignored
    (40, JOY_UP | JOY_FIRE),
    (30, JOY_UP | JOY_RIGHT | JOY_FIRE),
    (40, JOY_LEFT | JOY_FIRE),
    (30, JOY_RIGHT | JOY_FIRE),
    (0, JOY_FIRE),                    # a zero-length row runs for the rest of the game
)

# THE PICTURES ARE FLOWN WITH THE GAME'S OWN INVULNERABILITY CHEAT ARMED, and that is a seam rather
# than a preference. MEASURED, not assumed: with the cheat off this joystick script loses the plane
# on frame 194, before the second picture's own frame (2026-09-07).
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
# run stays inside the arm the reconstruction covers. ONCE, never twice: a second use of `HSC` sets
# `player_hit` instead and kills the player (../notes/frontend.md §6).
ARM_THE_CHEAT = "g_cheat_hsc_invulnerable"
# ...and the modes that are still that arm. The run refuses the moment the plane leaves them, so the
# guard above cannot silently stop working.
FLYING_MODES = (player.PLAYER_MODE_TAKEOFF, player.PLAYER_MODE_JOYSTICK,
                player.PLAYER_MODE_LANDING, player.PLAYER_MODE_FLYOFF)

PLAY_FRAMES = 900                    # a bound on the search, not a length: every picture stops earlier
# The frame `level1-takeoff` is taken at: far enough in that the terrain has scrolled and the plane
# has climbed out of the sea, early enough that the first squadron has not arrived. A stated number
# because "the take-off" is what the picture is OF.
TAKEOFF_FRAME = 48
# ...and the census the two later pictures search for: how many of the 223 display records must be
# live before a frame is kept. Floors, measured, and the run refuses a floor the level start already
# meets — a picture captioned "busy" over the opening frame would be a lie no reader could catch.
BUSY_RECORDS = 26
CROWDED_RECORDS = 34

# ---- the sprite sheet ----------------------------------------------------------------------------
#
# Drawn by the four unclipped masked blitters onto a screen this script cleared, one per width
# class, so the picture exercises `g_sprite_blit_w16`, `_w32`, `_w48` and `_w64` rather than one of
# them four times. A class-`c` sprite covers c + 2 sixteen-pixel screen groups (src/sprite.c), so a
# cell five groups wide holds the widest of them with a column of space either side.
SHEET_CELL_GROUPS = 5
SHEET_CELL_BYTES = SHEET_CELL_GROUPS * frame.SCREEN_GROUP_BYTES
SHEET_COLUMNS = frame.SCREEN_ROW_BYTES // SHEET_CELL_BYTES
SHEET_CELL_ROWS = 64                 # the tallest record in SPRITES.cru (out/assets/manifest.txt)
SHEET_ROWS = SCREEN_HEIGHT // SHEET_CELL_ROWS
SHEET_PER_CLASS = SHEET_COLUMNS * SHEET_ROWS // frame.SPRITE_WIDTH_CLASSES
SHEET_BLITTERS = ("g_sprite_blit_w16", "g_sprite_blit_w32", "g_sprite_blit_w48", "g_sprite_blit_w64")
SHEET_SHIFT = 0                      # every cell starts on a group boundary, so no sub-word rotate

# `SPRITES.cru`'s 20-byte directory record (../notes/gameplay.md §3.2). The pointer is ABSOLUTE in
# the post-load image: `init_load_assets` @ 0x112c2 relocated all 256 of them.
SPRITE_REC_DATA = 0
SPRITE_REC_CLASS = 4
SPRITE_REC_ROWS = 6

# ---- the title picture ---------------------------------------------------------------------------
#
# `init_load_assets` copies TITLE_COPY_BYTES from the START of A\FLY_SHK.NEO to Physbase - 0x80, so
# the NEOchrome header lands just below the screen and the pixels land on it (../names.txt @
# 0x11212). The palette is at the header's own +4 — the address the game hands XBIOS Setpalette.
NEO_HEADER_PALETTE = 4

_LONG = 4


def _u32(image, at):
    return int.from_bytes(image[at:at + _LONG], "big")


def _u16(image, at):
    return int.from_bytes(image[at:at + 2], "big")


# ==================================================================================================
# The candidate: binding its glue, and running a segment of the frame loop on an image
# ==================================================================================================

def _bind_glue():
    """Declare every glue this file calls, so ctypes cannot pass a 64-bit pointer as an `int`.

    `abi.declare_glue` is the batteries' own declaration, used here for the same reason: an image
    pointer truncated to 32 bits would be a segmentation fault at best and a picture of the wrong
    megabyte at worst.
    """
    abi.declare_glue(GLUE_FRAME_LOOP, ARM_THE_CHEAT)
    # a0 = sprite data, a1 = screen, d6 = x & 0xf, d7 = rows - 1 (src/sprite.c's glue comment)
    abi.declare_glue(*SHEET_BLITTERS, args=4)


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
# Staging: the boot chain, a new game, and a started level — all of it the original's own code
# ==================================================================================================

def _started_level_image(post_new_game):
    """Level 1 STARTED: `conftest.started_level`, stopped before `start_level`'s tail call.

    The same builder `recreate/test/`'s own frame cases stage on, at this file's own stop: the run
    follows `init_stage_state` @ 0x1139a through `difficulty_apply_fire_rates` into `start_level`
    @ 0x11440, which loads the level's five files, re-derives the map cursor, blacks the palette,
    prescrolls a whole screen of terrain and installs the in-play palette. Stopping at 0x1156a is
    what leaves the tune out: a picture wants the started level, not the music.
    """
    return conftest.started_level(post_new_game, loads=LEVEL_ASSET_LOADS,
                                  stop_pc=STOP_AFTER_SET_PALETTE_GAME)


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
# Playing the level with the verified cores
# ==================================================================================================

def _joystick_at(frame_number):
    """The `joy1_state` byte JOYSTICK_SCRIPT holds at this frame; the last row runs out the game."""
    at = frame_number
    for length, bits in JOYSTICK_SCRIPT:
        if length == 0 or at < length:
            return bits
        at -= length
    return JOYSTICK_SCRIPT[-1][1]


def _run_frame(image, frame_number):
    """One whole pass of `main`'s loop over `image`, and the screen base it published.

    Returns (image, published_base). The base is read out of `A_screen_draw` BEFORE the call, which
    is where `render_frame` finds it: that routine's LAST act is `advance_scroll`, moving the
    pointer on to the next frame's screen and leaving the published one in `A_screen_prev1` — so the
    two are checked against each other afterwards rather than either being trusted. Nothing else in
    the loop writes `A_screen_draw`.
    """
    image[player.A_joy1_state] = _joystick_at(frame_number)
    image[frame.A_VBL_TICK:frame.A_VBL_TICK + _LONG] = FRAME_VBL_BUDGET.to_bytes(_LONG, "big")

    buf = harness.candidate_image(image)
    harness.arm_candidate()
    published = _u32(bytes(buf[frame.A_SCREEN_DRAW:frame.A_SCREEN_DRAW + _LONG]), 0)
    getattr(LIB, GLUE_FRAME_LOOP)(buf)

    publications = _setscreen_publications()
    assert publications == 1, (
        f"frame {frame_number}: the loop published {publications} screen bases and a frame publishes "
        f"exactly one — either render_frame took its prescroll arm, or something else flipped")
    image = bytearray(buf)
    mode = image[player.A_player + player.PLAYER_MODE]
    assert mode in FLYING_MODES, (
        f"frame {frame_number}: the plane left the modes this run can play — mode {mode:#x}, and "
        f"the death and game-over arms both end in a routine no subsystem has ported "
        f"(ARM_THE_CHEAT is what is meant to keep them out of reach)")
    assert _u32(image, frame.A_SCREEN_PREV1) == published, (
        f"frame {frame_number}: render_frame published {published:#x} and left "
        f"{_u32(image, frame.A_SCREEN_PREV1):#x} in A_screen_prev1 — this picture would be of a "
        f"buffer the frame did not put on screen")
    return image, published


def _live_display_records(image):
    """How many of the 223 six-byte display records are live — the census a picture searches for."""
    return sum(1 for record in range(frame.A_DISPLAY_LIST, frame.A_DISPLAY_LIST_END,
                                     frame.DISPLAY_REC_BYTES)
               if image[record + frame.DISPLAY_REC_ACTIVE] != frame.DISPLAY_ACTIVE_HIDDEN)


class Playthrough:
    """One run of the level, played forward by the verified cores and photographed as it goes.

    Frames are only ever played FORWARD, so the pictures below come out of one continuous game
    rather than out of several independent runs that each replayed the staging.
    """

    def __init__(self, started):
        self.image = bytearray(started)
        self.frame_number = 0
        self.published = None
        buf = harness.candidate_image(self.image)
        harness.arm_candidate()
        getattr(LIB, ARM_THE_CHEAT)(buf)
        self.image = bytearray(buf)
        assert self.image[player.A_invuln_flag] != 0, (
            f"{ARM_THE_CHEAT} did not leave the invulnerability flag set, so this run would play on "
            f"past the plane's death")

    def step(self):
        self.image, self.published = _run_frame(self.image, self.frame_number)
        self.frame_number += 1

    def play_to(self, target_frame):
        assert target_frame >= self.frame_number, (
            f"frame {target_frame} is behind this playthrough's frame {self.frame_number} — the "
            f"pictures are taken in the order they are played")
        while self.frame_number < target_frame:
            self.step()
        return self

    def play_until(self, live_records):
        """Play on until the display list carries `live_records`, and refuse a floor already met."""
        assert _live_display_records(self.image) < live_records, (
            f"frame {self.frame_number} already has {_live_display_records(self.image)} live display "
            f"records, so a floor of {live_records} says nothing about the picture it selects")
        while self.frame_number < PLAY_FRAMES:
            self.step()
            if _live_display_records(self.image) >= live_records:
                return self
        raise AssertionError(
            f"{PLAY_FRAMES} frames of the joystick script never reached {live_records} live display "
            f"records (the most was {_live_display_records(self.image)}) — either the floor is too "
            f"high for this run or the run stopped producing enemies")


# ==================================================================================================
# The sprite sheet
# ==================================================================================================

def _sprite_records(image):
    """(id, class, rows, data) for every SPRITES.cru record that has pixels, in the game's own order.

    The directory is read out of the RELOCATED image, so a record's pointer is the absolute address
    `render_frame` would hand a blitter. Records with no rows are hit-box-only (out/assets/README).
    """
    records = []
    for index in range(conftest.SPRITE_RECORDS):
        record = conftest.A_sprite_bank + index * conftest.SPRITE_RECORD_BYTES
        rows = _u16(image, record + SPRITE_REC_ROWS)
        if rows:
            records.append((index, _u16(image, record + SPRITE_REC_CLASS), rows,
                            _u32(image, record + SPRITE_REC_DATA)))
    return records


def _sheet_selection(image):
    """SHEET_PER_CLASS records of each width class, so all four unclipped blitters draw something.

    The first of each class that fits a cell, in the game's own record order — a rule rather than a
    hand-picked list, so the sheet cannot quietly become a picture of records this script preferred.
    """
    records = _sprite_records(image)
    chosen = []
    for width_class in range(frame.SPRITE_WIDTH_CLASSES):
        of_class = [record for record in records
                    if record[1] == width_class and record[2] <= SHEET_CELL_ROWS]
        assert len(of_class) >= SHEET_PER_CLASS, (
            f"width class {width_class} has only {len(of_class)} records that fit a "
            f"{SHEET_CELL_ROWS}-row cell and the sheet wants {SHEET_PER_CLASS}")
        chosen.extend(of_class[:SHEET_PER_CLASS])
    return chosen


def _sprite_sheet(started, base):
    """Every cell drawn by the reconstruction's own masked blitter, onto a screen cleared here.

    The clearing is this script's — a sheet is a canvas, not a frame the game ever drew — and it is
    the only thing on this picture that the reconstruction did not put there.
    """
    image = bytearray(started)
    image[base:base + frame.SCREEN_ROW_BYTES * SCREEN_HEIGHT] = bytes(
        frame.SCREEN_ROW_BYTES * SCREEN_HEIGHT)
    selection = _sheet_selection(image)

    buf = harness.candidate_image(image)
    harness.arm_candidate()
    for cell, (_index, width_class, rows, data) in enumerate(selection):
        column, row = cell % SHEET_COLUMNS, cell // SHEET_COLUMNS
        assert row < SHEET_ROWS, f"cell {cell} falls off the bottom of the sheet"
        destination = (base + row * SHEET_CELL_ROWS * frame.SCREEN_ROW_BYTES
                       + column * SHEET_CELL_BYTES)
        getattr(LIB, SHEET_BLITTERS[width_class])(buf, data, destination, SHEET_SHIFT, rows - 1)
    print(f"  sheet: {', '.join(f'#{index} (class {klass})' for index, klass, _r, _d in selection)}")
    return bytearray(buf)


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


def render_everything():
    """Every picture, in one continuous playthrough. Returns {name: PNG bytes}."""
    OUT.mkdir(parents=True, exist_ok=True)
    print("staging: boot chain -> new game -> start_level (the original, under the oracle)")
    post_load = conftest.post_load()
    started = _started_level_image(conftest.post_new_game(post_load))
    palette = _in_play_palette(started)

    pictures = [_title(post_load)]
    print("playing level 1 with the verified cores (one g_frame_loop_once a frame)")
    play = Playthrough(started)
    for name, reach in (("level1-takeoff", lambda: play.play_to(TAKEOFF_FRAME)),
                        ("level1-busy", lambda: play.play_until(BUSY_RECORDS)),
                        ("level1-crowded", lambda: play.play_until(CROWDED_RECORDS))):
        reach()
        print(f"  frame {play.frame_number}: {_live_display_records(play.image)} live records")
        pictures.append(_screen(name, play.image, play.published, palette))

    print("drawing the sprite sheet with the four masked blitters")
    ring_slot_0 = _u32(started, frame.A_SCREEN_RING)
    pictures.append(_screen("sprites", _sprite_sheet(started, ring_slot_0), ring_slot_0, palette))
    return dict(pictures)


# The pictures the two READMEs embed, copied into the tracked folder every other game in this
# workspace keeps its README images in. The rest of `out/readme/` stays where it is written.
TRACKED_PICTURES = ("title", "level1-takeoff", "level1-busy", "level1-crowded", "sprites")


def main():
    first = render_everything()
    print("re-rendering the whole set to prove it is a function of the game files alone")
    second = render_everything()
    for name, png in first.items():
        assert second[name] == png, (
            f"{name}.png differs between two runs of this script, so something on the path reads a "
            f"clock, a random source or leftover state — the set is not reproducible")

    TRACKED.mkdir(parents=True, exist_ok=True)
    for name in TRACKED_PICTURES:
        shutil.copyfile(OUT / f"{name}.png", TRACKED / f"{name}.png")
        print(f"  tracked {(TRACKED / f'{name}.png').relative_to(WORKSPACE)}")


_bind_glue()

if __name__ == "__main__":
    main()
