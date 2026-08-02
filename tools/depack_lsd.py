#!/usr/bin/env python3
"""Static depacker for the "LSD!" backwards-LZ cruncher (Wonder Boy in Monsterland, Atari ST).

Reverse-engineered from the depack routine inside `AUTO/VAPOUR2.PRG` (text $7ec..$94a);
the annotated disassembly is `projects/wonderboy/notes/lsd_depacker.asm`.

Container
  +0   'LSD!'
  +4   be32  unpacked size
  +8   be32  filesize - 4   (how the routine finds EOF: a0 = (file+8) + this - 4)
  +12  packed stream, consumed BACKWARDS from EOF down to +12

EOF comes from that third long, *not* from the length of the buffer holding the file — the
routine never learns how big that buffer is. So anything past EOF is slack and is ignored,
exactly as it is on the machine: a stream sliced out of a larger file, or one read in whole
sectors, depacks the same as the byte-exact file.

Bitstream
  Bits leave a one-byte buffer MSB-first, refilled from *decreasing* addresses. Each byte
  carries its own end marker: the buffer is spent once the shifted-out remainder is 0, and
  the refill rotates that marker bit back in, so every refilled byte yields exactly 8 bits.
  The first buffer byte is EOF-3, or EOF-4 when the final word is negative.

Tokens (the output is filled backwards too, from unpacked_size down to 0)
  1 <count>   literal run: copy `count` bytes straight off the stream (1, or 2..1038 coded)
  0           no literals
  then, unless the stream pointer has reached +12, exactly one match:
    <length>  2, 3, 4..5, 6..9, 10..1033        (unary prefix selects a tier of extra bits)
    <offset>  length == 2: 0..63 / 64..575
              length >= 3: 0..31 / 32..287 / 288..4383
    copies `length` bytes from `offset` bytes ABOVE the write pointer (already-written data,
    since the buffer fills downwards).

Usage:
  python3 depack_lsd.py PACKED            # writes PACKED.out
  python3 depack_lsd.py PACKED -o OUT

Exit status:
  0  depacked
  1  unreadable input, unwritable output, or not a stream this depacker handles
  2  bad command line
"""
import collections
import struct
import sys

import depack_common

MAGIC = b"LSD!"
HDR_LEN = 12          # magic + unpacked size + end-of-file field; the stream starts here
# The seed reads the word just below the stream end (`tst.w -(a0)`, then one or two `move.b -(a0)`),
# so a file shorter than the header plus that word has no stream to seed from at all.
SEED_LOOKBACK = 2
MIN_FILE_LEN = HDR_LEN + SEED_LOOKBACK
MAX_UNPACKED = depack_common.MAX_UNPACKED

# Literal-run count: tiers tried from the last table entry down to 0; an all-ones value escapes
# to the next tier.
LIT_BITS = (10, 3, 2, 2)
LIT_BASE = (14, 7, 4, 1)
# Match length: the unary prefix (0, 10, 110, 1110, 1111) picks the tier directly.
LEN_BITS = (10, 2, 1, 0, 0)
LEN_BASE = (10, 6, 4, 3, 2)
# Match offset for length >= 3, tier from a 2-bit-max unary prefix. (The ROM table holds
# these bit counts minus one, because its read loop is a plain dbf.)
OFF_BITS = (12, 5, 8)
OFF_BASE = (288, 0, 32)
# Match offset for length == 2: one flag bit picks the tier.
OFF2_BITS = (6, 9)
OFF2_BASE = (0, 64)

# Every tier ladder is walked from its widest entry down; the ROM loads that start index as a
# `moveq` immediate, which is just the table's last index.
LIT_TIER_TOP = len(LIT_BITS) - 1
LEN_TIER_TOP = len(LEN_BITS) - 1
OFF_TIER_TOP = len(OFF_BITS) - 1

# What parse_header recovers: the size to allocate, and where the backwards walk starts.
Header = collections.namedtuple("Header", "unpacked_size stream_end")


class DepackError(Exception):
    """The file is not an LSD! stream, or it did not decode to exactly the size claimed."""


class _Stream:
    """The packed stream read BACKWARDS. Byte reads and bit reads share one pointer (a0)."""

    def __init__(self, data, pos):
        self.data = data
        self.pos = pos            # index just above the next byte to be read
        self.buf = self.byte()    # d0: seeded raw, so this byte's own low set bit is its marker

    def byte(self):
        self.pos -= 1
        if self.pos < 0:
            raise DepackError("stream ran off the front of the file")
        return self.data[self.pos]

    def bit(self):
        carry = self.buf >> 7                      # lsl.b #1,d0 -> C
        self.buf = (self.buf << 1) & 0xFF
        if self.buf:
            return carry
        b = self.byte()                            # spent: refill, roxl.b #1,d0 puts the
        self.buf = ((b << 1) | carry) & 0xFF       # marker back in as this byte's marker
        return b >> 7

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def unary(self, limit):
        """Count leading 1-bits, at most `limit` (the ROM counts down with dbf)."""
        n = 0
        while n < limit and self.bit():
            n += 1
        return n


