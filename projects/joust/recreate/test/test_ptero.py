"""Differential tests for Joust's pterodactyl driver (src/ptero.c): update_pterodactyl @ 0x14ada.

One entry, 1470 bytes, no arguments and no result — everything it reads and writes is memory, so the
oracle is entered at 0x14ada directly and the glue is a bare forwarder. Every path ends in the single
`rts` at 0x14b2e, so nothing here needs a `stop_pc` checkpoint, and every routine it calls
(play_sound, rng_advance, test_overlap, ptero_avoid_platform, ptero_spot_player, blit_mask_wide,
blit_sprite_planes) is already verified.

`poison=True` is OFF everywhere but the two batteries that name it, and the reason is MEASURED
rather than assumed: nearly every byte this routine writes is a byte it branches on — the flags word,
the two clip counters, the two byte timers, x, y, spawn_timer — so the attribution pass's inverted
image is a DIFFERENT case, not a check of the case it was asked about. Inverting a clip counter of 0
to 0xff, for instance, sends the re-run down the "still fading in" path instead of the hunt.
`test_poison_would_test_a_different_function` pins exactly that, so the absence stays a measurement.
Where it IS used the poisoned bytes steer nothing: the bounty popup's message record, and the
framebuffer the two blitters paint.

In poison's place every battery pre-fills what the routine must write with UNWRITTEN, so a write the
candidate skips shows up as a plain diff rather than as a coincidental match on a zeroed image.

Three of the cases below exist because a mutation sweep over the reconstruction found them missing;
each says so at the case itself.
"""
import ctypes
import functools
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin section at the end

# ---- entry point (Ghidra address; ../../names.txt) ----
ENTRY_UPDATE_PTERODACTYL = 0x14ada

# ---- globals (mirrors of include/ptero.h, object.h, draw.h, addrs.h, objects.h, wave.h, sound.h) --
A_PLATFORM_PRESENT = 0x10cfa
A_PTERO_WAVE_COUNTDOWN = 0x10d04
A_GAME_PHASE = 0x10d08
A_ACTIVE_PLAYERS = 0x10d09
A_PTERO_SPAWN_COUNT = 0x10d0d
A_DRAW_CLIP_CELL0 = 0x10d0e
A_SND_PRIORITY = 0x10d4c
A_HIT_BOX_A = 0x10da0
A_HIT_BOX_B = 0x10db0
A_HIT_ROWS = 0x10dc0
A_COLLISION_HIT = 0x10dc1
A_SCREEN_BASE = 0x10dde
A_DRAW_DST = 0x10de8
A_DRAW_SRC = 0x10df0
A_DRAW_SHIFT = 0x10df4
A_DRAW_ROWS = 0x10df6
A_DRAW_DST_OFF = 0x10df8
A_SPAWN_INTERVAL = 0x10dfa
A_SPAWN_TIMER = 0x10dfc
A_RNG_PTR = 0x10dfe
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36
A_PLAYER2 = 0x10f84
A_PTERODACTYL_TABLE = 0x113ba
A_PTERODACTYL_TABLE_END = 0x1143a
A_PLATFORM_SPRITES = 0x119d4
A_PTERO_FRAME_TABLE = 0x151d6
A_PTERO_BUMP_TABLE = 0x151f6
A_PTERO_AVOID_PLATFORM = 0x15226   # the next function up: the bump table's exclusive bound
STR_PTERO_BOUNTY = 0x152be

# ---- record geometry ----
PT_RECORD = 0x20
N_PTEROS = (A_PTERODACTYL_TABLE_END - A_PTERODACTYL_TABLE) // PT_RECORD
PT_FLAGS, PT_DST, PT_SRC, PT_SHIFT_W = 0x00, 0x02, 0x06, 0x0a
PT_X, PT_Y, PT_VX, PT_VY, PT_SPARE = 0x0c, 0x0e, 0x10, 0x12, 0x14
PT_DST_OFF, PT_ROWS_W, PT_ANIM = 0x16, 0x18, 0x1a
PT_SHIFT, PT_ROWS = 0x0b, 0x19   # the LOW BYTES of the shift and rows words, one off each
PT_CLIP_WRAPPED, PT_CLIP_ONSCREEN, PT_SWOOP_TIMER, PT_DWELL_TIMER = 0x1c, 0x1d, 0x1e, 0x1f

PT_FLAG_JUST_SPAWNED, PT_FLAG_MOVING_DOWN, PT_FLAG_MOVING_RIGHT = 1 << 0, 1 << 1, 1 << 2
PT_FLAG_LEAVING, PT_FLAG_DYING, PT_FLAG_IN_PLAY = 1 << 3, 1 << 5, 1 << 6

PSPR_RECORD, N_PLATFORMS = 0x10, 8
PSPR_PRESENT, PSPR_ROWS, PSPR_COLS, PSPR_SRC, PSPR_DST_OFF = 0x0, 0x4, 0x6, 0x8, 0xc
BUMP_RECORD, BUMP_X_LEFT, BUMP_X_RIGHT, BUMP_Y = 6, 0, 2, 4
FRAME_RECORD, FRAME_SRC, FRAME_DST_OFF, FRAME_ROWS = 8, 0, 4, 6
MSG_RECORD, N_MESSAGES = 0xc, 24
MSG_KIND, MSG_TIMER, MSG_COLOR, MSG_SHIFT, MSG_SCREEN_PTR, MSG_STRING = 0, 1, 2, 3, 4, 8
OBJ_Y = 0x04

SCREEN_ROW_BYTES, CELL_BYTES, CELL_PIXELS = 0xa0, 8, 16
PLAYFIELD_WIDTH = SCREEN_ROW_BYTES // CELL_BYTES * CELL_PIXELS   # 320

# ---- the values src/ptero.c names ----
SPAWN_TIMER_MARGIN = 0x20
PTERO_Y_MAX = 0x96
PTERO_ENTRY_SPEED, PTERO_ENTRY_FADE = 2, 0xb
PTERO_SPRITE_LEFTWARD, PTERO_SPRITE_RIGHTWARD, PTERO_FACING_STRIDE = 0x231aa, 0x2332a, 0x180
PTERO_ENTRY_DST_LEFTWARD, PTERO_ENTRY_DST_RIGHTWARD = 0x5dc0, 0x5e40
PTERO_ENTRY_X_RIGHTWARD = 0x120
PTERO_BOUNCE_SPEED, PLATFORM_PRESENT_SET = 4, 1
PTERO_DEATH_POSE_FRAMES, PTERO_DEATH_CLIP = 4, 4
PTERO_BOUNTY_KIND, PTERO_BOUNTY_COLOR, PTERO_BOUNTY_FRAMES = 1, 8, 0x3c
PTERO_BOUNTY_Y_BIAS, PTERO_BOUNTY_X_BIAS = 2, 8
PTERO_CROWD_X, PTERO_CROWD_Y, PTERO_CROWD_STEP = 0x1e, 0xc, 2
PTERO_LEAVE_SPEED, PTERO_EXIT_COLUMN_SIZE, PTERO_EXIT_COLUMN_LAST = 6, 6, 0x2f
PTERO_EXIT_FADE, PTERO_EXIT_RELEASE, PTERO_EXIT_HOLD = 7, 2, 3
PTERO_CRUISE_SPEED, PTERO_DIVE_SPEED, PTERO_CLIMB_STEP, PTERO_DWELL_FRAMES = 3, 6, 1, 3
PT_ANIM_STEP, PT_ANIM_FRAME_MASK, PT_ANIM_POSE2, PT_ANIM_POSE3 = 3, 0x18, 0x10, 0x18
PTERO_WRAP_ONE_CELL, PTERO_WRAP_TWO_CELLS = 0x120, 0x130
PTERO_BOX_COLS = 3
SND_PTERO_CRY = 3
SND_PRIORITY_IDLE = 0x10          # src/sound.c's "nothing playing"
PTERO_SWOOP_TIMER_SET = 0x14      # src/object.c — what ptero_spot_player arms

# ---- scratch areas, clear of the program (ends 0x2b7ae), of abi's stub space (0x40000..0x40207),
# of the staged-file table (0xbf000) and of the stack guard. ----
SCREEN = 0x70000
SCREEN_ALT = 0x80000        # a second framebuffer, so screen_base is read rather than assumed
SCREEN_BYTES = 0x8000
SPRITE_BIRD = 0x50000       # the bird's own collision-box source, solid pixels...
SPRITE_PLATFORM = 0x5a000   # ...and a platform's
SPRITE_BLANK = 0x64000      # never poked, so it reads back as no pixels at all: a bird given this
                            # source is swept against the platforms and never overlaps one
SPRITE_BYTES = 0x4000

UNWRITTEN = 0x5a            # pre-filled into everything the routine must write
RNG_START = 0x11000         # a quiet, word-aligned cursor well inside rng_advance's range

_U8P = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_update_pterodactyl.argtypes = [_U8P]
harness._lib.g_update_pterodactyl.restype = None


# ================================================================================================
# Staging helpers.
# ================================================================================================

def _ptero(**fields):
    """One 0x20-byte pterodactyl record. Every field not named is left at UNWRITTEN, so a write the
    candidate skips shows as a diff rather than matching a zeroed record by accident — except
    PT_FLAGS, whose zero/non-zero decides whether the slot exists at all."""
    record = bytearray([UNWRITTEN] * PT_RECORD)
    struct.pack_into(">H", record, PT_FLAGS, fields.get("flags", PT_FLAG_IN_PLAY))
    struct.pack_into(">I", record, PT_DST, fields.get("dst", 0))
    struct.pack_into(">I", record, PT_SRC, fields.get("src", SPRITE_BIRD))
    for off, name, default in ((PT_SHIFT_W, "shift", 0), (PT_X, "x", 0x80), (PT_Y, "y", 0x40),
                               (PT_VX, "vx", 1), (PT_VY, "vy", 1), (PT_SPARE, "spare", UNWRITTEN),
                               (PT_DST_OFF, "dst_off", 0), (PT_ROWS_W, "rows", 0),
                               (PT_ANIM, "anim", 0)):
        struct.pack_into(">H", record, off, fields.get(name, default) & 0xffff)
    for off, name in ((PT_CLIP_WRAPPED, "clip_wrapped"), (PT_CLIP_ONSCREEN, "clip_onscreen"),
                      (PT_SWOOP_TIMER, "swoop"), (PT_DWELL_TIMER, "dwell")):
        record[off] = fields.get(name, 0) & 0xff
    return bytes(record)


def _table(*records):
    """The whole four-slot table; the slots not given are free (a zero flags word)."""
    table = bytearray()
    for slot in range(N_PTEROS):
        table += records[slot] if slot < len(records) and records[slot] is not None \
            else bytes(PT_RECORD)
    return bytes(table)


def _message_table(first_free=0):
    """The 24 message slots, with the ones BELOW `first_free` TAKEN — so the bounty popup lands in
    slot `first_free`, and first_free == N_MESSAGES is a full table. Only MSG_KIND decides that, so
    the other eleven bytes of every record carry UNWRITTEN.

    NOTE THE POLARITY, which is the opposite of test_wave.py's same-named helper (`free` counts
    leading EMPTY slots there): a case copied between the two modules without changing the keyword
    stages the other half of the table and goes green having tested nothing.
    """
    table = bytearray()
    for slot in range(N_MESSAGES):
        record = bytearray([UNWRITTEN] * MSG_RECORD)
        record[MSG_KIND] = 0xf0 + slot % 8 if slot < first_free else 0
        table += record
    return bytes(table)


def _platform_sprites(records):
    """platform_sprites, as [(present_index, rows, cols, src, dst_off), ...] padded out to eight."""
    table = bytearray()
    for slot in range(N_PLATFORMS):
        present, rows, cols, src, dst_off = records[slot] if slot < len(records) \
            else (slot, 1, 1, SPRITE_PLATFORM, 0)
        table += struct.pack(">IHHII", A_PLATFORM_PRESENT + present, rows, cols, src, dst_off)
    return bytes(table)


def _bump_table(records):
    """ptero_bump_table, as [(x_left, x_right, y), ...] padded out to eight."""
    table = bytearray()
    for slot in range(N_PLATFORMS):
        table += struct.pack(">HHH", *(records[slot] if slot < len(records) else (0, 0, 0)))
    return bytes(table)


def _base_pokes(phase=0, players=3, timer=0x400, interval=0x200, screen_base=SCREEN,
                over=None):
    """A fully controlled starting state: nothing present on the playfield, no messages posted, no
    bird in the air and a spawn timer far enough out that no free slot arms itself."""
    pokes = {
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_PTERODACTYL_TABLE: _table(),
        A_PLATFORM_PRESENT: bytes(N_PLATFORMS),          # no platform exists this wave
        A_GAME_PHASE: bytes([phase]),
        A_ACTIVE_PLAYERS: bytes([players]),
        A_PTERO_WAVE_COUNTDOWN: bytes([0]),
        A_PTERO_SPAWN_COUNT: bytes([0]),
        A_SPAWN_INTERVAL: struct.pack(">HH", interval, timer & 0xffff),
        A_SND_PRIORITY: struct.pack(">H", SND_PRIORITY_IDLE),
        A_RNG_PTR: struct.pack(">I", RNG_START),
        A_MESSAGE_TABLE: _message_table(),
        A_HIT_BOX_A: bytes([UNWRITTEN] * 0x20),          # both boxes, back to back
        screen_base: bytes(SCREEN_BYTES),
        SPRITE_BIRD: b"\xff" * SPRITE_BYTES,
        SPRITE_PLATFORM: b"\xff" * SPRITE_BYTES,
    }
    pokes.update(over or {})
    return pokes


