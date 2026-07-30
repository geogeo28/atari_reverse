"""Differential tests for Joust's player-control layer (src/player.c).

Covered here: player_death @ 0x11f28 and control_player @ 0x11dd6, plus the piece of
control_player's restart path that lies between two unported calls (0x11e50, reconstructed as
`restart_reset_players`).

control_player has ONE PATH THAT NEVER RETURNS — no players left and fire pressed drops two return
addresses and restarts the game through check_highscore / init_game / init_video — so that branch
is diffed at a checkpoint PC instead of at `rts`. Every checkpoint here is paired with
`_never_returns`, because a `stop_pc` run that merely fell through to `rts` stops at the sentinel
and PASSES SILENTLY; without the pair a checkpoint proves nothing about which path ran. What each
checkpoint does and does not prove is written out at the case itself.
"""
import ctypes
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_CONTROL_PLAYER = 0x11dd6
ENTRY_PLAYER_DEATH = 0x11f28

# ---- inner addresses of control_player's restart path. They are not function entries, so
# names.txt cannot pin them; test_checkpoints_are_the_instructions_they_claim_to_be pins each
# against the ORIGINAL'S OWN ENCODING at that address instead.
CHECKPOINT_BEFORE_HISCORE = 0x11e44   # `jsr check_highscore` — the first unported call
ENTRY_RESTART_TAIL = 0x11e50          # `tst.b two_player_mode`, just past `jsr init_game`
CHECKPOINT_BEFORE_INIT_VIDEO = 0x11e94  # `jsr init_video`, the next unported call after the tail
JSR_ABS_LONG = 0x4eb9                 # `jsr xxx.l`
TST_B_ABS_LONG = 0x4a39               # `tst.b xxx.l`
A_CHECK_HIGHSCORE = 0x1437a
A_INIT_VIDEO = 0x104b2

# ---- the CONTROL_* results src/player.c reports its exit with ----
CONTROL_RETURNED, CONTROL_RESTART = 0, 1

# ---- globals (mirrors of include/player.h, score.h, addrs.h and draw.h) ----
A_PLAYERS_ALIVE = 0x10cf2
A_TWO_PLAYER_MODE = 0x10d11
A_GAME_OVER_FLAG = 0x10d12
A_SCREEN_BASE = 0x10dde
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36       # player 1's slot, and the table's base
A_PLAYER2 = 0x10f84
A_ENEMY_OBJECTS = 0x10fd2
A_TEXT_PTR = 0x10e0a           # draw_lives stages the text engine through here...
A_TEXT_SHIFT = 0x10e0e
A_TEXT_COLOR = 0x10e0f
A_TEXT_BG_COLOR = 0x10e10
A_TEXT_FLAGS = 0x10e11
A_STR_GAME_OVER = 0x185c5
A_STR_PLAYER1_OVER = 0x185d8
A_STR_PLAYER2_OVER = 0x185ed

# ---- record geometry ----
OBJ_SIZE, N_OBJECTS = 0x4e, 14
MSG_RECORD, N_MESSAGES = 0xc, 24
MSG_KIND, MSG_TIMER, MSG_COLOR, MSG_SHIFT, MSG_SCREEN_PTR, MSG_STRING = 0, 1, 2, 3, 4, 8
OBJ_LIVES, OBJ_SCORE_LAST_DIGIT = 0x4c, 0x44

# A "record" that is NOT a player slot but lies BELOW player 2's, which is the only thing
# player_death's `bls` bound actually asks. It is parked on a message-table slot so that staging it
# cannot clobber either player's record — an overwritten score pointer would send draw_lives
# painting outside the image rather than testing the bound.
A_BELOW_THE_PLAYERS = A_MESSAGE_TABLE + 17 * MSG_RECORD

# ---- the flags-word bits this layer reads (../../names.txt's object-flags comment). Every one of
# them is pinned to its header by test_mirrored_flag_bits_match_the_headers — a wrong bit here would
# quietly stage the WRONG SHAPE (a "dead" rider that is really alive), and both cores would then
# agree byte-for-byte on a case that tests nothing.
FLAG_GRABBED = 1 << 4
FLAG_FLAP_LOW = 1 << 6
FLAG_RESPAWN = 1 << 7
FLAG_IN_LAVA = 1 << 8
FLAG_ON_PLATFORM = 1 << 9
FLAG_FLAP_HIGH = 1 << 11
FLAG_DEAD = 1 << 13
FLAG_FACING_RIGHT = 1 << 15
FLAGS_FLAPPING = FLAG_FLAP_LOW | FLAG_FLAP_HIGH

# ---- the joystick byte ----
STICK_LEFT, STICK_RIGHT, STICK_FLAP = 0x04, 0x08, 0x80
STICK_UP, STICK_DOWN = 0x01, 0x02          # never tested by control_player — dead input, fuzzed

# ---- what the reconstruction's constants say the original does ----
PLAYER_STEER_VX = 4
DEAD_EXIT_RIGHT_X, DEAD_EXIT_LEFT_LO, DEAD_EXIT_LEFT_HI = 0x13c, 0x130, 0x133
HOVER_BAND_HIGH_Y, HOVER_BAND_MID_Y = 0x28, 0x64
HOVER_TARGET_HIGH, HOVER_TARGET_MID, HOVER_TARGET_LOW = 0x0a, 0x42, 0x8c
LIVES_EXHAUSTED = 0xff
PLAYER_START_LIVES, SCORE_UNITS_ZERO = 4, 0x30
PLAYERS_ALIVE_ONE, PLAYERS_ALIVE_TWO, GAME_OVER_SET = 1, 2, 1
BANNER_FRAMES = 0x64
BANNER_GAME_OVER_DST_OFF, BANNER_PLAYER_OUT_DST_OFF = 0x3238, 0x3230
BANNER_GAME_OVER_SHIFT, BANNER_PLAYER_OUT_SHIFT = 0, 4
BANNER_COLOR_GAME_OVER, BANNER_COLOR_P1, BANNER_COLOR_P2 = 1, 7, 2