def _stream_top(data, stream_end):
    """The a0 the routine holds when it seeds the bit buffer, so its first `move.b -(a0),d0`
    reads EOF-3 — or EOF-4 when the last word is negative. `data[stream_end - 2] & 0x80` is
    that `tst.w -(a0); bpl` sign test."""
    last_word_hi = data[stream_end - SEED_LOOKBACK]
    return stream_end - SEED_LOOKBACK - (1 if last_word_hi & 0x80 else 0)


def _literal_count(stream):
    tier = LIT_TIER_TOP
    while True:
        v = stream.bits(LIT_BITS[tier])
        if tier == 0 or v != (1 << LIT_BITS[tier]) - 1:
            return v + LIT_BASE[tier] + 1          # the ROM's dbf copies d1+1 bytes
        tier -= 1


def _match_length(stream):
    tier = LEN_TIER_TOP - stream.unary(LEN_TIER_TOP)
    return stream.bits(LEN_BITS[tier]) + LEN_BASE[tier]


def _match_offset(stream, length):
    if length == 2:
        tier = stream.bit()
        return stream.bits(OFF2_BITS[tier]) + OFF2_BASE[tier]
    tier = OFF_TIER_TOP - stream.unary(OFF_TIER_TOP)
    return stream.bits(OFF_BITS[tier]) + OFF_BASE[tier]


def depack(data, header):
    """Inflate one LSD! stream. `data` is the whole file (the routine indexes off both ends)."""
    unpacked_size = header.unpacked_size
    stream = _Stream(data, _stream_top(data, header.stream_end))
    out = bytearray(unpacked_size)
    dst = unpacked_size
    while True:
        if stream.bit():
            count = _literal_count(stream) if stream.bit() else 1
            if count > dst:
                raise DepackError("literal run of %d overruns the output at %d" % (count, dst))
            for _ in range(count):
                dst -= 1
                out[dst] = stream.byte()
        if stream.pos <= HDR_LEN:
            break
        length = _match_length(stream)
        offset = _match_offset(stream, length)
        if length > dst or dst + offset + length > unpacked_size:
            raise DepackError("match len=%d off=%d out of range at %d" % (length, offset, dst))
        out[dst - length:dst] = out[dst + offset:dst + offset + length]
        dst -= length
    if dst != 0 or stream.pos != HDR_LEN:
        raise DepackError("stream did not close cleanly: %d output byte(s) unwritten, "
                       "stream pointer at %d (want %d)" % (dst, stream.pos, HDR_LEN))
    return bytes(out)


def parse_header(data):
    """Return the Header, or raise if this is not a file this depacker handles.

    Two containers carry the same 12-byte header shape. Only the 'LSD!' one is this
    cruncher; the magic-less one is the game's own .RAD/.CRU resource container, a
    *different* cruncher (see the note in projects/wonderboy/notes/lsd_depacker.asm).
    """
    if len(data) < MIN_FILE_LEN:
        raise DepackError("file is too short to hold an LSD! header")
    field0, unpacked = struct.unpack(">II", data[:8])
    if data[:4] == MAGIC:
        eof_field = struct.unpack(">I", data[8:12])[0]
        # The routine walks a0 to (file+8) + eof_field - 4; only the buffer's real end bounds it.
        stream_end = 4 + eof_field
        if not MIN_FILE_LEN <= stream_end <= len(data):
            raise DepackError("LSD! header's EOF field is %d, putting the end of the stream at %d "
                           "— outside the %d bytes of this file" % (eof_field, stream_end, len(data)))
        if unpacked > MAX_UNPACKED:
            raise DepackError("LSD! header claims %d unpacked bytes, more than the 68000's whole "
                           "%d-byte address space" % (unpacked, MAX_UNPACKED))
        return Header(unpacked, stream_end)
    if field0 == len(data) - HDR_LEN:
        raise DepackError("this is the magic-less .RAD/.CRU container (packed=%d unpacked=%d), "
                       "which is a DIFFERENT cruncher from LSD! — use depack_rad.py"
                       % (field0, unpacked))
    raise DepackError("no 'LSD!' magic and no magic-less header (first longs %#x %#x) — "
                   "not a file this packer produced" % (field0, unpacked))


def _decode(data):
    """The whole file in, the inflated bytes out — what the shared command line drives."""
    return depack(data, parse_header(data))


if __name__ == "__main__":
    sys.exit(depack_common.main("depack_lsd.py", __doc__, _decode, DepackError))
