#!/usr/bin/env python3
"""Extract Buggy Boy GRAPHICS.GRA into PNGs.

GRAPHICS.GRA is RLE-compressed (per the game's unpacker FUN_00010620):
  word 0x1234, N  -> N+1 words of 0x0000   (0x1234,0 -> literal 0x1234)
  word 0x5678, N  -> N+1 words of 0xffff   (0x5678,0 -> literal 0x5678)
  0x1234 0x1234 0x1234 -> end of stream
  any other word  -> literal
Decompressed data is contiguous Atari ST bitplanes (4 planes, 8000 bytes each,
i.e. 320x200 16-colour low-res). We render each 32000-byte screen as a PNG.

A 16-colour ST palette (16 words, 0x0RGB, 3 bits/channel) can be supplied via
--pal-file/--pal-off (offset into e.g. BUGGYBOY.PRG); without it, colour index
0..15 maps to greyscale.

Usage: python3 extract_graphics.py GRAPHICS.GRA OUTDIR [--pal-file F --pal-off 0xNNNN]
"""
import struct
import sys
import zlib

PLANE_BYTES = 8000          # one ST low-res bitplane (320*200/8)
SCREEN_BYTES = PLANE_BYTES * 4
W, H = 320, 200
ROW_BYTES = W // 8          # 40 bytes per plane row


def rle_decode(d):
    out = bytearray()
    i, n = 0, len(d)

    def word(p):
        return (d[p] << 8) | d[p + 1]

    while i + 1 < n:
        x = word(i)
        if x == 0x1234:
            c = word(i + 2)
            if c == 0x1234 and i + 4 < n and word(i + 4) == 0x1234:
                break                       # end of stream
            if c == 0:
                out += d[i:i + 2]           # literal 0x1234
            else:
                out += b"\x00\x00" * (c + 1)
            i += 4
        elif x == 0x5678:
            c = word(i + 2)
            if c == 0:
                out += d[i:i + 2]           # literal 0x5678
            else:
                out += b"\xff\xff" * (c + 1)
            i += 4
        else:
            out += d[i:i + 2]               # literal word
            i += 2
    return bytes(out)


def load_palette(path, off):
    """16 ST palette words (0x0RGB, 3 bits/channel) -> list of (r,g,b) 0..255."""
    d = open(path, "rb").read()
    pal = []
    for i in range(16):
        w = struct.unpack(">H", d[off + i * 2:off + i * 2 + 2])[0]
        r, g, b = (w >> 8) & 7, (w >> 4) & 7, w & 7
        pal.append((r * 255 // 7, g * 255 // 7, b * 255 // 7))
    return pal


def render_indices(buf, base):
    """Return 320x200 rows of palette indices (0..15) from 4 contiguous planes."""
    rows = []
    for y in range(H):
        row = bytearray(W)
        for bx in range(ROW_BYTES):
            b0 = buf[base + 0 * PLANE_BYTES + y * ROW_BYTES + bx]
            b1 = buf[base + 1 * PLANE_BYTES + y * ROW_BYTES + bx]
            b2 = buf[base + 2 * PLANE_BYTES + y * ROW_BYTES + bx]
            b3 = buf[base + 3 * PLANE_BYTES + y * ROW_BYTES + bx]
            for bit in range(8):
                s = 7 - bit
                row[bx * 8 + bit] = (((b0 >> s) & 1) | (((b1 >> s) & 1) << 1)
                                     | (((b2 >> s) & 1) << 2) | (((b3 >> s) & 1) << 3))
        rows.append(row)
    return rows


def write_png(path, width, height, rows, pal):
    raw = bytearray()
    for r in rows:
        raw.append(0)                            # filter type 0
        for idx in r:
            raw.extend(pal[idx])                 # RGB triple
    def chunk(tag, body):
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))  # 8-bit RGB
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    pal = [(i * 17, i * 17, i * 17) for i in range(16)]     # default greyscale
    if "--pal-file" in sys.argv:
        pf = sys.argv[sys.argv.index("--pal-file") + 1]
        po = int(sys.argv[sys.argv.index("--pal-off") + 1], 0)
        pal = load_palette(pf, po)
        print("palette from %s @ 0x%x" % (pf, po))
    d = open(src, "rb").read()
    dec = rle_decode(d)
    nscreens = len(dec) // SCREEN_BYTES
    print("compressed %d -> decompressed %d bytes = %d full screens (+%d B)"
          % (len(d), len(dec), nscreens, len(dec) % SCREEN_BYTES))
    import os
    os.makedirs(outdir, exist_ok=True)
    montage = []
    for s in range(nscreens):
        rows = render_indices(dec, s * SCREEN_BYTES)
        write_png("%s/screen_%02d.png" % (outdir, s), W, H, rows, pal)
        montage.extend(rows[::2])                # every other row for the overview
    if nscreens:
        write_png("%s/_montage.png" % outdir, W, len(montage), montage, pal)
    print("wrote %d screen PNGs + _montage.png to %s" % (nscreens, outdir))


if __name__ == "__main__":
    main()