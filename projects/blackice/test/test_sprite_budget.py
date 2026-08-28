"""DESIGN 8.2's per-frame sprite-pixel budget: what a sprite costs, and which
one is exempt from paying.

test_sprites.py owns the projection.  This module owns the two rules the budget
is made of - the cost is counted after the window clip, and the nearest attacker
is drawn whatever the accumulator says - because both are decisions about the
SIMULATION's state (which body is in ATTACK) and not about pixels.
"""
import ctypes

import pytest

import aihelp
import blackice
from aihelp import CELL, glib     # noqa: F401 - the session fixture the tests take
from blackice import CONST

RENDER_H = CONST["RENDER_H"]
HEADER = "# name: BUDGET\n# start_facing: 256\n\n"      # brad 256 = east
EAST = 0


def build_list(glib, state):
    sprites = blackice.SpriteList()
    glib.sprite_build_list(aihelp.ref(state), ctypes.byref(sprites))
    return sprites


def kept_distances(sprites):
    return sorted(sprites.entries[i].dist for i in range(sprites.count))


def sprite_budget(glib, state):
    table = blackice.table(glib, "g_column_sets", blackice.ColumnSet,
                           CONST["DETAIL_LEVEL_COUNT"])
    return table[state.engine.detail_level].sprite_budget


def corridor(glib, dogs_at):
    """An east-west corridor with the player at the west end and a Watchdog at
    each named cell.  Wide enough that nothing is culled by the render radius."""
    width = 24
    row = ["#"] + ["."] * (width - 2) + ["#"]
    row[1] = "@"
    for x in dogs_at:
        row[x] = "w"
    rows = ["#" * width, "".join(row), "#" * width]
    return aihelp.level_from_rows(glib, rows, HEADER)


def aimed_state(glib, level):
    state = aihelp.new_state(glib, level)
    state.engine.player.angle = EAST
    return state


# ---------------------------------------------------------------------------
# the cost function
# ---------------------------------------------------------------------------

def bind_cost(glib):
    glib.sprite_pixel_cost.argtypes = [ctypes.POINTER(blackice.RenderSprite)]
    glib.sprite_pixel_cost.restype = ctypes.c_int32
    return glib.sprite_pixel_cost


@pytest.mark.parametrize("top,rows,cols,expected", [
    (0, 40, 10, 40 * 10),                       # wholly inside the window
    (-60, 200, 10, RENDER_H * 10),              # taller than the window, both ends
    (-20, 60, 10, 40 * 10),                     # clipped at the top only
    (RENDER_H - 10, 60, 10, 10 * 10),           # clipped at the bottom only
    (RENDER_H, 40, 10, 0),                      # wholly below the window
    (-40, 40, 10, 0),                           # wholly above it
])
def test_a_sprite_costs_the_pixels_it_would_actually_write(glib, top, rows, cols, expected):
    """DESIGN 8.2: "a sprite's contribution is the pixels it would actually
    write: AFTER clipping its projected rectangle to the 160x80 render window".

    At FOCAL_ROWS 115 a Watchdog at contact range projects 191 rows into an
    80-row window, so charging the unclipped height spends two and a half times
    what the frame draws - which is the difference between a budget that bounds
    the frame and one that only looks as though it does.
    """
    cost = bind_cost(glib)
    sprite = blackice.RenderSprite()
    sprite.top = top
    sprite.rows = rows
    sprite.cols = cols
    assert cost(ctypes.byref(sprite)) == expected


def test_the_projected_height_is_left_unclipped_for_the_drawer(glib):
    """The clip belongs to the cost function and nowhere else: sprite_draw maps
    a span's texel rows onto screen rows through `top` and `rows`, and clipping
    either of them in the list would squash the texture instead of cropping it."""
    level = corridor(glib, dogs_at=(2,))
    state = aimed_state(glib, level)
    sprites = build_list(glib, state)

    assert sprites.count == 1
    entry = sprites.entries[0]
    assert entry.rows > RENDER_H, "a dog one cell away should overflow the window"
    assert entry.top < 0, "and it should be centred, so it overflows both ends"
    assert bind_cost(glib)(ctypes.byref(entry)) == entry.cols * RENDER_H


# ---------------------------------------------------------------------------
# the exemption
# ---------------------------------------------------------------------------

