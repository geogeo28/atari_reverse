"""A scripted playthrough of level 1's critical path.

The unit tests each pin one rule.  This one asserts the rules compose: that the
route DESIGN 12 prints - `@` -> Bus Hall -> west alcove (`p` ALPHA) -> door `1`
-> Handshake Hall -> `>` - can actually be walked, with the level's own geometry
and its own entity roster, ending in PHASE_LEVEL_CLEAR.

The input is generated rather than hand-authored.  A hand-written script would
pin the exact tick a turn starts, and every tuning change to a speed or a turn
rate would break it for no reason; a planner that follows the level's own BFS
route and steers with the same joystick word the game gets pins the ROUTE, which
is the thing DESIGN 12 actually promises.
"""
import aihelp
import blackice
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

LEVEL1 = blackice.ROOT / "levels" / "level1.txt"
LEVEL2 = blackice.ROOT / "levels" / "level2.txt"

# Generous: the route is about 60 cells and the player walks 0.15 cells a tick,
# so 400 ticks would do it in a straight line.  The cap only has to stop a
# runaway, not to be tight.
MAX_TICKS = 4000


def glyph_cells(level, glyph_cell_value):
    return [(x, y)
            for y in range(level.height)
            for x in range(level.width)
            if level.cells[y * level.width + x] == glyph_cell_value]


def entity_cell(level, entity_type):
    for i in range(level.entity_count):
        e = level.entities[i]
        if e.type == entity_type:
            return (e.cell_x, e.cell_y)
    raise AssertionError("no entity of type %d in %s" % (entity_type, level.name))


def approach_cell(level, door_cell):
    """The open neighbour of a terminal door: the cell you walk INTO it from."""
    x, y = door_cell
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < level.width and 0 <= ny < level.height:
            if level.cells[ny * level.width + nx] == 0:
                return (nx, ny)
    raise AssertionError("the exit at %s has no open neighbour" % (door_cell,))


# A `>` never opens, so the player can never stand in it.  The route ends beside
# it and then walks at it: the collider refuses the move, reports the bump, and
# that bump is what ends the sector (DESIGN 10).
PUSH_TICKS = 200


ENEMY_TYPES = (CONST["ENT_WATCHDOG"], CONST["ENT_SENTRY"], CONST["ENT_TRACER"])


class Run:
    """What a driven route produced: the finished state, how far the planner
    got, and which enemies noticed at any point along the way.

    "At any point" matters: a Sentry that charges, fires and shuts its iris is
    back in IDLE by the end, so a check taken only at the finish would report a
    level that shot at you as one that never saw you.
    """

    def __init__(self, state, route_length):
        self.state = state
        self.route_length = route_length
        self.waypoints_reached = 0
        self.alerted = set()

    def observe(self, level):
        for i in range(level.entity_count):
            body = self.state.game.entities[i]
            if body.type in ENEMY_TYPES and body.state != CONST["ENT_STATE_IDLE"]:
                self.alerted.add(i)


def run_route(glib, level, waypoints, push_into=None, invulnerable=True):
    """Drive the player through `waypoints`, then lean on `push_into`."""
    state = aihelp.new_state(glib, level)
    route = []
    here = (level.start_cell_x, level.start_cell_y)
    for goal in waypoints:
        leg = aihelp.bfs_route(level, here, goal)
        route.extend(leg[1:])
        here = goal
    run = Run(state, len(route))

    def tick(word):
        if invulnerable:
            # This test pins the ROUTE.  Combat is pinned by test_ai and
            # test_weapons, and letting a Watchdog end the run here would make
            # a navigation test fail for a damage reason.
            state.game.integrity = CONST["PLAYER_INTEGRITY_MAX"]
        aihelp.step(glib, state, word)
        run.observe(level)

    for _ in range(MAX_TICKS):
        if state.game.phase != CONST["PHASE_PLAYING"] or run.waypoints_reached >= len(route):
            break
        word, arrived = aihelp.autopilot_input(state, route[run.waypoints_reached])
        if arrived:
            run.waypoints_reached += 1
            continue
        tick(word)

    for _ in range(PUSH_TICKS):
        if push_into is None or state.game.phase != CONST["PHASE_PLAYING"]:
            break
        word, _ = aihelp.autopilot_input(state, push_into)
        tick(word or CONST["INPUT_FORWARD"])
    return run


