"""Differential tests for collision_check @ 0x13842 (src/collide.c).

One routine, four sweeps, and the batteries below follow them in order: the platforms, the joust
between riders, the eggs a player can collect, and the pterodactyls.

NO CHECKPOINT RUN IS NEEDED ANYWHERE IN THIS FILE. collision_check has exactly one `rts` (0x13858,
the object loop running out of slots) and everything it calls — test_overlap, joust_bounce,
start_death_anim, play_sound, the score_update family, find_free_message, erase_egg_sprite — returns
normally, so every case below is diffed at the real return. `differential()` raises rather than
comparing anything if that `rts` is not reached, so "it returned" is proved by every green case.

STAGING CONVENTION. test_overlap measures a box's screen address and its y INDEPENDENTLY, so a case
whose two boxes disagree about which of them is higher up the screen exercises its degenerate arm
instead of a collision. Every rider, egg, platform and bird staged here therefore sits at
`SCREEN + y * SCREEN_ROW_BYTES`, which is what the game itself produces, and the sprites are solid
so the narrow phase hits on the first shared column. `_miss_*` helpers break exactly one of those
agreements at a time.

POISON. Measured, not assumed — see the note above `_case`. The short version is that
collision_check writes the very flags word it branches on, so an inverted image sends almost every
case down a different path (usually one that writes nothing at all). The attribution pass is
therefore kept on exactly one case, the one whose whole write set is scratch the routine rewrites
before reading it: test_no_hit_writes_only_scratch.
"""
import ctypes
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin tests at the end

# ---- entry point (Ghidra address; ../../names.txt) ----
ENTRY_COLLISION_CHECK = 0x13842

# ---- globals (mirrors of include/collide.h, object.h, world.h, score.h, addrs.h) ----
A_PLAYERS_ALIVE = 0x10cf2
A_WAVE_NUM = 0x10cf3
A_PLATFORM_PRESENT = 0x10cfa
A_GLADIATOR_WAVE_COUNTDOWN = 0x10d05
A_PLAYER_CONFLICT_FLAG = 0x10d06
A_FIRST_DISMOUNT_OWNER = 0x10d07
A_SND_PRIORITY = 0x10d4c
A_HIT_BOX_A = 0x10da0
A_HIT_BOX_B = 0x10db0
A_HIT_ROWS = 0x10dc0
A_COLLISION_HIT = 0x10dc1
A_SCREEN_BASE = 0x10dde
A_TEXT_PTR = 0x10e0a
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36
A_PLAYER2 = 0x10f84
A_OBJECT_TABLE_END = 0x1137a
A_PTERODACTYL_TABLE = 0x113ba
A_PTERODACTYL_TABLE_END = 0x1143a
A_EGG_BONUS_TABLE = 0x119b4
A_PLATFORM_SPRITES = 0x119d4
A_EGG_SPRITE_STILL = 0x1899a
A_DEATH_SPRITE_P1 = 0x1922a
A_DEATH_SPRITE_OTHER = 0x193da
STR_BONUS_500 = 0x18608

# ---- record geometry ----
OBJ_SIZE, N_OBJECTS = 0x4e, 14
PT_RECORD, N_PTEROS = 0x20, 4
PSPR_RECORD, N_PLATFORMS = 0x10, 8
MSG_RECORD, N_MESSAGES = 0xc, 24
BONUS_RECORD, N_BONUS = 8, 4
SCREEN_ROW_BYTES = 0xa0
CELL_BYTES = 8
CELL_PLANE_WORDS = 4

# ---- object-record fields, by name ----
OBJ_FLAGS, OBJ_X, OBJ_Y, OBJ_VX, OBJ_VY = 0x00, 0x02, 0x04, 0x06, 0x08
OBJ_TARGET_VX = 0x0c
OBJ_PREV_DST, OBJ_PREV_SRC, OBJ_PREV_ROWS, OBJ_PREV_SHIFT = 0x14, 0x18, 0x1c, 0x1d
OBJ_EGG_STATE, OBJ_EGG_HATCH_TIMER = 0x1e, 0x1f
OBJ_EGG_X, OBJ_EGG_Y, OBJ_EGG_DX, OBJ_EGG_DY = 0x20, 0x22, 0x24, 0x26
OBJ_EGG_ROLL_TIMER, OBJ_EGG_FALL_TIMER = 0x28, 0x29
OBJ_EGG_DST, OBJ_EGG_SRC, OBJ_EGG_ROWS, OBJ_EGG_SHIFT = 0x2a, 0x2e, 0x32, 0x33
OBJ_EGG_SPAWN_FLAGS, OBJ_EGG_CHAIN = 0x34, 0x35
OBJ_SCORE_COLOR = 0x3d
OBJ_SCORE_LIFE_DIGIT, OBJ_SCORE_HUNDREDS, OBJ_SCORE_PENDING = 0x41, 0x42, 0x43

# ---- flag bits ----
OBJ_FLAG_TYPE_LO = 1 << 0
OBJ_FLAG_TYPE_HI = 1 << 1
OBJ_FLAG_PLAYER = 1 << 2
OBJ_FLAG_RESPAWN = 1 << 7
OBJ_FLAG_DEAD = 1 << 13
OBJ_FLAG_REMOVED = 1 << 12
OBJ_FLAG_PLATFORM_BUMP = 1 << 14
OBJ_FLAG_FACING_RIGHT = 1 << 15
LIVE = 1 << 3          # a bit nothing in this routine reads, so a slot can be non-zero and inert

PT_FLAG_JUST_SPAWNED = 1 << 0
PT_FLAG_MOVING_RIGHT = 1 << 2
PT_FLAG_DYING = 1 << 5
PT_LIVE = 1 << 3       # as LIVE above: a bit this routine never reads, so a bird can be non-zero
                       # without also being "moving right" — flags of 0 means an EMPTY slot

# ---- message record ----
MSG_KIND, MSG_TIMER, MSG_COLOR, MSG_SHIFT, MSG_SCREEN_PTR, MSG_STRING = 0, 1, 2, 3, 4, 8
MSG_KIND_PERSISTENT = 3
MSG_BONUS_FRAMES = 0x32
MSG_BONUS_COLOR = 6

# ---- egg / sound / scoring constants the cases assert on ----
EGG_STATE_THROWN = 0x23
EGG_SPAWN_UNDRAWN = 1 << 7
EGG_HATCH_FRAMES = 0x88
SND_PLATFORM_BUMP, SND_RIDER_UNSEATED, SND_PTERO_LANCED = 7, 5, 2
SND_EGG_COLLECTED, SND_JOUST_TIE = 8, 0xb
A_SOUND_TABLE = 0x11774
N_SOUNDS = 16
SND_PRIORITY_IDLE = 0x7fff        # admits every request play_sound's SIGNED gate is handed

# ---- scratch, clear of the program (ends 0x2b7ae), abi.STUB (0x40000), the staged-file table
# (0xbf000) and the stack guard. ----
SCREEN = 0x60000
HUD = 0x68000                     # where each slot's score row is painted, one row per slot
SPRITE_SOLID = 0x50000            # every plane word set: the narrow phase hits on the first column
SPRITE_BLANK = 0x51000            # ...and this one never hits
SPRITE_ROWS, SPRITE_COLS = 24, 3  # big enough for the widest box any case stages

_U8P = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_collision_check.argtypes = [_U8P]
harness._lib.g_collision_check.restype = None


# ================================================================== staging

def _sprite(word):
    return struct.pack(">4H", *([word] * CELL_PLANE_WORDS)) * (SPRITE_ROWS * SPRITE_COLS)


_OBJ_FIELDS = {
    "flags": (OBJ_FLAGS, "H"), "x": (OBJ_X, "H"), "y": (OBJ_Y, "H"), "vx": (OBJ_VX, "H"),
    "vy": (OBJ_VY, "H"), "target_vx": (OBJ_TARGET_VX, "H"),
    "prev_dst": (OBJ_PREV_DST, "I"), "prev_src": (OBJ_PREV_SRC, "I"),
    "prev_rows": (OBJ_PREV_ROWS, "B"), "prev_shift": (OBJ_PREV_SHIFT, "B"),
    "egg_state": (OBJ_EGG_STATE, "B"), "hatch_timer": (OBJ_EGG_HATCH_TIMER, "B"),
    "egg_x": (OBJ_EGG_X, "H"), "egg_y": (OBJ_EGG_Y, "H"),
    "egg_dx": (OBJ_EGG_DX, "H"), "egg_dy": (OBJ_EGG_DY, "H"),
    "roll_timer": (OBJ_EGG_ROLL_TIMER, "B"), "fall_timer": (OBJ_EGG_FALL_TIMER, "B"),
    "egg_dst": (OBJ_EGG_DST, "I"), "egg_src": (OBJ_EGG_SRC, "I"),
    "egg_rows": (OBJ_EGG_ROWS, "B"), "egg_shift": (OBJ_EGG_SHIFT, "B"),
    "spawn_flags": (OBJ_EGG_SPAWN_FLAGS, "B"), "egg_chain": (OBJ_EGG_CHAIN, "B"),
    "lives": (0x4c, "B"),
}

