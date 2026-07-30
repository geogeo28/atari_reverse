"""Differential tests for the per-object render pass (src/render.c).

The three entries are one routine: `render_objects` seeds A0 and falls into `render_object_body`,
and every branch that finishes a slot falls into `render_objects_next`, which owns the only `rts`.
So entering the oracle at the body with A0 mid-table renders that slot AND every slot above it —
which is why almost every case below stages the whole object table (all slots free) and fills in
just the one it is about, usually the LAST, so exactly one slot's work is measured.

None of it needs a `stop_pc`: every path in the family reaches that single `rts`, including the two
that re-dispatch the same slot (the edge-bump miss and the end of a respawn).

NO CASE HERE USES poison=True, and that is MEASURED rather than assumed. The attribution pass
inverts every byte the oracle wrote and re-runs both cores — but this routine writes OBJ_PREV_DST, a
screen POINTER it dereferences again on the very next frame, so a poisoned prev_dst is a wild
address the erase pass reads through: the run tried, and the candidate segfaulted, taking the pytest
worker with it. Every branch here also commits the flags word it dispatched on, so even a poisoned
run that survived would be measuring a different branch. What the cases below use instead is a
direct assertion, off the ORACLE's own final image, that the named branch really fired.
"""
import ctypes
import random
import struct

import pytest

import harness   # binds the kit, which puts its oracle/ on sys.path for the next line
import emu       # noqa: E402  (import order matters: see above)
from harness import differential, report
from test_constants import _defines

ENTRY_RENDER_OBJECTS = 0x12caa
ENTRY_RENDER_OBJECTS_NEXT = 0x12cb2
ENTRY_RENDER_OBJECT_BODY = 0x12cc2

# --- globals (names.txt) -----------------------------------------------------------------------
A_PLAYERS_ALIVE = 0x10cf2
A_PLATFORM_PRESENT = 0x10cfa
A_LIVE_OBJECT_COUNT = 0x10d0a
A_RESPAWN_LOCK = 0x10d13        # names.txt `respawn_lock`; the C is include/addrs.h's
A_SPAWN_POINT_CURSOR = 0x10d14
A_SND_PRIORITY = 0x10d4c
A_SND_OWNER = 0x10d4e           # names.txt `snd_owner`; the C is include/render.h's
A_PLAYFIELD_BOTTOM = 0x10d60
A_DRAW_HALF_SELECT = 0x10dc2
A_FLAP_DELAY = 0x10ddc
A_SCREEN_BASE = 0x10dde
A_DRAW_DST = 0x10de8
A_DRAW_SRC = 0x10df0
A_DRAW_SHIFT = 0x10df4
A_DRAW_ROWS = 0x10df6
A_OBJECT_TABLE = 0x10f36
A_PLAYER2 = 0x10f84
A_ENEMY_OBJECTS = 0x10fd2
A_OBJECT_TABLE_END = 0x1137a
A_PLATFORM_EDGE_TABLE = 0x117f4
A_PLATFORM_EDGE_TABLE_END = 0x11944
A_SPAWN_POINTS = 0x11964
A_SPAWN_POINTS_END = 0x119b4

# --- object record -------------------------------------------------------------------------------
OBJ_SIZE = 0x4e
OBJ_SLOTS = 14                  # (A_OBJECT_TABLE_END - A_OBJECT_TABLE) / OBJ_SIZE
OBJ_FLAGS = 0x00
OBJ_X = 0x02
OBJ_Y = 0x04
OBJ_VX = 0x06
OBJ_VY = 0x08
OBJ_ANIM_TIMER = 0x0a
OBJ_STEP_TIMER = 0x0b
OBJ_TARGET_VX = 0x0c
OBJ_FLAP_FRAME = 0x0e
OBJ_PREV_X = 0x10
OBJ_PREV_Y = 0x12
OBJ_PREV_DST = 0x14
OBJ_PREV_SRC = 0x18
OBJ_PREV_ROWS = 0x1c
OBJ_PREV_SHIFT = 0x1d
OBJ_SCORE_PTR = 0x36
OBJ_SCORE_SHIFT = 0x3a
OBJ_SCORE_TEXT = 0x3c
OBJ_SCORE_PENDING = 0x43
OBJ_FLAP_TIMER = 0x49
OBJ_TURN_TIMER = 0x4b
OBJ_LIVES = 0x4c

# {keyword: (offset, struct format)} — the record packer below. Keeping the two spellings apart
# means the OBJ_* constants stay exactly what the pin section checks against the headers.
FIELDS = {
    "flags": (OBJ_FLAGS, ">H"), "x": (OBJ_X, ">H"), "y": (OBJ_Y, ">H"),
    "vx": (OBJ_VX, ">H"), "vy": (OBJ_VY, ">H"),
    "anim": (OBJ_ANIM_TIMER, "B"), "step": (OBJ_STEP_TIMER, "B"),
    "target_vx": (OBJ_TARGET_VX, ">H"), "frame": (OBJ_FLAP_FRAME, ">H"),
    "prev_x": (OBJ_PREV_X, ">H"), "prev_y": (OBJ_PREV_Y, ">H"),
    "prev_dst": (OBJ_PREV_DST, ">I"), "prev_src": (OBJ_PREV_SRC, ">I"),
    "prev_rows": (OBJ_PREV_ROWS, "B"), "prev_shift": (OBJ_PREV_SHIFT, "B"),
    "score_shift": (OBJ_SCORE_SHIFT, ">H"), "pending": (OBJ_SCORE_PENDING, "B"),
    "flap_timer": (OBJ_FLAP_TIMER, "B"), "turn_timer": (OBJ_TURN_TIMER, "B"), "lives": (OBJ_LIVES, "B"),
}

# --- the flags word ------------------------------------------------------------------------------
FLAG_TYPE_LO = 1 << 0
FLAG_TYPE_HI = 1 << 1
FLAG_PLAYER = 1 << 2
FLAG_GRABBED = 1 << 4
FLAG_CORPSE_INSIDE = 1 << 5
FLAG_WINGS_UP = 1 << 6
FLAG_RESPAWN = 1 << 7
FLAG_IN_LAVA = 1 << 8
FLAG_ON_PLATFORM = 1 << 9
FLAG_FLAP_TAKEN = 1 << 10
FLAG_FLAP_REQUEST = 1 << 11
FLAG_REMOVED = 1 << 12
FLAG_DEAD = 1 << 13
FLAG_PLATFORM_BUMP = 1 << 14
FLAG_FACING_RIGHT = 1 << 15

# --- sprite sets and the pose offsets added to them ----------------------------------------------
SPRITE_RIDER_P1 = 0x1a80a
SPRITE_RIDER_P2 = 0x1cd6a
SPRITE_RIDER_DEAD = 0xf20
SPRITE_ENEMY_DEAD = 0x2202a
SPRITE_ENEMY_TYPE1 = 0x1f2ca
SPRITE_ENEMY_TYPE2 = 0x201ea
SPRITE_ENEMY_TYPE3 = 0x2110a
SPRITE_WALK = 0x360
SPRITE_WALK_STRIDE = 0x260
SPRITE_WALK_FACING = 0x130
SPRITE_STRIDE_FACING = 0x120
SPRITE_GLIDE_FACING = 0xd0
SPRITE_FLAP = 0x1a0
SPRITE_FLAP_FACING = 0xe0
SPRITE_MATERIALISE_PLAYER = 0x260

RIDER_ROWS_FLIGHT = 0x0d
RIDER_ROWS_STANDING = 0x13
RIDER_ROWS_STRIDE = 0x12
WALK_FRAME_STRIDE_END = 4

CORPSE_CLIP_X = 0x12f
CORPSE_KEEP_LEADING_CELL = 0x01
CORPSE_KEEP_WRAP_COLUMN = 0x02

RIDER_X_WRAP = 0x140
RIDER_X_MAX = RIDER_X_WRAP - 1
RIDER_Y_MAX = 0xb4
EDGE_ROLL_DX = 4
STEP_TIMER_RESET = 5
WALK_ANIM_RESET = 3
EDGE_DWELL_FRAMES = 0x0b
RESPAWN_ANIM_FRAMES = 5
RESPAWN_STEP_FRAMES = 0x0b
RESPAWN_LIVE_LIMIT = 8
ENEMY_TYPE_3 = 3
PLATFORM_REDRAW_MARK = 1
LAVA_DEATH_SCORE = 5

SND_NONE = 0
SND_SPAWN = 4
SND_WALK_A = 9
SND_FLAP = 0x0a
SND_WALK_B = 0x0c
SND_STEP_A = 0x0d
SND_STEP_B = 0x0f
SND_PRIORITY_FREE = 0x10

# --- spawn_points record --------------------------------------------------------------------------
SPAWN_IN_USE = 0x0
SPAWN_Y0 = 0x2
SPAWN_Y1 = 0x4
SPAWN_X0 = 0x6
SPAWN_X1 = 0x8
SPAWN_Y = 0xa
SPAWN_X = 0xc
SPAWN_PRESENT_PTR = 0x10
SPAWN_RECORD = 0x14

# --- platform_edge_table record --------------------------------------------------------------------
EDGE_Y0 = 0x0
EDGE_X0 = 0x4
EDGE_Y_PUSH = 0x8
EDGE_X_PUSH = 0x9
EDGE_PLATFORM = 0xa
EDGE_RECORD = 0xc

SCREEN_ROW_BYTES = 0xa0
CELL_BYTES = 8
CELL_PIXELS = 16
PLATFORM_COUNT = 8

# Scratch screen, clear of the program (which ends at 0x2b7ae) and far below the staged-file table.
# The noise block covers every scanline a sprite can reach AND the banner player_death paints at
# screen_base + 0x3238; a candidate that failed to write a byte would leave noise where the oracle
# left pixels.
SCREEN = 0x60000
SCREEN_NOISE = 0x8000
SCORE_ROW = SCREEN + 0x7400    # inside the noise, for the two lives rows to paint over
NO_LAVA = 0x7fffffff           # a playfield_bottom no destination in these tests can reach

# The sprite the "previously drawn" block points at. Real rider data, so the erase pass reads the
# bytes the game would, and deliberately a pose the routine itself never selects — a reconstruction
# that erased from the NEW sprite instead of the recorded one would diff.
PREV_SPRITE = SPRITE_ENEMY_TYPE1 + SPRITE_WALK

harness._lib.g_render_objects.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_render_objects.restype = None
harness._lib.g_render_objects_next.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_render_objects_next.restype = None
harness._lib.g_render_object_body.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_render_object_body.restype = None


def slot(index):
    return A_OBJECT_TABLE + index * OBJ_SIZE


def _record(index, **fields):
    """One 0x4e-byte object record: free by default, with a score row inside the scratch screen.

    The score fields are part of every record rather than a separate poke because place_rider and
    the lava death repaint the lives row through draw_lives_p1/p2, which reload A0 from a constant
    — a slot with a null score pointer would send draw_string somewhere else entirely.
    """
    rec = bytearray(OBJ_SIZE)
    struct.pack_into(">I", rec, OBJ_SCORE_PTR, SCORE_ROW + index * 0x200)
    rec[OBJ_SCORE_TEXT:OBJ_SCORE_TEXT + 10] = b"\x02\x01" + b"0000000" + b"\x00"
    rec[OBJ_LIVES] = 3
    for name, value in fields.items():
        offset, fmt = FIELDS[name]
        struct.pack_into(fmt, rec, offset, value & (0xff if fmt == "B" else
                                                    0xffff if fmt == ">H" else 0xffffffff))
    return bytes(rec)


