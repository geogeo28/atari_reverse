"""ctypes binding for the BLACK ICE engine core.

The suite drives the real C, not a Python re-implementation: that is the whole
point of a differential test.  Every struct mirrored here is asserted against
the compiler's own sizeof/offsetof through host/abi.c, so a layout change fails
a test instead of silently corrupting one.

Constants are parsed out of the headers rather than restated, so the headers
stay the single source of truth.
"""
import ctypes
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB_PATH = ROOT / "build" / "libblackice.so"
HOST_BIN = ROOT / "build" / "blackice_host"

sys.path.insert(0, str(ROOT / "tools"))
import consts                                   # noqa: E402

# The tools read the headers with the same parser, so a constant means one
# thing to the level compiler, the asset generator and the suite alike.
_parse_defines = consts.parse_defines
_parse_enums = consts.parse_enums
CONST = dict(consts.CONST)

MAP_MAX_CELLS = CONST["MAP_MAX_CELLS"]
MAP_BITMAP_BYTES = CONST["MAP_BITMAP_BYTES"]
DOOR_MAX_COUNT = CONST["DOOR_MAX_COUNT"]
LEVEL_MAX_ENTITIES = CONST["LEVEL_MAX_ENTITIES"]
LEVEL_NAME_LEN = CONST["LEVEL_NAME_LEN"]
RENDER_W_MAX = CONST["RENDER_W_MAX"]
RENDER_H = CONST["RENDER_H"]
CHUNKY_BYTES = RENDER_W_MAX * RENDER_H
SPRITE_MAX_VISIBLE = CONST["SPRITE_MAX_VISIBLE"]
TRIG_TABLE_SIZE = CONST["TRIG_TABLE_SIZE"]
DIST_TABLE_SIZE = CONST["DIST_TABLE_SIZE"]
CELL_UNITS = CONST["CELL_UNITS"]
TRIG_ONE = CONST["TRIG_ONE"]
TEX_DIM = CONST["TEX_DIM"]


class Player(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int16), ("y", ctypes.c_int16), ("angle", ctypes.c_uint16)]


class Rng(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint32)]


class MapBlocking(ctypes.Structure):
    _fields_ = [("solid", ctypes.c_uint8 * MAP_BITMAP_BYTES)]


class Door(ctypes.Structure):
    _fields_ = [("cell", ctypes.c_uint16),
                ("cell_x", ctypes.c_uint8), ("cell_y", ctypes.c_uint8),
                ("variant", ctypes.c_uint8), ("state", ctypes.c_uint8),
                ("timer", ctypes.c_uint16)]


class Entity(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint8), ("cell_x", ctypes.c_uint8),
                ("cell_y", ctypes.c_uint8), ("facing", ctypes.c_uint8),
                ("extra", ctypes.c_uint8)]


class Level(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * (LEVEL_NAME_LEN + 1)),
        ("width", ctypes.c_uint8), ("height", ctypes.c_uint8),
        ("sector_index", ctypes.c_uint8), ("palette_variant", ctypes.c_uint8),
        ("texture_set", ctypes.c_uint8),
        ("start_cell_x", ctypes.c_uint8), ("start_cell_y", ctypes.c_uint8),
        ("start_facing_brads", ctypes.c_uint16),
        ("rng_seed", ctypes.c_uint32),
        ("trace_base_rate", ctypes.c_uint16),
        ("trace_start", ctypes.c_uint8), ("trace_carry_cap", ctypes.c_uint8),
        ("par_ticks", ctypes.c_uint16), ("entity_count", ctypes.c_uint16),
        ("cells", ctypes.c_uint8 * MAP_MAX_CELLS),
        ("entities", Entity * LEVEL_MAX_ENTITIES),
    ]


# The game layer (src/entities.c, ai.c, ...) appends its own fields to
# GameState.  The engine tests never read them, but game_init WRITES them, so
# the mirror has to be at least as large as the real struct or the C runs off
# the end of the ctypes buffer.  The tail is opaque and deliberately generous;
# test_abi asserts it is big enough, and test/aihelp.py overlays the game
# layer's real types on it for the game-layer tests.
GAME_LAYER_TAIL_BYTES = 32 * 1024


