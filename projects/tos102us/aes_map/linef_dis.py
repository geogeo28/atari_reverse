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


def objdump(lo, hi):
    """{address: (length, text)} for [lo, hi) as m68k-elf-objdump decodes it."""
    listing = subprocess.run(
        ["m68k-elf-objdump", "-D", "-b", "binary", "-m", "m68k:68000", f"--adjust-vma={ROM_BASE:#x}",
         f"--start-address={lo}", f"--stop-address={hi}", str(ROM_IMAGE)],
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


def disassemble(rom, lo, hi, names):
    """Print [lo, hi): Line-F words decoded here, everything else re-read from objdump at its own address,
    so a Line-F word objdump swallowed into a longer 'instruction' cannot shift the next one."""
    word = lambda at: struct.unpack_from(">H", rom, at - ROM_BASE)[0]
    long = lambda at: struct.unpack_from(">I", rom, at - ROM_BASE)[0]
    at = lo
    while at < hi:
        opcode = word(at)
        if opcode >> 12 == LINE_F_NIBBLE:
            length = WORD_BYTES
            if opcode & LINE_F_RETURN_BIT:
                text = f"LF_RET mask={(opcode & LINE_F_MASK_BITS) << LINE_F_MASK_SHIFT:03x}"
            else:
                target = long(LINE_F_TABLE + (opcode & LINE_F_INDEX_MASK))
                text = f"LF_CALL {target:#08x} {names.get(target, '')}".rstrip()
        else:
            length, text = objdump(at, min(at + 3 * LONG_BYTES, hi)).get(at, (WORD_BYTES, "??"))
        words = " ".join(f"{word(at + k):04x}" for k in range(0, length, WORD_BYTES))
        label = f"   <{names[at]}>" if at in names else ""
        print(f"  {at:06x}: {words:<24} {text}{label}")
        at += length


def main(arguments):
    if not arguments or len(arguments) % 2:
        sys.exit(__doc__)
    rom, names = ROM_IMAGE.read_bytes(), load_names()
    for lo, hi in zip(arguments[::2], arguments[1::2]):
        disassemble(rom, int(lo, 16), int(hi, 16), names)
        print("----")


if __name__ == "__main__":
    main(sys.argv[1:])