def _case(pokes, poison=False, max_insns=400_000, note=""):
    diffs, info = differential(ENTRY_UPDATE_PTERODACTYL, {"_pokes": pokes},
                               lambda lib, buf: lib.g_update_pterodactyl(buf),
                               poison=poison, max_insns=max_insns)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def _writes(info):
    """The oracle's write set with its own machine stack dropped — the `jsr`s this routine makes
    push return addresses the C reconstruction has no analogue for."""
    return {addr: value for addr, value in info["writes"].items() if addr < emu.STACK_GUARD_LO}


def _word(written, addr, default=None):
    if addr not in written and default is not None:
        return default
    return (written[addr] << 8) | written[addr + 1]


def _long(written, addr):
    return int.from_bytes(bytes(written[addr + n] for n in range(4)), "big")


def _slot(index=0):
    return A_PTERODACTYL_TABLE + index * PT_RECORD


# ================================================================================================
# Phase A — the scheduler: what arms a free slot, and what the arming costs.
# ================================================================================================

def test_the_frame_timer_is_taken_down_once_not_once_per_slot():
    """`subq.w #1` sits ABOVE the loop, so four free slots cost one tick, not four."""
    info = _case(_base_pokes(timer=0x400), note="all four slots free")
    written = _writes(info)
    assert _word(written, A_SPAWN_TIMER) == 0x3ff
    assert set(written) == {A_SPAWN_TIMER, A_SPAWN_TIMER + 1}, \
        "an idle table writes nothing else at all"


@pytest.mark.parametrize("timer,arms", ((3, False), (2, False), (1, True), (0, True),
                                        (0x7fff, False), (0x8000, False), (0xffff, True)))
def test_a_free_slot_arms_only_once_the_timer_has_run_out(timer, arms):
    """The tick happens first and the test is `tst.w` + `bgt`, i.e. SIGNED on the DECREMENTED word:
    a timer of 1 lands on 0 and fires, and 0 wraps to -1 and fires. 0x8000 is the trap — it
    decrements to 0x7fff, which is hugely positive, so the most negative timer there is holds the
    schedule off longest."""
    info = _case(_base_pokes(timer=timer), note=f"timer={timer:#x}")
    written = _writes(info)
    assert (_slot(0) + PT_FLAGS in written) == arms
    if arms:
        assert _word(written, _slot(0) + PT_FLAGS) == PT_FLAG_JUST_SPAWNED


@pytest.mark.parametrize("phase,players,arms", ((0, 3, True), (0, 1, True), (0, 2, True),
                                                (0, 0, False), (1, 3, False), (0xff, 3, False)))
def test_arming_needs_a_wave_in_progress_and_somebody_to_hunt(phase, players, arms):
    info = _case(_base_pokes(phase=phase, players=players, timer=1),
                 note=f"phase={phase} players={players}")
    assert (_slot(0) + PT_FLAGS in _writes(info)) == arms


@pytest.mark.parametrize("interval", (0, 1, 2, 3, 0x40, 0x7fff, 0x8000, 0xffbe))
def test_the_interval_halves_and_reloads_the_timer(interval):
    """`lsr.w` on memory shifts by exactly ONE bit and is LOGICAL, so 0x8000 halves to 0x4000
    rather than staying negative. The reload is that half plus SPAWN_TIMER_MARGIN, in a word."""
    info = _case(_base_pokes(interval=interval, timer=0), note=f"interval={interval:#x}")
    written = _writes(info)
    assert _word(written, A_SPAWN_INTERVAL) == interval >> 1
    assert _word(written, A_SPAWN_TIMER) == ((interval >> 1) + SPAWN_TIMER_MARGIN) & 0xffff


def test_only_one_slot_arms_per_frame_because_the_reload_holds_the_rest_off():
    """The reload is written before the next free slot is looked at, and it is positive, so the
    other three see a timer that has not run out."""
    info = _case(_base_pokes(interval=0x200, timer=0))
    written = _writes(info)
    assert _word(written, _slot(0) + PT_FLAGS) == PT_FLAG_JUST_SPAWNED
    for index in range(1, N_PTEROS):
        assert _slot(index) + PT_FLAGS not in written, f"slot {index} armed too"


def test_a_reload_that_wraps_negative_arms_a_second_slot_in_the_same_frame():
    """0xffff halves to 0x7fff and the margin pushes the reload to 0x801f, which the SIGNED `bgt`
    reads as deeply negative — so slot 1's test fires as well. Its own reload, 0x3fff + the margin,
    is positive again, which is what stops the cascade at two. The game never reaches an interval
    like that; the differential can, and the shape is the original's."""
    info = _case(_base_pokes(interval=0xffff, timer=0))
    written = _writes(info)
    assert _word(written, _slot(0) + PT_FLAGS) == PT_FLAG_JUST_SPAWNED
    assert _word(written, _slot(1) + PT_FLAGS) == PT_FLAG_JUST_SPAWNED
    for index in (2, 3):
        assert _slot(index) + PT_FLAGS not in written, f"slot {index} armed too"
    assert _word(written, A_SPAWN_INTERVAL) == 0x3fff, "halved once per slot that armed"


def test_an_occupied_slot_is_never_offered_to_the_scheduler():
    """The flags word being non-zero is the whole test — even a word with no meaningful bit set."""
    pokes = _base_pokes(timer=0, phase=1)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=0x0400))
    info = _case(pokes, note="an occupied slot with an otherwise empty flags word")
    assert _word(_writes(info), _slot(0) + PT_FLAGS) == 0x0400 | PT_FLAG_LEAVING, \
        "driven (game_phase 1 sends it away) and stored back, not armed"


# ================================================================================================
# Phase B — building an armed slot.
# ================================================================================================

def _rng_bit_pokes(bit):
    """rng_ptr aimed so that the byte rng_advance leaves it on has bit 0 equal to `bit`."""
    return {A_RNG_PTR: struct.pack(">I", RNG_START), RNG_START + 2: bytes([0xa0 | bit])}


@pytest.mark.parametrize("bit", (0, 1))
def test_an_armed_slot_is_built_from_the_random_bit(bit):
    """Bit 0 of the byte the ADVANCED cursor points at picks the entry edge, and with it the sprite
    set, the entry x, the first erase address and which clip counter fades the bird in."""
    # phase 0 with an empty board, so the new bird goes on to the HUNT driver — which leaves the
    # build's clip counters and entry x alone, where the leaving driver would rewrite both.
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
    pokes.update(_rng_bit_pokes(bit))
    info = _case(pokes, note=f"rng bit={bit}")
    written = _writes(info)

    rightward = bit == 1
    assert written[_slot(0) + PT_DWELL_TIMER] == 0
    assert written[_slot(0) + PT_SWOOP_TIMER] == 0
    assert _word(written, _slot(0) + PT_SPARE) == 0
    assert _word(written, _slot(0) + PT_VY) == 0
    assert _word(written, _slot(0) + PT_ANIM) == PT_ANIM_STEP, "the pose advances the same frame"
    # The pose lands on 0, so the draw reads frame 0 — whose source IS the leftward sprite set —
    # and a rightward bird takes it PTERO_FACING_STRIDE further on.
    assert _long(written, _slot(0) + PT_SRC) == \
        PTERO_SPRITE_LEFTWARD + (PTERO_FACING_STRIDE if rightward else 0)
    # The clip counter belonging to the edge the bird is entering by is armed, and the draw pass
    # then takes one off it; the other stays clear.
    assert written[_slot(0) + PT_CLIP_ONSCREEN] == (PTERO_ENTRY_FADE - 1 if rightward else 0)
    assert written[_slot(0) + PT_CLIP_WRAPPED] == (0 if rightward else PTERO_ENTRY_FADE - 1)
    assert _word(written, _slot(0) + PT_FLAGS) == \
        (PT_FLAG_IN_PLAY | PT_FLAG_MOVING_RIGHT if rightward else PT_FLAG_IN_PLAY)

    # x has already moved by the hunt's cruise speed when the record is written back, and y has not
    # moved at all: a leftward bird's very first step wraps it round to the right edge.
    assert _word(written, _slot(0) + PT_X) == \
        (PTERO_ENTRY_X_RIGHTWARD + PTERO_CRUISE_SPEED if rightward else PLAYFIELD_WIDTH - 1)
    assert _word(written, _slot(0) + PT_Y) == PTERO_Y_MAX


@pytest.mark.parametrize("bit", (0, 1))
def test_the_first_erase_pass_of_a_new_bird_draws_nothing(bit):
    """PT_ROWS_W is cleared before the entry address is stored, and blit_mask_wide refuses a row
    count of 0 — so PTERO_ENTRY_DST_* are stores, not geometry. Proved by moving screen_base: a
    frame that really erased at those addresses would paint two different framebuffers."""
    written = {}
    for screen_base in (SCREEN, SCREEN_ALT):
        pokes = _base_pokes(phase=0, players=0, screen_base=screen_base)
        pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
        pokes.update(_rng_bit_pokes(bit))
        info = _case(pokes, note=f"rng bit={bit} screen_base={screen_base:#x}")
        entry_dst = PTERO_ENTRY_DST_RIGHTWARD if bit else PTERO_ENTRY_DST_LEFTWARD
        touched = [a for a in _writes(info)
                   if screen_base + entry_dst <= a < screen_base + entry_dst + CELL_BYTES]
        assert not touched, "the entry address was blitted at"
        written[screen_base] = _writes(info)
    # ...and what it DID draw moved with screen_base, so the frame really was painted.
    assert any(a >= SCREEN for a in written[SCREEN])
    assert any(a >= SCREEN_ALT for a in written[SCREEN_ALT])


@pytest.mark.parametrize("count", (0, 1, 0x7f, 0x80, 0xfe, 0xff))
def test_the_spawn_count_wraps_in_a_byte(count):
    """`addq.b #1` — 0xff becomes 0, which count_objects_and_pad reads back as a fresh frame."""
    pokes = _base_pokes(phase=1, over={A_PTERO_SPAWN_COUNT: bytes([count])})
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
    info = _case(pokes, note=f"count={count:#x}")
    assert _writes(info)[A_PTERO_SPAWN_COUNT] == (count + 1) & 0xff


@pytest.mark.parametrize("priority,plays", ((SND_PRIORITY_IDLE, True), (SND_PTERO_CRY, True),
                                            (SND_PTERO_CRY - 1, False), (0x8000, False),
                                            (0x7fff, True), (0xffff, False)))
def test_the_arrival_cry_goes_through_play_sounds_signed_gate(priority, plays):
    """play_sound compares `cmp.w` + `bgt`, so 0x8000 outranks everything and 0x7fff outranks
    nothing. The Dosound ledger is what pins this: the call itself writes no memory."""
    pokes = _base_pokes(phase=1, over={A_SND_PRIORITY: struct.pack(">H", priority)})
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
    info = _case(pokes, note=f"priority={priority:#x}")
    assert (A_SND_PRIORITY in _writes(info)) == plays


@pytest.mark.parametrize("cursor", (0x10000, 0x11000, 0x17830, 0x1782e))
def test_the_random_cursor_is_advanced_before_its_bit_is_sampled(cursor):
    """`jsr rng_advance` then `btst #0,(a1)+` reads through the STEPPED pointer, including across
    the wrap at RNG_PTR_LIMIT — where the byte sampled is the one at the restart point, not the one
    two past the old cursor."""
    pokes = _base_pokes(phase=1, over={A_RNG_PTR: struct.pack(">I", cursor)})
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
    _case(pokes, note=f"cursor={cursor:#x}")


def test_the_random_nudge_is_the_flags_word_the_build_has_just_made():
    """rng_advance is handed D0, which at that point holds PT_FLAG_IN_PLAY and nothing else — so a
    wrap restarts the cursor at IMAGE_LOAD_BASE + (0x40 & 0xfe). Staged at the limit so the wrap
    actually happens and the restart address is in the write set."""
    pokes = _base_pokes(phase=1, over={A_RNG_PTR: struct.pack(">I", 0x17830)})
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=PT_FLAG_JUST_SPAWNED))
    info = _case(pokes)
    assert _long(_writes(info), A_RNG_PTR) == 0x10000 + (PT_FLAG_IN_PLAY & 0xfe)


def test_an_armed_bit_on_a_live_bird_still_rebuilds_it():
    """The build is gated on bit 0 alone, not on the slot being fresh — so the wave director raising
    that bit on a bird already in the air throws the bird's whole state away."""
    pokes = _base_pokes(phase=1)
    pokes[A_PTERODACTYL_TABLE] = _table(
        _ptero(flags=PT_FLAG_JUST_SPAWNED | PT_FLAG_LEAVING | PT_FLAG_DYING, x=0x50, y=0x20,
               anim=0x1234, swoop=9, dwell=9))
    pokes.update(_rng_bit_pokes(0))
    info = _case(pokes)
    written = _writes(info)
    assert _word(written, _slot(0) + PT_FLAGS) == PT_FLAG_IN_PLAY | PT_FLAG_LEAVING, \
        "every bit but the one this frame's driver sets is thrown away"
    assert written[_slot(0) + PT_SWOOP_TIMER] == 0


# ================================================================================================
# Phase C — the platform sweep.
#
# A platform whose bitmap the bird's sprite overlaps turns it away. Every case here is staged
# through _hit_pokes, which lays one solid platform bitmap and one solid bird sprite on the same
# screen column so that test_overlap always reports a hit — and asserts that it did, so a staging
# slip fails loudly instead of quietly testing the no-hit path.
# ================================================================================================

PLAT_ROW = 0x10                      # the scanline the staged platform's bitmap starts on
PLAT_ROWS, PLAT_COLS = 8, 4
BIRD_ROWS = 8

# Bump records that force one arm each. The x bounds are read as SIGNED words against the bird's x,
# so a bound at the far end of either half of the word range can never fire.
BUMP_NEVER_LEFT, BUMP_NEVER_RIGHT = 0x8000, 0x7fff


def _platform_sprites_spec():
    """The eight platform records _hit_pokes stages: all identical, all overlapping the bird."""
    return [(index, PLAT_ROWS, PLAT_COLS, SPRITE_PLATFORM, PLAT_ROW * SCREEN_ROW_BYTES)
            for index in range(N_PLATFORMS)]


