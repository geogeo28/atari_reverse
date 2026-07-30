"""Differential tests for update_objects @ 0x12014 (src/objects.c) — the per-frame enemy driver.

One call walks object_table slots 2..13 and, per live enemy, writes the altitude and horizontal
speed render_object_body should ease it toward, plus the flap bits in its flags word. It always
returns (the walk is a bounded 12-slot loop and its three calls — rng_advance, draw_object_mask,
erase_egg_sprite — all return), so nothing here needs a `stop_pc` checkpoint.

TWO REGISTERS ARE INPUTS, and every case drives both:

  * D0 is the flags word, and rng_advance takes its wrap offset from it — so on the first slot it
    is the CALLER's D0, and after that the flags word the previous slot stored.
  * D2 is a scratch word (`probe` in the C) that the type-1 chase test reads on a path that never
    writes it.

NO CASE USES poison=True, and that is measured rather than assumed: almost every byte this routine
writes it also reads — the flags word it dispatches on, the chase counters, the flap timers, and
rng_ptr, which every slot steps and the next instruction reads back. A poisoned re-run therefore
tests a DIFFERENT case and still passes, which is the trap.
`test_poison_would_test_a_different_function` measures that. Attribution is bought instead with
UNWRITTEN sentinels: _DEFAULTS puts one in the two output WORDS of every staged record, and the
cases that write the AI bytes stage those explicitly (see test_dead_recovery_clears_the_ai_bytes) —
a zero default there would be indistinguishable from the clear the code performs.
"""
import ctypes
import random
import struct

import pytest

import harness
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin section at the end

# ---- entry point (Ghidra address; ../../names.txt) ----
ENTRY_UPDATE_OBJECTS = 0x12014

# ---- globals (mirrors of include/objects.h, egg.h, addrs.h and draw.h) ----
A_ACTIVE_PLAYERS = 0x10d09
A_SPEED_TYPE1 = 0x10d58        # speed_type1/2/3 are three CONTIGUOUS words...
A_SPEED_TYPE2 = 0x10d5a
A_SPEED_TYPE3 = 0x10d5c
A_CHASERS_P1 = 0x10d5e         # ...immediately followed by the two chase counters
A_CHASERS_P2 = 0x10d5f
A_RNG_PTR = 0x10dfe
A_OBJECT_TABLE = 0x10f36       # player 1's slot, and the table's base
A_PLAYER2 = 0x10f84
A_ENEMY_OBJECTS = 0x10fd2      # slot 2 — where this routine's walk starts
A_OBJECT_TABLE_END = 0x1137a

# ---- record geometry ----
OBJ_SIZE = 0x4e
N_OBJECTS = 14
N_ENEMIES = N_OBJECTS - 2

# ---- flags-word bits ----
FLAG_CORPSE_INSIDE = 1 << 5
FLAG_WINGS_UP = 1 << 6
FLAG_RESPAWN = 1 << 7
FLAG_ON_PLATFORM = 1 << 9
FLAG_FLAP_TAKEN = 1 << 10
FLAG_FLAP_REQUEST = 1 << 11
FLAG_REMOVED = 1 << 12
FLAG_DEAD = 1 << 13
FLAG_FACING_RIGHT = 0x8000
FLAG_PLAYER = 0x0004           # bit2 — a player slot, i.e. rider type 0

TYPE1, TYPE2, TYPE3 = 1, 2, 3

# ---- the dead-rider exit strip and hover ladder (include/player.h) ----
# The original carries TWO identical copies of this logic — control_player's at 0x11ea0 and
# update_objects' at 0x12438 — so src/objects.c borrows player.h's constants rather than writing
# them out again. These mirror that header and are pinned to it at the end of this file.
DEAD_EXIT_RIGHT_X = 0x13c
DEAD_EXIT_LEFT_LO = 0x130
DEAD_EXIT_LEFT_HI = 0x133
PLAYER_STEER_VX = 4
HOVER_BAND_HIGH_Y, HOVER_BAND_MID_Y = 0x28, 0x64
HOVER_TARGET_HIGH, HOVER_TARGET_MID, HOVER_TARGET_LOW = 0xa, 0x42, 0x8c

# ---- rng_advance's own constants (src/rng.c), needed to place a wrap where a case wants one ----
RNG_PTR_LIMIT = 0x17832
RNG_PTR_STEP = 2

# ---- scratch areas, all clear of the program (ends 0x2b7ae), the staged-file table (0xbf000) and
# the stack guard. The sprite block is poked NON-ZERO on purpose: draw_object_mask and
# erase_egg_sprite AND-NOT their source into the screen, so a zeroed source would leave the screen
# untouched and a candidate that skipped the call outright would still match.
SPRITE = 0x50000
SPRITE_BODY = SPRITE + 0x100   # far enough in that the mask pass's -8(a2) read stays inside
SCREEN = 0x70000
EGG_SCREEN = SCREEN + 0x400    # a second landing area, so a rider's two blits cannot mask each other

_SPRITE_BYTES = bytes((i * 37 + 11) & 0xff for i in range(0x200))
_SCREEN_BYTES = b"\xff" * 0x1000

UNWRITTEN_W = 0x5a5a           # pre-filled into output words so a missing write shows as a diff
UNWRITTEN_B = 0x5a

SPRITE_ROWS = 2                # kept small: a 0 row count would mean 256 rows (`subq.b`)
SPRITE_SHIFT = 3

FUZZ_CHUNKS = 4

