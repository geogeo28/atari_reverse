"""The FAT, read and written as a pseudo-file — `src/gemdos/fs_io.c`'s `$fc6038`, `$fc5f44`, `$fc7e24`.

Every case here runs the WHOLE engine underneath: a FAT entry is a seek of the DMD's FAT OFD and a
two-byte transfer through `$fc6218`, the buffer cache and the staged `Rwabs` — so a FAT read lands in
a FAT buffer (list 0) exactly as it would on a real machine, and a FAT write leaves that buffer DIRTY
for `fs_disk.c`'s flush to write to both copies. What each case asserts on top of the byte diff is
the ENTRY: the value, which cluster's nibbles moved and which stood.

The FAT12 arithmetic the ROM does and these cases pin: entry `n` is the pair at byte `n + n/2`,
byte-swapped, then `& $fff` for an even `n` and `asr.w #4` for an odd one — SIGNED, so an odd
entry with bit 11 set comes back with `$f000` over it: `$ff8..$ffe`, and every cluster number from
`$800` up, are negative for an odd cluster and positive for an even one. (A floppy's FAT12 never
holds a cluster number that high, which is why only the reserved values show it in practice.) `$fff` alone is turned into -1, and only on an even
cluster: an odd `$fff` comes back as the word `$ffff`, which every caller's `cmp.w #-1` reads the same.
"""
import ctypes
import struct
from pathlib import Path

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu

import case
import fs_io as io
import gemdos
import gemdos_fs as fs

_lib.gemdos_split_shift.restype = ctypes.c_uint32
_lib.gemdos_fat_get.restype = ctypes.c_uint32
_lib.gemdos_fat_set.restype = None

# The FAT's first record in the DMD's pseudo-record space, and its BIOS record (the SECOND copy).
FAT_BIOS_RECORD = fs.record_of(fs.BCB_TYPE_FAT, fs.FAT_PSEUDO_RECORD)

# The FAT this file's cases read, over the base disk's: a free cluster, `$ff8` on an even and an odd
# cluster, and an entry whose pair STRADDLES the FAT's two sectors — cluster 341 is at byte 511.
FREE_CLUSTER = 7
EVEN_FF8, ODD_FF8 = 8, 9
RESERVED_EOC = 0xFF8
STRADDLING = 341
STRADDLING_VALUE = 0x5A3
assert STRADDLING + STRADDLING // 2 == fs.SECTOR_BYTES - 1
# ...and an ordinary cluster number with bit 11 set on an ODD entry, which the signed shift turns
# negative just as it does `$ff8`: the quirk is not about the reserved values at all.
ODD_HIGH, HIGH_VALUE = 11, 0x9AB
FAT = {EVEN_FF8: RESERVED_EOC, ODD_FF8: RESERVED_EOC, STRADDLING: STRADDLING_VALUE,
       ODD_HIGH: HIGH_VALUE}


def _fat_get_pokes(cluster, pokes=None):
    return {**io.disk(FAT), **(pokes or {}), **case.args(">HI", cluster & fs.D0_LOW_WORD, fs.DMD_AT)}


def _fat_get(cluster, pokes=None):
    return io.run(addrs.GEMDOS_FAT_GET,
                  lambda lib, buf: lib.gemdos_fat_get(fs.ENTRY_D0, buf, cluster & fs.D0_LOW_WORD,
                                                      fs.DMD_AT),
                  _fat_get_pokes(cluster, pokes), regs={"d0": fs.ENTRY_D0})


# ---- the host build's frame word -----------------------------------------------------------------
GEMDOS_HEADER = Path(__file__).resolve().parents[1] / "include" / "gemdos" / "gemdos.h"

def test_the_host_frame_word_is_inside_the_dropped_band_below_every_frame():
    """`GEMDOS_HOST_FRAME_WORD` stands in, off target, for the ROM's `-2(a6)`: the word a FAT
    routine hands the engine as its buffer. It must be where the differential drops bytes on both
    shores, and below the deepest frame the kit calls legitimate and the `savptr` frame this wave
    declares, so nothing the ORACLE writes can land on it."""
    at = addrs.parse(GEMDOS_HEADER)["GEMDOS_HOST_FRAME_WORD"]
    assert emu.STACK_GUARD_LO <= at and at + 2 <= emu.STACK_TOP - emu.STACK_SCRATCH
    assert at + 2 <= gemdos.FRAME_AT


