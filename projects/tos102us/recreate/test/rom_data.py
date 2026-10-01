"""ROM ADDRESSES USED AS VALUES — the census every component's sources are held to (`test_vdi_rom_data.py`,
`test_aes_rom_data.py`), and the reader of the ROM's own text the AES's is held to as well.

The reconstruction runs with the image based at 0, so `image + VDI_MAP_COL` reads the ROM's own table at its 1987
address and `wr32(... USER_BUT, VDI_ROM_USER_VECTOR_DEFAULT)` stores a 1987 code address. Both are right against this
ROM and both are OBLIGATIONS on a rebuilt one, which links its own code and data where its linker puts them. So every
such use is listed in its component's census, by file, with its KIND — which is what says what the ROM build owes it
(`../README.md`, "What ships as the ROM's own instructions"):

* TABLE — a data table outside every transcribed region, read in place: the ROM build keeps it at this address (its
  data band), or relocates every reference listed;
* CODE — a routine's address as a value: stored in a RAM vector, compared with one (`require_cpu_routine`), handed on
  as a dispatcher's D0, or handed to a walker as the routine it calls. The ROM build must use the address the SHIPPED
  routine is linked at;
* REGION_TABLE — a table INSIDE a region a `.S` transcribes (a code region). The C that reads it is that region's own
  C core, which the ROM build does not link (`TRANSCRIBED_C_CORES`): harmless exactly while that stays true. A shipped
  C that read one would have to read the `.S`'s copy instead;
* DISTANCE — two ROM addresses subtracted, a distance inside one transcribed region, which relocation keeps;
* WAIT_SITE — a busy-wait's site, the scheduled-write model's key for counting the ROM's arrivals against the C's
  polls (`sched.h`). No obligation: the target's `sched.h` ignores it, since a machine has a PC;
* RETURN_SITE — the instruction after a ROM caller's call into a GEMDOS door, which the C hands or stores so RAM holds
  what the ROM's own call leaves there (each census says what its door does with it). No obligation on a rebuilt ROM
  but a value its RAM would hold differently: nothing the C runs jumps through it.

A census is EXACT both ways: a new use anywhere in a component's sources — or in the CODE of one of its headers, an
inline compiled into every file that calls it, keyed `<component>/<name>.h` — reds until it is listed with its kind,
and a listed use the sources no longer make reds too. `kind_mismatches` holds each TABLE / REGION_TABLE to the
byte-pinned regions (`transcription.every_pinned_region`).

THE ROM'S OWN TEXT (`text_operands`): every operand of the 68000 instructions in a span of the ROM that is a ROM
address — an immediate or an absolute address (`move.l #`, `pea`, `lea`, `cmp.l #` ...; a `jsr`/`jmp`/branch target
is a CALL, which a linker resolves, and is not one) — or a pc-relative DATA reference. The span is decoded as the
instructions it is: a linear sweep that steps a GEM Line-F word as the one word it is (`aes_map/linef_dis.py`), and
re-decodes from the next address wherever objdump, reading one as an FPU instruction, ran past it.
"""
import functools
import re
import sys
from collections import namedtuple
from pathlib import Path

from harness import addrs

import transcription
import vdi

RECREATE = Path(__file__).resolve().parents[1]
INCLUDE = RECREATE / "include"
HEADERS = sorted(INCLUDE.glob("*.h")) + sorted(INCLUDE.glob("*/*.h"))
# The 68000's view of the ROM: 192 KB below the I/O page, which is where a VALUE is an obligation. The I/O page
# ($ff0000 up) is the machine's own address in any build.
ROM_LO, ROM_HI = 0xFC0000, 0xFF0000

TABLE, CODE, REGION_TABLE, DISTANCE, WAIT_SITE, RETURN_SITE = (
    "TABLE", "CODE", "REGION_TABLE", "DISTANCE", "WAIT_SITE", "RETURN_SITE")

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_TOKEN = re.compile(r"\b0[xX][0-9a-fA-F]+\b|\b[A-Za-z_]\w*\b")


# ---- the SOURCES' side ----------------------------------------------------------------------------------------------
class Component(namedtuple("Component", "sources headers")):
    """One component's census scope: every `*.c` / `*.S` in `sources`, and every `*.h` in `headers` — keyed by the
    header's path below `include/` (`vdi/attributes.h`). A battery proving the census itself hands a scratch pair."""

    def scanned(self):
        """`{key: path}`: every source by its name, and every header by its `<component>/<name>.h`."""
        sources = {source.name: source for source in sorted(self.sources.glob("*.[cS]"))}
        headers = {f"{self.headers.name}/{header.name}": header for header in sorted(self.headers.glob("*.h"))}
        return {**sources, **headers}


