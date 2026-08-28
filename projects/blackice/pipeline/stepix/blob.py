"""Helpers every blob writer needs: fixed-width name fields and C byte-array emission.

Both jobs were duplicated once per format (.PAK, .TEX, .SPR) and drifted: only one of the
three name fields validated its length, so a too-long name silently produced a directory
entry that ran into the next field. One implementation each, used by all three.
"""
from __future__ import annotations

C_BYTES_PER_LINE = 16           # one source line per 16 bytes: readable diffs


def fixed_name_field(name: str, width: int) -> bytes:
    """Upper-case ASCII `name`, NUL-padded to `width` bytes; too long is an error, not a trim.

    Truncating would silently alias two resources to the same on-disk name, and the engine
    looks members up by exactly these bytes.
    """
    encoded = name.upper().encode("ascii")
    if len(encoded) > width:
        raise ValueError(f"resource name {name!r} exceeds {width} bytes")
    return encoded.ljust(width, b"\0")


def c_byte_array(symbol: str, data: bytes, comment: str) -> str:
    """Emit `data` as a `static const unsigned char` array with a leading comment line."""
    lines = [f"/* {comment} */", f"static const unsigned char {symbol}[{len(data)}] = {{"]
    for start in range(0, len(data), C_BYTES_PER_LINE):
        chunk = data[start:start + C_BYTES_PER_LINE]
        lines.append("    " + ",".join(f"0x{b:02x}" for b in chunk) + ("," if start + C_BYTES_PER_LINE < len(data) else ""))
    lines.append("};")
    return "\n".join(lines) + "\n"