SCORE_TEXT = 0x3c                 # `02 <colour>` then seven ASCII digits then the NUL at 0x45
SCORE_COLOR = 3
DEFAULT_DIGITS = b"0000000"       # settled: neither score_update sweep has anything to do
BOX_ROWS = 8                      # every rider/egg/bird box in this file is this tall...
BOX_SHIFT = 0                     # ...at no pixel shift, so a hit needs no spill handling


def _obj(index, digits=DEFAULT_DIGITS, **fields):
    """A 0x4e-byte object record. Slot `index` fixes its own HUD row, so score_update — which the
    joust and egg paths call on player 1, player 2 AND the object itself — always has somewhere
    real to paint. Every field not named is zero."""
    rec = bytearray(OBJ_SIZE)
    struct.pack_into(">I", rec, 0x36, HUD + index * SCREEN_ROW_BYTES)     # OBJ_SCORE_PTR
    rec[SCORE_TEXT] = 0x02                                               # draw_string set-colour
    rec[SCORE_TEXT + 1] = SCORE_COLOR
    rec[SCORE_TEXT + 2:SCORE_TEXT + 9] = digits
    for name, value in fields.items():
        off, fmt = _OBJ_FIELDS[name]
        width = {"B": 8, "H": 16, "I": 32}[fmt]
        struct.pack_into(">" + fmt, rec, off, value & ((1 << width) - 1))
    return bytes(rec)


def _rider(index, y, **fields):
    """An object whose collision box is a solid two-cell sprite on scanline `y`.

    prev_dst is derived from y so the box's screen address and its y agree, which is the arrangement
    test_overlap is written for and the only one in which "who is higher" means what the joust
    thinks it means."""
    fields.setdefault("prev_dst", SCREEN + y * SCREEN_ROW_BYTES)
    fields.setdefault("prev_src", SPRITE_SOLID)
    fields.setdefault("prev_rows", BOX_ROWS)
    fields.setdefault("prev_shift", BOX_SHIFT)
    return _obj(index, y=y, **fields)


def _egg_holder(index, y, state=EGG_STATE_THROWN, **fields):
    """An object carrying an egg whose box sits on scanline `y` (see `_rider`)."""
    fields.setdefault("egg_dst", SCREEN + y * SCREEN_ROW_BYTES)
    fields.setdefault("egg_src", SPRITE_SOLID)
    fields.setdefault("egg_rows", BOX_ROWS)
    fields.setdefault("egg_shift", BOX_SHIFT)
    fields.setdefault("egg_y", y)
    return _obj(index, egg_state=state, **fields)


# The pterodactyl record, keyed by include/object.h's name for each field so the pin below can
# check every offset this packer encodes positionally. `shift`/`rows` are the LOW BYTES of the
# words at 0x0a/0x18, one byte off each — a pair a `_W` typo in stage_ptero_box would swap, and
# which every case here stages as 0, so the differential alone would not see it.
_PT_FIELDS = {"flags": ("PT_FLAGS", "H"), "dst": ("PT_DST", "I"), "src": ("PT_SRC", "I"),
              "shift": ("PT_SHIFT", "B"), "x": ("PT_X", "H"), "y": ("PT_Y", "H"),
              "dst_off": ("PT_DST_OFF", "H"), "rows": ("PT_ROWS", "B"),
              "swoop_timer": ("PT_SWOOP_TIMER", "B"), "dwell_timer": ("PT_DWELL_TIMER", "B")}
_PT_OFFSETS = {"PT_FLAGS": 0x00, "PT_DST": 0x02, "PT_SRC": 0x06, "PT_SHIFT": 0x0b, "PT_X": 0x0c,
               "PT_Y": 0x0e, "PT_DST_OFF": 0x16, "PT_ROWS": 0x19, "PT_SWOOP_TIMER": 0x1e,
               "PT_DWELL_TIMER": 0x1f}


def _ptero(**fields):
    rec = bytearray(PT_RECORD)
    for name, value in fields.items():
        field, fmt = _PT_FIELDS[name]
        off = _PT_OFFSETS[field]
        width = {"B": 8, "H": 16, "I": 32}[fmt]
        struct.pack_into(">" + fmt, rec, off, value & ((1 << width) - 1))
    return bytes(rec)


def _bird(row, **fields):
    """A live pterodactyl whose box lands on scanline `row`, one cell right of a rider staged there.

    A one-cell offset rather than none, so the column alignment test_overlap does is really being
    exercised — the rider's box is two cells wide, so column 1 of the rider meets column 0 here.
    `row` is the scanline the BOX lands on; the record's own y (which the lance test measures
    against) defaults to it but a case may set it independently."""
    fields.setdefault("flags", PT_FLAG_MOVING_RIGHT)
    fields.setdefault("dst", row * SCREEN_ROW_BYTES + CELL_BYTES)
    fields.setdefault("src", SPRITE_SOLID)
    fields.setdefault("rows", BOX_ROWS)
    fields.setdefault("shift", BOX_SHIFT)
    fields.setdefault("y", row)
    return _ptero(**fields)


_PSPR_FIELDS = {"present": (0x0, "I"), "rows": (0x4, "H"), "cols": (0x6, "H"),
                "src": (0x8, "I"), "dst_off": (0xc, "I")}


def _platform(index, y=None, rows=BOX_ROWS, cols=2, src=SPRITE_SOLID, dst_off=None):
    """One platform_sprites record. Its present byte is platform_present[index], the byte the game's
    own table points at, so a case arms a platform by setting that byte rather than the pointer."""
    if dst_off is None:
        dst_off = 0 if y is None else y * SCREEN_ROW_BYTES
    rec = bytearray(PSPR_RECORD)
    for name, value in (("present", A_PLATFORM_PRESENT + index), ("rows", rows), ("cols", cols),
                        ("src", src), ("dst_off", dst_off)):
        off, fmt = _PSPR_FIELDS[name]
        struct.pack_into(">" + fmt, rec, off, value & 0xffffffff)
    return bytes(rec)


def _table(records, count, stride):
    """`records` (a dict of index -> bytes) laid into a `count`-slot table, zero elsewhere.

    One poke for the whole table, never one per live slot: otherwise the base image's own bytes show
    through in the slots a case does not name, and a sweep that walked past its intended slot would
    read as passing."""
    table = bytearray(count * stride)
    for index, data in records.items():
        table[index * stride:index * stride + len(data)] = data
    return bytes(table)


def _pokes(objects=None, platforms=None, present=(), pteros=None, messages_used=0, **globals_):
    """The whole staged world: every table this routine walks, plus the globals it reads.

    `platforms` defaults to eight records that are all ABSENT (their present bytes are zero), so a
    case that says nothing about platforms gets none — the game's own table would otherwise put the
    real bitmaps under every rider.
    """
    pokes = {
        SPRITE_SOLID: _sprite(0xffff),
        SPRITE_BLANK: _sprite(0x0000),
        A_SCREEN_BASE: struct.pack(">I", SCREEN),
        A_SND_PRIORITY: struct.pack(">H", SND_PRIORITY_IDLE),
        A_PLATFORM_PRESENT: bytes(1 if i in present else 0 for i in range(N_PLATFORMS)),
        A_OBJECT_TABLE: _table(objects or {}, N_OBJECTS, OBJ_SIZE),
        A_PTERODACTYL_TABLE: _table(pteros or {}, N_PTEROS, PT_RECORD),
        A_PLATFORM_SPRITES: _table(platforms or {i: _platform(i) for i in range(N_PLATFORMS)},
                                   N_PLATFORMS, PSPR_RECORD),
        # Every slot below `messages_used` is taken, so find_free_message hands back the next one.
        A_MESSAGE_TABLE: _table({i: bytes([MSG_KIND_PERSISTENT]) for i in range(messages_used)},
                                N_MESSAGES, MSG_RECORD),
        # The text engine score_update paints its digits through; the two words either side of the
        # colour bytes are noise so an unwritten one still shows as a diff.
        A_TEXT_PTR: struct.pack(">IBBBBHH", 0x5a5a5a5a, 0x5a, SCORE_COLOR, 0xf, 0, 0x5a5a, 0x5a5a),
    }
    for name, value in globals_.items():
        addr = {"players_alive": A_PLAYERS_ALIVE, "wave_num": A_WAVE_NUM,
                "gladiator": A_GLADIATOR_WAVE_COUNTDOWN, "conflict": A_PLAYER_CONFLICT_FLAG,
                "first_dismount": A_FIRST_DISMOUNT_OWNER}[name]
        pokes[addr] = bytes([value])
    return pokes


