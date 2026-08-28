"""The Buster: what its hitscan finds, what it costs, and what it wakes.

DESIGN 7 makes the weapon a grid walk rather than a projectile, so the whole of
it is "what is in the first cell that has something in it" - and the one thing
that must never happen is the shot reaching the wall behind a body.
"""
import ctypes

import aihelp
from aihelp import CELL, glib    # noqa: F401 - the session fixture the tests take
from blackice import CONST

HEADER = "# name: WEAPONS\n# start_facing: 256\n\n"      # brad 256 = east
EAST = 0


def range_level(glib, dogs_at=()):
    """A 20-cell east-west corridor with the player at the west end and a
    Watchdog wherever the caller asks for one."""
    width = 22
    row = ["#"] + ["."] * (width - 2) + ["#"]
    row[1] = "@"
    for x in dogs_at:
        row[x] = "w"
    rows = ["#" * width, "".join(row), "#" * width]
    return aihelp.level_from_rows(glib, rows, HEADER)


def aim_east(state):
    state.engine.player.angle = EAST


def hitscan(glib, state):
    distance = ctypes.c_int32(0)
    target = glib.weapon_hitscan_target(aihelp.ref(state), ctypes.byref(distance))
    return target, distance.value


def test_the_shot_stops_at_the_first_body_and_not_the_wall_behind_it(glib):
    level = range_level(glib, dogs_at=(5,))
    state = aihelp.new_state(glib, level)
    aim_east(state)

    dog = aihelp.entity_index_at(level, 5, 1)
    target, _ = hitscan(glib, state)
    assert target == dog


def test_the_shot_stops_at_the_nearest_of_several_bodies(glib):
    """The corridor holds three dogs in a line.  A shot that walked past the
    first would be the classic hitscan bug and it is the reason cells carry a
    claim rather than the shot scanning the entity table."""
    level = range_level(glib, dogs_at=(4, 8, 12))
    state = aihelp.new_state(glib, level)
    aim_east(state)

    nearest = aihelp.entity_index_at(level, 4, 1)
    target, _ = hitscan(glib, state)
    assert target == nearest


