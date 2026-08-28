"""The navigation field, line of sight, the sight cones and the three state
machines of DESIGN 8.

The soak at the bottom is the one that matters: DESIGN 8.1 exists because v1's
straight-line chase jammed on the first outer corner of every block in both
shipped maps, and a BFS field is only worth its 4 KB if it provably cannot.
"""
import ctypes

import pytest

import aihelp
import blackice
from aihelp import CELL, CENTRE, ENT_SENTRY, ENT_TRACER, ENT_WATCHDOG, NAV_UNREACHABLE
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

HEADER = "# name: TEST\n# start_facing: 0\n\n"


def make_level(glib, rows):
    return aihelp.level_from_rows(glib, rows, HEADER)


# ---------------------------------------------------------------------------
# the ctypes mirror of the game layer
# ---------------------------------------------------------------------------

def test_the_game_layer_mirror_sits_where_the_compiler_puts_it(glib):
    """aihelp models the tail of GameState by hand.  If the C struct grows a
    field in the middle, every game-layer test would read the wrong bytes and
    still pass - so the start of the tail and three fields inside it are pinned
    against the compiler's own offsets, and the whole mirror against its size."""
    assert ctypes.sizeof(aihelp.FullGameState) == glib.bi_sizeof_gamestate()
    for name, probe in (("player", glib.bi_offset_state_player),
                        ("doors", glib.bi_offset_state_doors),
                        ("trace_milli", glib.bi_offset_state_trace),
                        ("entities", glib.bi_offset_state_gamelayer),
                        ("nav", glib.bi_offset_state_nav),
                        ("events", glib.bi_offset_state_events),
                        ("integrity", glib.bi_offset_state_integrity)):
        assert getattr(aihelp.FullGameState, name).offset == probe(), name


# ---------------------------------------------------------------------------
# the BFS distance field
# ---------------------------------------------------------------------------

CORRIDOR = [
    "#######",
    "#.....#",
    "#.###.#",
    "#.###.#",
    "#..@..#",
    "#######",
]


def test_the_field_is_the_true_step_distance_around_an_obstacle(glib):
    """A straight-line chase would walk into the block in the middle.  The BFS
    values must go the long way round it, and agree on both flanks."""
    level = make_level(glib, CORRIDOR)
    state = aihelp.new_state(glib, level)
    aihelp.step(glib, state)                 # tick 0 floods from the player cell

    nav = state.game.nav
    assert nav.origin_cell == aihelp.cell(level, 3, 4)
    assert nav.steps[aihelp.cell(level, 3, 4)] == 0
    # Round the left flank: (3,4) -> (1,4) is 2, then up the west column.
    assert nav.steps[aihelp.cell(level, 1, 4)] == 2
    assert nav.steps[aihelp.cell(level, 1, 1)] == 5
    # And the right flank is the mirror image.
    assert nav.steps[aihelp.cell(level, 5, 4)] == 2
    assert nav.steps[aihelp.cell(level, 5, 1)] == 5
    # The top of the ring is equidistant either way.
    assert nav.steps[aihelp.cell(level, 3, 1)] == 7


def test_walls_never_get_a_value(glib):
    level = make_level(glib, CORRIDOR)
    state = aihelp.new_state(glib, level)
    aihelp.step(glib, state)

    for y in range(level.height):
        for x in range(level.width):
            if level.cells[aihelp.cell(level, x, y)] != 0:
                assert state.game.nav.steps[aihelp.cell(level, x, y)] == NAV_UNREACHABLE


def test_the_flood_stops_at_the_radius(glib):
    """DESIGN 8.1 limits the flood to 20 cells.  A corridor longer than that
    must be reachable up to the limit and unreachable past it."""
    width = 30
    rows = ["#" * width]
    rows.append("#" + "." * (width - 2) + "#")
    rows.append("#" * width)
    rows[1] = "#@" + "." * (width - 3) + "#"
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    aihelp.step(glib, state)

    radius = CONST["NAV_RADIUS_STEPS"]
    assert state.game.nav.steps[aihelp.cell(level, 1 + radius, 1)] == radius
    assert state.game.nav.steps[aihelp.cell(level, 2 + radius, 1)] == NAV_UNREACHABLE


# Two parallel corridors joined only by the door at (3,2), so the field and the
# line of sight both have exactly one thing to say about it.
DOOR_ROOM = [
    "#######",
    "#..#..#",
    "#..+..#",
    "#..#..#",
    "#..#..#",
    "#@.#..#",
    "#######",
]


def test_a_closed_door_is_a_wall_to_the_field_and_an_open_one_is_not(glib):
    """DESIGN 8.1: a non-OPEN door is a wall.  The field must route around a
    closed leaf and straight through an open one."""
    level = make_level(glib, DOOR_ROOM)
    state = aihelp.new_state(glib, level)
    aihelp.step(glib, state)

    door_cell = aihelp.cell(level, 3, 2)
    assert state.game.nav.steps[door_cell] == NAV_UNREACHABLE
    # The east corridor is behind the leaf, so it has no route at all.
    assert state.game.nav.steps[aihelp.cell(level, 4, 2)] == NAV_UNREACHABLE
    assert state.game.nav.steps[aihelp.cell(level, 2, 2)] == 4

    glib.game_touch_door(aihelp.ref(state), door_cell)
    for _ in range(CONST["DOOR_OPENING_TICKS"] + CONST["NAV_REBUILD_TICKS"] + 1):
        aihelp.step(glib, state)
    assert state.game.nav.steps[door_cell] == 5
    assert state.game.nav.steps[aihelp.cell(level, 4, 2)] == 6


def test_the_field_is_rebuilt_on_the_design_cadence(glib):
    """Every 8 ticks, not every tick: DESIGN 8.1 buys the whole AI's
    affordability with that number, so it is pinned."""
    level = make_level(glib, CORRIDOR)
    state = aihelp.new_state(glib, level)
    cadence = CONST["NAV_REBUILD_TICKS"]

    aihelp.step(glib, state)
    origins = []
    # A 3-cell cycle against an 8-tick cadence, so consecutive rebuilds never
    # land on the same cell and a missed rebuild cannot hide as a repeat.
    for tick in range(cadence * 3):
        state.engine.player.x = (1 + tick % 3) * CELL + CENTRE
        state.engine.player.y = 4 * CELL + CENTRE
        aihelp.step(glib, state)
        origins.append(state.game.nav.origin_cell)

    changes = sum(1 for a, b in zip(origins, origins[1:]) if a != b)
    assert changes == 3, "3 rebuilds in 24 ticks at a cadence of %d" % cadence


# ---------------------------------------------------------------------------
# line of sight
# ---------------------------------------------------------------------------

LOS_ROOM = [
    "#######",
    "#.....#",
    "#..#..#",
    "#.....#",
    "#..@..#",
    "#######",
]


def point(x, y):
    return x * CELL + CENTRE, y * CELL + CENTRE


def los(glib, state, a, b):
    ax, ay = point(*a)
    bx, by = point(*b)
    return glib.ai_line_of_sight(aihelp.ref(state), ax, ay, bx, by)


