#!/usr/bin/env python3
"""Static depacker for the Gamex / "PP" LZSS cruncher used on some Atari ST releases.

Algorithm (reverse-engineered from START.TOS's self-depacker):
  control byte C:
    0x00        -> end of stream
    0x01..0x7f  -> literal run of C bytes
    0x80..0xff  -> back-reference: len bits = C & 0x3f
                   C & 0x40 set  -> long : offset = 16-bit (hi,lo),  count = len+3
                   C & 0x40 clr  -> short: offset =  8-bit,          count = len+2
                   copy count+1 bytes from out[-offset] (overlap allowed)
The inflated output is itself a GEMDOS .PRG (starts with 0x601a), so it can then go
through the normal pipeline (headless.sh / PrgLoader).

Usage: depack_gamex.py <packed-in> <depacked-out> [--start 0xNN]
       (without --start, scans for the offset that yields a valid PRG)
"""
import struct
import sys


def depack(data, start, limit=8_000_000):
    out = bytearray()
    i = start
    try:
        while i < len(data) and len(out) < limit:
            c = data[i]; i += 1
            if c == 0:
                break
            if c < 0x80:                       # literal run
                out += data[i:i + c]; i += c
            else:
                lb = c & 0x3f
                if c & 0x40:                   # long offset: hi, lo
                    off = (data[i] << 8) | data[i + 1]; i += 2; count = lb + 3
                else:                          # short offset: 1 byte
                    off = data[i]; i += 1;     count = lb + 2
                if off == 0 or off > len(out):
                    return None
                for _ in range(count + 1):
                    out.append(out[-off])
    except IndexError:
        return None
    return bytes(out)


def is_prg(b):
    if len(b) < 28 or b[:2] != b"\x60\x1a":
        return False
    tlen, dlen, blen, slen = struct.unpack(">IIII", b[2:18])
    return 28 + tlen + dlen + slen <= len(b)   # header self-consistent


def find_stream(data):
    for s in range(0, 0x800):
        out = depack(data, s)
        if out and is_prg(out):
            return s, out
    return None, None


def main():
    src, dst = sys.argv[1], sys.argv[2]
    data = open(src, "rb").read()
    if "--start" in sys.argv:
        s = int(sys.argv[sys.argv.index("--start") + 1], 0)
        out = depack(data, s)
    else:
        s, out = find_stream(data)
    if not out:
        sys.exit("could not depack (wrong packer or stream offset?)")
    open(dst, "wb").write(out)
    tlen, dlen, blen, slen = struct.unpack(">IIII", out[2:18])
    print("depacked %s (stream@0x%x) -> %s" % (src, s, dst))
    print("  %d packed -> %d bytes  |  text=0x%x data=0x%x bss=0x%x sym=0x%x  %s"
          % (len(data), len(out), tlen, dlen, blen, slen,
             "valid PRG" if is_prg(out) else "NOT a clean PRG"))


if __name__ == "__main__":
    main()