"""The sim-to-platform event ring, the cue map, and the sim's hashed surface.

The ring is the ONLY thing the simulation says out loud.  Everything else in
GameState is state the next tick reads back; a cue and a HUD line are read by
the platform layer and by nobody else, so a defect in this file is invisible to
every other test in the suite unless it is pinned here.
"""
import ctypes
import re

import pytest

import aihelp
import blackice
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

QUEUE_SIZE = CONST["EVENT_QUEUE_SIZE"]
RESERVE = CONST["EVENT_QUEUE_MESSAGE_RESERVE"]
#: One slot is always left empty, which is what makes head == tail mean "empty".
CAPACITY = QUEUE_SIZE - 1

SFX = CONST["EV_SFX_BUSTER_SHOT"]
OTHER_SFX = CONST["EV_SFX_GATE_OPEN"]
MESSAGE = CONST["EV_MSG_CYCLES"]

EVENT_SFX_HEADER = blackice.ROOT / "include" / "event_sfx.h"
AUDIO_BANK_IDS = blackice.ROOT / "audio" / "blackice_sfx_ids.h"


@pytest.fixture
def queue(glib):
    """An EventQueue on its own, driven through the engine's own entry points.

    Not a GameState: the ring's overflow behaviour needs more pushes than one
    tick of the sim will ever make, and reaching them through gameplay would
    test the gameplay instead of the ring.
    """
    aihelp.bind(glib)
    ring = aihelp.EventQueue()
    glib.event_reset(ctypes.byref(ring))
    return ring


def push(glib, ring, *ids):
    for event_id in ids:
        glib.event_push(ctypes.byref(ring), event_id)


def drain(glib, ring):
    out = []
    slot = ctypes.c_uint8()
    while glib.event_pop(ctypes.byref(ring), ctypes.byref(slot)):
        out.append(slot.value)
        assert len(out) <= QUEUE_SIZE, "event_pop is not draining the ring"
    return out


# ---------------------------------------------------------------------------
# the ring
# ---------------------------------------------------------------------------

def test_the_ring_hands_back_what_was_pushed_in_order(glib, queue):
    push(glib, queue, SFX, MESSAGE, OTHER_SFX)
    assert drain(glib, queue) == [SFX, MESSAGE, OTHER_SFX]
    assert drain(glib, queue) == [], "a drained ring is empty"


def test_a_repeated_cue_is_pushed_once(glib, queue):
    """One channel plays one thing at a time (DESIGN 16), so a second copy of a
    cue already waiting is not a quieter version of it - it is nothing at all.
    One tick can wake four Watchdogs, and four snarls are one snarl."""
    push(glib, queue, SFX, SFX, SFX)
    assert drain(glib, queue) == [SFX]


def test_a_cue_can_be_raised_again_once_it_has_been_played(glib, queue):
    """The dedupe is per DRAIN, not for ever: the platform layer empties the
    ring every frame, and a Buster firing on two consecutive ticks is two
    shots."""
    push(glib, queue, SFX)
    assert drain(glib, queue) == [SFX]
    push(glib, queue, SFX)
    assert drain(glib, queue) == [SFX]


def test_a_repeated_message_is_still_repeated(glib, queue):
    """Two pickups collected on one tick are two HUD lines, and the drainer
    decides which of them the 38-character field shows.  The dedupe is a
    property of the one-shot sound channel, not of the message block."""
    push(glib, queue, MESSAGE, MESSAGE)
    assert drain(glib, queue) == [MESSAGE, MESSAGE]


def test_a_full_ring_drops_the_new_cue_and_keeps_the_queued_ones(glib, queue):
    """DESIGN 16: a one-shot that cannot play is dropped and never queued.  The
    cue already in the ring is the one the player is about to hear."""
    messages = [MESSAGE] * CAPACITY
    push(glib, queue, *messages)
    push(glib, queue, SFX)

    assert queue.dropped == 1
    assert drain(glib, queue) == messages, "the queued cues, not the newest one"