def test_line_of_sight_is_symmetric_and_blocked_by_the_pillar(glib):
    level = make_level(glib, LOS_ROOM)
    state = aihelp.new_state(glib, level)

    clear = ((1, 1), (5, 1))
    through_pillar = ((3, 1), (3, 3))
    for a, b in (clear, through_pillar):
        assert los(glib, state, a, b) == los(glib, state, b, a), \
            "line of sight %s <-> %s is not symmetric" % (a, b)
    assert los(glib, state, *clear)
    assert not los(glib, state, *through_pillar)


def test_a_body_sees_its_own_cell(glib):
    level = make_level(glib, LOS_ROOM)
    state = aihelp.new_state(glib, level)
    assert los(glib, state, (1, 1), (1, 1))


def test_a_closed_door_blocks_sight_and_an_open_one_does_not(glib):
    level = make_level(glib, DOOR_ROOM)
    state = aihelp.new_state(glib, level)

    assert not los(glib, state, (2, 2), (4, 2))
    glib.game_touch_door(aihelp.ref(state), aihelp.cell(level, 3, 2))
    for _ in range(CONST["DOOR_OPENING_TICKS"] + 1):
        aihelp.step(glib, state)
    assert los(glib, state, (2, 2), (4, 2))


# ---------------------------------------------------------------------------
# the sight cone
# ---------------------------------------------------------------------------

QUARTER = CONST["ANGLE_QUARTER_TURN"]
EAST, SOUTH, WEST, NORTH = 0, QUARTER, 2 * QUARTER, 3 * QUARTER


@pytest.mark.parametrize("facing,dx,dy,inside", [
    (EAST, 100, 0, True),           # dead ahead
    (EAST, -100, 0, False),         # dead behind
    (EAST, 100, 99, True),          # 44.7 degrees off: inside a 90 degree cone
    (EAST, 100, 101, False),        # 45.3 degrees off: outside it
    (NORTH, 0, -100, True),
    (SOUTH, 0, 100, True),
    (WEST, -100, 0, True),
])
def test_the_sentry_cone_is_ninety_degrees(glib, facing, dx, dy, inside):
    """DESIGN 8 gives the Sentry a 90 degree cone, so its half-angle tangent is
    exactly 1 and the boundary is the diagonal."""
    tan = CONST["SENTRY_CONE_TAN_Q8"]
    assert bool(glib.ai_within_cone(facing, dx, dy, tan)) == inside


def test_a_wider_cone_admits_what_a_narrower_one_refuses(glib):
    """The three cones are 120 / 90 / 150 degrees, so a bearing must be admitted
    by strictly more of them as the cone widens."""
    dx, dy = 100, 150               # 56 degrees off the facing
    assert not glib.ai_within_cone(EAST, dx, dy, CONST["SENTRY_CONE_TAN_Q8"])
    assert glib.ai_within_cone(EAST, dx, dy, CONST["WATCHDOG_CONE_TAN_Q8"])
    assert glib.ai_within_cone(EAST, dx, dy, CONST["TRACER_CONE_TAN_Q8"])


# ---------------------------------------------------------------------------
# the Sentry
# ---------------------------------------------------------------------------

SENTRY_HALL = [
    "#########",
    "#.......#",
    "#.......#",
    "#.......#",
    "#...@...#",
    "####s####",       # the alcove: three wall neighbours, one open side
    "#########",
]


def test_a_sentry_faces_out_of_its_alcove(glib):
    """DESIGN 11 rule 5 makes the alcove's shape the authority on which way the
    turret looks, so no level file has to author a facing that could disagree
    with the geometry around it."""
    level = make_level(glib, SENTRY_HALL)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 5)

    assert state.game.entities[sentry].type == ENT_SENTRY
    assert state.game.entities[sentry].facing == NORTH


def test_the_sentry_runs_its_charge_iris_cooldown_cycle(glib):
    level = make_level(glib, SENTRY_HALL)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 5)
    body = state.game.entities

    aihelp.step(glib, state)
    assert body[sentry].state == CONST["ENT_STATE_ALERT"], "it should see the player"

    # +1: the tick the charge expires opens the iris, and the shot is the next.
    for _ in range(CONST["SENTRY_CHARGE_TICKS"] + 1):
        aihelp.step(glib, state)
    assert body[sentry].state == CONST["ENT_STATE_ATTACK"], "the iris should be open"
    assert state.game.integrity < CONST["PLAYER_INTEGRITY_MAX"], "it should have fired"

    for _ in range(CONST["SENTRY_IRIS_OPEN_TICKS"]):
        aihelp.step(glib, state)
    assert body[sentry].state == CONST["ENT_STATE_IDLE"], "the iris should have shut"


def test_a_sentry_is_invulnerable_until_its_iris_opens(glib):
    """DESIGN 8's whole Sentry fight is the vulnerability window, so a shot
    landing outside it must do nothing at all."""
    level = make_level(glib, SENTRY_HALL)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 5)
    full = CONST["SENTRY_HP"]

    assert glib.entity_damage(aihelp.ref(state), sentry, 30) == 0
    assert state.game.entities[sentry].hp == full

    for _ in range(CONST["SENTRY_CHARGE_TICKS"] + 2):
        aihelp.step(glib, state)
    assert state.game.entities[sentry].state == CONST["ENT_STATE_ATTACK"]
    assert glib.entity_damage(aihelp.ref(state), sentry, 30) == 1
    assert state.game.entities[sentry].hp == full - 30


def test_a_sentry_outside_its_cone_never_wakes(glib):
    """The alcove looks north; a player standing due east of it, behind the
    wall, is outside both the cone and the line of sight."""
    rows = [
        "#########",
        "#.......#",
        "####s####",
        "#####.@.#",
        "#########",
    ]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 2)

    for _ in range(CONST["SENTRY_CHARGE_TICKS"] * 2):
        aihelp.step(glib, state)
    assert state.game.entities[sentry].state == CONST["ENT_STATE_IDLE"]
    assert state.game.integrity == CONST["PLAYER_INTEGRITY_MAX"]


# ---------------------------------------------------------------------------
# the Watchdog
# ---------------------------------------------------------------------------

def test_a_watchdog_wakes_on_sight_tells_then_chases(glib):
    # 7 cells apart: inside the Watchdog's 8-cell base sight.
    rows = ["##########",
            "#w......@#",
            "##########"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 1, 1)
    # The dog is authored facing north; turn it to look down the corridor.
    state.game.entities[dog].facing = EAST

    aihelp.step(glib, state)
    assert state.game.entities[dog].state == CONST["ENT_STATE_ALERT"]

    for _ in range(CONST["WATCHDOG_ALERT_TICKS"]):
        aihelp.step(glib, state)
    assert state.game.entities[dog].state == CONST["ENT_STATE_CHASE"]

    start_x = state.game.entities[dog].x
    for _ in range(20):
        aihelp.step(glib, state)
    assert state.game.entities[dog].x > start_x, "a chasing dog must close"