def _base_pokes(seed=0, bottom=NO_LAVA, cursor=A_SPAWN_POINTS, priority=SND_PRIORITY_FREE,
                live=0, lock=0, flap_delay=0, present=(0,) * PLATFORM_COUNT):
    """The whole world this routine reads, staged to a quiet default: every slot free, no platform
    present this wave (so check_platform never lands), nothing playing, no lava within reach."""
    rng = random.Random(seed)
    return {
        A_OBJECT_TABLE: b"".join(_record(i) for i in range(OBJ_SLOTS)),
        A_PLATFORM_PRESENT: bytes(present),
        A_PLAYERS_ALIVE: b"\x02",
        A_LIVE_OBJECT_COUNT: bytes((live & 0xff,)),
        A_RESPAWN_LOCK: bytes((lock & 0xff,)),
        A_SPAWN_POINT_CURSOR: cursor.to_bytes(4, "big"),
        A_SND_PRIORITY: struct.pack(">H", priority),
        A_SND_OWNER: b"\x00\x00\x00\x00",
        A_PLAYFIELD_BOTTOM: (bottom & 0xffffffff).to_bytes(4, "big"),
        A_DRAW_HALF_SELECT: b"\x00",
        A_FLAP_DELAY: bytes((flap_delay & 0xff,)),
        A_SCREEN_BASE: SCREEN.to_bytes(4, "big"),
        SCREEN: rng.randbytes(SCREEN_NOISE),
    }


def _put(pokes, index, **fields):
    """Splice one record into the table-wide poke.

    Not a poke of its own at slot(index): slot 0 IS A_OBJECT_TABLE, so a second entry under that key
    would REPLACE the whole staged table and leave slots 1..13 holding the PRG's own bytes — which
    is how player 2's score pointer first came out null under a player-1 lava death.
    """
    table = bytearray(pokes[A_OBJECT_TABLE])
    table[index * OBJ_SIZE:(index + 1) * OBJ_SIZE] = _record(index, **fields)
    pokes[A_OBJECT_TABLE] = bytes(table)
    return pokes


def _body_case(pokes, index, poison=False, label=""):
    """Enter the oracle at render_object_body with A0 = this slot, and diff."""
    object_addr = slot(index)
    diffs, info = differential(
        ENTRY_RENDER_OBJECT_BODY, {"a0": object_addr, "_pokes": pokes},
        lambda lib, buf: lib.g_render_object_body(buf, object_addr), poison=poison)
    assert not diffs, f"{label} slot={index}\n{report(diffs)}"
    return info


def _oracle(pokes, index, entry=ENTRY_RENDER_OBJECT_BODY):
    """The oracle's own final image, for asserting that a case really took the branch it names."""
    regs = {} if entry == ENTRY_RENDER_OBJECTS else {"a0": slot(index)}
    final, writes, _ = emu.run(harness.make_image(pokes), entry, regs)
    return bytes(final), writes


def _word(image, addr):
    return struct.unpack_from(">H", image, addr)[0]


def _long(image, addr):
    return struct.unpack_from(">I", image, addr)[0]


# =================================================================================================
# The family's shape: three entries, one loop, one rts.
# =================================================================================================

def test_render_objects_walks_the_whole_table():
    """The head entry seeds A0 with object_table and renders every slot up to effect_table."""
    pokes = _base_pokes(seed=1)
    for index in range(OBJ_SLOTS):
        _put(pokes, index, flags=FLAG_DEAD | (index & 3), x=0x20 + index * 7, y=0x10 + index * 5,
             step=2, prev_dst=SCREEN + 0x400 + index * 0x100, prev_src=PREV_SPRITE,
             prev_rows=RIDER_ROWS_FLIGHT)
    diffs, _ = differential(ENTRY_RENDER_OBJECTS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_render_objects(buf))
    assert not diffs, report(diffs)

    final, _ = _oracle(pokes, 0, entry=ENTRY_RENDER_OBJECTS)
    for index in range(OBJ_SLOTS):
        assert final[slot(index) + OBJ_PREV_ROWS] == RIDER_ROWS_FLIGHT, f"slot {index} was skipped"


def test_render_objects_next_starts_one_slot_late():
    """The tail entry advances FIRST, so the slot it is handed is the one slot it does not draw."""
    pokes = _base_pokes(seed=2)
    for index in (5, 6):
        _put(pokes, index, flags=FLAG_DEAD, x=0x40 + index, y=0x30, step=2,
             prev_dst=SCREEN + 0x800, prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_FLIGHT)
    diffs, _ = differential(ENTRY_RENDER_OBJECTS_NEXT, {"a0": slot(5), "_pokes": pokes},
                            lambda lib, buf: lib.g_render_objects_next(buf, slot(5)))
    assert not diffs, report(diffs)

    final, _ = _oracle(pokes, 5, entry=ENTRY_RENDER_OBJECTS_NEXT)
    assert _long(final, slot(5) + OBJ_PREV_DST) == SCREEN + 0x800, "slot 5 was rendered after all"
    assert _long(final, slot(6) + OBJ_PREV_DST) != SCREEN + 0x800, "slot 6 was not rendered at all"


def test_render_objects_next_at_the_last_slot_just_returns():
    """A0 one slot below the end: the advance hits effect_table and the routine rts's untouched."""
    pokes = _base_pokes(seed=3)
    _put(pokes, OBJ_SLOTS - 1, flags=FLAG_DEAD, x=0x50, y=0x20, step=2)
    last = slot(OBJ_SLOTS - 1)
    diffs, info = differential(ENTRY_RENDER_OBJECTS_NEXT, {"a0": last, "_pokes": pokes},
                               lambda lib, buf: lib.g_render_objects_next(buf, last))
    assert not diffs, report(diffs)
    assert not [a for a in info["writes"] if a < emu.STACK_GUARD_LO], \
        "the tail entry wrote something at the end of the table"


def test_render_object_body_renders_that_slot_and_every_slot_above_it():
    """Entered mid-table it falls into the loop tail, so the slots below are untouched."""
    pokes = _base_pokes(seed=4)
    for index in range(OBJ_SLOTS):
        _put(pokes, index, flags=FLAG_DEAD, x=0x30 + index * 3, y=0x40, step=2)
    _body_case(pokes, 9, label="mid-table entry")

    final, _ = _oracle(pokes, 9)
    for index in range(9):
        assert final[slot(index) + OBJ_PREV_ROWS] == 0, f"slot {index} below the entry was rendered"
    for index in range(9, OBJ_SLOTS):
        assert final[slot(index) + OBJ_PREV_ROWS] != 0, f"slot {index} at or above it was not"


def test_free_slot_is_skipped_entirely():
    """`tst.w 0(a0)` — a zero flags word moves straight on to the next slot."""
    pokes = _base_pokes(seed=5)
    _put(pokes, OBJ_SLOTS - 1, flags=0, x=0x60, y=0x50, step=1)
    info = _body_case(pokes, OBJ_SLOTS - 1, label="free slot")
    assert not [a for a in info["writes"] if a < emu.STACK_GUARD_LO], "a free slot wrote something"


# =================================================================================================
# The flight branch: the fall-through case @ 0x12cea.
# =================================================================================================

FLYER = dict(flags=FLAG_TYPE_LO, x=0x50, y=0x40, step=2, prev_dst=SCREEN + 0x600,
             prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_FLIGHT, prev_shift=3)


def _fly_pokes(seed, index=OBJ_SLOTS - 1, **fields):
    pokes = _base_pokes(seed=seed)
    _put(pokes, index, **{**FLYER, **fields})
    return pokes


def _fly_case(seed, index=OBJ_SLOTS - 1, label="", poison=False, **fields):
    return _body_case(_fly_pokes(seed, index, **fields), index, poison=poison,
                      label=label or f"fly seed={seed:#x}")


@pytest.mark.parametrize("target_vx", (0, 1, -1, 0x7fff, -0x8000, 4, -4))
def test_flight_facing_follows_the_target_speed(target_vx):
    """`tst.w 12(a0)`: > 0 faces right, < 0 faces left, and 0 leaves the facing bit alone."""
    for facing in (0, FLAG_FACING_RIGHT):
        _fly_case(0x100 + (target_vx & 0xff) + facing, target_vx=target_vx,
                  flags=FLAG_TYPE_LO | facing)


@pytest.mark.parametrize("step,delay", ((0, 0), (1, 0), (5, 5), (6, 5), (0x7f, 0x7f), (0x80, 0x7f),
                                        (0x7f, 0x80), (0xff, 0x01), (0x01, 0xff)))
def test_troll_grabbed_caps_the_step_timer(step, delay):
    """`cmp.b flap_delay,d1 ; ble` is a SIGNED byte compare, so 0x80 counts as below 0x01."""
    pokes = _base_pokes(seed=0x200 + step * 4 + (delay & 3), flap_delay=delay)
    _put(pokes, OBJ_SLOTS - 1, **{**FLYER, "step": step, "vx": 0x1234, "target_vx": 7,
                                  "flags": FLAG_TYPE_LO | FLAG_GRABBED})
    _body_case(pokes, OBJ_SLOTS - 1, label=f"grabbed step={step:#x} delay={delay:#x}")


def test_troll_grabbed_clears_vx_and_never_steers():
    """A grabbed rider's vx is zeroed and the ease-toward-target block is skipped outright."""
    pokes = _base_pokes(seed=0x210, flap_delay=0x40)
    _put(pokes, OBJ_SLOTS - 1, **{**FLYER, "vx": 0x30, "target_vx": 0x30,
                                  "flags": FLAG_TYPE_LO | FLAG_GRABBED | FLAG_FLAP_REQUEST})
    _body_case(pokes, OBJ_SLOTS - 1, label="grabbed + flapping")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert _word(final, slot(OBJ_SLOTS - 1) + OBJ_VX) == 0, \
        "the grabbed rider kept its horizontal speed — nothing about the branch is pinned"


@pytest.mark.parametrize("vx,target", ((0, 0), (0, 3), (3, 0), (5, 3), (3, 5), (3, 3),
                                       (-1, 1), (1, -1), (0x7fff, -0x8000), (-0x8000, 0x7fff)))
def test_flap_eases_vx_one_pixel_toward_the_target(vx, target):
    """`cmp.w 12(a0),d1` then addq/subq: one step per flap, and a target of 0 disables it."""
    _fly_case(0x300 + (vx & 0x1f) * 8 + (target & 7), vx=vx, target_vx=target,
              flags=FLAG_TYPE_LO | FLAG_FLAP_REQUEST)


@pytest.mark.parametrize("vy", (0, 1, 4, -2, -3, -4, -5, 0x7fff, -0x8000, -0x7fff, 0x8001))
def test_flap_rise_saturates(vy):
    """`subq.w #2` then `cmp.w #$fffc ; bge`: the subtraction is a WORD op, so a vy of 0x8001 wraps
    to +0x7fff and reads as far ABOVE the rise limit rather than below it."""
    _fly_case(0x400 + (vy & 0xff), vy=vy, flags=FLAG_TYPE_LO | FLAG_FLAP_REQUEST)