_U8P = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_update_objects.argtypes = [_U8P, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_update_objects.restype = None


# ------------------------------------------------------------------ staging helpers

# Every field of the 0x4e-byte record this routine reads or writes. The blit fields (prev_*, egg_*)
# default to the scratch areas above rather than to zero, because a dead slot can reach
# draw_object_mask / erase_egg_sprite from almost any case here and a zeroed prev_dst would send
# 256 rows of AND-masks through the 68000 vector page.
_LAYOUT = {"flags": (0x00, "H"), "x": (0x02, "H"), "y": (0x04, "H"), "vx": (0x06, "H"),
           "vy": (0x08, "H"), "target_vx": (0x0c, "H"), "prev_x": (0x10, "H"),
           "prev_dst": (0x14, "I"), "prev_src": (0x18, "I"), "prev_rows": (0x1c, "B"),
           "prev_shift": (0x1d, "B"), "egg_state": (0x1e, "B"), "egg_x": (0x20, "H"),
           "egg_y": (0x22, "H"), "egg_dst": (0x2a, "I"), "egg_src": (0x2e, "I"),
           "egg_rows": (0x32, "B"), "egg_shift": (0x33, "B"), "target_y": (0x46, "H"),
           "chase_target": (0x48, "B"), "flap_timer": (0x49, "B"), "hatch_mount": (0x4a, "B"),
           "turn_timer": (0x4b, "B")}

_DEFAULTS = {"target_vx": UNWRITTEN_W, "target_y": UNWRITTEN_W,
             "prev_dst": SCREEN, "prev_src": SPRITE_BODY,
             "prev_rows": SPRITE_ROWS, "prev_shift": SPRITE_SHIFT,
             "egg_dst": EGG_SCREEN, "egg_src": SPRITE_BODY,
             "egg_rows": SPRITE_ROWS, "egg_shift": SPRITE_SHIFT}


def _obj(**fields):
    """A 0x4e-byte object record. Output fields carry sentinels and the blit fields safe scratch
    addresses (see _DEFAULTS); everything else is zero unless named."""
    rec = bytearray(OBJ_SIZE)
    for name, value in {**_DEFAULTS, **fields}.items():
        off, fmt = _LAYOUT[name]
        struct.pack_into(">" + fmt, rec, off, value & (0xffffffff if fmt == "I" else
                                                       0xffff if fmt == "H" else 0xff))
    return bytes(rec)


def _player(**fields):
    """A player slot that counts as on the board: live, not dead, not awaiting respawn."""
    return _obj(**{"flags": FLAG_PLAYER, **fields})


def _pokes(enemies, players=(None, None), speeds=(2, 3, 4), chasers=(0, 0), rng_ptr=0x11000):
    """Whole-image pokes for one update_objects call.

    `enemies` fills slots 2 upward and is padded with free (all-zero-flag) slots. The three wave
    speeds are contiguous words and the two chase counters the two bytes right after them, so each
    group is one poke.
    """
    table = bytearray()
    table += players[0] if players[0] is not None else _obj()
    table += players[1] if players[1] is not None else _obj()
    for slot in range(N_ENEMIES):
        table += enemies[slot] if slot < len(enemies) else _obj()
    assert len(table) == N_OBJECTS * OBJ_SIZE

    return {A_OBJECT_TABLE: bytes(table),
            A_ACTIVE_PLAYERS: bytes([UNWRITTEN_B]),
            A_SPEED_TYPE1: struct.pack(">HHH", *(s & 0xffff for s in speeds)),
            A_CHASERS_P1: bytes(c & 0xff for c in chasers),
            A_RNG_PTR: struct.pack(">I", rng_ptr),
            SPRITE: _SPRITE_BYTES,
            SCREEN: _SCREEN_BYTES}


def _case(enemies, note="", d0=0, d2=0, **staging):
    """Run one update_objects call under the differential. Returns the oracle's info dict.

    No case passes poison=True; test_poison_would_test_a_different_function measures why.
    """
    regs = {"d0": d0, "d2": d2, "_pokes": _pokes(enemies, **staging)}
    diffs, info = differential(ENTRY_UPDATE_OBJECTS, regs,
                               lambda lib, buf: lib.g_update_objects(buf, d0, d2))
    assert not diffs, f"{note} d0={d0:#x} d2={d2:#x}\n{report(diffs)}"
    return info


# ------------------------------------------------------------------ the walk itself

def test_walk_covers_every_enemy_slot_and_no_player_slot():
    """Twelve slots are visited, starting at enemy_objects — the two player slots are not.

    Asserted on the ORACLE's write set rather than on the diff: with an all-free table every
    stored flags word is a 0 over a 0, which no image compare can see.
    """
    info = _case([], note="empty table")
    flag_writes = {addr for addr in info["writes"]
                   if A_OBJECT_TABLE <= addr < A_OBJECT_TABLE_END
                   and (addr - A_OBJECT_TABLE) % OBJ_SIZE < 2}
    expected = {A_ENEMY_OBJECTS + slot * OBJ_SIZE + half
                for slot in range(N_ENEMIES) for half in (0, 1)}
    assert flag_writes == expected


@pytest.mark.parametrize("p1_flags,p2_flags", [
    (0, 0), (FLAG_PLAYER, 0), (0, FLAG_PLAYER), (FLAG_PLAYER, FLAG_PLAYER),
    (FLAG_PLAYER | FLAG_DEAD, FLAG_PLAYER), (FLAG_PLAYER, FLAG_PLAYER | FLAG_DEAD),
    (FLAG_PLAYER | FLAG_RESPAWN, FLAG_PLAYER), (FLAG_PLAYER, FLAG_PLAYER | FLAG_RESPAWN),
    (FLAG_DEAD, FLAG_RESPAWN), (0xffff, 0xffff), (1, 2), (FLAG_FACING_RIGHT, FLAG_ON_PLATFORM),
])
def test_active_players_prologue(p1_flags, p2_flags):
    """active_players is rebuilt from both player slots before any enemy is touched: a slot counts
    only while its flags word is non-zero and carries neither bit 13 nor bit 7."""
    _case([_obj(flags=TYPE1, y=100)],
          players=(_obj(flags=p1_flags, y=50), _obj(flags=p2_flags, y=50)),
          note=f"p1={p1_flags:#x} p2={p2_flags:#x}")


@pytest.mark.parametrize("flags", [FLAG_PLAYER, FLAG_PLAYER | FLAG_FACING_RIGHT,
                                   FLAG_ON_PLATFORM, FLAG_FLAP_REQUEST | FLAG_WINGS_UP])
def test_rider_type_zero_is_skipped(flags):
    """`andi.b #3` == 0 — a player-shaped slot in the enemy range is stored back untouched."""
    _case([_obj(flags=flags, y=100)], players=(_player(y=40), None), note=f"flags={flags:#x}")


@pytest.mark.parametrize("turn_timer", [0, 1, 2, 3, 4, 0x7f, 0x80, 0xfe, 0xff])
@pytest.mark.parametrize("rider_type", [TYPE1, TYPE2, TYPE3])
def test_turn_timer_flips_the_facing(turn_timer, rider_type):
    """`cmpi.b #3` + `bcs` is UNSIGNED, so 0x80..0xff are over the limit, not under it. At or over
    it the facing bit flips and the timer is zeroed, before any type handler runs."""
    _case([_obj(flags=rider_type | FLAG_FACING_RIGHT, y=100, turn_timer=turn_timer)],
          players=(_player(y=40), None), note=f"turn_timer={turn_timer}")


# ------------------------------------------------------------------ rider type 1 @ 0x120b0

@pytest.mark.parametrize("facing", [0, FLAG_FACING_RIGHT])
@pytest.mark.parametrize("speed", [0, 1, 7, 0x7fff, 0x8000, 0xffff])
def test_type1_respawn_aims_above_itself(facing, speed):
    """The respawn arm: clear the turn timer, aim six pixels up, and point the target speed along
    the facing — including the speed whose negation OVERFLOWS."""
    _case([_obj(flags=TYPE1 | FLAG_RESPAWN | facing, y=0x50, turn_timer=9)],
          speeds=(speed, 3, 4), players=(_player(y=40), None),
          note=f"speed={speed:#x} facing={facing:#x}")


@pytest.mark.parametrize("y,vy", [(0x50, 0), (0x50, 1), (0x50, 2), (0x50, -1), (0x50, 0x8000),
                                  (0, 5), (0x7fff, 5), (0x8000, 5)])
def test_type1_with_no_players_uses_the_target_y_tail(y, vy):
    """active_players == 0 skips every chase test and lands on 0x12588, which flaps only while the
    rider is below its target altitude AND not already rising."""
    _case([_obj(flags=TYPE1, y=y, vy=vy, target_y=0x40)], note=f"y={y:#x} vy={vy:#x}")


TYPE1_RIDER_Y = 0x50            # the rider these chase cases stand at
TYPE1_CHASE_Y_BIAS = 6          # `subq.w #6` after the `lsl.w #2`


@pytest.mark.parametrize("offset", [-2, -1, 0, 1, 2])
@pytest.mark.parametrize("speed2", [1, 3, 5])
@pytest.mark.parametrize("active", ["p1", "p2", "both"])
def test_type1_chase_threshold(offset, speed2, active):
    """`(speed_type2 << 2) - 6` lifts the player's y before the compare; at or below the rider's own
    y the climb budget runs, above it the fall-speed tail does.

    The player's y is DERIVED from the bias so the parameter straddles the real boundary at every
    speed rather than at one — which is what pins the shift and the subtraction rather than just
    "some bias was applied". Varying speed_type2 also moves the budget the climb tail then spends,
    so both of its branches are reached here too.
    """
    player_y = TYPE1_RIDER_Y + ((speed2 << 2) - TYPE1_CHASE_Y_BIAS) + offset
    p1 = _player(y=player_y) if active in ("p1", "both") else None
    p2 = _player(y=player_y) if active in ("p2", "both") else None
    _case([_obj(flags=TYPE1, y=TYPE1_RIDER_Y, vy=4, flap_timer=6, target_y=0x40)],
          players=(p1, p2), speeds=(2, speed2, 4),
          note=f"player_y={player_y:#x} speed2={speed2} active={active}")


@pytest.mark.parametrize("d2", [0, 6, 7, 8, 0x30, 0x8000, 0xffff])
def test_type1_reads_a_probe_it_never_wrote(d2):
    """With ONLY player 2 on the board the `move.w speed_type2,d2` that sets the chase bias up is
    skipped, and the player-2 compare runs on whatever D2 already held.

    The staged y values put the branch right on the boundary: probe 7 makes the lifted player y
    equal the rider's own y (chase), probe 6 puts it one above (no chase). A reconstruction that
    treated the bias as 0 — or recomputed it — would take the other branch and store a different
    flags word.
    """
    _case([_obj(flags=TYPE1, y=0x50, vy=4, flap_timer=6, target_y=0x40)],
          players=(None, _player(y=0x57)), d2=d2, note=f"d2={d2:#x}")


def test_type1_probe_survives_from_the_previous_slot():
    """The probe outlives one slot: a type-2 rider claiming a target leaves speed_type3 in D2, and
    the type-1 rider in the NEXT slot then chases off that value.

    speed_type3 is 7 here, the boundary value the case above pins, so a candidate that reset the
    probe per slot lands on the other branch.
    """
    _case([_obj(flags=TYPE2, y=0x20, target_y=0x10),
           _obj(flags=TYPE1, y=0x50, vy=4, flap_timer=6, target_y=0x40)],
          players=(None, _player(y=0x57)), speeds=(2, 3, 7), chasers=(0, 0),
          note="type2 leaves speed_type3 in the probe")


# ------------------------------------------------------------------ rider type 2 @ 0x12148

# One cursor per value of (rng word & 7), found by scanning the program text rng_advance walks.
# Only the low TWO bits reach the respawn altitude, so covering all eight is what shows the mask
# is 3 and not 7 — the words in any one neighbourhood of 68000 code are far too aligned to.
RNG_CURSORS_BY_LOW_BITS = (0x10002, 0x10000, 0x10014, 0x102b4,
                           0x10038, 0x1009a, 0x1000e, 0x10084)


@pytest.mark.parametrize("rng_ptr", RNG_CURSORS_BY_LOW_BITS)
def test_type2_respawn_jitter_comes_from_the_rng_cursor(rng_ptr):
    """`move.w (a1)+,d2 ; andi.w #$3` — two bits of the program's own bytes nudge the respawn
    altitude. The cursor is read AFTER rng_advance stepped it, so each start lands on a different
    word."""
    _case([_obj(flags=TYPE2 | FLAG_RESPAWN, y=0x50, chase_target=3, turn_timer=9)],
          rng_ptr=rng_ptr, players=(_player(y=40), None), note=f"rng_ptr={rng_ptr:#x}")


@pytest.mark.parametrize("chasers", [(0, 0), (1, 2), (0xff, 0xff), (0x7f, 0x80)])
def test_type2_with_no_players_clears_both_counters(chasers):
    """`clr.w $d5e` is ONE word store, so losing every player zeroes chasers_p1 AND chasers_p2."""
    _case([_obj(flags=TYPE2, y=0x50, chase_target=1, target_y=0x40)],
          chasers=chasers, note=f"chasers={chasers}")


@pytest.mark.parametrize("chasers", [(0, 0), (1, 0), (0, 1), (3, 3), (4, 4), (2, 3), (3, 2),
                                     (0xff, 0), (0, 0xff), (0x80, 0x7f)])
@pytest.mark.parametrize("active", ["p1", "p2", "both"])
def test_type2_claims_a_chase_slot(chasers, active):
    """No target yet: pick the player with the smaller count (a SIGNED byte compare) when both are
    on the board, else the only one there — then claim a slot if speed_type3's low byte, an
    UNSIGNED cap, still has room."""
    p1 = _player(y=0x30) if active in ("p1", "both") else None
    p2 = _player(y=0x30) if active in ("p2", "both") else None
    _case([_obj(flags=TYPE2, y=0x50, target_y=0x40)],
          players=(p1, p2), chasers=chasers, speeds=(2, 3, 4),
          note=f"chasers={chasers} active={active}")


@pytest.mark.parametrize("target", [1, 2, 3, 0x7f])
@pytest.mark.parametrize("active", ["p1", "p2", "both"])
def test_type2_close_in_target_selection(target, active):
    """OBJ_CHASE_TARGET 1 means player 1 and EVERY other positive value player 2 (`cmpi.b #1` +
    `bne`). Losing that player hands the chase slot back and decrements its counter."""
    p1 = _player(y=0x30, x=0x40) if active in ("p1", "both") else None
    p2 = _player(y=0x30, x=0x40) if active in ("p2", "both") else None
    _case([_obj(flags=TYPE2, y=0x50, x=0x20, vy=4, flap_timer=6,
                chase_target=target, target_y=0x40)],
          players=(p1, p2), chasers=(5, 5), note=f"target={target} active={active}")


@pytest.mark.parametrize("player_y", [0x6d, 0x6e, 0x6f, 0x70, 0x80, 0x10])
def test_type2_close_in_reach_threshold(player_y):
    """`subi.w #$1e` on the player's y: still at or below the rider means keep climbing on the
    budget, above it means the attack starts."""
    _case([_obj(flags=TYPE2, y=0x50, x=0x20, vy=4, flap_timer=6, chase_target=1, target_y=0x40)],
          players=(_player(y=player_y, x=0x40), None), chasers=(5, 5),
          note=f"player_y={player_y:#x}")


@pytest.mark.parametrize("rider_x,player_x", [
    (0x20, 0), (0x20, 1), (0x20, 0x20), (0x20, 0xbf), (0x20, 0xc0), (0x20, 0xc1),
    (0x20, 0x13f), (0x20, 0x140), (0x20, 0xffff), (0x20, 0x8000),
    # Gaps that OVERFLOW the 16-bit subtraction, where `bge` reading N == V and the sign of the
    # truncated word disagree — and disagree across the half-playfield boundary, so the rider ends
    # up facing the other way.
    (0x7fff, 0x8000), (0x8000, 0x7fff), (0x8000, 0x8000), (0x7fff, 0x7fff),
    (0xc000, 0x4000), (0x4000, 0xc000),
])
def test_type2_turns_toward_the_player(rider_x, player_x):
    """The x gap is brought into 0..0x140 by a `bge` that reads N == V — so a subtraction which
    overflowed 16 bits keeps the sign the hardware saw — and a gap under half the playfield means
    the quarry is to the right."""
    _case([_obj(flags=TYPE2, y=0x50, x=rider_x, chase_target=1, target_y=0x40)],
          players=(_player(y=0x80, x=player_x), None), chasers=(5, 5),
          note=f"rider_x={rider_x:#x} player_x={player_x:#x}")


@pytest.mark.parametrize("target", [0xff, 0xfe, 0xfd, 0x80])
@pytest.mark.parametrize("active", ["p1", "p2", "both"])
def test_type2_attack_target_selection(target, active):
    """A negative OBJ_CHASE_TARGET is an attack in progress: -1 is player 1 and every OTHER
    negative value player 2 (`cmpi.b #$ff` + `bne`)."""
    p1 = _player(y=0x70, x=0x28) if active in ("p1", "both") else None
    p2 = _player(y=0x70, x=0x28) if active in ("p2", "both") else None
    _case([_obj(flags=TYPE2, y=0x50, x=0x20, vy=4, chase_target=target, target_y=0x40)],
          players=(p1, p2), chasers=(5, 5), note=f"target={target:#x} active={active}")


@pytest.mark.parametrize("player_y", [0x50, 0x53, 0x54, 0x55, 0x7b, 0x7c, 0x7d, 0x90,
                                      0x8000, 0x8003, 0x7fff])
def test_type2_attack_vertical_window(player_y):
    """`subq.w #4` then `sub.w` then `ble`: the subq's result is truncated to a word first, and it
    is the SECOND subtraction's overflow the branch reads. Above the rider the attack is dropped;
    more than 0x28 below it, broken off."""
    _case([_obj(flags=TYPE2, y=0x50, x=0x20, vy=4, chase_target=0xff, target_y=0x40)],
          players=(_player(y=player_y, x=0x28), None), chasers=(5, 5),
          note=f"player_y={player_y:#x}")


@pytest.mark.parametrize("player_x", [0x14, 0x20, 0x2b, 0x2c, 0x2d, 0x40, 0x13, 0x12,
                                      0x153, 0x154, 0x155, 0xfeec, 0xfeed, 0x8000])
@pytest.mark.parametrize("on_platform", [0, FLAG_ON_PLATFORM])
def test_type2_attack_horizontal_window(player_x, on_platform):
    """Within a dozen pixels either way — measured directly AND the long way round the 320-px
    playfield — the rider commits and pursues; anywhere else it breaks off."""
    _case([_obj(flags=TYPE2 | on_platform, y=0x50, x=0x20, vx=6, vy=4,
                chase_target=0xff, target_y=0x40)],
          players=(_player(y=0x60, x=player_x), None), chasers=(5, 5),
          note=f"player_x={player_x:#x} on_platform={on_platform:#x}")


@pytest.mark.parametrize("vx", [0, 1, -1, 0x7fff, 0x8000, 0x8001, 0xffff])
def test_type2_pursue_reverses_the_current_speed(vx):
    """The airborne pursue tail negates the rider's CURRENT speed and faces it to match. `neg.w`
    overflows on 0x8000 and `blt` reads N != V, so that one value ends up FACING RIGHT despite the
    negation leaving it negative."""
    _case([_obj(flags=TYPE2, y=0x50, x=0x20, vx=vx, vy=4, chase_target=0xff, target_y=0x40)],
          players=(_player(y=0x60, x=0x22), None), chasers=(5, 5), note=f"vx={vx:#x}")


# ------------------------------------------------------------------ rider type 3 @ 0x12368

@pytest.mark.parametrize("facing", [0, FLAG_FACING_RIGHT])
def test_type3_respawn_skips_every_flap_tail(facing):
    """The only handler that stores its flags word untouched by a tail: the flap bits it came in
    with survive the pass."""
    for flags in (0, FLAG_FLAP_REQUEST, FLAG_WINGS_UP, FLAG_FLAP_REQUEST | FLAG_WINGS_UP):
        _case([_obj(flags=TYPE3 | FLAG_RESPAWN | facing | flags, y=0x50,
                    flap_timer=9, turn_timer=9)],
              players=(_player(y=0x30), None), note=f"flags={flags:#x}")


@pytest.mark.parametrize("flap_timer", [0, 1, 2, 0xff])
@pytest.mark.parametrize("on_platform", [0, FLAG_ON_PLATFORM])
def test_type3_flap_burst_and_platform_reset(flap_timer, on_platform):
    """Standing on a platform zeroes the burst timer; a non-zero timer takes the glide tail and
    steps the timer down instead of choosing a dive."""
    _case([_obj(flags=TYPE3 | on_platform, y=0x50, flap_timer=flap_timer, target_y=0x40)],
          players=(_player(y=0x30), None),
          note=f"flap_timer={flap_timer} on_platform={on_platform:#x}")


TYPE3_DIVE_Y_BIAS = 0xa    # `addi.w #$a`
TYPE3_DIVE_Y_MAX = 0x32    # `cmpi.w #$32` + `bgt`


@pytest.mark.parametrize("reach", [-2, -1, 0, 1, TYPE3_DIVE_Y_MAX - 1, TYPE3_DIVE_Y_MAX,
                                   TYPE3_DIVE_Y_MAX + 1, 0x40])
@pytest.mark.parametrize("rider_y", [0x03, 0x04, 0x05, 0x50])
def test_type3_dive_window(reach, rider_y):
    """`addi.w #$a` then `blt` (N != V) picks the climb; then 0x32 below is out of reach, and a
    rider already at or above y == 4 climbs rather than giving up altitude.

    The player's y is DERIVED from the reach the case wants, because the three tests run in that
    order: with a fixed player-y axis every high rider answers "out of reach" and the ceiling
    compare — the third test — is never executed at all.
    """
    player_y = (reach - TYPE3_DIVE_Y_BIAS + rider_y) & 0xffff
    _case([_obj(flags=TYPE3, y=rider_y, vy=4, target_y=0x40)],
          players=(_player(y=player_y), None), note=f"reach={reach} rider_y={rider_y:#x}")


@pytest.mark.parametrize("p1_y,p2_y", [(0x90, 0x60), (0x90, 0x90), (0x60, 0x90), (0x60, 0x60),
                                       (0x10, 0x90), (0x90, 0x10)])
def test_type3_arms_are_not_symmetric(p1_y, p2_y):
    """Player 1 out of reach falls THROUGH to the player-2 test; player 2 out of reach ends the
    pass on the fall-speed tail instead."""
    _case([_obj(flags=TYPE3, y=0x50, vy=4, target_y=0x40)],
          players=(_player(y=p1_y), _player(y=p2_y)), note=f"p1_y={p1_y:#x} p2_y={p2_y:#x}")


@pytest.mark.parametrize("p1_y", [None, 0x90, 0x20])
def test_type3_dives_at_player_two(p1_y):
    """The player-2 dive arm has its own copy of the commit, and only a rider high enough (y < 4)
    with player 1 absent or out of reach ever gets there."""
    p1 = None if p1_y is None else _player(y=p1_y)
    _case([_obj(flags=TYPE3, y=3, vy=4, target_y=0x40)],
          players=(p1, _player(y=0x20)), note=f"p1_y={p1_y}")


@pytest.mark.parametrize("rider_y", [0, 0x03, 0x50])
def test_type3_dive_overflow_reach(rider_y):
    """The dive reach is computed at FULL precision: a player y that wraps the 16-bit subtraction
    still takes the branch the 68000's V flag chose.

    The `blt` edge sits where `player_y - rider_y + 0xa` crosses 0, so it is derived per rider
    rather than fixed; 0x8000 / 0x7fff are the extremes that make the subtraction itself wrap.
    """
    edge = (-TYPE3_DIVE_Y_BIAS + rider_y) & 0xffff
    for player_y in (0x8000, 0x8005, 0x7fff, (edge - 1) & 0xffff, edge, (edge + 1) & 0xffff):
        _case([_obj(flags=TYPE3, y=rider_y, vy=4, target_y=0x40)],
              players=(_player(y=player_y), None), note=f"player_y={player_y:#x}")


# ------------------------------------------------------------------ the dead slot @ 0x12438
#
# BIT 12 (OBJ_FLAG_REMOVED) LIVES HERE, and these are the cases that reach each of its branches.

@pytest.mark.parametrize("egg_state", [0, 1, 0x24, 0xff])
def test_dead_without_an_egg_latches_removed(egg_state):
    """`btst #12` clear -> 0x124a6. With OBJ_EGG_STATE zero there is nothing to come back for, so
    `bset #12,d0` latches OBJ_FLAG_REMOVED and the SAME test is re-run — which now falls into the
    removal tail. With an egg the recovery walk runs instead and bit 12 is never set."""
    _case([_obj(flags=TYPE1 | FLAG_DEAD, y=0x50, x=0x40, egg_state=egg_state,
                egg_x=0x40, egg_y=0x60, target_y=0x40)],
          note=f"egg_state={egg_state:#x}")


@pytest.mark.parametrize("egg_state", [0, 1, 0x24, 0xff])
@pytest.mark.parametrize("x", [0x40, 0x13c])
def test_removed_beats_a_surviving_egg(x, egg_state):
    """`btst #12` is tested BEFORE OBJ_EGG_STATE, so a slot already marked for removal takes the
    removal tail even while it still has an egg that would otherwise send it walking back.

    Without this pair the bit-12 test is invisible: every other removal case here has no egg, and
    dropping the test entirely would just latch the bit at 0x124ac and arrive at the same tail.
    """
    _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_REMOVED | FLAG_FACING_RIGHT, y=0x50, x=x, prev_x=x,
                vx=3, vy=1, egg_state=egg_state, egg_x=0x40, egg_y=0x60, target_y=0x40)],
          note=f"x={x:#x} egg_state={egg_state:#x}")


