#!/usr/bin/env python3
"""Static depacker for the .RAD/.CRU resource cruncher (Wonder Boy in Monsterland, Atari ST).

Reverse-engineered from the depack routine inside the game itself, `AUTO/SWB.PRG`
(text $596a..$5a40, which the startup stub copies to runtime $5d62); the annotated
disassembly is `projects/wonderboy/notes/rad_depacker.asm`.

Container (no magic — the game reaches these files only through its own file index)
  +0   be32  packed length = filesize - 12   (how the routine finds EOF)
  +4   be32  unpacked length
  +8   be32  checksum: XOR of every longword of the stream
  +12  packed stream, consumed BACKWARDS from EOF down to +12

The routine never learns the size of the buffer the file was read into, so EOF comes from that
first long alone and trailing slack (a whole-sector read, a slice of a larger file) changes
nothing. Because the walk is by longwords, the packed length is always a multiple of 4.

Bitstream
  Bits leave a one-longword buffer LSB-first, refilled from *decreasing* addresses.
  Each longword carries its own end marker: the buffer is spent once the shifted-out
  remainder is 0, and the refill rotates a fresh 1 into bit 31 as the next marker, so
  every refilled longword yields exactly 32 data bits. The first (seed) longword is
  read without a marker, so its own highest set bit ends it.

Tokens (the output is filled backwards too, from unpacked_length down to 0)
  00           literal run: 3-bit count, 1..8 bytes, each 8 bits off the stream
  01           match, length 2,  8-bit offset
  1 00         match, length 3,  9-bit offset
  1 01         match, length 4, 10-bit offset
  1 10         match, 8-bit length field (1..256), 12-bit offset
  1 11         literal run: 8-bit count, 9..264 bytes
  A match copies `length` bytes one at a time from `offset` bytes ABOVE the write
  pointer (already-written data, since the buffer fills downwards), so an offset
  below the length repeats a short pattern.

The loop ends when the write pointer reaches the start of the destination; a well-formed stream
lands there with the stream pointer exactly back at +12 and the running checksum back at 0.

WHERE THIS DEVIATES FROM THE 68000
  The routine has essentially no error handling. It decodes whatever it is handed and reports
  only one thing: a non-zero checksum, by returning $ffffffff in d0 (`moveq #$ff,d0` SIGN-EXTENDS
  — it is not $ff). A host cannot follow it into reading and writing outside its buffers, so
  EVERY refusal below is a guard the original does not have, and each one names itself: see
  `DepackError` and the `GUARD_*` constants. Three of them refuse a file the 68000 would decode
  without complaint rather than merely failing earlier on a file it would reject:
    * GUARD_OUTPUT_OVERRUN     — a token running past the START of the destination. The routine
                                 tests its write pointer only BETWEEN tokens, so it writes below
                                 the buffer and then exits.
    * GUARD_MATCH_PAST_END     — a match sourced above the destination's end. The routine reads
                                 whatever is there.
    * GUARD_STREAM_NOT_CLOSED  — the stream pointer did not come back to +12. The routine gates
                                 on the checksum alone, and a clean checksum does NOT imply it:
                                 a longword never read is never XORed in either.
  Which guard real damage actually reaches, and which are pinned only synthetically, is recorded
  in `projects/wonderboy/notes/rad_differential.py` and
  `tools/recreate_kit/test/test_depack_rad.py`.

Usage:
  python3 depack_rad.py PACKED            # writes PACKED.out
  python3 depack_rad.py PACKED -o OUT

Exit status:
  0  depacked
  1  unreadable input, unwritable output, or not a stream this depacker handles
  2  bad command line
"""
import collections
import struct
import sys

import depack_common

HDR_LEN = 12          # packed length + unpacked length + checksum; the stream starts here
WORD = 4              # the stream is read a longword at a time, so lengths are longword multiples
# The seed reads one longword below the stream end, so a file shorter than the header plus that
# longword has no stream to seed from at all.
MIN_FILE_LEN = HDR_LEN + WORD
MAX_UNPACKED = depack_common.MAX_UNPACKED
# The other cruncher in this workspace's Wonder Boy corpus — a cracked release's, not the
# game's. Both wrap a backwards-consumed stream in a 12-byte header, so refuse it by name
# rather than decode it into nonsense. depack_lsd returns the favour.
LSD_MAGIC = b"LSD!"

MARKER = 1 << 31      # the refill's end-of-longword sentinel, rotated in above the data bits

# --- the guards, each a distinct invariant a file can break -----------------------------------
# A refusal names the guard that fired, so a caller can assert WHICH invariant broke instead of
# just that one did. The guards overlap — a badly damaged file trips several of them, whichever
# comes first — so the exception TYPE alone identifies nothing.
GUARD_SHORT_FILE = "file too short"
GUARD_LSD_MAGIC = "LSD! magic"
GUARD_STORED_FORM = "stored form"
GUARD_PACKED_LENGTH = "packed length"
GUARD_STREAM_PAST_EOF = "stream past the end of the file"
GUARD_NO_OUTPUT = "zero unpacked length"
GUARD_UNPACKED_TOO_BIG = "unpacked length too large"
GUARD_STREAM_UNDERRUN = "stream underrun"
GUARD_OUTPUT_OVERRUN = "output overrun"
GUARD_MATCH_PAST_END = "match past the end of the output"
GUARD_STREAM_NOT_CLOSED = "stream not closed"
GUARD_CHECKSUM = "checksum"