def test_a_watchdog_bites_after_its_wind_up_and_then_cools_down(glib):
    rows = ["#####",
            "#w@.#",
            "#####"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 1, 1)
    state.game.entities[dog].facing = EAST
    # Stand the player inside the melee reach so the bite is the only variable.
    state.engine.player.x = state.game.entities[dog].x + CONST["WATCHDOG_MELEE_REACH"] - 1

    full = CONST["PLAYER_INTEGRITY_MAX"]
    for _ in range(CONST["WATCHDOG_ALERT_TICKS"] + 2):
        aihelp.step(glib, state)
    assert state.game.entities[dog].state == CONST["ENT_STATE_ATTACK"]
    assert state.game.integrity == full, "the bite must wait out its wind-up"

    for _ in range(CONST["WATCHDOG_BITE_WINDUP_TICKS"] - 1):
        aihelp.step(glib, state)
    assert state.game.integrity == full, "still winding up"

    aihelp.step(glib, state)
    assert state.game.integrity == full - CONST["WATCHDOG_MELEE_DAMAGE"]

    # The cooldown holds the second bite off for WATCHDOG_ATTACK_TICKS.
    after_first = state.game.integrity
    for _ in range(CONST["WATCHDOG_ATTACK_TICKS"] - 2):
        aihelp.step(glib, state)
    assert state.game.integrity == after_first


