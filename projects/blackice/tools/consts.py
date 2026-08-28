"""Read the engine's constants out of include/*.h.

Every tool and every test that needs one of the engine's numbers reads it from
here rather than restating it.  A restated constant is invisible when it drifts:
the tool keeps compiling, the test keeps passing, and the level or the asset it
produced is simply wrong.

    from consts import CONST
    tex_dim = CONST["TEX_DIM"]
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
INCLUDE = ROOT / "include"

_INT_DEFINE = re.compile(r"^#define[ \t]+([A-Z][A-Z0-9_]*)[ \t]+(.+)$", re.M)
_ENUM_BLOCK = re.compile(r"typedef enum\s*\{(.*?)\}", re.S)
_ENUM_ENTRY = re.compile(r"([A-Z][A-Z0-9_]*)\s*(?:=\s*(-?\d+))?\s*(?:,|$)", re.M)

#: The headers whose constants the tools and the suite share.
DEFAULT_HEADERS = ("fixed.h", "game_consts.h", "game_rules.h", "map.h", "level.h",
                   "render.h", "sprite.h", "player.h", "rng.h", "hash.h")

#: Passes over the pending list; a #define built from three earlier ones needs
#: three, and four leaves room without turning a typo into a long loop.
_RESOLUTION_PASSES = 4


def parse_defines(paths):
    """Evaluate the integer #defines of some headers, including ones built from
    earlier defines.  Anything that will not evaluate to an int is skipped."""
    values = {}
    pending = []
    for path in paths:
        for name, body in _INT_DEFINE.findall(pathlib.Path(path).read_text()):
            body = re.sub(r"/\*.*", "", body).strip()
            if not body:
                continue
            pending.append((name, body))
    for _ in range(_RESOLUTION_PASSES):
        unresolved = []
        for name, body in pending:
            # Strip C integer suffixes and casts, never letters inside a name.
            expression = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", body)
            expression = re.sub(r"\((?:int|uint)\d+_t\)", "", expression)
            # A character literal is an integer in C; the .bil magic bytes are
            # spelled that way so the loader can compare without a string.
            expression = re.sub(r"'([^\\'])'", lambda m: str(ord(m.group(1))), expression)
            try:
                values[name] = int(eval(expression, {"__builtins__": {}}, dict(values)))
            except Exception:
                unresolved.append((name, body))
        pending = unresolved
        if not pending:
            break
    return values


def parse_enums(paths):
    """C enumerators, with the implicit auto-increment C gives them."""
    values = {}
    for path in paths:
        for body in _ENUM_BLOCK.findall(pathlib.Path(path).read_text()):
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            counter = 0
            for name, explicit in _ENUM_ENTRY.findall(body):
                counter = int(explicit) if explicit else counter
                values[name] = counter
                counter += 1
    return values


def load(headers=DEFAULT_HEADERS):
    """Defines and enumerators of `headers`, in one dictionary."""
    paths = [INCLUDE / name for name in headers]
    values = parse_defines(paths)
    values.update(parse_enums(paths))
    return values


CONST = load()