def test_flap_is_latched_so_holding_fire_costs_one_kick():
    """bit10 gates the kick: the request without it flaps, with it falls."""
    for latched in (0, FLAG_FLAP_TAKEN):
        _fly_case(0x410 + latched, vy=0, step=1,
                  flags=FLAG_TYPE_LO | FLAG_FLAP_REQUEST | latched)


def test_releasing_the_flap_request_drops_the_latch():
    for latched in (0, FLAG_FLAP_TAKEN):
        _fly_case(0x420 + latched, step=1, flags=FLAG_TYPE_LO | latched)


@pytest.mark.parametrize("index", (0, 1, 2, 3))
def test_only_a_player_is_heard_flapping(index):
    """`cmpa.l #enemy_objects,a0 ; bcc` — the sound is skipped from the third slot up."""
    _fly_case(0x430 + index, index=index, vy=0, flags=FLAG_TYPE_LO | FLAG_FLAP_REQUEST,
              label=f"flap sound slot={index}")


@pytest.mark.parametrize("step,vy", ((1, 0), (1, 3), (1, 4), (1, 5), (1, 0x7fff), (2, 0), (0, 0)))
def test_gravity_steps_on_the_timer_and_saturates(step, vy):
    """`subq.b #1,11(a0)`: only a countdown that reaches exactly 0 adds a unit of fall speed, and
    a step timer of 0 wraps to 0xff rather than firing."""
    _fly_case(0x500 + step * 8 + (vy & 7), step=step, vy=vy)


@pytest.mark.parametrize("y,vy", ((0, -1), (0, 0), (1, -1), (2, -5), (0x7fff, 1), (0x8000, -1),
                                  (RIDER_Y_MAX, 0), (RIDER_Y_MAX - 1, 1), (RIDER_Y_MAX, 1),
                                  (0xb0, 9), (0x40, 0), (0x7ffe, 1)))
def test_vertical_step_bounces_at_the_top_and_stops_at_the_bottom(y, vy):
    """`add.w d1,4(a0) ; bge` reads N == V — the sign of the TRUE sum — so y = 0x7fff plus 1 counts
    as NON-negative even though the stored word is 0x8000."""
    _fly_case(0x600 + (y & 0xff), y=y, vy=vy, step=2)


@pytest.mark.parametrize("x,vx", ((0, -1), (0, 0), (5, -6), (RIDER_X_MAX, 1), (RIDER_X_MAX, 0),
                                  (RIDER_X_WRAP, 0), (0x7fff, 1), (0x8000, -1), (0x100, 0x40),
                                  (0x30, -0x40), (0x7ffe, 1)))
def test_horizontal_step_wraps_round_the_playfield(x, vx):
    """Same N == V hazard on the x step, then `addi.w`/`subi.w #$140` either side."""
    _fly_case(0x700 + (x & 0xff), x=x, vx=vx, step=2)


# =================================================================================================
# Choosing the sprite @ 0x12dfc, and the commit @ 0x12f4c.
# =================================================================================================

_SPRITE_FLAG_SHAPES = (
    0,                                              # enemy, type 0 -> the middle set
    FLAG_TYPE_LO,                                   # type 1
    FLAG_TYPE_HI,                                   # type 2 -> also the middle set
    FLAG_TYPE_LO | FLAG_TYPE_HI,                    # type 3
    FLAG_DEAD,                                      # dead enemy: one set whatever the type
    FLAG_DEAD | FLAG_TYPE_LO | FLAG_TYPE_HI,
    FLAG_PLAYER,                                    # player 1
    FLAG_PLAYER | FLAG_TYPE_HI,                     # player 2
    FLAG_PLAYER | FLAG_DEAD,
    FLAG_PLAYER | FLAG_TYPE_HI | FLAG_DEAD,
)


@pytest.mark.parametrize("shape", _SPRITE_FLAG_SHAPES)
@pytest.mark.parametrize("pose", (0, FLAG_FACING_RIGHT, FLAG_WINGS_UP,
                                  FLAG_WINGS_UP | FLAG_FACING_RIGHT))
def test_airborne_sprite_set_and_pose(shape, pose):
    """Every set the routine can pick, times the glide/flap poses and both facings. The flags decide
    the sprite ADDRESS, which decides the pixels, so a wrong set diffs loudly."""
    _fly_case(0x800 + shape + pose, step=2, flags=shape | pose)


def test_flapping_sprite_is_one_row_taller():
    """`addq.b #1,draw_rows` — the wings-up pose is drawn RIDER_ROWS_FLIGHT + 1 rows deep."""
    pokes = _fly_pokes(0x830, step=2, flags=FLAG_TYPE_LO | FLAG_WINGS_UP)
    _body_case(pokes, OBJ_SLOTS - 1, label="flap rows")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_DRAW_ROWS] == RIDER_ROWS_FLIGHT + 1
    assert final[slot(OBJ_SLOTS - 1) + OBJ_PREV_ROWS] == RIDER_ROWS_FLIGHT + 1


def test_redrawing_in_place_still_commits_the_same_record():
    """The `beq 0x1300e` shortcut: address, source, height and shift all unchanged skips the erase.

    Its own effect is INVISIBLE — an AND-NOT of a sprite followed by an OR of the same sprite at the
    same place leaves exactly what the OR alone would — so this case pins the state around it (that
    a second identical frame commits the same record) rather than the skip itself. Staged by
    rendering a motionless rider twice from the state the first frame left behind.
    """
    pokes = _base_pokes(seed=0x840)
    _put(pokes, OBJ_SLOTS - 1, flags=FLAG_TYPE_LO, x=0x64, y=0x30, step=5)
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)

    settled = dict(pokes)
    settled[SCREEN] = bytes(final[SCREEN:SCREEN + SCREEN_NOISE])
    settled[slot(OBJ_SLOTS - 1)] = bytes(final[slot(OBJ_SLOTS - 1):slot(OBJ_SLOTS - 1) + OBJ_SIZE])
    _body_case(settled, OBJ_SLOTS - 1, label="unchanged redraw")

    assert _long(final, slot(OBJ_SLOTS - 1) + OBJ_PREV_DST) != 0, \
        "frame one committed no destination, so frame two cannot be the unchanged case"


def test_a_slot_never_drawn_before_is_not_erased():
    """prev_dst == 0 (`tst.l 20(a0)`) means there is nothing on screen to take back off."""
    _fly_case(0x850, prev_dst=0, prev_rows=0, step=2)


@pytest.mark.parametrize("prev_rows", (1, RIDER_ROWS_FLIGHT, 0x7f, 0xff))
def test_the_erase_uses_the_recorded_block_not_the_new_one(prev_rows):
    """The mask pass reads prev_dst/prev_src/prev_rows/prev_shift, all staged away from this frame's
    values, so a reconstruction that erased the NEW sprite would diff."""
    _fly_case(0x860 + prev_rows, prev_dst=SCREEN + 0x1234, prev_src=PREV_SPRITE,
              prev_rows=prev_rows, prev_shift=11, step=2)


def test_prev_x_and_prev_y_are_committed():
    """`move.w 2(a0),16(a0)` / `move.w 4(a0),18(a0)` — the erase's wrap column reads prev_x on the
    NEXT frame, so a missed commit only shows a frame later."""
    pokes = _fly_pokes(0x870, x=0x9c, y=0x21, vx=3, vy=0, prev_x=0, prev_y=0, step=3)
    _body_case(pokes, OBJ_SLOTS - 1, label="prev x/y commit")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    obj = slot(OBJ_SLOTS - 1)
    assert _word(final, obj + OBJ_PREV_X) == _word(final, obj + OBJ_X) != 0
    assert _word(final, obj + OBJ_PREV_Y) == _word(final, obj + OBJ_Y)


# =================================================================================================
# The dead rider leaving the right-hand edge @ 0x12f96 — the ONLY reader of OBJ_FLAG_REMOVED apart
# from update_objects, and the reason this function was worth porting on its own.
# =================================================================================================

def _corpse_pokes(seed, flags, x, vx):
    pokes = _base_pokes(seed=seed)
    _put(pokes, OBJ_SLOTS - 1, flags=flags, x=x, y=0x30, vx=vx, step=3, prev_dst=SCREEN + 0x900,
         prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_FLIGHT, prev_shift=5)
    return pokes


@pytest.mark.parametrize("removed", (0, FLAG_REMOVED))
@pytest.mark.parametrize("vx", (-1, 0, 1, -0x8000, 0x7fff))
def test_bit12_flips_which_half_of_a_departing_corpse_is_drawn(removed, vx):
    """`btst #12,d0` picks between two EXACTLY OPPOSITE mappings from the drift direction onto
    draw_half_select (0x12fb0 against 0x12fca).

    The clip runs AFTER the x step, so the expectation is computed from the x the object ends on;
    the three small velocities are additionally asserted to land past CORPSE_CLIP_X, which is what
    stops the whole battery from being a row of no-clip cases.
    """
    x = 0x134 if vx < 0 else 0x131
    pokes = _corpse_pokes(0x900 + removed + (vx & 0xff), FLAG_DEAD | removed, x, vx)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"corpse removed={bool(removed)} vx={vx:#x}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    final_x = _word(final, slot(OBJ_SLOTS - 1) + OBJ_X)
    clipped = CORPSE_CLIP_X < final_x <= 0x7fff
    assert clipped == (vx in (-1, 0, 1)), f"vx={vx:#x} ended at x={final_x:#x}"

    drifting_left = vx < 0
    if removed:
        drifting_left = not drifting_left
    expected = (CORPSE_KEEP_LEADING_CELL if drifting_left else CORPSE_KEEP_WRAP_COLUMN) if clipped \
        else 0
    assert final[A_DRAW_HALF_SELECT] == expected, (
        f"draw_half_select is {final[A_DRAW_HALF_SELECT]:#x}, not {expected:#x}")


@pytest.mark.parametrize("x", (0x12e, CORPSE_CLIP_X, 0x130, 0x8000, 0xffff))
def test_the_corpse_clip_is_a_signed_x_test(x):
    """`cmpi.w #$12f,2(a0) ; ble` — signed, so an x of 0x8000 and up counts as far to the LEFT.

    The clip reads the x the step LEFT BEHIND, and that step wraps: 0xffff is negative going in but
    comes out as 0x13f and IS clipped, while 0x8000 wraps to 0x8140 and is still negative. Both are
    the signed test, measured on the value it actually sees.
    """
    for removed in (0, FLAG_REMOVED):
        pokes = _corpse_pokes(0x920 + (x & 0xff) + removed, FLAG_DEAD | removed, x, 0)
        _body_case(pokes, OBJ_SLOTS - 1, label=f"clip x={x:#x} removed={bool(removed)}")
        final, _ = _oracle(pokes, OBJ_SLOTS - 1)
        final_x = _word(final, slot(OBJ_SLOTS - 1) + OBJ_X)
        clipped = final[A_DRAW_HALF_SELECT] != 0
        assert clipped == (CORPSE_CLIP_X < final_x <= 0x7fff), \
            f"x={x:#x} ended at {final_x:#x}, clipped={clipped}"


