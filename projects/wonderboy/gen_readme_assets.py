#!/usr/bin/env python3
"""Render the workspace README's Wonder Boy images straight from the verified C reconstruction.

Every picture here is *drawn by the reconstruction*, not screenshotted from the original
program. `../../tools/recreate_kit` loads and relocates your own `bin/disk1/AUTO/SWB.PRG`
into the flat image the differential harness uses, and this script then drives the very same
entry points `recreate/test/` drives through ctypes — `src/boot.c`'s four composed boot
slices and `src/game.c`'s `game_main_loop` — and de-interleaves the Atari low-res framebuffer
they paint, with the game's own palette words, into a PNG.

EVERY PLAY PICTURE RUNS THE WHOLE BOOT CHAIN, in the boot's own order, and that is not
thoroughness for its own sake: the status panel's ARTWORK is drawn by no routine in the game.
It is part of the credits picture, which `boot_credits_screen` copies down onto the buffer the
shifter is showing; `boot_load_stage` fills scroll buffers and touches no screen, and the first
frame paints the play window over the middle. A stage booted without the two slices above it
therefore shows the panel's counters over nothing, which looks plausible and is wrong — the
first published version of this set did exactly that. `_assert_the_screens_are_the_originals`
is what stops it recurring: both buffers are compared against the shipped 1989 binary's own
post-boot RAM.

Nothing here needs Hatari or a TOS ROM: the game's resources arrive through the kit's
FILE-LOAD SEAM (`disk_read_file` over the staged-file model, TRAP_MODEL.md's Phase 9) instead
of through the WD1772 driver, and the two vertical-blank waits inside `flip_screen` are
answered by the kit's SCHEDULED-WRITE model (Phase 8) rather than by an interrupt. It does
need YOUR OWN copy of the game under `bin/` — the AUTHENTIC `disk2/`, not the repaired
hybrid — and a built candidate; no game code or data is distributed with this repository.

Output goes to the tracked `<workspace>/assets/wonderboy/*.png`, and every run is
byte-identical: the whole set is a function of `SWB.PRG`, the game's own resource files, one
fixed joystick script and one fixed pseudo-random sequence, and nothing reads a clock. That
last one is the game's only entropy: `rng_next` and `bcd_add_random_1_to_4` read the shifter's
video address counter ($ff8207/$ff8209), which on a machine is a clock and which the kit's
seeded hardware model answers with whatever the run DECLARES — so each play frame here declares
a new byte of `video_counter_for`'s fixed sequence rather than one constant for the whole run.
THAT THE SET IS STILL REPRODUCIBLE IS ASSERTED AND NOT CLAIMED: `main` renders the whole set
TWICE and refuses a picture whose two renderings differ, which the run is quick enough (a
second or two) to afford. Re-run:

    cd recreate && make venv && make   # once: the venv and libwonderboy.so
    ./.venv/bin/python ../gen_readme_assets.py
"""
import collections
import ctypes
import functools
import hashlib
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RECREATE = HERE / "recreate"
BIN = HERE / "bin"
sys.path.insert(0, str(WORKSPACE / "tools"))     # write_png
sys.path.insert(0, str(RECREATE / "test"))       # harness.py — binds the kit and loads the .so

import harness                     # noqa: E402  loads SWB.PRG into the image, opens libwonderboy.so
import leaf                        # noqa: E402  entry lookup + the ctypes binding the tests use
import emu                         # noqa: E402  the oracle's schedule encoder (harness put it on
                                   #             sys.path); no oracle is RUN here
from layout import wb              # noqa: E402  the C headers' #defines, scraped
from test_boot import seam_pokes, STAGING_CAPACITY   # noqa: E402  the seam's staging, stated once
from test_sound import PLAY_SONG_MIXER, PSG_REG_MIXER  # noqa: E402  what the tune reads back
from extract_graphics import write_png             # noqa: E402

# The kit's per-run seeders are private to `recreate_kit.harness` — `differential()` is what
# normally calls them, and nothing here runs a differential. Imported rather than re-implemented so
# a candidate here is seeded exactly as one under `make test` is.
from recreate_kit.harness import (_seed_candidate_hw, _seed_candidate_psg,   # noqa: E402
                                  _seed_candidate_sched)

OUT = WORKSPACE / "assets" / "wonderboy"

# ---- the ST low-res framebuffer ------------------------------------------------------------------
SCREEN_WIDTH, SCREEN_HEIGHT = 320, 200
SCREEN_ROW_BYTES = 0xa0        # one scanline: 20 cells of four bitplane words
CELL_PIXELS = 16               # pixels per cell...
CELL_BYTES = 8                 # ...and its four plane words
PLANES = wb("PLANES")
PALETTE_COLOURS = wb("PALETTE_COLOURS")
PALETTE_CHANNEL_MAX = 7        # the ST's $0RGB word: three bits a channel

# ---- the game's own addresses (include/wonderboy.h, through layout.py) ---------------------------
SCREEN_LOW = wb("SCREEN_LOW")
SCREEN_HIGH = wb("SCREEN_HIGH")
SCREEN_FRONT = wb("SCREEN_FRONT")
SCREEN_BACK = wb("SCREEN_BACK")
TITLE_DEPACK_DEST = wb("TITLE_DEPACK_DEST")
CREDITS_DEPACK_DEST = wb("CREDITS_DEPACK_DEST")
PICTURE_PALETTE_OFF = wb("RAD_PICTURE_PALETTE_OFF")
PALETTE_TABLE = wb("PALETTE_TABLE")
PALETTE_ROW_SHIFT = wb("PALETTE_ROW_SHIFT")
STAGE_START_PTR = wb("STAGE_START_PTR")
START_PALETTE = wb("START_PALETTE")
START_FOLLOW_X = wb("START_FOLLOW_X")
STAGE_NUMBER = wb("STAGE_NUMBER")
SPRITE_CRU_LOAD = wb("SPRITE_CRU_LOAD")
LEVEL_SEQ_INDEX = wb("LEVEL_SEQ_INDEX")
FIRST_SEQUENCE_ROW = 0           # what game_restart_reset leaves the cursor at
LEVEL_SEQ_TABLE = wb("LEVEL_SEQ_TABLE")
LEVEL_SEQ_RECORD_BYTES = wb("LEVEL_SEQ_RECORD_BYTES")
LEVEL_SEQ_OVERLAY = wb("LEVEL_SEQ_OVERLAY")
LEVEL_SEQ_SECOND_LOAD = wb("LEVEL_SEQ_SECOND_LOAD")
LIFE_RESTART_ENTRY_C26 = wb("LIFE_RESTART_ENTRY_C26")
RESOURCE_FILE_TABLE = wb("RESOURCE_FILE_TABLE")
RESOURCE_FILE_ROW_BYTES = 1 << wb("RESOURCE_FILE_ROW_SHIFT")
RESOURCE_FIRST_OVERLAY = wb("RESOURCE_FIRST_OVERLAY")
JOY1_STATE = wb("JOY1_STATE")
KEY_LAST_SCANCODE = wb("KEY_LAST_SCANCODE")
KEY_SEQUENCE_SCANCODES = wb("KEY_SEQUENCE_SCANCODES")
KEY_SCANCODE_N = wb("KEY_SCANCODE_N")
VBL_COUNTER = wb("VBL_COUNTER")
VBL_COUNTER_READY = wb("VBL_COUNTER_READY")
FLIP_READY_WAIT_PC = wb("FLIP_READY_WAIT_PC")
FLIP_TICK_WAIT_PC = wb("FLIP_TICK_WAIT_PC")
TILE_INDEX_TABLE = wb("TILE_INDEX_TABLE")
ACTOR_SCREEN_RECORDS = wb("ACTOR_SCREEN_RECORDS")
ACTOR_SCREEN_RECORD_BYTES = wb("ACTOR_SCREEN_RECORD_BYTES")
ACTOR_SCREEN_RECORD_COUNT = wb("ACTOR_SCREEN_RECORD_COUNT")
ACTOR_SPRITE_HIDDEN = wb("ACTOR_SPRITE_HIDDEN")
RESOURCE_HEADER = wb("RESOURCE_HEADER")
RESOURCE_TABLE = wb("RESOURCE_TABLE")
RESOURCE_RECORD_BYTES = wb("RESOURCE_RECORD_BYTES")
SPRITE_CRU_FIRST_DESC = wb("SPRITE_CRU_FIRST_DESC")
SPRITE_CRU_UNMARKED = wb("SPRITE_CRU_UNMARKED")
SPRITE_CRU_GROUPS = wb("SPRITE_CRU_GROUPS")
SPRITE_CRU_GROUP_SLOTS = wb("SPRITE_CRU_GROUP_SLOTS")
SPRITE_CRU_FILE_HEADER = wb("SPRITE_CRU_FILE_HEADER")
SPRITE_CRU_DESC_COPIER = wb("SPRITE_CRU_DESC_COPIER")
SPRITE_CRU_DESC_COUNT = wb("SPRITE_CRU_DESC_COUNT")
SPRITE_CRU_INSTALLED = wb("SPRITE_CRU_INSTALLED")
# The four cell copiers, by the selector byte that picks them: how many words each moves per cell.
SPRITE_CRU_COPIER_WORDS = (wb("SPRITE_CRU_WORDS_5"), wb("SPRITE_CRU_WORDS_10"),
                           wb("SPRITE_CRU_WORDS_15"), wb("SPRITE_CRU_WORDS_20"))
