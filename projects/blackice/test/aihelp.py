"""Shared helpers for the game-layer tests: the ctypes mirror of the runtime
entity table, hand-built levels, and a BFS planner that drives the player.

The engine half of GameState is mirrored in blackice.py.  The game layer sits
after it, and this module models exactly the part the game-layer tests read, at
the offset host/abi.c publishes - so a field added to either half fails a test
instead of silently shifting one.
"""
import ctypes
import math

import pytest

import blackice
from blackice import CONST

# ---------------------------------------------------------------------------
# constants the game layer adds, parsed from its own headers
# ---------------------------------------------------------------------------

CONST.update(blackice._parse_defines([
    blackice.ROOT / "include" / "game_rules.h",
    blackice.ROOT / "include" / "ai.h",
    blackice.ROOT / "include" / "entities.h",
    blackice.ROOT / "include" / "events.h",
]))
CONST.update(blackice._parse_enums([blackice.ROOT / "include" / "events.h"]))


def _resolve_cell_macros():
    """game_rules.h states distances as CELLS(n) and CELL_TENTHS(n).

    blackice.py's integer-define parser cannot evaluate a function-like macro,
    so every distance in the rules header would be missing from CONST and the
    tests would have to restate it - which is exactly the drift the parser
    exists to prevent.  Re-evaluate just those lines with the two macros
    supplied as Python functions.
    """
    import re

    cell_units = CONST["CELL_UNITS"]
    namespace = dict(CONST)
    namespace["CELLS"] = lambda n: n * cell_units
    namespace["CELL_TENTHS"] = lambda n: (n * cell_units) // 10
    source = (blackice.ROOT / "include" / "game_rules.h").read_text()
    pattern = re.compile(r"^#define[ \t]+([A-Z][A-Z0-9_]*)[ \t]+(.+)$", re.M)
    for name, body in pattern.findall(source):
        body = re.sub(r"/\*.*", "", body).strip()
        if "CELLS(" not in body and "CELL_TENTHS(" not in body:
            continue
        CONST[name] = int(eval(body, {"__builtins__": {}}, namespace))
        namespace[name] = CONST[name]


_resolve_cell_macros()

MAP_MAX_CELLS = blackice.MAP_MAX_CELLS
LEVEL_MAX_ENTITIES = blackice.LEVEL_MAX_ENTITIES
NAV_QUEUE_MAX = CONST["NAV_QUEUE_MAX"]
NAV_UNREACHABLE = CONST["NAV_UNREACHABLE"]
EVENT_QUEUE_SIZE = CONST["EVENT_QUEUE_SIZE"]
CELL = blackice.CELL_UNITS
CENTRE = CELL // 2

ENT_WATCHDOG = CONST["ENT_WATCHDOG"]
ENT_SENTRY = CONST["ENT_SENTRY"]
ENT_TRACER = CONST["ENT_TRACER"]


class EntityRuntime(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint8), ("state", ctypes.c_uint8),
        ("flags", ctypes.c_uint8), ("hp", ctypes.c_uint8),
        ("x", ctypes.c_int16), ("y", ctypes.c_int16),
        ("facing", ctypes.c_uint16),
        ("state_timer", ctypes.c_uint16), ("attack_timer", ctypes.c_uint16),
        ("claim_cell", ctypes.c_uint16), ("spawn_cell", ctypes.c_uint16),
        ("target_x", ctypes.c_int16), ("target_y", ctypes.c_int16),
    ]


class EntityOccupancy(ctypes.Structure):
    _fields_ = [("owner", ctypes.c_uint8 * MAP_MAX_CELLS)]


class NavField(ctypes.Structure):
    # `steps` is a union of a byte view and a longword view in C, so that the
    # flood can clear it with move.l; the byte view is the one the field means
    # and the only one a test has any business reading.
    _fields_ = [("steps", ctypes.c_uint8 * MAP_MAX_CELLS),
                ("queue", ctypes.c_uint16 * NAV_QUEUE_MAX),
                ("origin_cell", ctypes.c_uint16),
                ("visited", ctypes.c_uint16),
                ("next_rebuild_tick", ctypes.c_uint32)]