def test_the_corpse_clip_needs_a_dead_rider_that_is_not_still_on_screen():
    """The two guards ahead of the bit-12 test: bit13 must be set and bit5 must be clear."""
    for flags, why in ((FLAG_TYPE_LO, "a live rider"),
                       (FLAG_DEAD | FLAG_CORPSE_INSIDE, "a corpse still inside the playfield"),
                       (FLAG_DEAD | FLAG_CORPSE_INSIDE | FLAG_REMOVED, "...even one being removed")):
        pokes = _corpse_pokes(0x940 + flags, flags, 0x134, -1)
        _body_case(pokes, OBJ_SLOTS - 1, label=why)
        final, _ = _oracle(pokes, OBJ_SLOTS - 1)
        assert final[A_DRAW_HALF_SELECT] == 0, f"{why} was clipped"


def test_bit12_changes_nothing_when_the_corpse_is_not_at_the_edge():
    """Away from the edge the bit is inert — the same slot renders identically either way, which is
    what makes the test above evidence about the CLIP rather than about the flags word."""
    obj = slot(OBJ_SLOTS - 1)
    finals = []
    for removed in (0, FLAG_REMOVED):
        final, _ = _oracle(_corpse_pokes(0x960, FLAG_DEAD | removed, 0x60, -1), OBJ_SLOTS - 1)
        blanked = bytearray(final[:emu.STACK_GUARD_LO])   # the oracle's own stack differs; ignore it
        struct.pack_into(">H", blanked, obj + OBJ_FLAGS, FLAG_DEAD)   # the bit is committed as-is
        finals.append(bytes(blanked))
    assert finals[0] == finals[1]


# =================================================================================================
# Standing on a platform @ 0x13200.
# =================================================================================================

# platform_table record 5 is y[33,36] x[96,189]; a rider inside it is put back on the platform by
# check_platform instead of falling off, so the walk branch survives its own frame.
WALK_PLATFORM = 5
WALK_PRESENT = tuple(0xff if i == WALK_PLATFORM else 0 for i in range(PLATFORM_COUNT))
WALKER = dict(flags=FLAG_TYPE_LO | FLAG_ON_PLATFORM, x=0x80, y=33, anim=WALK_ANIM_RESET, step=3,
              prev_dst=SCREEN + 0x700, prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_STANDING,
              prev_shift=2)


def _walk_pokes(seed, index=OBJ_SLOTS - 1, priority=SND_PRIORITY_FREE, owner=None, **fields):
    pokes = _base_pokes(seed=seed, present=WALK_PRESENT, priority=priority)
    if owner is not None:
        pokes[A_SND_OWNER] = owner.to_bytes(4, "big")
    _put(pokes, index, **{**WALKER, **fields})
    return pokes


def _walk_case(seed, index=OBJ_SLOTS - 1, label="", **kwargs):
    pokes = _walk_pokes(seed, index, **kwargs)
    _body_case(pokes, index, label=label or f"walk seed={seed:#x}")
    return pokes


@pytest.mark.parametrize("frame", range(6))
def test_walking_pose_is_one_stride_per_frame(frame):
    """`mulu.w 14(a0),d2` — the walk poses sit SPRITE_WALK_STRIDE apart, and frame 4 is the one that
    ends a stride: a row shorter, its own mirrored offset, and it wraps the counter to 0."""
    for facing in (0, FLAG_FACING_RIGHT):
        _walk_case(0xa00 + frame * 2 + bool(facing), frame=frame, vx=1, target_vx=1,
                   flags=FLAG_TYPE_LO | FLAG_ON_PLATFORM | facing)


def test_turning_round_is_the_only_way_the_walk_branch_reaches_the_stride_frame():
    """`eor.w` + `btst #15` at 0x1329c snaps the animation straight to WALK_FRAME_STRIDE_END and
    jumps the increment — which matters because 0x132ee wraps the counter back to 0 the moment the
    increment reaches 4, so a walking rider never hands that frame to the sprite select any other
    way. (A rider that LANDS mid-flap does, through check_platform; the fuzz covers that.)"""
    pokes = _walk_case(0xa20, frame=1, vx=1, target_vx=-1, label="turning -> stride frame")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_DRAW_ROWS] == RIDER_ROWS_STRIDE, "the stride pose was not the one drawn"
    assert _word(final, slot(OBJ_SLOTS - 1) + OBJ_FLAP_FRAME) == 0, "the pose did not wrap it"


@pytest.mark.parametrize("index", (0, 2))
@pytest.mark.parametrize("priority", (SND_WALK_A, SND_WALK_B, SND_PRIORITY_FREE, 0))
def test_the_footfall_sound_alternates_through_the_priority(index, priority):
    """@ 0x12ebc: with SND_WALK_A already playing the pair is swapped and the priority freed first;
    otherwise SND_WALK_A is asked for and only CLAIMED if play_sound took it. Enemies are silent."""
    _walk_case(0xa40 + index * 8 + priority, index=index, priority=priority,
               frame=1, vx=1, target_vx=-1,   # turning: the one route to the stride frame
               label=f"footfall slot={index} priority={priority:#x}")


@pytest.mark.parametrize("owner_slot", (0, 1, OBJ_SLOTS - 1))
@pytest.mark.parametrize("priority", (SND_WALK_A, SND_WALK_B, SND_STEP_A, SND_PRIORITY_FREE))
def test_the_walk_sound_is_released_only_by_its_own_owner(owner_slot, priority):
    """@ 0x12e84 — off the stride frame, `cmpa.l snd_owner,a0` plus one of the two walk indices."""
    _walk_case(0xa60 + owner_slot * 8 + priority, priority=priority, owner=slot(owner_slot),
               frame=1, vx=1, target_vx=1,
               label=f"release owner={owner_slot} priority={priority:#x}")


@pytest.mark.parametrize("vx,target", ((0, 0), (1, 1), (0, 3), (3, 0), (5, 3), (3, 5),
                                       (2, -2), (-2, 2), (-1, -1), (4, -4)))
@pytest.mark.parametrize("anim", (1, 2))
def test_walk_speed_eases_on_its_own_timer(vx, target, anim):
    """Already at the target holds the timer at its reload; otherwise it counts down and only a zero
    moves vx. A sign disagreement snaps the animation to the stride frame instead."""
    _walk_case(0xa80 + (vx & 7) * 8 + (target & 7) + anim, vx=vx, target_vx=target, anim=anim,
               frame=1)


def test_standing_still_clears_the_walk_frame_and_skips_the_vertical_step():
    """`tst.w 6(a0) ; beq` at 0x1326e branches straight to the x step, so vy is not applied."""
    pokes = _walk_case(0xaa0, vx=0, target_vx=0, vy=7, frame=2, label="standing still")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    obj = slot(OBJ_SLOTS - 1)
    assert _word(final, obj + OBJ_FLAP_FRAME) == 0
    assert _word(final, obj + OBJ_Y) == WALKER["y"], "vy was applied after all"


@pytest.mark.parametrize("frame", (0, 1, 2, 3, 5, 6, 7))
@pytest.mark.parametrize("index", (0, 2))
def test_the_footstep_sounds_ride_the_low_bits_of_the_walk_frame(frame, index):
    """`btst #0,15(a0)` then `btst #1,15(a0)` @ 0x132b2, on the frame AFTER the increment."""
    for priority in (SND_STEP_A, SND_STEP_A - 1, SND_PRIORITY_FREE):
        _walk_case(0xac0 + frame * 8 + index + priority, index=index, priority=priority,
                   frame=frame, vx=2, target_vx=2,
                   label=f"footstep frame={frame} slot={index} priority={priority:#x}")


@pytest.mark.parametrize("index", (0, 2))
def test_leaving_a_platform_swaps_bit9_for_bit6(index):
    """The take-off @ 0x1320c: bit9 off, bit6 on, bit10 off, y up one, vy and the walk frame
    cleared. The `cmpa.l #enemy_objects` that opens the block is DEAD — no branch reads its
    condition codes — so a player leaves the same way an enemy does."""
    pokes = _walk_case(0xae0 + index, index=index, vy=6, frame=2,
                       flags=FLAG_TYPE_LO | FLAG_ON_PLATFORM | FLAG_FLAP_REQUEST,
                       label=f"take-off slot={index}")
    final, _ = _oracle(pokes, index)
    flags = _word(final, slot(index) + OBJ_FLAGS)
    assert not flags & FLAG_ON_PLATFORM and flags & FLAG_WINGS_UP, "the take-off never fired"


def test_a_latched_flap_request_keeps_the_rider_walking():
    _walk_case(0xaf0, vx=1, target_vx=1, frame=1,
               flags=FLAG_TYPE_LO | FLAG_ON_PLATFORM | FLAG_FLAP_REQUEST | FLAG_FLAP_TAKEN)


# =================================================================================================
# Sinking into the lava @ 0x131a8.
# =================================================================================================

LAVA_PREV_DST = SCREEN + 0x2000
SINKER = dict(flags=FLAG_TYPE_LO | FLAG_IN_LAVA, x=0x70, y=0x90, prev_dst=LAVA_PREV_DST,
              prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_FLIGHT, prev_shift=4)


def _lava_pokes(seed, index=OBJ_SLOTS - 1, bottom=NO_LAVA, **fields):
    pokes = _base_pokes(seed=seed, bottom=bottom)
    _put(pokes, index, **{**SINKER, **fields})
    return pokes


def test_sinking_slides_one_scanline_and_redraws():
    """Above playfield_bottom the object keeps its recorded sprite and only moves down a row.

    The write-set assertion is also this file's evidence for refusing poison=True everywhere (see
    the module docstring): prev_dst is a screen POINTER the routine both writes and, on the next
    frame, dereferences, so inverting it hands the erase pass a wild address.
    """
    pokes = _lava_pokes(0xb00)
    info = _body_case(pokes, OBJ_SLOTS - 1, label="sinking")
    obj = slot(OBJ_SLOTS - 1)
    assert obj + OBJ_PREV_DST in info["writes"], "prev_dst is not committed on the sinking path"

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert _long(final, obj + OBJ_PREV_DST) == LAVA_PREV_DST + SCREEN_ROW_BYTES


@pytest.mark.parametrize("gap", (-1, 0, 1))
def test_the_lava_surface_is_a_signed_longword_bound(gap):
    """`cmp.l playfield_bottom,d1 ; blt` — the sink ends on the first row that reaches it."""
    pokes = _lava_pokes(0xb20 + gap, bottom=LAVA_PREV_DST + SCREEN_ROW_BYTES + gap)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"lava gap={gap}")
    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    died = _word(final, slot(OBJ_SLOTS - 1) + OBJ_FLAGS) != SINKER["flags"]
    assert died == (gap <= 0), f"gap={gap}: the bound moved"


