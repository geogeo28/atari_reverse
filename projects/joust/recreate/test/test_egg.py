"""Differential tests for Joust's egg subsystem (src/egg.c).

Covered here: update_eggs @ 0x12606, update_egg_draw @ 0x1285c and update_egg_physics @ 0x12a2a.

THE THREE ARE ONE UNIT, and the batteries below are shaped by how the original wires them together:

  * update_eggs walks object_table and seven of its branches leave by JUMPING FORWARD into
    update_egg_draw (three at its head, four at its erase/draw/commit tail), while its animation
    jump table adds the stub that only draws — and update_egg_draw ends `jmp 0x12612`, straight
    back into the loop advance;
  * update_egg_physics is reached with `bsr`, and its platform-edge branch ends
    `adda.w #$4,a7 ; bra.w 0x1285c`: it DISCARDS its own return address and tail-jumps into
    update_egg_draw, which returns to the loop on its behalf.

So the subsystem has exactly one `rts` (0x1261e, the loop running out of slots) and A7 balances,
which means every entry point here returns normally — no checkpoint (`stop_pc`) run is needed
anywhere in this file. It also means entering the oracle at update_egg_physics or update_egg_draw
runs THE REST OF THE OBJECT LOOP before coming back, so those two glues run it too; the tests below
that place a second egg in a later slot are what prove that continuation is really being compared.

Poisoning (`poison=True`) is used on the physics battery and nowhere else. The draw path commits
OBJ_EGG_DST / OBJ_EGG_SRC into the record, and a poisoned pointer there is dereferenced by the next
run's erase — off-image for the oracle (which drops the access) but out of bounds for the candidate,
which would crash rather than diff. The physics paths that return write no pointer that anything
later dereferences: the two hit boxes are re-staged in full before test_overlap reads them.
"""
import ctypes
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin tests at the end

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_UPDATE_EGGS = 0x12606
ENTRY_UPDATE_EGG_DRAW = 0x1285c
ENTRY_UPDATE_EGG_PHYSICS = 0x12a2a

# ---- globals (mirrors of include/egg.h, include/object.h and include/addrs.h) ----
A_PLATFORM_PRESENT = 0x10cfa
A_LIVE_OBJECT_COUNT = 0x10d0a
A_SPEED_TYPE1 = 0x10d58
A_PLAYFIELD_BOTTOM = 0x10d60
A_HIT_BOX_A = 0x10da0
A_HIT_BOX_B = 0x10db0
A_COLLISION_HIT = 0x10dc1
A_SCREEN_BASE = 0x10dde
A_DRAW_DST = 0x10de8
A_DRAW_X = 0x10dec
A_DRAW_Y = 0x10dee
A_DRAW_SRC = 0x10df0
A_DRAW_SHIFT = 0x10df4
A_DRAW_ROWS = 0x10df6
A_OBJECT_TABLE = 0x10f36
A_PLATFORM_TABLE = 0x117b4
A_PLATFORM_EDGE_TABLE = 0x117f4
A_PLATFORM_EDGE_TABLE_END = 0x11944
A_PLATFORM_SPRITES = 0x119d4
A_EGG_SPRITE_PTRS = 0x11a54

# ---- record geometry ----
OBJ_SIZE, N_OBJECTS = 0x4e, 14
N_PLATFORMS = 8
PLAT_RECORD = 8
PSPR_RECORD = 0x10
EDGE_RECORD = 0xc
N_EDGES = 28
EGG_PTR_RECORD = 8
SCREEN_ROW_BYTES = 0xa0
CELL_BYTES = 8
CELL_PIXELS = 16

# ---- egg states and the two jump-table handlers (mirrors of include/egg.h) ----
EGG_STATE_HATCH = 0x05
EGG_STATE_BOUNCE_UP = 0x0b
EGG_STATE_HATCHING = 0x12
EGG_STATE_DEATH_END = 0x19
EGG_STATE_READY = 0x21
EGG_STATE_RESTING = 0x22
EGG_STATE_THROWN = 0x23
EGG_STATE_LAVA = 0x24
EGG_HANDLER_DRAW_ONLY = 0x12854
EGG_HANDLER_REDRAW = 0x128c0

A_EGG_SPRITE_STILL = 0x1899a       # the real egg-at-rest bitmap, used as every test's egg source
EGG_SPAWN_UNDRAWN = 1 << 7

