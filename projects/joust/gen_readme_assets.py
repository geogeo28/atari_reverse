#!/usr/bin/env python3
"""Render the workspace README's Joust images straight from the verified C reconstruction.

Every picture here is *drawn by the reconstruction*, not screenshotted from the original
program. `../../tools/recreate_kit` loads and relocates your own `bin/JOUST.PRG` into the
flat image the differential harness uses, and this script then drives the very same
`g_*` entry points `recreate/test/` drives through ctypes — the title screen, the frame
loop, the high-score entry and five of the drawing routines — and de-interleaves the
Atari low-res framebuffer they paint, with the game's own palette words, into a PNG.

Nothing here needs Hatari or a TOS ROM: the kit models the handful of traps Joust makes,
so the whole set renders host-side. It does need YOUR OWN copy of the game in
`bin/JOUST.PRG` (depacked from `JOUSTS.CTE` by `tools/depack_gamex.py`) and a built
candidate — no game code or data is distributed with this repository.

Output goes to the tracked `<workspace>/assets/joust-*.png`, and every run is
byte-identical: the whole set is a function of `JOUST.PRG` alone (the high-score record is
the blank one the binary carries, not the save file beside it), the play frames come from
one seeded self-play chain, and nothing reads a clock. Re-run:

    cd recreate && make venv && make   # once: the venv and libjoust.so
    ./.venv/bin/python ../gen_readme_assets.py
"""
import collections
import ctypes
import functools
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RECREATE = HERE / "recreate"
sys.path.insert(0, str(WORKSPACE / "tools"))     # write_png
sys.path.insert(0, str(RECREATE / "test"))       # harness.py — binds the kit and loads the .so

import harness                     # noqa: E402  loads JOUST.PRG into the image, opens libjoust.so
from extract_graphics import write_png   # noqa: E402

OUT = WORKSPACE / "assets"

# ---- the ST low-res framebuffer: the four cell constants mirror recreate/include/joust.h ----
SCREEN_WIDTH, SCREEN_HEIGHT = 320, 200
SCREEN_ROW_BYTES = 0xa0        # one scanline: 20 cells of four bitplane words
CELL_PIXELS = 16               # pixels per cell...
CELL_BYTES = 8                 # ...and its four plane words
CELL_PLANE_WORDS = 4
PALETTE_PENS = 0x10

# ---- globals, by Ghidra address (mirrors names.txt and recreate/include/) ----
A_LIVE_OBJECT_COUNT = 0x10d0a  # .b — riders on the board, players included
A_EGG_COUNT = 0x10d0b          # .b
A_DRAW_CLIP_CELL0 = 0x10d0e    # draw.h — the first of DRAW_CLIP_CELLS per-cell suppressors
A_GAME_OVER_FLAG = 0x10d12     # score.h
A_DRAW_HALF_SELECT = 0x10dc2   # draw.h — bit1 skips the leading pass, bit0 the wrap column
A_SCREEN_BASE = 0x10dde        # addrs.h — .l, where init_system put XBIOS Physbase' answer
A_DRAW_DST = 0x10de8           # addrs.h — .l, absolute to the riders and eggs, an offset elsewhere
A_DRAW_X = 0x10dec             # object.h — .w
A_DRAW_SRC = 0x10df0           # addrs.h — .l
A_DRAW_SHIFT = 0x10df4         # addrs.h — .b to the riders and eggs, .w to the bird and the troll
A_DRAW_ROWS = 0x10df6          # addrs.h — same width clash, faithfully reproduced
A_DRAW_DST_OFF = 0x10df8       # draw.h — .w, sign-extended into the bird's destination
A_IKBD_PACKET = 0x10e06        # input.h — the reply an IKBD interrupt would leave
A_TITLE_PALETTE = 0x10cd2      # the 16 pens title_screen hands XBIOS Setpalette...
A_GAME_PALETTE = 0x1143a       # ...and the ones init_video does
A_PTERODACTYL_TABLE = 0x113ba  # object.h — PTERODACTYL_SLOTS records; a zero flags word is free
A_TROLL_SPRITE_TABLE = 0x14aba  # world.h — one hand frame per record
A_PTERO_FRAME_TABLE = 0x151d6  # ptero.h — {src.l, dst_off.w, rows.w} per wing-beat pose
A_HISCORE_NAME = 0x18396       # score.h — the 26-byte HIGH.SCO record: name, then score digits
A_EGG_SPRITE_STILL = 0x1899a   # egg.h — the three egg poses
A_EGG_SPRITE_ROLL_LEFT = 0x18a0a
A_EGG_SPRITE_ROLL_RIGHT = 0x18a7a
PTERODACTYL_SLOTS = 4          # object.h — A_pterodactyl_table_END is 4 x PT_RECORD on
PTERODACTYL_RECORD = 0x20      # object.h's PT_RECORD