# ================================================================== the case driver

# POISON, MEASURED. The attribution pass inverts every byte the oracle wrote and re-runs both cores
# — so it is only worth anything while the re-run takes the SAME path. collision_check writes the
# very flags word it branches on, and inverting that word turns LIVE | OBJ_FLAG_PLAYER into
# something carrying OBJ_FLAG_RESPAWN, which the head of the object loop skips outright.
#
# That was measured rather than argued, by comparing the oracle's executed-PC set and its write set
# on the plain image against the poisoned one, on nine representative cases. Result: the only shape
# that keeps its path is a run that finds NO collision, whose whole write set is
# hit_box_a / hit_box_b / hit_rows / collision_hit — every byte of which the next test_overlap
# rewrites before reading it. Every other shape diverged, and seven of the eight collapsed to a
# poisoned run that wrote NOTHING AT ALL: a pass that proves precisely nothing.
#
# So poison stays on exactly one case here, test_no_hit_writes_only_scratch, which also asserts the
# write set that makes it sound.
def _case(pokes, poison=False, max_insns=400_000, note=""):
    diffs, info = differential(ENTRY_COLLISION_CHECK, {"_pokes": pokes},
                               lambda lib, buf: lib.g_collision_check(buf),
                               poison=poison, max_insns=max_insns)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def _writes_below_stack(info):
    return {addr: value for addr, value in info["writes"].items() if addr < emu.STACK_GUARD_LO}


def _wrote(info, addr, size=1):
    """The bytes the ORACLE left at `addr`, as an int — or None if it never wrote there.

    Reading the write set rather than the final image is what keeps a case from passing vacuously:
    a field that already held the expected value proves nothing about either core."""
    parts = [info["writes"].get(addr + i) for i in range(size)]
    if any(part is None for part in parts):
        return None
    return int.from_bytes(bytes(parts), "big")


# ================================================================== the outer object loop

def test_empty_table_returns_without_writing():
    """Fourteen empty slots: the loop runs its full length and stops at the `cmpa.l` bound."""
    info = _case(_pokes())
    assert _writes_below_stack(info) == {}, "an empty table produced output"


def test_only_slots_that_are_live_and_not_respawning_are_swept():
    """`beq` on the flags word and `btst #7` are the two skips at the head of the loop."""
    objects = {0: _rider(0, y=40, flags=0),                          # empty
               1: _rider(1, y=40, flags=LIVE | OBJ_FLAG_RESPAWN),    # awaiting respawn
               2: _rider(2, y=40, flags=LIVE)}                       # the only one swept
    info = _case(_pokes(objects=objects, platforms={i: _platform(i, y=40) for i in range(8)},
                        present=(0,)))
    bumped = [slot for slot in range(3)
              if _wrote(info, A_OBJECT_TABLE + slot * OBJ_SIZE + OBJ_FLAGS, 2) is not None]
    assert bumped == [2], f"slots {bumped} were swept; only slot 2 should have been"


def test_every_one_of_the_fourteen_slots_is_swept():
    """The loop's stride and its bound, pinned by putting all fourteen slots on one platform."""
    objects = {slot: _rider(slot, y=40, flags=LIVE) for slot in range(N_OBJECTS)}
    info = _case(_pokes(objects=objects, platforms={i: _platform(i, y=40) for i in range(8)},
                        present=(0,)))
    for slot in range(N_OBJECTS):
        # Piled on one spot they also joust each other, which sets the facing bit on top of the
        # bump — so the assertion is on the bump bit alone.
        written = _wrote(info, A_OBJECT_TABLE + slot * OBJ_SIZE + OBJ_FLAGS, 2)
        assert written is not None and written & OBJ_FLAG_PLATFORM_BUMP, f"slot {slot} not swept"


def test_a_slot_past_the_end_is_not_swept():
    """effect_table starts where object_table ends; a rider-shaped record there must be ignored."""
    objects = {slot: _rider(slot, y=40, flags=LIVE) for slot in range(N_OBJECTS)}
    pokes = _pokes(objects=objects, platforms={i: _platform(i, y=40) for i in range(8)},
                   present=(0,))
    pokes[A_OBJECT_TABLE_END] = _rider(0, y=40, flags=LIVE)
    info = _case(pokes)
    assert _wrote(info, A_OBJECT_TABLE_END + OBJ_FLAGS, 2) is None, "the sweep ran past its bound"


# ================================================================== sweep 1: the platforms

def _platform_case(flags, present=(0,), platforms=None, **kwargs):
    objects = {0: _rider(0, y=40, flags=flags)}
    return _case(_pokes(objects=objects, present=present,
                        platforms=platforms or {i: _platform(i, y=40) for i in range(8)}),
                 **kwargs)


def test_platform_bump_sets_bit_14():
    info = _platform_case(LIVE)
    assert _wrote(info, A_OBJECT_TABLE + OBJ_FLAGS, 2) == LIVE | OBJ_FLAG_PLATFORM_BUMP


@pytest.mark.parametrize("flags,expected",
                         ((LIVE, []), (LIVE | OBJ_FLAG_PLAYER, [SND_PLATFORM_BUMP])))
def test_only_a_player_gets_the_bump_sound(flags, expected):
    """`btst #2,d0` after the flags word is stored — an enemy scraping a platform is silent."""
    info = _platform_case(flags)
    assert _dosound_indices(info) == expected


def test_an_absent_platform_is_never_tested():
    """The present byte is reached through the record's own POINTER, so a permuted table has to
    follow the pointer rather than the record's index."""
    platforms = {i: _platform(N_PLATFORMS - 1 - i, y=40) for i in range(N_PLATFORMS)}
    info = _platform_case(LIVE, present=(0,), platforms=platforms)
    assert _wrote(info, A_OBJECT_TABLE + OBJ_FLAGS, 2) == LIVE | OBJ_FLAG_PLATFORM_BUMP
    info = _platform_case(LIVE, present=(), platforms=platforms)
    assert _wrote(info, A_OBJECT_TABLE + OBJ_FLAGS, 2) is None, "an absent platform was tested"


def test_the_first_platform_hit_ends_the_sweep():
    """Two platforms under one rider: the second is never staged, which shows in hit_box_b."""
    platforms = {0: _platform(0, y=40, cols=2), 1: _platform(1, y=40, cols=3)}
    platforms.update({i: _platform(i) for i in range(2, N_PLATFORMS)})
    info = _platform_case(LIVE, present=(0, 1), platforms=platforms)
    assert _wrote(info, A_HIT_BOX_B + 0x8, 2) == 2, "hit_box_b holds the SECOND platform's width"


def test_platform_row_count_is_the_low_byte_of_the_rows_word():
    """`addq.l #1,a3 ; move.b (a3)+` reads the odd half of PSPR_ROWS, so a rows word of 0x0104 is
    four rows and 0x0400 is none at all (which `subq.b` then reads as 256)."""
    for rows_word, note in ((0x0100 | BOX_ROWS, "high half ignored"), (BOX_ROWS << 8, "low half")):
        platforms = {0: _platform(0, y=40, rows=rows_word)}
        platforms.update({i: _platform(i) for i in range(1, N_PLATFORMS)})
        _platform_case(LIVE, present=(0,), platforms=platforms, note=note)


@pytest.mark.parametrize("dst_off", (0, 0xa0, 0x28 * 0xa0, 0x50, 0x63ffa0, 0xffffffff))
def test_platform_box_y_is_the_screen_offset_divided_by_a_scanline(dst_off):
    """`divu.w #$a0` on the offset, and the last two exercise its OVERFLOW, where the 68000 leaves
    the dividend untouched so the field takes the offset's own low word instead of a quotient."""
    platforms = {0: _platform(0, dst_off=dst_off)}
    platforms.update({i: _platform(i) for i in range(1, N_PLATFORMS)})
    _platform_case(LIVE, present=(0,), platforms=platforms, note=f"dst_off={dst_off:#x}")