@pytest.mark.parametrize("x", [0, 2, 0x12b,
                               DEAD_EXIT_LEFT_LO - 1, DEAD_EXIT_LEFT_LO, DEAD_EXIT_LEFT_LO + 1,
                               DEAD_EXIT_LEFT_HI, DEAD_EXIT_LEFT_HI + 1,
                               DEAD_EXIT_RIGHT_X - 1, DEAD_EXIT_RIGHT_X, DEAD_EXIT_RIGHT_X + 1,
                               0x140, 0xffff, 0x8000, 0x7fff])
@pytest.mark.parametrize("facing", [0, FLAG_FACING_RIGHT])
def test_removal_exit_strip(x, facing):
    """`btst #12` SET -> the removal tail. Facing right, x at or past 0x13c means gone; facing left
    only the 0x130..0x133 band does. Reaching it masks the sprite off the screen (draw_object_mask)
    and ZEROES the flags word, freeing the slot."""
    _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_REMOVED | FLAG_CORPSE_INSIDE | facing,
                y=0x50, x=x, prev_x=x, vx=3, target_y=0x40)],
          note=f"x={x:#x} facing={facing:#x}")


@pytest.mark.parametrize("y", [0,
                               HOVER_BAND_HIGH_Y - 1, HOVER_BAND_HIGH_Y, HOVER_BAND_HIGH_Y + 1,
                               HOVER_BAND_MID_Y - 1, HOVER_BAND_MID_Y, HOVER_BAND_MID_Y + 1,
                               0x90, 0x8000, 0xffff])
