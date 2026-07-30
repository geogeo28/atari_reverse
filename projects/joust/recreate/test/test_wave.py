"""Differential tests for Joust's wave director (src/wave.c): wave_manager @ 0x1783c.

One entry, 2660 bytes over two code chunks — the dispatcher at 0x1783c and the wave-start body at
0x17012, which nothing else ever branches to. Every path ends in `rts`, so nothing here needs a
`stop_pc` checkpoint, and every routine it calls (find_free_message, score_update_p1/_p2,
rng_advance) is already verified.

`poison=True` is OFF everywhere here but ONE case, and the reason is MEASURED rather than assumed:
the bytes this routine writes are the very bytes it branches on next time — game_phase, the four
special-wave latches, wave_num, the three rider counts — so the attribution pass's inverted image is
a DIFFERENT case, not a check of the case it was asked about. Inverting a game_phase of 2 to 0xfd,
for instance, sends the re-run down the held path instead of the bonus path, and inverting a latch
that has just fired makes it 0xfe, which fires nothing.

The exception is the full-message-table banner case, where the twelve bytes that matter land at
0..0xb — the vector page the original scribbles on when find_free_message hands back 0 — and steer
nothing whatever; the poisoned game_phase still routes to the same announce path (measured at the
case itself).

In poison's place every battery pre-fills what the routine must write with UNWRITTEN, so a write the
candidate skips shows up as a plain diff rather than as a coincidental match on a zeroed image.
Message slots are the one place that filler has to stop short: MSG_KIND must be 0 for the slot to be
free, so only the other eleven bytes of each record carry it. The batteries whose path writes
NOTHING assert that emptiness directly instead.

Two of the cases below exist because a mutation sweep over sixteen disarmed guards found them
missing: the type counts staged at exactly 0x80 (the `subq.b`/`bge` N == V rule), and the survival
banner's recolour, whose ORDER an image diff cannot see until the HUD row is aimed at the banner's
own record.
"""
import ctypes
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin section at the end

# ---- entry point (Ghidra address; ../../names.txt) ----
ENTRY_WAVE_MANAGER = 0x1783c

# ---- globals (mirrors of include/wave.h, world.h, object.h, egg.h, score.h, draw.h, addrs.h) ----
A_PLAYERS_ALIVE = 0x10cf2
A_WAVE_NUM = 0x10cf3
A_WAVE_NUM_TEXT = 0x10cf4
A_WAVE_NUM_TENS = 0x10cf6
A_WAVE_NUM_UNITS = 0x10cf7
A_PLATFORM_PRESENT = 0x10cfa
A_EGG_WAVE_COUNTDOWN = 0x10d02
A_TEAM_WAVE_COUNTDOWN = 0x10d03
A_PTERO_WAVE_COUNTDOWN = 0x10d04
A_GLADIATOR_WAVE_COUNTDOWN = 0x10d05
A_PLAYER_CONFLICT_FLAG = 0x10d06
A_FIRST_DISMOUNT_OWNER = 0x10d07
A_GAME_PHASE = 0x10d08
A_LIVE_OBJECT_COUNT = 0x10d0a
A_EGG_COUNT = 0x10d0b
A_RESPAWN_LOCK = 0x10d13
A_SPAWN_POINT_CURSOR = 0x10d14
A_SND_PRIORITY = 0x10d4c
A_WAVE_LAYOUT_MASK = 0x10d54
A_WAVE_TYPE1_COUNT = 0x10d55
A_WAVE_TYPE2_COUNT = 0x10d56
A_WAVE_TYPE3_COUNT = 0x10d57
A_SPEED_TYPE1 = 0x10d58
A_SPEED_TYPE2 = 0x10d5a
A_SPEED_TYPE3 = 0x10d5c
A_CHASERS_P1 = 0x10d5e
A_FLOOR_STEP_TIMER = 0x10d64
A_FLOOR_ROWS_LEFT = 0x10d65
A_GROUND_ANIM = 0x10d68
A_FLAP_DELAY = 0x10ddc
A_SCREEN_BASE = 0x10dde
A_DRAW_X = 0x10dec
A_SPAWN_INTERVAL = 0x10dfa
A_SPAWN_TIMER = 0x10dfc
A_RNG_PTR = 0x10dfe
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36
A_PLAYER2 = 0x10f84
A_ENEMY_OBJECTS = 0x10fd2
A_EFFECT_TABLE = 0x1137a
A_PTERODACTYL_TABLE = 0x113ba
A_PTERODACTYL_TABLE_END = 0x1143a
A_PLATFORM_TABLE = 0x117b4
A_SPAWN_POINTS = 0x11964
A_WAVE_LAYOUT_TABLE = 0x11b58
A_EGG_SPREAD_SCRATCH = 0x17e7a
A_EGG_SPRITE_STILL = 0x1899a

# ---- the banner strings, in the order src/wave.c declares them ----
STR_PREPARE_TO_JOUST = 0x18429
STR_BUZZARD_BAIT = 0x1843c
STR_WAVE = 0x1844c
STR_SURVIVAL_WAVE = 0x18453
STR_TEAM_WAVE = 0x18463
STR_TEAM_PLAY_BONUS = 0x1846f
STR_GLADIATOR_WAVE = 0x1848d
STR_BOUNTY_OFFER = 0x1849e
STR_DISMOUNT_FIRST = 0x184b6
STR_EGG_WAVE = 0x184d1
STR_PTERODACTYL_WAVE = 0x184dc
STR_BEWARE_PTERO = 0x184ef
STR_CO_OPERATION = 0x18517
STR_PLAYER_CONFLICT = 0x18542
STR_SURVIVAL_BONUS = 0x18567
STR_NO_BONUS = 0x18586
STR_NO_BOUNTY = 0x18599
STR_BOUNTY_COLLECTED = 0x185ad

# ---- record geometry ----
MSG_RECORD, N_MESSAGES = 0xc, 24
MSG_KIND, MSG_TIMER, MSG_COLOR, MSG_SHIFT, MSG_SCREEN_PTR, MSG_STRING = 0, 1, 2, 3, 4, 8
PT_RECORD = 0x20
N_PTEROS = (A_PTERODACTYL_TABLE_END - A_PTERODACTYL_TABLE) // PT_RECORD
OBJ_SIZE = 0x4e
N_ENEMIES = (A_EFFECT_TABLE - A_ENEMY_OBJECTS) // OBJ_SIZE
OBJ_FLAGS = 0x00
OBJ_EGG_STATE = 0x1e
OBJ_EGG_HATCH_TIMER = 0x1f
OBJ_EGG_X, OBJ_EGG_Y = 0x20, 0x22
OBJ_EGG_ROLL_TIMER, OBJ_EGG_FALL_TIMER = 0x28, 0x29
OBJ_EGG_DST, OBJ_EGG_SRC = 0x2a, 0x2e
OBJ_EGG_ROWS = 0x32
OBJ_EGG_SPAWN_FLAGS = 0x34
OBJ_EGG_CHAIN = 0x35
OBJ_SCORE_PTR, OBJ_SCORE_SHIFT = 0x36, 0x3a
OBJ_SCORE_TEXT, OBJ_SCORE_FIRST_DIGIT, OBJ_SCORE_LIFE_DIGIT = 0x3c, 0x3e, 0x41
OBJ_LIVES = 0x4c
EFF_RECORD, EFF_KIND = 0x10, 0x2
N_EFFECTS = (A_PTERODACTYL_TABLE - A_EFFECT_TABLE) // EFF_RECORD
PLAT_RECORD, PLAT_Y0, PLAT_X0, PLAT_X1 = 0x8, 0x0, 0x4, 0x6
N_PLATFORMS = 8
GA_ROWS_LATCH, GA_ROWS, GA_FLAME_LEFT, GA_FLAME_RIGHT, GA_BLOCK_BYTES = 0, 2, 4, 0x10, 0x1c
SPR_SRC, SPR_DST_OFF, SPR_SHIFT, SPR_CELL_SELECT = 0x0, 0x4, 0x8, 0xa
SCREEN_ROW_BYTES = 0xa0
CELL_BYTES = 8

# ---- the values src/wave.c names ----
WAVE_PHASE_ANNOUNCE, WAVE_PHASE_BONUS = 1, 2
BANNER_FRAMES = 0x64
BANNER_COLOR_P1 = 7   # player.h's — the survival bonus is recoloured to it
BUZZARD_BAIT_CUE = 0x4b
SPECIAL_WAVE_LEAD = 5
WAVE_BONUS_THOUSANDS = 3
WAVE_NUM_WRAP, WAVE_NUM_WRAP_TO = 0x33, 0x29
FLOOR_ROWS_PER_WAVE, FLOOR_STEP_FRAMES = 5, 7
RIDER_SPEED_MAX = 4
GROUND_BURN_ROW = 185
FLAME_FRAME_FIRST, FLAME_FRAME_BYTES = 0x18636, 0xd8
SPAWN_INTERVAL_BASE = 0x640
PTERO_IMMEDIATE_TIMER = 0x30
EGG_SPREAD_RECORD = 4
OBJ_FLAG_RESPAWN, OBJ_FLAG_FACING_RIGHT = 1 << 7, 0x8000

# ---- scratch areas, clear of the program (ends 0x2b7ae), of abi's stub space (0x40000..0x40207),
# of the staged-file table (0xbf000) and of the stack guard. ----
SCREEN = 0x70000
SCREEN_ALT = 0x80000     # a second framebuffer, so screen_base is read rather than assumed
SCREEN_BYTES = 0x8000

UNWRITTEN = 0x5a         # pre-filled into everything the routine must write
SND_PRIORITY_IDLE = 0x10 # nothing playing (mirror of src/sound.c)

# The four platform boxes the placement tests stage: distinct rows, distinct and NON-ZERO widths
# (a zero-width platform is a 68000 divide-by-zero exception, so it is out of reach of the
# differential on either side and is deliberately never staged).
FUZZ_CHUNKS = 4

_U8P = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_wave_manager.argtypes = [_U8P]
harness._lib.g_wave_manager.restype = None


# ------------------------------------------------------------------ shared staging helpers

def _message_table(free=N_MESSAGES, kinds=None):
    """The whole 24-slot table. `free` says how many LEADING slots are free; the rest are taken.

    Only MSG_KIND decides whether a slot is free, so the other eleven bytes of every record carry
    UNWRITTEN — a banner the candidate fails to write then shows as a diff instead of matching a
    zeroed slot by accident.
    """
    table = bytearray()
    for slot in range(N_MESSAGES):
        record = bytearray([UNWRITTEN] * MSG_RECORD)
        record[MSG_KIND] = 0 if slot < free else (kinds[slot] if kinds else 0xf0 + slot % 8)
        table += record
    return bytes(table)


def _base_pokes(screen_base=SCREEN, free=N_MESSAGES, kinds=None):
    """A quiet, fully controlled starting state: no messages posted, no pterodactyls in the air."""
    return {
        A_SCREEN_BASE: struct.pack(">I", screen_base),
        A_MESSAGE_TABLE: _message_table(free, kinds),
        A_PTERODACTYL_TABLE: bytes(N_PTEROS * PT_RECORD),
        A_GAME_PHASE: bytes([WAVE_PHASE_ANNOUNCE]),
        A_WAVE_NUM: bytes([1]),
        A_PLAYERS_ALIVE: bytes([1]),
        A_EGG_WAVE_COUNTDOWN: bytes([9, 9, 9, 9]),   # the four latches, none of them due
        A_GROUND_ANIM: bytes(GA_BLOCK_BYTES),
    }


def _wave_case(pokes, poison=False, max_insns=200_000, note=""):
    diffs, info = differential(ENTRY_WAVE_MANAGER, {"_pokes": pokes},
                               lambda lib, buf: lib.g_wave_manager(buf),
                               poison=poison, max_insns=max_insns)
    assert not diffs, f"{note}\n{report(diffs)}"
    return info


def _image_writes(info):
    """The oracle's write set with its own machine stack dropped — a `jsr` pushes a return address
    the C reconstruction has no analogue for, and the differential already excludes that band."""
    return {addr: value for addr, value in info["writes"].items() if addr < emu.STACK_GUARD_LO}