# ---- scratch, all clear of the program (ends 0x2b7ae), of test/abi.py's stub space
# (0x40000..0x40207), of the staged-file table (0xbf000) and of the stack guard. The screen band is
# filled with noise so that a blit or a glyph that never happened shows as a diff rather than as
# zero matching zero.
SPRITE = 0x60000
SCREEN = 0x70000
SCREEN_SPAN = 0x8000
P1_SCORE_PTR = SCREEN + 0x1000     # where draw_lives_p1 paints player 1's row...
P2_SCORE_PTR = SCREEN + 0x2000     # ...and draw_lives_p2 player 2's
PREV_DST = SCREEN + 0x3000         # where draw_object_mask erases the corpse's last sprite

UNWRITTEN_W = 0x5a5a               # pre-filled into output words so a missing write shows as a diff
UNWRITTEN_B = 0x5a
SPRITE_ROWS = 4                    # kept small: prev_rows = 0 would mean 256 rows (`subq.b`)
SPRITE_SHIFT = 3

# A spin that never ends is capped rather than run to the harness default: the `_never_returns`
# cases exist to show the oracle does NOT come back, so a small cap keeps them cheap.
SPIN_CAP = 2_000

FUZZ_CHUNKS = 4

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs, _ret in (("g_control_player", 2, ctypes.c_uint32),
                            ("g_player_death", 1, None),
                            ("g_restart_reset_players", 0, None)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = _ret


# ------------------------------------------------------------------ shared staging helpers

def _never_returns(pokes, entry, regs=None):
    """Assert the original does not come back from `entry` on this input.

    Paired with every `stop_pc` case below: osh_run reports success whether it stopped at the
    checkpoint or at the `rts` sentinel, so a checkpointed run on a path that actually returned
    would go green while proving nothing about the branch it claims to cover.

    `regs` MUST be the checkpointed case's own registers. Entering control_player with a zeroed D0
    is a different case entirely — no fire, so it returns at once — and the pair would then be
    asserting nothing about the branch it is supposed to cover.

    (test_input.py carries the same helper, minus the registers its entries do not take. It is
    copied rather than imported because that module reaches into test_score for three of its own
    helpers, and this file has no other reason to depend on the high-score battery.)
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(pokes), entry, regs or {}, max_insns=SPIN_CAP)


_OBJECT_LAYOUT = {"flags": (0x00, "H"), "x": (0x02, "H"), "y": (0x04, "H"), "vx": (0x06, "H"),
                  "vy": (0x08, "H"), "target_vx": (0x0c, "H"), "prev_x": (0x10, "H"),
                  "prev_dst": (0x14, "I"), "prev_src": (0x18, "I"), "prev_rows": (0x1c, "B"),
                  "prev_shift": (0x1d, "B"), "score_ptr": (0x36, "I"), "score_shift": (0x3a, "H"),
                  "score_units": (0x44, "B"), "target_y": (0x46, "H"), "lives": (0x4c, "B")}


def _object(**fields):
    """A 0x4e-byte object record. The two words this layer WRITES start at a sentinel so that a
    candidate which failed to write one diverges; every other field not named is zero."""
    rec = bytearray(OBJ_SIZE)
    struct.pack_into(">H", rec, _OBJECT_LAYOUT["target_vx"][0], UNWRITTEN_W)
    struct.pack_into(">H", rec, _OBJECT_LAYOUT["target_y"][0], UNWRITTEN_W)
    for name, value in fields.items():
        off, fmt = _OBJECT_LAYOUT[name]
        struct.pack_into(">" + fmt, rec, off, value)
    return bytes(rec)


def _noise(seed, length):
    return bytes(random.Random(seed).randrange(0x100) for _ in range(length))


def _rider(**fields):
    """An object record with everything the erase pass and the lives row need already pointing at
    scratch, so any branch of either routine can be taken without staging it case by case."""
    staged = {"prev_dst": PREV_DST, "prev_src": SPRITE, "prev_rows": SPRITE_ROWS,
              "prev_shift": SPRITE_SHIFT, "score_ptr": P1_SCORE_PTR, "lives": 3}
    staged.update(fields)
    return _object(**staged)


def _world(objects=None, messages=None, players_alive=PLAYERS_ALIVE_TWO, two_player=1,
           game_over=UNWRITTEN_B):
    """Everything both routines touch outside the object under test.

    `objects` maps a slot address to its record; the two player slots default to records whose
    score pointers aim into the noise screen, because player_death repaints BOTH lives rows
    whichever player died. `messages` is the table's kind bytes, which is all find_free_message
    looks at — the rest of every slot starts as a sentinel so each field the banner writes shows.
    """
    kinds = [0] * N_MESSAGES if messages is None else list(messages)
    table = bytearray()
    for kind in kinds:
        record = bytearray([UNWRITTEN_B]) * MSG_RECORD
        record[MSG_KIND] = kind
        table += record

    pokes = {SCREEN: _noise(0x11dd6, SCREEN_SPAN),
             SPRITE: _noise(0x11f28, SPRITE_ROWS * 0x10 + 0x10),
             A_SCREEN_BASE: SCREEN.to_bytes(4, "big"),
             A_MESSAGE_TABLE: bytes(table),
             A_PLAYERS_ALIVE: bytes([players_alive]),
             A_TWO_PLAYER_MODE: bytes([two_player]),
             A_GAME_OVER_FLAG: bytes([game_over]),
             # The text engine's block, which draw_lives restages before every glyph. text_flags
             # starts DEFINED rather than sentinelled: the lives row ORs its two bits into it.
             A_TEXT_PTR: UNWRITTEN_W.to_bytes(2, "big") * 2,
             A_TEXT_SHIFT: bytes([UNWRITTEN_B]),
             A_TEXT_COLOR: bytes([UNWRITTEN_B]),
             A_TEXT_BG_COLOR: bytes([UNWRITTEN_B]),
             A_TEXT_FLAGS: bytes([0]),
             A_OBJECT_TABLE: _rider(score_ptr=P1_SCORE_PTR),
             A_PLAYER2: _rider(score_ptr=P2_SCORE_PTR)}
    for addr, record in (objects or {}).items():
        pokes[addr] = record
    return pokes


# WHERE `poison=True` IS AND IS NOT USED HERE. The attribution pass re-runs both cores on an image
# whose oracle-written bytes are INVERTED, and asks whether the candidate still matches. That is
# only an attribution check while the inverted bytes are pure outputs. control_player writes the
# flags word and BRANCHES ON IT (`beq` on zero, `btst #13`), and player_death branches on the very
# lives/players_alive counters it writes — so on those cases the poisoned re-run walks a DIFFERENT
# path and the pass degrades into one extra, unrelated differential case. Measured, not assumed:
# poisoning `FLAG_ON_PLATFORM` (0x0200 -> 0xfdff) sets bit 13 and sends the run through
# hover_dead_rider instead of steer_rider. So poison is kept only where the written bytes steer
# nothing (the empty-slot and restart cases, the enemy-slot clear, the life-losing branch whose
# counter cannot reach its own threshold under inversion, and the restart tail, which branches on
# two_player_mode and never writes it) and dropped elsewhere with that reason named.


def _death_case(object_addr, pokes, poison=False):
    diffs, info = differential(ENTRY_PLAYER_DEATH, {"a0": object_addr, "_pokes": pokes},
                               lambda lib, buf: lib.g_player_death(buf, object_addr),
                               poison=poison)
    assert not diffs, f"object={object_addr:#x}\n{report(diffs)}"
    return info


def _control_case(object_addr, stick, pokes, poison=False, **run_args):
    diffs, info = differential(ENTRY_CONTROL_PLAYER,
                               {"a0": object_addr, "d0": stick, "_pokes": pokes},
                               lambda lib, buf: lib.g_control_player(buf, object_addr, stick),
                               poison=poison, **run_args)
    assert not diffs, f"object={object_addr:#x} stick={stick:#010x}\n{report(diffs)}"
    return info


def _stored(writes, addr, size=1):
    """What the ORIGINAL left at `addr`, out of the write set the differential already returned —
    so the assertion is about the very image the differential verified. Raises if the run never
    wrote there, which is the useful answer for the cases below."""
    return int.from_bytes(bytes(writes[addr + step] for step in range(size)), "big")


# ==================================================================== player_death @ 0x11f28

def test_player_death_removes_a_non_player_slot():
    """`cmpa.l #player2 ; bls`: an enemy slot is simply emptied — no life is lost, no lives row is
    repainted and no banner is posted."""
    for slot in range(2, N_OBJECTS):
        address = A_OBJECT_TABLE + slot * OBJ_SIZE
        pokes = _world({address: _rider(flags=FLAG_DEAD | FLAG_FACING_RIGHT, lives=2)})
        info = _death_case(address, pokes, poison=True)
        assert _stored(info["writes"], address, 2) == 0
        assert address + OBJ_LIVES not in info["writes"], "an enemy slot lost a life"


@pytest.mark.parametrize("object_addr,is_player", ((A_BELOW_THE_PLAYERS, True),  # below the bound...
                                                   (A_PLAYER2, True),           # ...on it...
                                                   (A_PLAYER2 + 2, False),      # ...and past it
                                                   (A_ENEMY_OBJECTS, False)))
def test_player_death_boundary_is_a_full_width_compare(object_addr, is_player):
    """The bound is `cmpa.l #player2 ; bls` on the WHOLE pointer, so it is not "is this one of the
    two players": every address at or below player 2's takes the life-losing path, including ones
    that are not a slot at all. Two pointers straddling the bound by one WORD pin it, and the
    full-width half is real — a `cmpa.w` would truncate the relocated 0x10f84 to 0x0f84 and flip two
    of the four cases.

    THE UNSIGNEDNESS OF `bls` IS NOT PROVED, and cannot be here: `bls` and `ble` differ only for a
    pointer with bit 31 set, which is outside the 1 MiB image, so no run that reached the compare
    could go on to dereference it. An odd address is not probed either — the 68000 would fault on
    the record's word fields, which is not a divergence this harness can observe.
    """
    pokes = _world({object_addr: _rider(flags=FLAG_DEAD, lives=2)})
    info = _death_case(object_addr, pokes)
    lost_a_life = object_addr + OBJ_LIVES in info["writes"]
    assert lost_a_life == is_player, f"{object_addr:#x}: took the wrong side of the bound"


@pytest.mark.parametrize("lives", (1, 2, 3, 0x7f, 0x80, 0xfe))
@pytest.mark.parametrize("flags", (FLAG_DEAD, FLAG_DEAD | FLAG_GRABBED | FLAG_IN_LAVA,
                                   0xffff, FLAG_RESPAWN | FLAG_ON_PLATFORM | FLAG_FACING_RIGHT))
def test_player_death_loses_a_life_and_arms_the_respawn(lives, flags):
    """The ordinary case: one life off, the last-drawn position forgotten, vx zeroed, and the flags
    word rewritten — troll grab, dead and in-lava cleared, respawn set, everything else kept."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=flags, lives=lives, vx=0x1234,
                                           score_ptr=P1_SCORE_PTR)})
    info = _death_case(A_OBJECT_TABLE, pokes, poison=True)
    assert _stored(info["writes"], A_OBJECT_TABLE + OBJ_LIVES) == lives - 1