# ---- split_shift, $fc7e24 -------------------------------------------------------------------------

REMAINDER_AT = fs.USER_AT
REMAINDER_BYTES = 4                     # the word stored, and the word after it a LONG store would reach


def _split_shift_pokes(value, shift):
    return {REMAINDER_AT: bytes([fs.SLACK_FILL]) * REMAINDER_BYTES,
            **case.args(">IIH", REMAINDER_AT, value, shift)}


@pytest.mark.parametrize("value,shift", (
    (0x0001_2345, 9),           # a position -> its sector, and the offset inside it
    (0xFFFF_EDCB, 9),           # ...NEGATIVE: `asr.l` keeps the sign, the mask keeps the low bits
    (0x0001_2345, 0),           # mask[0] is 0: no remainder, the value back whole
    (0x89AB_CDEF, 16),          # mask[16] is $ffff, which `ext.l` widens to the whole longword
    (0x7FFF_FFFF, 1),
))
def test_split_shift_answers_the_quotient_and_stores_the_remainder_word(value, shift):
    """POISONED: the split touches no BIOS, no pool and no pointer it follows, so the attribution
    pass runs — the remainder word's store is a compared fact even where it rewrites what was there."""
    result = io.run(addrs.GEMDOS_SPLIT_SHIFT,
                    lambda lib, buf: lib.gemdos_split_shift(buf, REMAINDER_AT, value, shift),
                    _split_shift_pokes(value, shift), poison=True)
    signed = value - (1 << 32) if value & 0x8000_0000 else value
    assert result.info["ret"] == (signed >> shift) & 0xFFFF_FFFF
    assert case.written(result.info, REMAINDER_AT, 2) == value & ((1 << shift) - 1) & fs.D0_LOW_WORD
    assert result.after(REMAINDER_AT + 2, 2) == bytes([fs.SLACK_FILL]) * 2, "a LONG was stored"


# PAST THE TABLE'S MASKS: the index is a signed word and nothing bounds it, so a shift of -1 — what
# `$fc53c0` makes of a zero geometry field — reads the word BELOW the table, 17 reads its second $ffff
# and 18 the ROM's next bytes; the shift itself is `asr.l` by a register, modulo 64 (-1 is 63), so a
# count of 32..63 is the value's sign — which 40 tells apart from a count taken modulo 32.
SHIFT_COUNT_MASK = 63
LONG_BITS = 32
MASK_TABLE_ENTRY_BYTES = 2
OUTSIDE_THE_MASKS = (0xFFFF, 17, 18, 40)


def _rom_mask(shift):
    """The word the ROM's table holds at signed index `shift`, read out of the captured ROM."""
    index = ctypes.c_int16(shift).value
    return case.word_in(BASE_IMAGE, addrs.GEMDOS_BIT_MASK_TABLE + index * MASK_TABLE_ENTRY_BYTES)


@pytest.mark.parametrize("shift", OUTSIDE_THE_MASKS, ids=("-1, below the table", "17", "18, past it", "40, past a long"))
@pytest.mark.parametrize("value", (0x0001_2345, 0xFFFF_EDCB), ids=("positive", "negative"))
def test_split_shift_past_the_masks_reads_the_rom_and_shifts_modulo_64(value, shift):
    result = io.run(addrs.GEMDOS_SPLIT_SHIFT,
                    lambda lib, buf: lib.gemdos_split_shift(buf, REMAINDER_AT, value, shift),
                    _split_shift_pokes(value, shift), poison=True)
    signed = value - (1 << 32) if value & 0x8000_0000 else value
    bits = min(shift & SHIFT_COUNT_MASK, LONG_BITS - 1)
    assert result.info["ret"] == (signed >> bits) & 0xFFFF_FFFF
    assert case.written(result.info, REMAINDER_AT, 2) == _rom_mask(shift) & value & fs.D0_LOW_WORD