def test_level_one_can_be_walked_from_the_boot_chamber_to_the_exit(glib):
    """DESIGN 12's route, end to end, with the token gate in the middle of it."""
    level = blackice.parse_level(glib, LEVEL1.read_text())
    token = entity_cell(level, CONST["ENT_TOKEN_ALPHA"])
    exit_cell = glyph_cells(level, CONST["DOOR_SECTOR_EXIT"])[0]

    run = run_route(glib, level, [token, approach_cell(level, exit_cell)],
                    push_into=exit_cell)

    assert run.state.game.tokens & CONST["TOKEN_ALPHA_BIT"], \
        "the route runs over the ALPHA token in the west alcove"
    assert run.state.game.phase == CONST["PHASE_LEVEL_CLEAR"], \
        "reached waypoint %d of %d, phase %d" % (run.waypoints_reached, run.route_length,
                                                 run.state.game.phase)
    assert run.state.game.next_sector_index == level.sector_index + 1


def test_the_alpha_gate_is_what_makes_level_one_a_route_and_not_a_corridor(glib):
    """The same walk without the detour to the token must NOT finish: if the
    locked door opened for anyone, DESIGN 12's whole shape would be decorative."""
    level = blackice.parse_level(glib, LEVEL1.read_text())
    exit_cell = glyph_cells(level, CONST["DOOR_SECTOR_EXIT"])[0]

    run = run_route(glib, level, [approach_cell(level, exit_cell)], push_into=exit_cell)

    assert not (run.state.game.tokens & CONST["TOKEN_ALPHA_BIT"])
    assert run.state.game.phase == CONST["PHASE_PLAYING"], \
        "the ALPHA gate let the player through without the token"


def test_level_two_can_be_walked_in_its_lock_order(glib):
    """DESIGN 13's route takes BETA first and ALPHA second, and the validator
    reports exactly that order.  Walking it proves the two gates agree."""
    level = blackice.parse_level(glib, LEVEL2.read_text())
    beta = entity_cell(level, CONST["ENT_TOKEN_BETA"])
    alpha = entity_cell(level, CONST["ENT_TOKEN_ALPHA"])
    exit_cell = glyph_cells(level, CONST["DOOR_SECTOR_EXIT"])[0]

    run = run_route(glib, level, [beta, alpha, approach_cell(level, exit_cell)],
                    push_into=exit_cell)

    assert run.state.game.tokens & CONST["TOKEN_BETA_BIT"]
    assert run.state.game.tokens & CONST["TOKEN_ALPHA_BIT"]
    assert run.state.game.phase == CONST["PHASE_LEVEL_CLEAR"], \
        "reached waypoint %d of %d, phase %d" % (run.waypoints_reached, run.route_length,
                                                 run.state.game.phase)


def test_the_playthrough_meets_the_roster_design_twelve_promises(glib):
    """A run that never fights still has to be watched: the level-1 roster is
    four Watchdogs and a Sentry, and the walk must actually wake something."""
    level = blackice.parse_level(glib, LEVEL1.read_text())
    token = entity_cell(level, CONST["ENT_TOKEN_ALPHA"])
    exit_cell = glyph_cells(level, CONST["DOOR_SECTOR_EXIT"])[0]

    run = run_route(glib, level, [token, approach_cell(level, exit_cell)],
                    push_into=exit_cell)

    assert run.alerted, "a full lap of INGRESS should have been noticed by something"
    assert run.state.engine.trace_milli > 0, "the meter runs the whole time"


def test_a_run_is_reproducible_tick_for_tick(glib):
    """The planner is deterministic and so is the sim, so two runs of the same
    route must end on the same state hash - which is what makes this test a
    regression net and not just a smoke test."""
    level = blackice.parse_level(glib, LEVEL1.read_text())
    token = entity_cell(level, CONST["ENT_TOKEN_ALPHA"])
    exit_cell = glyph_cells(level, CONST["DOOR_SECTOR_EXIT"])[0]
    waypoints = [token, approach_cell(level, exit_cell)]

    first = run_route(glib, level, waypoints, push_into=exit_cell)
    second = run_route(glib, level, waypoints, push_into=exit_cell)
    assert (glib.game_state_hash(aihelp.ref(first.state))
            == glib.game_state_hash(aihelp.ref(second.state)))
    assert first.state.game.route_ticks == second.state.game.route_ticks