def component(name):
    """The census scope of `src/<name>` and `include/<name>`."""
    return Component(RECREATE / "src" / name, INCLUDE / name)


def _defines(path, known):
    """`path`'s `#define`s over `known` — `addrs.parse` refuses a file that has none, which a header of declarations
    or a source with no constants of its own is."""
    try:
        return {**known, **addrs.parse(path, known=known)}
    except RuntimeError:
        return known


@functools.cache
def _constants():
    known = dict(vdi.CONSTANTS)
    for header in HEADERS:
        known = _defines(header, known)
    return known


def constants_of(path):
    """Every constant `path` can name: the project's headers', then its own."""
    return _defines(path, _constants())


def _value(token, constants):
    return int(token, 16) if token[:2].lower() == "0x" else constants.get(token)


def _is_rom_address(token, constants):
    value = _value(token, constants)
    return isinstance(value, int) and ROM_LO <= value < ROM_HI


def census(scope):
    """`{file: {token}}`: every name or literal in a source's or header's CODE (comments and `#define` lines left out,
    which name an address rather than use it) whose value is a ROM address."""
    found = {}
    for key, path in scope.scanned().items():
        constants = constants_of(path)
        code = "\n".join(line for line in _COMMENT.sub(" ", path.read_text()).splitlines()
                         if not line.lstrip().startswith("#define"))
        uses = {token for token in _TOKEN.findall(code) if _is_rom_address(token, constants)}
        if uses:
            found[key] = uses
    return found


def listed(table):
    """A census table `{file: {name: kind}}` as `census` answers: `{file: {name}}`."""
    return {source: set(uses) for source, uses in table.items()}


def kind_mismatches(scope, table):
    """Every TABLE that lies inside a byte-pinned region and every REGION_TABLE that lies outside all of them."""
    regions, scanned, wrong = transcription.every_pinned_region(), scope.scanned(), []
    for source, uses in table.items():
        constants = constants_of(scanned[source])
        for name, kind in uses.items():
            if kind not in (TABLE, REGION_TABLE):
                continue
            inside = any(region.lo <= constants[name] < region.hi for region in regions)
            if inside != (kind == REGION_TABLE):
                wrong.append(f"{source}: {name} is a {kind}, but it lies {'inside' if inside else 'outside'} "
                             f"every pinned region")
    return wrong


# ---- the ROM TEXT's side --------------------------------------------------------------------------------------------
# `aes_map/linef_dis.py` is the one decoder of GEM's Line-F words and the one caller of objdump over the ROM.
sys.path.insert(0, str(RECREATE.parent / "aes_map"))
import linef_dis                                             # noqa: E402

ROM_IMAGE = linef_dis.ROM_IMAGE

Operand = namedtuple("Operand", "site value text pc_relative")
_CALL_OR_BRANCH = re.compile(r"(?:b(?:ra|sr|hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)[sw]?|db\w+|jsr|jmp)$")
_PC_RELATIVE = re.compile(r"%pc@\(0x([0-9a-f]+)")
_IMMEDIATE = re.compile(r"#(-?\d+)\b")
_ABSOLUTE = re.compile(r"(?<![\w(])0x([0-9a-f]+)\b")


@functools.cache
def instructions(lo, hi, rom=ROM_IMAGE):
    """`[(address, text)]`: [lo, hi) of the ROM image file `rom` as `linef_dis.sweep` decodes it (a Line-F word, CALL
    or RETURN, comes back as None). A byte no instruction decodes from is refused: a census over it would be silent."""
    found = [(address, text) for address, _length, text in linef_dis.sweep(lo, hi, rom)]
    undecoded = [hex(address) for address, text in found if text == linef_dis.UNDECODED]
    assert not undecoded, f"objdump decodes no instruction at {undecoded} in [{lo:#x}, {hi:#x})"
    return found


def text_operands(lo, hi, rom=ROM_IMAGE):
    """Every ROM address an instruction of [lo, hi) NAMES as a value (`Operand`s, in address order): an immediate or
    an absolute operand in [ROM_LO, ROM_HI), or a pc-relative operand that is not a call's or a branch's target."""
    operands = []
    for site, text in instructions(lo, hi, rom):
        if text is None or text.startswith("."):
            continue
        mnemonic, _, rest = text.partition(" ")
        if _CALL_OR_BRANCH.match(mnemonic):
            continue
        for target in _PC_RELATIVE.findall(rest):
            operands.append(Operand(site, int(target, 16), text, True))
        values = [int(value) for value in _IMMEDIATE.findall(rest)] + [int(value, 16) for value in _ABSOLUTE.findall(rest)]
        operands.extend(Operand(site, value, text, False) for value in values if ROM_LO <= value < ROM_HI)
    return operands