@pytest.mark.parametrize("vx", [PLAYER_STEER_VX, -PLAYER_STEER_VX, 0, 0x8000])
def test_removal_exit_altitude(y, vx):
    """Short of the exit strip the slot drifts on: the target speed keeps its sign and the target
    altitude is the first of 0x8c / 0x42 / 0xa the rider has not already passed."""
    _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_REMOVED, y=y, x=0x40, vx=vx, vy=1,
                target_y=0x40)],
          note=f"y={y:#x} vx={vx:#x}")


def test_removal_clears_the_egg_recovery_bit():
    """`bclr #5,d0` is the tail's first instruction, so bit 5 never survives into a removed slot —
    including on the path that then frees the slot outright."""
    for x in (0x40, 0x13c):
        for flags in (0, FLAG_CORPSE_INSIDE):
            _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_REMOVED | FLAG_FACING_RIGHT | flags,
                        y=0x50, x=x, prev_x=x, vx=3, target_y=0x40)],
                  note=f"x={x:#x} flags={flags:#x}")


@pytest.mark.parametrize("x", [0, 1, 2, 3, 0x12b, 0x12c, 0x12d, 0x13f, 0xffff, 0x8000])
def test_dead_egg_recovery_window(x):
    """Bit 5 is armed only while the dead rider is on-screen, by UNSIGNED compares — so a negative
    x is outside the window, not to the left of it. Off-window the pass ends immediately."""
    _case([_obj(flags=TYPE1 | FLAG_DEAD, y=0x50, x=x, vy=1, egg_state=4, egg_x=0x900,
                egg_y=0x60, target_y=0x40, flap_timer=7, turn_timer=7, chase_target=7)],
          note=f"x={x:#x}")