def test_player_death_last_life_is_spotted_by_the_byte_wrap():
    """`subq.b #1` then `cmpi.b #$ff`: only a count that was already 0 reaches the end-of-turn
    branch, and a count of 1 goes down to 0 and keeps playing. Both are checked here, one against
    the other, because the two branches share no output at all."""
    for lives, ends_the_turn in ((1, False), (0, True)):
        pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD, lives=lives)})
        info = _death_case(A_OBJECT_TABLE, pokes)
        assert (A_PLAYERS_ALIVE in info["writes"]) == ends_the_turn, f"lives={lives}"


@pytest.mark.parametrize("players_alive,expect_game_over", ((1, True), (2, False), (0, False)))
def test_player_death_game_over_banner_needs_an_exact_one_to_zero(players_alive, expect_game_over):
    """`subq.b #1,players_alive ; bne`: the game-over banner is posted only when the counter really
    reaches 0. A counter already at 0 wraps to 0xff — non-zero — and gets a per-player banner, which
    is the faithful behaviour rather than a guard the original does not have."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD, lives=0)},
                   players_alive=players_alive)
    info = _death_case(A_OBJECT_TABLE, pokes)   # no poison: see the note above
    slot = A_MESSAGE_TABLE
    expected = A_STR_GAME_OVER if expect_game_over else A_STR_PLAYER1_OVER
    assert _stored(info["writes"], slot + MSG_STRING, 4) == expected
    assert _stored(info["writes"], slot + MSG_TIMER) == BANNER_FRAMES
    assert _stored(info["writes"], slot + MSG_SCREEN_PTR, 4) == SCREEN + (
        BANNER_GAME_OVER_DST_OFF if expect_game_over else BANNER_PLAYER_OUT_DST_OFF)


@pytest.mark.parametrize("object_addr,string,colour", ((A_OBJECT_TABLE, A_STR_PLAYER1_OVER,
                                                        BANNER_COLOR_P1),
                                                       (A_PLAYER2, A_STR_PLAYER2_OVER,
                                                        BANNER_COLOR_P2),
                                                       (A_BELOW_THE_PLAYERS, A_STR_PLAYER2_OVER,
                                                        BANNER_COLOR_P2)))
def test_player_death_per_player_banner_identifies_the_slot(object_addr, string, colour):
    """Which wording the turn's last life gets is a full `cmpa.l` against player 1's slot, so
    anything that is not exactly player 1 — including a record that is no player slot at all — is
    announced as player 2."""
    pokes = _world({object_addr: _rider(flags=FLAG_DEAD, lives=0)}, players_alive=2)
    info = _death_case(object_addr, pokes, poison=True)
    assert _stored(info["writes"], A_MESSAGE_TABLE + MSG_STRING, 4) == string
    assert _stored(info["writes"], A_MESSAGE_TABLE + MSG_COLOR) == colour
    assert _stored(info["writes"], A_MESSAGE_TABLE + MSG_SHIFT) == BANNER_PLAYER_OUT_SHIFT


@pytest.mark.parametrize("free_slot", (0, 1, 5, N_MESSAGES - 1))
def test_player_death_banner_takes_the_first_free_message_slot(free_slot):
    kinds = [1] * N_MESSAGES
    kinds[free_slot] = 0
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD, lives=0)},
                   messages=kinds, players_alive=1)
    info = _death_case(A_OBJECT_TABLE, pokes)
    slot = A_MESSAGE_TABLE + free_slot * MSG_RECORD
    assert _stored(info["writes"], slot + MSG_STRING, 4) == A_STR_GAME_OVER


def test_player_death_with_a_full_message_table_writes_over_the_vector_page():
    """find_free_message hands back 0 when all 24 slots are taken and player_death tests nothing, so
    the twelve-byte banner record lands at addresses 0..0xb — the bottom of the 68000's vector
    page. An original bug, reproduced; the differential is what proves it really happens."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD, lives=0)},
                   messages=[1] * N_MESSAGES, players_alive=1)
    info = _death_case(A_OBJECT_TABLE, pokes)
    assert _stored(info["writes"], MSG_STRING, 4) == A_STR_GAME_OVER
    assert _stored(info["writes"], MSG_KIND) != 0, "nothing was written at address 0"


