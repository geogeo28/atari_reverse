#!/usr/bin/env python3
"""cdefines.py — the `#define` lines of a C header, as integers a Python driver can read.

EVERY DRIVER HERE READS ITS CONSTANTS OUT OF THE HEADER THE TARGET CODE IS COMPILED FROM, so a
number that matters on both sides of the machine has ONE definition. `romdefs.h` says how big the
ROM is; `prg/ledger.h` says where the ledger block sits and how wide a record is. A second copy in
Python is a second thing to keep right, and the day it drifts the driver reads the wrong offset and
reports a difference that is its own.

WHAT IT UNDERSTANDS, and it is deliberately narrow — three forms, which is every form the headers
here use:

    #define ROM_BYTES       0x30000        a plain integer literal, decimal or hex, optional L/U
    #define ROM_END         (ROM_BASE + ROM_BYTES)      a sum of two names already defined
    #define OS_RSV1         OS_START                    an alias of one

Anything else — an arithmetic expression, a cast, a string — is ABSENT from the result rather than
guessed at, so a caller asking for it gets a KeyError that names the macro instead of a plausible
wrong number. A trailing `/* ... */` comment is ignored on every form.
"""
import re
from pathlib import Path

# The three forms above. `L`/`U` suffixes are the C spelling of a long constant (`0xC0000L`), not
# part of the value.
_LITERAL = re.compile(r"^#define\s+(\w+)\s+(0x[0-9A-Fa-f]+|\d+)[LlUu]*\s*(?:/\*.*)?$")
_SUM = re.compile(r"^#define\s+(\w+)\s+\((\w+)\s*\+\s*(\w+)\)\s*(?:/\*.*)?$")
_ALIAS = re.compile(r"^#define\s+(\w+)\s+(\w+)\s*(?:/\*.*)?$")


def defines(header_path):
    """Every `#define` of `header_path` this module can evaluate, as {name: int}."""
    values = {}
    for line in Path(header_path).read_text().splitlines():
        line = line.strip()
        found = _LITERAL.match(line)
        if found:
            values[found.group(1)] = int(found.group(2), 0)
            continue
        found = _SUM.match(line)
        if found and found.group(2) in values and found.group(3) in values:
            values[found.group(1)] = values[found.group(2)] + values[found.group(3)]
            continue
        found = _ALIAS.match(line)
        if found and found.group(2) in values:
            values[found.group(1)] = values[found.group(2)]
    return values