@pytest.mark.parametrize("index", (0, 1, 2, 3))
@pytest.mark.parametrize("pending", (0x30, 0x34, 0x39, 0xff))
def test_reaching_the_lava_pays_a_player_and_kills_the_slot(index, pending):
    """`cmpa.l #player2,a0 ; bhi` is an UNSIGNED whole-pointer bound: only the two player slots are
    paid the 50 points, and every slot goes on through player_death."""
    pokes = _lava_pokes(0xb40 + index * 8 + (pending & 7), index=index, bottom=LAVA_PREV_DST,
                        pending=pending)
    _body_case(pokes, index, label=f"lava death slot={index} pending={pending:#x}")


@pytest.mark.parametrize("lives", (0, 1, 2, 0x80, 0xff))
def test_the_lava_death_runs_the_whole_player_death_tail(lives):
    """player_death is reached with A0 intact after score_update, which preserves it."""
    pokes = _lava_pokes(0xb60 + lives, index=0, bottom=LAVA_PREV_DST, lives=lives,
                        flags=FLAG_PLAYER | FLAG_IN_LAVA)
    _body_case(pokes, 0, label=f"lava death lives={lives:#x}")


# =================================================================================================
# The platform-edge bump @ 0x13044.
# =================================================================================================

def _edge_record(index):
    addr = A_PLATFORM_EDGE_TABLE + index * EDGE_RECORD
    y0, y1, x0, x1 = struct.unpack_from(">hhhh", harness.BASE_IMAGE, addr)
    y_push, x_push = struct.unpack_from(">bb", harness.BASE_IMAGE, addr + EDGE_Y_PUSH)
    platform = struct.unpack_from(">H", harness.BASE_IMAGE, addr + EDGE_PLATFORM)[0]
    return {"addr": addr, "y0": y0, "y1": y1, "x0": x0, "x1": x1,
            "y_push": y_push, "x_push": x_push, "platform": platform,
            "mid_x": (x0 + x1) // 2, "mid_y": (y0 + y1) // 2}


EDGE_COUNT = (A_PLATFORM_EDGE_TABLE_END - A_PLATFORM_EDGE_TABLE) // EDGE_RECORD
EDGES = [_edge_record(i) for i in range(EDGE_COUNT)]

BUMPER = dict(flags=FLAG_TYPE_LO | FLAG_PLATFORM_BUMP, step=3, prev_dst=SCREEN + 0xa00,
              prev_src=PREV_SPRITE, prev_rows=RIDER_ROWS_STANDING, prev_shift=6)


def _bump_pokes(seed, x, y, **fields):
    pokes = _base_pokes(seed=seed)
    _put(pokes, OBJ_SLOTS - 1, **{**BUMPER, "x": x & 0xffff, "y": y & 0xffff, **fields})
    return pokes


def _only_this_edge(pokes, keep):
    """Push every OTHER record's y band out of reach, so the record under test is the one that
    matches. The sweep takes the FIRST containing box, and the shipped boxes overlap."""
    for index in range(EDGE_COUNT):
        if index != keep:
            pokes[EDGES[index]["addr"] + EDGE_Y0] = struct.pack(">hh", 0x7fff, 0x7ffe)
    return pokes


@pytest.mark.parametrize("index", range(EDGE_COUNT))
def test_every_shipped_edge_box_pushes_its_own_way(index):
    """All 28 records of the real table, each isolated and hit dead centre. Between them they cover
    every push shape the game ships: y up, y down, x left, x right — never both axes at once."""
    box = EDGES[index]
    for vx in (0, 3, -3, 4, -4, 1, -1):
        pokes = _only_this_edge(_bump_pokes(0xc00 + index * 8 + (vx & 7), box["mid_x"],
                                            box["mid_y"], vx=vx, vy=-2), index)
        _body_case(pokes, OBJ_SLOTS - 1, label=f"edge {index} vx={vx}")


@pytest.mark.parametrize("index", (0, 5, 1, 2))
def test_the_edge_box_bounds_are_inclusive_on_all_four_sides(index):
    """Four `cmp.w` + blt/bgt pairs, so a coordinate exactly on an edge is INSIDE the box."""
    box = EDGES[index]
    for x, y in ((box["x0"], box["mid_y"]), (box["x0"] - 1, box["mid_y"]),
                 (box["x1"], box["mid_y"]), (box["x1"] + 1, box["mid_y"]),
                 (box["mid_x"], box["y0"]), (box["mid_x"], box["y0"] - 1),
                 (box["mid_x"], box["y1"]), (box["mid_x"], box["y1"] + 1)):
        pokes = _only_this_edge(_bump_pokes(0xc80 + index * 16 + (x & 15), x, y, vx=2), index)
        _body_case(pokes, OBJ_SLOTS - 1, label=f"edge {index} bound x={x} y={y}")


def test_a_bump_marks_its_platform_for_a_redraw():
    box = EDGES[5]
    pokes = _only_this_edge(_bump_pokes(0xca0, box["mid_x"], box["mid_y"], vx=1), 5)
    _body_case(pokes, OBJ_SLOTS - 1, label="platform redraw")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    present = final[A_PLATFORM_PRESENT:A_PLATFORM_PRESENT + PLATFORM_COUNT]
    assert present[box["platform"]] == PLATFORM_REDRAW_MARK
    assert sum(present) == PLATFORM_REDRAW_MARK, "more than one platform byte moved"


@pytest.mark.parametrize("rider_type", (0, 1, 2, 3, 4, 7))
def test_a_downward_push_parks_only_a_type_three_enemy(rider_type):
    """`andi.w #$3 ; cmpi.w #$3` — and only on a box that does NOT also push sideways. Record 5 is
    such a box: y push +1, x push 0."""
    box = EDGES[5]
    pokes = _only_this_edge(_bump_pokes(0xcc0 + rider_type, box["mid_x"], box["mid_y"], flap_timer=0,
                                        flags=rider_type | FLAG_PLATFORM_BUMP), 5)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"park type={rider_type}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    parked = final[slot(OBJ_SLOTS - 1) + OBJ_FLAP_TIMER] == EDGE_DWELL_FRAMES
    assert parked == ((rider_type & 3) == ENEMY_TYPE_3), f"type {rider_type} parked={parked}"


def test_a_box_that_pushes_both_axes_skips_the_park():
    """NOT REACHABLE FROM SHIPPED DATA — no record in platform_edge_table pushes on both axes, so
    the `tst.b 9(a1) ; bne` guarding the park is exercised only by a poked push byte."""
    box = EDGES[5]
    pokes = _only_this_edge(_bump_pokes(0xce0, box["mid_x"], box["mid_y"], vx=1, flap_timer=0,
                                        flags=ENEMY_TYPE_3 | FLAG_PLATFORM_BUMP), 5)
    pokes[box["addr"] + EDGE_Y_PUSH] = bytes((1, 1))     # push down AND right
    _body_case(pokes, OBJ_SLOTS - 1, label="both-axis push")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[slot(OBJ_SLOTS - 1) + OBJ_FLAP_TIMER] == 0, "the park ran despite the x push"


@pytest.mark.parametrize("x", (0, 1, 3, 4, 5, 0x7fff, 0x8000, 0x8003, 0x8004, 0x13c, 0x13f))
@pytest.mark.parametrize("index", (1, 2))
def test_the_sideways_roll_wraps_round_the_playfield(x, index):
    """Rolling right is `add.w` then a signed `cmp.w #$13f`; rolling left is `subq.w #4` whose `bge`
    reads N == V, so an x just above 0x8000 wraps the other way from what the stored word suggests.

    Record 1 pushes left and record 2 right; each has its x span opened out so the object's own x
    is free to be anything."""
    box = EDGES[index]
    pokes = _only_this_edge(_bump_pokes(0xd00 + index * 16 + (x & 15), x, box["mid_y"], vx=0),
                            index)
    pokes[box["addr"] + EDGE_X0] = struct.pack(">hh", -0x8000, 0x7fff)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"roll edge={index} x={x:#x}")


@pytest.mark.parametrize("vy", (-1, -3, 0, 1, 5, -0x8000, 0x7fff))
def test_a_sideways_push_cancels_a_rise(vy):
    """`tst.w 8(a0) ; bge` then `sub.w d3,4(a0)`: only a NEGATIVE vy is subtracted back out of y."""
    box = EDGES[2]
    pokes = _only_this_edge(_bump_pokes(0xd40 + (vy & 0xff), box["mid_x"], box["mid_y"], vy=vy,
                                        vx=1), 2)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"rise cancel vy={vy:#x}")


@pytest.mark.parametrize("vx", (0, 1, 2, 3, 4, 5, -1, -3, -4, -5, 0x7fff, -0x8000))
@pytest.mark.parametrize("index", (1, 2))
def test_the_roll_speed_saturates_in_each_direction(vx, index):
    """A roll turns a rider that was heading the other way round (`addq`/`subq` then `neg`) and
    otherwise eases toward +/-EDGE_ROLL_DX, each limit tested against its own `moveq` constant."""
    box = EDGES[index]
    pokes = _only_this_edge(_bump_pokes(0xd60 + index * 16 + (vx & 15), box["mid_x"], box["mid_y"],
                                        vx=vx, vy=0), index)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"roll speed edge={index} vx={vx:#x}")


@pytest.mark.parametrize("facing", (0, FLAG_FACING_RIGHT))
@pytest.mark.parametrize("vx", (0, 1, -1))
def test_an_upward_snap_starts_a_stopped_rider_walking(facing, vx):
    """`tst.w 6(a0) ; bne` at 0x13098: only a rider that had stopped is given a direction, and that
    direction is its facing. Record 0 has y push -1 and no x push."""
    box = EDGES[0]
    pokes = _only_this_edge(_bump_pokes(0xd80 + facing + (vx & 3), box["mid_x"], box["mid_y"],
                                        vx=vx, flags=FLAG_TYPE_LO | FLAG_PLATFORM_BUMP | facing), 0)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"snap facing={bool(facing)} vx={vx}")


def test_a_bump_with_no_box_re_dispatches_the_same_slot():
    """RESTART EDGE @ 0x1319c: bit14 is cleared, stored, and the body re-read from the top — so the
    object goes down whatever branch its remaining flags name, within the SAME call."""
    pokes = _bump_pokes(0xda0, 0x64, 0x0a, vy=0, prev_rows=RIDER_ROWS_FLIGHT,
                        flags=FLAG_TYPE_LO | FLAG_PLATFORM_BUMP | FLAG_FLAP_REQUEST)
    _body_case(pokes, OBJ_SLOTS - 1, label="edge miss -> restart")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    flags = _word(final, slot(OBJ_SLOTS - 1) + OBJ_FLAGS)
    assert not flags & FLAG_PLATFORM_BUMP, "the bump bit survived"
    assert flags & FLAG_FLAP_TAKEN, "the flight branch never ran after the restart"


def test_the_bump_redraws_from_the_recorded_sprite():
    """This branch picks no new pose: draw_rows and the sprite both come from the prev_* block."""
    box = EDGES[0]
    pokes = _only_this_edge(_bump_pokes(0xdc0, box["mid_x"], box["mid_y"], vx=1, prev_rows=7), 0)
    _body_case(pokes, OBJ_SLOTS - 1, label="bump redraw")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_DRAW_ROWS] == 7
    assert _long(final, A_DRAW_SRC) == PREV_SPRITE


# =================================================================================================
# The respawn @ 0x13376.
# =================================================================================================