def _banner_slots(info):
    """{slot index: {field: byte}} for every message record the oracle wrote."""
    posted = {}
    for addr, value in info["writes"].items():
        if not A_MESSAGE_TABLE <= addr < A_MESSAGE_TABLE + N_MESSAGES * MSG_RECORD:
            continue
        slot, field = divmod(addr - A_MESSAGE_TABLE, MSG_RECORD)
        posted.setdefault(slot, {})[field] = value
    return posted


def _slot_of(info, string):
    """The message slot the banner carrying `string` was posted into."""
    for slot, fields in _banner_slots(info).items():
        if all(off in fields for off in range(MSG_STRING, MSG_STRING + 4)) and \
                int.from_bytes(bytes(fields[MSG_STRING + n] for n in range(4)), "big") == string:
            return slot
    raise AssertionError(f"no banner carrying {string:#x} was posted")


def _posted_strings(info):
    """The MSG_STRING longword of every banner the oracle posted, in slot order."""
    out = []
    for slot, fields in sorted(_banner_slots(info).items()):
        if not all(off in fields for off in range(MSG_STRING, MSG_STRING + 4)):
            continue
        out.append(int.from_bytes(bytes(fields[MSG_STRING + n] for n in range(4)), "big"))
    return out


# ==================================================================================================
# Phase A — the dispatcher @ 0x1783c: what holds the countdown, and what lets it run.
# ==================================================================================================

def test_phase_0_routes_to_the_end_of_wave_test():
    """game_phase 0 means the wave is being played, and the only question is whether it is over."""
    pokes = _base_pokes()
    pokes[A_GAME_PHASE] = bytes([0])
    pokes[A_EGG_COUNT] = bytes([1])          # an egg is still on the board, so nothing happens
    info = _wave_case(pokes, note="phase 0, an egg left")
    assert not _image_writes(info), "an unfinished wave writes nothing at all"


@pytest.mark.parametrize("phase", (1, 2, 3, 0x7f, 0x80, 0xff))
def test_countdown_runs_when_nothing_holds_it(phase):
    """Any non-zero phase counts down by one. Only 1 -> 0 starts a wave; the rest just announce."""
    pokes = _base_pokes()
    pokes[A_GAME_PHASE] = bytes([phase])
    pokes[A_WAVE_NUM] = bytes([2])           # not wave 3, so the ground-burn hold cannot apply
    _wave_case(pokes, note=f"phase={phase:#x}")


@pytest.mark.parametrize("slot", (0, 1, 12, 23))
@pytest.mark.parametrize("phase", (1, 2))
def test_a_message_of_the_current_generation_holds_the_countdown(slot, phase):
    """game_phase doubles as a message GENERATION tag: the scan compares MSG_KIND against it, so a
    banner of THIS generation anywhere in the 24 slots freezes the countdown."""
    kinds = [0] * N_MESSAGES
    kinds[slot] = phase
    pokes = _base_pokes(free=0, kinds=kinds)
    pokes[A_GAME_PHASE] = bytes([phase])
    pokes[A_WAVE_NUM] = bytes([2])
    info = _wave_case(pokes, note=f"slot={slot} phase={phase}")
    assert not _image_writes(info), "the held path with the wrong wave number writes nothing"


@pytest.mark.parametrize("kind", (0, 1, 2, 3, 0xff))
def test_only_the_matching_generation_holds(kind):
    """A message of ANOTHER generation — including the persistent kind 3 — does not hold phase 2."""
    kinds = [0] * N_MESSAGES
    kinds[5] = kind
    pokes = _base_pokes(free=0, kinds=kinds)
    pokes[A_GAME_PHASE] = bytes([WAVE_PHASE_BONUS])
    pokes[A_WAVE_NUM] = bytes([2])
    _wave_case(pokes, note=f"kind={kind:#x}")


@pytest.mark.parametrize("slot", range(4))
def test_a_pterodactyl_in_the_air_holds_the_countdown(slot):
    """The second scan walks all four pterodactyl slots at PT_RECORD stride; a non-zero flags word
    in any of them holds. A stride error shows as a slot that fails to hold."""
    table = bytearray(N_PTEROS * PT_RECORD)
    struct.pack_into(">H", table, slot * PT_RECORD, 0x0001)
    pokes = _base_pokes()
    pokes[A_PTERODACTYL_TABLE] = bytes(table)
    pokes[A_WAVE_NUM] = bytes([2])
    info = _wave_case(pokes, note=f"ptero slot={slot}")
    assert not _image_writes(info), "a pterodactyl still in the air freezes everything"


@pytest.mark.parametrize("latch", (0, 1, 2, 0x7fff, 0x8000, 0xffff))
@pytest.mark.parametrize("wave", (2, 3, 4))
def test_the_ground_burn_holds_only_on_wave_3_and_only_while_positive(latch, wave):
    """`cmpi.b #3,wave_num` then `tst.w` + `bgt` on the burn's row latch — a SIGNED word test, so
    0x8000 and 0xffff do NOT hold. Wave 4 runs the same burn but is not consulted here."""
    ground = bytearray(GA_BLOCK_BYTES)
    struct.pack_into(">H", ground, GA_ROWS_LATCH, latch)
    pokes = _base_pokes()
    pokes[A_GROUND_ANIM] = bytes(ground)
    pokes[A_WAVE_NUM] = bytes([wave])
    _wave_case(pokes, note=f"wave={wave} latch={latch:#x}")


# ==================================================================================================
# Phase B — "BUZZARD BAIT!" @ 0x17ba8: the one thing that happens while the countdown is held.
# ==================================================================================================

def _held_pokes(**over):
    """A held countdown on wave 0 with the PREPARE banner in slot 0 at its cue timer."""
    kinds = [0] * N_MESSAGES
    kinds[0] = WAVE_PHASE_ANNOUNCE
    pokes = _base_pokes(free=0, kinds=kinds)
    pokes[A_GAME_PHASE] = bytes([WAVE_PHASE_ANNOUNCE])
    pokes[A_WAVE_NUM] = bytes([0])
    table = bytearray(pokes[A_MESSAGE_TABLE])
    table[MSG_TIMER] = BUZZARD_BAIT_CUE
    for slot in range(1, N_MESSAGES):
        table[slot * MSG_RECORD + MSG_KIND] = 0          # ...and the rest of the table free again
    pokes[A_MESSAGE_TABLE] = bytes(table)
    pokes.update(over)
    return pokes


def test_buzzard_bait_is_posted_at_the_cue():
    """It goes up when slot 0's timer has counted down to exactly BUZZARD_BAIT_CUE, and inherits
    that same timer so the two banners clear together."""
    info = _wave_case(_held_pokes(), note="the cue")
    assert _posted_strings(info) == [STR_BUZZARD_BAIT], "the buzzard-bait banner was not posted"
    posted = _banner_slots(info)[1]
    assert posted[MSG_TIMER] == BUZZARD_BAIT_CUE
    assert posted[MSG_KIND] == WAVE_PHASE_ANNOUNCE


@pytest.mark.parametrize("timer", (0, 1, BUZZARD_BAIT_CUE - 1, BUZZARD_BAIT_CUE + 1, 0x64, 0xff))
def test_buzzard_bait_needs_the_exact_cue_timer(timer):
    """`cmpi.b #$4b,1(a0)` is an equality test on slot 0's timer, not a threshold."""
    pokes = _held_pokes()
    table = bytearray(pokes[A_MESSAGE_TABLE])
    table[MSG_TIMER] = timer
    pokes[A_MESSAGE_TABLE] = bytes(table)
    info = _wave_case(pokes, note=f"timer={timer:#x}")
    assert (_posted_strings(info) == [STR_BUZZARD_BAIT]) == (timer == BUZZARD_BAIT_CUE)


@pytest.mark.parametrize("wave", (0, 1, 2, 0xff))
def test_buzzard_bait_is_the_first_waves_alone(wave):
    pokes = _held_pokes()
    pokes[A_WAVE_NUM] = bytes([wave])
    info = _wave_case(pokes, note=f"wave={wave:#x}")
    assert (_posted_strings(info) == [STR_BUZZARD_BAIT]) == (wave == 0)


@pytest.mark.parametrize("phase", (1, 2, 3, 0xff))
def test_buzzard_bait_only_during_the_announce_generation(phase):
    """The hold is whatever matches game_phase; the post is gated on the phase being exactly 1."""
    kinds = [0] * N_MESSAGES
    kinds[0] = phase
    pokes = _held_pokes()
    pokes[A_GAME_PHASE] = bytes([phase])
    table = bytearray(pokes[A_MESSAGE_TABLE])
    table[MSG_KIND] = phase
    pokes[A_MESSAGE_TABLE] = bytes(table)
    info = _wave_case(pokes, note=f"phase={phase:#x}")
    assert (_posted_strings(info) == [STR_BUZZARD_BAIT]) == (phase == WAVE_PHASE_ANNOUNCE)


def test_buzzard_bait_checks_the_slot_it_was_given():
    """One of only two posts in the whole routine that tests find_free_message's answer: with the
    table full it writes NOTHING, where an unguarded post would scribble on the vector page."""
    pokes = _held_pokes()
    table = bytearray(pokes[A_MESSAGE_TABLE])
    for slot in range(N_MESSAGES):
        table[slot * MSG_RECORD + MSG_KIND] = WAVE_PHASE_ANNOUNCE
    table[MSG_TIMER] = BUZZARD_BAIT_CUE
    pokes[A_MESSAGE_TABLE] = bytes(table)
    info = _wave_case(pokes, note="full table")
    assert not _image_writes(info), "a full table must leave the vector page alone on THIS path"


# ==================================================================================================
# Phase C — announcing the coming wave @ 0x178a4: the banners posted on the 2 -> 1 tick.
# ==================================================================================================

# The latches, in the order the announce half takes them down. A latch at 1 fires on this tick.
LATCHES = (A_EGG_WAVE_COUNTDOWN, A_TEAM_WAVE_COUNTDOWN,
           A_PTERO_WAVE_COUNTDOWN, A_GLADIATOR_WAVE_COUNTDOWN)
LATCH_IDLE = 9


def _announce_pokes(wave=1, players=1, latches=(LATCH_IDLE,) * 4, free=N_MESSAGES, **over):
    """A countdown tick with nothing holding it: game_phase 2 -> 1, so the banners go up."""
    pokes = _base_pokes(free=free)
    pokes[A_GAME_PHASE] = bytes([WAVE_PHASE_BONUS])
    pokes[A_WAVE_NUM] = bytes([wave])
    pokes[A_PLAYERS_ALIVE] = bytes([players])
    pokes[A_EGG_WAVE_COUNTDOWN] = bytes(latches)      # the four are contiguous, 0x10d02..0x10d05
    pokes[A_PLAYER_CONFLICT_FLAG] = bytes([UNWRITTEN, UNWRITTEN])   # ...and the two flags after them
    pokes.update(over)
    return pokes


def _announce(note="", **kwargs):
    return _wave_case(_announce_pokes(**kwargs), note=note or str(kwargs))


def test_announce_posts_the_wave_number_every_tick():
    """The label and the number are the two banners every countdown tick puts up."""
    info = _announce(wave=1)
    assert _posted_strings(info) == [STR_WAVE, A_WAVE_NUM_TEXT]
    assert _image_writes(info)[A_GAME_PHASE] == WAVE_PHASE_ANNOUNCE


def test_announce_wave_0_writes_prepare_to_joust_into_slot_0_directly():
    """Wave 0 does NOT go through find_free_message for its first banner — it writes message slot 0
    whatever is in it, which is why the case stages that slot as taken."""
    kinds = [0] * N_MESSAGES
    kinds[0] = 0x77                        # occupied, and not the current generation, so no hold
    pokes = _announce_pokes(wave=0, free=0)
    pokes[A_MESSAGE_TABLE] = _message_table(free=0, kinds=kinds)
    info = _wave_case(pokes, note="wave 0, slot 0 taken")
    assert _posted_strings(info) == [STR_PREPARE_TO_JOUST, STR_WAVE, A_WAVE_NUM_TEXT]


