"""What the level loader refuses about the ENTITY list.

test_level.py owns the header, the grid and the blob round trip.  This module
owns the rules that are about bodies rather than about cells, because they are
the ones the game layer's own code depends on: entities_init claims an entity's
cell, and sentry_facing_from_alcove walks the four neighbours of it, so a body
authored on a wall or a Sentry authored in the open are not cosmetic mistakes -
they are a claim inside a wall and a neighbour scan off the end of the grid.
"""
import ctypes

import pytest

import aihelp
import blackice
from aihelp import glib          # noqa: F401 - the session fixture the tests take
from blackice import CONST

LEVEL_OK = 0
LEVEL_ERR_ENTITY = CONST["LEVEL_ERR_ENTITY"]
ENTITY_BYTES = CONST["LEVEL_BLOB_ENTITY_BYTES"]
HEADER_BYTES = CONST["LEVEL_BLOB_HEADER_BYTES"]

HEADER = "# name: ENTITIES\n# start_facing: 0\n\n"


def parse(glib, rows):
    """Run the ASCII loader and hand back its result code, not a Level.

    blackice.parse_level asserts success, which is exactly what a test about
    refusals cannot use.
    """
    level = blackice.Level()
    text = (HEADER + "\n".join(rows) + "\n").encode("ascii")
    return glib.level_parse_text(text, len(text), ctypes.byref(level)), level


# ---------------------------------------------------------------------------
# the Sentry alcove (DESIGN 11 rule 5)
# ---------------------------------------------------------------------------

WELL_FORMED_ALCOVE = [
    "#######",
    "#.....#",
    "#..@..#",
    "###s###",
    "#######",
]

SENTRY_IN_THE_OPEN = [
    "#######",
    "#..s..#",
    "#..@..#",
    "#######",
]

SENTRY_IN_A_SEALED_POCKET = [
    "#######",
    "#.....#",
    "#..@..#",
    "#######",
    "###s###",       # four wall neighbours: it can never see anything
    "#######",
]

SENTRY_WITH_A_DOOR_FOR_A_WALL = [
    "#######",
    "#.....#",
    "#..@..#",
    "##+s###",       # a leaf that opens and shuts is not an alcove wall
    "#######",
]


def test_a_well_formed_alcove_loads(glib):
    result, level = parse(glib, WELL_FORMED_ALCOVE)
    assert result == LEVEL_OK
    assert level.entity_count == 1
    assert level.entities[0].type == CONST["ENT_SENTRY"]


@pytest.mark.parametrize("rows,why", [
    (SENTRY_IN_THE_OPEN, "one wall neighbour, not three"),
    (SENTRY_IN_A_SEALED_POCKET, "four wall neighbours, so no open side"),
    (SENTRY_WITH_A_DOOR_FOR_A_WALL, "a door is neither a wall nor an open side"),
])
def test_a_sentry_outside_a_three_wall_alcove_is_refused(glib, rows, why):
    """DESIGN 11 rule 5: "exactly three wall neighbours and one open
    neighbour".  DESIGN 8 then makes that shape the only authority on which way
    the turret looks, so a Sentry the shape does not describe has a facing
    decided by whichever neighbour the scan happened to reach first."""
    result, _level = parse(glib, rows)
    assert result == LEVEL_ERR_ENTITY, why


def test_the_shipped_levels_pass_the_entity_rules(glib):
    """Both maps author their Sentries into real alcoves, so the rule is one
    the shipped content already keeps and not a new constraint on it."""
    for name in ("level1", "level2", "level03", "level04",
                 "level05", "level06", "level07", "level08"):
        path = blackice.ROOT / "levels" / ("%s.bil" % name)
        blob = path.read_bytes()
        level = blackice.Level()
        assert glib.level_load_blob(blob, len(blob), ctypes.byref(level)) == LEVEL_OK, name


# ---------------------------------------------------------------------------
# an entity's cell, in the blob the ASCII legend cannot spell
# ---------------------------------------------------------------------------

def blob_of(glib, rows):
    _result, level = parse(glib, rows)
    buffer = ctypes.create_string_buffer(64 * 1024)
    written = glib.level_write_blob(ctypes.byref(level), buffer, len(buffer))
    assert written > 0
    return bytearray(buffer.raw[:written]), level


def load(glib, blob):
    level = blackice.Level()
    return glib.level_load_blob(bytes(blob), len(blob), ctypes.byref(level))


def patch_entity_cell(blob, level, index, x, y):
    at = HEADER_BYTES + level.width * level.height + index * ENTITY_BYTES
    blob[at + 1] = x
    blob[at + 2] = y


DOG_IN_A_ROOM = [
    "#######",
    "#.w...#",
    "#..@..#",
    "#######",
]


def test_a_blob_that_stands_a_body_on_a_wall_is_refused(glib):
    """No legend glyph can spell it - every entity glyph compiles its cell to 0
    - so this can only arrive from a corrupt or hand-edited file.  It has to be
    refused anyway: entities_init CLAIMS the cell, and a claim inside a wall is
    a body the mover will try to walk out of a cell nothing can enter."""
    blob, level = blob_of(glib, DOG_IN_A_ROOM)
    assert load(glib, blob) == LEVEL_OK

    patch_entity_cell(blob, level, 0, 0, 1)         # the west border wall
    assert load(glib, blob) == LEVEL_ERR_ENTITY


def test_a_blob_that_stands_a_body_in_a_door_is_refused(glib):
    """A door cell is not floor either: the leaf's blocking bit is the door
    table's to own, and a body claiming that cell makes the two disagree."""
    rows = ["#######",
            "#.w...#",
            "#..+..#",
            "#..@..#",
            "#######"]
    blob, level = blob_of(glib, rows)
    assert load(glib, blob) == LEVEL_OK

    patch_entity_cell(blob, level, 0, 3, 2)         # the plain gate
    assert load(glib, blob) == LEVEL_ERR_ENTITY


def test_a_blob_that_stands_a_body_off_the_grid_is_refused(glib):
    blob, level = blob_of(glib, DOG_IN_A_ROOM)
    patch_entity_cell(blob, level, 0, level.width, 1)
    assert load(glib, blob) == LEVEL_ERR_ENTITY

    blob, level = blob_of(glib, DOG_IN_A_ROOM)
    patch_entity_cell(blob, level, 0, 1, level.height)
    assert load(glib, blob) == LEVEL_ERR_ENTITY
