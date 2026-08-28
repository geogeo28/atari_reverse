"""The level compiler and the level loader must agree exactly.  They are two
separate implementations of one table, in two languages, and a divergence shows
up as a wrong wall - the hardest kind of bug to trace back to its cause."""
import ctypes
import importlib.util
import pathlib
import re

import pytest

import blackice
from blackice import CONST

TOOLS = blackice.ROOT / "tools"
LEVELS = blackice.ROOT / "levels"


def _load_mklevel():
    spec = importlib.util.spec_from_file_location("mklevel", TOOLS / "mklevel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mklevel = _load_mklevel()

_C_LEGEND_ROW = re.compile(
    r"\{\s*'(?P<glyph>\\?.)',\s*(?P<cell>[A-Z_0-9]+),\s*(?P<entity>[A-Z_0-9]+),\s*(?P<start>\d)\s*\}")


def _c_legend():
    """Read the legend table straight out of src/level.c."""
    source = (blackice.ROOT / "src" / "level.c").read_text()
    table = source[source.index("static const LegendEntry LEGEND[]"):]
    table = table[:table.index("};")]
    entity_values = {"ENT_" + name: value for name, value in mklevel.ENT.items()}
    out = {}
    for match in _C_LEGEND_ROW.finditer(table):
        glyph = match.group("glyph").replace("\\", "")
        cell = CONST.get(match.group("cell"), None)
        if match.group("cell") == "CELL_EMPTY":
            cell = 0
        entity = 0 if match.group("entity") == "ENT_NONE" else entity_values[match.group("entity")]
        out[glyph] = (cell, entity, match.group("start") == "1")
    return out


def test_compiler_and_loader_share_one_legend():
    c_legend = _c_legend()
    assert set(c_legend) == set(mklevel.LEGEND)
    for glyph, entry in mklevel.LEGEND.items():
        assert c_legend[glyph] == entry, "glyph %r disagrees" % glyph


ALL_LEVELS = sorted(path.stem for path in LEVELS.glob("*.txt"))


@pytest.mark.parametrize("name", ALL_LEVELS)
def test_text_and_blob_describe_the_same_level(lib, name):
    text = (LEVELS / f"{name}.txt").read_text()
    blob = mklevel.compile_level(text)

    from_text = blackice.parse_level(lib, text)
    from_blob = blackice.Level()
    assert lib.level_load_blob(blob, len(blob), ctypes.byref(from_blob)) == 0

    assert (from_text.width, from_text.height) == (from_blob.width, from_blob.height)
    assert (from_text.start_cell_x, from_text.start_cell_y) == \
           (from_blob.start_cell_x, from_blob.start_cell_y)
    assert from_text.entity_count == from_blob.entity_count
    cells = from_text.width * from_text.height
    assert bytes(from_text.cells[:cells]) == bytes(from_blob.cells[:cells])
    for i in range(from_text.entity_count):
        a, b = from_text.entities[i], from_blob.entities[i]
        assert (a.type, a.cell_x, a.cell_y) == (b.type, b.cell_x, b.cell_y)


@pytest.mark.parametrize("name", ALL_LEVELS)
def test_the_loader_round_trips_its_own_blob(lib, name):
    level = blackice.parse_level(lib, (LEVELS / f"{name}.txt").read_text())
    buffer = ctypes.create_string_buffer(64 * 1024)
    written = lib.level_write_blob(ctypes.byref(level), buffer, len(buffer))
    assert written > 0

    again = blackice.Level()
    assert lib.level_load_blob(buffer, written, ctypes.byref(again)) == 0
    cells = level.width * level.height
    assert bytes(again.cells[:cells]) == bytes(level.cells[:cells])
    assert written == len(mklevel.compile_level((LEVELS / f"{name}.txt").read_text()))


@pytest.mark.parametrize("name", ALL_LEVELS)
def test_shipped_levels_have_a_sealed_border(lib, name):
    """The DDA has no bounds test in its inner loop; the border is what makes
    that safe, so it is checked on the shipped data, not only in the compiler."""
    level = blackice.parse_level(lib, (LEVELS / f"{name}.txt").read_text())
    width, height = level.width, level.height
    for x in range(width):
        for y in (0, height - 1):
            assert 1 <= level.cells[y * width + x] <= CONST["CELL_WALL_MAX"]
    for y in range(height):
        for x in (0, width - 1):
            assert 1 <= level.cells[y * width + x] <= CONST["CELL_WALL_MAX"]


BAD_HEADER = "# name: BAD\n# facing: 0\n\n"


@pytest.mark.parametrize("body,expected", [
    ("####\n#..#\n#..#\n####\n", CONST["LEVEL_ERR_NO_START"]),          # no '@'
    ("####\n#@.#\n#..#\n#..#\n#.##\n", CONST["LEVEL_ERR_BORDER"]),      # open corner
    ("####\n#@.#\n#..\n####\n", CONST["LEVEL_ERR_ROW_WIDTH"]),          # ragged
    ("####\n#@Z#\n####\n", CONST["LEVEL_ERR_LEGEND"]),                  # unknown glyph
    ("####\n#@@#\n####\n", CONST["LEVEL_ERR_NO_START"]),                # two starts
])
def test_the_loader_refuses_broken_maps(lib, body, expected):
    level = blackice.Level()
    text = (BAD_HEADER + body).encode("ascii")
    assert lib.level_parse_text(text, len(text), ctypes.byref(level)) == expected


def test_the_compiler_refuses_an_unsealed_border():
    with pytest.raises(mklevel.LevelError):
        mklevel.compile_level(BAD_HEADER + "####\n#@.#\n#..#\n#.##\n#..#\n")


def test_the_compiler_refuses_an_unreachable_exit():
    with pytest.raises(mklevel.LevelError):
        mklevel.compile_level(BAD_HEADER + "#####\n#@#>#\n#####\n")


@pytest.mark.parametrize("name", ALL_LEVELS)
def test_authored_headers_survive_the_loader(lib, name):
    """Authored files spell some keys the long way (palette_variant,
    start_facing).  An ignored key is invisible - the level just renders in the
    wrong palette facing the wrong way - so both spellings are pinned here."""
    text = (LEVELS / f"{name}.txt").read_text()
    header = dict(re.findall(r"^# (\w+):\s*(.+)$", text, re.M))
    level = blackice.parse_level(lib, text)

    for key in ("palette", "palette_variant"):
        if key in header:
            assert level.palette_variant == int(header[key])
    for key in ("facing", "start_facing"):
        if key in header:
            assert level.start_facing_brads == int(header[key]) % CONST["BRADS_PER_TURN"]
    if "start_x" in header:
        assert (level.start_cell_x, level.start_cell_y) == \
               (int(header["start_x"]), int(header["start_y"]))


def test_the_compiler_refuses_a_header_that_contradicts_its_map():
    """A restated width or start that has drifted from the grid is a compile
    error, not a line the loader quietly drops."""
    source = "# name: DRIFT\n# start_x: 9\n# start_y: 1\n\n####\n#@.#\n####\n"
    with pytest.raises(mklevel.LevelError):
        mklevel.compile_level(source)