# ---- scratch, clear of the program (ends 0x2b7ae), abi.STUB (0x40000), the staged-file table
# (0xbf000) and the stack guard. The backdrop spans one 200-row screen plus slack, so an erase that
# writes nothing still shows up as a missing write against non-zero bytes.
EGG_SCREEN = 0x60000
BACKDROP_BYTES = 210 * SCREEN_ROW_BYTES
LAVA_DEPTH = 200 * SCREEN_ROW_BYTES      # init_game's playfield_bottom = screen_base + 32000

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs in (("g_update_eggs", 0), ("g_update_egg_draw", 1), ("g_update_egg_physics", 1)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = None


# ------------------------------------------------------------------ staging

_EGG_FIELDS = {"flags": (0x00, "H"), "x": (0x02, "H"), "y": (0x04, "H"), "vx": (0x06, "H"),
               "vy": (0x08, "H"), "anim_timer": (0x0a, "B"), "step_timer": (0x0b, "B"),
               "target_vx": (0x0c, "H"), "flap_frame": (0x0e, "H"), "prev_dst": (0x14, "I"),
               "egg_state": (0x1e, "B"), "hatch_timer": (0x1f, "B"), "egg_x": (0x20, "H"),
               "egg_y": (0x22, "H"), "egg_dx": (0x24, "H"), "egg_dy": (0x26, "H"),
               "roll_timer": (0x28, "B"), "fall_timer": (0x29, "B"), "egg_dst": (0x2a, "I"),
               "egg_src": (0x2e, "I"), "egg_rows": (0x32, "B"), "egg_shift": (0x33, "B"),
               "spawn_flags": (0x34, "B"), "target_y": (0x46, "H"), "hatch_mount": (0x4a, "B")}


def _egg(**fields):
    """A 0x4e-byte object record; every field not named is zero. Values are masked to their width,
    so a test can hand in a negative velocity or a signed y without spelling the two's complement."""
    record = bytearray(OBJ_SIZE)
    for name, value in fields.items():
        off, fmt = _EGG_FIELDS[name]
        mask = {"B": 0xff, "H": 0xffff, "I": 0xffffffff}[fmt]
        struct.pack_into(">" + fmt, record, off, value & mask)
    return bytes(record)


def _table(slots):
    """The whole 14-slot object_table, so no leftover of the PRG's own template steers a run."""
    table = bytearray(OBJ_SIZE * N_OBJECTS)
    for index, record in slots.items():
        table[index * OBJ_SIZE:(index + 1) * OBJ_SIZE] = record
    return bytes(table)


def _backdrop():
    """Non-zero screen bytes, so an AND-NOT erase that clears nothing is still a write to compare."""
    return bytes((0x5a + (i * 7)) & 0xff for i in range(BACKDROP_BYTES))


def _pokes(slots, present=(0,) * N_PLATFORMS, live=0, speed=2, screen=EGG_SCREEN, bottom=None,
           draw=(0, 0, 0, 0, 0, 0)):
    """The image every test in this file starts from.

    `draw` is the draw scratch as (dst, x, y, src, shift, rows) — it only matters for the two entry
    points that do NOT stage it themselves; update_eggs restages all six from the egg sub-record.
    """
    dst, x, y, src, shift, rows = draw
    return {
        A_PLATFORM_PRESENT: bytes(present),
        A_LIVE_OBJECT_COUNT: bytes([live & 0xff]),
        A_SPEED_TYPE1: struct.pack(">H", speed & 0xffff),
        A_PLAYFIELD_BOTTOM: struct.pack(">I", screen + LAVA_DEPTH if bottom is None else bottom),
        A_SCREEN_BASE: struct.pack(">I", screen),
        A_DRAW_DST: struct.pack(">IHHIBxB", dst, x & 0xffff, y & 0xffff, src, shift, rows),
        A_OBJECT_TABLE: _table(slots),
        EGG_SCREEN: _backdrop(),
    }


def _slot(index):
    return A_OBJECT_TABLE + index * OBJ_SIZE


def _differential(entry, pokes, glue, poison=False, label=""):
    diffs, _ = differential(entry, pokes, glue, poison=poison)
    assert not diffs, f"{label}\n{report(diffs)}"


# update_egg_physics' platform-edge branch ends `adda.w #$4,a7 ; bra.w update_egg_draw`: it POPS ITS
# OWN return address and lets the object loop's single `rts` return to whoever called update_eggs.
# Entering the oracle at update_egg_physics leaves no such caller, so that `rts` would pop the
# longword one past emu.STACK_TOP. Pre-poking a second sentinel there is the faithful stand-in for
# update_eggs' own return address; it lands inside the stack guard band the differential excludes,
# so it costs the comparison nothing. Every run below gets it, and the two helpers underneath are
# what say which exit a given case actually took.
_CALLER_RETURN_SLOT = emu.STACK_TOP + 4
_CALLER_SENTINEL = {_CALLER_RETURN_SLOT: emu.SENTINEL.to_bytes(4, "big")}


def _physics(pokes, slot=0, poison=False, label=""):
    object_addr = _slot(slot)
    _differential(ENTRY_UPDATE_EGG_PHYSICS, {"a0": object_addr, "_pokes": {**pokes,
                                                                          **_CALLER_SENTINEL}},
                  lambda lib, buf: lib.g_update_egg_physics(buf, object_addr),
                  poison=poison, label=label)


def _assert_tail_jumped(pokes, slot=0):
    """Prove the run really discarded its return address instead of coming back through `rts`.

    Run it WITHOUT the extra sentinel: the object loop's `rts` then pops the zero longword one past
    emu.STACK_TOP and the run never terminates, so reaching the cap is the positive evidence. A run
    that returned normally would pop the ordinary sentinel and stop. This is the counterpart of
    test_input.py's `_never_returns` — without it, a `_physics` case could "cover" the tail jump on a
    run that quietly took the `rts` instead, since the spare sentinel is simply unused then.
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(pokes), ENTRY_UPDATE_EGG_PHYSICS, {"a0": _slot(slot)})
    assert A_DRAW_DST in _physics_writes(pokes, slot), "the run never entered update_egg_draw"


def _assert_returned(pokes, slot=0):
    """The paired positive: with only the ordinary sentinel in place the run DOES reach `rts`, so it
    cannot have discarded a return address — and it never entered update_egg_draw either."""
    emu.run(harness.make_image(pokes), ENTRY_UPDATE_EGG_PHYSICS, {"a0": _slot(slot)})
    assert A_DRAW_DST not in _physics_writes(pokes, slot), "the run did enter update_egg_draw"


def _physics_writes(pokes, slot):
    """The oracle's write set for a physics run. draw_dst is the discriminator the two helpers above
    use: update_egg_physics never touches it, and update_egg_draw's first act is to store
    pos_to_screen's answer there."""
    _, writes, _ = emu.run(harness.make_image({**pokes, **_CALLER_SENTINEL}),
                           ENTRY_UPDATE_EGG_PHYSICS, {"a0": _slot(slot)})
    return writes


def _oracle_final(entry, pokes, slot=0):
    """The oracle's final image, for the handful of facts the differential cannot state on its own —
    namely which pass of a routine a staged case actually reached."""
    final, _, _ = emu.run(harness.make_image({**pokes, **_CALLER_SENTINEL}), entry,
                          {"a0": _slot(slot)})
    return final


# The program's own static tables, read once: the tests below derive box coordinates from the real
# platform_table rather than restating them (a restated box that drifted would stage the egg outside
# every platform and go green against two cores that both did nothing).
_IMAGE = harness.make_image({})


def _be16(addr):
    return int.from_bytes(_IMAGE[addr:addr + 2], "big")


def _be32(addr):
    return int.from_bytes(_IMAGE[addr:addr + 4], "big")


def _draw(pokes, slot=0, label=""):
    object_addr = _slot(slot)
    _differential(ENTRY_UPDATE_EGG_DRAW, {"a0": object_addr, "_pokes": pokes},
                  lambda lib, buf: lib.g_update_egg_draw(buf, object_addr), label=label)


def _eggs(pokes, label=""):
    _differential(ENTRY_UPDATE_EGGS, {"_pokes": pokes},
                  lambda lib, buf: lib.g_update_eggs(buf), label=label)


# ------------------------------------------------------------------ update_egg_physics @ 0x12a2a
#
# The playfield description it walks — platform_table, platform_sprites and platform_edge_table — is
# the game's own static data, left exactly as shipped; only platform_present and the egg record are
# staged. That keeps the boxes, the bitmaps and their screen offsets mutually consistent, which is
# what the pixel-collision pass needs to be reachable at all.

# Platform 6's top-left corner: the smallest platform bitmap (6 rows x 2 cells) sitting at row 40,
# cell 0. Landing an egg exactly on it is the cheapest way into the pixel-collision pass.
PLAT6_ROW = 40
PLAT6_DST_OFF = PLAT6_ROW * SCREEN_ROW_BYTES
EGG_ROWS = 7                    # what the dismount at 0x13b54 gives every egg


def _falling_egg(**fields):
    """An egg in flight over platform 6, with the fields a test does not care about pre-set."""
    base = dict(egg_state=EGG_STATE_THROWN, egg_src=A_EGG_SPRITE_STILL, egg_rows=EGG_ROWS,
                egg_dst=EGG_SCREEN + PLAT6_DST_OFF, egg_x=8, egg_y=PLAT6_ROW,
                roll_timer=2, fall_timer=2)
    base.update(fields)
    return _egg(**base)


def test_physics_no_platforms_present_is_a_no_op():
    """Every platform absent: the landing pass finds nothing, the pixel pass reads no bitmap (the
    present byte gates it), and the routine returns having written only hit_box_a."""
    _physics(_pokes({0: _falling_egg()}), poison=True)


def _platform_box(slot):
    record = A_PLATFORM_TABLE + slot * PLAT_RECORD
    return tuple(_be16(record + off) for off in (0, 2, 4, 6))     # y0, y1, x0, x1


def _only(slot):
    """platform_present with exactly one platform in play this wave."""
    return tuple(1 if i == slot else 0 for i in range(N_PLATFORMS))


# An egg sitting in the middle of platform 5's landing box, derived from the shipped table: the home
# of every test below that is about what happens AFTER a platform claims the egg.
_LANDING_BIAS = _defines("src/egg.c")["EGG_LANDING_Y_BIAS"]
_P5_Y0, _, _P5_X0, _P5_X1 = _platform_box(5)
_RESTING = dict(egg_y=_P5_Y0 + _LANDING_BIAS, egg_x=(_P5_X0 + _P5_X1) // 2)


def test_physics_landing_box_edges():
    """The landing probe sits EGG_LANDING_Y_BIAS rows above egg_y and must be inside the box on all
    four sides — one pixel out on any of them and the platform is skipped."""
    y0, y1, x0, x1 = _platform_box(6)
    present = _only(6)
    for egg_y in (y0 + _LANDING_BIAS - 1, y0 + _LANDING_BIAS,
                  y1 + _LANDING_BIAS, y1 + _LANDING_BIAS + 1):
        for egg_x in (x0 - 1, x0, x1, x1 + 1):
            _physics(_pokes({0: _falling_egg(egg_y=egg_y, egg_x=egg_x, egg_dy=1)}, present=present),
                     poison=True, label=f"egg=({egg_x:#x},{egg_y:#x})")


@pytest.mark.parametrize("slot", range(N_PLATFORMS))
def test_physics_landing_scans_every_platform_slot(slot):
    """The egg is put in platform `slot`'s own box and each platform is made present in turn: only
    that slot's present byte may claim it. This is what pins the two cursors — the platform_table
    record and the platform_present byte — advancing together."""
    y0, _, x0, _ = _platform_box(slot)
    for present_slot in range(N_PLATFORMS):
        _physics(_pokes({0: _falling_egg(egg_y=y0 + _LANDING_BIAS, egg_x=x0, egg_dy=1)},
                        present=_only(present_slot)),
                 label=f"box {slot} present {present_slot}")


def test_physics_landing_still_rising():
    """`tst.w egg_dy ; blt` — an egg still travelling upward is snapped to the platform and left
    alone: no friction step, no bounce, no hatchable state."""
    present = _only(5)
    for egg_dy in (-1, -0x8000, 0, 1):
        _physics(_pokes({0: _falling_egg(**_RESTING, egg_dy=egg_dy,
                                         egg_dx=3)}, present=present),
                 poison=True, label=f"dy={egg_dy:#x}")


def test_physics_landing_roll_friction():
    """The roll timer is a `subq.b` counter: it only steps the horizontal speed when it hits 0, and
    a stored 0 counts 256 down to 0xff — i.e. it does NOT fire."""
    present = _only(5)
    for roll_timer in (0, 1, 2, 0xff):
        for egg_dx in (-2, -1, 0, 1, 2, -0x8000, 0x7fff):
            _physics(_pokes({0: _falling_egg(**_RESTING, egg_dx=egg_dx,
                                             roll_timer=roll_timer)}, present=present),
                     poison=True, label=f"roll_timer={roll_timer} dx={egg_dx:#x}")


def test_physics_landing_bounce_loses_one_pixel():
    """`subq.w #1 ; neg.w` — a fall of n comes back as -(n - 1), so the bounce dies out, and a fall
    of exactly 1 lands on 0 and lets the settle test through."""
    present = _only(5)
    for egg_dy in (0, 1, 2, 4, 0x7fff, 0x8000):
        _physics(_pokes({0: _falling_egg(**_RESTING, egg_dy=egg_dy,
                                         roll_timer=2)}, present=present),
                 poison=True, label=f"dy={egg_dy:#x}")


def test_physics_landing_settles_to_hatchable():
    """Once both speeds reach 0 the egg becomes EGG_STATE_READY — unless a non-zero dx is still in
    play, which returns first."""
    present = _only(5)
    for egg_dx in (0, 1, -1):
        _physics(_pokes({0: _falling_egg(**_RESTING, egg_dx=egg_dx, egg_dy=1,
                                         roll_timer=2)}, present=present),
                 poison=True, label=f"dx={egg_dx:#x}")


def test_physics_landing_stuck_spot_is_nudged_instead():
    """The one spot (egg_y == 0x65, egg_x in 0x10e..0x118) where a settled egg is rolled left rather
    than made hatchable. It is on platform 3, whose box the y also has to be inside."""
    present = _only(3)
    for egg_x in (0x10d, 0x10e, 0x113, 0x118, 0x119):
        for egg_y in (0x64, 0x65, 0x66):
            _physics(_pokes({0: _falling_egg(egg_y=egg_y, egg_x=egg_x, egg_dy=1, roll_timer=2)},
                            present=present),
                     poison=True, label=f"({egg_x:#x},{egg_y:#x})")


def test_physics_pixel_pass_needs_a_present_platform():
    """No box claimed the egg, so the bitmaps are tested — but only the ones present this wave. The
    egg is placed exactly on platform 6's bitmap and platform 6's own landing box is far away."""
    for present_slot in (None, 6):
        pokes = _pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=8)}, present=_only(present_slot))
        _physics(pokes, poison=True, label=f"present={present_slot}")
    # Without this the whole battery could be staging a miss and comparing two cores that both
    # skipped the pass: collision_hit is set only by the pixel test the present byte gates.
    assert _oracle_final(ENTRY_UPDATE_EGG_PHYSICS, pokes)[A_COLLISION_HIT] != 0