def _death_fuzz_cases():
    rng = random.Random(0x11F28)                 # seeded ONCE — every chunk replays this stream
    slots = [A_OBJECT_TABLE, A_PLAYER2] + [A_OBJECT_TABLE + n * OBJ_SIZE for n in range(2, 6)]
    for i in range(240):
        kinds = [rng.choice((0, 0, rng.randrange(1, 0x100))) for _ in range(N_MESSAGES)]
        yield (i, rng.choice(slots), rng.randrange(0x10000), rng.randrange(0x100),
               rng.randrange(0x100), kinds, rng.randrange(0x10000))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_player_death_fuzz(chunk):
    ran = 0
    for i, slot, flags, lives, players_alive, kinds, vx in _death_fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        pokes = _world({slot: _rider(flags=flags, lives=lives, vx=vx)},
                       messages=kinds, players_alive=players_alive)
        _death_case(slot, pokes)
        ran += 1
    assert ran, "this shard ran no cases"


# ================================================================== control_player @ 0x11dd6

def test_control_player_empty_slot_ignores_everything_but_fire():
    """A zero flags word is an empty slot. Without fire the routine returns having written nothing
    at all, whatever else the stick says."""
    for stick in (0, STICK_LEFT, STICK_RIGHT, STICK_UP | STICK_DOWN, 0x7f):
        pokes = _world({A_OBJECT_TABLE: _rider(flags=0)}, players_alive=0)
        info = _control_case(A_OBJECT_TABLE, stick, pokes, poison=True)
        assert info["ret"] == CONTROL_RETURNED
        assert not info["writes"], "an empty slot with no fire wrote something"