@pytest.mark.parametrize("wave", (0, 1, 8, 9, 10, 0x7f, 0x80, 0xff))
def test_announce_two_digit_layout_is_a_signed_wave_compare(wave):
    """`cmpi.b #9,wave_num ; blt` picks the label and number shifts, and it is SIGNED — so a wave
    number of 0x80..0xff lays out as ONE digit however large it looks unsigned."""
    info = _announce(wave=wave, note=f"wave={wave:#x}")
    two_digits = (wave ^ 0x80) - 0x80 >= 9
    posted = _banner_slots(info)
    assert posted[_slot_of(info, STR_WAVE)][MSG_SHIFT] == (0x8 if two_digits else 0xb)
    assert posted[_slot_of(info, A_WAVE_NUM_TEXT)][MSG_SHIFT] == (0xe if two_digits else 0x8)


def test_announce_wave_number_checks_the_slot_it_was_given():
    """The wave NUMBER is the second of the routine's only two guarded posts: with one slot left it
    takes it for the LABEL and then declines to write the number at address 0."""
    pokes = _announce_pokes(free=0)
    kinds = [0x77] * N_MESSAGES
    kinds[23] = 0                          # exactly one free slot
    pokes[A_MESSAGE_TABLE] = _message_table(free=0, kinds=kinds)
    info = _wave_case(pokes, note="one free slot")
    assert _posted_strings(info) == [STR_WAVE], "only the label fits; the number must be dropped"
    assert not any(addr < MSG_RECORD for addr in _image_writes(info)), \
        "the guarded post must leave the vector page alone"


def test_announce_with_a_full_table_scribbles_on_the_vector_page():
    """The unguarded posts write their twelve-byte record at address 0 — the bottom of the 68000's
    vector page — exactly as player_death does. Reproduced, not fixed.

    This is the ONE case here that takes the attribution pass, and it earns it: the bytes that
    matter land at 0..0xb and steer nothing at all. MEASURED for the rest of the write set — the
    poisoned game_phase (1 -> 0xfe) still matches no slot kind and still counts down into the
    announce half, and the poisoned latches (0 -> 0xff) simply fire nothing — so the re-run posts
    the same two unguarded banners at the same address.
    """
    pokes = _announce_pokes(free=0, latches=(1, 1, 1, 1), players=2)
    kinds = [0x77] * N_MESSAGES
    pokes[A_MESSAGE_TABLE] = _message_table(free=0, kinds=kinds)
    info = _wave_case(pokes, poison=True, note="full table")
    assert _image_writes(info).get(MSG_KIND) == WAVE_PHASE_ANNOUNCE, \
        "the record really must land at address 0"


@pytest.mark.parametrize("value", (0, 1, 2, 0x80, 0xff))
@pytest.mark.parametrize("index", range(4))
def test_announce_each_latch_counts_down_by_one(value, index):
    """`subq.b` on each latch: only a latch that lands on exactly 0 announces, and a latch of 0
    wraps to 0xff — 256 ticks from firing, not already spent."""
    latches = [LATCH_IDLE] * 4
    latches[index] = value
    _announce(latches=tuple(latches), players=2, note=f"latch {index} = {value:#x}")


SPECIAL_WAVE_BANNERS = ((0, 1, [STR_EGG_WAVE]),
                        (1, 1, [STR_SURVIVAL_WAVE]),
                        (1, 2, [STR_TEAM_WAVE, STR_TEAM_PLAY_BONUS]),
                        (2, 1, [STR_PTERODACTYL_WAVE, STR_BEWARE_PTERO]),
                        (3, 2, [STR_GLADIATOR_WAVE, STR_BOUNTY_OFFER, STR_DISMOUNT_FIRST]),
                        (3, 1, []))


@pytest.mark.parametrize("index,players,expected", SPECIAL_WAVE_BANNERS)
def test_announce_special_wave_banners(index, players, expected):
    """Each latch announces its own wave as it lands on zero. The team latch picks its wording from
    the number of players still in, and the gladiator latch is announced only to two of them —
    though the latch itself is spent either way."""
    latches = [LATCH_IDLE] * 4
    latches[index] = 1
    info = _announce(latches=tuple(latches), players=players,
                     note=f"latch {index}, players={players}")
    assert _posted_strings(info) == [STR_WAVE, A_WAVE_NUM_TEXT] + expected


def test_announce_team_latch_clears_the_conflict_flag_whatever_the_wording():
    """`clr.b player_conflict_flag` sits BEFORE the two-player branch, so a one-player wave clears
    it too — and the gladiator latch clears first_dismount_owner only inside its own gate."""
    for players in (1, 2):
        latches = [LATCH_IDLE] * 4
        latches[1] = 1
        info = _announce(latches=tuple(latches), players=players)
        assert _image_writes(info).get(A_PLAYER_CONFLICT_FLAG) == 0
        assert A_FIRST_DISMOUNT_OWNER not in _image_writes(info)


@pytest.mark.parametrize("players", (0, 1, 2, 3, 0xff))
def test_announce_gladiator_latch_is_spent_but_only_told_to_two_players(players):
    latches = [LATCH_IDLE] * 4
    latches[3] = 1
    info = _announce(latches=tuple(latches), players=players, note=f"players={players}")
    assert _image_writes(info)[A_GLADIATOR_WAVE_COUNTDOWN] == 0, "the latch is spent either way"
    assert (A_FIRST_DISMOUNT_OWNER in _image_writes(info)) == (players == 2)


def test_announce_all_four_latches_at_once():
    """Nothing stops the four firing on the same tick; the banners then queue up in slot order."""
    info = _announce(latches=(1, 1, 1, 1), players=2)
    assert _posted_strings(info) == [STR_WAVE, A_WAVE_NUM_TEXT, STR_EGG_WAVE,
                                     STR_TEAM_WAVE, STR_TEAM_PLAY_BONUS,
                                     STR_PTERODACTYL_WAVE, STR_BEWARE_PTERO,
                                     STR_GLADIATOR_WAVE, STR_BOUNTY_OFFER, STR_DISMOUNT_FIRST]


@pytest.mark.parametrize("screen_base", (SCREEN, SCREEN + 2, SCREEN + SCREEN_ROW_BYTES, SCREEN_ALT))
def test_announce_banner_addresses_are_offsets_from_screen_base(screen_base):
    """MSG_SCREEN_PTR is screen_base plus the banner's own offset, and screen_base is re-read from
    the image — a candidate that hard-coded the framebuffer passes every other case here."""
    pokes = _announce_pokes(latches=(1, 1, 1, 1), players=2)
    pokes[A_SCREEN_BASE] = struct.pack(">I", screen_base)
    _wave_case(pokes, note=f"screen_base={screen_base:#x}")


# ==================================================================================================
# Phase D — the wave is over @ 0x17c08: arm the next special wave and pay for this one.
# ==================================================================================================

SCORE_COLOR = 7          # the colour the shipped score records carry
TEXT_SET_COLOR = 2       # draw_string's set-colour control byte (mirror of src/draw.c)
N_SCORE_DIGITS = 7
SCORE_ROW_PITCH = 12     # scanlines between the two staged HUD bands
# A settled score whose thousands digit can take WAVE_BONUS_THOUSANDS without carrying, so no case
# here pays an extra life — that is score_update's business and test_score.py's battery.
SETTLED_SCORE = b"  12340"


def _score_record(score_ptr, flags=0, digits=SETTLED_SCORE, lives=1, colour=SCORE_COLOR):
    """One player's object record: everything score_update reads, and UNWRITTEN everywhere else so
    that a field the candidate fails to write shows as a diff rather than matching a zero."""
    record = bytearray([UNWRITTEN] * OBJ_SIZE)
    struct.pack_into(">H", record, OBJ_FLAGS, flags)
    struct.pack_into(">I", record, OBJ_SCORE_PTR, score_ptr)
    struct.pack_into(">H", record, OBJ_SCORE_SHIFT, 0)
    record[OBJ_LIVES] = lives
    record[OBJ_SCORE_TEXT] = TEXT_SET_COLOR
    record[OBJ_SCORE_TEXT + 1] = colour
    record[OBJ_SCORE_FIRST_DIGIT:OBJ_SCORE_FIRST_DIGIT + N_SCORE_DIGITS] = digits
    record[OBJ_SCORE_FIRST_DIGIT + N_SCORE_DIGITS] = 0        # the string's terminator
    return bytes(record)


