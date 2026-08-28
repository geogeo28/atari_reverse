"""Billboard projection, the far-to-near sort, the depth test and the drop
budget.  Sprites are the one stage that can write over a wall it should be
behind, so the z test gets a case of its own rather than a soak."""
import ctypes

import blackice
from blackice import CONST, make_level

CELL = blackice.CELL
CENTRE = blackice.CENTRE
COLUMNS_HIGH = CONST["RENDER_COLUMNS_HIGH"]
# Map units between the eye and a billboard standing right in front of it.
# Well past SPRITE_MIN_DEPTH, and close enough to fill the window.
NOSE_TO_NOSE_UNITS = 100


def room_with_entities(lib, entities, width=16, height=16, walls=()):
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    for x, y in walls:
        cells[y * width + x] = 1
    level = make_level(lib, width, height, cells, (8, 8))
    level.entity_count = len(entities)
    for i, (kind, cell_x, cell_y) in enumerate(entities):
        level.entities[i].type = kind
        level.entities[i].cell_x = cell_x
        level.entities[i].cell_y = cell_y
    return level



def state_at_full_width(lib, level):
    """A state rendering at 160 columns.

    The shipping default is 80 (DESIGN v2.1 17.3), and the tests below read the
    160-column ray tables by name, so they have to say which width they mean
    rather than inherit whichever one ships this week.
    """
    state = blackice.new_state(lib, level)
    state.detail_level = CONST["DETAIL_COLUMNS_160"]
    return state


def look_east(state, cell_x=8, cell_y=8):
    state.player.x = cell_x * CELL + CENTRE
    state.player.y = cell_y * CELL + CENTRE
    state.player.angle = 0


def test_a_sprite_straight_ahead_lands_in_the_middle_column(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 8)])
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    assert sprites.count == 1
    sprite = sprites.entries[0]
    centre = sprite.left + sprite.cols // 2
    assert abs(centre - COLUMNS_HIGH // 2) <= 1
    assert sprite.dist == 4 * CELL
    # A billboard is one cell tall, so it projects to a wall's height.
    heights = blackice.table(lib, "g_slice_height", ctypes.c_uint16, blackice.DIST_TABLE_SIZE)
    assert sprite.rows == heights[sprite.dist]
    assert sprite.top == (blackice.RENDER_H - sprite.rows) // 2


def test_lateral_offset_moves_the_sprite_the_right_way(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 6),
                                     (CONST["ENT_WATCHDOG"], 12, 10)])
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    assert sprites.count == 2
    # World y runs south, and south is the player's right when facing east.
    north, south = sorted(sprites.entries[:2], key=lambda s: s.left)
    assert north.left < COLUMNS_HIGH // 2 < south.left + south.cols


def test_the_list_is_sorted_far_to_near(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 10, 8),
                                     (CONST["ENT_WATCHDOG"], 14, 8),
                                     (CONST["ENT_WATCHDOG"], 12, 8)])
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    distances = [sprites.entries[i].dist for i in range(sprites.count)]
    assert distances == sorted(distances, reverse=True)


def test_sprites_behind_and_beyond_the_radius_are_culled(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 4, 8)], width=40, height=16)
    state = state_at_full_width(lib, level)
    look_east(state, cell_x=8)                          # the entity is behind us
    sprites = blackice.SpriteList()
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    assert sprites.count == 0

    level.entities[0].cell_x = 8 + CONST["RENDER_RADIUS_NOMINAL"] + 2
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    assert sprites.count == 0, "drawn past the throttle radius"


def test_a_wall_hides_the_sprite_behind_it(lib):
    """The per-column depth test.  Without it a sprite in the next room shows
    through the wall, which is the classic billboard bug."""
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 8)],
                               walls=[(10, 7), (10, 8), (10, 9)])
    state = state_at_full_width(lib, level)
    look_east(state)
    scratch = blackice.RenderScratch()
    chunky = blackice.chunky_buffer()

    lib.render_frame(ctypes.byref(state), ctypes.byref(scratch), chunky)
    hidden = bytes(chunky.raw)

    # Remove the wall and the same sprite must now paint over those columns.
    level.cells[8 * level.width + 10] = 0
    level.cells[7 * level.width + 10] = 0
    level.cells[9 * level.width + 10] = 0
    state = state_at_full_width(lib, level)
    look_east(state)
    lib.render_frame(ctypes.byref(state), ctypes.byref(scratch), chunky)

    assert bytes(chunky.raw) != hidden
    sprite_colours = {CONST["COLOUR_VOID"]}
    assert set(chunky.raw) - set(hidden) - sprite_colours, "the sprite never appeared"