def test_a_dead_object_bumps_platforms_and_then_stops():
    """`btst #13,d0` sits AFTER the platform sweep, so a corpse still scrapes — but never jousts."""
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_DEAD),
               1: _rider(1, y=40, flags=LIVE)}
    info = _case(_pokes(objects=objects, present=(0,),
                        platforms={i: _platform(i, y=40) for i in range(8)}))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_FLAGS, 2) \
        == LIVE | OBJ_FLAG_DEAD | OBJ_FLAG_PLATFORM_BUMP, "the corpse did not bump"
    # Slot 1 sits on the same spot, so a corpse that carried on would tie with it: joust_bounce
    # would set its facing bit and play_sound would put the clash on the ledger. Neither happens
    # (the bump sound is a player's only, and both riders here are enemies).
    assert not _wrote(info, A_OBJECT_TABLE + OBJ_SIZE + OBJ_FLAGS, 2) & OBJ_FLAG_FACING_RIGHT, \
        "the dead slot went on to joust"
    assert _dosound_indices(info) == [], "the dead slot went on to joust"


def test_no_hit_writes_only_scratch():
    """A rider clear of everything: the whole write set is the two hit boxes and the two flags the
    narrow phase sets, every byte of which the next test_overlap rewrites before reading it. This is
    the case the poison flag is measured on — see the note above `_case`."""
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_PLAYER),
               1: _rider(1, y=140, flags=LIVE)}
    info = _case(_pokes(objects=objects, present=(0,),
                        platforms={i: _platform(i, y=180) for i in range(8)}), poison=True)
    scratch = set(range(A_HIT_BOX_A, A_HIT_BOX_A + 0x20)) | {A_HIT_ROWS, A_COLLISION_HIT}
    assert set(_writes_below_stack(info)) <= scratch, \
        f"a miss wrote outside the hit boxes: {sorted(set(_writes_below_stack(info)) - scratch)}"


# ================================================================== sweep 2: the joust

def _dosound_indices(info):
    """Which sound_table entries the run played, in order.

    play_sound hands XBIOS Dosound a command-list POINTER, which is off-image; the kit's ledger
    records those pointers and `differential` already compares the two sides' streams. Mapping them
    back through sound_table is what lets a case name the sound it expects.
    """
    table = harness.BASE_IMAGE
    by_pointer = {int.from_bytes(table[A_SOUND_TABLE + 4 * i:A_SOUND_TABLE + 4 * i + 4], "big"): i
                  for i in range(N_SOUNDS)}
    return [by_pointer[pointer] for pointer in info["regs"].get("dosound", [])]


def _joust(object_flags, other_flags, object_y=40, other_y=40, **kwargs):
    """Two riders whose boxes overlap, in slots 0 and 1."""
    objects = {0: _rider(0, y=object_y, flags=object_flags, x=100, vy=4, vx=3),
               1: _rider(1, y=other_y, flags=other_flags, x=140, vy=-4, vx=-3)}
    return _pokes(objects=objects, **kwargs)


def test_height_tie_bounces_both_riders():
    """Equal y: nobody is unseated, the clash sound plays and joust_bounce turns the pair apart."""
    info = _case(_joust(LIVE | OBJ_FLAG_PLAYER, LIVE), note="tie")
    assert _dosound_indices(info) == [SND_JOUST_TIE]
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is None, "a tie started a dismount"


def test_two_enemies_only_shove_each_other():
    """Neither is a player, so no death: the loser is pushed down, the winner up, and both bounce."""
    info = _case(_joust(LIVE, LIVE, object_y=40, other_y=41))
    assert _dosound_indices(info) == [], "an enemy-versus-enemy joust made a sound"
    assert _wrote(info, A_OBJECT_TABLE + OBJ_VY, 2) == 0xfffc, "the winner was not thrown upward"
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SIZE + OBJ_VY, 2) == 4, "the loser was not pushed down"


def test_an_enemy_on_top_of_a_player_still_only_shoves():
    """The `btst #2,d0` that gates the fatal branches is on the OBJECT's flags, not the winner's, so
    an enemy in the lower slot cannot unseat the player above it on its own turn."""
    info = _case(_joust(LIVE, LIVE | OBJ_FLAG_PLAYER, object_y=41, other_y=40))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SIZE + OBJ_EGG_STATE) is None, \
        "the enemy unseated the player"


@pytest.mark.parametrize("dead_or_gone", (OBJ_FLAG_DEAD, OBJ_FLAG_RESPAWN))
def test_the_other_rider_must_be_on_the_playfield(dead_or_gone):
    info = _case(_joust(LIVE | OBJ_FLAG_PLAYER, LIVE | dead_or_gone))
    assert _dosound_indices(info) == [], "a rider that is not on the playfield was jousted"


def test_each_pair_meets_once_per_frame():
    """`a3` starts one slot ABOVE `a0`, so slot 1's own turn does not re-test slot 0."""
    info = _case(_joust(LIVE, LIVE, object_y=40, other_y=41))
    # Slot 1's turn would push slot 0 down again, undoing what slot 0's turn did.
    assert _wrote(info, A_OBJECT_TABLE + OBJ_VY, 2) == 0xfffc, "slot 1 re-tested slot 0"


# ---- a player unseating an enemy: the dismount ----

ENEMY_BOUNTIES = (
    (0, 0, 7, 5),                                    # type 0: 700 into the hundreds, 50 into tens
    (OBJ_FLAG_TYPE_LO, 0, 5, 0),                     # type 1: 500
    (OBJ_FLAG_TYPE_HI, 0, 7, 5),                     # type 2: bit 0 clear, so 750 again
    (OBJ_FLAG_TYPE_LO | OBJ_FLAG_TYPE_HI, 1, 5, 0),  # type 3: 1000 + 500
)


@pytest.mark.parametrize("type_bits,thousands,hundreds,tens", ENEMY_BOUNTIES)
def test_enemy_bounty_comes_from_its_type_bits(type_bits, thousands, hundreds, tens):
    """`btst #0` then `btst #1` on the enemy's flags, paid into the player's ASCII digits."""
    pokes = _joust(LIVE | OBJ_FLAG_PLAYER, LIVE | type_bits, object_y=40, other_y=41)
    info = _case(pokes, note=f"type_bits={type_bits:#x}")
    digits = ord("0")
    for offset, added in ((OBJ_SCORE_LIFE_DIGIT, thousands), (OBJ_SCORE_HUNDREDS, hundreds),
                          (OBJ_SCORE_PENDING, tens)):
        assert _wrote(info, A_OBJECT_TABLE + offset) == (digits + added if added else None), \
            f"digit at {offset:#x}: expected +{added}"


def test_unseating_an_enemy_builds_the_egg_it_drops():
    """The whole handshake with the egg subsystem, in one case."""
    pokes = _joust(LIVE | OBJ_FLAG_PLAYER, LIVE | OBJ_FLAG_TYPE_LO, object_y=40, other_y=41)
    pokes[A_WAVE_NUM] = bytes([3])
    info = _case(pokes)
    enemy = A_OBJECT_TABLE + OBJ_SIZE
    assert _wrote(info, enemy + OBJ_EGG_X, 2) == 140
    assert _wrote(info, enemy + OBJ_EGG_Y, 2) == 41 + 5
    assert _wrote(info, enemy + OBJ_EGG_DX, 2) == 0xfffd                 # the rider's own vx
    assert _wrote(info, enemy + OBJ_EGG_DST, 4) == \
        SCREEN + 41 * SCREEN_ROW_BYTES + 6 * SCREEN_ROW_BYTES
    assert _wrote(info, enemy + OBJ_EGG_SRC, 4) == A_EGG_SPRITE_STILL
    assert _wrote(info, enemy + OBJ_EGG_STATE) == EGG_STATE_THROWN
    assert _wrote(info, enemy + OBJ_EGG_HATCH_TIMER) == EGG_HATCH_FRAMES - 3
    # type 1 hatches as type 2, and bit 7 tells update_egg_draw the egg has never been drawn.
    assert _wrote(info, enemy + OBJ_EGG_SPAWN_FLAGS) == EGG_SPAWN_UNDRAWN | 2
    assert _wrote(info, enemy + OBJ_FLAGS, 2) is not None


@pytest.mark.parametrize("type_bits,hatched", ((0, 1), (OBJ_FLAG_TYPE_LO, 2),
                                               (OBJ_FLAG_TYPE_HI, 3),
                                               (OBJ_FLAG_TYPE_LO | OBJ_FLAG_TYPE_HI, 3)))
def test_the_hatched_rider_type_climbs_and_sticks_at_three(type_bits, hatched):
    pokes = _joust(LIVE | OBJ_FLAG_PLAYER, LIVE | type_bits, object_y=40, other_y=41)
    info = _case(pokes, note=f"type_bits={type_bits:#x}")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SIZE + OBJ_EGG_SPAWN_FLAGS) \
        == EGG_SPAWN_UNDRAWN | hatched