def test_an_alerted_watchdog_wakes_its_pack(glib):
    """DESIGN 12 puts all four of level 1's dogs inside one 6-cell wake cluster
    precisely so they come out as one, so the radius is pinned here."""
    # The wall keeps the two western dogs from seeing the player themselves, so
    # the only thing that can wake them is the eastern dog's alert.
    rows = ["############",
            "#w.w####.w@#",
            "############"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    near = aihelp.entity_index_at(level, 1, 1)
    middle = aihelp.entity_index_at(level, 3, 1)
    far = aihelp.entity_index_at(level, 9, 1)

    # Only the far dog can see the player; it must wake the others in radius.
    for index in (near, middle, far):
        state.game.entities[index].facing = EAST
    aihelp.step(glib, state)

    assert state.game.entities[far].state == CONST["ENT_STATE_ALERT"]
    assert state.game.entities[middle].state != CONST["ENT_STATE_IDLE"], \
        "6 cells from the waker: inside the pack radius"
    assert state.game.entities[near].state == CONST["ENT_STATE_IDLE"], \
        "8 cells from the waker: outside it"


# ---------------------------------------------------------------------------
# the Tracer
# ---------------------------------------------------------------------------

TRACER_HALL = [
    "##############",
    "#............#",
    "#............#",
    "#.t........@.#",
    "#............#",
    "#............#",
    "##############",
]


def test_a_tracer_closes_to_its_ring_and_holds_it(glib):
    """DESIGN 8.1: a Tracer prefers cells whose field value is 3 to 5 and holds
    that ring, rather than closing like a Watchdog."""
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    state.game.entities[tracer].facing = EAST

    for _ in range(200):
        aihelp.step(glib, state)

    body = state.game.entities[tracer]
    steps = state.game.nav.steps[body.claim_cell]
    assert CONST["TRACER_RING_MIN_STEPS"] <= steps <= CONST["TRACER_RING_MAX_STEPS"], \
        "the Tracer settled at %d steps, outside its 3..5 ring" % steps


def test_a_hurt_tracer_flees_up_the_gradient_and_raises_the_trace(glib):
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    state.game.entities[tracer].facing = EAST

    for _ in range(CONST["TRACER_ALERT_TICKS"] + 2):
        aihelp.step(glib, state)
    assert state.game.entities[tracer].state == CONST["ENT_STATE_CHASE"]

    state.game.entities[tracer].hp = CONST["TRACER_FLEE_HP"] - 1
    before = state.engine.trace_milli
    for _ in range(200):
        aihelp.step(glib, state)
        if state.engine.entity_alive[tracer] == 0:
            break

    assert state.engine.entity_alive[tracer] == 0, "the Tracer never reached an edge"
    assert state.engine.trace_milli - before >= CONST["TRACE_BUMP_TRACER_ESCAPE"], \
        "an escaping Tracer must cost the player 15%"


# ---------------------------------------------------------------------------
# cell claims
# ---------------------------------------------------------------------------

def rebuild_occupancy(state, level):
    """The occupancy map, recomputed from the entity table alone.

    entities.c maintains it incrementally through claim_take and claim_release,
    which is fast but can only stay correct if nothing else writes it - so the
    test rebuilds it independently and compares.
    """
    owner = [0] * aihelp.MAP_MAX_CELLS
    gone = (CONST["ENT_STATE_DEAD"], CONST["ENT_STATE_DESTROYED"])
    for i in range(level.entity_count):
        body = state.game.entities[i]
        if not state.engine.entity_alive[i]:
            continue
        # A body that has died has released its cell: it is still drawn while it
        # dissolves, and a destroyed Sentry is drawn for good, but neither owns
        # floor any more.
        if body.state in gone:
            continue
        if body.type in (ENT_WATCHDOG, ENT_SENTRY, ENT_TRACER, CONST["ENT_ANCHOR"]):
            owner[body.claim_cell] = i + 1
    return owner


def test_the_occupancy_map_always_matches_the_entity_table(glib):
    """Including across a death: releasing the claim is the step that a body
    dissolving in a doorway depends on, and it is invisible to a rebuild that
    only ever sees living bodies."""
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    state.game.entities[tracer].facing = EAST
    killed = False

    for tick in range(120):
        aihelp.step(glib, state)
        if tick == 60:
            glib.entity_damage(aihelp.ref(state), tracer, CONST["TRACER_HP"])
            assert state.game.entities[tracer].state == CONST["ENT_STATE_DEAD"]
            killed = True
        expected = rebuild_occupancy(state, level)
        got = list(state.game.occupancy.owner)
        assert got == expected, "occupancy drifted from the entity table at tick %d" % tick
    assert killed


def test_two_watchdogs_never_claim_the_same_cell(glib):
    rows = ["##########",
            "#ww.....@#",
            "##########"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    for i in range(level.entity_count):
        state.game.entities[i].state = CONST["ENT_STATE_CHASE"]
    for tick in range(300):
        aihelp.step(glib, state)
        claims = [state.game.entities[i].claim_cell
                  for i in range(level.entity_count)
                  if state.engine.entity_alive[i]]
        assert len(claims) == len(set(claims)), "two bodies shared a cell at tick %d" % tick


# ---------------------------------------------------------------------------
# the DESIGN 8.1 soak: navigation must never jam
# ---------------------------------------------------------------------------

def _walkable_cells(level):
    return [(x, y)
            for y in range(level.height)
            for x in range(level.width)
            if level.cells[aihelp.cell(level, x, y)] == 0]


def _cell_distances(level, origin):
    """Step distance from `origin` over the grid, doors counted as passable.

    Used to CHOOSE the soak's spawn cells, never to check its answers.  Doors
    count because the player opens them on the way through and a chasing dog
    opens a plain gate by contact (DESIGN 8), so a cell behind one is somewhere
    the swarm really can be asked to walk from.
    """
    walkable = aihelp.passable_cells(level)
    distance = {origin: 0}
    frontier = [origin]
    while frontier:
        nxt = []
        for x, y in frontier:
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                step_to = (x + dx, y + dy)
                if step_to in distance or step_to not in walkable:
                    continue
                distance[step_to] = distance[(x, y)] + 1
                nxt.append(step_to)
        frontier = nxt
    return distance


# Far enough that they have to walk, near enough that the radius-limited field
# actually reaches them - a dog seeded outside NAV_RADIUS_STEPS has no gradient
# to descend and would make this soak pass by standing still.
SOAK_MIN_STEPS = 4
SOAK_TICKS_WALKING = 1500
SOAK_TICKS_CONVERGING = 500
SOAK_DOGS = 50
# With 50 bodies queueing into one cell's neighbourhood, this many being within
# three cells of the player is convergence; the exact figure is a floor chosen
# well under what both maps actually manage.
SOAK_MIN_ARRIVALS = 8
# Ticks a dog must have spent inside the field before "it never moved" is a
# defect rather than a body that only just came into range.
ENGAGED_SAMPLES = 2 * CONST["NAV_REBUILD_TICKS"]


def _seed_watchdogs(level, count):
    """Replace the level's authored roster with `count` Watchdogs spread over
    the walkable cells the navigation field can actually reach."""
    start = (level.start_cell_x, level.start_cell_y)
    distance = _cell_distances(level, start)
    reachable = sorted(c for c, d in distance.items()
                       if SOAK_MIN_STEPS <= d <= CONST["NAV_RADIUS_STEPS"])
    assert len(reachable) >= count, \
        "%s has only %d cells inside the field to seed into" % (level.name, len(reachable))

    # Spread them evenly rather than clumping at one end, so the soak exercises
    # bodies approaching from every direction and queueing into each other.
    stride = len(reachable) // count
    chosen = reachable[::stride][:count]

    level.entity_count = count
    for i, (x, y) in enumerate(chosen):
        level.entities[i].type = ENT_WATCHDOG
        level.entities[i].cell_x = x
        level.entities[i].cell_y = y
        level.entities[i].facing = 0
        level.entities[i].extra = 0
    return level


def _classify(state, level, player_cell):
    """Split the roster into arrived / queued / out-of-field / JAMMED.

    A jam is the one thing DESIGN 8.1 says cannot happen: a body standing in
    open floor, inside the field, with a strictly better neighbour it did not
    take and nothing in its way.
    """
    arrived, queued, out_of_field, jammed = [], [], [], []
    for i in range(level.entity_count):
        if not state.engine.entity_alive[i]:
            continue
        body = state.game.entities[i]
        cell_x = body.claim_cell % level.width
        cell_y = body.claim_cell // level.width
        steps = state.game.nav.steps[body.claim_cell]
        gap = max(abs(cell_x - player_cell[0]), abs(cell_y - player_cell[1]))
        if gap <= 1:
            arrived.append(i)
        elif body.flags & CONST["ENTITY_FLAG_BLOCKED"]:
            queued.append(i)
        elif steps == NAV_UNREACHABLE:
            out_of_field.append(i)
        else:
            jammed.append((i, (cell_x, cell_y), steps))
    return arrived, queued, out_of_field, jammed


@pytest.mark.parametrize("name", ["level1", "level2"])
def test_fifty_watchdogs_never_jam(glib, name):
    """DESIGN 8.1's whole claim: the field is a true BFS, so a chosen neighbour
    always exists and always reduces the distance, and the movement CANNOT jam.

    Fifty dogs chase a moving player on both shipped maps for 1500 ticks, then
    close on a stationary one for 500 more.  Two things are asserted, and the
    second is what stops the first from passing vacuously: no dog is left
    standing in open floor with a better cell free beside it, AND the swarm
    actually converged rather than never having moved at all.
    """
    path = blackice.ROOT / "levels" / ("%s.txt" % name)
    level = blackice.parse_level(glib, path.read_text())
    _seed_watchdogs(level, SOAK_DOGS)

    state = aihelp.new_state(glib, level)
    for i in range(level.entity_count):
        state.game.entities[i].state = CONST["ENT_STATE_CHASE"]
    started_at = [state.game.entities[i].claim_cell for i in range(level.entity_count)]

    route = aihelp.bfs_route(level,
                             (level.start_cell_x, level.start_cell_y),
                             _walkable_cells(level)[0])
    waypoint = 0
    engaged = {}            # dog -> how many samples it spent inside the field
    moved = set()
    for tick in range(SOAK_TICKS_WALKING + SOAK_TICKS_CONVERGING):
        # Keep the player alive: this soak is about navigation, and combat has
        # its own tests.
        state.game.integrity = CONST["PLAYER_INTEGRITY_MAX"]
        state.game.phase = CONST["PHASE_PLAYING"]
        word = 0
        if tick < SOAK_TICKS_WALKING and waypoint < len(route):
            word, arrived = aihelp.autopilot_input(state, route[waypoint])
            if arrived:
                waypoint += 1
        aihelp.step(glib, state, word)

        for i in range(level.entity_count):
            body = state.game.entities[i]
            if body.claim_cell != started_at[i]:
                moved.add(i)
            if state.game.nav.steps[body.claim_cell] != NAV_UNREACHABLE:
                engaged[i] = engaged.get(i, 0) + 1

    player_cell = (state.engine.player.x // CELL, state.engine.player.y // CELL)
    arrived, queued, out_of_field, jammed = _classify(state, level, player_cell)

    assert not jammed, ("%d of %d watchdogs jammed on %s: %s"
                        % (len(jammed), SOAK_DOGS, name, jammed[:8]))
    assert len(arrived) + len(queued) >= SOAK_MIN_ARRIVALS, (
        "%s: only %d of %d reached or queued (out of field %d) - the swarm did "
        "not converge, so 'nothing jammed' proves nothing"
        % (name, len(arrived) + len(queued), SOAK_DOGS, len(out_of_field)))

    # Two kinds of stillness are legitimate and one is not.  A dog behind a door
    # the route never opened has no gradient at all - DESIGN 8.1 makes a
    # non-OPEN door a wall - and a dog at the back of a queue has a gradient it
    # is not allowed to use, which is the one-per-cell claim working.  What
    # cannot happen is a dog with a gradient, nothing in its way, and no move.
    blocked = {i for i in range(level.entity_count)
               if state.game.entities[i].flags & CONST["ENTITY_FLAG_BLOCKED"]}
    idle_with_a_route = sorted(i for i, samples in engaged.items()
                               if samples >= ENGAGED_SAMPLES
                               and i not in moved and i not in blocked)
    assert not idle_with_a_route, (
        "%s: %d watchdogs sat inside the field, unobstructed, without moving: %s"
        % (name, len(idle_with_a_route), idle_with_a_route[:8]))
    assert len(engaged) >= SOAK_MIN_ARRIVALS, \
        "%s: only %d watchdogs ever entered the field at all" % (name, len(engaged))


# ---------------------------------------------------------------------------
# the flood's cost, and the tables that removed the multiplies from it
# ---------------------------------------------------------------------------

def test_the_neighbour_offsets_are_the_neighbour_table_times_the_width(glib):
    """The mover, the flood, the facing and the alcove test all index cells
    through GameState.neighbour_offset instead of multiplying dy by the width
    each time.  One wrong entry would send every one of them to the wrong cell,
    so the table is pinned against the accessors it was derived from."""
    level = make_level(glib, CORRIDOR)
    state = aihelp.new_state(glib, level)

    for n in range(CONST["NEIGHBOUR_COUNT"]):
        expected = glib.ai_neighbour_dx(n) + glib.ai_neighbour_dy(n) * level.width
        assert state.game.neighbour_offset[n] == expected, "neighbour %d" % n


def test_the_flood_visits_no_more_cells_than_the_level_has_floor(glib):
    """The rebuild's cost is proportional to the cells it dequeues, and nothing
    else: every cell is enqueued exactly when it is first reached.  Pinning the
    visit count is what makes the 68000 cycle budget checkable from a run and
    not only from the emitted loop - a flood that revisited cells would show up
    here as a count above the walkable total."""
    for name in ("level1", "level2"):
        path = blackice.ROOT / "levels" / ("%s.txt" % name)
        level = blackice.parse_level(glib, path.read_text())
        state = aihelp.new_state(glib, level)
        aihelp.step(glib, state)

        floor = len(_walkable_cells(level))
        visited = state.game.nav.visited
        assert 0 < visited <= floor, \
            "%s: the flood dequeued %d cells of %d walkable" % (name, visited, floor)
        reached = sum(1 for c in range(level.width * level.height)
                      if state.game.nav.steps[c] != NAV_UNREACHABLE)
        assert visited == reached, \
            "%s: %d dequeued but %d cells carry a distance" % (name, visited, reached)


def test_the_flood_marks_only_the_cells_the_grid_has(glib):
    """The clear is bounded by width * height, not by the 4,096-cell array, so
    the bytes past the grid are never written.  Nothing may come to depend on
    them: a cell index can never name one."""
    level = make_level(glib, CORRIDOR)
    state = aihelp.new_state(glib, level)
    aihelp.step(glib, state)

    cells = level.width * level.height
    inside = [state.game.nav.steps[c] for c in range(cells)]
    assert any(v != NAV_UNREACHABLE for v in inside), "the flood wrote nothing"


# ---------------------------------------------------------------------------
# the cones, driven through the sim rather than through the pure predicate
# ---------------------------------------------------------------------------

CONE_ROOM = [
    "##############",
    "#............#",
    "#............#",
    "#............#",
    "#............#",
    "#............#",
    "#.....@......#",
    "####s#########",
    "##############",
]

#: How far off the alcove's axis the two probe positions sit, in degrees either
#: side of the Sentry's 45 degree half-cone.
CONE_PROBE_MARGIN_DEGREES = 5
#: Distance from the body to the probe, in cells.  Well inside every roster
#: sight range, so only the cone is under test.
CONE_PROBE_CELLS = 3


def place_player_off_axis(state, body, degrees, cells=CONE_PROBE_CELLS):
    """Stand the player `degrees` off a NORTH-facing body's axis.

    The offsets are computed from the angle rather than written down, so a test
    that says "40 degrees" is testing 40 degrees and not a pair of magic
    coordinates that happen to be inside today's cone.
    """
    import math

    reach = cells * CELL
    state.engine.player.x = int(body.x + reach * math.tan(math.radians(degrees)))
    state.engine.player.y = int(body.y - reach)


@pytest.mark.parametrize("degrees,wakes", [
    (45 - CONE_PROBE_MARGIN_DEGREES, True),
    (45 + CONE_PROBE_MARGIN_DEGREES, False),
])
def test_the_sentry_alcove_is_itself_a_ninety_degree_aperture(glib, degrees, wakes):
    """DESIGN 8 gives the Sentry a 90 degree cone and DESIGN 11 rule 5 puts it
    in a 1-cell alcove, and the two agree for a reason worth writing down: the
    body stands half a cell behind a one-cell-wide mouth, so the MOUTH already
    admits exactly +/-45 degrees.  A player 50 degrees off the alcove axis has no
    line of sight at all - the grid walk's first step is into the jamb.

    That is why this is not a test of SENTRY_CONE_TAN_Q8: widening the cone in
    the stats table changes nothing an alcove-mounted Sentry can see.  The table
    is pinned in test_design_literals.py instead, and the cone arithmetic in
    test_the_sentry_cone_is_ninety_degrees above.
    """
    assert CONST["SENTRY_CONE_TAN_Q8"] == 256, "90 degrees: tan 45 = 1.0 in 8.8"
    level = make_level(glib, CONE_ROOM)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 7)
    place_player_off_axis(state, state.game.entities[sentry], degrees)

    for _ in range(3):
        aihelp.step(glib, state)
    awake = state.game.entities[sentry].state != CONST["ENT_STATE_IDLE"]
    assert awake == wakes, "%d degrees off the alcove axis" % degrees


WATCHDOG_CONE_ROOM = [
    "##############",
    "#............#",
    "#............#",
    "#............#",
    "#............#",
    "#....w..@....#",
    "##############",
]

#: The Watchdog's cone is 120 degrees, so its half-angle is 60.
WATCHDOG_HALF_CONE_DEGREES = 60


@pytest.mark.parametrize("degrees,wakes", [
    (WATCHDOG_HALF_CONE_DEGREES - CONE_PROBE_MARGIN_DEGREES, True),
    (WATCHDOG_HALF_CONE_DEGREES + CONE_PROBE_MARGIN_DEGREES, False),
])
def test_the_watchdog_wakes_only_inside_its_hundred_and_twenty_degree_cone(glib, degrees, wakes):
    """DESIGN 8: 120 degrees, so tan 60 = 1.7320508 and WATCHDOG_CONE_TAN_Q8 is
    443 in 8.8.  Same reasoning as the Sentry: the table is what is under test."""
    assert CONST["WATCHDOG_CONE_TAN_Q8"] == 443, "120 degrees: tan 60 = 1.732 in 8.8"
    level = make_level(glib, WATCHDOG_CONE_ROOM)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 5, 5)
    body = state.game.entities[dog]
    body.facing = NORTH             # the alcove-free case: aim it up the room
    place_player_off_axis(state, body, degrees)

    aihelp.step(glib, state)
    awake = state.game.entities[dog].state != CONST["ENT_STATE_IDLE"]
    assert awake == wakes, "%d degrees off the Watchdog's facing" % degrees


# ---------------------------------------------------------------------------
# sight is a line, not a distance
# ---------------------------------------------------------------------------

SENTRY_BEHIND_A_PILLAR = [
    "#############",
    "#....@......#",
    "#...........#",
    "#....#......#",
    "#...........#",
    "#####s#######",
    "#############",
]

SENTRY_CLEAR_SHOT = [
    "#############",
    "#....@......#",
    "#...........#",
    "#...........#",
    "#...........#",
    "#####s#######",
    "#############",
]


def open_the_iris(state, sentry):
    """Put a Sentry in the middle of its vulnerability window by hand, so the
    only thing left to decide the shot is whether it can see anything."""
    body = state.game.entities[sentry]
    body.state = CONST["ENT_STATE_ATTACK"]
    body.state_timer = CONST["SENTRY_IRIS_OPEN_TICKS"]
    body.attack_timer = 0


@pytest.mark.parametrize("rows,fires", [(SENTRY_CLEAR_SHOT, True),
                                        (SENTRY_BEHIND_A_PILLAR, False)])
def test_a_sentry_with_its_iris_open_fires_only_along_a_clear_line(glib, rows, fires):
    """DESIGN 8's sight rule is grid line of sight AND the cone AND the range.
    The player is dead ahead and four cells away in both maps; the only
    difference is one pillar on the line."""
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 5, 5)
    open_the_iris(state, sentry)

    aihelp.step(glib, state)
    hurt = state.game.integrity < CONST["PLAYER_INTEGRITY_MAX"]
    assert hurt == fires