def test_the_pixel_budget_drops_the_farthest_first(lib):
    """DESIGN 8.2: the budget is spent nearest-first, so the nearest sprite can
    never be dropped and the far ones are what vanish.

    What each sprite COSTS is the pixels it would actually write, after the
    window clip - sprite_pixel_cost, which test_sprite_budget.py pins on its
    own - and the exempt sprite (here the nearest, since nothing is attacking)
    is drawn free of the accumulator.  So the budget bounds the OTHERS.
    """
    entities = [(CONST["ENT_WATCHDOG"], 9 + i, 8) for i in range(8)]
    level = room_with_entities(lib, entities, width=24, height=16)
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()
    lib.sprite_pixel_cost.argtypes = [ctypes.POINTER(blackice.RenderSprite)]
    lib.sprite_pixel_cost.restype = ctypes.c_int32

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    kept = [sprites.entries[i].dist for i in range(sprites.count)]

    assert sprites.count >= 1
    assert min(kept) == CELL, "the nearest sprite was dropped"
    budget = blackice.table(lib, "g_column_sets", blackice.ColumnSet,
                            CONST["DETAIL_LEVEL_COUNT"])[state.detail_level].sprite_budget
    costs = sorted(lib.sprite_pixel_cost(ctypes.byref(sprites.entries[i]))
                   for i in range(sprites.count))
    assert sum(costs[:-1]) <= budget, "the non-exempt sprites overspent the budget"


def test_eighty_column_mode_halves_the_sprite_width_but_not_its_height(lib):
    """The window is 80 rows in both modes; only the horizontal resolution
    changes, so a billboard must squash sideways and keep its height."""
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 8)])
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    state.detail_level = CONST["DETAIL_COLUMNS_160"]
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    high = (sprites.entries[0].cols, sprites.entries[0].rows, sprites.entries[0].tex_step_u)

    # Same throttle, only the width changes: DESIGN 5 keeps the two apart.
    state.detail_level = CONST["DETAIL_COLUMNS_80"]
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    low = (sprites.entries[0].cols, sprites.entries[0].rows, sprites.entries[0].tex_step_u)

    assert low[0] == high[0] // 2
    assert low[1] == high[1]
    assert low[2] == high[2] * 2


def budget_of(lib, state):
    return blackice.table(lib, "g_column_sets", blackice.ColumnSet,
                          CONST["DETAIL_LEVEL_COUNT"])[state.detail_level].sprite_budget


def crowd(lib, count, width=40, height=16, first_cell=9):
    """A row of entities marching away from the player, nearest at `first_cell`."""
    return room_with_entities(lib, [(CONST["ENT_WATCHDOG"], first_cell + i, 8)
                                    for i in range(count)],
                              width=width, height=height)


def test_the_budget_actually_cuts_the_list_down(lib):
    """Ten times the budget still fits every sprite, so a mutation that widened
    it survived every assertion the suite had.  This one says the cut happened:
    fewer sprites came out than went in."""
    level = crowd(lib, 16)
    state = state_at_full_width(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    projected = sum(1 for i in range(16)
                    if level.entities[i].cell_x - 8 <= CONST["RENDER_RADIUS_NOMINAL"])
    assert sprites.count < projected, \
        "%d sprites were in range and all %d survived the budget" % (projected, sprites.count)


def test_what_is_kept_costs_no_more_than_the_budget_plus_one_sprite(lib):
    """The exact contract: the walk stops at the first sprite that would take
    it over, so the total is the budget plus at most that one sprite's cost."""
    for detail in range(CONST["DETAIL_LEVEL_COUNT"]):
        for throttle in range(CONST["THROTTLE_MODE_COUNT"]):
            level = crowd(lib, 16)
            state = state_at_full_width(lib, level)
            state.throttle = throttle
            state.detail_level = detail
            look_east(state)
            sprites = blackice.SpriteList()

            lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
            if sprites.count == 0:
                continue
            costs = [sprites.entries[i].cols * sprites.entries[i].rows
                     for i in range(sprites.count)]
            budget = budget_of(lib, state)
            assert sum(costs) <= budget + max(costs), \
                "detail %d throttle %d spent %d on a budget of %d" % (
                    detail, throttle, sum(costs), budget)


def test_the_nearest_sprite_is_kept_even_when_it_alone_blows_the_budget(lib):
    """The guard that makes "nearest is never dropped" true.  Deleting it left
    an empty list whenever one sprite filled the window, and an empty list
    passes every "fewer than before" assertion."""
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 9, 8)], width=24)
    state = state_at_full_width(lib, level)
    look_east(state)
    # Close enough that the billboard fills the window: at this depth its
    # projected height exceeds the whole 80-row window and its width is clipped
    # to the frame, so it costs more than the frame's entire sprite budget.
    state.player.x = 9 * CELL + CENTRE - NOSE_TO_NOSE_UNITS
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    assert sprites.count == 1
    cost = sprites.entries[0].cols * sprites.entries[0].rows
    assert cost > budget_of(lib, state), \
        "the case is not exercised: one sprite costs %d, the budget is %d" % (
            cost, budget_of(lib, state))