# The rider stands at x = 0x40 and its grab point is two pixels right of that, so the gap the reach
# test sees is 0x42 - egg_x. Each egg_x below is chosen for the gap it produces, and the four
# window edges are straddled from BOTH sides — widening one by a pixel has to fail, not just
# narrowing it.
DEAD_RIDER_X = 0x40
DEAD_RIDER_GRAB_X = DEAD_RIDER_X + 2


def _egg_x_for_gap(gap):
    return (DEAD_RIDER_GRAB_X - gap) & 0xffff


@pytest.mark.parametrize("gap", [0, 1, 2, 3, 4,                       # the `#$2` + `bls` edge
                                 0xffff, 0xfffe, 0xfffd, 0xfffc,      # the `#$fffe` + `bcc` edge
                                 0x13d, 0x13e, 0x13f,                 # the `#$13e` + `bge` edge
                                 0xfec1, 0xfec2, 0xfec3,              # the `#$fec2` + `ble` edge
                                 0x40, 0x8000])
@pytest.mark.parametrize("hatch_mount", [0, 1, 2, 0xff])
def test_dead_egg_reach_and_mount(gap, hatch_mount):
    """Over the egg (within two pixels either way, directly or the long way round the playfield)
    the rider either turns back or, having already turned, REMOUNTS: bit 13 clears, the egg sprite
    is erased and OBJ_EGG_STATE is freed. Short of it, the target speed is reversed exactly once."""
    _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_CORPSE_INSIDE, y=0x50, x=DEAD_RIDER_X, vy=1,
                egg_state=4, egg_x=_egg_x_for_gap(gap), egg_y=0x60, hatch_mount=hatch_mount,
                target_vx=5, target_y=0x40)],
          note=f"gap={gap:#x} hatch_mount={hatch_mount}")