# --- token encoding -------------------------------------------------------------------------
# First bit: 0 = a short token (one more bit picks which), 1 = a 2-bit selector follows.
SEL_BITS = 2
SEL_LONG_MATCH = 2                 # 8-bit length field, 12-bit offset
SEL_LONG_LITERALS = 3              # 8-bit count field
# Selector 0 and 1 are fixed-length matches; the wider match gets the wider offset.
SHORT_MATCH_LEN = (3, 4)
SHORT_MATCH_OFF_BITS = (9, 10)
# The "01" token: the shortest match the format can express.
MATCH2_LEN = 2
MATCH2_OFF_BITS = 8
# Literal runs. The ROM's dbf copies count+1 bytes, which is folded into the bases here.
LIT_SHORT_BITS, LIT_SHORT_BASE = 3, 1          # 1..8 bytes
LIT_LONG_BITS, LIT_LONG_BASE = 8, 9            # 9..264 bytes
# The "1 10" match: an 8-bit field, again copying count+1 bytes.
LONG_MATCH_LEN_BITS, LONG_MATCH_LEN_BASE = 8, 1
LONG_MATCH_OFF_BITS = 12

LITERAL_BITS = 8      # a literal byte is read as 8 plain stream bits, not off the byte stream

# What parse_header recovers: the size to allocate, where the backwards walk starts, and the
# checksum the walk has to reproduce.
Header = collections.namedtuple("Header", "unpacked_size stream_end checksum")


class DepackError(Exception):
    """The file is not a .RAD stream, or it did not decode the way the 68000 routine would.

    `.guard` is one of the `GUARD_*` constants: the invariant that refused this file. Assert on
    that, not on the exception type — several guards refuse the same malformed file at different
    points, so a type-only check would still pass with the guard under test deleted.
    """

    def __init__(self, guard, detail):
        super().__init__("%s: %s" % (guard, detail))
        self.guard = guard


class _Stream:
    """The packed stream read BACKWARDS, one longword at a time, XOR-summing as it goes."""

    def __init__(self, data, stream_end, checksum):
        self.data = data
        self.pos = stream_end       # index just above the next longword to be read
        self.checksum = checksum    # d5: seeded from the header, must return to 0
        self.buf = self.long()      # d0: seeded raw, so this longword's own top set bit is its marker

    def long(self):
        self.pos -= WORD
        if self.pos < 0:
            raise DepackError(GUARD_STREAM_UNDERRUN,
                              "the stream ran off the front of the file — the decode asked for "
                              "more longwords than the header's packed length holds")
        value = struct.unpack_from(">I", self.data, self.pos)[0]
        self.checksum ^= value
        return value

    def bit(self):
        value = self.buf & 1                       # lsr.l #1,d0 -> C
        self.buf >>= 1
        if self.buf:
            return value
        refill = self.long()                       # spent: the next longword brings its own marker
        self.buf = MARKER | (refill >> 1)          # move #$10,ccr / roxr.l #1,d0
        return refill & 1

    def bits(self, n):
        """`n` stream bits as one value, MSB first (the ROM's roxl into d2)."""
        value = 0
        for _ in range(n):
            value = (value << 1) | self.bit()
        return value


def _require_room(dst, count, what):
    """Refuse a token that would run past the START of the destination (GUARD_OUTPUT_OVERRUN).

    A deviation: the 68000 tests its write pointer only between tokens, so it writes below the
    buffer and exits, which a host must not imitate. No file on either disk reaches this — it is
    pinned synthetically, by test_depack_rad.test_token_overrunning_the_output_start_is_refused.
    """
    if count > dst:
        raise DepackError(GUARD_OUTPUT_OVERRUN,
                          "%s of %d overruns the start of the output at %d" % (what, count, dst))


def _copy_match(out, dst, length, offset):
    """Copy `length` bytes from `offset` above the write pointer, one byte at a time.

    Byte-at-a-time is not an implementation detail: an offset smaller than the length makes the
    copy read bytes this same match has just written, which is how the format encodes runs.
    """
    _require_room(dst, length, "match")
    for _ in range(length):
        dst -= 1
        # offset 0 sources the byte being written, i.e. whatever the destination already held: 0
        # here, stale buffer contents on the machine. Unreached by the corpus (0 of 27,166
        # matches); rad_differential poisons its destination so a future one cannot pass silently.
        source = dst + offset
        if source >= len(out):
            # Also a deviation: the 68000 reads whatever lies above the destination. Reached by
            # real damage — disk2/OVALAY4B.RAD and OVALAY5B.RAD both refuse here.
            raise DepackError(GUARD_MATCH_PAST_END,
                              "match at %d reads %d byte(s) past the end of the output"
                              % (dst, source - len(out) + 1))
        out[dst] = out[source]
    return dst