def _hit_pokes(x=0x80, y=0x40, vx=1, vy=1, down=False, facing=0, extra_flags=0,
               bumps=((BUMP_NEVER_LEFT, BUMP_NEVER_RIGHT, 0),), present=(1,), **fields):
    """A bird whose sprite is guaranteed to overlap platform 0's bitmap. Any further record field
    is passed straight through to _ptero.

    The two boxes have to be ordered so that test_overlap's band test survives. It measures the
    UPPER box — the one at the smaller screen address — downward and requires
    upper_y + upper_rows > lower_y, so a bird whose y is at or below the platform's own scanline
    has to be the UPPER box (its band then reaches down to the platform's), and a bird above it —
    or at a negative y, where the band reaches nothing — has to be the lower one. Which orientation
    applies follows from y alone, so callers never choose it.
    """
    pokes = _base_pokes(phase=0, players=0)
    bird_upper = ((y ^ 0x8000) - 0x8000) >= 0x18       # y as a signed word
    bird_dst = (PLAT_ROW + (-1 if bird_upper else 1)) * SCREEN_ROW_BYTES
    flags = PT_FLAG_IN_PLAY | facing | extra_flags | (PT_FLAG_MOVING_DOWN if down else 0)
    pokes[A_PTERODACTYL_TABLE] = _table(
        _ptero(flags=flags, x=x, y=y, vx=vx, vy=vy, dst=bird_dst, rows=BIRD_ROWS, dst_off=0,
               **fields))
    pokes[A_PLATFORM_SPRITES] = _platform_sprites(_platform_sprites_spec())
    pokes[A_PLATFORM_PRESENT] = bytes(list(present) + [0] * (N_PLATFORMS - len(present)))
    pokes[A_PTERO_BUMP_TABLE] = _bump_table(bumps)
    return pokes


def _bounced(pokes, note=""):
    """(vx, vy, flags, written) as the frame left them, having checked the sweep really hit."""
    written = _writes(_case(pokes, note=note))
    assert written.get(A_COLLISION_HIT), f"the sweep never found the platform: {note}"
    return (_word(written, _slot(0) + PT_VX, default=-1),
            _word(written, _slot(0) + PT_VY, default=-1),
            _word(written, _slot(0) + PT_FLAGS), written)


@pytest.mark.parametrize("left,turned_left", ((0x7f, False), (0x80, True), (0x81, True),
                                              (0xffff, False), (BUMP_NEVER_LEFT, False)))
def test_the_left_bump_bound_is_a_signed_at_or_past_test(left, turned_left):
    """`cmp.w x,bound ; blt` falls through — and turns the bird LEFT — when the bound is at or right
    of the bird's x. SIGNED, so a bound of 0xffff reads as -1 and never fires against x 0x80.

    With the right bound out of reach, failing this test drops through to the vertical arm, which is
    the only one that writes PT_VY — so the two arms are told apart by that field as well.
    """
    vx, vy, flags, _ = _bounced(_hit_pokes(x=0x80, bumps=((left, BUMP_NEVER_RIGHT, 0),)),
                                note=f"left={left:#x}")
    assert (flags & PT_FLAG_MOVING_RIGHT) == 0
    assert (vy == PTERO_BOUNCE_SPEED) != turned_left
    if turned_left:
        assert vx == PTERO_BOUNCE_SPEED


@pytest.mark.parametrize("right,turned_right", ((0x81, False), (0x80, True), (0x7f, True),
                                                (BUMP_NEVER_LEFT, True), (0xffff, True)))
def test_the_right_bump_bound_is_a_signed_at_or_past_test(right, turned_right):
    """The mirror: `cmp.w x,bound ; bgt` falls through when the bound is at or LEFT of the bird.
    SIGNED again, so 0x8000 and 0xffff both read as far left of x 0x80 and both fire."""
    vx, vy, flags, _ = _bounced(_hit_pokes(x=0x80, bumps=((BUMP_NEVER_LEFT, right, 0),)),
                                note=f"right={right:#x}")
    assert bool(flags & PT_FLAG_MOVING_RIGHT) == turned_right
    assert (vy == PTERO_BOUNCE_SPEED) != turned_right
    if turned_right:
        assert vx == PTERO_BOUNCE_SPEED


@pytest.mark.parametrize("bump_y,down", ((0x3f, True), (0x40, True), (0x41, False),
                                         (BUMP_NEVER_LEFT, True), (0xffff, True),
                                         (BUMP_NEVER_RIGHT, False)))
def test_between_the_two_bounds_the_platform_sends_the_bird_over_or_under(bump_y, down):
    """The third word is a SIGNED compare against the bird's y: a bird at or BELOW it on screen
    (bird y >= the bound — screen y grows downward) is sent DOWN, one above it UP. This arm is also
    the only one that touches PT_VY."""
    _, vy, flags, _ = _bounced(_hit_pokes(x=0x80, y=0x40,
                                          bumps=((BUMP_NEVER_LEFT, BUMP_NEVER_RIGHT, bump_y),)),
                               note=f"bump_y={bump_y:#x}")
    assert vy == PTERO_BOUNCE_SPEED
    assert bool(flags & PT_FLAG_MOVING_DOWN) == down


@pytest.mark.parametrize("facing", (0, PT_FLAG_MOVING_RIGHT))
def test_the_vertical_arm_leaves_the_horizontal_direction_and_speed_alone(facing):
    """It writes PT_VY and bit 1 only — a bird sent over a platform keeps flying the way it was, at
    the speed it was. (Which is what makes it the vehicle for the x-movement battery below.)"""
    _, _, flags, written = _bounced(_hit_pokes(x=0x80, vx=1, facing=facing),
                                    note=f"facing={facing}")
    assert (flags & PT_FLAG_MOVING_RIGHT) == facing
    assert _slot(0) + PT_VX not in written, "PT_VX is not even written by the vertical arm"


@pytest.mark.parametrize("down", (False, True))
def test_the_horizontal_arms_leave_the_vertical_direction_and_speed_alone(down):
    """The mirror, and the vehicle for the y-movement battery: neither x arm touches PT_VY or bit 1."""
    _, _, flags, written = _bounced(_hit_pokes(x=0x80, vy=1, down=down,
                                               bumps=((0x80, BUMP_NEVER_RIGHT, 0),)),
                                    note=f"down={down}")
    assert bool(flags & PT_FLAG_MOVING_DOWN) == down
    assert _slot(0) + PT_VY not in written, "PT_VY is not even written by either horizontal arm"


def test_the_first_present_platform_wins_and_the_rest_are_never_tested():
    """Platform 0 turns the bird LEFT and platform 1 would turn it RIGHT; the sweep stops at the
    first hit, so the answer is platform 0's."""
    _, _, flags, _ = _bounced(_hit_pokes(x=0x80, present=(1, 1),
                                         bumps=((0x80, BUMP_NEVER_RIGHT, 0),
                                                (BUMP_NEVER_LEFT, 0x7f, 0))))
    assert (flags & PT_FLAG_MOVING_RIGHT) == 0


def test_an_absent_platform_is_skipped_but_its_bump_record_is_still_stepped_over():
    """`addq.w #6,a5` runs on the miss path too, so platform 1's record is platform 1's whichever
    platforms before it exist. Platform 0 absent, platform 1 present and turning the bird RIGHT."""
    _, _, flags, _ = _bounced(_hit_pokes(x=0x80, present=(0, 1),
                                         bumps=((0x80, BUMP_NEVER_RIGHT, 0),
                                                (BUMP_NEVER_LEFT, 0x7f, 0))))
    assert flags & PT_FLAG_MOVING_RIGHT, "the second record was read for the second platform"


@pytest.mark.parametrize("present", (1, 2, 0x80, 0xff))
def test_a_hit_normalises_the_platforms_present_byte_to_one(present):
    """`move.b #$1,(a4)` — a store of the value already there in the shipped game, and a
    normalisation for anything else. Reproduced, not dropped."""
    _, _, _, written = _bounced(_hit_pokes(x=0x80, present=(present,),
                                           bumps=((0x80, BUMP_NEVER_RIGHT, 0),)),
                                note=f"present={present:#x}")
    assert written[A_PLATFORM_PRESENT] == PLATFORM_PRESENT_SET


def test_a_dying_bird_is_swept_against_the_platforms_before_it_is_allowed_to_die():
    """The sweep runs first, so a corpse that overlaps a platform is bounced and its death
    animation does not advance that frame — its two timers are left where they were."""
    vx, _, _, written = _bounced(_hit_pokes(x=0x80, extra_flags=PT_FLAG_DYING, swoop=1, dwell=1,
                                            bumps=((0x80, BUMP_NEVER_RIGHT, 0),)))
    assert _slot(0) + PT_SWOOP_TIMER not in written, "die() never ran"
    assert vx == PTERO_BOUNCE_SPEED


def test_the_birds_box_is_restaged_for_every_platform():
    """test_overlap advances HB_SRC and HB_CUR_COL in place on BOTH boxes, so a box staged once
    before the loop is somewhere else by the second platform.

    Both platforms are PRESENT — an absent one is skipped before test_overlap and so perturbs
    nothing, which is what makes it useless here. Platform 0's bitmap is BLANK, so its sweep runs
    the whole column walk (moving the bird's cursors) and finds no shared pixel; platform 1's is
    solid and must still report a hit. Hoisting the staging out of the loop leaves the bird's box
    wound forward and the second sweep misses.
    """
    pokes = _hit_pokes(x=0x80, present=(1, 1), bumps=((0, 0, 0), (0x80, BUMP_NEVER_RIGHT, 0)))
    sprites = list(_platform_sprites_spec())
    sprites[0] = (0, PLAT_ROWS, PLAT_COLS, SPRITE_BLANK, PLAT_ROW * SCREEN_ROW_BYTES)
    pokes[A_PLATFORM_SPRITES] = _platform_sprites(sprites)
    _, _, flags, written = _bounced(pokes)
    assert written[A_PLATFORM_PRESENT + 1] == PLATFORM_PRESENT_SET, "platform 1 is what hit"
    assert (flags & PT_FLAG_MOVING_RIGHT) == 0, "the second platform's sweep found the bird"


def test_no_platform_present_means_the_sweep_never_calls_test_overlap():
    """The bird's box is staged on every pass, so the sweep is not silent — but with every present
    byte at 0 the platform box is never filled in and collision_hit is never even cleared."""
    written = _writes(_case(_hit_pokes(x=0x80, present=(0,) * N_PLATFORMS)))
    assert A_COLLISION_HIT not in written, "test_overlap was called"
    assert A_HIT_BOX_A in written, "...but the bird's own box was still staged"


# ================================================================================================
# Phase D — keeping two birds apart.
#
# With no platform present and nobody on the board, PT_VY comes back 0 from ptero_avoid_platform, so
# the only thing that moves a bird's y in these cases is the separation itself.
# ================================================================================================

def _crowd_pokes(y0=0x40, y1=0x40, x0=0x80, x1=0x80, other_flags=PT_FLAG_IN_PLAY, slots=2):
    pokes = _base_pokes(phase=0, players=0)
    records = [_ptero(x=x0, y=y0, vx=0, vy=0)] + \
              [_ptero(flags=other_flags, x=x1, y=y1, vx=0, vy=0)] * (slots - 1)
    pokes[A_PTERODACTYL_TABLE] = _table(*records)
    return pokes


def _ys(info, staged, slots=2):
    """Each slot's y as the frame left it; a slot the frame never wrote keeps what it was staged
    with (a free slot is never driven at all)."""
    written = _writes(info)
    return [_word(written, _slot(index) + PT_Y, default=staged[index]) for index in range(slots)]


@pytest.mark.parametrize("x_gap,crowded", ((0x1e, True), (0x1f, False), (-0x1e, True),
                                           (-0x1f, False), (0, True)))
def test_the_crowding_x_band_is_inclusive_on_both_sides(x_gap, crowded):
    """`cmpi.w #$1e ; bgt` and `cmpi.w #$ffe2 ; blt` — a gap of exactly +/-0x1e still crowds."""
    info = _case(_crowd_pokes(x0=0x80 + x_gap, x1=0x80), note=f"x gap={x_gap}")
    assert (_ys(info, (0x40, 0x40))[0] != 0x40) == crowded


@pytest.mark.parametrize("y_gap,crowded", ((0xc, True), (0xd, False), (-0xc, True), (-0xd, False),
                                           (0, True)))
def test_the_crowding_y_band_is_inclusive_on_both_sides(y_gap, crowded):
    """`cmpi.w #$c ; bgt` on the way down and `cmpi.w #$fff4 ; blt` on the way up. The pair is
    pushed APART: whichever is lower goes lower still."""
    base = 0x40
    staged = ((base + y_gap) & 0xffff, base)
    y0, y1 = _ys(_case(_crowd_pokes(y0=staged[0], y1=base), note=f"y gap={y_gap}"), staged)
    assert (y1 != base) == crowded
    if crowded:
        step = PTERO_CROWD_STEP if y_gap >= 0 else -PTERO_CROWD_STEP
        assert y0 == (staged[0] + step) & 0xffff
        assert y1 == (base - step) & 0xffff


@pytest.mark.parametrize("y0,y1", ((0x8000, 0x7000), (0x7000, 0x8000)))
def test_which_bird_is_above_is_a_true_signed_compare_not_the_truncated_gap(y0, y1):
    """`sub.w` + `blt` branches on N != V, so it compares the two y values at full precision, while
    the band test right after it reads the TRUNCATED word. Straddling 0x8000 the subtraction
    overflows and the two disagree: 0x8000 against 0x7000 is far ABOVE by the branch and +0x1000 by
    the word, so the pair is nudged — where a reconstruction that read the sign of the truncated
    gap would take the other arm, find +0x1000 out of band, and leave both alone.

    Nothing the game itself produces reaches these values (y stays inside 0..PTERO_Y_MAX); this is
    the instruction's semantics, and the differential can reach it.
    """
    y0_out, y1_out = _ys(_case(_crowd_pokes(y0=y0, y1=y1), note=f"y0={y0:#x} y1={y1:#x}"),
                         (y0, y1))
    above = y0 == 0x8000
    assert y0_out == (y0 + (-PTERO_CROWD_STEP if above else PTERO_CROWD_STEP)) & 0xffff
    assert y1_out == (y1 + (PTERO_CROWD_STEP if above else -PTERO_CROWD_STEP)) & 0xffff