@pytest.mark.parametrize("players_alive", (1, 2, 0xff))
def test_control_player_fire_on_an_empty_slot_does_nothing_while_anyone_is_alive(players_alive):
    """The game-over screen's restart is gated on players_alive being exactly 0."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=0)}, players_alive=players_alive)
    info = _control_case(A_OBJECT_TABLE, STICK_FLAP, pokes, poison=True)
    assert info["ret"] == CONTROL_RETURNED
    assert not info["writes"]


def _restart_pokes():
    return _world({A_OBJECT_TABLE: _rider(flags=0)}, players_alive=0)


@pytest.mark.parametrize("stick", (STICK_FLAP, 0xff, 0xdeadbe80))
def test_control_player_restart_sets_game_over_and_never_returns(stick):
    """The no-players-left path. Diffed at `jsr check_highscore` — the first of three unported
    calls — so what this PROVES is: both guards (fire, and players_alive == 0) route here, and the
    only memory effect before that call is game_over_flag := 1.

    What it does NOT prove: the `addq.w #8,a7` that discards two return addresses (stack, which the
    diff drops and the C models as CONTROL_RESTART instead), nor anything from check_highscore
    onwards — check_highscore, init_game and init_video are all unported, and the tail between the
    last two is verified separately below. `stick` also shows that only bit 7 is consulted: a
    longword with garbage in every other bit restarts just the same.
    """
    pokes = _restart_pokes()
    info = _control_case(A_OBJECT_TABLE, stick, pokes, stop_pc=CHECKPOINT_BEFORE_HISCORE,
                         poison=True)
    assert info["ret"] == CONTROL_RESTART
    assert _stored(info["writes"], A_GAME_OVER_FLAG) == GAME_OVER_SET
    assert set(info["writes"]) == {A_GAME_OVER_FLAG}, "the prefix wrote more than game_over_flag"


@pytest.mark.parametrize("stick", (STICK_FLAP, 0xff, 0xdeadbe80))
def test_control_player_restart_really_does_not_return(stick):
    """...and it is the restart, not a fall-through: without the checkpoint the run cannot finish.
    This is the pair the checkpoint above needs — `stop_pc` reports success at the sentinel too."""
    _never_returns(_restart_pokes(), ENTRY_CONTROL_PLAYER, {"a0": A_OBJECT_TABLE, "d0": stick})


# ---- the live rider under the stick ----

_STEER_STICKS = (0, STICK_FLAP, STICK_LEFT, STICK_RIGHT, STICK_LEFT | STICK_RIGHT,
                 STICK_FLAP | STICK_LEFT, STICK_FLAP | STICK_RIGHT, STICK_UP | STICK_DOWN, 0xff)


@pytest.mark.parametrize("stick", _STEER_STICKS)
@pytest.mark.parametrize("flags", (FLAG_ON_PLATFORM, FLAG_RESPAWN,
                                   FLAG_RESPAWN | FLAGS_FLAPPING, FLAGS_FLAPPING,
                                   FLAG_FACING_RIGHT | FLAG_FLAP_LOW, 0xffff & ~FLAG_DEAD))
def test_control_player_steers_a_live_rider(stick, flags):
    """Fire drives BOTH flap bits together; the target speed is the rider's own vx, or nothing while
    it waits to respawn, or a fixed walk speed when the stick is pushed — right winning over left.
    The flags cases include one with only ONE of the two flap bits set, which a candidate that
    tracked a single bit would get wrong."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=flags, vx=0x0123)})
    info = _control_case(A_OBJECT_TABLE, stick, pokes)   # no poison: see the note above
    assert info["ret"] == CONTROL_RETURNED


@pytest.mark.parametrize("vx", (0, 1, 0x7fff, 0x8000, 0xfffc, 0xffff))
def test_control_player_target_speed_copies_the_whole_word(vx):
    """With no stick pushed and no respawn pending the target is a straight word copy of vx, so a
    reconstruction that clamped or sign-mangled it diverges on the extremes."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_ON_PLATFORM, vx=vx)})
    info = _control_case(A_OBJECT_TABLE, 0, pokes)   # no poison: see the note above
    assert _stored(info["writes"], A_OBJECT_TABLE + 0x0c, 2) == vx


# ---- the dead rider ----

_EXIT_X = (0, 0x12f, DEAD_EXIT_LEFT_LO, 0x131, DEAD_EXIT_LEFT_HI, 0x134, 0x13b,
           DEAD_EXIT_RIGHT_X, 0x13d, 0x7fff, 0x8000, 0xffff)


@pytest.mark.parametrize("x", _EXIT_X)
@pytest.mark.parametrize("facing_right", (False, True))
def test_control_player_dead_rider_exit_window(x, facing_right):
    """Where the corpse's drift ends the turn. Facing right that is a plain `>=` threshold; facing
    left it is a four-pixel WINDOW, and an x past its top hovers on — an asymmetry a reconstruction
    that mirrored the two would fail on 0x134..0x13b. 0x8000 and 0xffff pin the SIGNEDNESS: both are
    far to the right unsigned, and neither takes the exit.

    poison is deliberately not used: the erase pass's destination is one of the bytes player_death
    then zeroes, and an inverted pointer would send the blit far outside the image.
    """
    flags = FLAG_DEAD | (FLAG_FACING_RIGHT if facing_right else 0)
    pokes = _world({A_OBJECT_TABLE: _rider(flags=flags, x=x, prev_x=x, y=0x50, lives=3)})
    info = _control_case(A_OBJECT_TABLE, 0, pokes)
    assert info["ret"] == CONTROL_RETURNED

    # Every threshold is a SIGNED word compare (`cmpi.w` + blt/ble), so an x with bit 15 set is a
    # long way to the LEFT of the playfield and no facing takes the exit.
    signed_x = x - 0x10000 if x >= 0x8000 else x
    left = (signed_x >= DEAD_EXIT_RIGHT_X) if facing_right \
        else (DEAD_EXIT_LEFT_LO <= signed_x <= DEAD_EXIT_LEFT_HI)
    assert (A_OBJECT_TABLE + OBJ_LIVES in info["writes"]) == left, \
        f"x={x:#x} facing_right={facing_right}: took the wrong exit"


@pytest.mark.parametrize("y", (0, 1, HOVER_BAND_HIGH_Y, HOVER_BAND_HIGH_Y + 1, 0x41, 0x42, 0x43,
                               HOVER_BAND_MID_Y, HOVER_BAND_MID_Y + 1, 0x8b, 0x8c, 0x8d, 0xc8,
                               0x7fff, 0x8000, 0xffff))
@pytest.mark.parametrize("vy", (0, 1, 0x7fff, 0x8000, 0xffff))
def test_control_player_dead_rider_hover(y, vy):
    """The hover ladder and the wingbeat toggle. Every compare on the way is SIGNED, so the two
    negative y values pick the highest band and a negative vy stops the beating."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD | FLAGS_FLAPPING, x=0, y=y, vy=vy)})
    info = _control_case(A_OBJECT_TABLE, STICK_FLAP, pokes)   # no poison: see the note above
    assert info["ret"] == CONTROL_RETURNED

    target = HOVER_TARGET_HIGH if y <= HOVER_BAND_HIGH_Y or y >= 0x8000 else \
        HOVER_TARGET_MID if y <= HOVER_BAND_MID_Y else HOVER_TARGET_LOW
    assert _stored(info["writes"], A_OBJECT_TABLE + 0x46, 2) == target