STAGE_SECOND_LOAD_FLAG = wb("STAGE_SECOND_LOAD_FLAG")
STAGE_NUMBER_BCD_LIMIT = wb("STAGE_NUMBER_BCD_LIMIT")
BG_BUFFER_BASE = wb("BG_BUFFER_BASE")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
OVERLAY_DEPACK_DEST = wb("OVERLAY_DEPACK_DEST")
TILE_BITMAPS = wb("TILE_BITMAPS")
TEXT_BOX_ACTIVE = wb("TEXT_BOX_ACTIVE")
TEXT_BOX_ACTIVE_SET = wb("TEXT_BOX_ACTIVE_SET")
TEXT_REQUEST = wb("TEXT_REQUEST")
TEXT_BUFFER = wb("TEXT_BUFFER")
TEXT_BUFFER_LEN = wb("TEXT_BUFFER_LEN")
TEXT_MESSAGE_TABLE = wb("TEXT_MESSAGE_TABLE")
TEXT_MESSAGE_PTR_SHIFT = wb("TEXT_MESSAGE_PTR_SHIFT")
# The message every stage entry posts. include/wonderboy.h names the ids whose text a reconstructed
# routine needed, and this is not one of them — it is simply the FIRST entry of the table, which is
# what `WB_TEXT_MESSAGE_FIRST_ID` is the base of. `_assert_the_stage_entry_box` reads the
# string back out of the table rather than trusting this line.
TEXT_MESSAGE_LETS_GO = wb("TEXT_MESSAGE_FIRST_ID")
TEXT_MESSAGE_FIRST_ID = wb("TEXT_MESSAGE_FIRST_ID")
LETS_GO_TEXT = b"Let's go."
SCREEN_LINE = wb("SCREEN_LINE")
SCREEN_BYTES = wb("SCREEN_BYTES")
BG_BLIT_SCREEN_ORIGIN = wb("BG_BLIT_SCREEN_ORIGIN")
BG_BLIT_SCANLINES = wb("BG_BLIT_SCANLINES")
BG_BLIT_ROW_BYTES = wb("BG_BLIT_ROW_BYTES")

# THE ORIGINAL'S OWN POST-BOOT RAM, if this checkout has it: `atari/original.py dump` drives the
# shipped 1989 binary under Hatari to `$f8b4` — the instruction `boot_load_stage` returns to, which
# is exactly where the chain below stops — and writes [$3f8, $80000) out. It is a build artefact of
# the user's own machine (`atari/build/` is gitignored), so the pin that uses it says so and stands
# down when it is absent rather than refusing to render.
ORIGINAL_RAM = RECREATE / "atari" / "build" / "ORIGRAM.BIN"
ORIGINAL_RAM_BASE = 0x3f8        # ../recreate/project.toml's load base, which is the dump's own
ACTOR_SCREEN_SPRITE = wb("ACTOR_SCREEN_SPRITE")
ACTOR_FOLLOWED_DEFAULT = wb("ACTOR_FOLLOWED_DEFAULT")
ACTOR_SPRITE = wb("ACTOR_SPRITE")
SPRITE_DESC_X_OFFSET = wb("SPRITE_DESC_X_OFFSET")
SPRITE_DESC_Y_OFFSET = wb("SPRITE_DESC_Y_OFFSET")
SPRITE_DESC_HEIGHT = wb("SPRITE_DESC_HEIGHT")
SPRITE_RIGHT_CLIP_X = wb("SPRITE_RIGHT_CLIP_X")
SPRITE_LAST_ROW = wb("SPRITE_LAST_ROW")
BLIT_SCRATCH_REGS = wb("BLIT_SCRATCH_REGS")
KEY_SEQUENCE_MATCHED = wb("KEY_SEQUENCE_MATCHED")
KEY_SEQUENCE_MATCHED_SET = wb("KEY_SEQUENCE_MATCHED_SET")
KEY_SEQUENCE_TERMINATOR = wb("KEY_SEQUENCE_TERMINATOR")

# The three pictures' palette rows sit INSIDE the depacked picture, WB_RAD_PICTURE_PALETTE_OFF into
# the prefix the buffer is aimed below. include/wonderboy.h derives WB_TITLE_PALETTE_SRC and
# WB_CREDITS_PALETTE_SRC exactly this way (and WB_PROMPT_PALETTE_SRC is spelt as the credits pair,
# because both inflate into WB_SCREEN_HIGH); layout.py scrapes plain integers only, so a derived
# #define is out of its reach and the arithmetic is repeated here rather than hard-coded.
TITLE_PALETTE_SRC = TITLE_DEPACK_DEST + PICTURE_PALETTE_OFF
CREDITS_PALETTE_SRC = CREDITS_DEPACK_DEST + PICTURE_PALETTE_OFF
PROMPT_PALETTE_SRC = CREDITS_PALETTE_SRC

# ---- the boot slices' own file names -------------------------------------------------------------
# `CREDITS .RAD` and `SPRITES .CRU` carry the FAT12 space padding the game's own resource table
# holds, because that is the twelve bytes `load_resource_by_index` hands the seam (src/boot.c).
TITLE_FILE = "TITLESCR.RAD"
CREDITS_FILE = "CREDITS .RAD"
PROMPT_FILE = "DATADISK.RAD"
TILEDATA_FILE = "TILEDATA.RAD"
SPRITES_FILE = "SPRITES .CRU"
DISK1 = BIN / "disk1"
# THE AUTHENTIC DUMP, not `disk2_repaired`. Four of its overlays are damaged on the pressed disk
# (OVALAY4B/5B/6A/9A — projects/wonderboy/README.md); no picture below loads one, and
# `_assert_overlay_is_undamaged` is what keeps that true rather than merely intended.
DISK2 = BIN / "disk2"
DAMAGED_OVERLAYS = ("OVALAY4B.RAD", "OVALAY5B.RAD", "OVALAY6A.RAD", "OVALAY9A.RAD")

# ---- what the slices report (include/wonderboy.h) -------------------------------------------------
LOAD_OK = wb("LOAD_OK")
LOAD_COPYLOCK_RAN = wb("LOAD_COPYLOCK_RAN")
KEY_ACTIONS_RETURNED = wb("KEY_ACTIONS_RETURNED")
KEY_ACTIONS_LEVEL_SKIP = wb("KEY_ACTIONS_LEVEL_SKIP")

# ---- the joystick, as the IKBD reports it ---------------------------------------------------------
JOY_LEFT = 1 << wb("JOY1_LEFT_BIT")
JOY_RIGHT = 1 << wb("JOY1_RIGHT_BIT")
JOY_UP = 1 << wb("JOY1_UP_BIT")          # ...which is also the JUMP, on its rising edge
JOY_FIRE = 1 << wb("JOY1_FIRE_BIT")

# THE ONE JOYSTICK SCRIPT every play frame below is driven from, and it is fixed rather than seeded
# from a generator: walk the way the loaded stage runs (`_walk_direction`), jump on a fixed beat, and
# press fire on another. A rising edge is what the game acts on (`joy1_newly_pressed`), so each press
# is held for JUMP_HELD_FRAMES and then released. The two periods are coprime with each other, so no
# picture lands on the same phase of both.
JUMP_PERIOD, JUMP_PHASE, JUMP_HELD_FRAMES = 16, 4, 2
FIRE_PERIOD, FIRE_PHASE = 23, 7


def joystick_for(frame, walk):
    """The byte the IKBD would have left in WB_JOY1_STATE on `frame` of the script above, with
    `walk` (JOY_LEFT or JOY_RIGHT) held all the way through."""
    byte = walk
    if JUMP_PHASE <= frame % JUMP_PERIOD < JUMP_PHASE + JUMP_HELD_FRAMES:
        byte |= JOY_UP
    if frame % FIRE_PERIOD == FIRE_PHASE:
        byte |= JOY_FIRE
    return byte


# WHICH FRAME OF A PLAY RUN IS SHOWN — chosen by WHAT IT SHOWS and not by a number typed here.
# `_play_to_a_busy_frame` walks the script and stops on the first frame of this window with at least
# a picture's own minimum of sprites whole inside the play window, and refuses if the window runs
# out; so a caption that names creatures cannot go stale under a reconstruction fix that shifts the
# run, and a picture cannot quietly come out as background and a hero.
#
# THE WINDOW'S TWO ENDS ARE BOTH MEASURED. Before PLAY_WINDOW_FIRST the stage has not scrolled far
# enough for anything but the hero to be on screen — every stage here reaches its first busy frame
# after it. PLAY_WINDOW_LAST is short of the earliest frame at which a run of this script ends
# (stage 2's hero loses a life at frame 869), because an ending is a different picture and
# `_step` refuses one.
PLAY_WINDOW_FIRST, PLAY_WINDOW_LAST = 100, 800
STAGE1_WALK_SPRITES = 3          # what stage 1's walking picture must have in it

# ---- the later stages, reached through the game's own level-skip cheat ---------------------------
# The run boots the row BEFORE each of these and then types the cheat, so both overlays are staged
# and `_assert_overlay_is_undamaged` checks both. Five different overlays and five scenes that look
# nothing alike — open sky over brick platforms, a wood, a vine shaft underground, a spiked brick
# corridor and a run over lava.
#
# AND CHOSEN AMONG THE ROUNDS THE SKIP CAN ACTUALLY SHOW, which is `_assert_the_hero_is_installed`'s
# note: rounds 2, 3, 10 and 11 do not mark the frames of an unarmoured hero, so a cheat that arrives
# there with a round-1 hero draws him as noise. The town of round 2 and the golden keep of round 11
# were in this set until that was found, and both were wrong in exactly that way.
#
# `sprites` is the minimum the picture's caption is allowed to describe — the frame chosen is the
# first in the window that has at least that many — and `entry_box` is whether this row's entry
# posts a message box, which three of the five do.
_Stage = collections.namedtuple("_Stage", "row name sprites entry_box")
# The one thing checked on the way past rather than photographed: that entry message box, which
# lives WB_TEXT_LIFETIME_DEFAULT (50) frames and is therefore long gone by the frame a picture is
# taken on. Measured: where there is a box it is up over frames 0..49 exactly, so 30 is inside it
# with room either side and far enough in for the hero to have moved.
STAGE_ENTRY_BOX_FRAME = 30