def test_an_overflowing_pair_is_still_banded_on_the_truncated_gap():
    """The other half of that disagreement: the ARM comes from the full-precision branch but the
    BAND from the truncated word. 0x8000 against 1 is above by the branch, and +0x7fff by the word
    — which the up arm's `< -0xc` test does NOT reject, so the pair is nudged after all."""
    staged = (0x8000, 1)
    assert _ys(_case(_crowd_pokes(y0=staged[0], y1=staged[1])), staged) == [0x7ffe, 3]


@pytest.mark.parametrize("other_flags,pushes", ((PT_FLAG_IN_PLAY, True), (0, False),
                                                (PT_FLAG_DYING, False),
                                                (PT_FLAG_IN_PLAY | PT_FLAG_DYING, False),
                                                (PT_FLAG_JUST_SPAWNED, True)))
def test_a_free_or_dying_slot_is_not_pushed(other_flags, pushes):
    """A zero flags word is a free slot and bit 5 is a corpse; anything else is in the way. Note
    that an ARMED slot counts — it is rebuilt later in the same pass, y and all."""
    info = _case(_crowd_pokes(other_flags=other_flags), note=f"other flags={other_flags:#x}")
    assert (_ys(info, (0x40, 0x40))[0] != 0x40) == pushes


def test_only_later_slots_are_pushed_so_a_pair_meets_once():
    """Each slot starts its scan one record on, so slot 1 never looks back at slot 0. Three birds
    stacked at the same y: slot 0 meets 1 and 2 (so it takes two steps down), slot 1 meets only 2
    (one step down, after the one step up slot 0 gave it), and slot 2 meets nobody (two steps up).
    A scan that looked backwards as well would give other numbers."""
    staged = (0x40,) * 3
    step = PTERO_CROWD_STEP
    assert _ys(_case(_crowd_pokes(slots=3)), staged, slots=3) == \
        [0x40 + 2 * step, 0x40, 0x40 - 2 * step]


# ================================================================================================
# Phase E — leaving.
# ================================================================================================

def _leave_pokes(phase=1, players=0, countdown=0, flags=PT_FLAG_IN_PLAY, x=0x80, **fields):
    pokes = _base_pokes(phase=phase, players=players)
    pokes[A_PTERO_WAVE_COUNTDOWN] = bytes([countdown])
    fields.setdefault("y", 0x40)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(flags=flags, x=x, **fields))
    return pokes


@pytest.mark.parametrize("phase,players,countdown,leaves", (
    (1, 3, 0, True),         # between waves
    (0, 3, 0, False),        # a wave in progress and players on the board: hunt
    (0, 0, 0, False),        # nobody to hunt, but no pterodactyl wave pending either
    (0, 0, 1, True),         # a pterodactyl wave IS pending and the board is empty
    (0, 3, 1, False),        # ...but not while a player is still there
    (0xff, 0, 0, True),
))
def test_what_sends_a_bird_off_the_screen(phase, players, countdown, leaves):
    """Three independent reasons, and the third is a PAIR: a pterodactyl wave still counting down
    plus an empty board. Told apart by PT_VX, which the two drivers set differently."""
    info = _case(_leave_pokes(phase=phase, players=players, countdown=countdown),
                 note=f"phase={phase} players={players} countdown={countdown}")
    assert _word(_writes(info), _slot(0) + PT_VX) == \
        (PTERO_LEAVE_SPEED if leaves else PTERO_CRUISE_SPEED)


def test_the_leaving_bit_is_one_way():
    """Once set, the bird keeps leaving even with the wave back in progress and players on it."""
    written = _writes(_case(_leave_pokes(phase=0, players=3,
                                         flags=PT_FLAG_IN_PLAY | PT_FLAG_LEAVING)))
    assert _word(written, _slot(0) + PT_VX) == PTERO_LEAVE_SPEED
    assert _word(written, _slot(0) + PT_FLAGS) & PT_FLAG_LEAVING


@pytest.mark.parametrize("x,arms", ((0x119, False), (0x11a, True), (0x11f, True), (0x120, False)))
def test_a_rightward_exit_arms_its_fade_in_the_last_column(x, arms):
    """`divu.w #$6` puts x 0x11a..0x11f in column PTERO_EXIT_COLUMN_LAST, and only there. The
    counter is armed BEFORE the frame's own fade takes one off it."""
    written = _writes(_case(_leave_pokes(flags=PT_FLAG_IN_PLAY | PT_FLAG_MOVING_RIGHT, x=x),
                            note=f"x={x:#x}"))
    assert written[_slot(0) + PT_CLIP_WRAPPED] == (PTERO_EXIT_FADE - 1 if arms else 0)


@pytest.mark.parametrize("x,arms", ((0, True), (5, True), (6, False), (0xffff, False)))
def test_a_leftward_exit_arms_its_fade_in_column_zero(x, arms):
    written = _writes(_case(_leave_pokes(x=x), note=f"x={x:#x}"))
    assert written[_slot(0) + PT_CLIP_ONSCREEN] == (PTERO_EXIT_FADE - 1 if arms else 0)


@pytest.mark.parametrize("counter,released", ((PTERO_EXIT_RELEASE, True), (1, False), (3, False),
                                              (0, False)))
def test_the_exit_fade_releases_the_slot_on_exactly_one_value(counter, released):
    """`cmpi.b #$2` — an equality, not a threshold, so a counter that skipped 2 would never let the
    slot go. Both directions release; only the rightward one also parks the other counter."""
    for facing, field in ((PT_FLAG_MOVING_RIGHT, "clip_wrapped"), (0, "clip_onscreen")):
        written = _writes(_case(_leave_pokes(flags=PT_FLAG_IN_PLAY | facing, x=0x80,
                                             **{field: counter}),
                                note=f"facing={facing} counter={counter}"))
        assert (_word(written, _slot(0) + PT_FLAGS) == 0) == released
        if released and facing:
            assert written[_slot(0) + PT_CLIP_ONSCREEN] == PTERO_EXIT_HOLD - 1, \
                "the rightward release parks the other counter, and the fade then takes one off"


def test_the_two_exit_directions_are_not_mirror_images():
    """The leftward release writes nothing to the other counter, where the rightward one writes
    PTERO_EXIT_HOLD. Reproduced as the original's asymmetry — a symmetric reconstruction passes
    every rightward case and fails here."""
    written = _writes(_case(_leave_pokes(x=0x80, clip_onscreen=PTERO_EXIT_RELEASE,
                                         clip_wrapped=0)))
    assert _word(written, _slot(0) + PT_FLAGS) == 0
    assert written[_slot(0) + PT_CLIP_WRAPPED] == 0, "cleared, not parked at PTERO_EXIT_HOLD"


AVOID_STEP = 4          # what ptero_avoid_platform answers while a platform brackets the bird


def _avoiding(pokes, note=""):
    """Run a case that must reach ptero_avoid_platform, and return PT_VY as it left it.

    Both callers need the same delicate arrangement: one tall platform PRESENT so the avoid scan
    has something to find, and a BLANK bird sprite so the platform sweep — which runs first, and
    would take the bird down the bounce path instead — can never find a shared pixel. The miss is
    asserted rather than assumed, because a sweep that hit would leave PT_VY looking plausible.
    """
    pokes[A_PLATFORM_SPRITES] = _platform_sprites(
        [(0, 0x20, 1, SPRITE_PLATFORM, 0x38 * SCREEN_ROW_BYTES)] +
        [(index, 1, 1, SPRITE_PLATFORM, 0) for index in range(1, N_PLATFORMS)])
    pokes[A_PLATFORM_PRESENT] = bytes([1] + [0] * (N_PLATFORMS - 1))
    written = _writes(_case(pokes, note=note))
    assert not written.get(A_COLLISION_HIT), "the platform sweep must miss for this to test avoid"
    return _word(written, _slot(0) + PT_VY)


@pytest.mark.parametrize("x,steps", ((0x20, False), (0x3b, False), (0x3c, True), (0xfa, True),
                                     (0xfb, False)))
def test_a_leaving_bird_still_climbs_around_platforms(x, steps):
    """PT_VY comes straight from ptero_avoid_platform, whose x window is 0x3c..0xfa inclusive. With
    no platform present it answers 0 wherever the bird is, so the window is only visible in a run
    where a platform IS present and its row band brackets the bird."""
    assert _avoiding(_leave_pokes(x=x, y=0x40, src=SPRITE_BLANK), note=f"x={x:#x}") == \
        (AVOID_STEP if steps else 0)


# ================================================================================================
# Phase F — hunting.
# ================================================================================================

def _hunt_pokes(players=3, p1_y=0x30, p2_y=0x60, **fields):
    pokes = _base_pokes(phase=0, players=players)
    fields.setdefault("x", 0x20)      # clear of ptero_avoid_platform's window, so PT_VY is its own
    fields.setdefault("y", 0x40)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(**fields))
    pokes[A_OBJECT_TABLE + OBJ_Y] = struct.pack(">H", p1_y)
    pokes[A_PLAYER2 + OBJ_Y] = struct.pack(">H", p2_y)
    return pokes


@pytest.mark.parametrize("clip_wrapped,clip_onscreen,settled",
                         ((0, 0, True), (1, 0, False), (0, 1, False), (0xff, 0xff, False)))
def test_a_bird_still_fading_neither_looks_for_a_player_nor_dives(clip_wrapped, clip_onscreen,
                                                                  settled):
    """Both counters must be 0. Told apart by PT_SWOOP_TIMER: only a settled bird gets it armed by
    ptero_spot_player. Player 1 is placed squarely inside the bird's spotting window."""
    pokes = _hunt_pokes(players=1, p1_y=0x30, p2_y=0, x=0x80, y=0x30,
                        clip_wrapped=clip_wrapped, clip_onscreen=clip_onscreen)
    pokes[A_OBJECT_TABLE + 2] = struct.pack(">HH", 0x40, 0x30)
    written = _writes(_case(pokes, note=f"{clip_wrapped}/{clip_onscreen}"))
    assert (written.get(_slot(0) + PT_SWOOP_TIMER) == PTERO_SWOOP_TIMER_SET) == settled


@pytest.mark.parametrize("players,spots_p1,spots_p2", ((3, True, True), (1, True, False),
                                                       (2, False, True), (0, False, False)))
def test_each_player_is_offered_to_the_spotter_by_its_own_bit(players, spots_p1, spots_p2):
    """`btst #0` then `btst #1` of active_players, each guarding its own call. Only ONE of the two
    players is put in the bird's window at a time, so which bit was honoured is visible in the
    swoop timer."""
    for target, expected in ((A_OBJECT_TABLE, spots_p1), (A_PLAYER2, spots_p2)):
        # ptero_spot_player wants the player -4..+6 rows off and 1..0x60 pixels to the left of a
        # bird flying left; the other player is parked far away.
        in_window, far = (0x40, 0x30), (0x1000, 0x1000)
        p1, p2 = (in_window, far) if target == A_OBJECT_TABLE else (far, in_window)
        pokes = _hunt_pokes(players=players, x=0x80, y=0x30)
        pokes[A_OBJECT_TABLE + 2] = struct.pack(">HH", *p1)
        pokes[A_PLAYER2 + 2] = struct.pack(">HH", *p2)
        written = _writes(_case(pokes, note=f"players={players} target={target:#x}"))
        assert (written.get(_slot(0) + PT_SWOOP_TIMER) == PTERO_SWOOP_TIMER_SET) == expected, \
            f"target {target:#x}"


@pytest.mark.parametrize("dwell,decides", ((3, False), (2, False), (1, True), (0, True),
                                           (0x80, True), (0x81, True), (0x7f, False)))
def test_the_dwell_timer_is_a_subq_bgt_clock(dwell, decides):
    """`subq.b #1 ; bgt` tests N == V, so 0x80 decrements to 0x7f and still compares NEGATIVE — the
    bird decides on that frame, not 127 frames later. 0 wraps to 0xff and decides too."""
    written = _writes(_case(_hunt_pokes(dwell=dwell), note=f"dwell={dwell:#x}"))
    assert (_word(written, _slot(0) + PT_VY) == PTERO_CLIMB_STEP) == decides
    assert written[_slot(0) + PT_DWELL_TIMER] == (PTERO_DWELL_FRAMES if decides
                                                  else (dwell - 1) & 0xff)


@pytest.mark.parametrize("p1_y,p2_y,y,chases_p2", ((0x30, 0x60, 0x40, False),
                                                   (0x30, 0x60, 0x50, True),
                                                   # An exact tie, staged so the two answers are
                                                   # DISTINGUISHABLE: the players straddle the bird
                                                   # by the same 0x10 rows, so player 1 sends it up
                                                   # and player 2 would send it down.
                                                   (0x30, 0x50, 0x40, False)))
def test_the_nearer_players_row_is_the_one_chased(p1_y, p2_y, y, chases_p2):
    """The two row gaps are SQUARED with `muls.w` and compared with `cmp.w`, and the winner's row
    decides the direction. A tie goes to player 1 — `blt`, not `ble`."""
    written = _writes(_case(_hunt_pokes(p1_y=p1_y, p2_y=p2_y, y=y, dwell=1),
                            note=f"p1={p1_y:#x} p2={p2_y:#x} y={y:#x}"))
    chosen = p2_y if chases_p2 else p1_y
    assert bool(_word(written, _slot(0) + PT_FLAGS) & PT_FLAG_MOVING_DOWN) == (chosen >= y)