@pytest.mark.parametrize("wave_num", (0, 1, 0x87, 0x88, 0x89, 0xff))
def test_the_hatch_wait_is_a_byte_subtraction(wave_num):
    """`move.b #$88` then `sub.b wave_num` — a byte op, so a high wave number wraps rather than
    going negative."""
    pokes = _joust(LIVE | OBJ_FLAG_PLAYER, LIVE, object_y=40, other_y=41)
    pokes[A_WAVE_NUM] = bytes([wave_num])
    info = _case(pokes, note=f"wave_num={wave_num:#x}")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SIZE + OBJ_EGG_HATCH_TIMER) \
        == (EGG_HATCH_FRAMES - wave_num) & 0xff


def test_unseating_an_enemy_plays_the_death_sound_twice():
    """Once at 0x13af4, before the egg is built, and again in the shared tail at 0x13aa6."""
    info = _case(_joust(LIVE | OBJ_FLAG_PLAYER, LIVE, object_y=40, other_y=41))
    assert _dosound_indices(info) == [SND_RIDER_UNSEATED, SND_RIDER_UNSEATED]


# ---- a player being unseated ----

def test_a_player_below_is_unseated_and_leaves_the_loop():
    """start_death_anim arms the dismount sprite, and the sweep stops: a third rider that would also
    have collided is never reached."""
    objects = {0: _rider(0, y=41, flags=LIVE | OBJ_FLAG_PLAYER, x=100, vy=4),
               1: _rider(1, y=40, flags=LIVE, x=140, vy=-4),
               2: _rider(2, y=39, flags=LIVE, x=140, vy=-4)}
    info = _case(_pokes(objects=objects))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_FLAGS, 2) is not None
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_SRC, 4) == A_DEATH_SPRITE_P1
    assert _wrote(info, A_OBJECT_TABLE + 2 * OBJ_SIZE + OBJ_VY, 2) is None, \
        "the sweep carried on past the death"


def test_a_dying_player_still_collects_eggs_but_meets_no_bird():
    """The death jumps FORWARD to the egg sweep (0x13b9a), and the `btst #13` at 0x13d26 is what
    then keeps it out of the pterodactyl sweep."""
    objects = {0: _rider(0, y=41, flags=LIVE | OBJ_FLAG_PLAYER, x=100, vy=4),
               1: _rider(1, y=40, flags=LIVE, x=140, vy=-4),
               3: _egg_holder(3, y=41)}
    info = _case(_pokes(objects=objects, pteros={0: _bird(41)}))
    assert _wrote(info, A_OBJECT_TABLE + 3 * OBJ_SIZE + OBJ_EGG_STATE) == 0, "the egg was not taken"
    assert _wrote(info, A_PTERODACTYL_TABLE) is None, "a dead player traded with a bird"


def test_players_alive_of_exactly_one_raises_the_conflict_flag():
    """`cmpi.b #$1` — an exact compare, not "at most one"."""
    for alive, expected in ((0, None), (1, 1), (2, None)):
        objects = {0: _rider(0, y=41, flags=LIVE | OBJ_FLAG_PLAYER, x=100),
                   1: _rider(1, y=40, flags=LIVE, x=140)}
        info = _case(_pokes(objects=objects, players_alive=alive), note=f"alive={alive}")
        assert _wrote(info, A_PLAYER_CONFLICT_FLAG) == expected


# ---- player versus player: the gladiator bonus ----

def _duel(object_y, other_y, **globals_):
    objects = {0: _rider(0, y=object_y, flags=LIVE | OBJ_FLAG_PLAYER, x=100),
               1: _rider(1, y=other_y, flags=LIVE | OBJ_FLAG_PLAYER, x=140)}
    return _pokes(objects=objects, **globals_)


@pytest.mark.parametrize("object_y,other_y,winner,owner",
                         ((40, 41, A_OBJECT_TABLE, 1), (41, 40, A_PLAYER2, 2)))
def test_the_first_player_duel_of_a_wave_pays_3000(object_y, other_y, winner, owner):
    """500 always, and 2500 more for the wave's first dismount — recorded in first_dismount_owner so
    it cannot be claimed twice. The three `addq.b`s land as +2 on the thousands and +10 on the
    hundreds, and score_update then carries that second column: 0x3a is above '9', so the settled
    string is thousands '3' and hundreds '0'."""
    info = _case(_duel(object_y, other_y), note=f"owner={owner}")
    assert _wrote(info, A_FIRST_DISMOUNT_OWNER) == owner
    assert _wrote(info, winner + OBJ_SCORE_LIFE_DIGIT) == ord("0") + 3
    assert _wrote(info, winner + OBJ_SCORE_HUNDREDS) == ord("0")
    assert _wrote(info, A_PLAYER_CONFLICT_FLAG) == 1


@pytest.mark.parametrize("gladiator,first_dismount", ((1, 0), (0xff, 0), (0, 1), (0, 2)))
def test_the_gladiator_bonus_is_paid_at_most_once_per_wave(gladiator, first_dismount):
    """Either gate closed leaves the plain 500 — and neither writes first_dismount_owner again."""
    info = _case(_duel(40, 41, gladiator=gladiator, first_dismount=first_dismount),
                 note=f"gladiator={gladiator} first={first_dismount}")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SCORE_HUNDREDS) == ord("0") + 5
    assert _wrote(info, A_OBJECT_TABLE + OBJ_SCORE_LIFE_DIGIT) is None
    assert _wrote(info, A_FIRST_DISMOUNT_OWNER) is None


def test_the_loser_of_a_duel_gets_the_death_sprite_and_the_winner_is_thrown_up():
    info = _case(_duel(40, 41))
    loser = A_PLAYER2
    assert _wrote(info, loser + OBJ_EGG_SRC, 4) == A_DEATH_SPRITE_OTHER
    assert _wrote(info, loser + OBJ_FLAGS, 2) is not None
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is None, "the winner started a dismount too"


# ================================================================== sweep 3: the eggs

def _egg_case(player_slot=0, player_flags=LIVE | OBJ_FLAG_PLAYER, holder_slot=3, y=40,
              state=EGG_STATE_THROWN, holder_fields=None, **kwargs):
    objects = {player_slot: _rider(player_slot, y=y, flags=player_flags, x=100),
               holder_slot: _egg_holder(holder_slot, y=y, state=state, **(holder_fields or {}))}
    return _pokes(objects=objects, **kwargs)


def test_only_a_player_collects_eggs():
    """`btst #2,d0` at 0x13b9a gates the whole sweep."""
    info = _case(_egg_case(player_flags=LIVE))
    assert _wrote(info, A_OBJECT_TABLE + 3 * OBJ_SIZE + OBJ_EGG_STATE) is None


def test_collecting_an_egg_clears_it_erases_it_and_pays_the_chain():
    info = _case(_egg_case())
    holder = A_OBJECT_TABLE + 3 * OBJ_SIZE
    assert _wrote(info, holder + OBJ_EGG_STATE) == 0, "the egg was not consumed"
    assert _dosound_indices(info) == [SND_EGG_COLLECTED]
    assert any(SCREEN <= addr < SCREEN + 0x4000 for addr in info["writes"]), \
        "erase_egg_sprite never ran"
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_CHAIN) == 1, "the chain counter did not advance"


EGG_STATE_RESTING = 0x22   # any live state that is NOT the in-flight one, so only the chain pays


def _egg_case_with_chain(chain, state=EGG_STATE_RESTING):
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100, egg_chain=chain),
               3: _egg_holder(3, y=40, state=state)}
    return _pokes(objects=objects)


@pytest.mark.parametrize("chain,expected_next", ((0, 1), (1, 2), (2, 3), (3, None), (0x80, 0x81)))
def test_the_chain_counter_climbs_and_sticks_at_three(chain, expected_next):
    """`cmpi.b #$3` is an exact compare, so a counter poked past the table's four records goes on
    climbing — and the record it indexes is 0x400 bytes past egg_bonus_table, unchecked. Exactly
    what the original does."""
    info = _case(_egg_case_with_chain(chain), note=f"chain={chain:#x}")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_CHAIN) == expected_next