def test_the_nearest_sprite_is_exempt_when_nothing_is_attacking(glib):
    """DESIGN 8.2: "the closest entity in ATTACK, or if none is attacking, the
    closest entity".  The near dog alone costs more than the whole budget, so
    without the exemption every sprite in the frame would be dropped."""
    level = corridor(glib, dogs_at=(2, 12))
    state = aimed_state(glib, level)
    sprites = build_list(glib, state)

    near = min(kept_distances(sprites))
    assert near == CELL, "the nearest dog is one cell away"
    entry = [sprites.entries[i] for i in range(sprites.count)
             if sprites.entries[i].dist == near][0]
    assert bind_cost(glib)(ctypes.byref(entry)) > sprite_budget(glib, state), \
        "the near dog must cost more than the budget, or this proves nothing"
    assert sprites.count == 2, "the exempt sprite is charged nothing, so the far one fits"


def test_the_nearest_attacker_is_drawn_over_a_nearer_bystander(glib):
    """The rule that motivated DESIGN 8.2: the thing eating you is always drawn.

    The attacker is the FAR body here and a bystander stands one cell from the
    player, costing more than the whole budget by itself.  Distance alone would
    keep the bystander and drop the attacker; the exemption does the opposite,
    and the bystander is what vanishes - which is the documented failure mode.
    """
    level = corridor(glib, dogs_at=(2, 12))
    state = aimed_state(glib, level)
    attacker = aihelp.entity_index_at(level, 12, 1)
    far = state.game.entities[attacker].x - state.engine.player.x

    # With nothing attacking, the nearest body is the one that is kept.
    assert CELL in kept_distances(build_list(glib, state))

    state.game.entities[attacker].state = CONST["ENT_STATE_ATTACK"]
    kept = kept_distances(build_list(glib, state))
    assert kept == [far], \
        "the attacker must be drawn, and the bystander alone overspends the budget"


def test_an_attacker_outranks_a_nearer_body_for_the_exemption(glib):
    """Only ONE sprite is exempt.  With an attacker in the frame it is the
    attacker, so a nearer bystander that busts the budget is what gets dropped -
    the opposite of the answer distance alone would give."""
    level = corridor(glib, dogs_at=(2, 6, 12))
    state = aimed_state(glib, level)
    attacker = aihelp.entity_index_at(level, 12, 1)
    state.game.entities[attacker].state = CONST["ENT_STATE_ATTACK"]

    sprites = build_list(glib, state)
    far = state.game.entities[attacker].x - state.engine.player.x
    assert far in kept_distances(sprites), "the attacking dog must always be drawn"

    # Without an attacker the same scene keeps the nearest instead.
    state.game.entities[attacker].state = CONST["ENT_STATE_IDLE"]
    plain = build_list(glib, state)
    assert min(kept_distances(plain)) == CELL


def test_the_farthest_sprites_are_the_ones_that_vanish(glib):
    """DESIGN 8.2: "the rest are dropped farthest-first".  Whatever survives, no
    dropped sprite may be nearer than a kept one."""
    level = corridor(glib, dogs_at=(4, 6, 8, 10, 12, 14, 16, 18))
    state = aimed_state(glib, level)
    sprites = build_list(glib, state)

    kept = kept_distances(sprites)
    assert kept, "the frame drew nothing at all"
    all_distances = sorted(state.game.entities[i].x - state.engine.player.x
                           for i in range(level.entity_count))
    assert kept == all_distances[:len(kept)], "a nearer sprite was dropped for a farther one"


def test_the_budget_bounds_what_the_frame_draws(glib):
    """The whole point of the accumulator: DESIGN 8.2's bound is the exempt
    sprite - at most a window-filling 160x80 - PLUS the budget, and nothing in
    the list may push the total past it."""
    level = corridor(glib, dogs_at=(3, 5, 7, 9, 11, 13, 15, 17, 19))
    state = aimed_state(glib, level)
    sprites = build_list(glib, state)
    cost = bind_cost(glib)

    costs = sorted(cost(ctypes.byref(sprites.entries[i])) for i in range(sprites.count))
    budget = sprite_budget(glib, state)
    window = CONST["RENDER_W_MAX"] * RENDER_H
    assert sum(costs[:-1]) <= budget, "the non-exempt sprites overspent the budget"
    assert costs[-1] <= window, "the exempt sprite is itself window-clipped"
    assert sum(costs) <= window + budget, "DESIGN 8.2's worst case"