# ---------------------------------------------------------------------------
# the Sentry's iris cooldown is deaf as well as invulnerable
# ---------------------------------------------------------------------------

def test_a_sentry_in_its_iris_cooldown_cannot_be_woken(glib):
    """sentry_step spends SENTRY_IRIS_SHUT_TICKS in IDLE with a running timer.
    A body with its iris shut is not watching and cannot react, so neither sight
    nor the noise of a shot may pull it back into ALERT before the timer runs
    out - otherwise the cooldown is a cooldown only for the Sentry's own gun."""
    level = make_level(glib, SENTRY_HALL)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 5)
    body = state.game.entities

    # Run the full charge/open cycle so the body reaches its shut cooldown.
    for _ in range(CONST["SENTRY_CHARGE_TICKS"] + CONST["SENTRY_IRIS_OPEN_TICKS"] + 2):
        aihelp.step(glib, state)
    assert body[sentry].state == CONST["ENT_STATE_IDLE"]
    assert body[sentry].state_timer > 0, "it should be in the shut cooldown"

    # The player is standing right in front of it, in cone and in range.
    assert glib.entity_alert(aihelp.ref(state), sentry) == 0
    assert body[sentry].state == CONST["ENT_STATE_IDLE"]

    for _ in range(CONST["SENTRY_IRIS_SHUT_TICKS"] - 2):
        aihelp.step(glib, state)
        assert body[sentry].state == CONST["ENT_STATE_IDLE"], "woken inside the cooldown"

    for _ in range(3):
        aihelp.step(glib, state)
    assert body[sentry].state == CONST["ENT_STATE_ALERT"], \
        "and it must wake again the moment the cooldown ends"