# ---- the sprite sheet ----------------------------------------------------------------------------
# Where each sprite is put on the blank screen — and THE GRID IS NOT WHERE THE SPRITES LAND, which is
# why the rows start negative. A record's x and y are only half of a sprite's position: the pass adds
# the DESCRIPTOR's own WB_SPRITE_DESC_X_OFFSET and _Y_OFFSET, which for this cast are +15..+30 and
# +40..+48. So a grid laid out at face value puts its bottom row past WB_SPRITE_LAST_ROW, where the
# pass drops the record — measured, as a silently empty row — and its right-hand column past
# WB_SPRITE_RIGHT_CLIP_X, where the pass would pick a clipping table instead of the MID one that
# draws a sprite whole. `_assert_the_slot_draws_whole` is what holds these numbers honest.
SHEET_COLUMNS = (0, 48, 96, 144)
SHEET_ROWS = (-38, -8, 22, 52, 82)
SHEET_STAGE_ROW = 0              # the cast is stage 1's, which is the stage the other pictures show
# How long the run that CHOOSES the cast is let play. Longer than the walking picture's frame, and
# measured: over this many frames stage 1 puts more distinct sprites on the screen than the sheet has
# slots, which is what `render_sprite_sheet`'s own assertion requires.
SHEET_SCAN_FRAMES = 240


def _u16(image, addr):
    return struct.unpack_from(">H", image, addr)[0]


def _u32(image, addr):
    return struct.unpack_from(">I", image, addr)[0]


@functools.lru_cache(maxsize=None)
def _bind(name, extra_args=(), returns=True):
    """One candidate entry point, bound exactly as recreate/test/ binds it: the flat image as a
    ctypes buffer, then whatever else the routine takes.

    `returns` says the routine really does hand a longword back. Declaring one it does not have
    would let a later `assert` read a stale register and call it a result, so the `void` ones are
    bound as `void` rather than checked and ignored."""
    return leaf.bind(name, leaf.IMAGE_ARG + list(extra_args),
                     ctypes.c_uint32 if returns else None)


class _BlitRegs(ctypes.Structure):
    """include/blit.h's `sprite_blit_regs` — the 68000 registers a blitter reads and leaves."""
    _fields_ = [("scratch", ctypes.c_uint32 * BLIT_SCRATCH_REGS),
                ("shift", ctypes.c_uint32), ("rows", ctypes.c_uint32),
                ("source", ctypes.c_uint32), ("dest", ctypes.c_uint32),
                ("unwind", ctypes.c_uint32)]


class _PassRegs(ctypes.Structure):
    """...and `sprite_pass_regs`, which is game_main_loop's one argument."""
    _fields_ = [("blit", _BlitRegs), ("record", ctypes.c_uint32),
                ("descriptor", ctypes.c_uint32), ("blitter", ctypes.c_uint32)]


# THE TWO WAITS INSIDE `flip_screen`, DECLARED. $6aa spins until WB_VBL_COUNTER reaches
# WB_VBL_COUNTER_READY and $6d0 until it differs from a copy taken an instruction earlier; nothing
# in the routine raises that word — `vbl_handler` does, fifty times a second — so off target the
# kit's scheduled-write model stands in for the interrupt. One store per site releases each wait on
# its first poll, which is the shape test_game.py's own flip cases use.
FLIP_SCHEDULE = ({"pc": FLIP_READY_WAIT_PC, "nth": 1, "addr": VBL_COUNTER,
                  "width": 2, "value": VBL_COUNTER_READY},
                 {"pc": FLIP_TICK_WAIT_PC, "nth": 1, "addr": VBL_COUNTER,
                  "width": 2, "value": VBL_COUNTER_READY + 1})
FLIP_WAIT_SITES = (FLIP_READY_WAIT_PC, FLIP_TICK_WAIT_PC)
_FLIP_ENTRIES = emu.schedule_entries(list(FLIP_SCHEDULE))


# ---- THE ENTROPY, DECLARED PER FRAME ---------------------------------------------------------------
#
# The game's only random source is a CLOCK: `rng_next` ($68c6) reads the shifter's video address
# counter at $ff8209 and `bcd_add_random_1_to_4` ($51ac) reads $ff8209 and $ff8207, and off target
# the kit's seeded-hardware model (TRAP_MODEL.md's Phase 7) answers both with whatever the run
# declared — an undeclared read is a REFUSAL, which is why a constant was declared here at all. One
# constant for a whole run is a counter that never moves, which no machine's is, so each play frame
# declares the next byte of the fixed sequence below instead. It is a function of the frame index
# and of nothing else, which is what leaves the set byte-identical run to run.
#
# WHAT THE SEQUENCE ACTUALLY MOVES IN THIS SET, measured rather than hoped for: over the frames these
# pictures are taken from, `game_main_loop` reaches `rng_next` in the KEEP alone — every other run
# ends with WB_RNG_COUNTER_A..C still at zero, so no behaviour draw was made — and reaches
# `bcd_add_random_1_to_4` wherever gold is paid, which jitters the amount. It is not why the stages
# were once empty; PLAY_WINDOW_FIRST and `_walk_direction` are.
VIDEO_COUNTER_SEED = 0x1f
# The 16-bit LCG with the full period: every seed visits all 65,536 states, so the high byte the
# frames read is not a short cycle that could beat against JUMP_PERIOD or FIRE_PERIOD.
VIDEO_COUNTER_MULTIPLIER, VIDEO_COUNTER_INCREMENT = 25173, 13849
VIDEO_COUNTER_STATES = 1 << 16
VIDEO_COUNTER_HIGH_BYTE = 8      # ...and which eight bits of a state a frame declares


@functools.lru_cache(maxsize=None)
def _video_counter_sequence():
    """The generator's whole period, built once."""
    sequence, state = [], VIDEO_COUNTER_SEED
    for _ in range(VIDEO_COUNTER_STATES):
        state = (state * VIDEO_COUNTER_MULTIPLIER + VIDEO_COUNTER_INCREMENT) % VIDEO_COUNTER_STATES
        sequence.append(state >> VIDEO_COUNTER_HIGH_BYTE)
    return tuple(sequence)


def video_counter_for(frame):
    """What $ff8207 and $ff8209 are declared to hold on `frame`. No run here is long enough to
    reach the wrap, which is there so the function is total rather than because it is used."""
    sequence = _video_counter_sequence()
    return sequence[frame % len(sequence)]


def _check_no_refused_os_calls(what):
    """Fail if the run made an `os_*` call the kit's TOS model refuses to serve.

    The differential does this after every candidate run (`harness._vet_no_os_refusal`) because a
    refusal returns a sentinel and touches neither the out-param nor the image. Nothing here goes
    through `differential()`, so without this an unstaged file, an unreleased wait or an undeclared
    hardware read would render a plausible-looking picture with a piece silently missing, and the
    script would exit 0.
    """
    refusals = harness._lib.g_os_refusal_count()
    assert refusals == 0, (
        f"{what}: the candidate made {refusals} os_* call(s) the TOS model refuses — a staged file, "
        f"a declared wait site or a seeded hardware read is missing, so the picture is missing "
        f"whatever that call would have done")


def _fresh(pokes):
    """A candidate buffer over a fresh image, with the run's models seeded.

    The three seeds are the ones every case in ../recreate/test/ that reaches this code declares:
    the video address counter both PRNGs read, the YM2149 mixer `snd_play_song` reads back, and an
    empty schedule so nothing survives from the previous picture.

    The counter is `hw_declared()`'s own default here, which is the byte the boot slices run on and
    the one the pin against the original's post-boot RAM was measured with; `_run_frame` re-declares
    it per frame once the frame loop starts.
    """
    buf = harness.candidate_image(harness.make_image(pokes))
    harness._lib.g_os_refusal_reset()
    _seed_candidate_hw(leaf.hw_declared())
    _seed_candidate_psg({PSG_REG_MIXER: PLAY_SONG_MIXER})
    _seed_candidate_sched(emu.schedule_entries([]), ())
    return buf


def _palette(image, addr):
    """PALETTE_COLOURS ST palette words (0x0RGB, three bits a channel) -> RGB triples for the PNG."""
    pens = []
    for pen in range(PALETTE_COLOURS):
        word = _u16(image, addr + pen * 2)
        pens.append(tuple(((word >> shift) & PALETTE_CHANNEL_MAX) * 255 // PALETTE_CHANNEL_MAX
                          for shift in (8, 4, 0)))
    return pens