def test_physics_pixel_pass_hit_box_is_restaged_per_platform():
    """hit_box_a is written before the present byte is even read, so it is restaged on every pass —
    including passes that skip the platform. Two platforms present, only the second overlapping."""
    present = tuple(1 if i in (1, 6) else 0 for i in range(N_PLATFORMS))
    _physics(_pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=8)}, present=present), poison=True)


def test_physics_platform_offset_divu_overflow():
    """`divu.w #$a0` on the platform's screen offset leaves its destination UNTOUCHED when the
    quotient will not fit in 16 bits, so hit_box_b's scanline becomes the offset's own low word
    instead of a row number — and the scanline-band test that follows then reads wildly.

    No shipped platform_sprites record is anywhere near the 0xa00000 that takes, so this is the one
    place the battery stages a table record of its own rather than using the game's data. Only the
    OFFSET is invented; the present pointer, sprite and geometry are the shipped record's.
    """
    slot = 6
    record = A_PLATFORM_SPRITES + slot * PSPR_RECORD
    overflowing = struct.pack(">IHHII", _be32(record), _be16(record + 4), _be16(record + 6),
                              _be32(record + 8), DIVU_OVERFLOW_OFFSET)
    pokes = _pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=8)}, present=_only(slot))
    pokes[record] = overflowing
    _physics(pokes, poison=True)