def test_a_seek_on_a_drive_with_no_cluster_size_takes_the_mask_below_the_table():
    """...and the same through a caller: a DMD whose `m_clsizb` is 0 has a log2 of -1, so `$fc7d2a`'s
    split of the position stores the in-cluster offset through the word below the table."""
    position = 100
    ofd = io.open_file(fs.SPAN_CLUSTER, fs.SPAN_BYTES)
    result = io.run(addrs.GEMDOS_OFD_SEEK,
                    lambda lib, buf: lib.gemdos_ofd_seek(buf, io.OFD_AT, position),
                    {**io.drive(clsizb=0, clsizb_log2=fs.log2(0)), **ofd,
                     **case.args(">II", io.OFD_AT, position)})
    assert result.info["ret"] == position
    assert result.word(io.OFD_AT + fs.OFD_CLOFF) == _rom_mask(fs.log2(0) & fs.D0_LOW_WORD) & position


# ---- fat_get, $fc6038 ------------------------------------------------------------------------------

@pytest.mark.parametrize("cluster,expected,why", (
    (fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + 1, "an EVEN entry: the low twelve bits of its pair"),
    (fs.SPAN_CLUSTER + 1, fs.SPAN_CLUSTER + 2, "an ODD entry: the high twelve, `asr.w #4`"),
    (fs.SPAN_CLUSTER + 2, 0xFFFF_FFFF, "$fff on an EVEN cluster: `moveq #-1`, the whole longword"),
    (fs.SHORT_CLUSTER, 0x0000_FFFF, "$fff on an ODD cluster: `asr` makes it $ffff, a WORD -1"),
    (FREE_CLUSTER, 0, "a free cluster"),
    (EVEN_FF8, RESERVED_EOC, "$ff8 on an EVEN cluster comes back POSITIVE"),
    (ODD_FF8, 0x0000_FFF8, "...and on an ODD one NEGATIVE — the signed shift"),
    (ODD_HIGH, 0xF000 | HIGH_VALUE, "ANY odd entry with bit 11 set comes back negative"),
    (STRADDLING, STRADDLING_VALUE, "a pair split across the FAT's two sectors"),
))
def test_fat_get_decodes_fat12(cluster, expected, why):
    result = _fat_get(cluster)
    assert result.info["ret"] == expected, why


def test_a_pair_across_two_sectors_is_read_as_a_head_byte_and_a_tail_byte():
    """The transfer engine does not know it is reading a FAT: a two-byte read at offset 511 is a
    one-byte HEAD out of the FAT's first sector and a one-byte TAIL out of its second, two misses."""
    _fat_get(STRADDLING)
    assert [record for _rw, _count, record in io.rwabs_calls()] == [FAT_BIOS_RECORD,
                                                                   FAT_BIOS_RECORD + 1]


def test_a_negative_cluster_is_arithmetic_and_keeps_the_callers_high_half():
    """THE ARM THAT ENDS THE RECURSION: a pseudo-cluster's successor is `cl + 1`, written into D0's
    low word only, and nothing is read."""
    result = _fat_get(fs.FAT_START_CLUSTER)
    assert result.info["ret"] == (fs.callers_high_half(fs.ENTRY_D0)
                                  | ((fs.FAT_START_CLUSTER + 1) & fs.D0_LOW_WORD))
    assert not fs.DISK_CALLS


def test_the_fat_is_read_through_the_fat_list_and_left_cached():
    """A miss fills a FAT buffer — list 0, the FAT's own — from the SECOND copy (`fatrec`), and the
    FAT OFD's cursor is left just past the entry."""
    result = _fat_get(fs.SPAN_CLUSTER)
    offset = fs.SPAN_CLUSTER + fs.SPAN_CLUSTER // 2
    assert io.rwabs_calls() == [(fs.RWABS_READ, 1, FAT_BIOS_RECORD)]
    assert result.order(0)[0] in (0, 1), "the FAT sector did not land on the FAT list"
    assert case.written_long(result.info, fs.FAT_OFD_AT + fs.OFD_POS) == offset + 2


def test_a_cached_fat_sector_is_a_hit():
    """...and a second read of it is the cache's hit: `Mediach` asked, nothing transferred."""
    sector = fs.sector_of(fs.DISK, FAT_BIOS_RECORD)
    cache = fs.cache(fat=[(0, fs.holding(io.DRIVE, region=fs.BCB_TYPE_FAT, record=fs.FAT_PSEUDO_RECORD,
                                         contents=sector))])
    result = _fat_get(fs.SPAN_CLUSTER, cache)
    assert result.info["ret"] == fs.SPAN_CLUSTER + 1
    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_MEDIACH_FN]


