"""The image-layout constants of the reconstruction's headers, read from those headers.

Python cannot include a C header, and the tests below need the same numbers the reconstruction
will. CLAUDE.md §5's rule is to keep ONE canonical definition and pin the other side to it, so
nothing here restates a value: the headers are canonical and this module scrapes them. A constant
renamed or retyped there fails as a missing key naming the constant, rather than drifting quietly.

``include/wonderboy.h`` carries the image's own layout; ``include/blit.h`` carries the sprite
blitters' geometry, which is theirs alone; ``include/effects.h`` carries the one HUD-slot byte that
is a module's own rather than the image's; ``include/scene.h`` carries the three EXIT CODES the
scene tier returns in place of the transfers it declines to follow, ``include/actor.h`` the two
`actor_defeat_and_score` returns for the same reason, and ``include/behavior.h`` the two
`actor_dispatch_behavior` returns that stand in for a dispatch this port cannot follow,
``include/player.h`` the three `player_run_map_cell` reports (two of which stand in for a busy-wait
and a stack unwind), and
``include/hud.h`` the two entry-X claims a packed-BCD call site can make — all C-only.
All eight are scraped into ONE namespace — every name is
already prefixed (WB_BLIT_*), and a name defined in two of them is raised on rather than resolved,
for the same reason a name defined twice in one header is. That shared namespace is what lets a
case PIN two headers' spellings of the same byte against each other (test_effects.py's
`test_the_two_headers_spell_one_slot_byte`), which is the substitute for a `#define` that cannot
derive from another one — the scraper reads plain literals only.
"""
import re
from pathlib import Path

_INCLUDE = Path(__file__).resolve().parents[1] / "include"
_HEADER = _INCLUDE / "wonderboy.h"
_HEADERS = (_HEADER, _INCLUDE / "blit.h", _INCLUDE / "effects.h", _INCLUDE / "scene.h",
            _INCLUDE / "actor.h", _INCLUDE / "behavior.h", _INCLUDE / "player.h",
            _INCLUDE / "hud.h")

# `#define WB_NAME 0x1234u` / `#define WB_NAME 3u` — a plain integer literal and nothing else. The
# trailing lookahead makes the literal the WHOLE definition, so a compound expression is skipped
# rather than half-read into a plausible wrong number.
_DEFINE_RE = re.compile(r"^#define\s+(WB_\w+)\s+(0[xX][0-9a-fA-F]+|\d+)[uU]?(?=\s*(?:/[/*]|$))",
                        re.M)


def _scrape(text, header=_HEADER, defines=None):
    """``{name: value}`` for every plain-integer ``WB_`` #define in ``text``.

    Both failure modes are raised, naming the header, rather than resolved by a rule: this module
    exists so that Python and C cannot disagree about a constant, and a scraper that quietly picks
    one of two readings is the thing it is meant to prevent.

    ``defines`` is an accumulator: passing the dict a previous header filled is what makes the
    duplicate check span the headers rather than run inside each of them, so a name defined in two
    of them is refused as loudly as one defined twice in one.
    """
    defines = {} if defines is None else defines
    for name, value in _DEFINE_RE.findall(text):
        if name in defines:
            raise ValueError(
                f"{header}: {name} is #defined more than once ({defines[name]:#x} and {value}) — "
                f"the scraper would silently take the last, so which one is canonical would depend "
                f"on file order. Delete the duplicate.")
        try:
            defines[name] = int(value, 0)
        except ValueError:
            raise ValueError(
                f"{header}: {name} = {value} is a decimal with a leading zero, which C reads as "
                f"OCTAL and Python refuses outright — the two languages would not agree on its "
                f"value. Write it as a plain decimal or a 0x literal.") from None
    return defines


DEFINES = {}
for _each in _HEADERS:
    _scrape(_each.read_text(), _each, DEFINES)


def wb(name):
    """The value of ``#define WB_<name>`` in one of the scraped headers."""
    key = f"WB_{name}"
    assert key in DEFINES, (
        f"{key} is not a plain-integer #define in {[str(h) for h in _HEADERS]}")
    return DEFINES[key]