def test_a_full_ring_drops_a_new_message_too(glib, queue):
    """The reserve is for messages, not a guarantee of infinite room: once even
    the reserved slots are gone the newest line is dropped like any other cue,
    and the ring's contents do not shift.  Evicting the OLDEST instead would
    make what the player sees depend on what happened after it."""
    messages = [CONST["EV_MSG_ALPHA_REQUIRED"] + i for i in range(CAPACITY)]
    push(glib, queue, *messages)
    push(glib, queue, CONST["EV_MSG_CONNECTION_TERMINATED"])

    assert queue.dropped == 1
    assert drain(glib, queue) == messages, "the ring shifted instead of dropping"


def test_a_crowded_tick_never_costs_a_hud_line(glib, queue):
    """A dropped sound is a noise the player can see the cause of; a dropped HUD
    line is a rule they are never told.  So the last few slots are reserved: an
    SFX push is refused while fewer than EVENT_QUEUE_MESSAGE_RESERVE remain,
    and a message can always still get in."""
    distinct_sfx = [CONST["EV_SFX_BUSTER_SHOT"] + i for i in range(QUEUE_SIZE)]
    push(glib, queue, *distinct_sfx)

    drained = drain(glib, queue)
    assert len(drained) == CAPACITY - RESERVE, \
        "sound may fill the ring only up to the reserve"

    push(glib, queue, *distinct_sfx)
    push(glib, queue, MESSAGE)
    assert MESSAGE in drain(glib, queue), "a HUD line must always fit"


def test_the_no_op_event_is_never_queued(glib, queue):
    """trace.c's CLEAN band has no message of its own, so EV_NONE reaches the
    ring on the way past.  It is not a cue and must not take a slot."""
    push(glib, queue, CONST["EV_NONE"], SFX)
    assert drain(glib, queue) == [SFX]


def test_the_sim_pushes_the_hud_line_before_the_tone(glib):
    """A refusal is a line and a tone, and the line is what teaches the rule.
    Pushing it first is what makes the reserve unnecessary in the common case
    and the ordering visible in the drain."""
    rows = ["########",
            "#@.1...#",
            "########"]
    header = "# name: EVENTS\n# start_facing: 256\n# trace_base_rate: 0\n\n"
    level = aihelp.level_from_rows(glib, rows, header)
    state = aihelp.new_state(glib, level)
    aihelp.clear_events(state)

    for _ in range(30):
        aihelp.step(glib, state, CONST["INPUT_FORWARD"])
        events = aihelp.drain_events(state)
        if CONST["EV_MSG_ALPHA_REQUIRED"] in events:
            assert events.index(CONST["EV_MSG_ALPHA_REQUIRED"]) \
                < events.index(CONST["EV_SFX_DOOR_REFUSAL"])
            return
    pytest.fail("the locked gate never refused")


# ---------------------------------------------------------------------------
# the EventId -> SFX map
# ---------------------------------------------------------------------------

def parse_defines(path):
    """The integer #defines of a header, decimal or hexadecimal."""
    pattern = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(0x[0-9a-fA-F]+|\d+)\s*$", re.M)
    return {name: int(value, 0) for name, value in pattern.findall(path.read_text())}


def test_the_cue_map_names_the_same_bank_the_audio_pass_generated(glib):
    """include/event_sfx.h restates the bank's indices because audio/ is outside
    the engine's include path and its id header is generated.  Two copies of a
    number in two languages is exactly the drift CLAUDE.md asks to be pinned by
    a test rather than hoped for."""
    engine = parse_defines(EVENT_SFX_HEADER)
    bank = parse_defines(AUDIO_BANK_IDS)

    assert engine["EVENT_SFX_BANK_COUNT"] == bank["BLACKICE_SFX_COUNT"]
    for name, value in bank.items():
        if not name.startswith("SFX_"):
            continue
        mirrored = "EVENT_" + name
        assert mirrored in engine, "the cue map has no %s" % mirrored
        assert engine[mirrored] == value, name


def test_every_event_id_says_what_it_sounds_like(glib):
    """The map covers the WHOLE enum, so "no sound" is always a decision.  Five
    cues have no sample of their own - the gate close, the door refusal, the
    throttle change and the Tracer's two - and each is mapped to the nearest
    thing the bank does have rather than left silent."""
    aihelp.bind(glib)
    count = CONST["EV_ID_COUNT"]
    bank_count = parse_defines(EVENT_SFX_HEADER)["EVENT_SFX_BANK_COUNT"]
    none = parse_defines(EVENT_SFX_HEADER)["EVENT_SFX_NONE"]

    for event_id in range(1, count):
        cue = glib.event_sfx(event_id)
        if event_id >= CONST["EV_MSG_ALPHA_REQUIRED"]:
            assert cue == none, "message %d must be silent" % event_id
        else:
            assert cue < bank_count, \
                "SFX id %d maps to %d, which is not a bank cue" % (event_id, cue)
    assert glib.event_sfx(CONST["EV_NONE"]) == none
    assert glib.event_sfx(count) == none, "an id off the end asks for no sound"