# The smallest multiple of one scanline whose quotient passes 0xffff — 0xa0 * 0x10001.
DIVU_OVERFLOW_OFFSET = 0xa0 * 0x10001


# The edge boxes reachable at the pixel hit above (probe y = 40 - 7 = 0x21), each exercising a
# different push, plus one x outside every box: (egg_x, what the matching record pushes).
EDGE_CASES = ((0x08, "y down"), (0x18, "x right"), (0x110, "x left"), (0x200, "no box"))


@pytest.mark.parametrize("egg_x,which", EDGE_CASES)
def test_physics_edge_push(egg_x, which):
    """The tail-jump branch: a bitmap hit sends the egg to the edge boxes, and a match pushes it out
    and then runs update_egg_draw AND the rest of the object loop without ever returning here.

    `no box` is the paired negative — the same bitmap hit with an x outside every edge box, which
    falls out of the edge loop and takes the ordinary `rts`. The two exits are told apart by which
    of _assert_tail_jumped / _assert_returned holds, not by the differential, which cannot see the
    difference on its own.
    """
    present = _only(6)
    pokes = _pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=egg_x)}, present=present,
                   draw=(EGG_SCREEN + PLAT6_DST_OFF, egg_x & 0xffff, PLAT6_ROW,
                         A_EGG_SPRITE_STILL, 0, EGG_ROWS))
    if which == "no box":
        _assert_returned(pokes)
        # The negative has to be "the edge loop ran and matched nothing", not "the pixel pass
        # missed": only the edge branch writes EGG_STATE_RESTING over the thrown egg's state.
        assert _oracle_final(ENTRY_UPDATE_EGG_PHYSICS, pokes)[_slot(0) + 0x1e] == EGG_STATE_RESTING
    else:
        _assert_tail_jumped(pokes)
    _physics(pokes, label=which)


@pytest.mark.parametrize("egg_dx", (-5, -4, -3, -1, 0, 1, 3, 4, 5, -0x8000, 0x7fff))
def test_physics_edge_roll_speed(egg_dx):
    """A sideways bump spins the egg up toward +/-EGG_ROLL_SPEED_MAX, and reverses it a pixel slower
    than it came in (`subq.w #1 ; neg.w`). Both directions, from every interesting speed."""
    present = _only(6)
    for egg_x in (0x18, 0x110):
        _physics(_pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=egg_x, egg_dx=egg_dx)},
                        present=present,
                        draw=(EGG_SCREEN + PLAT6_DST_OFF, egg_x, PLAT6_ROW,
                              A_EGG_SPRITE_STILL, 0, EGG_ROWS)),
                 label=f"x={egg_x:#x} dx={egg_dx}")


def test_physics_edge_tail_jump_runs_the_rest_of_the_loop():
    """The discarded return address is the whole point: the run continues into update_egg_draw and
    then into update_eggs' slot advance, so a LATER slot's egg is processed by the same call."""
    present = _only(6)
    later = _egg(egg_state=EGG_STATE_LAVA, egg_src=A_EGG_SPRITE_STILL, egg_rows=3,
                 egg_dst=EGG_SCREEN + 60 * SCREEN_ROW_BYTES, egg_x=0x40, egg_y=60)
    pokes = _pokes({0: _falling_egg(egg_y=PLAT6_ROW, egg_x=0x18), 5: later}, present=present,
                   draw=(EGG_SCREEN + PLAT6_DST_OFF, 0x18, PLAT6_ROW,
                         A_EGG_SPRITE_STILL, 0, EGG_ROWS))
    _assert_tail_jumped(pokes)
    _physics(pokes)


def test_physics_edge_from_the_last_slot_ends_the_loop():
    """Entering at the last slot: the tail jump's continuation finds object_table's end straight
    away, which is the only reason the routine comes back at all."""
    present = _only(6)
    pokes = _pokes({N_OBJECTS - 1: _falling_egg(egg_y=PLAT6_ROW, egg_x=0x18)}, present=present,
                   draw=(EGG_SCREEN + PLAT6_DST_OFF, 0x18, PLAT6_ROW,
                         A_EGG_SPRITE_STILL, 0, EGG_ROWS))
    _assert_tail_jumped(pokes, slot=N_OBJECTS - 1)
    _physics(pokes, slot=N_OBJECTS - 1)


# ------------------------------------------------------------------ update_egg_draw @ 0x1285c
#
# Entered with the pending (draw_x, draw_y) already staged: it turns them into a screen address,
# erases whatever the record says is on screen, draws the new sprite and records it — then falls
# into the object loop's slot advance.

DRAWN_X, DRAWN_Y = 0x44, 0x50          # where every test below asks for the sprite
ELSEWHERE_ROW = 0x14                   # and where the record claims the last one was drawn