SPAWN_COUNT = (A_SPAWN_POINTS_END - A_SPAWN_POINTS) // SPAWN_RECORD
ALL_PLATFORMS = (0xff,) * PLATFORM_COUNT
FIRST_SPAWN = A_SPAWN_POINTS + SPAWN_RECORD    # where the default cursor moves to


def _spawn_field(record, offset):
    return struct.unpack_from(">H", harness.BASE_IMAGE, record + offset)[0]


def _spawn_pokes(seed, index=OBJ_SLOTS - 1, **fields):
    """A slot awaiting respawn that has never been drawn: prev_dst 0 sends it to the search."""
    pokes = _base_pokes(seed=seed, present=ALL_PLATFORMS)
    _put(pokes, index, **{"flags": FLAG_TYPE_LO | FLAG_RESPAWN, "x": 0x30, "y": 0x30,
                          "prev_dst": 0, "prev_src": 0, "prev_rows": 0, **fields})
    return pokes


@pytest.mark.parametrize("cursor_index", range(SPAWN_COUNT))
def test_the_search_starts_one_record_past_the_cursor_and_wraps(cursor_index):
    """`addi.l #$14` then a `cmpi.l` against the table end — a round-robin, not a rescan."""
    pokes = _spawn_pokes(0xe00 + cursor_index)
    pokes[A_SPAWN_POINT_CURSOR] = (A_SPAWN_POINTS + cursor_index * SPAWN_RECORD).to_bytes(4, "big")
    _body_case(pokes, OBJ_SLOTS - 1, label=f"spawn cursor={cursor_index}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    expected = A_SPAWN_POINTS + ((cursor_index + 1) % SPAWN_COUNT) * SPAWN_RECORD
    assert _long(final, A_SPAWN_POINT_CURSOR) == expected


@pytest.mark.parametrize("lock", (0, 1, 0xff))
@pytest.mark.parametrize("live", (0, RESPAWN_LIVE_LIMIT - 1, RESPAWN_LIVE_LIMIT, 0x80, 0xff))
def test_an_enemy_queues_behind_the_lock_and_the_live_count(lock, live):
    """`tst.b respawn_lock` then a SIGNED `cmpi.b #$8,live_object_count`, so a count of 0x80 reads
    as negative and lets the respawn straight through."""
    pokes = _spawn_pokes(0xe20 + lock * 8 + live)
    pokes[A_RESPAWN_LOCK] = bytes((lock,))
    pokes[A_LIVE_OBJECT_COUNT] = bytes((live,))
    _body_case(pokes, OBJ_SLOTS - 1, label=f"enemy queue lock={lock} live={live}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    searched = _long(final, A_SPAWN_POINT_CURSOR) != A_SPAWN_POINTS
    signed_live = live - 0x100 if live >= 0x80 else live
    assert searched == (lock == 0 and signed_live < RESPAWN_LIVE_LIMIT)


@pytest.mark.parametrize("lock", (0, 1))
@pytest.mark.parametrize("live", (0, RESPAWN_LIVE_LIMIT + 4))
def test_a_player_ignores_both_gates(lock, live):
    """`btst #2,d0 ; bne` jumps the pair outright."""
    pokes = _spawn_pokes(0xe40 + lock * 4 + (live & 3), index=0, flags=FLAG_PLAYER | FLAG_RESPAWN)
    pokes[A_RESPAWN_LOCK] = bytes((lock,))
    pokes[A_LIVE_OBJECT_COUNT] = bytes((live,))
    _body_case(pokes, 0, label=f"player respawn lock={lock} live={live}")

    final, _ = _oracle(pokes, 0)
    assert _long(final, A_SPAWN_POINT_CURSOR) != A_SPAWN_POINTS, "a player was held back"


@pytest.mark.parametrize("busy", range(SPAWN_COUNT))
def test_a_spawn_point_already_in_use_is_skipped(busy):
    pokes = _spawn_pokes(0xe60 + busy)
    pokes[A_SPAWN_POINTS + busy * SPAWN_RECORD + SPAWN_IN_USE] = b"\x01"
    _body_case(pokes, OBJ_SLOTS - 1, label=f"spawn busy={busy}")


def test_every_spawn_point_taken_leaves_the_slot_alone():
    """The scan stops when it comes back round to the cursor (`cmpa.l $d14.l,a2`)."""
    pokes = _spawn_pokes(0xe70)
    for i in range(SPAWN_COUNT):
        pokes[A_SPAWN_POINTS + i * SPAWN_RECORD + SPAWN_IN_USE] = b"\x01"
    _body_case(pokes, OBJ_SLOTS - 1, label="every spawn point taken")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_LIVE_OBJECT_COUNT] == 0, "a rider was placed after all"


@pytest.mark.parametrize("absent", range(SPAWN_COUNT))
def test_a_spawn_point_whose_platform_is_gone_is_skipped(absent):
    """`movea.l 16(a2),a1 ; tst.b (a1)` — the record points AT its own platform_present byte."""
    pokes = _spawn_pokes(0xe80 + absent)
    which = _long(harness.BASE_IMAGE, A_SPAWN_POINTS + absent * SPAWN_RECORD + SPAWN_PRESENT_PTR)
    present = bytearray(ALL_PLATFORMS)
    present[which - A_PLATFORM_PRESENT] = 0
    pokes[A_PLATFORM_PRESENT] = bytes(present)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"spawn platform gone={absent}")


@pytest.mark.parametrize("edge", ("y0", "y0-1", "y1", "y1+1", "x0", "x0-1", "x1", "x1+1"))
def test_another_object_over_the_pad_blocks_it(edge):
    """The occupancy box is `blt`/`bgt` on y and `blt`/`ble` on x — the right-hand x bound being
    `ble`, an object exactly on it still blocks."""
    y0, y1, x0, x1 = struct.unpack_from(">hhhh", harness.BASE_IMAGE, FIRST_SPAWN + SPAWN_Y0)
    mid_x, mid_y = (x0 + x1) // 2, (y0 + y1) // 2
    x, y = {"y0": (mid_x, y0), "y0-1": (mid_x, y0 - 1), "y1": (mid_x, y1), "y1+1": (mid_x, y1 + 1),
            "x0": (x0, mid_y), "x0-1": (x0 - 1, mid_y), "x1": (x1, mid_y),
            "x1+1": (x1 + 1, mid_y)}[edge]

    pokes = _spawn_pokes(0xea0 + len(edge))
    _put(pokes, 3, flags=FLAG_TYPE_LO, x=x, y=y)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"occupied {edge}")


def test_a_free_slot_over_the_pad_does_not_block_it():
    """`move.w 0(a1),d1 ; beq` — a zero flags word is skipped before the box is even tested."""
    pokes = _spawn_pokes(0xeb0)
    _put(pokes, 3, flags=0, x=_spawn_field(FIRST_SPAWN, SPAWN_X0),
         y=_spawn_field(FIRST_SPAWN, SPAWN_Y0))
    _body_case(pokes, OBJ_SLOTS - 1, label="free slot over the pad")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_LIVE_OBJECT_COUNT] == 1, "the free slot blocked the pad"


def test_the_respawning_slot_does_not_block_itself():
    """`cmpa.l a0,a1 ; beq` — the sweep skips the object it is placing."""
    pokes = _spawn_pokes(0xec0, x=_spawn_field(FIRST_SPAWN, SPAWN_X0),
                         y=_spawn_field(FIRST_SPAWN, SPAWN_Y0))
    _body_case(pokes, OBJ_SLOTS - 1, label="self over the pad")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert final[A_LIVE_OBJECT_COUNT] == 1, "the object blocked its own spawn point"


@pytest.mark.parametrize("rider_type", (0, 1, 2, 3, 4, 5, 7))
def test_placing_a_rider_locks_out_the_next_one_and_announces_itself(rider_type):
    """`and.b #$7` then two `cmp.b #$3`s: types 0-3 take the lock, and every one but 3 is heard."""
    pokes = _spawn_pokes(0xee0 + rider_type, flags=rider_type | FLAG_RESPAWN)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"place type={rider_type}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert (final[A_RESPAWN_LOCK] != 0) == (rider_type <= ENEMY_TYPE_3)
    assert (_long(final, A_SND_OWNER) == slot(OBJ_SLOTS - 1)) == (rider_type < ENEMY_TYPE_3)


@pytest.mark.parametrize("index", (0, 1, 2, 3))
def test_placing_a_player_repaints_its_lives_row(index):
    """`cmpa.l #object_table` / `#player2` at 0x13488: slots 0 and 1 alone call draw_lives."""
    flags = (FLAG_PLAYER if index < 2 else FLAG_TYPE_LO) | FLAG_RESPAWN
    _body_case(_spawn_pokes(0xf00 + index, index=index, flags=flags), index,
               label=f"place lives slot={index}")


def test_placing_a_rider_stages_the_whole_record():
    """Position, both timers, the grow counter in OBJ_VX's HIGH byte, the spawn offset in OBJ_VY, a
    one-row sprite, and bit 9."""
    pokes = _spawn_pokes(0xf20, vx=0xabcd)
    _body_case(pokes, OBJ_SLOTS - 1, label="place record")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    obj = slot(OBJ_SLOTS - 1)
    assert _word(final, obj + OBJ_Y) == _spawn_field(FIRST_SPAWN, SPAWN_Y)
    assert _word(final, obj + OBJ_X) == _spawn_field(FIRST_SPAWN, SPAWN_X)
    assert _word(final, obj + OBJ_VY) == FIRST_SPAWN - A_SPAWN_POINTS
    assert final[obj + OBJ_ANIM_TIMER] == RESPAWN_ANIM_FRAMES
    assert final[obj + OBJ_STEP_TIMER] == RESPAWN_STEP_FRAMES
    assert final[obj + OBJ_VX] == RESPAWN_ANIM_FRAMES, "the grow counter is not OBJ_VX's high byte"
    assert final[obj + OBJ_VX + 1] == 0xcd, "the low half of OBJ_VX was clobbered"
    assert _word(final, obj + OBJ_FLAGS) & FLAG_ON_PLATFORM
    assert final[obj + OBJ_PREV_ROWS] == 1
    assert final[FIRST_SPAWN + SPAWN_IN_USE] == 1
    assert final[A_LIVE_OBJECT_COUNT] == 1


# --- the materialise animation ---------------------------------------------------------------------

def _grow_pokes(seed, index=OBJ_SLOTS - 1, spawn=1, **fields):
    """A rider already standing on spawn point `spawn`, mid-materialise (prev_dst non-zero)."""
    record = A_SPAWN_POINTS + spawn * SPAWN_RECORD
    pokes = _base_pokes(seed=seed, present=ALL_PLATFORMS)
    pokes[record + SPAWN_IN_USE] = b"\x01"
    _put(pokes, index, **{"flags": FLAG_TYPE_LO | FLAG_RESPAWN | FLAG_ON_PLATFORM,
                          "x": _spawn_field(record, SPAWN_X), "y": _spawn_field(record, SPAWN_Y),
                          "vy": spawn * SPAWN_RECORD, "vx": RESPAWN_ANIM_FRAMES << 8,
                          "anim": RESPAWN_ANIM_FRAMES, "step": RESPAWN_STEP_FRAMES,
                          "prev_dst": SCREEN + 0x1800, "prev_src": SPRITE_ENEMY_TYPE1,
                          "prev_rows": 1, "prev_shift": 3, **fields})
    return pokes