@pytest.mark.parametrize("cluster,value,expected", (
    (5, 0x1234, 0x1234),
    (6, 0xFFFF, 0x0000_FFFF),   # FAT16 has no end-of-chain test: the word, as it is
))
def test_fat_get_reads_a_fat16_word(cluster, value, expected):
    result = _fat_get(cluster, {**io.drive(fat16=1), **io.fat16_disk({cluster: value})})
    assert result.info["ret"] == expected


# ---- fat_set, $fc5f44 ------------------------------------------------------------------------------

def _fat_set_pokes(cluster, value, pokes=None):
    return {**io.disk(FAT), **(pokes or {}), **case.args(">HHI", cluster, value, fs.DMD_AT)}


def _fat_set(cluster, value, pokes=None):
    return io.run(addrs.GEMDOS_FAT_SET,
                  lambda lib, buf: lib.gemdos_fat_set(buf, cluster, value, fs.DMD_AT),
                  _fat_set_pokes(cluster, value, pokes), width=case.NO_RESULT)


@pytest.mark.parametrize("cluster,value,stored", (
    (FREE_CLUSTER, 0x123, 0x123),               # odd: the high twelve bits of its pair
    (FREE_CLUSTER + 3, 0x456, 0x456),           # even: the low twelve
    (FREE_CLUSTER, 0xFFFF, 0xFFF),              # `andw #4095`: only twelve bits are stored
    (EVEN_FF8, 0, 0),
))
def test_fat_set_stores_twelve_bits_and_keeps_the_neighbours(cluster, value, stored):
    """A read-modify-write of the pair the entry SHARES: the neighbour's nibbles are what the
    `keep` mask carries through, so both neighbours must read back as they were."""
    result = _fat_set(cluster, value)
    table = io.fat_after(result)
    before = {**io.BASE_FAT, **FAT}
    assert fs.fat12_entry(table, cluster) == stored
    for neighbour in (cluster - 1, cluster + 1):
        assert fs.fat12_entry(table, neighbour) == before.get(neighbour, 0), neighbour
    assert result.word(fs.bcb_at(result.order(0)[0]) + fs.BCB_DIRTY) == fs.BCB_MARKED_DIRTY, (
        "the FAT buffer was not left dirty")
    assert [rw for rw, _count, _record in io.rwabs_calls()] == [fs.RWABS_READ], (
        "the FAT reached the disk — it waits in the cache for a flush")


def test_fat_set_across_the_sector_boundary_writes_both_halves():
    """Both halves of the pair are rewritten, each in its own sector's cached buffer — the FAT as
    the run left it reads back the new entry only if neither half is the disk's stale one."""
    result = _fat_set(STRADDLING, 0x5A5)
    assert fs.fat12_entry(io.fat_after(result), STRADDLING) == 0x5A5


FAT16_NEIGHBOURS = {5: 0x1234, 6: 0x5678, 7: 0x9ABC}


def test_fat_set_stores_a_fat16_word():
    """Entry 6 alone rewritten, little-endian, and its two neighbours' words standing."""
    result = _fat_set(6, 0xBEEF, {**io.drive(fat16=1), **io.fat16_disk(FAT16_NEIGHBOURS)})
    table = io.fat_after(result)
    words = struct.unpack_from("<3H", table, min(FAT16_NEIGHBOURS) * fs.FAT16_ENTRY_BYTES)
    assert words == (0x1234, 0xBEEF, 0x9ABC)


# ---- the registry ----------------------------------------------------------------------------------

def _register_all():
    io.register("fat_split_shift, a negative position", addrs.GEMDOS_SPLIT_SHIFT,
                _split_shift_pokes(0xFFFF_EDCB, 9))
    io.register("fat_get, an odd FAT12 entry", addrs.GEMDOS_FAT_GET, _fat_get_pokes(fs.SPAN_CLUSTER + 1),
                regs={"d0": fs.ENTRY_D0})
    io.register("fat_get, a negative pseudo-cluster", addrs.GEMDOS_FAT_GET,
                _fat_get_pokes(fs.FAT_START_CLUSTER), regs={"d0": fs.ENTRY_D0})
    io.register("fat_set, an odd FAT12 entry", addrs.GEMDOS_FAT_SET, _fat_set_pokes(FREE_CLUSTER, 0x123))


_register_all()