def _end_of_wave_pokes(players=1, live=None, eggs=0, latches=(LATCH_IDLE,) * 4,
                       conflict=0, owner=0, p1_flags=0, screen_base=SCREEN, extra=None):
    """A finished wave: game_phase 0, no eggs left, and only players still on the playfield."""
    pokes = _base_pokes(screen_base=screen_base)
    pokes[A_GAME_PHASE] = bytes([0])
    pokes[A_PLAYERS_ALIVE] = bytes([players])
    pokes[A_LIVE_OBJECT_COUNT] = bytes([players if live is None else live, eggs])
    pokes[A_EGG_WAVE_COUNTDOWN] = bytes(latches)
    pokes[A_PLAYER_CONFLICT_FLAG] = bytes([conflict, owner])
    pokes[A_SND_PRIORITY] = struct.pack(">H", SND_PRIORITY_IDLE)
    pokes[screen_base] = bytes(range(1, 0x100)) * (SCREEN_BYTES // 0xff)
    pokes[A_OBJECT_TABLE] = _score_record(screen_base + 0x400, flags=p1_flags)
    pokes[A_PLAYER2] = _score_record(screen_base + 0x400 + SCORE_ROW_PITCH * SCREEN_ROW_BYTES)
    pokes.update(extra or {})
    return pokes


def _end_of_wave(note="", **kwargs):
    return _wave_case(_end_of_wave_pokes(**kwargs), note=note or str(kwargs))


@pytest.mark.parametrize("eggs", (0, 1, 0x80, 0xff))
def test_end_of_wave_needs_every_egg_gone(eggs):
    """`tst.b egg_count` is a zero test, not a sign test."""
    info = _end_of_wave(eggs=eggs, latches=(LATCH_IDLE,) * 4, note=f"eggs={eggs:#x}")
    assert (A_GAME_PHASE in _image_writes(info)) == (eggs == 0)


@pytest.mark.parametrize("players,live", ((1, 1), (1, 2), (2, 2), (2, 1), (0, 0), (2, 0), (0xff, 0xff)))
def test_end_of_wave_needs_every_survivor_to_be_a_player(players, live):
    """A plain byte compare of players_alive against live_object_count: while any enemy is still on
    the playfield the two differ and the wave runs on."""
    info = _end_of_wave(players=players, live=live, note=f"players={players} live={live}")
    assert (A_GAME_PHASE in _image_writes(info)) == (players == live)


def test_end_of_wave_moves_to_the_bonus_generation():
    info = _end_of_wave(latches=(LATCH_IDLE,) * 4)
    assert _image_writes(info)[A_GAME_PHASE] == WAVE_PHASE_BONUS


# (armed latch index, latch bytes) — the four are consulted team, egg, ptero, gladiator.
LATCH_ORDER = ((1, (LATCH_IDLE, 0, LATCH_IDLE, LATCH_IDLE)),
               (0, (0, LATCH_IDLE, LATCH_IDLE, LATCH_IDLE)),
               (2, (LATCH_IDLE, LATCH_IDLE, 0, LATCH_IDLE)),
               (3, (LATCH_IDLE, LATCH_IDLE, LATCH_IDLE, 0)))


@pytest.mark.parametrize("armed,latches", LATCH_ORDER)
def test_end_of_wave_arms_exactly_one_latch(armed, latches):
    """Each spent latch is re-armed to SPECIAL_WAVE_LEAD, and the search stops at the first one —
    so the special waves take their turn instead of piling up."""
    info = _end_of_wave(latches=latches, note=f"armed={armed}")
    armed_now = {index for index in range(4)
                 if _image_writes(info).get(LATCHES[index]) == SPECIAL_WAVE_LEAD}
    assert armed_now == {armed}


def test_end_of_wave_arms_the_first_spent_latch_only():
    """With all four spent it is the TEAM latch that wins, because it is tested first."""
    info = _end_of_wave(latches=(0, 0, 0, 0))
    assert _image_writes(info)[A_TEAM_WAVE_COUNTDOWN] == SPECIAL_WAVE_LEAD
    assert A_EGG_WAVE_COUNTDOWN not in _image_writes(info)


def test_end_of_wave_with_nothing_spent_only_moves_the_phase():
    info = _end_of_wave(latches=(LATCH_IDLE,) * 4)
    assert set(_image_writes(info)) == {A_GAME_PHASE}


# ---- the team latch's payout ----

TEAM_ARMED = (LATCH_IDLE, 0, LATCH_IDLE, LATCH_IDLE)


@pytest.mark.parametrize("conflict", (0, 1, 0x80, 0xff))
def test_survival_bonus_is_forfeit_after_a_conflict(conflict):
    """One player left: the survival bonus, unless the two of them fought over it — and the
    conflict flag is a plain zero test."""
    info = _end_of_wave(players=1, latches=TEAM_ARMED, conflict=conflict, p1_flags=4,
                        note=f"conflict={conflict:#x}")
    assert _posted_strings(info) == ([STR_SURVIVAL_BONUS] if conflict == 0 else [STR_NO_BONUS])


@pytest.mark.parametrize("p1_flags", (0, 1, 4, 0x8000, 0xffff))
def test_survival_bonus_goes_to_whichever_player_still_has_a_slot(p1_flags):
    """`tst.w object_table` — player 1's flags WORD. Zero means player 1 is not on the board, so the
    3000 goes to player 2 instead; any non-zero value pays player 1 and recolours the banner."""
    info = _end_of_wave(players=1, latches=TEAM_ARMED, p1_flags=p1_flags,
                        note=f"p1_flags={p1_flags:#x}")
    paid, unpaid = ((A_PLAYER2, A_OBJECT_TABLE) if p1_flags == 0
                    else (A_OBJECT_TABLE, A_PLAYER2))
    assert _image_writes(info)[paid + OBJ_SCORE_LIFE_DIGIT] == ord("2") + WAVE_BONUS_THOUSANDS
    assert unpaid + OBJ_SCORE_LIFE_DIGIT not in _image_writes(info)

    banner = _slot_of(info, STR_SURVIVAL_BONUS)
    expected = BANNER_COLOR_P1 if p1_flags else 2
    assert _banner_slots(info)[banner][MSG_COLOR] == expected


def test_survival_banner_is_recoloured_after_score_update_returns():
    """The recolour only works because score_update saves and restores A0 (`movem.l #$8080,-(a7)`
    / `#$0101`), so the record posted before the call is still to hand after it.

    ORDER is what this case is about, and an image diff cannot normally see order at all — a
    candidate that recoloured BEFORE the call leaves the identical final byte. So player 1's HUD
    row is aimed AT the message table: score_update then paints over the banner's own record, and
    the two orderings differ in what survives (a mutation sweep found this hole — the case that
    only read the colour out of the write set passed either way).
    """
    pokes = _end_of_wave_pokes(players=1, latches=TEAM_ARMED, p1_flags=4)
    pokes[A_OBJECT_TABLE] = _score_record(A_MESSAGE_TABLE, flags=4)
    info = _wave_case(pokes, note="the score row drawn over the banner")

    banner = A_MESSAGE_TABLE      # the table is empty here, so the banner takes slot 0
    written = _image_writes(info)
    assert written[banner + MSG_KIND] == 0xff, "the row really must cover the record"
    assert written[banner + MSG_COLOR] == BANNER_COLOR_P1, \
        "the recolour was overpainted, so it happened BEFORE score_update rather than after"


@pytest.mark.parametrize("conflict", (0, 1))
@pytest.mark.parametrize("players", (2, 3, 0, 0xff))
def test_co_operation_bonus_pays_both_players(conflict, players):
    """Anything other than exactly one player left takes the co-operation branch, which pays 3000
    to BOTH records — or nothing at all if they fought."""
    info = _end_of_wave(players=players, latches=TEAM_ARMED, conflict=conflict, p1_flags=4,
                        note=f"players={players} conflict={conflict}")
    if conflict:
        assert _posted_strings(info) == [STR_PLAYER_CONFLICT]
        assert A_OBJECT_TABLE + OBJ_SCORE_LIFE_DIGIT not in _image_writes(info)
        return
    assert _posted_strings(info) == [STR_CO_OPERATION]
    for slot in (A_OBJECT_TABLE, A_PLAYER2):
        assert _image_writes(info)[slot + OBJ_SCORE_LIFE_DIGIT] == ord("2") + WAVE_BONUS_THOUSANDS


# ---- the gladiator latch's bounty ----

GLADIATOR_ARMED = (LATCH_IDLE, LATCH_IDLE, LATCH_IDLE, 0)


@pytest.mark.parametrize("owner,expected", ((0, [STR_NO_BOUNTY]), (1, [STR_BOUNTY_COLLECTED]),
                                            (2, [STR_BOUNTY_COLLECTED]),
                                            (0x7f, [STR_BOUNTY_COLLECTED]),
                                            (0x80, [STR_NO_BOUNTY]), (0xff, [STR_NO_BOUNTY])))
def test_bounty_owner_is_a_signed_byte(owner, expected):
    """`cmpi.b #1 ; beq` then `bgt` — SIGNED, so 0x80..0xff read as "nobody" and take the same
    branch as 0. The two winners share one string and differ only in where and how it is drawn."""
    info = _end_of_wave(players=2, latches=GLADIATOR_ARMED, owner=owner, note=f"owner={owner:#x}")
    assert _posted_strings(info) == expected
    if expected == [STR_BOUNTY_COLLECTED]:
        banner = _banner_slots(info)[_slot_of(info, STR_BOUNTY_COLLECTED)]
        assert banner[MSG_COLOR] == (7 if owner == 1 else 2)
        assert banner[MSG_SHIFT] == (0 if owner == 1 else 2)


def test_bounty_pays_no_score_at_all():
    """The gladiator bounty path posts a banner and nothing else — no digit is bumped here."""
    info = _end_of_wave(players=2, latches=GLADIATOR_ARMED, owner=1)
    assert not any(A_OBJECT_TABLE <= addr < A_ENEMY_OBJECTS for addr in _image_writes(info))


@pytest.mark.parametrize("screen_base", (SCREEN, SCREEN_ALT))
def test_end_of_wave_screen_bases(screen_base):
    """The bonus path draws through score_update as well as posting a banner, so both the banner's
    MSG_SCREEN_PTR and the repainted HUD row follow screen_base."""
    _end_of_wave(players=2, latches=TEAM_ARMED, p1_flags=4, screen_base=screen_base,
                 note=f"screen_base={screen_base:#x}")


# ==================================================================================================
# Phase E — starting the wave @ 0x17012, the second of wave_manager's two code chunks.
# ==================================================================================================

# Everything the wave start writes, pre-filled so a write the candidate skips shows as a diff.
FILLED_ON_START = ((A_RESPAWN_LOCK, 5),                    # + spawn_point_cursor
                   (A_SPEED_TYPE1, 8),                          # + speed 2/3 and the chase pair
                   (A_PLATFORM_PRESENT, N_PLATFORMS),
                   (A_FLAP_DELAY, 1),
                   (A_SPAWN_INTERVAL, 4),                       # + spawn_timer
                   (A_DRAW_X, 2),
                   (A_EFFECT_TABLE, N_EFFECTS * EFF_RECORD),
                   (A_ENEMY_OBJECTS, N_ENEMIES * OBJ_SIZE),
                   (A_EGG_SPREAD_SCRATCH, N_ENEMIES * EGG_SPREAD_RECORD))

RNG_START = 0x11000       # a cursor over the program's own text, where the words are not zero
LATCHES_QUIET = (LATCH_IDLE,) * 4


def _wave_start_pokes(wave=1, old_mask=0xff, new_mask=0xff, counts=(0, 0, 0), digits=b"01",
                      latches=LATCHES_QUIET, ground_latch=0, floor_rows=0, screen_base=SCREEN,
                      extra=None):
    """A countdown tick that reaches zero, so the wave-start body runs.

    `wave` is the number BEFORE the bump; the layout entry is poked at the bumped index, which is
    the one the body reads.
    """
    pokes = _base_pokes(screen_base=screen_base)
    pokes[A_GAME_PHASE] = bytes([WAVE_PHASE_ANNOUNCE])
    pokes[A_WAVE_NUM] = bytes([wave])
    pokes[A_WAVE_NUM_TENS] = bytes(digits)
    pokes[A_EGG_WAVE_COUNTDOWN] = bytes(latches)
    pokes[A_WAVE_LAYOUT_MASK] = bytes([old_mask, UNWRITTEN, UNWRITTEN, UNWRITTEN])
    pokes[A_FLOOR_STEP_TIMER] = bytes([UNWRITTEN, floor_rows])
    pokes[A_RNG_PTR] = struct.pack(">I", RNG_START)
    ground = bytearray([UNWRITTEN] * GA_BLOCK_BYTES)
    struct.pack_into(">H", ground, GA_ROWS_LATCH, ground_latch)
    pokes[A_GROUND_ANIM] = bytes(ground)
    for addr, length in FILLED_ON_START:
        pokes[addr] = bytes([UNWRITTEN] * length)
    for player in (A_OBJECT_TABLE, A_PLAYER2):
        pokes[player + OBJ_EGG_CHAIN] = bytes([UNWRITTEN])
    bumped = (wave + 1) & 0xff
    if bumped == WAVE_NUM_WRAP:
        bumped = WAVE_NUM_WRAP_TO
    pokes[A_WAVE_LAYOUT_TABLE + ((bumped ^ 0x80) - 0x80) * 4] = bytes([new_mask]) + bytes(counts)
    pokes.update(extra or {})
    return pokes


def _wave_start(note="", max_insns=200_000, **kwargs):
    return _wave_case(_wave_start_pokes(**kwargs), max_insns=max_insns, note=note or str(kwargs))


# ---- the wave count and the two digits the banner draws ----

@pytest.mark.parametrize("wave,expected", ((0, 1), (1, 2), (0x28, 0x29), (0x31, 0x32),
                                           (0x32, WAVE_NUM_WRAP_TO), (0x33, 0x34), (0xff, 0)))
def test_wave_number_wraps_at_the_last_wave(wave, expected):
    """The count climbs to WAVE_NUM_WRAP - 1 and then drops back, so the last ten waves repeat for
    ever. The test is an equality, not a bound: 0xff simply wraps round the byte."""
    info = _wave_start(wave=wave, note=f"wave={wave:#x}")
    assert _image_writes(info)[A_WAVE_NUM] == expected


@pytest.mark.parametrize("digits,expected", ((b"01", b"02"), (b"09", b"10"), (b" 9", b"10"),
                                             (b"19", b"20"), (b"99", b"\x3a0"), (b"  ", b" !")))
def test_wave_number_digits_carry_by_hand(digits, expected):
    """'9' + 1 is ':' and that is the carry's cue; the tens digit starts BLANK, so ITS first bump
    gives '!' and that is the cue to force it to '1'. A tens digit already at '9' carries to ':'
    and is left there — the original tests for '!' and nothing else."""
    info = _wave_start(wave=1, digits=digits, note=f"digits={digits!r}")
    written = _image_writes(info)
    got = bytes([written.get(A_WAVE_NUM_TENS, digits[0]), written.get(A_WAVE_NUM_UNITS, digits[1])])
    assert got == expected


# ---- the lava floor and the ground burn ----

@pytest.mark.parametrize("wave", (0, 1, 2, 3, 4, 0x7e, 0x7f, 0x80, 0xfe, 0xff))
def test_floor_is_owed_five_more_rows_over_the_opening_waves(wave):
    """`cmpi.b #3,wave_num ; bgt` on the BUMPED number, and it is SIGNED — so every wave number
    that reads negative is owed rows too."""
    info = _wave_start(wave=wave, floor_rows=2, note=f"wave={wave:#x}")
    bumped = _image_writes(info)[A_WAVE_NUM]
    owed = (bumped ^ 0x80) - 0x80 <= 3
    assert (A_FLOOR_ROWS_LEFT in _image_writes(info)) == owed
    if owed:
        assert _image_writes(info)[A_FLOOR_ROWS_LEFT] == 2 + FLOOR_ROWS_PER_WAVE
        assert _image_writes(info)[A_FLOOR_STEP_TIMER] == FLOOR_STEP_FRAMES


@pytest.mark.parametrize("rows", (0, 1, 0x7f, 0x80, 0xfb, 0xff))
def test_floor_rows_are_added_as_a_byte(rows):
    """`addq.b #5` — the count wraps in a byte rather than saturating."""
    info = _wave_start(wave=1, floor_rows=rows, note=f"rows={rows:#x}")
    assert _image_writes(info)[A_FLOOR_ROWS_LEFT] == (rows + FLOOR_ROWS_PER_WAVE) & 0xff


@pytest.mark.parametrize("wave", (1, 2, 3, 4, 0x80, 0xff))
def test_ground_burn_is_armed_on_waves_3_and_4_only(wave):
    """`cmpi.b #3 ; blt` then `cmpi.b #4 ; bgt` on the BUMPED number, both SIGNED."""
    info = _wave_start(wave=wave, note=f"wave={wave:#x}")
    bumped = (_image_writes(info)[A_WAVE_NUM] ^ 0x80) - 0x80
    assert (A_GROUND_ANIM in _image_writes(info)) == (3 <= bumped <= 4)


@pytest.mark.parametrize("wave,left_dst,right_dst,left_shift,right_shift,left_cells,right_cells",
                         ((2, 0x7398, 0x7438, 0xa, 0xc, 1, 0xffff),
                          (3, 0x73b0, 0x7428, 0x0, 0xa, 0, 0)))
def test_ground_burn_start_geometry(wave, left_dst, right_dst, left_shift, right_shift,
                                    left_cells, right_cells):
    """Wave 3 lights the flames at the two ends of the full-width ground, each clipped to the one
    cell that is on screen; wave 4 restarts them three cells further in, where both are whole.

    Every offset is scanline GROUND_BURN_ROW plus a whole number of cells — the derivation is
    asserted here so a transcription slip in the header cannot pass as layout.
    """
    assert left_dst == GROUND_BURN_ROW * SCREEN_ROW_BYTES + (-1 if wave == 2 else 2) * CELL_BYTES
    assert right_dst == GROUND_BURN_ROW * SCREEN_ROW_BYTES + (19 if wave == 2 else 17) * CELL_BYTES

    info = _wave_start(wave=wave, note=f"wave={wave}")
    written = _image_writes(info)

    def word(at):
        return (written[at] << 8) | written[at + 1]

    def long(at):
        return int.from_bytes(bytes(written[at + n] for n in range(4)), "big")

    left, right = A_GROUND_ANIM + GA_FLAME_LEFT, A_GROUND_ANIM + GA_FLAME_RIGHT
    assert word(A_GROUND_ANIM + GA_ROWS_LATCH) == 1 and word(A_GROUND_ANIM + GA_ROWS) == 0
    assert long(left + SPR_SRC) == FLAME_FRAME_FIRST
    assert long(right + SPR_SRC) == FLAME_FRAME_FIRST + 2 * FLAME_FRAME_BYTES
    assert (long(left + SPR_DST_OFF), long(right + SPR_DST_OFF)) == (left_dst, right_dst)
    assert (word(left + SPR_SHIFT), word(right + SPR_SHIFT)) == (left_shift, right_shift)
    assert (word(left + SPR_CELL_SELECT), word(right + SPR_CELL_SELECT)) == (left_cells,
                                                                             right_cells)


# ---- the platform layout, and the platforms handed to dissolve_platforms ----

@pytest.mark.parametrize("old_mask,new_mask", ((0xff, 0xff), (0xff, 0x00), (0x00, 0xff),
                                               (0xa5, 0x5a), (0x01, 0x00), (0x80, 0x00),
                                               (0x3c, 0x0f), (0xff, 0xfe)))
def test_effect_table_is_seeded_with_old_and_not_new(old_mask, new_mask):
    """This is the other end of dissolve_platforms' handshake, and it really is `old AND NOT new`:
    a platform that was there last wave and is gone this one gets an effect slot.

    The kind stored is 1-BASED — bit 0 of the mask is kind 1 — which is exactly why that routine
    indexes platform_sprites one record below the table.
    """
    info = _wave_start(wave=1, old_mask=old_mask, new_mask=new_mask,
                       note=f"{old_mask:#04x} -> {new_mask:#04x}")
    vanishing = [bit + 1 for bit in range(N_PLATFORMS) if old_mask & ~new_mask & (1 << bit)]
    written = _image_writes(info)
    got = []
    for slot in range(N_EFFECTS):
        at = A_EFFECT_TABLE + slot * EFF_RECORD + EFF_KIND
        if at in written:
            got.append((written[at] << 8) | written[at + 1])
    assert got == vanishing[:N_EFFECTS], "the wrong platforms were handed to the dissolve"


def test_effect_table_overruns_its_own_table_when_more_than_four_vanish():
    """There are only four effect slots and eight platforms, so a wave that loses five or more
    writes past the table — into the pterodactyl records above it. Reproduced, not guarded."""
    info = _wave_start(wave=1, old_mask=0xff, new_mask=0x00)
    written = _image_writes(info)
    beyond = A_EFFECT_TABLE + N_EFFECTS * EFF_RECORD + EFF_KIND
    assert (written[beyond] << 8) | written[beyond + 1] == N_EFFECTS + 1


@pytest.mark.parametrize("new_mask", (0x00, 0x01, 0x80, 0xff, 0xa5, 0x5a))
def test_platform_present_is_the_new_mask_one_bit_per_byte(new_mask):
    info = _wave_start(wave=1, new_mask=new_mask, note=f"mask={new_mask:#04x}")
    written = _image_writes(info)
    assert [written[A_PLATFORM_PRESENT + n] for n in range(N_PLATFORMS)] == \
        [(new_mask >> n) & 1 for n in range(N_PLATFORMS)]


def test_layout_table_index_is_a_signed_byte():
    """`ext.w` then `mulu.w #4` — the wave number is sign-extended, so a bumped number of 0x80..0xff
    reads BELOW the table. The case pokes its entry at the negative offset and checks the mask that
    came back, which is the only thing that distinguishes it from an unsigned index."""
    info = _wave_start(wave=0xfe, new_mask=0x81, counts=(0, 0, 0), note="wave 0xfe -> 0xff")
    assert _image_writes(info)[A_WAVE_LAYOUT_MASK] == 0x81


# ---- the per-wave difficulty numbers ----

@pytest.mark.parametrize("wave", (0, 1, 2, 0xf, 0x10, 0x1f, 0x20, 0x2f, 0x30, 0xff))
def test_flap_delay_drops_one_notch_every_sixteen_waves(wave):
    info = _wave_start(wave=wave, note=f"wave={wave:#x}")
    bumped = _image_writes(info)[A_WAVE_NUM]
    assert _image_writes(info)[A_FLAP_DELAY] == (5 - ((bumped >> 4) + 1)) & 0xff


@pytest.mark.parametrize("wave", (0, 1, 2, 4, 5, 8, 9, 0x10, 0x11, 0x40, 0x7f, 0x80, 0xff))
def test_rider_speeds_are_one_shifted_chain_with_a_cap(wave):
    """The three speeds come off one register shifted 2, 3 and 4 — and the decrement that feeds it
    is a BYTE inside a word, so wave 0 enters as 0xff and every type comes out at the cap."""
    info = _wave_start(wave=wave, note=f"wave={wave:#x}")
    rank = (_image_writes(info)[A_WAVE_NUM] - 1) & 0xff
    written = _image_writes(info)
    for at, shift in ((A_SPEED_TYPE1, 2), (A_SPEED_TYPE2, 3), (A_SPEED_TYPE3, 4)):
        got = (written[at] << 8) | written[at + 1]
        assert got == min((rank >> shift) + 1, RIDER_SPEED_MAX), f"speed at {at:#x}"


def test_wave_start_clears_the_egg_chains_and_the_chase_counts():
    """Both players' consecutive-egg counters go, and the pair of per-player chase counts is
    cleared with ONE `clr.w` — so both bytes are written, not just the first."""
    info = _wave_start(wave=1)
    written = _image_writes(info)
    assert written[A_OBJECT_TABLE + OBJ_EGG_CHAIN] == 0
    assert written[A_PLAYER2 + OBJ_EGG_CHAIN] == 0
    assert (written[A_CHASERS_P1], written[A_CHASERS_P1 + 1]) == (0, 0)


def test_wave_start_wipes_every_enemy_slot_whole():
    """`clr.w (a0)+` from enemy_objects to effect_table — the WHOLE area, physics and egg
    sub-records included, not just the flags words."""
    info = _wave_start(wave=1)
    written = _image_writes(info)
    for addr in range(A_ENEMY_OBJECTS, A_EFFECT_TABLE):
        assert written.get(addr) == 0, f"{addr:#x} was left holding {written.get(addr)}"


def test_wave_start_rewinds_the_spawn_point_cursor():
    info = _wave_start(wave=1)
    written = _image_writes(info)
    assert written[A_RESPAWN_LOCK] == 0
    assert int.from_bytes(bytes(written[A_SPAWN_POINT_CURSOR + n] for n in range(4)),
                          "big") == A_SPAWN_POINTS


# ---- the pterodactyl scheduler ----

@pytest.mark.parametrize("wave", (0, 1, 2, 0xf, 0x10, 0x11, 0x3f, 0x40, 0x63, 0x64, 0xff))
def test_spawn_interval_shortens_by_sixteen_a_wave(wave):
    """`#$640` less `wave_num << 4`, both as WORDS — so a high enough wave number wraps the
    subtraction rather than clamping. The timer starts at the same value."""
    info = _wave_start(wave=wave, note=f"wave={wave:#x}")
    written = _image_writes(info)
    bumped = written[A_WAVE_NUM]
    expected = (SPAWN_INTERVAL_BASE - ((bumped << 4) & 0xffff)) & 0xffff
    assert (written[A_SPAWN_INTERVAL] << 8) | written[A_SPAWN_INTERVAL + 1] == expected
    assert (written[A_SPAWN_TIMER] << 8) | written[A_SPAWN_TIMER + 1] == expected


@pytest.mark.parametrize("wave", (0, 1, 0xe, 0xf, 0x10, 0x7f, 0x80, 0xff))
@pytest.mark.parametrize("ptero_latch", (0, 1, LATCH_IDLE))
def test_pterodactyl_is_armed_only_on_its_own_wave(wave, ptero_latch):
    """A spent ptero latch arms slot 0 at once, and from PTERO_FIRST_ARMED_WAVE on it arrives
    almost immediately — `cmpi.b #$f ; bls`, an UNSIGNED compare, so 0x80 and 0xff are "past" it.

    LIMIT, stated rather than papered over: the loop that CLEARS the four slots cannot be observed
    here at all. A non-zero flags word in any slot holds the countdown (see phase A), so no run that
    reaches this code can have one — the clear writes 0 over 0 in every slot. Only slot 0's arming,
    and the fact that it happens AFTER the clear, are visible.
    """
    latches = (LATCH_IDLE, LATCH_IDLE, ptero_latch, LATCH_IDLE)
    info = _wave_start(wave=wave, latches=latches, note=f"wave={wave:#x} latch={ptero_latch}")
    written = _image_writes(info)
    armed = ptero_latch == 0
    assert ((written[A_PTERODACTYL_TABLE] << 8) | written[A_PTERODACTYL_TABLE + 1]) == int(armed)

    bumped = written[A_WAVE_NUM]
    timer = (written[A_SPAWN_TIMER] << 8) | written[A_SPAWN_TIMER + 1]
    if armed and bumped >= 0x10:
        assert timer == PTERO_IMMEDIATE_TIMER
    else:
        assert timer == (written[A_SPAWN_INTERVAL] << 8) | written[A_SPAWN_INTERVAL + 1]


# ---- lining up the riders ----

def _model_riders(counts):
    """(flags word per enemy slot, final counts) as the three spawn loops leave them."""
    flags, remaining = [], list(counts)
    for group, rider_type in enumerate((1, 2, 3)):
        if ((remaining[group] ^ 0x80) - 0x80) <= 0:
            continue
        while True:
            word = OBJ_FLAG_RESPAWN | rider_type
            if ((remaining[group] & 1) != 0) != (rider_type == 2):
                word |= OBJ_FLAG_FACING_RIGHT
            flags.append(word)
            remaining[group] = (remaining[group] - 1) & 0xff
            if remaining[group] == 0:
                break
    return flags, remaining


RIDER_COUNTS = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (3, 2, 1), (1, 1, 1), (4, 4, 4),
                (0x80, 1, 1), (0xff, 1, 1), (5, 0, 0), (0, 5, 0), (0, 0, 5), (2, 0, 3))