def test_dead_recovery_clears_the_ai_bytes():
    """The three `clr.b` at 0x124ce..0x124d6 and the `clr.b 74(a0)` at 0x1251a.

    Every other dead-slot case leaves those four bytes at 0, which is also what the clears write —
    so the writes are invisible there and a candidate that dropped all four stays green. Here each
    byte is staged to a sentinel instead, on both the "walks on" and the "over the egg" branches.
    """
    for gap, hatch_mount in ((0x40, 0), (0, 0), (0, 2)):
        _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_CORPSE_INSIDE, y=0x50, x=DEAD_RIDER_X, vy=1,
                    egg_state=4, egg_x=_egg_x_for_gap(gap), egg_y=0x60,
                    chase_target=UNWRITTEN_B, flap_timer=UNWRITTEN_B, turn_timer=UNWRITTEN_B,
                    hatch_mount=hatch_mount, target_vx=5, target_y=0x40)],
              note=f"gap={gap:#x} hatch_mount={hatch_mount}")


def test_dead_egg_mount_reverses_the_most_negative_speed():
    """The turn-back is a `neg.w` on OBJ_TARGET_VX with no branch on it, so 0x8000 negates to
    itself and the rider keeps going the same way — reproduced, not repaired."""
    for target_vx in (0, 1, 0x7fff, 0x8000, 0xffff):
        _case([_obj(flags=TYPE1 | FLAG_DEAD | FLAG_CORPSE_INSIDE, y=0x50, x=0x40, vy=1,
                    egg_state=4, egg_x=0x100, egg_y=0x60, target_vx=target_vx, target_y=0x40)],
              note=f"target_vx={target_vx:#x}")


# ------------------------------------------------------------------ the shared flap tails
#
# Every handler ends in one of these, and each moves a DIFFERENT subset of bits 6 / 10 / 11 — the
# reason the three cannot be one "flapping" constant the way player.h's joystick reader has them.

_TAIL_CASES = {
    # name -> (the object's own fields, the player slots) reaching exactly that tail
    # player 1 out of reach, player 2 absent — so the `btst #1` at 0x12400 is what routes here
    "fall_speed_0x1253c": ({"flags": TYPE3, "y": 0x50, "vy": 5, "target_y": 0x40},
                           (_player(y=0x90), None)),
    "flap_budget_0x12550": ({"flags": TYPE1, "y": 0x50, "vy": 4, "flap_timer": 0x40,
                             "target_y": 0x40}, (_player(y=0x30), None)),
    "flap_toggle_0x12598": ({"flags": TYPE1 | FLAG_RESPAWN, "y": 0x50}, (None, None)),
    "flap_stop_0x125a4": ({"flags": TYPE1, "y": 0x10, "target_y": 0x40}, (None, None)),
    "flap_start_0x125b0": ({"flags": TYPE3, "y": 0x50, "vy": 4, "target_y": 0x40},
                           (_player(y=0x10), None)),          # the player is above: climb
    "flap_burst_0x125c0": ({"flags": TYPE3, "y": 0x50, "flap_timer": 2, "target_y": 0x40},
                           (_player(y=0x30), None)),
}

_FLAP_BITS = [0, FLAG_WINGS_UP, FLAG_FLAP_TAKEN, FLAG_FLAP_REQUEST,
              FLAG_WINGS_UP | FLAG_FLAP_TAKEN, FLAG_WINGS_UP | FLAG_FLAP_REQUEST,
              FLAG_FLAP_TAKEN | FLAG_FLAP_REQUEST,
              FLAG_WINGS_UP | FLAG_FLAP_TAKEN | FLAG_FLAP_REQUEST]


@pytest.mark.parametrize("vy", [0, 1, 2, 3, 0xffff, 0x8000, 0x7fff])
def test_fall_speed_tail_boundary(vy):
    """0x1253c keeps the wings going only while the rider is already falling FASTER than 1 — a
    signed `bgt`, so the most negative speed counts as rising, not as the fastest fall."""
    _case([_obj(flags=TYPE3, y=0x50, vy=vy, target_y=0x40)],
          players=(_player(y=0x90), None), note=f"vy={vy:#x}")


@pytest.mark.parametrize("preset", _FLAP_BITS)
@pytest.mark.parametrize("tail", sorted(_TAIL_CASES))
def test_each_flap_tail_moves_only_its_own_bits(tail, preset):
    """Enter every tail with all eight combinations of bits 6/10/11 already set.

    None of the three steers any handler, so the tail reached is the same in all eight — which
    makes the stored flags word a direct readout of what that tail does to them. This is what
    catches, for instance, 0x125b0 forgetting its `bclr #10`.
    """
    fields, players = _TAIL_CASES[tail]
    fields = {**fields, "flags": fields["flags"] | preset}
    _case([_obj(**fields)], players=players, note=f"{tail} preset={preset:#x}")


@pytest.mark.parametrize("preset", _FLAP_BITS)
def test_flap_budget_also_clears_the_platform_bit(preset):
    """0x12550 is the one tail that touches a FIFTH bit: `bclr #9` drops the rider off its platform
    as the climb starts. Bit 9 steers the type-3 and pursue paths, so it cannot go in _FLAP_BITS —
    but it steers nothing on the type-1 chase path this case takes, which is why it can be preset
    here. Without this, dropping the `bclr #9` is caught only by the fuzz."""
    _case([_obj(flags=TYPE1 | FLAG_ON_PLATFORM | preset, y=TYPE1_RIDER_Y, vy=4, flap_timer=0x40,
                target_y=0x40)],
          players=(_player(y=TYPE1_RIDER_Y), None), speeds=(2, 3, 4),
          note=f"preset={preset:#x}")


# ------------------------------------------------------------------ the D0 carry into rng_advance

