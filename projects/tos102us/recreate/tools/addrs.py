"""The Python view of ``include/addrs.h`` — parsed, never re-typed.

Every ROM address, system variable and constant this recreate names is defined once, in the C
header the reconstruction itself includes. This module reads the `#define`s straight out of it and
binds them as module attributes, so a case and the core it proves cannot disagree about an address:

    import addrs
    addrs.XBIOS_RANDOM      # 0xfc1510
    addrs.SYSVAR_HZ_200     # 0x4ba

Only simple integer defines are taken (decimal or `0x`, with an optional `u` suffix) and ALIASES of
one already defined above it — `#define TRAP_EXCEPTION_FRAME_BYTES EXCEPTION_FRAME_BYTES`, which is
how the header says "the same value under a second name" without spelling the number twice for one
of the two to be corrected alone. Anything else — a macro with arguments, a string, an expression —
is skipped rather than guessed at, because a half-understood value bound under a familiar name is
worse than a missing one.
"""
import re
import sys
from pathlib import Path

HEADER = Path(__file__).resolve().parents[1] / "include" / "addrs.h"

# `#define NAME <integer>`, or `#define NAME <ANOTHER NAME THE HEADER DEFINES>`, and nothing else:
# the name, then a decimal or hex literal with an optional unsigned suffix, or a bare identifier,
# then end-of-value (a comment may follow).
_DEFINE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
                     r"((?:0[xX][0-9a-fA-F]+|\d+)[uUlL]*|[A-Za-z_][A-Za-z0-9_]*)\s*(?:/\*.*)?$")


def parse(header=HEADER):
    """``{name: value}`` for every plain integer `#define` in ``header``, aliases resolved.

    Aliases are resolved AFTER the whole file is read, not as they are met, so the header may put
    the two names in whichever sections they belong to rather than in parse order. One that names
    something this parser does not bind — a macro with arguments, an expression — is dropped rather
    than raised on: those are defines it deliberately does not read, and a name bound to a
    half-understood value is worse than a missing one.
    """
    values, aliases = {}, {}
    for line in Path(header).read_text().splitlines():
        match = _DEFINE.match(line)
        if not match:
            continue
        name, value = match.group(1), match.group(2)
        if value[0].isdigit():
            values[name] = int(value.rstrip("uUlL"), 0)
        else:
            aliases[name] = value
    for name, target in aliases.items():
        if target in values:
            values[name] = values[target]
    if not values:
        raise RuntimeError(f"{header} defined no integer constants — the parser and the header have "
                           f"drifted apart, and every address below would be missing rather than "
                           f"wrong, which is harder to notice")
    return values


ADDRS = parse()
# Bound as module attributes so a reader writes `addrs.XBIOS_RANDOM` rather than a dict lookup, and
# a typo is an AttributeError naming the constant instead of a KeyError naming a string.
sys.modules[__name__].__dict__.update(ADDRS)


if __name__ == "__main__":
    # `NAME=0x...` for each constant named on the command line — the CONTENT STAMP the makefile's
    # snapshot rule depends on. `tools/boot_snapshot.py` reads exactly two of this header's nine
    # hundred `#define`s, so a prerequisite on the whole file re-captures 15 s of real emulation for
    # an edit to a constant the capture never looks at (and, with two agents' `make`s running, makes
    # them race on the capture). A name the header does not define is an error rather than a blank.
    for _name in sys.argv[1:]:
        print(f"{_name}={ADDRS[_name]:#x}")