def _screen_addr(x, y):
    """pos_to_screen's answer for (x, y): the containing cell, and the pixel offset into it."""
    return EGG_SCREEN + y * SCREEN_ROW_BYTES + (x // CELL_PIXELS) * CELL_BYTES, x % CELL_PIXELS


def _draw_pokes(record, x=DRAWN_X, y=DRAWN_Y, rows=EGG_ROWS, src=A_EGG_SPRITE_STILL,
                bottom=None, slots=None):
    slots = dict(slots or {})
    slots.setdefault(0, record)
    return _pokes(slots, bottom=bottom, draw=(0, x, y, src, 0, rows))


def _recorded(**fields):
    """A record describing a sprite last drawn at (DRAWN_X, DRAWN_Y) — i.e. exactly what this
    frame is about to draw, so update_egg_draw's four-field compare succeeds."""
    dst, shift = _screen_addr(DRAWN_X, DRAWN_Y)
    base = dict(egg_state=EGG_STATE_THROWN, egg_dst=dst, egg_src=A_EGG_SPRITE_STILL,
                egg_rows=EGG_ROWS, egg_shift=shift, egg_x=DRAWN_X, egg_y=DRAWN_Y)
    base.update(fields)
    return _egg(**base)


def test_draw_matching_record_skips_the_undrawn_flag():
    """The one observable consequence of the `beq 0x128d4` shortcut.

    Erasing a sprite and then drawing the same sprite at the same address is an AND-NOT followed by
    an OR of the same bits, which equals the OR alone — so the skipped erase itself leaves no trace.
    What the shortcut also skips is the EGG_SPAWN_UNDRAWN handling, and THAT is visible: bit 7
    survives the matching case and is cleared by every mismatching one.
    """
    for differs, label in ((dict(), "matches"),
                           (dict(egg_shift=1), "shift"),
                           (dict(egg_rows=EGG_ROWS + 1), "rows"),
                           (dict(egg_src=A_EGG_SPRITE_STILL + 0x10), "src"),
                           (dict(egg_dst=EGG_SCREEN + ELSEWHERE_ROW * SCREEN_ROW_BYTES), "dst")):
        _draw(_draw_pokes(_recorded(spawn_flags=EGG_SPAWN_UNDRAWN, **differs)), label=label)


def test_draw_undrawn_flag_replaces_the_erase():
    """An egg that has never been drawn has nothing to erase: bit 7 is toggled off instead, and the
    old screen area named by the record is left alone."""
    record = dict(egg_dst=EGG_SCREEN + ELSEWHERE_ROW * SCREEN_ROW_BYTES)
    for spawn_flags in (0, EGG_SPAWN_UNDRAWN, EGG_SPAWN_UNDRAWN | 3, 0xff, 0x7f):
        _draw(_draw_pokes(_recorded(spawn_flags=spawn_flags, **record)),
              label=f"spawn_flags={spawn_flags:#x}")


@pytest.mark.parametrize("x", (0, 1, 0xf, 0x10, 0x12f, 0x130, 0x131, 0x13f))
def test_draw_position_drives_the_erase_and_the_new_sprite(x):
    """The shift and the wrap column both come out of x: pos_to_screen splits it into a cell and an
    offset, and past EGG_WRAP_X the spilled column belongs to the previous scanline."""
    old_dst, old_shift = _screen_addr(0x100, ELSEWHERE_ROW)
    record = _recorded(egg_dst=old_dst, egg_shift=old_shift, egg_x=0x100, egg_y=ELSEWHERE_ROW)
    _draw(_draw_pokes(record, x=x), label=f"x={x:#x}")


@pytest.mark.parametrize("rows", (1, 2, EGG_ROWS, 0x1f))
def test_draw_row_counts(rows):
    """The erase counts the record's rows and the draw counts draw_rows; they need not agree, and
    the record ends up holding the new one."""
    old_dst, _ = _screen_addr(0x20, ELSEWHERE_ROW)
    _draw(_draw_pokes(_recorded(egg_dst=old_dst, egg_rows=EGG_ROWS, egg_x=0x20,
                                egg_y=ELSEWHERE_ROW), rows=rows), label=f"rows={rows}")


def test_draw_empty_slot_still_commits_the_record():
    """draw_egg_sprite returns at once when the slot carries no egg — but the six-field commit is
    outside it and runs anyway, so an empty slot's record is rewritten from the draw scratch."""
    old_dst, _ = _screen_addr(0x20, ELSEWHERE_ROW)
    for egg_state in (0, 1, EGG_STATE_THROWN):
        _draw(_draw_pokes(_recorded(egg_state=egg_state, egg_dst=old_dst, egg_x=0x20,
                                    egg_y=ELSEWHERE_ROW)), label=f"state={egg_state:#x}")


def test_draw_reaching_the_lava_line():
    """draw_egg_sprite stops at playfield_bottom, flags the egg as fallen and rewrites draw_rows to
    the rows that fitted — and the commit then stores THAT as the record's row count."""
    dst, _ = _screen_addr(DRAWN_X, DRAWN_Y)
    old_dst, _ = _screen_addr(0x20, ELSEWHERE_ROW)
    for rows_above in range(EGG_ROWS + 2):
        _draw(_draw_pokes(_recorded(egg_dst=old_dst, egg_x=0x20, egg_y=ELSEWHERE_ROW),
                          bottom=dst + rows_above * SCREEN_ROW_BYTES),
              label=f"rows_above={rows_above}")


def test_draw_continues_the_object_loop():
    """`jmp 0x12612` — update_egg_draw hands control back to the slot advance, so a later slot's egg
    is driven by the same entry. Slot 9's egg is in flight and slot 11's is sinking."""
    old_dst, _ = _screen_addr(0x20, ELSEWHERE_ROW)
    later = {9: _egg(egg_state=EGG_STATE_THROWN, egg_src=A_EGG_SPRITE_STILL, egg_rows=4,
                     egg_dst=EGG_SCREEN + 0x60 * SCREEN_ROW_BYTES, egg_x=0x60, egg_y=0x60,
                     egg_dx=2, egg_dy=1, fall_timer=1),
             11: _egg(egg_state=EGG_STATE_LAVA, egg_src=A_EGG_SPRITE_STILL, egg_rows=3,
                      egg_dst=EGG_SCREEN + 0x70 * SCREEN_ROW_BYTES, egg_x=0x80, egg_y=0x70)}
    _draw(_draw_pokes(_recorded(egg_dst=old_dst, egg_x=0x20, egg_y=ELSEWHERE_ROW), slots=later))


def test_draw_from_the_last_slot_ends_the_loop():
    old_dst, _ = _screen_addr(0x20, ELSEWHERE_ROW)
    _draw(_draw_pokes(_recorded(egg_dst=old_dst, egg_x=0x20, egg_y=ELSEWHERE_ROW),
                      slots={N_OBJECTS - 1: _recorded(egg_dst=old_dst, egg_x=0x20,
                                                      egg_y=ELSEWHERE_ROW)}),
          slot=N_OBJECTS - 1)


# ------------------------------------------------------------------ update_eggs @ 0x12606
#
# The whole subsystem from the top: every branch below is reached by staging one slot's egg
# sub-record and letting the loop find it. No platform is present unless a test says so, which makes
# update_egg_physics return immediately and keeps the in-flight cases about gravity and motion.

HOME_ROW = 0x40


def _egg_slot(**fields):
    """A slot whose egg is drawn at (HOME_ROW * 16, HOME_ROW), well inside the backdrop."""
    base = dict(egg_src=A_EGG_SPRITE_STILL, egg_rows=EGG_ROWS, egg_shift=0,
                egg_dst=EGG_SCREEN + HOME_ROW * SCREEN_ROW_BYTES, egg_x=HOME_ROW, egg_y=HOME_ROW)
    base.update(fields)
    return _egg(**base)


def test_eggs_empty_table_writes_nothing():
    """Every slot's OBJ_EGG_STATE is 0, so the loop walks all 14 and returns without a single
    store — the one case in this file where the differential compares an empty write set."""
    _eggs(_pokes({}))


@pytest.mark.parametrize("slot", range(N_OBJECTS))
def test_eggs_finds_an_egg_in_every_slot(slot):
    """`adda.w #$4e` / `cmpa.l #$137a` — the loop reaches all 14 records and stops at the table's
    end, so a stride or a bound that drifted would miss (or overrun) a slot."""
    _eggs(_pokes({slot: _egg_slot(egg_state=EGG_STATE_THROWN)}), label=f"slot {slot}")


def test_eggs_several_slots_in_one_pass():
    """Three slots in different states, driven by one call — including two that leave through
    different jump targets."""
    slots = {1: _egg_slot(egg_state=EGG_STATE_LAVA, egg_rows=3),
             4: _egg_slot(egg_state=EGG_STATE_THROWN, egg_dx=2, egg_dy=1, fall_timer=1,
                          egg_dst=EGG_SCREEN + 0x50 * SCREEN_ROW_BYTES, egg_y=0x50),
             12: _egg_slot(egg_state=3, egg_dst=EGG_SCREEN + 0x60 * SCREEN_ROW_BYTES, egg_y=0x60)}
    _eggs(_pokes(slots))


# ---- EGG_STATE_LAVA @ 0x126d2 ----

@pytest.mark.parametrize("egg_rows", (1, 2, 3, EGG_ROWS, 0xff))
def test_eggs_lava_sinks_one_row_a_frame(egg_rows):
    """draw_rows is staged from the record and decremented; while anything is left the sprite drops
    one scanline and is redrawn, and the frame it reaches zero the egg is erased and the slot
    cleared. A record row count of 1 therefore clears on the very first frame."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_LAVA, egg_rows=egg_rows)}),
          label=f"rows={egg_rows}")


# ---- EGG_STATE_READY @ 0x126fa ----

@pytest.mark.parametrize("live", (0, 7, 8, 9, 0x7f, 0x80, 0xff))
def test_eggs_ready_waits_for_a_free_object_slot(live):
    """`cmpi.b #$8,live_object_count` + `bge` is a SIGNED byte compare, so a count of 0x80 or more
    reads as negative and counts as room to spare."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_READY, hatch_timer=1)}, live=live),
          label=f"live={live}")