class EventQueue(ctypes.Structure):
    _fields_ = [("ids", ctypes.c_uint8 * EVENT_QUEUE_SIZE),
                ("head", ctypes.c_uint8), ("tail", ctypes.c_uint8),
                ("dropped", ctypes.c_uint8), ("pad", ctypes.c_uint8)]


class RunProgress(ctypes.Structure):
    _fields_ = [("sectors_over_par", ctypes.c_uint8),
                ("deaths_this_sector", ctypes.c_uint8),
                ("integrity", ctypes.c_int16), ("cycles", ctypes.c_int16)]


# The game layer's own fields, in game.h's order.  They are spliced onto the
# engine half below rather than declared as a struct of their own: C aligns a
# member against the START of the whole struct, and a separately-declared tail
# placed at an odd offset pads differently from the real thing.  One mirror,
# one layout, no drift.
_GAME_LAYER_FIELDS = [
    ("entities", EntityRuntime * LEVEL_MAX_ENTITIES),
    ("occupancy", EntityOccupancy),
    ("nav", NavField),
    ("neighbour_offset", ctypes.c_int16 * CONST["NEIGHBOUR_COUNT"]),
    ("events", EventQueue),
    ("integrity", ctypes.c_int16),
    ("cycles", ctypes.c_int16),
    ("trace_remainder", ctypes.c_int16),
    ("route_ticks", ctypes.c_uint16),
    ("music_tempo_bpm", ctypes.c_uint16),
    ("tokens", ctypes.c_uint8),
    ("phase", ctypes.c_uint8),
    ("next_sector_index", ctypes.c_uint8),
    ("trace_band", ctypes.c_uint8),
    ("palette_variant", ctypes.c_uint8),
    ("enemy_tier", ctypes.c_uint8),
    ("weapon_cooldown", ctypes.c_uint8),
    ("muzzle_flash", ctypes.c_uint8),
    ("deaths_this_sector", ctypes.c_uint8),
    ("data_caches", ctypes.c_uint8),
    ("kills", ctypes.c_uint8),
    ("enemy_has_los", ctypes.c_uint8),
    ("bumped_cell", ctypes.c_int16),
    ("prev_bumped_cell", ctypes.c_int16),
]

# blackice.py mirrors the engine half and closes it with one opaque padding
# member, which the game-layer fields replace here.
_ENGINE_FIELDS = [f for f in blackice.GameState._fields_ if f[0] != "game_layer_tail"]


class FullGameState(ctypes.Structure):
    """The whole C GameState: the engine half plus the game layer."""

    _fields_ = _ENGINE_FIELDS + _GAME_LAYER_FIELDS


class State:
    """One GameState, addressed under two names.

    `state.engine` and `state.game` are the SAME object: the split is
    documentary, so a test reads `state.game.integrity` and `state.engine.tick`
    and it is obvious at the call site which half of the struct a field belongs
    to.  There is one allocation and one layout, which is what keeps the mirror
    honest.
    """

    def __init__(self, lib, level, seed):
        self.engine = FullGameState()
        self.game = self.engine
        self.level = level
        lib.game_init(ref(self), ctypes.byref(level), seed)


def ref(state):
    """A pointer to the state, typed as the engine's own mirror.

    blackice.py binds the engine entry points against ITS GameState, and this
    module's mirror is a different ctypes type describing the same bytes, so the
    pointer is cast rather than the argtypes loosened - a loose argtype would
    accept anything at all.
    """
    struct = state.engine if isinstance(state, State) else state
    return ctypes.cast(ctypes.byref(struct), ctypes.POINTER(blackice.GameState))


# ---------------------------------------------------------------------------
# binding the game layer's own entry points
# ---------------------------------------------------------------------------

_GAME_LAYER_BOUND = False
#: The library the game-layer helpers below drive.  Set by bind(), which every
#: entry point into this module calls first.
_LIB = None