# ---- glue results (mirrors recreate/include/) ----
TITLE_STARTED = 0              # init.h — title_screen reached its `rts`: a game is set up
START_AT_JOYSTICKS = 0         # init.h — the pass reached read_joysticks, which blocks
CONTROL_RETURNED = 0           # player.h — the rotated joystick pass came back
CHECK_HIGHSCORE_ENTERED = 1    # input.h — the name-entry screen is up
INPUT_CONTINUE = 0             # input.h — the key handler returned normally
GAME_OVER_SET = 1              # player.h — what the game itself writes when the last life goes

# ---- staging ----
HIGHSCORE_FILE = "HIGH.SCO"
HISCORE_RECORD_BYTES = 0x1a
ONE_PLAYER_KEY = "1"           # the console key title_screen starts a one-player game on
# A reply pointer for the IKBD packet, and the two joystick bytes behind it. Free image space:
# above the program (which ends at 0x2b7ae) and below the kit's staged-file table at 0xbf000.
IKBD_PACKET_BUF = 0x60000
IKBD_PACKET_BYTES = 2
# ...and a scratch block for the sprite sheet's object record and blit record, likewise free.
SCRATCH = 0x50000
SCRATCH_BLIT_RECORD = SCRATCH + 0x100

# The seed the self-play chain drives the sticks with. Random input is what makes the game play
# itself at all — the riders have to fight for an egg to exist — and a fixed seed is what makes
# every frame below reproducible.
PLAY_SEED = 0x10000

# WHICH LAPS OF THAT CHAIN ARE SHOWN — laps of the seeded run picked for what they show, not the
# EARLIEST lap that shows it. Each carries the CLAIM its README caption makes, asserted before the
# frame is written, so that a reconstruction fix which shifts the run fails loudly instead of
# quietly re-rendering an ordinary frame under a caption naming a bird that is no longer in it.
FRAME_SHOTS = (
    (60, "wave1", "the wave has not spawned its enemies yet",
     lambda image: _live_objects(image) == 0),
    (185, "eggs", "riders are up and an egg is loose",
     lambda image: _live_objects(image) >= 3 and image[A_EGG_COUNT] >= 1),
    (1850, "pterodactyl", "a pterodactyl slot is occupied",
     lambda image: _pterodactyls(image) >= 1),
)
# ...and the last lap the high-score run plays before its game is declared over (render_hiscore).
HISCORE_LAST_LAP = 445
HISCORE_NAME_TYPED = "JOUST"