@pytest.mark.parametrize("hatch_timer", (0, 1, 2, 0xff))
def test_eggs_ready_hatch_timer_is_a_byte(hatch_timer):
    """`subq.b #1` on the hatch timer: only the frame it lands on 0 starts the hatch animation and
    claims the object slot, and a stored 0 wraps to 0xff instead of firing."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_READY, hatch_timer=hatch_timer)}, live=1),
          label=f"timer={hatch_timer}")


# ---- the egg_sprite_ptrs jump table @ 0x12716 ----

@pytest.mark.parametrize("egg_state", (1, 2, 3, 6, 7, 8, 9, 0xa, 0xc, 0xd, 0xe, 0xf, 0x10, 0x11,
                                       0x12, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1a, 0x1b, 0x1c, 0x1d,
                                       0x1e, 0x1f, 0x20))
def test_eggs_animation_states(egg_state):
    """Every animation state the game can produce: the table picks this frame's sprite and one of
    its two handlers — draw only, or erase / draw / commit.

    State 4 is deliberately absent: its table record is all zero, so the original would `jmp 0`.
    Nothing writes that state (5 hatches instead of stepping down to it), which is why the record
    can be null at all; test_egg_sprite_ptrs_table_is_as_shipped pins which records those are.
    """
    _eggs(_pokes({0: _egg_slot(egg_state=egg_state)}), label=f"state={egg_state:#x}")


@pytest.mark.parametrize("egg_state", (0x13, 0x1a))
def test_eggs_animation_end_marks_clear_the_slot(egg_state):
    """Stepping onto EGG_STATE_HATCHING or EGG_STATE_DEATH_END ends the animation: the egg is erased
    and the state cleared instead of being dispatched."""
    _eggs(_pokes({0: _egg_slot(egg_state=egg_state)}), label=f"state={egg_state:#x}")


def test_eggs_bounce_up_frame_is_drawn_four_rows_higher():
    """State EGG_STATE_BOUNCE_UP adds four rows to the sprite and lifts it four scanlines before
    stepping the animation on, which is the one frame that does not draw where the record says."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_BOUNCE_UP)}))


# ---- the hatch @ 0x12762 ----

@pytest.mark.parametrize("egg_x", (0, 0x9f, 0xa0, 0x13f, 0x8000, 0xffff))
def test_eggs_hatch_launch_side(egg_x):
    """`cmpi.w #$a0` + `bcc` is UNSIGNED, so an egg on the left half launches its rider from x = 0
    heading left and everything else launches from HATCH_X_RIGHT heading right, facing bit and all.
    0x8000 is the case a signed compare would get wrong."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_HATCH, egg_x=egg_x, spawn_flags=1)}, speed=3),
          label=f"x={egg_x:#x}")


@pytest.mark.parametrize("egg_y", (0, 0x3b, 0x3c, 0x3d, 0x6d, 0x6e, 0x95, 0x96, 0x97, 0xc7))
def test_eggs_hatch_altitude_bands(egg_y):
    """The three altitudes, and the quirk in the middle band: it stores HATCH_Y_MID and then
    overwrites it with HATCH_Y_TOP for its upper half."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_HATCH, egg_y=egg_y, spawn_flags=2)}),
          label=f"y={egg_y:#x}")


@pytest.mark.parametrize("spawn_flags", (0, 1, 2, 3, 0x81, 0x82, 0x83, 0xff))
def test_eggs_hatch_rider_type(spawn_flags):
    """OBJ_EGG_SPAWN_FLAGS becomes the rider's flags word (plus OBJ_FLAG_DEAD and the facing bit)
    AND the next egg state, and its signed value picks one of three sprite sets."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_HATCH, spawn_flags=spawn_flags)}),
          label=f"spawn_flags={spawn_flags:#x}")


@pytest.mark.parametrize("speed", (0, 1, 4, 0x7fff, 0x8000, 0xffff))
def test_eggs_hatch_speed_is_always_type1(speed):
    """Whatever the rider's type, the hatch reads speed_type1 — and negates it for a left launch."""
    for egg_x in (0, 0x100):
        _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_HATCH, egg_x=egg_x, spawn_flags=3)},
                     speed=speed), label=f"speed={speed:#x} x={egg_x:#x}")


# ---- in flight @ 0x12668 ----

@pytest.mark.parametrize("fall_timer", (0, 1, 2, 0xff))
def test_eggs_gravity_timer_is_a_byte(fall_timer):
    """`subq.b #1` again: gravity only steps on the frame the timer lands on 0, and a stored 0
    counts 256 frames rather than firing at once."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, fall_timer=fall_timer)}),
          label=f"timer={fall_timer}")


@pytest.mark.parametrize("egg_dy", (-4, -1, 0, 3, 4, 5, 0x7fff))
def test_eggs_gravity_stops_at_terminal_speed(egg_dy):
    """The fall speed grows by one until it is exactly EGG_FALL_SPEED_MAX — an `beq`, so a speed
    that somehow passed it keeps growing."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, egg_dy=egg_dy, fall_timer=1)}),
          label=f"dy={egg_dy}")


@pytest.mark.parametrize("egg_x,egg_dx", ((0, -1), (0, -0x140), (1, -1), (0x13f, 1), (0x13c, 4),
                                          (0x140, 0), (0x141, 0), (0x80, 0), (0x7fff, 1),
                                          (0x8000, -1)))