def test_a_sentry_in_its_cooldown_does_not_charge_the_trace_meter(glib):
    """DESIGN 9's +0.6 %/s is charged "while any enemy has LOS on you".  A body
    with its iris shut has no line on you at all, so it must not hold the
    meter's fastest rise on by itself."""
    level = make_level(glib, SENTRY_HALL)
    state = aihelp.new_state(glib, level)
    sentry = aihelp.entity_index_at(level, 4, 5)

    for _ in range(CONST["SENTRY_CHARGE_TICKS"] + CONST["SENTRY_IRIS_OPEN_TICKS"] + 2):
        aihelp.step(glib, state)
    assert state.game.entities[sentry].state == CONST["ENT_STATE_IDLE"]
    assert state.game.entities[sentry].state_timer > 0

    aihelp.step(glib, state)
    assert state.game.enemy_has_los == 0
    assert not (state.game.entities[sentry].flags & CONST["ENTITY_FLAG_SEES_PLAYER"])


# ---------------------------------------------------------------------------
# enemies and doors (DESIGN 8)
# ---------------------------------------------------------------------------

def hunting_dog_beside_a_door(glib, door_glyph, entity_state, tokens=0):
    rows = ["########",
            "#@..%s%s.#" % (door_glyph, "w"),
            "########"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 5, 1)
    body = state.game.entities[dog]
    body.state = entity_state
    body.state_timer = CONST["WATCHDOG_ALERT_TICKS"]
    state.game.tokens = tokens
    aihelp.step(glib, state)
    return state, state.game.doors[state.engine.door_of_cell[aihelp.cell(level, 4, 1)]]


@pytest.mark.parametrize("entity_state", ["ENT_STATE_ALERT", "ENT_STATE_CHASE",
                                          "ENT_STATE_FLEE"])
def test_a_hunting_enemy_opens_a_plain_gate_by_contact(glib, entity_state):
    """DESIGN 8: "Watchdogs and Tracers in ALERT, CHASE or FLEE open variant 16
    by contact".  ALERT is in that list and was missing: the eight-tick tell is
    time the body is already committed, and a gate that shuts in front of it
    during the snarl is the retreat cheese DESIGN 8 closes."""
    _state, door = hunting_dog_beside_a_door(glib, "+", CONST[entity_state])
    assert door.state == CONST["DOOR_STATE_OPENING"]


def test_an_idle_enemy_leaves_a_plain_gate_alone(glib):
    _state, door = hunting_dog_beside_a_door(glib, "+", CONST["ENT_STATE_IDLE"])
    assert door.state == CONST["DOOR_STATE_CLOSED"]


@pytest.mark.parametrize("door_glyph", ["1", "~"])
def test_a_hunting_enemy_never_opens_a_locked_or_jammed_gate(glib, door_glyph):
    """The other half of DESIGN 8's door rule: "locked variants 17-19 and jammed
    22 stay shut to them".  An enemy that could open the ALPHA gate would walk
    the level's whole lock order for the player.

    The PLAYER is given the token first, deliberately.  door_may_open is the
    player's own token ledger, so a locked gate refuses an empty-handed dog for
    a reason that has nothing to do with the dog - and a test run without the
    token passes even if the enemy path stops checking the variant at all.
    """
    state, door = hunting_dog_beside_a_door(glib, door_glyph, CONST["ENT_STATE_CHASE"],
                                            tokens=CONST["TOKEN_ALPHA_BIT"])
    assert door.state == CONST["DOOR_STATE_CLOSED"]


# ---------------------------------------------------------------------------
# facing is the sim's, not the test's
# ---------------------------------------------------------------------------

def test_a_moving_body_turns_to_face_the_cell_it_committed_to(glib):
    """An enemy's cone is only meaningful if the sprite faces where the body is
    going, so face_cell runs on every commit.  The facing is deliberately set
    WRONG here and the sim has to correct it."""
    rows = ["##########",
            "#w......@#",
            "##########"]
    level = make_level(glib, rows)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 1, 1)
    body = state.game.entities[dog]
    body.state = CONST["ENT_STATE_CHASE"]
    body.facing = WEST                      # pointing away from the player
    started_at = body.claim_cell

    for _ in range(40):
        aihelp.step(glib, state)
        if body.claim_cell != started_at:
            break
    assert body.claim_cell != started_at, "the dog never committed to a cell"
    assert body.facing == EAST, "a body walking east must face east"


def test_a_tracer_holding_its_ring_keeps_its_gun_on_the_player(glib):
    """DESIGN 8.1: the Tracer strafes, so its heading and its aim are different
    things - face_player is what keeps the gun on you while the feet go
    sideways."""
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    body = state.game.entities[tracer]
    body.facing = EAST                      # so it wakes at all
    for _ in range(CONST["TRACER_ALERT_TICKS"] + 2):
        aihelp.step(glib, state)
    assert body.state == CONST["ENT_STATE_CHASE"]

    body.facing = WEST                      # away from the player, deliberately
    aihelp.step(glib, state)
    assert body.facing == EAST, "a Tracer in CHASE aims at the player, not at its heading"


# ---------------------------------------------------------------------------
# the Tracer's ring, its patrol, and the corner it may not cut
# ---------------------------------------------------------------------------

RING_PILLARS = [
    "################",
    "#..............#",
    "#..###..###....#",
    "#..............#",
    "#..###..###....#",
    "#..t........@..#",
    "################",
]