@pytest.mark.parametrize("wrap_slot", [0, 1, 5, 11])
def test_rng_wrap_offset_comes_from_the_previous_slots_flags(wrap_slot):
    """rng_advance restarts the cursor at 0x10000 + (D0 & 0xfe), and D0 at the call is the flags
    word the PREVIOUS slot stored — the caller's D0 only for the first slot.

    The cursor is staged so the wrap lands on `wrap_slot`, and every slot before it stores a
    different flags word, so a candidate that fed rng_advance a zero (or the CURRENT slot's flags)
    restarts the cursor somewhere else and the whole rest of the walk diverges.
    """
    riders = [_obj(flags=TYPE1 | FLAG_FACING_RIGHT | (slot << 4), y=0x50 + slot, vy=2,
                   flap_timer=slot, target_y=0x40)
              for slot in range(N_ENEMIES)]
    _case(riders, rng_ptr=RNG_PTR_LIMIT - RNG_PTR_STEP * (wrap_slot + 1),
          players=(_player(y=0x30), None), d0=0xbeef, note=f"wrap_slot={wrap_slot}")


@pytest.mark.parametrize("d0", [0, 1, 0xfe, 0xff, 0x100, 0x5a5a, 0xffff])
def test_first_slot_takes_the_callers_d0(d0):
    """Only the first slot's rng_advance sees the caller's D0, and only its low byte survives the
    `andi.l #$fe`."""
    _case([_obj(flags=TYPE2 | FLAG_RESPAWN, y=0x50)],
          rng_ptr=RNG_PTR_LIMIT - RNG_PTR_STEP, players=(_player(y=0x30), None),
          d0=d0, note=f"d0={d0:#x}")


# ------------------------------------------------------------------ why no case is poisoned

UPDATE_OBJECTS_END = 0x12606   # update_eggs, the next function (../../names.txt)


def _oracle_run_recording_pcs(image, regs):
    """One oracle run, returning (executed update_objects PCs, final image, write set).

    Executed-PC coverage is a process-global bitset in the oracle and is off during a normal run,
    so it is switched on and cleared around this call and switched back off afterwards.
    """
    harness.emu.cov_enable(True)
    try:
        harness.emu.cov_reset()
        final, writes, _ = harness.emu.run(bytearray(image), ENTRY_UPDATE_OBJECTS, dict(regs))
    finally:
        harness.emu.cov_enable(False)
    executed = {pc for pc in range(ENTRY_UPDATE_OBJECTS, UPDATE_OBJECTS_END, 2)
                if harness.emu.cov_visited(pc)}
    return executed, final, writes


def test_poison_would_test_a_different_function():
    """The measurement behind "no poison here", kept executable so it cannot go stale.

    poison=True re-runs both cores on an image whose oracle-written bytes are INVERTED. Almost
    every byte this routine writes is one it also reads: the flags word it dispatches on, the two
    chase counters it compares before bumping, the flap timers it decrements — and rng_ptr, which
    every slot's rng_advance steps and the very next instruction reads back.

    So the poisoned pass does not re-test this case harder; it silently tests a DIFFERENT one. It
    also passes, which is the trap: a green there would read as attribution while proving nothing.

    The evidence has to be about the CODE the re-run takes, not about any byte it stores: poison
    inverts the stored bytes itself, so comparing one is satisfied by construction whatever the
    poisoned run does. What is asserted instead is the oracle's executed-PC set across the whole
    routine, which poison does not touch. Measured on this case: the clean run executes 50 PCs, the
    poisoned run 53, and only 27 are common — 49 of the 76 addresses either run reaches are reached
    by just one of them. (That the cursor also lands ~15 MB outside the image is a consequence of
    the scheme, not a fact about this routine, so it is stated here rather than asserted.)

    Attribution is bought with UNWRITTEN sentinels in the staged records instead.
    """
    pokes = _pokes([_obj(flags=TYPE2 | FLAG_RESPAWN, y=0x50)], players=(_player(y=0x30), None))
    image = harness.make_image(pokes)
    regs = {"d0": 0, "d2": 0}

    clean_pcs, clean, writes = _oracle_run_recording_pcs(image, regs)
    poisoned = bytearray(image)
    for addr in writes:
        poisoned[addr] = clean[addr] ^ 0xff
    poisoned_pcs, _, _ = _oracle_run_recording_pcs(poisoned, regs)

    assert clean_pcs, ("the oracle recorded no executed PC inside update_objects, so the comparison "
                       "below would pass on two empty sets — coverage is not being recorded")
    assert clean_pcs != poisoned_pcs, (
        f"the poisoned run executed exactly the same {len(clean_pcs)} instructions of "
        "update_objects, so poison here would re-test this case rather than a different one — "
        "re-measure before enabling poison")


# ------------------------------------------------------------------ fuzz

def _fuzz_cases():
    rng = random.Random(0x12014)                 # seeded ONCE — every chunk replays this stream

    def word(interesting):
        return rng.choice(interesting) if rng.random() < 0.6 else rng.randrange(0x10000)

    def rider():
        return _obj(flags=rng.randrange(0x10000),
                    x=word((0, 2, 3, 0x40, 0x12b, 0x12c, 0x130, 0x133, 0x13c, 0x8000)),
                    y=word((0, 4, 0x28, 0x50, 0x64, 0x8c, 0x8000, 0x7fff)),
                    vx=word((0, 1, 0xffff, 0x8000)), vy=word((0, 1, 2, 0xffff, 0x8000)),
                    target_vx=word((0, 4, 0x8000)), target_y=word((0x40, 0x8c, 0x8000)),
                    egg_state=rng.choice((0, 0, 1, 4, 0x24, 0xff)),
                    egg_x=word((0, 0x3e, 0x40, 0x42, 0x180)), egg_y=word((0x60, 0, 0x8000)),
                    chase_target=rng.choice((0, 0, 1, 2, 3, 0xff, 0xfe, 0x7f, 0x80)),
                    flap_timer=rng.choice((0, 1, 2, 7, 0xff)),
                    hatch_mount=rng.choice((0, 0, 1, 2)),
                    turn_timer=rng.choice((0, 1, 3, 0x80, 0xff)),
                    prev_x=word((0, 0x130, 0x13c)))

    def player():
        return rng.choice((None, None,
                           _player(x=word((0, 0x40, 0x13f, 0x8000)),
                                   y=word((0, 0x30, 0x50, 0x70, 0x8000))),
                           _obj(flags=rng.choice((0, FLAG_PLAYER | FLAG_DEAD,
                                                  FLAG_PLAYER | FLAG_RESPAWN)))))

    for i in range(240):
        yield (i,
               [rider() for _ in range(N_ENEMIES)],
               {"players": (player(), player()),
                "speeds": tuple(rng.choice((0, 1, 2, 3, 7, 0x10, 0xffff)) for _ in range(3)),
                "chasers": (rng.randrange(0x100), rng.randrange(0x100)),
                "rng_ptr": rng.choice((0x11000, 0x17000,
                                       RNG_PTR_LIMIT - RNG_PTR_STEP * rng.randrange(1, 13)))},
               rng.randrange(0x10000), rng.randrange(0x10000))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_update_objects_fuzz(chunk):
    ran = 0
    for i, riders, staging, d0, d2 in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        ran += 1
        _case(riders, d0=d0, d2=d2, note=f"fuzz case {i}", **staging)
    assert ran, "the chunk filter rejected every case"