@pytest.mark.parametrize("chain", range(N_BONUS))
def test_the_chain_amounts_come_out_of_egg_bonus_table(chain):
    """250 / 500 / 750 / 1000: the three digit increments and the string are all table data."""
    record = A_EGG_BONUS_TABLE + chain * BONUS_RECORD
    table = harness.BASE_IMAGE
    string = int.from_bytes(table[record:record + 4], "big")
    added = table[record + 4:record + 7]

    info = _case(_egg_case_with_chain(chain), note=f"chain={chain}")
    for offset, amount in ((OBJ_SCORE_LIFE_DIGIT, added[0]), (OBJ_SCORE_HUNDREDS, added[1]),
                           (OBJ_SCORE_PENDING, added[2])):
        # `add.b` (not `addq.b`), so all three digits are written even where the record adds 0 —
        # and every amount here is small enough that score_update's carry sweep has nothing to do.
        assert _wrote(info, A_OBJECT_TABLE + offset) == ord("0") + amount, \
            f"digit at {offset:#x}: expected +{amount}"
    slot = A_MESSAGE_TABLE
    assert _wrote(info, slot + MSG_STRING, 4) == string, "the chain message used the wrong string"


def test_an_egg_in_flight_pays_500_more_and_takes_a_second_message_slot():
    """The dismount bonus claims its slot's kind byte BEFORE the chain message asks for one, which
    is the only reason the two do not land on top of each other."""
    info = _case(_egg_case(state=EGG_STATE_THROWN))
    first, second = A_MESSAGE_TABLE, A_MESSAGE_TABLE + MSG_RECORD
    assert _wrote(info, first + MSG_STRING, 4) == STR_BONUS_500
    assert _wrote(info, first + MSG_KIND) == MSG_KIND_PERSISTENT
    assert _wrote(info, first + MSG_TIMER) == MSG_BONUS_FRAMES
    assert _wrote(info, first + MSG_COLOR) == MSG_BONUS_COLOR
    assert _wrote(info, second + MSG_KIND) == MSG_KIND_PERSISTENT, "the chain message reused a slot"
    # the chain message takes its colour from the collector's own score string
    assert _wrote(info, second + MSG_COLOR) == SCORE_COLOR


@pytest.mark.parametrize("state", (0x22, 0x21, 0x24, 0x01, 0xff))
def test_only_a_freshly_dismounted_egg_pays_the_extra_500(state):
    """`cmpi.b #$23` is an exact compare — any other live state is just the chain."""
    info = _case(_egg_case(state=state), note=f"state={state:#x}")
    assert _wrote(info, A_MESSAGE_TABLE + MSG_STRING, 4) != STR_BONUS_500
    assert _wrote(info, A_MESSAGE_TABLE + MSG_RECORD + MSG_KIND) is None, "a second message was made"


@pytest.mark.parametrize("egg_row,expect_above", ((40, True), (6, True), (5, False), (0, False)))
def test_the_in_flight_message_drops_below_the_egg_when_it_would_clear_the_screen_top(
        egg_row, expect_above):
    """Five scanlines above the egg, unless that lands at or above screen_base — a SIGNED `cmp.l`
    against the base, so the fallback is one scanline BELOW and one cell right."""
    info = _case(_egg_case(y=egg_row), note=f"egg_row={egg_row}")
    egg_dst = SCREEN + egg_row * SCREEN_ROW_BYTES
    expected = egg_dst - 5 * SCREEN_ROW_BYTES if expect_above \
        else egg_dst + SCREEN_ROW_BYTES + CELL_BYTES
    assert _wrote(info, A_MESSAGE_TABLE + MSG_SCREEN_PTR, 4) == expected


def test_a_full_message_table_writes_the_record_over_address_zero():
    """find_free_message answers `suba.l a0,a0` when nothing is free, and the caller writes through
    it anyway. The same original bug player_death carries; reproduced, not guarded."""
    info = _case(_egg_case(messages_used=N_MESSAGES))
    assert _wrote(info, MSG_KIND) == MSG_KIND_PERSISTENT, "the record did not land at address 0"
    assert _wrote(info, MSG_STRING, 4) is not None


@pytest.mark.parametrize("holder_slot", (0, 1))
def test_a_players_own_egg_record_is_never_collected(holder_slot):
    """The sweep starts at object_table slot 2, so the death sprite a dying player is running is not
    food for the other one."""
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100),
               1: _rider(1, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100)}
    holder = _egg_holder(holder_slot, y=40, state=EGG_STATE_THROWN)
    # keep the rider fields of the slot that also carries the egg
    merged = bytearray(objects[holder_slot])
    for off in (OBJ_EGG_STATE, OBJ_EGG_ROWS, OBJ_EGG_SHIFT):
        merged[off] = holder[off]
    merged[OBJ_EGG_DST:OBJ_EGG_DST + 4] = holder[OBJ_EGG_DST:OBJ_EGG_DST + 4]
    merged[OBJ_EGG_SRC:OBJ_EGG_SRC + 4] = holder[OBJ_EGG_SRC:OBJ_EGG_SRC + 4]
    merged[OBJ_EGG_Y:OBJ_EGG_Y + 2] = holder[OBJ_EGG_Y:OBJ_EGG_Y + 2]
    objects[holder_slot] = bytes(merged)
    info = _case(_pokes(objects=objects))
    assert _wrote(info, A_OBJECT_TABLE + holder_slot * OBJ_SIZE + OBJ_EGG_STATE) is None


@pytest.mark.parametrize("player_slot,addr", ((0, A_OBJECT_TABLE), (1, A_PLAYER2)))
def test_the_score_redraw_alias_is_chosen_by_the_collectors_slot(player_slot, addr):
    """Two `cmpa.l`s against the two player slots, each guarding its own score_update alias."""
    info = _case(_egg_case(player_slot=player_slot))
    assert _wrote(info, addr + OBJ_SCORE_HUNDREDS) is not None
    assert any(HUD + player_slot * SCREEN_ROW_BYTES <= a
               < HUD + (player_slot + 1) * SCREEN_ROW_BYTES for a in info["writes"]), \
        "the collector's own HUD row was never repainted"


def test_more_than_one_egg_is_collected_in_one_pass():
    """The sweep carries on after a collection rather than returning, so a player standing on two
    eggs takes both — and the chain counter climbs once per egg."""
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100),
               3: _egg_holder(3, y=40), 7: _egg_holder(7, y=40)}
    info = _case(_pokes(objects=objects))
    for slot in (3, 7):
        assert _wrote(info, A_OBJECT_TABLE + slot * OBJ_SIZE + OBJ_EGG_STATE) == 0
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_CHAIN) == 2


# ================================================================== sweep 4: the pterodactyls

def _bird_case(player_flags=LIVE | OBJ_FLAG_PLAYER, player_x=100, y=40, birds=None, **kwargs):
    objects = {0: _rider(0, y=y, flags=player_flags, x=player_x, vx=3, target_vx=7)}
    return _pokes(objects=objects, pteros=birds or {0: _bird(y)}, **kwargs)


def test_only_a_live_player_meets_a_bird():
    info = _case(_bird_case(player_flags=LIVE))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is None
    assert _wrote(info, A_PTERODACTYL_TABLE) is None


@pytest.mark.parametrize("bird_flags", (0, PT_FLAG_JUST_SPAWNED, PT_FLAG_DYING,
                                        PT_FLAG_MOVING_RIGHT | PT_FLAG_DYING))
def test_a_bird_that_is_empty_spawning_or_already_dying_is_skipped(bird_flags):
    info = _case(_bird_case(birds={0: _bird(40, flags=bird_flags)}), note=f"flags={bird_flags:#x}")
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is None, "a skipped bird still killed"


def test_touching_a_bird_kills_the_player():
    """Level with the bird rather than one row under it, so the lance misses: the death block is
    start_death_anim's, inlined — right down to the sprite and the 50 points."""
    info = _case(_bird_case())
    player = A_OBJECT_TABLE
    assert _wrote(info, player + OBJ_EGG_SRC, 4) == A_DEATH_SPRITE_P1
    assert _wrote(info, player + OBJ_EGG_ROWS) == 9
    assert _wrote(info, player + OBJ_EGG_STATE) == 0x19
    assert _wrote(info, player + OBJ_SCORE_PENDING) == ord("0") + 5
    assert _wrote(info, A_PLAYER_CONFLICT_FLAG) == 1
    assert _dosound_indices(info) == [SND_RIDER_UNSEATED]


def test_a_bird_death_keeps_the_egg_chain_that_start_death_anim_would_clear():
    """The copy of start_death_anim inlined here drops its `clr.b OBJ_EGG_CHAIN`, so a player killed
    by a bird keeps the chain a player unseated in a joust loses. Both halves are asserted, since a
    reconstruction that CALLED start_death_anim would pass the first on its own."""
    objects = {0: _rider(0, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100, egg_chain=2)}
    info = _case(_pokes(objects=objects, pteros={0: _bird(40)}))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_CHAIN) is None, "the bird death cleared the chain"

    objects = {0: _rider(0, y=41, flags=LIVE | OBJ_FLAG_PLAYER, x=100, egg_chain=2),
               1: _rider(1, y=40, flags=LIVE, x=140)}
    info = _case(_pokes(objects=objects))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_CHAIN) == 0, "the joust death kept the chain"