@pytest.mark.parametrize("counts", RIDER_COUNTS)
def test_riders_are_lined_up_by_type_with_alternating_facings(counts):
    """Each group fills the next slots with OBJ_FLAG_RESPAWN plus its type number, and bit 0 of the
    count still owed picks the facing. Type 2 tests that bit the OTHER way round (`bne` where types
    1 and 3 `beq`), so it faces in antiphase with the other two — reproduced, not tidied.

    A count of 0x80 is NEGATIVE to the `tst.b`/`ble` gate even though it looks large unsigned.
    """
    info = _wave_start(wave=1, counts=counts, note=f"counts={counts}")
    written = _image_writes(info)
    expected, remaining = _model_riders(counts)
    for slot, word in enumerate(expected):
        at = A_ENEMY_OBJECTS + slot * OBJ_SIZE + OBJ_FLAGS
        assert (written[at] << 8) | written[at + 1] == word, f"slot {slot}"
    for group, at in enumerate((A_WAVE_TYPE1_COUNT, A_WAVE_TYPE2_COUNT, A_WAVE_TYPE3_COUNT)):
        assert written.get(at, counts[group]) == remaining[group]


def test_riders_fill_every_slot_when_the_wave_is_full():
    """Twelve enemy slots, and a wave that asks for exactly twelve fills them all."""
    info = _wave_start(wave=1, counts=(4, 4, 4))
    written = _image_writes(info)
    for slot in range(N_ENEMIES):
        at = A_ENEMY_OBJECTS + slot * OBJ_SIZE + OBJ_FLAGS
        assert (written[at] << 8) | written[at + 1] != 0, f"slot {slot} was left empty"


