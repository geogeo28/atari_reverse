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

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB_PATH = ROOT / "build" / "libblackice.so"
HOST_BIN = ROOT / "build" / "blackice_host"

_INT_DEFINE = re.compile(r"^#define[ \t]+([A-Z][A-Z0-9_]*)[ \t]+(.+)$", re.M)


def _parse_defines(paths):
    """Evaluate the integer #defines of a header, including ones built from
    earlier defines.  Anything that will not evaluate to an int is skipped."""
    values = {}
    pending = []
    for path in paths:
        for name, body in _INT_DEFINE.findall(path.read_text()):
            body = re.sub(r"/\*.*", "", body).strip()
            if not body:
                continue
            pending.append((name, body))
    for _ in range(4):                      # a few passes resolve the chains
        unresolved = []
        for name, body in pending:
            # Strip C integer suffixes and casts, never letters inside a name.
            expression = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", body)
            expression = re.sub(r"\((?:int|uint)\d+_t\)", "", expression)
            try:
                values[name] = int(eval(expression, {"__builtins__": {}}, dict(values)))
            except Exception:
                unresolved.append((name, body))
        pending = unresolved
        if not pending:
            break
    return values


_ENUM_BLOCK = re.compile(r"typedef enum\s*\{(.*?)\}", re.S)
_ENUM_ENTRY = re.compile(r"([A-Z][A-Z0-9_]*)\s*(?:=\s*(-?\d+))?\s*(?:,|$)", re.M)


def _parse_enums(paths):
    """C enumerators, with the implicit auto-increment C gives them."""
    values = {}
    for path in paths:
        for body in _ENUM_BLOCK.findall(path.read_text()):
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            counter = 0
            for name, explicit in _ENUM_ENTRY.findall(body):
                counter = int(explicit) if explicit else counter
                values[name] = counter
                counter += 1
    return values


CONST = _parse_defines([
    ROOT / "include" / "fixed.h",
    ROOT / "include" / "game_consts.h",
    ROOT / "include" / "map.h",
    ROOT / "include" / "level.h",
    ROOT / "include" / "render.h",
    ROOT / "include" / "sprite.h",
    ROOT / "include" / "player.h",
    ROOT / "include" / "rng.h",
])
CONST.update(_parse_enums([ROOT / "include" / "level.h"]))

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
    _fields_ = [("state", ctypes.c_uint16)]


class MapBlocking(ctypes.Structure):
    _fields_ = [("solid", ctypes.c_uint8 * MAP_BITMAP_BYTES)]


class Door(ctypes.Structure):
    _fields_ = [("cell", ctypes.c_uint16), ("variant", ctypes.c_uint8),
                ("state", ctypes.c_uint8), ("timer", ctypes.c_uint16)]


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
        ("trace_base_rate", ctypes.c_uint16),
        ("trace_start", ctypes.c_uint8), ("trace_carry_cap", ctypes.c_uint8),
        ("par_ticks", ctypes.c_uint16), ("entity_count", ctypes.c_uint16),
        ("cells", ctypes.c_uint8 * MAP_MAX_CELLS),
        ("entities", Entity * LEVEL_MAX_ENTITIES),
    ]


class GameState(ctypes.Structure):
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
    _fields_ = [("count", ctypes.c_uint16), ("width_shift", ctypes.c_uint8),
                ("pad", ctypes.c_uint8), ("angle", ctypes.c_void_p),
                ("cosine", ctypes.c_void_p)]


class ThrottleMode(ctypes.Structure):
    _fields_ = [("radius_cells", ctypes.c_uint8), ("band_count", ctypes.c_uint8),
                ("column_set", ctypes.c_uint8), ("pad", ctypes.c_uint8),
                ("speed_scale", ctypes.c_uint16), ("trace_scale", ctypes.c_uint16),
                ("sprite_budget", ctypes.c_uint16),
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
    lib.game_init.argtypes = [ctypes.POINTER(GameState), ctypes.POINTER(Level), ctypes.c_uint16]
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
                 "bi_offset_state_trace", "bi_offset_scratch_dist",
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


def chunky_buffer():
    return ctypes.create_string_buffer(CHUNKY_BYTES)


def chunky_pixel(buffer, x, y):
    return buffer.raw[x * RENDER_H + y]
