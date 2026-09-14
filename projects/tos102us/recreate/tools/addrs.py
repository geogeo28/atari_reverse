"""The Python view of ``include/addrs.h`` — parsed, never re-typed.

Every ROM address, system variable and constant this recreate names is defined once, in the C
header the reconstruction itself includes. This module reads the `#define`s straight out of it and
binds them as module attributes, so a case and the core it proves cannot disagree about an address:

    import addrs
    addrs.XBIOS_RANDOM      # 0xfc1510
    addrs.SYSVAR_HZ_200     # 0x4ba

Only simple integer defines are taken (decimal or `0x`, with an optional `u` suffix); anything else
in the header — a macro with arguments, a string, an expression — is skipped rather than guessed at,
because a half-understood value bound under a familiar name is worse than a missing one.
"""
import re
import sys
from pathlib import Path

HEADER = Path(__file__).resolve().parents[1] / "include" / "addrs.h"

# `#define NAME <integer>` and nothing else: name, then a decimal or hex literal with an optional
# unsigned suffix, then end-of-value (a comment may follow).
_DEFINE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
                     r"(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\s*(?:/\*.*)?$")


def parse(header=HEADER):
    """``{name: value}`` for every plain integer `#define` in ``header``."""
    values = {}
    for line in Path(header).read_text().splitlines():
        match = _DEFINE.match(line)
        if match:
            values[match.group(1)] = int(match.group(2), 0)
    if not values:
        raise RuntimeError(f"{header} defined no integer constants — the parser and the header have "
                           f"drifted apart, and every address below would be missing rather than "
                           f"wrong, which is harder to notice")
    return values


ADDRS = parse()
# Bound as module attributes so a reader writes `addrs.XBIOS_RANDOM` rather than a dict lookup, and
# a typo is an AttributeError naming the constant instead of a KeyError naming a string.
sys.modules[__name__].__dict__.update(ADDRS)