# ---- scattering the wave's eggs (egg_wave_countdown == 0) ----

EGG_LATCHES = (0, LATCH_IDLE, LATCH_IDLE, LATCH_IDLE)
EGG_REST_ROWS, EGG_REST_ROLL_TIMER, EGG_REST_FALL_TIMER = 7, 4, 6
EGG_STATE_RESTING = 0x22
EGG_HATCH_TIMER_BASE, EGG_HATCH_TIMER_STEP = 0x91, 7
EGG_SPREAD_GAP = 8


def _egg_slots(written):
    """The enemy slots that were given an egg, as {slot: {field: value}}."""
    eggs = {}
    for slot in range(N_ENEMIES):
        base = A_ENEMY_OBJECTS + slot * OBJ_SIZE
        if written.get(base + OBJ_EGG_STATE) != EGG_STATE_RESTING:
            continue
        eggs[slot] = {
            "x": (written[base + OBJ_EGG_X] << 8) | written[base + OBJ_EGG_X + 1],
            "y": (written[base + OBJ_EGG_Y] << 8) | written[base + OBJ_EGG_Y + 1],
            "type": written[base + OBJ_EGG_SPAWN_FLAGS],
            "hatch": written[base + OBJ_EGG_HATCH_TIMER],
            "rows": written[base + OBJ_EGG_ROWS],
            "src": int.from_bytes(bytes(written[base + OBJ_EGG_SRC + n] for n in range(4)), "big"),
            "dst": int.from_bytes(bytes(written[base + OBJ_EGG_DST + n] for n in range(4)), "big"),
        }
    return eggs


@pytest.mark.parametrize("counts", ((0x80, 1, 1), (1, 0x80, 1), (1, 1, 0x80)))
def test_egg_type_counts_are_claimed_with_the_n_equals_v_rule(counts):
    """`subq.b #1 ; bge` tests N == V, so a count of exactly 0x80 leaves 0x7f and still compares
    NEGATIVE — the type is passed over rather than claimed. Reading the sign of the truncated byte
    instead gets that one value backwards, and this is the only battery that stages it (a mutation
    sweep found the hole).

    A 0x80 count leaves ~0x7f behind, which the rider loops then read as a hundred-odd riders and
    line up far past the twelve object slots — over the platform tables and, in the third case, over
    update_pterodactyl's code. That overrun is the original's own arithmetic and both cores commit
    it identically. What is NOT staged is all three counts at 0x80 together: that walks the rider
    writes over wave_manager's OWN instructions while the oracle is executing them, which no
    differential can follow.
    """
    _wave_start(wave=1, counts=counts, latches=EGG_LATCHES, max_insns=4_000_000,
                note=f"counts={counts}")


@pytest.mark.parametrize("egg_latch", (0, 1, LATCH_IDLE))
def test_eggs_are_scattered_only_on_the_egg_wave(egg_latch):
    """The egg placement and the rider line-up are alternatives: the placement spends the same
    three counts the rider loops read, so an egg wave has no riders in it at all."""
    latches = (egg_latch, LATCH_IDLE, LATCH_IDLE, LATCH_IDLE)
    info = _wave_start(wave=1, counts=(2, 1, 1), latches=latches, max_insns=2_000_000,
                       note=f"egg latch={egg_latch}")
    written = _image_writes(info)
    eggs = _egg_slots(written)
    first_flags = A_ENEMY_OBJECTS + OBJ_FLAGS
    if egg_latch == 0:
        assert len(eggs) == 4, "four eggs were owed"
        assert (written[first_flags] << 8) | written[first_flags + 1] == 0, "no riders on an egg wave"
    else:
        assert not eggs
        assert (written[first_flags] << 8) | written[first_flags + 1] != 0


def test_egg_records_carry_the_settled_egg_fields():
    """Every placed egg is a settled one: the still sprite, seven rows, the roll and fall timers,
    a screen pointer that is bare screen_base, and a hatch wait that grows by
    EGG_HATCH_TIMER_STEP down the list from EGG_HATCH_TIMER_BASE less the wave number."""
    info = _wave_start(wave=1, counts=(3, 0, 0), latches=EGG_LATCHES, max_insns=2_000_000)
    eggs = _egg_slots(_image_writes(info))
    assert sorted(eggs) == [0, 1, 2]
    for slot, egg in eggs.items():
        assert egg["src"] == A_EGG_SPRITE_STILL
        assert egg["dst"] == SCREEN
        assert egg["rows"] == EGG_REST_ROWS
        assert egg["type"] == 1
        assert egg["hatch"] == (EGG_HATCH_TIMER_BASE - 2 + (slot + 1) * EGG_HATCH_TIMER_STEP) & 0xff


def test_egg_types_are_claimed_in_order_and_leave_every_count_negative():
    """The type is written BEFORE its count is tested, so the counts all end at -1 and the last
    (unused) record is left carrying type 3. That is what stands the rider loops down."""
    info = _wave_start(wave=1, counts=(2, 1, 1), latches=EGG_LATCHES, max_insns=2_000_000)
    written = _image_writes(info)
    assert [egg["type"] for _, egg in sorted(_egg_slots(written).items())] == [1, 1, 2, 3]
    # Each count is taken down once more on every LATER egg, and once more again on the pass that
    # finds all three spent — so with 2/1/1 they finish at -3/-2/-1, not at -1/-1/-1.
    assert (written[A_WAVE_TYPE1_COUNT], written[A_WAVE_TYPE2_COUNT],
            written[A_WAVE_TYPE3_COUNT]) == (0xfd, 0xfe, 0xff)


def test_eggs_land_inside_their_platforms_and_are_never_crowded():
    """Each egg's y is its platform's top edge plus a fixed drop, and its x is a remainder of the
    platform's width added to its left edge — so it lands ON the platform. Two eggs on the same
    platform are always more than EGG_SPREAD_GAP apart, which is the whole point of the re-roll."""
    info = _wave_start(wave=1, counts=(4, 4, 4), latches=EGG_LATCHES, max_insns=4_000_000)
    eggs = _egg_slots(_image_writes(info))
    assert len(eggs) == N_ENEMIES, "a full wave of eggs"

    boxes = harness.BASE_IMAGE[A_PLATFORM_TABLE:A_PLATFORM_TABLE + N_PLATFORMS * PLAT_RECORD]
    by_platform = {}
    for egg in eggs.values():
        # Two pairs of the shipped boxes share a top edge, so the box is identified by BOTH its y
        # and its x range — which are disjoint within each pair, so the match is still exact.
        matches = [n for n in range(N_PLATFORMS)
                   if struct.unpack_from(">H", boxes, n * PLAT_RECORD + PLAT_Y0)[0] + 0xc == egg["y"]
                   and struct.unpack_from(">H", boxes, n * PLAT_RECORD + PLAT_X0)[0] <= egg["x"]
                   < struct.unpack_from(">H", boxes, n * PLAT_RECORD + PLAT_X1)[0]]
        assert len(matches) == 1, f"egg at ({egg['x']:#x},{egg['y']:#x}) is on no single platform"
        by_platform.setdefault(matches[0], []).append(egg["x"])
    for platform, xs in by_platform.items():
        for a in range(len(xs)):
            for b in range(a + 1, len(xs)):
                assert abs(xs[a] - xs[b]) > EGG_SPREAD_GAP, f"crowded on platform {platform}"


@pytest.mark.parametrize("rng_ptr", (0x10000, 0x11000, 0x12345, 0x17830, 0x17832))
def test_egg_placement_walks_the_random_cursor(rng_ptr):
    """The placement re-rolls through rng_advance, whose cursor wraps at RNG_PTR_LIMIT — including
    the entry that starts one word short of it, where the very first nudge wraps."""
    _wave_start(wave=1, counts=(2, 2, 2), latches=EGG_LATCHES, max_insns=4_000_000,
                note=f"rng_ptr={rng_ptr:#x}", extra={A_RNG_PTR: struct.pack(">I", rng_ptr)})


def test_egg_placement_uses_a_staged_platform_table():
    """The shipped boxes are all wide and all in the lower half of the screen, so they cannot tell
    PLAT_Y0/PLAT_X0/PLAT_X1 apart from a constant. These eight are deliberately narrow, tall and
    distinct — a wrong field then puts every egg in the wrong place."""
    boxes = b"".join(struct.pack(">HHHH", 0x10 + n * 0x11, 0x20 + n * 0x11,
                                 0x30 + n * 0x13, 0x30 + n * 0x13 + 0x25 + n)
                     for n in range(N_PLATFORMS))
    _wave_start(wave=1, counts=(4, 4, 4), latches=EGG_LATCHES, max_insns=4_000_000,
                note="staged platform table", extra={A_PLATFORM_TABLE: boxes})


# ==================================================================================================
# Fuzz — the whole state at once, sharded so `make test -n auto` stays fast.
# ==================================================================================================

FUZZ_CASES = 240
# The four shapes a case is steered into. Left to chance the state space collapses onto the held
# path — one message of the current generation is enough to freeze everything, and 24 slots make
# that overwhelmingly likely — so the shape is drawn first and the staging is bent to reach it.
# MEASURED on the shipped seed: 74 held, 60 announce, 46 bonus and 60 wave starts, 35 of which
# scatter eggs. `test_wave_manager_fuzz_reaches_every_shape` re-measures it rather than trusting it
# — a staging slip that quietly collapsed the corpus back onto the held path would otherwise leave
# 240 green cases proving nothing.
FUZZ_SHAPES = ("held", "announce", "bonus", "start")