@pytest.mark.parametrize("prev_rows", tuple(range(1, RIDER_ROWS_STANDING + 1)) + (0x14, 0xff, 0))
def test_the_rider_grows_a_row_a_frame(prev_rows):
    """draw_rows = prev_rows + 1 and y up one, until prev_rows is already RIDER_ROWS_STANDING."""
    _body_case(_grow_pokes(0xf40 + prev_rows, prev_rows=prev_rows, vx=2 << 8), OBJ_SLOTS - 1,
               label=f"grow rows={prev_rows:#x}")


@pytest.mark.parametrize("rider_type", (0, 1, 2, 3))
@pytest.mark.parametrize("player", (0, FLAG_PLAYER))
def test_reaching_full_height_announces_and_frees_the_lock(rider_type, player):
    """@ 0x134f8: a player always announces; a non-player hands the lock back first and announces
    only if its type is at least ENEMY_TYPE_3.

    The type mask here is three bits wide, but bit 2 IS the player bit — so a "type" of 4..7 has
    already taken the player branch above, and the extra bit is unobservable on this path. Types
    0..3 are therefore the whole domain.
    """
    pokes = _grow_pokes(0xf60 + rider_type * 2 + bool(player), prev_rows=RIDER_ROWS_STANDING - 1,
                        vx=2 << 8,
                        flags=rider_type | player | FLAG_RESPAWN | FLAG_ON_PLATFORM)
    pokes[A_RESPAWN_LOCK] = b"\x01"
    _body_case(pokes, OBJ_SLOTS - 1, label=f"full height type={rider_type} player={bool(player)}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    assert (final[A_RESPAWN_LOCK] == 0) == (not player)
    announced = _long(final, A_SND_OWNER) == slot(OBJ_SLOTS - 1)
    assert announced == bool(player or (rider_type & 7) >= ENEMY_TYPE_3)


@pytest.mark.parametrize("grow", (1, 2, 5))
@pytest.mark.parametrize("step", (1, 2, 3, 4, 5, 0x0b))
def test_the_three_materialise_counters(grow, step):
    """OBJ_VX's high byte paces the frames, OBJ_STEP_TIMER the flashes within one animation step
    (its low two bits picking between the recorded sprite, select_sprite_base and a double step),
    and OBJ_ANIM_TIMER the steps themselves — running the last of them out ends the respawn."""
    for anim in (1, 2, 3):
        _body_case(_grow_pokes(0x1000 + grow * 64 + step * 4 + anim,
                               prev_rows=RIDER_ROWS_STANDING, vx=grow << 8, step=step, anim=anim),
                   OBJ_SLOTS - 1, label=f"grow={grow} step={step} anim={anim}")


@pytest.mark.parametrize("index", (0, OBJ_SLOTS - 1))
def test_a_player_materialises_from_a_further_sprite(index):
    """`btst #2,d0 ; add.l #$260,d1` @ 0x1354a, applied only once the frame counter has run out."""
    flags = (FLAG_PLAYER if index == 0 else FLAG_TYPE_LO) | FLAG_RESPAWN | FLAG_ON_PLATFORM
    _body_case(_grow_pokes(0x1100 + index, index=index, prev_rows=RIDER_ROWS_STANDING, vx=1 << 8,
                           step=3, flags=flags), index, label=f"materialise sprite slot={index}")


@pytest.mark.parametrize("anim", (1, 2, 3, 5))
def test_the_low_animation_counter_falls_back_to_the_ordinary_sprite_select(anim):
    """`cmpi.b #$2,10(a0) ; blt.w 0x12dfc` @ 0x13594 — the one edge that re-enters the sprite select
    from inside the respawn. A step timer of 5 lands on the double-step path that reaches it."""
    _body_case(_grow_pokes(0x1120 + anim, prev_rows=RIDER_ROWS_STANDING, vx=1 << 8, step=5,
                           anim=anim), OBJ_SLOTS - 1, label=f"grow tail anim={anim}")


@pytest.mark.parametrize("ends", ("flap_request", "steer", "counter"))
def test_the_respawn_finishes_and_re_dispatches_the_slot(ends):
    """RESTART EDGE @ 0x135f0: the sound and the pad are released, the three flags dropped, and the
    body re-read — so the rider walks in the SAME call."""
    fields = {"prev_rows": RIDER_ROWS_STANDING}
    if ends == "flap_request":
        fields["flags"] = FLAG_TYPE_LO | FLAG_RESPAWN | FLAG_ON_PLATFORM | FLAG_FLAP_REQUEST
    elif ends == "steer":
        fields["target_vx"] = 4
    else:
        fields.update({"vx": 1 << 8, "step": 1, "anim": 1})

    pokes = _grow_pokes(0x1140 + len(ends), **fields)
    pokes[A_SND_OWNER] = slot(OBJ_SLOTS - 1).to_bytes(4, "big")
    pokes[A_SND_PRIORITY] = struct.pack(">H", SND_SPAWN)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"respawn ends by {ends}")

    final, _ = _oracle(pokes, OBJ_SLOTS - 1)
    flags = _word(final, slot(OBJ_SLOTS - 1) + OBJ_FLAGS)
    assert not flags & FLAG_RESPAWN, "the respawn bit survived"
    assert final[FIRST_SPAWN + SPAWN_IN_USE] == 0, "the spawn pad was not released"
    # Only check_platform clears bit 9, and it is reached only from the physics branches — so a
    # cleared bit is proof the slot really was re-dispatched rather than simply finished.
    assert not flags & FLAG_ON_PLATFORM, "the restart never re-entered the body"


@pytest.mark.parametrize("owner", (OBJ_SLOTS - 1, 0, None))
def test_finishing_the_respawn_only_releases_a_sound_it_owns(owner):
    pokes = _grow_pokes(0x1160 + (owner or 0), prev_rows=RIDER_ROWS_STANDING, target_vx=4)
    pokes[A_SND_OWNER] = (0 if owner is None else slot(owner)).to_bytes(4, "big")
    pokes[A_SND_PRIORITY] = struct.pack(">H", SND_SPAWN)
    _body_case(pokes, OBJ_SLOTS - 1, label=f"respawn release owner={owner}")


# =================================================================================================
# Fuzz. Case generation is split from the check so `chunk` shards it across xdist workers, and the
# RNG is seeded ONCE outside the filter so every shard draws from the same stream.
# =================================================================================================

FUZZ_CASES = 320
FUZZ_CHUNKS = 8


def _fuzz_cases():
    rng = random.Random(ENTRY_RENDER_OBJECT_BODY)
    cases = []
    for _ in range(FUZZ_CASES):
        # One branch bit is forced on top of the random word so every branch keeps its share of the
        # cases; a uniform draw would spend most of them on the same two.
        branch = rng.choice((0, FLAG_TYPE_LO, FLAG_PLAYER, FLAG_RESPAWN, FLAG_ON_PLATFORM,
                             FLAG_PLATFORM_BUMP, FLAG_IN_LAVA, FLAG_DEAD))
        fields = {
            "flags": rng.getrandbits(16) | branch,
            "x": rng.choice((rng.randrange(RIDER_X_WRAP), rng.getrandbits(16))),
            "y": rng.choice((rng.randrange(RIDER_Y_MAX + 1), rng.getrandbits(16))),
            "vx": rng.choice((0, 1, -1, 4, -4, rng.getrandbits(16))),
            "vy": rng.choice((0, 1, -1, 4, -4, rng.getrandbits(16))),
            "anim": rng.randrange(0x100),
            "step": rng.randrange(0x100),
            "target_vx": rng.choice((0, 4, -4, rng.getrandbits(16))),
            "frame": rng.randrange(8),
            "prev_dst": rng.choice((0, (SCREEN + rng.randrange(0x4000)) & ~1)),
            "prev_src": rng.choice((PREV_SPRITE, SPRITE_ENEMY_TYPE2, SPRITE_RIDER_P1)),
            "prev_rows": rng.choice((0, 1, RIDER_ROWS_FLIGHT, RIDER_ROWS_STANDING,
                                     rng.randrange(0x100))),
            "prev_shift": rng.randrange(0x100),
            "flap_timer": rng.randrange(0x100),
            "turn_timer": rng.randrange(0x100),
            "lives": rng.choice((0, 1, 3, 0xff)),
            "pending": 0x30 + rng.randrange(10),
        }
        world = {
            "present": tuple(rng.choice((0, 1, 0xff)) for _ in range(PLATFORM_COUNT)),
            "priority": rng.choice((0, SND_WALK_A, SND_WALK_B, SND_STEP_A, SND_PRIORITY_FREE)),
            "live": rng.randrange(0x100),
            "lock": rng.choice((0, 1)),
            "flap_delay": rng.randrange(0x100),
            "cursor": A_SPAWN_POINTS + rng.randrange(SPAWN_COUNT) * SPAWN_RECORD,
        }
        cases.append((rng.randrange(OBJ_SLOTS), fields, world, rng.randrange(1 << 30)))
    return cases


_FUZZ = _fuzz_cases()


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_render_object_body_fuzz(chunk):
    ran = 0
    for case, (index, fields, world, seed) in enumerate(_FUZZ):
        if case % FUZZ_CHUNKS != chunk:
            continue
        ran += 1
        pokes = _base_pokes(seed=seed, **world)
        _put(pokes, index, **fields)
        _body_case(pokes, index, label=f"fuzz case={case}")
    assert ran, "the chunk filter rejected every case"


# =================================================================================================
# Constant pins. Every value this file restates lives somewhere else for real; a drift in a mirrored
# ADDRESS is invisible to the differential (both cores would simply read the same wrong place), so
# each is checked against its single source here. What `_defines` cannot read — a value built from
# arithmetic or from another macro — is out of reach for the same reason it is there, and the two
# such constants in render.h (RIDER_X_WRAP, RIDER_X_MAX) have their derivation pinned instead.
# =================================================================================================

def _check(defines, origin, mirrored):
    for name, value in mirrored.items():
        got = defines.get(name)
        assert got == value, (f"{name}: {origin} has "
                              f"{'no such #define' if got is None else hex(got)}, "
                              f"test has {value:#x}")