def test_eggs_horizontal_wrap(egg_x, egg_dx):
    """draw_x steps by the roll speed and wraps around the 320-pixel playfield. The `bge` after the
    `add.w` tests N==V — the MATHEMATICAL sign of the sum — so 0x7fff + 1 counts as positive and
    takes the right-hand clamp, not the left-hand one."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, egg_x=egg_x, egg_dx=egg_dx,
                               fall_timer=2)}),
          label=f"x={egg_x:#x} dx={egg_dx}")


@pytest.mark.parametrize("egg_y,egg_dy", ((5, -2), (2, -2), (2, -3), (0, -1), (0, 0), (0, 1),
                                          (2, 0x8000), (0x40, 4), (0x7fff, 1), (0x8000, -1)))
def test_eggs_vertical_clamp_bounces_off_the_top(egg_y, egg_dy):
    """A step that would take the egg above the screen parks it at row 0 and turns a rising speed
    back downward — but a speed that was already downward is left alone.

    The last two cases are the `add.w` + `bge` hazard: N==V is the MATHEMATICAL sign of the sum, so
    0x7fff + 1 counts as positive (no clamp) even though the stored word is negative, and
    0x8000 - 1 counts as negative even though the stored word is positive.
    """
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, egg_y=egg_y, egg_dy=egg_dy,
                               egg_dst=EGG_SCREEN + HOME_ROW * SCREEN_ROW_BYTES, fall_timer=2)}),
          label=f"y={egg_y:#x} dy={egg_dy:#x}")


@pytest.mark.parametrize("egg_state", (0x22, 0x23, 0x25, 0x40, 0x7f))
def test_eggs_every_in_flight_state(egg_state):
    """Anything above EGG_STATE_READY except EGG_STATE_LAVA runs the physics; the state itself is
    only a sprite selector for the frames that reach the table, never for these."""
    _eggs(_pokes({0: _egg_slot(egg_state=egg_state, egg_dx=1, egg_dy=1, fall_timer=1)}),
          label=f"state={egg_state:#x}")


def test_eggs_in_flight_lands_on_a_platform():
    """The full chain from the top: the loop stages the scratch, the physics claims the egg for a
    platform and returns, and gravity plus the move still run on top of the landing."""
    y0, _, x0, x1 = _platform_box(5)
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, egg_y=y0 + _LANDING_BIAS,
                               egg_x=(x0 + x1) // 2, egg_dy=2, egg_dx=1, roll_timer=1,
                               egg_dst=EGG_SCREEN + (y0 + _LANDING_BIAS) * SCREEN_ROW_BYTES)},
                 present=_only(5)))


def test_eggs_in_flight_bumps_off_a_platform_edge():
    """And the tail jump, driven from the top: the physics never returns to the gravity code, so an
    egg pushed off an edge does NOT gain a row of fall speed on the frame it is pushed."""
    _eggs(_pokes({0: _egg_slot(egg_state=EGG_STATE_THROWN, egg_y=PLAT6_ROW, egg_x=0x18,
                               egg_dst=EGG_SCREEN + PLAT6_DST_OFF, fall_timer=1)},
                 present=_only(6)))


# ------------------------------------------------------------------ the fuzz
#
# One random egg per case, driven from the top so every branch above is reachable in combination.
# The staged values are constrained rather than uniform: the record's screen address follows from
# its (x, y) so the erase lands on the backdrop, and the state is drawn from the states the GAME can
# produce — state 4 is excluded because its jump-table record is null (see test_eggs_animation_states).

FUZZ_CHUNKS = 4

_FUZZ_STATES = (1, 2, 3, EGG_STATE_HATCH, EGG_STATE_READY, EGG_STATE_RESTING, EGG_STATE_THROWN,
                EGG_STATE_LAVA, 0x25, 0x7f) + tuple(range(6, 0x21))


def _fuzz_cases():
    rng = random.Random(0x12606)                 # seeded ONCE — every chunk replays this stream
    for i in range(320):
        egg_x = rng.choice((0, 1, 0x9f, 0xa0, 0x12f, 0x130, 0x13f, rng.randrange(0x140)))
        egg_y = rng.randrange(8, 180)
        yield (i,
               dict(egg_state=rng.choice(_FUZZ_STATES), egg_x=egg_x, egg_y=egg_y,
                    egg_dst=EGG_SCREEN + egg_y * SCREEN_ROW_BYTES + (egg_x // 16) * CELL_BYTES,
                    egg_dx=rng.randint(-6, 6), egg_dy=rng.randint(-6, 6),
                    egg_rows=rng.randint(1, 12),
                    egg_shift=rng.choice((0, 1, 4, 8, 15, 16, 31, 64, 0xff)),
                    roll_timer=rng.choice((0, 1, 2, 4)), fall_timer=rng.choice((0, 1, 2, 6)),
                    hatch_timer=rng.choice((0, 1, 2)),
                    spawn_flags=rng.choice((0, 1, 2, 3, 0x81, 0x82, 0x83))),
               tuple(rng.randrange(2) for _ in range(N_PLATFORMS)),
               rng.choice((0, 7, 8, 0xff)), rng.choice((1, 2, 4, 0xffff)))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_eggs_fuzz(chunk):
    for i, fields, present, live, speed in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _eggs(_pokes({i % N_OBJECTS: _egg_slot(**fields)}, present=present, live=live, speed=speed),
              label=f"case {i}: {fields} present={present} live={live} speed={speed:#x}")


# ------------------------------------------------------------------ the shipped data this rests on

_NULL_TABLE_RECORDS = (3, 24, 31)     # states 4, EGG_STATE_DEATH_END and 0x20


def test_egg_sprite_ptrs_table_is_as_shipped():
    """The jump table drives a `jmp (a2)` on a longword read out of the image, so what the
    reconstruction may model is a property of the DATA, not of the code.

    Over every index a reachable state can produce (states 1..EGG_STATE_READY), the handler is one
    of exactly two addresses or the record is all-zero. src/egg.c dispatches on those two and treats
    anything else as "on to the next object" — a divergence from `jmp 0` that no state the game
    writes can reach: index 3 needs state 4, which nothing produces (state 5 hatches rather than
    stepping down to it), and the other two nulls sit on the states the animation clears instead of
    dispatching.
    """
    for index in range(EGG_STATE_READY):
        record = A_EGG_SPRITE_PTRS + index * EGG_PTR_RECORD
        sprite, handler = _be32(record), _be32(record + 4)
        if index in _NULL_TABLE_RECORDS:
            assert (sprite, handler) == (0, 0), f"index {index} is no longer null"
            continue
        assert handler in (EGG_HANDLER_DRAW_ONLY, EGG_HANDLER_REDRAW), \
            f"index {index} dispatches to {handler:#x}, which src/egg.c does not model"
        assert 0x10000 <= sprite < 0x2b7ae, f"index {index} sprite {sprite:#x} is off-image"


def test_platform_edge_table_shape():
    """28 records ending exactly where spawn_pad_colors begins, each naming a real platform slot and
    pushing at most one axis — which is what lets EDGE_Y_PUSH and EDGE_X_PUSH be named per axis."""
    assert A_PLATFORM_EDGE_TABLE + N_EDGES * EDGE_RECORD == A_PLATFORM_EDGE_TABLE_END
    pushes = set()
    for index in range(N_EDGES):
        record = A_PLATFORM_EDGE_TABLE + index * EDGE_RECORD
        y_push = int.from_bytes(_IMAGE[record + 8:record + 9], "big", signed=True)
        x_push = int.from_bytes(_IMAGE[record + 9:record + 10], "big", signed=True)
        assert 0 in (y_push, x_push), f"record {index} pushes both axes"
        assert _be16(record + 0xa) < N_PLATFORMS, f"record {index} names no platform"
        assert _be16(record) <= _be16(record + 2), f"record {index} has an inverted y range"
        assert _be16(record + 4) <= _be16(record + 6), f"record {index} has an inverted x range"
        pushes.add((y_push, x_push))
    assert pushes == {(-1, 0), (1, 0), (0, -1), (0, 1)}, "the four pushes the tests cover"


# ------------------------------------------------------------------ the mirrored constants
#
# Everything above restates addresses and offsets that really live in ../../names.txt and include/.
# Nothing makes a drifted mirror FAIL on its own — both cores would run against the real address,
# agree on the game's own static data and go green while the staged egg landed in dead memory — so
# the two pins below are what keep the batteries honest.

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_UPDATE_EGGS, "update_eggs"),
                       (ENTRY_UPDATE_EGG_DRAW, "update_egg_draw"),
                       (ENTRY_UPDATE_EGG_PHYSICS, "update_egg_physics")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"
    # The two jump-table handlers are addresses INSIDE those functions, so names.txt cannot name
    # them; they are pinned instead by the disassembly they were read from being still in place.
    assert EGG_HANDLER_DRAW_ONLY > ENTRY_UPDATE_EGGS
    assert ENTRY_UPDATE_EGG_DRAW < EGG_HANDLER_REDRAW < ENTRY_UPDATE_EGG_PHYSICS


def test_mirrored_constants_match_the_headers():
    """Every constant this file restates equals the one src/egg.c compiles against.

    Four headers, because the egg layer's constants are split by reach: what only it touches is in
    egg.h, the platform tables it shares with the collision layer are in object.h, the draw scratch
    and the object table are in addrs.h, and the record and screen geometry are in joust.h.
    """
    egg_h = _defines("include/egg.h")
    object_h = _defines("include/object.h")
    addrs_h = _defines("include/addrs.h")
    joust_h = _defines("include/joust.h")

    for defines, origin, mirrored in (
            (egg_h, "egg.h", {
                "A_draw_y": A_DRAW_Y, "A_speed_type1": A_SPEED_TYPE1,
                "A_platform_edge_table": A_PLATFORM_EDGE_TABLE,
                "A_platform_edge_table_END": A_PLATFORM_EDGE_TABLE_END,
                "A_egg_sprite_ptrs": A_EGG_SPRITE_PTRS,
                "A_egg_sprite_still": A_EGG_SPRITE_STILL,
                "EGG_STATE_HATCH": EGG_STATE_HATCH, "EGG_STATE_BOUNCE_UP": EGG_STATE_BOUNCE_UP,
                "EGG_STATE_HATCHING": EGG_STATE_HATCHING,
                "EGG_STATE_DEATH_END": EGG_STATE_DEATH_END,
                "EGG_STATE_READY": EGG_STATE_READY, "EGG_STATE_RESTING": EGG_STATE_RESTING,
                "EDGE_RECORD": EDGE_RECORD, "EGG_PTR_RECORD": EGG_PTR_RECORD,
                "EGG_SPAWN_UNDRAWN": EGG_SPAWN_UNDRAWN,
                "EGG_HANDLER_DRAW_ONLY": EGG_HANDLER_DRAW_ONLY,
                "EGG_HANDLER_REDRAW": EGG_HANDLER_REDRAW}),
            (object_h, "object.h", {
                "A_platform_present": A_PLATFORM_PRESENT,
                "A_live_object_count": A_LIVE_OBJECT_COUNT,
                "A_hit_box_a": A_HIT_BOX_A, "A_hit_box_b": A_HIT_BOX_B,
                "A_collision_hit": A_COLLISION_HIT, "A_draw_x": A_DRAW_X,
                "A_platform_table": A_PLATFORM_TABLE, "A_platform_sprites": A_PLATFORM_SPRITES,
                "PLAT_RECORD": PLAT_RECORD, "PSPR_RECORD": PSPR_RECORD,
                "EGG_STATE_LAVA": EGG_STATE_LAVA}),
            (addrs_h, "addrs.h", {
                "A_playfield_bottom": A_PLAYFIELD_BOTTOM, "A_screen_base": A_SCREEN_BASE,
                "A_draw_dst": A_DRAW_DST, "A_draw_src": A_DRAW_SRC,
                "A_draw_shift": A_DRAW_SHIFT, "A_draw_rows": A_DRAW_ROWS,
                "A_object_table": A_OBJECT_TABLE}),
            (joust_h, "joust.h", {
                "OBJ_SIZE": OBJ_SIZE, "SCREEN_ROW_BYTES": SCREEN_ROW_BYTES,
                "CELL_BYTES": CELL_BYTES, "CELL_PIXELS": CELL_PIXELS})):
        for name, value in mirrored.items():
            assert defines[name] == value, (f"{name}: {origin} has {defines[name]:#x}, "
                                            f"test has {value:#x}")

    # The object record, which _egg() encodes POSITIONALLY — no other assertion can catch these
    # drifting. EGG_STATE_THROWN has no counterpart in the C on purpose: nothing branches on 0x23,
    # so it is a test fixture chosen to differ from every state the routines write.
    for defines, origin, fields in (
            (joust_h, "joust.h", (("OBJ_FLAGS", 0x00), ("OBJ_X", 0x02), ("OBJ_Y", 0x04),
                                  ("OBJ_VX", 0x06), ("OBJ_VY", 0x08), ("OBJ_ANIM_TIMER", 0x0a),
                                  ("OBJ_STEP_TIMER", 0x0b), ("OBJ_TARGET_VX", 0x0c),
                                  ("OBJ_FLAP_FRAME", 0x0e),
                                  ("OBJ_PREV_DST", 0x14), ("OBJ_EGG_STATE", 0x1e),
                                  ("OBJ_EGG_X", 0x20), ("OBJ_EGG_DST", 0x2a),
                                  ("OBJ_EGG_SRC", 0x2e), ("OBJ_EGG_ROWS", 0x32),
                                  ("OBJ_EGG_SHIFT", 0x33), ("OBJ_TARGET_Y", 0x46))),
            (egg_h, "egg.h", (("OBJ_EGG_HATCH_TIMER", 0x1f),
                              ("OBJ_EGG_Y", 0x22), ("OBJ_EGG_DX", 0x24), ("OBJ_EGG_DY", 0x26),
                              ("OBJ_EGG_ROLL_TIMER", 0x28), ("OBJ_EGG_FALL_TIMER", 0x29),
                              ("OBJ_EGG_SPAWN_FLAGS", 0x34),
                              ("OBJ_HATCH_MOUNT", 0x4a)))):
        for name, off in fields:
            assert defines[name] == off, (f"{name}: {origin} has {defines[name]:#x}, "
                                          f"_egg() packs it at {off:#x}")
    for name, (off, _fmt) in _EGG_FIELDS.items():
        assert off in {v for v in list(joust_h.values()) + list(egg_h.values())}, \
            f"_egg() field `{name}` at {off:#x} is named in no header"