# ------------------------------------------------------------------ the mirrored constants
#
# Everything above restates addresses and record offsets that really live in ../../names.txt and
# include/. Nothing makes a drifted mirror FAIL on its own: both cores would run against the real
# address, agree byte-for-byte on the game's own static data, and go green while the staged inputs
# landed in dead memory. These pin the mirrors, the way test_constants.py pins the other batteries'.

def test_entry_address_matches_names_txt():
    assert harness.NAME_MAP.get(ENTRY_UPDATE_OBJECTS) == "update_objects"


def test_mirrored_constants_match_the_headers():
    """Every constant this file restates equals the one src/objects.c compiles against.

    Eight headers plus src/rng.c, because update_objects reads globals, record fields and whole
    constant groups that other layers already owned: egg.h has the egg's own y/mount bytes,
    world.h OBJ_FLAG_REMOVED, draw.h player 2's slot, object.h the table bound, player.h the
    dead-rider exit strip and hover ladder, addrs.h the table base, rng_ptr, the three rider speeds,
    the two chase counts and the enemy-slot bound, joust.h the record itself with its flag bits and rider types, rng.c
    the cursor limit. Each is scraped by name rather than as one merged namespace, so a constant
    that drifts into the wrong header fails here instead of being found in whichever copy still
    holds the old value.
    """
    objects_h = _defines("include/objects.h")
    addrs_h = _defines("include/addrs.h")
    joust_h = _defines("include/joust.h")
    draw_h = _defines("include/draw.h")
    egg_h = _defines("include/egg.h")
    world_h = _defines("include/world.h")
    object_h = _defines("include/object.h")
    player_h = _defines("include/player.h")
    rng_c = _defines("src/rng.c")

    for defines, origin, mirrored in (
            (objects_h, "objects.h", {"A_active_players": A_ACTIVE_PLAYERS}),
            (addrs_h, "addrs.h", {"A_object_table": A_OBJECT_TABLE, "A_rng_ptr": A_RNG_PTR,
                                  "A_speed_type1": A_SPEED_TYPE1, "A_speed_type2": A_SPEED_TYPE2,
                                  "A_speed_type3": A_SPEED_TYPE3,
                                  "A_enemy_objects": A_ENEMY_OBJECTS,
                                  "A_chasers_p1": A_CHASERS_P1, "A_chasers_p2": A_CHASERS_P2}),
            (joust_h, "joust.h", {"OBJ_SIZE": OBJ_SIZE, "OBJ_FLAG_RESPAWN": FLAG_RESPAWN,
                                  "OBJ_FLAG_ON_PLATFORM": FLAG_ON_PLATFORM,
                                  "OBJ_FLAG_DEAD": FLAG_DEAD,
                                  "OBJ_FLAG_FACING_RIGHT": FLAG_FACING_RIGHT,
                                  "OBJ_FLAG_CORPSE_INSIDE": FLAG_CORPSE_INSIDE,
                                  "OBJ_FLAG_WINGS_UP": FLAG_WINGS_UP,
                                  "OBJ_FLAG_FLAP_TAKEN": FLAG_FLAP_TAKEN,
                                  "OBJ_FLAG_FLAP_REQUEST": FLAG_FLAP_REQUEST,
                                  "ENEMY_TYPE_1": TYPE1, "ENEMY_TYPE_2": TYPE2,
                                  "ENEMY_TYPE_3": TYPE3}),
            (draw_h, "draw.h", {"A_player2": A_PLAYER2}),
            (world_h, "world.h", {"OBJ_FLAG_REMOVED": FLAG_REMOVED,
                                  "OBJ_FLAG_PLAYER": FLAG_PLAYER}),
            (object_h, "object.h", {"A_object_table_END": A_OBJECT_TABLE_END}),
            (player_h, "player.h", {"DEAD_EXIT_RIGHT_X": DEAD_EXIT_RIGHT_X,
                                    "DEAD_EXIT_LEFT_LO": DEAD_EXIT_LEFT_LO,
                                    "DEAD_EXIT_LEFT_HI": DEAD_EXIT_LEFT_HI,
                                    "PLAYER_STEER_VX": PLAYER_STEER_VX,
                                    "HOVER_BAND_HIGH_Y": HOVER_BAND_HIGH_Y,
                                    "HOVER_BAND_MID_Y": HOVER_BAND_MID_Y,
                                    "HOVER_TARGET_HIGH": HOVER_TARGET_HIGH,
                                    "HOVER_TARGET_MID": HOVER_TARGET_MID,
                                    "HOVER_TARGET_LOW": HOVER_TARGET_LOW}),
            (rng_c, "rng.c", {"RNG_PTR_LIMIT": RNG_PTR_LIMIT, "RNG_PTR_STEP": RNG_PTR_STEP})):
        for name, value in mirrored.items():
            assert defines[name] == value, (f"{name}: {origin} has {defines[name]:#x}, "
                                            f"test has {value:#x}")

    # The record layout _obj encodes positionally, which no other assertion can catch drifting.
    for name, off in (("OBJ_FLAGS", 0x00), ("OBJ_X", 0x02), ("OBJ_Y", 0x04), ("OBJ_VX", 0x06),
                      ("OBJ_VY", 0x08), ("OBJ_TARGET_VX", 0x0c), ("OBJ_PREV_X", 0x10),
                      ("OBJ_PREV_DST", 0x14), ("OBJ_PREV_SRC", 0x18), ("OBJ_PREV_ROWS", 0x1c),
                      ("OBJ_PREV_SHIFT", 0x1d), ("OBJ_EGG_STATE", 0x1e), ("OBJ_EGG_X", 0x20),
                      ("OBJ_EGG_DST", 0x2a), ("OBJ_EGG_SRC", 0x2e), ("OBJ_EGG_ROWS", 0x32),
                      ("OBJ_EGG_SHIFT", 0x33), ("OBJ_TARGET_Y", 0x46)):
        assert joust_h[name] == off, f"{name}: joust.h has {joust_h[name]:#x}, _obj uses {off:#x}"
    for name, off in (("OBJ_FLAP_TIMER", 0x49), ("OBJ_TURN_TIMER", 0x4b)):
        assert joust_h[name] == off, f"{name}: joust.h has {joust_h[name]:#x}, _obj uses {off:#x}"
    for name, off in (("OBJ_EGG_Y", 0x22), ("OBJ_HATCH_MOUNT", 0x4a)):
        assert egg_h[name] == off, f"{name}: egg.h has {egg_h[name]:#x}, _obj uses {off:#x}"
    assert objects_h["OBJ_CHASE_TARGET"] == 0x48, \
        f"OBJ_CHASE_TARGET: objects.h has {objects_h['OBJ_CHASE_TARGET']:#x}, _obj uses 0x48"

    assert N_ENEMIES == (A_OBJECT_TABLE_END - A_ENEMY_OBJECTS) // OBJ_SIZE
    assert N_OBJECTS == (A_OBJECT_TABLE_END - A_OBJECT_TABLE) // OBJ_SIZE
    assert A_PLAYER2 == A_OBJECT_TABLE + OBJ_SIZE
    assert A_ENEMY_OBJECTS == A_OBJECT_TABLE + 2 * OBJ_SIZE