def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_RENDER_OBJECTS, "render_objects"),
                       (ENTRY_RENDER_OBJECTS_NEXT, "render_objects_next"),
                       (ENTRY_RENDER_OBJECT_BODY, "render_object_body")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_constants_match_render_h():
    _check(_defines("include/render.h"), "render.h", {
        "A_snd_owner": A_SND_OWNER,
        "A_spawn_points_END": A_SPAWN_POINTS_END,
        "OBJ_PREV_Y": OBJ_PREV_Y,
        "OBJ_RIDER_TYPE_MASK": 0x7,
        "CORPSE_CLIP_X": CORPSE_CLIP_X, "CORPSE_KEEP_LEADING_CELL": CORPSE_KEEP_LEADING_CELL,
        "CORPSE_KEEP_WRAP_COLUMN": CORPSE_KEEP_WRAP_COLUMN, "RIDER_Y_MAX": RIDER_Y_MAX,
        "FALL_VY_MAX": 4, "EDGE_ROLL_DX": EDGE_ROLL_DX,
        "STEP_TIMER_RESET": STEP_TIMER_RESET, "WALK_ANIM_RESET": WALK_ANIM_RESET,
        "EDGE_DWELL_FRAMES": EDGE_DWELL_FRAMES, "RESPAWN_ANIM_FRAMES": RESPAWN_ANIM_FRAMES,
        "RESPAWN_STEP_FRAMES": RESPAWN_STEP_FRAMES, "RESPAWN_LIVE_LIMIT": RESPAWN_LIVE_LIMIT,
        "PLATFORM_REDRAW_MARK": PLATFORM_REDRAW_MARK, "LAVA_DEATH_SCORE": LAVA_DEATH_SCORE,
        "SPRITE_RIDER_P1": SPRITE_RIDER_P1, "SPRITE_RIDER_P2": SPRITE_RIDER_P2,
        "SPRITE_RIDER_DEAD": SPRITE_RIDER_DEAD, "SPRITE_ENEMY_DEAD": SPRITE_ENEMY_DEAD,
        "SPRITE_ENEMY_TYPE1": SPRITE_ENEMY_TYPE1, "SPRITE_ENEMY_TYPE2": SPRITE_ENEMY_TYPE2,
        "SPRITE_ENEMY_TYPE3": SPRITE_ENEMY_TYPE3, "SPRITE_WALK": SPRITE_WALK,
        "SPRITE_WALK_STRIDE": SPRITE_WALK_STRIDE, "SPRITE_WALK_FACING": SPRITE_WALK_FACING,
        "SPRITE_STRIDE_FACING": SPRITE_STRIDE_FACING, "SPRITE_GLIDE_FACING": SPRITE_GLIDE_FACING,
        "SPRITE_FLAP": SPRITE_FLAP, "SPRITE_FLAP_FACING": SPRITE_FLAP_FACING,
        "SPRITE_MATERIALISE_PLAYER": SPRITE_MATERIALISE_PLAYER,
        "RIDER_ROWS_FLIGHT": RIDER_ROWS_FLIGHT, "RIDER_ROWS_STANDING": RIDER_ROWS_STANDING,
        "RIDER_ROWS_STRIDE": RIDER_ROWS_STRIDE, "WALK_FRAME_STRIDE_END": WALK_FRAME_STRIDE_END,
        "SND_NONE": SND_NONE, "SND_SPAWN": SND_SPAWN, "SND_WALK_A": SND_WALK_A,
        "SND_FLAP": SND_FLAP, "SND_WALK_B": SND_WALK_B, "SND_STEP_A": SND_STEP_A,
        "SND_STEP_B": SND_STEP_B, "SND_PRIORITY_FREE": SND_PRIORITY_FREE,
        "SPAWN_IN_USE": SPAWN_IN_USE, "SPAWN_Y0": SPAWN_Y0, "SPAWN_Y1": SPAWN_Y1,
        "SPAWN_X0": SPAWN_X0, "SPAWN_X1": SPAWN_X1, "SPAWN_Y": SPAWN_Y, "SPAWN_X": SPAWN_X,
        "SPAWN_PRESENT_PTR": SPAWN_PRESENT_PTR, "SPAWN_RECORD": SPAWN_RECORD,
    })


def test_the_half_select_bits_are_the_ones_draw_c_reads():
    """render.h names the two draw_half_select bits from the WRITER's side; src/draw.c names the
    same pair from the reader's. Neither header carries them, so they are pinned equal here."""
    body = _defines("src/draw.c")
    assert body["HALF_SELECT_SKIP_WRAP"] == CORPSE_KEEP_LEADING_CELL, \
        "keeping the leading cell means SKIPPING the wrap column"
    assert body["HALF_SELECT_SKIP_LEADING"] == CORPSE_KEEP_WRAP_COLUMN


def test_the_platform_redraw_mark_is_the_one_egg_c_writes():
    """Both layers mark a scraped platform for redraw with the same byte; src/egg.c owns the name
    PLATFORM_NEEDS_REDRAW and render.h cannot include it, so the copies are pinned equal here."""
    assert _defines("src/egg.c")["PLATFORM_NEEDS_REDRAW"] == PLATFORM_REDRAW_MARK


def test_the_flap_pair_is_player_h_s_flapping_mask():
    """control_player moves bits 6 and 11 together and player.h carries them as one mask; this pass
    tests them apart. A drift would let one layer set a bit the other never reads."""
    assert _defines("include/player.h")["OBJ_FLAGS_FLAPPING"] == FLAG_WINGS_UP | FLAG_FLAP_REQUEST


def test_shared_headers_match_the_c():
    _check(_defines("include/joust.h"), "joust.h", {
        "OBJ_FLAGS": OBJ_FLAGS, "OBJ_X": OBJ_X, "OBJ_Y": OBJ_Y, "OBJ_VX": OBJ_VX, "OBJ_VY": OBJ_VY,
        "OBJ_ANIM_TIMER": OBJ_ANIM_TIMER, "OBJ_STEP_TIMER": OBJ_STEP_TIMER,
        "OBJ_TARGET_VX": OBJ_TARGET_VX, "OBJ_FLAP_FRAME": OBJ_FLAP_FRAME,
        "OBJ_PREV_X": OBJ_PREV_X, "OBJ_PREV_DST": OBJ_PREV_DST, "OBJ_PREV_SRC": OBJ_PREV_SRC,
        "OBJ_PREV_ROWS": OBJ_PREV_ROWS, "OBJ_PREV_SHIFT": OBJ_PREV_SHIFT, "OBJ_SIZE": OBJ_SIZE,
        "SCREEN_ROW_BYTES": SCREEN_ROW_BYTES, "CELL_BYTES": CELL_BYTES, "CELL_PIXELS": CELL_PIXELS,
        "OBJ_FLAG_RESPAWN": FLAG_RESPAWN, "OBJ_FLAG_IN_LAVA": FLAG_IN_LAVA,
        "OBJ_FLAG_ON_PLATFORM": FLAG_ON_PLATFORM, "OBJ_FLAG_DEAD": FLAG_DEAD,
        "OBJ_FLAG_FACING_RIGHT": FLAG_FACING_RIGHT,
        "OBJ_FLAP_TIMER": OBJ_FLAP_TIMER, "OBJ_TURN_TIMER": OBJ_TURN_TIMER,
        "OBJ_FLAG_CORPSE_INSIDE": FLAG_CORPSE_INSIDE, "OBJ_FLAG_WINGS_UP": FLAG_WINGS_UP,
        "OBJ_FLAG_FLAP_REQUEST": FLAG_FLAP_REQUEST, "OBJ_FLAG_FLAP_TAKEN": FLAG_FLAP_TAKEN,
        "OBJ_FLAG_TYPE_LO": FLAG_TYPE_LO, "OBJ_FLAG_TYPE_HI": FLAG_TYPE_HI,
        "OBJ_FLAG_PLATFORM_BUMP": FLAG_PLATFORM_BUMP,
        "ENEMY_TYPE_3": ENEMY_TYPE_3,
    })
    _check(_defines("include/addrs.h"), "addrs.h", {
        "A_screen_base": A_SCREEN_BASE, "A_playfield_bottom": A_PLAYFIELD_BOTTOM,
        "A_respawn_lock": A_RESPAWN_LOCK,
        "A_object_table": A_OBJECT_TABLE, "A_draw_dst": A_DRAW_DST, "A_draw_src": A_DRAW_SRC,
        "A_draw_shift": A_DRAW_SHIFT, "A_draw_rows": A_DRAW_ROWS,
        "A_spawn_point_cursor": A_SPAWN_POINT_CURSOR, "A_flap_delay": A_FLAP_DELAY,
        "A_enemy_objects": A_ENEMY_OBJECTS,
    })
    _check(_defines("include/object.h"), "object.h", {
        "A_platform_present": A_PLATFORM_PRESENT, "A_live_object_count": A_LIVE_OBJECT_COUNT,
        "A_object_table_END": A_OBJECT_TABLE_END,
    })
    _check(_defines("include/world.h"), "world.h", {
        "A_spawn_points": A_SPAWN_POINTS, "OBJ_FLAG_PLAYER": FLAG_PLAYER,
        "OBJ_FLAG_GRABBED": FLAG_GRABBED, "OBJ_FLAG_REMOVED": FLAG_REMOVED,
        "OBJ_SCORE_PENDING": OBJ_SCORE_PENDING, "PLATFORM_COUNT": PLATFORM_COUNT,
    })
    _check(_defines("include/egg.h"), "egg.h", {
        "A_platform_edge_table": A_PLATFORM_EDGE_TABLE,
        "A_platform_edge_table_END": A_PLATFORM_EDGE_TABLE_END,
        "EDGE_Y_PUSH": EDGE_Y_PUSH, "EDGE_X_PUSH": EDGE_X_PUSH,
        "EDGE_PLATFORM": EDGE_PLATFORM, "EDGE_RECORD": EDGE_RECORD,
    })
    _check(_defines("include/draw.h"), "draw.h",
           {"A_player2": A_PLAYER2, "A_draw_half_select": A_DRAW_HALF_SELECT})
    _check(_defines("include/sound.h"), "sound.h", {"A_snd_priority": A_SND_PRIORITY})
    _check(_defines("include/score.h"), "score.h",
           {"A_players_alive": A_PLAYERS_ALIVE, "OBJ_SCORE_PTR": OBJ_SCORE_PTR,
            "OBJ_SCORE_SHIFT": OBJ_SCORE_SHIFT, "OBJ_SCORE_TEXT": OBJ_SCORE_TEXT,
            "OBJ_LIVES": OBJ_LIVES})


def test_the_playfield_width_is_the_scanline_geometry():
    """render.h aliases world.h's TROLL_X_WRAP rather than re-deriving 320; both are this."""
    joust_h = _defines("include/joust.h")
    assert joust_h["SCREEN_ROW_BYTES"] // joust_h["CELL_BYTES"] * joust_h["CELL_PIXELS"] == \
        RIDER_X_WRAP == RIDER_X_MAX + 1


def test_the_table_bounds_are_the_originals_own_loop_bounds():
    assert (A_OBJECT_TABLE_END - A_OBJECT_TABLE) == OBJ_SLOTS * OBJ_SIZE
    assert (A_PLATFORM_EDGE_TABLE_END - A_PLATFORM_EDGE_TABLE) == EDGE_COUNT * EDGE_RECORD
    assert (A_SPAWN_POINTS_END - A_SPAWN_POINTS) == SPAWN_COUNT * SPAWN_RECORD
    assert harness.NAME_MAP.get(A_OBJECT_TABLE_END) == "effect_table"
    assert harness.NAME_MAP.get(A_SPAWN_POINTS_END) == "egg_bonus_table"
    assert harness.NAME_MAP.get(A_ENEMY_OBJECTS) == "enemy_objects"
    assert harness.NAME_MAP.get(A_PLAYER2) == "player2"
    assert harness.NAME_MAP.get(A_PLATFORM_EDGE_TABLE) == "platform_edge_table"