def bind(lib):
    """argtypes for everything the game-layer tests call directly.

    Without these, ctypes passes every argument as a plain int and the callee
    reads the low half of a register the ABI never required the caller to
    sign-extend - which is a wrong answer, not a crash.
    """
    global _GAME_LAYER_BOUND, _LIB
    _LIB = lib
    if _GAME_LAYER_BOUND:
        return lib
    state_p = ctypes.POINTER(blackice.GameState)

    lib.ai_line_of_sight.argtypes = [state_p, ctypes.c_int16, ctypes.c_int16,
                                     ctypes.c_int16, ctypes.c_int16]
    lib.ai_line_of_sight.restype = ctypes.c_int
    lib.ai_within_cone.argtypes = [ctypes.c_uint16, ctypes.c_int16, ctypes.c_int16,
                                   ctypes.c_int16]
    lib.ai_within_cone.restype = ctypes.c_int
    lib.ai_can_see_player.argtypes = [state_p, ctypes.c_uint16]
    lib.ai_can_see_player.restype = ctypes.c_int
    lib.ai_distance_squared.argtypes = [ctypes.c_int16] * 4
    lib.ai_distance_squared.restype = ctypes.c_int32

    lib.entity_damage.argtypes = [state_p, ctypes.c_uint16, ctypes.c_uint8]
    lib.entity_damage.restype = ctypes.c_int
    lib.entity_at_cell.argtypes = [state_p, ctypes.c_uint16]
    lib.entity_at_cell.restype = ctypes.c_int32
    lib.entity_hittable_in_cell.argtypes = [state_p, ctypes.c_uint16]
    lib.entity_hittable_in_cell.restype = ctypes.c_int32
    lib.entity_alert.argtypes = [state_p, ctypes.c_uint16]
    lib.entity_alert.restype = ctypes.c_int

    queue_p = ctypes.POINTER(EventQueue)
    lib.event_reset.argtypes = [queue_p]
    lib.event_push.argtypes = [queue_p, ctypes.c_uint8]
    lib.event_pop.argtypes = [queue_p, ctypes.POINTER(ctypes.c_uint8)]
    lib.event_pop.restype = ctypes.c_int
    lib.event_sfx.argtypes = [ctypes.c_uint8]
    lib.event_sfx.restype = ctypes.c_uint8

    lib.weapon_hitscan_target.argtypes = [state_p, ctypes.POINTER(ctypes.c_int32)]
    lib.weapon_hitscan_target.restype = ctypes.c_int32

    lib.trace_apply.argtypes = [state_p, ctypes.c_int32]
    lib.trace_step.argtypes = [state_p, ctypes.c_uint16]
    lib.trace_init.argtypes = [state_p, ctypes.POINTER(RunProgress)]
    lib.game_start_level.argtypes = [state_p, ctypes.POINTER(blackice.Level),
                                     ctypes.c_uint32, ctypes.POINTER(RunProgress)]
    lib.run_progress_reset.argtypes = [ctypes.POINTER(RunProgress)]
    lib.door_required_token.argtypes = [ctypes.c_uint8]
    lib.door_required_token.restype = ctypes.c_uint8
    lib.sim_damage_player.argtypes = [state_p, ctypes.c_uint8]
    lib.nav_rebuild.argtypes = [ctypes.POINTER(NavField), ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint16]

    for name in ("bi_offset_state_nav", "bi_offset_state_events",
                 "bi_offset_state_integrity"):
        getattr(lib, name).restype = ctypes.c_size_t
        getattr(lib, name).argtypes = []

    _GAME_LAYER_BOUND = True
    return lib


@pytest.fixture(scope="session")
def glib(lib):
    """The engine library with the game layer's entry points bound."""
    return bind(lib)


def new_state(lib, level, seed=None):
    """A State, initialised.  The seed defaults to the level's own."""
    bind(lib)
    return State(lib, level, level.rng_seed if seed is None else seed)


def step(lib, state, input_word=0):
    lib.game_step(ref(state), input_word)


# ---------------------------------------------------------------------------
# hand-built levels
# ---------------------------------------------------------------------------

def level_from_rows(lib, rows, header=""):
    """Compile an ASCII map with a minimal header through the real loader."""
    text = header + "\n".join(rows) + "\n"
    return blackice.parse_level(lib, text)


def cell(level, x, y):
    return y * level.width + x