def test_a_strafing_tracer_only_moves_to_ring_cells_it_can_shoot_from(glib):
    """DESIGN 8.1: the Tracer "prefers cells whose field value is 3-5 WITH line
    of sight to the player".  A ring cell behind a pillar is a cell it cannot
    fire from, so strafing into one is strafing out of the fight."""
    level = make_level(glib, RING_PILLARS)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 3, 5)
    body = state.game.entities[tracer]
    body.facing = EAST

    low, high = CONST["TRACER_RING_MIN_STEPS"], CONST["TRACER_RING_MAX_STEPS"]
    previous = body.claim_cell
    was_holding = False
    checked = 0
    for _ in range(400):
        aihelp.step(glib, state)
        holding = low <= state.game.nav.steps[body.claim_cell] <= high
        if body.claim_cell != previous and was_holding and body.state == CONST["ENT_STATE_CHASE"]:
            # The body was on the ring and moved, so pick_lateral_neighbour is
            # what chose the cell it is now in.
            cx = body.claim_cell % level.width
            cy = body.claim_cell // level.width
            assert los(glib, state, (cx, cy), (state.engine.player.x // CELL,
                                               state.engine.player.y // CELL)), \
                "the Tracer strafed to (%d, %d), which it cannot see the player from" % (cx, cy)
            checked += 1
        previous, was_holding = body.claim_cell, holding
    assert checked > 0, "the Tracer never strafed, so the LOS filter was never exercised"


PATROL_ROOM = [
    "#############",
    "#.......#...#",
    "#..t....#.@.#",
    "#.......#...#",
    "#############",
]

#: The patrol radius in whole cells, which is what the test measures in.
PATROL_RADIUS_CELLS = CONST["TRACER_PATROL_RADIUS_UNITS"] // CELL


def patrol_track(glib, seed, ticks=200):
    """The cells an IDLE Tracer visits on its beat, for one RNG seed."""
    level = make_level(glib, PATROL_ROOM)
    state = aihelp.new_state(glib, level, seed=seed)
    tracer = aihelp.entity_index_at(level, 3, 2)
    body = state.game.entities[tracer]
    track = []
    for _ in range(ticks):
        aihelp.step(glib, state)
        assert body.state == CONST["ENT_STATE_IDLE"], \
            "the wall must keep the player out of sight for the whole patrol"
        track.append(body.claim_cell)
    return level, body, track


def test_an_idle_tracer_patrols_instead_of_standing_still(glib):
    """DESIGN 8's state table: an IDLE Tracer "patrols its spawn room"."""
    level, body, track = patrol_track(glib, seed=1)
    assert len(set(track)) > 1, "the Tracer never left its spawn cell"

    spawn = (body.spawn_cell % level.width, body.spawn_cell // level.width)
    for cell_index in set(track):
        x, y = cell_index % level.width, cell_index // level.width
        assert abs(x - spawn[0]) <= PATROL_RADIUS_CELLS, (x, y)
        assert abs(y - spawn[1]) <= PATROL_RADIUS_CELLS, (x, y)


def test_two_seeds_walk_the_patrol_differently(glib):
    """DESIGN 4.3's LCG is the sim's only source of randomness, and until the
    patrol existed nothing drew from it: rng_seed was carried in every level
    header, hashed every tick, and read by nobody.  Two seeds must diverge, or
    the determinism contract has nothing behind it."""
    _level, _body, first = patrol_track(glib, seed=1)
    _level, _body, second = patrol_track(glib, seed=0x5EED)
    assert first != second
    # And the same seed twice is the same beat, which is the other half.
    _level, _body, again = patrol_track(glib, seed=1)
    assert first == again


DIAGONAL_TRAP = [
    "#####",
    "#w###",
    "##@.#",
    "#####",
]


def test_a_body_never_cuts_the_corner_between_two_walls(glib):
    """DESIGN 8.1's corner check: a diagonal is legal only if BOTH orthogonals
    it cuts between are open.  The dog here is walled in on all four sides and
    the player is on its diagonal - the one cell it must not squeeze through."""
    level = make_level(glib, DIAGONAL_TRAP)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 1, 1)
    body = state.game.entities[dog]
    body.state = CONST["ENT_STATE_CHASE"]
    trapped_in = body.claim_cell

    aihelp.step(glib, state)                 # tick 0 floods from the player cell
    assert state.game.nav.steps[aihelp.cell(level, 2, 2)] == 0, "the origin is the player"
    assert state.game.nav.steps[trapped_in] == NAV_UNREACHABLE, \
        "the trap is not 4-connected to the player, which is what makes the diagonal tempting"

    for _ in range(100):
        aihelp.step(glib, state)
    assert body.claim_cell == trapped_in, "the dog cut the corner between two walls"


# ---------------------------------------------------------------------------
# the sector edge a fleeing Tracer runs for
# ---------------------------------------------------------------------------

def test_the_outer_walkable_ring_is_reachable_on_both_shipped_maps(glib):
    """cell_is_sector_edge is what ends a Tracer's flee, so a map with no cell
    satisfying it would leave a fleeing body running until it fell out of the
    20-cell field.  Both shipped maps have floor on the ring - level 1 at the
    exit throat (15, 1) and along y = 30, level 2 at (27, 1) and the same
    southern chamber - and this is the assertion that says so."""
    for name, throat in (("level1", (15, 1)), ("level2", (27, 1))):
        path = blackice.ROOT / "levels" / ("%s.txt" % name)
        level = blackice.parse_level(glib, path.read_text())
        edge = [(x, y) for (x, y) in _walkable_cells(level)
                if x <= 1 or y <= 1 or x >= level.width - 2 or y >= level.height - 2]
        assert throat in edge, "%s: the exit throat is not on the outer ring" % name
        assert len(edge) >= 10, "%s: only %d ring cells" % (name, len(edge))


# ---------------------------------------------------------------------------
# the Tracer's gun and the neighbour it strafes to
# ---------------------------------------------------------------------------

def test_a_tracer_deals_the_design_eight_damage_at_its_rate(glib):
    """DESIGN 8: 10 ranged damage every 30 ticks."""
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    state.game.entities[tracer].facing = EAST
    full = CONST["PLAYER_INTEGRITY_MAX"]

    for _ in range(CONST["TRACER_ALERT_TICKS"] + 2):
        aihelp.step(glib, state)
    assert state.game.entities[tracer].state == CONST["ENT_STATE_CHASE"]
    assert state.game.integrity == full - CONST["TRACER_SHOT_DAMAGE"], \
        "the first shot lands the tick the tell ends"

    # And nothing lands again inside the rate of fire.
    for _ in range(CONST["TRACER_FIRE_TICKS"] - 2):
        aihelp.step(glib, state)
    assert state.game.integrity == full - CONST["TRACER_SHOT_DAMAGE"]


def blocks(state, cell_index):
    return (state.engine.blocking.solid[cell_index >> 3] >> (cell_index & 7)) & 1


def legal_lateral_candidates(glib, state, level, index):
    """Every cell pick_lateral_neighbour is allowed to choose, and how aligned
    each one is with the player bearing.

    Worked out in Python from the mirrors - open, corner-safe, unclaimed, inside
    the 3..5 ring, with line of sight - rather than read out of the sim, because
    what is under test is the sim's CHOICE among them.  The body is at its claim
    cell's centre when it picks, so that is the point the bearing is taken from.
    """
    low, high = CONST["TRACER_RING_MIN_STEPS"], CONST["TRACER_RING_MAX_STEPS"]
    body = state.game.entities[index]
    here = body.claim_cell
    from_x, from_y = point(here % level.width, here // level.width)
    bearing_x = state.engine.player.x - from_x
    bearing_y = state.engine.player.y - from_y
    out = []
    for n in range(CONST["NEIGHBOUR_COUNT"]):
        dx, dy = glib.ai_neighbour_dx(n), glib.ai_neighbour_dy(n)
        neighbour = here + state.game.neighbour_offset[n]
        if blocks(state, neighbour):
            continue
        if n >= CONST["NEIGHBOUR_ORTHO_COUNT"] and (
                blocks(state, here + dx) or blocks(state, here + dy * level.width)):
            continue                    # a diagonal may not cut a wall corner
        owner = state.game.occupancy.owner[neighbour]
        if owner != 0 and owner - 1 != index:
            continue
        if not low <= state.game.nav.steps[neighbour] <= high:
            continue
        centre_x, centre_y = point(neighbour % level.width, neighbour // level.width)
        if not glib.ai_line_of_sight(aihelp.ref(state), centre_x, centre_y,
                                     state.engine.player.x, state.engine.player.y):
            continue
        out.append((abs(dx * bearing_x + dy * bearing_y), neighbour))
    return out


def test_a_strafing_tracer_takes_the_least_aligned_neighbour(glib):
    """DESIGN 8.1: "strafing is choosing the LATERAL neighbour - the legal
    neighbour most PERPENDICULAR to the player bearing".  Taking the most
    aligned one instead would be a Tracer that charges or retreats, and both of
    those pass the ring test on their own, because closing in and backing off
    both leave the body inside the 3..5 band.

    The OPEN hall, not the pillared one: among pillars the legal ring cells came
    out symmetric about the player bearing, so the most and the least aligned
    were the same number and a swapped comparison changed nothing.  The
    assertion below refuses to pass unless it has seen a choice where they
    actually differ.
    """
    level = make_level(glib, TRACER_HALL)
    state = aihelp.new_state(glib, level)
    tracer = aihelp.entity_index_at(level, 2, 3)
    body = state.game.entities[tracer]
    body.facing = EAST

    low, high = CONST["TRACER_RING_MIN_STEPS"], CONST["TRACER_RING_MAX_STEPS"]
    discriminating = 0
    for _ in range(400):
        holding = (body.state == CONST["ENT_STATE_CHASE"]
                   and low <= state.game.nav.steps[body.claim_cell] <= high)
        candidates = legal_lateral_candidates(glib, state, level, tracer) if holding else []
        was = body.claim_cell
        aihelp.step(glib, state)
        if not holding or body.claim_cell == was:
            continue
        chosen = [alignment for alignment, cell_index in candidates
                  if cell_index == body.claim_cell]
        assert chosen, "the Tracer strafed to a cell pick_lateral_neighbour may not offer"
        alignments = [alignment for alignment, _cell in candidates]
        assert chosen[0] == min(alignments), \
            "the Tracer took an alignment of %d where %d was available" \
            % (chosen[0], min(alignments))
        if min(alignments) != max(alignments):
            discriminating += 1
    assert discriminating > 0, \
        "every strafe had all its options equally aligned, so the rule was never tested"


# ---------------------------------------------------------------------------
# a door never shuts on a body
# ---------------------------------------------------------------------------

DOORWAY = [
    "########",
    "#@..+w.#",
    "########",
]


def park_body_in_cell(state, level, index, x, y):
    """Hold a body in a cell: its claim, its occupancy byte and its position.

    The sim would walk it out again, and what is under test is the door's
    reaction to a body standing in its cell - not how the body got there.  It is
    held IDLE as well as still, because a HUNTING body beside a plain gate opens
    that gate by contact every tick (DESIGN 8) and would hold the leaf up for a
    reason that has nothing to do with the rule under test.
    """
    body = state.game.entities[index]
    body.state = CONST["ENT_STATE_IDLE"]
    state.game.occupancy.owner[body.claim_cell] = 0
    body.claim_cell = aihelp.cell(level, x, y)
    body.x = body.target_x = x * CELL + CENTRE
    body.y = body.target_y = y * CELL + CENTRE
    state.game.occupancy.owner[body.claim_cell] = index + 1


def open_the_gate(glib, state, level, x, y):
    glib.game_touch_door(aihelp.ref(state), aihelp.cell(level, x, y))
    for _ in range(CONST["DOOR_OPENING_TICKS"] + 1):
        aihelp.step(glib, state)
    door = state.game.doors[state.engine.door_of_cell[aihelp.cell(level, x, y)]]
    assert door.state == CONST["DOOR_STATE_OPEN"]
    return door


def test_a_gate_never_shuts_on_an_enemy_standing_in_it(glib):
    """The door state machine reverses on a body in its cell, and until it
    asked about enemies too, "a body" meant the player.  A Watchdog in a doorway
    would have the leaf come down through it - and worse, the cell's blocking
    bit set underneath it, which the collider and the flood both read as a wall
    with an enemy inside."""
    level = make_level(glib, DOORWAY)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 5, 1)
    door = open_the_gate(glib, state, level, 4, 1)

    for _ in range(CONST["DOOR_OPEN_TICKS"] + CONST["DOOR_CLOSING_TICKS"] + 2):
        park_body_in_cell(state, level, dog, 4, 1)
        aihelp.step(glib, state)
        assert door.state != CONST["DOOR_STATE_CLOSED"], "the leaf shut on the dog"
        assert not blocks(state, door.cell), "the cell went solid under a body"


def test_a_gate_with_nothing_in_it_does_shut(glib):
    """The other half: without the body the same gate closes on schedule, so the
    test above is about the body and not about a door that never closes."""
    level = make_level(glib, DOORWAY)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 5, 1)
    door = open_the_gate(glib, state, level, 4, 1)

    for _ in range(CONST["DOOR_OPEN_TICKS"] + CONST["DOOR_CLOSING_TICKS"] + 2):
        park_body_in_cell(state, level, dog, 6, 1)      # out of the doorway
        aihelp.step(glib, state)
    assert door.state == CONST["DOOR_STATE_CLOSED"]


def test_a_gate_stays_open_for_a_body_that_is_only_drawn_in_it(glib):
    """A mover claims the cell AHEAD and then walks to its centre, so a body
    halfway out of a doorway is drawn in it while the claim map already names
    the cell beyond.  It is still standing in the leaf's way."""
    level = make_level(glib, DOORWAY)
    state = aihelp.new_state(glib, level)
    dog = aihelp.entity_index_at(level, 5, 1)
    door = open_the_gate(glib, state, level, 4, 1)

    for _ in range(CONST["DOOR_OPEN_TICKS"] + CONST["DOOR_CLOSING_TICKS"] + 2):
        # Claiming the cell east of the gate, still drawn inside the gate.
        park_body_in_cell(state, level, dog, 5, 1)
        state.game.entities[dog].x = 4 * CELL + CENTRE
        aihelp.step(glib, state)
        assert door.state != CONST["DOOR_STATE_CLOSED"], "the leaf shut on the dog"