class GameState(ctypes.Structure):
    """The ENGINE half of the C GameState, plus an opaque game-layer tail.

    game.h appends the game layer's fields after trace_milli and never
    interleaves them, so every named field here keeps the C offset.  test_abi
    pins that boundary against bi_offset_state_gamelayer().
    """

    _fields_ = [
        ("level", ctypes.c_void_p),
        ("player", Player),
        ("rng", Rng),
        ("blocking", MapBlocking),
        ("doors", Door * DOOR_MAX_COUNT),
        ("door_of_cell", ctypes.c_uint8 * MAP_MAX_CELLS),
        ("door_count", ctypes.c_uint16),
        ("tick", ctypes.c_uint32),
        ("prev_input", ctypes.c_uint16),
        ("throttle", ctypes.c_uint8),
        ("throttle_lock", ctypes.c_uint8),
        ("entity_alive", ctypes.c_uint8 * LEVEL_MAX_ENTITIES),
        ("trace_milli", ctypes.c_int32),
        ("detail_level", ctypes.c_uint8),
        ("pad_to_game_layer", ctypes.c_uint8),
        ("game_layer_tail", ctypes.c_uint8 * GAME_LAYER_TAIL_BYTES),
    ]


class RenderColumn(ctypes.Structure):
    _fields_ = [("tex_id", ctypes.c_uint8), ("tex_col", ctypes.c_uint8),
                ("top", ctypes.c_int16), ("rows", ctypes.c_uint16),
                ("tex_v", ctypes.c_uint16), ("tex_step", ctypes.c_uint16),
                ("band", ctypes.c_uint8), ("side", ctypes.c_uint8)]


class RenderSprite(ctypes.Structure):
    _fields_ = [("texels", ctypes.c_void_p), ("spans", ctypes.c_void_p),
                ("left", ctypes.c_int16), ("cols", ctypes.c_uint16),
                ("top", ctypes.c_int16), ("rows", ctypes.c_uint16),
                ("tex_u", ctypes.c_uint16), ("tex_step_u", ctypes.c_uint16),
                ("tex_step_v", ctypes.c_uint16), ("dist", ctypes.c_uint16),
                ("band", ctypes.c_uint8), ("pad", ctypes.c_uint8)]


class SpriteList(ctypes.Structure):
    _fields_ = [("entries", RenderSprite * SPRITE_MAX_VISIBLE),
                ("count", ctypes.c_uint16)]


class RenderScratch(ctypes.Structure):
    _fields_ = [("columns", RenderColumn * RENDER_W_MAX),
                ("wall_dist", ctypes.c_uint16 * RENDER_W_MAX),
                ("sprites", SpriteList)]


class ColumnSet(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint16), ("sprite_budget", ctypes.c_uint16),
                ("width_shift", ctypes.c_uint8),
                ("pad", ctypes.c_uint8), ("angle", ctypes.c_void_p),
                ("cosine", ctypes.c_void_p)]


class ThrottleMode(ctypes.Structure):
    _fields_ = [("radius_cells", ctypes.c_uint8), ("band_count", ctypes.c_uint8),
                ("speed_scale", ctypes.c_uint16), ("trace_scale", ctypes.c_uint16),
                ("band_limit", ctypes.c_uint16 * (CONST["BAND_COUNT"] - 1))]


def _build():
    subprocess.run(["make", "-s", "all"], cwd=ROOT, check=True)


def load():
    _build()
    lib = ctypes.CDLL(str(LIB_PATH))

    lib.level_parse_text.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(Level)]
    lib.level_parse_text.restype = ctypes.c_int
    lib.level_load_blob.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(Level)]
    lib.level_load_blob.restype = ctypes.c_int
    lib.level_write_blob.argtypes = [ctypes.POINTER(Level), ctypes.c_char_p, ctypes.c_size_t]
    lib.level_write_blob.restype = ctypes.c_size_t

    lib.tables_init.argtypes = []
    lib.game_init.argtypes = [ctypes.POINTER(GameState), ctypes.POINTER(Level), ctypes.c_uint32]
    lib.game_step.argtypes = [ctypes.POINTER(GameState), ctypes.c_uint16]
    lib.game_state_hash.argtypes = [ctypes.POINTER(GameState)]
    lib.game_state_hash.restype = ctypes.c_uint32
    lib.game_touch_door.argtypes = [ctypes.POINTER(GameState), ctypes.c_int32]
    lib.game_touch_door.restype = ctypes.c_int

    lib.render_cast.argtypes = [ctypes.POINTER(GameState), ctypes.POINTER(RenderScratch)]
    lib.render_frame.argtypes = [ctypes.POINTER(GameState), ctypes.POINTER(RenderScratch),
                                 ctypes.c_char_p]
    lib.render_clear.argtypes = [ctypes.c_char_p, ctypes.c_uint16]
    lib.render_draw_columns.argtypes = [ctypes.POINTER(RenderScratch), ctypes.c_uint16,
                                        ctypes.c_char_p]
    lib.sprite_build_list.argtypes = [ctypes.POINTER(GameState), ctypes.POINTER(SpriteList)]
    lib.sprite_draw.argtypes = [ctypes.POINTER(SpriteList), ctypes.POINTER(ctypes.c_uint16),
                                ctypes.c_uint16, ctypes.c_char_p]
    lib.c2p_window.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.c_char_p]
    lib.planar_pixel.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint16]
    lib.planar_pixel.restype = ctypes.c_uint8

    for name in ("bi_sizeof_level", "bi_sizeof_gamestate", "bi_sizeof_rendercolumn",
                 "bi_sizeof_renderscratch", "bi_sizeof_rendersprite", "bi_sizeof_spritelist",
                 "bi_sizeof_door", "bi_offset_state_player", "bi_offset_state_doors",
                 "bi_offset_state_trace", "bi_offset_state_gamelayer",
                 "bi_offset_scratch_dist",
                 "bi_offset_scratch_sprites", "bi_offset_level_cells"):
        getattr(lib, name).restype = ctypes.c_size_t
        getattr(lib, name).argtypes = []

    lib.tables_init()
    return lib