def test_the_squared_row_gaps_are_compared_as_signed_words():
    """`muls.w` leaves a LONGWORD and `cmp.w` reads only its low half, so a gap of 0xb6 rows
    squares to 0x8164 — NEGATIVE as a word — and so beats a much smaller gap. Player 2 is 0xb6 rows
    below the bird and player 1 only 2 rows above it, and player 2 is still the one chased (the bird
    turns downward). A reconstruction comparing the two products as LONGWORDS picks player 1."""
    written = _writes(_case(_hunt_pokes(p1_y=0, p2_y=0xb8, y=2, dwell=1)))
    assert _word(written, _slot(0) + PT_FLAGS) & PT_FLAG_MOVING_DOWN, "chased player 2, the far one"


@pytest.mark.parametrize("players,down", ((3, False), (1, False), (2, True)))
def test_a_single_player_is_chased_without_a_comparison(players, down):
    """Either `btst` failing skips the squared compare entirely and picks the other player, however
    far away it is. Player 1 is above the bird and player 2 far below it."""
    written = _writes(_case(_hunt_pokes(players=players, p1_y=0, p2_y=0x90, y=0x40, dwell=1),
                            note=f"players={players}"))
    assert bool(_word(written, _slot(0) + PT_FLAGS) & PT_FLAG_MOVING_DOWN) == down


def test_with_nobody_on_the_board_the_bird_only_clears_the_platforms():
    """active_players 0 takes the other branch: PT_VY is whatever ptero_avoid_platform answers,
    bit 1 is cleared unconditionally, and the dwell clock is not consulted at all."""
    written = _writes(_case(_hunt_pokes(players=0, dwell=3,
                                        flags=PT_FLAG_IN_PLAY | PT_FLAG_MOVING_DOWN)))
    assert (_word(written, _slot(0) + PT_FLAGS) & PT_FLAG_MOVING_DOWN) == 0
    assert _word(written, _slot(0) + PT_VY) == 0
    assert _slot(0) + PT_DWELL_TIMER not in written, "this branch never touches the dwell clock"


def test_the_climb_step_is_flattened_to_one():
    """ptero_avoid_platform answers 4, and this branch overwrites it with PTERO_CLIMB_STEP — so the
    bird creeps over a platform rather than jumping it."""
    assert _avoiding(_hunt_pokes(players=0, x=0x80, y=0x40, dwell=3, src=SPRITE_BLANK)) == \
        PTERO_CLIMB_STEP
    assert PTERO_CLIMB_STEP != AVOID_STEP, "the flattening is only visible while the two differ"


@pytest.mark.parametrize("anim,advances", ((0, True), (8, True), (PT_ANIM_POSE2, False),
                                           (PT_ANIM_POSE3, True), (0x27, True), (0x30, False),
                                           (0x14, False), (0x37, False), (0x2f, True)))
def test_the_dive_freezes_on_one_pose(anim, advances):
    """The dive's own `addq.w #1` and the shared `addq.w #3` are BOTH skipped once
    (anim & PT_ANIM_FRAME_MASK) reaches PT_ANIM_POSE2 — the one path in the routine that branches
    past the shared advance. Everything outside those two bits is ignored, which is why 0x30 and
    0x37 freeze exactly as 0x10 and 0x14 do."""
    written = _writes(_case(_hunt_pokes(swoop=5, anim=anim), note=f"anim={anim:#x}"))
    # The freeze leaves PT_ANIM unwritten, so the default would satisfy the assertion on its own —
    # PT_VX is what proves the bird really took the dive rather than never reaching it.
    assert _word(written, _slot(0) + PT_VX) == PTERO_DIVE_SPEED, "the dive never ran"
    expected = (anim + 1 + PT_ANIM_STEP) & 0xffff if advances else anim
    assert _word(written, _slot(0) + PT_ANIM, default=anim) == expected


def test_the_dive_decrements_its_timer_without_ever_testing_it():
    """`subq.b #1,30(a0)` with no branch: the dive ends when the pose ladder or a platform ends it,
    never because the counter ran out. A timer of 1 lands on 0 and the dive still happened."""
    written = _writes(_case(_hunt_pokes(swoop=1, anim=0)))
    assert written[_slot(0) + PT_SWOOP_TIMER] == 0
    assert _word(written, _slot(0) + PT_VX) == PTERO_DIVE_SPEED


def test_the_dive_and_the_cruise_travel_at_different_speeds():
    diving = _writes(_case(_hunt_pokes(swoop=5)))
    cruising = _writes(_case(_hunt_pokes(swoop=0, dwell=3)))
    assert _word(diving, _slot(0) + PT_VX) == PTERO_DIVE_SPEED
    assert _word(diving, _slot(0) + PT_VY) == 0
    assert _word(cruising, _slot(0) + PT_VX) == PTERO_CRUISE_SPEED


# ================================================================================================
# Phase G — dying.
# ================================================================================================

def _death_pokes(swoop=1, dwell=1, anim=0, flags=PT_FLAG_IN_PLAY | PT_FLAG_DYING, first_free=0,
                 **fields):
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_MESSAGE_TABLE] = _message_table(first_free)
    fields.setdefault("x", 0x40)
    fields.setdefault("y", 0x30)
    pokes[A_PTERODACTYL_TABLE] = _table(
        _ptero(flags=flags, swoop=swoop, dwell=dwell, anim=anim, vx=0, vy=0, **fields))
    return pokes


def test_a_dying_bird_stops_dead_and_uncovers_itself():
    """Both speeds and both clip counters are zeroed on every frame of the animation."""
    written = _writes(_case(_death_pokes(swoop=4, dwell=4, clip_wrapped=9, clip_onscreen=9)))
    assert _word(written, _slot(0) + PT_VX) == 0 and _word(written, _slot(0) + PT_VY) == 0
    assert written[_slot(0) + PT_CLIP_WRAPPED] == 0
    assert written[_slot(0) + PT_CLIP_ONSCREEN] == 0


@pytest.mark.parametrize("swoop,flips", ((3, False), (2, False), (1, True), (0, False)))
def test_the_pose_timer_flips_the_facing_when_it_reaches_zero(swoop, flips):
    """`subq.b #1 ; bne` — the stored byte alone, so 0 wraps to 0xff and does NOT fire."""
    written = _writes(_case(_death_pokes(swoop=swoop, dwell=9), note=f"swoop={swoop}"))
    assert bool(_word(written, _slot(0) + PT_FLAGS) & PT_FLAG_MOVING_RIGHT) == flips
    assert written[_slot(0) + PT_SWOOP_TIMER] == (PTERO_DEATH_POSE_FRAMES if flips
                                                  else (swoop - 1) & 0xff)


@pytest.mark.parametrize("anim,pose", ((0, PT_ANIM_POSE3), (PT_ANIM_POSE3 - 1, PT_ANIM_POSE3),
                                       (PT_ANIM_POSE3, PT_ANIM_POSE2), (0x100, PT_ANIM_POSE2),
                                       (0x8000, PT_ANIM_POSE3), (0xffff, PT_ANIM_POSE3)))
def test_the_death_flap_alternates_between_two_poses_on_a_signed_test(anim, pose):
    """`cmpi.w #$18 ; bge` is SIGNED on the WHOLE counter, not on its pose bits — so 0x8000 counts
    as below 0x18 and takes the same arm as 0. The pose is ASSIGNED, not stepped, and the shared
    advance never runs while bit 5 is up."""
    written = _writes(_case(_death_pokes(swoop=9, anim=anim), note=f"anim={anim:#x}"))
    assert _word(written, _slot(0) + PT_ANIM) == pose


def test_the_last_pose_releases_the_slot_and_posts_the_bounty():
    """Both counters running out on the same frame: the flags word is cleared (which is what frees
    the slot), both clip counters are parked at PTERO_DEATH_CLIP, and the popup goes into the first
    free message record. Clearing the flags also drops bit 5, so the shared pose advance runs."""
    written = _writes(_case(_death_pokes(swoop=1, dwell=1, anim=0)))
    assert _word(written, _slot(0) + PT_FLAGS) == 0
    assert written[_slot(0) + PT_CLIP_WRAPPED] == PTERO_DEATH_CLIP - 1
    assert written[_slot(0) + PT_CLIP_ONSCREEN] == PTERO_DEATH_CLIP - 1
    assert _word(written, _slot(0) + PT_ANIM) == PT_ANIM_STEP, "no longer dying, so the pose steps"

    assert _long(written, A_MESSAGE_TABLE + MSG_STRING) == STR_PTERO_BOUNTY
    assert written[A_MESSAGE_TABLE + MSG_KIND] == PTERO_BOUNTY_KIND
    assert written[A_MESSAGE_TABLE + MSG_COLOR] == PTERO_BOUNTY_COLOR
    assert written[A_MESSAGE_TABLE + MSG_TIMER] == PTERO_BOUNTY_FRAMES