@functools.lru_cache(maxsize=None)
def _bind(name, argc=1, result=False):
    """One candidate entry point, driven exactly as recreate/test/ drives it: the flat image as a
    ctypes buffer, then this routine's own arguments.

    `result` says the glue returns a longword the caller reads — most of them are `void`, and
    declaring a return type they do not have would let a later `assert` read a stale register.
    Cached because the frame loop below binds per lap: the prototype is declared once.
    """
    fn = getattr(harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * (argc - 1)
    fn.restype = ctypes.c_uint32 if result else None
    return fn


def _w8(image, addr, value):
    image[addr] = value


def _w16(image, addr, value):
    struct.pack_into(">H", image, addr, value)


def _w32(image, addr, value):
    struct.pack_into(">I", image, addr, value)


def _screen_offset(y, cell):
    """Byte offset of a cell-aligned position in the framebuffer."""
    return y * SCREEN_ROW_BYTES + cell * CELL_BYTES


def _screen_base(image):
    """Where the game is drawing: the address `init_system` read out of XBIOS Physbase. Taken from
    the image rather than from a constant of our own, so the decode follows the game's own pointer."""
    return struct.unpack_from(">I", image, A_SCREEN_BASE)[0]


def _live_objects(image):
    """Riders on the board, players included, as `count_objects_and_pad` last counted them."""
    return image[A_LIVE_OBJECT_COUNT]


def _pterodactyls(image):
    """Occupied pterodactyl slots: a record whose flags word is zero is a free one."""
    return sum(1 for slot in range(PTERODACTYL_SLOTS)
               if struct.unpack_from(">H", image,
                                     A_PTERODACTYL_TABLE + slot * PTERODACTYL_RECORD)[0])


def _palette(image, addr):
    """PALETTE_PENS ST palette words (0x0RGB, 3 bits a channel) -> RGB triples for the PNG."""
    pens = []
    for pen in range(PALETTE_PENS):
        word = struct.unpack_from(">H", image, addr + pen * 2)[0]
        red, green, blue = (word >> 8) & 7, (word >> 4) & 7, word & 7
        pens.append((red * 255 // 7, green * 255 // 7, blue * 255 // 7))
    return pens


def _decode_interleaved(image, base):
    """De-interleave the ST low-res framebuffer at `base` into rows of palette indices (0..15).

    A row is 20 cells of four bitplane words; within a cell the words are planes 0..3 and the MSB
    is the leftmost pixel, plane 0 contributing the low bit of the index.
    """
    rows = []
    for y in range(SCREEN_HEIGHT):
        row = bytearray(SCREEN_WIDTH)
        row_base = base + y * SCREEN_ROW_BYTES
        for cell in range(SCREEN_WIDTH // CELL_PIXELS):
            words = [struct.unpack_from(">H", image, row_base + cell * CELL_BYTES + plane * 2)[0]
                     for plane in range(CELL_PLANE_WORDS)]
            for bit in range(CELL_PIXELS):
                shift = (CELL_PIXELS - 1) - bit
                index = 0
                for plane in range(CELL_PLANE_WORDS):
                    index |= ((words[plane] >> shift) & 1) << plane
                row[cell * CELL_PIXELS + bit] = index
        rows.append(row)
    return rows


def _write_screen(name, image, palette_addr=A_GAME_PALETTE):
    """Decode the framebuffer the reconstruction just painted and write it out as a PNG."""
    path = OUT / ("joust-%s.png" % name)
    write_png(str(path), SCREEN_WIDTH, SCREEN_HEIGHT,
              _decode_interleaved(image, _screen_base(image)), _palette(image, palette_addr))
    print("  wrote", path.relative_to(WORKSPACE))


def _shipped_hiscore_record():
    """The high-score record JOUST.PRG itself carries — 26 blank bytes, i.e. no record set yet."""
    return bytes(harness.BASE_IMAGE[A_HISCORE_NAME:A_HISCORE_NAME + HISCORE_RECORD_BYTES])


def _staged_image():
    """A fresh image with the two things Joust reads from the outside world staged.

    `HIGH.SCO` is served through the kit's modeled GEMDOS (init_system opens it by name) and one
    console keystroke through its modeled Bconstat/Bconin — the key title_screen starts a game on.

    The record staged is the BLANK one JOUST.PRG itself carries, not whatever `bin/HIGH.SCO` holds
    today: a fresh installation with no score on the board. That is what makes every picture here a
    pure function of the binary — a save file is mutable, and staging it would put one player's
    score into a tracked PNG and make "byte-identical every run" false between two machines. It is
    also what lets render_hiscore's own run beat the record honestly.
    """
    pokes, _ = harness.stage_files([(HIGHSCORE_FILE, _shipped_hiscore_record())])
    pokes.update(harness.console_key(ONE_PLAYER_KEY))
    image = harness.make_image(pokes)
    harness._lib.g_os_refusal_reset()      # see _check_no_refused_os_calls
    return image, (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(image)


def _check_no_refused_os_calls(what):
    """Fail if the run made an `os_*` call the kit's TOS model refuses to serve.

    The differential does this after every candidate run (`harness._vet_no_os_refusal`) because a
    refusal returns a sentinel and touches neither the out-param nor the image. Nothing here goes
    through `differential()`, so without this an unstaged file or an unmodelled trap would render a
    plausible-looking picture with a piece silently missing, and the script would exit 0.
    """
    refusals = harness._lib.g_os_refusal_count()
    assert refusals == 0, (
        f"{what}: the candidate made {refusals} os_* call(s) the TOS model refuses — something the "
        f"run needed is not staged, so the picture is missing whatever that call would have done")


def _drive_one_frame(image, buf, rng):
    """One lap of `_start`'s frame loop, driven the way test_init.py's walk drives it.

    The loop's ninth call blocks in an IKBD wait that ends on no run — the reply arrives on an
    interrupt neither core models — so a frame is two verified halves: `g_read_joysticks_pass`
    enters `read_joysticks` past its wait with a reply staged, and `g_start_frame_pass` runs calls
    10..21, takes the branch that closes the loop and comes back round to the ninth.
    """
    _w32(image, A_IKBD_PACKET, IKBD_PACKET_BUF)
    for byte in range(IKBD_PACKET_BYTES):
        image[IKBD_PACKET_BUF + byte] = rng.randrange(0x100)

    assert _bind("g_read_joysticks_pass", result=True)(buf) == CONTROL_RETURNED, \
        "the rotated joystick pass refused the staged packet, or the game restarted"
    assert _bind("g_start_frame_pass", 3, result=True)(buf, 0, 0) == START_AT_JOYSTICKS, \
        "the frame pass refused this lap: a quit key is pending, or the game is over with the " \
        "record taken (which would send check_highscore into a loop no staged input can leave)"


def _self_play(image, buf, last_lap, capture=None):
    """Boot the game and play it through `last_lap`, calling `capture(lap, image)` after each.

    `g_start` runs the four one-shot calls — init_system, init_game, title_screen (which consumes
    the staged key and chooses a one-player game) and init_video — and then the frame loop's first
    four, leaving the image exactly where the original stands at its ninth call.
    """
    assert _bind("g_start", result=True)(buf) == START_AT_JOYSTICKS, \
        "g_start refused the staged console key"
    rng = random.Random(PLAY_SEED)
    for lap in range(last_lap + 1):
        _drive_one_frame(image, buf, rng)
        if capture is not None:
            capture(lap, image)


def render_title():
    """The title screen: `init_system` takes the machine over and loads HIGH.SCO, then
    `title_screen` paints the picture JOUST.PRG carries, draws its three text lines — the middle
    one with the saved record spliced into it, blank here because the staged record is the PRG's
    own — and runs one attract pass, which is what rotates the six-pen ring the PNG's palette is
    then read out of."""
    image, buf = _staged_image()
    _bind("g_init_system")(buf)
    assert _bind("g_title_screen", result=True)(buf) == TITLE_STARTED, \
        "title_screen did not reach its rts for the staged key"
    _check_no_refused_os_calls("title_screen")
    _write_screen("title", image, A_TITLE_PALETTE)


def render_play_frames():
    """The frames of FRAME_SHOTS, off one run of the game playing itself through the verified
    per-frame chain — each checked to contain what its caption says before it is written."""
    wanted = {lap: shot for lap, *shot in FRAME_SHOTS}

    def capture(lap, image):
        if lap not in wanted:
            return
        name, claim, holds = wanted[lap]
        assert holds(image), f"lap {lap} no longer shows what joust-{name}.png claims: {claim}"
        _write_screen(name, image)

    image, buf = _staged_image()
    _self_play(image, buf, max(wanted), capture)
    _check_no_refused_os_calls("the frame loop")


def render_hiscore():
    """The high-score name-entry screen, on a game the reconstruction really played.

    The score is genuinely earned: it is played against the blank record JOUST.PRG carries, and
    `check_highscore` reports ENTERED only after its own comparison finds the leader's digits beat
    that record. The one thing staged is `game_over_flag` — the byte the game writes when the last
    life goes. Bounded self-play cannot reach that by itself, because `g_start_frame_pass` refuses
    a lap once the game is over with the record taken; the poke is what stands in for the last life.
    The name is then typed through `hiscore_key_input`, one console key a call.
    """
    image, buf = _staged_image()
    _self_play(image, buf, HISCORE_LAST_LAP)

    _w8(image, A_GAME_OVER_FLAG, GAME_OVER_SET)
    # The assert IS the proof the score was earned: check_highscore only reports ENTERED after its
    # own comparison finds the leader's digits beat the staged record.
    assert _bind("g_check_highscore", result=True)(buf) == CHECK_HIGHSCORE_ENTERED, \
        "this run's score no longer beats the record JOUST.PRG ships with"
    key_input = _bind("g_hiscore_key_input", result=True)
    for letter in HISCORE_NAME_TYPED:
        for addr, data in harness.console_key(letter).items():
            image[addr:addr + len(data)] = data
        assert key_input(buf) == INPUT_CONTINUE, f"the entry screen did not take {letter!r}"
    _check_no_refused_os_calls("check_highscore")
    _write_screen("hiscore", image)


# ---------------------------------------------------------------- the sprite sheet
#
# Every bitmap below is the game's own, at its own address, drawn by the routine that draws it in
# play; only the DESTINATION is ours, so the cast lays out as a grid instead of as a playfield.
# The five routines do not agree on how a sprite is described — the rider and egg ones take an
# absolute destination and read draw_shift/draw_rows as BYTES, the bird and the troll take an offset
# from screen_base and read the same two addresses as WORDS, and the flame takes a record of its own
# — which is why each family below stages its own block rather than sharing one.

RIDER_SETS = (0x1a80a,   # render.h's SPRITE_RIDER_P1 / _P2 / _ENEMY_TYPE1 / _TYPE2 / _TYPE3
              0x1cd6a,
              0x1f2ca,
              0x201ea,
              0x2110a)
RIDER_DEAD_OFF = 0xf20        # render.h's SPRITE_RIDER_DEAD: the unseated bird
ENEMY_DEAD_SET = 0x2202a      # ...and SPRITE_ENEMY_DEAD
# {y, source offset into the set, rows}: render.h's pose offsets and its RIDER_ROWS_* counts.
RIDER_POSES = ((6, 0x000, 0xd),     # gliding — RIDER_ROWS_FLIGHT
               (28, 0x1a0, 0xe),    # flapping — SPRITE_FLAP, one row taller
               (48, 0x360, 0x13))   # walking — SPRITE_WALK, RIDER_ROWS_STANDING
RIDER_DEAD_ROW = 76
RIDER_COLUMN_STEP = 4         # cells between one rider column and the next
RIDER_COLUMN_FIRST = 1
EGG_SPRITES = (A_EGG_SPRITE_STILL, A_EGG_SPRITE_ROLL_LEFT, A_EGG_SPRITE_ROLL_RIGHT)
EGG_ROWS = 7                  # collide.c's EGG_SPRITE_ROWS
EGG_ROW = 78
EGG_COLUMN_FIRST, EGG_COLUMN_STEP = 13, 2
PTERO_ROW = 100
TROLL_ROW = 124
TROLL_STATE_HAND_OUT = 1      # world.h — `btst #0,d0`: nothing is drawn without it
FLAME_FRAMES = 4              # world.h: FLAME_FRAME_FIRST..FLAME_FRAME_END, FLAME_FRAME_BYTES apart
FLAME_FRAME_FIRST, FLAME_FRAME_BYTES = 0x18636, 0xd8
# THE SHEET'S ONE ROW COUNT OF ITS OWN. In play the flames are blitted with GA_ROWS out of the
# ground-burn state block, which only a wave that narrows the ground ever arms — there is nothing to
# read on a cold image. 18 is the frame height ../names.txt records for these four bitmaps.
FLAME_ROWS = 18
FLAME_ROW = 154
WIDE_COLUMN_FIRST, WIDE_COLUMN_STEP = 1, 5   # the bird, the hand and the flame span several cells
DRAW_CLIP_CELLS = 3           # draw.h's draw_clip_cell0/1/2
DRAW_CLIP_CELL_SHOW = 0       # ...a NON-zero suppressor hides that cell of every row
# The blit record blit_sprite reads (draw.h's SPR_*), and the object record the rider and egg
# blitters read (joust.h's OBJ_*). Both are ours, in scratch space, since the sheet is not a frame.
SPR_SRC, SPR_DST_OFF, SPR_SHIFT, SPR_CELL_SELECT = 0x00, 0x04, 0x08, 0x0a
SPR_CELL_SELECT_BOTH = 0      # signed: 0 draws the leading cell and the trailing one
OBJ_FLAGS, OBJ_X, OBJ_EGG_STATE = 0x00, 0x02, 0x1e
OBJ_FLAGS_OCCUPIED = 1        # any non-zero flags word: an empty slot draws nothing
EGG_STATE_RESTING = 0x22      # egg.h — likewise, a slot with no egg draws nothing
# src/draw.c's HALF_SELECT_SKIP_LEADING/SKIP_WRAP pair, as render_object_body stages it for an
# ordinary draw: neither bit. It has to be neither — a rider is TWO cells wide (draw.c's
# SPRITE_SRC_ROW_BYTES is 0x10, two cells of plane words) and the "wrap column" pass is what draws
# the second one, so skipping it clips the sprite's right-hand pixels off.
HALF_SELECT_BOTH_PASSES = 0
# ...and that second cell lands one cell RIGHT only while x is below draw.c's SPRITE_WRAP_X (0x130);
# past it the pass drops back a scanline to the screen's left edge, which a grid does not want.
RIDER_X_BEFORE_WRAP = 0
NO_SHIFT = 0                  # every sprite is placed cell-aligned

# One animation table: where it is, how many frames, and where the sprite, the row count and (for
# the bird only) the per-pose vertical alignment sit inside a record. `dst_off = None` means the
# family has no alignment field and its routine reads no draw_dst_off either.
_FrameTable = collections.namedtuple("_FrameTable", "base frames record src rows dst_off")

# ptero.h's ptero_frame_table: FRAME_RECORD-sized {FRAME_SRC.l, FRAME_DST_OFF.w, FRAME_ROWS.w}.
# Poses 1 and 3 share a bitmap, so the four-phase beat is three drawings.
PTERO_TABLE = _FrameTable(A_PTERO_FRAME_TABLE, frames=4, record=8, src=0x0, rows=0x6, dst_off=0x4)
# world.h's troll_sprite_table: TROLL_FRAME_STEP-sized {TROLL_SPR_SRC.l, TROLL_SPR_ROWS.w}. Four
# records — the three the hand climbs through (up to TROLL_FRAME_CLIMB_LAST) and TROLL_FRAME_HELD,
# the one it uses once it has hold of something.
TROLL_TABLE = _FrameTable(A_TROLL_SPRITE_TABLE, frames=4, record=8, src=0x0, rows=0x4, dst_off=None)


def _draw_rider(image, buf, y, cell, src, rows):
    """One rider pose through `draw_object_data`, the blitter render_object_body draws riders with.
    It takes an absolute destination and reads its shift and row count as bytes."""
    _w32(image, A_DRAW_SRC, src)
    _w32(image, A_DRAW_DST, _screen_base(image) + _screen_offset(y, cell))
    _w8(image, A_DRAW_ROWS, rows)
    _bind("g_draw_object_data", 2)(buf, SCRATCH)


def _draw_riders(image, buf):
    """The five rider sprite sets in three poses, then the three unseated ones."""
    _w16(image, SCRATCH + OBJ_FLAGS, OBJ_FLAGS_OCCUPIED)
    _w16(image, SCRATCH + OBJ_X, RIDER_X_BEFORE_WRAP)
    _w8(image, A_DRAW_HALF_SELECT, HALF_SELECT_BOTH_PASSES)
    _w8(image, A_DRAW_SHIFT, NO_SHIFT)

    for column, base in enumerate(RIDER_SETS):
        cell = RIDER_COLUMN_FIRST + RIDER_COLUMN_STEP * column
        for y, pose, rows in RIDER_POSES:
            _draw_rider(image, buf, y, cell, base + pose, rows)

    dead = (RIDER_SETS[0] + RIDER_DEAD_OFF, RIDER_SETS[1] + RIDER_DEAD_OFF, ENEMY_DEAD_SET)
    glide_rows = RIDER_POSES[0][2]
    for column, src in enumerate(dead):
        _draw_rider(image, buf, RIDER_DEAD_ROW,
                    RIDER_COLUMN_FIRST + RIDER_COLUMN_STEP * column, src, glide_rows)


def _draw_eggs(image, buf):
    """The three egg poses through `draw_egg_sprite` — same scratch globals, its own row stride."""
    _w8(image, SCRATCH + OBJ_EGG_STATE, EGG_STATE_RESTING)
    _w16(image, A_DRAW_X, 0)
    for column, src in enumerate(EGG_SPRITES):
        _w32(image, A_DRAW_SRC, src)
        _w32(image, A_DRAW_DST,
             _screen_base(image)
             + _screen_offset(EGG_ROW, EGG_COLUMN_FIRST + EGG_COLUMN_STEP * column))
        _w8(image, A_DRAW_ROWS, EGG_ROWS)
        _bind("g_draw_egg_sprite", 2)(buf, SCRATCH)


def _draw_table_frames(image, buf, table, row, draw):
    """The bird's and the troll's animation frames, which are the same job twice.

    Both walk a table of fixed-stride records, take the sprite and its height out of the record,
    read `draw_shift`/`draw_rows` as WORDS, and take a destination that is an OFFSET from
    screen_base — so the two differ only in the table they walk and the routine they call.
    `table` is a `_FrameTable`; `draw(buf)` issues one frame.
    """
    _w16(image, A_DRAW_SHIFT, NO_SHIFT)
    for frame in range(table.frames):
        record = table.base + frame * table.record
        _w32(image, A_DRAW_SRC, struct.unpack_from(">I", image, record + table.src)[0])
        _w16(image, A_DRAW_ROWS, struct.unpack_from(">H", image, record + table.rows)[0])
        if table.dst_off is not None:
            _w16(image, A_DRAW_DST_OFF,
                 struct.unpack_from(">H", image, record + table.dst_off)[0])
        _w32(image, A_DRAW_DST, _screen_offset(row, WIDE_COLUMN_FIRST + WIDE_COLUMN_STEP * frame))
        draw(buf)


def _draw_pterodactyl(image, buf):
    """The four wing-beat poses through `blit_sprite_planes`, read whole out of the game's own
    `ptero_frame_table`: the bitmap, its height AND its per-pose vertical alignment, which is what
    holds the bird's body still while its wings move. The three per-cell suppressors must be clear
    or the bird is clipped the way it is at the screen edges."""
    for cell in range(DRAW_CLIP_CELLS):
        _w8(image, A_DRAW_CLIP_CELL0 + cell, DRAW_CLIP_CELL_SHOW)
    _draw_table_frames(image, buf, PTERO_TABLE, PTERO_ROW, _bind("g_blit_sprite_planes"))


def _draw_troll_hand(image, buf):
    """The lava troll's hand frames through `troll_draw_hand`, out of `troll_sprite_table` — the
    three it climbs through and the one it holds an object with.
    It draws only while the state word says the hand is out, so that bit is what is passed; its
    record carries no alignment field, and the routine reads no `draw_dst_off` either."""
    _draw_table_frames(image, buf, TROLL_TABLE, TROLL_ROW,
                       lambda buf_: _bind("g_troll_draw_hand", 2)(buf_, TROLL_STATE_HAND_OUT))


def _draw_flames(image, buf):
    """The four lava-flame frames through `blit_sprite`, the ground-animation blitter — the one
    that takes a record rather than the draw_* globals. Its silhouette mask sits inside the sprite
    (draw.h's SPR_MASK_OFF), which is why these are the frames that read as flame rather than as a
    rectangle."""
    for frame in range(FLAME_FRAMES):
        _w32(image, SCRATCH_BLIT_RECORD + SPR_SRC, FLAME_FRAME_FIRST + frame * FLAME_FRAME_BYTES)
        _w32(image, SCRATCH_BLIT_RECORD + SPR_DST_OFF,
             _screen_offset(FLAME_ROW, WIDE_COLUMN_FIRST + WIDE_COLUMN_STEP * frame))
        _w16(image, SCRATCH_BLIT_RECORD + SPR_SHIFT, NO_SHIFT)
        _w16(image, SCRATCH_BLIT_RECORD + SPR_CELL_SELECT, SPR_CELL_SELECT_BOTH)
        _bind("g_blit_sprite", 3)(buf, SCRATCH_BLIT_RECORD, FLAME_ROWS)


def render_sprite_sheet():
    """The cast, drawn onto the blank screen `init_system` + `init_game` leave behind.

    Those two are what make the sheet the game's own rather than a set of pokes: init_system reads
    the framebuffer's address out of XBIOS Physbase into screen_base, and init_game relocates
    playfield_bottom against it — the line every blitter here stops at.
    """
    image, buf = _staged_image()
    _bind("g_init_system")(buf)
    _bind("g_init_game")(buf)

    _draw_riders(image, buf)
    _draw_eggs(image, buf)
    _draw_pterodactyl(image, buf)
    _draw_troll_hand(image, buf)
    _draw_flames(image, buf)
    _check_no_refused_os_calls("the sprite sheet")
    _write_screen("sprites", image)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    render_title()
    render_play_frames()
    render_hiscore()
    render_sprite_sheet()


if __name__ == "__main__":
    main()
