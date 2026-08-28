"""Resource container (.PAK) and an LZSS codec whose depacker fits a 68000 in a few dozen bytes.

WHY this codec and not something stronger: the depacker runs on an 8 MHz 68000 with a 1 MB
budget, so the design targets (a) no state beyond two address registers and a bit counter,
(b) no window buffer -- matches are copied from the already-written output, so the "window"
is the destination itself, and (c) byte-at-a-time copies, which are correct even when a match
overlaps its own output (the classic run-length trick: offset 1, length 18 fills 18 bytes
from one). Ratio matters less than depack speed and code size; a 720 KB floppy is the
constraint, not a modem.

Stream format (see README.md for the byte-exact table):
  control byte, bits consumed MSB first, 8 tokens per control byte
    bit = 1 -> one literal byte follows
    bit = 0 -> a 2-byte big-endian match token: ((len - 3) << 12) | (offset - 1)
               offset 1..4096 counts BACK from the current output position, len 3..18
  The stream ends when raw_len bytes have been produced; there is no end marker, because the
  PAK entry already carries raw_len and an in-band marker would cost a token per file.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .blob import fixed_name_field

WINDOW_SIZE = 4096              # 12-bit offset field
MIN_MATCH = 3                   # below this a match token costs more than the literals
MAX_MATCH = 18                  # 4-bit length field, biased by MIN_MATCH
LENGTH_SHIFT = 12               # match token layout: length in the top nibble
OFFSET_MASK = 0x0FFF
CONTROL_BITS = 8                # flags per control byte
CONTROL_MSB = 1 << (CONTROL_BITS - 1)
MATCH_TOKEN_BYTES = 2
MAX_CHAIN = 64                  # candidate positions examined per match: packer speed knob

PAK_MAGIC = b"STPK"
PAK_FORMAT_VERSION = 1
PAK_NAME_BYTES = 8
PAK_ENTRY_BYTES = 24            # name8 + offset4 + packed4 + raw4 + method2 + reserved2
PAK_HEADER_BYTES = 8            # magic4 + version2 + count2
PAK_ALIGNMENT = 2               # every payload starts word-aligned: the 68000 wants it

METHOD_STORED = 0               # payload is the raw bytes (incompressible data)
METHOD_LZSS = 1                 # payload is an LZSS stream as described above


def lz_pack(data: bytes) -> bytes:
    """Compress with greedy matching over a hash chain of 3-byte prefixes."""
    out = bytearray()
    control_index = -1
    control_bit = 0
    chains: dict[bytes, list[int]] = {}
    position = 0
    size = len(data)

    while position < size:
        if control_bit == 0:
            control_index = len(out)
            out.append(0)
            control_bit = CONTROL_MSB

        best_length, best_offset = _find_match(data, position, chains)
        if best_length >= MIN_MATCH:
            token = ((best_length - MIN_MATCH) << LENGTH_SHIFT) | (best_offset - 1)
            out += struct.pack(">H", token)
            consumed = best_length
        else:
            out[control_index] |= control_bit          # flag set = literal
            out.append(data[position])
            consumed = 1

        for step in range(consumed):
            _index_position(data, position + step, chains)
        position += consumed
        control_bit >>= 1
    return bytes(out)


def _index_position(data: bytes, position: int, chains: dict[bytes, list[int]]) -> None:
    """Record `position` under its 3-byte prefix so later matches can find it."""
    if position + MIN_MATCH <= len(data):
        chains.setdefault(data[position:position + MIN_MATCH], []).append(position)


def _find_match(data: bytes, position: int, chains: dict[bytes, list[int]]) -> tuple[int, int]:
    """Longest match for `data[position:]` within the window. Returns (length, offset)."""
    if position + MIN_MATCH > len(data):
        return 0, 0
    candidates = chains.get(data[position:position + MIN_MATCH])
    if not candidates:
        return 0, 0

    limit = min(MAX_MATCH, len(data) - position)
    best_length, best_offset = 0, 0
    for candidate in reversed(candidates[-MAX_CHAIN:]):
        offset = position - candidate
        if offset > WINDOW_SIZE:
            break                                       # candidates are ordered: older only gets worse
        length = MIN_MATCH
        while length < limit and data[candidate + length] == data[position + length]:
            length += 1
        if length > best_length:
            best_length, best_offset = length, offset
            if length == limit:
                break
    return best_length, best_offset


def lz_unpack(stream: bytes, raw_len: int) -> bytes:
    """Reference depacker; `depack.c` is the byte-for-byte C twin of this loop.

    The two twins must agree on malformed streams as well as good ones, so the policies are
    paired: a match that overshoots `raw_len` is CLAMPED to the room left (here by the final
    slice, in C by clamping the length), while a match reaching before the output start or a
    truncated stream is REJECTED (here a ValueError, in C STEPIX_DEPACK_BAD_STREAM).
    """
    out = bytearray()
    read = 0
    control = 0
    control_bit = 0

    def require(count: int) -> None:
        """Every read is bounds-checked: a truncated resource must fail loudly, not IndexError."""
        if read + count > len(stream):
            raise ValueError(f"stream truncated after {len(out)} of {raw_len} bytes")

    while len(out) < raw_len:
        if control_bit == 0:
            require(1)
            control = stream[read]
            read += 1
            control_bit = CONTROL_MSB

        if control & control_bit:
            require(1)
            out.append(stream[read])
            read += 1
        else:
            require(MATCH_TOKEN_BYTES)
            token = struct.unpack_from(">H", stream, read)[0]
            read += MATCH_TOKEN_BYTES
            length = (token >> LENGTH_SHIFT) + MIN_MATCH
            offset = (token & OFFSET_MASK) + 1
            if offset > len(out):
                raise ValueError(f"match offset {offset} reaches before the start of the output")
            for _ in range(length):                    # byte at a time: overlapping matches are legal
                out.append(out[-offset])
        control_bit >>= 1
    return bytes(out[:raw_len])


@dataclass(frozen=True)
class PakEntry:
    """One file in the archive, as described by the directory."""

    name: str
    offset: int
    packed_len: int
    raw_len: int
    method: int

    @property
    def ratio(self) -> float:
        """Packed size as a fraction of raw; 1.0 means stored."""
        return self.packed_len / self.raw_len if self.raw_len else 1.0


def _upper_cased_names(resources: dict[str, bytes]) -> dict[str, bytes]:
    """Fold every key to the on-disk (upper-case) name, rejecting a collision.

    Names are upper-cased on the way to disk, so {'font', 'FONT'} would otherwise write two
    entries called FONT: `read_pak` keeps the last, the engine finds the first. Folding here
    makes `read_pak(build_pak(x)) == x` hold for any upper-case-keyed `x`.
    """
    folded: dict[str, bytes] = {}
    for name, data in resources.items():
        on_disk = name.upper()
        if on_disk in folded:
            raise ValueError(f"resource name {name!r} collides with an earlier entry as {on_disk!r}")
        folded[on_disk] = data
    return folded


def build_pak(resources: dict[str, bytes], compress: bool = True) -> bytes:
    """Build a .PAK. Each member is stored raw when compression would not shrink it."""
    members = _upper_cased_names(resources)
    directory, payload = bytearray(), bytearray()
    data_start = PAK_HEADER_BYTES + PAK_ENTRY_BYTES * len(members)

    for name, raw in members.items():
        packed = lz_pack(raw) if compress else raw
        method = METHOD_LZSS if compress and len(packed) < len(raw) else METHOD_STORED
        if method == METHOD_STORED:
            packed = raw
        if len(payload) % PAK_ALIGNMENT:
            payload += b"\0" * (PAK_ALIGNMENT - len(payload) % PAK_ALIGNMENT)
        directory += fixed_name_field(name, PAK_NAME_BYTES) + struct.pack(">IIIHH", data_start + len(payload), len(packed), len(raw), method, 0)
        payload += packed

    header = struct.pack(">4sHH", PAK_MAGIC, PAK_FORMAT_VERSION, len(members))
    return header + bytes(directory) + bytes(payload)


def read_pak_directory(blob: bytes) -> list[PakEntry]:
    """Parse just the directory -- what the engine does before seeking to one member."""
    if len(blob) < PAK_HEADER_BYTES:
        raise ValueError("blob is shorter than a PAK header")
    magic, version, count = struct.unpack_from(">4sHH", blob, 0)
    if magic != PAK_MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {PAK_MAGIC!r}")
    if version != PAK_FORMAT_VERSION:
        raise ValueError(f"unsupported PAK version {version}")

    entries = []
    for position in range(count):
        fields = struct.unpack_from(f">{PAK_NAME_BYTES}sIIIHH", blob, PAK_HEADER_BYTES + position * PAK_ENTRY_BYTES)
        name_bytes, offset, packed_len, raw_len, method, _reserved = fields
        entries.append(PakEntry(name_bytes.rstrip(b"\0").decode("ascii"), offset, packed_len, raw_len, method))
    return entries


def extract(blob: bytes, entry: PakEntry) -> bytes:
    """Return one member's raw bytes, depacking if needed."""
    payload = blob[entry.offset:entry.offset + entry.packed_len]
    if len(payload) != entry.packed_len:
        raise ValueError(f"entry {entry.name!r} runs past the end of the archive")
    if entry.method == METHOD_STORED:
        return payload
    if entry.method == METHOD_LZSS:
        return lz_unpack(payload, entry.raw_len)
    raise ValueError(f"entry {entry.name!r} uses unknown method {entry.method}")


def read_pak(blob: bytes) -> dict[str, bytes]:
    """Whole-archive convenience: every member depacked, keyed by name."""
    return {entry.name: extract(blob, entry) for entry in read_pak_directory(blob)}