def _fuzz_pokes(rng, shape):
    """One randomised starting state, bent towards `shape`."""
    screen_base = rng.choice((SCREEN, SCREEN_ALT))
    latches = [rng.choice((0, 1, 2, LATCH_IDLE, rng.randrange(0x100))) for _ in range(4)]
    counts = [rng.randrange(4) for _ in range(3)]
    wave = rng.randrange(0x100)
    phase = {"held": rng.choice((1, 2)), "announce": WAVE_PHASE_BONUS,
             "bonus": 0, "start": WAVE_PHASE_ANNOUNCE}[shape]

    # Half the wave starts are made egg waves — a spent egg latch AND something to place — since
    # the two alternatives are worth roughly equal weight and chance alone gives eggs far less.
    if shape == "start" and rng.randrange(2):
        latches[0] = 0
        counts[rng.randrange(3)] = rng.randrange(1, 4)

    # A slot whose kind matches game_phase holds the countdown, which is the point of "held" and
    # fatal to every other shape — so the other three draw their kinds from everything else.
    quiet = tuple(kind for kind in (0, 0, 0, 2, 3, 0x77, 0xff) if kind != phase)
    kinds = [rng.choice(quiet) for _ in range(N_MESSAGES)]
    if shape == "held":
        kinds[rng.randrange(N_MESSAGES)] = phase

    pokes = _wave_start_pokes(
        wave=wave, old_mask=rng.randrange(0x100), new_mask=rng.randrange(0x100), counts=counts,
        digits=bytes(rng.choice(b" 0123456789") for _ in range(2)), latches=tuple(latches),
        ground_latch=rng.choice((0, 0x8000, 0xffff) if shape != "held" else (0, 1, 0x7fff)),
        floor_rows=rng.randrange(0x100), screen_base=screen_base)

    pokes[A_GAME_PHASE] = bytes([phase])
    pokes[A_MESSAGE_TABLE] = _message_table(free=0, kinds=kinds)
    if shape == "held":
        pokes[A_PTERODACTYL_TABLE] = bytes([rng.randrange(2)]) + bytes(N_PTEROS * PT_RECORD - 1)
    players = rng.choice((0, 1, 2, 3))
    pokes[A_PLAYERS_ALIVE] = bytes([players])
    # The bonus shape needs the wave to be over: every survivor a player, and no eggs left.
    live = players if shape == "bonus" and rng.randrange(4) else rng.choice((0, 1, 2, 3))
    pokes[A_LIVE_OBJECT_COUNT] = bytes([live, 0 if shape == "bonus" else rng.choice((0, 0, 1))])
    pokes[A_PLAYER_CONFLICT_FLAG] = bytes([rng.choice((0, 1)), rng.choice((0, 1, 2, 0x80, 0xff))])
    pokes[A_SND_PRIORITY] = struct.pack(">H", SND_PRIORITY_IDLE)
    pokes[A_RNG_PTR] = struct.pack(">I", rng.randrange(0x10000, 0x17832) & ~1)

    # The HUD the bonus paths repaint through score_update, and the framebuffer under it.
    pokes[screen_base] = bytes(range(1, 0x100)) * (SCREEN_BYTES // 0xff)
    pokes[A_OBJECT_TABLE] = _score_record(screen_base + 0x400, flags=rng.choice((0, 4, 0xffff)))
    pokes[A_PLAYER2] = _score_record(screen_base + 0x400 + SCORE_ROW_PITCH * SCREEN_ROW_BYTES)
    for player in (A_OBJECT_TABLE, A_PLAYER2):
        pokes[player + OBJ_EGG_CHAIN] = bytes([UNWRITTEN])
    return pokes


def _fuzz_corpus():
    """The whole corpus, generated from ONE seed outside any shard filter so that every chunk
    replays the same stream and sees the same cases however they are scheduled."""
    rng = random.Random(ENTRY_WAVE_MANAGER)
    return [_fuzz_pokes(rng, FUZZ_SHAPES[index % len(FUZZ_SHAPES)]) for index in range(FUZZ_CASES)]


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_wave_manager_fuzz(chunk):
    """Random states across all three phases and both wave-start alternatives."""
    ran = 0
    for index, pokes in enumerate(_fuzz_corpus()):
        if index % FUZZ_CHUNKS != chunk:
            continue
        ran += 1
        _wave_case(pokes, max_insns=4_000_000, note=f"fuzz case {index}")
    assert ran, "the chunk filter rejected every case"


def test_wave_manager_fuzz_reaches_every_shape():
    """The corpus is only worth running if it lands where it claims to. Each case is classified by
    what the ORACLE actually wrote, so a staging slip that quietly turned the whole corpus into
    do-nothing held cases fails here instead of leaving 240 green cases proving nothing."""
    reached = {shape: 0 for shape in FUZZ_SHAPES}
    reached["eggs"] = 0
    for pokes in _fuzz_corpus():
        final, writes, _ = emu.run(harness.make_image(pokes), ENTRY_WAVE_MANAGER, {},
                                   max_insns=4_000_000)
        written = {addr for addr in writes if addr < emu.STACK_GUARD_LO}
        if A_WAVE_LAYOUT_MASK in written:
            reached["start"] += 1
            reached["eggs"] += any(final[A_ENEMY_OBJECTS + slot * OBJ_SIZE + OBJ_EGG_STATE]
                                   == EGG_STATE_RESTING for slot in range(N_ENEMIES))
        elif A_GAME_PHASE not in written:
            reached["held"] += 1
        elif writes[A_GAME_PHASE] == WAVE_PHASE_BONUS:
            reached["bonus"] += 1
        else:
            reached["announce"] += 1
    assert all(count >= FUZZ_CASES // 16 for count in reached.values()), \
        f"the corpus is lopsided: {reached}"


# ==================================================================================================
# Pins — the constants above restated from ../../names.txt and include/, kept equal by test.
# ==================================================================================================

def test_entry_address_matches_names_txt():
    assert harness.NAME_MAP.get(ENTRY_WAVE_MANAGER) == "wave_manager"


# (this module's name, the header it belongs to, the name it has there)
MIRRORED_ADDRESSES = (
    ("A_PLAYERS_ALIVE", "include/score.h", "A_players_alive"),
    ("A_WAVE_NUM", "include/world.h", "A_wave_num"),
    ("A_WAVE_NUM_TEXT", "include/wave.h", "A_wave_num_text"),
    ("A_WAVE_NUM_TENS", "include/wave.h", "A_wave_num_tens"),
    ("A_WAVE_NUM_UNITS", "include/wave.h", "A_wave_num_units"),
    ("A_PLATFORM_PRESENT", "include/object.h", "A_platform_present"),
    ("A_EGG_WAVE_COUNTDOWN", "include/wave.h", "A_egg_wave_countdown"),
    ("A_TEAM_WAVE_COUNTDOWN", "include/wave.h", "A_team_wave_countdown"),
    ("A_PTERO_WAVE_COUNTDOWN", "include/wave.h", "A_ptero_wave_countdown"),
    ("A_GLADIATOR_WAVE_COUNTDOWN", "include/addrs.h", "A_gladiator_wave_countdown"),
    ("A_PLAYER_CONFLICT_FLAG", "include/addrs.h", "A_player_conflict_flag"),
    ("A_FIRST_DISMOUNT_OWNER", "include/addrs.h", "A_first_dismount_owner"),
    ("A_GAME_PHASE", "include/object.h", "A_game_phase"),
    ("A_LIVE_OBJECT_COUNT", "include/object.h", "A_live_object_count"),
    ("A_EGG_COUNT", "include/object.h", "A_egg_count"),
    ("A_RESPAWN_LOCK", "include/addrs.h", "A_respawn_lock"),
    ("A_SPAWN_POINT_CURSOR", "include/addrs.h", "A_spawn_point_cursor"),
    ("A_WAVE_LAYOUT_MASK", "include/wave.h", "A_wave_layout_mask"),
    ("A_WAVE_TYPE1_COUNT", "include/wave.h", "A_wave_type1_count"),
    ("A_WAVE_TYPE2_COUNT", "include/wave.h", "A_wave_type2_count"),
    ("A_WAVE_TYPE3_COUNT", "include/wave.h", "A_wave_type3_count"),
    ("A_SPEED_TYPE1", "include/addrs.h", "A_speed_type1"),
    ("A_SPEED_TYPE2", "include/addrs.h", "A_speed_type2"),
    ("A_SPEED_TYPE3", "include/addrs.h", "A_speed_type3"),
    ("A_CHASERS_P1", "include/addrs.h", "A_chasers_p1"),
    ("A_FLOOR_STEP_TIMER", "include/world.h", "A_floor_step_timer"),
    ("A_FLOOR_ROWS_LEFT", "include/world.h", "A_floor_rows_left"),
    ("A_GROUND_ANIM", "include/world.h", "A_ground_anim"),
    ("A_FLAP_DELAY", "include/addrs.h", "A_flap_delay"),
    ("A_SCREEN_BASE", "include/addrs.h", "A_screen_base"),
    ("A_DRAW_X", "include/object.h", "A_draw_x"),
    ("A_SPAWN_INTERVAL", "include/wave.h", "A_spawn_interval"),
    ("A_SPAWN_TIMER", "include/wave.h", "A_spawn_timer"),
    ("A_RNG_PTR", "include/addrs.h", "A_rng_ptr"),
    ("A_MESSAGE_TABLE", "include/object.h", "A_message_table"),
    ("A_OBJECT_TABLE", "include/addrs.h", "A_object_table"),
    ("A_PLAYER2", "include/draw.h", "A_player2"),
    ("A_ENEMY_OBJECTS", "include/addrs.h", "A_enemy_objects"),
    ("A_EFFECT_TABLE", "include/world.h", "A_effect_table"),
    ("A_PTERODACTYL_TABLE", "include/object.h", "A_pterodactyl_table"),
    ("A_PTERODACTYL_TABLE_END", "include/object.h", "A_pterodactyl_table_END"),
    ("A_PLATFORM_TABLE", "include/object.h", "A_platform_table"),
    ("A_SPAWN_POINTS", "include/world.h", "A_spawn_points"),
    ("A_WAVE_LAYOUT_TABLE", "include/wave.h", "A_wave_layout_table"),
    ("A_EGG_SPREAD_SCRATCH", "include/wave.h", "A_egg_spread_scratch"),
    ("A_EGG_SPRITE_STILL", "include/egg.h", "A_egg_sprite_still"),
    # ---- record fields ----
    ("MSG_KIND", "include/object.h", "MSG_KIND"),
    ("MSG_TIMER", "include/score.h", "MSG_TIMER"),
    ("MSG_COLOR", "include/score.h", "MSG_COLOR"),
    ("MSG_SHIFT", "include/score.h", "MSG_SHIFT"),
    ("MSG_SCREEN_PTR", "include/object.h", "MSG_SCREEN_PTR"),
    ("MSG_STRING", "include/score.h", "MSG_STRING"),
    ("MSG_RECORD", "include/object.h", "MSG_RECORD"),
    ("PT_RECORD", "include/object.h", "PT_RECORD"),
    ("OBJ_SIZE", "include/joust.h", "OBJ_SIZE"),
    ("OBJ_FLAGS", "include/joust.h", "OBJ_FLAGS"),
    ("OBJ_EGG_STATE", "include/joust.h", "OBJ_EGG_STATE"),
    ("OBJ_EGG_HATCH_TIMER", "include/egg.h", "OBJ_EGG_HATCH_TIMER"),
    ("OBJ_EGG_X", "include/joust.h", "OBJ_EGG_X"),
    ("OBJ_EGG_Y", "include/egg.h", "OBJ_EGG_Y"),
    ("OBJ_EGG_ROLL_TIMER", "include/egg.h", "OBJ_EGG_ROLL_TIMER"),
    ("OBJ_EGG_FALL_TIMER", "include/egg.h", "OBJ_EGG_FALL_TIMER"),
    ("OBJ_EGG_DST", "include/joust.h", "OBJ_EGG_DST"),
    ("OBJ_EGG_SRC", "include/joust.h", "OBJ_EGG_SRC"),
    ("OBJ_EGG_ROWS", "include/joust.h", "OBJ_EGG_ROWS"),
    ("OBJ_EGG_SPAWN_FLAGS", "include/egg.h", "OBJ_EGG_SPAWN_FLAGS"),
    ("OBJ_EGG_CHAIN", "include/world.h", "OBJ_EGG_CHAIN"),
    ("OBJ_SCORE_PTR", "include/score.h", "OBJ_SCORE_PTR"),
    ("OBJ_SCORE_SHIFT", "include/score.h", "OBJ_SCORE_SHIFT"),
    ("OBJ_SCORE_TEXT", "include/score.h", "OBJ_SCORE_TEXT"),
    ("OBJ_SCORE_FIRST_DIGIT", "include/score.h", "OBJ_SCORE_FIRST_DIGIT"),
    ("OBJ_SCORE_LIFE_DIGIT", "include/score.h", "OBJ_SCORE_LIFE_DIGIT"),
    ("OBJ_LIVES", "include/score.h", "OBJ_LIVES"),
    ("EFF_RECORD", "include/world.h", "EFF_RECORD"),
    ("EFF_KIND", "include/world.h", "EFF_KIND"),
    ("PLAT_RECORD", "include/object.h", "PLAT_RECORD"),
    ("PLAT_Y0", "include/object.h", "PLAT_Y0"),
    ("PLAT_X0", "include/object.h", "PLAT_X0"),
    ("PLAT_X1", "include/object.h", "PLAT_X1"),
    ("N_PLATFORMS", "include/world.h", "PLATFORM_COUNT"),
    ("GA_ROWS_LATCH", "include/world.h", "GA_ROWS_LATCH"),
    ("GA_ROWS", "include/world.h", "GA_ROWS"),
    ("GA_FLAME_LEFT", "include/world.h", "GA_FLAME_LEFT"),
    ("GA_FLAME_RIGHT", "include/world.h", "GA_FLAME_RIGHT"),
    ("GA_BLOCK_BYTES", "include/world.h", "GA_BLOCK_BYTES"),
    ("SPR_SRC", "include/draw.h", "SPR_SRC"),
    ("SPR_DST_OFF", "include/draw.h", "SPR_DST_OFF"),
    ("SPR_SHIFT", "include/draw.h", "SPR_SHIFT"),
    ("SPR_CELL_SELECT", "include/draw.h", "SPR_CELL_SELECT"),
    ("SCREEN_ROW_BYTES", "include/joust.h", "SCREEN_ROW_BYTES"),
    ("CELL_BYTES", "include/joust.h", "CELL_BYTES"),
    # ---- the banner strings ----
    ("STR_PREPARE_TO_JOUST", "include/wave.h", "STR_PREPARE_TO_JOUST"),
    ("STR_BUZZARD_BAIT", "include/wave.h", "STR_BUZZARD_BAIT"),
    ("STR_WAVE", "include/wave.h", "STR_WAVE"),
    ("STR_SURVIVAL_WAVE", "include/wave.h", "STR_SURVIVAL_WAVE"),
    ("STR_TEAM_WAVE", "include/wave.h", "STR_TEAM_WAVE"),
    ("STR_TEAM_PLAY_BONUS", "include/wave.h", "STR_TEAM_PLAY_BONUS"),
    ("STR_GLADIATOR_WAVE", "include/wave.h", "STR_GLADIATOR_WAVE"),
    ("STR_BOUNTY_OFFER", "include/wave.h", "STR_BOUNTY_OFFER"),
    ("STR_DISMOUNT_FIRST", "include/wave.h", "STR_DISMOUNT_FIRST"),
    ("STR_EGG_WAVE", "include/wave.h", "STR_EGG_WAVE"),
    ("STR_PTERODACTYL_WAVE", "include/wave.h", "STR_PTERODACTYL_WAVE"),
    ("STR_BEWARE_PTERO", "include/wave.h", "STR_BEWARE_PTERO"),
    ("STR_CO_OPERATION", "include/wave.h", "STR_CO_OPERATION"),
    ("STR_PLAYER_CONFLICT", "include/wave.h", "STR_PLAYER_CONFLICT"),
    ("STR_SURVIVAL_BONUS", "include/wave.h", "STR_SURVIVAL_BONUS"),
    ("STR_NO_BONUS", "include/wave.h", "STR_NO_BONUS"),
    ("STR_NO_BOUNTY", "include/wave.h", "STR_NO_BOUNTY"),
    ("STR_BOUNTY_COLLECTED", "include/wave.h", "STR_BOUNTY_COLLECTED"),
    # ---- the values ----
    ("WAVE_PHASE_ANNOUNCE", "include/wave.h", "WAVE_PHASE_ANNOUNCE"),
    ("WAVE_PHASE_BONUS", "include/wave.h", "WAVE_PHASE_BONUS"),
    ("BANNER_FRAMES", "include/player.h", "BANNER_FRAMES"),
    ("BUZZARD_BAIT_CUE", "include/wave.h", "BUZZARD_BAIT_CUE"),
    ("SPECIAL_WAVE_LEAD", "include/wave.h", "SPECIAL_WAVE_LEAD"),
    ("WAVE_BONUS_THOUSANDS", "include/wave.h", "WAVE_BONUS_THOUSANDS"),
    ("WAVE_NUM_WRAP", "include/wave.h", "WAVE_NUM_WRAP"),
    ("WAVE_NUM_WRAP_TO", "include/wave.h", "WAVE_NUM_WRAP_TO"),
    ("FLOOR_ROWS_PER_WAVE", "include/wave.h", "FLOOR_ROWS_PER_WAVE"),
    ("FLOOR_STEP_FRAMES", "include/world.h", "FLOOR_STEP_FRAMES"),
    ("RIDER_SPEED_MAX", "include/wave.h", "RIDER_SPEED_MAX"),
    ("GROUND_BURN_ROW", "include/wave.h", "GROUND_BURN_ROW"),
    ("FLAME_FRAME_FIRST", "include/world.h", "FLAME_FRAME_FIRST"),
    ("FLAME_FRAME_BYTES", "include/world.h", "FLAME_FRAME_BYTES"),
    ("SPAWN_INTERVAL_BASE", "include/wave.h", "SPAWN_INTERVAL_BASE"),
    ("PTERO_IMMEDIATE_TIMER", "include/wave.h", "PTERO_IMMEDIATE_TIMER"),
    ("EGG_SPREAD_RECORD", "include/wave.h", "EGG_SPREAD_RECORD"),
    ("EGG_SPREAD_GAP", "include/wave.h", "EGG_SPREAD_GAP"),
    ("EGG_REST_ROWS", "include/wave.h", "EGG_REST_ROWS"),
    ("EGG_REST_ROLL_TIMER", "include/wave.h", "EGG_REST_ROLL_TIMER"),
    ("EGG_REST_FALL_TIMER", "include/wave.h", "EGG_REST_FALL_TIMER"),
    ("EGG_HATCH_TIMER_BASE", "include/wave.h", "EGG_HATCH_TIMER_BASE"),
    ("EGG_HATCH_TIMER_STEP", "include/wave.h", "EGG_HATCH_TIMER_STEP"),
    ("EGG_STATE_RESTING", "include/egg.h", "EGG_STATE_RESTING"),
    ("OBJ_FLAG_RESPAWN", "include/joust.h", "OBJ_FLAG_RESPAWN"),
    ("OBJ_FLAG_FACING_RIGHT", "include/joust.h", "OBJ_FLAG_FACING_RIGHT"),
    ("BANNER_COLOR_P1", "include/player.h", "BANNER_COLOR_P1"),
)


def test_mirrored_constants_match_their_headers():
    """Every value this module restates is pinned to the ONE header that owns it. A drift here is
    invisible to the differential itself: a staged input would land at a dead address, both cores
    would agree on the game's own untouched data, and the case would go green proving nothing."""
    headers = {}
    for mirror, path, name in MIRRORED_ADDRESSES:
        headers.setdefault(path, _defines(path))
        assert name in headers[path], f"{path} defines no {name}"
        assert headers[path][name] == globals()[mirror], \
            f"{mirror} ({globals()[mirror]:#x}) is not {path}'s {name} ({headers[path][name]:#x})"


def test_named_globals_match_names_txt():
    """The addresses this layer OWNS carry the names ../../names.txt gives them."""
    for addr, name in ((A_WAVE_NUM_TEXT, "wave_num_text"),
                       (A_EGG_WAVE_COUNTDOWN, "egg_wave_countdown"),
                       (A_TEAM_WAVE_COUNTDOWN, "team_wave_countdown"),
                       (A_PTERO_WAVE_COUNTDOWN, "ptero_wave_countdown"),
                       (A_GLADIATOR_WAVE_COUNTDOWN, "gladiator_wave_countdown"),
                       (A_PLAYER_CONFLICT_FLAG, "player_conflict_flag"),
                       (A_FIRST_DISMOUNT_OWNER, "first_dismount_owner"),
                       (A_SPAWN_POINT_CURSOR, "spawn_point_cursor"),
                       (A_WAVE_LAYOUT_MASK, "wave_layout_mask"),
                       (A_WAVE_TYPE1_COUNT, "wave_type1_count"),
                       (A_WAVE_TYPE2_COUNT, "wave_type2_count"),
                       (A_WAVE_TYPE3_COUNT, "wave_type3_count"),
                       (A_SPEED_TYPE2, "speed_type2"),
                       (A_SPEED_TYPE3, "speed_type3"),
                       (A_FLAP_DELAY, "flap_delay"),
                       (A_SPAWN_INTERVAL, "spawn_interval"),
                       (A_SPAWN_TIMER, "spawn_timer"),
                       (A_ENEMY_OBJECTS, "enemy_objects"),
                       (A_PTERODACTYL_TABLE, "pterodactyl_table")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_platform_present_end_is_exactly_one_byte_per_platform():
    """The loop bound is an ADDRESS in the original (`cmpa.l #$d02`), and the only thing that makes
    it eight passes is that the next global sits eight bytes up."""
    wave_h, world_h, object_h = (_defines("include/wave.h"), _defines("include/world.h"),
                                 _defines("include/object.h"))
    assert wave_h["A_platform_present_END"] - object_h["A_platform_present"] == \
        world_h["PLATFORM_COUNT"]
    assert wave_h["A_platform_present_END"] == wave_h["A_egg_wave_countdown"], \
        "the bound is the next global up, which is what makes the duplication safe"


def test_ground_burn_offsets_are_a_scanline_and_a_whole_number_of_cells():
    """Each flame's start offset is GROUND_BURN_ROW's scanline plus a cell count, so a transcribed
    digit cannot pass as layout. Wave 3 lights them one cell OFF each edge of the screen; wave 4
    three cells further in, where both are whole."""
    wave_h, joust_h = _defines("include/wave.h"), _defines("include/joust.h")
    row = wave_h["GROUND_BURN_ROW"] * joust_h["SCREEN_ROW_BYTES"]
    for name, cell in (("GROUND_BURN_WAVE3_LEFT_DST", -1), ("GROUND_BURN_WAVE3_RIGHT_DST", 19),
                       ("GROUND_BURN_WAVE4_LEFT_DST", 2), ("GROUND_BURN_WAVE4_RIGHT_DST", 17)):
        assert wave_h[name] == row + cell * joust_h["CELL_BYTES"], f"{name} is not row + {cell} cells"


def test_the_wave_layout_table_is_one_longword_per_wave_up_to_the_wrap():
    """The table runs from A_wave_layout_table to the next named thing above it, and holds exactly
    one {mask, count, count, count} longword per wave number the game can reach."""
    entries = 0x11c24 - A_WAVE_LAYOUT_TABLE      # poll_quit_key, the next function
    assert harness.NAME_MAP.get(0x11c24) == "poll_quit_key"
    assert entries == (WAVE_NUM_WRAP) * 4, "the table stops exactly where the wave count wraps"