def put_player(state, x, y, angle=0):
    state.engine.player.x = x * CELL + CENTRE
    state.engine.player.y = y * CELL + CENTRE
    state.engine.player.angle = angle


def entity_index_at(level, x, y):
    for i in range(level.entity_count):
        e = level.entities[i]
        if (e.cell_x, e.cell_y) == (x, y):
            return i
    raise AssertionError("no authored entity at (%d, %d)" % (x, y))


def drain_events(state):
    """Every event id in the ring, oldest first, POPPED through the engine's own
    event_pop.

    Reading the ring's bytes in Python instead would leave the read side of the
    queue - the half the platform layer actually runs - untested: a mutation
    that stops event_pop advancing the tail passed the whole suite, because the
    suite never called it.
    """
    lib = _LIB
    out = []
    slot = ctypes.c_uint8()
    # Bounded: a pop that returns an id without advancing the tail would other-
    # wise hang the suite instead of failing it.
    while lib.event_pop(ctypes.byref(state.game.events), ctypes.byref(slot)):
        out.append(slot.value)
        assert len(out) <= EVENT_QUEUE_SIZE, "event_pop is not draining the ring"
    return out


def clear_events(state):
    state.game.events.tail = state.game.events.head
    state.game.events.dropped = 0


# ---------------------------------------------------------------------------
# a planner that walks the player along a route
# ---------------------------------------------------------------------------

def passable_cells(level):
    """Cells a route may cross: empty, or any door (the planner assumes it can
    be opened, and the playthrough proves it by opening it)."""
    out = set()
    for y in range(level.height):
        for x in range(level.width):
            value = level.cells[cell(level, x, y)]
            if value == 0 or value >= CONST["CELL_DOOR_BASE"]:
                out.add((x, y))
    return out


def bfs_route(level, start, goal, blocked=()):
    """Shortest 4-neighbour cell route from start to goal, inclusive."""
    passable = passable_cells(level) - set(blocked)
    previous = {start: None}
    frontier = [start]
    while frontier:
        nxt = []
        for node in frontier:
            if node == goal:
                return _unwind(previous, goal)
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                step_to = (node[0] + dx, node[1] + dy)
                if step_to in previous or step_to not in passable:
                    continue
                previous[step_to] = node
                nxt.append(step_to)
        frontier = nxt
    if goal in previous:
        return _unwind(previous, goal)
    raise AssertionError("no route from %s to %s" % (start, goal))


def _unwind(previous, goal):
    route = []
    node = goal
    while node is not None:
        route.append(node)
        node = previous[node]
    route.reverse()
    return route


# The player turns PLAYER_TURN_SPEED per tick, so anything inside half of that
# is "aimed" and the autopilot walks instead of turning.
_TURN_SPEED = CONST["PLAYER_TURN_SPEED"]
_AIMED_ANGLE = _TURN_SPEED
_ARRIVAL_UNITS = 40         # map units: closer than a fifth of a cell


def _angle_to(state, target_x, target_y):
    dx = target_x - state.engine.player.x
    dy = target_y - state.engine.player.y
    return int(math.atan2(dy, dx) / (2 * math.pi) * 65536) & 0xFFFF


def autopilot_input(state, target_cell):
    """One tick of input that walks the player toward a cell centre.

    Returns (input_word, arrived).  It is a test-side driver, not part of the
    sim: the sim only ever sees an input word, exactly as the joystick gives it.
    """
    target_x = target_cell[0] * CELL + CENTRE
    target_y = target_cell[1] * CELL + CENTRE
    dx = target_x - state.engine.player.x
    dy = target_y - state.engine.player.y
    if abs(dx) <= _ARRIVAL_UNITS and abs(dy) <= _ARRIVAL_UNITS:
        return 0, True

    delta = (_angle_to(state, target_x, target_y) - state.engine.player.angle) & 0xFFFF
    if delta > 32768:
        delta -= 65536
    if abs(delta) > _AIMED_ANGLE:
        return (CONST["INPUT_TURN_LEFT"] if delta < 0 else CONST["INPUT_TURN_RIGHT"]), False
    return CONST["INPUT_FORWARD"], False