@pytest.mark.parametrize("vx,drift", ((0, PLAYER_STEER_VX), (1, PLAYER_STEER_VX),
                                      (0x7fff, PLAYER_STEER_VX),
                                      (0x8000, -PLAYER_STEER_VX & 0xffff),
                                      (0xffff, -PLAYER_STEER_VX & 0xffff)))
def test_control_player_dead_rider_keeps_drifting_the_way_it_was(vx, drift):
    """`tst.w ; bge` then `neg.w` on the STORED word: a vx of exactly 0 counts as drifting right."""
    pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD, x=0, y=0x50, vx=vx)})
    info = _control_case(A_OBJECT_TABLE, 0, pokes)   # no poison: see the note above
    assert _stored(info["writes"], A_OBJECT_TABLE + 0x0c, 2) == drift


# The three y values that sit EXACTLY on the target their own band selects — the boundary of the
# `bgt` that decides between toggling and clearing. They were a coverage hole a mutation sweep
# found: with both flap bits already set a toggle and a clear leave the same word, so `>` and `>=`
# are only distinguishable from a start state where the bits are CLEAR.
_ON_TARGET_Y = (HOVER_TARGET_HIGH, HOVER_TARGET_MID, HOVER_TARGET_LOW)


def test_control_player_dead_rider_flap_bits_toggle_rather_than_set():
    """Below its target and not falling, the corpse FLIPS both flap bits every frame; anywhere else
    it clears them. Started from each of the four combinations of the pair, since a `bset` and a
    `bchg` are indistinguishable from the two states where the bit is already clear."""
    for start in (0, FLAG_FLAP_LOW, FLAG_FLAP_HIGH, FLAGS_FLAPPING):
        for y, vy in ((0xc8, 0), (0xc8, 0xffff), (1, 0)) + tuple((y, 0) for y in _ON_TARGET_Y):
            pokes = _world({A_OBJECT_TABLE: _rider(flags=FLAG_DEAD | start, x=0, y=y, vy=vy)})
            _control_case(A_OBJECT_TABLE, 0, pokes)   # no poison: see the note above


def _control_fuzz_cases():
    rng = random.Random(0x11DD6)                 # seeded ONCE — every chunk replays this stream
    for i in range(320):
        # x is drawn from the exit window's neighbourhood as often as from the whole range, so the
        # death branch is reached often rather than once in 8000 cases.
        x = rng.choice((rng.randrange(0x10000), rng.randrange(0x12c, 0x140)))
        yield (i, rng.choice((A_OBJECT_TABLE, A_PLAYER2)),
               rng.choice((0, rng.randrange(0x10000), rng.randrange(0x10000) | FLAG_DEAD)),
               x, rng.randrange(0x10000), rng.randrange(0x10000), rng.randrange(0x10000),
               harness.hi_garbage(rng, rng.randrange(0x100)), rng.randrange(1, 4),
               rng.randrange(0x100))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_control_player_fuzz(chunk):
    """The whole input surface bar the restart path, which needs a checkpoint and is covered above.
    players_alive stays non-zero so a fuzzed empty slot with fire simply returns rather than
    diverging into the unported restart. The stick carries hi_garbage: `btst` on a data register
    reads the longword, and everything above bit 7 must stay dead."""
    ran = 0
    for i, slot, flags, x, y, vx, vy, stick, players_alive, lives in _control_fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        pokes = _world({slot: _rider(flags=flags, x=x, prev_x=x, y=y, vx=vx, vy=vy, lives=lives)},
                       players_alive=players_alive)
        _control_case(slot, stick, pokes)
        ran += 1
    assert ran, "this shard ran no cases"


# ============================================ control_player's restart tail @ 0x11e50

def _restart_tail_pokes(two_player):
    """The staging both restart-tail cases share, so the `_never_returns` pair below really is the
    same case as the checkpointed one — including the two_player arm it selects."""
    return _world({A_OBJECT_TABLE: _rider(lives=0, score_units=UNWRITTEN_B),
                   A_PLAYER2: _rider(flags=0xffff, lives=0, score_units=UNWRITTEN_B,
                                     score_ptr=P2_SCORE_PTR)},
                  players_alive=0, two_player=two_player)