@pytest.mark.parametrize("player2", (False, True))
def test_the_death_sprite_is_player_1s_only_for_player_1(player2):
    """A full `cmpa.l` against object_table, so player 2 takes the other sprite and state."""
    slot = 1 if player2 else 0
    objects = {slot: _rider(slot, y=40, flags=LIVE | OBJ_FLAG_PLAYER, x=100)}
    info = _case(_pokes(objects=objects, pteros={0: _bird(40)}))
    addr = A_PLAYER2 if player2 else A_OBJECT_TABLE
    assert _wrote(info, addr + OBJ_EGG_SRC, 4) == \
        (A_DEATH_SPRITE_OTHER if player2 else A_DEATH_SPRITE_P1)
    assert _wrote(info, addr + OBJ_EGG_STATE) == (0x20 if player2 else 0x19)


@pytest.mark.parametrize("rise_ok", (True, False))
def test_the_death_sprite_is_clamped_to_the_top_of_the_framebuffer(rise_ok):
    """Four scanlines up, unless that reaches screen_base — a SIGNED `cmp.l`, as in world.c."""
    row = 40 if rise_ok else 3
    objects = {0: _rider(0, y=row, flags=LIVE | OBJ_FLAG_PLAYER, x=100)}
    info = _case(_pokes(objects=objects, pteros={0: _bird(row)}))
    rider_dst = SCREEN + row * SCREEN_ROW_BYTES
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_DST, 4) == \
        (rider_dst - 0x280 if rise_ok else rider_dst)


# ---- the lance ----

PLAYER_X = 100


def _lance_case(bird_moving_right, player_facing_right, gap, dy=-1, y=40):
    """A bird whose box overlaps the player's, `dy` scanlines away in y and `gap` pixels in x.

    The bird's box follows its y, as the game's own does, so the pair really touch for every `dy`
    the window test uses. Its x, on the other hand, only ever feeds the lance test — the box is
    placed one CELL right of the player whatever `gap` says — which is what lets a case sweep the
    horizontal window without also sweeping whether there is a collision at all.
    """
    player_flags = LIVE | OBJ_FLAG_PLAYER | (OBJ_FLAG_FACING_RIGHT if player_facing_right else 0)
    objects = {0: _rider(0, y=y, flags=player_flags, x=PLAYER_X, vx=3, target_vx=7)}
    bird = _bird(y + dy, flags=PT_LIVE | (PT_FLAG_MOVING_RIGHT if bird_moving_right else 0),
                 x=(PLAYER_X + gap) & 0xffff)
    return _pokes(objects=objects, pteros={0: bird})


def _lanced(info):
    return _wrote(info, A_PTERODACTYL_TABLE) is not None and \
        _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is None


@pytest.mark.parametrize("dy", (-2, -1, 0, 1))
def test_the_bird_must_be_exactly_one_scanline_above(dy):
    """`cmpi.w #$ffff` on the y gap — an exact word, not a band. The range is one scanline either
    side because PT_Y is BOTH the lance's measurement and the box's own scanline: a bird staged
    further away stops overlapping at all, which would prove nothing about the lance."""
    info = _case(_lance_case(False, True, gap=4, dy=dy), note=f"dy={dy}")
    assert _lanced(info) == (dy == -1)


# The two windows, from the SIGNED bound to the UNSIGNED one, plus a step either side of each.
@pytest.mark.parametrize("gap,connects", ((0, True), (1, True), (0x11, True), (0x12, False),
                                          (0x1000, False), (0x7fff, False), (-0x8000, True),
                                          (-0x7fff, True), (-0x130, True), (-0x12f, True),
                                          (-0x12e, False), (-1, False)))
def test_a_bird_flying_left_must_be_just_to_the_players_right(gap, connects):
    """The player faces right into it. `cmpi.w #$11` + bgt is SIGNED and caps the near side at 17
    pixels; `cmpi.w #$fed1` + bhi is UNSIGNED and cuts out the near-NEGATIVE gaps, -1 down to
    -0x12e. What survives on that side is -0x12f and further, which — x wrapping at 320 — is the
    same bird just to the player's right, measured the other way round the screen."""
    info = _case(_lance_case(False, True, gap=gap), note=f"gap={gap:#x}")
    assert _lanced(info) == connects


@pytest.mark.parametrize("gap,connects", ((-0x1f, True), (-0x10, True), (-0x0f, False),
                                          (-0x20, False), (0, False), (0x121, True),
                                          (0x120, False), (0x7ff0, True), (0x7ff1, False)))
def test_a_bird_flying_right_must_be_just_to_the_players_left(gap, connects):
    """The mirror window, biased by 0xf before the compares — so 0x121 (which is 0x130 after the
    bias) connects by wrapping right round the screen."""
    info = _case(_lance_case(True, False, gap=gap), note=f"gap={gap:#x}")
    assert _lanced(info) == connects


@pytest.mark.parametrize("bird_right,facing_right", ((False, False), (True, True)))
def test_the_player_must_be_facing_into_the_bird(bird_right, facing_right):
    """`btst #15,d0`, opposite senses on the two branches: touching a bird from behind is fatal."""
    info = _case(_lance_case(bird_right, facing_right, gap=-0x18 if bird_right else 4))
    assert not _lanced(info), "the lance connected from behind"


def test_lancing_a_bird_turns_the_player_round_and_pays_1000():
    info = _case(_lance_case(False, True, gap=4))
    player = A_OBJECT_TABLE
    assert _wrote(info, A_PTERODACTYL_TABLE, 2) == PT_LIVE | PT_FLAG_DYING
    assert _wrote(info, A_PTERODACTYL_TABLE + 0x1e) == 4
    assert _wrote(info, A_PTERODACTYL_TABLE + 0x1f) == 4
    assert _wrote(info, player + OBJ_FLAGS, 2) == LIVE | OBJ_FLAG_PLAYER   # bit 15 toggled OFF
    assert _wrote(info, player + OBJ_VX, 2) == 0xfffd
    assert _wrote(info, player + OBJ_TARGET_VX, 2) == 0xfff9
    assert _wrote(info, player + OBJ_SCORE_LIFE_DIGIT) == ord("0") + 1
    assert _dosound_indices(info) == [SND_PTERO_LANCED]