@pytest.mark.parametrize("x,y", ((0x40, 0x30), (0, 0), (0x13f, 0x95), (0xfff8, 0xfffe), (7, 1)))
def test_the_bounty_lands_where_the_bird_was(x, y):
    """The row from y + PTERO_BOUNTY_Y_BIAS, the column from x + PTERO_BOUNTY_X_BIAS through
    `divu.w #$10` — remainder to MSG_SHIFT, quotient scaled by CELL_BYTES into the address. Both
    biases are applied in a WORD, so 0xfff8 + 8 wraps to 0 rather than carrying.

    One of the two batteries poison is safe on, and the reason is structural rather than lucky: the
    twelve bytes it writes are a message record, and nothing in this routine branches on one.
    """
    written = _writes(_case(_death_pokes(x=x, y=y), poison=True, note=f"x={x:#x} y={y:#x}"))
    column = (x + PTERO_BOUNTY_X_BIAS) & 0xffff
    expected = (((y + PTERO_BOUNTY_Y_BIAS) & 0xffff) * SCREEN_ROW_BYTES
                + (column // CELL_PIXELS) * CELL_BYTES + SCREEN) & 0xffffffff
    assert _long(written, A_MESSAGE_TABLE + MSG_SCREEN_PTR) == expected
    assert written[A_MESSAGE_TABLE + MSG_SHIFT] == column % CELL_PIXELS


@pytest.mark.parametrize("first_free", (0, 1, 12, 23))
def test_the_bounty_takes_the_first_free_slot(first_free):
    written = _writes(_case(_death_pokes(first_free=first_free), note=f"first_free={first_free}"))
    at = A_MESSAGE_TABLE + first_free * MSG_RECORD
    assert _long(written, at + MSG_STRING) == STR_PTERO_BOUNTY


def test_a_full_message_table_loses_the_bounty_rather_than_writing_over_the_vector_page():
    """This walk is NOT find_free_message: it ends at the table bound with nothing written, where
    find_free_message hands its callers a 0 they then write twelve bytes through (see
    player_death's and collision_check's rows in STATUS.md). The slot is still released."""
    written = _writes(_case(_death_pokes(first_free=N_MESSAGES)))
    assert _word(written, _slot(0) + PT_FLAGS) == 0, "the slot is freed either way"
    assert not [a for a in written if a < 0x100], "nothing was written over the vector page"
    assert not [a for a in written
                if A_MESSAGE_TABLE <= a < A_MESSAGE_TABLE + N_MESSAGES * MSG_RECORD]


@pytest.mark.parametrize("dwell,ends", ((3, False), (2, False), (1, True), (0, False)))
def test_the_flap_count_ends_the_animation_on_the_stored_byte(dwell, ends):
    """The second `subq.b #1 ; bne`, and it only runs on a frame the pose timer fired."""
    written = _writes(_case(_death_pokes(swoop=1, dwell=dwell), note=f"dwell={dwell:#x}"))
    assert (_word(written, _slot(0) + PT_FLAGS) == 0) == ends
    if not ends:
        assert written[_slot(0) + PT_DWELL_TIMER] == (dwell - 1) & 0xff


def test_the_flap_count_is_only_touched_on_a_frame_the_pose_timer_fired():
    written = _writes(_case(_death_pokes(swoop=3, dwell=1)))
    assert _slot(0) + PT_DWELL_TIMER not in written
    assert _word(written, _slot(0) + PT_FLAGS) & PT_FLAG_DYING


# ================================================================================================
# Phase H — the pose, the move, the clip and the draw.
#
# The move battery rides on the platform bounce, because it is the ONLY driver that leaves one of
# the two speeds where the record put it: the vertical arm keeps PT_VX and the facing bit, and the
# horizontal arms keep PT_VY and the up/down bit. Every other driver overwrites both.
# ================================================================================================

@pytest.mark.parametrize("anim", (0, 1, 7, 8, 0x10, 0x18, 0x1f, 0x20, 0xfffd, 0xffff))
def test_the_pose_advances_three_a_frame_and_runs_round_the_word(anim):
    written = _writes(_case(_hunt_pokes(anim=anim, dwell=3), note=f"anim={anim:#x}"))
    assert _word(written, _slot(0) + PT_ANIM, default=anim) == (anim + PT_ANIM_STEP) & 0xffff


@pytest.mark.parametrize("anim", (0, 8, 0x10, 0x18))
@pytest.mark.parametrize("facing", (0, PT_FLAG_MOVING_RIGHT))
def test_the_frame_table_is_indexed_by_the_pose_bits_and_offset_by_the_facing(anim, facing):
    """Four records of FRAME_RECORD bytes, picked by (PT_ANIM & PT_ANIM_FRAME_MASK) — which IS the
    byte offset — and a rightward bird reads the same record with PTERO_FACING_STRIDE added to its
    source. The pose advance happens BEFORE the lookup, so the index is this frame's pose."""
    pokes = _hunt_pokes(anim=anim, dwell=3, flags=PT_FLAG_IN_PLAY | facing)
    # A synthetic frame table, so a record picked by luck rather than by index shows up.
    pokes[A_PTERO_FRAME_TABLE] = b"".join(
        struct.pack(">IHH", SPRITE_BIRD + index * 0x40, index * 2, 1) for index in range(4))
    written = _writes(_case(pokes, note=f"anim={anim:#x} facing={facing}"))
    index = ((anim + PT_ANIM_STEP) & PT_ANIM_FRAME_MASK) // FRAME_RECORD
    assert _long(written, _slot(0) + PT_SRC) == \
        SPRITE_BIRD + index * 0x40 + (PTERO_FACING_STRIDE if facing else 0)
    assert _word(written, _slot(0) + PT_DST_OFF) == index * 2
    assert _word(written, _slot(0) + PT_ROWS_W) == 1


@pytest.mark.parametrize("x,vx,expected", ((0x100, 4, 0x104), (0x13b, 4, 0x13f), (0x13c, 4, 0),
                                           (0x13f, 1, 0), (0x7ff9, 6, 0), (0x7ffa, 6, 0x8000),
                                           (0, 0, 0)))
def test_a_rightward_bird_wraps_at_the_playfield_edge(x, vx, expected):
    """`add.w` then `cmpi.w #$140 ; blt` — a SIGNED bound. A sum under 0x140 is kept, one at or past
    it wraps to 0... and one that has run on into the NEGATIVE half of the word (0x7ffa + 6) reads
    as far BELOW 0x140 and is kept as it stands."""
    _, _, _, written = _bounced(_hit_pokes(x=x, vx=vx, facing=PT_FLAG_MOVING_RIGHT),
                                note=f"x={x:#x} vx={vx}")
    assert _word(written, _slot(0) + PT_X, default=x) == expected


@pytest.mark.parametrize("x,vx,expected", ((0x100, 4, 0xfc), (4, 4, 0), (3, 4, 0x13f),
                                           (0, 1, 0x13f), (0x7ffa, 6, 0x7ff4)))
def test_a_leftward_bird_wraps_at_x_zero(x, vx, expected):
    """`sub.w` + `bge` — N == V, so an ordinary underflow wraps the bird round to the right edge."""
    _, _, _, written = _bounced(_hit_pokes(x=x, vx=vx), note=f"x={x:#x} vx={vx}")
    assert _word(written, _slot(0) + PT_X, default=x) == expected


@pytest.mark.parametrize("vx", (0, 1, 4))
def test_the_leftward_wrap_tests_n_equals_v_not_the_stored_word(vx):
    """From x 0x8000 the subtraction fails `bge` for ANY step: 0x8000 - 0 is negative (N == 1,
    V == 0) and 0x8000 - 4 is a large positive 0x7ffc with V set. Both wrap the bird to the right
    edge, where reading the stored word's sign would keep 0x7ffc.

    x 0x8000 is also the one value no bump bound can be strictly left of, so this case necessarily
    rides the LEFT arm of the bounce — which forces PT_VX to PTERO_BOUNCE_SPEED. The staged step is
    therefore only itself for vx == PTERO_BOUNCE_SPEED; the other two ride the same arm and are
    here to show that the wrap does not depend on what the record asked for.
    """
    _, _, _, written = _bounced(_hit_pokes(x=0x8000, vx=vx, bumps=((0x8000, BUMP_NEVER_RIGHT, 0),)),
                                note=f"vx={vx}")
    assert _word(written, _slot(0) + PT_X) == PLAYFIELD_WIDTH - 1


@pytest.mark.parametrize("y,vy,expected", ((0x40, 4, 0x44), (0x91, 4, 0x95), (0x92, 4, PTERO_Y_MAX),
                                           (0x93, 4, PTERO_Y_MAX), (0x7fff, 4, PTERO_Y_MAX),
                                           (0xfffe, 1, PTERO_Y_MAX), (0x8000, 1, PTERO_Y_MAX)))
def test_the_downward_clamp_is_unsigned(y, vy, expected):
    """`cmpi.w #$96 ; bcs` — UNSIGNED, so 0x8001 and 0xffff are both "past the floor" and clamp,
    where the horizontal bound of the same shape would have called them negative."""
    _, _, _, written = _bounced(_hit_pokes(y=y, vy=vy, down=True,
                                           bumps=((0x80, BUMP_NEVER_RIGHT, 0),)),
                                note=f"y={y:#x} vy={vy}")
    assert _word(written, _slot(0) + PT_Y, default=y) == expected


@pytest.mark.parametrize("y,vy,expected", ((0x40, 4, 0x3c), (4, 4, 0), (3, 4, 0), (0, 1, 0),
                                           (0x8000, 4, 0), (0xfffe, 4, 0)))
def test_the_upward_clamp_stops_at_zero(y, vy, expected):
    """`sub.w` + `bge` again, and here the answer is a CLAMP rather than the wrap the horizontal
    axis gets. 0x8000 - 4 overflows to a large positive 0x7ffc and still clamps to 0."""
    _, _, _, written = _bounced(_hit_pokes(y=y, vy=vy, down=False,
                                           bumps=((0x80, BUMP_NEVER_RIGHT, 0),)),
                                note=f"y={y:#x} vy={vy}")
    assert _word(written, _slot(0) + PT_Y, default=y) == expected


@pytest.mark.parametrize("x", (0, 0x11f, 0x120, 0x12f, 0x130, 0x13f))
def test_the_clip_suppressors_follow_the_cells_that_wrapped_off_the_right_edge(x):
    """All three cells take PT_CLIP_ONSCREEN first; then the trailing cell takes PT_CLIP_WRAPPED
    from PTERO_WRAP_ONE_CELL on, and the middle one from PTERO_WRAP_TWO_CELLS on — which are
    exactly the x values at which those cells fall past the end of the scanline. Both bounds are
    UNSIGNED word compares of the x the bird has just MOVED to, which is why the staged step is 0."""
    pokes = _hit_pokes(x=x, vx=0, vy=1, facing=PT_FLAG_MOVING_RIGHT,
                       clip_wrapped=5, clip_onscreen=9)
    pokes[A_DRAW_CLIP_CELL0] = bytes([UNWRITTEN] * 3)
    _, _, _, written = _bounced(pokes, note=f"x={x:#x}")
    assert _word(written, _slot(0) + PT_X, default=x) == x, "the staged step must be 0"

    onscreen, wrapped = 9 - 1, 5 - 1       # both counters are faded before they are staged
    cells = [onscreen, onscreen, onscreen]
    if x >= PTERO_WRAP_ONE_CELL:
        cells[2] = wrapped
    if x >= PTERO_WRAP_TWO_CELLS:
        cells[1] = wrapped
    assert [written[A_DRAW_CLIP_CELL0 + n] for n in range(3)] == cells


@pytest.mark.parametrize("counter,left", ((3, 2), (1, 0), (0, 0), (0x80, 0), (0x81, 0),
                                          (0x7f, 0x7e)))
def test_a_clip_counter_fades_to_zero_and_stops(counter, left):
    """`subq.b #1 ; bge ; clr.b` — the N == V test again, so 0x80 stores 0x7f and is then CLEARED
    rather than counting down from 127. A mutation reading the truncated sign survives every value
    the game produces and dies on 0x80."""
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_PTERODACTYL_TABLE] = _table(
        _ptero(x=0x20, y=0x40, vx=0, vy=0, dwell=3, clip_wrapped=counter, clip_onscreen=counter))
    written = _writes(_case(pokes, note=f"counter={counter:#x}"))
    assert written[_slot(0) + PT_CLIP_WRAPPED] == left
    assert written[_slot(0) + PT_CLIP_ONSCREEN] == left


@pytest.mark.parametrize("x,y", ((0, 0x30), (0x40, 0x30), (0x13f, 0x95), (0x11, 0x01)))
@pytest.mark.parametrize("screen_base", (SCREEN, SCREEN_ALT))
def test_the_draw_scratch_and_the_record_agree_on_where_the_frame_landed(x, y, screen_base):
    """draw_dst is y * SCREEN_ROW_BYTES + (x / CELL_PIXELS) * CELL_BYTES with NO screen_base in it —
    the blitters add that — and draw_shift is the remainder, written as a WORD (the width clash
    addrs.h documents). All five scratch words are then copied back into the record. Both
    coordinates are the ones the frame's own move left behind, which is why they are read back out
    of the write set rather than assumed."""
    pokes = _base_pokes(phase=0, players=0, screen_base=screen_base)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(x=x, y=y, vx=0, vy=0, dwell=3))
    pokes[A_DRAW_DST] = bytes([UNWRITTEN] * 0x14)     # draw_dst .. draw_dst_off
    written = _writes(_case(pokes, note=f"x={x:#x} y={y:#x} base={screen_base:#x}"))
    moved_x = _word(written, _slot(0) + PT_X, default=x)
    moved_y = _word(written, _slot(0) + PT_Y, default=y)
    assert _long(written, A_DRAW_DST) == \
        moved_y * SCREEN_ROW_BYTES + (moved_x // CELL_PIXELS) * CELL_BYTES
    assert _word(written, A_DRAW_SHIFT) == moved_x % CELL_PIXELS
    assert _long(written, _slot(0) + PT_DST) == _long(written, A_DRAW_DST)
    assert _word(written, _slot(0) + PT_SHIFT_W) == _word(written, A_DRAW_SHIFT)
    assert _long(written, _slot(0) + PT_SRC) == _long(written, A_DRAW_SRC)
    assert _word(written, _slot(0) + PT_ROWS_W) == _word(written, A_DRAW_ROWS)
    assert _word(written, _slot(0) + PT_DST_OFF) == _word(written, A_DRAW_DST_OFF)


def test_the_erase_pass_uses_the_previous_frames_record_not_this_frames():
    """blit_mask_wide runs BEFORE the record is rewritten, so the AND-mask lands where the bird was
    last drawn. Staged with a previous frame far from the new one, so the two are distinguishable.

    The second battery poison is safe on: the bytes it inverts are framebuffer, which nothing in
    this routine reads back."""
    prev_dst = 0x20 * SCREEN_ROW_BYTES
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_PTERODACTYL_TABLE] = _table(
        _ptero(x=0x40, y=0x60, vx=0, vy=0, dwell=3, dst=prev_dst, rows=4,
               src=PTERO_SPRITE_LEFTWARD))
    pokes[SCREEN] = b"\xff" * SCREEN_BYTES
    written = _writes(_case(pokes, poison=True))
    assert any(SCREEN + prev_dst <= a < SCREEN + prev_dst + 4 * SCREEN_ROW_BYTES for a in written), \
        "nothing was erased at the previous frame's address"


# The overlapping-blit case below, laid out so the two passes contend for the same bytes.
OVERLAP_X, OVERLAP_Y = 0x40, 0x30      # the bird's staged position; the hunt moves x left by 3
OVERLAP_ROWS = 6
OVERLAP_SHIFT = (OVERLAP_X - PTERO_CRUISE_SPEED) % CELL_PIXELS
OVERLAP_DST = OVERLAP_Y * SCREEN_ROW_BYTES \
    + ((OVERLAP_X - PTERO_CRUISE_SPEED) // CELL_PIXELS) * CELL_BYTES


def test_the_erase_runs_before_the_draw_when_the_two_blits_share_bytes():
    """blit_mask_wide then blit_sprite_planes — the ORDER, not just which record each reads.

    The two passes are given the SAME screen rectangle: the record's previous frame (PT_DST,
    PT_ROWS_W) is staged at exactly the address and height this frame's x/y and frame record produce.
    They are also given contending data — an all-ZERO erase mask and an all-ONES sprite over an
    all-ONES framebuffer — so the two orders leave different bytes:

        erase then draw (the original)  ->  the rectangle is cleared, then the sprite is ORed back
        draw then erase                 ->  the OR changes nothing, and the clear wipes it out

    Swapping the two calls therefore leaves the whole rectangle at 0, which the assertions below
    catch on their own. Without this case the order is pinned only by the fuzz corpus — and only by
    three of its four shards — so a seed or FUZZ_CASES change could lose it silently.
    """
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_PTERODACTYL_TABLE] = _table(_ptero(
        x=OVERLAP_X, y=OVERLAP_Y, vx=0, vy=0, dwell=3, clip_wrapped=0, clip_onscreen=0,
        # The erase reads its mask PTERO_MASK_OFF into this set; SPRITE_BLANK is never poked, so the
        # mask is all zeros and the AND clears every byte it covers.
        src=SPRITE_BLANK, dst=OVERLAP_DST, dst_off=0, rows=OVERLAP_ROWS))
    # All four poses identical, so the frame the pose advance lands on cannot change the geometry.
    pokes[A_PTERO_FRAME_TABLE] = struct.pack(">IHH", SPRITE_BIRD, 0, OVERLAP_ROWS) * 4
    pokes[SCREEN] = b"\xff" * SCREEN_BYTES

    written = _writes(_case(pokes, note="erase and draw over the same rectangle"))
    assert _long(written, _slot(0) + PT_DST) == OVERLAP_DST, "the two rectangles must coincide"
    assert _word(written, A_DRAW_SHIFT) == OVERLAP_SHIFT

    # Cell 1 takes the sprite's low half whole (0xffff per plane) and cell 0 only what spilled into
    # its high half, so one cell proves the draw survived the erase and the other proves the erase
    # ran at all. Under the swap both are 0.
    at = SCREEN + OVERLAP_DST
    assert written[at + CELL_BYTES] == 0xff, "the draw did not survive the erase"
    assert written[at] == 0x00, "the erase never ran (the screen is still as it was staged)"


def test_every_occupied_slot_is_driven_and_drawn():
    """Four birds in one pass, each at its own x, each leaving its own record rewritten."""
    pokes = _base_pokes(phase=0, players=0)
    pokes[A_PTERODACTYL_TABLE] = _table(
        *[_ptero(x=0x10 + index * 0x40, y=0x20 + index * 0x10, vx=0, vy=0, dwell=3)
          for index in range(N_PTEROS)])
    written = _writes(_case(pokes))
    for index in range(N_PTEROS):
        assert _slot(index) + PT_DST in written, f"slot {index} was never drawn"