def table(lib, name, ctype, count):
    """Read one of the engine's const tables out of the shared library."""
    return (ctype * count).in_dll(lib, name)


def parse_level(lib, text):
    level = Level()
    data = text.encode("ascii")
    result = lib.level_parse_text(data, len(data), ctypes.byref(level))
    assert result == 0, "level_parse_text returned %d" % result
    return level


def new_state(lib, level, seed=0xACE1):
    state = GameState()
    lib.game_init(ctypes.byref(state), ctypes.byref(level), seed)
    return state


_SCRIPT_TOKEN = re.compile(r'\{\s*"(\w+)",\s*(INPUT_[A-Z0-9_]+)\s*\}')


def script_tokens():
    """The host's input-token table, read straight out of host/main_host.c.

    A second copy of this table in Python is a second thing to get wrong, and
    the way it goes wrong is silent: a token worth INPUT_BACK here and
    INPUT_FORWARD there gives two different runs that both pass.
    """
    source = (ROOT / "host" / "main_host.c").read_text()
    table = source[source.index("INPUT_TOKENS[]"):]
    table = table[:table.index("};")]
    return {name: CONST[macro] for name, macro in _SCRIPT_TOKEN.findall(table)}


def parse_script(text):
    """A replay script as one input word per tick, the way the host reads it.

    Same grammar as host/main_host.c's load_script: '#' comments, then
    `<ticks> <token>...` with '-' meaning no input.
    """
    tokens = script_tokens()
    script = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        word = 0
        for token in parts[1:]:
            if token != "-":
                word |= tokens[token]
        script += [word] * int(parts[0])
    return script


def chunky_buffer():
    return ctypes.create_string_buffer(CHUNKY_BYTES)


def chunky_pixel(buffer, x, y):
    return buffer.raw[x * RENDER_H + y]


# ---------------------------------------------------------------------------
# Hand-built levels.  Four test modules wanted the same three helpers, so they
# live here rather than being imported sideways out of whichever module
# happened to define one first.
# ---------------------------------------------------------------------------

CELL = CELL_UNITS
CENTRE = CELL // 2
#: The trace rate a hand-built level runs at.  Anything nonzero proves the
#: meter ticks; the shipped levels' own rate is in their headers.
TEST_TRACE_BASE_RATE = 400


def make_level(lib, width, height, cells, start_cell):
    """A Level built cell by cell, bypassing the ASCII compiler.

    The point of a hand-built level is a shape the legend cannot spell - a
    random pillar field, one door in one place - so it is filled in directly
    rather than round-tripped through text.
    """
    level = Level()
    level.width = width
    level.height = height
    level.entity_count = 0
    level.trace_base_rate = TEST_TRACE_BASE_RATE
    level.start_cell_x, level.start_cell_y = start_cell
    for i, value in enumerate(cells):
        level.cells[i] = value
    return level


def sealed_room(lib, width=8, height=8, extra_walls=(), start_cell=None, wall=1):
    """An empty room with a one-cell wall all the way round.

    The border is not decoration: the DDA has no bounds test in its inner loop,
    so every test level needs one or a stray ray walks out of the map.
    """
    cells = [wall if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    for x, y in extra_walls:
        cells[y * width + x] = wall
    return make_level(lib, width, height, cells,
                      start_cell or (width // 2, height // 2))


def place(state, cell_x, cell_y, angle, offset=(CENTRE, CENTRE)):
    """Put the player at a cell, with an optional sub-cell offset."""
    state.player.x = cell_x * CELL + offset[0]
    state.player.y = cell_y * CELL + offset[1]
    state.player.angle = angle


def wall_texture_slots(lib):
    """g_wall_textures as a list of ints: 0 where a slot has no art."""
    slots = (ctypes.c_void_p * (CONST["WALL_TEXTURE_MAX"] + 1)).in_dll(lib, "g_wall_textures")
    return [slot or 0 for slot in slots]