@pytest.mark.parametrize("two_player", (0, 1, 0xff))
def test_restart_tail_sets_up_the_new_game(two_player):
    """The piece of the restart path BETWEEN init_game and init_video, entered at its own head and
    diffed at the `jsr init_video` that ends it.

    What this PROVES: players_alive, player 2's slot (emptied in a one-player game, given a score
    digit and lives in a two-player one) and player 1's, all as the original leaves them.

    What it does NOT prove: that control_player reaches here at all — check_highscore and init_game
    sit in between and neither is ported, which is exactly why src/player.c does not call
    restart_reset_players from control_player. Nor anything from init_video onwards.
    """
    pokes = _restart_tail_pokes(two_player)
    diffs, info = differential(ENTRY_RESTART_TAIL, {"_pokes": pokes},
                               lambda lib, buf: lib.g_restart_reset_players(buf),
                               stop_pc=CHECKPOINT_BEFORE_INIT_VIDEO, poison=True)
    assert not diffs, f"two_player={two_player}\n{report(diffs)}"

    expected = PLAYERS_ALIVE_TWO if two_player else PLAYERS_ALIVE_ONE
    assert _stored(info["writes"], A_PLAYERS_ALIVE) == expected
    assert _stored(info["writes"], A_OBJECT_TABLE + OBJ_LIVES) == PLAYER_START_LIVES
    assert _stored(info["writes"], A_OBJECT_TABLE + OBJ_SCORE_LAST_DIGIT) == SCORE_UNITS_ZERO
    if two_player:
        assert _stored(info["writes"], A_PLAYER2 + OBJ_LIVES) == PLAYER_START_LIVES
    else:
        assert _stored(info["writes"], A_PLAYER2, 2) == 0


@pytest.mark.parametrize("two_player", (0, 1, 0xff))
def test_restart_tail_really_does_not_return(two_player):
    """The pair for the checkpoint above, over the SAME three arms and the same staging: the tail
    ends in `jsr init_video` and a `jmp` into the main loop, so a run entered here never reaches an
    `rts` of its own — whichever side of `tst.b two_player_mode` it took."""
    _never_returns(_restart_tail_pokes(two_player), ENTRY_RESTART_TAIL)


# ================================================================================ mirror pins
#
# Everything above restates addresses, record offsets and constants that really live in
# ../../names.txt and include/player.h. Nothing makes a drifted mirror FAIL on its own: both cores
# would run against the real address, agree byte-for-byte on the game's own static data and go
# green while the staged inputs landed in dead memory. These pin the mirrors, the way
# test_constants.py pins the other batteries' — hence the import of its scraper.