# ================================================================================================
# Phase I — the fuzz corpus.
# ================================================================================================

FUZZ_CASES = 240
FUZZ_CHUNKS = 4
FUZZ_SHAPES = ("idle", "spawn", "hunt", "leave", "die", "bounce")


def _fuzz_pokes(rng, shape):
    """One randomised starting state, bent towards `shape`.

    PT_DST and PT_ROWS_W are kept modest: they are what the erase pass blits through, and a wild
    pair would paint outside the framebuffer — over the program on one side and into the stack guard
    on the other, where the harness (rightly) refuses to compare.
    """
    screen_base = rng.choice((SCREEN, SCREEN_ALT))
    # The idle shape exists to reach the SCHEDULER, which needs all three of a wave in progress,
    # somebody to hunt, and a timer that has run out; drawn independently they coincide about one
    # case in five. The two negatives that gate it are covered exhaustively by the Phase A battery,
    # and free slots in the other five shapes still see a randomised phase, timer and player set.
    phase = {"idle": 0, "leave": 1}.get(shape, 0)
    players = 0 if shape == "leave" else rng.choice((1, 2, 3) if shape == "idle" else (0, 1, 2, 3))

    records = []
    for slot in range(N_PTEROS):
        if shape == "idle" and slot == 0:
            records.append(None)
            continue
        flags = PT_FLAG_IN_PLAY
        if shape == "spawn" and slot == 0:
            flags = PT_FLAG_JUST_SPAWNED
        if shape == "die" and slot == 0:
            flags |= PT_FLAG_DYING
        flags |= rng.choice((0, PT_FLAG_MOVING_RIGHT))
        flags |= rng.choice((0, PT_FLAG_MOVING_DOWN))
        if shape == "leave":
            flags |= rng.choice((0, PT_FLAG_LEAVING))
        # A dying bird only reaches the release-and-bounty frame when BOTH byte timers land on 0
        # together, which chance alone almost never arranges. So a corpse's pose timer is always
        # staged one frame short and only its flap count is rolled — three cases in four then reach
        # the release and post the bounty, and the fourth takes the ordinary flap arm. (The death
        # sub-branches themselves are covered exhaustively by the Phase G battery; what the corpus
        # is for is reaching them from randomised surroundings.)
        finishing = shape == "die" and slot == 0
        # ...and the dive is just as unlikely: it needs BOTH clip counters at 0 and a swoop timer
        # already armed, which chance gives about one case in twenty. The hunt shape's first slot is
        # therefore staged to reach it every time. Every other slot keeps its random counters, so
        # the "still fading, so neither spot nor dive" path is still exercised all over the corpus.
        diving = shape == "hunt" and slot == 0
        records.append(None if rng.randrange(4) == 0 and slot else _ptero(
            flags=flags,
            dst=rng.randrange(0, 0x60) * SCREEN_ROW_BYTES,
            rows=rng.choice((0, 1, 4, 7, 0xb)),
            src=PTERO_SPRITE_LEFTWARD,
            shift=rng.randrange(0x10),
            x=rng.choice((rng.randrange(PLAYFIELD_WIDTH), 0, 0x13f, 0x11c, 0x120, 0x130)),
            y=rng.choice((rng.randrange(PTERO_Y_MAX + 1), 0, PTERO_Y_MAX)),
            vx=rng.choice((0, 1, 2, 3, 4, 6)), vy=rng.choice((0, 1, 2, 4)),
            dst_off=rng.choice((0, 0xa0, 0x280)),
            anim=rng.randrange(0x40),
            clip_wrapped=0 if diving else rng.choice((0, 0, 1, 2, 3, 7, 0x80)),
            clip_onscreen=0 if diving else rng.choice((0, 0, 1, 2, 3, 7, 0x80)),
            swoop=1 if finishing else rng.choice((1, 4, 0x14, 0x80)) if diving
            else rng.choice((0, 0, 1, 4, 0x14, 0x80)),
            dwell=rng.choice((1, 1, 1, 2)) if finishing
            else rng.choice((0, 1, 2, 3, 4, 0x80))))

    present = [rng.randrange(2) for _ in range(N_PLATFORMS)] if shape == "bounce" \
        else [0] * N_PLATFORMS
    pokes = _base_pokes(phase=phase, players=players, screen_base=screen_base,
                        timer=rng.choice((0, 1, 0xffff) if shape == "idle"
                                         else (0, 1, 2, 0x100, 0x8000, 0xffff)),
                        interval=rng.choice((0, 1, 0x40, 0x200, 0xffbe)))
    pokes[A_PTERODACTYL_TABLE] = _table(*records)
    pokes[A_PTERO_WAVE_COUNTDOWN] = bytes([rng.choice((0, 1, 5))])
    pokes[A_PLATFORM_PRESENT] = bytes(present)
    pokes[A_PLATFORM_SPRITES] = _platform_sprites(
        [(index, rng.choice((1, 4, 8)), rng.choice((1, 2, 4)), SPRITE_PLATFORM,
          rng.randrange(0, 0x60) * SCREEN_ROW_BYTES) for index in range(N_PLATFORMS)])
    pokes[A_PTERO_BUMP_TABLE] = _bump_table(
        [(rng.randrange(0x140), rng.randrange(0x140), rng.randrange(0x100))
         for _ in range(N_PLATFORMS)])
    pokes[A_RNG_PTR] = struct.pack(">I", rng.randrange(0x10000, 0x17832) & ~1)
    # A corpse case wants somewhere to post its bounty; every other shape may see a full table.
    pokes[A_MESSAGE_TABLE] = _message_table(
        rng.choice((0, 1, 12)) if shape == "die" else rng.choice((0, 1, 12, N_MESSAGES)))
    pokes[A_OBJECT_TABLE + 2] = struct.pack(">HH", rng.randrange(0x140), rng.randrange(0xa0))
    pokes[A_PLAYER2 + 2] = struct.pack(">HH", rng.randrange(0x140), rng.randrange(0xa0))
    pokes[A_SND_PRIORITY] = struct.pack(">H", rng.choice((SND_PRIORITY_IDLE, 3, 2, 0x7fff)))
    pokes[screen_base] = bytes(range(1, 0x100)) * (SCREEN_BYTES // 0xff)
    return pokes


@functools.lru_cache(maxsize=1)
def _fuzz_corpus():
    """The whole corpus, generated from ONE seed outside any shard filter so that every chunk
    replays the same stream and sees the same cases however they are scheduled. Cached because each
    case carries ~96 KB of poke payload and every shard asks for all of it."""
    rng = random.Random(ENTRY_UPDATE_PTERODACTYL)
    # The shape cycles per CHUNK, not per index: FUZZ_CHUNKS and len(FUZZ_SHAPES) share a factor,
    # so `index % len(FUZZ_SHAPES)` would hand every shape of one parity to the same two chunks and
    # leave the coverage floor below structurally unreachable.
    return tuple(_fuzz_pokes(rng, FUZZ_SHAPES[(index // FUZZ_CHUNKS) % len(FUZZ_SHAPES)])
                 for index in range(FUZZ_CASES))


# What a fuzz case is classified by, off the ORACLE's own write set: {name: predicate(written)}.
# One event per shape the corpus claims to reach, plus `drew`, which fires for a driven bird of any
# shape and so only guards against a corpus that stopped driving anything at all.
#
# EACH PREDICATE HAS TO BE EXACT, not merely correlated with the branch — a counter that infers "the
# branch fired" from an output some OTHER branch also produces is met by the wrong cases and goes on
# reporting coverage after the branch it names has gone dead. Two here needed care:
#   * PTERO_DIVE_SPEED and PTERO_LEAVE_SPEED are the SAME value (6, from two different `move.w #$6`
#     instructions), so "PT_VX == 6" is tripped by every bird that merely LEFT — measured at 105
#     cases against 16 real dives. The dive is separated by the flags word instead: fly_away always
#     raises PT_FLAG_LEAVING, and the only other writers of PT_VX are the bounce (4) and the death
#     (0), so a live, non-leaving bird travelling at 6 is diving and nothing else is.
#   * spawn_pterodactyl's flags word (PT_FLAG_IN_PLAY, maybe bit 2) is indistinguishable from an
#     ordinary live bird's, so the BUILD is witnessed by the one byte only it touches.
def _slot_flag_words(written):
    return [(written[_slot(s) + PT_FLAGS] << 8) | written[_slot(s) + PT_FLAGS + 1]
            for s in range(N_PTEROS) if _slot(s) + PT_FLAGS in written]


def _dived(written):
    for slot in range(N_PTEROS):
        if _slot(slot) + PT_VX not in written or _slot(slot) + PT_FLAGS not in written:
            continue
        flags = _word(written, _slot(slot) + PT_FLAGS)
        if flags == 0 or flags & (PT_FLAG_LEAVING | PT_FLAG_DYING):
            continue
        if _word(written, _slot(slot) + PT_VX) == PTERO_DIVE_SPEED:
            return True
    return False


FUZZ_EVENTS = {
    "armed": lambda w: PT_FLAG_JUST_SPAWNED in _slot_flag_words(w),   # the scheduler
    "built": lambda w: A_PTERO_SPAWN_COUNT in w,                      # ...and spawn_pterodactyl
    "released": lambda w: 0 in _slot_flag_words(w),
    "bounced": lambda w: any(A_PLATFORM_PRESENT <= a < A_PLATFORM_PRESENT + N_PLATFORMS for a in w),
    "bounty": lambda w: any(w.get(A_MESSAGE_TABLE + s * MSG_RECORD + MSG_KIND) == PTERO_BOUNTY_KIND
                            for s in range(N_MESSAGES)),
    "dived": _dived,
    "drew": lambda w: any(a >= SCREEN for a in w),
}

# Every chunk must reach every event this many times. FUZZ_CASES / FUZZ_CHUNKS / len(FUZZ_SHAPES)
# is how many cases of ONE shape a chunk sees, so this is "most of the cases bent that way".
FUZZ_EVENT_FLOOR = FUZZ_CASES // FUZZ_CHUNKS // len(FUZZ_SHAPES) // 2


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_update_pterodactyl_fuzz(chunk):
    """Random tables across all six shapes, four slots at a time.

    The same pass classifies each case by what the ORACLE wrote, so a staging slip that quietly
    turned this chunk into do-nothing frames fails here instead of leaving 60 green cases proving
    nothing. Classifying inside the differential run rather than in a separate test is what keeps
    the battery shardable: a second pass over the whole corpus would be one unsharded test doing
    four chunks' worth of oracle work.
    """
    reached = {name: 0 for name in FUZZ_EVENTS}
    ran = 0
    for index, pokes in enumerate(_fuzz_corpus()):
        if index % FUZZ_CHUNKS != chunk:
            continue
        ran += 1
        written = _writes(_case(pokes, max_insns=1_000_000, note=f"fuzz case {index}"))
        for name, reached_by in FUZZ_EVENTS.items():
            reached[name] += bool(reached_by(written))
    assert ran, "the chunk filter rejected every case"
    assert all(count >= FUZZ_EVENT_FLOOR for count in reached.values()), \
        f"chunk {chunk} is lopsided: {reached}"


def test_poison_would_test_a_different_function():
    """Why `poison=True` is off almost everywhere here, MEASURED rather than assumed: the routine
    branches on the bytes it writes, so the attribution pass's inverted image runs a different case.
    A settled bird with both clip counters at 0 dives; invert them and it is fading in, which skips
    the dive entirely and cruises instead — a different path, not a check of this one."""
    plain = _writes(_case(_hunt_pokes(swoop=5, anim=0)))
    other = _writes(_case(_hunt_pokes(swoop=5, anim=0, clip_wrapped=0xff, clip_onscreen=0xff)))
    assert _word(plain, _slot(0) + PT_VX) != _word(other, _slot(0) + PT_VX), \
        "inverting the clip counters must change which driver runs, or poison would be safe here"


# ================================================================================================
# Pins — the constants above restated from ../../names.txt and include/, kept equal by test.
# ================================================================================================

def test_entry_address_matches_names_txt():
    assert harness.NAME_MAP.get(ENTRY_UPDATE_PTERODACTYL) == "update_pterodactyl"


def test_named_globals_match_names_txt():
    """The three addresses this layer OWNS carry the names ../../names.txt gives them."""
    for addr, name in ((A_PTERO_FRAME_TABLE, "ptero_frame_table"),
                       (A_PTERO_BUMP_TABLE, "ptero_bump_table"),
                       (STR_PTERO_BOUNTY, "str_ptero_bounty")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


# (this module's name, the file that owns it, the name it has there)
MIRRORED = (
    ("A_PTERO_FRAME_TABLE", "include/ptero.h", "A_ptero_frame_table"),
    ("A_PTERO_BUMP_TABLE", "include/ptero.h", "A_ptero_bump_table"),
    ("STR_PTERO_BOUNTY", "include/ptero.h", "STR_PTERO_BOUNTY"),
    ("FRAME_SRC", "include/ptero.h", "FRAME_SRC"),
    ("FRAME_DST_OFF", "include/ptero.h", "FRAME_DST_OFF"),
    ("FRAME_ROWS", "include/ptero.h", "FRAME_ROWS"),
    ("FRAME_RECORD", "include/ptero.h", "FRAME_RECORD"),
    ("BUMP_X_LEFT", "include/ptero.h", "BUMP_X_LEFT"),
    ("BUMP_X_RIGHT", "include/ptero.h", "BUMP_X_RIGHT"),
    ("BUMP_Y", "include/ptero.h", "BUMP_Y"),
    ("BUMP_RECORD", "include/ptero.h", "BUMP_RECORD"),
    ("PT_ANIM_FRAME_MASK", "include/ptero.h", "PT_ANIM_FRAME_MASK"),
    ("PT_ANIM_POSE2", "include/ptero.h", "PT_ANIM_POSE2"),
    ("PT_ANIM_POSE3", "include/ptero.h", "PT_ANIM_POSE3"),
    # ---- the pterodactyl record, which object.h owns for all three layers that read it ----
    ("A_PTERODACTYL_TABLE", "include/object.h", "A_pterodactyl_table"),
    ("A_PTERODACTYL_TABLE_END", "include/object.h", "A_pterodactyl_table_END"),
    ("PT_FLAGS", "include/object.h", "PT_FLAGS"), ("PT_DST", "include/object.h", "PT_DST"),
    ("PT_SRC", "include/object.h", "PT_SRC"), ("PT_SHIFT_W", "include/object.h", "PT_SHIFT_W"),
    # The two LOW-BYTE readings, one off each of the words above — the pair a `_W` typo in
    # stage_ptero_box would swap, which no collision case with a zero shift could see.
    ("PT_SHIFT", "include/object.h", "PT_SHIFT"), ("PT_ROWS", "include/object.h", "PT_ROWS"),
    ("PT_X", "include/object.h", "PT_X"), ("PT_Y", "include/object.h", "PT_Y"),
    ("PT_VX", "include/object.h", "PT_VX"), ("PT_VY", "include/object.h", "PT_VY"),
    ("PT_SPARE", "include/object.h", "PT_SPARE"),
    ("PT_DST_OFF", "include/object.h", "PT_DST_OFF"),
    ("PT_ROWS_W", "include/object.h", "PT_ROWS_W"), ("PT_ANIM", "include/object.h", "PT_ANIM"),
    ("PT_CLIP_WRAPPED", "include/object.h", "PT_CLIP_WRAPPED"),
    ("PT_CLIP_ONSCREEN", "include/object.h", "PT_CLIP_ONSCREEN"),
    ("PT_SWOOP_TIMER", "include/object.h", "PT_SWOOP_TIMER"),
    ("PT_DWELL_TIMER", "include/object.h", "PT_DWELL_TIMER"),
    ("PT_RECORD", "include/object.h", "PT_RECORD"),
    ("PT_FLAG_JUST_SPAWNED", "include/object.h", "PT_FLAG_JUST_SPAWNED"),
    ("PT_FLAG_MOVING_DOWN", "include/object.h", "PT_FLAG_MOVING_DOWN"),
    ("PT_FLAG_MOVING_RIGHT", "include/object.h", "PT_FLAG_MOVING_RIGHT"),
    ("PT_FLAG_LEAVING", "include/object.h", "PT_FLAG_LEAVING"),
    ("PT_FLAG_DYING", "include/object.h", "PT_FLAG_DYING"),
    ("PT_FLAG_IN_PLAY", "include/object.h", "PT_FLAG_IN_PLAY"),
    ("PTERO_BOX_COLS", "include/object.h", "PTERO_BOX_COLS"),
    # ---- everything else, by the header that owns it ----
    ("A_PLATFORM_PRESENT", "include/object.h", "A_platform_present"),
    ("A_GAME_PHASE", "include/object.h", "A_game_phase"),
    ("A_PTERO_SPAWN_COUNT", "include/object.h", "A_ptero_spawn_count"),
    ("A_HIT_BOX_A", "include/object.h", "A_hit_box_a"),
    ("A_HIT_BOX_B", "include/object.h", "A_hit_box_b"),
    ("A_HIT_ROWS", "include/object.h", "A_hit_rows"),
    ("A_COLLISION_HIT", "include/object.h", "A_collision_hit"),
    ("A_MESSAGE_TABLE", "include/object.h", "A_message_table"),
    ("A_PLATFORM_SPRITES", "include/object.h", "A_platform_sprites"),
    ("MSG_RECORD", "include/object.h", "MSG_RECORD"),
    ("MSG_KIND", "include/object.h", "MSG_KIND"),
    ("MSG_SCREEN_PTR", "include/object.h", "MSG_SCREEN_PTR"),
    ("PSPR_RECORD", "include/object.h", "PSPR_RECORD"),
    ("PSPR_PRESENT", "include/object.h", "PSPR_PRESENT"),
    ("PSPR_ROWS", "include/object.h", "PSPR_ROWS"),
    ("PSPR_COLS", "include/object.h", "PSPR_COLS"),
    ("PSPR_SRC", "include/object.h", "PSPR_SRC"),
    ("PSPR_DST_OFF", "include/object.h", "PSPR_DST_OFF"),
    ("MSG_TIMER", "include/score.h", "MSG_TIMER"),
    ("MSG_COLOR", "include/score.h", "MSG_COLOR"),
    ("MSG_SHIFT", "include/score.h", "MSG_SHIFT"),
    ("MSG_STRING", "include/score.h", "MSG_STRING"),
    ("A_PTERO_WAVE_COUNTDOWN", "include/wave.h", "A_ptero_wave_countdown"),
    ("A_SPAWN_INTERVAL", "include/wave.h", "A_spawn_interval"),
    ("A_SPAWN_TIMER", "include/wave.h", "A_spawn_timer"),
    ("A_ACTIVE_PLAYERS", "include/objects.h", "A_active_players"),
    ("A_DRAW_CLIP_CELL0", "include/draw.h", "A_draw_clip_cell0"),
    ("A_DRAW_DST_OFF", "include/draw.h", "A_draw_dst_off"),
    ("A_PLAYER2", "include/draw.h", "A_player2"),
    ("A_SND_PRIORITY", "include/sound.h", "A_snd_priority"),
    ("SND_PTERO_CRY", "include/sound.h", "SND_PTERO_CRY"),
    ("A_SCREEN_BASE", "include/addrs.h", "A_screen_base"),
    ("A_RNG_PTR", "include/addrs.h", "A_rng_ptr"),
    ("A_OBJECT_TABLE", "include/addrs.h", "A_object_table"),
    ("A_DRAW_DST", "include/addrs.h", "A_draw_dst"),
    ("A_DRAW_SRC", "include/addrs.h", "A_draw_src"),
    ("A_DRAW_SHIFT", "include/addrs.h", "A_draw_shift"),
    ("A_DRAW_ROWS", "include/addrs.h", "A_draw_rows"),
    ("OBJ_Y", "include/joust.h", "OBJ_Y"),
    ("SCREEN_ROW_BYTES", "include/joust.h", "SCREEN_ROW_BYTES"),
    ("CELL_BYTES", "include/joust.h", "CELL_BYTES"),
    ("CELL_PIXELS", "include/joust.h", "CELL_PIXELS"),
    ("PTERO_SWOOP_TIMER_SET", "src/object.c", "PTERO_SWOOP_TIMER_SET"),
    # ---- the driver's own values ----
    ("SPAWN_TIMER_MARGIN", "src/ptero.c", "SPAWN_TIMER_MARGIN"),
    ("PTERO_Y_MAX", "src/ptero.c", "PTERO_Y_MAX"),
    ("PTERO_ENTRY_SPEED", "src/ptero.c", "PTERO_ENTRY_SPEED"),
    ("PTERO_ENTRY_FADE", "src/ptero.c", "PTERO_ENTRY_FADE"),
    ("PTERO_SPRITE_LEFTWARD", "src/ptero.c", "PTERO_SPRITE_LEFTWARD"),
    ("PTERO_SPRITE_RIGHTWARD", "src/ptero.c", "PTERO_SPRITE_RIGHTWARD"),
    ("PTERO_FACING_STRIDE", "src/ptero.c", "PTERO_FACING_STRIDE"),
    ("PTERO_ENTRY_DST_LEFTWARD", "src/ptero.c", "PTERO_ENTRY_DST_LEFTWARD"),
    ("PTERO_ENTRY_DST_RIGHTWARD", "src/ptero.c", "PTERO_ENTRY_DST_RIGHTWARD"),
    ("PTERO_ENTRY_X_RIGHTWARD", "src/ptero.c", "PTERO_ENTRY_X_RIGHTWARD"),
    ("PTERO_BOUNCE_SPEED", "src/ptero.c", "PTERO_BOUNCE_SPEED"),
    ("PLATFORM_PRESENT_SET", "src/ptero.c", "PLATFORM_PRESENT_SET"),
    ("PTERO_DEATH_POSE_FRAMES", "src/ptero.c", "PTERO_DEATH_POSE_FRAMES"),
    ("PTERO_DEATH_CLIP", "src/ptero.c", "PTERO_DEATH_CLIP"),
    ("PTERO_BOUNTY_KIND", "src/ptero.c", "PTERO_BOUNTY_KIND"),
    ("PTERO_BOUNTY_COLOR", "src/ptero.c", "PTERO_BOUNTY_COLOR"),
    ("PTERO_BOUNTY_FRAMES", "src/ptero.c", "PTERO_BOUNTY_FRAMES"),
    ("PTERO_BOUNTY_Y_BIAS", "src/ptero.c", "PTERO_BOUNTY_Y_BIAS"),
    ("PTERO_BOUNTY_X_BIAS", "src/ptero.c", "PTERO_BOUNTY_X_BIAS"),
    ("PTERO_CROWD_X", "src/ptero.c", "PTERO_CROWD_X"),
    ("PTERO_CROWD_Y", "src/ptero.c", "PTERO_CROWD_Y"),
    ("PTERO_CROWD_STEP", "src/ptero.c", "PTERO_CROWD_STEP"),
    ("PTERO_LEAVE_SPEED", "src/ptero.c", "PTERO_LEAVE_SPEED"),
    ("PTERO_EXIT_COLUMN_SIZE", "src/ptero.c", "PTERO_EXIT_COLUMN_SIZE"),
    ("PTERO_EXIT_COLUMN_LAST", "src/ptero.c", "PTERO_EXIT_COLUMN_LAST"),
    ("PTERO_EXIT_FADE", "src/ptero.c", "PTERO_EXIT_FADE"),
    ("PTERO_EXIT_RELEASE", "src/ptero.c", "PTERO_EXIT_RELEASE"),
    ("PTERO_EXIT_HOLD", "src/ptero.c", "PTERO_EXIT_HOLD"),
    ("PTERO_CRUISE_SPEED", "src/ptero.c", "PTERO_CRUISE_SPEED"),
    ("PTERO_DIVE_SPEED", "src/ptero.c", "PTERO_DIVE_SPEED"),
    ("PTERO_CLIMB_STEP", "src/ptero.c", "PTERO_CLIMB_STEP"),
    ("PTERO_DWELL_FRAMES", "src/ptero.c", "PTERO_DWELL_FRAMES"),
    ("PT_ANIM_STEP", "src/ptero.c", "PT_ANIM_STEP"),
    ("PTERO_WRAP_ONE_CELL", "src/ptero.c", "PTERO_WRAP_ONE_CELL"),
    ("PTERO_WRAP_TWO_CELLS", "src/ptero.c", "PTERO_WRAP_TWO_CELLS"),
)


def test_mirrored_constants_match_their_sources():
    """Every value this module restates is pinned to the ONE file that owns it. A drift here is
    invisible to the differential itself: a staged input would land at a dead address, both cores
    would agree on the game's own untouched data, and the case would go green proving nothing."""
    sources = {}
    for mirror, path, name in MIRRORED:
        sources.setdefault(path, _defines(path))
        assert name in sources[path], f"{path} defines no {name}"
        assert sources[path][name] == globals()[mirror], \
            f"{mirror} ({globals()[mirror]:#x}) is not {path}'s {name} ({sources[path][name]:#x})"


def test_the_two_sprite_sets_are_one_facing_stride_apart():
    """The build's two immediates and the draw pass's `addi.l #$180` are the same relationship, so a
    transcribed digit in any of the three fails here rather than passing as layout."""
    body = _defines("src/ptero.c")
    assert body["PTERO_SPRITE_RIGHTWARD"] - body["PTERO_SPRITE_LEFTWARD"] == \
        body["PTERO_FACING_STRIDE"]


def test_the_entry_addresses_are_the_birds_own_lane():
    """Both are PTERO_Y_MAX scanlines down; the rightward one is sixteen cells further along."""
    body, joust_h = _defines("src/ptero.c"), _defines("include/joust.h")
    row = body["PTERO_Y_MAX"] * joust_h["SCREEN_ROW_BYTES"]
    assert body["PTERO_ENTRY_DST_LEFTWARD"] == row
    assert body["PTERO_ENTRY_DST_RIGHTWARD"] == row + 16 * joust_h["CELL_BYTES"]


def test_the_wrap_bounds_are_whole_cells_from_the_end_of_the_scanline():
    """PTERO_WRAP_ONE_CELL is where the bird's third cell falls off the scanline and
    PTERO_WRAP_TWO_CELLS where its second does — one and two cells short of the playfield width."""
    body, joust_h = _defines("src/ptero.c"), _defines("include/joust.h")
    width = joust_h["SCREEN_ROW_BYTES"] // joust_h["CELL_BYTES"] * joust_h["CELL_PIXELS"]
    assert width == PLAYFIELD_WIDTH, "this module's mirror of the playfield width has drifted"
    assert body["PTERO_WRAP_TWO_CELLS"] == width - joust_h["CELL_PIXELS"]
    assert body["PTERO_WRAP_ONE_CELL"] == width - 2 * joust_h["CELL_PIXELS"]


def test_the_frame_table_ends_where_the_bump_table_starts():
    """Four poses of FRAME_RECORD bytes, then eight bump records of BUMP_RECORD bytes, then
    ptero_avoid_platform's code — so both table lengths are pinned by what follows them."""
    assert A_PTERO_BUMP_TABLE - A_PTERO_FRAME_TABLE == 4 * FRAME_RECORD
    assert A_PTERO_AVOID_PLATFORM - A_PTERO_BUMP_TABLE == N_PLATFORMS * BUMP_RECORD
    assert harness.NAME_MAP.get(A_PTERO_AVOID_PLATFORM) == "ptero_avoid_platform"