def _copy_literals(stream, out, dst, count):
    _require_room(dst, count, "literal run")
    for _ in range(count):
        dst -= 1
        out[dst] = stream.bits(LITERAL_BITS)
    return dst


def _decode_token(stream, out, dst):
    """Decode one token at the write pointer `dst`; return the new write pointer."""
    if not stream.bit():
        if stream.bit():
            return _copy_match(out, dst, MATCH2_LEN, stream.bits(MATCH2_OFF_BITS))
        return _copy_literals(stream, out, dst,
                              stream.bits(LIT_SHORT_BITS) + LIT_SHORT_BASE)
    selector = stream.bits(SEL_BITS)
    if selector == SEL_LONG_LITERALS:
        return _copy_literals(stream, out, dst,
                              stream.bits(LIT_LONG_BITS) + LIT_LONG_BASE)
    if selector == SEL_LONG_MATCH:
        length = stream.bits(LONG_MATCH_LEN_BITS) + LONG_MATCH_LEN_BASE
        return _copy_match(out, dst, length, stream.bits(LONG_MATCH_OFF_BITS))
    length = SHORT_MATCH_LEN[selector]
    return _copy_match(out, dst, length, stream.bits(SHORT_MATCH_OFF_BITS[selector]))


def depack(data, header):
    """Inflate one .RAD stream. `data` is the whole file (the routine indexes off both ends)."""
    stream = _Stream(data, header.stream_end, header.checksum)
    out = bytearray(header.unpacked_size)
    dst = header.unpacked_size
    while dst > 0:
        dst = _decode_token(stream, out, dst)
    # A deviation, and a strictly STRONGER gate than the 68000's, not an early form of it: a
    # longword the decode never reads is never XORed in either, so a stream padded with unread
    # longwords closes with a clean checksum and the pointer short of +12 — and the routine
    # accepts it (confirmed under Musashi). A correct decode consumes every longword exactly once.
    if stream.pos != HDR_LEN:
        raise DepackError(GUARD_STREAM_NOT_CLOSED,
                          "the stream pointer stopped at %d, not at the start of the stream (%d)"
                          % (stream.pos, HDR_LEN))
    if stream.checksum:
        raise DepackError(GUARD_CHECKSUM,
                          "the header's XOR does not cancel (residue %#010x) — the packed data "
                          "is damaged" % stream.checksum)
    return bytes(out)


def parse_header(data):
    """Return the Header, or raise if this is not a file this depacker handles."""
    if len(data) < MIN_FILE_LEN:
        raise DepackError(GUARD_SHORT_FILE,
                          "file is too short to hold a .RAD header and one stream longword")
    if data[:len(LSD_MAGIC)] == LSD_MAGIC:
        raise DepackError(GUARD_LSD_MAGIC,
                          "this is an LSD! stream, a DIFFERENT cruncher — use depack_lsd.py")
    packed, unpacked, checksum = struct.unpack(">III", data[:HDR_LEN])
    if packed == unpacked:
        raise DepackError(GUARD_STORED_FORM,
                          "packed and unpacked lengths are both %d: this is the STORED form of "
                          "the container (SPRITES.CRU), whose body is verbatim data and which "
                          "the game never passes to the depack routine" % packed)
    if packed < WORD or packed % WORD:
        raise DepackError(GUARD_PACKED_LENGTH,
                          "packed length %d is not a positive multiple of %d; the routine walks "
                          "the stream by longwords and could never land on its start"
                          % (packed, WORD))
    stream_end = HDR_LEN + packed
    if stream_end > len(data):
        raise DepackError(GUARD_STREAM_PAST_EOF,
                          "header's packed length is %d, putting the end of the stream at %d — "
                          "outside the %d bytes of this file" % (packed, stream_end, len(data)))
    if unpacked == 0:
        # The routine's loop tests its write pointer only at the bottom, so a zero-length output
        # makes it decode one token below the destination. Refuse rather than model that.
        raise DepackError(GUARD_NO_OUTPUT, "header claims 0 unpacked bytes; there is no output "
                                           "to decode")
    if unpacked > MAX_UNPACKED:
        raise DepackError(GUARD_UNPACKED_TOO_BIG,
                          "header claims %d unpacked bytes, more than the 68000's whole %d-byte "
                          "address space" % (unpacked, MAX_UNPACKED))
    return Header(unpacked, stream_end, checksum)


def _decode(data):
    """The whole file in, the inflated bytes out — what the shared command line drives."""
    return depack(data, parse_header(data))


if __name__ == "__main__":
    sys.exit(depack_common.main("depack_rad.py", __doc__, _decode, DepackError))