def _decode_interleaved(image, base):
    """De-interleave the ST low-res framebuffer at `base` into rows of palette indices (0..15).

    A row is 20 cells of four bitplane words; within a cell the words are planes 0..3 and the MSB is
    the leftmost pixel, plane 0 contributing the low bit of the index.
    """
    rows = []
    for y in range(SCREEN_HEIGHT):
        row = bytearray(SCREEN_WIDTH)
        row_base = base + y * SCREEN_ROW_BYTES
        for cell in range(SCREEN_WIDTH // CELL_PIXELS):
            words = [_u16(image, row_base + cell * CELL_BYTES + plane * 2) for plane in range(PLANES)]
            for bit in range(CELL_PIXELS):
                shift = (CELL_PIXELS - 1) - bit
                index = 0
                for plane in range(PLANES):
                    index |= ((words[plane] >> shift) & 1) << plane
                row[cell * CELL_PIXELS + bit] = index
        rows.append(row)
    return rows


def _screen(name, image, base, palette_at):
    """Decode the framebuffer the reconstruction just painted and hand back (name, PNG bytes).

    The palette is read out of the IMAGE rather than out of a table here, because the palette the
    picture wants is the one the run's own `set_palette` was handed — and that write goes to a
    shifter register the loaded image does not have (include/shifter.h), so the SOURCE row is the
    only place off target where it can be read back.
    """
    path = OUT / f"{name}.png"
    write_png(str(path), SCREEN_WIDTH, SCREEN_HEIGHT,
              _decode_interleaved(image, base), _palette(image, palette_at))
    print("  wrote", path.relative_to(WORKSPACE))
    return name, path.read_bytes()


# ---------------------------------------------------------------- the boot's three pictures
#
# Each is one of src/boot.c's composed slices, run whole: the slice loads its resource across the
# file-load seam, inflates it with `rad_depack` and puts its palette row on the shifter through
# `set_palette`. The picture is what the depack left in a screen buffer.


def _resource(directory, name):
    """One resource file's bytes, found by the name the GAME asks for it by.

    The game's own table space-pads a short stem to eight characters, because that is what FAT12
    stores and what `load_resource_by_index` hands the seam — `CREDITS .RAD`, `SPRITES .CRU`. A host
    filesystem does not, so the padding is dropped here, in the one place that turns a seam name into
    a path.
    """
    return (directory / name.replace(" ", "")).read_bytes()


def _picture_pokes(directory, name):
    """The one thing a picture slice needs staged: its resource file, in the seam's model."""
    return seam_pokes([(name, _resource(directory, name))])


def render_title():
    """The title screen. `boot_title_screen` ($e512..$e550) arms the Copylock, loads TITLESCR.RAD
    through the seam, inflates it onto WB_SCREEN_LOW and starts the title tune."""
    buf = _fresh(_picture_pokes(DISK1, TITLE_FILE))
    result = _bind("boot_title_screen")(buf)
    assert result == LOAD_COPYLOCK_RAN, (
        f"boot_title_screen reported {result}, not WB_LOAD_COPYLOCK_RAN — $e51e's arming store did "
        f"not reach the load, so the slice did not run the way the boot runs it")
    _check_no_refused_os_calls("boot_title_screen")
    return _screen("title", buf, SCREEN_LOW, TITLE_PALETTE_SRC)


def render_credits():
    """The credits screen. `boot_credits_screen` ($e562..$e5a2) inflates CREDITS.RAD onto
    WB_SCREEN_HIGH, copies it down onto the buffer the shifter is showing, and starts a new game —
    which is what draws the status panel's lives over the picture."""
    buf = _fresh(_picture_pokes(DISK1, CREDITS_FILE))
    result = _bind("boot_credits_screen")(buf)
    assert result == LOAD_OK, f"boot_credits_screen reported {result}, not WB_LOAD_OK"
    _check_no_refused_os_calls("boot_credits_screen")
    return _screen("credits", buf, SCREEN_LOW, CREDITS_PALETTE_SRC)


def render_prompt():
    """The data-disk prompt. `boot_prompt_screen` ($e494..$e4d4) is the slice every one of the
    game's three `jmp $e494.l` endings lands in — ESC, the game-over box expiring, and slot 61's
    message terminator. It points the shifter at WB_SCREEN_HIGH and inflates DATADISK.RAD there."""
    buf = _fresh(_picture_pokes(DISK2, PROMPT_FILE))
    result = _bind("boot_prompt_screen")(buf)
    assert result == LOAD_OK, f"boot_prompt_screen reported {result}, not WB_LOAD_OK"
    _check_no_refused_os_calls("boot_prompt_screen")
    return _screen("prompt", buf, SCREEN_HIGH, PROMPT_PALETTE_SRC)


# ---------------------------------------------------------------- a stage, and frames of it


def _overlay_name(row):
    """The resource-table filename sequence row `row` names — read out of the game's own tables
    rather than typed here, so the script cannot disagree with the binary about which file a row
    wants."""
    ordinal = harness.BASE_IMAGE[LEVEL_SEQ_TABLE + row * LEVEL_SEQ_RECORD_BYTES + LEVEL_SEQ_OVERLAY]
    at = RESOURCE_FILE_TABLE + ((ordinal + RESOURCE_FIRST_OVERLAY) & 0xff) * RESOURCE_FILE_ROW_BYTES
    raw = bytes(harness.BASE_IMAGE[at:at + RESOURCE_FILE_ROW_BYTES])
    return raw[:raw.index(b"\x00")].decode("ascii")


def _assert_overlay_is_undamaged(name):
    assert name not in DAMAGED_OVERLAYS, (
        f"{name} is one of the four overlays the pressed data disk lost bytes from, so the picture "
        f"it produced would be an artefact of the damage rather than of the reconstruction")


@functools.lru_cache(maxsize=None)
def _sprites_cru():
    """SPRITES.CRU, read once. Every stage load below wants all of it (279,034 bytes, a size
    ../recreate/test/test_boot.py pins against the shipped file)."""
    return _resource(DISK2, SPRITES_FILE)


def _stage_files(rows):
    """The seam's file list for running the WHOLE CHAIN over `rows` — the title and credits
    pictures, each row's overlay, the tile bank, and as much of SPRITES.CRU as the model can hold
    beside them. Six files at most, against the model's eight slots.

    SPRITES.CRU DOES NOT FIT THE STAGED-FILE MODEL, which is measured rather than assumed
    (`test/test_boot_chain.py`'s `test_the_sprites_file_is_staged_as_the_prefix_the_model_can_hold`):
    the staging area is `STAGING_CAPACITY` bytes and the file is larger than all of it. So the seam
    is given the PREFIX that fits, and `_place_sprites_file` puts the whole file at the address the
    load lands on before every boot. Both halves are the shipped file's own bytes at their own
    addresses — the seam simply rewrites the head it already holds — so what the installer walks is
    the real file; what is substituted for is the READ, which is the seam's job anyway.
    """
    names = list(dict.fromkeys(_overlay_name(row) for row in rows))
    for name in names:
        _assert_overlay_is_undamaged(name)
    files = [(TITLE_FILE, _resource(DISK1, TITLE_FILE)),
             (CREDITS_FILE, _resource(DISK1, CREDITS_FILE))]
    files += [(name, _resource(DISK2, name)) for name in names]
    files.append((TILEDATA_FILE, _resource(DISK2, TILEDATA_FILE)))
    room = STAGING_CAPACITY - sum(len(data) for _, data in files)
    assert room > 0, (
        f"{len(files)} staged resources already fill the model's {STAGING_CAPACITY}-byte staging "
        f"area, so there is nothing left for SPRITES.CRU's prefix")
    files.append((SPRITES_FILE, _sprites_cru()[:room]))
    return files


def _place_sprites_file(buf):
    """Put the whole of SPRITES.CRU where the boot's own load lands it — the read the seam cannot do.

    THE STAGED-FILE MODEL CANNOT HOLD THIS FILE AND THE LIMIT IS THE KIT'S, not this project's:
    `OS_FS_TABLE`/`OS_FS_STAGING` are `tools/recreate_kit/include/os.h` constants (pinned by the
    kit's own `test_os_memory_map.py`, mirrored in `harness.py`), the area they leave below the
    stack guard is `STAGING_CAPACITY` = 258,048 bytes, and the file is 279,034 — it does not fit
    even with nothing else staged. `project.toml` has no knob for it; widening it means moving the
    table for Buggy Boy and Joust too. So the file's bytes are placed directly, and the seam serves
    the prefix that fits over the top of them — the same bytes, so what the installer walks is the
    shipped file either way.
    """
    cru = _sprites_cru()
    buf[SPRITE_CRU_LOAD:SPRITE_CRU_LOAD + len(cru)] = cru


# The bytes of a marked descriptor, read out of SPRITES.CRU itself: the offset of its cells inside
# the file's body, and how many bytes the copier its selector picks moves for its cell count. The
# INSTALLED pointer comes from the image, so `_assert_the_cells_are_the_file` compares one against
# the other with the file as the authority.
_Descriptor = collections.namedtuple("_Descriptor", "index sprite installed source cells")


def _installed_descriptors(buf):
    """Every descriptor the loaded stage's mask MARKED, as `sprites_cru_install` left it.

    `sprites_cru_install` writes WB_SPRITE_CRU_UNMARKED into every descriptor its stage's mask does
    not mark, and `resource_table_relocate` then turns each descriptor's first longword into an
    absolute pointer — so an unmarked one reads back as WB_RESOURCE_TABLE plus that constant. Asking
    the table is what makes this the STAGE's cast rather than a list chosen here.
    """
    file = _sprites_cru()
    descriptors = (SPRITE_CRU_GROUPS - 1) * SPRITE_CRU_GROUP_SLOTS + 1
    marked = []
    for index in range(descriptors):
        at = SPRITE_CRU_FIRST_DESC + index * RESOURCE_RECORD_BYTES
        installed = _u32(buf, RESOURCE_HEADER + at)
        if installed == RESOURCE_TABLE + SPRITE_CRU_UNMARKED:
            continue
        words = SPRITE_CRU_COPIER_WORDS[file[at + SPRITE_CRU_DESC_COPIER]]
        cells = (file[at + SPRITE_CRU_DESC_COUNT] + 1) * words * 2
        marked.append(_Descriptor(index,
                                  (RESOURCE_HEADER + at - RESOURCE_TABLE) // RESOURCE_RECORD_BYTES,
                                  installed, _u32(file, at), cells))
    return marked


def _assert_the_cells_are_the_file(buf, what):
    """Every marked sprite's installed cells, byte for byte against SPRITES.CRU's own bytes.

    THIS PIN EXISTS BECAUSE THE SET OF PICTURES WAS WRONG WITHOUT IT, and silently: the slice depacks
    TILEDATA.RAD onto WB_TILE_BANK ($4f000, 84,608 bytes) BEFORE it loads SPRITES.CRU, and the tile
    bank sits inside the span the raw file occupies. The seam then restores only the prefix it could
    stage, so on the first published set 28 of stage 1's 143 marked descriptors installed tile-bank
    bytes as sprite cells and nobody could tell by looking. Nothing else here compares the installed
    product against anything, so the check is stated rather than assumed.
    """
    file = _sprites_cru()
    for descriptor in _installed_descriptors(buf):
        want = file[SPRITE_CRU_FILE_HEADER + descriptor.source:
                    SPRITE_CRU_FILE_HEADER + descriptor.source + descriptor.cells]
        got = bytes(buf[descriptor.installed:descriptor.installed + descriptor.cells])
        assert got == want, (
            f"{what}: sprite {descriptor.sprite}'s {descriptor.cells} installed cell bytes at "
            f"{descriptor.installed:#x} are not SPRITES.CRU's own at file offset "
            f"{SPRITE_CRU_FILE_HEADER + descriptor.source:#x} — the raw file was damaged before "
            f"`sprites_cru_install` read it, and this stage would draw those bytes as a sprite")


def _reinstall_the_sprites(buf, what):
    """Redo the slice's sprite install over the file WHOLE, and rebuild what that costs.

    WHY IT IS NEEDED is `_assert_the_cells_are_the_file`'s note: the slice's own install reads a file
    the tile depack has holed. The original never meets this, because it reads SPRITES.CRU off the
    disk AFTER the depack and BEFORE the scroll buffers exist; the seam can only restore the prefix.

    WHY A SECOND INSTALL IS THE SAME AS A FIRST. `sprites_cru_install` reads nothing it does not
    first write: its opening act slides the file's own descriptor table down over WB_RESOURCE_HEADER
    and every later read is of that slid copy or of the file body, so over a freshly placed file and
    the same WB_STAGE_NUMBER it lays down exactly what a first install would. `resource_table_relocate`
    follows because the install leaves offsets where the sprite pass wants pointers, and its
    run-once guard is the WB_RESOURCE_RELOCATED stamp at WB_RESOURCE_HEADER — which the slide has
    just overwritten with the file's own first byte, so it runs again.

    AND WHY `stage_load_window` FOLLOWS. The raw file's span reaches WB_BG_BUFFER_BASE, so placing it
    overwrites the eight pre-shifted scroll buffers the slice has already built — in the original
    that band is still scratch at this point in the boot. Rebuilding them with the game's own builder,
    on the boot's own three operands, is the repair; requiring the rebuilt bytes to equal the ones
    the slice built is the receipt that the detour changed nothing the picture is made of.
    """
    built = bytes(buf[BG_BUFFER_BASE:SCREEN_LOW])
    _place_sprites_file(buf)
    installed = _bind("sprites_cru_install")(buf)
    assert installed == SPRITE_CRU_INSTALLED, (
        f"{what}: the second sprites_cru_install reported {installed}, not "
        f"WB_SPRITE_CRU_INSTALLED — it met a dispatch longword that is none of the four copiers")
    _bind("resource_table_relocate", returns=False)(buf)
    _bind("stage_load_window", (ctypes.c_uint32,) * 3, returns=False)(
        buf, MAP_ROW_STRIDE, OVERLAY_DEPACK_DEST, TILE_BITMAPS)
    assert bytes(buf[BG_BUFFER_BASE:SCREEN_LOW]) == built, (
        f"{what}: rebuilding the scroll buffers after the second install did not reproduce the ones "
        f"boot_load_stage built, so the detour changed something the background is made of")


def _row_loads_the_sprites(buf):
    """Whether the row the sequence is ABOUT to load will read SPRITES.CRU.

    `boot_load_stage` gates its second load on WB_STAGE_SECOND_LOAD_FLAG, which
    `stage_sequence_apply_row` takes from the row's own WB_LEVEL_SEQ_SECOND_LOAD byte — and it is a
    MAJORITY of the game's 35 rows that carry a zero there (src/boot.c). The other half of the gate,
    WB_LIFE_RESTART_ENTRY_C26, is asserted clear before every chain here, so the row byte is the
    whole answer.
    """
    row = _u16(buf, LEVEL_SEQ_INDEX)
    return harness.BASE_IMAGE[LEVEL_SEQ_TABLE + row * LEVEL_SEQ_RECORD_BYTES
                              + LEVEL_SEQ_SECOND_LOAD] != 0


def _boot_stage(buf, what, sprites_installed=False):
    """One run of `boot_load_stage` ($e5ba..$f8b4): advance the level sequence, load the row's
    overlay and the tile bank across the seam, install the tiles and (on a row that asks for them)
    the sprites, reset the actor tables and build the scroll engine's eight pre-shifted buffers.
    Answers whether this image now holds a round's installed sprite cells.

    THE RAW FILE IS PLACED ONLY FOR A LOAD THAT READS IT, and that is not tidiness: placing it
    scribbles 279,034 bytes over the region an EARLIER row's install already filled with cells, and
    a row whose WB_LEVEL_SEQ_SECOND_LOAD byte is zero installs nothing of its own to repair them
    with. Doing it unconditionally therefore left every second-area row drawing the previous round's
    sprites as raw file bytes; on the machine the file is simply not read there and the cells stand.

    `sprites_installed` carries that standing forward, so the cells are checked against the file
    after a no-install row too — the property being stated is that they are still the file's.
    """
    if _row_loads_the_sprites(buf):
        _place_sprites_file(buf)
    result = _bind("boot_load_stage")(buf)
    assert result in (LOAD_OK, LOAD_COPYLOCK_RAN), (
        f"{what}: boot_load_stage reported {result} — the seam refused one of the row's resources, "
        f"so no stage was loaded")
    _check_no_refused_os_calls(what)
    installed = sprites_installed or bool(buf[STAGE_SECOND_LOAD_FLAG])
    if buf[STAGE_SECOND_LOAD_FLAG]:
        _reinstall_the_sprites(buf, what)
    if installed:
        _assert_the_cells_are_the_file(buf, what)
    return installed


def _stage_number(buf):
    """WB_STAGE_NUMBER as the panel shows it. THE WORD IS PACKED BCD, which is not obvious and cost
    this script a wrong filename: `hud_draw_stage_number` draws the low byte's two NIBBLES, and both
    `sprites_cru_install` and the stage PRNG decode it with the `if (> 9) -= 6` a BCD tens carry
    needs. So $11 is round eleven, not seventeen."""
    packed = _u16(buf, STAGE_NUMBER) & 0xff
    tens, units = packed >> 4, packed & 0x0f
    assert tens <= STAGE_NUMBER_BCD_LIMIT and units <= STAGE_NUMBER_BCD_LIMIT, (
        f"WB_STAGE_NUMBER holds {packed:#04x}, which is not packed BCD — a nibble is above "
        f"WB_STAGE_NUMBER_BCD_LIMIT and the panel would draw a digit that does not exist")
    return tens * 10 + units


# The bytes of a screen buffer the background blit does NOT fill, which is where the status panel
# lives: `bg_scroll_blit` starts WB_BG_BLIT_SCREEN_ORIGIN into the buffer and lays
# WB_BG_BLIT_ROW_BYTES down each of WB_BG_BLIT_SCANLINES rows, so the panel is the rows above and
# below that window plus the columns left of it. Computed once — it is a property of the geometry.
def _panel_offsets():
    top_row, left_byte = divmod(BG_BLIT_SCREEN_ORIGIN, SCREEN_LINE)
    window = set()
    for row in range(top_row, top_row + BG_BLIT_SCANLINES):
        window |= set(range(row * SCREEN_LINE + left_byte,
                            row * SCREEN_LINE + left_byte + BG_BLIT_ROW_BYTES))
    return frozenset(range(SCREEN_BYTES)) - window


PANEL_OFFSETS = _panel_offsets()


def _assert_the_screens_are_the_originals(buf, what):
    """Both screen buffers, byte for byte against the ORIGINAL's own post-boot RAM.

    THIS IS WHY THE CHAIN IS RUN WHOLE, and it is the check that would have caught the set this
    script first published: the status panel's artwork — the LIFE/SCORE/HIGH/GOLD labels, the slot
    frames — is not drawn by anything in the game. It is part of the CREDITS picture, which
    `boot_credits_screen` inflates and then copies down onto the buffer the shifter is showing;
    `boot_load_stage` only fills scroll buffers, and the first frame paints the play window over the
    middle of it. Booting a stage without the two slices above it therefore leaves a panel with the
    counters on it and no artwork under them, which looks plausible and is wrong.

    The dump is `atari/original.py dump`'s: the shipped 1989 binary driven under Hatari to `$f8b4`,
    the instruction `boot_load_stage` returns to. It is a build artefact of the user's own machine,
    so this stands down when the checkout has not got one — but it does not soften: with the dump
    present the two buffers must agree with it exactly, and 0 is the measured answer.
    """
    if not ORIGINAL_RAM.is_file():
        print(f"    (no {ORIGINAL_RAM.name}: the screens are not pinned against the original's RAM)")
        return
    dump = ORIGINAL_RAM.read_bytes()
    for base, name in ((SCREEN_LOW, "WB_SCREEN_LOW"), (SCREEN_HIGH, "WB_SCREEN_HIGH")):
        ours = bytes(buf[base:base + SCREEN_BYTES])
        theirs = dump[base - ORIGINAL_RAM_BASE:base - ORIGINAL_RAM_BASE + SCREEN_BYTES]
        differing = [offset for offset in range(SCREEN_BYTES) if ours[offset] != theirs[offset]]
        assert not differing, (
            f"{what}: {len(differing)} of {SCREEN_BYTES} bytes of {name} differ from the original's "
            f"own post-boot RAM (first at {base + differing[0]:#x}), of which "
            f"{len(set(differing) & PANEL_OFFSETS)} are in the status panel — the boot chain this "
            f"picture ran did not leave the screen the original's boot leaves")
    print(f"    both screen buffers are byte-identical to {ORIGINAL_RAM.name}")


def _run_the_boot_chain(buf, what, at_row=FIRST_SEQUENCE_ROW):
    """The boot, in the original's own order and on one pair of buffers.

    `chain_prologue`'s two reconstructed steps first — `clear_palette` at $e4ea and
    `clear_both_screens` at $e4ee; its third, the screen-base publish, is a shifter write the loaded
    image does not have — then the three slices the fire waits cut the boot into. It is the same
    sequence `atari/wonderboy_main.c`'s `run_the_boot_chain` runs on the machine, which is why the
    on-target rungs and this script now draw the same panel.

    THE FIRST STAGE NEEDS NO SEEDING AT ALL, and that is the point of running the chain rather than
    the stage slice alone: `game_restart_reset`, inside the credits slice, is what puts the sequence
    cursor at its first row, so `at_row` defaults to the row the boot itself reaches and nothing
    here is written into the image. A LATER row is this script's one declared deviation — the cursor
    is put where a player who had reached that round would have left it, because the honest route
    (playing there) is not something a fixed joystick script can do. The reset is pinned first, so
    the deviation is a visible write over a known value rather than a poke into the unknown.
    """
    _bind("clear_palette")(buf)
    _bind("clear_both_screens", returns=False)(buf)
    title = _bind("boot_title_screen")(buf)
    assert title == LOAD_COPYLOCK_RAN, (
        f"{what}: boot_title_screen reported {title}, not WB_LOAD_COPYLOCK_RAN")
    credits = _bind("boot_credits_screen")(buf)
    assert credits == LOAD_OK, f"{what}: boot_credits_screen reported {credits}, not WB_LOAD_OK"
    _check_no_refused_os_calls(f"{what}: the title and credits slices")

    reset_to = _u16(buf, LEVEL_SEQ_INDEX)
    assert reset_to == FIRST_SEQUENCE_ROW, (
        f"{what}: the credits slice left WB_LEVEL_SEQ_INDEX at {reset_to}, not the "
        f"{FIRST_SEQUENCE_ROW} game_restart_reset writes — the boot no longer starts a new game")
    assert _u16(buf, LIFE_RESTART_ENTRY_C26) == 0, (
        f"{what}: WB_LIFE_RESTART_ENTRY_C26 is not clear, so the stage slice would take the "
        f"re-entry arm and load no sprites")
    if at_row != FIRST_SEQUENCE_ROW:
        struct.pack_into(">H", buf, LEVEL_SEQ_INDEX, at_row)
    return _boot_stage(buf, what)          # ...whether that row installed a round's sprite cells


def _stage_palette_src(buf):
    """Where `stage_load_window`'s `set_palette` read this stage's sixteen words: the row of
    WB_PALETTE_TABLE the loaded stage's START record names."""
    start = _u32(buf, STAGE_START_PTR)
    return PALETTE_TABLE + (buf[start + START_PALETTE] << PALETTE_ROW_SHIFT)


def _walk_direction(buf):
    """Which way the loaded stage is walked, taken from the stage's OWN START RECORD.

    THE SCRIPT USED TO HOLD RIGHT EVERYWHERE AND TWO PICTURES WERE THE PRICE. `boot_load_stage`
    latches the row's start record and drops the followed actor at its WB_START_FOLLOW_X, and two of
    the rows below start him at 1928 and 1432 — the far end of a map he is meant to walk BACK along,
    with an arrow tile on the ground saying so. Holding right there pins him against the wall for
    the whole run: measured, 1400 frames in which the hero never moved a pixel and not one creature
    was ever inside the window, because every one of them was off the LEFT edge. That is what the
    first published set's desert and castle pictures were.

    A start beyond the first screenful is the signal and it separates the two cases with room to
    spare: the rows walked rightwards start the hero at 24..88, and the two walked leftwards at 1432
    and 1928. WB_LEVEL_SEQ_SIDE is NOT the signal, though it looks like one — it is set on the keep's
    row too, which starts at 24 and is walked rightwards, and `actor_apply_stage_side` spends it on
    an actor's facing bit rather than on the map.
    """
    start = _u32(buf, STAGE_START_PTR)
    return JOY_LEFT if _u16(buf, start + START_FOLLOW_X) >= SCREEN_WIDTH else JOY_RIGHT


def _run_frame(buf, sprites, frame, joystick=0, scancode=0):
    """One lap of `game_main_loop` ($4a0), driven the way the machine drives it.

    The two bytes written first are the ones an interrupt would have left: WB_JOY1_STATE is what the
    IKBD's joystick-1 report handler stores and WB_KEY_LAST_SCANCODE what its keyboard arm stores.
    The schedule is re-installed per frame because each entry fires once, and `flip_screen` zeroes
    the counter on its way out — so every frame's two waits are the same two. The hardware seed is
    re-installed for the same reason a machine's counter has moved on: see `video_counter_for`.
    """
    buf[JOY1_STATE] = joystick
    buf[KEY_LAST_SCANCODE] = scancode
    _seed_candidate_hw(leaf.hw_declared(video_counter_for(frame)))
    _seed_candidate_sched(_FLIP_ENTRIES, FLIP_WAIT_SITES)
    return _bind("game_main_loop", (ctypes.POINTER(_PassRegs),))(buf, ctypes.byref(sprites))


def _entered_frame_loop():
    """The register file the boot chain hands `game_main_loop`, as the boot produces it.

    `sprite_draw_pass` never dereferences a5 — it only steps it back per wholly-off-left sprite — but
    the frame carries it, and it is PRODUCED rather than chosen: `bg_build_buffer`'s `lea
    $21e90.l,a5` is the one instruction in the hinge that writes the register, and its operand is
    WB_TILE_INDEX_TABLE (atari/wonderboy_main.c has the same derivation for the on-target build).
    """
    sprites = _PassRegs()
    sprites.blit.unwind = TILE_INDEX_TABLE
    return sprites


def _step(buf, sprites, frame, walk, what):
    """One lap of the frame loop on the fixed joystick script, refusing to end early.

    An ending is not a failure of the reconstruction — the loop has five of them and a run that
    presses nothing can still reach two (../include/game.h) — but it IS a different picture from the
    one the caller asked for, so it fails here with the ending named.
    """
    ending = _run_frame(buf, sprites, frame, joystick_for(frame, walk))
    assert ending == KEY_ACTIONS_RETURNED, (
        f"{what}: frame {frame} left the frame loop reporting {ending} (include/game.h's "
        f"WB_KEY_ACTIONS_* / WB_LOOP_EXIT_*), so the run no longer reaches the frame this "
        f"picture is of")


def _assert_the_hero_is_installed(buf, what):
    """The followed actor's own sprite has cells, and is not the UNMARKED sentinel.

    THIS PICTURE CLASS CAME OUT WRONG WITHOUT IT, and it looked like a rendering bug rather than a
    route one. `sprites_cru_install` writes WB_SPRITE_CRU_UNMARKED into every descriptor the ROUND's
    mask does not mark — wholesale, so a round that does not mark a sprite leaves its descriptor
    pointing at the cell area's base and the pass draws whatever is there. Rounds 2, 3, 10 and 11 do
    not mark the frames a hero WITHOUT the armour of the rounds before him uses (measured over the
    shipped mask table, rounds 1..11), and the level-skip cheat is exactly how you arrive at round 2
    with a round-1 hero: he came out as a band of scrambled bytes at his own position, in two of the
    five stage pictures this set first published.

    So this refuses that picture rather than drawing it, and the rows below are chosen among the
    rounds whose mask marks the hero the skip actually brings.
    """
    sprite = _u16(buf, ACTOR_FOLLOWED_DEFAULT + ACTOR_SPRITE)
    installed = _u32(buf, RESOURCE_TABLE + sprite * RESOURCE_RECORD_BYTES)
    assert installed != RESOURCE_TABLE + SPRITE_CRU_UNMARKED, (
        f"{what}: the hero's sprite {sprite} has no cells — this round's mask did not mark it, so "
        f"the pass would draw the unmarked sentinel's bytes where the hero should be")


def _play_to_a_busy_frame(buf, sprites, walk, minimum, what, first_frame=0):
    """Play until the picture has something in it, and say which frame that was and what is in it.

    The frame is the FIRST of [PLAY_WINDOW_FIRST, PLAY_WINDOW_LAST] that draws `minimum` sprites
    whole inside the play window, which the hero is one of on every run here — so a minimum of three
    is him and two others, and `_sprites_in_the_window`'s own bounds make even that a lower bound on
    what the picture shows. Running out of window is a refusal and not a shrug: a picture nothing
    has walked into is exactly the failure this replaced.
    """
    for frame in range(first_frame, PLAY_WINDOW_LAST + 1):
        _step(buf, sprites, frame, walk, what)
        drawn = _sprites_in_the_window(buf)
        if frame >= PLAY_WINDOW_FIRST and drawn >= minimum:
            _check_no_refused_os_calls(what)
            _assert_the_hero_is_installed(buf, what)
            return frame, drawn
    raise AssertionError(
        f"{what}: no frame of {PLAY_WINDOW_FIRST}..{PLAY_WINDOW_LAST} draws {minimum} sprite(s) "
        f"whole inside the window, so this picture would be background and a hero under a caption "
        f"naming creatures — the run has shifted, or this stage is not walked the way "
        f"`_walk_direction` says it is")


def _drawn_screen(buf):
    """The buffer holding the frame just finished: `flip_screen` swapped it to the front."""
    return _u32(buf, SCREEN_FRONT)


def render_stage1():
    """Stage 1, at its first frame and after the joystick script has walked the hero along it.

    `boot_load_stage` puts the stage up and `game_main_loop` then runs whole frames — its fifteen
    calls in its own order: the two keyboard ones, `round_bonus_run_frame`, `panel_refresh_frame`,
    `scene_run_frame` and `game_latch_input_and_step_actors` (the joystick edge and every actor's
    behaviour), then `project_followed_actor`, `bg_scroll_run_queue`, `project_actor_list`,
    `bg_scroll_blit`, `game_snap_follow_cursor`, `sprite_draw_pass`, `actor_spawn_pass`,
    `text_run_message_box` and `flip_screen`.
    """
    pictures = []
    buf = _fresh(_stage_pokes(SHEET_STAGE_ROW))
    _run_the_boot_chain(buf, "stage 1")
    _assert_the_screens_are_the_originals(buf, "stage 1")
    palette_at = _stage_palette_src(buf)
    sprites = _entered_frame_loop()
    walk = _walk_direction(buf)

    _step(buf, sprites, 0, walk, "stage 1's first frame")
    _check_no_refused_os_calls("stage 1's first frame")
    _assert_the_hero_is_installed(buf, "stage 1's first frame")
    pictures.append(_screen("stage1-start", buf, _drawn_screen(buf), palette_at))

    frame, drawn = _play_to_a_busy_frame(buf, sprites, walk, STAGE1_WALK_SPRITES,
                                         "stage 1, walking", first_frame=1)
    print(f"    stage1-walk: frame {frame}, {drawn} sprites inside the window")
    pictures.append(_screen("stage1-walk", buf, _drawn_screen(buf), palette_at))
    return pictures


def _sprites_in_the_window(buf):
    """How many of the projection's records the sprite pass will draw WHOLE and un-clipped.

    NOT just "names a sprite": `project_actor_list` publishes a record for every live actor, and the
    pass then drops the ones below its band and sends the ones past WB_SPRITE_RIGHT_CLIP_X to a
    clipping table. This applies both of those bounds, so it is a LOWER bound on what the picture
    shows — a sprite half off the right edge is drawn and is not counted here — which is the safe
    direction for a caption to be wrong in.
    """
    drawn = 0
    for slot in range(ACTOR_SCREEN_RECORD_COUNT):
        at = ACTOR_SCREEN_RECORDS + slot * ACTOR_SCREEN_RECORD_BYTES
        x, y, sprite = struct.unpack_from(">hhH", buf, at)
        if sprite != ACTOR_SPRITE_HIDDEN and 0 <= x < SPRITE_RIGHT_CLIP_X \
                and 0 <= y <= SPRITE_LAST_ROW:
            drawn += 1
    return drawn


def _stage_pokes(*rows):
    """A fresh image staged for booting `rows`: the seam's files, and NOTHING ELSE.

    Neither the sequence cursor nor the re-entry word is seeded any more, because the boot writes
    both itself — `game_restart_reset` inside the credits slice does — and a poke here would be
    overwritten by it anyway. The raw SPRITES.CRU is not poked here either: `_place_sprites_file` is
    the one statement of where that file goes, and it runs before every boot rather than once per
    image."""
    return dict(seam_pokes(_stage_files(rows)))


# ---------------------------------------------------------------- the later stages, through the cheat
#
# The game carries its own level skip and this is it, typed rather than poked. `game_key_actions`'
# walk at $5a8 steps a cursor along the four scancodes at $608 — $61 $30 $13 $1e, which are UNDO, B,
# R and A — and raises WB_KEY_SEQUENCE_MATCHED when the cursor reaches the $ff terminator. With that
# word raised, N ($31) takes the arm at $556, which pops game_main_loop's return address and `jmp`s
# to $e5ba: `boot_load_stage`, which advances the sequence and loads the next stage. The
# reconstruction cannot make that transfer, so it reports WB_KEY_ACTIONS_LEVEL_SKIP instead and this
# script calls the slice — which is exactly the wiring atari/wonderboy_main.c's own-entry build has.


@functools.lru_cache(maxsize=None)
def _cheat_scancodes():
    """The cheat's scancodes, read out of the shipped image's own table at WB_KEY_SEQUENCE_SCANCODES
    (the terminator included: the walk's last step reads it and needs a frame of its own)."""
    length = 0
    while harness.BASE_IMAGE[KEY_SEQUENCE_SCANCODES + length] != KEY_SEQUENCE_TERMINATOR:
        length += 1
    return tuple(harness.BASE_IMAGE[KEY_SEQUENCE_SCANCODES:KEY_SEQUENCE_SCANCODES + length])


def _type_the_cheat_and_skip(buf, sprites, what):
    """Type the cheat one scancode a frame, then press N.

    The walk takes one step per frame, so the sequence needs one frame per scancode plus one more on
    which the cursor meets the terminator and the cheat is raised. That last frame carries no
    scancode of its own — the terminator arm does not compare one.
    """
    typed = _cheat_scancodes() + (0,)
    for frame, scancode in enumerate(typed):
        ending = _run_frame(buf, sprites, frame, scancode=scancode)
        assert ending == KEY_ACTIONS_RETURNED, (
            f"{what}: typing the cheat left the frame loop reporting {ending}")
    assert _u16(buf, KEY_SEQUENCE_MATCHED) == KEY_SEQUENCE_MATCHED_SET, (
        f"{what}: the sequence walk did not raise WB_KEY_SEQUENCE_MATCHED, so N would be an "
        f"ordinary keypress and no level would be skipped")
    ending = _run_frame(buf, sprites, len(typed), scancode=KEY_SCANCODE_N)
    assert ending == KEY_ACTIONS_LEVEL_SKIP, (
        f"{what}: N with the cheat raised reported {ending}, not WB_KEY_ACTIONS_LEVEL_SKIP")


def _both_screens(buf):
    return (bytes(buf[SCREEN_LOW:SCREEN_LOW + SCREEN_BYTES]),
            bytes(buf[SCREEN_HIGH:SCREEN_HIGH + SCREEN_BYTES]))


def _assert_the_stage_load_left_the_panel(buf, before, what):
    """A reload must not disturb the panel the credits slice drew, and the check is the whole of it:
    `boot_load_stage` writes neither screen buffer at all.

    It fills the scroll engine's eight buffers and the sprite cells; the first frame after it paints
    the play WINDOW over the middle of a screen. So the panel a player sees in round eleven is still
    the one the credits picture put there in round one — which is what the machine does, and why the
    ladder's own reloads (`atari/wonderboy_main.c`) need nothing else. Stated over BOTH buffers and
    not just the panel columns, because "it touched nothing" is the property, and a load that
    scribbled inside the window would be just as wrong.
    """
    low, high = _both_screens(buf)
    for was, now, name in ((before[0], low, "WB_SCREEN_LOW"), (before[1], high, "WB_SCREEN_HIGH")):
        if was == now:
            continue
        differing = [offset for offset in range(SCREEN_BYTES) if was[offset] != now[offset]]
        raise AssertionError(
            f"{what}: the stage load changed {len(differing)} bytes of {name}, "
            f"{len(set(differing) & PANEL_OFFSETS)} of them in the status panel — the boot's own "
            f"reload is not supposed to touch a screen at all")


def _assert_the_box_says(buf, message_id, what):
    """Name the message the live box is showing, by composing that id again and comparing.

    WB_TEXT_BUFFER holds PLOTTED GLYPHS, not an id, and the request byte that named the message was
    consumed inside the same frame that composed it (`text_run_message_box` is the frame loop's
    fourteenth call and the arm that posts is its sixth) — so there is nothing left in the image to
    read the id off. Composing it again on a COPY and requiring the same 6,400 bytes is what turns
    "a box is up" into "this box is that message".
    """
    live = bytes(buf[TEXT_BUFFER:TEXT_BUFFER + TEXT_BUFFER_LEN])
    scratch = harness.candidate_image(bytearray(buf))
    scratch[TEXT_REQUEST] = message_id
    _bind("text_run_message_box", returns=False)(scratch)
    assert bytes(scratch[TEXT_BUFFER:TEXT_BUFFER + TEXT_BUFFER_LEN]) == live, (
        f"{what}: the box on this frame is not message {message_id:#x} — composing that id again "
        f"produces a different WB_TEXT_BUFFER, so the caption names the wrong message")


def _assert_the_stage_entry_box(buf, expected, what):
    """What the stage entry posted, checked on the way past STAGE_ENTRY_BOX_FRAME: a box is up and
    is the "Let's go." one, or — for the one row that posts nothing — no box is up at all.

    IT IS CHECKED AND NO LONGER PHOTOGRAPHED. The box lives WB_TEXT_LIFETIME_DEFAULT frames and this
    set's play pictures are now taken hundreds of frames in, where there is something in the window
    to see; but a stage entry that stopped posting its message would otherwise go unnoticed by
    anything here, so the check stayed and moved to where the box really is. A caption may say the
    entry posts a message because this ran, not because a picture happens to show one — which is the
    same mistake in the other direction that an earlier revision made, captioning a stage's frame
    120 as carrying a box it no longer had.

    BOTH DIRECTIONS ARE STATED because the rows are not alike, which is itself a measurement: three
    of the five rows below hold the box over frames 0..49 exactly, and two — the vine shaft and the
    lava — post no message at all.
    """
    active = buf[TEXT_BOX_ACTIVE]
    if not expected:
        assert active != TEXT_BOX_ACTIVE_SET, (
            f"{what}: WB_TEXT_BOX_ACTIVE is set on frame {STAGE_ENTRY_BOX_FRAME}, but this row is "
            f"the one measured to enter without a message box")
        return
    assert active == TEXT_BOX_ACTIVE_SET, (
        f"{what}: WB_TEXT_BOX_ACTIVE is {active:#04x}, not WB_TEXT_BOX_ACTIVE_SET — this row's "
        f"entry no longer posts the message every other row's does")
    at = TEXT_MESSAGE_TABLE + ((TEXT_MESSAGE_LETS_GO - TEXT_MESSAGE_FIRST_ID)
                              << TEXT_MESSAGE_PTR_SHIFT)
    text = bytes(harness.BASE_IMAGE[_u32(harness.BASE_IMAGE, at):][:0x20])
    assert LETS_GO_TEXT in text, (
        f"{what}: the message table's first entry is {text!r}, which does not carry "
        f"{LETS_GO_TEXT!r} — the caption quotes a string this binary does not have there")
    _assert_the_box_says(buf, TEXT_MESSAGE_LETS_GO, what)


SKIPPED_STAGES = (_Stage(7, "stage4-sky", 4, True),
                  _Stage(11, "stage5-woods", 7, True),
                  _Stage(12, "stage5-cave", 5, False),
                  _Stage(16, "stage6-dungeon", 4, True),
                  _Stage(23, "stage8-lava", 6, False))


def render_skipped_stages():
    """One picture per later stage, each reached by booting the row before it and using the cheat.

    ONE SKIP EACH, not a chain: every row the run passes through has to have its overlay staged, and
    the model holds eight files. So each picture boots row-1, types the cheat, and lets the skip's
    own `boot_load_stage` load the row the picture is of.
    """
    pictures = []
    for stage in SKIPPED_STAGES:
        what = f"{stage.name} (sequence row {stage.row})"
        buf = _fresh(_stage_pokes(stage.row - 1, stage.row))
        installed = _run_the_boot_chain(buf, f"{what}: the row before it", at_row=stage.row - 1)
        sprites = _entered_frame_loop()
        _type_the_cheat_and_skip(buf, sprites, what)
        before = _both_screens(buf)
        _boot_stage(buf, what, sprites_installed=installed)
        _assert_the_stage_load_left_the_panel(buf, before, what)
        landed = _u16(buf, LEVEL_SEQ_INDEX) - 1
        assert landed == stage.row, (
            f"{what}: the skip landed on sequence row {landed}, not the row this picture names")
        palette_at = _stage_palette_src(buf)
        walk = _walk_direction(buf)

        for frame in range(STAGE_ENTRY_BOX_FRAME + 1):
            _step(buf, sprites, frame, walk, what)
        _assert_the_stage_entry_box(buf, stage.entry_box, what)
        frame, drawn = _play_to_a_busy_frame(buf, sprites, walk, stage.sprites, what,
                                             first_frame=STAGE_ENTRY_BOX_FRAME + 1)
        print(f"    {stage.name}: sequence row {landed}, {_overlay_name(landed)}, "
              f"round {_stage_number(buf)}, walking "
              f"{'left' if walk == JOY_LEFT else 'right'}, frame {frame}, {drawn} sprites")
        pictures.append(_screen(stage.name, buf, _drawn_screen(buf), palette_at))
    return pictures


# ---------------------------------------------------------------- the cast
#
# The sheet is the game's own bitmaps, at their own addresses, drawn by the routine that draws them
# in play; only the DESTINATIONS are ours, so the cast lays out as a grid instead of as a playfield.
# `sprite_draw_pass` takes no argument — it walks the WB_ACTOR_SCREEN_RECORD_COUNT records
# `project_actor_list` leaves at WB_ACTOR_SCREEN_RECORDS — so writing records is how a sheet asks it
# for a sprite, and everything after that is the pass's own: the descriptor lookup, the clip against
# the band, the screen address, the sub-word shift and the dispatch into one of src/blit.c's twelve.


def _sprites_the_run_showed(buf, sprites, walk, frames):
    """Every sprite index the stage's own play put into a screen record over `frames` frames.

    WHY THE SHEET IS THIS AND NOT THE FIRST N OF THE MARKED SET: stage 1 marks 143 descriptors and a
    320x200 sheet holds twenty, so something has to choose. Taking the choice from the run means the
    sheet is the cast this stage ACTUALLY puts on the screen — the hero's own walk cycle and the
    creatures he met — rather than whichever descriptors happen to sit lowest in the table.
    """
    shown = []
    marked = {descriptor.sprite for descriptor in _installed_descriptors(buf)}
    for frame in range(frames):
        _run_frame(buf, sprites, frame, joystick_for(frame, walk))
        for slot in range(ACTOR_SCREEN_RECORD_COUNT):
            sprite = _u16(buf, ACTOR_SCREEN_RECORDS + slot * ACTOR_SCREEN_RECORD_BYTES
                          + ACTOR_SCREEN_SPRITE)
            if sprite != ACTOR_SPRITE_HIDDEN and sprite not in shown:
                assert sprite in marked, (
                    f"the run drew sprite {sprite}, which this stage's mask did not mark — the "
                    f"descriptor it read is another stage's, and the sheet would be drawing noise")
                shown.append(sprite)
    return sorted(shown)


def _assert_the_slot_draws_whole(buf, x, y, sprite):
    """Refuse a grid slot the sprite pass would clip, before anything is drawn.

    The pass rejects a record outright once its y passes WB_SPRITE_LAST_ROW, clamps the rows of one
    that would run past the band, and picks a clipping blitter table from WB_SPRITE_RIGHT_CLIP_X on
    — and every one of those is SILENT: the sheet simply comes out with a gap in it. So the sheet
    states where its sprites really land and fails on the arithmetic instead.
    """
    at = RESOURCE_TABLE + sprite * RESOURCE_RECORD_BYTES
    left = x + struct.unpack_from(">h", buf, at + SPRITE_DESC_X_OFFSET)[0]
    top = y + struct.unpack_from(">h", buf, at + SPRITE_DESC_Y_OFFSET)[0]
    rows = struct.unpack_from(">b", buf, at + SPRITE_DESC_HEIGHT)[0]
    assert 0 <= left < SPRITE_RIGHT_CLIP_X, (
        f"sprite {sprite} would be drawn at x={left}, outside "
        f"[0, WB_SPRITE_RIGHT_CLIP_X={SPRITE_RIGHT_CLIP_X}) — the pass would pick a clipping table "
        f"and the sheet would show part of it")
    assert 0 <= top and top + rows <= SPRITE_LAST_ROW, (
        f"sprite {sprite} would be drawn over rows {top}..{top + rows}, outside the band the pass "
        f"clips to (0..WB_SPRITE_LAST_ROW={SPRITE_LAST_ROW}) — SHEET_ROWS does not fit this cast")


def _lay_out(buf, batch):
    """Write one screenful of records: a sprite per grid slot, WB_ACTOR_SPRITE_HIDDEN for the rest."""
    for slot in range(ACTOR_SCREEN_RECORD_COUNT):
        at = ACTOR_SCREEN_RECORDS + slot * ACTOR_SCREEN_RECORD_BYTES
        if slot < len(batch):
            x, y, sprite = batch[slot]
            _assert_the_slot_draws_whole(buf, x, y, sprite)
            struct.pack_into(">hhH", buf, at, x, y, sprite)
        else:
            struct.pack_into(">hhH", buf, at, 0, 0, ACTOR_SPRITE_HIDDEN)


def render_sprite_sheet():
    """The cast, drawn onto the screen `clear_both_screens` leaves behind.

    The stage is loaded first and that is what makes the sheet the game's own rather than a set of
    pokes: `sprites_cru_install` is what put these cells in memory, out of the stage's own mask, and
    `resource_table_relocate` is what turned each descriptor's offset into the pointer the pass
    dereferences.
    """
    buf = _fresh(_stage_pokes(SHEET_STAGE_ROW))
    _run_the_boot_chain(buf, "the sprite sheet's stage")
    palette_at = _stage_palette_src(buf)
    sprites = _entered_frame_loop()
    cast = _sprites_the_run_showed(buf, sprites, _walk_direction(buf), SHEET_SCAN_FRAMES)
    slots = [(x, y) for y in SHEET_ROWS for x in SHEET_COLUMNS]
    assert len(cast) >= len(slots), (
        f"the run showed {len(cast)} sprite(s) and the sheet has {len(slots)} slots — it would be "
        f"drawn part empty, and the caption calling it the cast would overstate it")

    _bind("clear_both_screens", returns=False)(buf)
    for start in range(0, len(slots), ACTOR_SCREEN_RECORD_COUNT):
        batch = [(x, y, sprite) for (x, y), sprite
                 in zip(slots[start:start + ACTOR_SCREEN_RECORD_COUNT], cast[start:])]
        _lay_out(buf, batch)
        _bind("sprite_draw_pass", (ctypes.POINTER(_PassRegs),))(buf, ctypes.byref(sprites))
    _check_no_refused_os_calls("the sprite sheet")
    print(f"    the cast: {len(slots)} of {len(cast)} sprites the run showed")
    # The pass draws into WB_SCREEN_BACK, and nothing flipped afterwards.
    return [_screen("sprites", buf, _u32(buf, SCREEN_BACK), palette_at)]


def render_everything():
    """Every picture, in README order; returns [(name, PNG bytes)]."""
    pictures = [render_title(), render_credits(), render_prompt()]
    pictures += render_stage1()
    pictures += render_skipped_stages()
    pictures += render_sprite_sheet()
    return pictures


def main():
    """Render the set twice and require the two to agree, then say what was written.

    THE SECOND RENDERING IS THE POINT: "byte-identical every run" is the property that lets these
    PNGs be tracked in git, and it is cheap enough here to assert rather than assume.

    BOTH PASSES WRITE, so what is on disk after a mismatch is the SECOND run's picture and not the
    first — the two digests in the message are the record of what differed. That is deliberate: the
    thing being claimed is about the FILES, so rendering the second pass somewhere else would prove
    it of something else.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    first = render_everything()
    print("...and again, to prove the set is a function of the binary and nothing else")
    second = render_everything()
    assert [name for name, _ in first] == [name for name, _ in second], (
        "the two runs rendered different pictures, so the SET itself is not reproducible")
    for (name, before), (_, after) in zip(first, second):
        assert before == after, (
            f"{name}.png differs between two runs of this script — something in the set is not a "
            f"function of the binary and the game's own files (sha256 "
            f"{hashlib.sha256(before).hexdigest()} vs {hashlib.sha256(after).hexdigest()})")
    print(f"  {len(first)} pictures, byte-identical over two runs")


if __name__ == "__main__":
    main()