def test_the_nearest_sprite_survives_a_level_with_more_than_the_list_holds(lib):
    """The OTHER cap.  SPRITE_MAX_VISIBLE used to be applied in FILE order, so
    a level whose nearest entity is listed last had it dropped however close it
    was.  The nearest here is the last record in the level."""
    # A block of entities in front of the player, all inside the radius, listed
    # FARTHEST FIRST so the nearest one is the last record in the file.
    eye_x, eye_y = 8, 8
    block = [(x, y) for x in range(eye_x + 1, eye_x + 11) for y in range(eye_y - 2, eye_y + 3)]
    block.sort(key=lambda cell: -(cell[0] - eye_x))
    assert len(block) > CONST["SPRITE_MAX_VISIBLE"], "the cap is not exercised"

    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], x, y) for x, y in block],
                               width=40, height=16)
    state = state_at_full_width(lib, level)
    look_east(state, cell_x=eye_x, cell_y=eye_y)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    assert sprites.count >= 1
    nearest = min(sprites.entries[i].dist for i in range(sprites.count))
    assert nearest == CELL, \
        "the nearest entity was dropped because it was last in the file (kept %d)" % nearest


def test_a_sprite_exactly_as_far_as_the_wall_is_hidden(lib):
    """The depth test is `>=`, not `>`.  At exact equality the wall wins, and
    that is not arbitrary: a billboard standing IN a wall's plane must not be
    drawn over it, and equality is what a sprite in a doorway produces."""
    width = height = 16
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (8, 8))
    level.entity_count = 1
    level.entities[0].type = CONST["ENT_WATCHDOG"]
    level.entities[0].cell_x, level.entities[0].cell_y = 12, 8
    state = state_at_full_width(lib, level)
    look_east(state)

    sprites = blackice.SpriteList()
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    assert sprites.count == 1
    distance = sprites.entries[0].dist

    chunky = blackice.chunky_buffer()
    walls = (ctypes.c_uint16 * blackice.RENDER_W_MAX)()
    columns = COLUMNS_HIGH

    # A wall at exactly the sprite's distance hides it...
    for c in range(columns):
        walls[c] = distance
    lib.render_clear(chunky, columns)
    lib.sprite_draw(ctypes.byref(sprites), walls, columns, chunky)
    assert set(chunky.raw[:columns * blackice.RENDER_H]) == {CONST["COLOUR_VOID"]}, \
        "a sprite at exactly the wall distance was drawn"

    # ...and one unit further away does not.
    for c in range(columns):
        walls[c] = distance + 1
    lib.render_clear(chunky, columns)
    lib.sprite_draw(ctypes.byref(sprites), walls, columns, chunky)
    assert set(chunky.raw[:columns * blackice.RENDER_H]) != {CONST["COLOUR_VOID"]}, \
        "a sprite nearer than the wall was not drawn"


def test_a_sub_cell_step_toward_the_wall_hides_the_sprite(lib):
    """Depth is carried in map units, not cells, so the test must bite at
    sub-cell resolution.  A two-cell bias would pass everything above."""
    width = height = 16
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (8, 8))
    level.entity_count = 1
    level.entities[0].type = CONST["ENT_WATCHDOG"]
    level.entities[0].cell_x, level.entities[0].cell_y = 12, 8
    state = state_at_full_width(lib, level)
    look_east(state)

    sprites = blackice.SpriteList()
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    distance = sprites.entries[0].dist
    chunky = blackice.chunky_buffer()
    walls = (ctypes.c_uint16 * blackice.RENDER_W_MAX)()
    columns = COLUMNS_HIGH

    def drawn(wall_distance):
        for c in range(columns):
            walls[c] = wall_distance
        lib.render_clear(chunky, columns)
        lib.sprite_draw(ctypes.byref(sprites), walls, columns, chunky)
        return set(chunky.raw[:columns * blackice.RENDER_H]) != {CONST["COLOUR_VOID"]}

    quarter_cell = CELL // 4
    assert drawn(distance + quarter_cell), "a quarter cell of clearance was not enough"
    assert not drawn(distance - quarter_cell), "a quarter cell of occlusion was ignored"