@pytest.mark.parametrize("event,substitute", [
    ("EV_SFX_GATE_CLOSE", "EV_SFX_GATE_OPEN"),
    ("EV_SFX_TRACER_PING", "EV_SFX_WATCHDOG_SNARL"),
    ("EV_SFX_TRACER_SIREN", "EV_SFX_EXFIL_SIREN"),
])
def test_the_documented_substitutions_are_the_ones_the_map_makes(glib, event, substitute):
    """The five substitutions are a design decision written down in
    event_sfx.h's header comment.  Authoring the missing samples must be a
    deliberate change to this table and not something that happens by accident."""
    aihelp.bind(glib)
    assert glib.event_sfx(CONST[event]) == glib.event_sfx(CONST[substitute])


# ---------------------------------------------------------------------------
# the hashed surface
# ---------------------------------------------------------------------------

HASH_ROOM = [
    "#######",
    "#.....#",
    "#..@..#",
    "#.....#",
    "#######",
]

#: Every game-layer field the replay hash has to cover, with a value that
#: differs from the one a fresh state holds.  A field missing from sim_hash is a
#: whole class of divergence the replay cannot see.
HASHED_FIELDS = [
    ("prev_bumped_cell", 7),
    ("next_sector_index", 3),
    ("deaths_this_sector", 2),
    ("palette_variant", CONST["PALETTE_VARIANT_CORRUPT"]),
    ("music_tempo_bpm", CONST["TRACE_TEMPO_CORRUPT"]),
    ("enemy_tier", CONST["ENEMY_TIER_HOSTILE"]),
    ("trace_band", CONST["TRACE_BAND_CORRUPT"]),
    ("bumped_cell", 9),
    ("kills", 4),
    ("data_caches", 2),
    ("tokens", CONST["TOKEN_BETA_BIT"]),
    ("phase", CONST["PHASE_LEVEL_CLEAR"]),
    ("route_ticks", 11),
    ("weapon_cooldown", 3),
    ("muzzle_flash", 1),
    ("enemy_has_los", 1),
]


@pytest.mark.parametrize("field,value", HASHED_FIELDS)
def test_every_published_field_moves_the_replay_hash(glib, field, value):
    level = aihelp.level_from_rows(glib, HASH_ROOM,
                                   "# name: HASH\n# start_facing: 0\n\n")
    state = aihelp.new_state(glib, level)
    before = glib.game_state_hash(aihelp.ref(state))

    assert getattr(state.game, field) != value, "%s already holds the probe" % field
    setattr(state.game, field, value)
    assert glib.game_state_hash(aihelp.ref(state)) != before, \
        "%s is not in the hash, so a replay cannot see it change" % field


def test_the_event_ring_is_part_of_the_hashed_surface(glib):
    """The ring is the sim's output.  A change that plays the wrong cue, plays
    one twice, or loses a HUD line moves no other field in GameState, so without
    the ring a whole class of regression is invisible to the replay."""
    level = aihelp.level_from_rows(glib, HASH_ROOM,
                                   "# name: HASH\n# start_facing: 0\n\n")
    state = aihelp.new_state(glib, level)
    aihelp.clear_events(state)
    empty = glib.game_state_hash(aihelp.ref(state))

    glib.event_push(ctypes.byref(state.game.events), SFX)
    with_one = glib.game_state_hash(aihelp.ref(state))
    assert with_one != empty

    glib.event_push(ctypes.byref(state.game.events), OTHER_SFX)
    assert glib.game_state_hash(aihelp.ref(state)) != with_one, \
        "the ring's contents, not just its length"

    aihelp.drain_events(state)
    assert glib.game_state_hash(aihelp.ref(state)) == empty, \
        "a drained ring hashes the same as one that was never filled"
