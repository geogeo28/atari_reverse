"""Disassemble a range of the TOS 1.02 ROM with GEM's Line-F words decoded.

GEM (the AES and the desktop, 0xFD9ECA..0xFEE8FF) calls its own routines with ONE $Fxxx word: an even
word is a call through the table at 0xFEE900 (index = word & 0xFFF), an odd word is a return whose
register mask is (word & 0xFFE) << 2 (see AES_MAP.md §1.3). A plain objdump — and Ghidra's decomp.c —
decode those words as 68851/68881 instructions (psave, prestore, fsave, fb*…), so this prints them as
LF_CALL / LF_RET and leaves everything else to m68k-elf-objdump.

usage: python3 linef_dis.py LO HI [LO HI ...]      (hex addresses, HI exclusive)
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROM_IMAGE = PROJECT.parents[1] / "tools" / "hatari" / "TOS102US.img"
NAMES = PROJECT / "names.txt"

ROM_BASE = 0xFC0000
LINE_F_TABLE = 0xFEE900          # the handler's call table, one longword per index
LINE_F_NIBBLE = 0xF              # an opcode word whose top nibble is $F is a GEM call or return
LINE_F_INDEX_MASK = 0xFFF
LINE_F_RETURN_BIT = 0x1          # odd = return
LINE_F_MASK_BITS = 0xFFE         # the return word's register-mask field, before the << 2
LINE_F_MASK_SHIFT = 2
WORD_BYTES = 2
LONG_BYTES = 4
# How far one re-decode runs on from the address a Line-F word left objdump short of: past the next few instructions,
# which is where it falls back into step.
REDECODE_BYTES = 0x80
# What a byte objdump decodes as no instruction at all reads as.
UNDECODED = "??"

_OBJDUMP_LINE = re.compile(r"\s*([0-9a-f]+):\s+((?:[0-9a-f]{4} )+)\s*(.*)")
_CONTINUATION = re.compile(r"\s+((?:[0-9a-f]{4} )+)\s*$")
_NAME_LINE = re.compile(r"fn\s+0x([0-9a-fA-F]+)\s+(\S+)")


def load_names():
    """{address: name} from the project's name map."""
    names = {}
    for line in NAMES.read_text().splitlines():
        match = _NAME_LINE.match(line)
        if match:
            names[int(match.group(1), 16)] = match.group(2)
    return names


def objdump(lo, hi, rom=ROM_IMAGE):
    """{address: (length, text)} for [lo, hi) as m68k-elf-objdump decodes it, out of the ROM image file `rom`."""
    listing = subprocess.run(
        ["m68k-elf-objdump", "-D", "-b", "binary", "-m", "m68k:68000", f"--adjust-vma={ROM_BASE:#x}",
         f"--start-address={lo}", f"--stop-address={hi}", str(rom)],
        capture_output=True, text=True, check=True).stdout
    decoded, last = {}, None
    for line in listing.splitlines():
        match = _OBJDUMP_LINE.match(line)
        if match:
            address, words, text = int(match.group(1), 16), match.group(2).split(), match.group(3).strip()
            # objdump prints an 8-byte instruction's last extension word on a line of its own, with an address and
            # no text: it continues the instruction before it, it is not an instruction (`move.l abs.l,d16(An)`).
            if not text and last is not None and address == last + decoded[last][0]:
                decoded[last][0] += len(words) * WORD_BYTES
                continue
            decoded[address] = [len(words) * WORD_BYTES, text]
            last = address
            continue
        match = _CONTINUATION.match(line)
        if match and last is not None:
            decoded[last][0] += len(match.group(1).split()) * WORD_BYTES
    return decoded


def sweep(lo, hi, rom=ROM_IMAGE):
    """`[(address, length, text)]`: [lo, hi) of the ROM image file `rom` decoded as the instructions it is. A Line-F
    word, CALL or RETURN, is one word and its text None (`line_f_text` names it); everything else is objdump's, read
    in one pass and re-read from an address objdump ran past — reading a Line-F word as a longer FPU instruction —
    so the swallowed word cannot shift the next instruction. A byte no instruction decodes from reads UNDECODED."""
    image = Path(rom).read_bytes()
    decoded, found, at = objdump(lo, hi, rom), [], lo
    while at < hi:
        if _word(image, at) >> 12 == LINE_F_NIBBLE:
            found.append((at, WORD_BYTES, None))
            at += WORD_BYTES
            continue
        if at not in decoded:
            decoded.update(_redecoded(at, hi, rom))
        length, text = decoded.get(at, (WORD_BYTES, UNDECODED))
        found.append((at, length, text))
        at += length
    return found


def _redecoded(at, hi, rom):
    """objdump's decode of a window from `at`, less an instruction the window's end may have cut short: objdump prints
    the whole instruction's text but only the words before its stop address, so its length would be short (an 8-byte
    `movel` read as 4) and the sweep would step into its operand. The window's end is the span's own only at `hi`."""
    stop = min(at + REDECODE_BYTES, hi)
    return {address: entry for address, entry in objdump(at, stop, rom).items()
            if stop == hi or address + entry[0] < stop}


def _word(image, at):
    return struct.unpack_from(">H", image, at - ROM_BASE)[0]


def line_f_text(image, at, names):
    """The Line-F word at `at` as GEM means it: a call through the handler's table, or a return and its mask."""
    opcode = _word(image, at)
    if opcode & LINE_F_RETURN_BIT:
        return f"LF_RET mask={(opcode & LINE_F_MASK_BITS) << LINE_F_MASK_SHIFT:03x}"
    target = struct.unpack_from(">I", image, LINE_F_TABLE + (opcode & LINE_F_INDEX_MASK) - ROM_BASE)[0]
    return f"LF_CALL {target:#08x} {names.get(target, '')}".rstrip()


def disassemble(lo, hi, names, rom=ROM_IMAGE):
    """Print [lo, hi) of the ROM image file `rom` as `sweep` decodes it, the Line-F words named."""
    image = Path(rom).read_bytes()
    for at, length, text in sweep(lo, hi, rom):
        words = " ".join(f"{_word(image, at + k):04x}" for k in range(0, length, WORD_BYTES))
        label = f"   <{names[at]}>" if at in names else ""
        print(f"  {at:06x}: {words:<24} {line_f_text(image, at, names) if text is None else text}{label}")


def main(arguments):
    if not arguments or len(arguments) % 2:
        sys.exit(__doc__)
    names = load_names()
    for lo, hi in zip(arguments[::2], arguments[1::2]):
        disassemble(int(lo, 16), int(hi, 16), names)
        print("----")


if __name__ == "__main__":
    main(sys.argv[1:])