def test_the_bird_box_offset_is_sign_extended_into_the_address():
    """`adda.w 22(a3),a4` sign-extends the offset into the box's ADDRESS, while the same field is
    ZERO-extended into its y (`clr.l d1 ; move.w ; divu.w`). Staging a negative offset and biasing
    PT_Y by the quotient it produces (0xfff8 / 0xa0 = 409) puts the box back exactly where the
    rider is — which only happens if the address bent negative and the y did not."""
    y, offset = 40, 0xfff8
    objects = {0: _rider(0, y=y, flags=LIVE | OBJ_FLAG_PLAYER, x=100)}
    bird = _bird(y, dst=y * SCREEN_ROW_BYTES + CELL_BYTES + 8, dst_off=offset,
                 y=(y - 0xfff8 // 0xa0) & 0xffff)
    info = _case(_pokes(objects=objects, pteros={0: bird}))
    assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is not None, \
        "the box did not land on the rider, so neither extension was exercised"


def test_the_first_bird_that_touches_ends_the_sweep():
    birds = {0: _bird(40), 1: _bird(40)}
    info = _case(_bird_case(birds=birds))
    assert _wrote(info, A_PTERODACTYL_TABLE + PT_RECORD, 2) is None, "the sweep went on to bird 1"


def test_all_four_bird_slots_are_swept():
    for slot in range(N_PTEROS):
        info = _case(_bird_case(birds={slot: _bird(40)}), note=f"slot={slot}")
        assert _wrote(info, A_OBJECT_TABLE + OBJ_EGG_STATE) is not None, f"slot {slot} was skipped"


# ================================================================== fuzz

FUZZ_CHUNKS = 6
FUZZ_CASES = 240


def _fuzz_cases():
    """Random worlds over every sweep at once, so the four run into each other the way a frame does.

    The RNG is seeded ONCE, outside the chunk filter, so every worker replays the identical stream
    and picks its own share out of it."""
    rng = random.Random(0x13842)
    for index in range(FUZZ_CASES):
        rows = [rng.randrange(8, 90) for _ in range(N_OBJECTS)]
        xs = [rng.randrange(0, 0x140) for _ in range(N_OBJECTS)]
        objects = {}
        for slot in range(N_OBJECTS):
            if rng.random() < 0.45:
                continue
            flags = rng.choice((0, LIVE, LIVE | OBJ_FLAG_PLAYER, LIVE | OBJ_FLAG_PLAYER,
                                LIVE | OBJ_FLAG_TYPE_LO, LIVE | OBJ_FLAG_TYPE_HI,
                                LIVE | OBJ_FLAG_TYPE_LO | OBJ_FLAG_TYPE_HI,
                                LIVE | OBJ_FLAG_RESPAWN, LIVE | OBJ_FLAG_DEAD))
            flags |= rng.choice((0, OBJ_FLAG_FACING_RIGHT))
            fields = dict(x=xs[slot], vx=rng.randrange(-8, 9) & 0xffff,
                          vy=rng.randrange(-8, 9) & 0xffff, target_vx=rng.randrange(-8, 9) & 0xffff,
                          egg_chain=rng.randrange(0, 5))
            if slot >= 2 and rng.random() < 0.4:
                fields.update(egg_state=rng.choice((EGG_STATE_THROWN, 0x21, 0x22, 0x0b)),
                              egg_dst=SCREEN + rows[slot] * SCREEN_ROW_BYTES,
                              egg_src=rng.choice((SPRITE_SOLID, SPRITE_BLANK)),
                              egg_rows=BOX_ROWS, egg_shift=0, egg_y=rows[slot],
                              egg_x=rng.randrange(0, 0x140))
            objects[slot] = _rider(slot, y=rows[slot], flags=flags,
                                   prev_src=rng.choice((SPRITE_SOLID, SPRITE_SOLID, SPRITE_BLANK)),
                                   **fields)
        present = tuple(i for i in range(N_PLATFORMS) if rng.random() < 0.3)
        platforms = {i: _platform(i, y=rng.randrange(8, 90)) for i in range(N_PLATFORMS)}
        pteros = {}
        for slot in range(N_PTEROS):
            if rng.random() < 0.6:
                continue
            # Half the birds are aimed at a player slot from exactly one scanline up, with an x gap
            # drawn from around both edges of the lance window: left to itself the sweep almost
            # never lines one up, and the whole lance/kill exchange would go unfuzzed.
            aimed = rng.random() < 0.5
            target = rng.choice((0, 1))
            row = (rows[target] - 1) if aimed else rng.randrange(8, 90)
            x = (xs[target] + rng.choice((0, 1, 0x11, 0x12, -0x10, -0x1f, -0x20, 0x121, 0x120))) \
                if aimed else rng.randrange(0, 0x140)
            pteros[slot] = _bird(row, flags=PT_LIVE | rng.choice((PT_FLAG_MOVING_RIGHT, 0, 0,
                                                                  PT_FLAG_JUST_SPAWNED,
                                                                  PT_FLAG_DYING)),
                                 x=x & 0xffff,
                                 y=(row + rng.choice((0, 0, 0, -1, 1))) & 0xffff,
                                 src=rng.choice((SPRITE_SOLID, SPRITE_BLANK)))
        yield (index, _pokes(objects=objects, platforms=platforms, present=present, pteros=pteros,
                             messages_used=rng.randrange(0, 4),
                             players_alive=rng.randrange(0, 3),
                             wave_num=rng.randrange(0, 6),
                             gladiator=rng.choice((0, 0, 1)),
                             first_dismount=rng.choice((0, 0, 1, 2))))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_collision_check_fuzz(chunk):
    ran = 0
    for index, pokes in _fuzz_cases():
        if index % FUZZ_CHUNKS != chunk:
            continue
        ran += 1
        _case(pokes, max_insns=2_000_000, note=f"fuzz case {index}")
    assert ran, "the chunk filter rejected every case"


# ================================================================== the mirror pins
#
# Everything above restates constants that really live in ../names.txt or in include/collide.h.
# Python cannot import either, so each copy is pinned equal here (see test_constants.py's docstring).

def test_entry_address_matches_names_txt():
    assert harness.NAME_MAP.get(ENTRY_COLLISION_CHECK) == "collision_check"


def test_global_addresses_match_names_txt():
    for addr, name in ((A_PLAYERS_ALIVE, "players_alive"), (A_WAVE_NUM, "wave_num"),
                       (A_PLATFORM_PRESENT, "platform_present"),
                       (A_GLADIATOR_WAVE_COUNTDOWN, "gladiator_wave_countdown"),
                       (A_PLAYER_CONFLICT_FLAG, "player_conflict_flag"),
                       (A_FIRST_DISMOUNT_OWNER, "first_dismount_owner"),
                       (A_COLLISION_HIT, "collision_hit"), (A_SCREEN_BASE, "screen_base"),
                       (A_MESSAGE_TABLE, "message_table"), (A_OBJECT_TABLE, "object_table"),
                       (A_PLAYER2, "player2"), (A_OBJECT_TABLE_END, "effect_table"),
                       (A_PTERODACTYL_TABLE, "pterodactyl_table"),
                       (A_EGG_BONUS_TABLE, "egg_bonus_table"),
                       (A_PLATFORM_SPRITES, "platform_sprites"),
                       (A_EGG_SPRITE_STILL, "egg_sprite_still"),
                       (A_DEATH_SPRITE_P1, "death_sprite_p1"),
                       (A_DEATH_SPRITE_OTHER, "death_sprite_other")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_constants_match_collide_h():
    collide_h = _defines("include/collide.h")
    for c_name, mirror in (("A_egg_bonus_table", A_EGG_BONUS_TABLE),
                           ("BONUS_RECORD", BONUS_RECORD),
                           ("EGG_STATE_THROWN", EGG_STATE_THROWN)):
        assert collide_h[c_name] == mirror, f"{c_name} differs from this file's mirror"


def test_mirrored_constants_match_the_shared_headers():
    """The rest of what this file restates belongs to a header collide.h only includes: the
    gladiator bookkeeping the wave director shares with it, the flags-word bits the render pass
    reads back, and the pterodactyl table and record the wave director and the pterodactyl driver
    walk too."""
    addrs_h = _defines("include/addrs.h")
    joust_h = _defines("include/joust.h")
    object_h = _defines("include/object.h")
    for defines, origin, mirrored in (
            (addrs_h, "addrs.h", {"A_gladiator_wave_countdown": A_GLADIATOR_WAVE_COUNTDOWN,
                                  "A_player_conflict_flag": A_PLAYER_CONFLICT_FLAG,
                                  "A_first_dismount_owner": A_FIRST_DISMOUNT_OWNER}),
            (joust_h, "joust.h",
             {"OBJ_FLAG_PLATFORM_BUMP": OBJ_FLAG_PLATFORM_BUMP,
              "OBJ_FLAG_TYPE_LO": OBJ_FLAG_TYPE_LO,
              "OBJ_FLAG_TYPE_HI": OBJ_FLAG_TYPE_HI}),
            (object_h, "object.h", {"A_pterodactyl_table": A_PTERODACTYL_TABLE,
                                    "A_pterodactyl_table_END": A_PTERODACTYL_TABLE_END,
                                    "PT_RECORD": PT_RECORD,
                                    "PT_FLAG_JUST_SPAWNED": PT_FLAG_JUST_SPAWNED,
                                    "PT_FLAG_DYING": PT_FLAG_DYING,
                                    **_PT_OFFSETS})):
        for c_name, mirror in mirrored.items():
            assert defines[c_name] == mirror, f"{c_name}: {origin} differs from this file's mirror"


def test_mirrored_constants_match_collide_c():
    collide_c = _defines("src/collide.c")
    for c_name, mirror in (("SND_PLATFORM_BUMP", SND_PLATFORM_BUMP),
                           ("SND_JOUST_TIE", SND_JOUST_TIE),
                           ("SND_RIDER_UNSEATED", SND_RIDER_UNSEATED),
                           ("SND_EGG_COLLECTED", SND_EGG_COLLECTED),
                           ("SND_PTERO_LANCED", SND_PTERO_LANCED),
                           ("EGG_HATCH_FRAMES", EGG_HATCH_FRAMES),
                           ("MSG_BONUS_FRAMES", MSG_BONUS_FRAMES),
                           ("MSG_BONUS_COLOR", MSG_BONUS_COLOR),
                           ("STR_BONUS_500", STR_BONUS_500)):
        assert collide_c[c_name] == mirror, f"{c_name} differs from this file's mirror"
