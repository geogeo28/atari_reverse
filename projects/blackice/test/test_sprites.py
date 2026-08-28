"""Billboard projection, the far-to-near sort, the depth test and the drop
budget.  Sprites are the one stage that can write over a wall it should be
behind, so the z test gets a case of its own rather than a soak."""
import ctypes

import blackice
from blackice import CONST
from test_raycast import make_level

CELL = blackice.CELL_UNITS
CENTRE = CELL // 2
COLUMNS_HIGH = CONST["RENDER_COLUMNS_HIGH"]


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


def look_east(state, cell_x=8, cell_y=8):
    state.player.x = cell_x * CELL + CENTRE
    state.player.y = cell_y * CELL + CENTRE
    state.player.angle = 0


def test_a_sprite_straight_ahead_lands_in_the_middle_column(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 8)])
    state = blackice.new_state(lib, level)
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
    state = blackice.new_state(lib, level)
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
    state = blackice.new_state(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))

    distances = [sprites.entries[i].dist for i in range(sprites.count)]
    assert distances == sorted(distances, reverse=True)


def test_sprites_behind_and_beyond_the_radius_are_culled(lib):
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 4, 8)], width=40, height=16)
    state = blackice.new_state(lib, level)
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
    state = blackice.new_state(lib, level)
    look_east(state)
    scratch = blackice.RenderScratch()
    chunky = blackice.chunky_buffer()

    lib.render_frame(ctypes.byref(state), ctypes.byref(scratch), chunky)
    hidden = bytes(chunky.raw)

    # Remove the wall and the same sprite must now paint over those columns.
    level.cells[8 * level.width + 10] = 0
    level.cells[7 * level.width + 10] = 0
    level.cells[9 * level.width + 10] = 0
    state = blackice.new_state(lib, level)
    look_east(state)
    lib.render_frame(ctypes.byref(state), ctypes.byref(scratch), chunky)

    assert bytes(chunky.raw) != hidden
    sprite_colours = {CONST["COLOUR_VOID"]}
    assert set(chunky.raw) - set(hidden) - sprite_colours, "the sprite never appeared"


def test_the_pixel_budget_drops_the_farthest_first(lib):
    """DESIGN 8.2: the budget is spent nearest-first, so the nearest sprite can
    never be dropped and the far ones are what vanish."""
    entities = [(CONST["ENT_WATCHDOG"], 9 + i, 8) for i in range(8)]
    level = room_with_entities(lib, entities, width=24, height=16)
    state = blackice.new_state(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    kept = [sprites.entries[i].dist for i in range(sprites.count)]

    assert sprites.count >= 1
    assert min(kept) == CELL, "the nearest sprite was dropped"
    budget = blackice.table(lib, "g_throttle_modes", blackice.ThrottleMode,
                            CONST["THROTTLE_MODE_COUNT"])[CONST["THROTTLE_NOMINAL"]].sprite_budget
    spent = sum(sprites.entries[i].cols * sprites.entries[i].rows for i in range(sprites.count))
    assert spent <= budget or sprites.count == 1


def test_eighty_column_mode_halves_the_sprite_width_but_not_its_height(lib):
    """The window is 80 rows in both modes; only the horizontal resolution
    changes, so a billboard must squash sideways and keep its height."""
    level = room_with_entities(lib, [(CONST["ENT_WATCHDOG"], 12, 8)])
    state = blackice.new_state(lib, level)
    look_east(state)
    sprites = blackice.SpriteList()

    state.throttle = CONST["THROTTLE_NOMINAL"]
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    high = (sprites.entries[0].cols, sprites.entries[0].rows, sprites.entries[0].tex_step_u)

    state.throttle = CONST["THROTTLE_UNDERCLOCK"]
    lib.sprite_build_list(ctypes.byref(state), ctypes.byref(sprites))
    low = (sprites.entries[0].cols, sprites.entries[0].rows, sprites.entries[0].tex_step_u)

    assert low[0] == high[0] // 2
    assert low[1] == high[1]
    assert low[2] == high[2] * 2