def test_a_wall_stops_the_shot(glib):
    rows = ["#######",
            "#@.#w.#",
            "#######"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aim_east(state)

    assert hitscan(glib, state)[0] == -1


def test_a_closed_door_stops_the_shot_and_an_open_one_does_not(glib):
    rows = ["#######",
            "#@.+w.#",
            "#######"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 4, 1)

    assert hitscan(glib, state)[0] == -1
    glib.game_touch_door(aihelp.ref(state), aihelp.cell(level, 3, 1))
    for _ in range(CONST["DOOR_OPENING_TICKS"] + 1):
        aihelp.step(glib, state)
    assert hitscan(glib, state)[0] == dog


def test_a_body_beyond_the_range_is_not_hit(glib):
    """DESIGN 7 gives the Buster 12 cells.  A dog at 15 is out of reach even
    down an empty corridor."""
    level = range_level(glib, dogs_at=(17,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    assert hitscan(glib, state)[0] == -1


# ---------------------------------------------------------------------------
# damage, rate and cost
# ---------------------------------------------------------------------------

FIRE = CONST["INPUT_FIRE"]


def test_firing_costs_a_cycle_and_deals_the_near_damage(glib):
    level = range_level(glib, dogs_at=(3,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 3, 1)

    cycles = state.game.cycles
    aihelp.step(glib, state, FIRE)
    assert state.game.cycles == cycles - CONST["BUSTER_COST_CYCLES"]
    assert state.game.entities[dog].hp == CONST["WATCHDOG_HP"] - CONST["BUSTER_DAMAGE_NEAR"]


def test_damage_halves_past_eight_cells(glib):
    """DESIGN 7: 8 damage, 4 beyond 8 cells."""
    level = range_level(glib, dogs_at=(11,))       # 10 cells away
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 11, 1)

    aihelp.step(glib, state, FIRE)
    assert state.game.entities[dog].hp == CONST["WATCHDOG_HP"] - CONST["BUSTER_DAMAGE_FAR"]


def test_holding_fire_auto_repeats_at_the_weapon_rate(glib):
    """DESIGN 6: the press is an edge and holding auto-repeats at the rate.
    Both fall out of one rule, so the count over a fixed window is the test."""
    level = range_level(glib)
    state = aihelp.new_state(glib, level)
    aim_east(state)

    ticks = CONST["BUSTER_RATE_TICKS"] * 4
    start = state.game.cycles
    for _ in range(ticks):
        aihelp.step(glib, state, FIRE)
    assert start - state.game.cycles == 4, "held fire should repeat every 5 ticks"


def test_tapping_fire_faster_than_the_rate_does_not_double_up(glib):
    level = range_level(glib)
    state = aihelp.new_state(glib, level)
    aim_east(state)

    start = state.game.cycles
    for tick in range(CONST["BUSTER_RATE_TICKS"] * 2):
        aihelp.step(glib, state, FIRE if tick % 2 == 0 else 0)
    assert start - state.game.cycles == 2


def test_the_brownout_floor_still_fires_weaker_and_slower(glib):
    """DESIGN 7: at 0 cycles the Buster still fires - 3 damage, 10-tick rate."""
    level = range_level(glib, dogs_at=(3,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    state.game.cycles = 0
    dog = aihelp.entity_index_at(level, 3, 1)
    full = CONST["WATCHDOG_HP"]

    aihelp.step(glib, state, FIRE)
    assert state.game.cycles == 0, "a brownout shot costs nothing it does not have"
    assert state.game.entities[dog].hp == full - CONST["BUSTER_BROWNOUT_DAMAGE"]

    # And it is slower: nothing lands again inside the normal rate.
    for _ in range(CONST["BUSTER_RATE_TICKS"]):
        aihelp.step(glib, state, FIRE)
    assert state.game.entities[dog].hp == full - CONST["BUSTER_BROWNOUT_DAMAGE"]
    for _ in range(CONST["BUSTER_BROWNOUT_RATE_TICKS"]):
        aihelp.step(glib, state, FIRE)
    assert state.game.entities[dog].hp == full - 2 * CONST["BUSTER_BROWNOUT_DAMAGE"]


def test_a_shot_raises_the_muzzle_flash_for_the_renderer(glib):
    level = range_level(glib)
    state = aihelp.new_state(glib, level)
    aim_east(state)

    assert state.game.muzzle_flash == 0
    aihelp.step(glib, state, FIRE)
    assert state.game.muzzle_flash == CONST["MUZZLE_FLASH_TICKS"]
    aihelp.step(glib, state, 0)
    assert state.game.muzzle_flash == 0


def test_enough_shots_kill_and_the_body_dissolves_then_vanishes(glib):
    level = range_level(glib, dogs_at=(3,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 3, 1)

    shots = 0
    while state.game.entities[dog].hp > 0 and shots < 40:
        # The cell it dies IN, not the cell it was authored in: the first shot
        # is heard, the dog wakes and chases, and asserting on the authored cell
        # would be asserting that a body it had already walked out of is empty.
        death_cell = state.game.entities[dog].claim_cell
        aihelp.step(glib, state, FIRE)
        shots += 1
    assert state.game.entities[dog].hp == 0
    assert state.game.entities[dog].state == CONST["ENT_STATE_DEAD"]
    assert state.engine.entity_alive[dog] == 1, "the dissolve is still drawn"
    assert state.game.kills == 1
    # entity_die releases the claim the instant the body dies, so a dissolving
    # dog stops blocking the corridor before it stops being drawn.
    assert glib.entity_at_cell(aihelp.ref(state), death_cell) == -1, \
        "a dead body must release the cell it died in"

    for _ in range(CONST["ENEMY_DISSOLVE_TICKS"]):
        aihelp.step(glib, state)
    assert state.engine.entity_alive[dog] == 0, "the body is removed after the dissolve"
    assert glib.entity_at_cell(aihelp.ref(state), death_cell) == -1


def test_firing_near_an_unalerted_enemy_wakes_it_and_costs_trace(glib):
    """DESIGN 8: noise alerts regardless of cone.  DESIGN 9 charges +2% for it."""
    # 3 cells away - inside the 5-cell noise radius - but behind a wall, so
    # nothing but the sound of the shot can reach it.
    rows = ["######",
            "#@.#w#",
            "######"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 4, 1)

    assert state.game.entities[dog].state == CONST["ENT_STATE_IDLE"]
    before = state.engine.trace_milli
    aihelp.step(glib, state, FIRE)

    assert state.game.entities[dog].state != CONST["ENT_STATE_IDLE"], \
        "a shot inside the noise radius must be heard"
    assert state.engine.trace_milli - before >= CONST["TRACE_BUMP_NOISE_SHOT"]


def test_firing_with_nothing_in_earshot_costs_no_trace_bump(glib):
    level = range_level(glib)
    state = aihelp.new_state(glib, level)
    aim_east(state)

    before = state.engine.trace_milli
    aihelp.step(glib, state, FIRE)
    # The EXACT first-tick rise and nothing else.  "Under the noise bump" was a
    # 2,000 milli-percent window around a real value of 7, which a bump ten
    # times too small would still have satisfied.
    base_rise = level.trace_base_rate // CONST["SIM_HZ"]
    assert state.engine.trace_milli - before == base_rise


def test_a_shot_hits_a_body_drawn_across_the_line_while_it_claims_elsewhere(glib):
    """DESIGN 8.1 has a mover claim the cell AHEAD and then walk to its centre,
    so a body crossing the player's line of fire sideways is drawn on the line
    while the claim map names the cell it is heading for.  The visible body must
    be hittable, or the shot passes through a dog the player is looking at."""
    # The dog walks south across the corridor the player is aiming down.
    rows = ["#####",
            "#@.w#",
            "#####"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 3, 1)
    on_the_line = state.game.entities[dog].claim_cell

    # Hand the body a claim one cell off the line and leave it drawn where it
    # is: exactly the state advance_to_claim holds it in mid-crossing.
    aihelp.clear_events(state)
    state.game.occupancy.owner[on_the_line] = 0
    state.game.entities[dog].claim_cell = aihelp.cell(level, 3, 0)
    state.game.occupancy.owner[aihelp.cell(level, 3, 0)] = dog + 1

    assert glib.entity_at_cell(aihelp.ref(state), on_the_line) == -1, \
        "the claim map must NOT name the cell the body is drawn in"
    assert glib.entity_hittable_in_cell(aihelp.ref(state), on_the_line) == dog
    assert hitscan(glib, state)[0] == dog


def test_a_body_is_still_hittable_in_the_cell_it_has_claimed(glib):
    """The other half of the rule: the cell a body owns stops a shot even while
    the body itself is still walking into it."""
    level = range_level(glib, dogs_at=(5,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 5, 1)
    claimed = state.game.entities[dog].claim_cell

    # Drawn a whole cell short of the claim, as it is for most of a crossing.
    state.game.entities[dog].x -= CELL
    assert glib.entity_hittable_in_cell(aihelp.ref(state), claimed) == dog


def test_a_shot_paid_for_with_the_last_cycle_is_not_a_brownout(glib):
    """The cycle is spent BEFORE the damage is worked out, so a damage rule that
    re-read `cycles` would call the one properly paid shot a brownout."""
    level = range_level(glib, dogs_at=(3,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    state.game.cycles = CONST["BUSTER_COST_CYCLES"]
    dog = aihelp.entity_index_at(level, 3, 1)

    aihelp.step(glib, state, FIRE)
    assert state.game.cycles == 0
    assert state.game.entities[dog].hp == CONST["WATCHDOG_HP"] - CONST["BUSTER_DAMAGE_NEAR"], \
        "the last paid shot deals full damage, not the brownout floor"


def test_the_shot_finds_a_dog_that_has_walked_off_its_authored_cell(glib):
    """The hitscan reads the runtime claim, not the level file, so a body that
    has moved is hit where it is and not where it was authored."""
    level = range_level(glib, dogs_at=(9,))
    state = aihelp.new_state(glib, level)
    aim_east(state)
    dog = aihelp.entity_index_at(level, 9, 1)
    state.game.entities[dog].state = CONST["ENT_STATE_CHASE"]

    for _ in range(60):
        aihelp.step(glib, state)
    moved_cell = state.game.entities[dog].claim_cell
    assert moved_cell != aihelp.cell(level, 9, 1), "the dog should have closed"
    assert glib.entity_at_cell(aihelp.ref(state), moved_cell) == dog
    assert hitscan(glib, state)[0] == dog


# ---------------------------------------------------------------------------
# the noise of a shot (DESIGN 8, DESIGN 9)
# ---------------------------------------------------------------------------

def dog_behind_a_wall(glib, cells_away):
    """A Watchdog `cells_away` from the player with a wall between them, so the
    sound of a shot is the only thing that can reach it."""
    width = cells_away + 3
    row = ["#"] * width
    row[1] = "@"
    for x in range(2, cells_away):
        row[x] = "."
    row[cells_away] = "#"           # the wall
    row[cells_away + 1] = "w"
    rows = ["#" * width, "".join(row), "#" * width]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)
    aim_east(state)
    return level, state, aihelp.entity_index_at(level, cells_away + 1, 1)


def test_the_noise_radius_is_the_design_eight_figure_and_not_a_cell_more(glib):
    """DESIGN 8 gives the Watchdog a 5-cell noise radius.  A radius twice that
    would wake half a level off one shot, and a test that only ever fires next
    to the dog cannot tell the two apart."""
    inside = CONST["WATCHDOG_NOISE_UNITS"] // CELL
    _level, near, dog = dog_behind_a_wall(glib, inside)
    aihelp.step(glib, near, FIRE)
    assert near.game.entities[dog].state != CONST["ENT_STATE_IDLE"], \
        "%d cells is inside the 5-cell noise radius" % inside

    _level, far, dog = dog_behind_a_wall(glib, inside + 1)
    aihelp.step(glib, far, FIRE)
    assert far.game.entities[dog].state == CONST["ENT_STATE_IDLE"], \
        "%d cells is outside it" % (inside + 1)


def test_the_noise_of_a_shot_only_wakes_bodies_that_were_asleep(glib):
    """DESIGN 9 charges +2% for "firing within an UNALERTED enemy's noise
    radius".  A body already chasing you has nothing left to be told, so a
    second shot beside it must cost nothing - or the charge becomes a per-shot
    tax and DESIGN 9.1's reference run stops being reachable."""
    inside = CONST["WATCHDOG_NOISE_UNITS"] // CELL
    _level, state, dog = dog_behind_a_wall(glib, inside)

    aihelp.step(glib, state, FIRE)
    assert state.game.entities[dog].state != CONST["ENT_STATE_IDLE"]

    for _ in range(CONST["BUSTER_RATE_TICKS"]):
        aihelp.step(glib, state)
    before = state.engine.trace_milli
    aihelp.step(glib, state, FIRE)
    rise = state.engine.trace_milli - before
    assert rise < CONST["TRACE_BUMP_NOISE_SHOT"], \
        "the second shot re-charged the noise bump on an already-woken dog"


def test_a_shot_into_the_corner_of_the_map_reads_nothing_off_the_grid(glib):
    """The hitscan asks every cell it crosses who is standing there, and the
    LAST cell it crosses is the border wall - the one place in the game layer a
    neighbour walk starts from a cell that is not walkable.  From cell 0 a
    northward offset wraps a uint16 to 65,504, which is a read far past the
    occupancy map: harmless-looking on the host, a read of the 68000 vector page
    on target.  Firing at both border corners is the case that reaches it."""
    rows = ["####",
            "#@.#",
            "#..#",
            "####"]
    level = aihelp.level_from_rows(glib, rows, HEADER)
    state = aihelp.new_state(glib, level)

    # North into the top-left corner, then west into the same wall: the two
    # directions whose neighbour offsets go negative from the lowest cell index.
    for angle in (3 * CONST["ANGLE_QUARTER_TURN"], 2 * CONST["ANGLE_QUARTER_TURN"]):
        state.engine.player.angle = angle
        assert hitscan(glib, state)[0] == -1
        aihelp.step(glib, state, FIRE)
        for _ in range(CONST["BUSTER_RATE_TICKS"]):
            aihelp.step(glib, state)

    # And the far corner, where a southward offset runs off the other end.
    aihelp.put_player(state, 2, 2, CONST["ANGLE_QUARTER_TURN"])
    assert hitscan(glib, state)[0] == -1
