"""THE WIDTH-TAGGED LAYOUTS — one reader of a component's headers, whichever component (`test/vdi.py`, `test/aes.py`).

A component's headers spell its records as `#define`s whose comment opens with a WIDTH TAG (`vdi/linea.h`, "THE
WIDTH TAG"): `byte` / `word` / `long`, or an array `bytes[N]` / `words[N]` / `longs[N]` whose N is a literal or a
constant the headers define. A constant whose comment opens with anything else — a count, a mask, a ROM table — is
NOT a field. A battery stages and reads fields BY NAME at exactly that width, through a `Layouts` built over its
component's headers; this module is that reader, so the VDI and the AES cannot come to parse one convention two ways.

A record is a constant-name PREFIX, up to the first underscore (`LINEA_WRT_MODE` is LINEA's `WRT_MODE`, `OB_X` is
OB's `X`); a component names the prefixes it reads as records, and every other tagged define is left alone.
"""
import re
from collections import namedtuple

from harness import addrs

WORD_BYTES = 2
LONG_BYTES = 4

Field = namedtuple("Field", "at width count")       # count None: a scalar; otherwise an array of `width`s
WIDTHS = {"byte": 1, "word": WORD_BYTES, "long": LONG_BYTES}
_TAGGED = re.compile(r"^\s*#define\s+(?P<name>[A-Z][A-Z0-9_]*)\s+\S+\s*/\*\s*(?P<kind>byte|word|long)"
                     r"(?P<plural>s\[(?P<count>\w+)\])?(?=[\s:*])")


def parse_constants(headers, known=None):
    """Every plain integer `#define` of `headers`, parsed IN INCLUDE ORDER with what came before as `known` — a
    header may spell a field as an ALIAS of an earlier header's name (`linea.h` of the console's) rather than as a
    second number. `known` is another component's constants its headers include (the AES's, the VDI's): aliases of
    them resolve, and they are not answered."""
    constants = {}
    for header in headers:
        constants.update(addrs.parse(header, known={**addrs.ADDRS, **(known or {}), **constants}))
    return constants


def _refuse_nothing(_at, _size):
    return None


class Layouts:
    """The FIELDS of `records` in `headers` (`constants` their parsed values): `{record: {short name: Field}}`, and
    the doors a battery stages and reads them through. `require(at, size)` is the component's placement rule for a
    staged field (the VDI's: a poke into its window lies inside one claimed band); `where` names the convention in a
    refusal."""

    def __init__(self, headers, records, constants, *, require=_refuse_nothing, where="`vdi/linea.h`, THE WIDTH TAG"):
        self.records, self.require, self.where = tuple(records), require, where
        self.fields = {record: {} for record in self.records}
        for header in headers:
            for line in header.read_text().splitlines():
                match = _TAGGED.match(line)
                if not match:
                    continue
                record, _, short = match["name"].partition("_")
                if record not in self.fields:
                    continue
                count = match["count"]
                if count is not None:
                    count = int(count, 0) if count[0].isdigit() else constants[count]
                self.fields[record][short] = Field(constants[match["name"]], WIDTHS[match["kind"]], count)

    def field(self, record, name):
        """`record`'s field `name` (`"INTIN"` or `"LINEA_INTIN"` alike) — a KeyError naming it when the headers have
        no FIELD of that name, which includes every count, mask and ROM table they define."""
        short = name[len(record) + 1:] if name.startswith(record + "_") else name
        if short not in self.fields[record]:
            raise KeyError(f"{record}_{short} is not a {record} field the headers tag with a width "
                           f"({self.where}) — known: {', '.join(sorted(self.fields[record]))}")
        return self.fields[record][short]

    @staticmethod
    def encode(record, name, spec, value):
        """One field's bytes: a scalar in range for its width (a negative is its two's complement), or an array no
        longer than its count, given as `bytes` or as a sequence of elements."""
        def one(element):
            bits = 8 * spec.width
            if not -(1 << (bits - 1)) <= element < (1 << bits):
                raise ValueError(f"{record}_{name} is {spec.width} byte(s) wide; {element:#x} does not fit")
            return (element & ((1 << bits) - 1)).to_bytes(spec.width, "big")
        if spec.count is None:
            return one(value)
        data = bytes(value) if isinstance(value, (bytes, bytearray)) else b"".join(one(v) for v in value)
        if len(data) > spec.count * spec.width:
            raise ValueError(f"{record}_{name} holds {spec.count} x {spec.width} bytes; {len(data)} given")
        return data

    def pokes(self, record, base=0, **values):
        """Fields of `record` at `base`, by name — `pokes("WS", at, WRT_MODE=2)`. An absolute record's base is 0."""
        staged = {}
        for name, value in values.items():
            spec = self.field(record, name)
            staged[base + spec.at] = self.encode(record, name, spec, value)
        for at, data in staged.items():
            self.require(at, len(data))
        return staged

    def read(self, image, record, name, base=0):
        """A field back out of `image`: an int, or a list of elements for an array."""
        spec = self.field(record, name)
        at = base + spec.at
        count = spec.count or 1
        elements = [int.from_bytes(bytes(image[at + i * spec.width:at + (i + 1) * spec.width]), "big")
                    for i in range(count)]
        return elements if spec.count else elements[0]