def test_entry_addresses_match_names_txt():
    for addr, name in ((ENTRY_CONTROL_PLAYER, "control_player"),
                       (ENTRY_PLAYER_DEATH, "player_death"),
                       (A_CHECK_HIGHSCORE, "check_highscore"),
                       (A_INIT_VIDEO, "init_video")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_checkpoints_are_the_instructions_they_claim_to_be():
    """The three inner addresses are not function entries, so names.txt cannot pin them. Pin them
    against the ORIGINAL'S OWN ENCODING instead — the opcode and its relocated operand — so that a
    checkpoint drifting onto a neighbouring instruction fails here rather than silently diffing at
    the wrong place. (Precedent: snd_tone_sweep's unobservable register values, ../STATUS.md.)"""
    image = harness.BASE_IMAGE

    def word(addr):
        return int.from_bytes(bytes(image[addr:addr + 2]), "big")

    def long(addr):
        return int.from_bytes(bytes(image[addr:addr + 4]), "big")

    assert (word(CHECKPOINT_BEFORE_HISCORE), long(CHECKPOINT_BEFORE_HISCORE + 2)) \
        == (JSR_ABS_LONG, A_CHECK_HIGHSCORE), "the pre-check_highscore checkpoint moved"
    assert (word(CHECKPOINT_BEFORE_INIT_VIDEO), long(CHECKPOINT_BEFORE_INIT_VIDEO + 2)) \
        == (JSR_ABS_LONG, A_INIT_VIDEO), "the pre-init_video checkpoint moved"
    assert (word(ENTRY_RESTART_TAIL), long(ENTRY_RESTART_TAIL + 2)) \
        == (TST_B_ABS_LONG, A_TWO_PLAYER_MODE), "the restart tail's entry moved"


def test_global_addresses_match_names_txt():
    for addr, name in ((A_PLAYERS_ALIVE, "players_alive"), (A_TWO_PLAYER_MODE, "two_player_mode"),
                       (A_GAME_OVER_FLAG, "game_over_flag"), (A_SCREEN_BASE, "screen_base"),
                       (A_MESSAGE_TABLE, "message_table"), (A_OBJECT_TABLE, "object_table"),
                       (A_PLAYER2, "player2"), (A_ENEMY_OBJECTS, "enemy_objects"),
                       (A_TEXT_PTR, "text_ptr"), (A_STR_GAME_OVER, "str_game_over")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_mirrored_flag_bits_match_the_headers():
    """Every flags-word bit this file stages equals the one src/player.c compiles against.

    These bits decide which SHAPE each case stages, so an unpinned one does not fail loudly: it
    quietly turns "a dead rider" into a live one and both cores agree on a case that tests nothing.
    The ones spelled `(1u << N)` needed a scraper of their own here until test_constants' `_defines`
    learned to read that form.
    """
    joust_h, world_h, player_h = (_defines("include/joust.h"), _defines("include/world.h"),
                                  _defines("include/player.h"))
    for name, value, source in (("OBJ_FLAG_GRABBED", FLAG_GRABBED, world_h),
                                ("OBJ_FLAG_IN_LAVA", FLAG_IN_LAVA, joust_h),
                                ("OBJ_FLAG_FACING_RIGHT", FLAG_FACING_RIGHT, joust_h),
                                ("OBJ_FLAGS_FLAPPING", FLAGS_FLAPPING, player_h),
                                ("OBJ_FLAG_RESPAWN", FLAG_RESPAWN, joust_h),
                                ("OBJ_FLAG_ON_PLATFORM", FLAG_ON_PLATFORM, joust_h),
                                ("OBJ_FLAG_DEAD", FLAG_DEAD, joust_h)):
        assert source[name] == value, f"{name}: header has {source[name]:#x}, test stages {value:#x}"

    # FLAG_FLAP_LOW and FLAG_FLAP_HIGH are staged individually (a rider with only one of the pair
    # set is what distinguishes a `bset` from the mask), so pin them against the pair as well.
    assert FLAG_FLAP_LOW | FLAG_FLAP_HIGH == FLAGS_FLAPPING
    assert FLAG_FLAP_LOW != FLAG_FLAP_HIGH


def test_joystick_bits_match_input_c():
    """src/input.c's high-score stick reader names the same three bits. Two layers read them now, so
    they have earned a shared header (see the note in include/player.h); until that lands this is
    the pin that keeps the two spellings equal."""
    input_c, player_h = _defines("src/input.c"), _defines("include/player.h")
    for stick_name, joy_name in (("STICK_FLAP", "JOY_FIRE"), ("STICK_RIGHT", "JOY_RIGHT"),
                                 ("STICK_LEFT", "JOY_LEFT")):
        assert player_h[stick_name] == input_c[joy_name], \
            f"{stick_name} ({player_h[stick_name]:#x}) != input.c's {joy_name}"


def test_mirrored_constants_match_the_headers():
    """Every constant this file restates equals the one src/player.c compiles against."""
    header = _defines("include/player.h")
    mirrored = {
        "A_two_player_mode": A_TWO_PLAYER_MODE,
        "STICK_FLAP": STICK_FLAP, "STICK_RIGHT": STICK_RIGHT, "STICK_LEFT": STICK_LEFT,
        "PLAYER_STEER_VX": PLAYER_STEER_VX,
        "DEAD_EXIT_RIGHT_X": DEAD_EXIT_RIGHT_X, "DEAD_EXIT_LEFT_LO": DEAD_EXIT_LEFT_LO,
        "DEAD_EXIT_LEFT_HI": DEAD_EXIT_LEFT_HI,
        "HOVER_BAND_HIGH_Y": HOVER_BAND_HIGH_Y, "HOVER_BAND_MID_Y": HOVER_BAND_MID_Y,
        "HOVER_TARGET_HIGH": HOVER_TARGET_HIGH, "HOVER_TARGET_MID": HOVER_TARGET_MID,
        "HOVER_TARGET_LOW": HOVER_TARGET_LOW,
        "CONTROL_RETURNED": CONTROL_RETURNED, "CONTROL_RESTART": CONTROL_RESTART,
        "GAME_OVER_SET": GAME_OVER_SET,
        "PLAYERS_ALIVE_ONE": PLAYERS_ALIVE_ONE, "PLAYERS_ALIVE_TWO": PLAYERS_ALIVE_TWO,
        "PLAYER_START_LIVES": PLAYER_START_LIVES, "SCORE_UNITS_ZERO": SCORE_UNITS_ZERO,
        "LIVES_EXHAUSTED": LIVES_EXHAUSTED,
        "STR_PLAYER1_OVER": A_STR_PLAYER1_OVER, "STR_PLAYER2_OVER": A_STR_PLAYER2_OVER,
        "BANNER_FRAMES": BANNER_FRAMES,
        "BANNER_GAME_OVER_DST_OFF": BANNER_GAME_OVER_DST_OFF,
        "BANNER_PLAYER_OUT_DST_OFF": BANNER_PLAYER_OUT_DST_OFF,
        "BANNER_GAME_OVER_SHIFT": BANNER_GAME_OVER_SHIFT,
        "BANNER_PLAYER_OUT_SHIFT": BANNER_PLAYER_OUT_SHIFT,
        "BANNER_COLOR_GAME_OVER": BANNER_COLOR_GAME_OVER,
        "BANNER_COLOR_P1": BANNER_COLOR_P1, "BANNER_COLOR_P2": BANNER_COLOR_P2,
    }
    for name, value in mirrored.items():
        assert header[name] == value, f"{name}: player.h has {header[name]:#x}, test has {value:#x}"

    # The record fields _object() encodes positionally, which no other assertion can catch drifting.
    for defines, origin, fields in (
            (_defines("include/score.h"), "score.h", {"OBJ_LIVES": OBJ_LIVES,
                                                      "OBJ_SCORE_LAST_DIGIT": OBJ_SCORE_LAST_DIGIT,
                                                      "OBJ_SCORE_PTR": 0x36,
                                                      "OBJ_SCORE_SHIFT": 0x3a,
                                                      "MSG_TIMER": MSG_TIMER,
                                                      "MSG_COLOR": MSG_COLOR,
                                                      "MSG_SHIFT": MSG_SHIFT,
                                                      "MSG_STRING": MSG_STRING,
                                                      "STR_GAME_OVER": A_STR_GAME_OVER}),
            (_defines("include/object.h"), "object.h", {"MSG_KIND": MSG_KIND,
                                                        "MSG_SCREEN_PTR": MSG_SCREEN_PTR,
                                                        "MSG_RECORD": MSG_RECORD,
                                                        "A_message_table": A_MESSAGE_TABLE}),
            (_defines("include/joust.h"), "joust.h", {"OBJ_SIZE": OBJ_SIZE, "OBJ_FLAGS": 0x00,
                                                      "OBJ_X": 0x02,
                                                      "OBJ_Y": 0x04, "OBJ_VX": 0x06,
                                                      "OBJ_VY": 0x08, "OBJ_TARGET_VX": 0x0c,
                                                      "OBJ_PREV_X": 0x10,
                                                      "OBJ_PREV_DST": 0x14, "OBJ_PREV_SRC": 0x18,
                                                      "OBJ_PREV_ROWS": 0x1c,
                                                      "OBJ_PREV_SHIFT": 0x1d,
                                                      "OBJ_TARGET_Y": 0x46}),
            (_defines("include/addrs.h"), "addrs.h", {"A_screen_base": A_SCREEN_BASE,
                                                      "A_object_table": A_OBJECT_TABLE}),
            (_defines("include/draw.h"), "draw.h", {"A_player2": A_PLAYER2,
                                                    "A_text_ptr": A_TEXT_PTR})):
        for name, value in fields.items():
            assert defines[name] == value, (f"{name}: {origin} has {defines[name]:#x}, "
                                            f"test has {value:#x}")
